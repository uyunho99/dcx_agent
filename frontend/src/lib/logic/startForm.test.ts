import { describe, expect, it } from "vitest";
import { emptyStartForm, mergeStartForm, nextStepOnStart } from "./startForm";

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
    expect(merged).toEqual({ ...emptyStartForm, bk: "제품", researchQuestion: { text: "", template: "1" }, positioning: { price: "premium", market: "" }, targetScope: { ...emptyStartForm.targetScope, genders: ["여성"] } });
    merged.channels.push("blog");
    expect(emptyStartForm.channels).toEqual([]);
    expect(partial.targetScope.genders).toEqual(["여성"]);
  });
  it("preserves a full form including arrays and optional fields", () => {
    const full = { schemaVersion: 1 as const, bk: "제품", oneLiner: "설명", researchQuestion: { text: "질문", template: "2" }, projectType: { choice: "new", note: "성격" }, analysisGoal: { choice: "discover", note: "목적" }, keyMetrics: ["지표"], constraints: ["제약"], positioning: { price: "premium", market: "mass" }, channels: ["blog"], knownInsights: ["발견"], productCategory: { l1: "대", l2: "중", l3: "소", source: "user" as const }, targetScope: { ageRanges: ["20대"], genders: ["여성"], households: ["single"], lifeStages: ["student"], note: "대상" }, futureCustomer: { choices: ["new"], note: "미래" } };
    expect(mergeStartForm(full)).toEqual(full);
  });
});
