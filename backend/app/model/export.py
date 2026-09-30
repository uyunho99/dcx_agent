"""Stage-five writer and exact-file exports consumed by subsequent stages."""
import json

from app.context import store
from app.label import report, rule
from app.label.overview import labels_for, session
from app.model import infer, registry
from app.services import s3


def write_stage5(sid, data, model=None):
    """The only stage_5.json writer. Caller holds the session lock."""
    result = report.label_part(sid)
    monitor = data.get('training', {}).get('monitor', {})
    result.update(model=model, monitorDivergence=monitor.get('monitorDivergence'),
                  monitor=monitor or None)
    key = f"sessions/{sid}/versions/{data['version']}/stage_5.json"
    s3.save_json(key, result)
    return result


def write(sid, version=None, *, without_model=False):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        labels = labels_for(sid, data)
        infer.refresh_predictions(labels)
        docs = infer.documents(sid, data)
        model_id = None if without_model else (data.get('training', {}).get('modelId') or
            (data.get('labeling', {}).get('modelId') if data.get('labeling', {}).get('mode') == 'model' else None))
        meta = registry.require_compatible(model_id, infer.embedder_for(sid, data)) if model_id else None
        with labels._db() as db:
            if db.execute("SELECT 1 FROM queue WHERE status='open' LIMIT 1").fetchone():
                raise store.StoreError('사람 검수를 먼저 완료하세요.')
            final = {r['doc_id']: dict(r) for r in db.execute('SELECT * FROM final')}
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='model_predictions'").fetchone()
            predictions = {r['doc_id']: dict(r) for r in db.execute(
                'SELECT * FROM model_predictions WHERE model_id=?', (model_id,))} if exists and model_id else {}
        rows = []
        for doc_id, doc in docs.items():
            label = final.get(doc_id)
            if label and (label['source'] == 'human' or not model_id):
                if label['source'] != 'human' and label['route'] != 'accepted':
                    raise store.StoreError('사람 검수를 먼저 완료하세요.')
                tags = json.loads(label['tags_json'])
                probs = dict(anchor=float(tags['anchor']), situation=float(tags['situation']),
                             **{k: float(v) for k, v in tags['sem'].items()})
                values = dict(evidence_level_pred=label['level'], confidence=label['confidence'],
                    pred_entropy=0., relevance_score=float(label['level'] != 'non'), tagProbs=probs,
                    signal=label['signal'], source=label['source'])
            elif model_id and doc_id in predictions:
                if predictions[doc_id]['invalid_vector']:
                    raise store.StoreError('임베딩 실패 또는 미학습 헤드가 있는 문서를 먼저 검수하세요.')
                pred = json.loads(predictions[doc_id]['payload'])
                values = dict(evidence_level_pred=pred['level'], confidence=pred['confidence'],
                    pred_entropy=pred['predEntropy'], relevance_score=pred['relevanceScore'],
                    tagProbs=pred['tagProbs'], signal=pred['signal'] if pred['level'] != 'non' else None,
                    source='model')
            else:
                raise store.StoreError('모든 문서의 판정 또는 추론을 먼저 완료하세요.')
            rows.append({**doc, 'title': doc.get('title') or '',
                'desc': doc.get('desc') or doc.get('body') or doc.get('text') or '',
                'cafe': doc.get('cafe') or '', 'kw': doc.get('kw') or '', **values,
                'rule_version': rule.RULE_VERSION, 'modelId': model_id})
        base = f"classified/{sid}/{data['version']}"
        relevant = [r for r in rows if r['evidence_level_pred'] in ('core', 'supporting')]
        s3.save_jsonl(base + '/all.jsonl', rows)
        s3.save_jsonl(base + '/relevant.jsonl', relevant)
        model = None if meta is None else {key: meta[key] for key in ('modelId', 'kind', 'perHead', 'metrics')}
        stage = write_stage5(sid, data, model)
        ref = base + '/relevant.jsonl'
        store._update_locked(sid, {'training': {'exportRef': ref, 'allRef': base + '/all.jsonl', 'exportedAt': store.now()}})
        return dict(exportRef=ref, allRef=base + '/all.jsonl', total=len(rows), relevant=len(relevant), stage5=stage)
