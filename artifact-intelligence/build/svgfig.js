/* 도식 SVG 생성기 — 브라우저 단일 소스.
   Python(svgfig.py)이 서버에서 그리던 것을 옮겨왔다. 이유: 편집기에서 유형·단계를 바꾸면
   좌표를 전부 다시 계산해야 하는데, 생성기가 서버에만 있으면 즉시 반영이 불가능하다.
   PDF도 Chrome headless로 뽑으므로 브라우저가 그려도 벡터·한글 텍스트가 그대로 남는다.

   window.SVGFIG.render(spec) → SVG 문자열
   window.SVGFIG.mount(el)    → el.dataset.fig 를 읽어 그 안에 캡션·SVG·함의를 채운다 */
(() => {
const PASTEL = ["#EAF2FB", "#EAF7EE", "#FFF6E5", "#F3EAF7", "#EAF7F7"];
const ACCENT_BG = "#2E7D4F", LINE = "#666";
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const w = s => [...String(s)].reduce((a, c) => a + (c.codePointAt(0) > 0x2000 ? 1 : 0.55), 0);
const r1 = n => Math.round(n * 10) / 10;

function wrap(text, maxEm) {
  const out = []; let cur = "";
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const t = cur ? cur + " " + word : word;
    if (cur && w(t) > maxEm) { out.push(cur); cur = word; } else cur = t;
  }
  if (cur) out.push(cur);
  return out.length ? out : [""];
}
function tspans(lines, x, y0, fs, lh = 1.25) {
  const top = y0 - (lines.length - 1) * fs * lh / 2;
  return lines.map((t, i) => `<tspan x="${x}" y="${r1(top + i * fs * lh)}">${esc(t)}</tspan>`).join("");
}
function box(x, y, bw, bh, text, fill, o = {}) {
  const fs = o.fs || 13, color = o.color || "#000", stroke = o.stroke || "#555";
  const lines = wrap(text, (bw - 10) / fs);
  return `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="2" fill="${fill}" `
       + `stroke="${stroke}" stroke-width="1.2"/>`
       + `<text x="${x + bw / 2}" y="${y + bh / 2}" font-size="${fs}" fill="${color}" `
       + `font-weight="${o.bold === false ? 400 : 700}" text-anchor="middle" `
       + `dominant-baseline="central">${tspans(lines, x + bw / 2, y + bh / 2, fs)}</text>`;
}
const arrowDefs = () =>
  `<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" `
  + `orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${LINE}"/></marker></defs>`;
function arrow(x1, y1, x2, y2, label = "", both = false) {
  let a = `<line x1="${r1(x1)}" y1="${r1(y1)}" x2="${r1(x2)}" y2="${r1(y2)}" stroke="${LINE}" `
        + `stroke-width="1.6" marker-end="url(#ah)"${both ? ' marker-start="url(#ah)"' : ''}/>`;
  if (label) a += `<text x="${r1((x1 + x2) / 2)}" y="${r1((y1 + y2) / 2 - 5)}" font-size="10.5" `
                + `fill="#333" text-anchor="middle">${esc(label)}</text>`;
  return a;
}
const lab = s => (s && typeof s === "object") ? (s["라벨"] ?? "") : (s ?? "");

const R = {};
R.process = sp => {
  const steps = sp["단계"] || [], n = steps.length;
  const bw = 118, bh = 62, gap = 44, y = 26;
  const out = [arrowDefs()];
  steps.forEach((st, i) => {
    const x = i * (bw + gap);
    out.push(box(x, y, bw, bh, lab(st), PASTEL[i % PASTEL.length]));
    const sub = st && typeof st === "object" ? st["주체"] : null;
    if (sub) out.push(`<text x="${x + bw / 2}" y="${y + bh + 14}" font-size="10" fill="#555" `
                    + `text-anchor="middle">* ${esc(sub)}</text>`);
    if (i < n - 1) out.push(arrow(x + bw + 6, y + bh / 2, x + bw + gap - 6, y + bh / 2,
                                  (st && typeof st === "object" ? st["전이"] : "") || ""));
  });
  return [n * bw + (n - 1) * gap, bh + 42, out.join("")];
};
R.cycle = sp => {
  const steps = sp["단계"] || [], n = steps.length;
  const Rr = 118, cx = 250, cy = 150, bw = 130, bh = 52;
  const out = [arrowDefs()], pts = [];
  for (let i = 0; i < n; i++) {
    const ang = -Math.PI / 2 + 2 * Math.PI * i / n;
    pts.push([cx + Rr * Math.cos(ang) * 1.35, cy + Rr * Math.sin(ang)]);
  }
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % n];
    const dx = x2 - x1, dy = y2 - y1, d = Math.hypot(dx, dy) || 1, pad = 78;
    out.push(arrow(x1 + dx / d * pad, y1 + dy / d * pad * 0.55,
                   x2 - dx / d * pad, y2 - dy / d * pad * 0.55));
  }
  pts.forEach(([x, y], i) => out.push(box(x - bw / 2, y - bh / 2, bw, bh, lab(steps[i]),
                                          PASTEL[i % PASTEL.length])));
  return [500, 300, out.join("")];
};
R.converge = sp => {
  const reqs = sp["요건"] || [], bw = 132, bh = 46, gap = 18, n = reqs.length;
  const colh = n * bh + (n - 1) * gap, H = Math.max(colh, 90) + 20, cy = H / 2;
  const out = [arrowDefs()], top = cy - colh / 2;
  reqs.forEach((r, i) => {
    const y = top + i * (bh + gap);
    out.push(box(0, y, bw, bh, r, PASTEL[i % PASTEL.length], { fs: 12 }));
    out.push(arrow(bw + 4, y + bh / 2, bw + 52, cy));
  });
  const x2 = bw + 60;
  out.push(box(x2, cy - 32, 128, 64, sp["시행"] || "", "#FFF6E5", { fs: 13 }));
  out.push(arrow(x2 + 132, cy, x2 + 180, cy));
  out.push(box(x2 + 186, cy - 32, 138, 64, sp["결과"] || "", ACCENT_BG,
               { fs: 13, color: "#fff", stroke: ACCENT_BG }));
  return [x2 + 330, H, out.join("")];
};
R.strategy = sp => {
  const cols = sp["전략"] || [], n = cols.length, cw = 152, gap = 18;
  const W = n * cw + (n - 1) * gap, gh = 54, hh = 42, th = 34, tgap = 8, top = gh + 22;
  const out = [box(0, 0, W, gh, sp["목표"] || "", "#E5F5E5", { fs: 14, stroke: "#6E9E6E" })];
  let maxTasks = 0;
  cols.forEach((col, i) => {
    const x = i * (cw + gap);
    const tasks = col["과제"] || [];
    maxTasks = Math.max(maxTasks, tasks.length);
    out.push(`<line x1="${W / 2}" y1="${gh}" x2="${x + cw / 2}" y2="${top - 8}" `
           + `stroke="${LINE}" stroke-width="1.2"/>`);
    out.push(box(x, top, cw, hh, col["제목"] || "", PASTEL[i % PASTEL.length], { fs: 13 }));
    tasks.forEach((t, j) => {
      const ty = top + hh + 10 + j * (th + tgap);
      out.push(`<rect x="${x + 8}" y="${ty}" width="${cw - 16}" height="${th}" fill="#fff" `
             + `stroke="#999" stroke-width="0.9"/>`);
      const lines = wrap(t, (cw - 30) / 11);
      out.push(`<text x="${x + 16}" y="${ty + th / 2}" font-size="11" fill="#000" `
             + `dominant-baseline="central">`
             + lines.map((l, k) => `<tspan x="${x + 16}" y="${r1(ty + th / 2 - (lines.length - 1) * 6.8 + k * 13.6)}">▪ ${esc(l)}</tspan>`).join("")
             + `</text>`);
    });
  });
  return [W, top + hh + 10 + maxTasks * (th + tgap), out.join("")];
};
R.relation = sp => {
  const nodes = sp["노드"] || [], edges = sp["연결"] || [], cols = sp["열"] || 3;
  const bw = 138, bh = 56, gx = 46, gy = 46, pos = {};
  nodes.forEach((nd, i) => {
    const key = (nd && typeof nd === "object") ? nd.id : nd;
    pos[key] = [(i % cols) * (bw + gx), Math.floor(i / cols) * (bh + gy)];
  });
  const rows = Math.ceil(nodes.length / cols);
  const out = [arrowDefs()];
  edges.forEach(e => {
    const p1 = pos[e.from], p2 = pos[e.to];
    if (!p1 || !p2) return;
    const c1 = [p1[0] + bw / 2, p1[1] + bh / 2], c2 = [p2[0] + bw / 2, p2[1] + bh / 2];
    const dx = c2[0] - c1[0], dy = c2[1] - c1[1], d = Math.hypot(dx, dy) || 1;
    const pad = Math.abs(dx) > Math.abs(dy) ? 76 : 34;
    out.push(arrow(c1[0] + dx / d * pad, c1[1] + dy / d * pad,
                   c2[0] - dx / d * pad, c2[1] - dy / d * pad, e["라벨"] || "", !!e["쌍방향"]));
  });
  nodes.forEach((nd, i) => {
    const key = (nd && typeof nd === "object") ? nd.id : nd;
    const acc = nd && typeof nd === "object" && nd["강조"];
    const [x, y] = pos[key];
    out.push(box(x, y, bw, bh, lab(nd) || key, acc ? ACCENT_BG : PASTEL[i % PASTEL.length],
                 { fs: 12, color: acc ? "#fff" : "#000", stroke: acc ? ACCENT_BG : "#555" }));
  });
  return [cols * bw + (cols - 1) * gx, rows * bh + (rows - 1) * gy, out.join("")];
};
R.stack = sp => {
  const sets = sp["세트"] || [], bw = 96, gap = 96, Hbar = 240;
  const out = sets.length > 1 ? [arrowDefs()] : [];
  sets.forEach((st, si) => {
    const x = si * (bw + gap);
    const items = st["항목"] || [];
    const total = items.reduce((a, [, v]) => a + v, 0) || 100;
    let y = 8;
    items.forEach(([name, v], k) => {
      const h = Hbar * v / total, acc = st["강조"] === name;
      out.push(`<rect x="${x}" y="${r1(y)}" width="${bw}" height="${r1(h)}" `
             + `fill="${acc ? ACCENT_BG : PASTEL[k % PASTEL.length]}" stroke="#555" stroke-width="0.9"/>`);
      out.push(`<text x="${x + bw / 2}" y="${r1(y + h / 2)}" font-size="11" font-weight="700" `
             + `fill="${acc ? "#fff" : "#000"}" text-anchor="middle" dominant-baseline="central">`
             + `${esc(name)} ${v}%</text>`);
      y += h;
    });
    out.push(`<text x="${x + bw / 2}" y="${Hbar + 30}" font-size="12" font-weight="700" `
           + `text-anchor="middle">${esc(st["이름"] || "")}</text>`);
    if (si < sets.length - 1) out.push(arrow(x + bw + 14, Hbar / 2, x + bw + gap - 14, Hbar / 2));
  });
  return [sets.length * bw + (sets.length - 1) * gap, Hbar + 46, out.join("")];
};

