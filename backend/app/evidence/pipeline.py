"""Resumable evidence orchestration with a single SQLite writer.

Context computations run in a bounded pool. Their tag requests are marshalled
back to the worker main thread, where T7 runs its bounded LLM batches and writes
caches. A shared semaphore caps all provider calls, including novelty. Only
fully published Contexts are checkpoints; every invocation rotates the public
run generation without discarding successful Contexts on resume.
"""
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import closing, nullcontext
import hashlib
import json
from queue import Empty, Queue
import sqlite3
from threading import BoundedSemaphore, Event, Lock
import uuid

from app.config import settings
from app.context import store as sessions
from app.context.stale import clear_stale
from app.context.versions import version_dir
from app.evidence import assemble, candidates, novelty, params, queries, tabs, tagging, generation
from app.evidence.cache import TagCache, prompt_version, known_key, known_snapshot
from app.evidence.store import EvidenceStore
from app.known import store as known_store
from app.llm import registry
from app.llm.base import failure
from app.model.infer import prepared_root
from app.segment import dims
from app.segment.pipeline import LLM_REASON, _LLMUnavailable, _Stopped
from app.segment.store import SegmentStore
from app.vectors.store import VectorStore


def _session(sid, version, values, *, already_locked=False):
    with nullcontext() if already_locked else sessions.locked(sid):
        sessions.assert_writable(sid, version)
        path = version_dir(sid, version) / 'session.json'
        data = sessions.read_json(path)
        data.setdefault('evidence', {}).update(values)
        data.setdefault('completion', {}).pop('evidenceDone', None)
        if values.get('status') == 'done':
            data.get('stale', {}).pop('stage7', None)
        sessions.write_json(path, data)


def _load(sid, version):
    session = sessions.read_json(version_dir(sid, version) / 'session.json')
    seg = SegmentStore.open(sid, version)
    root = prepared_root(sid, session)
    if root is None:
        raise sessions.StoreError('Prepared documents required', 409, 'not_ready')
    rows = assemble._documents(seg)
    docs = {d['doc_id']: d for d in rows}
    for doc_id, original in assemble._load_docs(root, set(docs)).items():
        docs[doc_id].update(original)
    if session.get('training', {}).get('exportRef'):
        from app.known.filter import read_export
        for row in read_export(sid, session):
            if row['doc_id'] in docs:
                docs[row['doc_id']]['tagProbs'] = row.get('tagProbs')
    source = VectorStore(root)
    ids, values = source.get(list(docs))
    vectors = dict(zip(ids, values))
    cache = TagCache.open(sid, session['prep']['derivedRef']['prepKey'], prompt_version('tag'))
    path = cache.path.parent / f'dims-{hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()}.sqlite'
    dims_by_id = {}
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            dims_by_id = {i: json.loads(value) for i, value in db.execute('SELECT doc_id, context_dims FROM dims') if i in docs}
    return dict(session=session, seg=seg, docs=docs, source=source, vectors=vectors,
                cache=cache, dims=dims_by_id)


def _known(sid, version):
    return [item.model_dump() for item in known_store.list_known(sid, version)]


def _project(cache, ids, known):
    tags = cache.get_tags(ids)
    pairs = cache.get_known(ids, [known_key(i) for i in known if i['type'] == 'statement'])
    for doc_id, tag in tags.items():
        tag['known_match'] = next((i['id'] for i in known if pairs.get((doc_id, known_key(i)))), 'none')
    return tags


def _selected(rows):
    return [dict(doc_id=r['doc_id'], rank=r['rank'], role='support', quality=r.get('quality'),
                 novelty=r.get('novelty'), novelty_reason=r.get('novelty_reason')) for r in rows]


class _Calls:
    """Thread-safe accounting; publication and heartbeat stay on the caller."""
    def __init__(self, concurrency, events):
        self.limit = BoundedSemaphore(concurrency)
        self.lock = Lock()
        self.events = events
        self.counts = Counter()

    def step(self, owner, name):
        results = []

        def call(task):
            with self.limit:
                with self.lock:
                    self.counts[task.task] += 1
                self.events.put(('pulse', dict(context=owner, step=name)))
                try:
                    result = registry.run_task(task)
                except (TimeoutError, ConnectionError):
                    result = failure('backend', 'Provider unavailable')
                with self.lock:
                    results.append(None if result.ok else result.error.kind if result.error else 'unknown')
                return result

        def check():
            if results and all(kind in ('backend', 'timeout') for kind in results):
                raise _LLMUnavailable()
        return call, check


