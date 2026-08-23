#!/usr/bin/env python3
"""전이 카탈로그 생성기 — HTML→HWPX 를 건너야 하는 **시각 변수를 전수로 센다.**

    build/.hwpxenv/bin/python build/카탈로그.py        → build/전이카탈로그.json

왜 만드나 (구현계획 §2-0 진단) — 지금까지 네 번 갈아엎고 함정을 열넷 밟은 까닭은
**변수 공간을 모른 채 결과만 보고 고쳤기** 때문이다. HWPX 를 만들어 보고, 다른 데를
찾고, 그 하나를 고쳤다. 언제 끝나는지 알 수가 없었다.

그런데 변수 공간은 사실 유한하다. HTML 은 남이 만든 게 아니라 **우리 조립기 5개 +
우리 CSS 6벌**이 만든다. 그러니 "임의 CSS 를 다루는 문제" 가 아니라 "정확히 N 개의
알려진 속성을 각각 한 번씩 검증하는 문제" 로 바꿀 수 있다. 이 파일은 그 N 을 센다.

**손으로 적지 않는다**(규칙 2). 두 갈래로 모은다:
  · 정적 — CSS 6벌을 파싱해 선언된 값 전부(pt·색·mm·em·%·굵기·줄간격·자간)를 긁는다.
           @media(print/screen)·[data-*] 문맥을 값마다 같이 적는다. 같은 속성이라도
           인쇄에서 값이 달라지는 자리가 있다(report.css 의 sheet padding 이 그렇다).
  · 동적 — build/samples/*.html 38건을 `화면읽기.읽기()` 로 돌려 **실제 등장한**
           (요소종류 × 서식필드 × 값) 튜플을 모은다. 선언은 있으나 아무 문서도
           안 쓰는 값과, 선언에 없는데 화면에 나타나는 값(자간사냥·조판기 산출)을
           가른다.

**카탈로그의 단위는 "값" 이 아니라 "속성 × 전이규칙" 이다**(구현계획 §2-1).
서식 자유 입력이 정본(JSON)까지 닿는 통로는 정확히 7곳뿐이고(부록 §4), 그 7곳은
값을 제한할 것이 아니라 **변환식을 한 번 검증하면 닫힌다.** 그래서 연속값은 값을
나열하지 않고 `연속변수` 에 범위 + 변환식 이름으로 싣는다. 제품의 자유는 안 줄인다.

**검증상태는 전부 "미검증" 으로 낸다.** 검증을 부여하는 것은 WP-H2 의 몫이다.
여기서 미리 "검증됨" 을 적으면 재 보지도 않고 초록이 되는 그 함정이다(규칙 1).

**결정성** — 같은 입력이면 바이트가 같아야 한다. 시각·난수를 안 쓰고, 열쇠를 정렬하고,
목록을 정렬한다. 이게 깨지면 git diff 가 통째로 소음이 되어 아무도 안 읽는다.
화면 실측값의 mm 은 소수 첫째 자리로 접는다 — 크롬의 서브픽셀 계산이 0.01mm 자리에서
흔들리면 두 번 돌린 결과가 달라지고, 그 순간 이 파일은 diff 로 못 읽는 물건이 된다.
"""
from __future__ import annotations

import argparse
import bisect
import glob
import hashlib
import json
import re
import sys
import time
from pathlib import Path

여기 = Path(__file__).resolve().parent
ROOT = 여기.parent
sys.path.insert(0, str(여기))
import 자료뿌리                 # 산출물·등록부는 자료라 뿌리를 탄다(WP-S2 ①)


# ── 사상표: CSS 속성 → 우리가 화면에서 읽는 서식 이름 ────────────────────────
# 이것은 "목록" 이 아니라 **규칙**이다(역할.py 의 정렬표와 같은 갈래). 표에 없는 속성도
# 카탈로그에서 빠지지 않는다 — 서식필드 없이 그대로 실리고 `진단.규칙없는속성` 에 이름이
# 오른다. 조용히 버리면 그 속성은 영원히 미지로 남는다(규칙 3).
_속성사상 = {
    "font-size": "pt", "font-weight": "굵기", "font-family": "글꼴",
    "font-style": "기울임", "line-height": "줄간격", "letter-spacing": "자간em",
    "text-align": "정렬", "text-indent": "내어mm",
    "color": "글자색", "background": "바탕색", "background-color": "바탕색",
    "text-decoration": "밑줄취소선", "text-decoration-line": "밑줄취소선",
    "word-break": "어절분리", "content": "마커글자", "font": "글꼴", "src": "글꼴",
    "visibility": "빈자리mm", "size": "쪽크기",
    "page-break-after": "쪽나눔", "page-break-before": "쪽나눔",
    "break-after": "쪽나눔", "break-before": "쪽나눔", "break-inside": "쪽나눔",
    # @counter-style 과 CSS counter 는 **마커 글자를 만드는 기계**다. 화면읽기는 그것이
    # 접힌 최종 글자만 보므로(::before content) 전이는 마커글자 규칙 하나로 닫힌다.
    "counter-increment": "마커글자", "counter-reset": "마커글자",
    "system": "마커글자", "symbols": "마커글자", "suffix": "마커글자",
    "margin": "여백mm", "margin-top": "여백mm", "margin-bottom": "여백mm",
    "margin-left": "왼여백mm", "margin-right": "여백mm",
    "padding": "안여백mm", "padding-top": "안여백mm", "padding-bottom": "안여백mm",
    "padding-left": "안들여mm", "padding-right": "안여백mm",
    "width": "폭mm", "min-width": "폭mm", "max-width": "폭mm",
    "height": "높이mm", "min-height": "높이mm",
}
# 테두리 계열은 접두사로 잡는다 — border-top-width·border-bottom-color 처럼 갈래가 많다
_테두리앞 = "border"


def _서식필드(속성: str, 값: str) -> str | None:
    """CSS 속성 하나가 어떤 서식필드로 건너가는가."""
    if 속성.startswith("--"):
        # 사용자 정의 속성(토큰)은 이름이 아니라 **값의 생김새**로 갈린다.
        # `--doc-h-l1-size: 16pt` 은 pt 이고 `--doc-p-navy: #1C3D62` 는 색이다.
        # (값이 var() 로 한 번 더 가려진 자리는 부르는 쪽이 미리 풀어서 넘긴다)
        갈래 = _값갈래(값)
        for k in ("pt", "색", "mm"):
            if k in 갈래:
                return k
        if _글꼴같나(값):
            return "글꼴"
        if 값.startswith('"') or 값.startswith("'"):
            return "마커글자"          # --doc-mk2: "◦" — 마커 이형 스위치
        # 맨숫자 토큰은 값만 봐서는 갈리지 않는다. **이름까지 맞을 때만** 줄간격으로 본다 —
        # 실측(2026-08-07): 6벌의 맨숫자 토큰 다섯이 전부 줄간격이고 이름도 전부 lh 계열이다.
        # 이름이 안 맞는 맨숫자 토큰이 새로 생기면 규칙 없는 속성으로 남아 눈에 띈다.
        if "숫자" in 갈래 and re.search(r"(^|-)(lh|lhs|line-height)$", 속성):
            return "줄간격"
        return None
    if 속성.startswith(_테두리앞):
        # 접두사가 삼키면 안 되는 것들 — radius(모서리)·collapse·spacing 은 선이
        # 아니라 배치 성질이라 '전이됨(테두리)'로 오르면 거짓 장부다(2026-08-13
        # CSS 전수 갭 발견 — 화면읽기는 모서리 반경을 안 읽는다). None 으로 돌려
        # '화면 배치 전용' 규칙으로 닫는다.
        if 속성 in ("border-radius", "border-collapse", "border-spacing"):
            return None
        return "테두리"
    return _속성사상.get(속성)


# ── 전이규칙 — 속성이 HWPX 로 건너가는 길 ────────────────────────────────────
# 이름·식은 규칙이라 여기 적지만, **근거(파일:행)는 손으로 안 적는다.** 앵커 문자열을
# 실제 소스에서 찾아 줄 번호를 붙인다. 코드가 움직이면 다시 돌릴 때 번호도 따라오고,
# 앵커가 사라지면 `진단.앵커없음` 에 올라 규칙이 낡았음을 말한다.
_전이규칙표 = {
    "pt":       ("pt→charPr height", "ensure_run(size=pt) — charPr height = pt×100",
                 ['size=서식.get("pt")', '"pt": 집("pt")']),
    "굵기":     ("굵기→bold 두 갈래", "굵기 ≥ 600 이면 bold=1, 아니면 400 (400/700 로 접는다)",
                 ['>= 600', 'bold=bool(서식.get("굵게"))']),
    "글꼴":     ("글꼴이름→fontfaces+substFont",
                 "스택 첫 이름을 fontfaces 에 추가하고 substFont(명조계→함초롬바탕/그 외→함초롬돋움)",
                 ['font=_글꼴(서식.get("글꼴"))', 'def _글꼴']),
    "기울임":   ("기울임→italic", "ensure_run(italic=…)", ['italic=bool(서식.get("기울임"))']),
    "밑줄취소선": ("밑줄·취소선→underline/strike", "ensure_run(underline=…, strike=…)",
                 ['underline=bool(서식.get("밑줄"))', 'strike=bool(서식.get("취소선"))']),
    "글자색":   ("hex→charPr color", "ensure_run(color=#RRGGBB), 값 없으면 #000000",
                 ['color=_색(서식.get("색"))']),
    "형광":     ("조각 바탕→highlight", "조각의 backgroundColor 를 charPr highlight 로",
                 ['인자["highlight"]']),
    "자간em":   ("em→letter_spacing %", "round(em×100) 을 -50~100 으로 클램프, 0 도 명시 전달",
                 ['인자["letter_spacing"]']),
    "줄간격":   ("%→lineSpacing PERCENT + FIXED mm",
                 "apply_paragraph_format(line_spacing_percent) 뒤 pt×줄간격/100 mm 를 FIXED HWPUNIT 로 못 박음",
                 ['line_spacing_percent=int', 'ls.set("type", "FIXED")']),
    "정렬":     ("CSS 정렬→HWPX alignment",
                 "center→CENTER · right→RIGHT · justify→JUSTIFY · start/left→LEFT",
                 ['alignment=_정렬표.get', '_정렬표 = {']),
    "왼여백mm": ("mm→indent_left_mm", "왼여백mm + 안들여mm (마커가 글머리표로 가면 안들여 제외)",
                 ['indent_left_mm=round', 'if 마커있나:']),
    "안들여mm": ("padding-left→왼여백 합산/셀 안여백",
                 "문단은 왼여백에 더하고, 표 칸은 cellMargin 좌우로 간다",
                 ['indent_left_mm=round', 'cellMargin']),
    "패딩mm":   ("padding-top/bottom→문단 테두리 offset",
                 "배경 박스의 세로 안쪽 여백 → border offsetTop/Bottom(HU) — "
                 "박스 키가 화면과 같아진다(2026-08-14 육안 실측 수리)",
                 ['위안들여mm', 'offsetTop']),
    "내어mm":   ("text-indent→first_line_indent_mm", "음수 그대로(내어쓰기)",
                 ['first_line_indent_mm=round']),
    "여백mm":   ("mm→spacing_before/after_pt", "mm×72/25.4 pt · 이웃 문단은 CSS 처럼 max 로 겹침",
                 ['spacing_before_pt=round', 'spacing_after_pt=round', 'def _여백겹치기']),
    "안여백mm": ("padding→셀 cellMargin", "표 칸만 옮긴다 — 문단의 세로 padding 은 화면읽기가 안 읽는다",
                 ['cellMargin', 'hasMargin']),
    "바탕색":   ("hex→borderFill fillColor",
                 "ensure_border_fill(fill_color) · 바탕 없으면 민바탕을 명시(상속 오염 방지)",
                 ['fill_color=바탕', 'def _민바탕']),
    "테두리":   ("border→borderFill",
                 "표 칸은 변별 그대로(_변별괘선, 16단계 스냅·선종류 사상) · "
                 "문단 배경 테두리는 첫 변을 4변에 적용",
                 ['border_width=굵기', 'active_borders=', 'def _변별괘선']),
    "어절분리": ("word-break→breakNonLatinWord", "keep-all→KEEP_WORD · 그 외→BREAK_WORD",
                 ['breakNonLatinWord', 'def _어절분리']),
    "마커글자": ("::before content→글머리표 / 실글자→run",
                 "만든것이면 set_list_format(bullet), 실글자면 run 앞에 글자로 삽입",
                 ['set_list_format', '"마커가_글자냐"']),
    "폭mm":     ("mm→표·그림 절대폭", "표는 width=mm×HU(비율 오인 방지) · 그림은 add_picture 의 mm",
                 ['width=round(폭 * HU)', 'add_picture']),
    "높이mm":   ("mm→행 높이·그림 높이·띠 근사",
                 "표 행 높이는 mm×HU · 띠는 빈 문단 글자 크기(높이mm×2.8pt)로 근사",
                 ['add_picture', 'def 띠']),
    "쪽여백mm": ("mm→set_page_margins(HU)", "round(mm×HU) · 머리말·꼬리말은 0",
                 ['set_page_margins']),
    "글자폭":   ("useFontSpace=1", "글꼴 고유 폭을 쓴다 — 안 켜면 정사각 격자라 9~12% 벌어진다",
                 ['useFontSpace']),
    # 토큰·값묶음처럼 "무엇에 쓰이는지" 는 쓰는 쪽 속성이 들고 있고 **변환만 공통인** 것들
    "색":       ("hex→charPr color / borderFill fillColor",
                 "#RRGGBB 그대로 — 글자면 charPr color, 바탕이면 fillColor",
                 ['color=_색(서식.get("색"))', 'fill_color=바탕']),
    "mm":       ("mm→HWPUNIT", "round(mm × 283.465) — 여백·폭·높이가 다 이 한 식을 쓴다",
                 ['HU = ', 'set_page_margins']),
    "쪽크기":   ("A4→라이브러리 기본 유지",
                 "쪽 크기는 안 건드린다 — mm 로 넣었다가 0.7mm 쪽이 되어 446쪽이 나온 적이 있다",
                 ['쪽 크기는 건드리지 않는다']),
    "쪽나눔":   ("쪽 경계→page_break_before",
                 "화면의 쪽 번호가 바뀌면 쪽나눔 명령 → page_break_before=True",
                 ['"종류": "쪽나눔"', 'page_break_before']),
    "빈자리mm": ("visibility:hidden→전각공백 폭",
                 "유령 라벨은 글자를 버리고 자리(mm)만 남겨 전각공백 개수로 환산",
                 ['빈자리mm', '유령 라벨(visibility:hidden)']),
    "머리칸":   ("TH→머리칸", "th 여부를 그대로 실어 음영·굵게가 따라간다",
                 ['"머리칸": bool(c.get("머리칸"))', '머리칸']),
    "병합":     ("colSpan/rowSpan→merge_cells",
                 "글을 다 넣은 **뒤에** merge_cells 를 부른다(먼저 부르면 글이 사라진다)",
                 ['merge_cells', '"가로병합"']),
    "줄바꿈":   ("<br>→run 개행", "빈 글자로 지우면 줄이 붙는다 — 개행 run 으로 넣는다",
                 ['if x.get("줄바꿈")', '조각.push({ 줄바꿈: true })']),
    "그림":     ("SVG·img→PNG 캡처→add_picture",
                 "글로 못 옮기니 그 네모만 배율 3 으로 찍어 mm 크기로 넣는다",
                 ['add_picture', 'def _찍기']),
    "역할":     ("data-ent→옮김이 등록부",
                 "역할 이름으로 옮김이를 고른다. 없는 이름도 문단으로 내보내고 고발한다",
                 ['def 찾기', '미지정.append']),
    "종류":     ("마디 종류→옮김이 선택",
                 "**종류가 먼저다** — 역할로 먼저 고르면 표 안 문단이 표 옮김이로 가서 터진다",
                 ['if 종류 == "표":']),
}

