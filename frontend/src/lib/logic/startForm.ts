import type { ProjectContext } from "../types";

export const emptyStartForm: ProjectContext = {
  schemaVersion: 1, bk: "", oneLiner: "", researchQuestion: {text: ""},
  projectType: {choice: "", note: ""}, analysisGoal: {choice: "", note: ""},
  keyMetrics: [], constraints: [], positioning: {price: "", market: ""}, channels: [], knownInsights: [],
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
    const result = { ...source };
    for (const [key, value] of Object.entries(defaultValue)) result[key] = mergeDefaults(value, source[key]);
    return result;
  }
  return typeof loaded === typeof defaultValue ? loaded : defaultValue;
}

export function mergeStartForm(loaded: unknown): ProjectContext {
  return mergeDefaults(emptyStartForm, loaded) as ProjectContext;
}
