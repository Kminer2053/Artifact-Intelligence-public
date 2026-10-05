#!/usr/bin/env python3
"""완성된 HTML 을 **머리 없는 크롬으로 열어 실제 그려진 모습**을 트리로 받아 온다.

왜 이 방식인가 — 사장님이 처음부터 "html 을 똑같이 hwpx 로 만드는 것" 이라고 하셨다.
길이 한 줄이어야 한다는 뜻이다. 그런데 내가 낸 tohwpx 는 인스턴스 JSON 으로 되돌아가
**따로 다시 만들고** 있었다(2026-08-05 확인: 풀버전 HWPX 에 남은 글이 제목 한 줄뿐).

자료에서 다시 만들면 안 되는 구체적 이유:
  · 글머리 `□ ○ -` 가 자료에 없다. 자료엔 "2단계" 만 있고 무슨 글자인지는 CSS 가 정한다.
    게다가 `[data-style="gov"]`·`[data-hier="B"]` 같은 스위치가 그 글자를 바꾼다.
    자료만 보면 **찍어서 맞혀야 하고 틀린다.** 화면에는 답이 이미 나와 있다.
  · 장르마다 자료 모양이 전혀 달라(공통 키가 하나도 없다) 자료 읽는 코드가 그 자체로
    손목록이 된다. 새 장르가 오면 조용히 빠진다 — 이 저장소가 일곱 번 밟은 함정이다.

읽는 눈은 **여기 하나뿐이어야 한다.** 대조기와 전환기가 서로 다른 눈으로 보면
전환기가 못 옮긴 것을 대조기도 안 보고 "같다" 고 적는다.

빌린 것 — CSS 속성을 문서 속성으로 옮기는 사상표는 html4docx(MIT)를 참고했다.
다만 그쪽은 인라인 CSS 와 class 를 직접 읽어 우선순위를 손으로 푼다. 우리는 크롬에
물어보므로 **상속·오버라이드가 이미 다 접힌 최종값**을 받는다 — 그 단계가 통째로 없다.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 크롬찾기 가 같은 build/ 에 있다
from 크롬찾기 import 크롬, 띄우기


def _http전용열기():
    """크롬 디버깅 포트(/json)를 묻는 열기 — http 핸들러만 싣는다('26-10-01, workspace/api.py 와 같은 꼴).
    기본 urlopen 은 file:// 같은 다른 스킴 핸들러까지 가져, 정적 보안검사(Semgrep dynamic-urllib-use)가
    동적 URL 호출을 걸어 둔다. 여기 주소는 늘 http://127.0.0.1:<포트>/json 이라 동작은 같다."""
    od = urllib.request.OpenerDirector()
    for h in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(),
              urllib.request.HTTPHandler(), urllib.request.HTTPDefaultErrorHandler(),
              urllib.request.HTTPRedirectHandler(), urllib.request.HTTPErrorProcessor()):
        od.add_handler(h)
    return od


_HTTP열기 = _http전용열기()


def 디버깅목록(항, timeout=1.0):
    """헤드리스 크롬 디버깅 포트의 /json 목록(탭들)을 읽는다 — topptx.py 도 이것을 쓴다."""
    with _HTTP열기.open(f"http://127.0.0.1:{int(항)}/json", timeout=timeout) as r:
        return json.load(r)

