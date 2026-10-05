"""개체 위 막대(T1) — 도식·차트·표('26-09-29 도식·표 재설계, 편집기 알잘딱깔센).

render_editor_any.gen() 이 옛 편집 화면(판형 v2 가 아닌 문서)에 끼운다. 판형 v2 슬라이드는 editor_v2.py 의
막대를 쓴다 — 칸 순서는 그쪽과 같게 둔다(차트형 [값 고치기 | (크기) | AI로 고치기 | ⋯]).

  · 막대는 주 동작 셋 + ⋯ 네 칸 고정. 같은 종류는 장르가 달라도 칸 순서가 같다(프로파일 `막대`·`차트막대`)
      도식 [＋ 항목 추가 | 크기 | AI로 고치기 | ⋯]
      차트 [값 고치기   | 크기 | AI로 고치기 | ⋯]   ← 도식 개체 중 type 이 차트(bar·hbar·line·donut·stack)
      표   [＋ 행·열 추가 | 크기 | AI로 고치기 | ⋯(7개 이하)]
  · 크기는 작게·보통·크게 한 축(사장님 판정 ①). 누르면 바로 다시 그리고, 1p 한 쪽·풀버전 쪽 넘침·도식 한 쪽
    넘김·슬라이드 장 넘침이 새로 생기면 **적용하지 않고** 까닭을 알린다(쪽게이트). 옛 슬라이드 표는 판이 크기를
    정해 칸이 흐리다.
  · 색은 ⋯ › 색… 안 역할 칩(도식 칸: 기본·강조·회색·분야 1·분야 2 / 표 칸: 없음·강조·회색). 팔레트는 윗줄
    '문서 설정'에 한 번만 있다. 칩은 hex 를 안 쓰고 토큰(var(--fig-*))으로 칠한다.
  · 메뉴·하위 메뉴는 처음부터 지어 두고(숨김) 보이기만 켠다 — 막대가 다시 그려져도 단추 이름·차례가 같다.
  · 이력: 조작마다 state.ops 한 줄(저장 뒤 비움 — 편집기 2단계 규율). 크기는 5초 되돌리기 토스트를 붙이고,
    그 토스트가 떠 있는 동안만 Cmd/Ctrl+Z 가 크기를 되돌린다(모양 되돌리기와 같은 범위 규칙).

이 조각은 SCRIPT 의 IIFE 안(자리표시 /*@@BAR@@*/)에 들어가 state·select·save·figSpec·표 도우미를 그대로
쓴다. renderPanel 쪽 걸이(typeof 막대패널 === 'function')는 이 조각이 없으면 아무 일도 안 한다.
**맨 위 이름은 var·function 만 쓴다** — renderPanel 이 이 자리보다 먼저 불릴 수 있어(이어서하기) const 는
TDZ 로 죽는다. 색은 토큰(var(--ai-*)·var(--fig-*))만 쓴다.
"""

CHROME_BAR = r"""
<style data-editor>
  /* 개체 위 막대(도식·차트·표) — 판형 v2 막대(.v2bar)와 같은 모양. 쪽 바깥 고정 층(패널 안 자식)에 둔다. */
  .obar { position: fixed; z-index: 103; display: flex; gap: 2px; align-items: center; padding: 3px;
    background: var(--ai-color-ink); border-radius: var(--ai-radius-sm);
    box-shadow: var(--ai-shadow-card); font: 12.5px/1.2 var(--ai-font-sans); }
  .panel .obar button { display: inline-flex; width: auto; margin: 0; padding: 5px 9px; text-align: center;
    border: 0; border-radius: 4px; background: transparent; color: var(--ai-color-white);
    font: inherit; white-space: nowrap; cursor: pointer; }
  .panel .obar button:hover, .panel .obar button:focus-visible, .panel .obar button[aria-expanded="true"] {
    background: var(--ai-color-signal); border-color: transparent; outline: none; }
  .panel .obar button[disabled] { opacity: .38; cursor: default; background: transparent; }
  .omenu { position: fixed; z-index: 104; min-width: 180px; max-width: 300px; padding: 4px;
    background: var(--ai-color-white); border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    box-shadow: var(--ai-shadow-card); font: 12.5px/1.35 var(--ai-font-sans); }
  .omenu[hidden] { display: none; }
  .panel .omenu button { display: flex; gap: 7px; align-items: center; width: 100%; margin: 0; border: 0;
    border-radius: 4px; background: transparent; padding: 7px 9px; text-align: left; font: inherit; }
  .panel .omenu button:hover, .panel .omenu button:focus-visible { background: var(--ai-color-signal-tint); outline: none; }
  .panel .omenu button[aria-checked="true"] { background: var(--ai-color-signal); color: var(--ai-color-white); }
  .panel .omenu button[disabled] { opacity: .4; cursor: default; }
  .panel .omenu button.danger { color: var(--ai-color-issue); background: transparent;
    border-top: 1px solid var(--ai-color-line); border-radius: 0 0 4px 4px; }
  .omenu .oseg { display: flex; gap: 3px; }
  .panel .omenu .oseg button { justify-content: center; border: 1px solid var(--ai-color-line); }
  .omenu .ohint { padding: 5px 9px 3px; font-size: 11.5px; color: var(--ai-color-muted); }
  .omenu .osw { width: 14px; height: 14px; flex: none; border-radius: 3px; border: 1px solid var(--ai-color-line); }
  .opop { position: fixed; z-index: 105; top: 58px; left: 50%; transform: translateX(-50%);
    width: min(640px, calc(100vw - 24px)); max-height: calc(100vh - 80px); overflow: auto; box-sizing: border-box;
    padding: 14px 16px; background: var(--ai-color-white); color: var(--ai-color-ink);
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-md); box-shadow: var(--ai-shadow-card);
    font: 13px/1.5 var(--ai-font-sans); }
  .opop h4 { margin: 0 0 8px; font-size: 13.5px; }
  .opop .osub { margin: 0 0 10px; font-size: 12px; color: var(--ai-color-muted); }
  .opop table { border-collapse: collapse; width: 100%; }
  .opop td { padding: 2px; }
  .panel .opop input { width: 100%; min-width: 48px; padding: 5px 7px; font: inherit; box-sizing: border-box;
    border: 1px solid var(--ai-color-line); border-radius: 4px; }
  .opop .orow { display: flex; gap: 6px; justify-content: flex-end; margin-top: 12px; flex-wrap: wrap; }
  .opop .orow.left { justify-content: flex-start; margin-top: 8px; }
  .panel .opop .orow button { display: inline-block; width: auto; margin: 0; }
  .panel .opop .orow button.good { background: var(--ai-color-ink); color: var(--ai-color-white); border-color: var(--ai-color-ink); }
  .opop .oset { margin: 10px 0 0; padding-top: 8px; border-top: 1px solid var(--ai-color-line); }
  /* 그림 바꾸기 — 올린 자료 속 그림 목록 카드(그림 P3 '26-09-30) */
  .opop .ocards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
  .panel .opop button.ocard { display: flex; flex-direction: column; align-items: stretch; gap: 4px; width: auto;
    margin: 0; padding: 6px; text-align: left; border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-white); color: var(--ai-color-ink); font: inherit; cursor: pointer; }
  .panel .opop button.ocard:hover, .panel .opop button.ocard:focus-visible { border-color: var(--ai-color-signal); outline: none; }
  .panel .opop button.ocard[aria-selected="true"] { border-color: var(--ai-color-signal); box-shadow: 0 0 0 2px var(--ai-color-signal); }
  .panel .opop button.ocard[disabled] { opacity: .45; cursor: default; }
  .opop .ocard img { width: 100%; height: 96px; object-fit: contain; background: var(--ai-color-signal-tint); border-radius: 3px; }
  .opop .ocard .ocap { font-size: 12px; font-weight: 700; line-height: 1.3; }
  .opop .ocard .ocsub { font-size: 11.5px; line-height: 1.35; color: var(--ai-color-muted);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
"""

