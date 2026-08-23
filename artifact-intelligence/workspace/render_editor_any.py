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
  body { padding-top: 46px !important; }
  /* 문서를 좌(232)·우(268) 패널 사이 가운데로 — 전 장르 쪽 클래스 (예전 body margin-right:268 은
     아래 padding 과 겹쳐 문서를 ~150px 왼쪽으로 밀었다. 제거함) */
  .fr-page, .sheet, .gm-sheet, .pr-sheet, .sl-page, .rg-sheet {
    margin-left: auto !important; margin-right: auto !important; }
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
  /* 이어서하기/입력 바 — 좌 히스토리(232)·우 옵션(268) 패널 사이에 앉히고 그 위로 올린다
     (예전 left:0·z-index:97 은 왼쪽 패널에 덮여 복구 버튼이 안 눌렸다 — 적대검토 HIGH). */
  .resume-bar { position: fixed; top: 46px; left: 232px; right: 268px; z-index: 100;
    background: var(--ai-color-review-tint); border-bottom: 1px solid var(--ai-color-review-line);
    color: var(--ai-color-review-ink); padding: 9px 14px; font: 13px/1.5 var(--ai-font-sans); }
  @media (max-width: 1180px) { .resume-bar { left: 0; right: 0; } }
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
  /* #10 — 왼쪽 편집 히스토리 패널 (좌:히스토리 · 가운데:문서 · 우:편집옵션) */
  .hist { position: fixed; top: 46px; left: 0; bottom: 0; width: 232px; z-index: 98;
    overflow-y: auto; background: var(--ai-color-white); border-right: 1px solid var(--ai-color-line);
    padding: 13px; font: 13px/1.5 var(--ai-font-sans); box-sizing: border-box; }
  .hist h3 { font-size: 12px; color: var(--ai-color-muted); margin: 0 0 8px; font-weight: 600; }
  .hist .ud { display: flex; gap: 6px; margin-bottom: 10px; }
  .hist .ud button { flex: 1; padding: 6px 8px; border: 1px solid var(--ai-color-line);
    border-radius: var(--ai-radius-sm); background: var(--ai-color-agent-panel); cursor: pointer;
    font: inherit; font-size: 12px; text-align: center; }
  .hist .ud button:hover:not(:disabled) { background: var(--ai-color-signal-tint); border-color: var(--ai-color-signal); }
  .hist .ud button:disabled { opacity: .4; cursor: default; }
  .hist .hlist { list-style: none; margin: 0; padding: 0; }
  .hist .hlist li { padding: 6px 8px; margin: 2px 0; border-radius: var(--ai-radius-sm); cursor: pointer;
    font-size: 12px; border: 1px solid transparent; color: var(--ai-color-ink); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }
  .hist .hlist li:hover { background: var(--ai-color-signal-tint); }
  .hist .hlist li.cur { background: var(--ai-color-signal); color: var(--ai-color-white); font-weight: 700; }
  .hist .hlist li.ahead { color: var(--ai-color-muted); }
  .hist .hlist li.marked { border-color: var(--ai-color-signal); background: var(--ai-color-signal-tint); }
  .hist .hlist li.marked.cur { background: var(--ai-color-signal); }
  .hist .pin { font-weight: 700; color: var(--ai-color-signal); }
  .hist .hlist li.cur .pin { color: var(--ai-color-white); }
  .hist .dim { color: var(--ai-color-muted); font-size: 11px; }
  .hist .hlist li.cur .dim { color: var(--ai-color-white); opacity: .85; }
  .hist .unpin { float: right; opacity: .5; margin-left: 6px; }
  .hist .unpin:hover { opacity: 1; }
  .hist .pinbtn { display: block; width: 100%; margin: 0 0 10px; padding: 6px 8px; cursor: pointer;
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-agent-panel); font: inherit; font-size: 12px; text-align: center; }
  .hist .pinbtn:hover { background: var(--ai-color-signal-tint); border-color: var(--ai-color-signal); }
  .hist .hint { color: var(--ai-color-muted); font-size: 11px; margin-top: 10px; }
  /* 좌·우 패널 사이에 문서가 앉도록 본문 흐름에 좌우 여백을 준다(패널은 고정이라 그 위에 겹친다) */
  body { padding-left: 232px; padding-right: 268px; box-sizing: border-box; }
  @media (max-width: 1180px) { body { padding-left: 0; padding-right: 0; } }  /* 좁으면 겹침 허용 */
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
  if (typeof 이력쌓기 === 'function') 이력쌓기('직접 수정');   // #10 — 글자 편집은 ops.push 를 안 지나니 여기서 스냅샷
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

