"""
Crawl4AI service — 2nd stage crawler for Naver Cafe post body + metadata.

Uses Playwright (via Crawl4AI) to render Naver Cafe pages, extract full body
text and engagement metadata from the iframe-embedded article content.
"""

import re
import asyncio
import random
import logging
from datetime import datetime

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS selector chains (primary → fallback) — 모듈 상수로 관리, 변경 대응 용이
# ---------------------------------------------------------------------------

BODY_SELECTORS = [
    ".se-main-container",       # Smart Editor ONE (신형)
    "#postViewArea",            # Legacy editor (구형)
]

AUTHOR_SELECTORS = [".article_writer .nick", ".nick_box .nickname"]
DATE_SELECTORS = [".article_info .date"]
VIEW_SELECTORS = [".article_info .count"]
COMMENT_COUNT_SELECTORS = [".comment_count", ".comment_info .num"]
LIKE_SELECTORS = [".like_article .u_cnt", ".btn_like .count"]
BOARD_SELECTORS = [".article_board .link_board"]
HEADING_SELECTORS = [".se-section-title .se-text-paragraph"]
IMAGE_SELECTORS = [".se-image-resource"]


# ---------------------------------------------------------------------------
# Cookie parsing
# ---------------------------------------------------------------------------

def _parse_cookies(cookie_str: str | None) -> list[dict]:
    """Parse 'NID_AUT=xxx; NID_SES=yyy' into Playwright cookie dicts."""
    if not cookie_str:
        logger.warning("No cookies provided — crawling in non-login mode (some cafes may block access)")
        return []
    cookies = []
    for pair in re.split(r"[;\n]", cookie_str):
        pair = pair.strip()
        if "=" in pair:
            name, value = pair.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".naver.com",
                "path": "/",
            })
    return cookies


# ---------------------------------------------------------------------------
# Metadata extraction JS (run inside iframe page context)
# ---------------------------------------------------------------------------

EXTRACT_JS = """
(() => {
    function qs(sels) {
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el) return el.innerText.trim();
        }
        return null;
    }
    function qsAll(sels) {
        for (const s of sels) {
            const els = document.querySelectorAll(s);
            if (els.length > 0) return Array.from(els).map(e => e.innerText.trim());
        }
        return [];
    }
    function countAll(sels) {
        for (const s of sels) {
            const els = document.querySelectorAll(s);
            if (els.length > 0) return els.length;
        }
        return 0;
    }
    function parseNum(text) {
        if (!text) return null;
        const m = text.replace(/,/g, '').match(/\\d+/);
        return m ? parseInt(m[0], 10) : null;
    }

    const body = qs(BODY_SELECTORS);
    const author = qs(AUTHOR_SELECTORS);
    const dateRaw = qs(DATE_SELECTORS);
    const viewRaw = qs(VIEW_SELECTORS);
    const commentRaw = qs(COMMENT_COUNT_SELECTORS);
    const likeRaw = qs(LIKE_SELECTORS);
    const board = qs(BOARD_SELECTORS);
    const headings = qsAll(HEADING_SELECTORS);
    const imageCount = countAll(IMAGE_SELECTORS);

    return {
        body: body,
        author: author,
        date_raw: dateRaw,
        view_count: parseNum(viewRaw),
        comment_count: parseNum(commentRaw),
        like_count: parseNum(likeRaw),
        board_name: board,
        headings: headings,
        image_count: imageCount,
    };
})();
""".replace(
    "BODY_SELECTORS", str(BODY_SELECTORS)
).replace(
    "AUTHOR_SELECTORS", str(AUTHOR_SELECTORS)
).replace(
    "DATE_SELECTORS", str(DATE_SELECTORS)
).replace(
    "VIEW_SELECTORS", str(VIEW_SELECTORS)
).replace(
    "COMMENT_COUNT_SELECTORS", str(COMMENT_COUNT_SELECTORS)
).replace(
    "LIKE_SELECTORS", str(LIKE_SELECTORS)
).replace(
    "BOARD_SELECTORS", str(BOARD_SELECTORS)
).replace(
    "HEADING_SELECTORS", str(HEADING_SELECTORS)
).replace(
    "IMAGE_SELECTORS", str(IMAGE_SELECTORS)
)

# JS to extract the iframe src from the main cafe page
IFRAME_SRC_JS = """
(() => {
    const iframe = document.querySelector('iframe#cafe_main');
    return iframe ? iframe.src : null;
})();
"""


def _parse_date(date_raw: str | None) -> str | None:
    """Convert Naver date string like '2025.03.15. 14:32' to ISO format."""
    if not date_raw:
        return None
    cleaned = re.sub(r"\.\s*$", "", date_raw.strip())
    for fmt in ["%Y.%m.%d. %H:%M", "%Y.%m.%d %H:%M", "%Y.%m.%d.", "%Y.%m.%d"]:
        try:
            return datetime.strptime(cleaned, fmt).isoformat()
        except ValueError:
            continue
    return date_raw


# ---------------------------------------------------------------------------
# Single URL crawler
# ---------------------------------------------------------------------------

