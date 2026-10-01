"""Persistent keyword jobs. IDs are k_r{round}g{generation}_{1-based index:04d}."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import json
import logging
from pathlib import Path
from threading import Thread
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import settings
from app.context import store
from app.external import naver_autocomplete, naver_searchad
from app.external.base import Unconnected
from app.keywords import coverage
from app.keywords.events import KeywordEvent, append_event, load_events
from app.keywords.feedback import write_feedback_md
from app.keywords.models import Keyword
from app.keywords.normalize import clean_generated, norm_key
from app.keywords.prompts import MIN_COUNT, PROMPT_VERSION, RoundInputs, build_round_task, r3_input_status
from app.keywords.taxonomy import AXES, is_valid
from app.keywords.volume import attach_volumes
from app.llm.base import Attachment, LLMTask
from app.llm.registry import run_task


logger = logging.getLogger(__name__)


class _JobSuperseded(store.StoreError):
    """The worker no longer owns a running job."""


class RoundJob(BaseModel):
    jobId: str
    status: str
    round: int
    gen: int
    progress: float = 0
    updatedAt: str
    startedAt: str
    error: dict | None = None


class _CheckedPatch(dict):
    """Evaluate a patch inside update_session's existing storage lock.

    store.deep_merge iterates patch.items() after acquiring the lock. Deferring
    validation until then makes read/check/write atomic without nesting flock or
    bypassing the required public writer. Callbacks must not perform I/O writes.
    """
    def __init__(self, sid, build, version=None):
        super().__init__()
        self.sid, self.build, self.version = sid, build, version

    def items(self):
        if self.build is not None:
            build, self.build = self.build, None
            self.update(build(store.assert_writable(self.sid, self.version)))
        return super().items()


class _Replacement:
    """A mapping replacement for the store's deepcopy-on-nondict merge branch."""
    def __init__(self, value):
        self.value = value

    def __deepcopy__(self, memo):
        return deepcopy(self.value, memo)


def mutate(sid, build, version=None, confirm_stage=None):
    return store.update_session(sid, _CheckedPatch(sid, build, version), confirm_stage=confirm_stage)


def execute(fn):
    """Replace with an inline/queued executor only in tests."""
    thread = Thread(target=fn, daemon=True, name='keyword-round')
    thread.start()
    return thread


def _number(n):
    if n not in MIN_COUNT:
        raise store.StoreError('라운드는 1~4입니다', 422, 'validation')


def _order(data, n):
    if any(not data.get('keywordRounds', {}).get(str(i), {}).get('committed')
           or data.get('keywordRounds', {}).get(str(i), {}).get('needsRegeneration') for i in range(1, n)):
        raise store.StoreError('이전 라운드를 먼저 확정하세요')


def _keywords(data):
    return [Keyword.model_validate(k) for k in data.get('keywords', [])]


def _all_keywords(data, exclude_round=None):
    replacing = data.get('keywordRounds', {}).get(str(exclude_round), {}).get('replacing', False)
    by_id = {k.id: k for k in _keywords(data) if not (replacing and k.round == exclude_round and k.origin == 'llm')}
    for number, value in data.get('keywordRounds', {}).items():
        if number == str(exclude_round):
            continue
        for item in value.get('keywords', []):
            by_id.setdefault(item['id'], Keyword.model_validate(item))
    return list(by_id.values())


def start_round(sid, n, regenerate: bool = False, version=None) -> RoundJob:
    _number(n)
    created = False
    def patch(data):
        nonlocal created
        _order(data, n)
        rounds = data.get('keywordRounds', {})
        previous = rounds.get(str(n), {})
        if (previous.get('job') or {}).get('status') == 'running':
            return {}
        restarting = previous.get('needsRegeneration', False) or (
            bool(data.get('stale', {}).get('stage1')) and previous.get('committed', False))
        if previous.get('committed') and n != 4 and not restarting:
            raise store.StoreError('이미 확정된 라운드입니다')
        if (previous.get('job') or {}).get('status') == 'done' and not previous.get('committed') and not regenerate and not restarting:
            raise store.StoreError('생성된 키워드를 먼저 확정하세요')
        gen = previous.get('gen', 0) + 1
        now = store.now()
        job = RoundJob(jobId=uuid4().hex, status='running', round=n, gen=gen,
                       startedAt=now, updatedAt=now)
        created = True
        return {'keywordRounds': {**rounds, str(n): {
            'round': n, 'gen': gen, 'committed': False,
            'replacing': restarting or previous.get('replacing', False),
            'needsRegeneration': False,
            'keywords': previous.get('keywords', []) if regenerate and not previous.get('committed') else [],
            'inputs': {}, 'below_min': None, 'promptVersion': PROMPT_VERSION[n],
            'job': job.model_dump()}}}
    data = mutate(sid, patch, version=version)
    job = RoundJob.model_validate(data['keywordRounds'][str(n)]['job'])
    if created:
        execute(lambda: _run(sid, n, job.jobId))
    return job


