"""Public cafe JSON and restricted snippets, without authentication."""
from urllib.parse import urlsplit
from dataclasses import replace

from app.crawl.adapters.base import AdapterBlocked, FetchedDoc
from app.crawl.adapters.community import html_text
from app.crawl.adapters.naver_common import NaverAdapter

# Login-required code recorded in detail-1.json and T15-naver-probe.md.
RESTRICTION_CODES = frozenset({'0004'})


class NaverCafeAdapter(NaverAdapter):
    source = 'naver_cafe'

    def headers(self):
        return {**super().headers(), 'Referer': 'https://m.cafe.naver.com/'}

    def fetch(self, item, *, max_comments=None):
        owner, article_id = self.article_parts(item.url)
        use_cafe_id = 'true' if urlsplit(item.url).path.startswith('/ca-fe/cafes/') else 'false'
        response = self.request(
            f'https://article.cafe.naver.com/gw/v4/cafes/{owner}/articles/{article_id}?useCafeId={use_cafe_id}',
            restricted=True)
        try:
            payload = response.json()
        except ValueError:
            if response.status_code == 401:
                return self.restricted_doc(item)
            if response.status_code == 403:
                raise AdapterBlocked(f'{self.source}: HTTP 403') from None
            raise
        result = payload.get('result') if isinstance(payload, dict) else None
        if isinstance(result, dict):
            cafe = result.get('cafe') or {}
            more = result.get('more') or {}
            name = cafe.get('name') or cafe.get('cafeName') or more.get('cafeName')
            if name:
                item = replace(item, src_meta={**item.src_meta, 'cafe': name})
        if response.status_code == 401:
            return self.restricted_doc(item, result.get('errorCode') if isinstance(result, dict) else None)
        if response.status_code == 403:
            if isinstance(result, dict) and (
                    str(result.get('errorCode')) in RESTRICTION_CODES or self.restriction_reason(result)):
                return self.restricted_doc(item, result.get('errorCode'))
            raise AdapterBlocked(f'{self.source}: HTTP 403')
        if not isinstance(result, dict):
            raise ValueError('Naver cafe result missing')
        code = result.get('errorCode')
        if str(code) in RESTRICTION_CODES or self.restriction_reason(result):
            return self.restricted_doc(item, code)
        article = result.get('article')
        if not isinstance(article, dict) or not isinstance(article.get('contentHtml'), str):
            raise ValueError('Naver cafe article body missing')
        comments = []
        threads = []
        # Recorded JSON has no comment continuation URL/cursor. Only its first
        # comments.items batch is supported; article.commentCount retains total.
        batch = result.get('comments', {}).get('items', [])
        if not isinstance(batch, list):
            raise ValueError('Naver cafe comments malformed')
        for row in batch:
            if row.get('isDeleted'):
                continue
            if max_comments is not None and max_comments > 0 and len(comments) >= max_comments:
                break
            depth = int(bool(row.get('isRef')) or row.get('refId', row.get('id')) != row.get('id'))
            writer = row.get('writer') or {}
            comments.append(self.comment(
                html_text(row.get('content', '')), depth,
                self.normalize_date(row.get('updateDate')) or '',
                writer.get('memberKey') or writer.get('nick', '')))
            threads.append({'id': row.get('id'), 'parent': row.get('refId') if depth else None})
        writer = article.get('writer') or {}
        return [FetchedDoc(
            article.get('subject') or item.title, html_text(article['contentHtml']), comments,
            self.normalize_date(article.get('writeDate')) or item.date,
            {**item.src_meta, 'comment_count': article.get('commentCount'), 'comment_threads': threads},
            'public', writer.get('memberKey') or writer.get('nick'),
        )]

    @staticmethod
    def restriction_reason(result):
        reason = str(result.get('reason', '')) + str(result.get('message', ''))
        return any(word in reason for word in ('로그인', '등급', '권한', '비공개', '회원 전용'))

    @staticmethod
    def restricted_doc(item, code=None):
        meta = dict(item.src_meta)
        if code is not None:
            meta['restriction_code'] = str(code)
        return [FetchedDoc(item.title, item.snippet, [], item.date, meta, 'restricted', None)]
