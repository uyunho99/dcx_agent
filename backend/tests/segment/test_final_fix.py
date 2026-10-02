"""Final branch review regressions; all providers are offline."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm.base import Attachment, LLMTask, failure
from app.llm.fake import FakeBackend
from app.model.export import _label_entropy
from app.segment import dims, drafts, pipeline
from app.segment.store import SegmentStore
from tests.segment.test_pipeline import Context, setup, confirm_all


def test_null_vote_entropy():
    assert _label_entropy({'source': 'agreed', 'votes_json': None}) == 0


def test_optional_dims_echo(tmp_path, monkeypatch):
    monkeypatch.setattr(FakeBackend, 'fixture_dir', tmp_path)
    (tmp_path / 'segment.dims.echo.json').write_text('{"echo": true}')
    task = LLMTask(task='segment.dims', sid='s', instructions='extract',
        attachments=[Attachment(title=i, body='text') for i in ('a', 'b')], output_schema=dims.DimsOut)
    result = FakeBackend().run(task)
    assert result.ok
    assert [r.doc_id for r in result.data.items] == ['a', 'b']
    assert result.raw == FakeBackend().run(task).raw
    (tmp_path / 'segment.cluster_name.json').write_text('{"echo": true}')
    assert not FakeBackend().run(task.model_copy(update={'task': 'segment.cluster_name', 'output_schema': drafts.ClusterNameOut})).ok


def test_dims_prompt_bounds(monkeypatch):
    captured = []
    monkeypatch.setattr(dims.registry, 'run_task', lambda task: captured.append(task) or failure('backend', 'offline'))
    dims._extract('s', [['d']], {'d': {'body': 'x' * 4000, 'comments': ['x' * 500] + [{'text': 'y'*500}]*12}}, None, '')
    body = json.loads(captured[0].attachments[0].body)
    assert len(body['body']) == 2000
    assert len(body['comments']) == 10
    assert all(len(c['text']) <= 300 for c in body['comments'])


def test_plain_prompts():
    root = Path(dims.__file__).with_name('prompts')
    text = (root / 'dims.v1.md').read_text()
    assert '문서에서 관측된 항목' in text and '추출만 하고 세거나 요약하지 마세요' in text
    assert 'Context 차원' not in text and '코드 정규화' not in text
    assert '중심성 어휘' not in (root / 'persona_draft.v1.md').read_text()
    text = (root / 'context_draft.v1.md').read_text()
    assert '토픽 상위 어휘' not in text and '지배적 제약' not in text


def test_representatives_bounded():
    source = SimpleNamespace(vectors=np.ones((1, 2)), index={'d': 0}, docs={'d': {'body': 'x'*900}})
    assert len(pipeline._reps(source, ['d'])[0]['text']) == 300


def test_draft_prompt_reps_bounded(monkeypatch):
    captured = []
    monkeypatch.setattr(drafts.registry, 'run_task', lambda task: captured.append(task) or failure('backend', 'offline'))
    drafts._draft('s', 'cluster_name', drafts.ClusterNameOut, '', {'reps': [{'text':'x'*900}]})
    assert len(json.loads(captured[0].attachments[0].body)['reps'][0]['text']) == 300


def test_store_wal_and_no_repeated_ddl(tmp_path, monkeypatch):
    store = SegmentStore(tmp_path)
    with store._db() as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert db.execute('PRAGMA user_version').fetchone()[0] > 0
    statements = []
    connect = sqlite3.connect
    def traced(*a, **kw):
        db = connect(*a, **kw)
        db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(sqlite3, 'connect', traced)
    SegmentStore(tmp_path).personas()
    assert not any(s.lstrip().upper().startswith(('CREATE', 'ALTER')) for s in statements)


@pytest.mark.parametrize('message', ['클러스터링할 문서가 없습니다.', '형태소 토큰이 없습니다. 3단계 전처리를 다시 실행하세요.', None])
def test_failure_reason(setup, monkeypatch, message):
    fixture, _ = setup(docs_per_context=4)
    exc = sessions.StoreError(message) if message else ValueError('sensitive')
    def fail(*a, **kw):
        raise exc
    monkeypatch.setattr(pipeline.inputs, 'load_input', fail)
    with pytest.raises(type(exc)):
        pipeline.run(Context(fixture.sid))
    assert sessions.load_session(fixture.sid)['segment']['reason'] == (message or '클러스터링 중 오류가 났습니다. 이어서 진행하거나 다시 실행하세요.')


def test_failure_publication_preserves_original(setup, monkeypatch, caplog):
    fixture, _ = setup(docs_per_context=4)
    exc = ValueError('original')
    def fail(*a, **kw):
        raise exc
    original = pipeline._session
    def publish(sid, version, values, **kw):
        if values.get('status') == 'failed':
            raise OSError('disk')
        original(sid, version, values, **kw)
    monkeypatch.setattr(pipeline.inputs, 'load_input', fail)
    monkeypatch.setattr(pipeline, '_session', publish)
    with pytest.raises(ValueError) as caught:
        pipeline.run(Context(fixture.sid))
    assert caught.value is exc
    assert caplog.records


def test_compact_input_and_resume(setup, monkeypatch):
    fixture, _ = setup(docs_per_context=4)
    pipeline.run(Context(fixture.sid, stop_after='L2'))
    root = version_dir(fixture.sid, 'v1') / 'segment'
    saved = sessions.read_json(root / 'input.json')
    assert not {'docs', 'tokens', 'nouns'} & saved.keys()
    monkeypatch.setattr(pipeline.l1, 'cluster', lambda *a, **kw: pytest.fail('recomputed'))
    monkeypatch.setattr(pipeline.quality, 'resample_ari', lambda *a, **kw: 1.)
    pipeline.run(Context(fixture.sid))
    assert len(SegmentStore.open(fixture.sid, 'v1').docs(limit=10000)) == len(saved['ids'])


def test_numeric_progress_detail(setup):
    fixture, _ = setup(docs_per_context=4)
    ctx = Context(fixture.sid)
    pipeline.run(ctx)
    for step in ('L3', 'drafts'):
        details = [d for _, d in ctx.events if d['step'] == step and 'persona' in d]
        assert details and all(isinstance(d['persona'], int) and d['personas'] >= d['persona'] >= 1 for d in details)


@pytest.mark.parametrize('step', ['dims', 'drafts'])
@pytest.mark.parametrize('kind', ['backend', 'timeout'])
def test_outage_resume_preserves_layers(setup, monkeypatch, step, kind):
    fixture, _ = setup(docs_per_context=4)
    original = pipeline.registry.run_task
    monkeypatch.setattr(pipeline.registry, 'run_task', lambda task: failure(kind, 'offline') if (task.task == 'segment.dims') == (step == 'dims') else original(task))
    try:
        pipeline.run(Context(fixture.sid))
    except BaseException as exc:
        assert type(exc).__name__ == '_LLMUnavailable'
    state = sessions.load_session(fixture.sid)['segment']
    assert state['status'] == 'interrupted'
    assert state['reason'] == 'LLM이 연결되지 않았거나 한도를 넘었습니다. 연결을 확인한 뒤 이어서 진행하세요.'
    confirm_all(fixture.sid)
    store = SegmentStore.open(fixture.sid, 'v1')
    before = store.docs(limit=10000)
    confirmed = [p['confirmed_at'] for p in store.personas()]
    monkeypatch.setattr(pipeline.registry, 'run_task', original)
    for module, name in [(pipeline.l1, 'cluster'), (pipeline.l2, 'personas'), (pipeline.l3, 'contexts')]:
        monkeypatch.setattr(module, name, lambda *a, **kw: pytest.fail('recomputed layers'))
    pipeline.run(Context(fixture.sid))
    stable = lambda rows: [{k: v for k, v in row.items() if k != 'combo_rarity'} for row in rows]
    assert stable(before) == stable(store.docs(limit=10000))
    assert confirmed == [p['confirmed_at'] for p in store.personas()]
    assert all(p['desire_draft'] for p in store.personas())
    assert not sessions.load_session(fixture.sid)['segment'].get('reason')


def test_qa_session_real_pipeline(data_dir, monkeypatch):
    import subprocess
    import sys
    from app.config import settings
    from app.lexicon.knu import polarity
    script = Path(__file__).resolve().parents[1] / 'scripts/make_segment_qa.py'
    result = subprocess.run([sys.executable, str(script), str(data_dir)], capture_output=True, text=True, check=True)
    sid = json.loads(result.stdout)['sid']
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    monkeypatch.setattr(pipeline.registry, 'get_backend', lambda name: FakeBackend())
    for word in ('짜증', '불편', '실망'):
        assert polarity([word]) < 0
    pipeline.run(Context(sid))
    store = SegmentStore.open(sid, 'v1')
    report = sessions.read_json(version_dir(sid, 'v1') / 'segment/stage_6.json')
    actual = (sum('granularity_exceeded' in (p['flags'] or []) for p in store.personas()),
              sum('counter_context' in (c['flags'] or []) for c in store.contexts()),
              len(report['dims']['dims_failed']))
    assert actual[0] >= 1 and actual[1] >= 1 and actual[2] == 0, actual


def test_cached_drafts_do_not_mask_provider_outage(setup, monkeypatch):
    fixture, calls = setup(docs_per_context=4)
    ctx = Context(fixture.sid)
    heartbeat = ctx.heartbeat
    def stop_after_one(progress, detail):
        heartbeat(progress, detail)
        if detail['step'] == 'drafts' and any(n == 'segment.cluster_name' for n, _ in calls):
            ctx.stopped = True
    ctx.heartbeat = stop_after_one
    pipeline.run(ctx)
    monkeypatch.setattr(pipeline.registry, 'run_task', lambda task: failure('backend', 'offline'))
    with pytest.raises(BaseException) as caught:
        pipeline.run(Context(fixture.sid))
    assert type(caught.value).__name__ == '_LLMUnavailable'
    assert sessions.load_session(fixture.sid)['segment']['status'] == 'interrupted'


def test_real_worker_marks_llm_outage_interrupted(setup, monkeypatch):
    import os
    import time
    from app.work.worker import Context as WorkerContext, execute
    from app.work.status import transaction
    fixture, _ = setup(docs_per_context=4)
    monkeypatch.setattr(pipeline.registry, 'run_task', lambda task: failure('backend', 'offline'))
    with transaction(fixture.sid) as db:
        db.execute('INSERT INTO runs(run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,?,?,?)',
                   ('outage', 'v1', 'segment', '{}', os.getpid(), 'running', time.time(), time.time()))
    with pytest.raises(BaseException) as caught:
        execute(WorkerContext(fixture.sid, 'v1', 'segment', {}, 'outage'))
    assert type(caught.value).__name__ == '_LLMUnavailable'
    with transaction(fixture.sid) as db:
        assert db.execute("SELECT state FROM runs WHERE run_id='outage'").fetchone()[0] == 'interrupted'


def test_stop_during_first_noun_build(setup):
    fixture, _ = setup(docs_per_context=4)
    ctx = Context(fixture.sid)
    heartbeat = ctx.heartbeat
    def stop_load(progress, detail):
        heartbeat(progress, detail)
        if detail.get('docs') == 0 and detail.get('total'):
            ctx.stopped = True
    ctx.heartbeat = stop_load
    pipeline.run(ctx)
    assert sessions.load_session(fixture.sid)['segment']['status'] == 'interrupted'
    assert any(d.get('step') == 'load' and d.get('total') for _, d in ctx.events)
    assert 'load' not in sessions.read_json(version_dir(fixture.sid, 'v1') / 'segment/checkpoint.json')['done']
