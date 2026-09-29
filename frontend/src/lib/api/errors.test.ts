import { expect, it } from 'vitest';
import { responseError, displayError } from './errors';
it.each(['sources_unavailable','worker_running','invalid_request','unknown_resume_channel','p1_unfinished','finished_collection','readonly_version','version_conflict'])('localizes %s', code=>{
 const message=responseError({error:{code,message:'Raw backend English'}},400);
 expect(message).toMatch(/[가-힣]/); expect(message).not.toMatch(/Raw|!|죄송/);
 expect(message).not.toBe('요청에 실패했습니다. 다시 시도하세요.');
});
it('never displays unknown backend messages or validation details',()=>{
 for(const data of [{error:{code:'unknown',message:'English'}},{error:{message:'English'}},{detail:[{msg:'English'}]}]) expect(responseError(data,422)).toBe('요청에 실패했습니다. 다시 시도하세요.');
});

it('keeps network errors Korean and preserves screen-specific fallback text',()=>{
 expect(displayError(new Error('Failed to fetch'), '저장에 실패했습니다. 다시 시도하세요.')).toBe('저장에 실패했습니다. 다시 시도하세요.');
 const message=responseError({error:{code:'readonly_version'}},403);
 expect(displayError(new Error(message))).toBe(message);
 expect(responseError({error:{code:'constructor'}},400)).toBe('요청에 실패했습니다. 다시 시도하세요.');
});