def round_status(sid, n):
    _number(n)
    data = store.load_session(sid)
    value = (data or {}).get('keywordRounds', {}).get(str(n))
    if value is None:
        raise store.StoreError('라운드 작업이 없습니다', 404, 'not_found')
    return {**value['job'], 'keywords': value.get('keywords', []),
            'inputs': value.get('inputs', {}), 'below_min': value.get('below_min'),
            'committed': value.get('committed', False), 'promptVersion': value.get('promptVersion')}


def _past_zero_keywords(sid, data):
    result = list(data.get('past_zero_kws', []))
    bk = data.get('projectContext', {}).get('bk')
    if not bk:
        return result
    for path in (Path(settings.local_data_dir) / 'sessions').iterdir():
        if not path.is_dir() or path.name == sid:
            continue
        try:
            prior = store.load_session(path.name) or {}
            if prior.get('projectContext', {}).get('bk') != bk:
                continue
            result.extend(prior.get('past_zero_kws', []))
            collection = prior.get('collectionId')
            if collection and Path(collection).name == collection:
                report_path = Path(settings.local_data_dir) / 'crawl' / path.name / 'collections' / collection / 'report.json'
                report = store.read_json(report_path) or {}
                for kw, counts in report.get('counts', {}).items():
                    if isinstance(counts, dict) and counts and all(isinstance(v, (int, float)) and v == 0 for v in counts.values()):
                        result.append(kw)
        except Exception:
            logger.warning('Skipping prior session %s', path.name)
    return list(dict.fromkeys(result))


def _inputs(sid, data, n):
    ctx = data.get('projectContext', {})
    approved = [k for k in _keywords(data) if k.status == 'approved']
    feedback = write_feedback_md(sid)
    rejected = [k for k in _keywords(data) if k.status == 'rejected']
    signals = '\n'.join(f'{k.kw}: {json.dumps(k.reject, ensure_ascii=False)}' for k in rejected) or None
    cov = coverage_status(data.get('coverage') or {})
    coverage_text = ''
    if cov.get('status') in ('connected', 'ok'):
        coverage_text = json.dumps(cov['missing_top'], ensure_ascii=False) if cov.get('missing_top') else '부족 축 없음'
    elif cov.get('status') in ('failed', 'unavailable'):
        coverage_text = '커버리지 계산 실패 — 축 분포 균형에 집중'
    project_type = ctx.get('projectType', {'choice': 'renewal'})
    return RoundInputs(
        context_md=(store.session_dir(sid) / 'project_context.md').read_text(encoding='utf-8'),
        feedback_md=feedback if n >= 2 or load_events(sid) else None,
        approved=approved,
        distribution={axis: sum(k.axis == axis for k in approved) / len(approved) if approved else 0.0 for axis in AXES},
        rejection_signals=signals, coverage_signals=coverage_text,
        past_zero_kws=_past_zero_keywords(sid, data),
        project_type=project_type.get('choice', 'renewal') if isinstance(project_type, dict) else project_type,
        channels=ctx.get('channels', []), target_scope_text=json.dumps(ctx.get('targetScope'), ensure_ascii=False),
        product_category=json.dumps(ctx.get('productCategory', {}), ensure_ascii=False))


def volumes(kws):
    try:
        return attach_volumes(kws)
    except store.StoreError:
        raise
    except Exception:
        return [k.model_copy(update={'volume': {'monthly': None, 'source': 'searchad', 'at': None,
                                              'error': {'kind': 'request_failed'}}}) for k in kws]


def _job_patch(sid, n, job_id, values):
    def patch(data):
        current = data['keywordRounds'][str(n)]
        if current['job']['jobId'] != job_id or current['job']['status'] != 'running':
            raise _JobSuperseded('작업이 변경되었습니다')
        return {'keywordRounds': {str(n): values}}
    return mutate(sid, patch)


