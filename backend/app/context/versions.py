"""Version snapshots; immutable crawl collections remain outside this tree."""
from collections import Counter
import hashlib
import os
import re
import shutil
import uuid

from app.context.store import (StoreError, root_dir, read_json, write_json, locked,
                               now, session_activities, assert_writable)


def version_dir(sid, version):
    if not re.fullmatch(r'v[1-9][0-9]*', version):
        raise StoreError('Invalid version', 400, 'validation')
    return root_dir(sid) / 'versions' / version


def active_version_dir(sid):
    meta = read_json(root_dir(sid) / 'meta.json')
    return version_dir(sid, meta['activeVersion']) if meta else root_dir(sid)


def _link(root):
    # Stable compatibility path follows meta activation through one directory link.
    link = root / 'session.json'
    if not link.is_symlink():
        link.symlink_to('active/session.json')


def _activate_link(root, version):
    tmp = root / ('.active-' + uuid.uuid4().hex)
    try:
        tmp.symlink_to(f'versions/{version}', target_is_directory=True)
        os.replace(tmp, root / 'active')
    finally:
        tmp.unlink(missing_ok=True)


def initialize(sid):
    """Called under the store lock for a new v2 session."""
    root = root_dir(sid)
    if (root / 'meta.json').exists():
        return
    version_dir(sid, 'v1').mkdir(parents=True, exist_ok=True)
    if (root / 'session.json').exists():
        os.replace(root / 'session.json', version_dir(sid, 'v1') / 'session.json')
    _activate_link(root, 'v1')
    _link(root)
    write_json(root / 'meta.json', {'activeVersion': 'v1', 'versions': [dict(id='v1', parent=None, restartFrom='stage0', createdAt=now(), note='', readonly=False)]})


def _meta(sid):
    meta = read_json(root_dir(sid) / 'meta.json')
    if not meta:
        raise StoreError('Versioned session not found', 404, 'not_found')
    return meta


def _data(sid, v):
    data = read_json(version_dir(sid, v) / 'session.json')
    if data is None:
        raise StoreError('Version not found', 404, 'not_found')
    return data


def _idle(sid, data):
    running = any((r.get('job') or {}).get('status') == 'running' for r in data.get('keywordRounds', {}).values())
    if running or any(a['status'] == 'running' for a in session_activities(sid, data)):
        raise StoreError('진행 중인 작업이 끝난 뒤 다시 시도하세요')


CRAWL_UNFINISHED_MESSAGE = '크롤링 수집을 끝낸 뒤 새 버전을 만드세요.'


def _crawl_phase(sid, collection_id):
    if not collection_id:
        return 'none'
    from app.crawl.control import phase_state
    return phase_state(sid, collection_id)


def create_version(sid, from_v, restart_from, note, version=None) -> str:
    if not re.fullmatch(r'stage[0-9]+', restart_from):
        raise StoreError('Invalid restartFrom', 400, 'validation')
    with locked(sid):
        if version is not None:
            assert_writable(sid, version)
        meta = _meta(sid)
        data = _data(sid, from_v)
        # D-091: inspect the source collection before any copy or activation.
        if _crawl_phase(sid, data.get('collectionId')) in ('running', 'unfinished'):
            raise StoreError(CRAWL_UNFINISHED_MESSAGE)
        _idle(sid, _data(sid, meta['activeVersion']))
        _idle(sid, data)
        v = f"v{max(int(e['id'][1:]) for e in meta['versions']) + 1}"
        target = version_dir(sid, v)
        previous_active = meta['activeVersion']
        activated = False
        try:
            shutil.copytree(version_dir(sid, from_v), target)
            data.update(version=v, parentVersion=from_v, restartFrom=restart_from, updatedAt=now())
            stale = data.setdefault('stale', {})
            last_stage = max([6, int(restart_from[5:])] + [int(key[5:]) for key in stale.keys() | data.get('stageResults', {}).keys() if re.fullmatch(r'stage[0-9]+', key)])
            for stage in range(int(restart_from[5:]), last_stage + 1):
                stale[f'stage{stage}'] = f'{restart_from} changed in {v}'
            if int(restart_from[5:]) <= 1:
                for round_data in data.get('keywordRounds', {}).values():
                    round_data['needsRegeneration'] = True
            write_json(target / 'session.json', data)
            for entry in meta['versions']:
                entry['readonly'] = True
            meta['versions'].append(dict(id=v, parent=from_v, restartFrom=restart_from, createdAt=now(), note=note, readonly=False))
            meta['activeVersion'] = v
            _activate_link(root_dir(sid), v)
            activated = True
            write_json(root_dir(sid) / 'meta.json', meta)
        except Exception:
            if activated:
                _activate_link(root_dir(sid), previous_active)
            if target.exists():
                shutil.rmtree(target)
            raise
        return v


