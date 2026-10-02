import { createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
import { GradeMark } from './GradeMark';
import { ProvisionalBadge } from './ProvisionalBadge';
import { CCMTable, type CCMContext } from './CCMTable';
import { OpportunityMap } from './OpportunityMap';
import { ContextTable } from './ContextTable';
import { HierarchyTree } from './HierarchyTree';
import { Radar } from './Radar';
import { OpportunityBars } from './OpportunityBars';
import { JourneyTable } from './JourneyTable';
import { RevisionList } from './RevisionList';
import type { PersonaContextRow, PersonaMap } from '../../lib/types';

// Node-only interaction harness, matching segment's direct element-handler tests.
const state = vi.hoisted(() => ({ values: [] as unknown[], cursor: 0 }));
vi.mock('react', async importOriginal => ({ ...await importOriginal<typeof import('react')>(), useId: () => 'test-id', useState: (initial: unknown) => {
  const index = state.cursor++;
  if (!(index in state.values)) state.values[index] = initial;
  return [state.values[index], (next: unknown) => { state.values[index] = typeof next === 'function' ? next(state.values[index]) : next; }];
} }));
function draw<T>(component: (props: T) => ReactElement, props: T, reset = true) {
  state.cursor = 0; if (reset) state.values = []; return component(props);
}
function nodes(node: ReactNode, match: (e: ReactElement<Record<string, unknown>>) => boolean): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(n => nodes(n, match));
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [...(match(node) ? [node] : []), ...nodes(node.props.children as ReactNode, match)];
}
const html = (node: ReactNode) => renderToStaticMarkup(node);
const point = (id: string, odi = 1): PersonaContextRow => ({ context_id: id, name: `이름 ${id}`, persona_id: 'P1', cluster_id: 'CL1', i: .5, s: .5, odi, zone: 'B', star: true, counter: false, shape: 'circle', tone: 0 });
const map = (points: PersonaContextRow[]): PersonaMap => ({ points, base: { s_line: .5, diag1: [[0,.4],[1,1]], diag2: [[.6,0],[1,1]] }, legend: [...new Set(points.map(p=>p.cluster_id))].map((cluster_id,index)=>({cluster_id,shape:['circle','square','triangle','diamond','pentagon'][index] ?? 'circle',cluster_label:index>=5?cluster_id:null,personas:[...new Set(points.filter(p=>p.cluster_id===cluster_id).map(p=>p.persona_id))].map((persona_id,n)=>({persona_id,persona_name:persona_id,tone:['--ink-strong','--ink','--line-strong'][n%3]}))})) });
const contexts: CCMContext[] = Array.from({ length: 10 }, (_, n) => ({ id: `C${n}`, name: '긴Context이름'.repeat(20), counter: n === 9, cells: { action: { text: '긴문자'.repeat(50), grade: 'observed', evidence: '근거 원문' } } }));

