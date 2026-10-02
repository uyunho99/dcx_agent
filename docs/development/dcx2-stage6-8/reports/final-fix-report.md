# Stage 6 bundle 1 — final-review fix wave

Status: complete — all eleven findings fixed; final backend and frontend verification green.

Worktree: /Users/persona1/Desktop/dcx_agent-stage6-8
Branch: feature/dcx2-stage6-8

All eleven findings are addressed. Application/test edits remain inside the authorized paths; this is the explicitly requested report. No git add, commit, subagents, dependency changes, or external provider calls were used. The five explicitly deferred findings were left unchanged.

Read: design sections 3.10, 9 and 9.1; T2/T7/T8/T9/T10/T14 reports; pipeline worker argument contract. The contract remains k=None/fresh=False for checkpoint resume, and explicit k or fresh=True for a reset.

## 1. Confirmed edits survive reload as confirmed

Changes: frontend/src/components/segment/SegmentScreen.tsx:189 writes null tombstones for every confirmed ID, including bulk confirmations. Lines 148 and 113 discard null entries and discard restored edits whose fields equal a confirmed row's persisted fields. Different edits remain editable.

Tests: frontend/src/app/pipeline/clustering/page.test.ts:217 exercises edit → debounced PATCH → confirmation → merged server draft → remount, checking the confirmed badge and “6-B로 →”. Line 233 covers legacy matching edits, differing edits, and null values.

RED: initial clustering run had 3 failures / 35 passes, including both restoration regressions; the merged draft retained the edit rather than a null tombstone.
GREEN: both regressions pass in the final frontend suite. Existing post-confirmation PATCH-failure input-retention tests still pass.
Logs: /tmp/final-fix-frontend-red.log and /tmp/final-fix-frontend-full-final.log.

## 2. Korean failure reasons and original exception preservation

Changes: backend/app/segment/pipeline.py:399 persists StoreError's message and uses the exact generic Korean line for other exceptions. This repository's StoreError has no .message attribute, so its message is read with str(exc). A secondary failure publishing failed status is logged, then the original exception is re-raised. backend/app/routers/segment.py:174 gives the persisted Korean reason precedence over worker errors and does not expose exception class names. The frontend's existing reason banner is retained.

Tests: backend/tests/segment/test_final_fix.py:86 covers both exact empty-document/missing-token messages and generic failures; line 97 verifies original exception identity and logging when status publication fails. backend/tests/segment/test_api.py:372 checks reason precedence. Existing test_inputs.py:164 checks the actual missing-token condition. frontend/src/app/pipeline/clustering/page.test.ts:247 checks the Korean reason on screen.

RED: all three reason cases and original-exception preservation failed in the initial 17-failure regression run. The status API regression also failed before implementation.
GREEN: all pass in the final 71-test focused backend run and frontend suite.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-input-api-red.log, /tmp/final-fix-focused-final.log.

## 3. QA dims, granularity, and counter-context cases

Changes: backend/app/llm/fake.py:21 supports the optional segment.dims.echo.json companion fixture; its {"echo": true} marker emits one deterministic, schema-validated item per attachment title. Explicit response mappings retain precedence; other tasks retain their existing behavior. backend/tests/fixtures/llm/segment.dims.echo.json:1 enables it for the normal live fake server while retaining the static dims schema fixture.

backend/tests/fixtures/segment_synth.py:53 adds an opt-in QA layout, used by backend/tests/scripts/make_segment_qa.py:27. It retains 1,200 documents: an eight-topic Persona and nine three-topic Personas. One 16-document topic includes 짜증, 불편 and 실망; the committed KNU lexicon gives each a negative polarity. backend/app/segment/pipeline.py:354 also propagates granularity_exceeded to its Persona.

Tests: backend/tests/segment/test_final_fix.py:24 verifies optional echo behavior, dynamic attachment IDs, deterministic output, and isolation from another task. Line 164 invokes the actual QA script in a subprocess and runs the real pipeline with FakeBackend, without replacing clustering algorithms.

RED: the original QA session produced (granularity Personas, counter Contexts, dims failures) = (0, 0, 898). The echo marker and companion-fixture tests also failed before their respective implementation changes.
GREEN: real QA pipeline produced 1 granularity Persona, 1 counter Context (16 documents, mean sentiment -0.92857), and 0 dims failures. The existing QA script's 1,200-document contract still passes.
Logs: /tmp/final-fix-qa-red.log, /tmp/final-fix-echo-companion-red.log, /tmp/final-fix-qa-green.log, /tmp/final-fix-focused-final.log.

## 4. Target-scope hint

Changes: backend/app/routers/segment.py:207 adds each Persona's hint when targetScope contains nonempty content. It includes the exact “초안 힌트: 0단계 대상 선언” prefix and a plain, bounded summary of nested values. frontend/src/components/segment/PersonaLayer.tsx:35 renders the complete supplied hint without adding a second prefix.

Tests: backend/tests/segment/test_api.py:357 covers absent, empty, and nonempty scope. frontend/src/app/pipeline/clustering/page.test.ts:242 checks the declaration text and exactly one prefix.