// ── AI 편집(BYOK) — 웹앱(http)에서 내 키로 provider 를 브라우저가 직접 부른다 ──
// 채팅표면(file://, 스킬·MCP)은 addNote 로 코딩 에이전트에게 맡기고, 웹앱은 여기로 직접 고친다.
// 키·주소·모델은 app.html 과 **같은** localStorage('ai-llm'·'ai-api-key')에서만 읽고 서버로는
// 절대 안 보낸다(사장님 규칙: 서버에 입력되면 안 된다). 서버로 가는 /save 엔 문서만 실린다.
const AI키칸 = 'ai-api-key', AI설정칸 = 'ai-llm';
function AI설정() {
  let llm = {}; try { llm = JSON.parse(localStorage.getItem(AI설정칸)) || {}; } catch (e) {}
  return { 제공자: llm.제공자 || 'anthropic', 베이스: llm.베이스 || '',
           모델: llm.모델 || '', 키: localStorage.getItem(AI키칸) || '' };
}
function AI키준비됨() { const c = AI설정(); return c.제공자 === 'ollama' ? true : !!c.키; }
function AIJSON추출(글) {
  let s = String(글 || '').trim();
  s = s.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');   // 코드펜스 벗기기(관대 추출)
  const m = s.match(/\{[\s\S]*\}/);
  if (!m) throw new Error('모델이 JSON 을 돌려주지 않았습니다 (응답이 비었거나 형식이 아님) — JSON 모드 지원 모델인지 확인하세요');
  return JSON.parse(m[0]);
}
// provider 직접 호출 → 원문 문자열. Anthropic 은 전용 규격, 나머지는 OpenAI /chat/completions.
async function AI호출(지시, 사용자글, 최대토큰) {
  const c = AI설정(); 최대토큰 = 최대토큰 || 2000;
  if (c.제공자 === 'anthropic') {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': c.키,
        'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true' },
      body: JSON.stringify({ model: c.모델 || 'claude-sonnet-5', max_tokens: 최대토큰,
        system: 지시, messages: [{ role: 'user', content: 사용자글 }] }) });
    if (!r.ok) throw new Error('모델 호출 실패 (' + r.status + ') — ' + (await r.text()).slice(0, 200));
    const j = await r.json();
    return (j.content || []).map(x => x.text || '').join('');
  }
  let base = (c.베이스 || '').trim().replace(/\/+$/, '');
  if (!base) base = c.제공자 === 'ollama' ? 'http://localhost:11434/v1' : 'https://api.featherless.ai/v1';
  const 헤더 = { 'content-type': 'application/json' };
  if (c.키) 헤더['authorization'] = 'Bearer ' + c.키;
  // JSON 모드 요청 + 시스템에 'JSON 하나만' 못박기 — OpenRouter 등에서 잡담·펜스·빈 응답 방지.
  // response_format 을 거부(400)하는 모델은 그 항목만 빼고 한 번 더(프롬프트 강제 폴백).
  const 시스템 = 지시 + '\n\n[출력 형식] 반드시 JSON 하나만. 코드펜스·설명·머리말 없이 { 로 시작해 } 로 끝낸다.';
  const 몸 = jm => JSON.stringify(Object.assign({
    model: c.모델 || '', max_tokens: 최대토큰,
    messages: [{ role: 'system', content: 시스템 }, { role: 'user', content: 사용자글 }],
  }, jm ? { response_format: { type: 'json_object' } } : {}));
  let r = await fetch(base + '/chat/completions', { method: 'POST', headers: 헤더, body: 몸(true) });
  if (!r.ok) {                        // response_format 미지원이면(상태코드 무관) 빼고 한 번 더
    const t = await r.text();
    if (/response_format|json[_\s-]?object|schema|not supported|unsupported/i.test(t))
      r = await fetch(base + '/chat/completions', { method: 'POST', headers: 헤더, body: 몸(false) });
    else throw new Error('모델 호출 실패 (' + r.status + ') — ' + t.slice(0, 200));
  }
  if (!r.ok) throw new Error('모델 호출 실패 (' + r.status + ') — ' + (await r.text()).slice(0, 200));
  const j = await r.json();
  const msg = (((j.choices || [])[0] || {}).message || {});
  return msg.content || msg.reasoning_content || msg.reasoning || '';
}
// 선택 개체 주변 맥락 — 절 제목 + 형제 항목 몇 개(모델이 톤·범위를 맞추도록)
// 개체의 '제 글자'만 뽑는다 — .no(번호)·캡션·각주를 뺀 깨끗한 텍스트(모델 입력 오염 방지).
function aiText(el) {
  const c = el.cloneNode(true);
  c.querySelectorAll('.no, .cap, .fn').forEach(x => x.remove());
  return (c.textContent || '').trim();
}
// AI 편집이 글자를 갈아끼울 정확한 잎 — 개체 구조(안쪽 data-path span·.tx·.no)를 보존한다.
// planLeaf 는 data-arr 원소만 .tx 로 내려가, 장·절·별첨·요약항목 같은 컨테이너에선 el 을
// 그대로 돌려준다. 거기에 setText 하면 안쪽 data-path span 이 통째로 지워져 정본 반영이
// 유실되거나(스칼라 경로) 배열 원소가 prune 으로 삭제된다(적대검토 HIGH). 그래서 여기서
// **글자를 담는 실제 잎**을 찾아 그것만 바꾼다.
function aiLeaf(el) {
  return el.querySelector(':scope > .tx')             // 장·절 제목
      || el.querySelector(':scope > [data-path]')      // 별첨·요약항목 등 안쪽 글자 span
      || el;                                           // 항목 등 — el 자신이 잎
}
function aiSetText(el, v) {
  if (el.classList && el.classList.contains('fr-fig')) return;   // 방어 — 도식은 텍스트로 덮으면 SVG가 지워진다(도식은 aiRedrawFig)
  const leaf = aiLeaf(el);
  if (leaf !== el) { setText(leaf, v); }
  else {                                               // el 자신이 잎 — .no 번호는 살리고 글자만 교체
    const no = el.querySelector(':scope > .no');
    el.textContent = ''; if (no) el.appendChild(no);
    el.appendChild(document.createTextNode(v));
  }
  if (el.dataset && (el.dataset.ent === '장' || el.dataset.ent === '절')) el.dataset.title = v;
}
function AI맥락(el) {
  const parts = [];
  const sec = el.closest('[data-ent="절"]');
  if (sec) { const t = (sec.dataset.title || (sec.querySelector('.tx,.h-l1') || {}).textContent || '').trim();
    if (t) parts.push('절 제목: ' + t); }
  const sibs = [...(el.parentElement ? el.parentElement.children : [])]
    .filter(x => x !== el && x.dataset && x.dataset.ent === el.dataset.ent)
    .slice(0, 4).map(x => aiText(x)).filter(Boolean);
  if (sibs.length) parts.push('이웃 항목:\n- ' + sibs.join('\n- '));
  return parts.join('\n');
}
function AI작업표시(on) { document.querySelectorAll('.panel button').forEach(b => b.disabled = !!on); }
// 선택 내용을 사용자 요청대로 LLM 이 다시 쓴다(웹앱 전용).
function aiRewrite(el, info) {
  const 지금 = aiText(el);
  줄고치기('AI에게 어떻게 고쳐 달라 할까요? (예: 더 구체적으로 / 두 개로 나눠 / 근거 수치 추가)', '', async instr => {
    if (!instr) return;
    AI작업표시(true); toast('AI가 고치는 중…');
    try {
      const 지시 = [
        '너는 한국어 공공보고서 편집자다. 아래 "현재 문장"을 사용자 요청대로 고쳐라.',
        '개조식 명사형(공공보고서 문체)을 지키고, 앞머리 번호·마커(○·-·※·□·Ⅰ.)는 붙이지 마라 — 시스템이 자동으로 붙인다.',
        '없는 사실·수치를 지어내지 마라. 결과는 JSON 하나로만: {"text":"고친 문장"}',
      ].join('\n');
      const 맥락 = AI맥락(el);
      const 사용자글 = '현재 문장:\n' + 지금 + '\n\n요청:\n' + instr + (맥락 ? '\n\n(참고 맥락)\n' + 맥락 : '');
      const out = AIJSON추출(await AI호출(지시, 사용자글, 1500));
      const 새글 = String(out.text || out.값 || '').trim();
      if (!새글) throw new Error('빈 응답');
      aiSetText(el, 새글);
      state.ops.push({ action: 'AI 다시쓰기', to: 새글.slice(0, 24) });
      repaginate(); save(); select(el);
      toast('AI가 고쳤습니다');
    } catch (e) { toast('AI 편집 실패 — ' + (e.message || e)); }
    finally { AI작업표시(false); }
  });
}
// 표 전용 AI — 셀 구조라 aiRewrite(글자 통짜)면 표가 뭉개진다. header/rows 로 주고받아 표를 다시 그린다.
async function aiTable(el, info) {
  const t = (typeof tableOf === 'function') ? tableOf(el) : null;
  if (!t || !Array.isArray(t.header)) { toast('표를 읽지 못했습니다'); return; }
  줄고치기('표를 AI에게 어떻게 고쳐 달라 할까요? (예: 단위 통일 / 요약 행 추가 / 값 정리)', '', async instr => {
    if (!instr) return;
    AI작업표시(true); toast('AI가 표를 고치는 중…');
    try {
      const 지시 = [
        '너는 한국어 공공보고서의 표 편집자다. 아래 표(JSON)를 사용자 요청대로 고쳐라.',
        '결과는 JSON 하나로만: {"header":["…"],"rows":[["…", …], …]} — header 길이와 각 row 길이가 같아야 한다.',
        '없는 수치를 지어내지 마라. 열/행 구조는 요청이 없으면 그대로 둔다.',
      ].join('\n');
      const 사용자글 = '표:\n' + JSON.stringify({ header: t.header, rows: t.rows }) + '\n\n요청:\n' + instr;
      const out = AIJSON추출(await AI호출(지시, 사용자글, 2200));
      if (!Array.isArray(out.header) || !Array.isArray(out.rows)) throw new Error('형식이 아닙니다');
      const tb = el.querySelector('table'); if (!tb) throw new Error('표 없음');
      let h = '<tr>' + out.header.map(x => `<th>${esc(x)}</th>`).join('') + '</tr>';
      out.rows.forEach(r => { h += '<tr>' + (Array.isArray(r) ? r : [r]).map(c => `<td>${esc(c)}</td>`).join('') + '</tr>'; });
      tb.innerHTML = h;
      state.ops.push({ action: 'AI 표 편집' });
      repaginate(); save(); select(el);
      toast('표를 고쳤습니다');
    } catch (e) { toast('표 AI 편집 실패 — ' + (e.message || e)); }
    finally { AI작업표시(false); }
  });
}
// 도식으로 만들 수 있는 텍스트 개체 — **배열 원소만**(항목·박스). 절·장은 제목이 스칼라 키라
// el.remove() 해도 정본에 제목이 남아 재조립 때 되살아난다(적대검토 MED) → 제외한다.
function canFig(el) {
  return ['항목', '박스'].includes(el.dataset.ent) && !!parentArrayOf(el, '도식');
}
// 선택 텍스트가 담은 관계를 LLM 이 도식 스펙으로 바꾸고, 그 자리에 도식을 넣는다(웹앱 전용).
async function aiToFig(el, info) {
  const 지금 = aiText(el);
  if (!지금) { toast('도식으로 만들 내용이 없습니다'); return; }
  AI작업표시(true); toast('AI가 도식을 만드는 중…');
  try {
    const 지시 = [
      '너는 도식 설계자다. 아래 문장이 담은 관계를 SVG 도식 스펙(JSON) 하나로 바꿔라.',
      '유형(type)과 필드:',
      '· process(절차 흐름): {"type":"process","캡션":"…","단계":[{"라벨":"짧게","주체":"","전이":"다음"}, …]}',
      '· cycle(순환): {"type":"cycle","캡션":"…","단계":["단계1","단계2", …]}',
      '· converge(여러 입력→처리→결과): {"type":"converge","캡션":"…","요건":["입력1","입력2","입력3"],"시행":"처리","결과":"결과"}',
      '· strategy(전략 체계도) · relation(관계도) · bar/line/donut(간단 차트) 도 가능.',
      '가장 잘 맞는 유형 하나만 골라라. 상자 라벨은 6~14자로 짧게. 없는 내용 지어내지 마라. JSON 하나만, 다른 말 없이.',
    ].join('\n');
    const spec = AIJSON추출(await AI호출(지시, '문장:\n' + 지금, 1200));
    if (!spec || !spec.type) throw new Error('유형(type) 없는 스펙');
    if (window.SVGFIG && /알 수 없는 도식/.test(window.SVGFIG.render(spec)))
      throw new Error('그릴 수 없는 유형: ' + spec.type);
    const d = document.createElement('div');
    d.className = 'blk fr-fig'; d.dataset.ent = '도식';
    d.dataset.new = '1'; d.dataset.parent = parentArrayOf(el, '도식') || '';
    if (el.dataset.group) d.dataset.group = el.dataset.group;
    setFigSpec(d, spec);
    el.after(d);
    if (window.SVGFIG) window.SVGFIG.mount(d);
    // '[도식] …' 자리표시 텍스트면 도식이 대신하니 지운다. 보통 텍스트면 남길지 물어본다.
    const 자리표시 = /^\s*[\[【]?\s*(도식|그림|다이어그램|차트|개념도)\s*[\]】]?\s*[:：]/.test(지금);
    if (자리표시 || confirm('원래 텍스트도 지울까요? (확인=지움 · 취소=텍스트와 도식 둘 다 남김)')) el.remove();
    state.ops.push({ action: '도식으로 변환', to: spec.type });
    repaginate(); select(d); save();
    toast('도식으로 바꿨습니다');
  } catch (e) { toast('도식 변환 실패 — ' + (e.message || e)); }
  finally { AI작업표시(false); }
}

