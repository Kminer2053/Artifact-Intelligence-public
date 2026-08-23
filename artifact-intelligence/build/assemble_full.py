#!/usr/bin/env python3
"""풀버전 보고서 조립기 — JSON → 다쪽 HTML(표지→목차→요약→본문→참고자료).

문서 JSON 스키마(build/fullreport-docs.json — 배열):
{
  "filename": "fr-…", "genre": "fullreport",
  "표지": {"부제","제목","보고일","기관명","부서명","문서번호","보존기간","공개"},
  "요약": {"블록": [{"제목", "항목": [{"text", "세부": ["…"]}…]}…],
           "정보박스": {"일정","예산","협조사항"}},
  "장": [{"제목", "핵심박스": ["…"] (선택), "박스": [{…}] (선택), "도식": [{…}] (선택),
          "절": [{"제목", "항목": [{"level": 2|3|4, "text"}…],
                  "박스": [{"종류","캡션","항목","각주"}] (선택),
                  "도식": [{"type","캡션","함의", …}] (선택),
                  "표": {"캡션","header","rows"} (선택)}…]}…],
  박스 종류(shared.박스_카탈로그): 핵심메시지·총괄목표·결론전환·통계근거·참고사례·절차나열·현황참고
  도식 type(build/svgfig.py): process·cycle·converge·strategy·relation·stack
  "별첨": ["… 1부."] | []
}
level: 2=○ 항목 / 3=- 세부 / 4=※ 참고주석. 절 제목이 □. 장 마커(Ⅰ. Ⅱ.)는 자동.

조판(온톨로지 document_types.fullreport.디자인 — standard.hwpx 실측):
- 여백 좌우 20·실효 상하 25mm, 쪽번호 하단 중앙 '- N -'(표지 무번호, 목차=1)
- 장 시작 새 쪽(F구-21), 절 제목+첫 항목·표는 페이지 경계에 안 걸침(F위-20)
- 목차 쪽번호는 브라우저 페이지네이터가 실측 산출 → 기계 정합(F구-26)

게이트: 하드 없음(F구-27) — 연성 경고만 stdout 출력.
사용: python3 build/assemble_full.py build/fullreport-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
import 자료뿌리
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imageasset
import svgfig

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물은 **자료**다 — 어느 뿌리에 낼지는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# CSS·JS·프로파일은 코드라 BASE(코드뿌리) 그대로 둔다.
#
# ★ 산출물 뿌리를 모듈 적재 시점에 상수로 굳히지 않는다(WP-S9). import 로 부르면 모듈이
#   딱 한 번 적재돼 첫 세션 뿌리에 얼어붙고, 이후 모든 세션이 첫 세션 뿌리에 쓴다
#   (WP-S2 세션 오염). 뿌리는 `조립하기()` 가 **호출마다** 다시 푼다.

ROMAN = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ"]
LEVEL_CLS = {2: "i-l2", 3: "i-l3", 4: "i-l4"}

_PROFILES = None


def load_profile(genre):
    """편집기 프로파일(ontology/editor-profiles.json) — 개체→액션 선언."""
    global _PROFILES
    if _PROFILES is None:
        pth = os.path.join(BASE, "..", "ontology", "editor-profiles.json")
        with open(pth, encoding="utf-8") as f:
            _PROFILES = json.load(f)
    p = dict(_PROFILES["장르"].get(genre) or _PROFILES["장르"]["일반"])
    p["genre"] = genre
    return p


RICH_TAGS = {"b": "b", "u": "u", "lb": "span"}


def rich(s):
    """항목 텍스트: 이스케이프 후 강조 화이트리스트 복원 — 정부부처형 강조 관행(G본문-01·02).
    <b>고딕 굵게</b> · <u>밑줄</u> · <lb>(괄호 라벨)</lb>

    여닫음 짝을 검사한다. 안 닫힌 태그는 끝에서 닫고, 짝 없는 닫는 태그는 버린다 —
    검사하지 않으면 브라우저가 강조를 다음 형제 요소까지 번지게 만든다(적대 검증 확정 결함).
    """
    s = html.escape(s)
    open_stack, out, i = [], [], 0
    tokens = [(f"&lt;{k}&gt;", k, False) for k in RICH_TAGS] + \
             [(f"&lt;/{k}&gt;", k, True) for k in RICH_TAGS]
    while i < len(s):
        for tok, name, closing in tokens:
            if s.startswith(tok, i):
                if closing:
                    if name in open_stack:          # 짝이 있을 때만 닫는다
                        while open_stack and open_stack[-1] != name:
                            out.append(f"</{RICH_TAGS[open_stack.pop()]}>")
                        open_stack.pop()
                        out.append(f"</{RICH_TAGS[name]}>")
                    # 짝 없는 닫는 태그는 버린다(미아 </span> 유출 방지)
                else:
                    open_stack.append(name)
                    out.append('<span class="lb">' if name == "lb" else f"<{name}>")
                i += len(tok)
                break
        else:
            out.append(s[i])
            i += 1
    while open_stack:                                 # 안 닫힌 것은 여기서 닫는다
        out.append(f"</{RICH_TAGS[open_stack.pop()]}>")
    return "".join(out)


def _별첨줄(a):
    """별첨 한 항목을 한 줄 문자열로 강제한다. 모델(웹앱·서버 LLM)이 별첨을 문자열이 아니라
    dict/객체로 내도 조립기가 죽지 않게 한다 — 적대 검증에서 확인된 결함
    (AttributeError: 'dict' object has no attribute 'strip', line 303).
    dict 는 제목·내용류 키를 먼저 뽑고, 없으면 스칼라 값들을 이어 붙인다."""
    if isinstance(a, str):
        return a.strip()
    if a is None:
        return ""
    if isinstance(a, dict):
        for k in ("제목", "text", "내용", "설명", "파일명", "name", "title", "값"):
            v = a.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        조각 = [str(v).strip() for v in a.values()
              if isinstance(v, (str, int, float)) and str(v).strip()]
        return " ".join(조각).strip()
    return str(a).strip()


def warn_check(doc):
    """연성 경고(F구-27 — 하드 거부 없음)."""
    warns = []
    chapters = doc.get("장", [])
    # 정본은 '5개 초과'인데 여기만 6이었다(파급표가 잡아낸 어긋남, 2026-07-31).
    # 같은 규칙이 두 곳에 적혀 있으면 반드시 어긋난다 — 정본에 맞춘다.
    if len(chapters) > 5:
        warns.append(f"장 {len(chapters)}개 — 5개 초과, 통합 검토(F구-22)")
    title = doc.get("표지", {}).get("제목", "")
    if len(title) > 30:
        warns.append(f"표지 제목 {len(title)}자 — 1줄 초과 가능(F문-01)")
    # 제목 길이 상한 — 장 20자·절 30자. 넘으면 목차 점선이 깨지거나 장제목 박스가 두 줄로 밀린다
    for ci, ch in enumerate(chapters):
        ct = str(ch.get("제목", "")).strip()
        if len(ct) > 20:
            warns.append(f"{ROMAN[ci]}장 제목 {len(ct)}자 — 20자 상한 초과, 줄임 권고")
        for sec in ch.get("절", []):
            st = str(sec.get("제목", "")).strip()
            if len(st) > 30:
                warns.append(f"{ROMAN[ci]}장 '{st[:12]}…' — 절 제목 {len(st)}자, 30자 상한 초과")
    n_sum = sum(1 + len(i.get("세부", [])) for b in doc.get("요약", {}).get("블록", [])
                for i in b.get("항목", []))
    if n_sum > 22:
        warns.append(f"요약 줄 수 근사 {n_sum} — 1쪽 초과 위험, 압축 검토(F구-06)")
    return warns


def tbl_html(tb):
    cap = f'<div class="fr-tbl-caption">{html.escape(tb["캡션"])}</div>' if tb.get("캡션") else ""
    rows = tb.get("rows", [])
    ncols = max((len(r) for r in rows), default=0)
    numeric = [False] * ncols
    for j in range(1, ncols):
        vals = [r[j] for r in rows if j < len(r)]
        hits = sum(1 for v in vals if any(c.isdigit() for c in v))
        numeric[j] = hits * 2 >= len(vals) and hits > 0
    h = "<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in tb.get("header", [])) + "</tr>"
    for r in rows:
        # 셀 class 는 f-string 밖에서 정한다 — f-string 표현식 안의 이스케이프 따옴표는
        # Python 3.10/3.11 에서 SyntaxError(배포 서버가 3.10 이라 실측으로 걸렸다, '26-08-17).
        cells = []
        for j, c in enumerate(r):
            cls = ' class="r"' if j < ncols and numeric[j] else ''
            cells.append(f'<td{cls}>{html.escape(c)}</td>')
        h += "<tr>" + "".join(cells) + "</tr>"
    return f'<div class="blk fr-tbl-wrap" data-ent="표">{cap}<table class="fr-table">{h}</table></div>\n'


def box_html(bx, path=None, flat=False):
    """꾸밈형 글상자(shared.박스_카탈로그) — 종류로 시각 서식이 결정된다.

    path를 주면 각 항목·각주에 편집 경로를 부여한다. flat=True는 장 핵심박스처럼
    문자열 배열이 바로 항목인 경우(경로가 …핵심박스.N).
    """
    kind = bx.get("종류", "핵심메시지")
    pa = f' data-path="{html.escape(path)}"' if path else ""
    parts = [f'<div class="blk fr-box" data-ent="박스" data-box="{html.escape(kind)}"{pa}>']
    if bx.get("캡션"):
        cp = f' data-path="{html.escape(path)}.캡션"' if path and not flat else ""
        parts.append(f'<div class="cap"{cp}>&lt; {html.escape(bx["캡션"])} &gt;</div>')
    for i, it in enumerate(bx.get("항목", [])):
        cls = ' class="sub"' if isinstance(it, dict) and it.get("부속") else ""
        txt = it["text"] if isinstance(it, dict) else it
        ip = (f' data-path="{html.escape(path)}.{i}"' if flat
              else f' data-path="{html.escape(path)}.항목.{i}"') if path else ""
        parts.append(f'<p{cls}{ip}>{rich(txt)}</p>')
    for i, fn in enumerate(bx.get("각주", [])):
        fp = f' data-path="{html.escape(path)}.각주.{i}"' if path and not flat else ""
        parts.append(f'<p class="fn"{fp}>{rich(fn)}</p>')
    parts.append("</div>\n")
    return "".join(parts)


def 기준도장():
    """이 파일이 어느 기준으로 만들어졌는지 — 겉모습 해시에서는 빼고 센다."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "history"))
        import stamp
        # 속성 자리엔 잠금 없는 보간을 하나도 안 남긴다(assemble.기준도장 과 같은 이유)
        return f'<meta name="기준" content="{html.escape(stamp.조판지문("fullreport"))}">'
    except Exception:
        return ""


