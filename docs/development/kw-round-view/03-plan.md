# 키워드 화면 — 고른 라운드의 단어만 보기 · 구현 계획 + QA 계획

> 실행: 하네스 네이티브. 구현은 `codex:codex-rescue`(`--wait --fresh`, 쓰기)에 위임. Main Claude는 위임 · 확인 · 리뷰 · 커밋.

**목표:** 키워드 화면 목록이 "검토할 라운드"에서 고른 라운드의 단어만 보여주게 한다(최종 화면은 누적).
**설계:** `02-design.md`(승인) · 기획 `01-brainstorm.md`(승인). 기준 `9b8edeb`.

## 전역 제약
- 서버 · API · 저장 변경 금지. 레이아웃 · 문구 · 클래스 변경 금지.
- `all`을 그대로 쓰는 곳(reveal 존재 확인 · 중복 찾기 · 축 분포 approved · 승인 예정/거절 줄)은 바꾸지 않는다.
- 사용자 서버(3000 · 3310 · 3400 · 3401 · 8310 · 8400 · 8401)는 건드리지 않는다.

## 리뷰 집중 지점
1. 세라젬 형태(R1 87 · R3 60) — R1/R3 전환 시 목록 · 탭 개수가 바뀐다 → T1 단위 테스트 + QA1.
2. 최종 화면(R4 확정)은 누적 → T1 `final` 테스트 + QA2.
3. 검색 · 필터(미연결 등) 개수는 선택 라운드 기준 → QA1.
4. 확정 요청 결정 목록은 그대로 `current.keywords` 기준 → 코드 리뷰.
5. 직접 추가한 단어가 그 라운드 목록에 즉시 보인다 → QA3.

### T1: roundKeywords + 화면 적용 (Codex)
**파일(소유):** 신규 `frontend/src/lib/logic/roundKeywords.ts`, `frontend/src/lib/logic/roundKeywords.test.ts` · 수정 `frontend/src/app/pipeline/keywords/page.tsx` · `docs/development/kw-round-view/logs/T1-*.txt` · `reports/T1.md`
**인터페이스:** `export function roundKeywords<T extends { round: number }>(all: T[], round: number, final: boolean): T[]`

- [ ] RED — `roundKeywords.test.ts`: `it('keeps only the selected round')` (round 1/3 혼합 입력에서 1 → round 1만, 3 → round 3만, 없는 라운드 → []), `it('returns everything on the final view')` (final=true → 입력 그대로, 순서 유지).
  `npm --prefix frontend test -- src/lib/logic/roundKeywords.test.ts` → 실패(모듈 없음). 로그 `logs/T1-red.txt`.
- [ ] GREEN — 함수 구현. `page.tsx`: `all` 바로 아래 `const shown = roundKeywords(all, round, ui.final);` 추가, 설계 1절의 3곳(`groups`의 `all.map`, `tabKeywords`, 축 탭 count)만 `shown`으로. 그 밖 변경 금지.
- [ ] 확인 — `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build` 통과. 로그 `logs/T1-green.txt`. 보고 `reports/T1.md`.

## 독립 리뷰
- Main Claude diff 검토(읽기 전용). 필요 시 Codex 읽기 전용 리뷰.

## QA 계획 (gstack `qa-only` 기준, 내장 브라우저)
- worktree `~/Desktop/dcx_agent-kw-round-view`. 의존성: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`, `npm --prefix frontend ci`.
- 데이터: `/private/tmp/dcx-kw-round-view-qa` — 기존 QA 폴더 `/private/tmp/dcx-kw-skip-r2-qa/sessions`의 세라젬 복사본(R1 87 · R3 60)과 새 세션(R1 · R3 · R4 확정)을 `cp -R`.
- 시작(가짜 LLM): 백엔드 `cd backend && env STORAGE=local LOCAL_DATA_DIR=/private/tmp/dcx-kw-round-view-qa LLM_BACKEND=fake EMBED_BACKEND=fake JEV_BACKEND=fake LABEL_GPT_BACKEND=fake AUTOCOMPLETE_BACKEND=fake CORS_ORIGINS=http://localhost:3315 .venv/bin/uvicorn app.main:app --port 8315` · 화면 `cd frontend && env NEXT_PUBLIC_API_URL=http://localhost:8315 NEXT_PUBLIC_INTERNAL_TOOLS=true npx next dev -p 3315`
- 테스트 URL: `http://localhost:3315/pipeline/keywords` (1360×900)

| ID | 시나리오 | 기대 결과 | AC |
|---|---|---|---|
| QA1 | 세라젬 복사본: 검토할 라운드 R1 → R3 전환 | R1: 탭 "전체 87"(축 탭 합 87), R3: "전체 60". 칩 목록이 바뀜. 축 분포 카드 · 승인 예정/거절 줄은 두 경우 같은 누적 값 | AC1 · AC3 |
| QA2 | 새 세션(R4 확정) 최종 화면 | 탭 "전체" = R1+R3+R4 합(190) | AC2 |
| QA3 | 세라젬 복사본 R3(미확정) 화면에서 키워드 직접 추가 | 추가한 칩이 R3 목록에 보임 · 요청 값 변경 없음 | AC4 |
| QA4 | R3 거절 사유 입력 → 임시 저장 | 기존과 같은 동작 · 오류 없음 | AC4 |

## 검증
`development-harness evidence`(pytest · lint · build · vitest).

## 되돌리기
브랜치 미머지 또는 머지 커밋 revert. 데이터 변경 없음.

## 엔지니어링 리뷰 (요약)
- 범위: 화면 1파일 + 순수 함수 1개. 새 의존성 없음. 병렬화 불필요(Task 1개).
- 확인한 기존 구조: `page.tsx:92-97 · 125 · 137 · 144 · 159 · 166`의 `all` 사용처 7곳 중 목록 3곳만 교체.
- 위험: 다른 라운드 중복 단어 "확인하기" 스크롤 불가(설계 4절 수용).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 0 issues, 0 critical gaps |

- **VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
