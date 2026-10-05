/* 도식 SVG 생성기 — 브라우저 단일 소스.
   Python(svgfig.py)이 서버에서 그리던 것을 옮겨왔다. 이유: 편집기에서 유형·단계를 바꾸면
   좌표를 전부 다시 계산해야 하는데, 생성기가 서버에만 있으면 즉시 반영이 불가능하다.
   PDF도 Chrome headless로 뽑으므로 브라우저가 그려도 벡터·한글 텍스트가 그대로 남는다.

   window.SVGFIG.render(spec, 자리?) → SVG 문자열
   window.SVGFIG.mount(el)    → el.dataset.fig 를 읽어 그 안에 캡션·SVG·함의를 채운다
   window.SVGFIG.refresh()    → 전부 다시 그려 달라진 도식 수를 돌려준다(글꼴 로드 뒤 재조판용)

   ── 크기·글자('26-09-28 재설계 P0, 사장님 판정) ──
   예전에는 픽셀 고정 좌표로 그리고 <svg width=고유폭> 을 박아, 풀버전 도식이 어디에 넣어도
   배율 1.00·글자 5.4~9.8pt(본문의 0.38~0.70배)로 찍혔다(실측 44/44). 이제는
     · 그리는 순간 칸의 실제 폭(clientWidth, 0 이면 프리셋 mm)을 viewBox 폭으로 쓴다 — 배율이 늘 1
     · 글자는 pt 로 정한다. 역할별로 문서 전체에 고정(흐름 11pt · 체계도 13pt · 차트 10.5pt,
       하한 10.5pt — tokens.css --fig-pt-*). 칸이 좁다고 글자를 줄이지 않는다
     · 폭이 모자라면 줄을 바꾼다(흐름은 2줄 뱀까지, 한 줄에 3개가 안 들어가면 세로 목록형 —
       2×2 뱀은 순환도로 읽혀서 막는다)
     · 크기 = 작게|보통|크게(스펙 '크기', 기본 보통). 크게 = 면적과 글자를 같이 키운다.
       옛 값(슬라이드 '가득', 도식 '폭' % 따위)은 svgfig.py 크기정규화 한 곳이 이 셋으로 접는다
   ── 색 ──
   색 상수를 두지 않는다. --fig-* 토큰(build/도식색.py 가 hex 로 미리 계산)만 읽는다.
   스펙에는 hex 대신 역할(강조·보조·회색·분야1·분야2)만 적고, 칠은 아래 칠() 표가 정한다.
   강조 자동은 수렴 결과와 차트 최신값에만 준다. 강조는 굵은 테로도 표시해 흑백에서도 보인다. */
