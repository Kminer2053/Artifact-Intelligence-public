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
  if (spec.다지면) {                  // 슬라이드 — 장별로 넘침·장수·구성지표를 재고 여기서 끝낸다
    const pages = [...document.querySelectorAll(spec.지면)];
    if (!pages.length) {
      document.body.dataset.audit = JSON.stringify({ _못잼: '지면(' + spec.지면 + ')을 찾지 못했다' });
      return;
    }
    /* 판형 v2(부품 트리, .deck.v2) — 칸이 본문을 넘쳐 꼬리말·요지띠를 덮는 넘침은 장 밖으로
       안 나가서 장의 scrollHeight 로는 안 잡힌다('26-09-28 키노트 시제품 실측). 그래서 v2 장은
       본문·칸 그릇·부품·세로묶음 칸의 세로 넘침도 잰다. 옛 문서(.deck.v2 없음)는 그대로다. */
    const 넘침 = p => {
      let over = Math.round(p.scrollHeight - p.clientHeight);
      if (p.closest('.deck.v2')) {
        p.querySelectorAll('.sl-body, .v2-cell, .v2-cell > *, .v2-stack > *').forEach(el => {
          over = Math.max(over, Math.round(el.scrollHeight - el.clientHeight));
        });
      }
      return over;
    };
    const overflows = pages
      .map((p, i) => ({ n: i + 1, over: 넘침(p) }))
      .filter(x => x.over > 4);       /* 허용 4px — 반올림 잡음 아래(스텁 실측) */
    /* v2 가로 넘침('26-09-28 적대 검토 렌더 M7) — 세로 넘침만 재서, 띄어쓰기 없는 긴 라벨이 타일 밖·
       장 밖으로 나가 옆 칸과 겹쳐도 게이트를 통과했다. 화면 글(.tx)의 실제 글 네모(Range)를 그 글이
       든 칸 그릇(.v2-cell)에 대어 4px 넘게 나가면 센다. 새 지표라 soft(render_verify 인상 절)로 시작. */
    const 가로넘침 = [];
    pages.forEach((p, i) => {
      if (!p.closest('.deck.v2')) return;
      const 보기 = [];
      /* 조립기가 찍는 숫자(링·지표·진행막대 .num 안 글)도 잰다 — 링을 키우자 링 숫자가 옆 카드 밑으로 넘쳤는데
         .tx 만 재서 못 봤다('26-09-29 round2 적대 검토 H3). */
      p.querySelectorAll('.sl-body .tx, .sl-body .num > span').forEach(el => {
        const 칸 = el.closest('.v2-cell');
        if (!칸 || el.closest('svg')) return;
        const rg = document.createRange();
        rg.selectNodeContents(el);
        const q = rg.getBoundingClientRect(), c = 칸.getBoundingClientRect();
        if (q.width < 1) return;
        const 나감 = Math.round(Math.max(c.left - q.left, q.right - c.right));
        if (나감 > 4) 보기.push(((el.textContent || '').trim().slice(0, 12)) + ' ' + 나감 + 'px');
      });
      if (보기.length) 가로넘침.push({ n: i + 1, 곳: 보기.length, 보기: 보기.slice(0, 3) });
    });
    /* v2 그린 값 = 적힌 값 — **브라우저가 칠한 상자**에서 되읽는다('26-09-29 round2 적대 검토 H1·H2). 조립 게이트
       (slides_v2_gate.차트되읽기)는 HTML 속성(--v·dash)만 읽어, 행마다 다른 막대 트랙 폭(값 글 폭 탓)과 링 둥근 끝
       (CSS stroke-linecap, 굵기만큼 +4.5%p)을 못 봤다. 가로막대: 트랙 폭이 행마다 같은가 · 칠 끝/트랙 = 값 비(백분율은 값) ·
       비율링: dash + (둥근·네모 끝이면 굵기)/둘레 = 적힌 % · 점눈금: 점 가운데 ↔ 트랙 = 적힌 값 · 진행막대: 칠/트랙 = 적힌 %.
       문턱 1%(축 폭·100% 기준). 판형 v2 만 잰다. */
    const 차트어긋남 = [];
    const 배율 = { '조': 1e12, '억': 1e8, '천만': 1e7, '백만': 1e6, '만': 1e4, '천': 1e3 };
    const 글수 = t => {
      const s = String(t || ''), m = s.match(/-?\d[\d,]*(?:\.\d+)?/g);
      if (!m || m.length !== 1) return null;
      const u = s.slice(s.indexOf(m[0]) + m[0].length).match(/^\s*(조|억|천만|백만|만|천)/);
      return parseFloat(m[0].replace(/,/g, '')) * (u ? 배율[u[1]] : 1);
    };
    pages.forEach((p, i) => {
      if (!p.closest('.deck.v2')) return;
      const 보기 = [];
      p.querySelectorAll('.hbar').forEach(h => {
        const rows = [...h.children].filter(r => r.classList.contains('hbar__row'));
        const 상 = rows.map(r => {
          const t = r.querySelector('.hbar__track'), f = r.querySelector('.hbar__fill'), v = r.querySelector('.hbar__val');
          if (!t || !f) return null;
          const tr = t.getBoundingClientRect(), fr = f.getBoundingClientRect();
          return { w: tr.width, drawn: tr.width > 0 ? (fr.width > 0.5 ? fr.right - tr.left : 0) / tr.width : 0, v: v ? 글수(v.textContent) : null };
        }).filter(Boolean);
        const ws = 상.map(x => x.w);
        if (ws.length > 1 && Math.max(...ws) - Math.min(...ws) > 1)
          보기.push('가로막대 트랙 폭 ' + Math.round(Math.min(...ws)) + '~' + Math.round(Math.max(...ws)) + 'px');
        const 잰 = 상.filter(x => x.v !== null && x.v >= 0);
        if (h.dataset.scale === 'pct') {
          잰.forEach(x => { if (Math.abs(x.drawn * 100 - Math.min(100, x.v)) > 1) 보기.push('백분율 막대 ' + (x.drawn * 100).toFixed(1) + '% ↔ ' + x.v); });
        } else if (잰.length > 1) {
          const 큰 = 잰.reduce((a, b) => (b.v > a.v ? b : a));
          if (큰.v > 0 && 큰.drawn > 0) 잰.forEach(x => {
            if (Math.abs(x.drawn / 큰.drawn - x.v / 큰.v) > 0.01) 보기.push('막대 길이 비 ' + (x.drawn / 큰.drawn).toFixed(3) + ' ↔ 값 비 ' + (x.v / 큰.v).toFixed(3));
          });
        }
      });
      p.querySelectorAll('.ringc').forEach(c => {
        const 호 = c.querySelector('circle.ring-val'), n = c.querySelector('.num');
        const 적힌 = n ? 글수(n.textContent) : null;
        if (적힌 === null) return;
        if (!호) { if (적힌 > 1) 보기.push('링 호 없음 ↔ ' + 적힌 + '%'); return; }
        const r = parseFloat(호.getAttribute('r')) || 56, C = 2 * Math.PI * r;
        const L = parseFloat((호.getAttribute('stroke-dasharray') || '0').split(/[\s,]+/)[0]) || 0;
        const cap = getComputedStyle(호).strokeLinecap, sw = parseFloat(getComputedStyle(호).strokeWidth) || 0;
        const 보임 = Math.min(1, (L + (cap === 'round' || cap === 'square' ? sw : 0)) / C) * 100;
        if (Math.abs(보임 - 적힌) > 1) 보기.push('링 ' + 보임.toFixed(1) + '% ↔ ' + 적힌 + '%' + (cap !== 'butt' ? '(끝 ' + cap + ')' : ''));
      });
      p.querySelectorAll('.dotscale').forEach(d => {
        const cs = getComputedStyle(d), lo = parseFloat(cs.getPropertyValue('--min')), hi = parseFloat(cs.getPropertyValue('--max'));
        const tr = d.querySelector('.dotscale__track');
        if (!tr || !(hi > lo)) return;
        const t = tr.getBoundingClientRect();
        d.querySelectorAll('.dotscale__pt').forEach(pt => {
          const q = pt.getBoundingClientRect(), 글 = pt.querySelector('[data-derived="1"]');
          const 적힌 = 글 ? 글수(글.textContent) : null;
          if (적힌 === null || !(t.width > 0)) return;
          const 읽음 = lo + ((q.left + q.width / 2) - t.left) / t.width * (hi - lo);
          if (Math.abs(읽음 - 적힌) > (hi - lo) * 0.01) 보기.push('점눈금 ' + 읽음.toFixed(1) + ' 자리 ↔ ' + 적힌);
        });
      });
      p.querySelectorAll('.progress').forEach(g => {
        const t = g.querySelector('.progress__track'), f = g.querySelector('.progress__fill');
        const 끝 = [...(g.querySelector('.progress__legend') || { children: [] }).children].pop();
        const 적힌 = 끝 ? 글수(끝.textContent) : null;
        if (!t || !f || 적힌 === null) return;
        const w = t.getBoundingClientRect().width, 칠 = f.getBoundingClientRect().width;
        if (w > 0 && Math.abs(칠 / w * 100 - Math.min(100, 적힌)) > 1) 보기.push('진행막대 ' + (칠 / w * 100).toFixed(1) + '% ↔ ' + 적힌 + '%');
      });
      if (보기.length) 차트어긋남.push({ n: i + 1, 곳: 보기.length, 보기: 보기.slice(0, 4) });
    });

    /* [P3계약 신설] 비교·큰숫자·매트릭스·인용·타임라인 도입에 맞춘 구성 지표 7종.
       data-layout(신설 속성)과 DOM 프리미티브(.sl-fig/svg/table/img/.sl-picto/.sl-kpi)로만
       센다 — JSON 3층을 다시 훑지 않는 이유는 렌더 결과가 실제로 무엇을 보여주는지가
       중요해서다(자료가 시각이어도 조립이 글머리로 눌러 그렸으면 그게 사실이다).
       data-layout이 없는 장(옛 조립기 산출물)은 '?'로 묶어 종류 수를 거짓으로 부풀리지 않는다. */
    const 시각선택자 = '.sl-fig, svg, table, img, .sl-picto, .sl-kpi';
    const 레이아웃들 = pages.map(p => p.dataset.layout || '?');
    const 레이아웃종류 = new Set(레이아웃들).size;
    let 최대연속 = 0, 연속 = 0, 이전 = null;
    레이아웃들.forEach(l => { 연속 = (l === 이전) ? 연속 + 1 : 1; if (연속 > 최대연속) 최대연속 = 연속; 이전 = l; });

    let 글머리만장수 = 0, 시각합 = 0, 헤드길이최대 = 0, 항목최대 = 0, 백지장수 = 0;
    pages.forEach(p => {
      const 시각수 = p.querySelectorAll(시각선택자).length;
      시각합 += 시각수;
      const 글머리수 = p.querySelectorAll('.sl-l1, .sl-l2, .sl-l3, .sl-l4, .sl-agenda-i, [data-ent="항목"]').length;
      if (글머리수 > 0 && 시각수 === 0) 글머리만장수++;
      const 헤드 = p.querySelector('.sl-head');
      if (헤드) 헤드길이최대 = Math.max(헤드길이최대, (헤드.textContent || '').trim().length);
      const 항목수 = p.querySelectorAll('[data-ent="항목"]').length;
      if (항목수 > 항목최대) 항목최대 = 항목수;
      if (((p.textContent || '').replace(/\s+/g, '')).length === 0) 백지장수++;
    });

    /* [인상 지표 '26-09-28 신설 — 전부 soft, render_verify.sh 가 경고로만 찍는다]
       옛·v2 두 판형 공통(선택자는 .sl-head·.sl-foot·.sl-num·.sl-src·.sl-notes 만 쓴다).
       ① 판 채움: 본문 구역(머리 아래 ~ 꼬리말 위)에서 보이는 것(직접 글·svg·img·table·칠·테두리)이
          내려온 깊이 비율. 표지·간지·마무리·인용·목차 장은 안 잰다.
       ② 크기 대비: 장 안 글자 크기 최대/중앙.  ③ 캡션: 12pt(16px) 미만 글자 요소 수.
       ④ 글자 대비: 글자색 ↔ 실제 바탕색(조상의 첫 불투명 배경) 4.5:1(24pt 굵게 이상 3:1) 미만 수 —
          그라데이션·반투명 바탕 위 글자와 svg 글자는 잴 수 없어 뺀다(못 잰 것을 위반으로 세지 않는다). */
    const 인상 = (() => {
      const 덱 = document.querySelector('.deck');
      const 밀도 = 덱 && 덱.classList.contains('d-talk') ? '발표' : (덱 && 덱.classList.contains('d-handout') ? '배포' : '보고');
      const 표지류 = p => /(^|\s)(sl-cover|is-cover|is-divider|is-closing)(\s|$)/.test(p.className || '') ||
        ['표지', '간지', '마무리', '인용', '어젠다', '목차'].indexOf(p.dataset.layout || '') >= 0;
      const 보임 = el => {
        if (el.closest('[hidden], .sl-notes')) return false;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0.5 && r.height > 0.5;
      };
      const 직접글 = el => [...el.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim());
      const 색 = s => {
        const m = /rgba?\(([^)]+)\)/.exec(s || '');
        if (!m) return null;
        const v = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
        return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 };
      };
      const 휘도 = c => {
        const f = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
      };
      /* 요소 자신의 칠 — 색 | 'x'(그라데이션·반투명이라 잴 수 없음) | null(칠 없음) */
      const 칠 = n => {
        const cs = getComputedStyle(n);
        if (cs.backgroundImage && cs.backgroundImage !== 'none') return 'x';
        const c = 색(cs.backgroundColor);
        if (c && c.a >= 0.99) return c;
        if (c && c.a > 0.01) return 'x';
        if (typeof SVGGeometryElement !== 'undefined' && n instanceof SVGGeometryElement) {
          const f = 색(cs.fill);
          if (f && f.a > 0.01) return (f.a >= 0.99 && !(parseFloat(cs.fillOpacity) < 0.99)) ? f : 'x';
        }
        return null;
      };
      /* 실제 바탕 — 조상의 칠만 보면 격자 겹침·절대배치로 글자 **뒤에 깔린 곁가지**(타임라인 리본 띠 위
         흰 글자)를 놓쳐 흰 판 위 흰 글자(1.0)로 잘못 센다('26-09-28 v2 본보기 크롬 실측 — 9장 리본 4건).
         그래서 조상마다 먼저 그 조상 안 곁가지(글자를 품지 않은 자손) 가운데 글자 가운데 점을 덮는
         칠을 찾고(문서 순서 뒤의 것이 위에 칠해진다), 없으면 조상 자신의 칠을 본다. 쪽(.sl-page) 위로는
         곁가지를 찾지 않는다(쪽끼리는 겹치지 않는다). 배치가 없는 환경(jsdom — 상자 0)은 조상만 본다. */
      const 바탕 = el => {
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const 덮음 = m => {
          const q = m.getBoundingClientRect();
          return q.width > 0.5 && q.height > 0.5 && q.left <= cx && cx <= q.right && q.top <= cy && cy <= q.bottom;
        };
        let 아래 = el, 쪽위 = false;
        for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
          if (n !== el && !쪽위 && r.width > 0.5) {
            let 곁 = null;
            for (const m of n.querySelectorAll('*')) {
              if (m === 아래 || 아래.contains(m) || m.closest('[hidden], .sl-notes')) continue;
              const c = 칠(m);
              if (c !== null && 덮음(m)) 곁 = c;
            }
            if (곁 !== null) return 곁 === 'x' ? null : 곁;
          }
          const c = 칠(n);
          if (c !== null) return c === 'x' ? null : c;
          if (n.matches && n.matches('.sl-page')) 쪽위 = true;
          아래 = n;
        }
        return { r: 255, g: 255, b: 255, a: 1 };
      };
      const 장들 = [], 빈띠들 = [], 빈상자들 = [];
      let 작은합 = 0, 낮은합 = 0;
      const 작은보기 = [], 낮은보기 = [];
      pages.forEach((p, i) => {
        const 크기들 = [];
        [...p.querySelectorAll('*')].forEach(el => {
          if (!직접글(el) || !보임(el)) return;
          const cs = getComputedStyle(el);
          const fs = parseFloat(cs.fontSize);
          if (!(fs > 0)) return;
          크기들.push(fs);
          const 글 = (el.textContent || '').trim().slice(0, 16);
          if (fs < 15.95) { 작은합++; if (작은보기.length < 4) 작은보기.push((i + 1) + '장 ' + 글 + ' ' + fs.toFixed(1) + 'px'); }
          if (el instanceof SVGElement) return;
          const fg = 색(cs.color), bg = 바탕(el);
          if (!fg || !bg || fg.a < 0.99) return;
          const L1 = 휘도(fg), L2 = 휘도(bg);
          const 비 = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
          const 큰글 = fs >= 32 && (parseInt(cs.fontWeight, 10) || 400) >= 700;
          if (비 < (큰글 ? 3 : 4.5)) { 낮은합++; if (낮은보기.length < 4) 낮은보기.push((i + 1) + '장 ' + 글 + ' ' + 비.toFixed(1)); }
        });
        크기들.sort((a, b) => a - b);
        const 중앙 = 크기들.length ? 크기들[Math.floor(크기들.length / 2)] : 0;
        const 크기비 = 중앙 ? +(크기들[크기들.length - 1] / 중앙).toFixed(2) : null;
        let 채움 = null;
        const pr = p.getBoundingClientRect();
        if (!표지류(p) && pr.height > 0) {
          const pcs = getComputedStyle(p);
          const 머리 = p.querySelector('.sl-head');
          const 꼬리 = p.querySelector('.sl-foot, .sl-num');
          const 위 = 머리 && 보임(머리) ? 머리.getBoundingClientRect().bottom : pr.top + (parseFloat(pcs.paddingTop) || 0);
          const 아래 = 꼬리 && 보임(꼬리) ? 꼬리.getBoundingClientRect().top : pr.bottom - (parseFloat(pcs.paddingBottom) || 0);
          let 끝 = 위;
          p.querySelectorAll('*').forEach(el => {
            if (el.closest('.sl-head, .sl-foot, .sl-num, .sl-src')) return;
            if (el.matches('.sl-body')) return;      /* 본문 그릇 자체의 판 칠은 내용이 아니다(칸·카드는 센다) */
            if (!보임(el)) return;
            const ecs = getComputedStyle(el);
            const 칠 = 색(ecs.backgroundColor);
            const 보이는것 = 직접글(el) || /^(svg|img|table|canvas)$/i.test(el.tagName) || (칠 && 칠.a > 0.05) ||
              parseFloat(ecs.borderTopWidth) > 0 || parseFloat(ecs.borderBottomWidth) > 0;
            if (!보이는것) return;
            const b = Math.min(el.getBoundingClientRect().bottom, 아래);
            if (b > 끝) 끝 = b;
          });
          if (아래 - 위 > 10) 채움 = +((끝 - 위) / (아래 - 위)).toFixed(2);
        }
        장들.push([i + 1, 채움, 표지류(p) ? null : 크기비]);
        /* ⑤ 빈 띠('26-09-29 bench11 — 판 채움 ①은 '가장 깊이 내려온 곳'만 봐서, 카드가 가운데 띠에 몰리고
           위아래가 비어도 0.97 로 읽혔다): 본문 구역에서 **잉크**(글 줄 네모·svg·img·글 없는 칠 조각 — 막대·띠·점)가
           하나도 없는 가장 긴 세로 띠 / 구역 높이. 카드·패널 바탕은 잉크로 치지 않는다(속이 빈 카드도 빈 띠다). */
        if (!표지류(p) && pr.height > 0) {
          const 머리 = p.querySelector('.sl-head'), 꼬리 = p.querySelector('.sl-foot, .sl-num');
          const pcs = getComputedStyle(p);
          const 위 = 머리 && 보임(머리) ? 머리.getBoundingClientRect().bottom : pr.top + (parseFloat(pcs.paddingTop) || 0);
          const 아래 = 꼬리 && 보임(꼬리) ? 꼬리.getBoundingClientRect().top : pr.bottom - (parseFloat(pcs.paddingBottom) || 0);
          const 구간 = [], 잉크 = [], 상자 = [];
          const 넣기 = q => { const a = Math.max(q.top, 위), b = Math.min(q.bottom, 아래); if (b - a > 0.5) 구간.push([a, b]);
            잉크.push([q.top, q.bottom, q.left, q.right]); };
          /* 진한 칠('26-09-29 round2): 판 바탕과 3:1 넘게 대비되는 칠(단색·그라데이션 색 평균)은 글을 품어도 덩어리로
             보인다 — 남색 요청상자 속 여백을 빈 띠로 세면 판을 꽉 채운 상자가 0.33 으로 읽혔다(본보기 약한 덱 4장). */
          const 판칠 = 칠(p);
          const L판 = 휘도(판칠 && 판칠 !== 'x' ? 판칠 : { r: 255, g: 255, b: 255 });
          const 진한칠 = el => {
            const cs = getComputedStyle(el), 색들 = [];
            const c0 = 색(cs.backgroundColor);
            if (c0 && c0.a > 0.5) 색들.push(c0);
            if (cs.backgroundImage && cs.backgroundImage !== 'none')
              (cs.backgroundImage.match(/rgba?\([^)]*\)/g) || []).forEach(s => { const x = 색(s); if (x && x.a > 0.5) 색들.push(x); });
            if (!색들.length) return false;
            const L = 색들.reduce((s, x) => s + 휘도(x), 0) / 색들.length;
            return (Math.max(L, L판) + 0.05) / (Math.min(L, L판) + 0.05) >= 3;
          };
          p.querySelectorAll('*').forEach(el => {
            if (el.closest('.sl-head, .sl-foot, .sl-num, [hidden], .sl-notes, .ds-sprite')) return;
            if (!보임(el)) return;
            if (/^(svg|img|canvas)$/i.test(el.tagName)) { 넣기(el.getBoundingClientRect()); return; }
            if (el instanceof SVGElement) return;
            [...el.childNodes].forEach(n => {
              if (n.nodeType !== 3 || !n.nodeValue.trim()) return;
              const rg = document.createRange(); rg.selectNodeContents(n);
              [...rg.getClientRects()].forEach(넣기);
            });
            if (진한칠(el)) { 넣기(el.getBoundingClientRect()); return; }
            const ecs = getComputedStyle(el);
            const c = 색(ecs.backgroundColor);
            if (c && c.a > 0.05 && !(el.textContent || '').trim()) {
              const q = el.getBoundingClientRect();
              if (q.height < (아래 - 위) * 0.5) 넣기(q);     /* 막대·띠·점 같은 칠 조각(판만 한 빈 칠은 빼고) */
            }
            /* 상자('26-09-29 bench13 ①) — 판과 다른 옅은 칠이나 테두리 두 변 이상, 쪽 폭 12%·높이 18% 이상 */
            const 칠있음 = c && c.a > 0.05 && Math.abs(휘도(c) - L판) > 0.004;
            const 변 = ['Top', 'Bottom', 'Left', 'Right'].filter(k => parseFloat(ecs['border' + k + 'Width']) >= 1).length;
            if (칠있음 || 변 >= 2) {
              const q = el.getBoundingClientRect();
              if (q.width >= pr.width * 0.12 && q.height >= pr.height * 0.18 && q.width < pr.width * 0.99) 상자.push([el, q]);
            }
          });
          구간.sort((x, y) => x[0] - y[0]);
          let 끝 = 위, 최대 = 0;
          구간.forEach(([a, b]) => { if (a > 끝) 최대 = Math.max(최대, a - 끝); 끝 = Math.max(끝, b); });
          최대 = Math.max(최대, 아래 - 끝);
          if (아래 - 위 > 10) 빈띠들.push([i + 1, +(최대 / (아래 - 위)).toFixed(2)]);
          /* ⑥ 빈 상자 넓이('26-09-29 bench13 ① — 심사 3인 '카드는 큰데 속이 비었다' 1.2건/덱): 가장 바깥 상자마다
             (폭 × 구역 안 높이 × 상자 높이 중 잉크 없는 줄 비율)의 합 / 구역 넓이. 빈 띠(⑤)는 옆 칸에 글이 있으면
             속 빈 카드를 못 본다. 문턱은 render_verify.sh(무프롬프트 기준선 덱 분포). */
          if (아래 - 위 > 10) {
            const 바깥 = 상자.filter(([el]) => !상자.some(([o]) => o !== el && o.contains(el)));
            let 빈 = 0;
            바깥.forEach(([el, q]) => {
              const 속 = 잉크.filter(([t, b, l, r]) => l < q.right - 1 && r > q.left + 1 && b > q.top + 1 && t < q.bottom - 1)
                .map(([t, b]) => [Math.max(t, q.top), Math.min(b, q.bottom)]).sort((x, y) => x[0] - y[0]);
              let 끝2 = q.top, 덮 = 0;
              속.forEach(([a, b]) => { if (b > 끝2) { 덮 += b - Math.max(a, 끝2); 끝2 = b; } });
              const h = Math.max(0, Math.min(q.bottom, 아래) - Math.max(q.top, 위));
              빈 += q.width * h * (1 - 덮 / Math.max(1, q.height));
            });
            빈상자들.push([i + 1, +(빈 / (pr.width * (아래 - 위))).toFixed(2)]);
          }
        }
      });
      return { 밀도: 밀도, 장: 장들, 빈띠: 빈띠들, 빈상자: 빈상자들, small_text: 작은합, small_samples: 작은보기,
               low_contrast: 낮은합, low_samples: 낮은보기 };
    })();

    document.body.dataset.audit = JSON.stringify(
      { 장르: genre, splits, splitWords, slides: pages.length, overflows, h_overflows: 가로넘침, chart_mismatch: 차트어긋남,
        compressed: document.querySelectorAll('.jachigan-run').length,
        bullet_only_ratio: +(글머리만장수 / pages.length).toFixed(2),
        layout_variety: 레이아웃종류,
        max_same_run: 최대연속,
        visuals_per_slide: +(시각합 / pages.length).toFixed(2),
        head_len_max: 헤드길이최대,
        items_max: 항목최대,
        blank_slides: 백지장수,
        impression: 인상 });
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
