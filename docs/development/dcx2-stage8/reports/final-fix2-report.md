# DCX 2.0 Stage 8 — Final fix ROUND 2

- Branch: `feature/dcx2-stage8`.
- Reviewed `final-rereview1.md`, `final-review1.md`, `codex-branch-review1.md`, and D-312–D-316.
- Scope: N1–N10, C1/I1 remaining work, M6/M7/M8/M14. No subagents, staging, commits, or Next build.

## TDD evidence

Before production changes, the new backend regression file produced **11 failures** and the selected frontend regression files produced **16 failures / 40 passes**. These covered every requested fix; existing successful coverage remained in place. N9's additional different-run regression was also run red (1 failed / 2 passed) before tightening supervisor-run matching.

After implementation, focused backend verification passed **69 tests** (`test_api.py`, `test_final_fix2.py`, `test_final_fixes.py`), and frontend verification passed **137 tests / 7 files** (persona components and shared error mapping). TypeScript `--noEmit --incremental false` passed. Existing tests that asserted the superseded behavior were updated to the corrected contracts.

## Per-item results

| Item | Regression test | Fix | Result |
| --- | --- | --- | --- |
| N1 Critical | `PersonaScreen.test.ts`: `N1 uses package=%s with none and cards not_ready`, true and false cases | Added required `PersonaStatus.package`; empty state uses `package === false` or explicit `evidence_required`. `not_ready` is no longer evidence absence. Corrected the old parameterized assertion. | Red → green. `package:true`, status `none`, cards 409 `not_ready` offers **페르소나 만들기**. |
| N2 Important | `errors.test.ts`: crawl `kind:conflict/code:no_paused_detail`; stage-eight stale/evidence/persona kinds with unknown code | Choose the first mapped code, then mapped kind; added explicit Korean stage-eight prerequisite mappings. | Red → green. Existing crawl Korean copy preserved; stage-eight messages localized. |
| N3 Important | `test_n3_n10_real_exception_publishes_korean_reason` (unknown provider exception, real connection exception, stale Source); existing dimension mismatch regression | Pipeline publishes generic failure, stale guidance, or `LLM_REASON`. Same-run pipeline Korean reason wins; supervisor exception class names never become UI reasons. Legacy non-Korean reasons use Korean fallback. | Red → green. Actual exception paths exercised, including the raised exception's class name in supervisor output. |
| N4 Important | `test_n4_only_changed_insight_concept_is_outdated` uses real chat and metric recomputation | Both read-time and write-time concept checks compare only `id`, `title`, `pain_point`, `context_ids`. | Red → green. Editing I1 Contexts invalidates only I1's concept, while aggregate/rank changes leave I2/I3 concepts valid. |
| C1 partial | Backend `test_c1_status_identifies_package_older_than_confirmations`; frontend old-package guidance, cancellation, and accepted fresh launch | Status exposes `evidence_required` for package/segment confirmation mismatch. UI directs users to evidence with the exact requested copy. Stale fresh action is labeled **페르소나 다시 만들기** and requires the exact deletion confirmation. | Red → green. Cancel launches nothing; accept sends `{fresh:true}`; old package does not offer regeneration. |
| I1 partial | N1 fetcher tests plus status/cards `evidence_required` regressions | Uses the backend package flag, with explicit typed API errors for races. Removed message matching and the `not_ready` workaround. | Red → green. Package presence is authoritative. |
| M6 | `M6 uses naturally sorted backend legend presentation`; updated component fixtures model backend legend | Natural numeric cluster ordering (`CL2` before `CL10`); use backend `shape`, Persona `tone`, `persona_name`, and `cluster_label`. Narrowed the legend type. | Red → green. Backend presentation metadata survives display sorting. |
| M7 | `M7 legend toggles point visibility and keeps the table complete`; cluster/Persona chip component tests | Maintain hidden Persona IDs and filter SVG points. `aria-pressed` represents visibility. Table data is not filtered. | Red → green. Chips turn points off and on; the Context table remains complete. |
| M8 | Boundary confidence tests at 0.70, 0.40, 0.39 and ok/review/blocked summaries | Card header shows **신뢰도** and **처방 · 제약** with ✓ / ⚠ / ✕. | Red → green. Rules documented below. |
| M14 | `M14 tabs support arrows, Home and End with roving focus` | Left/Right wrap, Home/End jump, selection and focus move together; selected tab alone has `tabIndex=0`. | Red → green. All four navigation keys verified. |
| N5 Minor | `test_n5_confirm_keeps_hidden_ids` switches revisions, confirms, then returns | Persist `(old confirmed IDs − current revision IDs) ∪ new IDs`; return only current visible selection. | Red → green. Hidden I4 survives while visible I2/I3 changes are applied. |
| N6 Minor | `N6 retains decimal metrics greater than one in CCM and prescription` | Generic numeric values use `formatMetric`; only known count/index fields use integer formatting. | Red → green. ODI and prescription metric `1.37` remain `1.37`. |
| N7 Minor | `test_n7_busy_persona_rejects_without_waiting_for_lock`, edit and revert | Check writable version and `require_persona` before waiting on the inference lock; retain the guarded check inside. | Red → green. Requests return 409 `persona_required` within the test deadline while the lock is held. |
| N8 Minor | `test_n8_missing_package_completion_is_false_and_unchanged_poll_is_cached` | Explicitly catch `PackageMissing`. Bound completion caching to 128 source fingerprints (version root, cards, package, segment SQLite, WAL/journal; inode/size/nanosecond timestamps). Hash package only once per cache miss. | Red → green. Unchanged polling performs one expensive check; segment mutation invalidates it; missing package returns false. Existing `_completion` broad exception guard already prevented propagation in this checkout. |
| N9 Minor | `test_n9_old_terminal_worker_does_not_override_reset_or_chat` now exercises real fresh pipeline and successful chat; different-run regression | Ignore terminal supervisor history without a matching pipeline run; retain active launch discovery; completed pipeline/chat state overrides old same-run failure. | Red → green. Fresh cards show idle insights; successful chat clears the failure banner; a different old terminal run is ignored. |
| N10 Minor | Source variant of `test_n3_n10_real_exception_publishes_korean_reason` | Construct `Source` inside the pipeline try block after publishing running state. | Red → green. Upstream changed while queued publishes failed with Korean stale guidance and its run ID. |

