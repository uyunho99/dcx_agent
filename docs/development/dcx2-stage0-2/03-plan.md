# DCX 2.0 0~2단계 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 방식으로 Task 단위로 진행한다. 이 하네스에서 **구현 담당은 항상 Codex**(`codex:codex-rescue`, `--wait --fresh`, 쓰기 가능 작업)이고, Main Claude는 위임 · 결과 확인 · 리뷰만 한다. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 0단계 입력 · 1단계 키워드 발산/수렴 · 2단계 크롤링을 기획안(D-001~069)대로 다시 만들고, LG 에어컨 데이터로 네트워크 없이 0→2→전처리까지 끝까지 돌게 한다.

**Architecture:** FastAPI 백엔드에 새 패키지 `app/context` · `app/llm` · `app/keywords` · `app/external` · `app/crawl`을 추가하고, 옛 키워드 · 크롤링 라우터를 대체한다. 크롤링은 웹 서버와 분리된 P1/P3 워커 프로세스 + 로컬 SQLite 큐로 돈다. 프론트는 Person A 디자인 시스템 토큰 · 컴포넌트를 새로 깔고 0~2단계 화면을 목업대로 다시 만든다.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic v2 · pydantic-settings · httpx · selectolax · crawl4ai · yt-dlp · SQLite(WAL) · pytest / Next.js 16 · React 19 · Zustand 5 · Tailwind 4 · lucide-react

**Spec:** [`02-design.md`](02-design.md) (디자인 리뷰 13절 포함) · [`01-brainstorm.md`](01-brainstorm.md) (수용 기준 AC-01~21) · [`decision-log.md`](decision-log.md) · 목업 [`mockups/index.html`](mockups/index.html)

## Global Constraints
- Python **3.12** 가상환경 `backend/.venv`에서 실행한다. 시스템 Python 3.9.6은 기존 코드의 `X | None` 문법을 못 읽는다(계획 작성 중 확인).
- 저장소는 로컬 디스크다. `.env`의 `STORAGE=local`, 데이터 루트는 `LOCAL_DATA_DIR`(기본 `data`)이다. S3 경로는 지우지 않지만 새 기능은 로컬만 전제한다(D-002).
- 크롤링 검색어는 키워드 그대로이고 `bk`를 붙이지 않는다. 제품명 포함 필터는 기본 꺼짐이다(D-014).
- 모든 LLM 호출은 `app/llm/compose.py`를 거치고 `project_context.md` 원문을 "참고 맥락" 블록으로 싣는다. 파일 경로가 아니라 내용을 싣는다(D-017).
- LLM 백엔드는 `openai_api`(기본, D-076) · `codex_exec` · `claude_api`(선택) · `fake`(테스트 · QA용 결정적 응답)다(D-051 · D-076).
- 외부 API 키가 없어도 전 과정이 끝나야 하고, 미연결 기능은 `unconnected`로 표시한다(D-023). 키 값은 응답 · 로그 · 화면에 절대 싣지 않는다.
- 테스트는 네트워크 · API 키 · codex 설치 없이 돈다. HTTP는 녹화 파일 + `httpx.MockTransport`, codex는 가짜 실행 파일을 쓴다.
- UI 문구: 버튼은 동사로 끝난다. 이모지 · 느낌표 · 사과 표현을 쓰지 않는다. 로딩은 "처리 중…", 날짜는 `2026. 9. 28.` 형식, Eyebrow는 한국어다(02-design 10절).
- 색 · 타입 · 라운드는 02-design 10절 토큰만 쓴다. primary = `#0a73b5`, 보조 텍스트 = `#8A8A8C`(캡션 · 힌트 · 메타 전용).
- 내부용 요소(외부 API 드로어, md 미리보기, 내부 ID)는 `NEXT_PUBLIC_INTERNAL_TOOLS`로 켜고 끈다. 끄면 렌더링하지 않는다.
- 세션은 버전(통째 복사)으로 관리하고, 크롤링 수집본은 버전과 분리된 변경 불가 모듈이다(D-075 · D-078). 어떤 단계 결과도 서버가 거부해 사라지지 않는다(D-070 보완).
- 크롤링은 채널끼리, 채널 안에서는 키워드 · URL을 동시성 한도까지 병렬로 돈다(D-077).
- 원본 코퍼스 `~/Downloads/포털_전처리완료_에어컨.csv`는 git에 넣지 않는다. 테스트는 합성 샘플을 만들고, 원본 샘플은 `FIXTURE_CORPUS_PATH`로만 읽는다.

## Review Focus
1. **띄어쓰기만 다른 키워드**("실외기 소음" / "실외기소음")는 같은 키워드로 본다. 정규화 키 = 공백 제거 + 소문자 → T05 `test_normalize_merges_spacing_variants`.
2. **LLM이 JSON을 코드 펜스 · 앞뒤 설명 · 끝 쉼표로 감싸서** 돌려줘도 파싱된다. 그래도 안 되면 1회 재시도 후 `parse` 오류 → T02 `test_extract_json_tolerates_fence_and_prose`.
3. **같은 글의 다른 URL**(`m.cafe.naver.com` vs `cafe.naver.com`, `?art=` 같은 추적 파라미터)은 한 문서다 → T10 `test_normalize_url_collapses_cafe_variants`.
4. **jsonl 샤드 쓰기 도중 강제 종료**되면 마지막 줄이 잘릴 수 있다. 읽는 쪽은 잘린 줄을 건너뛰고 경고만 남긴다 → T13 `test_reader_skips_truncated_last_line`.
5. **session.json 동시 쓰기**(라운드 작업 스레드 + 화면 저장)로 한쪽 변경이 사라지면 안 된다. 세션 쓰기는 파일 잠금 + 필드 단위 병합(`update_session(sid, patch)`)으로만 한다 → T04 `test_concurrent_session_patches_both_survive`.

---

## 실행 규칙 (하네스)
- 계획 승인 후 기획 산출물을 커밋하고 `development-harness worktree <abs-path> feature/dcx2-stage0-2`로 worktree를 만든 뒤 그 안에서만 작업한다.
- Task 하나 = Codex 위임 하나. 위임문에 cwd · 소유 파일 · 이 문서의 해당 Task 발췌 · 수용 기준 · RED/GREEN 명령 · 보고서 경로(`docs/development/dcx2-stage0-2/reports/T##.md`)를 넣는다. TDD 규칙(먼저 실패 확인 → 최소 구현 → 통과 → 리팩터 · 남의 변경 보존)을 위임문에 직접 적는다.
- 파일 소유가 겹치는 Task는 순차로 한다. 겹치지 않고 의존이 끝난 Task만 병렬로 보낼 수 있다.
- 각 Task 뒤에 Claude가 명세 · 품질을 읽기 전용으로 리뷰한다. 수정이 필요하면 같은 Task를 Codex에 다시 보낸다.
- 백엔드 명령은 모두 `backend/`에서 `.venv/bin/python -m pytest ...`로 실행한다. 아래 표기 `PYTEST` = `cd backend && .venv/bin/python -m pytest`.

## 의존 관계 · 파일 소유

| Task | 이름 | 의존 | 소유 파일(생성 C / 수정 M) |
|---|---|---|---|
| T01 | 환경 · 테스트 기반 | – | C `backend/requirements-dev.txt` `backend/pytest.ini` `backend/tests/conftest.py` `backend/tests/test_health.py` · M `backend/requirements.txt` `backend/app/config.py` `.env.example` `README.md`(실행 절) |
| T02 | LLM 공통 층 | T01 | C `backend/app/llm/*` `backend/tests/llm/*` `backend/tests/fakes/fake_codex.py` |
| T03 | ProjectContext · md 생성 | T01 | C `backend/app/context/{models,labels,render}.py` `backend/tests/context/test_models.py` `test_render.py` |
| T04 | 세션 저장소 · Context API · 제품군 · 세션 활동 | T02 T03 | C `backend/app/context/{store,category}.py` `backend/app/routers/context.py` `backend/app/external/{__init__,base,naver_shopping}.py` `backend/tests/context/test_api.py` `test_store.py` · M `backend/app/routers/sessions.py` `backend/app/main.py` |
| T05 | 3축 분류 · 키워드 모델 · 정규화 | T01 | C `backend/app/keywords/{__init__,taxonomy,models,normalize}.py` `backend/tests/keywords/test_normalize.py` |
| T06 | 라운드 프롬프트 R1~R4 | T03 T05 | C `backend/app/keywords/prompts/r{1,2,3,4}.v1.md` `backend/app/keywords/prompts.py` `backend/tests/keywords/test_prompts.py` |
| T07 | HITL 이벤트 · keyword_feedback.md | T04 T05 | C `backend/app/keywords/{events,feedback}.py` `backend/tests/keywords/test_feedback.py` |
| T08 | 검색량 · 커버리지 | T02 T05 | C `backend/app/external/naver_searchad.py` `backend/app/keywords/{volume,coverage}.py` `backend/tests/keywords/test_coverage.py` `test_volume.py` |
| T09 | 라운드 작업 · 키워드 API | T06 T07 T08 | C `backend/app/keywords/rounds.py` `backend/app/routers/keywords_v2.py` `backend/tests/keywords/test_rounds_api.py` · M `backend/app/main.py` · 삭제 `backend/app/routers/keywords.py`의 `/generate-keywords` `/score-keywords`(`/suggest-words`는 v2로 이관) |
| T10 | 문서 스키마 · URL 정규화 · 해시 | T01 | C `backend/app/crawl/{__init__,schema,urls,hashing}.py` `backend/tests/crawl/test_schema.py` `test_urls.py` |
| T11 | SQLite 큐 · P2 필터 | T10 | C `backend/app/crawl/{queue,filters}.py` `backend/tests/crawl/test_queue.py` `test_filters.py` |
| T12 | 어댑터 규약 · 가짜 채널 | T10 | C `backend/app/crawl/adapters/{__init__,base,fixture}.py` `backend/tests/crawl/test_fixture_adapter.py` |
| T13 | P1/P3 워커 · 이어 하기 · P4 저장 | T11 T12 | C `backend/app/crawl/{worker,writer,ratelimit,healthcheck}.py` `backend/tests/crawl/test_worker.py` `test_resume.py` |
| T14 | 게이트 · P5 리포트 · 크롤링 API | T13 | C `backend/app/crawl/{gate,report,control}.py` `backend/app/routers/crawl_v2.py` `backend/tests/crawl/test_crawl_api.py` · M `backend/app/main.py` · 삭제 `backend/app/routers/crawling.py` `backend/app/services/crawling.py` |
| T15 | 네이버 카페 · 블로그 어댑터 | T12 | C `backend/app/crawl/adapters/{naver_cafe,naver_blog}.py` `backend/app/external/naver_search.py` `backend/tests/crawl/adapters/test_naver.py` `backend/tests/fixtures/http/naver_*/*` |
| T16 | 유튜브 어댑터 | T12 | C `backend/app/crawl/adapters/youtube.py` `backend/tests/crawl/adapters/test_youtube.py` `backend/tests/fixtures/http/youtube/*` |
| T17 | 뽐뿌 · 클리앙 어댑터 | T12 | C `backend/app/crawl/adapters/{community,ppomppu,clien}.py` `backend/tests/crawl/adapters/test_community.py` `backend/tests/fixtures/http/{ppomppu,clien}/*` |
| T18 | 전처리 호환 · 뒤 단계 폴백 · 통합 테스트 | T09 T14 | M `backend/app/services/preprocessing.py` `backend/app/routers/{training,personas,clustering}.py`(bk 폴백만) · C `backend/tests/test_integration_stage0_2.py` `backend/app/routers/integrations.py` |
| T19 | 디자인 시스템 기반 · 셸 | T01 | C `frontend/src/styles/tokens.css` `frontend/public/fonts/*` `frontend/src/components/ds/*` `frontend/src/lib/internalTools.ts` · M `frontend/src/app/globals.css` `frontend/src/app/layout.tsx` `frontend/src/app/pipeline/layout.tsx` `frontend/src/components/StepBar.tsx` `frontend/package.json` |
| T20 | 0단계 화면 · 세션 목록 | T04 T19 | C `frontend/src/lib/contextLabels.ts` `frontend/src/lib/api/context.ts` · M `frontend/src/app/pipeline/start/page.tsx` `frontend/src/components/SessionList.tsx` `frontend/src/lib/types.ts` `frontend/src/stores/useSessionStore.ts` `frontend/src/lib/sessionPersist.ts` · C `backend/tests/context/test_labels_parity.py` |
| T21 | 1단계 화면 | T09 T20 | M `frontend/src/app/pipeline/keywords/page.tsx` · C `frontend/src/components/keywords/*` `frontend/src/lib/api/keywords.ts` · 삭제 `frontend/src/components/{CategoryInputPanel,NewCategoryInput,KeywordTag,DuplicateAlertCard}.tsx`(새 컴포넌트로 대체) |
| T22 | 2단계 화면 | T14 T20 | M `frontend/src/app/pipeline/crawling/page.tsx` · C `frontend/src/components/crawl/*` `frontend/src/lib/api/crawl.ts` |
| T23 | 내부용 API 드로어 · 뒤 단계 화면 폴백 | T18 T19 | C `frontend/src/components/internal/IntegrationsDrawer.tsx` · M `frontend/src/app/pipeline/{training,personas}/page.tsx`(bk · pd를 projectContext에서) `frontend/src/lib/api.ts` |
| T24 | 버전 선택 · "이 단계부터 다시" · 비교 화면 | T04 T19 T21 | C `frontend/src/app/pipeline/compare/page.tsx` `frontend/src/components/versions/*` `frontend/src/lib/api/versions.ts` · M 셸 사이드바(T19 파일, T19 이후) |

