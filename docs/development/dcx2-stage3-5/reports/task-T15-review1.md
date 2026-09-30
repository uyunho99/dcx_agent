### Spec Compliance
- ✅ **`*.sqlite` copied with the backup API** (F4). `versions.py:86-93` opens the source read-only and backs it up to the target in one step. `versions.py:148-149` leaves WAL, SHM and journal sidecar files out of the copy. SQLite gives a consistent snapshot even while writers are active.
- ✅ **Everything gets copied, and references stay valid.** `labels.sqlite`, `known_vectors.f16` and `stage_*.json` live in the version folder, so `copytree` picks them up. Vectors and the judge cache sit outside it, keyed by `derivedRef` and `judgeRefs`. Both references are kept (`versions.py:117`, `:123`), so they still resolve. `training.exportRef` is dropped when restarting at stage 5 or earlier (`:126`). The old `classified/{sid}/v1/...` files stay in place.
- ✅ **Stage 3 restart.** `prep.status='stale'`, and the settings and `derivedRef` are kept (`versions.py:117-118`). The `labeling_v2.py:82` gate forces prep to run again. `prep.py:105-107` reuses the existing result when the rule is the same, and the integration test confirms 0 new embeddings (`test_integration_stage3_5.py:201-210`).
- ✅ **Stage 4 restart.** `human` is kept. `final` and `queue` are archived to `stale_*` tables and the active ones emptied. The judge cache is untouched (`versions.py:96-124`).
- ✅ **Stage 5 restart** sets `training={'status':'stale'}` (`versions.py:125-126`).
- ✅ **409 while a worker runs.** `_idle` (`versions.py:70-73`) blocks on any activity in the `running` state, now including runner rows. A paused judge is allowed.
- ✅ **Server-owned keys.** `/save-session` now also protects `prep`, `labeling` and `training` (`sessions.py:25`). `PATCH /session` only accepts `step` and `drafts` (`context.py:93`). Every server write in stages 3-5 goes under those three keys.
- ⚠️ **`compare`** (`versions.py:239-250`). Stage 3 returns only `stage_3`, and stages 4 and 5 return only `stage_5`. The brief says the stage 3 and stage 5 figures should appear "side by side", which could mean both.
- ✅ **Stage 0-2 behaviour unchanged.** `_restart` does nothing when there is no `prep`, `labeling` or `training` data and no `labels.sqlite`. The full suite passes.
- ✅ **Activity badges** (`store.py:157-169`): "판정 62%" (judging), "학습 중" (training) and "중단됨 · 이어서 진행" (stopped, continue) are produced as specified.

### Strengths
- The integration test is meaningful. It blocks all sockets, and uses a mock HTTP transport for Jev and the offline fake for codex. It runs the real prep, judge, review, audit, training, inference, export and clustering steps. It checks that the KMeans input matches the vector-store matrix exactly and that no embedding calls are made.
- Keeping stale rows in archive tables instead of changing the schema preserves the positional INSERT into `final`, and lets cache reconciliation run again unchanged.
- The report is candid: it separates the fixture's setup error from the real failing-test evidence.

### Issues
**Critical:** none.

**Important:**
1. **The "stopped" badge never goes away.**
   - `runner.status(sid)` returns every run ever recorded, across all versions. `public()` carries no version, and nothing ever deletes or replaces rows.
   - One interrupted or failed run therefore keeps appearing as a candidate forever. That includes runs on old read-only versions and runs whose resumed replacement already finished (`done`).
   - `activity_rank` puts interrupted and failed first (`store.py:174-176`). So the session list shows "중단됨 · 이어서 진행" and floats that session to the top permanently.
   - Fix: keep only the latest run for each kind (and labeler) in the active version, and drop interrupted or failed runs once a newer run of the same kind exists.
2. **A stale `stage_5.json` is copied into the new version.**
   - Restarting at stage 5 or earlier resets `training` but keeps the copied `stage_5.json`.
   - `training_v2.py:62` then shows the old stage 5 report next to `status: stale`, and `monitor.py:118` reads it too.
   - `compare(stage5)` right after the restart reports `same=True`, which is misleading.
   - Fix: when restarting at stage 5 or earlier, remove or rename `stage_5.json` in the new version, and do the same for `stage_3.json` when restarting at stage 3.
3. **`test_version_copy_sqlite_consistent` does not test a write during the backup.** The submit commits only after `backup()` has returned (`test_versions_stage3_5.py` backup override). The test does prove the snapshot boundary and that the WAL contents are included, which is the F4 intent. It never exercises a write racing the page copy.

**Minor:**
- `failed` gets the same "이어서 진행" (continue) label as `interrupted`, but a failed run may not be resumable.
- `session_activities` now calls `runner.status` for every session on `GET /sessions`. That opens a `BEGIN IMMEDIATE` write transaction and creates `work/{sid}/runs.sqlite` even for stage 0-2 or legacy sessions.
- Opening a WAL database with `mode=ro` fails if the `-wal` file exists but `-shm` is missing. This is a rare edge case after a crash.
- A running `monitor` also blocks version creation, which is stricter than the brief's list (prep, judge, train, infer). It is harmless because monitor jobs finish on their own.
- The review diff file `.superpowers/sdd/03-plan/review-30e277d..4612d36.diff` does not exist. I reviewed with `git diff 30e277d 4612d36` instead.

### Assessment
The core version-copy work is correct: the backup-API copy, reference handling, per-stage restart rules, server-owned key protection and the integration test. The two Important issues are real behaviour bugs: the badge that never clears, and the stale stage 5 report carried into the new version. Both fixes are small.

Task quality: Needs fixes
