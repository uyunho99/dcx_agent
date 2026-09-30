import { contextRequest } from './context';
import { versionQuery } from './errors';
import type { KnownInsight } from '../types';
const path = (sid: string, id?: string, version?: string) => versionQuery(`/known/${encodeURIComponent(sid)}${id ? `/${encodeURIComponent(id)}` : ''}`,version);
export const getKnownInsights = (sid: string) => contextRequest<{items: KnownInsight[]}>(path(sid));
export const addKnownInsight = (sid: string, body: {type: 'statement'; text: string} | {type: 'doc'; doc_id: string}, version?: string) => contextRequest<KnownInsight>(path(sid,undefined,version),'POST',body);
export const updateKnownInsight = (sid: string, id: string, text: string, version?: string) => contextRequest<KnownInsight>(path(sid,id,version),'PATCH',{text});
export const deleteKnownInsight = (sid: string, id: string, version?: string) => contextRequest<{status: 'ok'}>(path(sid,id,version),'DELETE');
