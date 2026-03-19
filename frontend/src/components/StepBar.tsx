"use client";
import { useRouter } from "next/navigation";

const STEPS = [
  { name: "시작", icon: "🚀", path: "/pipeline/start" },
  { name: "키워드", icon: "🔑", path: "/pipeline/keywords" },
  { name: "크롤링", icon: "🌐", path: "/pipeline/crawling" },
  { name: "전처리", icon: "⚙️", path: "/pipeline/preprocess" },
  { name: "라벨링", icon: "🏷️", path: "/pipeline/labeling" },
  { name: "학습", icon: "🧠", path: "/pipeline/training" },
  { name: "클러스터링", icon: "📊", path: "/pipeline/clustering" },
  { name: "페르소나", icon: "👤", path: "/pipeline/personas" },
];

const STEP_MAP: Record<string, number> = {
  start: 0,
  r1: 1, r2: 1, r3: 1, "r3-expand": 1, final: 1,
  "crawl-setup": 2, "crawl-start": 2,
  "preprocess-setup": 3, "preprocess-start": 3,
  labeling: 4, "labeling-done": 4,
  "train-start": 5, "train-check": 5,
  clustering: 6, "cluster-start": 6, "cluster-check": 6, "cluster-refine": 6,
  persona: 7, "persona-start": 7, "persona-check": 7,
  "embed-start": 7, "embed-check": 7, done: 7,
};

export default function StepBar({ currentStep }: { currentStep: string }) {
  const router = useRouter();
  const idx = STEP_MAP[currentStep] ?? 0;

  return (
    <div className="w-56 shrink-0 bg-white/50 backdrop-blur-xl border-r border-white/30 flex flex-col py-3 overflow-y-auto">
      {/* Progress summary */}
      <div className="px-4 pb-3 mb-1 border-b border-stone-100/60">
        <div className="text-[11px] font-medium text-stone-400 uppercase tracking-wider mb-1.5">파이프라인</div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-stone-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full transition-all duration-500"
              style={{ width: `${((idx + 1) / STEPS.length) * 100}%` }}
            />
          </div>
          <span className="text-[11px] font-semibold text-indigo-600">{idx + 1}/{STEPS.length}</span>
        </div>
      </div>

      {/* Step list */}
      <nav className="flex flex-col gap-0.5 px-2">
        {STEPS.map((step, i) => {
          const isCompleted = i < idx;
          const isCurrent = i === idx;
          const isFuture = i > idx;

          return (
            <button
              key={i}
              onClick={() => router.push(step.path)}
              className={`
                relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-200 group
                ${isCurrent
                  ? "bg-indigo-50/80 backdrop-blur-sm shadow-sm"
                  : "hover:bg-white/60"
                }
              `}
            >
              {/* Step number / check */}
              <div
                className={`
                  w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 transition-all
                  ${isCompleted
                    ? "bg-emerald-500 text-white shadow-sm"
                    : isCurrent
                    ? "bg-indigo-500 text-white shadow-md shadow-indigo-200"
                    : "bg-stone-100 text-stone-400 group-hover:bg-stone-200"
                  }
                `}
              >
                {isCompleted ? "✓" : i + 1}
              </div>

              {/* Label */}
              <div className="flex flex-col min-w-0">
                <span
                  className={`text-sm leading-tight truncate transition-colors ${
                    isCurrent
                      ? "font-semibold text-indigo-700"
                      : isCompleted
                      ? "font-medium text-stone-600"
                      : "text-stone-400 group-hover:text-stone-600"
                  }`}
                >
                  {step.name}
                </span>
                {isCurrent && (
                  <span className="text-[10px] text-indigo-400 font-medium mt-0.5">진행 중</span>
                )}
                {isCompleted && (
                  <span className="text-[10px] text-emerald-500 font-medium mt-0.5">완료</span>
                )}
              </div>

              {/* Active indicator */}
              {isCurrent && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-indigo-500 rounded-r-full" />
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