(() => {
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const w = s => [...String(s)].reduce((a, c) => a + (c.codePointAt(0) > 0x2000 ? 1 : 0.55), 0);
const r1 = n => Math.round(n * 10) / 10;
// 스펙 값을 숫자 자리에 쓸 때는 이걸 거친다 — 유한수가 아니면 0('26-09-28 스택 막대 XSS).
const 유한 = v => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const 제것 = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
// 지은 글을 칸에 넣는 한 자리('26-10-01 감사 code F7) — 넣는 글은 이 파일이 지은 HTML·SVG 뿐이고, 스펙 글자는
// esc() 를, 숫자는 유한()·r1() 을, 색은 토큰 hex 를 거친다. test/r38_figdom38.py 가 높이 후보·쪽 나눔·한 쪽 채우기·
// refresh 길을 독 스펙으로 모두 밟아 넣은 글을 DOM 으로 다시 읽는다. innerHTML 을 다른 데서 직접 쓰지 않는다.
function 그려넣기(el, html) { el.innerHTML = html; }
const PT = 96 / 72, MM = 96 / 25.4;

// ── 토큰 ─────────────────────────────────────────────────────────────
// 대체값은 CSS 가 없는 자리(독립 시험 쪽 등)에서만 쓴다 — tokens.css 의 남색 기본과 같은 값이다
// (build/도식색.py 팔레트('#1F3864'); test/r18_figs18.py 가 대조한다).
const 토큰기본 = {
  "accent": "#1F3864", "on-accent": "#FFFFFF", "mid": "#B1B9C9", "soft": "#E4E7EC",
  "chart": "#1F3864", "chart-mid": "#A1ABBE", "cat1-mid": "#B1D6CD", "cat1-soft": "#E2F0EC",
  "cat2-mid": "#ECCEB4", "cat2-soft": "#F8EDE3", "gray": "#F2F2F2", "line": "#6E6E6E",
  "ink": "#111111", "sub": "#444444", "frame": "#B8B8B8", "bg": "#FFFFFF",
};
const 수치기본 = { "pt-flow": 11, "pt-sys": 13, "pt-chart": 10.5, "pt-sub": 10.5, "pt-min": 10.5,
                  "slot-mm": 170, "max-h-mm": 222, "chart-h-mm": 58, "chart-big-h-mm": 82,
                  "chart-half-h-mm": 44 };
const 색꼴 = /^#[0-9A-Fa-f]{6}$/;
function 토큰읽기(el) {
  let cs = null;
  try { cs = el && el.isConnected ? getComputedStyle(el) : null; } catch (e) { cs = null; }
  const 색 = {}, 수치 = {};
  for (const k in 토큰기본) {
    const v = cs ? cs.getPropertyValue("--fig-" + k).trim() : "";
    색[k] = 색꼴.test(v) ? v.toUpperCase() : 토큰기본[k];      // hex 만 받는다 — 속성에 들어간다
  }
  for (const k in 수치기본) {
    const v = cs ? parseFloat(cs.getPropertyValue("--fig-" + k)) : NaN;
    const [lo, hi] = k.startsWith("pt") ? [6, 40] : [10, 400];
    수치[k] = Number.isFinite(v) && v >= lo && v <= hi ? v : 수치기본[k];
  }
  return { 색, 수치 };
}

// ── 역할 → 칠 (허용 목록 사상 — 스펙 글자를 속성에 그대로 쓰지 않는다) ─────────
const 역할들 = { "강조": 1, "보조": 1, "회색": 1, "분야1": 1, "분야2": 1 };
const 역할 = (o, 기본 = "보조") => {
  if (o && typeof o === "object") {
    const v = o["색"];
    if (typeof v === "string" && 제것(역할들, v)) return v;
    if (o["강조"] === true) return "강조";
  }
  return 기본;
};
function 칠(색, 역, 층 = "몸") {
  if (역 === "강조") return { fill: 색.accent, text: 색["on-accent"], stroke: 색.accent, sw: 2.2, bold: 700 };
  if (역 === "회색") return { fill: 색.gray, text: 색.ink, stroke: 색.line, sw: 1, bold: 700 };
  if (역 === "분야1" || 역 === "분야2") {
    const n = 역 === "분야1" ? 1 : 2;
    return { fill: 층 === "머리" ? 색[`cat${n}-mid`] : 색[`cat${n}-soft`], text: 색.ink,
             stroke: 색.line, sw: 1, bold: 700 };
  }
  if (역 === "라벨") return { fill: 색.accent, text: 색["on-accent"], stroke: 색.accent, sw: 1, bold: 700 };
  return { fill: 층 === "머리" ? 색.mid : 색.soft, text: 색.ink, stroke: 색.line, sw: 1, bold: 700 };
}

// ── 글 줄바꿈·재기 ───────────────────────────────────────────────────
// 어절 경계에서만 나눈다. 편집기는 tspan 을 공백으로 이어 라벨을 되읽으므로(svgLabelText)
// 어절 한가운데를 끊으면 저장할 때 글에 공백이 끼어든다 — 그래서 긴 어절은 자리를 넓히는
// 쪽(세로 목록형)으로 푼다. 글 폭은 글자 수 어림(w)이라 글꼴이 늦게 앉아도 배치가 같다.
function wrap(text, maxEm) {
  const out = []; let cur = "";
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const t = cur ? cur + " " + word : word;
    if (cur && w(t) > maxEm) { out.push(cur); cur = word; } else cur = t;
  }
  if (cur) out.push(cur);
  return out.length ? out : [""];
}
const 긴어절 = s => Math.max(0, ...String(s).split(/\s+/).filter(Boolean).map(w));
const 글폭 = (s, f) => w(s) * f * 1.04;
function tspans(lines, x, y0, fs, lh = 1.3) {
  const top = y0 - (lines.length - 1) * fs * lh / 2;
  return lines.map((t, i) => `<tspan x="${r1(x)}" y="${r1(top + i * fs * lh)}">${esc(t)}</tspan>`).join("");
}
// 원소 라벨 폴백 — 라벨 ?? label ?? name ?? 이름 ?? 제목 ?? text ?? title. 서버 정규화(assemble_slides.py
// _도식정규화)가 놓친 원소가 편집기 remount·클라 재렌더로 넘어와도 빈 박스로 안 보이게 여기서도 넓게 받는다
// (실측 2026-09-06: 타입-배열키 불일치로 나온 도식은 여기서 한 번 더 걸러야 편집기에서도 라벨이 산다).
const lab = s => (s && typeof s === "object")
  ? (s["라벨"] ?? s.label ?? s.name ?? s["이름"] ?? s["제목"] ?? s.text ?? s.title ?? "")
  : (s ?? "");
const 배열 = v => Array.isArray(v) ? v : [];

// 상자 하나 — 줄 수에 맞춘 높이를 부르는 쪽이 준다. 글은 tspan(편집기 라벨 자리)으로만 낸다 —
// 편집기(figLabels·syncFigSpec)는 tspan 든 <text> 를 차례대로 스펙 라벨에 되박으므로, 라벨이
// 아닌 글(주체·전이·번호·축)은 tspan 없이 낸다. 라벨 차례는 figSetters 차례와 같아야 한다.
function 상자(C, x, y, bw, bh, lines, 칠값, f, o = {}) {
  const 가운데x = o.왼쪽 ? x + C.padX : x + bw / 2;
  return `<rect x="${r1(x)}" y="${r1(y)}" width="${r1(bw)}" height="${r1(bh)}" rx="1.5" `
       + `fill="${칠값.fill}" stroke="${칠값.stroke}" stroke-width="${칠값.sw}"/>`
       + `<text x="${r1(가운데x)}" y="${r1(y + bh / 2)}" font-size="${r1(f)}" fill="${칠값.text}" `
       + `font-weight="${o.굵기 || 칠값.bold}" text-anchor="${o.왼쪽 ? "start" : "middle"}" `
       + `dominant-baseline="central">${tspans(lines, 가운데x, y + bh / 2, f)}</text>`;
}
const 줄높이 = (n, f) => n * f * 1.3;
function 화살촉(C) {
  return `<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="${r1(C.f * 0.42)}" `
       + `markerHeight="${r1(C.f * 0.42)}" markerUnits="userSpaceOnUse" orient="auto-start-reverse">`
       + `<path d="M0,0 L10,5 L0,10 z" fill="${C.색.line}"/></marker></defs>`;
}
function 선(C, x1, y1, x2, y2, o = {}) {
  return `<line x1="${r1(x1)}" y1="${r1(y1)}" x2="${r1(x2)}" y2="${r1(y2)}" stroke="${C.색.line}" `
       + `stroke-width="${o.sw || 1.4}"${o.끝 === false ? "" : ' marker-end="url(#ah)"'}`
       + `${o.양쪽 ? ' marker-start="url(#ah)"' : ""}/>`;
}
function 작은글(C, x, y, t, o = {}) {
  if (!t) return "";
  return `<text x="${r1(x)}" y="${r1(y)}" font-size="${r1(C.fs)}" fill="${C.색.sub}" `
       + `text-anchor="${o.끝 || "middle"}"${o.가운데 ? ' dominant-baseline="central"' : ""}`
       + `${o.굵게 ? ' font-weight="700"' : ""}>${esc(t)}</text>`;
}
// 가운데에서 네모 가장자리까지의 거리(방향 dx,dy 단위벡터) — 화살이 상자를 뚫지 않게
function 변까지(hw, hh, dx, dy) {
  const tx = Math.abs(dx) > 1e-6 ? hw / Math.abs(dx) : Infinity;
  const ty = Math.abs(dy) > 1e-6 ? hh / Math.abs(dy) : Infinity;
  return Math.min(tx, ty);
}
function 잇기(C, a, b, o = {}) {       // a,b = {x,y,hw,hh} 가운데·반폭·반높이
  const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d;
  const pad = C.f * 0.25;
  const s = 변까지(a.hw, a.hh, ux, uy) + pad, e = 변까지(b.hw, b.hh, ux, uy) + pad;
  if (s + e >= d) return "";
  return 선(C, a.x + ux * s, a.y + uy * s, b.x - ux * e, b.y - uy * e, o);
}
function 번호칩(C, cx, cy, n, 칠값) {
  const r = C.f * 0.78;
  return `<circle cx="${r1(cx)}" cy="${r1(cy)}" r="${r1(r)}" fill="${칠값.fill}" stroke="${칠값.stroke}" `
       + `stroke-width="1"/><text x="${r1(cx)}" y="${r1(cy)}" font-size="${r1(Math.max(C.f * 0.95, C.min))}" `
       + `font-weight="700" fill="${칠값.text}" text-anchor="middle" dominant-baseline="central">${n}</text>`;
}

// ── 세로 목록형 — 한 줄에 3개가 안 들어갈 때(절차·순환·수렴 공용) ───────────────
// 번호 칩 + 단계 이름 상자 + (주체) 를 한 줄씩. 줄 사이 ↓ 와 전이 글.
function 세로목록(C, 항목들, o = {}) {
  const f = C.f, 칩 = f * 1.9, x0 = 칩 + f * 0.5, bw = C.W - x0;
  const out = [화살촉(C)];
  let y = 2;
  항목들.forEach((it, i) => {
    const 주체 = it.주체 ? `* ${it.주체}` : "";
    const 주체폭 = 주체 ? 글폭(주체, C.fs) + C.padX : 0;
    const lines = wrap(it.글, (bw - 2 * C.padX - 주체폭) / (f * 1.04));
    const bh = 줄높이(lines.length, f) + 2 * C.padY;
    const 칠값 = 칠(C.색, it.역);
    out.push(번호칩(C, 칩 / 2, y + bh / 2, i + 1, 칠(C.색, it.역 === "강조" ? "강조" : "보조", "머리")));
    out.push(상자(C, x0, y, bw, bh, lines, 칠값, f, { 왼쪽: true }));
    if (주체) out.push(작은글(C, x0 + bw - C.padX, y + bh / 2, 주체, { 끝: "end", 가운데: true }));
    y += bh;
    if (i < 항목들.length - 1 || o.돌아감) {
      const 틈 = f * 1.9;
      out.push(선(C, 칩 / 2, y + f * 0.2, 칩 / 2, y + 틈 - f * 0.2));
      if (it.전이) out.push(작은글(C, 칩 / 2 + f * 0.6, y + 틈 / 2, it.전이, { 끝: "start", 가운데: true }));
      y += 틈;
    }
  });
  if (o.돌아감) out.push(작은글(C, 칩 / 2, y + C.fs * 0.4, "처음 단계로 돌아가 되풀이", { 끝: "start" }));
  return [C.W, y + (o.돌아감 ? C.fs * 1.2 : 2), out.join("")];
}

const R = {};
// 절차 — 한 줄 → 2줄 뱀(한 줄 3개 이상일 때만) → 세로 목록형
R.process = (sp, C) => {
  const steps = 배열(sp["단계"]), n = steps.length, f = C.f;
  const 항목들 = steps.map(st => ({
    글: lab(st), 역: 역할(st),
    주체: st && typeof st === "object" && st["주체"] ? String(st["주체"]) : "",
    전이: st && typeof st === "object" && st["전이"] ? String(st["전이"]) : "" }));
  if (!n) return [C.W, f * 2, ""];
  const 전이폭 = Math.max(0, ...항목들.map(it => it.전이 ? 글폭(it.전이, C.fs) + f * 0.6 : 0));
  const gap = Math.max(f * 2.4 * C.sp, 전이폭);
  const bwMin = Math.max(f * 4.3, Math.max(...항목들.map(it => 긴어절(it.글))) * f * 1.04) + 2 * C.padX;
  const 칸폭 = k => (C.W - (k - 1) * gap) / k;
  let k = n, 줄 = 1;
  if (n > 1 && 칸폭(n) < bwMin) {
    k = Math.ceil(n / 2); 줄 = 2;
    if (k < 3 || 칸폭(k) < bwMin) return 세로목록(C, 항목들);
  }
  const bw = 칸폭(k);
  const 줄들 = 항목들.map(it => wrap(it.글, (bw - 2 * C.padX) / (f * 1.04)));
  let bh = 줄높이(Math.max(...줄들.map(l => l.length)), f) + 2 * C.padY;
  // 칸 폭(간격 빼기 전) 기준 × 크기 배율 — 크게일수록 높아진다(간격이 넓어져 bw 가 줄어도 단조)
  if (C.슬) bh = Math.max(bh, Math.min(C.W / k * 0.42 * C.sp, C.maxH * 0.5 / 줄 - f * 2));
  const 주체h = 항목들.some(it => it.주체) ? C.fs * 1.6 : 0;
  const 줄틈 = f * 2.6;
  // 첫 줄 화살표 위 전이 글이 viewBox 위로 나가지 않게 위 여유를 둔다(작게에서 상자가 낮으면 나갔다)
  const 위 = 2 + (항목들.some(it => it.전이) ? Math.max(0, C.fs * 1.05 - (bh / 2 - f * 0.45)) : 0);
  const out = [화살촉(C)];
  const 자리 = i => {
    const r = i < k ? 0 : 1, j = r ? i - k : i;
    const col = r ? (k - 1 - j) : j;                     // 둘째 줄은 오른쪽에서 왼쪽으로(뱀)
    return { x: col * (bw + gap), y: 위 + r * (bh + 주체h + 줄틈), r };
  };
  항목들.forEach((it, i) => {
    const p = 자리(i);
    out.push(상자(C, p.x, p.y, bw, bh, 줄들[i], 칠(C.색, it.역), f));
    if (it.주체) out.push(작은글(C, p.x + bw / 2, p.y + bh + C.fs * 1.15, `* ${it.주체}`));
    if (i < n - 1) {
      const q = 자리(i + 1), cy = p.y + bh / 2;
      if (q.r === p.r) {
        const 오른 = q.x > p.x;
        const x1 = 오른 ? p.x + bw + f * 0.25 : p.x - f * 0.25, x2 = 오른 ? q.x - f * 0.25 : q.x + bw + f * 0.25;
        out.push(선(C, x1, cy, x2, cy));
        out.push(작은글(C, (x1 + x2) / 2, cy - f * 0.45, it.전이));
      } else {                                           // 줄을 내려간다(끝 칸 아래로)
        const x = p.x + bw / 2, y1 = p.y + bh + 주체h + f * 0.2, y2 = q.y - f * 0.2;
        out.push(선(C, x, y1, x, y2));
        out.push(작은글(C, x - f * 0.5, (y1 + y2) / 2, it.전이, { 끝: "end", 가운데: true }));
      }
    }
  });
  return [C.W, 위 + 줄 * (bh + 주체h) + (줄 - 1) * 줄틈 + 2, out.join("")];
};
// 순환 — 타원 둘레에 놓는다. 7개 이상이거나 칸이 좁으면 세로 목록형(끝에 '되풀이' 표시)
R.cycle = (sp, C) => {
  const steps = 배열(sp["단계"]), n = steps.length, f = C.f;
  const 항목들 = steps.map(st => ({ 글: lab(st), 역: 역할(st) }));
  if (n < 3) return R.process(sp, C);
  const bwMin = Math.max(f * 4.3, Math.max(...항목들.map(it => 긴어절(it.글))) * f * 1.04) + 2 * C.padX;
  const bw = Math.max(bwMin, Math.min(C.W / 3.4, Math.max(...항목들.map(it => 글폭(it.글, f))) + 2 * C.padX));
  if (n > 6 || C.W < bw * 2.6) return 세로목록(C, 항목들, { 돌아감: true });
  const 줄들 = 항목들.map(it => wrap(it.글, (bw - 2 * C.padX) / (f * 1.04)));
  const bh = 줄높이(Math.max(...줄들.map(l => l.length)), f) + 2 * C.padY;
  const rx = Math.min((C.W - bw) / 2 - 2, bw * 1.25 + f * 4 * C.sp);
  let ry = Math.max(bh * (n > 4 ? 1.35 : 1.1), rx * 0.42 * C.sp);
  ry = Math.min(ry, Math.max(bh * 1.1, (C.maxH - bh - 8) / 2));
  const cx = C.W / 2, cy = ry + bh / 2 + 3;
  const pts = 항목들.map((_, i) => {
    const a = -Math.PI / 2 + 2 * Math.PI * i / n;
    return { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a), hw: bw / 2, hh: bh / 2 };
  });
  const out = [화살촉(C)];
  pts.forEach((p, i) => out.push(잇기(C, p, pts[(i + 1) % n])));
  pts.forEach((p, i) => out.push(상자(C, p.x - bw / 2, p.y - bh / 2, bw, bh, 줄들[i], 칠(C.색, 항목들[i].역), f)));
  return [C.W, cy + ry + bh / 2 + 3, out.join("")];
};
// 수렴 — 요건 N → 시행 → 결과(자동 강조). 칸이 좁으면 위에서 아래로
R.converge = (sp, C) => {
  const f = C.f;
  const reqs = 배열(sp["요건"]).map(r => ({ 글: lab(r), 역: 역할(r) }));
  const 시행 = lab(sp["시행"]), 결과 = lab(sp["결과"]);
  // 시행이 비면 가운데 상자 없이 요건 → 결과로 잇는다 — 빈 회색 상자가 그려졌다(적대 검토 M6 '26-09-29)
  const 가운데없음 = !String(시행 || "").trim();
  const gap = f * 3 * C.sp;
  const 모두 = [...reqs.map(r => r.글), 시행, 결과];
  const bwMin = Math.max(f * 4.3, Math.max(...모두.map(긴어절)) * f * 1.04) + 2 * C.padX;
  const out = [화살촉(C)];
  let bw = 가운데없음 ? (C.W - gap) / 2 : (C.W - 2 * gap) / 3;
  if (bw >= bwMin) {
    const 줄 = t => wrap(t, (bw - 2 * C.padX) / (f * 1.04));
    const 요건줄 = reqs.map(r => 줄(r.글));
    const 요건h = 요건줄.map(l => 줄높이(l.length, f) + 2 * C.padY);
    const 틈 = f * 0.6;
    const colh = 요건h.reduce((a, b) => a + b, 0) + Math.max(0, reqs.length - 1) * 틈;
    const 시행줄 = 줄(시행), 결과줄 = 줄(결과);
    let 가운데h = Math.max(줄높이(Math.max(시행줄.length, 결과줄.length), f) + 2 * C.padY * 1.6, f * 3);
    if (C.슬) 가운데h = Math.max(가운데h, Math.min(C.W / 3 * 0.42 * C.sp, C.maxH * 0.6));
    const H = Math.max(colh, 가운데h) + 4, cy = H / 2;
    let y = cy - colh / 2;
    const x2 = bw + gap, x3 = 가운데없음 ? x2 : 2 * (bw + gap);
    reqs.forEach((r, i) => {
      out.push(상자(C, 0, y, bw, 요건h[i], 요건줄[i], 칠(C.색, r.역), f));
      out.push(잇기(C, { x: bw / 2, y: y + 요건h[i] / 2, hw: bw / 2, hh: 요건h[i] / 2 },
                       { x: x2 + bw / 2, y: cy, hw: bw / 2, hh: 가운데h / 2 }));
      y += 요건h[i] + 틈;
    });
    if (!가운데없음) {
      out.push(상자(C, x2, cy - 가운데h / 2, bw, 가운데h, 시행줄, 칠(C.색, "보조", "머리"), f));
      out.push(선(C, x2 + bw + f * 0.25, cy, x3 - f * 0.25, cy));
    }
    out.push(상자(C, x3, cy - 가운데h / 2, bw, 가운데h, 결과줄, 칠(C.색, "강조"), f));
    return [C.W, H, out.join("")];
  }
  // 세로: 요건(한 줄에 들어가면 나란히) ↓ 시행 ↓ 결과
  const n = Math.max(reqs.length, 1);
  let k = n;
  while (k > 1 && (C.W - (k - 1) * f) / k < bwMin) k--;
  const rw = (C.W - (k - 1) * f) / k;
  const 요건줄 = reqs.map(r => wrap(r.글, (rw - 2 * C.padX) / (f * 1.04)));
  const rh = 줄높이(Math.max(1, ...요건줄.map(l => l.length)), f) + 2 * C.padY;
  let y = 2;
  const rows = Math.ceil(reqs.length / k);
  reqs.forEach((r, i) => {
    const row = Math.floor(i / k), col = i % k;
    out.push(상자(C, col * (rw + f), y + row * (rh + f * 0.6), rw, rh, 요건줄[i], 칠(C.색, r.역), f));
  });
  y += rows * rh + Math.max(0, rows - 1) * f * 0.6;
  const cw = Math.min(C.W, Math.max(bwMin, C.W * 0.6)), cx = (C.W - cw) / 2;
  [[시행, "보조", "머리"], [결과, "강조", "몸"]].filter(([t], j) => j || !가운데없음).forEach(([t, 역, 층]) => {
    out.push(선(C, C.W / 2, y + f * 0.2, C.W / 2, y + f * 1.8));
    y += f * 2;
    const l = wrap(t, (cw - 2 * C.padX) / (f * 1.04)), h = 줄높이(l.length, f) + 2 * C.padY;
    out.push(상자(C, cx, y, cw, h, l, 칠(C.색, 역, 층), f));
    y += h;
  });
  return [C.W, y + 2, out.join("")];
};
// 체계도 — 목표(라벨: 진한 채움 한 줄) · 전략 머리(중간 파스텔 + 검정 굵게) · 과제(옅은 몸통)
R.strategy = (sp, C) => {
  const cols = 배열(sp["전략"]), n = cols.length;
  const fG = C.f + (C.크기 === "크게" ? 4 : 1) * PT, fH = C.f, fT = Math.max(C.f - PT, C.min);
  const out = [];
  const 목표 = lab(sp["목표"]);
  const gl = wrap(목표, (C.W - 2 * C.padX) / (fG * 1.04));
  const gh = 줄높이(gl.length, fG) + 2 * C.padY * 1.3;
  out.push(상자(C, 0, 0, C.W, gh, gl, 칠(C.색, "라벨"), fG));
  if (!n) return [C.W, gh, out.join("")];
  const gap = fH * 0.9 * C.sp;
  const 모두 = cols.flatMap(c => [lab(c), ...배열(c && c["과제"]).map(lab)]);
  const cwMin = Math.max(fH * 5.5, Math.max(...모두.map(긴어절)) * fH * 1.04) + 2 * C.padX;
  const cw = (C.W - (n - 1) * gap) / n;
  const 과제틈 = fT * 0.45 * C.sp;
  if (cw >= cwMin) {
    const 머리줄 = cols.map(c => wrap(lab(c), (cw - 2 * C.padX) / (fH * 1.04)));
    const hh = 줄높이(Math.max(...머리줄.map(l => l.length)), fH) + 2 * C.padY;
    const bus = gh + fH * 0.9 * C.sp, top = bus + fH * 0.9 * C.sp;
    const xs = cols.map((_, i) => i * (cw + gap) + cw / 2);
    out.push(`<line x1="${r1(C.W / 2)}" y1="${r1(gh)}" x2="${r1(C.W / 2)}" y2="${r1(bus)}" stroke="${C.색.line}" stroke-width="1.2"/>`);
    if (n > 1) out.push(`<line x1="${r1(xs[0])}" y1="${r1(bus)}" x2="${r1(xs[n - 1])}" y2="${r1(bus)}" stroke="${C.색.line}" stroke-width="1.2"/>`);
    let H = top + hh;
    cols.forEach((col, i) => {
      const x = i * (cw + gap), 역 = 역할(col);
      out.push(`<line x1="${r1(xs[i])}" y1="${r1(bus)}" x2="${r1(xs[i])}" y2="${r1(top)}" stroke="${C.색.line}" stroke-width="1.2"/>`);
      out.push(상자(C, x, top, cw, hh, 머리줄[i], 칠(C.색, 역, "머리"), fH));
      let y = top + hh + 과제틈;
      배열(col && col["과제"]).forEach(t => {
        const l = wrap(lab(t), (cw - 2 * C.padX) / (fT * 1.04)), th = 줄높이(l.length, fT) + 2 * C.padY * 0.8;
        // 과제 한 칸의 제 역할(판정 ④ '26-09-29)이 열 색보다 앞선다
        out.push(상자(C, x, y, cw, th, l, 칠(C.색, 역할(t, "") || (역 === "강조" ? "보조" : 역)), fT, { 굵기: 500 }));
        y += th + 과제틈;
      });
      H = Math.max(H, y - 과제틈);
    });
    return [C.W, H + 2, out.join("")];
  }
  // 줄 배치 — 전략이 많거나 칸이 좁으면 전략 하나가 한 줄(왼쪽 머리, 오른쪽 과제)
  const lw = Math.max(cwMin, C.W * 0.3), rw = C.W - lw - gap;
  let y = gh + fH * 0.8;
  cols.forEach(col => {
    const 역 = 역할(col);
    const 과제원 = 배열(col && col["과제"]);
    const 과제들 = 과제원.map(t => wrap(lab(t), (rw - 2 * C.padX) / (fT * 1.04)));
    const 과제h = 과제들.map(l => 줄높이(l.length, fT) + 2 * C.padY * 0.8);
    const 합 = 과제h.reduce((a, b) => a + b, 0) + Math.max(0, 과제들.length - 1) * 과제틈;
    const hl = wrap(lab(col), (lw - 2 * C.padX) / (fH * 1.04));
    const hh = Math.max(줄높이(hl.length, fH) + 2 * C.padY, 합);
    out.push(상자(C, 0, y, lw, hh, hl, 칠(C.색, 역, "머리"), fH));
    let ty = y;
    과제들.forEach((l, j) => {
      out.push(상자(C, lw + gap, ty, rw, 과제h[j], l, 칠(C.색, 역할(과제원[j], "") || (역 === "강조" ? "보조" : 역)), fT, { 굵기: 500, 왼쪽: true }));
      ty += 과제h[j] + 과제틈;
    });
    y += hh + fH * 0.6;
  });
  return [C.W, y, out.join("")];
};
// 구조 — 노드 격자 + 직선 연결(상자 가장자리에서 끊는다)
R.relation = (sp, C) => {
  const nodes = 배열(sp["노드"]), edges = 배열(sp["연결"]), f = C.f;
  const n = nodes.length;
  if (!n) return [C.W, f * 2, ""];
  const 글들 = nodes.map(nd => String(lab(nd) || ((nd && typeof nd === "object") ? nd.id : nd) || ""));
  const bwMin = Math.max(f * 4.3, Math.max(...글들.map(긴어절)) * f * 1.04) + 2 * C.padX;
  const 연결폭 = Math.max(0, ...edges.map(e => e && e["라벨"] ? 글폭(e["라벨"], C.fs) + f : 0));
  const gx = Math.max(f * 3 * C.sp, 연결폭), gy = f * 2.8 * C.sp;
  let cols = Math.max(1, Math.min(6, Math.round(유한(sp["열"])) || 3, n));
  const 폭 = c => Math.min((C.W - (c - 1) * gx) / c, f * 14);
  while (cols > 1 && 폭(cols) < bwMin) cols--;
  const bw = cols === 1 ? Math.min(C.W, Math.max(bwMin, f * 14)) : 폭(cols);
  const 줄들 = 글들.map(t => wrap(t, (bw - 2 * C.padX) / (f * 1.04)));
  const rows = Math.ceil(n / cols), pos = {};
  let bh = 줄높이(Math.max(...줄들.map(l => l.length)), f) + 2 * C.padY;
  if (C.슬) bh = Math.max(bh, Math.min(C.W / cols * 0.42 * C.sp, (C.maxH * 0.8 - (rows - 1) * gy) / rows));
  const 전체 = cols * bw + (cols - 1) * gx, x0 = (C.W - 전체) / 2;
  nodes.forEach((nd, i) => {
    const key = (nd && typeof nd === "object") ? nd.id : nd;
    pos[key] = { x: x0 + (i % cols) * (bw + gx) + bw / 2, y: Math.floor(i / cols) * (bh + gy) + bh / 2 + 2,
                 hw: bw / 2, hh: bh / 2 };
  });
  const out = [화살촉(C)];
  edges.forEach(e => {
    if (!e || typeof e !== "object") return;
    const a = pos[e.from], b = pos[e.to];
    if (!a || !b || a === b) return;
    out.push(잇기(C, a, b, { 양쪽: !!e["쌍방향"] }));
    if (e["라벨"]) {
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      out.push(`<text x="${r1(mx)}" y="${r1(my - f * 0.35)}" font-size="${r1(C.fs)}" fill="${C.색.sub}" `
             + `text-anchor="middle" paint-order="stroke" stroke="${C.색.bg}" stroke-width="3">${esc(e["라벨"])}</text>`);
    }
  });
  nodes.forEach((nd, i) => {
    const key = (nd && typeof nd === "object") ? nd.id : nd, p = pos[key];
    if (!p) return;
    out.push(상자(C, p.x - bw / 2, p.y - bh / 2, bw, bh, 줄들[i], 칠(C.색, 역할(nd)), f));
  });
  return [C.W, rows * bh + (rows - 1) * gy + 4, out.join("")];
};
/* ── 차트 ─────────────────────────────────────────────────────────
   실물 공공보고서 본문 44쪽을 눈으로 보고 뽑은 규격이다(2026-08-01, PDF 실측).
     · 격자선을 긋지 않는다 — 한 장도 없었다
     · 판을 얇은 회색 테로 두른다
     · 범례는 판 위 가운데
     · 값 라벨은 막대에 붙이고, 꺾은선은 **마지막 점에만** 붙인다
     · 꽉 찬 파이는 한 장도 없었다. 원형은 전부 **도넛**이다
     · 색은 문서 포인트색 **하나**(--fig-chart)만 쓰고 계열은 투명도로 가른다
       (32건 중 31건이 포인트색 1개 + 연한 파생. 무지개 배색은 실물에 없다)
   크기('26-09-28): 차트 하나는 전폭 낮게, 둘이 이어지면 반폭 둘을 나란히(재경부 2열 틀).
   강조 자동: 한 계열 시계열이면 마지막 시점만 진하게, 앞은 비교색(chart-mid). 최신값 글은 굵게.
   언제 쓰는가는 정본이 정한다 — data_elements.시각자료.의미구조_유형.시계열
   "5시점 초과 또는 메시지가 '추세·속도' → 선·막대그래프". 이 파일은 그리기만 한다. */
