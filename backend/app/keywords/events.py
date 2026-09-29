"""Append-only HITL events stored alongside the active session version."""

from datetime import datetime, timezone
import logging
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.context.store import assert_writable, locked, session_dir

REJECT_TAGS = ("irrelevant", "common", "sentence", "misclassified")
RejectTag = Literal["irrelevant", "common", "sentence", "misclassified"]
logger = logging.getLogger(__name__)


class KeywordEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ts: datetime
    round: int = Field(ge=1, le=4)
    type: Literal["direction", "approve", "reject", "move", "add", "unreject"]
    kwId: str | None = None
    kw: str | None = None
    tags: list[RejectTag] | None = None
    note: str | None = None
    text: str | None = None
    from_: dict[str, str] | None = Field(default=None, alias="from")
    to: dict[str, str] | None = None

    @field_validator("ts")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Treat timestamps without an offset as UTC for stable ordering."""
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def append_event(sid: str, ev: KeywordEvent) -> None:
    payload = (ev.model_dump_json(by_alias=True, exclude_none=True) + "\n").encode("utf-8")
    with locked(sid):
        assert_writable(sid)
        path = session_dir(sid) / "keyword_events.jsonl"
        # Keep a damaged/unterminated tail separate from the next complete event.
        if path.exists() and path.stat().st_size:
            with path.open("rb") as stream:
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    payload = b"\n" + payload
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            written = os.write(fd, payload)
            os.fsync(fd)
            if written != len(payload):
                raise OSError("Incomplete keyword event append")
        finally:
            os.close(fd)


def load_events(sid: str) -> list[KeywordEvent]:
    path = session_dir(sid) / "keyword_events.jsonl"
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        return []
    events = []
    with stream:
        for number, line in enumerate(stream, start=1):
            try:
                events.append(KeywordEvent.model_validate_json(line))
            except (ValidationError, ValueError):
                # Do not include user content or raw validation errors in logs.
                logger.warning("Skipping invalid keyword event at line %d", number)
    return events
