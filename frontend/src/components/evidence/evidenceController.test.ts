/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
import { evidenceContextFixture, evidenceStatusFixture, knownInsightsFixture } from './evidenceFixtures';
import type { EvidenceState } from '@/lib/types';
const hooks=vi.hoisted(()=>({slots:[] as any[],cursor:0,effects:[] as (()=>void)[]}));
vi.mock('react',async()=>({...await vi.importActual('react'),
 useState:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]=initial;return [hooks.slots[i],(n:any)=>{hooks.slots[i]=typeof n==='function'?n(hooks.slots[i]):n;}];},
 useRef:(initial:any)=>{const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]={current:initial};return hooks.slots[i];},
 useCallback:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j])) hooks.slots[i]={deps,fn};return hooks.slots[i].fn;},
 useEffect:(fn:any,deps:any[])=>{const i=hooks.cursor++;const old=hooks.slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.();hooks.slots[i]={deps,cleanup:fn()};});},
}));
const view=vi.hoisted(()=>({readonly:false,conflict:null,refreshSessionAfterStage:vi.fn().mockResolvedValue(undefined)}));
const push=vi.hoisted(()=>vi.fn());
const replace=vi.hoisted(()=>vi.fn());
vi.mock('next/navigation',()=>({useRouter:()=>({push,replace})}));
vi.mock('../versions/VersionProvider',()=>({useVersion:()=>view}));
vi.mock('@/lib/api/evidence',()=>({getEvidenceStatus:vi.fn(),getEvidenceContext:vi.fn(),getEvidencePersona:vi.fn(),startEvidence:vi.fn(),refreshEvidenceNew:vi.fn(),skipEvidenceContext:vi.fn()}));
vi.mock('@/lib/api/known',()=>({addKnownInsight:vi.fn(),getKnownInsights:vi.fn()}));
vi.mock('@/lib/api/segment',()=>({getSegmentStatus:vi.fn(),getSegmentPersonas:vi.fn(),getSegmentContexts:vi.fn()}));
import * as api from '@/lib/api/evidence';
import * as segment from '@/lib/api/segment';
import { addKnownInsight, getKnownInsights } from '@/lib/api/known';
import { EvidenceScreen, EvidenceScreenView } from './EvidenceScreen';
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];}
function render(){hooks.cursor=0;const tree=EvidenceScreen({sid:'s',version:'v2',readonly:view.readonly});hooks.effects.splice(0).forEach(fn=>fn());return nodes(tree).find(n=>n.type===EvidenceScreenView).props;}
const row=(id:string)=>({id,name:id,personaId:'P',status:'done' as const,counts:{all:2,new:1},coverage:5,knownChanged:false,error:null});
async function load(state:EvidenceState='running', confirmed=true){
 vi.mocked(getKnownInsights).mockResolvedValue({items:knownInsightsFixture});
 vi.useFakeTimers();
 vi.mocked(api.getEvidenceStatus).mockResolvedValue({...evidenceStatusFixture,status:state,run:'gen',contexts:[row('C1'),row('C2')]});
 vi.mocked(segment.getSegmentStatus).mockResolvedValue({status:'done',run:'seg',confirm:{contexts:confirmed?'2/2':'1/2'}} as any);
 vi.mocked(segment.getSegmentPersonas).mockResolvedValue({run:'seg',personas:[{id:'P',clusterId:'CL0',name:'부모',flags:[]}]} as any);
 vi.mocked(segment.getSegmentContexts).mockResolvedValue({run:'seg',contexts:[{id:'C1',flags:[]},{id:'C2',flags:[]}]} as any);
 vi.mocked(api.getEvidenceContext).mockImplementation(async(_s,id,tab)=>({...evidenceContextFixture,context:{...evidenceContextFixture.context,context_id:id},tab:tab ?? 'all'}));
 vi.mocked(api.getEvidencePersona).mockResolvedValue({desireSupport:[],artifacts:[]});
 render();await vi.advanceTimersByTimeAsync(0);render();await vi.advanceTimersByTimeAsync(0);return render();
}
afterEach(()=>{hooks.slots.forEach(s=>s?.cleanup?.());hooks.slots=[];hooks.effects=[];vi.useRealTimers();vi.clearAllMocks();view.readonly=false;vi.unstubAllGlobals();});
it('loads new by default, switches to all, and discards a late response for a previous selection',async()=>{
 let p=await load();expect(api.getEvidenceContext).toHaveBeenCalledWith('s','C1','new','v2');
 let resolve:any;vi.mocked(api.getEvidenceContext).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 p.onTab('all');render();p=render();p.onContext('C2');render();await vi.advanceTimersByTimeAsync(0);p=render();expect(p.detail.context.context_id).toBe('C2');
 resolve({...evidenceContextFixture,context:{...evidenceContextFixture.context,context_id:'C1'},tab:'all'});await vi.advanceTimersByTimeAsync(0);expect(render().detail.context.context_id).toBe('C2');
});
it('adds KI during running, leaves completed Contexts marked until explicitly recalculated',async()=>{
 const p=await load();
 vi.mocked(addKnownInsight).mockResolvedValue(knownInsightsFixture[0]);
 vi.mocked(api.refreshEvidenceNew).mockResolvedValue(evidenceContextFixture);
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
 const p=await load();expect(p.detail.context.context_id).toBe('C1');
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

it('starts exactly once on stage-six entry after prerequisites load',async()=>{
 vi.stubGlobal('window',{location:{search:'?start=1'}});
 await load('none');await vi.advanceTimersByTimeAsync(0);render();render();
 expect(api.startEvidence).toHaveBeenCalledExactlyOnceWith('s',{},'v2');
 expect(replace).toHaveBeenCalledWith('/pipeline/evidence',{scroll:false});
});
it.each(['running','readonly'])('does not auto-start when %s',async mode=>{
 vi.stubGlobal('window',{location:{search:'?start=1'}});view.readonly=mode==='readonly';
 await load(mode==='running'?'running':'none');await vi.advanceTimersByTimeAsync(0);render();
 expect(api.startEvidence).not.toHaveBeenCalled();
});
it('loads stable Known Insight IDs as display numbers',async()=>{
 const p=await load();expect(p.knownNumbers).toEqual({ki_first:1,ki_second:2});
});

it('waits for confirmed Contexts before consuming automatic start',async()=>{
 vi.stubGlobal('window',{location:{search:'?start=1'}});
 await load('none',false);await vi.advanceTimersByTimeAsync(0);render();
 expect(api.startEvidence).not.toHaveBeenCalled();expect(replace).not.toHaveBeenCalled();
});
it('starts stale evidence fresh on automatic entry',async()=>{
 vi.stubGlobal('window',{location:{search:'?start=1'}});
 await load('stale');await vi.advanceTimersByTimeAsync(0);render();
 expect(api.startEvidence).toHaveBeenCalledExactlyOnceWith('s',{fresh:true},'v2');
});

it.each(['done','partial','interrupted','failed'] as const)('does not auto-start existing %s evidence',async state=>{
 vi.stubGlobal('window',{location:{search:'?start=1'}});
 await load(state);await vi.advanceTimersByTimeAsync(0);render();
 expect(api.startEvidence).not.toHaveBeenCalled();
 expect(replace).toHaveBeenCalledWith('/pipeline/evidence',{scroll:false});
});
it('does not reload Known Insights on unchanged-run status polling',async()=>{
 await load();const count=vi.mocked(getKnownInsights).mock.calls.length;
 vi.mocked(api.getEvidenceStatus).mockResolvedValue({...evidenceStatusFixture,run:'gen',tagCalls:90,contexts:[row('C1'),row('C2')]});
 await vi.advanceTimersByTimeAsync(3000);render();await vi.advanceTimersByTimeAsync(0);
 expect(getKnownInsights).toHaveBeenCalledTimes(count);
});
