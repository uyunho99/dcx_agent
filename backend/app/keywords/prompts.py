"""Build versioned keyword tasks; context bodies are attached for LLM composition."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.context.labels import LABELS
from app.llm.base import Attachment, LLMTask

from .models import Keyword
from .normalize import BANNED
from .taxonomy import AXES

PROMPT_VERSION = {1: "r1.v3", 2: "r2.v2", 3: "r3.v3", 4: "r4.v3"}
MIN_COUNT = {1: 70, 2: 100, 3: 60, 4: 60}
TONE = {
    "renewal": "기존 사용 중 불만 · 고장 · 관리 부담",
    "new": "아직 충족되지 않은 니즈 · 대체 행동",
    "branding": "인식 · 이미지 · 정체성 · 사회적 시선",
    "ux": "사용 과정의 단계별 불편 · 실수",
}


TASK_FOCUS = {
    "metric": "과제 유형: 지표 개선형 — 첨부 맥락의 핵심 지표와 관련 문항이 떨어지는 순간을 겨냥한다. "
              "이용 과정의 어느 단계 · 어느 순간에 막히고, 기다리고, 헷갈리고, 불안해지는지 그 순간의 사물·현상 단어를 우선 발산한다.",
    "explore": "과제 유형: 탐색·기획형 — 아직 드러나지 않은 맥락을 겨냥한다. "
               "기존 사용 장면 밖의 생활 상황 · 대체 행동 · 인접 니즈로 넓게 발산하고, 이미 아는 것과 비슷한 단어에 머물지 않는다.",
}


@dataclass
class RoundInputs:
    """Round inputs, with add/move events carried by rendered feedback_md.

    context_md is the complete render_context_md result. Its labeled research
    question is quoted in the mission; no additional context field is required.
    Approved manual/suggested keywords also supply desired-direction signals for R3.
    """

    context_md: str
    feedback_md: str | None
    approved: list[Keyword]
    distribution: dict[str, float]
    rejection_signals: str | None
    coverage_signals: str | None
    past_zero_kws: list[str]
    project_type: str
    channels: list[str]
    target_scope_text: str
    product_category: str
    task_mode: str | None = None


class RoundKeyword(BaseModel):
    """Generated Keyword fields kw/axis/sub, plus generation rationale why.

    Persistence fields (id, round, origin, status, etc.) are assigned downstream.
    sub remains a string so T05 normalization can repair unknown sub codes.
    """

    kw: str
    axis: Literal["physical", "psychological", "behavioral"]
    sub: str
    why: str


class RoundOutput(BaseModel):
    """T09 validation envelope: {keywords: [{kw, axis, sub, why}]}.

    Minimum counts are generation targets, not schema rejection thresholds.
    """

    keywords: list[RoundKeyword]


def r3_input_status(state: RoundInputs) -> dict[str, str]:
    """Return ok for supplied signals or nonempty prior zero-result keywords.

    None/blank rejection signals yield empty:no_rejections; None/blank coverage
    signals yield empty:searchad_unconnected. An empty past_zero_kws list yields
    empty:no_prior_session (no usable prior-session signal, not a history check).
    Callers must render connected coverage as nonblank text, even for zero gaps.
    """
    return {
        "rejection": "ok" if _present(state.rejection_signals) else "empty:no_rejections",
        "coverage": "ok" if _present(state.coverage_signals) else "empty:searchad_unconnected",
        "prior_session": "ok" if state.past_zero_kws else "empty:no_prior_session",
    }


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


def _listing(items: list[str], empty: str = "없음.") -> str:
    return "\n".join(f"- {item}" for item in items) or empty


def _research_question(context_md: str) -> str:
    prefix = "- 리서치 질문:"
    for line in context_md.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return "첨부 project_context.md의 리서치 질문을 따른다."


def build_round_task(sid: str, n: Literal[1, 2, 3, 4], state: RoundInputs) -> LLMTask:
    """Read the selected Markdown at call time and strictly format its fields."""
    if n not in PROMPT_VERSION:
        raise ValueError("Keyword round must be 1, 2, 3, or 4")
    channels = ", ".join(
        LABELS["channels"].get(ch, ch) for ch in state.channels
    ) or "지정 없음"
    channel_rules = f"채널별 검색 문법을 따른다. 수집 채널: {channels}."
    if set(state.channels) & {"youtube", "naver_cafe", "ppomppu", "clien", "community"}:
        channel_rules += " 구어 · 줄임말 표현도 허용."
    desired_direction = _listing(
        [f"{kw.kw} ({kw.axis}/{kw.sub})" for kw in state.approved
         if kw.origin in {"manual", "suggested"}],
        empty="직접 추가 없음.",
    )
    values = {
        "prompt_version": PROMPT_VERSION[n],
        "min_count": MIN_COUNT[n],
        "research_question": _research_question(state.context_md),
        "product_category": state.product_category,
        "tone": TONE[state.project_type] if n == 1 else "",
        "task_focus": TASK_FOCUS.get(state.task_mode or "", "") if n == 1 else "",
        "target_scope_text": state.target_scope_text,
        "channel_rules": channel_rules,
        "banned_words": " · ".join(sorted(BANNED)),
        "taxonomy": "\n".join(f"| {axis} | {' · '.join(subs)} |" for axis, subs in AXES.items()),
        "approved_keywords": _listing([f"{kw.kw} ({kw.axis}/{kw.sub})" for kw in state.approved]),
        "category_distribution": _listing([f"{axis}: {state.distribution.get(axis, 0.0)}" for axis in AXES]),
        "rejection_signals": state.rejection_signals if _present(state.rejection_signals) else "거절 없음.",
        "coverage_signals": state.coverage_signals if _present(state.coverage_signals) else "커버리지 정보 없음 — 축 분포 균형에 집중.",
        "desired_direction": desired_direction,
        "past_zero_kws": _listing(state.past_zero_kws),
    }
    template = Path(__file__).with_name("prompts") / f"{PROMPT_VERSION[n]}.md"
    instructions = template.read_text(encoding="utf-8").format_map(values)
    attachments = [Attachment(title="project_context.md", body=state.context_md)]
    if state.feedback_md:
        attachments.append(Attachment(title="keyword_feedback.md", body=state.feedback_md))
    return LLMTask(
        task=f"kw_round_{n}", sid=sid, instructions=instructions,
        attachments=attachments, output_schema=RoundOutput,
    )
