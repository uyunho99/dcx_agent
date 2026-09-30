'use client';
import { useState } from 'react';
import { Button, Card, Input, Tabs } from '@/components/ds';
import type { PrepConfig } from '@/lib/types';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import { CHANNELS, DEFAULT_BOILERPLATE, splitLines } from './prep';

export function PrepSettings({ config, disabled, onChange, replacements }: {
  config: PrepConfig; disabled: boolean; onChange: (config: PrepConfig) => void;
  replacements?: Record<string, number>;
}) {
  const [channel, setChannel] = useState<string>('naver_cafe');
  const [phrases, setPhrases] = useState<Record<string, string>>({});
  // Text remains unnormalized while editing so newlines and cursor position survive.
  const [adText, setAdText] = useState(config.adFilter.join('\n'));
  const [sourcesText, setSourcesText] = useState(config.excludeSources.join('\n'));
  return <fieldset disabled={disabled} className="min-w-0 space-y-6">
    <Card>
      <div className="ds-card-h"><div><h2 className="ds-t-card">규칙 필터</h2><p className="ds-t-caption">본문 + 댓글 기준 · 0~2단계 설정을 그대로 가져왔습니다</p></div></div>
      <label className="ds-field"><span className="ds-lab">광고어</span><textarea className="ds-inp" rows={3} value={adText} onChange={event => { setAdText(event.target.value); onChange({ ...config, adFilter: splitLines(event.target.value) }); }} /><span className="ds-hint">한 줄에 하나씩 입력하세요.</span></label>
      <label className="ds-field"><span className="ds-lab">제외 출처</span><textarea className="ds-inp" rows={2} value={sourcesText} onChange={event => { setSourcesText(event.target.value); onChange({ ...config, excludeSources: splitLines(event.target.value) }); }} /><span className="ds-hint">출처 이름을 한 줄에 하나씩 입력하세요.</span></label>
      <Input label="최소 본문" type="number" min={0} step={1} required value={Number.isNaN(config.minBodyChars) ? '' : config.minBodyChars} onChange={event => onChange({ ...config, minBodyChars: event.target.value === '' ? NaN : Number(event.target.value) })} hint="자 (스니펫 문서는 제목 5자 또는 요약 10자)" error={!Number.isInteger(config.minBodyChars) || config.minBodyChars < 0 ? '0 이상의 정수를 입력하세요.' : undefined} />
    </Card>
    <Card>
      <div className="ds-card-h"><div><h2 className="ds-t-card">채널 정형 문구</h2><p className="ds-t-caption">본문 · 댓글에서 문자열만 지웁니다. 글은 남습니다.</p></div></div>
      <Tabs label="채널" value={channel} onChange={setChannel} items={CHANNELS.map(([key, label]) => ({ value: key, label, count: config.boilerplate[key]?.length ?? 0, content: <div className="space-y-4">
        <table className="ds-tbl"><caption>치환 건수는 채널별로 집계합니다. 문구별 집계는 제공되지 않습니다.</caption><thead><tr><th scope="col">문구</th><th scope="col" style={{ width: 64 }}>출처</th><th scope="col" style={{ width: 88 }}>치환 건수</th><th scope="col" style={{ width: 68 }}>삭제</th></tr></thead><tbody>
          {(config.boilerplate[key] ?? []).map((phrase, index) => <tr key={`${phrase}:${index}`}><td>{phrase}</td><td>{DEFAULT_BOILERPLATE[key]?.includes(phrase) ? '기본' : '추가'}</td><td className="ds-dim">{replacements ? '채널별 집계' : '실행 후 집계'}</td><td><Button variant="quiet" size="sm" aria-label={`${phrase} 삭제`} onClick={() => onChange({ ...config, boilerplate: { ...config.boilerplate, [key]: config.boilerplate[key].filter((_, i) => i !== index) } })}>삭제</Button></td></tr>)}
          {!config.boilerplate[key]?.length && <tr><td colSpan={4}>등록된 정형 문구가 없습니다.</td></tr>}
        </tbody></table>
        <p className="ds-t-caption">{label} 치환 {replacements ? `${(replacements[key] ?? 0).toLocaleString('ko-KR')}건` : '실행 후 집계'}</p>
        <div className="prep-add"><Input label={`${label}에 지울 문구 추가`} placeholder="지울 문구를 붙여 넣으세요" value={phrases[key] ?? ''} onChange={event => setPhrases({ ...phrases, [key]: event.target.value })} /><Button disabled={!phrases[key]?.trim() || config.boilerplate[key]?.includes(phrases[key].trim())} onClick={() => { onChange({ ...config, boilerplate: { ...config.boilerplate, [key]: [...(config.boilerplate[key] ?? []), phrases[key].trim()] } }); setPhrases({ ...phrases, [key]: '' }); }}>추가</Button></div>
      </div> }))} />
    </Card>
    {INTERNAL_TOOLS && <Card><label className="ds-field"><span className="ds-lab">내부용 · 임베더</span><select className="ds-inp" value={config.embedder} onChange={event => onChange({ ...config, embedder: event.target.value as PrepConfig['embedder'] })}><option value="voyage">Voyage</option><option value="fake">가짜 임베더 · 오프라인 시연</option></select></label></Card>}
  </fieldset>;
}
