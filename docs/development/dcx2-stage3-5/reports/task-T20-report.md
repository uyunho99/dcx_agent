# T20 구현 보고서

## 범위

- 요구사항: `.superpowers/sdd/03-plan/task-T20-brief.md`, `02-design-r2.md` 6.3 및 상태/문구 규칙, 목업 `index.html` s7, 계획 QA-K.
- 수정한 소유 파일: `frontend/src/app/pipeline/layout.tsx`, `frontend/src/components/ChatPanel.tsx`, `frontend/src/components/StepBar.tsx`, `frontend/src/components/SessionList.tsx`.
- T16 공유 API·KnownInsightsDrawer·SourceCard·types는 수정하지 않고 조합했다.
- 백엔드와 다른 작업 소유 페이지/컴포넌트는 읽기만 했다. 기존 및 병렬 작업 변경은 보존했다. 커밋하지 않았다.
- API 클라이언트 수정 없음: 기존 `sendChat`의 `Record<string, unknown>` 요청으로 `novel`을 전달할 수 있다. 응답 객체를 그대로 ChatPanel에 전달하므로 런타임의 `sources`와 `reason`도 보존된다.

## 구현

### 셸 / Known Insight

- 모든 파이프라인 화면의 사이드바에 `Known Insight · N` 버튼을 추가했다. 조회 중/실패는 `—`, 세션 없음은 `0`으로 표시한다.
- T16의 360px KnownInsightsDrawer를 사용한다. 빈 상태, 입력, 문장/원문·출처 배지, 삭제, 임베딩 경고, 모달 포커스/닫기는 공유 구현을 그대로 사용한다.
- 열린 드로어를 `null | known | integrations` 한 상태로 표현한다. 기존 InternalToolsProvider의 함수형 setter도 이 상태에 연결해 외부 API 진입 경로에서도 두 드로어가 동시에 열리지 않는다.
- 추가·삭제·닫기 후 목록 수를 갱신한다. 세션 변경 시 셸 상태를, 세션/버전 변경 시 채팅 상태를 분리한다.
- VersionProvider 안의 셸에서 선택 버전과 읽기 전용/로딩/오류 상태를 공유 카드·드로어에 전달한다. 현재 선택 버전으로 mutation을 보내고 과거 버전의 편집을 막는다.

### 채팅 / 근거 원문

- 기존 문자열 onSend 결과와 sources를 가진 구조화 결과를 모두 받는다.
- 질문 응답 아래 `근거 원문 N건`, `새 발견 찾기` 스위치, T16 SourceCard를 표시한다. 기본 필터는 켜짐이다. 문서 ID 없는 항목은 추가 가능한 원문 카드로 만들지 않는다.
- 필터 변경은 해당 질문을 다시 검색하며 `novel`을 전달한다. 입력부 스위치는 다음 질문의 필터를 지정한다.
- 카드에서 `Known Insight에 추가` 후 `다음 검색부터 비슷한 원문이 빠집니다`와 `추가한 이야기 빼고 다시 찾기`를 표시한다. 재검색은 `novel: true`로 실행한다.
- 공유 카드의 원문 링크, 등급, 유사도, 추가 오류/중복 방지를 재사용한다. 패널 삭제 후 카드의 로컬 추가 완료 상태도 새 키로 해제할 수 있게 했다.
- 검색 중 스켈레톤, 실패 후 재시도, 한글 조합 중 Enter 제출 방지, 중복 요청 잠금을 포함한다.
- `all_known`에는 지정 문구 `이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다.`를 그대로 표시한다. `no_vectors`, `no_labels`, `embedder_unconnected`는 각각 다른 안내를 표시한다.
- 디자인 시스템 Button/Switch/Skeleton과 토큰을 사용하고 셸 채팅에 파란 주요 버튼을 추가하지 않았다.

### 단계 / 세션 배지

- `prep-*`, `label-*`, `train-*`를 각각 전처리·라벨링·학습으로 매핑한다. 기존 이름은 유지했다.
- 채팅의 현재 단계 설명에도 같은 단계 해석을 사용해 기존 배열 인덱스 불일치를 없앴다.
- 작업 배지는 서버 label을 우선하고, 없으면 judge/prep/train/infer/monitor 등의 작업명을 표시한다. worker 진행률 0~1을 백분율로 바꾸며 기존 수집/키워드 문구와 중단/실패 문구는 유지한다.

## 검증

