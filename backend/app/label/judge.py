"""Judge prepared documents with durable, shared caches and bounded retries."""
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import math
from pathlib import Path
import time

from app.config import settings
from app.context import versions
from app.context.stale import judge_done
from app.label import gpt
from app.label.jev import get_jev_client as JevClient, JevError, build_state, GPT_ONLY_MESSAGE, labeler_mode
from app.label.questions import QVER, jev_questions
from app.label.votes import VoteCache
from app.work.status import transaction


JEV_TRANSIENT_LIMIT = 5
JEV_BACKOFF_CAP_S = 30
LEASE_WAIT_LIMIT = 6000  # At most ten minutes of 0.1-second lease polling.


def context_key(one_liner, labeler):
    if labeler == 'jev':
        identity = f'{settings.jev_model}/{settings.jev_backend}'
    elif labeler == 'gpt':
        model = settings.openai_model if settings.label_gpt_backend == 'openai_api' else settings.codex_profile
        identity = f'{model}/{settings.label_gpt_backend}'
    else:
        raise ValueError('Unknown labeler')
    questions = Path(__file__).with_name(f'questions.{QVER}.json').read_text(encoding='utf-8')
    return hashlib.sha256((one_liner + questions + identity).encode()).hexdigest()[:8]


def cache_root(sid, prep_key, labeler, one_liner):
    for component in (sid, prep_key, labeler):
        if not isinstance(component, str) or not component or component in ('.', '..') or Path(component).name != component:
            raise ValueError('Invalid cache identity')
    return Path(settings.local_data_dir) / 'judge' / sid / prep_key / labeler / f'{QVER}-{context_key(one_liner, labeler)}'


def estimate(docs, one_liner, labeler, *, key_count=None, recent=None):
    """Estimate seconds and JSON input tokens; recent contains (time, count) pairs."""
    count = len(docs)
    tokens = None
    if labeler == 'jev':
        keys = len(set(settings.jev_api_keys)) if key_count is None else key_count
        seconds = count * 60 / (settings.jev_rate_per_min * keys) if keys else None
        tokens = 0
        for doc in docs:
            try:
                state, _ = build_state(doc, one_liner)
            except JevError:
                continue
            request = dict(model=settings.jev_model, state=state, questions=jev_questions(one_liner))
            tokens += math.ceil(len(json.dumps(request, ensure_ascii=False, separators=(',', ':'))) / 4)
    else:
        samples = [(at, n) for at, n in (recent or []) if at >= time.monotonic() - 600]
        elapsed = samples[-1][0] - samples[0][0] if len(samples) > 1 else 0
        done = samples[-1][1] - samples[0][1] if len(samples) > 1 else 0
        seconds = count * elapsed / done if done and elapsed else None
    return dict(seconds=0 if not count else seconds, jevTokens=tokens)


def _pause(ctx, reason, detail):
    # heartbeat blocks until resume/stop, keeping execute() from marking it done.
    with transaction(ctx.sid) as db:
        db.execute("UPDATE runs SET action='pause', state='paused' WHERE run_id=? AND action IS NOT 'stop'", (ctx.run_id,))
    ctx.heartbeat(detail['progress'], {**detail, 'reason': reason})


