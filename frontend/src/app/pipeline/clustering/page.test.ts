/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
  useState: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]=initial; return [hooks.slots[i], (next: any) => {hooks.slots[i]=typeof next==='function' ? next(hooks.slots[i]) : next;}];},
  useCallback: (callback: any) => callback,
  useRef: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]={current:initial}; return hooks.slots[i];},
  useEffect: (effect: () => any, deps: any[]) => {const i=hooks.cursor++; const old=hooks.slots[i]; if (!old || deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.(); hooks.slots[i]={deps,cleanup:effect()};});},
}));
const view=vi.hoisted(()=>({readonly:false,refreshSessionAfterStage:vi.fn().mockResolvedValue(undefined)}));
const poll=vi.hoisted(()=>({data:{status:'running'} as any}));
vi.mock('next/navigation',()=>({useRouter:()=>({push:vi.fn()})}));
vi.mock('@/stores/useSessionStore',()=>({useSessionStore:()=>({sid:'s',sd:{step:'cluster-start'}})}));
vi.mock('@/components/versions/VersionProvider',()=>({useVersion:()=>view}));
vi.mock('@/lib/usePolling',()=>({usePolling:vi.fn(({enabled})=>({data:enabled ? poll.data : null}))}));
vi.mock('@/lib/api',()=>({getClusterStatus:vi.fn().mockResolvedValue({}),startCluster:vi.fn(),clusterRefine:vi.fn(),saveSession:vi.fn()}));
import ClusteringPage from './page';
import { usePolling } from '@/lib/usePolling';
import { getClusterStatus, startCluster, clusterRefine, saveSession } from '@/lib/api';
function nodes(node: any): any[] {return !node || typeof node!=='object' ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node,...nodes(node.props?.children)];}
function render(){hooks.cursor=0;const tree=nodes(ClusteringPage());hooks.effects.splice(0).forEach(effect=>effect());return tree;}
afterEach(()=>{hooks.slots=[];hooks.effects=[];view.readonly=false;poll.data={status:'running'};vi.clearAllMocks();});
it('refreshes once when clustering results are done, not on running or errors',()=>{
 render();poll.data={status:'error'};render();expect(view.refreshSessionAfterStage).not.toHaveBeenCalled();
 poll.data={status:'done'};render();render();expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
});
it('does not refresh historical clustering results',()=>{
 view.readonly=true;poll.data={status:'done'};render();expect(view.refreshSessionAfterStage).not.toHaveBeenCalled();
});

it('loads and renders historical cluster results while preventing writes and refresh', async () => {
 view.readonly=true;
 let tree=render();
 const options=vi.mocked(usePolling).mock.calls.at(-1)![0];
 expect(options.enabled).toBe(true);
 await options.fetcher();
 expect(getClusterStatus).toHaveBeenCalledWith('s');
 poll.data={status:'done',num_clusters:1,clusters:{'0':{size:7,keywords:['historical keyword']}}};
 tree=render();
 expect(tree.some(n=>n.props?.children==='historical keyword')).toBe(true);
 await tree.find(n=>n.props?.children==='정제 → 페르소나').props.onClick();
 expect(clusterRefine).not.toHaveBeenCalled();
 expect(saveSession).not.toHaveBeenCalled();
 expect(startCluster).not.toHaveBeenCalled();
 expect(view.refreshSessionAfterStage).not.toHaveBeenCalled();
});
