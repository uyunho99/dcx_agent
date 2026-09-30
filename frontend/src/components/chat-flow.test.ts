/* eslint-disable @typescript-eslint/no-explicit-any */
import { expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({slots: [] as unknown[], cursor: 0}));
vi.mock('react', async () => ({...await vi.importActual('react'),
 useEffect: () => {},
 useState: (initial: unknown) => {const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]=initial;return [hooks.slots[i],(next: unknown) => {hooks.slots[i]=typeof next === 'function' ? next(hooks.slots[i]) : next;}];},
 useRef: (initial: unknown) => {const i=hooks.cursor++;if(!(i in hooks.slots)) hooks.slots[i]={current:initial};return hooks.slots[i];},
}));
vi.mock('@/components/ds', () => ({Button:'Button',Switch:'Switch',Skeleton:'Skeleton'}));
vi.mock('@/components/known/SourceCard', () => ({SourceCard:'SourceCard'}));
import ChatPanel from './ChatPanel';
function nodes(node: any): any[] {return !node || typeof node !== 'object' ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node,...nodes(node.props?.children)];}
it('QA-K: question, add, search excluding known, then switch off', async () => {
 hooks.slots=[];
 const onSend=vi.fn().mockResolvedValueOnce({answer:'a',sources:[{doc_id:'d',text:'원문'}]})
 .mockResolvedValueOnce({answer:'a',sources:[],reason:'all_known'})
 .mockResolvedValueOnce({answer:'a',sources:[{doc_id:'d',text:'원문'}]});
 const onKnownAdded=vi.fn();
 const render=()=>{hooks.cursor=0;return nodes(ChatPanel({initialMessage:'hello',sid:'s',version:'v1',onSend,onKnownAdded}));};
 const settle=async()=>{await Promise.resolve();await Promise.resolve();};
 let tree=render();tree.find(n=>n.type==='input').props.onChange({target:{value:'question'}});
 tree=render();tree.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await settle();
 expect(onSend).toHaveBeenLastCalledWith('question',true);
 tree=render();const card=tree.find(n=>n.type==='SourceCard');expect(card.props).toMatchObject({sid:'s',version:'v1',source:{doc_id:'d'}});
 card.props.onAdded({id:'k',type:'doc',doc_id:'d'});expect(onKnownAdded).toHaveBeenCalledOnce();
 tree=render();tree.find(n=>n.props?.children==='추가한 이야기 빼고 다시 찾기').props.onClick();await settle();
 expect(onSend).toHaveBeenLastCalledWith('question',true);
 tree=render();expect(tree.some(n=>n.props?.children==="이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다.")).toBe(true);
 tree.find(n=>n.type==='Switch').props.onChange(false);await settle();
 expect(onSend).toHaveBeenLastCalledWith('question',false);
 tree=render();expect(tree.filter(n=>n.type==='SourceCard')).toHaveLength(1);
});

it('keeps the legacy chat error and retry wording without a session', async () => {
 hooks.slots=[];
 const render=()=>{hooks.cursor=0;return nodes(ChatPanel({initialMessage:'hello',onSend:vi.fn().mockRejectedValue(Error('failed'))}));};
 let tree=render();tree.find(n=>n.type==='input').props.onChange({target:{value:'question'}});
 tree=render();tree.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 await Promise.resolve();await Promise.resolve();
 tree=render();
 expect(tree.some(n=>n.props?.children==='오류가 발생했습니다.')).toBe(true);
 expect(tree.some(n=>n.props?.children==='다시 찾기')).toBe(false);
});
