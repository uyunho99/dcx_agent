# 키워드 거절 팝오버 가림 · 키워드 표시 띄어쓰기 — 구현 · QA 계획

기획 [01](01-brainstorm.md) · 설계 [02](02-design.md) 승인(2026-10-02). 구현 담당: Codex(`codex:codex-rescue`, 쓰기 모드). Claude는 위임·리뷰·QA만.

## 0. 작업 환경
- worktree: `/Users/persona1/Desktop/dcx_agent-kw-popover`, 브랜치 `fix/kw-popover-spacing`, 기준 `origin/main`(a63ffa9).
- 준비: `backend/.venv` 생성 후 `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`, `npm --prefix frontend ci`.
- 기준 검사: `harness.config.json`의 4개 명령(pytest · lint · build · vitest)을 먼저 돌려 기존 실패를 기록한다.

## 1. Task

| ID | 내용 | 담당 파일 | 의존 | AC |
|---|---|---|---|---|
| T1 | 표시 띄어쓰기 함수 + API `display` 필드 | `backend/app/keywords/display.py`(신규), `backend/app/routers/keywords_v2.py`, `backend/tests/keywords/test_display.py`(신규), 필요 시 `backend/tests/keywords/test_rounds_api.py` | — | AC4, AC5 |
| T2 | 프런트 표시값 사용 | `frontend/src/lib/api/keywords.ts`, `frontend/src/components/keywords/KeywordChip.tsx`, 키워드를 화면에 쓰는 다른 keywords 컴포넌트, `frontend/src/components/keywords/keywordDisplay.ts`(+`.test.ts`, 신규) | T1(필드 이름) | AC4, AC5 |
| T3 | 사이드바 접기 + 자동 접기 | `frontend/src/app/pipeline/layout.tsx`, `frontend/src/app/globals.css`, `frontend/src/components/sidebarAuto.tsx`(신규 컨텍스트), `frontend/src/components/sidebarAuto.test.ts`(신규), `KeywordChip.tsx`(호출 한 줄) | T2와 `KeywordChip.tsx` 겹침 → T2 다음 순차 | AC2, AC3 |
| T4 | 팝오버 위치 보정 · 중복 테두리 정리 | `frontend/src/components/ds/Popover.tsx`, `frontend/src/components/ds/ds.css`, `frontend/src/components/ds/popoverAlign.ts`(+`.test.ts`, 신규), 필요 시 `RejectPopover.tsx` | T3 이후 | AC1 |

실행 순서: T1 → T2 → T3 → T4 (파일 겹침과 필드 이름 의존 때문에 순차).

### T1 세부
- `display_form(kw)`: 공백 있음/비한글/3자 이하 → 원문. Kiwi `space()` 후 한 글자 조각을 앞 조각(첫 조각이면 뒤 조각)에 붙임. 공백 제거 결과가 원문과 다르거나 예외 → 원문. Kiwi 전역 지연 생성, `lru_cache`.
- `with_display(obj)`: 키워드 dict(문자열 `kw` 보유) 목록에 `display`를 붙인 **복사본** 반환. 저장 경로에는 쓰지 않는다.
- 적용: `GET /keywords/{sid}`, `GET /{sid}/rounds/{n}`, `POST /{sid}/manual`, `POST /{sid}/events`의 응답 중 `keywords` 목록.
- RED 테스트(먼저 실패 확인):
  - `귀촌휴식죄책감`→`귀촌 휴식 죄책감`, `귀촌부부온도차`→`귀촌 부부 온도차`, `농가미완성감`→`농가 미완성감`, `층간소음스트레스`→`층간 소음 스트레스`, `전원혼자시간`→`전원 혼자 시간`
  - `귀촌 후회`(이미 공백)·`ABC`·`귀촌`→ 원문, Kiwi 예외 monkeypatch → 원문
  - 결과에 한 글자 조각 없음, `''.join(display.split()) == kw`
  - API: GET 응답 키워드에 `display` 있음, 저장 파일(`keywords` json)에는 `display` 없음
- 명령: `backend/.venv/bin/python -m pytest backend/tests/keywords -q`

### T2 세부
- `Keyword` 타입에 `display?: string`. `keywordLabel(k) = k.display?.trim() || k.kw`, `keywordTitle(k)` = 표시값과 원문이 다를 때만 원문.
- 칩 텍스트·`aria-label`·Popover `label`은 표시값. 요청 값(`kw`, `id`)은 그대로.
- RED: `keywordDisplay.test.ts` — display 있음/없음/공백 문자열, title 조건.
- 명령: `npm --prefix frontend test -- keywordDisplay`

