import hashlib
import json
from pathlib import Path

import pytest

from app.config import settings
from app.label.questions import load_questions
from app.label.rule import SEM
from app.llm.base import validate


@pytest.fixture
def gpt():
    from app.label import gpt
    return gpt


@pytest.fixture
def fake_codex(monkeypatch, data_dir):
    monkeypatch.setattr(settings, 'codex_bin', str(Path(__file__).resolve().parents[1] / 'fakes/fake_codex.py'))
    monkeypatch.setattr(settings, 'codex_timeout_s', 30)
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    return data_dir


def docs(*ids):
    return [{'doc_id': doc_id, 'title': '경험', 'body': '구체적인 경험'} for doc_id in ids]


def item(doc_id):
    return dict(doc_id=doc_id, anchor=True, sem={key: int(key in ('feel', 'act')) for key in SEM}, situation=True, reason_code=None, signal='pain')


def judge(gpt, documents, **kwargs):
    return gpt.judge_batch(documents, '사용 경험', sid='session', ctx_key='context', **kwargs)


def test_prompt_first_line_is_one_liner(gpt, monkeypatch):
    definitions = load_questions()
    definitions['anchor']['instructions'] = '공유 정의를 바꾸면 즉시 반영된다.'
    monkeypatch.setattr(gpt, 'load_questions', lambda: definitions)
    task = gpt.build_task(docs('a'), '사용 경험')
    assert task.task == 'label_gpt'
    assert task.output_schema is gpt.GptBatch
    assert task.instructions.splitlines()[0] == '사용 경험'
    for definition in definitions.values():
        assert definition['instructions'] in task.instructions
        criteria = definition['criteria']
        for text in criteria.values() if isinstance(criteria, dict) else [criteria]:
            assert text in task.instructions
    assert task.instructions.index('공유 정의') < task.instructions.index('"doc_id": "a"')


def test_no_domain_examples():
    root = Path(__file__).resolve().parents[2] / 'app/label'
    for name in ('prompts/gpt_label.q1.md', 'questions.q1.json'):
        text = (root / name).read_text()
        for word in ('에어컨', '보험', '청소기', '분유'):
            assert word not in text


@pytest.mark.parametrize('items, missing', [
    ([item('a')], ['b', 'c']),
    ([item('a'), item('b'), item('b'), item('extra'), {'anchor': True}], ['b', 'c']),
    ([item('a'), dict(item('b'), sem={}), item('c')], ['b']),
])
def test_gpt_partial_batch_requeues_missing(gpt, monkeypatch, items, missing):
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    monkeypatch.setattr(gpt, 'run_many', lambda tasks, **kw: [validate(tasks[0], json.dumps({'items': items}))])
    votes, retry = judge(gpt, docs('a', 'b', 'c'))
    assert retry == missing
    assert set(votes) == {'a', 'b', 'c'} - set(missing)
    assert all(isinstance(vote, gpt.GptVote) for vote in votes.values())


