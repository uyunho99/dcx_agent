# 키워드 R2 잠금 · R1→R3 · r3.v3 / r4.v3 — 구현 계획 + QA 계획

> 실행: 하네스 네이티브. 구현은 Task마다 `codex:codex-rescue`(`--wait --fresh`, 쓰기 작업)에 위임. Main Claude는 위임 · 확인 · 리뷰 · 커밋만 한다.

**목표:** R2를 서버 설정으로 잠가 R1 다음에 R3가 생성되게 하고, R3 · R4 지시문을 수렴(7할) + 균형(3할) / 마지막 발산 · 정리로 바꾼다. 화면 모양은 그대로다.
**설계:** `docs/development/kw-skip-r2/02-design.md`(승인) · 기획 `01-brainstorm.md`(승인)
**기술:** FastAPI · pydantic-settings · pytest / Next.js · React · vitest
**기준 커밋:** origin/main `a63ffa9`

## 전역 제약
- 잠금 설정: `Settings.keyword_locked_rounds: list[int] = [2]` (환경변수 `KEYWORD_LOCKED_ROUNDS`, JSON 목록). 빈 목록 = 예전 동작.
- 잠금 거절: `StoreError('R2는 사용하지 않습니다. R1 다음은 R3입니다', 409, 'round_locked')` — 문구의 R 번호는 요청 번호 · 이전 라운드 · 다음 라운드로 채운다(기본값에서 위 문구 그대로).
- 지시문 버전: `PROMPT_VERSION = {1: "r1.v3", 2: "r2.v2", 3: "r3.v3", 4: "r4.v3"}`. `MIN_COUNT` 변경 없음. 옛 지시문 파일은 지우지 않는다.
- 지시문에는 **특정 분야 예시를 넣지 않는다**(기존 테스트 `test_no_role_sentence_no_domain_examples` 정책). 설계의 귀촌 예시(시골집외풍 등)는 기호형 예시로 바꾼다: "예: 「맥락어A+외풍」과 「맥락어B+외풍」은 같은 단어로 본다"처럼 `맥락어A/B · 핵심어X`로 표기.
- 화면: 레이아웃 · 컴포넌트 · 단계 표시 변경 금지. 글자 변경은 커버리지 배지 "R2 확정 후 계산" → "R1 확정 후 계산"(= `R${prevRound(3)}`) 하나뿐.
- 저장 데이터 이전 · 삭제 금지. 사용자 서버(3000 · 3310 · 3400 · 3401 · 8310 · 8400 · 8401)는 건드리지 않는다.
- Codex는 담당 파일만 수정. 다른 작업자 변경 보존. 커밋은 Main Claude가 한다(Codex 샌드박스는 worktree git 메타데이터에 못 씀).

## 리뷰 집중 지점
1. 세라젬 형태 세션(R1 확정 + R2 `done` 미확정 134개, `step: r2`) — 화면이 R1로 열리고 다음 라운드 생성이 R3를 만들며, R2 단어가 R3 중복 판정에서 빠져야 한다 → T1 `test_pending_locked_round_ignored`, T3 QA2.
2. R1을 다시 생성해 재확정(`replacing`)하거나 1단계부터 새 버전을 만들면 R2 · R3에 `needsRegeneration`이 붙는다 — R3 재생성이 R2 때문에 막히면 안 되고, 확정된 R2에 다시 생성 버튼이 뜨면 안 된다 → T1 `test_r1_recommit_then_r3_regenerates` · `test_committed_locked_round_not_regenerable_after_restart`.
3. R2를 이미 확정한 예전 세션 — 응답 · 승인 목록 유지, R3/R4 진행 → T1 `test_committed_locked_round_kept`.
4. 버전 조회(`GET /keywords/{sid}?version=`)도 미확정 R2를 빼야 한다 → T1 `test_pending_locked_round_hidden_in_version_view`.
5. R1 확정 직후 커버리지 loading 중 "다음 라운드 생성" — 버튼 비활성, 서버 409 → T1 `test_r1_commit_triggers_coverage`, T3 `roundUi` 테스트 + QA1.

