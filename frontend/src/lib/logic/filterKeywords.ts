export const keywordFilters = ['전체', '판단 필요', 'LLM 단독', '검색량 적음', '미연결', '거절됨', '수동'] as const;
export type KeywordFilter = typeof keywordFilters[number];
type Filterable = { kw: string; badges?: string[]; status?: string; origin?: string; volume?: { source?: string } | null };
export function filterKeywords<T extends Filterable>(kws: readonly T[], filter: KeywordFilter = '판단 필요', query = ''): T[] {
  const search = query.trim().toLocaleLowerCase();
  return kws.filter(k => {
    const badges = k.badges ?? [];
    const match = filter === '전체' || (filter === '판단 필요' && badges.some(b => ['llm_only', 'low_volume', 'misclassified_suspect', 'misclassified-suspect', 'misclassified'].includes(b)))
      || (filter === 'LLM 단독' && badges.includes('llm_only')) || (filter === '검색량 적음' && badges.includes('low_volume'))
      || (filter === '미연결' && (badges.includes('unconnected') || k.volume?.source === 'unconnected'))
      || (filter === '거절됨' && k.status === 'rejected') || (filter === '수동' && k.origin === 'manual');
    return match && k.kw.toLocaleLowerCase().includes(search);
  });
}
