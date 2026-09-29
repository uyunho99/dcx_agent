"""Deterministic project_context.md rendering in input order."""

from enum import Enum

from .labels import LABELS
from .models import ProjectContext, TargetScope


def _label(group: str, choice: Enum) -> str:
    return LABELS[group][choice.value]


def _with_note(label: str, note: str) -> str:
    return f"{label} ({note})" if note else label


def _items(values: list[str], empty: str = "없음") -> str:
    return ", ".join(values) if values else empty


def render_context_md(ctx: ProjectContext, known: list[str]) -> str:
    """Render session-level known insights from ``known``, without mutation."""
    category = ctx.productCategory
    target = ctx.targetScope or TargetScope()
    future = ctx.futureCustomer
    lines = [
        "## 0-A 프로젝트 개요",
        "",
        f"- 제품명: {ctx.bk}",
        f"- 한줄 정의: {ctx.oneLiner}",
        f"- 리서치 질문: {ctx.researchQuestion.text}",
    ]
    if ctx.researchQuestion.template:
        lines.append(f"- 질문 템플릿: {ctx.researchQuestion.template}")
    lines.extend([
        f"- 프로젝트 유형: {_with_note(_label('projectType', ctx.projectType.choice), ctx.projectType.note)}",
        f"- 분석 목표: {_with_note(_label('analysisGoal', ctx.analysisGoal.choice), ctx.analysisGoal.note)}",
        f"- 핵심 지표 (방향 지시자, 측정값 아님): {_items(ctx.keyMetrics)}",
        f"- 사내 제약: {_items(ctx.constraints)}",
        f"- 가격 포지셔닝: {_label('price', ctx.positioning.price)}",
        f"- 시장 포지셔닝: {_label('market', ctx.positioning.market)}",
        f"- 수집 채널: {_items([_label('channels', code) for code in ctx.channels])}",
        f"- 제품 분류: {' > '.join(part for part in (category.l1, category.l2, category.l3) if part)}",
        f"- 제품 분류 출처: {_label('source', category.source)}",
        "",
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
