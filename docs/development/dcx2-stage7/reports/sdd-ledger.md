# SDD ledger — plan: docs/development/dcx2-stage7/03-plan.md

BASE for T1-T3: 69dcf91
Ruling: T1/T2/T3 dispatched in parallel — disjoint file ownership per plan table — cost if wrong: controller merges overlapping edits
Ruling (T2): Voyage document requests keep no input_type (stored stage-3 vectors were made without it); only query sends input_type=query — why: avoid mixing document embedding variants — cost if wrong: re-embed later with document type
Task T3: complete — 799903a (controller self-review: report + scope ok)
Task T1: fix round 1 — remove domain words 가격/구매/구입/추천/사진 from STOPWORDS (Important)
Task T2: redispatched with D-256 ruling (first run asked a question, no changes)
Task T2: complete — c690041
BASE for T4: c690041 — T4 dispatched (parallel with T1 fix round 1, disjoint files)
Task T1: complete — ed15300 (fix round 1 addressed domain words)
Task T4: complete — 5d27e94
T5, T6, T8 dispatched in parallel (BASE 5d27e94, disjoint files)
Task T5: complete
Task T6: complete
Task T8: fix round 1 — D-257 DPP short fill
Task T8: complete — 1de0b35 (fix round 1 D-257)
T7 dispatched (BASE e8eb538); T13 dispatched (BASE 1de0b35, frontend only, contract from plan)
Task T7: complete
T9 dispatched
Task T13: complete (code-point offset fix carried into T14, D-258)
T14, T15 dispatched in parallel (BASE 0e328ba, disjoint frontend files)
Task T9: complete
Task T15: complete
T10 dispatched
Session restart: T10 left nothing → redispatched + tests/evidence/__init__ collision fix; T14 partial → continue dispatched
Task T14: complete
Task T10: complete (+ tests/evidence/__init__ collision fix; full suite 1880)
T11 dispatched
Task T11: complete (controller full suite 1922 passed)
T12 dispatched
Task T12: complete (backend 1944, frontend 522)
T16 dispatched
Task T16: complete (full suite 1946)
All tasks complete → final review
Final review: opus Ready-with-fixes (C1, I1-I8, M11) + Codex (I7, M2) → backend + frontend fix dispatched (D-259..D-266)
Final fix wave committed (backend 1980, frontend 539, lint, build ok) → scoped re-review dispatched
Browser QA round 1 (8320/3320): QA-infra fake responses mismatch (D-267) + live tag-call counter (D-268) → QA fix 1 dispatched
Re-review 1: 28/29 addressed (I3 partial → D-268), new N1 Important → fix round 2 dispatched; QA fix 1 committed 937fc01 (controller full suite 1987)
QA round 2 (8320/3320): E2 progress+live tag calls, E3 cards, E4 exclusion message, E7 labeling banner PASS; E-F1..F4 → QA fix 2 dispatched
QA round 2 extra: E8 restart-from-7 PASS (cache hits 1607, tag calls 0), E9 legacy PASS; E-F5 navigation after version creation goes to personas; E-F6 stage7 compare renders FileComparison (Invalid Date)
QA-L2 (real LLM, 3 Contexts, tag cache moved aside): tag_calls 40, untagged 120, evidence 0, contexts marked done → E-F7 real-LLM tag responses all rejected (diagnose) + E-F8 all-untagged Context must not be done. First L2 attempt reused fake tag cache (cache key lacks model — UAT note)
QA fix 2 committed 60a0647; QA fix 3 dispatched (E-F5..F9, E6 hook, real-LLM diagnosis) D-269..D-272
