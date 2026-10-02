import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';
import { completedThrough } from '@/lib/logic/completedThrough';
import { createInsightActions } from './insightActions';
import { PreviousSuggestions } from '@/components/known/PreviousSuggestions';
import type { InsightResponse } from '@/lib/types';
vi.mock('next/navigation', () => ({ usePathname: () => '/pipeline/insights', redirect: vi.fn() }));
vi.mock('@/components/DirtyProvider', () => ({useDirty: () => ({confirmNavigation: () => true})}));
import StepBar from '@/components/StepBar';
const snapshot: InsightResponse = {worker:{status:"idle",reason:null,runId:null,mode:null,target:null},insights:{revision:2,items:[],history:[]},concepts:{revision:1,items:[],history:[]},bars:null,radar:null};
function setup(ok = false) {
 const api = {chatInsight:vi.fn().mockResolvedValue({ok,revision:3}),getInsights:vi.fn().mockResolvedValue(snapshot),revertInsight:vi.fn().mockResolvedValue({revision:3}),confirmInsights:vi.fn().mockResolvedValue({confirmed:['I1']})};
 const publish = vi.fn(); const confirmed = vi.fn();
 return {api,publish,confirmed,actions:createInsightActions('sid','v2',api,publish,confirmed)};
}
it('chat failure keeps current revision without reloading or publishing', async () => {
 const {api,publish,actions} = setup();
 expect(await actions.chat('insights','change')).toBe('요청을 반영하지 못했습니다. 다르게 말해 주세요.');
 expect(api.getInsights).not.toHaveBeenCalled(); expect(publish).not.toHaveBeenCalled();
 api.chatInsight.mockRejectedValueOnce(new Error('offline'));
 expect(await actions.chat('insights','change')).toBe('요청을 반영하지 못했습니다. 다르게 말해 주세요.'); expect(publish).not.toHaveBeenCalled();
});
it('reverts the chosen target and reloads its new revision', async () => {
 const {api,publish,actions} = setup(); await actions.revert('concept:I1',1);
 expect(api.revertInsight).toHaveBeenCalledWith('sid',{target:'concept:I1',revision:1},'v2'); expect(publish).toHaveBeenCalledWith(snapshot);
});
it('confirms only explicit checked IDs and applies server response', async () => {
 const {api,confirmed,actions} = setup(); await actions.confirm(['I1']);
 expect(api.confirmInsights).toHaveBeenCalledWith('sid',{ids:['I1']},'v2'); expect(confirmed).toHaveBeenCalledWith(['I1']);
});
it('previous suggestions start collapsed and add only on click', () => {
 const onAdd = vi.fn(); const item = {sessionId:'old',insightId:'I1',title:'추천',painPoint:'문제'};
 const tree = PreviousSuggestions({items:[item],disabled:false,onAdd});
 const html = renderToStaticMarkup(tree); expect(html).toContain('이전 세션 추천'); expect(html).not.toContain('<details open'); expect(onAdd).not.toHaveBeenCalled();
 const list = tree.props.children[1]; list.props.children[0].props.children[2].props.onClick(); expect(onAdd).toHaveBeenCalledWith(item);
});
it('redirects old route and branches new route on derivedRef with legacy screen preserved', () => {
 const old = readFileSync('src/app/insights/page.tsx','utf8'); const route = readFileSync('src/app/pipeline/insights/page.tsx','utf8');
 expect(old).toMatch(/redirect\(['"]\/pipeline\/insights['"]\)/); expect(route).toContain('prep?.derivedRef'); expect(route).toContain('<InsightScreen'); expect(route).toContain('<LegacyInsightsPage');
});
it('links insight sidebar and reports completion at 8/9', () => {
 expect(completedThrough({completion:{personaDone:true,segmentDone:true}})).toBe(8);
 expect(completedThrough({completion:{insightDone:true,personaDone:true}})).toBe(9);
 expect(completedThrough({completion:{personaDone:false,insightDone:false,segmentDone:true}})).toBe(6);
 expect(renderToStaticMarkup(createElement(StepBar,{currentStep:'insight',session:{completion:{insightDone:true}}}))).toContain('href="/pipeline/insights"');
});

import { ConceptDetail } from './InsightScreen';
import { addSuggestedKnownInsight } from '@/lib/api/insight';
it('renders synthetic persona, quoted evidence location, journey and all four CX dimensions', () => {
 const html = renderToStaticMarkup(createElement(ConceptDetail,{concept:{outdated:false,persona_profile:{text:'프로필'},basis:'근거 45건',pain_points:[{quote:'실제 인용',channel:'cafe',location:{field:'body',idx:1},context_id:'C1'}],journey:[{context_id:'C1',action:'행동',feeling:'불편',service:'서비스',service_action:'변화',cx_4d:'정신적'}],constraint_check:[{constraint:'예산',verdict:'review',reason:'확인 필요'}]}}));
 for(const expected of ['합성값','실제 인용','cafe','body','C1','4D-CX','정신적 1','물리적 0','문화적 0','시스템 0','⚠ 검토']) expect(html).toContain(expected);
});
it('suggestion API explicitly sends prev_session only when invoked', async () => {
 const fetcher = vi.fn().mockResolvedValue({ok:true,json:async () => ({id:'K1'})}); vi.stubGlobal('fetch',fetcher);
 try {await addSuggestedKnownInsight('s',{type:'statement',text:'추천'},'v2');expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('/known/s?version=v2'),expect.objectContaining({method:'POST',body:JSON.stringify({type:'statement',text:'추천',from:'prev_session'})}));} finally {vi.unstubAllGlobals();}
});
