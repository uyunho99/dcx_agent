# DCX 2.0 3~5단계 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 방식으로 Task 단위로 진행한다. 이 하네스에서 **구현 담당은 항상 Codex**(`codex:codex-rescue`, `--wait --fresh`, 쓰기 가능 작업)이고, Main Claude는 위임 · 결과 확인 · 리뷰만 한다. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 3단계(전처리 · 임베딩 한 벌) · 4단계(Jev · GPT 교차 라벨 · 불일치만 사람 검수 · 무작위 감사) · 5단계(멀티태스크 MLP 앙상블 · 모델 저장소)와 Known Insight · 로컬 RAG 검색을 설계(02-design)대로 만들고, LG 에어컨 fixture로 키 없이 3→5단계를 끝까지 돌게 한다.

**엔지니어링 리뷰 반영:** 문서 끝 "엔지니어링 리뷰" 절 · 결정 원장(2026-09-30)을 따른다. 증류는 이번 범위가 아니다(D1 → B-107).

**Architecture:** 백엔드에 새 패키지 `app/work`(긴 작업 워커) · `app/vectors` · `app/prep` · `app/label` · `app/model` · `app/known`을 추가한다. 비싼 결과(3단계 결과 · LLM 판정 캐시 · 모델)는 버전 밖 모듈에 두고 버전은 가리키기만 한다(D-078 · D-103 · D-120 · D-108). 프론트는 전처리 · 라벨링 · 학습 화면을 목업대로 새로 만들고 Known Insight 패널 · 근거 원문 카드를 붙인다.

**Tech Stack:** (0~2단계 그대로) Python 3.12 · FastAPI · Pydantic v2 · SQLite(WAL) · pytest / Next.js 16 · React 19 · Zustand 5 · Vitest + **추가** `kiwipiepy` · `torch`(CPU) · `numpy` · `httpx`(Jev) / **제거** `tensorflow` · `pinecone`

**Spec:** [`02-design-r2.md`](02-design-r2.md) (승인된 [`02-design.md`](02-design.md) + 계획 단계 사용자 결정, 아래 "설계 변경" 절) · [`01-brainstorm.md`](01-brainstorm.md) (AC-01~25) · [`decision-log.md`](decision-log.md) (D-100~139) · 목업 [`mockups/index.html`](mockups/index.html)

## 설계 변경 (계획 단계 사용자 결정, 승인된 02-design 대비)
이 계획의 "02-design n.m" 참조는 모두 `02-design-r2.md` 기준이다.

| 결정 | 승인된 설계(02-design) | 바뀐 것(02-design-r2 · 이 계획) |
|---|---|---|
| D-140 | 5.1 "단일 모델 만들기(증류)" | 이번에 만들지 않음(B-107) |
| D-143 | 4.2 `near_boundary` · 4.9 경계 사유 | 경계 사례 규칙 없음 |
| D-144 | 4.1 · 4.8 · 4.11 τ · α · α 패널 · `low_confidence` | 제외. 검수 큐 = 판정 실패 · 등급 불일치 |
| D-145 | 4.8 캘리브레이션 400건 · 탭 | 제외. 라벨러 성능 · 자기 일관성은 감사(첫 라운드 채택 1,000건)로 |
| O4 | 5.5 `classified/{sid}/relevant_{ts}.jsonl` | `classified/{sid}/{version}/relevant.jsonl` + `training.exportRef` |
| O5 | 2.5 판정 캐시 키 | `{qver}-{ctxKey}`(한줄 정의 · 질문 · 모델 해시) |

## Global Constraints
- 0~2단계 계획의 Global Constraints를 모두 이어받는다(Python 3.12 `backend/.venv`, 로컬 저장소, 키 값 비노출, 테스트는 네트워크 · 키 · codex 없이, UI 문구 규칙, 토큰, `NEXT_PUBLIC_INTERNAL_TOOLS`).
- 임베딩: `voyage-4`, `output_dimension=1024`, 입력 2,000자 절단, 128건 배치(D-129). 저장은 float16.
- Jev: `POST https://jevmodel.org/v1/systemone`, `Authorization: Bearer $JEVMODEL_API_KEY`, 요청 1회 = 문서 1건 = 질문 8개(D-116), `state` 직렬화 ≤ 8,000자, 키당 분당 120회, 재시도에 `Idempotency-Key: {doc_id}:{qver}`(D-111).
- GPT 라벨러 기본 백엔드는 `codex_exec`(`run_many`), 설정으로 `openai_api`(D-113). 0~2단계 과업의 기본값 `openai_api`는 바꾸지 않는다.
- 모든 라벨러 호출의 첫 줄은 0단계 `oneLiner`, 도메인 예시 없음(AC-11).
- 등급 규칙은 `app/label/rule.py` 한 곳. 프론트는 규칙을 다시 쓰지 않고 `POST /label/rule/preview`를 부른다(D-104).
- τ · α · 캘리브레이션은 이번 범위가 아니다(D-144 · D-145). 검수 큐 = 판정 실패 · 두 라벨러 등급 불일치(D-143). 감사: 채택 1,000건에서 첫 라운드, 이후 1만 건마다 50건, 라운드마다 re-issue 2건 · θ 0.85 · 분류 모델 컷 0.2/0.8 · 감시 1% · 괴리 경고 15% · 헤드 최소 표본 30 · κ 하한 0.75(02-design · 기획안 12절).
- RAG 검색은 로컬 벡터 검색 하나. Pinecone 코드 · 의존성 · 설정을 없앤다(D-121).
- 새 3~5단계 화면은 세션 통째 저장(`/save-session`)을 쓰지 않는다. `PATCH /session`(drafts) + 기능별 API만(이전 학습 `dcx-full-session-save`, 02-design 13절).
- 화면당 파란 주요 버튼 하나(D-137). 이미 아는 이야기 목록의 화면 이름은 "Known Insight"(D-135).
- 5단계 모델: 입력 1032 → LayerNorm → 512 GELU Dropout0.2 → 256 GELU Dropout0.2 → 헤드, MLP ×3 + 선형 ×1, AdamW 1e-3 · wd 1e-4 · 배치 256 · 최대 30 에폭 · 인내 3, 분할 80/10/10, 사람 샘플 가중치 3(D-130). 난수 시드는 모두 고정.

## Review Focus
1. **Jev 응답에 질문 하나가 빠지거나 확률 합이 1이 아닌 경우**(`relate_outcome` 확률 합 0.97 등)도 문서를 버리지 않는다. 합으로 정규화하고, 빠진 질문이 있으면 그 문서를 `bad` 격리 후 재시도한다 → T06 `test_jev_normalizes_choice_probs` · `test_jev_missing_answer_is_bad`.
2. **GPT 묶음 답에서 `doc_id`가 빠지거나 중복 · 남는 경우**(20건 묶음에 19건 · 21건) 묶음 전체를 불량 처리하지 않고, 맞는 항목만 받고 빠진 문서만 다시 큐에 넣는다 → T07 `test_gpt_partial_batch_requeues_missing`.
3. **검수 · 감사 도중 버전을 새로 만들거나 브라우저를 닫아도** 이미 제출한 판정은 남는다(한 건 = 한 행 즉시 커밋) → T11 `test_submit_is_durable_per_item`.
4. **벡터가 0벡터(임베딩 실패)이거나 3단계 벡터가 없는 옛 세션**에서 RAG · 학습 · 군집이 터지지 않는다. 0벡터는 검색 후보 · 학습셋에서 빠지고, 옛 세션 검색은 `no_vectors` 사유를 돌려준다 → T02 `test_search_skips_zero_vectors` · T14 `test_search_legacy_session_reason`.
5. **등급 불일치율이 높아 검수 큐가 수만 건일 때**(예: 318,204건 중 12% = 약 3.7만 건) 개요는 불일치율 · 예상 시간을 보여 주고, 큐 API는 한 번에 한 건만 돌려주며 전체 목록을 읽지 않는다 → T11 `test_queue_large_next_is_constant_time`(4만 행에서 `GET /next` 50ms 이내).

---

## 실행 규칙 (하네스)
- 계획 승인 후 기획 산출물을 `plan/dcx2-stage3-5`에 커밋하고 `development-harness worktree /Users/persona1/Desktop/dcx_agent-dcx2-stage3-5 feature/dcx2-stage3-5`로 구현 worktree를 만든다. 이후 그 안에서만 작업한다.
- Task 하나 = Codex 위임 하나. 위임문에 cwd · 소유 파일 · 이 문서의 해당 Task 발췌 · 수용 기준 · RED/GREEN 명령 · 보고서 경로(`docs/development/dcx2-stage3-5/reports/T##.md`)를 넣고, TDD 규칙(먼저 실패 확인 → 최소 구현 → 통과 → 리팩터 · 남의 변경 보존)을 직접 적는다.
- 파일 소유가 겹치는 Task는 순차로 한다. `backend/app/main.py`(라우터 등록)와 `backend/app/config.py`는 T01만 필드를 추가하고, 이후 라우터 등록은 T05 · T11 · T13 · T14가 순서대로 한다.
- 각 Task 뒤에 Claude가 명세 · 품질을 읽기 전용으로 리뷰하고, 수정은 같은 Task로 Codex에 재위임한다.
- 표기: `PYTEST` = `cd backend && .venv/bin/python -m pytest`, `VITEST` = `npm --prefix frontend test --`.

## 의존 관계 · 파일 소유

