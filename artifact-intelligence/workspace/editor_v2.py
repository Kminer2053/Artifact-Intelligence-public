"""판형 v2 슬라이드(부품 트리) 편집 조각 — render_editor_any.gen() 이 v2 문서에만 끼운다.

모델은 부품 트리 JSON 만 쓰고 조립기(build/assemble_slides.build_v2)가 그린다. 편집기도 같은 결을 따른다.
  · 글은 누르면 바로 고친다(단추 없음). 잎(.tx)·런 묶음(data-runs) 글을 data-path 로 되쓴다.
  · 고른 개체 위에 막대 하나 — 주 동작(프로파일 slides-v2 의 ui.bar) + ⋯(ui.more, 삭제는 맨 끝).
    같은 꼴 부품은 칸 순서가 같다: 값형 [값·라벨 고치기 | AI | ⋯] · 목록형 [항목 추가 | AI | ⋯] ·
    차트형 [값 고치기(격자) | 크기(흐림) | AI | ⋯] · 표 [행 추가 | 크기(흐림) | AI | ⋯] ·
    항목 [아래에 추가 | 단계(흐림) | AI | ⋯]. 크기 칸은 옛 편집 화면 막대(editor_bar.py)와 칸 순서를 맞추려
    자리만 지킨다 — 슬라이드는 판(레이아웃)이 크기를 정한다('26-09-29).
  · 차트 값·장 순서·프리셋·밀도처럼 그림이 바뀌는 편집은 저장(apply_edit_any → 재조립) 뒤 다시 연다.
  · 저장 모양은 편집기 공통 serialize() 대신 v2직렬화() 가 만든다 — 원본(SRCDOC)을 복제해 글을 패치하고,
    항목·부품·장을 넣고 빼고 옮긴 배열만 화면 순서대로 다시 짠다(손대지 않은 배열은 원본 그대로).

이 조각은 SCRIPT 의 IIFE 안(자리표시 /*@@V2@@*/)에 들어가 state·select·save·serialize 도우미를
그대로 쓴다. SCRIPT 쪽 걸이(typeof v2… === 'function')는 이 조각이 없으면 아무 일도 안 한다.
색은 토큰(var(--ai-*))만 쓴다.
"""

CHROME_V2 = r"""
<style data-editor>
  /* 판형 v2 — 개체 위 막대(주 동작 + ⋯)와 작은 입력판. 쪽 바깥 고정 층(패널 안 자식)에 둔다. */
  .v2bar { position: fixed; z-index: 103; display: flex; gap: 2px; align-items: center; padding: 3px;
    background: var(--ai-color-ink); border-radius: var(--ai-radius-sm);
    box-shadow: var(--ai-shadow-card); font: 12.5px/1.2 var(--ai-font-sans); }
  .panel .v2bar button { display: inline-flex; width: auto; margin: 0; padding: 5px 9px; text-align: center;
    border: 0; border-radius: 4px; background: transparent; color: var(--ai-color-white);
    font: inherit; white-space: nowrap; cursor: pointer; }
  .panel .v2bar button:hover, .panel .v2bar button:focus-visible { background: var(--ai-color-signal);
    border-color: transparent; outline: none; }
  .panel .v2bar button[disabled] { opacity: .38; cursor: default; background: transparent; }
  .v2menu { position: fixed; z-index: 104; min-width: 170px; padding: 4px; background: var(--ai-color-white);
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm); box-shadow: var(--ai-shadow-card); }
  .panel .v2menu button { margin: 0; border: 0; border-radius: 4px; background: transparent; padding: 7px 9px; }
  .panel .v2menu button:hover { background: var(--ai-color-signal-tint); }
  .panel .v2menu button.danger { color: var(--ai-color-issue); background: transparent;
    border-top: 1px solid var(--ai-color-line); border-radius: 0 0 4px 4px; }
  .v2pop { position: fixed; z-index: 105; top: 58px; left: 50%; transform: translateX(-50%);
    width: min(620px, calc(100vw - 24px)); max-height: calc(100vh - 80px); overflow: auto; box-sizing: border-box;
    padding: 14px 16px; background: var(--ai-color-white); color: var(--ai-color-ink);
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-md); box-shadow: var(--ai-shadow-card);
    font: 13px/1.5 var(--ai-font-sans); }
  .v2pop h4 { margin: 0 0 8px; font-size: 13.5px; }
  .v2pop .v2sub { margin: 0 0 10px; font-size: 12px; color: var(--ai-color-muted); }
  .v2pop label { display: flex; gap: 8px; align-items: center; margin: 5px 0; font-size: 12.5px; }
  .v2pop label > span { width: 110px; flex: none; color: var(--ai-color-muted); }
  .panel .v2pop input { flex: 1; min-width: 0; width: auto; padding: 5px 7px; font: inherit;
    border: 1px solid var(--ai-color-line); border-radius: 4px; box-sizing: border-box; }
  .v2pop table { border-collapse: collapse; width: 100%; }
  .v2pop td, .v2pop th { padding: 2px; }
  .panel .v2pop td input { width: 100%; }
  .v2pop .v2row { display: flex; gap: 6px; justify-content: flex-end; margin-top: 12px; flex-wrap: wrap; }
  .panel .v2pop .v2row button { display: inline-block; width: auto; margin: 0; }
  .panel .v2pop .v2row button.good { background: var(--ai-color-ink); color: var(--ai-color-white); border-color: var(--ai-color-ink); }
  main.deck.v2 [data-v2ph]:empty::before { content: attr(data-v2ph); color: var(--ai-color-muted); }
  main.deck.v2 .tx { cursor: text; }
</style>
"""

