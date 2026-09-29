"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import SessionList from "@/components/SessionList";
import { SaveBar } from "@/components/SaveBar";
import { Badge, Banner, Button, Card, ChoiceChips, Input, Segmented, Skeleton } from "@/components/ds";
import { useSessionStore } from "@/stores/useSessionStore";
import { restoreSessionToStore } from "@/lib/sessionPersist";
import { createContext, getContext, patchSession, putContext, suggestCategory } from "@/lib/api/context";
import { contextLabels as labels } from "@/lib/contextLabels";
import { INTERNAL_TOOLS } from "@/lib/internalTools";
import { emptyStartForm as empty, mergeStartForm, nextStepOnStart } from "@/lib/logic/startForm";
import { isDirty } from "@/lib/logic/isDirty";
import type { ProjectContext, SessionInfo } from "@/lib/types";

const options = (group: Record<string, string>) => Object.entries(group).map(([value,label]) => ({value,label}));
const localDraft = "dcx_start_draft";
function ListInput({label, value, onChange, required}: {label: string; value: string[]; onChange: (v: string[]) => void; required?: boolean}) {
  const [text, setText] = useState("");
  const add = () => { if (text.trim()) { onChange([...value, text.trim()]); setText(""); } };
  return <div className="space-y-2"><Input label={label} required={required} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if(e.key === "Enter") {e.preventDefault(); add();} }} error={required && !value.length ? "한 줄 이상 추가하세요." : undefined} hint="한 줄씩 추가하세요." />
    <Button size="sm" onClick={add}>{label} 추가하기</Button>
    {value.map((item, i) => <div className="flex items-center justify-between gap-2" key={i}><span className="ds-t-body">{item}</span><Button size="sm" variant="quiet" onClick={() => onChange(value.filter((_, index) => index !== i))}>삭제하기</Button></div>)}
  </div>;
}
function preview(context: ProjectContext) {
  const label = (group: Record<string,string>, code: string) => group[code] || code;
  return `# 프로젝트 맥락 (참고용)\n## 0-A 프로젝트 개요\n- 제품: ${context.bk}\n- 한줄 정의: ${context.oneLiner}\n- 리서치 질문: ${context.researchQuestion.text}\n- 프로젝트 성격: ${label(labels.projectType, context.projectType.choice)} · ${context.projectType.note}\n- 분석 목적: ${label(labels.analysisGoal, context.analysisGoal.choice)} · ${context.analysisGoal.note}\n- 핵심 지표: ${context.keyMetrics.join(", ")}\n- 사내 제약: ${context.constraints.join(", ")}\n- 포지셔닝: ${label(labels.price, context.positioning.price)} · ${label(labels.market, context.positioning.market)}\n- 수집 채널: ${context.channels.map(v => label(labels.channels,v)).join(", ")}\n\n## 0-B 분석 대상 · 초기 기준선\n우선 탐색하되 범위 밖 발견도 배제하지 말 것.\n- 제품군: ${[context.productCategory.l1, context.productCategory.l2, context.productCategory.l3].filter(Boolean).join(" › ")}\n- 연령대: ${context.targetScope?.ageRanges.join(", ") || "전체"}\n- 성별: ${context.targetScope?.genders.join(", ") || "전체"}\n- 가구 형태: ${context.targetScope?.households.map(v => label(labels.households,v)).join(", ") || "전체"}\n- 생애주기: ${context.targetScope?.lifeStages.map(v => label(labels.lifeStages,v)).join(", ") || "전체"}\n- 대상 보충 설명: ${context.targetScope?.note || ""}\n- 미래 고객: ${context.futureCustomer?.choices.map(v => label(labels.futureCustomer,v)).join(", ") || ""} · ${context.futureCustomer?.note || ""}\n\n## 이미 아는 것\n${context.knownInsights.map(v => `- ${v}`).join("\n")}`;
}
export default function StartPage() {
  const router = useRouter();
  const store = useSessionStore();
  const [form, setForm] = useState<ProjectContext>(empty);
  const [saved, setSaved] = useState<ProjectContext>(empty);
  const [returned, setReturned] = useState<ProjectContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [reload, setReload] = useState(0);
  const [suggesting, setSuggesting] = useState(false);
  const [message, setMessage] = useState("");
  const [categoryError, setCategoryError] = useState("");
  const formRef = useRef<HTMLDivElement>(null);
  const operation = useRef(false);
  const createdSid = useRef<string | null>(null);
  const legacy = !!store.sid && store.sd?.schemaVersion !== 2;
  const update = <K extends keyof ProjectContext>(key: K, value: ProjectContext[K]) => setForm(current => ({...current, [key]: value}));
  useEffect(() => {
    let active = true;
    createdSid.current = store.sid;
    setLoadError(false);
    if (!store.sid) {
      let draft = mergeStartForm(null);
      try { const raw = localStorage.getItem(localDraft); if (raw) draft = mergeStartForm(JSON.parse(raw)); } catch { /* Storage is optional; use the empty form. */ }
      setForm(draft); setSaved(draft);
      setReturned(null); return;
    }
    if (legacy) return;
    setLoading(true);
    getContext(store.sid).then(data => {
      if (!active) return;
      const value = mergeStartForm(data.draft || data.projectContext);
      setForm(value); setSaved(value); setReturned(mergeStartForm(data.projectContext));
    }).catch(() => { if(active) { setLoadError(true); setMessage("입력값을 불러오지 못했습니다. 세션을 다시 여세요."); } }).finally(() => {if(active) setLoading(false);});
    return () => { active = false; };
  }, [store.sid, legacy, reload]);
  const valid = !!(form.bk.trim() && form.oneLiner.trim() && form.researchQuestion.text.trim() && form.projectType.choice && form.analysisGoal.choice && form.keyMetrics.length && form.positioning.price && form.positioning.market && form.channels.length);
  const persist = async (draft: boolean, navigate = false) => {
    if (operation.current) return;
    if (!draft && !valid) {
      const target = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
      target?.scrollIntoView({block: "center"}); target?.focus(); return;
    }
    operation.current = true; setBusy(true); setMessage("");
    const snapshot = structuredClone(form);
    try {
      let sid = store.sid || createdSid.current;
      if (draft) {
        if (sid) await patchSession(sid, {drafts: {start: snapshot}});
        else {
          try { localStorage.setItem(localDraft, JSON.stringify(snapshot)); }
          catch { setMessage("이 브라우저에 임시 저장하지 못했습니다. 입력값은 그대로 있습니다."); return; }
        }
        setSaved(snapshot); setMessage(sid ? "임시 저장했습니다." : "이 브라우저에 임시 저장했습니다. 필수값을 채운 뒤 저장하세요.");
      } else {
        const step = navigate ? nextStepOnStart(sid ? store.step : undefined) : undefined;
        if (!sid) { sid = (await createContext(snapshot)).sid; createdSid.current = sid; }
        else { await putContext(sid, snapshot); }
        await patchSession(sid, {drafts: {start: null}, ...(step ? {step} : {})});
        await restoreSessionToStore(sid, useSessionStore.getState());
        setSaved(snapshot); setReturned(mergeStartForm(useSessionStore.getState().projectContext));
        try { localStorage.removeItem(localDraft); } catch { /* A storage failure must not block a successful server save. */ }
        setMessage("저장했습니다.");
        if (navigate) router.push("/pipeline/keywords");
      }
    } catch { setMessage("저장에 실패했습니다. 입력값은 그대로 있습니다. 다시 시도하세요."); }
    finally { operation.current = false; setBusy(false); }
  };
  const open = async (sid: string, session?: SessionInfo) => {
    if (isDirty(saved, form) && !window.confirm("저장되지 않은 변경이 있습니다. 다른 세션을 여시겠습니까?")) return;
    setMessage("");
    try {
      const step = await restoreSessionToStore(sid, useSessionStore.getState());
      const early = /^(start|r[1-4]|kw-final|final|crawl)/.test(step);
      if (useSessionStore.getState().sd?.schemaVersion !== 2 && early) return;
      if (["interrupted", "paused_blocked", "blocked"].includes(session?.activity?.status || "")) { router.push("/pipeline/crawling"); return; }
      const route = step.startsWith("r") || (step === "final" || step === "kw-final") ? "keywords" : step.startsWith("crawl") ? "crawling" : step.startsWith("preprocess") ? "preprocess" : step.startsWith("label") ? "labeling" : step.startsWith("train") ? "training" : step.startsWith("cluster") ? "clustering" : /^(persona|embed|done)/.test(step) ? "personas" : "start";
      router.push(`/pipeline/${route}`);
    } catch { setMessage("세션을 불러오지 못했습니다. 다시 여세요."); }
  };
  const suggest = async () => {
    setSuggesting(true); setCategoryError("");
    try {
      const category = await suggestCategory(form.bk, form.oneLiner); update("productCategory", category);
      const missing = !category.l1 ? "l1" : !category.l2 ? "l2" : !category.l3 ? "l3" : null;
      if (missing) setTimeout(() => document.getElementById(`category-${missing}`)?.focus(), 0);
    } catch { setCategoryError("제품군을 제안하지 못했습니다. 직접 입력하세요."); }
    finally { setSuggesting(false); }
  };
  const single = (key: "projectType" | "analysisGoal", title: string) => <div className="space-y-2" role="group" aria-labelledby={`${key}-heading`} aria-describedby={!form[key].choice ? `${key}-error` : undefined} tabIndex={-1} aria-invalid={!form[key].choice || undefined}>
    <h3 id={`${key}-heading`} className="ds-t-label">{title} *</h3><ChoiceChips label={title} options={options(labels[key])} value={form[key].choice} onChange={choice => update(key, {...form[key], choice})} />
    {!form[key].choice && <p id={`${key}-error`} className="ds-err">하나를 선택하세요.</p>}<Input label={`${title} 보충 설명`} value={form[key].note} onChange={e => update(key, {...form[key], note: e.target.value})} />
  </div>;
  const target = form.targetScope || empty.targetScope!;
  return <div className="space-y-6">
    <SessionList onSelect={open} />
    {message && <Banner tone={message.includes("못") || message.includes("실패") ? "danger" : "info"}>{message}</Banner>}
    {store.persistError && <Banner tone="danger">{store.persistError}</Banner>}
    {legacy ? <Banner tone="warning" actions={<><Button onClick={() => router.push("/pipeline/preprocess")}>전처리 화면으로</Button><Button onClick={() => store.reset()}>새 프로젝트 만들기</Button></>}>구버전 세션은 0~2단계를 편집할 수 없습니다. 3단계 이후 화면에서 결과를 확인하세요.</Banner> : <>
      <header><p className="ds-t-eyebrow">0단계 · 입력</p><h1 className="ds-t-screen">새 프로젝트를 설정합니다</h1><p className="ds-t-body">0-A는 이후 모든 단계가 참고하는 프로젝트 개요입니다. 0-B는 분석 결과와 대조할 초기 기준선이며 전부 선택 입력입니다.</p></header>
      {store.sid && <Button onClick={() => { if (!isDirty(saved, form) || window.confirm("저장되지 않은 변경이 있습니다. 새 프로젝트를 만드시겠습니까?")) store.reset(); }}>새 프로젝트 만들기</Button>}
      {loadError ? <Button onClick={() => setReload(value => value + 1)}>입력값 다시 불러오기</Button> : loading ? <div role="status">처리 중…<Skeleton /><Skeleton /><Skeleton /></div> : <div className={INTERNAL_TOOLS ? "grid gap-6 lg:grid-cols-3" : "grid gap-6"}>
        <div className={INTERNAL_TOOLS ? "lg:col-span-2 space-y-6" : "space-y-6"} ref={formRef}>
          <fieldset disabled={busy} className="space-y-6">
          <Card className="space-y-6"><div className="flex justify-between gap-3"><div><h2 className="ds-t-card">0-A 프로젝트 개요</h2><p className="ds-t-caption">필수 · 지켜지는 값. 어긋나는 결과는 막지 않고 방향성과 맞지 않을 수 있음으로 표시합니다.</p></div><Badge>가드레일</Badge></div>
            <div className="grid gap-6 md:grid-cols-2"><Input label="제품명" required value={form.bk} onChange={e => update("bk",e.target.value)} error={!form.bk.trim() ? "제품명을 입력하세요." : undefined} hint="크롤링 검색어에는 붙지 않습니다." /><Input label="한줄 정의" required value={form.oneLiner} onChange={e => update("oneLiner",e.target.value)} error={!form.oneLiner.trim() ? "한줄 정의를 입력하세요." : undefined} /></div>
            <div className="space-y-2"><div className="flex flex-wrap gap-2">{["사용 중 불편 탐색하기", "비사용자의 망설임 탐색하기", "대체 방법과 이유 탐색하기"].map((title,i) => <Button key={title} size="sm" onClick={() => update("researchQuestion", {template: String(i+1), text: [`${form.bk || "제품"}을 쓰는 사람들은 언제·어디서·무엇을 하다가 어떤 불편을 겪는가?`, `${form.bk || "제품"}을 아직 안 쓰는 사람들은 무엇 때문에 망설이는가?`, `${form.bk || "제품"}을 대신해 사람들이 쓰는 방법은 무엇이고, 왜 그 방법을 택하는가?`][i]})}>{title}</Button>)}</div><Input label="리서치 질문" required value={form.researchQuestion.text} onChange={e => update("researchQuestion", {...form.researchQuestion, text:e.target.value})} error={!form.researchQuestion.text.trim() ? "리서치 질문을 입력하세요." : undefined} hint="템플릿을 고르면 채워지고, 자유롭게 고칠 수 있습니다." /></div>
            <div className="grid gap-6 md:grid-cols-2">{single("projectType","프로젝트 성격")}{single("analysisGoal","분석 목적")}</div>
            <div className="grid gap-6 md:grid-cols-2"><ListInput label="핵심 지표" required value={form.keyMetrics} onChange={v => update("keyMetrics",v)} /><ListInput label="사내 제약" value={form.constraints} onChange={v => update("constraints",v)} /></div>
            <div className="grid gap-6 md:grid-cols-2"><div className="space-y-2" role="group" aria-labelledby="positioning-heading" aria-describedby={!form.positioning.price || !form.positioning.market ? "positioning-error" : undefined} tabIndex={-1} aria-invalid={!form.positioning.price || !form.positioning.market || undefined}><h3 id="positioning-heading" className="ds-t-label">브랜드 포지셔닝 *</h3>{(["price", "market"] as const).map(key => <Segmented key={key} label={key === "price" ? "가격대" : "시장 위치"} options={options(labels[key])} value={form.positioning[key]} onChange={v => update("positioning", {...form.positioning, [key]:v})} />)}{(!form.positioning.price || !form.positioning.market) && <p id="positioning-error" className="ds-err">가격대와 시장 위치를 선택하세요.</p>}</div>
            <div role="group" aria-labelledby="channels-heading" aria-describedby={!form.channels.length ? "channels-error" : undefined} tabIndex={-1} aria-invalid={!form.channels.length || undefined}><h3 id="channels-heading" className="ds-t-label">수집 채널 *</h3><ChoiceChips multiple label="수집 채널" options={options(labels.channels).filter(o => INTERNAL_TOOLS || o.value !== "fixture")} value={form.channels} onChange={v => update("channels",v)} />{!form.channels.length && <p id="channels-error" className="ds-err">채널을 하나 이상 선택하세요.</p>}</div></div>
            <ListInput label="이미 아는 것" value={form.knownInsights} onChange={v => update("knownInsights",v)} />
          </Card>
          <Card className="space-y-6"><div className="flex justify-between gap-3"><div><h2 className="ds-t-card">0-B 분석 대상 · 초기 기준선</h2><p className="ds-t-caption">선택 · 대조되는 값. 우선 탐색하되 범위 밖 발견도 배제하지 않습니다.</p></div><Badge>기준선</Badge></div>
            <div className="flex items-center gap-3"><h3 className="ds-t-label">제품군 대 › 중 › 소</h3>{form.productCategory.source !== "user" && <Badge>{form.productCategory.source === "shopping" ? "쇼핑" : "추정"}</Badge>}<Button loading={suggesting} disabled={!form.bk.trim()} onClick={suggest}>자동 제안하기</Button></div>
            {categoryError && <Banner tone="warning">{categoryError}</Banner>}{suggesting && <Skeleton />}
            <div className="grid gap-3 md:grid-cols-3">{(["l1", "l2", "l3"] as const).map((key,i) => <Input key={key} id={`category-${key}`} label={["대분류","중분류","소분류"][i]} disabled={suggesting} value={form.productCategory[key] || ""} onChange={e => update("productCategory", {...form.productCategory, [key]:e.target.value, source:"user"})} />)}</div>
            <div className="grid gap-6 md:grid-cols-2">{(["ageRanges", "genders", "households", "lifeStages"] as const).map((key,i) => <div key={key}><h3 className="ds-t-label">{["연령대", "성별", "가구 형태", "생애주기"][i]}</h3><ChoiceChips multiple label={["연령대", "성별", "가구 형태", "생애주기"][i]} options={key === "ageRanges" ? options({"20대":"20대", "30대":"30대", "40대":"40대", "50대+":"50대+"}) : key === "genders" ? options({"남성":"남성", "여성":"여성"}) : options(labels[key])} value={target[key]} onChange={v => update("targetScope", {...target,[key]:v})} /><p className="ds-t-caption">미선택은 전체입니다.</p></div>)}</div>
            <Input label="분석 대상 보충 설명" value={target.note} onChange={e => update("targetScope", {...target,note:e.target.value})} />
            <div className="space-y-2"><h3 className="ds-t-label">미래 고객 정의</h3><ChoiceChips multiple label="미래 고객 정의" options={options(labels.futureCustomer)} value={form.futureCustomer?.choices || []} onChange={choices => update("futureCustomer", {choices,note:form.futureCustomer?.note || ""})} /><Input label="미래 고객 보충 설명" value={form.futureCustomer?.note || ""} onChange={e => update("futureCustomer", {choices:form.futureCustomer?.choices || [],note:e.target.value})} /></div>
          </Card>
          </fieldset>
          <SaveBar dirty={isDirty(saved,form)} valid={valid} saving={busy} onDraft={() => void persist(true)} onSave={() => void persist(false)} primary={<Button variant="primary" loading={busy} onClick={() => void persist(false,true)}>키워드 생성 시작하기</Button>} />
        </div>
        {INTERNAL_TOOLS && <aside><Card className="lg:sticky lg:top-6"><details open><summary className="ds-t-label">project_context.md 미리보기</summary><p className="ds-t-caption">서버 저장 맥락을 바탕으로 만든 미리보기입니다.</p><pre className="ds-t-caption whitespace-pre-wrap break-words">{preview(returned || form)}</pre></details></Card></aside>}
      </div>}
    </>}
  </div>;
}
