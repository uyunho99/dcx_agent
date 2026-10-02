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
                prep=deepcopy(session.get('prep', {})),
                training=deepcopy(session.get('training', {})),
                prepKey=session.get('prep', {}).get('derivedRef', {}).get('prepKey'),
                prompts={**(versions or {name: prompt_version(name) for name in ('tag', 'queries', 'novelty')}),
                         'dims':hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()})


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
             ref['prepKey'] != session.get('prep', {}).get('derivedRef', {}).get('prepKey'))) or
            session.get('evidence', {}).get('status') == 'stale' or 'stage6' in session.get('stale', {})):
        raise sessions.StoreError('Evidence input generation changed', 409, 'stale_run')


def check_read(sid, version, session):
    ref = read(sid, version)
    if ref and (ref['segmentRun'] != SegmentStore.open(sid, version).get_run() or
                ref['prepKey'] != session.get('prep', {}).get('derivedRef', {}).get('prepKey')):
        raise sessions.StoreError('Evidence input generation changed', 409, 'stale_run')


def check_prompts(sid, version):
    ref = read(sid, version)
    current = {name:prompt_version(name) for name in ('tag','queries','novelty')}
    current['dims'] = hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest()
    if ref and ref['prompts'] != current:
        raise sessions.StoreError('Evidence prompt generation changed; resume evidence first', 409, 'stale_run')
