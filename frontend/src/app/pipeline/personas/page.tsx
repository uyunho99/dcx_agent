"use client";
import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { startEmbed, startPersona, getPersonaStatus, saveSession } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import ProgressBar from "@/components/ProgressBar";
import PersonaCard from "@/components/PersonaCard";
import Spinner from "@/components/Spinner";
import type { ClusterPersona } from "@/lib/types";

export default function PersonasPage() {
  const router = useRouter();
  const store = useSessionStore();
  const { sid, bk, pd, sd } = store;

  const [started, setStarted] = useState(["persona-start", "persona-check", "embed-start", "embed-check", "done"].includes(sd?.step || ""));

  const fetcher = useCallback(() => getPersonaStatus(sid!), [sid]);
  const shouldStop = useCallback((d: Record<string, unknown>) => d.status === "done" || d.status === "error", []);
  const { data } = usePolling({ fetcher, interval: 5000, enabled: started && !!sid, shouldStop });

  const status = (data?.status as string) || "";
  const progress = (data?.progress as number) || 0;
  const personas = (data?.personas as ClusterPersona[]) || [];

  const handleStart = async () => {
    setStarted(true);
    try {
      await startEmbed({ sid });
    } catch {
      // embedding skip ok
    }
    await startPersona({ sid, bk, problemDef: pd });
    const updated = { ...sd!, step: "persona-start" };
    store.setSession({ sd: updated, step: "persona-start" });
    await saveSession(sid!, updated);
  };

  if (!started) {
    return (
      <div>
        <button onClick={() => router.push("/pipeline/clustering")} className="inline-flex items-center gap-1.5 text-stone-500 hover:text-stone-700 text-sm font-medium mb-4 transition-colors">← 클러스터링으로</button>
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          <h3 className="text-lg font-semibold text-stone-800 tracking-tight">페르소나 도출</h3>
        </div>
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
          <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100">Claude가 클러스터별 페르소나를 도출합니다.</div>
          <button onClick={handleStart} className="w-full bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-indigo-600 active:scale-[0.99] shadow-sm transition-all mb-3">페르소나 도출 시작</button>
          <p className="text-stone-400 text-xs">임베딩 + 페르소나 도출이 자동 진행됩니다</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <h3 className="text-lg font-semibold text-stone-800 tracking-tight">페르소나 도출{status === "done" ? " 완료" : "중"}</h3>
      </div>
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
        {status === "done" ? (
          <>
            <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100">완료! {personas.length}개 클러스터</div>
            <ProgressBar percent={100} />
            <div className="space-y-6 mt-5">
              {personas.map((cl) => (
                <div key={cl.cluster_id}>
                  <div className="text-base font-bold text-indigo-600 mb-3 px-5 py-3 bg-gradient-to-r from-indigo-50/70 to-violet-50/70 backdrop-blur-sm rounded-xl border border-indigo-100">
                    {cl.cluster_name || `클러스터 ${cl.cluster_id}`}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {cl.personas.map((p, i) => (
                      <PersonaCard key={i} persona={p} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button onClick={() => router.push("/pipeline/start")} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all mt-6">처음으로</button>
          </>
        ) : status === "error" ? (
          <div className="bg-rose-50 text-rose-700 text-sm px-4 py-3 rounded-xl border border-rose-100">{(data?.error as string) || "에러"}</div>
        ) : (
          <>
            <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium"><Spinner size={16} /> Claude 분석중... {progress}%</div>
            <ProgressBar percent={progress} />
          </>
        )}
      </div>
    </div>
  );
}
