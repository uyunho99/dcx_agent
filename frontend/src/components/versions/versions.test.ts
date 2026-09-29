import { afterEach, describe, expect, it, vi } from 'vitest';
import { createVersion, getVersionSession, getVersionKeywords, getVersionContext, getVersionRound, versionPath } from '../../lib/api/versions';
afterEach(() => vi.unstubAllGlobals());
describe('version API wire contract', () => {
  it('reads each history resource with an explicit version and never activates it', async () => {
    const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>({data:{}})}); vi.stubGlobal('fetch',fetch);
    await getVersionSession('s1','v1'); await getVersionContext('s1','v1'); await getVersionKeywords('s1','v1'); await getVersionRound('s1',2,'v1');
    expect(fetch.mock.calls.map(call=>String(call[0]))).toEqual(['/session/s1?version=v1','/context/s1?version=v1','/keywords/s1?version=v1','/keywords/s1/rounds/2?version=v1']);
    expect(fetch.mock.calls.every(call=>call[1].method==='GET')).toBe(true);
    expect(versionPath('/session/s1?x=1','v2')).toBe('/session/s1?x=1&version=v2');
  });
  it('creates from history using the backend alias and localizes the conflict code', async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({version:'v3'})}).mockResolvedValueOnce({ok:false,status:409,json:async()=>({error:{code:'crawl_unfinished',message:'Unfinished crawl'}})});vi.stubGlobal('fetch',fetch);
    await expect(createVersion('s1','v1','stage2','메모')).resolves.toEqual({version:'v3'});
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({from:'v1',restartFrom:'stage2',note:'메모'});
    await expect(createVersion('s1','v2','stage1','')).rejects.toThrow('크롤링 수집을 끝낸 뒤 새 버전을 만드세요.');
  });
});
