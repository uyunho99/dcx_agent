"""Persona-scoped query generation with one corrective attempt (AC-06).

The caller persists returned rows in its version/run-scoped EvidenceStore and
records ``query_gen_fail`` for every Context ID in ``failed``. No active-version
writes happen here. Persona dimensions are desire_check_1, desire_check_2 and
artifact so all three sentences survive the store's (owner, dim) primary key.
"""
from dataclasses import dataclass
from pathlib import Path
import re

from pydantic import BaseModel

from app.context import store as sessions
from app.evidence.params import FORBIDDEN, QUERY_DIMS
from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.segment.stopwords import filter_words

_FORBIDDEN_RE = re.compile(FORBIDDEN)


class PersonaQueryOut(BaseModel):
    persona_query: dict
    context_queries: dict[str, dict[str, str]]
    anchor_context_ids: list[str]


@dataclass
class QueryResult:
    persona_rows: list[dict]
    context_rows: dict[str, list[dict]]
    failed: list[str]
    calls: int


def _text_violations(text, label):
    if not isinstance(text, str) or not text.strip():
        return [f'{label}: 비어 있지 않은 문장이 필요합니다']
    match = _FORBIDDEN_RE.search(text)
    return [f'{label}: 금지어 {match.group()}'] if match else []


def _violations(out, context_ids):
    """Pair messages with affected IDs; None means a Persona-wide violation."""
    issues = []
    expected = set(context_ids)
    anchors = set(out.anchor_context_ids)
    for cid in context_ids:
        if cid not in anchors:
            issues.append((cid, f'anchor_context_ids: {cid} 누락'))
    extra = anchors - expected
    if extra:
        issues.append((None, f'anchor_context_ids: 알 수 없는 ID {sorted(extra)}'))
    extra = set(out.context_queries) - expected
    if extra:
        issues.append((None, f'context_queries: 알 수 없는 ID {sorted(extra)}'))
    for cid in context_ids:
        queries = out.context_queries.get(cid, {})
        if set(queries) != set(QUERY_DIMS):
            issues.append((cid, f'{cid}: 8키 필요; 누락 {sorted(set(QUERY_DIMS) - set(queries))}; '
                           f'추가 {sorted(set(queries) - set(QUERY_DIMS))}'))
        for dim in QUERY_DIMS:
            issues.extend((cid, message) for message in
                          _text_violations(queries.get(dim), f'{cid}.{dim}'))
    if set(out.persona_query) != {'desire_check', 'artifact'}:
        issues.append((None, 'persona_query: desire_check, artifact 키가 필요합니다'))
    for kind, count in (('desire_check', 2), ('artifact', 1)):
        sentences = out.persona_query.get(kind)
        if not isinstance(sentences, list) or len(sentences) != count:
            issues.append((None, f'persona_query.{kind}: {count}문장 필요'))
        if isinstance(sentences, list):
            for index, sentence in enumerate(sentences, 1):
                issues.extend((None, message) for message in
                              _text_violations(sentence, f'persona_query.{kind}[{index}]'))
    return issues


def validate_queries(out: PersonaQueryOut, context_ids: list[str]) -> list[str]:
    """Check anchor union, eight nonempty dimensions and forbidden wording."""
    return [message for _, message in _violations(out, context_ids)]


def _input_body(persona, contexts, one_liner, keywords, bk):
    artifact_words = filter_words(persona.get('keywords') or [], bk)
    # Segment rows normally expose Context keywords rather than Persona keywords.
    if not artifact_words:
        artifact_words = list(dict.fromkeys(word for words in keywords.values() for word in words))
    goals = persona.get('goals') or persona.get('goal') or []
    if isinstance(goals, str):
        goals = [goals]
    lines = [one_liner, f"Persona 이름: {persona.get('name') or ''}",
             f"Desire: {persona.get('desire') or ''}", f"Goal: {', '.join(goals)}",
             f"Artifact 후보(키워드): {', '.join(artifact_words)}"]
    for context in contexts:
        cid = context['context_id']
        lines.append(f"{cid} · {context.get('action') or ''} · 주된 제약: "
                     f"{context.get('dominant_constraint') or ''} · 키워드: {', '.join(keywords[cid])}")
    return '\n'.join(lines)


def generate_queries(sid: str, persona: dict, contexts: list[dict], one_liner: str,
                     *, run_task=registry.run_task) -> QueryResult:
    """Generate rows without mutating inputs; at most two run_task invocations.

    Missing anchors or invalid Context text affect only the corresponding
    Context. Unusable responses and Persona-wide violations affect all Contexts.
    Fallback uses up to three surviving keywords (never pads with stopwords).
    """
    context_ids = [context['context_id'] for context in contexts]
    session = sessions.load_session(sid) or {}
    bk = (session.get('projectContext') or {}).get('bk')
    keywords = {context['context_id']: filter_words(context.get('keywords') or [], bk)
                for context in contexts}
    prompt = Path(__file__).with_name('prompts').joinpath('queries.v1.md').read_text(encoding='utf-8')
    body = _input_body(persona, contexts, one_liner, keywords, bk)
    issues = []
    out = None
    for calls in (1, 2):
        instructions = prompt
        if issues:
            instructions += '\n\n이전 응답의 위반 목록을 모두 수정해 전체 JSON을 다시 작성하세요:\n'
            instructions += '\n'.join(f'- {message}' for _, message in issues)
        task = LLMTask(task='evidence.queries', sid=sid, instructions=instructions,
                       attachments=[Attachment(title='프로젝트와 검색 문장 입력', body=body)],
                       output_schema=PersonaQueryOut)
        out = None
        try:
            result = run_task(task)
            if result.ok and isinstance(result.data, PersonaQueryOut):
                out = result.data
                issues = _violations(out, context_ids)
            else:
                kind = result.error.kind if result.error else 'schema'
                issues = [(None, f'응답 검증 실패: {kind}; 출력 스키마에 맞는 JSON이 필요합니다')]
        except Exception:
            issues = [(None, '응답 생성 실패: backend; 출력 스키마에 맞는 JSON이 필요합니다')]
        if not issues:
            break

    failed_ids = set(context_ids) if any(cid is None for cid, _ in issues) else {cid for cid, _ in issues}
    origin = 'llm' if calls == 1 else 'regen'
    context_rows = {}
    for context in contexts:
        cid = context['context_id']
        if cid in failed_ids:
            text = ' '.join([context.get('name') or cid, *keywords[cid][:3]])
            context_rows[cid] = [dict(dim=dim, text=text, origin='fallback') for dim in QUERY_DIMS]
        else:
            context_rows[cid] = [dict(dim=dim, text=out.context_queries[cid][dim].strip(), origin=origin)
                                 for dim in QUERY_DIMS]
    persona_rows = []
    if out is not None and not any(cid is None for cid, _ in issues):
        persona_rows = [dict(dim=f'desire_check_{index}', text=text.strip(), origin=origin)
                        for index, text in enumerate(out.persona_query['desire_check'], 1)]
        persona_rows.append(dict(dim='artifact', text=out.persona_query['artifact'][0].strip(), origin=origin))
    return QueryResult(persona_rows, context_rows, [cid for cid in context_ids if cid in failed_ids], calls)
