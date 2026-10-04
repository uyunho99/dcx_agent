"""T2: GPT-only projection, completion, and legacy storage migration."""
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from app.context import stale, store, versions
from app.label import questions, route, rule
from app.label.store import LabelStore
from app.label.votes import VoteCache
from app.work.status import transaction
from tests.label.test_merge import put, rows, votes


def test_gpt_only_recovers_vote_consumed_by_cross_sync(tmp_path):
    labels = LabelStore(tmp_path / 'v1')
    jc, gc = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    put(gc, 'd', votes()[1])
    route.sync(labels, jc, gc, mode='cross')
    assert rows(labels, 'final') == []
    route.sync(labels, jc, gc, mode='gpt_only')
    assert [(r['doc_id'], r['source']) for r in rows(labels, 'final')] == [('d', 'gpt_only')]
    assert route.rebuild_final(labels, jc, gc, mode='gpt_only') == 0
    put(jc, 'd', votes()[0])
    route.sync(labels, jc, gc, mode='cross')
    assert labels.get('d').source == 'agreed'


@pytest.mark.parametrize('changed', ['rule', 'questions'])
def test_gpt_only_ignores_inactive_checkpoint_version(tmp_path, monkeypatch, changed):
    labels = LabelStore(tmp_path / 'v1')
    jc, gc = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    put(jc, 'd', votes()[0])
    put(gc, 'd', votes()[1])
    route.sync(labels, jc, gc, mode='cross')
    route.sync(labels, jc, gc, mode='gpt_only')
    monkeypatch.setattr(rule if changed == 'rule' else questions,
                        'RULE_VERSION' if changed == 'rule' else 'QVER', 'next')
    route.sync(labels, jc, gc, mode='gpt_only')
    before = rows(labels, 'final')
    assert len(before) == 1
    assert before[0]['source'] == 'gpt_only'
    assert (before[0]['rule_version'], before[0]['questions_version']) == (rule.RULE_VERSION, questions.QVER)
    route.sync(labels, jc, gc, mode='gpt_only')
    assert rows(labels, 'final') == before
    # Recreating rows on every sync would hide the stale-checkpoint bug.
    assert route.rebuild_final(labels, jc, gc, mode='gpt_only') == 0
    route.sync(labels, jc, gc, mode='cross')
    assert labels.get('d').source == 'agreed'


@pytest.mark.parametrize('jev_kind', ['none', 'missing', 'bad'])
def test_gpt_only_final_and_queue(tmp_path, jev_kind):
    labels = LabelStore(tmp_path / 'v1')
    gc = VoteCache(tmp_path / 'gpt')
    jc = None if jev_kind == 'none' else VoteCache(tmp_path / 'jev')
    if jev_kind == 'missing':
        jc.path.unlink()
    elif jev_kind == 'bad':
        jc.seed(['jev-failed'])
        jc.mark_bad('jev-failed', 'bad')
    expected = {}
    for i in range(3):
        g = votes()[1]
        g.anchor = i != 0
        g.situation = i == 2
        g.reason_code = 'other' if i == 0 else None
        expected[str(i)] = g
        put(gc, str(i), g)
    gc.seed(['bad'])
    gc.mark_bad('bad', 'bad')
    route.sync(labels, jc, gc, mode='gpt_only')
    assert len(rows(labels, 'final')) == 3
    for row in rows(labels, 'final'):
        g = expected[row['doc_id']]
        label = labels.get(row['doc_id'])
        assert label.source == 'gpt_only'
        assert label.route == 'accepted'
        assert label.confidence is None
        assert label.evidence_level == rule.grade(dict(anchor=int(g.anchor), situation=int(g.situation), **g.sem))
        assert json.loads(row['tags_json']) == g.model_dump()
        assert label.votes == {'jev': None, 'gpt': g.model_dump()}
        assert row['grade_mismatch'] == 0
        assert json.loads(row['disagree_json']) == []
        assert (row['reason_code'], row['signal']) == (g.reason_code, g.signal)
        assert (label.rule_version, label.questions_version) == (rule.RULE_VERSION, questions.QVER)
    assert [(r['doc_id'], r['reason']) for r in rows(labels, 'queue')] == [('bad', 'labeler_failed')]
    with labels._db() as db:
        assert [r[0] for r in db.execute("SELECT name FROM route_sync WHERE name!='mode'")] == ['gpt']
    assert route.rebuild_final(labels, jc, gc, mode='gpt_only') == 0


@pytest.mark.parametrize('changed', ['rule', 'questions'])
def test_gpt_only_invalidates_versions(tmp_path, monkeypatch, changed):
    labels = LabelStore(tmp_path / 'v1')
    gc = VoteCache(tmp_path / 'gpt')
    put(gc, 'd', votes()[1])
    route.rebuild_final(labels, None, gc, mode='gpt_only')
    monkeypatch.setattr(rule if changed == 'rule' else questions,
                        'RULE_VERSION' if changed == 'rule' else 'QVER', 'next')
    assert route.rebuild_final(labels, None, gc, mode='gpt_only') == 1
    assert labels.get('d').rule_version == rule.RULE_VERSION
    assert labels.get('d').questions_version == questions.QVER


