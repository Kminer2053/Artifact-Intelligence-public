#!/usr/bin/env python3
"""슬라이드 PPTX 의 차트를 **네이티브 차트**(PowerPoint '데이터 편집'이 되는 차트)로 넣는다.

'26-09-29 도식 재설계 P3(PPTX 만). 근거: 내부 기록 §P3 · critic_impl #16 ·
critic_design §5-3 · 사장님 판정 '26-09-28 ④ "PPTX 네이티브 차트는 함, HWPX 차트는 안 함".

부르는 곳은 build/topptx.py 하나다. 수확 JS 가 `.fr-fig[data-fig]` 안의 차트 SVG 를 만나면
그 스펙(data-fig)·팔레트 토큰(--fig-*)·그려진 글자 크기(px)를 크롭 항목에 같이 싣고, 조립이
여기 `넣기()` 를 먼저 부른다. 넣지 못하면(모르는 유형·그릴 값 없음·예외) False 를 돌려주고,
topptx 는 지금처럼 그 자리 PNG 크롭을 넣는다 — 차트 때문에 PPTX 전체가 서지 않는다.

그리는 규격은 svgfig.js 차트와 같다(실물 공공보고서 44쪽 육안 실측, svgfig.py 머리말):
  · 격자선 없음 · 얇은 회색 테(판) · 눈금은 svgfig 눈금()과 같은 1·2·2.5·5 배수
  · 범례는 계열 둘 이상일 때만, 판 위 가운데
  · 막대 값 라벨은 막대에 붙인다. 한 계열 3시점 이상이면 마지막 시점만 진하고 앞은 비교색(chart-mid),
    최신값 글은 굵게(흑백 인쇄에서도 보이게)
  · 꺾은선은 마지막 점에만 값 라벨(굵게), 끝 점은 크게. 셋째 계열부터 점선
  · 도넛은 안을 비운다(파이 없음, 구멍 60%), 범례는 오른쪽(자리 없으면 아래)
  · 쌓기(bar 쌓기·stack 구성비)는 칸 안 가운데 라벨, 진한 칠에는 흰 글
  · 색은 문서 설정 팔레트의 역할 토큰(--fig-chart·chart-mid·ink·sub·frame·bg·on-accent)에서만.
    계열은 한 색의 농도(svgfig 계열농도)를 **바탕색과 미리 섞은 hex** 로 칠한다(투명도에 기대지 않는다 —
    인쇄·뷰어마다 알파 처리가 다르다)
알려진 차이(잰 것은 test/r22_charts22.py): 도넛 조각 라벨이상 조각에만 값·비율), stack 세트 사이
화살표 없음, 막대 라벨 자리 넘침 판단은 판 폭 어림, 값 표시 소수 자리는 차트 안에서 한 자리수로 맞춘다.
"""
from __future__ import annotations

import math
import re

from contextlib import contextmanager

from lxml import etree
from pptx.chart.data import CategoryChartData
from pptx.chart.xlsx import CategoryWorkbookWriter
from xlsxwriter import Workbook
from pptx.dml.color import RGBColor
from pptx.enum.chart import (XL_AXIS_CROSSES, XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION,
                            XL_MARKER_STYLE, XL_TICK_LABEL_POSITION, XL_TICK_MARK)
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

FONT = "맑은 고딕"          # topptx.FONT 와 같다(공공 Windows 에 100% 있는 글꼴)
유형 = ("bar", "hbar", "line", "donut", "stack")
계열농도 = (1, 0.62, 0.38, 0.22, 0.13)                  # svgfig.js 계열농도와 같다
강조옆농도 = (0.45, 0.28, 0.16, 0.1)                     # svgfig.js stack 강조 옆 조각
# CSS 가 없는 자리의 대체값 — svgfig.js 토큰기본(= tokens.css 남색)과 같다(시험이 대조한다).
토큰기본 = {"chart": "#1F3864", "chart-mid": "#A1ABBE", "ink": "#111111", "sub": "#444444",
            "frame": "#B8B8B8", "bg": "#FFFFFF", "on-accent": "#FFFFFF"}
