/* 자동 게이트 감사 — jachigan 실행 후 측정 결과를 document.title에 기록.
   headless --dump-dom 으로 <title>을 회수해 게이트 판정에 사용한다.
   게이트: splits==0 (어절 분리 없음) / sheetMm<=297 (1쪽) / sumLines<=2 (요약 2줄 이하) */
/* [장르] 세 장르가 같은 코드를 쓰되 선택자는 갈라야 한다.
   그냥 붙이면 시행문·여러 장에서 아무것도 안 잡혀 splits:0 이 '합격'으로 기록된다 —
   문체검사기가 두 장르에 내던 공허한 통과와 정확히 같은 병이다(2026-07-30). */
/* 키는 조립기가 심는 data-genre 값 그대로다. 예전에는 여기 'onepage-report' 라고
   적어 놓고 조립기는 'onepage' 를 심었는데, 22행의 무조건 폴백이 그 어긋남을 덮어
   아무도 몰랐다. 폴백을 없앴으므로 이름이 틀리면 곧바로 '못 쟀다'로 드러난다.
   build/verify_all.py 의 check_audit_genres() 가 장르 누락을 막는다. */
const AUDIT_SPEC = {
  onepage:          { 지면: '.sheet', 어절: '.doc-summary, .i-l2, .i-l3, .i-l4, .doc-attach',
                      요약: '.doc-summary', 끝: '.doc-attach' },
  /* 시행문은 채움도를 재되 '비어 보인다' 판정은 하지 않는다 — 0.72 임계는
     1페이지 보고서의 검수 지적에서 나온 값이라 근거가 시행문까지 미치지 않는다. */
  gongmun:          { 지면: '.gm-sheet', 어절: '.g-l1, .g-l2, .g-tx, .gm-attach',
                      요약: null, 끝: '.gm-attach', sparse판정: false },
  /* 여러 장은 채움도를 재지 않는다 — 쪽이 여럿이라 '지면 대비 비율'이 한 값으로
     성립하지 않는다. 첫 쪽(표지)을 재면 0이나 0.99 같은 뜻 없는 수가 나온다. */
  fullreport:       { 지면: '.fr-page', 어절: '.fr-sec, .i-l2, .i-l3, .i-l4',
                      요약: null, 끝: null, 채움도: false },
  /* 규정·보도자료는 요약 개체가 없다. 채움도는 규정이 여러 쪽으로 가므로 안 잰다. */
  regulation:       { 지면: '.rg-sheet', 어절: '.rg-body p', 요약: null, 끝: null, 채움도: false },
  'press-release':  { 지면: '.pr-sheet', 어절: '.pr-body p', 요약: null, 끝: null, 채움도: false },
  /* 슬라이드는 장 = 고정 상자 여럿(다지면). 단일 지면 측정(sheetMm·채움도)이 성립하지
     않아 장별 넘침·장수를 대신 잰다. overflow:hidden 이라 넘쳐도 PDF 쪽수는 안 는다 —
     쪽수 게이트가 못 보는 넘침을 이 측정이 잡는다(스텁 실측 '26-08-13). */
  slides:           { 지면: '.sl-page', 어절: '.sl-head, .sl-body .tx, .sl-agenda-i',
                      요약: null, 끝: null, 채움도: false, 다지면: true },
};

/* 어절은 **블록 전체**를 이어 붙여 센다.
   텍스트 노드 하나씩 보면 강조 span 경계에 걸친 어절('…타당</span>하다는')이
   두 어절로 보여 분리가 안 잡힌다 — 하드 게이트가 거짓 합격을 낸다(2026-08-04 확정).
   <br> 과 블록 자식은 줄이 갈리는 자리이므로 경계를 끼워 '1부.붙임' 같은 가짜를 막는다. */
function 글자지도(el) {
  const map = [], chars = [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = w.nextNode())) {
    if (n.nodeType === 1) {
      if (n.tagName === 'BR' || getComputedStyle(n).display !== 'inline') {
        chars.push('\n'); map.push(null);
      }
      continue;
    }
    for (let i = 0; i < n.nodeValue.length; i++) { chars.push(n.nodeValue[i]); map.push([n, i]); }
  }
  return { text: chars.join(''), map: map };
}
function 글자상자(map, i) {
  if (!map[i]) return null;
  const r = document.createRange();
  r.setStart(map[i][0], map[i][1]); r.setEnd(map[i][0], map[i][1] + 1);
  return [...r.getClientRects()].filter(x => x.width > 0.5)[0] || null;
}
/* 줄이 갈렸는가 — top 집합 크기로 보면 굵은 글씨 경계에서 3px 차이로 가짜가 잡힌다.
   '글자의 왼쪽 좌표가 뒤로 되감겼는가'로 본다. 줄바꿈에서만 일어나는 일이다. */