_ALIGN_CSS = {"좌측": "left", "가운데": "center", "우측": "right"}
_GAP_CSS = {"좁게": "margin-top:0.4mm;margin-bottom:0.4mm", "넓게": "margin-top:5mm;margin-bottom:5mm"}
def _정렬속성(obj):
    """개체 정렬·간격 필드 → data-* + text-align/margin(편집기 왕복·셀 상속). 없으면 빈 문자열.
    간격은 표에만 쓰이고 장·절엔 없어 무해하다(한 style 속성에 합쳐 낸다)."""
    if not isinstance(obj, dict):
        return ""
    styles, attrs = [], ""
    v = obj.get("정렬")
    if v in _ALIGN_CSS:
        styles.append(f"text-align:{_ALIGN_CSS[v]}"); attrs += f' data-정렬="{html.escape(str(v))}"'
    g = obj.get("간격")
    if g in _GAP_CSS:
        styles.append(_GAP_CSS[g]); attrs += f' data-간격="{html.escape(str(g))}"'
    if styles:
        attrs += f' style="{html.escape(";".join(styles))}"'
    return attrs


def build(doc):
    cv = doc.get("표지", {})
    e = html.escape
    gov = doc.get("스타일") == "정부부처형"
    DOC_JSON = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    PROFILE_JSON = json.dumps(load_profile("fullreport"), ensure_ascii=False).replace("</", "<\\/")
    # 포인트색·여백은 사용자가 주는 값인데 **<html> 의 style 속성**으로 들어간다 —
    # 큰따옴표 하나면 style 을 일찍 닫고 onmouseover 를 <html> 에 심을 수 있었다
    # (적대리뷰 §높음, 2026-08-07 크롬 실측으로 실제 라이브 핸들러 확인).
    # 이 자리들의 계약은 자유글이 아니다 — 16진 색 하나, 밀리미터 숫자 하나다.
    pt = 속성값.색(doc.get("포인트색"), "포인트색", "#0070C0")
    style_bits = [f"--pt:{pt}"] if gov else []
    html_attr = ' data-style="gov"' if gov else ""
    # 위계는 정본이 하나가 아니다 — 기관·작성자마다 달라 문서마다 고른다
    # (온톨로지 fullreport.위계_카탈로그, '26.7.30. 실무자 판정)
    HIER = {"도형식": "", "번호식": "B", "5단 번호식": "S", "블릿 없음": "N"}
    hv = HIER.get(doc.get("위계체계") or "도형식", "")
    if hv:
        html_attr += f' data-hier="{hv}"'
    # 여백은 실측이 원칙. 사용자가 예시 양식을 주면 그 실측을 싣는다.
    m = doc.get("여백_mm")
    if isinstance(m, dict):
        html_attr += ' data-margin="custom"'
        for 변수, 키, 기본 in (("t", "상", 25), ("r", "우", 20),
                             ("b", "하", 25), ("l", "좌", 20)):
            폭 = 속성값.수(m.get(키), f"여백_mm.{키}", 기본=기본, 최소=0, 최대=200)
            style_bits.append(f"--m-{변수}:{폭}mm")
    elif doc.get("여백") == "규칙":
        html_attr += ' data-margin="rule"'  # noqa
    if style_bits:
        html_attr += ' style="' + ";".join(style_bits) + '"'
    # 글꼴은 화면 토글이 아니라 문서의 선택이다 — 안 읽으면 다시 만들 때 원복돼
    # "글꼴을 바꿨다"는 기록만 남고 결과는 안 남는다(이력이 거짓말한다).
    # 고를 수 있는 값은 편집기 프로파일의 상단바.글꼴 이 정본이다(손목록 금지) —
    # 이 값은 data-fonts 속성으로 들어가므로 잠금도 여기서 한 번에 건다(2026-08-07).
    _프 = load_profile("fullreport")
    글꼴들 = tuple(m[0] if isinstance(m, (list, tuple)) else m
                 for m in (_프.get("상단바") or {}).get("글꼴", ()))
    font = 속성값.열거(doc.get("글꼴"), 글꼴들, "글꼴",
                    기본=("serif" if gov else "embed"))
    html_attr += f' data-fonts="{font}"'
    sw = {m: (' class="on"' if m == font else "") for m in 글꼴들}
    sw_embed, sw_serif, sw_hwp = sw.get("embed", ""), sw.get("serif", ""), sw.get("hwp", "")
    STAMP = 기준도장()
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="fullreport"{html_attr}>
<head>
<meta charset="utf-8">{STAMP}
<title>{e(cv.get("제목", ""))}</title>
<link rel="stylesheet" href="../tokens.css?v=">
<link rel="stylesheet" href="../fullreport.css?v=">
</head>
<body>
<script type="application/json" id="fr-doc">{DOC_JSON}</script>
<script type="application/json" id="fr-profile">{PROFILE_JSON}</script>
<div class="font-switcher" aria-label="글꼴 모드" style="position:fixed;top:8px;right:8px;z-index:9">
  <button data-mode="embed"{sw_embed}>내장 표준</button><button data-mode="serif"{sw_serif}>명조</button><button data-mode="hwp"{sw_hwp}>한글 원본</button>