_색꼴 = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ── '데이터 편집' 워크북 — 글자는 글자로만 ────────────────────────────────────
# XlsxWriter 기본값(strings_to_formulas·strings_to_urls)은 '=' 로 시작하는 글을 수식으로, http(s):// 를 링크로
# 바꾼다. 범주·계열·항목 이름은 자료를 읽은 모델이 쓰므로 PowerPoint '데이터 편집' 때 수식이 계산된다(수식 주입,
# 보안 검토 S1 '26-09-29). python-pptx 1.0.2 사설 자리(_open_worksheet·_workbook_writer)에 기댄다 — r25 가 잰다.
class _글자만워크북(CategoryWorkbookWriter):
    @contextmanager
    def _open_worksheet(self, xlsx_file):
        wb = Workbook(xlsx_file, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
        ws = wb.add_worksheet()
        yield wb, ws
        wb.close()


class _차트자료(CategoryChartData):
    @property
    def _workbook_writer(self):
        w = self.__dict__.get("_글자만워크북")
        if w is None:
            w = self.__dict__["_글자만워크북"] = _글자만워크북(self)
        return w


# ── 스펙 읽기(svgfig.js 와 같은 뜻으로) ─────────────────────────────────────
def _숫자냐(v):
    """svgfig 숫자냐 — JS typeof number 이면서 유한. bool 은 수가 아니다."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _유한(v):
    """svgfig 유한 — Number(v) 가 유한수면 그 값, 아니면 0(도넛·stack 값)."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else 0.0
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return 0.0
        try:
            n = float(s)
        except ValueError:
            return 0.0
        return n if math.isfinite(n) else 0.0
    return 0.0


def _배열(v):
    return v if isinstance(v, list) else []


def _글(v):
    return "" if v is None else str(v)


def 표준(spec):
    """data-fig 스펙 → 네이티브 차트가 쓸 표준 모양. 그릴 것이 없으면 None(→ PNG 크롭).

    bar·hbar·line: {"type", "시점":[str], "계열":[{"이름", "값":[float|None]}], "단위", "쌓기"}
    donut:         {"type", "항목":[(이름, 값)], "가운데"}
    stack:         {"type", "세트":[이름], "조각":[이름], "값":[[세트별 값|None]], "강조":[이름|None]}
    """
    if not isinstance(spec, dict):
        return None
    t = spec.get("type")
    if t not in 유형:
        return None
    if t in ("bar", "hbar", "line"):
        시점 = [_글(x) for x in _배열(spec.get("시점"))]
        계열 = []
        for s in _배열(spec.get("계열")):
            if not isinstance(s, dict):
                continue
            값 = _배열(s.get("값"))
            계열.append({"이름": _글(s.get("이름")),
                        "값": [float(값[i]) if i < len(값) and _숫자냐(값[i]) else None for i in range(len(시점))]})
        if not 시점 or not any(v is not None for s in 계열 for v in s["값"]):
            return None
        return {"type": t, "시점": 시점, "계열": 계열, "단위": _글(spec.get("단위")).strip(),
                "쌓기": bool(spec.get("쌓기")) and t != "hbar"}
    if t == "donut":
        항목 = []
        for it in _배열(spec.get("항목")):
            if isinstance(it, list):
                이름, v = (it + [None, None])[:2]
            elif isinstance(it, dict):
                이름, v = it.get("이름"), it.get("값")
            else:
                이름, v = it, None
            항목.append((_글(이름), _유한(v)))
        if not 항목 or not any(v > 0 for _, v in 항목):
            return None
        return {"type": t, "항목": 항목, "가운데": _글(spec.get("가운데")).strip()}
    세트, 조각, 표 = [], [], {}
    강조 = []
    for st in _배열(spec.get("세트")):
        if not isinstance(st, dict):
            continue
        세트.append(_글(st.get("이름")))
        강조.append(st.get("강조") if isinstance(st.get("강조"), str) else None)
        for it in _배열(st.get("항목")):
            if isinstance(it, list):
                이름, v = (it + [None, None])[:2]
            elif isinstance(it, dict):
                이름, v = it.get("이름"), it.get("값")
            else:
                이름, v = it, None
            이름 = _글(이름)
            if 이름 not in 조각:
                조각.append(이름)
            표[(len(세트) - 1, 이름)] = _유한(v)
    if not 세트 or not 조각 or not any(v > 0 for v in 표.values()):
        return None
    값 = [[표.get((si, nm)) for si in range(len(세트))] for nm in 조각]
    return {"type": "stack", "세트": 세트, "조각": 조각, "값": 값, "강조": 강조,
            "차례": {(si, nm): k for si in range(len(세트))
                    for k, nm in enumerate([n for n in 조각 if (si, n) in 표])}}


def 눈금(최대, 최소):
    """svgfig.js 눈금() 그대로 — 1·2·2.5·5 배수. (아래, 위, 간격)."""
    폭 = (최대 - 최소) or abs(최대) or 1
    자릿수 = 10 ** math.floor(math.log10(폭 / 4))
    후보 = [m * 자릿수 for m in (1, 2, 2.5, 5, 10)]
    간격 = next((c for c in 후보 if 폭 / c <= 5), 후보[-1])
    위 = math.ceil(최대 / 간격 - 1e-9) * 간격
    아래 = math.floor(최소 / 간격 + 1e-9) * 간격 if 최소 < 0 else 0
    return round(아래, 6), round(위, 6), 간격


def _자리수(vs, 상한=2):
    """값 표시 소수 자리 — svgfig 수()는 소수 둘째 자리 반올림. 차트 안에서는 한 자리수로 맞춘다."""
    n = 0
    for v in vs:
        if v is None:
            continue
        s = f"{round(abs(v), 상한):.{상한}f}".rstrip("0")
        n = max(n, len(s.split(".")[1]) if "." in s else 0)
    return min(n, 상한)


def _수꼴(자리, 꼬리=""):
    return ("#,##0" + ("." + "0" * 자리 if 자리 else "")) + 꼬리


# ── 색 ───────────────────────────────────────────────────────────────────
def 토큰(tok):
    """수확한 --fig-* 값 → hex. #RRGGBB 가 아니면 대체값(svgfig 토큰읽기와 같은 규칙)."""
    out = dict(토큰기본)
    for k in 토큰기본:
        v = str((tok or {}).get(k) or "").strip()
        if _색꼴.match(v):
            out[k] = v.upper()
    return out


def 섞기(hex색, 농도, 바탕="#FFFFFF"):
    """fill-opacity 를 바탕과 미리 섞은 hex(인쇄·뷰어 알파 처리에 기대지 않는다)."""
    a = max(0.0, min(1.0, float(농도)))
    c = [int(hex색[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(바탕[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * a + y * (1 - a)):02X}" for x, y in zip(c, b))


def _RGB(h):
    return RGBColor.from_string(h[1:])


def 진하기(i):
    return 계열농도[i % len(계열농도)]


# ── XML 도우미 ────────────────────────────────────────────────────────────
def _글꼴(font, pt=None, 색=None, 굵게=None):
    """차트 글꼴 — 맑은 고딕을 latin·ea 두 축에 박는다(한글은 ea 가 있어야 적용된다)."""
    if pt is not None:
        font.size = Pt(pt)
    if 색 is not None:
        font.color.rgb = _RGB(색)
    if 굵게 is not None:
        font.bold = 굵게
    font.name = FONT
    rPr = font._rPr
    for 축 in ("a:ea", "a:cs"):
        if rPr.find(qn(축)) is None:
            rPr.append(rPr.makeelement(qn(축), {"typeface": FONT}))


def _선(fmt_line, 색=None, pt=None, 대시=None):
    if 색 is None:
        fmt_line.fill.background()
        return
    fmt_line.color.rgb = _RGB(색)
    if pt is not None:
        fmt_line.width = Pt(pt)
    if 대시 is not None:
        fmt_line.dash_style = 대시


def _판테(chart, 색, pt):
    """판(plot area) 얇은 테 — svgfig 판테(격자선 없이 테만)."""
    pa = chart._chartSpace.find(qn("c:chart")).find(qn("c:plotArea"))
    old = pa.find(qn("c:spPr"))
    if old is not None:
        pa.remove(old)
    sp = etree.SubElement(pa, qn("c:spPr"))
    ext = pa.find(qn("c:extLst"))
    if ext is not None:                       # spPr 는 extLst 앞(스키마 차례)
        ext.addprevious(sp)
    etree.SubElement(sp, qn("a:noFill"))
    if 색:
        ln = etree.SubElement(sp, qn("a:ln"), w=str(int(Pt(pt))))
        sf = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(sf, qn("a:srgbClr"), val=색[1:])
    else:
        ln = etree.SubElement(sp, qn("a:ln"))
        etree.SubElement(ln, qn("a:noFill"))


def _배치(부모, x, y, w, h):
    """c:layout 수동 배치 — 도넛 판·범례 자리를 정한다(가운데 글상자를 구멍에 맞추려고)."""
    ly = 부모.find(qn("c:layout"))
    if ly is None:
        ly = etree.Element(qn("c:layout"))
        if 부모.tag == qn("c:plotArea"):            # plotArea: layout 이 맨 앞
            부모.insert(0, ly)
        else:                                       # legend: legendPos, legendEntry*, layout, overlay…
            앞 = (부모.findall(qn("c:legendEntry")) or [부모.find(qn("c:legendPos"))])[-1]
            if 앞 is not None:
                앞.addnext(ly)
            else:
                부모.insert(0, ly)
    for c in list(ly):
        ly.remove(c)
    ml = etree.SubElement(ly, qn("c:manualLayout"))
    if 부모.tag == qn("c:plotArea"):
        etree.SubElement(ml, qn("c:layoutTarget"), val="inner")
    etree.SubElement(ml, qn("c:xMode"), val="edge")
    etree.SubElement(ml, qn("c:yMode"), val="edge")
    for 이름, v in (("c:x", x), ("c:y", y), ("c:w", w), ("c:h", h)):
        etree.SubElement(ml, qn(이름), val=f"{max(0.0, min(1.0, v)):.4f}")


def _점라벨(point, 위치=None, pt=None, 색=None, 굵게=None, 이름=False, 값=True, 꼴=None):
    dl = point.data_label
    if pt is not None or 색 is not None or 굵게 is not None:
        _글꼴(dl.font, pt, 색, 굵게)
    if 위치 is not None:
        dl.position = 위치
    el = dl._dLbl
    for tag, on in (("c:showVal", 값), ("c:showSerName", 이름)):
        x = el.find(qn(tag))
        if x is not None:
            x.set("val", "1" if on else "0")
    if 꼴:                                    # 점마다 제 소수 자리(svgfig 수(): '3'·'12.5' — 계열 한 꼴로 '3.00' 안 됨)
        nf = el.find(qn("c:numFmt"))
        if nf is None:
            nf = etree.Element(qn("c:numFmt"))
            뒤 = next((c for c in el if etree.QName(c).localname in
                      ("spPr", "txPr", "dLblPos", "showLegendKey", "showVal", "showCatName", "showSerName",
                       "showPercent", "showBubbleSize", "separator", "extLst")), None)
            if 뒤 is not None:
                뒤.addprevious(nf)
            else:
                el.append(nf)
        nf.set("formatCode", 꼴)
        nf.set("sourceLinked", "0")
    if 이름 and 값 and el.find(qn("c:separator")) is None:
        sep = etree.SubElement(el, qn("c:separator"))
        sep.text = " "
        ext = el.find(qn("c:extLst"))
        if ext is not None:
            ext.addprevious(sep)


def _점칠(point, 색, 테=None, 테pt=None):
    f = point.format.fill
    f.solid()
    f.fore_color.rgb = _RGB(색)
    if 테:
        _선(point.format.line, 테, 테pt)


def _글상자(slide, x, y, w, h, 글, pt, 색, 굵게=False, 맞춤=PP_ALIGN.RIGHT, 가운데=False):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.word_wrap = bool(가운데)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE if 가운데 else MSO_ANCHOR.BOTTOM
    p = tf.paragraphs[0]
    p.alignment = 맞춤
    r = p.add_run()
    r.text = 글
    _글꼴(r.font, pt, 색, 굵게)
    return tb


def _글폭(t, pt):
    """글 폭 어림(pt) — 한글 1em · 그 밖 0.55em(svgfig w()와 같은 어림)."""
    return sum(1.0 if ord(c) > 0x2000 else 0.55 for c in str(t)) * pt * 1.04


# ── 넣기 ─────────────────────────────────────────────────────────────────
def 넣기(slide, 차트, x, y, w, h, k):
    """차트 하나를 네이티브로 넣는다. x·y·w·h 는 EMU(그 SVG 자리), k 는 px→pt 배율.
    넣었으면 True, 못 넣었으면 False(부른 쪽이 PNG 크롭으로 넣는다)."""
    sp = 표준((차트 or {}).get("spec"))
    if sp is None:
        return False
    색 = 토큰((차트 or {}).get("tok"))
    fpx = (차트 or {}).get("fpx")
    fpt = max(6.0, min(40.0, float(fpx) * k)) if _숫자냐(fpx) and fpx > 0 else 10.5
    넣은 = []
    try:
        _그리기(slide, sp, 색, fpt, int(x), int(y), int(w), int(h), 넣은)
        return True
    except Exception:
        # 반쯤 넣은 모양(단위 글상자·차트 틀)을 남기지 않는다 — 지우고 PNG 로 돌아간다
        for g in 넣은:
            try:
                g._element.getparent().remove(g._element)
            except Exception:
                pass
        return False


def _그리기(slide, sp, 색, fpt, x, y, w, h, 넣은):
    t = sp["type"]
    단위 = sp.get("단위") if t in ("bar", "hbar", "line") else ""
    if 단위:                                  # svgfig 단위표기 — 판 오른쪽 위 "(단위: …)"
        uh = int(Pt(fpt * 1.5))
        넣은.append(_글상자(slide, x, y, w, uh, f"(단위: {단위})", fpt, 색["sub"]))
        y, h = y + uh, max(h - uh, int(Pt(fpt * 4)))
    if t == "donut":
        return _도넛(slide, sp, 색, fpt, x, y, w, h, 넣은)
    if t == "stack":
        return _구성(slide, sp, 색, fpt, x, y, w, h, 넣은)
    return _계열차트(slide, sp, 색, fpt, x, y, w, h, 넣은)


def _공통(chart, 색, fpt):
    chart.has_title = False
    _글꼴(chart.font, fpt, 색["ink"])


def _축(ax, 색, fpt, 줄=True):
    ax.major_tick_mark = XL_TICK_MARK.NONE
    ax.minor_tick_mark = XL_TICK_MARK.NONE
    ax.has_major_gridlines = False        # 격자선 없음 — 실물 규격
    ax.has_minor_gridlines = False
    _글꼴(ax.tick_labels.font, fpt, 색["sub"])
    _선(ax.format.line, 색["frame"] if 줄 else None, 0.6)


def _계열차트(slide, sp, 색, fpt, x, y, w, h, 넣은):
    t, 쌓기 = sp["type"], sp["쌓기"]
    계열 = sp["계열"]
    모든값 = [v for s in 계열 for v in s["값"] if v is not None]
    if 쌓기:                                 # 음수는 0 아래로 따로 쌓인다(PowerPoint) — 축은 양·음 합을 따로 본다
        n_ = range(len(sp["시점"]))
        양 = [sum(s["값"][i] for s in 계열 if s["값"][i] is not None and s["값"][i] > 0) for i in n_]
        음 = [sum(s["값"][i] for s in 계열 if s["값"][i] is not None and s["값"][i] < 0) for i in n_]
        아래, 위, 간격 = 눈금(max(양 + [0]), min(음 + [0]))
    else:
        아래, 위, 간격 = 눈금(max(모든값 + [0]), min(모든값 + [0]))
    자리 = _자리수(모든값)
    cd = _차트자료(number_format=_수꼴(자리))
    cd.categories = sp["시점"]
    for s in 계열:
        cd.add_series(s["이름"], s["값"])
    종류 = {"bar": XL_CHART_TYPE.COLUMN_STACKED if 쌓기 else XL_CHART_TYPE.COLUMN_CLUSTERED,
           "hbar": XL_CHART_TYPE.BAR_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS}[t]
    gf = slide.shapes.add_chart(종류, Emu(x), Emu(y), Emu(w), Emu(h), cd)
    넣은.append(gf)
    ch = gf.chart
    _공통(ch, 색, fpt)
    여럿 = len(계열) > 1
    ch.has_legend = 여럿                     # 범례는 둘 이상일 때만, 판 위 가운데
    if 여럿:
        ch.legend.position = XL_LEGEND_POSITION.TOP
        ch.legend.include_in_layout = False
        _글꼴(ch.legend.font, fpt, 색["sub"])
    va, ca = ch.value_axis, ch.category_axis
    va.minimum_scale, va.maximum_scale, va.major_unit = 아래, 위, 간격
    va.tick_labels.number_format = _수꼴(_자리수([간격, 아래, 위], 6))
    va.tick_labels.number_format_is_linked = False
    _축(va, 색, fpt, 줄=False)
    _축(ca, 색, fpt, 줄=True)
    ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW     # 음수 막대가 있어도 이름은 판 아래
    if t == "hbar":
        ca.reverse_order = True                             # 첫 항목이 위(svgfig 차례)
        ca.crosses = XL_AXIS_CROSSES.MAXIMUM                # 값 축은 그대로 아래
    _판테(ch, 색["frame"], 0.6)
    plot = ch.plots[0]
    n = len(sp["시점"])
    끝 = n - 1
    if t in ("bar", "hbar"):
        plot.gap_width = 60                                 # 막대 = 칸의 62%(svgfig 막대폭)
        plot.overlap = 100 if 쌓기 else 0
        최신만 = t == "bar" and len(계열) == 1 and not 쌓기 and n >= 3
        # 판 폭 어림 — 라벨이 막대 자리보다 넓으면 붙이지 않는다(svgfig: 글자를 하한 밑으로 안 줄인다)
        판폭 = Emu(w).pt * 0.86
        칸 = 판폭 / max(n, 1)
        묶음 = 1 if 쌓기 else max(len(계열), 1)
        막대 = min(fpt * 3.4, 칸 * 0.62 / 묶음)
        라벨자리 = 칸 * 0.92 if (묶음 == 1 and not 쌓기) else 막대 + 2
        for k_, s in enumerate(계열):
            ser = plot.series[k_]
            f = ser.format.fill
            f.solid()
            f.fore_color.rgb = _RGB(색["chart-mid"] if 최신만 else 섞기(색["chart"], 진하기(k_), 색["bg"]))
            _선(ser.format.line, None)
            ser.invert_if_negative = False
            for i, v in enumerate(s["값"]):
                if v is None:
                    continue
                if 최신만 and i == 끝:
                    _점칠(ser.points[i], 색["chart"])
                글 = f"{abs(v):,.{자리}f}"
                if t == "bar" and _글폭(글, fpt) > 라벨자리:
                    continue
                흰 = 쌓기 and 진하기(k_) >= 0.85
                굵게 = (i == 끝 and not 쌓기 and t == "bar")
                _점라벨(ser.points[i], XL_LABEL_POSITION.CENTER if 쌓기 else XL_LABEL_POSITION.OUTSIDE_END,
                       fpt, 색["on-accent"] if 흰 else 색["ink"], 굵게, 꼴=_수꼴(_자리수([v])))
    else:                                                   # line
        for k_, s in enumerate(계열):
            ser = plot.series[k_]
            ser.smooth = False
            c = 섞기(색["chart"], 진하기(k_), 색["bg"])
            _선(ser.format.line, c, max(0.75, fpt * 0.16), MSO_LINE_DASH_STYLE.DASH if k_ >= 2 else None)
            ser.marker.style = XL_MARKER_STYLE.CIRCLE
            ser.marker.size = max(2, min(72, round(fpt * 0.42)))
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = _RGB(c)
            _선(ser.marker.format.line, None)
            있는 = [i for i, v in enumerate(s["값"]) if v is not None]
            if not 있는:
                continue
            j = 있는[-1]                                    # 값 라벨은 마지막 점에만(최신값, 굵게)
            pt_ = ser.points[j]
            pt_.marker.style = XL_MARKER_STYLE.CIRCLE
            pt_.marker.size = max(3, min(72, round(fpt * 0.6)))
            pt_.marker.format.fill.solid()
            pt_.marker.format.fill.fore_color.rgb = _RGB(c)
            _선(pt_.marker.format.line, None)
            _점라벨(pt_, XL_LABEL_POSITION.RIGHT, fpt, 색["ink"], True, 꼴=_수꼴(_자리수([s["값"][j]])))
    return 넣은


def _도넛(slide, sp, 색, fpt, x, y, w, h, 넣은):
    항목 = sp["항목"]
    값 = [max(0.0, v) for _, v in 항목]
    총 = sum(값) or 1
    자리 = _자리수(값)
    cd = _차트자료(number_format=_수꼴(자리))
    cd.categories = [nm for nm, _ in 항목]
    cd.add_series("", 값)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Emu(x), Emu(y), Emu(w), Emu(h), cd)
    넣은.append(gf)
    ch = gf.chart
    _공통(ch, 색, fpt)
    plot = ch.plots[0]
    plot.vary_by_categories = True
    dn = ch._chartSpace.find(qn("c:chart")).find(qn("c:plotArea")).find(qn("c:doughnutChart"))
    for tag, val in (("c:firstSliceAng", "0"), ("c:holeSize", "60")):   # 위에서 시계 방향 · 구멍 60%
        el = dn.find(qn(tag))
        if el is None:
            el = etree.SubElement(dn, qn(tag))
        el.set("val", val)
    ser = plot.series[0]
    for k_, v in enumerate(값):
        c = 섞기(색["chart"], 진하기(k_), 색["bg"])
        _점칠(ser.points[k_], c, 색["bg"], 1.0)
        if v / 총 >= 0.08:                                   # 얇은 조각엔 글을 넣지 않는다(겹침)
            _점라벨(ser.points[k_], None, fpt, 색["on-accent"] if 진하기(k_) >= 0.6 else 색["ink"], True,
                   꼴=_수꼴(_자리수([v])))
    W, H = Emu(w).pt, Emu(h).pt
    범례폭 = fpt * 2.6 + max([_글폭(nm, fpt) for nm, _ in 항목] or [0])
    범례높 = len(항목) * fpt * 1.8
    D = max(fpt * 6, min(H * 0.94, W * 0.44))
    옆 = D + fpt * 2 + 범례폭 <= W
    ch.has_legend = True
    lg = ch.legend
    lg.include_in_layout = False
    _글꼴(lg.font, fpt, 색["ink"])
    if 옆:
        x0 = (W - (D + fpt * 2 + 범례폭)) / 2
        px, py = x0, (H - D) / 2
        lg.position = XL_LEGEND_POSITION.RIGHT
        _배치(lg._element, (x0 + D + fpt * 2) / W, max(0.0, (H - 범례높) / 2) / H, 범례폭 / W, min(H, 범례높) / H)
    else:
        D = max(fpt * 5, min(D, H - 범례높 - fpt * 1.6))
        px, py = (W - D) / 2, 0.0
        lg.position = XL_LEGEND_POSITION.BOTTOM
        _배치(lg._element, max(0.0, (W - 범례폭) / 2) / W, (D + fpt * 1.2) / H, min(W, 범례폭) / W,
             min(H - D - fpt * 1.2, 범례높) / H)
    pa = ch._chartSpace.find(qn("c:chart")).find(qn("c:plotArea"))
    _배치(pa, px / W, py / H, D / W, D / H)
    if sp.get("가운데"):                                     # 구멍 가운데 글(굵게)
        안 = D * 0.6 * 0.86
        cx, cy = x + int(Pt(px + D / 2 - 안 / 2)), y + int(Pt(py + D / 2 - 안 / 2))
        넣은.append(_글상자(slide, cx, cy, int(Pt(안)), int(Pt(안)), sp["가운데"], round(fpt * 1.1, 1),
                                 색["ink"], True, PP_ALIGN.CENTER, 가운데=True))
    return 넣은


def _구성(slide, sp, 색, fpt, x, y, w, h, 넣은):
    """stack(구성비 세트) → 100% 쌓은 세로 막대. 조각 라벨 '이름 값%', 강조 조각만 진하게."""
    세트, 조각, 값 = sp["세트"], sp["조각"], sp["값"]
    모든 = [v for row in 값 for v in row if v is not None]
    자리 = _자리수(모든)
    cd = _차트자료(number_format=_수꼴(자리, '"%"'))
    cd.categories = 세트
    for nm, row in zip(조각, 값):
        cd.add_series(nm, [None if v is None else max(0.0, v) for v in row])
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED_100, Emu(x), Emu(y), Emu(w), Emu(h), cd)
    넣은.append(gf)
    ch = gf.chart
    _공통(ch, 색, fpt)
    ch.has_legend = False                                   # 조각 이름은 라벨이 말한다(svgfig 와 같음)
    va, ca = ch.value_axis, ch.category_axis
    va.visible = False
    _축(va, 색, fpt, 줄=False)
    _축(ca, 색, fpt, 줄=False)
    _글꼴(ca.tick_labels.font, fpt, 색["ink"], True)
    _판테(ch, None, 0)
    plot = ch.plots[0]
    W = Emu(w).pt
    막대 = min(fpt * 7, W * 0.16)
    칸 = W / max(len(세트), 1)
    plot.gap_width = int(max(50, min(500, (칸 - 막대) / 막대 * 100)))
    plot.overlap = 100
    for s_i, nm in enumerate(조각):
        ser = plot.series[s_i]
        _선(ser.format.line, 색["bg"], 0.75)
        for si in range(len(세트)):
            v = 값[s_i][si]
            if v is None:
                continue
            강 = sp["강조"][si]
            acc = 강 is not None and 강 == nm
            k_ = sp["차례"].get((si, nm), s_i)
            농도 = 1 if acc else (강조옆농도[k_ % 4] if 강 is not None else 진하기(k_))
            _점칠(ser.points[si], 섞기(색["chart"], 농도, 색["bg"]), 색["bg"], 0.75)
            if v > 0:
                _점라벨(ser.points[si], XL_LABEL_POSITION.CENTER, fpt,
                       색["on-accent"] if 농도 >= 0.6 else 색["ink"], acc, 이름=True, 값=True,
                       꼴=_수꼴(_자리수([v]), '"%"'))
    return 넣은


# ── 되읽기(시험·요약용) ─────────────────────────────────────────────────────
def 되읽기(graphic_frame):
    """PPTX 차트 하나의 종류·범주·계열 이름·값을 XML 에서 다시 읽는다."""
    ch = graphic_frame.chart
    pa = ch._chartSpace.find(qn("c:chart")).find(qn("c:plotArea"))
    종류 = [etree.QName(c).localname for c in pa if etree.QName(c).localname.endswith("Chart")]
    계열 = []
    범주 = []
    for ser in pa.iter(qn("c:ser")):
        v = ser.find(qn("c:tx") + "//" + qn("c:v"))          # 이름은 캐시 값(수식 Sheet1!$B$1 말고)
        이름 = (v.text or "") if v is not None else ""
        cat = ser.find(qn("c:cat"))
        if cat is not None and not 범주:
            pts = cat.findall(".//" + qn("c:pt"))
            범주 = [(p.find(qn("c:v")).text or "") for p in sorted(pts, key=lambda p: int(p.get("idx")))]
        n = len(범주)
        vals = [None] * n
        for p in ser.find(qn("c:val")).findall(".//" + qn("c:pt")):
            i = int(p.get("idx"))
            if i < n:
                vals[i] = float(p.find(qn("c:v")).text)
        계열.append({"이름": 이름, "값": vals})
    return {"종류": 종류, "범주": 범주, "계열": 계열}
