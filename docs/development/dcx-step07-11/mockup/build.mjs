import fs from 'node:fs';
import path from 'node:path';

const dir = path.dirname(new URL(import.meta.url).pathname);
const css = fs.readFileSync(path.join(dir, '_shell.css'), 'utf8');
const glassCss = fs.readFileSync(path.join(dir, '_shell.glass.css'), 'utf8');

// Liquid Glass 변형을 함께 내는 화면 (DESIGN copy.md)
// Liquid Glass는 Person A 시스템(Light 단일 테마 · 정적 카드 그림자 금지)과 충돌하므로
// 생성을 멈추고 마지막 빌드 상태로 동결한다. 되살리려면 'all' 로 되돌린다.
const GLASS = new Set();

const STEPS = [
  ['Data Defining', [
    ['00', '세션', 'Main'],
    ['01·02', '입력 선언', 'Declare'],
    ['03', '키워드 설계', 'Keywords'],
    ['04', '데이터 수집', 'Crawling'],
  ]],
  ['Data Sensing', [
    ['05', '전처리 · 임베딩', 'Preprocess'],
    ['06-A', '모델 학습', 'Training'],
    ['06-B', '근거 판정', 'Labeling'],
    ['07', '군집', 'Clustering'],
    ['08', '페르소나', 'Persona'],
    ['09', '근거 수집', 'Evidence'],
  ]],
  ['Data Shaping', [
    ['10-A', 'Customer Action Map', 'ContextMap'],
    ['10-B', '기회 영역', 'Opportunity'],
    ['11-A', '인사이트 도출', 'Concept'],
    ['11-B', '경험 디자인 컨셉', 'Design'],
  ]],
  ['운영', [
    ['ADM', '프롬프트 관리', 'Admin'],
  ]],
];
const ORDER = STEPS.flatMap(([, s]) => s.map(x => x[2]));

function sidebar(active) {
  const ai = ORDER.indexOf(active);
  let h = '<nav class="side">';
  for (const [grp, items] of STEPS) {
    h += `<div class="grp">${grp}</div>`;
    for (const [no, name, key] of items) {
      const i = ORDER.indexOf(key);
      const on = key === active;
      const st = on ? 'cur' : i < ai ? 'done' : '';
      h += `<div class="step${on ? ' on' : ''}"><span class="no">${no}</span><span>${name}</span><span class="st ${st}"></span></div>`;
    }
  }
  h += `<div class="note"><div class="lab">활성 선언</div>
    <p class="xs" style="margin:6px 0 0;color:var(--sec)">무선 이어폰을 운동·건강 맥락에서 재정의할 미충족 니즈를 찾는다</p>
    <p class="xs" style="margin:6px 0 0">STEP 01 한줄 정의 · 전 단계 프롬프트 헤더로 상주</p></div>`;
  return h + '</nav>';
}

function topbar() {
  return `<header class="top">
  <div class="brand"><span class="dot"></span>DCX Agent</div>
  <span class="sep"></span>
  <span class="pill on">에어팟 프로 3 · 운동·건강 맥락 <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M6 9l6 6 6-6"/></svg></span>
  <span class="pill">세션 3개</span>
  <span class="grow"></span>
  <span class="pill">작업 2건 실행 중</span>
  <span class="pill">문서 검색</span>
  <span class="btn gho">내보내기</span>
  <span class="btn pri">세션 저장</span>
</header>`;
}

function meta(src, key, dflt) {
  const m = src.match(new RegExp(`<!--${key}:([\\s\\S]*?)-->`));
  return m ? m[1].trim() : dflt;
}

const outDir = path.join(dir, 'project');
fs.mkdirSync(outDir, { recursive: true });
const built = [];
const files = fs.readdirSync(path.join(dir, 'parts')).filter(f => f.endsWith('.body.html'));
for (const f of files) {
  const name = f.replace('.body.html', '');
  const src = fs.readFileSync(path.join(dir, 'parts', f), 'utf8');
  const h = meta(src, 'h', '1180');
  const title = meta(src, 'title', name);
  const sub = meta(src, 'sub', '');
  const chatMode = meta(src, 'chat', 'full');

  const sections = src.split(/\[\[(MAIN|CHAT|ANN)\]\]/);
  const part = {};
  for (let i = 1; i < sections.length; i += 2) part[sections[i]] = sections[i + 1].trim();

  const chat = chatMode === 'rail'
    ? `<aside class="chat rail">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#565c66" stroke-width="1.7"><path d="M21 12a8 8 0 0 1-8 8H7l-4 3v-5.5A8 8 0 0 1 11 4h2a8 8 0 0 1 8 8Z"/></svg>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#747a84" stroke-width="1.7"><path d="M4 6h16M4 12h16M4 18h10"/></svg>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#747a84" stroke-width="1.7"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      </aside>`
    : `<aside class="chat">${part.CHAT || ''}</aside>`;

  const ann = part.ANN ? `<section class="ann">
    <h4>1.0 대비 변경점</h4>
    <p class="lead"><span class="tag rep">치환</span>AS-IS가 있고 대체된다 &nbsp;<span class="tag new">신설</span>AS-IS 없음 · 새로 꽂는다 &nbsp;<span class="tag keep">유지</span>기존 확정 재확인 &nbsp;<span class="tag open">미결</span>답이 필요한 것</p>
    <div class="grid">${part.ANN}</div>
  </section>` : '';

  const render = (sheet, theme) => `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>
${sheet}
  </style>
</helmet>
<div class="art${theme}" style="width: 1440px; height: ${h}px;">
  <div class="app">
    ${topbar()}
    <div class="body">
      ${sidebar(name)}
      <main class="main">
        <div class="mhead"><h1>${title}</h1>${sub ? `<div class="sub">${sub}</div>` : ''}</div>
        <div class="mbody">
${part.MAIN || ''}
        </div>
      </main>
      ${chat}
    </div>
  </div>
  ${ann}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":1440,"height":${h}}}'>
class Component extends DCLogic {
  renderVals() { return {}; }
}
</script>
</body>
</html>
`;
  const out = render(css, '');
  fs.writeFileSync(path.join(outDir, `${name}.dc.html`), out);
  built.push([`${name}.dc.html`, out.length]);
  if (GLASS === 'all' || GLASS.has(name)) {
    const g = render(css + '\n' + glassCss, ' glass');
    fs.writeFileSync(path.join(outDir, `${name}.glass.dc.html`), g);
    built.push([`${name}.glass.dc.html`, g.length]);
  }
}

for (const [f, n] of built) console.log('built project/' + f, n + 'b');
console.log(built.length + ' artboards');
