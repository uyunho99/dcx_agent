import { describe, expect, it } from "vitest";
import { addPersonaSeed, choosePositionPreset, emptyStartForm, isPreTaskModeContext, mergeStartForm, missingDimensions, nextStepOnStart, positioningOpen, researchTemplates, setPositionText, toggleChoice, validateStartForm } from "./startForm";

describe("nextStepOnStart", () => {
  it.each([undefined, null, "", "start"])("starts R1 from %s", step => {
    expect(nextStepOnStart(step)).toBe("r1");
  });
  it.each(["r1", "r3", "crawl-setup", "done"])("leaves %s unchanged", step => {
    expect(nextStepOnStart(step)).toBeUndefined();
  });
});

describe("mergeStartForm", () => {
  it("restores defaults for null or missing drafts", () => {
    expect(mergeStartForm(null)).toEqual(emptyStartForm);
    expect(mergeStartForm(undefined)).toEqual(emptyStartForm);
  });
  it("fills missing nested fields in partial drafts without mutating defaults", () => {
    const partial = { bk: "제품", researchQuestion: { template: "1" }, positioning: { price: "premium" }, targetScope: { genders: ["여성"] }, projectType: null };
    const merged = mergeStartForm(partial);
    expect(merged).toEqual({ ...emptyStartForm, bk: "제품", researchQuestion: { text: "", template: "1" }, positioning: { price: "premium", market: "", priceText: "", marketText: "" }, targetScope: { ...emptyStartForm.targetScope, genders: ["여성"] } });
    merged.channels.push("blog");
    expect(emptyStartForm.channels).toEqual([]);
    expect(partial.targetScope.genders).toEqual(["여성"]);
  });
  it("preserves a full form including arrays and optional fields", () => {
    const full = { schemaVersion: 1 as const, bk: "제품", oneLiner: "설명", researchQuestion: { text: "질문", template: "2" }, projectType: { choice: "new", note: "성격" }, analysisGoal: { choice: "discover", note: "목적" }, keyMetrics: ["지표"], constraints: ["제약"], positioning: { price: "premium", market: "mass" }, channels: ["blog"], knownInsights: ["발견"], productCategory: { l1: "대", l2: "중", l3: "소", source: "user" as const }, targetScope: { ageRanges: ["20대"], genders: ["여성"], households: ["single"], lifeStages: ["student"], note: "대상" }, futureCustomer: { choices: ["new"], note: "미래" } };
    expect(mergeStartForm(full)).toEqual({ ...full, taskMode: "explore", keyMetrics: [{ name: "지표", source: "", item: "" }], positioning: { ...full.positioning, priceText: "", marketText: "" }, personaSeeds: { items: [], exploreBeyond: true } });
  });
});


const minimal = () => mergeStartForm({ bk: "제품", oneLiner: "설명", researchQuestion: { text: "질문" }, projectType: { choice: "new" }, channels: ["naver_blog"] });
const blankPosition = { price: "", market: "", priceText: "", marketText: "" };

describe("task-mode defaults and migration", () => {
  it("starts in explore mode without analysisGoal", () => {
    expect(emptyStartForm.taskMode).toBe("explore");
    expect("analysisGoal" in emptyStartForm).toBe(false);
    expect(emptyStartForm.personaSeeds).toEqual({ items: [], exploreBeyond: true });
    expect(emptyStartForm.positioning).toEqual(blankPosition);
  });
  it("converts legacy and mixed metrics and preserves analysisGoal", () => {
    const goal = { choice: "needs", note: "x" };
    const loaded = { keyMetrics: ["편의성", { name: "만족도", source: "평가" }], analysisGoal: goal };
    const merged = mergeStartForm(loaded);
    expect(merged.keyMetrics).toEqual([{ name: "편의성", source: "", item: "" }, { name: "만족도", source: "평가", item: "" }]);
    expect(merged.analysisGoal).toEqual(goal);
    expect(merged.taskMode).toBe("explore");
    merged.analysisGoal!.note = "changed";
    expect(goal.note).toBe("x");
  });
  it("normalizes a legacy goal with a note but no choice", () => {
    const merged = mergeStartForm({ ...minimal(), taskMode: undefined, analysisGoal: { choice: "", note: "메모" } });
    expect(merged.analysisGoal).toBeNull();
    expect(validateStartForm(merged).valid).toBe(true);
  });
  it("normalizes null server defaults and blank legacy goals", () => {
    const merged = mergeStartForm({ ...minimal(), taskMode: null, personaSeeds: null, positioning: { price: null, market: null }, analysisGoal: { choice: "", note: "" } });
    expect(merged.taskMode).toBe("explore");
    expect(merged.positioning).toEqual(blankPosition);
    expect(merged.personaSeeds).toEqual({ items: [], exploreBeyond: true });
    expect(merged.analysisGoal).toBeNull();
    expect(validateStartForm(merged).valid).toBe(true);
  });
  it.each([[{ bk: "a" }, true], [{ taskMode: null }, true], [{ taskMode: "metric" }, false], [null, false]])("detects pre-task-mode contexts: %j", (value, expected) => {
    expect(isPreTaskModeContext(value)).toBe(expected);
  });
});

