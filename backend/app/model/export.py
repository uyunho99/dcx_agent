"""Stage-five writer and exact-file exports consumed by subsequent stages."""
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from app.config import settings

from app.context.stale import clear_stale
from app.context import store
from app.label import report, rule
from app.label.overview import labels_for, session
from app.model import infer, registry


def _label_entropy(label):
    if label['source'] != 'agreed':
        return 0.
    votes = json.loads(label['votes_json'])
    if not votes.get('jev') or not votes.get('gpt'):
        return 0.
    gpt = votes['gpt']
    gpt_tags = dict(anchor=gpt['anchor'], situation=gpt['situation'], **gpt['sem'])
    # D-130 soft labels retain uncertainty without changing exported tagProbs.
    soft = {tag: (votes['jev']['probs'][tag] + gpt_tags[tag]) / 2
            for tag in rule.GRADE_FIELDS}
    grades = rule.grade_probs(soft)
    return -sum(p * math.log(p) for p in grades.values() if p > 0)


def write_stage5(sid, data, model=None, *, generation=None):
    """The only stage_5.json writer. Caller holds the session lock."""
    result = report.label_part(sid)
    monitor = data.get('training', {}).get('monitor', {})
    result.update(model=model, monitorDivergence=monitor.get('monitorDivergence'),
                  monitor=monitor or None)
    key = f"sessions/{sid}/versions/{data['version']}/stage_5.json"
    if generation is not None:
        store.write_json(generation / 'stage_5.json', result)
    else:
        store.write_json(Path(settings.local_data_dir) / key, result)
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
            prediction = predictions.get(doc_id)
            unavailable = bool(model_id) and (prediction is None or prediction['invalid_vector'])
            if label and (label['source'] == 'human' or not model_id or unavailable):
                if label['source'] != 'human' and label['route'] not in ('accepted', 'audited'):
                    raise store.StoreError('사람 검수를 먼저 완료하세요.')
                tags = json.loads(label['tags_json'])
                probs = dict(anchor=float(tags['anchor']), situation=float(tags['situation']),
                             **{k: float(v) for k, v in tags['sem'].items()})
                values = dict(evidence_level_pred=label['level'], confidence=label['confidence'],
                    pred_entropy=_label_entropy(label), relevance_score=float(label['level'] != 'non'), tagProbs=probs,
                    signal=label['signal'], source=label['source'])
                if unavailable:
                    values.update(prediction='unavailable', pred_entropy=None,
                                  relevance_score=None, tagProbs=None)
            elif model_id and not unavailable:
                pred = json.loads(prediction['payload'])
                values = dict(evidence_level_pred=pred['level'], confidence=pred['confidence'],
                    pred_entropy=pred['predEntropy'], relevance_score=pred['relevanceScore'],
                    tagProbs=pred['tagProbs'], signal=pred['signal'] if pred['level'] != 'non' else None,
                    source='model')
            else:
                raise store.StoreError('모든 문서의 판정 또는 추론을 먼저 완료하세요.')
            rows.append({**doc, 'title': doc.get('title') or '',
                'desc': doc.get('desc') or doc.get('body') or doc.get('text') or '',
                'cafe': doc.get('cafe') or '', 'kw': doc.get('kw') or '', **values,
                'rule_version': rule.RULE_VERSION, 'modelId': None if unavailable else model_id})
        base = f"classified/{sid}/{data['version']}/gen-{uuid4().hex}"
        generation = Path(settings.local_data_dir) / base
        generation.mkdir(parents=True, exist_ok=False)
        relevant = [r for r in rows if r['evidence_level_pred'] in ('core', 'supporting')]
        for name, items in (('all.jsonl', rows), ('relevant.jsonl', relevant)):
            store.atomic_write(generation / name, ''.join(
                json.dumps(row, ensure_ascii=False) + '\n' for row in items))
        model = None if meta is None else {key: meta[key] for key in ('modelId', 'kind', 'perHead', 'metrics')}
        stage = write_stage5(sid, data, model, generation=generation)
        # atomic_write fsyncs each file and its directory. Persist the new
        # generation's ancestor directory entries before publishing the pointer.
        for directory in (generation.parent, generation.parent.parent, generation.parent.parent.parent):
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        ref = base + '/relevant.jsonl'
        store._update_locked(sid, {'training': {'exportRef': ref, 'allRef': base + '/all.jsonl', 'stage5Ref': base + '/stage_5.json', 'exportedAt': store.now()}})
        # Compatibility report is atomic too; authoritative exported artifacts
        # remain together under stage5Ref/exportRef. Retain generations because
        # historical versions may still point to them.
        store.write_json(store.session_dir(sid) / 'stage_5.json', stage)
        clear_stale(sid, data['version'], 'stage5', already_locked=True)
        return dict(exportRef=ref, allRef=base + '/all.jsonl', total=len(rows), relevant=len(relevant), stage5=stage)