병렬 가능 묶음: {T02, T03, T05, T10, T19} → {T04, T06, T08, T11, T12} → {T07, T13, T15, T16, T17} → {T09, T14} → {T18, T20} → {T21, T22, T23}. 같은 줄 안에서도 소유 파일이 겹치는 `backend/app/main.py`(T04 · T09 · T14)는 순차로 한다.

---

## M0 · 기반

### Task T01: 환경 · 테스트 기반

**Files:** 위 표 참조.

**Interfaces:**
- Produces: `tests/conftest.py`의 fixture `data_dir(tmp_path, monkeypatch)` → `settings.local_data_dir`를 `tmp_path`로 바꾸고 `app.services.s3`의 로컬 백엔드가 그 경로를 쓰게 한다. fixture `client` → `fastapi.testclient.TestClient(app)`.
- `app/config.py` `Settings`에 필드 추가(모두 env 이름 = 대문자 필드명): `storage="local"`(기본값 변경), `llm_backend="openai_api"`, `openai_api_key=""`, `openai_model=""`(값은 사용자가 .env로 지정), `llm_backend_overrides: dict[str,str]={}`, `codex_bin="codex"`, `codex_profile="dcx-worker"`, `codex_timeout_s=600`, `claude_model="claude-sonnet-4-20250514"`, `naver_search_base_url="https://openapi.naver.com"`, `searchad_api_key=""`, `searchad_secret=""`, `searchad_customer_id=""`, `naver_datalab_*`는 두지 않음(B-002), `youtube_api_key=""`, `fixture_corpus_path=""`, `enable_fixture_channel=False`, `low_volume_threshold=10`, `gate_low_count=10`, `gate_low_unique=0.2`, `author_salt_path="data/.author_salt"`.

- [ ] **Step 1: 준비 (사람 1회)** — Python 3.12 설치: `brew install python@3.12`. 이 설치는 사용자 기기 소프트웨어 설치이므로 Codex가 실행하지 않는다. Main Claude가 사용자에게 요청하고 완료를 확인한다.
- [ ] **Step 2:** `python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt`, `backend/.venv/bin/crawl4ai-setup`(crawl4ai가 쓰는 Playwright Chromium 설치 · 엔지니어링 리뷰 F3), `npm --prefix frontend ci`.
- [ ] **Step 3: 실패 테스트** `tests/test_health.py::test_health_ok` — `client.get("/health").json() == {"status": "ok"}`; `test_default_storage_is_local` — `Settings().storage == "local"`.
- [ ] **Step 4: RED** `PYTEST tests/test_health.py -q` → `test_default_storage_is_local` FAIL(현재 기본값 `s3`).
- [ ] **Step 5:** config 필드 추가, `requirements.txt`에 `httpx selectolax crawl4ai yt-dlp pydantic>=2`, `requirements-dev.txt`에 `pytest pytest-asyncio`. `pytest.ini`: `testpaths = tests`, `asyncio_mode = auto`.
- [ ] **Step 6: GREEN** `PYTEST -q` → 2 passed.
- [ ] **Step 7:** `README.md` 실행 절을 venv · 로컬 저장소 기준으로 고치고 커밋 `chore: python 3.12 venv, pytest 기반, 로컬 저장소 기본값`.

### Task T02: LLM 공통 층

**Interfaces:**
- Produces (`app/llm/base.py`):
  - `class Attachment(BaseModel): title: str; body: str`
  - `class LLMTask(BaseModel): task: str; sid: str; instructions: str; attachments: list[Attachment]; output_schema: type[BaseModel]; max_tokens: int = 8000`
  - `class LLMError(BaseModel): kind: Literal["timeout","parse","schema","backend","interrupted"]; message: str`
  - `class LLMResult(BaseModel): ok: bool; data: BaseModel | None; raw: str | None; error: LLMError | None`
  - `class LLMBackend(Protocol): def run(self, task: LLMTask) -> LLMResult`
- `app/llm/compose.py`: `CONTEXT_HEADER = "아래는 규칙이 아니라 참고 맥락이다. 벗어나는 발견도 배제하지 말 것."`; `def compose(task: LLMTask) -> tuple[str, str]` → `(system, user)`. system = `CONTEXT_HEADER` + 첨부마다 `=== 참고: {title} ===\n{body}`; user = `instructions`. `def extract_json(text: str) -> Any`.
- `app/llm/registry.py`: `def get_backend(task_name: str) -> LLMBackend` (override는 fnmatch 패턴), `def run_task(task: LLMTask) -> LLMResult` = 백엔드 실행 + JSON 추출 + 스키마 검증 + 실패 시 1회 재시도.
- `app/llm/openai_api.py` `OpenAIApiBackend` (기본 · OpenAI Python SDK · 구조화 출력(JSON schema) 요청 · 참고 블록을 앞쪽 system 메시지에 고정) · `app/llm/claude_api.py` `ClaudeApiBackend`(선택).
- `app/llm/fake.py` `FakeBackend(responses: dict[str, str])` — `task` 이름으로 고정 응답. `settings.llm_backend="fake"`면 `backend/tests/fixtures/llm/{task}.json`을 읽는다(QA용).
- `app/llm/codex_exec.py` `CodexExecBackend` · `def run_many(tasks: list[LLMTask], run_id: str, concurrency: int) -> list[LLMResult]`. 폴더 배치 · 워커 지시문 · pid 잠금 · `bad/` 격리 · 로그 이어쓰기는 02-design 3.3을 그대로 따른다.

- [ ] **Step 1: 실패 테스트** `tests/llm/test_compose.py`
  - `test_compose_attaches_context_verbatim`: 본문 `"# 프로젝트 맥락\n- 제품: LG 휘센 에어컨"`인 첨부 → system에 그 문자열이 **바이트 그대로** 들어 있고 `CONTEXT_HEADER`로 시작한다 (AC-04).
  - `test_extract_json_tolerates_fence_and_prose`: `'설명\n```json\n[{"kw":"소음",}]\n```'` → `[{"kw":"소음"}]`.
- [ ] `tests/llm/test_registry.py`
  - `test_retry_once_then_schema_error`: FakeBackend가 두 번 다 스키마 위반 → `ok=False, error.kind=="schema"`, 호출 2회.
  - `test_override_pattern`: `llm_backend_overrides={"kw_round_*":"fake"}` → `get_backend("kw_round_2")`가 FakeBackend.
  - (D-076) `test_default_backend_is_openai`: 설정 기본값에서 `get_backend("kw_round_1")`가 `OpenAIApiBackend`이고, 모의 클라이언트로 호출하면 요청에 `response_format`(json_schema)과 참고 블록 system 메시지가 들어 있다. 키가 없으면 `backend` 오류 + `unconnected` 표시.
- [ ] `tests/llm/test_codex_exec.py` (`tests/fakes/fake_codex.py`를 `settings.codex_bin`으로 지정. 가짜는 지시문 첫 줄의 답 경로에 정해진 JSON을 쓴다)
  - `test_rerun_skips_answered_and_live` (AC-17): 3건 중 1건은 답이 있고 1건은 살아 있는 pid 잠금 → 새 exec 1개만 뜬다.
  - `test_bad_answer_quarantined`: 스키마 위반 답 → `answers/bad/task-0.json`과 `.reason.txt`가 생기고 결과 `schema`.
  - `test_timeout_kills_process`: 가짜가 잠들면 `codex_timeout_s=1` → `timeout`, 자식 프로세스가 남지 않는다.
- [ ] **RED** `PYTEST tests/llm -q` → ImportError(모듈 없음).
- [ ] **구현.** `claude_api`는 기존 `services/claude.py`의 requests 호출을 옮기고, `services/claude.py`는 호환 래퍼(`call_claude` → `ClaudeApiBackend`)로 남긴다.
- [ ] **GREEN** `PYTEST tests/llm -q` → all passed.
- [ ] 커밋 `feat(llm): 공통 LLM 층 (openai_api 기본·codex_exec·claude_api·fake)`.

---

## M1 · 0단계

### Task T03: ProjectContext · project_context.md

**Interfaces:**
- Produces (`app/context/models.py`): `ProjectContext` — 필드 · 선택지 코드는 02-design 2.3 표 그대로. `schemaVersion: Literal[1] = 1`. `ChoiceWithNote(choice: <Enum>, note: str = "")`. `AlignmentWarning(source, item, reason)`.
- `app/context/labels.py`: `LABELS: dict[str, dict[str, str]]` — 선택지 코드 → 한글 라벨(예: `LABELS["projectType"]["renewal"] == "리뉴얼"`).
- `app/context/render.py`: `def render_context_md(ctx: ProjectContext, known: list[str]) -> str`.

- [ ] **실패 테스트** `test_models.py`
  - `test_required_fields`: `oneLiner` 누락 → `ValidationError`
  - `test_channels_min_one`: `channels=[]` → `ValidationError`
  - `test_targetscope_optional`: 0-B 전부 비어도 통과
- [ ] `test_render.py`
  - `test_render_deterministic`: 같은 입력 두 번 → 같은 문자열
  - `test_render_sections`: `"## 0-A 프로젝트 개요"`, `"## 0-B 분석 대상 · 초기 기준선"`, `"우선 탐색하되 범위 밖 발견도 배제하지 말 것"`, `"## 이미 아는 것"`을 포함한다
  - `test_render_uses_korean_labels`: `projectType.choice="renewal"` → `"리뉴얼"`
- [ ] **RED** `PYTEST tests/context -q` → ImportError → 구현 → **GREEN**.
- [ ] 커밋 `feat(context): ProjectContext 모델과 project_context.md 생성`.

