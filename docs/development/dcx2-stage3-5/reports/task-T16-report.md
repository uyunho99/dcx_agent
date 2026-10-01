# T16 구현 보고서

## 상태

프론트 공용 컴포넌트, API 클라이언트, 지금 할 일 우선순위 및 판정 단축키 구현 완료. 전체 Vitest 155개와 lint, TypeScript 검사 및 Webpack 프로덕션 빌드 통과. 요청한 기본 `npm --prefix frontend run build`는 코드 오류가 아니라 샌드박스의 포트 바인딩 제한으로 실패했으므로 **요청한 세 기본 명령 모두 통과 조건은 충족하지 못했다**. 설정 변경 없이 대체 빌드를 검증했다.

작업 위치는 지정 저장소이며 네트워크, 패키지 설치, git 쓰기/커밋을 하지 않았다. T15의 병행 백엔드 변경은 수정하지 않았다. pipeline 페이지도 수정하지 않았다.

## 읽은 기준

- `.superpowers/sdd/03-plan/task-T16-brief.md`
- `docs/development/dcx2-stage3-5/02-design-r2.md`: 4.11, 6.3, 8, 9.1, 10, 13 및 관련 데이터 모델
- `docs/development/dcx2-stage3-5/mockups/index.html`: 판정 카드, 진행/성능 표, Known Insight
- 0~2단계 설계 10절 및 기존 DS, API contextRequest/errors, 단축키 및 테스트 패턴
- backend prep, labeling_v2, training_v2, known, chat 라우터 및 관련 schema/overview/route/audit/registry/export/known 모델
- 사용자 Controller rulings를 오래된 설계 문구보다 우선 적용했다.

## 구현

### 로직

- `pickNowCard`: 시작 전 → 중단 워커 → 정의 점검 → 검수 큐 → 감사 대기 → 판정 중 → 완료. 시작 전 방식 선택 안내와 예상 한 줄, 큐 예상 시간, 상태별 단일 액션을 반환한다.
- 감사 대기는 별도 boolean이 없는 실제 응답에 맞춰 `overview.now.state === 'audit'`로 판단한다. 상위 우선순위가 없는 경우 백엔드가 이 상태를 제공한다.
- `keyAction`: 카드 포커스에서만 A, 1~6, S, Enter, →를 매핑한다. 입력/textarea/select/contenteditable, 패널/팝오버, 조합 중 입력, modifier, repeat, 이미 처리된 이벤트는 무시한다. 버튼의 Enter는 네이티브 활성화로 남겨 중복 제출을 막는다.

### 클라이언트와 타입

- prep 설정 PUT, 실행 POST, 상태 GET.
- label 방식, 시작, 워커 pause/resume, overview, next, seen, preview, submit, audit.
- train 시작, 상태, export, 모델 목록/상세.
- Known Insight 목록, 문장/문서 추가, 문장 수정, 삭제.
- sid/id와 version, after 커서를 인코딩하고 정확한 메서드와 요청 본문을 사용한다. next는 한 건만 받는다.
- `markLabelSeen`은 명시적인 호출 함수다. 페이지에서 최초 overview를 읽은 뒤 열 때 한 번 호출하고 폴링에는 넣지 않아야 한다.
- 기존 `contextRequest`와 오류 표시를 재사용한다. draft 저장은 기존 `patchSession`을 사용하면 되므로 중복 래퍼를 만들지 않았다. 신규 클라이언트는 전체 세션 저장을 호출하지 않는다.
- 새 wire 타입은 기존 타입을 깨지 않도록 추가했다. legacy overview는 분리된 응답 타입이다. 모델 목록의 실제 `selectable/reason`을 반영했다.

### 컴포넌트

