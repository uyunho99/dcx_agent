import pytest
from pydantic import ValidationError

from app.context.models import AlignmentWarning, ProjectContext


def context_data():
    return {
        "bk": "에어컨",
        "oneLiner": "쾌적한 실내 환경을 만드는 제품",
        "researchQuestion": {"text": "사용자가 원하는 것은 무엇인가?"},
        "projectType": {"choice": "renewal"},
        "analysisGoal": {"choice": "needs"},
        "keyMetrics": ["사용 편의성"],
        "constraints": [],
        "positioning": {"price": "value", "market": "challenger"},
        "channels": ["naver_cafe"],
        "productCategory": {"l1": "가전", "source": "user"},
    }


def test_required_fields():
    data = context_data()
    del data["oneLiner"]
    with pytest.raises(ValidationError):
        ProjectContext(**data)


def test_channels_min_one():
    with pytest.raises(ValidationError):
        ProjectContext(**(context_data() | {"channels": []}))


def test_targetscope_optional():
    ctx = ProjectContext(**context_data())
    assert ctx.schemaVersion == 1
    assert ctx.projectType.note == ""
    assert ctx.knownInsights == []
    empty = ProjectContext(**(context_data() | {"targetScope": {}, "futureCustomer": {}}))
    assert empty.targetScope.ageRanges == []
    assert empty.targetScope.genders == []
    assert empty.targetScope.households == []
    assert empty.targetScope.lifeStages == []
    assert empty.targetScope.note == ""
    assert empty.futureCustomer.choices == []


@pytest.mark.parametrize("field,value", [
    ("keyMetrics", []),
    ("schemaVersion", 2),
    ("projectType", {"choice": "invalid"}),
    ("analysisGoal", {"choice": "invalid"}),
    ("positioning", {"price": "invalid", "market": "leader"}),
    ("channels", ["invalid"]),
    ("productCategory", {"source": "user"}),
    ("productCategory", {"l1": "가전", "source": "invalid"}),
    ("targetScope", {"households": ["invalid"]}),
    ("targetScope", {"lifeStages": ["invalid"]}),
    ("futureCustomer", {"choices": ["invalid"]}),
])
def test_invalid_values(field, value):
    with pytest.raises(ValidationError):
        ProjectContext(**(context_data() | {field: value}))


def test_round_trip_and_independent_defaults():
    ctx = ProjectContext(**context_data())
    assert ProjectContext.model_validate_json(ctx.model_dump_json()) == ctx
    ctx.knownInsights.append("기존 지식")
    assert ProjectContext(**context_data()).knownInsights == []


def test_alignment_warning():
    warning = AlignmentWarning(source="constraints", item="예산", reason="확인 필요")
    assert warning.item == "예산"
    with pytest.raises(ValidationError):
        AlignmentWarning(source="invalid", item="예산", reason="확인 필요")
