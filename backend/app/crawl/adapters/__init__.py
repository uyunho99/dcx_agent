"""Channel factories read configuration when called, never at import time."""

from collections.abc import Callable
from contextlib import contextmanager

from app.config import settings
from app.crawl.adapters.base import (
    AdapterBlocked,
    ChannelAdapter,
    FetchedDoc,
    ListItem,
    ListPage,
)
from app.crawl.adapters.fixture import FixtureAdapter
from app.crawl.adapters.youtube import YoutubeAdapter
from app.crawl.adapters.clien import ClienAdapter
from app.crawl.adapters.ppomppu import PpomppuAdapter


REGISTRY: dict[str, Callable[[], ChannelAdapter]] = {
    "fixture": lambda: FixtureAdapter(settings.fixture_corpus_path),
    "youtube": lambda: YoutubeAdapter(),
    "clien": lambda: ClienAdapter(),
    "ppomppu": lambda: PpomppuAdapter(),
}


@contextmanager
def managed_adapter(factory):
    adapter = factory()
    try:
        yield adapter
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            close()


def available_sources() -> list[str]:
    sources = []
    for source, factory in REGISTRY.items():
        with managed_adapter(factory) as adapter:
            if adapter.is_available():
                sources.append(source)
    return sources


__all__ = [
    "AdapterBlocked", "ChannelAdapter", "FetchedDoc", "ListItem", "ListPage",
    "REGISTRY", "available_sources",
]
