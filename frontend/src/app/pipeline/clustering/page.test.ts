/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useState:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots))hooks.slots[i]=typeof initial==='function'?initial():initial;return [hooks.slots[i],(next:any)=>{hooks.slots[i]=typeof next==='function'?next(hooks.slots[i]):next;}];},
 useRef:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots))hooks.slots[i]={current:initial};return hooks.slots[i];},
 useCallback:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j]))hooks.slots[i]={deps,fn};return hooks.slots[i].fn;},
 useEffect:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j]))hooks.effects.push(()=>{old?.cleanup?.();hooks.slots[i]={deps,cleanup:fn()};});},
}));
const state=vi.hoisted(()=>({session:{sid:'s',sd:{prep:{derivedRef:{prepKey:'p'}}}} as any,poll:null as any,view:{readonly:false,version:'v1',refreshSessionAfterStage:vi.fn().mockResolvedValue(undefined)}}));
vi.mock('next/navigation',()=>({useRouter:()=>({push:vi.fn()})}));
vi.mock('@/stores/useSessionStore',()=>({useSessionStore:()=>state.session}));
vi.mock('@/components/versions/VersionProvider',()=>({useVersion:()=>state.view}));
vi.mock('@/components/versions/StageVersion',()=>({VersionStage:({children}:any)=>children,StageVersionAction:()=>null}));
vi.mock('@/lib/usePolling',()=>({usePolling:()=>({data:state.poll,refresh:vi.fn()})}));
vi.mock('@/lib/api/context',()=>({patchSession:vi.fn().mockResolvedValue({})}));
vi.mock('@/lib/api/segment',()=>Object.fromEntries(['startSegment','getSegmentStatus','getSegmentClusters','getSegmentPersonas','getSegmentContexts','confirmSegmentCluster','confirmSegmentPersona','confirmSegmentContext','confirmSegmentContexts','createSegmentRequest'].map(k=>[k,vi.fn()])));
import Page from './page';
import { SegmentScreen } from '@/components/segment/SegmentScreen';
import { ClusterLayer } from '@/components/segment/ClusterLayer';
import { PersonaLayer } from '@/components/segment/PersonaLayer';
import { ContextLayer } from '@/components/segment/ContextLayer';
import { LayerTabs } from '@/components/segment/LayerTabs';
import * as api from '@/lib/api/segment';
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];}
const textOf=(n:any):string=>typeof n==='string'||typeof n==='number'?String(n):Array.isArray(n)?n.map(textOf).join(' '):n?.props?textOf(n.props.children):'';
function render(fn:()=>any){hooks.cursor=0;const n=fn();hooks.effects.splice(0).forEach(f=>f());return n;}
const row={id:'CL0',docs:23,nameDraft:'초안',name:null,confirmed:false,keywords:[],reps:[],quality:{},channels:{},requests:[],flags:[]};
const persona={...row,id:'P1',clusterId:'CL0',authors:10,desireDraft:'바람',desire:null,goalsDraft:['목적'],goals:[],centrality:[],network:{nodes:[],edges:[]},similar:[{id:'P2',score:.86,desire:'비슷한 바람'}]};
const context={...row,id:'C1',personaId:'P1',actionDraft:'행동',action:null,dominantConstraint:null,dimsSummary:{},flags:['counter_context','granularity_exceeded']};
const status={run:'r1',status:'review',step:'drafts',progress:1,confirm:{clusters:'3/5',personas:'0/12',contexts:'0/31'}};
const base={disabled:false,edits:{},onEdit:vi.fn(),onConfirm:vi.fn()};
afterEach(()=>{hooks.slots=[];hooks.effects=[];state.poll=null;state.view.readonly=false;state.session.sd={prep:{derivedRef:{prepKey:'p'}}};vi.clearAllMocks();});
it('routes derived sessions to SegmentScreen and retains the legacy screen',()=>{expect(nodes(Page()).some(n=>n.type===SegmentScreen)).toBe(true);state.session.sd={};expect(nodes(Page()).some(n=>n.type===SegmentScreen)).toBe(false);});
it('shows one primary run action before results and disables evidence',()=>{state.poll={...status,status:'idle',run:null};const tree=render(()=>SegmentScreen({sid:'s'}));expect(nodes(tree).filter(n=>n.props?.variant==='primary')).toHaveLength(1);expect(textOf(tree)).toContain('클러스터링 실행');expect(nodes(tree).find(n=>n.props?.title==='다음 묶음에서 열립니다')?.props.disabled).toBe(true);});
it('shows live running steps without enabled run or rerun actions',()=>{state.poll={...status,status:'running',step:'L3',progress:.58};const tree=render(()=>SegmentScreen({sid:'s'}));expect(textOf(tree)).toContain('6단계 · 실행 중');expect(nodes(tree).some(n=>n.props?.['aria-live']==='polite')).toBe(true);expect(nodes(tree).filter(n=>['다시 나누기','클러스터링 실행'].includes(textOf(n))).every(n=>n.props.disabled)).toBe(true);});
it('locks Persona until every Cluster is confirmed and displays 4/5',()=>{const tree=LayerTabs({value:'6-A',onChange:vi.fn(),confirm:{...status.confirm,clusters:'4/5'}});expect(textOf(tree)).toContain('4/5 확정');expect(nodes(tree).filter(n=>n.type==='button')[1].props['aria-disabled']).toBe(true);});
it('keeps blank Desire unconfirmable and explains similar desires',()=>{const tree=PersonaLayer({...base,personas:[persona],selected:'P1',onSelect:vi.fn(),edits:{P1:{name:'이름',desire:'',goals:['목적']}}} as any);expect(nodes(tree).find(n=>n.props?.variant==='primary')?.props.disabled).toBe(true);expect(textOf(tree)).toContain('클러스터가 달라 합치지 않고 기록만 남깁니다.');});
it('shows Persona bulk confirmation, counter warning, and six Context warning',()=>{const tree=ContextLayer({...base,contexts:Array.from({length:6},(_,i)=>({...context,id:`C${i}`})),onBulk:vi.fn(),emptyRatio:.18} as any);expect(textOf(tree)).toContain('이 Persona의 Context 모두 확정');expect(textOf(tree)).toContain('반례 6개 포함');expect(textOf(tree)).toContain('Context가 6개입니다(권장 2~4)');});
it('has only one primary Cluster confirmation and preserves supplied edits',()=>{const tree=ClusterLayer({...base,clusters:[row,{...row,id:'CL1'}],edits:{CL0:{name:'수정 이름'}},onRequest:vi.fn()} as any);expect(nodes(tree).filter(n=>n.props?.variant==='primary')).toHaveLength(1);expect(nodes(tree).some(n=>n.props?.value==='수정 이름')).toBe(true);});
it('keeps evidence disabled after completion with bundle tooltip',()=>{state.poll={...status,status:'done',confirm:{clusters:'5/5',personas:'12/12',contexts:'31/31'}};const tree=render(()=>SegmentScreen({sid:'s'}));const button=nodes(tree).find(n=>n.props?.title==='다음 묶음에서 열립니다');expect(button?.props.disabled).toBe(true);expect(button?.props.title).toBe('다음 묶음에서 열립니다');});

