/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useState: (initial:any) => {const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]=initial;return [hooks.slots[i],(next:any)=>{hooks.slots[i]=next;}];},
 useRef: (initial:any) => {const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]={current:initial};return hooks.slots[i];},
}));
const state = vi.hoisted(() => ({push:vi.fn(),select:vi.fn(),setSession:vi.fn()}));
vi.mock('next/navigation',()=>({useRouter:()=>({push:state.push}),usePathname:()=>'/pipeline/evidence'}));
vi.mock('./VersionProvider',()=>({useVersion:()=>({sid:'s',meta:{activeVersion:'v1'},select:state.select})}));
vi.mock('../DirtyProvider',()=>({useDirty:()=>({confirmNavigation:()=>true})}));
vi.mock('@/stores/useSessionStore',()=>({useSessionStore:Object.assign(()=>({}),{getState:()=>({setSession:state.setSession})})}));
vi.mock('@/lib/api/versions',()=>({createVersion:vi.fn(),getVersionSession:vi.fn()}));
import { createVersion, getVersionSession } from '@/lib/api/versions';
import { RestartVersion } from './StageVersion';
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];}
function render(){hooks.cursor=0;return nodes(RestartVersion({}));}
afterEach(()=>{hooks.slots=[];vi.clearAllMocks();});
it('offers stage 8 and opens personas after creating its restart version',async()=>{
 const tree=render();
 expect(tree.find(n=>n.type==='option' && n.props.value==='stage8')?.props.children).toEqual([8,'단계']);
 tree.find(n=>n.type==='select').props.onChange({target:{value:'stage8'}});
 vi.mocked(createVersion).mockResolvedValue({version:'v2'});
 vi.mocked(getVersionSession).mockResolvedValue({data:{step:'persona-start',version:'v2'}} as any);
 const button=render().find(n=>n.props.children==='새 버전 만들기');
 expect(button.props.disabled).toBe(false);
 button.props.onClick();
 await vi.waitFor(()=>expect(state.push).toHaveBeenCalledWith('/pipeline/personas'));
 expect(createVersion).toHaveBeenCalledWith('s','v1','stage8','');
 expect(state.select).toHaveBeenCalledWith('v2',true);
});