/* ── 차트 3종 ─────────────────────────────────────────────────────────
   실물 공공보고서 본문 44쪽을 눈으로 보고 뽑은 규격이다(2026-08-01, PDF 실측).
     · 격자선을 긋지 않는다 — 한 장도 없었다
     · 판을 얇은 회색 테로 두른다
     · 범례는 판 위 가운데
     · 값 라벨은 막대에 붙이고, 꺾은선은 **마지막 점에만** 붙인다
     · 꽉 찬 파이는 한 장도 없었다. 원형은 전부 **도넛**이다
     · 색은 문서 포인트색 **하나**만 쓰고 계열은 투명도로 가른다
       (32건 중 31건이 포인트색 1개 + 연한 파생. 무지개 배색은 실물에 없다)
   언제 쓰는가는 정본이 정한다 — data_elements.시각자료.의미구조_유형.시계열
   "5시점 초과 또는 메시지가 '추세·속도' → 선·막대그래프". 이 파일은 그리기만 한다. */
const 계열색 = i => `var(--doc-color-accent, #1F3864)`;
const 계열농도 = [1, 0.62, 0.38, 0.22, 0.13];
const 진하기 = i => 계열농도[i % 계열농도.length];
const 수 = n => (Math.round(n * 100) / 100).toLocaleString("ko-KR");

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