it('renders grades with distinct shapes and text, including missing evidence and provisional copy', () => {
  for (const [grade, symbol, label] of [['observed','●','관측'],['inferred','▲','추론'],['speculated','✕','추측']] as const) {
    const out = html(createElement(GradeMark, { grade })); expect(out).toContain(symbol); expect(out).toContain(label);
  }
  expect(html(createElement(GradeMark, { grade: null }))).toContain('근거 부족');
  expect(html(createElement(ProvisionalBadge))).toContain('잠정');
});
it('test_ccm_ten_columns_fold_no_overflow', () => {
  const out = html(draw(CCMTable, { contexts }));
  expect(out.match(/<table/g)).toHaveLength(2);
  expect(out.match(/table-layout:fixed/g)).toHaveLength(2);
  expect(out).toContain('overflow-wrap:anywhere'); expect(out).toContain('width:100%');
  expect(out.match(/scope="col"/g)).toHaveLength(12); expect(out).toContain('반례');
});
it('opens and closes cell evidence with native keyboard button activation and aria-expanded', () => {
  const props = { contexts: contexts.slice(0,1) };
  let tree = draw(CCMTable, props);
  let button = nodes(tree, e => e.type === 'button')[0];
  expect(button.props['aria-expanded']).toBe(false); expect(button.props.type).toBe('button');
  // Native buttons dispatch click for both Enter and Space; no duplicate key handlers.
  for (const key of ['Enter', ' ']) {
    (button.props.onClick as () => void)(); tree = draw(CCMTable, props, false);
    button = nodes(tree, e => e.type === 'button')[0];
    expect(button.props['aria-expanded']).toBe(key === 'Enter');
    expect(button.props['aria-controls']).toBeTruthy();
  }
});
it('sorts opportunity descending by default and toggles sortable headers', () => {
  const props = { rows: [point('C1',1),point('C2',3)], onOpenCard: vi.fn() };
  let tree = draw(ContextTable, props); expect(html(tree).indexOf('이름 C2')).toBeLessThan(html(tree).indexOf('이름 C1'));
  const header = nodes(tree, e => e.type === 'button' && e.props.children === '기회')[0];
  (header.props.onClick as () => void)(); tree = draw(ContextTable, props, false);
  expect(html(tree)).toContain('aria-sort="ascending"'); expect(html(tree).indexOf('이름 C1')).toBeLessThan(html(tree).indexOf('이름 C2'));
  expect(nodes(tree, e => e.type === 'th' && !!e.props['aria-sort'])).toHaveLength(8);
});
it('synchronizes row focus/hover and map click through shared highlightedId', () => {
  const onHighlight = vi.fn(), onOpenCard = vi.fn();
  const rows = [point('C1')]; const props = { rows, onHighlight, onOpenCard, highlightedId: 'C1' };
  const tree = draw(ContextTable, props); const row = nodes(tree, e => e.type === 'tr' && e.props.tabIndex === 0)[0];
  (row.props.onFocus as () => void)(); (row.props.onMouseEnter as () => void)(); expect(onHighlight).toHaveBeenLastCalledWith('C1');
  expect(row.props['data-highlighted']).toBe(true);
  const chart = draw(OpportunityMap, { map: map(rows), highlightedId: 'C1', onHighlight });
  const dot = nodes(chart, e => e.props['data-context-id'] === 'C1')[0];
  (dot.props.onClick as () => void)(); expect(onHighlight).toHaveBeenLastCalledWith('C1'); expect(dot.props['data-highlighted']).toBe(true);
  (nodes(tree, e => e.props.children === '카드 열기')[0].props.onClick as () => void)(); expect(onOpenCard).toHaveBeenCalledWith('P1', 'C1');
});
it('test_overlapping_points_table_lists_all', () => {
  const rows = [point('C1'), point('C2')];
  const out = html(draw(OpportunityMap, { map: map(rows) }));
  expect(out).toContain('겹친 Context 2개'); expect(out.match(/translate\(300 180\)/g)).toHaveLength(2);
  expect(out).toContain('role="img"'); expect(out).toContain('B Experiencing 2개');
  const table = html(draw(ContextTable, { rows, onOpenCard: vi.fn() })); for (const row of rows) expect(table).toContain(row.name);
});
it('renders cluster shapes, hollow counters, stars, baselines and toggling legend chips', () => {
  const points = Array.from({length: 6}, (_,n) => ({...point(`C${n}`), cluster_id: `CL${n}`, persona_id: `P${n}`, counter: true}));
  const props = { map: map(points) }; let tree = draw(OpportunityMap, props); const out = html(tree);
  for (const shape of ['circle','square','triangle','diamond','pentagon']) expect(out).toContain(`data-shape="${shape}"`);
  expect(out).toContain('fill="none"'); expect(out).toContain('★'); expect(out).toContain('CL5'); expect(out.match(/data-baseline=/g)).toHaveLength(3);
  const chip = nodes(tree, e => e.type === 'button' && e.props['aria-label'] === 'Persona P0')[0];
  (chip.props.onClick as () => void)(); tree = draw(OpportunityMap, props, false); expect(nodes(tree, e => e.props['data-context-id'] === 'C0')).toHaveLength(0);
  expect(nodes(tree, e => e.props['aria-label'] === 'Persona P0')[0].props['aria-pressed']).toBe(false);
});
it('renders hierarchy sizes, radar raw and percentile, bars mean, journey distribution and revisions', () => {
  expect(html(createElement(HierarchyTree, { root: { id:'product', name:'제품', doc_count:10, children:[{id:'CL1',name:'Cluster',doc_count:4}] } }))).toContain('문서 10건');
  const radar = html(createElement(Radar, { values: { Computed:{raw:.4,percentile:80}, Connected:{raw:.3,percentile:50}, Shared:{raw:.2,percentile:10} } }));
  for (const word of ['맞춤형 서비스가 필요해','실시간으로 직접 보고 싶어','함께 즐기고 싶어','0.40','80']) expect(radar).toContain(word);
  expect(html(createElement(OpportunityBars, { bars:[{id:'I1',label:'인사이트',value:2}], mean:1 }))).toContain('평균 1');
  const journey = html(createElement(JourneyTable, { rows:[{context_id:'C1',action:'행동',feeling:'감정',service:'서비스',service_action:'처방행동',cx_4d:'정신적'}] }));
  for (const word of ['AS-IS','TO-BE','⚪','처방','정신적 1','물리적 0','문화적 0','시스템 0']) expect(journey).toContain(word);
  const onView=vi.fn(), onRevert=vi.fn(); const tree=RevisionList({ revisions:[{revision:1,message:'초안'}], currentRevision:2,onView,onRevert });
  const buttons=nodes(tree,e=>e.type==='button'); (buttons[0].props.onClick as ()=>void)(); (buttons[1].props.onClick as ()=>void)();
  expect(onView).toHaveBeenCalledWith(1); expect(onRevert).toHaveBeenCalledWith(1); expect(html(tree)).toContain('이 판으로 되돌리기');
});

