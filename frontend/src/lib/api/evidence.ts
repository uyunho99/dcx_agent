import { contextRequest } from './context';
import { versionQuery } from './errors';
import type {
  EvidenceContextResponse, EvidenceGenerationRequest, EvidencePackage, EvidencePersonaResponse,
  EvidenceRunRequest, EvidenceRunResponse, EvidenceStatus, EvidenceTab,
} from '../types';

const path = (sid: string, suffix: string, version?: string) => versionQuery(`/evidence/${encodeURIComponent(sid)}${suffix}`, version);
const contextPath = (id: string) => `/contexts/${encodeURIComponent(id)}`;

export const startEvidence = (sid: string, body: EvidenceRunRequest = {}, version?: string) => contextRequest<EvidenceRunResponse>(path(sid, '/run', version), 'POST', body);
// Preserve stage7 report keys and quoteSource/noveltyShown wire fields (D-266).
export const getEvidenceStatus = (sid: string, version?: string) => contextRequest<EvidenceStatus>(path(sid, '/status', version));
export const getEvidenceContext = (sid: string, id: string, tab: EvidenceTab = 'all', version?: string) => contextRequest<EvidenceContextResponse>(path(sid, `${contextPath(id)}?tab=${encodeURIComponent(tab)}`, version));
export const getEvidencePersona = (sid: string, id: string, version?: string) => contextRequest<EvidencePersonaResponse>(path(sid, `/personas/${encodeURIComponent(id)}`, version));
export const refreshEvidenceNew = (sid: string, id: string, body: EvidenceGenerationRequest, version?: string) => contextRequest<EvidenceContextResponse>(path(sid, `${contextPath(id)}/refresh-new`, version), 'POST', body);
export const getEvidencePackage = (sid: string, version?: string) => contextRequest<EvidencePackage>(path(sid, '/package', version));
export const skipEvidenceContext = (sid: string, id: string, body: EvidenceGenerationRequest, version?: string) => contextRequest<EvidenceStatus>(path(sid, `${contextPath(id)}/skip`, version), 'POST', body);
