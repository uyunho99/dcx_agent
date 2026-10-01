import { afterEach, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CoveragePanel, coverageInterpretation, coverageMetrics, startCoveragePolling } from './CoveragePanel';
import { getCoverage } from '@/lib/api/keywords';
import type { Coverage } from '@/lib/api/keywords';

const autocomplete: Coverage = { status: 'connected', source: 'autocomplete', weighting: 'rank', seeds: 21, failedSeeds: 3, humanQueries: [['검색어', 2]], m1: .62, m2: null, m2_bands: [{ label: '1~3위', value: .7 }, { label: '4~6위', value: null }, { label: '7~10위', value: .4 }], m6: .12, m7: null, m7_reason: 'no_volume', missing_top: [['검색어', 2]] };
const render = (coverage: Coverage) => renderToStaticMarkup(createElement(CoveragePanel, { coverage, busy: false, beforeR3: true, onRefresh: () => {} }));
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it.each([[], undefined])('preserves R-114 unconnected copy with humanQueries=%j', humanQueries => {
  const coverage = { status: 'unconnected', humanQueries };
  expect(coverageInterpretation(coverage)).toBe('검색광고가 연결되지 않아 사람 검색어를 받지 못했습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.');
  expect(render(coverage)).toContain('미연결 · 검색광고 API가 연결되지 않았습니다. 커버리지 없이 R3을 생성합니다.');
});
it.each(['connected', 'failed', undefined])('preserves round interpretation for %s', status => {
  expect(coverageInterpretation({ status, missing_top: [['검색어', 100]] })).toBe('누락 쿼리 1개가 다음 라운드의 입력에 반영됩니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.');
});
it('renders autocomplete insight, evidence and partial failures', () => {
  const html = render(autocomplete);
  for (const copy of ['사람들이 많이 찾는 표현의 62%를 덮고 있습니다.', '사람 검색어', '1개', '출처', '네이버 자동완성', '가중', '순위 가중', '질의 21개 중 3개 실패', '② 순위 구간별 커버리지', '계산 불가(검색량 없음)', '<th scope="col">자동완성 순위</th>']) expect(html).toContain(copy);
});
it('shows rank bands with an em dash for an empty band', () => {
  expect(coverageMetrics(autocomplete).bands).toEqual([{ label: '1~3위', value: .7, displayValue: '70%' }, { label: '4~6위', value: 0, displayValue: '—' }, { label: '7~10위', value: .4, displayValue: '40%' }]);
});
it('explains unavailable autocomplete and failed seeds', () => {
  const html = render({ ...autocomplete, status: 'unavailable', m1: null });
  expect(html).toContain('커버리지 계산 불가');
  expect(html).toContain('네이버 자동완성을 받지 못해 커버리지를 계산할 수 없습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.');
  expect(html).toContain('실패한 질의');
  expect(html).toContain('3개');
});
it('announces loading, disables refresh and dims retained metrics', () => {
  const html = render({ ...autocomplete, status: 'loading' });
  expect(html).toContain('aria-live="polite">네이버 자동완성에서 사람 검색어를 받는 중입니다(약 20초).');
  expect(html).toMatch(/<button[^>]*disabled=""[^>]*aria-busy="true"/);
  expect(html).toContain('opacity:0.5');
  expect(html).toContain('70%');
});
it('distinguishes empty tables by source and preserves searchad metrics', () => {
  expect(render({ ...autocomplete, missing_top: [] })).toContain('자동완성 검색어를 모두 덮고 있습니다.');
  const html = render({ status: 'connected', source: 'searchad', m2: [.5, null], missing_top: [] });
  for (const copy of ['네이버 검색광고 연관키워드', '사람 쿼리', '① 검색량 가중', '② 검색량 구간별 커버리지', '월간 검색수', '표시할 누락 쿼리가 없습니다.', '1분위', '50%']) expect(html).toContain(copy);
  expect(html).not.toContain('순위 가중');
});
it.each(['connected', 'unavailable', 'unconnected'])('polls every 3 seconds and stops on %s', async status => {
  vi.useFakeTimers();
  const read = vi.fn().mockResolvedValueOnce({ coverage: { status: 'loading' } }).mockResolvedValue({ coverage: { status } });
  const receive = vi.fn(); const error = vi.fn();
  const stop = startCoveragePolling(read, receive, error);
  await vi.advanceTimersByTimeAsync(2999); expect(read).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1); expect(read).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(3000); expect(read).toHaveBeenCalledTimes(2);
  await vi.advanceTimersByTimeAsync(9000); expect(read).toHaveBeenCalledTimes(2);
  expect(receive).toHaveBeenCalledTimes(2); expect(error).not.toHaveBeenCalled(); stop();
});
it('cancels in-flight coverage polling without applying stale results', async () => {
  vi.useFakeTimers();
  let resolve!: (value: { coverage: Coverage }) => void;
  const read = vi.fn(() => new Promise<{ coverage: Coverage }>(r => { resolve = r; }));
  const receive = vi.fn();
  const stop = startCoveragePolling(read, receive, vi.fn());
  await vi.advanceTimersByTimeAsync(3000); stop(); resolve({ coverage: autocomplete });
  await vi.advanceTimersByTimeAsync(6000); expect(receive).not.toHaveBeenCalled(); expect(read).toHaveBeenCalledTimes(1);
});
it('explicit recalculation sends refresh=true and keeps the version', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => autocomplete }); vi.stubGlobal('fetch', fetch);
  await getCoverage('session', 'v1');
  expect(fetch.mock.calls[0][0]).toContain('/keywords/session/coverage?refresh=true&version=v1');
  expect(fetch.mock.calls[0][1].method).toBe('POST');
});
