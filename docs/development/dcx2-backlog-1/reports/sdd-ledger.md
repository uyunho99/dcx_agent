# SDD ledger — plan: docs/development/dcx2-backlog-1/03-plan.md
Base: ec6909e (baseline: backend 1279 passed, vitest 242, lint ok)
Wave 1 (parallel, file-disjoint): T1 T2 T4 T5 T6 T7 T8 T9 T10 T11. Wave 2: T3 after T1+T2.
Reports in: T1 T2 T5 T7 T8 T10. T3 dispatched (wave 2). Ruling: T3 may also edit backend/app/routers/keywords_v2.py to add refresh query param (plan omitted the router; no other task owns it) — cost if wrong: none, single param.
Ruling: T4 may also edit frontend/src/app/pipeline/keywords/page.tsx (R3 button disable + polling) and frontend/src/lib/api/keywords.ts (refresh=true) — plan ownership omitted them, no other task owns them — cost if wrong: none. T4 re-dispatched fresh (first run stopped to ask after 28s).
T9 measured: 310k warm 0.284s (pass, no code change), cold first call 14.77s — flag in review/UAT (AC-06 targets warm only).
Ruling: T3 GET path in keywords_v2.py applies coverage_status() so stale loading (>2min) reads unavailable — required by plan E3 — cost if wrong: none. T3 finish dispatched. T4 COMPLETE.
Controller check: full suite 1361 passed / vitest 274 / lint / build ok, BUT 5 tests in tests/keywords/test_final_w1.py made real HTTPS calls to Naver autocomplete (AC-14 violation). Added T12-netfix (conftest autouse fake autocomplete + external-connect guard), dispatched.
Wave committed ec6909e282ac5a7065995acd414d27bb55132c81..e74ace1 (backend 1370 + net guard 0 hits, vitest 274, lint, build).
Review display (T10/T11): Needs fixes — AC-08 signals missing (crawl completion not in payload unless step synced; labeling.status=done never written; clusters not in payload).
Review coverage (T1-T4,T12): Needs fixes — I1 R2 re-commit returns stale saved coverage (no recompute from saved humanQueries; affects searchad too); I2 2-min stale window includes LLM axis classification.
Fix round 1 dispatched in 3 parallel file-disjoint jobs: fix1-coverage.md, fix1-stability.md, fix1-display.md. Ruling: cold index batching done now (reviewer: 10s+ single write txn can cause 'database is locked' for submits) — cost if wrong: small code change.
Fix round 1 committed d7cb46d(cov) 0a3ba12(stab) 1b64004(disp); backend 1395 (0 net), vitest 285, lint, build. Perf: index 0.99s batched; cold estimate 11.7s (in-process cache) -> backlog candidate.
Fix1 re-review Approved (17/17). Fix2 dispatched: completion fail-soft + source-aware failure copy. Parked minors → backlog: interrupted classification shown connected (m6 missing); labeling.status done not reset on same-version rejudge; stale false completion until reload; release/refresh race (pre-existing); cold estimate 11.7s after restart.
Review phase: 5 findings → retry. R-207. rfix-coverage.md + rfix-completion.md dispatched.
Review-phase fixes committed 63d99dd,698dee3; backend 1430 (0 net), vitest 288.
Rfix re-review: Needs fixes (I1 stage6 never cleared → clustersDone false forever in restarted versions; minors M1-M6). Round 2 dispatched: rfix2-cluster.md, rfix2-coverage.md.
Round-2 fixes committed; backend 1447 (0 net), vitest 288.
Rfix2 re-review Approved. Parked minors: clustering.py session['version'] KeyError risk; clusters_done no version compare; _restart keeps inherited clustering field.
