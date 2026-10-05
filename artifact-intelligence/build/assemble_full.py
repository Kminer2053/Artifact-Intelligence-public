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

게이트: 형식 흠은 하드 없음(F구-27, 연성 경고만) — 단 '26-09-27부터 **내용 결손**은 하드다.
  · 장이 없거나("장": []) 모든 장에 절·항목 내용이 없으면 하드(gate_check) — 3차 측정에서
    서버 EXAONE 가 요약만 채우고 본문 장을 통째로 비운 채("장": [], run.json steps) 렌더까지
    통과해 백지 본문이 나갔다. 형식(제목 길이·장 수 등)은 여전히 연성이다.
사용: python3 build/assemble_full.py build/fullreport-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
import 수치꼴
import 표꼴
import 자료뿌리
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imageasset
import svgfig
import 도식색


def _도식html(fg):
    """도식 하나 → svgfig 빈 칸. 모르는 type·꼴 틀린 스펙 **하나가 조립 전체를 세우지 않게** 그 도식만
    빼고 빈 글자를 돌려준다('26-09-29 격자 도식 P2, critic_impl #14 — 예전엔 svgfig.render 의
    ValueError 를 안 잡아 문서가 통째로 안 만들어졌다). 알림은 warn_check 가 [경고] 로 낸다."""
    try:
        return svgfig.render(fg) if isinstance(fg, dict) else ""
    except ValueError:
        return ""


def _한쪽체계도(fg):
    """'크게' 체계도가 한 쪽을 채우나 — svgfig.js G.strategy.한쪽 과 같은 문턱(과제 합 9 이상 또는 전략+과제 12칸
    이상, critic_design 1-2 · '26-09-29 판정 ⑥). 두 곳이 같아야 쪽 어림이 화면과 맞는다."""
    if not isinstance(fg, dict) or fg.get("type") != "strategy" or svgfig.크기정규화(fg)[1] != "크게":
        return False
    cols = fg.get("전략") if isinstance(fg.get("전략"), list) else []
    과제합 = sum(len(c["과제"]) for c in cols if isinstance(c, dict) and isinstance(c.get("과제"), list))
    return 과제합 >= 9 or len(cols) + 과제합 >= 12


def _도식줄몫(도식들, 상수):
    """도식 하나의 줄 몫 — '크게'(면적과 글자를 같이 키운다)는 두 배로 어림한다('26-09-28).
    한 쪽을 채우는 '크게' 체계도(판정 ⑥)는 쪽 하나(판면 × 0.9)로 센다."""
    return sum(round((상수.get("쪽당_줄수") or 29) * 0.9) if _한쪽체계도(fg)
               else 상수["도식_한개_줄몫"] * (2 if isinstance(fg, dict)
                                            and svgfig.크기정규화(fg)[1] == "크게" else 1)
               for fg in (도식들 or []))

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
    # 도식 — 모르는 type 은 그 도식만 빼고 조립한다(_도식html). 문서당 도식 예산은 soft 경고다
    # ('26-09-29 격자 도식 P2, critic_design 1-5): 표현 수단(격자 표)이 늘어도 도식 남발로 번지지 않게.
    # 기본은 텍스트(정본 data_elements.시각자료._원칙). 재경부 보고서는 체계도가 문서당 1개(추진방향
    # 장 첫머리, 일부)이고 판면에서 도식·차트·그림 몫이 중앙 8.3%다(moef_figs §3·§5). 흐름·관계·비교
    # '3개 안팎'은 반박 검토의 판단값이다(재지 않음) — 그래서 막지 않고 알리기만 한다. 차트는 세지 않는다.
    도식들 = [(f"{ROMAN[ci]}장", fg) for ci, ch in enumerate(chapters) for fg in (ch.get("도식") or [])]
    도식들 += [(f"{ROMAN[ci]}장 '{str(sec.get('제목', ''))[:10]}'", fg) for ci, ch in enumerate(chapters)
             for sec in (ch.get("절") or []) for fg in (sec.get("도식") or [])]
    for 자리, fg in 도식들:
        t = fg.get("type") if isinstance(fg, dict) else None
        if t not in svgfig.유형:
            warns.append(f"{자리} 도식 type {t!r} 을 몰라 그 도식만 빼고 조립했다 — "
                         f"{'·'.join(svgfig.유형)} 중 하나로")
    체계 = sum(1 for _, fg in 도식들 if isinstance(fg, dict) and fg.get("type") == "strategy")
    흐름 = sum(1 for _, fg in 도식들 if isinstance(fg, dict)
             and fg.get("type") in ("process", "cycle", "converge", "relation", "compare"))
    if 체계 > 1:
        warns.append(f"체계도 {체계}개 — 문서당 1개(추진방향 장 첫머리)가 관행, 나머지는 본문·표로")
    if 흐름 > 3:
        warns.append(f"흐름·관계·비교 도식 {흐름}개 — 3개 안팎을 넘는다. 억지 도식은 본문으로(기본은 텍스트)")
    return warns


def _절에내용있나(sec):
    """절 하나가 화면에 찍힐 알맹이를 갖고 있는가 — 항목은 **글자가 실제로 있어야**
    친다(공백 text 는 렌더에 빈 <p> 만 남긴다, r10 검토자 발견 LOW). 항목이 없어도
    박스·도식·이미지·표가 있으면 유효하다(렌더 605-640행이 항목 없이도 이 넷을 그린다)."""
    if not isinstance(sec, dict):
        return False
    if any(isinstance(it, dict) and str(it.get("text") or "").strip()
           for it in (sec.get("항목") or [])):
        return True
    return bool(sec.get("박스") or sec.get("도식") or sec.get("이미지") or sec.get("표"))


