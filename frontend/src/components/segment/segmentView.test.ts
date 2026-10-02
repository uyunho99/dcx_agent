import { afterEach, describe, expect, it, vi } from 'vitest';
import { bulkConfirmWarning, canStartEvidence, granularityBadge, layerState, qualityBadges, currentSegmentDraft, segmentErrorMessage } from './segmentView';
import * as api from '../../lib/api/segment';
import type { SegmentStatus } from '../../lib/types';

const status = (clusters = '3/5', personas = '0/12', contexts = '0/31'): SegmentStatus => ({run:'generation',status:'review',step:'drafts',progress:1,confirm:{clusters,personas,contexts}});
afterEach(() => vi.unstubAllGlobals());

describe('segment presentation contract', () => {
  it('shows progress and gates each layer by global nonempty previous counts', () => {
    expect(layerState(status())).toEqual({clusters:{locked:false,reason:'',progress:'3/5 확정'},personas:{locked:true,reason:'6-A 확정 후',progress:'0/12 확정'},contexts:{locked:true,reason:'6-B 확정 후',progress:'0/31 확정'}});
    expect(layerState(status('5/5')).personas.locked).toBe(false);
    expect(layerState(status('5/5','12/12')).contexts.locked).toBe(false);
    for (const count of ['0/0','bad','6/5']) expect(layerState(status(count)).personas.locked).toBe(true);
  });
  it('uses strict warning boundaries for cohesion, boundary and L1/L2 stability', () => {
    expect(qualityBadges({cohesion:.6,boundary:.15,ari:.7}).map(b=>b.warning)).toEqual([false,false,false]);
    expect(qualityBadges({cohesion:.599,boundary:.151,ari:.699}).map(b=>b.warning)).toEqual([true,true,true]);
    expect(qualityBadges({ari:.6},'L2')[0].warning).toBe(false);
    expect(qualityBadges({ari:.599},'L2')[0].warning).toBe(true);
    expect(qualityBadges({boundary:.15})[0].text).toBe('경계 15%');
    expect(qualityBadges({cohesion:null,ari:NaN,boundary:Infinity})).toEqual([]);
    expect(qualityBadges({npmi:-.2},'L3')[0]).toEqual({text:'NPMI -0.20',warning:false});
  });
  it('counts counter contexts once per row', () => {
    expect(bulkConfirmWarning([{flags:[]},{flags:['counter_context','counter_context']}])).toBe('반례 1개 포함');
    expect(bulkConfirmWarning([])).toBeNull();
    expect(bulkConfirmWarning([{flags:['counter_context']},{flags:['counter_context']}])).toBe('반례 2개 포함');
  });
  it('keeps evidence closed even after all confirmations', () => {
    for (const state of ['none','review','done','running'] as const) expect(canStartEvidence({...status('5/5','12/12','31/31'),status:state})).toEqual({allowed:false,reason:'다음 묶음에서 열립니다'});
  });
  it('discards drafts across generations, including when no current run exists', () => {
    const draft = {run:'generation',name:'수정 중'};
    expect(currentSegmentDraft(draft,'generation')).toBe(draft);
    expect(currentSegmentDraft(draft,'new')).toBeNull();
    expect(currentSegmentDraft(draft,null)).toBeNull();
    expect(currentSegmentDraft(null,'generation')).toBeNull();
  });
  it('shows the D-235 badge only with its flag', () => {
    expect(granularityBadge(['granularity_exceeded'],6)).toBe('Context가 6개입니다(권장 2~4)');
    expect(granularityBadge([],6)).toBeNull();
  });
  it.each([
    ['running','클러스터링이 이미 진행 중입니다.'],
    ['locked','앞 층을 모두 확정한 뒤 진행하세요.'],
    ['confirm_required','다시 나누면 확정값이 지워집니다. 다시 나누기를 확인하세요.'],
    ['stale_run','다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.'],
    ['validation','입력값을 확인하고 다시 시도하세요.'],
  ])('maps %s errors', (kind,message) => {
    expect(segmentErrorMessage({error:{kind}})).toBe(message);
  });
  it('preserves Korean backend errors and hides technical errors', () => {
    expect(segmentErrorMessage({error:{kind:'validation',message:'Desire를 입력하세요.'}})).toBe('Desire를 입력하세요.');
    expect(segmentErrorMessage(new Error('앞 층을 모두 확정한 뒤 진행하세요.'))).toBe('앞 층을 모두 확정한 뒤 진행하세요.');
    expect(segmentErrorMessage(new Error('fetch failed'))).toBe('요청에 실패했습니다. 다시 시도하세요.');
  });
});

