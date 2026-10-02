import type { PersonaGrade } from '../../lib/types';
import { gradeLabel } from './personaView';
export function GradeMark({ grade }: { grade: PersonaGrade | null }) {
  const label = gradeLabel(grade);
  const symbol = { circle: '●', triangle: '▲', cross: '✕' };
  const color = grade === 'observed' ? '--success' : grade === 'inferred' ? '--warning' : '--danger';
  return <span className="ds-badge" style={{ color: grade ? `var(${color})` : 'var(--ink)' }}><span aria-hidden="true">{label.shape ? symbol[label.shape] : '—'}</span>{label.text}</span>;
}
