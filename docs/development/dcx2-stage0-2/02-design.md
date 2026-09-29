# 02 · 설계 — DCX 2.0 0~2단계 개편

- 기준: 승인된 [`01-brainstorm.md`](01-brainstorm.md) (2026-09-28 제품 승인) · 결정 원장 [`decision-log.md`](decision-log.md)
- 표기: `AC-xx`는 01 문서의 수용 기준, `D-xxx`는 결정 기록.
- 이 문서의 새 결정은 모두 `decision-log.md`의 D-06x에 요약해 둔다.

### 개정 이력
- **r2 (2026-09-29):** 사용자가 01의 가정 G1 · G3을 바꿨고(D-075~078), 엔지니어링 리뷰 결과(D-070~074, Codex 지적 #3~#8)를 반영했다. 바뀐 곳은 다음과 같다.
  - 2.1 · 2.2 · 2.2.1(신설): 세션 버전(통째 복사) · 크롤링 수집본 모듈 · 저장 원칙
  - 3.1 · 3.2: LLM 기본 백엔드 `openai_api`
  - 4.1: 버전 선택 · "이 단계부터 다시" · 비교 화면
  - 5.2: R4 추가 생성 회차
  - 6.1 · 6.2 · 6.3 · 6.4 · 6.6 · 6.7: 병렬 크롤링 · 채널 점검 · 유실 방지 · lease 회수 · 공유 URL 제외 규칙 · 게이트 저장/시작 분리 · 단계 끝 리포트
  - 7: 버전 · 부분 저장 · 추가 수집 · 게이트 API
  - 01의 G1("구버전은 열람만")은 옛 입력 형식 세션에만 적용되고, G3("기본 Claude API")은 D-076으로 대체된다.

---

## 1. 전체 구조

```
[프론트 Next.js]  start ─ keywords ─ crawling ─ (preprocess 이후 기존 화면)
        │ REST
[백엔드 FastAPI]
  app/context/     0단계: ProjectContext 모델 · project_context.md 생성 · 제품군 제안
  app/llm/         LLM 공통 층: claude_api | codex_exec 백엔드 · 맥락 첨부
  app/keywords/    1단계: 3축 분류 · 라운드별 프롬프트 · HITL 이벤트 · 피드백 md · 검색량 · 커버리지
  app/external/    외부 API 어댑터(검색광고 · 쇼핑 · 검색 · YouTube Data). 키가 없으면 "미연결"
  app/crawl/       2단계: 채널 어댑터 · SQLite 큐 · P1/P3 워커(별도 프로세스) · 필터 · 정규화 · 리포트
  app/services/preprocessing.py   새 스키마 → 기존 필드 호환(최소 수정)
        │
[로컬 디스크 data/]  sessions/{sid}/…  crawl/{sid}/…  llm_runs/{run_id}/…
```

**원칙**
- 판단이 필요 없는 일(필터 · 정규화 · 큐 · 지표 계산)은 결정론적 코드로 한다. LLM은 생성 · 분류만 한다(1단계 기획 "LLM에게 숫자를 맡기지 않는다").
- 모든 외부 호출은 어댑터 뒤에 둔다. 테스트는 가짜 어댑터를 쓰고 네트워크를 쓰지 않는다.
- 저장소는 기존 `app/services/s3.py`의 로컬 백엔드(`storage=local`, DCX-16)를 쓴다. `.env` 기본값을 `storage=local`로 바꾼다(D-002).
- 새 코드는 새 패키지에 둔다. 기존 `routers/keywords.py`, `services/crawling.py`, `services/naver.py`는 새 모듈을 부르는 얇은 층으로 바꾸거나 새 라우터로 대체한다.

---

## 2. 데이터 모델

### 2.1 세션 파일 배치

```
data/sessions/{sid}/
  meta.json                     # activeVersion, versions[{id, parent, restartFrom, createdAt, note, readonly}]
  versions/v1/                  # 버전 = 세션 내용 통째 복사본 (D-078)
    session.json                #   schemaVersion: 2
    project_context.md          #   0단계 입력으로 생성 (D-017)
    keyword_events.jsonl        #   HITL 이벤트 원본 (D-022)
    keyword_feedback.md         #   이벤트 요약 · 라운드마다 재생성
  versions/v2/ …
data/crawl/{sid}/collections/   # 크롤링 수집본 = 버전과 분리된 모듈, 만든 뒤 변경하지 않음 (D-078)
  c1/
    manifest.json               #   {id, parent: null|"c1", keywords[], channels[], config, snapshotId, status, createdAt}
    queue.sqlite                #   P1/P3 큐 · 스냅샷 · 워커 상태
    docs/part-00001.jsonl       #   P4 정규화 문서 (5,000건 단위 샤드)
    report.json                 #   P5 리포트 (단계 끝에 한 번, D-074)
  c2/ …                         #   "추가된 키워드만 수집" = parent c1 + 추가분
data/llm_runs/{run_id}/         # codex_exec 백엔드 작업 폴더 (3.3절)
```

### 2.2 `session.json` (schemaVersion 2)

```jsonc
{
  "schemaVersion": 2,
  "sid": "s1759...",
  "step": "start | r1 | r2 | r3 | r4 | kw-final | crawl-setup | crawl-list | crawl-gate | crawl-detail | crawl-done | preprocess-setup | …",
  "projectContext": { … 2.3 … },
  "knownInsights": [{ "id": "ki_01", "type": "statement", "text": "…", "from": "stage0" }],
  "keywords": [ … 2.4 … ],
  "keywordRounds": {
    "1": { "status": "done", "promptVersion": "r1.v1", "generated": 78, "approved": 61, "at": "…" },
    "3": { "status": "done", "promptVersion": "r3.v1",
           "inputs": { "distribution": "ok", "rejection": "empty:no_rejections",
                       "coverage": "empty:searchad_unconnected" } }
  },
  "coverage": { … 5.5 … },
  "crawlConfig": { … 6.8 … },
  "version": "v2", "parentVersion": "v1", "restartFrom": "stage1",
  "collectionId": "c1",           // 이 버전이 쓰는 크롤링 수집본
  "stale": { "stage3": "stage1 changed in v2" },   // 윗단계가 바뀐 뒤 그대로 가져온 결과 표시
  "drafts": { "start": {…}, "keywords": {…}, "crawl": {…} }   // 임시 저장 (D-070)
}
```

- **저장 원칙 (D-070 보완, D8):** 어느 단계 결과든 "임시 저장"(초안, `drafts`) 또는 "저장"(확정)으로 남고, 서버가 거부해서 사라지는 결과는 없다. 0~2단계 화면은 기능별 API로 부분 저장한다. 3단계 이후 기존 화면이 보내는 통째 저장은 받아 주되, 서버가 쓰는 칸(`projectContext` · `knownInsights` · `keywords` · `keywordRounds` · `coverage` · `crawlConfig` · `collectionId` · `version*` · `drafts`)은 무시하고 나머지만 파일 잠금 안에서 합친다.
- **구버전 세션(G1):** `schemaVersion`이 없으면 구버전이다. 목록에 "구버전" 배지를 달고, 0~2단계 화면에서는 편집을 막는 안내만 보여 준다. 3단계 이후 화면은 기존대로 열린다. 변환은 하지 않는다.
- `allKw`, `bk`, `problemDef` 같은 옛 키는 새 세션에 쓰지 않는다. 뒤 단계가 `bk`와 `problemDef`를 읽는 곳은 `projectContext`에서 가져오게 바꾼다(`bk` → `projectContext.bk`, `problemDef` → `projectContext.researchQuestion.text`).

### 2.2.1 버전 · 수집본 규칙 (D-075 · D-078)
- **버전 만들기:** `POST /sessions/{sid}/versions {from: "v1", restartFrom: "stage0|stage1|stage2|stage3|…", note}`
  - 원본 버전 폴더를 통째로 복사해 새 버전 폴더를 만든다(수집본은 복사하지 않고 `collectionId`만 따라간다).
  - 새 버전에서 `restartFrom` 이후 단계 결과는 지우지 않고 `stale`로 표시한다. 그 단계를 다시 저장하면 `stale` 표시가 풀린다.
  - `meta.activeVersion`이 새 버전으로 바뀐다. 이전 버전은 `readonly: true`가 되어 열람만 된다(되살리려면 그 버전에서 다시 새 버전을 만든다).
- **수집본 재사용:** 새 버전은 원본의 `collectionId`를 그대로 쓴다. `restartFrom=stage2`이면 수집 설정 화면부터 새로 하고 새 수집본을 만든다.
- **추가된 키워드만 수집:** 키워드가 바뀐 버전에서 "추가된 키워드만 수집"을 누르면 현재 수집본에 없는 키워드만으로 P1 → 게이트 → P3를 돌려 새 수집본 `c2 {parent: "c1"}`을 만든다. 전처리는 `c2`를 읽을 때 `c1` 문서 + `c2` 추가분을 `doc_id`로 합쳐 읽는다. `c1`은 바뀌지 않는다.
- **수집본 삭제 없음:** 수집본은 어떤 버전이 가리키고 있으면 지우지 않는다. 디스크 정리는 이번 범위 밖(backlog B-008).
- **비교:** `GET /sessions/{sid}/compare?a=v1&b=v2&stage=stage1`
  - stage0: 필드별 전/후
  - stage1: 키워드 추가 · 삭제 · 축 이동 목록 + 축 분포 차이
  - stage2: 수집본이 다르면 키워드 × 채널 건수 차이, 같으면 "같은 수집본"
  - stage3 이후: 이번에는 "결과 파일이 다름/같음"과 저장 시각만(해당 단계 개편 때 세부 비교)
- **동시성:** 버전 만들기 · 활성 버전 전환은 `meta.json` 파일 잠금 안에서 한다. 작업(라운드 생성 · 수집 워커)이 돌고 있는 버전에서는 새 버전을 만들 수 없다(409 + "진행 중인 작업이 끝난 뒤 다시 시도하세요").

### 2.3 `ProjectContext` (Pydantic, `app/context/models.py`)

| 필드 | 형태 | 필수 | 선택지 / 비고 |
|---|---|---|---|
| `bk` | str | ✓ | 제품명. 한줄 정의와 독립(D-013) |
| `oneLiner` | str | ✓ | 한줄 정의 |
| `researchQuestion` | `{text, template?}` | ✓ | 템플릿 3종 중 선택 후 편집 가능(4.1) |
| `projectType` | `{choice, note}` | ✓ | `branding` 브랜딩 · `new` 신규기획 · `renewal` 리뉴얼 · `ux` UX개선 |
| `analysisGoal` | `{choice, note}` | ✓ | `needs` 니즈탐색 · `marketing` 마케팅전략 · `concept` 컨셉발굴 · `segment` 세그먼트개척 |
| `keyMetrics` | list[str] | ✓(1개 이상) | 방향 지시자. 측정값 아님 |
| `constraints` | list[str] | ✓(0개 허용) | 사내 제약. 차단이 아니라 방향성 경고의 기준(D-012) |
| `positioning` | `{price, market}` | ✓ | price: `premium` · `value` / market: `leader` · `challenger` · `new` |
| `channels` | list[str] | ✓(1개 이상) | `naver_cafe` · `naver_blog` · `youtube` · `ppomppu` · `clien` · `fixture`(개발용, 설정으로만 노출) |
| `knownInsights` | list[str] | – | 0단계 입력분. 저장은 `session.knownInsights[]`(D-016) |
| `productCategory` | `{l1, l2?, l3?, source}` | l1 ✓ | source: `shopping` · `llm_estimate` · `user` (D-015) |
| `targetScope` | `{ageRanges[], genders[], households[], lifeStages[], note}` | – | 미선택 = 전체. households: `single` · `newlywed` · `infant` · `school` · `senior_cohab` / lifeStages: `student` · `early_career` · `parenting` · `empty_nest` · `retired` |
| `futureCustomer` | `{choices[], note}` | – | `competitor_users` · `watchers` · `churned` · `adjacent_needs` |
| `schemaVersion` | int | ✓ | 1 |

- 표시 라벨(한글)은 프론트 상수와 `project_context.md` 생성기가 같은 표(`app/context/labels.py` ↔ `frontend/src/lib/contextLabels.ts`)를 쓴다. 두 파일의 일치는 테스트로 확인한다.
- 0-B 값은 `project_context.md`에서 "분석 대상 초기 기준선 — 우선 탐색하되 범위 밖 발견도 배제하지 말 것, 해석을 조정하지 말 것"이라는 문구 아래에 둔다(0단계 기획 주입 문구).
- `alignment_warnings[]` 형태만 정의한다: `{source: "constraints|analysisGoal|positioning", item: str, reason: str}`. 이번 범위에서는 생성하지 않는다(D-012).

### 2.4 키워드 (`app/keywords/models.py`)

```jsonc
{
  "id": "k_r1_0007",            // 라운드+순번. 수동 추가는 "m_<ts>", 추천 단어는 "s_<ts>"
  "kw": "실외기소음",
  "axis": "physical | psychological | behavioral",
  "sub": "sense",               // 5.1 표의 코드. 사용자가 만든 하위는 "custom:<이름>"
  "round": 1,                   // 1~4 · 수동은 추가된 라운드
  "origin": "llm | manual | suggested",
  "status": "pending | approved | rejected",
  "reject": { "tags": ["common"], "note": "너무 흔함" },   // rejected일 때만
  "volume": { "monthly": 1240, "source": "searchad | unconnected", "at": "…" },
  "badges": ["llm_only", "low_volume"]
}
```

- 프론트 `Keyword` 타입의 `cat` 필드는 `axis`와 `sub`로 바뀐다. `score`와 `total`은 없어진다(D-014, D-026).

### 2.5 크롤링 문서 (`app/crawl/schema.py`, D-034)

```jsonc
{
  "doc_id": "nc_3f9a1c…",       // 채널 접두사 + sha1(정규화 URL + 스레드 키)[:16] → 결정적 (AC-13)
  "source": "naver_cafe | naver_blog | youtube | ppomppu | clien | fixture",
  "src_meta": { "cafe": "○○맘카페" },            // 채널별: blog id · video title/description · board 등
  "kw": "소음", "kw_axis": "physical", "kw_sub": "sense", "kw_hits": ["소음","실외기소음"],
  "title": "…", "body": "…",
  "comments": [{ "text": "…", "depth": 0, "date": "2026-07-12", "author_hash": "a1b2…" }],
  "date": "2026-07-12", "url": "https://…",
  "fetch_level": "full | snippet",
  "access": "public | restricted",
  "snippet": "…",               // P1 스니펫. 항상 보존
  "author_hash": "…",           // 원글 작성자. 원문 식별자는 저장하지 않음 (AC-15)
  "crawled_at": "2026-09-28T…"
}
```

- 유튜브는 최상위 댓글 + 답글 스레드 1개가 문서 1건이다. `title`은 비우고, 영상 제목과 설명은 `src_meta`에 둔다(2단계 기획 "문서 단위 · 피드형"). `doc_id`는 영상 URL + 스레드 ID로 만든다.
- 작성자 해시: `sha256(salt + source + 원문 식별자)[:16]`. salt는 처음 실행할 때 `data/.author_salt`에 생성하고 git에 넣지 않는다.

---

## 3. LLM 공통 층 (`app/llm/`, D-017 · D-051)

### 3.1 인터페이스

```python
@dataclass
class LLMTask:
    task: str                 # "kw_round_1" | "kw_axis_classify" | "category_estimate" | …
    sid: str
    instructions: str         # 과업 프롬프트 (라운드 템플릿 렌더 결과)
    attachments: list[Attachment]   # 원문 그대로 싣는 참고 블록 (project_context.md, keyword_feedback.md)
    output_schema: type[BaseModel]  # 응답 검증용
    max_tokens: int = 8000

class LLMBackend(Protocol):
    def run(self, task: LLMTask) -> LLMResult: ...   # 검증까지 통과한 결과 또는 오류
```

- **메시지 조립(`app/llm/compose.py`) 한 곳에서만 한다.** 순서:
  1. 참고 맥락 블록: `=== 참고 맥락: project_context.md ===` + 파일 원문
  2. (있으면) `=== 참고: keyword_feedback.md ===` + 원문
  3. 과업 지시
- 참고 블록 머리말은 "아래는 규칙이 아니라 참고 맥락이다. 벗어나는 발견도 배제하지 말 것" 한 줄로 고정한다(D-012, D-017). 블록은 파일 경로가 아니라 **내용 자체**를 싣는다. cvc-agent에서 "파일을 읽어라"로 지시했을 때 조각만 읽는 문제가 실측된 방식은 쓰지 않는다.
- 응답은 `output_schema`로 검증한다. JSON 추출 실패나 스키마 위반이면 같은 백엔드로 **1회 재시도**하고, 그래도 실패하면 오류를 돌려준다. 어느 단계에서 실패했는지는 `LLMResult.error.kind`(`timeout | parse | schema | backend`)에 담는다.
- 백엔드 선택: `settings.llm_backend`(기본 **`openai_api`**, D-076)가 기본값이고, `settings.llm_backend_overrides`(예: `{"kw_round_*": "codex_exec"}`)로 과업별로 바꿀 수 있다.

### 3.2 `openai_api` (기본) · `claude_api` (선택)
- `openai_api`: OpenAI 공식 Python SDK로 호출한다. 참고 블록은 system(developer) 메시지, 과업 지시는 user 메시지에 넣는다. JSON 출력은 구조화 출력(JSON schema) 모드로 요청하고, 그래도 `compose.extract_json` + 스키마 검증을 거친다. 참고 블록을 메시지 앞쪽에 고정해 자동 프롬프트 캐시가 걸리게 한다.
- 모델 ID는 설정값(`openai_model`)이고 교체는 설정으로만 한다. 키는 `OPENAI_API_KEY`. 키가 없으면 LLM이 필요한 기능은 "미연결"로 표시한다(D-023). 테스트 · QA는 `fake` 백엔드를 쓴다.
- `claude_api`: 기존 `services/claude.py` 경로를 옮겨 선택 백엔드로 남긴다. 3단계 이후 기존 코드(페르소나 · 채팅)가 쓰던 호출은 그대로 둔다.

### 3.3 `codex_exec` (cvc-agent 패턴 이식)
```
data/llm_runs/{run_id}/
  manifest.json                  # task, sid, 백엔드 설정, 입력 해시
  prompts/task-{n}.txt           # 렌더된 전체 입력 (참고 블록 + 과업, 평탄화)
  answers/task-{n}.json          # 워커가 쓴 답 (원자적 쓰기: .part → rename)
  answers/bad/task-{n}.json|.reason.txt   # 파싱·스키마 실패 격리
  locks/task-{n}.pid             # 진행 중 표시 · pid 생존 확인
  logs/worker-{n}.log            # 시도별 구분선으로 이어쓰기
```
- 실행: `codex exec --profile {settings.codex_profile} --skip-git-repo-check -C {run_dir} "<워커 지시문 + 프롬프트 본문 통째로>"`. 워커 지시문은 "답만 `answers/task-{n}.json.part`에 쓰고 rename하라"로 고정한다.
- 작업 1건 = exec 1개. 같은 `run_id`로 다시 실행하면 답이 있거나 워커가 살아 있는 작업은 건너뛴다. 이게 곧 재시도이고, 중복 과금이 없다(AC-17).
- 타임아웃(기본 600초)이 지나면 프로세스를 죽이고 `backend` 오류로 돌려준다.
- 1단계에서는 라운드 작업 스레드(5.2)가 exec 하나를 띄우고 답을 기다린다. 4단계 대량 판정(나중)을 위해 `run_many(tasks, concurrency)`를 같이 둔다.
- 테스트는 `codex` 대신 가짜 실행 파일(`tests/fakes/fake_codex.py`)을 `settings.codex_bin`으로 지정해 돌린다.

---

## 4. 0단계 · 입력

### 4.1 화면 (`/pipeline/start`)
- 위: 기존 세션 목록(`SessionList`). 구버전 세션에는 "구버전" 배지를 단다.
- **버전 (D-075 · D-078):**
  - 사이드바의 현재 세션 영역에 버전 선택(예: "v3 · 활성 ▾")을 두고, 누르면 버전 목록 드로어가 열린다. 목록 행: 버전 · 어디서부터 다시 했는지 · 만든 시각 · 메모 · 수집본 ID.
  - 각 단계 화면 오른쪽 위에 "이 단계부터 다시" 버튼(secondary)을 둔다. 누르면 메모 입력 팝오버 → 새 버전 생성 → 그 단계 화면을 새 버전으로 연다.
  - 윗단계가 바뀐 버전에서 아랫단계 화면을 열면 상단에 "이 결과는 v2의 1단계 기준입니다. 이 단계를 다시 하거나 그대로 쓰세요." 배너(`stale`)를 보여 준다.
  - 과거 버전을 열면 모든 입력이 읽기 전용이고, 상단에 "v1 · 읽기 전용 · 이 버전에서 다시 시작" 배너가 뜬다.
  - 비교 화면 `/pipeline/compare?a=v1&b=v2`: 단계 탭(0 · 1 · 2 · 3 이후), 2.2.1의 단계별 비교를 나란히 보여 준다. 키워드는 추가(초록 배지) · 삭제(회색 취소선) · 이동(축 → 축) 목록이다.
  - 키워드가 바뀐 버전의 크롤링 화면에는 "기존 수집본 c1 사용 중 · 추가된 키워드 12개" 안내와 "추가된 키워드만 수집" 버튼을 둔다.
- **세션 목록의 작업 상태 (디자인 리뷰 4A):**
  - 세션 행마다 현재 작업 배지를 단다. 배지 문구 예시: "R2 생성 중" · "목록 수집 62%" · "검토 대기" · "상세 수집 41%" · "중단됨 · 이어서 진행" · "차단으로 멈춤" · "완료".
  - 정렬은 주의가 필요한 순서다. 중단 · 차단 행이 가장 위, 그다음 진행 중, 나머지는 최근 순이다.
  - 행을 누르면 해당 단계 화면으로 바로 간다. 중단 · 차단 행은 상세 수집 화면으로 간다.
  - 상태 출처는 `GET /sessions`가 세션마다 `activity: {kind, status, progress, updatedAt}`를 함께 돌려준다. 라운드 작업은 `keywordRounds.*.job`, 크롤링은 `queue.sqlite runs` + heartbeat에서 읽는다(6.4). 목록 화면은 10초마다 폴링한다.
  - 사이드바 하단의 현재 세션 영역에도 같은 배지를 한 줄로 보여 준다.
- 아래: "새 프로젝트" 폼. 두 카드로 나눈다.
  - **0-A 프로젝트 개요 (필수)**
    - 제품명 · 한줄 정의 · 리서치 질문(템플릿 버튼 3개 → 텍스트 채움) · 프로젝트 성격 · 분석 목적(단일 선택 칩 + 보충 서술 칸)
    - 핵심 지표 · 사내 제약(한 줄씩 추가하는 목록 입력) · 브랜드 포지셔닝(2×3 선택) · 수집 채널(복수 선택 칩)
    - 이미 아는 것(한 줄씩 추가, 선택)
  - **0-B 분석 대상 · 초기 기준선 (선택)**
    - 제품군 대›중›소: "자동 제안" 버튼 → 결과를 편집 가능한 3칸에 채우고 출처 배지(쇼핑 분류 / 추정)를 단다
    - 연령대 · 성별 · 가구 형태 · 생애주기 · 미래 고객 정의: 복수 선택 칩 + 보충 서술
  - 카드 제목 옆 도움말: "0-A는 지켜지는 값, 0-B는 대조되는 값" (0단계 기획 2절)
- 리서치 질문 템플릿(`problemDef` 승계):
  - "{제품}을 쓰는 사람들은 언제·어디서·무엇을 하다가 어떤 불편을 겪는가?"
  - "{제품}을 아직 안 쓰는 사람들은 무엇 때문에 망설이는가?"
  - "{제품}을 대신해 사람들이 쓰는 방법은 무엇이고, 왜 그 방법을 택하는가?"
- 검증: 필수 필드가 비면 해당 칸에 인라인 오류를 보여 주고, 저장 버튼은 비활성화한다. `alert()`는 쓰지 않는다.
- "시작"을 누르면: `POST /context` → `session.json`과 `project_context.md` 생성 → `/pipeline/keywords`로 이동. 새로고침하면 서버 저장값으로 복원한다(AC-01).

### 4.2 제품군 제안 (`app/context/category.py`, D-015)
1. 네이버 쇼핑 검색 API로 `bk`를 검색하고, 상위 40개 상품의 `category1~3` 경로 중 최빈값을 쓴다 → `source=shopping`.
2. 키가 없거나 결과가 0건이면 LLM 과업 `category_estimate`(입력: bk · oneLiner · 쇼핑 분류 대분류 목록 상수)를 부른다 → `source=llm_estimate`, 화면에는 "추정"으로 표시한다.
3. 사용자가 고치면 `source=user`로 바뀐다.

### 4.3 `project_context.md` 생성 (`app/context/render.py`)
- 입력: ProjectContext + knownInsights. 출력: 결정적 마크다운. 같은 입력이면 바이트까지 같다. 섹션: 0-A / 0-B / 이미 아는 것.
- `POST /context`나 `PUT /context/{sid}`가 저장할 때마다 다시 생성한다.

---

## 5. 1단계 · 키워드

### 5.1 3축 분류 (`app/keywords/taxonomy.py`, D-021)

| axis | sub 코드 · 라벨 |
|---|---|
| physical 물리 | `time` 시간 · `space` 공간 · `social` 사회적 환경 · `sense` 감각 · `body` 신체 상태 · `product_physical` 제품-물리 상호작용 |
| psychological 심리 | `emotion` 감정 · `goal_ladder` 표면 목표→기능적 결과→숨은 니즈 · `perceived_risk` 심리적 장벽(인지된 위험) · `belief` 인지·신념 · `identity` 자아·정체성 |
| behavioral 행동 | `trigger` 기존 행동·문제 발생·트리거 · `constraint` 제약 · `coping` 대처·우회 · `info_search` 정보탐색 · `switching` 전환·이탈 |

- 사용자가 새 하위 카테고리를 만들 때는 반드시 축을 하나 고른다. 코드는 `custom:<이름>`이다(DCX-2 `NewCategoryInput` 변경).
- 경험 단계(구매 전 · 중 · 후)는 축에 넣지 않는다(1단계 기획 4절).

### 5.2 라운드 흐름 (D-020)

```
[방향 지시 입력(선택)] → 생성 → 검토(승인/거절+사유, 이동, 추가) → 확정 → 다음 라운드
R1 ─→ R2 ─→ (커버리지 검사) ─→ R3 ─→ R4 ─→ 최종 검토 ─→ 크롤링 설정
```
- 네 라운드는 항상 돈다. 라운드를 건너뛰는 버튼은 없다. R4 뒤 최종 검토 화면에서 "추가 생성"을 누르면 R4 프롬프트로 한 번 더 돈다(`round=4`, `promptVersion` 동일, 결과는 `round: 4`로 기록).
  - 추가 생성은 회차 번호 `gen`(1, 2, …)을 가진다. 키워드 ID는 `k_r4g2_0007`처럼 회차를 포함하고, 작업 · 초안 · 확정 요청은 모두 `{round, gen}`을 싣는다. 확정 요청의 `gen`이 최신이 아니면 409("다른 창에서 새로 생성되었습니다. 새로고침하세요")를 돌려준다(Codex #5).
- 라운드 생성: `POST /keywords/{sid}/rounds/{n}` → 서버가 `projectContext`, 승인 키워드, 이벤트, 커버리지를 **직접 읽어** 프롬프트를 만든다. 클라이언트가 bk나 문제정의를 보내지 않는다.
- **생성은 백그라운드 작업이다(디자인 리뷰 2A).**
  - 요청은 즉시 `{jobId, status: "running"}`를 돌려준다. 화면은 `GET /keywords/{sid}/rounds/{n}`을 3초마다 폴링한다.
  - 상태(`running | done | failed`, 시작 시각, 오류)는 `keywordRounds.{n}.job`에 저장한다. 새로고침하거나 다른 화면에 다녀와도 같은 작업의 결과를 받는다.
  - 같은 라운드에 `running` 작업이 있으면 새 요청은 기존 `jobId`를 돌려준다. 중복 실행과 중복 과금이 없다.
  - 서버가 재시작돼 작업이 사라졌으면(`running`인데 실행 중이 아님) `failed(kind=interrupted)`로 바꾸고 재시도 버튼을 보여 준다.
  - 실행은 FastAPI 프로세스 안의 스레드로 한다. 크롤링처럼 며칠 걸리는 작업이 아니므로 별도 워커는 두지 않는다.
- 응답 키워드는 서버에서 정규화한다: 공백 제거 · 2자 미만 제외 · 이미 있는 키워드(대소문자 무시) 제외 · 금지어 제외 · 알 수 없는 sub면 해당 축의 첫 sub로 보정하고 로그를 남긴다. 그다음 검색량을 조회한다.

### 5.3 라운드별 프롬프트 (`app/keywords/prompts/r{n}.v1.md`)
공통 골격(1단계 기획 1절): 역할 문장 없음 → `## 임무` → `## 사고 절차`(번호 순서 필수) → `## 키워드 형태 규칙`(형태 예시만: 좋은 예 명사형 / 나쁜 예 "후기 · 비교"형) → `## 분류`(5.1 표) → `## 출력`(JSON 스키마).

| 라운드 | 사고 절차 · 기법 | 추가 입력 | 목표 수 |
|---|---|---|---|
| R1 | ① 문제정의 속 상황 → ② 5W1H 전개 → ③ JTBD 규정 → ④ 사물·현상 단어로 좁힘. Pain Point 단어 필수 | 발산 톤(프로젝트 성격에서 결정, 아래) · 타겟 시드 | ≥70 |
| R2 | SCAMPER 대체 · 결합 · 응용을 기존 승인 키워드에 적용 | 승인 키워드 목록 · 피드백 md | ≥100 |
| R3 | 수렴·균형: 부족한 축 위주로 생성 | `{category_distribution}` `{rejection_signals}` `{coverage_signals}` · 피드백 md | ≥60 |
| R4 | SCAMPER 역발상 · 제거 + 극단 사용자 + 부정 공간(대체 · 전환 · 이탈) | 승인 키워드 목록 · 피드백 md | ≥60 |

- **발산 톤(프로젝트 성격 → R1):** renewal = "기존 사용 중 불만 · 고장 · 관리 부담", new = "아직 충족되지 않은 니즈 · 대체 행동", branding = "인식 · 이미지 · 정체성 · 사회적 시선", ux = "사용 과정의 단계별 불편 · 실수".
- **필드 → 프롬프트 매핑:** `project_context.md` 전체가 모든 라운드에 참고 블록으로 붙는다(D-017). 과업 지시에서 **직접 인용**하는 필드는 다음과 같다.
  - `researchQuestion`: R1~R4 임무
  - `projectType`: R1 톤
  - `productCategory`: 발산 프레임 "이 제품군 안에서"
  - `targetScope`: R1 "참고 시드, 제약 아님"
  - `channels`: 형태 규칙에 "채널별 검색 문법"
    - youtube · 커뮤니티가 포함되면 "구어 · 줄임말 표현도 허용"
- **R3 빈 입력(D-027):**
  - `{rejection_signals}`
    - 거절이 0건이면 "거절 없음."을 적는다.
    - 대신 "사용자가 직접 추가 · 이동한 키워드(원하는 방향)" 목록을 싣는다.
  - `{coverage_signals}`
    - 검색광고가 미연결이면 "커버리지 정보 없음 — 축 분포 균형에 집중."을 적는다.
    - 같은 `bk`의 이전 세션 P5에서 0건이었던 키워드가 있으면 "과거 0건 키워드"로 싣는다(D-026-4).
  - 입력 상태는 `keywordRounds.3.inputs`에 기록한다(AC-08).
- 프롬프트 파일명에 버전을 넣고(`r1.v1.md`), 사용한 버전을 `keywordRounds.{n}.promptVersion`에 남긴다(B-003).

### 5.4 HITL (D-022)
- **이벤트** (`keyword_events.jsonl`, 한 줄 = 한 이벤트, 추가만 함):
  `{ts, round, type: "direction" | "approve" | "reject" | "move" | "add" | "unreject", kwId?, kw?, tags?, note?, text?, from?, to?}`
- **거절 사유 태그:** `irrelevant` 관련성 낮음 · `common` 흔함 · `sentence` 문장형 · `misclassified` 오분류 + 자유 텍스트.
  - `misclassified`를 고르면 이동할 sub를 바로 고르게 하고, `move` 이벤트를 함께 남긴다.
- **`keyword_feedback.md`** (`app/keywords/feedback.py`): 라운드 확정 시와 방향 지시 저장 시 다시 생성한다. 결정적 렌더링이다.
  1. 누적 방향 지시(최신순, 라운드 표시)
  2. 거절 사유별 건수와 예시 키워드(태그당 최대 8개)와 자유 텍스트
  3. 사용자가 직접 추가하거나 이동한 키워드(원하는 방향 신호)
  4. 오분류 이동 기록(원래 → 바뀐 sub)
- 방향 지시는 라운드 생성 전 입력칸에 넣는다. 입력칸은 비워도 된다.

### 5.5 검색량 · 커버리지 (D-025 · D-026 · D-027)
- **검색량** (`app/external/naver_searchad.py`):
  - 키워드 5개씩 묶어 월간 검색수(PC+모바일)를 받는다.
  - 미연결이면 `volume.source=unconnected`이고 배지는 "미연결"이다.
  - `low_volume` 배지는 월간 검색수 < `settings.low_volume_threshold`(기본 10)일 때 붙는다.
- **사람 트렌드 목록 (기준 목록 ①):**
  - R2가 끝나면 검색광고 연관키워드 API에 hint = `bk` + 승인 키워드 상위 4개(검색량 순)를 넣어 연관 쿼리와 월간 검색수를 받는다. 호출은 1~2회다.
  - 세션당 1번 받아 `coverage.humanQueries`에 저장한다.
- **지표** (`app/keywords/coverage.py`, 순수 함수):
  - 매칭 = 정규화(공백 · 대소문자) 후 **부분일치**(한쪽이 다른 쪽을 포함). 임베딩 유사도 매칭은 설정 스위치로 두되 기본 꺼짐이다. 임계값이 아직 정해지지 않았기 때문이다(1단계 기획 ★ 미결).
  - ① 검색량 가중 커버리지 = 매칭된 사람 쿼리 검색량 합 ÷ 전체 검색량 합
  - ② 구간별 커버리지 = 사람 쿼리를 검색량 10분위로 나눠 분위마다 ①을 계산
  - ⑥ 축 분포 차이 = 사람 쿼리를 `kw_axis_classify` LLM 과업으로 3축에 나눈 분포와 LLM 키워드 축 분포의 Jensen–Shannon 거리(밑 2, 0~1)
  - ⑦ LLM 단독 비율 = (월간 검색수 < 10 ∧ 사람 쿼리에 대응 없음) 키워드 수 ÷ 전체 LLM 키워드 수 → 해당 키워드에 `llm_only` 배지
  - 누락된 사람 쿼리(검색량 상위 20개 + 매칭 없음)가 R3 `{coverage_signals}`가 된다.
- 판정은 플래그만 한다. 자동으로 탈락시키지 않는다.
- 사람 트렌드 목록을 못 받으면 ① ② ⑥은 "계산 불가(미연결)"로 표시하고, ⑦은 검색량만으로 계산할 수 있으면 계산한다.

### 5.6 화면 (`/pipeline/keywords`)
- **상단:** 라운드 진행 표시(R1 · R2 · R3 · R4 · 최종, 기법 이름을 작게), 방향 지시 입력칸 + "생성" 버튼.
- **필터 바 (탭 아래, 디자인 리뷰 1A):**
  - 배지 필터 칩(단일 선택): 전체 · 판단 필요(LLM 단독 ∪ 검색량 적음 ∪ 오분류 의심) · LLM 단독 · 검색량 적음 · 미연결 · 거절됨 · 수동
  - 키워드 검색 입력: 부분일치, 입력 즉시 필터
  - 기본값은 "판단 필요"다. 판단 필요가 0개면 "전체"로 시작한다. 필터가 켜져 있으면 "필터 적용 중 · 해제" 표시와 해제 버튼을 보여 준다(수정본 Filter 규칙).
  - 칩마다 개수를 표시한다. 필터 결과가 0개면 "조건에 맞는 키워드가 없습니다. 필터를 해제하세요."를 보여 준다.
- **본문:** 3축 탭(물리 · 심리 · 행동 · 전체) → 하위 카테고리 그룹. DCX-3의 접기 · 모두 접기 · 10개 이상 자동 접기는 **하위 카테고리 단위**로 유지한다.
- **키워드 칩:**
  - 클릭하면 거절 토글, 거절 시 사유 팝오버(태그 칩 4개 + 메모 한 줄, Enter로 저장, Esc로 닫기)
  - 드래그로 sub 이동(DCX-2 유지, 축 사이 이동 허용)
  - 배지: LLM 단독 · 검색량 적음 · 미연결 · 수동
- **사이드 패널:**
  - 축 분포 막대
  - 커버리지 요약(R2 뒤부터): ① ② ⑥ ⑦ + 누락 쿼리 상위 목록
  - `keyword_feedback.md` 미리보기(접힘)
- **하단:** "이 라운드 확정" 버튼. 최종 화면에서는 "추가 생성(R4 한 번 더)"과 "크롤링 설정으로" 버튼.
- **상태:**
  - 생성 중에는 하위 카테고리 그룹 자리에 스켈레톤 3개와 "처리 중… R2 생성 중 · 보통 30~90초" + 경과 시간을 보여 준다.
  - 생성 중에는 방향 지시 입력과 확정 버튼을 비활성화한다. 다른 화면으로 이동하는 것은 막지 않는다.
  - 생성 실패와 빈 결과는 8.1 상태 표를 따른다.

---

## 6. 2단계 · 크롤링

### 6.1 흐름 (D-026 · D-033)

```
설정 저장 ─→ [P1 목록 워커] 키워드×채널 검색 → P2(스니펫 기준) → URL 큐 적재 (스냅샷)
         ─→ [검토 게이트] 키워드×채널 표: 0건 · 저수율 · 고유 기여 → 사람이 키워드 제외
         ─→ [P3 상세 워커] 남은 URL 본문·댓글 수집 → P2(본문 기준) → P4 정규화 → docs/*.jsonl
         ─→ P5 리포트 (report.json) ─→ 전처리
```
- 위 흐름 한 번이 **수집본 하나**(`collections/c{n}`)를 만든다. 수집본은 끝나면 바뀌지 않고, 버전은 `collectionId`로 가리킨다(D-078). 목록을 다시 모으거나 추가 키워드를 수집하면 새 수집본이 생긴다.
- **병렬 (D-077):** P1 · P3 모두 채널끼리 동시에 돈다. 한 채널 안에서는 키워드(P1)와 URL(P3)을 그 채널의 `concurrency` 한도까지 동시에 처리하고, 채널별 `min_interval_s`는 지킨다. 예: 카페 4 · 블로그 4 · 유튜브 2 · 뽐뿌 1 · 클리앙 1 동시.

### 6.2 채널 어댑터 (`app/crawl/adapters/`)

```python
class ChannelAdapter(Protocol):
    source: str
    def list_page(self, kw: str, cursor: str | None) -> ListPage:     # P1: items[], next_cursor, total_hint
    def fetch(self, item: ListItem) -> list[FetchedDoc]:               # P3: 본문·댓글. 유튜브는 스레드 여러 개
```

| 채널 | P1 (목록) | P3 (상세) | 상한 · 비고 |
|---|---|---|---|
| `naver_cafe` | 검색 API `cafearticle`, 100건 × 10페이지 | crawl4ai로 공개 게시글 렌더링, 본문 + 댓글 + 대댓글 | 키워드당 1,000건. 로그인·등급이 필요하면 `access=restricted` · `fetch_level=snippet` |
| `naver_blog` | 검색 API `blog`, 100건 × 10페이지 | httpx로 모바일 본문 페이지. 파싱 실패 시 crawl4ai | 댓글은 수집하지 않음(댓글 수만 `src_meta`). 체험단 어휘 필터 강화 |
| `youtube` | yt-dlp `ytsearch{N}:{kw}` flat 목록(기본 N=20) | yt-dlp 댓글 추출(영상당 최대 `max_comments`, 기본 500), 스레드 단위 문서 | 영상 자체는 수집하지 않음. Data API 어댑터는 선택(`youtube_api`) |
| `ppomppu` | 사이트 내부 검색 URL 목록 페이지(httpx + HTML 파서) | 게시글 페이지 본문 + 댓글 | 요청 간격 기본 1초 |
| `clien` | 사이트 내부 검색 URL 목록 페이지 | 게시글 페이지 본문 + 댓글 | 요청 간격 기본 1초 |
| `fixture` | LG 에어컨 CSV에서 키워드가 들어간 행을 행 번호 순으로 100건씩 | 행 본문 그대로, 댓글 없음 | URL `fixture://aircon/{row}`. 네트워크 없음 |

- 검색 API 호스트는 설정값(`naver_search_base_url`)이다. NAVER API HUB로 옮길 때 URL만 바꾸면 된다.
- 어댑터 파싱 테스트는 실제 응답을 저장한 파일(`backend/tests/fixtures/http/<channel>/*.html|json`)로 한다(AC-16). 녹화 파일은 개발자가 한 번 실제로 받아 저장하고, 개인 식별 정보는 가린다.
- **채널 점검 (D-077):** 사이트 구조 변경 · 차단은 계속 생긴다고 보고, `python -m app.crawl.healthcheck [--source S] [--keyword 에어컨]`으로 채널마다 키워드 1개 목록 1페이지 + 글 3건 본문을 받아 "목록 파싱 성공 n/n · 본문 파싱 성공 n/3 · 차단 여부"를 보고한다. 파서가 깨지면 어느 채널의 어느 단계인지 바로 보이게 하고, 어댑터는 채널별 파일로 분리해 한 곳만 고치면 되게 한다. 워커도 채널별 파싱 실패율이 30%를 넘으면 그 채널을 `paused_parse_error`로 멈추고 리포트에 남긴다.
- `fixture` 코퍼스 경로는 `settings.fixture_corpus_path`다. 테스트는 원본에서 뽑은 2,000행 샘플(`backend/tests/fixtures/aircon_sample.csv`, git 제외, 없으면 테스트가 합성 샘플을 만든다)을 쓴다.

### 6.3 큐 (`app/crawl/queue.py`, SQLite · WAL)

| 테이블 | 주요 컬럼 | 비고 |
|---|---|---|
| `runs` | run_id, sid, kind(`list`/`detail`), pid, status, started_at, heartbeat_at, config_json | 워커 상태 |
| `list_tasks` | kw, source, cursor, status(`pending`/`done`/`failed`), fetched, total_hint, attempts, last_error | 키워드×채널×페이지 진행. PK(kw, source, cursor) |
| `urls` | url_norm, source, kw, kw_axis, kw_sub, snippet, title, date, src_meta_json, status(`pending`/`leased`/`done`/`failed`/`excluded`/`filtered`), lease_until, attempts, last_error, doc_count, first_seen_kw_order | UNIQUE(url_norm, source) = 중복 제거 |
| `snapshots` | snapshot_id, created_at, url_count, hash | P1 완료 시점의 URL 집합 해시 |

- **URL 정규화:** 스킴·호스트 소문자, 추적 파라미터(`utm_*`, `fbclid`, 네이버 `art=` 등 채널별 목록) 제거, 카페는 `cafe.naver.com/{cafe}/{articleid}` 형태로 통일.
- **같은 URL이 여러 키워드에서 나오면:** `urls`에는 처음 발견한 키워드로 한 행만 두고, 키워드별 발견 기록은 `url_hits(url_norm, source, kw)`에 남긴다. 고유 기여 계산에 쓴다.
- **재현성(AC-13):** P3는 `snapshot_id`의 URL 집합만 처리한다. 순서는 `(kw 확정 순서, source, url_norm)` 정렬이다. P1을 다시 돌리면 새 스냅샷이 생기고, 어느 스냅샷으로 P3를 돌릴지 명시적으로 고른다.
- **이어 하기(AC-12):**
  - 워커가 시작할 때 `leased`인데 `lease_until`이 지난 행을 `pending`으로 되돌린다.
  - 한 URL은 "문서 쓰기 → 같은 트랜잭션 안에서 `done`"으로 처리한다.
  - 문서 쓰기와 커밋 사이에 죽으면 같은 문서가 두 번 쓰일 수 있다. 읽는 쪽(전처리)이 `doc_id`로 중복을 제거해 무해하게 만든다.
  - **유실 방지 (엔지니어링 리뷰 Codex #3):** 200건 배치마다 샤드 파일을 `flush` + `fsync`한 **뒤에** 그 배치의 `done`을 커밋한다. 재시작 시 마지막 샤드 끝이 잘려 있으면 잘린 줄을 잘라 내고(truncate) 새 줄은 그 뒤에 이어 쓴다.
  - **죽은 실행의 lease 회수 (Codex #7):** `urls.lease_run_id`를 둔다. 워커가 시작할 때와 60초마다, pid가 죽은 run의 lease와 만료된 lease를 `pending`으로 되돌린다.
  - **키워드 제외와 공유 URL (Codex #4):** URL은 그것을 찾은 키워드(`url_hits`)가 **모두** 제외됐을 때만 `excluded`가 된다. 하나라도 남아 있으면 수집하고, 문서의 `kw`는 남은 키워드 중 확정 순서가 가장 앞선 것으로 적는다. 키워드별 원문 수는 `kw_hits` 기준으로 중복 포함 집계한다(D9, 사용자 확인). 문서 스키마에 `kw_hits[]`를 추가한다.
- **배치 커밋:** 기본 200건마다. 인덱스: `urls(status, source)`, `list_tasks(status)`.

### 6.4 워커 프로세스 (`app/crawl/worker.py`)
- 실행: `python -m app.crawl.worker {list|detail} --sid {sid} [--snapshot {id}]`. 백엔드가 `subprocess.Popen(..., start_new_session=True)`으로 띄운다. 웹 서버가 재시작돼도 워커는 계속 돈다.
- 워커는 10초마다 `runs.heartbeat_at`을 갱신한다.
- **상태 판정:** pid가 살아 있고 heartbeat가 60초 이내면 `running`이다. pid가 죽었는데 미완료 행이 남아 있으면 `interrupted`이고, 화면에 "이어서 진행" 버튼이 나온다.
- 같은 세션 · 같은 종류의 워커가 살아 있으면 새로 띄우지 않는다(pid 확인). 확인과 등록은 `BEGIN IMMEDIATE` 트랜잭션 하나로 묶어, 버튼을 동시에 두 번 눌러도 워커는 하나만 뜬다(Codex #8). 라운드 작업 시작도 같은 원칙으로 세션 파일 잠금 안에서 "실행 중 확인 → 작업 등록"을 한 번에 한다.
- **동시성:** asyncio. 채널마다 `concurrency`(동시 요청 수)와 `min_interval_s`(요청 간격)를 지키는 제한기를 둔다. crawl4ai 브라우저 풀 크기는 `render_pool_size`(기본 4)다.
- **실패 처리:** URL당 최대 `max_attempts`(기본 3)번 시도하고, 지수 백오프를 쓴다. 3번 다 실패하면 스니펫으로 문서를 만들고(`fetch_level=snippet`) `failed`가 아니라 `done` + `last_error`로 남긴다. 문서가 사라지지 않게 하기 위해서다(2단계 기획).
- 채널이 연속으로 차단 응답(HTTP 403·429)을 `block_threshold`(기본 20)번 보내면 해당 채널만 멈추고(`paused_blocked`) 리포트에 남긴다. 다른 채널은 계속 돈다.

### 6.5 P2 규칙 필터 (`app/crawl/filters.py`)
| # | 규칙 | 적용 시점 |
|---|---|---|
| ① | 날짜 범위(기본 최근 365일) | P1(날짜가 있는 채널) · P4 |
| ② | 광고어(기본 목록 + 블로그 체험단 어휘: 체험단 · 협찬 · 원고료 · 소정의 · 제공받아 · 서포터즈) | P1 스니펫 · P4 본문 |
| ③ | 제외 소스(카페 이름 · 블로그 id · 게시판 등. 기존 `default_exclude` 목록 이관) | P1 |
| ④ | 포함 소스(비우면 전체) | P1 |
| ⑤ | 제품명 포함 — **기본 꺼짐**(D-014). 켜면 본문 기준 | P4 |
| ⑥ | 중복 제거: 정규화 URL + 채널 키 | 큐 UNIQUE |
- 필터에 걸린 URL은 `filtered` 상태와 규칙 번호로 남긴다. 무엇이 왜 빠졌는지 리포트에서 셀 수 있다.
- 크롤링 검색어는 `kw` 그대로다. `bk`를 붙이지 않는다(AC-10).

### 6.6 검토 게이트
- P1이 끝나면 `step=crawl-gate`. 화면에 키워드 × 채널 표를 보여 준다.
  - 표 칸: 목록 수 · 필터 후 수 · 고유 기여(다른 키워드가 이미 잡지 않은 URL 수 ÷ 목록 수)
  - 행 배지: 0건 · 저수율(필터 후 < `gate_low_count`, 기본 10) · 고유 기여 낮음(< `gate_low_unique`, 기본 0.2)
- **표 표시 방식 (디자인 리뷰 13A):**
  - 열은 7개다: 제외 · 키워드 · 축·하위 · 목록→필터 후 · 고유 기여 · 채널 · 상태.
  - "채널" 칸은 채널별 작은 막대(폭 = 그 키워드 안에서 채널 비중, 0건 채널은 빈 막대 + 점선)로 그린다. 숫자는 툴팁과 스크린 리더용 텍스트(예: "카페 1,000, 블로그 1,000, 유튜브 402, 뽐뿌 700")로 제공한다.
  - 행을 누르거나 Enter를 누르면 행 아래에 채널별 상세(목록 · 필터 후 · 고유 기여 · 대표 제목 3개)가 펼쳐진다. `aria-expanded`를 쓰고, 한 번에 여러 행을 펼 수 있다.
  - 표 머리글은 스크롤해도 고정된다(`position: sticky`). 행이 300개를 넘으면 가상 스크롤로 그린다. 페이지 나눔은 없다.
- 기본 정렬은 "배지가 있는 행 먼저". 행마다 "제외" 체크, 상단에 "배지 행 모두 제외" 버튼이 있다.
- 예상 P3 규모(URL 수)와 예상 소요 시간(채널별 설정 처리량 기준)을 보여 준다.
- 게이트의 "저장"(`PUT /crawl/{sid}/gate` = 제외 목록 확정)과 "상세 수집 시작"(`POST /crawl/{sid}/detail`)은 서로 다른 동작이다(D-070). 시작할 때 저장된 제외 목록으로 URL을 `excluded`로 바꾸고(AC-14) P3 워커를 띄운다.
- 게이트에서 제외한 키워드는 세션의 `keywords[].crawlExcluded=true`로 남는다. 다음 세션 R3 "과거 0건 키워드"의 근거가 된다.

### 6.7 P4 정규화 · P5 리포트
- P4는 어댑터 결과를 2.5 스키마로 바꾼다. 작성자 식별자는 해시로 바꾸고 원문은 버린다. HTML 태그와 연속 공백을 정리한다(기존 `utils/text.clean_text` 재사용). 5,000건 단위 jsonl 샤드로 추가 저장한다.
- `report.json`:
  - `matrix[kw][source]` = `{listed, filtered, excluded, full, snippet, restricted, unique}`
  - `channels[source]` = `{docs, share, status, errors_top[]}`
  - `totals`, `snapshot_id`, `started_at/finished_at`, `throughput_per_min`
- 리포트는 단계가 끝날 때 한 번만 만든다(P1 끝 = 게이트 표, P3 끝 = `report.json`). 진행 중 화면은 큐의 단순 카운터만 읽는다. 계산은 큐 집계로 하고 docs 폴더를 읽지 않는다(D-074).

### 6.8 크롤링 설정 (`crawlConfig`)
`{channels(0-A에서 가져오되 이 화면에서 끌 수 있음), dateFrom, dateTo, adWords[], excludeSources[], includeSources[], productNameFilter: false, perChannel: {concurrency, min_interval_s, max_per_keyword}, youtube: {videos_per_keyword, max_comments}, target_total}`
- 기존 화면의 `target`(목표 건수)은 `target_total`로 이어 받는다. 도달하면 P3를 정상 종료한다.
- **100만 건 전제의 기본값(D-031):**
  - 카페 렌더링: 풀 4 × 요청당 약 2초 → 분당 약 120건
  - 커뮤니티 · 블로그(httpx): 채널당 분당 약 60건
  - 따라서 100만 건은 며칠 단위로 걸린다. 화면에 예상 시간을 보여 주고, 풀 크기와 동시성은 설정으로 올린다. 이어 하기가 전제이므로 중간에 멈춰도 된다.

### 6.9 화면 (`/pipeline/crawling`)
- **설정 카드:**
  - 채널 체크(0-A 값)
  - 날짜 · 광고어 · 제외/포함 소스 · 제품명 필터 토글(기본 꺼짐, "켜면 제품명이 없는 글이 빠집니다" 안내)
  - 고급(채널별 동시성 · 간격 · 상한 · 유튜브 설정, 접힘)
  - 확정 키워드 수 · 축별 수
- **P1 진행:** 채널별 진행 막대(키워드×페이지 완료/전체), 누적 URL 수.
- **게이트:** 6.6 표.
- **P3 진행:** 완료/전체, full/snippet/restricted 비율, 분당 처리량, 예상 남은 시간, 채널별 상태(`running`/`paused_blocked`/`done`). 워커가 끊겼으면 "이어서 진행" 버튼.
- **완료:** P5 요약(채널 분포, 키워드 상위/하위) → "전처리 →" 버튼.
- 폴링은 3초 간격이다(기존 `usePolling` 재사용). 화면을 닫아도 수집은 계속된다.

---

## 7. API

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /context` | 새 세션 생성(ProjectContext 검증) → sid |
| `GET /context/{sid}` · `PUT /context/{sid}` | 조회 · 수정(0단계 화면에서만. 키워드 R1 시작 뒤에는 `oneLiner`·`researchQuestion` 수정 시 경고 반환) |
| `POST /context/category-suggest` | 제품군 제안 `{bk, oneLiner}` → `{l1,l2,l3,source}` |
| `POST /keywords/{sid}/rounds/{n}` | 라운드 생성 작업 시작 → `{jobId, status}` (진행 중이면 기존 작업 반환) |
| `GET /keywords/{sid}/rounds/{n}` | 라운드 작업 상태 · 완료 시 pending 키워드 목록 |
| `POST /keywords/{sid}/events` | HITL 이벤트 추가(방향 지시 · 거절 · 이동 · 추가 등). 저장 후 피드백 md 재생성 |
| `POST /keywords/{sid}/rounds/{n}/commit` | 라운드 확정(pending → approved/rejected 반영) |
| `POST /keywords/{sid}/manual` | 수동 추가(검색량 조회 포함) |
| `GET /keywords/{sid}` | 키워드 · 라운드 상태 · 커버리지 · 피드백 md |
| `POST /keywords/{sid}/coverage` | 사람 트렌드 목록 수집 + 지표 계산(R2 확정 시 자동 호출, 수동 재계산 가능) |
| `POST /suggest-words` | 기존 기능 유지. 입력을 `sid, axis, sub`로 바꾸고 맥락은 서버가 읽음 |
| `GET /sessions/{sid}/versions` · `POST /sessions/{sid}/versions` | 버전 목록 · 새 버전 만들기 `{from, restartFrom, note}` (2.2.1) |
| `PUT /sessions/{sid}/active-version` | 활성 버전 전환(작업 진행 중이면 409) |
| `GET /sessions/{sid}/compare?a=&b=&stage=` | 두 버전의 단계별 비교 |
| `PATCH /session/{sid}` | 화면 소유 키(`step`, `drafts.*`)만 부분 저장 · 임시 저장 (D-070) |
| `PUT /crawl/{sid}/config` · `POST /crawl/{sid}/list` | 설정 저장 · P1 시작(새 수집본 생성) |
| `POST /crawl/{sid}/list?mode=added-keywords` | 현재 수집본에 없는 키워드만 수집 → 새 수집본 `{parent}` (D-078) |
| `PUT /crawl/{sid}/gate` · `POST /crawl/{sid}/detail` | 게이트 제외 목록 저장 · 상세 수집 시작(분리) |
| `GET /crawl/{sid}/status` | 워커 상태 · 진행 · 게이트 표 · 리포트 요약 |
| `POST /crawl/{sid}/resume` | 끊긴 워커 재기동 |
| `POST /crawl/{sid}/stop` | 워커 정상 종료 요청(현재 배치까지 커밋) |
| `GET /integrations` | 외부 API 연결 상태(연결됨/미연결) — 화면 배지용(AC-18) |

- 기존 `/generate-keywords`, `/score-keywords`, `/crawl`, `/status/{sid}`는 제거한다. 프론트가 새 경로만 쓰기 때문이다. 구버전 세션은 0~2단계 편집을 막으므로 옛 경로가 필요 없다.
- 오류 응답은 `{status: "error", error: {kind, message}}`로 통일한다(새 라우터 한정).

---

## 8. 실패 상태

| 상황 | 동작 | 화면 |
|---|---|---|
| LLM 시간 초과 · 파싱 · 스키마 실패(재시도 후) | 라운드 상태 `failed`, pending 없음 | "생성에 실패했습니다(원인: …)" + 재시도 |
| codex 실행 파일 없음 · 프로파일 오류 | `backend` 오류 | 원인 문구 + "설정에서 claude_api로 바꿀 수 있습니다" |
| 외부 API 미연결 | 해당 값 `unconnected`, 진행 계속 | "미연결" 배지(AC-18) |
| 외부 API 호출 오류(연결됨인데 실패) | 검색량 `null` + 오류 기록, 진행 계속 | "조회 실패" 배지 |
| P1 채널 전체 0건 | 게이트에 표시 | 행 배지 "0건" |
| 채널 차단(연속 403·429) | 해당 채널 `paused_blocked` | 채널 상태 칩 + 리포트 |
| 워커 비정상 종료 | `interrupted` | "이어서 진행" 버튼 |
| 디스크 쓰기 실패 | 워커 종료 · 오류 기록 | 오류 문구 |
| 구버전 세션을 0~2단계 화면에서 열기 | 편집 차단 | "구버전 세션은 0~2단계를 편집할 수 없습니다" |
| 0단계 필수값 누락 | 저장 불가 | 인라인 오류 |

### 8.1 화면 상태 표 (디자인 리뷰 3A)
문구 규칙은 Person A 기준이다. "일어난 일 + 다음 행동 하나". 오류에는 영향 범위와 복구 방법을 넣는다. 느낌표와 사과 표현은 쓰지 않는다. 목업의 "상태 모음" 화면이 이 표의 시각 기준이다.

| 기능 | 로딩 | 빈 결과 | 오류 | 성공 | 부분 성공 |
|---|---|---|---|---|---|
| 세션 목록 | 행 스켈레톤 3개 | "아직 프로젝트가 없습니다. 아래에서 새 프로젝트를 설정하세요." | "세션 목록을 불러오지 못했습니다. 새로고침하세요." | 최근 20개, 진행 중 작업 배지(Pass 3 결정) | 일부 세션 파일 손상 → 해당 행만 "읽을 수 없음" 배지 |
| 제품군 제안 | 버튼 "처리 중…" + 3칸 비활성 | 쇼핑 결과 0건 → LLM 추정으로 넘어가고 "추정" 배지 | 추정도 실패 → "제품군을 제안하지 못했습니다. 직접 입력하세요." 3칸 활성 | 3칸 채움 + 출처 배지 | 대분류만 찾음 → 중·소 칸 비워 두고 포커스 |
| 0단계 저장 | 버튼 "처리 중…" | – | 필수값 누락 → 칸마다 인라인 오류, 첫 오류 칸으로 스크롤·포커스 / 서버 실패 → "저장에 실패했습니다. 입력값은 그대로 있습니다. 다시 시도하세요." | 키워드 화면으로 이동 | – |
| 라운드 생성 | 스켈레톤 그룹 3개 + "처리 중… R2 생성 중 · 보통 30~90초" + 경과 시간 | 정규화 후 0개 → "새 키워드가 나오지 않았습니다. 방향 지시를 바꾸거나 다시 생성하세요." + 다시 생성 | "R2 생성에 실패했습니다(원인: 응답 형식 오류). 승인한 키워드는 그대로 있습니다. 다시 생성하세요." interrupted면 원인 "서버 재시작" | 검토 화면 | 목표 수 미달(예: R1 42/70) → 상단 안내 "목표 70개 중 42개가 생성되었습니다. 그대로 검토하거나 다시 생성하세요." |
| 검색량 조회 | 칩 옆 수치 자리 "…" | – | 칩에 "조회 실패" 배지, 전체 상단 안내 없음 | 수치 표시 | 일부만 성공 → 실패한 칩만 배지 |
| 커버리지 | 카드 스켈레톤 | 사람 쿼리 0개 → "비교할 사람 검색어가 없습니다. 이 입력 없이 R3를 생성합니다." | 미연결 → "검색광고 API가 연결되지 않았습니다. 커버리지 없이 R3를 생성합니다." | 인사이트 카드 + 지표 | ⑥ 축 분류 실패 → ⑥만 "계산 불가" |
| P1 목록 수집 | 채널별 진행 막대 + 누적 URL 수 | – (게이트에서 처리) | 채널 전체 실패 → 채널 행 "실패 · 원인" + 해당 채널만 다시 시도 | 게이트로 전환 | 일부 채널 실패 → 나머지로 게이트 진행 가능, 실패 채널 배지 |
| 검토 게이트 | – | 모든 키워드 0건 → 인사이트 자리 "수집된 목록이 없습니다. 날짜 범위와 채널을 확인하고 목록을 다시 수집하세요." + "설정으로" | – | 표 + 예상치 | 대부분 배지 → 기본 정렬로 배지 행 먼저 |
| P3 상세 수집 | 진행 막대 + 통계 | – | 워커 중단 → 경고 배너 + "이어서 진행" / 디스크 쓰기 실패 → "저장 공간에 쓰지 못했습니다. 디스크 여유 공간을 확인하고 이어서 진행하세요." | P5 요약 + "전처리로" | 채널 차단 → 채널 행 "차단으로 멈춤" + 원인 + "간격을 늘리고 재개" / 모든 채널 차단 → 경고 배너 |
| 구버전 세션 | – | – | 0~2단계 화면 진입 시 본문 대신 "구버전 세션은 0~2단계를 편집할 수 없습니다. 3단계 이후 화면에서 결과를 확인하세요." + "전처리 화면으로" | – | – |

---

## 9. 뒤 단계 호환 (D-034, AC-19)
- `services/preprocessing.py`만 새 스키마를 안다.
  - 읽기: 활성 버전의 `collectionId`가 가리키는 수집본 `crawl/{sid}/collections/{c}/docs/` (parent가 있으면 parent 문서 + 추가분을 `doc_id`로 합침, D-078)
  - 중복 제거: `doc_id` 기준
  - 저품질 컷: 본문 길이 기준. 스니펫 문서만 스니펫 기준을 유지한다(3~5단계 문서).
- 뒤 단계가 읽을 수 있게 전처리 출력에 호환 필드를 **추가**한다.
  - `desc = body + "\n" + 댓글 텍스트들`(최대 길이 설정)
  - `cafe = src_meta.cafe` 또는 채널 표시 이름
  - `link = url`
  - 원래 필드는 그대로 둔다. 학습 · 군집 · 임베딩 · 페르소나 · 채팅 코드는 고치지 않는다.
- `bk`와 `problemDef`를 요청 본문으로 받던 뒤 단계 라우터는 요청값이 비어 있으면 세션의 `projectContext`에서 읽는 폴백을 넣는다. 프론트 호출부도 `projectContext`에서 값을 채운다.
- `labeling.py`의 샘플 표시(`title`, `desc`)는 호환 필드로 그대로 동작한다.

---

## 10. UI 공통 · 디자인 시스템 · 반응형 · 접근성
- **목업:** [`mockups/index.html`](mockups/index.html). 6개 화면(0단계 입력 · R2 검토 · R3 커버리지 · 수집 설정 · 검토 게이트 · 상세 수집)이 있고, 상단 바로 전환한다. 구현은 이 목업을 기준으로 한다.
- **디자인 시스템: Person A Design System** (handoff bundle, D-067)
  - 우선순위는 번들 `CLAUDE.md`를 따른다. ① `uploads/펄슨에이_디자인규칙_수정본.html` → ② seed.
  - 색 · 레이아웃은 수정본 기준이다.
    - 색: 표면 Empathy White `#F8FCFF`, 텍스트 · 구조 Shadow Charcoal `#676668`, 신호 · 선택 Person Blue `#38B6F9`(soft `#EAF8FF`, deep `#168FCC`), 선 `#E7EAEE`
    - 레이아웃: 사이드바 224px, 12컬럼 · gutter 24 · margin 32
    - 라운드: Input 6 / Button 10 / Card 14 / Overlay 18. 그림자는 팝오버 · 드로어 · 모달에만 쓴다.
  - 컴포넌트는 코어 기준이다(Button · Input · Card · Badge · Table · Icon). primary 버튼 · 링크 · 포커스는 액션 블루 `#0a73b5`(hover `#085d93`)이고, BI 키트도 같은 조합이다. 버튼은 우측 정렬하고 primary는 가장 오른쪽, 화면당 하나다.
  - 타입은 Pretendard, 수정본 시맨틱 스케일이다.
    - screen.title 30/40/800 (화면당 하나)
    - insight.display 40/52/800: 게이트 · 커버리지처럼 판단이 있는 화면에만 쓴다. 800은 화면당 하나이므로, 이런 화면의 페이지 제목은 section.title 24/34/700으로 낮춘다.
    - card.title 18/27/700, body 15/24, label 13/19/600, caption 12/18
  - 분류 라벨(축 · 하위 · 채널)은 Neutral 배지다. Person Blue는 선택 상태 · 현재 라운드 · 핵심 신호(부족한 축 막대 하나 · 진행 막대)에만 쓴다. 차트는 주요 series 하나만 브랜드 색이다.
  - 판단이 있는 카드는 수정본 순서를 따른다(R3 커버리지 · 검토 게이트): Eyebrow → Insight → 해석 → 근거 메타(표본 수 · 기간 · 채널 · 스냅샷) → **다음 행동**.
  - Eyebrow · 사이드바 그룹 라벨은 한국어로 쓰고 영어 대문자를 쓰지 않는다(예: "커버리지 신호", "목록 신호", "파이프라인"). 디자인 리뷰 6A.
  - 문구 규칙: 버튼은 동사로 끝난다. 이모지와 느낌표를 쓰지 않는다. 로딩은 "처리 중…", 빈 상태와 오류는 "일어난 일 + 다음 행동 하나"다. 날짜는 `2026. 9. 28.` 형식이다.
  - **보조 텍스트 색 (D-068, 디자인 리뷰 8B):** 키트 값 `#8A8A8C`를 그대로 쓴다. 흰 배경 대비는 3.45:1로 AA(4.5:1)에 못 미친다. 사용자가 디자인 시스템과 같은 값을 유지하기로 했다. 그래서 이 색은 캡션 · 힌트 · 메타 정보에만 쓰고, 본문 · 레이블 · 오류 문구에는 쓰지 않는다.
  - primary 버튼 · 링크 · 포커스는 액션 블루 `#0a73b5`다(D-067, 디자인 리뷰 7A).
  - 구현 방식: 디자인 토큰을 `frontend/src/styles/tokens.css`(CSS 변수)로 옮긴다. Tailwind 4 `@theme`에 연결하고, Pretendard는 `frontend/public/fonts/`에서 자체 호스팅한다. 코어 컴포넌트는 `frontend/src/components/ds/`에 React+TS로 다시 만든다. 번들 jsx는 prototype이라 복사하지 않는다. Lucide 아이콘은 `lucide-react` 패키지를 쓴다.
  - 범위: 이번에 바꾸는 0~2단계 화면과 공통 셸(사이드바 · StepBar)에 적용한다. 3단계 이후 기존 화면은 셸만 바뀌고 본문 스타일은 그대로 둔다(뒤 단계 개편 때 적용).
- **DS 미정의 컴포넌트 규격 (디자인 리뷰 9A):** 번들 readme가 "미구현"으로 남긴 컴포넌트를 목업 기준으로 이렇게 정의한다. 모두 `frontend/src/components/ds/`에 코어 컴포넌트와 함께 둔다.

  | 컴포넌트 | 규격 |
  |---|---|
  | Select | Input과 같다. 높이 36, 라운드 6, 테두리 `--line-strong`, 오른쪽 chevron 16px. 오류 · 비활성 상태도 Input과 같다 |
  | Checkbox | 16px, `accent-color: --action`, 레이블 클릭 영역 포함. 표 머리글의 전체 선택은 indeterminate 상태를 지원한다 |
  | Switch | 36×20, 켜짐 `--action` · 꺼짐 `--line-strong`, `role="switch"` + `aria-checked`, 레이블 연결 필수 |
  | ChoiceChips | 높이 32, 라운드 10, 기본 `--line` 테두리, 선택 시 `--blue` 테두리 + `--blue-soft` 배경 + `--blue-deep` 글자, `aria-pressed`(복수) / `role="radiogroup"`(단일) |
  | Segmented | 높이 32, 바깥 라운드 10, 칸 사이 1px `--line`, 선택 칸은 ChoiceChips 선택색 |
  | Tabs | 13/600 텍스트, 활성 탭은 `--ink-strong` 글자 + 2px `--action` 밑줄, 개수는 `--sub` 400. `role="tablist/tab"` + 화살표 키 이동 |
  | Popover | 너비 300, 라운드 18(Overlay), `--shadow-md`, 패딩 16. Esc로 닫고 닫으면 여는 요소로 포커스를 돌려준다 |
  | Stepper | 5칸 균등 그리드, 칸 라운드 10. 완료는 `--success` 라벨, 현재는 `--blue` 테두리 + `--blue-soft` 배경 + `aria-current="step"` |
  | Skeleton | `--sunken` 채움, 라운드는 대상 요소와 같다. 애니메이션 없음(수정본 "장식용 애니메이션 없음") |
  | Banner | 라운드 10, 상태 soft 배경 + 상태색 아이콘, 오른쪽 끝 버튼 그룹, `role="alert"`(오류) / `role="status"`(안내) |

- **외부 API 연결 상태 = 내부용 표시 (디자인 리뷰 12, 사용자 결정):**
  - 프로덕트 화면에는 없어야 한다. 지금은 내부용이므로 보여 준다.
  - 이런 내부용 요소는 모두 설정 `NEXT_PUBLIC_INTERNAL_TOOLS`(기본 `true`) 하나로 켜고 끈다. 끄면 DOM에 렌더링하지 않는다.
  - 내부용 요소에는 "내부용" Neutral 배지를 붙여 프로덕트 UI와 구분한다.
  - 위치: 사이드바 하단 "외부 API · 2/6 연결" 버튼 → 오른쪽 드로어(너비 360, Overlay 라운드 18). 드로어에는 API별로 다음을 보여 준다.
    - 상태: 연결됨 / 미연결 / 마지막 오류
    - 영향 받는 기능: 예) 검색광고 → 검색량 · 커버리지
    - 필요한 환경변수 이름
    - "다시 확인" 버튼
  - 키 값은 어떤 경우에도 화면과 응답에 싣지 않는다. `GET /integrations`는 연결 여부와 오류 요약만 돌려준다.
  - 같은 설정으로 가리는 다른 내부용 요소: 목업의 `project_context.md` 미리보기, `keyword_feedback.md` 미리보기, 스냅샷 ID · 세션 ID 표기.
- **키워드 칩 키보드 조작 (디자인 리뷰 11A):**
  - 하위 카테고리 그룹 하나 = `role="listbox"` 하나 + 로밍 tabindex. Tab은 그룹 사이를 이동하고, 그룹 안에서는 ←/→/↑/↓로 칩을 이동하며 Home/End로 처음 · 끝에 간다.
  - Enter 또는 Space: 거절 토글. 거절하면 사유 팝오버가 열리고, 닫히면 같은 칩으로 포커스가 돌아온다.
  - M: "다른 카테고리로 이동" 메뉴. 드래그의 대안이다.
  - 칩은 `role="option"` + `aria-selected`(거절 여부)이고, 이름에는 키워드 · 검색량 · 배지를 담는다(예: "바람소리, LLM 단독, 검색량 적음").
  - 필터 바 오른쪽에 "키보드" 도움말 버튼을 두고 단축키 목록을 팝오버로 보여 준다.
- **클릭 영역 (디자인 리뷰 10A):** 데스크톱 · 마우스 기준으로 버튼 36/28, 칩 32를 유지한다. 아이콘 전용 버튼(칩 메뉴 `···`, 삭제 `×`, 닫기)은 보이는 크기와 상관없이 클릭 영역을 최소 24×24로 잡는다(WCAG 2.2 AA 2.5.8). 수정본의 44px 터치 영역은 터치 기기를 대상으로 하지 않으므로 적용하지 않는다(디자인 시스템과의 차이, D-069).
- **브라우저 기본 요소 테마 (디자인 리뷰 5A):** 전역 CSS에 다음을 둔다.
  - `accent-color`(체크박스 · 라디오) · `caret-color` = `--action`
  - `::selection` = `--blue-tint` 배경 + `--ink-strong` 글자
  - 스크롤바 = `scrollbar-color: --line-strong transparent`, `scrollbar-width: thin`
  - `select`는 `appearance: none` + Input과 같은 테두리 · 라운드 6 + Lucide `chevron-down` 16px
  - 숫자가 나오는 표 · 통계 · 막대 값은 `font-variant-numeric: tabular-nums`
- **대상 화면:** 맥미니에 연결한 데스크톱 브라우저. 최소 폭은 1024px이다. 1100px 미만이면 사이드바가 아이콘 폭으로 줄고, 4·8컬럼 카드가 12컬럼으로 쌓인다. 모바일 최적화는 하지 않는다(내부 도구). 200% 확대 시에도 가로 스크롤 없이 읽혀야 한다(수정본 Inclusive Design).
- **새 공용 컴포넌트:** `ChoiceChips`(단일/복수, `aria-pressed`), `ChoiceWithNote`, `ListInput`(한 줄씩 추가), `Segmented`, `Switch`(`role="switch"`), `Stepper`, `KeywordChip`, `RejectPopover`, `BarList`, `EvidenceMeta`, `InsightCard`(Eyebrow → Insight → 해석 → 근거 → 다음 행동), `StatGrid`, `ProgressBar`.
- **접근성:**
  - 선택 칩은 `button` + `aria-pressed`로 만든다. 지금의 `span onClick`은 교체한다.
  - 거절 사유 팝오버는 키보드로 조작할 수 있다(Tab 이동, Enter 저장, Esc 닫기).
  - 드래그 이동에는 대안 동작을 둔다: 칩 메뉴의 "다른 카테고리로 이동".
  - 진행 상태 영역은 `aria-live="polite"`다.
  - 색만으로 상태를 구분하지 않는다. 배지에는 항상 글자를 넣는다.
- **StepBar:** 단계 7개는 그대로 두고 `STEP_MAP`에 새 step 이름(`r4`, `kw-final`, `crawl-list`, `crawl-gate`, `crawl-detail`, `crawl-done`)을 추가한다.

---

## 11. 테스트 전략
- **백엔드 pytest** (`backend/tests/`): 네트워크 · API 키 · codex 설치 없이 돈다.
  - 외부 HTTP: `httpx.MockTransport`와 녹화 파일로 대체
  - LLM: 가짜 백엔드(정해진 JSON 응답)로 대체
  - codex: 가짜 실행 파일로 대체
  - 저장소: `tmp_path`를 `local_data_dir`로 지정
- **통합 테스트:** fixture 채널로 `POST /context` → R1~R4(가짜 LLM) → 게이트 → P3 → 전처리까지 FastAPI TestClient로 돈다(AC-11, AC-19, AC-20의 백엔드 부분).
- **이어 하기 테스트:** P3 워커를 서브프로세스로 띄워 N건 처리 후 SIGKILL하고, 재기동한 뒤 완료 URL이 다시 처리되지 않았는지 확인한다(AC-12).
- **프론트:** 화면에서 분리한 계산 로직(필터 · 로밍 포커스 · 라운드 버튼 상태 · 게이트 막대 · 저장 변경 감지 · 버전 비교)은 Vitest 단위 테스트로 검증하고(D-071), 화면 흐름은 `npm run lint` · `npm run build`와 gstack `qa-only` 브라우저 시나리오로 확인한다(03-plan에서 시나리오 정의).
- **의존성 추가 (backend/requirements.txt):**
  - 실행: `httpx`, `selectolax`(HTML 파서), `crawl4ai`, `yt-dlp`
  - 개발: `pytest`, `pytest-asyncio`(`requirements-dev.txt`)
  - SQLite는 표준 라이브러리다.
- **백엔드 가상환경:** `backend/.venv` 기준. 하네스 검증 명령은 `python3 -m pytest backend/tests -q`이고, 계획 단계에서 venv 경로를 반영해 확정한다.

---

## 12. 새 설계 결정 요약 (decision-log D-06x로 기록)
- D-060 기존 세션은 변환하지 않고 구버전으로 읽기 전용(G1 확정 반영).
- D-061 키워드 생성 · 크롤링 API를 새 경로로 교체하고 옛 경로는 제거.
- D-062 크롤링 워커는 웹 서버와 분리된 프로세스, 상태는 SQLite + heartbeat.
- D-063 커버리지 매칭 기본값은 부분일치만. 임베딩 매칭은 스위치로만(임계값 미결).
- D-064 상세 수집 3회 실패 시 스니펫 문서로 남긴다(문서 소실 방지).
- D-065 뒤 단계 호환은 전처리 출력에 `desc`·`cafe`·`link`를 덧붙이는 방식 하나로 한정.
- D-066 유튜브 문서 단위 = 댓글 스레드, 영상 정보는 `src_meta`.
- D-067 UI는 Person A Design System 기준, primary = 액션 블루.
- D-068 보조 텍스트 색은 키트 값 #8A8A8C 유지(대비 미달은 알려진 위험).
- D-069 44px 터치 영역 미적용, 아이콘 버튼만 최소 24×24.

---

## 13. 디자인 리뷰 (plan-design-review, 2026-09-28)

대상은 이 문서의 4.1 · 5.6 · 6.9 · 10절과 [`mockups/index.html`](mockups/index.html)이다. 사용자가 7개 항목 전부를 골랐고, AI 변형 목업은 만들지 않았다(기존 목업이 Person A 규칙으로 작성됨). 외부 의견(Codex · 서브에이전트)은 돌리지 않았다.

### 결정 (13건, 모두 사용자 개별 승인)
| # | 이슈 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | 키워드 100~400개를 추릴 도구가 없음 | A 배지 필터 칩 + 검색, 기본 "판단 필요" | 5.6 · 목업 R2 |
| 2 | 라운드 생성 중 새로고침하면 결과 소실 | A 백그라운드 작업 + 폴링, 중복 실행 방지 | 5.2 · 5.6 · 7 |
| 3 | 로딩 · 빈 결과 · 오류 · 부분 성공 미정의 | A 상태 표 + "상태 모음" 목업 | 8.1 · 목업 상태 모음 |
| 4 | 장시간 수집 후 돌아왔을 때 상태를 모름 | A 세션 목록 · 사이드바 작업 배지, 중단 세션 맨 위 | 4.1 · 목업 0단계 |
| 5 | 체크박스 · 선택색 · 스크롤바 · select가 OS 기본값 | A 토큰으로 테마 지정 | 10 |
| 6 | Eyebrow 영어 대문자 vs 한국어 UI 규칙 | A 한국어 | 10 · 목업 |
| 7 | primary 색: Charcoal vs 액션 블루 | A 액션 블루 `#0a73b5` | 10 · D-067 |
| 8 | 보조 텍스트 `#8A8A8C` 대비 3.45:1 | **B 키트 값 유지** (Claude 추천과 다름) | 10 · D-068 |
| 9 | DS에 없는 컴포넌트 7종+ | A 목업 기준 직접 규격화 | 10 규격 표 |
| 10 | 44px 터치 영역 요구 | A 데스크톱 기준, 아이콘 버튼 최소 24px | 10 · D-069 |
| 11 | 키워드 칩 키보드 조작 불가 | A 그룹 단위 로밍 포커스 + Enter/Space · M | 10 |
| 12 | 외부 API 연결 상태를 볼 곳 없음 | 사용자 지정: 내부용으로 표시, `NEXT_PUBLIC_INTERNAL_TOOLS`로 모든 내부용 요소 끄기 | 10 · 목업 사이드바 |
| 13 | 게이트 표 186~400행 가독성 | A 채널 미니 막대 + 행 펼침 + 머리글 고정 · 가상 스크롤 | 6.6 · 목업 게이트 |

추가로 사용자가 요청한 **목업 좌우 정렬 불일치**를 고쳤다. 원인은 두 가지였다. ① 필드 안 그리드가 남는 높이를 줄마다 나눠 가졌다. ② 나란히 놓인 카드의 높이가 서로 달랐다. 지금은 2열 필드는 위쪽 기준으로 맞고, 판단 카드 행은 높이가 같으며, "다음 행동"은 카드 바닥에 붙는다. 치수로 확인했다.

### 여정 스토리보드
| 단계 | 사용자가 하는 일 | 느끼는 것 | 설계가 받쳐 주는 것 |
|---|---|---|---|
| 1 | 새 프로젝트 입력 | 빠짐없이 적었나 | 인라인 검증 · md 미리보기 |
| 2 | R1~R4 검토 | 어디부터 보나 | "판단 필요" 필터 · 키보드 검토 |
| 3 | R3 커버리지 확인 | LLM이 사람 말을 놓쳤나 | 인사이트 카드 + 누락 쿼리 표 |
| 4 | 목록 수집 | 언제 끝나나 | 채널별 진행 막대 |
| 5 | 게이트 정리 | 무엇을 빼야 하나 | 배지 우선 정렬 · 채널 막대 · 행 펼침 |
| 6 | 상세 수집 중 자리를 비움 | 돌아와서 어디서 확인하나 | 세션 목록 작업 배지 · 중단 시 이어서 진행 |

### 뻔한 AI 디자인 점검 (도구형 화면 기준)
- 즉시 탈락 패턴: 없음.
- 판정 기준: 브랜드 식별 YES · 시각 중심 하나 YES · 제목만 훑어도 이해 YES · 영역마다 역할 하나 YES · 카드가 필요한가 대부분 YES(상태 모음은 참고 시트) · 모션 없음(규칙상 장식 모션 금지) · 그림자 없이도 성립 YES.

### 범위 밖 (이번 리뷰에서 결정하지 않음)
- 3단계 이후 화면 본문 스타일: 해당 단계 개편 때.
- 다크 테마: 디자인 시스템에 정의가 없다.
- 모바일 · 태블릿 최적화: 맥미니 데스크톱 전용(10절).
- 브라우저 알림(macOS): 4번에서 B를 고르지 않았다.

### 이미 있는 것 (재사용)
- Person A 번들: 토큰 · 코어 컴포넌트 5종 · BI 키트 셸 패턴(사이드바 224 · Evidence 드로어).
- 현재 코드: `usePolling`(폴링), `SessionList`, `sessionPersist`(DCX-16 복원), DCX-2 드래그 · DCX-3 접기 로직.

### 구현 과제 (03-plan으로 넘김)
- [ ] **T-D1 (P1)** 디자인 토큰 · 폰트 · 전역 브라우저 요소 테마 → `frontend/src/styles/tokens.css`, `frontend/public/fonts/`. 확인: `npm run build`, 목업과 나란히 놓고 비교.
- [ ] **T-D2 (P1)** `components/ds/` 코어 5종 + 10절 규격 표의 컴포넌트. 확인: 키보드 · 포커스 브라우저 QA.
- [ ] **T-D3 (P1)** 0단계 폼 · 세션 목록 작업 배지(4A). 확인: 브라우저 QA 시나리오.
- [ ] **T-D4 (P1)** 키워드 화면: 필터 바(1A) · 로밍 포커스(11A) · 생성 대기 상태(2A). 확인: 브라우저 QA.
- [ ] **T-D5 (P1)** 크롤링 화면: 게이트 표(13A) · 진행 · 중단 배너. 확인: 브라우저 QA.
- [ ] **T-D6 (P1)** 8.1 상태 표의 문구 · 모양 전부. 확인: 상태별 브라우저 QA.
- [ ] **T-D7 (P2)** 내부용 요소 스위치 `NEXT_PUBLIC_INTERNAL_TOOLS` + 외부 API 드로어(12). 확인: 끄고 빌드했을 때 DOM에 없음.

### 완료 요약
```
+====================================================================+
|         DESIGN PLAN REVIEW — COMPLETION SUMMARY                    |
+====================================================================+
| System Audit         | DESIGN.md 없음 → Person A 번들 기준, UI 범위 0~2단계 |
| Step 0               | 7/10, 7개 항목 전부                           |
| Pass 1  (Info Arch)  | 7/10 → 9/10                                  |
| Pass 2  (States)     | 5/10 → 9/10                                  |
| Pass 3  (Journey)    | 6/10 → 9/10                                  |
| Pass 4  (AI Slop)    | 8/10 → 9/10                                  |
| Pass 5  (Design Sys) | 7/10 → 9/10 (보조색 대비 미달 = 알려진 위험)   |
| Pass 6  (Responsive) | 7/10 → 9/10                                  |
| Pass 7  (Decisions)  | 2 resolved, 0 deferred                       |
+--------------------------------------------------------------------+
| NOT in scope         | written (4 items)                            |
| What already exists  | written                                      |
| TODOS.md updates     | 0 items proposed (backlog.md가 대신함)        |
| Approved Mockups     | 0 generated (기존 HTML 목업 사용)             |
| Decisions made       | 13 added to plan                             |
| Decisions deferred   | 0                                            |
| Overall design score | 5/10 → 9/10                                  |
+====================================================================+
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | — | Independent 2nd opinion | 0 | skipped | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | 03-plan 단계에서 수행 |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 5/10 → 9/10, 13 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** design phase outside voices skipped (not run this review).
- **VERDICT:** DESIGN CLEARED — eng review required (하네스 계획 단계에서 `plan-eng-review` 수행).

NO UNRESOLVED DECISIONS
