#!/usr/bin/env python3
"""표 스펙 공용 — 정규화와 HTML 렌더를 한 곳에서 한다('26-09-29 도식·표 재설계 P1).

왜 한 곳인가 — 표를 그리는 조립기가 여섯이다(1p·풀버전·시행문·보도자료·규정·옛 슬라이드).
예전엔 장르마다 `header`·`rows` 를 각자 <tr> 로 펴서, 새 키(열폭·정렬·병합…)를 넣으려면 여섯 벌을
고쳐야 했고 벌마다 조금씩 갈라졌다(수치 정렬 정규식이 두 벌로 갈라졌던 수치꼴.py 머리말과 같은 일).
여기서 스펙을 한 번 정규화하고, 조립기는 자기 표 클래스와 기본값(보고서형·통계형)만 넘긴다.

스펙(기존 `header`+`rows` 문자열 격자는 그대로 — 약한 모델에 새로 가르칠 것이 없다)
  style   모양 프리셋 — 1p `table.style` 체계를 전 장르로 넓힌다. 후보는 온톨로지
          data_elements.표.디자인.스타일_프리셋(1p 편집기 프로파일과 같은 여섯)에서 센다.
  머리    머리 칸 모양: 파랑(#DFE6F7, 기본) · 회색 · 없음
  첫열    첫 열을 행 머리로 칠한다(#F2F2F2). 없으면 장르 기본(보고서형은 켬, 통계형은 끔)
  열폭    열마다 % (합이 100 이 아니면 비율로 맞춘다). 열 수와 다르면 버린다
  열정렬  열마다 왼 | 가운데 | 오른 | ""(자동). 열 수와 다르면 버린다
  병합    [{"행", "열", "가로", "세로"}] — 좌표는 header 를 0행으로 센다. 덮인 칸의 글은 버린다
  강조    [{"행", "열", "색"}] — 칸 하나. 행만 주면 그 행 몸 칸 전부, 열만 주면 그 열 몸 칸 전부.
          색 = 강조(연노랑+굵게) | 회색(+굵게). 흑백 인쇄에서도 남도록 늘 굵게를 같이 건다
  크기    작게 | 보통 | 크게 — 칸 글자 크기 한 축('26-09-29 편집기 막대, 사장님 판정 ① 크기 3단).
          표는 늘 판면 전폭이라(아래 '폭' 없음) 면적은 글자가 키운다: 작게 = 장르 표 글자 −1pt
          (하한 10.5pt, 장르 기본이 그보다 작으면 그대로), 크게 = +1pt. 보통은 키를 안 남긴다.
          CSS 는 tokens.css `[data-크기]` 칸 규칙 하나(장르 글자에 em 으로 얹는다)

근거 없는 키는 두지 않는다(critic_design #25): 줄무늬(재경부 관행에 없음) · 머리반복(행 단위
쪽 넘김이면 늘 반복) · 폭(표는 늘 판면 전폭, critic_design 1-1).

정렬 기본값(사장님 판정 '26-09-28 ④, critic_design 1-9)
  · 머리 칸은 가운데
  · 긴 글 열(몸 칸 평균 12자 이상이거나 칸 안 줄바꿈이 있는 열)은 왼쪽
  · 짧은 칸은 가운데
  · 숫자 열 오른쪽은 **통계형에만**(보도자료 본문 표, 또는 열 6개 이상). 보고서형 숫자 열은 가운데다
    (재경부 보고서 짧은 칸 표의 오른쪽 18%, 보도 통계표 73% — critic_design 1-9 실측)

속성 자리는 전부 build/속성값.py 의 수()·열거() 를 **그 자리에서** 부른다(verify_all 속성 잠금
정적 검사가 이 파일도 훑는다 — check_attr_injection 의 공용 모듈 목록).
"""
from __future__ import annotations

import html
import json
import os
import sys

_여기 = os.path.dirname(os.path.abspath(__file__))
# 자기완결 — tomd·편집기 굽기(workspace/render_editor_any.py, 자료뿌리.모듈 로 부른다)처럼 build/ 가
# sys.path 에 없는 자리에서도 형제 모듈을 찾는다(tomd.py 머리와 같은 패턴)
if _여기 not in sys.path:
    sys.path.insert(0, _여기)
import 속성값  # noqa: E402
import 수치꼴  # noqa: E402

# 사람 말 → CSS 반. 값 집합의 정본은 이 사상 하나다(편집기·tomd 도 여기서 센다).
열정렬값 = ("왼", "가운데", "오른")
_정렬반 = {"왼": "l", "가운데": "", "오른": "r"}
머리값 = ("파랑", "회색", "없음")
강조색값 = ("강조", "회색")
크기값 = ("작게", "보통", "크게")         # 도식 크기(build/svgfig.py 크기들)와 같은 세 낱말
_최대병합 = 64          # 카탈로그._변환가능한가 병합 갈래(1~64)와 같은 상한

