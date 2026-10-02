"""T5 query contract, bounded regeneration and deterministic fallback."""
from copy import deepcopy
import json

import pytest

from app.context import store as sessions
from app.evidence.params import QUERY_DIMS
from app.evidence.queries import PersonaQueryOut, generate_queries, validate_queries
from app.evidence.store import EvidenceStore
from app.llm.base import failure, validate
from tests.fixtures.evidence_synth import fake_evidence_backend


@pytest.fixture
def inputs(data_dir):
    persona = dict(persona_id='p1', name='절약하는 나', desire='편안한 휴식',
                   goals=['숙면'], keywords=['리모컨', '예약'])
    contexts = [dict(context_id=f'c{i}', name=f'취침 {i}', action='예약 운전',
                     dominant_constraint='전기료 부담', keywords=['냉방', '예약', '숙면', '절약'])
                for i in range(2)]
    return persona, contexts


def output(contexts):
    backend = fake_evidence_backend(contexts)
    # Use the committed fake through its real output-schema validation.
    from app.llm.base import LLMTask
    task = LLMTask(task='evidence.queries', sid='test', instructions='',
                   attachments=[], output_schema=PersonaQueryOut)
    return backend.run(task).data.model_dump()


def runner(*responses):
    tasks = []

    def run(task):
        tasks.append(task)
        response = responses[min(len(tasks) - 1, len(responses) - 1)]
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, dict):
            return response
        return validate(task, json.dumps(response, ensure_ascii=False))
    return run, tasks


def test_valid_output_saved(inputs):
    persona, contexts = inputs
    run, tasks = runner(output(contexts))
    result = generate_queries('test', persona, contexts, '시원한 생활', run_task=run)
    assert result.calls == len(tasks) == 1 and result.failed == []
    assert len(result.persona_rows) == 3
    assert len({r['dim'] for r in result.persona_rows}) == 3
    store = EvidenceStore.open('test', 'v1')
    store.write_queries('persona:p1', result.persona_rows)
    assert len(store.queries('persona:p1')) == 3
    for cid, rows in result.context_rows.items():
        assert [r['dim'] for r in rows] == list(QUERY_DIMS)
        assert all(r['text'].strip() and r['origin'] == 'llm' for r in rows)
        store.write_queries(f'context:{cid}', rows)
        assert len(store.queries(f'context:{cid}')) == 8
    body = tasks[0].attachments[0].body
    assert body.splitlines()[0] == '시원한 생활'
    assert 'c0 · 예약 운전 · 주된 제약: 전기료 부담 · 키워드: 냉방, 예약, 숙면, 절약' in body
    assert all(word in body for word in ['절약하는 나', '편안한 휴식', '숙면', '리모컨'])


@pytest.mark.parametrize('anchors', [['c0'], ['c0', 'c1', 'unknown']])
def test_anchor_union_must_cover_contexts(inputs, anchors):
    value = output(inputs[1])
    value['anchor_context_ids'] = anchors
    assert any('anchor_context_ids' in v for v in validate_queries(PersonaQueryOut(**value), ['c0', 'c1']))


@pytest.mark.parametrize('mode', ['blank', 'missing_key', 'missing_context', 'extra_key'])
def test_empty_key_rejected(inputs, mode):
    value = output(inputs[1])
    if mode == 'blank':
        value['context_queries']['c0']['Sense'] = ' \n '
    elif mode == 'missing_key':
        del value['context_queries']['c0']['Sense']
    elif mode == 'missing_context':
        del value['context_queries']['c0']
    else:
        value['context_queries']['c0']['extra'] = '나는 쉬고 싶어요.'
    assert validate_queries(PersonaQueryOut(**value), ['c0', 'c1'])


@pytest.mark.parametrize('word', ['페르소나', '클러스터', '컨텍스트', '세그먼트', '인사이트', '소비자는', '사용자는', '고객은'])
def test_forbidden_words_rejected(inputs, word):
    value = output(inputs[1])
    value['context_queries']['c0']['Sense'] = f'{word} 시원해요.'
    assert any('c0' in v and word in v for v in validate_queries(PersonaQueryOut(**value), ['c0', 'c1']))