const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
const screen=()=>render(()=>SegmentScreen({sid:'s',version:'v1'}));
beforeEach(()=>{
 vi.mocked(api.getSegmentClusters).mockResolvedValue({run:'r1',clusters:[row] as any,kSuggest:null});
 vi.mocked(api.getSegmentPersonas).mockResolvedValue({run:'r1',personas:[persona] as any});
 vi.mocked(api.getSegmentContexts).mockResolvedValue({run:'r1',contexts:[context] as any,emptyGoalConstraintRatio:.18});
 vi.mocked(api.getSegmentStatus).mockResolvedValue(status as any);
});
async function ready(s:any=status){state.poll=s;screen();await tick();screen();await tick();return screen();}
it('confirms a Cluster with the run and updates progress to 4/5',async()=>{
 let tree=await ready();vi.mocked(api.confirmSegmentCluster).mockResolvedValue({...row,confirmed:true} as any);
 vi.mocked(api.getSegmentStatus).mockResolvedValue({...status,confirm:{...status.confirm,clusters:'4/5'}} as any);
 nodes(tree).find(n=>n.type===ClusterLayer).props.onConfirm('CL0');await tick();tree=screen();await tick();tree=screen();
 expect(api.confirmSegmentCluster).toHaveBeenCalledWith('s','CL0',{run:'r1',name:'초안',confirm:true},'v1');expect(textOf(tree)).toContain('4/5');
});
it('asks before resetting k and sends confirmReset true',async()=>{
 let tree=await ready();nodes(tree).find(n=>n.props?.['aria-label']==='클러스터 수 k').props.onChange({target:{value:'7'}});tree=screen();nodes(tree).find(n=>n.props?.children==='다시 나누기').props.onClick();tree=screen();
 expect(textOf(tree)).toContain('이름 · Desire · Context 확정이 모두 지워집니다.');expect(api.startSegment).not.toHaveBeenCalled();
 vi.mocked(api.startSegment).mockResolvedValue({runId:'r2'});
 await nodes(tree).find(n=>n.props?.children==='확인하고 다시 나누기').props.onClick();await tick();expect(api.startSegment).toHaveBeenCalledWith('s',{k:7,confirmReset:true},'v1');
 expect(textOf(screen())).toContain('6단계 · 실행 중');
});
it('preserves typed input after save failure and offers refresh on stale_run',async()=>{
 let tree=await ready();nodes(tree).find(n=>n.type===ClusterLayer).props.onEdit('CL0',{name:'내 이름'});tree=screen();
 vi.mocked(api.confirmSegmentCluster).mockRejectedValue(new Error('다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.'));
 nodes(tree).find(n=>n.type===ClusterLayer).props.onConfirm('CL0');await tick();tree=screen();
 expect(nodes(tree).find(n=>n.type===ClusterLayer).props.edits.CL0.name).toBe('내 이름');expect(textOf(tree)).toContain('다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.');
 expect(nodes(tree).some(n=>n.props?.actions?.props?.children==='새로고침')).toBe(true);
});
it('bulk confirms only the selected Persona using edited values',async()=>{
 const complete={...status,confirm:{clusters:'5/5',personas:'12/12',contexts:'0/31'}};let tree=await ready(complete);
 nodes(tree).find(n=>n.type===LayerTabs).props.onChange('6-C');tree=screen();
 nodes(tree).find(n=>n.type===ContextLayer).props.onBulk();await tick();
 expect(api.confirmSegmentContexts).toHaveBeenCalledWith('s','P1',{run:'r1',contexts:[{id:'C1',name:'초안',action:'행동'}]},'v1');
});

