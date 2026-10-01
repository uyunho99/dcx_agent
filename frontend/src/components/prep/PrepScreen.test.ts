/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
  useState: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]=initial; return [hooks.slots[i], (next: any) => {hooks.slots[i]=typeof next==='function' ? next(hooks.slots[i]) : next;}];},
  useCallback: (callback: any) => callback,
  useRef: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]={current:initial}; return hooks.slots[i];},
  useEffect: (effect: () => any, deps: any[]) => {const i=hooks.cursor++; const old=hooks.slots[i]; if (!old || deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.(); hooks.slots[i]={deps,cleanup:effect()};});},
}));
const view = vi.hoisted(() => ({version:'v2', readonly:false, session:null as any, refreshSessionAfterStage:vi.fn()}));
vi.mock('next/navigation', () => ({useRouter: () => ({push:vi.fn()})}));
vi.mock('@/components/versions/VersionProvider', () => ({useVersion: () => view}));
vi.mock('@/components/DirtyProvider', () => ({useDirty: () => ({register:vi.fn(),confirmNavigation:()=>true})}));
vi.mock('@/components/versions/StageVersion', async () => ({...await vi.importActual('@/components/versions/StageVersion'),RestartVersion:'RestartVersion'}));
vi.mock('@/components/ds', () => ({Banner:'Banner',Button:'Button',Card:'Card',ProgressBar:'ProgressBar',Skeleton:'Skeleton'}));
vi.mock('./PrepSettings', () => ({PrepSettings:'PrepSettings'}));
vi.mock('./PrepResult', () => ({PrepResult:'PrepResult'}));
vi.mock('@/lib/api/versions', () => ({getVersionSession:vi.fn()}));
vi.mock('@/lib/api/crawl', () => ({getCrawlStatus:vi.fn().mockResolvedValue({})}));
vi.mock('@/lib/api/context', () => ({patchSession:vi.fn().mockResolvedValue({})}));
vi.mock('@/lib/api/prep', () => ({getPrepStatus:vi.fn(),runPrep:vi.fn(),savePrepConfig:vi.fn().mockResolvedValue({})}));
import { StaleBanner } from '@/components/versions/StageVersion';
import { refreshSessionAfterStage } from '@/lib/refreshSessionAfterStage';
import { useSessionStore } from '@/stores/useSessionStore';
import { completedThrough } from '@/lib/logic/completedThrough';
import { PrepScreen } from './PrepScreen';
import { getPrepStatus, runPrep } from '@/lib/api/prep';
import { getVersionSession } from '@/lib/api/versions';
function nodes(node: any): any[] {return !node || typeof node!=='object' ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node,...nodes(node.props?.children)];}
function render() {
 hooks.cursor=0;
 const tree=nodes(PrepScreen({sid:'s'}));
 hooks.effects.splice(0).forEach(effect=>effect());
 return tree;
}
async function load(status='none') {
 vi.useFakeTimers();
 vi.stubGlobal('window', {addEventListener:vi.fn(),removeEventListener:vi.fn()});
 view.session={collectionId:'c',version:'v2',stale:{stage3:'stage3 changed in v2'}};
 vi.mocked(getVersionSession).mockResolvedValue({data:view.session});
 view.refreshSessionAfterStage.mockImplementation(()=>refreshSessionAfterStage('s','v2',session=>{view.session=session;},()=>!view.readonly));
 vi.mocked(getPrepStatus).mockResolvedValue({status,runId:'r',progress:0} as any);
 render(); await vi.advanceTimersByTimeAsync(0);
 return render();
}
afterEach(()=>{hooks.slots.forEach(slot=>slot?.cleanup?.()); hooks.slots=[];hooks.effects=[];view.readonly=false;vi.useRealTimers();vi.clearAllMocks();vi.unstubAllGlobals();});
it.each([false,true])('refreshes the session after immediate done (reused=%s)', async reused => {
 const tree=await load();
 expect(StaleBanner({stage:'stage3',session:view.session})).not.toBe(null);
 const fresh={collectionId:'c',version:'v2',step:'preprocess',stale:{},completion:{prepDone:true}} as any;
 vi.mocked(getVersionSession).mockResolvedValue({data:fresh});
 vi.mocked(runPrep).mockResolvedValue({status:'done',reused,runId:'r',progress:1});
 tree.find(n=>n.props?.children==='전처리 실행').props.onClick();
 await vi.advanceTimersByTimeAsync(0);render();
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
 expect(getVersionSession).toHaveBeenCalledTimes(2);
 expect(StaleBanner({stage:'stage3',session:view.session})).toBe(null);
 expect(useSessionStore.getState().sd).toBe(view.session);
 expect(completedThrough(useSessionStore.getState().sd)).toBe(3);
 await vi.advanceTimersByTimeAsync(9000);render();
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
});
it('refreshes once when polling moves running to done', async () => {
 await load('running');
 vi.mocked(getPrepStatus).mockResolvedValue({status:'done',runId:'r',progress:1});
 await vi.advanceTimersByTimeAsync(3000);render();
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
 await vi.advanceTimersByTimeAsync(9000);render();
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
});
it('does not refresh or run for a historical version', async () => {
 view.readonly=true;
 const tree=await load('done');
 tree.find(n=>n.props?.children==='전처리 실행').props.onClick();
 await vi.advanceTimersByTimeAsync(9000);
 expect(runPrep).not.toHaveBeenCalled();
 expect(view.refreshSessionAfterStage).not.toHaveBeenCalled();
});

it('keeps an immediate done result when session refresh fails, without save error or status recovery', async () => {
 const tree=await load();
 view.refreshSessionAfterStage.mockRejectedValueOnce(new Error('refresh unavailable'));
 vi.mocked(runPrep).mockResolvedValue({status:'done',runId:'r',progress:1});
 const reads=vi.mocked(getPrepStatus).mock.calls.length;
 tree.find(n=>n.props?.children==='전처리 실행').props.onClick();
 await vi.advanceTimersByTimeAsync(0);
 const result=render();
 expect(getPrepStatus).toHaveBeenCalledTimes(reads);
 expect(result.filter(n=>n.type==='Banner' && n.props.tone==='danger')).toEqual([]);
 expect(result.some(n=>n.props?.children==='완료된 결과를 불러오지 못했습니다. 다시 확인하거나 실행하세요.')).toBe(true);
 await vi.advanceTimersByTimeAsync(9000);render();
 expect(runPrep).toHaveBeenCalledTimes(1);
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
});
it('stops polling on done even when session refresh fails', async () => {
 await load('running');
 view.refreshSessionAfterStage.mockRejectedValueOnce(new Error('refresh unavailable'));
 vi.mocked(getPrepStatus).mockResolvedValue({status:'done',runId:'r',progress:1});
 await vi.advanceTimersByTimeAsync(3000);
 const reads=vi.mocked(getPrepStatus).mock.calls.length;
 // A failed optional refresh must not schedule another status request.
 await vi.advanceTimersByTimeAsync(3000);
 expect(getPrepStatus).toHaveBeenCalledTimes(reads);
 expect(render().some(n=>n.type==='Banner' && n.props.children==='refresh unavailable')).toBe(false);
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
});