const 계열농도 = [1, 0.62, 0.38, 0.22, 0.13];
const 진하기 = i => 계열농도[i % 계열농도.length];
const 수 = n => (Math.round(n * 100) / 100).toLocaleString("ko-KR");
const 숫자냐 = v => typeof v === "number" && Number.isFinite(v);

function 눈금(최대, 최소) {
  // 사람이 읽는 눈금으로 올린다. 1·2·2.5·5 배수만 쓴다.
  const 폭 = (최대 - 최소) || Math.abs(최대) || 1;
  const 자릿수 = Math.pow(10, Math.floor(Math.log10(폭 / 4)));
  const 후보 = [1, 2, 2.5, 5, 10].map(m => m * 자릿수);
  const 간격 = 후보.find(c => 폭 / c <= 5) || 후보[후보.length - 1];
  const 위 = Math.ceil(최대 / 간격) * 간격;
  const 아래 = 최소 < 0 ? Math.floor(최소 / 간격) * 간격 : 0;
  const out = [];
  for (let v = 아래; v <= 위 + 1e-9; v += 간격) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

function 판(sp, 계열들, C, 오른여유 = 0) {
  /* 판 하나를 잡아 준다. 폭은 칸 폭(C.W), 높이는 크기 프리셋(C.차트H)이 정한다. */
  const fc = C.fc;
  const 시점 = 배열(sp["시점"]).map(t => String(t));
  // 쌓기면 축의 끝은 개별 값이 아니라 **시점별 누적합**이다.
  // 개별 값으로 잡으면 막대가 판 위로 넘쳐 범례와 겹치고 라벨이 잘려 나간다.
  // 음수는 0 아래로 따로 쌓는다(엑셀·PowerPoint 와 같다) — 양의 합과 음의 합을 둘 다 축에 넣는다.
  const 쌓합 = 양 => 시점.map((_, i) => 계열들.reduce((a, s) => {
    const v = 배열(s["값"])[i];
    return a + (숫자냐(v) && (양 ? v > 0 : v < 0) ? v : 0);
  }, 0));
  const 값전부 = sp["쌓기"]
    ? 쌓합(true).concat(쌓합(false))
    : 계열들.flatMap(s => 배열(s["값"]).filter(숫자냐));
  const ticks = 눈금(Math.max(...값전부, 0), Math.min(...값전부, 0));
  const 왼 = Math.max(fc * 2.6, Math.max(...ticks.map(t => 글폭(수(t), fc))) + fc * 0.7);
  const 위 = (계열들.length > 1 ? fc * 2 : fc * 0.8) + (sp["단위"] ? fc * 1.5 : 0);
  const 판폭 = Math.max(fc * 8, C.W - 왼 - Math.max(fc * 0.6, 오른여유));
  const 칸 = 판폭 / (시점.length || 1);
  // 시점 글이 칸보다 길면 두 줄로 접는다(겹쳐 찍히지 않게)
  const 두줄 = 시점.some(t => 글폭(t, fc) > 칸 - fc * 0.4);
  const 시점줄 = 시점.map(t => 두줄 ? wrap(t, (칸 - fc * 0.4) / (fc * 1.04)).slice(0, 2) : [t]);
  const 아래 = fc * 1.9 + (두줄 ? fc * 1.3 : 0);
  const 판높이 = Math.max(fc * 6, C.차트H - 위 - 아래);
  const y = v => 위 + 판높이 * (1 - (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0] || 1));
  return { 시점, 시점줄, ticks, 왼, 위, 판높이, 판폭, 아래, y, 칸, 값전부,
           W: C.W, H: 위 + 판높이 + 아래 };
}

function 판테(C, g) {
  // 격자선은 긋지 않는다. 테와 눈금 글자만.
  let s = `<rect x="${r1(g.왼)}" y="${r1(g.위)}" width="${r1(g.판폭)}" height="${r1(g.판높이)}" fill="none" `
        + `stroke="${C.색.frame}" stroke-width="0.8"/>`;
  g.ticks.forEach(t => {
    s += `<text x="${r1(g.왼 - C.fc * 0.4)}" y="${r1(g.y(t))}" font-size="${r1(C.fc)}" fill="${C.색.sub}" `
       + `text-anchor="end" dominant-baseline="central">${esc(수(t))}</text>`;
  });
  if (g.ticks[0] < 0) s += `<line x1="${r1(g.왼)}" y1="${r1(g.y(0))}" x2="${r1(g.왼 + g.판폭)}" `
                         + `y2="${r1(g.y(0))}" stroke="${C.색.frame}" stroke-width="0.8"/>`;
  return s;
}

