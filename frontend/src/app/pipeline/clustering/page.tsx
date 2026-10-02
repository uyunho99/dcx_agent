"use client";
import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { startCluster, getClusterStatus, clusterRefine, saveSession } from "@/lib/api";
import { useVersion } from "@/components/versions/VersionProvider";
import { useStageCompletionRefresh } from "@/components/versions/useStageCompletionRefresh";
import { usePolling } from "@/lib/usePolling";
import ProgressBar from "@/components/ProgressBar";
import Spinner from "@/components/Spinner";

import { SegmentScreen } from "@/components/segment/SegmentScreen";
import type { SegmentDraft } from "@/lib/types";

export default function ClusteringPage() {
  const {sid, sd} = useSessionStore();
  const view = useVersion();
  const prep = sd?.prep as {derivedRef?: unknown} | undefined;
  if (prep?.derivedRef && sid) return <SegmentScreen key={`${sid}:${view.version ?? ''}`} sid={sid} version={view.version} readonly={view.readonly || !!view.conflict} draft={sd?.drafts?.segment as SegmentDraft | undefined} />;
  return <LegacyClusteringPage />;
}

function LegacyClusteringPage() {
  const router = useRouter();
  const readonly = true;
  const store = useSessionStore();
  const { sid, sd } = store;

  const [started, setStarted] = useState(["cluster-start", "cluster-check"].includes(sd?.step || ""));
  const [mergeInput, setMergeInput] = useState("");
  const [keepClusters, setKeepClusters] = useState<Set<string>>(new Set());

  const fetcher = useCallback(() => getClusterStatus(sid!), [sid]);
  const shouldStop = useCallback((d: Record<string, unknown>) => d.status === "done" || d.status === "error", []);
  const { data } = usePolling({ fetcher, interval: 4000, enabled: started && !!sid, shouldStop });

  const status = (data?.status as string) || "";
  useStageCompletionRefresh(status === "done" ? "clusters" : null);
  const progress = (data?.progress as number) || 0;
  const numClusters = (data?.num_clusters as number) || 0;
  const clusters = (data?.clusters as Record<string, { size: number; keywords: string[]; samples?: { title: string; desc: string; cafe: string; kw?: string }[] }>) || {};

  const handleStart = async () => {
    if (readonly) return;
    await startCluster({ sid });
    setStarted(true);
  };

  // Initialize keepClusters when done
  if (status === "done" && keepClusters.size === 0 && numClusters > 0) {
    const all = new Set<string>();
    for (let i = 0; i < numClusters; i++) all.add(String(i));
    setKeepClusters(all);
  }

  const toggleCluster = (id: string) => {
    setKeepClusters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleRefine = async () => {
    if (readonly) return;
    await clusterRefine({ sid, keepClusters: Array.from(keepClusters).join(","), mergeClusters: mergeInput });
    const updated = { ...sd!, step: "persona" };
    store.setSession({ sd: updated, step: "persona" });
    await saveSession(sid!, updated);
    router.push("/pipeline/personas");
  };

  if (!started) {
    return (
      <div>
        <button onClick={() => router.push("/pipeline/training")} className="inline-flex items-center gap-1.5 text-stone-500 hover:text-stone-700 text-sm font-medium mb-4 transition-colors">← 학습으로</button>
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          <p className="text-sm text-stone-500">옛 세션 · 읽기 전용</p><h3 className="text-lg font-semibold text-stone-800 tracking-tight">클러스터링</h3>
        </div>
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
          <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100">TF-IDF + K-means + Ward</div>
          <button disabled={readonly} onClick={handleStart} className="w-full bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-indigo-600 active:scale-[0.99] shadow-sm transition-all">시작</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <p className="text-sm text-stone-500">옛 세션 · 읽기 전용</p><h3 className="text-lg font-semibold text-stone-800 tracking-tight">클러스터링 {status === "done" ? "" : "진행중"}</h3>
      </div>
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
        {status === "done" ? (
          <>
            <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100">완료! {numClusters}개</div>
            <ProgressBar percent={100} />
            <div className="grid grid-cols-2 gap-3 mt-4">
              {Array.from({ length: numClusters }, (_, i) => {
                const c = clusters[String(i)] || {};
                const id = String(i);
                return (
                  <div key={i} className="border border-stone-200 rounded-xl p-4 hover:border-indigo-200 transition-colors">
                    <label className="flex items-start gap-2">
                      <input disabled={readonly} type="checkbox" checked={keepClusters.has(id)} onChange={() => toggleCluster(id)} className="mt-1 accent-indigo-500" />
                      <div>
                        <b className="text-sm font-semibold text-stone-800">클러스터 {i + 1}</b> <span className="text-stone-400 text-xs ml-1">({c.size || 0}건)</span>
                        <div className="text-xs text-stone-500 mt-1.5 leading-relaxed">{(c.keywords || []).slice(0, 5).join(", ")}</div>
                      </div>
                    </label>
                  </div>
                );
              })}
            </div>
            <div className="mt-4">
              <label className="block text-sm font-medium text-stone-700 mb-1.5">병합 (예: 1,3,5)</label>
              <input disabled={readonly} className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" placeholder="같은 주제 묶기" value={mergeInput} onChange={(e) => setMergeInput(e.target.value)} />
            </div>
            <button disabled={readonly} onClick={handleRefine} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all mt-5">정제 → 페르소나</button>
          </>
        ) : status === "error" ? (
          <div className="bg-rose-50 text-rose-700 text-sm px-4 py-3 rounded-xl border border-rose-100">{(data?.error as string) || "에러"}</div>
        ) : (
          <>
            <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium"><Spinner size={16} /> 처리 중... ({(data?.phase as string) || ""})</div>
            <ProgressBar percent={progress} />
          </>
        )}
      </div>
    </div>
  );
}