---

### T1: 서버 잠금 (Codex)
**파일(소유):**
- 수정: `backend/app/config.py`(Settings에 필드 1개), `backend/app/keywords/rounds.py`, `backend/app/routers/keywords_v2.py`(GET `/keywords/{sid}` 응답 필터)
- 테스트: 신규 `backend/tests/keywords/test_round_lock.py`, 수정 `backend/tests/keywords/test_rounds_api.py`

**인터페이스(생성):**
- `rounds.locked(n: int) -> bool` — `n in settings.keyword_locked_rounds`
- `rounds.previous_round(n: int) -> int | None` — n보다 작은 잠기지 않은 가장 큰 번호(1 미만이면 None). 기본값: `previous_round(3) == 1`, `previous_round(4) == 3`
- `rounds.visible_rounds(rounds_map: dict) -> dict` — 잠겼고 `committed`가 아닌 항목을 뺀 사본. 잠겼고 확정된 항목은 남기되 `needsRegeneration`을 `False`로 낮춘다(화면에 R2 다시 생성 버튼이 뜨지 않게). 라우터 GET이 사용

**동작:** 설계 2절 표 그대로 — `start_round`/`commit_round`는 `_number` 직후 잠금 검사, `_order`는 잠긴 번호 건너뜀, `_all_keywords`는 잠긴 미확정 라운드의 keywords 제외, `commit_round` 끝 `if n == 2` → `if n == previous_round(3)`.

- [ ] **RED 1 — 신규 테스트 작성** (`test_round_lock.py`, 기존 `test_rounds_api.py`의 `client`/`start`/`commit` 헬퍼 재사용 · 필요하면 conftest 없이 import)
  - `test_locked_round_rejected`: R1 확정 후 `POST /rounds/2` · `POST /rounds/2?regenerate=true` · `POST /rounds/2/commit`이 모두 409, `error.kind == 'round_locked'`(응답 형식은 기존 StoreError 직렬화 따름), 세션 `keywordRounds`에 `'2'` 없음.
  - `test_r3_after_r1`: R1 확정만으로 `start(client, 3)` 성공(status done), R1 미확정이면 `POST /rounds/3` 409.
  - `test_r1_commit_triggers_coverage`: R1 확정 직후 `store.load_session('test')['coverage']['source'] == 'autocomplete'`.
  - `test_pending_locked_round_ignored`: 세션에 R1 확정 + `keywordRounds['2'] = {job done, committed False, keywords=[kw "가짜중복"]}`을 직접 저장하고 가짜 LLM R3 응답에 "가짜중복"이 포함되도록 backend 픽스처 응답을 맞춘 뒤 R3 생성 → R3 keywords에 "가짜중복" 존재. `GET /keywords/test`의 `keywordRounds`에 `'2'` 없음, 세션 파일에는 `'2'` 그대로.
  - `test_pending_locked_round_hidden_in_version_view`: 위 상태에서 `GET /keywords/test?version=<현재 버전>`도 `'2'` 없음.
  - `test_committed_locked_round_kept`: `keywordRounds['2'].committed = True` + 승인 키워드 저장 → GET에 `'2'` 있음, R3 생성 시 그 단어는 중복으로 걸러짐, R3 · R4 진행 가능.
  - `test_committed_locked_round_not_regenerable_after_restart`: 확정된 R2에 `needsRegeneration: True`(1단계 재시작 버전 상태)를 저장 → GET 응답의 R2는 `needsRegeneration` False, `POST /rounds/2?regenerate=true` 409 `round_locked`, R3 생성은 R1만 보고 진행.
  - `test_r1_recommit_then_r3_regenerates`: R1 → R3 확정 후 R1 `needsRegeneration` 재생성 · 재확정(`replacing`) → R3 `POST /rounds/3` 200.
  - `test_unlocked_setting_restores_r2`: `monkeypatch.setattr(settings, 'keyword_locked_rounds', [])` → R1 확정 후 R3 409, R2 생성 · 확정 가능, R2 확정 시 커버리지 시작.
  - `test_locked_helpers`: 기본값에서 `locked(2) is True`, `previous_round(3) == 1`, `previous_round(4) == 3`, `previous_round(1) is None`; `[]`에서 `previous_round(3) == 2`.
