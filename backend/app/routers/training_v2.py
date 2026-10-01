"""Version-aware training, saved ensembles, and stage-five exports."""
from pathlib import Path

import numpy as np
import torch
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.context import store
from app.label.overview import session, labels_for
from app.model import registry, infer, export
from app.model.train import Targets, build_targets, train_ensemble
from app.routers.labeling_v2 import LabelRoute
from app.work import runner
from app.vectors.embedder import embedder_name

router = APIRouter(route_class=LabelRoute)


class TrainBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parent: str | None = None


class ExportBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    withoutModel: bool = False


@router.get('/models')
def models(sid: str | None = None, version: str | None = None):
    embedder = (infer.embedder_for(sid, session(sid, version)) if sid else
                dict(name=settings.embed_backend, model=settings.embed_model, dim=settings.embed_dim))
    return {'models': registry.list_models(embedder)}


@router.get('/models/{model_id}')
def model(model_id: str):
    return registry.metadata(model_id)


@router.post('/train/{sid}')
def start(sid: str, body: TrainBody = TrainBody(), version: str | None = None):
    with store.locked(sid):
        data = session(sid, version, writable=True)
        embedder = infer.embedder_for(sid, data)
        if body.parent:
            registry.require_compatible(body.parent, embedder)
            registry.dataset(body.parent)
        work = runner.start(sid, data['version'], 'train', body.model_dump())
        store._update_locked(sid, {'training': {'runId': work['runId']}})
        return work


@router.get('/train/{sid}/status')
def status(sid: str, version: str | None = None):
    data = session(sid, version)
    if store.is_legacy(data):
        return dict(readonly=True, training=data.get('training', {}))
    training = data.get('training', {})
    run_ids = {training.get(key) for key in ('runId', 'inferRunId')}
    works = runner.status(sid)
    monitor_run = next((r for r in works if r['runId'] == training.get('monitorRunId')
                        and r['kind'] == 'monitor'), None)
    monitor = training.get('monitor')
    if monitor_run:
        reason = monitor_run.get('detail', {}).get('reason') or (monitor or {}).get('reason')
        if not reason and monitor_run.get('error'):
            reason = f"감시 중 오류가 났습니다({monitor_run['error']})."
        if not reason and monitor_run['state'] in ('failed', 'interrupted'):
            reason = '감시를 완료하지 못했습니다.'
        monitor = {**(monitor or {}), **monitor_run, 'reason': reason}
    return dict(training=training, workers=[r for r in works
        if r['runId'] in run_ids and r['kind'] in ('train', 'infer')], monitor=monitor,
        stage5=store.read_json((Path(settings.local_data_dir) / training['stage5Ref'])
            if training.get('stage5Ref') else store.root_dir(sid) / 'versions' / data['version'] / 'stage_5.json'))


@router.post('/train/{sid}/export')
def export_session(sid: str, body: ExportBody = ExportBody(), version: str | None = None):
    return export.write(sid, version, without_model=body.withoutModel)


def _pack(X, targets):
    return dict(X=torch.as_tensor(X), values=targets.values, hard=targets.hard, masks=targets.masks,
        weights=targets.weights, doc_ids=targets.doc_ids.tolist(), grades=targets.grades.tolist(),
        channels=targets.channels.tolist())


def _unpack(data):
    return data['X'].numpy(), Targets(data['values'], data['hard'], data['masks'], data['weights'],
        np.array(data['doc_ids']), np.array(data['grades']), np.array(data['channels']))


def training_data(sid, data, parent=None):
    docs = infer.documents(sid, data)
    labels = labels_for(sid, data)
    from app.model.dataset import training_rows
    rows = training_rows(labels)
    for row in rows:
        if row['doc_id'] not in docs:
            raise store.StoreError('학습 문서를 찾을 수 없습니다.')
        row['channel'] = docs[row['doc_id']].get('channel', docs[row['doc_id']].get('source'))
    targets = build_targets(rows)
    X = infer.feature_rows(sid, data, [docs[i] for i in targets.doc_ids])
    if parent:
        registry.require_compatible(parent, infer.embedder_for(sid, data))
        old_X, old = _unpack(registry.dataset(parent))
        # Current human corrections supersede a repeated document in the parent.
        keep = np.flatnonzero(~np.isin(old.doc_ids, targets.doc_ids))
        old = old.take(keep)
        X = np.concatenate([old_X[keep], X])
        targets = Targets(*[{k: torch.cat([getattr(old, name)[k], getattr(targets, name)[k]])
            for k in getattr(old, name)} for name in ('values', 'hard', 'masks')],
            torch.cat([old.weights, targets.weights]),
            *[np.concatenate([getattr(old, name), getattr(targets, name)]) for name in ('doc_ids', 'grades', 'channels')])
    return X, targets


def run_worker(ctx):
    with store.locked(ctx.sid):
        data = session(ctx.sid, ctx.version, writable=True)
        embedder = infer.embedder_for(ctx.sid, data)
    ctx.heartbeat(0, {'phase': 'features'})
    if ctx.should_stop():
        return
    parent = ctx.args.get('parent')
    X, targets = training_data(ctx.sid, data, parent)
    ctx.heartbeat(.1, {'phase': 'train', 'members': 4, 'n': len(targets.doc_ids)})
    if ctx.should_stop():
        return
    result = train_ensemble(X, targets)
    ctx.heartbeat(.9, {'phase': 'saving', 'evaluation_split': 'validation'})
    if ctx.should_stop():
        return
    # Persist only the rows T12 actually trained, after zero-vector filtering.
    trained_ids = set(result.doc_ids)
    indices = np.array([i for i, doc_id in enumerate(targets.doc_ids) if doc_id in trained_ids], dtype=int)
    with store.locked(ctx.sid):
        session(ctx.sid, ctx.version, writable=True)
        project = data.get('projectContext', {})
        model_id = registry.save(result, dict(trainedFrom=dict(sid=ctx.sid, version=ctx.version),
            bk=project.get('bk', ''), oneLiner=project.get('oneLiner', ''), embedder=embedder, parent=parent),
            training_data=_pack(X[indices], targets.take(indices)))
        store._update_locked(ctx.sid, {'training': {'modelId': model_id,
            'embedder': embedder, 'embedderName': embedder_name(embedder),
            'metrics': registry.metadata(model_id)['metrics']}})
        work = runner.start(ctx.sid, ctx.version, 'infer', {'modelId': model_id})
        store._update_locked(ctx.sid, {'training': {'inferRunId': work['runId'], 'inferStatus': 'running'}})
    ctx.heartbeat(1, {'phase': 'done', 'modelId': model_id})
