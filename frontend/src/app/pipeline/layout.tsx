"use client";
import { useCallback } from "react";
import TopBar from "@/components/TopBar";
import StepBar from "@/components/StepBar";
import ChatPanel from "@/components/ChatPanel";
import { useSessionStore } from "@/stores/useSessionStore";
import { sendChat } from "@/lib/api";

export default function PipelineLayout({ children }: { children: React.ReactNode }) {
  const { sid, bk, kw, step } = useSessionStore();

  const handleChat = useCallback(
    async (msg: string) => {
      const STEPS = ["시작", "키워드", "크롤링", "전처리", "라벨링", "학습", "클러스터링", "페르소나"];
      const stepIdx = ["start", "r1", "r2", "r3", "crawl-setup", "preprocess-setup", "labeling", "train-start", "clustering", "persona"].indexOf(step);
      const ctx = `제품:${bk || "미설정"}, 세션:${sid || "없음"}, 현재단계:${STEPS[Math.max(0, stepIdx)] || "시작"}, 키워드:${kw.length}개`;
      const d = await sendChat({ sid, query: msg, pipeline_context: ctx });
      return d.answer || "응답 없음";
    },
    [sid, bk, kw, step],
  );

  return (
    <div className="flex flex-col h-screen">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        {/* Step sidebar */}
        <StepBar currentStep={step} />
        {/* Main content */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto p-6">{children}</div>
        </div>
        {/* Right panel - chatbot */}
        <div className="w-[400px] shrink-0 bg-white/60 backdrop-blur-xl flex flex-col shadow-[-4px_0_20px_rgba(0,0,0,0.06)] border-l border-white/30">
          <div className="px-5 py-3.5 border-b border-white/30 bg-white/40 backdrop-blur-sm font-semibold text-sm text-stone-700">
            💬 파이프라인 챗봇
          </div>
          <div className="flex-1 min-h-0">
            <ChatPanel
              initialMessage="안녕하세요! 파이프라인 진행이나 결과에 대해 물어보세요."
              onSend={handleChat}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