- [ ] **RED 확인:** `cd backend && .venv/bin/python -m pytest tests/keywords/test_round_lock.py -q` → 실패(locked 등 없음 / 409 아님). 로그를 `docs/development/kw-skip-r2/logs/T1-red.txt`에 저장.
- [ ] **GREEN:** 위 인터페이스 구현.
- [ ] **기존 테스트 정리:** `test_rounds_api.py`에서 R2를 거치는 테스트(`through(client, n)`, `test_rounds_must_follow_order`, `test_r2_commit_triggers_coverage`, R2를 포함하는 parametrize 등)를 고친다. 규칙: ① 일반 흐름 검증은 새 흐름(`through`가 잠긴 라운드를 건너뜀)으로, ② R2 고유 동작 검증은 `keyword_locked_rounds=[]` 픽스처에서 그대로 유지. 테스트 삭제 금지(이름 변경은 허용, 보고서에 대응표).
- [ ] **GREEN 확인:** `cd backend && .venv/bin/python -m pytest tests -q` 전부 통과. 로그 `logs/T1-green.txt`.
- [ ] **보고:** `docs/development/kw-skip-r2/reports/T1.md`(바꾼 파일 · 테스트 대응표 · RED/GREEN 요약).

### T2: 지시문 r3.v3 · r4.v3 (Codex)
**파일(소유):** 신규 `backend/app/keywords/prompts/r3.v3.md`, `r4.v3.md` · 수정 `backend/app/keywords/prompts.py`(`PROMPT_VERSION`만) · 테스트 `backend/tests/keywords/test_prompts.py`
**인터페이스:** 새 자리표시자 없음(기존 `values` 키만). r4.v3는 `{category_distribution}` · `{rejection_signals}`를 추가로 쓴다.

- [ ] **RED — 테스트 작성/수정** (`test_prompts.py`)
  - `test_four_distinct_templates`: 기대 `PROMPT_VERSION`을 전역 제약 값으로.
  - `test_r3_v3_converges_with_light_balance`: R3 지시문에 "주제 묶음", "약 7할", "약 3할", "가장 적은 축", "맥락어만 바꾼 변형" 포함, r3.v2의 임무 문구 "부족한 축을 보완하며 수렴·균형을 맞춘다" 미포함.
  - `test_r4_v3_final_divergence`: R4 지시문에 "대체 · 결합 · 응용", "역발상", "제거", "극단 사용자", "인접어", "맥락어만 바꾼 변형", "세 축에 고르게" 포함. `rejection_signals`/`distribution`을 채운 state에서 그 값이 R4 지시문에 나타남.
  - `test_v3_keeps_shared_sections`: r3.v3 · r4.v3의 `## 키워드 형태 규칙` 이후 전체(형태 규칙 · 분류 · 출력)가 r3.v2 · r4.v2의 같은 구간과 글자 그대로 같다.
  - 기존 `test_short_form_templates_only_add_form_rule`(v1→v2 비교)은 그대로 둔다. `test_no_role_sentence_no_domain_examples`, `test_form_rule_in_every_round` 통과 유지.
