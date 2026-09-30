import { describe, expect, it } from 'vitest';
import { compareView } from './compareView';

describe('compareView', () => {
  it('orders added, removed, moved rows then keywords without mutating input', () => {
    const diff = { added: [{ id: 'z', kw: 'z', axis: 'physical' }, { id: 'a', kw: 'a', axis: 'behavioral' }], removed: [{ id: 'r', kw: 'r', axis: 'physical' }], moved: [{ id: 'm', from: 'physical', to: 'behavioral' }], distribution: { physical: -2, behavioral: 2 } };
    expect(compareView(diff).rows.map(r => r.keyword)).toEqual(['a', 'z', 'r', 'm']);
    expect(diff.added[0].kw).toBe('z');
    expect(compareView(diff).distribution.map(d => d.axis)).toEqual(['physical', 'behavioral']);
  });
  it('maps badges, before/after axes and removed styling', () => {
    const view = compareView({ added: [{ kw: '추가', axis: 'physical', sub: '감각' }], removed: [{ kw: '삭제', axis: 'psychological' }], moved: [{ id: '이동', from: 'physical', to: 'behavioral' }], distribution: {} });
    expect(view.rows.map(r => [r.badge, r.tone, r.strike])).toEqual([['추가', 'success', false], ['삭제', 'neutral', true], ['축 이동', 'neutral', false]]);
    expect(view.rows[0].before).toBe('—');
    expect(view.rows[0].after).toBe('물리 · 감각');
    expect(view.rows[2].after).toBe('행동');
    expect(view.counts).toEqual({ added: 1, removed: 1, moved: 1 });
  });
  it('provides an explicit empty state', () => {
    expect(compareView({}).empty).toBe('키워드 변경이 없습니다.');
    expect(compareView({}).rows).toEqual([]);
    expect(compareView({}).distribution).toEqual([]);
  });
});
