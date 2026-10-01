import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { completedThrough } from './completedThrough';
import StepBar from '@/components/StepBar';

vi.mock('next/navigation', () => ({ usePathname: () => '/pipeline/preprocess' }));
vi.mock('@/components/DirtyProvider', () => ({ useDirty: () => ({ confirmNavigation: () => true }) }));

describe('completedThrough', () => {
  it.each([null, undefined, {}, { keywordRounds: {} }])('defaults to zero for %j', session => {
    expect(completedThrough(session)).toBe(0);
  });
  it.each([
    [{ keywordRounds: { '4': { committed: true } } }, 1],
    [{ step: 'crawl-done' }, 2],
    [{ crawl: { kind: 'detail', status: 'done' } }, 2],
    [{ prep: { status: 'done' } }, 3],
    [{ labeling: { status: 'done' } }, 4],
    [{ training: { exportRef: 'exports/relevant.jsonl' } }, 5],
    [{ clusters: { '0': { size: 3 } } }, 6],
    [{ prep: { status: 'done' }, training: { exportRef: 'exports/relevant.jsonl' } }, 5],
  ])('uses completed server evidence %j → %i', (session, expected) => {
    expect(completedThrough(session)).toBe(expected);
  });
  it.each([
    { keywordRounds: { '3': { committed: true }, '4': { committed: false, job: { status: 'done' } } } },
    { crawl: { kind: 'list', status: 'done' } },
    { crawl: { kind: 'detail', status: 'paused' } },
    { prep: { status: 'running' } },
    { labeling: { started: true, status: 'stale', judgeRuns: { jev: 'run1', gpt: 'run2' } } },
    { training: { status: 'done', exportRef: '' } },
    { clusters: {} },
  ])('does not infer completion from incomplete work %j', session => {
    expect(completedThrough(session)).toBe(0);
  });
});

function sidebar(currentStep: string, session?: Record<string, unknown>) {
  return renderToStaticMarkup(createElement(StepBar, { currentStep, session }));
}

it('checks the completed stage itself even when the saved step lags', () => {
  const html = sidebar('r4', { prep: { status: 'done' } });
  expect(html).toContain('전처리 완료');
  expect(html).toContain('크롤링 완료');
  expect(html).not.toContain('라벨링 완료');
  expect(html).toMatch(/aria-current="step"[^>]*href="\/pipeline\/preprocess"/);
});
it('retains saved-step completion when it is further ahead', () => {
  const html = sidebar('train-check', { keywordRounds: { '4': { committed: true } } });
  expect(html).toContain('라벨링 완료');
  expect(html).not.toContain('학습 완료');
});
it('checks cluster results without checking personas', () => {
  const html = sidebar('cluster-start', { clusters: { '0': { size: 3 } } });
  expect(html).toContain('클러스터링 완료');
  expect(html).not.toContain('페르소나 완료');
});
it('keeps legacy callers working without session data', () => {
  expect(sidebar('train-check')).toContain('라벨링 완료');
  expect(sidebar('start')).not.toContain('완료');
});

const completion = { crawlDone: false, prepDone: false, labelingDone: false, exportDone: false, clustersDone: false };
it.each([
  ['crawlDone', 2], ['prepDone', 3], ['labelingDone', 4], ['exportDone', 5], ['clustersDone', 6],
])('uses the session payload completion.%s', (signal, expected) => {
  const session = { schemaVersion: 2, version: 'v1', collectionId: 'c1', step: 'crawl-detail',
    labeling: { judgeRuns: { jev: 'run1', gpt: 'run2' } },
    completion: { ...completion, [signal]: true } };
  expect(completedThrough(session)).toBe(expected);
});
it('treats explicit server false as authoritative over old heuristics', () => {
  expect(completedThrough({ step: 'crawl-done', prep: { status: 'done' },
    labeling: { status: 'done' }, training: { exportRef: 'old.jsonl' },
    clusters: { '0': { size: 3 } }, completion })).toBe(0);
});
it('checks crawl when preprocess is opened without crawl polling', () => {
  expect(sidebar('crawl-detail', { collectionId: 'c1', step: 'crawl-detail',
    completion: { ...completion, crawlDone: true } })).toContain('크롤링 완료');
});
