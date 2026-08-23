#!/usr/bin/env python3
"""샘플 문서 JSON → samples/*.html 조립기.
사용: python3 assemble.py <docs.json>  (docs.json = 생성 워크플로우 결과 배열)"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
import 자료뿌리
import html
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물은 **자료**다 — 어느 뿌리에 낼지는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# CSS·JS·프로파일은 코드라 BASE(코드뿌리) 그대로 둔다.
#
# ★ 산출물 뿌리를 여기(모듈 적재 시점)서 상수로 굳히지 않는다(WP-S9). 예전엔
#   `OUT = 자료뿌리.산출물뿌리()` 였는데, api.py 가 이 모듈을 import 로 부르면 모듈이
#   딱 한 번 적재되며 그 값이 **첫 세션 뿌리에 얼어붙어** 이후 모든 세션의 조립이 첫
#   세션 뿌리에 쓴다(WP-S2·적대리뷰가 잡은 세션 오염). 그래서 뿌리는 `조립하기()` 가
#   **호출마다** 다시 푼다. subprocess 로 부를 때도 같은 함수를 탄다.

HEAD = """<!doctype html>
<html lang="ko" data-genre="onepage" data-fonts="{font}"{mk2}>
<head>
<meta charset="utf-8">{기준도장}
<title>{title}</title>
<link rel="stylesheet" href="../tokens.css?v=">
<link rel="stylesheet" href="../report.css?v=">
</head>
<body>
<div class="font-switcher" aria-label="글꼴 모드">
  <button data-mode="embed"{sw_embed}>내장 표준</button>
  <button data-mode="serif"{sw_serif}>명조</button>
  <button data-mode="hwp"{sw_hwp}>한글 원본</button>
</div>
<script>
document.querySelector('.font-switcher').addEventListener('click', e => {{
  const b = e.target.closest('button'); if (!b) return;
  document.documentElement.dataset.fonts = b.dataset.mode;
  document.querySelectorAll('.font-switcher button').forEach(x => x.classList.toggle('on', x === b));
  if (window.__hunt) window.__hunt();
}});
</script>
<script type="application/json" id="fr-doc">{doc_json}</script>
<script type="application/json" id="fr-profile">{profile_json}</script>
<div class="sheet">
  <div class="doc-titlebar"></div>
  <h1 class="doc-title" data-ent="제목" data-path="title"{title_fs}>{title}</h1>
  <div class="doc-titlebar bottom"></div>
  <p class="doc-byline" data-ent="작성자" data-path="byline">{byline}</p>
  <div class="doc-summary" data-ent="요약박스" data-path="summary"{summary_fs}>{summary}</div>
