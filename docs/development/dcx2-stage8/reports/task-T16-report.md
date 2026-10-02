# T16 — Offline stage-eight integration

Status: complete. Full backend suite passed.

## Delivered

- Added `backend/tests/persona/test_integration.py::test_package_to_insights_offline`: shared Evidence Package session → POST persona run → real persona worker → POST insight derive → real insight worker → one concept → one real chat edit → revert to revision 1 as new revision 3.
- Uses TestClient and the production routers, worker kind registry, LLM registry/schema validation, fake persona backend, FakeEmbedder, durable stores, and session completion projection. Only process launch is replaced by synchronous worker dispatch; no pipeline, derive, concept, chat, revert, or completion implementation is mocked.
- Checks cards, map (all six zones and two stars), tree, insight bars/radar, concept persistence, chat log, original/edited/reverted history snapshots, restored computed metrics, and personaDone/insightDone transitions.
- Checks every design §5.10 report field, downstream counts after each publication, final aggregate LLM call counts, and API/report-file agreement.
- Added a QA-script entry-point test using `--seed 17 --big-persona`. The actual script writes a session that `/session/{sid}` and persona status can serve; its package has ten Contexts for the first Persona and usable centroids for every Context.
- Socket protection includes the global external-connection guard and a stricter local guard rejecting all IPv4/IPv6 `connect`/`connect_ex` attempts. The journey and QA-script test both assert zero attempts. The script executes via runpy in-process so it remains covered by that guard.

## TDD findings and fixes

1. The first integration run failed during real derive with `Missing Context centroids`. The shared fixture planted segment assignments but omitted centroids. Added deterministic 1024-dimensional FakeEmbedder centroids to `write_session_with_package`, matching the synthetic helper's embedding dimension. This also repairs the QA script's downstream inputs; production centroid validation remains unchanged.
2. The next run completed the journey but failed the report assertion: insights/concepts/chat_revisions remained `(0, 0, 0)` instead of `(3, 1, 1)`. Production only published `stage_8.json` at persona completion. Added `pipeline.refresh_report`, invoked after completed insight publication (derive, concept, chat, revert), outside the session lock. Existing report calculation is reused and its persona run identity is preserved.
3. Insight and default chat calls now use the existing persisted call counter so the report includes downstream LLM work. The integration test compares the report's entire call-count dictionary with observed fake backend calls.

Production files changed: `backend/app/persona/pipeline.py`, `insight_pipeline.py`, `chat.py`. Test/support files changed: `backend/tests/persona/test_integration.py`, `backend/tests/fixtures/evidence_package.py`.

## Validation

- Initial integration: 1 failed (missing centroids), 1 passed.
- After fixture repair: 1 failed (stale report totals), 1 passed.
- Focused persona and stage-eight version tests after production repair: 239 passed, 1 warning.
- Final integration assertions: 2 passed, 1 warning.
- `git diff --check`: passed.
- Required full suite, run once at the end: `backend/.venv/bin/python -m pytest backend/tests -q` — **1951 passed, 2 deselected, 2 warnings in 283.25s (0:04:43)**; exit code 0.
- Warnings: Pydantic class-based Config deprecation and joblib physical-core detection fallback to logical cores.

## Scope and concerns

- Worker subprocess spawning, supervisor bookkeeping/heartbeats, real provider behavior, and browser UI are outside this in-process integration test. Actual worker kind dispatch and both pipelines execute synchronously.
- QA script serving is verified with real API reads; the full mutation journey uses the same shared fixture with its default package. The big-Persona script test validates all centroid inputs but does not run that variant through the entire journey.
- Fake centroids are deterministic QA data, not embeddings of real evidence. Report call counts retain the existing logical-task counting convention; provider-internal retries are not separate counter entries.
- No frontend changes, staging, commits, or subagents.
