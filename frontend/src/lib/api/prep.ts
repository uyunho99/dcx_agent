import { contextRequest } from './context';
import { versionQuery } from './errors';
import type { PrepConfig, PrepStatus } from '../types';
export type { PrepConfig, PrepStatus } from '../types';
const path = (sid: string, action: string, version?: string) => versionQuery(`/prep/${encodeURIComponent(sid)}/${action}`, version);
export const savePrepConfig = (sid: string, config: PrepConfig, version?: string) => contextRequest<{status: 'ok'; prep: Record<string, unknown>}>(path(sid,'config',version), 'PUT', config);
export const runPrep = (sid: string, version?: string) => contextRequest<PrepStatus>(path(sid,'run',version), 'POST');
export const getPrepStatus = (sid: string, version?: string) => contextRequest<PrepStatus>(path(sid,'status',version));
