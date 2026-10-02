import { ApiError, displayError } from '@/lib/api/errors';
import type * as client from '@/lib/api/insight';
import type { InsightResponse, InsightTarget } from '@/lib/types';
export const CHAT_FAILURE = '요청을 반영하지 못했습니다. 다르게 말해 주세요.';
type Api = Pick<typeof client, 'chatInsight' | 'getInsights' | 'revertInsight' | 'confirmInsights'>;
export function createInsightActions(sid: string, version: string | undefined, api: Api, publish: (data: InsightResponse) => void, confirmed: (ids: string[]) => void) {
 const reload = async () => {const result = await api.getInsights(sid, version); publish(result); confirmed(result.confirmed ?? []);};
 return {
  async chat(target: InsightTarget, message: string) {
   try { const result = await api.chatInsight(sid,{target,message},version); if (!result.ok) return CHAT_FAILURE; await reload(); return `판 ${result.revision}에 반영했습니다.`; } catch (cause) { return cause instanceof ApiError && cause.kind === 'stale' ? displayError(cause) : CHAT_FAILURE; }
  },
  async revert(target: InsightTarget, revision: number) { await api.revertInsight(sid,{target,revision},version); await reload(); },
  async confirm(ids: string[]) { const result = await api.confirmInsights(sid,{ids},version); confirmed(result.confirmed); },
 };
}
