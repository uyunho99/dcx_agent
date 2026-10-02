"""Persona-unit checkpoints and publication for stage eight.

``args`` accepts fresh/personas and an optional public ``run`` for retries.
``assert_run`` is also available to the API before it queues a retry. Public run
IDs rotate on resume, independently of the work supervisor's run ID. Store
mutations own their locks; never call them while holding sessions.locked.
"""
from collections import Counter
from contextlib import closing
import hashlib
import json
import logging
import shutil
import sqlite3
import uuid

from app.context import store as sessions
from app.context.stale import clear_stale
from app.context.versions import version_dir
from app.llm import registry
from app.llm.base import failure
from app.persona import params
from app.persona.cards import generate_card
from app.persona.grade import grade_card
from app.persona.opportunity import build_map
from app.persona.package import PackageMissing, evidence_ready, evidence_index, load_package
from app.persona.prescribe import prescribe, scope_check
from app.persona.store import PersonaStore
from app.persona.tree import build_tree
from app.segment.pipeline import LLM_REASON

CARD_REASON = '이 페르소나 카드를 만들지 못했습니다.'


class _LLMUnavailable(BaseException):
    """The shared worker maps non-Exception exits to interrupted."""


class _Stopped(BaseException):
    """Escape the card/prescription catch-all at cooperative boundaries."""


class _Stale(BaseException):
    """Stop publishing when source inputs change during generation."""


def _session(sid, version, values, *, stale=False, done=False):
    with sessions.locked(sid):
        sessions.assert_writable(sid, version)
        path = version_dir(sid, version) / 'session.json'
        data = sessions.read_json(path)
        data.setdefault('persona', {}).update(values)
        completion = data.setdefault('completion', {})
        completion.pop('personaDone', None)
        if stale:
            data.setdefault('stale', {})['stage8'] = 'Persona source changed'
            data.setdefault('insight', {})['status'] = 'stale'
            completion.pop('insightDone', None)
        if done:
            completion['personaDone'] = True
        sessions.write_json(path, data)
        if done:
            clear_stale(sid, version, 'stage8', already_locked=True)


def assert_run(sid, version, run_id):
    """Read-only 409 guard; safe to call under the router's session lock."""
    data = sessions.read_json(version_dir(sid, version) / 'session.json') or {}
    cards = PersonaStore.open(sid, version).read('cards') or {}
    if not run_id or data.get('persona', {}).get('run') != run_id or cards.get('run') != run_id:
        raise sessions.StoreError('이전 실행의 요청입니다. 새로고침한 뒤 다시 시도하세요.', 409, 'stale_run')


