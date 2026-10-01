# DCX2 stage 3–5 branch review

Reviewed `0e4501e..e16c5ce306d94bdf4af344e4802cf34ea2d6e0db` (`feature/dcx2-stage3-5`) against the specified plan-worktree `02-design-r2.md`, `03-plan.md`, and the decision log. Findings already recorded in `final-review1.md` or backlog B-108 are excluded.

Read-only review: only this report was written. Validation used source/diff inspection and Python probes with bytecode disabled, in-memory SQLite, and mocked filesystem/provider boundaries. No live providers, application datasets, or full test suites were run. Crash scenarios below are code-traced, not destructive fault-injection tests.

## Important

### 1. A human audit can return Non while permanently saving Core

**Location:** `backend/app/label/audit.py:139`; `backend/app/label/route.py:260`.

Model `final.level` is the most probable grade, whereas `final.tags_json` contains independently thresholded binary tags (`model/infer.py:151`). These can imply different grades. Audit reconciliation skips an answer whenever its tags equal `tags_json`, without comparing its calculated grade. The subsequent model-confirmation branch changes `source` to `human` but leaves the model's grade untouched.

**Reproduction:** Use four agreeing members with anchor and situation probabilities `0.99`, and each of the six semantic probabilities `0.4`; leave the optional signal untrained/null. The prediction is accepted Core, with relevance approximately `0.944`, but its thresholded tags imply Non. Sample this document for audit and submit anchor=true, situation=true, all semantic tags=0, null signal/reason. The actual in-memory execution returned `level='non'` while persisting `{level: 'core', source: 'human', route: 'audited'}`. Subsequent reconciliation still skips it. Export gives this human row precedence and includes it in `relevant.jsonl`; training independently calculates Non from its tags.

**Fix:** Recompute and persist the human grade even when the submitted tags equal the model projection; compare both tags and grade before treating an audit as unchanged.

### 2. Valid stage-3 restarts collide with an earlier GPT execution

**Location:** `backend/app/label/gpt.py:93` and `backend/app/label/gpt.py:128`.

The vote cache includes `prepKey`, but the Codex execution ID contains only session, question version, context hash, and document IDs. The context hash also omits prepared content. Codex's immutable manifest rejects changed inputs under an existing run ID (`llm/codex_exec.py:132`).

**Reproduction:** Finish GPT labeling of one batch in v1. Create v2 with “3단계부터 다시,” change a boilerplate phrase that occurs in those documents, and rerun preparation without removing any documents. Keep the one-liner and model unchanged. The fresh vote cache schedules the same document IDs with changed text, generating the old Codex run ID. `run_many` returns “Run ID already has different inputs or settings”; GPT pauses. Resuming repeats the collision and can eventually mark these documents bad. This occurs through the intended new-version workflow, independently of the already-reviewed same-version invalidation issue.

**Validation:** The in-memory probe produced identical run IDs and different prompts for unchanged IDs with changed bodies. **Fix:** Include the preparation identity or a canonical input hash in the execution ID.

### 3. Preparation can freeze an unfinished crawl into a permanently reused result

**Location:** `backend/app/routers/prep.py:93` through `backend/app/routers/prep.py:110`.

Starting preparation checks only the prep worker state and collection ID, not whether the crawl collection has finished. The source is read once, but the reuse key depends on collection ID/configuration rather than its changing contents. A completed prep manifest is then reused without examining crawl completion or newly arrived documents.

**Reproduction:** While detail crawling c1 has saved its first 100 documents and is still collecting, navigate directly to preprocessing through the sidebar and run it. Let preparation finish before the remaining crawl documents arrive. After c1 reaches 1,000 documents, rerun with the same configuration. The endpoint returns `reused: true` and keeps the original 100-document result, silently omitting 900 documents from labeling and export. Running early enough can freeze an empty result instead.

**Validation:** An in-memory endpoint probe launched preparation without consulting a crawl phase check. `PrepScreen` also enables execution based on the presence of `collectionId`, not crawl completion. **Fix:** Require a finalized collection before starting or reusing preparation, including the compatibility entry point.