def _run(sid, n, job_id):
    try:
        data = store.assert_writable(sid)
        generation = data['keywordRounds'][str(n)]['gen']
        state = _inputs(sid, data, n)
        _job_patch(sid, n, job_id, {'inputs': {**r3_input_status(state), 'promptVersion': PROMPT_VERSION[n]}})
        result = run_task(build_round_task(sid, n, state))
        if not result.ok:
            _job_patch(sid, n, job_id, {'job': {'status': 'failed', 'error': result.error.model_dump(), 'updatedAt': store.now()}})
            return
        # Retained pending keywords are replaced by this job, not deduplicated against it.
        cleaned, logs = clean_generated([k.model_dump() for k in result.data.keywords], _all_keywords(data, exclude_round=n), set())
        kws = volumes([Keyword(id=f'k_r{n}g{generation}_{i:04d}', kw=''.join(k['kw'].split()),
                               axis=k['axis'], sub=k['sub'], round=n, origin='llm')
                       for i, k in enumerate(cleaned, 1)])
        def finish(latest):
            current = latest['keywordRounds'][str(n)]
            if current['job']['jobId'] != job_id or current['job']['status'] != 'running':
                raise _JobSuperseded('작업이 변경되었습니다')
            existing = {norm_key(k.kw) for k in _all_keywords(latest, exclude_round=n)}
            kept = [k.model_dump() for k in kws if norm_key(k.kw) not in existing]
            return {'keywordRounds': {str(n): {'keywords': kept, 'normalization': logs,
                    'below_min': {'got': len(kept), 'min': MIN_COUNT[n]} if len(kept) < MIN_COUNT[n] else None,
                    'job': {'status': 'done', 'progress': 1, 'error': None, 'updatedAt': store.now()}}}}
        mutate(sid, finish)
    except _JobSuperseded:
        return
    except Exception:
        try:
            _job_patch(sid, n, job_id, {'job': {'status': 'failed', 'error': {'kind': 'backend', 'message': '생성 작업에 실패했습니다'}, 'updatedAt': store.now()}})
        except _JobSuperseded:
            return
        except Exception:
            logger.error('Could not persist failed keyword job for session %s', sid)


def recover_interrupted():
    root = Path(settings.local_data_dir) / 'sessions'
    if not root.exists():
        return
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            data = store.load_session(path.name)
            if not data or store.is_legacy(data):
                continue
            if not any((r.get('job') or {}).get('status') == 'running' for r in data.get('keywordRounds', {}).values()):
                continue
            def patch(current):
                return {'keywordRounds': {n: {'job': {'status': 'failed', 'updatedAt': store.now(),
                    'error': {'kind': 'interrupted', 'message': '작업이 중단되었습니다. 다시 생성하세요'}}}
                    for n, r in current.get('keywordRounds', {}).items() if (r.get('job') or {}).get('status') == 'running'}}
            mutate(path.name, patch)
        except Exception:
            logger.warning('Skipping recovery for session %s', path.name)


