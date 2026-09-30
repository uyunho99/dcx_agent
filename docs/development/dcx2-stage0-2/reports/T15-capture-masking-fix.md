# T15 capture masking fix

Implemented offline masking discovery, canonical Clien article deduplication, and a counts-only fixture audit. No network captures, fixture writes, staging, or commits were performed.

Changes:
- Ppomppu: scope HTML-valued name discovery to initialCommentData.comments and nested sub_cmt objects; discover comment images and meta.ip_display. Plain name keys elsewhere remain untouched.
- Ppomppu: discover post authors through .topTitle-name .baseList-name / .baseList-name, search writers through .content .desc > span:nth-child(2), view_info handlers, and view_info.php member ID query parameters. Inspection showed .bname contains the board label, so it is preserved.
- Clien: discover data-nick-id in addition to existing author/member attributes. Deduplicate article_urls by scheme, host, and path, ignoring query and fragment before applying the detail limit. Ppomppu article query identifiers remain significant.
- YouTube: explicitly discover uploader_url, channel_url, and author_url as identity URLs, alongside existing names, IDs, and thumbnails.
- audit_fixture(directory) returns counts of distinct non-placeholder values per kind, deduplicated across files. The --audit DIRECTORY CLI reads local HTML/JSON, honors manifest encodings with an EUC-KR fallback for Ppomppu, prints counts only, and exits 1 for leftovers or read/parse failures. Existing YouTube URLs containing plain or percent-encoded placeholders are accepted.

Validation used synthetic data only. The initial TDD run produced 5 failures and 23 passes. Final required command:

    backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?

Result: 30 passed; pytest rc=0. One existing Pydantic deprecation warning.

Read-only audit of existing captures:

| Source | Names | IDs | Profile URLs | Emails | Partial IPs | Errors | Total | Audit rc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clien | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ppomppu | 21 | 0 | 1 | 0 | 0 | 0 | 22 | 1 |
| youtube | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Clien audit covers nickname spans, member/author attributes, data-nick-id, and recognized profile markup. YouTube audit covers uploader, uploader_id, channel, channel_id, channel_url, uploader_url, and comment author, author_id, author_url, author_thumbnail fields. Zero means no non-placeholder values detected by these known-field rules, not a guarantee about arbitrary prose.

Existing Clien capture: 3 detail records, 2 distinct canonical articles, 1 duplicate.

Concerns: existing Ppomppu fixtures remain unmasked and must not be committed. The controller must re-capture with --force and audit all sources before committing fixtures. Existing Clien details require re-capture to obtain distinct articles. Audit shares discovery rules with masking and cannot identify arbitrary personal information outside known structures. Real fixtures were investigated only in memory and left unchanged.

## Follow-up: 14 findings after controller re-capture

Status: fixed in code; controller re-capture is still required. This section supersedes the earlier capture counts above. No network requests, fixture writes, or git writes were performed. Real data was inspected locally in memory; only counts and structural descriptions are reported.

Root cause: `discover_html` passed UTF-8 bytes to Selectolax with encoding detection enabled, although the response had already been decoded using its recorded EUC-KR encoding. The retained HTML charset declaration made Selectolax interpret those UTF-8 bytes as EUC-KR. Consequently, discovered names differed from the original strings and substitution missed them. The same conversion corrupted generated placeholders during audit, producing false positives. Disable encoding detection for these explicitly UTF-8 parser bytes. Original response encoding, HTML markup, and substitution behavior remain preserved.

Breakdown of the original 14 distinct name findings:

| Classification | Structure | Occurrences | Distinct findings |
| --- | --- | ---: | ---: |
| Real authors; fixed by code, require re-capture | `list.html`: `.content .desc > span:nth-child(2)` | 11 | 10 |
| Placeholder false positives | `list.html`: same search-author selector; `detail-1.html`, `detail-2.html`, `detail-3.html`: `.topTitle-name .baseList-name` | 5 (2 search, 3 detail) | 4 across files |

All three detail-author blocks already contain generated placeholders. The search page has 13 selected author spans: 11 unmasked occurrences and two placeholders. The two classifications have no overlapping distinct findings. These false positives are corrupted placeholders in author structures, not board names or site labels. Board labels in the first search-description span remain outside the author selector. Neither HTML entities, nonbreaking spaces, percent encoding, nor JavaScript escapes explain these 14 findings; correctly decoding the parser input makes all selected author strings match the original page text.

Synthetic tests were added before the production change. Both short `meta charset` and `http-equiv` EUC-KR declarations reproduce missed search/post authors through the recorder save path. A separate audit regression reproduces rejected placeholders and verifies that a real synthetic author is still reported. Initial result: 3 failures, 30 passes, pytest rc=1. After the fix, the required command was run:

    backend/.venv/bin/python -m pytest -q backend/tests/scripts; echo rc=$?

Result: 33 passed; pytest rc=0. One existing Pydantic deprecation warning.

Read-only audit of the unchanged Ppomppu directory now returns `{"name": 10}`, audit rc=1. A shared-map, in-memory discovery/substitution/re-discovery check over all four HTML files leaves zero known identity findings, and each result remains encodable as EUC-KR with the recorder's surrogate handling. No results were written to fixtures.

Files changed in this follow-up:
- `scripts/capture_http_fixture.py`
- `backend/tests/scripts/test_capture_masking.py`
- `docs/development/dcx2-stage0-2/reports/T15-capture-masking-fix.md`

Concerns: the 10 distinct real search-author names remain in the on-disk fixtures until the controller re-captures with `--force`; run the audit again afterward. No `--remask` option was added. Audit still shares discovery with masking and covers recognized identity structures, not arbitrary prose. Fresh capture results have not been verified because network capture was explicitly excluded.
