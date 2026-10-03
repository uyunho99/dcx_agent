import { useId, type TextareaHTMLAttributes } from "react";
type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; minRows?: number; charsPerRow?: number };
/** Multi-line field whose height follows its text so long drafts stay readable. */
export function textRows(value: unknown, minRows = 2, charsPerRow = 40) {
  const text = typeof value === "string" ? value : "";
  return Math.max(minRows, text.split("\n").reduce((rows, line) => rows + Math.max(1, Math.ceil(line.length / charsPerRow)), 0));
}
export function TextArea({ label, id, className = "", minRows = 2, charsPerRow = 40, ...props }: TextAreaProps) {
  const generated = useId(); const fieldId = id ?? generated;
  return <div className="ds-field"><label htmlFor={fieldId}>{label}</label><textarea {...props} id={fieldId} rows={textRows(props.value, minRows, charsPerRow)} className={`ds-inp ${className}`}/></div>;
}
