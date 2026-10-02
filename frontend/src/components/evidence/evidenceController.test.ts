/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks=vi.hoisted(()=>({slots:[] as any[],cursor:0,effects:[] as (()=>void)[]}));
vi.mock('react',async()=>({...await vi.importActual('react'),
 useState:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]=initial;return [hooks.slots[i],(n:any)=>{hooks.slots[i]=typeof n==='function'?n(hooks.slots[i]):n;}];},
 useRef:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]={current:initial};return hooks.slots[i];},
 useCallback:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j])) hooks.slots[i]={deps,fn};return hooks.slots[i].fn;},
 useEffect:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.();hooks.slots[i]={deps,cleanup:fn()};});},
}));
const view=vi.hoisted(()=>({readonly:false,conflict:null,refreshSessionAfterStage:vi.fn().mockResolvedValue(undefined)}));
const push=vi.hoisted(()=>vi.fn());
vi.mock('next/navigation',()=>({useRouter:()=>({push})}));
vi.mock('../versions/VersionProvider',()=>({useVersion:()=>view}));
vi.mock('@/lib/api/evidence',()=>({getEvidenceStatus:vi.fn(),getEvidenceContext:vi.fn(),getEvidencePersona:vi.fn(),startEvidence:vi.fn(),refreshEvidenceNew:vi.fn(),skipEvidenceContext:vi.fn()}));
vi.mock('@/lib/api/known',()=>({addKnownInsight:vi.fn()}));
vi.mock('@/lib/api/segment',()=>({getSegmentStatus:vi.fn(),getSegmentPersonas:vi.fn(),getSegmentContexts:vi.fn()}));
import * as api from '@/lib/api/evidence';
import * as segment from '@/lib/api/segment';
import { addKnownInsight } from '@/lib/api/known';
import { EvidenceScreen, EvidenceScreenView } from './EvidenceScreen';
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];}
function render(){hooks.cursor=0;const tree=EvidenceScreen({sid:'s',version:'v2',readonly:view.readonly});hooks.effects.splice(0).forEach(fn=>fn());return nodes(tree).find(n=>n.type===EvidenceScreenView).props;}
const row=(id:string)=>({id,name:id,personaId:'P',status:'done',counts:{all:2,new:1},coverage:5,knownChanged:false,error:null});
async function load(){
 vi.useFakeTimers();
 vi.mocked(api.getEvidenceStatus).mockResolvedValue({status:'running',run:'gen',progress:50,contexts:[row('C1'),row('C2')]} as any);
 vi.mocked(segment.getSegmentStatus).mockResolvedValue({status:'done',run:'seg',confirm:{contexts:'2/2'}} as any);
 vi.mocked(segment.getSegmentPersonas).mockResolvedValue({run:'seg',personas:[{id:'P',clusterId:'CL0',name:'부모',flags:[]}]} as any);
 vi.mocked(segment.getSegmentContexts).mockResolvedValue({run:'seg',contexts:[{id:'C1',flags:[]},{id:'C2',flags:[]}]} as any);
 vi.mocked(api.getEvidenceContext).mockImplementation(async(_s,id,tab)=>({context:{id},tab,items:[],queries:[],counter:[],rare:[],excludedKnown:0,queryFailed:false,undifferentiated:[]} as any));
 vi.mocked(api.getEvidencePersona).mockResolvedValue({desireSupport:[],artifacts:[]});
 render();await vi.advanceTimersByTimeAsync(0);render();await vi.advanceTimersByTimeAsync(0);return render();
}
afterEach(()=>{hooks.slots.forEach(s=>s?.cleanup?.());hooks.slots=[];hooks.effects=[];vi.useRealTimers();vi.clearAllMocks();view.readonly=false;});
it('loads new by default, switches to all, and discards a late response for a previous selection',async()=>{
 let p=await load();expect(api.getEvidenceContext).toHaveBeenCalledWith('s','C1','new','v2');
 let resolve:any;vi.mocked(api.getEvidenceContext).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 p.onTab('all');render();p=render();p.onContext('C2');render();await vi.advanceTimersByTimeAsync(0);p=render();expect(p.detail.context.id).toBe('C2');
 resolve({context:{id:'C1'},tab:'all'});await vi.advanceTimersByTimeAsync(0);expect(render().detail.context.id).toBe('C2');
});
it('adds KI during running, leaves completed Contexts marked until explicitly recalculated',async()=>{
 const p=await load();
 vi.mocked(addKnownInsight).mockResolvedValue({id:'ki'} as any);
 vi.mocked(api.refreshEvidenceNew).mockResolvedValue({} as any);
 vi.mocked(api.getEvidenceStatus).mockResolvedValue({status:'running',run:'gen',progress:50,contexts:[{...row('C1'),knownChanged:true},{...row('C2'),knownChanged:true}]} as any);
 p.onAdded('doc');await vi.advanceTimersByTimeAsync(0);const next=render();
 expect(addKnownInsight).toHaveBeenCalledWith('s',{type:'doc',doc_id:'doc'},'v2');expect(api.refreshEvidenceNew).not.toHaveBeenCalled();expect(next.status.contexts.every((c:any)=>c.knownChanged)).toBe(true);
 next.onRefresh('C2');await vi.advanceTimersByTimeAsync(0);expect(api.refreshEvidenceNew).toHaveBeenLastCalledWith('s','C2',{run:'gen'},'v2');
});
it('does not mutate a historical version while allowing evidence browsing',async()=>{
 view.readonly=true;const p=await load();p.onAdded('doc');p.onRetry('C1');p.onSkip('C1');p.onStart();await vi.advanceTimersByTimeAsync(0);
 expect(addKnownInsight).not.toHaveBeenCalled();expect(api.startEvidence).not.toHaveBeenCalled();expect(api.skipEvidenceContext).not.toHaveBeenCalled();expect(api.getEvidenceContext).toHaveBeenCalled();
});
it('navigates to personas without starting any generation',async()=>{
 await load();vi.mocked(api.getEvidenceStatus).mockResolvedValue({status:'done',run:'gen',progress:100,contexts:[row('C1')]} as any);
 await vi.advanceTimersByTimeAsync(3000);render().onNext();expect(push).toHaveBeenCalledWith('/pipeline/personas');expect(api.startEvidence).not.toHaveBeenCalled();
});