def _refresh_cached(sid, version, ev, source, row, known):
    cid = row['context_id']
    pool = ev.candidates(cid)
    tags = _project(source['cache'], [r['doc_id'] for r in pool], known)
    result = tabs.refresh_new(cid, pool, tags, source['vectors'], source['docs'], known_items=known)
    # Retain previously judged novelty where membership survives, no new calls.
    previous = {r['doc_id']: r for r in ev.selected(cid, 'new')}
    selected = [dict(r, novelty=previous.get(r['doc_id'], {}).get('novelty'),
                     novelty_reason=previous.get(r['doc_id'], {}).get('novelty_reason')) for r in result.rows]
    ev.write_selected(cid, 'new', _selected(selected))
    levels = {r['doc_id']: r for r in selected}
    ev.write_selected(cid, 'all', _selected([dict(r, novelty=levels.get(r['doc_id'], {}).get('novelty'),
        novelty_reason=levels.get(r['doc_id'], {}).get('novelty_reason')) for r in ev.selected(cid, 'all')]))
    ev.write_candidates(cid, [dict(r, known_excluded=result.exclusions.get(r['doc_id'])) for r in pool])
    pairs = source['cache'].get_known(tags, [known_key(i) for i in known if i['type'] == 'statement'])
    incomplete = any((doc_id, known_key(i)) not in pairs for doc_id in tags for i in known if i['type'] == 'statement')
    counts = {**(row.get('counts') or {}), 'knownChanged': incomplete, 'knownSnapshot': known_snapshot(known),
              'knownIds': [i['id'] for i in known], 'excludedKnown': result.excluded_known}
    ev.set_context(cid, row['persona_id'], row['status'], counts=counts)
    return result


def _assemble(sid, version):
    package = assemble.assemble(sid, version)
    root = version_dir(sid, version) / 'evidence'
    report = sessions.read_json(root / 'stage_7.json')
    call_counts = sessions.read_json(root / 'llm_calls.json') or {}
    report['llm_calls'] = sum(call_counts.values())
    report['tag_calls'] = call_counts.get('evidence.tag', 0)
    report.update((sessions.read_json(root / 'checkpoint.json') or {}).get('tagging', {}))
    sessions.write_json(root / 'stage_7.json', report)
    return package


def _finish(sid, version, ev, run_id):
    rows = ev.contexts()
    done = sum(r['status'] in ('done', 'skipped') for r in rows)
    state = 'done' if done == len(rows) else 'partial'
    with sessions.locked(sid):
        generation.check(sid, version, ev, run_id)
        _assemble(sid, version)
        _session(sid, version, dict(status=state, run=ev.get_run(), progress=done / max(1, len(rows)),
                                   contexts=dict(done=done, total=len(rows)), reason=None, savedAt=sessions.now()),
                 already_locked=True)
    return state


