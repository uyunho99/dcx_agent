export function roundKeywords<T extends { round: number }>(all: T[], round: number, final: boolean): T[] {
  return final ? all : all.filter(k => k.round === round);
}