### Task T04: 세션 저장소 · Context API · 제품군 · 세션 활동

**Interfaces:**
- Consumes: T02 `run_task`, T03 모델 · render.
- Produces (`app/context/store.py`):
  - `def load_session(sid) -> dict | None`
  - `def update_session(sid, patch: dict) -> dict` — 파일 잠금(`fcntl.flock`, `sessions/{sid}/.lock`) 안에서 읽기 → 깊은 병합 → 원자적 쓰기(임시 파일 → rename). **세션 쓰기는 이것만 쓴다.**
  - `def is_legacy(session) -> bool` (`schemaVersion` 없음)
  - `def session_dir(sid) -> Path`
- `app/context/category.py`: `def suggest_category(bk, one_liner) -> CategorySuggestion(l1, l2, l3, source: Literal["shopping","llm_estimate"])`.
- `app/external/base.py`:
  - `class Unconnected(Exception)`
  - `def integration_status() -> list[IntegrationStatus(name, connected, env_vars: list[str], affects: list[str], last_error: str | None)]` — 키 값은 싣지 않는다.
- `app/external/naver_shopping.py`: `def search_categories(bk, n=40) -> list[tuple[str,str,str]]` (키 없으면 `Unconnected`).
- API (`routers/context.py`):
  - `POST /context` → `{sid}`
  - `GET/PUT /context/{sid}`
  - `POST /context/category-suggest`
- `GET /sessions`: 각 항목에 `schemaVersion`, `legacy`, `activity: {kind, status, progress, updatedAt} | null`을 싣고, 02-design 4.1(4A) 순서로 정렬한다.
  - 크롤링 활동은 T14의 `crawl.control.activity(sid)`를 **있으면** 부른다. T14 전에는 `None`이다.

- [ ] **실패 테스트** `test_store.py`
  - `test_concurrent_session_patches_both_survive`: 스레드 2개가 `{"a":1}`, `{"b":2}`를 50번씩 패치 → 두 키가 모두 남는다(Review Focus 5)
  - `test_atomic_write_no_partial`: 쓰기 중 예외가 나도 기존 파일이 온전하다
- [ ] `test_api.py`
  - `test_post_context_creates_session_and_md` (AC-02): 201. `session.json`에 `schemaVersion==2`, `projectContext`가 있고 `project_context.md`가 생긴다.
  - `test_category_llm_fallback` (AC-03): 쇼핑 `Unconnected` + FakeBackend → `source=="llm_estimate"`.
  - `test_category_shopping_mode`: MockTransport로 상품 3개(2개가 `디지털/가전>계절가전>에어컨`) → 그 경로, `source=="shopping"`.
  - `test_sessions_legacy_flag`: 옛 형식 세션 → `legacy: true`.
  - `test_sessions_sorted_attention_first`: activity `interrupted` 세션이 첫 행이다.
  - `test_put_context_after_r1_warns`: R1 완료 세션에서 `oneLiner`를 바꾸면 응답에 `warnings: ["oneLiner_changed_after_r1"]`.
  - (R1) `test_step_patch_keeps_rounds`: 서버가 `keywordRounds.2`를 쓴 뒤 `PATCH /session/{sid}` `{step:"r3"}` → `keywordRounds.2`가 남는다. 허용 키 밖(`keywords`)을 보내면 400.
  - (R1) `test_draft_roundtrip_per_screen`: `PATCH /session/{sid}` `{drafts:{start:{...}}}` → `GET /context/{sid}`가 `draft`를 함께 돌려준다.
- [ ] **(D-075 · D-078) 버전:** `app/context/versions.py`
  - Produces:
    - `create_version(sid, from_v, restart_from, note) -> str` — 버전 폴더 통째 복사, `collectionId` 유지, `restart_from` 이후 단계에 `stale` 표시, 이전 버전 `readonly`
    - `set_active(sid, v)`
    - `list_versions(sid)`
    - `compare(sid, a, b, stage) -> dict` (02-design 2.2.1)
    - `active_version_dir(sid) -> Path` — `session_dir(sid)`는 이 경로를 돌려준다
  - `meta.json`은 파일 잠금 안에서만 바꾼다.
  - 라우터: 02-design 7절 버전 경로
- [ ] 테스트 `tests/context/test_versions.py`
  - `test_create_version_copies_all_but_collection`: v1 파일 전부가 v2에 복사되고, `collectionId`는 같으며, `crawl/{sid}/collections/`는 그대로다
  - `test_restart_marks_downstream_stale`: `restart_from="stage1"` → `stale`에 stage2 이후가 표시되고, stage1을 저장하면 stage1 표시가 풀린다
  - `test_old_version_readonly`: v1에 `PATCH /session` → 409
  - `test_version_blocked_while_job_running`: 라운드 작업 `running` 중 버전 생성 → 409
  - `test_compare_stage1_added_removed_moved`: 추가 · 삭제 · 축 이동 목록과 축 분포 차이가 맞다
  - `test_compare_stage2_same_collection`: 같은 수집본이면 `{"same": true}`
- [ ] **(D8 · D-070 보완) 통째 저장 병합:** `/save-session`은 거부하지 않고 서버 소유 키(02-design 2.2 목록)를 버린 뒤 나머지를 잠금 안에서 합친다.
  - `test_legacy_full_save_merges_but_keeps_server_keys`: 화면이 옛 `keywordRounds`를 담아 보내도 서버 값이 남고, `labeledData`는 반영된다
  - `test_labeling_save_then_train_reads`: 라벨링 화면 형식으로 저장 → `services/training.py`가 `labeledData`를 읽는다
  - 앞의 R1 테스트 `test_full_save_rejected_for_v2`는 이 두 테스트로 대체한다(엔지니어링 리뷰 D8)
- [ ] **RED → 구현 → GREEN** `PYTEST tests/context -q`.
- [ ] 커밋 `feat(context): 세션 저장소 잠금·병합, 버전, context API, 제품군 제안, 세션 활동`.

---

## M2 · 1단계

### Task T05: 3축 분류 · 키워드 모델 · 정규화

**Interfaces:**
- Produces:
  - `taxonomy.AXES: dict[str, list[str]]` — 02-design 5.1 표의 코드 그대로
  - `taxonomy.is_valid(axis, sub) -> bool` (`custom:` 허용)
  - `models.Keyword` — 02-design 2.4 필드
  - `normalize.norm_key(kw) -> str` (공백 제거 + 소문자 + NFC)
  - `normalize.clean_generated(items: list[dict], existing: list[Keyword], banned: set[str]) -> tuple[list[dict], list[str]]` — (통과, 보정 로그)
  - `BANNED = {"후기","비교","추천","가격","장단점","선택","고민","리뷰","평가","만족","불만"}`

- [ ] **실패 테스트** `test_normalize.py`
  - `test_normalize_merges_spacing_variants`: 기존 `실외기소음` + 생성 `실외기 소음` → 제외된다(Review Focus 1)
  - `test_drops_short_and_banned`: `"a"`, `"후기"` → 제외
  - `test_unknown_sub_coerced_to_first`: `axis="physical", sub="xxx"` → `sub="time"` + 보정 로그 1건
  - `test_custom_sub_allowed`: `custom:설치환경` → 통과
- [ ] **RED → 구현 → GREEN** `PYTEST tests/keywords/test_normalize.py -q` → 커밋.

### Task T06: 라운드 프롬프트 R1~R4

**Interfaces:**
- Consumes: T03 render, T05 AXES.
- Produces (`app/keywords/prompts.py`):
  - `def build_round_task(sid, n: Literal[1,2,3,4], state: RoundInputs) -> LLMTask`
  - `RoundInputs(context_md, feedback_md | None, approved: list[Keyword], distribution: dict[str,float], rejection_signals: str | None, coverage_signals: str | None, past_zero_kws: list[str], project_type: str, channels: list[str], target_scope_text: str, product_category: str)`
  - `PROMPT_VERSION = {1:"r1.v1",2:"r2.v1",3:"r3.v1",4:"r4.v1"}`
  - `MIN_COUNT = {1:70,2:100,3:60,4:60}`
  - `TONE = {...}` — 02-design 5.3 발산 톤 문구 그대로
  - `def r3_input_status(state) -> dict[str,str]` — 값: `"ok"` / `"empty:no_rejections"` / `"empty:searchad_unconnected"` / `"empty:no_prior_session"`
- 프롬프트 파일은 02-design 5.3 골격(임무 → 사고 절차 → 형태 규칙 → 분류 → 출력)을 따르고, 역할 문장과 도메인 예시를 넣지 않는다.

- [ ] **실패 테스트** `test_prompts.py`
  - `test_four_distinct_templates` (AC-05): 4개 렌더 결과가 서로 다르고, 각 버전 문자열이 `PROMPT_VERSION`과 일치한다.
  - `test_no_role_sentence_no_domain_examples`: 4개 모두 `"전문가입니다"`, `"에어컨 예시"`, `"보험 예시"`를 포함하지 않는다.
  - `test_r1_tone_by_project_type`: renewal → `TONE["renewal"]` 문구를 포함한다.
  - `test_r3_empty_inputs_explicit` (AC-08): 거절 0 + 미연결 → 본문에 `"거절 없음."`과 `"커버리지 정보 없음 — 축 분포 균형에 집중."`이 있고, status가 `{"rejection":"empty:no_rejections","coverage":"empty:searchad_unconnected", ...}`.
  - `test_r3_uses_user_moves_when_no_rejections`: 거절 0 + 수동 추가 2건 → 그 2건이 "원하는 방향" 목록에 나온다.
  - `test_attachments_include_feedback_md`: R2 이상이고 `feedback_md`가 있으면 첨부가 2개다.
- [ ] **RED → 구현 → GREEN** → 커밋.

### Task T07: HITL 이벤트 · keyword_feedback.md

**Interfaces:**
- Produces:
  - `events.append_event(sid, ev: KeywordEvent) -> None` (jsonl 추가 전용)
  - `events.load_events(sid) -> list[KeywordEvent]`
  - `KeywordEvent` — 02-design 5.4 필드
  - `REJECT_TAGS = ("irrelevant","common","sentence","misclassified")`
  - `feedback.render_feedback_md(events) -> str` (결정적) · `feedback.write_feedback_md(sid) -> str`

- [ ] **실패 테스트** `test_feedback.py`
  - `test_sections_order`: 방향 지시 → 거절 사유 → 원하는 방향 → 오분류 이동 순서로 헤더가 나온다.
  - `test_reject_examples_capped_8`: 같은 태그 12건 → 예시 8개 + `"외 4건"`.
  - `test_misclassified_records_move`: `from`/`to`가 표시된다.
  - `test_deterministic`: 같은 이벤트 → 같은 출력.
- [ ] **RED → 구현 → GREEN** → 커밋.

### Task T08: 검색량 · 커버리지

**Interfaces:**
- Produces:
  - `naver_searchad.monthly_volume(kws: list[str]) -> dict[str, int]` — 5개씩 묶어 호출, 서명 헤더 `X-Timestamp`/`X-API-KEY`/`X-Customer`/`X-Signature`(HMAC-SHA256)
  - `naver_searchad.related_queries(hints: list[str]) -> list[tuple[str,int]]`
  - 둘 다 키가 없으면 `Unconnected`
  - `volume.attach_volumes(kws: list[Keyword]) -> list[Keyword]` — `volume.source` · `low_volume` 배지
  - `coverage.compute(human: list[tuple[str,int]], llm: list[Keyword], human_axes: dict[str,str] | None) -> CoverageReport(m1, m2: list[float|None], m6: float|None, m7: float, missing_top: list[tuple[str,int]], llm_only_ids: list[str])`
  - `coverage.js_distance(p: dict, q: dict) -> float` (밑 2)

