#!/usr/bin/env python3
"""ontology.json → 검토본 HTML (사람용 뷰).
개체 × 3요소로 펼쳐 도메인 전문가가 규칙별로 판정(맞음/틀림/누락)할 수 있게 렌더.
SSOT(ontology.json) → 사람용 뷰의 첫 자동 생성. 재실행 안전."""
import html
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(BASE, "ontology.json"), encoding="utf-8"))

ELEM_COLOR = {"구성": "#2f5597", "문체": "#7030a0", "디자인": "#548235"}


def esc(x):
    return html.escape(str(x))


def render_val(v, depth=0):
    """값을 읽기 쉬운 HTML로. dict/list/scalar 재귀."""
    if isinstance(v, dict):
        rows = []
        for k, vv in v.items():
            if k.startswith("_"):
                continue
            label = "근거" if k == "근거" else esc(k)
            cls = ' class="geun"' if k == "근거" else ""
            rows.append(f'<div class="kv"{cls}><span class="k">{label}</span>'
                        f'<span class="v">{render_val(vv, depth+1)}</span></div>')
        return "".join(rows)
    if isinstance(v, list):
        if all(not isinstance(x, (dict, list)) for x in v):
            return " · ".join(esc(x) for x in v)
        return "".join(f'<div class="li">{render_val(x, depth+1)}</div>' for x in v)
    return esc(v)


def elem_block(name, obj):
    if name not in obj:
        return ""
    color = ELEM_COLOR.get(name, "#555")
    return (f'<div class="elem" style="border-left-color:{color}">'
            f'<div class="elem-h" style="color:{color}">{name}</div>'
            f'<div class="elem-b">{render_val(obj[name])}</div></div>')


def entity_card(name, e, kind="개체"):
    appear = e.get("등장", e.get("등장조건", ""))
    role = e.get("역할", e.get("label", ""))
    badge = f'<span class="badge">{esc(kind)}</span>'
    if e.get("status") == "미구현":
        badge += '<span class="badge todo">미구현</span>'
    head = (f'<div class="ent-head"><h3>{esc(e.get("label", name))}</h3>{badge}</div>'
            f'<div class="ent-meta">{esc(role)}'
            + (f' · <b>등장</b>: {esc(appear)}' if appear else "") + '</div>')
    body = "".join(elem_block(el, e) for el in ["구성", "문체", "디자인"])
    if not body and e.get("status") == "미구현":
        body = f'<div class="note">{esc(e.get("_note", ""))}</div>'
    verdict = ('<div class="verdict">검토: '
               '<label><input type="checkbox"> 맞음</label> '
               '<label><input type="checkbox"> 틀림/현실과 다름</label> '
               '<label><input type="checkbox"> 빠진 규칙 있음</label> '
               '<label><input type="checkbox"> 1층에서 정하면 안 됨(3층으로)</label>'
               '<div class="memo" contenteditable="true" data-ph="메모…"></div></div>')
    return f'<div class="card">{head}{body}{verdict}</div>'


parts = []
# 문서유형 전역
dt = d["document_types"]["onepage-report"]
parts.append('<section><h2>① 문서유형 전역 방법론 — 1페이지 보고서</h2>'
             '<p class="sec-desc">개체가 아니라 이 문서유형 전체에 걸리는 규칙(여백·분량·목차로직·게이트).</p>')
parts.append('<div class="card"><div class="ent-head"><h3>1p 보고서 전역</h3>'
             '<span class="badge">문서유형</span></div>')
for el in ["구성", "문체", "디자인"]:
    parts.append(elem_block(el, dt))
for extra in ["분량예산", "게이트"]:
    if extra in dt:
        parts.append(f'<div class="elem" style="border-left-color:#888">'
                     f'<div class="elem-h" style="color:#888">{extra}</div>'
                     f'<div class="elem-b">{render_val(dt[extra])}</div></div>')
parts.append('<div class="verdict">검토: '
             '<label><input type="checkbox"> 맞음</label> '
             '<label><input type="checkbox"> 틀림</label> '
             '<label><input type="checkbox"> 빠짐</label>'
             '<div class="memo" contenteditable="true"></div></div></div></section>')

# 개체
parts.append('<section><h2>② 개체 카탈로그 (개체 × 3요소)</h2>'
             '<p class="sec-desc">각 개체를 열면 구성·문체·디자인 방법론이 함께. 개체 목록(제목/요약박스/본문/붙임)이 맞는지, 각 요소 규칙이 맞는지 봐주세요.</p>')