function 판(sp, 계열들) {
  /* 판 하나를 잡아 준다. 두 차트가 같은 자를 쓰게 하려고 따로 뺐다. */
  const 시점 = sp["시점"] || [];
  // 쌓기면 축의 끝은 개별 값이 아니라 **시점별 누적합**이다.
  // 개별 값으로 잡으면 막대가 판 위로 넘쳐 범례와 겹치고 라벨이 잘려 나간다.
  const 값전부 = sp["쌓기"]
    ? 시점.map((_, i) => 계열들.reduce(
        (a, s) => a + (typeof (s["값"] || [])[i] === "number" ? s["값"][i] : 0), 0))
    : 계열들.flatMap(s => (s["값"] || []).filter(v => typeof v === "number"));
  const ticks = 눈금(Math.max(...값전부, 0), Math.min(...값전부, 0));
  const 왼 = Math.max(38, 8 + 7.2 * Math.max(...ticks.map(t => 수(t).length)));
  const 위 = (계열들.length > 1 ? 22 : 0) + (sp["단위"] ? 16 : 0);
  // 칸 너비는 계열 수와 **값 라벨 길이**를 함께 따라 늘린다.
  // 계열 수만 보면 3계열부터 막대가 14px 로 좁아져 라벨이 뭉치고("410 470 505"),
  // 라벨 길이를 안 보면 큰 수(151,900)에서 라벨이 통째로 사라진다.
  // 자리가 없다고 조용히 빼면 스펙 쓴 사람이 모른다 — 그래서 자리를 만든다.
  // 작은 글꼴(9)로도 라벨이 들어갈 막대 폭을 먼저 구하고, 거기서 칸을 역산한다.
  // 막대는 칸의 62%를 묶음 수로 나눠 쓰므로 0.62 로 나눈다.
  const 라벨폭 = Math.max(...값전부.map(v => 수(v).length), 1) * 9 * 0.56;
  const 묶음수 = sp["쌓기"] ? 1 : Math.max(계열들.length, 1);
  const 칸너비 = Math.min(150, Math.max(66, 묶음수 * (라벨폭 + 4) / 0.62));
  const 판높이 = 168, 판폭 = Math.max(300, 시점.length * 칸너비);
  const 아래 = 24 + (시점.some(t => w(t) > 4) ? 12 : 0);
  const y = v => 위 + 판높이 * (1 - (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0] || 1));
  return { 시점, ticks, 왼, 위, 판높이, 판폭, 아래, y,
           W: 왼 + 판폭, H: 위 + 판높이 + 아래 };
}

