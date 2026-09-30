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

## Follow-up FX-F

요청 범위의 frontend와 이 절만 수정했다. 기존 `.DS_Store` 및 병렬 backend/다른 보고서 변경은 건드리지 않았다. 하위 에이전트와 추가 질문 없이 진행했다. 아래 내용은 위 W3의 수집본 부재/오류 원문 보존/확정 라운드 재생성 관련 설명을 대체한다.

- I1: `restartFrom === stage2` 또는 `stale.stage2`일 때만 fresh setup/`새 수집 시작`. 최초 수집은 일반 설정과 `목록 수집 시작`을 유지한다.
- M1: `lib/api/errors.ts`에서 지정한 8개 `error.code`를 한국어 상황+다음 행동으로 매핑한다. 미지정/알 수 없는 코드는 기존 한국어 fallback을 쓰고 원문 message/detail은 노출하지 않는다. context 저장/조회/제안, keyword, crawl 화면에 연결했다. 네트워크 예외도 한국어 fallback으로 처리한다. 409 version conflict 이벤트는 유지한다.
- M2: done+미확정 또는 `needsRegeneration`인 라운드만 다시 생성 버튼을 표시한다(진행 중/dirty는 실행 불가). 과거 라운드에서 다음 라운드가 이미 있으면 **생성 대상인 다음 라운드**에 같은 조건을 적용하고 regenerate 요청을 보낸다. 다음 라운드가 없으면 기존 생성 흐름을 유지한다.
- M3 / R-66: 멈춘 채널만, 없으면 `collection_channels`만 전송한다. `min_interval_s`의 현재 유효값을 우선해 두 배로 늘리고, 없으면 설정값으로 계산한다(최소 1초). 두 status 필드가 없고 멈춘 채널도 없으면 빈 interval map을 보내 UI 채널을 추정하지 않는다. 설정 config는 변경하지 않는다.
- M4: 버전 id/읽기 전용·활성 상태 및 외부 API `n/6 연결`을 accessible name과 title에 포함했다. 새 활성 버전 안내에서 축소 화면용 숨김 클래스를 제거하여 1100px 미만에서도 안내와 열기 버튼을 유지한다.
- M7 / R-46: commit/지시 저장의 방향 이벤트는 다음 생성 라운드(최대 R4)에 기록한다. 실제 생성/재생성에서는 대상 라운드를 명시한다. helper로 R1→R2, R2→R3, R3→R4, R4→R4를 검증했다.

테스트를 먼저 작성한 RED:

```text
npm --prefix frontend test -- src/lib/logic/finalFix.test.ts src/lib/logic/roundUi.test.ts src/lib/api/errors.test.ts src/lib/logic/mutationContract.test.ts
Test Files 4 failed (4)
Tests 16 failed | 12 passed (28), exit 1
```

최종 단위 테스트/정적 검사:

```text
npm --prefix frontend test
Test Files 21 passed (21), Tests 81 passed (81), exit 0
npm --prefix frontend run lint
exit 0, 0 problems
```

실제 브라우저 시각/키보드 QA 및 병렬 backend와의 worker 왕복은 수행하지 않았다. 접근성은 JSX와 반응형 CSS 경로를 검토했다. 기존 Node DEP0205 경고가 남는다.

빌드 결과:

```text
npm --prefix frontend run build
Turbopack: binding to a port / Operation not permitted (os error 1), exit 1
npm --prefix frontend run build -- --webpack
Compiled successfully; TypeScript 통과; static pages 14/14, exit 0
```

`git diff --check -- frontend docs/development/dcx2-stage0-2/reports/final-fix-W3.md` 통과. 요청한 제목/trailer로 범위를 제한한 commit을 시도한다.

scoped `git add` 및 지정 제목/`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`를 넣은 `git commit --only` 모두 exit 128: worktree의 `index.lock` 생성이 `Operation not permitted`로 거부되었다. 결과는 **uncommitted**이며 변경을 그대로 남겼다.

## Follow-up FX-F2

R-67에 따라 이 절과 지정된 frontend 파일 5개만 수정했다. 위 FX-F의 I1/M1 설명은 아래 내용으로 대체한다. dev server를 실행하거나 하위 에이전트를 사용하지 않았으며 기존 `.DS_Store` 변경은 건드리지 않았다.

