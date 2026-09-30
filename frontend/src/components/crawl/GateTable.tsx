'use client';
import { Fragment, useLayoutEffect, useRef, useState } from 'react';
import { Badge, Button, Table } from '@/components/ds';
import type { GateRow } from '@/lib/api/crawl';
import { channelBars } from '@/lib/logic/channelBars';
import { crawlWindow } from '@/lib/logic/crawlWindow';
import { channelNames } from './Settings';
const badgeNames:Record<string,string>={zero:'0건',low:'저수율',low_unique:'고유 기여 낮음'};
export function GateTable({rows,excluded,onChange,disabled}:{rows:GateRow[];excluded:string[];onChange:(v:string[])=>void;disabled:boolean}) {
  const [expanded,setExpanded]=useState<Set<string>>(new Set()); const [filter,setFilter]=useState('');
  const [scroll,setScroll]=useState(0); const [viewport,setViewport]=useState(600); const [measured,setMeasured]=useState<Record<string,number>>({});
  const box=useRef<HTMLDivElement>(null);
  const sorted=rows.filter(r=>!filter || r.badges.includes(filter)).sort((a,b)=>Number(b.badges.length>0)-Number(a.badges.length>0));
  const heights=sorted.map(r=>measured[`${r.kw}:${expanded.has(r.kw)}`]??(expanded.has(r.kw)?240:64));
  const windowed=crawlWindow(heights,scroll,viewport);
  useLayoutEffect(()=>{
    const node=box.current; if(!node) return;
    const observer=new ResizeObserver(()=>{
      setViewport(node.clientHeight);
      const sizes:Record<string,number>={};
      node.querySelectorAll<HTMLTableRowElement>('tr[data-measure]').forEach(row=>{const key=row.dataset.measure!;sizes[key]=(sizes[key]??0)+row.getBoundingClientRect().height;});
      setMeasured(old=>Object.entries(sizes).some(([k,v])=>old[k]!==v)?{...old,...sizes}:old);
    });
    observer.observe(node); node.querySelectorAll('tr[data-measure]').forEach(row=>observer.observe(row));
    return ()=>observer.disconnect();
  },[expanded,filter,windowed.start,windowed.end,rows]);
  const toggle=(kw:string)=>setExpanded(old=>{const next=new Set(old);if(next.has(kw))next.delete(kw);else next.add(kw);return next;});
  return <><div className="crawl-actions">{['',...Object.keys(badgeNames)].map(key=><Button key={key} aria-pressed={filter===key} onClick={()=>{setFilter(key);setScroll(0);if(box.current)box.current.scrollTop=0;}}>{key?`${badgeNames[key]} 보기`:'배지 있는 행 먼저 보기'}</Button>)}<Button disabled={disabled} onClick={()=>onChange([...new Set([...excluded,...rows.filter(r=>r.badges.length).map(r=>r.kw)])])}>배지 행 모두 제외</Button><span>{excluded.length}개 제외 선택</span></div><div className="crawl-table-scroll" ref={box} onScroll={e=>setScroll(e.currentTarget.scrollTop)}><Table aria-label="키워드별 목록 검토" aria-rowcount={sorted.length+1}><thead><tr>{['제외','키워드','축 · 하위','목록 → 필터 후','고유 기여','채널','상태'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{windowed.before>0&&<tr aria-hidden="true"><td colSpan={7} style={{height:windowed.before,padding:0}}/></tr>}{sorted.slice(windowed.start,windowed.end).map((r,index)=>{
    const open=expanded.has(r.kw), measure=`${r.kw}:${open}`;
    return <Fragment key={r.kw}><tr data-measure={measure} aria-rowindex={windowed.start+index+2} onClick={()=>toggle(r.kw)}><td><input type="checkbox" aria-label={`${r.kw} 제외`} disabled={disabled} checked={excluded.includes(r.kw)} onClick={e=>e.stopPropagation()} onChange={e=>onChange(e.target.checked?[...excluded,r.kw]:excluded.filter(k=>k!==r.kw))}/></td><th scope="row"><button className="crawl-row-button" aria-expanded={open} onClick={e=>{e.stopPropagation();toggle(r.kw);}}>{r.kw} · {open?'접기':'펼치기'}</button></th><td>{r.axis} · {r.sub}</td><td>{r.listed.toLocaleString()} → {r.after_filter.toLocaleString()}</td><td>{r.listed?`${Math.round(r.unique_ratio*100)}%`:'—'}</td><td><div className="crawl-mini">{channelBars(r.per_source).map(b=><div key={b.source} title={`${channelNames[b.source]??b.source} ${b.count.toLocaleString()}`}><span className="sr-only">{channelNames[b.source]??b.source} {b.count.toLocaleString()}, {Math.round(b.ratio*100)}%</span><span className={b.dashed?'crawl-dashed':'crawl-track'} aria-hidden="true"><span style={{width:`${b.ratio*100}%`}}/></span></div>)}</div></td><td>{r.badges.length?r.badges.map(b=><Badge key={b} tone={b==='zero'?'danger':'warning'}>{badgeNames[b]??b}</Badge>):<Badge>정상</Badge>}</td></tr>{open&&<tr data-measure={measure}><td colSpan={7}><div className="crawl-detail">{Object.entries(r.per_source).map(([source,c])=><div key={source}><b>{channelNames[source]??source}</b><p>목록 {c.listed} · 필터 후 {Math.max(0,c.listed-c.filtered)} · 고유 기여 {c.listed?`${Math.round(c.unique/c.listed*100)}%`:'—'}</p>{c.titles?.slice(0,3).map((title,i)=><p key={i}>{title}</p>)}</div>)}</div></td></tr>}</Fragment>;
  })}{windowed.after>0&&<tr aria-hidden="true"><td colSpan={7} style={{height:windowed.after,padding:0}}/></tr>}</tbody></Table></div><p className="ds-t-caption">다른 키워드도 찾은 URL은 유지됩니다. 제외한 키워드는 다음 세션의 과거 0건 키워드 근거로 남습니다.</p></>;
}
