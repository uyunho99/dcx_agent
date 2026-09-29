"""Channel factories read configuration when called, never at import time."""

from collections.abc import Callable

from app.config import settings
from app.crawl.adapters.base import (
    AdapterBlocked,
    ChannelAdapter,
    FetchedDoc,
    ListItem,
    ListPage,
)
from app.crawl.adapters.fixture import FixtureAdapter


REGISTRY: dict[str, Callable[[], ChannelAdapter]] = {
    "fixture": lambda: FixtureAdapter(settings.fixture_corpus_path),
}


def available_sources() -> list[str]:
    return [source for source, factory in REGISTRY.items() if factory().is_available()]


__all__ = [
    "AdapterBlocked", "ChannelAdapter", "FetchedDoc", "ListItem", "ListPage",
    "REGISTRY", "available_sources",
]