import { patchSession } from '@/lib/api/context';
it('temporarily saves edits only in PATCH drafts.segment with the current run',async()=>{
 vi.useFakeTimers();const tree=await ready();nodes(tree).find(n=>n.type===ClusterLayer).props.onEdit('CL0',{name:'임시 이름'});
 await vi.advanceTimersByTimeAsync(600);expect(patchSession).toHaveBeenCalledWith('s',{drafts:{segment:{run:'r1',edits:{CL0:{name:'임시 이름'}}}}},'v1');vi.useRealTimers();
});
it('does not load or write an old draft from another run',async()=>{
 state.poll=status;const draw=()=>render(()=>SegmentScreen({sid:'s',draft:{run:'old',edits:{CL0:{name:'옛 이름'}}}}));draw();await tick();draw();await tick();const tree=draw();
 expect(nodes(tree).find(n=>n.type===ClusterLayer)?.props.edits).toEqual({});expect(patchSession).not.toHaveBeenCalled();
});
it('does not accept actions from readonly or running screens',async()=>{
 state.poll={...status,status:'running'};screen();await tick();const tree=screen();expect(nodes(tree).some(n=>n.type===ClusterLayer)).toBe(false);expect(api.startSegment).not.toHaveBeenCalled();
});
it('retains the legacy results and disables every legacy write action',()=>{
 state.session.sd={step:'cluster-check'};state.poll={status:'done',num_clusters:1,clusters:{'0':{size:7,keywords:['옛 키워드']}}};const legacy=nodes(Page()).find(n=>typeof n.type==='function')!;const tree=render(()=>legacy.type(legacy.props));
 expect(textOf(tree)).toContain('옛 키워드');expect(textOf(tree)).toContain('옛 세션 · 읽기 전용');expect(nodes(tree).find(n=>n.props?.children==='정제 → 페르소나').props.disabled).toBe(true);
});
it('retains edited input if cleaning the temporary draft fails after confirmation',async()=>{
 let tree=await ready();nodes(tree).find(n=>n.type===ClusterLayer).props.onEdit('CL0',{name:'저장할 이름'});tree=screen();
 vi.mocked(api.confirmSegmentCluster).mockResolvedValue({...row,name:'저장할 이름',confirmed:true} as any);
 vi.mocked(patchSession).mockRejectedValueOnce(new Error('임시 저장에 실패했습니다.'));
 nodes(tree).find(n=>n.type===ClusterLayer).props.onConfirm('CL0');await tick();tree=screen();
 expect(nodes(tree).find(n=>n.type===ClusterLayer).props.edits.CL0?.name).toBe('저장할 이름');
});

