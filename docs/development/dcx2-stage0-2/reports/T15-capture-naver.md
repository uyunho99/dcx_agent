# T15 Naver fixture capture update

Date: 2026-09-29. Basis: T15-naver-probe.md and decision D-094.

Implemented in `scripts/capture_http_fixture.py`:

- Naver blog/cafe lists now use browser headers and `https://search.naver.com/search.naver`, with `ssc=tab.blog.all` / `tab.cafe.all`, keyword query and `start=1+30*(page-1)`. `--pages` defaults to 1; saves `list-<page>.html`. Extracts canonical article URLs, deduplicating in document/page order. `--url` overrides detail candidates; search pages are still captured.
- Removed the search API request path and missing-key manifest note. Legacy environment secrets remain in the defensive masking list only; no Naver credentials are sent.
- Blog details use `m.blog.naver.com` over httpx and save `detail-N.html`.
- Cafe details use `article.cafe.naver.com/gw/v4/cafes/<cafeUrl>/articles/<articleId>?useCafeId=false`, Referer `https://m.cafe.naver.com/`, saving `detail-N.json`. The explicit cafe URL form is `https://[m.]cafe.naver.com/<cafeUrl>/<articleId>`.
- Cafe 401 / `errorCode="0004"` responses are saved with status 401, `restriction.login=true` and restricted access. HTTP 200 is marked public. Cafe JSON HTTP errors other than 403/429 do not terminate the article loop; 403/429 retain immediate stop behavior. Transport/JSON decoding failures still fail the capture.
- Cafe `--details N` counts public HTTP 200 articles. Restricted responses occupy attempt-numbered files without counting toward N. `--max-tries` defaults to 3*N; capture also ends when candidates are exhausted, noting any public-target shortfall in the manifest. Increase `--pages` to supply more candidates. Existing one-second throttling remains.
- Removed `--render` and the crawl4ai cafe renderer. Cafe details now require neither browser rendering nor crawl4ai.
- Extended identity discovery for search profile/name rows, blog nicknames and bare script assignments, cafe writer objects (including scoped `id` and `imageUrl`), member profile links and mentions in article/comment HTML. Shared discovery runs before saving list/detail/manifest files; article/comment IDs and memberLevelName remain intact. Offline `--audit` uses the same source-aware discovery and prints counts only.

## TDD and verification

Added synthetic tests before implementation: the initial new suite produced 10 failures. After implementation, added a script-only blogId audit regression, observed its failure, then corrected discovery. Updated the obsolete test that expected missing API keys to skip the list.

Final command:

```text
backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?
47 passed, 1 warning
rc=0
```

Coverage includes ordered URL extraction/deduplication, pagination/query/header construction, explicit URL override, cafe 401 continuation and saved restriction bodies, public success counting, explicit/default attempt caps, 403/429 stops, writer/profile/mention masking, preserved article/comment IDs, blog URLs/markup/manifest masking, audit raw-versus-masked checks, and CLI defaults/validation/removal of rendering. All requests in tests use mocks; no network captures were run. `git diff --check` passed. No git add/commit.

## Concerns

Real capture and inspection remain with the controller. Synthetic search markup covers legacy `user_info` and newer `sds-comps-profile` structures; selectors and audit are heuristic and cannot certify unknown live markup. Candidate exhaustion or the request cap can leave fewer public articles than requested, explicitly noted in the manifest. The test warning is the existing Pydantic class-based Config deprecation in backend/app/config.py.

## Follow-up: malformed page URLs (2026-09-29)

Added five failing synthetic regressions for malformed URL fragments (`//[::1`), bracketed blog paths, malformed profile URLs, discovery/masking/save/audit, article-link extraction, query-secret removal, and missing/empty audit directories. URL discovery now catches `ValueError` while still discovering query identities and continuing text/markup discovery. Secret stripping has a plain-text query fallback; malformed article hrefs are skipped; audit counts malformed profile values as findings rather than aborting.

Empty/missing audit inputs now return explicit `empty_directory` / `missing_directory` counts and CLI `status="not_audited"` plus `reason`, with rc=1 so an absent fixture cannot be mistaken for a clean audit. Non-directory input is similarly explicit. Updated the former generic-error expectation for an empty directory.

Verification: `backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?` → **52 passed, 1 existing Pydantic warning; rc=0**. No network requests or git writes were performed.

## Follow-up: writer member-key variants (2026-09-29)

Added five failing synthetic cases covering article/comment `baMemberKey`, normalized member-key/member-id suffixes, writer/author objects across JSON sources, image/profile URL variants, and audit detection of remaining keys alongside existing placeholders. Extended shared masking/audit discovery from the cafe-specific writer allowlist to generic JSON writer/author objects. String keys ending in `memberkey` or `memberid`, plus `id`, `userid`, nick/nickname/name and image/profile URLs, are discovered; member-level metadata and booleans remain intact. Article/comment IDs remain outside this scoped identity rule.

Verification: `backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?` → **57 passed, 1 existing Pydantic warning; rc=0**. Read-only audit of `backend/tests/fixtures/http/naver_cafe` → **audit_counts={"id":10}, total=10, rc=1** (expected findings). No fixture edits, network requests, or git writes.

## Follow-up: site/ad channel configuration identifiers (2026-09-29)

Added synthetic regressions first: five site-config cases failed; four YouTube/display-name controls passed. Passed source context through text/field discovery so non-YouTube `channel` values matching dotted ASCII configuration identifiers (including `clien.ch1`, `clien.ch2`, `ppomppu.ch1`) are preserved and excluded from identity findings. YouTube channel names, including dotted names, remain masked and audited; ordinary site channel display names remain masked.

Verification: `backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?` → **66 passed, 1 existing Pydantic warning; rc=0**. Read-only `--audit` of all five existing fixture directories: **naver_blog=0, naver_cafe=0, youtube=0, clien=0, ppomppu=0** (each audit_counts={}, rc=0). No fixture edits, network requests, or git writes.

## Follow-up: search dates and public cafe names (2026-09-29)

Inspected both recorded list pages for each Naver source locally, emitting only selector structure and aggregate counts. No recorded names or IDs were printed. Blog rows use `.sds-comps-profile-info-title-text` (with a nested link/text span) for the blogger and `.sds-comps-profile-info-subtext` for date metadata. Cafe rows use `.user_info .name` for the public cafe display name and `.user_info .sub` for date metadata. The recorded date fields and cafe titles already contain masking placeholders; this change cannot recover their original values. Fixtures were not modified.

Removed `.user_info .sub` and `.sds-comps-profile-info-subtext` from person discovery. Profile title selectors `.user_info .name`, `.sds-comps-profile-info-title-text`, and `.sds-comps-profile-info-name-text` now discover names only for `naver_blog`; cafe titles remain public so adapters can retain community names in `src_meta.cafe`. Blog profile titles/nicknames and blog URL IDs remain masked. Cafe person selectors such as `.nickname`, `.nick_name`, `.comment_nickname`, and member-profile links remain masked, along with member IDs. Offline `--audit` uses the same discovery, so public titles and dates produce no identity findings while unmasked people still do.

Added 18 synthetic failing regressions before implementation, covering legacy/SDS date fields, relative and absolute dates, public cafe titles across title variants, private cafe member names/IDs, blog title names/IDs, and audit/CLI behavior. Corrected the earlier synthetic test that treated cafe profile titles as people by limiting its blog markup to the blog source.

Verification: `backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?` → **83 passed, 1 existing Pydantic warning; rc=0**. No network requests, git writes, fixture edits, or changes to backend application/frontend files.