def test_cross_replaces_gpt_only_preserves_human_and_model(tmp_path):
    labels = LabelStore(tmp_path / 'v1')
    jc, gc = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    for doc in ('auto', 'human', 'model'):
        put(jc, doc, votes()[0])
        put(gc, doc, votes()[1])
    route.rebuild_final(labels, jc, gc)
    with labels._db() as db:
        db.execute("UPDATE final SET source='gpt_only' WHERE doc_id='auto'")
        db.execute("UPDATE final SET source=doc_id WHERE doc_id IN ('human','model')")
    before = {r['doc_id']: r for r in rows(labels, 'final')}
    # Both cursors are caught up: mode transition must still reconsider the row.
    assert route.rebuild_final(labels, jc, gc, mode='cross') == 1
    assert labels.get('auto').source == 'agreed'
    for row in rows(labels, 'final'):
        if row['doc_id'] != 'auto':
            assert row == before[row['doc_id']]


@pytest.mark.parametrize('mode', ['gpt_only', 'cross', None])
@pytest.mark.parametrize('recovery', [False, True])
def test_stage4_completion(data_dir, mode, recovery):
    labeling = {'started': True, 'status': 'running'}
    if mode is not None:
        labeling['labelerMode'] = mode
    store.update_session('session', {'schemaVersion': 2, 'version': 'v1',
        'labeling': labeling, 'stale': {'stage4': 'changed', 'stage5': 'changed'}})
    path = versions.version_dir('session', 'v1') / 'session.json'
    with transaction('session') as db:
        db.execute("""INSERT INTO runs
            (run_id,version,kind,labeler,args_json,pid,state,heartbeat_at,started_at)
            VALUES ('g','v1','judge','gpt','{}',?,?,1,1)""",
            (os.getpid(), 'done' if recovery else 'running'))
    if recovery:
        data = store.read_json(path)
        # Read mode from the version file, even if caller data is stale.
        data['labeling']['labelerMode'] = 'cross'
        stale.reconcile_judge_done('session', data, 'v1')
    else:
        stale.judge_done(SimpleNamespace(sid='session', version='v1', run_id='g'))
    saved = store.read_json(path)
    assert (saved['labeling']['status'] == 'done') is (mode == 'gpt_only')
    assert ('stage4' not in saved['stale']) is (mode == 'gpt_only')
    assert saved['stale']['stage5'] == 'changed'


def test_legacy_nullable_migration_preserves_rows_and_triggers(tmp_path):
    path = tmp_path / 'labels.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE final (
            doc_id TEXT PRIMARY KEY, level TEXT NOT NULL,
            confidence REAL NOT NULL, source TEXT NOT NULL, route TEXT NOT NULL,
            tags_json TEXT NOT NULL, reason_code TEXT, signal TEXT,
            rule_version TEXT NOT NULL, questions_version TEXT NOT NULL,
            votes_json TEXT NOT NULL, disagree_json TEXT NOT NULL,
            grade_mismatch INTEGER NOT NULL)''')
        db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('old', 'core', .9, 'agreed', 'accepted', votes()[1].model_dump_json(),
             None, 'workaround', rule.RULE_VERSION, questions.QVER, '{}', '[]', 0))
    # Install the existing events-v1 triggers without opening/migrating the DB.
    old = LabelStore.__new__(LabelStore)
    old.path = path
    with old._db() as db:
        db.execute('CREATE TABLE queue (doc_id TEXT PRIMARY KEY)')
        db.execute('CREATE INDEX final_source ON final(source)')
    route.schema(old)
    before = rows(old, 'final')
    # Remove the minimal queue fixture so LabelStore can create the full schema.
    with old._db() as db:
        db.execute('DROP TABLE queue')
    labels = LabelStore(tmp_path)
    assert rows(labels, 'final') == before
    with labels._db() as db:
        assert next(r for r in db.execute('PRAGMA table_info(final)') if r['name'] == 'confidence')['notnull'] == 0
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='final_source'").fetchone()
        db.execute("INSERT INTO final SELECT 'new',level,NULL,'gpt_only',route,tags_json,reason_code,signal,rule_version,questions_version,votes_json,disagree_json,grade_mismatch FROM final WHERE doc_id='old'")
        assert {r[0] for r in db.execute("SELECT kind FROM label_events WHERE doc_id='new'")} == {'merged', 'accepted'}
        schema_version = db.execute('PRAGMA schema_version').fetchone()[0]
    assert labels.get('new').confidence is None
    reopened = LabelStore(tmp_path)
    with reopened._db() as db:
        assert db.execute('PRAGMA schema_version').fetchone()[0] == schema_version
    assert rows(reopened, 'final') == rows(labels, 'final')
