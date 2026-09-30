"""Batch GPT votes; callers retain missing documents and paused work as pending."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.label.questions import QVER, load_questions
from app.label.rule import GRADE_FIELDS, SEM, grade
from app.label.schema import Tags
from app.llm.base import LLMTask
from app.llm.codex_exec import run_many
from app.llm.fake import FakeBackend
from app.llm.openai_api import OpenAIApiBackend

_TEMPLATE = Path(__file__).with_name('prompts') / 'gpt_label.q1.md'
_USAGE_MESSAGE = 'GPT 판정이 사용량 한도로 멈췄습니다. 잠시 뒤 이어서 진행하거나 설정에서 API 경로로 바꾸세요.'


class LabelerPaused(RuntimeError):
    """Worker must return its leased batch to pending before stopping."""
    def __init__(self, message: str, *, usage_limit: bool = False):
        self.usage_limit = usage_limit
        super().__init__(message)


class GptVote(Tags):
    """Binary tag vote, keyed externally by document ID."""


class GptItem(GptVote):
    doc_id: str = Field(min_length=1)


class GptBatch(BaseModel):
    items: list[GptItem]

    @field_validator('items', mode='before')
    @classmethod
    def salvage_items(cls, value):
        # Validate independently so one malformed/duplicate ID cannot erase peers.
        if not isinstance(value, list):
            raise ValueError('items must be a list')
        value = [item.model_dump() if isinstance(item, GptItem) else item for item in value]
        counts = Counter(item.get('doc_id') for item in value
                         if isinstance(item, dict) and isinstance(item.get('doc_id'), str))
        valid = []
        for item in value:
            if not isinstance(item, dict):
                continue
            doc_id = item.get('doc_id')
            if not isinstance(doc_id, str) or counts[doc_id] != 1:
                continue
            try:
                valid.append(GptItem.model_validate(item))
            except ValidationError:
                continue
        return valid


def _grade_conditions():
    # Derive the prompt's decision table from the single authoritative rule.
    rows = []
    for anchor in (False, True):
        for count in range(len(SEM) + 1):
            for situation in (False, True):
                tags = dict.fromkeys(GRADE_FIELDS, 0)
                tags.update(anchor=anchor, situation=situation)
                tags.update({name: int(index < count) for index, name in enumerate(SEM)})
                rows.append(f'anchor={int(anchor)}, 의미 태그 합={count}, situation={int(situation)} → {grade(tags)}')
    return '\n'.join(rows)


def build_task(docs: list[dict], one_liner: str) -> LLMTask:
    if not isinstance(one_liner, str) or '\n' in one_liner or '\r' in one_liner:
        raise ValueError('one_liner must be a single line')
    ids = [doc.get('doc_id') for doc in docs]
    if any(not isinstance(doc_id, str) or not doc_id for doc_id in ids) or len(set(ids)) != len(ids):
        raise ValueError('Documents require unique nonempty doc_id values')
    instructions = _TEMPLATE.read_text(encoding='utf-8').format(
        one_liner=one_liner,
        definitions=json.dumps(load_questions(), ensure_ascii=False, indent=2),
        grade_conditions=_grade_conditions(),
        documents=json.dumps(sorted(docs, key=lambda doc: doc['doc_id']), ensure_ascii=False, sort_keys=True),
    )
    return LLMTask(task='label_gpt', sid='', instructions=instructions,
                   attachments=[], output_schema=GptBatch)


def _run_id(ids, sid, qver, ctx_key):
    for component in (sid, qver, ctx_key):
        if not isinstance(component, str) or not re.fullmatch(r'[\w-]+', component):
            raise ValueError('Run identity components must contain letters, digits, underscores or hyphens')
    payload = json.dumps(sorted(ids), ensure_ascii=False, separators=(',', ':'))
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return f'lbl-{sid}-{qver}-{ctx_key}-{digest}'


def _pause_message(run_id):
    # The shared runner deliberately hides provider output in its error result.
    # Inspect only this batch's latest attempt, never expose the log to callers.
    path = Path(settings.local_data_dir) / 'llm_runs' / run_id / 'logs/worker-0.log'
    try:
        latest = path.read_text(encoding='utf-8').rsplit('--- attempt ---', 1)[-1].lower()
    except OSError:
        latest = ''
    if any(marker in latest for marker in ('usage limit', 'usage_limit', 'quota exceeded', '사용량 한도')):
        return _USAGE_MESSAGE
    return 'GPT 판정을 완료하지 못해 멈췄습니다. 잠시 뒤 이어서 진행하거나 설정에서 API 경로로 바꾸세요.'


def judge_batch(docs: list[dict], one_liner: str, *, sid: str, ctx_key: str,
                qver: str = QVER) -> tuple[dict[str, GptVote], list[str]]:
    """Judge one batch. T08 supplies context identity and schedules batch retries.

    Duplicate response IDs are ambiguous: requeue that ID, retain unique peers.
    Reordering an unchanged batch preserves both the manifest and its run ID.
    """
    if qver != QVER:
        raise ValueError('Unsupported question version')
    if not docs:
        return {}, []
    task = build_task(docs, one_liner).model_copy(update={'sid': sid})
    ids = [doc['doc_id'] for doc in docs]
    run_id = _run_id(ids, sid, qver, ctx_key)
    backend = settings.label_gpt_backend
    if backend == 'codex_exec':
        result = run_many([task], run_id=run_id, concurrency=settings.label_concurrency)[0]
    elif backend == 'openai_api':
        result = OpenAIApiBackend().run(task)
    elif backend == 'fake':
        items = [GptItem(doc_id=doc_id, anchor=False, sem=dict.fromkeys(SEM, 0),
                         situation=False, reason_code='no_needs', signal=None).model_dump() for doc_id in ids]
        result = FakeBackend(responses={'label_gpt': json.dumps({'items': items})}).run(task)
    else:
        raise ValueError('Unsupported label GPT backend')
    if not result.ok:
        if result.error and result.error.kind in ('parse', 'schema'):
            return {}, ids
        message = (_pause_message(run_id) if backend == 'codex_exec'
                   else 'GPT 판정을 완료하지 못해 멈췄습니다. API 연결 설정을 확인해 주세요.')
        raise LabelerPaused(message, usage_limit=message == _USAGE_MESSAGE)
    expected = set(ids)
    votes = {}
    for item in result.data.items:
        if item.doc_id in expected:
            vote = GptVote.model_validate(item.model_dump(exclude={'doc_id'}))
            level = grade(dict(anchor=vote.anchor, situation=vote.situation, **vote.sem))
            if level == 'non':
                vote.signal = None
            else:
                vote.reason_code = None
            votes[item.doc_id] = vote
    if not votes and backend == 'codex_exec':
        # With no usable peers, the retry has exactly the same run ID. Do not
        # let a schema-valid empty/foreign/duplicate answer poison that cache.
        answer = Path(settings.local_data_dir) / 'llm_runs' / run_id / 'answers/task-0.json'
        if answer.exists():
            bad = answer.parent / 'bad' / answer.name
            answer.replace(bad)
            bad.with_suffix('.reason.txt').write_text('No usable document votes', encoding='utf-8')
    return votes, [doc_id for doc_id in ids if doc_id not in votes]
