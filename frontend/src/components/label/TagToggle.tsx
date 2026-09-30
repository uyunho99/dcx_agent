'use client';
export type TagToggleProps = { label: string; pressed: boolean; onChange: (pressed: boolean) => void; shortcut?: string; disabled?: boolean };
export function TagToggle({label, pressed, onChange, shortcut, disabled}: TagToggleProps) {
 return <button type="button" className="ds-chip" aria-pressed={pressed} disabled={disabled} onClick={() => onChange(!pressed)}>{shortcut && <kbd>{shortcut} </kbd>}{label}</button>;
}
