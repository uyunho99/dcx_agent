"""Validated text edits and append-only reverts for stage-eight insights."""
import json
from pathlib import Path

from app.context import store as sessions
from app.known import store as known
from app.persona.source import Source
from app.llm.base import Attachment, LLMTask
from app.persona import concepts, insights, prescribe
from app.persona.insight_pipeline import serialized, publish_status
from app.persona.package import load_package
from app.persona.params import INSIGHT_RANGE
from app.persona.store import PersonaStore
from app.vectors.embedder import get_embedder

FAILURE_COPY = '요청을 반영하지 못했습니다. 다르게 말해 주세요.'


def _target(target):
    if target == 'insights':
        return 'insights', None
    if isinstance(target, str) and target.startswith('concept:') and target[8:]:
        return 'concepts', target[8:]
    raise ValueError('Invalid chat target')


def _concept_draft(item):
    return dict(persona_profile=item['persona_profile']['text'],
        pain_points=[p['evidence_number'] for p in item['pain_points']],
        journey=[{key: row[key] for key in concepts.JourneyRow.model_fields} for row in item['journey']])


def edit(sid, version, target: str, message: str, *, run_task=None) -> dict:
    with serialized(sid):
        source = Source(sid, version)
        source.check()
        store = PersonaStore.open(sid, version)
        store.guard = source.check
        if run_task is None:
            from app.persona.pipeline import _Calls
            run_task = _Calls(store.path, lambda: None).run_task
        try:
            name, insight_id = _target(target)
            current = store.read(name)
            if not current or not isinstance(message, str) or not message.strip():
                raise ValueError('Missing input')
            package = load_package(sid, version)
            payload = dict(current=current, message=message, target=target)
            schema = insights.DeriveOut
            if insight_id is not None:
                item = next(row for row in current['items'] if row['id'] == insight_id)
                insight = next(row for row in store.read('insights')['items'] if row['id'] == insight_id)
                contexts, _, refs, owners = concepts._inputs(package, insight)
                payload.update(editable=_concept_draft(item), insight=insight,
                    evidence={n: ref.model_dump() for n, ref in refs.items()})
                schema = concepts.ConceptOut
            task = LLMTask(task='insight.edit', sid=sid,
                instructions=Path(__file__).with_name('prompts').joinpath('edit.v1.md').read_text(encoding='utf-8'),
                attachments=[Attachment(title='현재 판과 수정 요청', body=json.dumps(payload, ensure_ascii=False))],
                output_schema=schema)
            result = run_task(task)
            if not result.ok or not isinstance(result.data, schema):
                raise ValueError('Invalid edit schema')
            draft = result.data.model_dump()
            if name == 'insights':
                items = draft['items']
                available = {c.context_id for b in package.personas for c in b.context_evidence}
                if (not INSIGHT_RANGE[0] <= len(items) <= INSIGHT_RANGE[1]
                        or len({row['id'] for row in items}) != len(items)
                        or any(not set(row['context_ids']) <= available or
                               len(set(row['context_ids'])) != len(row['context_ids']) for row in items)):
                    raise ValueError('Invalid insight references')
                embedder = known.session_embedder(sid, sessions.assert_writable(sid, version), get_embedder)
                insights.recompute(sid, version, items, package=package, embedder=embedder)
            else:
                if (any(n not in refs for n in draft['pain_points']) or
                        any(row['context_id'] not in insight['context_ids'] for row in draft['journey'])):
                    raise ValueError('Invalid concept references')
                concept = concepts._hydrate(draft, insight_id,
                    concepts._basis(sid, version, contexts), refs, owners)
                project = sessions.load_session(sid).get('projectContext', {})
                checked = prescribe.check_constraints(sid, concept, project, run_task=run_task)
                violations = [row for row in checked if row['verdict'] == 'violates']
                concept.update(insight_revision=store.read('insights')['revision'],
                               context_ids=list(insight['context_ids']), outdated=False,
                               constraint_check=checked, blocked=bool(violations),
                               represcribed=False, regenerated=False)
                if violations:
                    concept['message'] = '\n'.join(
                        f"사내 제약 '{row['constraint']}'를 지키는 처방을 만들지 못했습니다." for row in violations)
                items = [concept if row['id'] == insight_id else row for row in current['items']]
            source.check()
            revision = store.new_revision(name, items, by='chat', message=message)
            publish_status(sid, version, 'done', before_publish=source.check)
            outcome = {'ok': True, 'revision': revision}
        except sessions.StoreError:
            raise
        except Exception:
            outcome = {'ok': False, 'message': FAILURE_COPY}
        store.append_chat(dict(at=sessions.now(), target=target, message=message,
                               **{k: v for k, v in outcome.items() if k != 'message'},
                               **({'reason': FAILURE_COPY} if not outcome['ok'] else {})))
        return outcome


def revert(sid, version, target: str, revision: int) -> dict:
    with serialized(sid):
        source = Source(sid, version)
        source.check()
        store = PersonaStore.open(sid, version)
        store.guard = source.check
        name, insight_id = _target(target)
        if insight_id is None:
            number = store.revert(name, revision)
        else:
            current = store.read(name) or {}
            snapshot = next((h for h in current.get('history', []) if h['revision'] == revision), {})
            item = next((row for row in snapshot.get('items', []) if row['id'] == insight_id), None)
            if item is None:
                raise sessions.StoreError('Revision not found', 404, 'not_found')
            items = [row for row in current.get('items', []) if row['id'] != insight_id]
            number = store.new_revision(name, [*items, item], by='revert', message=None)
        publish_status(sid, version, 'done', before_publish=source.check)
        return {'revision': number}
