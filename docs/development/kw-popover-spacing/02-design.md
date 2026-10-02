# 키워드 거절 팝오버 가림 · 키워드 표시 띄어쓰기 — 설계

기획: [01-brainstorm.md](01-brainstorm.md) (2026-10-02 승인). 기준 브랜치: `origin/main` (a63ffa9, D-325 키워드 형태 규칙 포함).

## 1. 원인
- `.ds-pop`(ds.css:98,159)은 `position:absolute; right:0; width:300px`라서 칩의 오른쪽 끝을 기준으로 **왼쪽으로** 펼쳐진다.
- 칩 묶음/본문(`.pipeline-main`) 쪽 스크롤 컨테이너가 넘친 부분을 잘라, 팝오버 왼쪽이 사이드바 경계에서 잘린다. 사이드바가 펼쳐져(약 280px) 있으면 본문 폭이 줄어 더 자주 생긴다.

## 2. 동작

### 2-1. 사이드바 접기
- `PipelineShell`에 `sideCollapsed`(사용자 선택)와 `sideAutoCollapsed`(팝오버로 인한 일시 접힘) 상태를 둔다. 표시 상태 = 둘 중 하나라도 참이면 접힘.
- 사이드바 상단(로고 옆)에 아이콘 버튼 `사이드바 접기`/`사이드바 펴기`(`PanelLeftClose`/`PanelLeftOpen`, lucide). `aria-expanded`, `aria-controls="pipeline-side"`. 사용자 선택은 `localStorage`(`dcx.sidebar.collapsed`)에 저장, 읽기·쓰기는 try/catch.
- 접힘 스타일은 기존 `@media(max-width:1100px)` 규칙을 `.pipeline-shell[data-side="collapsed"]` 선택자로도 적용해 재사용한다(아이콘만 남는 좁은 사이드바). 1100px 이하에서는 지금처럼 항상 좁은 사이드바.
- 자동 접기: 레이아웃이 컨텍스트 `useSidebarAuto()`를 제공한다 → `{ request(): () => void }`. `KeywordChip`이 팝오버를 열 때 `request()`를 호출하고, 닫힐 때 돌려받은 해제 함수를 호출한다. 요청 카운터가 0이 되면 `sideAutoCollapsed=false`로 열기 전 상태로 복귀. 사용자가 원래 접어 뒀으면 접힌 채 유지(AC2).
- 너비 전환 애니메이션 없음(위치 재계산 단순화). `prefers-reduced-motion` 고려 불필요.

### 2-2. 팝오버 위치 보정
- `ds/Popover`에 열린 직후(`useLayoutEffect` + `requestAnimationFrame` 한 번, 사이드바 접힘 반영 뒤) 패널 위치를 잰다. 패널 왼쪽이 가장 가까운 잘림 조상(overflow ≠ visible) 또는 뷰포트 왼쪽 + 8px보다 왼쪽이면 `data-align="start"`를 붙여 `left:0; right:auto`로 바꾼다. 오른쪽도 같은 방식으로 넘치면 기존 `right:0` 유지.
- 창 크기 변경 시 다시 잰다. `contained` 팝오버는 대상 아님.
- 중복 렌더 확인: 스크린샷에서 패널 테두리가 두 겹으로 보였다. `KeywordChip`/`RejectPopover`가 패널을 두 번 그리는지 확인하고, 두 번 그리면 하나로 줄인다(구현 시 확인 결과를 보고서에 기록).

### 2-3. 키워드 표시 띄어쓰기
- 백엔드 `backend/app/keywords/display.py` 새 모듈: `display_form(kw: str) -> str`.
  1. 이미 공백이 있으면 그대로 반환.
  2. 한글이 아니거나 3자 이하면 그대로.
  3. `Kiwi().space(kw)` (Kiwi 인스턴스는 모듈 전역 지연 생성, `functools.lru_cache(maxsize=4096)`).
  4. 한 글자 조각은 앞 조각에 붙인다(첫 조각이면 뒤 조각에 붙임). 예: `귀촌 부부 온도 차` → `귀촌 부부 온도차`, `층 간 소음 스트레스` → `층간 소음 스트레스`.
  5. 공백을 지운 결과가 원문과 다르면(형태 변형) 원문 반환. Kiwi 예외 시 원문 반환.
- API 응답: 키워드를 내보내는 직렬화 지점에서 `display` 필드를 덧붙인다. **저장 모델 `Keyword`와 저장 파일에는 넣지 않는다**(파생 값). 저장/검색/중복(`norm_key`)/수집 검색어는 `kw` 그대로.
- 프런트: `Keyword` 타입에 `display?: string`. `KeywordChip` 표시 텍스트 = `k.display ?? k.kw`, `title`에 원문 `kw`(띄어쓰기와 다를 때만). `aria-label`도 표시값 사용. 다른 키워드 목록 표시 지점(검색량 표 등)이 있으면 같은 규칙을 쓴다. API 요청에 넣는 값은 모두 `kw`/`id`.

## 3. 데이터·API
| 항목 | 변경 |
|---|---|
| 저장 `Keyword` 모델 | 없음 |
| 키워드 목록/라운드 응답 | 각 키워드에 `display: string` 추가(읽기 전용) |
| 요청 본문 | 없음 |

## 4. 권한
변경 없음. 읽기 전용 버전 보기에서도 접기 버튼은 동작한다.

## 5. 실패 상태
- Kiwi 로드 실패/예외 → `display = kw`. 응답 실패로 번지지 않는다.
- `localStorage` 차단 → 펼침 기본값.
- 위치 측정 실패(패널 없음) → 기존 `right:0`.

## 6. UI 상태 · 반응형 · 접근성
- 상태: 펼침 / 사용자 접힘 / 자동 접힘(팝오버 열림) / 1100px 이하 항상 좁음.
- 접힌 사이드바에서도 단계 아이콘·Known Insight·외부 API 버튼은 지금 1100px 이하 화면과 같이 아이콘으로 남는다.
- 접기 버튼: 36×36 이상, 포커스 링, `aria-label` 상태에 맞게 변경.
- 팝오버 포커스 이동·Esc 동작은 기존 그대로.

## 7. 디자인 검토 (plan-design-review 요지)
- 정보 위계: 자동 접힘은 팝오버 작업에 집중하게 하고, 닫으면 바로 원래대로라 맥락을 잃지 않는다.
- 위험: 접힘·펼침으로 칩 위치가 바뀐다 → 팝오버는 칩 기준이라 함께 움직이고, 위치는 접힘 반영 뒤 측정한다.
- 일관성: 접힘 스타일을 기존 1100px 규칙과 같게 해 새 시각 상태를 만들지 않는다.
- 표시값과 원문이 달라 혼동될 수 있음 → `title`로 원문 노출.
