"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { getSample, saveSession } from "@/lib/api";
import Spinner from "@/components/Spinner";
import ProgressBar from "@/components/ProgressBar";

interface SampleItem {
  title: string;
  desc: string;
  cafe: string;
  kw?: string;
  link?: string;
}

export default function LabelingPage() {
  const router = useRouter();
  const store = useSessionStore();
  const { sid, sd } = store;

  const [samples, setSamples] = useState<SampleItem[]>([]);
  const [labels, setLabels] = useState<Record<number, number>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const labeledCount = (sd?.labeledData as unknown[])?.length || 0;
  const targetCount = Math.ceil(total * 0.02);
  const pct = targetCount > 0 ? Math.min(100, Math.round((labeledCount / targetCount) * 100)) : 0;

  const loadSamples = async () => {
    setLoading(true);
    try {
      const d = await getSample(sid!, 2);
      setSamples((d.samples || []) as unknown as SampleItem[]);
      setTotal(d.total || 0);
      setLabels({});
    } catch {
      /* empty */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (sid) loadSamples();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  const setLabel = (i: number, v: number) => {
    setLabels((prev) => ({ ...prev, [i]: v }));
  };

  const handleSave = async () => {
    const items = Object.entries(labels).map(([i, v]) => ({
      ...samples[Number(i)],
      label: v,
    }));
    const existing = ((sd?.labeledData as unknown[]) || []) as Record<string, unknown>[];
    const updated = { ...sd!, labeledData: [...existing, ...items] } as unknown as typeof sd;
    store.setSession({ sd: updated! });
    await saveSession(sid!, updated as unknown as Record<string, unknown>);
    loadSamples();
  };

  const handleDone = async () => {
    const updated = { ...sd!, step: "train-start" };
    store.setSession({ sd: updated, step: "train-start" });
    await saveSession(sid!, updated as unknown as Record<string, unknown>);
    router.push("/pipeline/training");
  };

  return (
    <div>
      <button onClick={() => router.push("/pipeline/preprocess")} className="inline-flex items-center gap-1.5 text-stone-500 hover:text-stone-700 text-sm font-medium mb-4 transition-colors">← 전처리로</button>
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <h3 className="text-lg font-semibold text-stone-800 tracking-tight">라벨링</h3>
      </div>
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
        <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100">
          목표:{targetCount}건 | 완료:{labeledCount}건
          <ProgressBar percent={pct} />
        </div>
        {loading ? (
          <div className="flex items-center gap-2.5 text-stone-500 text-sm"><Spinner size={16} /> 샘플 로딩...</div>
        ) : (
          <div className="space-y-4">
            {samples.map((item, i) => (
              <div key={i} className="border border-stone-200 rounded-xl p-4 hover:border-stone-300 transition-colors">
                <div className="font-semibold text-sm text-stone-800 mb-1.5">{item.title}</div>
                <div className="text-stone-500 text-sm mb-1.5 leading-relaxed line-clamp-3">{item.desc}</div>
                <div className="text-xs text-blue-600 font-medium mb-3">{item.cafe}</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setLabel(i, 1)}
                    className={`flex-1 py-2 rounded-xl text-xs font-semibold border transition-all ${labels[i] === 1 ? "bg-emerald-500 text-white border-emerald-500 shadow-sm" : "bg-white text-emerald-600 border-emerald-300 hover:bg-emerald-50"}`}
                  >관련</button>
                  <button
                    onClick={() => setLabel(i, 0)}
                    className={`flex-1 py-2 rounded-xl text-xs font-semibold border transition-all ${labels[i] === 0 ? "bg-rose-500 text-white border-rose-500 shadow-sm" : "bg-white text-rose-600 border-rose-300 hover:bg-rose-50"}`}
                  >무관</button>
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-3 mt-5">
          <button onClick={handleSave} className="flex-1 bg-amber-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-amber-600 active:scale-[0.99] shadow-sm transition-all">저장 후 다음</button>
          <button onClick={handleDone} className="flex-1 bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all">완료 → 학습</button>
        </div>
      </div>
    </div>
  );
}
