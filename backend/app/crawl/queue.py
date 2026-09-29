"""Process-local SQLite crawl queue. Adapter objects are accepted by attributes.

Use one connection per thread/process. Register a run before claiming work.
List and URL claims are atomic; fenced workers receive LeaseLost.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from app.crawl.urls import normalize_url

HEARTBEAT_INTERVAL = 10
STALE_AFTER_S = 60


class LeaseLost(Exception):
    """The run has stopped or no longer owns the requested work."""


DDL = """
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, sid TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('list','detail')),
 pid INTEGER NOT NULL, status TEXT NOT NULL, started_at REAL NOT NULL,
 heartbeat_at REAL NOT NULL, config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS list_tasks (
 kw TEXT NOT NULL, source TEXT NOT NULL, cursor TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed')),
 fetched INTEGER NOT NULL DEFAULT 0, total_hint INTEGER,
 attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, lease_run_id TEXT,
 PRIMARY KEY(kw, source, cursor)
);
CREATE TABLE IF NOT EXISTS keyword_meta (
 kw TEXT PRIMARY KEY, kw_axis TEXT NOT NULL, kw_sub TEXT NOT NULL, kw_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS urls (
 url_norm TEXT NOT NULL, source TEXT NOT NULL, kw TEXT NOT NULL,
 kw_axis TEXT NOT NULL, kw_sub TEXT NOT NULL, snippet TEXT NOT NULL, title TEXT NOT NULL,
 date TEXT, src_meta_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','leased','done','failed','excluded','filtered')),
 lease_until REAL, lease_run_id TEXT, lease_snapshot_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, doc_count INTEGER NOT NULL DEFAULT 0, first_seen_kw_order INTEGER NOT NULL,
 fetch_level TEXT, access TEXT, retry_at REAL, filter_rule TEXT,
 exhausted INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
 UNIQUE(url_norm, source)
);
CREATE TABLE IF NOT EXISTS url_hits (
 url_norm TEXT NOT NULL, source TEXT NOT NULL, kw TEXT NOT NULL,
 kw_axis TEXT NOT NULL, kw_sub TEXT NOT NULL, kw_order INTEGER NOT NULL,
 PRIMARY KEY(url_norm, source, kw)
);
CREATE TABLE IF NOT EXISTS snapshots (
 snapshot_id TEXT PRIMARY KEY, created_at REAL NOT NULL, url_count INTEGER NOT NULL, hash TEXT NOT NULL,
 exclusion_version INTEGER NOT NULL DEFAULT 0, swept_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS snapshot_urls (
 snapshot_id TEXT NOT NULL, url_norm TEXT NOT NULL, source TEXT NOT NULL,
 PRIMARY KEY(snapshot_id, url_norm, source)
);
CREATE TABLE IF NOT EXISTS excluded_keywords (
 snapshot_id TEXT NOT NULL, kw TEXT NOT NULL, PRIMARY KEY(snapshot_id, kw)
);
CREATE INDEX IF NOT EXISTS urls_status_source ON urls(status, source);
CREATE INDEX IF NOT EXISTS list_tasks_status ON list_tasks(status);
"""


@dataclass(frozen=True)
class KwMeta:
    kw: str
    axis: str
    sub: str
    order: int


class ListItemLike(Protocol):
    url: str
    title: str
    snippet: str
    date: str | date | datetime | None
    src_meta: dict[str, Any]


@dataclass
class QueueListItem:
    url: str
    title: str = ''
    snippet: str = ''
    date: str | None = None
    src_meta: dict[str, Any] = field(default_factory=dict)
    source: str = ''
    kw: str = ''
    kw_axis: str = ''
    kw_sub: str = ''
    kw_order: int = 0


@dataclass(frozen=True)
class ListTask:
    kw: str
    source: str
    cursor: str | None
    kw_axis: str
    kw_sub: str
    kw_order: int
    fetched: int = 0
    total_hint: int | None = None
    attempts: int = 0
    last_error: str | None = None
    lease_run_id: str | None = None


@dataclass
class UrlRow:
    url_norm: str
    source: str
    kw: str
    kw_axis: str
    kw_sub: str
    kw_order: int
    title: str
    snippet: str
    date: str | None
    src_meta: dict[str, Any]
    kw_hits: list[str]
    attempts: int
    status: str
    lease_until: float | None
    lease_run_id: str | None
    doc_count: int
    last_error: str | None
    fetch_level: str | None
    access: str | None
    first_seen_kw_order: int
    exhausted: bool = False

    @property
    def url(self) -> str:
        return self.url_norm


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, Mapping) else getattr(obj, key, default)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class CrawlQueue:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self._pid = os.getpid()
        self.run_id: str | None = None
        self.connection = self._connect(self.path, readonly=False)
        self.connection.executescript(DDL)
        # Upgrade databases created by T11 before list leasing was introduced.
        with self._write() as db:
            columns = {r['name'] for r in db.execute('PRAGMA table_info(list_tasks)')}
            if 'lease_run_id' not in columns:
                db.execute('ALTER TABLE list_tasks RENAME TO old_list_tasks')
                list_ddl = DDL.split('CREATE TABLE IF NOT EXISTS list_tasks (', 1)[1].split(';', 1)[0]
                db.execute('CREATE TABLE list_tasks (' + list_ddl)
                db.execute("""INSERT INTO list_tasks
                    (kw,source,cursor,status,fetched,total_hint,attempts,last_error)
                    SELECT kw,source,cursor,status,fetched,total_hint,attempts,last_error
                    FROM old_list_tasks""")
                db.execute('DROP TABLE old_list_tasks')
                db.execute('CREATE INDEX list_tasks_status ON list_tasks(status)')
            if 'exhausted' not in {r['name'] for r in db.execute('PRAGMA table_info(urls)')}:
                db.execute('ALTER TABLE urls ADD COLUMN exhausted INTEGER NOT NULL DEFAULT 0')
            if 'lease_snapshot_id' not in {r['name'] for r in db.execute('PRAGMA table_info(urls)')}:
                db.execute('ALTER TABLE urls ADD COLUMN lease_snapshot_id TEXT')
            if 'max_attempts' not in {r['name'] for r in db.execute('PRAGMA table_info(urls)')}:
                db.execute('ALTER TABLE urls ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(snapshots)')}
            if 'exclusion_version' not in columns:
                db.execute('ALTER TABLE snapshots ADD COLUMN exclusion_version INTEGER NOT NULL DEFAULT 0')
            if 'swept_version' not in columns:
                # Existing snapshots need one repair sweep for legacy pending rows.
                db.execute('ALTER TABLE snapshots ADD COLUMN swept_version INTEGER NOT NULL DEFAULT -1')

    @staticmethod
    def _connect(path, readonly):
        uri = Path(path).resolve().as_uri() + ('?mode=ro' if readonly else '?mode=rwc')
        db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=NORMAL')
        except BaseException:
            db.close()
            raise
        return db

    @classmethod
    def open_readonly(cls, path) -> sqlite3.Connection:
        """Caller owns and must close this mode=ro connection."""
        return cls._connect(path, readonly=True)

    def close(self):
        self.connection.close()

    @contextmanager
    def _write(self):
        if os.getpid() != self._pid:
            raise RuntimeError('Open a separate CrawlQueue in each process')
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self.connection
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def add_list_tasks(self, kws: list[KwMeta], sources: Iterable[str]):
        sources = tuple(sources)
        with self._write() as db:
            for k in kws:
                db.execute('INSERT OR IGNORE INTO keyword_meta VALUES (?,?,?,?)',
                           (k.kw, k.axis, k.sub, k.order))
                db.executemany('INSERT OR IGNORE INTO list_tasks(kw,source) VALUES (?,?)',
                               [(k.kw, s) for s in sources])

    def _require_run(self, db):
        if self.run_id is None:
            raise RuntimeError('Register a run before claiming work')
        if not db.execute("SELECT 1 FROM runs WHERE run_id=? AND pid=? AND status='running'",
                          (self.run_id, os.getpid())).fetchone():
            raise LeaseLost('Run is no longer running')

    def next_list_tasks(self, source: str | None, n: int) -> list[ListTask]:
        if n < 0:
            raise ValueError('n must be nonnegative')
        with self._write() as db:
            self._require_run(db)
            rows = db.execute("""SELECT t.*, m.kw_axis, m.kw_sub, m.kw_order
                FROM list_tasks t JOIN keyword_meta m USING(kw)
                WHERE status='pending' AND (? IS NULL OR source=?)
                ORDER BY kw_order, source, cursor LIMIT ?""", (source, source, n)).fetchall()
            tasks = []
            for row in rows:
                db.execute("""UPDATE list_tasks SET status='running',lease_run_id=?
                    WHERE kw=? AND source=? AND cursor=?""",
                           (self.run_id, row['kw'], row['source'], row['cursor']))
                data = {k: row[k] for k in ListTask.__dataclass_fields__}
                data.update(cursor=row['cursor'] or None, lease_run_id=self.run_id)
                tasks.append(ListTask(**data))
            return tasks

    def next_list_task(self) -> ListTask | None:
        tasks = self.next_list_tasks(None, 1)
        return tasks[0] if tasks else None

    def _list_owner(self, db, task):
        self._require_run(db)
        row = db.execute('SELECT * FROM list_tasks WHERE kw=? AND source=? AND cursor=?',
                         (task.kw, task.source, task.cursor or '')).fetchone()
        if (row is None or row['lease_run_id'] != self.run_id
                or task.lease_run_id != self.run_id or row['status'] != 'running'):
            raise LeaseLost('List task is no longer owned by this run')
        return row

    def mark_list_failed(self, task: ListTask, err: str) -> None:
        with self._write() as db:
            row = self._list_owner(db, task)
            db.execute("""UPDATE list_tasks SET attempts=attempts+1,last_error=?,
                status=?,lease_run_id=NULL WHERE kw=? AND source=? AND cursor=?""",
                       (err, 'failed' if row['attempts'] + 1 >= 3 else 'pending',
                        task.kw, task.source, task.cursor or ''))

    def _prepare(self, items, task=None):
        result = []
        for item in items:
            source = task.source if task else _get(item, 'source')
            kw = task.kw if task else _get(item, 'kw')
            if not source or not kw:
                raise ValueError('add_urls requires source and kw attributes or mapping keys')
            axis = task.kw_axis if task else _get(item, 'kw_axis', '')
            sub = task.kw_sub if task else _get(item, 'kw_sub', '')
            order = task.kw_order if task else _get(item, 'kw_order', 0)
            d = _get(item, 'date')
            if isinstance(d, (date, datetime)):
                d = d.isoformat()
            result.append((normalize_url(_get(item, 'url'), source), source, kw, axis, sub,
                           _get(item, 'snippet', ''), _get(item, 'title', ''), d,
                           json.dumps(_get(item, 'src_meta', {}), ensure_ascii=False), order))
        return result

    @staticmethod
    def _insert_urls(db, prepared):
        added = 0
        for row in prepared:
            added += db.execute('''INSERT OR IGNORE INTO urls
                (url_norm,source,kw,kw_axis,kw_sub,snippet,title,date,src_meta_json,first_seen_kw_order)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', row).rowcount
            db.execute('INSERT OR IGNORE INTO url_hits VALUES (?,?,?,?,?,?)', row[:5] + (row[9],))
        return added

    def record_list_page(self, task: ListTask, items: list[ListItemLike], next_cursor: str | None, *, filter_rules=None):
        prepared = self._prepare(items, task)
        with self._write() as db:
            self._list_owner(db, task)
            self._insert_urls(db, prepared)
            for row, rule in zip(prepared, filter_rules or [None] * len(prepared)):
                if rule:
                    db.execute("""UPDATE urls SET status='filtered',filter_rule=?,last_error=?
                        WHERE url_norm=? AND source=? AND status='pending' AND attempts=0""",
                        (rule, rule, row[0], row[1]))
            db.execute('''UPDATE list_tasks SET status='done', fetched=?, attempts=attempts+1,
                last_error=NULL,lease_run_id=NULL WHERE kw=? AND source=? AND cursor=?''',
                       (len(prepared), task.kw, task.source, task.cursor or ''))
            if next_cursor is not None:
                db.execute('INSERT OR IGNORE INTO list_tasks(kw,source,cursor) VALUES (?,?,?)',
                           (task.kw, task.source, next_cursor))

    def add_urls(self, items: Iterable[ListItemLike | Mapping[str, Any]]) -> int:
        """Standalone items additionally carry source, kw, kw_axis, kw_sub, kw_order."""
        prepared = self._prepare(items)
        with self._write() as db:
            return self._insert_urls(db, prepared)

    def take_snapshot(self) -> str:
        snapshot_id = uuid4().hex
        with self._write() as db:
            rows = db.execute('SELECT url_norm,source FROM urls ORDER BY source,url_norm').fetchall()
            digest = hashlib.sha256(json.dumps([tuple(r) for r in rows], ensure_ascii=False,
                                               separators=(',', ':')).encode()).hexdigest()
            db.execute('''INSERT INTO snapshots
                       (snapshot_id,created_at,url_count,hash,exclusion_version,swept_version)
                       VALUES (?,?,?,?,0,0)''',
                       (snapshot_id, time.time(), len(rows), digest))
            db.execute('INSERT INTO snapshot_urls SELECT ?,url_norm,source FROM urls', (snapshot_id,))
        return snapshot_id

    @staticmethod
    def _snapshot(db, snapshot_id):
        if not db.execute('SELECT 1 FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone():
            raise ValueError('Unknown snapshot')

    def lease_urls(self, snapshot_id: str, n: int, lease_s: float, sources: list[str] | None = None) -> list[UrlRow]:
        if n < 0 or lease_s <= 0:
            raise ValueError('n must be nonnegative and lease_s positive')
        now = time.time()
        with self._write() as db:
            self._require_run(db)
            self._snapshot(db, snapshot_id)
            versions = db.execute('''SELECT exclusion_version,swept_version FROM snapshots
                WHERE snapshot_id=?''', (snapshot_id,)).fetchone()
            if versions['exclusion_version'] != versions['swept_version']:
                # Selection below already chooses the lowest eligible keyword.
                self._apply_exclusions(db, snapshot_id, reassign=False)
                db.execute('''UPDATE snapshots SET swept_version=exclusion_version
                    WHERE snapshot_id=?''', (snapshot_id,))
            source_filter = '' if sources is None else ' AND u.source IN (' + ','.join('?' for _ in sources) + ')'
            rows = db.execute(f'''SELECT u.*, h.kw AS hit_kw, h.kw_axis AS hit_axis,
                    h.kw_sub AS hit_sub, h.kw_order AS hit_order
                FROM urls u JOIN snapshot_urls s USING(url_norm,source)
                JOIN url_hits h USING(url_norm,source)
                WHERE s.snapshot_id=? AND u.status='pending' AND (u.retry_at IS NULL OR u.retry_at<=?)
                AND h.kw=(SELECT h2.kw FROM url_hits h2
                    WHERE h2.url_norm=u.url_norm AND h2.source=u.source
                    AND NOT EXISTS (SELECT 1 FROM excluded_keywords e WHERE e.snapshot_id=? AND e.kw=h2.kw)
                    ORDER BY h2.kw_order,h2.kw LIMIT 1)
                {source_filter}
                ORDER BY h.kw_order,u.source,u.url_norm LIMIT ?''',
                              (snapshot_id, now, snapshot_id, *(sources or []), n)).fetchall()
            result = []
            for row in rows:
                exhausted = bool(row['exhausted'] or row['attempts'] >= row['max_attempts'])
                attempts = row['attempts'] if exhausted else row['attempts'] + 1
                db.execute('''UPDATE urls SET status='leased', lease_until=?, lease_run_id=?,
                    attempts=?, exhausted=?, kw=?, kw_axis=?, kw_sub=?, retry_at=NULL, lease_snapshot_id=?
                    WHERE url_norm=? AND source=?''',
                           (now + lease_s, self.run_id, attempts, exhausted, row['hit_kw'], row['hit_axis'], row['hit_sub'], snapshot_id,
                            row['url_norm'], row['source']))
                data = dict(row)
                data.update(kw=row['hit_kw'], kw_axis=row['hit_axis'], kw_sub=row['hit_sub'],
                            kw_order=row['hit_order'], attempts=attempts, exhausted=exhausted,
                            status='leased', lease_until=now + lease_s, lease_run_id=self.run_id,
                            src_meta=json.loads(row['src_meta_json']),
                            kw_hits=[r[0] for r in db.execute('''SELECT kw FROM url_hits
                                WHERE url_norm=? AND source=? ORDER BY kw_order,kw''',
                                                            (row['url_norm'], row['source']))])
                result.append(UrlRow(**{k: data[k] for k in UrlRow.__dataclass_fields__}))
        return result

    def _owns_completion(self, db, url_norm, source, allow_pending=False):
        if self.run_id is None:
            raise LeaseLost('No calling run')
        self._require_run(db)
        row = db.execute('SELECT * FROM urls WHERE url_norm=? AND source=?',
                         (url_norm, source)).fetchone()
        if row is not None:
            if row['status'] == 'leased' and row['lease_run_id'] == self.run_id:
                return row
            # P1 filters may reject newly discovered URLs before detail leasing.
            if (allow_pending and row['status'] == 'pending' and row['attempts'] == 0
                    and row['lease_run_id'] is None):
                return row
        raise LeaseLost('URL is no longer owned by this run')

    def mark_done(self, url_norm: str, source: str, doc_count: int, last_error=None,
                  fetch_level=None, access=None) -> None:
        self.mark_done_many([(url_norm, source, doc_count, last_error, fetch_level, access)])

    def mark_done_many(self, rows: list[tuple[str, str, int, str | None, str | None, str | None]]) -> None:
        """Commit a batch after the worker has flushed and fsynced its documents."""
        with self._write() as db:
            for url_norm, source, doc_count, last_error, fetch_level, access in rows:
                self._owns_completion(db, url_norm, source)
                db.execute("""UPDATE urls SET status='done',doc_count=?,last_error=?,fetch_level=?,
                    access=?,lease_until=NULL,lease_run_id=NULL,retry_at=NULL
                    WHERE url_norm=? AND source=?""",
                           (doc_count, last_error, fetch_level, access, url_norm, source))

    def mark_failed_attempt(self, url_norm: str, source: str, last_error: str,
                            max_attempts: int = 3, backoff_s: float = 1) -> str:
        """Return pending for retry, or exhausted while retaining the snippet lease."""
        with self._write() as db:
            row = self._owns_completion(db, url_norm, source)
            db.execute('UPDATE urls SET max_attempts=? WHERE url_norm=? AND source=?',
                       (max_attempts, url_norm, source))
            if row['exhausted'] or row['attempts'] >= max_attempts:
                db.execute('UPDATE urls SET exhausted=1,last_error=? WHERE url_norm=? AND source=?',
                           (last_error, url_norm, source))
                return 'exhausted'
            db.execute("""UPDATE urls SET status='pending',last_error=?,retry_at=?,
                lease_until=NULL,lease_run_id=NULL WHERE url_norm=? AND source=?""",
                       (last_error, time.time() + backoff_s * 2 ** (row['attempts'] - 1),
                        url_norm, source))
            self._apply_exclusions(db, keys=[(url_norm, source)])
            return 'pending'

    def mark_filtered(self, url_norm: str, source: str, rule: str) -> None:
        with self._write() as db:
            self._owns_completion(db, url_norm, source, allow_pending=True)
            db.execute("""UPDATE urls SET status='filtered',filter_rule=?,last_error=?,
                lease_until=NULL,lease_run_id=NULL WHERE url_norm=? AND source=?""",
                       (rule, rule, url_norm, source))

    def exclude_keywords(self, snapshot_id: str, kws: Iterable[str]) -> int:
        with self._write() as db:
            self._snapshot(db, snapshot_id)
            before = db.total_changes
            db.executemany('INSERT OR IGNORE INTO excluded_keywords VALUES (?,?)',
                           [(snapshot_id, kw) for kw in kws])
            if db.total_changes != before:
                db.execute('''UPDATE snapshots SET exclusion_version=exclusion_version+1
                    WHERE snapshot_id=?''', (snapshot_id,))
            return self._apply_exclusions(db, snapshot_id, include_failed=True)

    @staticmethod
    def _apply_exclusions(db, snapshot_id=None, *, keys=None, include_failed=False, reassign=True):
        """Apply D9 to selected rows inside the caller's write transaction.

        Without an explicit snapshot, use each row's persisted lease snapshot.
        Older leases without one are repaired by the next lease_urls sweep.
        """
        snapshot = '?' if snapshot_id is not None else 'urls.lease_snapshot_id'
        eligible = f"""SELECT h.kw FROM url_hits h
            WHERE h.url_norm=urls.url_norm AND h.source=urls.source
            AND NOT EXISTS (SELECT 1 FROM excluded_keywords e
                WHERE e.snapshot_id={snapshot} AND e.kw=h.kw)"""
        member = f"""EXISTS (SELECT 1 FROM snapshot_urls s WHERE s.snapshot_id={snapshot}
            AND s.url_norm=urls.url_norm AND s.source=urls.source)"""
        statuses = "('pending','failed')" if include_failed else "('pending')"
        target = f'status IN {statuses} AND {member}'
        if keys is not None:
            target += ' AND url_norm=? AND source=?'
        selected = [()] if keys is None else keys
        params = (snapshot_id,) if snapshot_id is not None else ()
        count = db.executemany(f"""UPDATE urls SET status='excluded',lease_until=NULL,
            lease_run_id=NULL WHERE {target} AND NOT EXISTS ({eligible})""",
            [params + tuple(key) + params for key in selected]).rowcount
        if not reassign:
            return count
        representative = f"""SELECT h.kw,h.kw_axis,h.kw_sub FROM url_hits h
            WHERE h.url_norm=urls.url_norm AND h.source=urls.source
            AND NOT EXISTS (SELECT 1 FROM excluded_keywords e
                WHERE e.snapshot_id={snapshot} AND e.kw=h.kw)
            ORDER BY h.kw_order,h.kw LIMIT 1"""
        db.executemany(f"""UPDATE urls SET (kw,kw_axis,kw_sub)=({representative})
            WHERE {target} AND EXISTS ({eligible})
            AND (kw,kw_axis,kw_sub) IS NOT ({representative})""",
            [params + params + tuple(key) + params + params for key in selected])
        return count

    def reclaim_expired_leases(self) -> int:
        now = time.time()
        with self._write() as db:
            runs = db.execute('SELECT run_id,pid,heartbeat_at,status FROM runs').fetchall()
            stale = {r['run_id'] for r in runs if not _alive(r['pid']) or
                     r['heartbeat_at'] < now - STALE_AFTER_S or r['status'] != 'running'}
            rows = db.execute("SELECT url_norm,source,lease_until,lease_run_id FROM urls WHERE status='leased'").fetchall()
            keys = [(r['url_norm'], r['source']) for r in rows
                    if r['lease_until'] is None or r['lease_until'] <= now or r['lease_run_id'] in stale]
            db.executemany("UPDATE urls SET status='pending',lease_until=NULL,lease_run_id=NULL WHERE url_norm=? AND source=?", keys)
            self._apply_exclusions(db, keys=keys)
            list_count = 0
            for run_id in stale:
                list_count += db.execute("""UPDATE list_tasks SET status='pending',lease_run_id=NULL
                    WHERE status='running' AND lease_run_id=?""", (run_id,)).rowcount
            db.executemany("UPDATE runs SET status='interrupted' WHERE run_id=? AND status='running'", [(r,) for r in stale])
        return len(keys) + list_count

    def register_run(self, kind: str) -> str:
        if kind not in ('list', 'detail'):
            raise ValueError('kind must be list or detail')
        now, run_id = time.time(), uuid4().hex
        # One queue file per collection/session; its directory is the stable session scope.
        sid = str(self.path.parent)
        with self._write() as db:
            rows = db.execute("SELECT * FROM runs WHERE sid=? AND kind=? AND status='running'", (sid, kind)).fetchall()
            for row in rows:
                if _alive(row['pid']) and row['heartbeat_at'] >= now - STALE_AFTER_S:
                    raise RuntimeError('A live worker of this kind is already registered')
                db.execute("UPDATE runs SET status='interrupted' WHERE run_id=?", (row['run_id'],))
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
                       (run_id, sid, kind, os.getpid(), 'running', now, now, '{}'))
        self.run_id = run_id
        self.reclaim_expired_leases()
        return run_id

    def heartbeat(self, run_id: str):
        with self._write() as db:
            if run_id != self.run_id:
                raise LeaseLost('Heartbeat does not belong to the calling run')
            if not db.execute("UPDATE runs SET heartbeat_at=? WHERE run_id=? AND pid=? AND status='running'",
                              (time.time(), run_id, os.getpid())).rowcount:
                raise LeaseLost('Run is no longer running')

    def finish_run(self, run_id: str, status: str):
        with self._write() as db:
            db.execute('UPDATE runs SET status=?,heartbeat_at=? WHERE run_id=? AND pid=?',
                       (status, time.time(), run_id, os.getpid()))
        if self.run_id == run_id:
            self.run_id = None

    def counts(self) -> dict:
        with closing(self.open_readonly(self.path)) as db:
            db.execute('BEGIN')
            result = dict.fromkeys(('pending', 'leased', 'done', 'failed', 'excluded', 'filtered'), 0)
            result.update(dict(db.execute('SELECT status,count(*) FROM urls GROUP BY status')))
            result['total'] = sum(result.values())
            result['doc_count'] = db.execute("SELECT coalesce(sum(doc_count),0) FROM urls WHERE status='done'").fetchone()[0]
            for key, column in (('fetch_level', 'fetch_level'), ('access', 'access'), ('filter_rules', 'filter_rule')):
                status = 'filtered' if key == 'filter_rules' else 'done'
                result[key] = dict(db.execute(f'SELECT {column},count(*) FROM urls WHERE status=? AND {column} IS NOT NULL GROUP BY {column}', (status,)))
            db.commit()
            return result
