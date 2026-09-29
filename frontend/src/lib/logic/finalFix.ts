export const allowNavigation = (dirty: boolean, confirm: (message: string) => boolean) => !dirty || confirm('저장되지 않은 변경이 있습니다. 이동할까요?');
export const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
export const crawlNeedsSetup = (session: {stale?: Record<string,string>; collectionId?: string | null}, restartFrom?: string) => restartFrom === 'stage2' || !!session.stale?.stage2;
export const availableChannels = (selected: string[], available: string[] | undefined, internal: boolean) => selected.filter(s => (internal || s !== 'fixture') && (available === undefined || available.includes(s)));
export const documentCount = (cell: {docs?: number; doc_count?: number; full?: number; snippet?: number}) => cell.docs ?? cell.doc_count ?? (cell.full ?? 0) + (cell.snippet ?? 0);

export const crawlStartLabel = (freshSetup: boolean) => freshSetup ? '새 수집 시작' : '목록 수집 시작';
export function increasedResumeIntervals(paused: string[], status: {collection_channels?: string[]; min_interval_s?: Record<string,number>}, config: {perChannel: Record<string,{min_interval_s:number}>}) {
  const sources = paused.length ? paused : status.collection_channels ?? [];
  return Object.fromEntries(sources.map(source => [source, Math.max(1, (status.min_interval_s?.[source] ?? config.perChannel[source]?.min_interval_s ?? 0) * 2)]));
}
