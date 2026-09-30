import { reconcileGateSelection } from './qaFix';
import { availableChannels, localDate } from './finalFix';
import type { CrawlConfig, CrawlSession, CrawlStatus, Limits } from '../api/crawl';

export const parseList = (value: string): string[] => value.split(',').map(s => s.trim()).filter(Boolean);

type Filters = Pick<CrawlConfig, 'adWords' | 'excludeSources'>;
export function prefillFilters(saved: Partial<Filters> | null | undefined, defaults: Filters): Filters {
  return {
    adWords: [...(saved?.adWords ?? defaults.adWords)],
    excludeSources: [...(saved?.excludeSources ?? defaults.excludeSources)],
  };
}

export function enabledChannelConfig<T extends { channels: string[]; perChannel: Record<string, unknown> }>(config: T): T {
  return { ...config, perChannel: Object.fromEntries(Object.entries(config.perChannel).filter(([source]) => config.channels.includes(source))) };
}

export function settingsSources(known: string[], selected: string[], available: string[]): string[] {
  return [...new Set([...known.filter(source => source !== 'fixture' || available.includes(source)), ...available, ...selected])];
}

export const limits = (source:string):Limits => ({concurrency:source === 'youtube' ? 2 : ['ppomppu','clien','naver_blog','naver_cafe'].includes(source) ? 1 : 4,min_interval_s:['ppomppu','clien','naver_blog','naver_cafe'].includes(source) ? 1 : 0,max_per_keyword:1000});

export function deriveCrawlLoad(result: {data: CrawlSession}, initial: Pick<CrawlStatus, 'defaults' | 'available_sources' | 'snapshot_id' | 'collectionId'> & {gate: {kw: string}[] | null}, context: {channels: string[]} | null, internal: boolean, now = new Date()) {
  const data = result.data;
  const raw = data.crawlConfig;
  const from = new Date(now);
  from.setDate(from.getDate() - 365);
  const channels = availableChannels(raw?.channels ?? data.projectContext?.channels ?? context?.channels ?? ['naver_cafe', 'naver_blog'], initial.available_sources, internal);
  const base: CrawlConfig = {
    channels,
    dateFrom: raw?.dateFrom === undefined ? localDate(from) : raw.dateFrom,
    dateTo: raw?.dateTo === undefined ? localDate(now) : raw.dateTo,
    ...prefillFilters(raw, initial.defaults),
    includeSources: raw?.includeSources ?? [],
    product_name_filter: raw?.product_name_filter ?? false,
    perChannel: raw?.perChannel ?? Object.fromEntries(channels.map(source => [source, limits(source)])),
    youtube: raw?.youtube ?? {videos_per_keyword: 20, max_comments: 500},
    target_total: raw?.target_total === undefined ? 1000000 : raw.target_total,
  };
  const draft = data.drafts?.crawl;
  const {saved: gate, excluded: selection} = reconcileGateSelection(null, initial, raw?.gateExclusions ?? [], draft?.gate);
  const config = draft?.config
    ? {...draft.config, channels: availableChannels(draft.config.channels, initial.available_sources, internal)} : base;
  return {
    data, config, savedConfig: raw?.channels ? {...base, channels: raw.channels} : null,
    gate, selection, keywords: approvedCrawlKeywords(data),
  };
}

export const approvedCrawlKeywords = (session: CrawlSession | null) => (session?.keywords ?? []).filter(k => k.status === 'approved');
