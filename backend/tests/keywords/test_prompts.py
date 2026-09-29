from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.keywords.models import Keyword
from app.keywords.prompts import (
    MIN_COUNT, PROMPT_VERSION, TONE, RoundInputs, RoundOutput,
    build_round_task, r3_input_status,
)
from app.keywords.taxonomy import AXES


@pytest.fixture
def state():
    return RoundInputs(
        context_md="## 0-A 프로젝트 개요\n- 리서치 질문: 어떤 상황에서 어려움을 겪는가?\n",
        feedback_md=None, approved=[], distribution={}, rejection_signals=None,
        coverage_signals=None, past_zero_kws=[], project_type="renewal",
        channels=["youtube"], target_scope_text="초기 대상", product_category="제품군",
    )


def test_four_distinct_templates(state):
    assert PROMPT_VERSION == {1: "r1.v1", 2: "r2.v1", 3: "r3.v1", 4: "r4.v1"}
    assert MIN_COUNT == {1: 70, 2: 100, 3: 60, 4: 60}
    tasks = [build_round_task("sid", n, state) for n in range(1, 5)]
    assert len({task.instructions for task in tasks}) == 4
    for n, task in enumerate(tasks, 1):
        assert PROMPT_VERSION[n] in task.instructions
        assert str(MIN_COUNT[n]) in task.instructions
        assert task.task == f"kw_round_{n}"
        assert task.sid == "sid"
        assert task.output_schema is RoundOutput
        headings = ["## 임무", "## 사고 절차", "## 키워드 형태 규칙", "## 분류", "## 출력"]
        positions = [task.instructions.index(h) for h in headings]
        assert positions == sorted(positions)
        assert "어떤 상황에서 어려움을 겪는가?" in task.instructions
        for axis, subs in AXES.items():
            assert axis in task.instructions
            assert all(sub in task.instructions for sub in subs)


def test_no_role_sentence_no_domain_examples(state):
    for n in range(1, 5):
        text = build_round_task("sid", n, state).instructions
        assert all(term not in text for term in ("전문가입니다", "당신은", "에어컨 예시", "보험 예시"))


@pytest.mark.parametrize("project_type,tone", [
    ("renewal", "기존 사용 중 불만 · 고장 · 관리 부담"),
    ("new", "아직 충족되지 않은 니즈 · 대체 행동"),
    ("branding", "인식 · 이미지 · 정체성 · 사회적 시선"),
    ("ux", "사용 과정의 단계별 불편 · 실수"),
])
def test_r1_tone_by_project_type(state, project_type, tone):
    assert TONE[project_type] == tone
    assert tone in build_round_task("sid", 1, replace(state, project_type=project_type)).instructions


def test_r3_empty_inputs_explicit(state):
    text = build_round_task("sid", 3, state).instructions
    assert "거절 없음." in text
    assert "커버리지 정보 없음 — 축 분포 균형에 집중." in text
    assert r3_input_status(state) == {
        "rejection": "empty:no_rejections", "coverage": "empty:searchad_unconnected",
        "prior_session": "empty:no_prior_session",
    }


def desired_direction_block(text):
    return text.split("사용자가 직접 추가 · 이동한 키워드(원하는 방향)\n", 1)[1].split(
        "\n커버리지 신호:", 1
    )[0].strip()


def test_r3_uses_user_moves_when_no_rejections(state):
    manual = [Keyword(id=str(i), kw=kw, axis="physical", sub="time", round=2,
                      origin="manual", status="approved")
              for i, kw in enumerate(["대기시간", "반복작업"])]
    state = replace(state, approved=manual, feedback_md="## 원하는 방향\n- 이동: 탐색부담 → info_search\n")
    text = build_round_task("sid", 3, state).instructions
    wanted = desired_direction_block(text)
    assert wanted == (
        "- 대기시간 (physical/time)\n- 반복작업 (physical/time)\n"
        '첨부 keyword_feedback.md의 "원하는 방향" · "오분류 이동" 항목도 원하는 방향으로 본다.'
    )
    assert "거절 없음." in text


def test_r3_desired_direction_excludes_rejected_feedback(state):
    feedback = "## 원하는 방향\n- 탐색부담\n## 거절\n- [범위 밖] 거절예시단어\n"
    text = build_round_task("sid", 3, replace(state, feedback_md=feedback)).instructions
    wanted = desired_direction_block(text)
    assert "거절예시단어" not in wanted
    assert feedback not in text
    assert wanted == (
        "직접 추가 없음.\n"
        '첨부 keyword_feedback.md의 "원하는 방향" · "오분류 이동" 항목도 원하는 방향으로 본다.'
    )


def test_r3_desired_direction_includes_suggested_only_from_approved(state):
    approved = [
        Keyword(id="suggested", kw="탐색부담", axis="behavioral", sub="info_search",
                round=2, origin="suggested", status="approved"),
        Keyword(id="llm", kw="자동생성단어", axis="physical", sub="time",
                round=2, origin="llm", status="approved"),
    ]
    text = build_round_task("sid", 3, replace(state, approved=approved)).instructions
    assert desired_direction_block(text) == (
        "- 탐색부담 (behavioral/info_search)\n"
        '첨부 keyword_feedback.md의 "원하는 방향" · "오분류 이동" 항목도 원하는 방향으로 본다.'
    )


@pytest.mark.parametrize("n", [1, 2, 3, 4])
@pytest.mark.parametrize("feedback", [None, "", "## 방향\n{사용자 입력}\n"])
def test_attachments_include_feedback_md(state, n, feedback):
    state = replace(state, feedback_md=feedback)
    task = build_round_task("sid", n, state)
    expected = [("project_context.md", state.context_md)]
    if feedback:
        expected.append(("keyword_feedback.md", feedback))
    assert [(a.title, a.body) for a in task.attachments] == expected


def test_r3_populated_signals(state):
    state = replace(state, rejection_signals="문장형 거절", coverage_signals="심리 축 부족",
                    distribution={"physical": 0.8, "psychological": 0.1, "behavioral": 0.1},
                    past_zero_kws=["과거표현"])
    assert r3_input_status(state) == dict.fromkeys(["rejection", "coverage", "prior_session"], "ok")
    text = build_round_task("sid", 3, state).instructions
    for value in ["문장형 거절", "심리 축 부족", "0.8", "과거 0건 키워드", "과거표현"]:
        assert value in text


@pytest.mark.parametrize("channel", ["youtube", "naver_cafe", "ppomppu", "clien"])
def test_channel_search_rules(state, channel):
    text = build_round_task("sid", 1, replace(state, channels=[channel])).instructions
    assert "구어 · 줄임말 표현도 허용" in text
    assert "참고 시드, 제약 아님" in text


def test_round_output_schema():
    item = {"kw": "탐색부담", "axis": "behavioral", "sub": "info_search", "why": "탐색 중 어려움"}
    assert RoundOutput.model_validate({"keywords": [item]}).model_dump() == {"keywords": [item]}
    for invalid in [{**item, "axis": "unknown"}, {k: v for k, v in item.items() if k != "why"}]:
        with pytest.raises(ValidationError):
            RoundOutput.model_validate({"keywords": [invalid]})


def test_templates_loaded_at_call_time_and_strict(state, monkeypatch):
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path.name == "r1.v1.md":
            return "{unknown_placeholder}"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(KeyError, match="unknown_placeholder"):
        build_round_task("sid", 1, state)


def test_invalid_round(state):
    with pytest.raises(ValueError):
        build_round_task("sid", 5, state)