"""

TAIL = """  {attach_line}
</div>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
</body>
</html>
"""

LEVEL_CLS = {2: "i-l2", 3: "i-l3", 4: "i-l4"}

_PROFILES = None


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


def load_profile(genre):
    """편집기 프로파일(ontology/editor-profiles.json) — 개체→액션 선언."""
    global _PROFILES
    if _PROFILES is None:
        with open(os.path.join(BASE, "..", "ontology", "editor-profiles.json"),
                  encoding="utf-8") as f:
            _PROFILES = json.load(f)
    p = dict(_PROFILES["장르"].get(genre) or _PROFILES["장르"]["일반"])
    p["genre"] = genre
    return p

import re

MARKER = re.compile(r'^\s*[-*○◦□ㅇ※·•]+\s*')


# 강조 span 의 허용 클래스 — **정본은 report.css 다**(.num/.accent/.delta, report.css:141-143).
# 여기 손으로 적어 두면 CSS 가 늘 때 조용히 어긋나므로 verify_all 의
# `check_emphasis_classes` 가 report.css 와 이 목록을 맞춰 본다(손목록 금지, 규칙 2).
강조클래스 = ("num", "accent", "delta")

_열린span = re.compile(r'<span class="([A-Za-z][\w-]*)">')
_닫힌span = re.compile(r'</span>')


def norm_plain(s):
    """제목·byline·attach: **평문 그대로.** 여기서 이스케이프를 풀지 않는다.

    2026-08-07 (WP-S2 ③) 고침 — 예전에는
        while '&lt;' in s or '&amp;' in s: s = html.unescape(s)
    였다. 이 반복은 `&lt;script&gt;` 를 **진짜 태그** `<script>` 로 되살리고,
    `&amp;lt;script&amp;gt;` 처럼 이스케이프가 겹친 입력은 두 바퀴 돌아 역시 태그가 된다.
    부르는 쪽이 `html.escape(norm_plain(...))` 로 다시 잠그고 있어서 지금 산출물에는
    구멍이 안 났지만, **이 함수가 태그를 만들어 놓고 그 다음 줄의 escape 하나에
    목숨을 거는 모양**이었다. 새 부르는 자리(편집기·HWPX 전환·내보내기)가 escape 를
    빠뜨리는 순간 구멍이 된다.

    이스케이프 처리는 **정확히 한 번**, 부르는 쪽의 `html.escape` 뿐이다.
    되풀이 해제가 필요 없다는 근거(실측 2026-08-07): 등록부 5벌의 title·byline·attach
    에 HTML 엔티티가 **한 개도 없다**(byline 24건의 `<시설관리처, …>` 는 날글자 꺾쇠라
    해제 대상이 아니다). 편집기가 되돌려 주는 글도 이미 평문이다
    (render_editor_any.py `textOf()` 가 textarea 로 한 번 풀어서 넘긴다) —
    여기서 또 푸는 것은 처음부터 겹치기였다.
    """
    return s


def _허용마크업(s):
    """1p 본문·요약의 **허용 태그 화이트리스트**(부록/시각변수전수.md '1p 본문 마크업').

    설계는 `items[].html` 에 강조 span 을 허용하는 것이다 — 그 셋만 살리고
    나머지 `<` 는 전부 `&lt;` 로 잠근다. 그러면 `<img src=x onerror=…>` ·
    `<script>` · `<span onmouseover=…>` 가 태그가 되지 못한다.

    **`&` 는 건드리지 않는다.** 이 자리의 계약은 "이미 HTML 인 글"이라 엔티티가
    정상 입력이다(실측: `F&amp;B` 1건). 여기서 `&` 를 다시 이스케이프하면
    `&amp;amp;` 가 되어 화면에 `F&amp;B` 라고 인쇄된다 — 잠그려다 글을 깨는 길이다.
    `&lt;script&gt;` 는 손대지 않아도 글자로 남으니 안전하다.

    여닫음 짝도 센다(assemble_full.rich 와 같은 이유) — 미아 `</span>` 이나 안 닫힌
    span 은 강조를 옆 형제 요소까지 번지게 한다.
    """
    나온것, 열린, i = [], 0, 0
    while i < len(s):
        ch = s[i]
        if ch != '<':
            나온것.append(ch)
            i += 1
            continue
        m = _열린span.match(s, i)
        if m and m.group(1) in 강조클래스:
            나온것.append(m.group(0))
            열린 += 1
            i = m.end()
            continue
        m = _닫힌span.match(s, i)
        if m and 열린 > 0:
            나온것.append(m.group(0))
            열린 -= 1
            i = m.end()
            continue
        나온것.append('&lt;')          # 허용 밖의 꺾쇠 — 글자로 잠근다
        i += 1
    나온것.append('</span>' * 열린)     # 안 닫힌 것은 여기서 닫는다
    return "".join(나온것)


def norm_rich(s):
    """항목·요약: 허용 태그(강조 span)만 남긴다. + 선두 마커 제거
    (마커는 CSS ::before가 그리므로 텍스트에 있으면 중복).

    2026-08-07 (WP-S2 ③): 여기 있던 반복 unescape 도 없앴다. 조건이
    `'&lt;span' in s or '&amp;lt;' in s` 였는데, **글 어딘가에 `&lt;span` 이
    한 번만 있으면 문자열 전체가 풀렸다** — 같은 항목에 섞어 넣은
    `&lt;script&gt;` 까지 함께 태그가 된다. 이 값은 `html.escape` 없이
    그대로 산출 HTML 의 본문 자리에 들어가므로 여기가 진짜 실행 지점이다.
    """
    s = _허용마크업(s)
    s = MARKER.sub('', s)
    # 가운뎃점 밀착 (조직 · 예산 → 조직·예산)
    s = re.sub(r'\s*([·・])\s*', r'·', s)
    # 날짜 표기 통일: '26.7.29. → '26. 7. 29.
    s = re.sub(r"'(\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", r"'\1. \2. \3.", s)
    # 쉼표 뒤 공백 보장 — 단, 숫자 자릿수 쉼표(1,240)는 제외
    s = re.sub(r',(?=[가-힣A-Za-z<])', ', ', s)
    return s


def norm_attach(s):
    """붙임: 라벨/끝 중복 제거 + 수량 뒤 마침표 보장 (…1부.  끝.)"""
    s = norm_plain(s).strip()
    s = re.sub(r'^(붙임|별첨)\s*[:：]?\s*', '', s)
    s = re.sub(r'\s*끝\s*\.?\s*$', '', s).rstrip()
    s = s.rstrip('.')
    if not re.search(r'\d+\s*[부매]$', s):
        s += ' 1부'
    return s + '.'



DELTA_RE = re.compile(r'<span class="delta">([^<]*)</span>')
ACCENT_RE = re.compile(r'<span class="accent">([^<]*)</span>')
SPAN_IN_SUMMARY = re.compile(r'<span class="[^"]*">([^<]*)</span>')


def enforce_emphasis(texts):
    """강조 일관성 기계 집행(검수 지적 반영):
    - delta(빨강)는 △ 포함 수치 전용 — △ 없으면 num(검정 볼드)으로 강등
    - accent(남색)는 문서 전체 2회까지 — 초과분은 평문으로 해제"""
    out = []
    accents = 0
    for t in texts:
        t = DELTA_RE.sub(lambda m: m.group(0) if '△' in m.group(1)
                         else f'<span class="num">{m.group(1)}</span>', t)
        def cap(m):
            nonlocal accents
            accents += 1
            return m.group(0) if accents <= 2 else m.group(1)
        t = ACCENT_RE.sub(cap, t)
        out.append(t)
    return out


def mk2_attr(값, 선택지):
    """2단 마커 선택 — 정본이 ○ 이고, 실물이 많이 쓰는 ◦ 를 선택지로 준다.

    실측(내부 보고서 11건)은 ◦ 가 10문서 207회 · ○ 가 1문서 38회였다. 그래도 정본을
    바꾸지 않은 것은 사장님 결정이다 — "정본이 원칙, 실물을 옵션으로." 그러니 이 값은
    문서마다 고르는 것이고, 안 고르면 ○ 다.
    마커 자체는 CSS ::before 가 그린다(텍스트에 넣으면 편집기가 지운다).

    선택지는 **부르는 쪽이 편집기 프로파일에서 세어** 넘긴다(항목.2단마커) —
    여기 손으로 적어 두면 화면이 주는 선택지와 조립기가 받는 선택지가 갈라진다.
    2026-08-07: 값이 속성으로 그냥 들어가던 것을 속성값.열거 로 못 박았다.
    """
    if not 선택지:
        return ""
    고른것 = 속성값.열거(값, 선택지, "2단마커")
    if not 고른것 or 고른것 == 선택지[0]:
        return ""          # 기본값은 속성을 안 남긴다 — 왕복 불변식이 깨진다
    return f' data-mk2="{고른것}"'


def 기준도장():
    """이 파일이 어느 기준으로 만들어졌는지 — 겉모습 해시에서는 빼고 센다."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "history"))
        import stamp
        # 지문은 16진수라 escape 해도 글자가 안 바뀐다. 그래도 잠그는 이유는
        # **속성 자리엔 잠금 없는 보간이 하나도 없어야** 하기 때문이다(자리로 막는다).
        return (f'<meta name="기준" '
                f'content="{html.escape(stamp.조판지문("onepage-report"))}">')
    except Exception:
        return ""