SCRIPT_V2 = r"""
// ════ 판형 v2 슬라이드 편집 — workspace/editor_v2.py 가 v2 문서에만 끼운다 ════════════════════
function v2상태() {
  if (!state.v2) state.v2 = { 더러운: new Set(), 새번호: {}, 값: {}, 지운필드: new Set(), 설정: {},
    다시: false, 다시대기: false, 폭풀기: new Set(), 마지막칸: null, 처음호스트: {} };
  return state.v2;
}
const V2부품 = new Set(Object.entries(ENTS).filter(([, s]) => s && s['kind']).map(([k]) => k));
const V2안고름 = new Set(PROFILE['unselectable'] || []);
const V2말 = { slideAdd: '＋ 장 추가', ai: 'AI로 고치기', addItem: '＋ 항목 추가', addBelow: '＋ 아래에 추가',
  level: '단계', slots: '값·라벨 고치기', figdata: '값 고치기', tablerow: '＋ 행 추가',
  figsize: '크기', tablesize: '크기',   // 자리만 지킨다(흐림) — 판형이 크기를 정한다. 옛 편집 화면 막대와 칸 순서를 맞춘다
  note: '발표자 노트', delRow: '행 빼기', del: '삭제' };
const V2단축 = { addBelow: '글 끝 Enter', del: 'Shift+Delete', reorder: 'Alt+↑↓' };
const v2조각 = p => String(p).split('.');
const v2복제 = o => JSON.parse(JSON.stringify(o));
const v2장 = el => el && el.closest && el.closest('section.sl-page[data-slide-idx]');

// ── 자리 — 호스트(장·부품·항목·표 행)가 어느 배열의 몇 번째인가 ──
function v2부품(el) {
  for (let n = el; n && n !== document.body; n = n.parentElement)
    if (n.dataset && n.dataset.path && (V2부품.has(n.dataset.ent) || n.dataset.ent === '세로묶음')) return n;
  return null;
}
function v2잎들(el) {
  const out = [];
  if (el.dataset && el.dataset.path) out.push(el);
  el.querySelectorAll('[data-path]').forEach(x => out.push(x));
  return out;
}
function v2호스트인가(n) {
  if (!n || !n.dataset) return false;
  if (n.matches('section.sl-page[data-slide-idx]')) return true;
  if (n.dataset.path && (V2부품.has(n.dataset.ent) || n.dataset.ent === '세로묶음')) return true;
  if (n.dataset.ent === '항목') return true;
  return n.tagName === 'TR' && !!n.closest('[data-ent="표"] tbody');
}
function v2자리(h) {
  if (h.matches('section.sl-page[data-slide-idx]')) return { arr: '장', idx: +h.dataset.slideIdx };
  if (h.dataset.path && (V2부품.has(h.dataset.ent) || h.dataset.ent === '세로묶음')) {
    const k = h.dataset.path.lastIndexOf('.');
    return { arr: h.dataset.path.slice(0, k), idx: +h.dataset.path.slice(k + 1) };
  }
  const 부 = v2부품(h.parentElement), 장 = v2장(h);
  const 밑 = 부 ? 부.dataset.path : (장 ? '장.' + 장.dataset.slideIdx : null);
  if (!밑) return null;
  const 잎 = v2잎들(h).map(x => x.dataset.path).filter(p => p.startsWith(밑 + '.'));
  if (!잎.length) return null;
  let 앞 = v2조각(잎[0]);
  잎.slice(1).forEach(p => {
    const s = v2조각(p); let k = 0;
    while (k < 앞.length && k < s.length && 앞[k] === s[k]) k++;
    앞 = 앞.slice(0, k);
  });
  const 밑길이 = v2조각(밑).length;
  for (let k = 앞.length - 1; k >= 밑길이; k--)
    if (/^\d+$/.test(앞[k])) return { arr: 앞.slice(0, k).join('.'), idx: +앞[k] };
  return null;
}
function v2호스트들() {
  const out = [];
  document.querySelectorAll('section.sl-page[data-slide-idx], main.deck.v2 [data-ent], main.deck.v2 [data-ent="표"] tbody tr')
    .forEach(n => { if (!v2호스트인가(n)) return; const z = v2자리(n); if (z) out.push({ el: n, arr: z.arr, idx: z.idx }); });
  return out;
}
function v2무리(자) {                 // 같은 배열·같은 원소를 그리는 호스트(짝 카드의 왼·오른 칸 등)
  return v2호스트들().filter(h => h.arr === 자.arr && h.idx === 자.idx).map(h => h.el);
}
function v2새번호(arr) {
  const S = v2상태();
  if (S.새번호[arr] === undefined) {
    const 원 = getPath(SRCDOC, arr);
    const 화면 = v2호스트들().filter(h => h.arr === arr).map(h => h.idx);
    S.새번호[arr] = Math.max(Array.isArray(원) ? 원.length : 0, ...화면.map(x => x + 1), 0);
  }
  return S.새번호[arr]++;
}
function v2다시주소(root, 앞, 뒤) {       // 복제본의 경로 앞머리를 새 자리로 바꾼다
  [root, ...root.querySelectorAll('[data-path]')].forEach(x => {
    const p = x.dataset && x.dataset.path;
    if (p && (p === 앞 || p.startsWith(앞 + '.'))) x.dataset.path = 뒤 + p.slice(앞.length);
  });
}
function v2더럽힘(arr) { v2상태().더러운.add(arr); }

// ── 글 칸 — 누르면 바로 고친다 ──
function v2글칸(t) {
  if (!t || !t.closest || !t.closest('main.deck.v2')) return null;
  if (t.closest('svg')) return null;                             // 차트 안 글은 격자에서
  const x = t.closest('[data-path]');
  if (!x || x.closest('[data-derived]')) return null;
  if (x.dataset.ent === '런') return x.closest('[data-runs]');
  if (x.classList.contains('tx')) return x;
  return null;
}
function v2고를것(n) {
  const info = entInfo(n);
  if (!info || V2안고름.has(info.type)) return false;
  if (info.type === '항목') {                                   // 차트 행 이름은 차트째 고른다(값은 격자에서)
    const 부 = v2부품(n.parentElement), s = 부 && ENTS[부.dataset.ent];
    if (s && s['kind'] === '차트') return false;
  }
  return true;
}
function v2안쪽(t) {
  for (let n = t; n && n !== document.body; n = n.parentElement) if (v2고를것(n)) return n;
  return null;
}
function v2고치기(leaf, e) {
  editText(leaf, () => v2빈새항목정리(leaf));
  try {
    if (e && document.caretRangeFromPoint) {
      const r = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (r && leaf.contains(r.startContainer)) { const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
    }
  } catch (x) { /* 커서 자리는 편의일 뿐 */ }
  if (leaf.closest('[data-ent="표"]')) v2상태().마지막칸 = leaf;
}
function v2빈새항목정리(leaf) {         // 새로 넣고 비운 채 벗어나면 지운다(안내 글이 실제 글로 안 남게)
  const h = leaf.closest('[data-v2seed]');
  if (!h || h.matches('section')) return;
  const 무리 = v2무리(v2자리(h) || {});
  const 빈 = 무리.every(m => v2잎들(m).every(x => !x.classList.contains('tx') || !x.textContent.trim()));
  if (빈) { 무리.forEach(m => m.remove()); select(null); }
}
document.addEventListener('click', e => {
  const t = e.target;
  if (t.closest('.panel,.edit-bar,.docset-pop,.copy-note,.resume-bar,.consent-card')) return;
  if (t.isContentEditable) return;
  if (!t.closest('main.deck.v2')) return;
  const leaf = v2글칸(t);
  select(v2안쪽(leaf || t));
  if (leaf) v2고치기(leaf, e);
}, true);
// 편집 중에는 자간 다시 맞추기(__hunt)가 칸 안 span 을 감쌌다 풀어 커서를 뺏지 않게 한다.
(function () {
  const 원 = window.__hunt;
  if (typeof 원 !== 'function') return;
  window.__hunt = function () { if (state.editing) return; return 원.apply(this, arguments); };
})();
document.addEventListener('keydown', e => {
  if (e.isComposing || e.keyCode === 229) return;
  const ed = state.editing;
  if (ed && ed.el && ed.el.closest && ed.el.closest('main.deck.v2')) {
    if (e.key === 'Enter') {
      e.preventDefault();
      const 호 = ed.el.closest('[data-ent="항목"]'), 보 = state.sel;
      ed.el.blur();
      if (호 && !e.shiftKey && 호.isConnected && v2고를것(호) && v2할수있나(호, 'addBelow')) { select(호); v2아래추가(호); }
      else if (보) select(보);
    } else if (e.key === 'Escape') { e.preventDefault(); ed.el.blur(); }
    return;
  }
  if (!state.sel || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName || '')) return;
  if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
    if (v2할수있나(state.sel, 'reorder')) { e.preventDefault(); v2옮기기(state.sel, e.key === 'ArrowUp' ? -1 : 1); }
  } else if (e.shiftKey && e.key === 'Delete') {
    if (v2할수있나(state.sel, 'del')) { e.preventDefault(); v2지우기(state.sel); }
  }
}, true);

// ── 막대 — 고른 개체 위 8px, 주 동작 + ⋯ ──
function v2할수있나(el, a) {
  const info = entInfo(el); if (!info) return false;
  const ui = info.spec['ui'] || {};
  if (![...(ui.bar || []), ...(ui.more || [])].includes(a)) return false;
  if (a === 'level') return !!info.spec['레벨'];                 // v2 항목은 단계가 없다 — 자리만 지킨다(흐림)
  if (a === 'figsize' || a === 'tablesize') return false;         // 판형(칸 배치)이 크기를 정한다 — 자리만 지킨다(흐림)
  if (a === 'ai') return 플러그인 || 서버있음;
  if (a === 'slideAdd') return !/^(표지|요청|마무리)$/.test(el.dataset.layout || '');
  return true;
}
function v2패널(panel, el, info) {
  panel.insertAdjacentHTML('beforeend', '<div class="hint">조작은 고른 개체 위 막대에 있습니다. 글은 눌러서 바로 고칩니다.</div>');
  const ui = info.spec['ui'] || {};
  const bar = document.createElement('div');
  bar.className = 'v2bar'; bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', info.label + ' 조작');
  (ui.bar || []).forEach(a => {
    const b = btn(V2말[a] || a, () => v2실행(a, el, info));
    b.dataset.act = a;
    if (V2단축[a]) b.title = V2단축[a];
    if (!v2할수있나(el, a)) { b.disabled = true; b.title = a === 'level' ? '판형 v2 항목은 단계가 없습니다' : (a === 'slideAdd' ? '표지·요청·마무리 장은 한 번만 둡니다'
      : (a === 'figsize' || a === 'tablesize') ? '슬라이드는 판(레이아웃)이 크기를 정합니다' : ''); }
    bar.appendChild(b);
  });
  if ((ui.more || []).length) {
    const m = btn('⋯', () => v2더보기(bar, el, info));
    m.dataset.act = 'more'; m.title = '더 보기'; m.setAttribute('aria-haspopup', 'menu');
    bar.appendChild(m);
  }
  bar.addEventListener('keydown', ev => {                         // 막대 안 방향키로 칸 옮기기
    if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
    const bs = [...bar.querySelectorAll('button:not([disabled])')], k = bs.indexOf(document.activeElement);
    if (k < 0) return; ev.preventDefault();
    bs[(k + (ev.key === 'ArrowRight' ? 1 : bs.length - 1)) % bs.length].focus();
  });
  panel.appendChild(bar);
  v2자리잡기(bar, el);
}
function v2자리잡기(bar, el) {
  if (!bar || !el || !el.isConnected) return;
  const r = el.getBoundingClientRect(), h = bar.offsetHeight || 30, w = bar.offsetWidth || 200;
  let top = r.top - h - 8;
  if (top < 52) top = r.bottom + 8;
  const left = Math.max(270, Math.min(r.left, window.innerWidth - w - 280));
  bar.style.top = Math.round(top) + 'px'; bar.style.left = Math.round(left) + 'px';
  const m = document.querySelector('.panel .v2menu');
  if (m) { m.style.top = Math.round(top + h + 4) + 'px'; m.style.left = Math.round(left) + 'px'; }
}
function v2다시자리() { v2자리잡기(document.querySelector('.panel .v2bar'), state.sel); }
window.addEventListener('scroll', v2다시자리, true);
window.addEventListener('resize', v2다시자리);
function v2더보기(bar, el, info) {
  const 옛 = document.querySelector('.panel .v2menu');
  if (옛) { 옛.remove(); return; }
  const m = document.createElement('div'); m.className = 'v2menu'; m.setAttribute('role', 'menu');
  const 넣기 = (말, f, c) => { const b = btn(말, () => { m.remove(); f(); }, c); b.setAttribute('role', 'menuitem'); m.appendChild(b); };
  const more = (info.spec['ui'] || {}).more || [];
  more.filter(a => a !== 'del').forEach(a => {
    if (!v2할수있나(el, a)) return;
    if (a === 'reorder') { 넣기('▲ 위로  (Alt+↑)', () => v2옮기기(el, -1)); 넣기('▼ 아래로  (Alt+↓)', () => v2옮기기(el, 1)); }
    else 넣기(V2말[a] || a, () => v2실행(a, el, info));
  });
  // 장 출처('26-09-30 주관 판정 X5) — 지운 출처(교정이 뺀 지은 출처·사람이 지운 출처)를 사람이 다시 적는 칸. 장 막대 ⋯ 안.
  if (info.type === '슬라이드' && el.dataset.layout !== '표지') 넣기('출처 적기…', () => v2출처(el));
  if (more.includes('del') && v2할수있나(el, 'del')) 넣기('삭제  (Shift+Delete)', () => v2지우기(el), 'danger');
  document.querySelector('.panel').appendChild(m);
  v2자리잡기(bar, el);
  const 첫 = m.querySelector('button'); if (첫) 첫.focus();
}
function v2실행(a, el, info) {
  if (a === 'ai') {
    if (플러그인) return addNote(el, info);
    if (서버있음) return ai다시쓰기(el, info);
    return;
  }
  if (a === 'slideAdd') return v2장추가(el);
  if (a === 'addBelow') return v2아래추가(el);
  if (a === 'addItem') return v2항목추가(el);
  if (a === 'tablerow') return v2행추가(el);
  if (a === 'delRow') return v2행빼기(el);
  if (a === 'slots') return v2칸고치기(el, info);
  if (a === 'figdata') return v2격자(el, info);
  if (a === 'note') return v2노트(el);
  if (a === 'del') return v2지우기(el);
}

// ── 넣기 · 빼기 · 옮기기 ──
function v2자리말(x) {
  const 끝 = v2조각(x.dataset.path).pop();
  return /^\d+$/.test(끝) ? '새 항목' : 끝;
}
function v2아래추가(h) {
  const 자 = v2자리(h); if (!자) return;
  const 새 = v2새번호(자.arr);
  let 첫 = null, 첫호 = null;
  v2무리(자).forEach(m => {
    const c = m.cloneNode(true);
    v2다시주소(c, 자.arr + '.' + 자.idx, 자.arr + '.' + 새);
    c.dataset.v2seed = String(자.idx); c.dataset.v2arr = 자.arr; c.dataset.v2idx = String(새);
    c.classList.remove('ent-sel', 'is-focus');
    c.querySelectorAll('.ent-sel').forEach(x => x.classList.remove('ent-sel'));
    [c, ...c.querySelectorAll('.tx')].filter(x => x.classList.contains('tx')).forEach(x => {
      x.textContent = ''; x.dataset.v2ph = v2자리말(x);
    });
    m.after(c);
    if (!첫) { 첫 = c.classList.contains('tx') ? c : c.querySelector('.tx'); 첫호 = c; }
  });
  v2더럽힘(자.arr);
  state.ops.push({ action: '항목 추가' });
  if (첫) { select(v2안쪽(첫) || 첫호); v2고치기(첫); }
  save();
}
function v2항목추가(part) {
  const hs = v2호스트들().filter(h => h.el !== part && part.contains(h.el) && !h.el.matches('tr')
    && v2부품(h.el.parentElement) === part);
  if (!hs.length) { toast('이 부품에는 더할 항목이 없습니다'); return; }
  const 얕 = Math.min(...hs.map(h => v2조각(h.arr).length));
  const 끝 = hs.filter(h => v2조각(h.arr).length === 얕).pop();
  v2아래추가(끝.el);
}
function v2행추가(part) {
  const trs = [...part.querySelectorAll('tbody tr')];
  if (!trs.length) return;
  v2아래추가(trs[trs.length - 1]);
}
function v2행빼기(part) {
  const trs = [...part.querySelectorAll('tbody tr')];
  if (trs.length <= 1) { toast('표에는 행이 하나는 있어야 합니다'); return; }
  const 칸 = v2상태().마지막칸, tr = (칸 && part.contains(칸) && 칸.closest('tbody tr')) || trs[trs.length - 1];
  v2빼고되돌리기([tr], v2자리(tr).arr, '표 행을 뺐습니다');
}
function v2빼고되돌리기(els, arr, 말) {
  const 자리 = els.map(x => [x, x.parentNode, x.nextSibling]);
  els.forEach(x => x.remove());
  if (arr) v2더럽힘(arr);
  state.ops.push({ action: '삭제', target: 말 });
  select(null); save();
  되돌리기토스트(말, () => {
    자리.slice().reverse().forEach(([x, p, n]) => { if (p) p.insertBefore(x, n && n.parentNode === p ? n : null); });
    state.ops.push({ action: '삭제 되돌림' }); save();
  });
}
function v2지우기(el) {
  const info = entInfo(el); if (!info) return;
  const t = info.type, S = v2상태();
  if (t === '슬라이드') {
    if (document.querySelectorAll('section.sl-page[data-slide-idx]').length <= 1) { toast('장이 하나뿐이라 지울 수 없습니다'); return; }
    S.다시 = true;
    return v2빼고되돌리기([el], '장', '장을 지웠습니다');
  }
  if (['요지띠', '리드', '출처', '표지수치'].includes(t)) {
    const 장 = v2장(el); if (!장) return;
    const p = '장.' + 장.dataset.slideIdx + '.' + ({ 표지수치: '표지.수치' }[t] || t);
    const 자리 = [el, el.parentNode, el.nextSibling];
    el.remove(); S.지운필드.add(p); S.다시 = true;
    state.ops.push({ action: '삭제', target: info.label }); select(null); save();
    되돌리기토스트(info.label + '을(를) 지웠습니다', () => {
      자리[1].insertBefore(자리[0], 자리[2] && 자리[2].parentNode === 자리[1] ? 자리[2] : null);
      S.지운필드.delete(p); save();
    });
    return;
  }
  const 자 = v2자리(el); if (!자) return;
  const 같은 = new Set(v2호스트들().filter(h => h.arr === 자.arr).map(h => h.idx));
  if (V2부품.has(t)) {
    // 장의 마지막 부품은 지우지 않는다(빈 장 = 렌더 백지 게이트). 장째 지우도록 안내한다.
    const 장 = v2장(el), 장부품 = 장 ? v2호스트들().filter(h => V2부품.has(h.el.dataset.ent) && 장.contains(h.el)).length : 0;
    if (장부품 <= 1) { toast('장의 마지막 부품입니다 — 장을 지우세요'); return; }
    const 묶 = el.parentElement && el.parentElement.classList.contains('v2-stack') ? el.parentElement : null;
    const 남 = 묶 ? [...묶.children].filter(x => x !== el) : [];
    let 뺄 = el, 배열 = 자.arr;
    if (!묶 && el.parentElement && el.parentElement.classList.contains('v2-cell')) 뺄 = el.parentElement;
    if (묶 && !남.length) {                        // 묶음이 비면 묶음째(명시 세로묶음이면 그 자리 배열로)
      뺄 = 묶.closest('.v2-cell') || 묶;
      if (묶.dataset.path) { const z = v2자리(묶); if (z) 배열 = z.arr; }
    }
    const 장길 = 장 ? '장.' + 장.dataset.slideIdx : '';
    if (장길 && 배열 === 장길 + '.칸') S.폭풀기.add(장길);   // 칸이 줄면 폭은 기본 배치로
    S.다시 = true;
    return v2빼고되돌리기([뺄], 배열, info.label + '을(를) 지웠습니다');
  }
  if (같은.size <= 1) { toast('마지막 항목은 지울 수 없습니다 — 부품을 지우세요'); return; }
  v2빼고되돌리기(v2무리(자), 자.arr, '항목을 지웠습니다');
}
function v2옮기기(el, d) {
  const 자 = v2자리(el); if (!자) return;
  if (el.matches('section')) {
    if (el.dataset.layout === '표지') { toast('표지는 맨 앞에 둡니다'); return; }
    let n = d < 0 ? el.previousElementSibling : el.nextElementSibling;
    while (n && !n.matches('section.sl-page[data-slide-idx]')) n = d < 0 ? n.previousElementSibling : n.nextElementSibling;
    if (!n || n.dataset.layout === '표지') { toast(d < 0 ? '더 위로 갈 수 없습니다' : '더 아래로 갈 수 없습니다'); return; }
    if (d < 0) n.before(el); else n.after(el);
    v2상태().다시 = true;
  } else {
    const 무리 = v2무리(자), 모두 = v2호스트들().filter(h => h.arr === 자.arr);
    const 순서 = [...new Set(모두.map(h => h.idx))], k = 순서.indexOf(자.idx), j = k + d;
    if (j < 0 || j >= 순서.length) { toast(d < 0 ? '더 위로 갈 수 없습니다' : '더 아래로 갈 수 없습니다'); return; }
    const 옆 = 모두.filter(h => h.idx === 순서[j]).map(h => h.el);
    무리.forEach((m, q) => { const x = 옆[q] || 옆[옆.length - 1]; if (!x) return; if (d < 0) x.before(m); else x.after(m); });
  }
  v2더럽힘(자.arr);
  state.ops.push({ action: '순서', to: d < 0 ? '위로' : '아래로' });
  save(); select(el); el.scrollIntoView({ block: 'nearest' });
}
function v2장추가(sec) {
  if (!v2할수있나(sec, 'slideAdd')) { toast('표지·건의(요청)·마무리 장은 덱에 한 번만 둡니다'); return; }
  const 원 = +sec.dataset.slideIdx, 새 = v2새번호('장');
  const c = sec.cloneNode(true);
  v2다시주소(c, '장.' + 원, '장.' + 새);
  c.dataset.slideIdx = String(새);
  c.dataset.v2seed = String(원); c.dataset.v2arr = '장'; c.dataset.v2idx = String(새);
  c.classList.remove('ent-sel'); c.querySelectorAll('.ent-sel').forEach(x => x.classList.remove('ent-sel'));
  sec.after(c);
  v2더럽힘('장'); v2상태().다시 = true;
  state.ops.push({ action: '장 추가', to: (원 + 1) + '장을 본뜸' });
  save(); select(c); c.scrollIntoView({ block: 'center' });
  toast('이 장을 본떠 바로 아래에 새 장을 만들었습니다 — 글을 눌러 고치세요', 3000);
}
function v2노트(sec) {
  const i = sec.dataset.slideIdx;
  let leaf = sec.querySelector('.sl-notes [data-path="장.' + i + '.노트.말"], .sl-notes [data-path="장.' + i + '.노트"]');
  줄고치기('발표자 노트 — 화면·인쇄에는 안 나오고 발표자 보기·PPTX 노트로 갑니다', leaf ? leaf.textContent : '', v => {
    if (!leaf) {
      if (!v) return;
      let a = sec.querySelector('aside.sl-notes');
      if (!a) { a = document.createElement('aside'); a.className = 'sl-notes'; a.hidden = true; a.dataset.ent = '노트'; sec.appendChild(a); }
      leaf = document.createElement('p'); leaf.className = 'tx';
      leaf.dataset.path = typeof getPath0('장.' + i + '.노트') === 'string' ? '장.' + i + '.노트' : '장.' + i + '.노트.말';
      leaf.dataset.v2make = '1'; a.prepend(leaf);
    }
    leaf.textContent = v;
    state.ops.push({ action: '발표자 노트' }); save();
  });
}

// ── 값·라벨 고치기(부품 글 칸 입력판) · 차트 값 격자 ──
function v2판(제목, 부제) {
  const 옛 = document.querySelector('.panel .v2pop'); if (옛) 옛.remove();
  const p = document.createElement('div'); p.className = 'v2pop'; p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', 제목);
  p.innerHTML = '<h4>' + esc(제목) + '</h4>' + (부제 ? '<p class="v2sub">' + esc(부제) + '</p>' : '');
  p.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); p.remove(); } });
  document.querySelector('.panel').appendChild(p);
  return p;
}
function v2출처(장el) {
  const S = v2상태(), p = '장.' + 장el.dataset.slideIdx + '.출처';
  S.출처 = S.출처 || {};
  const 지금 = (p in S.출처) ? S.출처[p] : (S.지운필드.has(p) ? '' : String(getPath(SRCDOC, p) || ''));
  const pop = v2판('이 장의 출처', '자료에 적힌 문서 이름과 시점만 적어 주세요. 비워 두고 적용하면 출처 줄이 빠집니다.');
  const l = document.createElement('label');
  l.innerHTML = '<span>출처</span>';
  const inp = document.createElement('input'); inp.type = 'text'; inp.maxLength = 60; inp.value = 지금; inp.dataset.v2src = '1';
  l.appendChild(inp); pop.appendChild(l);
  v2단추줄(pop, () => {
    const v = inp.value.replace(/\s+/g, ' ').trim();
    if (v === 지금.trim()) return;
    S.출처[p] = v; S.지운필드.delete(p); S.다시 = true;
    state.ops.push(v ? { action: '출처 적기', target: '출처' } : { action: '삭제', target: '출처' });
    save();
  });
  inp.focus();
}
function v2단추줄(p, 적용) {
  const r = document.createElement('div'); r.className = 'v2row';
  r.appendChild(btn('취소', () => p.remove()));
  r.appendChild(btn('적용', () => { if (적용() !== false) p.remove(); }, 'good'));
  p.appendChild(r);
}
function v2글잎들(el) {                    // 경로별 첫 조각 — 부품 안 글 칸(노트·파생 글 빼고)
  const 본 = new Map();
  [el, ...el.querySelectorAll('.tx')].forEach(x => {
    if (!x.classList || !x.classList.contains('tx') || !x.dataset.path) return;
    if (x.closest('[data-derived]') || x.closest('.sl-notes')) return;
    if (x.parentElement && x.parentElement.closest('[data-runs]')) return;
    if (!본.has(x.dataset.path)) 본.set(x.dataset.path, []);
    본.get(x.dataset.path).push(x);
  });
  return [...본.values()];
}
function v2숫자잎(x) {
  if (/(^|\s)(num__v|num__u|qty__v|qty__u)(\s|$)/.test(x.className)) return true;
  if (typeof getPath0(x.dataset.path) === 'number') return true;
  return /^[\d\s.,%+\-−~·]+$/.test(x.textContent.trim());
}
function v2잎이름(부, p) {
  return p.slice(부.length + 1).split('.').map(s => /^\d+$/.test(s) ? String(+s + 1) : s).join(' ') || '글';
}
function v2글넣기(els, v) { els[0].textContent = v; els.slice(1).forEach(x => { x.textContent = ''; }); }
function v2칸고치기(el, info) {
  const 무리 = v2글잎들(el); if (!무리.length) return;
  const 밑 = el.dataset.path || (v2장(el) ? '장.' + v2장(el).dataset.slideIdx : '');
  const p = v2판(info.label + ' — 값·라벨 고치기', '비우면 그 칸이 빈 채로 저장됩니다. 숫자 뒤 단위는 따로 적습니다.');
  const 입력 = 무리.map(els => {
    const l = document.createElement('label');
    l.innerHTML = '<span>' + esc(v2잎이름(밑, els[0].dataset.path)) + '</span>';
    const inp = document.createElement('input'); inp.type = 'text'; inp.value = textOf(이어붙임(els));
    inp.dataset.path = els[0].dataset.path;
    l.appendChild(inp); p.appendChild(l); return [els, inp];
  });
  v2단추줄(p, () => {
    let 바뀜 = 0;
    입력.forEach(([els, inp]) => { if (inp.value.trim() !== textOf(이어붙임(els))) { v2글넣기(els, inp.value.trim()); 바뀜++; } });
    if (바뀜) { state.ops.push({ action: '값·라벨 고치기', target: info.label }); repaginate(); }
  });
  입력[0][1].focus(); 입력[0][1].select();
}
function v2지금부품(path) { return getPath(v2직렬화().doc, path); }
function v2격자(el, info) {
  const 길 = el.dataset.path, 부 = v2지금부품(길);
  if (!부 || typeof 부 !== 'object') return;
  const p = v2판(info.label + ' — 값 고치기',
    서버있음 ? '적용하면 저장한 뒤 조립기가 차트를 다시 그립니다.' : '적용한 값은 채팅에서 문서를 다시 만들 때 그려집니다.');
  const 숫자 = s => { const t = String(s).replace(/,/g, '').trim(); if (t === '') return null; const n = Number(t); return isFinite(n) ? n : NaN; };
  const 칸 = (v, w) => { const i = document.createElement('input'); i.type = 'text'; i.value = v == null ? '' : String(v); if (w) i.style.minWidth = w; return i; };
  const tb = document.createElement('table'); p.appendChild(tb);
  let 거두기 = null;
  if (Array.isArray(부['가로축']) && Array.isArray(부['계열'])) {          // 선차트: 열 = 시점, 행 = 계열
    const 축 = 부['가로축'].slice(), 계열 = v2복제(부['계열']);
    const 그리기 = () => {
      tb.innerHTML = '';
      const hr = tb.insertRow(); hr.insertCell().textContent = '계열 / 시점';
      축.forEach((a, k) => { const c = hr.insertCell(); const i = 칸(a, '56px'); i.dataset.ax = k; c.appendChild(i); });
      계열.forEach((s, q) => {
        const r = tb.insertRow(); const c0 = r.insertCell(); const n = 칸(s['이름'], '90px'); n.dataset.nm = q; c0.appendChild(n);
        축.forEach((_, k) => { const c = r.insertCell(); const i = 칸((s['값'] || [])[k], '56px'); i.dataset.sr = q; i.dataset.k = k; c.appendChild(i); });
      });
    };
    const 읽기 = () => {
      tb.querySelectorAll('input[data-ax]').forEach(i => { 축[+i.dataset.ax] = i.value.trim(); });
      tb.querySelectorAll('input[data-nm]').forEach(i => { 계열[+i.dataset.nm]['이름'] = i.value.trim(); });
      let 틀림 = false;
      tb.querySelectorAll('input[data-sr]').forEach(i => {
        const v = 숫자(i.value); if (Number.isNaN(v)) 틀림 = true;
        const s = 계열[+i.dataset.sr]; s['값'] = (s['값'] || []).slice(0, 축.length);
        while (s['값'].length < 축.length) s['값'].push(null);
        s['값'][+i.dataset.k] = Number.isNaN(v) ? null : v;
      });
      return !틀림;
    };
    그리기();
    const r = document.createElement('div'); r.className = 'v2row'; r.style.justifyContent = 'flex-start';
    r.appendChild(btn('＋ 시점', () => { 읽기(); 축.push(''); 계열.forEach(s => (s['값'] = s['값'] || []).push(null)); 그리기(); }));
    r.appendChild(btn('－ 마지막 시점', () => { 읽기(); if (축.length <= 2) { toast('시점은 둘 이상이어야 합니다'); return; } 축.pop(); 계열.forEach(s => (s['값'] || []).pop()); 그리기(); }));
    p.appendChild(r);
    거두기 = () => (읽기() && 축.every(a => a) ? { 가로축: 축, 계열 } : null);
  } else {
    const 배열키 = ['행', '점', '조각'].find(k => Array.isArray(부[k]));
    if (배열키) {                                                    // 가로막대·점눈금·구성띠: 행 = 라벨 | 값
      const 줄 = v2복제(부[배열키]);
      const 그리기 = () => {
        tb.innerHTML = '';
        const hr = tb.insertRow(); hr.insertCell().textContent = '라벨'; hr.insertCell().textContent = '값' + (부['단위'] ? ' (' + 부['단위'] + ')' : '');
        줄.forEach((o, q) => { const r = tb.insertRow(); const a = 칸(o['라벨']); a.dataset.lb = q; r.insertCell().appendChild(a);
          const b = 칸(o['값'], '70px'); b.dataset.vl = q; r.insertCell().appendChild(b); });
      };
      const 읽기 = () => {
        let 틀림 = false;
        tb.querySelectorAll('input[data-lb]').forEach(i => { 줄[+i.dataset.lb]['라벨'] = i.value.trim(); });
        tb.querySelectorAll('input[data-vl]').forEach(i => { const v = 숫자(i.value); if (v === null || Number.isNaN(v)) 틀림 = true; else 줄[+i.dataset.vl]['값'] = v; });
        return !틀림;
      };
      그리기();
      const r = document.createElement('div'); r.className = 'v2row'; r.style.justifyContent = 'flex-start';
      r.appendChild(btn('＋ 행', () => { 읽기(); 줄.push({ 라벨: '', 값: 0 }); 그리기(); }));
      r.appendChild(btn('－ 마지막 행', () => { 읽기(); if (줄.length <= 1) return; 줄.pop(); 그리기(); }));
      p.appendChild(r);
      거두기 = () => (읽기() && 줄.every(o => o['라벨']) ? { [배열키]: 줄 } : null);
    } else {                                                          // 비율링·진행막대: 이름 붙은 숫자 칸
      const 키들 = ['값', '목표', '목표선'].filter(k => typeof 부[k] === 'number');
      if (typeof 부['표시'] === 'string') 키들.push('표시');
      키들.forEach(k => { const r = tb.insertRow(); r.insertCell().textContent = k; const i = 칸(부[k]); i.dataset.key = k; r.insertCell().appendChild(i); });
      거두기 = () => {
        const o = {}; let 틀림 = false;
        tb.querySelectorAll('input[data-key]').forEach(i => {
          const k = i.dataset.key;
          if (k === '표시') { o[k] = i.value.trim(); return; }
          const v = 숫자(i.value); if (v === null || Number.isNaN(v)) 틀림 = true; else o[k] = v;
        });
        return 틀림 ? null : o;
      };
    }
  }
  v2단추줄(p, () => {
    const 새 = 거두기 && 거두기();
    if (!새) { toast('비었거나 숫자가 아닌 칸이 있습니다 — 고쳐 주세요', 2600); return false; }
    const S = v2상태();
    S.값[길] = Object.assign(S.값[길] || {}, v2복제(새));
    // 화면의 이름 칸(행 라벨·계열 이름)도 같은 글로 — 글 패치가 격자 값을 되덮지 않게
    Object.entries(새).forEach(([k, v]) => {
      if (!Array.isArray(v)) return;
      v.forEach((o, q) => {
        if (!o || typeof o !== 'object') return;
        ['라벨', '이름'].forEach(f => {
          const x = document.querySelectorAll('[data-path="' + 길 + '.' + k + '.' + q + '.' + f + '"]');
          if (x.length && o[f] !== undefined) v2글넣기([...x], String(o[f]));
        });
      });
    });
    S.다시 = true;
    state.ops.push({ action: '차트 값', target: info.label });
    save();
    toast(서버있음 ? '값을 바꿨습니다 — 저장하면 차트를 다시 그립니다' : '값을 바꿨습니다 — 채팅에 알려 주시면 다시 그립니다', 2800);
  });
  const 첫 = p.querySelector('input'); if (첫) 첫.focus();
}

// ── 문서 설정 › 판 모양(프리셋)·밀도 ──
function v2설정기본(k) { return ((상단칸[k] || [])[0] || [])[0] || ''; }
function v2설정지금(k) {
  const S = v2상태();
  return k in S.설정 ? S.설정[k] : (SRCDOC[k] || v2설정기본(k));
}
function v2설정고르기(k, v, 라벨, 이름) {
  const S = v2상태();
  if (v === v2설정지금(k)) return;
  if (v === SRCDOC[k] || (SRCDOC[k] === undefined && v === v2설정기본(k))) delete S.설정[k];   // 원래대로 = 키 안 남김
  else S.설정[k] = v;
  if (k === '프리셋') {                                   // 곧바로 보이는 만큼만 미리(정확한 판은 다시 조립한 뒤)
    const d = document.querySelector('main.deck.v2');
    if (d) { d.classList.remove('p-data', 'p-briefing', 'p-keynote'); d.classList.add('p-' + v); }
  }
  S.다시 = true;
  state.ops = state.ops.filter(o => o.action !== 이름);
  state.ops.push({ action: 이름, to: 라벨 });
  v2설정표시(); save();
  toast(이름 + (받침있나(이름) ? '을 ' : '를 ') + 라벨 + 로(라벨) + ' 바꿉니다 — '
    + (서버있음 ? '저장하면 다시 그립니다' : '채팅에서 다시 만들 때 그려집니다'), 2800);
}
function v2설정표시() {
  document.querySelectorAll('.docset-pop .ds-opt[data-v2set]').forEach(b =>
    b.setAttribute('aria-checked', String(b.dataset.v === v2설정지금(b.dataset.v2set))));
  document.querySelectorAll('.docset-pop .ds-row[data-v2row]').forEach(r => 한자리만([...r.querySelectorAll('.ds-opt')]));
}
function v2설정절(판) {
  [['프리셋', '판 모양', '데이터형이 기본입니다. 브리핑·키노트는 프리셋 — 저장하면 다시 그립니다.'],
   ['밀도', '밀도', '장당 글 양의 기준입니다. 판을 억지로 늘리지 않습니다.']].forEach(([k, 이름, 말]) => {
    const 목록 = 상단칸[k]; if (!Array.isArray(목록) || !목록.length) return;
    const s = document.createElement('div'); s.className = 'ds-sec';
    s.innerHTML = '<h3>' + esc(이름) + '</h3><p class="ds-sub">' + esc(말) + '</p>';
    const row = document.createElement('div'); row.className = 'ds-row'; row.dataset.v2row = k;
    row.setAttribute('role', 'radiogroup'); row.setAttribute('aria-label', 이름);
    목록.forEach(([v, 라벨, 힌트]) => {
      const o = document.createElement('button');
      o.type = 'button'; o.className = 'ds-opt'; o.dataset.v2set = k; o.dataset.v = v; o.setAttribute('role', 'radio');
      o.textContent = 라벨; o.title = 힌트 || '';
      o.onclick = () => v2설정고르기(k, v, 라벨, 이름);
      row.appendChild(o);
    });
    row.addEventListener('keydown', 방향키(row, '.ds-opt'));
    s.appendChild(row); 판.appendChild(s);
  });
  setTimeout(v2설정표시, 0);
}

// ── AI 대상 — 부품의 글 칸(숫자·단위는 빼고). 한 칸이면 그 칸, 여럿이면 목록(개수·순서 유지) ──
function v2ai대상(el, info) {
  let 잎 = null;
  if (info.type === '슬라이드' || info.type === '머리') {
    const m = el.querySelector('.sl-head__msg.tx');
    return m ? { el: m, apply: null } : null;
  }
  잎 = v2글잎들(el).filter(els => !v2숫자잎(els[0]));
  if (!잎.length) return null;
  if (잎.length === 1) return { el: 잎[0][0], apply: () => 잎[0].slice(1).forEach(x => { x.textContent = ''; }) };
  return { 리스트: 잎.map(els => textOf(이어붙임(els))), 되박기: 고친 => {
    고친.forEach((v, k) => { if (v != null && String(v).trim() && 잎[k]) v2글넣기(잎[k], String(v).trim()); });
  } };
}

// ── 저장 모양 — 원본 복제 + 글 패치 + 바뀐 배열만 화면 순서로 다시 짜기 ──
function v2직렬화() {
  const S = v2상태();
  const doc = v2복제(SRCDOC);
  // ⓪ 새 자리(복제한 장·항목·행)에 본뜬 원소를 먼저 심는다 — 얕은 배열부터, 번호 순으로
  const 씨 = [...document.querySelectorAll('[data-v2seed]')]
    .map(el => ({ arr: el.dataset.v2arr, idx: +el.dataset.v2idx, src: +el.dataset.v2seed }))
    .sort((a, b) => (v2조각(a.arr).length - v2조각(b.arr).length) || (a.idx - b.idx));
  const 심음 = new Set();
  씨.forEach(s => {
    const 열쇠 = s.arr + '#' + s.idx; if (심음.has(열쇠)) return; 심음.add(열쇠);
    const a = getPath(doc, s.arr); if (!Array.isArray(a) || a[s.src] === undefined) return;
    const c = v2복제(a[s.src]);
    if (c && typeof c === 'object' && !Array.isArray(c) && s.arr !== '장' && c['역할'] === '강조') delete c['역할'];
    a[s.idx] = c;
  });
  // ① 차트 격자 값(부품 경로 → 필드) — 글 패치보다 먼저(이름 칸은 화면 글과 맞춰 두었다)
  Object.entries(S.값).forEach(([p, 필드]) => Object.entries(필드).forEach(([k, v]) => setPath(doc, p + '.' + k, v2복제(v))));
  // ② 글 칸 — .tx 잎(런 묶음 제외)만. 안 고친 칸은 원본 값·자료형 그대로 둔다.
  const 묶음 = [];
  경로조각().forEach(([path, els]) => {
    const el = els[0];
    if (el.dataset.runs) { 묶음.push([path, els]); return; }
    if (el.dataset.ent === '런' || !el.classList.contains('tx')) return;
    const 원 = getPath(doc, path);
    const now = textOf(이어붙임(els));
    if (원 === undefined && !el.closest('[data-v2seed]') && !el.dataset.v2make) return;   // 격자가 뺀 행의 옛 칸 등
    if (원 !== undefined && String(원 == null ? '' : 원).replace(/\s+/g, ' ').trim() === now) return;
    if (typeof 원 === 'number') { const n = Number(now.replace(/,/g, '')); setPath(doc, path, now !== '' && isFinite(n) ? n : now); }
    else setPath(doc, path, now);
  });
  // ③ 런 묶음 — 화면 글 조각을 차례대로 읽어 런 배열로(런 밖에 친 글은 역할 없는 런)
  묶음.forEach(([path, els]) => {
    const 원 = getPath(doc, path); if (!Array.isArray(원)) return;
    const 조 = [];
    els.forEach(w => {
      const tw = document.createTreeWalker(w, NodeFilter.SHOW_TEXT);
      for (let n = tw.nextNode(); n; n = tw.nextNode()) {
        const 런 = n.parentElement && n.parentElement.closest('[data-ent="런"]');
        const r = 런 && w.contains(런) ? +런.dataset.path.slice(path.length + 1).split('.')[0] : -1;
        if (조.length && 조[조.length - 1].r === r) 조[조.length - 1].t += n.nodeValue; else 조.push({ r, t: n.nodeValue });
      }
    });
    const 새 = 조.map(x => Object.assign(x.r >= 0 && 원[x.r] ? v2복제(원[x.r]) : {}, { t: x.t.replace(/ /g, ' ') }))
      .filter(o => o.t !== '');
    if (JSON.stringify(새) !== JSON.stringify(원)) setPath(doc, path, 새);
  });
  // ④ 지운 필드(요지띠·리드·출처·표지 수치)
  S.지운필드.forEach(p => {
    const k = p.lastIndexOf('.'), 부 = getPath(doc, p.slice(0, k));
    if (부 && typeof 부 === 'object' && !Array.isArray(부)) delete 부[p.slice(k + 1)];
  });
  // ④-2 장 막대 ⋯ 에서 다시 적은 출처(X5) — 빈 글이면 키를 뺀다(출처는 ○○로 두지 않는다). 번호는 ④ 처럼 원본 장 번호다
  Object.entries(S.출처 || {}).forEach(([p, v]) => {
    const k = p.lastIndexOf('.'), 부 = getPath(doc, p.slice(0, k));
    if (!부 || typeof 부 !== 'object' || Array.isArray(부)) return;
    if (v) 부[p.slice(k + 1)] = v; else delete 부[p.slice(k + 1)];
  });
  // ⑤ 머리 강조는 메시지 안 글자여야 한다 — 메시지를 고쳐 없어진 강조는 뺀다
  (doc['장'] || []).forEach(s => {
    const m = s && s['머리'];
    if (!m || !Array.isArray(m['강조'])) return;
    const msg = String(m['메시지'] || ''), k = m['강조'].filter(x => typeof x === 'string' && x && msg.includes(x));
    if (k.length !== m['강조'].length) { if (k.length) m['강조'] = k; else delete m['강조']; }
  });
  // ⑥ 칸이 준 장은 폭을 걷어 기본 배치로(일부만 폭이 남으면 게이트가 막는다)
  S.폭풀기.forEach(p => { const 칸 = getPath(doc, p + '.칸'); if (Array.isArray(칸)) 칸.forEach(c => { if (c && typeof c === 'object') delete c['폭']; }); });
  // ⑦ 넣고 빼고 옮긴 배열만 화면 순서대로 다시 짠다 — 깊은 배열부터(얕은 배열 번호가 아직 원본일 때)
  if (S.더러운.size) {
    const 모두 = v2호스트들();
    [...S.더러운].sort((a, b) => v2조각(b).length - v2조각(a).length).forEach(arr => {
      const a = getPath(doc, arr); if (!Array.isArray(a)) return;
      const 본 = new Set(), 새 = [];
      모두.filter(h => h.arr === arr).forEach(h => {
        if (본.has(h.idx)) return; 본.add(h.idx);
        if (a[h.idx] !== undefined) 새.push(a[h.idx]);
      });
      const 처음 = S.처음호스트[arr], 원길이 = (getPath(SRCDOC, arr) || []).length;
      a.forEach((x, k) => { if (x !== undefined && !본.has(k) && k < 원길이 && 처음 && !처음.has(k)) 새.push(x); });
      a.splice(0, a.length, ...새);
    });
  }
  // ⑧ 문서 설정(프리셋·밀도) — 기본값으로 되돌리면 키를 지운다
  Object.entries(S.설정).forEach(([k, v]) => { doc[k] = v; });
  return { doc, instructions: state.notes, ops: state.ops, 보관요청: state.보관요청 || null };
}

// ── 저장 뒤 — 그림이 바뀌는 편집이면 다시 조립한 판을 다시 연다(편집 중이면 끝난 뒤) ──
// '26-09-28 적대 검토(회귀 ①·④) — 예전엔 응답이 온 저장에 그 구조 편집이 실렸는지 모른 채 지금의 S.다시만
// 보고 다시 열어, 앞 저장이 나가 있는 동안 한 장 추가·장 삭제·프리셋 바꾸기가 새로고침에 조용히 사라졌고
// (버퍼도 지워 되살릴 길이 없었다), 장 삭제의 '5초 되돌리기'가 약 2초에 끊겼다. 이제 ① 응답이 온 저장본과
// 지금 화면을 직렬화한 문서가 같을 때만 다시 열고(다르면 한 번 더 저장해 그 응답을 기다린다), ② 되돌리기
// 토스트가 떠 있는 동안은 미룬다. 버퍼 지우기는 그 확인 뒤다.
function v2같은판(snap) {
  try {
    const a = JSON.parse(JSON.stringify((snap && snap.doc) || {}));
    const b = JSON.parse(JSON.stringify((serialize() || {}).doc || {}));
    delete a._수정시각; delete b._수정시각;
    return JSON.stringify(a) === JSON.stringify(b);
  } catch (e) { return false; }
}
function v2저장뒤(j, snap) {
  const S = v2상태();
  if (j && j.ok) { if (S.다시) { S.다시대기 = true; S.저장본 = snap || null; v2다시그리기(); } return null; }
  const 로그 = (j && j['로그']) || '';
  if (/판 규칙에 걸려/.test(로그)) {
    const 첫 = (로그.match(/^\s*·\s*(.+)$/m) || [])[1] || '';
    return '판 규칙에 걸려 저장하지 않았습니다' + (첫 ? ' — ' + 첫.slice(0, 90) : '');
  }
  return null;
}
function v2다시그리기() {
  const S = v2상태();
  if (!S.다시대기 || state.editing || !서버있음) return;
  clearTimeout(S.다시타이머);
  const 토스트 = document.querySelector('.copy-note');
  if (토스트 && getComputedStyle(토스트).display !== 'none' && 토스트.querySelector('button')) {   // ② 되돌리기를 누를 틈을 준다
    S.다시타이머 = setTimeout(v2다시그리기, 700); return;
  }
  if (S.저장본 && !v2같은판(S.저장본) && (S.어긋남 = (S.어긋남 || 0) + 1) <= 4) {   // ① 아직 안 실린 편집이 있다
    st.textContent = '문서에 반영하는 중… (이어서 고친 곳을 마저 싣습니다)';
    save(); return;                       // 그 저장의 응답이 v2저장뒤 → 여기로 다시 온다
  }
  st.textContent = '문서에 반영했습니다 — 다시 그리는 중…';
  S.다시타이머 = setTimeout(() => {
    // 250ms 사이에 또 고쳤으면(연달아 지우기) 다시 열지 않고 그것부터 싣는다 — 버퍼도 그대로 둔다
    if (S.저장본 && !v2같은판(S.저장본) && (S.어긋남 = (S.어긋남 || 0) + 1) <= 4) { save(); return; }
    try { sessionStorage.setItem('v2-scroll-' + FN, String(Math.round(window.scrollY))); } catch (e) {}
    try { localStorage.removeItem(KEY); } catch (e) {}
    location.reload();
  }, 250);
}
// 처음 그린 호스트(배열별 번호) — 화면에 안 그린 원소는 다시 짤 때도 남긴다
(function () {
  const S = v2상태();
  v2호스트들().forEach(h => { (S.처음호스트[h.arr] = S.처음호스트[h.arr] || new Set()).add(h.idx); });
  try {
    const y = sessionStorage.getItem('v2-scroll-' + FN);
    if (y !== null) { sessionStorage.removeItem('v2-scroll-' + FN); setTimeout(() => window.scrollTo(0, +y), 350); }
  } catch (e) {}
})();
"""
