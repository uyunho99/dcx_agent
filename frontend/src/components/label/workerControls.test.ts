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

import { labelerView } from './labelerMode';
import { Overview } from './Overview';
import type { Overview as OverviewData } from '@/lib/api/label';
const summary = {n:0,fields:{},grade:{n:0,accuracy:null,kappa:null}};
const gptOnlyOverview: OverviewData = {
 started:false, mode:'llm', modelId:null, labelerMode:'gpt_only',
 progress:{gpt:{state:'none',pending:0}},
 definitionCheck:{needed:false,reason:null}, queue:{total:0,estimatedSeconds:0,byReason:{}},
 now:{state:'before_start'}, merged:0,total:0,accepted:0,escalated:0,mismatchRate:null,
 levelDistribution:{core:0,supporting:0,non:0},audit:[],
 labelerAccuracy:{jev:null,gpt:summary,n:0},selfConsistency:{...summary,accuracy:null,agree:null},
 changes:{judged:0,merged:0,accepted:0,queued:0},lastSeenAt:null,
};
it('shows the GPT-only notice and only the GPT worker in overview data', () => {
 const view = labelerView(gptOnlyOverview);
 expect(view.showNotice).toBe(true);
 expect(view.workers.map(([name]) => name)).toEqual(['gpt']);
 expect(labelerView({...gptOnlyOverview,progress:{...gptOnlyOverview.progress,jev:{state:'none',pending:0}}}).workers.map(([name]) => name)).toEqual(['gpt']);
});
it.each(['none','running','done'])('renders the accessible GPT-only notice before workers in state %s', state => {
 const overview = {...gptOnlyOverview,started:state !== 'none',progress:{gpt:{state,pending:0}}};
 const html = renderToStaticMarkup(createElement(Overview,{sid:'s',overview,onRefresh:()=>{},onNavigate:()=>{}}));
 expect(html).toContain('role="status"');
 expect(html).toContain('Jev 미연결 · GPT 단독 판정');
 expect(html.indexOf('Jev 미연결')).toBeLessThan(html.indexOf('전량 판정'));
 expect(html).toContain('md:grid-cols-1');
 expect(html).not.toContain('예상 Jev 비용');
 expect(html).not.toContain('gpt_only');
 expect(html).toContain('<dt>불일치율</dt><dd>—</dd>');
 expect(html).toContain('<td>표본 부족</td><td>—</td><td>표본 부족</td>');
});
it('preserves both workers and the cost caption for cross labeling', () => {
 const overview = {...gptOnlyOverview,labelerMode:'cross' as const,mismatchRate:.125,labelerAccuracy:{jev:summary,gpt:summary,n:0},progress:{jev:{state:'none',pending:0},gpt:{state:'none',pending:0}}};
 expect(labelerView(overview).showNotice).toBe(false);
 expect(labelerView(overview).workers.map(([name]) => name)).toEqual(['jev','gpt']);
 const html = renderToStaticMarkup(createElement(Overview,{sid:'s',overview,onRefresh:()=>{},onNavigate:()=>{}}));
 expect(html).not.toContain('Jev 미연결 · GPT 단독 판정');
 expect(html).toContain('md:grid-cols-2');
 expect(html).toContain('예상 Jev 비용');
 expect(html).toContain('<dt>불일치율</dt><dd>12.5%</dd>');
});

import { Audit } from './Audit';
it('renders audit accuracy safely when the Jev summary is null', () => {
 const html = renderToStaticMarkup(createElement(Audit,{sid:'s',overview:gptOnlyOverview,onRefresh:()=>{}}));
 expect(html).toContain('Jev 정확도');
 expect(html).toContain('<td>표본 부족</td><td>—</td><td>표본 부족</td>');
});
