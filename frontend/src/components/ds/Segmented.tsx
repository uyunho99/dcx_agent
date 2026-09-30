"use client";
import { ChoiceChips, type ChoiceChipsProps } from "./ChoiceChips";
export type SegmentedProps = Extract<ChoiceChipsProps, { multiple?: false }>;
export function Segmented(props: SegmentedProps) { return <ChoiceChips {...props} className={`ds-seg ${props.className ?? ""}`} />; }
