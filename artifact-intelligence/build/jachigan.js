/* 자간 사냥꾼 v2 — 줄 단위 압축 (실무자 방식 재현)
   문단 전체가 아니라 "분리 어절이 시작되는 줄의 시작점 → 분리 어절 끝" 구간만
   선택 압축한다. 위에서부터 순차 처리하므로, 윗줄 교정이 아랫줄에 일으키는
   연쇄 어절단절도 다음 반복에서 이어서 잡는다.
   한도(-6%) 내 해결 불가한 어절은 포기하고(한글 기본 동작 수용) 다음으로 넘어간다. */
(function () {
  // 장르가 늘 때마다 여기 빠뜨리면 그 장르만 조판이 벌어진다 — 실제로 규정에서 겪었다.
  // build/verify_all.py 의 check_jachigan_genres() 가 장르별 접두사 누락을 막는다.
  const SEL = '.doc-summary, .i-l2, .i-l3, .i-l4, .doc-attach, .gm-body .g-tx, .gm-attach,'
            + ' .fr-sum-i, .fr-sum-sub, .rg-body p, .pr-body p, .sl-head, .sl-body .tx';
  const FLOOR = -0.06;   /* em ≈ HWP 자간 -6% */
  const STEP = 0.005;
  const MAX_FIXES = 30;  /* 블록당 교정 시도 상한 (연쇄 처리 폭주 방지) */
  const CLS = 'jachigan-run';

  const rectsOf = r => [...r.getClientRects()].filter(x => x.width > 0.5);
  const topsOf = r => [...new Set(rectsOf(r).map(x => Math.round(x.top)))];

  function textNodesIn(root) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const a = []; let n;
    while ((n = w.nextNode())) a.push(n);
    return a;
  }

  /* 문단의 전역 문자 인덱스 → (텍스트노드, 오프셋) 매핑.
     래핑으로 노드가 쪼개져도 문자 순서는 불변이므로 인덱스는 안정적이다. */
  function charMap(el) {
    const map = [];
    textNodesIn(el).forEach(n => {
      for (let i = 0; i < n.nodeValue.length; i++) map.push([n, i]);
    });
    return map;
  }

  function rangeOf(map, s, e) { /* [s, e) */
    const r = document.createRange();
    r.setStart(map[s][0], map[s][1]);
    const [en, eo] = map[e - 1];
    r.setEnd(en, eo + 1);
    return r;
  }

  /* 구간에 자간을 건다 — **요소를 쪼개지 않고**.

     예전에는 Range.extractContents() 로 구간을 통째 뽑아 span 하나에 담았다.
     그런데 extractContents 는 **범위에 걸친 요소를 속성까지 복제**한다. 복제본은
     span 을 풀어도 다시 안 합쳐진다(normalize 는 텍스트 노드만 합친다). 그래서
     data-path·강조·마커를 단 span 이 조각으로 흩어지고, hunt 를 부를수록 늘어났다
     — 2026-08-04 실측: __hunt() 20회에 [data-path] 84→524개, HTML 9,545→39,845자.
     저장기가 조각 하나만 읽어 글이 잘리고, 되살리기는 조각마다 전체 문장을 써 넣고,
     강조 한도는 조각을 세고, 빈 마커 껍데기가 줄을 잡아먹었다. 전부 여기서 나왔다.

     그래서 **범위 안 텍스트 노드만** 경계에서 잘라 각각을 얇은 span 으로 감싼다.
     요소 복제가 0이므로 되돌리기가 진짜 복원이 되고, 여러 번 돌려도 같은 결과가 된다.
     자간은 글자마다 붙으므로 span 이 나뉘어도 간격은 같다. */
  function 조각목록(map, s, e) {
    const out = [];
    for (let i = s; i < e; i++) {
      const [n, o] = map[i];
      const last = out[out.length - 1];
      if (last && last.n === n && last.e === o) last.e = o + 1;
      else out.push({ n: n, s: o, e: o + 1 });
    }
    return out;
  }
  function 감싸기(map, s, e) {
    const spans = [];
    조각목록(map, s, e).forEach(seg => {
      let node = seg.n;
      if (seg.e < node.nodeValue.length) node.splitText(seg.e);
      if (seg.s > 0) node = node.splitText(seg.s);
      const sp = document.createElement('span');
      sp.className = CLS;
      node.parentNode.insertBefore(sp, node);
      sp.appendChild(node);
      spans.push(sp);
    });
    return spans;
  }
  const 자간걸기 = (spans, v) => spans.forEach(sp => { sp.style.letterSpacing = v; });
  function 풀기(spans, el) {
    spans.forEach(sp => { if (sp.parentNode) sp.replaceWith(...sp.childNodes); });
    el.normalize();
  }
  /* 어절이 한 줄로 회수됐는가 — 문자 인덱스는 감싸기 뒤에도 그대로다(글자 순서 불변) */
  function 한줄인가(el, s, e) {
    return topsOf(rangeOf(charMap(el), s, e)).length === 1;
  }

  /* skip 집합에 없는 첫 분리 어절 */
  function findSplit(el, map, skip) {
    const text = map.map(([n, i]) => n.nodeValue[i]).join('');
    const re = /\S+/g; let m;
    while ((m = re.exec(text))) {
      if (skip.has(m.index)) continue;
      if (topsOf(rangeOf(map, m.index, m.index + m[0].length)).length > 1)
        return { start: m.index, end: m.index + m[0].length, word: m[0] };
    }
    return null;
  }

  /* 분리 어절의 머리가 놓인 줄(윗줄)의 시작 문자 인덱스 */
  function lineStartOf(map, split) {
    const head = rectsOf(rangeOf(map, split.start, split.start + 1));
    if (!head.length) return 0;
    const top = Math.round(head[0].top);
    for (let i = 0; i < split.start; i++) {
      const rr = rectsOf(rangeOf(map, i, i + 1));
      if (rr.length && Math.round(rr[0].top) === top) return i;
    }
    return 0;
  }

  /* v3: 과신장(over-stretched) 줄 탐지 — 양쪽맞춤이 어절 간격을 비정상적으로
     벌린 줄을 찾아, 다음 줄 첫 어절을 자간 압축으로 윗줄에 당겨온다. */
  function wordsWithRects(el, map) {
    const text = map.map(([n, i]) => n.nodeValue[i]).join('');
    const out = [];
    const re = /\S+/g; let m;
    while ((m = re.exec(text))) {
      const rr = rectsOf(rangeOf(map, m.index, m.index + m[0].length));
      if (rr.length) out.push({ start: m.index, end: m.index + m[0].length, rect: rr[0], top: Math.round(rr[0].top) });
    }
    return out;
  }

  function findStretched(el, map, skip) {
    const words = wordsWithRects(el, map);
    const fontPx = parseFloat(getComputedStyle(el).fontSize);
    const GAP = fontPx * 0.85; /* 정상 어절 간격(~0.3em)의 3배 근방 */
    const tops = [...new Set(words.map(w => w.top))].sort((a, b) => a - b);
    for (let li = 0; li < tops.length - 1; li++) { /* 마지막 줄 제외 */
      const line = words.filter(w => w.top === tops[li]);
      let maxGap = 0;
      for (let i = 1; i < line.length; i++)
        maxGap = Math.max(maxGap, line[i].rect.left - line[i - 1].rect.right);
      if (maxGap <= GAP) continue;
      const next = words.find(w => w.top === tops[li + 1]);
      if (!next || skip.has(next.start)) continue;
      return { lineStart: line[0].start, target: next, lineTop: tops[li] };
    }
    return null;
  }

  function gapPass(el, skip) {
    for (let guard = 0; guard < 10; guard++) {
      const map = charMap(el);
      const g = findStretched(el, map, skip);
      if (!g) return;
      const spans = 감싸기(map, g.lineStart, g.target.end);
      let ok = false;
      for (let v = -STEP; v >= FLOOR - 1e-9; v -= STEP) {
        자간걸기(spans, v.toFixed(3) + 'em');
        /* 성공: 대상 어절이 분리 없이 윗줄로 회수됨 */
        const m2 = charMap(el);
        const rr = rectsOf(rangeOf(m2, g.target.start, g.target.end));
        const t = [...new Set(rr.map(x => Math.round(x.top)))];
        if (t.length === 1 && t[0] <= g.lineTop + 2) { ok = true; break; }
      }
      if (!ok) {
        풀기(spans, el);
        skip.add(g.target.start);
      }
    }
  }

  function 초기화(el) {
    el.querySelectorAll('span.' + CLS).forEach(s => s.replaceWith(...s.childNodes));
    el.normalize();
  }

  function fixBlock(el) {
    /* 초기화는 부르는 쪽 몫이다 — gapPass 뒤에 다시 부를 때 그 결과를 지우면 안 된다 */
    const skip = new Set();
    let fixes = 0;
    while (fixes++ < MAX_FIXES) {
      const map = charMap(el);
      const split = findSplit(el, map, skip);
      if (!split) return;

      const ls = lineStartOf(map, split);
      const spans = 감싸기(map, ls, split.end);

      let ok = false;
      for (let v = -STEP; v >= FLOOR - 1e-9; v -= STEP) {
        자간걸기(spans, v.toFixed(3) + 'em');
        if (한줄인가(el, split.start, split.end)) { ok = true; break; }
      }
      if (!ok) {
        풀기(spans, el);
        skip.add(split.start); /* 이 어절은 한글 기본(분리) 수용 */
      }
      /* 성공 시: 처음부터 재스캔 → 아랫줄 연쇄 단절을 순차 처리 */
    }
  }

  /* 순서가 중요하다 — **gapPass 뒤에 분리 사냥을 한 번 더 돌린다.**

     gapPass 는 늘어진 줄의 다음 어절을 윗줄로 당긴다. 그러면 그 아래가 다시 흐르면서
     **새 분리가 생긴다.** 그런데 지금까지는 아무도 그것을 다시 안 봤다.
     규정 13건 실측(2026-08-04): 개입 없음 267건 → fixBlock 만 15건 → gapPass 까지 32건.
     **gapPass 가 분리를 두 배로 늘리고 있었다.**

     다시 부를 때 초기화를 하면 gapPass 가 건 자간이 다 풀린다 — 그래서 초기화를 갈랐다. */
  function fixBlockFull(el) {
    초기화(el);
    fixBlock(el);
    gapPass(el, new Set());
    fixBlock(el);          /* gapPass 가 새로 만든 분리를 거둔다 */
  }

  function hunt() { document.querySelectorAll(SEL).forEach(fixBlockFull); }

  /* 헤드리스 인쇄에서는 rAF가 돌지 않으므로 동기 실행 + 폰트 로드 후 재실행 */
  function run() {
    hunt();
    if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(hunt);
  }
  if (document.readyState === 'complete') run();
  else window.addEventListener('load', run);
  window.__hunt = run;
})();
