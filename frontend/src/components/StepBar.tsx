"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check } from "lucide-react";

import { completedThrough } from "@/lib/logic/completedThrough";

import { useDirty } from "./DirtyProvider";

const STEPS = [
  { name: "시작", path: "/pipeline/start" },
  { name: "키워드", path: "/pipeline/keywords" },
  { name: "크롤링", path: "/pipeline/crawling" },
  { name: "전처리", path: "/pipeline/preprocess" },
  { name: "라벨링", path: "/pipeline/labeling" },
  { name: "학습", path: "/pipeline/training" },
  { name: "클러스터링", path: "/pipeline/clustering" },
  { name: "근거 탐색", path: null },
  { name: "페르소나", path: "/pipeline/personas" },
  { name: "인사이트", path: null },
];

export const STEP_MAP: Record<string, number> = {
  start: 0,
  r4: 1, "kw-final": 1, r1: 1, r2: 1, r3: 1, "r3-expand": 1, final: 1,
  "crawl-list": 2, "crawl-gate": 2, "crawl-detail": 2, "crawl-done": 2, "crawl-setup": 2, "crawl-start": 2,
  "preprocess-setup": 3, "preprocess-start": 3,
  labeling: 4, "labeling-done": 4,
  "train-start": 5, "train-check": 5,
  clustering: 6, "cluster-start": 6, "cluster-check": 6, "cluster-refine": 6,
  persona: 8, "persona-start": 8, "persona-check": 8,
  "embed-start": 8, "embed-check": 8, done: 8,
};

export function stepIndex(step: string) {
  if (step.startsWith("prep-")) return 3;
  if (step.startsWith("label-")) return 4;
  if (step.startsWith("train-")) return 5;
  if (step.startsWith("cluster-")) return 6;
  if (step.startsWith("evidence")) return 7;
  if (step.startsWith("persona-") || step.startsWith("embed-")) return 8;
  if (step.startsWith("insight")) return 9;
  return STEP_MAP[step] ?? 0;
}

export default function StepBar({ currentStep, session }: { currentStep: string; session?: Record<string, unknown> | null }) {
  const { confirmNavigation } = useDirty();
  // Saved step is exclusive; server completion includes the completed stage itself.
  const completed = completedThrough(session);
  const index = Math.max(stepIndex(currentStep), completed > 0 ? completed + 1 : 0);
  const pathname = usePathname();
  const viewed = STEPS.findIndex(step => step.path === pathname);
  return <div>
    <div className="pipeline-group">파이프라인</div>
    <nav className="pipeline-nav" aria-label="파이프라인 단계">{STEPS.map((step, i) => {
    const props = {
      className: i === viewed ? "on" : i < index ? "done" : "",
      "aria-current": i === viewed ? "step" as const : undefined,
      "aria-label": `${i + 1}. ${step.name}${i < index ? " 완료" : ""}`,
    };
    const content = <>
      <i className="n" aria-hidden="true">{i < index ? <Check size={14} /> : i + 1}</i>
      <span>{step.name}</span>
      {i === viewed && <small>진행 중</small>}
    </>;
    return step.path === null
      ? <a key={step.name} {...props} role="link" aria-disabled="true" title="다음 묶음에서 열립니다">{content}</a>
      : <Link key={step.name} {...props} href={step.path} onClick={e => {
        if (!confirmNavigation()) e.preventDefault();
      }}>{content}</Link>;
    })}</nav>
  </div>;
}
