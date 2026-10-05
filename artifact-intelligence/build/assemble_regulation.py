#!/usr/bin/env python3
"""규정(내규·사규) 조립기 — JSON → 규정 HTML. 조문 번호 자동 부여.

정본: ontology document_types.regulation (실물 사례, 2026-08-01)
  구성  제명 — (제N장) — 제N조(조제목) — 부칙. 제1조· 부칙· 제1장
  문체  jomun(조문체) — 한다체+ 형용사 종결=. 합니다체 금지
  디자인 전 위계 같은 크기(14pt) · 위계는 굵게로만 가른다
        (제N장· 제N조· 제N절굵게 / 항·호·목

문서 JSON 스키마(build/regulation-docs.json — 배열):
{
  "filename": "reg-…", "genre": "regulation",
  "기관명": "…", "제명": "생성형 인공지능 업무활용 규정", "규정번호": "규정 제○○호",
  "본문": [                       ← 번호는 넣지 않는다(자동)
    {"level": "장", "제목": "총칙"},
    {"level": "절", "제목": "통칙"},
    {"level": "조", "제목": "목적", "text": "이 규정은 …을 목적으로 한다."},
    {"level": "항", "text": "…"},
    {"level": "호", "text": "…"},
    {"level": "목", "text": "…"}
  ],
  "부칙": [{"호": "제2026-○호", "일자": "2026. 8. 1.", "본문": ["이 규정은 … 시행한다."]}],
  "별표": [{"번호": 1, "제목": "…", "표": {"header": [...], "rows": [[...]]}}],
  "제정이유": "…" (선택, 제정안·개정안일 때 산문 한 단락),
  "주요내용": ["…", "…"] (선택, 배열 — 가.나.다. 는 자동),
  "확인요청": [{"조": "제3조", "가정": "…", "근거": "자료 문장 또는 '자료에 없음'"}] (선택 — 작성 모델이 스스로 정한 것.
              그리지 않는다. 새문서가 확인 물음으로 옮기고 등록 전에 뗀다, reg13d 판정 D1)
}
제정이유·주요내용(온톨로지 document_types.regulation.구성.선택키, '26-09-26 벤치마크 진단 반영)은
법제처 입법예고 관행대로 제명과 제1조 사이에 둔다. 둘 다 없으면 전과 같이 제1조부터 바로 시작한다(회귀 없음).

조판 규범 — 규정 표본 실측에 따른다
  · **첫 항은 조 제목과 같은 줄에 붙는다.** "제5조(도구의 승인) ① 업무에 쓰는 도구는 …"
  · **항이 하나뿐이면 ① 을 붙이지 않는다.** "제8조(교육) 정보화 담당 부서는 …"
    (시행문의 '항목 하나뿐이면 기호 미부여'와 같은 규범)
  · 조는 둘째 줄부터 2글자 들여쓴다(2글자 내어쓰기)
    ※ '26-09-28 정정 — 이 '2글자'는 내어쓰기 -10.4mm(HWP 이진 두 배 저장을 보정 없이 읽은
      값)에서 나온 옛 해석이다. 실측은 약 5.2mm(14pt 1자쯤)다. 값은 다음 단계에서 고친다.
  · 항 이하는 제 깊이만큼 통째로 들여쓴다(항 2글자 · 호 4글자 · 목 6글자)
    ※ 실측 앞칸은 항 2 · 호 2 · 목 4 인데(앞칸은 반각 칸 — 1칸 0.5자라 1자·1자·2자다,
      '26-09-28 정정. 위 '2글자·4글자·6글자'는 그것을 글자 수로 읽은 옛 해석이다), 호가 항 없이 조 바로 아래 오는 문서가
      많아서 그렇다. 그래서 기호가 아니라 **JSON 안 깊이**로 들여쓴다 — 두 경우가
      다 맞게 나온다.
  · **규정번호·부칙 호/일자는 관행 꼴(제○○호)로 씌운다**(_번호꼴·_일자꼴, '26-09-27
    4차 벤치마크 진단) — 모델이 "규정번호": "○○" 처럼 틀 없이 자리표시만 내면 제목
    아래 뜻 없는 글자 한 줄만 남는다(심사 3인 전원 지적). 이미 "제…호" 꼴이면(실번호든
    자리표시든) 그대로 두고, 틀만 없으면 씌운다 — 값 자체는 검증하지 않는다.
  · **조문 본문은 낱말 단위로 줄바꿈한다**(word-break: keep-all, regulation.css) — 전에는
    글자 단위 줄바꿈(기본값)을 썼는데, "재/택근무", "승/인하여야"처럼 한 낱말이 줄 끝에서
    갈라졌다(심사 지적, 실측은 regulation.css 머리말 참고). 쪽수 증가는 여백을 줄여 상쇄한다.

게이트(gate_check)
  · 제1조가 있어야 한다(실측)
  · 조가 있어도 전부 본문(text)이 비어 있으면 하드('26-09-27 — 풀버전의 '장이 통째로
    비었다' 이탈과 같은 결. "조" 표제만 나열되고 조문 자체가 없으면 조가 있다는 형식만
    갖춘 빈 규정이다)
  · 부칙이 있어야 한다(실측)
  · 합니다체 금지(조문체 규범,(실측)

사용: python3 build/assemble_regulation.py build/regulation-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
import 표꼴
import 자료뿌리
try:
    # 방어적 import(low, '26-09-27 재진단) — 이 모듈은 미추적 새 파일이라 배포(git archive
    # HEAD 등 추적 파일만 싣는 절차)에서 커밋을 깜빡하면 빠질 수 있다. 여기서 죽으면 규정
    # 조립 전체(주요내용 없는 규정까지)가 ImportError 로 막힌다 — 없으면 정정 없이 그냥
    # 진행한다(gate_check 는 이 모듈과 무관하게 그대로 돈다).
    import 조번호꼴
except Exception:
    조번호꼴 = None
import html
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물은 **자료**다 — 어느 뿌리에 낼지는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# CSS·JS·프로파일은 코드라 BASE(코드뿌리) 그대로 둔다.
#
# ★ 산출물 뿌리를 모듈 적재 시점에 상수로 굳히지 않는다(WP-S9). import 로 부르면 모듈이
#   딱 한 번 적재돼 첫 세션 뿌리에 얼어붙고, 이후 모든 세션이 첫 세션 뿌리에 쓴다
#   (WP-S2 세션 오염). 뿌리는 `조립하기()` 가 **호출마다** 다시 푼다.

# 마커·표제 뒤 공백 — 양쪽맞춤이 늘리지 못하게 줄바꿈 없는 공백을 쓴다
NBSP = "&#160;"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
GANADA = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"
깊이 = {"장": 0, "절": 0, "조": 0, "항": 1, "호": 2, "목": 3}

_PROFILES = None


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
    """이 파일이 어느 기준으로 만들어졌는지 — 겉모습 해시에서는 빼고 센다."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "history"))
        import stamp
        # 속성 자리엔 잠금 없는 보간을 하나도 안 남긴다(assemble.기준도장 과 같은 이유)
        return f'<meta name="기준" content="{html.escape(stamp.조판지문("regulation"))}">'
    except Exception:
        return ""