| Task | 이름 | 의존 | 소유 파일(생성 C / 수정 M / 삭제 D) |
|---|---|---|---|
| T01 | 의존성 · 설정 · 공용 워커 | – | M `backend/requirements.txt` `backend/app/config.py` `.env.example` `backend/app/crawl/{control,queue}.py` `backend/app/llm/codex_exec.py`(pid 확인만, R1) · C `backend/app/work/{__init__,proc,runner,worker,status}.py` `backend/tests/work/test_runner.py` `backend/tests/fakes/fake_worker.py` |
| T02 | 임베더 · 벡터 저장소 · 로컬 검색 | T01 | C `backend/app/vectors/{__init__,embedder,store,search}.py` `backend/tests/vectors/*` · M `backend/app/services/voyage.py` |
| T03 | 등급 규칙 | T01 | C `backend/app/label/{__init__,rule}.py` `backend/tests/label/test_rule.py` |
| T04 | 3단계 파이프라인 | T02 | C `backend/app/prep/{__init__,config,boilerplate,clean,tokens,pipeline,report}.py` `backend/app/prep/boilerplate.v1.json` `backend/tests/prep/*` · M `backend/app/services/preprocessing.py`(새 파이프라인 호출 + 호환 출력) |
| T05 | 3단계 API · 워커 연결 | T01 T04 | C `backend/app/routers/prep.py` `backend/tests/prep/test_prep_api.py` · M `backend/app/main.py` `backend/app/work/worker.py`(kind `prep`) |
| T06 | 라벨 스키마 · 질문 · Jev 클라이언트 | T03 | C `backend/app/label/{schema,questions,jev}.py` `backend/app/label/questions.q1.json` `backend/tests/label/test_jev.py` `backend/tests/fakes/fake_jev.py` `backend/tests/fixtures/jev/*.json` |
| T07 | GPT 라벨러 | T06 | C `backend/app/label/gpt.py` `backend/app/label/prompts/gpt_label.q1.md` `backend/tests/label/test_gpt.py` · M `backend/tests/fakes/fake_codex.py`(라벨 묶음 응답) |
| T08 | 판정 캐시 · 판정 워커 | T01 T06 T07 | C `backend/app/label/{votes,judge}.py` `backend/tests/label/test_judge.py` `test_judge_resume.py` · M `backend/app/work/worker.py`(kind `judge`) |
| T09 | 합치기 · confidence · labels.sqlite | T03 T08 | C `backend/app/label/{store,merge}.py` `backend/tests/label/test_merge.py` |
| T10 | 감사 통계 | T09 | C `backend/app/label/audit.py` `backend/tests/label/test_audit.py` |
| T11 | 라우팅 · 큐 · 라벨 API | T05 T10 | C `backend/app/label/{route,overview,report}.py` `backend/app/routers/labeling_v2.py` `backend/tests/label/test_route.py` `test_label_api.py` · M `backend/app/main.py` · D `backend/app/routers/labeling.py`의 `/sample`(새 세션 미사용, 옛 세션 열람은 유지) |
| T12 | 멀티태스크 MLP 앙상블 학습 | T02 T09 | C `backend/app/model/{__init__,features,net,train,calibrate}.py` `backend/tests/model/test_net.py` `test_train.py` |
| T13 | 모델 저장소 · 추론 · 내보내기 · 분류 모델 구간 | T11 T12 | C `backend/app/model/{registry,infer,export,monitor}.py` `backend/app/routers/training_v2.py` `backend/tests/model/test_registry.py` `test_infer.py` `test_export.py` `test_model_mode.py` · M `backend/app/main.py` `backend/app/work/worker.py`(kind `train` `infer` `monitor`) · D `backend/app/services/training.py`의 TF · sklearn 3모델 경로(옛 세션용 결과 읽기만 남김) |
| T14 | Known Insight · 로컬 RAG · 6/6.5단계 연결 | T02 T13 | C `backend/app/known/{__init__,models,store,filter}.py` `backend/app/routers/known.py` `backend/tests/known/*` · M `backend/app/services/pinecone_svc.py`→D(대체 `app/vectors/search.py`) `backend/app/routers/{chat,search}.py` `backend/app/services/{personas,clustering,embedding}.py` `backend/app/models/schemas.py`(`novel`) `backend/app/main.py` `backend/app/context/models.py`(knownInsights 읽기 호환) |
| T15 | 버전 · 활동 배지 · 통합 테스트 | T05 T11 T13 T14 | M `backend/app/routers/sessions.py`(서버 소유 칸 추가) `backend/app/context/{versions,store}.py`(restartFrom stage3~5, 워커 실행 중 차단, stage3+ 비교) · C `backend/tests/test_integration_stage3_5.py` `backend/tests/context/test_versions_stage3_5.py` |
| T16 | 프론트 공용 컴포넌트 · API 클라이언트 | T05 T11 T13 T14 | C `frontend/src/components/label/{TagToggle,LevelBadge,LabelerProgress,KappaTable,QueueCard}.tsx` `frontend/src/components/known/{KnownInsightsDrawer,SourceCard}.tsx` `frontend/src/lib/api/{prep,label,train,known}.ts` `frontend/src/lib/logic/{nowCard,labelKeys}.ts` + `.test.ts` · M `frontend/src/lib/types.ts` |
| T17 | 3단계 화면 | T16 | M `frontend/src/app/pipeline/preprocess/page.tsx` · C `frontend/src/components/prep/*` |
| T18 | 라벨링 화면 | T16 | M `frontend/src/app/pipeline/labeling/page.tsx` · C `frontend/src/components/label/{Overview,Queue,Audit}.tsx` |
| T19 | 학습 화면 · 모델 저장소 | T16 | M `frontend/src/app/pipeline/training/page.tsx` · C `frontend/src/components/train/*` |
| T20 | Known Insight 패널 · 근거 원문 · 셸 | T16 | M `frontend/src/app/pipeline/layout.tsx` `frontend/src/components/ChatPanel.tsx` `frontend/src/components/StepBar.tsx`(step 이름) `frontend/src/components/SessionList.tsx`(배지 문구) |

병렬 가능 묶음: {T02, T03} → {T04, T06} → {T05, T07} → {T08} → {T09} → {T10, T12} → {T11} → {T13} → {T14} → {T15, T16} → {T17, T18, T19, T20}. `backend/app/main.py`는 T05 → T11 → T13 → T14 순차.

---

## M0 · 기반

### Task T01: 의존성 · 설정 · 공용 워커

**Interfaces:**
- `app/config.py` `Settings` 추가(env = 대문자): `embed_backend="voyage"`(`voyage|fake`), `embed_model="voyage-4"`, `embed_dim=1024`, `jev_api_keys: list[str]=[]`(env `JEVMODEL_API_KEY`, 쉼표로 여러 개), `jev_model="jev-latest"`, `jev_rate_per_min=120`, `jev_backend="http"`(`http|fake`), `label_gpt_backend="codex_exec"`(`codex_exec|openai_api|fake`), `label_batch_size=20`, `label_concurrency=4`, `known_theta=0.85`, `model_cut_low=0.2`, `model_cut_high=0.8`, `monitor_rate=0.01`, `monitor_warn=0.15`, `head_min_samples=30`, `audit_first=1000`, `audit_every=10000`, `audit_size=50`, `audit_reissue=2`, `kappa_floor=0.75`. 삭제: `pinecone_api_key`.
- `app/work/runner.py`:
  - `def start(sid: str, version: str, kind: str, args: dict) -> dict` — 실행 키 = `(sid, version, kind, args.get("labeler"))`(외부 의견 O1). 같은 키가 살아 있으면 기존 run을 돌려주고, 아니면 `python -m app.work.worker {kind} --sid --version --args-json` 을 `start_new_session=True`로 띄운다. 확인과 등록은 `data/work/{sid}/runs.sqlite`의 `BEGIN IMMEDIATE` 하나(0~2단계 D-072 규칙).
  - `def status(sid: str) -> list[dict]` — `{kind, runId, state: running|interrupted|paused|done|failed, progress, detail, heartbeatAt, error}`. pid 생존 + heartbeat 60초 규칙.
  - `def request(sid, run_id, action: Literal["pause","resume","stop"]) -> dict`.
- `app/work/worker.py`: `KINDS: dict[str, Callable[[Context], None]]` 등록표. `Context`는 `heartbeat(progress, detail)`, `should_pause()`, `should_stop()`를 가진다. 10초 heartbeat.

- [ ] **Step 1: 실패 테스트** `tests/work/test_runner.py`
  - `test_double_start_spawns_one` — 가짜 kind(`tests/fakes/fake_worker.py`, 3초 잠)로 `start` 두 번 동시 호출 → 프로세스 1개, 같은 runId.
  - `test_killed_worker_is_interrupted` — SIGKILL 후 `status` → `interrupted`.
  - `test_two_labelers_run_independently` — `judge`(labeler=jev) · `judge`(labeler=gpt)가 각각 뜨고 따로 일시 정지된다(O1)
  - `test_pause_resume` — `request(pause)` → 다음 heartbeat에서 `paused`, `resume` → `running`.
  - `test_pid_alive_rejects_nonpositive` (`tests/work/test_proc.py`, R1) — `pid_alive(0) is False`, `pid_alive(-1) is False`, `pid_alive(os.getpid()) is True`; 기존 세 곳이 이 함수를 쓴다.
  - `test_settings_defaults` — `Settings().embed_model == "voyage-4"`, `jev_rate_per_min == 120`, `hasattr(Settings(), "pinecone_api_key") is False`.
- [ ] **Step 2: RED** `PYTEST tests/work -q` → ImportError.
- [ ] **Step 3: 구현.** `requirements.txt`: `+ kiwipiepy torch numpy scipy`, `- tensorflow pinecone`(해당 줄이 있으면). `.env.example`에 새 env 이름만(값 없음).
- [ ] **Step 4: 설치** 구현 worktree에는 `backend/.venv`가 없다(git 제외). `python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt && npm --prefix frontend ci` 후 기준 검사(검증 명령 4개)를 먼저 통과시킨다.
- [ ] **Step 5: GREEN** `PYTEST tests/work -q` → passed. 기존 전체 `PYTEST -q` 회귀 없음.
- [ ] **Step 6:** 커밋 `feat(work): 공용 긴 작업 워커, 3~5단계 설정, torch·kiwi 추가·tensorflow·pinecone 제거`.

### Task T02: 임베더 · 벡터 저장소 · 로컬 검색

**Interfaces:**
- `app/vectors/embedder.py`: `class Embedder(Protocol): name: str; model: str; dim: int; def embed(self, texts: list[str]) -> np.ndarray  # float32 [n,dim], 실패 행은 0`. `VoyageEmbedder`(키 없으면 `EmbedderUnconnected` 예외) · `FakeEmbedder`(sha256 시드 정규분포, L2 정규화). `def get_embedder() -> Embedder`.
- `app/vectors/store.py`: `class VectorStore(root: Path)` — `write_shard(ids: list[str], vecs: np.ndarray, failed: list[bool]) -> None`(10,000행 단위 `vectors/shard-{n:05d}.f16` + `ids.jsonl` 추가, `fsync` 뒤 기록), `get(doc_ids) -> tuple[list[str], np.ndarray]`(없는 id 제외), `iter_shards() -> Iterator[tuple[list[str], np.ndarray, np.ndarray]]`(ids, vecs float32, failed mask), `count() -> int`, `done_shards() -> int`.
- `app/vectors/search.py`: `def cosine_topk(store, queries: np.ndarray, top_k: int, allow: set[str] | None, exclude: set[str]) -> list[list[tuple[str, float]]]` — 샤드별 행렬곱, 0벡터 제외, 여러 질의 한 번에.
- 검색은 샤드를 `np.memmap`으로 열고 프로세스 안에 캐시한다(같은 prepKey면 다시 읽지 않음, 엔지니어링 리뷰 F7).
- `services/voyage.py`: 모델 `voyage-4`, `output_dimension=settings.embed_dim`.

- [ ] **실패 테스트** `tests/vectors/test_store.py` · `test_search.py` · `test_embedder.py`
  - `test_fake_embedder_deterministic` — 같은 글 → 같은 벡터, 노름 1.
  - `test_store_roundtrip_float16` — 25,000행 쓰기 → 샤드 3개, `get` 순서 보존, 오차 < 1e-3.
  - `test_search_skips_zero_vectors` — 0벡터 행은 결과에 없다(Review Focus 4).
  - `test_search_batch_queries` — 질의 3개 → 결과 3줄, `allow`/`exclude` 적용.
  - `test_voyage_request_model` — 모의 클라이언트 호출 인자 `model="voyage-4"`, `output_dimension=1024`.
- [ ] **RED** `PYTEST tests/vectors -q` → ImportError. **구현** → **GREEN** passed.
- [ ] 커밋 `feat(vectors): voyage-4 임베더·float16 샤드 저장소·로컬 코사인 검색`.

### Task T03: 등급 규칙 (경계 사례 규칙 없음, D-143)

**Interfaces (`app/label/rule.py`):**
- `SEM = ("sense","feel","think","act","relate","outcome")`, `GRADE_FIELDS = ("anchor",) + SEM + ("situation",)`, `RULE_VERSION = "r1"`.
- `def grade(tags: dict) -> Literal["core","supporting","non"]`
- `def grade_probs(p: dict[str, float]) -> dict[str, float]` — 02-design 4.2 공식, 6개 베르누이 DP.
- 경계 사례 판정 함수는 두지 않는다(R2 · D-143).

