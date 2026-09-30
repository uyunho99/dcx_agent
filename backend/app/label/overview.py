"""Version-local labeling overview, source indexing, and progress aggregation."""
from datetime import datetime
from functools import lru_cache
import sqlite3
import json

from app.config import settings
from app.context import store, versions
from app.label import audit, judge
from app.label.route import sync as rebuild_queue, next_item
from app.label.store import LabelStore
from app.label.votes import VoteCache
from app.work import runner

LEGACY_MESSAGE = '구버전 세션은 새 라벨링을 쓸 수 없습니다. 기존 결과만 볼 수 있습니다.'


def session(sid, version=None, writable=False):
    if writable:
        data = store.load_session(sid)
        if data is not None and store.is_legacy(data):
            raise store.StoreError(LEGACY_MESSAGE)
        return store.assert_writable(sid, version)
    data = versions._data(sid, version) if version else store.load_session(sid)
    if data is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    return data


def labels_for(sid, data):
    return LabelStore(versions.version_dir(sid, data['version']))


def caches_for(sid, data):
    ref = data.get('prep', {}).get('derivedRef')
    if not ref:
        return {}
    return {name: VoteCache(judge.cache_root(sid, ref['prepKey'], name,
                data.get('projectContext', {}).get('oneLiner', ''))) for name in ('jev', 'gpt')}