// 도식 유형별 스펙 카탈로그 — svgfig.js 의 R.<type> 이 실제로 읽는 필드(정본). aiRedrawFig 프롬프트용.
const FIG_SPEC_CATALOG = [
  '· process(절차 흐름): {"type":"process","캡션":"…","단계":[{"라벨":"짧게","주체":"","전이":"다음"}, …]}  (단계는 문자열도 가능)',
  '· cycle(순환): {"type":"cycle","캡션":"…","단계":["단계1","단계2","단계3"]}',
  '· converge(여러 입력→처리→결과): {"type":"converge","캡션":"…","요건":["입력1","입력2","입력3"],"시행":"가운데 처리","결과":"오른쪽 결과"}',
  '· strategy(전략 체계도): {"type":"strategy","목표":"상단 배너","전략":[{"제목":"기둥 제목","과제":["과제1","과제2"]}, …]}  (과제 값에 ▪ 넣지 마라 — 렌더러가 붙인다)',
  '· relation(구조도/관계도): {"type":"relation","노드":[{"id":"a","라벨":"표시글","강조":false}, …],"연결":[{"from":"a","to":"b","라벨":"관계","쌍방향":false}, …],"열":3}  (연결의 from/to 는 노드 id 를 가리킨다)',
  '· bar(막대): {"type":"bar","시점":["Q1","Q2"],"계열":[{"이름":"A","값":[100,120]}],"단위":"억원","쌓기":false}',
  '· line(꺾은선): {"type":"line","시점":["1월","2월"],"계열":[{"이름":"A","값":[10,20]}],"단위":"건"}',
  '· hbar(가로막대·항목명이 길 때): {"type":"hbar","시점":["항목1","항목2"],"계열":[{"이름":"A","값":[12,8]}],"단위":"%"}',
  '· donut(도넛): {"type":"donut","항목":[["항목명",30],["항목명2",70]],"가운데":"중앙 글자"}',
  '· stack(스택막대): {"type":"stack","세트":[{"이름":"바 라벨","항목":[["부문A",40],["부문B",60]],"강조":"부문A"}, …]}',
].join('\n');
// 도식 전용 AI — aiRewrite(글자 통짜)는 SVG를 지운다(aiSetText 가 el.textContent 를 비운다). 도식은
// 현재 스펙+맥락을 주고 완전한 유효 스펙(빈 필드까지 채움)을 받아 검증 후 다시 그린다. data-fig 만
// 갱신하므로 직렬화(syncFigSpec) 왕복이 보존된다. 사장님 사례: 수렴형 빈 상자 → 구조도 재작도.
async function aiRedrawFig(el, info) {
  const sp = figSpec(el);
  const 유형표 = info.spec['유형'] || {};
  const 유형목록 = Object.entries(유형표).map(([k, v]) => k + '(' + v + ')').join(', ');
  줄고치기('AI에게 어떻게 다시 그려 달라 할까요? (예: 구조도로 바꿔 관계를 그려 / 빈 상자 채워 / 단계 3개로 / 막대그래프로)', '', async instr => {
    if (!instr) return;
    AI작업표시(true); toast('AI가 도식을 다시 그리는 중…');
    try {
      const 지시 = [
        '너는 도식 설계자다. 아래 "현재 도식 스펙(JSON)"을 사용자 요청대로 다시 설계해 완전한 유효 스펙 하나로 돌려줘라.',
        '허용 유형(type)은 다음뿐이다: ' + 유형목록 + '. 이 중 하나만 써라.',
        '유형별 필드(이름·모양을 정확히 지켜라):',
        FIG_SPEC_CATALOG,
        '규칙: (1) 유형 변경 요청이면 목표 유형의 필드를 처음부터 채운다. (2) 빈 칸(converge 의 시행/결과, 라벨 없는 상자)은 맥락으로 자연스럽게 채운다 — 빈 채로 두지 마라. (3) 캡션·함의는 요청이 없으면 유지. (4) 상자 라벨은 6~14자로 짧게. 없는 사실·수치 지어내지 마라. (5) JSON 하나만, 코드펜스·설명 없이.',
      ].join('\n');
      const 맥락 = AI맥락(el);
      const 사용자글 = '현재 도식 스펙:\n' + JSON.stringify(sp) + '\n\n요청:\n' + instr + (맥락 ? '\n\n(참고 맥락)\n' + 맥락 : '');
      const spec = AIJSON추출(await AI호출(지시, 사용자글, 1800));
      if (!spec || !spec.type || !유형표[spec.type]) throw new Error('허용되지 않은 유형: ' + (spec && spec.type));
      if (window.SVGFIG && /알 수 없는 도식/.test(window.SVGFIG.render(spec))) throw new Error('그릴 수 없는 스펙: ' + spec.type);
      if (sp['캡션'] && !spec['캡션']) spec['캡션'] = sp['캡션'];    // 요청이 안 바꿨으면 캡션·함의 보존
      if (sp['함의'] && !spec['함의']) spec['함의'] = sp['함의'];
      setFigSpec(el, spec);                                          // data-fig 갱신 → 왕복 유지
      if (window.SVGFIG) window.SVGFIG.mount(el);                    // 캡션·SVG·함의 다시 그림
      state.ops.push({ action: 'AI 도식 재작도', to: (유형표[spec.type] || spec.type) });
      repaginate(); save(); select(el);
      toast('도식을 다시 그렸습니다');
    } catch (e) { toast('도식 재작도 실패 — ' + (e.message || e)); }
    finally { AI작업표시(false); }
  });
}

