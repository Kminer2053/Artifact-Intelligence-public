#!/usr/bin/env python3
"""범용 인라인 편집기 — 장르를 모르는 편집기 하나로 모든 문서를 다룬다.

편집 대상: 표지 필드 · 요약(사내표준형) · 장 → 절 → 항목 드릴다운 · 박스 7종 ·
          도식 6종 · 표 · 별첨. 목차와 쪽번호는 기계 산출이라 편집 대상이 아니다.

풀버전 특유:
- 스타일 변형 전환(사내표준형 ↔ 정부부처형) + 포인트색 — 같은 3층 내용이 두 판으로 즉시 전환
- 글꼴 3종(내장 표준·명조·한글 원본) — 바꾸면 조판을 다시 잡는다
- 조작할 때마다 재조판 → 문단 분절 방지·줄간격 자동 조정이 즉시 반영, 넘침은 붉은 표식
- 박스 종류 전환 7종은 즉시 미리보기(1p 표 스타일 패턴 이식)
- 도식은 data-fig 스펙을 왕복 — 라벨 수정은 SVG를 즉시 다시 그리고(어절 wrap 이식),
  유형·단계 변경은 스펙에 기록해 재조립 때 반영

저장: ws-edit-<fn> = {doc(3층 구조 복원), instructions, ops} → "고쳐놨어"로 반영
사용: python3 workspace/render_editor_fr.py --all | <filename>
"""
import importlib.util as _iu
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 코드뿌리(CSS·JS·프로파일)