function 가로칸(C, g) {
  return g.시점줄.map((줄, i) => {
    const x = g.왼 + g.칸 * (i + 0.5), y0 = g.위 + g.판높이 + C.fc * 1.25;
    return `<text x="${r1(x)}" y="${r1(y0)}" font-size="${r1(C.fc)}" fill="${C.색.sub}" text-anchor="middle">`
         + 줄.map((l, k) => `<tspan x="${r1(x)}" dy="${k ? r1(C.fc * 1.25) : 0}">${esc(l)}</tspan>`).join("")
         + `</text>`;
  }).join("");
}

function 범례(C, 계열들, 왼, 판폭, 위) {
  if (계열들.length < 2) return "";
  // 판 위 가운데 — 실물에서 예외를 못 봤다
  const fc = C.fc, 칸 = 계열들.map(s => fc * 1.1 + 글폭(s["이름"] || "", fc) + fc * 1.2);
  const 총 = 칸.reduce((a, b) => a + b, 0);
  let x = 왼 + (판폭 - 총) / 2, out = "";
  const yy = 위 - fc * 1.1;
  계열들.forEach((s, i) => {
    out += `<rect x="${r1(x)}" y="${r1(yy - fc * 0.4)}" width="${r1(fc * 0.8)}" height="${r1(fc * 0.8)}" `
         + `fill="${C.색.chart}" fill-opacity="${진하기(i)}"/>`
         + `<text x="${r1(x + fc * 1.1)}" y="${r1(yy)}" font-size="${r1(fc)}" fill="${C.색.sub}" `
         + `dominant-baseline="central">${esc(s["이름"] || "")}</text>`;
    x += 칸[i];
  });
  return out;
}

function 단위표기(C, sp, 오른끝, y) {
  if (!sp["단위"]) return "";
  // 표와 같은 규범 — 오른쪽 위 괄호
  return `<text x="${r1(오른끝)}" y="${r1(y)}" font-size="${r1(C.fc)}" fill="${C.색.sub}" `
       + `text-anchor="end">(단위: ${esc(sp["단위"])})</text>`;
}

R.bar = (sp, C) => {
  const 계열들 = 배열(sp["계열"]).filter(s => s && typeof s === "object");
  const g = 판(sp, 계열들, C), fc = C.fc;
  const 쌓기 = !!sp["쌓기"];
  const 묶음 = 쌓기 ? 1 : Math.max(계열들.length, 1);
  const 막대폭 = Math.min(fc * 3.4, (g.칸 * 0.62) / 묶음);
  // 강조 자동 — 한 계열 시계열(3시점 이상)이면 마지막 시점만 진하게, 앞은 비교색
  const 최신만 = 계열들.length === 1 && !쌓기 && g.시점.length >= 3;
  const out = [판테(C, g), 범례(C, 계열들, g.왼, g.판폭, g.위),
               단위표기(C, sp, g.왼 + g.판폭, g.위 - (계열들.length > 1 ? fc * 2.1 : fc * 0.5)), 가로칸(C, g)];
  const 끝 = g.시점.length - 1;
  g.시점.forEach((_, i) => {
    const 가운데 = g.왼 + g.칸 * (i + 0.5);
    let 쌓양 = 0, 쌓음 = 0;
    계열들.forEach((s, k) => {
      const v = 배열(s["값"])[i];
      if (!숫자냐(v)) return;
      const 쌓인 = v < 0 ? 쌓음 : 쌓양;              // 음수는 0 아래 제 더미에 쌓는다
      const x = 쌓기 ? 가운데 - 막대폭 / 2 : 가운데 - (묶음 * 막대폭) / 2 + k * 막대폭;
      const y0 = 쌓기 ? g.y(쌓인 + v) : g.y(Math.max(v, 0));
      const h = Math.abs(g.y(쌓기 ? 쌓인 : 0) - g.y(쌓기 ? 쌓인 + v : v));
      const 칠색 = 최신만 && i !== 끝 ? C.색["chart-mid"] : C.색.chart;
      out.push(`<rect x="${r1(x)}" y="${r1(y0)}" width="${r1(막대폭)}" height="${r1(h)}" `
             + `fill="${칠색}" fill-opacity="${최신만 ? 1 : 진하기(k)}"/>`);
      // 값 라벨은 막대에 붙인다 — 실물 규격. 글자가 막대 자리보다 넓으면 붙이지 않는다
      // (글자를 하한 밑으로 줄이지 않는다 — 값은 왼쪽 눈금이 이미 말해 준다).
      // 쓸 수 있는 자리: 계열이 하나면 칸 전체, 묶음이면 제 막대 폭만큼만.
      const 글자 = 수(v);
      const 자리 = (묶음 === 1 && !쌓기) ? g.칸 * 0.92 : 막대폭 + 3;
      if (글폭(글자, fc) <= 자리) {
        // 쌓기면 칸 안 가운데. 음수면 막대 아래인데, 판 바닥에 닿으면 x축 글자와
        // 겹치므로 그때는 막대 안쪽에 넣는다.
        const 바닥 = g.위 + g.판높이;
        const ly = 쌓기 ? (y0 + h / 2)
                 : v < 0 ? (y0 + h + fc * 1.05 > 바닥 - 2 ? y0 + h - fc * 0.4 : y0 + h + fc * 1.05)
                 : y0 - fc * 0.35;
        // 흰 글자는 배경이 충분히 진할 때만 — 0.62 농도에 흰 글자는 안 읽힌다
        const 흰 = (쌓기 || (v < 0 && ly < y0 + h)) && 진하기(k) >= 0.85;
        const 굵게 = i === 끝 && !쌓기;                  // 최신값 — 흑백에서도 보이게 굵게
        out.push(`<text x="${r1(x + 막대폭 / 2)}" y="${r1(ly)}" font-size="${r1(fc)}" `
               + `fill="${흰 ? C.색["on-accent"] : C.색.ink}" text-anchor="middle"`
               + `${굵게 ? ' font-weight="700"' : ""}`
               + `${쌓기 ? ' dominant-baseline="central"' : ""}>${esc(글자)}</text>`);
      }
      if (v < 0) 쌓음 += v; else 쌓양 += v;
    });
  });
  return [g.W, g.H, out.join("")];
};

R.hbar = (sp, C) => {
  /* 가로 막대 — 항목 이름이 길 때. 세로 막대는 이름이 길면 x축에서 겹친다.
     근거: 범정부오피스 서식 도구에 '가로막대'가 5색 변형으로 들어 있다
     (research/corpus/bumpiece-extraction/features-inventory.md 차트 14종).
     실무자에게 주어지는 도구에 있다는 것은 쓰인다는 뜻이다. */
  // 이름 칸은 잰 글 폭으로 잡고, 넓으면 두세 줄로 접는다(고정 여백이던 때는 긴 이름 앞 글자가
  // viewBox 밖으로 잘렸다 — 실측 2/40). 값은 막대 끝 바깥에 둔다.
  const 계열들 = 배열(sp["계열"]).filter(s => s && typeof s === "object"), fc = C.fc;
  const 이름들 = 배열(sp["시점"]).map(t => String(t));
  const 값전부 = 계열들.flatMap(s => 배열(s["값"]).filter(숫자냐));
  const ticks = 눈금(Math.max(...값전부, 0), Math.min(...값전부, 0));
  const 이름칸최대 = C.W * 0.4;
  const 이름줄 = 이름들.map(t => 글폭(t, fc) + fc * 0.8 <= 이름칸최대 ? [t]
                                  : wrap(t, (이름칸최대 - fc * 0.8) / (fc * 1.04)).slice(0, 3));
  const 왼 = Math.max(fc * 3, Math.max(0, ...이름줄.flat().map(t => 글폭(t, fc))) + fc * 0.8);
  // 단위 표기 자리를 위에 비워 둔다 — 안 비우면 판 밖으로 나가 잘린다
  const 위 = (계열들.length > 1 ? fc * 2 : fc * 0.5) + (sp["단위"] ? fc * 1.5 : 0);
  const 묶음 = 계열들.length || 1;
  const 최대줄 = Math.max(1, ...이름줄.map(l => l.length));
  const 줄간 = Math.max(fc * 1.3 * 최대줄 + fc * 0.8, 묶음 * fc * 1.2 + fc * 0.9);
  const 끝여유 = fc * 0.6 + Math.max(0, ...값전부.map(v => 글폭(수(v), fc)));
  const 판폭 = Math.max(fc * 8, C.W - 왼 - 끝여유), 판높이 = 이름들.length * 줄간;
  const x = v => 왼 + 판폭 * (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0] || 1);
  const out = [`<rect x="${r1(왼)}" y="${r1(위)}" width="${r1(판폭)}" height="${r1(판높이)}" fill="none" `
             + `stroke="${C.색.frame}" stroke-width="0.8"/>`,
               단위표기(C, sp, 왼 + 판폭, 위 - (계열들.length > 1 ? fc * 2.1 : fc * 0.4)),
               범례(C, 계열들, 왼, 판폭, 위)];
  ticks.forEach(t => out.push(
    `<text x="${r1(x(t))}" y="${r1(위 + 판높이 + fc * 1.25)}" font-size="${r1(fc)}" fill="${C.색.sub}" `
    + `text-anchor="middle">${esc(수(t))}</text>`));
  이름들.forEach((_, i) => {
    const 가운데 = 위 + 줄간 * (i + 0.5);
    out.push(`<text x="${r1(왼 - fc * 0.5)}" y="${r1(가운데)}" font-size="${r1(fc)}" fill="${C.색.ink}" `
           + `text-anchor="end" dominant-baseline="central">`
           + 이름줄[i].map((l, k) => `<tspan x="${r1(왼 - fc * 0.5)}" y="${r1(가운데 + (k - (이름줄[i].length - 1) / 2) * fc * 1.3)}">${esc(l)}</tspan>`).join("")
           + `</text>`);
    const 막대두께 = Math.min(fc * 1.6, (줄간 * 0.62) / 묶음);
    계열들.forEach((s, k) => {
      const v = 배열(s["값"])[i];
      if (!숫자냐(v)) return;
      const y0 = 가운데 - (묶음 * 막대두께) / 2 + k * 막대두께;
      const x0 = x(Math.min(v, 0)), 길이 = Math.abs(x(v) - x(0));
      out.push(`<rect x="${r1(x0)}" y="${r1(y0)}" width="${r1(길이)}" height="${r1(막대두께)}" `
             + `fill="${C.색.chart}" fill-opacity="${진하기(k)}"/>`);
      // 음수 막대가 판 왼쪽 끝까지 뻗으면 라벨이 판 밖으로 나가 항목 이름과 겹친다 —
      // 그때는 막대 안쪽에 넣는다.
      const 글자폭 = 글폭(수(v), fc);
      const 밖 = v < 0 ? x0 - fc * 0.4 - 글자폭 < 왼 + 2 : false;
      const lx = 밖 ? x0 + fc * 0.4 : (v < 0 ? x0 - fc * 0.4 : x0 + 길이 + fc * 0.4);
      out.push(`<text x="${r1(lx)}" y="${r1(y0 + 막대두께 / 2)}" font-size="${r1(fc)}" `
             + `fill="${밖 && 진하기(k) >= 0.85 ? C.색["on-accent"] : C.색.ink}" dominant-baseline="central" `
             + `text-anchor="${밖 ? "start" : v < 0 ? "end" : "start"}">${esc(수(v))}</text>`);
    });
  });
  return [C.W, 위 + 판높이 + fc * 1.9, out.join("")];
};

R.line = (sp, C) => {
  const 계열들 = 배열(sp["계열"]).filter(s => s && typeof s === "object"), fc = C.fc;
  const 끝값폭 = Math.max(0, ...계열들.map(s => {
    const v = 배열(s["값"]).filter(숫자냐).pop();
    return v === undefined ? 0 : 글폭(수(v), fc) + fc * 0.7;
  }));
  const g = 판(sp, 계열들, C, 끝값폭);
  const x = i => g.왼 + g.칸 * (i + 0.5);
  const out = [판테(C, g), 범례(C, 계열들, g.왼, g.판폭, g.위),
               단위표기(C, sp, g.왼 + g.판폭, g.위 - (계열들.length > 1 ? fc * 2.1 : fc * 0.5)), 가로칸(C, g)];
  const 끝라벨 = [];      // 끝값이 서로 가까우면 겹친다 — 다 그린 뒤 밀어낸다
  계열들.forEach((s, k) => {
    const 값 = 배열(s["값"]);
    const 점 = 값.map((v, i) => 숫자냐(v) ? [x(i), g.y(v)] : null).filter(Boolean);
    if (!점.length) return;
    out.push(`<polyline points="${점.map(([a, b]) => `${r1(a)},${r1(b)}`).join(" ")}" `
           + `fill="none" stroke="${C.색.chart}" stroke-opacity="${진하기(k)}" stroke-width="${r1(fc * 0.16)}"`
           + `${k >= 2 ? ' stroke-dasharray="5 3"' : ""}/>`);
    점.forEach(([a, b], j) => out.push(`<circle cx="${r1(a)}" cy="${r1(b)}" r="${r1(fc * (j === 점.length - 1 ? 0.3 : 0.21))}" `
                                     + `fill="${C.색.chart}" fill-opacity="${진하기(k)}"/>`));
    // 값 라벨은 마지막 점에만 — 실물 규격. 최신값이라 굵게(강조 자동)
    const 끝 = 점[점.length - 1], 끝값 = 값.filter(숫자냐).pop();
    끝라벨.push({ x: 끝[0] + fc * 0.5, y: 끝[1] - fc * 0.5, 글: 수(끝값) });
  });
  // 두 계열의 끝값이 붙어 있으면 글자가 겹친다. 위아래로 벌린다.
  끝라벨.sort((a, b) => a.y - b.y);
  for (let i = 1; i < 끝라벨.length; i++) {
    if (끝라벨[i].y - 끝라벨[i - 1].y < fc * 1.15) 끝라벨[i].y = 끝라벨[i - 1].y + fc * 1.15;
  }
  끝라벨.forEach(l => out.push(
    `<text x="${r1(l.x)}" y="${r1(Math.max(l.y, fc))}" font-size="${r1(fc)}" font-weight="700" `
    + `fill="${C.색.ink}">${esc(l.글)}</text>`));
  return [g.W, g.H, out.join("")];
};

