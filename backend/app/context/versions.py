"""Version snapshots; immutable crawl collections remain outside this tree."""
from collections import Counter
from contextlib import closing
import hashlib
import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path
import uuid

from app.context.store import (StoreError, root_dir, read_json, write_json, locked,
                               now, session_activities, assert_writable)


logger = logging.getLogger(__name__)


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
    if running or any(a['status'] == 'running' and a['kind'] != 'monitor'
                      for a in session_activities(sid, data)):
        raise StoreError('진행 중인 작업이 끝난 뒤 다시 시도하세요')


def _stop_readonly_workers(sid, version):
    from app.work.status import database_path, transaction

    if not database_path(sid).exists():
        return
    with transaction(sid) as db:
        # Publish both the durable terminal state and the cooperative stop
        # request atomically; workers must not resume against this snapshot.
        db.execute('''UPDATE runs SET action='stop', state='interrupted'
            WHERE version=? AND kind IN ('judge','infer') AND state='paused' ''',
            (version,))
        db.execute('''UPDATE runs SET action='stop'
            WHERE version=? AND kind='monitor' AND state IN ('running','paused')''',
            (version,))


CRAWL_UNFINISHED_MESSAGE = '크롤링 수집을 끝낸 뒤 새 버전을 만드세요.'


def _crawl_phase(sid, collection_id):
    if not collection_id:
        return 'none'
    from app.crawl.control import phase_state
    return phase_state(sid, collection_id)


def _copy_file(source, target):
    """SQLite owns the snapshot boundary; never copy its live WAL sidecars."""
    if Path(source).suffix != '.sqlite':
        return shutil.copy2(source, target)
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    return target


def _restart_labels(target):
    path = target / 'labels.sqlite'
    if not path.exists():
        return
    with closing(sqlite3.connect(path)) as db, db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # Preserve the stale projection for inspection, without letting old rows
        # suppress cache reconciliation or completed reviews suppress new review.
        for table in ('final', 'queue'):
            if table in tables:
                db.execute(f'DROP TABLE IF EXISTS stale_{table}')
                db.execute(f'CREATE TABLE stale_{table} AS SELECT * FROM {table}')
        for table in ('final', 'queue', 'route_sync', 'review_done', 'audit_set',
                      'audit_snapshot', 'audit_reissue', 'label_events',
                      'model_predictions', 'inference_context'):
            if table in tables:
                db.execute(f'DELETE FROM {table}')


def _restart(data, target, stage):
    # Reports describe completed stages; copied reports cannot represent a
    # restarted stage even when reusable inputs remain in the new version.
    for number in (3, 5):
        if stage <= number:
            (target / f'stage_{number}.json').unlink(missing_ok=True)
    if stage <= 3 and 'prep' in data:
        data['prep']['status'] = 'stale'
    if stage <= 4:
        _restart_labels(target)
        if 'labeling' in data:
            previous = data['labeling']
            data['labeling'] = {key: previous[key] for key in ('mode', 'modelId', 'judgeRefs') if key in previous}
            data['labeling'].update(started=False, status='stale',
                restartMessage=f"이 라벨은 {data['parentVersion']} 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.")
    if stage <= 5 and 'training' in data:
        data['training'] = {'status': 'stale'}
    if stage <= 6:
        shutil.rmtree(target / 'segment', ignore_errors=True)
        data['segment'] = {'status': 'stale'}
        data.get('completion', {}).pop('segmentDone', None)
        data.get('drafts', {}).pop('segment', None)
    if stage <= 7:
        shutil.rmtree(target / 'evidence', ignore_errors=True)
        if 'evidence' in data:
            data['evidence'] = {'status': 'stale'}
    if stage <= 8:
        shutil.rmtree(target / 'persona', ignore_errors=True)
        for key in ('persona', 'insight'):
            if key in data:
                data[key] = {'status': 'stale'}


def create_version(sid, from_v, restart_from, note, version=None) -> str:
    if not re.fullmatch(r'stage[0-9]+', restart_from):
        raise StoreError('Invalid restartFrom', 400, 'validation')
    with locked(sid):
        if version is not None:
            assert_writable(sid, version)
        meta = _meta(sid)
        data = _data(sid, from_v)
        # D-091: inspect the source collection before any copy or activation.
        crawl_phase = _crawl_phase(sid, data.get('collectionId'))
        if crawl_phase in ('running', 'unfinished'):
            raise StoreError(CRAWL_UNFINISHED_MESSAGE)
        _idle(sid, _data(sid, meta['activeVersion']))
        _idle(sid, data)
        v = f"v{max(int(e['id'][1:]) for e in meta['versions']) + 1}"
        target = version_dir(sid, v)
        previous_active = meta['activeVersion']
        activated = False
        try:
            shutil.copytree(version_dir(sid, from_v), target, copy_function=_copy_file,
                            ignore=shutil.ignore_patterns('*.sqlite-wal', '*.sqlite-shm', '*.sqlite-journal'))
            if crawl_phase == 'gate':
                data['collectionId'] = None
                crawl_draft = (data.get('drafts') or {}).get('crawl')
                if isinstance(crawl_draft, dict):
                    crawl_draft.pop('gate', None)
            data.update(version=v, parentVersion=from_v, restartFrom=restart_from, updatedAt=now())
            stale = data.setdefault('stale', {})
            last_stage = max([8, int(restart_from[5:])] + [int(key[5:]) for key in stale.keys() | data.get('stageResults', {}).keys() if re.fullmatch(r'stage[0-9]+', key)])
            for stage in range(int(restart_from[5:]), last_stage + 1):
                stale[f'stage{stage}'] = f'{restart_from} changed in {v}'
            if int(restart_from[5:]) <= 1:
                for round_data in data.get('keywordRounds', {}).values():
                    round_data['needsRegeneration'] = True
            _restart(data, target, int(restart_from[5:]))
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
        # Stop only after activation commits, outside its rollback boundary.
        try:
            _stop_readonly_workers(sid, previous_active)
        except Exception as exc:
            # Activation is committed; cleanup failure must not imply rollback.
            logger.warning('Could not stop read-only workers for %s/%s (%s)',
                           sid, previous_active, type(exc).__name__)
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
        if stage in ('stage3', 'stage4', 'stage5'):
            def metrics(data, v, name):
                local = read_json(version_dir(sid, v) / f'{name}.json')
                if local is not None or name != 'stage_3':
                    return local
                if data.get('prep', {}).get('status') == 'stale':
                    return None
                from app.known.store import prepared_root
                root = prepared_root(sid, data)
                return read_json(root / 'stage_3.json') if root else None
            names = ('stage_3', 'stage_5') if stage == 'stage3' else ('stage_5',)
            result = {name: {'before': metrics(before, a, name), 'after': metrics(after, b, name)} for name in names}
            result['same'] = all(value['before'] == value['after'] for value in result.values())
            return result
        if not re.fullmatch(r'stage[0-9]+', stage):
            raise StoreError('Invalid stage', 400, 'validation')
        def files(v):
            base = version_dir(sid, v) / stage
            return {str(p.relative_to(base)): {'hash': hashlib.sha256(p.read_bytes()).hexdigest(), 'savedAt': p.stat().st_mtime} for p in base.rglob('*') if p.is_file()}
        left, right = files(a), files(b)
        return {'same': {k: v['hash'] for k, v in left.items()} == {k: v['hash'] for k, v in right.items()}, 'before': left, 'after': right}