# ── 화면에서 읽어 오는 코드 ────────────────────────────────────────────────
# 이 안에서 하는 일은 딱 둘이다. ① 무엇이 마디인지 정한다 ② 그 마디의 최종 서식을 잰다.
# 무엇을 HWPX 로 어떻게 옮길지는 여기서 정하지 않는다(그건 build/역할.py 가 한다).
_읽는코드 = r"""
(() => {
  const PX = 3.779527559;                       // 1mm
  const mm  = v => Math.round(parseFloat(v || 0) / PX * 100) / 100;
  const pt  = v => Math.round(parseFloat(v || 0) * 0.75 * 10) / 10;
  // 색 계산값은 두 꼴로 온다 — `rgb()/rgba()`(0~255 정수)와, color-mix() 를 거친 값의
  // `color(srgb r g b [/ a])`(0~1 실수). 뒤엣것을 못 읽으면 틴트 바탕이 통째로 사라지고,
  // 그라데이션이면 **다음 스톱**(흰색)을 잡는다 — 정부부처형 장 띠가 흰 바탕으로 나간
  // 원인이다('26-09-28 P0-1 실측: 계산값 'color(srgb 0.84 0.910275 0.960471)').
  // 0~1 실수를 ×255 반올림한다(topptx._grad_colors 와 같은 식).
  const 색 = v => {
    v = v || '';
    let 채널, 알파;
    let m = /rgba?\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)(?:,\s*([\d.]+))?\)/.exec(v);
    if (m) {
      채널 = [m[1], m[2], m[3]].map(Number);
      알파 = m[4];
    } else {
      m = /color\(srgb\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)(?:\s*\/\s*([\d.]+)(%?))?\s*\)/.exec(v);
      if (!m) return null;
      채널 = [m[1], m[2], m[3]].map(x => parseFloat(x) * 255);
      알파 = m[4] === undefined ? undefined : String(parseFloat(m[4]) / (m[5] ? 100 : 1));
    }
    if (알파 !== undefined && parseFloat(알파) === 0) return null;      // 투명은 없는 것
    return '#' + 채널.map(x => Math.max(0, Math.min(255, Math.round(x)))
                             .toString(16).padStart(2,'0')).join('').toUpperCase();
  };
  // 그라데이션 배경의 대표색 — **첫 스톱**을 단색 근사로 쓴다(gov 바는 첫 스톱이
  // 포인트색이라 정직한 근사다). 안 읽으면 backgroundColor 가 투명이라 배경 없는
  // 장식으로 판정돼 gov 바·장 표제 띠가 통째로 사라진다(2026-08-13 CSS 전수 갭).
  // 첫 스톱이 color-mix 틴트면 계산값이 color(srgb …) 라 그 꼴도 첫 색으로 잡는다(P0-1).
  // 근사는 숨기지 않는다 — 근사목록 에 적어 내보내기 결과의 '알려진 차이'로 알린다(P0-6).
  const 근사목록 = [];
  const 근사 = (무엇, el) => 근사목록.push({ 무엇, 반: (el && (el.className || el.tagName.toLowerCase())) || null });
  const 그라색 = (v, el) => {
    if (!v || !/gradient\(/.test(v)) return null;
    const m = /rgba?\([^)]+\)|color\(srgb[^)]*\)/.exec(v);
    const c = m ? 색(m[0]) : null;
    if (c) 근사('그라데이션', el);
    return c;
  };
  // 선 굵기 — 크롬 계산값은 **CSS 화소로 반올림**된다(1px 미만은 1px). 0.12mm·0.3mm·0.4mm
  // 가 모두 1px(0.26mm)로, 1.1mm 가 4px 로 뭉개져 '가는/굵은 줄'을 가를 수 없었다
  // ('26-09-28 P0-3 실측). 장치 배율(deviceScaleFactor)을 올려도 계산값은 그대로였고,
  // 뿌리에 zoom 을 걸면 계산값이 1/zoom 화소 단위로 나온다(zoom 16: 0.4mm→1.5px,
  // 0.12mm→0.4375px). 그래서 여기서는 굵기를 1px 값으로 적어 두고 대상을 모았다가,
  // 맨 끝(정밀굵기())에서 zoom 을 잠깐 올려 **굵기만** 다시 잰다 — 배치·자리는 이미
  // 다 잰 뒤라 흔들리지 않고, zoom 은 같은 작업 안에서 되돌린다.
  const 굵기대상 = [];
  const 변읽기 = (el, s) => ['Top','Right','Bottom','Left'].map(d => {
    if (!(parseFloat(s['border'+d+'Width']) > 0)) return null;
    const o = { 굵기mm: mm(s['border'+d+'Width']), 색: 색(s['border'+d+'Color']),
                // 선종류(dashed·dotted)를 안 읽으면 목차 점선·점선 박스가 실선이 된다
                // (2026-08-13 CSS 전수 갭 — 사용처 8곳 실측)
                선종류: s['border'+d+'Style'] };
    굵기대상.push([el, d, o]);
    return o;
  });

  // ── 지면 찾기 ──
  // 클래스 이름으로 찾지 않는다 — 그게 손목록이다. 폭이 210mm 인 블록으로 찾되,
  // 쪽번호 띠(.fr-pageno)도 210mm 라서 **가장 키 큰 것**을 지면으로 삼는다.
  // (2026-08-05: "210mm 면 지면" 만으로 잡으면 풀보고서에서 16개가 잡혀 쪽나눔이 16번 들어간다)
  let 지면 = document.body, 최고 = 0;
  document.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (Math.abs(r.width / PX - 210) > 2) return;
    if (r.height > 최고) { 최고 = r.height; 지면 = el; }
  });
  const 지s = getComputedStyle(지면);
  // 같은 폭·같은 높이가 여러 개면 그것이 쪽 경계다(풀보고서 .fr-page ×9)
  const 지면들 = [...document.querySelectorAll('*')].filter(el => {
    const r = el.getBoundingClientRect();
    return Math.abs(r.width / PX - 210) <= 2 && Math.abs(r.height - 최고) < 2;
  });

  // ── 마디 모으기 ──
  const 덩어리태그 = new Set(['P','H1','H2','H3','H4','H5','H6','LI','DIV','TD','TH',
                            'DT','DD','BLOCKQUOTE','CAPTION','FIGCAPTION','PRE','HR']);
  const 조각태그   = new Set(['SPAN','STRONG','B','EM','I','U','S','SUP','SUB','A','CODE','MARK']);

  const 보임 = el => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0.01;
  };
  // 화면에는 있으나 **문서 내용이 아닌** 조각들:
  //  · .jachigan-run — 자간 사냥꾼이 줄바꿈을 맞추려고 감싼 것. 글자는 진짜다.
  //  · visibility:hidden 유령 라벨(.gm-at-ghost) — 자리만 차지한다. 글자는 가짜다.
  const 유령 = el => getComputedStyle(el).visibility === 'hidden';

  const 마커읽기 = el => {
    // 마커는 두 가지 모양으로 온다 — 둘 다 읽어 하나로 만든다.
    //  ① CSS 로 만든 것: ::before content (1p·풀보고서. counter 까지 접힌 최종 글자)
    //  ② DOM 안의 진짜 글자: <span class="mk">□</span> (보도자료·규정)
    const b = getComputedStyle(el, '::before');
    if (b.content && !['none','normal','""'].includes(b.content)) {
      const g = b.content.replace(/^["']|["']$/g, '').trim();
      if (g) return { 글자: g, 만든것: true };
    }
    const mk = el.querySelector(':scope > .mk');
    if (mk && mk.textContent.trim()) {
      // 실글자 마커는 **제 서식**을 같이 든다(P0-4). 속읽기() 가 .mk 를 건너뛰어, 쓰는 쪽이
      // 마커에 첫 글 조각의 서식을 입혔다 — 규정 '제1조' 는 화면 700 인데 첫 조각이 보통
      // 굵기 '(' 라 HWPX 에서 보통이 됐다('26-09-28 실측). 필드는 속읽기 조각과 같은 이름이다.
      const ms = getComputedStyle(mk);
      return { 글자: mk.textContent.trim(), 만든것: false, 서식: {
        pt: pt(ms.fontSize), 굵기: +ms.fontWeight, 색: 색(ms.color),
        글꼴: (ms.fontFamily.split(',')[0] || '').replace(/["']/g, '').trim(),
        밑줄: ms.textDecorationLine.includes('underline'),
        취소선: ms.textDecorationLine.includes('line-through'),
        기울임: ms.fontStyle === 'italic',
        자간em: ms.letterSpacing === 'normal' ? 0
               : Math.round(parseFloat(ms.letterSpacing) / parseFloat(ms.fontSize) * 10000) / 10000,
      } };
    }
    return null;
  };

  // 짧은 가운데 정렬 머리 문단(제목·부제)의 강제 줄바꿈 — 한글은 breakNonLatinWord=
  // KEEP_WORD 를 걸어도 **숫자로 시작하는 어절**을 쪼갠다(예: '1,200가구 / 로 50%…',
  // 2026-09-26/27 r2 인수 실측 H2). CSS 줄바꿈 규칙 차이를 한글에 가르칠 길이 없으니,
  // 대신 **브라우저가 실제로 줄을 나눈 자리**를 글자 단위 Range 로 재서 그 자리에
  // <hp:lineBreak/> 로 옮긴다 — 어차피 제목류는 화면 그대로 줄을 맞추는 게 목표이지
  // 재조판이 아니다. 본문 긴 문단에는 안 쓴다(글꼴 차이로 한글에서 넘칠 위험 — 위
  // 문단서식 주석의 5.5mm 사연과 같은 종류의 위험).
  const 글자별줄 = el => {
    // 마커·유령 자손은 제외하고, 실제 지면에 그려지는 텍스트 노드만 순서대로 걷는다.
    const 노드들 = [];
    (function 걷기(n) {
      for (const c of n.childNodes) {
        if (c.nodeType === 3) { if (c.nodeValue) 노드들.push(c); continue; }
        if (c.nodeType !== 1) continue;
        if (c.classList && c.classList.contains('mk')) continue;
        if (getComputedStyle(c).visibility === 'hidden') continue;
        걷기(c);
      }
    })(el);
    const 자리 = [];   // 전역 글자 인덱스별 줄 top(px)
    let 인덱스 = 0;
    for (const n of 노드들) {
      const 글 = n.nodeValue;
      for (let i = 0; i < 글.length; i++) {
        try {
          const r = document.createRange();
          r.setStart(n, i); r.setEnd(n, i + 1);
          const 사각 = r.getClientRects();
          자리.push(사각.length ? Math.round(사각[0].top) : null);
        } catch (e) { 자리.push(null); }
        인덱스++;
      }
    }
    return 자리;   // 길이 == 노드들의 글자 총수(마커 제외 el.innerText 와 같아야 한다)
  };
  // 조각 배열(속읽기 결과)에 전역 글자 인덱스 기준으로 줄바꿈 조각을 끼운다.
  const 줄바꿈끼우기 = (속, 줄top들) => {
    if (!줄top들.length) return 속;
    const 끊을자리 = new Set();
    for (let i = 1; i < 줄top들.length; i++) {
      if (줄top들[i] == null || 줄top들[i - 1] == null) continue;
      if (Math.abs(줄top들[i] - 줄top들[i - 1]) > 2) 끊을자리.add(i);   // i 번째 글자 앞에서 끊는다
    }
    if (!끊을자리.size) return 속;
    const 새속 = [];
    let idx = 0;   // 지금까지 지나온 글자 수(줄top들 기준 전역 인덱스)
    for (const f of 속) {
      if (f.글 == null) { 새속.push(f); continue; }
      let 시작 = 0;
      for (let k = 0; k < f.글.length; k++) {
        if (끊을자리.has(idx)) {
          if (k > 시작) 새속.push({ ...f, 글: f.글.slice(시작, k) });
          새속.push({ 줄바꿈: true });
          시작 = k;
        }
        idx++;
      }
      새속.push({ ...f, 글: f.글.slice(시작) });
    }
    return 새속;
  };
  // el 이 이 갈래를 타는지 — 가운데 정렬 + 3줄 이하 + 화면에 실제 줄바꿈이 있을 때만.
  // 본문(justify·left 정렬 긴 문단)은 절대 타지 않는다 — 그런 문단은 한글 자체 흐름에
  // 맡겨야 글꼴 차이로 넘치지 않는다.
  const 강제줄바꿈대상인가 = el => {
    const s = getComputedStyle(el);
    if (s.textAlign !== 'center') return false;
    try {
      const r = document.createRange(); r.selectNodeContents(el);
      // **자식 요소 하나를 통째로 감싼 range**(예: <h1><span class="tx">…</span></h1>)는
      // 크롬이 같은 줄 사각을 두 벌씩 겹쳐 돌려준다(경계가 노드 단위라 그렇다 — 자간사냥
      // (jachigan.js)의 topsOf() 가 top 값으로만 중복을 접는 것과 같은 함정). 너비 있는
      // 사각만 남기고 top 값으로 접어 **줄 수**를 센다 — 사각 개수가 아니라.
      const 줄top = new Set([...r.getClientRects()]
        .filter(x => x.width > 0.5 && x.height > 0.5).map(x => Math.round(x.top)));
      return 줄top.size >= 2 && 줄top.size <= 3;
    } catch (e) { return false; }
  };

  // `line-height: normal` 은 계산값이 글자 그대로 'normal' 로 나온다(숫자가 아니다).
  // 그대로 두면 옮기는 쪽이 제 기본값(160%)을 쓰게 되고 화면과 달라진다
  // (2026-08-05 풀보고서 35개 문단이 이 때문에 틀렸다).
  // 실제 그려진 줄 높이는 텍스트 범위의 줄 상자에서 잰다 — 짐작하지 않는다.
  const 줄간격재기 = el => {
    const s = getComputedStyle(el);
    const 크기 = parseFloat(s.fontSize);
    if (s.lineHeight !== 'normal') return Math.round(parseFloat(s.lineHeight) / 크기 * 100);
    try {
      const r = document.createRange(); r.selectNodeContents(el);
      const 줄 = [...r.getClientRects()].filter(x => x.height > 0.5);
      if (줄.length) return Math.round(Math.min(...줄.map(x => x.height)) / 크기 * 100);
    } catch (e) {}
    return null;
  };

  const 서식 = el => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return {
      pt: pt(s.fontSize), 굵기: +s.fontWeight, 기울임: s.fontStyle === 'italic',
      밑줄: s.textDecorationLine.includes('underline'),
      취소선: s.textDecorationLine.includes('line-through'),
      색: 색(s.color), 바탕: 색(s.backgroundColor) || 그라색(s.backgroundImage, el),
      글꼴: (s.fontFamily.split(',')[0] || '').replace(/["']/g, '').trim(),
      줄간격: 줄간격재기(el),
      정렬: s.textAlign,
      // 왼여백 = 문단 상자가 판면에서 얼마나 들어왔나 (HWPX 의 margin.left)
      왼여백mm: Math.round((r.left - 지면.getBoundingClientRect().left
                          - parseFloat(지s.paddingLeft)) / PX * 100) / 100,
      // 안쪽 들여쓰기 + 내어쓰기 (HWPX 의 margin.left / margin.intent)
      안들여mm: mm(s.paddingLeft), 내어mm: mm(s.textIndent),
      // 세로 안쪽 여백 — 배경 박스(요약박스 2.6mm 등)의 키를 정한다. 안 읽으면
      // 박스가 화면보다 얇다(부록 '안 읽는다' 표의 P2 갭, 2026-08-14 육안 실측 수리)
      위안들여mm: mm(s.paddingTop), 아래안들여mm: mm(s.paddingBottom),
      자간em: s.letterSpacing === 'normal' ? 0
              : Math.round(parseFloat(s.letterSpacing) / parseFloat(s.fontSize) * 1000) / 1000,
      위여백mm: mm(s.marginTop), 아래여백mm: mm(s.marginBottom),
      어절분리: s.wordBreak === 'keep-all' ? 'keep' : 'break',
      테두리: 변읽기(el, s),
      높이mm: Math.round(r.height / PX * 100) / 100,
      폭mm: Math.round(r.width / PX * 100) / 100,
    };
  };

  // 문단 안을 걸어 조각(강조·숫자·증감)과 줄바꿈을 뽑는다.
  // <br> 은 **공백 없이 지우면 안 된다** — 줄이 붙어 버린다(시행문 붙임에서 실제로 그랬다).
  const 속읽기 = (el, 마커글자) => {
    const 조각 = [];
    const 걷기 = (n, 물림) => {
      for (const c of n.childNodes) {
        if (c.nodeType === 3) {
          const t = c.nodeValue;
          if (t) 조각.push({ 글: t, ...물림 });
        } else if (c.nodeType === 1) {
          if (c.tagName === 'BR') { 조각.push({ 줄바꿈: true }); continue; }
          if (c.classList && c.classList.contains('mk')) continue;   // 마커는 따로 들고 간다
          if (유령(c)) { 조각.push({ 빈자리mm: mm(c.getBoundingClientRect().width) }); continue; }
          if (!보임(c)) continue;
          const cs = getComputedStyle(c);
          // 여백·폭이 있는 칠한 글자 상자(칩)는 HWPX 에서 글자 음영(shade)으로만 간다 —
          // 상자 여백·최소 폭·옆 간격이 빠진다. 숨기지 않고 알린다(P0-6).
          if (색(cs.backgroundColor) && (cs.display.includes('inline-block') ||
              parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) > 1 ||
              parseFloat(cs.marginRight) > 1)) 근사('글자음영상자', c);
          걷기(c, {
            반: c.className || c.tagName.toLowerCase(),
            pt: pt(cs.fontSize), 굵기: +cs.fontWeight, 색: 색(cs.color),
            // 조각별 글꼴 — gov 본문(명조) 속 강조 b·.lb 는 고딕이다. 안 읽으면
            // 문단 글꼴을 강제 상속해 강조가 명조로 나간다(2026-08-13 CSS 전수 갭)
            글꼴: (cs.fontFamily.split(',')[0] || '').replace(/["']/g, '').trim(),
            밑줄: cs.textDecorationLine.includes('underline'),
            취소선: cs.textDecorationLine.includes('line-through'),
            기울임: cs.fontStyle === 'italic',
            바탕: 색(cs.backgroundColor),
            // 자간은 **조각에서 읽어야 한다.** 자간사냥(jachigan.js)은 문단이 아니라
            // 줄을 감싼 `.jachigan-run` span 에 letter-spacing 을 건다. 여기서 안 읽으면
            // 그 값이 HWPX 에 안 실려 한글이 더 넓게 그리고, 어절이 한 칸씩 밀린다.
            자간em: cs.letterSpacing === 'normal' ? 0
                   : Math.round(parseFloat(cs.letterSpacing)
                                / parseFloat(cs.fontSize) * 10000) / 10000,
          });
        }
      }
    };
    걷기(el, {});
    // 붙어 있는 같은 서식끼리 합친다 — HWPX run 이 잘게 쪼개지지 않게
    const 뭉침 = [];
    for (const p of 조각) {
      const 앞 = 뭉침[뭉침.length - 1];
      if (앞 && !p.줄바꿈 && !앞.줄바꿈 && !p.빈자리mm && !앞.빈자리mm &&
          JSON.stringify({ ...앞, 글: '' }) === JSON.stringify({ ...p, 글: '' })) {
        앞.글 += p.글;
      } else 뭉침.push({ ...p });
    }
    // 조각의 글자가 전부 NBSP 처럼 '공백류' 여도 버리지 않는다 — 마커와 본문 사이는
    // CSS 여백이 아니라 **실제 NBSP 글자**로 벌린다(assemble_regulation.py·
    // assemble_press.py 의 설계 의도, 복붙 대비). JS trim() 은 NBSP(U+00A0)도 지워
    // '마커-본문 분리용' 조각을 통째로 삼켰다 — 호 '1. 정기'가 '1.정기'로, 항
    // '② 부서장'이 '②부서장'으로 나온 원인이다(2026-09-26, 벤치마크 진단
    // hwpx.findings[3]). 글자를 담는 조각은 걷기() 에서 이미 빈 문자열이 아니므로
    // (`if (t) 조각.push(...)`), 길이만 보면 된다 — trim() 으로 다시 비우지 않는다.
    //
    // **다만 개행·탭이 섞인 공백-only 조각은 다르다** — 그건 HTML 소스 들여쓰기
    // (`\n      ` 같은 서식용 텍스트 노드)일 뿐 화면에 그려지는 구분 공백이 아니다.
    // 살려 두면 _hwpx_write.문단() 이 `\n` 을 그대로 개행 run 으로 적어(<br> 과 같은
    // 처리 경로), flex 컨테이너 안이라 화면엔 안 보이던 줄바꿈+공백 6칸이 HWPX
    // 에서는 실제 줄바꿈으로 나간다 — 시행문 gm-contact 연락처 줄이 갈라진다
    // (hwpx:F3, 2026-09-26/27 벤치마크 진단 재확인). NBSP·본문 중간의 구분용
    // 한 칸 공백(개행·탭이 안 섞인 것)은 그대로 살린다.
    return 뭉침.filter(x => {
      if (x.줄바꿈 || x.빈자리mm) return true;
      if (!(x.글 && x.글.length > 0)) return false;
      if (/^\s*$/.test(x.글) && /[\n\t]/.test(x.글)) return false;
      return true;
    });
  };

  const 표읽기 = tbl => {
    const 행들 = [];
    [...tbl.rows].forEach(tr => {
      const 칸들 = [];
      [...tr.cells].forEach(td => {
        const s = getComputedStyle(td);
        칸들.push({
          글: (td.innerText || '').trim(), 가로병합: td.colSpan, 세로병합: td.rowSpan,
          머리칸: td.tagName === 'TH',
          폭mm: Math.round(td.getBoundingClientRect().width / PX * 100) / 100,
          서식: 서식(td), 속: 속읽기(td, null),
        });
      });
      행들.push({ 칸: 칸들, 높이mm: Math.round(tr.getBoundingClientRect().height / PX * 100) / 100 });
    });
    const s = getComputedStyle(tbl);
    // 표 정렬은 **기하로 잰다**('26-09-29 표 재설계 P1, critic_impl #13). 예전엔 계산값
    // marginLeft === 'auto' 를 봤는데 계산값은 늘 px 라 가운데 표도 LEFT 가 됐다(실측 F6: 82.5mm
    // 가운데 표가 한글에서 왼쪽). 판면보다 확실히 좁을 때(95% 미만)만 가운데·오른쪽을 가른다 —
    // 판면 폭 표는 정렬이 뜻이 없어 LEFT 그대로 둔다(기존 문서의 앵커 문단 모양이 안 바뀐다).
    // 기준은 표를 담은 그릇의 내용 상자다 — 풀버전 .fr-tbl-wrap 처럼 그릇이 5mm 들여 있으면 판면
    // 가운데와 2.5mm 어긋나 가운데 표도 LEFT 로 떨어졌다(r18 합성 실측). 한글은 단 가운데에 둔다.
    const 표r = tbl.getBoundingClientRect(), 그릇 = tbl.parentElement || 지면;
    const 지r = 그릇.getBoundingClientRect(), 그s = getComputedStyle(그릇);
    const 판왼 = 지r.left + parseFloat(그s.paddingLeft) + parseFloat(그s.borderLeftWidth || 0);
    const 판오 = 지r.right - parseFloat(그s.paddingRight) - parseFloat(그s.borderRightWidth || 0);
    const 좁다 = 표r.width < (판오 - 판왼) * 0.95;
    const 표정렬 = !좁다 ? 'LEFT'
      : Math.abs((표r.left + 표r.right) / 2 - (판왼 + 판오) / 2) <= 1.5 * PX ? 'CENTER'
      : Math.abs(표r.right - 판오) <= 1.5 * PX ? 'RIGHT' : 'LEFT';
    return { 행: 행들, 폭mm: Math.round(표r.width / PX * 100) / 100,
             정렬: 표정렬,
             // 겉선은 셀이 아니라 <table> 요소에 걸린다(기본표 상·하 0.4mm) — 안 읽으면
             // 셀 실측 전이(4-A) 이후 겉선이 통째로 사라진다(2026-08-13 한글 뷰어 육안 실측)
             테두리: 변읽기(tbl, s),
             // 표 크기(작게·크게, build/표꼴.py data-크기) — 카탈로그 학습이 이 표 칸 글자를 장르
             // 값 집합에 넣지 않게 알린다('26-09-29 도식·표 fixup). 서식 필드가 아니라 옮기지 않는다.
             크기: (tbl.dataset && tbl.dataset.크기) || null };
  };

  // ── 쪽 안 세로 자리 (쪽 단위 배치) ──
  // 흐름만 옮기면 화면이 flex·절대배치로 **쪽 안에 앉힌** 블록(풀버전 표지의 부제·제목·
  // 날짜 묶음과 아래 기관명, 시행문 결문처럼 쪽 바닥에 붙인 묶음)이 한글에서는 앞 블록
  // 바로 밑에 붙는다(2026-09-27 4차 E2E 한컴 뷰어 확인). 그래서 마디마다 **그 쪽 판면
  // (지면 content-box) 위끝에서 잰 위·아래 자리**와, 그 자리를 흐름이 아니라 배치가
  // 정했는지(자신·조상이 절대배치이거나 조상이 세로 flex)를 함께 싣는다. 무엇을 얼마나
  // 옮길지는 여기서 안 정한다 — build/역할.py 의 _세로배치옮기기() 가 한다.
  // 서식(서식()) 필드가 아니라 마디 곁의 기하 기록이라 카탈로그(동적수집)는 안 센다 —
  // 쪽 번호(쪽)와 같은 부류다.
  const 판 = 쪽번호 => {
    const 지 = 지면들[쪽번호 - 1] || 지면;
    const pr = 지.getBoundingClientRect(), ps = getComputedStyle(지);
    const 위 = pr.top + parseFloat(ps.paddingTop || 0) + parseFloat(ps.borderTopWidth || 0);
    const 아래 = pr.bottom - parseFloat(ps.paddingBottom || 0) - parseFloat(ps.borderBottomWidth || 0);
    return { el: 지, 위, 아래 };
  };
  const 배치인가 = (el, 지) => {
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (a !== 지 && (s.position === 'absolute' || s.position === 'fixed')) return '절대';
      if (a !== el && s.display.includes('flex') && s.flexDirection.startsWith('column')) return '세로flex';
      if (a === 지) break;
    }
    return null;
  };
  const 세로재기 = (el, r, 쪽번호) => {
    const p = 판(쪽번호);
    return { 위mm: mm(r.top - p.위), 아래mm: mm(r.bottom - p.위), 배치: 배치인가(el, p.el) };
  };

  // ── 나란히 — 가로(flex/grid 줄)로 나란히 앉은 칸 가운데 **표가 든** 것 ──
  // 풀버전 표지 윗줄 [문서정보 표 | 결재 표](.fr-cover-top, justify-content: space-between)
  // 가 이 모양이다. 예전엔 `:scope > table` 을 찾자마자 안으로 내려가 두 표를 위아래로
  // 쌓았다(4차 E2E 한컴 뷰어). 칸마다 평소대로 걷되, 거기서 나온 마디에 **어느 줄의 몇째
  // 칸인지·칸의 가로 자리**를 달아 둔다 — 옮기는 쪽이 괘선 없는 1행 배치용 표로 묶는다.
  // 글만 든 칸 줄(두문·결문·목차)은 아래 칸나눔(가로줄)이 이미 맡는다 — 여기는 표가
  // 들어 있어 그 길을 못 타는 줄만 본다.
  let 나란히수 = 0;
  const 나란히인가 = el => {
    const s = getComputedStyle(el);
    if (!(s.display.includes('flex') || s.display.includes('grid'))) return null;
    if (s.display.includes('flex') && s.flexDirection.startsWith('column')) return null;
    const 아이 = [...el.children].filter(보임);
    if (아이.length < 2) return null;
    if (!아이.some(x => x.tagName === 'TABLE' || x.querySelector('table'))) return null;
    const 상자 = 아이.map(x => ({ el: x, r: x.getBoundingClientRect() }))
                   .sort((a, b) => a.r.left - b.r.left);
    for (let i = 1; i < 상자.length; i++) {
      if (상자[i].r.left < 상자[i - 1].r.right - 1) return null;     // 가로로 겹치면 아니다
    }
    // 한 줄에 앉아 있어야 나란히다 — 세로 구간이 서로 겹친다(줄바꿈된 flex-wrap 은 아니다)
    const 위 = Math.max(...상자.map(b => b.r.top)), 아래 = Math.min(...상자.map(b => b.r.bottom));
    if (!(위 < 아래)) return null;
    return 상자;
  };

  // ── 문서 차례대로 걷는다 ──
  const 마디 = [];
  const 본것 = new WeakSet();
  const 걷기 = (el, 쪽번호) => {
    for (const c of el.children) 하나(c, 쪽번호);
  };
  // 마디를 넣을 때 세로 자리를 같이 단다 — 넣는 자리가 여럿이라 한 곳에 모은다.
  const 넣기 = (m, el, r, 쪽번호) => {
    m.세로 = 세로재기(el, r, 쪽번호);
    마디.push(m);
  };
  const 하나 = (c, 쪽번호) => {
    {
      if (!보임(c) || 본것.has(c)) return;
      // 도형·그림 — svgfig.js 가 그린 SVG 와 <img> 는 글로 옮길 수 없다.
      // 그렇다고 버리면 안 된다: 2026-08-05 풀보고서 관공서본에서 SVG 안 글자 212자가
      // 통째로 사라졌는데 마디 짝짓기는 "다 맞다" 고 했다(독립된 눈이 잡았다).
      // 여기서는 **어디를 찍을지**만 정하고, 실제 찍기는 tohwpx 가 크롬에 시킨다.
      const 그림 = (c.tagName === 'SVG' || c.tagName === 'svg' || c.tagName === 'IMG')
                 ? c : c.querySelector(':scope > svg, :scope > img');
      if (그림) {
        // **그림(svg/img) 자신의 자손만** 본것 처리한다 — svg/img 는 글로 못 옮기니
        // 화면에서 찍은 자리(자리)로만 들고 간다. 자리는 **svg/img 사각형뿐**이라,
        // 예전처럼 컨테이너 c 전체(캡션 '< … >' div·※주 div 포함)를 본것으로 지워
        // 버리면 그 둘은 자리에도 안 잡히고 글로도 안 남아 HWPX 에서 조용히
        // 사라진다(hwpx:F3, svgfig.js·imageasset.py 의 [div.cap, svg|img, div.note]
        // 구조). 캡션·주는 DOM 차례 그대로 **따로 걷어** 그림 위·아래에 제 문단으로
        // 내보낸다 — 그래야 대조가 그 글자를 다른 문단과 똑같이 센다.
        본것.add(그림); 그림.querySelectorAll('*').forEach(x => 본것.add(x));
        const gr = 그림.getBoundingClientRect();
        // **svg/img 자신의 글자만** 뽑는다(캡션·주는 이제 별도 문단으로 나간다) — 안
        // 좁히면 대조가 그림 글로 캡션·주까지 화면 글자수에서 통째로 빼 버려, HWPX 에서
        // 그 둘이 빠져도 "모자람 없음"으로 조용히 통과한다(hwpx:F3). **`그림.innerText`
        // 를 바로 쓰면 안 된다** — innerText 는 HTMLElement 에만 있고 SVGElement 에는
        // 없어(계산값이 아니라 없는 속성) `<svg>` 에서 늘 빈 문자열이 나온다(실측:
        // 자체검증 스크립트로 4개 도식 모두 0자로 나와 이 자리에서 잡았다). 그렇다고
        // svg.textContent 를 쓰면 화면에 안 보이는 <title>(대체텍스트, svgfig.js 가
        // 접근성용으로 심는다)까지 섞여 지면글과 안 맞는 글자가 끼거나, 형제 사이
        // 줄바꿈이 없어 이어붙은 글자가 지면글(innerText 기준)과 어긋나 대조의 뺄셈이
        // 아예 안 먹기도 한다. 그래서 **컨테이너 c 전체의 innerText(캡션·주·도식 글자가
        // 화면 그대로 이어진 것)에서, 앞뒤 형제(캡션·주)의 innerText 를 접두·접미로
        // 벗겨** 가운데(도식 자신)만 남긴다 — 형제 사이 구분자가 무엇이든
        // startsWith/endsWith 는 접두·접미 글자만 보므로 안 흔들린다.
        const 안전이너텍스트 = el => (el.innerText !== undefined ? el.innerText : el.textContent) || '';
        let 그림글 = 안전이너텍스트(c === 그림 ? 그림 : c);
        if (c !== 그림) {
          const 형제들 = [...c.children];
          const 내자리 = 형제들.indexOf(그림);
          const 앞글 = 형제들.slice(0, 내자리).map(안전이너텍스트).join('');
          const 뒤글 = 형제들.slice(내자리 + 1).map(안전이너텍스트).join('');
          if (앞글 && 그림글.startsWith(앞글)) 그림글 = 그림글.slice(앞글.length);
          if (뒤글 && 그림글.endsWith(뒤글)) 그림글 = 그림글.slice(0, 그림글.length - 뒤글.length);
        }
        const 그림마디내기 = () => 넣기({
          종류: '그림',
          역할: (c.closest('[data-ent]') || {}).dataset?.ent || null,
          반: c.className || c.tagName.toLowerCase(),
          글: 그림글.trim(),
          쪽: 쪽번호,
          자리: { x: gr.left + scrollX, y: gr.top + scrollY,
                 폭: gr.width, 높이: gr.height },
          폭mm: Math.round(gr.width / PX * 100) / 100,
          높이mm: Math.round(gr.height / PX * 100) / 100,
          서식: 서식(c),
          // AI 생성 그림(imageasset data-gen) — 한글 그림 파일 안에도 'AI 생성물' 표기를 심게 요청 id 를 싣는다(P3)
          생성: ((c.closest && c.closest('.fr-img[data-gen]')) || { dataset: {} }).dataset.gen || undefined,
        }, c, gr, 쪽번호);
        if (c === 그림) {
          그림마디내기();
          return;
        }
        // 컨테이너(.fr-fig 류)다 — DOM 차례 그대로 자식마다 걷는다. 그림 자리에서
        // 만나면 그림 마디를 내고, 그 밖(cap·note)은 여느 블록처럼 하나() 에 맡긴다
        // (덩어리태그 에 DIV 가 있어 글이 있으면 문단으로, 없으면 버려진다).
        [...c.children].forEach(자식 => {
          if (자식 === 그림) { 그림마디내기(); return; }
          하나(자식, 쪽번호);
        });
        return;
      }
      if (c.tagName === 'TABLE') {
        본것.add(c);
        c.querySelectorAll('*').forEach(x => 본것.add(x));   // 셀을 다시 세지 않는다
        넣기({ 종류: '표', 역할: (c.closest('[data-ent]') || {}).dataset?.ent || null,
               경로: c.getAttribute('data-path'), 쪽: 쪽번호, 표: 표읽기(c) },
             c, c.getBoundingClientRect(), 쪽번호);
        return;
      }
      // 나란히(가로로 앉은 칸 중 표가 든 줄) — 위 '나란히인가' 주석. 칸마다 평소대로
      // 걷고, 그 칸에서 나온 마디에 줄·칸 자리를 단다. 칸 폭은 가로줄과 같은 규칙으로
      // **다음 칸이 시작하는 자리까지**다(justify-content 가 벌린 틈이 앞 칸 몫이 된다 —
      // 그래야 오른쪽 칸이 화면과 같은 x 에서 시작한다).
      const 나란 = 나란히인가(c);
      if (나란) {
        본것.add(c);
        const 묶음 = ++나란히수;
        const cr = c.getBoundingClientRect(), p = 판(쪽번호);
        const 틀왼 = Math.round((cr.left - 지면.getBoundingClientRect().left
                                - parseFloat(지s.paddingLeft)) / PX * 100) / 100;
        나란.forEach((b, i, 전) => {
          const 시작 = 마디.length;
          하나(b.el, 쪽번호);
          for (let k = 시작; k < 마디.length; k++) {
            마디[k].나란히 = {
              묶음, 칸: i, 칸수: 전.length,
              칸왼mm: mm(b.r.left - cr.left),
              칸폭mm: mm((i + 1 < 전.length ? 전[i + 1].r.left : cr.right) - b.r.left),
              칸위mm: mm(b.r.top - p.위), 칸아래mm: mm(b.r.bottom - p.위),
              줄위mm: mm(cr.top - p.위), 줄아래mm: mm(cr.bottom - p.위),
              틀왼mm: 틀왼, 틀폭mm: mm(cr.width),
            };
          }
        });
        return;
      }
      // 표를 감싸기만 하는 껍데기(.rg-table-wrap)를 마디로 세면 표가 두 벌 나간다.
      // 2026-08-05 감리 지적: 규정에서 글자 80자가 두 번 세어졌다.
      const 안에표 = c.querySelector(':scope > table');
      if (안에표) { 걷기(c, 쪽번호); return; }

      // 가로 배치(grid/flex 로 칸을 나눈 줄) — 시행문 두문(수신·경유·제목)·결재란·결문이
      // 표가 아니라 CSS grid 다. 한 문단으로 뭉개면 '수신수신자 참조' 처럼 라벨과 값이
      // 붙는다(2026-08-05 한글 뷰어로 직접 보고 알았다 — 글자는 다 있어서 값 대조는
      // 통과했다). **칸이 나뉘어 있으면 나뉜 채로 옮긴다.**
      const 칸나눔 = (el) => {
        const 아이 = [...el.children].filter(보임);
        if (아이.length < 2) return null;
        const 상자 = 아이.map(x => ({ el: x, r: x.getBoundingClientRect(),
                                    빈: !(x.innerText || '').trim() }));
        // 세로 정렬 검사는 **글자가 있는 자식끼리만** 본다. 텍스트가 없는 순수 장식
        // 자식(목차 채움선처럼 border-bottom 만 있고 글자가 없는 빈 span)은 baseline
        // 정렬에서 높이가 1px 안팎이라 top 이 실측 23~25px 어긋나 오탐을 낸다 — 그
        // 오탐 때문에 목차 한 줄 전체가 칸이 아니라 통짜 문단으로 무너져 채움선·
        // 오른쪽 정렬 쪽번호·□ 표시가 한꺼번에 사라졌다(2026-09-26, 벤치마크 진단
        // hwpx.findings[0]). 빈 자식은 정렬 검사에서만 빼고, 폭·칸 계산에는 그대로 쓴다.
        const 글자있는것 = 상자.filter(b => !b.빈);
        if (!글자있는것.length) return null;      // 전부 장식이면 칸으로 볼 근거가 없다
        const 줄 = 글자있는것[0].r;
        for (const b of 글자있는것) {
          if (b.r.height < 1) return null;
          if (Math.abs(b.r.top - 줄.top) > Math.max(4, 줄.height * 0.6)) return null;
        }
        상자.sort((a, b) => a.r.left - b.r.left);
        for (let i = 1; i < 상자.length; i++) {
          if (상자[i].r.left < 상자[i-1].r.right - 1) return null;   // 가로로 겹치면 아니다
        }
        // **칸이냐 흐름이냐**를 가른다.
        //  · 칸(grid) — 상자가 글자보다 넓다. 라벨 '수신' 이 22.2mm 칸을 채운다.
        //  · 흐름(flex) — 상자가 글자에 딱 붙는다. 개조식 마커 '1. ' 이 그렇다.
        // 벌어진 틈만 보면 안 된다 — grid 는 칸이 딱 붙어 있어 틈이 0 이다
        // (2026-08-05: 그 기준으로 보다가 시행문 두문을 놓쳐 '수신수신자 참조' 가 나왔다).
        const 글자폭 = el => {
          try {
            const r = document.createRange(); r.selectNodeContents(el);
            const b = r.getBoundingClientRect();
            return b.width || 0;
          } catch (e) { return 0; }
        };
        // **마지막 칸은 보지 않는다.** 마지막 칸은 줄의 남은 자리를 그냥 다 차지하므로
        // 한 줄짜리면 늘 크게 남는다 — 그걸 '칸' 신호로 읽으면 개조식 마커 줄까지
        // 표로 바꿔 버려 '가' 와 '.' 이 두 줄로 쪼개진다(2026-08-05 실측: 마커 칸의
        // 남는 폭은 0, 뒤따르는 본문 칸이 147~422px 남았다).
        // 앞칸이 제 글자보다 넉넉히 넓을 때가 **칸**이다(라벨 22.2mm 에 '수신' 11mm).
        const 앞칸들 = 상자.slice(0, -1);
        const 칸같음 = 앞칸들.some(b => b.r.width - 글자폭(b.el) > 15);   // 15px ≈ 4mm
        const 첫칸빔 = 상자.some(b => !(b.el.innerText || '').trim());
        if (!칸같음 && !첫칸빔) return null;
        return 상자;
      };
      // **grid 만** 칸으로 본다. flex 는 흐름이다 — 개조식 마커(`1. ` `가. `)가 flex 인데
      // 이걸 칸으로 잡으면 마커가 좁은 칸에 갇혀 '가' 와 '.' 이 두 줄로 쪼개진다
      // (2026-08-05 한글 뷰어에서 실제로 그랬다).
      const _d = getComputedStyle(c).display;
      const 칸들 = (_d.includes('grid') || _d.includes('flex')) ? 칸나눔(c) : null;
      if (칸들 && !c.querySelector('table')) {
        본것.add(c);
        c.querySelectorAll('*').forEach(x => 본것.add(x));
        const 지r = 지면.getBoundingClientRect();
        넣기({
          종류: '가로줄',
          역할: (c.closest('[data-ent]') || {}).dataset?.ent ||
                (c.querySelector('[data-ent]') || {}).dataset?.ent || null,
          반: c.className || c.tagName.toLowerCase(),
          글: (c.innerText || '').trim(), 쪽: 쪽번호, 서식: 서식(c),
          // 칸 폭은 상자 폭이 아니라 **다음 칸이 시작하는 자리까지**로 잡는다.
          // flex `gap` 은 상자 밖에 있어서, 상자 폭만 쓰면 표가 그 틈만큼 좁아지고
          // 라이브러리가 남는 폭을 나눠 채워 글자가 밀린다(2026-08-05 결문에서 4mm 씩).
          칸: 칸들.map((b, i, 전) => {
            // 칸의 글은 innerText 로만 뽑는데, innerText 에는 **::before 로 만든 마커
            // (예: 풀버전 비-gov 목차 절 행 `.t::before{content:"□ "}`)가 안 들어간다.
            // 마커읽기() 는 칸 요소 자신의 ::before/:scope>.mk 를 보므로, 여기서도 같은
            // 눈으로 한 번 더 재서 앞에 붙인다(2026-09-26/27, r2 벤치마크 진단
            // hwpx.findings[3] — 1차 보고 "innerText 가 이미 포함" 은 재현되지 않았다).
            const 칸마커 = 마커읽기(b.el);
            const 마커앞 = 칸마커 ? 칸마커.글자 + ' ' : '';
            return {
              글: (마커앞 + (b.el.innerText || '').trim()).trim(),
              폭mm: Math.round(((i + 1 < 전.length ? 전[i+1].r.left : c.getBoundingClientRect().right)
                               - b.r.left) / PX * 100) / 100,
              서식: 서식(b.el), 속: 속읽기(b.el, null),
              경로: b.el.getAttribute('data-path'),
            };
          }),
        }, c, c.getBoundingClientRect(), 쪽번호);
        return;
      }

      // ── 번호칩 머리(P0-5) — [칠한 번호칩][간격][제목] 한 줄 ──
      // 정부부처형 절 표제(`.fr-sec` = <span.no 칩>+<span.tx 제목>)가 이 꼴이다. 문단으로
      // 옮기면 칩이 글자 음영으로만 남고 칩 폭·안여백·옆 간격(3mm)이 사라져 '1추진 배경'
      // 처럼 붙었다('26-09-28 실측). 칩은 grid 칸이 아니라 inline-block 이라 위 칸나눔을
      // 못 탄다 — CSS·DOM 은 그대로 두고(편집기 드릴다운·keep-with 가 이 구조에 걸려 있다)
      // 여기서 **칸 셋(칩 | 간격 | 제목)으로 나눈 가로줄**로 읽는다. 칸 폭은 화면 자리 그대로
      // (칩 = 칩 상자 폭, 간격 = 칩 오른끝~제목 왼끝, 제목 = 줄 오른끝까지). 좁게 가른다 —
      // 보이는 자식이 딱 둘이고, 첫째가 칠한 inline-block(30mm 이하)이고, 둘째가 그 오른쪽에
      // 오고, 자식 밖 글자가 없을 때만. 칩 칸은 한글에서 줄 높이만큼 칠해진다(화면은 글줄
      // 높이) — 근사라 알린다(P0-6).
      const 칩머리 = el => {
        const s0 = getComputedStyle(el);
        if (s0.display.includes('grid') || s0.display.includes('flex')) return null;
        const 아이 = [...el.children].filter(보임);
        if (아이.length !== 2) return null;
        for (const n of el.childNodes) if (n.nodeType === 3 && n.nodeValue.trim()) return null;
        const [칩, 글칸] = 아이;
        const ks = getComputedStyle(칩);
        if (!ks.display.includes('inline-block') || !색(ks.backgroundColor)) return null;
        if (!(칩.innerText || '').trim()) return null;
        // 제목 자리는 **첫 줄 상자**로 잰다. 제목이 두 줄로 접히면 둘째 줄이 줄 왼끝(칩
        // 아래)에서 시작해 span 전체 상자(getBoundingClientRect)의 left 가 칩보다 왼쪽이
        // 된다 — 그걸로 재면 칩머리가 null 이 돼 옛 문단 갈래로 떨어지고, 카탈로그에 없는
        // 문단 꼴 값 때문에 HWPX 내보내기가 막혔다('26-09-28 P0 적대검토 H1, 30자 넘는
        // 절 제목). 빈 제목(글칸 글 없음)도 같은 갈래로 떨어지지 않게 칸 셋으로 읽는다.
        const kr = 칩.getBoundingClientRect(), gr = 글칸.getClientRects()[0] || 글칸.getBoundingClientRect();
        if (kr.width / PX > 30 || gr.left < kr.right - 1) return null;
        return { 칩, 글칸, kr, gr, 접힘: 글칸.getClientRects().length > 1 };
      };
      const 칩줄 = 덩어리태그.has(c.tagName) ? 칩머리(c) : null;
      if (칩줄) {
        본것.add(c);
        c.querySelectorAll('*').forEach(x => 본것.add(x));
        const cr = c.getBoundingClientRect();
        근사('번호칩', c);
        // 두 줄 제목 — 화면은 둘째 줄이 칩 아래(줄 왼끝)로 돌아가지만 한글에서는 제목 칸
        // 안에서 접힌다(칸 셋 표라 칩 칸 아래로 흐를 수 없다). 근사라 알린다(P0-6).
        if (칩줄.접힘) 근사('번호칩두줄', c);
        넣기({
          종류: '가로줄',
          역할: (c.closest('[data-ent]') || {}).dataset?.ent || null,
          반: c.className || c.tagName.toLowerCase(),
          글: (c.innerText || '').trim(), 쪽: 쪽번호, 서식: 서식(c),
          칸: [
            { 글: (칩줄.칩.innerText || '').trim(), 폭mm: mm(칩줄.kr.width),
              서식: 서식(칩줄.칩), 속: 속읽기(칩줄.칩, null), 경로: 칩줄.칩.getAttribute('data-path') },
            // 간격 칸 — 글이 없다. 서식은 줄(컨테이너) 것을 빌린다(바탕 없음·같은 글자 크기)
            { 글: '', 폭mm: mm(칩줄.gr.left - 칩줄.kr.right), 서식: 서식(c), 속: [], 경로: null },
            // 빈 제목 칸은 글줄이 없어 줄간격을 못 잰다(null → 가드가 '없음'으로 세운다) —
            // 그때는 줄(컨테이너) 줄간격을 빌린다. 간격 칸과 같은 값이다.
            { 글: (칩줄.글칸.innerText || '').trim(), 폭mm: mm(cr.right - 칩줄.gr.left),
              서식: (f => (f.줄간격 == null ? { ...f, 줄간격: 서식(c).줄간격 } : f))(서식(칩줄.글칸)),
              속: 속읽기(칩줄.글칸, null),
              경로: 칩줄.글칸.getAttribute('data-path') || c.getAttribute('data-path') },
          ],
        }, c, cr, 쪽번호);
        return;
      }

      const 자식덩어리 = [...c.children].some(x => 덩어리태그.has(x.tagName) && 보임(x));
      const 글 = (c.innerText || '').trim();
      const r = c.getBoundingClientRect();
      if (덩어리태그.has(c.tagName) && !자식덩어리) {
        본것.add(c);
        const mk = 마커읽기(c);
        let 속 = 속읽기(c, mk && mk.글자);
        // 짧은 가운데 정렬 머리 문단(제목·제명·표지제목·부제·제목줄)만 — 본문류 역할은
        // 절대 안 탄다(위 강제줄바꿈대상인가·글자별줄 주석 참고). br·유령칸이 이미 섞인
        // 속이면 겹쳐 끼우지 않고 그대로 둔다(안전 우선 — 자리가 어긋날 수 있는 자리는
        // 손대지 않는다).
        const 역할이름 = (c.closest('[data-ent]') || {}).dataset?.ent || null;
        if (['제목', '제명', '표지제목', '부제', '제목줄'].includes(역할이름) &&
            !속.some(x => x.줄바꿈 || x.빈자리mm != null) &&
            강제줄바꿈대상인가(c)) {
          const 줄top들 = 글자별줄(c);
          const 글자수 = 속.reduce((n, x) => n + (x.글 ? x.글.length : 0), 0);
          if (줄top들.length === 글자수) 속 = 줄바꿈끼우기(속, 줄top들);
        }
        const 있나 = 속.some(x => x.글 && x.글.trim()) || 글;
        const 장식 = !있나 && (색(getComputedStyle(c).backgroundColor) || r.height >= 0.3);
        if (!있나 && !장식) return;
        넣기({
          종류: 있나 ? '문단' : '장식',
          역할: 역할이름,
          경로: c.getAttribute('data-path') ||
                (c.querySelector('[data-path]') || {}).getAttribute?.('data-path') || null,
          반: c.className || c.tagName.toLowerCase(), 태그: c.tagName.toLowerCase(),
          글: 글, 마커: mk, 속: 속, 서식: 서식(c), 쪽: 쪽번호,
        }, c, r, 쪽번호);
      } else {
        걷기(c, 쪽번호);
      }
    }
  };
  지면들.forEach((p, i) => 걷기(p, i + 1));

  // ── 선 굵기 정밀 재기(P0-3) — 위 '굵기대상' 주석 ──
  // 뿌리 zoom 을 16 으로 올려 굵기만 다시 잰다(1/16px = 0.0165mm 단위). 이 크롬이 zoom 을
  // 푼 계산값을 주는지(요즘 크롬) 곱한 값을 주는지(옛 크롬)는 1px 값과의 비로 가른다 —
  // 푼 값이면 비가 2 이하(1px 로 올려 잡힌 0.12mm 는 0.44 배), 곱한 값이면 7 이상이다.
  // 곱한 값이면 16 으로 나눈다. zoom 은 같은 작업 안에서 되돌린다(자리는 이미 다 쟀다).
  if (굵기대상.length) {
    const 뿌리 = document.documentElement, 옛줌 = 뿌리.style.zoom, 배율 = 16;
    try {
      뿌리.style.zoom = String(배율);
      const 잰것 = 굵기대상.map(([el, d]) => parseFloat(getComputedStyle(el)['border' + d + 'Width']));
      // 스프레드(Math.max(...배열))는 대상이 수십만이면 RangeError 로 읽기 전체가 죽는다 — 줄여 잰다
      const 비 = 잰것.reduce((m, w, i) => Math.max(m, w / (굵기대상[i][2].굵기mm * PX || 1)), 0);
      const 나눔 = 비 > 4 ? 배율 : 1;
      잰것.forEach((w, i) => { if (w > 0) 굵기대상[i][2].굵기mm = mm(w / 나눔); });
    } finally {
      뿌리.style.zoom = 옛줌;
    }
  }

  return JSON.stringify({
    장르: document.documentElement.getAttribute('data-genre'),
    제목: document.title,
    쪽: {
      크기mm: [210, 297],
      // 쪽 여백 — 가로는 지면 padding 이, **세로는 `--doc-page-mt/mb` 가 정본이다.**
      // 세로 여백을 `@page` 로 옮긴 뒤(이어지는 쪽에 여백이 없던 결함을 고치느라)
      // 인쇄 매체에서 지면 padding 의 위·아래가 0 이 됐다. 그걸 그대로 옮겼더니
      // HWPX 가 `top="0" bottom="0"` 으로 나왔다 — 위아래 여백이 없는 문서다
      // (2026-08-06, 고치다가 스스로 만든 회귀를 검사가 잡았다).
      여백mm: (() => {
        const v = k => {
          const s = getComputedStyle(document.documentElement).getPropertyValue(k).trim();
          if (!s) return null;
          const 재기 = document.createElement('div');
          재기.style.cssText = 'position:absolute;visibility:hidden;height:' + s;
          document.body.appendChild(재기);
          const h = 재기.getBoundingClientRect().height;
          재기.remove();
          return Math.round(h / PX * 10) / 10;
        };
        const 위 = v('--doc-page-mt'), 아래 = v('--doc-page-mb');
        return [위 !== null ? 위 : mm(지s.paddingTop), mm(지s.paddingRight),
                아래 !== null ? 아래 : mm(지s.paddingBottom), mm(지s.paddingLeft)];
      })(),
      지면반: 지면.className || 지면.tagName, 지면수: 지면들.length, 지면높이mm: Math.round(최고 / PX * 10) / 10,
    },
    // 쪽마다 화면이 실제로 찍은 쪽번호·숨김 여부 — assemble_full.py 조판기가 이미
    // 계산해 쪽마다 .fr-pageno(하단 '- N -')와 data-no-pageno 로 남겨 둔 것을 그대로
    // 옮긴다(다시 계산하지 않는다 — "화면에는 답이 이미 나와 있다", 이 파일 머리말).
    // .fr-pageno 가 아예 없는 쪽(gov 표지·목차처럼 '본문재시작'이 숫자를 안 매긴 쪽)도
    // 화면엔 번호가 없는 것이니 번호숨김=true 다 — data-no-pageno 유무만 보면
    // 그 쪽은 속아 넘어간다(3차 수정, "꼬리말 쪽번호" high 결함).
    // 판높이mm — 그 쪽 판면(지면 content-box)의 세로 길이. 마디.세로 의 위·아래 자리가
    // 이 판면 위끝에서 잰 값이라, 옮기는 쪽이 "쪽 바닥까지 얼마 남았나" 를 이 값으로 잰다
    // (역할._세로배치옮기기 의 넘침 여유 — 화면이 바닥에 붙인 결문이 한글에서 넘치지 않게).
    쪽정보: 지면들.map((p, i) => {
      const el = p.querySelector(':scope > .fr-pageno');
      const 번호숨김 = !el || p.hasAttribute('data-no-pageno');
      const m = el ? /(\d+)/.exec(el.textContent || '') : null;
      const pp = 판(i + 1);
      return { 번호숨김, 쪽번호: m ? parseInt(m[1], 10) : null, 판높이mm: mm(pp.아래 - pp.위) };
    }),
    마디: 마디,
    // 화면을 그대로 못 옮겨 **근사한 자리**(그라데이션→첫 색 단색, 칩→글자 음영·표 칸).
    // 서식 필드가 아니라 문서 곁의 기록이라 카탈로그(동적수집)는 안 센다 — 쓰는 쪽이
    // 내보내기 결과의 '알려진 차이'로 알린다(P0-6, _hwpx_write.쓰기).
    근사: 근사목록,
    // 지면 전체 글자 — **독립된 눈**이다. 마디를 다 합친 것과 따로 재서
    // 전환기가 빠뜨린 것을 마디 수집기가 같이 못 보고 넘어가는 일을 막는다.
    지면글: 지면들.map(p => p.innerText).join('\n'),
  });
})()
"""


