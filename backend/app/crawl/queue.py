"""Process-local SQLite crawl queue. Adapter objects are accepted by attributes.

Use one instance per process (and serialize use within that process). List workers
schedule each returned ListTask once; next_list_task is a peek, not a list lease.
Call register_run('detail') before leasing to associate leases with a worker.
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

DDL = """
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, sid TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('list','detail')),
 pid INTEGER NOT NULL, status TEXT NOT NULL, started_at REAL NOT NULL,
 heartbeat_at REAL NOT NULL, config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS list_tasks (
 kw TEXT NOT NULL, source TEXT NOT NULL, cursor TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','failed')),
 fetched INTEGER NOT NULL DEFAULT 0, total_hint INTEGER,
 attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
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
 lease_until REAL, lease_run_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, doc_count INTEGER NOT NULL DEFAULT 0, first_seen_kw_order INTEGER NOT NULL,
 fetch_level TEXT, access TEXT, retry_at REAL, filter_rule TEXT,
 UNIQUE(url_norm, source)
);
CREATE TABLE IF NOT EXISTS url_hits (
 url_norm TEXT NOT NULL, source TEXT NOT NULL, kw TEXT NOT NULL,
 kw_axis TEXT NOT NULL, kw_sub TEXT NOT NULL, kw_order INTEGER NOT NULL,
 PRIMARY KEY(url_norm, source, kw)
);
CREATE TABLE IF NOT EXISTS snapshots (
 snapshot_id TEXT PRIMARY KEY, created_at REAL NOT NULL, url_count INTEGER NOT NULL, hash TEXT NOT NULL
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

    def next_list_task(self) -> ListTask | None:
        with closing(self.open_readonly(self.path)) as db:
            row = db.execute('''SELECT t.*, m.kw_axis, m.kw_sub, m.kw_order
                FROM list_tasks t JOIN keyword_meta m USING(kw) WHERE status='pending'
                ORDER BY kw_order, source, cursor LIMIT 1''').fetchone()
        if row is None:
            return None
        return ListTask(**{k: row[k] for k in ListTask.__dataclass_fields__ if k != 'cursor'},
                        cursor=row['cursor'] or None)

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

    def record_list_page(self, task: ListTask, items: list[ListItemLike], next_cursor: str | None):
        prepared = self._prepare(items, task)
        with self._write() as db:
            row = db.execute('SELECT status FROM list_tasks WHERE kw=? AND source=? AND cursor=?',
                             (task.kw, task.source, task.cursor or '')).fetchone()
            if row is None:
                raise ValueError('Unknown list task')
            if row['status'] == 'done':
                return
            self._insert_urls(db, prepared)
            db.execute('''UPDATE list_tasks SET status='done', fetched=?, attempts=attempts+1,
                last_error=NULL WHERE kw=? AND source=? AND cursor=?''',
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
            db.execute('INSERT INTO snapshots VALUES (?,?,?,?)',
                       (snapshot_id, time.time(), len(rows), digest))
            db.execute('INSERT INTO snapshot_urls SELECT ?,url_norm,source FROM urls', (snapshot_id,))
        return snapshot_id

    @staticmethod
    def _snapshot(db, snapshot_id):
        if not db.execute('SELECT 1 FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone():
            raise ValueError('Unknown snapshot')

    def lease_urls(self, snapshot_id: str, n: int, lease_s: float) -> list[UrlRow]:
        if n < 0 or lease_s <= 0:
            raise ValueError('n must be nonnegative and lease_s positive')
        now = time.time()
        with self._write() as db:
            self._snapshot(db, snapshot_id)
            rows = db.execute('''SELECT u.*, h.kw AS hit_kw, h.kw_axis AS hit_axis,
                    h.kw_sub AS hit_sub, h.kw_order AS hit_order
                FROM urls u JOIN snapshot_urls s USING(url_norm,source)
                JOIN url_hits h USING(url_norm,source)
                WHERE s.snapshot_id=? AND u.status='pending' AND (u.retry_at IS NULL OR u.retry_at<=?)
                AND h.kw=(SELECT h2.kw FROM url_hits h2
                    WHERE h2.url_norm=u.url_norm AND h2.source=u.source
                    AND NOT EXISTS (SELECT 1 FROM excluded_keywords e WHERE e.snapshot_id=? AND e.kw=h2.kw)
                    ORDER BY h2.kw_order,h2.kw LIMIT 1)
                ORDER BY h.kw_order,u.source,u.url_norm LIMIT ?''',
                              (snapshot_id, now, snapshot_id, n)).fetchall()
            result = []
            for row in rows:
                db.execute('''UPDATE urls SET status='leased', lease_until=?, lease_run_id=?,
                    attempts=attempts+1, kw=?, kw_axis=?, kw_sub=?, retry_at=NULL
                    WHERE url_norm=? AND source=?''',
                           (now + lease_s, self.run_id, row['hit_kw'], row['hit_axis'], row['hit_sub'],
                            row['url_norm'], row['source']))
                data = dict(row)
                data.update(kw=row['hit_kw'], kw_axis=row['hit_axis'], kw_sub=row['hit_sub'],
                            kw_order=row['hit_order'], attempts=row['attempts'] + 1,
                            status='leased', lease_until=now + lease_s, lease_run_id=self.run_id,
                            src_meta=json.loads(row['src_meta_json']),
                            kw_hits=[r[0] for r in db.execute('''SELECT kw FROM url_hits
                                WHERE url_norm=? AND source=? ORDER BY kw_order,kw''',
                                                            (row['url_norm'], row['source']))])
                result.append(UrlRow(**{k: data[k] for k in UrlRow.__dataclass_fields__}))
        return result

    def _owns_completion(self, db, url_norm, source):
        row = db.execute('SELECT lease_run_id FROM urls WHERE url_norm=? AND source=?',
                         (url_norm, source)).fetchone()
        if row is None or row['lease_run_id'] not in (None, self.run_id):
            return False
        return self.run_id is None or db.execute(
            "SELECT 1 FROM runs WHERE run_id=? AND status='running' AND pid=?",
            (self.run_id, os.getpid())).fetchone() is not None

    def mark_done(self, url_norm: str, source: str, doc_count: int, last_error=None,
                  fetch_level=None, access=None):
        with self._write() as db:
            if not self._owns_completion(db, url_norm, source):
                return
            db.execute('''UPDATE urls SET status='done',doc_count=?,last_error=?,fetch_level=?,
                access=?,lease_until=NULL,lease_run_id=NULL,retry_at=NULL
                WHERE url_norm=? AND source=? AND status NOT IN ('excluded','filtered')''',
                       (doc_count, last_error, fetch_level, access, url_norm, source))

    def mark_failed_attempt(self, url_norm: str, source: str, last_error: str,
                            max_attempts: int = 3, backoff_s: float = 1):
        """Attempts increment on lease. At limit, worker must persist snippet then mark_done.

        'failed' is the awaiting-fallback state; never fabricate a persisted document here.
        """
        with self._write() as db:
            if not self._owns_completion(db, url_norm, source):
                return
            row = db.execute('SELECT attempts,status FROM urls WHERE url_norm=? AND source=?',
                             (url_norm, source)).fetchone()
            if row is None or row['status'] != 'leased':
                return
            exhausted = row['attempts'] >= max_attempts
            db.execute('''UPDATE urls SET status=?,last_error=?,retry_at=?,lease_until=NULL,
                lease_run_id=NULL WHERE url_norm=? AND source=?''',
                       ('failed' if exhausted else 'pending', last_error,
                        None if exhausted else time.time() + backoff_s * 2 ** (row['attempts'] - 1),
                        url_norm, source))

    def mark_filtered(self, url_norm: str, source: str, rule: str):
        with self._write() as db:
            if not self._owns_completion(db, url_norm, source):
                return
            db.execute('''UPDATE urls SET status='filtered',filter_rule=?,last_error=?,
                lease_until=NULL,lease_run_id=NULL WHERE url_norm=? AND source=?
                AND status NOT IN ('done','excluded')''', (rule, rule, url_norm, source))

    def exclude_keywords(self, snapshot_id: str, kws: Iterable[str]) -> int:
        with self._write() as db:
            self._snapshot(db, snapshot_id)
            db.executemany('INSERT OR IGNORE INTO excluded_keywords VALUES (?,?)',
                           [(snapshot_id, kw) for kw in kws])
            # Set-based updates avoid a Python round trip per URL under the write lock.
            eligible = """SELECT h.kw FROM url_hits h
                WHERE h.url_norm=urls.url_norm AND h.source=urls.source
                AND NOT EXISTS (SELECT 1 FROM excluded_keywords e
                    WHERE e.snapshot_id=? AND e.kw=h.kw)"""
            member = """EXISTS (SELECT 1 FROM snapshot_urls s WHERE s.snapshot_id=?
                AND s.url_norm=urls.url_norm AND s.source=urls.source)"""
            count = db.execute(f"""UPDATE urls SET status='excluded',lease_until=NULL,
                lease_run_id=NULL WHERE status!='excluded' AND {member}
                AND NOT EXISTS ({eligible})""", (snapshot_id, snapshot_id)).rowcount
            db.execute(f"""UPDATE urls SET (kw,kw_axis,kw_sub)=(
                SELECT h.kw,h.kw_axis,h.kw_sub FROM url_hits h
                WHERE h.url_norm=urls.url_norm AND h.source=urls.source
                AND NOT EXISTS (SELECT 1 FROM excluded_keywords e
                    WHERE e.snapshot_id=? AND e.kw=h.kw)
                ORDER BY h.kw_order,h.kw LIMIT 1)
                WHERE {member} AND EXISTS ({eligible})""",
                       (snapshot_id, snapshot_id, snapshot_id))
            return count

    def reclaim_expired_leases(self) -> int:
        now = time.time()
        with self._write() as db:
            runs = db.execute('SELECT run_id,pid,heartbeat_at,status FROM runs').fetchall()
            stale = {r['run_id'] for r in runs if not _alive(r['pid']) or
                     r['heartbeat_at'] < now - 3 * HEARTBEAT_INTERVAL or r['status'] != 'running'}
            rows = db.execute("SELECT url_norm,source,lease_until,lease_run_id FROM urls WHERE status='leased'").fetchall()
            keys = [(r['url_norm'], r['source']) for r in rows
                    if r['lease_until'] is None or r['lease_until'] <= now or r['lease_run_id'] in stale]
            db.executemany("UPDATE urls SET status='pending',lease_until=NULL,lease_run_id=NULL WHERE url_norm=? AND source=?", keys)
            db.executemany("UPDATE runs SET status='interrupted' WHERE run_id=? AND status='running'", [(r,) for r in stale])
        return len(keys)

    def register_run(self, kind: str) -> str:
        if kind not in ('list', 'detail'):
            raise ValueError('kind must be list or detail')
        now, run_id = time.time(), uuid4().hex
        # One queue file per collection/session; its directory is the stable session scope.
        sid = str(self.path.parent)
        with self._write() as db:
            rows = db.execute("SELECT * FROM runs WHERE sid=? AND kind=? AND status='running'", (sid, kind)).fetchall()
            for row in rows:
                if _alive(row['pid']) and row['heartbeat_at'] >= now - 3 * HEARTBEAT_INTERVAL:
                    raise RuntimeError('A live worker of this kind is already registered')
                db.execute("UPDATE runs SET status='interrupted' WHERE run_id=?", (row['run_id'],))
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
                       (run_id, sid, kind, os.getpid(), 'running', now, now, '{}'))
        self.run_id = run_id
        self.reclaim_expired_leases()
        return run_id

    def heartbeat(self, run_id: str):
        with self._write() as db:
            db.execute("UPDATE runs SET heartbeat_at=? WHERE run_id=? AND pid=? AND status='running'",
                       (time.time(), run_id, os.getpid()))

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
