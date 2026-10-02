"""Offline stage 5 -> real stage 6 -> evidence HTTP/worker integration.

Only the process boundary is replaced: runner.start/status, durable work rows,
worker.execute/KINDS, pipeline, stores and routers all run unchanged.
"""
import json
import os
from pathlib import Path
import runpy
import socket
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from app.config import settings
from app.context import store as sessions
from app.evidence import pipeline
from app.evidence.package import EvidencePackage
from app.evidence.store import EvidenceStore
from app.llm import registry
from app.work import runner, worker
from tests.fixtures.evidence_synth import (
    QueryEmbedder, fake_evidence_backend, make_evidence_session,
)


@pytest.fixture
def offline_worker(monkeypatch):
    attempts, children = [], []

    def blocked(sock, address):
        attempts.append(address)
        pytest.fail(f'Integration attempted a socket connection: {address!r}')

    # TestClient uses no connection; also guard connect_ex (not just connect).
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'embed_dim', 1024)
    monkeypatch.setattr(settings, 'evidence_llm_concurrency', 4)

    class ThreadProcess:
        def __init__(self, command, *, env, **kwargs):
            assert command[:3] == [sys.executable, '-m', 'app.work.worker']
            assert command[3] == 'evidence'
            self.pid = os.getpid()
            context = worker.Context(
                command[command.index('--sid') + 1],
                command[command.index('--version') + 1], command[3],
                json.loads(command[command.index('--args-json') + 1]),
                env['DCX_WORK_RUN_ID'],
            )
            self.thread = threading.Thread(target=worker.execute, args=(context,))
            children.append(self)
            self.thread.start()

        def wait(self):
            self.thread.join(timeout=60)
            assert not self.thread.is_alive(), 'Evidence worker did not terminate'
            return 0

        def kill(self):
            pytest.fail('Unexpected worker launch rollback')

    monkeypatch.setattr(runner, 'subprocess', SimpleNamespace(
        Popen=ThreadProcess, DEVNULL=runner.subprocess.DEVNULL))
    yield attempts
    for child in children:
        child.wait()
    assert attempts == []


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


def bind_backend(monkeypatch, fixture):
    source = pipeline._load(fixture.sid, fixture.version)
    contexts = source['seg'].contexts()
    calls = []
    if hasattr(fixture, 'expected'):
        embedder = QueryEmbedder(fixture, source['source'])
        monkeypatch.setattr(pipeline.known_store, 'get_embedder', lambda: embedder)

    def call(task):
        calls.append(task.task)
        owned = contexts
        if task.task == 'evidence.queries':
            owned = [c for c in contexts if c['context_id'] + ' ·' in task.attachments[0].body]
        docs = {a.title: source['docs'][a.title] for a in task.attachments if a.title in source['docs']}
        if task.task == 'evidence.novelty':
            docs = {r['doc_id']: source['docs'][r['doc_id']]
                    for r in json.loads(task.attachments[0].body)['new_rows']}
        return fake_evidence_backend(owned, docs).run(task)

    monkeypatch.setattr(registry, 'run_task', call)
    return source, calls


def run_and_poll(client, fixture, *, fresh=False):
    base = f'/evidence/{fixture.sid}'
    launched = ok(client.post(base + '/run', params={'version': fixture.version}, json={'fresh': fresh}))
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = ok(client.get(base + '/status', params={'version': fixture.version}))
        if state['status'] == 'done':
            break
        # Stage six invalidates evidence; stale can remain until worker load completes.
        assert state['status'] in ('none', 'stale', 'running'), state
        time.sleep(.02)
    else:
        pytest.fail(f'Evidence did not complete: {state}')
    work = next(w for w in runner.status(fixture.sid) if w['runId'] == launched['runId'])
    assert work['state'] == 'done' and work['error'] is None, work
    assert work['progress'] == 1
    assert state['progress'] == 1
    assert all(c['status'] == 'done' for c in state['contexts']), state
    return state


def assert_package(client, fixture, contexts):
    payload = ok(client.get(f'/evidence/{fixture.sid}/package', params={'version': fixture.version}))
    package = EvidencePackage.model_validate(payload)
    ev = EvidenceStore.open(fixture.sid, fixture.version)
    assert payload == sessions.read_json(ev.path.parent / 'package.json')
    assert package.version == fixture.version
    actual = [c for p in package.personas for c in p.context_evidence]
    assert {c.context_id for c in actual} == {c['context_id'] for c in contexts}
    assert all(c.evidence for c in actual)
    assert all(item.quote and item.quote.verified for c in actual for item in c.evidence)
    completion = ok(client.get(f'/session/{fixture.sid}'))['data']['completion']
    assert completion['segmentDone'] and completion['evidenceDone']
    return package


