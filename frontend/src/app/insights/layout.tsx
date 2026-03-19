"use client";
import { useCallback } from "react";
import TopBar from "@/components/TopBar";
import ChatPanel from "@/components/ChatPanel";
import { useSessionStore } from "@/stores/useSessionStore";
import { sendInsightChat } from "@/lib/api";

export default function InsightsLayout({ children }: { children: React.ReactNode }) {
  const { sid, bk } = useSessionStore();

  const handleChat = useCallback(
    async (msg: string) => {
      if (!sid) return "세션을 먼저 선택하세요.";
      const d = await sendInsightChat({ sid, query: msg, bk });
      return d.answer || "응답 없음";
    },
    [sid, bk],
  );

  return (
    <div className="flex flex-col h-screen">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex border-b border-white/30 bg-white/60 backdrop-blur-lg shrink-0">
            <a href="/pipeline/start" className="px-6 py-3 text-sm font-medium text-stone-400 border-b-2 border-transparent hover:text-stone-600 transition-colors">파이프라인</a>
            <span className="px-6 py-3 text-sm font-semibold text-indigo-600 border-b-2 border-indigo-500">인사이트</span>
          </div>
          <div className="flex-1 overflow-y-auto p-6">{children}</div>
        </div>
        <div className="w-[400px] shrink-0 bg-white/60 backdrop-blur-xl flex flex-col shadow-[-4px_0_20px_rgba(0,0,0,0.06)] border-l border-white/30">
          <div className="px-5 py-3.5 border-b border-teal-400/30 bg-teal-500/90 backdrop-blur-sm font-semibold text-sm text-white">인사이트 챗봇</div>
          <div className="flex-1 min-h-0">
            <ChatPanel
              initialMessage="페르소나와 클러스터 인사이트를 분석할 수 있습니다."
              onSend={handleChat}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
