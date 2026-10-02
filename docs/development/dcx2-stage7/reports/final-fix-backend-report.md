# Stage 7 final review fix wave — backend

Scope: backend implementation/tests and this report only. No frontend edits, subagents, staging, or commits. Controller decisions D-259–D-266 and both final reviews were read before changes.

## Verification method

Regression tests were added before the corresponding production changes. The first regression run reproduced 25 failures; the assembly interleaving regression was corrected to interleave only once, then independently reproduced its failure. Subsequent red tests reproduced missing Persona SQLite quality, Persona embedding failure propagation, missing prompt metadata, stale package reads, refresh after a prompt upgrade, and absent Context queries. Follow-up coverage checks the shared publication lock and exact missing-pair batching.

New regressions live in `backend/tests/evidence/test_final_review.py`. Existing tests were updated only where their old expected contracts explicitly conflict with the rulings (API additions, retained shared cache rows, actual Persona quality, bounded novelty excerpts, fallback Persona queries, and cleared all-only novelty).

## Per-item results

| Review item | Regression test(s) | Fix | Result |
| --- | --- | --- | --- |
| C1 / D-259 | `test_d259_required_quality_keys`, `test_d259_persona_quality_from_sqlite`; real stage-6 assembly test | Required, nullable typed quality models: Context cohesion/boundary/stability/npmi and Persona cohesion/boundary/stability_ari. Assembly fills every key. Stage 6 persists measured Persona cohesion/boundary/L2 stability in SQLite; existing stores migrate additively. Old stage-6 report stability remains a fallback; unavailable observations stay null. | PASS |
| I2 / D-260 | `test_d260_first_segment_not_stale` (missing/none); existing rerun and restart tests | Segment reset marks evidence stale only if evidence has a non-none status. Restart-from-7 removes evidence and sets status none. | PASS |
| I1, Codex 3/4 / D-261 | `test_d261_statement_after_done_and_edit`, `test_d261_failed_judgment_stays_changed`, `test_d261_only_new_statement_pairs_and_old_fingerprint_retained` | Judgment keys qualify KI IDs with a SHA-256 content fingerprint. Context snapshots include fingerprints; edits are visible even when IDs stay constant. Refresh judges only missing cached-document/statement pairs in batches of eight, outside the session publication lock, and rechecks generation before publishing. Failed/missing judgments and concurrent KI changes retain knownChanged. Existing and previous-content cache rows survive. | PASS |
| Codex 7 / D-262 | `test_d262_invalid_query_embeddings` (zero/missing/nonfinite), `test_d262_persona_embedding_failure_marks_contexts_retryable`, `test_d262_missing_context_queries_retryable` | Validate embedding completeness, shape, finiteness and nonzero norms. Invalid Context queries fail with a retryable reason. Persona-query embedding failure marks its pending Contexts failed, keeps their checkpoints retryable, and yields partial instead of empty done. | PASS |
| Codex 2/6 / D-263 | `test_d263_prompt_generation_pinned_then_invalidated`, `test_d263_generation_metadata_complete`, `test_d263_segment_generation_refuses_publication`, `test_d263_worker_launch_conflict_atomic` (both directions), `test_d263_package_read_rejects_changed_segment`, `test_d263_refresh_prompt_upgrade_refused` | Each generation captures segment run, prepKey/preparation and training references, and tag/query/novelty/dims prompt hashes. Reads use the captured tag cache and prepared inputs. Resume conservatively resets evidence checkpoints when captured inputs differ. Publication checks the captured segment generation. The worker database transaction rejects segment/evidence conflicts before spawning. Prompt upgrades require resume before refresh can write judgments. | PASS |
| Codex 1 | `test_codex1_assembly_preserves_live_context_state`, `test_codex1_publication_owns_session_lock` | Context completion and refresh publication use the same session lock plus generation checks. Assembly merges only its undifferentiated counter into the live SQLite row; it cannot overwrite status, coverage, or unrelated counters from a stale snapshot. Worker call accounting merges deltas with concurrent refresh calls. | PASS |
| I8 / D-264 | `test_d264_persona_violation_isolated`; existing per-Context fallback tests | Persona violations produce Persona-only Desire/Goal fallback queries. Valid Context queries remain intact; invalid Contexts alone get fallback. Report includes persona_query_fail. | PASS |
| D-265 / M7 | `test_d265_deleted_ki_cache_preserved`; updated mid-run deletion test | Removed production deletion of shared KI cache rows. Projection uses only current KI IDs/content fingerprints, preserving other versions. | PASS |
| D-266 / I3–I5 / M5 | `test_d266_quote_source_and_novelty`, `test_d266_tag_calls`; API and integration contracts | stage_7.json includes tag_calls and retains relevant_false. Status exposes live tagCalls. Shared GET/refresh card serialization provides quoteSource `{field, idx, text}` paired with Python code-point offsets and noveltyShown for high/very_high only. | PASS |
| I6 | `test_i6_refresh_clears_all_only_novelty`; updated end-to-end refresh check | Refresh rewrites all-tab novelty from surviving new-tab membership; all-only rows become null. Package support items take novelty only from new-tab rows. | PASS |
| I7 | `test_i7_flag_removed_and_restart_empty`, `test_i7_badge_existing_flag_readable` | Candidate flags are set or removed from current results, cleared on restart-from-7, and recomputed by scoped refresh. An existing flag remains readable through the Context endpoint even without a done evidence row. | PASS |
| M1 | `test_m1_act_mismatch` | Report counts relevant tagged documents whose Act probability threshold and extracted activity_response presence disagree. | PASS |
| M2 | `test_m2_counter_mean_uses_candidate_pool` | API, refresh and package use the same candidate-pool polarity mean helper. | PASS |
| M3 | `test_m3_verified_quote_after_unverified` | Locate every returned quote against originals; select the first verified quote, falling back to the first only when none verify. | PASS |
| M4 | `test_m4_novelty_excerpts`; updated novelty payload test | Both selected rows and Core representatives use tagging excerpt limits (1,500 body characters, 10 comments × 300 characters), retaining quotes/pain/unmet need while dropping internal row/cache payloads. | PASS |
| M8 | `test_m8_refresh_does_not_load_session` | Refresh avoids the full-session loader and assembly. It fetches candidate document rows and candidate/handed-document vectors only, updates the target Context flag/report, and marks the package dirty for a generation-checked rebuild on GET /package or normal final publication. | PASS |
| M9 | `test_m9_doc_ki_not_llm_judged`; tagging prompt test | Only statement KIs enter tagging/pair-judgment prompts. Doc KIs continue to be excluded by handed-document ID/cosine without LLM pair judgments. | PASS |

