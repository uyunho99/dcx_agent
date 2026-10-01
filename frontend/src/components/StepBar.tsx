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
  { name: "페르소나", path: "/pipeline/personas" },
];

export const STEP_MAP: Record<string, number> = {
  start: 0,
  r4: 1, "kw-final": 1, r1: 1, r2: 1, r3: 1, "r3-expand": 1, final: 1,
  "crawl-list": 2, "crawl-gate": 2, "crawl-detail": 2, "crawl-done": 2, "crawl-setup": 2, "crawl-start": 2,
  "preprocess-setup": 3, "preprocess-start": 3,
  labeling: 4, "labeling-done": 4,
  "train-start": 5, "train-check": 5,
  clustering: 6, "cluster-start": 6, "cluster-check": 6, "cluster-refine": 6,
  persona: 7, "persona-start": 7, "persona-check": 7,
  "embed-start": 7, "embed-check": 7, done: 7,
};

export function stepIndex(step: string) {
  if (step.startsWith("prep-")) return 3;
  if (step.startsWith("label-")) return 4;
  if (step.startsWith("train-")) return 5;
  return STEP_MAP[step] ?? 0;
}

export default function StepBar({ currentStep, session }: { currentStep: string; session?: Record<string, unknown> | null }) {
  const {confirmNavigation} = useDirty();
  // Saved step is exclusive; server completion includes the completed stage itself.
  const completed = completedThrough(session);
  const index = Math.max(stepIndex(currentStep), completed > 0 ? completed + 1 : 0);
  const pathname = usePathname();
  const viewed = STEPS.findIndex(step => step.path === pathname);
  return <div><div className="pipeline-group">파이프라인</div><nav className="pipeline-nav" aria-label="파이프라인 단계">{STEPS.map((step, i) => <Link key={step.path} href={step.path} onClick={e => {if(!confirmNavigation()) e.preventDefault();}} className={i === viewed ? "on" : i < index ? "done" : ""} aria-current={i === viewed ? "step" : undefined} aria-label={`${i + 1}. ${step.name}${i < index ? " 완료" : ""}`}><i className="n" aria-hidden="true">{i < index ? <Check size={14} /> : i + 1}</i><span>{step.name}</span>{i === viewed && <small>진행 중</small>}</Link>)}</nav></div>;
}
