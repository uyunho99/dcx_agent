"""Deterministic project_context.md rendering in input order."""

from enum import Enum

from .labels import LABELS
from .models import KeyMetric, PersonaSeeds, ProjectContext, TargetScope


def _label(group: str, choice: Enum) -> str:
    return LABELS[group][choice.value]


def _with_note(label: str, note: str) -> str:
    return f"{label} ({note})" if note else label


def _items(values: list[str], empty: str = "없음") -> str:
    return ", ".join(values) if values else empty


TASK_DESCRIPTIONS = {
    "metric": "외부·사내 평가 지표를 올리는 과제. 지표가 떨어지는 순간을 우선 탐색",
    "explore": "아직 드러나지 않은 맥락과 기회를 찾는 과제. 넓게 탐색",
}


def _metric(metric: KeyMetric) -> str:
    details = []
    if metric.source:
        details.append(f"출처: {metric.source}")
    if metric.item:
        details.append(f"문항: {metric.item}")
    return _with_note(metric.name, " · ".join(details))


def _personas(seeds: PersonaSeeds) -> list[str]:
    dimensions = LABELS["personaDimensions"]
    lines = ["## 생각하는 페르소나 · 디멘션", ""]
    lines.extend(
        "- " + _with_note(seed.text, _label("personaDimensions", seed.dimension) if seed.dimension else "")
        for seed in seeds.items
    )
    if not seeds.items:
        lines.append("- 없음")
    else:
        tagged = {seed.dimension for seed in seeds.items}
        missing = [label for code, label in dimensions.items() if code not in tagged]
        if missing:
            lines.append(f"- 아직 적지 않은 디멘션: {_items(missing)}")
    lines.extend([
        "",
        "디멘션: " + " · ".join(dimensions.values()),
        "예시는 출발점일 뿐이다. 네 디멘션 각각에서 예시와 비슷한 페르소나에 머물지 말고, 예시와 다른 페르소나와 맥락을 우선 발굴할 것"
        if seeds.exploreBeyond else "예시는 참고 시드이며 제약이 아니다. 범위 밖 발견도 배제하지 말 것",
        "",
    ])
    return lines


def render_context_md(ctx: ProjectContext, known: list[str]) -> str:
    """Render session-level known insights from ``known``, without mutation."""
    category = ctx.productCategory
    target = ctx.targetScope or TargetScope()
    future = ctx.futureCustomer
    lines = [
        "## 0-A 프로젝트 개요",
        "",
        f"- 제품명: {ctx.bk}",
    ]
    if ctx.taskMode is not None:
        lines.append(f"- 과제 유형: {_label('taskMode', ctx.taskMode)} — {TASK_DESCRIPTIONS[ctx.taskMode.value]}")
    lines.extend([
        f"- 한줄 정의: {ctx.oneLiner}",
        f"- 리서치 질문: {ctx.researchQuestion.text}",
    ])
    if ctx.researchQuestion.template:
        lines.append(f"- 질문 템플릿: {ctx.researchQuestion.template}")
    lines.append(f"- 프로젝트 유형: {_with_note(_label('projectType', ctx.projectType.choice), ctx.projectType.note)}")
    if ctx.analysisGoal is not None:
        lines.append(f"- 분석 목표: {_with_note(_label('analysisGoal', ctx.analysisGoal.choice), ctx.analysisGoal.note)}")
    lines.extend([
        f"- 핵심 지표 (방향 지시자, 측정값 아님): {_items([_metric(metric) for metric in ctx.keyMetrics])}",
        f"- 사내 제약: {_items(ctx.constraints)}",
    ])
    for axis, title in (("price", "가격"), ("market", "시장")):
        choice = getattr(ctx.positioning, axis)
        value = _label(axis, choice) if choice is not None else getattr(ctx.positioning, axis + "Text")
        if value:
            lines.append(f"- {title} 포지셔닝: {value}")
    lines.extend([
        f"- 수집 채널: {_items([_label('channels', code) for code in ctx.channels])}",
        f"- 제품 분류: {' > '.join(part for part in (category.l1, category.l2, category.l3) if part)}",
        f"- 제품 분류 출처: {_label('source', category.source)}",
        "",
    ])
    if ctx.personaSeeds is not None:
        lines.extend(_personas(ctx.personaSeeds))
    lines.extend([
        "## 0-B 분석 대상 · 초기 기준선",
        "",
        "분석 대상 초기 기준선 — 우선 탐색하되 범위 밖 발견도 배제하지 말 것, 해석을 조정하지 말 것",
        "",
        f"- 연령대: {_items(target.ageRanges, '전체')}",
        f"- 성별: {_items(target.genders, '전체')}",
        f"- 가구 유형: {_items([_label('households', code) for code in target.households], '전체')}",
        f"- 생애 단계: {_items([_label('lifeStages', code) for code in target.lifeStages], '전체')}",
        f"- 분석 대상 메모: {target.note or '없음'}",
        "- 미래 고객: " + _with_note(
            _items([_label('futureCustomer', code) for code in future.choices], '전체') if future else '전체',
            future.note if future else '',
        ),
        "",
        "## 이미 아는 것",
        "",
    ])
    lines.extend(f"- {item}" for item in known)
    if not known:
        lines.append("- 없음")
    return "\n".join(lines) + "\n"
