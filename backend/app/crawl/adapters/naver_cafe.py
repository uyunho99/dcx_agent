"""Public cafe JSON and restricted snippets, without authentication."""
from app.crawl.adapters.base import FetchedDoc
from app.crawl.adapters.community import html_text
from app.crawl.adapters.naver_common import NaverAdapter


class NaverCafeAdapter(NaverAdapter):
    source = 'naver_cafe'

    def headers(self):
        return {**super().headers(), 'Referer': 'https://m.cafe.naver.com/'}

    def fetch(self, item, *, max_comments=None):
        owner, article_id = self.article_parts(item.url)
        response = self.request(
            f'https://article.cafe.naver.com/gw/v4/cafes/{owner}/articles/{article_id}?useCafeId=false',
            restricted=True)
        payload = response.json()
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError('Naver cafe result missing')
        code = result.get('errorCode')
        reason = str(result.get('reason', '')) + str(result.get('message', ''))
        restricted = response.status_code == 401 or str(code) == '0004' or any(
            word in reason for word in ('로그인', '등급', '권한', '비공개', '회원 전용'))
        if code and restricted:
            return [FetchedDoc(item.title, item.snippet, [], item.date,
                               {**item.src_meta, 'restriction_code': str(code)}, 'restricted', None)]
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