def commit_round(sid, n, decisions: list, gen: int | None = None, version=None) -> None:
    _number(n)
    events = []
    def patch(data):
        _order(data, n)
        current = data.get('keywordRounds', {}).get(str(n), {})
        if (current.get('job') or {}).get('status') != 'done' or current.get('committed'):
            raise store.StoreError('확정할 작업이 없습니다')
        if gen is not None and gen != current['gen']:
            raise store.StoreError('다른 창에서 새로 생성되었습니다. 새로고침하세요')
        wanted = {k['id']: k.copy() for k in current.get('keywords', [])}
        if len({d['id'] for d in decisions}) != len(decisions):
            raise store.StoreError('중복 결정입니다', 422, 'validation')
        for decision in decisions:
            if decision.get('gen', current['gen']) != current['gen'] or decision['id'] not in wanted:
                raise store.StoreError('다른 창에서 새로 생성되었습니다. 새로고침하세요')
            if decision['status'] not in ('approved', 'rejected'):
                raise store.StoreError('승인 또는 거절을 선택하세요', 422, 'validation')
            kw = wanted[decision['id']]
            kw.update(status=decision['status'], reject=decision.get('reject'))
            reject = decision.get('reject') or {}
            if kw['status'] == 'rejected' and 'misclassified' in (reject.get('tags') or []) and reject.get('to'):
                dest = reject['to']
                if not is_valid(dest.get('axis', ''), dest.get('sub', '')):
                    raise store.StoreError('이동할 분류를 확인하세요', 422, 'validation')
                events.append(KeywordEvent(ts=store.now(), round=n, type='move', kwId=kw['id'], kw=kw['kw'],
                    from_={'axis': kw['axis'], 'sub': kw['sub']}, to=dest))
                kw.update(axis=dest['axis'], sub=dest['sub'])
            events.append(KeywordEvent(ts=store.now(), round=n, type='approve' if kw['status'] == 'approved' else 'reject',
                                       kwId=kw['id'], kw=kw['kw'], tags=reject.get('tags'), note=reject.get('note')))
        if any(k['status'] == 'pending' for k in wanted.values()):
            raise store.StoreError('모든 키워드를 검토하세요', 422, 'validation')
        return {'keywords': [k for k in data.get('keywords', []) if k['id'] not in wanted
                    and not (current.get('replacing') and k.get('round') == n and k.get('origin') == 'llm')] + list(wanted.values()),
                'keywordRounds': {str(n): {'keywords': list(wanted.values()), 'committed': True, 'needsRegeneration': False, 'replacing': False},
                    **{number: {'committed': False, 'needsRegeneration': True}
                       for number in data.get('keywordRounds', {}) if int(number) > n and current.get('replacing')}}}
    with store.locked(sid):
        data = store.assert_writable(sid, version)
        directory = store.session_dir(sid)
        pinned_version = data.get('version')
        values = patch(data)
        generation = data['keywordRounds'][str(n)]['gen']
        for event in events:
            event.id = f'commit:{n}:{generation}:{event.kwId}:{event.type}'
            append_event(sid, event, directory=directory)
        store._update_locked(sid, values, confirm_stage='stage1')
        write_feedback_md(sid, directory=directory)
    if n == 2:
        compute_coverage(sid, version=pinned_version)


class HumanAxes(BaseModel):
    axes: dict[str, str]


def coverage_status(saved):
    """Interpret abandoned background work without fetching or mutating on reads."""
    if saved.get('status') == 'loading':
        try:
            age = (datetime.fromisoformat(store.now()) -
                   datetime.fromisoformat(saved['startedAt'])).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = 121
        if age > 120:
            return {**saved, 'status': 'unavailable', 'error': {'kind': 'interrupted'}}
    return saved


def compute_coverage(sid, version=None, refresh=False):
    """Return cached coverage, or persist loading before dispatching a fetch."""
    created = False
    def begin(data):
        nonlocal created
        saved = coverage_status(data.get('coverage') or {})
        if saved and (not refresh or saved.get('status') == 'loading'):
            return {}
        created = True
        return {'coverage': _Replacement({**saved, 'status': 'loading', 'startedAt': store.now()})}
    data = mutate(sid, begin, version=version)
    value = coverage_status(data.get('coverage') or {})
    if created:
        # Capture the active version and context before returning to the caller.
        with store.locked(sid):
            store.assert_writable(sid, data.get('version'))
            directory = store.session_dir(sid)
        execute(lambda: _run_coverage(sid, data, directory))
    return value


