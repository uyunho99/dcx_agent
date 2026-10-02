import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { cardKeyTarget, ChoiceCards } from "./ChoiceCards";

describe("cardKeyTarget", () => {
  it.each([
    ["ArrowRight", 1, 2, 0],
    ["ArrowLeft", 0, 2, 1],
    ["ArrowDown", 0, 2, 1],
    ["ArrowUp", 0, 2, 1],
    ["Home", 1, 2, 0],
    ["End", 0, 2, 1],
    ["Enter", 0, 2, null],
    [" ", 0, 2, null],
    ["Tab", 0, 2, null],
    ["ArrowRight", 0, 1, 0],
    ["End", 0, 0, null],
  ])("%s from %i with %i cards returns %s", (key, index, count, target) => {
    expect(cardKeyTarget(key, index, count)).toBe(target);
  });
});

describe("ChoiceCards", () => {
  const options = [
    { value: "metric", label: "지표 개선형", description: "외부·사내 평가 지표를 올리는 과제입니다." },
    { value: "explore", label: "탐색·기획형", description: "아직 드러나지 않은 맥락과 기회를 찾는 과제입니다." },
  ];

  function render(value: string) {
    return renderToStaticMarkup(createElement(ChoiceCards, {
      label: "과제 유형", "aria-labelledby": "task-heading", "aria-describedby": "task-summary",
      options, value, onChange: () => {},
    }));
  }

  it("links the group heading and summary and renders radio buttons with descriptions", () => {
    const html = render("explore");
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-labelledby="task-heading"');
    expect(html).toContain('aria-describedby="task-summary"');
    expect(html.match(/type="button"/g)).toHaveLength(2);
    expect(html.match(/role="radio"/g)).toHaveLength(2);
    expect(html).toContain('aria-checked="false" tabindex="-1"');
    expect(html).toContain('aria-checked="true" tabindex="0"');
    expect(html).toContain('class="ds-t-label"');
    expect(html).toContain('class="ds-t-caption"');
    expect(html).toContain(options[1].description);
  });

  it("makes only the first card tabbable when nothing is selected", () => {
    const html = render("");
    expect(html.match(/tabindex="0"/g)).toHaveLength(1);
    expect(html).toContain('aria-checked="false" tabindex="0"');
    expect(html).not.toContain('aria-checked="true"');
  });
});
