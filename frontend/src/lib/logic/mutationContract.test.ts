import { afterEach, expect, it, vi } from 'vitest';
import { patchSession, putContext, contextRequest } from '../api/context';
import { startRound, regenerateRound, commitRound, postEvent, addKeyword, suggestWords, getCoverage } from '../api/keywords';
import { resumeCrawl } from '../api/crawl';
afterEach(()=>vi.unstubAllGlobals());
it('sends displayed version on context and all keyword mutations',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>({})}));vi.stubGlobal('fetch',fetch);
 await patchSession('s',{drafts:{}},'v2'); await putContext('s',{} as never,'v2');
 await startRound('s',1,'v2'); await regenerateRound('s',2,'v2'); await commitRound('s',1,1,[],'v2'); await postEvent('s',{round:1,type:'direction',text:'방향'},'v2');await addKeyword('s','말',{axis:'physical',sub:'x'},'manual','v2');await suggestWords('s',{axis:'physical',sub:'x'},'v2');await getCoverage('s','v2');
 for(const [url] of fetch.mock.calls as unknown as [string][]) expect(new URL(url,'http://local').searchParams.get('version')).toBe('v2');
});
it('keeps resume body optional and sends increased intervals',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>({})}));vi.stubGlobal('fetch',fetch);
 await resumeCrawl('s','v2');await resumeCrawl('s','v2',{min_interval_s:{clien:2}});
 expect((fetch.mock.calls as unknown as [string,RequestInit][])[0][1].body).toBeUndefined();expect(JSON.parse((fetch.mock.calls as unknown as [string,RequestInit][])[1][1].body as string)).toEqual({min_interval_s:{clien:2}});
});
it('preserves validation and version conflict messages without retry',async()=>{
 const fetch=vi.fn(async()=>({ok:false,status:422,json:async()=>({detail:[{msg:'사용 불가 채널'}]})}));vi.stubGlobal('fetch',fetch);
 await expect(contextRequest('/test')).rejects.toThrow('사용 불가 채널');expect(fetch).toHaveBeenCalledTimes(1);
});
it('announces active-version conflicts once and never retries the mutation',async()=>{
 const dispatchEvent=vi.fn();vi.stubGlobal('window',{dispatchEvent});
 const fetch=vi.fn(async()=>({ok:false,status:409,json:async()=>({error:{message:'다른 버전이 활성화되었습니다'}})}));vi.stubGlobal('fetch',fetch);
 await expect(patchSession('s',{step:'r1'},'v1')).rejects.toThrow('다른 버전이 활성화되었습니다');
 expect(fetch).toHaveBeenCalledTimes(1);expect(dispatchEvent).toHaveBeenCalledTimes(1);expect(dispatchEvent.mock.calls[0][0].type).toBe('dcx-version-conflict');
});
