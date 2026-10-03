"""R-111 regressions: each test was run red before implementation."""
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from app.config import settings, Settings
from app.context import store
from app.label import audit, gpt, judge, route, rule
from app.label.overview import labels_for, overview
from app.label.schema import Tags
from app.model import export, infer, monitor
from tests.model.test_model_mode import prepared, context
from tests.model.test_export import seed


def test_c1_same_tags_model_grade_is_corrected(data_dir, monkeypatch):
    sid, _ = prepared(data_dir)
    seed(sid)
    labels = labels_for(sid, store.load_session(sid))
    probs = dict.fromkeys(rule.SEM, .4) | {'anchor': .99, 'situation': .99}
    pred = infer.from_tag_probs(probs, [probs] * 4)
    assert pred.level == 'core' and pred.relevanceScore > .9
    tags = Tags(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 0))
    with labels._db() as db:
        db.execute('DELETE FROM final')
        db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('d0', pred.level, pred.confidence, 'model', 'accepted', tags.model_dump_json(),
             None, None, rule.RULE_VERSION, 'q1', '{}', '[]', 0))
    monkeypatch.setattr(settings, 'audit_first', 1)
    r = audit.maybe_new_round(labels, 1)
    result = route.submit_item(labels, 'd0', 'person', 'audit', tags, round=r)
    final = labels.get('d0')
    assert result['level'] == final.evidence_level == 'non'
    assert final.source == 'human' and final.route == 'audited'
    assert audit.apply_audit_overrides(labels) == 0


def test_c2_body_changes_execution_identity(monkeypatch):
    from app.llm.base import validate
    runs = []
    def run(tasks, **kw):
        runs.append(kw['run_id'])
        return [validate(tasks[0], '{"items":[]}')]
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    monkeypatch.setattr(gpt, 'run_many', run)
    for body in ['before', 'after', 'after']:
        gpt.judge_batch([{'doc_id': 'a', 'body': body}], 'topic', sid='s', ctx_key='ctx')
    assert runs[0] != runs[1]
    assert runs[1] == runs[2]


def prep_session(data_dir, monkeypatch, *, started=False, completed=False):
    from app.routers import prep
    from app.prep.config import PrepConfig, prep_key
    cfg = PrepConfig(embedder='fake')
    store.update_session('prepcheck', {'schemaVersion': 2, 'collectionId': 'c1',
        'prep': {'config': cfg.model_dump()}, 'labeling': {'started': started}})
    ref = dict(collectionId='c1', prepKey=prep_key('c1', cfg,
        SimpleNamespace(name=cfg.embedder, model=cfg.embedModel, dim=cfg.embedDim)))
    monkeypatch.setattr('app.crawl.control.phase_state', lambda *a: 'done' if completed else 'unfinished')
    monkeypatch.setattr(prep.runner, 'start', lambda *a: dict(state='running', runId='test', progress=0))
    return ref


@pytest.mark.parametrize('reuse', [False, True])
def test_c3_unfinished_crawl_cannot_start_or_reuse(client, data_dir, monkeypatch, reuse):
    ref = prep_session(data_dir, monkeypatch)
    if reuse:
        root = data_dir / 'derived/prepcheck/c1' / ref['prepKey']
        store.write_json(root / 'manifest.json', dict(status='done', compatWritten=True, compatRef='compat.jsonl'))
        store.write_json(root / 'stage_3.json', {})
        (data_dir / 'compat.jsonl').write_text('')
    response = client.post('/prep/prepcheck/run')
    assert response.status_code == 409
    assert response.json()['error']['message'] == '수집이 끝난 뒤에 전처리를 실행할 수 있습니다.'


def test_c3_legacy_endpoint_rejects_unfinished(client, data_dir, monkeypatch):
    prep_session(data_dir, monkeypatch)
    monkeypatch.setattr('app.routers.preprocessing.threading.Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    response = client.post('/preprocess', json={'sid': 'prepcheck'})
    assert response.status_code == 409
    assert response.json()['error']['message'] == '수집이 끝난 뒤에 전처리를 실행할 수 있습니다.'


def test_c4_human_only_trainable_count(client, data_dir):
    from app.routers.training_v2 import training_data
    sid, docs = prepared(data_dir, 42)
    labels = labels_for(sid, store.load_session(sid))
    tags = Tags(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1))
    with labels._db() as db:
        for i, doc in enumerate(docs):
            db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (doc['doc_id'], 'core', 1, 'human', 'audited' if i % 2 else 'escalated:human',
                 tags.model_dump_json(), None, None, rule.RULE_VERSION, 'q1', '{}', '[]', 0))
    from app.vectors.store import VectorStore
    # Two human labels have no usable embedding.
    import shutil
    root = data_dir / f'derived/{sid}/c1/p_123456789abc'
    for p in root.iterdir():
        if p.name not in ('docs', 'manifest.json'):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    VectorStore(root).write_shard([d['doc_id'] for d in docs[:41]],
        np.concatenate([np.ones((40, 1024)), np.zeros((1, 1024))]), [False] * 40 + [True])
    result = client.get(f'/label/{sid}/overview').json()
    assert result['accepted'] == 0
    assert result['trainable'] == 40
    X, targets = training_data(sid, store.load_session(sid))
    assert np.count_nonzero(np.any(X[:, :1024] != 0, axis=1)) == result['trainable']