- [ ] **실패 테스트** `tests/label/test_rule.py`
  - `test_plan_table` — 기획안 6절 6행(분유 온도 → core · "좀 시끄럽긴" → supporting · "짜증나서 껐다" → core · "완전 좋아요" → non · "그냥 쓰레기" → non · "특가 링크" anchor 0 → non).
  - `test_grade_probs_sum_one` · `test_grade_probs_matches_montecarlo`(1e5 샘플, 오차 < 0.01) · `test_grade_probs_worked_example` — 02-design 예시 확률 → core ≈ 0.67, supporting ≈ 0.27(±0.01).
- [ ] **RED → 구현 → GREEN** `PYTEST tests/label/test_rule.py -q`.
- [ ] 커밋 `feat(label): 등급 규칙 r1 (Core·Supporting·Non, 확률)`.

---

## M1 · 3단계

### Task T04: 3단계 파이프라인

**Interfaces:**
- `app/prep/config.py`: `class PrepConfig(BaseModel)` — 02-design 3.1 필드(`adFilter` · `excludeSources` · `minBodyChars=10` · `boilerplate: dict[str, list[str]]` · `analyzer="kiwi"` · `tokenPos=["NNG","NNP","VV","VA","XR"]` · `embedder` · `embedModel` · `embedDim`). `def prep_key(collection_id: str, cfg: PrepConfig, embedder: Embedder) -> str` = `"p_" + sha256(정규화 JSON)[:12]`(분석기 버전 포함).
- `app/prep/clean.py`: `def clean_html(text) -> str`, `def strip_boilerplate(text, phrases) -> tuple[str, int]`, `def token_text(text) -> str`(문장부호 · 특수문자 삭제).
- `app/prep/tokens.py`: `def tokenize(text, pos) -> list[str]`(Kiwi).
- `app/prep/pipeline.py`: `def run_prep(ctx, sid: str, version: str) -> Path` — 02-design 3.2 순서 1~6, 샤드 단위 진행 기록(`manifest.json.progress`), 이미 끝난 샤드 건너뜀, 결과 폴더 `data/derived/{sid}/{collectionId}/{prepKey}/`. 같은 `prepKey` 폴더가 `status=done`이면 즉시 반환.
- `app/prep/report.py`: `def stage3_report(...) -> dict` — 02-design 3.5 필드 그대로.
- `services/preprocessing.py`: 새 세션이면 `run_prep`을 부르고 `preprocessed/{sid}/{ts}.jsonl`에도 같은 문서를 쓴다(뒤 단계 호환). 옛 세션은 기존 경로.

- [ ] **실패 테스트** `tests/prep/`
  - `test_filters_use_body` · `test_no_target_word_filter`("육아맘" 들어간 글이 남는다) (AC-01)
  - `test_boilerplate_removed_counted` — 카페 가입 안내 문구가 본문 · 댓글에서 지워지고 건수가 센다 (AC-02)
  - `test_two_paths` — 같은 문서의 토큰 입력엔 `?`·`!`가 없고, 임베딩 입력 · `docs/` 본문엔 남는다 (AC-03)
  - `test_tokens_written` — `tokens/part-00001.jsonl`에 `{doc_id, tokens}` (AC-04)
  - `test_prep_key_reuse` — 같은 수집본 · 설정 두 번 실행 → 임베더 호출 1회 (AC-06)
  - `test_embed_failure_zero_vector` — 가짜 임베더가 한 배치 3회 실패 → 0벡터 + `embed_failed_zero_vector` (AC-07)
  - `test_resume_skips_done_shards` — 샤드 2개 끝난 뒤 중단 → 재실행 시 3번째부터
  - `test_stage3_report_contract` — 필드 전부 존재 (AC-20 일부)
- [ ] **RED → 구현 → GREEN** `PYTEST tests/prep -q`, 기존 `tests/test_integration_stage0_2.py` 회귀 없음.
- [ ] 커밋 `feat(prep): 3단계 규칙·정형 문구·두 갈래 정제·Kiwi 토큰·임베딩 한 벌·stage_3.json`.

