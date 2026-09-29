"""Shared keyless search parsing and CommunityAdapter HTTP lifecycle."""
import re
from collections import OrderedDict
from threading import Lock
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser

from app.crawl.adapters.base import AdapterBlocked, ListItem, ListPage
from app.crawl.adapters.community import CommunityAdapter, selected, text

KST = ZoneInfo('Asia/Seoul')


class NaverAdapter(CommunityAdapter):
    def __init__(self, client=None, *, now=None, **kwargs):
        super().__init__(client, **kwargs)
        self._pages = OrderedDict()
        self._pages_lock = Lock()
        self.now = now or (lambda: datetime.now(KST))

    @property
    def kind(self):
        return self.source.removeprefix('naver_')

    def normalize_date(self, value):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, KST).date().isoformat()
        value = str(value or '')
        match = re.search(r'(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})', value)
        if match:
            return datetime(*map(int, match.groups())).date().isoformat()
        match = re.fullmatch(r'\s*(\d+)\s*(초|분|시간|일|주)\s*전\s*', value)
        if match:
            amount, unit = match.groups()
            seconds = int(amount) * {'초': 1, '분': 60, '시간': 3600, '일': 86400, '주': 604800}[unit]
            return (self.now() - timedelta(seconds=seconds)).date().isoformat()
        if value.strip() in ('방금 전', '오늘', '어제'):
            return (self.now() - timedelta(days=value.strip() == '어제')).date().isoformat()
        return None

    def article_parts(self, url):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.netloc not in (
                f'{self.kind}.naver.com', f'm.{self.kind}.naver.com'):
            raise ValueError('Unexpected Naver article URL')
        match = re.fullmatch(r'/([A-Za-z0-9_-]+)/(\d+)/?', parsed.path)
        if match:
            return match.groups()
        if self.kind == 'cafe':
            match = re.fullmatch(r'/ca-fe/cafes/(\d+)/articles/(\d+)/?', parsed.path)
            if match:
                return match.groups()
        if self.kind == 'blog' and parsed.path == '/PostView.naver':
            query = parse_qs(parsed.query)
            owner, article_id = query.get('blogId', []), query.get('logNo', [])
            if (len(owner) == len(article_id) == 1
                    and re.fullmatch(r'[A-Za-z0-9_-]+', owner[0])
                    and re.fullmatch(r'\d+', article_id[0])):
                return owner[0], article_id[0]
        raise ValueError('Unexpected Naver article URL')

    def article_url(self, url):
        owner, article_id = self.article_parts(url)
        if self.kind == 'cafe' and urlsplit(url).path.startswith('/ca-fe/cafes/'):
            # Preserve numeric cafe IDs rather than pretending they are cafe names.
            return f'https://cafe.naver.com/ca-fe/cafes/{owner}/articles/{article_id}'
        return f'https://{self.kind}.naver.com/{owner}/{article_id}'

    def request(self, url, *, restricted=False):
        with self._limiter:
            response = self.client.get(url, headers=self.headers(), follow_redirects=False)
        if response.status_code == 429 or (response.status_code == 403 and not restricted):
            raise AdapterBlocked(f'{self.source}: HTTP {response.status_code}')
        # Cafe detail classifies 403 JSON restrictions versus channel blocking.
        if not (restricted and response.status_code in (401, 403)):
            response.raise_for_status()
        return response

    def list_page(self, kw, cursor=None):
        start = int(cursor or 1)
        if start < 1 or (start - 1) % 30:
            raise ValueError('Naver cursor must be 1 + 30*n')
        url = 'https://search.naver.com/search.naver?' + urlencode(
            {'ssc': f'tab.{self.kind}.all', 'query': kw, 'start': start})
        tree = HTMLParser(self.request(url).content.decode('utf-8', errors='replace'))
        items, seen = [], set()
        rows = tree.css('[data-template-id="ugcItem"], .lst_view > li')
        for row in rows:
            headline = row.css_first('.sds-comps-text-type-headline1')
            link = headline.parent if headline is not None else row.css_first('a.title_link')
            if link is None or link.tag != 'a' or not link.attributes.get('href'):
                raise ValueError('Naver search result title missing')
            title = text(headline if headline is not None else link)
            if not title:
                raise ValueError('Naver search result title empty')
            try:
                url = self.article_url(link.attributes['href'])
            except ValueError:
                # Valid titled links may be advertisements, profiles or more links.
                continue
            owner, article_id = self.article_parts(url)
            if url in seen:
                continue
            seen.add(url)
            snippet = selected(row, '.sds-comps-text-type-body1, .dsc_link')
            date = None
            for node in row.css('.sds-comps-profile-info-subtext, .user_info .sub, .date'):
                date = self.normalize_date(text(node)) or date
            meta = {'article_id': article_id, f'{self.kind}_id': owner}
            if self.kind == 'cafe':
                name = selected(row, '.user_info .name, .sds-comps-profile-info-title-text')
                if name:
                    meta['cafe'] = name
            items.append(ListItem(url, title, snippet, date, meta))
        if not items:
            notice = selected(tree, '.not_found, .api_noresult_wrap, .no_result')
            if rows or not re.search(r'검색\s*결과가?\s*없|검색된.*없', notice):
                raise ValueError('Naver search results could not be parsed')
        # Captures have no next-page link. A short page is terminal; an explicit
        # disabled next control also terminates a full page. No internal retries.
        terminal = tree.css_first('.sc_page .btn_next[aria-disabled="true"], .sc_page .btn_next.disabled')
        signature = frozenset(i.url for i in items)
        with self._pages_lock:
            previous = self._pages.get(kw)
            repeated = previous is not None and previous[0] == signature and previous[1] < start
            # Preserve the first start of consecutive identical pages so retrying
            # a terminal cursor cannot accidentally reopen pagination.
            self._pages[kw] = (signature, previous[1] if repeated else start)
            self._pages.move_to_end(kw)
            if len(self._pages) > 256:
                self._pages.popitem(last=False)
        more = len(items) == 30 and terminal is None and not repeated
        return ListPage(items, str(start + 30) if more else None, None)