SCRIPT_BAR = r"""
// ════ 개체 위 막대 — 도식·차트·표('26-09-29) — workspace/editor_bar.py 가 옛 편집 화면에 끼운다 ═════════
var 막대말 = { figstep: '＋ 항목 추가', figsize: '크기', figdata: '값 고치기', tablerow: '＋ 행·열 추가',
  tablesize: '크기', ai: 'AI로 고치기', imgswap: '바꾸기', imgsize: '크기', imgcrop: '자르기' };
var 막대더말 = { figtype: '모양…', color: '색…', figlabel: '글자 고치기…', edit: '글 고치기…',
  tablestyle: '표 모양…', tablecell: '칸 합치기·나누기…', tablecol: '행·열 빼기…', del: '삭제',
  imgcap: '캡션·설명 고치기…' };
var 차트형 = { bar: 1, hbar: 1, line: 1, donut: 1, stack: 1 };
var 계열차트 = ['bar', 'line', 'hbar'];            // 같은 데이터 꼴(시점·계열)끼리만 모양을 바꾼다
var 크기셋 = ['작게', '보통', '크게'];
var 도식색칩 = [['보조', '기본', 'var(--fig-soft)'], ['강조', '강조', 'var(--fig-accent)'],
  ['회색', '회색', 'var(--fig-gray)'], ['분야1', '분야 1', 'var(--fig-cat1-mid)'], ['분야2', '분야 2', 'var(--fig-cat2-mid)']];
var 표색칩 = [['', '없음', 'var(--ai-color-white)'], ['강조', '강조', 'var(--doc-table-hl-bg)'],
  ['회색', '회색', 'var(--doc-p-gray-soft)']];

function 차트인가(el) { return !!차트형[figSpec(el).type]; }
function 막대꼴(el, info) {
  const s = info.spec;
  if (info.type === '도식' && 차트인가(el) && s['차트막대']) return { 종류: '차트', 주: s['차트막대']['주'] || [], 더: s['차트막대']['더'] || [] };
  const m = s['막대'] || {};
  return { 종류: info.type === '도식' ? '도식' : info.type === '이미지' ? '그림' : '표', 주: m['주'] || [], 더: m['더'] || [] };
}
function 슬라이드안(el) { return !!(el.closest && el.closest('.sl-page')); }
function 막대할수있나(el, info, a) {            // [된다, 까닭]
  if (a === 'ai') return [플러그인 || 서버있음, ''];
  if (a === 'tablesize' && 슬라이드안(el)) return [false, '슬라이드는 판(레이아웃)이 표 크기를 정합니다'];
  if (a === 'imgsize' || a === 'imgcrop') {                     // 그림(P3) — 못 얻은 그림·슬라이드·AI 그림
    if (el.dataset.miss || !el.querySelector('img')) return [false, '그림이 들어오면 ' + (a === 'imgsize' ? '크기를 고를' : '자를') + ' 수 있습니다'];
    if (a === 'imgsize' && 슬라이드안(el)) return [false, '슬라이드는 판(레이아웃)이 그림 크기를 정합니다'];
    if (a === 'imgcrop' && imgSpec(el)['출처'] === '생성') return [false, 'AI로 만든 그림은 자르지 않습니다 — 바꾸기로 다른 그림을 고르세요'];
  }
  if (a === 'figtype') {
    const 차트 = 차트인가(el);
    if (차트 && !계열차트.includes(figSpec(el).type)) return [false, '이 차트는 모양을 바꿀 수 없습니다'];
    const 후보 = Object.keys(info.spec['유형'] || {}).filter(k => 차트 ? 계열차트.includes(k) : !차트형[k]);
    if (후보.length < 2) return [false, '바꿀 수 있는 모양이 없습니다'];
  }
  return [true, ''];
}
function 지금크기(el, info) {
  if (info.type === '이미지') return 그림단(imgSpec(el));
  if (info.type === '도식') {
    const v = figSpec(el)['크기'];
    return window.SVGFIG && window.SVGFIG.크기풀기 ? window.SVGFIG.크기풀기(v === '가득' ? '크게' : v) : '보통';
  }
  const tb = el.querySelector('table');
  return (tb && 크기셋.includes(tb.dataset.크기)) ? tb.dataset.크기 : '보통';
}
function 막대이름(a, el, info) {
  if (a === 'figsize' || a === 'tablesize' || a === 'imgsize') return '크기 · ' + 지금크기(el, info);
  if (a === 'imgswap' && el.dataset.miss) return '그림 고르기';
  return 막대말[a] || a;
}

// ── 막대 짓기 — 패널에는 이름·힌트만, 조작은 고른 개체 위 막대에 ──
function 막대패널(panel, el, info) {
  const 꼴 = 막대꼴(el, info);
  panel.insertAdjacentHTML('beforeend', '<div class="hint">조작은 고른 개체 위 막대에 있습니다.'
    + (꼴.종류 === '표' ? ' 칸을 누르면 그 칸이 합치기·열 넣기·칸 색의 기준이 됩니다.'
       : 꼴.종류 === '도식' ? ' 칸(라벨)을 누르면 그 칸이 색 바꾸기의 기준이 됩니다.'
       : 꼴.종류 === '그림' ? ' 바꾸기는 올린 자료에서 꺼낸 그림 목록에서 고릅니다.' : '') + '</div>');
  // 못 얻은 그림(P0 표식) — 까닭을 먼저 보인다. 산출물에는 이 자리가 빠진다
  if (꼴.종류 === '그림' && el.dataset.miss) {
    let 말 = ((el.querySelector('.ph') || {}).textContent || '').replace('[이미지 미확보] ', '');
    // ('26-09-30 Q5, verify_fixup4_ux V6) 고를 그림이 없는데 '그림을 바꾸거나'라고만 하면 할 수 없는 일을 시킨다 — 서랍이 비면
    // 지우기를 먼저, 바꾸기는 사진 파일·PDF 를 올린 뒤로 말한다(생성 그림 자리는 따로 — 그림을 넣는 쪽 말이 이미 맞다)
    if (!그림목록().length && imgSpec(el)['출처'] !== '생성')
      말 = '올린 자료에서 그림을 가져오지 못했습니다. 이 자리를 지우거나, 사진 파일·PDF를 올린 뒤 그림을 바꿔 주세요';
    panel.insertAdjacentHTML('beforeend', '<div class="hint">' + esc(말)
      + ' — 내보낸 문서(PDF·한글·발표 파일)에는 이 자리가 빠집니다.</div>');
  }
  const bar = document.createElement('div');
  bar.className = 'obar'; bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', info.label + ' 조작');
  bar.dataset.kind = 꼴.종류;
  const 메뉴들 = [];
  꼴.주.forEach(a => {
    const b = btn(막대이름(a, el, info), () => 막대누름(a, el, info, b));
    b.dataset.act = a;
    const [된다, 까닭] = 막대할수있나(el, info, a);
    if (!된다) { b.disabled = true; b.title = 까닭; }
    bar.appendChild(b);
    const m = 막대메뉴(a, el, info);
    if (m) { m.dataset.for = a; b.setAttribute('aria-haspopup', 'menu'); b.setAttribute('aria-expanded', 'false'); 메뉴들.push(m); }
  });
  if (꼴.더.length) {
    const mb = btn('⋯', () => 막대누름('more', el, info, mb));
    mb.dataset.act = 'more'; mb.title = '더 보기'; mb.setAttribute('aria-haspopup', 'menu'); mb.setAttribute('aria-expanded', 'false');
    bar.appendChild(mb);
    메뉴들.push(...더보기메뉴들(꼴, el, info));
  }
  bar.addEventListener('keydown', ev => {                    // 막대 안 방향키로 칸 옮기기(v2 막대와 같다)
    if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
    const bs = [...bar.querySelectorAll('button:not([disabled])')], k = bs.indexOf(document.activeElement);
    if (k < 0) return; ev.preventDefault();
    bs[(k + (ev.key === 'ArrowRight' ? 1 : bs.length - 1)) % bs.length].focus();
  });
  panel.appendChild(bar);
  메뉴들.forEach(m => { m.hidden = true; panel.appendChild(m); });
  막대자리(bar, el);
}
// 그 점에 고른 개체 밖의 **글자**가 있나 — 막대가 바로 위 장·절 제목을 가리던 것('26-09-29 fixup §4-4).
// caretRangeFromPoint 로 가장 가까운 글자 한 자의 네모를 재어, 점이 그 안에 들 때만 글 위로 본다.
function 글위인가(x, y, el) {
  const r = document.caretRangeFromPoint ? document.caretRangeFromPoint(x, y) : null;
  const t = r && r.startContainer;
  if (!t || t.nodeType !== 3 || el.contains(t) || (t.parentElement && t.parentElement.closest('.panel'))) return false;
  for (const k of [r.startOffset - 1, r.startOffset]) {
    if (k < 0 || k >= t.length || !/\S/.test(t.data[k])) continue;
    const g = document.createRange(); g.setStart(t, k); g.setEnd(t, k + 1);
    const b = g.getBoundingClientRect();
    if (x >= b.left - 1 && x <= b.right + 1 && y >= b.top - 1 && y <= b.bottom + 1) return true;
  }
  return false;
}
function 막대가림(el, top, left, w, h) {
  let n = 0;
  for (const fy of [0.2, 0.5, 0.8]) for (let i = 0; i < 7; i++)
    if (글위인가(left + 4 + (w - 8) * i / 6, top + h * fy, el)) n++;
  return n;
}
// 못 실은 그림 자리는 높이 0 이고 칩만 보인다 — 잇단 자리의 칩은 세로로 쌓인다(render_editor_any --mi). 막대를 그 자리 기준으로
// 놓으면 위 칩을 덮어 앞 자리를 누를 수 없었다('26-09-30 fixup4 U6). 잇단 칩 묶음 전체의 상자를 기준으로 놓는다.
function 못실은칩상자(el) {
  if (!el || !el.dataset || !el.dataset.miss) return null;
  const 못 = n => n && n.matches && n.matches('.fr-img[data-miss]');
  let 첫 = el;
  while (못(첫.previousElementSibling)) 첫 = 첫.previousElementSibling;
  let 상 = null;
  for (let n = 첫; 못(n); n = n.nextElementSibling) {
    const ph = n.querySelector(':scope > .ph');
    if (!ph) continue;
    const b = ph.getBoundingClientRect();
    상 = 상 ? { top: Math.min(상.top, b.top), bottom: Math.max(상.bottom, b.bottom), left: Math.min(상.left, b.left),
               right: Math.max(상.right, b.right) } : { top: b.top, bottom: b.bottom, left: b.left, right: b.right };
  }
  return 상;
}
function 막대자리(bar, el) {
  if (!bar || !el || !el.isConnected) return;
  const r = 못실은칩상자(el) || el.getBoundingClientRect(), h = bar.offsetHeight || 30, w = bar.offsetWidth || 240;
  const 왼 = x => Math.max(270, Math.min(x, window.innerWidth - w - 280));
  const 된다 = t => t >= 52 && t + h <= window.innerHeight - 8;
  // 자리 후보: 위·왼쪽(기본) → 위·오른쪽 → 위에서 옆으로 옮긴 자리(가운데 맞춘 장 제목을 비켜 가게 개체 양옆
  // 60px 까지) → 아래·왼쪽·오른쪽. 고른 개체 밖 글자를 가리지 않는 첫 자리, 없으면 가장 덜 가리는 자리를 쓴다.
  const 위 = r.top - h - 8, 아래 = r.bottom + 8, 옆 = [];
  for (let i = 0; i <= 8; i++) 옆.push(왼(r.left - 60 + (r.right - r.left - w + 120) * i / 8));
  옆.sort((a, b) => Math.abs(a - r.left) - Math.abs(b - r.left));
  const 후보 = [[위, 왼(r.left)], [위, 왼(r.right - w)], ...옆.map(l => [위, l]), [아래, 왼(r.left)], [아래, 왼(r.right - w)]]
    .filter(([t]) => 된다(t));
  let top, left;
  if (후보.length) {
    const 숨길 = [bar, ...document.querySelectorAll('.panel .omenu:not([hidden])')];
    숨길.forEach(x => { x.style.visibility = 'hidden'; });
    let 최소 = Infinity;
    for (const [t, l] of 후보) {
      const n = 막대가림(el, t, l, w, h);
      if (n < 최소) { 최소 = n; top = t; left = l; }
      if (n === 0) break;
    }
    숨길.forEach(x => { x.style.visibility = ''; });
  } else {
    top = r.top - h - 8;
    if (top < 52) top = Math.min(r.bottom + 8, window.innerHeight - h - 8);
    if (top < 52) top = 52;
    left = 왼(r.left);
  }
  bar.style.top = Math.round(top) + 'px'; bar.style.left = Math.round(left) + 'px';
  const m = document.querySelector('.panel .omenu:not([hidden])');
  if (m) {
    const 칸 = m.dataset.for && bar.querySelector('[data-act="' + (m.dataset.for.split(':')[0] === 'more' ? 'more' : m.dataset.for) + '"]');
    const x = 칸 ? 칸.getBoundingClientRect().left : left;
    m.style.top = Math.round(top + h + 4) + 'px';
    m.style.left = Math.round(Math.min(x, window.innerWidth - (m.offsetWidth || 200) - 8)) + 'px';
  }
}
var 막대자리틀 = 0;                                      // 스크롤마다 글자 재기를 한 번(화면 틀)으로 묶는다
function 막대다시자리() {
  if (막대자리틀) return;
  막대자리틀 = requestAnimationFrame(() => { 막대자리틀 = 0; 막대자리(document.querySelector('.panel .obar'), state.sel); });
}
window.addEventListener('scroll', 막대다시자리, true);
window.addEventListener('resize', 막대다시자리);
function 메뉴닫기() {
  document.querySelectorAll('.panel .omenu').forEach(m => { m.hidden = true; });
  document.querySelectorAll('.panel .obar [aria-expanded]').forEach(b => b.setAttribute('aria-expanded', 'false'));
}
function 메뉴열기(키) {
  const 옛 = document.querySelector('.panel .omenu:not([hidden])');
  const 같다 = 옛 && 옛.dataset.for === 키;
  메뉴닫기();
  if (같다) return;
  const m = document.querySelector('.panel .omenu[data-for="' + 키 + '"]');
  if (!m) return;
  if (typeof m._짓기 === 'function') m._짓기();
  m.hidden = false;
  const b = document.querySelector('.panel .obar [data-act="' + (키.startsWith('more') ? 'more' : 키) + '"]');
  if (b) b.setAttribute('aria-expanded', 'true');
  막대자리(document.querySelector('.panel .obar'), state.sel);   // 곧바로(한 틀 늦으면 메뉴가 엉뚱한 곳에 한 번 뜬다)
  const 첫 = m.querySelector('button:not([disabled])'); if (첫) 첫.focus();
}
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const p = document.querySelector('.panel .opop');
  if (p) { p.remove(); e.preventDefault(); return; }
  if (document.querySelector('.panel .omenu:not([hidden])')) { 메뉴닫기(); e.preventDefault(); }
});
document.addEventListener('mousedown', e => {           // 막대·메뉴 바깥을 누르면 메뉴를 닫는다
  if (!e.target.closest('.panel .obar, .panel .omenu, .panel .opop')) 메뉴닫기();
}, true);

function 막대누름(a, el, info, b) {
  if (a === 'ai') { 메뉴닫기(); if (플러그인) return addNote(el, info); if (서버있음) return ai다시쓰기(el, info); return; }
  if (a === 'figstep') { 메뉴닫기(); return 도식항목넣기(el); }
  if (a === 'figdata') { 메뉴닫기(); return 차트값판(el, info); }
  if (a === 'imgswap') { 메뉴닫기(); return 그림서랍(el, info); }
  if (a === 'imgcrop') { 메뉴닫기(); return 자르기시작(el); }
  if (a === 'more') return 메뉴열기('more');
  return 메뉴열기(a);                                   // figsize·tablesize·tablerow — 작은 메뉴
}
function 메뉴(말) {
  const m = document.createElement('div'); m.className = 'omenu'; m.setAttribute('role', 'menu');
  if (말) m.setAttribute('aria-label', 말);
  return m;
}
function 메뉴단추(m, 말, f, 반) {
  const b = btn(말, () => { 메뉴닫기(); f(); }, 반);
  b.setAttribute('role', 'menuitem'); m.appendChild(b); return b;
}
function 막대메뉴(a, el, info) {
  if (a === 'imgsize') {
    const m = 메뉴('그림 크기');
    m.insertAdjacentHTML('beforeend', '<div class="ohint">작게 약 80mm · 보통 약 130mm · 크게 전폭'
      + (document.documentElement.dataset.genre === 'fullreport' ? ' — 작게 둘이 이웃하면 나란히 놓습니다' : '') + '</div>');
    const seg = document.createElement('div'); seg.className = 'oseg'; seg.setAttribute('role', 'radiogroup');
    const 지금 = 지금크기(el, info);
    크기셋.forEach(v => {
      const b = btn(v, () => { 메뉴닫기(); 그림크기(el, v); });
      b.setAttribute('role', 'menuitemradio'); b.setAttribute('aria-checked', String(v === 지금));
      seg.appendChild(b);
    });
    m.appendChild(seg);
    return m;
  }
  if (a === 'figsize' || a === 'tablesize') {
    const m = 메뉴(a === 'figsize' ? '도식 크기' : '표 크기');
    m.insertAdjacentHTML('beforeend', '<div class="ohint">' + (a === 'figsize'
      ? '크게는 글자와 면적을 함께 키웁니다' : '표 글자를 한 단계 줄이거나 키웁니다(폭은 늘 전폭)') + '</div>');
    const seg = document.createElement('div'); seg.className = 'oseg'; seg.setAttribute('role', 'radiogroup');
    const 지금 = 지금크기(el, info);
    크기셋.forEach(v => {
      const b = btn(v, () => { 메뉴닫기(); a === 'figsize' ? 도식크기(el, v) : 표크기(el, v); });
      b.setAttribute('role', 'menuitemradio'); b.setAttribute('aria-checked', String(v === 지금));
      seg.appendChild(b);
    });
    m.appendChild(seg);
    return m;
  }
  if (a === 'tablerow') {
    const m = 메뉴('행·열 추가');
    메뉴단추(m, '＋ 행 추가', () => 표행넣기(el));
    메뉴단추(m, '＋ 오른쪽에 열', () => 열넣기(el));
    m.insertAdjacentHTML('beforeend', '<div class="ohint">열은 누른 칸의 오른쪽에 넣습니다</div>');
    return m;
  }
  return null;
}
function 더보기메뉴들(꼴, el, info) {
  const 밖 = [];
  const m = 메뉴('더 보기'); m.dataset.for = 'more'; 밖.push(m);
  const 하위 = (키, 말, 짓기) => {                      // ⋯ 안의 하위 메뉴 — ⋯ 자리에 바꿔 연다
    const s = 메뉴(말); s.dataset.for = 'more:' + 키;
    // 열 때마다 다시 짓는다(누른 칸·지금 값이 바뀌었을 수 있다). 처음에도 지어 두어 단추 이름·차례가 늘 있다
    s._짓기 = () => {
      s.textContent = '';
      const 뒤 = btn('‹ ' + 말.replace(/…$/, ''), () => 메뉴열기('more')); 뒤.setAttribute('role', 'menuitem');
      뒤.style.fontWeight = '700'; s.appendChild(뒤);
      짓기(s);
    };
    s._짓기(); 밖.push(s);
    const b = btn(말, () => 메뉴열기('more:' + 키)); b.setAttribute('role', 'menuitem'); b.dataset.act = 키;
    m.appendChild(b);
    return b;
  };
  꼴.더.filter(a => a !== 'del').forEach(a => {
    const [된다, 까닭] = 막대할수있나(el, info, a);
    if (a === 'figtype') {
      const b = 하위('figtype', 막대더말.figtype, s => 유형메뉴(s, el, info));
      if (!된다) { b.disabled = true; b.title = 까닭; }
    } else if (a === 'color') 하위('color', 막대더말.color, s => (info.type === '도식' ? 도식색메뉴(s, el) : 표색메뉴(s, el)));
    else if (a === 'figlabel') 하위('figlabel', 막대더말.figlabel, s => 글자메뉴(s, el));
    else if (a === 'edit') {
      if (info.type === '도식') 하위('edit', '캡션·설명 고치기…', s => {
        메뉴단추(s, '✏ 캡션 수정', () => 도식글고치기(el, '.cap', 'caption'));
        메뉴단추(s, '✏ 그림 밑 설명(※) 수정', () => 도식글고치기(el, '.note', 'note'));
      });
      else 메뉴단추(m, '✏ 셀 직접 수정', () => editText(el.querySelector('table')));
    }
    else if (a === 'figdrop') 메뉴단추(m, '－ 마지막 항목 빼기', () => 도식항목빼기(el));
    else if (a === 'tablestyle') 하위('tablestyle', 막대더말.tablestyle, s => 표모양메뉴(s, el, info));
    else if (a === 'tablecell') 하위('tablecell', 막대더말.tablecell, s => {
      메뉴단추(s, '→ 합치기', () => 칸합치기(el, '오른쪽'));
      메뉴단추(s, '↓ 합치기', () => 칸합치기(el, '아래'));
      메뉴단추(s, '나누기', () => 칸나누기(el));
      s.insertAdjacentHTML('beforeend', '<div class="ohint">누른 칸을 기준으로 합니다</div>');
    });
    else if (a === 'tablecol') 하위('tablecol', 막대더말.tablecol, s => {
      메뉴단추(s, '－ 마지막 행 빼기', () => 표행빼기(el));
      메뉴단추(s, '－ 이 열 빼기', () => 열빼기(el));
      s.insertAdjacentHTML('beforeend', '<div class="ohint">열은 누른 칸의 열을 뺍니다</div>');
    });
    else if (a === 'imgcap') 하위('imgcap', 막대더말.imgcap, s => {
      메뉴단추(s, '✏ 캡션(그림 제목) 고치기', () => 그림글고치기(el, '캡션'));
      메뉴단추(s, '✏ 그림 밑 설명(※) 고치기', () => 그림글고치기(el, '함의'));
    });
    else if (a === 'ai') {                                   // 그림 ⋯ 의 AI — 캡션만 고친다(render_editor_any _ai대상)
      const b = 메뉴단추(m, 'AI로 고치기(캡션)', () => 막대누름('ai', el, info));
      if (!된다) { b.disabled = true; b.title = 까닭; }
      else if (!el.querySelector('.cap')) { b.disabled = true; b.title = '캡션이 없습니다 — 캡션을 먼저 넣으세요'; }
    }
  });
  if (꼴.종류 === '그림') m.insertAdjacentHTML('afterbegin', '<div class="ohint">' + esc(그림출처말(el)) + '</div>');
  if (꼴.더.includes('del')) 메뉴단추(m, '🗑 ' + (info.spec['라벨'] || info.type) + ' 삭제', () => delEl(el, info), 'danger');
  return 밖;
}

// ── 크기 — 누르면 바로 다시 그리고, 쪽 게이트가 넘치면 되돌리고 까닭을 알린다 ──
function 쪽재기(el) {
  const o = {};
  const 장르 = document.documentElement.dataset.genre;
  const sh = 장르 === 'onepage' && document.querySelector('.sheet');   // build/audit.js AUDIT_SPEC.onepage 지면
  if (sh) o.mm = sh.scrollHeight / 96 * 25.4;
  if (typeof window.__repaginate === 'function') { window.__repaginate(); o.over = (window.__frOverflow || []).length; }
  // 도식 높이 상한 — SVG 는 svg.fig-over, 격자(표)는 줄여 맞추면 data-fig-fit(실제 단), 못 맞추면 .fig-over
  o.fig = !!(el && (el.querySelector('svg.fig-over, table.fig-over') || el.classList.contains('fig-over')));
  o.fit = (el && el.dataset && el.dataset.figFit) || '';
  const 장 = el && el.closest && el.closest('.sl-page');
  if (장) o.sl = 장.scrollHeight - 장.clientHeight;
  return o;
}
function 쪽게이트(el, 적용, 되돌림) {
  const 전 = 쪽재기(el);
  적용();
  const 후 = 쪽재기(el);
  let 까닭 = '';
  if (후.mm !== undefined && 후.mm > 297.5 && 후.mm > (전.mm || 0) + 0.3)
    까닭 = '한 쪽을 넘게 돼 적용하지 않았습니다 — 1페이지 보고서는 한 쪽 안에 들어야 합니다';
  else if ((후.fig && !전.fig) || (후.fit && 후.fit !== 전.fit))
    까닭 = '도식이 한 쪽 높이를 넘게 돼 적용하지 않았습니다 — 항목을 줄이거나 보통으로 두세요';
  else if ((후.over || 0) > (전.over || 0))
    까닭 = '쪽 밖으로 넘치는 곳이 생겨 적용하지 않았습니다';
  else if (후.sl !== undefined && 후.sl > 4 && 후.sl > (전.sl || 0) + 1)
    까닭 = '장 밖으로 넘치게 돼 적용하지 않았습니다';
  if (까닭) { 되돌림(); if (typeof window.__repaginate === 'function') window.__repaginate(); }
  return 까닭;
}
var 크기되돌림 = null;                                   // { 글, fn } — 되돌리기 토스트가 떠 있는 동안만 Cmd+Z
var 크기뒤편집 = false;                                  // 크기를 바꾼 뒤 문서 글을 고쳤나(패널 입력칸은 빼고)
function 크기토스트(말, fn) {
  되돌리기토스트(말, fn);
  // 앞: 이 크기 조작까지 쌓인 조작들 — 그 뒤에 온 조작만 '다른 편집'으로 센다(앞서 한 모양 바꾸기의
  // 저장 응답이 늦게 와도 방금 바꾼 크기의 되돌리기를 거두지 않게)
  크기되돌림 = { 글: note.textContent, fn, 앞: new Set(state.ops) }; 크기뒤편집 = false;
}
// 크기 바꾸기가 **마지막 조작**일 때만 — 그 뒤에 다른 조작(라벨·항목·표 칸…)이 쌓였거나 문서 글을 고쳤으면
// 토스트가 아직 떠 있어도 Cmd+Z 로 크기를 되돌리지 않는다. 저장 응답을 기다리면 그 사이(1~3초)에 누른
// Cmd+Z 가 방금 고친 라벨이 아니라 몇 초 전 크기를 되돌렸다(실입력 재현: 크기 → 라벨 고침 → Cmd+Z).
function 크기토스트떠있나() {
  if (!크기되돌림 || note.style.display !== 'block' || note.textContent !== 크기되돌림.글 || 크기뒤편집) return false;
  const 앞 = 크기되돌림.앞;
  return !state.ops.some(o => o && !앞.has(o) && o.action !== '도식 크기' && o.action !== '표 크기' && o.action !== '그림 크기');
}
document.addEventListener('input', e => {
  if (!(e.target && e.target.closest && e.target.closest('.panel'))) 크기뒤편집 = true;
}, true);
// 저장 응답 뒤(저장뒤비우기 가 부른다) — 크기를 바꾼 뒤 다른 편집(글 입력·다른 조작)이 문서에 저장되면
// 크기 되돌리기를 거둔다. 모양 되돌리기(편집기 2단계 F4)와 같은 규칙: 그 뒤엔 토스트·단축키 어느 쪽으로도
// 옛 크기가 안 돌아온다.
function 크기기록_저장뒤(snap) {
  if (!크기되돌림) return;
  const 앞 = 크기되돌림.앞;
  const 다른op = (snap.ops || []).some(o => o && !앞.has(o) && o.action !== '도식 크기' && o.action !== '표 크기' && o.action !== '그림 크기');
  if (!(크기뒤편집 || 다른op)) return;
  const 떠있다 = note.style.display === 'block' && note.textContent === 크기되돌림.글;
  크기되돌림 = null; 크기뒤편집 = false;
  if (떠있다) note.style.display = 'none';
}
// 잡기 단계(capture)에서 받는다 — 문서 설정 창이 열려 있어도 모양 되돌리기와 겹쳐 두 번 되돌리지 않게,
// 크기 토스트가 떠 있으면(가장 최근 조작) 크기만 되돌리고 멈춘다.
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.isComposing || e.keyCode === 229) return;
  if ((e.key || '').toLowerCase() !== 'z') return;
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
  if (!크기토스트떠있나()) return;
  const f = 크기되돌림.fn; 크기되돌림 = null; note.style.display = 'none';
  e.preventDefault(); e.stopImmediatePropagation(); f();
}, true);
function 크기걸기_도식(el, v) {
  const s2 = figSpec(el); if (v !== '보통') s2['크기'] = v; else delete s2['크기'];
  setFigSpec(el, s2);
  delete el.dataset.크기;                    // 옛 슬라이드 속성(크게·가득 CSS)은 새 도식에 안 먹는다
  window.SVGFIG.mount(el);
}
function 도식크기(el, v) {
  const 전 = 지금크기(el, entInfo(el) || { type: '도식' });
  if (전 === v || !window.SVGFIG) { select(el); return; }
  // 짝 차트(반폭 둘)는 하나의 크기가 옆 차트 배치를 함께 바꾼다 — 옆이 말없이 바뀌지 않게 토스트에 적는다(적대 검토 L4)
  const 짝들 = () => [...((el.parentNode && el.parentNode.children) || [])].filter(x => x !== el && x.classList.contains('fr-fig'))
    .map(x => x.classList.contains('fig-pair-l') ? 'l' : x.classList.contains('fig-pair-r') ? 'r' : '').join();
  const 짝전 = 짝들();
  const 까닭 = 쪽게이트(el, () => 크기걸기_도식(el, v), () => 크기걸기_도식(el, 전));
  if (까닭) { toast('크기를 ' + v + 로(v) + ' 바꾸면 ' + 까닭, 4200); select(el); return; }
  state.ops.push({ action: '도식 크기', to: v }); save(); repaginate(); select(el);
  // 한 쪽에 못 담아 쪽을 나눠 실었으면(판정 ⑧ — 사람이 고른 크기 그대로) 그렇다고 적는다
  const 나눔말 = el.dataset.figSplit === '1' ? ' — 한 쪽을 넘어 다음 쪽으로 나눠 이어 그렸습니다' : '';
  크기토스트('도식 크기를 ' + v + 로(v) + ' 바꿨습니다' + (짝들() !== 짝전 ? ' — 옆 차트의 나란히 배치도 바뀌었습니다' : '') + 나눔말, () => {
    if (!el.isConnected) return;
    크기걸기_도식(el, 전); state.ops.push({ action: '도식 크기', to: 전 }); save(); repaginate(); select(el);
    toast('도식 크기를 ' + 전 + 로(전) + ' 되돌렸습니다', 2400);
  });
}
function 크기걸기_표(el, v) {
  const tb = el.querySelector('table'); if (!tb) return;
  if (v === '보통') delete tb.dataset.크기; else tb.dataset.크기 = v;
}
function 표크기(el, v) {
  const 전 = 지금크기(el, { type: '표' });
  if (전 === v) { select(el); return; }
  const 까닭 = 쪽게이트(el, () => 크기걸기_표(el, v), () => 크기걸기_표(el, 전));
  if (까닭) { toast('크기를 ' + v + 로(v) + ' 바꾸면 ' + 까닭, 4200); select(el); return; }
  state.ops.push({ action: '표 크기', to: v }); save(); repaginate(); select(el);
  크기토스트('표 크기를 ' + v + 로(v) + ' 바꿨습니다', () => {
    if (!el.isConnected) return;
    크기걸기_표(el, 전); state.ops.push({ action: '표 크기', to: 전 }); save(); repaginate(); select(el);
    toast('표 크기를 ' + 전 + 로(전) + ' 되돌렸습니다', 2400);
  });
}

// ── 그림(이미지) — 바꾸기(목록 카드)·크기 세 단·짝·캡션('26-09-30 그림 P3, r2/img design §7) ─────────────
// 막대 [바꾸기 | 크기 | 자르기 | ⋯]. 바꾸기는 render_editor_any 가 굽는 순간 심은 목록 카드(#img-cards — 올린 자료에서
// 시스템이 꺼낸 그림, 미리보기는 data:)에서 고른다. 스펙에는 "그림":"img-…" id 만 남기고 경로·좌표는 쓰지 않는다 —
// 저장하면 조립이 카드 그림을 다시 자른다(imageasset.extract). 크기 세 단의 값은 imageasset._표시폭 과 같다.
var 그림폭 = { 작게: '80mm', 보통: '130mm', 크게: '100%' };
var 그림목록판 = null;
function 그림목록() {
  if (그림목록판) return 그림목록판;
  try { const n = document.getElementById('img-cards'); 그림목록판 = n ? JSON.parse(n.textContent) : []; }
  catch (e) { 그림목록판 = []; }
  return 그림목록판;
}
function 그림단(sp) {                                    // imageasset.크기접기 와 같은 규칙(옛 폭 % 는 가까운 단)
  if (sp && 크기셋.includes(sp['크기'])) return sp['크기'];
  const m = /^\s*(\d+(?:\.\d+)?)\s*%\s*$/.exec(String((sp && sp['폭']) || '80%'));
  if (!m) return '보통';
  const v = parseFloat(m[1]);
  return v <= 50 ? '작게' : v <= 85 ? '보통' : '크게';
}
function 그림출처말(el) {
  const sp = imgSpec(el);
  if (sp['출처'] === '생성') return 'AI로 만든 그림입니다 — 내보낸 문서에도 AI 생성물 표기가 붙습니다';
  const c = sp['그림'] && 그림목록().find(x => x.id === sp['그림']);
  if (c) return '올린 자료: ' + c['자리'] + ' · ' + c['종류'];
  if (sp['그림']) return '올린 자료 그림 ' + sp['그림'];
  if (sp['파일']) return '올린 자료: ' + sp['파일'] + (sp['쪽'] ? ' ' + sp['쪽'] + '쪽' : '');
  return '어디서 온 그림인지 적혀 있지 않습니다';
}
// imageasset.그림짝 과 같은 규칙 — 풀버전 한 절 안에서 이웃한(못 얻은 그림은 건너뜀) '작게' 둘을 나란히
function 그림짝다시() {
  if (document.documentElement.dataset.genre !== 'fullreport') return;
  let run = [], 앞절 = null;
  const 끊기 = () => {
    for (let k = 0; k + 1 < run.length; k += 2) {
      run[k].classList.add('fig-pair', 'fig-pair-l'); run[k + 1].classList.add('fig-pair', 'fig-pair-r'); }
    run = [];
  };
  document.querySelectorAll('.fr-img[data-path]').forEach(x => {
    x.classList.remove('fig-pair', 'fig-pair-l', 'fig-pair-r');
    if (x.dataset.miss) return;
    const 절 = x.dataset.path.replace(/\.이미지\.\d+$/, '');
    if (절 !== 앞절) 끊기();
    앞절 = 절;
    if (imgSpec(x)['크기'] === '작게') run.push(x); else 끊기();
  });
  끊기();
}
function 그림크기걸기(el, v) {
  const sp = imgSpec(el);
  // 숫자 꼴 옛 '크기'(생성 해상도 1024x1024)는 '비율'로 옮긴다 — 생성 요청 id 가 바뀌지 않게(imageasset._해상도)
  if (sp['크기'] && !크기셋.includes(sp['크기']) && !sp['비율']) sp['비율'] = sp['크기'];
  sp['크기'] = v; delete sp['폭'];
  imgSave(el, sp);
  const img = el.querySelector('img');
  if (img) { img.style.width = 그림폭[v]; img.style.maxWidth = '100%'; }
  그림짝다시();
}
function 그림크기(el, v) {
  const 전 = 지금크기(el, { type: '이미지' });
  if (전 === v) { select(el); return; }
  const 원 = el.dataset.img, img = el.querySelector('img'), 원꼴 = img ? img.getAttribute('style') : null;
  const 되돌 = () => {
    el.dataset.img = 원;
    if (img) { if (원꼴 === null) img.removeAttribute('style'); else img.setAttribute('style', 원꼴); }
    그림짝다시();
  };
  const 까닭 = 쪽게이트(el, () => 그림크기걸기(el, v), 되돌);
  if (까닭) { toast('크기를 ' + v + 로(v) + ' 바꾸면 ' + 까닭, 4200); select(el); return; }
  state.ops.push({ action: '그림 크기', to: v }); save(); repaginate(); select(el);
  const 짝 = el.classList.contains('fig-pair') ? ' — 이웃한 작은 그림과 나란히 놓았습니다' : '';
  크기토스트('그림 크기를 ' + v + 로(v) + ' 바꿨습니다' + 짝, () => {
    if (!el.isConnected) return;
    되돌(); state.ops.push({ action: '그림 크기', to: 전 }); save(); repaginate(); select(el);
    toast('그림 크기를 ' + 전 + 로(전) + ' 되돌렸습니다', 2400);
  });
}
// 스펙의 캡션·함의·AI 표기로 그림 둘레 글을 다시 짓는다 — imageasset.render 와 같은 차례(캡션 위 · 그림 · 배지 ·
// 보도자료 사진 설명 · ※함의). 보도자료 붙임 사진(.pr-photo)은 설명을 사진 아래 꺾쇠 없이 둔다.
function 그림글다시(el) {
  const sp = imgSpec(el), 아래 = el.classList.contains('pr-photo');
  el.querySelectorAll(':scope > .cap, :scope > .note, :scope > .ai-gen').forEach(x => x.remove());
  const img = el.querySelector('img'); if (!img) return;
  const 앞 = img.closest('.crop-wrap') || img;
  const 새 = (cls, t) => { const d = document.createElement('div'); d.className = cls; d.textContent = t; return d; };
  let 끝 = 앞;
  const 뒤에 = x => { 끝.after(x); 끝 = x; };
  if (sp['캡션'] && !아래) 앞.before(새('cap', '< ' + sp['캡션'] + ' >'));
  if (sp['출처'] === '생성') 뒤에(새('ai-gen', '🅰 AI 생성물'));
  if (sp['캡션'] && 아래) 뒤에(새('cap cap-below', sp['캡션']));
  const 노트 = sp['함의'] || sp['설명'];
  if (노트) 뒤에(새('note', 노트));
}
function 그림글고치기(el, 키) {
  const sp = imgSpec(el);
  const 말 = 키 === '캡션' ? (el.classList.contains('pr-photo') ? '사진 설명 (사진 아래 한 줄)' : '그림 제목 (< > 안에 들어갑니다)')
    : '이 그림에서 읽어야 할 것 (※ 로 붙습니다)';
  줄고치기(말, 키 === '캡션' ? (sp['캡션'] || '') : (sp['함의'] || sp['설명'] || ''), v => {
    const s2 = imgSpec(el);
    if (v) s2[키] = v; else delete s2[키];
    if (키 === '함의') delete s2['설명'];                  // 옛 '설명'(함의 폴백)은 함의 하나로 모은다
    imgSave(el, s2); 그림글다시(el);
    state.ops.push({ action: 키 === '캡션' ? '그림 제목' : '그림 설명' }); repaginate(); save(); select(el);
  });
}
function 그림서랍(el, info) {
  const 목록 = 그림목록(), sp = imgSpec(el);
  const 공개 = ['press-release', 'slides'].includes(document.documentElement.dataset.genre);
  const p = 작은판(el.dataset.miss ? '그림 고르기' : '그림 바꾸기', 목록.length
    ? '올린 자료에서 꺼낸 그림입니다. 누르면 바로 바뀌고, 5초 안에 되돌릴 수 있습니다.' : '');
  // ('26-09-30 fixup4 P2) 한글·워드 문서 속 사진은 쓰지 않는다 — 확인할것·파일읽기와 같은 한 줄(#img-cards-note)을 보인다.
  // 전에는 사진이 든 한글 문서를 이미 올린 사람에게도 사진 든 자료를 올려 달라고만 해 앞뒤가 맞지 않았다(verify_fixup3_ux U1)
  let 문서사진알림 = '';
  try { const n = document.getElementById('img-cards-note'); 문서사진알림 = n ? String(JSON.parse(n.textContent) || '') : ''; }
  catch (e) { 문서사진알림 = ''; }
  const 알림칸 = t => { const q = document.createElement('p'); q.className = 'osub'; q.textContent = t; p.appendChild(q); };
  if (!목록.length)
    알림칸(문서사진알림 || '올린 자료에 쓸 수 있는 그림이 없습니다. 사진 파일(PNG·JPG)이나 PDF를 올린 뒤 편집기를 다시 열어 주세요.');
  else if (문서사진알림) 알림칸(문서사진알림);
  const 판 = document.createElement('div'); 판.className = 'ocards'; 판.setAttribute('role', 'listbox');
  판.setAttribute('aria-label', '올린 자료 속 그림');
  목록.forEach(c => {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'ocard'; b.dataset.id = c.id;
    b.setAttribute('role', 'option'); b.setAttribute('aria-selected', String(c.id === sp['그림']));
    const 막음 = 공개 && c['비밀표지'];
    const im = document.createElement('img'); im.alt = ''; im.src = c.src; b.appendChild(im);
    const t = document.createElement('span'); t.className = 'ocap'; t.textContent = c['자리'] + ' · ' + c['종류']; b.appendChild(t);
    const s = document.createElement('span'); s.className = 'ocsub';
    s.textContent = 막음 ? "비밀 표지 '" + c['비밀표지'] + "' — 공개 문서에는 쓰지 않습니다"
      : c['비밀표지'] ? "비밀 표지 '" + c['비밀표지'] + "'가 붙은 자료의 그림입니다" : (c['곁글'] || '곁 글 없음');
    b.appendChild(s);
    if (막음) { b.disabled = true; b.title = s.textContent; }
    b.onclick = () => { p.remove(); 그림바꾸기(el, c); };
    판.appendChild(b);
  });
  p.appendChild(판);
  const r = document.createElement('div'); r.className = 'orow';
  r.appendChild(btn('닫기', () => p.remove())); p.appendChild(r);
  const 첫 = 판.querySelector('button[aria-selected="true"]:not([disabled])') || 판.querySelector('button:not([disabled])');
  if (첫) 첫.focus();
}
function 그림바꾸기(el, c) {
  const 잡 = 되돌림잡기(el);
  const sp = imgSpec(el);
  // 옛 경로·좌표·생성 칸은 지운다 — 모델·사람 모두 id 로만 고른다(주관 판정 '26-09-29). 표시 크기·캡션은 둔다
  ['파일', '쪽', 'index', '자를곳', '크롭', 'dpi', '출처', '프롬프트', '원프롬프트', '비율', '제공자', '이름', '실사']
    .forEach(k => { delete sp[k]; });
  if (sp['크기'] && !크기셋.includes(sp['크기'])) delete sp['크기'];
  sp['그림'] = c.id;
  imgSave(el, sp);
  if (el.dataset.miss) {                                     // 못 얻은 그림 자리 — 표식을 걷고 그림을 세운다
    el.removeAttribute('data-miss'); el.removeAttribute('hidden');
    el.querySelectorAll(':scope > .ph').forEach(x => x.remove());
  }
  el.removeAttribute('data-gen');
  let img = el.querySelector('img');
  if (!img) {
    img = document.createElement('img'); el.appendChild(img);
    img.style.width = 크기셋.includes(sp['크기']) ? 그림폭[sp['크기']] : String(sp['폭'] || '80%');
    img.style.maxWidth = '100%';
  }
  img.src = c.src; img.alt = sp['대체텍스트'] || sp['캡션'] || '';
  el.dataset.shownCrop = '[]';                               // 보이는 그림 = 카드 전체(자르기 합성의 기준)
  그림글다시(el); 그림짝다시();
  state.ops.push({ action: '그림 바꾸기', to: c.id });
  repaginate(); save(); select(el);
  되돌림걸기(잡, '그림을 바꿨습니다');
}

// ── 도식 항목 넣기·빼기 · 모양 · 글자 · 캡션 ──
function 도식다시(el, op) {
  window.SVGFIG.mount(el); if (op) state.ops.push(op); repaginate(); select(el);
}
function 도식항목넣기(el) {
  const s2 = figSpec(el);
  if (s2.type === 'compare') {               // 비교판은 현행·개선 두 판에 한 줄씩
    ['전', '후'].forEach(k => { if (!Array.isArray(s2[k])) s2[k] = []; s2[k].push('새 항목'); });
  } else {
    const arr = 도식배열(s2);
    if (!Array.isArray(arr)) { toast('이 도식은 항목을 더할 자리가 없습니다'); return; }
    arr.push(s2.type === 'strategy' ? { 제목: '새 전략', 과제: ['새 과제'] } : '새 항목');
  }
  setFigSpec(el, s2); 도식다시(el, { action: '도식 항목 추가' });
}
function 도식항목빼기(el) {
  const s2 = figSpec(el);
  if (s2.type === 'compare') {               // 긴 쪽의 끝 줄을 뺀다(두 판에 한 줄씩은 남긴다)
    const a = Array.isArray(s2['전']) ? s2['전'] : [], b = Array.isArray(s2['후']) ? s2['후'] : [];
    const n = Math.max(a.length, b.length);
    if (n <= 1) { toast('한 줄은 남겨야 합니다'); return; }
    if (a.length === n) a.pop();
    if (b.length === n) b.pop();
  } else {
    const arr = 도식배열(s2);
    if (!Array.isArray(arr) || arr.length <= 2) { toast('항목이 둘 남으면 더 뺄 수 없습니다'); return; }
    arr.pop();
  }
  const 잡 = 되돌림잡기(el);
  setFigSpec(el, s2); 도식다시(el, { action: '도식 항목 삭제' });
  되돌림걸기(잡, '마지막 항목을 뺐습니다');
}
function 유형메뉴(s, el, info) {
  const 지금 = figSpec(el).type, 차트 = 차트인가(el);
  Object.entries(info.spec['유형'] || {}).forEach(([k, v]) => {
    if (차트 ? !계열차트.includes(k) : !!차트형[k]) return;     // 도식은 도식끼리, 차트는 같은 데이터 꼴끼리
    const b = 메뉴단추(s, v, () => 유형바꾸기(el, k, v));
    b.setAttribute('role', 'menuitemradio'); b.setAttribute('aria-checked', String(k === 지금));
  });
}
function 유형바꾸기(el, k, v) {
  const s2 = figSpec(el);
  // 비교판(전[]·후[])만 배열 이름이 둘이다 — 오갈 때 글을 옮긴다(원래 배열은 지우지 않아 되돌리면 산다)
  const 글만 = x => (x && typeof x === 'object') ? String(x['라벨'] ?? x['제목'] ?? x['이름'] ?? '') : String(x ?? '');
  if (k === 'compare' && !Array.isArray(s2['전']) && !Array.isArray(s2['후'])) {
    const a = 도식배열(s2); if (Array.isArray(a)) { s2['전'] = a.map(글만); s2['후'] = []; }
  } else if (s2.type === 'compare' && k !== 'compare') {
    const 키 = { process: '단계', cycle: '단계', converge: '요건', relation: '노드' }[k];
    if (키 && !Array.isArray(s2[키])) s2[키] = [...(s2['전'] || []), ...(s2['후'] || [])].map(글만);
  }
  const 잡 = 되돌림잡기(el);
  s2.type = k; setFigSpec(el, s2);
  도식다시(el, { action: '도식 유형', to: v });
  되돌림걸기(잡, '모양을 ' + v + 로(v) + ' 바꿨습니다');
}
function 글자메뉴(s, el) {
  const setters = figSetters(figSpec(el));
  figLabels(el).forEach((t, i) => {
    if (!setters[i]) return;
    메뉴단추(s, '✏ ' + (svgLabelText(t).slice(0, 14) || '(빈 라벨)'), () => 라벨판(el, i));
  });
}
function 작은판(제목, 부제) {
  const 옛 = document.querySelector('.panel .opop'); if (옛) 옛.remove();
  const p = document.createElement('div'); p.className = 'opop'; p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', 제목);
  p.innerHTML = '<h4>' + esc(제목) + '</h4>' + (부제 ? '<p class="osub">' + esc(부제) + '</p>' : '');
  document.querySelector('.panel').appendChild(p);
  return p;
}
function 판단추(p, 적용말, 적용) {
  const r = document.createElement('div'); r.className = 'orow';
  r.appendChild(btn('취소', () => p.remove()));
  r.appendChild(btn(적용말 || '적용', () => { if (적용() !== false) p.remove(); }, 'good'));
  p.appendChild(r);
}
function 라벨판(el, i) {
  const t = figLabels(el)[i]; if (!t) return;
  const p = 작은판('라벨 수정', '고치면 바로 다시 그립니다');
  const inp = document.createElement('input'); inp.type = 'text'; inp.value = svgLabelText(t);
  p.appendChild(inp);
  판단추(p, '적용', () => {
    const s2 = figSpec(el); const S = figSetters(s2);
    if (!S[i]) return;
    S[i](inp.value); setFigSpec(el, s2); 도식다시(el, { action: '도식 라벨' });
  });
  inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); p.querySelector('.orow .good').click(); } });
  setTimeout(() => inp.select(), 30);
}
function 도식글고치기(el, 선택, 키) {
  const n = el.querySelector(선택);
  if (n) { editText(n, () => { syncFigSpec(el); window.SVGFIG.mount(el); }); return; }
  // 캡션·설명이 아직 없으면 스펙에 새로 넣는다(빈 글이면 안 넣는다)
  const 말 = 키 === 'caption' ? '캡션' : '그림 밑 설명(※)';
  const p = 작은판(말 + ' 넣기', '비우면 넣지 않습니다');
  const inp = document.createElement('input'); inp.type = 'text'; p.appendChild(inp);
  판단추(p, '넣기', () => {
    const v = inp.value.trim(); if (!v) return;
    const s2 = figSpec(el); s2[키 === 'caption' ? '캡션' : '함의'] = v; setFigSpec(el, s2);
    도식다시(el, { action: 키 === 'caption' ? '도식 캡션' : '도식 설명' });
  });
  setTimeout(() => inp.focus(), 30);
}

// ── 색 — 역할 칩(문맥별 5개 이하). 팔레트(실제 색)는 윗줄 '문서 설정' 한 곳 ──
function 도식칸기억(e) {
  // 쪽을 나눠 실은 도식의 이음 조각(판정 ⑧)을 눌렀으면 원본 도식의 칸으로 센다(figLabels 가 조각 칸까지 센다)
  const f = e.target.closest && (e.target.closest('.fr-fig[data-fig]')
    || (typeof 도식원본 === 'function' ? 도식원본(e.target) : null));
  if (!f || e.target.closest('.panel')) return;
  const 칸 = e.target.closest('td[data-gi]') || e.target.closest('svg text');
  if (!칸) return;
  const i = figLabels(f).indexOf(칸);
  if (i >= 0) state.도식칸 = { el: f, i };
}
// window 에서 잡는다 — 문서(document) 쪽 드릴다운 처리기가 막대를 다시 짓기 **전에** 누른 칸을 알아 둔다
window.addEventListener('click', 도식칸기억, true);
window.addEventListener('click', e => 표칸기억(e.target), true);
// gi 차례(figSetters 와 같다)마다 색 역할을 걸 원소 — 목표·머리·시행·결과처럼 역할이 고정인 칸은 null.
// 돌려주는 것: [배열, 차례, 제목키] (전략은 '제목', 나머지는 '라벨')
function 색자리(sp) {
  const S = [];
  const 배 = k => (Array.isArray(sp[k]) ? sp[k] : []);
  if (sp.type === 'process' || sp.type === 'cycle') 배('단계').forEach((_, i) => S.push([sp['단계'], i, '라벨']));
  else if (sp.type === 'converge') {
    배('요건').forEach((_, i) => S.push([sp['요건'], i, '라벨']));
    if (String(svgLab(sp['시행'])).trim()) S.push(null);    // 시행이 비면 칸이 없다(figSetters 와 같은 차례, M6)
    S.push(null);
  }
  else if (sp.type === 'strategy') {
    S.push(null);
    배('전략').forEach((c, i) => {
      S.push([sp['전략'], i, '제목']);
      // 과제 칸은 그 칸 하나('26-09-29 판정 ④ — 예전엔 전략(열) 전체에 걸렸다). 넷째 자리 = 과제 표지(칩 거르기)
      (Array.isArray(c && c['과제']) ? c['과제'] : []).forEach((_, j) => S.push([c['과제'], j, '라벨', '과제']));
    });
  } else if (sp.type === 'relation') 배('노드').forEach((_, i) => S.push([sp['노드'], i, '라벨']));
  else if (sp.type === 'compare') {
    S.push(null); 배('전').forEach((_, i) => S.push([sp['전'], i, '라벨']));
    S.push(null); 배('후').forEach((_, i) => S.push([sp['후'], i, '라벨']));
  }
  return S;
}
function 색읽기(자) {                        // svgfig.js 역할() 과 같은 읽기 — 색(허용 목록) 또는 강조:true
  const x = 자 && 자[0][자[1]];
  if (!x || typeof x !== 'object') return '보조';
  if (도식색칩.some(([v]) => v === x['색'])) return x['색'];
  return x['강조'] === true ? '강조' : '보조';
}
function 색쓰기(자, r) {
  const [arr, i, 키] = 자;
  let x = arr[i];
  const 글이었다 = !x || typeof x !== 'object';
  if (글이었다) { x = { [키]: x == null ? '' : String(x) }; arr[i] = x; }
  delete x['강조'];
  if (r === '보조') delete x['색']; else x['색'] = r;
  const ks = Object.keys(x);                  // 역할을 지워 라벨만 남으면 원래 글 모양으로 되돌린다(왕복 불변)
  if (글이었다 && ks.length === 1 && ks[0] === 키) arr[i] = x[키];
}
function 칩(s, 값, 말, 색, 지금, f) {
  const b = btn('', () => { 메뉴닫기(); f(값); });
  b.setAttribute('role', 'menuitemradio'); b.setAttribute('aria-checked', String(값 === 지금));
  b.dataset.role = 값 || '없음';
  const sw = document.createElement('span'); sw.className = 'osw'; sw.style.background = 색;
  b.appendChild(sw); b.appendChild(document.createTextNode(말));
  s.appendChild(b); return b;
}
function 도식칸(el) {
  const c = state.도식칸;
  return c && c.el === el && el.isConnected ? c.i : -1;
}
function 도식색메뉴(s, el) {
  const 칸 = 도식칸(el);
  const sp0 = figSpec(el);
  const 자 = 칸 >= 0 ? 색자리(sp0)[칸] : null;
  const t = 칸 >= 0 ? figLabels(el)[칸] : null;
  // 체계도 — 전략 머리 칸은 그 전략(열) 전체에, 과제 칸은 그 칸 하나에 걸린다('26-09-29 판정 ④). 힌트가
  // 어디에 걸리는지 말한다(적대 검토 M5: 과제 칸을 눌렀는데 열 전체가 칠해져 힌트와 결과가 달랐다)
  const 과제칸 = sp0.type === 'strategy' && 자 && 자[3] === '과제';
  const 체계 = sp0.type === 'strategy' && 자 && !과제칸;
  s.insertAdjacentHTML('beforeend', '<div class="ohint">' + (체계
      ? '이 칸이 속한 전략(열) 전체에 걸립니다 — ' + esc(String(svgLab((sp0['전략'] || [])[자[1]]) || '').slice(0, 18))
    : 과제칸 ? '이 과제 칸 하나에만 걸립니다 — ' + esc((t ? svgLabelText(t) : '').slice(0, 18))
    : 자 ? '고른 칸: ' + esc((t ? svgLabelText(t) : '').slice(0, 18))
    : 칸 >= 0 ? '이 칸은 색이 정해져 있습니다(목표·머리·결과) — 다른 칸을 누르세요'
    : '색을 바꿀 칸(라벨)을 먼저 누르세요') + '</div>');
  const 지금 = 자 ? 색읽기(자) : '';
  // 분야색은 체계도 전략(열) 묶음에만(critic_design 3-5, 적대 검토 L2) — 흐름·비교판·관계와 체계도 과제 칸 하나는
  // 기본·강조·회색 셋(판정 ④ — 역할 칩 5개 안에서, 분야는 묶음 색이라 칸 하나에 안 쓴다)
  도식색칩.filter(([값]) => (sp0.type === 'strategy' && !과제칸) || !/^분야/.test(값) || 값 === 지금).forEach(([값, 말, 색]) => {
    const b = 칩(s, 값, 말, 색, 지금, v => {
      const i = 도식칸(el), s2 = figSpec(el), 자2 = i >= 0 ? 색자리(s2)[i] : null;
      if (!자2) { toast('색을 바꿀 칸(라벨)을 먼저 누르세요'); return; }
      const 잡 = 되돌림잡기(el);
      색쓰기(자2, v); setFigSpec(el, s2); 도식다시(el, { action: '도식 색 역할', to: 말 });
      되돌림걸기(잡, '칸 색을 ' + 말 + 로(말) + ' 바꿨습니다');
    });
    if (!자) b.disabled = true;
  });
  s.insertAdjacentHTML('beforeend', '<div class="ohint">실제 색은 윗줄 문서 설정의 도식·차트 색이 정합니다</div>');
}
function 표색메뉴(s, el) {
  // 규정 별표 표는 칸 색을 쓰지 않는다(critic_design #13, 적대 검토 L5)
  if (PROFILE.genre === 'regulation') {
    s.insertAdjacentHTML('beforeend', '<div class="ohint">규정 별표 표는 칸에 색을 칠하지 않습니다</div>'); return; }
  const td = 지금칸(el), 된다 = !!td && td.tagName !== 'TH';
  if (!된다) s.insertAdjacentHTML('beforeend', '<div class="ohint">' + (td ? '머리 칸은 칠하지 않습니다 — 몸 칸을 누르세요'
    : '칠할 칸을 먼저 누르세요') + '</div>');
  const 지금 = 된다 ? (td.dataset.강조 || '') : null;
  표색칩.forEach(([값, 말, 색]) => 칩(s, 값, 말, 색, 지금, v => {
    const t = 지금칸(el);
    if (!t || t.tagName === 'TH') { toast('강조할 칸을 먼저 누르세요 — 머리 칸은 강조하지 않습니다'); return; }
    const 잡 = 되돌림잡기(el);
    if (v) t.dataset.강조 = v; else delete t.dataset.강조;
    // 이력 이름 — 셋 다 '칸 강조'로 남아 회색·지움이 강조로 읽혔다(적대 검토 L1)
    표조작뒤(el, v === '강조' ? '칸 강조' : v ? '칸 칠(' + 말 + ')' : '칸 칠 지움');
    되돌림걸기(잡, v ? '칸을 ' + 말 + 로(말) + ' 칠했습니다' : '칸 칠을 지웠습니다');
  }));
  s.insertAdjacentHTML('beforeend', '<div class="ohint">강조 칸은 흑백 인쇄에서도 보이게 굵게 씁니다</div>');
}
function 표모양메뉴(s, el, info) {
  const tb = el.querySelector('table');
  const 후보 = info.spec['스타일'] || 표모양들;
  const 지금 = el.dataset.표모양 !== undefined ? el.dataset.표모양 : (tb && tb.dataset.style) || '';
  [''].concat(후보).forEach(v => {
    const b = 메뉴단추(s, v || '기본', () => {
      if (!tb) return;
      const 잡 = 되돌림잡기(el);
      if (v) tb.dataset.style = v; else delete tb.dataset.style;
      el.dataset.표모양 = v;
      state.ops.push({ action: '표 모양', to: v || '기본' }); repaginate(); save(); select(el);
      되돌림걸기(잡, '표 모양을 ' + (v || '기본') + 로(v || '기본') + ' 바꿨습니다');
    });
    b.setAttribute('role', 'menuitemradio'); b.setAttribute('aria-checked', String(v === 지금));
  });
}

// ── 표 행 ──
function 표행넣기(el) {
  // 새 행은 **격자 열 수**만큼 칸을 만든다(위에서 세로로 합친 칸이 내려와 있어도 칸이 모자라지 않게)
  const tb = el.querySelector('table'); const g = 표격자(tb);
  const tr = tb.insertRow(-1);
  for (let i = 0; i < g.n열; i++) tr.insertCell(-1).textContent = '—';
  표조작뒤(el, '표 행 추가');
}
function 표행빼기(el) {
  const tb = el.querySelector('table'); const g = 표격자(tb);
  if (tb.rows.length <= 2) { toast('행이 둘 남으면 더 뺄 수 없습니다'); return; }
  const r = g.n행 - 1;
  const 잡 = 되돌림잡기(el);
  g.자리.forEach(z => { if (z.r < r && z.r + z.세로 - 1 >= r) z.td.rowSpan = z.세로 - 1; });
  tb.deleteRow(-1); 표조작뒤(el, '표 행 삭제');
  되돌림걸기(잡, '마지막 행을 뺐습니다');
}

// ── 차트 값 고치기(격자) — 스펙 값을 칸으로 고친다. 적용하면 그 자리에서 다시 그린다 ──
function 차트값판(el, info) {
  const sp = figSpec(el), 복 = o => JSON.parse(JSON.stringify(o));
  const p = 작은판(info.label + ' — 값 고치기', '적용하면 바로 다시 그립니다. 빈 칸은 값 없음으로 둡니다.');
  const 숫자 = s => { const t = String(s).replace(/,/g, '').trim(); if (t === '') return null; const n = Number(t); return isFinite(n) ? n : NaN; };
  const 칸 = (v, w) => { const i = document.createElement('input'); i.type = 'text'; i.value = v == null ? '' : String(v); if (w) i.style.minWidth = w; return i; };
  const tb = document.createElement('table'); p.appendChild(tb);
  const 줄 = () => { const r = document.createElement('div'); r.className = 'orow left'; p.appendChild(r); return r; };
  let 거두기 = null;
  if (sp.type === 'bar' || sp.type === 'line' || sp.type === 'hbar') {       // 열 = 시점(항목), 행 = 계열
    const 축 = (Array.isArray(sp['시점']) ? sp['시점'] : []).map(x => String(x ?? ''));
    const 계열 = 복((Array.isArray(sp['계열']) ? sp['계열'] : []).filter(s => s && typeof s === 'object'));
    if (!계열.length) 계열.push({ 이름: '', 값: 축.map(() => null) });
    const 그리기 = () => {
      tb.innerHTML = '';
      const hr = tb.insertRow(); hr.insertCell().textContent = sp.type === 'hbar' ? '계열 / 항목' : '계열 / 시점';
      축.forEach((a, k) => { const i = 칸(a, '64px'); i.dataset.ax = k; hr.insertCell().appendChild(i); });
      계열.forEach((s, q) => {
        const r = tb.insertRow(); const n = 칸(s['이름'], '90px'); n.dataset.nm = q; r.insertCell().appendChild(n);
        축.forEach((_, k) => { const i = 칸((s['값'] || [])[k], '64px'); i.dataset.sr = q; i.dataset.k = k; r.insertCell().appendChild(i); });
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
      계열.forEach(s => { s['값'] = (s['값'] || []).slice(0, 축.length); while (s['값'].length < 축.length) s['값'].push(null); });
      return !틀림;
    };
    그리기();
    const r = 줄(), 말 = sp.type === 'hbar' ? '항목' : '시점';
    r.appendChild(btn('＋ ' + 말, () => { 읽기(); 축.push(''); 그리기(); }));
    r.appendChild(btn('－ 마지막 ' + 말, () => { 읽기(); if (축.length <= 1) return; 축.pop(); 그리기(); }));
    r.appendChild(btn('＋ 계열', () => { 읽기(); 계열.push({ 이름: '', 값: 축.map(() => null) }); 그리기(); }));
    r.appendChild(btn('－ 마지막 계열', () => { 읽기(); if (계열.length <= 1) return; 계열.pop(); 그리기(); }));
    거두기 = () => (읽기() && 축.every(a => a) ? { 시점: 축, 계열 } : null);
  } else if (sp.type === 'donut') {                                          // 행 = 이름 | 값
    const 원 = Array.isArray(sp['항목']) ? sp['항목'] : [];
    const 배열꼴 = !원.length || Array.isArray(원[0]);
    const 항목 = 원.map(it => Array.isArray(it) ? [String(it[0] ?? ''), it[1]] : [String((it && it['이름']) ?? ''), it && it['값']]);
    const 그리기 = () => {
      tb.innerHTML = '';
      const hr = tb.insertRow(); hr.insertCell().textContent = '이름'; hr.insertCell().textContent = '값';
      항목.forEach(([n, v], q) => { const r = tb.insertRow(); const a = 칸(n); a.dataset.lb = q; r.insertCell().appendChild(a);
        const b = 칸(v, '80px'); b.dataset.vl = q; r.insertCell().appendChild(b); });
    };
    const 읽기 = () => {
      let 틀림 = false;
      tb.querySelectorAll('input[data-lb]').forEach(i => { 항목[+i.dataset.lb][0] = i.value.trim(); });
      tb.querySelectorAll('input[data-vl]').forEach(i => { const v = 숫자(i.value); if (v === null || Number.isNaN(v)) 틀림 = true; else 항목[+i.dataset.vl][1] = v; });
      return !틀림;
    };
    그리기();
    const r = 줄();
    r.appendChild(btn('＋ 행', () => { 읽기(); 항목.push(['', 0]); 그리기(); }));
    r.appendChild(btn('－ 마지막 행', () => { 읽기(); if (항목.length <= 1) return; 항목.pop(); 그리기(); }));
    거두기 = () => (읽기() && 항목.every(([n]) => n)
      ? { 항목: 항목.map(([n, v]) => 배열꼴 ? [n, v] : { 이름: n, 값: v }) } : null);
  } else if (sp.type === 'stack') {                                          // 세트마다 이름 | 값
    const 세트 = 복((Array.isArray(sp['세트']) ? sp['세트'] : []).filter(s => s && typeof s === 'object'));
    const 그리기 = () => {
      tb.innerHTML = '';
      세트.forEach((st, si) => {
        const hr = tb.insertRow(); const c = hr.insertCell(); c.colSpan = 2;
        const n = 칸(st['이름'], '120px'); n.dataset.set = si; c.appendChild(n);
        (Array.isArray(st['항목']) ? st['항목'] : []).forEach((it, q) => {
          const [nm, v] = Array.isArray(it) ? it : [it && it['이름'], it && it['값']];
          const r = tb.insertRow(); const a = 칸(nm); a.dataset.si = si; a.dataset.lb = q; r.insertCell().appendChild(a);
          const b = 칸(v, '80px'); b.dataset.si = si; b.dataset.vl = q; r.insertCell().appendChild(b);
        });
      });
    };
    const 읽기 = () => {
      let 틀림 = false;
      tb.querySelectorAll('input[data-set]').forEach(i => { 세트[+i.dataset.set]['이름'] = i.value.trim(); });
      tb.querySelectorAll('input[data-si]').forEach(i => {
        const st = 세트[+i.dataset.si], q = +(i.dataset.lb ?? i.dataset.vl), it = st['항목'][q];
        const 배 = Array.isArray(it), o = 배 ? it : (it || {});
        if (i.dataset.lb !== undefined) { if (배) o[0] = i.value.trim(); else o['이름'] = i.value.trim(); }
        else { const v = 숫자(i.value); if (v === null || Number.isNaN(v)) 틀림 = true; else if (배) o[1] = v; else o['값'] = v; }
        st['항목'][q] = o;
      });
      return !틀림;
    };
    그리기();
    거두기 = () => (읽기() ? { 세트 } : null);
  } else {
    p.insertAdjacentHTML('beforeend', '<p class="osub">이 차트는 값 칸이 없습니다.</p>');
  }
  판단추(p, '적용', () => {
    const 새 = 거두기 && 거두기();
    if (!새) { toast('비었거나 숫자가 아닌 칸이 있습니다 — 고쳐 주세요', 2600); return false; }
    const 전 = figSpec(el), s2 = Object.assign(figSpec(el), 새);
    const 까닭 = 쪽게이트(el, () => { setFigSpec(el, s2); window.SVGFIG.mount(el); },
                             () => { setFigSpec(el, 전); window.SVGFIG.mount(el); });
    if (까닭) { toast('값을 바꾸면 ' + 까닭, 4200); return false; }
    state.ops.push({ action: '차트 값', target: info.label }); save(); repaginate(); select(el);
    toast('차트 값을 바꿨습니다', 2000);
  });
  const 첫 = p.querySelector('input'); if (첫) 첫.focus();
}

// ── 되돌리기 — 지우기·칸 합치기/나누기·열·행·항목 빼기·색 칩·모양·AI(적대 검토 H2 '26-09-29) ─────────
// 되돌리기 토스트가 크기·색(팔레트)·제목 모양에만 있고, 되돌리기 어려운 조작에는 없었다(남은 길은 5분 판
// 간격의 이력 레일뿐이라 그 뒤 고친 것까지 잃었다). 조작 **직전** 개체가 든 블록 하나를 글(outerHTML)로 붙잡아
// 두었다가, 조작이 실제로 걸렸으면(state.ops 가 늘었으면) 5초 [되돌리기] 토스트를 띄운다. 토스트가 떠 있고
// 그 조작이 마지막일 때만 Cmd/Ctrl+Z 도 같은 일을 한다(크기 토스트와 같은 규칙 — 크기토스트떠있나).
// 되박은 블록은 원래 data-path 를 그대로 가져 직렬화가 SRCDOC 에서 그 자리를 되살린다(serialize ② 가지치기의 역).
function 되돌림그릇(el) { return (el && el.closest && (el.closest('.blk') || el.closest('p'))) || el; }
function 되돌림잡기(el) {
  const host = 되돌림그릇(el);
  if (!host || !host.parentNode) return null;
  const 길 = [];                                          // 블록 → 고른 개체(자식 차례) — 되박은 뒤 다시 고른다
  for (let x = el; x && x !== host && x.parentElement; x = x.parentElement) 길.unshift([...x.parentElement.children].indexOf(x));
  const c = host.cloneNode(true);
  [c, ...c.querySelectorAll('.ent-sel,[contenteditable]')].forEach(x => { x.classList.remove('ent-sel'); x.removeAttribute('contenteditable'); });
  return { host, html: c.outerHTML, 부모: host.parentNode, 앞: host.previousElementSibling,
           뒤: host.nextElementSibling, 길, n: state.ops.length };
}
function 되박기(잡) {
  const t = document.createElement('template'); t.innerHTML = 잡.html;
  const 새 = t.content.firstElementChild; if (!새) return null;
  if (잡.host.isConnected) 잡.host.replaceWith(새);
  else if (잡.뒤 && 잡.뒤.isConnected) 잡.뒤.before(새);
  else if (잡.앞 && 잡.앞.isConnected) 잡.앞.after(새);
  else if (잡.부모 && 잡.부모.isConnected) 잡.부모.appendChild(새);
  else return null;
  if (window.SVGFIG) (새.matches('.fr-fig[data-fig]') ? [새] : [...새.querySelectorAll('.fr-fig[data-fig]')])
    .forEach(f => window.SVGFIG.mount(f, false));
  state.표칸 = null; state.도식칸 = null;
  let x = 새; 잡.길.forEach(i => { x = x && x.children[i]; });
  return x || 새;
}
function 되돌림걸기(잡, 말) {
  if (!잡 || state.ops.length <= 잡.n) return;            // 조작이 안 걸렸다(토스트로 거절 등)
  크기토스트(말, () => {
    const x = 되박기(잡);
    if (!x) { toast('되돌릴 자리를 찾지 못했습니다'); return; }
    state.ops.push({ action: '되돌리기', target: 말 }); repaginate(); save();
    select(x.closest && x.closest('[data-ent]') ? x.closest('[data-ent]') : x);
    toast('되돌렸습니다', 2000);
  });
}
function 되돌림감싸기(원, 말) {
  return function (el, ...나머지) {
    const 잡 = 되돌림잡기(el);
    const r = 원.call(this, el, ...나머지);
    const 걸기 = () => 되돌림걸기(잡, typeof 말 === 'function' ? 말(el, ...나머지) : 말);
    if (r && typeof r.then === 'function') return r.then(v => { 걸기(); return v; });
    걸기(); return r;
  };
}
function svgLab(x) {                                     // svgfig.js lab() 과 같은 읽기
  return (x && typeof x === 'object')
    ? (x['라벨'] ?? x.label ?? x.name ?? x['이름'] ?? x['제목'] ?? x.text ?? x.title ?? '') : (x ?? '');
}
function 을를(s) {
  const c = String(s || '').trim().slice(-1).charCodeAt(0) - 0xAC00;
  return (c >= 0 && c <= 11171 && c % 28 !== 0) ? '을' : '를';
}
// render_editor_any 의 조작(함수 선언이라 이 자리에서 감쌀 수 있다 — 부르는 쪽은 모두 이 이름을 다시 읽는다)
if (typeof delEl === 'function') delEl = 되돌림감싸기(delEl, (el, info) => {
  const 이름 = (info && (info.label || info.type)) || '개체'; return 이름 + 을를(이름) + ' 지웠습니다'; });
if (typeof 칸합치기 === 'function') 칸합치기 = 되돌림감싸기(칸합치기, '칸을 합쳤습니다');
if (typeof 칸나누기 === 'function') 칸나누기 = 되돌림감싸기(칸나누기, '칸을 나눴습니다');
if (typeof 열빼기 === 'function') 열빼기 = 되돌림감싸기(열빼기, '열을 뺐습니다');
if (typeof ai다시쓰기 === 'function') ai다시쓰기 = 되돌림감싸기(ai다시쓰기, 'AI로 고쳤습니다');
// 못 실은 그림 자리 칩의 차례(--mi) — 잇단 자리마다 한 칸씩 내려 쌓는다('26-09-30 Q5, verify_fixup4_ux V5). CSS 형제 규칙은
// 다섯 칸에서 멈춰 여섯째부터 칩이 한 자리에 겹쳤다. 개수 제한 없이 여기서 매기고, 재조판·그림 바꾸기로 자리가 바뀌면(자식 목록
// 변화) 다시 매긴다. 간격은 칩 제 높이(render_editor_any 의 translateY(… var(--mi) * (100% + 2px)))라 글자 크기가 달라도 맞는다.
function 못실은칩차례() {
  const 못 = n => n && n.matches && n.matches('.fr-img[data-miss]');
  document.querySelectorAll('.fr-img[data-miss]').forEach(el => {
    let k = 0, n = el.previousElementSibling;
    while (못(n)) { k++; n = n.previousElementSibling; }
    if (el.style.getPropertyValue('--mi') !== String(k)) el.style.setProperty('--mi', String(k));
  });
}
var 칩차례판 = null, 칩차례시계 = 0;
try {
  못실은칩차례();
  칩차례판 = new MutationObserver(() => { clearTimeout(칩차례시계); 칩차례시계 = setTimeout(못실은칩차례, 30); });
  칩차례판.observe(document.body, { childList: true, subtree: true });
} catch (e) { /* 칩 차례를 못 매겨도 편집기는 돈다(CSS 형제 규칙 다섯 칸까지) */ }
// 그림을 지우면 남은 '작게' 그림끼리 짝을 다시 짓는다(풀버전 나란히 — 그림 P3)
if (typeof delEl === 'function') {
  var 그림지우기전 = delEl;
  delEl = function (el, info) {
    const r = 그림지우기전.apply(this, arguments);
    if (info && info.type === '이미지') 그림짝다시();
    return r;
  };
}

// ── 격자 도식 칸은 누르면 바로 고친다(적대 검토 M7) — 고른 격자 도식의 칸을 한 번 더 누르면 그 칸 라벨 판 ──
// 예전엔 ⋯ › 글자 고치기… › 라벨 고르기 › 입력으로 네 번을 눌렀다(사장님 기준 '누르면 바로 편집').
// render_editor_any 의 문서 클릭 처리기가 고른 것을 두고(드릴다운으로 바깥 장에 되돌아가지 않게) 여기를 부른다.
function 격자칸고치기(f, td) {
  const i = figLabels(f).indexOf(td);
  if (i < 0 || !figSetters(figSpec(f))[i]) return;
  라벨판(f, i);
}
"""