def _장에내용있나(ch):
    """장 하나가 화면에 찍힐 알맹이를 갖고 있는가 — 절 없이 핵심박스·박스·도식만으로
    이끄는 장(렌더 578-609행이 절 없이도 그린다)도 유효하다(gate_check 머리말 그대로,
    r10 검토자 발견 LOW로 실제 판정이 이 문구와 어긋나 있던 것을 고친다)."""
    if not isinstance(ch, dict):
        return False
    if ch.get("핵심박스") or ch.get("박스") or ch.get("도식"):
        return True
    return any(_절에내용있나(sec) for sec in (ch.get("절") or []))


def gate_check(doc):
    """풀버전 최소 골격 하드 게이트 — **내용 결손**만 막는다(형식 흠은 여전히 warn_check 몫,
    F구-27). 장이 없거나("장": []) 모든 장에 절·항목 내용이 없으면 막는다 — 3차 측정(서버
    EXAONE, run.json steps)에서 요약 페이지만 채우고 본문 장을 통째로 비운 문서가 렌더까지
    통과해 백지 본문이 나갔다("장 시작 새 쪽"만 있고 본문은 없는 쪽들). 장 하나하나가 아니라
    **문서 전체**를 본다 — 장마다 강제하면, 핵심박스·박스·도식만으로 이끄는 장(절 없이도
    유효한 구성, 스키마의 절은 장의 '선택' 자식 중 하나일 뿐이다)이 오탐으로 걸린다. 실측
    (build/fullreport-docs.json 8건 전부·bench2 프론티어 10건·bench3 20건)에서 절·항목이
    빈 장은 항상 전부(즉 이 실패 사례처럼 장이 통째로 비었을 때)뿐이었다 — 오탐 0."""
    bad = []
    chapters = doc.get("장") or []
    본문있음 = any(_장에내용있나(ch) for ch in chapters if isinstance(ch, dict))
    if not chapters or not 본문있음:
        bad.append("본문 장이 비었습니다 — 요약만으로는 풀버전이 아닙니다. "
                    "자료로 장(Ⅰ~)·절·항목을 채우십시오")
    return bad


# 순수 수치 칸(숫자·부호·단위·기호만) 판정과 열 단위 우측정렬은 build/수치꼴.py 공용
# 모듈에 있다(assemble.py 와 같이 쓴다, assemble:F10 '26-09-27 — 두 조립기가 각자 정규식을
# 복사해 뒀다가 단위 목록이 갈라졌었다. 경위는 그 모듈 docstring에 있다).
_순수수치인가 = 수치꼴.순수수치인가
_표_열_우측정렬 = 수치꼴.표_열_우측정렬


def tbl_html(tb):
    cap = f'<div class="fr-tbl-caption">{html.escape(str(tb["캡션"]))}</div>' if tb.get("캡션") else ""
    # '26-09-29 표 재설계 P1: 열폭·열정렬·머리·첫열·병합·강조·모양(style)은 build/표꼴.py 한 곳이
    # 그린다(여섯 조립기 공용). 보고서형 — 숫자 열도 가운데(통계형만 오른쪽, 사장님 판정 '26-09-28 ④),
    # 긴 글 열은 왼쪽, 첫 열은 행 머리로 칠한다(재경부 관행, design 5-2).
    return f'<div class="blk fr-tbl-wrap" data-ent="표">{cap}{표꼴.표html(tb, "fr-table")}</div>\n'


def _연속쓰기_기준():
    """장마다 새 쪽을 여는 대신 이어 쓸지 정하는 어림 상수 — 온톨로지 정본
    document_types.fullreport.골격.본문._새쪽_조건부_2026_09_26.기준 을 읽는다(3차 검토:
    화면 실측 JS 는 .fr-content 가 height 고정이라 늘 0 으로 나와 한 번도 작동하지 않았고,
    그 압축이 HWPX 를 거부시키는 회귀까지 냈다 — 조립 시점에 아는 값만으로 정하도록 되돌렸다).
    _새쪽_조건부_2026_09_26 은 "장" 의 자식이 아니라 "본문" 바로 아래 형제 키다 — "장" 은
    사람이 읽는 규칙 문장(문자열)이라 .get() 을 못 받는다(3차 검토 중 실측으로 잡은 최초
    구현 결함 — 이 read 가 늘 실패해 아래 폴백만 쓰여 재보정 값이 하나도 안 먹혔었다).
    온톨로지 파일이 빠진 설치(0.3.x 배포본)에서는 이 폴백을 쓴다 — 값은 정본과 같아야 한다(코드에
    새 수치를 박지 않는다는 원칙 — assemble_slides.py 의 카탈로그 폴백과 같은 방식).

    쪽당_줄수(4차 검토, '26-09-27) — 15는 3차 검토가 "압축(보정1)이 카탈로그 밖 값을
    낸다"는 결함을 피하려고 안전 쪽으로 낮춘 값이었다(기준 안 _쪽당_줄수_고침_2026_09_27
    참조). 이번에 그 압축 자체를 이어쓰기 문서에서 아예 걷어냈으므로(넘치는 묶음은 늘
    다음 쪽으로 미는 분기만 탄다, 페이지네이터 스크립트) 그 안전판이 더 필요 없다. 값은
    실제 렌더 실측으로 다시 잡았다(기준._쪽당_줄수_재보정_2026_09_27 참조)."""
    폴백 = {"유효폭_자": 34, "쪽당_줄수": 29, "도식_한개_줄몫": 8, "이미지_한개_줄몫": 8,
           "절약_쪽수_기준": 2, "평균채움_기준": 0.60}
    p = os.path.join(ROOT, "ontology", "ontology.json")
    if not os.path.exists(p):
        return 폴백
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        기준 = (j["document_types"]["fullreport"]["골격"]["본문"]
                 .get("_새쪽_조건부_2026_09_26", {}).get("기준"))
        if isinstance(기준, dict):
            return {**폴백, **{k: v for k, v in 기준.items() if k in 폴백}}
    except Exception:
        pass
    return 폴백