def _run_coverage(sid, data, directory):
    version = data.get('version')
    started_at = data['coverage']['startedAt']
    approved = [k for k in _keywords(data) if k.status == 'approved']
    metadata = {'source': 'searchad', 'weighting': 'volume'}
    try:
        top = sorted(approved, key=lambda k: (k.volume or {}).get('monthly') or 0, reverse=True)[:4]
        bk = data.get('projectContext', {}).get('bk', '')
        hints = [h for h in [bk] + [k.kw for k in top] if h]
        metadata.update(seeds=len(hints), failedSeeds=0)
        try:
            human = naver_searchad.related_queries(hints)
        except Unconnected:
            # Stable round sorting retains generation/display order within a round.
            llm = sorted((k for k in approved if k.origin == 'llm'), key=lambda k: k.round)
            seeds = [bk] + [k.kw for k in llm[:20]]
            metadata = {'source': 'autocomplete', 'weighting': 'rank',
                        'seeds': len(seeds), 'failedSeeds': len(seeds)}
            result = naver_autocomplete.suggestions(seeds)
            human = result.queries
            metadata.update(seeds=result.total, failedSeeds=result.failed)
        human_axes = None
        if human:
            context_md = (directory / 'project_context.md').read_text(encoding='utf-8')
            classification = run_task(LLMTask(task='kw_axis_classify', sid=sid,
                instructions='각 검색어를 physical, psychological, behavioral 중 하나로 분류하세요. axes는 검색어→축 매핑입니다.\n'
                             + json.dumps(human, ensure_ascii=False),
                attachments=[Attachment(title='project_context.md', body=context_md)], output_schema=HumanAxes))
            if classification.ok:
                human_axes = classification.data.axes
        report = asdict(coverage.compute(human, [k for k in approved if k.origin == 'llm'],
                                         human_axes, weighting=metadata['weighting']))
        value = {'status': 'connected', 'humanQueries': human, 'humanAxes': human_axes, **report}
    except naver_autocomplete.AutocompleteUnavailable:
        value = {'status': 'unavailable', 'error': {'kind': 'autocomplete_unavailable'}}
    except Exception:
        value = {'status': 'failed', 'error': {'kind': 'request_failed'}}
    value.update(metadata)
    def finish(current):
        saved = current.get('coverage') or {}
        if saved.get('status') != 'loading' or saved.get('startedAt') != started_at:
            raise _JobSuperseded('작업이 변경되었습니다')
        keywords = current.get('keywords', [])
        ids = value.get('llm_only_ids', [])
        keywords = [{**k, 'badges': [b for b in k.get('badges', []) if b != 'llm_only'] + (['llm_only'] if k['id'] in ids else [])} for k in keywords]
        return {'coverage': _Replacement(value), 'keywords': keywords}
    try:
        mutate(sid, finish, version=version)
    except store.StoreError:
        # A superseding request/version owns its own result; never overwrite it.
        return
    except Exception:
        logger.error('Could not persist coverage for session %s', sid)


class Duplicate(store.StoreError):
    def __init__(self, keyword_id):
        super().__init__('이미 있는 키워드입니다')
        self.duplicateOf = keyword_id


def add_manual(sid, kw, axis, sub, origin='manual', version=None):
    with store.locked(sid):
        data = store.assert_writable(sid, version)
        version = data.get('version')
    if not norm_key(kw) or not is_valid(axis, sub):
        raise store.StoreError('키워드와 분류를 확인하세요', 422, 'validation')
    keyword = volumes([Keyword(id='manual-' + uuid4().hex, kw=''.join(kw.split()), axis=axis,
                               sub=sub, round=1, origin=origin, status='approved')])[0]
    def patch(data):
        duplicate = next((k for k in _all_keywords(data) if norm_key(k.kw) == norm_key(kw)), None)
        if duplicate:
            raise Duplicate(duplicate.id)
        keyword.round = max((int(n) for n in data.get('keywordRounds', {})), default=1)
        return {'keywords': data.get('keywords', []) + [keyword.model_dump()]}
    with store.locked(sid):
        data = store.assert_writable(sid, version)
        directory = store.session_dir(sid)
        store._update_locked(sid, patch(data), confirm_stage='stage1')
        append_event(sid, KeywordEvent(ts=store.now(), round=keyword.round, type='add', kwId=keyword.id, kw=keyword.kw), directory=directory)
        write_feedback_md(sid, directory=directory)
    return keyword


class SuggestedWord(BaseModel):
    word: str
    type: str


class Suggestions(BaseModel):
    words: list[SuggestedWord] = Field(default_factory=list)


def suggest_words(sid, axis, sub, version=None):
    with store.locked(sid):
        data = store.assert_writable(sid, version)
        directory = store.session_dir(sid)
    if not is_valid(axis, sub):
        raise store.StoreError('분류를 확인하세요', 422, 'validation')
    context_md = (directory / 'project_context.md').read_text(encoding='utf-8')
    task = LLMTask(task='kw_suggest_words', sid=sid, max_tokens=2000,
        instructions=f'{axis}/{sub}의 경험을 나타내는 형용사와 동사를 10~15개 제안하세요. 1~2단어. '
                     f'기존 단어 제외: {json.dumps([k.kw for k in _all_keywords(data)], ensure_ascii=False)}',
        attachments=[Attachment(title='project_context.md', body=context_md)], output_schema=Suggestions)
    result = run_task(task)
    if not result.ok:
        raise store.StoreError(result.error.message, 502, result.error.kind)
    return {'status': 'ok', **result.data.model_dump()}
