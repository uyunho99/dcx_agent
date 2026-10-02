"""Deterministic, cumulative feedback for subsequent keyword rounds."""

from contextlib import nullcontext
import os
from pathlib import Path
import re
import tempfile

from app.context.store import assert_writable, locked, read_json, session_dir
from app.keywords.events import KeywordEvent, REJECT_TAGS, load_events
from app.keywords.normalize import norm_key

_LABELS = {
    "irrelevant": "관련성 낮음", "common": "흔함",
    "sentence": "문장형", "misclassified": "오분류",
}


def _inline(value: str | None) -> str:
    """Keep event content on one Markdown line, without creating headings."""
    text = " ".join((value or "").split())
    if text.startswith(("#", "-", ">")):
        return "\\" + text
    return re.sub(r"^(\d+)\.", r"\1\\.", text)


def _keyword(ev: KeywordEvent) -> str:
    return _inline(ev.kw or ev.kwId) or "(키워드 없음)"


def _location(location: dict[str, str] | None) -> str:
    return _inline("/".join((location or {}).get(key, "?") for key in ("axis", "sub")))


def _keys(ev: KeywordEvent) -> list[tuple[str, str]]:
    keys = []
    if ev.kwId:
        keys.append(("id", ev.kwId))
    if ev.kw:
        keys.append(("kw", norm_key(ev.kw)))
    return keys


def _rejection_group(label: str, group: list[KeywordEvent]) -> list[str]:
    if not group:
        return []
    lines = [f"### {label} · {len(group)}건"]
    for ev in group[:8]:
        note = f" — {_inline(ev.note)}" if ev.note else ""
        lines.append(f"- {_keyword(ev)}{note}")
    if len(group) > 8:
        lines.append(f"- 외 {len(group) - 8}건")
        # Preserve free-text feedback even when keyword examples are capped.
        lines.extend(f"- 의견: {_inline(ev.note)}" for ev in group[8:] if ev.note)
    return lines


def render_feedback_md(events: list[KeywordEvent]) -> str:
    directions = [f"- 라운드 {ev.round}: {_inline(ev.text or ev.note)}"
                  for ev in sorted((ev for ev in events if ev.type == "direction"),
                                   key=lambda ev: ev.ts, reverse=True)]
    rejections = []
    rejected = []
    restored = set()
    seen_rejects = set()
    for ev in reversed(events):
        if ev.type in ("unreject", "add", "approve"):
            restored.update(_keys(ev))
        elif ev.type == "reject" and restored.isdisjoint(_keys(ev)):
            key = ("id", ev.kwId) if ev.kwId else ("kw", norm_key(ev.kw or ""))
            if key in seen_rejects:
                continue
            seen_rejects.add(key)
            rejected.append(ev)
    rejected.reverse()
    for tag in REJECT_TAGS:
        group = [ev for ev in rejected if tag in (ev.tags or [])]
        rejections.extend(_rejection_group(f"{tag} ({_LABELS[tag]})", group))
    rejections.extend(_rejection_group("기타", [ev for ev in rejected if not ev.tags]))

    desired, moves = [], []
    moved = {}
    for ev in events:
        if ev.type == "add":
            desired.append(f"- {_keyword(ev)} (추가, 라운드 {ev.round})")
        elif ev.type == "move":
            for key in _keys(ev):
                moved[key] = ev
            moves.append(f"- {_keyword(ev)}: {_location(ev.from_)} → {_location(ev.to)}")
        elif ev.type == "approve":
            prior = next((moved[key] for key in _keys(ev) if key in moved), None)
            if prior is not None:
                desired.append(f"- {_keyword(prior)} (이동 승인, 라운드 {ev.round})")

    sections = [("방향 지시", directions), ("거절 사유", rejections),
                ("원하는 방향", desired), ("오분류 이동", moves)]
    return "\n\n".join(f"## {name}\n" + "\n".join(lines or ["- 없음"])
                       for name, lines in sections) + "\n"


def write_feedback_md(sid: str, *, directory=None) -> str:
    # Imported here because rounds uses this writer for event persistence.
    from app.keywords.rounds import locked as round_locked

    with locked(sid) if directory is None else nullcontext():
        assert_writable(sid)
        directory = directory or session_dir(sid)
        data = read_json(directory / "session.json") or {}
        kept_ids = {kw.get("id") for kw in data.get("keywords", [])}
        hidden_ids = {kw["id"]
                      for number, state in data.get("keywordRounds", {}).items()
                      if round_locked(int(number)) and not state.get("committed")
                      for kw in state.get("keywords", []) if kw.get("id")} - kept_ids
        # Use keyword membership, not the event's possibly historical round tag.
        # Directions and manual additions remain valid user input in every round.
        events = [ev for ev in load_events(sid, directory=directory)
                  if ev.type in ("direction", "add") or ev.kwId not in hidden_ids]
        text = render_feedback_md(events)
        fd, name = tempfile.mkstemp(prefix=".keyword-feedback-", suffix=".tmp", dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, directory / "keyword_feedback.md")
        finally:
            temporary.unlink(missing_ok=True)
        return text
