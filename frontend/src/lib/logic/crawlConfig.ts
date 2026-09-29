import type { CrawlConfig } from '../api/crawl';

export const parseList = (value: string): string[] => value.split(',').map(s => s.trim()).filter(Boolean);

type Filters = Pick<CrawlConfig, 'adWords' | 'excludeSources'>;
export function prefillFilters(saved: Partial<Filters> | undefined, defaults: Filters): Filters {
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