- [ ] **RED 확인:** `cd backend && .venv/bin/python -m pytest tests/keywords/test_prompts.py -q` → 새 테스트 실패. 로그 `logs/T2-red.txt`.
- [ ] **GREEN:** 설계 3절 문장으로 두 파일 작성(분야 예시 금지 · 기호형 예시만). `PROMPT_VERSION` 변경.
- [ ] **GREEN 확인:** `cd backend && .venv/bin/python -m pytest tests -q`. 로그 `logs/T2-green.txt`. 보고 `reports/T2.md`.

### T3: 화면 로직 (Codex)
**파일(소유):** `frontend/src/lib/logic/roundUi.ts`, `frontend/src/lib/logic/roundUi.test.ts`, `frontend/src/app/pipeline/keywords/page.tsx`
**인터페이스(생성, `roundUi.ts`):**
- `export const LOCKED_ROUNDS: readonly number[] = [2]`
- `export function nextRound(round: number): number` — 다음 잠기지 않은 번호, 4 이상이면 4 (1→3, 3→4, 4→4)
- `export function prevRound(round: number): number` — 앞의 잠기지 않은 번호, 없으면 round 자신 (3→1, 4→3, 1→1)
- `directionRound(round)` = `nextRound(round)`

- [ ] **RED — `roundUi.test.ts`에 추가:** `it('skips locked R2 when advancing')` — `nextRound(1)===3`, `nextRound(3)===4`, `nextRound(4)===4`, `prevRound(3)===1`, `prevRound(4)===3`, `directionRound(1)===3`, `directionRound(4)===4`, `LOCKED_ROUNDS` 동일 `[2]`.
- [ ] **RED 확인:** `npm --prefix frontend test -- src/lib/logic/roundUi.test.ts` → 실패. 로그 `logs/T3-red.txt`.
- [ ] **GREEN:** 함수 구현 + `page.tsx` 설계 4절 표의 6곳 교체(`next()`의 `round + 1`, `nextRound` 데이터 키, 다음 버튼 커버리지 조건, 커버리지 안내 조건, 커버리지 카드 · h1 조건 `keywordRounds[String(prevRound(3))]`, 배지 문구 `R${prevRound(3)} 확정 후 계산`). 그 밖의 JSX · 클래스 · 문구는 손대지 않는다. `generate()`의 `n === 3 && coverageLoading` 검사는 유지.
- [ ] **GREEN 확인:** `npm --prefix frontend test` · `npm --prefix frontend run lint` · `npm --prefix frontend run build` 통과. 로그 `logs/T3-green.txt`. 보고 `reports/T3.md`.

**의존:** T1 · T2 · T3 파일이 겹치지 않음 → 병렬 위임 가능. 커밋은 Task별로 Main Claude가 순서대로.

## 독립 리뷰
- Task별: Main Claude가 diff를 설계 표와 대조(읽기 전용, gstack `review`). 수정은 Codex 재위임.
- 브랜치 전체: 별도 `codex:codex-rescue` 읽기 전용 리뷰 1회(범위: `git diff a63ffa9...HEAD`, 위 리뷰 집중 지점 5개).

## QA 계획 (gstack `qa-only`)
- worktree: `~/Desktop/dcx_agent-kw-skip-r2` (브랜치 `fix/kw-skip-r2`). 의존성: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`, `npm --prefix frontend ci`.
- 데이터: `/private/tmp/dcx-kw-skip-r2-qa`(빈 폴더 + 세라젬 세션 폴더 통째 복사본 `sessions/s89d92341bdb340b0bd7a5943a1c86dc7/`(session.json · meta.json · versions · active) — 원본 `~/srv/dcx-agent/shared/data/sessions/…`는 `cp -R`로 읽기만). 복사 후 `active` 링크가 원본을 가리키면 복사본 안 경로로 다시 건다.
- 시작(가짜 LLM): 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=/private/tmp/dcx-kw-skip-r2-qa LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3313 .venv/bin/uvicorn app.main:app --port 8313` · 화면 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8313 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3313`
- 테스트 URL: `http://localhost:3313/pipeline/keywords` (세션 선택 후), 뷰포트 1360×900

