# 키워드 화면 — 이전 라운드 승인 단어 누적 + 라운드 표시 · 구현 계획 + QA 계획

> 실행: 하네스 네이티브. 구현은 `codex:codex-rescue`(`--wait --fresh`, 쓰기)에 위임. Main Claude는 위임 · 확인 · 리뷰 · 커밋.

**목표:** 라운드 n 화면에 이전 라운드 승인 단어를 함께 보이고, 그 칩에 `R{round}` 표시를 붙인다.
**설계:** `02-design.md`(승인) · 기획 `01-brainstorm.md`(승인). 기준 `8c7a693`.

## 전역 제약
- 서버 · API · 저장 변경 금지. 칩 모양 · 색 · 클래스 추가 금지(기존 `Badge` 하나 추가만).
- `page.tsx`의 `all` 사용처(reveal · 중복 · approved · 승인 예정/거절)와 `shown` 사용처는 그대로.
- 사용자 서버(3000 · 3310 · 3400 · 3401 · 8310 · 8400 · 8401)는 건드리지 않는다.

## 리뷰 집중 지점
1. R3 화면에 R1 거절 단어가 섞이지 않는다 → T1 테스트 + QA1.
2. 이번 라운드 단어는 임시 거절(overrides)이어도 보인다 → T1 테스트(이번 라운드 rejected 포함).
3. 최종 화면에는 라운드 표시가 없다 → `currentRound={ui.final ? undefined : round}` + QA3.
4. `aria-label`에 라운드 표시가 들어간다(스크린리더) → QA1 DOM 확인.
5. 확정 요청은 이번 라운드 단어만 → 코드 리뷰.

### T1: roundKeywords 규칙 · roundTag · 칩 표시 (Codex)
**파일(소유):** `frontend/src/lib/logic/roundKeywords.ts`, `frontend/src/lib/logic/roundKeywords.test.ts`, `frontend/src/components/keywords/KeywordChip.tsx`, `frontend/src/components/keywords/KeywordGroup.tsx`, `frontend/src/app/pipeline/keywords/page.tsx`, `docs/development/kw-round-carry/logs/T1-*.txt`, `reports/T1.md`
**인터페이스:**
- `roundKeywords<T extends { round: number; status: string }>(all: T[], round: number, final: boolean): T[]`
- `roundTag(keywordRound: number, currentRound: number | undefined): string | undefined`
- `KeywordChip` 선택 prop `roundTag?: string` · `KeywordGroup` 선택 prop `currentRound?: number`

- [ ] RED — `roundKeywords.test.ts` 갱신/추가:
  - `it('keeps the selected round and earlier approved keywords')`: 입력 [r1 approved, r1 rejected, r3 pending, r3 rejected, r4 approved], round 3 → [r1 approved, r3 pending, r3 rejected](입력 순서 유지). round 1 → r1 두 개. 
  - `it('returns everything on the final view')` 유지.
  - `it('tags only earlier-round keywords')`: `roundTag(1,3)==='R1'`, `roundTag(3,3)===undefined`, `roundTag(1,undefined)===undefined`, `roundTag(4,3)==='R4'`.
  `npm --prefix frontend test -- src/lib/logic/roundKeywords.test.ts` → 실패. 로그 `logs/T1-red.txt`.
- [ ] GREEN — 설계 1절대로 구현. `KeywordChip`은 `roundTag`가 있으면 `labels` 맨 앞에 추가. `KeywordGroup`은 `currentRound`를 받아 칩에 `roundTag(k.round, currentRound)` 전달. `page.tsx`는 `<KeywordGroup … currentRound={ui.final ? undefined : round} />`만 추가.
- [ ] 확인 — `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`. 로그 `logs/T1-green.txt`. 보고 `reports/T1.md`.

## 독립 리뷰
Main Claude diff 검토(읽기 전용).

## QA 계획 (내장 브라우저)
- worktree(구현용, 생성 예정) `~/Desktop/dcx_agent-kw-round-carry`. 의존성: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`, `npm --prefix frontend ci`.
- 데이터: `/private/tmp/dcx-kw-round-carry-qa` ← `/private/tmp/dcx-kw-round-view-qa/sessions` 복사(세라젬 R1 87 · R3 61(직접 추가 1 포함), QA에어컨 R4 확정).
- 시작(가짜 LLM): 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=/private/tmp/dcx-kw-round-carry-qa LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3316 .venv/bin/uvicorn app.main:app --port 8316` · 화면 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8316 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3316`
- 테스트 URL: `http://localhost:3316/pipeline/keywords`

| ID | 시나리오 | 기대 결과 | AC |
|---|---|---|---|
| QA1 | 세라젬 복사본 R3 화면 | 탭 전체 = 61 + 67 = 128, R1 승인 칩에 "R1" 표시(67개) · aria-label 포함, R1 거절 20개 목록에 없음, R3 칩 표시 없음 | AC1 · AC2 |
| QA2 | 세라젬 복사본 R1 화면 | 전체 87, "R1" 표시 없음 | AC3 |
| QA3 | QA에어컨 최종 화면 | 전체 190, 라운드 표시 없음 | AC3 |
| QA4 | 오른쪽 축 분포 · 승인 예정/거절 줄 | R1 · R3 화면 같은 누적 값 | AC4 |

## 검증
`development-harness evidence`.

## 되돌리기
브랜치 미머지 또는 머지 커밋 revert. 데이터 변경 없음.

## 엔지니어링 리뷰 (요약)
- 범위: 화면 4파일 + 테스트. 새 의존성 없음. Task 1개.
- 확인한 기존 구조: `KeywordChip.tsx:17` `labels` 배열이 Badge와 aria-label을 함께 만든다 → 표시 하나 추가로 접근성까지 해결. `KeywordGroup.tsx:20`에서 칩 생성.
- 위험: 이전 라운드 단어를 R3에서 거절하면 R3 목록에서 사라짐(설계 4절 수용).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 0 issues, 0 critical gaps |

- **VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
