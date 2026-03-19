"use client";
import { useSessionStore } from "@/stores/useSessionStore";

export default function TopBar() {
  const { bk, sid } = useSessionStore();
  return (
    <div className="flex items-center justify-between bg-white/70 backdrop-blur-xl px-6 h-14 shrink-0 border-b border-white/40 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h2 className="text-lg font-bold text-indigo-600 tracking-tight">DCX</h2>
      <span className="text-xs font-medium text-stone-500 bg-white/50 backdrop-blur-sm px-3 py-1 rounded-full border border-white/40">
        {bk && sid ? `${bk} | ${sid}` : "세션 없음"}
      </span>
    </div>
  );
}
