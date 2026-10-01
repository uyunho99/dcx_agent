"""Manual audits must not consume automatic audit thresholds (AC-04)."""
import json
import socket
import sqlite3

import pytest

from app.context import store as sessions
from app.label import audit, questions, rule
from app.label.schema import Tags
from app.label.store import LabelStore


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Audit tests must not connect to the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def seed(labels, start, stop):
    tags = Tags(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1))
    with labels._db() as db:
        db.executemany('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ((f'd{i}', 'core', .9, 'agreed', 'accepted', tags.model_dump_json(),
              None, None, rule.RULE_VERSION, questions.QVER, json.dumps({}), '[]', 0)
             for i in range(start, stop)))


def test_manual_at_500_does_not_delay_automatic_round(client, data_dir):
    sid = 'audit-kind'
    sessions.update_session(sid, {'schemaVersion': 2})
    labels = LabelStore(sessions.session_dir(sid))
    seed(labels, 0, 500)
    assert audit.maybe_new_round(labels, 500) is None
    response = client.post(f'/label/{sid}/audit')
    assert response.status_code == 200, response.text
    assert response.json() == {'round': 1}

    seed(labels, 500, 1000)
    labels = LabelStore(labels.path.parent)
    assert audit.maybe_new_round(labels, 999) is None
    assert audit.maybe_new_round(labels, 1000) == 2
    assert audit.maybe_new_round(labels, 1000) is None
    assert audit.maybe_new_round(labels, 10999) is None
    assert audit.maybe_new_round(labels, 11000) == 3
    with labels._db() as db:
        assert [tuple(row) for row in db.execute(
            'SELECT round, kind, count(*) FROM audit_set GROUP BY round, kind ORDER BY round'
        )] == [(1, 'manual', 50), (2, 'auto', 50), (3, 'auto', 50)]


@pytest.mark.parametrize('legacy_round', [None, 7])
def test_existing_database_migrates_and_reopens(tmp_path, legacy_round):
    with sqlite3.connect(tmp_path / 'labels.sqlite') as db:
        db.execute('''CREATE TABLE audit_set (
            round INTEGER NOT NULL, doc_id TEXT NOT NULL, picked_at REAL NOT NULL,
            PRIMARY KEY(round, doc_id))''')
        if legacy_round is not None:
            db.executemany('INSERT INTO audit_set VALUES (?,?,?)',
                           [(legacy_round, 'old-a', 123.0), (legacy_round, 'old-b', 124.0)])

    labels = LabelStore(tmp_path)
    with labels._db() as db:
        columns = {row['name']: row for row in db.execute('PRAGMA table_info(audit_set)')}
        assert 'kind' in columns
        assert columns['kind']['dflt_value'] == "'auto'"
        if legacy_round is not None:
            assert [tuple(row) for row in db.execute('SELECT * FROM audit_set ORDER BY doc_id')] == [
                (7, 'old-a', 123.0, 'auto'), (7, 'old-b', 124.0, 'auto')]

    labels = LabelStore(tmp_path)  # Migration must be repeatable.
    seed(labels, 0, 1000)
    if legacy_round is None:
        assert audit.maybe_new_round(labels, 1000) == 1
    else:
        assert audit.maybe_new_round(labels, 1000) is None
        assert audit.maybe_new_round(labels, 10999) is None
        assert audit.maybe_new_round(labels, 11000) == 8
        assert audit.maybe_new_round(labels, 11000) is None
    with labels._db() as db:
        assert {row[0] for row in db.execute('SELECT kind FROM audit_set')} == {'auto'}