# 서식이 아니라 **카탈로그의 축**인 것들 — 값은 세되 HWPX 로 옮기는 물건이 아니다.
_자리표 = {"반", "지면반"}

# 부록 §3.2 가 실측으로 확인한 **떨어뜨리는 자리.** 카탈로그가 이것을 들고 있어야
# H2 가 "옮겼다고 착각한 것" 과 "알고 못 옮기는 것" 을 가를 수 있다.
_떨어뜨림 = {
    "칸·기울임": "표 칸서식이 pt·굵게·색·글꼴만 실어 간다",
    "칸·밑줄": "표 칸서식이 pt·굵게·색·글꼴만 실어 간다",
    "칸·취소선": "표 칸서식이 pt·굵게·색·글꼴만 실어 간다",
    # '칸·테두리'는 2026-08-13 에 걷혔다 — _hwpx_write._변별괘선() 이 실측 테두리를
    # 변별 borderFill 로 전이한다(16단계 스냅). 가로줄칸 테두리는 여전히 안 싣는다
    # (역할.py 가 격자 칸에 테두리:None 을 명시 — 괘선없음 격자가 정본).
    "가로줄칸·테두리": "격자(grid) 칸은 배치 수단이라 역할.py 가 테두리를 의도적으로 안 싣는다",
    "칸·왼여백mm": "셀의 x 자리는 열 폭 누적으로만 정해진다 — OWPML Tc 에 오프셋 필드가 없다"
                 "(2026-08-13 명세 확인: cellAddr 는 col/row 주소뿐). 값은 폭mm 전이의 파생물이다",
    "가로줄칸·왼여백mm": "칸·왼여백mm 와 같다 — 격자 칸의 자리는 앞 칸들의 폭이 정한다",
    "그림·정렬": "명령에는 실려 오나 그림() 이 안 쓴다",
    "문단·자간em": "문단 수준 자간은 자리잡기가 안 쓴다 — 다만 소실이 아니라 **run 경유 "
                 "보존**이다(글자서식 집() 폴백이 문단 자간을 조각에 상속, 2026-08-13 확인)",
    # '조각·글꼴'은 2026-08-14 에 걷혔다 — 속읽기가 조각 글꼴을 읽고 글자서식이
    # 조각 우선으로 상속한다(gov 강조 고딕이 명조로 나가던 갭 종결).
}

# 내용에 따라 값이 이어지는 자리 — 값을 나열하면 목록이 쓰레기통이 된다.
# 부록 §4 가 "표 열 폭(내용 따라)·이미지 크기" 라고 지목한 그 자리다.
_연속필드 = {"폭mm", "높이mm", "빈자리mm"}

# 메타 이름표(data-path·data-num 따위)는 값이 문서 내용에서 온다. 이 수를 넘으면
# 나열을 접고 가짓수만 센다 — 목록이 쓰레기통이 되면 아무도 안 읽는다.
_메타나열상한 = 24


# ── CSS 파서 ────────────────────────────────────────────────────────────────
# 우리 CSS 는 우리가 쓴 것이라 형태가 규칙적이다. 다만 @media 안에 @page 가 든 자리가
# 있어(gongmun.css:37, fullreport.css:42) 정규식 한 방으로는 못 뜯는다 — 중괄호 짝을
# 세는 스캐너로 간다. 따옴표 안(content: "□")의 중괄호도 안 센다.
def _주석빼기(글: str) -> str:
    """/* */ 를 지우되 **줄 수는 보존한다** — 줄 번호가 곧 근거라서 어긋나면 못 쓴다."""
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), 글, flags=re.S)


def _짝(글: str, i: int) -> int:
    """글[i] == '{' 의 짝이 되는 '}' 자리."""
    깊이 = 0
    while i < len(글):
        c = 글[i]
        if c in "\"'":
            q, i = c, i + 1
            while i < len(글) and 글[i] != q:
                i += 2 if 글[i] == "\\" else 1
        elif c == "{":
            깊이 += 1
        elif c == "}":
            깊이 -= 1
            if 깊이 == 0:
                return i
        i += 1
    return len(글) - 1


def _선언쪼개기(속: str, 밑자리: int):
    """블록 안을 (자리, 속성, 값) 목록으로. 괄호·따옴표 안의 ; 와 : 는 안 자른다."""
    나온다 = []
    깊이, 시작, i = 0, 0, 0
    while i <= len(속):
        c = 속[i] if i < len(속) else ";"
        if c in "\"'":
            q, i = c, i + 1
            while i < len(속) and 속[i] != q:
                i += 2 if 속[i] == "\\" else 1
        elif c == "(":
            깊이 += 1
        elif c == ")":
            깊이 -= 1
        elif c == ";" and 깊이 == 0:
            한줄 = 속[시작:i]
            자리 = 밑자리 + 시작 + (len(한줄) - len(한줄.lstrip()))
            한줄 = 한줄.strip()
            if 한줄:
                쪼갬 = _콜론자리(한줄)
                if 쪼갬 is not None:
                    나온다.append((자리, 한줄[:쪼갬].strip().lower(), 한줄[쪼갬 + 1:].strip()))
            시작 = i + 1
        i += 1
    return 나온다


def _콜론자리(한줄: str) -> int | None:
    깊이, i = 0, 0
    while i < len(한줄):
        c = 한줄[i]
        if c in "\"'":
            q, i = c, i + 1
            while i < len(한줄) and 한줄[i] != q:
                i += 2 if 한줄[i] == "\\" else 1
        elif c == "(":
            깊이 += 1
        elif c == ")":
            깊이 -= 1
        elif c == ":" and 깊이 == 0:
            return i
        i += 1
    return None


def _줄매기기(글: str):
    """글자 자리 → 줄 번호."""
    끝들 = [i for i, c in enumerate(글) if c == "\n"]
    return lambda 자리: bisect.bisect_left(끝들, 자리) + 1


def css읽기(경로: Path):
    """CSS 한 벌 → [(줄, 매체, 셀렉터, 속성, 값)] 전부."""
    원본 = 경로.read_text(encoding="utf-8")
    글 = _주석빼기(원본)
    줄번호 = _줄매기기(글)
    결과 = []

    def 블록(처음: int, 끝: int, 문맥: tuple):
        머리, i = 처음, 처음
        while i < 끝:
            c = 글[i]
            if c in "\"'":
                q, i = c, i + 1
                while i < 끝 and 글[i] != q:
                    i += 2 if 글[i] == "\\" else 1
                i += 1
                continue
            if c == "{":
                셀렉터 = " ".join(글[머리:i].split())
                짝자리 = _짝(글, i)
                if 셀렉터.startswith("@media") or 셀렉터.startswith("@supports"):
                    블록(i + 1, 짝자리, 문맥 + (셀렉터,))
                else:
                    for 자리, 속성, 값 in _선언쪼개기(글[i + 1:짝자리], i + 1):
                        결과.append((줄번호(자리), _매체(문맥), 셀렉터, 속성,
                                    " ".join(값.split())))
                i = 짝자리 + 1
                머리 = i
                continue
            if c in ";}":
                i += 1
                머리 = i
                continue
            i += 1

    블록(0, len(글), ())
    return 결과


def _매체(문맥: tuple) -> str:
    """@media 문맥을 한 낱말로. 문맥이 없으면 'all' 이다."""
    if not 문맥:
        return "all"
    return "+".join(x.replace("@media", "").strip() for x in 문맥)


# ── 값 갈래 나누기 ──────────────────────────────────────────────────────────
_pt = re.compile(r"(-?\d+(?:\.\d+)?)pt\b")
_mm = re.compile(r"(-?\d+(?:\.\d+)?)mm\b")
_em = re.compile(r"(-?\d+(?:\.\d+)?)em\b")
_퍼센트 = re.compile(r"(-?\d+(?:\.\d+)?)%")
_hex = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
_맨숫자 = re.compile(r"^-?\d+(?:\.\d+)?$")


def _값갈래(값: str) -> set:
    갈래 = set()
    if _pt.search(값):
        갈래.add("pt")
    if _mm.search(값):
        갈래.add("mm")
    if _em.search(값):
        갈래.add("em")
    if _퍼센트.search(값):
        갈래.add("%")
    if _hex.search(값):
        갈래.add("색")
    if _맨숫자.match(값.strip()):
        갈래.add("숫자")
    return 갈래


def _글꼴같나(값: str) -> bool:
    """글꼴 스택인가 — 총칭 이름이 있거나 따옴표 낱말이 쉼표로 이어지면 스택이다."""
    저 = 값.lower()
    return ("sans-serif" in 저 or "serif" in 저 or "monospace" in 저
            or ("," in 값 and ('"' in 값 or "'" in 값)))


_var = re.compile(r"var\(\s*(--[A-Za-z0-9-]+)\s*(?:,([^()]*))?\)")


def _var풀기(값: str, 토큰: dict, 깊이: int = 0) -> str:
    """`var(--x)` 를 한 겹씩 푼다 — **분류에만 쓴다.** 기록되는 값은 선언 원문 그대로다.

    왜 — `--doc-page-mt: var(--doc-margin-top)` 처럼 값이 한 번 더 가려진 자리가 있다.
    안 풀면 "이 속성은 무슨 서식인지 모른다" 가 되어, 정작 화면읽기가 쪽 여백을 읽는
    바로 그 변수가 규칙 없는 속성으로 떨어진다.
    """
    if 깊이 > 5 or "var(" not in 값:
        return 값
    def 바꿈(m):
        속 = 토큰.get(m.group(1))
        return 속 if 속 is not None else (m.group(2) or "").strip()
    return _var풀기(_var.sub(바꿈, 값), 토큰, 깊이 + 1)


def _값문자열(v) -> str:
    """모든 값을 **문자열 한 꼴**로 접는다.

    왜 — 열쇠를 섞어 두면(숫자·참거짓·없음) 정렬 결과가 파이썬 판마다 달라질 수 있고,
    그러면 결정성이 깨진다. 값의 뜻은 문자열로도 다 산다.
    """
    if v is None:
        return "없음"
    if isinstance(v, bool):
        return "참" if v else "거짓"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(round(v, 4))
    if isinstance(v, int):
        return str(v)
    return str(v)


def _mm접기(v):
    """화면 실측 mm 은 소수 첫째 자리로. 크롬 서브픽셀이 0.01 자리에서 흔들린다."""
    return None if v is None else round(float(v) + 0.0, 1)


# ── 모으개 ──────────────────────────────────────────────────────────────────
class 모으개:
    """(열쇠 → 값 → {횟수·출처·반}) 를 쌓는다. 출력 직전에만 정렬한다."""

    def __init__(self):
        self.통 = {}
        self.토큰 = {}          # `--x: 값` 표 — var() 를 풀어 서식필드를 가르는 데만 쓴다

    def 담기(self, 열쇠: str, 값, 출처: str, 반: str | None = None, 횟수: int = 1):
        칸 = self.통.setdefault(열쇠, {})
        낱 = 칸.setdefault(_값문자열(값), {"횟수": 0, "출처": set(), "반": set()})
        낱["횟수"] += 횟수
        낱["출처"].add(출처)
        if 반:
            낱["반"].add(반)


# ── 정적 수집 ───────────────────────────────────────────────────────────────
def 정적수집(css경로들, 모음: 모으개, 진단: dict):
    """CSS 벌들을 파싱해 (속성 × 값) 과 (값갈래 × 값) 을 함께 담는다.

    두 벌로 담는 이유 — 속성별로만 담으면 `border-bottom: var(--doc-table-border)` 처럼
    값이 변수로 숨은 자리에서 실제 굵기가 안 보이고, 값갈래로만 담으면 어느 속성이
    그 값을 냈는지가 사라진다. 둘 다 있어야 부록 표와 대조할 수 있다.
    """
    # tokens.css 는 장르 CSS 가 var() 로 가리키는 뿌리라 **분류용 표에는 늘 함께 둔다.**
    for p in [여기 / "tokens.css"] + [x for x in css경로들 if x.name != "tokens.css"]:
        for _, _, _, 속성, 값 in css읽기(p):
            if 속성.startswith("--"):
                모음.토큰.setdefault(속성, 값)
    for p in css경로들:
        이름 = p.name
        for 줄, 매체, 셀렉터, 속성, 값 in css읽기(p):
            자리 = f"{이름}:{줄} [{매체}] {셀렉터}"
            모음.담기(f"정적·{속성}", 값, 자리, 셀렉터)
            필드 = _서식필드(속성, _var풀기(값, 모음.토큰))
            if 필드 is None and not 속성.startswith("--"):
                진단.setdefault("화면배치전용속성", set()).add(속성)
            # 값 안에 든 낱값들 — 선언 하나에 여러 개가 들 수 있다(margin: 4mm 0 1.5mm)
            for 표, 갈래 in ((_pt, "pt"), (_mm, "mm"), (_em, "em"), (_퍼센트, "%")):
                for m in 표.finditer(값):
                    모음.담기(f"정적값·{갈래}", m.group(1) + 갈래, 자리, 셀렉터)
            for m in _hex.finditer(값):
                모음.담기("정적값·색", m.group(0).upper(), 자리, 셀렉터)
            if 속성 == "font-weight" or (속성.startswith("--") and "weight" in 속성):
                모음.담기("정적값·굵기", 값, 자리, 셀렉터)
            if 속성 == "line-height" or 속성.endswith("line-height"):
                모음.담기("정적값·줄간격", 값, 자리, 셀렉터)
            if 속성 == "letter-spacing":
                모음.담기("정적값·자간em", 값, 자리, 셀렉터)
            if 속성 == "font-family":
                모음.담기("정적값·글꼴스택", 값, 자리, 셀렉터)
            if 속성 == "src" and "url(" in 값:
                모음.담기("정적값·글꼴파일", 값, 자리, 셀렉터)
            # 셀렉터가 키로 삼는 data-* 스위치 — **스위치 공간은 CSS 가 정의한다**
            for 이름2, 값2 in _스위치뽑기(셀렉터):
                모음.담기(f"스위치·{이름2}", 값2, 자리, 셀렉터)


