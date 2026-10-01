/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as any[], cursor: 0, effects: [] as (() => void)[]}));
vi.mock('react', async () => ({...await vi.importActual('react'),
  useState: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]=initial; return [hooks.slots[i], (next: any) => {hooks.slots[i]=typeof next==='function' ? next(hooks.slots[i]) : next;}];},
  useRef: (initial: any) => {const i=hooks.cursor++; if (!(i in hooks.slots)) hooks.slots[i]={current:initial}; return hooks.slots[i];},
  useEffect: (effect: () => any, deps: any[]) => {const i=hooks.cursor++; const old=hooks.slots[i]; if (!old || deps.some((d,j)=>d!==old.deps[j])) hooks.effects.push(()=>{old?.cleanup?.(); hooks.slots[i]={deps,cleanup:effect()};});},
}));
vi.mock('next/navigation', () => ({useRouter: () => ({push: vi.fn()})}));
vi.mock('@/stores/useSessionStore', () => ({useSessionStore: (select: any) => select({sid:'s'})}));
vi.mock('@/components/versions/VersionProvider', () => ({useVersion: () => ({version:'v1',readonly:false})}));
vi.mock('@/components/ds', () => ({Banner:'Banner',Button:'Button',Card:'Card',ProgressBar:'ProgressBar'}));
vi.mock('@/components/label/LevelBadge', () => ({LevelBadge:'LevelBadge'}));
vi.mock('@/components/train/ModelRepository', () => ({ModelRepository:'ModelRepository'}));
vi.mock('@/components/train/TrainingResult', () => ({TrainingResult:'TrainingResult'}));
vi.mock('@/lib/api/train', () => ({getTrainingStatus:vi.fn(),getModels:vi.fn().mockResolvedValue({models:[]}),startTraining:vi.fn(),exportTraining:vi.fn()}));
vi.mock('@/lib/api/label', () => ({getLabelOverview:vi.fn()}));
import TrainingPage from './page';
import { getTrainingStatus, getModels, startTraining } from '@/lib/api/train';
import { getLabelOverview } from '@/lib/api/label';
function nodes(node: any): any[] {return !node || typeof node!=='object' ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node,...nodes(node.props?.children)];}
function render() {
  hooks.cursor=0;
  const screen=TrainingPage() as any;
  const tree=nodes(screen.type(screen.props));
  hooks.effects.splice(0).forEach(effect=>effect());
  return tree;
}
afterEach(()=>{hooks.slots.forEach(slot=>slot?.cleanup?.()); hooks.slots=[];hooks.effects=[];vi.useRealTimers();vi.clearAllMocks();});
it('stops idle polling, allows empty export, resumes on start and stops after completion', async () => {
  vi.useFakeTimers();
  vi.mocked(getTrainingStatus).mockResolvedValue({training:{}});
  vi.mocked(getLabelOverview).mockResolvedValue({accepted:0,merged:20,queue:{total:0}} as any);
  render(); await vi.advanceTimersByTimeAsync(0);
  let tree=render();
  expect(tree.some(n=>n.props?.children==='학습할 라벨이 없습니다. 라벨링을 먼저 끝내세요.')).toBe(true);
  expect(tree.find(n=>n.props?.children==='모델 없이 내보내기').props.disabled).toBe(false);
  expect(tree.find(n=>n.props?.children==='학습 시작').props.disabled).toBe(true);
  await vi.advanceTimersByTimeAsync(15000);
  expect(getTrainingStatus).toHaveBeenCalledTimes(1);
  // Reopen with accepted labels, then start a fresh run from the idle screen.
  hooks.slots.forEach(slot=>slot?.cleanup?.()); hooks.slots=[];
  vi.mocked(getLabelOverview).mockResolvedValue({accepted:12,merged:0,queue:{total:0}} as any);
  render(); await vi.advanceTimersByTimeAsync(0);tree=render();
  const worker={runId:'r',kind:'train',state:'running' as const,progress:0,detail:{}};
  vi.mocked(startTraining).mockResolvedValue(worker);
  vi.mocked(getTrainingStatus).mockResolvedValue({training:{runId:'r'},workers:[worker]});
  await tree.find(n=>n.props?.children==='학습 시작').props.onClick();
  await vi.advanceTimersByTimeAsync(0);render();await vi.advanceTimersByTimeAsync(0);
  expect(startTraining).toHaveBeenCalledWith('s',null,'v1');
  const calls=vi.mocked(getTrainingStatus).mock.calls.length;
  vi.mocked(getTrainingStatus).mockResolvedValue({training:{inferStatus:'done'}});
  await vi.advanceTimersByTimeAsync(5000);
  expect(getTrainingStatus).toHaveBeenCalledTimes(calls+1);
  await vi.advanceTimersByTimeAsync(15000);
  expect(getTrainingStatus).toHaveBeenCalledTimes(calls+1);
});

it('renders model export with a secondary monitor failure notice', async () => {
  vi.useFakeTimers();
  vi.mocked(getModels).mockResolvedValue({models:[{modelId:'m',kind:'ensemble'}]});
  vi.mocked(getTrainingStatus).mockResolvedValue({training:{modelId:'m',inferStatus:'done'},workers:[],monitor:{runId:'watch',kind:'monitor',state:'failed',progress:0,detail:{},reason:'감시 연결 실패'}});
  vi.mocked(getLabelOverview).mockResolvedValue({accepted:12,queue:{total:0}} as any);
  render(); await vi.advanceTimersByTimeAsync(0);
  const tree=render();
  expect(tree.find(n=>n.type==='TrainingResult')?.props.disabled).toBe(false);
  expect(tree.find(n=>n.props?.children==='감시를 끝내지 못했습니다 · 감시 연결 실패')?.props.tone).toBe('warning');
});

it('enables fresh and additional training for 40 human-only labels', async () => {
  vi.useFakeTimers();
  vi.mocked(getTrainingStatus).mockResolvedValue({training:{}});
  vi.mocked(getLabelOverview).mockResolvedValue({accepted:0,trainable:40,queue:{total:0}} as any);
  render(); await vi.advanceTimersByTimeAsync(0);
  const tree=render();
  expect(tree.some(n=>n.props?.children==='학습할 라벨이 없습니다. 라벨링을 먼저 끝내세요.')).toBe(false);
  expect(tree.find(n=>n.props?.children==='학습 시작').props.disabled).toBe(false);
  expect(tree.find(n=>n.type==='ModelRepository').props.disabled).toBe(false);
  expect(tree.some(n=>Array.isArray(n.props?.children) && n.props.children[0]==='학습할 라벨 ' && n.props.children[1]==='40')).toBe(true);
});
