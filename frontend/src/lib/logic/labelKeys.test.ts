import { expect, it } from 'vitest';
import { keyAction } from './labelKeys';
const event = (key: string, extra = {}) => ({ key, ...extra } as KeyboardEvent);
it('S in input is inert and S in card toggles situation', () => { expect(keyAction(event('S'), 'input')).toBeNull(); expect(keyAction(event('S'), 'card')).toBe('toggleSituation'); });
it('disables every shortcut outside card', () => { for (const zone of ['input', 'panel', 'popover'] as const) for (const key of ['A','1','2','3','4','5','6','S','Enter','ArrowRight']) expect(keyAction(event(key), zone)).toBeNull(); });
it('maps card shortcuts', () => { expect(keyAction(event('a'), 'card')).toBe('toggleAnchor'); for(let i=1;i<=6;i++) expect(keyAction(event(String(i)), 'card')).toEqual({ type: 'toggleSem', index: i-1 }); expect(keyAction(event('Enter'), 'card')).toBe('submit'); expect(keyAction(event('ArrowRight'), 'card')).toBe('skip'); });
it('ignores composition, repeat, modifiers and editable targets', () => { for(const flag of ['isComposing','repeat','ctrlKey','metaKey','altKey']) expect(keyAction(event('s',{[flag]:true}), 'card')).toBeNull(); for(const tagName of ['INPUT','TEXTAREA','SELECT']) expect(keyAction(event('S',{target:{tagName}}), 'card')).toBeNull(); expect(keyAction(event('S',{target:{isContentEditable:true}}),'card')).toBeNull(); });
it('leaves button Enter native and ignores dialog/popover descendants', () => {
 expect(keyAction(event('Enter',{target:{tagName:'BUTTON'}}),'card')).toBeNull();
 expect(keyAction(event('S',{target:{closest:()=>({})}}),'card')).toBeNull();
 expect(keyAction(event('s',{keyCode:229}),'card')).toBeNull();
 expect(keyAction(event('s',{defaultPrevented:true}),'card')).toBeNull();
 expect(keyAction(event(' '),'card')).toBeNull();
});
