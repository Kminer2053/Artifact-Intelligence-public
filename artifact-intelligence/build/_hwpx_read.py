#!/usr/bin/env python3
"""만든 HWPX 를 **되읽어** 문단마다 실제 서식을 뽑는다. venv 에서 돈다.

    build/.hwpxenv/bin/python build/_hwpx_read.py <파일.hwpx>

손으로 XML 을 파싱하지 않는다. 전에는 대조기가 header.xml 을 정규식으로 뜯었는데,
셀 음영을 못 읽어 **파일에 멀쩡히 들어 있는 `#DFE6F7` 을 "없음" 이라고 적었다**
(2026-08-05). 재는 쪽이 틀리면 고친 것도 안 고친 것으로 보인다.

라이브러리가 이미 아는 것을 쓴다:
  · `read_fidelity.resolve_run_spans` — run 마다 pt·굵기·색·**글꼴 이름**까지 풀어 준다
  · `headers[0].paragraph_property(id)` — margin·align·border·heading·line_spacing
  · `headers[0].border_fill(id)` — 바탕색
"""
from __future__ import annotations

import json
import sys

from hwpx.document import HwpxDocument
from hwpx.tools.read_fidelity import resolve_run_spans

HU = 283.465


def _수(v, 기본=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 기본


def 읽기(경로: str) -> dict:
    d = HwpxDocument.open(경로)
    h = d.oxml.headers[0]

    # 바탕색 표 (borderFill id → faceColor).
    # `border_fill()` 은 GenericElement 를 주는데 faceColor 는 그 **자식**(fillBrush/winBrush)
    # 안에 있다. 겉만 보고 "없음" 이라 적으면, 파일에 멀쩡히 든 #DFE6F7 을 놓친다
    # (2026-08-05 실제로 그랬다 — 되레 고친 것을 안 고쳤다고 보고할 뻔했다).
    # `h.border_fill(i)` 는 GenericElement 를 주는데 그 안에서 faceColor 가 안 나온다
    # (라이브러리가 이 속성을 겉으로 내주지 않는다 — 6.0.2 실측).
    # 그래서 이 한 속성만 원본 XML 에서 읽는다. 포맷 전체를 손으로 파싱하는 게 아니라,
    # 접근자가 비워 둔 칸 하나를 메우는 것이다.
    import re
    import zipfile

    바탕 = {}
    with zipfile.ZipFile(경로) as z:
        _h = z.read("Contents/header.xml").decode("utf-8", "replace")
    for m in re.finditer(r'<hh:borderFill\b[^>]*\bid="(\d+)"'
                         r'((?:(?!</hh:borderFill>).)*?)faceColor="(#[0-9A-Fa-f]{6})"',
                         _h, re.S):
        바탕[m.group(1)] = m.group(3).upper()

    # 변별 괘선 표 (borderFill id → 변마다 (선종류, 굵기mm, 색)). 셀 괘선 전이(4-A·B)를
    # 대조가 재려면 이 눈이 있어야 한다 — 없던 시절 겉선·정렬 소실을 사람 눈만 잡았다
    # (2026-08-13~14 육안 라운드). 속성 순서를 가정하지 않는다.
    변별표 = {}
    _변이름 = {"topBorder": "상", "rightBorder": "우",
             "bottomBorder": "하", "leftBorder": "좌"}
    for m in re.finditer(r'<hh:borderFill\b[^>]*?\bid="(\d+)"'
                         r'((?:(?!</hh:borderFill>).)*)', _h, re.S):
        변들 = {}
        for 변m in re.finditer(r'<hh:(topBorder|rightBorder|bottomBorder|leftBorder)'
                              r'\b([^>]*)>', m.group(2)):
            속성 = dict(re.findall(r'(\w+)="([^"]*)"', 변m.group(2)))
            if (속성.get("type") or "NONE") == "NONE":
                continue
            폭 = re.search(r"([\d.]+)", 속성.get("width") or "")
            변들[_변이름[변m.group(1)]] = {
                "선종류": 속성.get("type"),
                "굵기mm": float(폭.group(1)) if 폭 else None,
                "색": (속성.get("color") or "").upper()}
        if 변들:
            변별표[m.group(1)] = 변들

    # 문단 여백·줄간격도 마찬가지로 원본에서 읽는다.
    # `ParagraphProperty.margin` 은 이 골격에서 늘 None 이다 — 값이 `<hp:switch>/<hp:default>`
    # 안에 들어 있고 그 접근자가 거기까지 안 들어간다(6.0.2 실측).
    # 2026-08-05, 이걸 모르고 "왼여백 0.0mm" 이라 적어 **제대로 들어간 값을 안 들어갔다고**
    # 보고할 뻔했다. 재는 쪽이 틀리면 고친 것도 안 고친 것으로 보인다.
    _속 = {}
    for m in re.finditer(r'<hh:paraPr\b([^>]*)>((?:(?!</hh:paraPr>).)*?)</hh:paraPr>', _h, re.S):
        i = re.search(r'\bid="(\d+)"', m.group(1))
        if not i:
            continue
        b = m.group(2)
        여 = re.search(r'<hh:margin>(.*?)</hh:margin>', b, re.S)   # 첫 벌이면 족하다
        값 = dict(re.findall(r'<hc:(\w+) value="(-?\d+)"', 여.group(1))) if 여 else {}
        # 줄 간격은 **타입을 보고 읽어야 한다.** `FIXED` 면 value 는 퍼센트가 아니라
        # HWPUNIT 이다. 안 보고 그대로 퍼센트로 읽었더니 150% 가 1950% 로 나와
        # 대조가 38건 전부 실패했다(2026-08-06).
        줄 = re.search(r'<hh:lineSpacing[^>]*\bvalue="(\d+)"', b)
        줄형 = re.search(r'<hh:lineSpacing[^>]*\btype="(\w+)"', b)
        줄높이mm = (round(int(줄.group(1)) / HU, 3)
                  if (줄 and 줄형 and 줄형.group(1) == "FIXED") else None)
        정 = re.search(r'<hh:align[^>]*horizontal="(\w+)"', b)
        머 = re.search(r'<hh:heading[^>]*type="(\w+)"', b)
        쪽 = re.search(r'pageBreakBefore="1"', b)
        테 = re.search(r'<hh:border[^>]*borderFillIDRef="(\d+)"', b)
        분 = re.search(r'breakNonLatinWord="(\w+)"', b)
        _속[i.group(1)] = {
            "왼여백mm": round(int(값.get("left", 0)) / HU, 2),
            "내어쓰기mm": round(int(값.get("intent", 0)) / HU, 2),
            "위여백mm": round(int(값.get("prev", 0)) / HU, 2),
            "아래여백mm": round(int(값.get("next", 0)) / HU, 2),
            "줄간격": (int(줄.group(1)) if (줄 and 줄높이mm is None) else None),
            "줄높이mm": 줄높이mm,
            "정렬": 정.group(1) if 정 else "LEFT",
            "글머리": 머.group(1) if 머 else None,
            "어절분리": 분.group(1) if 분 else "BREAK_WORD",
            "쪽나눔": bool(쪽),
            "바탕색": 바탕.get(테.group(1)) if 테 else None,
        }

    # 자간(charPr 의 spacing.hangul, 단위 %)은 `resolve_run_spans` 가 안 내준다
    # (span 이 가진 것: bold·color·font·size_pt·strikeout·sub/superscript·text·underline).
    # 그런데 이 값이 빠지면 자간사냥 결과가 옮겨졌는지 아무도 못 본다 — 실제로 안 옮겨지고
    # 있었는데 대조는 38/38 통과라고 했다(2026-08-06). 그래서 charPr 표를 따로 읽어
    # run 순서대로 짝지어 붙인다.
    자간표 = {}
    for m in re.finditer(r'<hh:charPr\b[^>]*\bid="(\d+)"'
                         r'((?:(?!</hh:charPr>).)*?)<hh:spacing\b[^>]*\bhangul="(-?\d+)"',
                         _h, re.S):
        자간표[m.group(1)] = int(m.group(3))
    # run 을 문서 차례대로 (글, 자간) 으로 훑는다. 정규식으로 `<hp:run>…</hp:run>` 을
    # 잘라 세면 안 된다 — 표 안에 run 이 겹쳐 들어 있어 비탐욕 매칭이 엉뚱한 데서 닫힌다.
    import xml.etree.ElementTree as _ET
    HPNS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    차례 = []
    with zipfile.ZipFile(경로) as z:
        for 이름 in sorted(n for n in z.namelist()
                          if re.fullmatch(r"Contents/section\d+\.xml", n)):
            for run in _ET.fromstring(z.read(이름)).iter(f"{HPNS}run"):
                글 = "".join(t.text or "" for t in run.findall(f"{HPNS}t"))
                if 글:
                    차례.append((글, 자간표.get(run.get("charPrIDRef"), 0)))

    # run 단위 서식 — 문단 순서대로 온다.
    # **차례 번호로 맞추지 않는다** — 라이브러리가 run 을 세는 기준이 우리와 달라
    # 표가 든 문서에서 통째로 밀린다(그렇게 맞췄다가 자간이 다 어긋나 보였다).
    # 글로 맞추고, 안 맞으면 맞을 때까지 앞으로 감는다.
    스팬, 손 = [], 0
    for s in resolve_run_spans(d):
        자간 = 0
        for j in range(손, min(손 + 40, len(차례))):
            if 차례[j][0] == s.text:
                자간, 손 = 차례[j][1], j + 1
                break
        스팬.append({"글": s.text, "pt": s.size_pt, "굵게": bool(s.bold), "색": s.color,
                    "글꼴": s.font, "밑줄": bool(s.underline),
                    "취소선": bool(s.strikeout), "자간": 자간})

    빈속 = {"왼여백mm": 0, "내어쓰기mm": 0, "위여백mm": 0, "아래여백mm": 0,
           "줄간격": 160, "정렬": "LEFT", "글머리": None, "어절분리": "BREAK_WORD",
           "쪽나눔": False, "바탕색": None}
    문단들 = []
    for p in d.paragraphs:
        문단들.append({
            "글": p.text or "",
            **_속.get(str(p.para_pr_id_ref), 빈속),
            "표": len(getattr(p, "tables", []) or []) > 0,
        })

    # 표 — 셀마다 글·음영·크기
    표들 = []
    for sec in d.sections:
        for p in sec.paragraphs:
            for t in (getattr(p, "tables", []) or []):
                행 = []
                for r in t.rows:                       # rows 는 개수가 아니라 **행 목록**이다
                    칸 = []
                    for c in r.cells:
                        bf = c.element.get("borderFillIDRef") if c.element is not None else None
                        문단 = [{"글": cp.text or "",
                                "정렬": _속.get(str(cp.para_pr_id_ref), 빈속)["정렬"],
                                "줄간격": _속.get(str(cp.para_pr_id_ref), 빈속)["줄간격"]}
                               for cp in (getattr(c, "paragraphs", []) or [])]
                        여 = None
                        if c.element is not None and c.element.get("hasMargin") == "1":
                            for cm in c.element.iter():
                                if cm.tag.endswith("cellMargin"):
                                    여 = round(_수(cm.get("left")) / HU, 2)
                        칸.append({"글": (c.text or "").strip(), "안여백mm": 여,
                                  "바탕": 바탕.get(str(bf)) if bf else None,
                                  "테두리": 변별표.get(str(bf)) if bf else None,
                                  "폭mm": round(_수(getattr(c, "width", 0)) / HU, 2),
                                  "높이mm": round(_수(getattr(c, "height", 0)) / HU, 2),
                                  "병합": list(getattr(c, "span", (1, 1))),
                                  "빈문단": sum(1 for x in 문단 if not x["글"].strip()),
                                  "문단": 문단})
                    if 칸:
                        행.append(칸)
                표들.append({"행": 행})

    쪽 = {}
    try:
        from hwpx.tools.layout_preview import render_layout_preview
        pv = render_layout_preview(경로, mode="pages")
        if pv.pages:
            g = pv.pages[0]
            쪽 = {"크기mm": [round(g.width_mm), round(g.height_mm)],
                 "여백mm": [round(g.margins_mm[k], 1)
                          for k in ("top", "right", "bottom", "left")],
                 "머리말mm": round(g.margins_mm.get("header", 0), 1),
                 "꼬리말mm": round(g.margins_mm.get("footer", 0), 1)}
    except Exception as e:
        쪽 = {"못잼": f"{type(e).__name__}"}

    # 6.0 에서 doc.media 로 옮겼다 — 옛 이름은 7.0 에 없어진다
    _미 = getattr(d, "media", None)
    참조 = (_미.picture_references() if _미 else d.picture_references()) or ()
    그림 = [{"폭mm": round(_수(getattr(g, "width", 0)) / HU, 2),
            "높이mm": round(_수(getattr(g, "height", 0)) / HU, 2)} for g in 참조]

    return {"문단": 문단들, "스팬": 스팬, "표": 표들, "그림": 그림, "쪽": 쪽}


if __name__ == "__main__":
    # 라이브러리가 enum 을 돌려주는 자리가 있다(ParagraphAlignment 등) — 글자로 눕힌다
    print(json.dumps(읽기(sys.argv[1]), ensure_ascii=False, default=str))