RED: the initial API test fixture incorrectly attempted an incomplete validated ProjectContext update; it was corrected to write the version fixture directly. Running the corrected tests against the HEAD personas implementation in an isolated pytest plugin reproduced the actual missing-hint bug: 1 failed / 2 passed. The strengthened UI test then reproduced the duplicate prefix: 1 failed / 38 passed.
GREEN: all three API cases pass in the final focused backend run, and the frontend hint test passes in the final frontend run.
Logs: /tmp/final-fix-hint-corrected-red.log, /tmp/final-fix-hint-ui-red.log, /tmp/final-fix-focused-final.log, /tmp/final-fix-frontend-full-final.log.

## 5. Relevant-only input memory and compact resume

Changes: backend/app/segment/inputs.py:54 streams document/token shards and retains only relevant IDs. Line 60 builds and validates the shared noun cache incrementally, still caching every prepared document's nouns, retaining only relevant noun rows and one bounded output batch. Matching prepared docs/tokens streams preserve the noun-only fast path; manifest-last publication and dedicated locking remain.

Line 142 streams the vector index too, retaining only selected records and per-shard sizes, avoiding the shared reader's collection-wide index dictionary. Line 123 rebuilds input from immutable preparation shards and the noun cache. backend/app/segment/pipeline.py:300 writes only ids/report to input.json and uses memory-mapped vectors on resume.

Tests: backend/tests/segment/test_inputs.py:218 fixes the relevant set at two documents and expands irrelevant content from 200 to 4,000 documents with 8,000-character bodies; it asserts large_peak < small_peak * 3 + 2 MB, checks retained IDs, and checks that the noun cache still covers all documents. Line 272 forbids the collection-wide vector index reader. backend/tests/segment/test_final_fix.py:115 checks compact checkpoint fields and resumes while forbidding L1 recomputation. Existing cache corruption, interrupted publication, cross-version reuse, and input equivalence tests remain green.

RED: peak traced memory grew from 2,151,426 to 39,612,136 bytes in the original loader, violating the bound. The old input checkpoint contained docs/tokens/nouns, and the vector-index regression failed on the whole-collection reader.
GREEN: all memory, cache, vector and resume regressions pass in the final focused run.
Logs: /tmp/final-fix-input-api-red.log, /tmp/final-fix-backend-red.log, /tmp/final-fix-vectors-red.log, /tmp/final-fix-focused-final.log.

## 6. Useful progress detail and noun-build stop

Changes: backend/app/segment/pipeline.py:257 publishes numeric persona/personas counts during L3 and drafts, retaining that detail across nested LLM pulses. Noun loading publishes docs/total and checks stop on every callback; persisted progress updates are throttled to avoid per-document session writes. backend/app/segment/inputs.py:60 pulses during first builds and cache reads. backend/app/routers/segment.py:174 exposes detail; frontend/src/lib/types.ts:199 types it; SegmentScreen.tsx:294 announces Persona or document counts in the short aria-live line.

Tests: backend/tests/segment/test_final_fix.py:127 checks numeric L3/draft counts; line 220 checks a real pipeline stop during initial noun loading without completing the load checkpoint. test_inputs.py:251 stops a mixed-POS noun build and verifies no completed manifest is published, then successfully rebuilds. test_api.py:372 checks detail. Frontend tests at lines 238 and 247 check “L3 · Context 3/12 Persona” and document counts. The prior heartbeat coverage test was updated from Persona IDs to numeric positions, preserving its coverage-of-every-Persona assertion.

RED: numeric heartbeat, noun callback and status detail tests failed before changes; the frontend announced only percentage rather than Persona counts.
GREEN: all pass in the final focused backend and frontend runs.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-input-api-red.log, /tmp/final-fix-frontend-red.log, /tmp/final-fix-focused-final.log.

## 7. LLM outage interruption and checkpoint resume

Changes: backend/app/segment/pipeline.py:111 tracks provider outcomes separately from cached draft responses. At line 381, if every provider call in dims or drafts fails with backend/timeout, the worker exits as interrupted with the exact Korean connection/quota reason. The unfinished step is not checkpointed. Successful caches and completed L1–L3 artifacts remain reusable; the next run clears the old reason. The dedicated BaseException exit follows the existing worker's interrupted-state contract without modifying the worker module. Partial provider success keeps the existing per-item draft_failed behavior.

Tests: backend/tests/segment/test_final_fix.py:138 covers both steps × both error kinds, recovered drafts, unchanged assignments and confirmation timestamps, and forbidden L1/L2/L3 recomputation. Line 186 proves a cached success cannot mask an outage in all new calls. Line 203 executes the real worker and checks its durable interrupted state. Existing router {}-resume tests, partial failures and successful-call replay tests remain green.

RED: all four initial outage cases incorrectly finished in review. The additional cached-success scenario initially failed to interrupt (1 failed / 2 other checks passed).
GREEN: all outage, worker and resume cases pass in the final focused run. The dims resume comparison intentionally excludes combo_rarity, which must update after successful dims recovery; layer assignments and geometry remain compared.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-outage-extra-red.log, /tmp/final-fix-focused-final.log.