_스위치 = re.compile(r"\[data-([A-Za-z0-9-]+)(?:\s*[~^|*$]?=\s*[\"']?([^\"'\]]*)[\"']?)?\]")


def _스위치뽑기(셀렉터: str):
    for m in _스위치.finditer(셀렉터):
        yield m.group(1), (m.group(2) if m.group(2) is not None else "(있기만 하면)")


def _스위치값모음(css경로들, 이름: str) -> set:
    """CSS 가 정의한 `[data-이름=값]` 스위치의 값 전부 — **손으로 안 적는다.**

    `글꼴전환표본읽기` 가 "명조·한글원본이 정확히 무엇인가" 를 CSS 선언에서 그대로
    센다. `serif`·`hwp` 를 여기 문자열로 박아 넣으면 그게 곧 새 손목록이라(규칙 2),
    tokens.css 가 `:root[data-fonts="…"]` 로 선언한 값을 스캔해서 얻는다.
    """
    값 = set()
    for p in css경로들:
        for _, _, 셀렉터, _, _ in css읽기(p):
            for n, v in _스위치뽑기(셀렉터):
                if n == 이름 and v != "(있기만 하면)":
                    값.add(v)
    return 값


# ── 동적 수집 ───────────────────────────────────────────────────────────────
_서식이름사상 = {
    "pt": "pt", "굵기": "굵기", "기울임": "기울임", "밑줄": "밑줄취소선",
    "취소선": "밑줄취소선", "색": "글자색", "바탕": "바탕색", "글꼴": "글꼴",
    "줄간격": "줄간격", "정렬": "정렬", "왼여백mm": "왼여백mm", "안들여mm": "안들여mm",
    "위안들여mm": "패딩mm", "아래안들여mm": "패딩mm",
    "내어mm": "내어mm", "자간em": "자간em", "위여백mm": "여백mm", "아래여백mm": "여백mm",
    "어절분리": "어절분리", "높이mm": "높이mm", "폭mm": "폭mm", "테두리굵기mm": "테두리",
    "테두리색": "테두리", "테두리변": "테두리", "테두리선종류": "테두리",
    "마커글자": "마커글자",
    "마커방식": "마커글자", "여백mm": "쪽여백mm", "빈자리mm": "빈자리mm",
    "행높이mm": "높이mm", "머리칸": "머리칸", "가로병합": "병합", "세로병합": "병합",
    "줄바꿈": "줄바꿈", "png있음": "그림", "크기mm": "쪽크기", "지면수": "쪽나눔",
    "종류": "종류", "역할": "역할",
}
_mm필드 = {"왼여백mm", "안들여mm", "내어mm", "위여백mm", "아래여백mm", "높이mm",
          "폭mm", "빈자리mm", "테두리굵기mm", "위안들여mm", "아래안들여mm"}


def _서식담기(모음: 모으개, 종류: str, 서식: dict, 문서: str, 반: str | None):
    for k, v in (서식 or {}).items():
        if k == "테두리":
            for 변, t in zip("상우하좌", v or []):
                if not t:
                    continue
                모음.담기(f"동적·{종류}·테두리변", 변, 문서, 반)
                모음.담기(f"동적·{종류}·테두리굵기mm", _mm접기(t.get("굵기mm")), 문서, 반)
                모음.담기(f"동적·{종류}·테두리색", t.get("색"), 문서, 반)
                모음.담기(f"동적·{종류}·테두리선종류", t.get("선종류") or "solid", 문서, 반)
            continue
        모음.담기(f"동적·{종류}·{k}", _mm접기(v) if k in _mm필드 else v, 문서, 반)


def _조각담기(모음: 모으개, 종류: str, 속: list, 문서: str, 반: str | None):
    for x in 속 or []:
        조각반 = x.get("반") or 반
        for k, v in x.items():
            if k in ("글", "반"):
                continue
            모음.담기(f"동적·{종류}·{k}", _mm접기(v) if k in _mm필드 else v, 문서, 조각반)
        if 조각반:
            모음.담기(f"동적·{종류}·반", 조각반, 문서, None)


def 동적수집(읽은것들: dict, 모음: 모으개):
    """`화면읽기.읽기()` 결과들 → (요소종류 × 서식필드 × 값) 튜플 집합."""
    for 문서 in sorted(읽은것들):
        d = 읽은것들[문서]
        쪽 = d.get("쪽") or {}
        for 변, v in zip("상우하좌", 쪽.get("여백mm") or []):
            모음.담기("동적·쪽·여백mm", _mm접기(v), 문서, 변)
        모음.담기("동적·쪽·크기mm", "×".join(_값문자열(x) for x in 쪽.get("크기mm") or []),
                 문서, None)
        모음.담기("동적·쪽·지면반", 쪽.get("지면반"), 문서, None)
        모음.담기("동적·쪽·지면수", 쪽.get("지면수"), 문서, None)
        for 마디 in d.get("마디") or []:
            종 = 마디.get("종류")
            반 = (마디.get("반") or None)
            모음.담기("동적·마디·종류", 종, 문서, 반)
            if 반:
                모음.담기(f"동적·{종}·반", 반, 문서, None)
            if 마디.get("역할"):
                모음.담기("동적·마디·역할", 마디["역할"], 문서, 반)
            if 종 in ("문단", "장식"):
                _서식담기(모음, 종, 마디.get("서식"), 문서, 반)
                _조각담기(모음, "조각", 마디.get("속"), 문서, 반)
                mk = 마디.get("마커")
                if mk:
                    모음.담기("동적·문단·마커글자", mk.get("글자"), 문서, 반)
                    모음.담기("동적·문단·마커방식",
                             "만든것" if mk.get("만든것") else "실글자", 문서, 반)
            elif 종 == "표":
                t = 마디.get("표") or {}
                모음.담기("동적·표·폭mm", _mm접기(t.get("폭mm")), 문서, 반)
                모음.담기("동적·표·정렬", t.get("정렬"), 문서, 반)
                # 겉선(표 요소 테두리) — 셀 테두리와 별도 축이다(2026-08-13 육안 실측)
                _서식담기(모음, "표", {"테두리": t.get("테두리")}, 문서, 반)
                for r in t.get("행") or []:
                    모음.담기("동적·표·행높이mm", _mm접기(r.get("높이mm")), 문서, 반)
                    for c in r.get("칸") or []:
                        모음.담기("동적·칸·머리칸", bool(c.get("머리칸")), 문서, 반)
                        모음.담기("동적·칸·가로병합", c.get("가로병합"), 문서, 반)
                        모음.담기("동적·칸·세로병합", c.get("세로병합"), 문서, 반)
                        모음.담기("동적·칸·폭mm", _mm접기(c.get("폭mm")), 문서, 반)
                        _서식담기(모음, "칸", c.get("서식"), 문서, 반)
                        _조각담기(모음, "칸조각", c.get("속"), 문서, 반)
            elif 종 == "가로줄":
                _서식담기(모음, "가로줄", 마디.get("서식"), 문서, 반)
                for c in 마디.get("칸") or []:
                    모음.담기("동적·가로줄칸·폭mm", _mm접기(c.get("폭mm")), 문서, 반)
                    _서식담기(모음, "가로줄칸", c.get("서식"), 문서, 반)
                    _조각담기(모음, "가로줄칸조각", c.get("속"), 문서, 반)
            elif 종 == "그림":
                모음.담기("동적·그림·폭mm", _mm접기(마디.get("폭mm")), 문서, 반)
                모음.담기("동적·그림·높이mm", _mm접기(마디.get("높이mm")), 문서, 반)
                모음.담기("동적·그림·png있음", bool(마디.get("png")), 문서, 반)
                _서식담기(모음, "그림", 마디.get("서식"), 문서, 반)


# ── 항목으로 굳히기 ─────────────────────────────────────────────────────────
def _열쇠뜯기(열쇠: str):
    조각 = 열쇠.split("·")
    갈래 = 조각[0]
    if 갈래 == "동적":
        return "동적", 조각[1], "·".join(조각[2:])
    if 갈래 in ("정적", "정적값", "스위치"):
        return 갈래, None, "·".join(조각[1:])
    return 갈래, None, "·".join(조각[1:])


def _근거찾기(앵커들):
    """앵커 문자열이 실제 코드 어디에 있나 — **손으로 안 적는다.**"""
    자리 = []
    for 파일 in ("역할.py", "_hwpx_write.py", "화면읽기.py"):
        본문 = (여기 / 파일).read_text(encoding="utf-8").splitlines()
        for 앵 in 앵커들:
            for n, 줄 in enumerate(본문, 1):
                if 앵 in 줄:
                    자리.append(f"{파일}:{n}")
    return sorted(set(자리))


_근거캐시 = {}


def _전이규칙(필드: str | None, 종류: str | None, 이름: str, 갈래: str):
    """속성 하나가 건너가는 규칙. 없으면 **없다고 말한다**(조용히 넘기지 않는다)."""
    떨 = _떨어뜨림.get(f"{종류}·{이름}") if 종류 else None
    if 이름 in _자리표:
        return {"이름": "자리표", "식": "요소 이름표(class) — 서식이 아니라 카탈로그의 축이다",
                "근거": [], "비고": "HWPX 로 옮기는 물건이 아니다"}
    if 갈래 == "메타":
        return {"이름": "메타 이름표", "근거": [],
                "식": "시각 서식이 아니라 역할·경로·편집 그룹의 이름표다(부록 §1.10). "
                      "시각엔 간접 영향만 준다 — 문단 그룹이 쪼개지지 않게 붙잡는 자리"}
    if 갈래 == "스위치":
        return {"이름": "스위치→변형 좌표", "근거": [],
                "식": "값 자체가 건너가지 않는다 — 이 스위치가 켜지면 CSS 가 다른 서식을 내고, "
                      "화면읽기는 **접힌 최종 서식**만 읽는다. 그러므로 검증 단위는 값이 아니라 조합이다"}
    if 갈래 == "정적값" and 필드 is None:
        return {"이름": "값묶음", "근거": [],
                "식": "선언에 등장한 낱값 전수 — 이 값을 쓰는 속성 항목이 전이규칙을 들고 있다"}
    if 갈래 == "정적" and 필드 is None:
        # **화면읽기가 읽는 서식 필드가 전이의 전부다**(WP-H2 가 닫은 규칙).
        # 2026-08-07 실측: 이 갈래로 떨어지는 속성 30개가 전부 화면 배치 전용이었다
        # (display·flex·position·gap·z-index·overflow·transform·box-shadow …).
        # 화면읽기는 이것들을 아예 안 내보내므로 **옮길 값 자체가 없다** — 미지의
        # 변수가 아니라 정의상 전이 대상 밖이다. 그래서 "미정의"(=이름이 안 붙은 구멍)가
        # 아니라 이름 붙은 규칙으로 닫는다.
        # 한계도 같이 적는다 — 화면읽기가 안 읽는데 **눈에는 보이는** 속성
        # (transform: rotate 같은)이 새로 들어오면 이 규칙은 그것을 조용히 통과시킨다.
        # 그 자리를 잡는 것은 값 대조가 아니라 기하 오라클(WP-H3)의 몫이다.
        return {"이름": "화면 배치 전용", "근거": [],
                "식": "HWPX 로 건너가지 않는다 — 화면읽기가 내보내는 서식 필드가 전이의 "
                      "전부이고, 이 속성은 그 목록에 없다(가드도 같은 기준으로 돈다)",
                "비고": "화면 배치를 만드는 속성이다. 값이 바뀌면 화면읽기가 재는 "
                       "pt·mm·색이 따라 바뀌고, 전이는 그 바뀐 값으로 이뤄진다"}
    if 필드 is None:
        return {"이름": "미정의", "식": None, "근거": [],
                "비고": "화면읽기가 읽는 서식 목록에 없다 — 옮길지 말지 정해진 적이 없다"}
    if 필드 not in _전이규칙표:
        return {"이름": "미정의", "식": None, "근거": [],
                "비고": f"서식필드 {필드} 에 전이규칙이 없다"}
    이름2, 식, 앵커들 = _전이규칙표[필드]
    열쇠 = 필드
    if 열쇠 not in _근거캐시:
        _근거캐시[열쇠] = _근거찾기(앵커들)
    규 = {"이름": 이름2, "식": 식, "근거": _근거캐시[열쇠]}
    if 떨:
        규["떨어뜨림"] = 떨
    return 규


def 항목화(모음: 모으개) -> dict:
    항목 = {}
    for 열쇠 in sorted(모음.통):
        값통 = 모음.통[열쇠]
        갈래, 종류, 이름 = _열쇠뜯기(열쇠)
        필드 = None
        if 갈래 == "동적":
            필드 = _서식이름사상.get(이름)
        elif 갈래 == "정적":
            # 값이 여럿이면 **하나만 보고 정하지 않는다** — `--doc-p-line-thin` 처럼
            # 화면(max(0.12mm,1px))과 인쇄(0.12mm)에서 값 생김새가 갈리는 자리가 있다.
            for v in sorted(값통):
                필드 = _서식필드(이름, _var풀기(v, 모음.토큰))
                if 필드:
                    break
        elif 갈래 == "정적값":
            필드 = {"pt": "pt", "색": "색", "mm": "mm", "굵기": "굵기",
                    "줄간격": "줄간격", "자간em": "자간em",
                    "글꼴스택": "글꼴", "글꼴파일": "글꼴"}.get(이름)
        # 나열하지 않는 두 갈래: ① 내용에 따라 이어지는 서식(표 열 폭·그림 크기)
        #                        ② 문서 내용에서 값이 오는 메타 이름표(data-path 따위)
        메타넘침 = 갈래 == "메타" and len(값통) > _메타나열상한
        연속 = (필드 in _연속필드) or (이름 in _연속필드) or 메타넘침
        항 = {
            "갈래": 갈래,
            "요소종류": 종류,
            "속성": 이름,
            "서식필드": 필드,
            "유한": not 연속,
            "값가짓수": len(값통),
            "등장횟수": sum(v["횟수"] for v in 값통.values()),
            "전이규칙": _전이규칙(필드, 종류, 이름, 갈래),
            "검증상태": "미검증",
        }
        출처합 = sorted({o for v in 값통.values() for o in v["출처"]})
        if 연속:
            수 = sorted(float(x) for x in 값통 if _맨숫자.match(x))
            항["범위"] = ({"최소": 수[0], "최대": 수[-1]} if 수 else None)
            항["출처"] = 출처합
            항["비고"] = (f"값이 {_메타나열상한}가지를 넘는 메타 이름표 — 문서 내용에서 오는 값이라 "
                        f"나열하지 않는다(가짓수만 센다)" if 메타넘침 else
                        "연속값 — 내용에 따라 이어지는 자리라 값을 나열하지 않는다(범위+변환식)")
        else:
            항["값"] = [
                {"값": v, "횟수": 값통[v]["횟수"],
                 "출처": sorted(값통[v]["출처"]), "반": sorted(값통[v]["반"])}
                for v in sorted(값통)
            ]
        항목[열쇠] = 항
    return 항목