</div>
<script>
document.querySelector('.font-switcher').addEventListener('click', e => {{
  const b = e.target.closest('button'); if (!b) return;
  document.documentElement.dataset.fonts = b.dataset.mode;
  document.querySelectorAll('.font-switcher button').forEach(x => x.classList.toggle('on', x === b));
  if (window.__repaginate) window.__repaginate();   // 글꼴이 바뀌면 조판을 다시 잡는다
  if (window.__hunt) window.__hunt();
}});
</script>
"""]
    title_br = e(cv.get("제목", "")).replace(chr(10), "<br>")
    if gov:
        tag = cv.get("상정표기", "")
        tag_html = (f'<div class="gov-tag" data-ent="표지필드" data-frf="상정표기" data-path="표지.상정표기" data-multiline="1">{e(tag).replace(chr(10), "<br>")}</div>' if tag else "")
        issuer = e(cv.get("발행주체", "") or cv.get("기관명", ""))
        parts.append(f"""<div class="fr-page fr-cover gov">
  {tag_html}
  <div class="gov-cover-mid">
    <div class="gov-bar"></div>
    <div class="fr-subtitle">- <span data-ent="표지필드" data-frf="부제" data-path="표지.부제">{e(cv.get("부제", ""))}</span> -</div>
    <div class="fr-title" data-ent="표지필드" data-frf="제목" data-path="표지.제목" data-multiline="1">{title_br}</div>
    <div class="gov-bar thin"></div>
  </div>
  <div class="fr-date" data-ent="표지필드" data-frf="보고일" data-path="표지.보고일">{e(cv.get("보고일", ""))}</div>
  <div class="gov-issuer" data-ent="표지필드" data-frf="발행주체" data-path="표지.발행주체">{issuer}</div>
