"""Task-mode focus is confined to R1 and preserves the legacy prompt."""
from dataclasses import replace
from pathlib import Path

import pytest

from app.context import store
from app.keywords import prompts, rounds
from app.keywords.normalize import BANNED
from app.keywords.taxonomy import AXES
from test_prompts import state  # Reuse the existing RoundInputs fixture.


EXPECTED_FOCUS = {
    "metric": "과제 유형: 지표 개선형 — 첨부 맥락의 핵심 지표와 관련 문항이 떨어지는 순간을 겨냥한다. "
              "이용 과정의 어느 단계 · 어느 순간에 막히고, 기다리고, 헷갈리고, 불안해지는지 그 순간의 사물·현상 단어를 우선 발산한다.",
    "explore": "과제 유형: 탐색·기획형 — 아직 드러나지 않은 맥락을 겨냥한다. "
               "기존 사용 장면 밖의 생활 상황 · 대체 행동 · 인접 니즈로 넓게 발산하고, 이미 아는 것과 비슷한 단어에 머물지 않는다.",
}


def assert_focus(state, mode):
    text = prompts.build_round_task("sid", 1, replace(state, task_mode=mode)).instructions
    assert prompts.TASK_FOCUS[mode] == EXPECTED_FOCUS[mode]
    assert f"발산 톤: {prompts.TONE[state.project_type]}\n{EXPECTED_FOCUS[mode]}\n" in text
    assert all(term not in text for term in ("전문가입니다", "당신은", "에어컨 예시", "보험 예시"))


def test_r1_metric_focus(state):
    assert_focus(state, "metric")


def test_r1_explore_focus(state):
    assert_focus(state, "explore")


@pytest.mark.parametrize("mode", [None, "other"])
def test_r1_no_mode_blank(state, mode):
    text = prompts.build_round_task("sid", 1, replace(state, task_mode=mode)).instructions
    assert "과제 유형:" not in text
    templates = Path(prompts.__file__).with_name("prompts")
    legacy = (templates / "r1.v1.md").read_text(encoding="utf-8")
    assert (templates / "r1.v2.md").read_text(encoding="utf-8").replace("{task_focus}\n", "", 1) == legacy
    expected = legacy.format_map({
        "prompt_version": "r1.v1", "min_count": 70,
        "research_question": "어떤 상황에서 어려움을 겪는가?",
        "product_category": state.product_category,
        "tone": prompts.TONE[state.project_type],
        "target_scope_text": state.target_scope_text,
        "approved_keywords": "없음.",
        "banned_words": " · ".join(sorted(BANNED)),
        "channel_rules": "채널별 검색 문법을 따른다. 수집 채널: 유튜브. 구어 · 줄임말 표현도 허용.",
        "taxonomy": "\n".join(f"| {axis} | {' · '.join(subs)} |" for axis, subs in AXES.items()),
    })
    tone_line = f"발산 톤: {prompts.TONE[state.project_type]}\n"
    assert tone_line + "\n" in text
    assert text.replace(tone_line + "\n", tone_line, 1).replace("프롬프트 버전: r1.v2", "프롬프트 버전: r1.v1", 1) == expected


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("mode", ["metric", "explore", None, "other"])
def test_other_rounds_untouched(state, n, mode):
    text = prompts.build_round_task("sid", n, replace(state, task_mode=mode)).instructions
    assert "과제 유형:" not in text
    assert text == prompts.build_round_task("sid", n, state).instructions


@pytest.mark.parametrize("context,expected", [({"taskMode": "metric"}, "metric"), ({}, None)])
def test_rounds_pass_task_mode(data_dir, context, expected):
    store.update_session("test", {"schemaVersion": 2, "keywords": []})
    data = store.load_session("test")
    data["projectContext"] = context
    store.write_json(store.session_dir("test") / "session.json", data)
    (store.session_dir("test") / "project_context.md").write_text("원문 맥락\n- 리서치 질문: 어떤 경험인가?", encoding="utf-8")
    inputs = rounds._inputs("test", store.load_session("test"), 1)
    assert inputs.task_mode == expected