function 판테(g) {
  // 격자선은 긋지 않는다. 테와 눈금 글자만.
  let s = `<rect x="${g.왼}" y="${g.위}" width="${g.판폭}" height="${g.판높이}" fill="none" `
        + `stroke="#B8B8B8" stroke-width="0.8"/>`;
  g.ticks.forEach(t => {
    s += `<text x="${g.왼 - 6}" y="${r1(g.y(t))}" font-size="10" fill="#444" `
       + `text-anchor="end" dominant-baseline="central">${esc(수(t))}</text>`;
  });
  if (g.ticks[0] < 0) s += `<line x1="${g.왼}" y1="${r1(g.y(0))}" x2="${g.왼 + g.판폭}" `
                         + `y2="${r1(g.y(0))}" stroke="#B8B8B8" stroke-width="0.8"/>`;
  return s;
}

function 가로칸(g) {
  const 칸 = g.판폭 / (g.시점.length || 1);
  return g.시점.map((t, i) =>
    `<text x="${r1(g.왼 + 칸 * (i + 0.5))}" y="${g.위 + g.판높이 + 14}" font-size="10.5" `
    + `fill="#333" text-anchor="middle">${esc(t)}</text>`).join("");
}

function 범례(계열들, g) {
  if (계열들.length < 2) return "";
  // 판 위 가운데 — 실물에서 예외를 못 봤다
  const 칸 = 계열들.map(s => 12 + 6.4 * w(s["이름"] || "") + 14);
  const 총 = 칸.reduce((a, b) => a + b, 0);
  let x = g.왼 + (g.판폭 - 총) / 2, out = "";
  계열들.forEach((s, i) => {
    out += `<rect x="${r1(x)}" y="${g.위 - 17}" width="9" height="9" fill="${계열색(i)}" `
         + `fill-opacity="${진하기(i)}"/>`
         + `<text x="${r1(x + 13)}" y="${g.위 - 12.5}" font-size="10.5" fill="#333" `
         + `dominant-baseline="central">${esc(s["이름"] || "")}</text>`;
    x += 칸[i];
  });
  return out;
}