@pytest.mark.parametrize('module', [judge, monitor])
def test_c5_fake_factory_never_uses_http(monkeypatch, module):
    monkeypatch.setattr(settings, 'jev_backend', 'fake')
    requests = []
    transport = httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(400))
    with module.JevClient(['not-a-real-key'], 'jev-latest', transport=transport) as client:
        a = client.judge({'doc_id': 'a', 'body': 'text'}, 'topic')
        b = client.judge({'doc_id': 'a', 'body': 'text'}, 'topic')
    assert a == b
    assert requests == []


@pytest.mark.parametrize('failure_at', ['all.jsonl', 'relevant.jsonl', 'stage_5.json', 'publish'])
def test_c6_export_crash_keeps_published_generation(data_dir, monkeypatch, failure_at):
    sid, _ = prepared(data_dir)
    seed(sid)
    first = export.write(sid, without_model=True)
    old = {name: (data_dir / first['exportRef']).with_name(name).read_bytes()
           for name in ['all.jsonl', 'relevant.jsonl', 'stage_5.json']}
    write = store.atomic_write
    update = store._update_locked
    def fail_publish(*args, **kwargs):
        raise OSError('simulated crash before pointer publication')
    if failure_at == 'publish':
        monkeypatch.setattr(store, '_update_locked', fail_publish)
    def crash(path, text):
        if Path(path).name == failure_at:
            Path(path).write_text('{partial')
            raise OSError('simulated disk failure')
        return write(path, text)
    monkeypatch.setattr(store, 'atomic_write', crash)
    with pytest.raises(OSError):
        export.write(sid, without_model=True)
    assert store.load_session(sid)['training']['exportRef'] == first['exportRef']
    assert old == {name: (data_dir / first['exportRef']).with_name(name).read_bytes() for name in old}
    from app.known.filter import read_export
    assert len(read_export(sid, store.load_session(sid))) == 2
    monkeypatch.setattr(store, 'atomic_write', write)
    monkeypatch.setattr(store, '_update_locked', update)
    second = export.write(sid, without_model=True)
    assert second['exportRef'] != first['exportRef']
    assert len(read_export(sid, store.load_session(sid))) == 2
    assert (data_dir / first['exportRef']).is_file()


def test_g2_two_visits_keep_previous_baseline(client, data_dir, monkeypatch):
    sid, _ = prepared(data_dir)
    route.schema(labels_for(sid, store.load_session(sid)))
    from app.routers import labeling_v2
    # _update_locked also calls now; return a stable timestamp for each visit.
    monkeypatch.setattr(labeling_v2.store, 'now', lambda: '2026-01-01T00:00:00+00:00')
    client.post(f'/label/{sid}/seen')
    with labels_for(sid, store.load_session(sid))._db() as db:
        db.execute("INSERT INTO label_events VALUES ('accepted','a',1767312000)")
    monkeypatch.setattr(labeling_v2.store, 'now', lambda: '2026-01-03T00:00:00+00:00')
    client.post(f'/label/{sid}/seen')
    labeling = store.load_session(sid)['labeling']
    assert labeling['prevSeenAt'] == '2026-01-01T00:00:00+00:00'
    for _ in range(2):
        assert overview(sid, sync=False)['changes']['accepted'] == 1


def test_g3_unknown_dotenv_and_environment_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv('PINECONE_API_KEY', 'obsolete-placeholder')
    env = tmp_path / '.env'
    env.write_text('PINECONE_API_KEY=obsolete-placeholder\nUNKNOWN_OLD_KEY=unused\n')
    assert Settings(_env_file=env).embed_model == 'voyage-4'


@pytest.mark.parametrize('doc', [{'channel': 'fixture'}, {'source': 'other'}, {}])
def test_g4_unknown_channel_zero_hot(doc):
    from app.model.features import build_features
    X = build_features([{'doc_id': 'a', 'body': 'text', **doc}], np.ones((1, 1024)))
    assert X.shape == (1, 1032)
    assert not X[0, 1024:1029].any()
    assert X[0, 1029] == pytest.approx(np.log1p(4))


