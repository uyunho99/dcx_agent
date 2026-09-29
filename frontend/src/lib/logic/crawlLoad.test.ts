import { afterEach, expect, it, vi } from 'vitest';
import session from './__fixtures__/session_v1.json';
import status from './__fixtures__/crawl_status.json';
import versions from './__fixtures__/versions.json';
import integrations from './__fixtures__/integrations.json';
import { getVersionSession, listVersions } from '../api/versions';
import { getCrawlConnections, getCrawlStatus } from '../api/crawl';
import { deriveCrawlLoad } from './crawlConfig';

afterEach(() => vi.unstubAllGlobals());
it('loads the QA responses without an error and shows approved keywords with default settings', async () => {
  const payloads = [versions, session, status, integrations];
  vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => payloads.shift()})));
  const meta = await listVersions('qa');
  const result = await getVersionSession('qa', meta.activeVersion);
  const initial = await getCrawlStatus('qa');
  expect(await getCrawlConnections()).toEqual(integrations);
  const loaded = deriveCrawlLoad(result, initial, session.data.projectContext, true, new Date(2026, 8, 29));
  expect(loaded.keywords).toHaveLength(19);
  expect(loaded.config.channels).toEqual(session.data.projectContext.channels.filter(c => status.available_sources.includes(c)));
  expect(loaded.config.adWords).toEqual(status.defaults.adWords);
  expect(loaded.config.excludeSources).toEqual(status.defaults.excludeSources);
  expect(loaded.config.dateFrom).toBe('2025-09-29');
  expect(loaded.config.dateTo).toBe('2026-09-29');
  expect(loaded.selection).toEqual([]);
  expect(loaded.savedConfig).toBeNull();
});

it('handles explicitly null config, absent context store, and null snapshot without a crawl draft', () => {
  const loaded = deriveCrawlLoad({data: {...session.data, crawlConfig: null, drafts: {}}}, {...status, snapshot_id: null}, null, true);
  expect(loaded.keywords).toHaveLength(19);
  expect(loaded.config.channels).toEqual(['fixture']);
  expect(loaded.config.adWords).toEqual(status.defaults.adWords);
  expect(loaded.selection).toEqual([]);
});

it('restores gate drafts only for an existing matching snapshot and preserves saved filters', () => {
  const data = {...session.data, crawlConfig: {gateExclusions: ['saved'], adWords: [], target_total: null}, drafts: {crawl: {gate: {collectionId: 'c1', snapshot_id: 'snapshot', exclusions: ['draft', 'unknown']}}}};
  const initial = {...status, collectionId: 'c1', snapshot_id: 'snapshot', gate: ['saved','draft'].map(kw => ({kw}))};
  expect(deriveCrawlLoad({data}, initial, null, true).selection).toEqual(['draft']);
  const stale = deriveCrawlLoad({data}, {...initial, snapshot_id: 'new'}, null, true);
  expect(stale.selection).toEqual(['saved']);
  expect(deriveCrawlLoad({data}, {...initial, collectionId: 'c2'}, null, true).selection).toEqual(['saved']);
  expect(stale.config.adWords).toEqual([]);
  expect(stale.config.target_total).toBeNull();
  expect(deriveCrawlLoad({data}, initial, null, false).config.channels).toEqual([]);
});
