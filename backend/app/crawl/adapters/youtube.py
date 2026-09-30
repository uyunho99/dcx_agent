"""Bounded yt-dlp search and comment threads, without downloading media.

A nonempty description becomes a document with thread_key="". Each top-level
comment becomes a document whose body is that comment and whose comments are
its replies (depth 1). max_comments counts roots and replies, not descriptions.
Search is one bounded batch; there is no continuation cursor.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from app.config import settings
import importlib

from app.crawl.adapters.base import AdapterBlocked, FetchedDoc, ListItem, ListPage
from app.crawl.hashing import author_hash
from app.crawl.schema import Comment


def _date(info: dict) -> str | None:
    if info.get('timestamp') is not None:
        return datetime.fromtimestamp(info['timestamp'], ZoneInfo('Asia/Seoul')).date().isoformat()
    if info.get('upload_date'):
        return datetime.strptime(info['upload_date'], '%Y%m%d').date().isoformat()
    return None


def _metadata(info: dict) -> dict:
    return dict(video_title=info.get('title') or '', video_id=info['id'],
                channel=info.get('channel') or '', duration=info.get('duration'),
                view_count=info.get('view_count'))


def _author(info: dict) -> str | None:
    return info.get('author_id') or info.get('author')


def _blocked(error: BaseException) -> bool:
    """Recognize bot confirmation and HTTP blocks through yt-dlp exception chains."""
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        message = str(current).casefold().replace("’", "'")
        if "confirm you're not a bot" in message:
            return True
        if getattr(current, 'status', None) in (403, 429) or getattr(current, 'code', None) in (403, 429):
            return True
        pending.extend([current.__cause__, current.__context__, getattr(current, 'cause', None)])
        exc_info = getattr(current, 'exc_info', None)
        if exc_info:
            pending.append(exc_info[1])
    return False


class YoutubeAdapter:
    source = 'youtube'

    def __init__(self, videos_per_keyword: int = 10, max_comments: int = 30):
        if videos_per_keyword <= 0:
            raise ValueError('videos_per_keyword must be positive')
        if max_comments < 0:
            raise ValueError('max_comments must be nonnegative')
        self.videos_per_keyword = videos_per_keyword
        self.max_comments = max_comments

    @classmethod
    def is_available(cls) -> bool:
        if not settings.real_channels_enabled:
            return False
        try:
            importlib.import_module('yt_dlp')
        except ImportError:
            return False
        return True

    def _extract(self, url: str, **options) -> dict:
        yt_dlp = importlib.import_module('yt_dlp')
        try:
            # Each lease owns its extractor; adapters can be called concurrently.
            with yt_dlp.YoutubeDL(dict(quiet=True, no_warnings=True, skip_download=True,
                                      **options)) as extractor:
                result = extractor.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            if _blocked(exc):
                raise AdapterBlocked('YouTube blocked the request') from exc
            raise
        if not isinstance(result, dict):
            raise ValueError('Expected a yt-dlp information dictionary')
        return result

    def list_page(self, kw: str, cursor: str | None, *, videos_per_keyword: int | None = None) -> ListPage:
        if cursor is not None:
            raise ValueError('YouTube search has no continuation cursor')
        limit = self.videos_per_keyword if videos_per_keyword is None else videos_per_keyword
        if limit <= 0:
            raise ValueError('videos_per_keyword must be positive')
        info = self._extract(f'ytsearch{limit}:{kw}', extract_flat=True)
        items = []
        for entry in (info.get('entries') or [])[:limit]:
            if entry is None:
                continue
            items.append(ListItem(
                url=f"https://www.youtube.com/watch?v={entry['id']}", title='',
                snippet=entry.get('description') or '', date=_date(entry),
                src_meta=_metadata(entry)))
        return ListPage(items, None, len(items))

    def fetch(self, item: ListItem, *, max_comments: int | None = None) -> list[FetchedDoc]:
        limit = self.max_comments if max_comments is None else max_comments
        if limit < 0:
            raise ValueError('max_comments must be nonnegative')
        info = self._extract(item.url, getcomments=limit > 0,
                             extractor_args={'youtube': {'max_comments': [str(limit), 'all', '10', '5']}})
        meta = _metadata(info)
        video_date = _date(info)
        restricted = info.get('availability') in (
            'private', 'premium_only', 'subscriber_only', 'needs_auth')
        access = 'restricted' if restricted else 'public'
        docs = []
        if info.get('description'):
            docs.append(FetchedDoc('', info['description'], [], video_date, meta, access,
                                   info.get('channel_id') or info.get('uploader_id')))
        comments = (info.get('comments') or [])[:limit]
        # Index roots first so reply order does not matter. Orphans are omitted;
        # inventing a root would give the worker an incorrect document identity.
        roots = {c['id']: c for c in comments if c.get('parent') in (None, '', 'root')}
        replies = {key: [] for key in roots}
        for comment in comments:
            parent = comment.get('parent')
            if parent in replies:
                raw = _author(comment)
                replies[parent].append(Comment(
                    text=comment.get('text') or '', depth=1, date=_date(comment) or '',
                    author_hash=author_hash(self.source, raw) if raw else ''))
        for key, root in roots.items():
            docs.append(FetchedDoc('', root.get('text') or '', replies[key], _date(root),
                                   meta, access, _author(root), key))
        return docs
