import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { completedThrough } from './completedThrough';
import StepBar, { STEP_MAP, STEP_NAMES, stepIndex } from '@/components/StepBar';

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

describe('T15 stage completion', () => {
  it('uses segmentDone even when legacy completion is false', () => {
    expect(completedThrough({ completion: { ...completion, segmentDone: true } })).toBe(6);
    const html = sidebar('train-check', { completion: { segmentDone: true } });
    expect(html).toContain('클러스터링 완료');
    expect(html).not.toContain('근거 탐색 완료');
    expect(html).not.toContain('페르소나 완료');
  });
  it('treats explicit segmentDone false as authoritative', () => {
    expect(completedThrough({ clusters: { '0': {} },
      completion: { segmentDone: false, clustersDone: true, exportDone: true } })).toBe(5);
  });
  it.each([
    [{ clusters: { '0': {} } }, 6],
    [{ clusters: {} }, 0],
    [{ clusters: ['legacy'] }, 0],
    [{ completion: { clustersDone: true } }, 6],
    [{ clusters: { '0': {} }, completion: { clustersDone: false } }, 0],
    [{ completion: { segmentDone: 'true' } }, 0],
  ])('preserves the legacy fallback for %j → %i', (session, expected) => {
    expect(completedThrough(session)).toBe(expected);
  });
});

describe('T15 chat context step names', () => {
  it.each([
    ['persona-start', '페르소나'],
    ['evidence', '근거 탐색'],
    ['done', '페르소나'],
    ['clustering', '클러스터링'],
    ['start', '시작'],
  ])('maps %s to %s for chat context', (step, expected) => {
    expect(STEP_NAMES[Math.max(0, stepIndex(step))] || '시작').toBe(expected);
  });
});

describe('T15 step keys (R3 critical regression)', () => {
  it.each([
    ...['clustering', 'cluster-start', 'cluster-check', 'cluster-refine', 'cluster-legacy'].map(key => [key, 6] as const),
    ...['persona', 'persona-start', 'persona-check', 'persona-legacy', 'embed-start', 'embed-check', 'embed-legacy', 'done'].map(key => [key, 8] as const),
    ...['evidence', 'evidence-start', 'evidenceSearch'].map(key => [key, 7] as const),
    ...['insight', 'insight-start', 'insights'].map(key => [key, 9] as const),
    ['prep-future', 3], ['label-future', 4], ['train-future', 5],
    ['start', 0], ['r4', 1], ['crawl-detail', 2], ['preprocess-start', 3], ['labeling', 4], ['unknown', 0],
  ] as const)('maps %s to %i', (key, expected) => {
    expect(stepIndex(key)).toBe(expected);
  });
  it.each(['persona', 'persona-start', 'persona-check', 'embed-start', 'embed-check', 'done'])('updates the exported legacy mapping for %s', key => {
    expect(STEP_MAP[key]).toBe(8);
  });
});

it('renders the ten stages in order with future stages disabled and personas navigable', () => {
  const html = sidebar('start');
  const names = [...html.matchAll(/<span>([^<]+)<\/span>/g)].map(match => match[1]);
  expect(names).toEqual(['시작', '키워드', '크롤링', '전처리', '라벨링', '학습', '클러스터링', '근거 탐색', '페르소나', '인사이트']);
  expect(html).not.toContain('임베딩');
  for (const name of ['근거 탐색', '인사이트']) {
    const tag = html.match(new RegExp(`<([a-z]+)\\b([^>]*aria-label="[^"]*${name}[^"]*"[^>]*)>`));
    expect(tag).not.toBeNull();
    expect(tag![2]).toContain('aria-disabled="true"');
    expect(tag![2]).toContain('title="다음 묶음에서 열립니다"');
    expect(tag![2]).not.toMatch(/\bhref=/);
    expect(tag![2]).not.toMatch(/\btabindex="0"/);
  }
  expect(html).toMatch(/<a\b[^>]*aria-label="9\. 페르소나"[^>]*href="\/pipeline\/personas"/);
  expect([...html.matchAll(/\bhref="([^"]+)"/g)].map(match => match[1])).toEqual([
    '/pipeline/start', '/pipeline/keywords', '/pipeline/crawling', '/pipeline/preprocess',
    '/pipeline/labeling', '/pipeline/training', '/pipeline/clustering', '/pipeline/personas',
  ]);
});