def test_regenerates_once_with_reasons(inputs):
    persona, contexts = inputs
    good = output(contexts)
    bad = deepcopy(good)
    bad['context_queries']['c0']['Sense'] = '사용자는 편해요.'
    bad['context_queries']['c1']['Feel'] = ''
    bad['anchor_context_ids'] = ['c0']
    reasons = validate_queries(PersonaQueryOut(**bad), ['c0', 'c1'])
    run, tasks = runner(bad, good)
    result = generate_queries('test', persona, contexts, '생활', run_task=run)
    assert result.calls == len(tasks) == 2 and result.failed == []
    assert all(reason in tasks[1].instructions for reason in reasons)
    assert all(r['origin'] == 'regen' for rows in result.context_rows.values() for r in rows)


def test_fallback_after_second_failure(inputs):
    persona, contexts = inputs
    bad = output(contexts)
    bad['context_queries']['c0']['Act'] = ''
    run, tasks = runner(bad)
    result = generate_queries('test', persona, contexts, '생활', run_task=run)
    assert result.calls == len(tasks) == 2
    assert result.failed == ['c0']  # caller records query_gen_fail for these IDs
    assert result.context_rows['c0'] == [dict(dim=dim, text='취침 0 냉방 예약 숙면', origin='fallback') for dim in QUERY_DIMS]
    assert all(r['origin'] == 'regen' for r in result.context_rows['c1'])


def test_keywords_filtered_by_stopwords(inputs):
    persona, contexts = inputs
    sessions.write_json(sessions.session_dir('test') / 'session.json', {'projectContext': {'bk': '에어 컨'}})
    noise = ['사용', '정말', '가', '123', '에어컨', '무풍에어컨']
    persona['keywords'] = noise + ['리모컨']
    contexts[0]['keywords'] = noise + ['냉방', '예약', '숙면', '절약']
    bad = output(contexts)
    bad['context_queries']['c0']['Act'] = ''
    run, tasks = runner(bad)
    original = deepcopy((persona, contexts))
    result = generate_queries('test', persona, contexts, '생활', run_task=run)
    for task in tasks:
        body = task.attachments[0].body
        assert not any(word in body for word in noise)
        assert '리모컨' in body
    assert result.context_rows['c0'][0]['text'] == '취침 0 냉방 예약 숙면'
    assert (persona, contexts) == original


@pytest.mark.parametrize('response', [failure('backend', 'offline'), RuntimeError('offline'), {'bad': 'schema'}])
def test_backend_or_schema_failure_is_bounded(inputs, response):
    run, tasks = runner(response)
    result = generate_queries('test', *inputs, '생활', run_task=run)
    assert result.calls == len(tasks) == 2
    assert result.failed == ['c0', 'c1']
    assert len(result.persona_rows) == 3
    assert all(r['origin'] == 'fallback' for r in result.persona_rows)
    assert all(r['origin'] == 'fallback' for rows in result.context_rows.values() for r in rows)


@pytest.mark.parametrize('value', [{'desire_check': ['하나'], 'artifact': ['둘']},
                                  {'desire_check': ['나는 쉬어요.', '사용자는 쉬어요.'], 'artifact': ['나는 예약해요.']}])
def test_invalid_persona_queries_rejected(inputs, value):
    payload = output(inputs[1])
    payload['persona_query'] = value
    assert validate_queries(PersonaQueryOut(**payload), ['c0', 'c1'])


def test_missing_anchor_falls_back_only_affected_context(inputs):
    persona, contexts = inputs
    bad = output(contexts)
    bad['anchor_context_ids'] = ['c1', 'c1']
    run, _ = runner(bad)
    result = generate_queries('test', persona, contexts, '생활', run_task=run)
    assert result.failed == ['c0']
    assert result.context_rows['c1'][0]['origin'] == 'regen'


@pytest.mark.parametrize('words,expected', [([], '취침 0'), (['사용', '냉방'], '취침 0 냉방')])
def test_fallback_does_not_pad_short_keyword_lists(inputs, words, expected):
    persona, contexts = inputs
    contexts[0]['keywords'] = words
    run, _ = runner(failure('backend', 'offline'))
    result = generate_queries('test', persona, contexts, '생활', run_task=run)
    assert all(row['text'] == expected for row in result.context_rows['c0'])
