import { describe, expect, it } from 'vitest';
import { previewText, sourceSorts } from './SourceBrowser';

describe('SourceBrowser', () => {
  it('truncates long bodies to 300 characters until expanded', () => {
    const doc = { title: '제목', body: '가'.repeat(400) };
    expect(previewText(doc, false)).toBe(`${'가'.repeat(300)}…`);
    expect(previewText(doc, true)).toBe('가'.repeat(400));
    expect(previewText({ title: '제목', body: '' }, false)).toBe('제목');
  });
  it('offers centre-first and edge-first ordering', () => {
    expect(sourceSorts.map(([key]) => key)).toEqual(['center', 'edge']);
  });
});