def gate_check(doc):
    """규정이 규정 꼴을 갖췄는가. 실측에서 예외가 없던 것만 하드로 건다."""
    bad = []
    items = doc.get("본문")
    if not isinstance(items, list):
        # r10 검토자 발견(LOW, '26-09-27) — "본문": null·"본문": "문자열" 처럼 list 가
        # 아닌 값이 오면 .get 기본값([])은 명시 값이 있을 때 안 먹혀(dict.get 은 키가
        # 있으면 그 값을 그대로 준다), 아래 조들·조문체 루프가 이터레이션·인덱싱에서
        # TypeError 로 죽었다(NoneType 은 못 돌고, 문자열은 글자 단위로 돌아 it["level"]이
        # 문자열 인덱싱을 요구해 죽었다). 새 하드 위반을 적어 두고 빈 리스트로 갈음해
        # 아래를 안전하게 통과시킨다 — 이 문서는 어차피 "조가 하나도 없다"로도 막힌다.
        bad.append("본문이 목록이 아닙니다 — 조 항목 배열이어야 합니다")
        items = []
    조들 = [it for it in items if isinstance(it, dict) and it.get("level") == "조"]
    if not 조들:
        bad.append("조가 하나도 없다 — 규정은 조로 이루어진다(실측)")
    elif not any(str(it.get("text") or "").strip() for it in 조들):
        # 조 표제(제목)만 나열되고 조문 자체가 비면 형식만 갖춘 빈 규정이다(3차 측정,
        # 풀버전 '장이 통째로 비었다'와 같은 결의 이탈 — build/fullreport-docs.json·
        # regulation-docs.json 등 실측 표본은 조마다 text 가 있어 오탐이 없다).
        bad.append("본문 조에 내용이 없습니다 — 요약만으로는 규정이 아닙니다. "
                   "자료로 조문을 채우십시오")
    if not doc.get("부칙"):
        bad.append("부칙이 없다 — 시행일을 정하는 자리다(실측)")
    # 조문체 — 합니다체는 규정이 아니라 보고서·공문의 말투다
    for it in items:
        t = (it.get("text") or "").strip()
        if re.search(r"(습니다|합니다|입니다|바랍니다)\.?$", t):
            bad.append(f"합니다체 — 규정은 한다체로 쓴다: “{t[:34]}…”")
    return bad


def 번호매기기(items):
    """조·항·호·목 번호를 매긴다. 조는 문서 전체 통산, 항 이하는 부모마다 새로."""
    cnt = {"장": 0, "절": 0, "조": 0, "항": 0, "호": 0, "목": 0}
    out = []
    for i, it in enumerate(items):
        lv = it.get("level")
        if lv not in cnt:
            continue
        cnt[lv] += 1
        if lv == "장":
            cnt["절"] = 0
        if lv in ("장", "절", "조"):
            cnt["항"] = cnt["호"] = cnt["목"] = 0
        if lv == "항":
            cnt["호"] = cnt["목"] = 0
        if lv == "호":
            cnt["목"] = 0
        out.append((i, it, lv, cnt[lv]))
    return out