it.each([[0,0],[4,1],[5,2],[8,2],[9,2],[10,2]])('folds %i contexts into %i tables without dropping columns', (count,tables) => {
  const out = html(draw(CCMTable,{contexts:contexts.slice(0,count)}));
  expect(out.match(/<table/g) || []).toHaveLength(tables);
  expect(out.match(/scope="col"/g) || []).toHaveLength(count + tables);
  if (!count) expect(out).toContain('Context가 없습니다.');
});
it('shows evidence only while expanded and associates the button with its panel', () => {
  const props = {contexts:contexts.slice(0,1)};
  let tree=draw(CCMTable,props); const button=nodes(tree,e=>e.type==='button')[0];
  expect(html(tree)).not.toContain('근거 원문');
  (button.props.onClick as ()=>void)(); tree=draw(CCMTable,props,false);
  const panel=nodes(tree,e=>e.props.id===`${button.props['aria-controls']}`)[0];
  expect(panel.props.hidden).toBe(false); expect(panel.props.children).toBe('근거 원문');
});
it('uses backend persona tones and toggles visibility', () => {
  const points=Array.from({length:4},(_,n)=>({...point(`C${n}`),persona_id:`P${n}`}));
  const props={map:map(points)}; let tree=draw(OpportunityMap,props);
  for (const tone of ['--ink-strong','--ink','--line-strong']) expect(html(tree)).toContain(`var(${tone})`);
  expect(html(tree)).not.toContain('var(--blue)');
  const chip=()=>nodes(tree,e=>e.props['aria-label']==='Persona P0')[0];
  (chip().props.onClick as ()=>void)(); tree=draw(OpportunityMap,props,false);
  expect(chip().props['aria-pressed']).toBe(false);
  expect(nodes(tree,e=>e.props['data-context-id']==='C0')).toHaveLength(0);
  (chip().props.onClick as ()=>void)(); tree=draw(OpportunityMap,props,false);
  expect(chip().props['aria-pressed']).toBe(true); expect(nodes(tree,e=>e.props['data-context-id']==='C0')).toHaveLength(1);
});
it('toggles a whole cluster and marks an externally selected persona blue', () => {
  const props={map:map([point('C1')])}; let tree=draw(OpportunityMap,props);
  const cluster=nodes(tree,e=>e.type==='button')[0]; (cluster.props.onClick as ()=>void)();
  tree=draw(OpportunityMap,props,false); expect(nodes(tree,e=>e.type==='button').every(e=>!e.props['aria-pressed'])).toBe(true);
  expect(html(draw(OpportunityMap,{...props,selectedPersonaId:'P1'}))).toContain('var(--blue)');
});
it('sorts every Context column using the shared sorter without mutating input', () => {
  const rows=[{...point('B',1),name:'가',persona_name:'가',i:.1,s:.9,zone:'A' as const,star:false},{...point('A',2),name:'나',persona_name:'나',i:.9,s:.1,zone:'F' as const,star:true}];
  const original=JSON.stringify(rows);
  for (const label of ['ID','이름','Persona','중요도','만족도','기회','구역','★']) {
    const props={rows,onOpenCard:vi.fn()}; let tree=draw(ContextTable,props);
    (nodes(tree,e=>e.type==='button'&&e.props.children===label)[0].props.onClick as ()=>void)();
    tree=draw(ContextTable,props,false);
    expect(nodes(tree,e=>e.type==='th'&&e.props['aria-sort']!=='none'&&!!e.props['aria-sort'])).toHaveLength(1);
  }
  expect(JSON.stringify(rows)).toBe(original);
});
it('scales hierarchy node area with document count through all four levels', () => {
  const tree=HierarchyTree({root:{id:'product',name:'제품',doc_count:16,children:[{id:'CL',name:'Cluster',doc_count:4,children:[{id:'P',name:'Persona',doc_count:1,children:[{id:'C',name:'Context',doc_count:0}]}]}]}});
  expect(nodes(tree,e=>e.type==='circle').map(e=>e.props.r)).toEqual([24,12,6,0]);
  expect(nodes(tree,e=>e.type==='line')).toHaveLength(3);
});
it('renders empty charts and missing metrics without invalid coordinates', () => {
  const outputs=[html(draw(OpportunityMap,{map:map([])})),html(createElement(OpportunityBars,{bars:[],mean:null})),html(createElement(Radar,{values:{Computed:{raw:null,percentile:null},Connected:{raw:0,percentile:0},Shared:{raw:1,percentile:100}}})),html(createElement(JourneyTable,{rows:[]}))];
  outputs.forEach(out=>expect(out).not.toMatch(/NaN|Infinity/));
});
it('keeps ten journey Contexts in fixed-width rows and shows all four distribution buckets', () => {
  const rows=Array.from({length:10},(_,n)=>({context_id:`C${n}`,action:'a'.repeat(200),feeling:'감정',service:'서비스',service_action:'행동',cx_4d:'문화적' as const}));
  const out=html(createElement(JourneyTable,{rows}));
  expect(out.match(/scope="row"/g)).toHaveLength(10); expect(out).toContain('문화적 10'); expect(out).toContain('table-layout:fixed');
});
it('disables reverting the current revision and all revision actions while busy', () => {
  const props={revisions:[{revision:1}],currentRevision:1,onView:vi.fn(),onRevert:vi.fn()};
  expect(nodes(RevisionList(props),e=>e.type==='button')[1].props.disabled).toBe(true);
  expect(nodes(RevisionList({...props,busy:true}),e=>e.type==='button').every(e=>e.props.disabled)).toBe(true);
});