- [ ] **실패 테스트** `test_coverage.py` — 입력 사람 쿼리 `[("에어컨 소음",100),("에어컨 냄새",50),("실외기",30),("리모컨",20)]`, LLM `["소음","실외기","결로"]`, 부분일치 규칙
  - `test_m1_volume_weighted`: `m1 == pytest.approx(130/200)`
  - `test_m2_deciles_len_10`: 길이 10, 쿼리가 없는 분위는 `None`
  - `test_js_identical_zero_disjoint_one`: 같은 분포 → `0.0`, 겹침 없음 → `1.0`
  - `test_m7_llm_only`: 검색량 `{"소음":900,"실외기":400,"결로":5}` → `결로`만 매칭 없음 ∧ <10 → `m7 == pytest.approx(1/3)`, `llm_only_ids`에 결로 id
  - `test_missing_top_sorted_by_volume`: 누락 쿼리가 검색량 내림차순이고 최대 20개
  - `test_m6_none_without_axes`: `human_axes=None` → `m6 is None`
- [ ] `test_volume.py`
  - `test_unconnected_marks_source`: 키 없음 → 모두 `source=="unconnected"`, `low_volume` 배지 없음
  - `test_batches_of_five`: 12개 → 호출 3회(MockTransport 카운트)
  - `test_signature_header`: 고정 timestamp · secret → 알려진 서명값
- [ ] **RED → 구현 → GREEN** → 커밋.

### Task T09: 라운드 작업 · 키워드 API

**Interfaces:**
- Consumes: T04 `update_session`, T06 `build_round_task`, T07 events, T08 volume/coverage, T02 `run_task`.
- Produces (`rounds.py`):
  - `def start_round(sid, n) -> RoundJob(jobId, status)` — 같은 라운드에 running이 있으면 그것을 반환
  - `def round_status(sid, n) -> RoundJob & {keywords?}`
  - `def commit_round(sid, n, decisions: list[{id, status, reject?}]) -> None`
  - 서버가 시작할 때 `recover_interrupted()`가 `running` → `failed(kind=interrupted)`로 바꾼다
- 라우터(`keywords_v2.py`): 02-design 7절 키워드 경로 전부 + `POST /keywords/{sid}/suggest-words` (입력 `{axis, sub}`).
- 라운드 확정 순서: R1→R2→R3→R4 강제. R4 뒤에는 `POST /keywords/{sid}/rounds/4`를 다시 불러 추가 생성할 수 있다. R2 확정 시 `coverage`를 자동 계산한다.

