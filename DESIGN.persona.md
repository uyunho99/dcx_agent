# Person A 디자인 시스템 — design.md

Person A 제품(SaaS 웹 앱)과 그 주변 화면을 만들 때 따르는 규칙과 토큰의 단일 기준 문서입니다. 브랜드는 **사람(Human)을 이해하는 지능(Intelligence)** — 밝은 블루 하나와 차분한 그래파이트 하나로 말하고, 나머지는 뉴트럴이 받쳐줍니다. 화면은 데이터와 작업이 주인공이므로 브랜드 색은 절제해서 씁니다.

- 서체: Pretendard (자체 호스팅, 100~900)
- 테마: Light (다크 테마는 미정의)
- 컴포넌트 네임스페이스: `PersonA` (React 18)
- 원본: Design System 아티팩트 "Person A" → `project/tokens.json`, `project/README.md`, `project/components/*`

---

## 1. 원칙

1. **데이터가 주인공** — 브랜드 색은 로고·선택 상태·히어로에만. UI의 액션은 별도의 액션 블루.
2. **보더로 구분, 그림자는 떠 있는 것에만** — 카드·패널·입력 필드는 `line` 1px 보더. `shadow`는 드롭다운·모달·토스트.
3. **세 단계면 충분** — 텍스트 3단계(`ink` / `ink-secondary` / `ink-subtle`), 모서리 3단계, 제목 위계 3단계.
4. **색만으로 의미를 전달하지 않는다** — 상태는 항상 단어(뱃지 텍스트)나 아이콘을 동반.
5. **대비는 검증된 값만** — 모든 텍스트/배경 쌍 4.5:1 이상, 컨트롤 보더·포커스 링·아이콘 3:1 이상.

---

## 2. 컬러

### 2.1 브랜드

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `persona-blue-100` | `#37b7f8` | 브랜드 시그니처(Human / Understanding / Possibility). 로고, 브랜드 일러스트, 선택 상태 강조, 마케팅 히어로 채움. **흰 배경 위 텍스트·아이콘·버튼 채움에는 쓰지 않는다**(대비 2.3:1). 이 색 위의 글자는 항상 `ink`(7.4:1). |
| `persona-blue-soft` | `#e4f5fe` | 브랜드 블루의 연한 틴트. 선택된 행·탭 배경, 브랜드 강조 카드 배경. 위 글자는 `ink`. |
| `persona-graphite-100` | `#68696e` | 브랜드 그래파이트(Intelligence / Structure / Reliability). 워드마크, 브랜드 문구의 보조 텍스트. `surface`·`surface-raised` 위 5.1:1 이상. 제품 UI 보조 텍스트는 `ink-secondary`를 쓴다. |

### 2.2 액션

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `action` | `#0a73b5` | 제품 UI의 액션 색. 기본 버튼 채움(위 글자 `on-action`, 5.1:1), 링크 텍스트(`surface-raised` 위 5.1:1, `surface` 위 4.7:1), 포커스 링, 활성 탭 밑줄, 체크·라디오 선택 상태. |
| `action-hover` | `#085d93` | `action` 요소의 hover·pressed 채움. 위 글자 `on-action`(7.0:1). |
| `action-soft` | `#e8f4fc` | `action`의 연한 틴트. secondary 버튼 hover 배경, info 배너·뱃지 배경, 선택된 메뉴 항목 배경. 위 글자는 `action`(4.5:1) 또는 `ink`. |
| `on-action` | `#ffffff` | `action`·`action-hover`·`danger` 채움 위의 글자와 아이콘. |

### 2.3 서피스·보더

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `surface` | `#f6f7f9` | 앱 페이지 배경(사이드바 뒤, 콘텐츠 영역 뒤). |
| `surface-raised` | `#ffffff` | 카드, 패널, 모달, 드롭다운, 테이블 본문, 입력 필드 배경. `surface` 위에 `line` 보더로 구분. |
| `surface-sunken` | `#eceef1` | 테이블 헤더, 비활성 입력 필드, 코드 블록, 하위 영역 배경. |
| `line` | `#e1e4e8` | 구분선, 카드·테이블 보더. 장식용(의미 없음). |
| `line-strong` | `#7f838b` | 입력 필드·체크박스 등 컨트롤의 기본 보더. `surface-raised` 위 3.8:1, `surface` 위 3.6:1. |

