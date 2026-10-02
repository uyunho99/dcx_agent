"use client";
import { displayError } from "@/lib/api/errors";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import SessionList from "@/components/SessionList";
import { SaveBar } from "@/components/SaveBar";
import { Badge, Banner, Button, Card, Checkbox, ChoiceCards, ChoiceChips, Input, Skeleton } from "@/components/ds";
import { VersionStage, StageVersionAction } from "@/components/versions/StageVersion";
import { useVersion } from "@/components/versions/VersionProvider";
import { getVersionContext } from "@/lib/api/versions";
import { useSessionStore } from "@/stores/useSessionStore";
import { restoreSessionToStore } from "@/lib/sessionPersist";
import { createContext, patchSession, putContext, suggestCategory } from "@/lib/api/context";
import { contextLabels as labels } from "@/lib/contextLabels";
import { INTERNAL_TOOLS } from "@/lib/internalTools";
import { emptyStartForm as empty, mergeStartForm, nextStepOnStart, isPreTaskModeContext, validateStartForm, researchTemplates, choosePositionPreset, setPositionText, positioningOpen, addPersonaSeed, missingDimensions, toggleChoice } from "@/lib/logic/startForm";
import { isDirty } from "@/lib/logic/isDirty";
import type { ProjectContext, SessionInfo } from "@/lib/types";

