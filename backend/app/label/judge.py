"""Judge prepared documents with durable, shared caches and bounded retries."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import time

from app.config import settings
from app.context import versions
from app.label import gpt
from app.label.jev import JevClient, JevError, build_state
from app.label.questions import QVER, jev_questions
from app.label.votes import VoteCache
from app.work.status import transaction


JEV_TRANSIENT_LIMIT = 5
JEV_BACKOFF_CAP_S = 30


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
    cache.seed(docs)
    from app.label.route import sync
    from app.label.store import LabelStore
    labels = LabelStore(versions.version_dir(ctx.sid, ctx.version))
    caches = {name: VoteCache(cache_root(ctx.sid, ref['prepKey'], name, one_liner))
              for name in ('jev', 'gpt')}
    # Bootstrap cached results on restart, even if there is no work to lease.
    sync(labels, caches['jev'], caches['gpt'])
    ctx_key = context_key(one_liner, labeler)
    recent = deque([(time.monotonic(), cache.counts()['done'])])
    message = '판정 맥락이 바뀌어 다시 판정합니다' if changed else None
    batch_size = 50 if labeler == 'jev' else settings.label_batch_size
    if batch_size <= 0:
        raise ValueError('Batch size must be positive')
    total_estimate = estimate(list(docs.values()), one_liner, labeler)
    client = JevClient(settings.jev_api_keys, settings.jev_model) if labeler == 'jev' else None
    transient_failures = 0
    try:
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
            ids = cache.lease(batch_size, ctx.run_id)
            if not ids:
                if counts['pending']:
                    # Another version may own live leases in this shared cache.
                    time.sleep(.1)
                    continue
                return
            batch = [docs[i] for i in ids]
            if labeler == 'gpt':
                try:
                    votes, missing = gpt.judge_batch(batch, one_liner, sid=ctx.sid, ctx_key=ctx_key, qver=QVER)
                except gpt.LabelerPaused as exc:
                    if not exc.usage_limit:
                        for doc_id in ids:
                            cache.fail(doc_id, 'gpt_backend_failed')
                    cache.release()
                    sync(labels, caches['jev'], caches['gpt'])
                    _pause(ctx, str(exc), detail)
                    continue
                for doc_id, vote in votes.items():
                    cache.put(doc_id, vote.model_dump())
                for doc_id in missing:
                    cache.fail(doc_id, 'invalid_or_missing_vote')
            else:
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
            sync(labels, caches['jev'], caches['gpt'])
            recent.append((time.monotonic(), cache.counts()['done']))
            while len(recent) > 1 and recent[0][0] < time.monotonic() - 600:
                recent.popleft()
    finally:
        cache.release()
        if client is not None:
            client.close()
