import { afterEach, describe, expect, it, vi } from 'vitest';
import { cxCounts, foldColumns, gradeLabel, sortContexts, zoneName } from './personaView';
import * as persona from '../../lib/api/persona';
import * as insight from '../../lib/api/insight';

afterEach(() => vi.unstubAllGlobals());

describe('persona presentation contract', () => {
  it('pairs every grade with exact Korean copy and a distinct shape', () => {
    expect(gradeLabel('observed')).toEqual({ text: '관측', shape: 'circle' });
    expect(gradeLabel('inferred')).toEqual({ text: '추론', shape: 'triangle' });
    expect(gradeLabel('speculated')).toEqual({ text: '추측', shape: 'cross' });
    expect(gradeLabel(null)).toEqual({ text: '근거 부족', shape: null });
  });

  it.each([
    [0, 1, 0], [1, 1, 1], [4, 1, 4], [5, 2, 4],
    [8, 2, 4], [9, 2, 5], [10, 2, 5],
  ])('folds %i contexts into %i rows of at most %i columns', (n, rows, columns) => {
    expect(foldColumns(n)).toEqual({ rows, columns });
  });

  it.each([-1, 1.5, 11, NaN, Infinity])('rejects invalid context counts (%s)', n => {
    expect(() => foldColumns(n)).toThrow(RangeError);
  });

  it('sorts numbers, text and stars without mutating or dropping overlapping points', () => {
    const rows = Object.freeze([
      { context_id: 'C2', odi: 1, name: '나', star: false },
      { context_id: 'C1', odi: 1, name: '가', star: true },
      { context_id: 'C3', odi: 0.5, name: '다', star: false },
    ]);
    expect(sortContexts(rows, 'odi', 'desc').map(r => r.context_id)).toEqual(['C1', 'C2', 'C3']);
    expect(sortContexts(rows, 'odi', 'asc').map(r => r.context_id)).toEqual(['C3', 'C1', 'C2']);
    expect(sortContexts(rows, 'name', 'asc').map(r => r.context_id)).toEqual(['C1', 'C2', 'C3']);
    expect(sortContexts(rows, 'star', 'desc').map(r => r.context_id)).toEqual(['C1', 'C2', 'C3']);
    expect(rows.map(r => r.context_id)).toEqual(['C2', 'C1', 'C3']);
    expect(sortContexts(rows, 'odi', 'desc')[0]).toBe(rows[1]);
  });

  it('preserves input order for equal values and ids and puts missing metrics last', () => {
    const rows = [
      { context_id: 'C0', odi: null }, { context_id: 'C1', odi: 1 },
      { context_id: 'C1', odi: 1 }, { context_id: 'C2', odi: NaN },
    ];
    for (const dir of ['asc', 'desc'] as const) {
      const sorted = sortContexts(rows, 'odi', dir);
      expect(sorted).toEqual([rows[1], rows[2], rows[0], rows[3]]);
      expect(sorted[0]).toBe(rows[1]);
      expect(sorted[1]).toBe(rows[2]);
    }
    expect(sortContexts([], 'context_id', 'asc')).toEqual([]);
  });

  it('uses the six exact zone names', () => {
    expect((['A', 'B', 'C', 'D', 'E', 'F'] as const).map(zoneName)).toEqual([
      'A Exciting', 'B Experiencing', 'C Competitive', 'D Forgiven', 'E Dangling', 'F At-risk',
    ]);
  });

  it('counts journey rows in all four CX dimensions, including zero counts', () => {
    expect(cxCounts([])).toEqual({ 정신적: 0, 물리적: 0, 문화적: 0, 시스템: 0 });
    expect(cxCounts([
      { cx_4d: '정신적' }, { cx_4d: '물리적' }, { cx_4d: '정신적' }, { cx_4d: '시스템' },
    ])).toEqual({ 정신적: 2, 물리적: 1, 문화적: 0, 시스템: 1 });
  });
});

const mockResponse = (data: unknown) => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => data });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
};

