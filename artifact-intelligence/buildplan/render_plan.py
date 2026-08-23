#!/usr/bin/env python3
"""빌드플랜 JSON → 승인용 HTML 뷰 (v2 — 사람말 번역 계층 포함).
원칙: 빌드플랜 JSON은 기계·감사용, 이 화면은 사람용. 내부 표기(규칙 ID·경로·층 용어)는
번역하거나 숨긴다. 긴 문단은 문장 단위로 끊어 보여준다.
사용: python3 render_plan.py [plan.json] → plan.html"""
import html
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))   # 코드뿌리/buildplan (예시·스키마·CSS)
ROOT = os.path.dirname(BASE)

# 플랜과 승인 화면은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
import importlib.util as _iu
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(ROOT, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "example-ev-charger.json")
p = json.load(open(src, encoding="utf-8"))


# ── 사람말 번역 계층 ──────────────────────────────────────────
STRIP_PATTERNS = [
    # 괄호 안 내부 인용 제거: (R구-19), (근거: ...), (§3-4), (entities..., _model, ARCHITECTURE §2) 등
    r"\s*[\(（][^)）]*(?:R[구문레진유지]\s*[-‐]\s*\d+|§|entities\.|document_types\.|ontology|ARCHITECTURE|_model|schema|json_field|e2e)[^)）]*[\)）]",
    # 표기만 남은 규칙 ID·경로
    r"R[구문레진유지]\s*[-‐]\s*\d+[호의번]?",
    r"(?:entities|document_types|writing_profiles|data_elements|shared)\.[\w가-힣.·_\[\]]+",
    r"references/[\w\-.]+",
    r"§\s*[\d\-]+[번호]?",
]
TRANSLATE = [
    (r"온톨로지 원칙상\s*", ""),
    (r"온톨로지", "작성 규칙집"),
    (r"3층에서", "내용을 쓸 때"),
    (r"3층이", "내용 작성 단계에서"),
    (r"3층", "내용 작성 단계"),
    (r"2층", "설계 단계"),
    (r"1층", "규칙집"),
    (r"요청드림 강도", "요청 표현의 수위"),
    (r"두괄식", "결론 먼저 쓰기"),
    (r"불변규칙", "기본 원칙"),
    (r"개체", "구성 요소"),
    (r"인스턴스", "초안"),
    (r"다시 볼 이유", "설계를 다시 볼 사유"),
]


def human(s):
    """내부 표기를 사람말로. 남는 이중 공백·고아 구두점 정리."""
    s = str(s)
    for pat in STRIP_PATTERNS:
        s = re.sub(pat, "", s)
    for pat, rep in TRANSLATE:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.·)\]])", r"\1", s)
    s = re.sub(r"[\(（]\s*[\)）]", "", s)
    return s.strip(" -—·,")


def esc(x):
    return html.escape(human(x))


def sentences(s, limit=90):
    """긴 문단을 문장 단위로 끊어 리스트 HTML로. 짧으면 그대로."""
    s = human(s)
    if len(s) <= limit:
        return esc_raw(s)
    parts = re.split(r"(?<=[다음됨임함봄])\.\s+|(?<=\.)\s+(?=[가-힣A-Z(])", s)
    parts = [x.strip().rstrip(".") for x in parts if x.strip()]
    if len(parts) <= 1:
        return esc_raw(s)
    return "<ul class='sent'>" + "".join(f"<li>{esc_raw(x)}.</li>" for x in parts) + "</ul>"


def esc_raw(x):
    return html.escape(str(x))


j = p.get("판정", {}); j = j if isinstance(j, dict) else {}
r = p.get("요구분석", {}); r = r if isinstance(r, dict) else {}
ask = r.get("확인필요", []) or []
ask = ask if isinstance(ask, list) else []
appr = p.get("승인", {})
status_h = {"되묻기중": "확인 대기", "대기": "승인 대기", "승인": "승인됨", "수정요청": "수정 요청됨"}.get(appr.get("status", ""), appr.get("status", ""))