- 로직 선행 Vitest: 구현 전에 `/tmp/t20-tests/shell.test.ts` 작성 및 실행. 미구현 함수와 기존 잘못된 배지 문구로 **4 tests failed** 확인 후 구현하여 통과했다.
- 백엔드 worker가 `judge`와 0~1 진행률 및 label을 반환함을 확인한 뒤 추가 회귀 테스트를 먼저 실패시켰고 수정 후 통과했다.
- 최종 T20 전용 Vitest: **2 files / 6 tests passed**. 응답 변환, 빈 검색 사유, 단계 매핑, 작업 배지, QA-K 이벤트 흐름.
- `npm --prefix frontend test -- --run`: **32 files / 173 tests passed** (최종 전체 실행; 최초 실행은 31 files / 169 tests).
- `npm --prefix frontend run lint`: **통과**, 최종 변경 후 재실행도 통과.
- `npx --prefix frontend next build --webpack`: **통과**. Next.js 16.1.6, TypeScript 및 14개 정적 페이지 생성 완료.
  - 루트 cwd에서 이 명령을 실행하면 Next가 루트에서 app/pages를 찾아 실패한다. 동일 명령을 `frontend/` cwd에서 실행해 프로젝트 루트를 맞췄다.
  - 최초 재시도는 다른 병렬 작업의 `.next/lock` 때문에 실패했다. 다른 프로세스를 종료하거나 잠금을 삭제하지 않고 재시도하여 성공했다.
- `git diff --check`: 통과.
- 스크린샷은 사용자 지시에 따라 생략했다. 목업 s7의 구조·문구를 소스 기준으로 대조했다.

## QA-K 범위와 제한

- 모의 응답과 React hook harness로 질문 → 카드 → 추가 callback → 새 발견 재검색 → all_known 문구 → 스위치 끔 → 원문 복귀 및 `true/false` 요청 전달을 검증했다.
- 실제 서버 검색/임베딩 유사도와 브라우저 모달 포커스를 실행 검증한 것은 아니다. 모달·카드 동작은 T16 구현을 조합한다.
- `/insights/layout.tsx`는 소유 범위 밖이라 수정하지 않았다. 이 기존 호출부는 여전히 문자열 답변만 반환한다. 구조화 응답을 받는 공용 ChatPanel은 준비되어 있으나 이번 근거 원문 연결은 요청 범위인 파이프라인 셸에 적용했다.
- GET Known Insight와 채팅 검색은 기존 API 계약에 따라 활성 세션 데이터를 사용한다. 과거 버전 선택은 mutation을 읽기 전용으로 막는다. 읽기 API의 version 확장은 이 작업 범위 밖이다.

## 테스트 보존 / 재실행

소유 파일 제한 때문에 저장소에 테스트 파일/설정을 추가하지 않았다. 선행 테스트를 `/tmp/t20-tests`에서 실행했으며, 컨트롤러가 재현할 수 있도록 원문을 아래에 보존한다. 아래 세 코드 블록을 같은 이름으로 `/tmp/t20-tests/`에 저장한 뒤 저장소 루트에서 실행한다:

```sh
frontend/node_modules/.bin/vitest run --config /tmp/t20-tests/vitest.config.mjs
```

### vitest.config.mjs

```javascript
export default { esbuild: { jsx: 'automatic' }, resolve: { alias: { vitest: '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/node_modules/vitest/dist/index.js', '@': '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/src', react: '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/node_modules/react' } }, test: { environment: 'node', include: ['/tmp/t20-tests/*.test.ts'] } };

```

### shell.test.ts