- `TagToggle`: 버튼, aria-pressed, 단축키 안내, disabled.
- `LevelBadge`: Core / Supporting / Non 글자와 DS 배지.
- `LabelerProgress`: 진행 막대, 판정/잔여 수, 남은 예상 분, 중단 사유와 보조 pause/resume 버튼.
- `KappaTable`: 감사 필드/등급별 표본, κ, Jev/GPT 정확도, 30건 미만 표본 안내와 κ 0.75 미만 정의 점검 안내.
- `QueueCard`: 원문/댓글, 8개 태그, signal, Non 사유. 등급은 서버 preview만 사용하며 프론트에서 계산 규칙을 구현하지 않았다. 오래된 preview 응답을 무시하고 새 태그의 preview 완료 전 제출을 막는다. 실패하면 입력을 유지한다. 이중 제출을 잠그고 문서/버전/라운드 변경 시 로컬 상태를 초기화한다. 새 문서의 원문에 포커스를 두며 등급 변경은 aria-live로 알린다. 제출 성공 후에만 사람 태그와 Jev 확률/GPT 태그를 비교한다. 제출 전후 각각 파란 버튼 하나만 렌더링한다.
- `KnownInsightsDrawer`: 360px 모달 dialog, 원래 포커스 복귀, Escape 닫기, 목록/빈 상태/로딩/오류, 유형·출처·날짜, 문장 추가, 삭제, 임베딩 미연결 안내. 내부 버튼은 모두 보조 스타일이다.
- `SourceCard`: 채팅 sources 원문, 채널/유사도/서버 제공 등급, 안전한 http(s) 원문 링크, Known Insight 추가와 중복 클릭 방지.

## 정확한 변경 파일

1. `frontend/src/components/label/TagToggle.tsx`
2. `frontend/src/components/label/LevelBadge.tsx`
3. `frontend/src/components/label/LabelerProgress.tsx`
4. `frontend/src/components/label/KappaTable.tsx`
5. `frontend/src/components/label/QueueCard.tsx`
6. `frontend/src/components/known/KnownInsightsDrawer.tsx`
7. `frontend/src/components/known/SourceCard.tsx`
8. `frontend/src/lib/api/prep.ts`
9. `frontend/src/lib/api/label.ts`
10. `frontend/src/lib/api/train.ts`
11. `frontend/src/lib/api/known.ts`
12. `frontend/src/lib/api/label.test.ts`
13. `frontend/src/lib/logic/nowCard.ts`
14. `frontend/src/lib/logic/nowCard.test.ts`
15. `frontend/src/lib/logic/labelKeys.ts`
16. `frontend/src/lib/logic/labelKeys.test.ts`
17. `frontend/src/lib/types.ts`
18. `.superpowers/sdd/03-plan/task-T16-report.md`

## TDD 증거

구현 파일 작성 전에 nowCard, labelKeys, API 테스트를 먼저 작성했다.

RED:

```text
npm --prefix frontend test -- src/lib/logic/nowCard.test.ts src/lib/logic/labelKeys.test.ts src/lib/api/label.test.ts
Test Files 3 failed (3)
Tests no tests
Cannot find module './nowCard'
Cannot find module './labelKeys'
Cannot find module './label'
exit 1
```

초기 GREEN:

```text
동일 명령
Test Files 3 passed (3)
Tests 13 passed (13)
exit 0
```

이후 검증 보강: 새 클라이언트 전체의 경로/메서드, 주요 본문, 버전과 skip 커서 인코딩, storage 오류 보존, 네이티브 버튼 Enter, 팝오버/IME 방어를 추가했다. 파일 소스와 실제 요청 목록에서 전체 세션 저장 경로가 없음을 검증한다. 새 테스트 최종 16개: nowCard 7, labelKeys 5, API 4.

## 최종 검증