_스타일캐시: list | None = None


def 스타일들():
    """모양 프리셋 후보 — 온톨로지 data_elements.표.디자인.스타일_프리셋 의 id 들(손목록 금지)."""
    global _스타일캐시
    if _스타일캐시 is None:
        try:
            o = json.load(open(os.path.join(os.path.dirname(_여기), "ontology", "ontology.json"),
                               encoding="utf-8"))
            ps = ((((o.get("data_elements") or {}).get("표") or {}).get("디자인") or {})
                  .get("스타일_프리셋") or [])
            _스타일캐시 = [p["id"] for p in ps if isinstance(p, dict) and isinstance(p.get("id"), str)]
        except (OSError, ValueError):
            _스타일캐시 = []
        if not _스타일캐시:
            # 온톨로지 파일이 빠진 설치(0.3.x 배포본)에서는 — 동봉되는 편집기 프로파일의
            # 1p 표.스타일(HEAD assemble.py 가 세던 자리, r18 A 가 두 목록이 같은지 대조)로 물러선다.
            try:
                pr = json.load(open(os.path.join(os.path.dirname(_여기), "ontology", "editor-profiles.json"),
                                    encoding="utf-8"))
                ss = (((((pr.get("장르") or {}).get("onepage-report") or {}).get("개체") or {})
                       .get("표") or {}).get("스타일") or [])
                _스타일캐시 = [x for x in ss if isinstance(x, str)]
            except (OSError, ValueError, AttributeError):
                _스타일캐시 = []
    return tuple(_스타일캐시)


def _글(x):
    return "" if x is None else str(x)


def _정수(v, 최소, 최대):
    if isinstance(v, bool):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if isinstance(v, float) and v != n:
        return None
    return n if 최소 <= n <= 최대 else None