- fresh setup은 `restartFrom === 'stage2' && !!stale.stage2`일 때만 켜진다. stage0/1 재시작은 stage2 stale 여부와 무관하게 추가 키워드 수집 경로를 유지한다. stage2의 `start_list` 확인 후 backend가 stale을 지우면 reload 후에도 fresh setup이 꺼진다. 최초 수집은 일반 설정과 `목록 수집 시작`, fresh setup만 `새 수집 시작`을 쓴다.
- 오류는 등록된 code의 한국어 매핑을 우선하고, 그 외에는 Hangul이 포함된 backend `error.message`를 그대로 보존한다. 영어/메시지 부재는 일반 한국어 fallback을 쓴다. 화면에서 다시 소실되지 않도록 `displayError`도 한국어 메시지를 보존한다.
- `storage_error`는 설계 8.1의 디스크 쓰기 실패 문구를 사용한다. `no_collection`, `snapshot_conflict`, `no_unfinished_phase`, `gate_not_editable`의 한국어 안내도 추가했다. crawling 화면의 영어 storage/disk 정규식 분기를 제거했다. 409 `dcx-version-conflict` 이벤트는 코드 및 코드 없는 한국어 메시지 양쪽에서 유지한다.

테스트를 먼저 작성하고 기존 구현에서 RED를 확인했다:

```text
npm --prefix frontend test -- src/lib/logic/finalFix.test.ts src/lib/api/errors.test.ts
Test Files 2 failed; Tests 11 failed | 19 passed (30), exit 1
```

구현 후 검증:

```text
npm --prefix frontend test
Test Files 21 passed; Tests 94 passed (94), exit 0
npm --prefix frontend run lint
exit 0, 0 problems
```

```text
npm --prefix frontend run build
Turbopack: binding to a port / Operation not permitted (os error 1), exit 1
npm --prefix frontend run build -- --webpack
Compiled successfully; TypeScript 통과; static pages 14/14, exit 0
```

기존 Node DEP0205 경고가 남는다. 브라우저 QA 세션에 접근하지 않았으며 실제 backend worker 왕복은 별도 QA 대상이다. 지정 파일만 staging하고 요청한 제목 및 co-author trailer로 commit을 시도한다.

`git diff --check`는 통과했다. scoped `git add`와 지정 제목/trailer의 `git commit --only`는 모두 exit 128: `/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock` 생성이 `Operation not permitted`로 거부되었다. 결과는 **uncommitted**이며 권한 우회 없이 변경을 남겼다.

## QA fix QF-1

- Q3 원인: QA status 응답에는 `snapshot_id`가 없고 session에는 `drafts.crawl`이 없다. 기존 `draft?.gate?.snapshot_id === initial.snapshot_id`가 `undefined === undefined`로 참이 되어 `draft.gate.exclusions`에서 TypeError가 발생했다. `setSession` 이전에 실패하여 승인 키워드도 0개로 보였다. `{status, data}` unwrap과 최상위 `data.keywords` 위치는 정상이었다. 제공 파일의 crawlConfig는 누락되어 있으며 명시적인 null도 별도 검증했다.
- Q3 수정: 설정 파생을 순수 함수 `deriveCrawlLoad`로 추출하고 실제 gate와 snapshot이 있는 경우에만 초안을 복원한다. 조회한 버전의 projectContext 채널과 available_sources 교집합을 우선하고, 저장 설정 부재 시 status 필터 기본값을 적용한다. 화면과 테스트는 승인 키워드 helper를 공유한다. 성공한 재조회는 오류 표시를 지운다. 내부 도구 비활성 시 fixture 채널 제외 정책은 유지한다.
- 회귀 fixture: `.superpowers/sdd/03-plan/qa-repro/`의 네 JSON을 읽기만 하고 frontend의 `lib/logic/__fixtures__/`에 복사했다. session 최상위 키워드는 실제 첫 20개(승인 19개), 각 round는 첫 5개로 줄였다. 네 API 응답을 mock fetch로 그대로 공급하여 version/session unwrap, integrations, 승인 수, 기본 채널·필터·날짜 및 오류 없는 파생을 검증한다. 추가로 null 설정/누락 store context/null snapshot, 일치·불일치 gate snapshot, 저장된 빈 필터와 null 목표를 검증한다.
- Q1: layout의 restoring 초기값을 서버와 최초 클라이언트 렌더 모두 true로 통일했다. mount effect에서 기존 sid/저장된 sid 유무에 따라 로딩 종료 또는 복원을 수행한다.
- Q4: `josa(word, pair)`를 추가했다. 한글 종성, 숫자의 한국어 발음, 영문자 이름의 종성(L/M/N/R), 알 수 없는 끝글자의 기본 모음형을 처리한다. 네 조사 쌍과 인용부호를 포함해 22개 테스트로 검증했다. 시작 질문 템플릿, 라운드 저장, 중복 키워드, 커버리지, 버전 비교/새 활성 버전 안내에 적용했다. 해당 화면과 컴포넌트의 변수 직후 조사 패턴을 검색해 확인했다.
- Q5: R2 확정 후 R3/R4 기록이 아직 없을 때만 R3 생성 전 미연결/빈 검색어 안내를 표시한다. 기존 커버리지 결과 패널은 유지한다.