def run_worker(ctx):
    labeler = ctx.args['labeler']
    if labeler not in ('jev', 'gpt'):
        raise ValueError('Unknown labeler')
    session = versions._data(ctx.sid, ctx.version)
    if labeler == 'jev' and labeler_mode(session) == 'gpt_only':
        raise ValueError(GPT_ONLY_MESSAGE)
    ref = session['prep']['derivedRef']
    one_liner = session['projectContext']['oneLiner']
    root = cache_root(ctx.sid, ref['prepKey'], labeler, one_liner)
    cid = ref['collectionId']
    if not isinstance(cid, str) or Path(cid).name != cid or cid in ('.', '..'):
        raise ValueError('Invalid collection')
    docs_root = Path(settings.local_data_dir) / 'derived' / ctx.sid / cid / ref['prepKey'] / 'docs'
    if not docs_root.is_dir():
        raise ValueError('Prepared documents missing')
    docs = {}
    for path in sorted(docs_root.glob('*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    doc = json.loads(line)
                    if doc['doc_id'] in docs:
                        raise ValueError('Duplicate prepared document ID')
                    docs[doc['doc_id']] = doc
    changed = not (root / 'votes.sqlite').exists() and any(root.parent.glob('*/votes.sqlite'))
    cache = VoteCache(root)
    ctx._heartbeat_callback = lambda: cache.refresh(ctx.run_id)
    client = None
    pool = None
    try:
        first = set(settings.label_priority_sources)
        cache.seed(docs, {doc_id: 0 if doc.get('source') in first else 1 for doc_id, doc in docs.items()})
        from app.label.route import sync
        from app.label.store import LabelStore
        labels = LabelStore(versions.version_dir(ctx.sid, ctx.version))
        caches = {name: VoteCache(cache_root(ctx.sid, ref['prepKey'], name, one_liner))
                  for name in ('jev', 'gpt')}
        # Bootstrap cached results on restart, even if there is no work to lease.
        sync(labels, caches['jev'], caches['gpt'], mode=labeler_mode(session))
        ctx_key = context_key(one_liner, labeler)
        recent = deque([(time.monotonic(), cache.counts()['done'])])
        message = '판정 맥락이 바뀌어 다시 판정합니다' if changed else None
        batch_size = 50 if labeler == 'jev' else settings.label_batch_size
        if batch_size <= 0:
            raise ValueError('Batch size must be positive')
        concurrency = max(1, settings.label_concurrency) if labeler == 'gpt' else 1
        total_estimate = estimate(list(docs.values()), one_liner, labeler)
        client = JevClient(settings.jev_api_keys, settings.jev_model) if labeler == 'jev' else None
        transient_failures = 0
        lease_waits = 0
        pool = ThreadPoolExecutor(max_workers=concurrency) if labeler == 'gpt' else None
        inflight = {}
        while True:
            counts = cache.counts()
            progress = (counts['done'] + counts['bad']) / len(docs) if docs else 1
            detail = dict(**counts, progress=progress, cacheRef=str(root.relative_to(settings.local_data_dir)), message=message)
            remaining = dict(total_estimate)
            if labeler == 'gpt':
                remaining = estimate(range(counts['pending']), one_liner, labeler, recent=recent)
            elif remaining['seconds'] is not None:
                remaining['seconds'] *= counts['pending'] / len(docs) if docs else 0
            detail['estimate'] = remaining
            ctx.heartbeat(progress, detail)
            if ctx.should_stop():
                return
            if labeler == 'gpt':
                # Rolling slots: refill each finished batch immediately instead of
                # waiting for the slowest batch of a whole group.
                while len(inflight) < concurrency:
                    chunk_ids = cache.lease(batch_size, ctx.run_id)
                    if not chunk_ids:
                        break
                    chunk = [docs[i] for i in chunk_ids]
                    inflight[pool.submit(gpt.judge_batch, chunk, one_liner, sid=ctx.sid,
                                         ctx_key=ctx_key, qver=QVER)] = chunk
                ids = [doc['doc_id'] for chunk in inflight.values() for doc in chunk]
            else:
                ids = cache.lease(batch_size, ctx.run_id)
            if not ids:
                if counts['pending']:
                    # Another version may own live leases in this shared cache.
                    lease_waits += 1
                    if lease_waits >= LEASE_WAIT_LIMIT:
                        # lease() has just attempted safe reclamation. Leave live
                        # owners alone and make this run resumable, not complete.
                        reason = '다른 판정 워커의 응답을 기다리는 시간이 초과되었습니다. 이어서 진행하세요.'
                        ctx.heartbeat(progress, {**detail, 'reason': reason})
                        with transaction(ctx.sid) as db:
                            db.execute("UPDATE runs SET state='interrupted' WHERE run_id=? AND state IN ('running','paused')", (ctx.run_id,))
                        return
                    time.sleep(.1)
                    continue
                judge_done(ctx)
                return
            lease_waits = 0
            if labeler == 'gpt':
                paused = error = None

                def collect(finished):
                    nonlocal paused, error
                    for future in finished:
                        chunk = inflight.pop(future)
                        try:
                            votes, missing = future.result()
                        except gpt.LabelerPaused as exc:
                            if not exc.usage_limit:
                                for doc in chunk:
                                    cache.fail(doc['doc_id'], 'gpt_backend_failed')
                            if paused is None or exc.usage_limit and not paused.usage_limit:
                                paused = exc
                        except Exception as exc:
                            if error is None:
                                error = exc
                        else:
                            for doc_id, vote in votes.items():
                                cache.put(doc_id, vote.model_dump())
                            for doc_id in missing:
                                cache.fail(doc_id, 'invalid_or_missing_vote')

                finished, _ = wait(list(inflight), timeout=5, return_when=FIRST_COMPLETED)
                collect(finished)
                if paused is not None or error is not None:
                    # Store the batches already in flight before stopping or pausing.
                    collect(wait(list(inflight))[0])
                if error is not None:
                    raise error
                if paused is not None:
                    cache.release()
                    sync(labels, caches['jev'], caches['gpt'], mode=labeler_mode(session))
                    _pause(ctx, str(paused), detail)
                    continue
                if not finished:
                    continue
            else:
                batch = [docs[i] for i in ids]
                for doc in batch:
                    try:
                        vote = client.judge(doc, one_liner, idempotency_key=f"{doc['doc_id']}:{QVER}-{ctx_key}")
                    except JevError as exc:
                        if exc.transient:
                            cache.release()
                            transient_failures += 1
                            if transient_failures >= JEV_TRANSIENT_LIMIT:
                                _pause(ctx, 'Jev 연결이 불안정해 판정을 멈췄습니다', detail)
                                transient_failures = 0
                            else:
                                time.sleep(min(2 ** (transient_failures - 1), JEV_BACKOFF_CAP_S))
                            break
                        transient_failures = 0
                        if exc.code == 'unconnected':
                            ctx.heartbeat(progress, {**detail, 'reason': str(exc), 'code': exc.code})
                            raise
                        if exc.code == 'insufficient':
                            cache.release()
                            _pause(ctx, str(exc), detail)
                            break
                        cache.fail(doc['doc_id'], exc.code)
                    else:
                        transient_failures = 0
                        cache.put(doc['doc_id'], vote.model_dump())
            sync(labels, caches['jev'], caches['gpt'], mode=labeler_mode(session))
            recent.append((time.monotonic(), cache.counts()['done']))
            while len(recent) > 1 and recent[0][0] < time.monotonic() - 600:
                recent.popleft()
    finally:
        if pool is not None:
            pool.shutdown(wait=True)
        ctx._heartbeat_callback = None
        cache.release()
        if client is not None:
            client.close()
