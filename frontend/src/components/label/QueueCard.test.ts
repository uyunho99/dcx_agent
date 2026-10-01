import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { QueueCard } from './QueueCard';
import type { SourceDocument } from '@/lib/types';

function render(document: SourceDocument | null) {
 return renderToStaticMarkup(createElement(QueueCard, {sid:'s',labeler:'human',item:{doc_id:'d',document},onNext:()=>{}}));
}
it('shows the title above the body as separate elements', () => {
 const html=render({doc_id:'d',title:'에어컨 설치 후 밤에 생긴 소음',body:'이것 때문에 잠을 못 자서 결국 껐어요.'});
 expect(html).toContain('에어컨 설치 후 밤에 생긴 소음</h3>');
 expect(html).toContain('이것 때문에 잠을 못 자서 결국 껐어요.</p>');
 expect(html.indexOf('에어컨 설치')).toBeLessThan(html.indexOf('이것 때문에'));
});
it('keeps text/body/content fallbacks without a title', () => {
 for(const field of ['text','body','content']) expect(render({doc_id:'d',[field]:'원문 내용'})).toContain('원문 내용</p>');
 expect(render(null)).toContain('원문을 찾지 못했습니다. 다음 문서를 확인하세요.');
});
it('shows a title-only document once without a missing-source warning', () => {
 const html=render({doc_id:'d',title:'제목만 있는 문서'});
 expect(html.split('제목만 있는 문서')).toHaveLength(2);
 expect(html).not.toContain('원문을 찾지 못했습니다.');
});
it('groups the controls into four labeled rows and preserves shortcuts and live feedback', () => {
 const html=render({doc_id:'d',text:'원문'});
 for(const label of ['대상 경험','경험 6차원','상황','신호 · Non 사유']) {
  expect(html).toContain(`role="group" aria-label="${label}"`);
 }
 expect(html.match(/aria-pressed="false"/g)).toHaveLength(8);
 for(const shortcut of ['A','1','2','3','4','5','6','S']) {
  expect(html).toContain(`<kbd>${shortcut} </kbd>`);
 }
 expect(html).toContain('aria-live="polite"');
});
it('keeps both selects labeled and disables Non reason while the level is pending', () => {
 const html=render({doc_id:'d',text:'원문'});
 for(const label of ['신호','Non 사유']) {
  const id=html.match(new RegExp(`<label for="([^"]+)">${label}</label>`))?.[1];
  expect(id).toBeTruthy();
  expect(html).toContain(`id="${id}"`);
 }
 const selects=html.match(/<select\b[^>]*>/g);
 expect(selects).toHaveLength(2);
 expect(selects?.[0]).not.toContain('disabled');
 expect(selects?.[1]).toContain('disabled');
});