it('keeps hover emphasis neutral, reserves blue for selected personas, and labels all map zones', () => {
  const props = { map: map([point('C1')]), highlightedId: 'C1' };
  const tree = draw(OpportunityMap, props);
  const dot = nodes(tree, e => e.props['data-context-id'] === 'C1')[0];
  expect(dot.props.stroke).toBe('var(--ink-strong)');
  const labels = nodes(tree, e => e.type === 'text').map(e => html(e)).join('');
  for (const label of ['A Exciting', 'B Experiencing', 'C Competitive', 'D Forgiven', 'E Dangling', 'F At-risk']) expect(labels).toContain(label);
  const selected = draw(OpportunityMap, { ...props, selectedPersonaId: 'P1' });
  expect(nodes(selected, e => e.props['data-context-id'] === 'C1')[0].props.stroke).toBe('var(--blue)');
});

it('folds long journeys into two tables while preserving mockup rows and all four dimensions', () => {
  const rows = Array.from({length:10}, (_,i) => ({context_id:`C${i}`,action:'긴행동'.repeat(40),feeling:'느낌',service:'서비스',service_action:'바뀐 행동',cx_4d:'정신적' as const}));
  const tree = JourneyTable({rows});
  expect(nodes(tree,e=>e.type==='table')).toHaveLength(2);
  expect(nodes(tree,e=>e.type==='th' && e.props.scope==='row')).toHaveLength(10);
  expect(html(tree)).toContain('overflow-wrap:anywhere');
  expect(html(tree)).toContain('정신적 10');
});