def test_stage5_to_stage7_offline(client, data_dir, monkeypatch, offline_worker):
    fixture = make_evidence_session(data_dir, clusters=3, personas=(1, 1, 1),
                                    contexts=(2, 2, 2), docs_per_context=12)
    source, calls = bind_backend(monkeypatch, fixture)
    contexts = source['seg'].contexts()
    assert contexts and all(c['confirmed_at'] for c in contexts)
    state = run_and_poll(client, fixture)
    assert set(calls) == {'evidence.queries', 'evidence.tag', 'evidence.novelty'}
    ev = EvidenceStore.open(fixture.sid, fixture.version)
    report = sessions.read_json(ev.path.parent / 'stage_7.json')
    assert state['stage7'] == report
    # Design 4.8, plus implementation diagnostics; independent contract list.
    counters = {'coverage_supplements', 'query_gen_fail', 'new_expansions',
                'rare_fallback', 'dpp_fill', 'untagged', 'lazy_dims', 'llm_calls',
                'cache_hits', 'relevant_false', 'tag_calls', 'act_mismatch', 'persona_query_fail'}
    distributions = {'coverage', 'band_exposure_ratios', 'novelty_distribution',
                     'escalation_candidates', 'reason_code', 'known_match_distribution'}
    assert set(report) == counters | distributions | {'per_tab_counts', 'params'}
    assert all(isinstance(report[k], int) and report[k] >= 0 for k in counters)
    assert all(isinstance(report[k], dict) for k in distributions)
    assert report['llm_calls'] == len(calls) > 0
    assert report['untagged'] == report['query_gen_fail'] == 0
    assert report['cache_hits'] > 0
    assert set(report['coverage']) == {c['context_id'] for c in contexts}
    assert all(v['total'] == 6 and 0 <= v['covered'] <= 6 for v in report['coverage'].values())
    assert report['params'] == ev.snapshot().params
    base = f'/evidence/{fixture.sid}'
    details = {}
    for context in contexts:
        cid = context['context_id']
        for tab in ('all', 'new'):
            detail = ok(client.get(base + f'/contexts/{cid}', params={'tab': tab}))
            details[cid, tab] = detail
            assert detail['tab'] == tab and detail['items']
            assert len(detail['queries']) == 8 and not detail['queryFailed']
            assert [i['docId'] for i in detail['items']] == [r['doc_id'] for r in ev.selected(cid, tab)]
    for tab in ('all', 'new'):
        assert report['per_tab_counts'][tab] == sum(len(details[c['context_id'], tab]['items']) for c in contexts)
    assert_package(client, fixture, contexts)

    # Ordinary second run resumes published queries/novelty and cached tags.
    # A fresh=True run deliberately regenerates queries and novelty.
    cached_tags = source['cache'].get_tags(source['docs'])
    assert cached_tags
    calls.clear()
    second = run_and_poll(client, fixture)
    assert second['run'] != state['run']
    assert calls == []
    assert source['cache'].get_tags(source['docs']) == cached_tags

    # Force recomputation as well: tag-cache reuse must not merely be a
    # consequence of skipping done Context checkpoints on the second run.
    fresh = run_and_poll(client, fixture, fresh=True)
    assert set(calls) == {'evidence.queries', 'evidence.novelty'}
    assert fresh['stage7']['cache_hits'] > 0
    assert source['cache'].get_tags(source['docs']) == cached_tags
    calls.clear()

    cid = contexts[0]['context_id']
    doc_id = details[cid, 'new']['items'][0]['docId']
    added = ok(client.post(f'/known/{fixture.sid}', json={'type': 'doc', 'doc_id': doc_id}), 201)
    assert added['from'] == 'rag' and added['doc_id'] == doc_id
    changed = ok(client.get(base + '/status'))
    assert all(c['knownChanged'] for c in changed['contexts'])
    refreshed = ok(client.post(base + f'/contexts/{cid}/refresh-new', json={'run': fresh['run']}))
    assert refreshed['tab'] == 'new' and refreshed['excludedKnown'] >= 1
    assert doc_id not in [r['docId'] for r in refreshed['items']]
    after_all = ok(client.get(base + f'/contexts/{cid}', params={'tab': 'all'}))['items']
    assert [i['docId'] for i in after_all] == [i['docId'] for i in details[cid, 'all']['items']]
    removed = next(i for i in after_all if i['docId'] == doc_id)
    assert removed['novelty'] is None and removed['noveltyShown'] is False
    assert calls == []
    assert_package(client, fixture, contexts)
    assert offline_worker == []


