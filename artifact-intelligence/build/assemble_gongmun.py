#!/usr/bin/env python3
"""시행문(공문) 조립기 — JSON → 시행문 HTML. 체계B 마커 자동 부여 + 시행문 게이트 내장.

문서 JSON 스키마(build/gongmun-docs.json — 배열):
{
  "filename": "gm-…", "genre": "gongmun",
  "슬로건": "", "기관명": "…", "수신": "수신자 참조 | 내부결재 | …", "경유": "",
  "제목": "…",
  "본문": [ {"level": 1~6, "text": "서술문 또는 개조식 세부"} … ],   ← 마커는 넣지 않는다(자동)
  "붙임": ["… 1부."] | [],
  "발신명의": "…", "관인생략": true|false,
  "수신자란": "수신자 참조이고 수신처가 둘 이상일 때만 나열(하나면 조립기가 '수신' 칸에 그 기관명을
    바로 적고 이 자리는 비운다 — 구성.수신.단일수신, '26-09-26)",
  "메타": {"기안자":"", "시행":"부서명-", "시행일":"", "주소":"", "전화":"", "내선":"", "팩스":"",
          "이메일":"", "공개":"…"}
}
메타 빈값 원칙: 시행번호·결재선 서명·접수 등 전자결재가 채우는 자리는 빈 칸으로 남긴다(실사용 시 채움).
다만 연락처(전화·내선·전자우편)는 자료에 있으면 그대로 채운다(디자인.메타_빈값원칙, '26-09-26 — 예전엔
이 구분 없이 통째로 비워 자료에 있던 내선번호까지 지워졌다). 결문의 빈 조각(시행일 없는 "( )",
값 없는 "전화 /전송 /" 등)은 구분자째 감춘다(render 가 처리).

게이트(온톨로지 document_types.gongmun.게이트):
- 본문 필수(하드, '26-09-27) — 항목이 없거나 전부 text 가 비어 있으면(표 항목은 별도) 막는다.
  풀버전의 '장이 통째로 비었다' 이탈과 같은 결이다.
- 발신명의 필수(하드) / 공손체 종결(level 1·2 서술문 '…다.' 완결, ~요망·~바람·~할 것 금지)
- 끝표시 규칙은 조립기가 기계 집행(붙임 유무에 따라 위치 자동)

사용: python3 build/assemble_gongmun.py build/gongmun-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
try:
    # 방어적 import(low, '26-09-27 재진단) — 미추적 새 파일이라 배포에서 커밋을 깜빡하면
    # 빠질 수 있다. 없으면 붙임 분리 없이 그냥 진행한다(gate_check 의 붙임 힌트 메시지는
    # 이 모듈과 무관하게 그대로 돈다 — 사람이 직접 최상위 붙임 배열로 옮겨야 한다는 안내만 남는다).
    import 붙임꼴
except Exception:
    붙임꼴 = None
import 수신꼴
import 표꼴
import 자료뿌리
import html
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물은 **자료**다 — 어느 뿌리에 낼지는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# CSS·JS·프로파일은 코드라 BASE(코드뿌리) 그대로 둔다.
# ★ 산출물 뿌리를 모듈 적재 시점에 상수로 굳히지 않는다(WP-S9). import 로 부르면 모듈이
#   딱 한 번 적재돼 첫 세션 뿌리에 얼어붙고, 이후 모든 세션이 첫 세션 뿌리에 쓴다
#   (WP-S2 세션 오염). 뿌리는 `조립하기()` 가 **호출마다** 다시 푼다.

GANADA = "가나다라마바사아자차카타파하"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

# 메타 값 방어형 변환(assemble:F6) — 우편번호처럼 원래 숫자인 값을 자료·모델이 정수로 낼 수
# 있다. .strip()·html.escape 는 str 만 받으므로 int·None 이 그대로 들어오면 조립 전체가
# AttributeError 로 죽는다(문서 한 건이 등록부 나머지까지 막는다). None 은 빈 문자열로,
# 그 밖의 값은 str() 로 감싼다(assemble_press.py 의 _s 와 같은 패턴).
def _s(x):
    return "" if x is None else str(x)


def _우편번호꼴(x):
    """우편번호는 대한민국 우편번호 체계상 5자리 고정이다. 정수로 오면 앞자리 0 이 이미
    사라진 상태다(JSON 은 0 으로 시작하는 수를 못 받는다 — 자료·모델이 03154 를 3154 로
    흘린 뒤에야 여기 닿는다) — 방어적으로 5자리를 맞춘다. bool 은 제외한다(True/False 가
    1/0 으로 새는 사고를 막는다, _s 와 같은 경계). 문자열로 오면 이미 자리가 맞다고 보고
    손대지 않는다. 범위 밖 정수·그 밖의 값은 기존처럼 str() 로만 감싼다(assemble:R7-04,
    '26-09-27 — severity 는 낮다: 스키마 밖 곁길이고, 모델 출력은 엄격한 json.loads 를
    거쳐 애초에 03154 꼴을 못 받으므로 이 경로는 입력이 이미 0 을 잃은 뒤에만 열린다)."""
    if isinstance(x, bool):
        return _s(x)
    if isinstance(x, int) and 0 <= x < 100000:
        return f"{x:05d}"
    return _s(x)


def marker(level, idx):
    """체계B 기호: 1. 가. 1) 가) (1) (가) ① (편람 구-11)."""
    if level == 1:
        return f"{idx}."
    if level == 2:
        return f"{GANADA[idx-1]}."
    if level == 3:
        return f"{idx})"
    if level == 4:
        return f"{GANADA[idx-1]})"
    if level == 5:
        return f"({idx})"
    if level == 6:
        return f"({GANADA[idx-1]})"
    return CIRCLED[idx - 1]


def em_width(s):
    """마커+1타의 폭(em) 추정 — 행잉 인덴트용."""
    w = 0.0
    for ch in s:
        w += 0.55 if ch.isascii() else 1.0
    return round(w + 0.5, 2)  # +1타(반각 공백)


FORBIDDEN_END = re.compile(r"(요망|바람|할\s?것)\s*[.]?\s*$")
POLITE_END = re.compile(r"(다\.)\s*$")
# '관련: 「…」 제N조(…)'·'문의: …(내선 1234)'처럼 <표지어>: <내용> 꼴로 여는 항목은 공문 관행상
# 명사형(서술어 미완결)이 정상이다. 예전엔 이 꼴도 1. 수준이면 '다.' 종결을 강제해 근거줄·문의처
# 표기를 되돌렸다(writing_profiles.gongmun-gyeoksik.종결.표지어_예외, '26-09-26 벤치마크 진단).
#  첫 글자를 한글로 묶는다 — 숫자로 시작하는 앞부분(예: '14:00부터…', '1:1 면담으로…')까지
#  '<표지어>:' 로 잘못 봐, 서술어 완결('…다.') 하드 게이트를 시각·비율 표현이 빠져나가던
#  결함을 고쳤다(2차 검토). 허용 표지어는 '관련:'·'문의:' 처럼 한글 낱말로 시작한다.
LABEL_ITEM = re.compile(r"^(?!\d)[가-힣][가-힣A-Za-z0-9·/()「」]{0,13}\s*[:：]")
# '붙임'으로 시작하는데 build/붙임꼴.py 의 분리하기() 가 옮기지 못한 나머지(예: '부.' 종결이
# 없는 낯선 변형) — gate_check 가 이걸 만나면 "서술어 완결 아님"이라는 원인 불명 메시지 대신
# 최상위 붙임 배열로 옮기라는 구체적 지시를 낸다(map-fix-sites.md C, bench3 qwen-s3 실패 로그
# 의 반복 반려 원인 — 모델이 원인을 못 알아듣고 '…다.'로 고쳐 쓰려다 매번 다시 걸렸다).
# \b 는 "붙임1"처럼 라벨 뒤에 바로 숫자가 붙으면 안 걸린다(둘 다 \w 라 경계가 안 생긴다,
# low — review34/bu_adv.py '붙임1-nospace' 실측) — 뒤에 공백·숫자·마침표·콜론이 오거나
# 줄이 그대로 끝나면 걸리게 넓힌다.
_붙임비슷 = re.compile(r"^\s*(?:※\s*)?붙임(?:\s|\d|[.:：]|$)")


# 받는 기관의 급에 따라 맺음말을 달리 한다('26.7.30. 실무자 판정).
# 온톨로지 writing_profiles.gongmun-gyeoksik.수신자_급별_종결 과 같은 표다.
급별_종결 = {
    "상급기관": (r"(보고|제출)합니다", "상급기관에는 '보고합니다/제출합니다'로 맺습니다"),
    "대등기관": (r"(협조|회신|검토)하여\s*주시기\s*바랍니다|주시기\s*바랍니다",
             "대등기관에는 '협조하여 주시기 바랍니다'류로 맺습니다"),
    "하급기관": (r"하(시기|여\s*주시기)\s*바랍니다", "하급기관에는 '하시기 바랍니다'류로 맺습니다"),
}


def gate_check(doc):
    """시행문 게이트 — 위반 목록 반환(하드)."""
    bad = []
    # 본문 — 항목이 없거나 전부 text 가 비어 있으면(표 항목은 별도로 친다) 요약만 있고
    # 알맹이가 없는 시행문이다('26-09-27, 풀버전의 '장이 통째로 비었다' 이탈과 같은 결 —
    # 실측 표본 gongmun-docs.json 사례·bench2/3 사례은 모두 본문이 있어 오탐이 없다).
    본문 = doc.get("본문")
    본문없음 = not isinstance(본문, list) or not any(
        isinstance(it, dict) and (("표" in it) or str(it.get("text") or "").strip())
        for it in 본문
    )
    if 본문없음:
        bad.append("본문이 비어 있습니다 — 시행문은 본문 항목(서술문)이 있어야 합니다. "
                   "자료로 내용을 채우십시오")
    if not isinstance(본문, list):
        # r10 검토자 발견(LOW, '26-09-27) — "본문": null·"본문": "문자열" 은 위 하드
        # 위반에 이미 잡혔는데도, 아래 급별 종결·서술어 검사가 doc.get("본문", [])로
        # 다시 읽어(키가 있으면 .get 기본값이 안 먹는다) None 은 못 돌고 문자열은 글자
        # 단위로 돌아 it["level"] 인덱싱에서 TypeError 로 죽었다. 위에서 이미 하드로
        # 막았으니 여기서 그만 돌려 아래 루프들이 안전하게 스킵되게 한다.
        return bad
    # 발신명의는 서명 때 한글에서 채우는 자리라 **초안에서 비어 있는 게 정상**이다(워크셋도
    # '빈자리로'). 예전엔 여기서 하드 거부해 초안·HWPX 를 통째로 막았다(코덱스·커서 교차
    # 테스트 지적, 2026-08-24). 이제 막지 않고 render 가 '(발신 명의 — 서명 시 기입)' 자리표시자를
    # 넣는다 — 필수 입력 되묻기는 에이전트(SKILL)의 몫이고, 게이트는 형식상 흠을 막기보다
    # 초안이 나가게 두는 초안 도구의 규범을 따른다.
    # 급을 밝힌 문서만 검사한다. 안 밝히면 '하시기 바랍니다'가 기본이라 따로 볼 것이 없다.
    급 = doc.get("수신기관급")
    if 급 in 급별_종결:
        pat, hint = 급별_종결[급]
        본문 = [it for it in doc.get("본문", []) if "표" not in it]
        마지막 = 본문[-1]["text"].strip() if 본문 else ""
        if 마지막 and not re.search(pat, 마지막):
            bad.append(f"수신이 {급}인데 맺음말이 맞지 않습니다 — {hint}. 「{마지막[-24:]}」")
    for i, it in enumerate(doc.get("본문", [])):
        if "표" in it:
            continue
        t = it["text"].strip()
        if FORBIDDEN_END.search(t):
            bad.append(f"본문 {i+1}번째: 금지 종결(~요망/~바람/~할 것) — 공손체로(gongmun-gyeoksik)")
        # 서술어 완결('…다.')은 주요 서술부(1. 수준)의 규범 — 세부 개조식(가. 이하)은 명사형 허용.
        # '관련:'·'문의:' 같은 표지어 항목도 예외(LABEL_ITEM) — 공문 관행이지 흠이 아니다.
        if it["level"] == 1 and not POLITE_END.search(t) and not LABEL_ITEM.match(t):
            if _붙임비슷.match(t):
                # 원인을 "문장을 못 맺었다"로만 알리면 모델이 '…다.'로 고쳐 쓰려다 매번
                # 다시 걸린다(bench3/runs/P/qwen-s3/run.json 실패 로그 — 5회 반려). 최상위
                # 붙임 배열로 옮기라고 구체적으로 알린다.
                bad.append(f"본문 {i+1}번째: 이 줄은 '붙임' 표시로 보인다 — 본문이 아니라 "
                           f"최상위 '붙임' 배열에 넣어라(예: \"붙임\": [\"○○ 계획 1부.\"]) — 「{t[:24]}」")
            else:
                bad.append(f"본문 {i+1}번째(주요 서술부): 서술어 완결('…다.') 아님 — 「{t[-20:]}」")
    return bad


# 단일수신 축약 판정은 build/수신꼴.py 공용 모듈에 있다(tomd.py 와 같이 쓴다, assemble:F11
# '26-09-27 — MD 산출물이 이 축약을 안 따라 같은 문서의 두문·결문 표기가 HTML/HWPX 와
# 달랐다). 얇은 별칭만 남겨 기존 호출부(build() 안의 _수신정리(doc))를 그대로 둔다.
_수신정리 = 수신꼴.수신정리


def _결문줄(m):
    """연락처 줄 — 값이 없는 조각은 구분자째 감춘다(전화·팩스·이메일·공개가 비면 '전화 / 전송 / /'
    처럼 빈 자리표시가 찍히던 것을 고쳤다, '26-09-26 벤치마크 진단). 전화·내선은 함께 있으면
    '전화 02-000-0000(내선 1234)'로 묶는다."""
    전화 = _s(m.get("전화")).strip()
    내선 = _s(m.get("내선")).strip()
    if 전화 and 내선:
        조각 = [f"전화 {전화}(내선 {내선})"]
    elif 전화:
        조각 = [f"전화 {전화}"]
    elif 내선:
        조각 = [f"내선 {내선}"]
    else:
        조각 = []
    for 라벨, 키 in (("전송 ", "팩스"), ("", "이메일"), ("", "공개")):
        값 = _s(m.get(키)).strip()
        if 값:
            조각.append(f"{라벨}{값}")
    return html.escape(" / ".join(조각))


def _시행표시(m):
    """시행 줄 — 시행일이 없으면 빈 괄호 '( )'를 통째로 감춘다('26-09-26 벤치마크 진단:
    '시행 정보보안처- ()' 처럼 빈 괄호가 찍힘)."""
    시행 = html.escape(_s(m.get("시행")).strip())
    시행일 = html.escape(_s(m.get("시행일")).strip())
    return f"{시행} ({시행일})" if 시행일 else 시행


def _우편주소(m):
    """우편번호·주소 줄 — 값이 둘 다 없으면 '우' 라벨째 줄을 감춘다. 스키마는 지금
    '주소' 한 필드뿐이지만(있으면 우편번호까지 포함해 적는 관행), 자료에 '우편번호'가
    따로 실려 와도 받아 앞에 붙인다. 하나만 있으면 있는 것만 낸다('26-09-27 벤치마크
    진단: 주소가 비어도 '우' 글자만 남아 결문 한 줄을 차지함 — tomd.py 는 이미
    비면 줄째 뺐는데 HTML/PDF/HWPX 는 이 조립기가 만드는 같은 html 을 썼으므로
    여기만 고치면 셋 다 같이 고쳐진다)."""
    우편번호 = _우편번호꼴(m.get("우편번호")).strip()
    주소 = _s(m.get("주소")).strip()
    조각 = [x for x in (우편번호, 주소) if x]
    return html.escape(" ".join(조각)) if 조각 else None


_PROFILES = None


def load_profile(genre):
    global _PROFILES
    if _PROFILES is None:
        with open(os.path.join(BASE, "..", "ontology", "editor-profiles.json"), encoding="utf-8") as f:
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
        return f'<meta name="기준" content="{html.escape(stamp.조판지문("gongmun"))}">'
    except Exception:
        return ""


def build(doc):
    org = html.escape(doc.get("기관명", ""))
    DOC_JSON = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    PROFILE_JSON = json.dumps(load_profile("gongmun"), ensure_ascii=False).replace("</", "<\\/")
    STAMP = 기준도장()
    # 여백 — 사용자가 고르거나 예시 양식을 실측한 값이 있으면 그것을 싣는다.
    # 없으면 CSS 기본값(실물 실측)이 그대로 쓰인다.
    m = doc.get("여백_mm") or {}
    스타일 = ""
    if isinstance(m, dict) and m:
        # 여백은 밀리미터 **숫자 하나**다(build/속성값.py). 예전엔 값을 그대로
        # style 속성 조각에 보간해, 큰따옴표 하나로 <html> 에 임의 속성을 심을 수
        # 있었다 — 풀보고서와 규정에도 같은 자리가 있었다(적대리뷰 §높음의 부류).
        쪽 = []
        for 변수, 키 in (("t", "상"), ("r", "우"), ("b", "하"), ("l", "좌")):
            폭 = 속성값.수(m.get(키), f"여백_mm.{키}", 최소=0, 최대=200)
            if 폭 is not None:
                쪽.append(f"--gm-m{변수}:{폭}mm")
        스타일 = (' style="' + ";".join(쪽) + '"') if 쪽 else ""
    # _수신정리 가 두문 값의 실제 출처 필드를 직접 돌려준다(축약 여부만으로 고르면
    # '수신==수신자란' 케이스에서 경로가 틀린다 — 위 _수신정리 docstring, 3차 검토).
    수신표시, 수신자란표시, _수신경로 = _수신정리(doc)
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="gongmun"{스타일}>
<head>
<meta charset="utf-8">{STAMP}
<title>{html.escape(doc.get("제목",""))}</title>
<link rel="stylesheet" href="../tokens.css?v=">
<link rel="stylesheet" href="../gongmun.css?v=">
</head>
<body>
<script type="application/json" id="fr-doc">{DOC_JSON}</script>
<script type="application/json" id="fr-profile">{PROFILE_JSON}</script>
<div class="gm-sheet">
  <div class="gm-head">
    <div class="gm-slogan">{html.escape(doc.get("슬로건",""))}</div>
    <div class="gm-org-row"><div class="gm-logo">{'(로고)' if doc.get("로고표시") else ''}</div>
      <div class="gm-org" data-ent="두문결문" data-gf="기관명" data-path="기관명">{org}</div><div></div></div>
    <div class="gm-gap"></div>
    <div class="gm-line"><span class="lb">수신</span><span data-ent="두문결문" data-gf="수신" data-path="{속성값.열거(_수신경로, ("수신", "수신자란"), "수신경로", 기본="수신")}">{html.escape(수신표시)}</span></div>
    <div class="gm-line"><span class="lb">(경유)</span><span data-ent="두문결문" data-gf="경유" data-path="경유">{html.escape(doc.get("경유",""))}</span></div>
    <div class="gm-subject"><span class="lb">제목</span><span data-ent="제목" data-path="제목">{html.escape(doc.get("제목",""))}</span></div>
  </div>
  <div class="gm-body">
"""]
    counters = {}
    items = doc.get("본문", [])
    only_one_l1 = sum(1 for it in items if "표" not in it and it["level"] == 1) <= 1
    last_html_idx = None
    last_is_table = False
    for it in items:
        if "표" in it:
            tb = it["표"]
            cap = f'<div class="gm-tbl-caption">{html.escape(tb.get("캡션",""))}</div>' if tb.get("캡션") else ''
            # '26-09-29 표 재설계 P1: 표 몸은 build/표꼴.py 공용(열폭·열정렬·머리·첫열·병합·강조·모양)
            parts.append(f'    <div class="gm-table-wrap" data-ent="표" data-path="본문.{items.index(it)}.표">'
                         f'{cap}{표꼴.표html(tb, "gm-table")}</div>\n')
            last_html_idx = None
            last_is_table = True
            continue
        last_is_table = False
        lv = it["level"]
        counters[lv] = counters.get(lv, 0) + 1
        for deeper in list(counters):
            if deeper > lv:
                counters[deeper] = 0
        if lv == 1 and only_one_l1:
            mk = ""            # 항목 하나뿐이면 기호 미부여(편람 구-13)
        else:
            mk = marker(lv, counters[lv])
        indent = (lv - 1) * 1.0  # 2타 = 1em(한글 1자)씩 — 편람 디-02
        style = f"padding-left:{indent}em" if indent else ""
        text = html.escape(it["text"])
        # 플렉스 구조: 마커 폭과 무관하게 둘째 줄이 내용 첫 글자에 정렬(편람 디-04 원칙)
        mk_html = f'<span class="g-mk">{mk} </span>' if mk else ""
        parts.append(f'    <p class="g-l{min(lv,6)}" data-ent="항목" style="{style}">'
                     f'{mk_html}<span class="g-tx" data-path="본문.{items.index(it)}.text">'
                     f'{text}</span></p>\n')
        last_html_idx = len(parts) - 1

    attach = [a for a in doc.get("붙임", []) if a.strip()]
    end_style = doc.get("끝표시", "같은줄")   # 같은줄 | 새줄 | 새줄오른쪽 (FB-023 카탈로그)
    END_INLINE = '&nbsp;&nbsp;<span class="gm-end-i" data-ent="끝표시" data-gend>끝.</span>'
    def end_p():
        cls = "gm-end right" if end_style == "새줄오른쪽" else "gm-end"
        return f'    <p class="{cls}" data-ent="끝표시" data-gend>끝.</p>\n'
    if attach:
        lines = []
        for i, a in enumerate(attach):
            # 이어지는 줄은 투명 유령 라벨 — 첫 줄과 동일 글자폭이라 번호 열이 정확히 정렬(비례폰트 안전)
            label = "붙임" if i == 0 else '<span class="gm-at-ghost">붙임</span>'
            num = f" {i+1}." if len(attach) > 1 else ""
            # 줄마다 글만 span(data-path)으로 감싼다 — 보도자료 pr-attach 와 같은 모양
            # (assemble_press.py). 라벨·번호·끝 표시는 span 밖에 둔다. 예전엔 붙임 전체를
            # <br> 로 이은 한 태그에만 data-ent 를 달아 편집기 serialize 가 되쓸 자리가
            # 없었다 — '직접 수정'으로 고친 글이 저장에 전혀 안 실렸다(asm:R7-03).
            lines.append(f'{label}{num}&nbsp;&nbsp;<span class="tx" data-path="붙임.{i}">'
                         f'{html.escape(a)}</span>')
        if end_style == "같은줄":
            lines[-1] += END_INLINE               # 붙임 뒤 2타 끝.(표-36②)
        parts.append('    <p class="gm-attach" data-ent="붙임">' + "<br>".join(lines) + "</p>\n")
        if end_style != "같은줄":
            parts.append(end_p())
    elif last_is_table or end_style != "같은줄":
        # 표로 끝나면 같은줄 불가 — 표 아래 왼쪽 기본선(표-36④). 스타일 지정 시 그 스타일로.
        parts.append(end_p())
    elif last_html_idx is not None:
        parts[last_html_idx] = parts[last_html_idx].replace(
            "</span></p>", END_INLINE + "</span></p>")  # 본문 끝 2타 뒤 끝.(표-36①)

    m = doc.get("메타", {})
    # 관인 — 시행규칙 제11조제1항: "발신 명의 표시의 마지막 글자가 인영의 가운데에 오도록".
    # 도장이 글자 옆이 아니라 글자 위에 겹쳐 찍히는 것이 규범이다.
    # 배경을 지운 이미지를 마지막 글자 위에 얹는다('26.7.31. 판정).
    관인 = doc.get("관인") or {}
    if doc.get("관인생략"):
        stamp = '<span class="gm-stamp-note">(관인생략)</span>'
    elif 관인.get("이미지"):
        크기 = 속성값.수(관인.get("지름_mm"), "관인.지름_mm", 기본=30, 최소=1, 최대=200)
        오른 = 관인.get("오른쪽에", False)          # 민원서류 직인은 오른쪽 허용(같은 항 단서)
        stamp = (f'<img class="gm-seal{" right" if 오른 else ""}" '
                 f'src="{html.escape(관인["이미지"])}" alt="관인" '
                 f'style="--seal:{크기}mm" data-ent="관인" data-path="관인.이미지">')
    else:
        stamp = ""
    recipients = html.escape(수신자란표시)
    우편주소값 = _우편주소(m)
    우편주소줄 = (f'    <div class="gm-meta"><span class="k">우</span><span class="v">{우편주소값}</span></div>\n'
              if 우편주소값 is not None else '')
    parts.append(f"""  </div>
  <div class="gm-foot">
    <div class="gm-sign"><span class="gm-name" data-ent="두문결문" data-gf="발신명의" data-path="발신명의">{html.escape(_s(doc.get("발신명의")).strip()) or "(발신 명의 — 서명 시 기입)"}</span>{stamp}</div>
    <div class="gm-recipients">{('수신자 ' + recipients) if recipients else ''}</div>
    <div class="gm-band"></div>
    <div class="gm-approvers"><div class="cell">기안자 {html.escape(_s(m.get("기안자")))}</div>
      <div class="cell">검토자</div><div class="cell">협조자</div><div class="cell">결재권자</div></div>
    <div class="gm-band"></div>
    <div class="gm-meta"><span class="k">시행</span><span class="v">{_시행표시(m)}</span>
      <span class="k">접수</span><span class="v"> ( )</span></div>
{우편주소줄}    <div class="gm-contact">{_결문줄(m)}</div>
  </div>
</div>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
<script src="../gmseal.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


def 조립하기(등록부경로, only=None, out=None, 저장=False):
    """시행문 등록부 → HTML + 복붙용 .txt. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 게이트 위반 문서는 안
    쓰고 ok=False 가 된다(subprocess 였다면 returncode≠0). 산출물뿌리를 **호출마다**
    다시 푼다(세션 오염 방지). `out` 을 주면(=--out) 그 자리로 뽑는다.

    `저장`(기본 False) — True 면 gate_check 의 "본문이 비어 있습니다"(내용 결손) 위반만
    소프트 경고로 낮춘다(assemble_full·assemble_slides 의 같은 인자와 같은 취지, r10
    사후검토 발견 medium) — 이미 등록된(빈 본문) 문서를 저장할 때 등록부(JSON)는 편집이
    반영됐는데 HTML 은 재조립 실패로 옛 채로 남는 어긋남을 막는다. 새 초안에서는 여전히
    하드로 막힌다(저장=False 기본값).
    """
    낼곳 = out if out else 자료뿌리.산출물뿌리()   # 호출마다 세션 뿌리를 다시 푼다
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    # 한 건만 다시 만들 수 있다(`--only <문서키>`, WP-S2 ②) — 세션 안에서 문서
    # 하나를 저장할 때 나머지 문서 파일까지 다시 쓰지 않으려고. 판정은 genres 한 곳.
    docs = genres.한건만(docs, ["--only", only] if only else [])
    fail = 0
    낸것, 로그 = [], []
    for doc in docs:
        # gate_check 보다 먼저 돈다 — 편집기·B 의 등록 정규화를 거치지 않은 옛 doc(또는
        # 손으로 지은 표본)도 안전하게 걸러야 한다(B 와의 약속). 본문에 섞여 들어온 '붙임'
        # 표시 줄을 최상위 배열로 옮기면, 매 붙임 줄마다 하나씩 쌓이던 서술어 완결 위반이
        # 통째로 사라진다(bench3 qwen-s3 5회 반려 원인).
        # 강제=True — 이 조립기는 자신이 이미 시행문 경로다(손으로 지은 표본이 genre
        # 키를 빠뜨려도 건너뛰지 않는다, low — 붙임꼴.py 분리하기 docstring 참고).
        옮긴수 = 붙임꼴.분리하기(doc, 강제=True) if 붙임꼴 else 0
        if 옮긴수:
            로그.append(f"[소프트 경고] {doc['filename']}")
            로그.append(f"  ! 본문에 섞인 '붙임' 표시 {옮긴수}건을 최상위 붙임 배열로 옮겼다")
        bad = gate_check(doc)
        if 저장 and bad:
            연성 = [b for b in bad if b.startswith("본문이 비어 있습니다")]
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
        # 복붙용 텍스트(1급 산출물 — FB-022): 제목 + 본문(마커·들여쓰기 포함)
        lines = [doc.get("제목", ""), ""]
        counters = {}
        items = doc.get("본문", [])
        only_one = sum(1 for it in items if "표" not in it and it["level"] == 1) <= 1
        for it in items:
            if "표" in it:
                tb = it["표"]
                if tb.get("캡션"):
                    lines.append("  " + tb["캡션"])
                lines.append("  " + "\t".join(tb.get("header", [])))
                for row in tb.get("rows", []):
                    lines.append("  " + "\t".join(row))
                continue
            lv = it["level"]
            counters[lv] = counters.get(lv, 0) + 1
            for dp in list(counters):
                if dp > lv:
                    counters[dp] = 0
            mk = "" if (lv == 1 and only_one) else marker(lv, counters[lv]) + " "
            lines.append("  " * (lv - 1) + mk + it["text"])
        att = [a for a in doc.get("붙임", []) if a.strip()]
        if att:
            lines.append("")
            for i, a in enumerate(att):
                lead = "붙임" if i == 0 else "    "
                num = f" {i+1}." if len(att) > 1 else ""
                lines.append(f"{lead}{num}  {a}")
        end_style = doc.get("끝표시", "같은줄")
        # 붙임이 있으면 표 여부와 무관하게 붙임 마지막 줄에 인라인(표-36② — HTML과 동일 규칙)
        if end_style == "같은줄" and (att or not (items and "표" in items[-1])):
            lines[-1] += "  끝."
        else:
            lines.append("끝.")
        with 자료뿌리.쓰기(os.path.join(낼곳, f"{doc['filename']}.txt")) as f:
            f.write("\n".join(lines) + "\n")
        낸것.append(fn)
        로그.append(f"built: {fn} + .txt")
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