function 단위표기(sp, g) {
  if (!sp["단위"]) return "";
  // 표와 같은 규범 — 오른쪽 위 괄호
  return `<text x="${g.왼 + g.판폭}" y="${g.위 - (g.계열수 > 1 ? 24 : 6)}" font-size="10" `
       + `fill="#555" text-anchor="end">(단위: ${esc(sp["단위"])})</text>`;
}

R.bar = sp => {
  const 계열들 = sp["계열"] || [];
  const g = 판(sp, 계열들); g.계열수 = 계열들.length;
  const 쌓기 = !!sp["쌓기"];
  const 칸 = g.판폭 / (g.시점.length || 1);
  const 묶음 = 쌓기 ? 1 : 계열들.length;
  const 막대폭 = Math.min(34, (칸 * 0.62) / 묶음);
  const out = [판테(g), 범례(계열들, g), 단위표기(sp, g), 가로칸(g)];
  g.시점.forEach((_, i) => {
    const 가운데 = g.왼 + 칸 * (i + 0.5);
    let 쌓인 = 0;
    계열들.forEach((s, k) => {
      const v = (s["값"] || [])[i];
      if (typeof v !== "number") return;
      const x = 쌓기 ? 가운데 - 막대폭 / 2
                     : 가운데 - (묶음 * 막대폭) / 2 + k * 막대폭;
      const y0 = 쌓기 ? g.y(쌓인 + v) : g.y(Math.max(v, 0));
      const h = Math.abs(g.y(쌓기 ? 쌓인 : 0) - g.y(쌓기 ? 쌓인 + v : v));
      out.push(`<rect x="${r1(x)}" y="${r1(y0)}" width="${r1(막대폭)}" height="${r1(h)}" `
             + `fill="${계열색(k)}" fill-opacity="${진하기(k)}"/>`);
      // 값 라벨은 막대에 붙인다 — 실물 규격.
      // 다만 글자가 막대 자리보다 넓으면 겹쳐서 못 읽는다. 그때는 붙이지 않는다.
      // 값은 왼쪽 눈금이 이미 말해 주므로 안 붙여도 정보가 사라지지는 않는다.
      const 글자 = 수(v);
      // 쓸 수 있는 자리: 계열이 하나면 칸 전체를 쓴다(옆에 다른 막대가 없다).
      // 묶음이면 제 막대 폭만큼만 — 안 그러면 옆 계열 라벨과 부딪힌다.
      const 자리 = (묶음 === 1 && !쌓기) ? 칸 * 0.92 : 막대폭 + 3;
      // 글꼴은 문턱으로 고르지 않고 **들어가는 것 중 큰 것**으로 고른다.
      // 문턱으로 고르면 막대가 조금 넓다는 이유로 큰 글꼴을 잡았다가 못 들어가
      // 라벨이 통째로 사라진다(151,900 에서 실제로 그랬다).
      const 글꼴 = [10, 9].find(fs => 글자.length * fs * 0.56 <= 자리);
      if (글꼴) {
        // 쌓기면 칸 안 가운데. 음수면 막대 아래인데, 판 바닥에 닿으면 x축 글자와
        // 겹치므로 그때는 막대 안쪽에 넣는다.
        const 바닥 = g.위 + g.판높이;
        const ly = 쌓기 ? (y0 + h / 2)
                 : v < 0 ? (y0 + h + 11 > 바닥 - 2 ? y0 + h - 5 : y0 + h + 11)
                 : y0 - 4;
        // 흰 글자는 배경이 충분히 진할 때만 — 0.62 농도에 흰 글자는 안 읽힌다
        const 흰 = (쌓기 || (v < 0 && ly < y0 + h)) && 진하기(k) >= 0.85;
        out.push(`<text x="${r1(x + 막대폭 / 2)}" y="${r1(ly)}" font-size="${글꼴}" `
               + `fill="${흰 ? "#fff" : "#222"}" text-anchor="middle"`
               + `${쌓기 ? ' dominant-baseline="central"' : ""}>${esc(글자)}</text>`);
      }
      쌓인 += v;
    });
  });
  return [g.W, g.H, out.join("")];
};

