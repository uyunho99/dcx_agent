"""Cached ensemble inference and version-local predictions; no provider calls."""
from dataclasses import asdict, dataclass
import json
import math

import numpy as np
import torch

from app.config import settings
from app.context import store
from app.label import questions, rule
from app.label.overview import labels_for, index_documents, session, caches_for
from app.model import registry
from app.model.features import build_features
from app.model.net import HEADS, probabilities
from app.model.train import SIGNALS, REASONS, _logits
from app.vectors.store import VectorStore


@dataclass
class Pred:
    tagProbs: dict
    gradeProbs: dict
    level: str
    confidence: float
    predEntropy: float
    relevanceScore: float
    memberDisagree: bool
    memberTagProbs: list
    signal: str | None = None
    reason: str | None = None


def from_tag_probs(tag_probs, member_tag_probs=(), *, signal=None, reason=None):
    grades = rule.grade_probs(tag_probs)
    level = max(grades, key=grades.get)
    members = [max(p, key=p.get) for tags in member_tag_probs if (p := rule.grade_probs(tags))]
    return Pred(dict(tag_probs), grades, level, float(grades[level]),
        -sum(p * math.log(p) for p in grades.values() if p > 0),
        float(grades['core'] + grades['supporting']), len(set(members)) > 1,
        list(member_tag_probs), signal, reason)


def predict(model, X) -> list[Pred]:
    x = torch.as_tensor(X, dtype=torch.float32)
    if x.ndim != 2 or x.shape[1] != 1032 or not torch.isfinite(x).all():
        raise ValueError('Expected finite 1032-column features')
    with torch.inference_mode():
        outputs = [member.probabilities(x) for member in model.members]
        means = {k: torch.stack([out[k] for out in outputs]).mean(0) for k in HEADS}
        calibrated = probabilities({k: _logits(p, k) / model.temperatures[k] for k, p in means.items()})
    def tags(output):
        return torch.cat([output['anchor'], output['sem'], output['situation']], -1).tolist()
    member_rows = [tags(out) for out in outputs]
    signals = calibrated['signal'].argmax(-1).tolist()
    reasons = calibrated['reason'].argmax(-1).tolist()
    per_head = model.meta.get('perHead', {})
    return [from_tag_probs(dict(zip(rule.GRADE_FIELDS, row)),
        [dict(zip(rule.GRADE_FIELDS, rows[i])) for rows in member_rows],
        signal=SIGNALS[signals[i]] if per_head.get('signal', {}).get('trained', True) else None,
        reason=REASONS[reasons[i]] if per_head.get('reason', {}).get('trained', True) else None)
        for i, row in enumerate(tags(calibrated))]


def route_prediction(pred):
    if settings.model_cut_low <= pred.relevanceScore <= settings.model_cut_high:
        return 'model_uncertain'
    return 'model_disagree' if pred.memberDisagree else 'accepted'


def prepared_root(sid, data):
    from app.routers.prep import _root
    ref = data.get('prep', {}).get('derivedRef')
    if data.get('prep', {}).get('status') != 'done' or not ref:
        raise store.StoreError('전처리를 먼저 완료하세요.')
    return _root(sid, ref['collectionId'], ref['prepKey'])


def embedder_for(sid, data):
    manifest = store.read_json(prepared_root(sid, data) / 'manifest.json')
    if not manifest or not manifest.get('embedder'):
        raise store.StoreError('임베딩 정보를 찾을 수 없습니다.', 409, 'no_vectors')
    return manifest['embedder']


