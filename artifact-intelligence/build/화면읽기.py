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
from 크롬찾기 import 크롬

# ── 화면에서 읽어 오는 코드 ────────────────────────────────────────────────
# 이 안에서 하는 일은 딱 둘이다. ① 무엇이 마디인지 정한다 ② 그 마디의 최종 서식을 잰다.
# 무엇을 HWPX 로 어떻게 옮길지는 여기서 정하지 않는다(그건 build/역할.py 가 한다).
_읽는코드 = r"""
(() => {
  const PX = 3.779527559;                       // 1mm
  const mm  = v => Math.round(parseFloat(v || 0) / PX * 100) / 100;
  const pt  = v => Math.round(parseFloat(v || 0) * 0.75 * 10) / 10;
  const 색 = v => {
    const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(v || '');
    if (!m) return null;
    if (m[4] !== undefined && parseFloat(m[4]) === 0) return null;      // 투명은 없는 것
    return '#' + [1,2,3].map(i => (+m[i]).toString(16).padStart(2,'0')).join('').toUpperCase();
  };
  // 그라데이션 배경의 대표색 — **첫 스톱**을 단색 근사로 쓴다(gov 바는 첫 스톱이
  // 포인트색이라 정직한 근사다). 안 읽으면 backgroundColor 가 투명이라 배경 없는
  // 장식으로 판정돼 gov 바·장 표제 띠가 통째로 사라진다(2026-08-13 CSS 전수 갭).
  const 그라색 = v => {
    if (!v || !/gradient\(/.test(v)) return null;
    const m = /rgba?\([^)]+\)/.exec(v);
    return m ? 색(m[0]) : null;
  };

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
    if (mk && mk.textContent.trim()) return { 글자: mk.textContent.trim(), 만든것: false };
    return null;
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
      색: 색(s.color), 바탕: 색(s.backgroundColor) || 그라색(s.backgroundImage),
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
      테두리: ['Top','Right','Bottom','Left'].map(d =>
        parseFloat(s['border'+d+'Width']) > 0
          ? { 굵기mm: mm(s['border'+d+'Width']), 색: 색(s['border'+d+'Color']),
              // 선종류(dashed·dotted)를 안 읽으면 목차 점선·점선 박스가 실선이 된다
              // (2026-08-13 CSS 전수 갭 — 사용처 8곳 실측)
              선종류: s['border'+d+'Style'] } : null),
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
    return 뭉침.filter(x => x.줄바꿈 || x.빈자리mm || (x.글 && x.글.trim() !== ''));
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
    return { 행: 행들, 폭mm: Math.round(tbl.getBoundingClientRect().width / PX * 100) / 100,
             정렬: s.marginLeft === 'auto' ? 'CENTER' : 'LEFT',
             // 겉선은 셀이 아니라 <table> 요소에 걸린다(기본표 상·하 0.4mm) — 안 읽으면
             // 셀 실측 전이(4-A) 이후 겉선이 통째로 사라진다(2026-08-13 한글 뷰어 육안 실측)
             테두리: ['Top','Right','Bottom','Left'].map(d =>
               parseFloat(s['border'+d+'Width']) > 0
                 ? { 굵기mm: mm(s['border'+d+'Width']), 색: 색(s['border'+d+'Color']),
                     선종류: s['border'+d+'Style'] } : null) };
  };

  // ── 문서 차례대로 걷는다 ──
  const 마디 = [];
  const 본것 = new WeakSet();
  const 걷기 = (el, 쪽번호) => {
    for (const c of el.children) {
      if (!보임(c) || 본것.has(c)) continue;
      // 도형·그림 — svgfig.js 가 그린 SVG 와 <img> 는 글로 옮길 수 없다.
      // 그렇다고 버리면 안 된다: 2026-08-05 풀보고서 관공서본에서 SVG 안 글자 212자가
      // 통째로 사라졌는데 마디 짝짓기는 "다 맞다" 고 했다(독립된 눈이 잡았다).
      // 여기서는 **어디를 찍을지**만 정하고, 실제 찍기는 tohwpx 가 크롬에 시킨다.
      const 그림 = (c.tagName === 'SVG' || c.tagName === 'svg' || c.tagName === 'IMG')
                 ? c : c.querySelector(':scope > svg, :scope > img');
      if (그림) {
        본것.add(c); c.querySelectorAll('*').forEach(x => 본것.add(x));
        const gr = 그림.getBoundingClientRect();
        마디.push({
          종류: '그림',
          역할: (c.closest('[data-ent]') || {}).dataset?.ent || null,
          반: c.className || c.tagName.toLowerCase(),
          글: (c.innerText || '').trim(),           // 도형 안 글자 — 빠짐 검사가 이걸 센다
          쪽: 쪽번호,
          자리: { x: gr.left + scrollX, y: gr.top + scrollY,
                 폭: gr.width, 높이: gr.height },
          폭mm: Math.round(gr.width / PX * 100) / 100,
          높이mm: Math.round(gr.height / PX * 100) / 100,
          서식: 서식(c),
        });
        continue;
      }
      if (c.tagName === 'TABLE') {
        본것.add(c);
        c.querySelectorAll('*').forEach(x => 본것.add(x));   // 셀을 다시 세지 않는다
        마디.push({ 종류: '표', 역할: (c.closest('[data-ent]') || {}).dataset?.ent || null,
                   경로: c.getAttribute('data-path'), 쪽: 쪽번호, 표: 표읽기(c) });
        continue;
      }
      // 표를 감싸기만 하는 껍데기(.rg-table-wrap)를 마디로 세면 표가 두 벌 나간다.
      // 2026-08-05 감리 지적: 규정에서 글자 80자가 두 번 세어졌다.
      const 안에표 = c.querySelector(':scope > table');
      if (안에표) { 걷기(c, 쪽번호); continue; }

      // 가로 배치(grid/flex 로 칸을 나눈 줄) — 시행문 두문(수신·경유·제목)·결재란·결문이
      // 표가 아니라 CSS grid 다. 한 문단으로 뭉개면 '수신수신자 참조' 처럼 라벨과 값이
      // 붙는다(2026-08-05 한글 뷰어로 직접 보고 알았다 — 글자는 다 있어서 값 대조는
      // 통과했다). **칸이 나뉘어 있으면 나뉜 채로 옮긴다.**
      const 칸나눔 = (el) => {
        const 아이 = [...el.children].filter(보임);
        if (아이.length < 2) return null;
        const 상자 = 아이.map(x => ({ el: x, r: x.getBoundingClientRect() }));
        // 세로로는 겹치고 가로로는 안 겹쳐야 '한 줄에 나란히' 다
        const 줄 = 상자[0].r;
        for (const b of 상자) {
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
        마디.push({
          종류: '가로줄',
          역할: (c.closest('[data-ent]') || {}).dataset?.ent ||
                (c.querySelector('[data-ent]') || {}).dataset?.ent || null,
          반: c.className || c.tagName.toLowerCase(),
          글: (c.innerText || '').trim(), 쪽: 쪽번호, 서식: 서식(c),
          // 칸 폭은 상자 폭이 아니라 **다음 칸이 시작하는 자리까지**로 잡는다.
          // flex `gap` 은 상자 밖에 있어서, 상자 폭만 쓰면 표가 그 틈만큼 좁아지고
          // 라이브러리가 남는 폭을 나눠 채워 글자가 밀린다(2026-08-05 결문에서 4mm 씩).
          칸: 칸들.map((b, i, 전) => ({
            글: (b.el.innerText || '').trim(),
            폭mm: Math.round(((i + 1 < 전.length ? 전[i+1].r.left : c.getBoundingClientRect().right)
                             - b.r.left) / PX * 100) / 100,
            서식: 서식(b.el), 속: 속읽기(b.el, null),
            경로: b.el.getAttribute('data-path'),
          })),
        });
        continue;
      }

      const 자식덩어리 = [...c.children].some(x => 덩어리태그.has(x.tagName) && 보임(x));
      const 글 = (c.innerText || '').trim();
      const r = c.getBoundingClientRect();
      if (덩어리태그.has(c.tagName) && !자식덩어리) {
        본것.add(c);
        const mk = 마커읽기(c);
        const 속 = 속읽기(c, mk && mk.글자);
        const 있나 = 속.some(x => x.글 && x.글.trim()) || 글;
        const 장식 = !있나 && (색(getComputedStyle(c).backgroundColor) || r.height >= 0.3);
        if (!있나 && !장식) continue;
        마디.push({
          종류: 있나 ? '문단' : '장식',
          역할: (c.closest('[data-ent]') || {}).dataset?.ent || null,
          경로: c.getAttribute('data-path') ||
                (c.querySelector('[data-path]') || {}).getAttribute?.('data-path') || null,
          반: c.className || c.tagName.toLowerCase(), 태그: c.tagName.toLowerCase(),
          글: 글, 마커: mk, 속: 속, 서식: 서식(c), 쪽: 쪽번호,
        });
      } else {
        걷기(c, 쪽번호);
      }
    }
  };
  지면들.forEach((p, i) => 걷기(p, i + 1));

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
    마디: 마디,
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
        p = subprocess.Popen(
            [크롬경로, "--headless", "--disable-gpu", "--remote-debugging-port=0",
             f"--user-data-dir={tmp}/u", "--no-first-run", "--no-default-browser-check",
             html경로.resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            붙을곳 = None
            for _ in range(160):
                try:
                    항 = int((Path(tmp) / "u" / "DevToolsActivePort")
                            .read_text().splitlines()[0])
                    j = json.load(urllib.request.urlopen(f"http://127.0.0.1:{항}/json", timeout=1))
                    쓸것 = [t for t in j if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                    if 쓸것:
                        붙을곳 = 쓸것[0]["webSocketDebuggerUrl"]
                        break
                except Exception:
                    pass
                time.sleep(0.25)
            if not 붙을곳:
                raise SystemExit("크롬 디버깅에 못 붙었다")
            time.sleep(1.3)                     # 글꼴·자간 사냥이 앉을 때까지
            앞선것 = ([("Emulation.setEmulatedMedia", {"media": "print"})]
                    if 매체 == "print" else [])
            읽은것 = json.loads(_평가(붙을곳, _읽는코드, 앞선것))
            # 도형은 글로 못 옮긴다 — **그 자리를 그대로 찍어** PNG 로 들고 간다.
            for m in 읽은것["마디"]:
                if m["종류"] == "그림" and m.get("자리"):
                    m["png"] = _찍기(붙을곳, m["자리"])
            return 읽은것
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


def _찍기(붙을곳: str, 자리: dict) -> str | None:
    """그 네모만 크롬으로 찍어 PNG(base64)로 돌려준다.

    배율 3 으로 찍는다 — HWPX 에 넣으면 인쇄 해상도로 쓰이므로 화면 픽셀 그대로면
    글자가 뭉갠다. 실패하면 None 을 주고, 옮기는 쪽이 "도형을 못 옮겼다" 고 고발한다.
    **조용히 빈 자리로 두지 않는다.**
    """
    if not (자리.get("폭") and 자리.get("높이")):
        return None
    답 = _평가(붙을곳, "1", [
        ("Page.enable", {}),
        ("Emulation.setDeviceMetricsOverride",
         {"width": 0, "height": 0, "deviceScaleFactor": 3, "mobile": False}),
    ])
    받 = _명령(붙을곳, "Page.captureScreenshot", {
        "format": "png", "captureBeyondViewport": True,
        "clip": {"x": 자리["x"], "y": 자리["y"],
                 "width": 자리["폭"], "height": 자리["높이"], "scale": 3}})
    return (받 or {}).get("data")


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