def set_active(sid, v, version=None):
    with locked(sid):
        if version is not None:
            assert_writable(sid, version)
        meta = _meta(sid)
        _data(sid, v)
        _idle(sid, _data(sid, meta['activeVersion']))
        _idle(sid, _data(sid, v))
        entry = next((entry for entry in meta['versions'] if entry['id'] == v), None)
        if entry is None or entry['readonly']:
            raise StoreError('읽기 전용 버전은 활성화할 수 없습니다. 복원하려면 새 버전을 만드세요')
        previous_active = meta['activeVersion']
        meta['activeVersion'] = v
        _activate_link(root_dir(sid), v)
        try:
            write_json(root_dir(sid) / 'meta.json', meta)
        except Exception:
            _activate_link(root_dir(sid), previous_active)
            raise


def list_versions(sid):
    with locked(sid):
        meta = _meta(sid)
        return {**meta, 'versions': [{**entry, 'collectionId': _data(sid, entry['id']).get('collectionId')} for entry in meta['versions']]}


def compare(sid, a, b, stage) -> dict:
    with locked(sid):
        before, after = _data(sid, a), _data(sid, b)
        if stage == 'stage0':
            left, right = before.get('projectContext', {}), after.get('projectContext', {})
            return {key: {'before': left.get(key), 'after': right.get(key)} for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)}
        if stage == 'stage1':
            left = {k.get('id', k.get('text')): k for k in before.get('keywords', [])}
            right = {k.get('id', k.get('text')): k for k in after.get('keywords', [])}
            old = Counter(k.get('axis') for k in left.values())
            new = Counter(k.get('axis') for k in right.values())
            return dict(added=[k for key, k in right.items() if key not in left],
                        removed=[k for key, k in left.items() if key not in right],
                        moved=[{'id': key, 'from': left[key].get('axis'), 'to': k.get('axis')} for key, k in right.items() if key in left and left[key].get('axis') != k.get('axis')],
                        distribution={key: new[key] - old[key] for key in sorted(old.keys() | new.keys(), key=str)})
        if stage == 'stage2':
            if before.get('collectionId') == after.get('collectionId'):
                return {'same': True}
            def counts(data):
                cid = data.get('collectionId')
                if not cid:
                    return {}
                if not re.fullmatch(r'[A-Za-z0-9_-]+', cid):
                    raise StoreError('Invalid collection id', 400, 'validation')
                report = read_json(root_dir(sid).parents[1] / 'crawl' / sid / 'collections' / cid / 'report.json') or {}
                return report.get('counts', {})
            left, right = counts(before), counts(after)
            delta = {kw: {channel: right.get(kw, {}).get(channel, 0) - left.get(kw, {}).get(channel, 0)
                          for channel in sorted(left.get(kw, {}).keys() | right.get(kw, {}).keys())}
                     for kw in sorted(left.keys() | right.keys())}
            return {'same': False, 'before': before.get('collectionId'), 'after': after.get('collectionId'), 'counts': delta}
        if not re.fullmatch(r'stage[0-9]+', stage):
            raise StoreError('Invalid stage', 400, 'validation')
        def files(v):
            base = version_dir(sid, v) / stage
            return {str(p.relative_to(base)): {'hash': hashlib.sha256(p.read_bytes()).hexdigest(), 'savedAt': p.stat().st_mtime} for p in base.rglob('*') if p.is_file()}
        left, right = files(a), files(b)
        return {'same': {k: v['hash'] for k, v in left.items()} == {k: v['hash'] for k, v in right.items()}, 'before': left, 'after': right}
