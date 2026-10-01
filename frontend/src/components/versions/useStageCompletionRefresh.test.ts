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
vi.mock('./VersionProvider',()=>({useVersion:()=>view}));
import { useStageCompletionRefresh } from './useStageCompletionRefresh';
function Hook({completion}:{completion:string|null}) {useStageCompletionRefresh(completion);return null;}
function render(key:string|null) {hooks.cursor=0;Hook({completion:key});hooks.effects.splice(0).forEach(effect=>effect());}
afterEach(()=>{hooks.slots=[];hooks.effects=[];view.readonly=false;vi.clearAllMocks();});
it.each(['judge-run','exports/relevant.jsonl','clusters'])('refreshes once per completion transition: %s', async key=>{
 render(null);expect(view.refreshSessionAfterStage).not.toHaveBeenCalled();
 render(key);render(key);await Promise.resolve();
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(1);
 render(null);render(key);await Promise.resolve();
 expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(2);
});
it('does not refresh a past version',()=>{view.readonly=true;render('done');expect(view.refreshSessionAfterStage).not.toHaveBeenCalled();});
it('refreshes a new completed run even when running was between polls',()=>{render('run1');render('run2');expect(view.refreshSessionAfterStage).toHaveBeenCalledTimes(2);});
