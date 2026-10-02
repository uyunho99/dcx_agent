import pytest
from pydantic import ValidationError

from app.context import models
from app.context.models import ProjectContext, Positioning
from test_models import context_data


def test_legacy_rules_unchanged():
    ctx = ProjectContext(**context_data())
    assert ctx.keyMetrics == [models.KeyMetric(name='사용 편의성')]
    for changes in ({'keyMetrics': []}, {'analysisGoal': None}, {'positioning': {}}):
        with pytest.raises(ValidationError):
            ProjectContext(**(context_data() | changes))


def test_metric_requires_metric_only():
    data = context_data() | {'taskMode': 'metric', 'keyMetrics': [{'name': '환자경험 점수', 'source': '보건복지부 환자경험평가', 'item': '수납 대기 시간이 적절했다'}]}
    del data['analysisGoal'], data['positioning']
    assert ProjectContext(**data).keyMetrics[0].source == '보건복지부 환자경험평가'
    with pytest.raises(ValidationError):
        ProjectContext(**(data | {'keyMetrics': [{'name': '  '}]}))


def test_explore_requires_nothing_extra():
    data = context_data() | {'taskMode': 'explore'}
    for field in ('keyMetrics', 'positioning', 'analysisGoal'):
        del data[field]
    ctx = ProjectContext(**data)
    assert ctx.keyMetrics == [] and ctx.analysisGoal is None
    assert ctx.schemaVersion == 1


def test_positioning_blank_and_custom():
    empty = Positioning(price='', market='')
    assert empty.price is None and empty.market is None
    assert Positioning(priceText='  중상가 · 구독형 ').priceText == '중상가 · 구독형'
    for field in ('priceText', 'marketText'):
        with pytest.raises(ValidationError):
            Positioning(**{field: '가' * 41})


@pytest.mark.parametrize('axis,code', [('price', 'premium'), ('market', 'new')])
def test_positioning_both_rejected(axis, code):
    assert ProjectContext(**(context_data() | {'taskMode': 'explore', 'positioning': {axis: code}})).taskMode == 'explore'
    with pytest.raises(ValidationError):
        ProjectContext(**(context_data() | {'taskMode': 'explore', 'positioning': {axis: code, axis + 'Text': '중상가'}}))


def test_mixed_metric_items():
    ctx = ProjectContext(**(context_data() | {'keyMetrics': ['편의성', {'name': '만족도', 'source': '사내'}]}))
    assert ctx.keyMetrics == [models.KeyMetric(name='편의성'), models.KeyMetric(name='만족도', source='사내')]


def test_persona_seed_limits():
    seeds = models.PersonaSeeds(items=[{'text': ' 초진 보호자 ', 'dimension': 'social'}, {'text': '간병인'}])
    assert seeds.items[0].text == '초진 보호자'
    assert seeds.items[1].dimension is None and seeds.exploreBeyond is True
    assert len(models.PersonaSeeds(items=[{'text': '가' * 40}] * 20).items) == 20
    for items in ([{'text': '  '}], [{'text': '가' * 41}], [{'text': '가'}] * 21, [{'text': '가', 'dimension': 'invalid'}]):
        with pytest.raises(ValidationError):
            models.PersonaSeeds(items=items)


def test_unknown_task_mode_rejected():
    with pytest.raises(ValidationError):
        ProjectContext(**(context_data() | {'taskMode': 'other'}))


def test_empty_goal_is_none():
    data = context_data() | {'analysisGoal': {'choice': '', 'note': ''}}
    assert ProjectContext(**(data | {'taskMode': 'explore'})).analysisGoal is None
    with pytest.raises(ValidationError):
        ProjectContext(**data)


def test_goal_with_note_but_no_choice_is_none():
    data = context_data() | {'analysisGoal': {'choice': '', 'note': '메모'}}
    assert ProjectContext(**(data | {'taskMode': 'explore'})).analysisGoal is None


@pytest.mark.parametrize('mode_fields', [{}, {'taskMode': None}])
def test_legacy_goal_with_note_but_no_choice_is_rejected(mode_fields):
    data = context_data() | mode_fields | {'analysisGoal': {'choice': '', 'note': '메모'}}
    with pytest.raises(ValidationError):
        ProjectContext(**data)


def test_null_task_mode_is_legacy():
    data = context_data() | {'taskMode': None}
    assert ProjectContext(**data).taskMode is None
    for field in ('keyMetrics', 'analysisGoal', 'positioning'):
        with pytest.raises(ValidationError):
            ProjectContext(**{key: value for key, value in data.items() if key != field})