### 2.4 텍스트

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `ink` | `#1c1e22` | 제목과 본문. `surface` 15.6:1, `surface-raised` 16.7:1, `surface-sunken` 14.4:1, `persona-blue-100` 7.4:1. |
| `ink-secondary` | `#55585f` | 설명문, 테이블 헤더 라벨, 메타 정보. `surface` 6.7:1, `surface-raised` 7.1:1. |
| `ink-subtle` | `#6a6e76` | 플레이스홀더, 비활성 텍스트, 타임스탬프. `surface-raised` 5.1:1, `surface` 4.8:1 — **이보다 연한 글자는 만들지 않는다.** |

### 2.5 상태

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `success` | `#1b7446` | 성공·완료·활성. `success-soft` 5.2:1, `surface-raised` 5.6:1. |
| `success-soft` | `#e6f6ec` | success 뱃지·배너 배경. |
| `warning` | `#9a5b00` | 주의·대기·만료 임박. `warning-soft` 4.9:1, `surface-raised` 5.4:1. |
| `warning-soft` | `#fff3dc` | warning 뱃지·배너 배경. |
| `danger` | `#c62828` | 오류·삭제·실패 텍스트·아이콘, 파괴적 버튼 채움(위 글자 `on-action` 5.6:1), 오류 입력 필드 보더. `danger-soft` 4.9:1. |
| `danger-soft` | `#fdeaea` | danger 뱃지·배너 배경, 오류 입력 필드 배경. |

info는 별도 색 없이 `action` + `action-soft`를 재사용합니다.

### 2.6 색 사용 규칙

- 페이지 배경 `surface` → 카드·패널 `surface-raised` + `line` 보더. 정적 카드에 그림자 없음.
- 버튼·링크·포커스·선택 상태는 `action`. 브랜드 블루로 버튼을 채우지 않는다.
- 파괴적 액션(삭제, 해지) 버튼만 `danger` 채움. 한 화면에 파괴적 버튼은 하나.
- 컨트롤 보더 `line-strong`, 포커스 링 `action` 2px solid, offset 2px. 포커스 링을 없애지 않는다.
- 상태 색은 `-soft` 배경과 짝으로만 조합하고, 항상 텍스트·아이콘을 동반한다.

---

## 3. 타이포그래피

### 3.1 서체

```css
--font-sans: Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", system-ui, sans-serif;
--font-mono: "SF Mono", Menlo, Consolas, "D2Coding", monospace;
```

Pretendard는 `fonts/Pretendard-{Thin…Black}.otf` 9종을 자체 호스팅합니다. **UI에는 400 / 500 / 600 / 700만** 씁니다. Thin·ExtraLight·Light·ExtraBold·Black은 마케팅 그래픽 전용.

### 3.2 스케일

| 스타일 | 크기 / 행간 | 굵기 | 자간 | 용도 |
| --- | --- | --- | --- | --- |
| `display-lg` | 32 / 40 | 700 | -0.02em | 페이지 히어로 숫자(KPI), 온보딩·빈 상태 헤드라인. 한 화면에 하나. |
| `display` | 24 / 32 | 700 | -0.01em | 페이지 제목(H1). 앱 헤더 아래 한 번. |
| `heading-lg` | 20 / 28 | 600 | — | 섹션 제목(H2), 모달 제목, 카드 그룹 제목. |
| `heading` | 16 / 24 | 600 | — | 카드 제목(H3), 사이드 패널 제목, 설정 항목 이름. |
| `body-lg` | 16 / 24 | 400 | — | 긴 본문: 도움말, 온보딩 설명, 빈 상태 안내. |
| `body` | 14 / 20 | 400 | — | **기본 UI 본문.** 폼 값, 테이블 셀, 목록 항목, 설명문. |
| `body-strong` | 14 / 20 | 600 | — | 본문 강조, 테이블 첫 열(엔티티 이름), 버튼 라벨. |
| `label` | 13 / 18 | 500 | — | 폼 라벨, 테이블 헤더, 탭·메뉴 항목, 뱃지 텍스트. |
| `caption` | 12 / 16 | 400 | — | 타임스탬프, 힌트, 각주, 카운터. **12px 아래로 내려가지 않는다.** |
| `code` (mono) | 13 / 20 | 400 | — | API 키, ID, 코드, 로그. `surface-sunken` 배경 위. |

