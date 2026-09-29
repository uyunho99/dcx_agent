# FINAL fix W3 — frontend

## 범위와 결과

frontend와 이 보고서만 수정했다. backend, 다른 작업의 파일, 기존 보고서는 수정하지 않았고 하위 에이전트를 사용하지 않았다. 지정 설계 구간, decision-log 마지막 결정, T19–T24 및 현재 router/계약 구현을 읽었다.

| 항목 | 구현 | 검증 |
|---|---|---|
| F1 | 1100px 이하에서도 footer를 유지. 버전/Layers, 외부 API/Plug에 접근 가능한 이름과 아이콘을 제공하고 텍스트만 숨김. 버전 drawer 안의 비교 버튼 접근 유지. 활동 배지를 SessionList portal에서 셸 공통 polling으로 이동하여 모든 단계에서 유지 | CSS/DOM 경로 검토, 두 INTERNAL_TOOLS 빌드 |
| F2 | 양쪽 snapshot 키워드 목록으로 삭제·추가·이동 계산. rejected 전환은 삭제/취소선, 양쪽 rejected는 제외. 축 분포는 approved만 계산하고 행 변경이 없어도 표시 | finalFix 및 기존 compareView 테스트 |
| F3 | status.available_sources를 기준으로 사용 불가 채널 비활성/회색/사용 불가 배지. 필드 부재 시 integrations 연결 정보로 표시. 초기 채널은 stage0/저장값과 사용 가능 목록의 교집합. unavailable 저장 채널을 제거한 경우 설정을 다시 저장하도록 함. INTERNAL_TOOLS=false는 fixture 행/고급 설정/초기 선택을 숨김. 422 error.message/detail 문자열 및 validation 배열 메시지 보존 | availableChannels, 기존 crawlConfig, mutationContract 테스트 |
| F4 | DirtyProvider가 SaveBar dirty 등록/해제를 공유. StepBar, 버전 열기, 비교 이동, RestartVersion 생성 전에 동일 native confirm. 취소하면 이동/생성하지 않음. 승인된 restart는 이중 confirm하지 않음 | allowNavigation 테스트(깨끗함/취소/정확한 문구), 호출 경로 검토 |
| F5 | start의 세 목록 Enter가 keywordKeys의 공통 helper를 사용. isComposing 또는 keyCode 229면 추가/기본 이벤트 취소하지 않음 | finalFix IME 테스트 및 기존 keywordKeys 테스트 |
| F6 | drafts.keywords.rN.direction 저장/세대 일치 시 복원. 저장된 direction 기준값과 비교하여 임시 저장 후 dirty 해제. 지시 저장 후 서버 초안 direction도 비움. 실패한 라운드에서도 방향 임시 저장 가능 | keywordDraft 테스트(문자열 보존, 세대 불일치, 예전 초안 필드 부재), 코드 흐름 검토 |
| R-61 | context PUT, session PATCH, keyword 생성/재생성/확정/events/manual/suggest/coverage 및 crawl mutation에 화면 version을 명시. 409 버전 변경은 공통 배너와 활성 버전 열기 제공, mutation 재시도 없음. 서버 성공/오류가 확정 라운드 재생성 가능 여부를 결정. 기존 라운드 선택 추가로 복사된 R1–R3 재생성 접근 제공 | mutationContract 쿼리/409 단일 호출/이벤트 테스트, roundUi 테스트 |
| Codex #9 | stage2 재시작의 stale stage2 또는 수집본 없는 snapshot은 설정 우선. 새 수집 시작은 mode 없는 POST list. 이전 gate/report/추가 수집/전처리 액션을 최종 결과로 표시하지 않음. stage0/1 재시작의 기존 수집본은 추가된 키워드만 수집 경로 유지 | crawlNeedsSetup 테스트(기존 수집본, stage2 stale, collection 없음, stage1 재시작 회귀) |
| W2 | interrupted/paused 및 채널별 paused 상태 배너/칩. 이어서 진행은 본문 없음. 간격을 늘리고 재개는 멈춘 채널의 간격을 두 배(최소 1초)로 보내며 화면에 규칙 설명. stopReason/paused_reason/reason optional 수용. 문서 수 우선 표시 및 per-keyword URL 목록/완료 카운터 분리 | resume 본문 유무 wire 테스트, documentCount 0/legacy fallback 테스트 |
| R-63 | ds-eyebrow 사용, target_total의 null 유지, 로컬 달력 날짜 사용, md/환경변수 텍스트에 명시적 --ink(DS caption의 CSS 우선순위 고려), 과거 수집 날짜 ko-KR 표시, 버전 숫자 와/과 조사, 채팅 열기를 하단으로 이동 | localDate 테스트, 소스 검토, 타입/빌드 |

기존 지정 버튼 문구는 유지했다. stage2 재시작의 새 수집 시작만 요구에 따라 추가했다. dirty 확인 문구는 `저장되지 않은 변경이 있습니다. 이동할까요?`다.

## W1/W2 계약과 controller 메모