it('clears previous evidence immediately when the selection changes',async()=>{
 const p=await load();expect(p.detail.context.id).toBe('C1');
 p.onContext('C2');expect(render().detail).toBeNull();
});
it('blocks stale row actions while allowing a fresh run',async()=>{
 await load();vi.mocked(api.getEvidenceStatus).mockResolvedValue({status:'stale',run:'gen',progress:0,contexts:[row('C1')]} as any);
 await vi.advanceTimersByTimeAsync(3000);const p=render();p.onRefresh('C1');p.onRetry('C1');p.onSkip('C1');await vi.advanceTimersByTimeAsync(0);
 expect(api.refreshEvidenceNew).not.toHaveBeenCalled();expect(api.startEvidence).not.toHaveBeenCalled();expect(api.skipEvidenceContext).not.toHaveBeenCalled();
 p.onStart();await vi.advanceTimersByTimeAsync(0);expect(api.startEvidence).toHaveBeenCalledWith('s',{fresh:true},'v2');
});

it('reloads Persona support when another Context finishes during the same run',async()=>{
 await load();const before=vi.mocked(api.getEvidencePersona).mock.calls.length;
 vi.mocked(api.getEvidenceStatus).mockResolvedValue({status:'running',run:'gen',progress:0.75,contexts:[row('C1'),row('C2'),row('C3')]} as any);
 await vi.advanceTimersByTimeAsync(3000);render();await vi.advanceTimersByTimeAsync(0);
 expect(api.getEvidencePersona).toHaveBeenCalledTimes(before+1);
});
