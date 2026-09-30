"""Canonical content URLs and deterministic document identifiers."""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_PREFIXES = {"naver_cafe":"nc","naver_blog":"nb","youtube":"yt","ppomppu":"pp","clien":"cl","fixture":"fx"}
_TRACKERS = {"fbclid", "gclid"}
_NAVER_TRACKERS = {"art", "query", "where", "sm"}
_YOUTUBE_TRACKERS = {"si", "feature", "t", "pp"}


def normalize_url(url: str, source: str) -> str:
    """Remove trackers and collapse the supported mobile/channel variants."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    # Preserve user info, if supplied, while normalizing only scheme and host.
    userinfo, separator, _ = parts.netloc.rpartition("@")
    netloc = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        netloc += f":{parts.port}"
    if separator:
        netloc = userinfo + "@" + netloc
    path = parts.path.rstrip("/")
    trackers = _TRACKERS
    if source in {"naver_cafe", "naver_blog"}:
        trackers = trackers | _NAVER_TRACKERS
    elif source == "youtube":
        trackers = trackers | _YOUTUBE_TRACKERS
    params = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in trackers
    ]

    if source == "naver_cafe" and host in {"m.cafe.naver.com", "cafe.naver.com"}:
        scheme, netloc = "https", "cafe.naver.com"
        if re.fullmatch(r"/ca-fe/[^/]+/[0-9]+", path):
            path = path.removeprefix("/ca-fe")
    elif source == "naver_blog" and host in {"m.blog.naver.com", "blog.naver.com"}:
        scheme, netloc = "https", "blog.naver.com"
    elif source == "youtube" and host in {"youtu.be", "m.youtube.com", "youtube.com", "www.youtube.com"}:
        scheme, netloc = "https", "www.youtube.com"
        if host == "youtu.be" and path.strip("/"):
            video_id = path.strip("/").split("/")[0]
            path = "/watch"
            params = [(key, value) for key, value in params if key != "v"]
            params.append(("v", video_id))

    return urlunsplit((scheme, netloc, path, urlencode(sorted(params)), ""))


def doc_id(source: str, url_norm: str, thread_key: str = "") -> str:
    """Channel prefix + underscore + sha1(URL + thread key)[:16]."""
    digest = hashlib.sha1((url_norm + thread_key).encode("utf-8")).hexdigest()[:16]
    return _PREFIXES[source] + "_" + digest