def 짜기(items):
    """자리마다 번호와 깊이를 정한다. 이름표가 아니라 **실제 층계**로 센다.

    두 가지를 이름표만 보고 정하면 틀린다.
      ① 조의 본문이 곧 제1항이다. 실물에 "조 본문 + 별도 ①" 은 없다 —
        "제5조(도구의 승인) ① 업무에 쓰는 도구는 …" 처럼 조 줄이 곧 첫 항이다.
        그래서 뒤에 항이 따라오면 조 본문에 ① 을 붙이고 다음 항은 ② 부터 센다.
        항이 안 따라오면 번호를 아예 안 붙인다("제8조(교육) 정보화 담당 부서는 …").
      ② 호가 항 없이 조 바로 아래 오는 규정이 많다. 그때 호는 항 자리(한 칸)에 선다.
        이름표로 "호=두 칸"이라고 박으면 그런 조가 통째로 밀린다.
        실측 앞칸이 항 2 · 호 2 · 목 4 로 나온 것이 바로 이 때문이다(앞칸은 반각 칸 수 — 0.5자 단위).

    낸다: {자리: {"번호": n, "깊이": d, "조본문항": bool}}
    """
    out = {}
    cnt = {"장": 0, "절": 0, "조": 0}
    항n = 호n = 목n = 0
    조자리 = None
    항있음 = False               # 이 조에서 항이 나온 적 있는가(호 깊이 판정용)
    for i, it in enumerate(items):
        lv = it.get("level")
        if lv in ("장", "절"):
            cnt[lv] += 1
            if lv == "장":
                cnt["절"] = 0
            out[i] = {"번호": cnt[lv], "깊이": 0}
            조자리, 항있음 = None, False
        elif lv == "조":
            cnt["조"] += 1
            항n = 호n = 목n = 0
            조자리, 항있음 = i, False
            out[i] = {"번호": cnt["조"], "깊이": 0}
        elif lv == "항":
            항있음 = True
            항n += 1
            호n = 목n = 0
            # 조 본문이 제1항이므로 뒤따르는 항은 ② 부터
            out[i] = {"번호": 항n + (1 if 조자리 is not None else 0), "깊이": 1}
        elif lv == "호":
            호n += 1
            목n = 0
            out[i] = {"번호": 호n, "깊이": 2 if 항있음 else 1}
        elif lv == "목":
            목n += 1
            out[i] = {"번호": 목n, "깊이": (3 if 항있음 else 2)}
        if 조자리 is not None and lv == "항":
            out[조자리]["조본문항"] = True
    return out


def _제정이유_정규화(v):
    """제정이유(선택키)는 산문 한 단락(문자열)이 정본 모양이다(온톨로지 예시도 문자열).
    모델이 배열로 낼 때도 있어 — 그때 문자열만 받으면 조용히 빠진다(3차 검토 결함) —
    이어 붙여 한 단락으로 받는다."""
    if isinstance(v, list):
        return " ".join(str(x).strip() for x in v if str(x).strip())
    return v.strip() if isinstance(v, str) else ""


def _주요내용_정규화(v):
    """주요내용(선택키)은 배열(문자열 목록)이 정본 모양이다. 항목이 하나뿐이면 모델이
    문자열 하나로 낼 때가 흔한데 — 그대로 돌면 글자 수만큼 가.나.다. 항목이 생긴다
    (3차 검토 결함) — [문자열]로 감싸 항목 하나로 받는다."""
    if isinstance(v, str):
        v = [v] if v.strip() else []
    return [str(x).strip() for x in (v or []) if str(x).strip()]


# 제목 아래 규정번호·부칙 호가 관행 꼴(제○○호)을 갖췄는가('26-09-27, 4차 벤치마크
# 진단) — 모델이 자리표시를 "○○" 한 낱말로만 내면(실물 규정 관행인 "제○○호" 틀 없이)
# 뜻 없는 글자 한 줄만 남는다(front-s4 심사 3인 모두 지적: "제목 아래 뜻 없는 '○○'").
# 이미 "제…호" 꼴을 갖췄으면(실제 번호든 자리표시든) 그대로 두고, 틀만 없으면 씌운다 —
# 값 자체를 검증하지 않는다(규정번호는 자유 문자열이라 "제2026-3호"처럼 가운데 부호가
# 있어도 "제"…"호" 사이만 확인하면 충분하다).
_제호패턴 = re.compile(r"제\s*\S*?호")


def _번호꼴(v):
    v = (v or "").strip()
    if not v or _제호패턴.search(v):
        return v            # 빈 값은 그대로(호출부가 아예 줄을 안 그린다) · 이미 관행 꼴
    return f"제{v}호"


