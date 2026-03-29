"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import SessionList from "@/components/SessionList";
import { useSessionStore } from "@/stores/useSessionStore";
import { saveSession } from "@/lib/api";
import { restoreSessionToStore } from "@/lib/sessionPersist";

const AGES = ["주부", "직장인", "1인가구", "신혼부부", "육아맘", "시니어", "대학생", "자영업"];
const RANGES = ["20대", "30대", "40대", "50대+"];
const GENDERS = ["남성", "여성"];

export default function StartPage() {
  const router = useRouter();
  const store = useSessionStore();
  const [bk, setBk] = useState("");
  const [pd, setPd] = useState("");
  const [ages, setAges] = useState<string[]>([]);
  const [ar, setAr] = useState<string[]>([]);
  const [gens, setGens] = useState<string[]>([]);

  const toggle = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  };

  const handleNew = async () => {
    if (!bk.trim()) return alert("키워드 입력");
    if (!pd.trim()) return alert("문제정의 입력");
    const sid = "s" + Date.now();
    const sd = { bk, problemDef: pd, ages, ageRange: ar, gens, allKw: [], sid, step: "r1" };
    store.setSession({ sid, bk, pd, ages, ar, gens, kw: [], step: "r1", sd });
    await saveSession(sid, sd);
    router.push("/pipeline/keywords");
  };

  const handleLoad = async (sid: string) => {
    try {
      const step = await restoreSessionToStore(sid, store);
      const routeMap: Record<string, string> = {
        start: "/pipeline/start", r1: "/pipeline/keywords", r2: "/pipeline/keywords",
        r3: "/pipeline/keywords", "r3-expand": "/pipeline/keywords", final: "/pipeline/keywords",
        "crawl-setup": "/pipeline/crawling", "crawl-start": "/pipeline/crawling",
        "preprocess-setup": "/pipeline/preprocess", "preprocess-start": "/pipeline/preprocess",
        labeling: "/pipeline/labeling", "labeling-done": "/pipeline/labeling",
        "train-start": "/pipeline/training", "train-check": "/pipeline/training",
        clustering: "/pipeline/clustering", "cluster-start": "/pipeline/clustering",
        "cluster-check": "/pipeline/clustering", "cluster-refine": "/pipeline/clustering",
        persona: "/pipeline/personas", "persona-start": "/pipeline/personas",
        "persona-check": "/pipeline/personas", "embed-start": "/pipeline/personas",
        "embed-check": "/pipeline/personas", done: "/pipeline/personas",
      };
      router.push(routeMap[step] || "/pipeline/start");
    } catch {
      alert("세션 로드 실패");
    }
  };

  return (
    <div>
      <SessionList onSelect={handleLoad} />
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
        <h3 className="text-lg font-semibold text-stone-800 tracking-tight">새로 시작</h3>
        <div className="mt-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">메인 키워드</label>
            <input className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" placeholder="예: 에어컨" value={bk} onChange={(e) => setBk(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">문제정의</label>
            <textarea className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" rows={3} placeholder="예: 에어컨 구매 시 소비자 고민 파악" value={pd} onChange={(e) => setPd(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">타겟</label>
            <div className="flex flex-wrap gap-2">
              {AGES.map((v) => (
                <span key={v} onClick={() => toggle(ages, v, setAges)} className={`px-3.5 py-1.5 rounded-full text-xs font-medium cursor-pointer border transition-all ${ages.includes(v) ? "bg-indigo-500 text-white border-indigo-500 shadow-sm" : "bg-white text-stone-600 border-stone-200 hover:border-stone-300 hover:bg-stone-50"}`}>{v}</span>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">나이대</label>
            <div className="flex flex-wrap gap-2">
              {RANGES.map((v) => (
                <span key={v} onClick={() => toggle(ar, v, setAr)} className={`px-3.5 py-1.5 rounded-full text-xs font-medium cursor-pointer border transition-all ${ar.includes(v) ? "bg-indigo-500 text-white border-indigo-500 shadow-sm" : "bg-white text-stone-600 border-stone-200 hover:border-stone-300 hover:bg-stone-50"}`}>{v}</span>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">성별</label>
            <div className="flex flex-wrap gap-2">
              {GENDERS.map((v) => (
                <span key={v} onClick={() => toggle(gens, v, setGens)} className={`px-3.5 py-1.5 rounded-full text-xs font-medium cursor-pointer border transition-all ${gens.includes(v) ? "bg-indigo-500 text-white border-indigo-500 shadow-sm" : "bg-white text-stone-600 border-stone-200 hover:border-stone-300 hover:bg-stone-50"}`}>{v}</span>
              ))}
            </div>
          </div>
          <button onClick={handleNew} className="w-full bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-indigo-600 active:scale-[0.99] shadow-sm transition-all mt-2">시작</button>
        </div>
      </div>
    </div>
  );
}
