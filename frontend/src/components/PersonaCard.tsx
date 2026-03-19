import type { Persona } from "@/lib/types";

interface PersonaCardProps {
  persona: Persona;
}

export default function PersonaCard({ persona }: PersonaCardProps) {
  return (
    <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)] transition-shadow">
      <div className="text-sm font-bold text-indigo-600 mb-4">{persona.name}</div>
      <div className="border-l-[3px] border-blue-300 pl-3 mb-3">
        <span className="text-xs font-semibold text-blue-600 uppercase tracking-wide">상황</span>
        <p className="text-sm text-stone-600 mt-1 leading-relaxed">{persona.situation}</p>
      </div>
      <div className="border-l-[3px] border-rose-300 pl-3 mb-3">
        <span className="text-xs font-semibold text-rose-600 uppercase tracking-wide">Pain Point</span>
        <p className="text-sm text-stone-600 mt-1 leading-relaxed">{persona.pain_point}</p>
      </div>
      <div className="border-l-[3px] border-emerald-300 pl-3 bg-emerald-50/40 backdrop-blur-sm rounded-lg p-3">
        <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wide">인사이트</span>
        <p className="text-sm text-stone-600 mt-1 leading-relaxed">{persona.insight}</p>
      </div>
    </div>
  );
}