### 4. The training screen disables training when every usable label is human

**Location:** `frontend/src/components/train/trainingView.ts:39`.

`trainingLabels` treats `overview.accepted` as the complete training set. The backend defines that count as `route='accepted'`; human escalations have `route='escalated:human'`, and corrected/confirmed audits can have `route='audited'`. Nevertheless, the training query explicitly includes all `source='human'` rows (`routers/training_v2.py:96`). The page uses the incorrect empty flag to disable both fresh and additional training.

**Reproduction:** Label 40 documents for which Jev and GPT disagree on every grade, then finish all 40 human reviews, with successful embeddings. There are 40 eligible training rows but `overview.accepted == 0`. Stage 5 says there are no training labels and disables “학습 시작” and repository additional-training actions. The backend can train these same rows if called directly. An analogous failure occurs after reviewing all uncertain model-mode predictions.

**Validation:** The in-memory human-label projection had one trainable human row and zero accepted rows. **Fix:** Expose/use a training-eligible count matching the backend selection, including human reviews.

### 5. `JEV_BACKEND=fake` still invokes the real HTTP adapter

**Location:** `backend/app/label/judge.py:112`; also `backend/app/model/monitor.py:87`.

The configuration accepts a fake Jev backend, but workers unconditionally construct `JevClient`. The setting is only used in the cache identity. `JevClient.judge` always posts to `jevmodel.org`; no production adapter selection implements the fake setting. The integration test hides this by monkeypatching the client factory.

**Reproduction:** Start the documented offline QA configuration with `JEV_BACKEND=fake`, `EMBED_BACKEND=fake`, and `LABEL_GPT_BACKEND=fake`. Stage-4 Jev fails as unconnected when no key is present. If the environment contains a real Jev key, this supposedly offline run sends document content to the real service and consumes requests. Model monitoring takes the same path.

**Validation:** With `settings.jev_backend='fake'`, a MockTransport recorded an HTTP request addressed to `jevmodel.org`; no live request was made. **Fix:** Select a deterministic fake adapter in both worker paths, and test the environment-configured subprocess path without replacing its client factory.

### 6. Re-export can destroy the last published output on process failure

**Location:** `backend/app/model/export.py:69` and `backend/app/model/export.py:70`.

Every export overwrites the same version-local `all.jsonl` and `relevant.jsonl`. The existing local storage helper uses `Path.write_text`, which truncates the destination in place (`services/s3.py:55`); stage-5 JSON is also written non-atomically. The old `training.exportRef` stays published throughout these writes. A session lock does not protect against a crash or preserve the previous file contents.

**Reproduction:** Successfully export v1, then export it again after additional reviews or training. Kill the API process after `relevant.jsonl` is opened/truncated but before its write finishes, or encounter a disk-full write. Restart: the session still advertises the successful export reference/timestamp, but that path now contains an empty or partial result. Local RAG/clustering either sees missing documents or raises a JSON parsing error. A failure between the individual file writes can also leave all/relevant/report artifacts from different export attempts.

**Fix:** Write a complete export generation to fresh paths, fsync it, then atomically publish the reference. Preserve the previously published generation until the new one is complete.

## Minor

### 7. Human reviewers cannot see the title when a document has a body

**Location:** `frontend/src/components/label/QueueCard.tsx:56`.

The card renders `text || body || content || title`, so the title is only a fallback. Both machine labelers receive title and body; the review API already includes the title, but the human sees less evidence.

**Reproduction:** Review a post titled “에어컨 설치 후 밤에 생긴 소음” with body “이것 때문에 잠을 못 자서 결국 껐어요.” The card shows only the body and comments. The product/temporal context needed for anchor and situation is hidden, affecting both escalation decisions and independent audit answers.

**Fix:** Render the title separately above the body, preserving both inputs available to the labelers.

Assessment: fixes required before merge. No new Critical finding established.

Status: Critical 0 | Important 6 | Minor 1
