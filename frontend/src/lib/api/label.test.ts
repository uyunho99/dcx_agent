import { afterEach, expect, it, vi } from 'vitest';
import * as label from './label';
import * as prep from './prep';
import * as train from './train';
import * as known from './known';
import { readFileSync } from 'node:fs';
afterEach(() => vi.unstubAllGlobals());
it('new clients never call whole-session save', () => {
 for (const name of ['prep','label','train','known']) expect(readFileSync(new URL(`./${name}.ts`, import.meta.url),'utf8')).not.toContain('/save-session');
 expect([prep, train, known].every(client => Object.keys(client).length > 0)).toBe(true);
});
it('uses seen POST and encodes the skip cursor and version', async () => {
 const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({item:null})}); vi.stubGlobal('fetch',fetcher);
 await label.markLabelSeen('s/a','v 2'); await label.getNextLabel('s/a',{mode:'audit',round:2,after:'a+b/=',version:'v 2'});
 expect(fetcher.mock.calls[0][0]).toBe('/label/s%2Fa/seen?version=v%202'); expect(fetcher.mock.calls[0][1].method).toBe('POST');
 const url = new URL(fetcher.mock.calls[1][0], 'http://local'); expect(url.searchParams.get('after')).toBe('a+b/='); expect(url.searchParams.get('round')).toBe('2'); expect(url.searchParams.get('version')).toBe('v 2');
});
it('uses feature routes, methods and bodies for every stage 3–5 client', async () => {
 const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({})}); vi.stubGlobal('fetch',fetcher);
 const tags = {anchor:true,sem:{sense:1,feel:0,think:0,act:0,relate:0,outcome:0},situation:false} as const;
 const config = {adFilter:[],excludeSources:[],minBodyChars:10,boilerplate:{},analyzer:'kiwi',tokenPos:['NNG'],embedder:'voyage',embedModel:'voyage-4',embedDim:1024} as const;
 await prep.savePrepConfig('s',{...config,adFilter:[],excludeSources:[],tokenPos:['NNG']},'v1'); await prep.runPrep('s','v1'); await prep.getPrepStatus('s','v1');
 await label.setLabelMode('s',{mode:'model',modelId:'m1'},'v1'); await label.startLabel('s','v1'); await label.controlLabeler('s','jev','pause','v1'); await label.controlLabeler('s','gpt','resume','v1'); await label.getLabelOverview('s','v1'); await label.previewLabelRule(tags); await label.submitLabel('s',{doc_id:'d',labeler:'human',mode:'audit',round:1,tags},'v1'); await label.createAudit('s','v1');
 await train.startTraining('s','parent','v1'); await train.getTrainingStatus('s','v1'); await train.exportTraining('s',true,'v1'); await train.getModels('s','v1'); await train.getModel('m/a');
 await known.getKnownInsights('s'); await known.addKnownInsight('s',{type:'doc',doc_id:'d'},'v1'); await known.updateKnownInsight('s','i/a','새 문장','v1'); await known.deleteKnownInsight('s','i/a','v1');
 expect(fetcher.mock.calls.map(([url,init]) => [url,init.method])).toEqual([
 ['/prep/s/config?version=v1','PUT'],['/prep/s/run?version=v1','POST'],['/prep/s/status?version=v1','GET'],
 ['/label/s/mode?version=v1','POST'],['/label/s/start?version=v1','POST'],['/label/s/judge/jev/pause?version=v1','POST'],['/label/s/judge/gpt/resume?version=v1','POST'],['/label/s/overview?version=v1','GET'],['/label/rule/preview','POST'],['/label/s/submit?version=v1','POST'],['/label/s/audit?version=v1','POST'],
 ['/train/s?version=v1','POST'],['/train/s/status?version=v1','GET'],['/train/s/export?version=v1','POST'],['/models?sid=s&version=v1','GET'],['/models/m%2Fa','GET'],
 ['/known/s','GET'],['/known/s?version=v1','POST'],['/known/s/i%2Fa?version=v1','PATCH'],['/known/s/i%2Fa?version=v1','DELETE']]);
 expect(JSON.parse(fetcher.mock.calls[8][1].body)).toEqual({tags});
 expect(JSON.parse(fetcher.mock.calls[9][1].body)).toEqual({doc_id:'d',labeler:'human',mode:'audit',round:1,tags});
 expect(JSON.parse(fetcher.mock.calls[11][1].body)).toEqual({parent:'parent'});
 expect(JSON.parse(fetcher.mock.calls[13][1].body)).toEqual({withoutModel:true});
 expect(JSON.parse(fetcher.mock.calls[17][1].body)).toEqual({type:'doc',doc_id:'d'});
 expect(fetcher.mock.calls.every(([url]) => !url.includes('/save-session'))).toBe(true);
});
it('preserves Korean API failure text for retry UI', async () => {
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:500,json:async()=>({status:'error',error:{kind:'storage',message:'저장하지 못했습니다. 입력은 그대로 있습니다. 다시 제출하세요.'}})}));
 await expect(label.markLabelSeen('s')).rejects.toThrow('저장하지 못했습니다. 입력은 그대로 있습니다. 다시 제출하세요.');
});
