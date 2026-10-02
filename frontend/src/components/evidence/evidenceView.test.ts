import { afterEach, describe, expect, it, vi } from 'vitest';
import { canBuildPersona, excludedMessage, highlight, locationLabel, rowBadge } from './evidenceView';
import * as api from '../../lib/api/evidence';
import type { EvidenceContextState } from '../../lib/types';

afterEach(() => vi.unstubAllGlobals());

describe('evidence display contract', () => {
  it.each([
    ['queued', '대기'], ['running', '진행 중'], ['done', '완료'],
    ['failed', '실패'], ['skipped', '건너뜀'],
  ] as const)('labels %s rows', (state, label) => {
    expect(rowBadge(state)).toBe(label);
  });
  it('allows persona building only when every context is done or skipped', () => {
    const status = (...states: EvidenceContextState[]) => ({contexts: states.map(status => ({status}))});
    expect(canBuildPersona(status('done', 'skipped'))).toBe(true);
    expect(canBuildPersona(status('done'))).toBe(true);
    expect(canBuildPersona(status('skipped'))).toBe(true);
    expect(canBuildPersona(status())).toBe(true);
    for (const state of ['queued', 'running', 'failed'] as const) {
      expect(canBuildPersona(status('done', state))).toBe(false);
    }
  });
  it('labels quote locations using one-based comment numbers', () => {
    expect(locationLabel({field:'title', idx:null})).toBe('제목');
    expect(locationLabel({field:'body', idx:null})).toBe('본문');
    expect(locationLabel({field:'comment', idx:0})).toBe('댓글 1');
    expect(locationLabel({field:'comment', idx:2})).toBe('댓글 3');
  });
  it('splits a half-open range without empty surrounding segments', () => {
    expect(highlight('가나다라마', 1, 4)).toEqual([{text:'가',mark:false},{text:'나다라',mark:true},{text:'마',mark:false}]);
    expect(highlight('가나다', 0, 3)).toEqual([{text:'가나다',mark:true}]);
    expect(highlight('가나다', 0, 1)).toEqual([{text:'가',mark:true},{text:'나다',mark:false}]);
    expect(highlight('가나다', 2, 3)).toEqual([{text:'가나',mark:false},{text:'다',mark:true}]);
  });
  it.each([
    [null, 2], [0, null], [null, null], [-1, 2], [0, 4], [2, 1], [1, 1],
    [0.5, 2], [0, 1.5], [NaN, 2], [0, Infinity],
  ])('leaves invalid range %s:%s unmarked', (start, end) => {
    expect(highlight('가나다', start, end)).toEqual([{text:'가나다',mark:false}]);
  });
  it('slices backend Unicode code-point offsets after an emoji', () => {
    expect(highlight('😀 인용 끝', 2, 4)).toEqual([{text:'😀 ',mark:false},{text:'인용',mark:true},{text:' 끝',mark:false}]);
  });
  it('preserves empty text and exact exclusion copy', () => {
    expect(highlight('', 0, 0)).toEqual([{text:'',mark:false}]);
    expect(excludedMessage(0)).toBe('0건이 Known Insight와 같아 빠졌습니다');
    expect(excludedMessage(12)).toBe('12건이 Known Insight와 같아 빠졌습니다');
  });
});

describe('evidence API wire contract (offline fetch)', () => {
  it('encodes IDs, tabs and versions and preserves response envelopes', async () => {
    const envelopes = [{status:'done',contexts:[]}, {context:{id:'C'},tab:'new',items:[],counter:[],rare:[],excludedKnown:2,queries:[],queryFailed:false,undifferentiated:[]}, {desireSupport:[],artifacts:[]}, {schema:'evidence-package/1',version:'v2',params:{},personas:[]}];
    const fetcher = vi.fn();
    for (const envelope of envelopes) fetcher.mockResolvedValueOnce({ok:true,json:async()=>envelope});
    vi.stubGlobal('fetch', fetcher);
    expect(await api.getEvidenceStatus('s /', 'v 2')).toEqual(envelopes[0]);
    expect(await api.getEvidenceContext('s', 'C/0', 'new', 'v2')).toEqual(envelopes[1]);
    expect(await api.getEvidencePersona('s', 'P/0', 'v2')).toEqual(envelopes[2]);
    expect(await api.getEvidencePackage('s', 'v2')).toEqual(envelopes[3]);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/evidence/s%20%2F/status?version=v%202','/evidence/s/contexts/C%2F0?tab=new&version=v2','/evidence/s/personas/P%2F0?version=v2','/evidence/s/package?version=v2']);
    for (const [, init] of fetcher.mock.calls) {
      expect(init.method).toBe('GET');
      expect(init.body).toBeUndefined();
    }
  });
  it('defaults to the all tab and omits absent version queries', async () => {
    const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({})});
    vi.stubGlobal('fetch', fetcher);
    await api.getEvidenceContext('s', 'C');
    await api.getEvidenceStatus('s');
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/evidence/s/contexts/C?tab=all','/evidence/s/status']);
  });
  it('sends exact write bodies, preserving generation run separately from worker runId', async () => {
    const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({runId:'worker'})});
    vi.stubGlobal('fetch', fetcher);
    expect(await api.startEvidence('s', {fresh:true,contexts:['C']}, 'v2')).toEqual({runId:'worker'});
    await api.startEvidence('s');
    await api.refreshEvidenceNew('s /', 'C/0', {run:'generation'}, 'v 2');
    await api.skipEvidenceContext('s /', 'C/0', {run:'generation'}, 'v 2');
    expect(fetcher.mock.calls.map(([url, init]) => [url,init.method,JSON.parse(init.body)])).toEqual([
      ['/evidence/s/run?version=v2','POST',{fresh:true,contexts:['C']}],
      ['/evidence/s/run','POST',{}],
      ['/evidence/s%20%2F/contexts/C%2F0/refresh-new?version=v%202','POST',{run:'generation'}],
      ['/evidence/s%20%2F/contexts/C%2F0/skip?version=v%202','POST',{run:'generation'}],
    ]);
  });
  it.each(['segment_required','running','locked','not_found','not_ready','stale_run'])('uses shared error handling for %s', async kind => {
    const message = '요청 상태를 확인하세요.';
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:kind === 'not_found' ? 404 : 409,json:async()=>({status:'error',error:{kind,message}})}));
    await expect(api.getEvidenceStatus('s')).rejects.toThrow(message);
  });
});