R.hbar = sp => {
  /* 가로 막대 — 항목 이름이 길 때. 세로 막대는 이름이 길면 x축에서 겹친다.
     근거: 범정부오피스 서식 도구에 '가로막대'가 5색 변형으로 들어 있다
     (research/corpus/bumpiece-extraction/features-inventory.md 차트 14종).
     실무자에게 주어지는 도구에 있다는 것은 쓰인다는 뜻이다. */
  const 계열들 = sp["계열"] || [], 이름들 = sp["시점"] || [];
  const 값전부 = 계열들.flatMap(s => (s["값"] || []).filter(v => typeof v === "number"));
  const ticks = 눈금(Math.max(...값전부, 0), Math.min(...값전부, 0));
  const 왼 = Math.max(52, 8 + 6.6 * Math.max(...이름들.map(w), 0));
  // 단위 표기 자리를 위에 비워 둔다 — 안 비우면 판 밖으로 나가 잘린다
  const 위 = (계열들.length > 1 ? 22 : 0) + (sp["단위"] ? 16 : 0);
  const 묶음 = 계열들.length || 1;
  const 줄높이 = Math.max(26, 묶음 * 15 + 12);
  const 판높이 = 이름들.length * 줄높이, 판폭 = 320;
  const x = v => 왼 + 판폭 * (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0] || 1);
  const g = { 왼, 위, 판폭, 판높이, ticks, 계열수: 묶음, y: null };
  const out = [`<rect x="${왼}" y="${위}" width="${판폭}" height="${판높이}" fill="none" `
             + `stroke="#B8B8B8" stroke-width="0.8"/>`, 단위표기(sp, g)];
  ticks.forEach(t => out.push(
    `<text x="${r1(x(t))}" y="${위 + 판높이 + 13}" font-size="10" fill="#444" `
    + `text-anchor="middle">${esc(수(t))}</text>`));
  if (계열들.length > 1) {
    let lx = 왼 + (판폭 - 계열들.reduce((a, s) => a + 26 + 6.4 * w(s["이름"] || ""), 0)) / 2;
    계열들.forEach((s, k) => {
      out.push(`<rect x="${r1(lx)}" y="${위 - 17}" width="9" height="9" fill="${계열색(k)}" `
             + `fill-opacity="${진하기(k)}"/><text x="${r1(lx + 13)}" y="${위 - 12.5}" `
             + `font-size="10.5" fill="#333" dominant-baseline="central">`
             + `${esc(s["이름"] || "")}</text>`);
      lx += 26 + 6.4 * w(s["이름"] || "");
    });
  }
  이름들.forEach((이름, i) => {
    const 가운데 = 위 + 줄높이 * (i + 0.5);
    out.push(`<text x="${왼 - 7}" y="${r1(가운데)}" font-size="10.5" fill="#333" `
           + `text-anchor="end" dominant-baseline="central">${esc(이름)}</text>`);
    const 막대두께 = Math.min(18, (줄높이 * 0.62) / 묶음);
    계열들.forEach((s, k) => {
      const v = (s["값"] || [])[i];
      if (typeof v !== "number") return;
      const y0 = 가운데 - (묶음 * 막대두께) / 2 + k * 막대두께;
      const x0 = x(Math.min(v, 0)), 길이 = Math.abs(x(v) - x(0));
      out.push(`<rect x="${r1(x0)}" y="${r1(y0)}" width="${r1(길이)}" `
             + `height="${r1(막대두께)}" fill="${계열색(k)}" fill-opacity="${진하기(k)}"/>`);
      // 값은 막대 끝 바깥에 — 가로 막대는 옆에 자리가 넉넉하다.
      // 다만 음수 막대가 판 왼쪽 끝까지 뻗으면 라벨이 판 밖으로 나가 항목 이름과
      // 겹친다. 그때는 막대 안쪽에 넣는다.
      const 글자폭 = 수(v).length * 5.6;
      const 밖 = v < 0 ? x0 - 4 - 글자폭 < 왼 + 2 : false;
      const lx = 밖 ? x0 + 4 : (v < 0 ? x0 - 4 : x0 + 길이 + 4);
      out.push(`<text x="${r1(lx)}" y="${r1(y0 + 막대두께 / 2)}" font-size="10" `
             + `fill="${밖 && 진하기(k) >= 0.85 ? "#fff" : "#222"}" `
             + `dominant-baseline="central" `
             + `text-anchor="${밖 ? "start" : v < 0 ? "end" : "start"}">${esc(수(v))}</text>`);
    });
  });
  const 끝여유 = 10 + 6 * Math.max(...값전부.map(v => 수(v).length), 1);
  return [왼 + 판폭 + 끝여유, 위 + 판높이 + 20, out.join("")];
};