</div>
""")
    else:
        # 결재란 직함 — 조직마다 다르므로 편집 가능하게 왕복(표지.결재[]). 값 없으면 표준 3칸.
        _결재 = cv.get("결재")
        if not isinstance(_결재, list) or not _결재:
            _결재 = ["처장", "본부장", "대표이사"]
        _결재 = [str(x) for x in _결재][:6]
        _결재셀 = "".join(
            f'<td data-ent="표지필드" data-frf="결재칸{i + 1}" data-path="표지.결재.{i}">{e(x)}</td>'
            for i, x in enumerate(_결재))
        _사인셀 = "".join('<td class="sign"></td>' for _ in _결재)
        parts.append(f"""<div class="fr-page fr-cover">
  <div class="fr-cover-top">
    <table class="fr-cover-meta"><tr><td class="k">문서번호</td><td data-ent="표지필드" data-frf="문서번호" data-path="표지.문서번호">{e(cv.get("문서번호", "")) or "&nbsp;" * 8}</td></tr>
      <tr><td class="k">보존기간</td><td data-ent="표지필드" data-frf="보존기간" data-path="표지.보존기간">{e(cv.get("보존기간", ""))}</td></tr>
      <tr><td class="k">공개구분</td><td data-ent="표지필드" data-frf="공개" data-path="표지.공개">{e(cv.get("공개", ""))}</td></tr>
      <tr><td class="k">보고일자</td><td>{e(cv.get("보고일", ""))}</td></tr></table>
    <table class="fr-approve"><tr><td class="k" rowspan="2">협<br>조</td>{_결재셀}</tr>
      <tr>{_사인셀}</tr></table>
  </div>
  <div class="fr-cover-mid">
    <div class="fr-subtitle">- <span data-ent="표지필드" data-frf="부제" data-path="표지.부제">{e(cv.get("부제", ""))}</span> -</div>
    <div class="fr-title" data-ent="표지필드" data-frf="제목" data-path="표지.제목" data-multiline="1">{title_br}</div>
    <div class="fr-date" data-ent="표지필드" data-frf="보고일" data-path="표지.보고일">{e(cv.get("보고일", ""))}</div>
  </div>
  <div class="fr-cover-bottom">
    <div class="fr-org" data-ent="표지필드" data-frf="기관명" data-path="표지.기관명">{e(cv.get("기관명", ""))}</div>
    <div class="fr-dept" data-ent="표지필드" data-frf="부서명" data-path="표지.부서명">{e(cv.get("부서명", ""))}</div>
  </div>
</div>
""")
    parts.append("""<div class="fr-page" id="fr-toc">
  <div class="fr-content">
    <h1 class="fr-toc-title">목차</h1>
    <div class="fr-toc-list" id="toc-list"></div>