R.donut = (sp, C) => {
  // 값은 스택과 같이 유한수로 받는다 — 글자 "3" 이 오면 합계가 "035" 로 이어 붙었다
  const fc = C.fc;
  const 항목 = 배열(sp["항목"]).map(it => Array.isArray(it) ? it : [it && it["이름"], it && it["값"]])
                              .map(([이름, v]) => [String(이름 ?? ""), 유한(v)]);
  const 총 = 항목.reduce((a, [, v]) => a + v, 0) || 1;
  const 범례글 = 항목.map(([이름, v]) => `${이름} ${수(v)} (${(v / 총 * 100).toFixed(1)}%)`);
  const 범례폭 = fc * 1.4 + Math.max(0, ...범례글.map(t => 글폭(t, fc)));
  const 범례높 = 항목.length * fc * 1.8;
  let R0 = Math.max(fc * 3, Math.min(C.차트H / 2 - 4, C.W * 0.22));
  const 옆 = 2 * R0 + fc * 2 + 범례폭 <= C.W;         // 범례 자리가 없으면 아래로(잘리지 않게)
  if (!옆) R0 = Math.max(fc * 3, Math.min(R0, C.W / 2 - 4));
  const R1 = R0 * 0.6;                                // 안쪽을 비운다 — 파이는 쓰지 않는다
  const 전체 = 옆 ? 2 * R0 + fc * 2 + 범례폭 : 2 * R0;
  const cx = (C.W - 전체) / 2 + R0, cy = Math.max(R0, 옆 ? 범례높 / 2 : 0) + 2;
  const out = [];
  let 각 = -Math.PI / 2;
  항목.forEach(([, v], k) => {
    const 폭 = 2 * Math.PI * Math.max(0, v) / 총, 끝 = 각 + 폭;
    const 큰 = 폭 > Math.PI ? 1 : 0;
    const p = (rr, a) => `${r1(cx + rr * Math.cos(a))},${r1(cy + rr * Math.sin(a))}`;
    out.push(`<path d="M ${p(R0, 각)} A ${r1(R0)} ${r1(R0)} 0 ${큰} 1 ${p(R0, 끝)} `
           + `L ${p(R1, 끝)} A ${r1(R1)} ${r1(R1)} 0 ${큰} 0 ${p(R1, 각)} Z" `
           + `fill="${C.색.chart}" fill-opacity="${진하기(k)}" stroke="${C.색.bg}" stroke-width="1.2"/>`);
    각 = 끝;
  });
  if (sp["가운데"]) {
    const 줄 = wrap(sp["가운데"], (R1 * 1.7) / (fc * 1.1 * 1.04));
    out.push(`<text x="${r1(cx)}" y="${r1(cy)}" font-size="${r1(fc * 1.1)}" font-weight="700" fill="${C.색.ink}" `
           + `text-anchor="middle" dominant-baseline="central">` + tspans(줄, cx, cy, fc * 1.1) + `</text>`);
  }
  // 범례는 오른쪽(자리가 없으면 아래)에 값·비율과 함께 — 도넛은 조각에 글자를 넣으면 겹친다
  const lx = 옆 ? cx + R0 + fc * 2 : (C.W - 범례폭) / 2;
  const ly0 = 옆 ? cy - (항목.length - 1) * fc * 0.9 : cy + R0 + fc * 1.6;
  항목.forEach(([이름, v], k) => {
    const y = ly0 + k * fc * 1.8;
    out.push(`<rect x="${r1(lx)}" y="${r1(y - fc * 0.45)}" width="${r1(fc * 0.9)}" height="${r1(fc * 0.9)}" `
           + `fill="${C.색.chart}" fill-opacity="${진하기(k)}"/>`
           + `<text x="${r1(lx + fc * 1.4)}" y="${r1(y)}" font-size="${r1(fc)}" fill="${C.색.ink}" `
           + `dominant-baseline="central">${esc(이름)} ${esc(수(v))}`
           + `<tspan fill="${C.색.sub}"> (${(v / 총 * 100).toFixed(1)}%)</tspan></text>`);
  });
  const H = 옆 ? Math.max(2 * R0, 범례높) + 4 : 2 * R0 + fc * 1.6 + 범례높 + 4;
  return [C.W, H, out.join("")];
};

// 구성비 쌓은 막대 — 세트마다 막대 하나. 조각이 얇으면 이름은 막대 옆에 쓴다.
// 값은 유한한 숫자로만 쓴다('26-09-28 보안 — 값을 이스케이프 없이 글자로 넣어 도식 데이터의
// '<img onerror>' 가 편집기·웹앱에서 실행됐다). 합계·높이·글자가 같은 숫자를 쓴다.
R.stack = (sp, C) => {
  const sets = 배열(sp["세트"]).filter(s => s && typeof s === "object"), fc = C.fc;
  const n = sets.length;
  if (!n) return [C.W, fc * 2, ""];
  const 글들 = sets.map(st => 배열(st["항목"]).map(it => {
    const [name, v] = Array.isArray(it) ? it : [it && it["이름"], it && it["값"]];
    return [String(name ?? ""), 유한(v)];
  }));
  const 옆글폭 = Math.max(0, ...글들.flat().map(([nm, v]) => 글폭(`${nm} ${수(v)}%`, fc))) + fc * 0.6;
  const bw = Math.min(fc * 7, C.W * 0.16);
  const gap = Math.max(fc * 4, 옆글폭 + fc * 1.2);
  const 전체 = n * bw + (n - 1) * gap + 옆글폭;
  const x0 = Math.max(0, (C.W - 전체) / 2);
  const Hbar = Math.max(fc * 8, C.차트H - fc * 2.6);
  const out = n > 1 ? [화살촉(C)] : [];
  sets.forEach((st, si) => {
    const x = x0 + si * (bw + gap);
    const items = 글들[si];
    const total = items.reduce((a, [, v]) => a + Math.max(0, v), 0) || 100;
    const 강조 = typeof st["강조"] === "string" ? st["강조"] : null;
    let y = 2;
    items.forEach(([name, v], k) => {
      const h = Hbar * Math.max(0, v) / total, acc = 강조 !== null && 강조 === name;
      const 농도 = acc ? 1 : (강조 !== null ? [0.45, 0.28, 0.16, 0.1][k % 4] : 진하기(k));
      out.push(`<rect x="${r1(x)}" y="${r1(y)}" width="${r1(bw)}" height="${r1(h)}" `
             + `fill="${C.색.chart}" fill-opacity="${농도}" stroke="${C.색.bg}" stroke-width="1"/>`);
      const 글 = `${name} ${수(v)}%`, 안 = h >= fc * 1.4 && 글폭(글, fc) <= bw - fc * 0.4;
      const tx = 안 ? x + bw / 2 : x + bw + fc * 0.4;
      out.push(`<text x="${r1(tx)}" y="${r1(y + h / 2)}" font-size="${r1(fc)}" font-weight="${acc ? 700 : 500}" `
             + `fill="${안 && 농도 >= 0.6 ? C.색["on-accent"] : C.색.ink}" text-anchor="${안 ? "middle" : "start"}" `
             + `dominant-baseline="central">${esc(글)}</text>`);
      y += h;
    });
    out.push(`<text x="${r1(x + bw / 2)}" y="${r1(Hbar + 2 + fc * 1.5)}" font-size="${r1(fc)}" font-weight="700" `
           + `fill="${C.색.ink}" text-anchor="middle">${esc(st["이름"] || "")}</text>`);
    if (si < n - 1) out.push(선(C, x + bw + 옆글폭, Hbar / 2, x + bw + gap - fc * 0.4, Hbar / 2));
  });
  return [C.W, Hbar + 2 + fc * 2.2, out.join("")];
};

// ── 격자 도식 — HTML <table> 칸으로 짓는다('26-09-29 재설계 P2, 사장님 판정 ②) ─────────────
// 재경부 보고서 도식은 대부분 표 칸을 합치고 칠해서 만든다(표 932개 대 도형 약 180개, moef_figs §3-2).
// 그래서 A4 의 체계도(strategy)·흐름띠(process)와 새 비교판(compare)은 SVG 가 아니라 <table> 로 그린다 —
// 화면읽기가 칸·병합·칠·글을 그대로 읽어 HWPX 에서 한글 네이티브 표가 되고, 한글에서 칸·색·글을 고칠 수
// 있다. **스펙은 그대로다**(새 키는 비교판의 전[]·후[]뿐, 머리[] 는 없어도 된다) — 약한 모델이 이미 내는
// strategy·process 를 격자로 그린다(critic_impl #6). 옛 슬라이드(.sl-page)의 체계도·절차는 SVG 그대로다.
// 규칙(critic_impl #5 · critic_design #4·#20):
//   · 칸 하나에 부품 하나 — HWPX 칸은 서식 한 벌이라 머리와 항목을 한 칸에 섞지 않는다. 표 안 표 없음
//   · 카드 사이 틈은 빈 칸 열·행(border-spacing 은 HWPX 수확기가 모른다). ▼·⇨ 는 실제 글자(CSS 삼각형 없음)
//   · 진한 채움은 왼쪽 라벨 한 열로 끝. 머리는 중간 파스텔 + 검정 굵은 글, 몸통은 옅은 파스텔
//   · 글자는 역할별 pt 고정(자리짓기: 흐름 11 · 체계 13, 크기 3단) — 칸 폭은 % 라 배율이 늘 1
// 속성·style 에 들어가는 값은 토큰 hex(토큰읽기가 #RRGGBB 만 받는다)·유한수(r1·정수)·고정 낱말뿐이고,
// 스펙 글자는 esc() 를 거쳐 칸 안 글로만 들어간다. 편집기 라벨 자리는 data-gi(정수 = figSetters 차례).
const G = {};
const 정수 = v => Math.max(0, Math.floor(유한(v)));
// 칸 하나. 칠값 = 칠() 결과(없으면 무채움). 변 = 테두리를 그을 변 't r b l' 글자 모음(고정 낱말).
function 칸(C, 글, o = {}) {
  const 칠값 = o.칠 || null, f = o.f || C.f;
  const 굵기 = o.굵기 || (칠값 ? 칠값.bold : 400);
  const st = [`font-size:${r1(f / PT)}pt`, "line-height:1.3",
              `padding:${r1(o.padY ?? C.padY)}px ${r1(o.padX ?? C.padX)}px`,
              `text-align:${o.왼쪽 ? "left" : "center"}`, "vertical-align:middle",
              `font-weight:${굵기 === 700 ? 700 : 굵기 === 500 ? 500 : 400}`,
              `color:${o.글색 || (칠값 ? 칠값.text : C.색.ink)}`];
  if (칠값) st.push(`background:${칠값.fill}`);
  const 변 = typeof o.변 === "string" ? o.변 : (칠값 ? "trbl" : "");
  const 선 = `0.2mm solid ${C.색.frame}`, 속선 = `0.2mm solid ${C.색.mid}`;
  [["t", "top"], ["r", "right"], ["b", "bottom"], ["l", "left"]].forEach(([k, s]) =>
    st.push(`border-${s}:${변.includes(k) ? 선 : (o.속 || "").includes(k) ? 속선 : "none"}`));
  const 병 = (o.cs > 1 ? ` colspan="${정수(o.cs)}"` : "") + (o.rs > 1 ? ` rowspan="${정수(o.rs)}"` : "");
  const gi = Number.isInteger(o.gi) ? ` data-gi="${o.gi}"` : "";
  return `<td${병}${gi} style="${st.join(";")}">${esc(String(글 ?? "")).replace(/\n/g, "<br>")}</td>`;
}
// 틈 칸 — 무채움·무테두리. 높이를 주면 그 높이의 틈 행이 된다
const 틈칸 = (o = {}) => `<td${o.cs > 1 ? ` colspan="${정수(o.cs)}"` : ""}${o.rs > 1 ? ` rowspan="${정수(o.rs)}"` : ""}`
  + ` style="padding:0;border:none${o.h ? `;height:${r1(o.h)}px` : ""}"></td>`;