type_h = human(j.get("보고목적유형", "?")).lstrip("①②③④⑤⑥⑦⑧⑨⑩⑪ ")

_web = "--web" in sys.argv          # 웹앱 임베드: 확정 버튼을 앱이 대므로 히어로 안 버튼은 생략
hero_r = "" if _web else '''<div class="hero-r">
    <div class="lab">이 방향이 맞습니까?</div>
    <div class="btns">
      <button class="ok" onclick="mark('승인')">네, 이대로 진행</button>
      <button class="no" onclick="mark('수정요청')">아니요, 수정할게요</button>
    </div>
    <div id="res" class="res"></div>
  </div>'''

head = f"""
<div class="hero">
  <div class="hero-l">
    <div class="lab">이 요청을 이렇게 만들려고 합니다</div>
    <div class="big">{esc_raw(type_h)}</div>
    <div class="sub">A4 한 장 보고서 · 판단 확신: {esc(j.get('확신도', '?'))}</div>
  </div>
  {hero_r}
</div>
<div class="why"><b>왜 이렇게 판단했나</b>{sentences(j.get('근거', ''))}</div>
"""

askbox = ""
if ask:
    items = "".join(
        f'<div class="ask"><div class="ask-q">Q{i+1}. {esc(a.get("질문",""))}</div>'
        f'<div class="ask-w">{sentences(a.get("왜",""), 120)}</div>'
        f'<textarea placeholder="답변을 적어주세요…" data-ask="{esc_raw(a.get("항목",""))}"></textarea></div>'
        for i, a in enumerate(ask))
    askbox = (f'<section class="warn"><h2>먼저 여쭤볼 것이 있습니다 ({len(ask)}건)</h2>'
              f'<p class="d">아래 답을 주시면 문서에 반영합니다. 답하기 어려운 항목은 비워두셔도 됩니다.</p>{items}</section>')

reqbox = (f'<section><h2>제가 이해한 요청</h2><div class="card">'
          f'<div class="kv"><span class="k">누가 읽나</span><span class="v">{sentences(r.get("독자",""),120)}</span></div>'
          f'<div class="kv"><span class="k">읽고 할 일</span><span class="v">{sentences(r.get("목적",""),120)}</span></div>'
          f'<div class="kv"><span class="k">배경</span><span class="v">{sentences(r.get("상황",""),120)}</span></div>'
          f'</div></section>')

alts = j.get("대안후보") if isinstance(j.get("대안후보"), list) else []
altbox = ""
if alts:
    rows = "".join(f'<tr><td class="alt-t">{esc_raw(human(a.get("유형","")).lstrip("①②③④⑤⑥⑦⑧⑨⑩⑪ "))}</td>'
                   f'<td>{sentences(a.get("탈락사유",""),110)}</td></tr>' for a in alts)
    altbox = (f'<section><h2>다른 보고 유형이 아닌 이유</h2>'
              f'<p class="d">혹시 이 중 하나가 맞다고 보시면 "수정할게요"를 눌러 알려주세요.</p>'
              f'<table class="alt">{rows}</table></section>')

ents = p.get("개체구성") if isinstance(p.get("개체구성"), list) else []
ents = [e for e in ents if isinstance(e, dict)]
ENT_H = {"제목": "제목", "요약박스": "요약 박스(회색 상자)", "본문": "본문", "붙임": "붙임·끝 표기"}
erow = "".join(
    f'<tr><td>{esc_raw(ENT_H.get(e.get("개체",""), e.get("개체","")))}</td>'
    f'<td class="{"y" if e.get("포함") else "n"}">{"넣음" if e.get("포함") else "뺌"}</td>'
    f'<td>{sentences(e.get("비고",""),110)}</td></tr>' for e in ents)
entbox = (f'<section><h2>문서 구성</h2>'
          f'<table class="ent"><tr><th>요소</th><th>포함</th><th>이유</th></tr>{erow}</table></section>')