""")
    _별첨원 = doc.get("별첨") or []
    if isinstance(_별첨원, (str, dict)):                 # 리스트가 아니어도 한 항목으로 받는다
        _별첨원 = [_별첨원]
    annex = [s for s in (_별첨줄(a) for a in _별첨원) if s]
    if annex:
        parts.append('    <div class="fr-toc-annex"><div class="hd">【참고자료】</div><ol>\n')
        for a in annex:
            parts.append(f"      <li>{e(a)}</li>\n")
        parts.append("    </ol></div>\n")
    parts.append("  </div>\n</div>\n")

    # ── 요약 페이지(전용 체계 ▦/1./-, 정보박스 — F구-07). 정부부처형은 없음(G구성-01) ──
    # 요약 페이지는 문서 전체를 요약한다 — 본문 첫 장의 보고 개요와 역할이 달라 둘 다 둔다.
    # 넣을지 말지는 구성 설계에서 고른다('26.7.30. 판정). 정부부처형은 기본이 '없음'.
    sm = doc.get("요약", {}) or {}
    # 요약이 비어 있으면 기본으로 그 쪽을 아예 안 그린다 — 예전엔 빈 '보고내용 요약' 쪽이
    # 덩그러니 남았다(사장님 스크린샷 #1). 사용자가 요약페이지를 명시(True/False)하면 그대로 따른다.
    _요약있음 = bool(sm.get("블록")) or bool(sm.get("정보박스"))
    want_summary = doc.get("요약페이지") if doc.get("요약페이지") is not None else (not gov and _요약있음)
    if want_summary:
        parts.append('<div class="fr-page" id="fr-summary">\n  <div class="fr-content">\n'
                     '    <h1 class="fr-sum-title">보고내용 요약</h1>\n')
        for bi, blk in enumerate(sm.get("블록", [])):
            parts.append(f'    <div class="fr-sum-block" data-path="요약.블록.{bi}">'
                         f'<h2 class="fr-sum-h" data-ent="요약블록" data-path="요약.블록.{bi}.제목">{e(blk["제목"])}</h2>\n')
            for i, it in enumerate(blk.get("항목", []), 1):
                ip = f"요약.블록.{bi}.항목.{i-1}"
                parts.append(f'      <p class="fr-sum-i" data-ent="요약항목"><span class="no">{i}.</span> '
                             f'<span data-path="{ip}.text">{rich(it["text"])}</span></p>\n')
                for si, sub in enumerate(it.get("세부", [])):
                    parts.append(f'      <p class="fr-sum-sub" data-ent="요약항목" data-path="{ip}.세부.{si}">{rich(sub)}</p>\n')
            parts.append("    </div>\n")
        box = sm.get("정보박스", {})
        if box:
            parts.append('    <div class="fr-infobox">')
            for k in ("일정", "예산", "협조사항"):
                parts.append(f'<div class="cell"><b>{k}</b>'
                             f'<span data-path="요약.정보박스.{k}">{e(box.get(k, ""))}</span></div>')
            parts.append("</div>\n")
        parts.append("  </div>\n</div>\n")

    # ── 본문 흐름(페이지네이터 소스) ──
    parts.append('<div id="fr-flow">\n')
    # 간지 — 장을 가르는 표지 낱장. 예시 양식이 쓰거나, 요청하시거나, 경영평가보고서일 때
    # ('26.7.31. 판정). 간지에는 쪽번호를 찍지 않는 것이 기본이다.
    간지 = doc.get("간지")
    간지쓴다 = 간지 if isinstance(간지, bool) else (간지 == "장마다")
    for ci, ch in enumerate(doc.get("장", [])):
        rn = ROMAN[ci]
        if 간지쓴다:
            parts.append(f'  <div class="blk ch fr-divider" data-ent="간지" data-num="{rn}" '
                         f'data-title="{e(ch["제목"])}">'
                         f'<div class="no">{rn}</div>'
                         f'<div class="tx">{e(ch["제목"])}</div></div>\n')
        _새쪽 = ' data-새페이지="false"' if ch.get("새페이지") is False else ""
        parts.append(f'  <div class="blk ch fr-chapter" data-ent="장" data-num="{rn}" data-title="{e(ch["제목"])}"{_정렬속성(ch)}{_새쪽}>'
                     f'<span class="no">{rn}.</span> '
                     f'<span class="tx" data-path="장.{ci}.제목">{e(ch["제목"])}</span></div>\n')
        kb = ch.get("핵심박스") or []
        if kb:   # 장 시작 두괄 대행 — 카탈로그 '핵심메시지'로 렌더
            parts.append("  " + box_html({"종류": "핵심메시지", "항목": kb},
                                         path=f"장.{ci}.핵심박스", flat=True))
        for bi, bx in enumerate(ch.get("박스", [])):
            parts.append("  " + box_html(bx, path=f"장.{ci}.박스.{bi}"))
        for fi, fg in enumerate(ch.get("도식", [])):
            parts.append("  " + svgfig.render(fg).replace(
                'class="blk fr-fig"', f'class="blk fr-fig" data-path="장.{ci}.도식.{fi}"', 1))
        for si, sec in enumerate(ch.get("절", []), 1):
            gid = f"g{ci}-{si}"     # 문단 그룹 = 절 제목 + 그 절의 항목·박스·도식·표
            sp = f"장.{ci}.절.{si-1}"
            parts.append(f'  <h2 class="blk fr-sec" data-ent="절" data-group="{gid}" data-title="{e(sec["제목"])}" '
                         f'data-path="{sp}.제목"{_정렬속성(sec)}>'
                         f'<span class="no">{si}</span><span class="tx">{e(sec["제목"])}</span></h2>\n')
            for ii, it in enumerate(sec.get("항목", [])):
                cls = LEVEL_CLS.get(it["level"], "i-l2")
                _mk = it.get("블릿")                     # 개별 블릿(편집기에서 이 항목만 바꾼 마커)
                _mkattr = f' data-mk="{e(str(_mk))}"' if _mk else ""
                parts.append(f'  <p class="blk {cls}" data-ent="항목" data-group="{gid}"{_mkattr} '
                             f'data-path="{sp}.항목.{ii}.text">{rich(it["text"])}</p>\n')
            for bi, bx in enumerate(sec.get("박스", [])):
                parts.append("  " + box_html(bx, path=f"{sp}.박스.{bi}").replace(
                    'class="blk fr-box"', f'class="blk fr-box" data-group="{gid}"', 1))
            for fi, fg in enumerate(sec.get("도식", [])):
                parts.append("  " + svgfig.render(fg).replace(
                    'class="blk fr-fig"',
                    f'class="blk fr-fig" data-group="{gid}" data-path="{sp}.도식.{fi}"', 1))
            for ii, img in enumerate(sec.get("이미지", [])):
                parts.append("  " + imageasset.render(img, f"{doc['filename']}-{gid}-{ii}")
                             .replace('class="blk fr-fig fr-img"',
                                      f'class="blk fr-fig fr-img" data-group="{gid}" '
                                      f'data-path="{sp}.이미지.{ii}"', 1))
            if sec.get("표"):
                # 정본은 절.표=단일 dict 지만, 모델이 표를 리스트로 낼 때가 있다(그러면
                # tbl_html 이 'list' has no attribute get 으로 크래시). dict 든 list 든 흡수한다 —
                # list 면 각 표를 .표.N 경로로, 단일 dict 면 .표 경로로(정본 왕복 보존).
                _표리스트 = sec["표"] if isinstance(sec["표"], list) else [sec["표"]]
                _단일 = not isinstance(sec["표"], list)
                for _ti, _tb in enumerate(_표리스트):
                    if not isinstance(_tb, dict):
                        continue
                    _경로 = f"{sp}.표" if _단일 else f"{sp}.표.{_ti}"
                    parts.append("  " + tbl_html(_tb).replace(
                        'class="blk fr-tbl-wrap" data-ent="표"',
                        f'class="blk fr-tbl-wrap" data-ent="표" data-group="{gid}" data-path="{_경로}"{_정렬속성(_tb)}', 1))
    if annex:
        parts.append('  <div class="blk ch fr-annex-title" data-num="" data-title="참고자료">참고자료</div>\n')
        for i, a in enumerate(annex, 1):
            parts.append(f'  <p class="blk fr-annex-item" data-ent="별첨"><span class="no">{i}.</span> '
                         f'<span data-path="별첨.{i-1}">{e(a)}</span></p>\n')
    parts.append("</div>\n")

    # ── 페이지네이터: 장 새쪽 · 문단 그룹 분절 방지(줄간격 자동 조정) · 쪽번호·목차 기계 산출 ──
    parts.append('<script src="../svgfig.js?v="></script>\n')
    parts.append("""<script>
