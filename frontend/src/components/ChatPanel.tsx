"use client";
import { useState, useRef, useEffect } from "react";
import { Button, Skeleton, Switch } from "@/components/ds";
import { SourceCard, type ChatSource } from "@/components/known/SourceCard";
import type { KnownInsight } from "@/lib/types";

export type ChatReply = string | { answer: string; sources?: unknown[]; reason?: unknown; status?: string };
export function normalizeChatReply(reply: ChatReply): {answer: string; sources?: ChatSource[]; reason?: string} {
  if (typeof reply === "string") return {answer: reply};
  if (reply.status === "error") throw new Error("검색 실패");
  return {answer: reply.answer || "응답 없음", sources: (reply.sources ?? []).filter((source): source is ChatSource =>
    !!source && typeof source === "object" && "doc_id" in source && typeof source.doc_id === "string" && !!source.doc_id),
    reason: typeof reply.reason === "string" ? reply.reason : undefined};
}
export function sourceEmptyMessage(reason: string | undefined, novel: boolean) {
  if (reason === "all_known" && novel) return "이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다.";
  if (reason === "no_vectors") return "검색할 벡터가 없습니다. 전처리를 먼저 완료하세요.";
  if (reason === "no_labels") return "검색할 근거 원문이 없습니다. 라벨 판정을 먼저 완료하세요.";
  if (reason === "embedder_unconnected") return "임베딩 API가 연결되지 않았습니다. 연결 상태를 확인하세요.";
  return "검색된 근거 원문이 없습니다.";
}
interface Message {
  role: "user" | "bot";
  text: string;
  sources?: ChatSource[];
  reason?: string;
  query?: string;
  novel?: boolean;
  added?: boolean;
  failed?: boolean;
}
interface ChatPanelProps {
  initialMessage: string;
  onSend: (msg: string, novel: boolean) => Promise<ChatReply>;
  sid?: string | null;
  version?: string;
  readonly?: boolean;
  known?: KnownInsight[];
  onKnownAdded?: (item: KnownInsight) => void;
}
export default function ChatPanel({ initialMessage, onSend, sid, version, readonly = false, known = [], onKnownAdded }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([{ role: "bot", text: initialMessage }]);
  const [input, setInput] = useState("");
  const [novel, setNovel] = useState(true);
  const [loading, setLoading] = useState(false);
  const lock = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const send = async (query = input, filter = novel, retryIndex?: number) => {
    const msg = query.trim();
    if (!msg || lock.current) return;
    lock.current = true;
    if (retryIndex === undefined) {
      setInput("");
      setMessages(m => [...m, { role: "user", text: msg }]);
    }
    setLoading(true);
    try {
      const reply = normalizeChatReply(await onSend(msg, filter));
      const answer: Message = {role: "bot", text: reply.answer, sources: reply.sources, reason: reply.reason, query: msg, novel: filter};
      setMessages(m => retryIndex === undefined ? [...m, answer] : m.map((row, i) => i === retryIndex ? answer : row));
    } catch {
      const error: Message = {role: "bot", text: sid ? "검색에 실패했습니다. 다시 시도하세요." : "오류가 발생했습니다.", query: msg, novel: filter, failed: true};
      setMessages(m => retryIndex === undefined ? [...m, error] : m.map((row, i) => i === retryIndex ? error : row));
    } finally { lock.current = false; setLoading(false); }
  };

  return <div className="flex flex-col h-full text-ink ds-t-body" data-focus-zone="panel">
    <div className="flex-1 overflow-y-auto p-4 space-y-4" aria-live="polite">
      {messages.map((m, i) => <div key={i} className="space-y-3">
        <p className={`whitespace-pre-wrap rounded-card border border-line p-3 ${m.role === "user" ? "bg-soft ml-6" : "bg-paper"}`} role={m.failed ? "alert" : undefined}>{m.text}</p>
        {m.sources !== undefined && sid && <section className="space-y-3" aria-label="근거 원문">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="ds-t-card">근거 원문 {m.sources.length}건</h3>
            <Switch label="새 발견 찾기" checked={m.novel ?? true} disabled={loading} onChange={value => {setNovel(value);void send(m.query, value, i);}} />
          </div>
          {m.sources.length === 0 && <p role="status">{sourceEmptyMessage(m.reason, m.novel ?? true)}</p>}
          {m.sources.map(source => <SourceCard key={`${source.doc_id}:${known.find(item => item.type === "doc" && item.doc_id === source.doc_id)?.id ?? ""}`} sid={sid} version={version} source={source} readonly={readonly}
            known={known.some(item => item.type === "doc" && item.doc_id === source.doc_id)}
            onAdded={item => {setMessages(rows => rows.map((row, index) => index === i ? {...row, added: true} : row));onKnownAdded?.(item);}} />)}
          {m.added && <><p className="ds-t-caption">다음 검색부터 비슷한 원문이 빠집니다</p><Button disabled={loading} onClick={() => {setNovel(true);void send(m.query, true, i);}}>추가한 이야기 빼고 다시 찾기</Button></>}
        </section>}
        {m.failed && sid && <Button disabled={loading} onClick={() => void send(m.query, m.novel, i)}>다시 찾기</Button>}
      </div>)}
      {loading && <div role="status" className="space-y-3"><p>{sid ? "근거 원문을 찾고 있습니다…" : "응답을 기다리고 있습니다…"}</p><Skeleton /><Skeleton /></div>}
      <div ref={bottomRef} />
    </div>
    <form className="border-t border-line p-3 space-y-3" onSubmit={e => {e.preventDefault();void send();}}>
      {sid && <Switch label="새 발견 찾기" checked={novel} disabled={loading} onChange={setNovel} />}
      <div className="flex gap-2"><input aria-label="메시지" className="min-w-0 flex-1 border border-line rounded-input px-3 py-2 bg-paper" placeholder="메시지를 입력하세요..." value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => {if(e.key === "Enter" && e.nativeEvent.isComposing) e.preventDefault();}} />
        <Button type="submit" disabled={loading || !input.trim()}>전송</Button></div>
    </form>
  </div>;
}
