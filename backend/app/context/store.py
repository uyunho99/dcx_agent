"""Local session storage. All mutations serialize on the session root .lock."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

from app.config import settings


class StoreError(Exception):
    def __init__(self, message, status=409, kind='conflict'):
        super().__init__(message)
        self.status, self.kind = status, kind


def now():
    return datetime.now(timezone.utc).isoformat()


def root_dir(sid):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
        raise StoreError('Invalid session id', 400, 'validation')
    return Path(settings.local_data_dir) / 'sessions' / sid


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


@contextmanager
def locked(sid):
    root = root_dir(sid)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield root
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.tmp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


def session_dir(sid) -> Path:
    from app.context.versions import active_version_dir
    return active_version_dir(sid)


def load_session(sid) -> dict | None:
    return read_json(session_dir(sid) / 'session.json')


def is_legacy(session) -> bool:
    return 'schemaVersion' not in session


def deep_merge(current, patch):
    result = deepcopy(current)
    for key, value in patch.items():
        result[key] = deep_merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def assert_writable(sid, version=None):
    data = load_session(sid)
    if data is None:
        raise StoreError('Session not found', 404, 'not_found')
    if is_legacy(data):
        raise StoreError('구버전 세션은 0~2단계를 편집할 수 없습니다')
    meta = read_json(root_dir(sid) / 'meta.json')
    if meta:
        if version is not None and version != meta['activeVersion']:
            raise StoreError('다른 버전이 활성화되었습니다')
        selected = version or meta['activeVersion']
        entry = next((v for v in meta['versions'] if v['id'] == selected), None)
        if not entry or selected != meta['activeVersion'] or entry['readonly']:
            raise StoreError('읽기 전용 버전입니다')
    return data


def update_session(sid, patch: dict, confirm_stage=None) -> dict:
    """Only an explicit stage confirmation clears that stage stale marker.

    Crawl list creation passes confirm_stage="stage2"; configuration/gate and
    background writes omit it. _update_locked has the same contract.
    """
    with locked(sid):
        return _update_locked(sid, patch, confirm_stage=confirm_stage)


def _update_locked(sid, patch, confirm_stage=None):
    """Caller must hold locked(sid); used to keep API validation and writes together."""
    root = root_dir(sid)
    previous = load_session(sid) or {}
    result = deep_merge(previous, patch)
    if result.get('schemaVersion') == 2:
        from app.context.versions import initialize
        initialize(sid)
        meta = read_json(root / 'meta.json')
        if next(v for v in meta['versions'] if v['id'] == meta['activeVersion'])['readonly']:
            raise StoreError('읽기 전용 버전입니다')
        result['version'] = meta['activeVersion']
        result['updatedAt'] = now()
        if confirm_stage is not None:
            result.get('stale', {}).pop(confirm_stage, None)
        if 'projectContext' in patch:
            from app.context.models import ProjectContext
            from app.context.render import render_context_md
            ctx = ProjectContext.model_validate(result['projectContext'])
            known = [item['text'] if isinstance(item, dict) else item for item in result.get('knownInsights', ctx.knownInsights)]
            atomic_write(session_dir(sid) / 'project_context.md', render_context_md(ctx, known))
    write_json(session_dir(sid) / 'session.json', result)
    return result


def session_activities(sid, data):
    candidates = []
    for number, round_data in data.get('keywordRounds', {}).items():
        job = round_data.get('job') or {}
        if job.get('status') in {'running', 'failed', 'interrupted', 'paused_blocked'}:
            candidates.append(dict(kind=f'keyword_round_{number}', status=job['status'],
                                   progress=job.get('progress'), updatedAt=job.get('updatedAt')))
    try:
        from app.crawl.control import activity
    except ImportError:
        activity = None
    if activity:
        crawl = activity(sid)
        if crawl:
            candidates.append(crawl)
    from app.work import runner
    names = {'prep': '전처리 중', 'train': '학습 중', 'infer': '추론 중', 'monitor': '감시 중'}
    for run in runner.status(sid):
        state = run['state']
        if state not in {'running', 'paused', 'interrupted', 'failed'}:
            continue
        kind = run['kind']
        progress = run.get('progress', 0)
        label = ('중단됨 · 이어서 진행' if state in {'interrupted', 'failed'} else
                 '일시 정지됨 · 이어서 진행' if state == 'paused' else
                 f'판정 {round(progress * 100)}%' if kind == 'judge' else names.get(kind, kind))
        candidates.append(dict(kind=kind, status=state, progress=progress,
                               updatedAt=run.get('heartbeatAt'), runId=run['runId'], label=label))
    return candidates


def session_activity(sid, data):
    candidates = session_activities(sid, data)
    return min(candidates, key=activity_rank) if candidates else None


def activity_rank(activity):
    status = (activity or {}).get('status')
    return 0 if status in {'interrupted', 'paused_blocked', 'blocked', 'failed'} else 1 if status == 'running' else 2
