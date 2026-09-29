import type { KeywordState } from '../api/keywords';
import { roundUi } from './roundUi';

export function reviewKeywords(data: Pick<KeywordState, 'keywordRounds' | 'keywords'>) {
  const rounds = Object.values(data.keywordRounds);
  const available = (r: typeof rounds[number]) => roundUi({ round: r.round, status: r.job.status, gen: r.gen, jobGen: r.job.gen }).canEdit;
  const staleIds = new Set(rounds.filter(r => !available(r)).flatMap(r => r.keywords.map(k => k.id)));
  return [...new Map([...rounds.filter(available).flatMap(r => r.keywords), ...data.keywords]
    .filter(k => !staleIds.has(k.id)).map(k => [k.id, k])).values()];
}
