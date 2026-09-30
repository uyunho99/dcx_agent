#!/usr/bin/env python3
"""Host-only, one-shot real HTTP fixture recorder. Importing never makes requests."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

SOURCES = ('naver_blog', 'naver_cafe', 'youtube', 'clien', 'ppomppu')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.7',
}
TRIM_KEYS = {'formats', 'thumbnails', 'automatic_captions', 'requested_formats', 'http_headers'}
NAME_KEYS = {'author', 'authorname', 'nickname', 'nick', 'membernickname', 'writer',
             'writername', 'bloggername', 'uploader', 'channel', 'displayname'}
ID_KEYS = {'authorid', 'memberid', 'memberkey', 'userid', 'blogid', 'writerid', 'uploaderid', 'channelid', 'naverid', 'nickid'}
PROFILE_KEYS = {'author_thumbnail', 'profileimage', 'profileimageurl', 'profileurl', 'avatar', 'avatarurl',
                'authorurl', 'uploaderurl', 'channelurl'}
SELECTORS = {
    'naver_blog': ('.nick, .nickname, .blog_author, .blogger, .writer, .user_name, '
                   '.user_info .name, .sds-comps-profile-info-name-text, '
                   '.sds-comps-profile-info-title-text'),
    'naver_cafe': '.nick, .nickname, .nick_name, .comment_nickname, .ArticleWriter .nickname',
    'clien': '.nickname, .nick, .member, .comment_view .nickname',
    'ppomppu': '.list_name, .list_name2, .view_name, .comment_name, .nickname, .topTitle-name .baseList-name, .baseList-name, .content .desc > span:nth-child(2)',
    'youtube': '[itemprop="author"]',
}
# Search profile titles identify bloggers only on blog pages; on cafe pages
# they identify public communities. .user_info .sub and SDS profile subtext
# contain dates/metadata, not people. Audit shares these discovery selectors.
NAVER_NAMES = ('.sub_name, .blog-nick, .nick_name, '
               '.mention, .se-mention, .tag_nickname')
EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
URL = re.compile(r'(?:https?:)?//[^\s<>"\'\\]+')
SECRET_KEY = re.compile(r'(?:^key$|api.?key|secret|token|authorization|credential|signature|password|client.?id)', re.I)


def normalized(key):
    return re.sub(r'[^a-z]', '', key.lower())


def letters(number):
    result = ''
    while number >= 0:
        result = chr(97 + number % 26) + result
        number = number // 26 - 1
    return result


def strip_query_secrets(url):
    """Keep useful article/search parameters; remove credentials and fragments."""
    try:
        parts = urlsplit(html.unescape(url))
    except ValueError:
        # Regex matches in page scripts are not necessarily valid URLs. Still
        # remove query credentials without requiring a valid authority.
        base, separator, query = html.unescape(url).split('#', 1)[0].partition('?')
        query = '&'.join(pair for pair in query.split('&')
                         if not SECRET_KEY.search(unquote(pair.split('=', 1)[0])))
        result = base + ('?' + query if separator and query else '')
        return result.replace('&', '&amp;') if '&amp;' in url else result
    host = parts.netloc.rsplit('@', 1)[-1]
    query = '&'.join(pair for pair in parts.query.split('&')
                     if not SECRET_KEY.search(unquote(pair.split('=', 1)[0])))
    result = urlunsplit((parts.scheme, host, parts.path, query, ''))
    return result.replace('&', '&amp;') if '&amp;' in url else result


def identity_text_parts(node):
    """Yield text tokens inside this identity element, never its siblings."""
    child = node.child
    while child is not None:
        if child.tag == '-text':
            yield child.text(strip=True)
        else:
            yield from identity_text_parts(child)
        child = child.next


class Masker:
    """One in-memory mapping shared by every response and manifest in a capture."""
    def __init__(self, secrets=()):
        self.mapping = {}
        self.counts = Counter()
        self.secrets = tuple(s for s in secrets if s)

    def remember(self, value, kind):
        if not isinstance(value, str) or not value.strip():
            return
        value = html.unescape(value.strip())
        if value in self.mapping:
            return
        label = letters(self.counts[kind])
        self.counts[kind] += 1
        self.mapping[value] = {
            'name': '사용자' + label.upper(), 'id': 'user_' + label,
            'email': 'user_' + label + '@example.invalid',
            'profile': 'https://example.invalid/profile_' + label + '.png',
            'ip': 'user_' + label,
        }[kind]

    def discover_url(self, value):
        value = html.unescape(value)
        # Discover query identities even when a malformed authority cannot be
        # parsed. Returning below must not interrupt the rest of discover_text.
        for key, val in parse_qsl(value.partition('?')[2].split('#', 1)[0]):
            if normalized(key) in ID_KEYS:
                self.remember(val, 'id')
        try:
            parts = urlsplit(value)
        except ValueError:
            return
        host = (parts.hostname or '').lower()
        for key, val in parse_qsl(parts.query):
            if normalized(key) in ID_KEYS or (parts.path.endswith('/view_info.php') and key == 'id'):
                self.remember(val, 'id')
        if host in {'blog.naver.com', 'm.blog.naver.com'}:
            first = unquote(parts.path.strip('/').split('/')[0])
            if first and not first.lower().endswith(('.naver', '.nhn')):
                self.remember(first, 'id')
        if host in {'cafe.naver.com', 'm.cafe.naver.com'} or not host:
            member = re.search(r'/members/([^/?]+)', parts.path)
            if member:
                self.remember(unquote(member[1]), 'id')
        match = re.search(r'/(?:channel/|user/|@)([^/?]+)', parts.path)
        if host.endswith('youtube.com') and match:
            self.remember(unquote(match[1]), 'id')
        if any(marker in host for marker in ('profile', 'blogpfthumb', 'yt3.')):
            self.remember(value, 'profile')

    def discover_text(self, text, source=None):
        for value in EMAIL.findall(text):
            self.remember(value, 'email')
        for value in URL.findall(text.replace('\\/', '/')):
            self.discover_url(value)
        # Embedded hydration/config JSON and JavaScript object literals.
        # Naver mobile pages also expose identity through bare JS assignments.
        pattern = r'''(?:["']([\w-]+)["']|\b([A-Za-z_]\w*))\s*[:=]\s*(["'])((?:\\.|(?!\3).)*?)\3'''
        for match in re.finditer(pattern, text):
            value = match[4]
            try:
                value = json.loads('"' + value + '"')
            except ValueError:
                pass
            self.discover_field(match[1] or match[2], value, source)
        for match in re.finditer(r'''(?:showMemberInfo|showMemberMenu|memberInfo)\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]''', text):
            self.remember(match[1], 'id')
            self.remember(match[2], 'name')

    def discover_field(self, key, value, source=None):
        key = normalized(key)
        # Site/ad script channels are dotted config identifiers. YouTube's
        # channel field is a display name, even when it has the same syntax.
        if (key == 'channel' and source in SOURCES and source != 'youtube'
                and isinstance(value, str)
                and re.fullmatch(r'[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)+', value, re.ASCII)):
            return
        if key in NAME_KEYS:
            self.remember(value, 'name')
        elif key in ID_KEYS:
            self.remember(value, 'id')
        elif key in {normalized(k) for k in PROFILE_KEYS}:
            self.remember(value, 'profile')

    def discover_json(self, obj, source=None):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if normalized(key) in {'writer', 'author'} and isinstance(value, dict):
                    for field, identity in value.items():
                        field = normalized(field)
                        if not isinstance(identity, str) or field.startswith('memberlevel'):
                            continue
                        if field.endswith(('memberkey', 'memberid')) or field in {'id', 'userid'}:
                            self.remember(identity, 'id')
                        elif ('image' in field or 'profile' in field) and (
                                field.endswith('url') or identity.startswith(('http://', 'https://', '//', '/'))):
                            self.remember(identity, 'profile')
                        elif field in {'nick', 'nickname', 'name'}:
                            self.remember(identity, 'name')
                if isinstance(value, str):
                    self.discover_field(key, value, source)
                self.discover_json(value, source)
        elif isinstance(obj, list):
            for value in obj:
                self.discover_json(value, source)
        elif isinstance(obj, str):
            if source in {'naver_blog', 'naver_cafe'} and '<' in obj:
                self.discover_html(source, obj)
            else:
                self.discover_text(obj, source)

    def discover_html(self, source, text):
        from selectolax.parser import HTMLParser
        self.discover_text(text, source)
        if source == 'ppomppu':
            for match in re.finditer(r'\bvar\s+initialCommentData\s*=\s*', text):
                data, _ = json.JSONDecoder().raw_decode(text[match.end():])
                self.discover_ppomppu_comments(data.get('comments', []))
            for match in re.finditer(r'''\bview_info\(\s*['"]([^'"]+)['"]''', html.unescape(text)):
                self.remember(match[1], 'id')
        # Responses are already decoded using the recorded transport charset.
        # Do not let a legacy meta charset reinterpret these UTF-8 parser bytes:
        # that corrupts discovered identities (and audit placeholders) so they
        # no longer match the original text during substitution.
        tree = HTMLParser(text.encode('utf-8', errors='replace'), detect_encoding=False)
        selectors = SELECTORS[source]
        if source.startswith('naver_'):
            selectors += ', ' + NAVER_NAMES
        for node in tree.css(selectors):
            # Blog profile titles may repeat or split names across nested spans.
            # html() substitutes individual text tokens, so discover those same
            # tokens instead of a concatenation absent from the original markup.
            names = (list(identity_text_parts(node)) if source == 'naver_blog'
                     else [node.text(strip=True)])
            for value in (*names, node.attributes.get('title'), node.attributes.get('alt')):
                self.remember(value, 'name')
            for child in node.css('img'):
                self.remember(child.attributes.get('alt'), 'name')
                self.remember(child.attributes.get('src'), 'profile')
        for node in tree.css('*'):
            attrs = node.attributes
            if attrs.get('href'):
                self.discover_url(attrs['href'])
                if source.startswith('naver_') and re.search(r'/members/|MemberProfile|member[.]nhn', attrs['href'], re.I):
                    self.remember(node.text(strip=True), 'name')
            for key, value in attrs.items():
                self.discover_field(key.removeprefix('data-'), value, source)
            marker = ' '.join((attrs.get('class') or '', attrs.get('id') or '')).lower()
            if node.tag == 'img' and any(s in marker for s in ('profile', 'avatar', 'member', 'nick')):
                for key in ('src', 'data-src', 'srcset'):
                    self.remember(attrs.get(key), 'profile')
                self.remember(attrs.get('alt'), 'name')

    def discover_ppomppu_comments(self, comments):
        from selectolax.parser import HTMLParser
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            name = comment.get('name', '')
            tree = HTMLParser(name)
            self.remember(tree.text(strip=True), 'name')
            self.discover_html('ppomppu', name)
            for markup in (name, comment.get('image', '')):
                for node in HTMLParser(markup).css('img'):
                    for key in ('src', 'data-src', 'srcset'):
                        self.remember(node.attributes.get(key), 'profile')
                    self.remember(node.attributes.get('alt'), 'name')
            self.remember((comment.get('meta') or {}).get('ip_display'), 'ip')
            self.discover_ppomppu_comments(comment.get('sub_cmt') or [])

    def text(self, text):
        text = URL.sub(lambda m: strip_query_secrets(m[0]), text)
        # One substitution pass avoids replacing text inside generated placeholders.
        variants = {}
        for original, replacement in self.mapping.items():
            variants[original] = replacement
            variants.setdefault(html.escape(original, quote=True), html.escape(replacement, quote=True))
            variants.setdefault(json.dumps(original, ensure_ascii=True)[1:-1], json.dumps(replacement, ensure_ascii=True)[1:-1])
            variants.setdefault(original.replace('/', '\\/'), replacement.replace('/', '\\/'))
            variants.setdefault(quote(original, safe=''), quote(replacement, safe=''))
        for secret in self.secrets:
            for variant in (secret, quote(secret, safe=''), html.escape(secret), json.dumps(secret)[1:-1]):
                variants[variant] = '[REDACTED]'
        if variants:
            pattern = '|'.join(
                (r'(?<![\w])' if v[0].isalnum() or v[0] == '_' else '') + re.escape(v)
                + (r'(?![\w])' if v[-1].isalnum() or v[-1] == '_' else '')
                for v in sorted(variants, key=len, reverse=True))
            text = re.sub(pattern, lambda m: variants[m[0]], text)
        # Secrets are scrubbed even when embedded in a longer response string.
        for secret in self.secrets:
            for value in (secret, quote(secret, safe=''), html.escape(secret), json.dumps(secret)[1:-1]):
                text = text.replace(value, '[REDACTED]')
        return URL.sub(lambda m: strip_query_secrets(m[0]), text)

    def json(self, obj):
        if isinstance(obj, dict):
            return {k: ('[REDACTED]' if SECRET_KEY.search(k) else self.json(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.json(v) for v in obj]
        return self.text(obj) if isinstance(obj, str) else obj

    def html(self, text):
        # Preserve tags, whitespace, attribute order and quoting; mask values only.
        tokens = re.split(r'(<[^>]*>)', text)
        for i, token in enumerate(tokens):
            if token.startswith('<') and not token.startswith('<!--'):
                def attribute(match):
                    if match[1].lower() in {'class', 'id', 'name', 'type'}:
                        return match[0]
                    value = match[3]
                    if value[:1] in {'\"', "'"}:
                        value = value[0] + self.text(value[1:-1]) + value[-1]
                    else:
                        value = self.text(value)
                    return match[1] + match[2] + value
                tokens[i] = re.sub(r'''([\w:-]+)(\s*=\s*)("[^"]*"|'[^']*'|[^\s>]+)''',
                                   attribute, token, flags=re.S)
            else:
                tokens[i] = self.text(token)
        return ''.join(tokens)


def mask_html(source, text, masker=None):
    masker = masker or Masker()
    masker.discover_html(source, text)
    return masker.html(text)


def mask_json(source, obj, masker=None):
    if source not in SOURCES:
        raise ValueError('unsupported source')
    masker = masker or Masker()
    masker.discover_json(obj, source)
    return masker.json(obj)


def trim_youtube(obj):
    if isinstance(obj, dict):
        return {k: trim_youtube(v) for k, v in obj.items() if k not in TRIM_KEYS}
    if isinstance(obj, list):
        return [trim_youtube(v) for v in obj]
    return obj


def write_manifest(directory, manifest, masker, force=False):
    path = Path(directory) / 'manifest.json'
    masker.discover_json(manifest)
    data = masker.json(manifest)
    data['masking_stats'] = dict(masker.counts)
    with path.open('w' if force else 'x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


class Blocked(Exception):
    pass


class Recorder:
    def __init__(self, source, keyword, out, force=False, secrets=()):
        self.source, self.force = source, force
        self.directory = Path(out) / source
        if self.directory.exists() and any(self.directory.iterdir()) and not force:
            raise FileExistsError('fixture directory is not empty; use --force explicitly')
        self.masker = Masker(secrets)
        self.pending = []
        self.last_request = 0.0
        self.blocked = False
        self.manifest = {'source': source, 'keyword': keyword,
                         'captured_at': datetime.now(timezone.utc).isoformat(),
                         'requests': [], 'notes': [], 'masking_stats': {}}

    def wait(self):
        if self.blocked:
            raise Blocked()
        time.sleep(max(0, 1 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()

    def record(self, url, status, encoding=None, file=None, **extra):
        self.manifest['requests'].append(dict(url=url, status_code=status, encoding=encoding, file=file, **extra))
        if status in (403, 429):
            self.blocked = True
            self.manifest['notes'].append('Stopped on HTTP 403/429; no retries.')
            raise Blocked()

    def get(self, client, url, file, headers=None):
        # Follow redirects explicitly: every hop gets throttled and recorded.
        for _ in range(10):
            self.wait()
            try:
                response = client.get(url, headers=headers)
            except Exception:
                self.record(url, None, notes='Transport failed; no HTTP response received.')
                raise
            encoding = response.encoding or 'utf-8'
            if self.source == 'ppomppu':
                charset = re.search(rb'charset\s*=\s*["\']?([\w-]+)', response.content[:8192], re.I)
                declared = re.search(r'charset\s*=\s*[\"\']?([\w-]+)', response.headers.get('content-type', ''), re.I)
                encoding = (declared[1] if declared else charset[1].decode('ascii') if charset else 'euc-kr')
            self.record(str(response.url), response.status_code, encoding,
                        file if not response.is_redirect else None)
            if response.is_redirect:
                url = urljoin(str(response.url), response.headers['location'])
                headers = None  # Never forward Naver credentials to a redirected host.
                continue
            text = response.content.decode(encoding, errors='surrogateescape')
            if file.endswith('.json'):
                self.pending.append((file, response.json(), 'utf-8'))
            else:
                self.pending.append((file, text, encoding))
            if self.source == 'naver_cafe':
                self.manifest['requests'][-1].update(restriction=restriction(text, str(response.url)))
            expected_restriction = (self.source == 'naver_cafe' and file.endswith('.json')
                                    and response.status_code == 401
                                    and response.json().get('errorCode') == '0004')
            if expected_restriction:
                self.manifest['requests'][-1]['restriction'].update(login=True, access='restricted')
            elif self.source == 'naver_cafe' and file.endswith('.json') and response.status_code == 200:
                self.manifest['requests'][-1]['restriction']['access'] = 'public'
            elif not (self.source == 'naver_cafe' and file.endswith('.json')):
                response.raise_for_status()
            return response
        raise RuntimeError('redirect limit')

    def save(self):
        # Discover across ALL pages first, then write only masked representations.
        for filename, data, _ in self.pending:
            if filename.endswith('.json'):
                self.masker.discover_json(data, self.source)
            else:
                self.masker.discover_html(self.source, data)
        self.masker.discover_json(self.manifest)
        self.directory.mkdir(parents=True, exist_ok=True)
        for filename, data, encoding in self.pending:
            if filename.endswith('.json'):
                payload = json.dumps(self.masker.json(data), ensure_ascii=False, indent=2).encode('utf-8')
            else:
                payload = self.masker.html(data).encode(encoding, errors='surrogateescape')
            with (self.directory / filename).open('wb' if self.force else 'xb') as stream:
                stream.write(payload)
        write_manifest(self.directory, self.manifest, self.masker, self.force)
        print(json.dumps({'masking_stats': dict(self.masker.counts)}, ensure_ascii=False))


def restriction(text, url=''):
    login = 'nid.naver.com' in url or any(s in text for s in ('로그인이 필요', '로그인 후', '로그인해주세요'))
    grade = any(s in text for s in ('등급 이상', '멤버만', '멤버에게만', '가입한 멤버', '접근 권한', '권한이 없습니다'))
    return {'login': login, 'grade_restricted': grade, 'access': 'restricted' if login or grade else 'unknown'}


def mobile_url(source, url):
    parts = urlsplit(html.unescape(url))
    allowed = {'naver_blog': {'blog.naver.com', 'm.blog.naver.com'},
               'naver_cafe': {'cafe.naver.com', 'm.cafe.naver.com'}}[source]
    if parts.scheme not in ('http', 'https') or parts.hostname not in allowed:
        raise ValueError('unsupported Naver detail URL')
    query = dict(parse_qsl(parts.query))
    if source == 'naver_blog' and query.get('blogId') and query.get('logNo'):
        return f"https://m.blog.naver.com/{quote(query['blogId'])}/{quote(query['logNo'])}"
    if source == 'naver_cafe' and query.get('clubid') and query.get('articleid'):
        return f"https://m.cafe.naver.com/ca-fe/web/cafes/{quote(query['clubid'])}/articles/{quote(query['articleid'])}"
    host = 'm.blog.naver.com' if source == 'naver_blog' else 'm.cafe.naver.com'
    return urlunsplit(('https', host, parts.path, parts.query, ''))


def article_urls(source, text, base):
    from selectolax.parser import HTMLParser
    result = []
    seen = set()
    for node in HTMLParser(text).css('a[href]'):
        try:
            url = urljoin(base, html.unescape(node.attributes['href']))
            parts = urlsplit(url)
        except ValueError:
            continue
        if source in {'naver_blog', 'naver_cafe'}:
            host = 'blog.naver.com' if source == 'naver_blog' else 'cafe.naver.com'
            if (parts.scheme in {'http', 'https'} and parts.hostname in {host, 'm.' + host}
                    and re.fullmatch(r'/[^/]+/\d+/?', parts.path)):
                canonical = 'https://' + host + parts.path.rstrip('/')
                if canonical not in seen:
                    seen.add(canonical)
                    result.append(canonical)
            continue
        if parts.hostname != urlsplit(base).hostname:
            continue
        query = dict(parse_qsl(parts.query))
        good = (re.match(r'^/service/board/[^/]+/\d+', parts.path) if source == 'clien'
                else parts.path.endswith('/view.php') and query.get('id') and query.get('no'))
        canonical = (parts.scheme, parts.netloc, parts.path) if source == 'clien' else url
        if good and canonical not in seen:
            seen.add(canonical)
            result.append(url)
    return result


def cafe_article_url(url):
    parts = urlsplit(html.unescape(url))
    if parts.scheme not in {'http', 'https'} or parts.hostname not in {'cafe.naver.com', 'm.cafe.naver.com'}:
        raise ValueError('unsupported Naver cafe article URL')
    match = re.fullmatch(r'/([^/]+)/(\d+)/?', parts.path)
    if not match:
        raise ValueError('expected cafeUrl/articleId URL')
    return (f'https://article.cafe.naver.com/gw/v4/cafes/{quote(unquote(match[1]), safe="")}'
            f'/articles/{match[2]}?useCafeId=false')


def capture_youtube(recorder, keyword, details, urls):
    from yt_dlp import YoutubeDL
    from yt_dlp.networking.exceptions import HTTPError

    class QuietLogger:
        def debug(self, *args): pass
        def warning(self, *args): pass
        def error(self, *args): pass

    class PoliteYDL(YoutubeDL):
        def urlopen(self, req):
            recorder.wait()
            url = req if isinstance(req, str) else req.url
            try:
                response = super().urlopen(req)
            except HTTPError as exc:
                recorder.record(url, exc.status)
                raise
            recorder.record(url, response.status)
            return response

    options = {'quiet': True, 'no_warnings': True, 'logger': QuietLogger(), 'cachedir': False,
               'socket_timeout': 15, 'retries': 0, 'extractor_retries': 0, 'fragment_retries': 0,
               'skip_download': True, 'extract_flat': True}
    with PoliteYDL(options) as ydl:
        data = ydl.sanitize_info(ydl.extract_info(f'ytsearch10:{keyword}', download=False))
        recorder.pending.append(('list.json', trim_youtube(data), 'utf-8'))
        recorder.record(f'ytsearch10:{keyword}', None, 'utf-8', 'list.json',
                        notes='Extractor output; HTTP status codes are in individual request records.')
    selected = urls or [entry.get('url') or f"https://www.youtube.com/watch?v={entry['id']}"
                        for entry in data.get('entries', []) if entry]
    options.update(extract_flat=False, getcomments=True,
                   extractor_args={'youtube': {'max_comments': ['30', 'all', '10', '5']}})
    for index, url in enumerate(selected[:details], 1):
        with PoliteYDL(options) as ydl:
            data = ydl.sanitize_info(ydl.extract_info(url, download=False))
        recorder.pending.append((f'detail-{index}.json', trim_youtube(data), 'utf-8'))
        recorder.record(url, None, 'utf-8', f'detail-{index}.json',
                        notes='Extractor output; HTTP status codes are in individual request records.')


def capture_http(recorder, args):
    import httpx
    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=False) as client:
        urls = args.url
        if args.source.startswith('naver_'):
            discovered = []
            kind = 'blog' if args.source == 'naver_blog' else 'cafe'
            for page in range(1, args.pages + 1):
                url = 'https://search.naver.com/search.naver?' + urlencode({
                    'ssc': f'tab.{kind}.all', 'query': args.keyword, 'start': 1 + 30 * (page - 1)})
                response = recorder.get(client, url, f'list-{page}.html')
                discovered.extend(article_urls(args.source, response.text, str(response.url)))
            urls = list(dict.fromkeys(urls or discovered))
            if args.source == 'naver_cafe':
                public = 0
                limit = args.max_tries if args.max_tries is not None else 3 * args.details
                for index, url in enumerate(urls[:limit], 1):
                    if public >= args.details:
                        break
                    response = recorder.get(client, cafe_article_url(url), f'detail-{index}.json',
                                            {'Referer': 'https://m.cafe.naver.com/'})
                    public += response.status_code == 200
                if public < args.details:
                    recorder.manifest['notes'].append(
                        f'Public article target not reached: {public}/{args.details}; candidates or max-tries exhausted.')
                return
            urls = [mobile_url(args.source, url) for url in urls]
        else:
            if args.source == 'clien':
                url = 'https://www.clien.net/service/search?' + urlencode(
                    {'q': args.keyword, 'sort': 'recency', 'boardCd': '', 'isBoard': 'false'})
            else:
                url = 'https://www.ppomppu.co.kr/search_bbs.php?keyword=' + quote(args.keyword.encode('euc-kr'))
                client.headers['Referer'] = 'https://www.ppomppu.co.kr/'
            response = recorder.get(client, url, 'list.html')
            urls = urls or article_urls(args.source, recorder.pending[-1][1], str(response.url))
            client.headers['Referer'] = str(response.url)
        for index, url in enumerate(urls[:args.details], 1):
            recorder.get(client, url, f'detail-{index}.html')


def audit_fixture(directory):
    """Return counts of distinct unmasked known values by kind; never expose values.

    Reads only local files. Counts are deduplicated within each kind across files.
    Parse/read failures fail closed through an error count.
    """
    directory = Path(directory)

    class Auditor(Masker):
        def __init__(self):
            super().__init__()
            self.seen = set()

        def remember(self, value, kind):
            if not isinstance(value, str) or not value.strip():
                return
            value = html.unescape(value.strip())
            if re.fullmatch(r'(?:사용자[A-Z]+|@?user_[a-z]+)', value):
                return
            if kind == 'email' and re.fullmatch(r'user_[a-z]+@example\.invalid', value):
                return
            if kind == 'profile':
                try:
                    parts = urlsplit(value)
                except ValueError:
                    parts = None  # Malformed profile values are still findings.
                if parts is not None and parts.hostname == 'example.invalid':
                    return
                if parts is not None and parts.hostname in {'www.youtube.com', 'youtube.com'} and re.fullmatch(
                        r'/(?:channel/|user/|@)?(?:user_[a-z]+|사용자[A-Z]+)',
                        unquote(parts.path)) and not parts.query and not parts.fragment:
                    return
            if (kind, value) not in self.seen:
                self.seen.add((kind, value))
                self.counts[kind] += 1

    auditor = Auditor()
    try:
        if not directory.exists():
            return {'missing_directory': 1}
        if not directory.is_dir():
            return {'not_directory': 1}
        files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in {'.html', '.json'})
        if not files:
            return {'empty_directory': 1}
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        source = manifest.get('source', directory.name)
        if source not in SOURCES or not directory.is_dir():
            return {'error': 1}
        encodings = {r.get('file'): r.get('encoding') for r in manifest.get('requests', [])}
        for path in files:
            try:
                if path.suffix == '.json':
                    auditor.discover_json(json.loads(path.read_text(encoding='utf-8')), source)
                else:
                    encoding = encodings.get(path.name) or ('euc-kr' if source == 'ppomppu' else 'utf-8')
                    auditor.discover_html(source, path.read_bytes().decode(encoding, errors='surrogateescape'))
            except Exception:
                auditor.counts['error'] += 1
    except Exception:
        auditor.counts['error'] += 1
    return dict(auditor.counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', choices=SOURCES, nargs='?')
    parser.add_argument('keyword', nargs='?')
    parser.add_argument('--audit', type=Path, metavar='DIRECTORY', help='Audit saved fixtures offline; print counts only')
    parser.add_argument('--details', type=int, default=3)
    parser.add_argument('--out', type=Path, default=Path('backend/tests/fixtures/http'))
    parser.add_argument('--url', action='append', default=[], help='Repeat to override detail candidates; cafe counts public responses toward --details')
    parser.add_argument('--pages', type=int, default=1, help='Naver search pages (30 results per page)')
    parser.add_argument('--max-tries', type=int, help='Cafe article request limit (default: 3 * --details)')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    if args.audit is not None:
        counts = audit_fixture(args.audit)
        result = {'audit_counts': counts, 'total': sum(counts.values())}
        for reason in ('missing_directory', 'empty_directory', 'not_directory'):
            if reason in counts:
                result.update(status='not_audited', reason=reason)
                break
        print(json.dumps(result))
        return int(bool(counts))
    if args.source is None or args.keyword is None:
        parser.error('source and keyword are required for capture')
    if args.details < 0 or args.pages < 1 or (args.max_tries is not None and args.max_tries < 0):
        parser.error('--details and --max-tries must be nonnegative; --pages must be positive')
    secrets = [os.getenv(key, '') for key in ('NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET', 'YOUTUBE_API_KEY')]
    try:
        recorder = Recorder(args.source, args.keyword, args.out, args.force, secrets)
    except FileExistsError:
        print('Refusing to overwrite existing fixtures. Use --force explicitly.', file=sys.stderr)
        return 2
    code = 0
    # Third-party extractors may emit raw URLs; never expose their diagnostics.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            if args.source == 'youtube':
                capture_youtube(recorder, args.keyword, args.details, args.url)
            else:
                capture_http(recorder, args)
            if recorder.blocked:
                code = 1
        except Blocked:
            code = 1
        except Exception:
            recorder.manifest['notes'].append('Capture failed; inspect recorded status codes. Raw diagnostics suppressed.')
            code = 1
    try:
        recorder.save()
    except Exception:
        print('Could not safely write fixtures; inspect output directory before retrying.', file=sys.stderr)
        return 1
    return code


if __name__ == '__main__':
    sys.exit(main())
