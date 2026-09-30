"""Synchronous crawl contracts; frozen dataclasses hold adapter results."""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.crawl.schema import Comment


@dataclass(frozen=True)
class ListItem:
    url: str
    title: str
    snippet: str
    date: str | None
    src_meta: dict


@dataclass(frozen=True)
class ListPage:
    items: list[ListItem]
    next_cursor: str | None
    total_hint: int | None


@dataclass(frozen=True)
class FetchedDoc:
    title: str
    body: str
    comments: list[Comment]
    date: str | None
    src_meta: dict
    access: Literal["public", "restricted"]
    author_raw: str | None
    thread_key: str = ""


class AdapterBlocked(Exception):
    """Real adapters raise this on HTTP 403 or 429."""


class ChannelAdapter(Protocol):
    source: str

    def list_page(self, kw: str, cursor: str | None) -> ListPage: ...

    def fetch(self, item: ListItem) -> list[FetchedDoc]: ...

    def is_available(self) -> bool:
        """Report whether this channel is configured for use."""
        ...