```typescript
import { expect, it, vi } from 'vitest';
vi.mock('@/components/ds', () => ({}));
vi.mock('@/components/known/SourceCard', () => ({}));
vi.mock('@/components/DirtyProvider', () => ({}));
import { normalizeChatReply, sourceEmptyMessage } from '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/src/components/ChatPanel';
import { stepIndex } from '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/src/components/StepBar';
import { activityLabel } from '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/src/components/SessionList';
it('preserves legacy replies and only admits sources with document IDs', () => {
 expect(normalizeChatReply('hello')).toEqual({answer:'hello'});
 expect(normalizeChatReply({answer:'a',sources:[{doc_id:'d',text:'e'}, {},null],reason:'all_known'})).toEqual({answer:'a',sources:[{doc_id:'d',text:'e'}],reason:'all_known'});
 expect(() => normalizeChatReply({status:'error',answer:'secret'})).toThrow();
});
it('distinguishes all excluded from unavailable search', () => {
 expect(sourceEmptyMessage('all_known',true)).toBe("이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다.");
 expect(sourceEmptyMessage('all_known',false)).not.toContain('이미 아는');
 expect(sourceEmptyMessage('no_vectors',true)).toContain('전처리');
 expect(sourceEmptyMessage('no_labels',true)).toContain('라벨');
 expect(sourceEmptyMessage('embedder_unconnected',true)).toContain('연결');
});
it('recognizes every new stage prefix and preserves old steps', () => {
 for(const step of ['prep-setup','prep-running','prep-done']) expect(stepIndex(step)).toBe(3);
 for(const step of ['label-setup','label-queue','label-audit']) expect(stepIndex(step)).toBe(4);
 for(const step of ['train-setup','train-running','train-export']) expect(stepIndex(step)).toBe(5);
 expect(stepIndex('r3')).toBe(1);expect(stepIndex('unknown')).toBe(0);
});
it('names stage 3–5 activity without calling it collection', () => {
 expect(activityLabel({kind:'label',status:'running',progress:42})).toBe('판정 42%');
 expect(activityLabel({kind:'train',status:'running'})).toBe('학습 중');
 expect(activityLabel({kind:'prep',status:'running',progress:12})).toBe('전처리 12%');
 expect(activityLabel({kind:'classify',status:'running',progress:62})).toBe('분류 62%');
 expect(activityLabel({kind:'label',status:'interrupted'})).toBe('중단됨 · 이어서 진행');
});
it('uses fractional worker progress and server badge wording', () => {
 expect(activityLabel({kind:'judge',status:'running',progress:0.42})).toBe('판정 42%');
 expect(activityLabel({kind:'prep',status:'running',progress:0.12})).toBe('전처리 12%');
 expect(activityLabel({kind:'infer',status:'running',progress:0.62})).toBe('분류 62%');
 expect(activityLabel({kind:'train',status:'running',progress:0.5,label:'학습 중'})).toBe('학습 중');
});

```

### chat-flow.test.ts

```typescript
import { expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as unknown[], cursor: 0}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useEffect: () => {},
 useState: (initial: unknown) => {const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]=initial;return [hooks.slots[i],(next: unknown) => {hooks.slots[i]=typeof next === 'function' ? next(hooks.slots[i]) : next;}];},
 useRef: (initial: unknown) => {const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]={current:initial};return hooks.slots[i];},
}));
vi.mock('@/components/ds', () => ({Button:'Button',Switch:'Switch',Skeleton:'Skeleton'}));
vi.mock('@/components/known/SourceCard', () => ({SourceCard:'SourceCard'}));
import ChatPanel from '/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/frontend/src/components/ChatPanel';
function nodes(node: any): any[] {return !node || typeof node !== 'object' ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node,...nodes(node.props?.children)];}
it('QA-K: question, add, search excluding known, then switch off', async () => {
 hooks.slots=[];
 const onSend=vi.fn().mockResolvedValueOnce({answer:'a',sources:[{doc_id:'d',text:'원문'}]})
 .mockResolvedValueOnce({answer:'a',sources:[],reason:'all_known'})
 .mockResolvedValueOnce({answer:'a',sources:[{doc_id:'d',text:'원문'}]});
 const onKnownAdded=vi.fn();
 const render=()=>{hooks.cursor=0;return nodes(ChatPanel({initialMessage:'hello',sid:'s',version:'v1',onSend,onKnownAdded}));};
 const settle=async()=>{await Promise.resolve();await Promise.resolve();};
 let tree=render();tree.find(n=>n.type==='input').props.onChange({target:{value:'question'}});
 tree=render();tree.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await settle();
 expect(onSend).toHaveBeenLastCalledWith('question',true);
 tree=render();const card=tree.find(n=>n.type==='SourceCard');expect(card.props).toMatchObject({sid:'s',version:'v1',source:{doc_id:'d'}});
 card.props.onAdded({id:'k',type:'doc',doc_id:'d'});expect(onKnownAdded).toHaveBeenCalledOnce();
 tree=render();tree.find(n=>n.props?.children==='추가한 이야기 빼고 다시 찾기').props.onClick();await settle();
 expect(onSend).toHaveBeenLastCalledWith('question',true);
 tree=render();expect(tree.some(n=>n.props?.children==="이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다.")).toBe(true);
 tree.find(n=>n.type==='Switch').props.onChange(false);await settle();
 expect(onSend).toHaveBeenLastCalledWith('question',false);
 tree=render();expect(tree.filter(n=>n.type==='SourceCard')).toHaveLength(1);
});

```