import { popoverKeyAction } from "@/lib/logic/keywordKeys";
const options = (group: Record<string, string>) => Object.entries(group).map(([value,label]) => ({value,label}));
const localDraft = "dcx_start_draft";
function ListInput({label, value, onChange, required}: {label: string; value: string[]; onChange: (v: string[]) => void; required?: boolean}) {
  const [text, setText] = useState("");
  const add = () => { if (text.trim()) { onChange([...value, text.trim()]); setText(""); } };
  return <div className="space-y-2"><Input label={label} required={required} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if(popoverKeyAction("input", e.key, e.nativeEvent.isComposing, e.nativeEvent.keyCode) === "submit") {e.preventDefault(); add();} }} error={required && !value.length ? "한 줄 이상 추가하세요." : undefined} hint="한 줄씩 추가하세요." />
    <Button size="sm" onClick={add}>{label} 추가하기</Button>
    {value.map((item, i) => <div className="flex items-center justify-between gap-2" key={i}><span className="ds-t-body">{item}</span><Button size="sm" variant="quiet" onClick={() => onChange(value.filter((_, index) => index !== i))}>삭제하기</Button></div>)}
  </div>;
}
const dimensionOptions = options({social: "사회적 외부", taste: "취향·활동", movement: "동선", bio: "바이오"});
function submitOnEnter(event: KeyboardEvent<HTMLInputElement>, submit: () => void) {
  if (popoverKeyAction("input", event.key, event.nativeEvent.isComposing, event.nativeEvent.keyCode) === "submit") {
    event.preventDefault(); submit();
  }
}
function preview(context: ProjectContext) {
  const label = (group: Record<string, string>, code: string) => group[code] || code;
  const items = (values: string[], fallback = "없음") => values.join(", ") || fallback;
  const note = (value: string, extra?: string) => extra ? `${value} (${extra})` : value;
  // Normalize old string metrics without adding task/persona defaults to the saved preview.
  const metrics = mergeStartForm(context).keyMetrics;
  const lines = ["## 0-A 프로젝트 개요", "", `- 제품명: ${context.bk}`];
  if (context.taskMode) lines.push(`- 과제 유형: ${labels.taskMode[context.taskMode]} — ${context.taskMode === "metric" ? "외부·사내 평가 지표를 올리는 과제. 지표가 떨어지는 순간을 우선 탐색" : "아직 드러나지 않은 맥락과 기회를 찾는 과제. 넓게 탐색"}`);
  lines.push(`- 한줄 정의: ${context.oneLiner}`, `- 리서치 질문: ${context.researchQuestion.text}`);
  if (context.researchQuestion.template) lines.push(`- 질문 템플릿: ${context.researchQuestion.template}`);
  lines.push(`- 프로젝트 유형: ${note(label(labels.projectType, context.projectType.choice), context.projectType.note)}`);
  if (context.analysisGoal) lines.push(`- 분석 목표: ${note(label(labels.analysisGoal, context.analysisGoal.choice), context.analysisGoal.note)}`);
  lines.push(`- 핵심 지표 (방향 지시자, 측정값 아님): ${items(metrics.map(metric => note(metric.name, [metric.source && `출처: ${metric.source}`, metric.item && `문항: ${metric.item}`].filter(Boolean).join(" · "))))}`, `- 사내 제약: ${items(context.constraints)}`);
  for (const axis of ["price", "market"] as const) {
    const value = context.positioning[axis] ? label(labels[axis], context.positioning[axis]) : context.positioning[`${axis}Text`];
    if (value) lines.push(`- ${axis === "price" ? "가격" : "시장"} 포지셔닝: ${value}`);
  }
  lines.push(`- 수집 채널: ${items(context.channels.map(code => label(labels.channels, code)))}`, `- 제품 분류: ${[context.productCategory.l1, context.productCategory.l2, context.productCategory.l3].filter(Boolean).join(" > ")}`, `- 제품 분류 출처: ${labels.source[context.productCategory.source]}`, "");
  if (context.personaSeeds) {
    const seeds = context.personaSeeds;
    lines.push("## 생각하는 페르소나 · 디멘션", "", ...seeds.items.map(seed => `- ${note(seed.text, seed.dimension ? labels.personaDimensions[seed.dimension] : "")}`));
    if (!seeds.items.length) lines.push("- 없음");
    else {
      const missing = missingDimensions(seeds.items);
      if (missing.length) lines.push(`- 아직 적지 않은 디멘션: ${missing.map(code => labels.personaDimensions[code]).join(", ")}`);
    }
    lines.push("", `디멘션: ${Object.values(labels.personaDimensions).join(" · ")}`, seeds.exploreBeyond ? "예시는 출발점일 뿐이다. 네 디멘션 각각에서 예시와 비슷한 페르소나에 머물지 말고, 예시와 다른 페르소나와 맥락을 우선 발굴할 것" : "예시는 참고 시드이며 제약이 아니다. 범위 밖 발견도 배제하지 말 것", "");
  }
  const target = context.targetScope || empty.targetScope!;
  lines.push("## 0-B 분석 대상 · 초기 기준선", "", "분석 대상 초기 기준선 — 우선 탐색하되 범위 밖 발견도 배제하지 말 것, 해석을 조정하지 말 것", "",
    `- 연령대: ${items(target.ageRanges, "전체")}`, `- 성별: ${items(target.genders, "전체")}`,
    `- 가구 유형: ${items(target.households.map(code => label(labels.households, code)), "전체")}`,
    `- 생애 단계: ${items(target.lifeStages.map(code => label(labels.lifeStages, code)), "전체")}`,
    `- 분석 대상 메모: ${target.note || "없음"}`, `- 미래 고객: ${note(items((context.futureCustomer?.choices || []).map(code => label(labels.futureCustomer, code)), "전체"), context.futureCustomer?.note)}`,
    "", "## 이미 아는 것", "", ...(context.knownInsights.length ? context.knownInsights.map(value => `- ${value}`) : ["- 없음"]));
  return lines.join("\n") + "\n";
}
function PositionAxisInput({axis, position, onChange}: {axis: "price" | "market"; position: ProjectContext["positioning"]; onChange: (value: ProjectContext["positioning"]) => void}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const title = axis === "price" ? "가격대" : "시장 위치";
  const custom = position[`${axis}Text`];
  const add = () => {
    if (!text.trim()) return;
    onChange(setPositionText(position, axis, text)); setText(""); setEditing(false);
  };
  return <div className="space-y-2">
    <h4 className="ds-t-label">{title}</h4>
    <div className="flex flex-wrap items-center gap-2">
      <ChoiceChips label={title} options={options(labels[axis])} value={position[axis] || ""} onChange={value => onChange(choosePositionPreset(position, axis, value))} />
      {custom && <span className="ds-chip" style={{borderColor: "var(--action)", background: "var(--action-soft)"}}>{custom}<Button size="sm" variant="quiet" aria-label={`${title} 직접 입력 지우기`} onClick={() => onChange(setPositionText(position, axis, ""))}>✕</Button></span>}
      {!editing && <Button size="sm" variant="quiet" onClick={() => setEditing(true)}>+ 직접 입력</Button>}
    </div>
    {editing && <div className="flex flex-wrap items-end gap-2"><Input autoFocus label={`${title} 직접 입력`} placeholder={axis === "price" ? "예: 중상가 · 구독형" : "예: 틈새 전문 브랜드"} maxLength={40} value={text} onChange={event => setText(event.target.value)} onKeyDown={event => submitOnEnter(event, add)} /><Button size="sm" disabled={!text.trim()} onClick={add}>추가하기</Button></div>}
  </div>;
}
export default function StartPage() { return <StartScreen />; }
function StartScreen() {
  const { version } = useVersion();
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
  const [saveWarnings, setSaveWarnings] = useState<string[]>([]);
  const [metric, setMetric] = useState({name: "", source: "", item: ""});
  const [personaText, setPersonaText] = useState("");
  const [personaNotice, setPersonaNotice] = useState("");
  const formRef = useRef<HTMLDivElement>(null);
  const operation = useRef(false);
  const createdSid = useRef<string | null>(null);
  const legacy = !!store.sid && store.sd?.schemaVersion !== 2;
  const update = <K extends keyof ProjectContext>(key: K, value: ProjectContext[K]) => setForm(current => ({...current, [key]: value}));
  useEffect(() => {
    let active = true;
    createdSid.current = store.sid;
    setLoadError(false); setReturned(null); setSaveWarnings([]);
    setMetric({name: "", source: "", item: ""}); setPersonaText(""); setPersonaNotice("");
    if (!store.sid) {
      let draft = mergeStartForm(null);
      try { const raw = localStorage.getItem(localDraft); if (raw) draft = mergeStartForm(JSON.parse(raw)); } catch { /* Storage is optional; use the empty form. */ }
      setForm(draft); setSaved(draft);
      setReturned(null); return;
    }
    if (legacy) return;
    setLoading(true);
    getVersionContext(store.sid, version).then(data => {
      if (!active) return;
      const value = mergeStartForm(data.draft || data.projectContext);
      setForm(value); setSaved(value); setReturned(data.projectContext);
    }).catch((e) => { if(active) { setLoadError(true); setMessage(displayError(e, "입력값을 불러오지 못했습니다. 세션을 다시 여세요.")); } }).finally(() => {if(active) setLoading(false);});
    return () => { active = false; };
  }, [store.sid, legacy, reload, version]);
  const {valid, errors} = validateStartForm(form);
  const seeds = form.personaSeeds || empty.personaSeeds!;
  const missing = missingDimensions(seeds.items);
  const addMetric = () => {
    if (!metric.name.trim()) return;
    update("keyMetrics", [...form.keyMetrics, {name: metric.name.trim(), source: metric.source.trim(), item: metric.item.trim()}]);
    setMetric({name: "", source: "", item: ""});
  };
  const addPersona = () => {
    const result = addPersonaSeed(seeds.items, personaText);
    setPersonaNotice(result.reason === "limit" ? "20개까지 적을 수 있습니다." : "");
    if (result.reason) return;
    update("personaSeeds", {...seeds, items: result.items}); setPersonaText("");
  };
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
        if (sid) await patchSession(sid, {drafts: {start: snapshot}}, version);
        else {
          try { localStorage.setItem(localDraft, JSON.stringify(snapshot)); }
          catch { setMessage("이 브라우저에 임시 저장하지 못했습니다. 입력값은 그대로 있습니다."); return; }
        }
        setSaved(snapshot); setMessage(sid ? "임시 저장했습니다." : "이 브라우저에 임시 저장했습니다. 필수값을 채운 뒤 저장하세요.");
      } else {
        const step = navigate ? nextStepOnStart(sid ? store.step : undefined) : undefined;
        if (!sid) { sid = (await createContext(snapshot)).sid; createdSid.current = sid; setReturned(snapshot); setSaveWarnings([]); }
        else {
          const response = await putContext(sid, snapshot, version);
          setReturned(response.projectContext); setSaveWarnings(response.warnings || []);
        }
        await patchSession(sid, {drafts: {start: null}, ...(step ? {step} : {})}, version);
        await restoreSessionToStore(sid, useSessionStore.getState());
        setSaved(snapshot);
        try { localStorage.removeItem(localDraft); } catch { /* A storage failure must not block a successful server save. */ }
        setMessage("저장했습니다.");
        if (navigate) router.push("/pipeline/keywords");
      }
    } catch (e) { setMessage(displayError(e, "저장에 실패했습니다. 입력값은 그대로 있습니다. 다시 시도하세요.")); }
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
    } catch (e) { setMessage(displayError(e, "세션을 불러오지 못했습니다. 다시 여세요.")); }
  };
  const suggest = async () => {
    setSuggesting(true); setCategoryError("");
    try {
      const category = await suggestCategory(form.bk, form.oneLiner); update("productCategory", category);
      const missing = !category.l1 ? "l1" : !category.l2 ? "l2" : !category.l3 ? "l3" : null;
      if (missing) setTimeout(() => document.getElementById(`category-${missing}`)?.focus(), 0);
    } catch (e) { setCategoryError(displayError(e, "제품군을 제안하지 못했습니다. 직접 입력하세요.")); }
    finally { setSuggesting(false); }
  };
  const single = (key: "projectType", title: string) => <fieldset className="min-w-0 space-y-2" aria-labelledby={`${key}-heading`} aria-describedby={errors[key] ? `${key}-error` : undefined} tabIndex={-1} aria-invalid={!!errors[key] || undefined}>
    <h3 id={`${key}-heading`} className="ds-t-label">{title} *</h3><ChoiceChips label={title} options={options(labels[key])} value={form[key].choice} onChange={choice => update(key, {...form[key], choice})} />
    {errors[key] && <p id={`${key}-error`} className="ds-err">{errors[key]}</p>}<Input label={`${title} 보충 설명`} value={form[key].note} onChange={event => update(key, {...form[key], note: event.target.value})} />
  </fieldset>;
  const positioning = <div className="space-y-3">
    {(["price", "market"] as const).map(axis => <PositionAxisInput key={`${store.sid || "new"}-${version}-${reload}-${axis}`} axis={axis} position={form.positioning} onChange={value => update("positioning", value)} />)}
    <p className="ds-t-caption">고른 칩을 다시 누르면 해제됩니다.</p>
  </div>;
  const target = form.targetScope || empty.targetScope!;
  return <div className="space-y-6">
    <SessionList onSelect={open} />
    {store.sid && !legacy && <Button onClick={() => { if (!isDirty(saved, form) || window.confirm("저장되지 않은 변경이 있습니다. 새 프로젝트를 만드시겠습니까?")) store.reset(); }}>새 프로젝트 만들기</Button>}
    {message && <Banner tone={message.includes("못") || message.includes("실패") ? "danger" : "info"}>{message}</Banner>}
    {store.persistError && <Banner tone="danger">{store.persistError}</Banner>}
    {legacy ? <Banner tone="warning" actions={<><Button onClick={() => router.push("/pipeline/preprocess")}>전처리 화면으로</Button><Button onClick={() => store.reset()}>새 프로젝트 만들기</Button></>}>구버전 세션은 0~2단계를 편집할 수 없습니다. 3단계 이후 화면에서 결과를 확인하세요.</Banner> : <VersionStage stage="stage0">
      <header><StageVersionAction stage="stage0" /><p className="ds-eyebrow">0단계 · 입력</p><h1 className="ds-t-screen">새 프로젝트를 설정합니다</h1><p className="ds-t-body">0-A는 이후 모든 단계가 참고하는 프로젝트 개요입니다. 0-B는 분석 결과와 대조할 초기 기준선이며 전부 선택 입력입니다.</p></header>
      {!loading && isPreTaskModeContext(returned) && <Banner tone="info">이 세션은 과제 유형이 생기기 전에 저장되었습니다. 지금은 탐색·기획형으로 표시됩니다. 저장하면 이 유형으로 저장되고, project_context.md에 과제 유형과 생각하는 페르소나 섹션이 추가됩니다.</Banner>}
      {saveWarnings.length > 0 && <Banner tone="info">R1 키워드는 바뀌기 전 입력으로 만들었습니다. 새 입력을 반영하려면 새 버전을 만들어 0단계부터 다시 시작하세요.</Banner>}
      {loadError ? <Button onClick={() => setReload(value => value + 1)}>입력값 다시 불러오기</Button> : loading ? <div role="status">처리 중…<Skeleton /><Skeleton /><Skeleton /></div> : <div className={INTERNAL_TOOLS ? "grid gap-6 lg:grid-cols-3" : "grid gap-6"}>
        <div className={INTERNAL_TOOLS ? "lg:col-span-2 space-y-6" : "space-y-6"} ref={formRef}>
          <fieldset disabled={busy} className="space-y-6">
          <Card className="space-y-3">
            <h2 id="task-mode-heading" className="ds-t-card">과제 유형 *</h2>
            <p className="ds-t-caption">프로젝트 성격(브랜딩 · 리뉴얼 등)과는 따로 고릅니다.</p>
            <ChoiceCards aria-labelledby="task-mode-heading" aria-describedby="task-mode-summary" value={form.taskMode || "explore"} onChange={value => update("taskMode", value as ProjectContext["taskMode"])} options={[
              {value: "metric", label: labels.taskMode.metric, description: "외부·사내 평가 지표를 올리는 과제입니다. 예: 환자경험평가 점수 개선"},
              {value: "explore", label: labels.taskMode.explore, description: "아직 드러나지 않은 맥락과 기회를 찾는 과제입니다. 예: 새 주거 컨셉 발굴"},
            ]} />
            <p id="task-mode-summary" className="ds-t-caption" role="status">{form.taskMode === "metric" ? "핵심 지표 필수" : "핵심 지표 선택"}</p>
          </Card>
          <Card className="space-y-6"><div className="flex justify-between gap-3"><div><h2 className="ds-t-card">0-A 프로젝트 개요</h2><p className="ds-t-caption">필수 · 지켜지는 값. 어긋나는 결과는 막지 않고 방향성과 맞지 않을 수 있음으로 표시합니다.</p></div><Badge>가드레일</Badge></div>
            <div className="grid gap-6 md:grid-cols-2"><Input label="제품명" required value={form.bk} onChange={event => update("bk", event.target.value)} error={errors.bk} hint="크롤링 검색어에는 붙지 않습니다." /><Input label="한줄 정의" required value={form.oneLiner} onChange={event => update("oneLiner", event.target.value)} error={errors.oneLiner} /></div>
            {single("projectType", "프로젝트 성격")}
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">{researchTemplates(form.taskMode, form.bk).map(template => <Button key={template.id} size="sm" onClick={() => update("researchQuestion", {template: template.id, text: template.text})}>{template.title}</Button>)}</div>
              <Input label="리서치 질문" required value={form.researchQuestion.text} onChange={event => update("researchQuestion", {...form.researchQuestion, text: event.target.value})} error={errors.researchQuestion} hint="템플릿을 고르면 채워지고, 자유롭게 고칠 수 있습니다." />
            </div>
            <fieldset className="min-w-0 space-y-2" aria-labelledby="metrics-heading" aria-describedby={`metrics-hint${errors.keyMetrics ? " metrics-error" : ""}`} tabIndex={-1} aria-invalid={!!errors.keyMetrics || undefined}>
              <h3 id="metrics-heading" className="ds-t-label">핵심 지표 {form.taskMode === "metric" ? "*" : "(선택)"}</h3>
              <p id="metrics-hint" className="ds-t-caption">{form.taskMode === "metric" ? "지표명은 필수입니다. 출처와 관련 설문 문항을 함께 적으면 키워드가 지표가 떨어지는 순간을 겨냥합니다." : "선택 입력입니다. 방향을 잡는 지표가 있으면 적으세요."}</p>
              <div className="grid gap-3 md:grid-cols-3">
                <Input label="지표명" value={metric.name} onChange={event => setMetric({...metric, name: event.target.value})} onKeyDown={event => submitOnEnter(event, addMetric)} />
                <Input label="출처" value={metric.source} onChange={event => setMetric({...metric, source: event.target.value})} />
                <Input label="관련 설문 문항" value={metric.item} onChange={event => setMetric({...metric, item: event.target.value})} />
              </div>
              <Button size="sm" disabled={!metric.name.trim()} onClick={addMetric}>지표 추가하기</Button>
              {errors.keyMetrics && <p id="metrics-error" className="ds-err">{errors.keyMetrics}</p>}
              {form.keyMetrics.map((entry, index) => <div key={index} className="flex items-center justify-between gap-2"><span className="ds-t-body">{[entry.name, entry.source, entry.item].filter(Boolean).join(" · ")}</span><Button size="sm" variant="quiet" onClick={() => update("keyMetrics", form.keyMetrics.filter((_, i) => i !== index))}>삭제하기</Button></div>)}
            </fieldset>
            <div className="grid gap-6 md:grid-cols-2">
              <ListInput label="사내 제약" value={form.constraints} onChange={value => update("constraints", value)} />
              {form.taskMode === "metric" ? <details open={positioningOpen(form.taskMode, form.positioning)} className="space-y-3"><summary className="ds-t-label">브랜드 포지셔닝 (선택)</summary>{positioning}</details> : <div className="space-y-3"><h3 className="ds-t-label">브랜드 포지셔닝 (선택)</h3>{positioning}</div>}
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              <fieldset className="min-w-0" aria-labelledby="channels-heading" aria-describedby={errors.channels ? "channels-error" : undefined} tabIndex={-1} aria-invalid={!!errors.channels || undefined}><h3 id="channels-heading" className="ds-t-label">수집 채널 *</h3><ChoiceChips multiple label="수집 채널" options={options(labels.channels).filter(option => INTERNAL_TOOLS || option.value !== "fixture")} value={form.channels} onChange={value => update("channels", value)} />{errors.channels && <p id="channels-error" className="ds-err">{errors.channels}</p>}</fieldset>
              <ListInput label="이미 아는 것" value={form.knownInsights} onChange={value => update("knownInsights", value)} />
            </div>
          </Card>
          <Card className="space-y-4">
            <div className="flex justify-between gap-3"><div><h2 className="ds-t-card">생각하는 페르소나 (선택)</h2><p className="ds-t-caption">떠오르는 사람을 한 줄씩 적으세요. 결과는 이 목록을 넘어서도록 지시합니다.</p></div><Badge>시드</Badge></div>
            <div className="flex flex-wrap items-end gap-2"><Input label="페르소나" placeholder="예: 초진 보호자" maxLength={40} disabled={seeds.items.length >= 20} value={personaText} onChange={event => setPersonaText(event.target.value)} onKeyDown={event => submitOnEnter(event, addPersona)} /><Button size="sm" disabled={seeds.items.length >= 20} onClick={addPersona}>추가하기</Button></div>
            {(seeds.items.length >= 20 || personaNotice) && <p className="ds-t-caption" role="status">20개까지 적을 수 있습니다.</p>}
            {seeds.items.map((seed, index) => <div key={seed.text} className="grid grid-cols-[1fr_auto] items-center gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto]">
              <span className="ds-t-body break-words">{seed.text}</span>
              <ChoiceChips className="col-span-2 row-start-2 md:col-span-1 md:col-start-2 md:row-start-1 [&_button]:min-h-9" label={`${seed.text} 디멘션`} options={dimensionOptions} value={seed.dimension || ""} onChange={value => update("personaSeeds", {...seeds, items: seeds.items.map((entry, i) => i === index ? {...entry, dimension: (toggleChoice(entry.dimension, value) || null) as typeof entry.dimension} : entry)})} />
              <Button className="col-start-2 row-start-1 md:col-start-3" size="sm" variant="quiet" onClick={() => { update("personaSeeds", {...seeds, items: seeds.items.filter((_, i) => i !== index)}); setPersonaNotice(""); }}>삭제하기</Button>
            </div>)}
            {seeds.items.length > 0 && <p className="ds-t-caption" role="status">{missing.length ? `아직 안 적은 관점: ${missing.map(code => labels.personaDimensions[code]).join(" · ")}` : "네 관점이 모두 있습니다."}</p>}
            <Checkbox label="예시와 다른 페르소나를 우선 발굴" checked={seeds.exploreBeyond} onChange={event => update("personaSeeds", {...seeds, exploreBeyond: event.target.checked})} />
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
        {INTERNAL_TOOLS && <aside><Card className="lg:sticky lg:top-6"><details open><summary className="ds-t-label">project_context.md 미리보기</summary><p className="ds-t-caption">서버 저장 맥락을 바탕으로 만든 미리보기입니다.</p><pre style={{color:"var(--ink)"}} className="ds-t-caption whitespace-pre-wrap break-words">{preview(returned || form)}</pre></details></Card></aside>}
      </div>}
    </VersionStage>}
  </div>;
}
