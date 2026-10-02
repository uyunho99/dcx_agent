# 키워드 화면 — 이전 라운드 승인 단어 누적 + 라운드 표시 · 설계

기획: `01-brainstorm.md`(승인). 기준 `8c7a693`.

## 1. 구조 (화면만, 서버 변경 없음)
- `frontend/src/lib/logic/roundKeywords.ts`
  - `roundKeywords(all, round, final)` 규칙 변경: `final`이면 `all`, 아니면 `all.filter(k => k.round === round || (k.round < round && k.status !== 'rejected'))`. 순서 유지.
  - 신규 `export function roundTag(keywordRound: number, currentRound: number | undefined): string | undefined` — `currentRound`가 있고 `keywordRound !== currentRound`이면 `` `R${keywordRound}` ``, 아니면 `undefined`.
- `frontend/src/components/keywords/KeywordChip.tsx`: 선택 prop `roundTag?: string`. 있으면 기존 `labels` 배열 맨 앞에 넣는다 → 기존 `<Badge>` 표시와 `aria-label`에 같이 들어간다. 모양 · 클래스 추가 없음.
- `frontend/src/components/keywords/KeywordGroup.tsx`: 선택 prop `currentRound?: number`를 받아 각 칩에 `roundTag={roundTag(k.round, currentRound)}` 전달.
- `frontend/src/app/pipeline/keywords/page.tsx`: `<KeywordGroup … currentRound={ui.final ? undefined : round} />` 한 곳 추가. `shown` 사용처(목록 · 묶음 · 탭 개수)는 그대로.

## 2. 데이터
- `round < 선택 라운드`인 단어는 앞 라운드 확정분(top-level `keywords`) 또는 직접 추가분. 상태는 approved/rejected. 미확정 R2는 서버 응답에서 이미 빠져 있다.
- 이번 라운드 단어의 상태(pending · 임시 거절)는 기존 `overrides` 반영 후 판정 — 이번 라운드 단어는 상태와 관계없이 모두 보인다.

## 3. UI 상태
| 화면 | 목록 | 라운드 표시 |
|---|---|---|
| R1 | round 1 전부 | 없음 |
| R3 | round 3 전부 + round 1 승인 | round 1 칩에 "R1" |
| R4 | round 4 전부 + round 1 · 3 승인 | "R1" · "R3" |
| 최종(R4 확정) | 전체 | 없음 |
레이아웃 · 색 · 컴포넌트 구조 변경 없음(기존 Badge 하나 추가) → `plan-design-review` 미적용. 브라우저 QA로 확인.

## 4. 실패 · 경계
- 이전 라운드 승인 단어를 R3 화면에서 거절하면 그 단어는 거절 상태가 되고 R3 목록에서 빠진다(이전 라운드 거절 단어는 숨김). 거절 해제는 그 라운드(R1)를 골라 할 수 있다. 예전 누적 화면에서도 거절 자체는 가능했던 동작.
- 확정 요청은 `current.keywords`(이번 라운드)만 — 변경 없음.

## 5. 권한
변경 없음.

## 6. 테스트
- `roundKeywords.test.ts`: 이전 라운드 승인 포함 · 이전 라운드 거절 제외 · 다음 라운드 단어 제외 · final 누적 · `roundTag` 4경우.
- 브라우저: 세라젬 형태 R3 = 127(R1 표시 67), R1 = 87(표시 없음), 최종 = 190(표시 없음).
