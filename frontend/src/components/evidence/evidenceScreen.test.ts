import { createElement, isValidElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
import { EvidenceScreenView, evidenceActions } from './EvidenceScreen';
import { EvidenceCard } from './EvidenceCard';
import { completedThrough } from '@/lib/logic/completedThrough';
import StepBar from '../StepBar';
import EvidencePage from '@/app/pipeline/evidence/page';
import { stage7Fixture, evidenceItemFixture, evidenceContextFixture } from './evidenceFixtures';
import type { EvidenceContextResponse, EvidenceStatus, EvidenceItemView } from '@/lib/types';
vi.mock('next/navigation', () => ({useRouter: () => ({push:vi.fn()}), usePathname: () => '/pipeline/evidence'}));
vi.mock('../DirtyProvider', () => ({useDirty: () => ({confirmNavigation: () => true})}));
const session = vi.hoisted(() => ({sid:'s',sd:{prep:{}} as Record<string, unknown>}));
vi.mock('@/stores/useSessionStore', () => ({useSessionStore: () => session}));
vi.mock('../versions/VersionProvider', () => ({useVersion: () => ({readonly:false,version:'v2'})}));
const row = (id: string, status: EvidenceStatus['contexts'][number]['status']) => ({id,personaId:'P',name:id,status,coverage:5,counts:{all:10,new:8},error:null,knownChanged:false});
const status: EvidenceStatus = {status:'running',run:'generation',progress:40,tagCalls:84,contexts:[row('C1','done'),row('C2','queued'),row('C3','failed')]};
const detail: EvidenceContextResponse = {...evidenceContextFixture,items:[]};
const props = () => ({status,personas:[{id:'P',clusterId:'CL0',name:'부모',flags:[]}],selectedPersona:'P',selectedContext:'C1',tab:'new' as const,detail,personaEvidence:null,ready:true,readonly:false,busy:false,error:'',onPersona:vi.fn(),onContext:vi.fn(),onTab:vi.fn(),onStart:vi.fn(),onRetry:vi.fn(),onSkip:vi.fn(),onRefresh:vi.fn(),onAdded:vi.fn(),onNext:vi.fn(),sid:'s',version:'v2'});
// Resolve stateless view components so handlers can be exercised without a DOM dependency.
function nodes(node: unknown): ReactElement<Record<string, unknown>>[] {
 if (Array.isArray(node)) return node.flatMap(nodes);
 if (!isValidElement(node)) return [];
 const el = node as ReactElement<Record<string, unknown>>;
 if (typeof el.type === 'function' && !['EvidenceCard','Tabs'].includes(el.type.name)) return nodes((el.type as (p: unknown) => unknown)(el.props));
 return [el,...nodes(el.props.children)];
}
function button(tree: unknown, label: string) {return nodes(tree).find(n => n.type === 'button' && renderToStaticMarkup(n).includes(label))!;}
it('defaults Context evidence to new and changes tabs', () => {
 const p = props(); const tabs = nodes(EvidenceScreenView(p)).find(n => typeof n.type === 'function' && n.type.name === 'Tabs')!;
 expect(tabs.props.value).toBe('new'); (tabs.props.onChange as (s:string)=>void)('all'); expect(p.onTab).toHaveBeenCalledWith('all');
});
it('opens done rows during a run, locks pending rows and persona creation', () => {
 const p = props(); const tree = EvidenceScreenView(p);
 expect(button(tree,'C1').props.disabled).toBe(false);
 (button(tree,'C1').props.onClick as ()=>void)(); expect(p.onContext).toHaveBeenCalledWith('C1');
 expect(button(tree,'C2').props.disabled).toBe(true);
 expect(button(tree,'페르소나 만들기').props.disabled).toBe(true);
 const html = renderToStaticMarkup(createElement(EvidenceScreenView,p));
 for(const copy of ['완료','대기','실패','Context 1/3 · 태깅 호출 84회','CL0','Coverage 5/6']) expect(html).toContain(copy);
});
it('shows refresh on completed rows after Known Insight changes', () => {
 const p = props(); p.status = {...status,contexts:status.contexts.map(c=>({...c,knownChanged:c.status==='done'}))};
 const tree = EvidenceScreenView(p); (button(tree,'새 발견 다시 계산').props.onClick as ()=>void)(); expect(p.onRefresh).toHaveBeenCalledWith('C1');
 expect(renderToStaticMarkup(createElement(EvidenceScreenView,p))).toContain('Known Insight가 바뀌었습니다');
});
it('sends doc Known Insight and generation/version guarded refresh and failed actions', async () => {
 const api = {addKnownInsight:vi.fn().mockResolvedValue({}), refreshEvidenceNew:vi.fn().mockResolvedValue(detail), startEvidence:vi.fn(),skipEvidenceContext:vi.fn()};
 const actions = evidenceActions('s','v2','generation',api);
 await actions.add('doc'); expect(api.addKnownInsight).toHaveBeenCalledWith('s',{type:'doc',doc_id:'doc'},'v2');
 await actions.refresh('C1'); expect(api.refreshEvidenceNew).toHaveBeenCalledWith('s','C1',{run:'generation'},'v2');
 await actions.retry('C3'); expect(api.startEvidence).toHaveBeenCalledWith('s',{contexts:['C3']},'v2');
 await actions.skip('C3'); expect(api.skipEvidenceContext).toHaveBeenCalledWith('s','C3',{run:'generation'},'v2');
 const p = props(); const tree = EvidenceScreenView(p);
 (button(tree,'다시 시도').props.onClick as ()=>void)(); expect(p.onRetry).toHaveBeenCalledWith('C3');
 (button(tree,'건너뛰고 진행').props.onClick as ()=>void)(); expect(p.onSkip).toHaveBeenCalledWith('C3');
 expect(renderToStaticMarkup(createElement(EvidenceScreenView,p))).toContain('이 Context의 근거를 찾지 못했습니다:');
});
it('renders the three exact empty states and stale copy', () => {
 const p = props();
 expect(renderToStaticMarkup(createElement(EvidenceScreenView,p))).toContain('Known Insight를 빼니 남는 원문이 없습니다. 전체 탭에서 보세요.');
 expect(renderToStaticMarkup(createElement(EvidenceScreenView,{...p,tab:'all',detail:{...detail,tab:'all'}}))).toContain('이 Context에서 근거로 쓸 원문을 찾지 못했습니다.');
 const html = renderToStaticMarkup(createElement(EvidenceScreenView,{...p,ready:false,status:{...status,status:'none',contexts:[]}}));
 expect(html).toContain('6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요.');
 expect(button(EvidenceScreenView({...p,ready:false,status:{...status,status:'none',contexts:[]}}),'근거 탐색 실행').props.disabled).toBe(true);
 expect(renderToStaticMarkup(createElement(EvidenceScreenView,{...p,status:{...status,status:'stale'}}))).toContain('6단계가 다시 나뉘어 이 근거는 이전 결과 기준입니다. 다시 실행하세요.');
});
it('uses a shrinkable 1024px layout and one primary, locks writes in history', () => {
 const p = props(); const html = renderToStaticMarkup(createElement(EvidenceScreenView,p));
 expect(html).toContain('min-w-0'); expect(html).toContain('lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]'); expect(html).not.toContain('min-w-[1024px]'); expect(html.match(/ds-primary/g)).toHaveLength(1);
 const tree = EvidenceScreenView({...p,readonly:true}); expect(button(tree,'다시 시도').props.disabled).toBe(true); expect(button(tree,'건너뛰고 진행').props.disabled).toBe(true); expect(button(tree,'C1').props.disabled).toBe(false);
});
it('unlocks navigation only after done or skipped and navigates via callback', () => {
 const p = props(); p.status={...status,status:'done',contexts:[row('C1','done'),row('C3','skipped')]};
 const next=button(EvidenceScreenView(p),'페르소나 만들기'); expect(next.props.disabled).toBe(false); (next.props.onClick as ()=>void)(); expect(p.onNext).toHaveBeenCalledOnce();
});
it('renders Unicode quote, source, location and known match', () => {
 const item: EvidenceItemView={...evidenceItemFixture};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn(),knownNumber:2}));
 for(const text of ['<mark>인용</mark>','댓글 3','새로움 높음 · 잠정','Feel','Known Insight와 같은 내용 #2','Known Insight에 추가']) expect(html).toContain(text);
});
it('adds sidebar evidence path and completion 7 while retaining legacy branch', () => {
 expect(completedThrough({completion:{evidenceDone:true,segmentDone:true}})).toBe(7);
 expect(completedThrough({completion:{evidenceDone:false,segmentDone:true}})).toBe(6);
 const html=renderToStaticMarkup(createElement(StepBar,{currentStep:'evidence',session:{prep:{derivedRef:'x'}}})); expect(html).toContain('href="/pipeline/evidence"');
 const legacy=renderToStaticMarkup(createElement(StepBar,{currentStep:'persona',session:{prep:{}}})); expect(legacy).not.toContain('href="/pipeline/evidence"');
 expect(renderToStaticMarkup(createElement(EvidencePage))).toContain('옛 세션');
 session.sd={prep:{derivedRef:'x'}}; expect(EvidencePage().type).not.toBe('div'); session.sd={prep:{}};
});

