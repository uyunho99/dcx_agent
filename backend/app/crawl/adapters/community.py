"""Shared synchronous community HTTP adapter and selectolax text helpers."""
import re
import time
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.parser import HTMLParser

from app.crawl.adapters.base import AdapterBlocked, ListItem, ListPage, FetchedDoc
from app.crawl.hashing import author_hash
from app.crawl.ratelimit import ChannelLimiter
from app.crawl.schema import Comment


def text(node) -> str:
    if node is None:
        return ""
    return " ".join(node.text(separator=" ", strip=True).split())


def html_text(markup: str) -> str:
    tree = HTMLParser(markup)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return text(tree.body or tree.root)


def selected(tree, selector: str) -> str:
    return text(tree.css_first(selector))


def date_text(value: str) -> str | None:
    match = re.search(r"\d{4}[-.]\d{2}[-.]\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?", value)
    return match.group().replace(".", "-") if match else None


class CommunityAdapter:
    """Subclasses supply list URL templates and list/detail parser hooks.

    One limiter per instance spaces request starts, including list-to-detail
    transitions. Injected clients remain caller-owned; close() releases only
    clients created here. Site encodings override unreliable response headers.
    """
    source: str
    origin: str
    encoding = "utf-8"
    list_url_template: str

    def __init__(self, client: httpx.Client | None = None, *,
                 clock=time.monotonic, sleep=time.sleep):
        self._owns_client = client is None
        self.client = client if client is not None else httpx.Client(timeout=30)
        self._limiter = ChannelLimiter(1, 1.0, clock=clock, sleep=sleep)

    def close(self):
        if self._owns_client:
            self.client.close()

    def is_available(self) -> bool:
        return True

    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        }

    def absolute_url(self, href: str) -> str:
        url = urljoin(self.origin, href)
        if urlsplit(url).netloc != urlsplit(self.origin).netloc or urlsplit(url).scheme != "https":
            raise ValueError("Unexpected community URL")
        return url

    def _get(self, url: str) -> HTMLParser:
        with self._limiter:
            response = self.client.get(self.absolute_url(url), headers=self.headers(),
                                       follow_redirects=False)
        if response.status_code in (403, 429):
            raise AdapterBlocked(f"{self.source}: HTTP {response.status_code}")
        response.raise_for_status()
        # Some captures contain invalid bytes in third-party scripts; replacement
        # is confined to those bytes rather than guessing the article encoding.
        return HTMLParser(response.content.decode(self.encoding, errors="replace"))

    def list_url(self, kw: str, cursor: str | None) -> str:
        raise NotImplementedError

    def list_page(self, kw: str, cursor: str | None = None) -> ListPage:
        return self.parse_list(self._get(self.list_url(kw, cursor)), cursor)

    def fetch(self, item: ListItem) -> list[FetchedDoc]:
        return [self.parse_detail(self._get(item.url), item)]

    def parse_list(self, tree: HTMLParser, cursor: str | None) -> ListPage:
        raise NotImplementedError

    def parse_detail(self, tree: HTMLParser, item: ListItem) -> FetchedDoc:
        raise NotImplementedError

    def comment(self, content: str, depth: int, date: str, author: str) -> Comment:
        return Comment(text=content, depth=depth, date=date,
                       author_hash=author_hash(self.source, author) if author else "")