R.line = sp => {
  const 계열들 = sp["계열"] || [];
  const g = 판(sp, 계열들); g.계열수 = 계열들.length;
  const 칸 = g.판폭 / (g.시점.length || 1);
  const x = i => g.왼 + 칸 * (i + 0.5);
  const out = [판테(g), 범례(계열들, g), 단위표기(sp, g), 가로칸(g)];
  const 끝라벨 = [];      // 끝값이 서로 가까우면 겹친다 — 다 그린 뒤 밀어낸다
  계열들.forEach((s, k) => {
    const 값 = s["값"] || [];
    const 점 = 값.map((v, i) => typeof v === "number" ? [x(i), g.y(v)] : null).filter(Boolean);
    if (!점.length) return;
    out.push(`<polyline points="${점.map(([a, b]) => `${r1(a)},${r1(b)}`).join(" ")}" `
           + `fill="none" stroke="${계열색(k)}" stroke-opacity="${진하기(k)}" stroke-width="1.8"`
           + `${k >= 2 ? ' stroke-dasharray="5 3"' : ""}/>`);
    점.forEach(([a, b]) => out.push(`<circle cx="${r1(a)}" cy="${r1(b)}" r="2.6" `
                                  + `fill="${계열색(k)}" fill-opacity="${진하기(k)}"/>`));
    // 값 라벨은 마지막 점에만 — 실물 규격. 전부 붙이면 선이 안 읽힌다
    const 끝 = 점[점.length - 1], 끝값 = 값.filter(v => typeof v === "number").pop();
    끝라벨.push({ x: 끝[0] + 6, y: 끝[1] - 6, 글: 수(끝값) });
  });
  // 두 계열의 끝값이 붙어 있으면 글자가 겹친다. 위아래로 벌린다.
  끝라벨.sort((a, b) => a.y - b.y);
  for (let i = 1; i < 끝라벨.length; i++) {
    const 틈 = 끝라벨[i].y - 끝라벨[i - 1].y;
    if (틈 < 12) 끝라벨[i].y = 끝라벨[i - 1].y + 12;
  }
  끝라벨.forEach(l => out.push(
    `<text x="${r1(l.x)}" y="${r1(l.y)}" font-size="10.5" font-weight="700" `
    + `fill="#222">${esc(l.글)}</text>`));
  const 넘침 = Math.max(0, ...끝라벨.map(l => 6.2 * l.글.length + 10));
  return [g.W + 넘침, g.H, out.join("")];
};

