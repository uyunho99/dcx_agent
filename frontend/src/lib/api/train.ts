import { contextRequest } from './context';
import { versionQuery } from './errors';
import type { Worker, ModelMetadata, TrainingStatus } from '../types';
const path = (sid: string, suffix = '', version?: string) => versionQuery(`/train/${encodeURIComponent(sid)}${suffix}`,version);
export const startTraining = (sid: string, parent: string | null = null, version?: string) => contextRequest<Worker>(path(sid,'',version),'POST',{parent});
export const getTrainingStatus = (sid: string, version?: string) => contextRequest<TrainingStatus>(path(sid,'/status',version));
export const exportTraining = (sid: string, withoutModel = false, version?: string, partial = false) => contextRequest<{exportRef: string; allRef: string; total: number; relevant: number; stage5: Record<string, unknown>}>(path(sid,'/export',version),'POST',partial ? {withoutModel, partial} : {withoutModel});
export const getModels = (sid?: string, version?: string) => contextRequest<{models: ModelMetadata[]}>(versionQuery(`/models${sid ? `?sid=${encodeURIComponent(sid)}` : ''}`,version));
export const getModel = (id: string) => contextRequest<ModelMetadata>(`/models/${encodeURIComponent(id)}`);
