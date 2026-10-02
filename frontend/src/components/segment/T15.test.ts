/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useState:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots))hooks.slots[i]=typeof initial==='function'?initial():initial;return [hooks.slots[i],(next:any)=>{hooks.slots[i]=typeof next==='function'?next(hooks.slots[i]):next;}];},
 useRef:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots))hooks.slots[i]={current:initial};return hooks.slots[i];},
 useCallback:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j]))hooks.slots[i]={deps,fn};return hooks.slots[i].fn;},
 useEffect:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j]))hooks.effects.push(()=>{old?.cleanup?.();hooks.slots[i]={deps,cleanup:fn()};});},
}));
const state=vi.hoisted(()=>({session:{sid:'s',sd:{prep:{derivedRef:{prepKey:'p'}}}} as any,poll:null as any,pollOptions:null as any,view:{readonly:false,version:'v1',refreshSessionAfterStage:vi.fn().mockResolvedValue(undefined)}}));
const dirty = vi.hoisted(() => ({register: vi.fn(), confirmNavigation: vi.fn(() => true)}));
vi.mock('@/components/DirtyProvider', () => ({useDirty: () => dirty}));
const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation',()=>({useRouter:()=>({push})}));
vi.mock('@/lib/api/evidence',()=>({getEvidenceContext:vi.fn(),startEvidence:vi.fn()}));
import {getEvidenceContext, startEvidence} from '@/lib/api/evidence';
vi.mock('@/stores/useSessionStore',()=>({useSessionStore:()=>state.session}));
vi.mock('@/components/versions/VersionProvider',()=>({useVersion:()=>state.view}));
vi.mock('@/components/versions/StageVersion',()=>({VersionStage:({children}:any)=>children,StageVersionAction:()=>null}));
vi.mock('@/lib/usePolling',()=>({usePolling:(options:any)=>{state.pollOptions=options;return {data:state.poll,refresh:vi.fn()};}}));
vi.mock('@/lib/api/context',()=>({patchSession:vi.fn().mockResolvedValue({})}));
vi.mock('@/lib/api/segment',()=>Object.fromEntries(['startSegment','getSegmentStatus','getSegmentClusters','getSegmentPersonas','getSegmentContexts','confirmSegmentCluster','confirmSegmentPersona','confirmSegmentContext','confirmSegmentContexts','createSegmentRequest'].map(k=>[k,vi.fn()])));
vi.mock('@/lib/api/versions',()=>({getVersionSession:vi.fn()}));
import { getVersionSession } from '@/lib/api/versions';
import { SegmentScreen } from '@/components/segment/SegmentScreen';
import { ContextLayer } from '@/components/segment/ContextLayer';
import * as api from '@/lib/api/segment';
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];}
const textOf=(n:any):string=>typeof n==='string'||typeof n==='number'?String(n):Array.isArray(n)?n.map(textOf).join(' '):n?.props?textOf(n.props.children):'';
function render(fn:()=>any){hooks.cursor=0;const n=fn();hooks.effects.splice(0).forEach(f=>f());return n;}
const row={id:'CL0',docs:23,nameDraft:'초안',name:null,confirmed:false,keywords:[],reps:[],quality:{},channels:{},requests:[],flags:[]};
const persona={...row,id:'P1',clusterId:'CL0',authors:10,desireDraft:'바람',desire:null,goalsDraft:['목적'],goals:[],centrality:[],network:{nodes:[],edges:[]},similar:[{id:'P2',score:.86,desire:'비슷한 바람'}]};
const context={...row,id:'C1',personaId:'P1',actionDraft:'행동',action:null,dominantConstraint:null,dimsSummary:{},flags:['counter_context','granularity_exceeded']};
const status={run:'r1',status:'review',step:'drafts',progress:1,confirm:{clusters:'3/5',personas:'0/12',contexts:'0/31'}};
const base={disabled:false,edits:{},onEdit:vi.fn(),onConfirm:vi.fn()};

afterEach(()=>{hooks.slots.forEach(slot=>slot?.cleanup?.()); hooks.slots=[]; hooks.effects=[]; state.poll=null; vi.clearAllMocks();});
beforeEach(()=>{
 vi.mocked(getVersionSession).mockResolvedValue({data:{drafts:{}}} as any);
 vi.mocked(api.getSegmentClusters).mockResolvedValue({run:'r1',clusters:[row] as any,kSuggest:null});
 vi.mocked(api.getSegmentPersonas).mockResolvedValue({run:'r1',personas:[persona] as any});
 vi.mocked(api.getSegmentContexts).mockResolvedValue({run:'r1',contexts:[context] as any,emptyGoalConstraintRatio:0});
});
const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
it('opens three candidate sources lazily from evidence without a create action',async()=>{
 const props={...base,sid:'s',version:'v1',contexts:[{...context,flags:['undifferentiated_candidate']}],onBulk:vi.fn(),emptyRatio:0};
 const tree=ContextLayer(props as any);
 const candidate=nodes(tree).find(n=>typeof n.type==='function' && n.type.name==='CandidateSources');
 expect(candidate).toBeDefined();
 const draw=()=>render(()=>candidate.type(candidate.props));
 let details=draw();
 expect(textOf(details)).toContain('새 Context 후보 — 원문 3건');
 expect(getEvidenceContext).not.toHaveBeenCalled();
 vi.mocked(getEvidenceContext).mockResolvedValue({undifferentiated:['d1','d2','d3'],items:[],counter:[],rare:[1,2,3].map(i=>({docId:`d${i}`,text:`후보 원문 ${i}`}))} as any);
 await details.props.onToggle({currentTarget:{open:true}}); await tick();
 details=draw();
 expect(getEvidenceContext).toHaveBeenCalledWith('s','C1','all','v1');
 for(const i of [1,2,3])expect(textOf(details)).toContain(`후보 원문 ${i}`);
 expect(textOf(details)).not.toContain('생성');
 await details.props.onToggle({currentTarget:{open:false}});
 await details.props.onToggle({currentTarget:{open:true}});
 expect(getEvidenceContext).toHaveBeenCalledTimes(1);
 expect(nodes(ContextLayer({...props,contexts:[context]} as any)).some(n=>n.type===candidate.type)).toBe(false);
});
it('navigates completed clustering to evidence without starting a run here',async()=>{
 state.poll={...status,status:'done',confirm:{clusters:'1/1',personas:'1/1',contexts:'1/1'}};
 const draw=()=>render(()=>SegmentScreen({sid:'s',version:'v1'}));
 draw();await tick();draw();await tick();
 const button=nodes(draw()).find(n=>n.props?.children==='근거 탐색 실행');
 expect(button.props.disabled).toBe(false);
 button.props.onClick();
 expect(push).toHaveBeenCalledWith('/pipeline/evidence');
 expect(startEvidence).not.toHaveBeenCalled();
});