def test_confirm_all_script_runs_evidence_api(client, data_dir, monkeypatch, offline_worker, capsys):
    """Execute the actual CLI parser/default 1,200-doc QA corpus, then HTTP."""
    script = Path(__file__).resolve().parents[1] / 'scripts/make_segment_qa.py'
    monkeypatch.setenv('EMBED_BACKEND', 'fake')
    monkeypatch.setenv('LLM_BACKEND', 'fake')
    monkeypatch.setattr(sys, 'argv', [str(script), str(data_dir), '--confirm-all'])
    monkeypatch.setattr(sys, 'path', list(sys.path))
    runpy.run_path(str(script), run_name='__main__')
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result['documents'] == 1200
    fixture = SimpleNamespace(sid=result['sid'], version=result['version'])
    source, calls = bind_backend(monkeypatch, fixture)
    contexts = source['seg'].contexts()
    assert contexts and all(c['confirmed_at'] for c in contexts)
    run_and_poll(client, fixture)
    assert_package(client, fixture, contexts)
    assert 'evidence.tag' in calls
    assert offline_worker == []


def test_qa_script_default_fake_echo_full_worker(client, data_dir, monkeypatch, offline_worker):
    """Browser QA data through real registry, fake embedder and worker entry."""
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    monkeypatch.setattr(settings, 'llm_backend_overrides', {})
    monkeypatch.setattr(sys, 'argv', ['make_segment_qa.py', str(data_dir), '--confirm-all'])
    runpy.run_path(str(Path(__file__).parents[1] / 'scripts/make_segment_qa.py'), run_name='__main__')
    # The generator writes a single session into this isolated data directory.
    session_paths = list(data_dir.glob('sessions/*/versions/*/session.json'))
    if not session_paths:
        session_paths = list(data_dir.rglob('versions/v1/session.json'))
    assert len(session_paths) == 1, list(data_dir.rglob('session.json'))
    data = json.loads(session_paths[0].read_text())
    sid = data['sid'] if 'sid' in data else session_paths[0].parents[2].name
    response = ok(client.post(f'/evidence/{sid}/run', json={}))
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        works = runner.status(sid)
        work = next(w for w in works if w['runId'] == response['runId'])
        if work['state'] not in ('running', 'paused'):
            break
        time.sleep(.05)
    status = ok(client.get(f'/evidence/{sid}/status'))
    assert status['status'] == 'done', status
    report = status['stage7']
    with_evidence = sum(row['counts']['all'] > 0 for row in status['contexts'])
    details = [ok(client.get(f'/evidence/{sid}/contexts/{row["id"]}')) for row in status['contexts']]
    metrics = dict(query_gen_fail=report['query_gen_fail'], untagged=report['untagged'],
        contexts_with_evidence=with_evidence, contexts=len(details), tag_calls=report['tag_calls'],
        coverage_min=min(row['coverage'] for row in status['contexts']),
        rare=sum(len(d['rare']) for d in details), counter=sum(len(d['counter']) for d in details),
        undifferentiated=sum(bool(d['undifferentiated']) for d in details))
    print('QA_FIX1_METRICS=' + json.dumps(metrics))
    assert metrics['query_gen_fail'] == metrics['untagged'] == 0
    assert with_evidence == len(details)
    assert metrics['coverage_min'] > 0
    assert metrics['rare'] > 0 and metrics['counter'] > 0
    # Only require escalation when the unchanged QA vectors permit a triple.
    from app.evidence.assemble import undifferentiated_candidate
    source = pipeline._load(sid, data['version'])
    eligible = sum(bool(undifferentiated_candidate(
        [r for r in source['docs'].values() if r['persona_id'] == p['persona_id'] and r['band'] == 'edge'],
        source['vectors'])) for p in source['seg'].personas())
    print('QA_FIX1_ELIGIBLE_PERSONAS=' + str(eligible))
    assert metrics['undifferentiated'] > 0 or eligible == 0