## Validation

- First broad evidence/segment/context/worker pass: 683 passed, 12 failed, 2 deselected; all 12 failures were old contract expectations, subsequently corrected and checked.
- Evidence-only pass after contract updates: 244 passed, 1 failed, 1 deselected; remaining assertion expected all-tab novelty to stay unchanged after refresh, now corrected under I6.
- Final regression plus end-to-end integration check: **36 passed, 2 warnings in 31.19s**.
- Full backend suite, invoked once after the final implementation changes: `backend/.venv/bin/python -m pytest backend/tests -q`
  - **1980 passed, 3 deselected, 2 warnings in 343.95s (0:05:43)**.
  - Warnings: existing Pydantic class-config deprecation and joblib physical-core detection fallback in the sandbox.
- Final status: all requested backend review fixes implemented; full suite green.
- `git diff --check -- backend`: clean.

## Implementation choices and concerns

- Input/prompt mismatches conservatively invalidate the entire evidence generation rather than attempting dependency-specific partial reuse. Tag caches remain reusable when their prompt/preparation identity matches.
- Refresh is synchronous for newly added/edited statements; knownChanged stays true during its missing-pair calls and after provider failures. A retry calls only still-missing pairs. Doc-only changes make no LLM calls.
- Full package assembly is deferred after refresh. Consumers should request GET /package before consuming a refreshed package; a direct read of package.json can see the preceding artifact until the dirty marker is reconciled. GET /package and normal worker finalization rebuild it under the session lock.
- Targeted refresh bounds materialized documents/vectors. Prepared originals still use the existing JSONL scan, and tag probability enrichment uses the existing export reader. No production-scale session latency benchmark or live-provider run was performed in this fix wave.
- Existing stage-6 runs without measured Persona quality retain null unavailable values; newly computed stage-6 runs persist actual Persona measurements. Context boundary/stability remain null when stage 6 has no corresponding observation.
- Frontend-only review items are left to the parallel frontend worker. The backend delivers the D-266 field names without aliases or removal of relevant_false.