for name, e in d["entities"].items():
    parts.append(entity_card(name, e))
parts.append('</section>')

# 데이터 등장요소
parts.append('<section><h2>③ 데이터에 따라 등장하는 요소</h2>'
             '<p class="sec-desc">개체가 아님. 맥락 데이터를 봐야 등장 여부가 정해지는 것(표·이미지). 이 판단을 1층이 아니라 3층에 두는 게 맞는지.</p>')
for name, e in d["data_elements"].items():
    if name.startswith("_"):
        continue
    parts.append(entity_card(name, e, kind="등장요소"))
parts.append('</section>')

# 문체 프로파일 + 공통
parts.append('<section><h2>④ 문체 프로파일 · 공통 규칙</h2>'
             '<p class="sec-desc">여러 개체가 공유하는 문체(공문서-개조식)와 강조·표기 규범.</p>')
wp = d["writing_profiles"]["gongmun-gaejosik"]
parts.append(f'<div class="card"><div class="ent-head"><h3>공문서-개조식 문체</h3><span class="badge">문체 프로파일</span></div>'
             f'<div class="elem-b">{render_val({k: v for k, v in wp.items() if not k.startswith("_")})}</div>'
             '<div class="verdict">검토: <label><input type="checkbox"> 맞음</label> '
             '<label><input type="checkbox"> 틀림</label> <label><input type="checkbox"> 빠짐</label>'
             '<div class="memo" contenteditable="true"></div></div></div>')
parts.append(f'<div class="card"><div class="ent-head"><h3>공통: 강조 · 표기</h3><span class="badge">shared</span></div>'
             f'<div class="elem-b">{render_val({k: v for k, v in d["shared"].items() if not k.startswith(("_", "enforcer"))})}</div>'
             '<div class="verdict">검토: <label><input type="checkbox"> 맞음</label> '
             '<label><input type="checkbox"> 틀림</label> <label><input type="checkbox"> 빠짐</label>'
             '<div class="memo" contenteditable="true"></div></div></div>')
parts.append('</section>')

body = "\n".join(parts)
gen = "ontology.json에서 자동 생성 (SSOT→사람용 뷰)"
out = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>1층 온톨로지 검토본 — 1p 보고서</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "Apple SD Gothic Neo","Malgun Gothic",sans-serif; max-width: 1000px;
  margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.55; background:#fafafa; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
