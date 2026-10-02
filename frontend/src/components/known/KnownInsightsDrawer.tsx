'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { Button } from '../ds/Button';
import { Badge } from '../ds/Badge';
import { addKnownInsight, deleteKnownInsight, getKnownInsights } from '@/lib/api/known';
import { displayError } from '@/lib/api/errors';
import { getKnownSuggestions, addSuggestedKnownInsight } from '@/lib/api/insight';
import { PreviousSuggestions } from './PreviousSuggestions';
import type { InsightSuggestion, KnownInsight } from '@/lib/types';
import styles from './KnownInsightsDrawer.module.css';
export type KnownInsightsDrawerProps = {sid: string; version?: string; open: boolean; onClose: () => void; onChange?: (items: KnownInsight[]) => void; readonly?: boolean};
const origins = {stage0:'프로젝트 정의',drawer:'직접 입력',rag:'근거 원문',prev_session:'이전 세션'};
export function KnownInsightCard({item, disabled, onDelete}: {item: KnownInsight; disabled: boolean; onDelete: () => void}) {
 const [expanded, setExpanded] = useState(false);
 const bodyId = useId();
 return <li className={`ds-card ds-sm ${styles.card}`}>
  <div className={styles.badges}><Badge>{item.type === 'statement' ? '문장' : '원문'}</Badge><Badge>{origins[item.from]}</Badge></div>
  <div>
   <p id={bodyId} className={`${styles.body} ${item.type === 'doc' && !expanded ? styles.clamped : ''}`}>{item.text || '근거 원문'}</p>
   {item.type === 'doc' && <Button variant="quiet" size="sm" aria-expanded={expanded} aria-controls={bodyId} onClick={() => setExpanded(value => !value)}>{expanded ? '접기' : '펼치기'}</Button>}
  </div>
  {item.warning && <p className={`ds-t-caption ${styles.warning}`} role="status">유사도 제외는 임베딩 연결 후 적용됩니다</p>}
  <footer className={styles.footer}>
   {item.createdAt && <time className="ds-t-caption" dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleDateString('ko-KR')}</time>}
   <Button className={styles.delete} variant="quiet" size="sm" disabled={disabled} aria-label={`${item.text || '근거 원문'} 삭제`} onClick={onDelete}>삭제</Button>
  </footer>
 </li>;
}
export function KnownInsightsDrawer(props: KnownInsightsDrawerProps) {
 return props.open ? <Drawer key={`${props.sid}:${props.version}`} {...props}/> : null;
}
function Drawer({sid, version, onClose, onChange, readonly = false}: KnownInsightsDrawerProps) {
 const [suggestions,setSuggestions] = useState<InsightSuggestion[]>([]);
 const [suggestionsError,setSuggestionsError] = useState('');
 const dialog = useRef<HTMLDialogElement>(null); const input = useRef<HTMLTextAreaElement>(null);
 const [items,setItems] = useState<KnownInsight[]>([]); const [text,setText] = useState('');
 const [loading,setLoading] = useState(true); const [busy,setBusy] = useState(false); const [error,setError] = useState(''); const [retry,setRetry] = useState(0); const lock = useRef(false);
 useEffect(() => {let active = true; getKnownSuggestions(sid,version).then(data => {if(active) {setSuggestions(data.items);setSuggestionsError('');}}).catch(e => {if(active) setSuggestionsError(displayError(e));});return () => {active = false;};},[sid,version,retry]);
 useEffect(() => { const previous = document.activeElement as HTMLElement | null; const node = dialog.current; node?.showModal(); return () => { node?.close(); previous?.focus(); }; }, []);
 useEffect(() => { let active = true; getKnownInsights(sid, version).then(data => { if(active) {setItems(data.items);setLoading(false); if(!data.items.length) input.current?.focus();} }).catch(e => {if(active) {setError(displayError(e));setLoading(false);}}); return () => {active = false;}; }, [sid,version,retry]);
 async function mutate(action: () => Promise<KnownInsight[]>) {
  if(lock.current || readonly) return; lock.current = true;setBusy(true);setError('');
  try { const next = await action(); setItems(next);onChange?.(next); } catch(e) {setError(displayError(e));} finally {lock.current = false;setBusy(false);}
 }
 return <dialog ref={dialog} aria-label="Known Insight" data-focus-zone="panel" className="ds-t-body text-ink bg-paper border border-line p-6 space-y-6" style={{position:'fixed',inset:'0 0 0 auto',margin:0,width:360,maxWidth:'100vw',height:'100dvh',maxHeight:'100dvh',overflowY:'auto'}} onCancel={e => {e.preventDefault();onClose();}}>
  <header className="ds-actions"><h2 className="ds-t-card">Known Insight · {items.length}</h2><Button onClick={onClose}>닫기</Button></header>
  {loading ? <p role="status">처리 중…</p> : items.length === 0 && !error ? <p>아직 Known Insight가 없습니다. 근거 원문에서 추가하거나 한 문장으로 적으세요.</p> : null}
  {error && <div role="alert"><p>{error}</p><Button onClick={() => {setError('');setLoading(true);setRetry(n => n+1);}}>목록 다시 불러오기</Button></div>}
  <ul className={styles.list}>{items.map(item => <KnownInsightCard key={item.id} item={item} disabled={busy || readonly} onDelete={() => void mutate(async () => {await deleteKnownInsight(sid,item.id,version);return items.filter(row => row.id !== item.id);})}/>)}</ul>
  {suggestionsError && <p role="alert">{suggestionsError}<Button onClick={() => setRetry(n => n+1)}>추천 다시 불러오기</Button></p>}
  <PreviousSuggestions items={suggestions} disabled={readonly || busy || loading} onAdd={item => void mutate(async () => {const added = await addSuggestedKnownInsight(sid,{type:'statement',text:`${item.title}\n${item.painPoint}`},version);setSuggestions(rows => rows.filter(row => row.sessionId !== item.sessionId || row.insightId !== item.insightId));return [...items.filter(row => row.id !== added.id),added];})}/>
  <form onSubmit={e => {e.preventDefault();if(!text.trim() || loading) return;void mutate(async () => {const added = await addKnownInsight(sid,{type:'statement',text:text.trim()},version);setText('');return [...items.filter(row => row.id !== added.id),added];});}}>
   <label className="ds-field"><span className="ds-lab">새 문장</span><textarea className="ds-inp" rows={4} ref={input} value={text} disabled={readonly || busy} onChange={e => setText(e.target.value)}/></label><div className="ds-actions"><Button type="submit" loading={busy} disabled={readonly || loading || !text.trim()}>추가</Button></div>
  </form>
 </dialog>;
}
