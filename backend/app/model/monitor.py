"""Random one-percent monitoring through the existing context-keyed vote caches."""
import hashlib
import json
import math
import os
import random
import time

import httpx

from app.config import settings
from app.context import store
from app.label import gpt, judge, rule
from app.label.jev import get_jev_client as JevClient, JevVote, JevError
from app.label.questions import QVER
from app.label.overview import caches_for, labels_for, session
from app.model import infer

WARNING = '이 도메인에서는 LLM 라벨 구간으로 다시 하거나 추가 학습하세요'


def divergence(predicted, judged):
    if len(predicted) != len(judged):
        raise ValueError('Monitoring rows must align')
    n = len(predicted)
    value = sum(a != b for a, b in zip(predicted, judged)) / n if n else None
    return dict(n=n, monitorDivergence=value,
                warning=WARNING if value is not None and value > settings.monitor_warn else None)


def _claim(cache, doc_id, run_id):
    """Claim only the sampled row; never drain unrelated pending judge work."""
    cache.run_id = run_id
    with cache._db() as db:
        cache.reclaim(db)
        db.execute('INSERT OR IGNORE INTO owners VALUES (?,?)', (run_id, os.getpid()))
        row = db.execute('SELECT * FROM votes WHERE doc_id=?', (doc_id,)).fetchone()
        if row['status'] == 'done':
            return json.loads(row['payload_json'])
        if row['status'] == 'bad':
            return False
        if row['run_id'] not in (None, run_id):
            raise store.StoreError('감시 표본을 다른 판정 워커가 처리 중입니다. 이어서 진행하세요.')
        db.execute('UPDATE votes SET run_id=?,at=? WHERE doc_id=?', (run_id, time.time(), doc_id))
    return None


def run_worker(ctx):
    with store.locked(ctx.sid):
        data = session(ctx.sid, ctx.version, writable=True)
    if settings.monitor_rate == 0:
        return
    docs = infer.documents(ctx.sid, data)
    ids = sorted(docs)
    # Stable random sample across retries, independent of document ordering.
    seed = int(hashlib.sha256(f'{ctx.sid}:{ctx.version}'.encode()).hexdigest(), 16)
    sampled = random.Random(seed).sample(ids, min(len(ids), math.ceil(len(ids) * settings.monitor_rate)))
    caches = caches_for(ctx.sid, data)
    for cache in caches.values():
        cache.seed(sampled)
    labels = labels_for(ctx.sid, data)
    model_id = ctx.args.get('modelId') or data.get('training', {}).get('modelId') or data['labeling']['modelId']
    with labels._db() as db:
        predictions = {r[0]: json.loads(r[1])['level'] for r in db.execute(
            'SELECT doc_id,payload FROM model_predictions WHERE model_id=?', (model_id,))}
    one_liner = data.get('projectContext', {}).get('oneLiner', '')
    predicted, judged = [], []
    errors = []
    per_labeler = {'jev': [], 'gpt': []}
    client = None
    try:
        for i, doc_id in enumerate(sampled):
            ctx.heartbeat(i / max(len(sampled), 1),
                          {'phase': 'monitor', 'sampled': len(sampled), 'done': i, 'total': len(sampled)})
            if ctx.should_stop():
                return
            votes = {}
            try:
                for name, cache in caches.items():
                    for _ in range(3):
                        payload = _claim(cache, doc_id, ctx.run_id)
                        if payload is not None:
                            if payload is not False:
                                votes[name] = payload
                            break
                        if name == 'jev':
                            if client is None:
                                client = JevClient(settings.jev_api_keys, settings.jev_model)
                            vote = client.judge(docs[doc_id], one_liner,
                                idempotency_key=f'{doc_id}:{QVER}-{judge.context_key(one_liner, name)}')
                        else:
                            answers, missing = gpt.judge_batch([docs[doc_id]], one_liner, sid=ctx.sid,
                                ctx_key=judge.context_key(one_liner, name), qver=QVER)
                            vote = answers.get(doc_id)
                        if vote is None:
                            cache.fail(doc_id, 'invalid_or_missing_vote')
                        else:
                            payload = vote.model_dump()
                            cache.put(doc_id, payload)
                            votes[name] = payload
                            break
            except (JevError, gpt.LabelerPaused, store.StoreError, httpx.HTTPError, OSError) as exc:
                errors.append(dict(doc_id=doc_id, reason=type(exc).__name__))
                for cache in caches.values():
                    cache.release()
                continue
            if doc_id in predictions and set(votes) == {'jev', 'gpt'}:
                jev = JevVote.model_validate(votes['jev'])
                gpt_vote = gpt.GptVote.model_validate(votes['gpt'])
                levels = dict(jev=rule.grade({k: int(jev.probs[k] >= .5) for k in rule.GRADE_FIELDS}),
                    gpt=rule.grade(dict(anchor=gpt_vote.anchor, situation=gpt_vote.situation, **gpt_vote.sem)))
                predicted.append(predictions[doc_id])
                # Conservative divergence: either judge differing counts once.
                judged.append(predictions[doc_id] if all(v == predictions[doc_id] for v in levels.values()) else 'diverged')
                for name in per_labeler:
                    per_labeler[name].append(levels[name])
            else:
                errors.append(dict(doc_id=doc_id, reason='missing_prediction_or_vote'))
        result = divergence(predicted, judged)
        result.update(sampled=len(sampled), done=len(sampled), total=len(sampled),
            incomplete=len(sampled)-len(predicted), errors=errors,
            state='done', reason=f'감시 표본 {len(errors)}건을 완료하지 못했습니다.' if errors else None,
            perLabeler={name: divergence(predicted, levels)['monitorDivergence'] for name, levels in per_labeler.items()})
        with store.locked(ctx.sid):
            session(ctx.sid, ctx.version, writable=True)
            store._update_locked(ctx.sid, {'training': {'monitor': result}})
            # All stage-five writes still go through the single export writer.
            stage = store.read_json(store.session_dir(ctx.sid) / 'stage_5.json')
            if stage is not None:
                from app.model.export import write_stage5
                write_stage5(ctx.sid, store.load_session(ctx.sid), stage.get('model'))
        ctx.heartbeat(1, result)
    finally:
        for cache in caches.values():
            cache.release()
        if client is not None:
            client.close()