# ── 크롬에 물어보기 ────────────────────────────────────────────────────────
def 읽기(html경로: Path, 매체: str = "print") -> dict:
    """HTML 을 열어 위 코드를 그 페이지에서 돌리고 결과를 받는다.

    매체를 print 로 두는 이유 — 화면에는 글꼴 전환기 같은 조작 UI 가 같이 뜬다.
    그건 문서가 아니다(@media print 에서 display:none). 화면 그대로 재면 그걸
    "HWPX 에 빠진 것" 으로 세게 된다(실제로 한 번 그렇게 셌다).

    **주의** — 인쇄 매체로 놓아도 크롬이 쪽을 실제로 나누지는 않는다. 여기서 나오는
    것은 "인쇄용 규칙이 적용된 배치" 이지 "종이" 가 아니다. 종이는 PDF 를 뜯어 재야
    한다(build/verify_all.py 의 check_print_margin).
    """
    크롬경로 = 크롬()   # 못 찾으면 안내와 함께 여기서 죽는다(build/크롬찾기.py)
    # ignore_cleanup_errors — snap chromium 이 user-data-dir 의 'Default' 프로필에 잠금
    # 파일을 남겨 rmtree 가 "Directory not empty" 로 터지는 레이스가 있다(2026-08-17 실측:
    # 카탈로그 배치 스캔 42회에서 크래시). 정리 실패는 스캔 결과와 무관하니 삼킨다(Py3.10+).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        # 포트는 크롬이 빈 것을 골라 user-data-dir/DevToolsActivePort 에 적는다(포트 0).
        # 9333 고정이던 시절, 딴 데서 뜬 측정 크롬이 그 포트를 쥐고 있으면 /json 이
        # **남의 탭**을 돌려줬다 — 대조의 화면 쪽 문서 짝이 통째로 밀리는 조용한 오염,
        # 남의 크롬이 내려가는 순간엔 ConnectionRefused (2026-08-07 실측).
        # 부모(serve.py·tohwpx)가 SIGKILL 로 죽어도 크롬이 고아로 남지 않게 크롬찾기.띄우기 한 손으로 띄운다('26-10-01 R3)
        p = 띄우기(
            [크롬경로, "--headless", "--disable-gpu", "--remote-debugging-port=0",
             f"--user-data-dir={tmp}/u", "--no-first-run", "--no-default-browser-check",
             html경로.resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 치울=tmp)
        try:
            붙을곳 = None
            # 폴링 간격 — 예전엔 0.25초라 160회로 최대 40초를 쟀다. 크롬은 대개
            # 그보다 훨씬 빨리 포트를 연다(속도 진단 실측: 냉기동도 1초 안쪽이 흔하다).
            # 간격을 0.05초로 좁혀 빨리 뜬 경우의 헛대기를 줄인다(2026-09-26,
            # speed_result.json 진단). **횟수가 아니라 time.monotonic() 마감으로 40초
            # 상한을 건다** — 횟수(800회)로만 재면 포트 파일은 있는데 /json 이 안 답하는
            # 드문 경우(행 걸린 크롬)에 매 회 urlopen(timeout=1)이 그대로 1초씩 막혀
            # 최악 대기가 40초가 아니라 800×(0.05+1)≈840초가 된다 — 주석의 "같은 40초
            # 상한"과 실제가 어긋났다(2026-09-26/27, r2 벤치마크 진단 hwpx.findings[6]).
            # urlopen timeout 도 남은 시간으로 줄여, 마감 직전 한 번의 시도가 마감을
            # 넘기지 않게 한다.
            _마감 = time.monotonic() + 40
            while time.monotonic() < _마감:
                try:
                    항 = int((Path(tmp) / "u" / "DevToolsActivePort")
                            .read_text().splitlines()[0])
                    남은 = max(0.05, min(1.0, _마감 - time.monotonic()))
                    j = 디버깅목록(항, timeout=남은)
                    쓸것 = [t for t in j if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                    if 쓸것:
                        붙을곳 = 쓸것[0]["webSocketDebuggerUrl"]
                        break
                except Exception:
                    pass
                time.sleep(0.05)
            if not 붙을곳:
                raise SystemExit("크롬 디버깅에 못 붙었다")
            # 글꼴·자간 사냥이 앉을 때까지 — 예전엔 문서 내용·속도와 무관하게 무조건
            # 1.3초를 잤다(speed_result.json 실측: hwpx 내보내기마다 100% 낭비되는
            # 시간이었다). jachigan.js 는 자간 사냥이 끝나면(글꼴 로드까지 기다린 뒤)
            # <html data-jachigan-done="1"> 을 찍는다 — 그 신호를 0.05초 간격으로
            # 짧게 확인하되, 신호가 없는 옛 HTML(자간사냥 스크립트가 없는 문서)은
            # readyState 만 보고 지금까지처럼 넘어간다. 최대 1.3초까지만 기다린다
            # (신호가 끝내 안 오면 그 이상은 안 기다리고 진행 — 무한대기 방지, 2026-09-26).
            #
            # **data-genre 도 같이 본다.** 크롬을 URL 인자로 띄우면 DevToolsActivePort 는
            # 최초 about:blank 탭에서도 곧장 나타난다 — 그 시점에 readyState 만 보면
            # 'complete'(about:blank 는 즉시 완료)를 우리 문서로 착각해 실제 내비게이션이
            # 끝나기 전에 빈 페이지를 읽어 버린다(실측: kiosk-review , 지면수=0 으로
            # 카탈로그 가드가 섰다 — 조판 실패 신호를 정확히 잡아낸 것이지만 원인은
            # 이 폴링의 조기 통과였다). 우리 문서는 예외 없이 `<html data-genre="…">`
            # 를 단다 — 그 속성이 실릴 때까지 기다려 about:blank 오탐을 막는다.
            _준비확인 = (
                "(() => { if (document.readyState !== 'complete') return false;"
                " const 문서 = document.documentElement;"
                " if (!문서.getAttribute('data-genre')) return false;"
                " const 자간사냥있나 = !!document.querySelector('script[src*=\"jachigan\"]')"
                "   && typeof window.__hunt === 'function';"
                " if (자간사냥있나 && 문서.getAttribute('data-jachigan-done') !== '1') return false;"
                " if (document.fonts && document.fonts.status !== 'loaded') return false;"
                " return true; })()")
            # **상한 1.3초는 모자랐다**(적대 검토 H3 '26-09-29): 도식 다시 그림 → 재조판 → 자간 사냥이
            # 끝나 신호가 서기까지 1.12~2.32초(18회 중 14회가 1.3초 넘음, load 57~72)였고, 상한에서 그냥
            # 읽자 표지·목차만 든 HWPX(문단 21·표 2, 정상 59·15)가 '스키마 통과'로 나왔다. 신호는
            # fonts.ready 뒤 늘 서므로(jachigan.js run) 넉넉히 기다리고, 그래도 안 서면 반쯤 조판된 화면을
            # 읽지 않고 멈춘다(조용한 실패 금지). 준비가 빨리 되면 그만큼만 기다린다.
            # 자간 사냥 스크립트 **태그만 있고 실리지 못한** HTML(../jachigan.js 가 없는 곳으로 옮긴 사본 —
            # 세션 방 밖 폴더)은 신호가 영영 안 선다. readyState=complete 면 동기 스크립트는 다 돌았으므로
            # window.__hunt(jachigan.js 가 실리면 늘 단다)가 없으면 사냥꾼 없는 옛 HTML 과 같게 본다
            # ('26-09-29 실측: 자산 없는 방에 옮긴 추적 표본 41/41 이 25초 뒤 멈췄다 — 옛 1.3초는 이를 가렸다).
            _기다림시작 = time.monotonic()
            _준비됨 = False
            while time.monotonic() - _기다림시작 < 25:
                try:
                    if _평가(붙을곳, _준비확인):
                        _준비됨 = True
                        break
                except Exception:
                    pass
                time.sleep(0.05)
            if not _준비됨:
                raise SystemExit("화면 조판이 25초 안에 끝나지 않았다 — 반쯤 그려진 화면은 읽지 않는다"
                                 "(다시 내보내 보세요)")
            앞선것 = ([("Emulation.setEmulatedMedia", {"media": "print"})]
                    if 매체 == "print" else [])
            # 규정·보도자료의 '소량 넘침 당기기'(--rg-tighten/--pr-tighten, assemble_
            # regulation.py·assemble_press.py build() 끝 인라인 스크립트)가 화면에서
            # 이미 결정을 내려 <html> 인라인 스타일에 값(예: 0.90)을 박아 둔 채로 이
            # 함수가 열릴 수 있다('26-09-27 재검토 발견, high). 그 값은 매체를 안
            # 가리고(줄간격·여백 계산식이 무조건 곱한다) 화면·인쇄 둘 다에 걸리므로,
            # 여기서 media 를 print 로 바꿔도 그대로 살아 있다 — 줄간격(정본
            # 값)가 207% 처럼 카탈로그 값 집합 밖(연속값)으로 나가 이 함수를 부르는
            # 넷(tohwpx·verify_all·대조·카탈로그) 전부가 "카탈로그 밖의 서식"으로 선다
            # (실측: bench4 M/s4 재조립 → tohwpx 가 문단·줄간격=207·위여백mm=2.7 로 거부).
            # 당기기는 **인쇄 쪽수만 줄이려는 화면 전용 눈속임**이지 문서의 참값이
            # 아니다 — 이 함수가 캐는 것은 참값(구조)이므로, 읽기 전에 1(정본)로
            # 되돌린다. 인라인 스타일을 지우면(removeProperty) 값은 각 css 의
            # `:root { --rg-tighten: 1 }` 기본값으로 돌아간다 — 그 문서를 실제로
            # 화면·인쇄하는 다른 경로(예: --print-to-pdf 로 PDF 를 낼 때)는 이 탭과
            # 무관한 별도 렌더라 영향이 없다. 당기기가 없는 장르(1p·풀버전·시행문·
            # 슬라이드)엔 이 속성 자체가 없으니 그냥 지나간다.
            앞선것 = [("Runtime.evaluate", {
                "expression": "document.documentElement.style.removeProperty('--rg-tighten'),"
                              "document.documentElement.style.removeProperty('--pr-tighten')"})] + 앞선것
            읽은것 = json.loads(_평가(붙을곳, _읽는코드, 앞선것))
            # 도형은 글로 못 옮긴다 — **그 자리를 그대로 찍어** PNG 로 들고 간다.
            # 자리(자리.y 등)는 위 앞선것 이 건 매체 기준으로 잰 것이니, 찍을 때도
            # **같은 매체**를 걸어야 자리가 맞는다(hwpx:F2 — _찍기() 주석 참고).
            for m in 읽은것["마디"]:
                if m["종류"] == "그림" and m.get("자리"):
                    m["png"] = _찍기(붙을곳, m["자리"], 매체)
            return 읽은것
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


def _찍기(붙을곳: str, 자리: dict, 매체: str = "print") -> str | None:
    """그 네모만 크롬으로 찍어 PNG(base64)로 돌려준다.

    배율 3 으로 찍는다 — HWPX 에 넣으면 인쇄 해상도로 쓰이므로 화면 픽셀 그대로면
    글자가 뭉갠다. 실패하면 None 을 주고, 옮기는 쪽이 "도형을 못 옮겼다" 고 고발한다.
    **조용히 빈 자리로 두지 않는다.**

    **매체를 반드시 같은 연결에서 다시 건다(hwpx:F2)** — Emulation 오버라이드는
    연결을 닫으면 풀린다. 예전엔 매체 설정(_평가)과 캡처(_명령)를 **서로 다른
    연결**로 나눠 보내, 캡처 시점엔 이미 화면(screen) CSS(.fr-page 의 margin:
    6mm auto)로 되돌아가 있었다 — 읽기() 가 인쇄 매체(margin:0)에서 잰 자리와
    어긋나, 쪽번호(k)가 커질수록 약 6k mm 씩 위로 밀린 엉뚱한 자리를 찍었다
    (2026-09-27 실측: matchMedia('print').matches 가 새 연결에서 false 로
    되돌아옴 — build/_hwpx_write.py 개조와 같은 날 확인). _명령들() 로 매체
    설정·크기·캡처를 **한 연결**에 실어 보낸다.

    **DeviceMetricsOverride 는 안 건다(hwpx:R7-3)** — 배율은 아래 clip.scale
    하나로만 낸다. 예전(F2 전) 에는 setDeviceMetricsOverride(deviceScaleFactor=3)
    가 캡처와 **다른** 연결(_평가, 매번 새 연결)에서 걸렸다 — 그 연결이 곧바로
    닫혀 오버라이드가 풀린 채로 캡처됐으니 사실상 죽은 코드였고, clip.scale 3
    혼자 배율 3(300%)을 냈다. F2 가 매체·캡처를 한 연결(_명령들)로 묶으며 이
    죽어 있던 오버라이드까지 같은 연결에 얹었더니, 이번엔 실제로 먹어 DPR
    3 과 clip.scale 3 이 곱해져 화소가 9배(300%×300%)로 찍혔다(1161×618 →
    3483×1854 실측). 해상도 이득 없이 PNG 용량·메모리·base64 전송량만 커진다
    (fr-task100-plan 그림 1장 60KB→388KB). setDeviceMetricsOverride 를 빼면
    clip.scale 3 만 남아 의도한 배율 3(위 docstring 그대로)으로 돌아간다.
    """
    if not (자리.get("폭") and 자리.get("높이")):
        return None
    앞선것 = [("Emulation.setEmulatedMedia", {"media": "print"})] if 매체 == "print" else []
    *_, 받 = _명령들(붙을곳, [
        ("Page.enable", {}),
        *앞선것,
        ("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": True,
            "clip": {"x": 자리["x"], "y": 자리["y"],
                     "width": 자리["폭"], "height": 자리["높이"], "scale": 3}}),
    ])
    return (받 or {}).get("data")


def _명령들(url: str, 목록: list[tuple[str, dict]]) -> list[dict | None]:
    """CDP 명령 여러 개를 **같은 연결**에서 차례로 보내고, 각각의 result 를 순서대로 돌려준다.

    `_명령()`(단일 명령·매번 새 연결)과 `_평가()`(앞선것+Runtime.evaluate 한 벌)로는
    "매체를 걸고 그 상태에서 찍는다" 를 표현할 수 없었다 — 두 함수를 이어 부르면
    그 사이에 연결이 한 번 끊어진다. id 를 명령 차례(1부터)로 매겨 보내고, 받는
    프레임마다 id 로 결과를 모았다가 같은 차례로 돌려준다.
    """
    from urllib.parse import urlparse
    u = urlparse(url)
    s = socket.create_connection((u.hostname, u.port), timeout=60)
    키 = base64.b64encode(os.urandom(16)).decode()
    s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n"
               % (u.path, u.hostname, u.port, 키)).encode())
    버퍼 = b""
    while b"\r\n\r\n" not in 버퍼:
        버퍼 += s.recv(4096)
    남은 = 버퍼.split(b"\r\n\r\n", 1)[1]

    def 던지기(몸: bytes):
        가림 = os.urandom(4)
        n = len(몸)
        머리 = b"\x81" + bytes([0x80 | (n if n < 126 else 126 if n < 65536 else 127)])
        if 126 <= n < 65536:
            머리 += struct.pack(">H", n)
        elif n >= 65536:
            머리 += struct.pack(">Q", n)
        s.sendall(머리 + 가림 + bytes(b ^ 가림[i % 4] for i, b in enumerate(몸)))

    for i, (수단, 인자) in enumerate(목록, start=1):
        던지기(json.dumps({"id": i, "method": 수단, "params": 인자}).encode())

    def 받기(k):
        nonlocal 남은
        while len(남은) < k:
            조각 = s.recv(1 << 20)
            if not 조각:
                return None
            남은 += 조각
        앞, 남은 = 남은[:k], 남은[k:]
        return 앞

    답들: dict[int, dict] = {}
    try:
        while len(답들) < len(목록):
            h = 받기(2)
            if h is None:
                break
            길이 = h[1] & 0x7F
            if 길이 == 126:
                길이 = struct.unpack(">H", 받기(2))[0]
            elif 길이 == 127:
                길이 = struct.unpack(">Q", 받기(8))[0]
            원 = 받기(길이)
            if 원 is None:
                break
            답 = json.loads(원.decode("utf-8", "replace"))
            아이디 = 답.get("id")
            if isinstance(아이디, int) and 1 <= 아이디 <= len(목록):
                답들[아이디] = 답.get("result")
    finally:
        s.close()
    return [답들.get(i) for i in range(1, len(목록) + 1)]