# 적용방법론.본문.구성.목차패턴.표준시퀀스(손작성 스키마)를 안전하게 파고, 없으면
# 상위 '본문순서'(LLM 설계 패스가 내는 단순 목록)로 폴백한다. 어느 층이 문자열이어도 안 깨진다.
def _dg(x, k):
    return x.get(k, {}) if isinstance(x, dict) else {}
seq = _dg(_dg(_dg(_dg(p, "적용방법론"), "본문"), "구성"), "목차패턴")
seq = seq.get("표준시퀀스", []) if isinstance(seq, dict) else []
if not seq:
    seq = p.get("본문순서", [])
if not isinstance(seq, list):
    seq = []
seqbox = ""
if seq:
    chips = "".join(f'<span class="chip">{i+1}. {esc_raw(s)}</span>' for i, s in enumerate(seq))
    seqbox = (f'<section><h2>본문 순서(안)</h2>'
              f'<p class="d">본문을 이 순서로 씁니다. 각 절의 실제 제목과 항목 수는 자료를 보고 정합니다.</p>'
              f'<div class="chips">{chips}</div></section>')

els = p.get("등장요소_전망") if isinstance(p.get("등장요소_전망"), list) else []
els = [e for e in els if isinstance(e, dict)]
elbox = ""
if els:
    POSS_H = {"높음": "들어갈 가능성 높음", "중간": "자료에 따라", "낮음": "안 들어갈 듯"}
    rows = ""
    for e in els:
        poss = POSS_H.get(e.get("가능성", ""), e.get("가능성", ""))
        first = re.split(r"(?<=\.)\s", human(e.get("근거", "")))[0][:120]
        rows += (f'<tr><td>{esc_raw(e.get("요소",""))}</td>'
                 f'<td class="poss">{esc_raw(poss)}</td><td>{esc_raw(first)}</td></tr>')
    elbox = (f'<section><h2>표·이미지</h2>'
             f'<p class="d">실제로 넣을지는 자료를 보고 정합니다.</p>'
             f'<table class="ent"><tr><th>요소</th><th>전망</th><th>왜</th></tr>{rows}</table></section>')

dele = p.get("미확정_3층위임") if isinstance(p.get("미확정_3층위임"), list) else []
dele = [x for x in dele if isinstance(x, str)]
delbox = ""
if dele:
    lis = "".join(f"<li>{esc(x)}</li>" for x in dele[:8])
    more = f'<div class="more">…외 {len(dele)-8}건</div>' if len(dele) > 8 else ""
    delbox = (f'<section><h2>자료를 보고 정할 것들</h2>'
              f'<p class="d">설계 단계에서 미리 못 박지 않고, 내용을 쓰면서 정하는 항목입니다.</p>'
              f'<ul class="dele">{lis}</ul>{more}</section>')

out = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>작성 계획 확인 — {esc_raw(p.get('plan_id',''))}</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:"Apple SD Gothic Neo","Malgun Gothic",sans-serif;max-width:880px;margin:0 auto;
padding:28px 24px;color:#222;line-height:1.75;background:#f7f8fa;font-size:14.5px}}
h1{{font-size:22px;margin:0 0 4px}} .top-sub{{color:#777;font-size:13px;margin:0 0 20px}}
h2{{font-size:17px;margin:34px 0 8px;color:#1F3864}}
.d{{color:#666;font-size:13px;margin:0 0 12px}}
.hero{{display:flex;gap:24px;background:#1F3864;color:#fff;border-radius:12px;padding:22px 26px;align-items:center;flex-wrap:wrap}}
.hero-l{{flex:1;min-width:220px}} .lab{{font-size:12px;opacity:.8;margin-bottom:5px}}
.big{{font-size:25px;font-weight:800;line-height:1.3}} .sub{{font-size:13px;opacity:.85;margin-top:6px}}
.btns{{display:flex;gap:10px;margin-top:8px}}
.btns button{{border:0;border-radius:8px;padding:11px 18px;font-size:14px;font-weight:700;cursor:pointer}}
.ok{{background:#fff;color:#1F3864}} .no{{background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.5)}}
.res{{font-size:12px;margin-top:9px;opacity:.9;min-height:16px}}
.why{{background:#eef3ff;border-left:4px solid #1F3864;padding:14px 18px;margin:16px 0 0;
border-radius:0 8px 8px 0;font-size:14px}}
.why b{{display:block;margin-bottom:6px}}
.sent{{margin:4px 0 0;padding-left:18px}} .sent li{{margin:5px 0}}
.warn{{background:#fff8ea;border:1px solid #f0d9a0;border-radius:10px;padding:16px 20px;margin-top:26px}}
.warn h2{{color:#8a6100;margin-top:0}}
.ask{{background:#fff;border:1px solid #ecdfc0;border-radius:8px;padding:13px 15px;margin:12px 0}}
.ask-q{{font-weight:700;font-size:15px;margin-bottom:5px}}
.ask-w{{color:#666;font-size:13px;margin:0 0 9px;line-height:1.65}}
.ask textarea{{width:100%;min-height:48px;border:1px solid #ddd;border-radius:6px;padding:8px 10px;font-size:13.5px;font-family:inherit}}
.card{{background:#fff;border:1px solid #e2e2e2;border-radius:10px;padding:16px 18px}}
.kv{{display:flex;gap:14px;margin:9px 0;align-items:baseline}}
.kv .k{{color:#888;min-width:82px;flex-shrink:0;font-size:13px;font-weight:600}}
.kv .v{{flex:1}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:13.5px;border:1px solid #e2e2e2;border-radius:10px;overflow:hidden}}
th{{background:#eef1f6;text-align:left;padding:9px 14px;font-size:12.5px}}
td{{padding:10px 14px;border-top:1px solid #eee;vertical-align:top;line-height:1.65}}
.alt-t{{font-weight:700;width:150px}} .y{{color:#1a7f37;font-weight:700;width:60px}} .n{{color:#999;width:60px}}
.poss{{font-weight:700;width:130px}}
.chips{{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}}
.chip{{background:#1F3864;color:#fff;padding:9px 16px;border-radius:22px;font-size:14px;font-weight:600}}
.dele{{background:#fff;border:1px solid #e2e2e2;border-radius:10px;padding:14px 14px 14px 32px;font-size:13.5px;color:#555;margin:0}}
.dele li{{margin:6px 0}}
.more{{color:#999;font-size:12.5px;margin-top:6px;padding-left:6px}}
</style></head><body>
<h1>작성 계획 확인</h1>
<p class="top-sub">문서를 쓰기 전에, 어떻게 만들지 먼저 보여드립니다 · 현재: <b>{esc_raw(status_h)}</b></p>
{head}
{askbox}
{reqbox}
{altbox}
{entbox}
{seqbox}
{elbox}
{delbox}
<script>
function mark(s) {{
  const answers = [...document.querySelectorAll('[data-ask]')]
    .filter(t => t.value.trim())
    .map(t => `- ${{t.dataset.ask}}: ${{t.value.trim()}}`);
  const txt = `[작성 계획 ${{s}}]` + (answers.length ? `\\n답변:\\n${{answers.join('\\n')}}` : '');
  navigator.clipboard.writeText(txt);
  document.getElementById('res').textContent = '복사됐습니다 — 대화창에 붙여넣어 주세요.';
}}
</script>
</body></html>"""

if "--stdout" in sys.argv:
    # 웹앱: 파일로 안 쓰고 HTML 을 그대로 stdout 으로 — 세션별 승인화면길() 경로 의존을
    # 없앤다(승인화면 op 가 이 stdout 을 캡처해 브라우저로 돌려준다).
    sys.stdout.write(out)
else:
    자료뿌리.원자쓰기(자료뿌리.승인화면길(), out)     # 원자 쓰기(WP-S2 ③)
    print("written: buildplan/plan.html (사람말 v2)")
