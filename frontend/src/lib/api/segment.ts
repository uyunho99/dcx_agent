import { contextRequest } from './context';
import { versionQuery } from './errors';
import type {
  SegmentStatus, SegmentRunRequest, SegmentClustersResponse, SegmentPersonasResponse, SegmentContextsResponse,
  SegmentCluster, SegmentPersona, SegmentContext, SegmentConfirmation, SegmentPersonaConfirmation,
  SegmentContextConfirmation, SegmentBulkConfirmation, SegmentBulkResponse, SegmentRequest, SegmentRequestMemo,
  SegmentDocsOptions, SegmentDocsResponse,
} from '../types';

const path = (sid: string, suffix: string, version?: string) => versionQuery(`/segment/${encodeURIComponent(sid)}${suffix}`, version);
export const startSegment = (sid: string, body: SegmentRunRequest = {}, version?: string) => contextRequest<{runId: string}>(path(sid, '/run', version), 'POST', body);
export const getSegmentStatus = (sid: string, version?: string) => contextRequest<SegmentStatus>(path(sid, '/status', version));
export const getSegmentClusters = (sid: string, version?: string) => contextRequest<SegmentClustersResponse>(path(sid, '/clusters', version));
const filterQuery = (key: string, value?: string) => value === undefined ? '' : `?${key}=${encodeURIComponent(value)}`;
export const getSegmentPersonas = (sid: string, cluster?: string, version?: string) => contextRequest<SegmentPersonasResponse>(path(sid, `/personas${filterQuery('cluster', cluster)}`, version));
export const getSegmentContexts = (sid: string, persona?: string, version?: string) => contextRequest<SegmentContextsResponse>(path(sid, `/contexts${filterQuery('persona', persona)}`, version));
export const confirmSegmentCluster = (sid: string, id: string, body: SegmentConfirmation, version?: string) => contextRequest<SegmentCluster>(path(sid, `/clusters/${encodeURIComponent(id)}`, version), 'PUT', body);
export const confirmSegmentPersona = (sid: string, id: string, body: SegmentPersonaConfirmation, version?: string) => contextRequest<SegmentPersona>(path(sid, `/personas/${encodeURIComponent(id)}`, version), 'PUT', body);
export const confirmSegmentContext = (sid: string, id: string, body: SegmentContextConfirmation, version?: string) => contextRequest<SegmentContext>(path(sid, `/contexts/${encodeURIComponent(id)}`, version), 'PUT', body);
export const confirmSegmentContexts = (sid: string, id: string, body: SegmentBulkConfirmation, version?: string) => contextRequest<SegmentBulkResponse>(path(sid, `/personas/${encodeURIComponent(id)}/confirm-contexts`, version), 'POST', body);
export const createSegmentRequest = (sid: string, body: SegmentRequest, version?: string) => contextRequest<SegmentRequestMemo>(path(sid, '/requests', version), 'POST', body);
export function getSegmentDocs(sid: string, options: SegmentDocsOptions = {}, version?: string) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options)) if (value !== undefined) query.set(key, String(value));
  return contextRequest<SegmentDocsResponse>(path(sid, `/docs${query.size ? `?${query}` : ''}`, version));
}
