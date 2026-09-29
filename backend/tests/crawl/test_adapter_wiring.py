import pytest

from app.crawl.adapters import REGISTRY, available_sources
from app.crawl import healthcheck
from app.crawl.adapters.base import ListItem, ListPage


@pytest.mark.parametrize('failure', [None, 'availability', 'list', 'fetch'])
def test_probe_closes_adapters(monkeypatch, failure):
    closed = []
    class Adapter:
        def is_available(self):
            if failure == 'availability':
                raise ValueError('probe')
            return True
        def list_page(self, *args):
            if failure == 'list':
                raise ValueError('list')
            return ListPage([ListItem('fixture://a', '', '', None, {})], None, 1)
        def fetch(self, item):
            if failure == 'fetch':
                raise ValueError('fetch')
            return []
        def close(self):
            closed.append(self)
    monkeypatch.setattr('app.crawl.adapters.REGISTRY', {'fixture': Adapter})
    monkeypatch.setattr(healthcheck, 'REGISTRY', {'fixture': Adapter})
    if failure == 'availability':
        with pytest.raises(ValueError):
            available_sources()
    else:
        assert available_sources() == ['fixture']
        assert healthcheck.main(['--source', 'fixture']) == int(failure is not None)
    assert len(closed) == (1 if failure == 'availability' else 2)


def test_real_registry_availability_is_offline(monkeypatch):
    from app.config import settings
    from app.crawl.adapters.youtube import YoutubeAdapter
    from app.crawl.adapters.clien import ClienAdapter
    from app.crawl.adapters.ppomppu import PpomppuAdapter
    from app.crawl.adapters.naver_blog import NaverBlogAdapter
    from app.crawl.adapters.naver_cafe import NaverCafeAdapter
    import httpx
    import yt_dlp
    def forbidden(*args, **kwargs):
        pytest.fail('availability must not make requests')
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', forbidden)
    monkeypatch.setattr(settings, 'enable_fixture_channel', False)
    assert set(available_sources()) == {'youtube', 'clien', 'ppomppu', 'naver_blog', 'naver_cafe'}
    for source, cls in [('youtube', YoutubeAdapter), ('clien', ClienAdapter),
                        ('ppomppu', PpomppuAdapter), ('naver_blog', NaverBlogAdapter),
                        ('naver_cafe', NaverCafeAdapter)]:
        adapter = REGISTRY[source]()
        try:
            assert isinstance(adapter, cls)
        finally:
            if hasattr(adapter, 'close'):
                adapter.close()
