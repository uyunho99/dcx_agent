from enum import Enum

from app.context import models
from app.context.labels import LABELS
from app.context.models import ProjectContext
from app.context.render import render_context_md


def make_context(**changes):
    data = {
        "bk": "에어컨",
        "oneLiner": "쾌적한 실내 환경을 만드는 제품",
        "researchQuestion": {"text": "어떤 불편이 있는가?", "template": "질문 템플릿"},
        "projectType": {"choice": "renewal", "note": "기존 제품 개선"},
        "analysisGoal": {"choice": "needs", "note": "사용 불편 중심"},
        "keyMetrics": ["편의성", "만족도"],
        "constraints": ["예산 제한"],
        "positioning": {"price": "premium", "market": "new"},
        "channels": ["naver_blog", "fixture"],
        "productCategory": {"l1": "가전", "l2": "냉방", "l3": "에어컨", "source": "llm_estimate"},
        "targetScope": {"ageRanges": ["30대"], "genders": ["여성"], "households": ["single"], "lifeStages": ["early_career"], "note": "우선 검토"},
        "futureCustomer": {"choices": ["watchers"], "note": "구매 전환 탐색"},
        "knownInsights": ["컨텍스트 내부 지식"],
    }
    return ProjectContext(**(data | changes))


def test_render_deterministic():
    ctx = make_context()
    before = ctx.model_dump_json()
    known = ["두 번째 발견", "첫 번째 발견"]
    result = render_context_md(ctx, known)
    assert result.encode() == render_context_md(ctx, known).encode()
    assert result.index(known[0]) < result.index(known[1])
    assert ctx.model_dump_json() == before
    assert known == ["두 번째 발견", "첫 번째 발견"]


def test_render_sections():
    md = render_context_md(make_context(), [])
    headings = ["## 0-A 프로젝트 개요", "## 0-B 분석 대상 · 초기 기준선", "## 이미 아는 것"]
    assert all(heading in md for heading in headings)
    assert md.index(headings[0]) < md.index(headings[1]) < md.index(headings[2])
    assert "분석 대상 초기 기준선 — 우선 탐색하되 범위 밖 발견도 배제하지 말 것, 해석을 조정하지 말 것" in md
    assert md.endswith("## 이미 아는 것\n\n- 없음\n")
    assert "컨텍스트 내부 지식" not in md


def test_render_uses_korean_labels():
    md = render_context_md(make_context(), ["기존 발견"])
    assert "리뉴얼 (기존 제품 개선)" in md
    assert "니즈탐색 (사용 불편 중심)" in md
    for group, code in [("price", "premium"), ("market", "new"), ("channels", "naver_blog"), ("channels", "fixture"), ("source", "llm_estimate"), ("households", "single"), ("lifeStages", "early_career"), ("futureCustomer", "watchers")]:
        assert LABELS[group][code] in md
    for value in ["30대", "여성", "우선 검토", "구매 전환 탐색", "가전", "냉방", "에어컨", "질문 템플릿", "기존 발견"]:
        assert value in md


def test_render_empty_optional_fields():
    md = render_context_md(make_context(targetScope=None, futureCustomer=None), [])
    assert "전체" in md
    assert "None" not in md


def test_labels_cover_every_enum():
    enums = [value for value in vars(models).values() if isinstance(value, type) and issubclass(value, Enum) and value is not Enum]
    assert enums
    for enum in enums:
        codes = {member.value for member in enum}
        assert any(codes == set(labels) for labels in LABELS.values()), enum.__name__