describe('segment API wire contract (offline fetch)', () => {
  it('encodes paths, filters and versions and preserves list envelopes', async () => {
    const envelope = {run:'generation',clusters:[],kSuggest:null};
    const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>envelope});
    vi.stubGlobal('fetch',fetcher);
    expect(await api.getSegmentClusters('s /','v 2')).toEqual(envelope);
    await api.getSegmentStatus('s');
    await api.getSegmentPersonas('s','CL/0','v2');
    await api.getSegmentContexts('s','P/0','v2');
    await api.getSegmentDocs('s',{context:'C/0',band:'edge',offset:0,limit:10},'v2');
    expect(fetcher.mock.calls.map(c=>c[0])).toEqual(['/segment/s%20%2F/clusters?version=v%202','/segment/s/status','/segment/s/personas?cluster=CL%2F0&version=v2','/segment/s/contexts?persona=P%2F0&version=v2','/segment/s/docs?context=C%2F0&band=edge&offset=0&limit=10&version=v2']);
  });
  it('sends exact write bodies and distinguishes worker runId from generation run', async () => {
    const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({runId:'worker'})});
    vi.stubGlobal('fetch',fetcher);
    const cluster = {run:'generation',name:'이름',confirm:true as const};
    const persona = {...cluster,desire:'바람',goals:['목표'] as [string]};
    const context = {...cluster,action:'행동'};
    const bulk = {run:'generation',contexts:[{id:'C',name:'이름',action:'행동'}]};
    const memo = {layer:'clusters' as const,id:'CL',kind:'split' as const,note:'메모'};
    expect(await api.startSegment('s',{k:5,confirmReset:true},'v2')).toEqual({runId:'worker'});
    await api.confirmSegmentCluster('s','CL/0',cluster,'v2');
    await api.confirmSegmentPersona('s','P',persona,'v2');
    await api.confirmSegmentContext('s','C',context,'v2');
    await api.confirmSegmentContexts('s','P',bulk,'v2');
    await api.createSegmentRequest('s',memo,'v2');
    expect(fetcher.mock.calls.map(([url,init])=>[url,init.method,JSON.parse(init.body)])).toEqual([
      ['/segment/s/run?version=v2','POST',{k:5,confirmReset:true}],
      ['/segment/s/clusters/CL%2F0?version=v2','PUT',cluster],
      ['/segment/s/personas/P?version=v2','PUT',persona],
      ['/segment/s/contexts/C?version=v2','PUT',context],
      ['/segment/s/personas/P/confirm-contexts?version=v2','POST',bulk],
      ['/segment/s/requests?version=v2','POST',memo],
    ]);
  });
  it('surfaces backend stale_run messages through the shared request error handling', async () => {
    const message = '다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.';
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({status:'error',error:{kind:'stale_run',message}})}));
    await expect(api.getSegmentStatus('s')).rejects.toThrow(message);
  });
});

it('surfaces the running conflict from the real API wrapper', async () => {
  const message = '클러스터링이 이미 진행 중입니다.';
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({status:'error',error:{kind:'running',message}})}));
  await expect(api.startSegment('s',{},'v1')).rejects.toThrow(message);
});