function 격자표(C, spec, 폭들, 행들) {
  const 합 = 폭들.reduce((a, b) => a + b, 0) || 1;
  const title = esc(spec["대체텍스트"] || spec["캡션"] || spec.type);
  return `<table class="fig-grid" role="table" aria-label="${title}" style="width:100%;border-collapse:collapse;`
       + `table-layout:fixed;margin:0 auto;font-family:Pretendard, sans-serif;word-break:keep-all;`
       + `overflow-wrap:anywhere;color:${C.색.ink};background:none">`
       + `<colgroup>${폭들.map(p => `<col style="width:${r1(p / 합 * 100)}%">`).join("")}</colgroup><tbody>`
       + 행들.map(r => `<tr>${r}</tr>`).join("") + `</tbody></table>`;
}
const 흰칠 = C => ({ fill: C.색.bg, text: C.색.ink, bold: 400 });
// 카드 몸 칸의 변 — 카드 하나(같은 열의 몸 칸들)는 바깥 네 변만 긋고 안쪽은 옅은 선으로 가른다
const 몸변 = (j, 끝) => "lr" + (j === 0 ? "t" : "") + (j === 끝 ? "b" : "");
const 몸속 = (j, 끝) => (j < 끝 ? "b" : "");

// 체계도 — [라벨 열 | 틈 | 카드 열 × n]. 목표 띠 → ▼ → 전략 머리 → 과제 몸(카드).
// 전략이 4개를 넘거나 칸이 좁으면 줄 배치(전략 하나가 한 줄: 머리 | 과제들)
// 글자('26-09-29 판정 ⑥): 보통 = 머리·과제 13pt · 목표 14pt(과제도 체계도 13 — 예전 과제 12 라 중앙이 12 였다).
// 과제 색('26-09-29 판정 ④): 과제 원소가 제 역할(색 = 강조·회색)을 가지면 그 칸 하나만 칠한다(열 색보다 앞선다).
// 쪽 나눔('26-09-29 판정 ⑧): C.범위 = [a, b] 이면 그 단위(열 배치 = 과제 줄, 줄 배치 = 과제 칸)만 그린다 —
//   이어지는 조각은 목표 띠를 다시 안 그리고, 열 배치는 전략 머리 줄을 되풀이한다(머리 반복, 라벨 자리 없음).
// 한 쪽('26-09-29 판정 ⑥): C.과제덧(px) 만큼 과제 칸 위아래 여백을 늘린다(높이맞추기가 '크게'·칸 많음일 때 준다).
const 범위풀기 = (C, N) => {
  if (!Array.isArray(C.범위)) return [0, N];
  const a = Math.min(N, 정수(C.범위[0])), b = Math.max(a, Math.min(N, 정수(C.범위[1])));
  return [a, b];
};
function 체계틀(sp, C) {
  const cols = 배열(sp["전략"]), n = cols.length;
  const fG = C.f + (C.크기 === "크게" ? 4 : 1) * PT, fH = C.f, fT = fH;
  const L = Math.min(Math.max(글폭("과제", fH) + 2 * C.padX + 4, C.W * 0.085), C.W * 0.16);
  const g0 = Math.max(C.W * 0.012, 3) * C.sp;              // 라벨 열과 카드 사이 틈
  const gap = Math.max(C.W * 0.018, fH * 0.45) * C.sp;     // 카드 사이 틈
  const 과제원 = cols.map(c => 배열(c && c["과제"]));
  const 과제들 = 과제원.map(a => a.map(lab));
  const 모두 = cols.flatMap((c, i) => [lab(c), ...과제들[i]]);
  const cwMin = Math.max(fH * 5.5, Math.max(0, ...모두.map(긴어절)) * fH * 1.04) + 2 * C.padX;
  const Wc = C.W - L - g0;
  const cw = n ? (Wc - (n - 1) * gap) / n : 0;
  const kmax = Math.max(0, ...과제들.map(a => a.length));
  const 열배치 = n > 0 && n <= 4 && cw >= cwMin;
  const 줄수 = 과제들.map(a => Math.max(1, a.length));
  const 단위 = !n ? 0 : 열배치 ? kmax : 줄수.reduce((a, b) => a + b, 0);
  return { cols, n, fG, fH, fT, L, g0, gap, 과제원, 과제들, cwMin, Wc, cw, kmax, 열배치, 줄수, 단위 };
}
G.strategy = (sp, C) => {
  const T = 체계틀(sp, C);
  const { cols, n, fG, fH, fT, L, g0, gap, 과제원, 과제들, Wc, cw, kmax, 줄수 } = T;
  const 목표 = lab(sp["목표"]);
  const 라벨 = (t, o = {}) => 칸(C, t, { 칠: 칠(C.색, "라벨"), f: fH, 굵기: 700, ...o });
  let gi = 0;
  const 목표gi = gi++;
  const 머리gi = [], 과제gi = [];
  cols.forEach((c, i) => { 머리gi.push(gi++); 과제gi.push(과제들[i].map(() => gi++)); });
  const 행들 = [];
  const 목표칸 = (cs) => 칸(C, 목표, { 칠: 칠(C.색, "보조"), f: fG, 굵기: 700, cs, gi: 목표gi });
  const 화살행 = (cs) => 틈칸() + 틈칸() + 칸(C, "▼", { f: fH, 글색: C.색.line, cs, padY: fH * 0.15 });
  if (!n) {
    행들.push(라벨("목표") + 틈칸() + 목표칸(1));
    return 격자표(C, sp, [L, g0, Wc], 행들);
  }
  const 덧 = Math.max(0, 유한(C.과제덧)) / 2;
  // 과제 칸 칠 — 제 역할(강조·회색·분야)이 있으면 그 칸만, 없으면 열(전략) 몸 색
  const 과제칠 = (i, j, 몸) => {
    const 과역 = j < 과제원[i].length ? 역할(과제원[i][j], "") : "";
    return 과역 ? { ...칠(C.색, 과역), bold: 과역 === "강조" ? 700 : 400 } : { ...몸, bold: 400 };
  };
  const [a, b] = 범위풀기(C, T.단위);
  if (T.열배치) {
    const 폭들 = [L, g0];
    cols.forEach((_, i) => { if (i) 폭들.push(gap); 폭들.push(cw); });
    const 안 = 2 * n - 1;
    if (a === 0) {
      행들.push(라벨("목표") + 틈칸() + 목표칸(안));
      행들.push(화살행(안));
    }
    // 이어지는 조각(a > 0)은 머리 줄을 되풀이한다 — 편집기 라벨 자리(data-gi)는 첫 조각 머리에만 둔다
    행들.push(라벨("전략") + 틈칸() + cols.map((c, i) => (i ? 틈칸() : "")
      + 칸(C, lab(c), { 칠: 칠(C.색, 역할(c), "머리"), f: fH, 굵기: 700, gi: a === 0 ? 머리gi[i] : undefined })).join(""));
    const m = b - a;
    for (let j = a; j < b; j++) {
      행들.push((j === a ? 라벨("과제", { rs: m }) : "") + 틈칸() + cols.map((c, i) => {
        const 역 = 역할(c), 몸 = 칠(C.색, 역 === "강조" ? "보조" : 역);
        const 있음 = j < 과제들[i].length;
        return (i ? 틈칸() : "") + 칸(C, 있음 ? 과제들[i][j] : "", {
          칠: 과제칠(i, j, 몸), f: fT, 왼쪽: true, 변: 몸변(j - a, m - 1), 속: 몸속(j - a, m - 1),
          padY: C.padY + 덧, gi: 있음 ? 과제gi[i][j] : undefined });
      }).join(""));
    }
    return 격자표(C, sp, 폭들, 행들);
  }
  // 줄 배치 — [라벨 | 틈 | 머리 | 틈 | 과제]. 전략 사이에 얇은 틈 행. 단위 = 과제 칸(전략 i 의 j 번째)
  const lw = Math.max(T.cwMin, (Wc - gap) * 0.3), rw = Wc - gap - lw;
  const U = [];
  cols.forEach((_, i) => { for (let j = 0; j < 줄수[i]; j++) U.push([i, j]); });
  const 조 = U.slice(a, b);
  const 틈수 = 조.filter((u, t) => t > 0 && 조[t - 1][0] !== u[0]).length;
  const 전체 = 조.length + 틈수;
  if (a === 0) {
    행들.push(라벨("목표") + 틈칸() + 목표칸(3));
    행들.push(화살행(3));
  }
  조.forEach(([i, j], t) => {
    if (t > 0 && 조[t - 1][0] !== i) 행들.push(틈칸() + 틈칸({ cs: 3, h: fH * 0.5 * C.sp }));
    const 내것 = 조.filter(u => u[0] === i), 첫j = 내것[0][1], k = 내것.length;
    const c = cols[i], 역 = 역할(c), 몸 = 칠(C.색, 역 === "강조" ? "보조" : 역);
    const 있음 = j < 과제들[i].length;
    // 머리 칸은 그 전략이 이 조각에서 처음 나오는 줄에 — 쪼개진 전략의 이어지는 머리는 되풀이(라벨 자리 없음)
    행들.push((t === 0 ? 라벨("전략", { rs: 전체 }) : "") + 틈칸()
      + (j === 첫j ? 칸(C, lab(c), { 칠: 칠(C.색, 역, "머리"), f: fH, 굵기: 700, rs: k,
                                     gi: 첫j === 0 ? 머리gi[i] : undefined }) + 틈칸({ rs: k }) : "")
      + 칸(C, 있음 ? 과제들[i][j] : "", { 칠: 과제칠(i, j, 몸), f: fT, 왼쪽: true,
            변: 몸변(j - 첫j, k - 1), 속: 몸속(j - 첫j, k - 1), padY: C.padY + 덧,
            gi: 있음 ? 과제gi[i][j] : undefined }));
  });
  return 격자표(C, sp, [L, g0, lw, gap, rw], 행들);
};
// 쪽 나눔 단위 수 — 높이맞추기·조판기(assemble_full paginate)가 조각을 지을 때 쓴다
G.strategy.단위 = (sp, C) => 체계틀(sp, C).단위;
// '크게' 한 쪽(판정 ⑥) — 칸이 많을 때만(과제 합 9개 이상 또는 전략+과제 12칸 이상, critic_design 1-2 문턱).
// 적은 내용을 한 쪽에 늘이면 빈 체계도가 된다(critic_design 1-2 — 글 면적 20% 미만)
G.strategy.한쪽 = sp => {
  const cols = 배열(sp["전략"]);
  const 과제합 = cols.reduce((s, c) => s + 배열(c && c["과제"]).length, 0);
  return 과제합 >= 9 || cols.length + 과제합 >= 12;
};
G.strategy.과제줄 = (sp, C) => { const T = 체계틀(sp, C); return T.열배치 ? T.kmax : T.단위; };

