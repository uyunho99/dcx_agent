'use client';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../ds/Button';
import { Card } from '../ds/Card';
import { Table } from '../ds/Table';
import { Select } from '../ds/Select';
import './queueCard.css';
import { queueReasonLabel } from './queueView';
import { TagToggle } from './TagToggle';
import { LevelBadge, levelNames } from './LevelBadge';
import { previewLabelRule, submitLabel } from '@/lib/api/label';
import { displayError } from '@/lib/api/errors';
import { keyAction, type FocusZone } from '@/lib/logic/labelKeys';
import type { EvidenceLevel, LabelResult, LabelTags, LabelVote, QueueItem, ReviewMode, SemanticTag } from '@/lib/types';
const semantics: [SemanticTag,string][] = [['sense','감각'],['feel','감정'],['think','판단'],['act','행동'],['relate','관계'],['outcome','결과']];
const initialTags = (): LabelTags => ({anchor:false,sem:{sense:0,feel:0,think:0,act:0,relate:0,outcome:0},situation:false,reason_code:null,signal:null});
export type QueueCardProps = {sid: string; version?: string; item: QueueItem; mode?: ReviewMode; labeler: string; focusZone?: FocusZone; readonly?: boolean; onNext: (after?: string) => void; onSubmitted?: (result: LabelResult) => void};
// Remount local drafts when navigating to a different document, round, or version.
export function QueueCard(props: QueueCardProps) { return <JudgingCard key={`${props.sid}:${props.version}:${props.mode}:${props.item.round}:${props.item.doc_id}`} {...props}/>; }
function voteValue(vote: LabelVote | undefined, field: string): string {
 if(!vote) return '—';
 if(vote.probs?.[field] != null) return vote.probs[field].toFixed(2);
 const tags = vote.tags ?? vote;
 const value = field === 'anchor' ? tags.anchor : field === 'situation' ? tags.situation : tags.sem?.[field as SemanticTag];
 return value == null ? '—' : value ? '있음' : '없음';
}
function JudgingCard({sid, version, item, mode = 'escalate', labeler, focusZone = 'card', readonly = false, onNext, onSubmitted}: QueueCardProps) {
 const [tags,setTags] = useState<LabelTags>(initialTags);
 const [preview,setPreview] = useState<{tags: LabelTags; level: EvidenceLevel} | null>(null);
 const [previewError,setPreviewError] = useState(''); const [retry,setRetry] = useState(0);
 const [error,setError] = useState(''); const [busy,setBusy] = useState(false); const [result,setResult] = useState<LabelResult | null>(null);
 const source = useRef<HTMLDivElement>(null); const lock = useRef(false); const opened = useRef<number | null>(null);
 useEffect(() => { source.current?.focus(); opened.current = Date.now(); }, []);
 useEffect(() => {
  let active = true;
  previewLabelRule(tags).then(value => { if(active) { setPreview({tags,level:value.level}); setPreviewError(''); } }).catch(e => { if(active) setPreviewError(displayError(e)); });
  return () => { active = false; };
 }, [tags,retry]);
 const level = preview?.tags === tags ? preview.level : null;
 const disabled = readonly || busy || result !== null;
 function change(next: LabelTags) { setPreviewError(''); setTags(next); }
 function toggleSem(index: number) { const key = semantics[index][0]; change({...tags,sem:{...tags.sem,[key]:tags.sem[key] ? 0 : 1}}); }
 async function submit() {
  if(disabled || lock.current || !level || !item.document) return;
  lock.current = true; setBusy(true); setError('');
  try {
   const saved = await submitLabel(sid,{doc_id:item.doc_id,labeler,mode,tags,...(item.round == null ? {} : {round:item.round}),elapsedSeconds:Math.min(3600,Math.max(.001,(Date.now()-(opened.current ?? Date.now()))/1000))},version);
   setResult(saved); onSubmitted?.(saved);
  } catch(e) { setError(displayError(e,'저장하지 못했습니다. 입력은 그대로 있습니다. 다시 제출하세요.')); }
  finally { lock.current = false; setBusy(false); }
 }
 const body = item.document?.text || item.document?.body || item.document?.content;
 const fields: [string,string][] = [['anchor','대상 경험'],...semantics,['situation','상황']];
 return <Card data-focus-zone="card" onKeyDown={event => {
  const action = keyAction(event.nativeEvent,focusZone); if(!action || disabled) return;
  event.preventDefault();
  if(action === 'submit') void submit(); else if(action === 'skip') { if(item.cursor) onNext(item.cursor); } else if(action === 'toggleAnchor') change({...tags,anchor:!tags.anchor}); else if(action === 'toggleSituation') change({...tags,situation:!tags.situation}); else toggleSem(action.index);
 }}>
  <p className="ds-t-label">{queueReasonLabel(item.reason, mode)}</p>
  <div ref={source} tabIndex={-1}>
   {item.document?.title && <h3 className="ds-t-card">{item.document.title}</h3>}
   {body ? <p>{body}</p> : !item.document?.title && <p>원문을 찾지 못했습니다. 다음 문서를 확인하세요.</p>}
  </div>
  {item.document?.comments?.map((comment,index) => <p key={index}>{comment.text}</p>)}
  <p className="ds-t-caption">{item.document?.channel}</p>
  <div className="queue-card-controls">
   <div className="queue-card-row" role="group" aria-label="대상 경험">
    <span className="queue-card-row-label">대상 경험</span>
    <div className="queue-card-toggles"><TagToggle label="대상 경험" shortcut="A" pressed={tags.anchor} disabled={disabled} onChange={anchor => change({...tags,anchor})}/></div>
   </div>
   <div className="queue-card-row" role="group" aria-label="경험 6차원">
    <span className="queue-card-row-label">6차원</span>
    <div className="queue-card-toggles">{semantics.map(([key,label],index) => <TagToggle key={key} label={label} shortcut={String(index+1)} pressed={!!tags.sem[key]} disabled={disabled} onChange={() => toggleSem(index)}/>)}</div>
   </div>
   <div className="queue-card-row" role="group" aria-label="상황">
    <span className="queue-card-row-label">상황</span>
    <div className="queue-card-toggles"><TagToggle label="상황 보임" shortcut="S" pressed={tags.situation} disabled={disabled} onChange={situation => change({...tags,situation})}/></div>
   </div>
   <div className="queue-card-row" role="group" aria-label="신호 · Non 사유">
    <span className="queue-card-row-label">신호 · Non 사유</span>
    <div className="queue-card-selects">
     <Select label="신호" value={tags.signal ?? ''} disabled={disabled} onChange={e => change({...tags,signal:(e.target.value || null) as LabelTags['signal']})}><option value="">선택하세요</option>{Object.entries({pain:'불편',unmet:'미충족',workaround:'우회',delight:'만족',none:'없음'}).map(([v,t]) => <option key={v} value={v}>{t}</option>)}</Select>
     <Select label="Non 사유" value={tags.reason_code ?? ''} disabled={disabled || level !== 'non'} onChange={e => change({...tags,reason_code:(e.target.value || null) as LabelTags['reason_code']})}><option value="">선택하세요</option>{Object.entries({ad:'광고',no_needs:'니즈 없음',pure_criticism:'단순 비난',other:'기타'}).map(([v,t]) => <option key={v} value={v}>{t}</option>)}</Select>
    </div>
   </div>
  </div>
  <div aria-live="polite">{level ? <><LevelBadge level={level}/> 등급 {levelNames[level]}으로 바뀜</> : previewError || '처리 중…'}</div>
  {previewError && <Button onClick={() => {setPreviewError('');setRetry(n => n+1);}}>등급 다시 계산</Button>}
  {error && <p role="alert">{error}</p>}
  {result ? <><h3>제출 후 · 라벨러와 비교</h3><LevelBadge level={result.level}/><Table><thead><tr><th>칸</th><th>내 판정</th><th>Jev 확률</th><th>GPT</th></tr></thead><tbody>{fields.map(([field,name]) => <tr key={field}><th scope="row">{name}</th><td>{voteValue(tags,field)}</td><td>{voteValue(result.votes.jev,field)}</td><td>{voteValue(result.votes.gpt,field)}</td></tr>)}</tbody></Table><div className="ds-actions"><Button variant="primary" onClick={() => onNext()}>다음 문서 보기</Button></div></> : <div className="ds-actions"><Button disabled={busy || !item.cursor} onClick={() => onNext(item.cursor)}>건너뛰기</Button><Button variant="primary" disabled={disabled || !level || !item.document} loading={busy} onClick={() => void submit()}>제출</Button></div>}
 </Card>;
}
