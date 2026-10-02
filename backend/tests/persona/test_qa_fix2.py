import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.persona.concepts import make_concept, _inputs
from app.persona.package import load_package
from app.routers import stage8
from app.llm.fake import FakeBackend
from tests.persona.test_insights import env
from tests.persona.test_chat import ready
from tests.fixtures.evidence_package import write_session_with_package


def test_fixture_authors(data_dir):
    session = write_session_with_package(data_dir)
    root = data_dir / 'sessions' / session.sid / 'versions' / session.version
    with sqlite3.connect(root / 'segment/segment.sqlite') as db:
        assert db.execute('SELECT count(*), count(author_hash), count(DISTINCT author_hash) FROM docs').fetchone() == (88, 88, 44)


def test_failed_header(data_dir):
    session = write_session_with_package(data_dir)
    from app.persona.store import PersonaStore
    PersonaStore.open(session.sid, session.version).write('cards', {'run': 'qa', 'personas': {'CL0-P3': {'status': 'failed', 'error': 'qa'}}})
    row = stage8.persona_cards(session.sid)['personas']['CL0-P3']
    assert row['card'] is None
    assert row['package_counts'] == dict(doc_count=16, author_count=8, context_count=2)


def test_every_pain_point_has_evidence_context(ready):
    session = ready[0]
    result = make_concept(session.sid, session.version, 'I1', run_task=FakeBackend().run)
    assert result['basis'] == '근거 4건 · 작성자 2명에서 종합'
    assert all(p['context_id'] == 'CL0-P0-C0' for p in result['pain_points'])
    package = load_package(session.sid, session.version)
    refs = _inputs(package, {'context_ids': ['CL0-P0-C1']})[2]
    assert refs and all(r.context_id == 'CL0-P0-C1' for r in refs.values())


def test_second_session_cli(data_dir):
    script = Path(__file__).parents[1] / 'scripts/make_persona_qa.py'
    run = subprocess.run([sys.executable, str(script), str(data_dir), '--second-session'], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    output = json.loads(run.stdout)
    assert output['second_sid'] != output['sid']
    first, second = [data_dir / 'sessions' / output[key] / 'versions/v1' for key in ('sid', 'second_sid')]
    assert json.loads((first / 'session.json').read_text())['bk'] == json.loads((second / 'session.json').read_text())['bk']
    assert not (second / 'persona').exists()