| ID | 시나리오 | 기대 결과 | AC |
|---|---|---|---|
| QA1 | 새 세션: 0단계 저장 → 키워드 R1 생성 · 전체 승인 · 저장 → "다음 라운드 생성" | R3 생성 시작(제목 "R3 수렴 · 균형 결과 …"), 단계 표시 R1 완료 · R2 다가올 단계 · R3 현재, 세션 `step == r3`. R1 저장 직후 커버리지 카드가 나타나고 loading 동안 다음 버튼 비활성 | AC1 · AC3 · AC7 |
| QA2 | 세라젬 복사본 열기 | R1 화면으로 열림, "검토할 라운드" 목록에 R1만, 다음 라운드 생성 → R3 | AC4 |
| QA3 | R2 직접 요청: `curl -X POST localhost:8313/keywords/<sid>/rounds/2` | 409 `round_locked`, 안내 문구 | AC2 |
| QA4 | 화면 동일성: QA1 화면을 origin/main 화면(같은 데이터, 같은 단계)과 스크린샷 비교 | 레이아웃 · 버튼 · 단계 표시 동일, 커버리지 배지 숫자(R1)만 다름 | AC7 |
| QA5 | R3 저장 → 다음 → R4 → 저장 → "크롤링 설정하기" | R4 생성 · 크롤링 화면 이동 | AC1 |
| QA-L1 | (실제 LLM, 보고용) 세라젬 복사본에서 백엔드를 `.env` 키로 8313 재시작 후 R3 1회 생성 | R3 결과 상위 30개를 R2(134개)와 나란히 기록, "앞말만 바꾼 인접어" 사례 수를 셈. 판정 아님 · 사용자 판단 자료 | AC9 |

- `.env`는 worktree에 없으므로 QA-L1은 `~/Desktop/dcx_agent/.env`를 `env $(grep -v '^#' … | xargs)` 형태로 읽어 넘기거나 `--env-file`을 쓴다. 키 값은 보고서 · 대화에 남기지 않는다. 실행 실패 시 "미실행(사유)"로 기록.
- 보고: `docs/development/kw-skip-r2/qa.json`(+ 스크린샷 `qa/`). 실패 시 `harness retry` → Codex 수정 → 재리뷰 · 재QA. 세 번 실패하면 중단 · 계획 수정 요청.

## 검증
`development-harness evidence`(설정된 4개 명령: pytest · lint · build · vitest) → `verification.json` 확인 → UAT.

## 되돌리기
- 운영 중 즉시: 백엔드 환경변수 `KEYWORD_LOCKED_ROUNDS=[]` + 화면 `LOCKED_ROUNDS = []` 후 재배포 → R2 복귀(지시문 r3.v3 · r4.v3는 유지).
- 전체: 브랜치 `fix/kw-skip-r2`를 머지하지 않거나 머지 커밋 revert. 데이터 변경이 없으므로 데이터 복구 불필요.

## 수용 기준 연결
| AC | Task · 시나리오 |
|---|---|
| AC1 | T1 `test_r3_after_r1` · QA1 · QA5 |
| AC2 | T1 `test_locked_round_rejected` · QA3 |
| AC3 | T3 · QA1 |
| AC4 | T1 `test_pending_locked_round_ignored` · `…_hidden_in_version_view` · QA2 |
| AC5 | T1 `test_committed_locked_round_kept` |
| AC6 | T2 테스트 4개 |
| AC7 | T3 범위 제한 · QA4 |
| AC8 | 검증 4개 명령 |
| AC9 | QA-L1 |

## 엔지니어링 리뷰 (plan-eng-review, 2026-10-02)

범위 판단: 서버 3파일 · 지시문 2파일 · 화면 2파일, 새 의존성 없음. 복잡도 낮음, 범위 축소 불필요.

