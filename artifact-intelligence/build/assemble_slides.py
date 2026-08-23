#!/usr/bin/env python3
"""발표 슬라이드 조립기 — JSON → 16:9 가로 슬라이드 HTML.

정본: ontology document_types.slides ('26-08-13 등재 — 외부 코퍼스 4유파 수렴,
      실물 부처 PPT 실측 전이라 수치 게이트는 soft)
  중핵  헤드메시지 = 완결 주장 문장 ≤2줄 · 장당 메시지 1개 · 헤드메시지 연쇄 = 스토리
  지면  338.7×190.5mm (=960×540pt, PPT 물리 규격. 사장님 판정 '26-08-13: mm 확정)
  페이지 모델  **장 = 고정 상자.** 풀버전처럼 흘려 다시 앉히지 않는다 — 넘침은
        재배치가 아니라 **위반**이다(reveal pdfMaxPagesPerSlide=1 과 같은 판단).
        overflow:hidden 이라 넘쳐도 PDF 쪽수는 안 늘어난다 — 그래서 쪽수 게이트가
        아니라 audit.js 의 장별 실측(AUDIT_SPEC.slides)이 넘침을 잡는다(스텁 실측).

문서 JSON 스키마(build/slides-docs.json — 배열):
{
  "filename": "sl-…", "genre": "slides",
  "표지": {"제목": "…", "부제": "…", "발표정보": "기관 · 일자 · 보고대상"},
  "슬라이드": [
    {"레이아웃": "어젠다|간지|본문|표|도식|이미지|픽토그램|마무리",
     "헤드메시지": "완결 주장 1문장(본문·표·도식·이미지·픽토그램·마무리 필수)",
     "항목": [{"level": 1~3, "text": "…"} …] | ["…"](어젠다),
     "번호": "Ⅰ", "제목": "…"(간지),
     "표": {"캡션": "…", "header": […], "rows": [[…]…]}(표),
     "도식": {"type": "process|cycle|converge|strategy|relation|stack", …}(도식 — 풀버전과 같은 svgfig),
     "이미지": {"출처": "생성|(첨부)", "캡션": "…", "프롬프트|자를곳": …}(이미지 — 풀버전과 같은 imageasset),
     "픽토그램": [{"아이콘": "safety-shield", "라벨": "…", "설명": "…(선택)"} …](픽토그램 — build/pictograms.json),
     "출처": "…(선택)"}
  ]
}
시각 장(도식·이미지·픽토그램)도 헤드메시지가 이끈다 — 장당 1메시지 중핵은 그대로다.
표지는 슬라이드 배열에 넣지 않는다 — 문서당 하나라 최상위 "표지" 다.

게이트(gate_check — 조립 시점 하드)
  · 표지.제목 필수 · 슬라이드 1장 이상
  · 레이아웃은 카탈로그 열거값(모르는 이름을 조용히 본문으로 떨어뜨리지 않는다)
  · 본문·표·마무리엔 헤드메시지 필수 — 헤드메시지 없는 장은 메시지 없는 장이다
장수·넘침은 렌더 게이트(render_verify.sh) 소관 — 조립기는 세지 않는다.

사용: python3 build/assemble_slides.py build/slides-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
import 자료뿌리
import svgfig
import imageasset
import pictogram
import html
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물 뿌리는 조립하기() 가 호출마다 다시 푼다(WP-S9·세션 오염 방지) — 상수 금지.

NBSP = "&#160;"

# 개조식 사다리 — 슬라이드 본문은 얕다(3단이면 이미 깊다. 장당 1메시지가 중핵이다)
마커 = {1: "□", 2: "○", 3: "-"}
레이아웃들 = ("어젠다", "간지", "본문", "표", "도식", "이미지", "픽토그램", "마무리")
# 헤드메시지가 이끄는 장들 — 하나의 몸통 구조(헤드메시지 + sl-body)를 공유한다.
헤드장 = ("본문", "표", "도식", "이미지", "픽토그램", "마무리")
# 디자인 테마 라이브러리 — 강조색 한 색을 바꾸는 카탈로그(slides.css 와 같아야 한다).
# 기본(없거나 "네이비")은 data-테마 없이 간다. 정본: ontology slides.테마.
테마들 = ("네이비", "청록", "감청", "자목", "숲", "먹")

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
    global _PROFILES
    if _PROFILES is None:
        with open(os.path.join(ROOT, "ontology", "editor-profiles.json"),
                  encoding="utf-8") as f:
            _PROFILES = json.load(f)
    p = dict(_PROFILES["장르"].get(genre) or _PROFILES["장르"]["일반"])
    p["genre"] = genre
    return p


def 기준도장():
    try:
        sys.path.insert(0, os.path.join(ROOT, "history"))
        import stamp
        return (f'<meta name="기준" '
                f'content="{html.escape(stamp.조판지문("slides"))}">')
    except Exception:
        return ""


def _표정규화(doc):
    """모델이 표를 정본(header/rows) 대신 한글 키(헤더/행)나 행 객체로 내는 흔한 이탈을
    조립기가 읽는 배열 꼴로 옮긴다 — 슬라이드가 통째로 게이트에 걸리는 것보다 낫다.
    행이 dict 면 값을 header 열 순서(모델이 그 순서로 낸다)대로 편다. 이미 정본이면 안 건드린다."""
    for s in (doc.get("슬라이드") or []):
        tb = s.get("표")
        if not isinstance(tb, dict):
            continue
        if "header" not in tb and tb.get("헤더") is not None:
            tb["header"] = tb.pop("헤더")
        if not tb.get("rows") and tb.get("행") is not None:
            펼침 = []
            for r in tb.pop("행"):
                if isinstance(r, dict):
                    펼침.append([("" if v is None else str(v)) for v in r.values()])
                elif isinstance(r, list):
                    펼침.append(r)
            tb["rows"] = 펼침
    return doc


def gate_check(doc):
    """슬라이드 꼴을 갖췄는가 — 조립 시점 하드 게이트."""
    bad = []
    if not (doc.get("표지") or {}).get("제목"):
        bad.append("표지.제목이 없다")
    테마 = doc.get("테마")
    if 테마 and 테마 not in 테마들:
        bad.append(f"테마 {테마!r} — 라이브러리에 없다({', '.join(테마들)})")
    장들 = doc.get("슬라이드") or []
    if not 장들:
        bad.append("슬라이드가 한 장도 없다")
    for i, s in enumerate(장들):
        lo = s.get("레이아웃")
        if lo not in 레이아웃들:
            bad.append(f"슬라이드.{i}: 레이아웃 {lo!r} — 카탈로그에 없다"
                       f"({', '.join(레이아웃들)}). 모르는 이름을 본문으로 떨어뜨리지 않는다")
            continue
        if lo in 헤드장 and not (s.get("헤드메시지") or "").strip():
            bad.append(f"슬라이드.{i}({lo}): 헤드메시지가 없다 — "
                       f"메시지 없는 장은 장당 1메시지 중핵 위반이다")
        if lo == "표" and not (s.get("표") or {}).get("rows"):
            bad.append(f"슬라이드.{i}(표): 표 rows 가 없다")
        if lo == "도식":
            t = (s.get("도식") or {}).get("type")
            if t not in svgfig.도식유형:
                bad.append(f"슬라이드.{i}(도식): 도식 type {t!r} — 카탈로그에 없다"
                           f"({', '.join(svgfig.도식유형)})")
        if lo == "이미지" and not (s.get("이미지") or {}):
            bad.append(f"슬라이드.{i}(이미지): 이미지 스펙이 없다")
        if lo == "픽토그램":
            ps = s.get("픽토그램") or []
            if not ps:
                bad.append(f"슬라이드.{i}(픽토그램): 픽토그램 목록이 없다")
            미상 = [p.get("아이콘") for p in ps if not pictogram.has(p.get("아이콘", ""))]
            if 미상:
                bad.append(f"슬라이드.{i}(픽토그램): 라이브러리에 없는 아이콘 {미상} "
                           f"— build/pictograms.json 에 없다(조용히 삼키지 않는다)")
        # 자유배치 — 좌표는 지면 %(0~100)이고 개체는 지면 안에 있어야 한다(겹침은 사용자 의도라 허용).
        if s.get("배치모드") == "자유":
            if lo not in 헤드장:
                bad.append(f"슬라이드.{i}({lo}): 자유배치는 헤드메시지 장만 "
                           f"({', '.join(헤드장)}) — 어젠다·간지는 흐름만")
            배치 = s.get("배치")
            if not isinstance(배치, dict):
                bad.append(f"슬라이드.{i}: 배치모드=자유인데 배치{{역할:{{x,y,w,h}}}}가 없다")
            else:
                for role, b in 배치.items():
                    if role not in ("헤드", "본문"):
                        bad.append(f"슬라이드.{i}.배치: 모르는 역할 {role!r} — 헤드·본문만")
                        continue
                    xs = {k: (b or {}).get(k) for k in ("x", "y", "w", "h")} if isinstance(b, dict) else {}
                    if not xs or any(not isinstance(v, (int, float)) or isinstance(v, bool)
                                     for v in xs.values()):
                        bad.append(f"슬라이드.{i}.배치.{role}: x·y·w·h 는 수(지면 %)여야 한다 — {b}")
                        continue
                    x, y, w, h = xs["x"], xs["y"], xs["w"], xs["h"]
                    if not (0 <= x <= 100 and 0 <= y <= 100 and 0 < w <= 100 and 0 < h <= 100):
                        bad.append(f"슬라이드.{i}.배치.{role}: 좌표가 지면(0~100%)을 벗어난다 "
                                   f"— x{x} y{y} w{w} h{h}")
                    elif x + w > 100.5 or y + h > 100.5:
                        bad.append(f"슬라이드.{i}.배치.{role}: 개체가 지면 밖으로 나간다 "
                                   f"— x+w={x + w:.1f} y+h={y + h:.1f} (100 이내여야)")
    return bad


def _항목들(items, base, e):
    """개조식 항목 목록 → <p class="sl-l{n}"> 나열. press 와 같은 속성 잠금."""
    out = []
    for j, it in enumerate(items or []):
        if isinstance(it, str):        # 모델이 항목을 {level,text} dict 대신 맨 문자열로 낼 때
            it = {"text": it}          # 크래시 대신 기본 위계(1)의 텍스트 항목으로 흡수한다
        lv = 속성값.열거(it.get("level"), tuple(마커), f"{base}.{j}.level", 기본=1)
        mk = 마커.get(lv, "□")
        out.append(f'      <p class="sl-l{lv}" data-ent="항목">'
                   f'<span class="mk">{mk}</span>{NBSP}'
                   f'<span class="tx" data-path="{e(base)}.{j}.text">{e(it.get("text", ""))}</span>'
                   f'</p>\n')
    return "".join(out)


def _표(tb, base, e):
    cap = (f'<div class="sl-tbl-caption">{e(tb.get("캡션", ""))}</div>'
           if tb.get("캡션") else "")
    rows = "<tr>" + "".join(f"<th>{e(h)}</th>" for h in tb.get("header", [])) + "</tr>"
    for row in tb.get("rows", []):
        rows += "<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>"
    return (f'      <div class="sl-table-wrap" data-ent="표"{_정렬속성(tb)} data-path="{e(base)}">'
            f'{cap}<table class="sl-table">{rows}</table></div>\n')


def _도식(fg, base, e):
    """SVG 도식 — 풀버전과 같은 svgfig(.fr-fig) 재사용. jachigan.js 가 그린다."""
    return "      " + svgfig.render(fg).replace(
        'class="blk fr-fig"',
        f'class="blk fr-fig sl-fig" data-path="{e(base)}"', 1)


def _이미지(img, name, base, e):
    """이미지(삽화·첨부 크롭) — 풀버전과 같은 imageasset 재사용. AI 생성물 표기까지 그대로."""
    return "      " + imageasset.render(img, name).replace(
        'class="blk fr-fig fr-img"',
        f'class="blk fr-fig fr-img sl-img" data-path="{e(base)}"', 1)


def _픽토그램(items, base, e):
    """픽토그램 나열 — 의미 아이콘 + 라벨(+설명) 카드 줄. 애셋은 build/pictogram.py."""
    import pictogram
    cards = []
    for j, it in enumerate(items or []):
        svg = pictogram.render(it.get("아이콘", ""))
        라벨 = e(it.get("라벨", ""))
        설명 = e(it.get("설명", "")) if it.get("설명") else ""
        블 = (f'      <figure class="sl-picto" data-ent="픽토그램" data-path="{e(base)}.{j}"'
              f' data-icon="{e(it.get("아이콘", ""))}">'
              f'<span class="sl-picto-ic" aria-hidden="true">{svg}</span>'
              f'<figcaption class="sl-picto-l"><span class="tx" '
              f'data-path="{e(base)}.{j}.라벨">{라벨}</span></figcaption>')
        if 설명:
            블 += (f'<p class="sl-picto-d"><span class="tx" '
                   f'data-path="{e(base)}.{j}.설명">{설명}</span></p>')
        블 += '</figure>'
        cards.append(블)
    return (f'      <div class="sl-pictos" data-ent="픽토그램나열" data-path="{e(base)}">\n'
            + "\n".join(cards) + "\n      </div>\n")


def _바닥(s, i, 쪽, e):
    """출처(좌) · 쪽번호(우) — 정량 주장 장에 출처 줄을 두는 컨설팅 규범."""
    out = ""
    if s is not None and s.get("출처"):
        out += (f'      <div class="sl-src" data-ent="출처">'
                f'<span class="tx" data-path="슬라이드.{i}.출처">{e(s["출처"])}</span></div>\n')
    out += f'      <div class="sl-num" data-ent="쪽번호">{쪽}</div>\n'
    return out


def _배치어트(자유, 배치, role, i, e):
    """자유배치 모드에서 개체를 지면 위 절대좌표로 앉히는 (class·style·경로) 세 쪽.

    좌표는 지면 %(x·y·w·h) — 조립기가 스타일에 직접 박고, 편집기는 data-배치경로 로
    되짚어 왕복한다(픽토처럼 전용 처리라 serialize 폴백에 안 샌다). 흐름 모드이거나
    이 역할에 배치가 없으면 빈 문자열 → 기존 흐름 레이아웃 그대로다(기본값 불변식).
    """
    if not 자유:
        return "", "", ""
    b = (배치 or {}).get(role)
    if not isinstance(b, dict):
        return "", "", ""
    # 좌표·인덱스는 속성값.수() 로 잠근다 — 문서에서 온 값이 속성 자리로 가므로(WP-S5 속성잠금)
    # 수 검증을 거쳐야 큰따옴표 탈출을 막는다. 수()는 .10g 로 찍어 25.5293 정밀도도 보존한다.
    # 직접 인라인 호출한다(람다·도우미로 감싸면 정적 잠금 검사가 못 밝힌다).
    자리 = f"슬라이드.{i}.배치.{role}"
    style = (f' style="left:{속성값.수(b.get("x"), 자리 + ".x", 기본=0, 최소=0, 최대=100)}%;'
             f'top:{속성값.수(b.get("y"), 자리 + ".y", 기본=0, 최소=0, 최대=100)}%;'
             f'width:{속성값.수(b.get("w"), 자리 + ".w", 기본=100, 최소=0, 최대=100)}%;'
             f'height:{속성값.수(b.get("h"), 자리 + ".h", 기본=100, 최소=0, 최대=100)}%"')
    path = f' data-배치경로="슬라이드.{속성값.수(i, "슬라이드idx", 기본=0)}.배치.{e(role)}"'
    return " sl-placed", style, path


def build(doc):
    e = html.escape
    DOC_JSON = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    PROFILE_JSON = json.dumps(load_profile("slides"),
                              ensure_ascii=False).replace("</", "<\\/")
    표지 = doc.get("표지") or {}
    테마 = doc.get("테마") or ""
    테마attr = f' data-테마="{e(테마)}"' if 테마 and 테마 != "네이비" else ""
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="slides"{테마attr}>
<head>
<meta charset="utf-8">{기준도장()}
<title>{e(표지.get("제목", ""))}</title>
<link rel="stylesheet" href="../tokens.css?v=">
<link rel="stylesheet" href="../slides.css?v=">
</head>
<body>
<script type="application/json" id="fr-doc">{DOC_JSON}</script>
<script type="application/json" id="fr-profile">{PROFILE_JSON}</script>
"""]
    # ── 표지 (1쪽 — 문서당 하나, 최상위 "표지") ──
    parts.append('<section class="sl-page sl-cover" data-ent="표지">\n')
    parts.append(f'      <h1 class="sl-title"><span class="tx" data-path="표지.제목">'
                 f'{e(표지.get("제목", ""))}</span></h1>\n')
    if 표지.get("부제"):
        parts.append(f'      <p class="sl-sub"><span class="tx" data-path="표지.부제">'
                     f'{e(표지["부제"])}</span></p>\n')
    if 표지.get("발표정보"):
        parts.append(f'      <p class="sl-info"><span class="tx" data-path="표지.발표정보">'
                     f'{e(표지["발표정보"])}</span></p>\n')
    parts.append("</section>\n")

    # ── 본문 장들 ──
    for i, s in enumerate(doc.get("슬라이드") or []):
        lo = s.get("레이아웃")
        쪽 = i + 2                      # 표지가 1쪽이다
        자유 = s.get("배치모드") == "자유"      # 자유배치(PPT식 절대좌표)면 개체를 sl-placed 로
        배치 = s.get("배치") or {}
        parts.append(f'<section class="sl-page sl-{e(lo)}'
                     f'{" sl-free" if 자유 else ""}" data-ent="슬라이드" '
                     f'data-slide-idx="{i}">\n')
        if lo == "어젠다":
            parts.append('      <h2 class="sl-head sl-head-plain">목차</h2>\n')
            for j, t in enumerate(s.get("항목") or []):
                글 = t if isinstance(t, str) else str(t)
                parts.append(f'      <p class="sl-agenda-i" data-ent="항목">'
                             f'<span class="tx" data-path="슬라이드.{i}.항목.{j}">{e(글)}</span></p>\n')
        elif lo == "간지":
            parts.append(f'      <div class="sl-sec-no"><span class="tx" '
                         f'data-path="슬라이드.{i}.번호">{e(s.get("번호", ""))}</span></div>\n')
            parts.append(f'      <h2 class="sl-sec-title"><span class="tx" '
                         f'data-path="슬라이드.{i}.제목">{e(s.get("제목", ""))}</span></h2>\n')
        else:                # 헤드메시지가 이끄는 장 — 본문·표·도식·이미지·픽토그램·마무리
            hc, hs, hp = _배치어트(자유, 배치, "헤드", i, e)
            parts.append(f'      <h2 class="sl-head{hc}" data-ent="헤드메시지"{hs}{hp}><span class="tx" '
                         f'data-path="슬라이드.{i}.헤드메시지">{e(s.get("헤드메시지", ""))}</span></h2>\n')
            bc, bs, bp = _배치어트(자유, 배치, "본문", i, e)
            parts.append(f'      <div class="sl-body sl-body-{e(lo)}{bc}"{bs}{bp}>\n')
            if lo == "표":
                parts.append(_표(s.get("표") or {}, f"슬라이드.{i}.표", e))
            elif lo == "도식":
                parts.append(_도식(s.get("도식") or {}, f"슬라이드.{i}.도식", e))
            elif lo == "이미지":
                parts.append(_이미지(s.get("이미지") or {},
                                    f"{doc.get('filename', 'sl')}-s{i}",
                                    f"슬라이드.{i}.이미지", e))
            elif lo == "픽토그램":
                parts.append(_픽토그램(s.get("픽토그램"), f"슬라이드.{i}.픽토그램", e))
            if s.get("항목"):
                parts.append(_항목들(s.get("항목"), f"슬라이드.{i}.항목", e))
            parts.append("      </div>\n")
        parts.append(_바닥(s, i, 쪽, e))
        parts.append("</section>\n")

    parts.append("""<script src="../svgfig.js?v="></script>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
<script src="../present.js?v="></script>
</body>
</html>
""")
    return "".join(parts).replace("</head>", 속성값.간격스타일(doc) + "</head>", 1)  # #3 개체 위/아래 간격


def 조립하기(등록부경로, only=None, out=None):
    """슬라이드 등록부 → HTML. 직접 호출·subprocess 공용 몸통(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [...], "로그": …}. 게이트 위반 문서는 안 쓰고
    ok=False. 산출물뿌리는 호출마다 다시 푼다(세션 오염 방지).
    """
    낼곳 = out if out else 자료뿌리.산출물뿌리()
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    docs = genres.한건만(docs, ["--only", only] if only else [])
    fail = 0
    낸것, 로그 = [], []
    for doc in docs:
        _표정규화(doc)
        bad = gate_check(doc)
        if bad:
            fail = 1
            로그.append(f"[게이트 위반] {doc['filename']}")
            for b in bad:
                로그.append(f"  ✗ {b}")
            continue
        with 자료뿌리.쓰기(os.path.join(낼곳, f"{doc['filename']}.html")) as f:
            f.write(genres.판찍기(build(doc)))
        낸것.append(f"{doc['filename']}.html")
        로그.append(f"built: {doc['filename']}.html")
    return {"ok": fail == 0, "낸것": 낸것, "로그": "\n".join(로그)}


def main():
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
