/* present.js — 슬라이드 발표 보기의 화면 제어. 정본: ontology slides.화면기능.
 *
 *   · 앞뒤 이동  : 이전/다음 슬라이드로 부드럽게 이동(제어 바 + 방향키·PageUp/Down)
 *   · PDF        : 브라우저 인쇄로 저장(=@page 16:9 규격 그대로 PDF)
 *   · 목차 점프  : 어젠다 항목을 누르면 같은 순서의 간지(섹션)로 이동
 *
 * 셋 다 **기본 탑재**다. 문서의 doc["화면"] 플래그(false)로 하나씩 뺀다 — 편집기 디자인
 * 영역이 그 플래그를 세운다. 인쇄(PDF)에는 제어 바가 안 나온다(@media print).
 * 이 파일은 그리기(svgfig.js)·감사(audit.js)와 나란한 화면 계층이라 조판·게이트를
 * 건드리지 않는다(제어 바는 position:fixed 라 장별 넘침 측정 밖이다). */
(function () {
  "use strict";
  var el = document.getElementById("fr-doc");
  var doc = {};
  try { doc = JSON.parse(el.textContent); } catch (e) { doc = {}; }
  var 화면 = doc["화면"] || {};
  var on = function (k) { return 화면[k] !== false; };   // 없으면 기본 true

  var pages = Array.prototype.slice.call(document.querySelectorAll(".sl-page"));
  if (pages.length < 2) return;

  function current() {
    var mid = window.scrollY + window.innerHeight / 2, best = 0, bd = Infinity;
    pages.forEach(function (p, i) {
      var d = Math.abs((p.offsetTop + p.offsetHeight / 2) - mid);
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  }
  function goto(i) {
    i = Math.max(0, Math.min(pages.length - 1, i));
    pages[i].scrollIntoView({ behavior: "smooth", block: "center" });
  }

  /* ── 목차 점프 — 어젠다 항목 → 같은 순서의 간지(없으면 텍스트 매칭) ── */
  if (on("목차점프")) {
    var 간지 = pages.filter(function (p) { return p.classList.contains("sl-간지"); });
    Array.prototype.slice.call(document.querySelectorAll(".sl-agenda-i")).forEach(function (a, i) {
      var t = a.textContent.trim();
      var target = 간지[i] || 간지.filter(function (g) { return g.textContent.indexOf(t) >= 0; })[0];
      if (!target) return;
      a.classList.add("sl-jump");
      a.setAttribute("role", "link");
      a.setAttribute("tabindex", "0");
      var jump = function () { target.scrollIntoView({ behavior: "smooth", block: "center" }); };
      a.addEventListener("click", jump);
      a.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); jump(); }
      });
    });
  }

  /* ── 제어 바 — 앞뒤 이동 · PDF ── */
  if (on("앞뒤이동") || on("PDF")) {
    var bar = document.createElement("div");
    bar.className = "sl-controls";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "슬라이드 제어");
    var h = "";
    if (on("앞뒤이동")) {
      h += '<button class="slc-btn" data-act="prev" aria-label="이전 슬라이드">‹</button>'
        + '<span class="slc-num"><b id="slc-cur">1</b> / ' + pages.length + "</span>"
        + '<button class="slc-btn" data-act="next" aria-label="다음 슬라이드">›</button>';
    }
    if (on("PDF")) {
      if (on("앞뒤이동")) h += '<span class="slc-sep"></span>';
      h += '<button class="slc-btn slc-pdf" data-act="pdf" aria-label="PDF로 저장">⤓ PDF</button>';
    }
    bar.innerHTML = h;
    document.body.appendChild(bar);
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("[data-act]");
      if (!b) return;
      var act = b.getAttribute("data-act");
      if (act === "prev") goto(current() - 1);
      else if (act === "next") goto(current() + 1);
      else if (act === "pdf") window.print();
    });
    var cur = document.getElementById("slc-cur");
    if (cur) {
      var upd = function () { cur.textContent = current() + 1; };
      window.addEventListener("scroll", upd, { passive: true });
      upd();
    }
  }

  /* ── 키보드 — 좌우·PageUp/Down 로 이동(위아래는 일반 스크롤로 남긴다) ── */
  if (on("앞뒤이동")) {
    document.addEventListener("keydown", function (e) {
      if (e.target.closest && e.target.closest("input,textarea,[contenteditable]")) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); goto(current() + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); goto(current() - 1); }
    });
  }

  /* ── 진입 애니메이션 — 목적 있는 절제(정본 slides.애니메이션) ──
   * 점진적 향상: JS 가 있을 때만 data-anim 을 달아 슬라이드를 숨겼다 보인다(JS 없으면 정적).
   * 접근성: prefers-reduced-motion 이면 아예 켜지 않는다(WCAG 2.1). 인쇄엔 CSS 가 끈다.
   * 화면에 들어온 슬라이드에 .sl-in 을 달아 CSS 진입 효과를 트리거한다(주의 유도·순차 공개). */
  var 효과 = doc["효과"] || "페이드";                       // 기본 페이드(가장 중립·전문적)
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (효과 !== "없음" && !reduce && "IntersectionObserver" in window) {
    document.documentElement.setAttribute("data-anim", 효과);
    if (효과 === "순차") {                                  // 항목을 하나씩(segmenting) — 지연 인덱스
      pages.forEach(function (p) {
        Array.prototype.forEach.call(
          p.querySelectorAll(".sl-body > *, .sl-pictos > *"),
          function (k, i) { k.style.setProperty("--i", i); });
      });
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("sl-in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.18 });
    pages.forEach(function (p) { io.observe(p); });
  }
})();
