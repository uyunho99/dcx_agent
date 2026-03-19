"use client";
import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { startTrain, getTrainStatus, saveSession } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import ProgressBar from "@/components/ProgressBar";
import Spinner from "@/components/Spinner";

export default function TrainingPage() {
  const router = useRouter();
  const store = useSessionStore();
  const { sid, bk, pd, sd } = store;

  const [started, setStarted] = useState(sd?.step === "train-check");

  const fetcher = useCallback(() => getTrainStatus(sid!), [sid]);
  const shouldStop = useCallback((d: Record<string, unknown>) => d.status === "done" || d.status === "error", []);
  const { data } = usePolling({ fetcher, interval: 5000, enabled: started && !!sid, shouldStop });

  const status = (data?.status as string) || "";
  const progress = (data?.progress as number) || 0;
  const phase = (data?.phase as string) || "";

  const handleStart = async () => {
    await startTrain({ sid, bk, problemDef: pd });
    setStarted(true);
  };

  const handleNext = async () => {
    const updated = { ...sd!, step: "clustering" };
    store.setSession({ sd: updated, step: "clustering" });
    await saveSession(sid!, updated);
    router.push("/pipeline/clustering");
  };

  if (!started) {
    return (
      <div>
        <button onClick={() => router.push("/pipeline/labeling")} className="inline-flex items-center gap-1.5 text-stone-500 hover:text-stone-700 text-sm font-medium mb-4 transition-colors">← 라벨링으로</button>
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          <h3 className="text-lg font-semibold text-stone-800 tracking-tight">학습</h3>
        </div>
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
          <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100">3중 준지도 + LLM 앙상블</div>
          <div className="grid grid-cols-4 gap-3 mb-5">
            {["LSTM", "CNN", "GRU", "Claude"].map((m) => (
              <div key={m} className="bg-stone-50 rounded-xl p-4 text-center border border-stone-100 hover:border-indigo-200 transition-colors">
                <b className="text-sm font-bold text-stone-700">{m.charAt(0) === "C" ? "LLM" : m.charAt(0)}{m.length > 1 ? m.slice(1, 2) : ""}</b>
                <div className="text-xs text-stone-400 mt-0.5">{m}</div>
              </div>
            ))}
          </div>
          <button onClick={handleStart} className="w-full bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-indigo-600 active:scale-[0.99] shadow-sm transition-all">학습 시작</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <h3 className="text-lg font-semibold text-stone-800 tracking-tight">학습 진행중</h3>
      </div>
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
        {status === "done" ? (
          <>
            <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl font-medium border border-indigo-100">
              완료! 전체:{((data?.total as number) || 0).toLocaleString()} 관련:{((data?.relevant as number) || 0).toLocaleString()} 무관:{((data?.irrelevant as number) || 0).toLocaleString()}
            </div>
            <ProgressBar percent={100} />
            <button onClick={handleNext} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all mt-5">클러스터링 →</button>
          </>
        ) : status === "error" ? (
          <div className="bg-rose-50 text-rose-700 text-sm px-4 py-3 rounded-xl border border-rose-100">{(data?.error as string) || "에러"}</div>
        ) : (
          <>
            <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium"><Spinner size={16} /> 진행중... ({phase})</div>
            <ProgressBar percent={progress} />
          </>
        )}
      </div>
    </div>
  );
}
