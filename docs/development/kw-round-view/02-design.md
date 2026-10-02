# 키워드 화면 — 고른 라운드의 단어만 보기 · 설계

기획: `01-brainstorm.md`(승인). 기준 `9b8edeb`.

## 1. 구조
- 신규 순수 함수 `frontend/src/lib/logic/roundKeywords.ts`
  - `export function roundKeywords<T extends { round: number }>(all: T[], round: number, final: boolean): T[]` — `final`이면 `all` 그대로, 아니면 `all.filter(k => k.round === round)`.
- `frontend/src/app/pipeline/keywords/page.tsx`
  - `const shown = roundKeywords(all, round, ui.final);` (`all` 계산 바로 아래)
  - `shown`으로 바꾸는 곳(목록 관련 3곳):
    1. 하위 카테고리 묶음 `groups`(95행)의 `all.map(...)` → `shown.map(...)`
    2. 축 탭 목록 `tabKeywords`(97행) `all.filter(...)` → `shown.filter(...)` (→ `visible` · 필터 개수도 따라감)
    3. 축 탭 개수(159행) `all.filter(...).length` → `shown.filter(...).length`
  - `all` 그대로 두는 곳: `reveal`의 존재 확인(125행), 중복 키워드 찾기(137행), 축 분포 `approved`(144행), "승인 예정 · 거절" 줄(166행).
- 서버 · API · 저장 변경 없음.

## 2. 데이터
- 키워드의 `round`는 서버가 붙인다: LLM 생성 = 그 라운드 번호, 직접 추가 = 잠기지 않았거나 확정된 라운드 중 가장 큰 번호(kw-skip-r2 T6). 화면이 그 라운드에서 직접 추가한 단어는 그 라운드에 보인다.
- 확정(commit)은 원래 `current.keywords`(그 라운드)만 보낸다 — 변경 없음.

## 3. UI 상태
| 상황 | 목록 |
|---|---|
| R1 선택 | round 1 키워드 |
| R3 선택 | round 3 키워드 |
| R4 확정 후(최종 화면) | 전체 누적 |
| 생성 중 · 실패 · 0개 | 기존 화면 그대로(목록 카드는 `ui.canEdit`일 때만 보임) |
레이아웃 · 컴포넌트 · 문구 변경 없음 → `plan-design-review` 미적용(목록에 들어가는 항목만 달라짐). 브라우저 QA로 확인.

## 4. 실패 · 경계
- 다른 라운드에 있는 단어를 직접 추가하려다 중복이면: 오류 문구("이미 있는 키워드입니다. …")는 그대로 나오지만 그 단어는 현재 목록에 없어 "중복 키워드 확인하기"가 해당 칩으로 스크롤하지 못한다. 문구로 위치(축 · 하위 카테고리)를 알려주므로 이번 범위에서 수용.
- 직접 추가 기능이 R1 화면에서 쓰였는데 그 시점 가장 큰 라운드가 3이면 round=3으로 저장돼 R3에 보인다(기존 서버 규칙). 이번 범위에서 수용.

## 5. 권한
변경 없음.

## 6. 테스트
- `roundKeywords.test.ts`: 라운드 필터 · final 누적 · 빈 목록.
- 브라우저: 세라젬 형태 QA 세션에서 R1(87) · R3(60) 전환, 최종 화면 누적.
