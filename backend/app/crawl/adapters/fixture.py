"""Offline CSV adapter. Row identifiers are zero-based, excluding the header."""

import csv
from datetime import date, timedelta
from pathlib import Path
from threading import Lock

from app.config import settings
from app.crawl.adapters.base import FetchedDoc, ListItem, ListPage


_CORPUS_CACHE: dict[tuple[Path, int], list[str]] = {}
_CACHE_LOCK = Lock()


def _row_date(row: int, today: date | None = None) -> str:
    return ((today or date.today()) - timedelta(days=364) + timedelta(days=row % 365)).isoformat()


class FixtureAdapter:
    source = "fixture"

    def __init__(self, corpus_path: str | Path, page_size: int = 100, *, today: date | None = None):
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        self.corpus_path = corpus_path
        self.page_size = page_size
        self.today = today or date.today()
        self._reviews: list[str] | None = None

    def is_available(self) -> bool:
        return bool(settings.enable_fixture_channel and settings.fixture_corpus_path)

    def _load(self) -> list[str]:
        if self._reviews is None:
            path = Path(self.corpus_path).expanduser().resolve()
            with _CACHE_LOCK:
                key = (path, path.stat().st_mtime_ns)
                if key not in _CORPUS_CACHE:
                    with path.open(encoding="utf-8-sig", newline="") as stream:
                        reader = csv.DictReader(stream)
                        if not reader.fieldnames or "review" not in reader.fieldnames:
                            raise ValueError("Fixture CSV must contain a review column")
                        reviews = [row["review"] or "" for row in reader]
                    _CORPUS_CACHE[key] = reviews
                    # Existing instances keep their snapshot; discard old cache versions.
                    for stale_key in list(_CORPUS_CACHE):
                        if stale_key[0] == path and stale_key != key:
                            del _CORPUS_CACHE[stale_key]
                self._reviews = _CORPUS_CACHE[key]
        return self._reviews

    def list_page(self, kw: str, cursor: str | None) -> ListPage:
        start = 0 if cursor is None else int(cursor)
        if start < 0:
            raise ValueError("cursor offset must be nonnegative")
        matches = [(row, review) for row, review in enumerate(self._load()) if kw in review]
        end = start + self.page_size
        items = [
            ListItem(
                url=f"fixture://aircon/{row}",
                title=review[:30],
                snippet=review[:30],
                date=_row_date(row, self.today),
                src_meta={"row": row},
            )
            for row, review in matches[start:end]
        ]
        return ListPage(items, str(end) if end < len(matches) else None, len(matches))

    def fetch(self, item: ListItem) -> list[FetchedDoc]:
        prefix = "fixture://aircon/"
        if not item.url.startswith(prefix):
            raise ValueError("Invalid fixture URL")
        row = int(item.url[len(prefix):])
        if row < 0:
            raise ValueError("Invalid fixture URL")
        body = self._load()[row]
        return [FetchedDoc(
            title=body[:30],
            body=body,
            comments=[],
            date=_row_date(row, self.today),
            src_meta={"row": row},
            access="public",
            author_raw=None,
        )]
