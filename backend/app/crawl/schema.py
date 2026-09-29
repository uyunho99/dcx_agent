"""JSON-compatible crawl document fields from design section 2.5."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Comment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    depth: int
    date: str
    author_hash: str


class Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    source: Literal["naver_cafe", "naver_blog", "youtube", "ppomppu", "clien", "fixture"]
    src_meta: dict[str, Any]
    kw: str
    kw_axis: str
    kw_sub: str
    kw_hits: list[str]
    title: str
    body: str
    comments: list[Comment]
    date: str
    url: str
    fetch_level: Literal["full", "snippet"]
    access: Literal["public", "restricted"]
    snippet: str
    author_hash: str
    crawled_at: str
