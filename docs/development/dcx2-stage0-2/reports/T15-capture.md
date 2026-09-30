# T15–T17 HTTP fixture recorder

`scripts/capture_http_fixture.py` records real responses once on the host. No captures were run while implementing it. The synthetic snippets in `backend/tests/scripts/test_capture_masking.py` test the recorder's masking and file handling only; they are not channel-adapter fixtures. T15–T17 adapter tests must use host-recorded responses.

## Host usage

Run from the repository root with the backend virtual environment. Export credentials into the host environment using the existing secret provisioning mechanism; do not put key values in commands, URLs, or fixtures. The script deliberately does not load `.env` or the configuration's placeholder `x` credentials.

```sh
backend/.venv/bin/python scripts/capture_http_fixture.py --help
backend/.venv/bin/python scripts/capture_http_fixture.py naver_blog "에어컨" --details 3
backend/.venv/bin/python scripts/capture_http_fixture.py naver_cafe "에어컨" --details 3 --render
backend/.venv/bin/python scripts/capture_http_fixture.py youtube "에어컨" --details 3
backend/.venv/bin/python scripts/capture_http_fixture.py clien "에어컨" --details 3
backend/.venv/bin/python scripts/capture_http_fixture.py ppomppu "에어컨" --details 3
```

General syntax:

```text
backend/.venv/bin/python scripts/capture_http_fixture.py <source> "<keyword>" [--details N] [--out backend/tests/fixtures/http] [--url URL ...] [--render] [--force]
```

Repeat `--url URL` for each explicit detail URL. Explicit URLs replace discovered detail candidates; `--details` caps either list and defaults to 3. `--details 0` records only the list. Naver detail URLs work without credentials; the manifest notes that the list was skipped. Missing one or both Naver credentials skips the API call. If credentials are present, the list is recorded even when explicit detail URLs are supplied.

Files go into `<out>/<source>/`. A nonempty source directory is rejected before any network request unless `--force` is supplied. Prefer a fresh output directory for a different capture: `--force` overwrites generated names but does not delete older files absent from the new capture. Use the new manifest to identify that capture's artifacts.

## Source behavior

| Source | List | Details | Credentials/dependencies |
| --- | --- | --- | --- |
| `naver_blog` | `/v1/search/blog.json`, `display=10`, `start=1`, `list-1.json` | Desktop or legacy `PostView.naver` links become mobile blog URLs; `detail-N.html` | `NAVER_CLIENT_ID` and `NAVER_CLIENT_SECRET` for list only; httpx |
| `naver_cafe` | `/v1/search/cafearticle.json`, same pagination, `list-1.json` | Mobile café HTML; optional `detail-N.rendered.html` via crawl4ai | Same list credentials; crawl4ai and installed browser for `--render` |
| `youtube` | yt-dlp `ytsearch10:<keyword>` with `extract_flat=True`, `list.json` | `getcomments=True`, `max_comments=["30","all","10","5"]`, `detail-N.json` | yt-dlp; `YOUTUBE_API_KEY` is not required or used |
| `clien` | `/service/search?q=...&sort=recency&boardCd=&isBoard=false`, `list.html` | Unique same-host `/service/board/<board>/<number>` links | httpx and selectolax; no keys |
| `ppomppu` | `/search_bbs.php?keyword=...` with EUC-KR percent encoding, `list.html` | Unique same-host `view.php?id=...&no=...` links | httpx and selectolax; no keys |

Naver API requests send credentials only in `X-Naver-Client-Id` and `X-Naver-Client-Secret`. `NAVER_SEARCH_BASE_URL` defaults to `https://openapi.naver.com`, matching `backend/app/config.py`; the script appends `/v1/search/<kind>.json`. Redirects do not forward these credential headers.

