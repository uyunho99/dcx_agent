import type { InsightCxDimension, PersonaGrade, PersonaGradeLabel, PersonaSortDirection, PersonaZone } from '../../lib/types';

const gradeLabels: Record<PersonaGrade, PersonaGradeLabel> = {
  observed: { text: '관측', shape: 'circle' },
  inferred: { text: '추론', shape: 'triangle' },
  speculated: { text: '추측', shape: 'cross' },
};

export function gradeLabel(grade: PersonaGrade | null): PersonaGradeLabel {
  return grade === null ? { text: '근거 부족', shape: null } : { ...gradeLabels[grade] };
}

/** Fixed-capacity rows: 5–8 contexts use four columns; 9–10 use five. */
export function foldColumns(n: number): { rows: number; columns: number } {
  if (!Number.isInteger(n) || n < 0 || n > 10) throw new RangeError('Expected 0–10 contexts');
  return { rows: n <= 4 ? 1 : 2, columns: n <= 4 ? n : n <= 8 ? 4 : 5 };
}

type SortValue = string | number | boolean | null | undefined;
type SortKey<T> = { [K in keyof T]-?: T[K] extends SortValue ? K : never }[keyof T];
const missing = (value: unknown) => value == null || (typeof value === 'number' && !Number.isFinite(value));
const compare = (a: SortValue, b: SortValue) => a === b ? 0 : a! < b! ? -1 : 1;

/** Missing values stay last; ties use ascending context ID, then input order. */
export function sortContexts<T extends { context_id: string }>(rows: readonly T[], key: 'context_id' | SortKey<T>, dir: PersonaSortDirection): T[] {
  return rows.map((row, index) => ({ row, index })).sort((a, b) => {
    const left = a.row[key] as SortValue;
    const right = b.row[key] as SortValue;
    const leftMissing = missing(left);
    const rightMissing = missing(right);
    if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
    const order = leftMissing ? 0 : compare(left, right) * (dir === 'asc' ? 1 : -1);
    return order || compare(a.row.context_id, b.row.context_id) || a.index - b.index;
  }).map(({ row }) => row);
}

const zoneNames: Record<PersonaZone, string> = {
  A: 'Exciting', B: 'Experiencing', C: 'Competitive', D: 'Forgiven', E: 'Dangling', F: 'At-risk',
};
export const zoneName = (zone: PersonaZone): string => zoneNames[zone];

export function cxCounts(rows: readonly { cx_4d: InsightCxDimension }[]): Record<InsightCxDimension, number> {
  const counts: Record<InsightCxDimension, number> = { 정신적: 0, 물리적: 0, 문화적: 0, 시스템: 0 };
  for (const row of rows) counts[row.cx_4d] += 1;
  return counts;
}