it('ranks opportunity bars without changing inputs and labels the mean independently of color', () => {
  const bars = [{id:'low',label:'낮음',value:.5},{id:'high',label:'높음',value:2}];
  const tree = OpportunityBars({bars,mean:1});
  const out = html(tree);
  expect(out.indexOf('높음')).toBeLessThan(out.indexOf('낮음'));
  expect(bars[0].id).toBe('low');
  expect(nodes(tree,e=>e.type==='line')).toHaveLength(1);
  expect(nodes(tree,e=>e.type==='svg')[0].props['aria-label']).toContain('평균 1');
  expect(html(OpportunityBars({bars:[],mean:null}))).toContain('기회 정보가 없습니다.');
});

it('renders all hierarchy levels with proportional node areas and an accessible summary', () => {
  const tree = HierarchyTree({root:{id:'product',name:'제품',doc_count:16,children:[{id:'CL1',name:'Cluster',doc_count:4,children:[{id:'P1',name:'Persona',doc_count:1,children:[{id:'C1',name:'Context',doc_count:0}]}]}]}});
  expect(nodes(tree,e=>e.type==='circle').map(e=>e.props.r)).toEqual([24,12,6,0]);
  expect(nodes(tree,e=>e.type==='line')).toHaveLength(3);
  const svg = nodes(tree,e=>e.type==='svg')[0];
  expect(svg.props.role).toBe('img'); expect(svg.props['aria-label']).toContain('Context 문서 0건');
});

it('keeps exact radar axes, missing values, and distinct raw/percentile encodings', () => {
  const tree = Radar({values:{Computed:{raw:.4,percentile:80},Connected:{raw:null,percentile:null},Shared:{raw:0,percentile:0}}});
  const out = html(tree);
  for (const label of ['맞춤형 서비스가 필요해','실시간으로 직접 보고 싶어','함께 즐기고 싶어','원값 —','실선 · 원값 / 점선 · 백분위']) expect(out).toContain(label);
  expect(nodes(tree,e=>e.type==='svg')[0].props.role).toBe('img');
  expect(out).not.toContain('NaN'); expect(out).toContain('stroke-dasharray="4 4"');
});

it('disables revision actions while busy and prevents reverting the current revision', () => {
  const props = {revisions:[{revision:1},{revision:2}],currentRevision:2,onView:vi.fn(),onRevert:vi.fn()};
  const tree = RevisionList(props);
  expect(nodes(tree,e=>e.type==='li' && e.props['aria-current']==='true')).toHaveLength(1);
  expect(nodes(tree,e=>e.type==='button').map(e=>e.props.disabled)).toEqual([false,false,false,true]);
  expect(nodes(RevisionList({...props,busy:true}),e=>e.type==='button').every(e=>e.props.disabled)).toBe(true);
  expect(html(RevisionList({...props,revisions:[]}))).toContain('저장된 판이 없습니다.');
});

it('opens actual CCM evidence and closes the previous cell with matching disclosure targets', () => {
  const props = {contexts:contexts.slice(0,2)};
  let tree = draw(CCMTable,props);
  (nodes(tree,e=>e.type==='button')[0].props.onClick as ()=>void)();
  tree = draw(CCMTable,props,false);
  const first = nodes(tree,e=>e.type==='button')[0];
  expect(nodes(tree,e=>e.props.id===first.props['aria-controls'])[0].props.hidden).toBe(false);
  expect(html(tree)).toContain('근거 원문');
  (nodes(tree,e=>e.type==='button')[1].props.onClick as ()=>void)();
  tree = draw(CCMTable,props,false);
  expect(nodes(tree,e=>e.type==='button' && e.props['aria-expanded']===true)).toHaveLength(1);
  expect(nodes(tree,e=>e.type==='button')[0].props['aria-expanded']).toBe(false);
});
