import { describe, expect, it } from 'vitest';
import { parseList, prefillFilters, enabledChannelConfig, settingsSources } from './crawlConfig';

describe('crawl settings', () => {
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