describe("validateStartForm", () => {
  it("accepts the minimal explore form with no metrics, positioning or analysisGoal", () => {
    expect(validateStartForm(minimal())).toEqual({ valid: true, errors: {} });
  });
  it.each([{ keyMetrics: [] }, { keyMetrics: [{ name: " ", source: "", item: "" }] }])("requires a named metric in metric mode: %j", ({ keyMetrics }) => {
    expect(validateStartForm({ ...minimal(), taskMode: "metric", keyMetrics })).toEqual({ valid: false, errors: { keyMetrics: "지표를 하나 이상 추가하세요." } });
  });
  it("accepts metric mode with a named metric and no positioning", () => {
    expect(validateStartForm({ ...minimal(), taskMode: "metric", keyMetrics: [{ name: "편의성", source: "", item: "" }] }).valid).toBe(true);
  });
  it("reports every required base field", () => {
    expect(validateStartForm({ ...emptyStartForm, bk: " ", oneLiner: "\t", researchQuestion: { text: " " } })).toEqual({ valid: false, errors: {
      bk: "제품명을 입력하세요.", oneLiner: "한줄 정의를 입력하세요.", researchQuestion: "리서치 질문을 입력하세요.", projectType: "프로젝트 성격을 선택하세요.", channels: "채널을 하나 이상 선택하세요.",
    } });
  });
});

describe("researchTemplates", () => {
  it("preserves all three existing question strings and adds explore template 4", () => {
    expect(researchTemplates("explore", "세라젬 모듈러 주택")).toEqual([
      { id: "1", title: "사용 중 불편 탐색하기", text: "세라젬 모듈러 주택을 쓰는 사람들은 언제·어디서·무엇을 하다가 어떤 불편을 겪는가?" },
      { id: "2", title: "비사용자의 망설임 탐색하기", text: "세라젬 모듈러 주택을 아직 안 쓰는 사람들은 무엇 때문에 망설이는가?" },
      { id: "3", title: "대체 방법과 이유 탐색하기", text: "세라젬 모듈러 주택을 대신해 사람들이 쓰는 방법은 무엇이고, 왜 그 방법을 택하는가?" },
      { id: "4", title: "드러나지 않은 맥락 탐색하기", text: "세라젬 모듈러 주택과 관련해 사람들이 아직 말하지 않은 생활 속 맥락과 필요는 무엇인가?" },
    ]);
  });
  it("uses the exact metric copy", () => {
    expect(researchTemplates("metric", "서울아산병원")).toEqual([
      { id: "m1", title: "막히는 순간 탐색하기", text: "서울아산병원을 이용하는 사람들은 어느 단계, 어느 순간에 막히거나 기다리는가?" },
      { id: "m2", title: "평가가 낮은 순간 탐색하기", text: "서울아산병원 이용 경험 평가가 낮게 나오는 순간, 사람들은 무엇을 겪고 있는가?" },
      { id: "m3", title: "불안 · 헷갈림 탐색하기", text: "서울아산병원을 이용하는 사람들은 언제, 무엇 때문에 불안하거나 헷갈려하는가?" },
    ]);
  });
  it("falls back to 제품 and chooses the Korean particle", () => {
    expect(researchTemplates("explore", "")[0].text).toBe("제품을 쓰는 사람들은 언제·어디서·무엇을 하다가 어떤 불편을 겪는가?");
    expect(researchTemplates("metric", "")[0].text).toBe("제품을 이용하는 사람들은 어느 단계, 어느 순간에 막히거나 기다리는가?");
    expect(researchTemplates("explore", "서비스")[3].text).toBe("서비스와 관련해 사람들이 아직 말하지 않은 생활 속 맥락과 필요는 무엇인가?");
    expect(researchTemplates("explore", "서비스")[0].text).toContain("서비스를 쓰는");
  });
});

