import type { ProjectContext } from "../types";
import { josa } from "./josa";

type Positioning = ProjectContext["positioning"];
type PositionAxis = "price" | "market";
type TaskMode = ProjectContext["taskMode"];
type PersonaSeed = NonNullable<ProjectContext["personaSeeds"]>["items"][number];
type PersonaDimension = NonNullable<PersonaSeed["dimension"]>;

export const emptyStartForm: ProjectContext = {
  schemaVersion: 1, bk: "", oneLiner: "", researchQuestion: {text: ""},
  projectType: {choice: "", note: ""}, taskMode: "explore",
  personaSeeds: {items: [], exploreBeyond: true},
  keyMetrics: [], constraints: [], positioning: {price: "", market: "", priceText: "", marketText: ""}, channels: [], knownInsights: [],
  productCategory: {l1: "", l2: "", l3: "", source: "user"},
  targetScope: {ageRanges: [], genders: [], households: [], lifeStages: [], note: ""}, futureCustomer: {choices: [], note: ""},
};

// Undefined means the PATCH must omit step to preserve later-stage progress.
export function nextStepOnStart(currentStep?: string | null): "r1" | undefined {
  return !currentStep || currentStep === "start" ? "r1" : undefined;
}

function mergeDefaults(defaultValue: unknown, loaded: unknown): unknown {
  if (loaded == null) return structuredClone(defaultValue);
  if (Array.isArray(defaultValue)) return Array.isArray(loaded) ? structuredClone(loaded) : structuredClone(defaultValue);
  if (defaultValue && typeof defaultValue === "object") {
    const source = typeof loaded === "object" && !Array.isArray(loaded) ? loaded as Record<string, unknown> : {};
    const result = structuredClone(source);
    for (const [key, value] of Object.entries(defaultValue)) result[key] = mergeDefaults(value, source[key]);
    return result;
  }
  return typeof loaded === typeof defaultValue ? loaded : defaultValue;
}

export function mergeStartForm(loaded: unknown): ProjectContext {
  const form = mergeDefaults(emptyStartForm, loaded) as ProjectContext;
  form.keyMetrics = form.keyMetrics.map(metric => mergeDefaults(
    { name: "", source: "", item: "" },
    typeof metric === "string" ? { name: metric } : metric,
  ) as ProjectContext["keyMetrics"][number]);
  // Old drafts without a goal choice must not submit an invalid enum, even with a note.
  if (form.analysisGoal?.choice === "") form.analysisGoal = null;
  return form;
}


/** Inspect the raw saved context before mergeStartForm supplies the new defaults. */
export function isPreTaskModeContext(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && (value as Record<string, unknown>).taskMode == null;
}

export function validateStartForm(form: ProjectContext): {
  valid: boolean;
  errors: Partial<Record<keyof ProjectContext, string>>;
} {
  const errors: Partial<Record<keyof ProjectContext, string>> = {};
  if (!form.bk.trim()) errors.bk = "제품명을 입력하세요.";
  if (!form.oneLiner.trim()) errors.oneLiner = "한줄 정의를 입력하세요.";
  if (!form.projectType.choice.trim()) errors.projectType = "프로젝트 성격을 선택하세요.";
  if (!form.researchQuestion.text.trim()) errors.researchQuestion = "리서치 질문을 입력하세요.";
  if (form.taskMode === "metric" && !form.keyMetrics.some(metric => metric.name.trim())) {
    errors.keyMetrics = "지표를 하나 이상 추가하세요.";
  }
  if (!form.channels.length) errors.channels = "채널을 하나 이상 선택하세요.";
  return { valid: Object.keys(errors).length === 0, errors };
}

export function researchTemplates(taskMode: TaskMode, bk: string): { id: string; title: string; text: string }[] {
  const product = bk || "제품";
  const object = `${product}${josa(product, "을/를")}`;
  if (taskMode === "metric") return [
    { id: "m1", title: "막히는 순간 탐색하기", text: `${object} 이용하는 사람들은 어느 단계, 어느 순간에 막히거나 기다리는가?` },
    { id: "m2", title: "평가가 낮은 순간 탐색하기", text: `${product} 이용 경험 평가가 낮게 나오는 순간, 사람들은 무엇을 겪고 있는가?` },
    { id: "m3", title: "불안 · 헷갈림 탐색하기", text: `${object} 이용하는 사람들은 언제, 무엇 때문에 불안하거나 헷갈려하는가?` },
  ];
  return [
    { id: "1", title: "사용 중 불편 탐색하기", text: `${object} 쓰는 사람들은 언제·어디서·무엇을 하다가 어떤 불편을 겪는가?` },
    { id: "2", title: "비사용자의 망설임 탐색하기", text: `${object} 아직 안 쓰는 사람들은 무엇 때문에 망설이는가?` },
    { id: "3", title: "대체 방법과 이유 탐색하기", text: `${object} 대신해 사람들이 쓰는 방법은 무엇이고, 왜 그 방법을 택하는가?` },
    { id: "4", title: "드러나지 않은 맥락 탐색하기", text: `${product}${josa(product, "와/과")} 관련해 사람들이 아직 말하지 않은 생활 속 맥락과 필요는 무엇인가?` },
  ];
}

export function toggleChoice(current: string | null, choice: string): string {
  return current === choice ? "" : choice;
}

export function choosePositionPreset(position: Positioning, axis: PositionAxis, preset: string): Positioning {
  return { ...position, [axis]: toggleChoice(position[axis], preset), [`${axis}Text`]: "" };
}

function shortText(value: string): string {
  return Array.from(value.trim()).slice(0, 40).join("").trim();
}

export function setPositionText(position: Positioning, axis: PositionAxis, text: string): Positioning {
  return { ...position, [axis]: "", [`${axis}Text`]: shortText(text) };
}

export function positioningOpen(taskMode: TaskMode, position: Positioning): boolean {
  return taskMode !== "metric" || [position.price, position.market, position.priceText, position.marketText]
    .some(value => Boolean(value?.trim()));
}

export function addPersonaSeed(items: PersonaSeed[], input: string): {
  items: PersonaSeed[];
  reason?: "empty" | "duplicate" | "limit";
} {
  const text = shortText(input);
  if (!text) return { items, reason: "empty" };
  const withoutWhitespace = (value: string) => value.replace(/\s/g, "");
  if (items.some(item => withoutWhitespace(item.text) === withoutWhitespace(text))) {
    return { items, reason: "duplicate" };
  }
  if (items.length >= 20) return { items, reason: "limit" };
  return { items: [...items, { text, dimension: null }] };
}

export function missingDimensions(items: PersonaSeed[]): PersonaDimension[] {
  const dimensions: PersonaDimension[] = ["social", "taste", "movement", "bio"];
  return dimensions.filter(dimension => !items.some(item => item.dimension === dimension));
}
