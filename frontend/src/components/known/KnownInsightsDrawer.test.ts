import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { KnownInsight } from '@/lib/types';
import { KnownInsightCard } from './KnownInsightsDrawer';

const item: KnownInsight = {
 id: 'known-1', type: 'doc', text: '긴 근거 원문 내용', doc_id: 'doc-1',
 from: 'rag', createdAt: '2026-10-01T00:00:00Z', vectorRow: null, warning: null,
};
function render(overrides: Partial<KnownInsight> = {}, disabled = false) {
 return renderToStaticMarkup(createElement(KnownInsightCard, {item: {...item, ...overrides}, disabled, onDelete: () => {}}));
}

it('gives documents an initially collapsed disclosure linked to their body', () => {
 const html = render();
 const bodyId = html.match(/<p id="([^"]+)"/)?.[1];
 expect(bodyId).toBeTruthy();
 expect(html).toContain('aria-expanded="false"');
 expect(html).toContain(`aria-controls="${bodyId}"`);
 expect(html).toContain('>펼치기</button>');
 expect(html).toContain(item.text);
});

it('leaves statements fully readable without a disclosure', () => {
 const html = render({type: 'statement', from: 'drawer'});
 expect(html).toContain('문장</span>');
 expect(html).toContain('직접 입력</span>');
 expect(html).not.toContain('aria-expanded');
});

it('places the caption date before a small quiet delete action in the footer', () => {
 const footer = render().match(/<footer[\s\S]*<\/footer>/)?.[0];
 expect(footer).toMatch(/<time class="ds-t-caption" dateTime="2026-10-01T00:00:00Z">[^<]+<\/time><button/);
 expect(footer).toContain('ds-quiet ds-sm');
 expect(footer).toContain(`aria-label="${item.text} 삭제"`);
});

it('disables deletion while retaining document disclosure and warning announcements', () => {
 const html = render({text: '', warning: 'pending'}, true);
 expect(html).toMatch(/<button[^>]*aria-label="근거 원문 삭제"[^>]*disabled=""/);
 expect(html).toMatch(/<button(?![^>]*disabled)[^>]*aria-expanded="false"[^>]*>펼치기<\/button>/);
 expect(html).toContain('role="status"');
});
