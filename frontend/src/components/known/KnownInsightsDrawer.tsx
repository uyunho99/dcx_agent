'use client';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../ds/Button';
import { Badge } from '../ds/Badge';
import { addKnownInsight, deleteKnownInsight, getKnownInsights } from '@/lib/api/known';
import { displayError } from '@/lib/api/errors';
import type { KnownInsight } from '@/lib/types';
export type KnownInsightsDrawerProps = {sid: string; version?: string; open: boolean; onClose: () => void; onChange?: (items: KnownInsight[]) => void; readonly?: boolean};
const origins = {stage0:'프로젝트 정의',drawer:'직접 입력',rag:'근거 원문',prev_session:'이전 세션'};
export function KnownInsightsDrawer(props: KnownInsightsDrawerProps) {
 return props.open ? <Drawer key={`${props.sid}:${props.version}`} {...props}/> : null;
}
function Drawer({sid, version, onClose, onChange, readonly = false}: KnownInsightsDrawerProps) {
 const dialog = useRef<HTMLDialogElement>(null); const input = useRef<HTMLTextAreaElement>(null);
 const [items,setItems] = useState<KnownInsight[]>([]); const [text,setText] = useState('');
 const [loading,setLoading] = useState(true); const [busy,setBusy] = useState(false); const [error,setError] = useState(''); const [retry,setRetry] = useState(0); const lock = useRef(false);
 useEffect(() => { const previous = document.activeElement as HTMLElement | null; const node = dialog.current; node?.showModal(); return () => { node?.close(); previous?.focus(); }; }, []);
 useEffect(() => { let active = true; getKnownInsights(sid).then(data => { if(active) {setItems(data.items);setLoading(false); if(!data.items.length) input.current?.focus();} }).catch(e => {if(active) {setError(displayError(e));setLoading(false);}}); return () => {active = false;}; }, [sid,retry]);
 async function mutate(action: () => Promise<KnownInsight[]>) {
  if(lock.current || readonly) return; lock.current = true;setBusy(true);setError('');
  try { const next = await action(); setItems(next);onChange?.(next); } catch(e) {setError(displayError(e));} finally {lock.current = false;setBusy(false);}
 }
 return <dialog ref={dialog} aria-label="Known Insight" data-focus-zone="panel" className="ds-t-body text-ink bg-paper border border-line rounded-overlay p-6" style={{position:'fixed',left:'auto',right:16,top:16,bottom:16,margin:0,width:360,maxWidth:'calc(100vw - 32px)',maxHeight:'calc(100vh - 32px)',overflowY:'auto'}} onCancel={e => {e.preventDefault();onClose();}}>
  <header className="ds-actions"><h2 className="ds-t-card">Known Insight · {items.length}</h2><Button onClick={onClose}>닫기</Button></header>
  {loading ? <p role="status">처리 중…</p> : items.length === 0 && !error ? <p>아직 Known Insight가 없습니다. 근거 원문에서 추가하거나 한 문장으로 적으세요.</p> : null}
  {error && <div role="alert"><p>{error}</p><Button onClick={() => {setError('');setLoading(true);setRetry(n => n+1);}}>목록 다시 불러오기</Button></div>}
  <ul>{items.map(item => <li key={item.id} style={{marginBlock:16}}><Badge>{item.type === 'statement' ? '문장' : '원문'}</Badge> <Badge>{origins[item.from]}</Badge><p>{item.text || '근거 원문'}</p>{item.createdAt && <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleDateString('ko-KR')}</time>}{item.warning && <p role="status">유사도 제외는 임베딩 연결 후 적용됩니다</p>}<Button disabled={busy || readonly} aria-label={`${item.text || '근거 원문'} 삭제`} onClick={() => void mutate(async () => {await deleteKnownInsight(sid,item.id,version);return items.filter(row => row.id !== item.id);})}>삭제</Button></li>)}</ul>
  <form onSubmit={e => {e.preventDefault();if(!text.trim() || loading) return;void mutate(async () => {const added = await addKnownInsight(sid,{type:'statement',text:text.trim()},version);setText('');return [...items.filter(row => row.id !== added.id),added];});}}>
   <label>새 문장<textarea ref={input} value={text} disabled={readonly || busy} onChange={e => setText(e.target.value)}/></label><div className="ds-actions"><Button type="submit" loading={busy} disabled={readonly || loading || !text.trim()}>추가</Button></div>
  </form>
 </dialog>;
}