.lead {{ color:#666; margin:0 0 24px; font-size:14px; }}
h2 {{ font-size:19px; margin: 32px 0 6px; padding-bottom:6px; border-bottom:2px solid #1F3864; color:#1F3864; }}
.sec-desc {{ color:#666; font-size:13.5px; margin:0 0 14px; }}
.card {{ background:#fff; border:1px solid #e2e2e2; border-radius:8px; padding:16px 18px; margin:0 0 14px;
  box-shadow:0 1px 3px rgba(0,0,0,.04); }}
.ent-head {{ display:flex; align-items:center; gap:8px; }}
.ent-head h3 {{ font-size:17px; margin:0; }}
.badge {{ font-size:11px; background:#eef; color:#3355aa; padding:2px 8px; border-radius:10px; }}
.badge.todo {{ background:#fee; color:#c00; }}
.ent-meta {{ color:#777; font-size:13px; margin:2px 0 12px; }}
.elem {{ border-left:4px solid #555; padding:2px 0 2px 12px; margin:10px 0; }}
.elem-h {{ font-weight:700; font-size:14px; margin-bottom:4px; }}
.elem-b {{ font-size:13.5px; }}
.kv {{ display:flex; gap:8px; margin:2px 0; align-items:baseline; }}
.kv .k {{ color:#888; min-width:96px; flex-shrink:0; font-size:12.5px; }}
.kv .v {{ flex:1; }}
.kv.geun {{ opacity:.6; }} .kv.geun .k {{ color:#a80; }}
.li {{ padding:1px 0 1px 10px; border-left:1px dotted #ccc; margin:2px 0; }}
.note {{ color:#777; font-style:italic; font-size:13px; }}
.verdict {{ margin-top:12px; padding-top:10px; border-top:1px dashed #ddd; font-size:12.5px; color:#555; }}
.verdict label {{ margin-right:10px; white-space:nowrap; cursor:pointer; }}
.memo {{ border:1px solid #e0e0e0; border-radius:5px; min-height:26px; margin-top:6px; padding:5px 8px;
  background:#fffdf5; font-size:13px; }}
.memo:empty:before {{ content:"메모…"; color:#bbb; }}
.legend {{ font-size:12.5px; color:#666; margin:0 0 20px; padding:10px 14px; background:#eef4ff; border-radius:6px; }}
.legend b {{ color:#1F3864; }}
.savebar {{ position:sticky; top:0; z-index:9; background:#1F3864; color:#fff; padding:8px 14px;
  border-radius:6px; margin:0 0 16px; display:flex; align-items:center; gap:12px; font-size:13px; }}
.savebar button {{ background:#fff; color:#1F3864; border:0; border-radius:4px; padding:5px 12px;
  font-size:12.5px; cursor:pointer; font-weight:600; }}
.savebar .status {{ opacity:.85; font-size:12px; }}
</style></head><body>
<div class="savebar">
  <span>✔ 체크·메모는 <b>자동 저장</b>됩니다(브라우저에 보관)</span>
  <button onclick="exportReview()">검토결과 복사</button>
  <span class="status" id="stat"></span>
</div>
<script>
const KEY = 'ontology-review-v1';
function collect() {{
  const out = [];
  document.querySelectorAll('.card').forEach((card, i) => {{
    const title = card.querySelector('h3')?.textContent || ('card' + i);
    const checked = [...card.querySelectorAll('.verdict input')].map(x => x.checked);
    const labels = [...card.querySelectorAll('.verdict input:checked')].map(x => x.parentElement.textContent.trim());
    const memo = card.querySelector('.memo')?.textContent.trim() || '';
    out.push({{ i, title, checked, labels, memo }});
  }});
  return out;
}}
function save() {{
  localStorage.setItem(KEY, JSON.stringify(collect()));
  const s = document.getElementById('stat');
  s.textContent = '저장됨 ' + new Date().toLocaleTimeString('ko-KR');
}}
function restore() {{
  const raw = localStorage.getItem(KEY); if (!raw) return;
  try {{
    JSON.parse(raw).forEach(rec => {{
      const card = document.querySelectorAll('.card')[rec.i]; if (!card) return;
      const boxes = card.querySelectorAll('.verdict input');
      (rec.checked || []).forEach((v, j) => {{ if (boxes[j]) boxes[j].checked = v; }});
      const m = card.querySelector('.memo'); if (m && rec.memo) m.textContent = rec.memo;
    }});
    document.getElementById('stat').textContent = '이전 검토 복원됨';
  }} catch (e) {{}}
}}
function exportReview() {{
  const marked = collect().filter(r => r.labels.length || r.memo);
  const txt = marked.map(r => `[${{r.title}}] ${{r.labels.join(', ') || '-'}}${{r.memo ? '\\n  메모: ' + r.memo : ''}}`).join('\\n');
  navigator.clipboard.writeText(txt || '(검토 표시 없음)');
  document.getElementById('stat').textContent = '복사됨 — 대화창에 붙여넣으세요';
}}
addEventListener('load', () => {{
  restore();
  document.addEventListener('change', e => {{ if (e.target.matches('.verdict input')) save(); }});
  document.addEventListener('input', e => {{ if (e.target.matches('.memo')) save(); }});
  document.addEventListener('blur', e => {{ if (e.target.matches('.memo')) save(); }}, true);
}});
</script>
<h1>1층 온톨로지 검토본 — 1페이지 보고서</h1>
<p class="lead">{gen} · 개체 × 3요소 구조</p>
<div class="legend">
<b>검토 방법</b>: 각 개체·규칙을 읽고 아래 체크로 판정하세요. 코드 볼 필요 없이 내용만 보시면 됩니다.<br>
· <b style="color:#2f5597">구성</b>(정보 흐름·목차·위계) · <b style="color:#7030a0">문체</b>(문장·종결·길이) · <b style="color:#548235">디자인</b>(시각·마커·CSS)<br>
· 특히 봐주실 것: ① 개체 목록(제목/요약/본문/붙임)이 맞나 ② 각 규칙이 현실과 맞나(45자·여백·붙임 등) ③ 1층에서 정하면 안 되는 걸 정했나(데이터가 정할 것) ④ 빠진 규칙<br>
· 회색 흐린 <b style="color:#a80">근거</b>는 그 규칙의 출처. 무시하고 내용만 보셔도 됩니다.
</div>
{body}
</body></html>"""

with open(os.path.join(BASE, "review.html"), "w", encoding="utf-8") as f:
    f.write(out)
print("written: ontology/review.html")
