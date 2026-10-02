import hashlib
import json
import sqlite3
import threading
from copy import deepcopy

import pytest
from app.evidence.cache import TagCache
from app.evidence.tagging import tag_documents, judge_known
from app.llm.base import validate
from app.segment import dims
from app.context import store as sessions
from tests.fixtures.evidence_synth import fake_evidence_backend


@pytest.fixture
def setup(tmp_path):
    docs = {f'd{i}': dict(title='제목', body='본문', comments=[], source='cafe', evidence_level='core') for i in range(20)}
    cache = TagCache(tmp_path / 'tag.sqlite')
    return docs, cache


def runner(docs, edit=None):
    tasks = []
    backend = fake_evidence_backend([], docs)
    def run(task):
        tasks.append(task)
        result = backend.run(task)
        if edit:
            value = result.data.model_dump()
            edit(task, value)
            return validate(task, json.dumps(value, ensure_ascii=False))
        return result
    return run, tasks


def tag(setup, run, **kwargs):
    docs, cache = setup
    return tag_documents('test', list(docs), docs=docs, cache=cache, dims_by_id={}, known_items=[], run_task=run, concurrency=1, **kwargs)


def test_batches_of_eight(setup):
    run, tasks = runner(setup[0])
    result = tag(setup, run)
    assert result.calls == len(tasks) == 3
    assert [len(t.attachments) for t in tasks] == [8, 8, 4]
    assert len(result.tags) == 20 and result.untagged == 0


def test_cache_hit_no_llm(setup):
    run, tasks = runner(setup[0])
    first = tag(setup, run)
    tasks.clear()
    second = tag(setup, run)
    assert second.calls == len(tasks) == 0 and second.cache_hits == 20
    assert first.tags == second.tags


def test_input_truncation(setup):
    docs, cache = setup
    docs['d0'].update(body='b'*1600, comments=[{'text': 'c'*350} for _ in range(12)])
    known = [dict(id='a', type='statement', text='s'*250), dict(id='b', type='doc', text='z'*250)]
    run, tasks = runner(docs)
    tag_documents('test', ['d0'], docs=docs, cache=cache, dims_by_id={}, known_items=known, run_task=run, concurrency=1)
    body = json.loads(tasks[0].attachments[0].body)
    assert len(body['body']) == 1500
    assert body['comments'] == [dict(idx=i, text='c'*300) for i in range(10)]
    assert '#1 ' + 's'*250 in tasks[0].instructions
    assert '#2 ' not in tasks[0].instructions and 'z'*200 not in tasks[0].instructions


def test_situation_from_dims_when_present(setup):
    docs, cache = setup
    values = dict(environment='집', task_goal='숙면', internal_state='불안', resource_constraint='돈', activity_response=None)
    run, _ = runner(docs)
    result = tag_documents('test', ['d0'], docs=docs, cache=cache, dims_by_id={'d0': values}, known_items=[], run_task=run, concurrency=1)
    assert result.tags['d0']['situation'] == dict(state='집 숙면', emotion='불안', barrier='돈')
    assert result.tags['d0']['situation_origin'] == 'dims'


def test_dims_lazy_for_core_without_dims(setup):
    docs, cache = setup
    docs['d1']['evidence_level'] = 'peripheral'
    run, _ = runner(docs)
    result = tag(setup, run)
    path = cache.path.parent / ('dims-' + hashlib.sha256(dims.PROMPT_PATH.read_bytes()).hexdigest() + '.sqlite')
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT doc_id, origin FROM dims').fetchall()
    assert len(rows) == 19 and all(origin == 'lazy' for _, origin in rows)
    assert 'd1' not in dict(rows)
    assert result.lazy_dims == 19


def test_known_judged_per_item(setup, data_dir):
    docs, cache = setup
    old = dict(id='old', type='statement', text='old sentence')
    new = dict(id='new', type='statement', text='new sentence')
    def match(task, value):
        for row in value['items']:
            row['known_match'] = '#1'
    run, tasks = runner(docs, match)
    tag_documents('test', list(docs), docs=docs, cache=cache, dims_by_id={}, known_items=[old], run_task=run, concurrency=1)
    sessions.write_json(sessions.session_dir('test') / 'session.json', {'knownInsights': [old, new]})
    tasks.clear()
    pairs = judge_known('test', list(docs), ['old', 'new'], cache=cache, run_task=run, concurrency=4)
    assert len(pairs) == 40 and all(pairs.values())
    assert len(tasks) == 3
    assert all('new sentence' in t.instructions and 'old sentence' not in t.instructions for t in tasks)
    tasks.clear()
    judge_known('test', list(docs), ['old', 'new'], cache=cache, run_task=run, concurrency=1)
    assert not tasks
    cache.drop_known('old')
    assert not cache.get_known(docs, ['old'])


