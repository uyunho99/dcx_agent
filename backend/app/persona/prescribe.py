"""Stage-eight prescription, bounded constraint repair, and isolated scope check.

Call failures raise PrescriptionError for the caller to mark the Persona failed;
only a completed second constraint check can produce a blocked prescription.
The scope verdict ``outside`` is the downstream header's FUTURE condition.
"""
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm import registry
from app.llm.base import Attachment, LLMTask


Text = Annotated[str, Field(min_length=1)]


class _Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class PrescriptionOut(_Output):
    direction: Text
    target_metric: Text
    contribution: Text
    journey_hypothesis: Text


class ConstraintVerdict(_Output):
    constraint: Text
    verdict: Literal['ok', 'violates', 'review']
    reason: Text


class ConstraintCheckOut(_Output):
    constraints: list[ConstraintVerdict]


class ScopeOut(_Output):
    verdict: Literal['in', 'outside']
    reason: Text


class PrescriptionError(RuntimeError):
    """A prescription/scope call failed or did not check the requested constraints."""


def _mapping(value):
    return value.model_dump(mode='json') if isinstance(value, BaseModel) else value


def _call(sid, name, schema, payload, run_task):
    prompt = (Path(__file__).with_name('prompts') / f'{name}.v1.md').read_text(encoding='utf-8')
    task = LLMTask(task=f'persona.{name}', sid=sid, instructions=prompt,
                   attachments=[Attachment(title='판단 입력', body=json.dumps(payload, ensure_ascii=False))],
                   output_schema=schema)
    try:
        result = run_task(task)
    except Exception as exc:
        raise PrescriptionError(f'{task.task}: backend failed') from exc
    if not result.ok or not isinstance(result.data, schema):
        kind = result.error.kind if result.error else 'schema'
        raise PrescriptionError(f'{task.task}: {kind}')
    return result.data.model_dump()


def prescribe(sid, card_summary, project_context, *, run_task=None) -> dict:
    """Check each draft separately; repair once only when a verdict violates.

    ``constraint`` contains final verdicts/reasons. A blocked result additionally
    carries ``message`` with the section-nine copy for each remaining violation.
    Schema retry belongs to the LLM registry, not this business retry loop.
    """
    run_task = registry.run_task if run_task is None else run_task
    context = _mapping(project_context)
    constraints = list(dict.fromkeys(context.get('constraints', [])))
    payload = dict(card_summary=_mapping(card_summary),
                   analysisGoal=context.get('analysisGoal'),
                   keyMetrics=context.get('keyMetrics', []), constraints=constraints)
    for attempt in range(2):
        draft = _call(sid, 'prescribe', PrescriptionOut, payload, run_task)
        checked = _call(sid, 'constraint_check', ConstraintCheckOut,
                        dict(prescription=draft, constraints=constraints), run_task)['constraints']
        if (len(checked) != len(constraints)
                or {row['constraint'] for row in checked} != set(constraints)):
            raise PrescriptionError('persona.constraint_check: incomplete or unknown constraints')
        violations = [row for row in checked if row['verdict'] == 'violates']
        if violations and attempt == 0:
            payload = {**payload, 'previous_prescription': draft, 'violations': violations}
            continue
        result = dict(draft, constraint=checked, blocked=bool(violations), represcribed=bool(attempt))
        if violations:
            result['message'] = '\n'.join(
                f"사내 제약 '{row['constraint']}'를 지키는 처방을 만들지 못했습니다."
                for row in violations)
        return result


def scope_check(sid, card_summary, project_context, *, run_task=None) -> dict:
    """Return in/outside and reason; outside maps to FUTURE in the header."""
    context = _mapping(project_context)
    payload = {'card_summary': _mapping(card_summary),
               **{key: context.get(key) for key in ('targetScope', 'productCategory', 'positioning')}}
    return _call(sid, 'scope', ScopeOut, payload,
                 registry.run_task if run_task is None else run_task)
