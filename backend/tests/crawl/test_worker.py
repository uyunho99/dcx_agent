import csv
import json
from dataclasses import replace

import pytest

from app.config import settings
from app.crawl import worker
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import AdapterBlocked
from app.crawl.adapters.fixture import FixtureAdapter
from app.crawl.filters import FilterConfig
from app.crawl.queue import CrawlQueue
from app.crawl.schema import Doc
from app.crawl.writer import read_docs


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    path = tmp_path / 'corpus.csv'
    with path.open('w') as f:
        w = csv.writer(f)
        w.writerow(['review'])
        w.writerows([[f'에어컨 소음 {i}'] for i in range(80)])
    monkeypatch.setattr(settings, 'fixture_corpus_path', str(path))
    monkeypatch.setattr(settings, 'enable_fixture_channel', True)
    monkeypatch.setattr(settings, 'author_salt_path', str(tmp_path / '.salt'))
    return path


def setup_list(tmp_path, **kwargs):
    return worker.run_list('S', collection=tmp_path, keywords=['에어컨'],
                           sources=['fixture'], filters=FilterConfig(date_from=None, date_to=None), **kwargs)


def detail(tmp_path, snapshot, **kwargs):
    return worker.run_detail('S', snapshot, collection=tmp_path,
                            filters=FilterConfig(date_from=None, date_to=None), backoff_s=0.001, **kwargs)


def state(path):
    return json.loads((path / 'worker_state.json').read_text())['channels']


def test_list_then_detail_writes_docs(tmp_path, corpus):
    snapshot = setup_list(tmp_path)
    detail(tmp_path, snapshot)
    docs = list(read_docs(tmp_path / 'docs'))
    assert len(docs) == 80
    assert all(set(d) == set(Doc.model_fields) for d in docs)
    assert all(d['kw_hits'] == ['에어컨'] and d['kw'] == '에어컨' for d in docs)
    assert all(Doc.model_validate(d) for d in docs)


def test_fetch_failure_falls_back_to_snippet(tmp_path, corpus, monkeypatch):
    snapshot = setup_list(tmp_path)
    calls = []
    class Broken(FixtureAdapter):
        def fetch(self, item):
            calls.append(item.url)
            raise OSError('offline')
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Broken(corpus))
    detail(tmp_path, snapshot)
    docs = list(read_docs(tmp_path / 'docs'))
    assert len(calls) == 240 and len(docs) == 80
    assert all(d['fetch_level'] == 'snippet' for d in docs)
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    assert q.counts()['done'] == 80
    assert all(r[0] == 'OSError: offline' for r in q.connection.execute('SELECT last_error FROM urls'))
    q.close()


def test_blocked_channel_pauses_only_that_channel(tmp_path, corpus, monkeypatch):
    class Blocked(FixtureAdapter):
        def fetch(self, item):
            raise AdapterBlocked('403')
    monkeypatch.setitem(REGISTRY, 'naver_blog', lambda: Blocked(corpus))
    snap = worker.run_list('S', collection=tmp_path, keywords=['에어컨'],
                           sources=['fixture', 'naver_blog'], filters=FilterConfig(date_from=None, date_to=None))
    detail(tmp_path, snap)
    assert state(tmp_path)['naver_blog']['status'] == 'paused_blocked'
    assert state(tmp_path)['naver_blog']['blocked'] >= 20
    assert len([d for d in read_docs(tmp_path / 'docs') if d['source'] == 'fixture']) == 80


def test_restricted_recorded(tmp_path, corpus, monkeypatch):
    snapshot = setup_list(tmp_path)
    class Restricted(FixtureAdapter):
        def fetch(self, item):
            return [replace(super().fetch(item)[0], access='restricted', author_raw='private-id')]
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Restricted(corpus))
    detail(tmp_path, snapshot)
    docs = list(read_docs(tmp_path / 'docs'))
    assert all(d['access'] == 'restricted' and len(d['author_hash']) == 16 for d in docs)
    assert 'private-id' not in ''.join(p.read_text() for p in (tmp_path / 'docs').glob('*'))
