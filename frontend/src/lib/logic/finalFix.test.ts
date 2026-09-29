import { describe, expect, it, vi } from 'vitest';
import { allowNavigation, localDate, crawlNeedsSetup, documentCount, availableChannels, increasedResumeIntervals, crawlStartLabel } from './finalFix';
import { keywordSnapshotDiff } from './compareView';
import { popoverKeyAction } from './keywordKeys';
describe('final fixes', () => {
 it('confirms only dirty navigation and preserves cancel',()=>{const confirm=vi.fn(()=>false); expect(allowNavigation(false,confirm)).toBe(true); expect(confirm).not.toHaveBeenCalled(); expect(allowNavigation(true,confirm)).toBe(false); expect(confirm).toHaveBeenCalledWith('저장되지 않은 변경이 있습니다. 이동할까요?');});
 it('ignores IME Enter including legacy 229',()=>{expect(popoverKeyAction('input','Enter',true)).toBe('native');expect(popoverKeyAction('input','Enter',false,229)).toBe('native');expect(popoverKeyAction('input','Enter',false,13)).toBe('submit');});
 it('compares rejection as removal and only approved axis counts',()=>{const a=[{id:'a',kw:'바람',axis:'physical',status:'approved'},{id:'b',axis:'physical',status:'pending'}]; const b=[{...a[0],status:'rejected'}, {...a[1],axis:'behavioral'}];const diff=keywordSnapshotDiff(a,b);expect(diff.removed).toEqual([a[0]]);expect(diff.moved).toEqual([]);expect(diff.distribution?.physical).toBe(-1);expect(diff.distribution?.behavioral??0).toBe(0);});
 it.each(['stage0','stage1'])('keeps incremental collection available after a %s restart', restartFrom=>{
 expect(crawlNeedsSetup({stale:{stage2:'changed'},collectionId:'c1'},restartFrom)).toBe(false);
 });
 it('uses fresh setup only before a stage2 restart starts its new list',()=>{
 const fresh=crawlNeedsSetup({stale:{stage2:'changed'},collectionId:'c1'},'stage2');
 expect(fresh).toBe(true);
 expect(crawlStartLabel(fresh)).toBe('새 수집 시작');
 for(const stale of [{},undefined]) {
 const afterStart=crawlNeedsSetup({stale,collectionId:'c2'},'stage2');
 expect(afterStart).toBe(false);
 expect(crawlStartLabel(afterStart)).toBe('목록 수집 시작');
 }
 });
 it('uses normal setup and label for a first crawl',()=>{
 const fresh=crawlNeedsSetup({collectionId:null});
 expect(fresh).toBe(false);
 expect(crawlStartLabel(fresh)).toBe('목록 수집 시작');
 });
 it('doubles effective intervals only for paused or manifest channels without changing settings',()=>{
 const config={perChannel:{a:{min_interval_s:3},b:{min_interval_s:5},ui:{min_interval_s:9}}};
 const before=JSON.stringify(config);
 expect(increasedResumeIntervals(['a'],{collection_channels:['a','b'],min_interval_s:{a:7}},config)).toEqual({a:14});
 expect(increasedResumeIntervals([],{collection_channels:['b'],min_interval_s:{b:0}},config)).toEqual({b:1});
 expect(increasedResumeIntervals(['a'],{},config)).toEqual({a:6});
 expect(increasedResumeIntervals([],{},config)).toEqual({});
 expect(JSON.stringify(config)).toBe(before);
 });
 it('uses local calendar dates and available public channels',()=>{expect(localDate(new Date(2026,8,29,0,30))).toBe('2026-09-29');expect(availableChannels(['fixture','youtube','naver_blog'],['fixture','naver_blog'],false)).toEqual(['naver_blog']);});
 it('prefers document counts including zero over legacy counts',()=>{expect(documentCount({docs:0,full:8,snippet:3})).toBe(0);expect(documentCount({full:8,snippet:3})).toBe(11);});
});
