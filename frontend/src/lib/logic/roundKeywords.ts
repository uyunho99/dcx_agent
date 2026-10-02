export function roundKeywords<T extends { round: number; status: string }>(all: T[], round: number, final: boolean): T[] {
  return final ? all : all.filter(k => k.round === round || (k.round < round && k.status !== 'rejected'));
}

export function roundTag(keywordRound: number, currentRound: number | undefined): string | undefined {
  return currentRound !== undefined && keywordRound !== currentRound ? `R${keywordRound}` : undefined;
}
