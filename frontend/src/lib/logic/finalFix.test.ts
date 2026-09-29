import { describe, expect, it, vi } from 'vitest';
import { allowNavigation, localDate, crawlNeedsSetup, documentCount, availableChannels } from './finalFix';
import { keywordSnapshotDiff } from './compareView';
import { popoverKeyAction } from './keywordKeys';
describe('final fixes', () => {
 it('confirms only dirty navigation and preserves cancel',()=>{const confirm=vi.fn(()=>false); expect(allowNavigation(false,confirm)).toBe(true); expect(confirm).not.toHaveBeenCalled(); expect(allowNavigation(true,confirm)).toBe(false); expect(confirm).toHaveBeenCalledWith('저장되지 않은 변경이 있습니다. 이동할까요?');});
 it('ignores IME Enter including legacy 229',()=>{expect(popoverKeyAction('input','Enter',true)).toBe('native');expect(popoverKeyAction('input','Enter',false,229)).toBe('native');expect(popoverKeyAction('input','Enter',false,13)).toBe('submit');});
 it('compares rejection as removal and only approved axis counts',()=>{const a=[{id:'a',kw:'바람',axis:'physical',status:'approved'},{id:'b',axis:'physical',status:'pending'}]; const b=[{...a[0],status:'rejected'}, {...a[1],axis:'behavioral'}];const diff=keywordSnapshotDiff(a,b);expect(diff.removed).toEqual([a[0]]);expect(diff.moved).toEqual([]);expect(diff.distribution?.physical).toBe(-1);expect(diff.distribution?.behavioral??0).toBe(0);});
 it('reopens stage2 setup for stale or detached collection',()=>{expect(crawlNeedsSetup({stale:{stage2:'changed'},collectionId:'c1'})).toBe(true);expect(crawlNeedsSetup({collectionId:null})).toBe(true);expect(crawlNeedsSetup({collectionId:'c1'})).toBe(false);expect(crawlNeedsSetup({stale:{stage2:'changed'},collectionId:'c1'},'stage1')).toBe(false);});
 it('uses local calendar dates and available public channels',()=>{expect(localDate(new Date(2026,8,29,0,30))).toBe('2026-09-29');expect(availableChannels(['fixture','youtube','naver_blog'],['fixture','naver_blog'],false)).toEqual(['naver_blog']);});
 it('prefers document counts including zero over legacy counts',()=>{expect(documentCount({docs:0,full:8,snippet:3})).toBe(0);expect(documentCount({full:8,snippet:3})).toBe(11);});
});
