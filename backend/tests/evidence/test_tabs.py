"""T9 contracts: pure tabs, cached refresh and one novelty judgment per Context."""
from copy import deepcopy
import json
from unittest.mock import Mock

import numpy as np
import pytest

from app.evidence.cache import TagCache
from app.evidence.tabs import all_tab, default_tab, known_exclusions, new_tab, refresh_new
from app.evidence.novelty import apply_novelty, core_representatives, judge_novelty
from app.llm.fake import FakeBackend


def pool(n=12):
    rows = [dict(doc_id=f'd{i}', relevance=1-i/(n+1), band='core') for i in range(n)]
    tags = {r['doc_id']: dict(relevant=True, known_match='none') for r in rows}
    vectors = dict(zip(tags, np.eye(n)))
    docs = {i: dict(body=f'Original {i}', tagProbs=dict(sense=1, feel=1, think=1, act=1)) for i in tags}
    return rows, tags, vectors, docs


def ids(result):
    return [r['doc_id'] for r in result.rows]


def test_new_excludes_handed_match_dup():
    rows, tags, vectors, docs = pool(5)
    tags['d1']['known_match'] = 'ki1'
    for doc_id, cosine in [('d2', .96), ('d3', .94), ('d4', .95)]:
        vectors[doc_id] = np.array([cosine, np.sqrt(1-cosine**2), 0, 0, 0]) * 3
    excluded = known_exclusions(rows, tags, {'d0'}, np.array([vectors['d0']])*2, vectors)
    assert excluded == dict(d0='handed', d1='match', d2='dup', d4='dup')
    result = new_tab('c1', rows, tags, vectors, docs, handed_doc_ids={'d0'},
                     handed_vectors=np.array([vectors['d0']]))
    assert ids(result) == ['d3']


@pytest.mark.parametrize('enough, rounds, size', [(True, 2, 10), (False, 3, 4)])
def test_expand_until_ten_max_three(enough, rounds, size):
    rows, tags, vectors, docs = pool(160)
    batches = [rows[1:51], rows[51:101], rows[101:151]]
    for row in rows[1:]:
        tags[row['doc_id']]['relevant'] = False
    for row in (rows[51:61] if enough else [rows[1], rows[51], rows[101]]):
        tags[row['doc_id']]['relevant'] = True
    initial = {'d0': tags['d0']}
    expand = Mock(side_effect=batches)
    prepare = Mock(side_effect=lambda batch: {r['doc_id']: tags[r['doc_id']] for r in batch})
    result = new_tab('c1', rows[:1], initial, vectors, docs, expand=expand, prepare=prepare)
    assert result.rounds == rounds and len(result.rows) == size
    assert expand.call_args_list == [((50,),)] * rounds
    assert prepare.call_count == rounds
    assert initial == {'d0': tags['d0']}
    assert result.selection.dpp_fill == 0


def test_excluded_count_message_value():
    rows, tags, vectors, docs = pool(3)
    tags['d1']['known_match'] = 'ki1'
    result = new_tab('c1', rows + rows, tags, vectors, docs, handed_doc_ids={'d0'})
    assert result.excluded_known == 2
    assert result.message == '2건이 Known Insight와 같아 빠졌습니다 → 전체 탭에서 보기'


def test_refresh_new_zero_llm(monkeypatch):
    args = pool()
    before = new_tab('c1', *args)
    llm = Mock(side_effect=AssertionError('refresh must not call LLM'))
    monkeypatch.setattr('app.llm.registry.get_backend', llm)
    monkeypatch.setattr('app.evidence.tagging._collect', llm)
    cached_expand = Mock(return_value=args[0][10:])
    after = refresh_new('c1', args[0][:10], *args[1:], known_items=[dict(id='ki1', type='doc', origin='rag', doc_id='d0')],
                        cached_expand=cached_expand)
    llm.assert_not_called()
    cached_expand.assert_called_once_with(50)
    assert after.params['NEW_EXPAND_MAX'] == 3
    assert 'd0' in ids(before) and 'd0' not in ids(after)
    assert len(after.rows) == 10
    assert args[1]['d0']['known_match'] == 'none'


def test_all_tab_known_badge():
    args = pool(3)
    args[1]['d0']['known_match'] = 'ki1'
    result = all_tab(*args, known_items=[dict(id='ki1', type='statement')])
    assert ids(result) == ['d0', 'd1', 'd2']
    assert result.rows[0]['known_match'] == 'ki1'
    assert result.rows[0]['novelty'] is None
    assert default_tab('context') == 'new'
    assert default_tab('desire_support') == default_tab('counter') == 'all'


def test_known_deleted_midrun(tmp_path):
    args = pool(3)
    args[1]['d0']['known_match'] = 'ki_deleted'
    cache = TagCache(tmp_path / 'tag.sqlite')
    cache.put_known({('d0', 'ki_deleted'): True}, 'fake')
    known = [dict(id='ki_deleted', type='statement')]
    assert 'd0' not in ids(new_tab('c1', *args, known_items=lambda: known))
    def expand(_):
        cache.drop_known('ki_deleted')
        known.clear()
        return []
    result = new_tab('c1', *args, known_items=lambda: known, expand=expand)
    assert 'd0' in ids(result) and result.excluded_known == 0
    assert cache.get_known(['d0'], ['ki_deleted']) == {}
    assert all_tab(*args, known_items=known).rows[0]['known_match'] == 'none'