// ── 패널 ──
const panel = document.createElement('div'); panel.className = 'panel'; document.body.appendChild(panel);
function btn(t, f, c) { const b = document.createElement('button'); b.textContent = t; b.onclick = f;
  if (c) b.className = c; return b; }
// ── 결재란 칸(열) 편집 — 결재칸은 직함 한 칸(표지필드)이라 'AI 다시쓰기'로 늘리면 한 칸에 뭉친다.
//    fr-approve 표는 라벨행 + 서명행 2줄(assemble_full ~331). 두 행의 <td>를 짝으로 넣고 뺀다.
//    새 라벨셀엔 data-path='표지.결재.N' 만 붙이면 serialize ①/setPath 가 배열을 그 길이로 왕복한다.
function _approveRows(el) {
  const 라벨행 = el.closest('tr');
  return { 라벨행, 서명행: 라벨행 ? 라벨행.nextElementSibling : null };
}
function _renumberApprove(라벨행) {           // 삭제 후 인덱스 0..n-1 연속화
  [...라벨행.querySelectorAll('[data-frf^="결재칸"]')].forEach((td, i) => {
    td.dataset.frf = '결재칸' + (i + 1); td.dataset.path = '표지.결재.' + i;
  });
}
function addApproveCol(el) {
  const { 라벨행, 서명행 } = _approveRows(el); if (!라벨행) return;
  const n = 라벨행.querySelectorAll('[data-frf^="결재칸"]').length;
  if (n >= 6) { toast('결재칸은 최대 6칸입니다'); return; }
  const td = document.createElement('td');
  td.dataset.ent = '표지필드'; td.dataset.frf = '결재칸' + (n + 1);
  td.dataset.path = '표지.결재.' + n;          // ★ data-path 만(data-new 금지 — serialize ①이 집어감)
  td.textContent = '직함';
  라벨행.appendChild(td);                        // 라벨셀 맨 뒤(가장 오른쪽 = 최종결재)
  if (서명행) { const sc = document.createElement('td'); sc.className = 'sign'; 서명행.appendChild(sc); }
  state.ops.push({ action: '결재칸 추가' });
  repaginate(); save(); select(td); editText(td);   // 바로 직함 입력
}
function delApproveCol(el) {
  const { 라벨행, 서명행 } = _approveRows(el); if (!라벨행) return;
  if (라벨행.querySelectorAll('[data-frf^="결재칸"]').length <= 1) { toast('결재칸은 최소 1칸입니다'); return; }
  const idx = [...라벨행.cells].indexOf(el);
  el.remove();
  if (서명행 && 서명행.cells[idx]) 서명행.cells[idx].remove();   // 짝 서명셀도
  _renumberApprove(라벨행);
  state.ops.push({ action: '결재칸 삭제' });
  select(null); repaginate(); save();
}
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
    panel.insertAdjacentHTML('beforeend', '<div class="hint">글자를 고치면 바로 다시 그립니다 — 빈 칸(예: 수렴형 가운데 상자)도 채울 수 있습니다.</div>');
    const sp = figSpec(el);
    도식필드(sp).forEach(fld => {
      A('✏ ' + fld.라벨 + ' — ' + (fld.값.slice(0, 12) || '(비어 있음)'), () => {
        줄고치기(fld.라벨, fld.값, v => {
          fld.set(v); setFigSpec(el, sp);
          if (window.SVGFIG) window.SVGFIG.mount(el);
          state.ops.push({ action: '도식 글자', to: fld.라벨 });
          repaginate(); select(el); save();
        });
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
    // 빈 쪽 지우기 — 조판기(paginate)는 자식 0개인 쪽은 이미 버린다(assemble_full ~530).
    // 그래도 눈에 빈 쪽이 남는 건 그 쪽에 '보이지 않는 빈 블록'(빈 문단·실패한 도식 껍데기)이
    // 있어서다. 그 블록을 지우고 쪽까지 없앤 뒤 다시 조판하면 접힌다. 바디쪽에만(표지·목차·요약 제외).
    // 예전엔 blks.length>0 을 요구해 0블록 빈 쪽엔 버튼이 안 떴다(사장님이 지운 참고자료 뒤 빈 쪽).
    const inner = el.querySelector('.fr-content');
    const blks = inner ? [...inner.querySelectorAll('.blk')] : [];
    const 살아있나 = b => {                       // 실제로 눈에 보이는 내용이 있나(빈 껍데기는 걸러낸다)
      if ((b.textContent || '').trim()) return true;
      const t = b.querySelector('table'); if (t && t.querySelector('td,th')) return true;
      if (b.querySelector('img')) return true;
      const s = b.querySelector('svg'); if (s && s.children.length) return true;
      return false;
    };
    const 실질 = blks.filter(살아있나);
    if (inner && el.classList.contains('fr-bodypage') && 실질.length === 0) {
      A('🗑 이 빈 쪽 지우기', () => {
        blks.forEach(b => b.remove());
        el.remove();                               // 0블록 쪽도 확실히 없앤다 — 조판기가 흐름에서 다시 세운다
        state.ops.push({ action: '빈 쪽 삭제', to: idx + '쪽' });
        select(null); repaginate(); save();
        toast('빈 쪽을 지웠습니다');
      }, 'danger');
    } else if (el.classList.contains('fr-bodypage') && 실질.length) {
      panel.insertAdjacentHTML('beforeend',
        '<div class="hint">이 쪽에는 내용이 있어 통째로 지우지 않습니다 — 내용을 먼저 지우면 빈 쪽은 자동으로 사라집니다.</div>');
    }
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
  if (has('align')) {                                    // 제목·표 정렬(가운데/좌/우) — data-정렬 로 왕복
    panel.insertAdjacentHTML('beforeend', '<div class="hint">정렬 — 위치</div>');
    const cur = el.dataset.정렬 || '';
    const r = document.createElement('div'); r.className = 'row';
    [['좌측', 'left', '◁ 좌'], ['가운데', 'center', '가운데'], ['우측', 'right', '우 ▷']].forEach(([val, css, lbl]) => {
      r.appendChild(btn(lbl, () => {
        el.style.textAlign = css; el.dataset.정렬 = val;
        state.ops.push({ action: '정렬', to: (info.spec['라벨'] || info.type) + ' ' + val });
        save(); repaginate(); select(el);
      }, cur === val ? 'sel' : ''));
    });
    panel.appendChild(r);
  }
  if (has('tablegap')) {                                 // 표 위아래 간격(좁게/보통/넓게)
    panel.insertAdjacentHTML('beforeend', '<div class="hint">표 위아래 간격</div>');
    const cur = el.dataset.간격 || '보통';
    const r = document.createElement('div'); r.className = 'row';
    [['좁게', '0.4mm'], ['보통', ''], ['넓게', '5mm']].forEach(([val, mm]) => {
      r.appendChild(btn(val, () => {
        el.style.marginTop = mm; el.style.marginBottom = mm; el.dataset.간격 = val;
        state.ops.push({ action: '표 간격', to: val });
        save(); repaginate(); select(el);
      }, cur === val ? 'sel' : ''));
    });
    panel.appendChild(r);
  }
  if (has('pagebreak')) {                                // 장을 새 쪽/앞 쪽 이어서 시작(#8)
    const 새쪽 = el.dataset.새페이지 !== 'false';
    A(새쪽 ? '↳ 이 장을 앞 쪽에 이어서' : '↥ 이 장을 새 쪽에서 시작', () => {
      el.dataset.새페이지 = 새쪽 ? 'false' : 'true';
      state.ops.push({ action: '장 시작', to: 새쪽 ? '이어서' : '새 쪽' });
      save(); repaginate(); select(el);
    });
  }
  // 위/아래 간격(빈줄) — **세로 margin 이 먹는 블록 개체만**. 표·쪽·간지 등 페이지형과, 표셀(td)·
  // 인라인 span 표지필드는 세로 margin 이 CSS 상 무효라 뺀다(적대검토 MED — 죽은 버튼 방지).
  // gpKey 는 블록 자체 경로 OR **직접자식** span 경로만 — 깊은 후손을 잡으면 조립기 :has(>) 가
  // 못 맞춰 산출에서 조용히 사라진다(press 담당표·쪽 클릭 오검출). 그래서 깊은 querySelector 폴백 제거.
  // 표·쪽·간지·되돌림은 개체 종류로 뺀다. 표지필드는 종류로 안 뺀다 — 제목·날짜·기관명(div, 블록)은
  // 간격이 유효하고, 결재칸·문서번호(td, table-cell)·부제(inline span)는 아래 display 판정이 거른다.
  const _간격못하는개체 = ['표', '쪽', '간지', '되돌림'];
  if (el.dataset.ent && !_간격못하는개체.includes(el.dataset.ent)) {
    const _disp = getComputedStyle(el).display;
    const _세로margin가능 = /^(block|flex|grid|list-item|flow-root|table|inline-block)$/.test(_disp);
    const 직접span = el.dataset.path ? null
      : (el.querySelector(':scope > .tx[data-path]') || el.querySelector(':scope > [data-path]'));
    const gpKey = el.dataset.path || (직접span && 직접span.dataset.path) || '';
    if (gpKey && _세로margin가능) {
      const isSpan = !el.dataset.path;
      const 값맵 = { '없음': '', '좁게': '2mm', '보통': '4mm', '넓게': '8mm' };
      state.간격조정 = state.간격조정 || {};
      const 현재 = state.간격조정[gpKey] || {};
      ['위', '아래'].forEach(side => {
        panel.insertAdjacentHTML('beforeend', `<div class="hint">${side} 간격(빈줄)</div>`);
        const cssKey = side === '위' ? 'marginTop' : 'marginBottom';
        const r = document.createElement('div'); r.className = 'row';
        Object.entries(값맵).forEach(([라벨, mm]) => {
          r.appendChild(btn(라벨, () => {
            el.style[cssKey] = mm;                       // 블록에 직접(세로 margin 유효)
            const m = state.간격조정[gpKey] = state.간격조정[gpKey] || {};
            if (mm) m[side] = mm; else delete m[side];
            if (isSpan) m.span = true; else delete m.span;
            if (!m['위'] && !m['아래']) delete state.간격조정[gpKey];
            state.ops.push({ action: side + ' 간격', to: 라벨 }); save(); repaginate(); select(el);
          }, (현재[side] || '') === mm ? 'sel' : ''));
        });
        panel.appendChild(r);
      });
    }
  }
  // 개별 블릿 — 이 항목만 마커를 바꾸거나 지운다(문서 전체 위계와 별개). fullreport 항목/세부만.
  //  data-mk 로 왕복(serialize ④ → 모델 블릿 → assemble data-mk → fullreport.css). 기본 마커는
  //  위계에 따라 달라지므로(도형식 ○/-/※), 여기선 명시 마커나 '없음'만 얹고 '기본'은 키 삭제.
  if (document.documentElement.dataset.genre === 'fullreport' && el.classList.contains('blk')
      && (el.classList.contains('i-l2') || el.classList.contains('i-l3') || el.classList.contains('i-l4'))) {
    panel.insertAdjacentHTML('beforeend',
      '<div class="hint">이 항목의 블릿 — 문서 전체 위계와 따로, 이 줄만 바꿉니다</div>');
    const curmk = el.dataset.mk || '';
    const r = document.createElement('div'); r.className = 'row';
    [['○', '○'], ['□', '□'], ['-', '－'], ['※', '※'], ['·', '·'], ['▪', '▪']].forEach(([val, lbl]) => {
      r.appendChild(btn(lbl, () => {
        el.dataset.mk = val; el.style.paddingLeft = '';
        state.ops.push({ action: '블릿 기호', to: val }); save(); repaginate(); select(el);
      }, curmk === val ? 'sel' : ''));
    });
    panel.appendChild(r);
    A(curmk === '없음' ? '● 이 항목 블릿 다시 넣기' : '⊘ 이 항목 블릿 없애기', () => {
      if (el.dataset.mk === '없음') delete el.dataset.mk; else el.dataset.mk = '없음';
      state.ops.push({ action: '블릿 기호', to: el.dataset.mk || '기본' });
      save(); repaginate(); select(el);
    }, curmk === '없음' ? 'sel' : '');
    if (curmk) A('↺ 문서 위계 기본으로 되돌리기', () => {
      delete el.dataset.mk;
      state.ops.push({ action: '블릿 기호', to: '기본' }); save(); repaginate(); select(el);
    });
  }
  // 결재칸(표지필드) — 칸(열) 추가/삭제. 직함 글자 편집은 표지필드 'edit'(직접 수정)이 한다.
  if (el.dataset.ent === '표지필드' && /^결재칸/.test(el.dataset.frf || '')) {
    const 셀수 = (el.closest('tr') || document).querySelectorAll('[data-frf^="결재칸"]').length;
    panel.insertAdjacentHTML('beforeend', '<div class="hint">결재란 칸 — 직함 하나에 한 칸입니다</div>');
    if (셀수 < 6) A('＋ 오른쪽에 칸 추가', () => addApproveCol(el));
    if (셀수 > 1) A('－ 이 칸 삭제', () => delApproveCol(el), 'danger');
  }
  // AI 편집 — 표면에 따라 길이 다르다. 채팅표면(file://, 스킬·MCP)은 노트를 남겨 코딩
  // 에이전트가 반영하고, 웹앱(http)은 내 키로 브라우저가 provider 를 직접 불러 즉시 고친다.
  if (has('ai')) {
    if (채팅표면) {
      A('✍ AI에게 고쳐달라 하기 — ' + info.spec['라벨'], () => addNote(el, info));
    } else if (AI키준비됨()) {
      const 결재셀 = el.dataset.ent === '표지필드' && /^결재칸/.test(el.dataset.frf || '');
      if (el.dataset.ent === '표') {
        A('✎ AI에게 표 고쳐 달라', () => aiTable(el, info));
      } else if (el.dataset.ent === '도식') {
        A('✎ AI에게 다시 그려 달라 — ' + info.spec['라벨'], () => aiRedrawFig(el, info));
      } else if (결재셀) {
        // 결재칸은 산문이 아니라 직함 한 칸 — AI 다시쓰기 부적합(칸 추가/삭제는 위 구조 버튼).
      } else {
        A('✎ AI에게 다시 써 달라 — ' + info.spec['라벨'], () => aiRewrite(el, info));
        if (canFig(el)) A('◆ 이 내용을 도식으로 만들기', () => aiToFig(el, info));
      }
    } else {
      panel.insertAdjacentHTML('beforeend',
        '<div class="hint">✎ AI로 고치려면 메인 화면 오른쪽 위 “API 키”를 먼저 넣으세요 — 내 키로 브라우저가 직접 호출하고 서버로는 보내지 않습니다.</div>');
    }
  }
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
  // 편집 내역은 **왼쪽 히스토리 패널**(#10)이 담당한다. 오른쪽엔 AI(채팅)에게 맡긴 것만 —
  // 그마저도 채팅표면(스킬·MCP)에서만 뜻이 있다(웹앱은 즉시 반영이라 '대기'가 없다).
  const keys = Object.keys(state.notes);
  if (!채팅표면 || !keys.length) return;
  panel.insertAdjacentHTML('beforeend', '<div class="notes"><b>AI에게 맡긴 것</b><ul>' +
    keys.map(k => `<li>📌 ${esc(k)}: ${esc(state.notes[k])}</li>`).join('') +
    '</ul><div class="hint">채팅에 "고쳐놨어"라고 하시면 반영해 다시 만듭니다</div></div>');
}

// ── 직렬화: 원본 모델을 복제해 '경로(data-path)'로 패치 ──
// DOM 순서 워크 + 커서 방식은 절 제목을 지우면 항목이 유실되고, jachigan 잔해까지
// 되살리는 구조적 결함이 있었다(적대 검증 확정). 원본을 신뢰하고 델타만 얹는다.
const SRCDOC = JSON.parse(document.getElementById('fr-doc').textContent);
// 위/아래 간격(빈줄)은 정본에서 이어받아 state 에 싣는다 — 그래야 패널이 현재 값을 'sel' 로 비춘다
// (화면 margin 은 조립기가 낸 <style data-gap> 로 이미 적용돼 있다).
state.간격조정 = (SRCDOC && SRCDOC['간격조정'] && typeof SRCDOC['간격조정'] === 'object')
  ? JSON.parse(JSON.stringify(SRCDOC['간격조정'])) : {};

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
// 스펙에서 **편집 가능한 모든 필드**를 열거한다(빈 값도 포함) — figLabels(SVG 텍스트)는 빈 박스를
// 빠뜨려 converge 의 빈 '시행' 같은 칸을 못 고쳤다(사장님 지적). {라벨, 값, set(v)} 로 돌려준다.
function 도식필드(sp) {
  const F = [], add = (라벨, 값, set) => F.push({ 라벨, 값: (값 == null ? '' : String(값)), set });
  const lab = st => (st && typeof st === 'object') ? (st['라벨'] || '') : (st || '');
  const t = sp.type;
  if (t === 'process' || t === 'cycle') {
    (sp['단계'] || []).forEach((st, i) => {
      add('단계 ' + (i + 1), lab(st), v => { if (typeof sp['단계'][i] === 'object') sp['단계'][i]['라벨'] = v; else sp['단계'][i] = v; });
      if (t === 'process' && st && typeof st === 'object') {
        add('단계 ' + (i + 1) + ' 주체', st['주체'], v => sp['단계'][i]['주체'] = v);
        if (i < (sp['단계'].length - 1)) add((i + 1) + '→' + (i + 2) + ' 화살표 글자', st['전이'], v => sp['단계'][i]['전이'] = v);
      }
    });
  } else if (t === 'converge') {
    (sp['요건'] || []).forEach((r, i) => add('입력 ' + (i + 1), r, v => sp['요건'][i] = v));
    add('처리(가운데 상자)', sp['시행'], v => sp['시행'] = v);
    add('결과', sp['결과'], v => sp['결과'] = v);
  } else if (t === 'strategy') {
    add('목표', sp['목표'], v => sp['목표'] = v);
    (sp['전략'] || []).forEach((c, i) => {
      add('전략 ' + (i + 1), c && c['제목'], v => sp['전략'][i]['제목'] = v);
      ((c && c['과제']) || []).forEach((tk, j) => add('전략 ' + (i + 1) + ' 과제 ' + (j + 1), tk, v => sp['전략'][i]['과제'][j] = v.replace(/^▪\s*/, '')));
    });
  } else if (t === 'relation') {
    (sp['노드'] || []).forEach((n, i) => add('노드 ' + (i + 1), lab(n), v => { if (typeof sp['노드'][i] === 'object') sp['노드'][i]['라벨'] = v; else sp['노드'][i] = v; }));
  } else {
    const arr = 도식배열(sp);
    if (arr) arr.forEach((x, i) => add('항목 ' + (i + 1), lab(x), v => { if (typeof arr[i] === 'object') arr[i]['라벨'] = v; else arr[i] = v; }));
  }
  return F;
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
  // ①-e 정렬 — 개체(장·절·표)의 정렬을 doc 객체 필드로 되쓴다(data-정렬 이 있는 것만).
  //     경로: 표=data-path 그대로 · 절=data-path 에서 '.제목' 떼기 · 장=.tx 자식의 data-path 에서 떼기.
  document.querySelectorAll('[data-정렬]').forEach(el => {
    const v = el.dataset.정렬; if (!v) return;
    const ent = el.dataset.ent;
    let objPath = null;
    if (ent === '표') objPath = el.dataset.path || null;
    else if (ent === '절') objPath = (el.dataset.path || '').replace(/\.(제목|heading|title)$/, '') || null;
    else if (ent === '장') { const tx = el.querySelector('.tx[data-path]'); objPath = tx ? (tx.dataset.path || '').replace(/\.제목$/, '') : null; }
    if (!objPath) return;
    const o = getPath(doc, objPath);
    if (o && typeof o === 'object') o['정렬'] = v;
  });
  // ①-f 장 새쪽 시작 — data-새페이지 로 왕복(기본=새 쪽 · false 면 앞 쪽에 이어서).
  document.querySelectorAll('.fr-chapter[data-새페이지]').forEach(el => {
    const tx = el.querySelector('.tx[data-path]');
    const base = tx ? (tx.dataset.path || '').replace(/\.제목$/, '') : null;
    if (!base) return;
    const o = getPath(doc, base);
    if (o && typeof o === 'object') { if (el.dataset.새페이지 === 'false') o['새페이지'] = false; else delete o['새페이지']; }
  });
  // ①-g 표 간격 — data-간격 로 왕복(보통=기본 → 필드 삭제).
  document.querySelectorAll('[data-ent="표"][data-간격]').forEach(el => {
    if (!el.dataset.path) return;
    const o = getPath(doc, el.dataset.path);
    if (o && typeof o === 'object') { const g = el.dataset.간격; if (g === '좁게' || g === '넓게') o['간격'] = g; else delete o['간격']; }
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
  // ④ 항목 레벨 변경 + 개별 블릿(data-mk) 반영 — 같은 base 를 재활용해 함께 되쓴다.
  //    블릿은 기본이면 키를 지운다(왕복 불변식 — 안 고친 항목에 키가 생기면 안 된다).
  document.querySelectorAll('.blk[data-path$=".text"]').forEach(el => {
    if (!LVORDER.some(c => el.classList.contains(c))) return;
    const lv = el.classList.contains('i-l4') ? 4 : el.classList.contains('i-l3') ? 3 : 2;
    const base = el.dataset.path.replace(/\.text$/, '');
    const it = getPath(doc, base);
    if (it && typeof it === 'object') {
      it.level = lv;
      if (el.dataset.mk) it['블릿'] = el.dataset.mk; else delete it['블릿'];
    }
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
  if (state.위계체계 !== undefined) { if (state.위계체계 && state.위계체계 !== '도형식') doc['위계체계'] = state.위계체계; else delete doc['위계체계']; }
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
  // ⑨ 위/아래 간격(빈줄) — data-path 키 맵. 지워진 개체의 죽은 키는 걸러낸다(적대검토 LOW —
  // 개체 삭제 시 prune 은 정본 트리만 훑지 state.간격조정 은 안 지운다 → 화면에 없는 경로가 남음).
  if (state.간격조정 && typeof state.간격조정 === 'object') {
    const 살아있는 = {};
    Object.entries(state.간격조정).forEach(([k, v]) => {
      let 있나 = false;
      try { 있나 = !!document.querySelector('[data-path="' + String(k).replace(/["\\]/g, '\\$&') + '"]'); }
      catch (e) { 있나 = true; }                          // 셀렉터가 이상하면 보수적으로 남긴다
      if (있나) 살아있는[k] = v;
    });
    state.간격조정 = 살아있는;
    if (Object.keys(살아있는).length) doc['간격조정'] = 살아있는; else delete doc['간격조정'];
  } else delete doc['간격조정'];
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

// ── #10 편집 히스토리 + 한 단계 언두/리두 ──────────────────────────────────
// 편집마다(save 시점) 문서 페이지들을 통째로 스냅샷해 쌓는다. 되돌리기는 이전 스냅샷을
// 되살리고 재조판한다(페이지네이터가 블록에서 쪽을 다시 그리므로 fr-page 통째로 담아도 안전).
// "대기 중 작업" 로그를 대신하는 왼쪽 패널이다(좌:히스토리 · 가운데:문서 · 우:옵션).
let 복원중 = false;
// 판=스냅HTML · 라벨=편집이름 · 아이디=항목별 안정 id(지점 표시가 인덱스 밀림에도 붙어 있게)
// 지점={id:이름} — 옛 '되돌림 지점'을 여기 이름표(📌)로 통합했다(줄 클릭 점프로 되돌아간다).
const 이력 = { 판: [], 라벨: [], 아이디: [], 위치: -1, 지점: {} };
let _다음지점id = 1;
const 이력판 = document.createElement('div'); 이력판.className = 'hist'; document.body.appendChild(이력판);
// 편집 순간에 **동기적으로** 스냅샷을 잡는다 — save/repaginate 디바운스 체인에 얹으면 ~1초 밀린다.
// 구조 편집은 전부 state.ops.push 를 지나고(그 자리에서 DOM 이 이미 바뀌어 있다), 순수 글자
// 편집은 finishEdit 를 지난다. 두 길목에서만 쌓으면 빠짐없이 즉시 잡힌다(이력쌓기 가 중복은 거른다).
// state.ops = state.ops.filter(...) 재할당(2단마커·스타일)이 래핑을 잃지 않게 setter 로 다시 감싼다.
(function () {
  let _arr = state.ops;
  const 감싸기 = a => { const _p = a.push.bind(a); a.push = function () { const r = _p.apply(null, arguments); 이력쌓기(); return r; }; return a; };
  감싸기(_arr);
  Object.defineProperty(state, 'ops', { get: () => _arr, set: v => { _arr = 감싸기(v); }, configurable: true });
})();
// 쪽 컨테이너는 **장르마다 클래스가 다르다** — 하나만 보면 그 장르만 언두가 산다(적대검토 HIGH).
// 새 장르가 생기면 여기에 그 쪽 클래스를 더한다.
const _쪽셀렉터 = '.fr-page, .sheet, .gm-sheet, .pr-sheet, .sl-page, .rg-sheet';
function _페이지들() { return [...document.querySelectorAll(_쪽셀렉터)]; }
// 스냅은 쪽 DOM뿐 아니라 <html> 속성·state 설정(글꼴·강조색·테마·효과·화면·스타일·끝표시)도 담는다 —
// 이들은 .fr-page 밖(html/state)이라 예전 스냅이 못 봤고, 되돌리기가 이 변화를 놓쳐 혼합본을 저장했다(적대검토).
function _설정스냅() {
  const h = document.documentElement;
  return { style: h.getAttribute('style') || '', fonts: h.dataset.fonts || '',
    mk2: h.dataset.mk2 || '', 테마attr: h.getAttribute('data-테마') || '', hier: h.dataset.hier || '',
    st: { 포인트색: state.포인트색, 글꼴: state.글꼴, 테마: state.테마, 효과: state.효과,
          화면: state.화면, pendingStyle: state.pendingStyle, 끝표시: state.끝표시, 위계체계: state.위계체계,
          간격조정: state.간격조정 } };   // #3 위/아래 간격도 스냅(_스냅 의 JSON 직렬화가 깊은 복사)
}
function _설정복원(cfg) {
  if (!cfg) return;
  const h = document.documentElement;
  if (cfg.style) h.setAttribute('style', cfg.style); else h.removeAttribute('style');
  if (cfg.fonts) h.dataset.fonts = cfg.fonts; else delete h.dataset.fonts;
  if (cfg.mk2) h.dataset.mk2 = cfg.mk2; else delete h.dataset.mk2;
  if (cfg.테마attr) h.setAttribute('data-테마', cfg.테마attr); else h.removeAttribute('data-테마');
  if (cfg.hier) h.dataset.hier = cfg.hier; else delete h.dataset.hier;
  Object.assign(state, cfg.st || {});                    // serialize 가 읽는 설정도 되돌린다(혼합본 방지)
  if (typeof _위계표시 === 'function') _위계표시();
}
function _스냅() { return JSON.stringify({ 쪽: _페이지들().map(p => p.outerHTML), 설정: _설정스냅() }); }
function _최근편집이름() {
  const o = state.ops[state.ops.length - 1];
  return o ? (esc(o.action) + (o.to ? ' → ' + esc(o.to) : '') + (o.target ? ' ' + esc(o.target) : '')) : '직접 수정';
}
function 이력초기화() {
  이력.판 = [_스냅()]; 이력.라벨 = ['처음 상태']; 이력.아이디 = [_다음지점id++];
  이력.위치 = 0; 이력.지점 = {}; 이력그리기();
}
function _트림() {   // 상한 초과분은 **지점 표시 아닌** 가장 오래된 것부터 버린다(표시는 세션 내 보존)
  const 상한 = 120;
  while (이력.판.length > 상한) {
    let idx = 이력.아이디.findIndex(id => !이력.지점[id]);
    if (idx < 0) idx = 0;                                 // 전부 표시면 어쩔 수 없이 맨 앞
    delete 이력.지점[이력.아이디[idx]];
    이력.판.splice(idx, 1); 이력.라벨.splice(idx, 1); 이력.아이디.splice(idx, 1);
    if (idx <= 이력.위치) 이력.위치--;
  }
}
function 이력쌓기(라벨) {
  if (복원중 || !이력.판.length) return;                 // 초기화 전이면 건너뛴다
  const s = _스냅();
  if (s === 이력.판[이력.위치]) return;                   // 바뀐 게 없으면 안 쌓는다
  for (let k = 이력.위치 + 1; k < 이력.아이디.length; k++) delete 이력.지점[이력.아이디[k]]; // 버릴 redo 꼬리의 표시도 지운다
  이력.판 = 이력.판.slice(0, 이력.위치 + 1);              // redo 꼬리 버림
  이력.라벨 = 이력.라벨.slice(0, 이력.위치 + 1);
  이력.아이디 = 이력.아이디.slice(0, 이력.위치 + 1);
  이력.판.push(s); 이력.라벨.push(라벨 || _최근편집이름()); 이력.아이디.push(_다음지점id++);
  이력.위치 = 이력.판.length - 1;
  _트림();
  이력그리기();
}
// 이 지점(현재 위치)에 이름표를 단다 — 옛 '되돌림 지점'을 히스토리 마크로 통합. 이름을 비우면 표시 해제.
function 지점표시하기() {
  const id = 이력.아이디[이력.위치];
  줄고치기('이 지점에 이름 붙이기 (예: 검토 요청 전) — 비우면 표시 해제', 이력.지점[id] || '', v => {
    if (v && v.trim()) 이력.지점[id] = v.trim(); else delete 이력.지점[id];
    이력그리기();
  });
}
function _이력적용(i) {
  if (i < 0 || i >= 이력.판.length || i === 이력.위치) return;
  clearTimeout(sT);                                       // 대기 중 저장 취소(복원과 안 엉키게)
  이력.위치 = i;
  복원중 = true;
  let 짐; try { 짐 = JSON.parse(이력.판[i]); } catch (e) { 짐 = null; }
  const 페이지들 = _페이지들();
  if (짐 && 페이지들.length) {
    const parent = 페이지들[0].parentNode, 앵커 = 페이지들[페이지들.length - 1].nextSibling;
    const tmp = document.createElement('div'); tmp.innerHTML = (짐.쪽 || []).join('\n');
    페이지들.forEach(p => p.remove());
    [...tmp.children].forEach(p => parent.insertBefore(p, 앵커));
    _설정복원(짐.설정);                                   // <html>·state 설정도 되돌린다
  }
  select(null);
  if (window.SVGFIG) window.SVGFIG.mountAll();            // 도식 다시 그리기
  repaginate();
  복원중 = false;
  try {                                                   // 되돌린 상태를 화면·서버에 반영(이력엔 새로 안 쌓음)
    const snap = serialize();
    snap._저장때 = new Date().toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    localStorage.setItem(KEY, JSON.stringify(snap)); 보내기();
  } catch (e) {}
  이력그리기();
}
function 되돌리기() { if (이력.위치 > 0) { _이력적용(이력.위치 - 1); toast('되돌렸습니다'); } }
function 다시하기() { if (이력.위치 < 이력.판.length - 1) { _이력적용(이력.위치 + 1); toast('다시 했습니다'); } }
function 이력그리기() {
  const 끝 = 이력.판.length - 1;
  const 목록 = 이력.라벨.map((L, i) => {
    const 표 = 이력.지점[이력.아이디[i]];
    const 안 = 표
      ? `<span class="pin">📌 ${esc(표)}</span> <span class="dim">${L}</span><span class="unpin" data-un="${i}" title="표시 해제">✕</span>`
      : L;
    return `<li class="${i === 이력.위치 ? 'cur' : ''} ${i > 이력.위치 ? 'ahead' : ''} ${표 ? 'marked' : ''}" data-i="${i}">${안}</li>`;
  }).reverse().join('');                                  // 최신이 맨 위
  const 현표 = !!이력.지점[이력.아이디[이력.위치]];
  이력판.innerHTML =
    '<h3>편집 히스토리</h3>' +
    '<div class="ud">' +
      `<button id="undo"${이력.위치 <= 0 ? ' disabled' : ''}>↶ 되돌리기</button>` +
      `<button id="redo"${이력.위치 >= 끝 ? ' disabled' : ''}>↷ 다시</button>` +
    '</div>' +
    `<button class="pinbtn" id="pin">📌 ${현표 ? '이 지점 이름 고치기' : '이 지점 표시'}</button>` +
    '<ol class="hlist">' + 목록 + '</ol>' +
    '<div class="hint">한 줄을 누르면 그 시점으로 갑니다 · 📌 표시는 눈에 띄게 남습니다 · ⌘Z / ⌘⇧Z</div>';
  const u = 이력판.querySelector('#undo'), r = 이력판.querySelector('#redo'), p = 이력판.querySelector('#pin');
  if (u) u.onclick = 되돌리기; if (r) r.onclick = 다시하기; if (p) p.onclick = 지점표시하기;
  이력판.querySelectorAll('.hlist li').forEach(li => li.onclick = () => _이력적용(+li.dataset.i));
  이력판.querySelectorAll('.unpin').forEach(x => x.onclick = e => {
    e.stopPropagation(); delete 이력.지점[이력.아이디[+x.dataset.un]]; 이력그리기();
  });
}
function _입력중() {                                     // 입력창/편집영역이면 브라우저 기본 undo 에 맡긴다
  if (state.editing) return true;
  const a = document.activeElement;
  return !!(a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)));
}
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey)) return;
  const k = (e.key || '').toLowerCase();
  if (k === 'z') { if (_입력중()) return; e.preventDefault(); e.shiftKey ? 다시하기() : 되돌리기(); }
  else if (k === 'y') { if (_입력중()) return; e.preventDefault(); 다시하기(); }
});

// 완료 — **나가기 전에 저장을 확실히 밀어낸다(flush)**. 자동저장은 디바운스(400ms·1500ms)라
// 막 고치고 바로 닫으면 마지막 수정이 잘릴 수 있다(사장님 지적) — 그래서 대기 타이머를 취소하고
// 지금 상태를 화면·서버에 확정 저장한 뒤 닫는다. '완료'와 '닫기'를 이 하나로 합쳤다.
async function 완료하기(btn) {
  const 원래 = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '저장 중…'; }
  try {
    clearTimeout(sT); clearTimeout(sT2);                 // 대기 중인 디바운스 취소
    let 대기 = 0;                                        // 앞선 전송이 끝날 때까지 잠깐 기다린다
    while (보내는중 && 대기 < 6000) { await new Promise(r => setTimeout(r, 100)); 대기 += 100; }
    const snap = serialize();
    snap._저장때 = new Date().toLocaleString('ko-KR',
      { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    localStorage.setItem(KEY, JSON.stringify(snap));     // ① 화면 저장은 무조건
    if (snap.doc && !채팅표면) {                          // ② 웹앱이면 서버 정본까지 확정 반영
      const r = await fetch('/save', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(snap) });
      const j = await r.json().catch(() => ({}));
      if (j && j.수정시각) { SRCDOC._수정시각 = j.수정시각; snap.doc._수정시각 = j.수정시각;
                           localStorage.setItem(KEY, JSON.stringify(snap)); }
      if (r.ok === false || (j && j.ok === false)) throw new Error((j && j.로그) || '서버 반영 실패');
    }
  } catch (e) {
    // 화면 저장은 이미 끝났다 — 서버 반영만 실패. 유실 위험을 알리고 닫을지 물어본다.
    if (!confirm('문서 반영에 실패했습니다 — 그래도 닫을까요?\n(화면에는 저장돼 있어 새로고침하면 이어서 고칠 수 있습니다)')) {
      if (btn) { btn.disabled = false; btn.textContent = 원래; }
      return;
    }
  }
  // 닫기 — 스크립트로 연 탭이 아니면 window.close 가 막히니, 못 닫으면 메인으로 돌아간다.
  window.close(); setTimeout(() => location.replace('/workspace/app.html'), 350);
}

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
// ── 위계(문서 전체 블릿/번호 체계) — CSS data-hier 로 즉시 전환, 위계체계 로 정본 왕복 ──
const HIER맵 = { '도형식': '', '번호식': 'B', '5단 번호식': 'S', '블릿 없음': 'N' };
function _위계표시() {
  const cur = document.documentElement.dataset.hier || '';
  document.querySelectorAll('.edit-bar [data-hier-btn]').forEach(b =>
    b.classList.toggle('on', (HIER맵[b.dataset.hierBtn] || '') === cur));
}
document.querySelectorAll('.edit-bar [data-hier-btn]').forEach(b => b.onclick = () => {
  const v = HIER맵[b.dataset.hierBtn] || '';
  if (v) document.documentElement.dataset.hier = v; else delete document.documentElement.dataset.hier;
  state.위계체계 = b.dataset.hierBtn;
  _위계표시();
  state.ops.push({ action: '블릿 체계', to: b.dataset.hierBtn });
  if (typeof repaginate === 'function') repaginate();
});
_위계표시();
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
on('btn-done', () => 완료하기(document.getElementById('btn-done')));   // 저장 flush 후 닫기(완료·닫기 합침)
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
// ── 되돌림 지점은 편집 히스토리(#10)의 이름표(📌)로 통합됐다 — 별도 서버 버전 저장소·패널을
//    걷어냈다. '이 지점 표시'는 이력판(왼쪽)에서 현재 항목에 이름을 달고, 줄 클릭으로 되돌아간다.

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
  // 되살린 상태를 히스토리 **기준(처음 상태)**으로 다시 잡는다 — 안 그러면 되돌리기가 복원 이전으로
  // 넘어가 되살린 편집을 정본에서 지운다(적대검토 HIGH 자료유실). 재조판 뒤 스냅을 잡는다.
  if (typeof 이력초기화 === 'function') setTimeout(이력초기화, 80);
  toast(diff.length ? `고치시던 내용 ${diff.length}군데를 되살렸습니다`
                    : '고치신 글자는 없고, 남기신 요청만 되살렸습니다');
}
if (location.search.indexOf('selfcheck=1') < 0) 이어서하기();

renderPanel();
pendingBar();
if (typeof repaginate === 'function') setTimeout(repaginate, 200);
setTimeout(이력초기화, 320);   // #10 — 첫 조판이 끝난 뒤 히스토리 첫 스냅샷(처음 상태)
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
    if bar_spec.get("위계"):                                # 문서 전체 블릿/번호 체계
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">위계</span>')
        for key, label in bar_spec["위계"]:
            grp.append(f'<button data-hier-btn="{key}">{label}</button>')
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
        '<span class="st">아직 수정 없음</span>'
        '<span style="width:10px"></span>'
        '<button id="btn-done" title="편집을 마치고 닫습니다 — 마지막 수정까지 확실히 저장합니다" '
        'style="background:var(--ai-color-signal);color:var(--ai-color-white);font-weight:700">완료</button>'
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
