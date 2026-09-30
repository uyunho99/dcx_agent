import { describe, expect, it } from 'vitest';
import { prepConfig, prepView, splitLines, prepPhase, prepEstimate } from './prep';

describe('preparation settings', () => {
  it('inherits crawl rules and uses the exact production defaults', () => {
    const config = prepConfig({ crawlConfig: { adWords: ['협찬'], excludeSources: ['판매 카페'] } });
    expect(config).toMatchObject({ adFilter: ['협찬'], excludeSources: ['판매 카페'], minBodyChars: 10, analyzer: 'kiwi', tokenPos: ['NNG','NNP','VV','VA','XR'], embedder: 'voyage', embedModel: 'voyage-4', embedDim: 1024 });
    expect(config.boilerplate.naver_cafe).toContain('카페 가입하기');
  });
  it('restores drafts ahead of saved config, preserving explicit empty lists and zero', () => {
    const result = prepConfig({ crawlConfig: { adWords: ['협찬'] }, prep: { config: { minBodyChars: 30, boilerplate: { naver_cafe: ['기본'] } } }, drafts: { prep: { config: { adFilter: [], minBodyChars: 0, boilerplate: { naver_cafe: [] } } } } });
    expect(result.adFilter).toEqual([]);
    expect(result.minBodyChars).toBe(0);
    expect(result.boilerplate.naver_cafe).toEqual([]);
  });
  it('can ignore drafts while restoring the actual running configuration', () => {
    expect(prepConfig({ prep: { config: { minBodyChars: 20 } }, drafts: { prep: { config: { minBodyChars: 5 } } } }, false).minBodyChars).toBe(20);
  });
  it('splits lines without splitting phrases or source names at commas', () => {
    expect(splitLines(' 공감 \n\n문구, 그대로\n공감 ')).toEqual(['공감', '문구, 그대로']);
  });
});
describe('preparation status', () => {
  it('never presents stale results as a completed run', () => {
    expect(prepView({ status: 'running', progress: 0.2, runId: 'r', stage3: { after: 20 } }).report).toBeNull();
  });
  it('distinguishes empty and partial results and permits only nonempty results to advance', () => {
    expect(prepView({ status: 'done', progress: 1, runId: null, stage3: { original: 100, after: 0 } })).toMatchObject({ empty: true, canNext: false });
    expect(prepView({ status: 'done', progress: 1, runId: null, stage3: { after: 40, embed_failed_zero_vector: 4 } })).toMatchObject({ partial: true, canNext: true });
    expect(prepView({ status: 'done', progress: 1, runId: null })).toMatchObject({ canNext: false, report: null });
  });
  it('offers resume only for interrupted jobs, not a worker paused without a resume endpoint', () => {
    expect(prepView({ status: 'interrupted', progress: 0.2, runId: 'r' }).resumable).toBe(true);
    expect(prepView({ status: 'paused', progress: 0.2, runId: 'r' }).resumable).toBe(false);
  });
  it('tracks backend shard progress without inventing filter/token completion', () => {
    expect(prepPhase({})).toBe('필터 → 토큰 → 임베딩');
    expect(prepPhase({ done_shards: 1, total_shards: 3 })).toBe('임베딩');
    expect(prepPhase({ phase: 'tokens' })).toBe('토큰');
  });
  it('uses measured prior results for an estimate, never mockup fixture counts', () => {
    expect(prepEstimate(null)).toBeNull();
    expect(prepEstimate({ original: 100, after: 80 })).toEqual({ original: 100, after: 80, storageBytes: 163840 });
  });
});

import { prepEditLock } from './prep';
it('locks prep rules after labeling starts and ignores stale draft rules', () => {
 const session = {labeling:{started:true},prep:{config:{minBodyChars:20}},drafts:{prep:{config:{minBodyChars:99}}}};
 expect(prepEditLock(session)).toBe('라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.');
 expect(prepConfig(session).minBodyChars).toBe(20);
 expect(prepEditLock({labeling:{started:false}})).toBeNull();
 expect(prepEditLock({})).toBeNull();
});
