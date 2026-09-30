# SDD ledger — plan: docs/development/dcx2-stage3-5/03-plan.md
Spec: docs/development/dcx2-stage3-5/02-design-r2.md (승인본 02-design.md + 계획 단계 결정). Executor: Codex via codex:codex-rescue (--wait --fresh --write). Baseline 2026-09-30: pytest 815 passed, vitest 139, lint · build ok. Branch base d5d8a66.

## Pre-flight scan
| 대상 | 생산 → 소비 | 확인 결과 |
|---|---|---|
| T01 ↔ T14 | T01이 `pinecone_api_key` · pinecone 의존성 삭제 → `services/pinecone_svc.py` · `services/embedding.py`가 T14까지 사용 | 충돌: T14 전까지 import 깨짐 위험 |
| T01 ↔ T13 | T01 tensorflow 제거 → `services/training.py`(지연 import, try 안) | 문제 없음(옛 경로 import 실패 시 기존 폴백) |
| T02 → T04 · T12 · T14 | Embedder · VectorStore · cosine_topk | 인터페이스 일치 |
| T03 → T09 · T11 · T13 | grade · grade_probs (near_boundary 없음) | 일치 |
| T06 · T07 → T08 | JevVote · GptVote · judge_batch(docs, one_liner) | 일치 |
| T08 → T09 · T11 | VoteCache(bad 문서 → labeler_failed) | 일치 |
| T09 → T10 · T11 · T12 | LabelStore(final · human · audit_set · queue) | 일치 |
| T11 ↔ 옛 labeling 화면 | T11이 `/sample` 삭제 표기 → 옛 세션 열람 화면이 사용 | 충돌: 표기가 "옛 세션 열람은 유지"와 모순 |
| T13 → T14 | `training.exportRef` · `classified/{sid}/{version}/relevant.jsonl` | 일치 |
| T15 | routers/sessions.py 서버 소유 칸 + versions | T05 · T11 · T13 뒤 순서 맞음 |
| main.py | T05 → T11 → T13 → T14 | 순차 지정됨 |
| work/worker.py | T05 · T08 · T13 | 순차 |
| T16 → T17~T20 | lib/api · logic · 컴포넌트 | 일치 |
| 각 Task 자기 일관성 | T01~T20 테스트 ↔ 인터페이스 | T01 `test_settings_defaults`가 pinecone 부재를 단언(아래 규칙으로 이동) — 그 외 일치 |