function 어절이갈렸나(map, s, e) {
  let 앞 = null;
  for (let i = s; i < e; i++) {
    const b = 글자상자(map, i);
    if (!b) continue;
    if (앞 && b.left < 앞.left - 1) return true;
    앞 = b;
  }
  return false;
}

window.addEventListener('load', () => {
  const genre = document.documentElement.dataset.genre || '';
  const spec = AUDIT_SPEC[genre];
  if (!spec) {                        // 모르는 장르를 1p 명세로 떨어뜨리면 조용히 거짓 합격이 된다
    document.body.dataset.audit = JSON.stringify({ _못잼: "모르는 장르('" + genre + "') — AUDIT_SPEC 에 없다" });
    return;
  }
  const SEL = spec.어절;
  let splits = 0;
  const splitWords = [];
  document.querySelectorAll(SEL).forEach(el => {
    const g = 글자지도(el);
    const re = /\S+/g; let m;
    while ((m = re.exec(g.text))) {
      const s = m.index, e = s + m[0].length;
      const r = document.createRange();          // 값싼 앞거르개 — 상자가 하나면 안 갈렸다
      r.setStart(g.map[s][0], g.map[s][1]);
      const 끝 = g.map[e - 1]; r.setEnd(끝[0], 끝[1] + 1);
      if ([...r.getClientRects()].filter(x => x.width > 0.5).length < 2) continue;
      if (어절이갈렸나(g.map, s, e)) { splits++; splitWords.push(m[0]); }
    }
  });
  if (spec.다지면) {                  // 슬라이드 — 장별로 넘침·장수를 재고 여기서 끝낸다
    const pages = [...document.querySelectorAll(spec.지면)];
    if (!pages.length) {
      document.body.dataset.audit = JSON.stringify({ _못잼: '지면(' + spec.지면 + ')을 찾지 못했다' });
      return;
    }
    const overflows = pages
      .map((p, i) => ({ n: i + 1, over: Math.round(p.scrollHeight - p.clientHeight) }))
      .filter(x => x.over > 4);       /* 허용 4px — 반올림 잡음 아래(스텁 실측) */
    document.body.dataset.audit = JSON.stringify(
      { 장르: genre, splits, splitWords, slides: pages.length, overflows,
        compressed: document.querySelectorAll('.jachigan-run').length });
    return;
  }
  const sheet = document.querySelector(spec.지면);
  if (!sheet) {                       // 잴 수 없으면 '통과'가 아니라 '못 쟀다'로 남긴다
    document.body.dataset.audit = JSON.stringify({ _못잼: '지면(' + spec.지면 + ')을 찾지 못했다' });
    return;
  }
  const sheetMm = Math.round(sheet.scrollHeight / 96 * 25.4);
  const sum = spec.요약 ? document.querySelector(spec.요약) : null;
  let sumLines = 0;
  if (sum) {
    const cs = getComputedStyle(sum);
    const inner = sum.offsetHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    sumLines = Math.round(inner / parseFloat(cs.lineHeight));
  }
  const compressed = document.querySelectorAll('.jachigan-run').length;
  /* 채움도(fill): 인쇄 영역 대비 실제 콘텐츠가 차지하는 비율.
     sheet는 min-height 297mm라 sparse해도 sheetMm는 안 줄어든다 → 별도 측정.
     마지막 콘텐츠(.doc-attach) 하단까지의 높이 / 인쇄 영역(252mm). */
  const 잰다 = spec.채움도 !== false;
  const cs = getComputedStyle(sheet);
  const padTop = parseFloat(cs.paddingTop), padBot = parseFloat(cs.paddingBottom);
  const last = spec.끝 ? document.querySelector(spec.끝) : null;
  const sheetTop = sheet.getBoundingClientRect().top + padTop;
  /* 마지막 요소가 없으면 sheetTop 을 쓰면 안 된다 — contentMm 0, sparse true 라는
     거짓 관측이 나온다. 지면 안 마지막 자식의 하단을 쓴다. */
  const tail = last || sheet.lastElementChild;
  const contentBottom = tail ? tail.getBoundingClientRect().bottom : sheetTop;
  const contentMm = Math.max(0, Math.round((contentBottom - sheetTop) / 96 * 25.4));
  const printAreaMm = 297 - Math.round(padTop / 96 * 25.4) - Math.round(padBot / 96 * 25.4);
  const fillRatio = +(contentMm / printAreaMm).toFixed(2);
  const sparse = 잰다 && spec.sparse판정 !== false && fillRatio < 0.72;
  const out = { 장르: genre, splits, splitWords, sheetMm, compressed };
  if (spec.요약) out.sumLines = sumLines;
  if (잰다) { out.contentMm = contentMm; out.fillRatio = fillRatio; out.sparse = sparse; }
  else out._안잰것 = '채움도 — 쪽이 여럿이라 한 값으로 성립하지 않는다';
  document.body.dataset.audit = JSON.stringify(out);
});