# 부칙 일자가 통짜 자리표시(○ 만, 실제 숫자 없음)면 날짜 자리가 드러나는 꼴로 감싼다 —
# kordoc 표본(front-s4 expert 심사, "부칙 <제○○호, ○○○○. ○. ○.>")이 감점 없이
# 받은 실측 관행 꼴을 그대로 따른다. 이미 숫자가 있는 실제 일자는 건드리지 않는다.
_일자자리표시전부 = re.compile(r"^[○\s]+$")


def _일자꼴(v):
    v = (v or "").strip()
    if v and _일자자리표시전부.match(v):
        return "○○○○. ○. ○."
    return v


def _표시속성(원값, 표시값):
    """_번호꼴·_일자꼴 이 값을 바꿨을 때만 data-orig·data-shown 을 잎에 단다('26-09-27
    재검토 발견, medium) — 안 달면 편집기가 사람 손을 안 댄 문서도 저장하는 순간 표시
    글자("제○○호")를 정본으로 되쓴다(render_editor_any.py:1659 serialize() 의
    data-path 잎 글자 그대로 되쓰기 규범). data-orig 가 있으면 그 자리는 대신 "화면
    글자가 data-shown 과 같으면 안 고친 것 — data-orig(원래 자리표시)를 저장하고,
    다르면 사람이 고친 새 글자를 저장한다"는 이미 있던 왕복 규범을 탄다(지금까지 이
    자리를 채우는 조립기가 없었을 뿐이다). 안 바뀐 값(이미 관행 꼴·빈 값)은 그대로
    두어 이 속성 자체가 안 실린다 — 실측 표본 대다수가 여기 해당한다(test C 회귀)."""
    if 원값 == 표시값:
        return ""
    return f' data-orig="{html.escape(원값)}" data-shown="{html.escape(표시값)}"'


def 머리기관겹침(doc):
    """제명이 기관명으로 시작하는가(띄어쓰기 무시) — 그러면 머리 기관 칸을 되풀이하지 않는다(reg12 '26-09-30 판정
    B-H3: 제정안 제명 '○○공사 보안 점검 지침 제정(안)'에 머리 '○○공사'가 한 번 더 붙어 '○○공사 | ○○공사 …'로 보였다).
    HTML 은 기관 칸을 숨기고(값·편집 자리는 남긴다 — 저장은 그대로), md 머리(tomd)도 같은 규칙으로 기관 줄을 뺀다.
    <title> 은 늘 제명만 쓴다(기관명을 붙이지 않으니 겹치지 않는다)."""
    # reg12 fixup(verify.md L2) — 제명이 「」·『』로 시작해도('「○○공사 보안 점검 지침」 제정안') 겹침이다: 낫표는 떼고 견준다.
    기관 = re.sub(r"[\s「」『』]", "", str(doc.get("기관명") or ""))
    제명 = re.sub(r"[\s「」『』]", "", str(doc.get("제명") or ""))
    return bool(기관) and 제명.startswith(기관)


def build(doc):
    # '확인요청'(reg13d 판정 D1, '26-10-01) — 작성 모델이 스스로 정한 것을 적는 칸이다. 새문서가 확인 물음으로 옮기고 등록 전에
    # 떼지만, 칸이 남아 들어와도 조립기는 그리지 않고 편집기 문서 사본(fr-doc)에도 싣지 않는다(모르는 키로 걷는다).
    if isinstance(doc, dict) and "확인요청" in doc:
        doc = {k: v for k, v in doc.items() if k != "확인요청"}
    DOC_JSON = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    PROFILE_JSON = json.dumps(load_profile("regulation"),
                              ensure_ascii=False).replace("</", "<\\/")
    e = html.escape
    m = doc.get("여백_mm") or {}
    스타일 = ""
    if isinstance(m, dict) and m:
        # 여백은 밀리미터 숫자 하나(build/속성값.py) — assemble_gongmun 과 같은 자리다
        쪽 = []
        for 변수, 키 in (("t", "상"), ("r", "우"), ("b", "하"), ("l", "좌")):
            폭 = 속성값.수(m.get(키), f"여백_mm.{키}", 최소=0, 최대=200)
            if 폭 is not None:
                쪽.append(f"--rg-m{변수}:{폭}mm")
        스타일 = (' style="' + ";".join(쪽) + '"') if 쪽 else ""
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="regulation"{스타일}>
<head>
<meta charset="utf-8">{기준도장()}
<title>{e(doc.get("제명", ""))}</title>
<link rel="stylesheet" href="../tokens.css?v=">
<link rel="stylesheet" href="../regulation.css?v=">
</head>
<body>
<script type="application/json" id="fr-doc">{DOC_JSON}</script>
<script type="application/json" id="fr-profile">{PROFILE_JSON}</script>
<div class="rg-sheet">
  <div class="rg-head">
    <div class="rg-org" data-ent="머리" data-path="기관명"{' hidden data-dup="제명"' if 머리기관겹침(doc) else ''}>{e(doc.get("기관명", ""))}</div>
    <h1 class="rg-title" data-ent="제명" data-path="제명">{e(doc.get("제명", ""))}</h1>
    <div class="rg-no" data-ent="머리" data-path="규정번호"{_표시속성(doc.get("규정번호", ""), _번호꼴(doc.get("규정번호", "")))}>{e(_번호꼴(doc.get("규정번호", "")))}</div>
  </div>
  <div class="rg-body">