## Display rules

- **신뢰도**: equal-weight arithmetic mean of the card's finite Context `traceable_support` ratios (top-level enriched card row, with nested card fallback). No support values means zero. **상 ≥ 0.7**, **중 ≥ 0.4**, otherwise **하**. This summarizes traceable support, not LLM certainty.
- **처방 · 제약**: blocked prescription or any `violates` → **✕ blocked**; otherwise any `review` → **⚠ review**; otherwise an available prescription → **✓ ok**. No prescription shows **—**.
- Numeric metrics use two decimals; explicit count/index fields use integer/count formatting.
- `status.package` reports presence; `status.evidence_required` separately reports whether evidence must be rerun because the package no longer matches stage-six confirmations.

## Final full verification

Each requested full command was run **once**, after the fixes:

| Command | Result |
| --- | --- |
| `backend/.venv/bin/python -m pytest backend/tests -q` | **2005 passed, 2 deselected, 2 warnings**, exit 0; 284.56 seconds |
| `npm --prefix frontend test` | **583 passed / 58 files**, exit 0 |
| `npm --prefix frontend run lint` | **Passed**, exit 0; no lint diagnostics |

Additional checks: `tsc --noEmit --incremental false` and `git diff --check` passed. Backend warnings were the existing Pydantic class-based config deprecation and joblib physical-core detection falling back to logical cores. Raw execution logs are `/tmp/fix2-full-backend.log`, `/tmp/fix2-full-frontend.log`, and `/tmp/fix2-full-lint.log`.

## Concerns / remaining scope

D-316's deferred stage-eight restart selector and derive-prompt size work remain deferred. No live LLM calls or browser end-to-end run were performed; regression coverage uses offline fixtures and actual local source/store/pipeline paths. No Next build was run, as requested.
