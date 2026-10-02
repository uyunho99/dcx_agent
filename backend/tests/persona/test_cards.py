import json
from copy import deepcopy

import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.base import failure, validate
from app.persona.cards import generate_card
from app.persona.package import Package, evidence_index
from tests.fixtures.evidence_package import make_package, fake_persona_backend


class RawOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


class Runner:
    """Adapt the shared fake's Persona-wide citations to chunk-local IDs."""
    def __init__(self, package, mutate=None):
        self.package = Package.model_validate(package)
        self.backend = fake_persona_backend(package)
        self.calls = []
        self.mutate = mutate

    def __call__(self, task):
        self.calls.append(task)
        result = self.backend.run(task.model_copy(update={"output_schema": RawOutput}))
        data = json.loads(result.raw)
        if task.task == 'persona.card':
            payload = json.loads(task.attachments[0].body)
            block = next(b for b in self.package.personas if b.persona_evidence.persona_id == payload['persona_id'])
            selected = payload['context_ids']
            keys = [k for k, ref in evidence_index(block).items() if ref.context_id in selected]
            mapping = {key: f'E{i+1}' for i, key in enumerate(keys)}
            for row in data['contexts']:
                for field in ('state', 'emotion', 'barrier'):
                    row[field]['cite'] = [mapping[c] for c in row[field]['cite']]
        if self.mutate:
            self.mutate(task, data)
        return validate(task, json.dumps(data))


def setup(**kwargs):
    raw = make_package(**kwargs)
    return Package.model_validate(raw), Runner(raw)


def test_chunks_of_four():
    package, runner = setup(big_persona_contexts=10)
    result = generate_card('s', package.personas[0], run_task=runner)
    assert result.status == 'done'
    assert [t.task for t in runner.calls] == ['persona.card'] * 3 + ['persona.summary']
    assert [len(json.loads(t.attachments[0].body)['context_ids']) for t in runner.calls[:3]] == [4, 4, 2]
    assert len(result.card['contexts']) == 10


def test_cite_renumbered():
    package, runner = setup(big_persona_contexts=10)
    block = package.personas[0]
    result = generate_card('s', block, run_task=runner)
    refs = evidence_index(block)
    for row, original in zip(result.card['contexts'], block.context_evidence):
        cite = row['state']['cite'][0]
        assert refs[cite].context_id == original.context_id
        assert refs[cite].quote == original.evidence[0].quote
    assert result.card['contexts'][4]['state']['cite'] == ['E18']
    assert result.card['trace'][0]['evidence']['quote'] == block.context_evidence[0].evidence[0].quote.model_dump()


def test_action_from_6c_not_generated():
    package, runner = setup()
    block = package.personas[0]
    block.context_evidence[0].action = '확정된 고유 행동'
    result = generate_card('s', block, run_task=runner)
    assert result.card['contexts'][0]['action'] == '확정된 고유 행동'
    schema = runner.calls[0].output_schema.model_json_schema()
    assert 'action' not in schema['$defs']['ContextOut']['properties']


def test_dims_situation_refined_only():
    package, runner = setup()
    def mutate(task, data):
        if task.task == 'persona.card':
            data['contexts'][0]['state']['text'] = '근거에 없는 완전히 다른 상황'
    runner.mutate = mutate
    result = generate_card('s', package.personas[0], run_task=runner)
    assert result.card['contexts'][0]['state']['text'] == package.personas[0].context_evidence[0].situation.state


def test_target_scope_not_in_prompt():
    package, runner = setup()
    block = package.personas[0]
    block.model_extra['targetScope'] = 'SCOPE_SENTINEL'
    block.persona_evidence.model_extra['projectContext'] = {'targetScope': 'SCOPE_SENTINEL'}
    block.context_evidence[0].evidence[0].model_extra['targetScope'] = 'SCOPE_SENTINEL'
    generate_card('s', block, run_task=runner)
    for task in runner.calls:
        prompt = task.instructions + ''.join(a.body for a in task.attachments)
        assert 'targetScope' not in prompt
        assert 'SCOPE_SENTINEL' not in prompt


def test_desire_goal_equal_6b():
    package, runner = setup()
    block = package.personas[0]
    result = generate_card('s', block, run_task=runner)
    for field in ('persona_id', 'persona_name', 'desire', 'goal'):
        assert result.card[field] == getattr(block.persona_evidence, field)


@pytest.mark.parametrize('failed_task', ['persona.card', 'persona.summary'])
def test_schema_fail_twice_marks_failed(failed_task):
    package, runner = setup(big_persona_contexts=10)
    def mutate(task, data):
        if task.task == failed_task:
            data['unexpected'] = True
    runner.mutate = mutate
    result = generate_card('s', package.personas[0], run_task=runner)
    assert result.status == 'failed' and result.card is None
    assert sum(t.task == failed_task for t in runner.calls) == 2
    runner.mutate = None
    assert generate_card('s', package.personas[1], run_task=runner).status == 'done'


