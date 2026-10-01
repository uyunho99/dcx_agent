import { afterEach, expect, it, vi } from 'vitest';
import { refreshSessionAfterStage, labelCompletionKey } from './refreshSessionAfterStage';
import { getVersionSession, type VersionSession } from './api/versions';
import { useSessionStore } from '@/stores/useSessionStore';
vi.mock('./api/versions', () => ({getVersionSession:vi.fn()}));
vi.mock('@/stores/useSessionStore', () => ({useSessionStore:{getState:()=>({setSession})}}));
const setSession = vi.fn();
afterEach(() => vi.clearAllMocks());
it('fetches the selected version and updates the banner session and sidebar together', async () => {
 const data = {step:'preprocess',stale:{},completion:{prepDone:true}} as unknown as VersionSession;
 vi.mocked(getVersionSession).mockResolvedValue({data});
 const apply = vi.fn();
 await refreshSessionAfterStage('s','v2',apply,()=>true);
 expect(getVersionSession).toHaveBeenCalledWith('s','v2');
 expect(apply).toHaveBeenCalledWith(data);
 expect(useSessionStore.getState().setSession).toHaveBeenCalledWith({sd:data,step:data.step});
});
it('ignores read-only or departed versions before fetching and after resolving', async () => {
 const apply=vi.fn();
 await refreshSessionAfterStage('s','v1',apply,()=>false);
 expect(getVersionSession).not.toHaveBeenCalled();
 let active=true;
 vi.mocked(getVersionSession).mockImplementation(async () => {active=false;return {data:{} as VersionSession};});
 await refreshSessionAfterStage('s','v2',apply,()=>active);
 expect(apply).not.toHaveBeenCalled();expect(setSession).not.toHaveBeenCalled();
});
it('preserves both session copies on a failed fetch', async () => {
 vi.mocked(getVersionSession).mockRejectedValue(new Error('offline'));
 const apply=vi.fn();
 await expect(refreshSessionAfterStage('s','v2',apply,()=>true)).rejects.toThrow('offline');
 expect(apply).not.toHaveBeenCalled();expect(setSession).not.toHaveBeenCalled();
});
it('detects completed judge pairs or model inference, without waiting for monitor or review queue', () => {
 const progress={jev:{state:'done',runId:'j'},gpt:{state:'running',runId:'g'},monitor:{state:'running'}};
 expect(labelCompletionKey({started:true,mode:'llm',progress})).toBe(null);
 progress.gpt.state='done';
 expect(labelCompletionKey({started:true,mode:'llm',progress})).toBe('j:g');
 expect(labelCompletionKey({started:true,mode:'model',progress:{infer:{state:'done',runId:'i'},monitor:{state:'running'}}})).toBe('i');
 expect(labelCompletionKey({started:false,mode:'llm',progress})).toBe(null);
 expect(labelCompletionKey({legacy:true})).toBe(null);
});