# ── 연속변수 정본 (부록 §4 — 서식 자유 입력이 정본까지 닿는 7곳) ─────────────
# 값을 제한하는 게 아니라 **변환식을 한 번 검증하면 닫히는** 자리들이다.
# 관측 범위는 등록부(-docs.json)를 훑어 **세어서** 채운다 — 손으로 안 적는다.
#
# `면제` — 완전성 가드가 이 자리에서는 **값 집합이 아니라 변환식 적용 가능성**을 보는
# (장르 × 요소종류 × 속성) 짝이다. 이것을 안 적으면 가드가 제품의 자유를 막는다
# (1p 에서 사용자가 13.7pt 를 고르면 빌드가 서는 꼴). 반대로 넓게 적으면 가드가
# 헐거워지므로 **자리마다 왜 그 속성인지 실측 근거를 같이 적는다.**
#
# 서식필드가 아니라 **속성**으로 적는 이유 — `테두리` 한 필드에 속성이 셋 붙는다
# (테두리변·테두리굵기mm·테두리색). 필드로 면제하면 포인트색 하나 열자고 "어느 변에
# 선이 있나" 까지 같이 열리고, 그러면 mm 검사가 "상" 이라는 값에 걸린다
# (2026-08-07 실측 — 오탐 7건이 여기서 났다).
_연속변수정본 = [
    dict(자리="1p 항목별 임의 pt", 장르=["onepage"],
         입력열쇠=["title_fs", "summary_fs", "fs"],
         제한="없음 — 임의 pt",
         변환식이름="pt→ensure_run(size=pt)",
         변환식="inline font-size:{v}pt → 화면읽기 pt → charPr height = pt×100",
         # assemble.py 가 제목·요약·항목의 **인라인 style** 로 심는다 → 화면읽기는
         # 그 자리를 문단 pt 로 읽고, 조각에 다른 pt 가 없으면 조각도 같은 값을 문다.
         면제=[("문단", "pt"), ("조각", "pt")],  # 화면읽기가 내보내는 속성 이름 그대로
         면제근거="assemble.py 가 style=\"font-size:{v}pt\" 를 제목·요약·항목에 직접 붙인다",
         앵커=[("assemble.py", 'return f\' style="font-size:{pt}pt"\''),
              ("_hwpx_write.py", 'size=서식.get("pt")')]),
    dict(자리="풀버전 포인트색(임의 hex)", 장르=["fullreport"],
         입력열쇠=["포인트색"],
         제한="없음 — 임의 색 문자열(편집기 color picker 도 --pt 직접 설정)",
         변환식이름="hex→charPr color / borderFill",
         변환식="--pt:{색} → 화면읽기가 접힌 최종 color·backgroundColor 로 읽음 → charPr color·fillColor",
         # 실측(fullreport.css) — `var(--pt)` 가 글자색(color)·테두리(border)·
         # 바탕(background)에 모두 쓰인다. 셋 다 열려야 임의 hex 가 통과한다.
         면제=[("문단", "색"), ("조각", "색"), ("칸", "색"),
              ("문단", "바탕"), ("칸", "바탕"), ("장식", "바탕"),
              ("문단", "테두리색"), ("칸", "테두리색")],
         면제근거="fullreport.css 가 var(--pt) 를 color·border·background 세 자리에 쓴다",
         앵커=[("assemble_full.py", '속성값.색(doc.get("포인트색")'),
              ("_hwpx_write.py", 'color=_색(서식.get("색"))'),
              ("fullreport.css", "var(--pt)")]),
    dict(자리="풀버전 여백(임의 mm)", 장르=["fullreport"],
         입력열쇠=["여백_mm"],
         제한="없음 — 임의 mm",
         변환식이름="mm→HWPUNIT",
         변환식="--m-t/r/b/l:{v}mm → --doc-page-mt/mb 실측 → round(mm×283.465) HWPUNIT",
         면제=[("쪽", "여백mm")],
         면제근거="화면읽기가 쪽 여백 넉 장을 --doc-page-mt/mb 와 지면 padding 에서 잰다",
         앵커=[("assemble_full.py", 'm = doc.get("여백_mm")'),
              ("_hwpx_write.py", "set_page_margins")]),
    dict(자리="시행문 여백(임의 mm)", 장르=["gongmun"],
         입력열쇠=["여백_mm"],
         제한="없음 — 임의 mm",
         변환식이름="mm→HWPUNIT",
         변환식="--gm-mt/mr/mb/ml:{v}mm → --doc-page-mt/mb 실측 → round(mm×283.465) HWPUNIT",
         면제=[("쪽", "여백mm")],
         면제근거="화면읽기가 쪽 여백 넉 장을 --doc-page-mt/mb 와 지면 padding 에서 잰다",
         앵커=[("assemble_gongmun.py", 'm = doc.get("여백_mm")'),
              ("_hwpx_write.py", "set_page_margins")]),
    dict(자리="규정 여백(임의 mm)", 장르=["regulation"],
         입력열쇠=["여백_mm"],
         제한="없음 — 임의 mm",
         변환식이름="mm→HWPUNIT",
         변환식="--rg-mt/mr/mb/ml:{v}mm → --doc-page-mt/mb 실측 → round(mm×283.465) HWPUNIT",
         면제=[("쪽", "여백mm")],
         면제근거="화면읽기가 쪽 여백 넉 장을 --doc-page-mt/mb 와 지면 padding 에서 잰다",
         앵커=[("assemble_regulation.py", 'm = doc.get("여백_mm")'),
              ("_hwpx_write.py", "set_page_margins")]),
    dict(자리="관인(임의 크기·임의 이미지)", 장르=["gongmun"],
         입력열쇠=["지름_mm", "관인"],
         제한="없음 — 임의 지름mm·임의 이미지 경로",
         변환식이름="mm→그림 mm(add_picture)",
         변환식="--seal:{v}mm(기본 30) → 화면읽기가 그림 마디로 폭/높이mm 실측 → add_picture(mm)",
         면제=[("그림", "폭mm"), ("그림", "높이mm")],
         면제근거="관인은 그림 마디로 읽히고 크기만 건너간다(--seal 이 지름mm 를 정한다)",
         앵커=[("assemble_gongmun.py", '속성값.수(관인.get("지름_mm")'),
              ("_hwpx_write.py", "add_picture")]),
    dict(자리="이미지 폭(임의 %)", 장르=["fullreport"],
         입력열쇠=["폭"],
         제한="없음 — 임의 %(편집기 목록은 40/60/80/100 이나 스펙 직접 기입은 자유)",
         변환식이름="%→그림 mm(add_picture)",
         변환식='style="width:{v}" → 화면읽기가 그림 폭mm 실측 → add_picture(mm)',
         면제=[("그림", "폭mm"), ("그림", "높이mm")],
         면제근거="폭 % 는 화면에서 mm 로 접혀 읽히고, 높이는 그 비율을 따라간다",
         앵커=[("imageasset.py", 'w = spec.get("폭", "80%")'),
              ("_hwpx_write.py", "add_picture")]),
    # 아래 두 자리는 위 일곱과 성질이 다르다 — 사용자 입력이 아니라 **조판이 정하는
    # 연속량**이다. 입력열쇠가 비어 있는 이유다(등록부에 이 값이 오는 열쇠가 없다).
    # 가드가 이걸 유한열거로 배우면 표본에 없던 콘텐츠가 전부 선다(2026-08-13 실측:
    # 풀버전 표 포함 문서가 문단 17.4·49.3 / 칸 122.4·152.2·63.5 / 지면수 5 로 fail-close).
    dict(자리="화면 기하 실측(왼여백mm) — 상자의 왼쪽 자리는 내용·배치가 정한다",
         장르=["fullreport", "gongmun", "onepage", "press-release", "regulation"],
         입력열쇠=[],
         제한="없음 — 크롬 렌더 좌표에서 잰 연속량(가드는 ±2000mm 변환검사만 본다)",
         변환식이름="mm→indent_left_mm(HWPUNIT)",
         변환식="r.left−지면.left−padding 실측 → 문단은 왼여백mm(+안들여mm)→HWPUNIT · "
               "칸·가로줄칸은 열 폭 누적의 파생값이라 값 자체는 안 실린다(Tc 에 x 오프셋 필드 없음)",
         # 서식() 필드 중 왼여백mm 만 유일하게 기하(r.left)에서 온다(화면읽기.py 서식()).
         # 나머지 mm(내어·위/아래여백)는 computed style 선언값이라 우리 CSS 가 유한하게
         # 묶는다 — 그래서 이 면제는 왼여백mm 석 짝에서 멈춘다(넓히면 가드가 헐거워진다).
         면제=[("문단", "왼여백mm"), ("칸", "왼여백mm"), ("가로줄칸", "왼여백mm")],
         면제근거="왼여백mm 는 제목 길이·표 열 폭·격자 배치가 정하는 기하 실측이라 값 집합이 "
                "성립하지 않는다 — 표본 21가지 밖 17.4 가 실제 콘텐츠에서 나와 섰다(2026-08-13)",
         앵커=[("화면읽기.py", "왼여백mm: Math.round((r.left"),
              ("_hwpx_write.py", "indent_left_mm=round")]),
    dict(자리="쪽 수(지면수) — 내용 분량이 정한다",
         장르=["fullreport", "gongmun", "onepage", "press-release", "regulation"],
         입력열쇠=[],
         제한="없음 — 1~999 정수(0 은 지면이 안 그려진 조판 실패라 계속 세운다)",
         변환식이름="쪽 경계→page_break_before",
         변환식="화면의 쪽 번호가 바뀌는 마디마다 쪽나눔 명령 → page_break_before=True "
               "(쪽 수 자체는 HWPX 에 안 실린다 — 경계의 개수로만 산다)",
         면제=[("쪽", "지면수")],
         면제근거="표본 fullreport 가 전부 9쪽이라 유한집합 {9} 로 굳어 5쪽 실문서가 섰다"
                "(2026-08-13 실측). 0 거부는 남긴다 — CSS 미적재 HTML 을 정확히 잡아낸 값이다",
         앵커=[("역할.py", '명령.append({"종류": "쪽나눔"})'),
              ("_hwpx_write.py", "page_break_before")]),
    dict(자리="자간(자간em) — 줄 넘침을 막으려 조판이 정하는 연속량",
         장르=["fullreport", "gongmun", "onepage", "press-release", "regulation"],
         입력열쇠=[],
         제한="없음 — jachigan.js 가 0 ~ -0.06em(FLOOR) 로 줄마다 압축한 연속량",
         변환식이름="em→letter_spacing %",
         변환식="round(em×100) 을 -50~100 으로 클램프해 charPr letter_spacing % 로 — 0 도 명시 전달",
         # 자간은 사용자 입력이 아니라 jachigan.js 가 **줄바꿈을 맞추려** 텍스트 런마다
         # 붙이는 값이다(FLOOR -0.06). 내용이 다르면 값이 달라지므로 유한집합이 성립하지
         # 않는다 — 지면수·왼여백mm 과 같은 부류다(입력열쇠가 비어 있는 이유).
         면제=[("문단", "자간em"), ("조각", "자간em"), ("가로줄칸조각", "자간em")],
         면제근거="jachigan.js 가 줄 넘침을 막으려 자간을 줄마다 압축한다(FLOOR -0.06em) — 내용 "
                "의존 연속값이라 유한집합이 성립하지 않는다(2026-08-17 실측: regulation 조각 -0.02·-0.03 거부)",
         앵커=[("jachigan.js", "sp.style.letterSpacing = v"),
              ("역할.py", '"자간em": 서식.get("자간em")'),
              ("_hwpx_write.py", '인자["letter_spacing"]')]),
    # 테두리 선종류 — 값은 CSS 계산값 넷(solid·dashed·dotted·double)으로 유한하지만,
    # 표본 38건이 점선 자리(1p 표 프리셋 data-style="테두리점선" — 진단의 '표본에 없는
    # 스위치값'에 실재)를 안 밟아 값집합이 {solid} 로 굳는다. 편집기 프리셋이 제품
    # 자유라 넷 검사(_변환가능한가)로 연다. 장르·요소종류는 CSS 실사용처로만 좁힌다.
    dict(자리="1p 표 프리셋 점선(테두리점선)", 장르=["onepage"],
         입력열쇠=[],
         제한="solid·dashed·dotted·double — CSS 계산값 넷",
         변환식이름="CSS 선종류→LineType2",
         변환식="borderStyle → _선종류표(solid:SOLID·dashed:DASH·dotted:DOT·"
               "double:DOUBLE_SLIM) → 변별 borderFill",
         면제=[("칸", "테두리선종류")],
         면제근거="편집기 표 스타일 프리셋 '테두리점선'(report.css:223-228)이 dashed 를 "
                "내는데 표본이 안 밟는다(표본에 없는 스위치값 실측)",
         앵커=[("화면읽기.py", "선종류: s['border'"),
              ("_hwpx_write.py", "_선종류표 = {")]),
    dict(자리="풀버전 점선 상자·리더", 장르=["fullreport"],
         입력열쇠=[],
         제한="solid·dashed·dotted·double — CSS 계산값 넷",
         변환식이름="CSS 선종류→LineType2",
         변환식="borderStyle → _선종류표 → 변별 borderFill(칸) 또는 첫 변→4변(문단 배경)",
         면제=[("문단", "테두리선종류"), ("장식", "테두리선종류")],
         면제근거="목차 리더 dotted(fullreport.css:99)·gov-tag dashed(:168)·참고사례/절차나열 "
                "박스 dashed(:290·295)·이미지 자리표 dashed(:324) — 표본이 일부만 밟는다",
         앵커=[("화면읽기.py", "선종류: s['border'"),
              ("_hwpx_write.py", "_선종류표 = {")]),
]


def _앵커줄(파일: str, 앵커: str, 진단: dict):
    p = 여기 / 파일
    if not p.exists():
        진단.setdefault("앵커없음", set()).add(f"{파일}:{앵커}")
        return []
    자리 = [f"{파일}:{n}" for n, 줄 in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
           if 앵커 in 줄]
    if not 자리:
        진단.setdefault("앵커없음", set()).add(f"{파일}:{앵커}")
    return 자리