@pytest.mark.parametrize('legacy', [False, True])
def test_g5_changed_prep_identity_locked(client, data_dir, monkeypatch, legacy):
    prep_session(data_dir, monkeypatch, started=True, completed=True)
    monkeypatch.setattr('app.routers.preprocessing.threading.Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    response = client.post('/preprocess', json={'sid': 'prepcheck'}) if legacy else client.post('/prep/prepcheck/run')
    assert response.status_code == 409
    assert response.json()['error']['message'] == '라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.'


def test_g6_environment_documentation():
    root = Path(__file__).resolve().parents[2]
    readme = (root / 'README.md').read_text()
    example = (root / '.env.example').read_text()
    assert 'PINECONE_API_KEY' not in readme + example
    assert 'Pinecone' not in readme
    from app.config import Settings
    fields = list(Settings.model_fields)
    for name in fields[fields.index('embed_backend'):fields.index('kappa_floor') + 1]:
        env = 'JEVMODEL_API_KEY' if name == 'jev_api_keys' else name.upper()
        assert env in readme and env in example


def test_c3_unverified_old_result_not_reused_after_finalization(client, data_dir, monkeypatch):
    ref = prep_session(data_dir, monkeypatch, completed=True)
    root = data_dir / 'derived/prepcheck/c1' / ref['prepKey']
    store.write_json(root / 'manifest.json', dict(status='done', compatWritten=True, compatRef='compat.jsonl'))
    store.write_json(root / 'stage_3.json', {})
    (data_dir / 'compat.jsonl').write_text('')
    response = client.post('/prep/prepcheck/run')
    assert response.status_code == 200
    assert response.json()['reused'] is False


@pytest.mark.parametrize('legacy', [False, True])
def test_g5_same_ref_reuse_allowed_after_labeling(client, data_dir, monkeypatch, legacy):
    ref = prep_session(data_dir, monkeypatch, completed=True, started=True)
    store.update_session('prepcheck', {'prep': {'derivedRef': ref, 'status': 'done'}})
    root = data_dir / 'derived/prepcheck/c1' / ref['prepKey']
    store.write_json(root / 'manifest.json', dict(status='done', collectionFinalized=True,
        compatWritten=True, compatRef='compat.jsonl'))
    store.write_json(root / 'stage_3.json', {})
    (data_dir / 'compat.jsonl').write_text('')
    monkeypatch.setattr('app.routers.preprocessing.threading.Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    response = client.post('/preprocess', json={'sid': 'prepcheck'}) if legacy else client.post('/prep/prepcheck/run')
    assert response.status_code == 200
    assert store.load_session('prepcheck')['prep']['derivedRef'] == ref


@pytest.mark.parametrize('guard', ['unfinished', 'labeling'])
def test_legacy_direct_service_guard(data_dir, monkeypatch, guard):
    from app.services.preprocessing import preprocess_data
    from app.jobs.manager import job_manager
    prep_session(data_dir, monkeypatch, completed=guard == 'labeling', started=guard == 'labeling')
    preprocess_data({'sid': 'prepcheck'})
    result = job_manager.get('preprocess', 'prepcheck')
    assert result['status'] == 'error'
    assert ('수집이 끝난 뒤에' if guard == 'unfinished' else '새 버전에서 다시 하세요') in result['error']
    assert not (data_dir / 'derived').exists()


@pytest.mark.parametrize('kind', ['judge', 'monitor'])
def test_c5_environment_selected_fake_workers_subprocess(data_dir, kind):
    import os
    import subprocess
    import sys
    sid, _ = prepared(data_dir)
    if kind == 'monitor':
        labels = labels_for(sid, store.load_session(sid))
        with labels._db() as db:
            db.execute('CREATE TABLE model_predictions (doc_id TEXT, model_id TEXT, payload TEXT)')
            db.executemany('INSERT INTO model_predictions VALUES (?, ?, ?)',
                          [(f'd{i}', 'fake-model', '{"level":"core"}') for i in range(3)])
    script = '''
import sys
from types import SimpleNamespace
import httpx
from app.config import settings
from app.label import judge
from app.model import monitor
requests = []
real_client = httpx.Client
transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(400))
class MockClient(real_client):
    def __init__(self, *a, **kw):
        super().__init__(*a, **{**kw, 'transport': transport})
httpx.Client = MockClient
assert settings.jev_backend == settings.label_gpt_backend == 'fake'
ctx = SimpleNamespace(sid='modeltest', version='v1', run_id='fake-subprocess',
    args={'labeler': 'jev', 'modelId': 'fake-model'}, heartbeat=lambda *a: None,
    should_stop=lambda: False)
(judge if sys.argv[1] == 'judge' else monitor).run_worker(ctx)
assert requests == [], len(requests)
from app.label.overview import caches_for
from app.context.store import load_session
assert caches_for(ctx.sid, load_session(ctx.sid))['jev'].counts()['done'] == 3
'''
    env = dict(os.environ, LOCAL_DATA_DIR=str(data_dir), JEV_BACKEND='fake',
        JEVMODEL_API_KEY='offline-placeholder', LABEL_FAKE_JEV_CROSS='true', LABEL_GPT_BACKEND='fake', EMBED_BACKEND='fake', MONITOR_RATE='1')
    result = subprocess.run([sys.executable, '-c', script, kind],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
