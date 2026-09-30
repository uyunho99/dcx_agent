"""Mobile blog HTML; missing editor markup is a worker-visible parse failure."""
import re

from selectolax.parser import HTMLParser

from app.crawl.adapters.base import FetchedDoc
from app.crawl.adapters.community import html_text, selected
from app.crawl.adapters.naver_common import NaverAdapter


class NaverBlogAdapter(NaverAdapter):
    source = 'naver_blog'

    def fetch(self, item):
        owner, article_id = self.article_parts(item.url)
        response = self.request(f'https://m.blog.naver.com/{owner}/{article_id}')
        markup = response.content.decode('utf-8', errors='replace')
        tree = HTMLParser(markup)
        body = tree.css_first('.se-main-container, #postViewArea')
        components = [body] if body is not None else tree.css('.se_component')
        content = ' '.join(html_text(node.html) for node in components).strip()
        if not content:
            raise ValueError('Naver blog article body missing')
        meta = dict(item.src_meta)
        count = re.search(r'commentCount\s*[=:]\s*["\']?(\d+)', markup)
        if count:
            meta['comment_count'] = int(count[1])
        return [FetchedDoc(
            selected(tree, '.se-title-text, .tit_h3') or item.title,
            content, [], self.normalize_date(selected(tree, '.blog_date, .se_publishDate, .post_date')) or item.date,
            meta, 'public', owner,
        )]