R.donut = sp => {
  const 항목 = (sp["항목"] || []).map(it => Array.isArray(it) ? it : [it["이름"], it["값"]]);
  const 총 = 항목.reduce((a, [, v]) => a + v, 0) || 1;
  const cx = 108, cy = 108, R0 = 96, R1 = 58;   // 안쪽을 비운다 — 파이는 쓰지 않는다
  const out = [];
  let 각 = -Math.PI / 2;
  항목.forEach(([, v], k) => {
    const 폭 = 2 * Math.PI * v / 총, 끝 = 각 + 폭;
    const 큰 = 폭 > Math.PI ? 1 : 0;
    const p = (rr, a) => `${r1(cx + rr * Math.cos(a))},${r1(cy + rr * Math.sin(a))}`;
    out.push(`<path d="M ${p(R0, 각)} A ${R0} ${R0} 0 ${큰} 1 ${p(R0, 끝)} `
           + `L ${p(R1, 끝)} A ${R1} ${R1} 0 ${큰} 0 ${p(R1, 각)} Z" `
           + `fill="${계열색(k)}" fill-opacity="${진하기(k)}" stroke="#fff" stroke-width="1.2"/>`);
    각 = 끝;
  });
  if (sp["가운데"]) {
    const 줄 = wrap(sp["가운데"], 7);
    out.push(`<text x="${cx}" y="${cy}" font-size="12.5" font-weight="700" fill="#222" `
           + `text-anchor="middle" dominant-baseline="central">`
           + tspans(줄, cx, cy, 12.5) + `</text>`);
  }
  // 범례는 오른쪽에 값·비율과 함께 — 도넛은 조각에 글자를 넣으면 겹친다
  const lx = cx + R0 + 22;
  항목.forEach(([이름, v], k) => {
    const y = cy - (항목.length - 1) * 11 + k * 22;
    out.push(`<rect x="${lx}" y="${r1(y - 5)}" width="10" height="10" fill="${계열색(k)}" `
           + `fill-opacity="${진하기(k)}"/>`
           + `<text x="${lx + 15}" y="${r1(y)}" font-size="11" fill="#222" `
           + `dominant-baseline="central">${esc(이름)} ${esc(수(v))}`
           + `<tspan fill="#666"> (${(v / 총 * 100).toFixed(1)}%)</tspan></text>`);
  });
  const 너비 = Math.max(...항목.map(([n, v]) => 6.6 * w(n + " " + 수(v)) + 62), 90);
  return [lx + 너비, Math.max(2 * R0 + 16, 항목.length * 22 + 16), out.join("")];
};

function render(spec) {
  const fn = R[spec && spec.type];
  if (!fn) return `<div class="ph">알 수 없는 도식 유형: ${esc(spec && spec.type)}</div>`;
  const [W, H, body] = fn(spec);
  const pad = 6, cap = spec["캡션"] || "";
  const title = esc(spec["대체텍스트"] || cap || spec.type);
  return `<svg viewBox="${-pad} ${-pad} ${W + pad * 2} ${H + pad * 2}" width="${W + pad * 2}" `
       + `role="img" aria-label="${title}" xmlns="http://www.w3.org/2000/svg" `
       + `font-family="Pretendard, sans-serif"><title>${title}</title>${body}</svg>`;
}
function mount(el) {
  let spec; try { spec = JSON.parse(el.dataset.fig || "{}"); } catch (e) { return; }
  const cap = spec["캡션"] || "", note = spec["함의"] || "";
  el.innerHTML = (cap ? `<div class="cap">&lt; ${esc(cap)} &gt;</div>` : "")
               + render(spec)
               + (note ? `<div class="note">${esc(note)}</div>` : "");
}
function mountAll(root) {
  (root || document).querySelectorAll('.fr-fig[data-fig]').forEach(mount);
}
window.SVGFIG = { render, mount, mountAll, wrap };
mountAll();
})();
