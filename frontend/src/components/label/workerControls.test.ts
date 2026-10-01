import { expect, it } from 'vitest';
import { controlTarget, workerActions } from './workerControls';
it('maps only controllable workers to the judge endpoint', () => {
 expect(controlTarget('infer','model')).toBe('infer');
 expect(controlTarget('infer','llm')).toBeUndefined();
 expect(controlTarget('monitor','model')).toBeUndefined();
 expect(controlTarget('jev','llm')).toBe('jev');
 expect(controlTarget('gpt','llm')).toBe('gpt');
});
it('offers pause and stop while active, and resume after every interruption', () => {
 expect(workerActions('running')).toEqual(['pause','stop']);
 expect(workerActions('paused')).toEqual(['resume','stop']);
 for (const state of ['failed','interrupted','cancelled']) expect(workerActions(state)).toEqual(['resume']);
 for (const state of ['none','done']) expect(workerActions(state)).toEqual([]);
});

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { LabelerProgress } from './LabelerProgress';
it('renders actionable model controls and hides them for read-only workers', () => {
 const render = (state: string, writable = true) => renderToStaticMarkup(createElement(LabelerProgress, {name:'분류 모델',progress:{state,pending:3},onControl:writable ? () => {} : undefined}));
 expect(render('running')).toContain('일시 정지');
 expect(render('running')).toContain('중단');
 for (const state of ['paused','failed','interrupted','cancelled']) expect(render(state)).toContain('이어서 진행');
 expect(render('running',false)).not.toContain('<button');
 expect(render('done')).not.toContain('<button');
});