def _등록부훑기(열쇠들: set):
    """등록부 JSON 을 재귀로 훑어 그 열쇠에 실제로 들어온 값을 센다."""
    나옴 = {}
    for p in 자료뿌리.등록부들():
        문서들 = json.load(open(p, encoding="utf-8"))
        for d in 문서들:
            이름 = d.get("filename") or Path(p).stem

            def 걷기(x):
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k in 열쇠들 and not isinstance(v, (dict, list)):
                            나옴.setdefault(k, {}).setdefault(_값문자열(v), set()).add(이름)
                        elif k in 열쇠들 and isinstance(v, dict):
                            for k2, v2 in v.items():
                                if not isinstance(v2, (dict, list)):
                                    나옴.setdefault(k, {}).setdefault(
                                        f"{k2}={_값문자열(v2)}", set()).add(이름)
                        걷기(v)
                elif isinstance(x, list):
                    for v in x:
                        걷기(v)

            걷기(d)
    return 나옴


def 연속변수만들기(진단: dict):
    모든열쇠 = {k for v in _연속변수정본 for k in v["입력열쇠"]}
    관측 = _등록부훑기(모든열쇠)
    나옴 = []
    for v in _연속변수정본:
        값들 = {}
        for k in v["입력열쇠"]:
            for 값, 문서들 in (관측.get(k) or {}).items():
                값들.setdefault(값, set()).update(문서들)
        수 = sorted(float(x) for x in 값들 if _맨숫자.match(x))
        근거 = []
        for 파일, 앵커 in v["앵커"]:
            근거 += _앵커줄(파일, 앵커, 진단)
        나옴.append({
            "자리": v["자리"],
            "장르": sorted(v["장르"]),
            "입력열쇠": sorted(v["입력열쇠"]),
            "제한": v["제한"],
            # 가드가 값 집합 대신 변환식 적용 가능성만 보는 자리 — 여기가 곧 제품의 자유다
            "면제": {"짝": [{"요소종류": a, "속성": b,
                          "서식필드": _서식이름사상.get(b)} for a, b in sorted(v["면제"])],
                   "근거": v["면제근거"]},
            "변환식": {"이름": v["변환식이름"], "식": v["변환식"], "근거": sorted(set(근거))},
            "관측": {
                "값가짓수": len(값들),
                "범위": ({"최소": 수[0], "최대": 수[-1]} if 수 else None),
                "값": [{"값": x, "출처": sorted(값들[x])} for x in sorted(값들)],
            },
            "검증상태": "미검증",
        })
    return 나옴


# ── 표본(38건) 훑기 ─────────────────────────────────────────────────────────
def 표본목록():
    """build/samples/*.html 에서 탐침(_probe-)과 발표 슬라이드를 뺀 것 — **세어서** 얻는다.
    슬라이드는 가로(16:9) 화면 산출물이라 HWPX 로 안 가고(내보내기에서 거부), 전이 카탈로그가
    전제하는 세로 지면을 화면읽기가 못 찾는다 — 전이 측정 대상에서 뺀다."""
    out = []
    for p in Path(자료뿌리.산출물뿌리()).glob("*.html"):
        if p.name.startswith("_probe-"):
            continue
        try:
            if 'data-genre="slides"' in p.read_text(encoding="utf-8")[:1500]:
                continue
        except OSError:
            pass
        out.append(p)
    return sorted(out)


_링크 = re.compile(r'<link[^>]+href="\.\./([\w.\-]+\.css)')
_장르 = re.compile(r'<html[^>]*\sdata-genre="([^"]+)"')


def 표본메타(p: Path):
    """장르·쓰는 CSS·문서에 실제로 박힌 data-* 를 **HTML 에서 읽는다.**

    짝(장르↔CSS)을 손으로 적지 않는 이유는 늘 같다 — 장르가 늘면 손목록만 안 따라온다.
    """
    글 = p.read_text(encoding="utf-8")
    m = _장르.search(글)
    속성 = {}
    for a, v in re.findall(r'\bdata-([A-Za-z0-9-]+)="([^"]*)"', 글):
        속성.setdefault(a, {})
        속성[a][v] = 속성[a].get(v, 0) + 1
    for a in re.findall(r'\bdata-([A-Za-z0-9-]+)(?=[\s/>])', 글):
        속성.setdefault(a, {})
        속성[a].setdefault("(값없음)", 0)
        속성[a]["(값없음)"] += 1
    루트 = {}
    끝 = 글.find(">", 글.find("<html"))
    for a, v in re.findall(r'\bdata-([A-Za-z0-9-]+)="([^"]*)"', 글[:끝 + 1] if 끝 > 0 else ""):
        루트[a] = v
    return {
        "장르": m.group(1) if m else None,
        "CSS": sorted(set(_링크.findall(글))),
        "속성": {k: dict(sorted(v.items())) for k, v in sorted(속성.items())},
        "루트": dict(sorted(루트.items())),
    }


def CSS가키로삼는것(css경로들) -> set:
    """**스위치 공간은 CSS 가 정의한다** — 셀렉터가 키로 삼는 data-* 만 서식 스위치다.

    나머지(data-path·data-ent 따위)는 편집·저장·조판 그룹의 이름표라 시각엔 간접 영향만
    준다(부록 §1.10 '스타일 아닌 메타'). 손으로 가르지 않고 셀렉터에서 세어 가른다.
    """
    나옴 = set()
    for p in css경로들:
        for _, _, 셀렉터, _, _ in css읽기(p):
            for 이름, _ in _스위치뽑기(셀렉터):
                나옴.add(이름)
    return 나옴


def 화면읽기전부(표본들, 시끄럽게=True):
    """38건을 **순차로** 읽는다. 예전엔 CDP 포트 9333 고정이라 병렬이 서로 물었다 —
    지금은 포트를 크롬이 골라(화면읽기.py) 물진 않지만, 병렬은 검증한 적 없어 순차 유지.

    `_유효한읽기()` 로 감싼다 — 빈 페이지(폰트 로딩 경합)를 버리고 다시 읽는다.
    자세한 사연은 `_유효한읽기()` docstring(2026-08-07 적대리뷰 재검, 대조 2건이
    '글자: 못 찾음' 으로 선 것을 보고 표본 정식 수집에도 감쌌다).
    """
    import 화면읽기
    나옴 = {}
    for i, p in enumerate(표본들, 1):
        if 시끄럽게:
            print(f"  [{i}/{len(표본들)}] {p.stem}", flush=True)
        나옴[p.stem] = _유효한읽기(화면읽기, p, p.name)
    return 나옴


_html열기 = re.compile(r"(<html\b[^>]*)(>)")
_data_fonts = re.compile(r'data-fonts="[^"]*"')


def 글꼴전환표본읽기(표본들, 읽은것들: dict, 시끄럽게=True) -> dict:
    """상단바 '내장·명조·한글원본' 글꼴 전환이 실제로 만드는 서식을 **실측**한다.

    왜 이게 따로 필요한가 (적대리뷰 결함② 고침) — `data-fonts` 는 tokens.css 가
    `:root[data-fonts=…]` 로 건 전역 스위치라 다섯 장르 모두에 이름은 걸리지만,
    장르 CSS 가 그 값을 실제로 물려받는지는 장르마다 다르다(gongmun.css 는
    `--gm-font` 로 독립돼 안 바뀌고, press.css·regulation.css 는 tokens.css 에 없는
    `--doc-font-serif` 를 가리켜 늘 고정값이다 — 실측 2026-08-07). **어느 장르가
    반응하나를 손으로 가르지 않는다** — 다섯 장르 전부를 실제로 스위치를 걸어
    화면읽기로 재고, 값이 그대로면 그냥 새 항목이 안 생길 뿐이라 해가 없다.

    **표본 전량을 돈다 — 대표 문서 하나가 아니다(고침 2/3).** 처음엔 장르마다
    (정렬된 목록의) 첫 문서 하나만 탐침했다. 코드는 돌았고 대표 문서로는 통과했는데,
    적대리뷰가 범위를 넓혀 재니 13건 중 6건에서 다시 가드가 섰다 — 대표에 없는
    요소종류(가로줄·그림, 대표와 다른 문단 반)가 낸 글꼴 값이 카탈로그에 안 올라서다
    (2026-08-07 재현: e2e-full-flow·bt01-callcenter·bt02-waterpipe 의 '맑은 고딕',
    fr-task100-plan·fr-task100-plan-gov·ab-도형-실측 의 'HY헤드라인M'). 표본을 더
    잘 고르는 문제가 아니다 — H1/H2 의 논지 자체가 "HTML 은 우리 조립기+CSS 가
    만드니 변수공간이 유한하고, 그래서 전량을 센다"(구현계획 §2-0)이다. 그래서
    **38건 전부**를 각 모드로 다시 읽는다.

    **값 하나를 새로 들일 땐 두 번 읽어 재현되는지 본다(고침 3/3).** 처음엔 한 번만
    읽고 바로 실었다 — 그런데 카탈로그 재생성을 반복하면 sha256 이 흔들렸다
    (2026-08-07 적대리뷰 재검: `fullreport·문단·줄간격` 에 142·146 이 어느 회는
    있고 어느 회는 없었다). 원인은 임베드 글꼴(Noto Serif KR, `font-display:swap`)이
    비동기로 걸린다는 것 — 크롬이 그 글꼴을 다 앉히기 전에 재면 줄 상자 높이가
    그 사이 값으로 잡힌다(각 읽기가 매번 새 `--user-data-dir` 라 캐시가 안 남아
    확률이 매 읽기 독립이다). 페이지 자체를 못 찾는 극단은 `_화면읽기_재시도()`
    가 이미 거르지만, 이런 "페이지는 있는데 값 하나가 어중간한" 경우는 그 눈에 안
    걸린다. **표본 38건이 이미 낸 값과 같으면** 그대로 싣고(재확인 불필요 — 이미
    검증된 값이다), **새 값이면** 그 확률을 딱 한 번만 더 읽어 재현되는지 본다 —
    재현되면(같은 장르 안에서 그다음부터는 "이미 아는 값"이 되어 더 안 다시 읽는다)
    싣고, 안 되면 그 값만 버린다(마디 나머지는 그대로 싣는다). 후보가 적어서
    (실측: 76탐침 중 극소수) 비용은 크지 않다 — 매번 두 배로 읽는 것보다 훨씬 싸다.

    표본 수에는 안 들어간다 — 파일 이름을 `_probe-` 로 시작해 `표본목록()` 이 38건
    셈에서 저절로 뺀다(이 저장소가 고장 주입 때 이미 쓰던 관례, §2-2 ③).
    """
    import 화면읽기

    모드들 = sorted(_스위치값모음(sorted(여기.glob("*.css")), "fonts"))
    if not 모드들:
        return {}

    # 장르별 "이미 아는 값" — 표본 38건의 정상 corpus 에서 계산한다(재확인 여부를
    # 가르는 기준일 뿐, 실제 카탈로그 항목화는 짓기() 가 따로 한다).
    학습됨 = {}
    for p in 표본들:
        학습됨.setdefault(표본메타(p)["장르"], 모으개())
    for 이름, d in 읽은것들.items():
        장르 = d.get("장르")
        if 장르 in 학습됨:
            동적수집({이름: d}, 학습됨[장르])

    나옴 = {}
    총 = len(표본들) * len(모드들)
    재확인수 = 0
    i = 0
    for 원본 in 표본들:                                  # 대표가 아니라 **전량**(위 사유)
        장르 = 표본메타(원본)["장르"]
        글 = 원본.read_text(encoding="utf-8")
        if _html열기.search(글) is None:
            # 조용히 넘기지 않는다(규칙 3) — 조립기 산출물은 늘 <html> 이 루트다.
            # 이 자리가 걸리면 조립기 산출 형태가 바뀐 것이라 탐침이 아니라 사람이 봐야 한다.
            raise SystemExit(f"글꼴전환표본읽기: {원본.name} 에 <html> 태그가 없다")
        for 모드 in 모드들:
            i += 1
            if _data_fonts.search(글):
                새글 = _data_fonts.sub(f'data-fonts="{모드}"', 글, count=1)
            else:
                새글 = _html열기.sub(rf'\1 data-fonts="{모드}"\2', 글, count=1)
            이름 = f"_probe-fonts-{모드}-{원본.stem}"
            대상 = 원본.parent / f"{이름}.html"
            대상.write_text(새글, encoding="utf-8")
            try:
                if 시끄럽게:
                    print(f"  [글꼴탐침 {i}/{총} {장르}·{모드}] {원본.stem}", flush=True)
                모음1 = _한번읽고모으기(화면읽기, 대상, 원본.name)
                학습 = 학습됨[장르]
                후보 = [(열쇠, 값) for 열쇠, 값통 in 모음1.통.items() for 값 in 값통
                        if 값 not in (학습.통.get(열쇠) or {})]
                최종 = 모음1
                if 후보:
                    재확인수 += 1
                    if 시끄럽게:
                        print(f"    (새 값 후보 {len(후보)}건 — 한 번 더 읽어 재현 확인)",
                              flush=True)
                    모음2 = _한번읽고모으기(화면읽기, 대상, 원본.name)
                    최종 = 모으개()
                    최종.통 = {
                        열쇠: {값: 정보 for 값, 정보 in 값통.items()
                              if 값 in (학습.통.get(열쇠) or {}) or 값 in (모음2.통.get(열쇠) or {})}
                        for 열쇠, 값통 in 모음1.통.items()
                    }
                # 이번에 확인된(또는 이미 알던) 값을 학습에 더해 — 같은 장르의
                # 다음 탐침부터는 이 값을 "이미 안다"고 보고 재확인을 또 안 한다.
                for 열쇠, 값통 in 최종.통.items():
                    칸 = 학습.통.setdefault(열쇠, {})
                    for 값, 정보 in 값통.items():
                        칸.setdefault(값, {"횟수": 0, "출처": set(), "반": set()})
                나옴.setdefault(장르, {})[이름] = 최종
            finally:
                대상.unlink(missing_ok=True)            # 표본이 아니라 탐침이다 — 안 남긴다
    if 시끄럽게:
        print(f"  글꼴탐침 재확인 {재확인수}/{총}건", flush=True)
    return 나옴