### 3.3 규칙

- 위계: `display`(24) 한 번 → `heading-lg`(20) → `heading`(16). 카드 안에서는 `heading` → `body` → `caption` 세 단계만.
- 숫자 열(금액, 카운트)은 `font-variant-numeric: tabular-nums`.
- 대문자 변환(uppercase) 스타일은 어디에도 쓰지 않는다.

---

## 4. 간격·모서리·레이어

### 4.1 Spacing (4px 베이스)

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `space-1` | 4px | 아이콘–라벨 사이, 뱃지 세로 패딩, 인라인 간격 |
| `space-2` | 8px | 버튼·입력 세로 패딩, 뱃지 가로 패딩, 라벨–필드 사이 |
| `space-3` | 12px | 버튼 가로 패딩(sm), 테이블 셀 패딩, 목록 항목 간격, 툴바 내부 |
| `space-4` | 16px | 버튼 가로 패딩(md), 카드 패딩(compact), 폼 필드 간 세로 간격, 사이드바 항목 패딩 |
| `space-6` | 24px | 카드·모달·패널 패딩(기본), 카드 그리드 간격, 폼 섹션 사이 |
| `space-8` | 32px | 페이지 좌우 여백, 섹션 제목 위 여백 |
| `space-12` | 48px | 페이지 섹션 사이, 온보딩·설정 블록 간격 |

### 4.2 Radius

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `radius-sm` | 6px | 버튼, 입력 필드, 체크박스, 사각 뱃지, 툴팁 |
| `radius-md` | 10px | 카드, 패널, 모달, 드롭다운, 팝오버, 썸네일 |
| `radius-full` | 999px | pill 뱃지, 아바타, 토글, 상태 점 |

로고의 둥근 삼각형처럼 모서리는 살리되 과하게 둥글지 않게.

### 4.3 Shadow

| 토큰 | 값 | 용도 |
| --- | --- | --- |
| `shadow-sm` | `0 1px 2px rgba(28,30,34,0.06)` | 카드 hover, 드래그 중인 항목. 정적 카드에는 쓰지 않는다. |
| `shadow-md` | `0 8px 24px rgba(28,30,34,0.12), 0 1px 2px rgba(28,30,34,0.06)` | 드롭다운, 팝오버, 모달, 토스트 |

### 4.4 레이아웃·모션

- 좌측 사이드바 240px(`surface`) + 콘텐츠 영역(`surface`, 좌우 패딩 `space-8`, 최대 폭 1200px). 우측 컨텍스트 패널은 `surface-raised` + 좌측 `line` 보더.
- 카드 그리드 간격 `space-6`, 카드 최소 폭 280px.
- 모션은 **150ms ease-out** 하나(hover, 열림·닫힘). 장식 애니메이션 없음.

---

## 5. 콘텐츠·톤

- 한국어 UI 기본. 짧은 평서형(“저장되었습니다”, “3개 항목을 선택했습니다”). 버튼 라벨은 동사로 끝낸다(“저장”, “초대 보내기”, “삭제”).
- “회원님” 같은 호칭 없이 쓴다. 시스템 주체는 기능 이름으로.
- 고유명사·제품명은 원문 그대로: “Person A”, “Synthetic Persona”.
- 숫자는 천 단위 콤마, 날짜는 `2026. 9. 18.` 또는 상대 시간(“3분 전”)을 `caption`으로.
- 이모지는 UI 텍스트에 쓰지 않는다. 상태는 뱃지의 단어와 색으로.
- 빈 상태·오류 메시지는 “무엇이 일어났는지 + 다음 행동 한 가지”. 사과·감탄 표현 없음.

---

## 6. 아이콘·로고·이미지

- 아이콘: **Lucide**, 1.5px 스트로크, 16px·20px 두 크기. 의미 아이콘은 `ink`/`ink-secondary`, 상태 아이콘은 해당 상태 색. `persona-blue-100`은 아이콘 색으로 쓰지 않는다(3:1 미달).
- 로고: `assets/Logo/person-a-logo.png`(마크 + 워드마크 세로 조합)를 그대로 쓴다. 다시 그리거나 색을 바꾸지 않는다. 최소 높이 32px, 여백은 마크 높이의 1/4 이상. 어두운 배경 위 사용은 별도 에셋 전까지 피한다.
- 일러스트·빈 상태 그래픽은 `persona-blue-100`, `persona-blue-soft`, `ink`, `line` 네 색만. 그라디언트 없음.

