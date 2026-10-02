import { contextRequest } from './context';
import { versionQuery } from './errors';
import type {
  InsightChatRequest, InsightChatResponse, InsightConfirmRequest, InsightConfirmResponse,
  InsightResponse, InsightRevertRequest, InsightRevertResponse, InsightRunRequest,
  InsightRunResponse, InsightSuggestedKnownRequest, InsightSuggestionsResponse, KnownInsight,
} from '../types';

const path = (sid: string, suffix: string, version?: string) => versionQuery(`/insight/${encodeURIComponent(sid)}${suffix}`, version);
const knownPath = (sid: string, suffix: string, version?: string) => versionQuery(`/known/${encodeURIComponent(sid)}${suffix}`, version);
export const startInsight = (sid: string, body: InsightRunRequest, version?: string) => contextRequest<InsightRunResponse>(path(sid, '/run', version), 'POST', body);
export const getInsights = (sid: string, version?: string) => contextRequest<InsightResponse>(path(sid, '', version));
export const createInsightConcept = (sid: string, id: string, version?: string) => contextRequest<InsightRunResponse>(path(sid, `/concept/${encodeURIComponent(id)}`, version), 'POST');
export const chatInsight = (sid: string, body: InsightChatRequest, version?: string) => contextRequest<InsightChatResponse>(path(sid, '/chat', version), 'POST', body);
export const revertInsight = (sid: string, body: InsightRevertRequest, version?: string) => contextRequest<InsightRevertResponse>(path(sid, '/revert', version), 'POST', body);
export const confirmInsights = (sid: string, body: InsightConfirmRequest, version?: string) => contextRequest<InsightConfirmResponse>(path(sid, '/confirm', version), 'PUT', body);
export const getKnownSuggestions = (sid: string, version?: string) => contextRequest<InsightSuggestionsResponse>(knownPath(sid, '/suggestions', version));
export const addSuggestedKnownInsight = (sid: string, body: InsightSuggestedKnownRequest, version?: string) => contextRequest<KnownInsight>(knownPath(sid, '', version), 'POST', { ...body, from: 'prev_session' });