"""]
    # ── 제정이유·주요내용(선택키, '26-09-26 벤치마크 진단) — 제명과 제1조 사이, 조 번호 없이 산문·목록으로.
    # 법제처 입법예고 관행(구성.선택키._전거) — 없으면 지금처럼 제1조부터 바로 시작한다(회귀 없음).
    제정이유 = _제정이유_정규화(doc.get("제정이유"))
    if 제정이유:
        # data-ent 도 data-path 와 같이 **잎**에 건다(4차 검토, assemble:F6) — 컨테이너
        # div 에 걸었더니 클릭 드릴다운이 div 를 고르고, '표제(h2)는 개체 밖'이라는 아래
        # 238행 주석과 달리 _ai대상 이 div.innerText(표제 '제정이유' 글자까지 섞임)를
        # 원문으로 보내 AI 재작성 결과를 div.textContent 로 대입 — h2 표제와 잎 p 가
        # 함께 지워지고, serialize 는 [data-path] 잎만 찾으므로 저장에는 반영조차 안 된
        # 채 표제 글자만 화면에서 사라졌다. div 에는 data-ent 를 두지 않아 클릭이 곧장
        # 잎으로 떨어지게 한다 — h2 표제는 그대로 "개체 밖"에 남는다.
        parts.append(f'    <div class="rg-reason">'
                     f'<h2 class="rg-reason-h">제정이유</h2>'
                     f'<p class="rg-reason-tx" data-ent="제정이유" data-path="제정이유">{e(제정이유)}</p></div>\n')
    주요내용 = _주요내용_정규화(doc.get("주요내용"))
    if 주요내용:
        항목들 = "".join(
            f'<p class="rg-주요내용-i" data-ent="주요내용"><span class="mk-h">'
            f'{e(GANADA[i % len(GANADA)])}.</span><span class="sp">{NBSP}</span>'
            f'<span class="tx" data-path="주요내용.{i}">{e(x)}</span></p>'
            for i, x in enumerate(주요내용))
        parts.append(f'    <div class="rg-주요내용">'
                     f'<h2 class="rg-주요내용-h">주요내용</h2>{항목들}</div>\n')
    items = doc.get("본문", [])
    자리표 = 짜기(items)
    # 경로는 **잎**에 건다. 마커까지 품은 컨테이너에 걸면 저장할 때
    # "제1장 총칙" 이 통째로 제목 값이 되어 왕복이 깨진다(이 프로젝트의 1번 함정).
    for i, it in enumerate(items):
        # level 은 class·data-ent 두 속성으로 들어간다 — 열거값이라고 **자리에서**
        # 못 박는다. 값 집합은 위 `깊이` 표 하나에서 세어 온다(손목록 금지).
        # 지금도 짜기() 가 모르는 level 을 걸러 내지만, 그 방어는 여기서 안 보인다 —
        # 걸러 내는 자리와 속성에 싣는 자리가 떨어져 있으면 언젠가 어긋난다.
        lv = 속성값.열거(it.get("level"), tuple(깊이), f"본문.{i}.level")
        z = 자리표.get(i)
        if not z:
            continue
        p = f"본문.{i}"
        n, 깊 = z["번호"], z["깊이"]
        if lv in ("장", "절"):
            parts.append(f'    <h2 class="rg-{lv}" data-ent="장절">'
                         f'<span class="mk">제{n}{lv}</span>{NBSP}'
                         f'<span class="tx" data-path="{p}.제목">{e(it.get("제목", ""))}</span>'
                         f'</h2>\n')
        elif lv == "조":
            머리 = f'<span class="mk">제{n}조</span>'
            if it.get("제목"):
                # 괄호는 조판이고 값은 제목뿐이다 — 괄호를 span 밖에 둔다
                머리 += f'(<span class="ttl" data-path="{p}.제목">{e(it["제목"])}</span>)'
            # 표제와 본문 사이 공백은 CSS 여백이 아니라 **글자**로 넣는다.
            # 여백만 주면 화면은 맞아도 복붙하면 "제1조(목적)이 규정은…" 으로 붙는다.
            머리 += NBSP
            # 뒤에 항이 따라오면 이 본문이 제1항이다 — ① 을 붙인다
            if z.get("조본문항"):
                머리 += '<span class="mk-h">①</span>' + NBSP
            parts.append(f'    <p class="rg-조" data-ent="조">{머리}'
                         f'<span class="tx" data-path="{p}.text">{e(it.get("text", ""))}</span>'
                         f'</p>\n')
        else:
            기호 = (CIRCLED[(n - 1) % len(CIRCLED)] if lv == "항"
                  else f"{n}." if lv == "호"
                  else f"{GANADA[(n - 1) % len(GANADA)]}.")
            # 기호 뒤 공백은 글자(NBSP)로 두되 고정 폭 칸(.sp)에 담는다('26-09-28) — 맨 글자면
            # 양쪽맞춤이 첫 줄에서 그 공백을 늘려(실측 최대 3mm) 목(가.)의 둘째 줄을 첫 줄 글에
            # 맞출 수 없었다. 글자는 그대로라 복붙·HWPX 에서 기호와 글이 붙지 않는다.
            parts.append(f'    <p class="rg-{lv}" data-d="{깊}" data-ent="{lv}">'
                         f'<span class="mk-h">{e(기호)}</span><span class="sp">{NBSP}</span>'
                         f'<span class="tx" data-path="{p}.text">{e(it.get("text", ""))}</span>'
                         f'</p>\n')

    # ── 부칙 —(실측). 시행일을 정하는 자리라 규정의 필수 부분이다
    for bi, b in enumerate(doc.get("부칙", [])):
        # 부칙 머리 '<○○, ○○>' 는 번호·날짜 자리가 드러나지 않는다('26-09-27, 4차
        # 벤치마크 진단) — 위 규정번호와 같은 이유로 관행 꼴을 씌운다(_번호꼴·_일자꼴).
        호원, 일자원 = b.get("호", ""), b.get("일자", "")
        호값, 일자값 = _번호꼴(호원), _일자꼴(일자원)
        머리 = '<h2 class="rg-부칙" data-ent="부칙">부칙'
        if 호값 or 일자값:
            머리 += ' &lt;'
            if 호값:
                머리 += (f'<span class="tx" data-path="부칙.{bi}.호"'
                        f'{_표시속성(호원, 호값)}>{e(호값)}</span>')
            if 일자값:
                머리 += (", " if 호값 else "")
                머리 += (f'<span class="tx" data-path="부칙.{bi}.일자"'
                        f'{_표시속성(일자원, 일자값)}>{e(일자값)}</span>')
            머리 += '&gt;'
        parts.append("    " + 머리 + "</h2>\n")
        for li, line in enumerate(b.get("본문", [])):
            parts.append(f'    <p class="rg-부칙문" data-ent="부칙">'
                         f'<span class="tx" data-path="부칙.{bi}.본문.{li}">{e(line)}</span></p>\n')

    # ── 별표 — 수치·목록은 본문에 안 넣고 여기로 뺀다(실측 표 중앙값 0)
    for ti, t in enumerate(doc.get("별표", [])):
        # 별표 번호는 **본문 자리**인데 escape 를 빠뜨리고 있었다(속성 자리를 훑다
        # 같이 나왔다, 2026-08-07). `번호` 에 `<img src=x onerror=…>` 를 넣으면
        # 그대로 태그가 됐다 — 크롬 실측으로 __pwn 전역이 오염됐다.
        parts.append(f'    <h2 class="rg-별표" data-ent="별표">'
                     f'[별표 {e(str(t.get("번호", ti + 1)))}] '
                     f'<span class="tx" data-path="별표.{ti}.제목">{e(t.get("제목", ""))}</span>'
                     f'</h2>\n')
        tb = t.get("표") or {}
        if tb:
            # '26-09-29 표 재설계 P1: 표 몸은 build/표꼴.py 공용(열폭·열정렬·머리·첫열·병합·강조·모양)
            parts.append(f'    <div class="rg-table-wrap" data-ent="표" '
                         f'data-path="별표.{ti}.표">{표꼴.표html(tb, "rg-table")}</div>\n')

    parts.append("""  </div>