def _유효한읽기(화면읽기모듈, 대상: Path, 이름: str, 시도수: int = 3) -> dict:
    """크롬이 가끔 지면을 못 찾고 빈 트리를 준다 — **그대로 카탈로그에 실으면 안 된다.**

    실측(2026-08-07 적대리뷰 재검): `task100-review-request` 를 serif 로 3번 연달아
    읽으니 2번은 정상(지면반=sheet·마디 24)인데 1번은 지면반=BODY·마디 0(크롬이 폰트
    로딩을 못 기다리고 지면(210mm 블록)을 못 찾은 경합). 그 결과가 그대로 섞이면
    "지면반=BODY"·"지면수=0"·"여백mm=0" 이 **정상 값인 것처럼** 카탈로그에 오르고,
    가드는 그걸 진짜 문서로 착각한다 — 재지도 않고 믿는 것과 같은 사고다.

    `화면읽기전부()`(표본 38건 정식 수집)도 이걸 쓴다 — 처음엔 탐침(그 아래 함수)만
    감쌌는데, 같은 날 재현에서 표본 정식 수집 쪽도 드물게 흔들리는 게 나왔다(대조가
    2건 '글자: 못 찾음' 으로 섰다 — 동시에 도는 다른 세션들의 크롬 부하가 커지면
    1.3초 정착 대기를 넘길 수 있다는 뜻). 순차 38번은 원래도 이 경합을 안 밟았는데
    실측이 그렇지 않다고 보여 준 이상 여기도 감싼다 — **재지도 않고 믿는 게 함정**
    이라는 같은 교훈이다.
    """
    마지막 = None
    for 시도 in range(시도수):
        d = 화면읽기모듈.읽기(대상)
        마지막 = d
        if d.get("마디") and (d.get("쪽") or {}).get("지면수", 0) >= 1:
            for m in d.get("마디") or []:
                if "png" in m:
                    m["png"] = bool(m["png"])           # 카탈로그.화면읽기전부 와 같은 규칙
            return d
    raise SystemExit(
        f"{이름} 을 {시도수}번 읽어도 지면을 못 찾았다"
        f"(마지막 시도: 지면반={(마지막 or {}).get('쪽', {}).get('지면반')!r} · "
        f"마디 {len((마지막 or {}).get('마디') or [])}개) — 크롬 경합이 아니라 진짜 결함일 수 있다, 손으로 봐야 한다")


def _한번읽고모으기(화면읽기모듈, 대상: Path, 원본이름: str) -> "모으개":
    """한 번 (유효하게) 읽어 `동적수집` 눈으로 (열쇠→값) 을 모은다."""
    d = _유효한읽기(화면읽기모듈, 대상, 원본이름)
    모음 = 모으개()
    동적수집({대상.stem: d}, 모음)
    return 모음


def _글꼴탐침섞기(모음: 모으개, 탐침모음들: dict) -> None:
    """탐침이 이미 걸러 낸 (열쇠→값) 만 장르 모음에 더한다 — 원 트리를 다시 안 읽는다.

    `글꼴전환표본읽기()` 가 반환하는 값은 이제 **이미 재확인까지 끝난 `모으개`** 다
    (탐침이름 → 모으개). 여기서는 그중에서도 **이 장르 모음이 아직 안 낸 새 값만**
    더한다 — 이미 아는 값을 또 더하면 그 항목의 "출처" 집합에 탐침 이름이 섞여
    `검증부여()` 가 잘못 검증을 뺏는다(실측 2026-08-07: 여과 없이 섞었더니
    코퍼스검증이 110→15 로 무너졌다). 필드를 "글꼴만" 으로 좁히지 않는 이유는 별도
    (자간·줄간격처럼 글꼴 전환이 **파생시키는** 값도 이 규칙 하나로 자연히 잡힌다 —
    필드를 손으로 좁히면 그 파생 효과가 또 빠진다, 결함①과 같은 모양).
    """
    for 탐침이름, 탐침모음 in 탐침모음들.items():
        for 열쇠, 값통 in 탐침모음.통.items():
            기존값 = set(모음.통.get(열쇠, {}))
            for 값, 정보 in 값통.items():
                if 값 in 기존값:
                    continue          # 실제 표본이 이미 낸 값 — 탐침 출처를 안 섞는다
                칸 = 모음.통.setdefault(열쇠, {})
                낱 = 칸.setdefault(값, {"횟수": 0, "출처": set(), "반": set()})
                낱["횟수"] += 정보["횟수"]
                낱["출처"] |= 정보["출처"]
                낱["반"] |= 정보["반"]


# ── 짓기 ────────────────────────────────────────────────────────────────────
def 짓기(읽은것들: dict, 글꼴탐침: dict | None = None) -> dict:
    """`글꼴탐침` — `글꼴전환표본읽기()` 가 낸 (장르 → {탐침이름: 모으개}).
    (탐침마다 이미 재확인까지 끝난 (열쇠→값) 이다 — 이 함수는 원 트리를 다시 안 본다)

    `_글꼴탐침섞기()` 로 장르별 모음에 섞는다(새 값만 — 왜는 그 함수 docstring).
    값이 이미 아는 것이면 그냥 no-op 이고, 처음 보는 값(명조·한글원본이 실제로
    바꾸는 글꼴명, 그리고 그로부터 파생되는 자간·줄간격 값)이면 그 값이 장르 항목에
    새로 오른다 — 손으로 "이 장르는 글꼴이 몇 종" 이라고 적지 않고 실측으로
    값집합을 채운다(적대리뷰 결함②의 고침).
    """
    진단 = {}
    표본들 = 표본목록()
    메타 = {p.stem: 표본메타(p) for p in 표본들}

    장르별문서 = {}
    for 이름, m in sorted(메타.items()):
        장르별문서.setdefault(m["장르"], []).append(이름)

    # ── 공통: tokens.css 는 다섯 장르가 모두 건다(표본에서 확인한다) ──
    토큰씀 = {이름 for 이름, m in 메타.items() if "tokens.css" in m["CSS"]}
    공통모음 = 모으개()
    정적수집([여기 / "tokens.css"], 공통모음, 진단)
    키속성 = CSS가키로삼는것(sorted(여기.glob("*.css")))
    for 이름, m in sorted(메타.items()):
        for a, 값셈 in m["속성"].items():
            열쇠 = f"스위치·{a}" if a in 키속성 else f"메타·{a}"
            for v, n in 값셈.items():
                공통모음.담기(열쇠, v, f"samples/{이름}.html", None, 횟수=max(n, 1))
        조합 = "·".join(f"{a}={v}" for a, v in m["루트"].items())
        공통모음.담기("스위치·조합", 조합 or "(없음)", f"samples/{이름}.html", None)
    공통항목 = 항목화(공통모음)

    # ── 장르별: 그 장르가 거는 CSS(토큰 제외) + 그 장르 문서들의 화면 실측 ──
    장르별 = {}
    for 장르 in sorted(장르별문서):
        문서들 = sorted(장르별문서[장르])
        css들 = sorted({c for 이름 in 문서들 for c in 메타[이름]["CSS"] if c != "tokens.css"})
        모음 = 모으개()
        정적수집([여기 / c for c in css들], 모음, 진단)
        동적수집({k: v for k, v in 읽은것들.items() if k in set(문서들)}, 모음)
        if 글꼴탐침 and 장르 in 글꼴탐침:
            _글꼴탐침섞기(모음, 글꼴탐침[장르])
        장르별[장르] = {
            "문서": 문서들,
            "문서수": len(문서들),
            "CSS": ["build/tokens.css"] + [f"build/{c}" for c in css들],
            "항목": 항목화(모음),
        }

    연속변수 = 연속변수만들기(진단)
    # 자유 입력 통로인데 **등록부의 어느 문서도 값을 넣은 적이 없는** 자리.
    # 변환식이 한 번도 밟힌 적 없다는 뜻이라, H2 가 검증을 붙이려면 문서부터 있어야 한다.
    안밟은연속 = [v["자리"] for v in 연속변수 if v["관측"]["값가짓수"] == 0]
    if 안밟은연속:
        진단["등록부가_안_밟은_연속변수"] = 안밟은연속

    # 실제로 읽힌 문서와 표본 목록이 어긋나면 **조용히 넘어가지 않는다**
    안읽힌 = sorted({p.stem for p in 표본들} - set(읽은것들))
    if 안읽힌:
        진단["안읽힌문서"] = 안읽힌

    # 마커가 한 번도 '마커' 로 안 읽힌 장르 — 화면읽기는 `::before` 나 `:scope>.mk` 만 본다.
    # 시행문은 마커 글자를 `.g-mk` 로 감싸서 마커가 아니라 **보통 조각**으로 읽힌다.
    #
    # **이것은 고칠 결함이 아니라 검증된 현행이다**(H1→H2 인수, 2026-08-07).
    # `.g-mk` 를 `.mk` 로 바꾸면 마커가 HWPX **글머리표** 경로를 타고, 그러면 한글이
    # 글머리 자리를 스스로 더해 줄이 통째로 밀린다(역할.문단서식 의 5.5mm 사연).
    # 지금 방식(마커 글자를 run 조각으로 그냥 내보내기)은 그 가산이 없고, 그 상태로
    # 2026-08-06 한컴 뷰어 실측을 통과했다. 그래서 진단이 아니라 **규칙**으로 남긴다 —
    # 다음 모델이 "마커가 안 읽힌다" 를 버그로 읽고 고치지 않도록.
    마커없음 = sorted(g for g, v in 장르별.items()
                    if "동적·문단·마커글자" not in v["항목"])
    if 마커없음:
        진단["마커가_글자조각으로_나가는_장르"] = {
            "규칙": "마커 글자를 글머리표가 아니라 **run 조각**으로 내보낸다 — 검증된 현행이다. "
                  "화면읽기의 마커 눈(::before / :scope>.mk)에 안 잡히는 것이 의도한 결과다",
            "왜": "글머리표 경로를 타면 한글이 글머리 자리(1em+textOffset)를 스스로 더해 "
                 "줄이 5.5mm 밀린다(2026-08-06 a5-14-overflow 실측). 조각으로 내보내면 "
                 "그 가산이 없다",
            "근거": "2026-08-06 한컴 뷰어 실측 통과 · 대조 38/38 유지",
            "고치지_말 것": "`.g-mk` 를 `.mk` 로 바꾸면 마커가 글머리표 경로를 타면서 회귀한다",
            "장르": 마커없음,
        }

    # CSS 는 정의했는데 **표본 38건이 한 번도 안 밟은 스위치 값** — 여기가 곧 구멍이다.
    # 검증되지 않은 변형이 제품에는 열려 있다는 뜻이라, H2 가 문서를 늘려 채워야 한다.
    밟힘 = {}
    for m in 메타.values():
        for a, 값셈 in m["속성"].items():
            밟힘.setdefault(a, set()).update(값셈)
    안밟음 = sorted({
        f'data-{이름}="{값}"'
        for p in sorted(여기.glob("*.css"))
        for _, _, 셀렉터, _, _ in css읽기(p)
        for 이름, 값 in _스위치뽑기(셀렉터)
        if not (값 in 밟힘.get(이름, set())
                or (값 == "(있기만 하면)" and 이름 in 밟힘))})
    if 안밟음:
        진단["표본_HTML에_없는_스위치값"] = {
            "비고": "CSS 는 이 값을 위한 서식을 갖고 있는데 표본 38건의 HTML 원문에는 없다. "
                   "**렌더 시점에 JS 가 붙이는 것**(data-overflow 는 페이지네이터가 단다)은 "
                   "이 눈에 안 보인다 — 나머지는 검증되지 않은 변형이 제품에 열려 있다는 뜻이다",
            "값": 안밟음,
        }

    카 = {
        "생성기": "build/카탈로그.py",
        "입력": {
            "CSS": [{"파일": f"build/{p.name}", "지문": _지문(p)}
                    for p in sorted((여기).glob("*.css"))],
            "표본수": len(표본들),
            "표본": [{"이름": p.stem, "장르": 메타[p.stem]["장르"],
                     "CSS": [f"build/{c}" for c in 메타[p.stem]["CSS"]],
                     "마디수": len((읽은것들.get(p.stem) or {}).get("마디") or []),
                     "지면수": ((읽은것들.get(p.stem) or {}).get("쪽") or {}).get("지면수")}
                    for p in 표본들],
            "tokens.css를_거는_문서수": len(토큰씀),
            "CSS가_키로_삼는_data속성": sorted(키속성),
        },
        "공통": {"CSS": ["build/tokens.css"], "항목": 공통항목},
        "장르별": 장르별,
        "연속변수": 연속변수,
        "진단": {k: sorted(v) if isinstance(v, set) else v for k, v in sorted(진단.items())},
    }
    카["요약"] = _요약(카)
    return 카


def _지문(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12]


def 항목전부(카: dict):
    """카탈로그의 모든 항목 — 검증상태를 세는 자리가 여기 하나뿐이어야 한다."""
    for k, v in sorted(카["공통"]["항목"].items()):
        yield f"공통·{k}", v
    for 장르 in sorted(카["장르별"]):
        for k, v in sorted(카["장르별"][장르]["항목"].items()):
            yield f"{장르}·{k}", v
    for i, v in enumerate(카["연속변수"]):
        yield f"연속변수[{i}]", v


def _요약(카: dict) -> dict:
    항목들 = list(항목전부(카))
    장르요약 = {}
    for 장르, g in sorted(카["장르별"].items()):
        갈래 = {}
        for v in g["항목"].values():
            갈래[v["갈래"]] = 갈래.get(v["갈래"], 0) + 1
        장르요약[장르] = {
            "문서수": g["문서수"], "항목수": len(g["항목"]),
            "갈래별": {k: 갈래[k] for k in sorted(갈래)},
            "유한항목수": sum(1 for v in g["항목"].values() if v["유한"]),
            "연속항목수": sum(1 for v in g["항목"].values() if not v["유한"]),
            "코퍼스검증항목수": sum(1 for v in g["항목"].values()
                            if v.get("검증상태") == "코퍼스검증"),
            "화면전용항목수": sum(1 for v in g["항목"].values()
                           if v["전이규칙"]["이름"] == "화면 배치 전용"),
            "전이규칙없음": sorted(k for k, v in g["항목"].items()
                             if v["전이규칙"]["이름"] == "미정의"),
        }
    상태 = {}
    for _, v in 항목들:
        s = v.get("검증상태")
        if s:
            상태[s] = 상태.get(s, 0) + 1
    return {
        "항목수": len(항목들),
        "검증상태있는항목수": sum(1 for _, v in 항목들 if "검증상태" in v),
        "검증상태별": {k: 상태[k] for k in sorted(상태)},
        "공통항목수": len(카["공통"]["항목"]),
        "연속변수수": len(카["연속변수"]),
        "장르별": 장르요약,
    }


