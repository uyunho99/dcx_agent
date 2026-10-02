import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({cursor: 0, diff: {} as unknown}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useState: () => [[ 'stage3', 'stage6', {key:'s:v1:v2:stage6', data:state.diff, session:{}}, '', 0 ][state.cursor++], vi.fn()],
}));
vi.mock('next/navigation', () => ({useSearchParams: () => new URLSearchParams('a=v1&b=v2')}));
vi.mock('@/components/versions/VersionProvider', () => ({useVersion: () => ({sid:'s', meta:{versions:[{id:'v1'},{id:'v2'}]}})}));
vi.mock('@/components/versions/StageVersion', () => ({RestartVersion:()=>null, StaleBanner:()=>null}));
vi.mock('@/components/versions/VersionPicker', () => ({VersionHistory:()=>null}));
import Page from './page';
it('renders stage-six report availability and saved names, desire, goals, action and confirmation counts', () => {
 const empty = {report:null, clusters:{total:0,confirmed:0,items:[]}, personas:{total:0,confirmed:0,items:[]}, contexts:{total:0,confirmed:0,items:[]}};
 state.diff = {same:false,before:empty,after:{...empty,report:{k:5,dims:{act_unknown:2}},
 clusters:{total:1,confirmed:1,items:[{cluster_id:'CL0',name:'Bedroom',confirmed:true}]},
 personas:{total:1,confirmed:1,items:[{persona_id:'P0',name:'Sleeper',desire:'Rest',goals:['Sleep'],confirmed:true}]},
 contexts:{total:1,confirmed:1,items:[{context_id:'C0',name:'Night',action:'Reserve',confirmed:true}]}}};
 state.cursor=0;
 const html=renderToStaticMarkup(createElement(Page));
 for (const text of ['Bedroom','Sleeper','Rest','Sleep','Night','Reserve','1/1','저장된 보고서 없음']) expect(html).toContain(text);
 expect(html).not.toContain('Invalid Date');
});