### T3 세부
- `SidebarAutoProvider`/`useSidebarAuto()`: `request()`가 카운터 +1, 반환 함수 1회만 −1. 순수 로직은 `createSidebarAuto()`로 분리해 테스트.
- 레이아웃: `data-side="collapsed|expanded"`를 `.pipeline-shell`에, `id="pipeline-side"`를 aside에. 버튼 `aria-label`=`사이드바 접기`/`사이드바 펴기`, `aria-expanded`, `aria-controls`.
- 사용자 선택 `localStorage['dcx.sidebar.collapsed']` try/catch.
- CSS: 기존 1100px 미디어 규칙을 `.pipeline-shell[data-side="collapsed"] …`에도 적용(규칙 복제 또는 선택자 묶기).
- `KeywordChip`: `mode`가 null이 아니게 되면 `request()`, 닫히거나 언마운트되면 해제(`useEffect`).
- RED: 카운터 0→1→0, 중복 해제 무시, 사용자 접힘 상태 유지(합성 결과 = user || auto).
- 명령: `npm --prefix frontend test -- sidebarAuto`

### T4 세부
- `popoverAlign(panelRect, boundaryLeft, boundaryRight, margin=8) → 'end' | 'start'`: 기본 `end`(오른쪽 정렬), 왼쪽이 경계+여백을 넘으면 `start`. 순수 함수 테스트.
- `Popover`: 열린 뒤 `requestAnimationFrame` 한 번 뒤 측정(사이드바 접힘 반영), 가장 가까운 overflow 잘림 조상(없으면 뷰포트) 경계 사용, `data-align` 설정, `resize`에 재측정. `contained`는 제외.
- CSS: `.ds-pop[data-align="start"] { left:0; right:auto; }`.
- 중복 테두리: 브라우저에서 `.ds-pop` 개수와 중첩 여부 확인 후 원인을 보고서에 기록하고 하나로 정리.
- RED: `popoverAlign.test.ts` — 충분한 공간 → end, 왼쪽 부족 → start.
- 명령: `npm --prefix frontend test -- popoverAlign`

## 2. TDD 규칙 (Codex에 전달)
RED(새 테스트 실패 확인 · 출력 기록) → GREEN(최소 구현) → 리팩터링. 다른 Task 변경 보존, 담당 외 파일 수정 금지(필요하면 보고). Task별 보고서 `docs/development/kw-popover-spacing/reports/T<n>.md`에 RED/GREEN 명령·결과 요약, 변경 파일.

## 3. 리뷰
- Task별: 명세 일치(설계 2-1~2-3), 저장값 불변(AC5), 접근성 속성.
- 브랜치 전체: gstack `review` 읽기 전용. 수정은 Codex에 재위임.

## 4. 브라우저 QA (gstack `qa-only`)
- 시작: `.claude/launch.json`의 프런트/백엔드 설정(없으면 `backend/.venv/bin/uvicorn app.main:app --port 8000`(cwd backend), `npm --prefix frontend run dev`), URL `http://localhost:3000/pipeline/keywords` (키워드가 있는 기존 세션 선택).
- 시나리오
  - S1 (AC1·AC2): 1440px 폭, 사이드바 펼침 → 맨 오른쪽 칩 클릭 → 사이드바 자동 접힘, 팝오버 전체가 본문 안에 보임(`getBoundingClientRect` 왼쪽 ≥ 본문 왼쪽). 취소 → 사이드바 다시 펼침.
  - S2 (AC2): 접기 버튼으로 접은 뒤 칩 팝오버 열고 닫기 → 접힌 채 유지. 새로고침 후에도 접힘.
  - S3 (AC3): Tab으로 접기 버튼 이동, Enter로 전환, `aria-expanded` 값 확인.
  - S4 (AC4): 칩 텍스트가 띄어쓰기된 표시값, 한 글자 조각 없음, 마우스 올리면 원문.
  - S5 (AC5): 칩 거절 → 네트워크 요청 본문의 키워드가 원문 `kw`/`id`.
  - S6: 왼쪽 첫 칩 팝오버도 잘리지 않음, 팝오버 테두리 한 겹.
- 증거: 스크린샷 S1·S4, 보고서 `docs/development/kw-popover-spacing/reports/qa.md`.

## 5. 수용 기준 연결
AC1→T4,S1,S6 · AC2→T3,S1,S2 · AC3→T3,S3 · AC4→T1,T2,S4 · AC5→T1,T2,S5 · AC6→검증 명령 4개.

## 6. 되돌리기
브랜치 `fix/kw-popover-spacing` 미병합 시 worktree 제거로 끝. 병합 후에는 커밋 revert. 저장 데이터 형식 변경 없음(`display`는 응답 전용)이라 데이터 이전 불필요.