# 산출물·편집 화면·골격은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
_사양 = _iu.spec_from_file_location("자료뿌리", str(ROOT / "build" / "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

SAMPLES = Path(자료뿌리.산출물뿌리())
EDITORS = Path(자료뿌리.편집화면뿌리())

# WP-F1 마무리 — 편집기 크롬(조작 UI)을 브랜드 토큰으로(흰 테마, 사장님 판정 2026-08-08).
# **문서 영역 셀렉터·구조는 그대로 두고 색 값만 토큰으로 간다** — body/.fr-page 오버라이드
# 같은 구조 규칙을 건드리면 편집 중 레이아웃이 달라져 §4-3 "문서 영역 스타일은 손대지
# 마라"를 어긴다. 이 화면엔 애초에 다크 모드 토글이 없었다 — edit-bar 가 밝기와 무관하게
# 늘 Ink 배경인 것도 토글과는 별개다(ui-tokens.css 의 --ai-color-*-on-dark 3색 주석 참고).
# 토큰 파일은 산출 위치가 갈린다(workspace/editors/ 와 buildplan/skeletons/edit/) — gen() 이
# @@TOKENS_HREF@@ 를 그 자리에 맞는 상대경로로 채운다(SCRIPT 의 @@FN@@ 치환과 같은 방식).
CHROME = """
<link rel="stylesheet" href="@@TOKENS_HREF@@" data-editor>
<style data-editor>
  body { padding-top: 46px !important; margin-right: 268px !important; }
  .fr-page { margin-left: auto !important; margin-right: auto !important; }   /* 문서를 편집 영역 가운데로 */
  .edit-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 99; background: var(--ai-color-ink);
    color: var(--ai-color-white); font: 13px/1.4 var(--ai-font-sans);
    padding: 7px 14px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }
  .edit-bar .grp { display: flex; gap: 6px; align-items: center; }
  .edit-bar button { border: none; border-radius: var(--ai-radius-sm); padding: 5px 10px; font: inherit;
    background: color-mix(in srgb, var(--ai-color-white) 16%, transparent);
    color: var(--ai-color-white); cursor: pointer; transition: background var(--ai-motion-fast); }
  .edit-bar button:hover { background: var(--ai-color-signal); }
  .edit-bar button.on { background: var(--ai-color-signal); color: var(--ai-color-white); font-weight: 700; }
  .edit-bar .st { color: var(--ai-color-muted-on-dark); } .edit-bar .st.on { color: var(--ai-color-signal-on-dark); }
  .edit-bar .warn { color: var(--ai-color-issue-on-dark); font-weight: 700; }
  .edit-bar input[type=color] { width: 26px; height: 22px; border: none; background: none; padding: 0; }
  .font-switcher { display: none !important; }
  .crop-wrap { position: relative; display: inline-block; }
  .crop-sel { pointer-events: none; }
  /* 이어서 하기 / 판 보관 — 화면 맨 위에 붙는 알림 띠. 색은 알림.기다림/나쁨 과 같은
     토큰 쌍(review/issue tint·line·ink)을 쓴다 — app.html 의 같은 뜻 알림과 통일. */
  .resume-bar { position: fixed; top: 46px; left: 0; right: 268px; z-index: 97;
    background: var(--ai-color-review-tint); border-bottom: 1px solid var(--ai-color-review-line);
    color: var(--ai-color-review-ink); padding: 9px 14px; font: 13px/1.5 var(--ai-font-sans); }
  .resume-bar.danger { background: var(--ai-color-issue-tint); border-bottom-color: var(--ai-color-issue-line);
    color: var(--ai-color-issue-ink); }
  .resume-bar .row { margin-top: 6px; display: flex; gap: 6px; }
  .resume-bar button { border: none; border-radius: var(--ai-radius-sm); padding: 5px 11px; font: inherit;
    background: var(--ai-color-ink); color: var(--ai-color-white); cursor: pointer; }
  /* '좋음'에 해당하는 확정 동작 — 브랜드 6색엔 Mint(AI 전용) 말고 다른 초록이 없어
     Signal Blue 를 쓴다(app.html 의 .알림.좋음 과 같은 결정, 부록 §1-1). */
  .resume-bar button.good { background: var(--ai-color-signal); }
  .resume-bar button.danger { background: var(--ai-color-issue); }
  .panel { position: fixed; top: 46px; right: 0; bottom: 0; width: 268px; z-index: 98;
    overflow-y: auto; background: var(--ai-color-white); border-left: 1px solid var(--ai-color-line);
    padding: 13px; font: 13px/1.5 var(--ai-font-sans); box-sizing: border-box; }
  .panel h3 { font-size: 12px; color: var(--ai-color-muted); margin: 0 0 4px; font-weight: 600; }
  .panel .ent { font-size: 15px; font-weight: 700; color: var(--ai-color-signal); margin-bottom: 2px; }
  .panel .hint { color: var(--ai-color-muted); font-size: 12px; margin: 4px 0 9px; }
  .panel button { display: block; width: 100%; margin: 5px 0; padding: 7px 9px; text-align: left;
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-agent-panel); cursor: pointer; font: inherit; }
  .panel button:hover { background: var(--ai-color-signal-tint); border-color: var(--ai-color-signal); }
  .panel button.sel { background: var(--ai-color-signal); color: var(--ai-color-white); border-color: var(--ai-color-signal); }
  .panel .danger { border-color: var(--ai-color-issue-line); background: var(--ai-color-issue-tint); }
  .panel .danger:hover { background: color-mix(in srgb, var(--ai-color-issue) 20%, var(--ai-color-white)); border-color: var(--ai-color-issue); }
  .panel textarea, .panel input[type=text] { width: 100%; font: inherit; font-size: 12.5px;
    padding: 6px; border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm); box-sizing: border-box; }
  .panel textarea { min-height: 66px; resize: vertical; }
  .panel .row { display: flex; gap: 5px; } .panel .row button { flex: 1; text-align: center; }
  .panel .explain { background: var(--ai-color-signal-tint-2); border-left: 3px solid var(--ai-color-signal);
    padding: 9px 10px; border-radius: 0 6px 6px 0; font-size: 12.5px; line-height: 1.65;
    color: var(--ai-color-ink-soft); margin: 6px 0 4px; }
  .panel .notes { margin-top: 12px; border-top: 1px solid var(--ai-color-line); padding-top: 9px;
    font-size: 12px; color: var(--ai-color-muted); }
  .panel .notes li { margin: 3px 0; }
  .ent-sel { outline: 2px solid var(--ai-color-signal) !important; outline-offset: 3px; border-radius: 2px;
    background: var(--ai-color-signal-tint-strong); }
  .has-note { box-shadow: -3px 0 0 0 var(--ai-color-review); }
  [contenteditable="true"] { outline: 2px solid var(--ai-color-signal) !important; background: var(--ai-color-signal-tint); }
  /* ── 슬라이드 자유배치 — 이동 그립(fp-grip)과 8방향 크기 핸들(fp-h). 드래그는 그립·핸들에서만
     시작하므로 본문 클릭(자식 개체 선택·편집)과 안 부딪힌다. ── */
  .sl-free .sl-placed.fp-move { outline: 1.5px dashed var(--ai-color-agent); outline-offset: 2px; }
  .sl-free .sl-placed .fp-grip { position: absolute; left: -1.5px; top: -22px; height: 20px; padding: 0 7px;
    background: var(--ai-color-agent); color: var(--ai-color-white); border-radius: 4px 4px 0 0; cursor: move; z-index: 31;
    display: flex; align-items: center; gap: 4px; font: 11px var(--ai-font-sans); white-space: nowrap; }
  .sl-free .sl-placed .fp-h { position: absolute; width: 12px; height: 12px; background: var(--ai-color-agent);
    border: 2px solid var(--ai-color-white); border-radius: 50%; box-sizing: border-box; z-index: 30; }
  .fp-nw{left:-6px;top:-6px;cursor:nwse-resize} .fp-ne{right:-6px;top:-6px;cursor:nesw-resize}
  .fp-se{right:-6px;bottom:-6px;cursor:nwse-resize} .fp-sw{left:-6px;bottom:-6px;cursor:nesw-resize}
  .fp-n{left:calc(50% - 6px);top:-6px;cursor:ns-resize} .fp-s{left:calc(50% - 6px);bottom:-6px;cursor:ns-resize}
  .fp-e{right:-6px;top:calc(50% - 6px);cursor:ew-resize} .fp-w{left:-6px;top:calc(50% - 6px);cursor:ew-resize}
  #fr-toc .fr-content::after { content: "목차와 쪽번호는 자동으로 만들어집니다";
    position: absolute; left: 0; right: 0; bottom: 3mm; text-align: center;
    font: 10px var(--ai-font-sans); color: var(--ai-color-muted); }
  /* 복사 완료 토스트 — 디자인 앱 v1.1 의 .toast 그대로(흰 배경 + Ink 글자, 색을 안 쓴다) */
  .copy-note { position: fixed; bottom: 14px; left: 42%; background: var(--ai-color-white);
    color: var(--ai-color-ink); padding: 8px 18px; border-radius: 20px; font: 13px var(--ai-font-sans);
    box-shadow: var(--ai-shadow-card); display: none; z-index: 99; }
  /* 능동 동의 카드(WP-S10 2차-B, "리터칭" 훅 — 문구 다듬기 사장님 판정 2026-08-09) — "이 부분
     (비식별)" 같은 알쏭달쏭한 말을 걷어내고 머리에 로고를 얹는다. Mint 는 로고 마크
     하나에만 남긴다(부록 §1-1 "Mint 남용 금지" — 동의 신호는 허용 예외, app.html 의
     .동의카드 와 같은 결정). icons.svg 는 이 편집기의 산출 위치가 둘로 갈려(workspace/
     editors/ 와 buildplan/skeletons/edit/, gen() 의 TOKENS_HREF 참고) <use href> 상대경로가
     자리마다 다르다 — 그 자리표시자를 하나 더 늘리는 대신 logo-mark 의 path 데이터(작은
     정적 마크)를 그대로 인라인해 참조 문제를 아예 없앤다. stroke=currentColor 로 icons.svg
     의 §1-4 규칙(심볼에 색을 안 박고 쓰는 자리에서 켠다)을 그대로 잇는다. */
  .consent-card { position: fixed; right: 14px; bottom: 14px; z-index: 100; width: min(360px, 86vw);
    background: var(--ai-color-white); border-radius: var(--ai-radius-md);
    box-shadow: var(--ai-shadow-card); overflow: hidden; }
  .consent-card .cc-head { display: flex; align-items: center; gap: 9px; padding: 12px 14px 11px;
    border-bottom: 1px solid var(--ai-color-line); }
  .consent-card .cc-head .cc-logo { width: 22px; height: 22px; flex: none; color: var(--ai-color-agent);
    fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .consent-card .cc-head .cc-word { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .consent-card .cc-head .cc-word b { font-family: var(--ai-font-heading); font-weight: 800;
    font-size: 13.5px; color: var(--ai-color-ink); }
  .consent-card .cc-head .cc-word span { font-size: 10.5px; color: var(--ai-color-muted); }
  .consent-card .cc-body { padding: 12px 14px; }
  .consent-card p { margin: 0 0 10px; font: 12.5px/1.6 var(--ai-font-sans); color: var(--ai-color-ink-soft);
    white-space: pre-wrap; }
  /* "왜" 칸(신규) — 선택 입력. 값을 넣고 [남기기] 를 누르면 `지시`(이유)로 실려
     `_항목빚기` 가 비식별한 뒤 코퍼스에 남는다(feedback/corpus.py, 손 안 댐 — 부르기만). */
  .consent-card .cc-why { margin: 0 0 10px; }
  .consent-card .cc-why label { display: block; font-size: 11px; line-height: 1.5;
    color: var(--ai-color-muted); margin-bottom: 4px; }
  .consent-card .cc-why input[type="text"] { width: 100%; box-sizing: border-box; font: inherit;
    font-size: 12px; padding: 6px 8px; border: 1px solid var(--ai-color-line);
    border-radius: var(--ai-radius-sm); }
  .consent-card .cc-why input[type="text"]:focus { outline: none; border-color: var(--ai-color-signal); }
  /* 유의 안내 — 비식별기(feedback/corpus.py)는 메일·링크·숫자·기관·이름을 가리나 완벽하지
     않아 입력칸에서 미리 알린다(사장님 방침 2026-08-09). */
  .consent-card .cc-why .cc-hint { margin: 6px 0 0; font-size: 10.5px; line-height: 1.5;
    color: var(--ai-color-muted); }
  .consent-card .cc-row { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
  .consent-card button { border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    padding: 6px 10px; font: 12.5px var(--ai-font-sans); background: var(--ai-color-white);
    color: var(--ai-color-ink); cursor: pointer; }
  .consent-card button.good { background: var(--ai-color-ink); color: var(--ai-color-white); border: 0; }
</style>
"""

SCRIPT = r"""
<script data-editor>
(() => {
// 자가검사 — ?selfcheck=1 이면 왕복 불변식을 스스로 확인하고 결과를 제목에 남긴다.
// (정적 패턴 검사는 오탐만 냈다. 진짜 검사는 '저장했다 다시 읽으면 같은가'다.)
if (location.search.includes('selfcheck=1')) {
  setTimeout(async () => {
    const w = ms => new Promise(r => setTimeout(r, ms));
    await w(1400);
    try {
      const el = document.getElementById('fr-doc');
      if (!el) { document.title = 'SELFCHECK skip 모델없음'; return; }
      const src = JSON.parse(el.textContent);
      localStorage.removeItem(KEY);
      document.dispatchEvent(new Event('input'));
      await w(900);
      const saved = (JSON.parse(localStorage.getItem(KEY) || '{}')).doc || {};
      const norm = o => JSON.stringify(o, (k, v) =>
        (v && typeof v === 'object' && !Array.isArray(v))
          ? Object.fromEntries(Object.keys(v).sort().map(x => [x, v[x]])) : v);
      const diffs = [];
      const walk = (a, b, p) => {
        if (norm(a) === norm(b)) return;
        if (a && b && typeof a === 'object' && typeof b === 'object')
          new Set([...Object.keys(a), ...Object.keys(b)]).forEach(k => walk(a[k], b[k], p + '.' + k));
        else diffs.push(p);
      };
      walk(src, saved, '');
      const ov = (window.__frOverflow || []).length;
      document.title = 'SELFCHECK ' + (diffs.length ? 'FAIL ' + diffs.slice(0, 3).join(' ') : 'OK')
        + ' overflow=' + ov;
    } catch (e) { document.title = 'SELFCHECK ERROR ' + e.message; }
  }, 0);
}
window.addEventListener('error', e => {
  if (location.search.includes('selfcheck=1'))
    document.title = 'SELFCHECK ERROR ' + e.message;
});
const FN = '@@FN@@';
const KEY = 'ws-edit-' + FN;
// 작업 채널 — 세션이 어떻게 시작됐는지로 가른다. 웹앱은 serve.py 가 http 로 서빙하고
// (세션이 자동 유지되고 편집이 /save 로 서버 정본에 확실히 저장·보관된다), 스킬·MCP 는
// 편집기를 파일로 열어(file://) 서버가 없다 — 저장·보관·반영이 채팅의 Claude 를 거쳐야 한다.
// 그래서 '채팅에 알려 주세요' 류는 스킬·MCP 에서만 옳다. 웹앱에선 감추거나 사실대로 바꾼다.
const 채팅표면 = location.protocol === 'file:';
// 문서 글자를 HTML 로 넣기 전에 잠근다 (WP-S2 ③). 이 화면에 실리는 label·붙임 본문·
// 도식 라벨·대기 작업은 **문서에서 온 글**이라 태그가 섞여 있을 수 있다. 이 화면은
// 세션 쿠키와 같은 출처에서 도니, 한 곳만 새도 그 세션 전체가 남의 것이 된다.
const esc = s => String(s === undefined || s === null ? '' : s)
  .replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;',
                               '"': '&quot;', "'": '&#39;' }[c]));
// 1p 본문(.html)만 강조 마크업을 허용한다 — **서버 build/assemble.py 의
// `_허용마크업()` 과 같은 규칙**(강조 span 셋만 살리고 나머지 꺾쇠는 잠근다).
// 여기서 한 번 더 거르는 까닭: 이어서하기(localStorage 버퍼)와 SRCDOC 은 조립기를
// 안 지나고 곧장 innerHTML 로 들어간다 — 조립 산출물만 씻어서는 이 문이 안 닫힌다.
const 강조클래스 = ['num', 'accent', 'delta'];
function 허용마크업(s) {
  const 열림 = /^<span class="([A-Za-z][\w-]*)">/;
  let out = '', 열린 = 0, i = 0;
  s = String(s === undefined || s === null ? '' : s);
  while (i < s.length) {
    if (s[i] !== '<') { out += s[i++]; continue; }
    const m = 열림.exec(s.slice(i, i + 40));
    if (m && 강조클래스.includes(m[1])) { out += m[0]; 열린++; i += m[0].length; continue; }
    if (열린 > 0 && s.startsWith('</span>', i)) { out += '</span>'; 열린--; i += 7; continue; }
    out += '&lt;'; i++;
  }
  return out + '</span>'.repeat(열린);
}
const st = document.querySelector('.edit-bar .st');
const warn = document.querySelector('.edit-bar .warn');
const note = document.querySelector('.copy-note');
const state = { sel: null, notes: {}, ops: [], noteFor: null, editing: null };
const BOXES = ['핵심메시지','총괄목표','결론전환','통계근거','참고사례','절차나열','현황참고'];
const FIGS  = {process:'절차도', cycle:'순환도', converge:'수렴형',
               strategy:'전략체계도', relation:'구조도', stack:'스택막대'};
const LVSPEC = ((PROFILE0 => (PROFILE0['개체'] || {})['항목'])(
  (() => { try { return JSON.parse(document.getElementById('fr-profile').textContent); }
           catch (e) { return {}; } })()) || {})['레벨'] || [['i-l2','○'],['i-l3','-'],['i-l4','※']];
const LVORDER = LVSPEC.map(x => x[0]);
const LV = Object.fromEntries(LVSPEC);

// ── 조판 재실행(문단 분절 방지·줄간격 자동 조정이 매번 다시 걸린다) ──
let reT;
function repaginate() {
  clearTimeout(reT);
  reT = setTimeout(() => {
    if (window.__repaginate) window.__repaginate();   // 골격 등 조판기가 없는 문서는 건너뛴다
    const ov = window.__frOverflow || [];
    warn.textContent = ov.length ? `⚠ 내용이 쪽 밖으로 넘친 곳 ${ov.length}군데` : '';
    if (window.__hunt) window.__hunt();
    save();
  }, 60);
}

// ── 개체 판정: 문서가 선언한 data-ent 를 읽고, 프로파일에서 액션을 꺼낸다 ──
// 편집기는 장르를 모른다. 새 장르는 조립기가 data-ent/data-path를 심고
// ontology/editor-profiles.json 에 항목을 추가하면 그대로 동작한다.
const PROFILE = (() => {
  const el = document.getElementById('fr-profile');
  try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
})() || { genre: '일반', 개체: {}, 상단바: {} };
const ENTS = PROFILE['개체'] || {};

function entInfo(el) {
  if (!el || !el.dataset) return null;
  const ent = el.dataset.ent;
  if (!ent || !ENTS[ent]) return null;
  const spec = ENTS[ent];
  let label = spec['라벨'] || ent;
  if (ent === '표지필드') label += ' — ' + (el.dataset.frf || '');
  else if (ent === '절' || ent === '장') {
    const t = el.dataset.title || (el.querySelector('.tx') || {}).textContent || '';
    if (t.trim()) label += ' — ' + t.trim();
  }
  else if (ent === '되돌림') {
    const q = (el.querySelector('.q') || {}).textContent || '';
    label += ' — ' + (q.trim().slice(0, 12) || (el.dataset.no + '번'));
  }
  else if (ent === '박스') label += ' — ' + (el.dataset.box || '');
  else if (ent === '도식') label += ' — ' + ((spec['유형'] || {})[figSpec(el).type] || figSpec(el).type);
  else if (ent === '항목' && spec['레벨']) {
    // 개체 이름은 구성 설계와 같은 말로 유지하고, 레벨은 뒤에 덧붙인다
    const lv = (spec['레벨'].find(([c]) => el.classList.contains(c)) || [])[1];
    if (lv) label += ' — ' + lv + ' 단계';
  }
  return { type: ent, spec, label };
}
// 구성 요소를 넣고 빼기 / 가능성 값 바꾸기 — 패널 단추와 되돌림 카드가 같은 함수를 쓴다.
// (되돌림의 '한 번에 바꾸기'가 배지·속성 갱신을 빠뜨리면 화면과 저장값이 어긋난다)
function applyToggle(el, next) {
  el.dataset.on = String(next);
  if (next) el.removeAttribute('data-off'); else el.setAttribute('data-off', '1');
  const nm = el.querySelector('.nm');
  if (nm) {
    const o = nm.querySelector('.off');
    if (next && o) o.remove();
    else if (!next && !o) nm.insertAdjacentHTML('beforeend', '<span class="off">제외됨</span>');
  }
}
// 잎 노드의 글자를 갈아끼운다. data-shown 은 손대지 않는다 —
// 그래야 serialize 가 '사람이 고쳤다'고 보고 새 값을 저장한다.
function setText(el, v) {
  el.textContent = v;
}
function cycPre(spec) {
  const l = spec && spec['값라벨'];
  return l === '' ? '' : (l || '가능성');   // 빈 라벨은 값만 보여준다
}
function cycShow(spec, v) { return ((spec && spec['값표시']) || {})[v] || v; }
function applyCycle(el, spec, v) {
  el.dataset.lv = v;
  const s2 = el.querySelector('.lv');
  if (s2) s2.textContent = (cycPre(spec) + ' ' + cycShow(spec, v)).trim();
}
// 되돌아온 카드가 가리키는 '고칠 자리'를 찾는다. 경로는 계획서 안의 위치다.
function planTarget(P) {
  return document.querySelector(`[data-path="${P}"],[data-flag="${P}"],[data-cycle="${P}"]`);
}
// 순서 항목(data-arr)은 컨테이너에 경로가 걸리고 실제 글자는 .tx 에 있다.
// 컨테이너에 그대로 쓰면 번호·설명·다음 단계 안내가 통째로 날아간다.
function planLeaf(t) {
  return t.dataset.arr ? (t.querySelector('.tx') || t) : t;
}
function planCur(t) {
  if (t.dataset.flag) return String(t.dataset.on !== 'false');
  if (t.dataset.cycle) return t.dataset.lv || '';
  return textOf(planLeaf(t)).trim();
}

function select(el) {
  document.querySelectorAll('.ent-sel').forEach(x => x.classList.remove('ent-sel'));
  state.sel = el; if (el) el.classList.add('ent-sel');
  renderPanel();
}
document.addEventListener('click', e => {
  if (e.target.closest('.panel,.edit-bar')) return;
  if (e.target.isContentEditable) return;
  if (state.editing) finishEdit();
  const f = e.target.closest('[data-frf]');
  if (f) { select(f); e.preventDefault(); return; }
  // 드릴다운: 바깥 개체 → 안쪽 개체 (장 → 절 → 항목)
  const chain = [];
  for (let n = e.target; n && n !== document.body; n = n.parentElement) {
    if (entInfo(n)) chain.unshift(n);
  }
  if (!chain.length) { select(null); return; }
  const i = state.sel ? chain.indexOf(state.sel) : -1;
  select(i >= 0 && i < chain.length - 1 ? chain[i + 1] : chain[0]);
  e.preventDefault();
}, true);

// ── 직접 수정(blur + 바깥 클릭 이중 경로 — 임베디드 브라우저 대비) ──
function unhunt(el) { el.querySelectorAll('span.jachigan-run').forEach(s => s.replaceWith(...s.childNodes)); el.normalize(); }
function finishEdit() {
  const ed = state.editing; if (!ed) return;
  state.editing = null;
  ed.el.removeAttribute('contenteditable');
  if (ed.after) ed.after();
  repaginate();                       // 재조판은 편집이 끝난 뒤에만
}
function editText(el, after) {
  unhunt(el);
  el.contentEditable = 'true'; el.focus();
  state.editing = { el, after };
  el.addEventListener('blur', finishEdit, { once: true });
}

// ── 도식: 스펙 왕복 + 라벨 즉시 반영(어절 wrap 이식) ──
// 도식마다 항목을 담는 배열 이름이 다르다 — 그리는 쪽(svgfig.js)이 읽는 이름과
// **같아야 한다**. 여기 손으로 적었다가 '전략'(전략체계도)을 빠뜨려, 그 도식에서는
// 단계 추가·삭제가 아무 일도 안 했다(2026-08-06 B-1 시험에서 걸림).
const 도식배열이름 = ['단계', '요건', '노드', '전략', '항목', '계열'];
function 도식배열(sp) {
  for (const k of 도식배열이름) if (Array.isArray(sp[k])) return sp[k];
  return null;
}
function figSpec(el) { try { return JSON.parse(el.dataset.fig || '{}'); } catch (e) { return {}; } }
function setFigSpec(el, sp) { el.dataset.fig = JSON.stringify(sp); }
function wrapKo(text, maxEm) {
  const w = s => [...s].reduce((a, c) => a + (c.codePointAt(0) > 0x2000 ? 1 : 0.55), 0);
  const out = []; let cur = '';
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const t = cur ? cur + ' ' + word : word;
    if (cur && w(t) > maxEm) { out.push(cur); cur = word; } else cur = t;
  }
  if (cur) out.push(cur);
  return out.length ? out : [''];
}
function figLabels(el) {
  return [...el.querySelectorAll('svg text')].filter(t => t.querySelector('tspan'));
}

// ── 액션 ──
function addNote(el, info) { state.noteFor = { el, info }; renderPanel(); }
function commitNote(v) {
  const nf = state.noteFor;
  if (nf && v && v.trim()) { state.notes[nf.info.label] = v.trim(); nf.el.classList.add('has-note'); }
  state.noteFor = null; save(); renderPanel();
}
function setBox(el, kind) {
  el.dataset.box = kind;
  state.ops.push({ action: '박스 종류', to: kind }); repaginate(); renderPanel();
  save();   // **저장까지 해야 정본에 닿는다**
}
function delEl(el, info) {
  const host = el.closest('.blk') || el.closest('p') || el;
  host.remove(); state.ops.push({ action: '삭제', target: info.label });
  select(null); repaginate(); save();   // **저장까지 해야 정본에 닿는다**
}
function parentArrayOf(el, kind) {
  // 형제 중 경로가 있는 노드에서 소속 배열 경로를 유도한다
  for (let n = el; n; n = n.previousElementSibling) {
    const p = n.dataset && n.dataset.path;
    if (!p) continue;
    const m = p.match(/^(장\.\d+\.절\.\d+)\./);
    if (m) return m[1] + '.' + kind;
    const c = p.match(/^(장\.\d+)\./);
    if (c) return c[1] + '.' + kind;
  }
  return null;
}
function addItemBelow(el, 처음단계) {
  const p = document.createElement('p');
  p.className = 'blk ' + (처음단계 ? LVORDER[0]
                          : (LVORDER.find(c => el.classList.contains(c)) || 'i-l2'));
  // **개체 이름을 반드시 붙인다** — 없으면 만들어 놓고 고를 수가 없다(박스에서 그랬다)
  p.dataset.ent = '항목';
  p.dataset.new = '1';
  p.dataset.parent = parentArrayOf(el, '항목') || '';
  if (el.dataset.group) p.dataset.group = el.dataset.group;
  p.textContent = '새 항목 — 클릭해 내용을 쓰세요';
  el.after(p); state.ops.push({ action: '항목 추가' });
  select(p); editText(p);            // 재조판은 편집이 끝난 뒤(finishEdit)에만 — 포커스 파괴 방지
  save();   // **저장까지 해야 정본에 닿는다**
}
function changeLevel(el, d) {
  const cur = LVORDER.findIndex(c => el.classList.contains(c));
  const next = Math.min(LVORDER.length - 1, Math.max(0, cur + d));
  if (next === cur) return;
  el.classList.remove(LVORDER[cur]); el.classList.add(LVORDER[next]);
  state.ops.push({ action: '레벨', to: LV[LVORDER[next]] });
  repaginate(); renderPanel();
  save();   // **저장까지 해야 정본에 닿는다**
}
function moveSeq(el, d) {
  const sib = d < 0 ? el.previousElementSibling : el.nextElementSibling;
  if (!sib || sib.dataset.ent !== el.dataset.ent) return;
  if (d < 0) sib.before(el); else sib.after(el);
  renumberSeq((el.dataset.path || sib.dataset.path || '').replace(/\.\d+$/, ''));
  state.ops.push({ action: '순서 이동' }); save(); select(el);
}
function renumberSeq(base) {
  if (!base) return;
  const els = [...document.querySelectorAll('[data-arr]')].filter(x =>
    (x.dataset.path || '').replace(/\.\d+$/, '') === base || x.dataset.parent === base);
  els.forEach((x, i) => {
    const no = x.querySelector('.no'); if (no) no.textContent = (i + 1) + '.';
  });
}
function addBox(host, kind) {
  const d = document.createElement('div');
  d.className = 'blk fr-box'; d.dataset.box = kind;
  // **개체 이름을 반드시 붙인다.** 조립기는 `data-ent="박스"` 를 심는데 여기서만
  // 빠뜨려서, 새로 만든 박스는 고를 수도 없고 액션도 안 떴다 — 만들자마자
  // 손댈 수 없는 박스가 됐다(2026-08-06 B-1 시험에서 걸림).
  d.dataset.ent = '박스';
  d.dataset.new = '1'; d.dataset.parent = parentArrayOf(host, '박스') || '';
  if (host.dataset.group) d.dataset.group = host.dataset.group;
  d.innerHTML = '<p>새 박스 — 클릭해 내용을 쓰세요</p>';
  host.after(d); state.ops.push({ action: '박스 추가', to: kind });
  repaginate(); select(d);
  save();   // **저장까지 해야 정본에 닿는다**
}
function addFig(host) {
  // 도식을 새로 넣는다. 도식은 자기완결이다 — 스펙(data-fig)만 있으면 svgfig.js 가 그린다.
  // 박스와 똑같이 **개체 이름·소속 배열**을 붙여야 저장(serialize ③)이 절.도식 배열로 받는다.
  const d = document.createElement('div');
  d.className = 'blk fr-fig'; d.dataset.ent = '도식';
  d.dataset.new = '1'; d.dataset.parent = parentArrayOf(host, '도식') || '';
  if (host.dataset.group) d.dataset.group = host.dataset.group;
  // 기본은 절차(process) 2단계 — 유형·라벨·캡션은 패널에서 바로 고친다
  setFigSpec(d, { type: 'process', '캡션': '새 도식 — 유형과 라벨을 고치세요',
    '단계': [{ '라벨': '단계 1', '주체': '', '전이': '다음' }, { '라벨': '단계 2', '주체': '' }] });
  host.after(d);
  if (window.SVGFIG) window.SVGFIG.mount(d);   // data-fig 를 읽어 캡션·SVG·함의를 그린다
  state.ops.push({ action: '도식 추가' });
  repaginate(); select(d);
  save();   // **저장까지 해야 정본에 닿는다**
}

// ── 패널 ──
const panel = document.createElement('div'); panel.className = 'panel'; document.body.appendChild(panel);
function btn(t, f, c) { const b = document.createElement('button'); b.textContent = t; b.onclick = f;
  if (c) b.className = c; return b; }
function renderPanel() {
  panel.innerHTML = '<h3>선택한 부분</h3>';
  const A = (t, f, c) => panel.appendChild(btn(t, f, c));
  if (state.noteFor) {
    panel.insertAdjacentHTML('beforeend',
      `<div class="ent">✍ AI에게 고쳐달라 하기</div><div class="hint">${esc(state.noteFor.info.label)}</div>` +
      `<textarea id="notein" placeholder="예: 이 부분을 표로 바꿔줘 / 근거 수치 추가 / 두 개로 나눠줘"></textarea>`);
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('저장', () => commitNote(document.getElementById('notein').value)));
    r.appendChild(btn('취소', () => { state.noteFor = null; renderPanel(); }));
    panel.appendChild(r);
    setTimeout(() => document.getElementById('notein').focus(), 40);
    return appendPending();
  }
  const el = state.sel, info = el && entInfo(el);
  if (!info) {
    panel.insertAdjacentHTML('beforeend',
      '<div class="ent">없음</div><div class="hint">고칠 곳을 클릭하세요.<br>' +
      '같은 자리를 다시 누르면 더 안쪽(큰 제목 → 작은 제목 → 항목)이 잡힙니다.<br>' +
      '목차와 쪽번호는 자동으로 만들어집니다.<br>' +
      '고칠 때마다 줄과 쪽을 다시 맞춥니다 — 한 덩어리 글이 쪽을 넘어 쪼개지지 않게 합니다.</div>');
    return appendPending();
  }
  // info.label 은 절 제목 등 **문서 글자**를 이어 붙여 만든다(entInfo 참고)
  panel.insertAdjacentHTML('beforeend', `<div class="ent">${esc(info.label)}</div>`);
  if (info.spec['힌트']) panel.insertAdjacentHTML('beforeend', `<div class="hint">${info.spec['힌트']}</div>`);
  // 슬라이드 자유배치 — 헤드·본문이 있는 슬라이드면 흐름⇄자유 토글과, 고른 개체의 좌표를 보인다.
  const 슬sec = el.closest && el.closest('.sl-page[data-slide-idx]');
  if (슬sec && (슬sec.querySelector('.sl-head') || 슬sec.querySelector('.sl-body'))) {
    const 자유 = 슬sec.classList.contains('sl-free');
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">${자유 ? '자유배치 — 그립(✥)으로 옮기고 모서리 점으로 크기 조절' : '흐름 배치 — 정해진 자리'}</div>`);
    A(자유 ? '흐름 배치로 되돌리기' : '＋ 자유배치로 전환', () => 자유배치토글(슬sec), 자유 ? '' : 'good');
    if (자유 && el.classList.contains('sl-placed')) {
      const st = el.style, vv = k => Math.round(parseFloat(st[k]) || 0);
      panel.insertAdjacentHTML('beforeend',
        `<div class="hint">이 개체 위치 — x ${vv('left')} · y ${vv('top')} · 너비 ${vv('width')} · 높이 ${vv('height')} (지면 %)</div>`);
    }
  }
  const acts = info.spec['액션'] || [];
  if (!acts.length && !el.dataset.explain)
    panel.insertAdjacentHTML('beforeend',
      '<div class="explain">이 항목은 이 화면에서 고치지 않습니다.</div>');
  const has = a => acts.includes(a);

  if (has('boxkind')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">종류 — 누르면 바로 바뀝니다</div>');
    (info.spec['종류'] || []).forEach(k => A(k, () => setBox(el, k), el.dataset.box === k ? 'sel' : ''));
  }
  if (has('figtype')) {
    const sp = figSpec(el);
    panel.insertAdjacentHTML('beforeend', '<div class="hint">모양 — 누르면 바로 다시 그립니다</div>');
    Object.entries(info.spec['유형'] || {}).forEach(([k, v]) => A(v, () => {
      const s2 = figSpec(el); s2.type = k; setFigSpec(el, s2);
      window.SVGFIG.mount(el); state.ops.push({ action: '도식 유형', to: v });
      repaginate(); select(el);
    }, sp.type === k ? 'sel' : ''));
  }
  if (has('edit')) {
    if (info.type === '도식') {
      A('✏ 캡션 수정', () => { const c = el.querySelector('.cap');
        if (c) editText(c, () => { syncFigSpec(el); window.SVGFIG.mount(el); }); });
      A('✏ 그림 밑 설명(※) 수정', () => { const n = el.querySelector('.note');
        if (n) editText(n, () => { syncFigSpec(el); window.SVGFIG.mount(el); }); });
    } else if (info.type === '표') {
      A('✏ 셀 직접 수정', () => editText(el.querySelector('table')));
    } else if (info.type === '장' || info.type === '절') {
      A(`✏ ${info.spec['라벨']} 제목 수정`, () => { const tx = el.querySelector('.tx') || el;
        editText(tx, () => { el.dataset.title = tx.textContent.trim(); }); });
    } else {
      A('✏ 직접 수정', () => editText(el));
    }
  }
  if (has('figlabel')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">글자 — 고치면 바로 다시 그립니다</div>');
    const setters = figSetters(figSpec(el));
    figLabels(el).forEach((t, i) => {
      if (!setters[i]) return;
      A('✏ ' + (svgLabelText(t).slice(0, 14) || '(빈 라벨)'), () => {
        // 예전엔 따옴표 하나만 바꿔 속성 안에 밀어 넣었다 — 잠금은 전부 건다
        panel.innerHTML = `<h3>라벨 수정</h3><input type="text" id="labin" value="${esc(svgLabelText(t))}">`;
        const r = document.createElement('div'); r.className = 'row';
        r.appendChild(btn('적용', () => {
          const s2 = figSpec(el); figSetters(s2)[i](document.getElementById('labin').value);
          setFigSpec(el, s2); window.SVGFIG.mount(el);
          state.ops.push({ action: '도식 라벨' }); repaginate(); select(el);
        }));
        r.appendChild(btn('취소', () => renderPanel()));
        panel.appendChild(r);
        setTimeout(() => document.getElementById('labin').select(), 40);
      });
    });
  }
  if (has('figstep')) {
    A('＋ 단계·항목 추가', () => {
      const s2 = figSpec(el);
      const arr = 도식배열(s2);
      if (!Array.isArray(arr)) return;
      arr.push('새 항목'); setFigSpec(el, s2); window.SVGFIG.mount(el);
      state.ops.push({ action: '도식 항목 추가' }); repaginate(); select(el);
    });
    A('－ 마지막 단계 삭제', () => {
      const s2 = figSpec(el);
      const arr = 도식배열(s2);
      if (!Array.isArray(arr) || arr.length <= 2) return;
      arr.pop(); setFigSpec(el, s2); window.SVGFIG.mount(el);
      state.ops.push({ action: '도식 항목 삭제' }); repaginate(); select(el);
    }, 'danger');
  }
  if (has('level') && info.spec['레벨']) {
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('＋ 상위 단계로', () => changeLevel(el, -1)));
    r.appendChild(btn('－ 하위 단계로', () => changeLevel(el, 1)));
    panel.appendChild(r);
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">${info.spec['레벨'].map(x => x[1]).join(' → ')}</div>`);
  }
  if (has('mk2') && info.spec['2단마커']) {
    // 2단 마커는 문서 한 벌이 같아야 한다 — 항목 하나만 바꾸면 뒤죽박죽이 된다.
    // 그래서 문서 뿌리(html)에 걸고 CSS 변수로 전체에 미친다.
    const 목록 = info.spec['2단마커'], 기본 = 목록[0];
    const cur = document.documentElement.dataset.mk2 || 기본;
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">2단 마커 — 문서 전체에 적용됩니다 (지금 ${cur})</div>`);
    목록.forEach(m => A(`${m} 로 통일${m === cur ? '  ✓' : ''}`, () => {
      if (m === 기본) delete document.documentElement.dataset.mk2;
      else document.documentElement.dataset.mk2 = m;
      state.ops = state.ops.filter(o => o.action !== '2단 마커');
      if (m !== 기본) state.ops.push({ action: '2단 마커', to: m });
      save(); repaginate(); select(el);
    }));
  }
  if (has('addBelow')) A('＋ 아래에 항목 추가', () => {
    // 절·장 아래는 첫 단계(○)로, 항목 아래는 그 항목과 같은 단계로 —
    // **한 함수로 한다.** 두 곳에 같은 코드를 두었더니 한쪽만 data-ent 를 붙였다.
    addItemBelow(el, info.type === '절' || info.type === '장');
  });
  if (has('addBox')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">박스 추가</div>');
    ((ENTS['박스'] || {})['종류'] || ['통계근거']).slice(0, 3).forEach(k =>
      A('＋ ' + k + ' 박스', () => addBox(el, k)));
  }
  if (has('addFig')) A('＋ 도식 넣기', () => addFig(el));
  if (has('addItem')) A('＋ 항목 추가', () => { const p = document.createElement('p');
    p.textContent = '새 항목'; el.appendChild(p); editText(p); });
  if (has('addNote')) A('＋ 각주 추가', () => { const p = document.createElement('p');
    p.className = 'fn'; p.textContent = '근거·출처'; el.appendChild(p); editText(p); });
  if (has('tablerow')) {
    A('＋ 행 추가', () => { const tb = el.querySelector('table');
      const last = tb.rows[tb.rows.length - 1]; const tr = tb.insertRow(-1);
      for (let i = 0; i < last.cells.length; i++) tr.insertCell(-1).textContent = '—';
      repaginate(); });
    A('🗑 마지막 행 삭제', () => { const tb = el.querySelector('table');
      if (tb.rows.length > 2) { tb.deleteRow(-1); repaginate(); } }, 'danger');
  }
  if (has('endstyle')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">끝 표시 위치</div>');
    // **고른 값을 들고 있어야 한다.** 전에는 조작만 기록하고 값을 아무 데도 안 담아
    // 화면도 안 바뀌고 정본에도 안 닿았다 — 액션이 통째로 죽어 있었다
    // (2026-08-06 B-1 시험에서 걸림). 조립기는 `끝표시` 필드를 읽는다.
    const 지금 = state.끝표시 !== undefined ? state.끝표시 : (getPath0('끝표시') || '같은줄');
    (info.spec['위치'] || []).forEach(v => A(v, () => {
      state.끝표시 = v;
      state.ops.push({ action: '끝 표시', to: v });
      save(); renderPanel();
    }, v === 지금 ? 'sel' : ''));
  }
  if (has('explain') && el.dataset.explain) {
    panel.insertAdjacentHTML('beforeend',
      `<div class="explain">${el.dataset.explain}</div>`);
  }
  if (has('emphasis')) {
    const spans = [...el.querySelectorAll('span.num, span.accent, span.delta')];
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">강조 — 숫자(검정 굵게) · 핵심(남색, 문서 2회까지) · 증감(빨강, △ 필요)</div>`);
    spans.forEach((sp, i) => {
      const kind = sp.classList.contains('accent') ? '핵심'
                 : sp.classList.contains('delta') ? '증감' : '숫자';
      A(`${kind} — ${sp.textContent.slice(0, 12)}`, () => {
        const order = ['num', 'accent', 'delta'];
        const cur = order.findIndex(c => sp.classList.contains(c));
        const next = order[(cur + 1) % order.length];
        if (next === 'delta' && !sp.textContent.includes('△')) {
          toast('증감 강조는 △가 있는 수치에만 씁니다'); return;
        }
        if (next === 'accent' &&
            document.querySelectorAll('span.accent').length >= 2 && cur !== 1) {
          toast('핵심 강조는 문서에 2회까지입니다'); return;
        }
        sp.className = next;
        state.ops.push({ action: '강조', to: next }); save(); renderPanel();
      });
    });
    if (spans.length) A('강조 모두 해제', () => {
      spans.forEach(sp => sp.replaceWith(...sp.childNodes));
      el.normalize(); state.ops.push({ action: '강조 해제' }); save(); renderPanel();
    }, 'danger');
  }
  if (has('endmark')) {
    // **이번 판에서 바꾼 값이 먼저다.** 정본 값만 보면, 눌러서 끝 표시를 켜 놓고도
    // 단추 이름이 "넣기" 로 남아 두 번 눌러도 안 꺼진다(2026-08-06 B-1 시험에서 걸림).
    // 저장하기 전까지 화면과 단추가 어긋나 있었다.
    const on = state.endmark !== undefined
      ? state.endmark : (getPath0('show_end_mark') === true);  // 정본 기본값 False(종결표기_옵션): 1p 표준=표기 없음
    A(on ? '⊘ 끝 표시 숨기기' : '✓ 끝 표시 넣기', () => {
      state.endmark = !on;
      const lbl = el.querySelector('.label');
      const body = el.textContent.replace(/\s*끝\s*\.?\s*$/, '').replace(/^붙임\s*/, '').trim();
      // **textContent 를 innerHTML 로 되돌리면 글자가 태그로 승격한다.** 붙임에
      // `<img src=x onerror=…>` 라고 적혀 있으면 화면에서는 글자였다가 이 한 줄에서
      // 진짜 태그가 된다 — 잠그고 넣는다(WP-S2 ③).
      el.innerHTML = (lbl ? '<span class="label">붙임</span>&nbsp;&nbsp;' : '') + esc(body) +
        (state.endmark ? '&nbsp;&nbsp;끝.' : '');
      state.ops.push({ action: '끝 표시', to: state.endmark ? '표시' : '숨김' });
      save(); renderPanel();
    });
  }
  if (has('toggle')) {
    const on = el.dataset.on !== 'false';
    A(on ? '⊘ 이 요소 빼기' : '✓ 이 요소 넣기', () => {
      applyToggle(el, !on);
      state.ops.push({ action: '구성 요소', to: !on ? '넣음' : '뺌' }); save(); renderPanel();
    }, on ? 'danger' : '');
  }
  if (has('reorder')) {
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('▲ 위로', () => moveSeq(el, -1)));
    r.appendChild(btn('▼ 아래로', () => moveSeq(el, 1)));
    panel.appendChild(r);
  }
  if (has('addSeq')) A('＋ 아래에 항목 추가', () => {
    const c = el.cloneNode(true);
    c.removeAttribute('data-path'); c.dataset.new = '1';
    c.dataset.parent = el.dataset.path.replace(/\.\d+$/, '');
    const tx = c.querySelector('.tx'); if (tx) tx.textContent = '새 항목';
    const why = c.querySelector('.why'); if (why) why.remove();
    el.after(c); renumberSeq(el.dataset.path.replace(/\.\d+$/, ''));
    state.ops.push({ action: '본문 항목 추가' }); save(); select(c);
    if (tx) editText(tx);
  });
  if (has('pagehide')) {
    const idx = el.dataset.pageIdx || '?';
    const hidden = el.hasAttribute('data-no-pageno');
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">${idx}번째 쪽입니다. 번호는 표지부터 통산합니다.</div>`);
    A(hidden ? '① 이 쪽에 쪽번호 보이기' : '⊘ 이 쪽의 쪽번호 감추기', () => {
      const next = hidden;                       // 감춰져 있었으면 보이게
      el.dataset.flag = '쪽번호.표시.' + idx;    // 손댄 쪽에만 훅을 단다
      el.dataset.on = String(next);
      if (next) el.removeAttribute('data-no-pageno'); else el.setAttribute('data-no-pageno', '1');
      state.ops.push({ action: '쪽번호', to: idx + '쪽 ' + (next ? '보임' : '감춤') });
      save(); renderPanel();
    });
  }
  if (has('pagestart')) {
    const idx = el.dataset.pageIdx || '?';
    A('①→ 이 쪽부터 번호 새로 시작', () => {
      const box = document.createElement('div'); box.className = 'row';
      const inp = document.createElement('input');
      inp.type = 'number'; inp.min = '1'; inp.value = el.dataset.restart || '1';
      inp.style.cssText = 'width:70px;padding:4px;border:1px solid var(--ai-color-line-strong);border-radius:4px';
      box.appendChild(inp);
      box.appendChild(btn('적용', () => {
        const v = String(Math.max(1, parseInt(inp.value, 10) || 1));
        el.dataset.restart = v;
        // 값을 DOM에 남겨야 저장기가 집어간다 — 모델에 직접 쓰면 다시 그릴 때 지워진다
        el.dataset.cycle = '쪽번호.새번호시작.' + idx;
        el.dataset.lv = v;
        state.ops.push({ action: '쪽번호 시작', to: idx + '쪽부터 ' + v });
        save();
        if (typeof repaginate === 'function') repaginate();
        renderPanel();
      }));
      panel.appendChild(box);
    });
  }
  if (has('imgsize')) {
    const spec = imgSpec(el), img = el.querySelector('img');
    panel.insertAdjacentHTML('beforeend', '<div class="hint">지면 폭에 대한 비율입니다.</div>');
    (info.spec['크기'] || ['40%', '60%', '80%', '100%']).forEach(w => A(w, () => {
      spec['폭'] = w; imgSave(el, spec);
      if (img) img.style.width = w;
      state.ops.push({ action: '그림 크기', to: w }); save(); renderPanel();
    }, (spec['폭'] || '80%') === w ? 'sel' : ''));
  }
  if (has('imgcap')) {
    A('✏ 그림 제목 고치기', () => {
      const spec = imgSpec(el);
      줄고치기('그림 제목 (표 제목처럼 < > 안에 들어갑니다)', spec['캡션'] || '', v => {
        spec['캡션'] = v; imgSave(el, spec);
        let cap = el.querySelector('.cap');
        if (!cap && v) { cap = document.createElement('div'); cap.className = 'cap';
                         el.insertBefore(cap, el.firstChild); }
        if (cap) cap.textContent = v ? '< ' + v + ' >' : '';
        state.ops.push({ action: '그림 제목' }); save(); renderPanel();
      });
    });
    A('✏ 이 그림이 말하는 것 고치기', () => {
      const spec = imgSpec(el);
      줄고치기('이 그림에서 읽어야 할 것 (※ 로 붙습니다)', spec['함의'] || '', v => {
        spec['함의'] = v; imgSave(el, spec);
        let n = el.querySelector('.note');
        if (!n && v) { n = document.createElement('div'); n.className = 'note'; el.appendChild(n); }
        if (n) n.textContent = v;
        state.ops.push({ action: '그림 설명' }); save(); renderPanel();
      });
    });
  }
  if (has('imgcrop')) {
    A('⛶ 쓸 부분 고르기', () => 자르기시작(el));
  }
  if (has('planfix')) {
    const P = el.dataset.planPath;
    const tgt = P ? planTarget(P) : null;
    if (!tgt) {
      panel.insertAdjacentHTML('beforeend',
        '<div class="hint">이 항목은 이 화면에서 바로 고칠 자리가 없습니다 — '
        + '위에서 해당하는 곳을 직접 손봐 주세요.</div>');
    } else {
      A('↗ 바꿀 곳으로 가기', () => {
        tgt.scrollIntoView({ block: 'center', behavior: 'smooth' });
        select(tgt); renderPanel();
      });
      const sug = el.dataset.suggest;
      if (sug !== undefined) A(`이대로 바꾸기 → ${sug}`, () => {
        // 카드가 만들어진 뒤에 그 자리가 이미 바뀌었을 수 있다 — 덮어쓰지 않고 알린다
        const was = el.dataset.planWas;
        if (was !== undefined && planCur(tgt) !== was) {
          toast('이 요청이 가리키던 곳이 그새 바뀌었습니다 — 직접 확인해 주세요');
          tgt.scrollIntoView({ block: 'center' }); select(tgt); renderPanel(); return;
        }
        const tspec = (entInfo(tgt) || {}).spec || {};
        if (tgt.dataset.flag) applyToggle(tgt, sug === 'true' || sug === '넣음');
        else if (tgt.dataset.cycle) applyCycle(tgt, tspec, sug);
        else {
          const leaf = planLeaf(tgt);
          setText(leaf, sug);          // data-shown 은 건드리지 않는다(고친 걸로 인식돼야 저장된다)
          if (tgt.dataset.title !== undefined) tgt.dataset.title = sug;
        }
        applyCycle(el, info.spec, '반영');
        state.ops.push({ action: '확인할 것 반영', to: sug });
        save(); renderPanel();
        toast('구성 설계를 고쳤습니다 — 문서를 다시 만들어야 반영됩니다');
      }, 'good');
    }
  }
  if (has('cycle') && info.spec['값']) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">'
      + (info.spec['값힌트'] || '가능성 — 실제로 넣을지는 다음 단계에서 정합니다') + '</div>');
    info.spec['값'].forEach(v => A(cycShow(info.spec, v), () => {
      applyCycle(el, info.spec, v);
      state.ops.push({ action: info.spec['라벨'], to: (cycPre(info.spec) + ' ' + v).trim() });
      save(); renderPanel();
    }, el.dataset.lv === v ? 'sel' : ''));
  }
  // 남긴 지시는 apply_edit_any 가 '대기'로 기록만 하고 채팅의 Claude 가 읽어 반영한다.
  // 웹앱엔 그 Claude 가 없어 눌러도 아무 일도 안 일어나므로(죽은 기능) 감춘다.
  if (채팅표면 && has('ai')) A('✍ AI에게 고쳐달라 하기 — ' + info.spec['라벨'], () => addNote(el, info));
  if (has('delSection')) A('🗑 절 전체 삭제', () => {
    const gid = el.dataset.group; const kill = [el];
    document.querySelectorAll(`.blk[data-group="${gid}"]`).forEach(n => { if (n !== el) kill.push(n); });
    kill.forEach(n => n.remove());
    state.ops.push({ action: '삭제', target: '절 ' + (el.dataset.title || '') });
    select(null); repaginate();
  }, 'danger');
  if (has('del')) A('🗑 ' + info.spec['라벨'] + ' 삭제', () => delEl(el, info), 'danger');
  appendPending();
}
function appendPending() {
  const keys = Object.keys(state.notes);
  if (!keys.length && !state.ops.length) return;
  // 열쇠는 개체 라벨(문서 글자), 값은 **사람이 적어 넣은 요청**이다 — 둘 다 잠근다
  panel.insertAdjacentHTML('beforeend', '<div class="notes"><b>대기 중 작업</b><ul>' +
    keys.map(k => `<li>📌 ${esc(k)}: ${esc(state.notes[k])}</li>`).join('') +
    state.ops.slice(-6).map(o => `<li>· ${esc(o.action)}${o.to ? ' → ' + esc(o.to) : ''} ${esc(o.target || '')}</li>`).join('') +
    '</ul><div class="hint">' + (채팅표면
      ? '채팅에 "고쳐놨어"라고 하시면 반영해 다시 만듭니다'
      : '고친 내용은 저장하는 즉시 문서에 반영됩니다') + '</div></div>');
}

// ── 직렬화: 원본 모델을 복제해 '경로(data-path)'로 패치 ──
// DOM 순서 워크 + 커서 방식은 절 제목을 지우면 항목이 유실되고, jachigan 잔해까지
// 되살리는 구조적 결함이 있었다(적대 검증 확정). 원본을 신뢰하고 델타만 얹는다.
const SRCDOC = JSON.parse(document.getElementById('fr-doc').textContent);

// ── WP-S10 2차-B: 문체 동의 카드 — "리터칭"(사람이 직접 다듬는 것) 흐름의 훅 ──────
// 저장마다(아래 보내기()) 마지막 진단 기준(문체기준)과 지금 막 고친 내용을 backtrace
// 세그먼트 diff 로 견주어(서버 `문체후보` → feedback/backtrace.py 의 extract·diff_docs
// 그대로, 1차·2차-A 가 실측한 그 함수) 조를 만한 낱말 치환을 찾으면 F1 동의 카드를
// 띄운다. 기본은 안 묻는 상태다 — 서버가 후보를 null 로 돌려주면(변경이 없거나 이
// 문서가 backtrace 대상(1p) 이 아니면) 카드는 아예 안 뜬다.
let 문체기준 = SRCDOC;                  // 마지막으로 진단한 기준 — 첫 저장 전엔 원본 그대로
const 물어본문체델타 = new Set();
// 한글 받침 유무로 조사를 고른다(을/를·으로/로) — 낱말이 사용자가 쓴 임의 값이라
// 고정 조사를 박으면 절반은 어색해진다("설치"를 "구축"**로** 는 맞지만 "이전"을
// "이후"**으로** 처럼 받침이 있으면 "로"가 틀린다).
function 받침있나(s) {
  const c = String(s || '').trim().slice(-1).codePointAt(0);
  if (c === undefined || c < 0xAC00 || c > 0xD7A3) return false;   // 한글 완성형이 아니면 판단 보류
  return (c - 0xAC00) % 28 !== 0;
}
function 동의카드보이기(항목, 설명) {
  if (document.querySelector('.consent-card')) return;   // 이미 하나 떠 있으면 겹치지 않는다
  const el = document.createElement('div');
  el.className = 'consent-card';
  el.innerHTML = `<div class="cc-head">
      <svg class="cc-logo" viewBox="0 0 100 100" aria-hidden="true">
        <path d="M17 9h45l21 21v61H17z"/><path d="M62 9v24h21"/><path d="M31 47h37M31 60h37M31 73h25"/>
      </svg>
      <div class="cc-word"><b>문서지능</b><span>피드백으로 문서 품질을 함께 높입니다</span></div>
    </div><div class="cc-body">
    <p>${esc(설명)}</p>
    <div class="cc-why">
      <label for="cc-why-input">왜 바꾸셨는지 한 줄 남겨 주시면 더 정확히 반영됩니다 (선택)</label>
      <input type="text" id="cc-why-input" placeholder="분량이 많아 풀버전이 맞다고 봤습니다">
      <p class="cc-hint">이름·연락처 등 개인정보는 빼고 적어 주세요.</p>
    </div>
    <div class="cc-row">
      <button data-d="이번만 아니오">이번만 아니오</button>
      <button data-d="앞으로 묻지 않기">다시 묻지 않기</button>
      <button data-d="남깁니다" class="good">남기기</button>
    </div></div>`;
  document.body.appendChild(el);
  el.querySelector('.cc-row').onclick = async e => {
    const b = e.target.closest('button[data-d]'); if (!b) return;
    const 결정 = b.dataset.d;
    // "왜" 칸은 선택 — el.remove() 전에 값을 챙긴다.
    const 왜 = ((el.querySelector('#cc-why-input') || {}).value || '').trim();
    el.remove();
    if (결정 === '앞으로 묻지 않기') sessionStorage.setItem('ai-consent-skip-style', '1');
    if (결정 !== '남깁니다') return;    // **동의 없이는 저장 API 를 아예 안 부른다**(왜칸 값이 있어도 마찬가지)
    try {
      // 왜칸 값을 `지시`(이유)로 실어 보낸다 — 엔진(`_항목빚기`, feedback/corpus.py 손 안 댐)이
      // 동의 뒤 한 번에 비식별한다. 안 쓰면 항목이 이미 들고 있던 지시(문체는 늘 없음)를 그대로 둔다.
      await fetch('/api/동의코퍼스', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 결정, 항목: { ...항목, 지시: 왜 || 항목.지시 || null } }) });
    } catch (e) { /* 반영(/save) 은 이미 끝났다 — 코퍼스 기록만 못 갔을 뿐, 조용히 넘어간다 */ }
  };
}
async function 문체동의진단(이후) {
  const 이전 = 문체기준;
  문체기준 = 이후;                       // 이 진단 이후로는 "지금"이 새 기준이다(중복 질문 방지)
  if (sessionStorage.getItem('ai-consent-skip-style')) return;
  try {
    const r = await fetch('/api/문체후보', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: FN, 이전, 이후 }) });
    const j = await r.json();
    const 항목 = j.ok ? j['값'] : null;
    if (!항목) return;                   // 변경 없음·1p 아님·주목할 변경 아님 — 조용히 넘어간다
    const d = 항목['델타'] || {};
    const 델타키 = String(d['전']) + '→' + String(d['후']);
    if (물어본문체델타.has(델타키)) return;    // 같은 치환은 이 화면에서 한 번만 묻는다
    물어본문체델타.add(델타키);
    동의카드보이기(항목,
      `방금 「${d['전']}」${받침있나(d['전']) ? '을' : '를'} 「${d['후']}」${받침있나(d['후']) ? '으로' : '로'} 다듬으셨습니다.\n\n` +
      `이런 손질이 규칙을 다듬는 데 큰 도움이 됩니다.\n피드백으로 남겨도 될까요?\n\n` +
      `원문도 개인정보도 저장하지 않습니다.\n무엇을 어떻게 바꾸셨는지만 익명으로 남습니다.`);
  } catch (e) { /* 서버가 없거나 file:// 로 열렸을 때(자가검사)는 조용히 건너뛴다 */ }
}

function stripAngle(t) {   // '< 제목 >' → '제목'
  return String(t).replace(/^\s*[<＜]\s*/, '').replace(/\s*[>＞]\s*$/, '').trim();
}
function getPath0(p) { try { return getPath(SRCDOC, p); } catch (e) { return undefined; } }
function getPath(o, path) {
  const ks = path.split('.');
  for (const k of ks) { if (o == null) return undefined; o = o[/^\d+$/.test(k) ? +k : k]; }
  return o;
}
function setPath(o, path, v) {
  const ks = path.split('.');
  for (let i = 0; i < ks.length - 1; i++) {
    const k = /^\d+$/.test(ks[i]) ? +ks[i] : ks[i];
    if (o[k] == null) o[k] = /^\d+$/.test(ks[i + 1]) ? [] : {};
    o = o[k];
  }
  const last = ks[ks.length - 1];
  o[/^\d+$/.test(last) ? +last : last] = v;
}
// ── 경로 조각 모으기 ────────────────────────────────────────────────────
// 자간 조정(jachigan)은 줄에 걸친 범위를 span 으로 감싼다. 그런데
// Range.extractContents() 는 **걸친 요소를 속성까지 복제**하므로, data-path 를 단
// span 하나가 조각 수십 개로 흩어진다. 조각 하나만 읽으면 글이 잘린 채 저장된다
// — 2026-08-04 규정·보도자료 왕복 실패의 원인이었다(규정 본문 1문단이 64조각).
// 1p·풀버전이 멀쩡했던 것은 경로를 블록(<p>)에 걸어 블록 자체는 안 쪼개졌기 때문이다.
// 경로를 잎(span)에 거는 장르가 늘면 또 샌다. 그래서 클래스가 아니라 **경로로 모은다.**
function 경로조각() {
  const m = new Map();
  document.querySelectorAll('[data-path]').forEach(el => {
    const p = el.dataset.path;
    if (!m.has(p)) m.set(p, []);
    m.get(p).push(el);
  });
  return [...m.entries()];
}
function 이어붙임(els) {
  if (els.length === 1) return els[0];
  // 조각은 문서 순서대로 온다. innerHTML 을 이어 붙이면 조각 사이 공백과
  // 강조 태그가 그대로 살아난다(조각마다 trim 하면 어절이 붙어버린다).
  const box = document.createElement('span');
  box.className = els[0].className;
  box.innerHTML = els.map(x => x.innerHTML).join('');
  return box;
}
function textOf(el) {                    // jachigan 잔해·빈 강조 껍데기를 걷어낸 3층 표기
  const c = el.cloneNode(true);
  c.querySelectorAll('span.jachigan-run').forEach(s => s.replaceWith(...s.childNodes));
  c.querySelectorAll('.no,.cap,.fn').forEach(x => { if (x !== c) x.remove(); });
  c.querySelectorAll('b,u,span.lb').forEach(x => { if (!x.textContent.trim()) x.remove(); });
  c.normalize();
  c.querySelectorAll('span.lb').forEach(x => x.replaceWith(document.createTextNode('<lb>' + x.textContent + '</lb>')));
  c.querySelectorAll('b').forEach(x => x.replaceWith(document.createTextNode('<b>' + x.textContent + '</b>')));
  c.querySelectorAll('u').forEach(x => x.replaceWith(document.createTextNode('<u>' + x.textContent + '</u>')));
  let t = c.innerHTML !== undefined ? c.innerHTML : c.textContent;
  t = t.replace(/<br\s*\/?>/gi, '\n');                 // 표지 제목 2줄 보존
  t = t.replace(/<[^>]+>/g, '');                        // 남은 태그 제거
  const d = document.createElement('textarea'); d.innerHTML = t; t = d.value;
  // 인접 중복 강조 병합(<b>a</b><b>b</b> → <b>ab</b>)
  t = t.replace(/<\/(b|u)><\1>/g, '').replace(/<\/lb><lb>/g, '');
  return t.replace(/ /g, ' ').replace(/[ \t]+/g, ' ').trim();
}
// 도식: 라벨 순서 → 유형별 필드 설정자(적대 검증 확정 결함 — _labels는 아무도 안 읽었다)
function figSetters(sp) {
  const S = [];
  const put = (fn) => S.push(fn);
  if (sp.type === 'process') (sp['단계'] || []).forEach((st, i) => put(v => {
    if (typeof sp['단계'][i] === 'object') sp['단계'][i]['라벨'] = v; else sp['단계'][i] = v; }));
  else if (sp.type === 'cycle') (sp['단계'] || []).forEach((st, i) => put(v => {
    if (typeof sp['단계'][i] === 'object') sp['단계'][i]['라벨'] = v; else sp['단계'][i] = v; }));
  else if (sp.type === 'converge') {
    (sp['요건'] || []).forEach((r, i) => put(v => sp['요건'][i] = v));
    put(v => sp['시행'] = v); put(v => sp['결과'] = v);
  } else if (sp.type === 'strategy') {
    put(v => sp['목표'] = v);
    (sp['전략'] || []).forEach((c, i) => {
      put(v => sp['전략'][i]['제목'] = v);
      (c['과제'] || []).forEach((t, j) => put(v => sp['전략'][i]['과제'][j] = v.replace(/^▪\s*/, '')));
    });
  } else if (sp.type === 'relation') (sp['노드'] || []).forEach((n, i) => put(v => {
    if (typeof sp['노드'][i] === 'object') sp['노드'][i]['라벨'] = v; else sp['노드'][i] = v; }));
  return S;
}
function svgLabelText(t) {   // tspan 사이에 공백을 넣어 어절 손실 방지
  return [...t.querySelectorAll('tspan')].map(x => x.textContent.trim()).join(' ').trim();
}
function syncFigSpec(el) {
  const sp = figSpec(el);
  const cap = el.querySelector('.cap'), nt = el.querySelector('.note');
  if (cap) sp['캡션'] = stripAngle(cap.textContent);
  if (nt) sp['함의'] = nt.textContent.replace(/^※\s*/, '').trim();
  const setters = figSetters(sp), labs = figLabels(el);
  labs.forEach((t, i) => { if (setters[i]) setters[i](svgLabelText(t)); });
  setFigSpec(el, sp);
  return sp;
}
function boxOf(el) {
  const items = [], fns = [];
  [...el.children].forEach(p => {
    if (p.classList.contains('cap')) return;
    if (p.classList.contains('fn')) fns.push(textOf(p)); else items.push(textOf(p));
  });
  const cap = el.querySelector('.cap');
  const o = { '종류': el.dataset.box, '항목': items };
  if (cap) o['캡션'] = stripAngle(cap.textContent);
  if (fns.length) o['각주'] = fns;
  return o;
}
// 그림 — 스펙을 통째로 실어 두고(data-img) 읽고 쓴다. 도식(syncFigSpec)과 같은 방식이다.
// 한 줄 고치기 — prompt() 를 못 쓰므로 패널 안에서 받는다
function 줄고치기(라벨, 지금값, 끝나면) {
  const bar = document.createElement('div');
  bar.className = 'resume-bar';
  bar.innerHTML = '<b>' + 라벨 + '</b>';
  const inp = document.createElement('input');
  inp.type = 'text'; inp.value = 지금값;
  inp.style.cssText = 'display:block;width:100%;margin-top:6px;padding:6px 8px;'
    + 'border:1px solid var(--ai-color-line-strong);border-radius:5px;font:inherit;box-sizing:border-box';
  bar.appendChild(inp);
  const row = document.createElement('div'); row.className = 'row';
  row.appendChild(btn('저장', () => { 끝나면(inp.value.trim()); bar.remove(); }, 'good'));
  row.appendChild(btn('취소', () => bar.remove()));
  bar.appendChild(row);
  document.body.insertBefore(bar, document.body.firstChild);
  inp.focus(); inp.select();
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { 끝나면(inp.value.trim()); bar.remove(); }
    if (e.key === 'Escape') bar.remove();
  });
}

// 쓸 부분 고르기 — 화면의 그림 위에 상자를 끌어 그린다.
// 여기서 정하는 것은 '어디를' 뿐이고, 실제로 자르는 것은 반영할 때 원본에서 한다.
function 자르기시작(el) {
  const img = el.querySelector('img');
  if (!img) { toast('아직 그림이 들어오지 않았습니다'); return; }
  document.querySelectorAll('.crop-wrap').forEach(x => x.replaceWith(...x.childNodes));
  const spec = imgSpec(el);
  const wrap = document.createElement('span');
  wrap.className = 'crop-wrap';
  wrap.style.cssText = 'position:relative;display:inline-block;line-height:0';
  img.replaceWith(wrap); wrap.appendChild(img);
  const sel = document.createElement('div');
  sel.className = 'crop-sel';
  wrap.appendChild(sel);

  const 이전 = spec['크롭'];
  let x0 = 0, y0 = 0, 끄는중 = false;
  const 놓기 = (l, t, w, h) => {
    sel.style.cssText = `position:absolute;left:${l * 100}%;top:${t * 100}%;`
      + `width:${w * 100}%;height:${h * 100}%;border:2px solid var(--ai-color-issue);`
      + 'background:color-mix(in srgb, var(--ai-color-issue) 10%, transparent);box-sizing:border-box';
  };
  if (이전 && 이전.length === 4 && Math.max(...이전) <= 1) 놓기(...이전);
  else 놓기(0, 0, 1, 1);

  const 비율 = e => {
    const r = img.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
            Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  wrap.onmousedown = e => { e.preventDefault(); [x0, y0] = 비율(e); 끄는중 = true; };
  wrap.onmousemove = e => {
    if (!끄는중) return;
    const [x, y] = 비율(e);
    놓기(Math.min(x0, x), Math.min(y0, y), Math.abs(x - x0), Math.abs(y - y0));
  };
  wrap.onmouseup = () => { 끄는중 = false; };

  const bar = document.createElement('div');
  bar.className = 'resume-bar';
  bar.innerHTML = '<b>그림 위에서 쓸 부분을 끌어 주세요.</b> '
    + '여기서는 자리만 정하고, 실제로 자르는 것은 문서에 반영할 때 원본에서 합니다.';
  const row = document.createElement('div'); row.className = 'row';
  row.appendChild(btn('이 부분으로', () => {
    const st = sel.style;
    const v = k => parseFloat(st[k]) / 100;
    const box = [v('left'), v('top'), v('width'), v('height')].map(n => +n.toFixed(4));
    if (box[2] < 0.02 || box[3] < 0.02) { toast('너무 좁습니다 — 다시 끌어 주세요'); return; }
    const sp = imgSpec(el); sp['크롭'] = box; imgSave(el, sp);
    state.ops.push({ action: '그림 자르기' });
    wrap.replaceWith(...[...wrap.childNodes].filter(n => n !== sel));
    bar.remove(); save(); renderPanel();
    toast('반영할 때 이 부분만 다시 잘라 넣습니다');
  }, 'good'));
  row.appendChild(btn('전체 쓰기', () => {
    const sp = imgSpec(el); delete sp['크롭']; imgSave(el, sp);
    wrap.replaceWith(...[...wrap.childNodes].filter(n => n !== sel));
    bar.remove(); save(); renderPanel();
  }));
  row.appendChild(btn('취소', () => {
    wrap.replaceWith(...[...wrap.childNodes].filter(n => n !== sel));
    bar.remove();
  }));
  bar.appendChild(row);
  document.body.insertBefore(bar, document.body.firstChild);
}

function imgSpec(el) {
  try { return JSON.parse(el.dataset.img || '{}'); } catch (e) { return {}; }
}
function imgSave(el, spec) {
  el.dataset.img = JSON.stringify(spec);
}

function tableOf(el) {
  const tb = el.querySelector('table'); if (!tb) return null;
  const cap = el.querySelector('[class*="cap"]');   // 장르마다 클래스명이 다르다
  const rows = [...tb.rows];
  return { '캡션': cap ? cap.textContent.trim() : '',
    header: [...rows[0].cells].map(c => c.textContent.trim()),
    rows: rows.slice(1).map(r => [...r.cells].map(c => c.textContent.trim())) };
}
function serialize() {
  const doc = JSON.parse(JSON.stringify(SRCDOC));      // 원본 신뢰 — 화면에 없는 것도 보존
  // ① 경로가 있는 노드의 현재 텍스트를 모델에 되쓴다
  //    같은 경로가 여러 조각으로 흩어져 있을 수 있다(자간 조정이 span 을 쪼갠다).
  경로조각().forEach(([path, els]) => {
    const el = els[0];
    if (el.classList.contains('fr-box')) {
      const b = boxOf(el);
      // 장 핵심박스는 문자열 배열(경로가 …핵심박스) — 항목만 넣는다
      setPath(doc, path, path.endsWith('핵심박스') ? b['항목'] : b);
      return;
    }
    // 그림이 먼저다 — .fr-img 도 .fr-fig 클래스를 함께 갖고 있어 순서가 뒤바뀌면
    // 도식 처리로 새어 스펙이 통째로 날아간다.
    if (el.classList.contains('fr-img')) { setPath(doc, path, imgSpec(el)); return; }
    if (el.classList.contains('fr-fig')) { setPath(doc, path, syncFigSpec(el)); return; }
    // 표를 감싼 컨테이너 — 장르마다 클래스명이 달라(fr-/doc-/gm-) 하나라도 빠지면
// 표 객체가 통째로 문자열로 덮어써진다. 클래스 대신 '표가 들어 있는가'로 판정한다.
    if (el.querySelector('table')) {
      const t = tableOf(el);
      if (t) {
        const prev = getPath(doc, path);
        // 원본의 스키마(1p는 after_heading·caption, 풀버전은 캡션)를 지키며 값만 갱신
        if (prev && typeof prev === 'object' && !Array.isArray(prev)) {
          const merged = Object.assign({}, prev);
          if ('캡션' in prev) merged['캡션'] = t['캡션']; else if ('caption' in prev) merged.caption = t['캡션'];
          merged.header = t.header; merged.rows = t.rows;
          setPath(doc, path, merged);
        } else setPath(doc, path, t);
      }
      return;
    }
    if (el.dataset.arr) return;                         // 시퀀스는 ①-b가 통째로 처리
    if (el.classList.contains('doc-attach')) {
      const c = 이어붙임(els).cloneNode(true);
      c.querySelectorAll('span.jachigan-run').forEach(x => x.replaceWith(...x.childNodes));
      c.querySelectorAll('.label').forEach(x => x.remove());     // '붙임' 라벨은 조립기가 붙인다
      let t = c.textContent.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
      t = t.replace(/\s*끝\s*\.?\s*$/, '').trim();             // 끝 표시도 조립기 몫
      t = t.replace(/\.$/, '').trim();                        // 수량 뒤 마침표도 조립기 몫
      const had = getPath(doc, path);
      // 조립기가 수량 뒤 마침표를 보장하므로, 마침표만 다르면 '안 고친 것'이다
      const bare = x => String(x).replace(/\.$/, '').trim();
      if (typeof had === 'string' && bare(had) === bare(t)) return;
      if (t || (had !== undefined && had !== null)) setPath(doc, path, t);
      return;
    }
    if (path.endsWith('.html')) {
      // 1p 본문 — 강조 span(num/accent/delta)을 살려 마크업 그대로 저장
      const c = 이어붙임(els).cloneNode(true);
      c.querySelectorAll('span.jachigan-run').forEach(x => x.replaceWith(...x.childNodes));
      c.normalize();
      setPath(doc, path, c.innerHTML.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim());
      return;
    }
    if (el.dataset.orig !== undefined) {
      // 화면에는 사람말로 다듬어 보여준 값 — 사용자가 고치지 않았으면 원본을 그대로 둔다
      const now = textOf(이어붙임(els));
      setPath(doc, path, now === (el.dataset.shown || '') ? el.dataset.orig : now);
      return;
    }
    if (el.classList.contains('fr-sum-block')) return;   // 컨테이너
    if (el.closest('.fr-box')) return;                  // 박스 내부는 boxOf가 통째로 처리
    if (el.closest('.fr-fig')) return;                  // 도식 내부는 syncFigSpec이 처리
    // 픽토그램 — 나열(sl-pictos)은 배열 경로, 카드(sl-picto)는 배열 원소 경로를 달고 있어
    // 폴백 텍스트로 새면 배열/객체{아이콘·라벨·설명}가 통째로 문자열로 덮여 왕복이 깨진다
    // (도식·이미지가 전용 처리로 피하는 것과 같은 함정). 아이콘은 화면에 SVG 만 있고
    // 이름이 없으므로 data-icon 로 보존하고, 라벨·설명은 안쪽 .tx 하위 경로가 패치한다.
    if (el.classList.contains('sl-pictos')) return;      // 나열 컨테이너 — 손대지 않는다(원소 경로가 처리)
    if (el.classList.contains('sl-picto')) {             // 카드 — 아이콘만 data-icon 로 되쓰고 라벨·설명은 하위 경로에 맡긴다
      if (el.dataset.icon != null && el.dataset.icon !== '') setPath(doc, path + '.아이콘', el.dataset.icon);
      return;
    }
    setPath(doc, path, textOf(이어붙임(els)));
  });
  // ①-b data-arr 로 표시된 시퀀스는 DOM 순서로 통째 재구성한다
  //     (순서 이동·추가·삭제가 한 번에 반영된다 — 경로 인덱스에 기대지 않는다)
  const seqGroups = {};
  document.querySelectorAll('[data-arr]').forEach(el => {
    const base = (el.dataset.path || el.dataset.parent || '').replace(/\.\d+$/, '');
    if (!base) return;
    (seqGroups[base] = seqGroups[base] || []).push(el);
  });
  Object.entries(seqGroups).forEach(([base, els]) => {
    setPath(doc, base, els.map(x => {
      const txs = [...x.querySelectorAll('.tx')];
      return textOf(txs.length ? 이어붙임(txs) : x);
    }));
  });
  // ①-c 포함/제외 플래그
  document.querySelectorAll('[data-flag]').forEach(el => {
    setPath(doc, el.dataset.flag, el.dataset.on !== 'false');
  });
  // ①-d 값 순환(등장요소 가능성 등)
  document.querySelectorAll('[data-cycle]').forEach(el => {
    if (el.dataset.lv) setPath(doc, el.dataset.cycle, el.dataset.lv);
  });
  // ② 화면에서 사라진 경로는 모델에서도 지운다(삭제 반영) — 배열은 뒤에서부터
  const alive = new Set([...document.querySelectorAll('[data-path]')].map(x => x.dataset.path));
  const anyAlive = base => [...alive].some(p => p.startsWith(base + '.'));
  // 부모가 화면에 있으면, 자식이 **다 지워져 비어도** 정리한다.
  // `anyAlive` 만 보면 '마지막 하나를 지운 절' 이 "화면에 없는 영역" 으로 오인돼
  // 지운 것이 되살아난다(2026-08-06 실측: 절은 살아 있는데 items 가 0 이 되자 그랬다).
  const 부모가_살아있나 = base => {
    const i = base.lastIndexOf('.');
    if (i < 0) return true;                   // 최상위 배열(별첨 등)은 문서에 늘 있다
    const 부모 = base.slice(0, i);            // sections.3.items → sections.3
    return alive.has(부모) || [...alive].some(p => p.startsWith(부모 + '.'));
  };
  function prune(arr, base) {
    // 이 영역이 화면에 아예 없으면(gov 의 요약처럼 장르가 안 그리는 곳) 손대지 않는다
    if (!anyAlive(base) && !부모가_살아있나(base)) return;
    for (let i = arr.length - 1; i >= 0; i--) {
      // **열쇠를 하나로 고정하지 않는다.** 같은 배열 안에서도 마디마다 열쇠가 다르다 —
      // 규정 본문은 장·조가 `제목`, 항·호·목은 `text` 다. 열쇠 하나만 보면
      // 다른 열쇠를 쓴 마디를 '지워진 것' 으로 오인해 통째로 날린다
      // (2026-08-06: 이 실수로 규정·시행문·보도자료의 왕복이 깨졌다).
      const 앞 = `${base}.${i}`;
      const 살았나 = alive.has(앞) ||
        [...alive].some(p => p === 앞 || p.startsWith(앞 + '.'));
      if (!살았나) arr.splice(i, 1);
    }
  }
  // **배열 경로를 손으로 적지 않는다.** 화면에 있는 data-path 에서 배열 자리를
  // 세어 낸다 — 전에는 풀버전 경로(장·절·별첨·요약)만 적혀 있어서
  // 1p 의 `sections.N.items` 와 시행문·규정·보도자료의 `본문.N` 은 **아예 안 돌았다.**
  // 그래서 그 네 장르에서 **삭제가 정본에 닿지 않았다**(2026-08-06 B-1 시험에서 걸림).
  // 화면에서 지웠는데 저장하면 되살아났고, 아무 신호도 없었다.
  const 배열자리 = new Map();          // '경로.접두' → 열쇠(마지막 조각) 또는 null
  alive.forEach(p => {
    const 조각 = p.split('.');
    for (let i = 조각.length - 1; i >= 1; i--) {
      if (!/^\d+$/.test(조각[i])) continue;
      const base = 조각.slice(0, i).join('.');
      const key = 조각.slice(i + 1).join('.') || null;
      if (!배열자리.has(base)) 배열자리.set(base, key);
    }
  });
  // 화면에서 **통째로 비어 버린 배열**은 위 수집에 안 잡힌다(살아 있는 경로가 없으니).
  // 같은 꼴의 형제 경로에서 이름을 빌려 와 채운다 — sections.0.items 가 있으면
  // sections.3.items 도 봐야 한다.
  [...배열자리.keys()].forEach(base => {
    const m = base.match(/^(.*)\.(\d+)\.(.+)$/);
    if (!m) return;
    const [, 뿌리, , 끝] = m;
    const 형제 = getPath(doc, 뿌리);
    if (!Array.isArray(형제)) return;
    형제.forEach((_, i) => {
      const b = `${뿌리}.${i}.${끝}`;
      if (!배열자리.has(b)) 배열자리.set(b, 배열자리.get(base));
    });
  });
  배열자리.forEach((key, base) => {
    const arr = getPath(doc, base);
    if (Array.isArray(arr)) prune(arr, base);
  });
  // ③ 새로 추가된 블록(경로 없음)을 소속 배열 끝에 얹는다
  document.querySelectorAll('[data-new]:not([data-arr])').forEach(el => {
    const parent = el.dataset.parent; if (!parent) return;
    let arr = getPath(doc, parent);
    // **없으면 만든다.** 문서에 아직 그 배열이 없으면(박스를 처음 넣는 절 등)
    // 여기서 조용히 되돌아가 새로 만든 것이 통째로 사라졌다
    // (2026-08-06: addBox 로 만든 박스가 저장에 한 번도 안 실렸다).
    if (!Array.isArray(arr)) {
      const i = parent.lastIndexOf('.');
      const 뿌리 = i < 0 ? null : getPath(doc, parent.slice(0, i));
      if (!뿌리 || typeof 뿌리 !== 'object') return;
      arr = []; 뿌리[parent.slice(i + 1)] = arr;
    }
    if (el.classList.contains('fr-box')) arr.push(boxOf(el));
    // 그림이 먼저다 — .fr-img 도 .fr-fig 클래스를 함께 갖고 있어(①의 1137행과 같은 함정),
    // 순서가 뒤바뀌면 새 그림이 도식 스펙(figSpec)으로 잘못 저장된다.
    else if (el.classList.contains('fr-img')) arr.push(imgSpec(el));
    else if (el.classList.contains('fr-fig')) arr.push(figSpec(el));
    else {
      const lv = el.classList.contains('i-l4') ? 4 : el.classList.contains('i-l3') ? 3 : 2;
      arr.push(parent.endsWith('항목') && !el.classList.contains('fr-annex-item')
        ? { level: lv, text: textOf(el) } : textOf(el));
    }
  });
  // ④ 항목 레벨 변경 반영
  document.querySelectorAll('.blk[data-path$=".text"]').forEach(el => {
    if (!LVORDER.some(c => el.classList.contains(c))) return;
    const lv = el.classList.contains('i-l4') ? 4 : el.classList.contains('i-l3') ? 3 : 2;
    const base = el.dataset.path.replace(/\.text$/, '');
    const it = getPath(doc, base);
    if (it && typeof it === 'object') it.level = lv;
  });
  // ④-b 끝 표시 옵션
  if (state.endmark !== undefined) doc.show_end_mark = state.endmark;
  if (state.끝표시 !== undefined) doc['끝표시'] = state.끝표시;
  // ⑤ 스타일(대기 반영)
  const styleNow = document.documentElement.dataset.style === 'gov' ? '정부부처형' : null;
  const styleWant = state.pendingStyle || styleNow;
  if (styleWant === '정부부처형') {
    doc['스타일'] = '정부부처형';
    const pt = getComputedStyle(document.documentElement).getPropertyValue('--pt').trim();
    if (pt) doc['포인트색'] = pt;
  } else delete doc['스타일'];
  // 글꼴·포인트색은 화면 토글이 아니라 문서의 선택이다. 안 남기면 다시 만들 때
  // 원복돼 "바꿨다"는 기록만 남고 결과가 안 남는다 — 이력이 거짓말하게 된다.
  // 다만 고른 적 없는 문서에 키를 만들면 안 고쳤는데 바뀐 것이 되므로 고른 것만 쓴다.
  if (state.글꼴) doc['글꼴'] = state.글꼴;
  if (state.포인트색) doc['포인트색'] = state.포인트색;
  // ⑥ 2단 마커 — 글꼴과 같은 이치다. 기본값(○)이면 키를 안 남긴다(왕복 불변식).
  const mk2 = document.documentElement.dataset.mk2;
  if (mk2) doc['2단마커'] = mk2; else delete doc['2단마커'];
  // ⑦ 슬라이드 디자인 영역 — 테마·효과·화면(문서 단위). 기본값이면 키를 안 남긴다(왕복 불변식).
  if (state.테마 !== undefined) { if (state.테마 && state.테마 !== '네이비') doc['테마'] = state.테마; else delete doc['테마']; }
  if (state.효과 !== undefined) { if (state.효과 && state.효과 !== '페이드') doc['효과'] = state.효과; else delete doc['효과']; }
  if (state.화면 !== undefined) doc['화면'] = state.화면;
  // ⑧ 슬라이드 자유배치 — 각 슬라이드의 배치모드(자유 여부)와 개체 절대좌표(배치)를 되쓴다.
  //    좌표는 sl-placed 의 inline %(left/top/width/height)를 읽는다. 흐름이면 배치모드·배치를
  //    지운다(기본값 불변식). 슬라이드 아닌 장르엔 .sl-page[data-slide-idx]가 없어 무해하다.
  document.querySelectorAll('.sl-page[data-slide-idx]').forEach(sec => {
    const i = sec.dataset.slideIdx;
    const s = (doc['슬라이드'] || [])[i];
    if (!s || typeof s !== 'object') return;
    if (sec.classList.contains('sl-free')) {
      s['배치모드'] = '자유';
      const b = {};
      sec.querySelectorAll('[data-배치경로]').forEach(el => {
        const role = el.dataset['배치경로'].split('.').pop();
        const st = el.style, num = k => parseFloat(st[k]) || 0;   // 화면 값 그대로(반올림은 드래그가 함)
        b[role] = { x: num('left'), y: num('top'), w: num('width'), h: num('height') };
      });
      s['배치'] = b;
    } else { delete s['배치모드']; delete s['배치']; }
  });
  return { doc, instructions: state.notes, ops: state.ops,
           보관요청: state.보관요청 || null };
}
let sT;
// 저장은 두 겹이다.
//   ① 화면(localStorage) — 400ms 마다. 창이 닫혀도 안 잃는다. 서버가 없어도 된다.
//   ② 문서(서버 POST /save) — 1.5초 동안 손을 멈추면. 정본 반영·이력·재조립까지 간다.
// 예전에는 ①만 하고 사람이 채팅에 "다 고쳤어요"라고 말해야 ②가 됐다. 그러면
// 저장했는데 반영 안 된 상태가 생기고, Claude 가 브라우저를 읽을 수 있어야만 돌았다.
let sT2, 보내는중 = false;
function save() { clearTimeout(sT); sT = setTimeout(() => {
  try {
    const snap = serialize();
    snap._저장때 = new Date().toLocaleString('ko-KR',
      { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    localStorage.setItem(KEY, JSON.stringify(snap));
    st.textContent = '화면에 저장했습니다 — 문서에 반영하는 중…';
    st.classList.add('on');
    보내기();
  } catch (e) { st.textContent = 채팅표면
      ? '저장하지 못했습니다 — 창을 닫지 말고 채팅으로 알려 주세요'
      : '저장하지 못했습니다 — 새로고침한 뒤 다시 시도해 주세요'; }
}, 400); }

function 보내기() { clearTimeout(sT2); sT2 = setTimeout(async () => {
  if (보내는중) { 보내기(); return; }          // 앞 요청이 끝난 뒤에 다시
  보내는중 = true;
  try {
    const snap = JSON.parse(localStorage.getItem(KEY) || '{}');
    if (!snap.doc) { 보내는중 = false; return; }
    // WP-S10 2차-B — 문체 진단은 반영(/save)과 **따로** 흐른다(await 안 한다). 카드를
    // 띄우는 일이 반영을 늦추거나, 반영 실패가 진단을 막으면 안 된다 — 둘은 별개 관심사다.
    문체동의진단(snap.doc);
    const r = await fetch('/save', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(snap) });
    const j = await r.json();
    if (j.ok) {
      // **정본의 새 수정시각을 받아 원본에 반영한다.** 안 받으면 다음 저장 때
      // 낙관적 잠금이 "그 사이 바뀌었다"며 거부한다 — 바꾼 게 우리인데도.
      if (j.수정시각) { SRCDOC._수정시각 = j.수정시각; snap.doc._수정시각 = j.수정시각;
                     localStorage.setItem(KEY, JSON.stringify(snap)); }
      const 몇 = (j.로그.match(/바뀐 곳 (\d+)군데/) || [])[1];
      st.textContent = 몇 ? `문서에 반영했습니다 — ${몇}군데` : '문서에 반영했습니다';
    } else if (/이 화면을 연 뒤에/.test(j.로그 || '')) {
      st.textContent = '다른 곳에서 이 문서가 바뀌었습니다 — 새로고침한 뒤 다시 고쳐 주세요';
    } else {
      st.textContent = 채팅표면
        ? '화면에만 저장했습니다 — 문서 반영은 채팅으로 알려 주세요'
        : '문서에 반영하지 못했습니다 — 잠시 후 다시 시도해 주세요';
    }
  } catch (e) {
    // 서버가 없어도 편집은 계속돼야 한다. 화면 저장은 이미 끝났다.
    // 스킬·MCP 는 서버가 없는 게 정상(채팅이 반영)이지만, 웹앱에선 서버 장애다.
    st.textContent = 채팅표면
      ? '화면에만 저장했습니다 — 문서에 반영하려면 채팅에 알려 주세요'
      : '문서에 반영하지 못했습니다 — 연결을 확인하고 다시 시도해 주세요';
  } finally { 보내는중 = false; }
}, 1500); }
document.addEventListener('input', save);

// ── 슬라이드 자유배치 — 개체(헤드·본문)를 그립으로 옮기고 8방향 핸들로 크기를 바꾼다 ──
// 픽토 자르기의 포인터 패턴과 같은 이치: inline left/top/width/height(%) 를 갱신하고 save()
// → serialize ⑧ 이 data-배치경로 로 되짚어 doc.배치 에 되쓴다(왕복). 드래그는 그립·핸들에서만
// 시작하므로 본문 클릭(자식 개체 선택)과 안 부딪힌다. 슬라이드 아닌 장르엔 sl-placed 가 없어 무해.
function 자유_비율(sec, e) {
  const r = sec.getBoundingClientRect();
  return [(e.clientX - r.left) / r.width * 100, (e.clientY - r.top) / r.height * 100];
}
// 값은 여기서만 2자리로 다듬는다 — 드래그가 만든 float 을 깔끔히 하되, serialize 는 화면 값을
// 그대로 읽어(반올림 안 함) 손으로 적은 임의 정밀도도 왕복이 정확하다(자리를 둘로 안 나눈다).
const 자유_고정 = v => Math.round(Math.max(0, Math.min(100, v)) * 100) / 100;
const 자유_둥글 = v => Math.round(v * 100) / 100;
function 자유핸들달기(el) {
  if (el.querySelector(':scope > .fp-grip')) return;
  const grip = document.createElement('div');
  grip.className = 'fp-grip'; grip.dataset.dir = 'move'; grip.textContent = '✥ 옮기기';
  el.appendChild(grip);
  ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].forEach(d => {
    const h = document.createElement('div'); h.className = 'fp-h fp-' + d; h.dataset.dir = d; el.appendChild(h);
  });
}
function 자유배치_달기(sec) {
  sec.querySelectorAll('.sl-placed').forEach(el => { el.classList.add('fp-move'); 자유핸들달기(el); });
}
let 자유끌기 = null;
// 마우스 이벤트를 쓴다(포인터가 아니라) — 픽토 자르기 선례와 같고, 임베디드 브라우저·자동화
// 도구가 포인터 이벤트를 늘 합성하진 않기 때문이다. 데스크톱 편집이라 터치는 대상 아님.
document.addEventListener('mousedown', e => {
  const grip = e.target.closest('.fp-grip'), handle = e.target.closest('.fp-h');
  if (!grip && !handle) return;                    // 그립·핸들에서만 끈다(본문 클릭은 선택으로)
  const el = e.target.closest('.sl-placed'); if (!el) return;
  const sec = el.closest('.sl-page.sl-free'); if (!sec) return;
  e.preventDefault();
  const [px, py] = 자유_비율(sec, e), st = el.style, v = k => parseFloat(st[k]) || 0;
  자유끌기 = { el, sec, dir: handle ? handle.dataset.dir : null, px, py,
    x: v('left'), y: v('top'), w: v('width') || 100, h: v('height') || 100 };
  select(el);
}, true);
document.addEventListener('mousemove', e => {
  const g = 자유끌기; if (!g) return;
  const [mx, my] = 자유_비율(g.sec, e), dx = mx - g.px, dy = my - g.py, st = g.el.style;
  if (!g.dir) {                                    // 이동 — 개체가 지면 밖으로 안 나가게 x+w·y+h 를 가둔다
    st.left = 자유_둥글(Math.max(0, Math.min(100 - g.w, g.x + dx))) + '%';
    st.top = 자유_둥글(Math.max(0, Math.min(100 - g.h, g.y + dy))) + '%';
  } else {                                         // 크기 조절(방향별) — 지면 안에 가둔다
    let x = g.x, y = g.y, w = g.w, h = g.h;
    if (g.dir.includes('e')) w = g.w + dx;
    if (g.dir.includes('s')) h = g.h + dy;
    if (g.dir.includes('w')) { w = g.w - dx; x = g.x + dx; }
    if (g.dir.includes('n')) { h = g.h - dy; y = g.y + dy; }
    if (x < 0) { w += x; x = 0; }                  // 왼/위로 나가면 0 에서 멈추고 폭·높이를 흡수
    if (y < 0) { h += y; y = 0; }
    w = Math.max(6, Math.min(w, 100 - x)); h = Math.max(6, Math.min(h, 100 - y));   // 최소 6%·지면 안
    st.left = 자유_둥글(x) + '%'; st.top = 자유_둥글(y) + '%';
    st.width = 자유_둥글(w) + '%'; st.height = 자유_둥글(h) + '%';
  }
}, true);
document.addEventListener('mouseup', () => {
  const g = 자유끌기; if (!g) return; 자유끌기 = null;
  state.ops.push({ action: g.dir ? '개체 크기' : '개체 이동' });
  save(); if (state.sel === g.el) renderPanel();
}, true);
// 토글: 흐름 ⇄ 자유. 흐름→자유면 헤드·본문에 기본 배치를 주고 sl-placed·경로·핸들을 단다.
function 자유배치토글(sec) {
  if (!sec) return;
  const i = sec.dataset.slideIdx, head = sec.querySelector('.sl-head'), body = sec.querySelector('.sl-body');
  if (!head && !body) { toast('이 슬라이드는 자유배치를 지원하지 않습니다'); return; }
  if (sec.classList.contains('sl-free')) {         // 자유 → 흐름
    sec.classList.remove('sl-free');
    sec.querySelectorAll('.sl-placed').forEach(el => {
      el.classList.remove('sl-placed', 'fp-move'); el.removeAttribute('style');
      el.removeAttribute('data-배치경로');
      el.querySelectorAll(':scope > .fp-grip, :scope > .fp-h').forEach(h => h.remove());
    });
    state.ops.push({ action: '흐름 배치로' });
  } else {                                          // 흐름 → 자유
    sec.classList.add('sl-free');
    const 기본 = { 헤드: { x: 5, y: 6, w: 62, h: 16 }, 본문: { x: 6, y: 30, w: 88, h: 62 } };
    const 앉히기 = (el, role) => {
      if (!el) return; const b = 기본[role];
      el.classList.add('sl-placed');
      el.style.cssText = `left:${b.x}%;top:${b.y}%;width:${b.w}%;height:${b.h}%`;
      el.setAttribute('data-배치경로', `슬라이드.${i}.배치.${role}`);
    };
    앉히기(head, '헤드'); 앉히기(body, '본문'); 자유배치_달기(sec);
    state.ops.push({ action: '자유 배치로' });
  }
  save(); renderPanel();
}
// 편집기가 뜰 때, doc 에서 이미 자유인 슬라이드에 그립·핸들을 단다.
document.querySelectorAll('.sl-page.sl-free').forEach(자유배치_달기);

// ── 상단바: 스타일·포인트색·글꼴·재조판 ──
function toast(m) { note.textContent = m; note.style.display = 'block';
  setTimeout(() => note.style.display = 'none', 1800); }
// 스타일 전환은 표지·목차·요약의 '구조'를 바꾸므로 CSS만으로는 미리보기가 불가능하다.
// 어중간한 혼합 상태를 보여주는 대신, 의도를 기록하고 재조립 때 반영한다.
const CUR_STYLE = document.documentElement.dataset.style === 'gov' ? 'gov' : 'std';
document.querySelectorAll('.edit-bar [data-style-btn]').forEach(b => b.onclick = () => {
  const want = b.dataset.styleBtn;
  document.querySelectorAll('.edit-bar [data-style-btn]').forEach(x => x.classList.toggle('on', x === b));
  state.pendingStyle = (want === CUR_STYLE) ? null : (want === 'gov' ? '정부부처형' : '기관 표준형');
  state.ops = state.ops.filter(o => o.action !== '스타일');
  if (state.pendingStyle) state.ops.push({ action: '스타일', to: state.pendingStyle });
  pendingBar(); save();
});
function pendingBar() {
  const p = [];
  if (state.pendingStyle) p.push('문서 모양 → ' + state.pendingStyle);

  const el = document.getElementById('pending-note');
  el.textContent = p.length ? '문서를 다시 만들 때 반영: ' + p.join(' · ') : '';
}
const pick = document.getElementById('ptcolor');
if (pick) pick.oninput = () => {
  document.documentElement.style.setProperty('--pt', pick.value);
  state.포인트색 = pick.value;
  state.ops.push({ action: '강조색', to: pick.value }); save();
};
document.querySelectorAll('.edit-bar [data-font]').forEach(b => b.onclick = () => {
  document.documentElement.dataset.fonts = b.dataset.font;
  state.글꼴 = b.dataset.font;
  document.querySelectorAll('.edit-bar [data-font]').forEach(x => x.classList.toggle('on', x === b));
  state.ops.push({ action: '글꼴', to: b.textContent });
  if (typeof repaginate === 'function') repaginate();
});
// ── 슬라이드 디자인 영역 — 테마(라디오)·효과(라디오)·화면(토글) ──
document.querySelectorAll('.edit-bar [data-theme-btn]').forEach(b => b.onclick = () => {
  const v = b.dataset.themeBtn;
  document.querySelectorAll('.edit-bar [data-theme-btn]').forEach(x => x.classList.toggle('on', x === b));
  state.테마 = v;
  if (v === '네이비') document.documentElement.removeAttribute('data-테마');
  else document.documentElement.setAttribute('data-테마', v);   // 라이브 미리보기(색이 즉시 바뀐다)
  state.ops.push({ action: '테마', to: b.textContent });
  save();
});
document.querySelectorAll('.edit-bar [data-fx-btn]').forEach(b => b.onclick = () => {
  document.querySelectorAll('.edit-bar [data-fx-btn]').forEach(x => x.classList.toggle('on', x === b));
  state.효과 = b.dataset.fxBtn;
  state.ops.push({ action: '효과', to: b.textContent });   // 발표 보기에서 적용(편집 화면은 정적)
  save();
});
document.querySelectorAll('.edit-bar [data-screen-btn]').forEach(b => b.onclick = () => {
  const k = b.dataset.screenBtn, now = !b.classList.contains('on');
  b.classList.toggle('on', now);
  if (state.화면 === undefined) state.화면 = Object.assign({}, SRCDOC['화면'] || {});
  if (now) delete state.화면[k]; else state.화면[k] = false;   // 켬=키 없음(기본) · 끔=false
  state.ops.push({ action: '화면', to: b.textContent + (now ? ' 켬' : ' 끔') });
  save();
});
// 여러 장 전용 단추 — 1페이지·시행문·구성 설계 화면에는 없다.
// (없는 걸 null 째로 건드려 스크립트가 통째로 죽던 자리. on()으로 감싼다.)
const on = (id, f) => { const e = document.getElementById(id); if (e) e.onclick = f; };
on('btn-repag', () => { repaginate(); toast('줄과 쪽을 다시 맞췄습니다'); });
on('btn-copy', () => {
  const d = serialize().doc;
  const lines = [d.표지?.제목 || '', ''];
  (d.장 || []).forEach((c, i) => {
    lines.push(`${['Ⅰ','Ⅱ','Ⅲ','Ⅳ','Ⅴ','Ⅵ','Ⅶ','Ⅷ','Ⅸ','Ⅹ'][i] || (i + 1)}. ${c.제목}`);
    (c.절 || []).forEach(s => { lines.push(`  □ ${s.제목}`);
      (s.항목 || []).forEach(it => lines.push('    '.repeat(it.level - 1) +
        ({2:'○ ',3:'- ',4:'※ '}[it.level] || '') + it.text.replace(/<\/?[a-z]+>/g, ''))); });
  });
  const ta = document.createElement('textarea'); ta.value = lines.join('\n');
  document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); toast('본문 복사됨'); } catch (e) { toast('복사 실패'); }
  ta.remove();
});
// ── 판 보관 요청 ────────────────────────────────────────────────────
// 이 화면은 파일을 못 쓴다. 그래서 단추는 '요청'만 남기고, 실제 판은
// "고쳐놨어" 때 apply_edit_any 가 뜬다. 새 쓰기 경로를 만들지 않는다.
// prompt() 는 이 화면(임베디드 브라우저)에서 예외를 던지고 confirm() 은 조용히 false를
// 돌려준다 — 둘 다 쓰면 단추가 아무 일도 안 하고 사용자는 눌렀다고 믿는다.
// 그래서 묻는 것은 전부 화면 안에서 한다.
function 줄입력(라벨, 필수) {
  const wrap = document.createElement('label');
  wrap.style.cssText = 'display:block;margin-top:6px;font-size:12.5px';
  wrap.textContent = 라벨 + (필수 ? ' (필수)' : ' (선택)');
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.style.cssText = 'display:block;width:100%;margin-top:3px;padding:5px 7px;'
    + 'border:1px solid var(--ai-color-line-strong);border-radius:5px;font:inherit;box-sizing:border-box';
  wrap.appendChild(inp);
  return { wrap: wrap, get: () => inp.value.trim(), focus: () => inp.focus() };
}
// ── 되돌림 지점 — 여기로 돌아올 수 있게 이름 붙여 잡아 두는 자리(최대 3개) ──────
// 웹앱(http)은 서버가 목록·되돌리기·지우기를 처리한다. 스킬·MCP(file://)는 서버가
// 없어 채팅이 반영하므로, 잡기만 하고 목록·되돌리기는 이력(채팅) 몫으로 둔다.
const 지점최대 = 3;
async function 부르기(이름, 인자, 쓰기) {
  const r = 쓰기
    ? await fetch('/api/' + 이름, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(인자 || {}) })
    : await fetch('/api/' + 이름 + '?' + new URLSearchParams(인자 || {}));
  return r.json();
}
function 되돌림지점열기() {
  if (채팅표면) return 지점잡기();      // 스킬·MCP — 잡기만(채팅이 반영·되돌리기)
  되돌림지점패널();                     // 웹앱 — 목록 + 잡기 + 되돌리기 + 지우기
}
async function 되돌림지점패널() {
  document.querySelectorAll('.keep-bar').forEach(x => x.remove());
  const bar = document.createElement('div');
  bar.className = 'resume-bar keep-bar';
  bar.innerHTML = '<b>되돌림 지점</b> — 여기로 돌아올 수 있게 이름을 붙여 잡아 둡니다 (최대 '
    + 지점최대 + '개). 잡아 둔 지점으로 언제든 되돌릴 수 있습니다.';
  const 목록 = document.createElement('div'); 목록.style.cssText = 'margin-top:8px';
  bar.appendChild(목록);
  const row = document.createElement('div'); row.className = 'row'; bar.appendChild(row);
  const note = document.createElement('div');
  note.style.cssText = 'margin-top:6px;font-size:11.5px;opacity:.8';
  note.textContent = '이 기록은 작업하실 때 참고하시라고 모아 둔 것입니다. 기관의 공식 기록은 아닙니다.';
  bar.appendChild(note);
  document.body.insertBefore(bar, document.body.firstChild);
  async function 그리기() {
    목록.innerHTML = '<div style="opacity:.6;font-size:12px">불러오는 중…</div>';
    const r = await 부르기('history', { key: FN });
    const 지점 = ((r && r.ok && r['값'] && r['값']['판']) || []).filter(v => v['종류'] === '직접');
    목록.innerHTML = '';
    if (!지점.length)
      목록.innerHTML = '<div style="opacity:.7;font-size:12px">아직 잡아 둔 지점이 없습니다.</div>';
    지점.forEach(v => {
      const 이름 = v['메모'] || v['고친 이유'] || ('버전 ' + v['버전']);
      const 사유 = v['고친 이유'] || '';
      const d = document.createElement('div');
      d.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 0;'
        + 'border-top:1px solid var(--ai-color-line)';
      d.innerHTML = '<div style="flex:1"><b>' + esc(이름) + '</b>'
        + (사유 ? '<div style="font-size:11.5px;opacity:.75">' + esc(사유) + '</div>' : '')
        + '<div style="font-size:11px;opacity:.55">' + esc(v['때'] || '') + '</div></div>';
      d.appendChild(btn('되돌리기', () => 지점되돌리기(v['버전'], 이름), 'good'));
      d.appendChild(btn('지우기', () => 지점지우기(v['버전'], 그리기), 'danger'));
      목록.appendChild(d);
    });
    row.innerHTML = '';
    if (지점.length < 지점최대) {
      row.appendChild(btn('＋ 되돌림 지점 잡기', () => { bar.remove(); 지점잡기(); }, 'good'));
    } else {
      const m2 = document.createElement('div');
      m2.style.cssText = 'flex:1;font-size:12px;color:var(--ai-color-issue)';
      m2.textContent = '지점 ' + 지점최대 + '개가 찼습니다 — 하나를 지우고 다시 잡아 주세요.';
      row.appendChild(m2);
    }
    row.appendChild(btn('닫기', () => bar.remove()));
  }
  그리기();
}
// 지점 잡기 — 이름 + 사유를 받아 저장에 실어 보낸다(서버가 apply_edit_any 로 남긴다).
function 지점잡기() {
  document.querySelectorAll('.keep-bar').forEach(x => x.remove());
  const bar = document.createElement('div');
  bar.className = 'resume-bar keep-bar';
  bar.innerHTML = (채팅표면
      ? '<b>되돌림 지점을 잡습니다</b> — 채팅에 알려 주시면 그때 남깁니다. '
      : '<b>되돌림 지점을 잡습니다</b> — 저장되는 대로 서버가 남깁니다. ')
    + '여기로 돌아올 수 있게 이름과 사유를 적어 주세요. 화면·인쇄본도 함께 남습니다.';
  const m = 줄입력('이 지점의 이름 (예: 검토 요청 전)', false);
  bar.appendChild(m.wrap);
  const w = 줄입력('왜 여기에 지점을 잡나요 (사유)', true);
  bar.appendChild(w.wrap);
  const row = document.createElement('div'); row.className = 'row';
  row.appendChild(btn('지점 잡기', () => {
    if (!w.get()) { toast('사유를 한 줄 적어 주시면 잡습니다'); w.focus(); return; }
    state.보관요청 = { 종류: '직접', 메모: m.get(), 고친이유: w.get() };
    save(); bar.remove();
    toast(채팅표면
      ? '채팅에 "다 고쳤어요"라고 알려 주시면 지점을 남깁니다'
      : '지점을 잡습니다 — 저장되는 대로 목록에 나타납니다');
  }, 'good'));
  row.appendChild(btn('취소', () => bar.remove()));
  bar.appendChild(row);
  const note = document.createElement('div');
  note.style.cssText = 'margin-top:6px;font-size:11.5px;opacity:.8';
  note.textContent = '이 기록은 작업하실 때 참고하시라고 모아 둔 것입니다. 기관의 공식 기록은 아닙니다.';
  bar.appendChild(note);
  document.body.insertBefore(bar, document.body.firstChild);
  m.focus();
}
async function 지점되돌리기(n, 이름) {
  const r = await 부르기('revert', { key: FN, n: n, 이유: '되돌림 지점 「' + (이름 || '') + '」으로 복귀' }, true);
  if (!r || !r.ok) { toast((r && r['로그']) || '되돌리지 못했습니다'); return; }
  localStorage.removeItem(KEY);     // 옛 화면 버퍼가 되돌린 것을 덮지 않게
  toast('되돌렸습니다 — 화면을 새로 불러옵니다');
  setTimeout(() => location.reload(), 600);
}
async function 지점지우기(n, 다시그리기) {
  const r = await 부르기('delpoint', { key: FN, n: n }, true);
  if (!r || !r.ok) { toast((r && r['로그']) || '지우지 못했습니다'); return; }
  toast('지웠습니다'); if (다시그리기) 다시그리기();
}
const bk = document.getElementById('btn-keep');
if (bk) bk.onclick = () => 되돌림지점열기();

// 완료·닫기 — /workspace/app.html 로의 이동은 **웹앱에서만** 유효하다. 플러그인(file://)엔
// 그 서버·파일이 없어 location.replace 하면 방금까지 편집하던 화면이 브라우저 오류페이지
// (ERR_FILE_NOT_FOUND)로 대체된다. 그래서 채팅표면이면 이동하지 않고, 마지막 편집을 잃지
// 않게 화면을 **즉시** 저장(400ms 디바운스 건너뜀)한 뒤 반영을 시도하고 탭만 닫는다.
function 편집마침() {
  try {
    clearTimeout(sT);
    const snap = serialize();
    snap._저장때 = new Date().toLocaleString('ko-KR',
      { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    localStorage.setItem(KEY, JSON.stringify(snap));
  } catch (e) { /* 화면 저장 실패해도 아래로 진행 — 창을 오류로 대체하진 않는다 */ }
  if (채팅표면) {
    보내기();   // 서버가 있으면 반영 시도, 없으면(플러그인) 화면 저장만 — 반영은 채팅의 Claude
    toast('편집을 마쳤습니다 — 이 탭을 닫고 채팅으로 돌아가세요. 반영은 채팅이 합니다');
    window.close();   // 스크립트가 연 탭이면 닫히고, 아니면 무해한 no-op(오류페이지로 안 감)
  } else {
    window.close();
    setTimeout(function () { location.replace('/workspace/app.html'); }, 350);
  }
}
['btn-done', 'btn-close'].forEach(function (id) {
  const b = document.getElementById(id);
  if (b) b.addEventListener('click', 편집마침);
});

// ── 이어서 하기 ─────────────────────────────────────────────────────
// 고치다 만 것이 이 화면에만 남아 있다가 창을 닫으면 사라진다.
// 그런데 복구를 그냥 붙이면 **새 손실 경로**가 열린다 — 그 사이 문서가 다시
// 만들어졌다면 옛 버퍼를 되살리는 순간 새 내용이 조용히 지워진다.
// 그래서 반드시 _수정시각을 대조하고, 기계가 둘을 합치지 않는다.
function 이어서하기() {
  let buf;
  try { buf = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return; }
  if (!buf || !buf.doc) return;
  const 그때 = (buf.doc || {})['_수정시각'];
  const 지금 = (SRCDOC || {})['_수정시각'];
  const 같다 = !그때 || !지금 || 그때 === 지금;
  const 언제 = (buf.doc && buf._저장때) || '';

  const bar = document.createElement('div');
  bar.className = 'resume-bar' + (같다 ? '' : ' danger');
  bar.innerHTML = 같다
    ? `<b>고치시던 내용이 남아 있습니다.</b>${언제 ? ' ' + 언제 + '에 마지막으로 저장했습니다.' : ''}`
    : '<b>그 사이에 문서를 다시 만들었습니다.</b> 고치시던 내용을 되살리면 '
      + '새로 만든 내용이 지워집니다.';
  const row = document.createElement('div'); row.className = 'row';
  let 각오 = false;
  const go = btn(같다 ? '이어서 고치기' : '그래도 되살리기', () => {
    if (!같다 && !각오) {
      각오 = true;
      go.textContent = '한 번 더 누르면 새로 만든 내용이 지워집니다';
      return;                                   // confirm() 을 못 쓰므로 두 번 누르기로
    }
    되살리기(buf); bar.remove();
  }, 같다 ? 'good' : 'danger');
  row.appendChild(go);
  row.appendChild(btn(같다 ? '버리고 처음부터' : '버리고 새 문서로 시작', () => {
    localStorage.removeItem(KEY); bar.remove(); toast('고치던 내용을 버렸습니다');
  }));
  bar.appendChild(row);
  document.body.insertBefore(bar, document.body.firstChild);
}
// 되살리기는 화면을 다시 그리는 것이 아니라 '무엇이 달랐는지'만 알려준다.
// 기계가 두 쪽을 합치면 어느 쪽 뜻도 아닌 문서가 나오고 그 사실이 안 남는다.
function 되살리기(buf) {
  state.notes = buf.instructions || {};
  state.ops = buf.ops || [];
  // 저장기와 **같은 잣대**로 읽어야 한다. 경로 하나가 여러 조각으로 흩어져 있으면
  // 조각마다 부분 문자열이 나와 전부 '달라졌다'가 되고, 그 다음 줄이 조각마다
  // 온전한 문장을 써 넣어 한 문단이 조각 수만큼 반복된다 — 사용자가 한 글자도
  // 안 고쳤는데 문서가 망가진다(2026-08-04 확정, 규정 99자 → 645자·같은 문장 7회).
  // 지금은 자간 조정이 요소를 안 쪼개지만, 읽는 잣대가 두 벌이면 언제든 다시 갈린다.
  const diff = [];
  경로조각().forEach(([path, els]) => {
    const v = getPath(buf.doc, path);
    if (typeof v === 'string' && v !== textOf(이어붙임(els)).trim()) diff.push([path, els, v]);
  });
  diff.forEach(([path, els, v]) => {
    const leaf = planLeaf(els[0]);
    // 1p 본문(.html)은 값에 강조 마크업이 들어 있다. textContent 로 넣으면 태그가
    // **글자로 박혀** 화면에 <span class="num"> 이 그대로 보이고, 그게 저장까지 된다
    // (2026-08-04 실측: bt01 한 문서에서 8군데). 마크업은 마크업으로 넣는다.
    if (path.endsWith('.html')) leaf.innerHTML = 허용마크업(v);
    else setText(leaf, v);
    els.slice(1).forEach(x => { x.textContent = ''; });   // 조각이 남아 있으면 글이 겹쳐 보인다
  });
  save();
  if (typeof repaginate === 'function') repaginate();
  toast(diff.length ? `고치시던 내용 ${diff.length}군데를 되살렸습니다`
                    : '고치신 글자는 없고, 남기신 요청만 되살렸습니다');
}
if (location.search.indexOf('selfcheck=1') < 0) 이어서하기();

renderPanel();
pendingBar();
if (typeof repaginate === 'function') setTimeout(repaginate, 200);
})();
</script>
"""


SKELETONS = Path(자료뿌리.골격뿌리())


def gen(fn, out_prefix="editor-", src_dir=None):
    """산출물·골격 HTML → 편집기 HTML. 장르는 문서에 심긴 프로파일이 알려준다."""
    base = Path(src_dir) if src_dir else SAMPLES
    src = (base / f"{fn}.html").read_text(encoding="utf-8")
    if base == SKELETONS:                      # 편집본은 buildplan/skeletons/edit/ 로 한 단계 더 들어간다
        src = src.replace('href="../../build/tokens.css', 'href="../../../build/tokens.css')
        src = src.replace('href="../skeleton.css', 'href="../../skeleton.css')
    # 편집기는 workspace/editors/ 에 놓이므로 산출물의 ../ 참조를 한 칸 더 올려야 한다.
    # 예전에는 파일 이름을 여덟 개 손으로 적어 뒀는데, 장르가 늘 때 regulation.css·
    # press.css·gmseal.js 가 빠져 편집 화면이 404 를 물고 **서식 없이** 떴다(2026-08-04).
    # 그래서 이름을 적지 않고, build/ 에 실제로 있는 파일이면 옮긴다.
    def _자산(m):
        속성, 경로, 꼬리 = m.group(1), m.group(2), m.group(3)
        실물 = (ROOT / "build" / 경로.split("/")[0]) if "/" in 경로 else (ROOT / "build" / 경로)
        return (f'{속성}="../../build/{경로}{꼬리}"' if 실물.exists()
                else m.group(0))
    src = re.sub(r'(href|src)="\.\./(?!\.\./)([^"?]+)([^"]*)"', _자산, src)

    prof = {}
    m = re.search(r'<script type="application/json" id="fr-profile">(.*?)</script>', src, re.S)
    if m:
        try:
            prof = json.loads(m.group(1))
        except Exception:
            prof = {}
    bar_spec = prof.get("상단바", {})
    gov = 'data-style="gov"' in src
    # 슬라이드 디자인 영역 초기 상태 — 현재 doc 의 테마·효과·화면(없으면 기본값)
    cur_doc = {}
    md = re.search(r'<script type="application/json" id="fr-doc">(.*?)</script>', src, re.S)
    if md:
        try:
            cur_doc = json.loads(md.group(1))
        except Exception:
            cur_doc = {}
    cur_테마 = cur_doc.get("테마") or "네이비"
    cur_효과 = cur_doc.get("효과") or "페이드"
    cur_화면 = cur_doc.get("화면") or {}
    grp = []
    for key, label in bar_spec.get("스타일", []):
        on = " class=on" if (key == "gov") == gov else ""
        grp.append(f'<button data-style-btn="{key}"{on}>{label}</button>')
    if bar_spec.get("포인트색"):
        # <input type=color> 의 value 속성은 HTML5 명세상 #rrggbb 리터럴만 받는다(var() 불가) —
        # 이 값은 앱 크롬 색이 아니라 **풀버전 문서 자신의 포인트색 기본값**(기관표준형 파랑)이라
        # 브랜드 토큰과 무관하다. build/verify_all.py 의 check_app_no_raw_hex 가 이 줄만 면제한다.
        grp.append('<input type="color" id="ptcolor" value="#0070C0" title="강조색">')
    if grp:
        grp.append('<span style="width:8px"></span>')
    for i, (key, label) in enumerate(bar_spec.get("글꼴", [])):
        grp.append(f'<button data-font="{key}"{" class=on" if i == 0 else ""}>{label}</button>')
    if bar_spec.get("글꼴"):
        grp.append('<span style="width:8px"></span>')
    # 슬라이드 디자인 영역 — 테마·효과(라디오, 하나 켬)·화면(토글, 기본 켬)
    if bar_spec.get("테마"):
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">테마</span>')
        for key, label in bar_spec["테마"]:
            grp.append(f'<button data-theme-btn="{key}"{" class=on" if key == cur_테마 else ""}>{label}</button>')
        grp.append('<span style="width:8px"></span>')
    if bar_spec.get("효과"):
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">효과</span>')
        for key, label in bar_spec["효과"]:
            grp.append(f'<button data-fx-btn="{key}"{" class=on" if key == cur_효과 else ""}>{label}</button>')
        grp.append('<span style="width:8px"></span>')
    if bar_spec.get("화면"):
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">화면</span>')
        for key, label in bar_spec["화면"]:
            켬 = cur_화면.get(key) is not False
            grp.append(f'<button data-screen-btn="{key}"{" class=on" if 켬 else ""}>{label}</button>')
        grp.append('<span style="width:8px"></span>')
    if bar_spec.get("재조판"):
        grp.append('<button id="btn-repag">↻ 줄·쪽 다시 맞춤</button>')
    if bar_spec.get("복사"):
        grp.append(f'<button id="btn-copy">📋 {bar_spec["복사"]} 복사</button>')
    auto = " · ".join(prof.get("자동", []))
    bar = (
        '<div class="edit-bar" data-editor>'
        f'<span class="grp"><b>{prof.get("라벨", "문서")}</b>'
        '<span class="warn"></span>'
        '<span id="pending-note" style="color:var(--ai-color-review);font-size:12px"></span></span>'
        f'<span class="grp">{"".join(grp)}'
        '<button id="btn-keep" title="여기로 돌아올 수 있게 이름 붙여 지점을 잡아 둡니다 (최대 3개)">되돌림 지점</button>'
        '<span class="st">아직 수정 없음</span>'
        '<span style="width:10px"></span>'
        '<button id="btn-done" title="편집을 마칩니다 — 수정은 자동 저장됩니다" '
        'style="background:var(--ai-color-signal);color:var(--ai-color-white);font-weight:700">완료</button>'
        '<button id="btn-close" title="편집 탭을 닫습니다 (수정은 자동 저장됨)">닫기</button>'
        '</span></div>'
        '<div class="copy-note" data-editor></div>'
        + (f'<!-- 자동 산출(편집 대상 아님): {auto} -->' if auto else ''))
    src = src.replace("<body>", "<body>\n" + bar, 1)
    # ui-tokens.css 는 workspace/ 에 산다 — 편집기 출력 위치가 갈리니(workspace/editors/
    # 와 buildplan/skeletons/edit/) 상대경로도 갈린다. 값을 여기 손으로 두 번 적는 대신
    # CHROME 의 자리표시자 하나를 그 위치에 맞게 채운다(SCRIPT 의 @@FN@@ 치환과 같은 결).
    TOKENS_HREF = "../../../workspace/ui-tokens.css" if base == SKELETONS else "../ui-tokens.css"
    src = src.replace("</head>", CHROME.replace("@@TOKENS_HREF@@", TOKENS_HREF) + "</head>", 1)
    src = src.replace("</body>", SCRIPT.replace("@@FN@@", fn) + "</body>", 1)
    EDITORS.mkdir(parents=True, exist_ok=True)
    out = EDITORS / f"{out_prefix}{fn}.html"
    if base == SKELETONS:
        (SKELETONS / "edit").mkdir(parents=True, exist_ok=True)
        out = SKELETONS / "edit" / f"{fn}.html"
    자료뿌리.원자쓰기(str(out), src)             # 원자 쓰기(WP-S2 ③)
    return out


def SOURCES():
    """장르 등록부는 세어서 얻는다 — 손으로 적으면 늘 때마다 빠진다.

    2026-08-04: 여기에 규정·보도자료가 빠져 있어 `--all` 이 그 둘의 편집기를 한 번도
    다시 만들지 않았다. 저장기를 고쳐도 화면은 옛 코드 그대로였고, 왕복 검사가
    '고쳤는데 안 고쳐졌다'고 나왔다. 같은 함정을 다섯 번째로 밟았다
    (자치간 SEL · 이력 SRC · verify_all BUILDS · 파급표 · 여기).
    """
    return [g["길"] for g in 자료뿌리.모듈("genres").등록부()]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] == "--skeletons":
        n = 0
        if SKELETONS.exists():
            for f in sorted(SKELETONS.glob("*.html")):
                gen(f.stem, src_dir=SKELETONS)
                n += 1
        print(f"구성 설계 화면: {n}건")
        return 0
    if sys.argv[1] == "--all":
        n = 0
        for srcname in SOURCES():
            path = Path(srcname)
            if not path.exists():
                continue
            for d in json.load(open(path, encoding="utf-8")):
                if (SAMPLES / f"{d['filename']}.html").exists():
                    gen(d["filename"])
                    n += 1
        print(f"editors: {n}건 (범용)")
    else:
        print("written:", gen(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