def test_two_batches_then_retry_real_run_many(gpt, fake_codex, monkeypatch):
    monkeypatch.setenv('FAKE_CODEX_LABEL_MODE', 'partial')
    first, retry1 = judge(gpt, docs('b', 'a'))
    second, retry2 = judge(gpt, docs('d', 'c'))
    assert set(first) == {'a'} and retry1 == ['b']
    assert set(second) == {'c'} and retry2 == ['d']
    assert set(judge(gpt, docs(*retry1))[0]) == {'b'}
    assert set(judge(gpt, docs(*retry2))[0]) == {'d'}
    assert judge(gpt, docs('a', 'b')) == (first, retry1)
    roots = list((fake_codex / 'llm_runs').iterdir())
    assert len(roots) == 4
    digest = hashlib.sha256(json.dumps(['a', 'b'], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:12]
    assert len(list((fake_codex / 'llm_runs').glob(f'lbl-session-q1-*-{digest}/manifest.json'))) == 1
    assert all(len((root / 'invocations').read_text().splitlines()) == 1 for root in roots)


def test_codex_backend_used_by_default(gpt, fake_codex, monkeypatch):
    from app.config import Settings
    assert Settings(_env_file=None).label_gpt_backend == 'codex_exec'
    monkeypatch.setattr(settings, 'llm_backend', 'openai_api')
    assert set(judge(gpt, docs('a'))[0]) == {'a'}
    assert len(list((fake_codex / 'llm_runs').glob('*/manifest.json'))) == 1


def test_usage_limit_pauses(gpt, fake_codex, monkeypatch):
    monkeypatch.setenv('FAKE_CODEX_LABEL_MODE', 'usage_limit')
    with pytest.raises(gpt.LabelerPaused) as exc:
        judge(gpt, docs('a'))
    assert str(exc.value) == 'GPT 판정이 사용량 한도로 멈췄습니다. 잠시 뒤 이어서 진행하거나 설정에서 API 경로로 바꾸세요.'
    assert exc.value.usage_limit is True
    monkeypatch.setenv('FAKE_CODEX_LABEL_MODE', 'normal')
    assert set(judge(gpt, docs('a'))[0]) == {'a'}


@pytest.mark.parametrize('backend', ['openai_api', 'fake'])
def test_explicit_backend_selection(gpt, monkeypatch, backend):
    monkeypatch.setattr(settings, 'label_gpt_backend', backend)
    cls = gpt.OpenAIApiBackend if backend == 'openai_api' else gpt.FakeBackend
    monkeypatch.setattr(cls, 'run', lambda self, task: validate(task, json.dumps({'items': [item('a')]})))
    monkeypatch.setattr(gpt, 'run_many', lambda *a, **kw: pytest.fail('Unexpected codex call'))
    assert set(judge(gpt, docs('a'))[0]) == {'a'}


def test_empty_batch(gpt, monkeypatch):
    monkeypatch.setattr(gpt, 'run_many', lambda *a, **kw: pytest.fail('Empty batch executed'))
    assert judge(gpt, []) == ({}, [])


def test_batch_accepts_typed_items(gpt):
    batch = gpt.GptBatch(items=[gpt.GptItem(**item('a'))])
    assert [entry.doc_id for entry in batch.items] == ['a']


def test_fake_backend_runs_without_external_fixture(gpt, monkeypatch):
    monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
    votes, retry = judge(gpt, docs('a'))
    assert retry == []
    assert votes['a'].anchor is False
    assert votes['a'].signal is None


@pytest.mark.parametrize('raw', ['broken', '{}', '{"items": {}}'])
def test_bad_response_requeues_batch(gpt, monkeypatch, raw):
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    monkeypatch.setattr(gpt, 'run_many', lambda tasks, **kw: [validate(tasks[0], raw)])
    assert judge(gpt, docs('a', 'b')) == ({}, ['a', 'b'])


def test_context_changes_run_identity(gpt, fake_codex):
    for ctx_key in ('ctx1', 'ctx2'):
        votes, retry = gpt.judge_batch(docs('a'), '사용 경험', sid='session', ctx_key=ctx_key)
        assert set(votes) == {'a'} and not retry
    assert len(list((fake_codex / 'llm_runs').iterdir())) == 2


def test_non_signal_uses_shared_grade(gpt, monkeypatch):
    response = dict(item('a'), anchor=False)
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    monkeypatch.setattr(gpt, 'run_many', lambda tasks, **kw: [validate(tasks[0], json.dumps({'items': [response]}))])
    assert judge(gpt, docs('a'))[0]['a'].signal is None


def test_empty_answer_can_retry_same_batch(gpt, fake_codex):
    assert set(judge(gpt, docs('a'))[0]) == {'a'}
    root = next((fake_codex / 'llm_runs').iterdir())
    answer = root / 'answers/task-0.json'
    answer.write_text('{"items": []}')
    assert judge(gpt, docs('a')) == ({}, ['a'])
    assert set(judge(gpt, docs('a'))[0]) == {'a'}
    assert (root / 'answers/bad/task-0.json').exists()


def test_build_task_truncates_long_body():
    from app.label.gpt import GPT_BODY_LIMIT, build_task
    long = {'doc_id': 'd1', 'body': '가' * (GPT_BODY_LIMIT + 500), 'title': 't'}
    short = {'doc_id': 'd2', 'body': '짧은 본문'}
    task = build_task([long, short], '한 줄')
    assert '가' * GPT_BODY_LIMIT in task.instructions
    assert '가' * (GPT_BODY_LIMIT + 1) not in task.instructions
    assert '짧은 본문' in task.instructions
    assert len(long['body']) == GPT_BODY_LIMIT + 500