// 흐름띠 — 단계 칸 + ⇨ 칸. 한 줄 → 2줄 뱀(한 줄 3칸 이상일 때만, ⇩·⇦) → 세로 목록형(번호 칩 + ▼)
G.process = (sp, C) => {
  const steps = 배열(sp["단계"]), n = steps.length, f = C.f;
  const 항목들 = steps.map(st => ({
    글: lab(st), 역: 역할(st),
    주체: st && typeof st === "object" && st["주체"] ? String(st["주체"]) : "",
    전이: st && typeof st === "object" && st["전이"] ? String(st["전이"]) : "" }));
  if (!n) return 격자표(C, sp, [1], [틈칸()]);
  const 작은 = (t, o = {}) => 칸(C, t, { f: C.fs, 글색: C.색.sub, padY: C.fs * 0.15, padX: C.fs * 0.2, ...o });
  const 단계칸 = (i, o = {}) => 칸(C, 항목들[i].글, { 칠: 칠(C.색, 항목들[i].역), f, 굵기: 700, gi: i, ...o });
  const 전이폭 = Math.max(0, ...항목들.map(it => it.전이 ? Math.max(...wrap(it.전이, 6).map(l => 글폭(l, C.fs))) : 0));
  const aw = Math.max(f * 1.9, 전이폭 + C.fs * 0.6) * (C.sp < 1 ? 0.9 : 1);
  const bwMin = Math.max(f * 4.3, Math.max(...항목들.map(it => 긴어절(it.글))) * f * 1.04) + 2 * C.padX;
  const 칸폭 = k => (C.W - (k - 1) * aw) / k;
  const 주체있음 = 항목들.some(it => it.주체);
  let k = n, 줄 = 1;
  if (n > 1 && 칸폭(n) < bwMin) {
    k = Math.ceil(n / 2); 줄 = 2;
    if (k < 3 || 칸폭(k) < bwMin) k = 0;               // 세로 목록형
  }
  if (Array.isArray(C.범위)) k = 0;                     // 쪽 나눔 조각(판정 ⑧)은 늘 세로 목록형 — 단계 단위로 끊는다
  if (k) {
    const bw = 칸폭(k), 폭들 = [];
    for (let c = 0; c < k; c++) { if (c) 폭들.push(aw); 폭들.push(bw); }
    // 화살 칸은 글자 하나(⇨·⇦·⇩)만 — 전이 글은 그 위 행의 같은 열에 따로 둔다(칸 하나 = 서식 하나)
    const 화살 = 글자 => 칸(C, 글자, { f: f * 1.3, 글색: C.색.line, 굵기: 700, padX: 0, padY: 0 });
    const 행들 = [];
    // 한 줄 몫: 칸 자리 c 에 단계 idx(c) (없으면 null), 화살 m 은 단계 from(m) → 다음
    const 줄짓기 = (idx, 화살글자, from) => {
      let t = "", r = "", u = "", 전이있음 = false;
      for (let c = 0; c < k; c++) {
        if (c) {
          const s = from(c - 1);
          r += s !== null ? 화살(화살글자) : 틈칸();
          if (s !== null && 항목들[s].전이) { t += 작은(항목들[s].전이, { padY: 0 }); 전이있음 = true; } else t += 틈칸();
          u += 틈칸();
        }
        const i = idx(c);
        t += 틈칸();
        r += i !== null ? 단계칸(i) : 틈칸();
        // 주체 행은 자리가 주체를 말한다 — '* ' 는 재경부 문서에서 주석·출처 표지라 격자에선 뺀다(적대 검토 L7)
        u += i !== null && 항목들[i].주체 ? 작은(String(항목들[i].주체)) : 틈칸();
      }
      if (전이있음) 행들.push(t);
      행들.push(r);
      if (주체있음) 행들.push(u);
    };
    const 첫 = c => (c < n ? c : null);
    줄짓기(첫, "⇨", m => (m + 1 < k && m + 1 < n ? m : null));
    if (줄 === 2) {
      // 줄을 내려간다 — 끝 칸 아래 ⇩, 끝 단계의 전이 글은 그 왼쪽 열에
      let d = "";
      for (let c = 0; c < k; c++) {
        if (c) d += c === k - 1 && 항목들[k - 1].전이 ? 작은(항목들[k - 1].전이, { padY: 0 }) : 틈칸();
        d += c === k - 1 ? 화살("⇩") : 틈칸();
      }
      행들.push(d);
      // 둘째 줄은 오른쪽에서 왼쪽으로(뱀) — 칸 자리 c 에 단계 k + (k-1-c)
      const 둘 = c => { const i = k + (k - 1 - c); return i < n ? i : null; };
      줄짓기(둘, "⇦", m => { const i = k + (k - 1 - (m + 1)); return i >= k && i + 1 < n ? i : null; });
    }
    return 격자표(C, sp, 폭들, 행들);
  }
  // 세로 목록형 — [번호 칩 | 틈 | 단계 | (주체)]. 단계 사이 ▼ 와 전이 글
  // 칩 폭은 가장 긴 번호의 글폭으로 — 두 자리(10~)가 '1/0' 으로 세로로 쪼개졌다(적대 검토 M2 '26-09-29)
  const 칩 = Math.max(f * 2.2, 글폭(String(n), f) * 1.08 + 2 * C.padX + 2), g = Math.max(3, f * 0.3), 주체폭 = 주체있음
    ? Math.min(C.W * 0.3, Math.max(...항목들.map(it => it.주체 ? 글폭(String(it.주체), C.fs) : 0)) + C.fs) : 0;
  const 폭들 = [칩, g, C.W - 칩 - g - 주체폭].concat(주체있음 ? [주체폭] : []);
  const 행들 = [];
  // 쪽 나눔 조각이면 [a, b) 단계만 — 번호는 전체 차례 그대로, 조각 끝 뒤 ▼ 는 다음 조각이 잇는다
  const [a, b] = 범위풀기(C, n);
  항목들.forEach((it, i) => {
    if (i < a || i >= b) return;
    행들.push(칸(C, String(i + 1), { 칠: 칠(C.색, it.역 === "강조" ? "강조" : "보조", "머리"), f, 굵기: 700 })
      + 틈칸() + 단계칸(i, { 왼쪽: true })
      + (주체있음 ? (it.주체 ? 작은(String(it.주체), { 왼쪽: true }) : 틈칸()) : ""));
    // 촘촘(높이 상한 마지막 후보) — 전이 글 없는 ▼ 행은 뺀다(번호 칩이 차례를 말한다)
    if (i < n - 1 && i < b - 1 && !(C.촘촘 && !it.전이))
      행들.push(칸(C, "▼", { f, 글색: C.색.line, padY: f * 0.1, padX: 0 }) + 틈칸()
        + (it.전이 ? 작은(it.전이, { 왼쪽: true }) : 틈칸())
        + (주체있음 ? 틈칸() : ""));
  });
  return 격자표(C, sp, 폭들, 행들);
};
G.process.단위 = sp => 배열(sp["단계"]).length;         // 쪽 나눔 단위 = 단계(판정 ⑧)

// 비교판 — [현행 | ⇨ | 개선] 두 판을 나란히. 현행 머리는 회색(비교 기준), 개선 머리는 중간 파스텔.
// 항목은 칸 하나에 하나, 판 하나는 바깥 네 변만 긋는다. 강조 자동 없음(색은 항목 '색' 역할로만)
G.compare = (sp, C) => {
  const 전 = 배열(sp["전"]), 후 = 배열(sp["후"]), 머리 = 배열(sp["머리"]);
  const h0 = String(lab(머리[0]) || "현행"), h1 = String(lab(머리[1]) || "개선");
  const m = Math.max(전.length, 후.length), f = C.f;
  const aw = f * 2.4, sw = (C.W - aw) / 2;
  let gi = 0;
  const 머리gi0 = gi++, 전gi = 전.map(() => gi++), 머리gi1 = gi++, 후gi = 후.map(() => gi++);
  const 행들 = [칸(C, h0, { 칠: 칠(C.색, "회색"), f, 굵기: 700, gi: 머리gi0 }) + 틈칸()
               + 칸(C, h1, { 칠: 칠(C.색, "보조", "머리"), f, 굵기: 700, gi: 머리gi1 })];
  for (let i = 0; i < m; i++) {
    const 판 = (arr, gis, 기본칠) => {
      const x = arr[i], 있음 = i < arr.length;
      const 역 = 있음 ? 역할(x, "") : "";
      const 칠값 = 역 ? 칠(C.색, 역 === "강조" ? "강조" : 역) : 기본칠;
      return 칸(C, 있음 ? lab(x) : "", { 칠: { ...칠값, bold: 역 === "강조" ? 700 : 400 }, f, 왼쪽: true,
                 변: 몸변(i, m - 1), 속: 몸속(i, m - 1), gi: 있음 ? gis[i] : undefined });
    };
    행들.push(판(전, 전gi, 흰칠(C))
      + (i === 0 ? 칸(C, "⇨", { f: f * 1.6, 글색: C.색.line, 굵기: 700, rs: m, padX: 0 }) : "")
      + 판(후, 후gi, 칠(C.색, "보조")));
  }
  return 격자표(C, sp, [sw, aw, sw], 행들);
};

// ── 자리(칸) — 크기·글자·색을 한데 모은다 ───────────────────────────────
const 차트유형 = { bar: 1, line: 1, hbar: 1, donut: 1, stack: 1 };
const 크기풀기 = v => (typeof v === "string" && 제것({ "작게": 1, "보통": 1, "크게": 1 }, v)) ? v : "보통";
function 자리짓기(spec, el, o = {}) {
  const 토 = 토큰읽기(el), 수치 = 토.수치;
  const 크기 = 크기풀기(spec && spec["크기"]);
  let W = o.W || (el ? el.clientWidth : 0);
  // 폭을 못 잰다(숨김·빈 flex 칸) → 프리셋 mm. 짝이면 그 절반 남짓
  if (!(W > 0)) W = 수치["slot-mm"] * MM * (o.짝 ? 0.48 : 1);
  // 홀로 선 차트는 '작게'여도 전폭이다 — 높이만 낮춘다(아래 차트H 44mm, '26-09-29 판정 ⑦ · critic_design #1
  // 'A4 전폭 고정'). 예전엔 반폭 가운데(폭 0.50)라 판면 한가운데에 작은 섬이 떴다.
  const 더 = 크기 === "크게" ? 2 : 크기 === "작게" ? -1 : 0;
  const 최소 = 수치["pt-min"];
  const 역글 = spec && spec.type === "strategy" ? 수치["pt-sys"] : 수치["pt-flow"];
  // 역할 글자(문서 전체 고정)는 '보통'의 값이다. 사람이 그 도식에 고른 크기(작게·크게)가 그 도식만은 이긴다
  // — 한 문서에 흐름 11·13pt 가 섞여도 알리거나 되돌리지 않는다('26-09-29 판정 ③, 적대 검토 M4)
  const f = Math.max(역글 + 더, 최소) * PT;
  const fs = Math.max(수치["pt-sub"] + Math.min(더, 1), 최소) * PT;
  const fc = Math.max(수치["pt-chart"] + (크기 === "크게" ? 1 : 0), 최소) * PT;
  const sp = 크기 === "크게" ? 1.35 : 크기 === "작게" ? 0.8 : 1;
  const 차트H = (o.짝 || 크기 === "작게" ? 수치["chart-half-h-mm"]
                : 크기 === "크게" ? 수치["chart-big-h-mm"] : 수치["chart-h-mm"]) * MM;
  // 슬라이드 도식 장은 그림이 주인공이다 — 상자를 판면 띠처럼 얇게 두지 않고 폭의 0.42 까지 세운다
  // (A4 는 재경부처럼 얇은 흐름 띠가 맞다). 옛 덱의 도식 칸(.sl-fig)에서만 켠다.
  const 슬 = !!(el && el.closest && el.closest(".sl-page"));
  // 격자(표) 도식 — A4 에서 체계도·흐름띠는 <table> 로(위 '격자 도식'). 옛 슬라이드는 SVG 그대로이고,
  // 부르는 쪽이 {격자:false} 를 주면 SVG 로 그린다(SVG 배치 시험). 비교판은 SVG 가 없어 늘 격자다.
  const 격자 = !슬 && o.격자 !== false;
  return { W, f, fs, fc, min: 최소 * PT, sp, 크기, 색: 토.색, 차트H, 슬, 격자,
           maxH: 수치["max-h-mm"] * MM, padX: f * 0.6 * sp, padY: f * 0.42 * sp, 짝: !!o.짝 };
}

function render(spec, 자리) {
  // 제 열쇠만 — type 이 "toString"·"constructor" 면 R 의 원형 함수가 불려 글자가 좌표로 샜다
  const t = spec && spec.type;
  const fn = 제것(R, t) ? R[t] : null, 격 = 제것(G, t) ? G[t] : null;
  if (!fn && !격) return `<div class="ph">알 수 없는 도식 유형: ${esc(t)}</div>`;
  const C0 = 자리 && 자리.W && 자리.색 ? 자리 : 자리짓기(spec, null, 자리 || {});
  if (격 && (!fn || C0.격자)) return 격(spec, C0);
  const pad = 2;
  // viewBox 폭(= 그림 폭 + 양쪽 여유)이 칸 폭과 같아야 배율이 정확히 1 이다 — 그림은 여유만큼 좁게 짓는다
  const C = { ...C0, W: Math.max(C0.W - pad * 2, 40) };
  let [W, H, body] = fn(spec, C);
  // 판면 높이 × 0.9 상한 — 넘으면 간격부터 줄여 다시 그린다(글자는 그대로). 그래도 넘으면
  // 그림 전체를 그 높이에 맞게 줄이고 표시(fig-over)를 단다.
  if (H > C.maxH && C.sp > 0.7) {
    const C2 = { ...C, sp: 0.7, padX: C.f * 0.6 * 0.7, padY: C.f * 0.42 * 0.7 };
    [W, H, body] = fn(spec, C2);
  }
  const 넘침 = H > C.maxH;
  const 폭비 = 넘침 ? Math.max(20, Math.floor(C.maxH / H * 100)) : 100;
  const cap = spec["캡션"] || "";
  const title = esc(spec["대체텍스트"] || cap || spec.type);
  // 고유 폭(px)을 박지 않는다 — 칸 폭 = viewBox 폭이라 100% 로 두면 배율이 1 이다.
  // 인라인 style 은 장르 CSS(슬라이드 86%·크게/가득)보다 앞선다. 홀로 선 '작게' 차트도 전폭이다(판정 ⑦)
  const 폭 = 폭비;
  return `<svg viewBox="${-pad} ${-pad} ${r1(W + pad * 2)} ${r1(H + pad * 2)}" width="${폭}%" `
       + `class="fig-svg${넘침 ? " fig-over" : ""}" style="width:${폭}%;height:auto;max-width:100%;`
       + `max-height:none;display:block;margin:0 auto" `
       + `role="img" aria-label="${title}" xmlns="http://www.w3.org/2000/svg" `
       + `font-family="Pretendard, sans-serif"><title>${title}</title>${body}</svg>`;
}

