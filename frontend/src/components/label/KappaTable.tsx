import { Table } from '../ds/Table';
import type { KappaSummary } from '@/lib/types';
const names: Record<string,string> = {anchor:'대상 경험',sense:'감각',feel:'감정',think:'판단',act:'행동',relate:'관계',outcome:'결과',situation:'상황',grade:'등급'};
const metric = (value: number | null | undefined) => value == null ? '표본 부족' : value.toFixed(2);
export function KappaTable({audit, jev, gpt}: {audit?: KappaSummary; jev?: KappaSummary; gpt?: KappaSummary}) {
 return <Table><caption>라벨러 성능 · 감사 기준</caption><thead><tr><th scope="col">칸</th><th scope="col">표본</th><th scope="col">감사 κ</th><th scope="col">Jev 정확도</th><th scope="col">GPT 정확도</th><th scope="col">비고</th></tr></thead><tbody>{Object.entries(names).map(([key,name]) => {
 const a = key === 'grade' ? audit?.grade : audit?.fields[key]; const j = key === 'grade' ? jev?.grade : jev?.fields[key]; const g = key === 'grade' ? gpt?.grade : gpt?.fields[key];
 return <tr key={key}><th scope="row">{name}</th><td>{a?.n ?? 0}</td><td>{metric(a?.kappa)}</td><td>{metric(j?.accuracy)}</td><td>{metric(g?.accuracy)}</td><td>{!a || a.n < 30 ? '표본 30건부터 확인하세요' : a.kappa != null && a.kappa < .75 ? '태그 정의를 확인하세요' : '—'}</td></tr>;
 })}</tbody></Table>;
}