## 8. Nullable votes_json

Changes: backend/app/model/export.py:20 parses label['votes_json'] or '{}', preserving zero entropy when agreement votes are absent.

Test: backend/tests/segment/test_final_fix.py:20 supplies an agreed label with NULL votes_json.
RED: TypeError from json.loads(None).
GREEN: passes in focused and targeted verification; existing model tests pass.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-focused-final.log, /tmp/final-fix-targeted.log.

## 9. Plain dims prompt and bounded attachments

Changes: backend/app/segment/prompts/dims.v1.md:1 uses “문서에서 관측된 항목”; line 11 says “추출만 하고 세거나 요약하지 마세요” and removes the analysis-operation terminology. backend/app/segment/dims.py:198 caps body at 2,000 characters and the first ten comments at 300 characters each, tolerating non-dict comments. Prompt-hashed caches naturally invalidate.

Tests: backend/tests/segment/test_final_fix.py:37 covers long body/comments, excess comments and a string comment; line 47 checks the prompt wording.
RED: string comments caused AttributeError and the prompt check failed.
GREEN: both pass; existing dims schema, cache and extraction tests pass in the targeted suite.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-focused-final.log, /tmp/final-fix-targeted.log.

## 10. Bounded representatives and plain draft wording

Changes: backend/app/segment/pipeline.py:197 caps stored representative text at 300 characters. backend/app/segment/drafts.py:64 independently caps representatives in prompt evidence. backend/app/routers/segment.py:136 caps API representatives even for older stored rows. persona_draft.v1.md:2 uses “자주 함께 나온 단어”; context_draft.v1.md:2 uses “자주 나온 단어” and “자주 나온 제약”. The cluster prompt already used plain wording and required no edit.

Tests: backend/tests/segment/test_final_fix.py:57 and :62 check persisted/prompt text; :47 checks wording. backend/tests/segment/test_api.py:383 checks both Cluster and Persona legacy API rows.
RED: long representatives failed both initial tests; legacy API rows subsequently reproduced two failures before adding projection caps.
GREEN: all pass in final focused verification; existing draft tests pass.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-api-reps-red.log, /tmp/final-fix-focused-final.log.

## 11. SQLite WAL and one-time schema initialization

Changes: backend/app/segment/store.py:78 enables WAL. user_version gates schema creation and the legacy Persona flags migration, so reopening for GET does not execute CREATE/ALTER statements.

Test: backend/tests/segment/test_final_fix.py:69 checks WAL, a nonzero user_version, and traces SQL on reopen to prohibit repeated DDL. Existing store transactions, version isolation and legacy migration tests remain green.
RED: the database reported journal_mode=delete.
GREEN: passes in focused verification; all existing segment store tests pass in the targeted run.
Logs: /tmp/final-fix-backend-red.log, /tmp/final-fix-focused-final.log, /tmp/final-fix-targeted.log.

## Verification

- Initial backend regression file: 17 failed, demonstrating the requested behavior gaps before implementation.
- Initial frontend clustering tests: 3 failed / 35 passed. Additional hint-prefix RED: 1 failed / 38 passed.
- Required targeted command: backend/.venv/bin/python -m pytest backend/tests/segment backend/tests/model backend/tests/llm -q — 303 passed, 1 deselected, 2 warnings in 141.66 seconds. This preceded the final cached-outage and legacy representative refinements.
- Final focused backend command: backend/.venv/bin/python -m pytest backend/tests/segment/test_final_fix.py backend/tests/segment/test_api.py backend/tests/segment/test_inputs.py -q — 71 passed, 2 warnings in 86.52 seconds, including those refinements.
- Full backend command (executed once): backend/.venv/bin/python -m pytest backend/tests -q — 1,688 passed, 2 deselected, 2 existing warnings in 278.29 seconds (exit 0). Log: /tmp/final-fix-backend-full.log.
- Final frontend command: npm --prefix frontend test — 51 files / 428 tests passed (exit 0). Log: /tmp/final-fix-frontend-full-final.log.
- Final lint command: npm --prefix frontend run lint — passed, no lint warnings (exit 0). Log: /tmp/final-fix-lint-final.log.
- Final build command: npm --prefix frontend run build -- --webpack — passed: compilation, TypeScript and 14/14 static pages (exit 0). Log: /tmp/final-fix-build-final.log.
- git diff --check — passed after final application/test changes.

## Concerns and limits

No known implementation blocker. Tests use offline providers, with external network access prohibited by the existing test guard.

The memory regression proves bounded retained memory under a growing irrelevant collection and prohibits collection-wide vector-index materialization; it is not a million-document production stress benchmark. The QA integration runs the actual script and pipeline, but no manual browser/screen-reader visual QA was performed.

Expected existing warnings are Pydantic class-based configuration deprecation, joblib physical-core detection fallback, and Node DEP0205. No default Turbopack build was attempted; webpack is the requested verification path.
