import { Children, createElement, isValidElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({cursor: 0, stage: 'stage6', diff: {} as unknown, content: null as ReactNode}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useState: () => [[ 'stage3', state.stage, {key:`s:v1:v2:${state.stage}`, data:state.diff, session:{}}, '', 0 ][state.cursor++], vi.fn()],
}));
vi.mock('@/components/ds', async () => {
 const actual = await vi.importActual<typeof import('@/components/ds')>('@/components/ds');
 return {...actual, Tabs: (props: Parameters<typeof actual.Tabs>[0]) => {
  state.content = props.items.find(item => item.value === props.value)?.content;
  return createElement(actual.Tabs, props);
 }};
});
vi.mock('next/navigation', () => ({useSearchParams: () => new URLSearchParams('a=v1&b=v2')}));
vi.mock('@/components/versions/VersionProvider', () => ({useVersion: () => ({sid:'s', meta:{versions:[{id:'v1'},{id:'v2'}]}})}));
vi.mock('@/components/versions/StageVersion', () => ({RestartVersion:()=>null, StaleBanner:()=>null}));
vi.mock('@/components/versions/VersionPicker', () => ({VersionHistory:()=>null}));
import Page from './page';
function renderComparison(stage: string, diff: unknown) {
 state.stage = stage;
 state.diff = diff;
 state.cursor = 0;
 // Render inside Suspense so a renderer error is not hidden by its fallback.
 return renderToStaticMarkup(Page().props.children);
}
it('renders stage-six report availability and saved names, desire, goals, action and confirmation counts', () => {
 const empty = {report:null, clusters:{total:0,confirmed:0,items:[]}, personas:{total:0,confirmed:0,items:[]}, contexts:{total:0,confirmed:0,items:[]}};
 const html = renderComparison('stage6', {same:false,before:empty,after:{...empty,report:{k:5,dims:{act_unknown:2}},
 clusters:{total:1,confirmed:1,items:[{cluster_id:'CL0',name:'Bedroom',confirmed:true}]},
 personas:{total:1,confirmed:1,items:[{persona_id:'P0',name:'Sleeper',desire:'Rest',goals:['Sleep'],confirmed:true}]},
 contexts:{total:1,confirmed:1,items:[{context_id:'C0',name:'Night',action:'Reserve',confirmed:true}]}}});
 for (const text of ['Bedroom','Sleeper','Rest','Sleep','Night','Reserve','1/1','저장된 보고서 없음']) expect(html).toContain(text);
 expect(html).not.toContain('Invalid Date');
});
it('renders stage-three metrics from the union of keys across result entries', () => {
 const html = renderComparison('stage3', {same:false,
  stage_3:{before:{documents:12, removed:2, missing:null},after:{documents:9, added:3}},
  extra:{before:{score:0},after:{score:1}},
 });
 expect(html).toContain('결과가 다릅니다.');
 expect(html).toContain('<th>항목</th><th>v1</th><th>v2</th>');
 for (const cells of [
  '<td>documents</td><td>12</td><td>9</td>',
  '<td>removed</td><td>2</td><td>—</td>',
  '<td>added</td><td>—</td><td>3</td>',
  '<td>missing</td><td>—</td><td>—</td>',
  '<td>score</td><td>0</td><td>1</td>',
 ]) expect(html).toContain(cells);
});
it.each(['stage4', 'stage5'])('renders %s metrics with a null before value', stage => {
 const html = renderComparison(stage, {same:false,stage_5:{before:null,after:{accuracy:0.9}}});
 expect(html).toContain('<td>accuracy</td><td>—</td><td>0.9</td>');
});
it.each([{before:null,after:null}, {}])('renders missing saved metrics for %j', entry => {
 const html = renderComparison('stage3', {same:true,stage_3:entry});
 expect(html).toContain('결과가 같습니다.');
 expect(html).toContain('저장된 결과가 없습니다.');
});
it('keeps file-shaped stage-seven results in FileComparison', () => {
 const html = renderComparison('stage7', {same:true,before:{},after:{}});
 expect(html).toContain('결과 파일이 같습니다.');
});
it.each(['before', 'after'] as const)('makes FileComparison safe when %s is null', side => {
 renderComparison('stage7', {same:true,before:{},after:{}});
 // Capture the routed renderer to exercise its defensive handling directly.
 if (!isValidElement<{children: ReactNode}>(state.content)) throw new Error('Missing tab content');
 const comparison = Children.toArray(state.content.props.children).find(child => isValidElement(child) && typeof child.type === 'function');
 if (!isValidElement<{diff: unknown}>(comparison)) throw new Error('Missing comparison renderer');
 const diff = {same:false,before:{report:{savedAt:1}},after:{report:{savedAt:2}},[side]:null};
 const html = renderToStaticMarkup(createElement(comparison.type, {diff}));
 expect(html).toContain('결과 파일이 다릅니다.');
 expect(html).toContain('<td>—</td>');
});
