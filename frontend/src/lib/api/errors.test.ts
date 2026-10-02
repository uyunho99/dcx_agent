import { afterEach, expect, it, vi } from 'vitest';
import { responseError, displayError } from './errors';
it.each(['sources_unavailable','worker_running','invalid_request','unknown_resume_channel','p1_unfinished','finished_collection','readonly_version','version_conflict','storage_error','no_collection','snapshot_conflict','no_unfinished_phase','gate_not_editable'])('localizes %s', code=>{
 const message=responseError({error:{code,message:'Raw backend English'}},400);
 expect(message).toMatch(/[가-힣]/); expect(message).not.toMatch(/Raw|!|죄송/);
 expect(message).not.toBe('요청에 실패했습니다. 다시 시도하세요.');
});
it('uses a generic fallback for English, missing messages, and validation details',()=>{
 for(const data of [{error:{code:'unknown',message:'English'}},{error:{message:'English'}},{detail:[{msg:'English'}]},{error:{}},{}]) expect(responseError(data,422)).toBe('요청에 실패했습니다. 다시 시도하세요.');
});

it('keeps network errors Korean and preserves screen-specific fallback text',()=>{
 expect(displayError(new Error('Failed to fetch'), '저장에 실패했습니다. 다시 시도하세요.')).toBe('저장에 실패했습니다. 다시 시도하세요.');
 const message=responseError({error:{code:'readonly_version'}},403);
 expect(displayError(new Error(message))).toBe(message);
 expect(responseError({error:{code:'constructor'}},400)).toBe('요청에 실패했습니다. 다시 시도하세요.');
});

afterEach(()=>vi.unstubAllGlobals());
it.each([undefined,'unknown'])('preserves Korean backend messages with unmapped code %s through displayError',code=>{
 for(const message of ['작업이 진행 중입니다. 완료 후 다시 시도하세요.','다른 버전이 활성화되었습니다']) {
 expect(responseError({error:{code,message}},409)).toBe(message);
 expect(displayError(new Error(responseError({error:{code,message}},409)))).toBe(message);
 }
});
it('prefers mapped Korean text over a Korean backend message',()=>{
 expect(responseError({error:{code:'version_conflict',message:'서버 원문'}},409)).toBe('다른 버전이 활성화되었습니다. 활성 버전을 열고 다시 시도하세요.');
});
it('explains storage failure and the next action',()=>{
 expect(responseError({error:{code:'storage_error',message:'disk failure'}},500)).toBe('저장 공간에 쓰지 못했습니다. 디스크 여유 공간을 확인하고 이어서 진행하세요.');
});
it('keeps the version-conflict event for coded and code-less 409 responses only',()=>{
 const dispatchEvent=vi.fn();
 vi.stubGlobal('window',{dispatchEvent});
 responseError({error:{code:'version_conflict'}},409);
 responseError({error:{message:'다른 버전이 활성화되었습니다'}},409);
 expect(dispatchEvent).toHaveBeenCalledTimes(2);
 expect(dispatchEvent.mock.calls.every(([event])=>event.type==='dcx-version-conflict')).toBe(true);
 responseError({error:{code:'version_conflict'}},400);
 responseError({error:{message:'작업이 진행 중입니다'}},409);
 expect(dispatchEvent).toHaveBeenCalledTimes(2);
});

it('explains unfinished crawl conflicts through the display helper',()=>{
 const message=responseError({error:{code:'crawl_unfinished',message:'Unfinished crawl'}},409);
 expect(message).toBe('크롤링 수집을 끝낸 뒤 새 버전을 만드세요.');
 expect(displayError(new Error(message), '새 버전을 만들지 못했습니다.')).toBe(message);
});

it('N2 keeps crawl code copy ahead of broad conflict kind',()=>{
 expect(responseError({error:{kind:'conflict',code:'no_paused_detail',message:'No channel'}},409)).toBe('차단 또는 파싱 오류로 멈춘 상세 수집 채널이 없습니다.');
});
it.each(['stale','evidence_required','persona_required'])('N2 maps stage-eight kind %s with unknown code',kind=>{
 expect(responseError({error:{kind,code:'unknown',message:'Internal message'}},409)).not.toBe('요청에 실패했습니다. 다시 시도하세요.');
});
