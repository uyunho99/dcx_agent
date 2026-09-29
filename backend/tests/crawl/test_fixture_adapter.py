import csv
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.crawl.adapters import REGISTRY, available_sources
from app.crawl.adapters.fixture import FixtureAdapter


def write_corpus(path, reviews, encoding="utf-8"):
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["review"])
        writer.writerows([review] for review in reviews)
    return path


@pytest.fixture
def corpus(tmp_path):
    reviews = [f"{row}: {'소음' if row % 2 == 0 else '냉방'} 에어컨 후기 " + "긴 본문 " * 12 for row in range(20)]
    return write_corpus(tmp_path / "reviews.csv", reviews), reviews


def collect_pages(adapter, kw):
    pages = []
    cursor = None
    while True:
        page = adapter.list_page(kw, cursor)
        pages.append(page)
        if page.next_cursor is None:
            return pages
        assert isinstance(page.next_cursor, str)
        cursor = page.next_cursor


def test_list_pages_by_100_and_cursor(tmp_path):
    path = write_corpus(tmp_path / "large.csv", [f"에어컨 {row}" for row in range(250)])
    pages = collect_pages(FixtureAdapter(path), "에어컨")
    assert [len(page.items) for page in pages] == [100, 100, 50]
    assert [page.total_hint for page in pages] == [250] * 3
    assert [item.url for page in pages for item in page.items] == [f"fixture://aircon/{row}" for row in range(250)]


def test_query_is_keyword_only(corpus):
    path, reviews = corpus
    adapter = FixtureAdapter(path, page_size=3)
    pages = collect_pages(adapter, "소음")
    assert [len(page.items) for page in pages] == [3, 3, 3, 1]
    items = [item for page in pages for item in page.items]
    assert [item.src_meta["row"] for item in items] == list(range(0, 20, 2))
    assert all("소음" in reviews[item.src_meta["row"]] for item in items)
    assert adapter.list_page("없는 검색어", None).items == []


def test_fetch_returns_body(corpus):
    path, reviews = corpus
    adapter = FixtureAdapter(path, today=date(2026, 9, 29))
    for row, item in enumerate(adapter.list_page("", None).items):
        assert item.url == f"fixture://aircon/{row}"
        assert item.title == reviews[row][:30]
        assert item.date == (date(2026, 9, 29) - timedelta(days=364) + timedelta(days=row % 365)).isoformat()
        assert item.src_meta == {"row": row}
        documents = adapter.fetch(item)
        assert len(documents) == 1
        doc = documents[0]
        assert doc.body == reviews[row]
        assert doc.title == item.title
        assert doc.date == item.date
        assert doc.src_meta == item.src_meta
        assert doc.comments == []
        assert doc.access == "public"
        assert doc.author_raw is None
        assert doc.thread_key == ""


def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_fixture_channel", False)
    monkeypatch.setattr(settings, "fixture_corpus_path", "")
    assert set(REGISTRY) == {"fixture"}
    assert "fixture" not in available_sources()


def test_availability_reads_settings_at_call_time(corpus, monkeypatch):
    path, _ = corpus
    monkeypatch.setattr(settings, "enable_fixture_channel", True)
    monkeypatch.setattr(settings, "fixture_corpus_path", "")
    assert available_sources() == []
    monkeypatch.setattr(settings, "fixture_corpus_path", str(path))
    assert available_sources() == ["fixture"]
    assert REGISTRY["fixture"]().list_page("소음", None).total_hint == 10
    monkeypatch.setattr(settings, "enable_fixture_channel", False)
    assert available_sources() == []


def test_utf8_bom(tmp_path):
    path = write_corpus(tmp_path / "bom.csv", ["소음, 조용함\n두 번째 줄"], "utf-8-sig")
    adapter = FixtureAdapter(path)
    item = adapter.list_page("소음", None).items[0]
    assert adapter.fetch(item)[0].body == "소음, 조용함\n두 번째 줄"


def test_cache_uses_resolved_path_and_mtime(corpus, monkeypatch):
    path, reviews = corpus
    first = FixtureAdapter(path)
    first.list_page("", None)
    original_open = Path.open
    reads = []

    def track_open(self, *args, **kwargs):
        reads.append(self)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", track_open)
    second = FixtureAdapter(path.parent / "." / path.name)
    first.list_page("소음", None)
    second.list_page("소음", None)
    assert reads == []
    previous_mtime = path.stat().st_mtime_ns
    write_corpus(path, ["새 후기"])
    os.utime(path, ns=(previous_mtime + 1_000_000_000,) * 2)
    reads.clear()
    third = FixtureAdapter(path)
    assert third.list_page("새 후기", None).total_hint == 1
    assert len(reads) == 1
    assert first.list_page("", None).total_hint == len(reviews)


def test_missing_review_column(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text("body\nhello\n", encoding="utf-8")
    with pytest.raises(ValueError, match="review"):
        FixtureAdapter(path).list_page("", None)


@pytest.mark.parametrize("page_size", [0, -1])
def test_invalid_page_size(corpus, page_size):
    with pytest.raises(ValueError, match="page_size"):
        FixtureAdapter(corpus[0], page_size=page_size)
