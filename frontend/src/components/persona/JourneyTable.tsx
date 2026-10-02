import type { InsightJourneyRow } from '../../lib/types';
import { cxCounts, formatCount } from './personaView';
export function JourneyTable({ rows }: { rows: InsightJourneyRow[] }) {
  const counts = cxCounts(rows);
  // Preserve the approved mockup's Context rows; split long journeys into two sections.
  const capacity = rows.length > 4 ? Math.ceil(rows.length / 2) : Math.max(1, rows.length);
  const groups = rows.length > 4 ? [rows.slice(0, capacity), rows.slice(capacity)] : [rows];
  return <div style={{minWidth:0, overflowWrap:'anywhere'}}>{groups.map((group, section) => <table key={section} className="ds-tbl" style={{tableLayout:'fixed',width:'100%'}}><caption>JOURNEY · {section + 1}/{groups.length}</caption><thead><tr><th scope="col" rowSpan={2}>Context</th><th scope="colgroup" colSpan={2}>AS-IS</th><th scope="colgroup" colSpan={2}>TO-BE</th></tr><tr><th scope="col">행동</th><th scope="col">느낌</th><th scope="col">제안 서비스 · ⚪ 처방</th><th scope="col">바뀐 행동</th></tr></thead><tbody>{group.map((row,index) => <tr key={`${row.context_id}-${index}`}><th scope="row">{row.context_id}</th><td>{row.action}</td><td>{row.feeling}</td><td><span aria-label="처방">⚪ 처방</span> {row.service} · {row.cx_4d}</td><td>{row.service_action}</td></tr>)}</tbody></table>)}<p className="ds-t-caption">4D-CX 분포 · {Object.entries(counts).map(([dimension,count]) => `${dimension} ${formatCount(count)}`).join(' · ')}</p></div>;
}