def test_concurrency_equal_results(setup, tmp_path, monkeypatch):
    docs, cache = setup
    run, _ = runner(docs)
    first = tag(setup, run)
    other = TagCache(tmp_path / 'other' / 'tag.sqlite')
    main = threading.get_ident()
    for name in ('put_tags', 'put_known'):
        original = getattr(other, name)
        def checked(*args, _original=original, **kwargs):
            assert threading.get_ident() == main
            return _original(*args, **kwargs)
        monkeypatch.setattr(other, name, checked)
    write_dims = dims.write_cache
    def checked_dims(*args, **kwargs):
        assert threading.get_ident() == main
        return write_dims(*args, **kwargs)
    monkeypatch.setattr(dims, 'write_cache', checked_dims)
    second = tag_documents('test', list(docs), docs=docs, cache=other, dims_by_id={}, known_items=[], run_task=run, concurrency=4)
    assert first == second


def test_irrelevant_reason_counts(setup):
    def edit(task, value):
        for i, row in enumerate(value['items']):
            row.update(relevant=False, reason_code=['ad', 'no_needs', 'pure_criticism', 'other'][i % 4])
    run, _ = runner(setup[0], edit)
    result = tag(setup, run)
    assert result.reason_counts == dict(ad=5, no_needs=5, pure_criticism=5, other=5)


def test_tag_response_id_mismatch(setup):
    def edit(task, value):
        value['items'] = [r for r in value['items'] if r['doc_id'] not in ('d0', 'd1')]
        alien = deepcopy(value['items'][0]); alien['doc_id'] = 'alien'
        value['items'].append(alien)
    run, tasks = runner(setup[0], edit)
    result = tag(setup, run)
    requested = [a.title for t in tasks for a in t.attachments]
    assert requested.count('d0') == requested.count('d1') == 2
    assert all(requested.count(f'd{i}') == 1 for i in range(2, 20))
    assert all(len(t.attachments) <= 8 for t in tasks)
    assert result.untagged == 2 and result.untagged_ids == ['d0', 'd1']
    assert not {'alien', 'd0', 'd1'} & result.tags.keys()
    assert not setup[1].get_tags(['alien', 'd0', 'd1'])


def test_missing_document_recovers_on_retry(setup):
    attempts = []
    def edit(task, value):
        if any(a.title == 'd0' for a in task.attachments):
            attempts.append(1)
            if len(attempts) == 1:
                value['items'] = [r for r in value['items'] if r['doc_id'] != 'd0']
    run, tasks = runner(setup[0], edit)
    result = tag(setup, run)
    assert result.untagged == 0 and len(result.tags) == 20
    assert [a.title for a in tasks[-1].attachments] == ['d0']


@pytest.mark.parametrize('change', [dict(polarity=2), dict(relevant=False, reason_code=None),
                                     dict(tags=['Sense'])])
def test_invalid_schema_not_cached(setup, change):
    def edit(task, value):
        for row in value['items']:
            row.update(change)
    run, tasks = runner(setup[0], edit)
    result = tag(setup, run)
    assert result.untagged == 20 and result.calls == 6
    assert not setup[1].get_tags(setup[0])


def test_deleted_known_not_projected_from_tag_cache(setup):
    run, _ = runner(setup[0], lambda task, value: [r.update(known_match='#1') for r in value['items']])
    docs, cache = setup
    known = [dict(id='ki', type='statement', text='문장')]
    result = tag_documents('test', list(docs), docs=docs, cache=cache, dims_by_id={}, known_items=known, run_task=run, concurrency=1)
    assert result.tags['d0']['known_match'] == 'ki'
    cache.drop_known('ki')
    result = tag(setup, run)
    assert result.calls == 0 and all(r['known_match'] == 'none' for r in result.tags.values())


def test_request_carries_explicit_ids_and_schema(setup):
    run, tasks = runner(setup[0])
    tag(setup, run)
    task = tasks[0]
    assert '"properties"' in task.instructions
    assert all(json.loads(a.body)['doc_id'] == a.title for a in task.attachments)


def test_switch_model_retags_and_rejudges_known(setup, monkeypatch):
    from app.evidence import tagging
    model = ['old-model']
    monkeypatch.setattr(tagging, '_model', lambda: model[0])
    docs, cache = setup
    known = [dict(id='ki', type='statement', text='문장')]
    run, tasks = runner(docs, lambda task, value: [r.update(known_match='#1') for r in value['items']])
    kwargs = dict(docs=docs, cache=cache, dims_by_id={}, known_items=known, run_task=run, concurrency=1)
    first = tag_documents('test', list(docs), **kwargs)
    assert all(r['known_match'] == 'ki' for r in first.tags.values())
    model[0] = 'new-model'
    tasks.clear()
    run, tasks = runner(docs)
    second = tag_documents('test', list(docs), **{**kwargs, 'run_task': run})
    assert second.cache_hits == 0 and second.calls == 3
    assert all(r['known_match'] == 'none' for r in second.tags.values())