// ── 짝(반폭 둘 나란히) — 이어진 차트 둘. 큰 차트·슬라이드는 짝을 안 짓는다 ────────
function 스펙(el) { try { return JSON.parse(el.dataset.fig || "{}"); } catch (e) { return {}; } }
function 짝가능(x) {
  if (!x || !x.classList || !x.classList.contains("fr-fig") || x.classList.contains("fr-img")) return false;
  if (!x.dataset || !x.dataset.fig || (x.closest && x.closest(".sl-page"))) return false;
  const s = 스펙(x);
  return 제것(차트유형, s.type) && 크기풀기(s["크기"]) !== "크게";
}
function 짝찾기(el) {
  if (!짝가능(el)) return null;
  let a = el;
  while (짝가능(a.previousElementSibling)) a = a.previousElementSibling;
  const run = [];
  for (let x = a; 짝가능(x); x = x.nextElementSibling) run.push(x);
  const k = run.indexOf(el);
  if (run.length < 2 || (k % 2 === 0 && k + 1 >= run.length)) return null;   // 홀수 끝은 홀로
  return k % 2 === 0 ? "왼" : "오";
}
function 짝달기(el, 짝) {
  el.classList.toggle("fig-pair", !!짝);
  el.classList.toggle("fig-pair-l", 짝 === "왼");
  el.classList.toggle("fig-pair-r", 짝 === "오");
}

// 그릴 글을 짓는다(짝 클래스는 먼저 단다 — 반폭이 정해져야 그 폭을 잰다). 넣지는 않는다.
function 짓기(el) {
  let spec; try { spec = JSON.parse(el.dataset.fig || "{}"); } catch (e) { return null; }
  const 짝 = 짝찾기(el);
  짝달기(el, 짝);
  const cap = spec["캡션"] || "", note = spec["함의"] || "";
  const C = 자리짓기(spec, el, { 짝: !!짝 });
  const 싸기 = C2 => (cap ? `<div class="cap">&lt; ${esc(cap)} &gt;</div>` : "")
             + render(spec, C2)
             + (note ? `<div class="note">${esc(note)}</div>` : "");
  const html = 싸기(C);
  // 격자(표) 도식의 높이 상한 후보 — 간격 좁히기 → 한 단 작게 → 두 단 작게(글자 하한은 자리짓기가 지킨다)
  const 후보 = () => {
    const 좁게 = C1 => ({ ...C1, sp: Math.min(C1.sp, 0.7), padX: C1.f * 0.6 * Math.min(C1.sp, 0.7),
                                  padY: C1.f * 0.42 * Math.min(C1.sp, 0.7) });
    const 단 = ["크게", "보통", "작게"], k = 단.indexOf(C.크기);
    // 단마다 [간격 좁힘] → (흐름이면) [▼ 행 뺌] 차례 — 글자(역할 pt)를 되도록 지킨다. 세로 목록형 흐름의
    // 전이 글 없는 ▼ 행은 번호 칩이 차례를 말하므로 뺄 수 있다
    const out = [];
    for (let j = Math.max(k, 0); j < 단.length; j++) {
      const Cj = 좁게(j === k || k < 0 ? C : 자리짓기({ ...spec, "크기": 단[j] }, el, { 짝: !!짝 }));
      const 이름 = j === k || k < 0 ? "" : 단[j];
      out.push([Cj, 이름]);
      if (spec.type === "process") out.push([{ ...Cj, 촘촘: true }, 이름]);
      if (k < 0) break;
    }
    return out.map(([C2, 단이름]) => [싸기(C2), 단이름]);
  };
  // 쪽 나눔 조각('26-09-29 판정 ⑧) — 격자로 한 쪽에 못 담는 절차·체계도는 글자를 줄이는 그림(SVG 비율 축소)
  // 물러섬 대신 조판기가 쪽마다 조각으로 나눠 싣는다. 이어지는 조각은 캡션에 '(계속)'을 달고, 열 배치 체계도는
  // 전략 머리 줄을 되풀이한다(G.strategy). 함의(※)는 마지막 조각에만. 비교판은 가운데 ⇨ 칸이 모든 줄을 세로로
  // 합쳐 끊을 자리가 없어 나누지 않고 경고만 남긴다(높이맞추기).
  const 격자 = !!(C.격자 && 제것(G, spec.type));
  const 나눌 = 격자 && typeof G[spec.type].단위 === "function";
  const 단위 = 나눌 ? G[spec.type].단위(spec, C) : 0;
  const 조각 = 나눌 ? (a, b) => (a === 0 ? (cap ? `<div class="cap">&lt; ${esc(cap)} &gt;</div>` : "")
                                 : `<div class="cap">${cap ? `&lt; ${esc(cap)}(계속) &gt;` : "(계속)"}</div>`)
                               + render(spec, { ...C, 범위: [a, b] })
                               + (b >= 단위 && note ? `<div class="note">${esc(note)}</div>` : "") : null;
  // '크게' 체계도 한 쪽(판정 ⑥) — 칸이 많을 때만 과제 칸 여백을 늘려 판면 높이 상한(0.9쪽)까지 채운다
  const 한쪽 = 격자 && spec.type === "strategy" && C.크기 === "크게" && G.strategy.한쪽(spec)
    ? 덧 => 싸기({ ...C, 과제덧: 덧 }) : null;
  const 과제줄 = 한쪽 ? G.strategy.과제줄(spec, C) : 0;
  return { html, 짝, W: el.clientWidth, 격자, maxH: C.maxH, 후보, 조각, 단위, 한쪽, 과제줄,
           비교: spec.type === "compare" };
}
// 격자 도식이 판면 높이 상한(--fig-max-h-mm, 판면 × 0.9)을 넘으면 — SVG 길(간격 → 비율 축소 → fig-over)처럼
// 간격을 좁히고, 그래도 넘치면 한 단씩 작게 다시 그린다. 크기를 줄여 맞췄으면 data-fig-fit 에 실제 단을
// 적는다(편집기 게이트가 '크게 → 실제 보통' 을 막는 데 쓴다). 적대 검토 H4('26-09-29): 격자는 상한이 없어
// 긴 절차·큰 체계도가 PDF 에서 잘렸다. 그래도 넘치면 — 절차·체계도는 사람이 고른 크기 그대로 두고
// data-fig-split 을 달아 조판기가 쪽을 나눠 싣게 한다(판정 ⑧, 나눠싣기). 나눌 수 없는 비교판은 fig-over 와
// 경고(data-fig-warn · console)를 남긴다(조판 넘침 표식·편집기 크기 게이트가 본다).
const 비교판경고 = "비교판이 한 쪽을 넘습니다 — 비교판은 쪽을 나눌 수 없어 넘친 줄이 잘립니다(항목을 줄이거나 두 도식으로 나누세요)";
function 높이맞추기(el, g) {
  el.classList.remove("fig-over");
  delete el.dataset.figFit;
  delete el.dataset.figSplit;
  delete el.dataset.figFill;
  delete el.dataset.figWarn;
  if (!g.격자 || !(g.maxH > 0)) return;
  const 표 = () => el.querySelector("table.fig-grid");
  const 높이 = () => { const t = 표(); return t ? t.offsetHeight : 0; };
  let h = 높이();
  if (!(h > 0)) return;                                    // 0 = 아직 조판 전(숨김) — 재지 않는다
  if (h <= g.maxH) { 한쪽채우기(el, g, h, 높이); return; }
  for (const [html, 단] of g.후보()) {
    그려넣기(el, html);
    h = 높이();
    if (h <= g.maxH) { if (단) el.dataset.figFit = 단; return; }
  }
  if (g.조각 && g.단위 > 1) {                              // 쪽 나눔 — 고른 크기(글자) 그대로
    그려넣기(el, g.html);
    el.dataset.figSplit = "1";
    return;
  }
  el.classList.add("fig-over");
  const t = 표();
  if (t) t.classList.add("fig-over");
  if (g.비교) {
    el.dataset.figWarn = 비교판경고;
    try { console.warn("[도식 경고] " + 비교판경고); } catch (e) { /* 콘솔 없음 */ }
  }
}
// '크게' 체계도 한 쪽 — 모자란 높이를 과제 줄에 고루 나눠 여백으로 준다. 넘치면 되돌린다
function 한쪽채우기(el, g, h, 높이) {
  if (!g.한쪽 || !(g.과제줄 > 0)) return;
  const 곁 = Math.max(0, el.offsetHeight - h);             // 캡션·함의 몫
  const 목표 = g.maxH - 곁;
  if (!(목표 > h * 1.02)) return;
  그려넣기(el, g.한쪽((목표 - h) / g.과제줄));
  if (높이() > 목표 + 1) { 그려넣기(el, g.html); return; }
  el.dataset.figFill = "한쪽";
}
// 쪽 나눔 — 조판기(assemble_full paginate)가 부른다. el 을 지금 쪽(inner)에 두고, 맞나(inner)가 참인 동안 조각을
// 늘린다. 넘치면 새쪽() 을 받아 이음 조각(.fr-fig-cont — 같은 도식 역할 data-ent="도식", 스펙·경로 없음)을 싣는다.
// 첫 조각이 앞 글 밑에 두 단위도 못 들면 새 쪽에서 시작한다. 마지막 쪽 inner 를 돌려준다.
let 이음수 = 0;
function 이음지우기(el) {
  const id = el && el.dataset && el.dataset.figId;
  if (id) document.querySelectorAll(".fr-fig-cont").forEach(x => { if (x.dataset.figCont === id) x.remove(); });
  if (el && el.dataset) delete el.dataset.figCut;
}
function 나눌수(el) {
  return !!(el && el.dataset && el.dataset.figSplit === "1" && el.__도식 && el.__도식.조각);
}
function 나눠싣기(el, inner, 맞나, 새쪽) {
  const g = el.__도식, N = g.단위;
  이음지우기(el);
  if (!el.dataset.figId) el.dataset.figId = "fs" + (++이음수);
  el.dataset.figCut = "1";
  let a = 0, cur = el;
  while (a < N) {
    const 넣기 = e => 그려넣기(cur, g.조각(a, e));
    if (inner.childElementCount > 1) {
      넣기(Math.min(a + 2, N));
      if (!맞나(inner)) { inner.removeChild(cur); inner = 새쪽(); inner.appendChild(cur); }
    }
    let e = a + 1;
    넣기(e);
    while (e < N) { 넣기(e + 1); if (!맞나(inner)) { 넣기(e); break; } e++; }
    // 끝 조각에 한 단위만 남으면(다음 쪽 외톨이 한 줄) 이 조각에서 하나를 넘겨 둘로 싣는다
    if (e < N && N - e < 2 && e - a > 2) { e = N - 2; 넣기(e); }
    a = e;
    if (a < N) {
      const c = document.createElement("div");
      c.className = "blk fr-fig fr-fig-cont";
      c.dataset.ent = "도식";
      c.dataset.figCont = el.dataset.figId;
      inner = 새쪽(); inner.appendChild(c); cur = c;
    }
  }
  return inner;
}
// 조판을 다시 잡기 전에 — 이음 조각을 걷고 나뉜 도식을 통째로 되그린다(조판기·편집기가 부른다)
function 되붙이기(root) {
  (root || document).querySelectorAll(".fr-fig-cont").forEach(x => x.remove());
  (root || document).querySelectorAll(".fr-fig[data-fig-cut]").forEach(el => mount(el, false));
}
function mount(el, 곁 = true) {
  const g = 짓기(el);
  if (!g) return;
  이음지우기(el);
  el.__도식 = g;
  그려넣기(el, g.html);
  높이맞추기(el, g);
  // 이어진 도식 줄 전체에서 짝이 바뀐 것을 다시 그린다(유형·크기를 바꿔 차트 줄이 갈리면 바로 옆이
  // 아닌 셋째·넷째의 짝도 바뀐다 — 예: [A B C D] 에서 A 를 크게 하면 B·C 가 짝, D 는 홀로. '26-09-29 fixup)
  if (곁) {
    const 줄 = [];
    for (let x = el.previousElementSibling; x && x.classList && x.classList.contains("fr-fig"); x = x.previousElementSibling) 줄.push(x);
    for (let x = el.nextElementSibling; x && x.classList && x.classList.contains("fr-fig"); x = x.nextElementSibling) 줄.push(x);
    줄.forEach(x => { if (x.__도식 && x.__도식.짝 !== 짝찾기(x)) mount(x, false); });
  }
}
function mountAll(root) {
  (root || document).querySelectorAll('.fr-fig[data-fig]').forEach(el => mount(el, false));
}
// 전부 다시 지어 보고, 지난번과 달라진 도식만 갈아 끼운 뒤 그 수를 돌려준다. 글꼴이 앉은 뒤
// (jachigan.js) 부른다 — 달라진 것이 있을 때만 재조판(__repaginate)이 따라 돈다. 같으면 DOM 을
// 안 건드린다(편집기가 잡고 있는 라벨 마디를 갈아엎지 않게).
function refresh(root) {
  let n = 0;
  (root || document).querySelectorAll('.fr-fig[data-fig]').forEach(el => {
    const g = 짓기(el);
    if (!g) return;
    if (el.__도식 && el.__도식.html === g.html && el.firstChild) return;
    이음지우기(el);                                        // 나뉘어 있었으면 조각을 걷는다 — 재조판이 다시 나눈다
    el.__도식 = g;
    그려넣기(el, g.html);
    높이맞추기(el, g);
    n++;
  });
  return n;
}
window.SVGFIG = { render, mount, mountAll, refresh, wrap, 크기풀기, 나눌수, 나눠싣기, 되붙이기 };
mountAll();
})();