def run(context):
    sid, version = context.sid, context.version
    with sessions.locked(sid):
        session = sessions.assert_writable(sid, version)
        if session.get('segment', {}).get('status') != 'done' or 'stage6' in session.get('stale', {}):
            raise sessions.StoreError('6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요.', 409, 'segment_required')
        captured = generation.capture(sid, version, session, versions={name: prompt_version(name) for name in ('tag', 'queries', 'novelty')})
    source = _load(sid, version)
    contexts = source['seg'].contexts()
    if not contexts or any(not c.get('confirmed_at') for c in contexts):
        raise sessions.StoreError('6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요.', 409, 'segment_required')
    requested = context.args.get('contexts')
    if requested is not None and set(requested) - {c['context_id'] for c in contexts}:
        raise sessions.StoreError('Context not found', 404, 'not_found')
    concurrency = settings.evidence_llm_concurrency
    if concurrency < 1:
        raise ValueError('evidence_llm_concurrency must be positive')
    ev = EvidenceStore.open(sid, version)
    root = ev.path.parent
    run_id = str(uuid.uuid4())
    fresh = context.args.get('fresh', False) or ev.get_run() is None or session.get('evidence', {}).get('status') == 'stale'
    fresh = fresh or generation.read(sid, version) != captured
    checkpoint = {} if fresh else sessions.read_json(root / 'checkpoint.json') or {}
    all_params = {name: getattr(params, name) for name in vars(params) if name.isupper()}
    all_params['CONCURRENCY'] = concurrency
    with sessions.locked(sid):
        current_session = sessions.assert_writable(sid, version)
        if (captured['segmentRun'] != source['seg'].get_run() or
                captured['prepKey'] != current_session.get('prep', {}).get('derivedRef', {}).get('prepKey')):
            raise sessions.StoreError('Evidence input generation changed', 409, 'stale_run')
        if fresh:
            ev.reset(run_id, all_params)
            for name in ('package.json', 'stage_7.json', 'queries.json', 'llm_calls.json'):
                (root / name).unlink(missing_ok=True)
            for row in contexts:
                ev.set_context(row['context_id'], row['persona_id'], 'queued')
        else:
            used_params = {**ev.snapshot().params, 'CONCURRENCY': concurrency}
            with ev._db(write=True) as db:
                db.execute('UPDATE meta SET run=?, params_json=?', (run_id, json.dumps(used_params)))
        sessions.write_json(root / 'generation.json', captured)
        _session(sid, version, dict(status='running', run=run_id, reason=None, progress=0, detail={}), already_locked=True)
    checkpoint['run'] = run_id
    checkpoint.setdefault('personas', [])
    checkpoint.setdefault('queries', list(checkpoint['personas']))
    checkpoint.setdefault('knownIds', [])
    checkpoint.setdefault('tagging', dict(cache_hits=0, lazy_dims=0))
    events, requests, aborted = Queue(), Queue(), Event()
    calls = _Calls(concurrency, events)
    previous_calls = sessions.read_json(root / 'llm_calls.json') or {}
    saved_calls = Counter()

    def save():
        with calls.lock:
            current_calls = calls.counts.copy()
        with sessions.locked(sid):
            if ev.get_run() != run_id:
                return
            checkpoint['done'] = [r['context_id'] for r in ev.contexts() if r['status'] in ('done', 'skipped')]
            sessions.write_json(root / 'checkpoint.json', checkpoint)
            totals = Counter(sessions.read_json(root / 'llm_calls.json') or {})
            totals.update(current_calls - saved_calls)
            saved_calls.clear()
            saved_calls.update(current_calls)
            sessions.write_json(root / 'llm_calls.json', dict(totals))

    def pulse(**detail):
        if context.should_stop():
            raise _Stopped()
        rows = ev.contexts()
        done = sum(r['status'] in ('done', 'skipped') for r in rows)
        progress = done / max(1, len(rows))
        with calls.lock:
            detail['tagCalls'] = previous_calls.get('evidence.tag', 0) + calls.counts['evidence.tag']
        context.heartbeat(progress, {**detail, 'done': done, 'total': len(rows)})
        _session(sid, version, dict(progress=progress, contexts=dict(done=done, total=len(rows)), detail=detail))
        if context.should_stop():
            raise _Stopped()

    def reconcile():
        with sessions.locked(sid):
            sessions.assert_writable(sid, version)
            known = _known(sid, version)
            ids = {i['id'] for i in known}
            for row in ev.contexts():
                if row['status'] != 'done':
                    continue
                used = set((row.get('counts') or {}).get('knownIds', []))
                if used - ids:
                    _refresh_cached(sid, version, ev, source, row, known)
                    row = next(r for r in ev.contexts() if r['context_id'] == row['context_id'])
                doc_ids = [r['doc_id'] for r in ev.candidates(row['context_id'])]
                tagged_ids = source['cache'].get_tags(doc_ids)
                pairs = source['cache'].get_known(tagged_ids, [known_key(i) for i in known if i['type']=='statement'])
                missing = any((doc_id, known_key(i)) not in pairs for doc_id in tagged_ids for i in known if i['type']=='statement')
                if missing or ids - used or (row.get('counts') or {}).get('knownSnapshot', {}) != known_snapshot(known):
                    ev.set_context(row['context_id'], row['persona_id'], 'done',
                                   counts={**(row.get('counts') or {}), 'knownChanged': True})
            checkpoint['knownIds'] = sorted(ids)
            return known

    def drain():
        while True:
            try:
                _, detail = events.get_nowait()
            except Empty:
                break
            pulse(**detail)

    def prepare(owner, rows):
        known = reconcile()
        call, check = calls.step(owner, 'tag')
        result = tagging.TagResult({}, 0, 0, 0, [], {}, 0)
        # Bound each wave so the caller can pulse/stop between tag batches.
        wave = concurrency * params.TAG_BATCH
        for start in range(0, len(rows), wave):
            pulse(context=owner, step='tag', batch=start // params.TAG_BATCH + 1)
            batch = tagging.tag_documents(sid, [r['doc_id'] for r in rows[start:start + wave]],
                docs=source['docs'], dims_by_id=source['dims'], known_items=known,
                cache=source['cache'], run_task=call, concurrency=concurrency)
            result.tags.update(batch.tags)
            for key in ('calls', 'cache_hits', 'untagged', 'lazy_dims'):
                setattr(result, key, getattr(result, key) + getattr(batch, key))
            result.untagged_ids.extend(batch.untagged_ids)
            result.reason_counts = dict(Counter(result.reason_counts) + Counter(batch.reason_counts))
            for key in ('cache_hits', 'lazy_dims'):
                checkpoint['tagging'][key] += getattr(batch, key)
            save()
            drain()
        check()
        call, check = calls.step(owner, 'tag')
        tagging.judge_known(sid, list(result.tags), [i['id'] for i in known], cache=source['cache'],
                            run_task=call, concurrency=concurrency, known_items=known)
        drain()
        check()
        current = reconcile()
        result.tags = _project(source['cache'], list(result.tags), current)
        return result, current

    def rpc(function, *args):
        future = Future()
        requests.put((future, function, args))
        while not aborted.is_set():
            try:
                return future.result(timeout=.1)
            except FutureTimeout:
                if future.done():
                    raise
        raise _Stopped()

    def compute(row, qrows):
        cid = row['context_id']
        if not qrows:
            raise ValueError('query_embedding_failed (retryable): Context queries are missing')
        pool, tags, counts = {}, {}, Counter()
        known = rpc(reconcile)
        # Retain the Context's input snapshot: a later KI read must not claim
        # that already selected/tagged rows incorporated a concurrent edit.
        known_ids = [item['id'] for item in known]
        used_known = known_snapshot(known)

        def ingest(rows):
            fresh_rows = [r for r in rows if r['doc_id'] not in pool]
            if fresh_rows:
                result, current = rpc(prepare, cid, fresh_rows)
                known[:] = current
                tags.update(result.tags)
                counts.update(cache_hits=result.cache_hits, lazy_dims=result.lazy_dims)
                pool.update({r['doc_id']: r for r in fresh_rows})
            return {r['doc_id']: tags[r['doc_id']] for r in rows if r['doc_id'] in tags}

        def search(qs, n=params.CANDIDATES_M, round=0):
            rows = candidates.search_context(cid, qs, docs=source['docs'], store=source['source'],
                embedder=embedder, exclude=set(pool), top_per_query=n if round else params.TOP_PER_QUERY, m=n)
            return [dict(r, round=round) for r in rows]

        initial = search(qrows)
        ingest(initial)

        def supplement(missing, n):
            rows = search([q for q in qrows if q['dim'].lower() in missing], n, 'cov')
            ingest(rows)
            return rows

        all_selection = tabs.all_tab(list(pool.values()), tags, source['vectors'], source['docs'],
                                      known_items=known, supplement=supplement)
        rounds = 0

        def expand(n):
            nonlocal rounds
            rounds += 1
            return search(qrows, n, rounds)

        new = tabs.new_tab(cid, list(pool.values()), tags, source['vectors'], source['docs'],
                          known_items=lambda: rpc(reconcile), expand=expand, prepare=ingest, supplement=supplement)
        known = rpc(reconcile)
        call, check = calls.step(cid, 'novelty')
        core = novelty.core_representatives([d for d in source['docs'].values() if d.get('context_id') == cid],
                                            source['vectors'], row['centroid'] if row.get('centroid') is not None else [])
        enriched = [{**source['docs'][r['doc_id']], **new.tags.get(r['doc_id'], {}), **r} for r in new.rows]
        judgments = novelty.judge_novelty(sid, {k: v for k, v in row.items() if k != 'centroid'}, enriched, core, known, run_task=call)
        check()
        all_rows, new_rows = novelty.apply_novelty(all_selection.rows, new.rows, judgments)
        counts.update(coverage_supplements=all_selection.coverage_supplements + new.selection.coverage_supplements,
                      new_expansions=new.rounds, rare_fallback=all_selection.rare_fallback + new.selection.rare_fallback,
                      dpp_fill=all_selection.dpp_fill + new.selection.dpp_fill)
        counts.update(query_gen_fail=int(any(q['origin']=='fallback' for q in qrows)), excludedKnown=new.excluded_known)
        return dict(candidates=[dict(r, known_excluded=new.exclusions.get(r['doc_id'])) for r in pool.values()],
                    all=all_rows, new=new_rows, coverage=all_selection.coverage,
                    counts={**counts, 'knownIds':known_ids, 'knownSnapshot':used_known, 'knownChanged':False})

    executor = None
    try:
        save()
        pulse(step='load')
        embedder = known_store.session_embedder(sid, source['session'], known_store.get_embedder)
        pending_ids = {r['context_id'] for r in ev.contexts() if r['status'] not in ('done','skipped')}
        if requested is not None:
            pending_ids &= set(requested)
        for persona in source['seg'].personas():
            pid = persona['persona_id']
            owned = [c for c in contexts if c['persona_id']==pid]
            if not any(c['context_id'] in pending_ids for c in owned):
                continue
            if pid in checkpoint['personas']:
                continue
            if pid not in checkpoint['queries']:
                pulse(step='queries', persona=pid)
                call, check = calls.step(pid, 'queries')
                result = queries.generate_queries(sid, persona, owned,
                    source['session'].get('projectContext', {}).get('oneLiner', ''), run_task=call)
                drain()
                check()
                ev.write_queries('persona:'+pid, result.persona_rows)
                for cid, rows in result.context_rows.items():
                    ev.write_queries('context:'+cid, rows)
                checkpoint['queries'].append(pid)
                save()
            persona_queries = ev.queries('persona:'+pid)
            # Persona support uses all-tab ranking and is checkpointed with queries.
            support = []
            embedding_failed = False
            for kind, qs in [('desire',[q for q in persona_queries if q['dim'].startswith('desire_check')]),
                             ('artifact',[q for q in persona_queries if q['dim']=='artifact'])]:
                try:
                    rows = candidates.search_persona(pid, qs, docs=source['docs'], store=source['source'], embedder=embedder)
                except ValueError as exc:
                    if 'query_embedding_failed' not in str(exc):
                        raise
                    with sessions.locked(sid):
                        generation.check(sid, version, ev, run_id)
                        for owned_context in owned:
                            cid = owned_context['context_id']
                            if cid in pending_ids:
                                ev.set_context(cid, pid, 'failed', error=str(exc))
                                pending_ids.discard(cid)
                    embedding_failed = True
                    break
                tagged, known = prepare(pid, rows)
                selection = tabs.all_tab(rows, tagged.tags, source['vectors'], source['docs'], known_items=known)
                support.extend(dict(doc_id=r['doc_id'], rank=r['rank'], kind=kind) for r in selection.rows)
            if embedding_failed:
                save()
                continue
            with sessions.locked(sid):
                generation.check(sid, version, ev, run_id)
                ev.write_persona_support(pid, support)
            checkpoint['personas'].append(pid)
            save()
        sessions.write_json(root / 'queries.json', ev.queries())
        executor = ThreadPoolExecutor(max_workers=concurrency)
        pending = iter(c for c in contexts if c['context_id'] in pending_ids)
        active = []

        def launch():
            while len(active) < concurrency:
                row = next(pending, None)
                if row is None:
                    break
                reconcile()
                pulse(step='context', context=row['context_id'])
                ev.set_context(row['context_id'], row['persona_id'], 'running', error=None)
                future = executor.submit(compute, row, ev.queries('context:'+row['context_id']))
                active.append((row, future))

        launch()
        while active:
            drain()
            try:
                future, function, args = requests.get(timeout=.05)
            except Empty:
                pass
            else:
                try:
                    future.set_result(function(*args))
                except BaseException as exc:
                    future.set_exception(exc)
                    if not isinstance(exc, Exception):
                        raise
            # Ordered publication gives deterministic checkpoints across concurrency.
            while active and active[0][1].done():
                row, future = active.pop(0)
                cid = row['context_id']
                try:
                    result = future.result()
                    with sessions.locked(sid):
                        generation.check(sid, version, ev, run_id)
                        ev.write_candidates(cid, result['candidates'])
                        ev.write_selected(cid, 'all', _selected(result['all']))
                        ev.write_selected(cid, 'new', _selected(result['new']))
                        ev.set_context(cid, row['persona_id'], 'done', error=None,
                                       coverage=result['coverage'], counts=result['counts'])
                except Exception as exc:
                    with sessions.locked(sid):
                        generation.check(sid, version, ev, run_id)
                        ev.set_context(cid, row['persona_id'], 'failed', error=str(exc))
                save()
                pulse(step='context', context=cid)
                reconcile()
            launch()
            if context.should_stop():
                raise _Stopped()
        reconcile()
        save()
        _finish(sid, version, ev, run_id)

    except (_Stopped, _LLMUnavailable) as exc:
        save()
        _session(sid, version, dict(status='interrupted', reason=LLM_REASON if isinstance(exc, _LLMUnavailable) else None))
        raise
    except Exception as exc:
        _session(sid, version, dict(status='failed', reason=str(exc)))
        raise
    finally:
        aborted.set()
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
        save()


def _action(sid, version, context_id, run_id):
    data = sessions.assert_writable(sid, version)
    version = version or data.get('version') or sessions.read_json(sessions.root_dir(sid) / 'meta.json')['activeVersion']
    ev = EvidenceStore.open(sid, version)
    if ev.get_run() != run_id or data.get('evidence', {}).get('run') != run_id or data.get('evidence', {}).get('status') == 'stale' or 'stage6' in data.get('stale', {}):
        raise sessions.StoreError('Evidence run changed', 409, 'stale_run')
    generation.check(sid, version, ev, run_id)
    row = next((r for r in ev.contexts() if r['context_id']==context_id), None)
    if row is None:
        raise sessions.StoreError('Context not found', 404, 'not_found')
    return version, ev, row


def _context_response(ev, source, context_id, known):
    row = next(r for r in ev.contexts() if r['context_id'] == context_id)
    context = next(c for c in source['seg'].contexts() if c['context_id'] == context_id)
    context = {k: v for k, v in context.items() if k != 'centroid'}
    pool = ev.candidates(context_id)
    tags = _project(source['cache'], [r['doc_id'] for r in pool], known)
    docs = source['docs']

    def view(selected, role='support'):
        return assemble.item_view(selected, docs, tags, role)

    counter = assemble.counter_evidence(pool, tags, context_mean=assemble.context_polarity_mean(pool, tags))
    rare = assemble.rare_evidence(pool, tags, docs)
    counts = row.get('counts') or {}
    return dict(context=context, tab='new', items=[view(r) for r in ev.selected(context_id, 'new')],
                counter=[view(r, 'counter') for r in counter], rare=[view(r, 'rare') for r in rare],
                excludedKnown=counts.get('excludedKnown', 0), queries=ev.queries('context:'+context_id),
                queryFailed=bool(counts.get('query_gen_fail')), undifferentiated=counts.get('undifferentiated', []))


def _load_context(sid, version, ev, context_id, known):
    session = sessions.read_json(version_dir(sid, version) / 'session.json')
    session, pver = generation.inputs(sid, version, session)
    seg = SegmentStore.open(sid, version)
    wanted = {r['doc_id'] for r in ev.candidates(context_id)}
    with seg._db() as db:
        from app.segment.store import _decode
        docs = {i: _decode(row) for i in wanted
                if (row := db.execute('SELECT * FROM docs WHERE doc_id=?', (i,)).fetchone())}
    root = prepared_root(sid, session)
    for i, original in assemble._load_docs(root, wanted).items():
        docs[i] = {**docs.get(i, {}), **original}
    if session.get('training', {}).get('exportRef'):
        from app.known.filter import read_export
        for row in read_export(sid, session):
            if row['doc_id'] in docs:
                docs[row['doc_id']]['tagProbs'] = row.get('tagProbs')
    vector_ids = wanted | {i['doc_id'] for i in known if i.get('doc_id')}
    ids, vectors = VectorStore(root).get(sorted(vector_ids))
    return dict(seg=seg, docs=docs, vectors=dict(zip(ids, vectors)),
                cache=TagCache.open(sid, session['prep']['derivedRef']['prepKey'], pver))


def refresh_new(sid: str, version: str | None, context_id: str, run: str) -> dict:
    """Judge missing statement pairs outside the publication lock, then recheck."""
    with sessions.locked(sid):
        version, ev, row = _action(sid, version, context_id, run)
        if row['status'] != 'done':
            raise sessions.StoreError('Context not ready', 409, 'not_ready')
        generation.check_prompts(sid, version)
        known = _known(sid, version)
        source = _load_context(sid, version, ev, context_id, known)
        ev.patch_counts(context_id, knownChanged=True)
    calls = 0
    def call(task):
        nonlocal calls
        calls += 1
        return registry.run_task(task)
    tagging.judge_known(sid, list(source['docs']), [i['id'] for i in known],
                        cache=source['cache'], known_items=known, run_task=call, concurrency=1)
    with sessions.locked(sid):
        version, ev, row = _action(sid, version, context_id, run)
        current = _known(sid, version)
        _refresh_cached(sid, version, ev, source, row, current)
        if known_snapshot(current) != known_snapshot(known):
            ev.patch_counts(context_id, knownChanged=True)
        root = ev.path.parent
        totals = sessions.read_json(root / 'llm_calls.json') or {}
        totals['evidence.tag'] = totals.get('evidence.tag', 0) + calls
        sessions.write_json(root / 'llm_calls.json', totals)
        report = sessions.read_json(root / 'stage_7.json') or {}
        report.update(tag_calls=totals['evidence.tag'], llm_calls=sum(totals.values()))
        sessions.write_json(root / 'stage_7.json', report)
        # Recompute only this Context's candidate flag; full package assembly is lazy.
        pool = ev.candidates(context_id)
        tags = _project(source['cache'], source['docs'], current)
        rare = assemble._rare_candidates(pool, tags, source['docs'])
        escalation = assemble.undifferentiated_candidate(rare, source['vectors'])
        assemble.append_context_flag(source['seg'], context_id, 'undifferentiated_candidate', present=bool(escalation))
        ev.patch_counts(context_id, undifferentiated=escalation)
        snapshot = ev.snapshot()
        report['per_tab_counts'] = {tab:sum(r['tab']==tab for r in snapshot.selected) for tab in ('all','new')}
        report['novelty_distribution'] = dict(Counter(r['novelty'] for r in snapshot.selected if r.get('novelty')))
        report.setdefault('escalation_candidates', {}).pop(context_id, None)
        if escalation:
            report['escalation_candidates'][context_id] = escalation
        sessions.write_json(root / 'stage_7.json', report)
        sessions.write_json(root / 'package_dirty.json', {'run':run})
        return _context_response(ev, source, context_id, current)


def skip_context(sid: str, version: str | None, context_id: str, run: str) -> dict:
    with sessions.locked(sid):
        version, ev, row = _action(sid, version, context_id, run)
        if sessions.read_json(version_dir(sid, version) / 'session.json')['evidence']['status'] == 'running':
            raise sessions.StoreError('Evidence is running', 409, 'running')
        if row['status'] != 'failed':
            raise sessions.StoreError('Only failed Contexts can be skipped', 409, 'not_ready')
        ev.set_context(context_id, row['persona_id'], 'skipped', error=None)
        checkpoint_path = ev.path.parent / 'checkpoint.json'
        checkpoint = sessions.read_json(checkpoint_path) or {'run': run}
        checkpoint['done'] = [r['context_id'] for r in ev.contexts() if r['status'] in ('done', 'skipped')]
        sessions.write_json(checkpoint_path, checkpoint)
        # Publish without reacquiring the non-reentrant session flock.
        _assemble(sid, version)
        rows = ev.contexts()
        done = sum(r['status'] in ('done','skipped') for r in rows)
        path = version_dir(sid, version) / 'session.json'
        data = sessions.read_json(path)
        data['evidence'].update(status='done' if done == len(rows) else 'partial',
                                contexts=dict(done=done,total=len(rows)), progress=done/max(1,len(rows)), savedAt=sessions.now())
        data.setdefault('completion', {}).pop('evidenceDone', None)
        if done == len(rows):
            clear_stale(sid, version, 'stage7', already_locked=True)
            data.get('stale', {}).pop('stage7', None)
        sessions.write_json(path, data)
        return data['evidence']