- W1은 mutation의 optional `?version=`을 검사하며 버전이 달라지면 409 `다른 버전이 활성화되었습니다`를 돌려준다고 가정한다. 신규 POST /context는 아직 표시 버전이 없으므로 버전 없음. 기존 표시 버전은 모든 단계 0–2 호출에 전달한다. versions 생성은 기존 `{from, restartFrom, note}` alias 계약 유지.
- W1의 복사된 committed R1–R3 재생성은 서버에서 승인/거절한다. UI는 done 상태에서 다시 생성 버튼을 제공하며 오류를 그대로 표시한다. 이전 서버가 거절해도 조용히 다른 mutation으로 재시도하지 않는다.
- **controller에게:** backend compare도 상태가 rejected로 바뀐 키워드를 removed로, distribution을 approved 기준으로 맞추는 것이 바람직하다. 이 작업은 소유권에 따라 backend diff를 수정하지 않고 이미 읽는 양쪽 snapshot을 사용해 화면에서 보정했다. 다른 compare API 소비자는 여전히 서버 diff 의미를 따른다.
- W2의 resume JSON은 `{min_interval_s:{source:seconds}}`이고 일반 resume는 body가 없다. 새 필드가 없어도 예전 channel.status와 full/snippet 카운터로 표시한다. W2의 report matrix full/snippet가 document counts이고 urls_listed/urls_done은 URL counts라는 계약을 따른다. docs/doc_count 명시 값이 있으면 0도 우선한다.
- paused_channels, reason 계열은 optional이다. 현재 W2 파일에서 확인한 `stopReason`도 지원한다. 불가능한 채널 사용 여부는 available_sources를 authoritative로 사용한다.
- stage2 재시작은 metadata.restartFrom을 함께 확인하여 stage0/1 변경 후 기존 수집본 추가 수집을 잘못 숨기지 않는다. collectionId가 없으면 metadata와 무관하게 새 설정을 연다.

## RED

구현 전 테스트를 작성하고 실행했다.

```text
npm --prefix frontend test -- src/lib/logic/finalFix.test.ts
FAIL: Cannot find module './finalFix'
Test Files 1 failed, Tests no tests, exit 1

npm --prefix frontend test -- src/lib/logic/mutationContract.test.ts
3 failed, exit 1
- expected null to be 'v2'
- "undefined" is not valid JSON (resume body)
- expected '사용 불가 채널', received '요청에 실패했습니다'

npm --prefix frontend test -- src/lib/logic/keywordDraft.test.ts
FAIL: Cannot find module './keywordDraft'
Test Files 1 failed, Tests no tests, exit 1

추가 회귀: stage1 재시작의 기존 수집본을 보존하는 assertion을 먼저 추가
finalFix.test.ts: 1 failed | 5 passed, expected true to be false, exit 1
이후 restartFrom 분기를 적용했다.
```

중간 검증에서 lint의 선언 순서 1건/미사용 인자 2건, webpack TypeScript의 snapshot keywords 타입 누락을 찾아 수정했다.

## GREEN

```text
npm --prefix frontend test
Test Files 20 passed (20)
Tests 68 passed (68)
exit 0

npm --prefix frontend run lint
eslint
exit 0, 0 problems

npm --prefix frontend run build
TurbopackInternalError: Failed to write app endpoint /page
creating new process / binding to a port
Operation not permitted (os error 1)
exit 1

npm --prefix frontend run build -- --webpack
Compiled successfully
Running TypeScript ...
Generating static pages (14/14)
exit 0

NEXT_PUBLIC_INTERNAL_TOOLS=false npm --prefix frontend run build -- --webpack
Compiled successfully
Running TypeScript ...
Generating static pages (14/14)
exit 0
```

## 우려/검증 한계

- 실제 브라우저 1024×768/1440 시각·키보드 QA, native confirm 상호작용, 실제 worker 왕복은 이번 환경에서 실행하지 않았다. 단위 테스트, 소스 연결 확인, lint, 타입 검사와 프로덕션 빌드로 검증했다.
- W1/W2 변경이 병렬로 진행 중이다. 통합 시 409 활성 버전 열기, copied committed 라운드 재생성, stage2 새 수집, paused resume를 실제 서버와 왕복 확인해야 한다.
- 새 필드가 없는 이전 보고서는 예전 카운터를 표시한다. 오래된 URL 카운터에서 실제 문서 수를 새로 추정하지 않는다.
- 기존 Node DEP0205 경고가 test/build에 남는다. Turbopack 자체 GREEN은 포트 바인딩 가능한 환경에서 확인해야 한다.

## Git

최종 scoped commit 시도 결과는 아래에 기록한다.

`git diff --check -- frontend docs/development/dcx2-stage0-2/reports/final-fix-W3.md`는 통과했다.

지정 범위 `git add`는 exit 128:

```text
fatal: Unable to create '/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock': Operation not permitted
```

요청한 제목과 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` trailer를 포함한 scoped `git commit --only`도 시도했다. add 실패로 신규 보고서가 index에 없어 exit 1:

```text
error: pathspec 'docs/development/dcx2-stage0-2/reports/final-fix-W3.md' did not match any file(s) known to git
```

결과는 **uncommitted**. 권한 우회 없이 변경을 남겼으며 backend 및 다른 작업의 파일을 staging/commit하지 않았다.
