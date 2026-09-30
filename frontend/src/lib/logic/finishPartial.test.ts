import { expect, it } from 'vitest';
import { canFinishPartial, finishPartialConfirmation } from './finishPartial';
const paused = {kind:'detail' as const,status:'interrupted',resumable:true,channels:{ppomppu:{status:'paused_blocked'},clien:{status:'paused_parse_error'}},remaining_by_channel:{ppomppu:300,clien:12}};
it('shows the finish button only for stopped paused detail channels',()=>{
 expect(canFinishPartial(paused)).toBe(true);
 expect(canFinishPartial({...paused,status:'running'})).toBe(false);
 expect(canFinishPartial({...paused,kind:'list'})).toBe(false);
 expect(canFinishPartial({...paused,channels:{}})).toBe(false);
 expect(canFinishPartial({...paused,resumable:false})).toBe(false);
});
it('confirms each channel remaining count and reason',()=>{
 const text=finishPartialConfirmation(paused,{ppomppu:'뽐뿌',clien:'클리앙'});
 expect(text).toContain('뽐뿌 300건 미수집(차단)');
 expect(text).toContain('클리앙 12건 미수집(파싱 오류)');
 expect(text).toContain('건너뛰고');
});