---

## 7. 컴포넌트

기본 세트 5종. 모두 `window.PersonA` 네임스페이스(React 18)로 제공되며, 새 컴포넌트는 같은 토큰 사용 방식(보더 `line`, 컨트롤 보더 `line-strong`, 포커스 `action`, 본문 `body`)을 따릅니다.

### 7.1 Button

명령을 실행하는 버튼. 라벨은 동사로 끝나는 2~4어절.

| prop | 값 | 설명 |
| --- | --- | --- |
| `variant` | `primary` \| `secondary`(기본) \| `quiet` \| `danger` | primary는 화면(모달)당 하나. quiet는 툴바·카드 헤더·테이블 셀. danger는 파괴적 액션 확정 버튼에만. |
| `size` | `md`(36px, 기본) \| `sm`(28px) | sm은 테이블·툴바 |
| `icon` | ReactNode | 16px SVG, 라벨 앞 |
| `loading` | boolean | 비활성화 + 라벨 “처리 중…” |
| `disabled` | boolean | opacity 0.5 |

스타일: `primary` = `action`/`on-action`, hover `action-hover`. `secondary` = `surface-raised` + `line-strong` 보더, hover `action-soft`. `quiet` = 글자 `action`, hover `action-soft`. `danger` = `danger`/`on-action`. 모두 `radius-sm`, 600 굵기.

Do: 버튼 그룹은 우측 정렬, primary 가장 오른쪽, 간격 `space-2`. 아이콘만 있는 버튼은 `aria-label`.
Don't: 페이지 이동에 primary 사용, `persona-blue-100`으로 채움.

### 7.2 Input

라벨·힌트·오류가 묶인 한 줄 입력. 필드 사이 간격 `space-4`.

| prop | 설명 |
| --- | --- |
| `label` | 항상 준다(숨길 때만 `aria-label`) |
| `hint` | 형식 안내(`caption`, `ink-secondary`). 오류가 있으면 숨김 |
| `error` | 오류 문장 하나. 보더 `danger`, `role="alert"` |
| `required` | 라벨 뒤 `*`(`danger`) |
| `size` | `md`(36px) \| `sm`(28px) |
| 그 외 | `type`, `value`, `onChange`, `placeholder`, `disabled` 등 input 속성 |

상태: 기본 `surface-raised` + `line-strong` → hover 보더 `ink-secondary` → 포커스 보더·아웃라인 `action` → 오류 보더 `danger` → 비활성 `surface-sunken` + `ink-subtle`.

Don't: 플레이스홀더를 라벨 대신 쓰지 않는다.

### 7.3 Card

`surface-raised` + `line` 1px + `radius-md`. 그림자 없음.

| prop | 설명 |
| --- | --- |
| `title` / `description` | `heading` 16/600, 설명은 `ink-secondary` |
| `actions` | 헤더 우측(quiet/secondary Button, Badge) |
| `footer` | 하단 버튼 영역, 우측 정렬, 상단 `line` 구분선 |
| `padding` | `md`(`space-6`, 기본) \| `sm`(`space-4`, 그리드 카드) |
| `interactive` | 카드 전체가 클릭 대상일 때만. hover `shadow-sm` + `line-strong` |

Don't: 카드 안에 카드, 좌측 색 보더로 상태 표시(Badge를 쓴다), 페이지 전체를 카드 하나로 감싸기.

### 7.4 Badge

상태·분류를 한두 단어로. 텍스트가 의미를 전달하고 색은 보조.

| tone | 배경 / 글자 | 의미 |
| --- | --- | --- |
| `neutral`(기본) | `surface-sunken` / `ink-secondary` | 분류·카운트(“초안”, “12개”) |
| `info` | `action-soft` / `action` | 진행 중·안내 |
| `success` | `success-soft` / `success` | 완료·활성·연결됨 |
| `warning` | `warning-soft` / `warning` | 대기·만료 임박·확인 필요 |
| `danger` | `danger-soft` / `danger` | 실패·오류·중단 |
| `brand` | `persona-blue-soft` / `ink` | Person A가 생성·추천한 것(“AI 생성”). 상태 표시에는 쓰지 않는다 |