def 정규화(tb, *, 통계=False, 첫열기본=True):
    """표 스펙 → 렌더할 모양 한 벌. 모르는 값은 버리고 stderr 에 알린다(속성값._거부 와 같은 길).

    낸다: {"머리": [..], "몸": [[..]], "n열", "칸": {(r,c): {"가로","세로"}}, "덮임": set,
           "열폭": [..]|None, "열정렬": [..]|None, "정렬": [반..], "강조": {(r,c): 색},
           "첫열": bool, "머리모양": str|None, "style": str}
    """
    tb = tb if isinstance(tb, dict) else {}
    hdr = tb.get("header")
    hdr = hdr if isinstance(hdr, list) else ([] if hdr is None else [hdr])
    몸 = []
    for row in (tb.get("rows") or []):
        cells = row if isinstance(row, list) else (list(row.values()) if isinstance(row, dict) else [row])
        몸.append([_글(c) for c in cells])
    머리 = [_글(h) for h in hdr]
    n열 = max([len(머리)] + [len(r) for r in 몸] + [0])
    # 직사각으로 편다 — 모자란 칸은 빈칸(편집기 tableOf 도 덮인 칸을 "" 로 되살린다)
    if 머리:
        머리 += [""] * (n열 - len(머리))
    몸 = [r + [""] * (n열 - len(r)) for r in 몸]
    n행 = (1 if 머리 else 0) + len(몸)
    격자 = ([머리] if 머리 else []) + 몸

    # ── 병합: 겹치거나 머리·몸을 가로지르면 버린다 ──
    칸 = {}
    덮임 = set()
    병합 = tb.get("병합")
    if 병합 is not None and not isinstance(병합, list):
        속성값._거부("표.병합", 병합, "목록([{행,열,가로,세로}])이어야 합니다")
        병합 = []
    for m in 병합 or []:
        if not isinstance(m, dict):
            속성값._거부("표.병합", m, "{행,열,가로,세로} 꼴이어야 합니다")
            continue
        r = _정수(m.get("행"), 0, max(n행 - 1, 0))
        c = _정수(m.get("열"), 0, max(n열 - 1, 0))
        가 = _정수(m.get("가로", 1), 1, _최대병합)
        세 = _정수(m.get("세로", 1), 1, _최대병합)
        if None in (r, c, 가, 세) or not 격자:
            속성값._거부("표.병합", m, "행·열·가로·세로가 표 안의 정수가 아닙니다")
            continue
        가, 세 = min(가, n열 - c), min(세, n행 - r)
        if 가 == 1 and 세 == 1:
            continue
        if 머리 and r == 0 and 세 > 1:
            속성값._거부("표.병합", m, "머리 행은 아래(몸)로 합칠 수 없습니다")
            continue
        자리들 = {(r + i, c + j) for i in range(세) for j in range(가)}
        if any(p in 덮임 or p in 칸 for p in 자리들):
            속성값._거부("표.병합", m, "다른 병합과 겹칩니다")
            continue
        칸[(r, c)] = {"가로": 가, "세로": 세}
        덮임 |= 자리들 - {(r, c)}
    for (r, c) in 덮임:                      # 덮인 칸의 글은 버린다(design 5-1)
        격자[r][c] = ""

    # ── 열폭 ──
    열폭 = tb.get("열폭")
    열폭원 = None
    if 열폭 is not None:
        수들 = [속성값.수(x, "표.열폭", 최소=0.5, 최대=100) for x in 열폭] if isinstance(열폭, list) else None
        if not 수들 or len(수들) != n열 or any(x is None for x in 수들):
            속성값._거부("표.열폭", 열폭, f"열 {n열}개에 맞는 % 목록이어야 합니다")
            열폭 = None
        else:
            # 원값(편집기가 되읽는 data-w — 저장이 값을 바꾸지 않게)과 화면 폭(합 100 으로 맞춘 %)을 따로 든다
            열폭원 = 수들
            합 = sum(float(x) for x in 수들)
            열폭 = [round(float(x) * 100 / 합, 2) for x in 수들]

    # ── 열정렬(사람이 정한 것) + 자동 ──
    열정렬 = tb.get("열정렬")
    if 열정렬 is not None:
        if (not isinstance(열정렬, list) or len(열정렬) != n열
                or any(x not in 열정렬값 and x not in ("", None) for x in 열정렬)):
            속성값._거부("표.열정렬", 열정렬, f"열 {n열}개에 맞는 왼·가운데·오른 목록이어야 합니다")
            열정렬 = None
        else:
            열정렬 = [x or "" for x in 열정렬]
    통계형 = bool(통계) or n열 >= 6
    우측 = 수치꼴.표_열_우측정렬(몸, n열) if 통계형 else [False] * n열
    정렬 = []
    for j in range(n열):
        if 열정렬 and 열정렬[j]:
            정렬.append(_정렬반[열정렬[j]])
            continue
        값들 = [몸[i][j] for i in range(len(몸)) if ((i + (1 if 머리 else 0)), j) not in 덮임]
        글들 = [v.strip() for v in 값들 if v.strip()]
        길다 = bool(글들) and (sum(len(v) for v in 글들) / len(글들) >= 12 or any("\n" in v for v in 글들))
        정렬.append("r" if 우측[j] else ("l" if 길다 else ""))

    # ── 첫 열 칠 ── 한 열 표·첫 열이 숫자뿐인 표는 켜지 않는다(행 머리가 아니다)
    첫열 = tb.get("첫열")
    if 첫열 is not None and not isinstance(첫열, bool):
        속성값._거부("표.첫열", 첫열, "참·거짓이어야 합니다")
        첫열 = None
    if 첫열 is None:
        첫칸 = [r[0].strip() for r in 몸 if r and r[0].strip()]
        첫열 = (bool(첫열기본) and n열 >= 2 and bool(첫칸)
                and not all(수치꼴.순수수치인가(v) for v in 첫칸))

    # ── 강조 ──
    강조 = {}
    몸시작 = 1 if 머리 else 0
    받음 = tb.get("강조")
    if 받음 is not None and not isinstance(받음, list):
        속성값._거부("표.강조", 받음, "목록([{행,열,색}])이어야 합니다")
        받음 = []
    for h in 받음 or []:
        if not isinstance(h, dict):
            속성값._거부("표.강조", h, "{행,열,색} 꼴이어야 합니다")
            continue
        색 = 속성값.열거(h.get("색") or "강조", 강조색값, "표.강조.색", 기본=None)
        r = _정수(h.get("행"), 몸시작, n행 - 1) if h.get("행") is not None else None
        c = _정수(h.get("열"), 0, n열 - 1) if h.get("열") is not None else None
        if 색 is None or (h.get("행") is not None and r is None) or (h.get("열") is not None and c is None) \
                or (r is None and c is None):
            속성값._거부("표.강조", h, "몸 칸의 행·열(하나 이상)과 강조·회색 중 하나여야 합니다")
            continue
        for rr in ([r] if r is not None else range(몸시작, n행)):
            for cc in ([c] if c is not None else range(n열)):
                if (rr, cc) not in 덮임:
                    강조[(rr, cc)] = 색

    return {"머리": 격자[0] if 머리 else [], "몸": 격자[몸시작:], "n열": n열, "n행": n행,
            "칸": 칸, "덮임": 덮임, "열폭": 열폭, "열폭원": 열폭원, "열정렬": 열정렬, "정렬": 정렬, "강조": 강조,
            "첫열": 첫열,
            "크기": 속성값.열거(tb.get("크기"), 크기값, "표.크기", 기본="보통"),
            "머리모양": 속성값.열거(tb.get("머리"), 머리값, "표.머리", 기본=None),
            "style": 속성값.열거(tb.get("style"), 스타일들(), "표.style", 기본="")}


