"""Clien search and article HTML parsing; search uses the keyword unchanged."""
import re
from urllib.parse import urlencode, urlsplit

from app.crawl.adapters.base import FetchedDoc, ListItem, ListPage
from app.crawl.adapters.community import CommunityAdapter, date_text, html_text, selected


class ClienAdapter(CommunityAdapter):
    source = "clien"
    origin = "https://www.clien.net"
    list_url_template = origin + "/service/search?{query}"

    def list_url(self, kw, cursor):
        params = {"q": kw, "sort": "recency", "boardCd": "", "isBoard": "false"}
        if cursor is not None:
            if int(cursor) < 0:
                raise ValueError("Clien page must be nonnegative")
            params["p"] = str(int(cursor))
        return self.list_url_template.format(query=urlencode(params))

    def parse_list(self, tree, cursor):
        items = []
        seen = set()
        for row in tree.css(".list_item"):
            link = row.css_first("a.subject_fixed")
            if link is None:
                continue
            url = self.absolute_url(link.attributes["href"])
            if url in seen:
                continue
            seen.add(url)
            parts = urlsplit(url).path.split("/")
            items.append(ListItem(
                url, selected(row, "a.subject_fixed"), selected(row, ".preview"),
                date_text(selected(row, ".timestamp")),
                {"board": parts[-2], "article_id": parts[-1]},
            ))
        # Recorded navigation uses app.searchDetails("", zero_based_p).
        # Follow only a later advertised page; never invent a terminal page.
        current = int(cursor or 0)
        pages = []
        for link in tree.css(".board-pagination [onclick]"):
            match = re.search(r'searchDetails\(\s*["\'][^"\']*["\']\s*,\s*["\'](\d+)["\']',
                              link.attributes["onclick"])
            if match and int(match[1]) > current:
                pages.append(int(match[1]))
        return ListPage(items, str(min(pages)) if pages else None, None)

    def parse_detail(self, tree, item):
        article = tree.css_first(".post_article")
        if article is None:
            raise ValueError("Clien article body missing")
        title = selected(tree, ".post_subject > span:not(.post_category)") or item.title
        comments, threads = [], []
        root_id = None
        # Clien renders roots followed by flat .re replies. The capture exposes
        # no explicit parent ID; replies are attached to the preceding root.
        for row in tree.css(".comment_row"):
            content = row.css_first(".comment_content")
            if content is None:
                continue
            comment_id = row.attributes.get("data-comment-sn")
            depth = int("re" in row.attributes.get("class", "").split())
            parent = root_id if depth else None
            if not depth:
                root_id = comment_id
            comments.append(self.comment(
                html_text(content.html), depth,
                date_text(selected(row, ".comment_time .timestamp")) or "",
                selected(row, ".nickname") or row.attributes.get("data-author-id", ""),
            ))
            threads.append({"id": comment_id, "parent": parent})
        return FetchedDoc(
            title, html_text(article.html), comments,
            date_text(selected(tree, ".post_author .date")) or item.date,
            {**item.src_meta, "comment_threads": threads}, "public",
            selected(tree, ".post_info .nickname") or None,
        )
