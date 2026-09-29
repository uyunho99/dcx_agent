# Final fix W1 — backend context, keywords, sessions and fake LLM

## Changes and covering tests

- **C2:** Ship seven schema-valid default fixtures: `kw_round_1`–`kw_round_4`, `category_suggest`, `kw_suggest_words`, `kw_axis_classify` (all production LLM task names found). Round counts are 70/100/60/60, satisfying MIN_COUNT, with 290 distinct literal words. `make_corpus.py` distributes five fixture words per synthetic review and retains the original synthetic markers for existing offline integration clients. Generated the ignored `backend/tests/fixtures/aircon_qa.csv`: 200 rows, each fixture keyword occurs in at least three rows. Common real-review words 소음, 냄새, 실외기, 리모컨, 결로, 필터, 전기세 are included. No real sample was present. Tests: `test_shipped_fake_rounds_and_corpus` runs real default fixture loading with only the fake backend setting (no fixture-dir patch); `test_shipped_fixture_validates` checks all seven schemas; suggestions are exercised through the API.
- **I2:** Remove every key-based stale inference. Explicit confirmation clears exactly one marker. Context PUT confirms stage0; keyword commit/manual/HITL confirm stage1. Coverage, round start/recovery, crawl gate/config preserve markers. Tests: `test_only_explicit_confirmation_clears`, `test_background_paths_preserve_stale`, `test_hitl_confirms_stage1`, and `test_crawl_confirm_and_nonconfirm_paths` exercise actual W2 list/config/gate calls.
- **I3 / R-58:** Forks restarting stage0 or stage1 retain copied results and mark each copied round `needsRegeneration`. Order validation rejects predecessors still needing regeneration. Copied committed rounds start gen+1, with or without regenerate; commit replaces that round's generated keywords and invalidates later committed rounds. The per-round marker survives stage1's first confirmation. Temporary `replacing` state resets at commit so normal R4 extra-generation behavior remains cumulative. Tests: `test_restart_round_order_and_replacement` (both query modes), `test_restart_r4_then_extra_generation_preserves_committed`, and existing generation/order tests.
- **R-59:** Version creation calls W2's read-only `phase_state(sid)`. Running remains 409; unfinished detaches the new version's collectionId and marks stage2 stale, even when restarting a later stage. Original version retains its collection. A transitional read-only fallback through `latest_run`/`CrawlQueue.open_readonly` was implemented before the public helper existed; the current W2 helper is used in validation. Tests: `test_fork_collection_phase` and `test_fork_detaches_actual_unfinished_queue` (stopped/interrupted/paused). Existing completed-collection tests now explicitly model a done phase.
- **R-61:** Remove the unlocked keyword dependency guard. Every keyword mutation checks the displayed version within its session-lock critical section; slow manual volume and coverage work capture then recheck the version before writing. Suggest-words captures the version directory under lock. Context/session/version mutations also accept optional query version. Tests: `test_stale_version_does_not_write` snapshots all disk files; `test_version_checked_after_lock_acquired` switches versions just before acquiring the lock across all six keyword POST routes; `test_session_mutations_guard_displayed_version` covers fork/activation/legacy save/delete.
- **R-62:** Validate decisions, append deterministic `commit:{round}:{gen}:{kwId}:{eventType}` events with fsync and ID deduplication, then save committed state. Event, session and feedback writes share one lock and captured version directory. The type suffix distinguishes a move from its rejection event. Test: `test_commit_crash_retries_events_once` crashes after append and before state write, then retries without duplicate events. Existing event-concurrency/version-isolation tests remain green.
- **R-63:** Per-row unreadable sessions return exactly `{sid,status:"unreadable"}` while healthy rows remain. Save/delete exceptions use generic messages. OpenAI connected requires both key and model. V2 legacy saves discard bk/pd/problemDef/allKw/_pendingKw/ages/ar/gens along with server-owned fields. Tests: `test_unreadable_session_isolated`, `test_session_errors_generic`, `test_openai_needs_model`, `test_legacy_keys_dropped`.

Existing assertion updates: explicit stage confirmation in `test_restart_marks_downstream_stale`; exact new mismatch message in feedback version isolation. No W2/W3 files were edited by W1. The CSV is a generated ignored QA artifact, not a source change.

## W2 confirmation contract

`store.update_session(sid, patch, confirm_stage=None)` acquires the session lock.
`store._update_locked(sid, patch, confirm_stage=None)` requires that the caller already holds it.
Both clear ONLY the supplied stage marker; None preserves all markers, including stageResults writes.
For `start_list` creating a collection, pass `confirm_stage="stage2"`. W2's `_mutate` already holds the lock, so it must call `_update_locked`, never nest `update_session` (flock is not reentrant). W2's current implementation now does this; real crawl contract tests pass. Config/gate/progress/recovery omit confirmation.

## W3 displayed-version contract

All keyword POST routes accept optional **query** `?version=vN`:

- `/keywords/{sid}/rounds/{n}` (also `?regenerate=true&version=vN`)
- `/keywords/{sid}/rounds/{n}/commit`
- `/keywords/{sid}/events`
- `/keywords/{sid}/manual`
- `/keywords/{sid}/suggest-words`
- `/keywords/{sid}/coverage`

Other guarded mutations also use optional query `?version=vN`: PUT `/context/{sid}`, PATCH `/session/{sid}`, POST `/sessions/{sid}/versions`, PUT `/sessions/{sid}/active-version`, POST `/save-session`, DELETE `/delete-session/{sid}`. On active-version, the body `version` remains the activation target; the query is the displayed active version. On version creation, body `from` remains the fork source. New-session creation/category suggestion have no existing session version to guard. Crawl routes remain W2-owned.

Mismatch returns HTTP 409 with `error.kind="conflict"`, `error.message="다른 버전이 활성화되었습니다"`. Omitted version keeps compatible behavior. Other request bodies are unchanged.

## Fixture keyword list

**R1 (70):** 소음, 소음문제, 소음관리, 소음설정, 소음점검, 소음변화, 소음상태, 소음조절, 소음확인, 소음불편, 냄새, 냄새문제, 냄새관리, 냄새설정, 냄새점검, 냄새변화, 냄새상태, 냄새조절, 냄새확인, 냄새불편, 실외기, 실외기문제, 실외기관리, 실외기설정, 실외기점검, 실외기변화, 실외기상태, 실외기조절, 실외기확인, 실외기불편, 리모컨, 리모컨문제, 리모컨관리, 리모컨설정, 리모컨점검, 리모컨변화, 리모컨상태, 리모컨조절, 리모컨확인, 리모컨불편, 결로, 결로문제, 결로관리, 결로설정, 결로점검, 결로변화, 결로상태, 결로조절, 결로확인, 결로불편, 필터, 필터문제, 필터관리, 필터설정, 필터점검, 필터변화, 필터상태, 필터조절, 필터확인, 필터불편, 전기세, 전기세문제, 전기세관리, 전기세설정, 전기세점검, 전기세변화, 전기세상태, 전기세조절, 전기세확인, 전기세불편

**R2 (100):** 냉방, 냉방문제, 냉방관리, 냉방설정, 냉방점검, 냉방변화, 냉방상태, 냉방조절, 냉방확인, 냉방불편, 제습, 제습문제, 제습관리, 제습설정, 제습점검, 제습변화, 제습상태, 제습조절, 제습확인, 제습불편, 송풍, 송풍문제, 송풍관리, 송풍설정, 송풍점검, 송풍변화, 송풍상태, 송풍조절, 송풍확인, 송풍불편, 풍량, 풍량문제, 풍량관리, 풍량설정, 풍량점검, 풍량변화, 풍량상태, 풍량조절, 풍량확인, 풍량불편, 온도, 온도문제, 온도관리, 온도설정, 온도점검, 온도변화, 온도상태, 온도조절, 온도확인, 온도불편, 습도, 습도문제, 습도관리, 습도설정, 습도점검, 습도변화, 습도상태, 습도조절, 습도확인, 습도불편, 설치, 설치문제, 설치관리, 설치설정, 설치점검, 설치변화, 설치상태, 설치조절, 설치확인, 설치불편, 배수, 배수문제, 배수관리, 배수설정, 배수점검, 배수변화, 배수상태, 배수조절, 배수확인, 배수불편, 청소, 청소문제, 청소관리, 청소설정, 청소점검, 청소변화, 청소상태, 청소조절, 청소확인, 청소불편, 진동, 진동문제, 진동관리, 진동설정, 진동점검, 진동변화, 진동상태, 진동조절, 진동확인, 진동불편

**R3 (60):** 수면, 수면문제, 수면관리, 수면설정, 수면점검, 수면변화, 수면상태, 수면조절, 수면확인, 수면불편, 예약, 예약문제, 예약관리, 예약설정, 예약점검, 예약변화, 예약상태, 예약조절, 예약확인, 예약불편, 절전, 절전문제, 절전관리, 절전설정, 절전점검, 절전변화, 절전상태, 절전조절, 절전확인, 절전불편, 환기, 환기문제, 환기관리, 환기설정, 환기점검, 환기변화, 환기상태, 환기조절, 환기확인, 환기불편, 난방, 난방문제, 난방관리, 난방설정, 난방점검, 난방변화, 난방상태, 난방조절, 난방확인, 난방불편, 벽걸이, 벽걸이문제, 벽걸이관리, 벽걸이설정, 벽걸이점검, 벽걸이변화, 벽걸이상태, 벽걸이조절, 벽걸이확인, 벽걸이불편