def build(doc):
    # 요약박스는 강조 없는 평문 관례(검수 지적) — span 전부 해제
    summary = SPAN_IN_SUMMARY.sub(r'\1', norm_rich(doc.get("summary", "")))
    # 본문 항목 전체에 강조 일관성 집행
    flat = []
    for sec in doc.get("sections", []):
        for it in sec["items"]:
            flat.append(norm_rich(it["html"]))
    flat = enforce_emphasis(flat)
    fi = iter(flat)
    for sec in doc.get("sections", []):
        for it in sec["items"]:
            it["html"] = next(fi)

    def fs_attr(v, 자리):
        """글자크기 속성 — **숫자만** 실린다(build/속성값.py, 2026-08-07).

        예전에는 `f' style="font-size:{v}pt"'` 로 값을 그대로 보간했다.
        `title_fs='1pt"><img src=x onerror=…>'` 하나로 속성을 닫고 태그를 심을 수
        있었고, 실제로 크롬에서 돌았다(적대리뷰 §치명). 0·없음이면 예전처럼
        속성을 아예 안 남긴다 — 남기면 왕복 불변식이 깨진다.
        """
        if not v:
            return ''
        pt = 속성값.수(v, 자리, 최소=1, 최대=400)
        return f' style="font-size:{pt}pt"' if pt is not None else ''
    prof = load_profile("onepage-report")
    # 글꼴은 화면 토글이 아니라 문서의 선택이다 — 안 읽으면 다시 만들 때 원복된다.
    # 고를 수 있는 값은 **편집기 프로파일의 상단바.글꼴** 이 정본이다(손목록 금지) —
    # 여기 세 값을 손으로 또 적어 두면 화면이 주는 선택지와 갈라진다. 이 값은
    # `data-fonts` 속성으로 들어가므로 잠금도 여기서 한 번에 건다(2026-08-07).
    글꼴들 = tuple(m[0] if isinstance(m, (list, tuple)) else m
                 for m in (prof.get("상단바") or {}).get("글꼴", ()))
    font = 속성값.열거(doc.get("글꼴"), 글꼴들, "글꼴", 기본="embed")
    sw = {m: (' class="on"' if m == font else "") for m in 글꼴들}
    parts = [HEAD.format(
        기준도장=기준도장(), font=font,
        mk2=mk2_attr(doc.get("2단마커"),
                     tuple(((prof.get("개체") or {}).get("항목") or {}).get("2단마커", ()))),
        sw_embed=sw.get("embed", ""), sw_serif=sw.get("serif", ""),
        sw_hwp=sw.get("hwp", ""),
        title=html.escape(norm_plain(doc.get("title", ""))),
        byline=html.escape(norm_plain(doc.get("byline", ""))),
        summary=summary,
        title_fs=fs_attr(doc.get("title_fs"), "title_fs"),
        summary_fs=fs_attr(doc.get("summary_fs"), "summary_fs"),
        doc_json=json.dumps(doc, ensure_ascii=False).replace("</", "<\\/"),
        profile_json=json.dumps(prof, ensure_ascii=False).replace("</", "<\\/"),
    )]
    table = doc.get("table")
    for si, sec in enumerate(doc.get("sections", [])):
        parts.append(f'  <h2 class="h-l1" data-ent="절"{_정렬속성(sec)} data-path="sections.{si}.heading">'
                     f'{html.escape(sec["heading"])}</h2>\n')
        for ii, it in enumerate(sec["items"]):
            cls = LEVEL_CLS.get(it["level"], "i-l2")
            fss = fs_attr(it.get("fs"), f"sections.{si}.items.{ii}.fs")
            parts.append(f'  <p class="{cls}" data-ent="항목" '
                         f'data-path="sections.{si}.items.{ii}.html"{fss}>{it["html"]}</p>\n')
        if table and table.get("after_heading") == sec["heading"]:
            parts.append(f'  <div class="doc-table-wrap" data-ent="표"{_정렬속성(table)} data-path="table">\n')
            parts.append(f'    <div class="doc-table-caption">{html.escape(table["caption"])}</div>\n')
            # 표 스타일은 **등록부가 정한 여섯 중 하나**다 — 후보를 여기 손으로 적지
            # 않고 편집기 프로파일(ontology/editor-profiles.json 의 표.스타일)에서
            # 세어 온다(규칙 2). 예전에는 값을 그대로 data-style 에 보간해
            # `x"><img src=x onerror=…>` 로 표 태그 안에 마크업을 심을 수 있었다.
            표스타일들 = ((prof.get("개체") or {}).get("표") or {}).get("스타일") or ()
            style = 속성값.열거(table.get("style"), 표스타일들, "table.style", 기본="")
            style_attr = f' data-style="{style}"' if style and style != "샌드위치" else ""
            parts.append(f'    <table class="doc-table"{style_attr}>\n      <tr>')
            for hcell in table["header"]:
                parts.append(f'<th>{html.escape(hcell)}</th>')
            parts.append('</tr>\n')
            rows = table["rows"]
            # 열 단위 정렬 판정: 첫 열 제외, 절반 이상이 숫자성인 열은 '-' 포함 전체 우측 정렬
            ncols = max(len(r) for r in rows) if rows else 0
            numeric_col = [False] * ncols
            for j in range(1, ncols):
                vals = [r[j] for r in rows if j < len(r)]
                hits = sum(1 for v in vals if any(ch.isdigit() for ch in v))
                numeric_col[j] = hits * 2 >= len(vals) and hits > 0
            for row in rows:
                parts.append('      <tr>')
                for j, cell in enumerate(row):
                    r = ' class="r"' if j < ncols and numeric_col[j] else ''
                    parts.append(f'<td{r}>{html.escape(cell)}</td>')
                parts.append('</tr>\n')
            parts.append('    </table>\n  </div>\n')
    # 붙임: attach가 있으면 "붙임 …1부.  끝.", 없으면 본문 끝에 "끝."만 (KeyError 방지)
    attach_raw = doc.get("attach") or ""
    end_mark = doc.get("show_end_mark", False)  # 종결 표기 — 정본 기본값 False (entities.붙임.문체.종결표기_옵션.기본값): 내부 1p 보고서 표준=표기 없음. 시행문은 별도 조립기(assemble_gongmun)가 강제
    end_txt = "&nbsp;&nbsp;끝." if end_mark else ""
    if attach_raw.strip():
        attach_line = (f'<p class="doc-attach" data-ent="붙임" data-path="attach"><span class="label">붙임</span>'
                       f'&nbsp;&nbsp;{html.escape(norm_attach(attach_raw))}{end_txt}</p>')
    elif end_mark:
        attach_line = '<p class="doc-attach" data-ent="붙임" data-path="attach">끝.</p>'
    else:
        attach_line = ''
    parts.append(TAIL.format(attach_line=attach_line))
    return "".join(parts).replace("</head>", 속성값.간격스타일(doc) + "</head>", 1)  # #3 개체 위/아래 간격


