/* eslint-disable @typescript-eslint/no-explicit-any */
import {expect,it,vi} from 'vitest';
const h=vi.hoisted(()=>({cursor:0,values:[] as any[]}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),useState:(initial:any)=>{const i=h.cursor++;return [i in h.values?h.values[i]:initial,vi.fn()];},useRef:()=>({current:false}),useEffect:()=>{}}));
vi.mock('../versions/VersionProvider',()=>({useVersion:()=>({refreshSessionAfterStage:vi.fn()})}));
vi.mock('../versions/useStageCompletionRefresh',()=>({useStageCompletionRefresh:vi.fn()}));
import {OpportunityBars} from './OpportunityBars';
import {InsightScreen} from './InsightScreen';
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];}
function text(n:any):string{return typeof n==='string'?n:Array.isArray(n)?n.map(text).join(''):n?.props?text(n.props.children):'';}
it.each([null,'r1'])('QA-F2 shows concept failure with a pending launch and runId %s',runId=>{
 h.cursor=0;h.values=[{insights:{revision:1,items:[{id:'I3',title:'제목',pain_point:'문제',context_ids:['C3'],known_ki_id:null}],history:[]},concepts:{revision:0,items:[],history:[]},bars:null,radar:null,worker:{status:'failed',mode:'concept',target:'I3',reason:'컨셉을 만들지 못했습니다. 다시 시도하세요.',runId}},[],'I3','insights',null,false,'',0,{runId:'r1',mode:'concept',target:'I3'}];
 const alerts=nodes(InsightScreen({sid:'s'})).filter(n=>n.props?.role==='alert');
 expect(alerts.map(text).join('')).toContain('컨셉을 만들지 못했습니다. 다시 시도하세요.');
});

it('keeps missing ODI distinct from a measured zero',()=>{
 h.cursor=0;h.values=[{insights:{revision:1,items:[],history:[]},concepts:{revision:0,items:[],history:[]},bars:{bars:[{id:'missing',odi:null},{id:'zero',odi:0}],mean:0},radar:null},[]];
 const bars=nodes(InsightScreen({sid:'s'})).find(n=>n.type===OpportunityBars);
 expect(bars.props.bars.map((b:any)=>b.value)).toEqual([null,0]);
 const rendered=OpportunityBars(bars.props);
 expect(nodes(rendered).filter(n=>n.type==='rect')).toHaveLength(1);
 expect(text(rendered)).toContain('—');
});
