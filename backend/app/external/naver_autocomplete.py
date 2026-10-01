"""Keyless Naver autocomplete, with ranked results and an offline fixture backend."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from app.config import settings
from app.keywords.normalize import norm_key

client_factory = httpx.Client
_URL = 'https://ac.search.naver.com/nx/ac'
_PARAMS = dict(con='1', frm='nv', ans='2', r_format='json', r_enc='UTF-8',
               r_unicode='0', t_koreng='1', run='2', rev='4', q_enc='UTF-8', st='100')
_FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/autocomplete/suggestions.json'


@dataclass
class AutocompleteResult:
    queries: list[tuple[str, int]]
    failed: int
    total: int


class AutocompleteUnavailable(RuntimeError):
    """No seed produced usable autocomplete results."""


def _parse(payload) -> list[tuple[str, int]]:
    if not isinstance(payload, dict):
        raise ValueError('Invalid autocomplete response')
    items = payload.get('items')
    if not isinstance(items, list) or not items or not isinstance(items[0], list):
        raise ValueError('Invalid autocomplete items')
    queries = []
    for rank, row in enumerate(items[0][:10], start=1):
        if (not isinstance(row, list) or not row or not isinstance(row[0], str)
                or not norm_key(row[0])):
            raise ValueError('Invalid autocomplete query')
        queries.append((row[0], rank))
    if not queries:
        raise ValueError('Empty autocomplete results')
    return queries


def _load(seed: str, client: httpx.Client | None, fake: bool):
    if fake:
        return json.loads(_FIXTURE.read_text(encoding='utf-8'))
    response = client.get(
        _URL, params={**_PARAMS, 'q': seed},
        headers={'User-Agent': 'Mozilla/5.0 (compatible; DCX/2.0)'}, timeout=10,
    )
    response.raise_for_status()
    return response.json()


def suggestions(seeds: list[str], client: httpx.Client | None = None,
                sleep: Callable[[float], None] = time.sleep,
                on_progress: Callable[[], None] | None = None) -> AutocompleteResult:
    """Keep each normalized query's best rank, in first-seen query order.

    Failed seeds count once; invalid responses contribute no partial rows.
    Caller-owned clients remain open. Fake mode never constructs an HTTP client.
    """
    fake = settings.autocomplete_backend == 'fake'
    owned = not fake and client is None and bool(seeds)
    if owned:
        client = client_factory()
    queries: dict[str, tuple[str, int]] = {}
    failed = 0
    try:
        for index, seed in enumerate(seeds):
            if not fake and index:
                sleep(1)
            try:
                received = _parse(_load(seed, client, fake))
            except (httpx.HTTPError, ValueError, OSError):
                failed += 1
            else:
                for query, rank in received:
                    key = norm_key(query)
                    if key not in queries or rank < queries[key][1]:
                        queries[key] = (query, rank)
            if on_progress is not None:
                on_progress()
    finally:
        if owned:
            client.close()
    if not queries:
        raise AutocompleteUnavailable('No autocomplete results received')
    return AutocompleteResult(list(queries.values()), failed, len(seeds))
