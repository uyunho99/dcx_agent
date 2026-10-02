import { describe, expect, it } from 'vitest';
import { parseList, prefillFilters, enabledChannelConfig, settingsSources, deriveCrawlLoad } from './crawlConfig';
import type { Limits } from '../api/crawl';

describe('crawl settings', () => {
  const initial = { defaults: { adWords: [], excludeSources: [] }, available_sources: ['naver_blog'], gate: null };

  it('merges channel defaults into partial saved perChannel', () => {
    for (const saved of [{ max_per_keyword: 25 }, { max_per_keyword: 25, min_interval_s: 0 }]) {
      // The server can persist partial limits even though the client type requires all fields.
      const perChannel = { naver_blog: saved as Limits };
      const loaded = deriveCrawlLoad({ data: { crawlConfig: { channels: ['naver_blog'], perChannel } } }, initial, null, false);
      const expected = { concurrency: 1, min_interval_s: 0.5, max_per_keyword: 25, ...saved };
      expect(loaded.config.perChannel.naver_blog).toEqual(expected);
      expect(loaded.savedConfig?.perChannel.naver_blog).toEqual(expected);
      expect(perChannel.naver_blog).toEqual(saved);
    }
  });

  it('merges channel defaults into partial draft perChannel', () => {
    const base = deriveCrawlLoad({ data: {} }, initial, { channels: ['naver_blog'] }, false).config;
    for (const saved of [{ max_per_keyword: 25 }, { max_per_keyword: 25, min_interval_s: 0 }]) {
      const draft = { ...base, perChannel: { naver_blog: saved as Limits } };
      const loaded = deriveCrawlLoad({ data: { crawlConfig: base, drafts: { crawl: { config: draft } } } }, initial, null, false);
      expect(loaded.config.perChannel.naver_blog).toEqual({ concurrency: 1, min_interval_s: 0.5, max_per_keyword: 25, ...saved });
      expect(loaded.savedConfig?.perChannel.naver_blog).toEqual(base.perChannel.naver_blog);
      expect(draft.perChannel.naver_blog).toEqual(saved);
    }
  });

  it('trims all list entries and drops empty entries', () => {
    expect(parseList('  카페 , , 블로그, ')).toEqual(['카페', '블로그']);
    expect(parseList('')).toEqual([]);
    expect(parseList(' , \t, ')).toEqual([]);
  });
  it('prefills server defaults exactly, preserving order and duplicates', () => {
    const defaults = { adWords: ['중고', '판매', '거래', '협찬', '협찬'], excludeSources: ['장터'] };
    expect(prefillFilters(undefined, defaults)).toEqual(defaults);
    expect(prefillFilters({ adWords: [], excludeSources: [] }, defaults)).toEqual({ adWords: [], excludeSources: [] });
    expect(prefillFilters({ adWords: ['custom'] }, defaults)).toEqual({ adWords: ['custom'], excludeSources: ['장터'] });
  });
  it('only sends limits for enabled channels without mutating the input', () => {
    const config = { channels: ['fixture'], perChannel: { fixture: { concurrency: 1 }, youtube: { concurrency: 2 } } };
    expect(enabledChannelConfig(config)).toEqual({ channels: ['fixture'], perChannel: { fixture: { concurrency: 1 } } });
    expect(config.perChannel.youtube).toEqual({ concurrency: 2 });
  });
  it('shows connected fixture before selection and retains selected sources', () => {
    expect(settingsSources(['naver_blog', 'fixture'], [], ['fixture'])).toEqual(['naver_blog', 'fixture']);
    expect(settingsSources(['naver_blog', 'fixture'], [], [])).toEqual(['naver_blog']);
    expect(settingsSources(['naver_blog', 'fixture'], ['fixture'], [])).toEqual(['naver_blog', 'fixture']);
  });
});