(() => {
if (window.SVGFIG) window.SVGFIG.mountAll();   // 도식을 먼저 그린 뒤 조판(높이 확정 필요)
const flow0 = document.getElementById('fr-flow');
let SRC = [...flow0.querySelectorAll('.blk')];          // 최초 블록 목록
// 목차·쪽번호는 실제 쪽수를 알아야 정해지므로 조판기가 문서 설정을 직접 읽는다
const DOC = (() => { try { return JSON.parse(document.getElementById('fr-doc').textContent); }
                     catch (e) { return {}; } })();

// 재조판 전에 현재 쪽에서 블록을 다시 걷는다 — 편집기가 추가·삭제한 것을 살리기 위해.
// (최초 스냅샷만 다시 뿌리면 편집 결과가 통째로 사라진다)
function harvest() {
  const pages = [...document.querySelectorAll('.fr-bodypage')];
  if (!pages.length) return SRC;
  const out = [];
  pages.forEach(p => {
    const inner = p.querySelector('.fr-content');
    if (inner) [...inner.children].forEach(b => { if (b.classList.contains('blk')) out.push(b); });
  });
  return out.length ? out : SRC;
}
const LHS_MIN = 0.86, LHS_MAX = 1.16;                   // 줄간격 배율 허용 범위
const GAP_FILL = 0.10;                                  // 이 비율 이상 남으면 늘려서 채운다

function paginate() {
  if (window.SVGFIG) document.querySelectorAll('.fr-fig[data-fig]:empty')
    .forEach(el => window.SVGFIG.mount(el));
  SRC = harvest();                                      // 현재 상태를 원본으로 삼는다
  document.querySelectorAll('.fr-bodypage').forEach(p => p.remove());
  const flow = document.createElement('div');           // 매 회차 새 흐름에서 시작
  flow.id = 'fr-flow'; flow.style.cssText = 'position:absolute;left:-9999mm;top:0;width:170mm;visibility:hidden';
  document.body.appendChild(flow);
  SRC.forEach(b => { b.style.removeProperty('display'); flow.appendChild(b); });

  const total = {};                                     // 그룹별 총 블록 수
  SRC.forEach(b => { const g = b.dataset.group; if (g) total[g] = (total[g] || 0) + 1; });

  const pages = [];
  function newPage() {
    const pg = document.createElement('div'); pg.className = 'fr-page fr-bodypage';
    const inner = document.createElement('div'); inner.className = 'fr-content';
    pg.appendChild(inner); document.body.insertBefore(pg, flow);
    pages.push(pg); return inner;
  }
  const fits = inner => inner.scrollHeight <= inner.clientHeight + 0.5;

  let inner = null;
  const blocks = [...flow.querySelectorAll('.blk')];
  for (const b of blocks) {
    const isCh = b.classList.contains('ch');
    // 장은 기본으로 새 쪽에서 시작한다. data-새페이지="false" 면 앞 쪽에 이어 붙인다(사장님 요청 #8).
    const 새쪽 = isCh && b.dataset.새페이지 !== 'false';
    if (!inner || (새쪽 && inner.childElementCount)) inner = newPage();
    inner.appendChild(b);
    if (fits(inner) || inner.childElementCount === 1) continue;

    // 넘쳤다 — 이 블록이 속한 문단 그룹이 쪽 경계에서 쪼개지는 상황
    const g = b.dataset.group;
    const head = g ? [...inner.children].filter(x => x.dataset.group === g && x !== b) : [];
    const tail = g ? (total[g] - head.length) : 1;      // 이 블록 포함 넘어갈 조각 수
    const prevInner = inner;
    inner = newPage();
    if (head.length && tail > head.length) {
      // 뒤쪽이 더 많다 → 문단 시작 앞에서 쪽을 넘기고, 앞 쪽은 줄간격을 늘려 채운다
      head.forEach(x => inner.appendChild(x));
      prevInner.parentElement.dataset.fill = '1';
    } else {
      // 앞쪽이 더 많다(또는 그룹 없음) → 앞 쪽을 압축해 꼬리를 당겨오도록 표시
      prevInner.parentElement.dataset.tighten = g || '';
    }
    inner.appendChild(b);
    while (!fits(inner) && inner.childElementCount > 1) { // 한 쪽을 넘는 초대형 블록 방어
      const last = inner.lastElementChild; inner = newPage(); inner.appendChild(last);
    }
  }

  const kept = pages.filter(p => { const ok = p.firstChild.childElementCount > 0;
    if (!ok) p.remove(); return ok; });

  // ── 보정 1: 압축 — 다음 쪽으로 넘어간 같은 그룹 꼬리를 줄간격을 줄여 당겨온다 ──
  kept.forEach((pg, i) => {
    const g = pg.dataset.tighten; const next = kept[i + 1];
    if (!g || !next) return;
    const tail = [...next.firstChild.children].filter(x => x.dataset.group === g);
    if (!tail.length) return;
    const inner = pg.firstChild;
    const moved = [];
    for (const t of tail) { inner.appendChild(t); moved.push(t); }
    let ok = false;
    for (let lhs = 1.0; lhs >= LHS_MIN - 1e-9; lhs -= 0.02) {
      pg.style.setProperty('--lhs', lhs.toFixed(2));
      if (fits(inner)) { ok = true; break; }
    }
    if (!ok) {                                          // 압축으로도 안 되면 원복
      pg.style.removeProperty('--lhs');
      moved.reverse().forEach(t => next.firstChild.insertBefore(t, next.firstChild.firstChild));
    }
  });

  // ── 보정 2: 채움 — 문단을 통째로 넘긴 앞 쪽의 빈 공간을 줄간격을 늘려 메운다 ──
  kept.forEach(pg => {
    if (!pg.dataset.fill) return;
    const inner = pg.firstChild;
    const gap = 1 - inner.scrollHeight / inner.clientHeight;
    if (gap < GAP_FILL) return;
    for (let lhs = 1.0; lhs <= LHS_MAX + 1e-9; lhs += 0.02) {
      pg.style.setProperty('--lhs', lhs.toFixed(2));
      if (!fits(inner)) { pg.style.setProperty('--lhs', (lhs - 0.02).toFixed(2)); break; }
    }
  });

  // ── 목차를 넣을지 — 본문이 4쪽 이하면 넣지 않는 것이 원칙('26.7.30. 실무자 판정).
  //    실제 쪽수는 여기서만 알 수 있어 조판이 끝난 뒤에 정한다. 사용자가 지정하면 그것을 따른다.
  const TOCSET = DOC['목차'] || {};
  const tocEl = document.getElementById('fr-toc');
  const tocWanted = TOCSET['포함'] !== undefined ? !!TOCSET['포함'] : (kept.length > 4);
  if (tocEl) tocEl.style.display = tocWanted ? '' : 'none';

  // ── 쪽번호 ──
  //   표지를 1쪽으로 보고 전체를 통산하되, 표지와 목차에는 찍지 않는다(판정).
  //   정부부처형은 본문부터 재시작하는 관행이 실물에서 관찰돼 변형으로 남긴다.
  document.querySelectorAll('.fr-pageno').forEach(x => x.remove());
  const GOV = document.documentElement.dataset.style === 'gov';
  const PN = DOC['쪽번호'] || {};
  const mode = PN['방식'] || (GOV ? '본문재시작' : '전체통산');
  const cover = document.querySelector('.fr-cover');
  const summary = document.getElementById('fr-summary');
  const inOrder = [cover, tocWanted ? tocEl : null, summary, ...kept].filter(Boolean);
  const numbered = mode === '본문재시작' ? kept : inOrder;
  const hideDefault = new Set([cover, tocEl].filter(Boolean));
  // 간지에는 쪽번호를 찍지 않는 것이 기본이다(경영평가편람 제2절 2.가(2)).
  // 번호는 세되 표시만 생략하며, 쪽마다 바꿀 수 있다.
  document.querySelectorAll('.fr-divider').forEach(d => {
    const pg = d.closest('.fr-page');
    if (pg) hideDefault.add(pg);
  });
  const showMap = PN['표시'] || {};             // { "5": false } = 5번째 쪽 번호 감추기
  const restart = PN['새번호시작'] || {};       // { "5": 1 }    = 5번째 쪽부터 1로 다시
  const pageNo = new Map();
  let n = 0;
  numbered.forEach((p, i) => {
    const r = restart[String(i + 1)];
    n = (r !== undefined) ? Number(r) : n + 1;
    pageNo.set(p, n);
    const f = document.createElement('div'); f.className = 'fr-pageno';
    f.textContent = '- ' + n + ' -'; p.appendChild(f);
    const key = String(i + 1);
    const asked = showMap[key];
    const hide = hideDefault.has(p) ? (asked !== true) : (asked === false);
    if (hide) p.setAttribute('data-no-pageno', '1');
    else p.removeAttribute('data-no-pageno');
    p.dataset.ent = '쪽'; p.dataset.pageIdx = key;
    // 사용자가 손댄 쪽에만 저장 훅을 단다 — 전 쪽에 달면 안 고친 문서까지 설정이 생긴다
    if (asked !== undefined) { p.dataset.flag = '쪽번호.표시.' + key; p.dataset.on = String(asked); }
    if (restart[key] !== undefined) p.dataset.restart = String(restart[key]);
  });
  const list = document.getElementById('toc-list');
  if (list) {
  list.innerHTML = '';
  // 목차 점프 — 항목을 누르면 해당 장/절로 이동(화면). 기본 켬, doc["화면"].목차점프=false 로 뺀다(편집기).
  let 목차점프 = true;
  try { 목차점프 = (JSON.parse(document.getElementById('fr-doc').textContent)['화면'] || {})['목차점프'] !== false; } catch (e) {}
  // 목차 깊이 — 분량에 따라 자동(장이 많거나 길면 장만), 사용자가 지정하면 그것을 따른다
  const depth = TOCSET['깊이'] || ((kept.length > 14) ? '장만' : '장과 큰 항목');
  const pick = depth === '장만' ? '.fr-bodypage .ch:not(.fr-divider)'
    : '.fr-bodypage .ch:not(.fr-divider), .fr-bodypage .fr-sec';
  document.querySelectorAll(pick).forEach(el => {
    const pg = pageNo.get(el.closest('.fr-page'));
    const isCh = el.classList.contains('ch');
    const row = document.createElement('div');
    row.className = 'fr-toc-row ' + (isCh ? 'ch' : 'sec');
    const num = el.dataset.num, secNo = el.querySelector('.no');
    const label = isCh ? (num ? num + '.  ' : '') + el.dataset.title
      : ((GOV && secNo) ? secNo.textContent + '. ' : '') + el.dataset.title;
    row.innerHTML = '<span class="t"></span><span class="dots"></span><span class="pg"></span>';
    row.querySelector('.t').textContent = label;
    row.querySelector('.pg').textContent = pg;
    list.appendChild(row);
    if (목차점프) {
      row.classList.add('fr-toc-jump');
      row.setAttribute('role', 'link');
      row.tabIndex = 0;
      const 이동 = () => el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      row.addEventListener('click', 이동);
      row.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); 이동(); }
      });
    }
  });
  }
  // ── 보정 3: 목차 자동 축소 — 프레임 안쪽 가용 높이가 줄어 참고자료가 잘리던 결함 ──
  const toc = document.getElementById('fr-toc');
  if (toc) {
    toc.style.removeProperty('--lhs');
    const ti = toc.firstElementChild;
    for (let lhs = 1.0; !fits(ti) && lhs >= 0.70; lhs -= 0.02) {
      toc.style.setProperty('--lhs', lhs.toFixed(2));
    }
  }

  // ── 보정 4: 넘침 감지 — 조용히 잘리는 대신 표식·경고를 남긴다 ──
  const over = [];
  document.querySelectorAll('.fr-page').forEach((p, i) => {
    const inn = p.querySelector('.fr-content');
    if (!inn) return;
    p.removeAttribute('data-overflow');
    if (inn.scrollHeight > inn.clientHeight + 1) {
      p.setAttribute('data-overflow', '1');
      over.push({ page: i + 1, id: p.id || '', px: Math.round(inn.scrollHeight - inn.clientHeight) });
    }
  });
  window.__frOverflow = over;
  if (over.length) console.warn('[조판 경고] 내용이 잘린 쪽:', over);

  flow.remove();
  window.__frPages = document.querySelectorAll('.fr-page').length;  // 표지·목차 포함 물리 쪽수
  window.__frLhs = kept.map(p => p.style.getPropertyValue('--lhs') || '1');
}
window.__repaginate = paginate;
paginate();
flow0.remove();
if (window.__hunt) window.__hunt();
})();
</script>
""")
    parts.append("""
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
</body>
</html>
""")
    return "".join(parts).replace("</head>", 속성값.간격스타일(doc) + "</head>", 1)  # #3 개체 위/아래 간격


def 조립하기(등록부경로, only=None, out=None):
    """풀버전 등록부 → HTML. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 산출물뿌리를 **호출마다**
    다시 푼다(세션 오염 방지, 모듈 머리말). `out` 을 주면(=--out) 그 자리로 뽑는다.
    """
    낼곳 = out if out else 자료뿌리.산출물뿌리()   # 호출마다 세션 뿌리를 다시 푼다
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    # 한 건만 다시 만들 수 있다(`--only <문서키>`, WP-S2 ②) — 세션 안에서 문서
    # 하나를 저장할 때 나머지 문서 파일까지 다시 쓰지 않으려고. 판정은 genres 한 곳.
    docs = genres.한건만(docs, ["--only", only] if only else [])
    낸것, 로그 = [], []
    for doc in docs:
        for w in warn_check(doc):
            로그.append(f"[경고] {doc['filename']}: {w}")
        fn = f"{doc['filename']}.html"
        with 자료뿌리.쓰기(os.path.join(낼곳, fn)) as f:      # 원자 쓰기(WP-S2 ③)
            f.write(genres.판찍기(build(doc)))
        낸것.append(fn)
        로그.append(f"built: {fn}")
    return {"ok": True, "낸것": 낸것, "로그": "\n".join(로그)}


def main():
    # --out DIR 로 다른 곳에 뽑을 수 있다. 기준이 바뀌었을 때 임시 폴더에 다시 만들어
    # 겉모습을 대조하려면 정본을 건드리지 않고 뽑을 길이 있어야 한다(history/stamp.py).
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    본 = 조립하기(argv[0], only=only, out=out)
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
