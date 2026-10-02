import type { Keyword } from '@/lib/api/keywords';

type KeywordText = Pick<Keyword, 'kw' | 'display'>;

export function keywordLabel(k: KeywordText): string {
  return k.display?.trim() || k.kw;
}

export function keywordTitle(k: KeywordText): string | undefined {
  return k.kw !== keywordLabel(k) ? k.kw : undefined;
}