def test_null_when_no_evidence():
    package, runner = setup()
    def mutate(task, data):
        if task.task == 'persona.card':
            for row in data['contexts']:
                for field in ('state', 'emotion', 'barrier'):
                    row[field] = {'text': '지어낸 값', 'cite': []}
    runner.mutate = mutate
    result = generate_card('s', package.personas[-1], run_task=runner)
    for field in ('state', 'emotion', 'barrier'):
        assert result.card['contexts'][-1][field] == {'text': None, 'cite': []}


@pytest.mark.parametrize('value', ['high', 0.8, '매우 높음'])
def test_sensitivity_ordinal_only(value):
    package, runner = setup()
    def mutate(task, data):
        if task.task == 'persona.summary':
            data['sensitivity']['price'] = value
    runner.mutate = mutate
    assert generate_card('s', package.personas[0], run_task=runner).status == 'failed'


@pytest.mark.parametrize('ratios,ok', [([.2, .3, .5], True), ([None]*3, True), ([.3]*3, False), ([None, .5, .5], False), ([-1., 1., 1.], False)])
def test_journey_ratios(ratios, ok):
    package, runner = setup()
    def mutate(task, data):
        if task.task == 'persona.summary':
            data['journey'] = dict(zip(('pre_purchase', 'purchase', 'post_purchase'), ratios))
    runner.mutate = mutate
    assert (generate_card('s', package.personas[0], run_task=runner).status == 'done') is ok


def test_recovery_and_no_retry_for_backend_failure():
    package, runner = setup()
    calls = []
    def recover(task):
        calls.append(task)
        return failure('schema', 'bad') if len(calls) == 1 else runner(task)
    assert generate_card('s', package.personas[0], run_task=recover).status == 'done'
    assert len(calls) == 3
    calls.clear()
    def broken(task):
        calls.append(task)
        return failure('backend', 'unavailable')
    assert generate_card('s', package.personas[0], run_task=broken).card is None
    assert len(calls) == 1


@pytest.mark.parametrize('issue', ['missing', 'duplicate', 'foreign_cite', 'foreign_context'])
def test_invalid_references_and_context_coverage(issue):
    package, runner = setup()
    def mutate(task, data):
        if task.task == 'persona.card':
            if issue == 'missing':
                data['contexts'].pop()
            elif issue == 'duplicate':
                data['contexts'][1] = deepcopy(data['contexts'][0])
            elif issue == 'foreign_cite':
                data['contexts'][0]['state']['cite'] = ['E999']
        elif issue == 'foreign_context':
            data['intent']['basis_context_ids'] = ['unknown']
    runner.mutate = mutate
    assert generate_card('s', package.personas[0], run_task=runner).status == 'failed'


def test_later_chunk_failure_discards_entire_card():
    package, runner = setup(big_persona_contexts=10)
    failed_id = package.personas[0].context_evidence[4].context_id
    def mutate(task, data):
        if task.task == 'persona.card' and data['contexts'][0]['context_id'] == failed_id:
            data['unexpected'] = True
    runner.mutate = mutate
    result = generate_card('s', package.personas[0], run_task=runner)
    assert result.status == 'failed' and result.card is None
    assert len(runner.calls) == 3
    assert all(task.task == 'persona.card' for task in runner.calls)


def test_default_registry_does_not_double_retry(monkeypatch):
    from app.llm import registry
    package, _ = setup()
    calls = []
    class BrokenBackend:
        def run(self, task):
            calls.append(task)
            return validate(task, '{}')
    monkeypatch.setattr(registry, 'get_backend', lambda name: BrokenBackend())
    result = generate_card('s', package.personas[0])
    assert result.status == 'failed' and result.card is None
    assert len(calls) == 2


def test_no_persona_evidence_nulls_summary():
    raw = make_package()
    block = raw['personas'][0]
    block['persona_evidence']['desire_support'] = []
    for context in block['context_evidence']:
        for field in ('evidence', 'counter_evidence', 'rare_evidence'):
            context[field] = []
    package, runner = Package.model_validate(raw), Runner(raw)
    card = generate_card('s', package.personas[0], run_task=runner).card
    assert card['intent']['text'] is None
    assert card['usage_context']['text'] is None
    assert card['jtbd']['text'] is None
    assert set(card['sensitivity'].values()) == {None}
    assert set(card['journey'].values()) == {None}
    assert card['trace'] == []
