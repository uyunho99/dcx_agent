import { expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
vi.mock('next/navigation', () => ({usePathname: () => '/pipeline/preprocess'}));
vi.mock('@/components/DirtyProvider', () => ({useDirty: () => ({confirmNavigation: () => true})}));
import StepBar from './StepBar';
import { LabelerProgress } from './label/LabelerProgress';
import { embedderLabel, restartLabelNotice } from '@/lib/logic/browserQa';

it('highlights the viewed stage while retaining completed steps from session progress', () => {
 const html = renderToStaticMarkup(createElement(StepBar, {currentStep:'train-check'}));
 expect(html).toMatch(/aria-current="step"[^>]*href="\/pipeline\/preprocess"/);
 expect(html).not.toMatch(/aria-current="step"[^>]*href="\/pipeline\/training"/);
 expect(html).toContain('라벨링 완료');
});
it('shows idle workers as waiting without an indeterminate processing bar', () => {
 const html = renderToStaticMarkup(createElement(LabelerProgress, {name:'Jev',progress:{state:'none',pending:2000}}));
 expect(html).toContain('대기 중');
 expect(html).not.toContain('처리 중');
});
it('shows actual model worker done / total counts', () => {
 const html = renderToStaticMarkup(createElement(LabelerProgress, {name:'분류 모델',progress:{state:'running',done:750,total:2000,pending:1250,progress:.375}}));
 expect(html).toContain('750 / 2,000건 판정');
 expect(html).toContain('1,250건 남음');
});
it('formats real embedder identities and does not invent a missing backend', () => {
 expect(embedderLabel('fake')).toBe('가짜 임베더');
 expect(embedderLabel({name:'fake',model:'voyage-4',dim:1024})).toBe('가짜 임베더');
 expect(embedderLabel({name:'voyage',model:'voyage-4',dim:1024})).toBe('voyage-4 · 1024');
 expect(embedderLabel('voyage')).toBe('voyage-4 · 1024');
 expect(embedderLabel(undefined)).toBe('확인 불가');
});
it('uses the actual stage-four restart parent and the exact design wording', () => {
 expect(restartLabelNotice({restartFrom:'stage4',parentVersion:'v7'})).toBe('이 라벨은 v7 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.');
 expect(restartLabelNotice({restartFrom:'stage3',parentVersion:'v7'})).toBeNull();
 expect(restartLabelNotice({restartFrom:'stage4'})).toBeNull();
});

import { PrepResult } from './prep/PrepResult';
import { Tabs } from './ds/Tabs';
it('requires an explicit reuse signal, including when a completed result has no run ID', () => {
 const report = {original:1,after:1,removed:{},boilerplate_replaced:{},tokens_written:1,embedded:1,embed_failed_zero_vector:0,embedder:'fake'};
 const render = (reused?: boolean) => renderToStaticMarkup(createElement(PrepResult, {report,status:{status:'done',progress:1,runId:null,reused},busy:false,onNext:() => {}}));
 expect(render(false)).not.toContain('같은 규칙의 결과를 그대로 씁니다');
 expect(render()).not.toContain('같은 규칙의 결과를 그대로 씁니다');
 expect(render(true)).toContain('같은 규칙의 결과를 그대로 씁니다');
 expect(render(false)).toContain('가짜 임베더');
});
it('exposes labeling tabs with selected state and linked panels', () => {
 const html = renderToStaticMarkup(createElement(Tabs, {label:'라벨링',value:'overview',onChange:() => {},items:[{value:'overview',label:'개요',content:'개요 내용'},{value:'queue',label:'검수 큐',content:'큐'},{value:'audit',label:'감사',content:'감사 내용'}]}));
 expect(html).toContain('role="tablist"');
 expect(html.match(/role="tab"/g)).toHaveLength(3);
 expect(html.match(/aria-selected="true"/g)).toHaveLength(1);
 expect(html.match(/role="tabpanel"/g)).toHaveLength(3);
});