def _칸글(v):
    """칸 글 — 줄바꿈은 <br> 로(칸 안 줄바꿈: 편집기 tableOf 가 <br> 을 \\n 으로 되읽는다)."""
    return "<br>".join(html.escape(x) for x in v.split("\n"))


def 표html(tb, 반, *, 통계=False, 첫열기본=True, 샌드위치속성=True):
    """스펙 → `<table class="반" …>…</table>`. 반은 부르는 조립기의 표 클래스(코드 상수)다.

    `샌드위치속성=False` 면 style 이 '샌드위치'일 때 data-style 을 안 남긴다(1p — 샌드위치가
    report.css 기본이라 속성을 안 남겨 왔다. 표본 산출물을 그대로 두려고 지킨다).
    """
    n = 정규화(tb, 통계=통계, 첫열기본=첫열기본)
    style = n["style"]
    if style == "샌드위치" and not 샌드위치속성:
        style = ""
    속 = f' data-style="{속성값.열거(style, 스타일들(), "표.style", 기본="")}"' if style else ""
    if n["머리모양"]:
        속 += f' data-머리="{속성값.열거(n["머리모양"], 머리값, "표.머리", 기본="")}"'
    if n["크기"] != "보통":                 # 보통은 속성을 안 남긴다(추적 표본 산출물 그대로)
        속 += f' data-크기="{속성값.열거(n["크기"], 크기값, "표.크기", 기본="보통")}"'
    if n["열폭"]:
        속 += ' style="table-layout:fixed"'
    out = [f'<table class="{html.escape(반)}"{속}>']
    if n["열폭"] or n["열정렬"]:
        # 사람이 정한 열폭·열정렬만 <col data-*> 로 싣는다 — 편집기가 되읽어 저장하고, 열을
        # 넣고 빼면 이 칸도 같이 넣고 뺀다(자동 정렬은 싣지 않는다: 저장이 기본값을 굳히지 않게)
        cols = []
        for j in range(n["n열"]):
            w = n["열폭"][j] if n["열폭"] else None
            a = n["열정렬"][j] if n["열정렬"] else ""
            wv = 속성값.수(w, "표.열폭", 최소=0, 최대=100)
            wo = 속성값.수(n["열폭원"][j] if n["열폭원"] else None, "표.열폭", 최소=0, 최대=100)
            cols.append("<col"
                        + (f' data-w="{wo}" style="width:{wv}%"' if wv else "")
                        + (f' data-a="{속성값.열거(a, 열정렬값, "표.열정렬", 기본="")}"' if a else "")
                        + ">")
        out.append("<colgroup>" + "".join(cols) + "</colgroup>")
    격자 = ([n["머리"]] if n["머리"] else []) + n["몸"]
    몸시작 = 1 if n["머리"] else 0
    for r, row in enumerate(격자):
        칸들 = []
        for c, v in enumerate(row):
            if (r, c) in n["덮임"]:
                continue
            머리칸 = r < 몸시작
            반들 = []
            if not 머리칸:
                if n["정렬"][c]:
                    반들.append(n["정렬"][c])
                if c == 0 and n["첫열"]:
                    반들.append("c1")
            속2 = f' class="{" ".join(속성값.열거(x, ("l", "r", "c1"), "표.칸반", 기본="") for x in 반들)}"' \
                if 반들 else ""
            m = n["칸"].get((r, c))
            if m:
                if m["가로"] > 1:
                    속2 += f' colspan="{속성값.수(m["가로"], "표.병합.가로", 최소=1, 최대=_최대병합)}"'
                if m["세로"] > 1:
                    속2 += f' rowspan="{속성값.수(m["세로"], "표.병합.세로", 최소=1, 최대=_최대병합)}"'
            hl = n["강조"].get((r, c))
            if hl:
                속2 += f' data-강조="{속성값.열거(hl, 강조색값, "표.강조.색", 기본="강조")}"'
            태그 = "th" if 머리칸 else "td"
            칸들.append(f"<{태그}{속2}>{_칸글(v)}</{태그}>")
        out.append("<tr>" + "".join(칸들) + "</tr>")
    out.append("</table>")
    return "".join(out)


def md줄(tb):
    """MD 표 몸 — (머리, 몸 행들, 병합있나). 덮인 칸은 빈칸으로 두고, 칸 안 줄바꿈은 <br>."""
    n = 정규화(tb, 첫열기본=False)
    return n["머리"], n["몸"], bool(n["칸"])
