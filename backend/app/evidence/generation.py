"""Captured inputs for an evidence generation, including immutable cache refs."""
from copy import deepcopy
import hashlib
from app.segment import dims

from app.context import store as sessions
from app.context.versions import version_dir
from app.evidence.cache import prompt_version
from app.segment.store import SegmentStore


def capture(sid, version, session, *, versions=None):
    return dict(segmentRun=SegmentStore.open(sid, version).get_run(),
                prep=deepcopy({key: session.get('prep', {}).get(key) for key in ('status', 'derivedRef')}),
                training=deepcopy({key: session.get('training', {}).get(key) for key in ('exportRef', 'modelId')}),
                prepKey=session.get('prep', {}).get('derivedRef', {}).get('prepKey'),
                prompts={**(versions or {name: prompt_version(name) for name in ('tag', 'queries', 'novelty')}),
                         'dims':hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()})


def input_refs(snapshot):
    """Compare immutable inputs, including older snapshots with full UI state."""
    derived = snapshot.get('prep', {}).get('derivedRef') or {}
    training = snapshot.get('training', {})
    return (derived.get('collectionId'), derived.get('prepKey'),
            training.get('exportRef'), training.get('modelId'))


def equivalent(previous, current):
    # Pre-snapshot runs retain their completed Contexts; normal stale checks
    # still force a fresh run when upstream stages invalidate those results.
    return previous is None or (previous['segmentRun'] == current['segmentRun'] and
                               input_refs(previous) == input_refs(current) and
                               previous['prompts'] == current['prompts'])


def read(sid, version):
    return sessions.read_json(version_dir(sid, version) / 'evidence/generation.json')


def inputs(sid, version, session):
    ref = read(sid, version)
    if not ref:
        return session, prompt_version('tag')
    return {**session, 'prep':ref['prep'], 'training':ref['training']}, ref['prompts']['tag']


def check(sid, version, ev, run=None):
    session = sessions.assert_writable(sid, version)
    ref = read(sid, version)
    if ((run is not None and ev.get_run() != run) or
            (ref and (ref['segmentRun'] != SegmentStore.open(sid, version).get_run() or
             input_refs(ref) != input_refs(session))) or
            session.get('evidence', {}).get('status') == 'stale' or 'stage6' in session.get('stale', {})):
        raise sessions.StoreError('Evidence input generation changed', 409, 'stale_run')


def check_read(sid, version, session):
    ref = read(sid, version)
    if ref and (ref['segmentRun'] != SegmentStore.open(sid, version).get_run() or
                input_refs(ref) != input_refs(session)):
        raise sessions.StoreError('Evidence input generation changed', 409, 'stale_run')


def check_prompts(sid, version):
    ref = read(sid, version)
    current = {name:prompt_version(name) for name in ('tag','queries','novelty')}
    current['dims'] = hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()
    if ref and ref['prompts'] != current:
        raise sessions.StoreError('근거 프롬프트가 바뀌었습니다. 이어서 진행을 눌러 다시 계산하세요.', 409, 'stale_run')
