# T8 — completed

Implemented only the T8-owned modules, prompt, tests, and this report. No git add/commit; no subagents. Other workers' files were not modified.

## Implementation

- `insights.py`: `derive(sid, version, *, run_task=None, embedder)` reads cards through PersonaStore, package Context metrics, and session Known Insights. Calls `insight.derive` using the registry and a Pydantic output schema. Accepts 3–8 insights; invalid count or Context/ID membership regenerates once, then raises InsightError with exactly `인사이트를 만들지 못했습니다. 다시 시도하세요.`. Extra response fields are ignored, including all model-provided metrics. Backend/schema failure raises the same error; registry owns schema retries.
- `radar.py`: embeds the verbatim RADAR_AXES sentences with `input_type='query'` when supported, otherwise calls `embed(texts)`. Signature inspection avoids masking an internal TypeError by retrying. Reads version-local `segment/segment.sqlite` Context centroid float32 BLOBs in read-only mode. Computes absolute cosine for each Context, then document-count-weighted means. Zero vectors contribute zero; missing or invalid data fails before saving.
- `opportunity_bars(insights, odi_by_context)` returns `{bars: [{id, odi}], mean, targets}` using unweighted member Context ODI means and the mean across insights; equality qualifies for default targeting.
- Saved item fields: schema text/IDs plus `radar: {raw: {axis: value}, percentile: {axis: rank}}`, `odi`, `opportunity_mean`, `default_target`, `known_badge`. All calculated fields are inside revision snapshots; `PersonaStore.new_revision(..., by='generate', message=None)` is the only insight persistence mutation.
- `confirm(sid, version, ids)` validates IDs and writable version, replaces/deduplicates `session.insight.confirmed`, and supports clearing with `[]`. No PersonaStore mutation occurs under a session lock.
- Derivation leaves session run/status/revision orchestration to T10. Confirm changes only the confirmation selection.

## TDD evidence

1. Added test_insights.py and test_radar.py before implementation.
2. RED: the required test command failed collection with two ModuleNotFoundError errors for the unimplemented modules.
3. Implemented modules and prompt: 16 passed.
4. Refactored unused loop binding and added integration regressions for unequal document weights and preserving an existing revision after a missing centroid.
5. Final command: `backend/.venv/bin/python -m pytest backend/tests/persona/test_insights.py backend/tests/persona/test_radar.py -q`
6. Final result: **18 passed, 1 warning in 3.36s**. Warning is the existing Pydantic class-based config deprecation in app/config.py.

Coverage includes both range boundaries, below/above-range failures and successful regeneration, revision history, cards and Known input, Known badge, bars/mean/equality targets, numeric-field rejection, session confirmation/invalid ID/clear, unknown Context rejection, weighted absolute cosine, session percentile ties, embedding signature compatibility, internal embedder errors, zero vectors, SQLite float32 centroids, and missing-centroid failure atomicity. Tests use minimal cards.json and fake LLM/embedding backends; no network or keys.

## Integration conventions / concerns

The brief does not define a percentile estimator. Implemented midrank on a 0–100 scale: `100 * (count below + 0.5 * count equal) / N`; identical values share a rank, and a singleton ranks at 50. Stored insight percentiles compare all generated session insights per axis. Standalone `radar()` ranks its weighted mean against its input Context similarities; derive replaces that with the insight cohort rank.

Downstream T10/T11 should consume the documented per-item calculated fields (or reconstruct top-level radar/bars views from them). No API or worker files were changed. Actual production embedder/centroid compatibility beyond deterministic fake vectors is not exercised by these two test files.