### Task T05: 3단계 API · 워커 연결
- `PUT /prep/{sid}/config` · `POST /prep/{sid}/run` · `GET /prep/{sid}/status`(02-design 8절). 세션 `prep.{config,derivedRef,status,savedAt}`를 `update_session`으로 부분 저장.
- [ ] **실패 테스트** `test_prep_api.py`: `test_run_then_status_done`(fixture 수집본 + 가짜 임베더 → 결과 `stage3`), `test_reuse_returns_done_immediately`, `test_embed_unconnected_stops_with_reason`(voyage 키 없음 → `failed` + `kind="embedder_unconnected"`), `test_legacy_session_rejected`.
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(prep): 3단계 API·워커 연결`.

---

## M2 · 4단계 라벨러

### Task T06: 라벨 스키마 · 질문 · Jev 클라이언트

**Interfaces:**
- `app/label/schema.py`: `class Tags(BaseModel)`(anchor · sem · situation · reason_code · signal), `class Label(BaseModel)`(02-design 2.3 전부).
- `app/label/questions.py`: `QVER = "q1"`, `def load_questions() -> dict`(q1 json: 필드별 `instructions` ≤ 1,800자, 선택지), `def jev_questions(one_liner) -> dict` — 질문 8개(D-116 표).
- `app/label/jev.py`: `class JevClient(keys, model, transport=None)` — `def judge(doc: dict, one_liner: str) -> JevVote`. `JevVote = {probs: {anchor, sense, feel, think, act, relate, outcome, situation}, reason_probs: {ad, no_needs, pure_criticism, other, not_non}, model, truncated}`. `def build_state(doc, one_liner) -> tuple[str, bool]`(8,000자, 댓글 → 본문 끝 순 절단). 오류 매핑: 401 `unconnected` · 402 `insufficient` · 422 `bad` · 429/502 백오프(최대 5회).

- [ ] **실패 테스트** `tests/label/test_jev.py`(`httpx.MockTransport` + `tests/fixtures/jev/*.json`)
  - `test_request_shape` — 질문 이름 8개 · `model` · `Authorization` · `Idempotency-Key="{doc_id}:q1"`, `state` 첫 줄 `[맥락] {oneLiner}` (AC-09 · AC-11)
  - `test_relate_outcome_recovered` — `{none:.1, relate:.2, outcome:.6, both:.1}` → relate 0.3 · outcome 0.7
  - `test_jev_normalizes_choice_probs` · `test_jev_missing_answer_is_bad` (Review Focus 1)
  - `test_state_truncation` — 12,000자 문서 → 직렬화 ≤ 8,000, `truncated=True`
  - `test_error_mapping` — 401/402/422/429→성공/502→성공
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(label): 라벨 스키마·질문 q1·Jev 클라이언트`.

### Task T07: GPT 라벨러
- `app/label/gpt.py`: `def build_task(docs: list[dict], one_liner: str) -> LLMTask`(task `label_gpt`, 출력 스키마 `GptBatch{items: list[GptItem]}`), `def judge_batch(docs, one_liner) -> tuple[dict[str, GptVote], list[str]]` — (받은 표, 다시 넣을 doc_id 목록). `run_many`의 실행 ID는 묶음마다 `lbl-{sid}-{qver}-{ctxKey}-{sha256(정렬된 doc_id)[:12]}`로 만든다. 같은 묶음을 다시 돌리면 같은 ID(이어 하기), 빠진 문서만 다시 넣으면 새 묶음 = 새 ID(외부 의견 O6, `codex_exec.py:137` 입력 고정 규칙). 백엔드는 `settings.label_gpt_backend`(`codex_exec`면 `run_many`).
- 프롬프트 `prompts/gpt_label.q1.md`: 첫 줄 `{one_liner}` → 태그 정의(questions.q1과 같은 원문) → 문서 묶음(`doc_id` 포함) → 출력 형식. `signal`은 Core · Supporting 조건을 6차원 태그로 먼저 판단한 뒤 고르게 한다.
- [ ] **실패 테스트** `test_gpt.py`: `test_prompt_first_line_is_one_liner` · `test_no_domain_examples`(템플릿 파일 `gpt_label.q1.md`와 `questions.q1.json`에 도메인 명사 목록 `에어컨 · 보험 · 청소기 · 분유` 없음, AC-11) · `test_gpt_partial_batch_requeues_missing`(Review Focus 2) · `test_two_batches_then_retry_real_run_many`(가짜 codex로 연속 두 묶음 + 부분 응답 후 재시도가 `run_many` 입력 고정 오류 없이 끝난다, O6) · `test_codex_backend_used_by_default` · `test_usage_limit_pauses`(가짜 codex가 사용량 한도 메시지 → `LabelerPaused`).
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(label): GPT 라벨러(codex_exec 기본, 묶음 판정, 빠진 문서 재큐)`.

### Task T08: 판정 캐시 · 판정 워커
- `app/label/votes.py`: `class VoteCache(root)` — `votes.sqlite` 02-design 2.5 스키마, `seed(doc_ids)`, `lease(n, run_id) -> list[str]`, `put(doc_id, payload)`, `mark_bad(doc_id, reason)`, `counts() -> {pending, done, bad}`, 죽은 lease 회수. 경로 = `data/judge/{sid}/{prepKey}/{labeler}/{qver}-{ctxKey}/`, `ctxKey = sha256(oneLiner + 질문 원문 + 라벨러 모델 · 백엔드)[:8]`. Jev `Idempotency-Key`도 `{doc_id}:{qver}-{ctxKey}`(외부 의견 O5). 0단계 한줄 정의를 바꾸면 새 캐시가 생기고 개요에 "판정 맥락이 바뀌어 다시 판정합니다"가 뜬다.
- `app/label/judge.py`: kind `judge` 본문 — labeler `jev`(요청 1건씩, 키별 제한기) · `gpt`(묶음). 402 · 사용량 한도 → `ctx` paused + 사유. 예상 완료 · 예상 Jev 토큰(ceil(len/4)) 계산 `def estimate(...)`.
- [ ] **실패 테스트** `test_judge.py` · `test_judge_resume.py`
  - `test_both_labelers_fill_cache` (가짜 Jev · 가짜 codex)
  - `test_kill_restart_no_duplicate_calls` — 100건 중 40건 뒤 SIGKILL → 재시작 → 가짜 Jev 호출 총 100회 (AC-10)
  - `test_one_liner_change_new_cache` — `oneLiner`를 바꾸면 새 캐시 경로, 이전 표를 쓰지 않는다(O5)
  - `test_cache_shared_across_versions` — 새 버전이 같은 캐시를 가리키고 호출 0회 (D-120)
  - `test_rate_limit_respected` — 가짜 시계로 분당 120 초과 없음
  - `test_insufficient_credit_pauses`
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(label): 판정 캐시(버전 밖 모듈)·판정 워커·이어 하기`.

---

## M3 · 4단계 라우팅 · 감사

### Task T09: 합치기 · confidence · labels.sqlite
- `app/label/store.py`: `class LabelStore(version_dir)` — 02-design 2.4 테이블(`final` · `human` · `audit_set` · `queue`), `submit(doc_id, labeler, mode, tags)`는 한 행 즉시 커밋.
- `rebuild_final`은 두 표가 모두 생긴 문서만 증분으로 합친다. 전체 재계산은 `rule_version` · `qver`가 바뀔 때만(엔지니어링 리뷰 F6).
- `app/label/merge.py`: `def merge(jev: JevVote, gpt: GptVote) -> MergedLabel` — 02-design 4.7(같으면 그 값, 다르면 Jev, `signal`은 GPT, `confidence` = 일치 수/8 × min(max(p,1−p)), `grade_mismatch`). `def rebuild_final(store, jev_cache, gpt_cache)`.
- [ ] **실패 테스트** `test_merge.py`: `test_agree_confidence`(8/8 · 최소 0.9 → 0.9) · `test_disagree_takes_jev_and_flags` · `test_grade_mismatch` · `test_signal_from_gpt_only` · `test_waits_until_both`.
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(label): 두 라벨러 합치기·confidence·labels.sqlite`.

### Task T10: 감사 통계 (D-145)
- `app/label/audit.py`: `def maybe_new_round(store, accepted_count) -> int | None`(채택 1,000건에서 첫 라운드, 이후 1만 건마다, 채택분 무작위 50건, 시드 고정), `def reissue_items(store, round) -> list[str]`(이전 감사 문서 2건), `def kappa_ai(store, round) -> dict`(필드별 · 등급), `def labeler_accuracy(store) -> dict`(감사 정답 누적 대비 Jev · GPT 필드별 정확도 · κ, `relate` · `outcome` 따로, 표본 수 `n`), `def self_consistency(store) -> dict`, `def definition_signal(history) -> {needed, reason}`(κ_AI 등급 두 라운드 연속 하락 ∧ < 0.75). 감사 사람 값이 채택 라벨과 다르면 `final`을 사람 값으로(`source=human`).
- [ ] **실패 테스트** `test_audit.py`
  - `test_first_round_at_1000_then_every_10k` · `test_round_samples_accepted_only`
  - `test_reissue_two_per_round` · `test_self_consistency`
  - `test_labeler_accuracy_from_audit` — 감사 정답 100건 고정 → Jev · GPT 정확도 기대값, `relate` · `outcome` 분리
  - `test_definition_signal` (AC-15)
  - `test_audit_override_sets_human`
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(label): 감사 라운드·라벨러 정확도·자기 일관성·정의 점검 신호`.

### Task T11: 라우팅 · 큐 · 감사 · 라벨 API
- `app/label/route.py`: `def route(label) -> str`(02-design 4.9: `labeler_failed` → `grade_mismatch` → `accepted`), `def rebuild_queue(store)`. 판정 캐시에서 재시도를 다 쓴 `bad` 문서(어느 라벨러든)는 합치기를 기다리지 않고 `labeler_failed`로 바로 큐에 넣는다(외부 의견 O7).
- `app/label/overview.py`: `def overview(sid) -> dict`(진행 · 예상 · 분포 · 불일치율 · 라벨러 성능(T10) · 큐 사유별 · `lastSeenAt` 이후 변화).
- `app/label/report.py`: `def label_part(sid) -> dict` — `stage_5.json`의 라벨 부분만 돌려준다. 파일은 T13 `export.write_stage5`만 쓴다(엔지니어링 리뷰 F5).
- `routers/labeling_v2.py`: 02-design 8절 `/label/*` 전부. `POST /label/{sid}/start` = 두 판정 워커 시작(D-136). `POST /label/{sid}/mode`는 시작 뒤 409(D-139).
- [ ] **실패 테스트** `test_route.py` · `test_audit.py` · `test_label_api.py`
  - `test_failed_doc_reaches_queue` — Jev가 3회 실패한 문서가 큐에 `labeler_failed`로 오고 사람 제출로 `final`에 들어간다(O7)
  - `test_route_order` — 사유는 `labeler_failed` → `grade_mismatch` 두 가지뿐, 등급이 같으면 채택(AC-13, R2 · R3)
  - `test_queue_large_next_is_constant_time` (Review Focus 5)
  - `test_submit_is_durable_per_item` (Review Focus 3, AC-14)
  - `test_next_hides_votes_until_submit` — `GET /next` 응답에 `votes` 없음, `submit` 응답에만 비교 (AC-14)
  - `test_legacy_label_reads_as_anchor` (AC-16)
  - `test_mode_locked_after_start`
  - `test_rule_preview` — `POST /label/rule/preview` = `rule.grade` 결과 (AC-08)
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(label): 라우팅·검수 큐·라벨 API`.

---

## M4 · 5단계

### Task T12: 멀티태스크 MLP 앙상블 학습
- `app/model/features.py`: `def build_features(docs, vectors) -> np.ndarray [n,1032]`(Voyage 1024 + 채널 원-핫 5 순서 `naver_cafe,naver_blog,youtube,ppomppu,clien` + log1p(본문 글자) + 스니펫 + Jev 잘림).
- `app/model/net.py`: `class MultiHeadMLP(nn.Module)`(D-130 구조, `linear=True`면 몸통 없음), `def masked_loss(out, targets, masks, weights, pos_weight) -> Tensor`.
- `app/model/train.py`: `def build_targets(final_rows, jev_cache) -> Targets`(소프트 라벨 규칙 D-130), `def train_member(X, T, seed, bootstrap, linear) -> state_dict`, `def train_ensemble(...) -> EnsembleResult{members, metrics, perHead}`. 헤드 표본 < 30이면 제외 표시.
- `app/model/calibrate.py`: `def fit_temperature(logits, y) -> float`(보정셋, LBFGS 1개 파라미터).
- [ ] **실패 테스트** `tests/model/test_net.py` · `test_train.py`(합성: 태그별 방향이 다른 가우시안 벡터 3,000건)
  - `test_forward_shapes` — anchor 1 · sem 6 · situation 1 · signal 5 · reason 4
  - `test_mask_zero_grad` — anchor=0 문서의 sem 목표를 바꿔도 기울기 동일
  - `test_soft_targets` — 합의분 목표 = (Jev p + GPT 0/1)/2, 사람 가중치 3
  - `test_ensemble_learns_synthetic` — 헤드별 F1 ≥ 0.9, 멤버 4개
  - `test_temperature_reduces_ece`
  - `test_one_dim_doc_is_supporting_and_trained` — 6차원 1개 문서가 Supporting으로 학습셋에 들어간다(R2)
  - `test_head_min_samples` — signal 18건 → 미학습 표시
  - `test_seed_reproducible`
- [ ] **RED → 구현 → GREEN** `PYTEST tests/model -q`(CPU, 60초 이내) → 커밋 `feat(model): 멀티태스크 MLP 앙상블·마스크 손실·소프트 라벨·temperature`.

### Task T13: 모델 저장소 · 추론 · 내보내기 · 분류 모델 구간
- `registry.py`: `save(result, meta) -> model_id`, `list_models(embedder) -> list[dict]`(임베더 다르면 `selectable=False` + 이유), `load(model_id)`.
- `infer.py`: `def predict(model, X) -> Pred{tagProbs, gradeProbs, level, confidence, predEntropy, relevanceScore, memberDisagree}`(규칙 변경 시 저장된 tagProbs로 재계산만, AC-17).
- 증류(단일 모델 만들기)는 이번에 만들지 않는다(엔지니어링 리뷰 D1 → B-107). `meta.json`의 `kind`는 `"ensemble"`만 쓰되 필드는 남긴다.
- `export.py`: `classified/{sid}/{version}/relevant.jsonl`(Core + Supporting) · `all.jsonl` + `stage_5.json`, 세션 `training.exportRef`에 경로를 저장한다(D-109, 02-design 5.5 · 5.6). 로컬 로더는 `classified/{sid}/relevant_` 같은 접두사를 파일로 찾지 못해 빈 목록을 돌려주므로(`services/s3.py:28` `target = base if base.is_dir() else base.parent`, 없으면 `return all_data`) 접두사 경로를 쓰지 않는다(외부 의견 O4). 모델 없이 내보내기(D-126) 지원.
- `monitor.py`: 분류 모델 구간 1% 재판정(같은 판정 캐시) · 괴리율.
- `routers/training_v2.py`: `/train/*` · `/models/*`. mode=model이면 4단계 `start`가 `infer` 워커를 띄우고 0.2/0.8 컷 + `model_disagree` 라우팅.
- [ ] **실패 테스트** `test_registry.py` · `test_infer.py` · `test_export.py` · `test_model_mode.py`
  - `test_rule_change_no_retrain` (AC-17) · `test_registry_embedder_mismatch_not_selectable`
  - `test_model_mode_zero_llm_calls` — 새 세션이 모델 선택 → 4 · 5단계 끝까지 가짜 Jev · codex 호출 0회(감시 1% 제외 설정 시) (AC-18)
  - `test_model_disagree_routed` · `test_monitor_divergence_warn`
  - `test_export_relevant_contract` — 기존 `services/clustering.py`가 읽는 필드 + 새 필드 (AC-19 · AC-20)
  - `test_export_without_model`
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(model): 모델 저장소·추론·5단계 내보내기·분류 모델 구간`.

---

## M5 · 공통 · 통합

### Task T14: Known Insight · 로컬 RAG · 6/6.5단계 연결
- `app/known/models.py`: `KnownInsight`(02-design 2.6), `def read_known(session) -> list[KnownInsight]`(옛 `string[]`은 statement).
- `app/known/store.py`: CRUD + 문장 임베딩(`known_vectors.f16`) + 새 세션 생성 시 같은 `bk` 이전 세션 statement 복사(`from=prev_session`).
- `app/known/filter.py` + `app/vectors/search.py` 사용: `def search_docs(sid, queries: list[str], top_k, novel=True) -> SearchResult{items, reason}` — 활성 버전의 Core + Supporting만, ⓐ doc_id 제외 ⓑ 최대 코사인 ≥ θ 제외, 후보 `top_k×3`. 사유: `no_vectors` · `no_labels` · `all_known` · `embedder_unconnected`.
- `services/pinecone_svc.py` 삭제, 호출부(`routers/chat.py` 2곳 · `routers/search.py` · `services/personas.py`)를 `search_docs`로. 페르소나는 군집별 질의를 한 번에 묶는다.
- `services/clustering.py`: 새 세션은 `training.exportRef`의 `relevant.jsonl`만 읽고(없으면 "5단계 결과가 없습니다" 오류, 전처리 전체로 넘어가지 않음), 벡터는 저장소에서 읽는다(O4). 옛 세션은 기존 경로. `services/embedding.py`: 새 세션은 즉시 `done`("3단계 벡터 사용").
- [ ] **실패 테스트** `tests/known/`
  - `test_statement_and_doc_excluded` · `test_toggle_off_returns_all` · `test_theta_similarity_cut` (AC-21)
  - `test_search_legacy_session_reason` (Review Focus 4)
  - `test_prev_session_statements_copied`
  - `test_clustering_reads_store_no_embed_calls` — 가짜 임베더 호출 0회 (AC-05)
  - `test_clustering_input_is_core_supporting_only` — 군집 입력 doc_id 집합 = 내보낸 Core + Supporting 집합, Non 없음(O4)
  - `test_no_pinecone_import` — `import app.main` 뒤 `"pinecone" not in sys.modules`
- [ ] **RED → 구현 → GREEN** → 커밋 `feat(known): Known Insight·로컬 RAG 검색·Pinecone 제거·6/6.5단계 벡터 재사용`.

### Task T15: 버전 · 활동 배지 · 통합 테스트
- `context/versions.py`: 버전 복사에서 `*.sqlite`는 `sqlite3` 백업 API로 복사한다(F4). `restartFrom` `stage3|stage4|stage5` 처리 — stage3: `prep` stale(같은 규칙이면 재사용), stage4: `labels.sqlite`의 `final` · `queue` stale · `human` 유지 · 판정 캐시 그대로, stage5: `training` stale. `prep`/`judge`/`train`/`infer` 실행 중이면 새 버전 409(일시 정지 `judge`는 허용). `compare(stage=stage3|4|5)`: stage_3/stage_5 수치 나란히.
- `context/store.py` `session_activities`: `app/work/runner.status` 포함 → 배지 "판정 62%" · "학습 중" · "중단됨 · 이어서 진행".
- [ ] **실패 테스트** `tests/context/test_versions_stage3_5.py`(위 규칙 각각) · `tests/test_integration_stage3_5.py`
  - `test_end_to_end_fixture` — fixture 수집본 → 3단계(가짜 임베더) → `label/start` → 가짜 Jev · codex 판정 → 큐 제출(가짜 사람 = 고정 정답) → 감사 1라운드 → 학습(작은 에폭) → 내보내기 → 6단계 군집이 벡터 저장소로 돈다. 외부 네트워크 0회. (AC-22 · AC-23의 백엔드 부분)
  - `test_restart_stage4_reuses_cache` — 새 버전에서 Jev 호출 0회 (AC-22)
  - `test_version_copy_sqlite_consistent` — 사람 제출이 진행 중인 `labels.sqlite`를 새 버전으로 복사해도 복사본 `PRAGMA integrity_check == ok`이고 행 수가 복사 시점과 같다(`sqlite3` 백업 API 사용, 엔지니어링 리뷰 F4)
  - `test_save_session_keeps_stage3_5_keys` — 옛 화면의 `/save-session`이 `prep` · `labeling` · `training`을 덮어쓰지 않는다(엔지니어링 리뷰 F1)
- [ ] **RED → 구현 → GREEN** → 커밋 `feat: 3~5단계 버전 규칙·활동 배지·통합 테스트`.

---

## 프론트엔드 (T16~T20)

### Task T16: 공용 컴포넌트 · API 클라이언트 · 로직
- `lib/logic/nowCard.ts`: `function pickNowCard(o: Overview): {kind, title, body, action?: {label, target}}` — 02-design 4.11 우선순위 6단계 + 시작 전 상태.
- `lib/logic/labelKeys.ts`: `function keyAction(e: KeyboardEvent, focusZone: "card"|"input"|"panel"|"popover") -> Action | null` — 카드 영역에서만 A · 1~6 · S · Enter · →(D-138).
- 컴포넌트: `TagToggle`(`aria-pressed`) · `LevelBadge`(글자 포함) · `LabelerProgress` · `KappaTable` · `QueueCard`(판정 카드: 계산 등급 = `/label/rule/preview`, 제출 뒤 비교) · `KnownInsightsDrawer` · `SourceCard`.
- `lib/api/{prep,label,train,known}.ts`: 02-design 8절 경로. 저장은 `PATCH /session`(drafts)과 기능별 API만.
- [ ] **실패 테스트(Vitest)** `nowCard.test.ts` — 6개 상황 + 시작 전 각각 기대 카드(예: 잔액 부족 + 큐 214 → 잔액 카드 우선) · `labelKeys.test.ts` — 입력칸 포커스에서 "S" → null, 카드에서 → `toggleSituation` · `api/label.test.ts` — 새 화면 클라이언트에 `/save-session` 호출이 없다.
- [ ] **RED** `VITEST src/lib/logic/nowCard.test.ts` → FAIL. **구현** → **GREEN** `npm --prefix frontend test` · `npm --prefix frontend run lint`.
- [ ] 커밋 `feat(web): 3~5단계 공용 컴포넌트·API 클라이언트·지금 할 일·단축키 범위`.

### Task T17: 3단계 화면 — 02-design 3.6 · 목업 s1 · 9.1 행. 확인: `lint` · `build` · QA-P.
### Task T18: 라벨링 화면 — 02-design 4.11 · 4.12 · 목업 s2~s5. "라벨링 시작" 하나 + 예상 한 줄, 방식 잠금 배지, 첫 감사 라운드 뒤 정의 수정 안내, 탭 3개(개요 · 검수 큐 · 감사), 제출 = 저장, 단축키 범위, `aria-live`. 확인: `lint` · `build` · QA-L1~L6.
### Task T19: 학습 화면 · 모델 저장소 — 02-design 5.7 · 목업 s6. "단일 모델 만들기" 버튼과 증류 행은 만들지 않는다(D1). 확인: `lint` · `build` · QA-M.
### Task T20: Known Insight 패널 · 근거 원문 · 셸 — 02-design 6.3 · 목업 s7. 사이드바 "Known Insight · N"(외부 API 드로어와 동시에 하나만 열림), ChatPanel 답변 아래 근거 원문 카드 · "새 발견 찾기" 스위치 · "Known Insight에 추가", StepBar step 이름(`prep-*` · `label-*` · `train-*`), 세션 목록 배지 문구. 확인: `lint` · `build` · QA-K.

각 화면 Task는 RED/GREEN 대신: (1) 해당 화면이 쓰는 로직 함수가 있으면 Vitest를 먼저 쓴다, (2) `npm --prefix frontend run lint && npm --prefix frontend run build` 통과, (3) 목업과 나란히 놓고 브라우저 확인 스크린샷을 보고서에 붙인다.

---

## 브라우저 QA 계획

**실행(로컬 전용, 키 없음):**
```bash
cd backend && STORAGE=local LOCAL_DATA_DIR=/tmp/dcx-qa35 LLM_BACKEND=fake ENABLE_FIXTURE_CHANNEL=true FIXTURE_CORPUS_PATH=tests/fixtures/aircon_qa.csv EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake .venv/bin/uvicorn app.main:app --port 8000
cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_INTERNAL_TOOLS=true npm run dev
```
- 테스트 URL: `http://localhost:3000/pipeline/start` → 0~2단계는 가짜 채널로 빠르게 끝내고 `http://localhost:3000/pipeline/preprocess`부터 본다.
- QA용 짧은 설정: `AUDIT_FIRST=20`, `AUDIT_EVERY=200`, `AUDIT_SIZE=10`(환경변수).
- 도구: gstack `qa-only`(읽기 전용 보고서), 1440×900과 1024×768.

| ID | 시나리오 | 기대 결과 | AC |
|---|---|---|---|
| QA-P | 3단계: 정형 문구 하나 추가 → 실행 → 결과 카드 → 같은 설정으로 새 버전 "3단계부터 다시" → 실행 | 규칙별 제거 막대, 두 번째는 "같은 규칙의 결과를 그대로 씁니다" | AC-01~07 |
| QA-L1 | 라벨링 첫 진입: 예상 한 줄 → "라벨링 시작" → 개요 | 판정 워커 두 개 진행, 방식 배지 고정 | AC-09 · D-136 · D-139 |
| QA-L2 | 검수 큐 · 감사 판정을 키보드로(A · 1~6 · S · Enter), 중간에 Known Insight 패널에 "S" 포함 문장 입력 | 입력칸에서는 태그가 안 바뀜, 계산 등급 변경이 읽힘 | AC-08 · D-138 |
| QA-L3 | 새로고침 · 브라우저 닫기 후 재진입 | 제출한 건 유지, 이어서 다음 건 | AC-14 |
| QA-L4 | 개요: 불일치율 · 큐 건수 · 예상 시간 · 라벨러 성능(감사 기준, 표본 수 표시) | 숫자가 판정 진행에 따라 갱신 | AC-13 |
| QA-L5 | 검수 큐: 제출 전 라벨러 판정 안 보임 → 제출 뒤 비교 표 | 앵커링 방지 | AC-14 |
| QA-L6 | 감사 라운드 판정 · 가짜 데이터로 κ 두 번 하락 | "태그 정의를 확인하세요" 배너 + 지금 할 일 카드 우선순위 2 | AC-15 |
| QA-W | 판정 중 백엔드 워커 kill → 세션 목록 · 개요 | "중단됨 · 이어서 진행" → 이어서 → 호출 중복 없음 | AC-10 |
| QA-M | 학습 → 결과 카드 · 헤드 표 → 저장하고 클러스터링으로 → 군집 화면 동작 | 6단계가 에러 없이 돈다 | AC-17 · AC-19 |
| QA-M2 | 새 세션에서 "분류 모델" 선택 → 라벨링 → 학습 | LLM 호출 없이 끝남(내부용 지표로 확인) | AC-18 |
| QA-K | 채팅 질문 → 근거 원문 → "Known Insight에 추가" → "추가한 이야기 빼고 다시 찾기" → 스위치 끔 | 비슷한 원문이 빠졌다가 다시 보임, 패널에 원문 항목 | AC-21 |
| QA-V | "4단계부터 다시" 새 버전 | 안내 배너, 판정 캐시 재사용(진행 막대 100%) | AC-22 |
| QA-S | 상태: 임베딩 미연결(EMBED_BACKEND=voyage, 키 없음) · Jev 미연결 · 큐 0건 · Known Insight 빈 목록 | 9.1 문구 그대로 | AC-23 |
| QA-E2E | LG 에어컨 fixture 0→5단계 끝까지 | 전 과정 완료 | AC-24 |
| QA-R | 1024×768 · 200% 확대 · Tab 순서 · 포커스 링 | 가로 스크롤 없음, 파란 버튼 화면당 하나 | 10절 |

## 리뷰 계획
- Task마다: Claude가 해당 Task diff를 읽기 전용으로 명세(이 계획 · 02-design)와 품질 기준으로 리뷰하고 `reports/T##.md`에 적는다. 수정은 Codex에 재위임.
- 전체 브랜치: gstack `review`(읽기 전용) + 별도 Codex 읽기 전용 리뷰 1회.
- 통계 코드(T12 temperature · T03 grade_probs)는 리뷰 때 시뮬레이션 테스트 출력을 보고서에 붙인다.
- UAT 때 사용자와 함께(자동 기준 아님): Jev 키 · Voyage 키를 넣고 감사 정답으로 Jev · GPT 정확도와 `relate_outcome` 합친 질문의 κ를 본다(D-116 확인 항목).

## 검증 명령 (harness configure)
```
[["backend/.venv/bin/python","-m","pytest","backend/tests","-q"],
 ["npm","--prefix","frontend","run","lint"],
 ["npm","--prefix","frontend","run","build"],
 ["npm","--prefix","frontend","test"]]
```
- 0~2단계와 같다(이미 `harness.config.json`에 설정됨). torch 테스트가 포함되므로 pytest 전체가 수 분 걸릴 수 있다. 느린 학습 테스트는 합성 데이터 · 작은 에폭으로 60초 이내.

## 되돌리기
- 모든 작업은 worktree의 `feature/dcx2-stage3-5`(기준 `plan/dcx2-stage3-5` ← `feature/dcx2-stage0-2`)에서 한다. `main` · `feature/dcx2-stage0-2`는 건드리지 않는다. 전체 취소는 브랜치와 worktree를 버린다.
- Task마다 커밋이 하나 이상이다. 삭제가 있는 Task(T11 `/sample`, T13 TF 학습, T14 Pinecone)는 삭제를 별도 커밋으로 분리해 따로 되돌릴 수 있게 한다.
- 데이터는 `data/`(git 제외)에만 쓴다. 새 모듈 폴더(`derived/` · `judge/` · `models/` · `work/`)는 지워도 원본 수집본 · 세션은 남는다. QA 데이터는 `/tmp/dcx-qa35`.
- 옛 세션 형식은 바꾸지 않는다(읽기 호환만).

## 수용 기준 연결
| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| 01 | T04 · QA-P | 10 | T08 · QA-W | 19 | T13 · T14 · QA-M |
| 02 | T04 · T17 | 11 | T06 · T07 | 20 | T04 · T13 |
| 03 | T04 | 12 | 제외(D-144) | 21 | T14 · T20 · QA-K |
| 04 | T04 | 13 | T11 · QA-L4 | 22 | T15 · QA-V |
| 05 | T14 | 14 | T11 · T18 · QA-L3 · QA-L5 | 23 | T05 · QA-S |
| 06 | T04 · QA-P | 15 | T11 · QA-L6 | 24 | T15 · QA-E2E |
| 07 | T04 | 16 | T11 | 25 | 검증 명령 |
| 08 | T03 · T11 · QA-L2 | 17 | T12 · T13 | | |
| 09 | T06 · T07 | 18 | T13 · QA-M2 | | |

---

## 엔지니어링 리뷰 (plan-eng-review, 2026-09-30)

대상: 이 문서(03-plan.md). 설계 기준: 02-design.md(승인). 확인한 현재 코드: `backend/app/routers/sessions.py`, `backend/app/crawl/control.py`, `backend/app/llm/codex_exec.py`, `backend/app/crawl/ratelimit.py`, `backend/app/context/{store,versions}.py`, `backend/tests/conftest.py`.

**범위 기록:** feature answers: D1 = B(증류는 백로그 B-107, 2026-09-30) · structure: A Original arrangement(D2, 2026-09-30) · accepted scope: T01~T20에서 증류(distill.py · `/models/{id}/distill` · 테스트 · 화면 버튼) 제외 · pending remedies: R1.

**질문 없이 반영한 것 (이미 승인된 동작의 필수 구현 · 증명):**
- F1 `[P1] (confidence: 9/10) backend/app/routers/sessions.py:22-25` — `owned = {"projectContext", "knownInsights", "keywords", "keywordRounds", "coverage", "crawlConfig", "collectionId", "drafts", …}`에 새 서버 소유 칸 `prep` · `labeling` · `training`이 없다. 6~8단계 옛 화면이 세션 통째 저장을 하면 워커가 쓴 3~5단계 상태를 옛 사본으로 덮어쓴다(이전 학습 `dcx-full-session-save`). 근거 승인: 0~2단계 D-070 보완(D8 답 A, "기존 통째 저장을 받아 주되 서버가 쓰는 칸은 보호한다"). → T15에 `routers/sessions.py` 수정과 `test_save_session_keeps_stage3_5_keys`를 추가했다.
- F2 (D-145로 무의미해져 철회) `[P1] (confidence: 8/10) 03-plan.md T08 · 02-design 4.8` — τ는 캘리브레이션 문서의 LLM 판정이 있어야 계산된다. 판정 순서가 정해지지 않아 318,204건 중 캘리브레이션 400건이 마지막(약 44시간 뒤)에 판정될 수 있다. 근거 승인: 02-design 4.1 "캘리브레이션을 끝내면 채택 건수가 계산됩니다"(D-136). → T08에 "캘리브레이션 · 자기 일관성 문서를 판정 큐 맨 앞에 둔다"와 `test_calibration_docs_judged_first`를 추가했다.


## Decision ledger

### R1: 공용 워커(app/work)와 기존 프로세스 관리 코드의 공유 범위
Finding: F3 · [P2] · confidence 8/10 · `backend/app/crawl/control.py:35` `def pid_alive(pid):` · `backend/app/crawl/queue.py:155` `def _alive(pid: int) -> bool:` · `backend/app/llm/codex_exec.py:17` `def _alive(pid: int) -> bool:` (이 사본만 `if pid <= 0: return False` 가드가 있음) · `control.py:126` `_spawn`(BEGIN IMMEDIATE + Popen + runs 행) · reviewer: Claude
Plan baseline: T01이 `app/work/runner.py`를 새로 만든다. 02-design 7절 · D-125는 "크롤러 프로세스 관리를 app/work로 뽑아 공용화, 크롤러 동작 불변"이라고 적었다(제안 상태, 이 세부는 사용자 답 없음).
Runtime evidence: pid 확인 함수가 이미 세 벌이고 가드가 서로 다르다. 크롤러의 실행 관리(`_live` · `_spawn`)는 `CrawlQueue`의 `runs` 표 · `app.crawl.worker` 명령 문자열에 묶여 있어 그대로 옮기면 크롤러 테스트 전체가 영향 범위다.
Comparison grid:
| 선택 | 현재 | A | B | C |
|---|---|---|---|---|
| 새 워커 runner | 계획: 새로 만듦 | 새로 만듦 | 새로 만듦 | 크롤러 코드를 옮겨 공용화 |
| pid 확인 함수 | 세 벌(가드 다름) | 네 번째 사본을 만들지 않고 `app/work/proc.py` 하나, 새 코드만 사용 | `app/work/proc.py` 하나 + 기존 세 곳도 이것을 import(가드 통일) | C 안에 포함 |
| 크롤러 실행 관리 | control.py | 그대로 | 그대로 | app/work로 이동 |
| 회귀 증명 | 기존 크롤러 테스트 | 기존 테스트 그대로 | 기존 크롤러 · codex_exec 테스트 전부 통과 + `test_pid_alive_rejects_nonpositive` | 크롤러 테스트 전부 + 이어 하기 kill 테스트 재검증 |
Question D3:
D3 — 새 긴 작업 워커와 기존 크롤러의 프로세스 관리 코드를 얼마나 공유할까요?
Project/branch/task: plan/dcx2-stage3-5, T01.
ELI10: 크롤러에는 이미 "워커가 살아 있나 확인 · 두 번 뜨지 않게 막기 · 죽으면 이어서 진행" 코드가 있습니다. 새 3~5단계 워커도 같은 일을 합니다. 그런데 "살아 있나 확인" 함수만 해도 이미 세 군데에 조금씩 다르게 복사돼 있습니다(하나만 pid 0 방어가 있음). 크롤러 코드를 통째로 옮기면 잘 돌던 크롤러를 건드리게 됩니다.
Stakes if we pick wrong: 통째로 옮기면 크롤링 이어 하기가 깨질 수 있고, 아무것도 공유하지 않으면 같은 버그를 네 군데서 고치게 됩니다.
Recommendation: B because 작은 함수 하나만 합쳐서 가드를 통일하고(실제 안전성 이득), 크롤러 실행 관리는 건드리지 않아 회귀 위험이 거의 없습니다.
Completeness: A=7/10, B=9/10, C=8/10
Net: 공유 범위를 늘릴수록 중복은 줄지만 크롤러 회귀 위험이 커진다.
Header: 워커 공유
Options:
A) 새로 만들고 공유 없음
✅ 크롤러 코드를 전혀 건드리지 않아 회귀 위험이 0입니다. ✅ T01이 가장 작습니다(사람 ~0.5일 / CC ~10분). ❌ pid 확인 함수가 네 번째 사본이 되고, 세 기존 사본의 가드 차이는 그대로 남습니다.
B) pid 확인 함수만 합치기 (recommended)
✅ `app/work/proc.py`의 `pid_alive` 하나로 기존 세 곳도 바꿔 pid ≤ 0 가드를 통일합니다(구현 약 −20줄/+15줄). ✅ 크롤러 실행 관리(_live · _spawn)는 그대로라 기존 크롤러 · codex_exec 테스트로 회귀를 확인합니다(사람 ~0.5일 / CC ~15분). ❌ 크롤러와 새 워커의 실행 관리 로직 자체는 여전히 두 벌입니다.
C) 크롤러 실행 관리까지 통째로 공용화
✅ 설계서 D-125 문구대로 실행 관리가 한 벌이 됩니다. ✅ 이후 워커 종류를 늘릴 때 한 곳만 고칩니다. ❌ CrawlQueue 표 · 명령 문자열에 묶인 코드를 옮겨 크롤링 이어 하기 전체가 영향 범위가 됩니다(사람 ~2일 / CC ~1시간, 회귀 위험 큼).

State: approved
Actual answer: B) pid 확인 함수만 합치기 (D3, 2026-09-30)
Accepted scope: T01에 `backend/app/work/proc.py` `def pid_alive(pid: int) -> bool`(pid ≤ 0 → False, ProcessLookupError → False, PermissionError → True)를 만들고, `crawl/control.py:35` `pid_alive` · `crawl/queue.py:155` `_alive` · `llm/codex_exec.py:17` `_alive`를 이것을 import하도록 바꾼다. 크롤러 `_live` · `_spawn`은 바꾸지 않는다. 증명: `tests/work/test_proc.py::test_pid_alive_rejects_nonpositive` · 기존 `tests/crawl` · `tests/llm` 전부 통과.
History: none

### R2: 경계 근접(near_boundary) 정의
Finding: O2 · [P1] · confidence 9/10 · `03-plan.md` T03 `def near_boundary(tags: dict) -> bool — 8개 필드 중 하나만 뒤집어 등급이 바뀌면 참` · `02-design.md` 4.2 · 기획안 8절 ④ "경계 근접 (태그 하나만 뒤집혀도 등급이 바뀌는 건) → escalate" · reviewer: Codex(외부 의견), Claude 확인
Plan baseline: 기획안 · 02-design의 문자 그대로 정의(승인됨). T03 테스트 "분유 예시 → False"는 이 정의와 모순이다.
Runtime evidence: anchor를 0으로 뒤집으면 모든 Core · Supporting이 Non이 되므로, 문자 그대로면 Non이 아닌 문서 전부가 경계 근접 → 전부 escalate. 8개 이진 필드 256조합 중 Core · Supporting 126개가 모두 해당(Codex 계산, 규칙상 자명).
Comparison grid:
| 선택 | 현재(문자 정의) | A | B | C |
|---|---|---|---|---|
| 뒤집어 볼 필드 | 8개 전부 | Jev 확률이 애매한(0.35~0.65) 필드만 | anchor 제외 7개 | 경계 규칙 없음 |
| Core·Supporting 중 escalate | 100% | 애매한 칸이 등급을 바꾸는 문서만(수 % 예상) | 6차원 개수가 딱 문턱(Core 2개 · Supporting 1개)이거나 상황이 Core를 가르는 문서 — 대부분 | 0 |
| α와의 관계 | 검수량이 α와 무관하게 전량 | α가 검수량을 정함(기획안 의도) | α 효과가 약함 | 경계 사례는 τ · 감사에만 맡김 |
Question D4:
D4 — "경계 사례" 규칙을 어떻게 정의할까요?
Project/branch/task: plan/dcx2-stage3-5, T03 · T11.
ELI10: 기획안은 "태그 하나만 뒤집혀도 등급이 바뀌는 글은 사람이 본다"고 했습니다. 그런데 글자 그대로 하면 "대상 경험인가"를 뒤집으면 어떤 Core·Supporting 글도 Non이 되므로, Non이 아닌 글 전부를 사람이 봐야 합니다. 31만 건 중 약 13만 건입니다. 예: "새벽에 짜증나서 그냥 껐다"(감정·행동·상황)는 Core인데, Jev가 감정을 0.52(애매)로 봤다면 정말 경계지만, 0.97로 확신했다면 경계가 아닙니다.
Stakes if we pick wrong: 문자 정의면 α를 아무리 바꿔도 사람 검수가 13만 건으로 고정돼 기획의 핵심(α가 검수량을 정한다)이 무너집니다.
Recommendation: A because 경계의 뜻이 "애매한 칸 하나가 등급을 가른다"이고, Jev가 칸마다 확률을 주므로 그 애매함을 직접 쓸 수 있습니다.
Completeness: A=9/10, B=6/10, C=5/10
Net: 경계 사례를 사람이 보는 장치는 지키되, 확실한 칸까지 뒤집어 보지는 않는다.
Header: 경계 정의
Options:
A) 애매한 칸만 뒤집어 보기 (recommended)
✅ Jev 확률이 0.35~0.65인 칸(설정값)만 뒤집어 보고, 그 칸 하나로 등급이 바뀌면 경계로 봅니다. 확실한 칸은 건드리지 않습니다. ✅ α가 검수량을 정한다는 기획 의도가 살아납니다. T03 테스트를 "분유 예시(모두 확실) → False, 짜증 예시(감정 0.52) → True"로 고칩니다(사람 ~0.5일 / CC ~10분). ❌ 애매함 구간 0.35~0.65가 튜닝값으로 하나 늘어납니다.
B) 대상 경험만 빼고 7칸 뒤집어 보기
✅ 확률 없이 태그만으로 판단해 단순합니다. ✅ 대상 경험 여부는 confidence가 따로 다룹니다. ❌ 6차원이 딱 문턱에 걸린 글(대부분의 Supporting)이 모두 경계가 되어 검수량이 여전히 매우 큽니다.
C) 경계 규칙 없애기
✅ 규칙 하나가 줄고 검수량이 가장 적습니다. ✅ 애매한 글은 confidence < τ로 대부분 걸립니다. ❌ 기획안 ④의 경계 라우팅이 사라지고, 등급은 확신하는데 한 칸이 애매한 글을 놓칠 수 있습니다.

State: approved
Actual answer: C) 경계 규칙 없애기 (D4 재질문, 2026-09-30). 사용자: "1개만 있어도 유용한 문장으로 포함시켜서 모델에서 학습해야 하는거 아니야? … 다 사람 검수하는건 너무 어려워. 그래서 내가 두 모델이 다르게 평가한거에 대해서만 하겠다고 한거고."
Accepted scope: `rule.near_boundary` · 큐 사유 `near_boundary` · `/label/rule/preview`의 `nearBoundary` · 화면의 "경계 사례" 표시를 모두 없앤다. 검수 큐 사유 = `labeler_failed` → `grade_mismatch` → `low_confidence`. 칸 1개 문서는 Supporting으로 학습셋에 그대로 들어간다. 증명: T11 `test_route_order`가 세 사유만 쓰고, `test_one_dim_doc_is_supporting_and_trained`(T12)가 칸 1개 문서가 학습셋에 들어감을 확인한다.
History: 첫 D4(A/B/C 제시) → 사용자 되물음 "경계 사례가 뭐야?" → 개념 설명 → 사용자 의견 → D4 재질문(C/B) → C.

### R3: τ(채택 기준) 탐색 방식
Finding: O3 · [P1] · confidence 9/10 · `02-design.md` 4.8 "후보 τ(고유값들)를 높은 쪽부터 차례로 검사 … UCB ≤ α인 동안 τ를 낮춘다. 처음 실패하면 멈추고" · `03-plan.md` T10 `compute_tau` · reviewer: Codex(외부 의견), Claude 계산 확인
Plan baseline: 02-design 4.8(설계 승인)의 고정 순서 검정, 후보 = confidence 고유값 전부.
Runtime evidence: Clopper-Pearson 상한(δ=0.10, 오류 0건)은 n=1 → 0.900, n=40 → 0.0559, n=100 → 0.0228, n=400 → 0.0057(scipy 계산). 첫 후보는 채택 1건이라 상한 0.9 > α=0.10으로 곧바로 실패하고 멈춘다 → 라벨러가 완벽해도 "채택 불가".
Comparison grid:
| 선택 | 현재 | A | B |
|---|---|---|---|
| 보장("채택 오류율 ≤ α, 확률 1−δ") | 유지(하지만 채택 0) | 유지 | 유지 |
| 후보 τ | 고유값 전부, 위에서부터 | 미리 정한 20칸: confidence 상위 10% · 15% · … · 100% 지점, 위에서부터, 처음 실패에서 멈춤 | 같은 20칸, 각 칸을 δ/20으로 검사하고 통과한 가장 낮은 τ |
| 첫 검사 표본(캘리브레이션 400건) | 1건 | 40건 | 40건 |
| 오류 0건일 때 첫 칸 상한 | 0.900(실패) | 0.056(통과) | 0.124(실패, 50건쯤부터 통과) |
| 증명 | 위험 시뮬레이션만 | 위험 시뮬레이션 + `test_tau_accepts_on_perfect_labels` | 같음 |
Question D5:
D5 — 채택 기준(τ)을 찾는 방식을 고칠까요?
Project/branch/task: plan/dcx2-stage3-5, T10.
ELI10: τ는 "confidence가 이 값 이상이면 사람 검수 없이 채택"하는 선입니다. 설계는 가장 높은 confidence 글 1건부터 시작해 "여기까지 채택해도 오류율이 α 이하라고 통계적으로 말할 수 있나"를 한 칸씩 내려가며 확인합니다. 그런데 1건만으로는 통계적으로 아무 말도 못 해서(상한 90%) 첫 칸에서 바로 실패하고 멈춥니다. 라벨러가 400건을 다 맞혀도 "채택할 수 있는 라벨이 없습니다"가 뜹니다.
Stakes if we pick wrong: 지금대로면 모든 문서가 사람 검수로 가서 α 기능 전체가 쓸모없어집니다.
Recommendation: A because 표준 방식(미리 정한 칸을 위에서부터 검사)이라 보장은 그대로이고, 첫 칸부터 40건이라 좋은 라벨러면 바로 채택이 생깁니다.
Completeness: A=9/10, B=8/10
Net: 같은 통계 보장 안에서, 검사 칸을 어떻게 나누느냐의 차이.
Header: τ 탐색
Options:
A) 20칸 고정 순서 (recommended)
✅ confidence 상위 10%(캘리브레이션 40건) · 15% · … · 100% 지점만 위에서부터 검사하고 처음 실패에서 멈춥니다. 보장(확률 1−δ로 오류율 ≤ α)은 그대로입니다. ✅ 400건을 다 맞히면 첫 칸 상한 5.6%로 바로 채택됩니다. `test_tau_accepts_on_perfect_labels`를 추가합니다(사람 ~0.5일 / CC ~10분). ❌ 중간 칸에서 한 번 실패하면 그 아래는 더 보지 않아, 운이 나쁘면 τ가 필요 이상으로 높게 나올 수 있습니다.
B) 20칸 각각 따로 검사(본페로니)
✅ 한 칸이 실패해도 아래 칸을 계속 봅니다. ✅ 보장은 같습니다. ❌ 칸마다 더 엄격하게 검사해(δ/20) 첫 칸은 오류 0건이어도 통과하지 못하고, 채택량이 A보다 조금 적습니다.

State: approved
Actual answer: 사용자 지정 — "타우 자체를 없애도 될거 같아. 지금은. 그냥 이 개념을 당분간 제외하자." (D5 재질문 답, 2026-09-30). A · B 모두 고르지 않음.
Accepted scope: τ · α · δ와 `compute_tau` · `POST /label/{sid}/alpha` · α 패널 · `low_confidence` 큐 사유 · AC-12 · AC-13의 α 부분 · QA-L4를 이번 범위에서 뺀다. 검수 큐 사유 = `labeler_failed` → `grade_mismatch`. `confidence`는 계속 계산해 저장한다(학습 가중 · 나중에 τ를 되살릴 때 사용). 캘리브레이션의 역할은 R4에서 정한다.
History: D5(A/B) → 사용자 되물음 "오류율이 나중에 모델이 있고 나서는 안 보여지는거 아니야?" → 방식별 설명 → D5 재질문 → τ 제외.

### R4: 캘리브레이션의 역할 (τ 제외 뒤)
Finding: R3 결과로 생긴 새 선택 · reviewer: Claude
Plan baseline: 02-design 4.8 캘리브레이션 400건(한 사람, D-131).
Runtime evidence: τ가 빠지면 캘리브레이션의 남은 역할은 라벨러 정확도 측정 · 합친 질문 점검뿐이다.
Comparison grid: A 400건 유지 · B 제외하고 감사로 대신(첫 라운드 1,000건, re-issue 2건/라운드) · C 100건 유지
Question D6: τ를 빼면 캘리브레이션(사람이 400건 직접 판정)은 어떻게 할까요? (전문은 대화 기록)
Header: 캘리브레이션
Options:
A) 400건 캘리브레이션 유지
B) 캘리브레이션 빼고 감사로 대신 (recommended)
C) 작게(100건) 유지

State: approved
Actual answer: B) 캘리브레이션 빼고 감사로 대신 (D6, 2026-09-30)
Accepted scope: 캘리브레이션 세트 · 탭 · `calib_set` 표 · `calib.py`를 만들지 않는다. T10 = 감사 통계(첫 라운드 채택 1,000건, 이후 1만 건마다 50건, re-issue 2건/라운드, 라벨러 정확도 누적, 정의 점검 신호). 목업 캘리브레이션 화면 삭제.
History: none


### 엔지니어링 리뷰 결과 (Sections 1–4 · 외부 의견)

**1 · 아키텍처**
- F4 `[P1] (8/10) 02-design 2.4 · T15` 버전 복사 중 `labels.sqlite` 불일치 → 백업 API(질문 없이, D-078 근거). 
- O1 `[P1] (9/10) T01` 두 판정 워커의 실행 키 충돌 → 키에 라벨러 포함(질문 없이, D-136 근거).
- O4 `[P1] (9/10) services/clustering.py:19 · services/s3.py:28` 로컬에서 `classified/{sid}/relevant_` 접두사를 못 읽어 전처리 전체로 넘어감 → 버전별 명시 경로(질문 없이, D-109 · AC-19 근거).
- O5 `[P1] (8/10) routers/context.py:75` 한줄 정의 변경 후에도 판정 캐시 재사용 → `ctxKey`(질문 없이, D-120 근거).

**2 · 코드 품질**
- F3/R1 `[P2] (8/10) crawl/control.py:35 · crawl/queue.py:155 · llm/codex_exec.py:17` pid 확인 함수 세 벌 → D3 B.
- F5 `[P2] (7/10) T11 · T13` `stage_5.json` 쓰는 곳 두 개 → `export.write_stage5` 하나.
- O6 `[P1] (9/10) llm/codex_exec.py:137` `run_many` 입력 고정과 GPT 묶음 재시도 충돌 → 묶음별 실행 ID(질문 없이).
- O7 `[P1] (8/10) T09 · T11` 영구 실패 문서가 큐에 못 감 → 바로 큐(질문 없이).

**3 · 테스트** — 프레임워크: pytest(`backend/pytest.ini`) · Vitest(`frontend/package.json` `"test": "vitest run"`).
```
CODE PATHS (계획)                                     USER FLOWS
[+] app/prep (T04 · T05)                              [+] 3단계 실행 · 재사용 · 미연결 — QA-P · QA-S
  ├── [★★★] 필터·정형 문구·두 갈래·토큰·재사용·0벡터·이어 하기
[+] app/vectors (T02)                                 [+] 라벨링 시작 → 개요 → 검수 → 감사 — QA-L1~L6
  ├── [★★★] 결정적 임베딩·샤드·0벡터 제외·배치 질의       ├── [★★★] 입력칸 단축키 차단 — QA-L2 · labelKeys.test
[+] app/label                                            ├── [★★★] 새로고침 후 이어서 — QA-L3 · test_submit_is_durable
  ├── rule [★★★] 표 6행·확률 DP·몬테카를로              └── [★★ ] 워커 kill 후 이어서 — QA-W · test_kill_restart
  ├── jev [★★★] 요청 형태·확률 복원·정규화·누락·절단·오류 6종
  ├── gpt [★★★] 첫 줄·도메인 예시 없음·부분 묶음·연속 묶음 재시도(O6)·한도
  ├── votes/judge [★★★] 이어 하기·캐시 공유·ctxKey(O5)·속도 제한·잔액
  ├── merge [★★★] 합의·불일치·signal·대기
  ├── audit [★★★] 첫 라운드 1,000·re-issue·정확도·신호·사람 덮어쓰기
  └── route/API [★★★] 사유 2종·실패 문서 큐(O7)·대량 큐·투표 숨김·모드 잠금
[+] app/model (T12 · T13)                             [+] 학습 → 저장 → 군집 — QA-M · test_clustering_input_is_core_supporting_only
  ├── [★★★] 헤드 형태·마스크 기울기 0·소프트 라벨·앙상블·temperature·표본 부족·시드
  └── [★★★] 규칙 변경 재추론·임베더 불일치·모델 구간 LLM 0회·불일치 라우팅·감시
[+] app/known · 로컬 검색 (T14)                        [+] 근거 원문 → Known Insight — QA-K
  └── [★★★] doc_id·θ 제외·토글·옛 세션 사유·Pinecone 미로드
[+] 버전 · 저장 (T15)                                 [+] 4단계부터 다시 — QA-V · test_restart_stage4_reuses_cache
  └── [★★★] sqlite 백업 복사(F4)·서버 소유 칸(F1)·E2E
LLM 품질: [→EVAL] Jev 질문 q1 · GPT 프롬프트 q1 — 자동 평가 없음. UAT에서 실제 키로 감사 정답 대비 정확도 · relate_outcome κ 확인(D-116).
COVERAGE(계획): 코드 경로 전부 테스트 지정 · 사용자 흐름 13개 QA 지정 | GAPS: 자동 LLM 평가 1(UAT로)
```
- 회귀: 0~2단계 테스트(`tests/crawl` · `tests/llm` · `tests/keywords` · `tests/test_integration_stage0_2.py`)가 T01(pid 통합) · T04(전처리 교체) 뒤에도 그대로 통과해야 한다(검증 명령에 포함). 옛 세션은 3~5단계 새 화면에서 열람만(02-design 2.1, 승인됨) — T05 `test_legacy_session_rejected` · T11 `test_legacy_label_reads_as_anchor`.

**4 · 성능**
- F6 `[P2] (8/10) T09` 전체 재합치기 → 증분.
- F7 `[P2] (7/10) T02` 검색마다 2GB 재읽기 → memmap + 캐시.
- 참고: GPT 판정 31.8만 건 ÷ 20 = 약 1.6만 exec, 동시 4개 · exec당 약 60초면 약 2.8일(설정으로 조절). Jev는 약 44시간.

**외부 의견 (Codex, 완료):** 7건 — O1 · O4 · O5 · O6 · O7은 질문 없이 반영, O2 → D4(C 경계 규칙 없음), O3 → D5(τ 제외) → D6(캘리브레이션 제외).

### NOT in scope
- 증류(B-107): 앙상블만으로 속도 충분(D1).
- τ · α · 캘리브레이션(D-144 · D-145): 사용자 결정. `confidence`는 저장해 두어 나중에 되살릴 수 있다.
- 크롤러 실행 관리 공용화(D3 C): 회귀 위험.
- 자동 LLM 품질 평가 스위트: 실제 키가 없어 UAT에서 측정.
- 6단계 이후 개편 · actor 태그 · Core 강화 조건(01 · backlog).

### What already exists (재사용)
- `app/llm/codex_exec.run_many`(GPT 대량 판정), `app/crawl/ratelimit.ChannelLimiter`(Jev 속도), `app/context/store.update_session` · `locked`(부분 저장), `app/context/versions`(버전 복사), `routers/sessions.py` 서버 소유 칸 보호(F1로 확장), `services/voyage.py`(모델만 교체), `tests/fakes/fake_codex.py`, `tests/conftest.py`의 `data_dir` · `client`.

### 데이터 흐름
```
수집본 c1 ──▶ [T04 prep] ──▶ derived/{c1}/{prepKey}/ docs · tokens · vectors · stage_3.json
                                    │
                    [T08 judge:jev] ┼ [T08 judge:gpt]   (판정 캐시 judge/…/{qver}-{ctxKey}/)
                                    ▼
                         [T09 merge] ─▶ labels.sqlite final ─▶ [T11 route] ─▶ queue ─▶ 사람 제출
                                    │                              └▶ 채택 ─▶ [T10 audit 1,000/1만]
                                    ▼
                         [T12 train 앙상블] ─▶ models/{id} ─▶ [T13 infer/export] ─▶ classified/{sid}/{v}/relevant.jsonl
                                                                                   └▶ 6단계 군집 · [T14 로컬 RAG]
```

### Failure modes
| 경로 | 실제로 일어날 실패 | 테스트 · 처리 | 사용자에게 보이나 |
|---|---|---|---|
| Jev | 잔액 부족(402) | `test_insufficient_credit_pauses` | 배너 "Jev 잔액이 부족합니다" |
| GPT | codex 사용량 한도 | `test_usage_limit_pauses` | 배너 + 이어서 진행 |
| 판정 캐시 | 한줄 정의 변경 후 옛 판정 재사용 | `test_one_liner_change_new_cache` | "판정 맥락이 바뀌어 다시 판정합니다" |
| 합치기 | 한 라벨러 영구 실패 | `test_failed_doc_reaches_queue` | 큐 사유 "판정 실패" |
| 버전 복사 | 제출 중 sqlite 복사 | `test_version_copy_sqlite_consistent` | (조용히 막힘, 복사본 정상) |
| 6단계 | Non까지 군집 | `test_clustering_input_is_core_supporting_only` | 오류 "5단계 결과가 없습니다" |
| 옛 화면 저장 | 워커 상태 덮어쓰기 | `test_save_session_keeps_stage3_5_keys` | (조용히 보호) |
| 로컬 검색 | 벡터 없음 · 전부 제외 | `test_search_legacy_session_reason` | 사유 문구 |
- 테스트도 처리도 없이 조용히 실패하는 경로: 없음(critical gap 0).

### Worktree parallelization strategy
| Step | Modules touched | Depends on |
|---|---|---|
| A 기반 | backend/app/work, config, crawl·llm(pid만) | — |
| B 벡터 · 규칙 | backend/app/vectors, backend/app/label(rule) | A |
| C 3단계 | backend/app/prep, routers | B |
| D 라벨러 | backend/app/label(schema·jev·gpt·votes·judge) | B |
| E 합치기 · 감사 · 라우팅 | backend/app/label(store·merge·audit·route·overview), routers | D, C |
| F 학습 · 모델 | backend/app/model, routers | E(합치기), B |
| G Known · RAG · 연결 | backend/app/known, services, routers | F |
| H 버전 · 통합 | backend/app/context, routers/sessions | C, E, F, G |
| I 프론트 | frontend/src | H(API 계약) |
- Lane 1: A → B → {C ∥ D} → E → F → G → H. Lane 2: I(T16 → {T17 ∥ T18 ∥ T19 ∥ T20}) — H 뒤.
- 충돌: `backend/app/main.py`(T05 → T11 → T13 → T14 순차), `backend/app/work/worker.py`(T05 · T08 · T13 순차).

## Implementation Tasks
Synthesized from this review's findings. 각 항목은 위 Task에 이미 반영됐다(파일 · 테스트 지정).
- [ ] **E1 (P1, human: ~2h / CC: ~10min)** — work — 판정 워커 실행 키에 라벨러 포함 (O1 → T01)
- [ ] **E2 (P1, human: ~3h / CC: ~15min)** — model/export · clustering — 버전별 명시 경로로 내보내고 군집이 그 파일만 읽기 (O4 → T13 · T14)
- [ ] **E3 (P1, human: ~2h / CC: ~10min)** — label/votes — 판정 캐시 키에 ctxKey (O5 → T08)
- [ ] **E4 (P1, human: ~3h / CC: ~15min)** — label/gpt — 묶음별 run_many 실행 ID · 부분 응답 재시도 (O6 → T07)
- [ ] **E5 (P1, human: ~1h / CC: ~10min)** — label/route — 영구 실패 문서 바로 큐 (O7 → T11)
- [ ] **E6 (P1, human: ~2h / CC: ~10min)** — context/versions — sqlite 백업 API 복사 (F4 → T15)
- [ ] **E7 (P1, human: ~1h / CC: ~5min)** — routers/sessions — 서버 소유 칸 prep · labeling · training (F1 → T15)
- [ ] **E8 (P2, human: ~2h / CC: ~15min)** — work/proc — pid_alive 통합 (R1 → T01)
- [ ] **E9 (P2, human: ~2h / CC: ~10min)** — label/merge · vectors — 증분 합치기 · memmap 캐시 (F6 · F7 → T09 · T02)
- [ ] **E10 (P1, human: ~1d / CC: ~30min)** — label — 경계 사례 · τ · α · 캘리브레이션 제거, 감사 통계(T10) (R2 · R3 · R4)

### Unresolved decisions
- 없음.

### Completion summary
- Step 0: Scope Challenge — scope reduced per recommendation (증류 제외, D1)
- Architecture Review: 4 issues found (F4 · O1 · O4 · O5)
- Code Quality Review: 4 issues found (F3 · F5 · O6 · O7)
- Test Review: diagram produced, 1 gap identified (자동 LLM 평가 → UAT)
- Performance Review: 2 issues found (F6 · F7)
- NOT in scope: written
- What already exists: written
- TODOS.md updates: 0 items proposed to user (프로젝트에 TODOS.md 없음, 백로그 B-107로 기록)
- Failure modes: 0 critical gaps flagged
- Unresolved decisions: 0 in this review
- Outside voice: codex, completed (7 findings)
- Parallelization: 2 lanes, 백엔드 순차 위주 + 프론트 4개 병렬
- Lake Score: 3/3 (D3 · D5→D6 · 설계 결정 모두 완전한 쪽 선택; 종류 선택 D1 · D2 · D4 제외)

Approval readiness: PASS — D1(B) · D2(A) · D3(B) · D4(C) · D5(τ 제외, 사용자 지정) · D6(B); 질문 없이 반영한 F1 · F4 · F5 · F6 · F7 · O1 · O4 · O5 · O6 · O7은 승인된 동작(D-070 · D-078 · D-109 · D-120 · D-136 · AC-19)의 필수 구현.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | codex (`/plan-eng-review` outside voice) | Independent 2nd opinion | 1 | completed | 7 findings, 7 resolved |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | ISSUES OPEN (all mapped to tasks) | 12 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR (FULL) | score: 4/10 → 8/10, 9 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex, plan-review phase, completed, 7 findings (O1~O7) — 5건 질문 없이 반영, 2건 사용자 결정(D4 · D5).
- **CROSS-MODEL:** Claude 리뷰가 놓친 O1 · O2 · O3 · O4 · O6 · O7을 Codex가 찾았다. O5는 Claude F2(판정 순서)와 같은 영역(판정 캐시 계약). 두 리뷰 모두 캐시 · 워커 계약을 가장 큰 위험으로 봤다.
- **VERDICT:** DESIGN CLEARED. ENG — 발견 12건 모두 Task로 반영, 미결 0(상태 issues_open은 "매핑된 작업 있음" 뜻).

NO UNRESOLVED DECISIONS
