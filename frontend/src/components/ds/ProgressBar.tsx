export type ProgressBarProps = { label: string; value?: number; max?: number };
export function ProgressBar({ label, value, max = 100 }: ProgressBarProps) {
  const limit = Number.isFinite(max) && max > 0 ? max : 100;
  const current = value === undefined || !Number.isFinite(value) ? undefined : Math.max(0, Math.min(limit, value));
  return <div aria-live="polite"><div className="ds-progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={current} aria-valuetext={current === undefined ? "처리 중…" : undefined}><div style={{ width: `${current === undefined ? 100 : current / limit * 100}%` }} /></div>{current === undefined && <span className="ds-t-caption">처리 중…</span>}</div>;
}