it('provides recovery for a failed run even without failed Context rows', () => {
 const p=props();const tree=EvidenceScreenView({...p,status:{...status,status:'failed',contexts:[]}});
 const resume=button(tree,'이어서 진행');expect(resume).toBeDefined();expect(resume.props.disabled).toBe(false);
 (resume.props.onClick as ()=>void)();expect(p.onStart).toHaveBeenCalledOnce();
});
it('shows eight queries, fallback copy and collapsed supporting evidence', () => {
 const p=props();const html=renderToStaticMarkup(createElement(EvidenceScreenView,{...p,detail:{...detail,queryFailed:true,queries:['Sense','Feel','Think','Act','Relate','Outcome','Counter','Residual'].map(dim=>({dim,text:dim+' 문장',origin:'fallback' as const}))}}));
 expect(html).toContain('쿼리 보기 · 8문장');expect(html).toContain('자동 쿼리 생성에 실패해 Context 이름과 키워드로 검색했습니다.');
 expect(html).toContain('반례 0 · 희소 0');expect(html).not.toContain('<details open');
});

it('renders Context completion progress without assuming API percentage units', () => {
 const html=renderToStaticMarkup(createElement(EvidenceScreenView,{...props(),status:{...status,progress:1/3}}));
 expect(html).toContain('aria-valuemax="3"');expect(html).toContain('aria-valuenow="1"');
});

 it.each(['title','body','comment'] as const)('highlights only quoteSource for %s', field => {
 const item={...evidenceItemFixture,quoteSource:{field,idx:field==='comment'?2:null,text:'😀 인용 끝'}};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn()}));
 expect(html).toContain('<mark>인용</mark>');
 if(field === 'body') expect(html).not.toContain('별개의 본문 미리보기');
 else expect(html).toContain('<p class="whitespace-pre-wrap">별개의 본문 미리보기</p>');
 expect(html).toContain(field==='title'?'제목':field==='body'?'본문':'댓글 3');
 });
 it.each(['none','low','high','very_high'])('obeys noveltyShown rather than novelty value %s', novelty => {
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item:{...evidenceItemFixture,novelty,noveltyShown:false},readonly:false,onAdd:vi.fn()}));
 expect(html).not.toContain('새로움 ');
 });
 it('replaces stale detail skeleton and suppresses stale warning without a previous run',()=>{
 const html=renderToStaticMarkup(createElement(EvidenceScreenView,{...props(),status:{...status,status:'stale'},detail:null}));
 expect(html).toContain('다시 실행 후 열람할 수 있습니다.');expect(html).not.toContain('근거 불러오는 중');
 const empty=renderToStaticMarkup(createElement(EvidenceScreenView,{...props(),status:{...status,status:'stale',run:null,contexts:[]},detail:null}));
 expect(empty).not.toContain('이 근거는 이전 결과');
 });
 it('shows artifact mention counts and partial recovery guidance',()=>{
 const html=renderToStaticMarkup(createElement(EvidenceScreenView,{...props(),status:{...status,status:'partial'},personaEvidence:{desireSupport:[],artifacts:[{name:'리모컨',mention_count:12}]}}));
 expect(html).toContain('리모컨 · 12건');expect(html).toContain('실패한 Context를 다시 시도하거나 건너뛰고 진행하세요.');
 });