def index_documents(sid, data, labels):
    ref = data.get('prep', {}).get('derivedRef')
    if not ref:
        return
    from app.routers.prep import _root
    root = _root(sid, ref['collectionId'], ref['prepKey']) / 'docs'
    with labels._db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS document_files (path TEXT PRIMARY KEY, stamp TEXT)')
        for path in sorted(root.glob('*.jsonl')):
            stat = path.stat()
            stamp = f'{stat.st_mtime_ns}:{stat.st_size}'
            seen = db.execute('SELECT stamp FROM document_files WHERE path=?', (str(path),)).fetchone()
            if seen and seen[0] == stamp:
                continue
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    doc = json.loads(line)
                    # Only original text/source metadata is safe on a blind card.
                    public = {key: doc[key] for key in ('doc_id', 'text', 'title', 'body', 'content', 'url', 'channel') if key in doc}
                    if 'comments' in doc:
                        public['comments'] = [{'text': c.get('text', '')} for c in doc['comments']]
                    db.execute('INSERT OR REPLACE INTO documents VALUES (?,?)',
                               (doc['doc_id'], json.dumps(public, ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO document_files VALUES (?,?)', (str(path), stamp))


@lru_cache(maxsize=128)
def _estimate(path, labeler, counts, context, stamp):
    # Only deserialize the corpus on an estimate cache miss, never for worker ETAs.
    with sqlite3.connect(path) as db:
        docs = [json.loads(row[0]) for row in db.execute('SELECT payload FROM documents')]
    result = judge.estimate(docs, context, labeler)
    total = sum(counts)
    if total and result['seconds'] is not None:
        result['seconds'] *= counts[0] / total
    return result


def now_card(started, progress, definition, queue_count, audit_pending):
    if not started:
        return dict(state='before_start', priority=0, message='라벨링을 시작하세요', action='라벨링 시작')
    stopped = next((p for p in progress.values() if p['state'] in ('paused', 'failed', 'interrupted')), None)
    if stopped:
        return dict(state='paused', priority=1, message=stopped.get('reason') or '판정이 멈췄습니다', action='이어서 진행')
    if definition['needed']:
        return dict(state='definition_check', priority=2, message=definition['reason'], action='태그 정의 보기')
    if queue_count:
        return dict(state='review', priority=3, message=f'사람이 볼 문서가 {queue_count}건 있습니다', action='검수 시작')
    if audit_pending:
        return dict(state='audit', priority=4, message='채택 라벨을 확인하세요', action='감사 시작')
    if any(p['state'] == 'running' or p['pending'] for p in progress.values()):
        return dict(state='running', priority=5, message='판정 중입니다', action=None)
    return dict(state='done', priority=6, message='라벨링이 끝났습니다', action='학습으로')


def overview(sid, version=None, *, sync=True) -> dict:
    """Read version metrics without taking or writing the session lock."""
    data = session(sid, version)
    if store.is_legacy(data):
        return dict(legacy=True, readonly=True, message=LEGACY_MESSAGE,
                    legacyLabels=[{**row, 'anchor': bool(row['label'])} for row in data.get('labeledData', [])])
    labeling = data.get('labeling', {})
    labels = labels_for(sid, data)
    caches = caches_for(sid, data)
    if sync:
        rebuild_queue(labels, caches.get('jev'), caches.get('gpt'))
        index_documents(sid, data, labels)
    else:
        from app.label.route import schema
        schema(labels)
    with labels._db() as db:
        accepted = db.execute("SELECT count(*) FROM final WHERE route='accepted'").fetchone()[0]
    with labels._db() as db:
        rounds = [row[0] for row in db.execute('SELECT DISTINCT round FROM audit_set ORDER BY round')]
    history = []
    for r in rounds:
        metric = audit.kappa_ai(labels, r)
        with labels._db() as db:
            picked = db.execute('SELECT MIN(picked_at) FROM audit_set WHERE round=?', (r,)).fetchone()[0]
        history.append(dict(round=r, n=metric['n'], kappaAI=metric, at=picked))
    accuracy = audit.labeler_accuracy(labels)
    consistency = audit.self_consistency(labels)
    consistency['agree'] = consistency['accuracy']
    definition = audit.definition_signal([r['kappaAI'] for r in history])
    with labels._db() as db:
        accuracy['n'] = db.execute("SELECT count(DISTINCT doc_id) FROM audit_snapshot s WHERE EXISTS (SELECT 1 FROM human h WHERE h.doc_id=s.doc_id AND h.mode='audit' AND h.rowid>s.human_floor)").fetchone()[0]
        total = db.execute('SELECT count(*) FROM final').fetchone()[0]
        merged = db.execute("SELECT count(*) FROM label_events WHERE kind='merged'").fetchone()[0]
        accepted = db.execute("SELECT count(*) FROM final WHERE route='accepted'").fetchone()[0]
        distribution = dict.fromkeys(('core', 'supporting', 'non'), 0)
        distribution.update(dict(db.execute('SELECT level, count(*) FROM final GROUP BY level')))
        reasons = dict.fromkeys(('labeler_failed', 'grade_mismatch'), 0)
        reasons.update(dict(db.execute("SELECT reason, count(*) FROM queue WHERE status='open' GROUP BY reason")))
        average = db.execute("SELECT avg(elapsed) FROM review_done WHERE mode='escalate' AND elapsed IS NOT NULL").fetchone()[0] or 10
        since = labeling.get('prevSeenAt', labeling.get('lastSeenAt'))
        timestamp = datetime.fromisoformat(since).timestamp() if since else 0
        changes = dict.fromkeys(('merged', 'accepted', 'queued'), 0)
        changes.update(dict(db.execute('SELECT kind, count(*) FROM label_events WHERE at>? GROUP BY kind', (timestamp,))))
        files = db.execute("SELECT 1 FROM sqlite_master WHERE name='document_files'").fetchone()
        stamp = tuple(db.execute('SELECT path, stamp FROM document_files ORDER BY path').fetchall()) if files else ()
        stamp = tuple(tuple(row) for row in stamp)
    changes['judged'] = 0
    for cache in caches.values():
        with cache._db() as db:
            changes['judged'] += db.execute("SELECT count(*) FROM votes WHERE status IN ('done','bad') AND at>?", (timestamp,)).fetchone()[0]
    work = {row['runId']: row for row in runner.status(sid)}
    progress = {}
    for name in ('jev', 'gpt'):
        counts = caches[name].counts() if name in caches else dict(done=0, pending=0, bad=0)
        run = work.get(labeling.get('judgeRuns', {}).get(name), {})
        detail = run.get('detail', {})
        estimate = detail.get('estimate')
        if estimate is None:
            estimate = dict(_estimate(str(labels.path), name, tuple(counts[k] for k in ('pending', 'done', 'bad')),
                                      data.get('projectContext', {}).get('oneLiner', ''), stamp))
        count = sum(counts.values())
        progress[name] = dict(**counts, state=run.get('state', 'done' if count and not counts['pending'] else 'none'),
                              progress=run.get('progress', (counts['done']+counts['bad'])/count if count else 0),
                              estimate=estimate, reason=detail.get('reason'), runId=run.get('runId'))
    queue_count = sum(reasons.values())
    pending = next_item(labels, 'audit') is not None or next_item(labels, 'reissue') is not None
    from app.model.dataset import trainable_count
    result = dict(trainable=trainable_count(sid, data, labels), mode=labeling.get('mode', 'llm'), modelId=labeling.get('modelId'), started=labeling.get('started', False),
                  merged=merged, total=total, accepted=accepted, escalated=queue_count,
                  mismatchRate=queue_count / merged if merged else 0,
                  levelDistribution=distribution, queue=dict(total=queue_count, byReason=reasons, estimatedSeconds=queue_count * average),
                  labelerAccuracy=accuracy, selfConsistency=consistency, definitionCheck=definition,
                  progress=progress, audit=history, changes=changes,
                  lastSeenAt=labeling.get('lastSeenAt'), prevSeenAt=since)
    result['now'] = now_card(result['started'], progress, definition, queue_count, pending)
    if result['now']['state'] == 'review':
        result['now']['estimatedSeconds'] = queue_count * average
    return result