def _digest(package):
    return hashlib.sha256(json.dumps(package.model_dump(mode='json', by_alias=True),
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _confirmed_matches(sid, version, package):
    """Read confirmed identity without creating or migrating a segment store."""
    path = version_dir(sid, version) / 'segment/segment.sqlite'
    if not path.is_file():
        return False
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        personas = {r['persona_id']: dict(r) for r in db.execute('SELECT * FROM personas')}
        contexts = {r['context_id']: dict(r) for r in db.execute('SELECT * FROM contexts')}
    if set(personas) != {b.persona_evidence.persona_id for b in package.personas}:
        return False
    if set(contexts) != {c.context_id for b in package.personas for c in b.context_evidence}:
        return False
    for block in package.personas:
        p = block.persona_evidence
        row = personas[p.persona_id]
        if (not row['confirmed_at'] or row['cluster_id'] != p.cluster_id
                or row['name'] != p.persona_name or row['desire'] != p.desire
                or json.loads(row['goals_json'] or '[]') != p.goal):
            return False
        for c in block.context_evidence:
            row = contexts[c.context_id]
            if (not row['confirmed_at'] or row['persona_id'] != p.persona_id
                    or row['name'] != c.context_name or row['action'] != c.action):
                return False
    return True


def mark_stale_if_changed(sid, version):
    """Reconcile upstream edits for the API; call outside the session lock."""
    cards = PersonaStore.open(sid, version).read('cards')
    if cards is None:
        return False
    try:
        package = load_package(sid, version)
        changed = (not evidence_ready(sid, version)
                   or cards.get('package_run') != getattr(package, 'run', None)
                   or cards.get('package_hash', _digest(package)) != _digest(package)
                   or not _confirmed_matches(sid, version, package))
    except PackageMissing:
        changed = True
    if changed:
        _session(sid, version, {'status': 'stale'}, stale=True)
    return changed


class _Calls:
    retries_schema = True

    def __init__(self, root, pulse):
        self.root, self.pulse = root, pulse
        self.counts = sessions.read_json(root / 'llm_calls.json') or {}
        self.results = []

    def run_task(self, task):
        self.pulse()
        name = task.task.split('.')[-1]
        try:
            result = registry.run_task(task)
        except (TimeoutError, ConnectionError):
            result = failure('backend', 'Provider unavailable')
        self.counts[name] = self.counts.get(name, 0) + getattr(result, 'attempts', 1)
        # root is version-local: all accounting writes obey version immutability.
        store = PersonaStore(task.sid, self.root, self.root.parent.name)
        store.write_aux('llm_calls', self.counts)
        self.results.append(None if result.ok else result.error.kind if result.error else 'unknown')
        return result


def _report(store, rows, opportunity, calls, run_id):
    done = [row for row in rows.values() if row['status'] == 'done']
    grades = Counter()
    nulls = 0

    def null_count(value):
        if isinstance(value, dict):
            return sum(null_count(v) for v in value.values())
        if isinstance(value, list):
            return sum(null_count(v) for v in value)
        return int(value is None)

    for row in done:
        for fields in row['grades'].values():
            grades.update(fields.values())
        grades.update(row['summary'].values())
        # Count displayed card properties, excluding metadata/source quote offsets.
        card = row['card']
        nulls += sum(null_count(card.get(key)) for key in
                     ('intent', 'usage_context', 'jtbd', 'journey', 'sensitivity', 'values', 'decision_style'))
        nulls += sum(null_count(c.get(key)) for c in card['contexts'] for key in ('state', 'emotion', 'barrier'))
    insights = store.read('insights') or {}
    concepts = store.read('concepts') or {}
    insight_items = insights.get('items', [])
    odi = [item['odi'] for item in insight_items if isinstance(item.get('odi'), (int, float))]
    mean = sum(odi) / len(odi) if odi else 0
    above_mean = sum(value >= mean for value in odi)
    return dict(run=run_id, at=sessions.now(), cards=len(done),
        failed=sum(row['status'] == 'failed' for row in rows.values()),
        grades={key: grades[key] for key in ('observed', 'inferred', 'speculated')},
        null_attributes=nulls,
        constraint_violations=sum(c['verdict'] == 'violates' for row in done for c in row['constraint']),
        represcribed=sum(bool(row['prescription']['represcribed']) for row in done),
        blocked=sum(bool(row['prescription']['blocked']) for row in done),
        future=sum(row['scope']['verdict'] == 'outside' for row in done),
        zones={z: sum(p['zone'] == z for p in opportunity['points']) for z in 'ABCDEF'},
        stars=sum(bool(p['star']) for p in opportunity['points']),
        insights=len(insights.get('items', [])), above_mean=above_mean,
        concepts=len(concepts.get('items', [])),
        chat_revisions=sum(h.get('by') == 'chat' for doc in (insights, concepts) for h in doc.get('history', [])),
        llm_calls=calls.counts, params={k: v for k, v in vars(params).items() if k.isupper()},
        provisional=list(params.PROVISIONAL))


def refresh_report(sid, version):
    """Refresh downstream totals after a durable insight publication."""
    store = PersonaStore.open(sid, version)
    report = store.read('stage_8')
    if report is None:
        return
    cards = store.read('cards') or {}
    store.write('stage_8', _report(store, cards.get('personas', {}),
        store.read('map'), _Calls(store.path, lambda: None), report['run']))


def run(context):
    from app.persona.insight_pipeline import serialized
    # Announce a reset before waiting on inference, so a pending chat cannot
    # report success against the generation about to be removed.
    if context.args.get('fresh'):
        with sessions.locked(context.sid):
            sessions.assert_writable(context.sid, context.version)
            path = version_dir(context.sid, context.version) / 'session.json'
            data = sessions.read_json(path)
            data.setdefault('persona', {}).update(reset_epoch=str(uuid.uuid4()), status='running')
            data.setdefault('completion', {}).pop('personaDone', None)
            sessions.write_json(path, data)
    with serialized(context.sid):
        return _run(context)


def _run(context):
    sid, version = context.sid, context.version
    root = version_dir(sid, version) / 'persona'
    with sessions.locked(sid):
        sessions.assert_writable(sid, version)
        if 'run' in context.args:
            assert_run(sid, version, context.args['run'])
    package = load_package(sid, version)
    if not evidence_ready(sid, version) or not _confirmed_matches(sid, version, package):
        _session(sid, version, {'status': 'stale'}, stale=True)
        return
    if not context.args.get('fresh') and mark_stale_if_changed(sid, version):
        return
    store = PersonaStore.open(sid, version)
    ids = [b.persona_evidence.persona_id for b in package.personas]
    selected = None if context.args.get('fresh') else context.args.get('personas')
    if selected is not None and (not isinstance(selected, list) or not set(selected) <= set(ids)):
        raise sessions.StoreError('Unknown Persona', 400, 'validation')
    if context.args.get('fresh'):
        with sessions.locked(sid):
            sessions.assert_writable(sid, version)
            shutil.rmtree(root, ignore_errors=True)
            path = version_dir(sid, version) / 'session.json'
            data = sessions.read_json(path)
            data.pop('insight', None)
            data.get('completion', {}).pop('insightDone', None)
            sessions.write_json(path, data)
    cards = store.read('cards') or {'personas': {}}
    rows = cards['personas']
    for pid in ids:
        rows.setdefault(pid, {'status': 'pending'})
    # Durable done cards are the unit checkpoint, including a crash between the
    # cards replacement and checkpoint replacement. Failed units remain retryable.
    done = [pid for pid in ids if rows.get(pid, {}).get('status') == 'done']
    run_id = str(uuid.uuid4())
    signature = _digest(package)
    cards.update(run=run_id, package_run=getattr(package, 'run', None), package_hash=signature)
    checkpoint = dict(run=run_id, done=done, package_run=cards['package_run'], package_hash=signature)
    store.write('cards', cards)
    store.write_aux('checkpoint', checkpoint)
    _session(sid, version, dict(status='running', run=run_id, progress=0, reason=None))
    project = sessions.read_json(version_dir(sid, version) / 'session.json').get('projectContext', {})
    active = None

    def pulse():
        if context.should_stop():
            raise _Stopped()
        progress = len(checkpoint['done']) / max(len(ids), 1)
        detail = dict(persona=active, personas=len(ids), completed=len(checkpoint['done']))
        context.heartbeat(progress, detail)
        if context.should_stop():
            raise _Stopped()
        _session(sid, version, dict(progress=progress, detail=detail))

    def check_source():
        try:
            current = load_package(sid, version)
            valid = (evidence_ready(sid, version) and _digest(current) == signature
                     and _confirmed_matches(sid, version, current))
        except PackageMissing:
            valid = False
        if not valid:
            _session(sid, version, {'status': 'stale'}, stale=True)
            raise _Stale()

    calls = _Calls(root, pulse)
    try:
        for block in package.personas:
            active = block.persona_evidence.persona_id
            pulse()
            if active in done or (selected is not None and active not in selected):
                continue
            check_source()
            try:
                result = generate_card(sid, block, run_task=calls.run_task)
                if result.status != 'done':
                    row = dict(status='failed', error=CARD_REASON)
                else:
                    card = result.card
                    grades = grade_card(card, evidence_index(block))
                    prescription = prescribe(sid, card, project, run_task=calls.run_task)
                    scope = scope_check(sid, card, project, run_task=calls.run_task)
                    row = dict(status='done', card=card, **grades, prescription=prescription,
                               constraint=prescription['constraint'], scope=scope)
            except Exception:
                row = dict(status='failed', error=CARD_REASON)
            pulse()
            check_source()
            rows[active] = row
            store.write('cards', cards)
            if row['status'] == 'done':
                checkpoint['done'].append(active)
            store.write_aux('checkpoint', checkpoint)
        if calls.results and all(kind in ('backend', 'timeout') for kind in calls.results):
            _session(sid, version, dict(status='interrupted', reason=LLM_REASON))
            raise _LLMUnavailable()
        pulse()
        check_source()
        opportunity = build_map(package)
        store.write('map', opportunity)
        store.write('tree', build_tree(package, project.get('bk', '')))
        report = _report(store, rows, opportunity, calls, run_id)
        store.write('stage_8', report)
        check_source()
        complete = bool(ids) and all(row['status'] in ('done', 'failed') for row in rows.values())
        progress = 1 if complete else len(checkpoint['done']) / max(len(ids), 1)
        _session(sid, version, dict(status='done' if complete else 'interrupted',
            progress=progress, savedAt=report['at']), done=complete)
        return report
    except _Stopped:
        _session(sid, version, {'status': 'interrupted'})
    except _Stale:
        return
    except Exception:
        _session(sid, version, {'status': 'failed', 'reason': CARD_REASON})
        logging.getLogger(__name__).exception('Could not publish Persona run')
        raise
