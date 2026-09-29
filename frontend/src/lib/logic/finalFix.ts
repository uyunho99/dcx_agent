export const allowNavigation = (dirty: boolean, confirm: (message: string) => boolean) => !dirty || confirm('저장되지 않은 변경이 있습니다. 이동할까요?');
export const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
export const crawlNeedsSetup = (session: {stale?: Record<string,string>; collectionId?: string | null}, restartFrom?: string) => !session.collectionId || (!!session.stale?.stage2 && (restartFrom === undefined || restartFrom === 'stage2'));
export const availableChannels = (selected: string[], available: string[] | undefined, internal: boolean) => selected.filter(s => (internal || s !== 'fixture') && (available === undefined || available.includes(s)));
export const documentCount = (cell: {docs?: number; doc_count?: number; full?: number; snippet?: number}) => cell.docs ?? cell.doc_count ?? (cell.full ?? 0) + (cell.snippet ?? 0);
