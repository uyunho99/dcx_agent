import { describe, expect, it } from 'vitest';
import { reconcileGateSelection, stalePageStage, formatCrawlNumber, crawlWorkerRunning } from './qaFix';

const scope = {collectionId:'c1', snapshot_id:'s1', gate:[{kw:'keep'},{kw:'saved'}]};
const previous = {...scope, excluded:['keep'], saved:['saved'], draft:['keep']};
describe('gate selection scope', () => {
  it.each([{collectionId:'c2'}, {snapshot_id:'s2'}])('resets on collection or snapshot change: %j', change => {
    expect(reconcileGateSelection(previous, {...scope,...change}, ['saved','unknown']).excluded).toEqual(['saved']);
  });
  it('keeps local selection in the same collection and snapshot', () => {
    expect(reconcileGateSelection(previous, scope, []).excluded).toEqual(['keep']);
  });
  it('restores only matching scoped drafts and drops unknown keywords', () => {
    const draft = {collectionId:'c1',snapshot_id:'s1',exclusions:['keep','unknown']};
    expect(reconcileGateSelection(null, scope, ['saved','unknown'], draft)).toMatchObject({excluded:['keep'],draft:['keep'],saved:['saved']});
    for (const invalid of [{...draft,collectionId:'c2'},{...draft,snapshot_id:'s2'},{snapshot_id:'s1',exclusions:['keep']}]) {
      expect(reconcileGateSelection(null, scope, ['saved'], invalid).excluded).toEqual(['saved']);
    }
  });
  it('prunes existing local and draft selections when rows change', () => {
    expect(reconcileGateSelection(previous, {...scope,gate:[]}, [])).toMatchObject({excluded:[],draft:[],saved:[]});
  });
  it('ignores restored drafts when transitioning an existing selection', () => {
    expect(reconcileGateSelection(previous, {...scope,collectionId:'c2'}, [], {collectionId:'c2',snapshot_id:'s1',exclusions:['keep']}).excluded).toEqual([]);
  });
});
it('selects only the current page stale stage, irrespective of the restart cause', () => {
  const stale = {stage1:'stage1 changed in v2',stage2:'stage1 changed in v2'};
  expect(stalePageStage('stage2',stale)).toBe('stage2');
  expect(stalePageStage('stage1',stale)).toBe('stage1');
  expect(stalePageStage('stage0',stale)).toBeNull();
  expect(stalePageStage('stage0',{stage0:'stage0 changed in v2'})).toBe('stage0');
  expect(stalePageStage('stage2',undefined)).toBeNull();
});
it('formats crawl numbers with grouping and at most one decimal', () => {
  expect(formatCrawlNumber(22797.14)).toBe('22,797.1');
  expect(formatCrawlNumber(12000)).toBe('12,000');
  expect(formatCrawlNumber(0)).toBe('0');
});
it('shows the refresh caption only while a worker runs or stops', () => {
  for (const status of ['running','stopping']) expect(crawlWorkerRunning(status)).toBe(true);
  for (const status of ['done','paused','interrupted','idle','failed']) expect(crawlWorkerRunning(status)).toBe(false);
});