Community requests use browser-like User-Agent, Accept, and Korean Accept-Language headers; Ppomppu also gets Referer. Ppomppu uses the declared HTTP charset, then HTML meta charset, then EUC-KR. HTML is decoded and re-encoded using that encoding with surrogate escape, preserving original bytes outside masked values rather than converting the document to UTF-8. It is impossible to keep identifying bytes unchanged and mask them simultaneously; no unmasked copy is written.

YouTube removes `formats`, `thumbnails`, `automatic_captions`, `requested_formats`, and `http_headers` recursively before saving. Video IDs, comment IDs, parent/thread references, and other parser-facing structure remain. The installed yt-dlp version accepts `extract_flat` as a `YoutubeDL` option and reads the four comment limits from `extractor_args['youtube']['max_comments']`.

## Masking and manifest

Responses remain in memory until all identities are discovered, then the same capture-wide mapping is applied to every file and the manifest. No mapping of original values is persisted or printed; stdout contains only category counts.

- Known JSON fields identify author/nickname/writer/blogger/channel names, member/author/blog/channel IDs, and profile images. Embedded JSON/JavaScript fields are also scanned.
- Source-specific author selectors include Naver nickname/writer nodes, Clien nickname/member nodes, and Ppomppu list/view/comment author nodes. Identity attributes and member-menu arguments are scanned. Image nicknames and profile images are replaced.
- Names become `사용자A`, `사용자B`, …; IDs become `user_a`, `user_b`, …, with stable replacements in related URLs. Emails become `user_a@example.invalid`; profile URLs use `https://example.invalid/profile_a.png`. Numbering is per identity category; names and IDs are not inferred to belong to the same person.
- Email detection runs throughout text. Known identifiers are also replaced in HTML-escaped, JSON-escaped, and percent-encoded forms. HTML tag structure and structural attributes remain intact; JSON keys and nesting remain intact.
- URLs lose userinfo, fragments, and credential query parameters while preserving useful query bytes. Known environment API-key values are redacted, including in response text. Raw third-party stdout, stderr, and exception messages are suppressed.

Each `manifest.json` contains the keyword, UTC capture time, source, request URLs, HTTP status codes, encodings, file associations, notes, and masking counts. Redirect hops are recorded. YouTube HTTP requests are recorded individually; logical extractor artifacts have null status codes instead of an invented HTTP status. Transport failures likewise use null status.

Café records include `restriction.login`, `restriction.grade_restricted`, and `restriction.access`. These flags use login redirect URLs and recognizable Korean restriction messages. Absence of a marker yields `access="unknown"`, not an assertion that a page is public. Inspect the host capture for new site layouts, unknown author fields, and ambiguous restriction pages before using it as an adapter fixture; update selectors against those real pages rather than inventing HTML.

## Request controls and verification

HTTP requests and redirect hops are serialized with at least one second between starts and a 15-second timeout. yt-dlp uses a throttled `urlopen`, 15-second socket timeout, disabled retries and disk cache, and a silent logger. Optional rendering gates browser requests with an asynchronous lock and one-second spacing; it uses a 15-second page/request timeout, disabled crawl4ai cache, and a null logger. A complex rendered page may time out under these limits; its failure is recorded without relaxing politeness.

HTTP 403/429 is recorded and stops the capture without retry. Completed earlier responses are still masked and saved. A failed/blocked capture exits 1, overwrite refusal exits 2, and successful capture exits 0. No login, grade restriction, or anti-bot bypass is attempted.

Offline verification (no capture commands executed):

```sh
cd backend && .venv/bin/python -m pytest tests/scripts -q
# From repository root:
backend/.venv/bin/python scripts/capture_http_fixture.py --help
```

The offline tests cover all five sources' masking, stable mappings, escaped identities, URL secrets, large YouTube-field trimming, thread references, manifest overwrite protection, late identity discovery, EUC-KR preservation, short IDs, 403/429 stop behavior, redirects, request spacing, suppressed errors, and keyless Naver explicit details. Live endpoint behavior and browser rendering remain for the host controller to verify.