it('highlights an original body quote beyond the 600-character preview',()=>{
 const item={...evidenceItemFixture,quoteSource:{field:'body' as const,idx:null,text:'가'.repeat(610)+'인용'},quote:{text:'인용',start:610,end:612,verified:true},text:'가'.repeat(600)};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn()}));
 expect(html).toContain('<mark>인용</mark>');
});
it('keeps unverified quotes visible without highlighting any source text',()=>{
 const item={...evidenceItemFixture,quote:{...evidenceItemFixture.quote!,verified:false}};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn()}));
 expect(html).not.toContain('<mark>');expect(html).toContain('<blockquote>인용</blockquote>');expect(html).toContain('인용 미확인 · 추론');
});

it('renders live status tagCalls before a stage7 report exists and ignores stale reports', () => {
 for (const stage7 of [undefined, {...stage7Fixture,tag_calls:999}]) {
  const wire: EvidenceStatus = {status:'running',run:'generation',progress:1/3,
   contexts:status.contexts,tagCalls:17,stage7};
  const html=renderToStaticMarkup(createElement(EvidenceScreenView,{...props(),status:wire}));
  expect(html).toContain('Context 1/3 · 태깅 호출 17회');
 }
});

it.each([null,{text:'고유본문',start:0,end:4,verified:true}])('renders body only once with or without a quote',quote=>{
 const item={...evidenceItemFixture,text:'고유본문',quoteSource:{field:'body' as const,idx:null,text:'고유본문'},quote};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn()}));
 expect(html.split('고유본문').length-1).toBe(1);
});
it('offers resume after a prompt upgrade on a completed screen',()=>{
 const p={...props(),status:{...status,status:'done' as const},error:'근거 프롬프트가 바뀌었습니다. 이어서 진행을 눌러 다시 계산하세요.'};
 const resume=button(EvidenceScreenView(p),'이어서 진행');
 expect(resume).toBeDefined();(resume.props.onClick as ()=>void)();expect(p.onStart).toHaveBeenCalledOnce();
});

 it.each([['very_high','매우 높음'],['high','높음'],['medium','보통'],['low','낮음'],['none','없음']])('localizes novelty %s when shown', (novelty,label) => {
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item:{...evidenceItemFixture,novelty,noveltyShown:true},readonly:false,onAdd:vi.fn()}));
 expect(html).toContain(`새로움 ${label} · 잠정`);
 });
 it('renders only the dimensions present in the lowercase API tags', () => {
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item:{...evidenceItemFixture,tags:['sense','think','outcome']},readonly:false,onAdd:vi.fn()}));
 for(const label of ['Sense','Think','Outcome']) expect(html).toContain(`>${label}<`);
 for(const label of ['sense','think','outcome','Feel','Act','Relate']) expect(html).not.toContain(`>${label}<`);
 });
 it.each([null,2])('badges handed documents on all with KI display number %s', number => {
 const item={...evidenceItemFixture,knownMatch:'none',known:{handed:true,kiId:'ki_second'}};
 const knownNumbers: Record<string, number> = number ? {ki_second:number} : {};
 const p={...props(),tab:'all' as const,detail:{...detail,tab:'all' as const,items:[item]},knownNumbers};
 const html=renderToStaticMarkup(createElement(EvidenceScreenView,p));
 expect(html).toContain('Known Insight와 같은 내용'+(number?' #2':''));
 expect(html).toContain('Known Insight에 추가됨');
 });
it('renders all six design dimension names from API keys',()=>{
 const item={...evidenceItemFixture,tags:['sense','feel','think','act','relate','outcome']};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn()}));
 for(const label of ['Sense','Feel','Think','Act','Relate','Outcome']) expect(html).toContain(`>${label}<`);
});
it('does not badge an unhanded document with no known match',()=>{
 const item={...evidenceItemFixture,knownMatch:'none',known:{handed:false,kiId:null}};
 const html=renderToStaticMarkup(createElement(EvidenceCard,{item,readonly:false,onAdd:vi.fn()}));
 expect(html).not.toContain('Known Insight와 같은 내용');
});