def 조립하기(등록부경로, only=None, out=None):
    """3층 JSON 등록부 → samples/*.html. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": "built: …" 줄들}.

    ★ 산출물뿌리를 **호출마다** 다시 푼다(세션 오염 방지, 모듈 머리말 참고). `out` 을
      주면(=CLI `--out`) 정본을 안 건드리고 그 자리로 뽑는다 — history/stamp.py 가
      기준 대조를 위해 임시 폴더로 뽑을 때 쓴다.
    """
    낼곳 = out if out else 자료뿌리.산출물뿌리()   # 호출마다 세션 뿌리를 다시 푼다
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    # 한 건만 다시 만들 수 있다(`--only <문서키>`, WP-S2 ②) — 세션 안에서 문서
    # 하나를 저장할 때 나머지 문서 파일까지 다시 쓰지 않으려고. 판정은 genres 한 곳.
    docs = genres.한건만(docs, ["--only", only] if only else [])
    낸것, 로그 = [], []
    for doc in docs:
        fn = f"{doc['filename']}.html"
        # 원자 쓰기(WP-S2 ③) — 예전엔 `open(...,"w")` 가 먼저 파일을 0바이트로 자르고
        # 그 안에서 build(doc) 을 불렀다. doc 이 깨져 있으면 정확히 그 사이에서 죽어
        # **0바이트 산출물**이 남았다(2026-08-07 실측, 새문서 실패). 이제는 tmp 에
        # 쓰고 다 되면 갈아 끼우므로, 죽어도 옛 파일이 그대로 있고 tmp 도 안 남는다.
        with 자료뿌리.쓰기(os.path.join(낼곳, fn)) as f:
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