def documents(sid, data):
    root = prepared_root(sid, data) / 'docs'
    if not root.is_dir():
        raise store.StoreError('전처리 문서를 찾을 수 없습니다.')
    docs = {}
    for path in sorted(root.glob('*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    doc = json.loads(line)
                    if doc['doc_id'] in docs:
                        raise ValueError('Duplicate prepared document ID')
                    docs[doc['doc_id']] = doc
    return docs


def _truncation(sid, data):
    cache = caches_for(sid, data).get('jev')
    if cache is None:
        return {}
    with cache._db() as db:
        return {r[0]: json.loads(r[1]).get('truncated', False) for r in
                db.execute("SELECT doc_id,payload_json FROM votes WHERE status='done'")}


def feature_rows(sid, data, docs):
    """Preserve caller order and join Jev truncation without invoking a judge."""
    truncated = _truncation(sid, data)
    docs = [dict(d, jev_truncated=truncated.get(d['doc_id'], False)) for d in docs]
    return build_features(docs, VectorStore(prepared_root(sid, data)))


def _batches(sid, data, docs):
    """Read each vector shard and vote cache once, with bounded feature batches."""
    truncated = _truncation(sid, data)
    seen = set()
    vectors = VectorStore(prepared_root(sid, data))
    for ids, matrix, _ in vectors.iter_shards():
        selected = [i for i, doc_id in enumerate(ids) if doc_id in docs]
        for start in range(0, len(selected), 256):
            indices = selected[start:start + 256]
            batch = [dict(docs[ids[i]], jev_truncated=truncated.get(ids[i], False)) for i in indices]
            seen.update(d['doc_id'] for d in batch)
            yield batch, build_features(batch, matrix[indices])
    missing = [doc_id for doc_id in docs if doc_id not in seen]
    for start in range(0, len(missing), 256):
        batch = [dict(docs[i], jev_truncated=truncated.get(i, False)) for i in missing[start:start + 256]]
        yield batch, build_features(batch, {})


def prediction_schema(labels, model_mode=False):
    with labels._db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS inference_context (model_mode INTEGER PRIMARY KEY)')
        if model_mode:
            db.execute('INSERT OR IGNORE INTO inference_context VALUES (1)')
        db.execute('''CREATE TABLE IF NOT EXISTS model_predictions (
            doc_id TEXT PRIMARY KEY, model_id TEXT NOT NULL, payload TEXT NOT NULL,
            rule_version TEXT NOT NULL, invalid_vector INTEGER NOT NULL DEFAULT 0)''')


def _project(db, doc_id, pred, invalid=False):
    current = db.execute('SELECT source FROM final WHERE doc_id=?', (doc_id,)).fetchone()
    if current and current['source'] == 'human':
        return
    reason = 'model_uncertain' if invalid else route_prediction(pred)
    tags = dict(anchor=pred.tagProbs['anchor'] >= .5, situation=pred.tagProbs['situation'] >= .5,
        sem={key: int(pred.tagProbs[key] >= .5) for key in rule.SEM},
        signal=pred.signal if pred.level != 'non' else None,
        reason_code=pred.reason if pred.level == 'non' else None)
    route = 'accepted' if reason == 'accepted' else 'escalated:' + reason
    db.execute('''INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(doc_id) DO UPDATE SET level=excluded.level, confidence=excluded.confidence,
        source=excluded.source, route=excluded.route, tags_json=excluded.tags_json,
        reason_code=excluded.reason_code, signal=excluded.signal, rule_version=excluded.rule_version,
        questions_version=excluded.questions_version, grade_mismatch=0''',
        (doc_id, pred.level, pred.confidence, 'model', route, json.dumps(tags), tags['reason_code'],
         tags['signal'], rule.RULE_VERSION, questions.QVER, '{}', '[]', 0))
    if reason == 'accepted':
        db.execute("UPDATE queue SET status='closed' WHERE doc_id=? AND reason LIKE 'model_%'", (doc_id,))
    else:
        db.execute('''INSERT INTO queue VALUES (?,?,?,'open') ON CONFLICT(doc_id)
            DO UPDATE SET reason=excluded.reason, priority=excluded.priority, status='open' ''',
            (doc_id, reason, pred.confidence))


def refresh_predictions(labels):
    """AC-17: rule-only changes reuse stored tag/member probabilities."""
    with labels._db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='model_predictions'").fetchone():
            return False
        model_mode = db.execute('SELECT 1 FROM inference_context WHERE model_mode=1').fetchone() is not None
        for row in db.execute('SELECT * FROM model_predictions WHERE rule_version!=?', (rule.RULE_VERSION,)).fetchall():
            old = json.loads(row['payload'])
            pred = from_tag_probs(old['tagProbs'], old['memberTagProbs'], signal=old.get('signal'), reason=old.get('reason'))
            db.execute('UPDATE model_predictions SET payload=?,rule_version=? WHERE doc_id=?',
                (json.dumps(asdict(pred)), rule.RULE_VERSION, row['doc_id']))
            if model_mode:
                _project(db, row['doc_id'], pred, row['invalid_vector'])
    return model_mode


def run_worker(ctx):
    with store.locked(ctx.sid):
        data = session(ctx.sid, ctx.version, writable=True)
        model_id = ctx.args.get('modelId') or data.get('labeling', {}).get('modelId') or data.get('training', {}).get('modelId')
        registry.require_compatible(model_id, embedder_for(ctx.sid, data))
        labels = labels_for(ctx.sid, data)
        prediction_schema(labels, data.get('labeling', {}).get('mode') == 'model')
        index_documents(ctx.sid, data, labels)
    model = registry.load(model_id)
    docs = documents(ctx.sid, data)
    completed = 0
    for batch, X in _batches(ctx.sid, data, docs):
        ctx.heartbeat(completed / max(len(docs), 1),
                      {'phase': 'infer', 'modelId': model_id, 'done': completed, 'total': len(docs)})
        if ctx.should_stop():
            return
        predictions = predict(model, X)
        with store.locked(ctx.sid):
            session(ctx.sid, ctx.version, writable=True)
            with labels._db() as db:
                for doc, pred, x in zip(batch, predictions, X):
                    invalid = not np.any(x[:1024]) or any(
                        model.meta.get('perHead', {}).get(k, {}).get('trained') is False
                        for k in ('anchor', 'sem', 'situation'))
                    db.execute('INSERT OR REPLACE INTO model_predictions VALUES (?,?,?,?,?)',
                        (doc['doc_id'], model_id, json.dumps(asdict(pred)), rule.RULE_VERSION, int(invalid)))
                    # LLM training keeps accepted and human labels for training provenance.
                    if data.get('labeling', {}).get('mode') == 'model':
                        _project(db, doc['doc_id'], pred, invalid)
        completed += len(batch)
    with store.locked(ctx.sid):
        session(ctx.sid, ctx.version, writable=True)
        store._update_locked(ctx.sid, {'training': {'modelId': model_id, 'inferStatus': 'done'}})
        if data.get('labeling', {}).get('mode') == 'model' and settings.monitor_rate > 0:
            from app.work import runner
            work = runner.start(ctx.sid, ctx.version, 'monitor', {'modelId': model_id})
            store._update_locked(ctx.sid, {'training': {'monitorRunId': work['runId'], 'monitor': None}})
    ctx.heartbeat(1, {'phase': 'done', 'modelId': model_id, 'n': len(docs),
                      'done': completed, 'total': len(docs)})
