**Verdict: Approved.** All 13 items are fixed. I found one Important issue: the new C4 `trainable` count makes every 5-second overview poll re-read all prepared data. It can be fixed as a follow-up, but it should be fixed before real-scale runs.

This was a read-only review of `e16c5ce..eaf81a6`. I read the changed sources and did not run any tests. I relied on your verification at `eaf81a6`.

## Per-item verdicts

- **C1: Addressed.** `backend/app/label/audit.py:139-140` recalculates the grade and treats an audit as unchanged only when both tags and grade match. `backend/app/label/route.py:261` now saves the recalculated grade when a model result is confirmed.
- **C2: Addressed.** `backend/app/label/gpt.py:128-131` hashes the full prompt into the run ID. That prompt contains the prepared documents sorted by ID (`gpt.py:87`).
  - Existing caches are not needlessly invalidated. The vote cache key did not change, so votes already saved are kept.
  - The only cost is that a Codex batch that was mid-run before this change runs once more under a new ID.
- **C3: Addressed.** `backend/app/prep/guards.py:13` checks `control.phase_state(...) == 'done'`, which is the real crawl completion signal (`crawl/control.py:484`, `report.can_finalize`). The check runs in:
  - `/prep/run` (`routers/prep.py:95`), before both starting and reusing;
  - the legacy `/preprocess` route (`routers/preprocessing.py:18-23`) and service (`services/preprocessing.py:129-130`);
  - the worker at start and at publication (`prep/pipeline.py:132-135`, `:152`).
  - Reuse also requires `collectionFinalized` (`routers/prep.py:102`).
  - Stage 0-2 legacy sessions are unaffected because the check only applies when `schemaVersion == 2`. The one stage 0-2 test change (`tests/test_integration_stage0_2.py:394`) is an expected error-message update.
- **C4: Addressed.** The backend sends `overview.trainable` (`label/overview.py:167`), using the same selection rule as training (`model/dataset.py:4`, used by `training_v2.py:96-97`).
  - The frontend field name matches: `trainingView.ts:40` reads `overview?.trainable ?? overview?.accepted`, and `types.ts:142` declares it.
- **C5: Addressed.** `backend/app/label/jev.py:205-245` adds a fake Jev client that makes no HTTP calls, and the factory picks it when `JEV_BACKEND=fake`. Both `judge.py:12/112` and `monitor.py:14/87` now go through that factory.
- **C6: Addressed.**
  - Each export goes to a fresh folder, `classified/{sid}/{v}/gen-{uuid}/` (`model/export.py:74-80`). Every file is written atomically and flushed to disk, and the folders are flushed too (`:83-89`). Only then is the pointer switched under the session lock (`:92`).
  - Search and clustering still pass validation: the pointer is `…/gen-x/relevant.jsonl`, so the file is still named `relevant.jsonl` and sits under `classified/{sid}` (`known/filter.py:29-33`). No old exports are ever deleted.
- **C7: Addressed.** `QueueCard.tsx:57-61` shows the title as a separate heading above the body. Prepared documents have no top-level `text` field, so the title is not shown twice.
- **G1: Addressed.** `lib/types.ts:149`, `components/label/queueView.ts:3-17`, `QueueCard.tsx:57`, `Queue.tsx:29`.
- **G2: Addressed.** `routers/labeling_v2.py:171-177` saves the previous visit time as `prevSeenAt`, and `label/overview.py:139` counts changes from it. On the frontend, `labeling/page.tsx:45-46` starts the overview fetch before recording the visit.
- **G3: Addressed.** `config.py:92` sets `extra = 'ignore'`, and the key is removed from `.env.example`.
- **G4: Addressed.** `model/features.py:30-32`: an unknown channel now gives an all-zero channel encoding instead of an error.
- **G5: Addressed.** `prep/guards.py:16-18` applies the R-106 lock whenever the prep result reference would change. That covers `/prep/run`, legacy `/preprocess` and publication.
- **G6: Addressed.** README.md:12 and 322-338 describe local vector search and list the new settings with their real names from `config.py`. Neither README nor `.env.example` contains any secret values, only names and defaults.

## New issues

**Critical:** none.

**Important**
1. **The 5-second overview poll now scans everything.** `model/dataset.py:13-27`, called from `label/overview.py:166-167`, runs on every poll of the labeling and training screens. Each time it:
   - parses every prepared document (`infer.documents`);
   - loads every vector file as float32, about 400 MB of allocation at 100k documents;
   - does this without the caching that `index_documents` uses (file stamps, `overview.py:51-56`).

   The cost grows with the size of the collection. The fix is to cache the count, keyed on the prep result and the labels database state, or to compute it only on the training screen.

**Minor**
1. **Old prep results are wiped, even under started labeling.** `prep/pipeline.py:173-180` deletes, then rebuilds, any prep folder whose manifest lacks `collectionFinalized`. The R-106 lock does not stop this, because the result reference is unchanged, and another version may still point at that folder. The risk is limited to development data created before this fix.
2. **Status can show a stale stage-5 report.** `routers/training_v2.py:73-74` reads the report from the export folder first. Monitoring updates after an export only reach the separate compatibility copy (`monitor.py:126-129`). The frontend mostly reads `training.monitor` first (`training/page.tsx:64`), so the impact is small.
3. **Broken README table.** A blank line at README.md:321 cuts the new settings rows off from the table header, so they will not render as a table.
4. **Response format change on `/preprocess`.** It now uses the shared error wrapper (`routers/preprocessing.py:12`), so a 422 validation error and an OSError now come back in that wrapper's format. Stage 0-2 tests pass.
5. **Blank queue label.** `queueView.ts:11`: an unknown `reason` value shows an empty label instead of a fallback.

**Verdict: Approved.**
