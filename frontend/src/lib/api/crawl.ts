import { enabledChannelConfig } from '../logic/crawlConfig';
import { contextRequest } from './context';
export type Limits = {concurrency:number; min_interval_s:number; max_per_keyword:number; per_minute?:number};
export type CrawlConfig = {channels:string[]; dateFrom:string|null; dateTo:string|null; adWords:string[]; excludeSources:string[]; includeSources:string[]; product_name_filter:boolean; perChannel:Record<string,Limits>; youtube:{videos_per_keyword:number;max_comments:number}; target_total:number|null};
export type Cell = {docs?:number;doc_count?:number;urls_listed?:number;urls_done?:number;listed:number;filtered:number;unique:number; titles?:string[]; full?:number;snippet?:number;restricted?:number};
export type GateRow = {kw:string;axis:string;sub:string;per_source:Record<string,Cell>;listed:number;after_filter:number;unique_ratio:number;badges:string[]};
export type ChannelState = {status:string;attempts?:number;parse_errors?:number;blocked?:number};
export type CrawlStatus = {status:string;resumable?:boolean;remaining_by_channel?:Record<string,number>;paused_channels?:string[];collection_channels?:string[];min_interval_s?:Record<string,number>;reason?:string;paused_reason?:string;stopReason?:string;kind:'list'|'detail'|null;collectionId?:string;snapshot_id?:string|null;updatedAt?:string;progress:{done:number;target:number;full:number;snippet:number;restricted:number;per_minute:number;list_tasks:Record<string,{done:number;target:number}>;channels:Record<string,ChannelState>}|null;channels:Record<string,ChannelState>;gate:GateRow[]|null;estimate:{urls:number;minutes:number}|null;report:{matrix:Record<string,Record<string,Cell>>;channels:Record<string,{docs:number;share:number;status:string;errors_top:unknown[];skipped?:number;skip_reason?:string|null}>;totals:Record<string,number>}|null;defaults:Pick<CrawlConfig,'adWords'|'excludeSources'>;available_sources?:string[];added_keywords_count:number;collection_keywords:string[]};
export type CrawlSession = {stale?:Record<string,string>;collectionId?:string|null;projectContext?:{channels:string[]};crawlConfig?:(Partial<CrawlConfig>&{gateExclusions?:string[]})|null;drafts?:{crawl?:{config?:CrawlConfig|null;gate?:{exclusions:string[];snapshot_id:string}|null}};keywords?:{kw:string;axis:string;status:string}[];version?:string;readonly?:boolean};
const path = (sid:string, action:string, version?:string) => `/crawl/${encodeURIComponent(sid)}/${action}${version ? `?version=${encodeURIComponent(version)}` : ''}`;
export const getCrawlStatus = (sid:string) => contextRequest<CrawlStatus>(path(sid,'status'));
export const saveCrawlConfig = (sid:string, config:CrawlConfig, version?:string) => contextRequest<{crawlConfig:CrawlConfig}>(path(sid,'config',version),'PUT',enabledChannelConfig(config));
export const saveCrawlGate = (sid:string, exclusions:string[], version?:string) => contextRequest(path(sid,'gate',version),'PUT',{exclusions});
export const startCrawlList = (sid:string, added=false, version?:string) => contextRequest(path(sid,'list',version)+(added ? `${version ? '&' : '?'}mode=added-keywords` : ''),'POST');
export const startCrawlDetail = (sid:string, snapshot_id:string, version?:string) => contextRequest(path(sid,'detail',version),'POST',{snapshot_id});
export const resumeCrawl = (sid:string, version?:string, body?:{min_interval_s:Record<string,number>}) => contextRequest(path(sid,'resume',version),'POST',body);
export const setAutoChain = (sid:string, enabled:boolean) => contextRequest<{autoChain:boolean}>(path(sid,'auto-chain'),'PUT',{enabled});
export const finishPartialCrawl = (sid:string, version?:string) => contextRequest(path(sid,'finish-partial',version),'POST');
export const stopCrawl = (sid:string, version?:string) => contextRequest(path(sid,'stop',version),'POST');
export type Integration = {name:string;connected:boolean;affects:string[];env_vars:string[];last_error:string|null};
export async function getCrawlConnections():Promise<Integration[]> {
  try { const data = await contextRequest<Integration[]|{integrations:Integration[]}>('/integrations'); return Array.isArray(data) ? data : data.integrations ?? []; } catch { return []; }
}
