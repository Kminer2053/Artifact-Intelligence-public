/* 관인 위치 — 발신 명의 '마지막 글자'의 가운데에 인영 중심을 맞춘다.
   근거: 행정업무의 운영 및 혁신에 관한 규정 시행규칙 제11조제1항
   "관인을 찍는 경우에는 발신 명의 표시의 마지막 글자가 인영의 가운데에 오도록 한다."
   글자 폭은 글꼴·글자 수마다 달라 브라우저에서만 잴 수 있다. */
window.addEventListener('load', () => {
  const seal = document.querySelector('.gm-seal:not(.right)');
  const name = document.querySelector('.gm-sign .gm-name');
  if (!seal || !name) return;
  const node = [...name.childNodes].find(n => n.nodeType === 3 && n.nodeValue.trim());
  if (!node) return;
  const v = node.nodeValue.replace(/\s+$/, '');
  if (!v) return;
  const r = document.createRange();
  r.setStart(node, v.length - 1);
  r.setEnd(node, v.length);
  const 글자 = r.getBoundingClientRect();
  const 줄 = name.parentElement.getBoundingClientRect();
  const 치우침 = 글자.left + 글자.width / 2 - (줄.left + 줄.width / 2);
  seal.style.setProperty('--gm-half', 치우침.toFixed(1) + 'px');
});