def test_new_coverage_supplement_is_filtered_and_prepared():
    rows, tags, vectors, docs = pool(4)
    for doc in docs.values():
        doc['tagProbs'] = {'sense': 1}
    docs['d3']['tagProbs'] = dict(feel=1, think=1, act=1)
    tags['d2']['known_match'] = 'ki1'
    supplement = Mock(return_value=rows[1:])
    prepare = Mock(side_effect=lambda batch: {r['doc_id']: tags[r['doc_id']] for r in batch})
    result = new_tab('c1', rows[:1], tags, vectors, docs, handed_doc_ids={'d1'},
                     supplement=supplement, prepare=prepare)
    assert ids(result) == ['d0', 'd3']
    assert result.selection.coverage == 4 and result.excluded_known == 2
    assert supplement.call_count == prepare.call_count == 1
    assert supplement.call_args.args[1] == 15


def test_novelty_only_new_tab():
    all_rows = [dict(doc_id='a', novelty='high'), dict(doc_id='b')]
    new_rows = [dict(doc_id='b'), dict(doc_id='c')]
    before = deepcopy((all_rows, new_rows))
    all_result, new_result = apply_novelty(all_rows, new_rows, {'a': ('high', 'ignored'), 'b': ('low', 'known'), 'c': ('high', 'new')})
    assert all_result[0]['novelty'] is None and all_result[0]['novelty_reason'] is None
    assert all_result[1]['novelty'] == 'low'
    assert new_result[1]['novelty'] == 'high'
    assert (all_rows, new_rows) == before


@pytest.mark.parametrize('level, show', [('none', False), ('low', False), ('medium', False), ('high', True), ('very_high', True)])
def test_novelty_show_threshold(level, show):
    _, rows = apply_novelty([], [dict(doc_id='a')], {'a': (level, 'reason')})
    assert rows[0]['show_novelty'] is show


def test_novelty_once_with_final_ten_core_five_and_known():
    rows, _, vectors, docs = pool(12)
    rows = [dict(r, **docs[r['doc_id']]) for r in rows]
    rows[0]['band'] = 'supporting'
    reps = core_representatives(rows, vectors, vectors['d11'])
    assert len(reps) == 5 and reps[0]['doc_id'] == 'd11'
    assert all(r['band'] == 'core' for r in reps)
    known = [dict(id='ki1', type='statement', text='Existing insight')]
    output = [dict(doc_id=r['doc_id'], novelty='high', reason='New experience') for r in rows[:10]]
    output += [dict(doc_id='alien', novelty='low', reason='Ignored')]
    backend = FakeBackend(responses={'evidence.novelty': json.dumps({'items': output})})
    run = Mock(side_effect=backend.run)
    result = judge_novelty('sid', {'context_id': 'c1'}, rows[:10], reps, known, run_task=run)
    assert len(result) == 10 and 'alien' not in result
    run.assert_called_once()
    task = run.call_args.args[0]
    assert task.task == 'evidence.novelty'
    payload = json.loads(task.attachments[0].body)
    assert [r['doc_id'] for r in payload['new_rows']] == [r['doc_id'] for r in rows[:10]]
    assert [r['body'] for r in payload['new_rows']] == [r['body'] for r in rows[:10]]
    assert [r['doc_id'] for r in payload['core_reps']] == [r['doc_id'] for r in reps]
    assert all('tagProbs' not in r for r in payload['new_rows'])
    assert payload['known_items'] == known


def test_empty_and_failed_novelty_no_retry():
    run = Mock(side_effect=FakeBackend(responses={}).run)
    assert judge_novelty('sid', {}, [], [], [], run_task=run) == {}
    run.assert_not_called()
    assert judge_novelty('sid', {}, [{'doc_id': 'a'}], [], [], run_task=run) == {}
    run.assert_called_once()


def test_only_rag_documents_are_handed():
    args = pool(3)
    known = [dict(id='statement', type='statement', origin='stage0', doc_id='d0'),
             dict(id='drawer', type='doc', origin='drawer', doc_id='d1'),
             dict(id='rag', type='doc', **{'from': 'rag'}, doc_id='d2')]
    result = new_tab('c1', *args, known_items=known)
    assert ids(result) == ['d0', 'd1']
    assert result.exclusions == {'d2': 'handed'}


@pytest.mark.parametrize('level, reason', [('extreme', 'reason'), ('high', 'two\nlines')])
def test_novelty_schema_rejects_invalid_output(level, reason):
    run = Mock(side_effect=FakeBackend(responses={'evidence.novelty': json.dumps({
        'items': [dict(doc_id='a', novelty=level, reason=reason)]})}).run)
    assert judge_novelty('sid', {}, [{'doc_id': 'a'}], [], [], run_task=run) == {}
    run.assert_called_once()
