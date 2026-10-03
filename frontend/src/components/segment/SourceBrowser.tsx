'use client';
import { useRef, useState } from 'react';
import { getSegmentDocs } from '@/lib/api/segment';
import { displayError } from '@/lib/api/errors';
import { Badge, Banner, Button } from '../ds';
import type { SegmentDocument } from '@/lib/types';

const PAGE = 20;
const bandLabel: Record<string, string> = { core: '핵심', fringe: '주변', edge: '가장자리' };
export const sourceSorts = [['center', '중심순'], ['edge', '가장자리순 · 숨은 니즈 후보']] as const;
export const supportSorts = [['center', '가까운 순'], ['edge', '먼 순']] as const;
export function previewText(doc: Pick<SegmentDocument, 'body' | 'title'>, open: boolean, limit = 300) {
    const text = doc.body || doc.title || '';
    return open || text.length <= limit ? text : `${text.slice(0, limit)}…`;
}

/** All originals of one Cluster · Persona · Context, paged, centre- or edge-first. */
export function SourceBrowser({ sid, version, filter, total, support = false }: {
    sid?: string; version?: string; filter: { cluster?: string; persona?: string; context?: string }; total?: number;
    /** Auxiliary channel (YouTube comments) attached to the nearest Context. */
    support?: boolean;
}) {
    const [sort, setSort] = useState<'center' | 'edge'>('center');
    const [docs, setDocs] = useState<SegmentDocument[] | null>(null);
    const [count, setCount] = useState<number | null>(null);
    const [open, setOpen] = useState<Record<string, boolean>>({});
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const request = useRef(0);
    async function load(nextSort = sort, append = false) {
        if (!sid) { setError('세션을 먼저 선택하세요.'); return; }
        const id = ++request.current;
        setLoading(true);
        setError('');
        try {
            const result = await getSegmentDocs(sid, { ...filter, sort: nextSort, ...(support ? { support: true } : {}), limit: PAGE, offset: append ? docs?.length ?? 0 : 0 }, version);
            if (id !== request.current) return;
            setDocs(append ? [...(docs ?? []), ...result.docs] : result.docs);
            setCount(result.total);
        } catch (e) {
            if (id === request.current) setError(displayError(e));
        } finally {
            if (id === request.current) setLoading(false);
        }
    }
    return <details onToggle={event => { if (event.currentTarget.open && !docs) void load(); }}>
        <summary className="cursor-pointer ds-t-caption">{support ? '공감 댓글 · 보조 근거' : '원문 더 보기'}{total !== undefined ? ` · ${total.toLocaleString('ko-KR')}건` : ''}</summary>
        <div className="my-3 flex flex-wrap gap-2" role="group" aria-label="원문 정렬">{(support ? supportSorts : sourceSorts).map(([key, label]) =>
            <Button key={key} variant={sort === key ? 'primary' : 'secondary'} disabled={loading} onClick={() => { setSort(key); setOpen({}); void load(key); }}>{label}</Button>)}</div>
        {error && <Banner tone="danger" actions={<Button onClick={() => void load()}>다시 불러오기</Button>}>{error}</Banner>}
        {docs && <ol className="space-y-3">{docs.map(doc => {
            const full = !!open[doc.docId];
            const text = doc.body || doc.title || '';
            return <li key={doc.docId} className="border-l-2 pl-3 break-words">
                {doc.title && doc.body && <p className="ds-t-label">{doc.title}</p>}
                <p className="whitespace-pre-wrap">{previewText(doc, full)}</p>
                <p className="ds-t-caption flex flex-wrap items-center gap-2">{doc.band && <Badge>{bandLabel[doc.band] ?? doc.band}</Badge>}<span>{doc.docId}</span>
                    {text.length > 300 && <button className="underline" onClick={() => setOpen({ ...open, [doc.docId]: !full })}>{full ? '접기' : '펼치기'}</button>}
                    {doc.url && <a className="underline" href={doc.url} target="_blank" rel="noreferrer">원문 링크</a>}</p>
            </li>;
        })}</ol>}
        {loading && <p role="status">원문을 불러오는 중…</p>}
        {docs && count !== null && docs.length < count && <Button disabled={loading} onClick={() => void load(sort, true)}>{`더 불러오기 (${docs.length.toLocaleString('ko-KR')} / ${count.toLocaleString('ko-KR')})`}</Button>}
        {docs?.length === 0 && <p>원문이 없습니다.</p>}
    </details>;
}
