"use client";
import type { AriaAttributes, KeyboardEvent } from "react";

export type ChoiceCardOption = { value: string; label: string; description: string };
export type ChoiceCardsProps = Pick<AriaAttributes, "aria-labelledby" | "aria-describedby"> & {
  label?: string;
  options: ChoiceCardOption[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
};

export function cardKeyTarget(key: string, index: number, count: number): number | null {
  if (count <= 0) return null;
  switch (key) {
    case "Home": return 0;
    case "End": return count - 1;
    case "ArrowLeft":
    case "ArrowUp": return (index - 1 + count) % count;
    case "ArrowRight":
    case "ArrowDown": return (index + 1) % count;
    default: return null;
  }
}

export function ChoiceCards(props: ChoiceCardsProps) {
  const selectedIndex = props.options.findIndex(option => option.value === props.value);
  const tabIndex = selectedIndex < 0 ? 0 : selectedIndex;

  function onKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = cardKeyTarget(event.key, index, props.options.length);
    if (next === null) return;
    event.preventDefault();
    props.onChange(props.options[next].value);
    const buttons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button[role=radio]");
    buttons?.[next]?.focus();
  }

  return <div className={`ds-cards ${props.className ?? ""}`} role="radiogroup" aria-label={props.label} aria-labelledby={props["aria-labelledby"]} aria-describedby={props["aria-describedby"]}>
    {props.options.map((option, index) => <button key={option.value} type="button" className="ds-card-opt" role="radio" aria-checked={option.value === props.value} tabIndex={index === tabIndex ? 0 : -1} onKeyDown={event => onKey(event, index)} onClick={() => props.onChange(option.value)}>
      <strong className="ds-t-label">{option.label}</strong>
      <span className="ds-t-caption">{option.description}</span>
    </button>)}
  </div>;
}