def _장_줄수(ch, 상수):
    """장 하나의 분량을 글자수로 어림한 줄 수 — 실제 조판(브라우저) 측정이 아니라 근사치다.
    본문 전체 이어쓰기 여부(_문서_이어쓰기인가)를 정하는 재료로만 쓴다."""
    폭 = 상수["유효폭_자"]

    def 줄수(s):
        s = str(s or "").strip()
        return -(-len(s) // 폭) if s else 0   # 올림 나눗셈 — 빈 문자열은 0줄

    줄 = 1  # 장 제목 자신
    for t in (ch.get("핵심박스") or []):
        줄 += 줄수(t if isinstance(t, str) else (t or {}).get("text", ""))
    for bx in (ch.get("박스") or []):
        줄 += sum(줄수(it if isinstance(it, str) else (it or {}).get("text", ""))
                 for it in bx.get("항목", []))
        줄 += sum(줄수(fn) for fn in bx.get("각주", []))
    줄 += _도식줄몫(ch.get("도식"), 상수)
    for sec in (ch.get("절") or []):
        줄 += 1 + 줄수(sec.get("제목", ""))
        줄 += sum(줄수(it.get("text", "")) for it in sec.get("항목", []))
        for bx in (sec.get("박스") or []):
            줄 += sum(줄수(it if isinstance(it, str) else (it or {}).get("text", ""))
                     for it in bx.get("항목", []))
        줄 += _도식줄몫(sec.get("도식"), 상수)
        줄 += 상수["이미지_한개_줄몫"] * len(sec.get("이미지") or [])
        tb = sec.get("표")
        if tb:
            for t in (tb if isinstance(tb, list) else [tb]):
                if isinstance(t, dict):
                    줄 += 1 + len(t.get("rows") or [])
    return 줄


def _문서_이어쓰기인가(장목록):
    """장마다 새 쪽을 강제하면 낭비인지를 판정한다(4차 검토, '26-09-27 — 3차의 고정
    쪽수 문턱을 대체). 장 하나하나의 실측 대신, 조립 시점에 이미 아는 값(장·절·항목·표
    행 수)으로 문서 전체를 한 번만 어림한다.

    '짧다/길다'를 절대 쪽수로 가르던 3차 방식은, 쪽당_줄수 문턱 하나로 두 가지 서로 다른
    질문(그래서 안전 쪽으로 낮춘 값이 정반대 실패를 냈다 — 자료가 적은 보고서가 장마다
    성긴 새 쪽을 탐, e2e s2 진단)에 답하려 했다. 대신 '장마다 새 쪽'과 '이어쓰기'가 서로
    얼마나 다른 쪽수를 쓰는지 **같은 L(쪽당_줄수)로** 직접 비교한다 —
      분리쪽 = Σ_i ceil(줄_i / L)   (장마다 새 쪽을 강제할 때 어림 쪽수)
      합쪽   = ceil(Σ_i 줄_i / L)   (모두 이어 쓸 때 어림 쪽수)
    절약(분리쪽-합쪽)이 크거나(절약_쪽수_기준) 분리쪽 기준 평균 채움(총줄/(분리쪽×L))이
    낮으면(평균채움_기준 미만) 이어쓴다 — 어느 한쪽만 걸려도 낭비로 본다. 이어쓰기로
    붙인 문서는 절 분절이 쪽 경계에 걸려도 압축(보정1)을 쓰지 않고 늘 다음 쪽으로 미는
    분기만 타므로(페이지네이터 스크립트), L 을 실측 기반으로 다시 올려도(기준.
    _쪽당_줄수_재보정_2026_09_27) 3차가 피하려던 카탈로그 밖 서식이 나지 않는다."""
    상수 = _연속쓰기_기준()
    장줄 = [_장_줄수(ch, 상수) for ch in (장목록 or [])]
    if len(장줄) < 2:
        return False   # 이어붙일 다음 장이 없으면 이어쓰기가 애초에 뜻이 없다
    L = 상수["쪽당_줄수"] or 29
    분리쪽 = sum(-(-n // L) for n in 장줄)          # Σ ceil(줄_i / L)
    총줄 = sum(장줄)
    합쪽 = -(-총줄 // L)                             # ceil(Σ줄 / L)
    if 분리쪽 <= 합쪽:
        return False                                 # 이어써도 쪽이 안 준다 — 낭비가 아니다
    평균채움 = 총줄 / (분리쪽 * L)
    return (분리쪽 - 합쪽) >= 상수["절약_쪽수_기준"] or 평균채움 < 상수["평균채움_기준"]


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
    # 제목 모양('26-09-28) — 묶음(제목모양) 하나 + 요소별 덮어쓰기(제목틀·장모양·절모양).
    # 선택지 정본은 편집기 프로파일의 상단바.제목모양·제목틀·장모양·절모양 이다(손목록 금지) —
    # <html> data 속성으로 들어가므로 속성값.열거 를 **여기서 직접** 부른다(도우미·람다로 감싸면
    # 속성 잠금 정적 검사가 못 밝힌다). 기본(키 없음)이면 속성을 안 남긴다 — 왕복 불변식.
    # 모양은 CSS 스위치뿐이다(fullreport.css 끝 '제목 모양' 절) — 구조·경로·페이지네이터는 그대로다.
    _상단 = _프.get("상단바") or {}
    모양 = 속성값.열거(doc.get("제목모양"), tuple(m[0] for m in _상단.get("제목모양", ())),
                   "제목모양", 기본="")
    제목틀 = 속성값.열거(doc.get("제목틀"), tuple(m[0] for m in _상단.get("제목틀", ())),
                    "제목틀", 기본="")
    장모양 = 속성값.열거(doc.get("장모양"), tuple(m[0] for m in _상단.get("장모양", ())),
                    "장모양", 기본="")
    절모양 = 속성값.열거(doc.get("절모양"), tuple(m[0] for m in _상단.get("절모양", ())),
                    "절모양", 기본="")
    html_attr += "".join((f' data-제목모양="{모양}"' if 모양 else "",
                          f' data-제목틀="{제목틀}"' if 제목틀 else "",
                          f' data-장모양="{장모양}"' if 장모양 else "",
                          f' data-절모양="{절모양}"' if 절모양 else ""))
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
        # 결재선(팀장·부서장·기관장)과 협조란은 다르다 — 예전엔 결재선 머리칸을 '협조'로 고정
        # 출력해 결재선을 협조란으로 표시했다(디자인._정의의 '표지 결재협조'는 원래 둘을 구분하는
        # 뜻이었다). 결재선은 항상 그리고 '결재'로 표기하며, 협조자가 있을 때만 그 위에 별도
        # '협조' 행을 더한다('26-09-26 벤치마크 진단).
        _결재 = cv.get("결재")
        if not isinstance(_결재, list) or not _결재:
            _결재 = ["팀장", "부서장", "기관장"]
        _결재 = [str(x) for x in _결재][:6]
        _협조 = cv.get("협조")
        _협조 = [str(x) for x in _협조][:6] if isinstance(_협조, list) and _협조 else []
        # 협조·결재 두 행은 한 표(fr-approve) 안에서 세로로 맞물린다 — 칸 수가 다르면 표
        # 오른쪽이 비고 border-collapse 괘선이 어긋난다(2차 검토). 짧은 쪽을 빈 칸으로 채워
        # 두 행(그리고 서명 행)의 칸 수를 맞춘다.
        _칸수 = max(len(_결재), len(_협조))
        _결재셀 = "".join(
            f'<td data-ent="표지필드" data-frf="결재칸{i + 1}" data-path="표지.결재.{i}">{e(x)}</td>'
            for i, x in enumerate(_결재))
        _결재셀 += "<td></td>" * (_칸수 - len(_결재))
        _사인셀 = '<td class="sign"></td>' * _칸수
        _협조행 = ""
        if _협조:
            _협조셀 = "".join(
                f'<td data-ent="표지필드" data-frf="협조칸{i + 1}" data-path="표지.협조.{i}">{e(x)}</td>'
                for i, x in enumerate(_협조))
            _협조셀 += "<td></td>" * (_칸수 - len(_협조))
            _협조사인셀 = '<td class="sign"></td>' * _칸수
            _협조행 = (f'<tr><td class="k" rowspan="2">협<br>조</td>{_협조셀}</tr>'
                      f'<tr>{_협조사인셀}</tr>')
        parts.append(f"""<div class="fr-page fr-cover">
  <div class="fr-cover-top">
    <table class="fr-cover-meta"><tr><td class="k">문서번호</td><td data-ent="표지필드" data-frf="문서번호" data-path="표지.문서번호">{e(cv.get("문서번호", "")) or "&nbsp;" * 8}</td></tr>
      <tr><td class="k">보존기간</td><td data-ent="표지필드" data-frf="보존기간" data-path="표지.보존기간">{e(cv.get("보존기간", ""))}</td></tr>
      <tr><td class="k">공개구분</td><td data-ent="표지필드" data-frf="공개" data-path="표지.공개">{e(cv.get("공개", ""))}</td></tr>
      <tr><td class="k">보고일자</td><td>{e(cv.get("보고일", ""))}</td></tr></table>
    <table class="fr-approve">{_협조행}<tr><td class="k" rowspan="2">결<br>재</td>{_결재셀}</tr>
      <tr>{_사인셀}</tr></table>
  </div>
  <div class="fr-cover-mid">
    <div class="fr-tt-bar"></div>
    <div class="fr-subtitle">- <span data-ent="표지필드" data-frf="부제" data-path="표지.부제">{e(cv.get("부제", ""))}</span> -</div>
    <div class="fr-title" data-ent="표지필드" data-frf="제목" data-path="표지.제목" data-multiline="1">{title_br}</div>
    <div class="fr-tt-bar bottom"></div>
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
    # 본문 전체가 아주 짧으면(어림 쪽수가 기준 이하) 장마다 새 쪽을 열지 않고 모두 이어 쓴다 —
    # 단순화(3차 검토): 장마다 화면에서 실측해 정하던 1·2차 방식은 .fr-content 가 높이 고정
    # (overflow:hidden)이라 남은 공간이 늘 0으로 나와 한 번도 작동하지 않았고, 그 압축이 HWPX
    # 내보내기를 거부시키는 회귀까지 냈다(_문서_이어쓰기인가 위 docstring). 문서 전체를 조립
    # 시점에 한 번만 어림해 정하므로 장 단위 실측이 필요 없다. 간지를 쓰는 문서는 간지가 늘
    # 새 쪽을 열므로 대상에서 뺀다 — 아니면 간지 뒤 장 본문이 간지 쪽에 올라붙어 쪽번호가
    # 숨고 빈 쪽이 남는다(2차 검토에서 확인된 문제, 그대로 유지).
    전체이어쓰기 = (not 간지쓴다) and _문서_이어쓰기인가(doc.get("장", []))
    # 페이지네이터(순수 JS, 아래)에 이어쓰기 여부를 건네는 자리 — doc 자체를 건드리지
    # 않는다(#fr-doc 는 doc 를 그대로 dump 하므로, 여기 넣으면 JSON 내보내기에 내부
    # 판정값이 새 필드로 섞여 나간다). 값은 늘 bool 이라 속성값.* 잠금이 필요 없다.
    parts.append('<script type="application/json" id="fr-pageflags">'
                 + json.dumps({"이어쓰기": bool(전체이어쓰기)}) + '</script>\n')
    for ci, ch in enumerate(doc.get("장", [])):
        rn = ROMAN[ci]
        if 간지쓴다:
            parts.append(f'  <div class="blk ch fr-divider" data-ent="간지" data-num="{rn}" '
                         f'data-title="{e(ch["제목"])}">'
                         f'<div class="no">{rn}</div>'
                         f'<div class="tx">{e(ch["제목"])}</div></div>\n')
        # 새 쪽 여부 — 문서가 명시(장.새페이지: true/false)하면 그 값을 그대로 따른다. 안 하면
        # 기본은 새 쪽이고(첫 장 제외), 전체이어쓰기(위)면 이 장도 앞 장 뒤에 이어 쓴다.
        명시_새페이지 = ch.get("새페이지")
        if 명시_새페이지 is False:
            _새쪽 = ' data-새페이지="false"'
        elif 명시_새페이지 is True:
            _새쪽 = ' data-새페이지="true"'
        elif 전체이어쓰기 and ci > 0:
            _새쪽 = ' data-새페이지="false"'
        else:
            _새쪽 = ""
        # 장 제목이 쪽 끝에 홀로 남지 않게(짧은 장 이어쓰기가 새로 만드는 orphan 방지) 이 장의
        # 첫 내용 블록과 같은 그룹으로 묶는다 — 첫 내용이 절이면 그 절 자신의 그룹(g{ci}-1)을
        # 그대로 쓰고, 아니면(핵심박스·박스·도식이 절보다 먼저 오면) 제목·그 블록만의 2인 그룹을 새로 만든다.
        kb = ch.get("핵심박스") or []
        장박스 = ch.get("박스") or []
        장도식 = ch.get("도식") or []
        if kb:
            첫타입 = "핵심박스"
        elif 장박스:
            첫타입 = "박스"
        elif 장도식:
            첫타입 = "도식"
        elif ch.get("절"):
            첫타입 = "절"
        else:
            첫타입 = None
        첫그룹 = (f"g{ci}-1" if 첫타입 == "절" else f"ch{ci}head" if 첫타입 else None)
        # 페이지네이터 전용 속성(data-keepwith) — 분절 방지에만 쓰고 편집기가 보는 data-group
        # 은 재사용하지 않는다. 첫 내용이 절일 때 장 제목에 그 절의 data-group(g{ci}-1)을
        # 그대로 붙였더니, 편집기의 '절 전체 삭제'(같은 data-group 블록을 모두 지움)가 그
        # 절을 지울 때 장 제목까지 지워 장 자체가 정본에서 통째로 사라졌다(2차 검토 확인).
        _제목그룹 = f' data-keepwith="{첫그룹}"' if 첫그룹 else ""
        parts.append(f'  <div class="blk ch fr-chapter" data-ent="장" data-num="{rn}" data-title="{e(ch["제목"])}"{_정렬속성(ch)}{_새쪽}{_제목그룹}>'
                     f'<span class="no">{rn}.</span> '
                     f'<span class="tx" data-path="장.{ci}.제목">{e(ch["제목"])}</span></div>\n')
        if kb:   # 장 시작 두괄 대행 — 카탈로그 '핵심메시지'로 렌더
            _추가 = f' data-keepwith="{첫그룹}"' if 첫타입 == "핵심박스" else ""
            parts.append("  " + box_html({"종류": "핵심메시지", "항목": kb},
                                         path=f"장.{ci}.핵심박스", flat=True).replace(
                'class="blk fr-box"', f'class="blk fr-box"{_추가}', 1))
        for bi, bx in enumerate(ch.get("박스", [])):
            _추가 = f' data-keepwith="{첫그룹}"' if (첫타입 == "박스" and bi == 0) else ""
            parts.append("  " + box_html(bx, path=f"장.{ci}.박스.{bi}").replace(
                'class="blk fr-box"', f'class="blk fr-box"{_추가}', 1))
        for fi, fg in enumerate(ch.get("도식", [])):
            _추가 = f' data-path="장.{ci}.도식.{fi}"'
            if 첫타입 == "도식" and fi == 0:
                _추가 += f' data-keepwith="{첫그룹}"'
            _칸 = _도식html(fg)
            if _칸:
                parts.append("  " + _칸.replace('class="blk fr-fig"', f'class="blk fr-fig"{_추가}', 1))
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
                _칸 = _도식html(fg)
                if _칸:
                    parts.append("  " + _칸.replace(
                        'class="blk fr-fig"',
                        f'class="blk fr-fig" data-group="{gid}" data-path="{sp}.도식.{fi}"', 1))
            # 이웃한 두 그림이 둘 다 '작게'면 나란히(현장 전후 쌍 — P3 '26-09-30, design §7). 짝은 imageasset.그림짝 이
            # 정하고, 한글(HWPX)은 위아래로 쌓고 알린다(_hwpx_write.그림)
            # 생성 그림은 풀버전에 싣지 않는다(genres.그림정책 — 저장·편집기로 들어와도 여기서 빠진다, imageasset.싣는가)
            _그림들 = [(_gi, x) for _gi, x in enumerate(sec.get("이미지") if isinstance(sec.get("이미지"), list) else [])
                     if isinstance(x, dict) and imageasset.싣는가(x, "fullreport")]
            _그림html = [imageasset.render(x, f"{doc['filename']}-{gid}-{_gi}") for _gi, x in _그림들]
            for (_gi, _x), _h, _짝 in zip(_그림들, _그림html, imageasset.그림짝(_그림html, [x for _, x in _그림들])):
                parts.append("  " + _h.replace(
                    'class="blk fr-fig fr-img"',
                    f'class="blk fr-fig fr-img{속성값.열거(_짝, ("", " fig-pair fig-pair-l", " fig-pair fig-pair-r"), "그림짝", 기본="")}" '
                    f'data-group="{gid}" data-path="{sp}.이미지.{속성값.수(_gi, "그림차례", 기본="0")}"', 1))
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
// 이어쓰기로 붙인 문서인가(조립기가 정한 값, 위 #fr-pageflags) — 참이면 아래 넘침
// 분기에서 압축(보정1)을 아예 안 쓴다. 짧은 문서를 이어 쓰다 절 그룹이 쪽 경계에
// 걸릴 때 --lhs 를 낮추는 압축이 카탈로그 밖 줄간격·여백을 만들어 HWPX 를 거부시켰다
// (4차 검토) — 이어쓰기 문서는 넘친 묶음을 늘 다음 쪽으로 미는 분기만 타게 한다.
const CONT_MODE = (() => { try {
  return !!JSON.parse(document.getElementById('fr-pageflags').textContent)['이어쓰기'];
} catch (e) { return false; } })();

// 재조판 전에 현재 쪽에서 블록을 다시 걷는다 — 편집기가 추가·삭제한 것을 살리기 위해.
// (최초 스냅샷만 다시 뿌리면 편집 결과가 통째로 사라진다)
function harvest() {
  const pages = [...document.querySelectorAll('.fr-bodypage')];
  if (!pages.length) return SRC;
  const out = [];
  pages.forEach(p => {
    const inner = p.querySelector('.fr-content');
    // 이음 조각(.fr-fig-cont — 나뉜 도식의 둘째 쪽 뒤)은 원본 블록이 아니라 걷지 않는다(되붙이기가 치운다)
    if (inner) [...inner.children].forEach(b => {
      if (b.classList.contains('blk') && !b.classList.contains('fr-fig-cont')) out.push(b); });
  });
  return out.length ? out : SRC;
}
const LHS_MIN = 0.86, LHS_MAX = 1.16;                   // 줄간격 배율 허용 범위
const GAP_FILL = 0.10;                                  // 이 비율 이상 남으면 늘려서 채운다

function paginate() {
  // 쪽을 나눠 실었던 도식(판정 ⑧)은 이음 조각을 걷고 통째로 되그린 뒤 다시 잡는다 — 조각은 원본 블록이 아니다
  if (window.SVGFIG && window.SVGFIG.되붙이기) window.SVGFIG.되붙이기();
  if (window.SVGFIG) document.querySelectorAll('.fr-fig[data-fig]:empty')
    .forEach(el => window.SVGFIG.mount(el));
  SRC = harvest();                                      // 현재 상태를 원본으로 삼는다
  document.querySelectorAll('.fr-bodypage').forEach(p => p.remove());
  const flow = document.createElement('div');           // 매 회차 새 흐름에서 시작
  flow.id = 'fr-flow'; flow.style.cssText = 'position:absolute;left:-9999mm;top:0;width:170mm;visibility:hidden';
  document.body.appendChild(flow);
  SRC.forEach(b => { b.style.removeProperty('display'); flow.appendChild(b); });

  // 문단 그룹 열쇠 — data-group(편집기가 '절 전체 삭제'로 인식하는 바로 그 그룹)과
  // data-keepwith(장 제목·장 시작 블록을 분절 방지에만 묶는 페이지네이터 전용 값, 2차 검토)를
  // 함께 본다. 장 제목이 절과 같은 data-group 을 들고 있으면 편집기가 절을 지울 때 제목까지
  // 지워 장이 통째로 사라지므로, 제목 쪽은 data-group 대신 data-keepwith 만 쓴다.
  const gkey = b => b.dataset.group || b.dataset.keepwith;
  const total = {};                                     // 그룹별 총 블록 수
  SRC.forEach(b => { const g = gkey(b); if (g) total[g] = (total[g] || 0) + 1; });
  // 장 제목이 낀 그룹(data-keepwith 를 든 .ch 블록) — 쪼개질 때 압축(보정1)을 걸지 않고 늘
  // 다음 쪽으로 옮기는 분기만 타게 하는 데 쓴다(아래 head/tail 판정, 3차 검토).
  const titleGroups = new Set(SRC.filter(b => b.classList.contains('ch') && b.dataset.keepwith)
    .map(b => b.dataset.keepwith));
  // 이 id 가 data-group 으로도(절 자신의 그룹으로) 쓰이는가 — 첫 내용이 절일 때 장 제목이
  // 그 절의 data-group 을 그대로 재사용한다(위 주석). 그런 그룹은 제목+절 제목뿐 아니라
  // 절의 항목·표까지 멀리 걸쳐 여러 쪽에 나뉠 수 있어, 늘 보호하면 절 내부의 흔한(제목과
  // 무관한) 분절까지 전부 압축 금지로 바뀐다(아래 제목경계 판정에서 가른다). 첫 내용이
  // 핵심박스·박스·도식이면(ch{ci}head) data-group 으로는 안 쓰여 늘 2인조(제목+블록 하나)
  // 뿐이므로 늘 보호해도 안전하다.
  const 절재사용그룹 = new Set(SRC.filter(b => b.dataset.group).map(b => b.dataset.group));

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
    // 장은 기본으로 새 쪽에서 시작한다. data-새페이지="false" 면 앞 쪽에 이어 붙인다(사장님
    // 요청 #8 — 본문 전체가 짧을 때 조립기가 이 값을 직접 채운다, 3차 검토 단순화).
    const 새쪽 = isCh && b.dataset.새페이지 !== 'false';
    if (!inner || (새쪽 && inner.childElementCount)) inner = newPage();
    inner.appendChild(b);
    // 한 쪽 높이 상한을 넘는 격자 절차·체계도(svgfig 가 data-fig-split 을 단다) — 통째로 넘기거나 넘친 채 두지
    // 않고 이 쪽부터 조각으로 나눠 싣는다(이음 조각은 '(계속)' 캡션·머리 줄 되풀이). '26-09-29 판정 ⑧
    if (!fits(inner) && window.SVGFIG && window.SVGFIG.나눌수 && window.SVGFIG.나눌수(b)) {
      inner = window.SVGFIG.나눠싣기(b, inner, fits, newPage);
      continue;
    }
    if (fits(inner) || inner.childElementCount === 1) continue;

    // 넘쳤다 — 이 블록이 속한 문단 그룹이 쪽 경계에서 쪼개지는 상황
    const g = gkey(b);
    const head = g ? [...inner.children].filter(x => gkey(x) === g && x !== b) : [];
    const tail = g ? (total[g] - head.length) : 1;      // 이 블록 포함 넘어갈 조각 수
    // keep-with 경계인가 — 늘 2인조(제목+블록 하나)뿐인 그룹(핵심박스·박스·도식이 첫
    // 내용)은 항상 보호한다. 절이 첫 내용이라 data-group 을 재사용하는 그룹은, 장 제목이
    // **아직 내용 없이 혼자(또는 절 제목과만)** 쪽에 남는 순간에만 보호한다 — 제목·절 제목
    // 뒤로 실제 항목이 이미 하나라도 함께 놓인 뒤에는 그 절이 여러 쪽에 걸쳐 나중에 또 넘칠
    // 수 있는데, 그건 제목과 무관한 보통의 절 분절이라 원래 분기(tail>head)를 그대로
    // 따라야 한다 — 안 그러면 절 내부의 흔한 분절까지 전부 '압축 금지'로 바뀐다(3차 검토
    // 중 실물 표본 재현으로 확인한 회귀 — fr-paper-digitization-3yr 같은 흔한 문서가
    // 카탈로그 밖 서식으로 HWPX 거부됐다).
    const 헤더뿐 = x => x.classList.contains('ch') || x.classList.contains('fr-sec');
    const 제목경계 = g && titleGroups.has(g) && (
      !절재사용그룹.has(g) ||
      ([...head, b].every(헤더뿐) && [...head, b].some(x => x.classList.contains('ch'))));
    const prevInner = inner;
    inner = newPage();
    // keep-with 경계는 쪼개질 때 압축하지 않는다 — 늘 다음 쪽으로 옮긴다. 압축(보정1)은
    // 줄간격을 카탈로그 밖 값(0.86 근방)까지 낮춰 HWPX 내보내기를 거부시킨다. 이어쓰기
    // 문서(CONT_MODE)는 이 보호를 제목경계뿐 아니라 모든 분절에 넓힌다 — 짧은 문서를
    // 이어 쓰다 보통 절 그룹이 쪽 경계에 걸려도 압축을 절대 쓰지 않는다(4차 검토).
    if (CONT_MODE || 제목경계 || (head.length && tail > head.length)) {
      // keep-with 경계, 또는 뒤쪽이 더 많다 → 문단 시작 앞에서 쪽을 넘기고, 앞 쪽은 줄간격을
      // 늘려 채운다(head 가 비어 있으면 채울 것도 없어 사실상 그대로 둔다)
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

  let kept = pages.filter(p => { const ok = p.firstChild.childElementCount > 0;
    if (!ok) p.remove(); return ok; });

  // ── 보정 1: 압축 — 다음 쪽으로 넘어간 같은 그룹 꼬리를 줄간격을 줄여 당겨온다 ──
  kept.forEach((pg, i) => {
    const g = pg.dataset.tighten; const next = kept[i + 1];
    if (!g || !next) return;
    const tail = [...next.firstChild.children].filter(x => gkey(x) === g);
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

  // 보정 1이 다음 쪽의 꼬리를 통째로 당겨오면 그 다음 쪽이 통째로 빌 수 있다 — kept 는
  // 보정 1보다 먼저 걸러 뒀으므로, 그때는 안 비었다가 방금 비어 버린 쪽이 목록에 남아
  // 쪽번호만 찍힌 빈 쪽이 생겼다(2차 검토). 보정 1 뒤에 한 번 더 걸러 낸다.
  kept = kept.filter(pg => { const ok = pg.firstChild.childElementCount > 0;
    if (!ok) pg.remove(); return ok; });

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
  // 간지에는 쪽번호를 찍지 않는 것이 기본이다(경영평가 보고서 관행).
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
    # #3 개체 위/아래 간격 + 도식 팔레트(--fig-*, 도식색.py 가 hex 로 미리 계산 — 남색 기본이면 빈 글자)
    return "".join(parts).replace("</head>", 속성값.간격스타일(doc) + 도식색.스타일(doc) + "</head>", 1)


def 조립하기(등록부경로, only=None, out=None, 저장=False):
    """풀버전 등록부 → HTML. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 산출물뿌리를 **호출마다**
    다시 푼다(세션 오염 방지, 모듈 머리말). `out` 을 주면(=--out) 그 자리로 뽑는다.
    gate_check(내용 결손)에 걸린 문서는 안 쓰고 ok=False — 그 밖의 형식 흠은 여전히
    warn_check 로만 알린다(F구-27, 하드 아님).

    `저장`(기본 False) — True 면 gate_check 의 "본문 장이 비었습니다"(내용 결손) 위반만
    소프트 경고로 낮춘다(assemble_slides.조립하기 의 같은 인자와 같은 취지, r10 사후검토
    발견 medium). 예전엔 새 하드 게이트가 **이미 백지 본문으로 등록된 문서**의 저장(편집
    반영 후 재조립, apply_edit_any.py 가 `--저장`을 붙여 부른다)까지 막아, 등록부(JSON)는
    편집이 반영됐는데 HTML 은 옛 채로 남는(정본과 화면이 어긋나는) 상태를 만들었다 — 정작
    그 문서를 고치려는 편집이 통째로 실패했다. 새 초안(새문서)에서는 여전히 하드로 막되
    (저장=False 기본값), 이미 등록된 문서를 저장할 때는 다른 결함(제목 없음 등, gate_check
    에 더 없다)은 그대로 하드다."""
    낼곳 = out if out else 자료뿌리.산출물뿌리()   # 호출마다 세션 뿌리를 다시 푼다
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    # 한 건만 다시 만들 수 있다(`--only <문서키>`, WP-S2 ②) — 세션 안에서 문서
    # 하나를 저장할 때 나머지 문서 파일까지 다시 쓰지 않으려고. 판정은 genres 한 곳.
    docs = genres.한건만(docs, ["--only", only] if only else [])
    fail = 0
    낸것, 로그 = [], []
    for doc in docs:
        bad = gate_check(doc)
        if 저장 and bad:
            연성 = [b for b in bad if b.startswith("본문 장이 비었습니다")]
            if 연성:
                bad = [b for b in bad if b not in 연성]
                로그.append(f"[소프트 경고] {doc['filename']}")
                for w in 연성:
                    로그.append(f"  · (저장이라 하드에서 낮춤) {w}")
        if bad:
            fail = 1
            로그.append(f"[게이트 위반] {doc['filename']}")
            for b in bad:
                로그.append(f"  ✗ {b}")
            continue
        for w in warn_check(doc):
            로그.append(f"[경고] {doc['filename']}: {w}")
        fn = f"{doc['filename']}.html"
        with 자료뿌리.쓰기(os.path.join(낼곳, fn)) as f:      # 원자 쓰기(WP-S2 ③)
            f.write(genres.판찍기(build(doc)))
        낸것.append(fn)
        로그.append(f"built: {fn}")
    return {"ok": fail == 0, "낸것": 낸것, "로그": "\n".join(로그)}


def main():
    # --out DIR 로 다른 곳에 뽑을 수 있다. 기준이 바뀌었을 때 임시 폴더에 다시 만들어
    # 겉모습을 대조하려면 정본을 건드리지 않고 뽑을 길이 있어야 한다(history/stamp.py).
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    # --저장 — apply_edit_any.py 가 저장(편집 반영) 뒤 재조립할 때만 붙인다(조립하기()
    # docstring 참고, assemble_regulation.py 의 같은 깃발과 같은 방침).
    본 = 조립하기(argv[0], only=only, out=out, 저장=("--저장" in sys.argv))
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