async def _crawl_single(
    url: str,
    crawler: AsyncWebCrawler,
    semaphore: asyncio.Semaphore,
    cookies: list[dict],
) -> dict:
    """Crawl a single Naver Cafe post URL and extract body + metadata."""
    result = {
        "url": url,
        "body": None,
        "meta": {
            "author": None,
            "written_at": None,
            "view_count": None,
            "comment_count": None,
            "like_count": None,
            "board_name": None,
            "image_count": 0,
            "headings": [],
            "body_length": 0,
            "crawl_status": "failed",
        },
    }

    for attempt in range(settings.crawl4ai_max_retries):
        try:
            async with semaphore:
                await asyncio.sleep(random.uniform(
                    settings.crawl4ai_min_delay, settings.crawl4ai_max_delay
                ))

                # Step 1: Load main page to get iframe src
                config = CrawlerRunConfig(
                    js_code=IFRAME_SRC_JS,
                    wait_for="css:iframe#cafe_main",
                    page_timeout=15000,
                )
                if cookies:
                    config.cookies = cookies

                main_result = await crawler.arun(url=url, config=config)

                # Extract iframe src from JS result
                iframe_src = None
                if main_result.js_result:
                    iframe_src = main_result.js_result if isinstance(main_result.js_result, str) else None

                if not iframe_src:
                    logger.warning("Could not extract iframe src for %s, trying direct approach", url)
                    iframe_src = url

                # Step 2: Navigate to iframe URL and extract content
                extract_config = CrawlerRunConfig(
                    js_code=EXTRACT_JS,
                    wait_for="css:.se-main-container, #postViewArea",
                    page_timeout=15000,
                )
                if cookies:
                    extract_config.cookies = cookies

                article_result = await crawler.arun(url=iframe_src, config=extract_config)

                if article_result.js_result and isinstance(article_result.js_result, dict):
                    data = article_result.js_result
                    body_text = data.get("body") or ""
                    result["body"] = body_text
                    result["meta"] = {
                        "author": data.get("author"),
                        "written_at": _parse_date(data.get("date_raw")),
                        "view_count": data.get("view_count"),
                        "comment_count": data.get("comment_count"),
                        "like_count": data.get("like_count"),
                        "board_name": data.get("board_name"),
                        "image_count": data.get("image_count", 0),
                        "headings": data.get("headings", []),
                        "body_length": len(body_text),
                        "crawl_status": "success" if body_text and len(body_text) > 10 else "failed",
                    }
                else:
                    # Fallback: use the markdown content from Crawl4AI
                    if article_result.markdown and len(article_result.markdown) > 50:
                        result["body"] = article_result.markdown
                        result["meta"]["body_length"] = len(article_result.markdown)
                        result["meta"]["crawl_status"] = "success"

                return result

        except Exception as e:
            error_msg = str(e)
            is_retryable = any(code in error_msg for code in ["429", "403", "Timeout", "timeout"])

            if is_retryable and attempt < settings.crawl4ai_max_retries - 1:
                delay = (2 ** (attempt + 1)) + random.uniform(0, 1)
                logger.warning("Retryable error for %s (attempt %d): %s, retrying in %.1fs",
                               url, attempt + 1, error_msg[:100], delay)
                await asyncio.sleep(delay)
                continue

            logger.error("Crawl failed for %s after %d attempts: %s", url, attempt + 1, error_msg[:200])
            return result

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def crawl_cafe_posts(
    urls: list[str],
    cookies: str | None = None,
    on_progress=None,
    should_stop=None,
) -> list[dict]:
    """
    Crawl a list of Naver Cafe post URLs to extract body text and metadata.

    Args:
        urls: List of Naver Cafe post URLs to crawl.
        cookies: Optional cookie string (e.g. "NID_AUT=xxx; NID_SES=yyy").
        on_progress: Optional callback(crawled: int, success: int, failed: int)
                     called after each URL completes.
        should_stop: Optional callable returning bool. When True, cancel remaining tasks.

    Returns:
        List of dicts with keys: url, body, meta (contains crawl_status).
    """
    if not urls:
        return []

    parsed_cookies = _parse_cookies(cookies)
    semaphore = asyncio.Semaphore(settings.crawl4ai_concurrency)
    results: list[dict] = []
    success_count = 0
    failed_count = 0

    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = []
        for url in urls:
            task = asyncio.create_task(
                _crawl_single(url, crawler, semaphore, parsed_cookies)
            )
            tasks.append(task)

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            if result["meta"]["crawl_status"] == "success":
                success_count += 1
            else:
                failed_count += 1
            if on_progress:
                on_progress(len(results), success_count, failed_count)

            # Stop requested: cancel remaining tasks
            if should_stop and should_stop():
                for t in tasks:
                    if not t.done():
                        t.cancel()
                # Suppress CancelledError from cancelled tasks
                for t in tasks:
                    if t.cancelled():
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass
                logger.info("Crawl4AI stopped by user after %d/%d URLs", len(results), len(urls))
                break

    return results