def _명령(url: str, 수단: str, 인자: dict):
    """CDP 명령 하나를 보내고 그 결과를 받는다."""
    import base64 as _b64
    from urllib.parse import urlparse
    u = urlparse(url)
    s = socket.create_connection((u.hostname, u.port), timeout=60)
    키 = _b64.b64encode(os.urandom(16)).decode()
    s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n"
               % (u.path, u.hostname, u.port, 키)).encode())
    버퍼 = b""
    while b"\r\n\r\n" not in 버퍼:
        버퍼 += s.recv(4096)
    남은 = 버퍼.split(b"\r\n\r\n", 1)[1]

    몸 = json.dumps({"id": 1, "method": 수단, "params": 인자}).encode()
    가림 = os.urandom(4)
    n = len(몸)
    머리 = b"\x81" + bytes([0x80 | (n if n < 126 else 126 if n < 65536 else 127)])
    if 126 <= n < 65536:
        머리 += struct.pack(">H", n)
    elif n >= 65536:
        머리 += struct.pack(">Q", n)
    s.sendall(머리 + 가림 + bytes(b ^ 가림[i % 4] for i, b in enumerate(몸)))

    def 받기(k):
        nonlocal 남은
        while len(남은) < k:
            조각 = s.recv(1 << 20)
            if not 조각:
                return None
            남은 += 조각
        앞, 남은 = 남은[:k], 남은[k:]
        return 앞

    while True:
        h = 받기(2)
        if h is None:
            s.close()
            return None
        길이 = h[1] & 0x7F
        if 길이 == 126:
            길이 = struct.unpack(">H", 받기(2))[0]
        elif 길이 == 127:
            길이 = struct.unpack(">Q", 받기(8))[0]
        원 = 받기(길이)
        if 원 is None:
            s.close()
            return None
        답 = json.loads(원.decode("utf-8", "replace"))
        if 답.get("id") == 1:
            s.close()
            return 답.get("result")


