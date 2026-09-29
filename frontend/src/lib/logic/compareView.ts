import { subLabel } from '../../components/keywords/taxonomy';
import type { Axis } from '../api/keywords';
export type CompareKeyword = { id?: string; kw?: string; text?: string; axis?: string; sub?: string };
export type KeywordDiff = { added?: CompareKeyword[]; removed?: CompareKeyword[]; moved?: { id: string; kw?: string; from?: string; to?: string }[]; distribution?: Record<string, number> };
export const axisLabel = (axis?: string) => ({ physical: '물리', psychological: '심리', behavioral: '행동' }[axis ?? ''] ?? axis ?? '—');
const place = (k: CompareKeyword) => [axisLabel(k.axis), k.sub && (['physical','psychological','behavioral'].includes(k.axis ?? '') ? subLabel({axis:k.axis as Axis,sub:k.sub}) : k.sub)].filter(Boolean).join(' · ');
export function compareView(diff: KeywordDiff) {
  const rows = (['added', 'removed', 'moved'] as const).flatMap(kind => {
    if (kind === 'moved') return (diff.moved ?? []).map(k => ({ keyword: k.kw ?? k.id, before: axisLabel(k.from), after: axisLabel(k.to), badge: '축 이동', tone: 'neutral' as const, strike: false }));
    return (diff[kind] ?? []).map(k => ({ keyword: k.kw ?? k.text ?? k.id ?? '이름 없음', before: kind === 'added' ? '—' : place(k), after: kind === 'removed' ? '—' : place(k), badge: kind === 'added' ? '추가' : '삭제', tone: kind === 'added' ? 'success' as const : 'neutral' as const, strike: kind === 'removed' }));
  }).sort((a, b) => ['추가', '삭제', '축 이동'].indexOf(a.badge) - ['추가', '삭제', '축 이동'].indexOf(b.badge) || a.keyword.localeCompare(b.keyword, 'ko'));
  const order = ['physical', 'psychological', 'behavioral'];
  return { rows, counts: { added: diff.added?.length ?? 0, removed: diff.removed?.length ?? 0, moved: diff.moved?.length ?? 0 }, empty: rows.length ? null : '키워드 변경이 없습니다.', distribution: Object.entries(diff.distribution ?? {}).sort(([a], [b]) => (order.indexOf(a) < 0 ? 3 : order.indexOf(a)) - (order.indexOf(b) < 0 ? 3 : order.indexOf(b)) || a.localeCompare(b)).map(([axis, delta]) => ({ axis, label: axisLabel(axis), delta })) };
}

export function keywordSnapshotDiff(before: (CompareKeyword & {status?: string})[], after: (CompareKeyword & {status?: string})[]): KeywordDiff {
  const key = (k: CompareKeyword) => k.id ?? k.kw ?? k.text;
  const left = new Map(before.filter(k => k.status !== 'rejected').map(k => [key(k), k]));
  const right = new Map(after.filter(k => k.status !== 'rejected').map(k => [key(k), k]));
  const distribution: Record<string,number> = {};
  for (const [list, sign] of [[before,-1],[after,1]] as const) for (const k of list) if(k.status === 'approved' && k.axis) distribution[k.axis] = (distribution[k.axis] ?? 0) + sign;
  return {added: [...right].filter(([id])=>!left.has(id)).map(([,k])=>k), removed: [...left].filter(([id])=>!right.has(id)).map(([,k])=>k), moved: [...right].filter(([id,k])=>left.has(id)&&left.get(id)!.status === 'approved'&&k.status === 'approved'&&left.get(id)!.axis!==k.axis).map(([id,k])=>({id:id ?? '',kw:k.kw,from:left.get(id)!.axis,to:k.axis})), distribution};
}
