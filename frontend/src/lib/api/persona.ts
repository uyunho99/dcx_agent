import { contextRequest } from './context';
import { versionQuery } from './errors';
import type {
  PersonaCard, PersonaCardsResponse, PersonaMap, PersonaRetryRequest,
  PersonaRunRequest, PersonaRunResponse, PersonaStatus, PersonaTree,
} from '../types';

const path = (sid: string, suffix: string, version?: string) => versionQuery(`/persona/${encodeURIComponent(sid)}${suffix}`, version);
export const startPersona = (sid: string, body: PersonaRunRequest = {}, version?: string) => contextRequest<PersonaRunResponse>(path(sid, '/run', version), 'POST', body);
export const getPersonaStatus = (sid: string, version?: string) => contextRequest<PersonaStatus>(path(sid, '/status', version));
export const getPersonaCards = (sid: string, version?: string) => contextRequest<PersonaCardsResponse>(path(sid, '/cards', version));
export const getPersonaCard = (sid: string, id: string, version?: string) => contextRequest<PersonaCard>(path(sid, `/cards/${encodeURIComponent(id)}`, version));
export const retryPersonaCard = (sid: string, id: string, body: PersonaRetryRequest, version?: string) => contextRequest<PersonaStatus>(path(sid, `/cards/${encodeURIComponent(id)}/retry`, version), 'POST', body);
export const getPersonaMap = (sid: string, version?: string) => contextRequest<PersonaMap>(path(sid, '/map', version));
export const getPersonaTree = (sid: string, version?: string) => contextRequest<PersonaTree>(path(sid, '/tree', version));