RED (수정 전 로직을 순수 함수로 옮긴 뒤 실행):

```text
npm --prefix frontend test
Test Files 1 failed | 21 passed; Tests 1 failed | 94 passed
TypeError: Cannot read properties of undefined (reading 'gate')
  deriveCrawlLoad — crawlLoad.test.ts
exit 1
```

GREEN:

```text
npm --prefix frontend test
Test Files 23 passed; Tests 119 passed; exit 0
npm --prefix frontend run lint
exit 0, 0 problems
```

dev server와 build는 실행하지 않았다. 실제 브라우저 재검증은 수행하지 않았으며 기존 Node DEP0205 경고가 남는다. frontend 및 이 보고서 외의 파일과 `.superpowers`는 수정하지 않았다. 기존 `.DS_Store` 변경은 staging 대상에서 제외했다.

지정 범위 `git add`와 요청한 정확한 제목/co-author trailer의 `git commit --only`를 시도했으나 모두 exit 128로 실패했다. worktree의 `/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock` 생성이 `Operation not permitted`로 거부되었다. 권한 우회 없이 **uncommitted** 상태로 남겼다.

## QA fix QF-2

- Q9: 게이트 선택·저장 기준·임시 저장 기준을 status의 collectionId와 snapshot_id에 묶었다. 둘 중 하나가 바뀌면 현재 버전의 session을 다시 읽고 crawlConfig.gateExclusions와 현재 gate 행의 교집합으로 초기화한다. 동일 범위의 로컬 선택은 유지하되 행에서 사라진 키워드는 제거한다. 새 초안에는 collectionId도 저장하며, 초안 복원은 두 ID가 모두 일치할 때만 허용한다. collectionId 없는 기존 초안은 서버 저장값으로 대체한다. 순수 함수 reconcileGateSelection을 초기 로드와 status 갱신에 공유한다.
- Q8: StaleBanner는 현재 페이지 단계의 stale 여부만 확인하고 해당 단계 번호를 표시한다. restart 원인 단계는 원본 버전 추적에만 사용한다. crawling은 stage2, keywords는 stage1, start는 stage0이며 자기 단계가 stale이 아니면 배너를 숨긴다.
- Q10: 갱신·백그라운드 수집 안내는 running/stopping 동안만 표시한다. 분당 처리량은 천 단위 구분과 소수 최대 한 자리로 표시한다. P3/P5의 채널 시도·오류 수, URL·문서 합계, 키워드별 표·상하위 막대, 남은 시간에도 숫자 포맷을 적용하고 tabular numerals를 사용한다.
- 테스트 먼저 작성: qaFix.test.ts의 helper 미구현으로 RED를 확인했다. 초기 로드의 기존 테스트에도 collectionId와 현재 행 밖 초안을 추가하여 unknown 키워드가 남는 실패를 확인한 뒤 수정했다. 범위 변경, 동일 범위 유지, 초안 범위 불일치·행 교집합, 단계 선택, 숫자 포맷, 실행 상태를 검증한다.

검증 결과:

```text
npm --prefix frontend test
Test Files 24 passed; Tests 128 passed; exit 0
npm --prefix frontend run lint
exit 0, 0 problems
```

dev server 및 build는 실행하지 않았다. 실제 브라우저·worker 왕복 재검증은 수행하지 않았다. 기존 Node DEP0205 경고는 남는다. 지정 범위만 수정했으며 기존 .DS_Store 변경은 포함하지 않는다.

커밋 결과: 지정 파일의 git add는 worktree index.lock 생성 권한 오류(Operation not permitted)로 실패했다. scoped commit은 새 파일이 미등록 상태라 실패했고, 요청한 메시지·trailer의 git commit도 동일한 index.lock 권한 오류로 실패했다. 변경은 **uncommitted**로 남겼다. 작업 도중 나타난 별도 qa/ 미추적 디렉터리도 수정하거나 staging하지 않았다.