Ruling: pinecone 설정 · 의존성 삭제와 `hasattr(Settings(), "pinecone_api_key") is False` 단언은 T01이 아니라 T14에서 한다 — pinecone_svc를 대체하는 Task가 같이 지워야 중간 상태가 깨지지 않음 — 틀리면 T01~T13 동안 pinecone 설정이 남는 것뿐.
Ruling: T11은 `/sample`을 지우지 않는다 — 계획 표기 "새 세션 미사용, 옛 세션 열람은 유지"를 따르면 옛 화면이 쓰는 경로가 남아야 함 — 틀리면 쓰이지 않는 경로 하나가 남음.
Task T01: implemented by Codex (agent a9377877cd77382d5), committed by controller 2b49789 — Ruling: controller runs pip install and git commit for Codex tasks — Codex sandbox blocks network and worktree git metadata writes — if wrong, commits carry controller as committer but content is Codex's
Ruling: 사용자 요청("동시에 개발 가능한건 동시에")에 따라 파일 소유가 겹치지 않는 Task는 병렬로 Codex에 보낸다 — SDD 기본(순차)보다 사용자 지시가 우선 — 틀리면 같은 파일 충돌이 날 수 있어, 각 dispatch에 소유 파일 외 수정 금지와 병렬 상대 파일 목록을 명시한다.
T01 review dispatched (sonnet). T02 · T03 dispatched in parallel from base 2b49789.
Task T01: complete (commits d5d8a66..2b49789, review clean)
Task T01: minor (deferred): worker.execute state defaults 'done' and catches only Exception (SystemExit/KeyboardInterrupt recorded as done) — worker.py:529-546
Task T01: minor (deferred): Context._row uses BEGIN IMMEDIATE for reads; per-item should_stop in T08 may contend — carry to T08 dispatch
Task T01: minor (deferred): --args-json on argv (ps/ARG_MAX), child stdout/stderr to DEVNULL; status() unbounded; test_settings_defaults checks 3/21; pydantic-settings min version unpinned; import order control.py:160
Task T03: implemented by Codex, committed 77cd329 (tests/label 11 passed; suite 841 passed excl. in-progress tests/vectors); review dispatched. T06 dispatched in parallel with T02 (base 77cd329).
Task T03: complete (commits 2b49789..77cd329, review clean)
Task T03: minor (deferred): grade_probs may return tiny negatives from float error; no clamp (rule.py:37-38); KeyError on missing field untested
Task T02: implemented by Codex, committed e88acd0 (vectors 14 passed; suite 855 passed)
Task T02: complete (commits 77cd329..e88acd0, review clean)
Task T02: minor (deferred): VectorStore.write_shard rewrites ids.jsonl each call — callers must buffer 10,000 rows per call (check in T04 review); cosine_topk allow/exclude mask via Python loop
Task T06: implemented by Codex, committed 3d86f1f (tests/label 61 passed; suite excl. in-progress prep: 903 passed + 2 failures caused by T04 in-progress preprocessing.py)
Task T06: review — Needs fixes (2 Important: caller-supplied Idempotency-Key; shared per-key limiter pool). Fix round 1 dispatched (fresh Codex; resume not used because parallel Codex threads make resume-last ambiguous).
Task T06: minor (deferred): noul prob >1 epsilon rejected; 429 ignores Retry-After, no key rotation; jev_questions(one_liner) unused arg; huge title → bad
Task T06: fix round 1 committed 690e3f7
Task T06: fix round 1/5 (2 addressed, 0 open; commits 3d86f1f..690e3f7)
Task T06: complete (commits e88acd0..690e3f7, review clean)
Task T06: minor (deferred): limiter pool keyed by key hash only (rate change mid-process ignored); idempotency_key keyword-only (T08 must pass by name)
Task T07: implemented by Codex, committed 80d75b4 (label+llm focused pass; suite 934 passed, 2 deselected T04-affected)
Task T04: implemented by Codex, committed bf87c13 (full suite 954 passed)
Task T04: review — Needs fixes (Important 1: unconnected Voyage cached as done; Important 2: failed vectors never retried on resume).
Ruling: T04 Important 1은 이미 T05 dispatch가 "pipeline.py 최소 수정으로 embedder_unconnected 실패 처리"를 맡고 있어, T05 완료 후 T04 fix round 1에서 두 finding을 함께 확인 · 마무리한다 — pipeline.py를 두 Codex가 동시에 고치는 충돌 방지 — 틀리면 T04 완료가 T05 뒤로 조금 늦어짐.
Task T04: minor (deferred): snippet docs ad filter only body/comments; compat filename time_ns vs legacy timestamp format; embed retry no backoff
Task T07: complete (commits 690e3f7..80d75b4, review clean)
Task T07: minor (deferred → carry to T08): non-parse/schema failures (incl. persistent "Run ID already has different inputs" when codex settings change) all become LabelerPaused; Core/Supporting vote with signal=None accepted silently; quota markers heuristic; fully unusable batch requeued without attempt counter (T08 must count attempts)
Task T05: implemented by Codex, committed ae514eb (suite 962 passed)
Task T05: complete (commits bf87c13..ae514eb, review clean)
Task T05: minor (deferred): _save config branch does locked whole-session write (drops removed keys, bypasses update_session); stale 'running' with no worker row never becomes interrupted; prep_key before collection check (collection_required 409 untested); config-while-running untested; private store._update_locked / versions._data use; run_worker docstring overstates guard
Task T04: fix round 1/5 (2 addressed per implementer; 8 regressions in tests/test_integration_stage0_2.py and tests/crawl/test_final_w5.py::test_finish_partial — preprocess without keys now raises)
Ruling: 3단계는 docs → tokens → compat(preprocessed/) 파일을 쓴 뒤 임베딩 단계에서 EmbedderUnconnected로 멈춘다; 옛 서비스 진입점 preprocess_data는 이를 잡아 job을 done + embedding "unconnected"로 기록한다; /prep API · 워커는 failed + embedder_unconnected(T05 그대로) — 0~2단계 AC-18/19(키 없이 전처리 완료)와 설계 9절(임베딩 단계에서 멈춤)을 둘 다 지키는 유일한 순서 — 틀리면 키 없이 만든 3단계 결과에 벡터가 없는 상태로 남음(done 표시는 안 됨).
Task T08: implemented by Codex, committed 4f8da50 (label+work passed; 8 suite failures belong to in-progress T04 fix)
Task T04: fix rounds 1-2 committed 5bfa2ef (focused 81 passed; suite 970 passed)
Task T04: fix round 2/5 (3 addressed, 0 open; commits 4f8da50..5bfa2ef)
Task T04: complete (commits 80d75b4..5bfa2ef + fix 5bfa2ef, review clean)
Task T04: minor (deferred): docs/tokens rewritten on every run (extra I/O on resume); prep_counts attached ad hoc to exception
Task T08: review — Needs fixes (Important 1: transport/429/5xx exhaustion counted as doc attempts, no backoff; Important 2: codex usage-limit pauses consume attempts, contrary to design 4.5). Fix round 1 dispatched incl. test stabilization.
Task T08: minor (deferred): PID reuse blocks lease reclaim (at column unused as expiry); counts() takes write lock, no WAL; context-change message lost after restart; startup estimate() loads whole corpus in memory; mark_bad unused; Jev 402 path not exercised with real Context
Task T08: fix round 1 committed 12569e7; found: test_kill_restart_no_duplicate_calls fails when pytest runs from repo root (subprocess without cwd/PYTHONPATH) — harness verification runs from root
Task T09: implemented by Codex, committed 283efcf (tests/label 138 passed)
Task T09: review — 1 Important (confidence min over all 8 grade fields vs matching fields).
Ruling: confidence의 min은 등급 결정 필드 8개 전체에 대해 취한다 — 기획안 7절 원문 "등급 결정 필드( anchor · 6차원 · situation ) 일치 비율 × 해당 필드 Jev 최소 확률"의 "해당 필드"는 등급 결정 필드 전체를 가리키고, 02-design-r2 4.7도 같은 문구 — 틀리면 불일치 칸이 있는 문서의 confidence가 조금 낮게 저장됨(τ 제외로 지금은 라우팅에 쓰이지 않음, 학습 가중치에만 영향).
Task T09: complete (commits 12569e7..283efcf, 0 open after ruling)
Task T09: minor (carry → T11): a doc queued labeler_failed that later merges keeps its open queue row — T11 rebuild_queue must close it
Task T09: minor (deferred): candidates cursor read while inserting into final (use fetchall); source always 'agreed' even when Jev value taken on disagreement
Task T08: fix round 2 committed 0e478cf
Task T08: fix round 2/5 (4 addressed, 0 open; commits 5bfa2ef..12569e7, 283efcf..0e478cf)
Task T08: complete (commits ae514eb..4f8da50 + fixes 12569e7, 0e478cf; review clean)
Task T08: minor (deferred): backoff sleep ignores stop requests (auto-pause ~2.5 min into sustained 5xx/429); all 5xx treated transient incl. 501/505; worker transient test covers only ConnectError
Task T10: implemented by Codex, committed 2b72a61 (tests/label from root passed)
Task T10: complete (commits 0e478cf..2b72a61, review clean)
Task T10: carry → T12/T13: audit override sets route='audited' — training set/export must include route in (accepted, audited) and source human; do not filter on route=='accepted' only
Task T10: minor (deferred): audit submissions lack round column (late answers attributed to next round); stats calls write final as side effect; reissue <2 when previous round incomplete
Task T12: implemented by Codex, committed 857e880 (tests/model 13 passed)
Task T12: complete (commits 2b72a61..857e880, review clean)
Task T12: carry → T13: caller must join JevVote.truncated as jev_truncated and build X in Targets.doc_ids order; predict() rebuilds models per call — cache in infer; reported metrics are on the early-stopping validation fold (label as validation in UI/stage_5)
Task T12: minor (deferred): synthetic test too easy (±8σ, human-only rows; soft-label path untrained); agreed row with missing Jev cache vote → bare KeyError (read votes_json['jev'] instead); reason soft targets also average Jev reason_probs (design extension — record in decision log); pos_weight on all binary tags; seed test doesn't check member diversity
Task T11: implemented by Codex, committed 9fe6a1b (full suite 1075 passed from root)
Task T11: review — Needs fixes (Important: 1 queue/final freshness depends on overview polling; 2 polling resets lastSeenAt; 3 overview O(corpus) under session lock blocks next/submit; 4 no skip cursor on /next). Fix round 1 queued after T13 (T13 may touch route.py/labeling_v2.py).
Task T11: minor (deferred): past-version overview writes schema/overrides; mismatchRate uses open queue count; changes.judged double counts; label_part sync=False for current version; /next accepts past versions; modelId not validated
Task T13: implemented by Codex, committed 175e479 (full suite 1100 passed)
Task T13: review — Needs fixes (Important 1: audit hook route.py:157-162 converts unchanged audit confirmations to human/audited in LLM mode too → shifts accepted count and audit cadence; Important 2: LLM mode with trained model — any zero-vector/untrained-head doc blocks export with no way to clear). Fix round 1 queued after T11 fix (route.py conflict).
Task T13: minor (deferred): rebuild_queue imports app.model.infer (torch) on every poll; list_models KeyError without embedder key; monitor aborts on provider exception without recorded reason; model-mode start lacks double-start guard; export files not one transaction
Ruling: T14 Codex asked to add one init call in backend/app/routers/context.py post_context (copy same-bk previous-session Known Insight statements on new session) — allowed; design 6.1 requires it and it is one call — if wrong, context.py gains one line outside T14's table ownership. T14 re-dispatched fresh with this permission (first run made no changes).
Task T11: fix round 1 committed 136d178 (label 194 passed)
Task T14: implemented (retry job task-muo0ck62-hy1ds2); T14 tests 20 passed; 1 failing stage0-2 test test_integration_stage0_2.py::test_downstream_clustering_reads_compat_fields (expects new-session clustering on preprocessed docs).
Ruling: 0~2단계 테스트 test_downstream_clustering_reads_compat_fields는 새 설계(새 세션 군집은 training.exportRef만 읽음, D-109 · O4)에 맞춰 "5단계 모델 없이 내보내기 → 군집이 호환 필드(desc · cafe · link)를 읽음"으로 경로만 바꾸고 단언(호환 필드가 군집 입력에 있음)은 유지한다 — 테스트 의도(D-065)를 지키면서 승인된 설계와 충돌하지 않는 유일한 방법 — 틀리면 새 세션이 5단계 없이 군집을 돌릴 수 없다는 제약이 남음(설계 의도).
Task T11: fix round 1/5 (4 addressed, 0 open; commits 175e479..136d178)
Task T11: complete (commits 857e880..9fe6a1b + fix 136d178, review clean)
Task T11: carry → T18: labeling screen must call POST /label/{sid}/seen once on open; /next skip uses item.cursor as after=
Task T11: minor (deferred): rebuild_queue per-batch full scans (read-only when unchanged); worker sync failure fails judge run; worker syncs non-active version; schema migration guard early-return blocks future DDL; other overview metrics full-table per poll (outside lock)
Task T13: fix round 1 committed e6010b3 (model+label 241 passed)
Task T13: fix round 1/5 (4 addressed, 0 open; commits 136d178..e6010b3)
Task T13: complete (commits b3f8e12..175e479 + fix e6010b3, review clean)
Task T14: implemented by Codex (+fix round 1), committed 8023e0d (full suite 1138 passed from root)
Task T14: review 1 — Needs fixes (Important: persona fallback lost for legacy/no-vector; search_docs holds session lock across embed + full scans). Fix round 1 dispatched (codex bg), brief task-T14-fix1.md. Parked minors: legacy createdAt churn on read; legacy Known CRUD shows 0~2 edit message.
Task T16: implemented, committed 07f8895de78ec64d0151d3da620b348e1fbceeee (tests 155, lint, build ok). Review dispatched.
Task T16: review Approved. Parked minors: KnownInsightsDrawer unknown-from fallback; dense one-line code in QueueCard/Drawer; KeyA IME fallback untested; nowCard fixture shape. Task T16: complete (07f8895)
Task T14: fix 1 committed 30e277d (1168 backend passed). Re-review dispatched.
Task T15: committed 4612d36. Review dispatched.
Task T17: committed e1d923d. Review dispatched.
Task T18: committed b1e9df2. Review dispatched.
Task T19: committed 8b2ed68. Review dispatched.
Task T20: committed 168f19f. Review dispatched. (frontend 174 tests, lint, build ok)
Task T14: re-review fix 1 Approved. Task T14: complete (8023e0d, 30e277d)
Task T18: review Approved. Ruling: seen must fire once on labeling screen open (spec 4.11), not queue-tab open — controller dispatch drifted; fix in frontend batch — cost if wrong: baseline advances on overview-only visits. Parked minors: no component test for seen-once/skip wiring; static definitions copy in Audit.tsx duplicates questions json; overview refetch per submit; help text wording.
Task T17: review Approved. Batch fix: partial-failure copy align to mockup s1 ('임베딩 실패 N건은 0벡터로 남기고 검색 · 학습에서 제외합니다.'). Parked minors: PrepSettings channel tab resets on remount; DEFAULT_BOILERPLATE drift vs backend json; kiwi_unavailable kind not sent by backend (prep_failed); pre-run estimate numbers unavailable from API; getCrawlStatus not version-scoped.
Task T19: review Approved. Batch fix: empty state keyed on displayed accepted count (not merged), keep '모델 없이 내보내기' enabled per D-126; createdAt format '2026. 10. 2.'; drift banner include percent; evidence label '' slots. Parked minors: polls 3 endpoints indefinitely; Jev 대비/멤버 불일치 shown 확인 불가 (API gap); no page-state component tests.
Task T20: review Approved w/ follow-up. Batch fix: persist Vitest for normalizeChatReply/sourceEmptyMessage/stepIndex/activityLabel into repo (were in /tmp/t20-tests); SessionList use server label for all statuses when present; insights chat error text keep '오류가 발생했습니다.' for non-search chat. Parked minors: speculative prep-/label-/train- step prefixes; switch re-run replaces old answer; sources without doc_id dropped.
Task T15: review 1 Needs fixes (badge never clears; stale stage_5.json copied; backup race untested). Fix round 1 dispatched, brief task-T15-fix1.md.
Frontend batch fix 1 dispatched (T17-T20 follow-ups), brief task-FE-fix1.md.
Task T15: fix 1 committed a240d62 (backend 1184 passed). Re-review dispatched.
FE fix 1: committed b846840 (vitest 192, lint, build ok). Re-review dispatched.
FE fix 1: re-review Approved. Task T17: complete (e1d923d, b846840). Task T18: complete (b1e9df2, b846840). Task T19: complete (8b2ed68, b846840). Task T20: complete (168f19f, b846840). Parked minors: PrepResult evidence label '' slots; no-sid loading text changed; hook tests don't mount real components (cover in QA).
Task T15: re-review fix 1 Approved. Task T15: complete (4612d36, a240d62). Parked: compare stage3 same=False when only stage_5 differs; runner.status refresh writes when db exists. ALL TASKS COMPLETE. Final whole-branch review next.
Final review 1: With fixes (5 Important). Rulings R-106..R-110 logged in decision-log. One fix dispatch (split backend/frontend in parallel): final-fix1.md, final-fix1-fe.md.
Final fix 1 committed e7dcf4f,35bc291 (backend 1216, vitest 213, lint, build ok). Scoped re-review dispatched.
Final fix re-review: Approved (15/15 addressed). Residual minors → backlog B-108. Final review clean.
Review phase: gstack 6 + Codex 7 findings → harness retry (phase build). Ruling R-111. Fix dispatch: review-fix1.md (backend), review-fix1-fe.md (frontend).
Review-phase fix committed d094401,eaf81a6 (backend 1244, vitest 221, lint, build ok). Scoped re-review dispatched.
Review-phase fix 1 re-review Approved; 1 Important (trainable count full scan per poll) → fix 2 dispatched with 2 minors. Parked: prep folder wipe for pre-fix manifests (dev data only); stage5 report read order; /preprocess error envelope change.
Review fix 2 re-review Approved. Review phase clean.