describe("positioning", () => {
  it("toggles a selected choice off", () => {
    expect(toggleChoice("premium", "premium")).toBe("");
    expect(toggleChoice("", "value")).toBe("value");
  });
  it.each(["price", "market"] as const)("keeps preset and text exclusive on %s without changing the other axis", axis => {
    const textKey = axis === "price" ? "priceText" : "marketText";
    const preset = axis === "price" ? "premium" : "new";
    const initial = { ...blankPosition, [textKey]: "중상가" };
    const chosen = choosePositionPreset(initial, axis, preset);
    expect(chosen).toEqual({ ...initial, [axis]: preset, [textKey]: "" });
    expect(choosePositionPreset(chosen, axis, preset)[axis]).toBe("");
    expect(setPositionText(chosen, axis, "  중상가 · 구독형 ")).toEqual({ ...initial, [axis]: "", [textKey]: "중상가 · 구독형" });
    expect(setPositionText(chosen, axis, "가".repeat(45))[textKey]).toBe("가".repeat(40));
    expect(initial[textKey]).toBe("중상가");
  });
  it("opens in explore mode or when metric mode has any saved positioning", () => {
    expect(positioningOpen("metric", blankPosition)).toBe(false);
    expect(positioningOpen("explore", blankPosition)).toBe(true);
    for (const key of ["price", "market", "priceText", "marketText"] as const) {
      expect(positioningOpen("metric", { ...blankPosition, [key]: key === "market" ? "new" : "값" })).toBe(true);
    }
  });
});

describe("persona seeds", () => {
  it("trims a seed and adds it without a dimension", () => {
    expect(addPersonaSeed([], " 초진 보호자 ")).toEqual({ items: [{ text: "초진 보호자", dimension: null }] });
  });
  it("rejects whitespace-only and duplicate names ignoring whitespace", () => {
    const items = [{ text: "초진 보호자", dimension: null }];
    expect(addPersonaSeed(items, "   ")).toEqual({ items, reason: "empty" });
    expect(addPersonaSeed(items, "초진  보호자")).toEqual({ items, reason: "duplicate" });
    expect(addPersonaSeed(items, "초진보호자")).toEqual({ items, reason: "duplicate" });
    expect(items).toEqual([{ text: "초진 보호자", dimension: null }]);
  });
  it("rejects a 21st seed", () => {
    const items = Array.from({ length: 20 }, (_, i) => ({ text: String(i), dimension: null }));
    expect(addPersonaSeed(items, "다른 사람")).toEqual({ items, reason: "limit" });
  });
  it("truncates to 40 characters before duplicate detection", () => {
    expect(addPersonaSeed([], "가".repeat(45))).toEqual({ items: [{ text: "가".repeat(40), dimension: null }] });
    expect(addPersonaSeed([{ text: "가".repeat(40), dimension: null }], "가".repeat(41)).reason).toBe("duplicate");
  });
  it("lists missing dimensions in design order", () => {
    expect(missingDimensions([{ text: "a", dimension: "social" }, { text: "b", dimension: "bio" }])).toEqual(["taste", "movement"]);
    expect(missingDimensions([])).toEqual(["social", "taste", "movement", "bio"]);
    expect(missingDimensions([{ text: "a", dimension: null }])).toEqual(["social", "taste", "movement", "bio"]);
    expect(missingDimensions((["social", "taste", "movement", "bio"] as const).map(dimension => ({ text: dimension, dimension })))).toEqual([]);
  });
});