it('shows the mockup warnings for one community, insufficient documents, and failed drafts',()=>{
 const p=PersonaLayer({...base,personas:[{...persona,flags:['few_communities'],desireDraft:null}] as any,selected:'P1',onSelect:vi.fn()});
 const c=ContextLayer({...base,contexts:[{...context,flags:['few_docs'],actionDraft:null}] as any,emptyRatio:0,onBulk:vi.fn()});
 expect(textOf(p)).toContain('어휘 네트워크가 하나로 묶여 Persona를 나누지 않았습니다.');expect(textOf(c)).toContain('문서가 적어 Context를 나누지 않았습니다(');expect(textOf(c)).toContain('초안을 만들지 못했습니다. 직접 입력하세요.');
});
it('confirms Persona edits with nonempty Desire and 1–3 Goals',async()=>{
 let tree=await ready({...status,confirm:{...status.confirm,clusters:'5/5'}});nodes(tree).find(n=>n.type===LayerTabs).props.onChange('6-B');tree=screen();
 nodes(tree).find(n=>n.type===PersonaLayer).props.onEdit('P1',{desire:'수정한 바람',goals:['수정한 목적']});tree=screen();nodes(tree).find(n=>n.type===PersonaLayer).props.onConfirm('P1');await tick();
 expect(api.confirmSegmentPersona).toHaveBeenCalledWith('s','P1',{run:'r1',name:'초안',desire:'수정한 바람',goals:['수정한 목적'],confirm:true},'v1');
});
it('confirms individual Context edits with the current run',async()=>{
 let tree=await ready({...status,confirm:{clusters:'5/5',personas:'12/12',contexts:'0/31'}});nodes(tree).find(n=>n.type===LayerTabs).props.onChange('6-C');tree=screen();nodes(tree).find(n=>n.type===ContextLayer).props.onEdit('C1',{action:'수정한 행동'});tree=screen();nodes(tree).find(n=>n.type===ContextLayer).props.onConfirm('C1');await tick();
 expect(api.confirmSegmentContext).toHaveBeenCalledWith('s','C1',{run:'r1',name:'초안',action:'수정한 행동',confirm:true},'v1');
});
