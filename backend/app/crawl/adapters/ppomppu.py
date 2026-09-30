"""Ppomppu EUC-KR search, article bodies, and inline/HTML comments."""
import json
import re
from urllib.parse import parse_qs, quote, urlsplit

from app.crawl.adapters.base import FetchedDoc, ListItem, ListPage
from app.crawl.adapters.community import CommunityAdapter, date_text, html_text, selected, text


class PpomppuAdapter(CommunityAdapter):
    source = "ppomppu"
    origin = "https://www.ppomppu.co.kr"
    encoding = "euc-kr"
    list_url_template = origin + "/search_bbs.php?keyword={keyword}"

    def headers(self):
        return {**super().headers(), "Referer": self.origin + "/"}

    def list_url(self, kw, cursor):
        url = self.list_url_template.format(keyword=quote(kw, safe="", encoding=self.encoding))
        if cursor is not None:
            if int(cursor) < 1:
                raise ValueError("Ppomppu page must be positive")
            url += f"&page={int(cursor)}"
        return url

    def parse_list(self, tree, cursor):
        items, seen = [], set()
        for row in tree.css(".content"):
            link = row.css_first(".title a")
            if link is None:
                continue
            url = self.absolute_url(link.attributes["href"])
            parts = urlsplit(url)
            params = parse_qs(parts.query)
            if parts.path != "/zboard/view.php" or not params.get("no") or url in seen:
                continue
            seen.add(url)
            # Comment counts are nested inside the title anchor.
            for count in link.css(".comment-cnt"):
                count.decompose()
            items.append(ListItem(
                url, text(link), selected(row, "p:not(.desc)"),
                date_text(selected(row, ".desc")),
                {"board": params.get("id", [""])[0], "article_id": params["no"][0]},
            ))
        # The recorded aggregate search has only category "more" links, no
        # page links: it is terminal. On paginated search HTML use advertised
        # one-based page= values; category traversal is deliberately separate.
        current, pages = int(cursor or 1), []
        for link in tree.css("a[href]"):
            target = urlsplit(link.attributes["href"])
            if target.path.split("/")[-1] != "search_bbs.php":
                continue
            page = parse_qs(target.query).get("page", [""])[0]
            if page.isdigit() and int(page) > current:
                pages.append(int(page))
        return ListPage(items, str(min(pages)) if pages else None, None)

    def parse_detail(self, tree, item):
        article = tree.css_first(".board-contents")
        if article is None:
            raise ValueError("Ppomppu article body missing")
        heading = tree.css_first("#topTitle h1")
        if heading:
            for count in heading.css("#comment"):
                count.decompose()
        comments, threads, seen = [], [], set()

        def add(comment_id, parent, depth, content, date, author):
            comment_id = str(comment_id)
            if comment_id in seen:
                return
            seen.add(comment_id)
            comments.append(self.comment(content, int(depth), date, author))
            threads.append({"id": comment_id, "parent": str(parent) if parent else None})

        for script in tree.css("script"):
            match = re.search(r"\bvar\s+initialCommentData\s*=\s*", script.text())
            if not match:
                continue
            # raw_decode handles nested objects and braces in comment text;
            # never execute JavaScript or truncate JSON with a brace regex.
            data, _ = json.JSONDecoder().raw_decode(script.text()[match.end():])
            for row in data.get("comments", []):
                meta = row.get("meta", {})
                add(row["no"], row.get("parent"), row.get("depth", 0),
                    html_text(row.get("memo", "")),
                    meta.get("time_detail") or meta.get("time_display", ""),
                    html_text(row.get("name", "")))

        # Older/server-rendered skins: content IDs or explicit comment rows.
        # Ignore hidden ori_comment edit forms; deduplicate IDs against JSON.
        for content in tree.css('.comment-content, .comment_content, [id^="commentContent_"]'):
            row = content
            while row.parent and not (
                row.attributes.get("id", "").startswith("comment_")
                or "data-comment-no" in row.attributes
            ):
                row = row.parent
            comment_id = row.attributes.get("data-comment-no") or row.attributes.get("id", "").removeprefix("comment_")
            if not comment_id or not comment_id.isdigit():
                comment_id = content.attributes.get("id", "").removeprefix("commentContent_")
            if not comment_id.isdigit():
                continue
            add(comment_id, row.attributes.get("data-parent"),
                row.attributes.get("data-depth", 0), html_text(content.html),
                date_text(selected(row, ".comment-date, .comment_date")) or "",
                selected(row, ".comment-name, .comment_name, .baseList-name"))
        return FetchedDoc(
            text(heading) or item.title, html_text(article.html), comments,
            date_text(selected(tree, ".topTitle-mainbox")) or item.date,
            {**item.src_meta, "comment_threads": threads}, "public",
            selected(tree, ".topTitle-name") or None,
        )