</div>
<script>
/* 소량 넘침 당기기('26-09-27, 4차 벤치마크 진단) — "3쪽에 제11조와 부칙만 3줄
   남는다"(심사 지적, front-s4) 같은 경우, 마지막 쪽에 몇 줄만 걸치면 --rg-tighten
   (줄간격·여백 배율)을 살짝 낮춰 그 쪽 자체를 없앤다. fullreport 의 쪽 압축(보정1)과
   같은 목적이지만, 규정·보도자료는 쪽마다 DOM 이 갈라지지 않는(브라우저가 인쇄 때
   스스로 지면을 나누는) 연속 흐름이라 **쪽 하나만 콕 집어** 조이지 못한다 — 대신
   문서 전체에 같은(작은) 배율을 걸어 같은 효과를 낸다. 넘침이 많으면(대략 쪽 하나의
   15% 넘게 넘치면) 손대지 않는다 — "몇 줄"이 아니라 진짜 여러 쪽짜리 문서를 억지로
   구기지 않기 위해서다.

   **안전배율(0.95)** — 이 스크립트는 화면(스크린) 배치에서 잰 mm 로 인쇄 쪽수를
   미리 내다본다. 실측(test/r11_asm11.py, 합성 표본으로 경계를 좁혀 잰 결과, '26-09-27):
   화면에서 "이 배율이면 2쪽에 든다"고 잰 값이 실제 --print-to-pdf 결과와 어긋난 적이
   있다 — 화면 재기는 493.7mm(경계 494mm 바로 아래, 여유 0.3mm)로 2쪽을 장담했지만
   실제 인쇄는 3쪽으로 나왔다(더 낮춘 476mm 도 아직 3쪽, 467mm 에서야 2쪽 — 실제
   여유가 화면 계산보다 한 쪽당 대략 7~9mm 작았다). 여러 줄에 걸쳐 화면·인쇄 사이 아주
   작은 줄높이 반올림 차이가 쌓인 것으로 보인다(정확한 근원은 특정하지 않았다 — 아래
   안전배율로 흡수한다). 그래서 "쪽 하나가 사라졌다"를 **빠듯하게** 확인하지 않고,
   계산상 그 쪽 용량의 95% 안에 들 때만 성공으로 친다 — 실제 인쇄가 화면 계산보다
   더 필요로 해도 여유가 남는다. 그래도 안 되면(범위 끝까지 못 미치면) 원래대로
   둔다 — 확신 없이 압축하느니 안 건드리는 쪽이 안전하다. */
