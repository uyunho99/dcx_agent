import { contextRequest } from './context';
import { versionQuery } from './errors';
import type { EvidenceLevel, LabelTags, LabelSubmission, LabelResult, Overview, LegacyOverview, QueueItem, ReviewMode, Worker } from '../types';
export type { Overview, QueueItem, LabelTags, LabelResult } from '../types';
const path = (sid: string, action: string, version?: string) => versionQuery(`/label/${encodeURIComponent(sid)}/${action}`,version);
export const setLabelMode = (sid: string, body: {mode: 'llm' | 'model'; modelId?: string | null}, version?: string) => contextRequest<typeof body>(path(sid,'mode',version),'POST',body);
export const startLabel = (sid: string, version?: string) => contextRequest<{started: boolean; workers: Record<string, Worker>}>(path(sid,'start',version),'POST');
export const controlLabeler = (sid: string, labeler: 'jev' | 'gpt', action: 'pause' | 'resume', version?: string) => contextRequest<Worker>(path(sid,`judge/${labeler}/${action}`,version),'POST');
export const getLabelOverview = (sid: string, version?: string) => contextRequest<Overview | LegacyOverview>(path(sid,'overview',version));
export function getNextLabel(sid: string, options: {mode?: ReviewMode; round?: number; after?: string; version?: string} = {}) {
 const query = new URLSearchParams();
 if(options.mode) query.set('mode',options.mode);
 if(options.round !== undefined) query.set('round',String(options.round));
 if(options.after !== undefined) query.set('after',options.after);
 if(options.version) query.set('version',options.version);
 return contextRequest<{item: QueueItem | null; message: string | null}>(`${path(sid,'next')}?${query}`);
}
// The screen calls this once after reading the overview on open, never on polling.
export const markLabelSeen = (sid: string, version?: string) => contextRequest<{lastSeenAt: string}>(path(sid,'seen',version),'POST');
export const previewLabelRule = (tags: LabelTags) => contextRequest<{level: EvidenceLevel}>('/label/rule/preview','POST',{tags});
export const submitLabel = (sid: string, body: LabelSubmission, version?: string) => contextRequest<LabelResult>(path(sid,'submit',version),'POST',body);
export const createAudit = (sid: string, version?: string) => contextRequest<{round: number | null}>(path(sid,'audit',version),'POST');