# ── 검증상태 부여 (WP-H2 ②) ─────────────────────────────────────────────────
# H1 은 전 항목을 "미검증" 으로 냈다. 재 보지도 않고 초록을 적는 게 이 저장소가
# 가장 크게 밟은 함정이라(규칙 1) 검증 부여를 따로 떼어 낸 것이다. 그 몫이 여기다.
#
# **승격 조건 넷을 다 지켜야 "코퍼스검증" 이다:**
#   ① 갈래가 `동적` 이다 — 표본 38건이 화면에서 **실제로 밟은** 값이다.
#      (`정적`·`정적값` 은 CSS 선언일 뿐 아무 문서도 안 쓸 수 있다)
#   ② (요소종류 × 서식필드) 를 `대조.py` 가 **실제로 비교한다.** 아래 표가 그 목록이고,
#      앵커로 대조.py 안의 그 줄을 찾아 근거로 싣는다 — 대조가 그 비교를 그만두면
#      앵커가 사라져 `진단.앵커없음` 에 오른다.
#   ③ 전이규칙에 `떨어뜨림` 이 없다 — 알고도 못 옮기는 자리는 검증 대상이 아니다.
#   ④ 그 항목을 낸 **문서가 전부** 이번 대조에서 통과했다.
#
# 실제로 대조를 돌려서 붙인다. "대조가 이 필드를 본다" 만으로 붙이면 그게 곧
# "잰 적 없는 초록" 이다.
_대조가재는것 = {
    # (요소종류, 서식필드): (대조 검사 이름, 대조.py 안의 앵커)
    ("문단", "pt"): ("글자크기", '화pt = x.get("pt") or s.get("pt")'),
    ("문단", "굵기"): ("굵기", '화굵 = (x.get("굵기") or s.get("굵기") or 400) >= 600'),
    ("문단", "글자색"): ("글자색", '화색 = (x.get("색") or s.get("색") or "#000000").upper()'),
    ("문단", "글꼴"): ("글꼴", '화글꼴 = _글꼴(x.get("글꼴") or s.get("글꼴"))'),
    ("문단", "줄간격"): ("줄높이", '"줄높이",'),
    ("문단", "왼여백mm"): ("왼여백", '"왼여백", f\'{기대["왼여백mm"]}mm\''),
    ("문단", "안들여mm"): ("왼여백", '"왼여백", f\'{기대["왼여백mm"]}mm\''),
    ("문단", "내어mm"): ("내어쓰기", '"내어쓰기", f\'{기대["내어쓰기mm"]}mm\''),
    ("문단", "어절분리"): ("어절분리", "기대분리 != 하분리"),
    ("문단", "정렬"): ("정렬", '"정렬", 기대["정렬"], b["정렬"]'),
    ("문단", "바탕색"): ("바탕색", '화바탕 != 하바탕'),
    ("조각", "pt"): ("글자크기", '화pt = x.get("pt") or s.get("pt")'),
    ("조각", "굵기"): ("굵기", '화굵 = (x.get("굵기") or s.get("굵기") or 400) >= 600'),
    ("조각", "글자색"): ("글자색", '화색 = (x.get("색") or s.get("색") or "#000000").upper()'),
    ("조각", "자간em"): ("자간", '"자간", f"{화자간}%"'),
    ("장식", "바탕색"): ("띠 색", '"띠 색", 화색'),
    ("그림", "폭mm"): ("그림 폭", '"그림 폭", f\'{a["폭mm"]}mm\''),
    ("칸", "바탕색"): ("표 음영", '"음영", 바, cb.get("바탕") or "없음"'),
    ("칸", "정렬"): ("칸 정렬", '"칸 정렬",'),
    ("칸", "테두리"): ("괘선", 'f"괘선{변}"'),
    ("문단", "위여백mm"): ("문단간격", '"문단간격",'),
    ("문단", "아래여백mm"): ("문단간격", '"문단간격",'),
    ("칸", "안들여mm"): ("표 셀 안여백", '"셀 안여백",'),
    ("칸", "폭mm"): ("표 열너비", '"열너비",'),
    ("가로줄칸", "안들여mm"): ("표 셀 안여백", '"셀 안여백",'),
    ("가로줄칸", "폭mm"): ("표 열너비", '"열너비",'),
    ("쪽", "쪽여백mm"): ("쪽여백", '"쪽여백(위·오른·아래·왼 mm)"'),
    ("쪽", "쪽나눔"): ("쪽나눔 수", '"쪽나눔 수", 기대쪽나눔, 난쪽나눔'),
}


def _대조앵커근거(진단: dict) -> dict:
    """대조.py 안에서 그 비교가 실제로 있는 줄을 찾는다 — 손으로 안 적는다."""
    본문 = (여기 / "대조.py").read_text(encoding="utf-8").splitlines()
    나옴 = {}
    for 짝, (이름, 앵커) in sorted(_대조가재는것.items()):
        자리 = [f"대조.py:{n}" for n, 줄 in enumerate(본문, 1) if 앵커 in 줄]
        if not 자리:
            진단.setdefault("앵커없음", set()).add(f"대조.py:{앵커}")
        나옴[짝] = {"검사": 이름, "근거": 자리}
    return 나옴


def 대조로재기(읽은것들: dict, 시끄럽게=True) -> dict:
    """표본을 `대조.py` 로 재 본다 — **화면은 이미 읽은 것을 그대로 쓴다.**

    화면읽기를 또 돌리면 크롬이 38번 더 뜬다(86초). 카탈로그가 방금 읽은 트리를
    그대로 넘겨 쓰면 HWPX 되읽기(빠르다)만 새로 돈다.

    **여기서는 가드를 끈다.** 대조는 기대치를 얻으려고 `역할.옮기기()` 를 부르는데,
    그 시점의 카탈로그는 **지금 만들고 있는 것보다 낡았다.** 낡은 카탈로그로 가드를
    걸면 카탈로그를 새로 만들 때마다 옛 값이 구멍으로 잡혀 재생성이 막힌다.
    """
    import 역할
    import 대조 as _대조

    옛가드, 역할.가드켬 = 역할.가드켬, False
    통과, 실패, 못잼 = [], [], []
    try:
        for i, 이름 in enumerate(sorted(읽은것들), 1):
            hwpx = Path(자료뿌리.산출물(이름, "hwpx"))
            if not hwpx.exists():
                못잼.append({"문서": 이름, "까닭": "HWPX 짝이 없다"})
                continue
            if 시끄럽게:
                print(f"  [대조 {i}/{len(읽은것들)}] {이름}", flush=True)
            try:
                r = _대조.대조(Path(자료뿌리.산출물(이름, "html")), hwpx,
                             화=읽은것들[이름])
            except Exception as e:                       # noqa: BLE001
                못잼.append({"문서": 이름, "까닭": str(e)[:120]})
                continue
            갈래 = sorted({x[2] for x in r["틀림"]} | {x[1] for x in r["표틀림"]}
                        | {x[0] for x in r["쪽틀림"]})
            if (갈래 or r["화면에만"] or r["hwpx에만"] or r["글자수"]["모자람"] > 0):
                실패.append({"문서": 이름, "갈래": 갈래,
                           "빠진마디": len(r["화면에만"]), "남는마디": len(r["hwpx에만"]),
                           "모자란글자": r["글자수"]["모자람"]})
            else:
                통과.append(이름)
    finally:
        역할.가드켬 = 옛가드
    return {"통과": sorted(통과), "실패": 실패, "못잼": 못잼}


def _출처문서(항: dict) -> set:
    """그 항목을 낸 표본 문서들. 유한 항목은 값마다, 연속 항목은 항목마다 들고 있다."""
    if "값" in 항:
        return {o for v in 항["값"] for o in v["출처"]}
    return set(항.get("출처") or [])


def 검증부여(카: dict, 잰것: dict, 진단: dict):
    """대조 결과로 검증상태를 올린다. **안 밟은 것은 그대로 미검증이다.**"""
    근거표 = _대조앵커근거(진단)
    통과 = set(잰것["통과"])
    올린수 = 0

    for 장르 in sorted(카["장르별"]):
        for 열쇠, 항 in sorted(카["장르별"][장르]["항목"].items()):
            if 항["갈래"] != "동적":
                continue
            짝 = (항["요소종류"], 항["서식필드"])
            if 짝 not in 근거표:
                continue
            if "떨어뜨림" in 항["전이규칙"]:
                continue
            출처 = _출처문서(항)
            if not 출처 or not (출처 <= 통과):
                continue
            항["검증상태"] = "코퍼스검증"
            항["검증근거"] = {
                "방법": "build/대조.py — 화면 값과 HWPX 되읽기 값을 나란히 비교",
                "대조검사": 근거표[짝]["검사"],
                "근거": 근거표[짝]["근거"],
                "문서": sorted(출처),
            }
            올린수 += 1

    # 연속변수 7곳 — 값이 아니라 **변환식**을 검증한다. 등록부에 실제로 값이 들어온
    # 자리이고(관측 값가짓수 > 0), 그 값이 닿는 (요소종류 × 서식필드) 를 대조가 재고,
    # 그 문서가 통과했을 때만 올린다.
    for v in 카["연속변수"]:
        문서들 = sorted({o for x in v["관측"]["값"] for o in x["출처"]})
        if not 문서들 or not (set(문서들) <= 통과):
            continue
        재는짝 = [(p["요소종류"], p["서식필드"]) for p in v["면제"]["짝"]
               if (p["요소종류"], p["서식필드"]) in 근거표]
        if not 재는짝:
            continue
        v["검증상태"] = "코퍼스검증"
        v["검증근거"] = {
            "방법": "build/대조.py — 그 값이 닿는 서식필드를 화면과 HWPX 에서 나란히 비교",
            "대조검사": sorted({근거표[짝]["검사"] for 짝 in 재는짝}),
            "문서": 문서들,
        }
        올린수 += 1

    카["검증"] = {
        "방법": "build/대조.py 38건 — 화면(정본) 값과 HWPX 되읽기 값을 나란히 비교",
        "잰문서수": len(잰것["통과"]) + len(잰것["실패"]),
        "통과문서수": len(잰것["통과"]),
        "통과문서": 잰것["통과"],
        "실패문서": 잰것["실패"],
        "못잰문서": 잰것["못잼"],
        "대조가재는것": [{"요소종류": a, "서식필드": b, "검사": 근거표[(a, b)]["검사"],
                    "근거": 근거표[(a, b)]["근거"]}
                   for a, b in sorted(_대조가재는것)],
        "올린항목수": 올린수,
    }
    카["요약"] = _요약(카)
    return 올린수


# ── 정적 빠른 검사 (WP-H2 ③) ────────────────────────────────────────────────
# CSS 6벌만 다시 긁어 카탈로그의 정적 부분과 맞대 본다. 크롬이 필요 없어 **매 실행**
# 돌릴 수 있다. 동적 38건 재수집은 크롬으로 86초라 --full 몫이다.
#
# 값만 맞댄다(줄 번호는 안 본다) — 주석 한 줄 넣었다고 "카탈로그가 낡았다" 가 뜨면
# 아무도 안 읽는 경보가 된다. 대신 CSS 지문이 달라진 것은 **경고**로 남긴다(근거로
# 실린 줄 번호가 밀렸을 수 있다는 뜻이다).
_CSS자리 = re.compile(r"^[\w.\-]+\.css:\d+ ")


def _CSS에서온값(항: dict) -> set:
    """항목의 값 중 **CSS 선언에서 온 것**만. (표본 HTML 에서 온 값과 섞여 있다)"""
    return {v["값"] for v in 항.get("값") or []
            if any(_CSS자리.match(o) for o in v["출처"])}


def 정적대조(카: dict) -> dict:
    """지금 CSS 를 다시 긁어 카탈로그의 정적 부분과 맞댄다. `{다름: [...], 지문다름: [...]}`"""
    다름, 진단 = [], {}

    def 한벌(이름표: str, css들, 항목들: dict):
        모음 = 모으개()
        정적수집(css들, 모음, 진단)
        이제 = 항목화(모음)
        for 열쇠 in sorted(set(이제) | set(항목들)):
            갈래 = 열쇠.split("·")[0]
            if 갈래 not in ("정적", "정적값", "스위치"):
                continue
            새 = {v["값"] for v in (이제.get(열쇠) or {}).get("값") or []}
            옛 = _CSS에서온값(항목들.get(열쇠) or {})
            if 열쇠 not in 항목들:
                다름.append({"어디": 이름표, "열쇠": 열쇠, "무엇": "카탈로그에 없는 항목",
                           "값": sorted(새)[:8]})
            elif 새 - 옛:
                다름.append({"어디": 이름표, "열쇠": 열쇠, "무엇": "CSS 에 새로 생긴 값",
                           "값": sorted(새 - 옛)[:8]})
            elif 옛 - 새:
                다름.append({"어디": 이름표, "열쇠": 열쇠, "무엇": "CSS 에서 사라진 값",
                           "값": sorted(옛 - 새)[:8]})

    한벌("공통(tokens.css)", [여기 / "tokens.css"], 카["공통"]["항목"])
    for 장르 in sorted(카["장르별"]):
        g = 카["장르별"][장르]
        css들 = [ROOT / c for c in g["CSS"] if not c.endswith("tokens.css")]
        빠짐 = [str(p) for p in css들 if not p.exists()]
        if 빠짐:
            다름.append({"어디": 장르, "열쇠": "(CSS)", "무엇": "CSS 파일이 없다", "값": 빠짐})
            continue
        한벌(장르, css들, g["항목"])

    지문다름 = []
    for x in 카["입력"]["CSS"]:
        p = ROOT / x["파일"]
        if not p.exists():
            지문다름.append(f"{x['파일']} (사라졌다)")
        elif _지문(p) != x["지문"]:
            지문다름.append(x["파일"])
    return {"다름": 다름, "지문다름": 지문다름}


# ── 완전성 가드 (WP-H2 ①) ───────────────────────────────────────────────────
# 화면읽기가 내보낸 마디가 카탈로그가 아는 범위 밖이면 **조용히 근사치로 옮기지 않고
# 빌드를 세운다.** 이것이 §2-0 이 말한 "건건이 대응의 종말" 이다 — 새 변수가 생기는
# 순간 이름이 붙는다.
#
# 뜯는 눈은 카탈로그를 지을 때와 **똑같은 것**(`동적수집`)을 쓴다. 눈을 따로 만들면
# 규칙이 둘로 갈려서, 카탈로그가 낸 값을 가드가 거부하는 일이 난다. 그래서 현행 38건은
# 정의상 전부 통과해야 하고, 안 되면 **가드가 틀린 것이다.**
#
# 검사하지 않는 것 — `반`·`지면반`(요소 이름표)은 서식필드가 없다. 화면읽기가 내보내는
# **서식 필드가 전이의 전부**이므로 이름표는 전이 대상이 아니다(H1 진단 ③ 이 닫은 규칙).

def _수(값: str):
    try:
        return float(값)
    except (TypeError, ValueError):
        return None


_색꼴 = re.compile(r"^#[0-9A-Fa-f]{6}$")


_변 = ("상", "우", "하", "좌")