**확인한 기존 구조**
- `rounds._order` · `_all_keywords` · `commit_round`(`if n == 2: compute_coverage`) · `start_round`(R3 커버리지 대기) — `backend/app/keywords/rounds.py:90-346`.
- 화면 `page.tsx:48-161`의 `round + 1` · `keywordRounds['2']` 7곳, `roundUi.ts` `directionRound`.
- 서버 응답을 쓰는 다른 곳: `lib/logic/reviewKeywords.ts`(최종 검토 후보) · `completedThrough.ts`(R4 확정만 봄) · `context/versions.py`(1단계 재시작 시 모든 라운드 `needsRegeneration`) · `context/store.py` 활동 목록(실행 중 작업만).

```
R1 확정 ──(커버리지 시작: previous_round(3)=1)──▶ R3 생성(_order: 1만 확인, 2 건너뜀)
   │                                              │  중복 판정: _all_keywords − 미확정 R2
   └─ 화면 next(): nextRound(1)=3                  ▼
                                                 R3 확정 ──▶ R4 ──▶ 크롤링
R2 요청(start/regenerate/commit) ──▶ 409 round_locked
GET /keywords/{sid} ──▶ visible_rounds(): 미확정 R2 제거 · 확정 R2 needsRegeneration=False
```

**발견 · 반영**
- [P1] (confidence: 9/10) `rounds.py:346` — 커버리지 시작이 `n == 2`에 묶여 잠금 시 영영 계산되지 않음. 설계 D-329로 이미 반영(`previous_round(3)`). 테스트 `test_r1_commit_triggers_coverage`.
- [P2] (confidence: 8/10) `context/versions.py:187` — 1단계부터 새 버전을 만들면 확정된 R2에도 `needsRegeneration`이 붙어 화면 `roundUi.regenerable`이 R2 "다시 생성" 버튼을 띄우고, 누르면 409. → `visible_rounds`가 확정 R2의 `needsRegeneration`을 낮추도록 T1에 추가, 테스트 `test_committed_locked_round_not_regenerable_after_restart`.
- [P2] (confidence: 8/10) `tests/keywords/test_prompts.py:45` — 지시문에 분야 예시 금지 정책. 설계의 귀촌 예시를 기호형 예시로 바꾸도록 전역 제약에 명시.
- [P3] (confidence: 7/10) QA 세션 복사 — `session.json`만 복사하면 `versions` · `active` 링크가 없어 버전 조회가 깨질 수 있음 → 세션 폴더 통째 복사로 QA 계획 수정.
- 화면 상수 `LOCKED_ROUNDS`와 서버 설정이 따로 있음(설계 5절 한계로 기록). 이번 범위에서 수용.

**테스트 공백 점검:** 잠금 거절 · 순서 · 미확정/확정 R2 · 버전 조회 · 재시작 · 커버리지 · 잠금 해제 · 지시문 문구 · 화면 다음 라운드 번호 모두 Task 테스트 또는 QA에 연결됨. 실제 모델 품질은 자동 판정 불가 → QA-L1 보고용.
**성능:** 변경 없음(응답 필터는 라운드 4개 이하 dict 순회).
**병렬화:** T1 · T2 · T3 파일 겹침 없음 → 병렬 위임, 커밋은 순서대로.
**제외 범위:** 화면 단계 표시 변경, 서버 측 맥락어 변형 자동 판정(필요 시 백로그), 배포.
**외부 의견(Outside Voice):** 계획 단계에서는 생략. 구현 후 브랜치 전체를 별도 Codex 읽기 전용 리뷰로 확인(위 "독립 리뷰").

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | codex (계획 단계 생략) | Independent 2nd opinion | 0 | skipped | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 4 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | 해당 없음(레이아웃 변경 없음) | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex, plan-review 단계, skipped(구현 후 브랜치 리뷰에서 수행 예정), findings 없음.
- **VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