(() => {
  const sheet = document.querySelector('.rg-sheet');
  if (!sheet) return;
  const 문서 = document.documentElement;
  const PXPERMM = 96 / 25.4;                    // CSS 규격 고정값(1in=96px=25.4mm) — 매체 무관
  const 안전배율 = 0.95;                         // 화면 재기 ≠ 실제 인쇄 오차를 흡수하는 여유(위 주석 실측)
  function 재기() {
    // padding-top/bottom 을 **지금 매체 그대로** 읽는다 — 화면에서는 .rg-sheet 의
    // padding(위·아래 여백 한 벌)이 총 높이에 이미 들어 있고, 인쇄 매체에서는
    // 0(@page 가 대신 낸다) 이라 총 높이가 곧 순수 내용 높이다. 둘 다 이 한 식으로 맞다.
    const cs = getComputedStyle(sheet);
    const 패딩mm = ((parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0)) / PXPERMM;
    // .rg-sheet 의 **화면 전용** min-height(297mm, regulation.css)가 한 쪽이 채 안
    // 되는 문서의 내용mm 를 부풀린다('26-09-27 재검토 발견, medium) — 인쇄 매체는
    // min-height:auto(위 @media print)라 이 부풀림이 없는데, 화면(이 스크립트가
    // 재는 매체)만 그렇다. 재는 순간만 지운다 — 인라인 스타일이 클래스 규칙보다
    // 우선하고, 읽자마자 되돌려 실제 배치(사람 눈)엔 아무 티도 안 난다.
    const 원래최소높이 = sheet.style.minHeight;
    sheet.style.setProperty('min-height', '0px');
    const 내용mm = sheet.scrollHeight / PXPERMM - 패딩mm;
    if (원래최소높이) sheet.style.setProperty('min-height', 원래최소높이);
    else sheet.style.removeProperty('min-height');
    const rs = getComputedStyle(문서);
    const 상 = parseFloat(rs.getPropertyValue('--rg-mt')) || 0;
    const 하 = parseFloat(rs.getPropertyValue('--rg-mb')) || 0;
    return { 내용mm, 쪽높이mm: 297 - 상 - 하 };
  }
  function 시도() {
    문서.style.removeProperty('--rg-tighten');    // 매번 배율 1(원래 조판)에서 다시 잰다
    const { 내용mm, 쪽높이mm } = 재기();
    if (쪽높이mm <= 0) return;
    const 쪽수 = Math.ceil(내용mm / 쪽높이mm);
    if (쪽수 < 2) return;                          // 한 쪽뿐이면 당길 것이 없다
    const 남는것mm = 내용mm - (쪽수 - 1) * 쪽높이mm;   // 마지막 쪽에 걸친 분량
    if (남는것mm > 쪽높이mm * 0.15) return;          // 소량(몇 줄)이 아니면 그대로 둔다
    for (let s = 0.99; s >= 0.90 - 1e-9; s -= 0.01) {
      문서.style.setProperty('--rg-tighten', s.toFixed(2));
      const 잰것 = 재기();
      // 쪽 하나가 (안전배율만큼 여유 있게) 사라졌다 — 이 배율로 둔다
      if (잰것.내용mm <= (쪽수 - 1) * 잰것.쪽높이mm * 안전배율) return;
    }
    문서.style.removeProperty('--rg-tighten');      // 최대(10%)까지 줄여도 안 되면 원복 — 억지로 안 구긴다
  }
  // **글꼴이 실제로 앉기 전(대체 글꼴)에는 화면 높이가 달라진다** — 실측(합성 표본으로
  // 경계를 좁혀 재현, '26-09-27): 대체 글꼴로 잰 내용 높이가 최종 글꼴보다 더 커서
  // (한 사례에서 22.8mm 더 큼) '넘침이 15%보다 많다'며 아예 시도조차 안 하고 넘어간
  // 적이 있다 — 최종 글꼴로 다시 재면 그 문서는 원래 소량 넘침(당길 수 있는 경우)
  // 이었다. jachigan.js 와 같은 이유로 글꼴 로드 뒤 한 번 더 재야 한다.
  function run() {
    시도();
    if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(시도);
  }
  if (document.readyState === 'complete') run(); else window.addEventListener('load', run);
})();
</script>
<script src="../jachigan.js?v="></script>\n<script src="../audit.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