- [ ] **실패 테스트** `test_rounds_api.py` (FakeBackend, `data_dir`)
  - `test_rounds_must_follow_order` (AC-05): R1 확정 전 R2 시작 → 409
  - `test_start_is_idempotent_while_running`: 두 번 POST → 같은 `jobId`, 백엔드 호출 1회
  - `test_job_survives_refresh`: 시작 → 완료 후 GET → pending 키워드. 새 TestClient로도 같다
  - `test_interrupted_on_restart`: `running` 상태를 저장해 두고 `recover_interrupted()` → `failed/interrupted`
  - `test_partial_count_flag`: 42개 응답(R1) → 상태에 `below_min: {got:42, min:70}`
  - `test_r2_commit_triggers_coverage`: R2 확정 → `session.coverage` 존재(미연결이면 `status:"unconnected"`)
  - `test_r3_inputs_recorded`: `keywordRounds.3.inputs` 기록
  - `test_old_endpoints_removed`: `/generate-keywords` → 404
  - (R5 회귀 계약 · CRITICAL) `test_manual_add_scores_volume`: `POST /keywords/{sid}/manual` `{kw, axis, sub}` → `origin=="manual"`, 검색량 조회 결과(또는 `unconnected`)가 붙는다
  - (R5) `test_manual_add_duplicate_409`: 띄어쓰기만 다른 기존 키워드 → 409 + `{duplicateOf: <id>}`(화면의 중복 경고 근거)
  - (R5) `test_suggested_word_origin_recorded`: 추천 단어로 추가 → `origin=="suggested"`
  - (R5) `test_custom_sub_requires_axis`: `sub="custom:설치환경"`에 `axis`가 없으면 422
  - (Codex #5) `test_r4_regen_gen_ids_unique`: R4를 두 번 추가 생성 → 키워드 ID에 `g1`/`g2`가 붙어 겹치지 않고, 옛 `gen`으로 확정하면 409
  - (Codex #8) `test_concurrent_round_start_single_job`: 스레드 2개가 동시에 `POST /rounds/2` → `jobId` 1개, 백엔드 호출 1회
- [ ] **RED → 구현 → GREEN** `PYTEST tests/keywords -q` → 커밋.

---

## M3 · 2단계 수집 기반

### Task T10: 문서 스키마 · URL 정규화 · 해시

**Interfaces:**
- Produces:
  - `schema.Doc` — 02-design 2.5 필드
  - `urls.normalize_url(url, source) -> str`
  - `urls.doc_id(source, url_norm, thread_key: str = "") -> str` — 접두사 `{"naver_cafe":"nc","naver_blog":"nb","youtube":"yt","ppomppu":"pp","clien":"cl","fixture":"fx"}` + `_` + sha1 앞 16자
  - `hashing.author_hash(source, raw_id) -> str` — salt 파일이 없으면 생성, 권한 600

- [ ] **실패 테스트**
  - `test_normalize_url_collapses_cafe_variants`: `https://m.cafe.naver.com/ca-fe/mamcafe/123?art=xx` · `https://cafe.naver.com/mamcafe/123` → 같은 값(Review Focus 3)
  - `test_strips_tracking_params`: `utm_source`, `fbclid` 제거
  - `test_doc_id_deterministic_and_prefixed` (AC-13)
  - `test_author_hash_stable_and_no_raw` (AC-15): 같은 입력 → 같은 해시, 결과에 원문이 없음, salt 파일 권한 `0o600`
- [ ] **RED → 구현 → GREEN** → 커밋.

### Task T11: SQLite 큐 · P2 필터

**Interfaces:**
- Produces (`queue.py`, 테이블은 02-design 6.3 그대로):
  - `class CrawlQueue(path)`
  - `add_list_tasks(kws: list[KwMeta], sources)`
  - `next_list_task() -> ListTask | None`
  - `record_list_page(task, items: list[ListItem], next_cursor)`
  - `add_urls(items) -> int` (UNIQUE 충돌 시 `url_hits`만 추가)
  - `take_snapshot() -> snapshot_id`
  - `lease_urls(snapshot_id, n, lease_s) -> list[UrlRow]` — 순서는 `(kw_order, source, url_norm)`
  - `mark_done(url_norm, source, doc_count, last_error=None)`
  - `mark_failed_attempt(...)`
  - `exclude_keywords(snapshot_id, kws) -> int`
  - `reclaim_expired_leases() -> int`
  - `counts() -> dict`
- `filters.py`:
  - `class FilterConfig(date_from, date_to, ad_words, exclude_sources, include_sources, product_name_filter=False, bk="")`
  - `def check_list(item, cfg) -> str | None` (걸린 규칙 번호 문자열)
  - `def check_doc(doc, cfg) -> str | None`
  - `DEFAULT_AD_WORDS`: 기존 목록 + `체험단 협찬 원고료 소정의 제공받아 서포터즈`
  - `DEFAULT_EXCLUDE_SOURCES`: 기존 `crawling.py`의 `default_exclude` 목록

- [ ] **실패 테스트** `test_queue.py`
  - `test_unique_url_records_hits`: 같은 URL을 두 키워드로 추가 → urls 1행, url_hits 2행
  - `test_lease_order_deterministic` (AC-13)
  - `test_reclaim_expired`: lease 만료 → `pending` 복귀
  - `test_exclude_keywords` (AC-14): 제외 → `excluded`, `lease_urls`에 나오지 않음
  - (R2) `test_concurrent_writers_no_locked_error`: 프로세스 3개가 5초 동안 동시에 `mark_done` · `exclude_keywords` · runs heartbeat를 써도 `sqlite3.OperationalError` 0건. 모든 연결은 `PRAGMA journal_mode=WAL; busy_timeout=10000; synchronous=NORMAL`, 상태 조회는 `mode=ro` 연결
  - (Codex #7) `test_dead_run_leases_reclaimed`: 죽은 run이 잡은 lease(아직 만료 전)도 새 워커 시작 시 `pending`으로 돌아간다
  - (Codex #4 · D9) `test_shared_url_excluded_only_if_all_hits_excluded`: A · B가 같은 URL을 찾았을 때 A만 제외하면 수집되고 `kw=B`, 둘 다 제외하면 `excluded`
- [ ] `test_filters.py`
  - `test_product_filter_off_by_default` (AC-10): 본문에 `bk`가 없어도 통과
  - `test_product_filter_on_uses_body`: 켜면 제목에는 없고 본문에만 있어도 통과
  - `test_ad_words_blog_sponsored`: `"소정의 원고료를"` → `"②"`
  - `test_date_range`
- [ ] **RED → 구현 → GREEN** → 커밋.

### Task T12: 어댑터 규약 · 가짜 채널

**Interfaces:**
- Produces (`adapters/base.py`):
  - `ListItem(url, title, snippet, date | None, src_meta)`
  - `ListPage(items, next_cursor: str | None, total_hint: int | None)`
  - `FetchedDoc(title, body, comments: list[Comment], date, src_meta, access, author_raw | None, thread_key="")`
  - `class ChannelAdapter(Protocol): source: str; def list_page(kw, cursor) -> ListPage; def fetch(item) -> list[FetchedDoc]`
  - `class AdapterBlocked(Exception)` (403·429)
  - `REGISTRY: dict[str, Callable[[], ChannelAdapter]]`
  - `def available_sources() -> list[str]` (`fixture`는 `enable_fixture_channel`일 때만)
- `adapters/fixture.py` `FixtureAdapter(corpus_path)`:
  - 부분일치 검색, 행 번호 순, 페이지 100건, URL `fixture://aircon/{row}`
  - 제목은 본문 앞 30자, 댓글 없음, 날짜는 행 번호로 만든 결정적 날짜
  - 코퍼스 파일은 한 번 읽어 메모리 인덱스로 둔다

- [ ] **실패 테스트** `test_fixture_adapter.py` — 테스트가 20행 합성 CSV(`review` 컬럼)를 `tmp_path`에 만든다
  - `test_list_pages_by_100_and_cursor`
  - `test_query_is_keyword_only`: `"소음"`으로 찾으면 `"소음"`이 든 행만 나온다
  - `test_fetch_returns_body`
  - `test_disabled_by_default`: `available_sources()`에 `fixture`가 없다
- [ ] **RED → 구현 → GREEN** → 커밋.

### Task T13: P1/P3 워커 · 이어 하기 · P4 저장

**Interfaces:**
- Consumes: T11 큐 · 필터, T12 어댑터, T10 스키마 · 해시.
- Produces:
  - `worker.main(argv)` — `python -m app.crawl.worker {list|detail} --sid S [--snapshot ID]`
  - `worker.run_list(sid) -> snapshot_id`
  - `worker.run_detail(sid, snapshot_id)` — heartbeat 10초 · runs 테이블 · pid
  - `writer.DocWriter(dir, shard_size=5000)` — `write(doc)`, `close()`
  - `writer.read_docs(dir) -> Iterator[dict]` — 잘린 줄 건너뛰기 + 경고
  - `ratelimit.ChannelLimiter(concurrency, min_interval_s)`
- 실패 처리 · 차단 처리는 02-design 6.4 값 그대로: `max_attempts=3` · 지수 백오프 · 스니펫 폴백 · `block_threshold=20` → 채널 `paused_blocked`.
- 1건 처리 순서: fetch → P2 `check_doc` → Doc 생성(해시) → `DocWriter.write` → `mark_done` (200건마다 커밋).

- [ ] **실패 테스트** `test_worker.py` (가짜 채널 · 합성 CSV)
  - `test_list_then_detail_writes_docs` (AC-11): docs에 새 스키마 필드가 모두 있다
  - `test_fetch_failure_falls_back_to_snippet` (AC-15): 어댑터가 3회 예외 → `fetch_level=="snippet"`, `last_error` 기록
  - `test_blocked_channel_pauses_only_that_channel`: A 채널만 `AdapterBlocked` 20회 → A는 `paused_blocked`, B는 완료
  - `test_restricted_recorded`: `access=="restricted"` 문서도 기록된다
- [ ] `test_resume.py`
  - `test_kill_and_resume_no_refetch` (AC-12): detail 워커를 서브프로세스로 띄워 fetch 호출 수를 파일로 센다. 30건 처리 후 SIGKILL → 재기동 → 완료 후 URL별 fetch 호출이 최대 1회(lease 중이던 최대 1배치 제외)이고 `doc_id` 중복은 읽기 단계에서 0이 된다
  - `test_reader_skips_truncated_last_line` (Review Focus 4)
  - (Codex #3) `test_fsync_before_done`: `mark_done` 커밋 직전에 강제 종료를 흉내 내도(모의) 커밋된 URL의 문서는 모두 샤드에 있다. 잘린 마지막 줄 뒤 재개 → 새 줄이 올바른 줄 경계에서 시작한다
  - (D-077) `test_channels_and_keywords_run_concurrently`: 가짜 어댑터 2채널 × 키워드 3개, 요청마다 0.2초 → 전체 시간이 순차 합(1.2초)의 절반 미만이고 채널별 동시 요청 수는 한도를 넘지 않는다
  - (D-077) `test_parse_error_rate_pauses_channel`: 파싱 실패 30% 초과 채널 → `paused_parse_error`, 다른 채널 계속
  - (D-077) `test_healthcheck_reports_per_stage`: `python -m app.crawl.healthcheck --source fixture` → 채널별 `list_ok n/n · detail_ok n/3 · blocked false` 한 줄씩, 파서 예외가 나면 해당 단계가 `FAIL`로 찍힌다
  - `test_same_snapshot_same_urls` (AC-13): 같은 스냅샷으로 두 번 → 같은 `doc_id` 집합
- [ ] **RED → 구현 → GREEN** `PYTEST tests/crawl -q` → 커밋.

### Task T14: 게이트 · P5 리포트 · 크롤링 API

**Interfaces:**
- Produces:
  - `gate.compute_gate(queue) -> list[GateRow(kw, axis, sub, per_source: dict[source, {listed, filtered, unique}], listed, after_filter, unique_ratio, badges: list[Literal["zero","low","low_unique"]])]` — 기준 `gate_low_count=10`, `gate_low_unique=0.2`
  - `gate.estimate(queue, cfg) -> {urls, minutes}`
  - `report.build_report(queue) -> dict` (02-design 6.7 형태, 큐 집계만 · D7) · `report.write_report(sid)` (P3 종료 시 한 번) · `report.progress(queue) -> Progress` (진행 중 단순 카운터)
  - `control.start_list(sid)` · `control.start_detail(sid, snapshot_id)` · `control.resume(sid)` · `control.stop(sid)` · `control.status(sid)`
  - `control.activity(sid) -> Activity | None` (T04가 사용)
  - 워커는 `subprocess.Popen([sys.executable,"-m","app.crawl.worker",...], start_new_session=True)`로 띄운다. 살아 있는 pid가 있으면 새로 띄우지 않는다.
- 라우터 `crawl_v2.py`: 02-design 7절 크롤링 경로 전부. 설정은 `session.crawlConfig`에 저장한다.

- [ ] **실패 테스트** `test_crawl_api.py`
  - `test_gate_badges`: 0건 · 저수율 · 고유 기여 낮음 각각 1개 키워드를 만들어 배지를 확인한다
  - `test_gate_excludes_then_detail_skips` (AC-14)
  - `test_report_matrix_fields` (AC-11): `matrix[kw][source]`에 `listed, filtered, excluded, full, snippet, restricted, unique` 키
  - `test_status_interrupted_when_pid_dead`: 죽은 pid + 미완료 → `interrupted`
  - `test_no_double_spawn`: `start_detail` 두 번 → Popen 1회(monkeypatch)
  - `test_query_never_contains_bk` (AC-10): 어댑터가 받은 검색어 목록에 `bk` 문자열이 없다
  - `test_old_crawl_endpoints_removed`: `/crawl` POST → 404
  - (R3 · D-074) `test_report_built_on_phase_end_only`: P3 진행 중에는 `report.json`이 생기지 않고, P3 종료 시 한 번 생긴다
  - (D-070 · Codex #6) `test_gate_save_does_not_start_detail`: `PUT /crawl/{sid}/gate` 뒤 워커가 뜨지 않고, `POST /crawl/{sid}/detail`에서만 뜬다
  - (D9) `test_per_keyword_counts_include_shared`: 두 키워드가 같은 URL을 찾으면 게이트 표 · 리포트의 키워드별 수에 각각 1건씩 잡히고, 전체 문서 수에는 1건
  - (D-078) `test_added_keywords_creates_child_collection`: 키워드 12개가 추가된 버전에서 `mode=added-keywords` → `c2.parent=="c1"`, c2 목록 작업은 추가 키워드만, c1 파일은 바뀌지 않는다
  - (D-078) `test_new_list_creates_new_collection`: 목록을 다시 모으면 새 수집본이 생기고 이전 수집본 docs는 그대로다
  - (Codex #8) `test_concurrent_detail_start_single_worker`: 동시 두 요청 → Popen 1회
  - (R3) `test_report_from_queue_only`: docs 폴더를 지운 뒤에도 `build_report(queue)`가 같은 matrix를 만든다
  - (R3) `test_progress_counters_from_queue`: `GET /crawl/{sid}/status`의 진행 숫자가 큐의 `fetch_level` · `access` 집계와 같다
- [ ] **RED → 구현 → GREEN** → 커밋.

---

## M4 · 실제 채널 어댑터

공통: 파싱 테스트는 녹화 파일만 쓴다(AC-16). 녹화 파일은 `scripts/capture_http_fixture.py <source> <keyword>`로 **한 번** 받아 `backend/tests/fixtures/http/<source>/`에 저장하고, 닉네임 · 작성자 ID를 `사용자A`처럼 가린다.
- 캡처 스크립트는 네트워크가 필요하다. Codex 실행 환경에서 네트워크가 막혀 있으면 Task 보고서에 "캡처 불가"를 적고 멈춘다. 이때 Main Claude가 사용자 기기에서 캡처를 요청한다.
- 녹화본 없이 추측으로 만든 HTML로 테스트를 통과시키지 않는다.

### Task T15: 네이버 카페 · 블로그
- **Produces:** `NaverCafeAdapter`, `NaverBlogAdapter`, `naver_search.search(kind: Literal["cafearticle","blog"], query, start, display=100) -> dict` (base URL은 `naver_search_base_url`).
- **카페 P3:** crawl4ai로 `m.cafe.naver.com` 글 페이지를 렌더링한다. 로그인 · 등급 제한 → `access="restricted"`, 스니펫 문서.
- **블로그 P3:** httpx로 `m.blog.naver.com/{id}/{logNo}`를 받고, 파싱 실패 시 crawl4ai로 다시 받는다. 댓글은 받지 않고 `src_meta.comment_count`만 남긴다.
- [ ] 테스트:
  - `test_cafe_list_parses_items_and_cursor`
  - `test_cafe_detail_body_and_nested_comments`: depth 0/1이 있어야 한다
  - `test_cafe_restricted_page`
  - `test_blog_detail_body_no_comments`
  - `test_search_uses_keyword_only_query`
  - `test_http_403_raises_blocked`
- [ ] RED → 구현 → GREEN → 커밋.

### Task T16: 유튜브
- **Produces:** `YoutubeAdapter`. P1은 yt-dlp Python API `extract_info(f"ytsearch{N}:{kw}", extract_flat=True)`, P3은 `getcomments=True` + `max_comments`. 스레드 단위로 `FetchedDoc`을 여러 개 만든다(`thread_key` = 최상위 댓글 id).
- [ ] 테스트(yt-dlp 반환 dict 녹화본을 monkeypatch):
  - `test_list_returns_videos_as_items`
  - `test_fetch_groups_replies_into_threads`
  - `test_video_meta_in_src_meta_not_title`: `title==""`, `src_meta.video_title`에 영상 제목
  - `test_max_comments_respected`
- [ ] RED → 구현 → GREEN → 커밋.

### Task T17: 뽐뿌 · 클리앙
- **Produces:** `community.CommunityAdapter`(공통: 목록 URL 템플릿 · 파서 훅 · 요청 간격 1초 · 인코딩 처리), `PpomppuAdapter`, `ClienAdapter`. 파서는 selectolax를 쓴다.
- [ ] 테스트(사이트마다):
  - `test_<site>_list_parse`
  - `test_<site>_detail_body_comments`
  - `test_<site>_encoding`: 뽐뿌 EUC-KR이 깨지지 않는다
  - `test_min_interval_enforced`: 가짜 시계로 연속 2요청 사이 ≥1초
- [ ] RED → 구현 → GREEN → 커밋.

---

## M5 · 호환 · 통합

### Task T18: 전처리 호환 · 뒤 단계 폴백 · 통합 테스트
- **Produces:**
  - `preprocessing.preprocess_data`가 활성 버전의 수집본(`crawl/{sid}/collections/{c}/docs/`, parent 체인 포함)을 `read_docs`로 읽는다.
  - 중복 제거는 `doc_id` 기준, 저품질 컷은 본문 길이 기준이다. 스니펫 문서만 기존 기준(제목 5자 · 설명 10자)을 쓴다.
  - 출력에 `desc`(= `body + "\n" + 댓글 텍스트`, 최대 4,000자) · `cafe`(= `src_meta.cafe` 또는 채널 표시 이름) · `link`(= `url`)를 **추가**한다(D-065).
  - `routers/training.py` · `personas.py` · `clustering.py`에서 `bk`/`problemDef`가 비면 `projectContext.bk` / `researchQuestion.text`로 채운다.
  - `routers/integrations.py` `GET /integrations` → `integration_status()`.
- [ ] 테스트 `test_integration_stage0_2.py` (FakeBackend + 가짜 채널 + 합성 CSV 200행)
  - `test_end_to_end_0_to_preprocess` (AC-11 · AC-19 · AC-20 백엔드): `POST /context` → R1~R4 시작 · 확정 → 크롤링 설정(`fixture`) → list → gate → detail(워커를 인프로세스로 실행) → `/preprocess` → `preprocessed/`에 `desc`·`cafe`·`link`가 있다
  - `test_no_api_keys_full_run` (AC-18 백엔드): 모든 키가 비어도 위 흐름이 끝나고 `GET /integrations`가 전부 `connected:false`, 응답 어디에도 키 필드 값이 없다
  - `test_legacy_session_preprocess_still_reads_old_crawl`: 옛 형식 `crawl/{sid}/*.jsonl`만 있는 구버전 세션도 전처리가 돈다(읽기 경로 폴백)
  - `test_downstream_clustering_reads_compat_fields` (D-065 증명 · 엔지니어링 리뷰 F7): 전처리 출력으로 `services/clustering.py`의 군집 함수를 sklearn 경로로 돌리면 예외 없이 샘플에 `desc`·`cafe`가 채워진다
  - (D-078) `test_preprocess_reads_collection_chain`: 활성 버전이 `c2{parent:c1}`을 가리키면 c1 문서 + c2 추가분을 `doc_id`로 합쳐 읽는다(중복 0)
- [ ] RED → 구현 → GREEN `PYTEST -q`(전체) → 커밋.

---

## 프론트엔드 (T19~T23)

프론트는 계산 로직만 Vitest 단위 테스트로 검증하고(엔지니어링 리뷰 R4 · D-071, 02-design 11절 대체), 화면 흐름은 브라우저 QA로 확인한다. 각 Task의 기준은 다음과 같다.
- RED: 해당 브라우저 QA 시나리오가 현재 코드에서 실패하는 것을 기록한다(스크린샷 또는 "요소 없음").
- GREEN: `npm --prefix frontend run lint`와 `npm --prefix frontend run build`가 통과하고, 해당 QA 시나리오가 통과한다.
- 모양은 [`mockups/index.html`](mockups/index.html)과 나란히 놓고 맞춘다. 수치(토큰 · 간격 · 라운드)는 목업 CSS 값을 그대로 쓴다.

### Task T19: 디자인 시스템 기반 · 셸
- **Produces:**
  - `tokens.css`: 목업 `:root` 변수 전부 + 02-design 10절 브라우저 기본 요소 테마. Tailwind 4 `@theme`에 색 · 라운드를 연결한다.
  - `components/ds/`: `Button` `Input` `Select` `Card` `Badge` `Table` `Icon`(lucide-react) `Checkbox` `Switch` `ChoiceChips` `Segmented` `Tabs` `Popover` `Stepper` `Skeleton` `Banner` `InsightCard` `EvidenceMeta` `BarList` `StatGrid` `ProgressBar` — props · 규격은 02-design 10절 표
  - `lib/internalTools.ts`: `export const INTERNAL_TOOLS = process.env.NEXT_PUBLIC_INTERNAL_TOOLS !== "false"`
  - (R4 · D-071) Vitest: `package.json`에 `"test": "vitest run"`, `vitest.config.ts`(environment `node`, include `src/**/*.test.ts`). `frontend/src/lib/logic/` 순수 함수의 RED → GREEN은 T20~T22 각 Task가 자기 함수로 한다. 여기서는 `src/lib/logic/smoke.test.ts` 하나로 러너가 도는 것만 확인한다.
  - T20 `isDirty(saved, current)` · T21 `filterKeywords(kws, filter, query)` · `nextFocus(grid, current, key)` · `roundUi(roundState)` · T22 `channelBars(perSource)` — 각 Task에서 테스트를 먼저 쓴다.
  - 셸: 사이드바 224px(로고, 파이프라인 단계, 현재 세션 · 작업 배지, 내부용 API 버튼)
  - `StepBar` `STEP_MAP`에 새 step 이름을 추가한다
  - 기존 3단계 이후 페이지 본문은 건드리지 않는다
  - 폰트는 번들의 Pretendard 400/600/700/800 otf를 `public/fonts/`로 복사한다
- **QA:** QA-DS

### Task T20: 0단계 화면 · 세션 목록
- **Produces:**
  - `contextLabels.ts`(백엔드 `labels.py`와 같은 키 · 라벨)
  - 0-A/0-B 폼(02-design 4.1, 목업 S1): 인라인 검증, `alert()` 없음, 리서치 질문 템플릿 3종, 제품군 자동 제안 + 출처 배지, `project_context.md` 미리보기(내부용)
  - 세션 목록 작업 배지 · 정렬(4A) · 10초 폴링, 구버전 배지 · 차단 화면
  - 스토어의 `ages/ar/gens/pd` 필드를 `projectContext`로 바꾼다
  - (D-070) 스토어 · `sessionPersist`의 통째 저장 호출(`saveSession(sid, sd)`)을 새 세션에서 없애고 `PATCH /session/{sid}` · 기능별 API로 바꾼다. 공통 컴포넌트 `SaveBar`(임시 저장 · 저장 · 저장되지 않은 변경 표시 · `beforeunload` 경고)를 만들고 0단계 화면에 붙인다. 저장은 검증 통과 시에만 활성화되고, 둘 다 화면을 이동하지 않는다.
- [ ] 백엔드 테스트 `test_labels_parity.py::test_ts_labels_match_python`: `contextLabels.ts`를 정규식으로 읽어 `LABELS`와 키 · 값이 같은지 확인한다(RED: 파일 없음).
- **QA:** QA-1, QA-2, QA-8(구버전)

### Task T21: 1단계 화면
- **Produces:**
  - 목업 S2 · S3 · 상태 모음. 라운드 스테퍼, 방향 지시, 3축 탭, 필터 바(1A, 기본 "판단 필요"), 하위 카테고리 그룹 · 접기(DCX-3 동작 유지)
  - `KeywordChip`(로밍 포커스 11A, Enter/Space 거절, M 이동), `RejectPopover`(태그 4 + 메모, Esc/Enter), 드래그 이동(DCX-2 유지, 축 사이 허용)
  - 수동 추가 · 추천 단어(하위 카테고리 단위), 축 분포, 커버리지 인사이트 카드 + 누락 쿼리 표, 피드백 md 미리보기(내부용)
  - 라운드 작업 3초 폴링 + 스켈레톤(2A), 상태 문구(8.1)
  - (D-070) `SaveBar` 부착. 임시 저장 = 이 라운드의 승인 · 거절 · 메모 선택을 `drafts.keywords.r{n}`에 저장. 저장 = 라운드 확정(`commit`)만 하고 다음 라운드는 시작하지 않는다. primary = "다음 라운드 생성"
- **QA:** QA-3, QA-4, QA-5

### Task T22: 2단계 화면
- **Produces:**
  - 목업 S4 · S5 · S6. 설정(채널 스위치 + 연결 배지, 범위 · 필터, 제품명 필터 기본 꺼짐 + 안내, 고급 접힘), P1 진행
  - 게이트 표(13A: 채널 미니 막대 · 행 펼침 · 고정 머리글 · 300행 초과 가상 스크롤), 예상치
  - P3 진행 · 채널 상태표 · 중단/차단 배너 + 이어서 진행, P5 요약 → 전처리
  - (D-070) 설정 화면과 게이트 화면에 `SaveBar`. 임시 저장 = 설정 초안 · 게이트 제외 선택을 `drafts.crawl`에 저장, 저장 = `PUT /crawl/{sid}/config` · 제외 목록 확정. primary는 "목록 수집 시작" / "상세 수집 시작"
- **QA:** QA-6, QA-7

### Task T23: 내부용 API 드로어 · 뒤 단계 화면 폴백
- **Produces:**
  - `IntegrationsDrawer`: 너비 360, 라운드 18. API별 상태 · 영향 기능 · 환경변수 이름 · 다시 확인. `INTERNAL_TOOLS`가 false면 렌더링하지 않는다.
  - 학습 · 페르소나 화면은 `bk` · `pd`를 `projectContext`에서 읽는다.
- **QA:** QA-9

---

### Task T24: 버전 선택 · "이 단계부터 다시" · 비교 화면 (D-075 · D-078)
- **Produces:**
  - 사이드바 버전 선택 + 버전 목록 드로어(02-design 4.1)
  - 각 단계 화면 헤더의 "이 단계부터 다시"(메모 팝오버 → 새 버전 → 그 단계 화면)
  - `stale` 배너, 읽기 전용 버전 배너 + 입력 비활성
  - `/pipeline/compare?a=&b=` 비교 화면(목업 S8: 단계 탭, 키워드 추가 · 삭제 · 이동 표, 축 분포 차이, 수집본 정보)
  - 크롤링 화면의 "기존 수집본 사용 중 · 추가된 키워드 n개" 안내 + "추가된 키워드만 수집"
- [ ] Vitest `compareView(diff)` 순수 함수(추가 · 삭제 · 이동 정렬과 배지 매핑)부터 쓴다.
- **QA:** QA-V

## 브라우저 QA 계획

**실행(로컬 전용, 키 없음 · 가짜 LLM · 가짜 채널):**
```bash
cd backend && STORAGE=local LOCAL_DATA_DIR=/tmp/dcx-qa LLM_BACKEND=fake ENABLE_FIXTURE_CHANNEL=true FIXTURE_CORPUS_PATH=tests/fixtures/aircon_qa.csv .venv/bin/uvicorn app.main:app --port 8000
cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_INTERNAL_TOOLS=true npm run dev
```
- 테스트 URL: `http://localhost:3000/pipeline/start`
- `tests/fixtures/aircon_qa.csv`: 원본 CSV에서 앞 2,000행을 뽑은 샘플이다(git 제외). 원본이 없으면 T18의 합성 샘플 생성기로 만든다.
- 도구: gstack `qa-only` (읽기 전용 보고서). 해상도 1440×900과 1024×768 두 가지.

| ID | 시나리오 | 기대 결과 | AC |
|---|---|---|---|
| QA-DS | 셸 · 컴포넌트: Tab으로 사이드바 → 본문 이동, 포커스 링 2px 액션 블루, 체크박스 · select · 선택색 테마 | 목업과 토큰 일치, 포커스가 항상 보임 | AC-21 |
| QA-1 | 0단계: 필수값 비우고 시작 → 인라인 오류 · 첫 오류 칸 포커스 → 채우고 시작 → 새로고침 | 값 복원, 키워드 화면 이동 | AC-01 |
| QA-2 | 제품군 "다시 제안" (쇼핑 미연결) | "추정" 배지, 3칸 편집 가능 | AC-03 · AC-18 |
| QA-3 | R1 생성 중 새로고침 → 다른 화면 → 복귀 | 같은 작업 결과가 뜨고 중복 생성 없음, 스켈레톤 · 경과 시간 표시 | 2A |
| QA-4 | 키보드만으로 R2 검토: 그룹 Tab, 화살표, Enter 거절 → 태그 선택 → Enter, M으로 이동 | 이벤트 기록, 피드백 md에 반영, 포커스 복귀 | AC-06 · AC-07 |
| QA-5 | R2 확정 → R3 커버리지 화면(미연결) → R3 · R4 → 최종 | 커버리지 "미연결" 안내, R4 항상 실행, 필터 "판단 필요" 기본값 | AC-05 · AC-08 · AC-09 |
| QA-6 | 크롤링 설정(가짜 채널) → 목록 수집 → 게이트: 배지 행 모두 제외 → 상세 수집 | 제외 키워드 URL 미수집, 채널 막대 · 행 펼침 동작 | AC-10 · AC-11 · AC-14 |
| QA-7 | 상세 수집 중 백엔드 워커 kill → 화면 | "중단됨" 배너 → 이어서 진행 → 완료, 세션 목록 맨 위 배지 | AC-12 · 4A |
| QA-8 | 구버전 세션을 0~2단계에서 열기 | 편집 차단 화면 + "전처리 화면으로" | G1 |
| QA-9 | 사이드바 외부 API 버튼 → 드로어 / `NEXT_PUBLIC_INTERNAL_TOOLS=false`로 재빌드 | 키 값 없음 / 내부용 요소 DOM에 없음 | AC-18 · 12 |
| QA-R | (R5 회귀) 수동 추가 → 검색량 표시, 같은 키워드 다시 추가 → 중복 경고, 추천 단어 클릭 추가, 드래그로 다른 축의 하위로 이동, 새 하위 카테고리(축 선택 필수), 그룹 접기 · 모두 접기, 하위 카테고리 10개 이상이면 자동 접기 | 기존 DCX-2 · DCX-3 동작이 3축 구조에서 모두 된다 | AC-06 |
| QA-V | (D-075 · D-078) 키워드 화면에서 "이 단계부터 다시" → 메모 입력 → v2 생성 → 키워드 2개 추가 · 1개 삭제 → 비교 화면에서 v1 대비 변경이 보인다 → 크롤링 화면에서 "추가된 키워드만 수집" → 새 수집본 c2, v1은 읽기 전용으로 열린다 | 버전 · 수집본 구조대로 동작, 과거 버전은 편집 불가 | D-075 · D-078 |
| QA-10 | 1024×768 · 200% 확대 | 사이드바가 아이콘 폭, 카드 12열로 쌓임, 가로 스크롤 없음 | 10절 |

## 리뷰 계획
- Task마다: Claude가 해당 Task의 diff를 읽기 전용으로 명세(이 계획 · 02-design)와 품질 기준으로 리뷰하고, 결과를 `reports/T##.md`에 적는다. 수정은 Codex에 재위임한다.
- 전체 브랜치: gstack `review`(읽기 전용) + 별도 Codex 읽기 전용 리뷰 1회.
- UAT 때 사용자와 함께: 키워드 1~2개로 실제 카페 · 블로그 · 유튜브 · 뽐뿌 · 클리앙 소량 수집(자동 기준 아님, 01 문서 5절).

## 검증 명령 (harness configure)
```
[["backend/.venv/bin/python","-m","pytest","backend/tests","-q"],
 ["npm","--prefix","frontend","run","lint"],
 ["npm","--prefix","frontend","run","build"],
 ["npm","--prefix","frontend","test"]]
```
- pytest는 저장소 루트에서 실행되므로 `backend/pytest.ini`의 `rootdir`와 `pythonpath = .`(backend 기준)를 T01에서 설정한다. 루트 실행용으로 `backend/tests/conftest.py`가 `sys.path`에 `backend/`를 넣는다.

## 되돌리기
- 모든 작업은 worktree의 `feature/dcx2-stage0-2` 브랜치에서 한다. `main`은 건드리지 않는다. 전체 취소는 브랜치와 worktree를 버리면 된다(병합 전).
- Task마다 커밋이 하나 이상이다. 특정 Task는 `git revert <커밋>`으로 되돌린다. 옛 라우터 삭제(T09 · T14)는 각자 커밋으로 분리해 따로 되돌릴 수 있게 한다.
- 데이터는 `data/`(git 제외)에만 쓴다. QA 데이터는 `/tmp/dcx-qa`를 쓴다. 기존 세션 파일 형식은 바꾸지 않는다(구버전은 읽기 전용).
- 설정 기본값 변경(`storage=local`)은 `.env`에서 `STORAGE=s3`로 되돌릴 수 있다.

## 수용 기준 연결
| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| 01 | T20 · QA-1 | 08 | T06 · T09 | 15 | T10 · T13 |
| 02 | T04 | 09 | T08 · QA-5 | 16 | T15 · T16 · T17 |
| 03 | T04 · QA-2 | 10 | T11 · T14 | 17 | T02 |
| 04 | T02 | 11 | T13 · T14 · T18 | 18 | T18 · QA-2 · QA-9 |
| 05 | T06 · T09 | 12 | T13 · QA-7 | 19 | T18 |
| 06 | T05 · T21 · QA-4 | 13 | T10 · T11 · T13 | 20 | T18 · QA-6 |
| 07 | T07 · QA-4 | 14 | T11 · T14 · QA-6 | 21 | 검증 명령 |

---

## 엔지니어링 리뷰 (plan-eng-review, 2026-09-29)

대상: 이 문서(03-plan.md). 설계 기준: 02-design.md. 파일을 직접 읽어 확인한 현재 코드는 `backend/app/routers/sessions.py`, `frontend/src/stores/useSessionStore.ts`, `backend/app/services/*.py`이다.

**범위 기록:** 기능 축소 제안 없음. 파일 배치 = Original arrangement (D2 답변, 2026-09-29). 수용 범위 = 이 계획의 T01~T23 그대로. 미결 remedy: R1~R5.

**질문 없이 반영한 것 (이미 승인된 동작의 필수 설정 · 증명):**
- F3 `[P2] (confidence: 8/10) 03-plan.md:85` — crawl4ai는 Playwright Chromium이 있어야 렌더링된다. T01 Step 2에 `crawl4ai-setup`을 추가했다(카페 렌더링은 D-033 · 02-design 6.2에서 승인됨).
- F7 `[P2] (confidence: 8/10) 03-plan.md T18` — D-065("뒤 단계 코드를 건드리지 않고 끝까지 돈다")의 증명이 전처리에서 멈춰 있었다. 군집 단계가 호환 필드를 읽는 테스트를 T18에 추가했다.

## Decision ledger

### R1: 화면의 세션 전체 덮어쓰기
Finding: F1 · [P1] · confidence 9/10 · `backend/app/routers/sessions.py:14` `save_json(f"sessions/{req.sid}/session.json", req.data)` + `frontend/src/stores/useSessionStore.ts:102` `saveSession(sid, updated);` · reviewer: Claude
Plan baseline: T04는 `update_session`(잠금 + 병합)을 만들지만 `/save-session`은 그대로 둔다(원래 제안).
Runtime evidence: 현재 프론트는 세션 객체 전체를 보내 파일을 통째로 덮어쓴다(코드 확인).
State: approved
Actual answer: A + 사용자 추가 요구 "중간에 임시 저장 버튼도 두고 저장 버튼도 두면 좋겠다" (D3, 2026-09-29)
Accepted scope: (1) ~~schemaVersion 2 세션에 `/save-session`(통째 저장)을 보내면 409~~ → R6(D8)에서 "서버 소유 키 보호 + 나머지 병합"으로 대체. 구버전 세션은 기존 방식 유지. (2) 화면 쓰기는 기능별 API와 `PATCH /session/{sid}` (허용 키: `step`, `drafts.*`)만 쓰고 모두 `update_session`을 거친다. (3) 화면마다 "임시 저장"(검증 없이 `drafts.{screen}`에 초안 저장, 이동 없음) · "저장"(검증 후 확정 저장, 이동 없음) 버튼 + 기존 primary 이동 버튼 하나. (4) 저장되지 않은 변경이 있으면 "저장되지 않은 변경 있음" 표시 + 페이지 이탈 경고. 테스트: `test_full_save_rejected_for_v2`, `test_step_patch_keeps_rounds`, `test_draft_roundtrip_per_screen`. 작업: T04(백엔드) · T20 · T21 · T22(화면).

### R2: SQLite 동시 접근 규칙
Finding: F2 · [P1] · confidence 7/10 · `03-plan.md:9` "SQLite(WAL)" · T11 · T13 · T14 — 목록 워커 · 상세 워커 · API 상태 조회 · 리포트가 같은 `queue.sqlite`를 쓰는데 잠금 대기 규칙이 없다.
Plan baseline: WAL 모드만 명시.
Runtime evidence: 미구현 코드라 관측 불가(unknown). 설명 중 정정: 목록 · 상세 수집기는 동시에 돌지 않고(P1 → 게이트 → P3), WAL에서 읽기는 쓰기를 막지 않는다. 실제 충돌은 쓰기끼리 겹칠 때(200건 완료 기록 vs 정지 요청 · heartbeat · 게이트 제외 저장)뿐이다.
State: approved
Actual answer: A 기다렸다 쓰기 (D4 확인 2, 2026-09-29). 사용자 확인: 큐 파일은 프로젝트마다 따로 둔다(이미 설계대로).
Accepted scope: 모든 SQLite 연결에 `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=10000; PRAGMA synchronous=NORMAL`. 프로세스마다 자기 연결을 쓴다. 쓰기 트랜잭션은 200건 배치 단위로 짧게 한다. API 상태 조회는 읽기 전용 연결(`mode=ro`)을 쓴다. 테스트 T11 `test_concurrent_writers_no_locked_error`: 프로세스 3개가 5초 동안 동시에 써도 `OperationalError` 0건.

### R3: P5 리포트 계산 방식
Finding: F4 · [P2] · confidence 8/10 · `02-design.md:428` "리포트는 P3 진행 중에도 1분마다 갱신한다" + `03-plan.md:395` `report.build_report(queue, docs_dir)` — docs 폴더(100만 건이면 수 GB)를 1분마다 다시 읽는다.
Plan baseline: 큐 + docs 폴더를 읽어 계산.
Runtime evidence: unknown(미구현).
State: approved
Actual answer: 사용자 지정 "라운드(단계)가 끝날 때마다 그때 집계된 것 기준으로만" (D7, 2026-09-29)
Accepted scope: (1) 게이트 표는 P1이 끝날 때 한 번, 최종 P5 리포트는 P3가 끝날 때 한 번 생성한다. 1분마다 다시 만드는 갱신은 없앤다. (2) 진행 중 화면은 큐의 단순 카운터(완료/대상, full · snippet · restricted 비율, 분당 처리량, 채널 상태)만 보여 준다. 이를 위해 `urls` 행에 `fetch_level` · `access` · `doc_count`를 `mark_done`과 같은 트랜잭션에서 적는다. (3) 리포트 계산은 큐 집계 쿼리로 하고 docs 폴더를 읽지 않는다. 테스트 T14 `test_report_built_on_phase_end_only` · `test_report_from_queue_only` · `test_progress_counters_from_queue`.

### R4: 프론트 순수 로직 단위 테스트
Finding: F5 · [P2] · confidence 7/10 · `02-design.md:607` "테스트 러너는 추가하지 않는다" — 필터 규칙 · 로밍 포커스 · 라운드 상태 전환 · 게이트 막대 계산이 브라우저 QA로만 검증된다. 설계 승인된 결정을 재검토하는 이유: 디자인 리뷰 1A · 2A · 11A · 13A로 프론트 로직이 설계 당시보다 크게 늘었다.
Plan baseline: 테스트 러너 없음(02-design 11절, 설계 동의 범위).
Runtime evidence: 프론트 테스트 0개(현재 package.json에 test 스크립트 없음).
State: approved
Actual answer: A 계산 로직만 단위 테스트 (D6, 2026-09-29) · 02-design 11절 "테스트 러너 없음"을 이 결정으로 대체
Accepted scope: T19에서 Vitest(`vitest`, jsdom 불필요 · node 환경) 추가, `npm test` = `vitest run`. 화면 로직을 순수 함수로 분리해 `frontend/src/lib/logic/*.ts`에 두고 `*.test.ts`로 검증: `filterKeywords`(판단 필요 = llm_only ∪ low_volume ∪ misclassified 의심), `nextFocus`(로밍 포커스 화살표 · Home/End), `roundUi`(라운드 상태별 버튼 활성), `channelBars`(0건 점선 · 비율), `isDirty`(저장되지 않은 변경 감지, D-070). 검증 명령에 `["npm","--prefix","frontend","test"]` 추가.

### R5: DCX-2/DCX-3 회귀 계약
Finding: F6 · [P1] · confidence 9/10 · T21이 `CategoryInputPanel` · `NewCategoryInput` · `KeywordTag` · `DuplicateAlertCard`를 삭제하고 새로 만든다. 기존 동작(수동 추가 후 검색량 비동기 조회, 중복 경고, 추천 단어 추가, 드래그 이동, 하위 그룹 접기 · 모두 접기 · 10개 이상 자동 접기)을 지킬 기준이 없다.
Plan baseline: "DCX-2 · DCX-3 동작 유지"라는 문장만 있음.
Runtime evidence: 현재 동작은 `frontend/src/app/pipeline/keywords/page.tsx:152-240`에 있음(코드 확인).
State: approved
Actual answer: A 6개 모두 계약 + 백엔드·브라우저 확인 (D5, 2026-09-29)
Accepted scope: 지킬 동작 ①~⑥(수동 추가 → 검색량 조회, 중복 경고, 추천 단어 추가, 드래그 이동, 새 하위 카테고리, 접기 · 모두 접기 · 10개 이상 자동 접기). 의도된 변경: 카테고리 → 3축 하위, 새 하위는 축 필수, 검색량은 키워드 단독. 백엔드 테스트 T09 `test_manual_add_scores_volume` · `test_manual_add_duplicate_409` · `test_suggested_word_origin_recorded` · `test_custom_sub_requires_axis`, 브라우저 QA-R(드래그 이동 · 접기 3종 · 자동 접기 기준을 하위 카테고리 10개 이상으로).

### R6: 3단계 이후 화면의 통째 저장 (R1 재검토)
Finding: Codex #1 · [P1] · confidence 9/10 · `frontend/src/app/pipeline/labeling/page.tsx:62` `await saveSession(sid!, updated ...)` — 전처리 · 라벨링 · 학습 · 클러스터링 · 페르소나 화면도 통째 저장을 쓴다. R1대로 거부하면 새 세션에서 라벨 결과가 저장되지 않아 학습이 멈춘다.
Plan baseline: R1 approved (통째 저장 409).
Runtime evidence: `grep saveSession` 결과 9개 파일(코드 확인).
State: approved
Actual answer: D8 A "보호 항목만 지키고 나머지 병합" + 사용자 원칙 "모든 결과는 임시 저장이나 저장을 무조건 만들어야 한다" (2026-09-29)
Accepted scope: `/save-session`은 거부하지 않고 서버 소유 키를 버린 뒤 병합(T04 테스트 2개). 0~2단계 새 화면은 R1대로 부분 저장 + 임시 저장 · 저장 버튼. 3단계 이후 화면은 개편 때 같은 구조로 옮긴다(D-070 보완).
History: R1의 "409 거부"는 이 결정으로 대체.

### 질문 없이 반영한 Codex 지적 (이미 승인된 동작의 필수 구현)
- #3 문서 유실 방지(fsync 후 done) → AC-12 · D-033. T13 `test_fsync_before_done`.
- #5 R4 추가 생성 회차 ID → 02-design 5.2 승인 동작. T09 `test_r4_regen_gen_ids_unique`.
- #6 게이트 저장/시작 분리 → D-070. T14 `test_gate_save_does_not_start_detail`.
- #7 죽은 run의 lease 회수 → AC-12. T11 `test_dead_run_leases_reclaimed`.
- #8 작업 시작 원자성 → 2A · D-062. T09 · T14 동시 요청 테스트.
- #2 목록 재수집 시 스냅샷 경계 → 사용자 결정 D-078(수집본 모듈)로 해소. T14 `test_new_list_creates_new_collection`, T18 `test_preprocess_reads_collection_chain`.

### R7: 여러 키워드가 같은 글을 찾았을 때의 제외 규칙
Finding: Codex #4 · [P1] · confidence 8/10 · 02-design 6.3 "같은 URL이 여러 키워드에서 나오면 처음 발견한 키워드로 한 행만" + 6.6 "제외한 키워드의 URL을 excluded로"
Plan baseline: 대표 키워드(처음 발견) 기준으로 제외.
Runtime evidence: unknown(미구현).
State: approved
Actual answer: 사용자 설명 "이중 크롤링을 방지하려고 URL부터 모으고 URL마다 원문을 수집하는 것이니 중복이 애초에 없다. 키워드당 원문 개수 카운팅은 중복으로 해도 된다." (D9, 2026-09-29) → A와 같은 규칙
Accepted scope: URL은 한 번만 수집한다. URL은 그것을 찾은 키워드가 모두 제외됐을 때만 `excluded`. 문서에 `kw`(확정 순서가 가장 앞선 남은 키워드) + `kw_hits[]`(찾은 키워드 전부)를 남긴다. 키워드별 원문 수는 `kw_hits` 기준으로 중복 포함 집계한다. T11 `test_shared_url_excluded_only_if_all_hits_excluded` · T14 `test_per_keyword_counts_include_shared`.

Approval readiness: PASS — R1(D3, R6로 보완) · R2(D4) · R3(D7) · R4(D6) · R5(D5) · R6(D8) · R7(D9), 범위 기록(D2). 보류 · 미결 없음.

### 테스트 커버리지 (계획 기준)
```
CODE PATHS                                         USER FLOWS
[+] app/llm (T02)                                  [+] 0단계 입력 → 키워드 화면
  ├── compose / extract_json   [★★★ 계획]           ├── [★★★ QA-1] 인라인 검증 · 새로고침 복원
  ├── openai_api / codex_exec  [★★★ 계획]           └── [★★  QA-2] 제품군 추정
  └── retry · timeout · 격리   [★★★ 계획]          [+] 1단계 검토
[+] app/context (T03 T04)                            ├── [★★★ QA-3] 생성 중 새로고침 · 중복 없음
  ├── update_session 잠금·병합 [★★★ 계획]           ├── [★★★ QA-4] 키보드 검토 · 이벤트
  ├── 버전 생성·stale·읽기전용 [★★★ 계획]           ├── [★★★ QA-R] DCX-2/3 회귀 6개
  └── 통째 저장 병합(D8)       [★★★ 계획]           └── [★★  QA-5] R3 커버리지 · R4
[+] app/keywords (T05~T09)                         [+] 2단계 수집
  ├── 라운드 작업·회차·동시시작 [★★★ 계획]           ├── [★★★ QA-6] 게이트 제외 · 막대 · 펼침
  └── 커버리지 ①②⑥⑦            [★★★ 계획]           ├── [★★★ QA-7] kill → 이어서 진행
[+] app/crawl (T10~T17)                              └── [★★  QA-V] 버전 · 추가 키워드 수집
  ├── 큐 동시쓰기·lease·제외    [★★★ 계획]          [+] 오류 · 빈 상태
  ├── fsync·재개·병렬·파싱실패  [★★★ 계획]           └── [★★  상태 모음 8.1] 각 상태 문구
  └── 어댑터 5종 (녹화 응답)    [★★  계획]
[+] 뒤 단계 호환 (T18)          [★★★ 계획]  → 군집까지
LLM 프롬프트 품질: [GAP] [→EVAL] R1~R4 결과 품질 평가 없음 — 사용자가 A/B 평가를 백로그로 보냄(B-003)
```
실제 사이트 파서는 녹화 응답으로만 검증된다. 사이트 구조가 바뀌면 `healthcheck`가 알려 주고, UAT 때 소량 실제 수집으로 확인한다.

### 실패 모드
| 경로 | 현실적인 실패 | 대응 · 테스트 | 사용자에게 보이나 |
|---|---|---|---|
| 라운드 생성 | 응답 JSON이 깨짐 | 1회 재시도 → `parse` 오류(T02) | 예: "R2 생성에 실패했습니다(원인: 응답 형식 오류)" |
| 세션 저장 | 화면 · 서버 동시 쓰기 | 잠금 + 병합 · 보호 키(T04) | 해당 없음(유실 없음) |
| 버전 생성 | 작업 진행 중 분기 | 409(T04) | 예: "진행 중인 작업이 끝난 뒤 다시 시도하세요" |
| 상세 수집 | 강제 종료 | fsync 후 done · lease 회수(T11 · T13) | 예: "중단됨 · 이어서 진행" |
| 상세 수집 | 사이트 구조 변경 | 파싱 실패율 30% → `paused_parse_error` · healthcheck(T13) | 예: 채널 상태 칩 |
| 상세 수집 | 차단(429) | 채널만 멈춤(T13) | 예: "차단으로 멈춤" |
| 큐 | 쓰기 겹침 | busy_timeout(T11) | 해당 없음 |
| 전처리 | 수집본 체인 중복 | `doc_id` 병합(T18) | 해당 없음 |
치명적 공백(테스트 · 처리 · 표시 모두 없음): 0건.

### 범위 밖 (이번 리뷰에서 뒤로 미룬 것)
- 수집본 디스크 정리(B-008), 3단계 이후 세부 버전 비교(B-009), 프롬프트 A/B 평가(B-003), 채널 간 규모 균형(B-001).
- 3단계 이후 화면의 저장 방식 전환: 해당 단계 개편 때(D-070 보완).

### 이미 있는 것 (재사용)
- `app/services/s3.py` 로컬 저장 백엔드(DCX-16), `frontend/src/lib/usePolling.ts`, `sessionPersist`, DCX-2/3 로직(회귀 계약 R5로 동작 보존), `utils/text.clean_text`, cvc-agent의 codex exec 레인 패턴.

### 병렬 작업 계획
| 단계 | 모듈 | 의존 |
|---|---|---|
| 기반 | backend 설정 · tests 기반 | — |
| LLM | `app/llm` | 기반 |
| 입력 · 버전 | `app/context` · `app/external` | LLM |
| 키워드 | `app/keywords` | 입력 |
| 수집 | `app/crawl` · adapters | 기반 |
| 호환 | `app/services/preprocessing` · 뒤 단계 라우터 | 키워드 · 수집 |
| 화면 | `frontend/src` | 각 백엔드 API |
- 레인 A: LLM → 입력 · 버전 → 키워드. 레인 B: 수집 기반 → 워커 → 어댑터 3종(서로 병렬). 레인 C: 디자인 시스템 기반.
- A · B · C를 동시에 시작한다. A와 B가 끝나면 호환 작업을 한다. 화면 Task는 해당 API가 끝난 순서대로 붙인다.
- 충돌 주의: `backend/app/main.py`(T04 · T09 · T14)는 순차로 한다. 셸 사이드바(T19 → T24)도 순차다.

### 완료 요약
- Step 0 범위: 그대로 수용(파일 배치 원안)
- 아키텍처: 2건(R1 · R2) + Codex 8건
- 코드 품질: 0건(부록 1건: 라벨 동기화 정규식 · 신뢰도 6)
- 테스트: 다이어그램 작성, 공백 2건(R4 · R5) + [→EVAL] 1건(백로그)
- 성능: 1건(R3)
- 범위 밖 · 이미 있는 것: 작성
- TODOS.md: 새 항목 없음(backlog.md가 대신함)
- 실패 모드: 치명적 공백 0건
- 미결 결정: 0건
- 외부 의견: Codex 완료(8건, 전부 반영)
- 병렬: 레인 3개
- 도중 사용자 기획 변경: G1 → 버전 관리(D-075 · D-078), G3 → GPT API 기본(D-076), 병렬 크롤링(D-077), 저장 원칙(D-070 보완)

### 부록 · 보류한 발견
- [P3] (confidence: 6/10) T20 `test_labels_parity.py` — TS 라벨 파일을 정규식으로 읽는 방식은 형식이 바뀌면 깨지기 쉽다. 필요하면 Python에서 TS를 생성하는 방식으로 바꾼다.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | codex (plan-eng-review outside voice) | Independent 2nd opinion | 1 | completed | 8 findings, all resolved |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open (mapped to tasks) | 14 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 5/10 → 9/10, 13 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex · plan-review · completed · 8 findings (5 carried forward as required proof, 3 decided with user).
- **VERDICT:** DESIGN CLEARED. ENG review complete with all findings mapped to tasks; status issues_open reflects mapped work, not open decisions. Design doc was revised (r2) after its design review; version UI (S8) was added without a second design review.

NO UNRESOLVED DECISIONS