옵션: `pill`(`radius-full`), `dot`(라이브 상태 점). 높이 22px, 13px/500, `radius-sm`.

Don't: 뱃지를 클릭 대상으로 만들기, 한 항목에 3개 이상.

### 7.5 Table

같은 구조의 항목 5개 이상을 열로 비교할 때. 컨테이너 `surface-raised` + `line` + `radius-md`, 헤더 `surface-sunken` + `label`(`ink-secondary`), 본문 `body`.

| prop | 설명 |
| --- | --- |
| `columns` | `{ key, header, render?, align?: 'left' \| 'right', width? }[]` — 숫자 열은 `right`(tabular-nums) |
| `rows` / `rowKey` | 데이터와 키 함수 |
| `caption` | 테이블 제목(페이지 제목이 바로 위면 생략) |
| `dense` | 13px, `space-2` 패딩 — 로그·관리 화면 |
| `selectedKey` | 선택 행 `persona-blue-soft` |
| `emptyText` | 빈 상태 문장(기본 “표시할 항목이 없습니다.”) |

규칙: 첫 열은 엔티티 이름(행 헤더, `body-strong`). 상태 열은 Badge, 액션 열은 `quiet sm` Button을 가장 오른쪽에. 행 hover `surface`. 줄무늬 배경 없음. 7열 이상이면 열을 숨기거나 상세 패널로. 셀에 여러 줄 설명 없음.

---

## 8. 접근성 체크리스트

- [ ] 텍스트/배경 대비 4.5:1 이상 (24px+ 또는 19px+ bold는 3:1)
- [ ] 컨트롤 보더·포커스 링·의미 아이콘 3:1 이상 (`line-strong`, `action`)
- [ ] 포커스 링을 제거하지 않음 (`outline: 2px solid var(--action); outline-offset: 2px`)
- [ ] 상태는 색 + 텍스트/아이콘
- [ ] 모든 입력에 `label`, 오류에 `aria-invalid` + `role="alert"`
- [ ] 아이콘 전용 버튼에 `aria-label`
- [ ] 12px 미만 텍스트 없음

---

## 9. 빠른 참조 (CSS 변수)

```css
:root {
  /* brand */
  --persona-blue-100: #37b7f8;  --persona-blue-soft: #e4f5fe;  --persona-graphite-100: #68696e;
  /* action */
  --action: #0a73b5;  --action-hover: #085d93;  --action-soft: #e8f4fc;  --on-action: #ffffff;
  /* surface & line */
  --surface: #f6f7f9;  --surface-raised: #ffffff;  --surface-sunken: #eceef1;
  --line: #e1e4e8;  --line-strong: #7f838b;
  /* ink */
  --ink: #1c1e22;  --ink-secondary: #55585f;  --ink-subtle: #6a6e76;
  /* status */
  --success: #1b7446;  --success-soft: #e6f6ec;
  --warning: #9a5b00;  --warning-soft: #fff3dc;
  --danger: #c62828;   --danger-soft: #fdeaea;
  /* spacing */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;  --space-4: 16px;
  --space-6: 24px; --space-8: 32px; --space-12: 48px;
  /* radius */
  --radius-sm: 6px;  --radius-md: 10px;  --radius-full: 999px;
  /* shadow */
  --shadow-sm: 0 1px 2px rgba(28,30,34,0.06);
  --shadow-md: 0 8px 24px rgba(28,30,34,0.12), 0 1px 2px rgba(28,30,34,0.06);
  /* type */
  --font-sans: Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", system-ui, sans-serif;
  --font-mono: "SF Mono", Menlo, Consolas, "D2Coding", monospace;
}
```

---

## 10. 미정·다음 단계

- 다크 테마 미정의 (필요 시 `on-…` 토큰 추가 후 별도 테마로)
- 어두운 배경용 로고 에셋 없음
- 다음 컴포넌트 후보: Select, Checkbox/Radio, Toggle, Modal, Toast, 사이드바 내비게이션, Tabs
