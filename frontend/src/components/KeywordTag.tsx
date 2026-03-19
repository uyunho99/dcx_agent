"use client";

interface KeywordTagProps {
  kw: string;
  score?: number;
  variant: "old" | "new" | "approved" | "rejected";
  onClick?: () => void;
}

function scoreClass(score: number) {
  if (score >= 70) return "text-emerald-700 bg-emerald-100";
  if (score >= 50) return "text-amber-700 bg-amber-100";
  return "text-rose-700 bg-rose-100";
}

export default function KeywordTag({ kw, score, variant, onClick }: KeywordTagProps) {
  const base = "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all select-none hover:scale-[1.03]";
  const styles: Record<string, string> = {
    old: "bg-stone-100/70 backdrop-blur-sm text-stone-500",
    new: "bg-indigo-50/70 backdrop-blur-sm text-indigo-700 border border-indigo-200/60 shadow-sm",
    approved: "bg-indigo-50/70 backdrop-blur-sm text-indigo-700 border border-indigo-200/60 shadow-sm",
    rejected: "bg-stone-50/50 text-stone-400 line-through opacity-50",
  };

  return (
    <span className={`${base} ${styles[variant]}`} onClick={onClick}>
      {kw}
      {score !== undefined && (
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${scoreClass(score)}`}>
          {score}
        </span>
      )}
    </span>
  );
}
