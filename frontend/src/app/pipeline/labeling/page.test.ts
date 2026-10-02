/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
  useState: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]=initial; return [hooks.slots[i], (next: any) => {hooks.slots[i]=typeof next==='function' ? next(hooks.slots[i]) : next;}];},
  useCallback: (callback: any) => callback,
  useRef: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]={current:initial}; return hooks.slots[i];},
  useEffect: (effect: () => any, deps: any[]) => {const i=hooks.cursor++; const old=hooks.slots[i]; if (!old || deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.(); hooks.slots[i]={deps,cleanup:effect()};});},
}));
vi.mock('next/navigation', () => ({useRouter: () => ({push: vi.fn()})}));
vi.mock('@/stores/useSessionStore', () => ({useSessionStore: (select: any) => select({sid:'s'})}));
const refreshSessionAfterStage=vi.hoisted(()=>vi.fn().mockResolvedValue(undefined));
vi.mock('@/components/versions/VersionProvider', () => ({useVersion: () => ({version:'v1',readonly:false,refreshSessionAfterStage})}));
vi.mock('@/components/versions/StageVersion', () => ({RestartVersion:'RestartVersion'}));
vi.mock('@/components/ds', () => ({Badge:'Badge',Banner:'Banner',Button:'Button',Tabs:'Tabs'}));
vi.mock('@/components/label/Overview', () => ({Overview:'Overview'}));
vi.mock('@/components/label/Queue', () => ({Queue:'Queue'}));
vi.mock('@/components/label/Audit', () => ({Audit:'Audit'}));
vi.mock('@/lib/api/label', () => ({getLabelOverview:vi.fn(),markLabelSeen:vi.fn()}));
vi.mock('@/lib/api/evidence', () => ({getEvidenceStatus:vi.fn().mockResolvedValue({status:'none'})}));
import {getEvidenceStatus} from '@/lib/api/evidence';
import LabelingPage from './page';
import { getLabelOverview, markLabelSeen } from '@/lib/api/label';
function nodes(node: any): any[] {return !node || typeof node!=='object' ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node,...nodes(node.props?.children)];}
function render() {
 hooks.cursor=0;
 const screen=LabelingPage() as any;
 const tree=nodes(screen.type(screen.props));
 hooks.effects.splice(0).forEach(effect=>effect());
 return tree;
}
afterEach(()=>{hooks.slots.forEach(slot=>slot?.cleanup?.()); hooks.slots=[];hooks.effects=[];vi.useRealTimers();vi.clearAllMocks();});
it('fetches overview before seen, displays server changes, and marks once across polls', async () => {
 vi.useFakeTimers();
 const overview={started:true,mode:'llm',queue:{total:0},changes:{judged:40,merged:40,accepted:20,queued:20}};
 vi.mocked(getLabelOverview).mockResolvedValue(overview as any);
 let finishSeen!: () => void;
 vi.mocked(markLabelSeen).mockImplementation(()=>new Promise(resolve=>{finishSeen=()=>resolve({lastSeenAt:'now'});}));
 render(); await vi.advanceTimersByTimeAsync(0);
 expect(vi.mocked(getLabelOverview).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(markLabelSeen).mock.invocationCallOrder[0]);
 let tree=render();
 expect(tree.find(n=>n.type==='Tabs').props.items[0].content.props.overview).toBe(overview);
 finishSeen(); await vi.advanceTimersByTimeAsync(0);
 tree=render();
 expect(tree.find(n=>n.type==='Tabs').props.items[0].content.props.overview.changes).toEqual(overview.changes);
 const next={...overview,changes:{judged:45,merged:45,accepted:25,queued:20}};
 vi.mocked(getLabelOverview).mockResolvedValue(next as any);
 await vi.advanceTimersByTimeAsync(5000);
 tree=render();
 expect(tree.find(n=>n.type==='Tabs').props.items[0].content.props.overview).toBe(next);
 expect(markLabelSeen).toHaveBeenCalledTimes(1);
 expect(getLabelOverview).toHaveBeenCalledTimes(2);
});

it('refreshes the session once when both judges complete, including while review remains', async () => {
 vi.useFakeTimers();
 vi.mocked(markLabelSeen).mockResolvedValue({lastSeenAt:'now'});
 const overview={started:true,mode:'llm',queue:{total:20},progress:{jev:{state:'done',runId:'j'},gpt:{state:'running',runId:'g'}}};
 vi.mocked(getLabelOverview).mockResolvedValue(overview as any);
 render();await vi.advanceTimersByTimeAsync(0);render();
 expect(refreshSessionAfterStage).not.toHaveBeenCalled();
 vi.mocked(getLabelOverview).mockResolvedValue({...overview,progress:{...overview.progress,gpt:{state:'done',runId:'g'}}} as any);
 await vi.advanceTimersByTimeAsync(5000);render();
 expect(refreshSessionAfterStage).toHaveBeenCalledTimes(1);
 await vi.advanceTimersByTimeAsync(10000);render();
 expect(refreshSessionAfterStage).toHaveBeenCalledTimes(1);
});

it('shows the stage7 irrelevant count as information only', async () => {
 vi.useFakeTimers();
 vi.mocked(getEvidenceStatus).mockResolvedValue({stage7:{irrelevant:7}} as any);
 vi.mocked(getLabelOverview).mockResolvedValue({started:true,queue:{total:0}} as any);
 render(); await vi.advanceTimersByTimeAsync(0);
 const banner=render().find(n=>n.type==='Banner');
 expect(banner).toBeDefined();
 expect(banner.props.tone).toBe('info');
 expect(banner.props.children.join('')).toBe('7단계에서 무관 판정 7건 — 4단계 재점검 참고');
 expect(getEvidenceStatus).toHaveBeenCalledWith('s','v1');
 expect(banner.props.actions).toBeUndefined();
});
it.each([{}, {stage7:{irrelevant:0}}, null])('preserves legacy labeling when evidence is absent, zero, or unavailable: %s', async evidence => {
 vi.useFakeTimers();
 if(evidence) vi.mocked(getEvidenceStatus).mockResolvedValue(evidence as any);
 else vi.mocked(getEvidenceStatus).mockRejectedValue(new Error('not found'));
 vi.mocked(getLabelOverview).mockResolvedValue({legacy:true,message:'기존 세션 라벨링'} as any);
 render(); await vi.advanceTimersByTimeAsync(0);
 const tree=render();
 expect(tree.some(n=>n.props?.children==='기존 세션 라벨링')).toBe(true);
 expect(tree.some(n=>n.type==='Banner')).toBe(false);
 expect(tree.some(n=>n.props?.role==='alert')).toBe(false);
});
