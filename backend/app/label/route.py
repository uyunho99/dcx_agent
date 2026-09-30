"""Queue reconciliation and one-item, blind human review operations."""
import json
import time

from app.context.store import StoreError
from app.label import audit, questions, rule
from app.label.schema import Tags


def route(label) -> str:
    values = label if isinstance(label, dict) else label.model_dump()
    if values.get('labeler_failed'):
        return 'labeler_failed'
    return 'grade_mismatch' if values.get('grade_mismatch') else 'accepted'


def schema(store):
    with store._db() as db:
        audit._schema(db)
        db.execute('''CREATE TABLE IF NOT EXISTS review_done (
            mode TEXT, round INTEGER, doc_id TEXT, elapsed REAL,
            PRIMARY KEY(mode, round, doc_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY, payload TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS label_events (
            kind TEXT, doc_id TEXT, at REAL, PRIMARY KEY(kind, doc_id))''')
        db.execute('CREATE INDEX IF NOT EXISTS label_events_at ON label_events(at)')
        # Backfill once per document, including data created before this API existed.
        db.execute("""INSERT OR IGNORE INTO label_events
            SELECT 'merged', doc_id, ? FROM final WHERE source!='human'""", (time.time(),))
        db.execute("""INSERT OR IGNORE INTO label_events
            SELECT 'accepted', doc_id, ? FROM final WHERE route='accepted'""", (time.time(),))
        db.execute("""INSERT OR IGNORE INTO label_events
            SELECT 'queued', doc_id, ? FROM queue""", (time.time(),))
        for table, kind, condition in (
            ('final', 'merged', "NEW.source!='human'"),
            ('final', 'accepted', "NEW.route='accepted'"), ('queue', 'queued', '1')):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS event_{kind} AFTER INSERT ON {table}
                WHEN {condition} BEGIN INSERT OR IGNORE INTO label_events VALUES
                ('{kind}', NEW.doc_id, (julianday('now')-2440587.5)*86400.0); END''')


def rebuild_queue(store, jev_cache=None, gpt_cache=None):
    """Refresh on overview/judge polling, never on the indexed next-item path."""
    schema(store)
    from app.model.infer import refresh_predictions
    model_mode = refresh_predictions(store)
    if not model_mode and jev_cache is not None and gpt_cache is not None:
        from app.label.merge import rebuild_final
        rebuild_final(store, jev_cache, gpt_cache)
    with store._db() as db:
        # T09 carry-over: a recovered failed vote must not leave a stale review.
        db.execute("""UPDATE queue SET status='closed' WHERE status='open'
            AND EXISTS (SELECT 1 FROM final f WHERE f.doc_id=queue.doc_id
                        AND (f.source='human' OR (f.source!='model' AND f.grade_mismatch=0)))""")
        db.execute("""INSERT INTO queue(doc_id, reason, priority, status)
            SELECT doc_id, 'grade_mismatch', 1+confidence, 'open' FROM final
            WHERE grade_mismatch=1 AND source='agreed'
            ON CONFLICT(doc_id) DO UPDATE SET reason=excluded.reason,
                priority=excluded.priority WHERE queue.status='open'""")
        if model_mode:
            return
        for name, cache in (('jev', jev_cache), ('gpt', gpt_cache)):
            if cache is None:
                continue
            db.execute(f'ATTACH DATABASE ? AS {name}', (cache.path.resolve().as_uri() + '?mode=ro',))
            db.execute(f"""INSERT INTO queue(doc_id, reason, priority, status)
                SELECT doc_id, 'labeler_failed', 0, 'open' FROM {name}.votes v
                WHERE status='bad' AND NOT EXISTS (SELECT 1 FROM final f
                    WHERE f.doc_id=v.doc_id AND f.source='human')
                ON CONFLICT(doc_id) DO UPDATE SET reason='labeler_failed', priority=0
                    WHERE queue.status='open'""")


def _review_schema(db):
    # Constant-size DDL only; no corpus materialization on /next.
    audit._schema(db)
    db.execute('''CREATE TABLE IF NOT EXISTS review_done (
        mode TEXT, round INTEGER, doc_id TEXT, elapsed REAL,
        PRIMARY KEY(mode, round, doc_id))''')
    db.execute('CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')


def next_item(store, mode='escalate', round=None):
    with store._db() as db:
        if mode == 'escalate':
            row = db.execute("SELECT doc_id, reason FROM queue WHERE status='open' ORDER BY priority, doc_id LIMIT 1").fetchone()
        else:
            _review_schema(db)
            table = 'audit_snapshot' if mode == 'audit' else 'audit_reissue'
            row = db.execute(f'''SELECT s.doc_id, s.round FROM {table} s
                WHERE (? IS NULL OR s.round=?)
                AND NOT EXISTS (SELECT 1 FROM review_done d
                    WHERE d.mode=? AND d.round=s.round AND d.doc_id=s.doc_id)
                AND NOT EXISTS (SELECT 1 FROM {table} later
                    WHERE later.doc_id=s.doc_id AND later.round>s.round)
                {'AND NOT EXISTS (SELECT 1 FROM human h WHERE h.doc_id=s.doc_id AND h.mode=\'audit\' AND h.rowid>s.human_floor)' if mode == 'audit' else ''}
                ORDER BY s.round, s.doc_id LIMIT 1''', (round, round, mode)).fetchone()
        if row is None:
            return None
        result = dict(row)
        # The source index is populated at start/overview, not by a scan per item.
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='documents'").fetchone()
        doc = db.execute('SELECT payload FROM documents WHERE doc_id=?', (row['doc_id'],)).fetchone() if exists else None
        result['document'] = json.loads(doc[0]) if doc else None
        return result


def submit_item(store, doc_id, labeler, mode, tags, round=None, elapsed=None, caches=None):
    tags = Tags.model_validate(tags.model_dump() if isinstance(tags, Tags) else tags)
    level = rule.grade(dict(anchor=int(tags.anchor), situation=int(tags.situation), **tags.sem))
    with store._db() as db:
        _review_schema(db)
        if mode == 'escalate':
            valid = db.execute("SELECT 1 FROM queue WHERE doc_id=? AND status='open'", (doc_id,)).fetchone()
        else:
            table = 'audit_snapshot' if mode == 'audit' else 'audit_reissue'
            valid = db.execute(f'''SELECT 1 FROM {table} WHERE doc_id=? AND round=?
                AND round=(SELECT MAX(round) FROM {table} WHERE doc_id=?)
                AND NOT EXISTS (SELECT 1 FROM review_done WHERE mode=? AND round=? AND doc_id=?)''',
                (doc_id, round, doc_id, mode, round, doc_id)).fetchone()
        if valid and mode == 'audit':
            valid = not db.execute('''SELECT 1 FROM human h JOIN audit_snapshot s
                ON s.doc_id=h.doc_id WHERE s.round=? AND s.doc_id=?
                AND h.mode='audit' AND h.rowid>s.human_floor LIMIT 1''', (round, doc_id)).fetchone()
        if not valid:
            raise StoreError('현재 검수 항목과 감사 라운드를 확인하세요.')
        # Append the judgment and update its projection in the same durable
        # transaction. No comparison is returned until this commits.
        db.execute('''INSERT INTO human
            (doc_id, labeler, mode, tags_json, reason_code, signal, submitted_at)
            VALUES (?,?,?,?,?,?,?)''',
            (doc_id, labeler, mode, tags.model_dump_json(), tags.reason_code, tags.signal, time.time()))
        if mode == 'escalate':
            db.execute('''INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(doc_id) DO UPDATE SET level=excluded.level,
                source='human', route=excluded.route, tags_json=excluded.tags_json,
                reason_code=excluded.reason_code, signal=excluded.signal,
                rule_version=excluded.rule_version''',
                (doc_id, level, 1, 'human', 'escalated:human', tags.model_dump_json(),
                 tags.reason_code, tags.signal, rule.RULE_VERSION, questions.QVER, '{}', '[]', 0))
            db.execute("UPDATE queue SET status='closed' WHERE doc_id=?", (doc_id,))
        if caches:
            row = db.execute('SELECT votes_json FROM final WHERE doc_id=?', (doc_id,)).fetchone()
            votes = json.loads(row[0]) if row else {}
            for name, cache in caches.items():
                if name in votes:
                    continue
                with cache._db() as vote_db:
                    vote = vote_db.execute("SELECT payload_json FROM votes WHERE doc_id=? AND status='done'", (doc_id,)).fetchone()
                if vote:
                    votes[name] = json.loads(vote[0])
            db.execute('UPDATE final SET votes_json=? WHERE doc_id=?', (json.dumps(votes), doc_id))
        db.execute('INSERT OR REPLACE INTO review_done VALUES (?,?,?,?)', (mode, round or 0, doc_id, elapsed))
    if mode == 'audit':
        audit.apply_audit_overrides(store)
        # Even an unchanged confirmation is a human training example (weight 3).
        with store._db() as db:
            latest = db.execute('SELECT mode FROM human WHERE doc_id=? ORDER BY rowid DESC LIMIT 1', (doc_id,)).fetchone()
            projected = db.execute('SELECT tags_json FROM final WHERE doc_id=?', (doc_id,)).fetchone()
            if latest and latest[0] == 'audit' and projected and json.loads(projected[0]) == tags.model_dump():
                db.execute("UPDATE final SET source='human',route='audited' WHERE doc_id=?", (doc_id,))
    final = store.get(doc_id)
    return dict(doc_id=doc_id, level=level, votes=final.votes if final else {})
