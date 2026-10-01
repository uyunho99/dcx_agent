'use client';
import { useRef, useState } from 'react';
import { Card } from '../ds/Card';
import { Button } from '../ds/Button';
import { LevelBadge } from '../label/LevelBadge';
import { addKnownInsight } from '@/lib/api/known';
import { displayError } from '@/lib/api/errors';
import type { EvidenceLevel, KnownInsight, SourceDocument } from '@/lib/types';
export type ChatSource = SourceDocument & {desc?: string; cafe?: string; link?: string; score?: number; evidence_level?: EvidenceLevel; evidence_level_pred?: EvidenceLevel};
export type SourceCardProps = {sid: string; version?: string; source: ChatSource; known?: boolean; readonly?: boolean; onAdded?: (item: KnownInsight) => void};
export function SourceCard(props: SourceCardProps) {return <Source key={`${props.sid}:${props.version}:${props.source.doc_id}`} {...props}/>;}
function Source({sid,version,source,known = false,readonly = false,onAdded}: SourceCardProps) {
 const [added,setAdded] = useState(false); const [busy,setBusy] = useState(false);const [error,setError] = useState(''); const lock = useRef(false);
 const level = source.evidence_level ?? source.evidence_level_pred; const url = source.url || source.link;
 async function add() {if(lock.current || known || added || readonly) return;lock.current = true;setBusy(true);setError('');try {const item = await addKnownInsight(sid,{type:'doc',doc_id:source.doc_id},version);setAdded(true);onAdded?.(item);} catch(e) {setError(displayError(e));} finally {lock.current = false;setBusy(false);}}
 return <Card><p>{source.text || source.body || source.content || source.desc || source.title}</p><div>{level && <LevelBadge level={level}/>} <span>{source.channel || source.cafe}</span>{source.score != null && <span> · 유사도 {source.score.toFixed(2)}</span>}</div>{url && /^https?:\/\//i.test(url) && <a href={url} target="_blank" rel="noopener noreferrer">원문 보기</a>}{error && <p role="alert">{error}</p>}<div className="ds-actions"><Button disabled={readonly || known || added || !source.doc_id} loading={busy} onClick={() => void add()}>{known || added ? 'Known Insight에 추가됨' : 'Known Insight에 추가'}</Button></div></Card>;
}
