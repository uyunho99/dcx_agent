import fs from 'node:fs';
import path from 'node:path';
const dir = path.dirname(new URL(import.meta.url).pathname);
const css = fs.readFileSync(path.join(dir, '_shell.css'), 'utf8');
const glass = fs.readFileSync(path.join(dir, '_shell.glass.css'), 'utf8');

// 글래스 시트를 .art.glass 아래로 스코프한다 — 한 페이지에 두 테마가 공존하므로.
function scope(sheet, root) {
  // 주석을 먼저 지운다 — 주석이 셀렉터 앞에 붙으면 스코프가 깨져 다른 테마로 샌다.
  sheet = sheet.replace(/\/\*[\s\S]*?\*\//g, '');
  return sheet.replace(/(^|\})\s*([^{}@]+)\{/g, (m, close, sel) => {
    const scoped = sel.split(',').map(s => {
      s = s.trim();
      if (!s || s.startsWith('/*')) return s;
      if (s === ':root' || s === 'body' || s === '.art') return root;
      if (s.startsWith('.art')) return root + s.slice(4);
      return `${root} ${s}`;
    }).join(', ');
    return `${close}\n${scoped}{`;
  });
}

const files = fs.readdirSync(path.join(dir,'project')).filter(f => f.endsWith('.dc.html')).sort();
let out = `<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400..700&family=Noto+Sans+KR:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>${css}
${scope(glass, '.art.glass')}
html{background:#c9ced7}body{padding:24px;display:flex;flex-direction:column;gap:40px;align-items:flex-start}
.cap{font:600 13px Inter,sans-serif;color:#2f343b;letter-spacing:.04em;text-transform:uppercase}
.art{outline:1px solid #9aa1ad;box-shadow:0 2px 18px rgba(11,12,15,.16);transform:scale(var(--z,1));transform-origin:top left}
.slot{overflow:hidden}</style>`;
for (const f of files) {
  const s = fs.readFileSync(path.join(dir, 'project', f), 'utf8');
  const m = s.match(/<div class="art[\s\S]*<\/div>\s*<\/x-dc>/);
  const body = m ? m[0].replace(/<\/x-dc>/, '') : '(parse fail)';
  const hm = body.match(/height:(\d+)px/);
  const h = hm ? Number(hm[1]) : 600;
  out += `<div><div class="cap">${f}</div><div class="slot" style="width:1440px;height:${h}px">${body}</div></div>`;
}
fs.writeFileSync(path.join(dir, 'preview.html'), out);
console.log('preview.html', out.length);
