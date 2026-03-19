"use client";
import { useState, useRef, useEffect } from "react";

interface Message {
  role: "user" | "bot";
  text: string;
}

interface ChatPanelProps {
  initialMessage: string;
  onSend: (msg: string) => Promise<string>;
}

export default function ChatPanel({ initialMessage, onSend }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "bot", text: initialMessage },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const answer = await onSend(msg);
      setMessages((m) => [...m, { role: "bot", text: answer }]);
    } catch {
      setMessages((m) => [...m, { role: "bot", text: "오류가 발생했습니다." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] px-4 py-2.5 text-sm whitespace-pre-wrap shadow-sm ${
                m.role === "user"
                  ? "bg-indigo-500 text-white rounded-2xl rounded-br-sm"
                  : "bg-white/60 backdrop-blur-sm border border-white/40 text-stone-700 rounded-2xl rounded-bl-sm"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/60 backdrop-blur-sm border border-white/40 px-4 py-2.5 rounded-2xl rounded-bl-sm shadow-sm">
              <div className="w-4 h-4 border-2 border-stone-300 border-t-indigo-400 rounded-full animate-spin" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-white/30 p-3 flex gap-2 bg-white/40 backdrop-blur-md">
        <input
          className="flex-1 border border-white/40 rounded-xl px-4 py-2.5 text-sm bg-white/70 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300 placeholder:text-stone-400"
          placeholder="메시지를 입력하세요..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
        />
        <button
          onClick={send}
          disabled={loading}
          className="bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-indigo-600 active:scale-[0.98] disabled:opacity-40 shadow-sm"
        >
          전송
        </button>
      </div>
    </div>
  );
}