**R4 (60):** 자동운전, 자동운전문제, 자동운전관리, 자동운전설정, 자동운전점검, 자동운전변화, 자동운전상태, 자동운전조절, 자동운전확인, 자동운전불편, 스마트폰, 스마트폰문제, 스마트폰관리, 스마트폰설정, 스마트폰점검, 스마트폰변화, 스마트폰상태, 스마트폰조절, 스마트폰확인, 스마트폰불편, 음성안내, 음성안내문제, 음성안내관리, 음성안내설정, 음성안내점검, 음성안내변화, 음성안내상태, 음성안내조절, 음성안내확인, 음성안내불편, 표시등, 표시등문제, 표시등관리, 표시등설정, 표시등점검, 표시등변화, 표시등상태, 표시등조절, 표시등확인, 표시등불편, 실내기, 실내기문제, 실내기관리, 실내기설정, 실내기점검, 실내기변화, 실내기상태, 실내기조절, 실내기확인, 실내기불편, 냉매, 냉매문제, 냉매관리, 냉매설정, 냉매점검, 냉매변화, 냉매상태, 냉매조절, 냉매확인, 냉매불편

Category: 디지털/가전 → 계절가전 → 에어컨. Suggest-words: 시원하다, 조용하다, 쾌적하다, 답답하다, 습하다, 건조하다, 번거롭다, 편리하다, 차갑다, 덥다. Axis fixture: 소음/냄새 → physical, 전기세 → psychological.

## RED / GREEN

Tests were written before the corresponding fixes.

Initial RED command: `cd backend && .venv/bin/python -m pytest tests/context/test_final_w1_context.py tests/keywords/test_final_w1.py -q`

```text
23 failed, 2 passed, 1 warning in 1.44s
```

Additional RED for session mutation query guards:

```text
4 failed, 12 deselected, 1 warning in 1.23s
```

Additional RED for R4 extra generation after restart:

```text
1 failed, 19 deselected, 1 warning in 2.61s
```

The first full run returned 4 failed / 507 passed: W2's integration tests used the original synthetic corpus markers. Preserving those markers in W1's corpus generator restored compatibility without editing W2 tests. A subsequent full run passed 518 tests. Final required command outputs follow.

`cd backend && .venv/bin/python -m pytest tests/context tests/keywords tests/llm -q`

```text
........................................................................ [ 25%]
........................................................................ [ 50%]
........................................................................ [ 75%]
.....................................................................    [100%]
=============================== warnings summary ===============================
app/config.py:8
  /Users/persona1/Desktop/dcx_agent-dcx2-stage0-2/backend/app/config.py:8: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
285 passed, 1 warning in 10.16s
```

`cd backend && .venv/bin/python -m pytest -q`

```text
........................................................................ [ 13%]
........................................................................ [ 27%]
........................................................................ [ 41%]
........................................................................ [ 55%]
........................................................................ [ 68%]
........................................................................ [ 82%]
........................................................................ [ 96%]
..................                                                       [100%]
=============================== warnings summary ===============================
app/config.py:8
  /Users/persona1/Desktop/dcx_agent-dcx2-stage0-2/backend/app/config.py:8: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

tests/test_integration_stage0_2.py::test_downstream_clustering_reads_compat_fields
  /Users/persona1/Desktop/dcx_agent-dcx2-stage0-2/backend/.venv/lib/python3.12/site-packages/joblib/externals/loky/backend/context.py:134: UserWarning: Could not find the number of physical cores for the following reason:
  invalid literal for int() with base 10: ''
  Returning the number of logical cores instead. You can silence this warning by setting LOKY_MAX_CPU_COUNT to the number of cores you want to use.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
522 passed, 2 warnings in 33.03s
```

## Concerns

No test failures remain. Warnings are the existing Pydantic class-config deprecation and joblib physical-core detection falling back to logical cores in the sandbox. No real provider calls were used. The generated corpus is synthetic and is ignored by git. Parallel W2/W3 changes and unrelated .DS_Store changes are excluded from the W1 commit.

## Commit outcome

**uncommitted**. Attempted explicit W1-only staging and `git commit --only -F` using the requested subject and final `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` line. Staging failed because the sandbox cannot create the worktree index lock. The commit then rejected the unstaged new paths. No escalation or unrelated staging was attempted.

```text
add exit 128
fatal: Unable to create '/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock': Operation not permitted

commit exit 1
error: pathspec 'backend/tests/context/test_final_w1_context.py' did not match any file(s) known to git
error: pathspec 'backend/tests/context/test_w1_crawl_contract.py' did not match any file(s) known to git
error: pathspec 'backend/tests/keywords/test_final_w1.py' did not match any file(s) known to git
error: pathspec 'backend/tests/llm/test_shipped_fixtures.py' did not match any file(s) known to git
error: pathspec 'docs/development/dcx2-stage0-2/reports/final-fix-W1.md' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/category_suggest.json' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/kw_axis_classify.json' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/kw_round_1.json' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/kw_round_2.json' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/kw_round_3.json' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/kw_round_4.json' did not match any file(s) known to git
error: pathspec 'backend/tests/fixtures/llm/kw_suggest_words.json' did not match any file(s) known to git
```

W1 source diff whitespace check passed. Final tests: 285 targeted / 522 full, all passed.