def 조립하기(등록부경로, only=None, out=None, 정정=True, 저장=False):
    """자치법규 등록부 → HTML. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 게이트 위반 문서는 안
    쓰고 ok=False 가 된다. 산출물뿌리를 **호출마다** 다시 푼다(세션 오염 방지).
    `out` 을 주면(=--out) 그 자리로 뽑는다.

    `정정`(기본 True) — False 면 조번호꼴.맞추기 를 건너뛴다. **저장(편집 반영) 뒤
    재조립에서는 False 로 부른다**(main() 의 --저장 참고, workspace/apply_edit_any.py
    가 doc 재조립마다 이 깃발을 단다) — 이 함수는 새문서(첫 조립)와 저장(재조립) 둘
    다에서 subprocess 로 불리는 **같은 진입점**인데, 맞추기가 여기서 항상 돌면 사람이
    편집기에서 손으로 고친 조 번호를 저장할 때마다 되돌린다(회귀 근거는 조번호꼴.py
    머리 docstring). 새문서는 이미 workspace/api.py 의 새문서() 가 등록 **전에**
    조번호꼴.맞추기 를 직접 불러 doc 를 고쳐 두므로(등록부에 정정된 값이 그대로
    쓰인다), 여기서 또 부르지 않아도 첫 조립부터 정정된 번호가 그대로 실린다.

    `저장`(기본 False) — True 면 gate_check 의 "본문 조에 내용이 없습니다"(내용 결손)
    위반만 소프트 경고로 낮춘다(assemble_full·assemble_slides 의 같은 인자와 같은 취지,
    r10 사후검토 발견 medium) — 이미 등록된(빈 조문) 문서를 저장할 때 등록부(JSON)는
    편집이 반영됐는데 HTML 은 재조립 실패로 옛 채로 남는 어긋남을 막는다. `정정`과는
    별개 인자다(둘 다 main() 에서 같은 --저장 CLI 깃발로 세팅되지만 뜻이 다르다) —
    "조가 하나도 없다"(기존 하드)는 저장 때도 그대로 막는다(내용 결손과 결이 다른,
    구조 자체가 없는 흠이라 무관한 편집을 핑계로 눈감지 않는다)."""
    낼곳 = out if out else 자료뿌리.산출물뿌리()   # 호출마다 세션 뿌리를 다시 푼다
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    # 한 건만 다시 만들 수 있다(`--only <문서키>`, WP-S2 ②) — 세션 안에서 문서
    # 하나를 저장할 때 나머지 문서 파일까지 다시 쓰지 않으려고. 판정은 genres 한 곳.
    docs = genres.한건만(docs, ["--only", only] if only else [])
    fail = 0
    낸것, 로그 = [], []
    for doc in docs:
        # 조번호꼴.맞추기 는 gate_check 보다 먼저 돈다 — 주요내용의 괄호 조 인용이 본문과
        # 어긋나는 것은 게이트가 잡는 위반이 아니라(온톨로지 예시가 번호를 문장에 박아
        # 넣도록 가르쳐 놓고 대조하는 코드가 없던 공백이다, map-fix-sites.md A) 여기서
        # 바로잡는다. 바뀐 게 있으면 슬라이드 소프트 경고와 같은 표기로 알린다(하드 위반이
        # 아니다 — 문서는 그대로 나간다). `정정=False`(저장 재조립)면 아예 건너뛴다.
        if 정정 and 조번호꼴:
            바뀜 = 조번호꼴.맞추기(doc)
            if 바뀜:
                로그.append(f"[소프트 경고] {doc['filename']}")
                for w in 바뀜:
                    로그.append(f"  ! 주요내용 조번호 정정: {w}")
        bad = gate_check(doc)
        if 저장 and bad:
            연성 = [b for b in bad if b.startswith("본문 조에 내용이 없습니다")]
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
        fn = f"{doc['filename']}.html"
        with 자료뿌리.쓰기(os.path.join(낼곳, fn)) as f:      # 원자 쓰기(WP-S2 ③)
            f.write(genres.판찍기(build(doc)))
        낸것.append(fn)
        로그.append(f"built: {fn}")
    return {"ok": fail == 0, "낸것": 낸것, "로그": "\n".join(로그)}


def main():
    # --out DIR 로 다른 곳에 뽑을 수 있다(history/stamp.py). 정본을 안 건드리고 뽑는다.
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    # --저장 — apply_edit_any.py 가 저장(편집 반영) 뒤 재조립할 때만 붙인다(조립하기()
    # docstring 참고). 다른 장르 조립기도 같은 깃발을 받지만 모르는 옵션은 위 줄에서
    # 이미 걸러졌으니 이 파일만 뜻을 준다. 정정=False 와 저장=True 는 같은 깃발에서
    # 나온 서로 다른 두 뜻이다(위 조립하기 docstring).
    저장플래그 = "--저장" in sys.argv
    본 = 조립하기(argv[0], only=only, out=out, 정정=(not 저장플래그), 저장=저장플래그)
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
