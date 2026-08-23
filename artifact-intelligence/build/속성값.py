#!/usr/bin/env python3
"""HTML **속성 자리**에 들어가는 값의 계약 — 본문 새니타이저(assemble._허용마크업)의 짝.

왜 만들었나 (2026-08-07, 적대리뷰발견.md §치명 1건·§높음 1건 + 같이 나온 넉 자리):
본문·요약·제목은 잠갔는데 **속성 자리는 아무도 안 잠갔다.** 조립기 다섯이 전부
표현용 '수치성' 필드를 f-string 으로 속성값에 그대로 보간하고 있었다 —

    assemble.py            title_fs·summary_fs·항목 fs → style="font-size:{v}pt"
                           table.style                 → data-style="{v}"
    assemble_full.py       여백_mm·포인트색            → <html style="…">
    assemble_gongmun.py    여백_mm·관인.지름_mm        → style="…"
    assemble_regulation.py 여백_mm                     → <html style="…">
    assemble_press.py      본문[].level                → class="pr-l{v}"

값에 큰따옴표를 넣으면 속성을 일찍 닫고 태그 안에 활성 마크업을 심을 수 있다.
2026-08-07 실측(진짜 크롬, 포트0+DevToolsActivePort)으로 다섯 장르 전부에서
`<img onerror>` · `<html onmouseover>` · `<p onmouseover>` 가 **실제로 붙고 돌았다**
(1p 는 전역 넷 오염 __pwn_title·summary·item·table). 산출 HTML 은 CSP
script-src 'unsafe-inline' 아래에서 돌고, 로그인이 없어 세션쿠키 하나가 곧 신분이라
실행 즉시 그 세션 전체가 남의 것이 된다.

**이스케이프가 아니라 계약으로 좁힌다.** `html.escape` 로 때우면 CSS 에
`--m-t:0mm&quot;…mm` 같은 못 읽는 값이 남고, 무엇보다 이 자리들의 계약은 자유글이
아니다 — 숫자이거나(pt·mm) 등록부가 정한 열거값이다(표 스타일·글꼴). 숫자여야 하는
자리는 **숫자만 받는 편**이 이스케이프보다 좁다. 본문 자리에서 `&` 를 다시
이스케이프하면 `F&B` 가 화면에 `F&amp;B` 로 인쇄되는 것과 같은 이유로, 자리마다
계약을 보고 그 계약에 맞게 좁힌다(assemble._허용마크업 주석과 같은 원칙).

**거부는 소리 내서 한다**(구현계획 §0 규칙 3, 조용한 실패 금지). 못 읽는 값을
조용히 버리지 않고 stderr 에 한 줄 남긴다 — 웹앱은 자식 프로세스의 stderr 를 `로그` 로
사용자에게 그대로 올린다. 죽이지는 않는다: 표현용 값 하나 때문에 문서 전체가 안
나오면 그게 더 나쁘다.

열거 후보는 **여기 손으로 적지 않는다**(규칙 2, 손목록 금지) — 부르는 쪽이
등록부(ontology/editor-profiles.json)·CSS 에서 세어서 넘긴다.
"""
import math
import sys

# 숫자 하나. 지수표기(1e3)·공백·단위·부호섞임은 안 받는다 — pt·mm 자리의 계약이다.
_숫자꼴 = ("0123456789", ".", "+-")


def _거부(자리, 값, 왜):
    print(f"[속성 거부] {자리}={값!r} — {왜}", file=sys.stderr)


def _수읽기(값):
    """문자열/숫자 → float. 못 읽으면 None. `float()` 을 바로 안 쓰는 이유:
    float 는 'inf'·'nan'·'1_0'·' 1 ' 까지 받아 준다 — 속성에 실을 글자가 아니다."""
    if isinstance(값, bool):
        return None                       # True 는 1 이 아니다 — 잘못 흘러온 값이다
    if isinstance(값, (int, float)):
        return float(값) if math.isfinite(값) else None
    if not isinstance(값, str):
        return None
    s = 값.strip()
    if not s:
        return None
    몸 = s[1:] if s[0] in "+-" else s
    if not 몸 or 몸.count(".") > 1:
        return None
    if any(c not in "0123456789." for c in 몸):
        return None
    if 몸 == ".":
        return None
    return float(s)


def 수(값, 자리, 기본=None, 최소=None, 최대=None):
    """숫자 하나만 받는 자리(pt·mm·em 앞). 낸다: 숫자 문자열 또는 `기본`.

    `None`·빈 문자열은 '안 준 것' 이라 조용히 `기본` 이다(거부가 아니다).
    0 은 정상 값이다 — 여백 0mm 는 실제로 쓴다. 그래서 여기서 0 을 안 걸러 낸다.
    부르는 쪽이 '0 이면 속성을 안 남긴다'로 쓰고 싶으면 부르기 전에 스스로 판단한다.
    """
    if 값 is None or 값 == "":
        return 기본
    n = _수읽기(값)
    if n is None:
        _거부(자리, 값, "숫자만 받는 자리입니다(속성 탈출 방지)")
        return 기본
    if (최소 is not None and n < 최소) or (최대 is not None and n > 최대):
        _거부(자리, 값, f"{최소}~{최대} 밖입니다")
        return 기본
    # 25.0 → '25' · 11.5 → '11.5'. 정수는 정수로 찍어야 산출물이 예전과 같다.
    return f"{n:.10g}"


def 열거(값, 후보들, 자리, 기본=None):
    """등록부가 정한 값 중 하나만 받는 자리(표 스타일·글꼴·level 따위).

    후보들은 **부르는 쪽이 등록부에서 세어서** 넘긴다 — 여기 적으면 손목록이 된다.
    """
    if 값 is None or 값 == "":
        return 기본
    if 값 in 후보들:
        return 값
    _거부(자리, 값, "고를 수 있는 것: "
          + (", ".join(str(x) for x in 후보들) or "(없음)"))
    return 기본


def 색(값, 자리, 기본):
    """CSS 색 한 개. 계약은 16진 표기다(실측: 정본이 쓰는 것은 #0070C0·#C00000 뿐).

    `rgb()`·`color-mix()` 같은 함수 표기를 열어 주면 괄호 안에 뭐든 들어가 다시
    같은 문이 된다. 넓힐 일이 생기면 여기 한 곳만 넓힌다.
    """
    if 값 is None or 값 == "":
        return 기본
    s = str(값).strip()
    if (len(s) in (4, 5, 7, 9) and s[0] == "#"
            and all(c in "0123456789abcdefABCDEF" for c in s[1:])):
        return s
    _거부(자리, 값, "#RGB·#RRGGBB 꼴 16진 색만 받습니다")
    return 기본