| 명령 | 결과 |
| --- | --- |
| `npm --prefix frontend test` | PASS: 29 files, 155 tests |
| `npm --prefix frontend run lint` | PASS: exit 0 |
| `frontend/node_modules/.bin/tsc --project frontend/tsconfig.json --noEmit` | PASS: exit 0 |
| `npm --prefix frontend run build` | FAIL: Turbopack의 기존 globals.css 처리 중 자식 프로세스 포트 바인딩이 샌드박스에서 금지됨 |
| `npm --prefix frontend run build -- --webpack` | PASS: compile, TypeScript, 14/14 static pages, traces 완료 |
| `git diff --check -- frontend` | PASS |

기본 빌드 오류의 핵심:

```text
Failed to write app endpoint /page
[project]/src/app/globals.css [app-client] (css)
creating new process
binding to a port
Operation not permitted (os error 1)
```

승인 요청이나 샌드박스 우회를 하지 않았고 package.json/Next 설정도 바꾸지 않았다. Vitest/빌드의 Node `DEP0205 module.register()` 경고는 기존 도구 체인 경고이며 검사 실패 원인이 아니다.

## 자체 검토와 작은 선택

- 소유 범위의 17개 프론트 파일 및 요청된 보고서만 작성했다. T15의 백엔드 변경은 작업 결과에 포함하지 않는다.
- 제외된 패널/튜닝/보정 기능을 추가하지 않았다. 탭/페이지 변경은 소유 범위 밖이라 구현하지 않았다.
- 단일 주요 버튼 규칙을 지키도록 QueueCard만 현재 액션을 primary로 렌더링하고 Known Insight 및 진행 제어는 secondary로 둔다.
- 날짜는 ko-KR 형식, 처리 문구는 `처리 중…`, 기능 이름은 `Known Insight`로 통일했다.
- 직접 서버 요청으로 저장하고 실패 시 draft를 유지한다. 전체 세션 저장이나 페이지 effect 자동 저장을 추가하지 않았다.
- 등급 미리보기 실패 시 재계산 버튼을 제공한다. 원문이 없는 항목은 제출하지 못하게 했다.
- 감사 next 응답에는 cursor가 없고 after가 감사 분기에 적용되지 않는다. 같은 항목을 다시 열어 입력을 잃게 하지 않도록 cursor 없는 항목의 건너뛰기는 비활성화했다. 검수 큐에서는 item.cursor를 onNext로 전달한다.
- 현재 overview의 예상은 seconds와 내부 토큰 정보뿐이다. 비용이나 정확한 완료 시각을 만들어내지 않고 남은 분을 보여준다.
- 제출 후 비교는 서버가 제공한 Jev 확률과 GPT 태그를 그대로 표시한다. 반환되지 않은 AI 등급을 프론트 규칙으로 추정하지 않는다.

## 우려 및 후속 연결

1. 기본 Turbopack 명령의 성공은 포트 바인딩이 가능한 환경에서 재검증해야 한다. 대체 Webpack 빌드는 통과했다.
2. 페이지는 의도적으로 수정하지 않았다. T17–T20에서 시작 전 방식/모델 선택과 nowCard 액션 연결, overview 후 seen 1회 호출, 폴링, after 커서 전달, draft PATCH 연결을 해야 한다.
3. 부모 화면은 패널/팝오버가 열렸을 때 QueueCard의 focusZone을 전달하고, Known Insight와 외부 API 드로어를 동시에 열지 않도록 관리해야 한다. 카드 자체도 입력 및 패널 하위 이벤트를 방어한다.
4. 채팅 목록의 새 발견 찾기 스위치/재검색은 페이지 책임이다. SourceCard는 sources 한 건 표시와 Known Insight 추가를 제공한다.
5. 새 컴포넌트를 실제 페이지에 장착하는 작업이 범위 밖이므로 브라우저 시각 QA 및 실제 API 연결 E2E는 하지 않았다. 단위 계약, lint, TS 및 전체 프로덕션 빌드로 검증했다.
6. 감사 건너뛰기와 Jev 비용/완료 시각은 현 백엔드 응답에 없는 정보다. 임의 값으로 보완하지 않았다.