def _평가(url: str, 코드: str, 앞선것=()) -> str:
    """의존성 없이 쓰는 최소 웹소켓. 앞선것을 먼저 던지고 마지막에 코드를 평가한다."""
    from urllib.parse import urlparse
    u = urlparse(url)
    s = socket.create_connection((u.hostname, u.port), timeout=60)
    키 = base64.b64encode(os.urandom(16)).decode()
    s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n"
               % (u.path, u.hostname, u.port, 키)).encode())
    버퍼 = b""
    while b"\r\n\r\n" not in 버퍼:
        버퍼 += s.recv(4096)
    남은 = 버퍼.split(b"\r\n\r\n", 1)[1]

    def 던지기(몸: bytes):
        가림 = os.urandom(4)
        n = len(몸)
        머리 = b"\x81" + bytes([0x80 | (n if n < 126 else 126 if n < 65536 else 127)])
        if 126 <= n < 65536:
            머리 += struct.pack(">H", n)
        elif n >= 65536:
            머리 += struct.pack(">Q", n)
        s.sendall(머리 + 가림 + bytes(b ^ 가림[i % 4] for i, b in enumerate(몸)))

    for i, (수단, 인자) in enumerate(앞선것, start=2):
        던지기(json.dumps({"id": i, "method": 수단, "params": 인자}).encode())
    던지기(json.dumps({"id": 1, "method": "Runtime.evaluate",
                     "params": {"expression": 코드, "returnByValue": True,
                                "awaitPromise": True}}).encode())

    def 받기(k):
        nonlocal 남은
        while len(남은) < k:
            조각 = s.recv(1 << 20)
            if not 조각:
                raise SystemExit("웹소켓이 끊겼다")
            남은 += 조각
        앞, 남은 = 남은[:k], 남은[k:]
        return 앞

    while True:
        h = 받기(2)
        길이 = h[1] & 0x7F
        if 길이 == 126:
            길이 = struct.unpack(">H", 받기(2))[0]
        elif 길이 == 127:
            길이 = struct.unpack(">Q", 받기(8))[0]
        답 = json.loads(받기(길이).decode("utf-8", "replace"))
        if 답.get("id") == 1:
            s.close()
            r = 답.get("result", {})
            if "exceptionDetails" in r:
                raise SystemExit("화면 읽기 실패: " + json.dumps(r["exceptionDetails"])[:500])
            return r["result"]["value"]


if __name__ == "__main__":
    for 것 in sys.argv[1:]:
        d = 읽기(Path(것))
        print(f"■ {Path(것).name} — 장르 {d['장르']} · 마디 {len(d['마디'])}개 · "
              f"지면 {d['쪽']['지면반']} ×{d['쪽']['지면수']} · 여백 {d['쪽']['여백mm']}")
        셈 = {}
        for m in d["마디"]:
            셈[m["종류"]] = 셈.get(m["종류"], 0) + 1
        print("   종류:", 셈)
        역할없음 = [m for m in d["마디"] if not m.get("역할") and m["종류"] != "장식"]
        if 역할없음:
            print(f"   역할 없는 마디 {len(역할없음)}개 — 예: "
                  f"{[ (m.get('반') or '')[:16] for m in 역할없음[:5] ]}")
