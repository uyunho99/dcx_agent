/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
  useState: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]=initial; return [hooks.slots[i], (next: any) => {hooks.slots[i]=typeof next==='function' ? next(hooks.slots[i]) : next;}];},
  useCallback: (callback: any) => callback,
  useRef: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]={current:initial}; return hooks.slots[i];},
  useEffect: (effect: () => any, deps: any[]) => {const i=hooks.cursor++; const old=hooks.slots[i]; if (!old || deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.(); hooks.slots[i]={deps,cleanup:effect()};});},
}));
const store=vi.hoisted(()=>({sid:'s',sd:{schemaVersion:2},setSession:vi.fn()}));
vi.mock('zustand',()=>({create:(init:any)=>{let data:any;const set=(patch:any)=>{data={...data,...patch};};data=init(set);return Object.assign(()=>data,{getState:()=>data});}}));
vi.mock('@/stores/useSessionStore',()=>({useSessionStore:Object.assign((select:any)=>select(store),{getState:()=>store})}));
vi.mock('../DirtyProvider',()=>({useDirty:()=>({confirmNavigation:()=>true})}));
vi.mock('@/components/ds',()=>({Banner:'Banner',Button:'Button'}));
vi.mock('@/lib/api/versions',()=>({getVersionSession:vi.fn(),listVersions:vi.fn()}));
import { VersionProvider } from './VersionProvider';
import { getVersionSession, listVersions } from '@/lib/api/versions';
function render(){hooks.cursor=0;const tree=VersionProvider({children:null});hooks.effects.splice(0).forEach(effect=>effect());return tree.props.value;}
async function load(){
 vi.useFakeTimers();vi.stubGlobal('window',{addEventListener:vi.fn(),removeEventListener:vi.fn()});
 vi.mocked(listVersions).mockResolvedValue({activeVersion:'v2',versions:[{id:'v1',readonly:true},{id:'v2',readonly:false}]} as any);
 vi.mocked(getVersionSession).mockResolvedValue({data:{version:'v2',stale:{stage3:'old'},step:'preprocess'}} as any);
 render();await vi.advanceTimersByTimeAsync(0);render();await vi.advanceTimersByTimeAsync(0);return render();
}
afterEach(()=>{hooks.slots.forEach(slot=>slot?.cleanup?.());hooks.slots=[];hooks.effects=[];store.sid+='s';vi.clearAllMocks();vi.useRealTimers();vi.unstubAllGlobals();});
it('publishes refreshed session to the banner context and store; older periodic reads cannot undo it',async()=>{
 const view=await load();
 let finish!:(value:any)=>void;
 vi.mocked(getVersionSession).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 await vi.advanceTimersByTimeAsync(10000);
 const fresh={version:'v2',step:'preprocess',stale:{},completion:{prepDone:true}} as any;
 vi.mocked(getVersionSession).mockResolvedValue({data:fresh});
 await view.refreshSessionAfterStage();
 expect(render().session).toBe(fresh);
 expect(store.setSession).toHaveBeenCalledWith({sd:fresh,step:'preprocess'});
 finish({data:{version:'v2',stale:{stage3:'old'}}});await vi.advanceTimersByTimeAsync(0);
 expect(render().session).toBe(fresh);
});
it('ignores a refresh that resolves after selection changes and blocks historical refreshes',async()=>{
 const view=await load();
 let finish!:(value:any)=>void;
 vi.mocked(getVersionSession).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const pending=view.refreshSessionAfterStage();
 view.select('v1',true);render();await vi.advanceTimersByTimeAsync(0);
 finish({data:{version:'v2',stale:{}}});await pending;
 expect(store.setSession).not.toHaveBeenCalled();
 const historical=render();expect(historical.readonly).toBe(true);
 vi.mocked(getVersionSession).mockClear();
 await historical.refreshSessionAfterStage();
 expect(getVersionSession).not.toHaveBeenCalled();
});