def _변환가능한가(이름: str, 필드: str, 값: str) -> str | None:
    """연속·면제 자리에서 **값이 아니라 변환식 적용 가능성**을 본다. 되면 None.

    필드가 아니라 **속성 이름을 먼저** 본다 — `테두리` 한 필드에 성질이 다른 속성이
    셋 붙어 있어서(변·굵기mm·색) 필드만 보면 "상" 을 mm 로 재려 든다.
    """
    if 값 == "없음":
        return None                       # 값 없음은 어느 변환식에서나 "안 건다" 다
    if 이름 == "테두리변":
        return None if 값 in _변 else f"테두리 변 이름이 아니다 — {'·'.join(_변)} 중 하나여야 한다"
    if 이름 == "테두리색":
        return None if _색꼴.match(값) else "테두리색→borderFill 에 넣을 수 없다 — #RRGGBB 여야 한다"
    if 이름 == "테두리선종류":
        # CSS 가 낼 수 있는 계산값 — _hwpx_write._선종류표 가 이 넷+solid 만 사상한다
        return None if 값 in ("solid", "dashed", "dotted", "double") else \
            "선종류→LineType2 에 넣을 수 없다 — solid·dashed·dotted·double 이어야 한다"
    if 이름 == "png있음":
        return None if 값 in ("참", "거짓") else "그림이 찍혔는지는 참·거짓이어야 한다"
    if 이름 == "지면수":
        # 쪽 수는 서식이 아니라 조판 결과다 — 내용 분량이 정하므로 값 집합이 성립하지
        # 않는다(표본 fullreport 가 전부 9쪽이라 {9} 로 굳어 5쪽 문서가 섰다, 2026-08-13).
        # 0 은 지면이 아예 안 그려진 것(CSS 미적재)이라 계속 세운다 — 같은 날 실측으로
        # 조판 환경이 빠진 HTML 을 정확히 이 값이 잡아냈다.
        v = _수(값)
        return None if (v is not None and v == int(v) and 1 <= v <= 999) else \
            "쪽 경계→page_break_before 로 옮긴다 — 지면수는 1~999 의 정수여야 한다" \
            " (0 은 지면이 안 그려진 조판 실패 신호)"
    if 필드 == "pt":
        v = _수(값)
        return None if (v is not None and 0 < v <= 1000) else \
            "pt→charPr height(=pt×100) 에 넣을 수 없다 — 0 초과 1000 이하의 수여야 한다"
    if 필드 in ("글자색", "바탕색", "색", "테두리색"):
        return None if _색꼴.match(값) else \
            "hex→charPr color 에 넣을 수 없다 — #RRGGBB 여야 한다"
    if 필드 == "자간em":
        v = _수(값)
        return None if (v is not None and -0.5 <= v <= 1.0) else \
            "em→letter_spacing % 는 -50~100 으로 클램프된다 — -0.5~1.0em 밖이면 값이 잘린다"
    if 필드 == "줄간격":
        v = _수(값)
        return None if (v is not None and 0 < v <= 1000) else \
            "%→lineSpacing 에 넣을 수 없다 — 0 초과 1000 이하의 수여야 한다"
    if 필드 == "굵기":
        v = _수(값)
        return None if (v is not None and 1 <= v <= 1000) else \
            "굵기→bold 두 갈래에 넣을 수 없다 — 1~1000 의 수여야 한다"
    if 필드.endswith("mm") or 필드 == "테두리":
        v = _수(값)
        # mm×283.465 가 HWPUNIT 정수로 살아야 한다. A4 한 장이 297mm 이니 ±2000mm 면
        # 어떤 자리(표 폭·그림·여백)도 다 든다. 밖이면 옮기는 쪽이 아니라 재는 쪽이 틀렸다.
        return None if (v is not None and -2000 <= v <= 2000) else \
            "mm→HWPUNIT(mm×283.465) 에 넣을 수 없다 — -2000~2000mm 의 수여야 한다"
    # **모르는 필드는 통과시키지 않는다.** 여기 이름이 없다는 건 그 필드를 연속으로
    # 다루는 규칙을 아무도 안 정했다는 뜻이다(규칙 3 — 조용한 실패 금지).
    return f"연속으로 다루는 규칙이 없는 서식필드다({필드}) — 카탈로그에 규칙을 더해야 한다"


class 완전성가드:
    """카탈로그 한 벌을 들고 마디를 검사한다. **프로세스당 한 번만 짓는다.**"""

    def __init__(self, 카: dict):
        self.카 = 카
        self.값집합 = {}
        self.항목 = {}
        for 장르, g in 카["장르별"].items():
            self.항목[장르] = g["항목"]
            self.값집합[장르] = {k: {v["값"] for v in (항.get("값") or [])}
                              for k, 항 in g["항목"].items()}
        self.면제 = {}
        for v in 카["연속변수"]:
            for 장르 in v["장르"]:
                self.면제.setdefault(장르, set()).update(
                    (p["요소종류"], p["속성"]) for p in v["면제"]["짝"])

    def 검사(self, 읽은것: dict, 문서이름: str = "(문서)") -> dict:
        장르 = 읽은것.get("장르")
        if 장르 not in self.항목:
            return {"ok": False, "구멍": [{
                "종류": "문서", "속성": "장르", "서식필드": None, "값": str(장르),
                "사유": "카탈로그가 모르는 장르다 — build/카탈로그.py 를 다시 돌려야 한다",
                "어디": {"문서": 문서이름, "반": [], "경로": []}}]}

        모음 = 모으개()
        동적수집({문서이름: 읽은것}, 모음)
        반경로 = self._반경로(읽은것)
        항목, 값집합 = self.항목[장르], self.값집합[장르]
        면제 = self.면제.get(장르, set())

        구멍 = []
        for 열쇠 in sorted(모음.통):
            _, 종류, 이름 = _열쇠뜯기(열쇠)
            값통 = 모음.통[열쇠]
            if 이름 in _자리표:
                continue                  # 반·지면반 — 카탈로그의 축이지 서식필드가 아니다(정당한 면제)
            필드 = _서식이름사상.get(이름)
            if 필드 is None:
                # 2026-08-07 고침(적대리뷰 결함①) — 예전엔 여기서 그냥 continue 했다.
                # 그 한 줄이 "반·지면반처럼 전이 대상이 아니라고 정한 이름표" 와
                # "_서식이름사상 에 아무도 안 넣은 새 필드" 를 못 갈랐다. 후자는 화면읽기가
                # 회전·투명도·그림자 같은 값을 재기 시작하는 순간 카탈로그에도 가드에도 안
                # 걸린 채 근사치로 HWPX 에 실리는 구멍이었다(고장 주입 재현: 문단에 없던
                # '투명도' 필드를 심으면 ok=True 구멍 0 으로 조용히 통과했다).
                # 완전성 가드의 존재 이유가 "카탈로그 밖이면 세운다"이므로, 이름표가 아닌
                # 미지의 필드는 조용히 넘기지 않고 **선다**(규칙 3).
                for 값 in sorted(값통):
                    구멍.append(self._구멍(
                        종류, 이름, None, 값, 문서이름, 값통, 반경로,
                        "카탈로그가 모르는 서식필드다 — _서식이름사상 에 이름이 없다"
                        "(반·지면반 같은 이름표가 아니면 build/카탈로그.py 를 다시 돌려 "
                        "이름을 등재하고 전이규칙을 정해야 한다)"))
                continue
            항 = 항목.get(열쇠)
            if 항 is None:
                for 값 in sorted(값통):
                    구멍.append(self._구멍(종류, 이름, 필드, 값, 문서이름, 값통, 반경로,
                                        "카탈로그가 모르는 (요소종류 × 서식필드) 다"))
                continue
            연속 = (not 항["유한"]) or ((종류, 이름) in 면제)
            for 값 in sorted(값통):
                if 연속:
                    말 = _변환가능한가(이름, 필드, 값)
                    if 말:
                        구멍.append(self._구멍(종류, 이름, 필드, 값, 문서이름, 값통,
                                            반경로, 말))
                elif 값 not in 값집합.get(열쇠, set()):
                    구멍.append(self._구멍(
                        종류, 이름, 필드, 값, 문서이름, 값통, 반경로,
                        f"카탈로그의 값 집합 밖이다(아는 값 {len(값집합.get(열쇠) or ())}가지)"))
        return {"ok": not 구멍, "구멍": 구멍}

    def 자기대조(self) -> list:
        """카탈로그가 아는 값을 **가드 자신에게** 먹여 본다.

        카탈로그는 현행 38건에서 나왔다. 그러니 가드가 그 값을 거부하면 38건이 거부된다는
        뜻이고, 그때 틀린 것은 문서가 아니라 **가드다**. 크롬 없이 도는 검사라 매 실행
        걸 수 있다 — 진짜 조립으로 같은 것을 보는 자리는 `--full` 의 HWPX재현 검사다.
        """
        구멍 = []

        def 재보기(장르, 열쇠, 종류, 이름, 필드, 값, 연속):
            말 = (_변환가능한가(이름, 필드, 값) if 연속 else
                 (None if 값 in self.값집합[장르].get(열쇠, set())
                  else "카탈로그가 자기 값을 값 집합에서 못 찾는다"))
            if 말:
                구멍.append({"장르": 장르, "열쇠": 열쇠, "종류": 종류, "속성": 이름,
                           "서식필드": 필드, "값": 값, "사유": 말})

        for 장르, 항목 in sorted(self.항목.items()):
            면제 = self.면제.get(장르, set())
            for 열쇠, 항 in sorted(항목.items()):
                if 항["갈래"] != "동적":
                    continue
                _, 종류, 이름 = _열쇠뜯기(열쇠)
                필드 = _서식이름사상.get(이름)
                if 필드 is None:
                    continue
                연속 = (not 항["유한"]) or ((종류, 이름) in 면제)
                for v in 항.get("값") or []:
                    재보기(장르, 열쇠, 종류, 이름, 필드, v["값"], 연속)
                # 연속 항목은 값을 안 나열한다 — 관측된 **범위 양끝**을 대신 재 본다
                if not 항.get("값"):
                    범위 = 항.get("범위") or {}
                    for x in (범위.get("최소"), 범위.get("최대")):
                        if x is not None:
                            재보기(장르, 열쇠, 종류, 이름, 필드, _값문자열(x), True)
        return 구멍

    @staticmethod
    def _반경로(읽은것: dict) -> dict:
        """반(class) → 그 반을 처음 쓴 마디의 경로. 구멍을 짚을 때만 쓴다."""
        나옴 = {}
        for m in 읽은것.get("마디") or []:
            반 = m.get("반")
            if 반 and 반 not in 나옴 and m.get("경로"):
                나옴[반] = m["경로"]
        return 나옴

    @staticmethod
    def _구멍(종류, 이름, 필드, 값, 문서이름, 값통, 반경로, 사유):
        반들 = sorted(값통[값]["반"])
        return {
            "종류": 종류, "속성": 이름, "서식필드": 필드, "값": 값, "사유": 사유,
            "어디": {"문서": 문서이름, "반": 반들[:6],
                   "경로": [반경로[b] for b in 반들 if b in 반경로][:3]},
        }


_가드캐시 = {}


def 가드읽기(경로: Path | None = None) -> 완전성가드:
    """**프로세스당 1회만** 카탈로그를 읽는다 — 1.1MB JSON 을 마디마다 읽으면 조립이 긴다."""
    p = Path(경로 or (여기 / "전이카탈로그.json"))
    열쇠 = str(p.resolve())
    if 열쇠 not in _가드캐시:
        if not p.exists():
            raise SystemExit(
                f"전이카탈로그가 없다: {p} — build/카탈로그.py 를 먼저 돌려라 "
                f"(완전성 가드는 카탈로그 없이는 못 돈다)")
        _가드캐시[열쇠] = 완전성가드(json.loads(p.read_text(encoding="utf-8")))
    return _가드캐시[열쇠]


def 쓰기(카: dict, 낼곳: Path):
    글 = json.dumps(카, ensure_ascii=False, indent=1, sort_keys=True)
    낼곳.write_text(글 + "\n", encoding="utf-8")
    return 낼곳


def main():
    ap = argparse.ArgumentParser(description="HTML→HWPX 전이 카탈로그를 만든다")
    ap.add_argument("--out", default=str(여기 / "전이카탈로그.json"))
    ap.add_argument("--조용히", action="store_true")
    ap.add_argument("--대조없이", action="store_true",
                    help="검증상태를 안 올린다(전부 미검증). 대조가 못 돌 때만 쓴다")
    a = ap.parse_args()

    표본들 = 표본목록()
    if not a.조용히:
        print(f"표본 {len(표본들)}건을 순차로 읽는다 (병렬은 검증한 적 없음)")
    읽은것들 = 화면읽기전부(표본들, 시끄럽게=not a.조용히)
    if not a.조용히:
        print("글꼴 전환(명조·한글원본)이 실제로 내는 서식을 **표본 전량**으로 탐침한다"
              " — 대표 하나만 보면 그 문서에 없는 요소종류가 빠진다(적대리뷰 재검)")
    _글꼴탐침시작 = time.monotonic()
    글꼴탐침 = 글꼴전환표본읽기(표본들, 읽은것들, 시끄럽게=not a.조용히)
    if not a.조용히:
        print(f"  글꼴탐침 도합 {time.monotonic() - _글꼴탐침시작:.1f}초"
              f" ({sum(len(v) for v in 글꼴탐침.values())}탐침, 재확인분 포함 — 위 줄 참고)")
    카 = 짓기(읽은것들, 글꼴탐침)

    # 검증상태 부여 — **재 보고 올린다.** 안 재면 전부 미검증으로 남는다(규칙 1).
    진단2 = {}
    잰것 = ({"통과": [], "실패": [], "못잼": [{"문서": "(전부)", "까닭": "--대조없이"}]}
          if a.대조없이 else 대조로재기(읽은것들, 시끄럽게=not a.조용히))
    올린 = 검증부여(카, 잰것, 진단2)
    for k, v in 진단2.items():
        카["진단"][k] = sorted(set(카["진단"].get(k) or []) | set(v))
    카["진단"] = dict(sorted(카["진단"].items()))
    카["요약"] = _요약(카)

    낸곳 = 쓰기(카, Path(a.out))
    요 = 카["요약"]
    # --out 이 저장소 밖(스크래치 등)이면 relative_to 가 ValueError 로 죽는다 —
    # 파일은 이미 다 쓴 뒤라 결과는 멀쩡한데 종료코드만 1 이 됐다(2026-08-13 실측).
    표시경로 = 낸곳.relative_to(ROOT) if 낸곳.is_relative_to(ROOT) else 낸곳
    print(f"■ {표시경로} — 항목 {요['항목수']}개 "
          f"(검증상태 있는 항목 {요['검증상태있는항목수']}개) · 연속변수 {요['연속변수수']}개")
    for 장르, s in 요["장르별"].items():
        print(f"   {장르}: 문서 {s['문서수']} · 항목 {s['항목수']} "
              f"(유한 {s['유한항목수']} / 연속 {s['연속항목수']} / "
              f"코퍼스검증 {s['코퍼스검증항목수']})")
    print(f"   검증: 대조 {카['검증']['통과문서수']}/{카['검증']['잰문서수']} 통과 "
          f"→ {올린}항목 코퍼스검증 · " + " · ".join(
              f"{k} {v}" for k, v in 요["검증상태별"].items()))
    if 카["검증"]["실패문서"]:
        for x in 카["검증"]["실패문서"][:5]:
            print(f"     ✗ {x['문서']}: {', '.join(x['갈래'][:4]) or '마디 어긋남'}")
    if 카["진단"]:
        print("   진단:", {k: (len(v) if isinstance(v, list) else v)
                         for k, v in 카["진단"].items()})


if __name__ == "__main__":
    main()
