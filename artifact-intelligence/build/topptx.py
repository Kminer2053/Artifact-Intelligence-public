#!/usr/bin/env python3
"""완성된 발표 슬라이드 HTML → 편집 가능한 PPTX 전환.

genre=slides 전용이다. 텍스트·표·도형·테두리는 **네이티브(편집 가능) 요소**로 옮기고,
도식·픽토그램 아이콘·이미지는 라이브 크롬에서 그 자리를 그대로 오려 그림으로 넣는다.
단 svgfig 차트(.fr-fig[data-fig] 의 bar·hbar·line·donut·stack)는 스펙을 같이 수확해 PowerPoint
네이티브 차트('데이터 편집' 가능)로 넣고, 못 넣으면 그 크롭 그림으로 돌아간다(build/pptx차트.py,
'26-09-29 도식 재설계 P3). 슬라이드 v2 부품(선차트·비율링)은 스펙을 싣지 않아 그림 그대로다.

읽는 눈은 build/화면읽기.py 하나다 — 크롬 열기·CDP 붙기·JS 평가·사각형 캡처를 그대로
빌려 쓴다(포트0 자동배정이라 측정 크롬끼리 안 겹치고, 크롬 행 회수도 그 코드에 들었다).
그래서 pdftoppm·PDF 왕복이 없다(핸드오프 PoC 의 '200dpi 페이지 렌더 후 크롭' 경로를
'그 네모만 직접 캡처'로 대체 — 함정 #1 크롬 행·#6 pdftoppm 경고가 통째로 사라진다).

이것은 **전환이지 생성이 아니다** — tohwpx 와 같은 사상이다. 완성된 규격(화면의 최종
배치·서체·색)을 PPTX 그릇에 그대로 옮긴다. 규칙으로 다시 만들지 않는다.

폰트 — Pretendard 는 PPTX 에 임베드할 수 없어 미설치 PC 에서 예측불가 대체가 됐다.
그래서 공공 Windows(발표 실물)에 100% 있는 **맑은 고딕**으로 박는다(사장님 판정
2026-08-16, 아래 FONT). eastAsia 축까지 같은 글꼴로 지정해 한글이 적용되게 한다.

글상자 규칙('26-09-28 보강, 근거 내부 기록·v2/build_pptx.md) —
맑은 고딕은 Pretendard 보다 한 줄 중간값 1.14배 넓어, 화면 좌표에 조각마다 박은 글상자가 서로
덮었다. 그래서 (1) 제 모양 없는 글 조각이 한 줄에 나란하면(강조 조각·숫자+단위) 글상자 하나의
런 여럿으로 묶고, (2) 안여백·가로/세로 맞춤을 계산값에서 옮기고, (3) 맑은 고딕 폭 표(_말굽_*)로
다시 재서 넘치면 빈 곳으로 넓히고 → 안여백을 헐고 → 그래도 모자라면 글자를 줄인다(_맞춤).
알약(큰 px 반경)은 가로세로가 같을 때만 타원, 나머지는 둥근 사각 adj 0.5.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 화면읽기·크롬찾기 가 같은 build/
import 화면읽기
from 크롬찾기 import 찾기, 띄우기

from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn

try:   # 네이티브 차트('26-09-29 P3). 모듈이 빠진 배포본이면 차트는 예전처럼 PNG 크롭으로 간다(죽지 않는다)
    import pptx차트 as _차트
except Exception as _e:   # noqa: BLE001
    _차트 = None
    print(f"[pptx] 네이티브 차트 모듈을 못 불렀다 — 차트는 그림으로 넣는다({type(_e).__name__})", file=sys.stderr)

FONT = "맑은 고딕"   # pptx 는 Windows PowerPoint 에서 열어 고치는 편집형이라 그 PC 에 100%
                    # 있는 공공 표준 글꼴로 박는다(사장님 판정 2026-08-16). Pretendard 는
                    # 임베드 불가라 미설치 PC 에서 예측불가 대체가 됐다. 화면(HTML)은 그대로
                    # Pretendard — pptx 만 맑은 고딕(획·비례가 가까워 인상 유지).
_캡처배율 = 3   # 크롭 스크린샷 해상도(CSS px × 3 ≈ 인쇄 해상도). clip.scale 로만 준다.

# ── 화면에서 뽑는 수확기 ────────────────────────────────────────────────────
# harvest.js v2 를 CDP 반환형으로 옮긴 것. 요소 좌표·서체·색에 더해 테두리·의사요소
# (::before/::after)·CSS content 텍스트까지 뽑는다 — 헤드 세로바(border-left)·구분선
# (border-bottom)·카드 상단바(border-top)·"출처: " 접두(content)가 전부 이 두 계열이라
# 사장님 실물 1차 확인('26-08-14)에서 이게 빠져 재작업했다. 크롭(도식·아이콘·이미지)은
# 자리(ax/ay 문서좌표)만 실어 보내고, 파이썬이 그 자리를 화면읽기._찍기 로 오려 담는다.
_수확코드 = r"""(function () {
  const INLINE = new Set(["B","STRONG","I","EM","SPAN","BR","SMALL","SUB","SUP","MARK","U","A"]);
  function clear(c) {                        // 칠이 없는가(투명·알파 0)
    if (!c || c === "transparent") return true;
    const m = c.match(/^rgba\(\s*\d+,\s*\d+,\s*\d+,\s*([\d.]+)\s*\)$/);
    if (m) return parseFloat(m[1]) === 0;
    const n = c.match(/\/\s*([\d.]+)(%?)\s*\)$/);
    return n ? parseFloat(n[1]) === 0 : false;
  }
  function borderSides(cs) {
    const out = {};
    for (const nm of ["Top","Right","Bottom","Left"]) {
      const w = parseFloat(cs["border"+nm+"Width"]) || 0;
      const st = cs["border"+nm+"Style"];
      if (w >= 0.25 && st !== "none" && st !== "hidden")
        out[nm[0].toLowerCase()] = { w: w, c: cs["border"+nm+"Color"] };
    }
    return Object.keys(out).length ? out : null;
  }
  function pseudoBox(el, which, pr) {
    const cs = getComputedStyle(el, which);
    if (!cs.content || cs.content === "none" || cs.content === "normal") return null;
    const m = cs.content.match(/^"(.*)"$/);
    if (m && m[1]) return null;              // 알맹이 있는 텍스트만 텍스트 쪽 — content:"" 는 장식
    if (cs.position !== "absolute") return null;
    let cb = el;
    while (cb && getComputedStyle(cb).position === "static") cb = cb.parentElement;
    const cbr = (cb || document.body).getBoundingClientRect();
    const W = parseFloat(cs.width) || 0, H = parseFloat(cs.height) || 0;
    if (W < 1 || H < 1) return null;
    let x = cbr.left, y = cbr.top;
    if (cs.left !== "auto") x = cbr.left + parseFloat(cs.left);
    else if (cs.right !== "auto") x = cbr.right - parseFloat(cs.right) - W;
    if (cs.top !== "auto") y = cbr.top + parseFloat(cs.top);
    else if (cs.bottom !== "auto") y = cbr.bottom - parseFloat(cs.bottom) - H;
    const br = cs.borderRadius || "0";
    return { kind: "box", x: x - pr.left, y: y - pr.top, w: W, h: H,
             bg: cs.backgroundColor, bgi: cs.backgroundImage === "none" ? "" : cs.backgroundImage,
             radius: parseFloat(br) || 0, radiusPct: /%/.test(br),
             opacity: parseFloat(cs.opacity), pseudo: 1 };
  }
  function pseudoText(el, which) {
    const c = getComputedStyle(el, which).content || "";
    const m = c.match(/^"(.*)"$/);
    return m ? m[1] : "";
  }
  function pseudoIsBox(el, which) {
    const c = getComputedStyle(el, which);
    if (!c.content || c.content === "none" || c.content === "normal") return false;
    const m = c.content.match(/^"(.*)"$/);
    if ((m && m[1]) || c.position !== "absolute") return false;
    return (parseFloat(c.width) || 0) >= 1 && (parseFloat(c.height) || 0) >= 1;
  }
  // 제 모양(칠·테두리·장식 가상요소)이 있는가 — 있으면 글 런으로 녹여 넣을 수 없는 조각이다
  function visual(el, cs) {
    return !clear(cs.backgroundColor) || (cs.backgroundImage && cs.backgroundImage !== "none")
      || !!borderSides(cs) || pseudoIsBox(el, "::before") || pseudoIsBox(el, "::after");
  }
  // 칠만 있는 인라인 조각(형광펜 강조 런) — 글 런에 a:highlight 로 녹일 수 있다('26-09-28 적대 검토 H3:
  // 데이터형×보고 목적의 런 강조가 묶음에서 빠져 글상자 3개·글자 크기 3가지로 갈라졌다)
  function hlOnly(el, cs) {
    return cs.display === "inline" && !clear(cs.backgroundColor) && cs.backgroundImage === "none"
      && !borderSides(cs) && !pseudoIsBox(el, "::before") && !pseudoIsBox(el, "::after");
  }
  function shown(el) { const c = getComputedStyle(el); return c.display !== "none" && c.visibility !== "hidden"; }
  // svgfig 차트 SVG 인가 — 그렇다면 {spec, tok, fpx}. 스펙은 data-fig 그대로(파이썬 pptx차트.표준 이 읽는다),
  // 색은 그 칸의 --fig-* 토큰(문서 설정 팔레트), 글자는 그려진 차트 글(fc)의 화면 px.
  const CHART = { bar: 1, hbar: 1, line: 1, donut: 1, stack: 1 };
  function chartOf(svg, r) {
    const fig = svg.parentElement;
    if (!fig || !fig.classList.contains("fr-fig") || fig.classList.contains("fr-img") || !fig.dataset.fig) return null;
    let spec = null;
    try { spec = JSON.parse(fig.dataset.fig); } catch (e) { return null; }
    if (!spec || typeof spec !== "object" || !Object.prototype.hasOwnProperty.call(CHART, spec.type)) return null;
    const cs = getComputedStyle(fig), tok = {};
    for (const k of ["chart", "chart-mid", "ink", "sub", "frame", "bg", "on-accent"])
      tok[k] = cs.getPropertyValue("--fig-" + k).trim();
    const vb = svg.viewBox && svg.viewBox.baseVal;
    const sc = vb && vb.width > 0 ? r.width / vb.width : 1;
    const fs = Array.from(svg.querySelectorAll("text")).map(t => parseFloat(t.getAttribute("font-size")))
      .filter(v => Number.isFinite(v) && v > 0);
    return { spec: spec, tok: tok, fpx: fs.length ? Math.min.apply(null, fs) * sc : null };
  }
  function directText(el) { return Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim()); }
  function onlyInline(el) { return Array.from(el.children).every(c => INLINE.has(c.tagName.toUpperCase())); }
  function isLeaf(el) { return directText(el) && onlyInline(el); }
  function fs(el) { return parseFloat(getComputedStyle(el).fontSize) || 16; }
  function sty(cs) {
    return { size: parseFloat(cs.fontSize) || 16, weight: +cs.fontWeight || 400, color: cs.color,
             ls: parseFloat(cs.letterSpacing) || 0, it: cs.fontStyle === "italic" ? 1 : 0,
             u: /underline/.test(cs.textDecorationLine || "") ? 1 : 0 };
  }
  function relOf(el, pr) {
    const r = el.getBoundingClientRect();
    return { x: r.left - pr.left, y: r.top - pr.top, w: r.width, h: r.height };
  }

  // ── 글 런 모으기 ── 한 글상자에 들어갈 글을 (글, 크기·굵기·색·자간) 런으로 모은다.
  // 절대배치 자식(번호 원 등)은 떼어 제 글상자로 보내고(det), 제 칠이 있는 줄 안 조각(칩)은
  // 글은 런에 두되 칠을 글 **밑에** 먼저 깐다(chips). 칠만 있는 display:inline 은 형광펜(hl).
  // 표 칸(cell)에서는 칩을 칸 밖 도형으로 뺀다 — 칸 채움이 불투명이라 밑에 깔 수 없다.
  function splitLines(tn, st, cx) {
    const s = tn.textContent, rg = document.createRange();
    let buf = "";
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (!/\s/.test(ch)) {
        rg.setStart(tn, i); rg.setEnd(tn, i + 1);
        const q = rg.getClientRects()[0];
        if (q && q.height > 0) {
          if (cx.sh.lb !== null && q.top > cx.sh.lb - 0.25 * q.height) {
            if (buf) cx.runs.push(Object.assign({ t: buf }, st));
            cx.runs.push({ t: "\n" }); buf = ""; cx.sh.lb = q.bottom;
          } else cx.sh.lb = cx.sh.lb === null ? q.bottom : Math.max(cx.sh.lb, q.bottom);
        }
      }
      buf += ch;
    }
    if (buf) cx.runs.push(Object.assign({ t: buf }, st));
  }
  function collect(node, cx) {
    for (const n of node.childNodes) {
      if (n.nodeType === 3) {
        if (!n.textContent) continue;
        cx.nodes.push(n);
        const pcs = getComputedStyle(n.parentElement);
        const st = sty(pcs);
        st.lh = parseFloat(pcs.lineHeight) || 0;   // 줄마다 줄 간격이 다를 수 있다(큰 숫자 줄·작은 단위 줄)
        if (cx.hl.length) st.hl = cx.hl[cx.hl.length - 1];
        if (cx.bal) splitLines(n, st, cx); else cx.runs.push(Object.assign({ t: n.textContent }, st));
      } else if (n.nodeType === 1) {
        const tg = n.tagName.toUpperCase();
        if (tg === "BR") { cx.runs.push({ t: "\n" }); continue; }
        if (tg === "SVG" || tg === "IMG" || !shown(n)) continue;
        const ncs = getComputedStyle(n);
        if (ncs.position === "absolute" || ncs.position === "fixed") { cx.det.push(n); continue; }
        let hl = false;
        if (visual(n, ncs)) {
          if (ncs.display === "inline" && !clear(ncs.backgroundColor) && ncs.backgroundImage === "none"
              && !borderSides(ncs) && !pseudoIsBox(n, "::before") && !pseudoIsBox(n, "::after")) {
            cx.hl.push(ncs.backgroundColor); cx.skip.push(n); hl = true;
          } else if (cx.cell) { cx.chips.push(n); continue; }
          else cx.chips.push(n);
        }
        const pb = pseudoText(n, "::before"), pa = pseudoText(n, "::after");
        if (pb) cx.runs.push(Object.assign({ t: pb }, sty(getComputedStyle(n, "::before"))));
        collect(n, cx);
        if (pa) cx.runs.push(Object.assign({ t: pa }, sty(getComputedStyle(n, "::after"))));
        if (hl) cx.hl.pop();
      }
    }
  }
  function sameSty(a, b) {
    return a.size === b.size && a.weight === b.weight && a.color === b.color && a.ls === b.ls
      && a.it === b.it && a.u === b.u && (a.hl || "") === (b.hl || "");
  }
  function norm(runs) {                      // 공백 접기·앞뒤 자르기·같은 모양 런 잇기
    const out = [];
    let sp = true;
    for (const r of runs) {
      if (r.t === "\n") {
        if (out.length && out[out.length - 1].t !== "\n") out[out.length - 1].t = out[out.length - 1].t.replace(/ +$/, "");
        while (out.length && !out[out.length - 1].t) out.pop();
        if (out.length && out[out.length - 1].t !== "\n") out.push({ t: "\n" });
        sp = true; continue;
      }
      let t = r.t.replace(/\s+/g, " ");
      if (sp) t = t.replace(/^ /, "");
      if (!t) continue;
      sp = t.endsWith(" ");
      const L = out[out.length - 1];
      if (L && L.t !== "\n" && sameSty(L, r)) { L.t += t; L.lh = Math.max(L.lh || 0, r.lh || 0); }
      else out.push(Object.assign({}, r, { t: t }));
    }
    while (out.length && out[out.length - 1].t === "\n") out.pop();
    if (out.length) { const L = out[out.length - 1]; L.t = L.t.replace(/ +$/, ""); if (!L.t) out.pop(); }
    return out;
  }
  function textRects(nodes) {
    const rg = document.createRange(), out = [];
    for (const n of nodes) {
      rg.selectNodeContents(n);
      for (const q of rg.getClientRects()) if (q.width > 0.5 && q.height > 0.5) out.push(q);
    }
    return out;
  }
  function lineBands(rects) {               // 글 네모들을 줄로 묶는다(세로로 절반 넘게 겹치면 같은 줄)
    const lines = [];
    for (const q of rects) {
      const L = lines.find(l => Math.min(l.b, q.bottom) - Math.max(l.t, q.top) > 0.5 * Math.min(l.b - l.t, q.height));
      if (L) { L.t = Math.min(L.t, q.top); L.b = Math.max(L.b, q.bottom); L.l = Math.min(L.l, q.left); L.r = Math.max(L.r, q.right); }
      else lines.push({ t: q.top, b: q.bottom, l: q.left, r: q.right });
    }
    return lines;
  }
  function gather(leaves, bal, pg) {
    const sh = { lb: null }, parts = [];
    for (const L of leaves) {
      const cx = { runs: [], nodes: [], det: [], chips: [], skip: [], hl: [], bal: bal, sh: sh, cell: false };
      const par = L.parentElement;
      if (leaves.length > 1) {                // 묶음 안 형광펜 조각 — 칠은 런 강조로, 도형으로는 안 깐다
        const lcs = getComputedStyle(L);
        if (visual(L, lcs) && hlOnly(L, lcs)) { cx.hl.push(lcs.backgroundColor); cx.skip.push(L); }
      }
      let pre = pseudoText(L, "::before"), post = pseudoText(L, "::after");
      if (pre) cx.runs.push(Object.assign({ t: pre }, sty(getComputedStyle(L, "::before"))));
      if (par && par !== pg && L === par.firstElementChild) {
        const pp = pseudoText(par, "::before");
        if (pp) cx.runs.unshift(Object.assign({ t: pp }, sty(getComputedStyle(par, "::before"))));
      }
      collect(L, cx);
      if (post) cx.runs.push(Object.assign({ t: post }, sty(getComputedStyle(L, "::after"))));
      if (par && par !== pg && L === par.lastElementChild) {
        const pp = pseudoText(par, "::after");
        if (pp) cx.runs.push(Object.assign({ t: pp }, sty(getComputedStyle(par, "::after"))));
      }
      cx.rects = textRects(cx.nodes);
      parts.push(cx);
    }
    return parts;
  }
  // ── 한 줄 묶음 ── 강조 조각(.runs > .r)·숫자+단위(.num)처럼 제 모양 없는 글 조각이 한 줄(또는
  // 줄 첫머리로 되돌아가며 접힌 줄)에 나란히 놓인 묶음을 찾는다. 조각마다 글상자를 따로 두면
  // 맑은 고딕이 Pretendard 보다 넓어(한 줄 중간값 1.14배) 앞 조각이 뒤 조각을 덮는다.
  function flatten(el, top) {
    const cs = getComputedStyle(el);
    if (!top && ((visual(el, cs) && !hlOnly(el, cs)) || cs.position === "absolute" || cs.position === "fixed")) return null;
    if (isLeaf(el)) return [el];
    if (directText(el)) return null;
    const kids = Array.from(el.children).filter(shown);
    if (!kids.length || kids.some(c => !c.textContent.trim())) return null;   // 아이콘·빈 조각이 끼면 묶지 않는다
    if (/grid/.test(cs.display)) return null;
    if (/^vertical/.test(cs.writingMode || "")) return null;   // 세로쓰기 줄(매트릭스 세로축)은 조각마다 따로 — 검토 M6
    const row = /flex/.test(cs.display) && cs.flexDirection === "row";
    if (!row && !kids.every(c => /^inline/.test(getComputedStyle(c).display))) return null;
    let out = [];
    for (const c of kids) { const f = flatten(c, false); if (!f) return null; out = out.concat(f); }
    return out;
  }
  function groupOk(parts, leaves, el) {
    const all = [].concat(...parts.map(p => p.rects));
    if (!all.length) return false;
    const sz = Math.max(...leaves.map(fs));
    const lines = lineBands(all);
    if (lines.length > 1) {                  // 접힌 줄은 첫머리(왼쪽 맞춤)나 가운데(가운데 맞춤)로 돌아가야 한다
      const l0 = Math.min(...lines.map(l => l.l)), c0 = (lines[0].l + lines[0].r) / 2;
      const left = lines.every(l => l.l <= l0 + 0.6 * sz);
      const mid = lines.every(l => Math.abs((l.l + l.r) / 2 - c0) <= 0.6 * sz);
      if (!left && !mid) return false;
    }
    for (let i = 1; i < parts.length; i++) {
      const a = parts[i - 1].rects, b = parts[i].rects;
      if (!a.length || !b.length) return false;
      const qa = a[a.length - 1], qb = b[0];
      const s2 = Math.min(fs(leaves[i - 1]), fs(leaves[i]));
      const same = Math.min(qa.bottom, qb.bottom) - Math.max(qa.top, qb.top) > 0.3 * Math.min(qa.height, qb.height);
      if (same) { const g = qb.left - qa.right; if (g < -0.5 * s2 || g > 0.8 * s2) return false; }
      else if (qb.top < qa.bottom - 0.3 * qb.height) return false;
      else if (qb.top - qa.bottom > 1.2 * s2) return false;   // 한 줄 넘게 떨어진 조각은 접힌 줄이 아니다(검토 M6)
    }
    return true;
  }
  function groupLeaves(el) {
    const f = flatten(el, true);
    return f && f.length >= 2 ? f : null;
  }
  // 글상자가 넓어질 수 있는 끝 — 가장 가까운 '제 모양 있는' 조상(또는 자기)의 네모. 안여백의 절반
  // 까지는 넘어가도 된다(최대 12px). 조상이 없으면 장(안여백 절반 안쪽).
  function limOf(el, pg, pr) {
    let a = el;
    while (a && a !== pg) {
      const c = getComputedStyle(a);
      if (!clear(c.backgroundColor) || (c.backgroundImage && c.backgroundImage !== "none") || borderSides(c)) break;
      a = a.parentElement;
    }
    const base = a || pg, c = getComputedStyle(base), r = base.getBoundingClientRect();
    const cap = base === pg ? 1e9 : 12;
    // 제 칠이 있는 글(칩·뱃지·알약) 자신이 끝이면 안여백의 1/4 까지만 남긴다 — 칩은 여백이 좁아
    // 절반을 남기면 맑은 고딕 폭(1.14배)에 글자가 20% 가까이 줄었다('운영 중' 뱃지).
    const share = base === el ? 0.25 : 0.5;
    const ins = s => Math.min((parseFloat(c["padding" + s]) || 0) * share, cap);
    return [r.left - pr.left + ins("Left"), r.top - pr.top + ins("Top"),
            r.width - ins("Left") - ins("Right"), r.height - ins("Top") - ins("Bottom")];
  }
  // 이웃한 글 조각 묶음 — 칩·아이콘이 섞인 가로 flex 줄에서, 제 모양 없는 글 조각이 둘 이상
  // 이어진 구간만 묶는다(예: '목표까지 | 7%p 이상 더 낮춤 | [산출]' → 앞 두 조각이 글상자 하나).
  function plainRuns(el, cs) {
    if (!(/flex/.test(cs.display) && cs.flexDirection === "row")) return [];
    if (/^vertical/.test(cs.writingMode || "")) return [];
    const out = [];
    let cur = [];
    const flush = () => {
      const lv = [].concat(...cur.map(c => c.f));
      if (cur.length >= 2 && lv.length >= 2) out.push({ kids: cur.map(c => c.el), leaves: lv });
      cur = [];
    };
    for (const c of Array.from(el.children).filter(shown)) {
      const f = c.textContent.trim() ? flatten(c, false) : null;
      if (f && f.length) cur.push({ el: c, f: f }); else flush();
    }
    flush();
    return out.map(q => {
      const rs = q.kids.map(k => k.getBoundingClientRect());
      const l = Math.min(...rs.map(v => v.left)), t = Math.min(...rs.map(v => v.top));
      const rr = Math.max(...rs.map(v => v.right)), b = Math.max(...rs.map(v => v.bottom));
      return Object.assign(q, { box: { left: l, top: t, right: rr, bottom: b, width: rr - l, height: b - t } });
    });
  }
  function textItem(el, cs, leaves, pg, pr, box) {
    let parts = gather(leaves, false, pg);
    let rects = [].concat(...parts.map(p => p.rects));
    if (leaves.length > 1 && !groupOk(parts, leaves, el)) return null;
    let lines = lineBands(rects);
    const tw = cs.textWrap || cs.textWrapStyle || "";
    // 여러 줄이면 브라우저가 끊은 자리를 강제 줄로 옮긴다 — 고르게 나눈 줄(text-wrap: balance)과
    // 조각 묶음(조각이 통째로 다음 줄로 넘어간 flex 줄)은 줄 모양이 뜻이라, PowerPoint 가 맑은
    // 고딕 폭으로 다시 접으면 '반납으로 연 / 1,550만 원' 처럼 강조 조각이 두 줄로 찢어진다.
    if (lines.length >= 2 && (/balance/.test(tw) || leaves.length > 1)) parts = gather(leaves, true, pg);
    let runs = [];
    parts.forEach((p, i) => {
      if (i > 0) {
        const a = parts[i - 1].rects, b = p.rects;
        let space = true;
        if (a.length && b.length) {
          const qa = a[a.length - 1], qb = b[0];
          const same = Math.min(qa.bottom, qb.bottom) - Math.max(qa.top, qb.top) > 0.3 * Math.min(qa.height, qb.height);
          space = !same || qb.left - qa.right > 0.12 * Math.min(fs(leaves[i - 1]), fs(leaves[i]));
        }
        if (space) runs.push(Object.assign({ t: " " }, sty(getComputedStyle(leaves[i - 1]))));
      }
      runs = runs.concat(p.runs);
    });
    runs = norm(runs);
    if (!runs.length) return null;
    const r = box || el.getBoundingClientRect();
    let u = r;
    if (rects.length) {
      const l = Math.min(...rects.map(q => q.left)), t = Math.min(...rects.map(q => q.top));
      const rr = Math.max(...rects.map(q => q.right)), b = Math.max(...rects.map(q => q.bottom));
      u = { left: l, top: t, right: rr, bottom: b, width: rr - l, height: b - t };
    }
    const P = box ? [0, 0, 0, 0] : ["Left", "Top", "Right", "Bottom"].map(s =>
      (parseFloat(cs["padding" + s]) || 0) + (parseFloat(cs["border" + s + "Width"]) || 0));
    let nl = lines.length;
    let lh = 0;
    for (const L of leaves) lh = Math.max(lh, parseFloat(getComputedStyle(L).lineHeight) || 0);
    if (!nl) nl = Math.max(1, lh ? Math.round(r.height / lh) : 1);
    // line-height: normal 이면 글 네모에서 줄 간격을 잰다 — n 줄 합친 높이 = (n−1)×간격 + 한 줄 높이
    if (!lh) lh = !rects.length ? 0 : nl >= 2 ? Math.max(1, (u.height - rects[0].height) / (nl - 1)) : u.height;
    // 가로 맞춤 — CSS(text-align, 가로 flex 의 justify-content) 먼저, 한 줄이면 실제 글 자리로 확인
    let al = cs.textAlign;
    if (al === "start" || al === "-webkit-left") al = "left";
    if (al === "end" || al === "-webkit-right") al = "right";
    if (al === "-webkit-center") al = "center";
    if (/flex/.test(cs.display) && cs.flexDirection === "row") {
      if (/center/.test(cs.justifyContent)) al = "center";
      else if (/flex-end|^end|right/.test(cs.justifyContent)) al = "right";
    }
    const cl = r.left + P[0], cr = r.right - P[2], ct = r.top + P[1], cb = r.bottom - P[3];
    const gl = u.left - cl, gr = cr - u.right, gt = u.top - ct, gb = cb - u.bottom;
    const pad = P.slice();
    if (nl === 1 && rects.length) {
      if (al !== "center" && al !== "right" && gl > 2 && gr > 2 && Math.abs(gl - gr) <= Math.max(2, 0.06 * (cr - cl))) al = "center";
      else if (al !== "center" && al !== "right" && gl > 3 && gr < 1.5) al = "right";
      if (al === "right" && gr > 2) pad[2] += gr;
      else if (al !== "center" && al !== "right" && gl > 2) pad[0] += gl;
    }
    // 세로 맞춤 — 글이 네모 가운데에 떠 있으면 가운데(칩·번호 칸·알약), 바닥에 붙었으면 아래
    let an = "t";
    if (rects.length) {
      if (gt > 1.5 && gb > 1.5 && Math.abs(gt - gb) <= Math.max(2, 0.08 * (cb - ct))) an = "ctr";
      else if (gb < 1.5 && gt > 4 && nl === 1) an = "b";
    }
    const first = runs.find(x => x.t !== "\n") || {};
    const item = { kind: "text", t: runs.map(x => x.t).join(""), runs: runs,
      size: Math.max(...runs.filter(x => x.size).map(x => x.size)), weight: first.weight || 400,
      color: first.color || "", align: al, anchor: an, lh: lh, lines: nl, pad: pad,
      tr: [u.left - pr.left, u.top - pr.top, u.width, u.height], lim: limOf(el, pg, pr),
      ff: cs.fontFamily, x: r.left - pr.left, y: r.top - pr.top, w: r.width, h: r.height,
      // 줄을 꺾지 않는 글(nowrap — 지표 큰 숫자 .num__v·단위 등) — PPTX 에서도 두 줄로 접지 않는다(r4 적대 검토 렌더 R4)
      nw: leaves.length > 0 && leaves.every(L => /^(nowrap|pre)$/.test(getComputedStyle(L).whiteSpace)) };
    return { item: item, det: [].concat(...parts.map(p => p.det)),
             chips: [].concat(...parts.map(p => p.chips)), skip: [].concat(...parts.map(p => p.skip)) };
  }
  // ── 모양 항목(가상요소 앞·칠·테두리) ── 요소 하나의 도형들. 뒤 가상요소는 따로 준다.
  function boxesOf(el, cs, pr) {
    const out = [], rel = relOf(el, pr);
    const bBox = pseudoBox(el, "::before", pr);
    if (bBox) out.push(bBox);
    const hasBg = cs.backgroundColor && cs.backgroundColor !== "rgba(0, 0, 0, 0)"
                  && cs.backgroundColor !== "transparent";
    const hasGrad = cs.backgroundImage && cs.backgroundImage !== "none";
    // 번짐 없는 윤곽 그림자(box-shadow: 0 0 0 Npx 색)는 고리 선으로 옮긴다
    let ring = null;
    const bs = cs.boxShadow || "";
    const rm = bs.match(/^((?:rgba?|color)\([^)]*\))\s+0px\s+0px\s+0px\s+([\d.]+)px$/);
    if (rm && parseFloat(rm[2]) > 0) ring = { c: rm[1], w: parseFloat(rm[2]) };
    if (hasBg || hasGrad || ring)
      out.push(Object.assign({ kind: "box", bg: (hasBg || hasGrad) ? cs.backgroundColor : "rgba(0, 0, 0, 0)",
        bgi: hasGrad ? cs.backgroundImage : "",
        radius: parseFloat(cs.borderRadius) || 0,
        radiusPct: /%/.test(cs.borderRadius || ""), opacity: 1, ring: ring }, rel));
    const bd = borderSides(cs);
    if (bd) out.push(Object.assign({ kind: "borders", bd,
      radius: parseFloat(cs.borderRadius) || 0, radiusPct: /%/.test(cs.borderRadius || "") }, rel));
    return out;
  }

  const pages = Array.from(document.querySelectorAll(".sl-page"));
  const out = [];
  for (const pg of pages) {
    const pr = pg.getBoundingClientRect();
    const pcs = getComputedStyle(pg);
    const items = [];
    const captured = [], detached = [], boxDone = new Set();
    // 이미 어떤 글상자에 담긴 글인가 — 단, 그 글상자가 떼어 낸(절대배치) 조각 안이면 아니다
    const covered = el => captured.some(a => a.contains(el) && !detached.some(d => a.contains(d) && d.contains(el)));
    items.push({ kind: "page", w: pr.width, h: pr.height,
                 bg: pcs.backgroundColor, bgi: pcs.backgroundImage });
    for (const which of ["::before","::after"]) {
      const b = pseudoBox(pg, which, pr);
      if (b) items.push(b);
    }
    const all = pg.querySelectorAll("*");
    for (const el of all) {
      const tag = el.tagName.toUpperCase();
      if (tag === "SCRIPT" || tag === "STYLE") continue;
      if (el.closest("svg") && tag !== "SVG") continue;
      if (el.closest("table") && tag !== "TABLE") continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const rel = { x: r.left - pr.left, y: r.top - pr.top, w: r.width, h: r.height };

      if (tag === "TABLE") {
        // 칸 글은 런으로(색·굵기 유지), 세로 맞춤·안여백은 계산값에서. 칸 안 칩(제 칠 있는 조각)은
        // 칸 채움 밑에 깔 수 없어, 표 **위에** 칠한 도형 + 제 글상자로 따로 얹는다.
        const extra = [];
        const rows = Array.from(el.rows).map(tr => Array.from(tr.cells).map(td => {
          const tcs = getComputedStyle(td);
          const tr2 = td.getBoundingClientRect();
          const cx = { runs: [], nodes: [], det: [], chips: [], skip: [], hl: [], bal: false, sh: { lb: null }, cell: true };
          collect(td, cx);
          for (const c of cx.chips.concat(cx.det)) {
            const ccs = getComputedStyle(c);
            const lv = isLeaf(c) ? [c] : groupLeaves(c);
            const ti = lv ? textItem(c, ccs, lv, pg, pr) : null;
            extra.push(...boxesOf(c, ccs, pr));
            if (ti) extra.push(ti.item);
            else cx.runs.push(Object.assign({ t: " " + c.textContent + " " }, sty(ccs)));
          }
          const runs = norm(cx.runs);
          return { t: runs.map(x => x.t).join(""), runs: runs,
                   w: tr2.width, h: tr2.height, th: td.tagName === "TH",
                   bg: tcs.backgroundColor, color: tcs.color,
                   size: parseFloat(tcs.fontSize), b: (+tcs.fontWeight) >= 600,
                   align: tcs.textAlign, va: tcs.verticalAlign, bd: borderSides(tcs),
                   pad: ["Left", "Top", "Right", "Bottom"].map(s => parseFloat(tcs["padding" + s]) || 0),
                   // 병합('26-09-29 표 재설계 P1) — 파이썬이 점유 격자로 진짜 열에 놓고 gridSpan·rowSpan 으로 합친다
                   cs: td.colSpan || 1, rs: td.rowSpan || 1 };
        }));
        // 행 높이는 행(tr)에서 잰다 — 첫 칸 높이는 세로 병합 칸이면 여러 행 높이다
        const rh = Array.from(el.rows).map(tr => tr.getBoundingClientRect().height);
        items.push(Object.assign({ kind: "table", rows, rh }, rel));
        items.push(...extra);
        continue;
      }
      // 도식(svgfig 주입 SVG)·이미지 — 자리만 실어 보내고 파이썬이 그 네모를 직접 찍는다.
      // svg 는 늘 진한 내용(도식·픽토, 테마색)이 있어 백지로 잡히면 실패로 본다(svg 표식).
      // img(첨부)는 밝을 수 있어 백지 검사에서 뺀다.
      if (tag === "SVG") {
        // 차트(.fr-fig[data-fig] 의 bar·hbar·line·donut·stack)면 스펙·팔레트 토큰·글자 크기를 같이 싣는다 —
        // 파이썬이 네이티브 차트로 넣고, 못 넣으면 이 크롭(PNG)으로 돌아간다('26-09-29 도식 재설계 P3).
        const ch = chartOf(el, r);
        items.push(Object.assign({ kind: "crop", svg: true, ax: r.left, ay: r.top }, ch ? { chart: ch } : {}, rel));
        continue;
      }
      if (tag === "IMG") {
        // AI 생성 그림(imageasset data-gen)이면 요청 id 를 싣는다 — 파이썬이 찍은 PNG 안에 'AI 생성물' 표기를 심는다(P3)
        const gen = ((el.closest && el.closest(".fr-img[data-gen]")) || { dataset: {} }).dataset.gen;
        items.push(Object.assign({ kind: "crop", ax: r.left, ay: r.top }, gen ? { gen } : {}, rel));
        continue;
      }

      if (!boxDone.has(el)) items.push(...boxesOf(el, cs, pr));

      // 글 — 한 요소의 글(자식이 인라인뿐)이나, 한 줄에 나란한 글 조각 묶음을 글상자 **하나**로.
      // <br>은 줄바꿈으로 옮긴다(공백 없이 지우면 "제목<br>부제" → "제목부제" 로 붙는다).
      if (!covered(el)) {
        const leaves = isLeaf(el) ? [el] : groupLeaves(el);
        const ti = leaves ? textItem(el, cs, leaves, pg, pr) : null;
        if (ti) {
          for (const c of ti.chips) {            // 줄 안 칩의 칠은 글보다 먼저(밑에) 깐다
            if (boxDone.has(c)) continue;
            items.push(...boxesOf(c, getComputedStyle(c), pr));
            const ab = pseudoBox(c, "::after", pr);
            if (ab) items.push(ab);
            boxDone.add(c);
          }
          for (const c of ti.skip) boxDone.add(c);
          items.push(ti.item);
          captured.push(el);
          detached.push(...ti.det);
        } else if (!leaves) {
          for (const q of plainRuns(el, cs)) {
            const t2 = textItem(el, cs, q.leaves, pg, pr, q.box);
            if (!t2) continue;
            for (const c of t2.chips) {
              if (boxDone.has(c)) continue;
              items.push(...boxesOf(c, getComputedStyle(c), pr));
              const ab = pseudoBox(c, "::after", pr);
              if (ab) items.push(ab);
              boxDone.add(c);
            }
            for (const c of t2.skip) boxDone.add(c);
            items.push(t2.item);
            captured.push(...q.kids);
            detached.push(...t2.det);
          }
        }
      }

      if (!boxDone.has(el)) {
        const aBox = pseudoBox(el, "::after", pr);
        if (aBox) items.push(aBox);
      }
    }
    out.push(items);
  }
  return JSON.stringify(out);
})()"""


# ── 색·칠·테두리 헬퍼 (build_pptx.py 포팅) ─────────────────────────────────
# 크롬 계산값의 색 두 꼴 — rgb()/rgba() 정수, 그리고 color-mix() 를 거친 color(srgb r g b [/ a])
# 0~1 실수. 한 곳에서 푼다: 예전엔 그라데이션(_grad_colors)만 둘째 꼴을 알고 단색(_rgb)은
# 몰라, 표 머리 틴트(--sl-thead: color-mix(… 13%, #fff))가 None → 흰색으로 나갔다
# ('26-09-28 P0 적대검토 L3, sl-charger-brief 4쪽). 화면읽기.py 의 색() 과 같은 식(×255 반올림).
_색꼴 = re.compile(
    r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?"
    r"|color\(srgb\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)(?:\s*/\s*([\d.]+)(%?))?\s*\)")


def _채널(m):
    """_색꼴 한 짝 → ((r, g, b), 알파). 알파가 없으면 1.0."""
    if m.group(1) is not None:
        rgb = tuple(int(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
    else:
        rgb = tuple(max(0, min(255, round(float(m.group(i)) * 255))) for i in (5, 6, 7))
        a = (float(m.group(8)) / (100 if m.group(9) else 1)) if m.group(8) is not None else 1.0
    return rgb, a


def _rgb(s):
    m = _색꼴.match((s or "").strip())
    if not m:
        return None
    rgb, a = _채널(m)
    # 완전 투명(alpha 0)은 **색이 아니다** — None 을 줘 대체(흰색·무채움)로 가게 한다.
    # 안 그러면 "rgba(0, 0, 0, 0)"(배경 없는 표 셀)이 앞 세 숫자로 검정이 돼 셀을
    # 불투명 검정으로 칠하고 어두운 글씨가 사라진다(적대검토 HIGH, '26-08-14 실측).
    if a == 0:
        return None
    return RGBColor(*rgb)


def _rgba_alpha(s):
    m = _색꼴.match((s or "").strip())
    return _채널(m)[1] if m else 1.0


def _grad_colors(bgi):
    # 크롬 computed style 은 color-mix() 결과를 color(srgb r g b) 0~1 실수로 직렬화한다
    return [RGBColor(*_채널(m)[0]) for m in _색꼴.finditer(bgi or "")]


def _no_line(shape):
    shape.line.fill.background()


def _set_grad(fill, colors, angle_deg=45):
    fill.gradient()
    stops = fill.gradient_stops
    stops[0].color.rgb = colors[0]
    stops[-1].color.rgb = colors[-1]
    try:
        fill.gradient_angle = angle_deg
    except Exception:
        pass


def _solid_alpha(sh, color, alpha):
    """반투명 단색 칠 — python-pptx 공개 API 엔 알파가 없어 spPr 에 직접 쓴다.
    스키마 순서(prstGeom→fill→ln) 때문에 기존 fill·ln 을 걷어내고 fill 을 먼저 넣는다."""
    spPr = sh._element.spPr
    for t in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:ln"):
        for e in spPr.findall(qn(t)):
            spPr.remove(e)
    fill = spPr.makeelement(qn("a:solidFill"), {})
    clr = spPr.makeelement(qn("a:srgbClr"), {"val": str(color)})
    a = spPr.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))})
    clr.append(a)
    fill.append(clr)
    spPr.append(fill)
    ln = spPr.makeelement(qn("a:ln"), {})
    ln.append(spPr.makeelement(qn("a:noFill"), {}))
    spPr.append(ln)   # ln 을 안 쓰면 테마 윤곽선이 상속된다


def _cell_borders(cell, bd, k):
    """표 셀 테두리 — tcPr 의 lnL·lnR·lnT·lnB (스키마상 fill 앞이라 맨 앞에 끼운다)"""
    tcPr = cell._tc.get_or_add_tcPr()
    order = [("l", "a:lnL"), ("r", "a:lnR"), ("t", "a:lnT"), ("b", "a:lnB")]
    made = []
    for key, tag in order:
        side = bd.get(key)
        if not side:
            continue
        ln = tcPr.makeelement(qn(tag), {"w": str(int(side["w"] * k * 12700)), "cap": "flat"})
        f = tcPr.makeelement(qn("a:solidFill"), {})
        c = tcPr.makeelement(qn("a:srgbClr"), {"val": str(_rgb(side["c"]) or RGBColor(0xD9, 0xD9, 0xD9))})
        f.append(c)
        ln.append(f)
        made.append(ln)
    for ln in reversed(made):
        tcPr.insert(0, ln)


_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER,
          "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY}


def _거의흴가(png_bytes, 문턱=0.995):
    """캡처가 사실상 백지(내용 없음)인가 — 48×48 로 줄여 흰 픽셀 비율로 본다. svg 도식·
    픽토는 늘 진한 테마색 내용이 있어 99.5% 이상 흰색이면 렌더 실패로 본다(적대검토 #7 —
    좌표가 밀려 빈 자리를 찍으면 유효한 흰 PNG 가 나와 png=None 고발을 우회했다)."""
    im = Image.open(io.BytesIO(png_bytes)).convert("L").resize((48, 48))
    d = im.tobytes()   # "L" 모드 = 픽셀당 1바이트(밝기). getdata() 는 Pillow 14 에서 사라진다.
    return sum(1 for v in d if v > 245) >= len(d) * 문턱


def _grad_parse(bgi):
    """계산값 background-image 첫 층 → (CSS 각도, [(RGBColor, 알파, 위치0~1|None)]).
    linear-gradient 만 각도를 읽는다(없으면 CSS 기본 180deg=위→아래). 그 밖(radial 등)은
    각도 None — 부른 쪽이 옛 45° 2색으로 둔다. 멈춤점 위치(%)가 없으면 고르게 나눈다."""
    s = (bgi or "").strip()
    if not s:
        return None, []
    깊이, 끝 = 0, len(s)
    for 자리, ch in enumerate(s):      # 첫 층만(쉼표로 이어진 여러 층 중 맨 위)
        if ch == "(":
            깊이 += 1
        elif ch == ")":
            깊이 -= 1
            if 깊이 == 0:
                끝 = 자리 + 1
                break
    첫 = s[:끝]
    각도 = None
    if 첫.startswith("linear-gradient"):
        m = re.match(r"linear-gradient\(\s*(-?[\d.]+)deg", 첫)
        방향 = {"to top": 0, "to right": 90, "to bottom": 180, "to left": 270,
                "to top right": 45, "to right top": 45, "to bottom right": 135, "to right bottom": 135,
                "to bottom left": 225, "to left bottom": 225, "to top left": 315, "to left top": 315}
        if m:
            각도 = float(m.group(1))
        else:
            m2 = re.match(r"linear-gradient\(\s*(to [a-z ]+?)\s*,", 첫)
            각도 = 방향.get(m2.group(1), 180) if m2 else 180
    멈춤 = []
    for m in _색꼴.finditer(첫):
        rgb, a = _채널(m)
        뒤 = re.match(r"\)?\s*(-?[\d.]+)%", 첫[m.end():])   # rgb() 짝은 닫는 괄호 앞에서 끝난다
        멈춤.append([RGBColor(*rgb), a, float(뒤.group(1)) / 100 if 뒤 else None])
    if 멈춤:
        if 멈춤[0][2] is None:
            멈춤[0][2] = 0.0
        if 멈춤[-1][2] is None:
            멈춤[-1][2] = 1.0
        자리 = 0
        while 자리 < len(멈춤):          # 위치 없는 멈춤점은 앞뒤 아는 값 사이에 고르게
            if 멈춤[자리][2] is None:
                뒤자리 = 자리
                while 멈춤[뒤자리][2] is None:
                    뒤자리 += 1
                앞값, 뒤값, 칸 = 멈춤[자리 - 1][2], 멈춤[뒤자리][2], 뒤자리 - 자리 + 1
                for 순 in range(자리, 뒤자리):
                    멈춤[순][2] = 앞값 + (뒤값 - 앞값) * (순 - 자리 + 1) / 칸
                자리 = 뒤자리
            자리 += 1
    return 각도, [tuple(x) for x in 멈춤]


def _칠_그라데이션(fill, bgi):
    """도형 채움에 CSS 그라데이션을 옮긴다 — 각도·멈춤점 수·위치·알파까지. 옮겼으면 True.
    linear 가 아니면(radial 등) 예전처럼 첫·끝 색 45° 로 둔다."""
    각도, 멈춤 = _grad_parse(bgi)
    if len(멈춤) < 2:
        return False
    if 각도 is None:
        _set_grad(fill, [c for c, _a, _p in 멈춤])
        return True
    fill.gradient()
    gs목록 = fill._xPr.find(qn("a:gradFill")).find(qn("a:gsLst"))
    for e in list(gs목록):
        gs목록.remove(e)
    for 색, 알파, 위치 in 멈춤:
        gs = gs목록.makeelement(qn("a:gs"), {"pos": str(int(round(max(0.0, min(1.0, 위치)) * 100000)))})
        clr = gs.makeelement(qn("a:srgbClr"), {"val": str(색)})
        if 알파 < 0.999:
            clr.append(clr.makeelement(qn("a:alpha"), {"val": str(int(알파 * 100000))}))
        gs.append(clr)
        gs목록.append(gs)
    # CSS 각도(0=아래→위, 시계 방향) → python-pptx gradient_angle(0=왼→오, 반시계): 450 − CSS
    try:
        fill.gradient_angle = (450 - 각도) % 360
    except Exception:
        pass
    return True


def _모양종류(rad, pct, w, h):
    """CSS 모서리 반경 → (도형 종류, 곡률 비율). 알약(border-radius: 999px 같은 큰 px 값)은
    **가로세로가 같을 때만** 타원이다 — 예전엔 반경 ≥ 짧은 변 절반이면 무조건 OVAL 이라, 253×44
    알약이 양끝 뾰족한 럭비공이 됐다(시제품 152건, '26-09-28 pptx_report C). 긴 알약은 둥근 사각
    adj 0.5(짧은 변 절반 반경 = 반원 끝). % 반경은 CSS 에서도 타원이라 50% 이상이면 OVAL."""
    미니 = min(w, h) or 1
    비율 = (rad / 100.0) if pct else (rad / 미니)
    정방 = abs(w - h) <= 0.1 * max(w, h, 1)
    if 비율 >= 0.5 and (pct or 정방):
        return MSO_SHAPE.OVAL, 0.5
    if rad > 0:
        return MSO_SHAPE.ROUNDED_RECTANGLE, min(비율, 0.5)
    return MSO_SHAPE.RECTANGLE, 0.0


def _도형(s, kind_adj, x, y, w, h):
    kind, adj = kind_adj
    sh = s.shapes.add_shape(kind, x, y, w, h)
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            sh.adjustments[0] = adj   # 실제 곡률(기본 16.7% 고정 탈피)
        except Exception:
            pass
    sh.shadow.inherit = False
    return sh


def _선만(sh, 색, 굵기pt):
    sh.fill.background()
    sh.line.color.rgb = 색
    sh.line.width = Pt(굵기pt)


# ── 맑은 고딕 글자 폭 (1/1000 em) ────────────────────────────────────────────
# PPTX 는 맑은 고딕으로 박는데(FONT) 화면 배치는 Pretendard 로 잰 것이라, 한 줄 글상자 폭 비가
# 중간값 1.14배·상위 10% 1.19배다(pptx_report A). 서버엔 맑은 고딕 파일이 없으니 폭을 표로 싣는다
# — Office for Mac 번들 malgun.ttf/malgunbd.ttf 의 advance 를 '26-09-28 PIL getlength 로 잰 값.
# 한글 음절·자모·한자·전각은 1.0em(표 밖 U+1100 이상 기본값), ASCII 32~126 과 자주 쓰는 기호만 싣는다.
_말굽_ASCII = {
    False: [int(v) for v in (
        "352 289 395 606 551 836 818 232 305 305 425 701 219 410 219 396 551 551 551 551 551 551 551 551 "
        "551 551 219 219 701 701 701 460 980 658 584 635 717 517 499 702 725 270 360 590 480 917 765 773 "
        "571 773 610 543 534 703 634 954 601 563 583 305 764 305 701 426 272 520 601 473 602 535 316 602 "
        "579 246 246 506 246 880 578 599 601 602 354 433 345 578 487 736 465 493 462 305 239 305 701").split()],
    True: [int(v) for v in (
        "352 323 476 608 580 875 857 282 358 358 456 719 262 414 262 439 580 580 580 580 580 580 580 580 "
        "580 580 262 262 719 719 719 452 979 704 637 639 746 539 524 722 770 310 431 645 512 964 798 776 "
        "615 776 654 566 583 731 671 1010 653 606 611 358 764 358 719 426 309 543 626 487 626 550 373 626 "
        "607 274 279 555 274 923 608 620 626 626 394 462 384 608 537 795 539 536 483 358 309 358 719").split()],
}
_말굽_기호 = {
    "·": (219, 262), "…": (740, 882), "→": (950, 1000), "←": (950, 1000), "↑": (950, 1000),
    "↓": (950, 1000), "↗": (950, 1000), "↘": (950, 1000), "⇒": (950, 1000), "—": (1026, 1026),
    "–": (513, 513), "‘": (231, 279), "’": (231, 279), "“": (379, 472), "”": (379, 472),
    "×": (701, 719), "※": (800, 800), "「": (571, 571), "」": (571, 571), "『": (517, 517),
    "』": (517, 517), "℃": (950, 950), "∼": (684, 714), "Ⅰ": (950, 1000), "Ⅱ": (950, 1000),
    "Ⅲ": (950, 1000), "〈": (542, 542), "〉": (542, 542), "《": (596, 596), "》": (596, 596),
    "【": (518, 518), "】": (518, 518), "•": (417, 417), "‧": (663, 663), "±": (701, 719),
    "÷": (701, 719), "≥": (701, 720), "≤": (701, 720), "≒": (684, 715), "°": (387, 389),
}


def _자폭(ch, 굵게):
    """맑은 고딕 글자 하나의 폭(em)."""
    o = ord(ch)
    if 32 <= o < 127:
        return _말굽_ASCII[굵게][o - 32] / 1000.0
    짝 = _말굽_기호.get(ch)
    if 짝:
        return 짝[1 if 굵게 else 0] / 1000.0
    return 1.0 if o >= 0x1100 else 0.6


def _줄글자(runs):
    """런 목록 → 강제 줄(\\n)마다 [(글자, 폭px)] — 크기·굵기·자간을 반영한 맑은 고딕 폭."""
    줄들, 지금 = [], []
    for r in runs:
        if r.get("t") == "\n":
            줄들.append(지금)
            지금 = []
            continue
        굵게 = r.get("weight", 400) >= 600
        크기, 자간 = r.get("size", 16), r.get("ls", 0) or 0
        for ch in r.get("t", ""):
            지금.append((ch, _자폭(ch, 굵게) * 크기 + 자간))
    줄들.append(지금)
    return 줄들


def _접은줄수(글자, 폭, 배율):
    """어절 단위 줄바꿈(어절이 줄보다 길면 글자 단위)을 했을 때의 줄 수 — PowerPoint 가 한글을
    띄어쓰기에서 끊는 기본값을 흉내 낸다(측정 보고서의 가정과 같다)."""
    줄, 현재, 낱말, 빈칸 = 1, 0.0, 0.0, False
    for ch, 너비 in 글자:
        너비 *= 배율
        if ch == " ":
            현재 += 너비
            낱말, 빈칸 = 0.0, True
            continue
        if 현재 + 너비 > 폭 + 0.01 and 현재 > 0:
            줄 += 1
            if 빈칸 and 낱말 + 너비 <= 폭:
                현재 = 낱말
            else:
                현재, 낱말 = 0.0, 0.0
            빈칸 = False
        현재 += 너비
        낱말 += 너비
    return 줄


def _여유(네모, 띠, 방향, 끝, 막힘):
    """글상자가 방향(r·l·d)으로 넓어질 수 있는 px — 담는 모양의 끝(끝)과, 같은 줄 띠(띠: 글
    세로 범위)에 걸친 다른 글·그림·표(막힘)의 가장자리 중 가까운 쪽까지."""
    x, y, w, h = 네모
    t0, t1 = 띠
    if 방향 in ("r", "l"):
        벽 = 끝
        for ox, oy, ow, oh in 막힘:
            겹 = min(t1, oy + oh) - max(t0, oy)
            if 겹 <= 0.3 * min(t1 - t0, oh):
                continue
            if 방향 == "r" and ox >= x + w - 1:
                벽 = min(벽, ox - 2)
            elif 방향 == "l" and ox + ow <= x + 1:
                벽 = max(벽, ox + ow + 2)
        return max(0.0, (벽 - (x + w)) if 방향 == "r" else (x - 벽))
    벽 = 끝
    for ox, oy, ow, oh in 막힘:
        if min(x + w, ox + ow) - max(x, ox) <= 1:
            continue
        if 방향 == "u":
            if oy + oh <= y + 1:
                벽 = max(벽, oy + oh + 2)
        elif oy >= y + h - 1:
            벽 = min(벽, oy - 2)
    return max(0.0, (y - 벽) if 방향 == "u" else (벽 - (y + h)))


def _맞춤(it, 막힘):
    """맑은 고딕 폭으로 다시 재서 글상자를 맞춘다(px 공간). 돌려주는 것: (x, y, w, h, 배율, 접기, 안여백).
    한 줄 상자: 넘치면 먼저 빈 곳으로 넓히고(맞춤 방향대로), 다음엔 안여백을 끝(lim)까지 헐고
    (칩·뱃지는 상자가 곧 칠이라 밖으로 못 넓힌다), 그래도 모자라면 글자를 줄인다
    (0.6배까지). 여러 줄 상자: 줄이 늘면 아래 빈 곳으로 키우고, 모자라면 글자를 줄인다(0.7배까지).
    PowerPoint 의 '넘치면 글자 줄이기'(normAutofit)는 **글을 고칠 때만** 다시 계산하므로(열 때는
    저장된 배율 그대로), 여는 순간의 모양은 여기서 미리 맞춰 둔다."""
    x, y, w, h = it["x"], it["y"], it["w"], it["h"]
    pl, pt_, pr_, pb = (it.get("pad") or [0, 0, 0, 0])[:4]
    줄들 = _줄글자(it["runs"])
    n = max(1, int(it.get("lines") or 1))
    tr = it.get("tr") or [x, y, w, h]
    띠 = (tr[1], tr[1] + max(tr[3], 1))
    lx, ly, lw, lh_ = it.get("lim") or [x, y, w, h]
    끝r, 끝l, 끝d = max(lx + lw, x + w), min(lx, x), max(ly + lh_, y + h)
    배율 = 1.0
    if n <= len(줄들):                                   # 한 줄(또는 강제 줄만 있는) 상자
        필요 = max(sum(너 for _c, 너 in 줄) for 줄 in 줄들) * 1.03 + 1
        안폭 = w - pl - pr_
        if 필요 > 안폭:
            부족 = 필요 - 안폭
            al = it.get("align", "left")
            if al == "center":
                # 가운데 맞춤은 양쪽 반씩 넓히되, 한쪽이 막혔으면 다른 쪽이 더 받는다(글 가운데가
                # 조금 옮겨 가는 편이 글자를 줄이는 것보다 낫다 — 오른쪽에 칩이 붙은 결론 줄 등).
                왼, 오 = (_여유((x, y, w, h), 띠, "l", 끝l, 막힘), _여유((x, y, w, h), 띠, "r", 끝r, 막힘))
                gl_, gr_ = min(왼, 부족 / 2), min(오, 부족 / 2)
                남 = 부족 - gl_ - gr_
                gl_, gr_ = gl_ + min(남, 왼 - gl_), gr_ + min(max(0.0, 남 - min(남, 왼 - gl_)), 오 - gr_)
                x, w = x - gl_, w + gl_ + gr_
            elif al == "right":
                g = min(부족, _여유((x, y, w, h), 띠, "l", 끝l, 막힘))
                x, w = x - g, w + g
            else:
                g = min(부족, _여유((x, y, w, h), 띠, "r", 끝r, 막힘))
                w += g
            안폭 = w - pl - pr_
            if 필요 > 안폭:
                최소l, 최소r = max(0.0, lx - x), max(0.0, (x + w) - (lx + lw))
                여l, 여r = max(0.0, pl - 최소l), max(0.0, pr_ - 최소r)
                부족 = 필요 - 안폭
                if al == "center":
                    dl = min(여l, 부족 / 2)
                    dr = min(여r, 부족 - dl)
                    dl = min(여l, 부족 - dr)
                elif al == "right":
                    dl, dr = min(여l, 부족), 0.0
                else:
                    dl, dr = 0.0, min(여r, 부족)
                pl, pr_ = pl - dl, pr_ - dr
                안폭 = w - pl - pr_
            if 필요 > 안폭:
                배율 = max(0.6, int(안폭 / 필요 * 100) / 100.0)
                # 띄어 쓴 글이면 줄이기 전에 두 줄로 접어 본다 — 담는 모양(lim) 안 위아래 빈 곳에 줄이 들면 글자 크기는 HTML
                # 그대로다(주관 판정 ⑧: 키운 짝카드·타일 글이 맑은 고딕 폭 때문에 ×0.85~0.9 로 줄었다). 칩·알약처럼 상자가 곧
                # 칠인 글은 lim 이 제 상자라 빈 곳이 없어 그대로 줄인다
                an = it.get("anchor", "t")
                # 줄을 꺾지 않는 글(nw — 지표 큰 숫자 '2억 4천만원')은 접지 않는다: HTML 은 한 줄인데 PPTX 가 '2억 / 4천만원'으로
                # 접었다(r4 적대 검토 렌더 R4 — bench14 a-s5 3장). 발표 숫자는 줄이 나뉘면 안 된다 — 줄여서 한 줄로 둔다
                if 배율 < 0.97 and len(줄들) == 1 and " " in (it.get("t") or "").strip() and an in ("t", "ctr") \
                        and not it.get("nw"):
                    m = _접은줄수(줄들[0], max(1.0, w - pl - pr_) / 1.03, 1.0)
                    줄높이 = it.get("lh") or 1.2 * (it.get("size") or 16)
                    더 = m * 줄높이 - (h - pt_ - pb)
                    아래 = _여유((x, y, w, h), 띠, "d", 끝d, 막힘)
                    위 = _여유((x, y, w, h), 띠, "u", min(ly, y), 막힘) if an == "ctr" else 0.0
                    if m >= 2 and 더 <= 아래 + 위:
                        더 = max(0.0, 더)
                        u_ = 0.0 if an == "t" else min(위, max(더 / 2, 더 - 아래))
                        return x, y - u_, w, h + 더, 1.0, True, [pl, pt_, pr_, pb]
        return x, y, w, h, 배율, False, [pl, pt_, pr_, pb]
    안폭 = max(1.0, w - pl - pr_)
    줄높이 = it.get("lh") or 1.2 * (it.get("size") or 16)
    안높이 = h - pt_ - pb

    def 들어가나(b):
        m = sum(_접은줄수(줄, 안폭, b) for 줄 in 줄들)
        return m <= n or m * 줄높이 * b <= 안높이 + 1, m

    됨, m = 들어가나(1.0)
    # 줄이 늘면 글자를 줄이기 전에 빈 곳으로 상자를 키운다 — 위 맞춤은 아래로, 가운데 맞춤은 위아래 반씩(한쪽이 막히면
    # 다른 쪽이 더), 아래 맞춤은 위로('26-09-30 bench14 주관 판정 ⑧: 키운 칸의 글 18%가 PPTX 에서 다시 줄었다 — HTML 에서
    # 잰 글자 크기를 그대로 옮기고 정말 넘칠 때만 줄인다). 가운데 맞춤 카드·타일 글이 줄던 몫이 컸다
    if not 됨:
        더 = m * 줄높이 - 안높이
        an = it.get("anchor", "t")
        아래 = _여유((x, y, w, h), 띠, "d", 끝d, 막힘) if an in ("t", "ctr") else 0.0
        위 = _여유((x, y, w, h), 띠, "u", min(ly, y), 막힘) if an in ("ctr", "b") else 0.0
        if an == "t" and 더 <= 아래:
            return x, y, w, h + 더, 1.0, True, [pl, pt_, pr_, pb]
        if an == "b" and 더 <= 위:
            return x, y - 더, w, h + 더, 1.0, True, [pl, pt_, pr_, pb]
        if an == "ctr" and 더 <= 아래 + 위:
            d_ = min(아래, 더 / 2)
            u_ = 더 - d_
            if u_ > 위:
                u_, d_ = 위, 더 - 위
            return x, y - u_, w, h + 더, 1.0, True, [pl, pt_, pr_, pb]
    b = 1.0
    while not 됨 and b > 0.705:
        b = round(b - 0.03, 2)
        됨, m = 들어가나(b)
    b = b if 됨 else max(b, 0.7)
    # 상자 높이가 줄 수 × 줄 간격보다 낮으면(화면에서도 살짝 넘쳐 있던 글) 아래 빈 곳만큼 키운다 —
    # 안 그러면 PowerPoint 가 글을 고치는 순간 '넘치면 줄이기'로 글자를 줄여 버린다.
    모자람 = m * 줄높이 * b - 안높이
    if 모자람 > 0.5 and it.get("anchor", "t") == "t":
        h += min(모자람, _여유((x, y, w, h), 띠, "d", 끝d, 막힘))
    return x, y, w, h, b, True, [pl, pt_, pr_, pb]


def _칩넓히기(items, page):
    """제 칠이 곧 상자인 한 줄 글(알약·칩)을 맑은 고딕 폭만큼 **칠과 함께** 넓힌다(제자리 고침) — 넓힐 자리는 그 칩을
    담은 모양(카드·패널) 안, 같은 줄의 다른 글·그림과 겹치지 않는 곳까지, 칩 폭의 15% 까지.
    HTML 알약은 Pretendard 글 폭 + 안여백이라 맑은 고딕(한글 1em)으로는 늘 모자라 _맞춤 이 글자를 ×0.85~0.9 로 줄였다
    (bench14 재조립 — 키운 알약 42px 가 PPTX 에서 36px, 주관 판정 ⑧ 'HTML 글자 크기를 그대로 옮긴다')."""
    모양 = [it for it in items if it["kind"] in ("box", "borders") and not (it["w"] >= page["w"] - 1 and it["h"] >= page["h"] - 1)]
    글 = [it for it in items if it["kind"] in ("text", "crop", "table")]
    for n, it in enumerate(items):
        if it["kind"] != "text" or int(it.get("lines") or 1) != 1:
            continue
        # 칩 = 바로 앞(세 항목 안)에 깐 칠 상자 가운데 글을 품고 글보다 조금만 큰 것(알약 = 칠한 span 안 글 span)
        칩 = next((b for b in reversed(items[max(0, n - 3):n]) if b["kind"] == "box"
                  and b["x"] <= it["x"] + 1 and b["x"] + b["w"] >= it["x"] + it["w"] - 1
                  and b["y"] <= it["y"] + 1 and b["y"] + b["h"] >= it["y"] + it["h"] - 1
                  and b["w"] <= it["w"] * 1.6 + 48 and b["h"] <= it["h"] * 2 + 24), None)
        if 칩 is None:
            continue
        pl, _, pr_, _ = (it.get("pad") or [0, 0, 0, 0])[:4]
        필요 = max(sum(너 for _c, 너 in 줄) for 줄 in _줄글자(it["runs"])) * 1.03 + 1
        lx, ly, lw, lh_ = it.get("lim") or [it["x"], it["y"], it["w"], it["h"]]
        부족 = 필요 - max(it["w"] - pl - pr_, lw - pl - pr_)
        if 부족 <= 0.5 or 부족 > 0.3 * it["w"]:
            continue
        부족 = 필요 - (it["w"] - pl - pr_) + 2          # 글상자 자체를 필요 폭까지(끝 lim 도 같이 넓힌다)
        cx, cy = it["x"] + it["w"] / 2, it["y"] + it["h"] / 2
        담은 = [m for m in 모양 if m is not 칩 and m["x"] <= cx <= m["x"] + m["w"] and m["y"] <= cy <= m["y"] + m["h"]
              and m["w"] * m["h"] > it["w"] * it["h"] * 1.5]
        if not 담은:
            continue
        벽 = min(담은, key=lambda m: m["w"] * m["h"])
        왼끝, 오른끝 = 벽["x"] + 4, 벽["x"] + 벽["w"] - 4
        for o in 글:
            if o is it or not (min(it["y"] + it["h"], o["y"] + o["h"]) - max(it["y"], o["y"]) > 1):
                continue
            if o["x"] >= it["x"] + it["w"] - 1:
                오른끝 = min(오른끝, o["x"] - 2)
            elif o["x"] + o["w"] <= it["x"] + 1:
                왼끝 = max(왼끝, o["x"] + o["w"] + 2)
        오, 왼 = max(0.0, 오른끝 - (it["x"] + it["w"])), max(0.0, it["x"] - 왼끝)
        if 오 + 왼 < 부족:
            continue
        if it.get("align") == "center" and 왼 >= 부족 / 2 and 오 >= 부족 / 2:
            dl, dr = 부족 / 2, 부족 / 2
        else:
            dr = min(오, 부족)
            dl = 부족 - dr
        for q in (칩, it):
            q["x"], q["w"] = q["x"] - dl, q["w"] + dl + dr
        if it.get("lim"):
            it["lim"] = [lx - dl, ly, lw + dl + dr, lh_]
        if it.get("tr"):
            it["tr"] = [it["tr"][0] - dl, it["tr"][1], it["tr"][2] + dl + dr, it["tr"][3]]


def _런쓰기(p, r_, 배율, k):
    """문단 p 에 런 하나를 쓴다 — 크기·굵기·기울임·밑줄·색(알파)·자간·형광펜·동아시아 글꼴."""
    r = p.add_run()
    r.text = r_.get("t", "")
    r.font.name = FONT
    r.font.size = Pt(max(1.0, round(r_.get("size", 16) * 배율 * k * 2) / 2))
    r.font.bold = r_.get("weight", 400) >= 600
    if r_.get("it"):
        r.font.italic = True
    if r_.get("u"):
        r.font.underline = True
    c = _rgb(r_.get("color", ""))
    if c is not None:
        r.font.color.rgb = c
    rPr = r._r.get_or_add_rPr()
    알파 = _rgba_alpha(r_.get("color", ""))
    if c is not None and 알파 < 0.999:      # 글자 알파(0.82·0.7 같은 옅은 글)
        clr = rPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
        clr.append(clr.makeelement(qn("a:alpha"), {"val": str(int(알파 * 100000))}))
    자간 = (r_.get("ls", 0) or 0) * 배율 * k
    if abs(자간) >= 0.01:
        rPr.set("spc", str(int(round(자간 * 100))))
    형광 = _rgb(r_.get("hl", "")) if r_.get("hl") else None
    if 형광 is not None:                   # 스키마 순서: 채움 뒤·latin 앞
        hl = rPr.makeelement(qn("a:highlight"), {})
        hl.append(hl.makeelement(qn("a:srgbClr"), {"val": str(형광)}))
        latin = rPr.find(qn("a:latin"))
        if latin is not None:
            latin.addprevious(hl)
        else:
            rPr.append(hl)
    rPr.append(rPr.makeelement(qn("a:ea"), {"typeface": FONT}))   # 한글 글꼴은 eastAsia 축도 지정해야 적용된다
    return r


def _문단채우기(p, runs, 배율, k):
    for r_ in runs:
        if r_.get("t") == "\n":
            p.add_line_break()
        elif r_.get("t"):
            _런쓰기(p, r_, 배율, k)


_세로 = {"t": MSO_ANCHOR.TOP, "ctr": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}
_표무늬없음 = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"   # 'No Style, No Grid' — 준 선·채움만 보인다


# ── 수확 (라이브 크롬) ──────────────────────────────────────────────────────
def 수확(html경로) -> tuple[list | None, str | None]:
    """HTML 을 머리 없는 크롬으로 열어 페이지별 요소를 뽑고, 크롭 자리는 그 자리 그대로
    찍어 png(base64)를 실어 돌려준다. 실패는 (None, 사유)."""
    크롬 = 찾기()   # 못 찾아도 죽지 않는다(WP-S8) — 서버가 이 요청 하나로 안 내려가게
    if not 크롬:
        return None, "크롬을 찾지 못해 PPTX 를 뽑을 수 없습니다"
    with tempfile.TemporaryDirectory() as tmp:
        # 부모가 죽어도 크롬이 고아로 남지 않게 크롬찾기.띄우기 한 손으로 띄운다('26-10-01 R3)
        p = 띄우기(
            [크롬, "--headless", "--disable-gpu", "--remote-debugging-port=0",
             f"--user-data-dir={tmp}/u", "--no-first-run", "--no-default-browser-check",
             Path(html경로).resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 치울=tmp)
        try:
            붙을곳 = None
            for _ in range(160):
                try:
                    항 = int((Path(tmp) / "u" / "DevToolsActivePort")
                             .read_text().splitlines()[0])
                    j = 화면읽기.디버깅목록(항, timeout=1)   # http 전용 열기('26-10-01)
                    쓸것 = [t for t in j if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                    if 쓸것:
                        붙을곳 = 쓸것[0]["webSocketDebuggerUrl"]
                        break
                except Exception:
                    pass
                time.sleep(0.25)
            if not 붙을곳:
                return None, "크롬 디버깅에 못 붙었습니다"
            # 인쇄 매체를 **수확 전에 따로** 앉힌다. 이걸 수확 eval 의 앞선것으로 같이 보내면
            # 미디어 재적용이 그 eval 안에서 아직 정착 안 된 배치를 재게 해 좌표가 밀린다(도식
            # y 3345→3194 로 밀려 5쪽 도식이 백지로 캡처됨, '26-08-14 사장님 실물). 화면에는
            # 발표 조작 UI(present.js: 앞뒤·PDF·목차)가 같이 뜨는데 그건 문서가 아니다(@media
            # print 에서 display:none). PDF 도 같은 매체라 결과가 맞는다.
            화면읽기._평가(붙을곳, "1", [("Emulation.setEmulatedMedia", {"media": "print"})])
            time.sleep(1.3)   # 글꼴·자간·svgfig 도식·미디어 전환이 다 앉을 때까지
            pages = json.loads(화면읽기._평가(붙을곳, _수확코드, []))   # 미디어 재적용 없이 잰다
            # 도식·아이콘·이미지 — 그 네모만 그대로 찍는다(배율 3, 화면읽기._찍기 와 같은 눈).
            for items in pages:
                for it in items:
                    if it.get("kind") == "crop":
                        # **직접 clip 캡처 — setDeviceMetricsOverride 를 안 쓴다.** 화면읽기._찍기 는
                        # 캡처마다 그걸 걸어 뷰포트를 바꿔 문서를 리플로우시켰다: 아래쪽 장일수록
                        # 좌표가 밀려(도식 y 3194→3345) 수확 때 잰 자리엔 백지만 잡혔다('26-08-14
                        # 사장님 실물에서 5쪽 도식이 빈 것으로 드러남). 레이아웃을 안 건드리면 수확
                        # 좌표가 그대로 유효하다 — clip.scale 로만 해상도를 올린다.
                        받 = 화면읽기._명령(붙을곳, "Page.captureScreenshot", {
                            "format": "png", "captureBeyondViewport": True,
                            "clip": {"x": it["ax"], "y": it["ay"], "width": it["w"],
                                     "height": it["h"], "scale": _캡처배율}})
                        it["png"] = (받 or {}).get("data")
            return pages, None
        except (Exception, SystemExit) as e:
            # 화면읽기 는 웹소켓 끊김·수확 JS 예외를 **SystemExit**(BaseException)로 던진다.
            # 그게 위로 새면 동기 호출자(api.부르기·serve._post·verify_all)의 `except Exception`
            # 을 뚫고 ok:False 계약이 깨진다 — 스레드 서버는 워커만 죽어 응답이 안 나가고
            # verify_all 은 통째로 중단된다(적대검토 MEDIUM). 여기서 붙잡아 실패로 돌린다.
            return None, f"수확 중 크롬이 끊겼습니다: {str(e)[:80]}"
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


# ── 조립 (수확 → PPTX) ─────────────────────────────────────────────────────
def _조립(pages, tmpdir):
    """수확한 페이지들을 960×540pt 슬라이드로 조립한다. 크롭 png 가 비면(도식을 못
    옮겼으면) 조용히 넘기지 않고 목록에 담아 돌려준다 — 부른 쪽이 실패로 고발한다."""
    prs = Presentation()
    prs.slide_width = Emu(12192000)    # 960pt
    prs.slide_height = Emu(6858000)    # 540pt
    blank = prs.slide_layouts[6]
    빠진크롭 = []

    for pageno, items in enumerate(pages, 1):
        page = next(it for it in items if it["kind"] == "page")
        k = 960.0 / page["w"]          # px → pt
        s = prs.slides.add_slide(blank)

        # 페이지 배경 — 슬라이드 배경 속성은 뷰어가 그라데이션을 무시하는 일이 있어
        # (실측: 검정) 전면 사각형 도형으로 깐다. 도형 gradFill 은 표준대로 먹는다.
        cols = _grad_colors(page.get("bgi", ""))
        bgc = _rgb(page.get("bg", ""))
        if len(cols) >= 2 or bgc is not None:
            bgsh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0,
                                      prs.slide_width, prs.slide_height)
            if not (len(cols) >= 2 and _칠_그라데이션(bgsh.fill, page.get("bgi", ""))):
                bgsh.fill.solid()
                bgsh.fill.fore_color.rgb = bgc or RGBColor(0xFF, 0xFF, 0xFF)
            _no_line(bgsh)
            bgsh.shadow.inherit = False

        _칩넓히기(items, page)
        # 맞춤용 막힘 — 이 장의 글상자·그림·표 네모(px). 글상자는 맞춘 뒤 새 네모로 바꿔 둔다.
        글자리 = {id(it): [it["x"], it["y"], it["w"], it["h"]]
                  for it in items if it["kind"] in ("text", "crop", "table")}
        # 칠한 도형·테두리 틀도 막힘이다(글상자가 옆 카드·패널 안으로 넓어지면 안 된다). 단 글을
        # **담는** 도형(글상자 가운데를 품는 것)은 막힘이 아니라 끝(lim)이 맡는다. 가상요소 장식은
        # 알파 0.3 이상만(표지의 옅은 원 같은 배경 무늬는 글 뒤에 깔린 것이다), 요소 칠은 옅어도
        # 막힘이다(반투명 패널). 장 전체 배경은 뺀다.
        모양자리 = [[it["x"], it["y"], it["w"], it["h"]] for it in items
                    if (it["kind"] == "borders" or (it["kind"] == "box" and (
                        _rgba_alpha(it.get("bg", "")) * it.get("opacity", 1) >= (0.3 if it.get("pseudo") else 0.02)
                        or it.get("bgi"))))
                    and not (it["w"] >= page["w"] - 1 and it["h"] >= page["h"] - 1)]

        for idx, it in enumerate(items):
            kind = it["kind"]
            if kind == "page":
                continue
            x, y, w, h = (Pt(it["x"] * k), Pt(it["y"] * k),
                          Pt(max(it["w"] * k, 1)), Pt(max(it["h"] * k, 1)))

            if kind == "box":
                # 반경을 '짧은 변 대비 비율'로 환산한다 — %는 /100, px는 짧은 변으로 나눈다.
                # 옛 코드는 "20%"의 20 을 px 처럼 min(w,h)/2 와 견줘 작은 상자를 타원으로
                # 오판했다(적대검토 LOW). 타원은 가로세로가 같은 원·% 반경만(_모양종류).
                종류 = _모양종류(it["radius"], it.get("radiusPct"), it["w"], it["h"])
                sh = _도형(s, 종류, x, y, w, h)
                cols = _grad_colors(it.get("bgi", ""))
                alpha = _rgba_alpha(it.get("bg", "")) * it.get("opacity", 1)
                if len(cols) >= 2:
                    if not _칠_그라데이션(sh.fill, it.get("bgi", "")):
                        _set_grad(sh.fill, cols)
                    _no_line(sh)
                elif alpha < 0.999:
                    c = _rgb(it.get("bg", "")) or RGBColor(0xFF, 0xFF, 0xFF)
                    _solid_alpha(sh, c, alpha)     # fill·ln 을 스스로 정리한다
                else:
                    c = _rgb(it.get("bg", "")) or RGBColor(0xFF, 0xFF, 0xFF)
                    sh.fill.solid()
                    sh.fill.fore_color.rgb = c
                    _no_line(sh)
                sh.shadow.inherit = False
                고리 = it.get("ring")
                if 고리 and _rgb(고리.get("c", "")) is not None:
                    # 번짐 없는 윤곽 그림자 = 바깥 고리. PPTX 선은 도형 가장자리 가운데에 그려져
                    # 굵기 절반만큼 바깥으로 키운 같은 모양에 선만 준다.
                    q = 고리["w"] / 2
                    종류2 = _모양종류(it["radius"] + q if not it.get("radiusPct") else it["radius"],
                                    it.get("radiusPct"), it["w"] + 2 * q, it["h"] + 2 * q)
                    링 = _도형(s, 종류2, Pt((it["x"] - q) * k), Pt((it["y"] - q) * k),
                              Pt((it["w"] + 2 * q) * k), Pt((it["h"] + 2 * q) * k))
                    _선만(링, _rgb(고리["c"]), 고리["w"] * k)

            elif kind == "borders":
                bd = it["bd"]
                px, py, pw, ph = it["x"], it["y"], it["w"], it["h"]
                같은테 = (len(bd) == 4 and it.get("radius", 0) > 0
                          and len({round(v["w"], 2) for v in bd.values()}) == 1
                          and len({str(_rgb(v["c"])) for v in bd.values()}) == 1)
                if 같은테 and _rgb(bd["t"]["c"]) is not None:
                    # 둥근 요소의 네 변 같은 테두리 — 변마다 직사각 조각을 깔면 원형 점이 네모 틀이
                    # 된다(현행 덱 32건). 같은 둥근 모양에 선만 준다(선 가운데 = 테두리 가운데).
                    q = bd["t"]["w"] / 2
                    종류 = _모양종류(max(it["radius"] - q, 0) if not it.get("radiusPct") else it["radius"],
                                   it.get("radiusPct"), pw - 2 * q, ph - 2 * q)
                    테 = _도형(s, 종류, Pt((px + q) * k), Pt((py + q) * k),
                              Pt(max((pw - 2 * q) * k, 0.5)), Pt(max((ph - 2 * q) * k, 0.5)))
                    _선만(테, _rgb(bd["t"]["c"]), bd["t"]["w"] * k)
                    continue
                for key, bx, by, bw, bh in (
                        ("t", px, py, pw, bd.get("t", {}).get("w", 0)),
                        ("b", px, py + ph - bd.get("b", {}).get("w", 0), pw, bd.get("b", {}).get("w", 0)),
                        ("l", px, py, bd.get("l", {}).get("w", 0), ph),
                        ("r", px + pw - bd.get("r", {}).get("w", 0), py, bd.get("r", {}).get("w", 0), ph)):
                    if key not in bd:
                        continue
                    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                            Pt(bx * k), Pt(by * k),
                                            Pt(max(bw * k, 0.5)), Pt(max(bh * k, 0.5)))
                    sh.fill.solid()
                    sh.fill.fore_color.rgb = _rgb(bd[key]["c"]) or RGBColor(0xD9, 0xD9, 0xD9)
                    _no_line(sh)
                    sh.shadow.inherit = False

            elif kind == "crop":
                # 차트 스펙이 실렸으면 네이티브 차트('데이터 편집' 되는 PowerPoint 차트)로 먼저 넣는다.
                # 모르는 유형·그릴 값 없음·예외면 False → 아래 PNG 크롭 그대로('26-09-29 도식 재설계 P3).
                if it.get("chart") and _차트 is not None and _차트.넣기(s, it["chart"], x, y, w, h, k):
                    continue
                b64 = it.get("png")
                png = base64.b64decode(b64) if b64 else None
                # svg 크롭(도식·픽토)이 백지로 잡히면 렌더 실패다 — 조용히 빈 그림을 심지
                # 않고 고발한다(적대검토 #7: '26-08-14 사장님 실물에서 5쪽 도식이 백지로
                # 나갔다). img(첨부)는 밝을 수 있어 백지 검사에서 뺀다.
                if not png or (it.get("svg") and _거의흴가(png)):
                    빠진크롭.append(f"{pageno}쪽 도식/그림")
                    continue
                if it.get("gen"):
                    # AI 생성 그림 — 발표 파일의 그림(ppt/media) 안에도 'AI 생성물' 표기(PNG 글 조각)를 심는다(P3 '26-09-30,
                    # 주관 판정). 화면에서 다시 찍은 PNG 라 자산의 조각이 따라오지 않았다(P2 실측 media 0/2).
                    try:
                        import imageasset as _ia
                        png = _ia.AI표기심기(png, str(it["gen"]), "") or png
                    except Exception as exc:
                        print(f"[topptx] AI 생성 그림 표기를 못 심었다 — {type(exc).__name__}", file=sys.stderr)
                fn = os.path.join(tmpdir, f"crop-{pageno}-{idx}.png")
                with open(fn, "wb") as f:
                    f.write(png)
                s.shapes.add_picture(fn, x, y, w, h)

            elif kind == "text":
                # 한 요소(또는 한 줄 조각 묶음)의 글 = 글상자 하나, 모양 다른 조각 = 런 여럿.
                # 안여백·가로/세로 맞춤은 수확 계산값에서 옮기고, 맑은 고딕 폭으로 다시 재서
                # 넘치면 빈 곳으로 넓히거나 글자를 줄인다(_맞춤).
                if not it.get("runs"):
                    it["runs"] = [{"t": it.get("t", ""), "size": it.get("size", 16),
                                   "weight": it.get("weight", 400), "color": it.get("color", "")}]
                cx_, cy_ = it["x"] + it["w"] / 2, it["y"] + it["h"] / 2
                막힘 = [v for 열쇠, v in 글자리.items() if 열쇠 != id(it)] + [
                    m for m in 모양자리 if not (m[0] <= cx_ <= m[0] + m[2] and m[1] <= cy_ <= m[1] + m[3])]
                fx, fy, fw, fh, 배율, 접기, 안여백 = _맞춤(it, 막힘)
                글자리[id(it)] = [fx, fy, fw, fh]
                tb = s.shapes.add_textbox(Pt(fx * k), Pt(fy * k), Pt(max(fw * k, 1)), Pt(max(fh * k, 1)))
                tf = tb.text_frame
                pl, pt_, pr_, pb = 안여백
                tf.margin_left, tf.margin_top = Pt(pl * k), Pt(pt_ * k)
                tf.margin_right, tf.margin_bottom = Pt(pr_ * k), Pt(pb * k)
                # HTML 에서 한 줄이던 텍스트는 PPT 에서도 꺾지 않는다 — 대신 넘칠 폭을 미리 재서
                # 맞춘다(_맞춤). 여러 줄은 접고 '넘치면 글자 줄이기'를 켜 둔다(고칠 때 PowerPoint 가
                # 다시 맞춘다).
                tf.word_wrap = 접기
                tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE if 접기 else MSO_AUTO_SIZE.NONE
                tf.vertical_anchor = _세로.get(it.get("anchor", "t"), MSO_ANCHOR.TOP)
                # 강제 줄(브라우저가 끊은 자리·<br>)마다 문단 하나 — 줄마다 줄 간격이 다를 수 있어서다
                # (큰 숫자 줄 아래 작은 단위 줄을 큰 줄 간격으로 내리면 아래 글과 겹친다).
                줄묶음, 지금 = [], []
                for r_ in it["runs"]:
                    if r_.get("t") == "\n":
                        줄묶음.append(지금)
                        지금 = []
                    else:
                        지금.append(r_)
                줄묶음.append(지금)
                for 순번, 줄 in enumerate(줄묶음):
                    p = tf.paragraphs[0] if 순번 == 0 else tf.add_paragraph()
                    p.alignment = _ALIGN.get(it.get("align", "left"), PP_ALIGN.LEFT)
                    줄간격 = (max((r_.get("lh") or 0) for r_ in 줄) if 줄 else 0) or it.get("lh")
                    if 줄간격:
                        p.line_spacing = Pt(줄간격 * 배율 * k)
                    _문단채우기(p, 줄, 배율, k)

            elif kind == "table":
                rows = it["rows"]
                # 점유 격자('26-09-29 표 재설계 P1, critic_impl §4) — 병합 칸(cs·rs)이 덮은 자리를
                # 건너뛰어 칸마다 진짜 열을 찾는다. 예전엔 열 수 = 가장 긴 행의 칸 수, 열폭 = 첫 행
                # 칸 폭이라 colspan 이 있으면 칸이 한 칸씩 밀리고 오른쪽이 빈 흰 칸이 됐다.
                덮임, 자리 = set(), []
                for i2, row in enumerate(rows):
                    j, 줄 = 0, []
                    for cell in row:
                        while (i2, j) in 덮임:
                            j += 1
                        가 = max(1, int(cell.get("cs") or 1))
                        세 = max(1, min(int(cell.get("rs") or 1), len(rows) - i2))
                        덮임 |= {(i2 + a, j + b) for a in range(세) for b in range(가)} - {(i2, j)}
                        줄.append((j, 가, 세, cell))
                        j += 가
                    자리.append(줄)
                ncol = max([j + 가 for 줄 in 자리 for (j, 가, 세, _c) in 줄] + [1])
                gf = s.shapes.add_table(len(rows), ncol, x, y, w, h)
                tbl = gf.table
                # 기본 표 무늬(Medium Style 2: 머리 줄·띠 줄)를 떼어 낸다 — 칸 채움·테두리는
                # 화면 계산값으로 다 준다. 무늬가 남으면 테두리 안 준 변에 흰 선이 비친다.
                tbl.first_row = False
                tbl.horz_banding = False
                무늬 = gf._element.graphic.graphicData.tbl.tblPr.find(qn("a:tableStyleId"))
                if 무늬 is not None:
                    무늬.text = _표무늬없음
                # 열폭은 한 칸짜리 칸에서 잰다. 한 칸짜리가 없는 열은 남은 폭을 고르게 나눈다
                너비 = [None] * ncol
                for 줄 in 자리:
                    for (j, 가, 세, c_) in 줄:
                        if 가 == 1 and 너비[j] is None:
                            너비[j] = c_["w"]
                if None in 너비:
                    남 = max(0.0, it["w"] - sum(x_ for x_ in 너비 if x_))
                    빈 = 너비.count(None)
                    너비 = [x_ if x_ is not None else 남 / 빈 for x_ in 너비]
                for j, cw in enumerate(너비):
                    tbl.columns[j].width = Pt(cw * k)
                행높이 = it.get("rh") or [row[0]["h"] for row in rows]
                합칠것 = []
                for i2, 줄 in enumerate(자리):
                    tbl.rows[i2].height = Pt(행높이[i2] * k)
                    for j, 가, 세, cell in 줄:
                        if 가 > 1 or 세 > 1:
                            합칠것.append((i2, j, i2 + 세 - 1, j + 가 - 1))
                        tc = tbl.cell(i2, j)
                        안 = cell.get("pad")
                        if 안:
                            tc.margin_left, tc.margin_top = Pt(안[0] * k), Pt(안[1] * k)
                            tc.margin_right, tc.margin_bottom = Pt(안[2] * k), Pt(안[3] * k)
                        else:
                            tc.margin_left = tc.margin_right = Pt(6)
                            tc.margin_top = tc.margin_bottom = Pt(3)
                        tc.vertical_anchor = {"middle": MSO_ANCHOR.MIDDLE,
                                              "bottom": MSO_ANCHOR.BOTTOM}.get(cell.get("va", ""), MSO_ANCHOR.TOP)
                        if cell.get("bd"):
                            _cell_borders(tc, cell["bd"], k)
                        bg = _rgb(cell.get("bg", ""))
                        tc.fill.solid()
                        tc.fill.fore_color.rgb = bg if bg is not None else RGBColor(0xFF, 0xFF, 0xFF)
                        p = tc.text_frame.paragraphs[0]
                        p.alignment = _ALIGN.get(cell.get("align", "left"), PP_ALIGN.LEFT)
                        런들 = cell.get("runs")
                        if not 런들:
                            런들 = [{"t": cell.get("t", ""), "size": cell.get("size", 16),
                                    "weight": 700 if cell.get("b") else 400, "color": cell.get("color", "")}]
                        _문단채우기(p, 런들, 1.0, k)
                # 병합은 칸을 다 채운 뒤에 건다(a:tc gridSpan·rowSpan + 덮인 칸 hMerge·vMerge)
                for a, b, c2, d2 in 합칠것:
                    try:
                        tbl.cell(a, b).merge(tbl.cell(c2, d2))
                    except Exception as ex:          # 조용히 버리지 않는다 — 칸은 나뉜 채로 남는다
                        print(f"[pptx] 표 칸 병합({a},{b})~({c2},{d2})을 못 했다 — {type(ex).__name__}",
                              file=sys.stderr)

    return prs, 빠진크롭


def _되읽기(경로):
    """편집 가능성 구조 되읽기 — 텍스트가 텍스트인지, 표가 네이티브 표인지 센다."""
    p2 = Presentation(경로)
    n = {"슬라이드": len(p2.slides), "텍스트": 0, "표": 0, "그림": 0, "차트": 0}
    for sl in p2.slides:
        for sh in sl.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                n["텍스트"] += 1
            if sh.has_table:
                n["표"] += 1
            if getattr(sh, "has_chart", False) and sh.has_chart:   # 네이티브 차트(데이터 편집 가능)
                n["차트"] += 1
            if sh.shape_type == 13:   # PICTURE
                n["그림"] += 1
    return n


_노트장_RX = re.compile(r'<section class="sl-page[^"]*"[^>]*\bdata-slide-idx="\d+"')
_노트칸_RX = re.compile(r'<aside class="sl-notes[^"]*"[^>]*>(.*?)</aside>', re.S)


def _노트싣기(prs, html경로):
    """v2 슬라이드의 숨은 노트(<aside class="sl-notes">: 발표자 말·작성 메모·산출 식)를 PPTX 발표자
    노트 칸으로 옮긴다('26-09-28 v2 통합 E2E — 조립기가 'PPTX 노트 칸의 원천'으로 심어 두었는데
    수확기가 읽지 않아 PPTX 에서 노트가 통째로 사라졌다). 장 수가 안 맞거나 노트가 없으면 아무것도 안 한다."""
    import html as _h
    try:
        원 = open(html경로, encoding="utf-8").read()
    except OSError:
        return 0
    자리 = [m.start() for m in _노트장_RX.finditer(원)]
    if not 자리 or len(자리) != len(prs.slides):
        return 0
    실음 = 0
    for 번, 시작 in enumerate(자리):
        끝 = 자리[번 + 1] if 번 + 1 < len(자리) else len(원)
        m = _노트칸_RX.search(원, 시작, 끝)
        if not m:
            continue
        몸 = re.sub(r"<li[^>]*>", "\n· ", m.group(1))
        몸 = re.sub(r"</p>|</ul>", "\n", 몸)
        글 = "\n".join(x.strip() for x in _h.unescape(re.sub(r"<[^>]+>", "", 몸)).splitlines() if x.strip())
        if 글:
            prs.slides[번].notes_slide.notes_text_frame.text = 글
            실음 += 1
    return 실음


def 만들기(html경로, 낼경로) -> tuple[bool, object]:
    """슬라이드 HTML → PPTX. tohwpx.만들기 와 같은 (ok, 말) 계약.
    성공: (True, 되읽기요약dict). 실패: (False, 사유문자열)."""
    if not os.path.exists(html경로):
        return False, "HTML 이 없습니다 — 조립을 먼저 돌리세요"
    pages, 사유 = 수확(html경로)
    if 사유:
        return False, 사유
    if not pages:
        return False, "슬라이드를 하나도 읽지 못했습니다"
    tmpdir = tempfile.mkdtemp(prefix="pptxcrop_")
    try:
        prs, 빠진크롭 = _조립(pages, tmpdir)
        if 빠진크롭:
            # 조용히 빈 자리로 두지 않는다 — 도식을 못 찍었으면 실패로 알린다(화면읽기 철학).
            return False, f"도식·그림 {len(빠진크롭)}건을 옮기지 못했습니다: {', '.join(빠진크롭[:3])}"
        _노트싣기(prs, html경로)
        prs.save(낼경로)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return True, _되읽기(낼경로)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python topptx.py <슬라이드.html> <낼.pptx>", file=sys.stderr)
        sys.exit(2)
    ok, 말 = 만들기(sys.argv[1], sys.argv[2])
    print(("OK " if ok else "실패 ") + json.dumps(말, ensure_ascii=False))
    sys.exit(0 if ok else 1)