describe('persona API wire contract (offline)', () => {
  it('uses the singular persona paths and preserves response envelopes', async () => {
    const envelope = { run: 'generation', personas: {} };
    const fetcher = mockResponse(envelope);
    expect(await persona.getPersonaCards('s /', 'v 2')).toBe(envelope);
    await persona.getPersonaStatus('s');
    await persona.getPersonaCard('s', 'P/1', 'v2');
    await persona.getPersonaMap('s', 'v2');
    await persona.getPersonaTree('s', 'v2');
    expect(fetcher.mock.calls.map(([url, init]) => [url, init.method, init.body])).toEqual([
      ['/persona/s%20%2F/cards?version=v%202', 'GET', undefined],
      ['/persona/s/status', 'GET', undefined],
      ['/persona/s/cards/P%2F1?version=v2', 'GET', undefined],
      ['/persona/s/map?version=v2', 'GET', undefined],
      ['/persona/s/tree?version=v2', 'GET', undefined],
    ]);
  });

  it('sends fresh/personas and retries with the result generation', async () => {
    const fetcher = mockResponse({ runId: 'worker' });
    expect(await persona.startPersona('s /', { fresh: true, personas: ['P/1'] }, 'v 2')).toEqual({ runId: 'worker' });
    await persona.startPersona('s');
    await persona.retryPersonaCard('s', 'P/1', { run: 'generation' }, 'v2');
    expect(fetcher.mock.calls.map(([url, init]) => [url, init.method, JSON.parse(init.body)])).toEqual([
      ['/persona/s%20%2F/run?version=v%202', 'POST', { fresh: true, personas: ['P/1'] }],
      ['/persona/s/run', 'POST', {}],
      ['/persona/s/cards/P%2F1/retry?version=v2', 'POST', { run: 'generation' }],
    ]);
  });

  it.each(['evidence_required', 'running', 'locked', 'not_ready', 'stale_run'])('propagates %s through contextRequest', async kind => {
    const message = '근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다.';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ error: { kind, message } }) }));
    await expect(persona.getPersonaCards('s')).rejects.toThrow(message);
  });
});

describe('insight API wire contract (offline)', () => {
  it('reads the root insight envelope and previous-session suggestions', async () => {
    const envelope = { insights: { revision: 1, items: [], history: [] }, concepts: { revision: 0, items: [], history: [] }, bars: {}, radar: {} };
    const fetcher = vi.fn(async (url: string) => ({ok:true,json:async () => url.startsWith('/session/') ? {data:{insight:{confirmed:[]}}} : envelope}));
    vi.stubGlobal('fetch',fetcher);
    expect(await insight.getInsights('s /', 'v 2')).toEqual({...envelope,confirmed:[]});
    await insight.getKnownSuggestions('s /', 'v 2');
    await insight.getInsights('s');
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/insight/s%20%2F?version=v%202', '/session/s%20%2F?version=v%202', '/known/s%20%2F/suggestions?version=v%202', '/insight/s', '/session/s',
    ]);
  });

  it('uses exact methods, singular concept paths and unmodified request bodies', async () => {
    const fetcher = mockResponse({ runId: 'worker' });
    await insight.startInsight('s', { mode: 'derive' }, 'v2');
    await insight.startInsight('s', { mode: 'concept', target: 'I/1' }, 'v2');
    await insight.createInsightConcept('s /', 'I/1', 'v 2');
    await insight.chatInsight('s', { target: 'insights', message: '수정' }, 'v2');
    await insight.chatInsight('s', { target: 'concept:I/1', message: '수정' }, 'v2');
    await insight.revertInsight('s', { target: 'concept:I/1', revision: 1 }, 'v2');
    await insight.confirmInsights('s', { ids: [] }, 'v2');
    await insight.addSuggestedKnownInsight('s /', { type: 'statement', text: '발견' }, 'v 2');
    expect(fetcher.mock.calls.map(([url, init]) => [url, init.method, init.body === undefined ? undefined : JSON.parse(init.body)])).toEqual([
      ['/insight/s/run?version=v2', 'POST', { mode: 'derive' }],
      ['/insight/s/run?version=v2', 'POST', { mode: 'concept', target: 'I/1' }],
      ['/insight/s%20%2F/concept/I%2F1?version=v%202', 'POST', undefined],
      ['/insight/s/chat?version=v2', 'POST', { target: 'insights', message: '수정' }],
      ['/insight/s/chat?version=v2', 'POST', { target: 'concept:I/1', message: '수정' }],
      ['/insight/s/revert?version=v2', 'POST', { target: 'concept:I/1', revision: 1 }],
      ['/insight/s/confirm?version=v2', 'PUT', { ids: [] }],
      ['/known/s%20%2F?version=v%202', 'POST', { type: 'statement', text: '발견', from: 'prev_session' }],
    ]);
  });

  it('preserves both chat outcomes without turning a rejected edit into an exception', async () => {
    const rejected = { ok: false, message: '요청을 반영하지 못했습니다. 다르게 말해 주세요.' };
    mockResponse(rejected);
    expect(await insight.chatInsight('s', { target: 'insights', message: '수정' })).toBe(rejected);
    mockResponse({ ok: true, revision: 2 });
    expect(await insight.chatInsight('s', { target: 'insights', message: '수정' })).toEqual({ ok: true, revision: 2 });
  });

  it.each(['persona_required', 'not_found'])('propagates %s errors', async kind => {
    const message = kind === 'persona_required' ? '페르소나를 만든 뒤 인사이트를 도출할 수 있습니다.' : '요청에 실패했습니다. 다시 시도하세요.';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ error: { kind, message } }) }));
    await expect(insight.startInsight('s', { mode: 'derive' })).rejects.toThrow(message);
  });
});
