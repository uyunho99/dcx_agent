export type FocusZone = 'card' | 'input' | 'panel' | 'popover';
export type Action = 'toggleAnchor' | 'toggleSituation' | 'submit' | 'skip' | {type: 'toggleSem'; index: number};
export function keyAction(e: KeyboardEvent, focusZone: FocusZone): Action | null {
 if(focusZone !== 'card' || e.defaultPrevented || e.isComposing || e.keyCode === 229 || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return null;
 const target = e.target as HTMLElement | null;
 if(target && (['INPUT','TEXTAREA','SELECT'].includes(target.tagName) || target.isContentEditable || target.closest?.('[role="dialog"], [data-focus-zone="panel"], [data-focus-zone="popover"]'))) return null;
 if(e.key === 'Enter' && target?.tagName === 'BUTTON') return null;
 const key = e.key.toLowerCase();
 if(key === 'a' || e.code === 'KeyA') return 'toggleAnchor';
 if(key === 's' || e.code === 'KeyS') return 'toggleSituation';
 if(/^[1-6]$/.test(key)) return {type:'toggleSem',index:Number(key)-1};
 return e.key === 'Enter' ? 'submit' : e.key === 'ArrowRight' ? 'skip' : null;
}
