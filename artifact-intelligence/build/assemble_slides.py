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
     "헤드메시지": "완결 주장 문장(본문·표·도식·이미지·픽토그램·마무리 필수)",
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
  · 레이아웃은 카탈로그 열거값(모르는 이름을 조용히 본문으로 떨어뜨리지 않는다) — 단 실측된
    한국어 관행어·부분일치("…도식")는 _레이아웃정규화가 먼저 정본으로 옮긴다(레이아웃별칭)
  · 본문·표·마무리엔 헤드메시지 필수 — 헤드메시지 없는 장은 메시지 없는 장이다
픽토그램 아이콘은 하드가 아니다('26-09-27) — 흔한 영문 별칭(_아이콘별칭)으로 먼저 옮기고,
그래도 라이브러리에 없으면 그 아이콘만 빼고(그림 없이 라벨·설명 글만) 소프트 경고로 알린다
— 약한 모델이 아이콘 하나 때문에 덱 전체를  반려당하던 것(실측 bench3 P/exaone-s6)을 막는다.
장수·넘침은 렌더 게이트(render_verify.sh) 소관 — 조립기는 세지 않는다.

판형 v2('26-09-28) — 최상위 `판형: "v2"` 문서는 부품 트리 경로(build_v2)를 탄다: 모델은 장·칸·부품
JSON 만 쓰고 조립기가 12열 배치·차트(값 배열 → SVG/div)·강조·산출 꼬리·노트를 그린다.
정본 모양 build/slides_v2.schema.json · 게이트 build/slides_v2_gate.py · 서식 build/slides_v2.css.
판형 키가 없는 옛 문서는 위 경로 그대로다(test/r16_slides16b.py 가 지문으로 지킨다).

사용: python3 build/assemble_slides.py build/slides-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
import 표꼴
import 자료뿌리
import svgfig
import imageasset
import pictogram
import html
import json
import re
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물 뿌리는 조립하기() 가 호출마다 다시 푼다(WP-S9·세션 오염 방지) — 상수 금지.

NBSP = "&#160;"

# 개조식 사다리 — 슬라이드 본문은 얕다(3단이면 이미 깊다. 장당 1메시지가 중핵이다)
마커 = {1: "□", 2: "○", 3: "-"}


def _온톨로지슬라이드구성():
    """온톨로지 document_types.slides.구성 = 슬라이드 카탈로그 정본(레이아웃·도식유형).
    온톨로지 파일이 빠진 설치(0.3.x 배포본)에서는 None 을 돌려줄 수 있다 — 그땐 아래 폴백."""
    p = os.path.join(ROOT, "ontology", "ontology.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)["document_types"]["slides"]["구성"]
    except Exception:
        return None


# 정본은 온톨로지 slides.구성.레이아웃_카탈로그 — 있으면 거기서 파생(드리프트 0), 없으면(배포
# 스크럽) 아래 폴백. 폴백은 정본과 같은 값이어야 한다(build/tests/test_slides_catalog_sync.py).
# 헤드장(헤드메시지가 이끄는 장) = 카탈로그 설명이 "헤드메시지"로 시작하는 레이아웃(어젠다·간지는 흐름만).
# [P3계약 신설 '26-09-06] 비교·큰숫자·매트릭스·타임라인은 헤드메시지 필수(헤드장) — 인용은
# 헤드메시지가 선택(인용문·출처가 이미 주장을 담는다)이라 헤드장에서 뺀다.
레이아웃들 = ("어젠다", "간지", "본문", "표", "도식", "이미지", "픽토그램", "마무리",
           "비교", "큰숫자", "매트릭스", "인용", "타임라인")
헤드장 = ("본문", "표", "도식", "이미지", "픽토그램", "마무리", "비교", "큰숫자", "매트릭스", "타임라인")
try:
    _카탈로그 = (_온톨로지슬라이드구성() or {}).get("레이아웃_카탈로그") or {}
    _본문형 = {k: v for k, v in _카탈로그.items() if not k.startswith("_") and k != "표지"}
    if _본문형:
        레이아웃들 = tuple(_본문형)
        헤드장 = tuple(k for k, v in _본문형.items()
                     if isinstance(v, str) and v.startswith("헤드메시지"))
except Exception:
    pass
# 실측된 레이아웃 유의어 → 정본 이름. **아무 미지값을 삼키는 게 아니다**(게이트의 "모르는 이름을
# 조용히 본문으로 안 떨어뜨린다"는 그대로) — EXAONE 가 '본문'을 '본체'로 반복해 자가수정을
# 낭비하던 특정 유의어만 정본으로 옮긴다(2026-09-02 스윕). 값은 반드시 레이아웃들 안이어야 한다
# (verify_all check_slides_catalog_sync 가 지킨다).
# [P3계약 신설 '26-09-06] 신규 레이아웃 5종의 영문·유의어 별칭 — 다른 문서지능 코퍼스·프롬프트
# 유파(Slidev·pptx 계열)가 쓰는 이름을 정본으로 옮긴다.
# [3차 측정 재발 '26-09-27] 서버 EXAONE 실패 로그(bench3 P/exaone-s6) — '정리'·'본페이지'가
# 카탈로그에 없어 5회 하드 게이트로 덱 전체가 막혔다. 한국어 관행어 별칭을 더한다.
레이아웃별칭 = {
    "본체": "본문", "본론": "본문", "본페이지": "본문", "내용": "본문",
    "compare": "비교", "two-cols": "비교", "comparison": "비교", "비교표": "비교", "대조": "비교",
    "kpi": "큰숫자", "KPI": "큰숫자", "bignumber": "큰숫자", "fact": "큰숫자", "statement": "큰숫자",
    "수치": "큰숫자", "숫자": "큰숫자",
    "matrix": "매트릭스", "2x2": "매트릭스", "quadrant": "매트릭스",
    "quote": "인용", "testimonial": "인용",
    "timeline": "타임라인", "roadmap": "타임라인", "일정": "타임라인", "로드맵": "타임라인",
    "chart": "도식",
    "정리": "마무리", "요약": "마무리", "결론": "마무리", "맺음": "마무리",
    "목차": "어젠다", "순서": "어젠다",
}
# 이름에 '도식'이 그대로 들어 있으면(예: '본사 모으듯이 도식') 별칭표를 안 거쳐도 도식으로 본다
# — 위 별칭표는 정확히 일치하는 이름만 잡고, 모델이 설명을 덧붙인 온전한 문장을 내는 이탈은
# 못 잡는다(실측 bench3 exaone-s6, 같은 실패 로그).
_레이아웃부분일치 = (("도식", "도식"),)
# 도식 type 유의어 → svgfig 정본 이름(차트 4종 도입, '26-09-06). 게이트·렌더 모두 이 뒤에 온다.
도식유형별칭 = {"bar_chart": "bar", "column": "bar", "line_chart": "line",
             "pie": "donut", "doughnut": "donut"}
# 픽토그램 아이콘 흔한 영문 별칭 → build/pictograms.json 의 실제 이름(가장 가까운 것). 실측
# bench3 P/exaone-s6(같은 실패 로그) — chat·chatbot·alert·hand-raise 가 라이브러리에 없어
# 약한 모델이 아이콘 하나 때문에 덱 전체를 5회 반려당했다. 여기서도 못 찾으면(별칭표 밖)
# **하드로 막지 않는다** — _픽토그램정규화 가 소프트 경고만 남기고, 렌더(_픽토그램)가 그
# 아이콘 하나만 빼고 라벨·설명 글로 낸다.
_아이콘별칭 = {
    "chat": "dialogue", "chatbot": "dialogue", "message": "dialogue", "messaging": "dialogue",
    "alert": "warning", "hand-raise": "customer", "hand_raise": "customer", "handraise": "customer",
    "user": "person", "home": "location",
}
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


def _내용기반레이아웃(s):
    """장 안에 이미 담긴 시각 콘텐츠 키(표·도식·지표·단계·좌우)를 본다 — 있으면 그 키를
    그리는 레이아웃이 이름 별칭보다 우선이다(r10 사후검토 발견 medium, '26-09-27). 이름만
    보고 옮기면('비교표'+표 → 이름 별칭은 '비교') 그 레이아웃 전용 자리에서만 그려지는
    콘텐츠가 조용히 안 그려진다 — build() 는 lo=='표'일 때만 _표() 를, lo=='비교'일 때만
    좌·우를 그린다(1236-1253행). 실측: '비교표'+표는 비교로 옮겨지면 표가 안 그려지고
    렌더 본체 빔(하드)까지 요구하며, '순서'+도식은 어젠다로 옮겨져 목차 항목 0개를
    요구한다. 콘텐츠 키가 없으면(순수 이름 문제) None — 그때만 이름 별칭·부분일치를 쓴다."""
    tb = s.get("표")
    if isinstance(tb, dict) and (tb.get("rows") or tb.get("header")):
        return "표"
    fg = s.get("도식")
    if isinstance(fg, dict) and fg.get("type"):
        return "도식"
    지표 = s.get("지표")
    if isinstance(지표, list) and 지표:
        return "큰숫자"
    단계 = s.get("단계")
    if isinstance(단계, list) and 단계:
        return "타임라인"
    좌, 우 = s.get("좌"), s.get("우")
    if (isinstance(좌, dict) and 좌) or (isinstance(우, dict) and 우):
        return "비교"
    return None


def _레이아웃정규화(doc):
    """모델이 레이아웃 이름을 정본 유의어로 흘리는 흔한 이탈(본체→본문)을 정본 이름으로 옮긴다 —
    _표정규화와 같은 자리·같은 취지(게이트에 통째로 걸리는 것보다 낫다). 별칭표·부분일치 밖
    미지 이름은 안 건드린다(그건 게이트가 '모르는 이름'으로 잡는다). 실측 2026-09-02 스윕:
    '본체' 가 입력 여럿에서 반복돼 5회 자가수정을 낭비했다.

    내용 키(_내용기반레이아웃)가 이름 별칭보다 먼저다(위 docstring) — 이름 별칭은 그 장에
    표·도식·지표·단계·좌우 어느 콘텐츠도 없을 때만 적용한다. 또 이름 별칭으로 '마무리'가
    나왔는데 그 장이 마지막 장이 아니면 '본문'으로 돌린다(r10 사후검토: '요약'을 중간 장에
    쓰면 마무리로 옮겨져 '마무리 장이 마지막이 아니다' 같은 헛구조 경고가 늘었다) — 카탈로그
    이름 그대로 '마무리'를 쓴 장(별칭이 아니다)은 이 보정 밖이라 그대로 하드 위반으로 남는다.

    돌려주는 값: 고친 내역(소프트 경고 문구) 목록 — **조용히 바꾸지 않는다**('26-09-27, 3차
    측정 재발). 반환값은 예전엔 안 쓰였다(호출부·시험 모두 버렸다) — 그 자리를 재사용한다."""
    바뀜 = []
    장들 = doc.get("슬라이드") or []
    n = len(장들)
    for i, s in enumerate(장들):
        if not isinstance(s, dict):
            continue
        원래 = s.get("레이아웃")
        if 원래 in 레이아웃들:
            continue
        내용기반 = _내용기반레이아웃(s)
        if 내용기반:
            새, 근거 = 내용기반, "내용 키 기준"
        else:
            새 = 레이아웃별칭.get(원래)
            if 새 is None and isinstance(원래, str):
                for 조각, 대상 in _레이아웃부분일치:
                    if 조각 in 원래:
                        새 = 대상
                        break
            if 새 == "마무리" and i != n - 1:
                새 = "본문"
            근거 = "별칭"
        if 새:
            s["레이아웃"] = 새
            바뀜.append(f"슬라이드.{i}: 레이아웃 '{원래}'를 '{새}'로 교정({근거})")
    return 바뀜


def _도식타입정규화(doc):
    """모델이 차트 type 을 유의어로 내는 흔한 이탈(bar_chart→bar, pie→donut …)을 svgfig 정본
    이름으로 옮긴다 — _레이아웃정규화와 같은 자리·같은 취지(게이트에 통째로 걸리는 것보다 낫다)."""
    for s in (doc.get("슬라이드") or []):
        if not isinstance(s, dict):
            continue
        fg = s.get("도식")
        if isinstance(fg, dict) and fg.get("type") in 도식유형별칭:
            fg["type"] = 도식유형별칭[fg["type"]]
    return doc


def _큰숫자정규화(doc):
    """모델이 큰숫자 지표 원소에서 단위·라벨 슬롯을 뒤섞는 흔한 이탈을 조립 시점에 바로잡는다 —
    _도식정규화·_레이아웃정규화와 같은 자리·같은 취지(게이트에 통째로 걸리는 것보다 낫다). 실측
    2026-09-06: 서버 EXAONE 가 {값:"30일", 단위:"점검 주기 단축", 라벨:""} 처럼 지표 이름 문구를
    단위 슬롯에 넣고 라벨을 비웠다 — 조립기가 그대로 88pt 값 옆 인라인(.sl-kpi-unit)에 붙여
    화면에서 값과 겹쳐 잘렸다. 값 끝에 붙는 진짜 짧은 단위(일·분·%·억·건·명 등 1~2자)는 값
    문자열 안에 있어도 손대지 않는다(무해하다)."""
    for s in (doc.get("슬라이드") or []):
        if not isinstance(s, dict) or s.get("레이아웃") != "큰숫자":
            continue
        지표 = s.get("지표")
        if not isinstance(지표, list):
            # 키 별칭 — 실측 2026-09-06(라이브 EXAONE): 지표 배열을 레이아웃 이름과 같은 "큰숫자" 키로 내
            # 조립기가 빈 카드판을 그렸고(헤드만 있어 백지 게이트도 통과) 장이 통째로 비었다. 도식의
            # 영문키 정규화와 같은 취지로 흔한 별칭을 정본 키 "지표"로 옮긴다(내용 창작 없음).
            for k in ("큰숫자", "지표들", "수치", "카드", "kpi", "KPI", "metrics", "items"):
                v = s.get(k)
                if isinstance(v, list) and v:
                    지표 = v
                    s["지표"] = v
                    break
        if not isinstance(지표, list):
            continue
        정규 = []
        for m in 지표:
            if not isinstance(m, dict):
                정규.append({"값": str(m)} if m is not None else {})
                continue
            m = dict(m)
            for 영, 한 in (("value", "값"), ("unit", "단위"), ("label", "라벨"), ("name", "라벨"),
                         ("delta", "변화"), ("change", "변화")):
                if 영 in m and 한 not in m:
                    m[한] = m.pop(영)
            라벨 = str(m.get("라벨") or "").strip()
            단위 = str(m.get("단위") or "").strip()
            if 단위:
                문구다 = len(단위) > 4 or any(ch.isspace() for ch in 단위)
                if not 라벨:
                    m["라벨"] = 단위
                    m["단위"] = ""
                elif 문구다:
                    m["단위"] = ""
            정규.append(m)
        s["지표"] = 정규
    return doc


def _픽토그램정규화(doc):
    """모델이 픽토그램 아이콘 이름을 흔한 영문 유의어(chat·chatbot·alert·hand-raise 등)로 내는
    흔한 이탈을 build/pictograms.json 의 실제 이름으로 옮긴다 — _레이아웃정규화·_도식타입정규화와
    같은 자리·같은 취지(게이트에 통째로 걸리는 것보다 낫다). 별칭표로도 못 푸는 이름은 **여기서
    지우거나 비우지 않는다** — 값은 그대로 두고(다음 저장·재조립에서도 같은 판정이 멱등으로
    돌게), 렌더(_픽토그램)가 pictogram.has() 를 다시 물어 그 아이콘 하나만 그림 없이 라벨·설명
    글로 낸다. 하드로 막지 않는 이유: 약한 모델이 아이콘 하나 때문에 덱 전체가 5회 반려당했다
    (실측 bench3 P/exaone-s6, run.json steps).

    돌려주는 값: 고친 내역(별칭 교정 + 그림 뺀 안내) 소프트 경고 문구 목록 — 조용히 바꾸지
    않는다('26-09-27)."""
    바뀜 = []
    for i, s in enumerate(doc.get("슬라이드") or []):
        if not isinstance(s, dict) or s.get("레이아웃") != "픽토그램":
            continue
        ps = s.get("픽토그램")
        if not isinstance(ps, list):
            continue
        for j, p in enumerate(ps):
            if not isinstance(p, dict):
                continue
            아이콘 = p.get("아이콘", "")
            if not 아이콘 or pictogram.has(아이콘):
                continue
            새 = _아이콘별칭.get(아이콘)
            if 새:
                p["아이콘"] = 새
                바뀜.append(f"슬라이드.{i}.픽토그램.{j}: 아이콘 '{아이콘}'을 '{새}'로 교정(별칭)")
            else:
                바뀜.append(f"슬라이드.{i}.픽토그램.{j}: 라이브러리에 없는 아이콘 '{아이콘}' — "
                           f"그 아이콘만 빼고 그림 없이 라벨·설명 글로 낸다(하드로 막지 않는다)")
    return 바뀜


def _객체(x):
    """dict 면 그대로, 아니면 {} — LLM 이 dict 자리에 문자열/배열을 넣어도 게이트가
    .get() 에서 크래시하지 않고 곱게 '위반'으로 떨어지게 한다(그래야 자가수정 되먹임이 돈다).
    실측 2026-09-02: EXAONE 가 슬라이드 '표' 자리에 문자열을 넣어 gate_check 가
    AttributeError 로 죽었고, 조립 예외라 자가수정이 발동조차 못 했다."""
    return x if isinstance(x, dict) else {}


# 화면에 안 찍히는 메타 필드 — '텍스트 0자' 재귀 스캔에서 뺀다(레이아웃 이름·자유배치 좌표·
# 도식 type 열거값은 값 자체가 문자열이라도 사람 눈엔 안 보인다).
_비텍스트키 = ("레이아웃", "배치모드", "배치", "type")


def _텍스트있나(v):
    """장(또는 그 아래 아무 값) 안에 화면에 찍힐 글자가 하나라도 있는가 — 하드 게이트
    '어떤 장도 렌더 텍스트 0자 금지'의 재귀 스캔. 인용처럼 헤드메시지가 선택인 레이아웃도
    이걸로 잡는다(인용문·출처가 둘 다 비면 화면이 진짜로 빈다)."""
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, dict):
        return any(_텍스트있나(x) for k, x in v.items() if k not in _비텍스트키)
    if isinstance(v, list):
        return any(_텍스트있나(x) for x in v)
    return False


def gate_check(doc):
    """슬라이드 꼴을 갖췄는가 — 조립 시점 하드 게이트."""
    if _v2문서인가(doc):
        # 판형 v2 문서는 v2 게이트로 — 옛 꼴(표지.제목·슬라이드 배열)로 재면 늘 '없다'가 나와, 지어냄 교정 적용
        # (api._장르게이트확인)이 v2 문서의 고침을 전부 거절했다('26-09-29 EXAONE s2 실측: 4.2억 원을 42억 원으로
        # 쓴 초안의 교정이 '표지.제목이 없다 / 슬라이드가 한 장도 없다'로 막힘)
        import slides_v2_gate
        return list(slides_v2_gate.검사(doc)[0])
    bad = []
    if not _객체(doc.get("표지")).get("제목"):
        bad.append("표지.제목이 없다")
    테마 = doc.get("테마")
    if 테마 and 테마 not in 테마들:
        bad.append(f"테마 {테마!r} — 라이브러리에 없다({', '.join(테마들)})")
    장들 = doc.get("슬라이드") or []
    if not 장들:
        bad.append("슬라이드가 한 장도 없다")
    for i, s in enumerate(장들):
        if not isinstance(s, dict):
            bad.append(f"슬라이드.{i}: 슬라이드가 객체가 아니다({type(s).__name__}) — "
                       f"{{레이아웃, 헤드메시지, …}} 꼴이어야 한다")
            continue
        lo = s.get("레이아웃")
        if lo not in 레이아웃들:
            bad.append(f"슬라이드.{i}: 레이아웃 {lo!r} — 카탈로그에 없다"
                       f"({', '.join(레이아웃들)}). 모르는 이름을 본문으로 떨어뜨리지 않는다")
            continue
        if lo in 헤드장 and not str(s.get("헤드메시지") or "").strip():
            bad.append(f"슬라이드.{i}({lo}): 헤드메시지가 없다 — "
                       f"메시지 없는 장은 장당 1메시지 중핵 위반이다")
        if lo in 헤드장 and len(str(s.get("헤드메시지") or "").strip()) > 50:
            # 실측 보정 2026-09-07: 실물 부처 덱 사례의 덱별 최대 헤드 글자수 p90 = 43자 — 50자는 그 위(hard)
            bad.append(f"슬라이드.{i}({lo}): 헤드메시지가 {len(str(s.get('헤드메시지')).strip())}자 — 50자를 넘는다"
                       f"(실물 덱 최대 43자). 결론 한 문장으로 줄여라")
        if lo == "표":
            tb = _객체(s.get("표"))
            rows = tb.get("rows")
            hdr = tb.get("header")
            if not rows:
                bad.append(f"슬라이드.{i}(표): 표 rows 가 없다")
            elif not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
                # 게이트가 구조까지 봐야 _표 렌더의 `for c in row` 가 안 죽는다(숫자·None 행 = 크래시)
                bad.append(f"슬라이드.{i}(표): 표 rows 는 이중배열이어야 한다 — 각 행을 셀 목록([\"a\",\"b\"])으로")
            elif hdr is not None and not isinstance(hdr, list):
                bad.append(f"슬라이드.{i}(표): 표 header 는 열 이름 배열이어야 한다")
        if lo == "도식":
            # [P3계약 '26-09-06] 차트 4종(bar/hbar/line/donut) 허용 — svgfig.도식유형→svgfig.유형으로 확장.
            t = _객체(s.get("도식")).get("type")
            if t not in svgfig.유형:
                bad.append(f"슬라이드.{i}(도식): 도식 type {t!r} — 카탈로그에 없다"
                           f"({', '.join(svgfig.유형)})")
            else:
                # 실측 2026-09-06: 타입-배열키가 어긋나면(예: converge인데 단계 키) 원본 JSON엔
                # 글자가 있어도 화면엔 라벨이 하나도 안 찍힌다 — _텍스트있나(줄 324)의 원본 스캔은
                # 이걸 못 잡는다(글자 자체는 doc 안에 있으니까). 정규화(_도식정규화) 뒤 정본 자리만
                # 다시 훑는다 — 정본 배열이 아예 없는 타입(세트 기반 진짜 stack·차트 3종)은
                # _도식정본배열키 에 없어서 이 검사 밖이다(차트 라벨은 다른 규칙의 몫이다).
                정규도식 = _도식정규화(dict(_객체(s.get("도식"))))
                if 정규도식.get("type") in _도식정본배열키 and not _도식라벨텍스트들(정규도식):
                    bad.append(f"슬라이드.{i}(도식): 도식 라벨이 비어 있음 — "
                               f"type={정규도식.get('type')!r}의 정본 배열·시행·결과가 전부 비어 있다")
                elif 정규도식.get("type") in svgfig.차트유형:
                    # 차트 4종(bar/hbar/line/donut) 하드 게이트 — 값이 하나도 없거나 전부
                    # 0이면 svgfig.js 가 "축 0만 있는 빈 차트"를 그린다(실측 bench3, 근거는
                    # _차트값문제 docstring). 별칭·숫자 문자열 되살리기까지 마친 뒤 본다.
                    정규차트 = _차트정규화(정규도식)
                    문제 = _차트값문제(정규차트)
                    if 문제:
                        bad.append(f"슬라이드.{i}(도식): {문제}")
        if lo == "간지" and not str(s.get("제목") or "").strip():
            bad.append(f"슬라이드.{i}(간지): 제목이 없다")
        if lo == "어젠다":
            항목 = s.get("항목")
            if not isinstance(항목, list) or len(항목) < 2:
                bad.append(f"슬라이드.{i}(어젠다): 목차 항목이 {len(항목) if isinstance(항목, list) else 0}개"
                           f" — 2개 이상이어야 한다")
        if lo == "마무리":
            항목 = s.get("항목")
            항목수 = len(항목) if isinstance(항목, list) else 0
            문구 = str(s.get("문구") or "").strip()
            if 항목수 < 1 and not 문구:
                bad.append(f"슬라이드.{i}(마무리): 내용이 없다 — 항목 1개 이상이거나 문구가 있어야 한다")
        if lo == "큰숫자":
            # 정규화(_큰숫자정규화, 별칭 포함) 뒤에도 값 있는 카드가 없으면 카드판이 빈 백지다 —
            # _텍스트있나 는 헤드 글자만으로 통과시킨다(실측 2026-09-06 라이브 덱 5장).
            지표 = s.get("지표")
            값있음 = [m for m in 지표 if isinstance(m, dict) and str(m.get("값") or "").strip()] \
                if isinstance(지표, list) else []
            if not 값있음:
                bad.append(f"슬라이드.{i}(큰숫자): 지표가 비어 있다 — \"지표\" 배열에 "
                           f"{{값,단위,라벨,변화}} 카드를 2~4개 넣어라(다른 키 이름에 넣지 마라)")
        if lo == "인용":
            if not str(s.get("인용문") or "").strip():
                bad.append(f"슬라이드.{i}(인용): 인용문이 없다")
            if not str(s.get("출처") or "").strip():
                # 인용 장의 출처는 말한 사람이다('26-09-30 주관 판정 X1) — 비었다고 사람을 지어 채우라고 밀지 않는다
                bad.append(f"슬라이드.{i}(인용): 말한 사람(출처)이 없다 — 자료에 적힌 말한 사람을 \"출처\"에 적고, 자료에 말한 "
                           "사람이 없으면 이 장을 인용 대신 요지 장(레이아웃 \"본문\" — 헤드메시지와 항목)으로 바꾼다. 사람을 지어 채우지 않는다")
        if not _텍스트있나(s):
            bad.append(f"슬라이드.{i}({lo}): 렌더 텍스트가 0자다 — 화면에 글자가 하나도 없다")
        if lo == "이미지" and not (s.get("이미지") or {}):
            bad.append(f"슬라이드.{i}(이미지): 이미지 스펙이 없다")
        if lo == "픽토그램":
            ps = s.get("픽토그램") or []
            if not isinstance(ps, list):
                ps = []
            if not ps:
                bad.append(f"슬라이드.{i}(픽토그램): 픽토그램 목록이 없다")
            # 라이브러리에 없는 아이콘은 더는 하드로 막지 않는다('26-09-27, 3차 측정 재발) —
            # _픽토그램정규화(별칭)가 먼저 옮기고, 그래도 못 찾으면 렌더가 그 아이콘 하나만
            # 그림 없이 라벨·설명 글로 낸다(소프트 경고로 남긴다). 약한 모델이 아이콘 하나
            # 때문에 덱 전체를  반려당하던 것(실측 bench3 P/exaone-s6)을 막는다.
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


# 주제어형 헤드 판정 — 이 명사로 끝나면서 서술어 꼬리가 없으면 "제목"이지 "주장"이 아니다.
_주제어꼬리 = ("계획", "현황", "개요", "방안", "일정", "예산", "결과", "배경", "목표", "요청", "효과",
           "체계", "전략", "과제", "방향", "성과", "사항", "내용", "구성", "절차", "추진", "분석")
_서술어꼬리 = ("다", "함", "음", "됨", "임", "요", "니다", "한다", "된다", "있다", "이다", "필요")


_설득신호 = ("요청", "승인", "건의", "제안", "협조", "편성", "결정", "검토", "의결", "재가")


def _목적(doc):
    """문서 목적 설득|보고 — 사장님 판정 2026-09-07(헤드 문체는 목적에 따라 다르다). 최상위 "목적" 키가
    우선(별칭 정규화), 없으면 표지 부제·마무리 항목의 결정 요청 신호로 추정한다(정본: slides.문체.헤드_목적별)."""
    v = str(doc.get("목적") or "").strip()
    if v:
        if any(k in v for k in ("설득", "제안", "승인", "요청", "persua", "propos")):
            return "설득"
        if any(k in v for k in ("보고", "현황", "결과", "report", "inform")):
            return "보고"
    글 = [str(_객체(doc.get("표지")).get("부제") or "")]
    for sl in (doc.get("슬라이드") or []):
        if isinstance(sl, dict) and sl.get("레이아웃") == "마무리":
            글.append(str(sl.get("헤드메시지") or ""))
            for it in (sl.get("항목") or []):
                글.append(str(_객체(it).get("text") or _객체(it).get("텍스트") or it))
    본 = " ".join(글)
    return "설득" if any(k in 본 for k in _설득신호) else "보고"


def _수치수(t):
    """문장 속 숫자 덩어리 수(정규식 없이) — '90일, 41건, 12명' → 3."""
    n, 앞 = 0, False
    for c in str(t):
        d = c.isdigit()
        if d and not 앞:
            n += 1
        앞 = d
    return n


def _소프트지표(doc):
    """조립 시점 소프트 게이트(경고만, 덱은 안 버린다) — hard 와 달리 자가수정을 끊지 않는다.
    audit.js AUDIT_SPEC.slides 가 **렌더된 DOM** 에서 재는 같은 이름의 지표(bullet_only_ratio 등)를
    **JSON 단계**에서 미리 대략 재는 조기경보다 — 두 측정이 서로 다른 단계라 완전히 같은 값은
    아니지만(픽토그램 개수·자유배치 등 렌더 세부는 DOM 쪽이 정확) 조립 즉시 로그에 남아 다음
    자가수정 턴이 곧바로 반영할 수 있다는 게 이 단계 측정의 값어치다.
    돌려주는 값: (경고문 목록, {글머리만, 종류, 최대연속, 시각당장, 백지})."""
    장들 = [s for s in (doc.get("슬라이드") or []) if isinstance(s, dict)]
    n = len(장들)
    if n == 0:
        return [], {"글머리만": 0.0, "종류": 0, "최대연속": 0, "시각당장": 0.0, "백지": 0}

    def _시각수(s):
        lo = s.get("레이아웃")
        if lo == "픽토그램":
            ps = s.get("픽토그램")
            return len(ps) if isinstance(ps, list) else 0
        return 1 if lo in ("도식", "표", "이미지", "큰숫자") else 0

    def _글머리수(s):
        # audit.js 의 '.sl-l1…, .sl-agenda-i, [data-ent="항목"]' 선택자와 같은 뜻 —
        # 항목(불릿) 개체가 렌더되는 자리를 JSON 필드에서 센다.
        lo = s.get("레이아웃")
        if lo in ("본문", "마무리", "어젠다"):
            항목 = s.get("항목")
            return len(항목) if isinstance(항목, list) else 0
        if lo == "비교":
            좌 = _객체(s.get("좌")).get("항목")
            우 = _객체(s.get("우")).get("항목")
            return (len(좌) if isinstance(좌, list) else 0) + (len(우) if isinstance(우, list) else 0)
        if lo == "매트릭스":
            사분면 = s.get("사분면")
            사분면 = 사분면 if isinstance(사분면, list) else []
            return sum(len(_객체(q).get("항목") or []) if isinstance(_객체(q).get("항목"), list) else 0
                       for q in 사분면)
        return 0

    시각합 = 글머리만 = 0
    for s in 장들:
        v, b = _시각수(s), _글머리수(s)
        시각합 += v
        if b > 0 and v == 0:
            글머리만 += 1

    레이아웃값 = [s.get("레이아웃") for s in 장들]
    종류 = len(set(레이아웃값))
    최대연속 = 연속 = 0
    이전 = object()          # 슬라이드에 절대 안 나올 값 — None 레이아웃과도 안 섞인다
    for l in 레이아웃값:
        연속 = 연속 + 1 if l == 이전 else 1
        최대연속 = max(최대연속, 연속)
        이전 = l
    백지 = sum(1 for s in 장들 if not _텍스트있나(s))

    지표 = {"글머리만": round(글머리만 / n, 2), "종류": 종류, "최대연속": 최대연속,
          "시각당장": round(시각합 / n, 2), "백지": 백지}

    경고 = []
    목적 = _목적(doc)
    if 지표["글머리만"] > 0.25:   # 실측 보정 2026-09-07: 실물 부처 덱은 0.00 — 0.30→0.25
        경고.append(f"글머리만 비율 {지표['글머리만']} — 0.25 초과(장마다 시각 프리미티브를 먼저 고른다)")
    if n >= 8 and 종류 < 5:
        경고.append(f"레이아웃 종류 {종류} — 장수 {n}장인데 5종 미만(단조롭다)")
    if 최대연속 > 2:
        경고.append(f"같은 레이아웃이 {최대연속}장 연속 — 2장을 넘는다")
    for i, s in enumerate(장들):
        헤드길이 = len(str(s.get("헤드메시지") or ""))
        if 헤드길이 > 40:
            경고.append(f"슬라이드.{i}: 헤드메시지가 {헤드길이}자 — 40자를 넘는다")
        항목 = s.get("항목")
        if isinstance(항목, list) and len(항목) > 6:
            경고.append(f"슬라이드.{i}: 항목이 {len(항목)}개 — 장당 6개를 넘는다")
        # 심사 감점 상위 2종(2026-09-06 덱 A v3 3.92): ① 주제어형 헤드("예산 및 일정 계획" — 표 제목처럼
        # 읽힘) ② 수치가 글머리 문장 속에 묻힌 장(90일·사례·12명을 큰숫자·차트 없이 나열). 둘 다 경고만 —
        # 소프트 재시도 힌트로 모델에 되먹인다(하드로 올리면 약한 모델의 재시도가 소진된다).
        lo = s.get("레이아웃")
        헤드 = str(s.get("헤드메시지") or "").strip().rstrip(".。!?")
        # 주제어형 경고는 목적=설득 에만 — 보고형은 주제어형 제목이 실물 관행(사장님 판정 2026-09-07)
        if 목적 == "설득" and lo not in ("표지", "어젠다", "간지") and 헤드 and 헤드.endswith(_주제어꼬리) \
                and not 헤드.endswith(_서술어꼬리):
            경고.append(f"슬라이드.{i}: 헤드메시지가 주제어형('{헤드[-6:]}') — 완결된 주장으로"
                        " (예: '…으로 30일 단축한다', '…이 필요하다', 수치 든 결론)")
        if _글머리수(s) > 0 and _시각수(s) == 0 and lo in ("본문", "마무리"):
            글 = " ".join(str(_객체(x).get("텍스트") or _객체(x).get("text") or x) for x in (항목 or []))
            수치 = _수치수(글)
            if 수치 >= 2:
                경고.append(f"슬라이드.{i}: 수치 {수치}개가 글머리 속에 묻힘 — 큰숫자(지표 2~4개)나 차트로")
        if s.get("레이아웃") == "도식":
            # gate_check 의 하드 규칙(라벨 0자)과 같은 정규화를 재사용한 소프트 경고 —
            # 라벨은 있는데(하드 통과) 정본 배열이 1개뿐이면 절차·구조가 안 보인다(실측 2026-09-06).
            정규도식 = _도식정규화(dict(_객체(s.get("도식"))))
            if 정규도식.get("type") in _도식정본배열키:
                항목수 = len(_도식정본배열(정규도식))
                if 정규도식.get("type") == "compare" and isinstance(정규도식.get("후"), list):
                    항목수 += len(정규도식["후"])     # 비교판은 두 판을 합쳐 센다
                if 항목수 <= 1:
                    경고.append(f"슬라이드.{i}: 도식 항목 {항목수}개 — 절차/구조가 안 보인다")
    마무리들 = [i for i, s in enumerate(장들) if s.get("레이아웃") == "마무리"]
    if len(마무리들) != 1:
        경고.append(f"마무리 장이 {len(마무리들)}개 — 정확히 1개여야 한다")
    elif 마무리들[0] != n - 1:
        경고.append("마무리 장이 마지막 장이 아니다")
    if 장들[0].get("레이아웃") == "마무리":
        경고.append("표지 다음 장이 곧바로 마무리다")
    return 경고, 지표


def _정렬st(정렬맵, path):
    """경로별 정렬 오버레이(doc['_정렬'][path]) → text-align 스타일 조각. 없으면 빈 문자열.
    텍스트는 문자열이라 개체 필드를 못 다는 대신, 편집기가 이 경로맵을 왕복한다(전 요소 정렬)."""
    v = (정렬맵 or {}).get(path)
    return f' style="text-align:{_ALIGN_CSS[v]}"' if v in _ALIGN_CSS else ""


def _항목들(items, base, e, 정렬맵=None):
    """개조식 항목 목록 → <p class="sl-l{n}"> 나열. press 와 같은 속성 잠금."""
    out = []
    for j, it in enumerate(items or []):
        if isinstance(it, str):        # 모델이 항목을 {level,text} dict 대신 맨 문자열로 낼 때
            it = {"text": it}          # 크래시 대신 기본 위계(1)의 텍스트 항목으로 흡수한다
        lv = 속성값.열거(it.get("level"), tuple(마커), f"{base}.{j}.level", 기본=1)
        mk = 마커.get(lv, "□")
        _p = f"{base}.{j}.text"
        out.append(f'      <p class="sl-l{lv}" data-ent="항목"{_정렬st(정렬맵, _p)}>'
                   f'<span class="mk">{mk}</span>{NBSP}'
                   f'<span class="tx" data-path="{e(_p)}">{e(it.get("text", ""))}</span>'
                   f'</p>\n')
    return "".join(out)


def _표(tb, base, e):
    cap = (f'<div class="sl-tbl-caption">{e(tb.get("캡션", ""))}</div>'
           if tb.get("캡션") else "")
    # 게이트가 구조를 걸러도, 렌더는 절대 안 죽어야 한다(백스톱) — header·row 비리스트를 강제하고,
    # 셀 값도 문자열로 강제한다(e()=html.escape 는 숫자·None 을 받으면 죽는다: 모델이 수치 셀을
    # 문자열이 아닌 int 로 내는 흔한 이탈).
    # '26-09-29 표 재설계 P1: 표 몸은 build/표꼴.py 공용(병합·열폭·열정렬·강조 — PPTX 수확이 병합·칸 안
    # 줄바꿈을 옮긴다). 옛 덱은 첫 열 칠을 기본으로 안 켠다(테마 표 모양 그대로)
    return (f'      <div class="sl-table-wrap" data-ent="표"{_정렬속성(tb)} data-path="{e(base)}">'
            f'{cap}{표꼴.표html(tb, "sl-table", 첫열기본=False)}</div>\n')


def _도식정규화(fg):
    """EXAONE 가 도식을 svgfig 스키마(한글 키·문자열/라벨) 대신 영문 객체 구조(steps/nodes/layers,
    {id,label,desc})로 내는 흔한 이탈을 svgfig.js 가 읽는 꼴로 옮긴다 — 안 그러면 svgfig 가 한글
    키(단계/요건/노드/…)를 못 찾아 **도식이 빈 채로 그려진다**(실측 2026-09-04, aside). 편집기
    remount·AI 재작성도 이 한글 스키마를 전제하므로 여기서 한 번 정규화하면 세 곳이 다 산다."""
    if not isinstance(fg, dict):
        return fg
    fg = dict(fg)
    t = fg.get("type")

    def _라벨(x):
        return (x.get("label") or x.get("라벨") or x.get("이름") or "") if isinstance(x, dict) else str(x or "")

    def _문자열들(arr):
        return [_라벨(x) for x in arr] if isinstance(arr, list) else []

    def _주체들(arr):   # {label,desc} → {라벨, 주체(부제)}
        out = []
        for x in (arr if isinstance(arr, list) else []):
            if isinstance(x, dict):
                d = {"라벨": _라벨(x)}
                sub = x.get("desc") or x.get("주체")
                if sub:
                    d["주체"] = sub
                out.append(d)
            else:
                out.append({"라벨": str(x or "")})
        return out

    if t in ("process", "cycle") and fg.get("steps") is not None and "단계" not in fg:
        fg["단계"] = _주체들(fg.get("steps"))
    elif t == "converge" and fg.get("nodes") is not None and "요건" not in fg:
        fg["요건"] = _문자열들(fg.get("nodes"))
        if fg.get("center") is not None and not fg.get("시행"):
            fg["시행"] = _라벨(fg.get("center"))
        if fg.get("outputs") is not None and not fg.get("결과"):
            fg["결과"] = " · ".join(_문자열들(fg.get("outputs")))
    elif t == "strategy" and fg.get("strategies") is not None and "전략" not in fg:
        fg["전략"] = fg.get("strategies")
    elif t == "relation" and fg.get("nodes") is not None and "노드" not in fg:
        fg["노드"] = _주체들(fg.get("nodes"))
        if fg.get("edges") and "연결" not in fg:
            fg["연결"] = fg.get("edges")
    elif t == "compare":
        # 비교판('26-09-29 격자 도식 P2) — 영문·유의 키(before/after, as_is/to_be, 현행/개선)를 전·후로
        for 원, 정 in (("before", "전"), ("as_is", "전"), ("asis", "전"), ("현행", "전"), ("기존", "전"),
                      ("after", "후"), ("to_be", "후"), ("tobe", "후"), ("개선", "후"), ("변경", "후")):
            if isinstance(fg.get(원), list) and not isinstance(fg.get(정), list):
                fg[정] = [_라벨(x) if isinstance(x, dict) else str(x or "") for x in fg[원]]
    elif t == "stack" and fg.get("layers") is not None:
        # svgfig 의 stack 은 쌓은 막대 차트다. EXAONE 는 '계층 구조'로 오용하니 세로 절차로 강등해
        # 라벨을 살린다(빈 막대보다 낫다).
        fg["type"] = "process"; fg["단계"] = _주체들(fg.get("layers"))

    # ---- 타입↔배열키 정합: 데이터가 진실이다 ----
    # 실측 2026-09-06(서버 EXAONE): {"type":"converge","단계":["센서 도입","데이터 분석","실시간
    # 대응"],"시행":"","결과":""} — 타입은 converge 인데 배열키는 단계(process 전용)이고 시행·
    # 결과는 둘 다 빈 문자열. 영문키 매핑(위)은 english→한글 이탈만 잡지 이 "한글 키 타입 불일치"는
    # 못 잡아서, svgfig.R.converge 가 요건을 못 찾아 라벨 없는 빈 박스 2개+화살표만 그렸다(백지 장이
    # 하드 게이트를 통과해 나간 사고). type 라벨보다 데이터가 실제로 담고 있는 배열 쪽을 믿는다 —
    # 정본 배열키가 비어 있는데 다른 타입의 정본 배열키가 채워져 있으면 타입을 그 데이터 쪽으로
    # 바꾼다(예: converge+단계→process, process+요건→converge, strategy+단계→process,
    # relation+단계→process).
    _정본키 = {"process": "단계", "cycle": "단계", "converge": "요건",
              "strategy": "전략", "relation": "노드"}
    _키의타입 = {"단계": "process", "요건": "converge", "전략": "strategy", "노드": "relation"}
    cur_t = fg.get("type")
    정본키 = _정본키.get(cur_t)
    if 정본키 and not fg.get(정본키):
        for 다른키, 다른타입 in _키의타입.items():
            if 다른키 != 정본키 and fg.get(다른키) and 다른타입 != cur_t:
                fg["type"] = cur_t = 다른타입
                break
    # converge 는 요건이 있어도 시행·결과가 둘 다 비면 화살표 두 개짜리 깡통이라 의미가 없다 —
    # 요건을 단계로 옮겨 process 로 강등한다(내용은 지어내지 않는다, 있는 요건만 그대로 옮긴다).
    if cur_t == "converge" and fg.get("요건") and not fg.get("시행") and not fg.get("결과"):
        fg["단계"] = fg.pop("요건")
        fg["type"] = "process"

    # 원소 안 라벨 폴백 — 라벨 ?? label ?? name ?? 이름 ?? 제목 ?? text ?? title(svgfig lab 과 같은
    # 순서). strategy 컬럼처럼 이미 자기 라벨 필드(제목)를 쓰는 원소도 라벨을 나란히 채워둔다 —
    # 게이트가 정본 배열을 라벨 하나로 훑을 때 필드명을 또 갈라 안 봐도 되게.
    _라벨키후보 = ("label", "name", "이름", "제목", "text", "title")
    for v in fg.values():
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and not it.get("라벨"):
                    for k in _라벨키후보:
                        if it.get(k):
                            it["라벨"] = it[k]
                            break
    return fg


# 도식 타입별 정본 배열키 — process/cycle=단계, converge=요건, relation=노드, strategy=전략.
# _도식정규화 의 타입↔배열키 정합과 gate_check/​_소프트지표 의 라벨 스캔이 같은 지도를 쓴다
# (하나를 고치면 셋 다 같이 맞아야 한다).
_도식정본배열키 = {"process": "단계", "cycle": "단계", "converge": "요건",
              "relation": "노드", "strategy": "전략",
              # 비교판('26-09-29 격자 도식 P2) — 정본 배열이 둘(전·후)이다. 여기엔 '전'을 적고, 라벨 스캔
              # (_도식라벨텍스트들)과 항목 수(_소프트지표)가 '후'를 더한다. 여기 없으면 빈 비교판이 게이트를 지난다
              "compare": "전"}


def _도식정본배열(fg):
    """정규화된 도식에서 타입에 맞는 정본 배열(리스트)만 뽑는다 — 없거나 리스트가 아니면 빈 리스트."""
    key = _도식정본배열키.get((fg or {}).get("type"))
    arr = (fg or {}).get(key) if key else None
    return arr if isinstance(arr, list) else []


def _도식라벨텍스트들(fg):
    """정규화된 도식에서 화면에 찍힐 라벨 글자만 모은다 — 정본 배열 원소 라벨 + converge 의
    시행·결과 + strategy 컬럼 제목까지. 원소가 dict 면 라벨 필드를(제목 포함) 우선하고
    아니면 그대로 문자열화한다. 게이트가 '라벨 없는 빈 도식'을 잡는 유일한 창구다 — 원본 JSON은
    글자가 있어도(예: 엉뚱한 배열키 아래) 화면엔 하나도 안 찍힐 수 있어서, 반드시 정규화 후
    정본 자리만 본다."""
    if not isinstance(fg, dict):
        return []
    t = fg.get("type")

    def _글자(x):
        if isinstance(x, dict):
            return str(x.get("라벨") or x.get("제목") or "")
        return str(x or "")

    out = [_글자(x) for x in _도식정본배열(fg)]
    if t == "converge":
        out += [str(fg.get("시행") or ""), str(fg.get("결과") or "")]
    if t == "compare" and isinstance(fg.get("후"), list):
        out += [_글자(x) for x in fg["후"]]
    return [s for s in out if s.strip()]


# ── 차트 4종(bar/hbar/line/donut) 전용 정규화 — process류 _도식정규화 와 같은 자리·같은 취지.
# 실측 2026-09-26(bench3 qwen/gemma): 차트의 계열/값/시점/항목 키에는 영문 별칭 매핑이 전혀
# 없어(map-fix-sites.md ③) 모델이 series/data/values/labels 를 쓰면 값이 조용히 사라졌다.
_차트키별칭 = {"series": "계열", "data": "계열", "categories": "시점", "labels": "시점",
           "x": "시점", "xAxis": "시점", "items": "항목"}
_계열원소별칭 = {"name": "이름", "values": "값", "data": "값", "value": "값", "label": "이름"}
_항목원소별칭 = {"name": "이름", "value": "값", "label": "이름"}
# 전체가 숫자(+부호·소수점)뿐이거나, 숫자 뒤에 짧은 단위 한 조각(%·명·건 …)만 붙었을 때만
# 되살린다. "420/500명"처럼 숫자가 여럿 섞이면 어느 쪽을 뽑을지 코드가 알 도리가 없어
# 그대로 둔다 — 이런 값은 애초에 '계열' 차트가 아니라 '단계' 글목록(process·큰숫자감)이라,
# 억지로 뽑기보다 아래 _차트값문제 의 게이트가 "숫자 계열이 필요하다"로 막는 편이 낫다
# (설계 지시, map-fix-sites.md ③).
_수형패턴_온전 = re.compile(r'^[+-]?\d+(?:\.\d+)?$')
_수형패턴_단위 = re.compile(r'^([+-]?\d+(?:\.\d+)?)\s*([^\d\s,]{1,3})$')
# 배수사(천·만·억·조)가 붙은 단위는 되살리지 않는다 — "5천만"·"1.2억"을 그냥 5·1.2로
# 벗기면 실제 크기가 뒤집힌다(5천만<1.2억인데 5>1.2로 그려진다, 회귀 근거는 실측
# "5천만원"·"1.2억원" 두 값을 렌더한 막대 크기 비교, '26-09-27). 배수 없는 단위
# (%·명·건·개·원·점·일·회 …)만 대상이다.
_배수사 = ("천", "만", "억", "조")


def _수형(v):
    """차트 값 자리의 "84%"·"1,200명" 같은 숫자 문자열을 숫자로 되살린다(내용 변형이 아니라
    표기만 벗긴다). 못 읽으면(또는 배수 단위가 섞여 있으면) 원래 값을 그대로 돌려준다 —
    게이트가 '숫자 없음'(또는 '숫자가 아닌 값 섞임')으로 잡는다."""
    if isinstance(v, bool) or not isinstance(v, str):
        return v
    s = v.strip().replace(",", "")
    if not s:
        return v
    if _수형패턴_온전.match(s):
        return float(s) if "." in s else int(s)
    m = _수형패턴_단위.match(s)
    if m:
        단위 = m.group(2)
        if any(배수 in 단위 for 배수 in _배수사):
            return v   # 크기를 왜곡하므로 되살리지 않는다 — 게이트가 막는다
        n = m.group(1)
        return float(n) if "." in n else int(n)
    return v


def _차트정규화(fg):
    """차트 4종의 흔한 영문 키(series/data/values/labels/categories/name)를 정본 한글 키
    (계열/값/시점/이름·항목)로 옮기고, 값 자리의 숫자 문자열을 숫자로 되살린다. 정본 키가
    이미 있으면 안 건드린다(process류 _도식정규화 와 같은 보수적 원칙). 차트 유형이 아니면
    그대로 돌려준다."""
    if not isinstance(fg, dict) or fg.get("type") not in svgfig.차트유형:
        return fg
    fg = dict(fg)
    for 영, 한 in _차트키별칭.items():
        if 영 in fg and 한 not in fg:
            fg[한] = fg.pop(영)
    if fg.get("type") == "donut":
        항목 = fg.get("항목")
        if isinstance(항목, list):
            새항목 = []
            for it in 항목:
                if isinstance(it, dict):
                    it = dict(it)
                    for 영, 한 in _항목원소별칭.items():
                        if 영 in it and 한 not in it:
                            it[한] = it.pop(영)
                    if "값" in it:
                        it["값"] = _수형(it["값"])
                    새항목.append(it)
                elif isinstance(it, list) and len(it) >= 2:
                    새항목.append([it[0], _수형(it[1])])
                else:
                    새항목.append(it)
            fg["항목"] = 새항목
    else:
        계열 = fg.get("계열")
        if isinstance(계열, list):
            새계열 = []
            for s in 계열:
                if isinstance(s, dict):
                    s = dict(s)
                    for 영, 한 in _계열원소별칭.items():
                        if 영 in s and 한 not in s:
                            s[한] = s.pop(영)
                    if isinstance(s.get("값"), list):
                        s["값"] = [_수형(v) for v in s["값"]]
                    새계열.append(s)
                else:
                    새계열.append(s)
            fg["계열"] = 새계열
    return fg


def _차트값들(fg):
    """정규화된 차트에서 실제로 그려질 값만 모은다(bool 은 숫자로 안 친다 — True/False 가
    1/0 으로 새는 사고를 막는다, assemble_gongmun._s 와 같은 경계)."""
    if (fg or {}).get("type") == "donut":
        raw = []
        for it in (fg.get("항목") or []):
            if isinstance(it, dict):
                raw.append(it.get("값"))
            elif isinstance(it, list) and len(it) >= 2:
                raw.append(it[1])
        return raw
    raw = []
    for s in (fg.get("계열") or []):
        if isinstance(s, dict):
            raw.extend(s.get("값") or [])
    return raw


#  아래 네 메시지 머리글은 assemble_slides.조립하기() 가 "저장(편집 반영) 뒤 재조립"에서
# 이 하드 위반들만 소프트 경고로 낮추는 데 쓴다(_차트게이트_연성가능) — 문구를 바꾸면
# 그 상수도 같이 바꿔야 한다.
_차트게이트_연성가능 = ("막대 차트엔 숫자 계열이 필요하다", "차트 데이터에 숫자가 하나도 없다",
                  "차트 값이 전부 0이다", "차트 값에 숫자가 아닌 값이 섞여 있다",
                  "가로축(시점) 라벨이")


def _차트값문제(fg):
    """차트(bar/hbar/line/donut) 데이터가 실제로 그려질 수 있는가 — 계열[].값(도넛은
    항목[].값)에 숫자가 하나도 없거나 전부 0이면 svgfig.js 가 눈금 [0] 하나만 있는 빈 판을
    그린다(원인 분석: R.bar 293행 `if (typeof v !== "number") return`, 눈금() 의
    Math.max(...[],0)=0). 실측(bench3 gemma-s6): {"type":"bar","단계":["교육 이수(420/500명)",
    "콜백 회신율(94%)"]} 처럼 '단계' 글목록만 있는 경우는 숫자를 억지로 뽑지 않고 유형을
    바꾸라고 알린다(process·큰숫자 감이지 계열 차트감이 아니다).

    '26-09-27 추가 — 실측(review34/chart_adv.py, svgfig.js 를 node 로 직접 그려 확인):
    ① 숫자가 하나라도 있으면(0이 아니면) 통과시켰는데, **일부만 숫자고 나머지가 문자열**
       (예: donut 항목 값이 "약 70%"·30 섞임)이면 그 문자열 항목만 NaN 경로가 된다 — 섞이면
       하드로 막는다. ② bar/hbar/line 은 계열[].값만 보고 '시점'(가로축)은 전혀 안 봤는데,
       R.bar 가 `g.시점.forEach` 로 도는 이상 시점이 비면(또는 계열 길이보다 짧으면) 값이
       있어도 막대가 하나도 안 그려진다 — '단계' 판정과 같은 자리에서 함께 본다."""
    t = (fg or {}).get("type")
    값들 = _차트값들(fg)
    숫자들 = [v for v in 값들 if isinstance(v, (int, float)) and not isinstance(v, bool)]
    비숫자들 = [v for v in 값들 if not (isinstance(v, (int, float)) and not isinstance(v, bool))]
    if t == "donut":
        예시 = '{"type":"donut","항목":[{"이름":"정규직","값":72},{"이름":"기간제","값":28}]}'
        정본키 = "항목[].값"
        계열자리없음 = not isinstance(fg.get("항목"), list)
    else:
        예시 = '{"type":"bar","시점":["1월","2월"],"계열":[{"이름":"이수율","값":[84,90]}],"단위":"%"}'
        정본키 = "계열[].값"
        계열자리없음 = not isinstance(fg.get("계열"), list)
    if t != "donut" and 계열자리없음 and isinstance(fg.get("단계"), list) and fg.get("단계"):
        # 계열 자리가 아예 없고 '단계' 글목록만 있다(실측 bench3 gemma-s6) — process·큰숫자
        # 감이지 계열 차트감이 아니다. 숫자를 억지로 뽑지 않는다(설계 지시).
        return (f"막대 차트엔 숫자 계열이 필요하다 — 숫자가 없으면 type 을 process 로 바꾸거나 "
                f"큰숫자 레이아웃을 써라. {정본키} 예: {예시}")
    if not 숫자들:
        return f"차트 데이터에 숫자가 하나도 없다 — {정본키}에 실제 수치를 숫자로 넣어라(문자열·빈 배열 불가). 예: {예시}"
    if 비숫자들:
        return (f"차트 값에 숫자가 아닌 값이 섞여 있다({비숫자들!r}) — {정본키}는 전부 숫자여야 한다"
                f"(단위 표기는 벗겨지지만 배수 단위·복합 표기는 안 벗겨진다). 예: {예시}")
    if not any(v != 0 for v in 숫자들):
        return (f"차트 값이 전부 0이다(축 0만 있는 빈 차트가 된다) — 정말 전부 0이면 큰숫자·표로 "
                f"바꿔라. {정본키} 예: {예시}")
    if t != "donut":
        시점 = fg.get("시점")
        시점길이 = len(시점) if isinstance(시점, list) else 0
        최대계열길이 = max((len(s.get("값") or []) for s in (fg.get("계열") or [])
                       if isinstance(s, dict) and isinstance(s.get("값"), list)), default=0)
        if 시점길이 < 최대계열길이:
            return (f"가로축(시점) 라벨이 계열 값 개수보다 적다({시점길이}개 vs {최대계열길이}개) — "
                    f"svgfig 는 '시점' 배열을 따라 막대를 그리므로 시점이 모자라면 뒤쪽 값은 "
                    f"그려지지 않는다. '시점'에 계열과 같은 개수의 라벨을 채워라. 예: {예시}")
    return None


def _도식(fg, base, e):
    """SVG 도식 — 풀버전과 같은 svgfig(.fr-fig) 재사용. jachigan.js 가 그린다."""
    fg = _도식정규화(fg or {})
    fg = _차트정규화(fg)
    크기 = (fg or {}).get("크기")
    크기attr = f' data-크기="{e(str(크기))}"' if 크기 in ("크게", "가득") else ""
    return "      " + svgfig.render(fg).replace(
        'class="blk fr-fig"',
        f'class="blk fr-fig sl-fig"{크기attr} data-path="{e(base)}"', 1)


_이미지높이 = {1: "max-height:106mm;", 2: "max-height:98mm;", 3: "max-height:90mm;"}


def _이미지(img, name, base, e):
    """이미지(삽화·첨부 크롭) — 풀버전과 같은 imageasset 재사용. AI 생성물 표기까지 그대로.

    ('26-09-30 P2 실측) slides.css 는 그림 높이를 본문 높이(116mm) 그대로 두어, 높이가 먼저 차는 그림(4:3·1:1 생성
    그림)에 캡션·'AI 생성물' 배지가 붙으면 장이 8px 넘쳐 조판게이트가 hard 로 막았다. 그림 밑에 붙는 줄 수만큼
    그림 높이를 줄인다(값은 고정 표 — 카탈로그에 걸린 CSS 는 건드리지 않는다). 또 imageasset 의 폭(기본 80%)이
    고정 width 라 높이가 먼저 차는 그림은 가로로 늘어났다(4:3 1.88배·1:1 2.50배·16:9 1.41배 [잼]) — 슬라이드에서는
    폭을 max-width 로 바꿔 비율을 지킨다."""
    img = img or {}
    부속 = (bool(img.get("캡션")) + (img.get("출처") == "생성") + bool(img.get("함의") or img.get("설명")))
    h = imageasset.render(img, name).replace(
        'class="blk fr-fig fr-img"',
        f'class="blk fr-fig fr-img sl-img" data-path="{e(base)}"', 1)
    if "<img " in h:
        h = h.replace(' style="width:', ' style="' + _이미지높이.get(부속, "") + 'max-width:', 1)
    return "      " + h


def _픽토그램(items, base, e):
    """픽토그램 나열 — 의미 아이콘 + 라벨(+설명) 카드 줄. 애셋은 build/pictogram.py.

    _픽토그램정규화가 별칭으로 못 옮긴 아이콘은(라이브러리에 없다) 그 카드만 그림을 빼고
    라벨·설명 글로 낸다('26-09-27 — 하드 게이트 대신 소프트 강등, 실측 bench3 P/exaone-s6).
    pictogram.render() 자체는 미상 이름에 '안내(원+i)' 자리표시 SVG를 주지만, 여기서는 그
    자리표시조차 안 그린다 — 스펙이 요구하는 '그림 없이 글만'은 안내 아이콘도 없는 상태다."""
    import pictogram
    cards = []
    for j, it in enumerate(items or []):
        아이콘명 = it.get("아이콘", "")
        있음 = pictogram.has(아이콘명)
        svg_span = (f'<span class="sl-picto-ic" aria-hidden="true">{pictogram.render(아이콘명)}</span>'
                    if 있음 else "")
        cls = "sl-picto" if 있음 else "sl-picto sl-picto-noicon"
        라벨 = e(it.get("라벨", ""))
        설명 = e(it.get("설명", "")) if it.get("설명") else ""
        블 = (f'      <figure class="{cls}" data-ent="픽토그램" data-path="{e(base)}.{j}"'
              f' data-icon="{e(아이콘명)}">'
              f'{svg_span}'
              f'<figcaption class="sl-picto-l"><span class="tx" '
              f'data-path="{e(base)}.{j}.라벨">{라벨}</span></figcaption>')
        if 설명:
            블 += (f'<p class="sl-picto-d"><span class="tx" '
                   f'data-path="{e(base)}.{j}.설명">{설명}</span></p>')
        블 += '</figure>'
        cards.append(블)
    return (f'      <div class="sl-pictos" data-ent="픽토그램나열" data-path="{e(base)}">\n'
            + "\n".join(cards) + "\n      </div>\n")


# ── [P3계약 신설 '26-09-06] 비교·큰숫자·매트릭스·인용·타임라인 — 표준 블록 DOM(div/p/h3/h4)만,
# 절대좌표 없음(pptx CDP 크롭 호환). 각자 slides.css 의 .sl-compare/.sl-kpi/.sl-matrix/.sl-quote/
# .sl-timeline 컨테이너 하나로 감싼다 — audit.js 시각선택자('.sl-kpi' 포함)와 이름을 맞춘다.


def _비교(s, i, e):
    """좌우 대비 카드 — 현행 vs 개선, 방안A vs 방안B 류의 두 열 비교. 결론 줄은 선택."""
    out = ['      <div class="sl-compare">\n']
    for side, key in (("left", "좌"), ("right", "우")):
        col = _객체(s.get(key))
        out.append(f'        <div class="sl-compare-col sl-compare-{side}">\n')
        out.append(f'          <h3 class="sl-compare-title" data-ent="비교제목"><span class="tx" '
                   f'data-path="슬라이드.{i}.{e(key)}.제목">{e(col.get("제목", ""))}</span></h3>\n')
        out.append(_항목들(col.get("항목"), f"슬라이드.{i}.{key}.항목", e))
        out.append('        </div>\n')
    out.append('      </div>\n')
    if s.get("결론"):
        # 결론은 새 개체를 안 만든다(계약: 항목·헤드메시지만 재사용) — 헤드메시지와 같은 결로,
        # 완결 주장 한 줄이라 그 개체를 그대로 쓴다.
        out.append(f'      <p class="sl-compare-concl" data-ent="헤드메시지"><span class="tx" '
                   f'data-path="슬라이드.{i}.결론">{e(str(s["결론"]))}</span></p>\n')
    return "".join(out)


def _큰숫자(s, i, e):
    """대형 수치 카드 2~4개 — KPI·핵심 지표를 숫자 그대로 던진다(장당 1메시지의 숫자판)."""
    지표 = s.get("지표")
    지표 = 지표 if isinstance(지표, list) else []
    out = ['      <div class="sl-kpi">\n']
    for j, m in enumerate(지표):
        m = _객체(m)
        out.append('        <div class="sl-kpi-item">\n')
        단위 = m.get("단위")
        # 단위는 새 개체가 아니다(계약 목록 밖) — 값 옆에 작게, 편집 대상은 값·라벨·변화 셋뿐.
        단위span = f'<span class="sl-kpi-unit">{e(str(단위))}</span>' if 단위 else ""
        값 = str(m.get("값", ""))
        # 값 글자폭(한글 1.7·구두점 0.5·그 외 1)을 CSS 로 넘겨 카드 폭에 맞춰 글자를 자동 축소한다 —
        # "12,400"×4장이 70pt 로 이웃 카드를 덮던 겹침(심사 감점 1순위). 숫자 자리라 속성값.수 로 잠근다.
        폭 = sum(1.7 if ord(c) > 0x2E80 else (0.5 if c in ",." else 1) for c in 값)
        chars = 속성값.수(round(폭, 1), f"슬라이드.{i}.지표.{j}.값폭", 기본=3, 최소=1, 최대=20)
        out.append(f'          <div class="sl-kpi-val" data-ent="지표값" style="--kpi-chars:{chars}"><span class="tx" '
                   f'data-path="슬라이드.{i}.지표.{j}.값">{e(값)}</span>{단위span}</div>\n')
        out.append(f'          <div class="sl-kpi-label" data-ent="지표라벨"><span class="tx" '
                   f'data-path="슬라이드.{i}.지표.{j}.라벨">{e(m.get("라벨", ""))}</span></div>\n')
        if m.get("변화"):
            out.append(f'          <div class="sl-kpi-delta" data-ent="지표변화"><span class="tx" '
                       f'data-path="슬라이드.{i}.지표.{j}.변화">{e(str(m["변화"]))}</span></div>\n')
        out.append('        </div>\n')
    out.append('      </div>\n')
    return "".join(out)


_사분면순서 = ("좌상", "우상", "좌하", "우하")


def _매트릭스(s, i, e):
    """2×2 사분면 — 두 축 교차로 넷을 가른다(현재/향후 × 유지/전환 류). 축라벨 4개는 사분면
    바깥 위·옆 줄에, 사분면 내용은 그리드 칸마다 제목+항목으로."""
    축 = _객체(s.get("축"))
    가로 = 축.get("가로") if isinstance(축.get("가로"), list) else []
    세로 = 축.get("세로") if isinstance(축.get("세로"), list) else []
    사분면 = s.get("사분면") if isinstance(s.get("사분면"), list) else []
    out = ['      <div class="sl-matrix">\n']
    out.append('        <div class="sl-matrix-axis-x">\n')
    for k, t in enumerate(가로[:2]):
        out.append(f'          <span class="sl-axis-label" data-ent="축라벨" '
                   f'data-path="슬라이드.{i}.축.가로.{k}">{e(str(t))}</span>\n')
    out.append('        </div>\n')
    out.append('        <div class="sl-matrix-grid">\n')
    for k, q in enumerate(사분면[:4]):
        q = _객체(q)
        위치 = _사분면순서[k] if k < len(_사분면순서) else f"q{k}"
        out.append(f'          <div class="sl-matrix-q sl-matrix-{위치}">\n')
        out.append(f'            <h4 class="sl-matrix-title" data-ent="사분면제목"><span class="tx" '
                   f'data-path="슬라이드.{i}.사분면.{k}.제목">{e(q.get("제목", ""))}</span></h4>\n')
        out.append(_항목들(q.get("항목"), f"슬라이드.{i}.사분면.{k}.항목", e))
        out.append('          </div>\n')
    out.append('        </div>\n')
    out.append('        <div class="sl-matrix-axis-y">\n')
    for k, t in enumerate(세로[:2]):
        out.append(f'          <span class="sl-axis-label" data-ent="축라벨" '
                   f'data-path="슬라이드.{i}.축.세로.{k}">{e(str(t))}</span>\n')
    out.append('        </div>\n')
    out.append('      </div>\n')
    return "".join(out)


def _인용(s, i, e):
    """큰따옴표 인용 카드 — 선언·증언·원칙 한 문장을 세워 보인다. 출처는 기존 '출처' 개체
    재사용(바닥 각주와 같은 필드 — 조립기가 여기서 이미 보여줬으니 바닥엔 다시 안 찍는다)."""
    return (f'      <blockquote class="sl-quote">\n'
            f'        <p class="sl-quote-text" data-ent="인용문"><span class="tx" '
            f'data-path="슬라이드.{i}.인용문">{e(s.get("인용문", ""))}</span></p>\n'
            f'        <footer class="sl-quote-src" data-ent="출처"><span class="tx" '
            f'data-path="슬라이드.{i}.출처">{e(s.get("출처", ""))}</span></footer>\n'
            f'      </blockquote>\n')


def _타임라인(s, i, e):
    """가로 단계열 — 순서·일정을 점과 선으로 잇는다. 설명은 선택이라 있을 때만 붙인다."""
    단계 = s.get("단계")
    단계 = 단계 if isinstance(단계, list) else []
    out = ['      <div class="sl-timeline">\n']
    for j, st in enumerate(단계):
        st = _객체(st)
        out.append('        <div class="sl-timeline-step">\n')
        out.append('          <div class="sl-timeline-dot"></div>\n')
        out.append(f'          <div class="sl-timeline-when" data-ent="시점"><span class="tx" '
                   f'data-path="슬라이드.{i}.단계.{j}.시점">{e(st.get("시점", ""))}</span></div>\n')
        out.append(f'          <div class="sl-timeline-label" data-ent="단계라벨"><span class="tx" '
                   f'data-path="슬라이드.{i}.단계.{j}.라벨">{e(st.get("라벨", ""))}</span></div>\n')
        if st.get("설명"):
            out.append(f'          <p class="sl-timeline-desc" data-ent="항목"><span class="tx" '
                       f'data-path="슬라이드.{i}.단계.{j}.설명">{e(str(st["설명"]))}</span></p>\n')
        out.append('        </div>\n')
    out.append('      </div>\n')
    return "".join(out)


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


def _v2문서인가(doc):
    """판형 v2(부품 트리)로 조립할 문서인가 — 판형이 'v2' 이거나, 판형 키는 있는데 옛 슬라이드 배열이
    없을 때(값 오타 — _v2한건 이 '판형 오타'를 첫 줄로 되돌린다). 옛 문서(슬라이드 배열)에 '판형':'16:9'
    같은 값이 끼면 옛 경로로 간다('26-09-28 적대 검토 L5: 예전엔 키만 보고 빈 v2 표지를 냈다)."""
    if not isinstance(doc, dict) or "판형" not in doc:
        return False
    return doc.get("판형") == "v2" or "슬라이드" not in doc


def _문서섬(DOC_JSON, PROFILE_JSON):
    """fr-doc·fr-profile 섬 — 판형이 둘(옛·v2)이어도 섬을 짓는 자리는 이 하나다('26-10-01). 이어받기는 조립기마다 이
    섬이 정확히 하나라는 전제로 장르 분기 없이 문서를 되읽는다(verify_all 이어받기). 값은 부르는 쪽이 '</' 를 막아 준다."""
    return (f'<script type="application/json" id="fr-doc">{DOC_JSON}</script>\n'
            f'<script type="application/json" id="fr-profile">{PROFILE_JSON}</script>\n')


def build(doc):
    if _v2문서인가(doc):      # 판형 v2(부품 트리) — 아래 build_v2. 옛 문서는 이 줄을 안 탄다
        return build_v2(doc)
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
{_문서섬(DOC_JSON, PROFILE_JSON)}"""]
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
        # data-layout(신설 '26-09-06) — audit.js 가 이 속성으로 장별 레이아웃 다양성·연속을 잰다.
        parts.append(f'<section class="sl-page sl-{e(lo)}'
                     f'{" sl-free" if 자유 else ""}" data-ent="슬라이드" '
                     f'data-layout="{e(lo)}" data-slide-idx="{i}">\n')
        if lo == "어젠다":
            parts.append('      <h2 class="sl-head sl-head-plain">목차</h2>\n')
            # 어젠다는 카탈로그상 헤드메시지가 안 이끄는 흐름장이라 제목은 늘 '목차' 고정이지만,
            # 사용자·모델이 헤드메시지를 채워 보내는 경우가 있다(예: 결정사항을 앞 장에서
            # 먼저 밝히는 설계) — 예전엔 그 값을 조용히 버렸다(cli s6, '26-09-27). 값이 있으면
            # 목차 제목 아래 한 줄(부제)로 살리고 data-path 를 달아 편집·왕복에도 실린다.
            if str(s.get("헤드메시지") or "").strip():
                parts.append(f'      <p class="sl-tbl-caption" data-ent="헤드메시지"><span class="tx" '
                             f'data-path="슬라이드.{i}.헤드메시지">{e(s["헤드메시지"])}</span></p>\n')
            for j, t in enumerate(s.get("항목") or []):
                글 = t if isinstance(t, str) else str(t)
                _ap = f"슬라이드.{i}.항목.{j}"
                parts.append(f'      <p class="sl-agenda-i" data-ent="항목"{_정렬st(doc.get("_정렬"), _ap)}>'
                             f'<span class="tx" data-path="{_ap}">{e(글)}</span></p>\n')
        elif lo == "간지":
            parts.append(f'      <div class="sl-sec-no"><span class="tx" '
                         f'data-path="슬라이드.{i}.번호">{e(s.get("번호", ""))}</span></div>\n')
            parts.append(f'      <h2 class="sl-sec-title"><span class="tx" '
                         f'data-path="슬라이드.{i}.제목">{e(s.get("제목", ""))}</span></h2>\n')
        elif lo == "인용":
            # 헤드메시지가 선택이라 다른 헤드장과 같은 else 가지에 안 넣는다 — 있을 때만 h2 를 낸다.
            if str(s.get("헤드메시지") or "").strip():
                parts.append(f'      <h2 class="sl-head" data-ent="헤드메시지"><span class="tx" '
                             f'data-path="슬라이드.{i}.헤드메시지">{e(s.get("헤드메시지", ""))}</span></h2>\n')
            parts.append('      <div class="sl-body sl-body-인용">\n')
            parts.append(_인용(s, i, e))
            parts.append("      </div>\n")
        else:                # 헤드메시지가 이끄는 장 — 본문·표·도식·이미지·픽토그램·마무리·비교·큰숫자·매트릭스·타임라인
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
            elif lo == "비교":
                parts.append(_비교(s, i, e))
            elif lo == "큰숫자":
                parts.append(_큰숫자(s, i, e))
            elif lo == "매트릭스":
                parts.append(_매트릭스(s, i, e))
            elif lo == "타임라인":
                parts.append(_타임라인(s, i, e))
            if s.get("항목") and lo not in ("비교", "매트릭스", "타임라인"):
                # 비교·매트릭스·타임라인은 항목을 이미 자기 슬롯(좌우·사분면·단계) 안에서 그렸다 —
                # 여기서 또 슬라이드.{i}.항목 을 흘려 그리면 같은 텍스트가 두 번 찍힌다.
                parts.append(_항목들(s.get("항목"), f"슬라이드.{i}.항목", e, doc.get("_정렬")))
            elif lo == "마무리" and not s.get("항목") and s.get("문구"):
                # 마무리 내용 하드게이트의 대체 경로(항목 없이 문구 한 줄로도 유효) — 항목 개체 재사용.
                parts.append(f'      <p class="sl-l1" data-ent="항목"><span class="mk">□</span>{NBSP}'
                             f'<span class="tx" data-path="슬라이드.{i}.문구">{e(str(s["문구"]))}</span></p>\n')
            parts.append("      </div>\n")
        # 인용은 출처를 본문 안에서 이미 보여줬다(_인용) — 바닥에 또 찍으면 중복이라 여기선 뺀다.
        parts.append(_바닥({} if lo == "인용" else s, i, 쪽, e))
        parts.append("</section>\n")

    parts.append("""<script src="../svgfig.js?v="></script>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
<script src="../present.js?v="></script>
</body>
</html>
""")
    return "".join(parts).replace("</head>", 속성값.간격스타일(doc) + "</head>", 1)  # #3 개체 위/아래 간격


# ══════════════════════════════════════════════════════════════════════════
# 판형 v2 — 부품 트리 조립 경로('26-09-28)
#
# 문서 최상위에 `판형: "v2"` 가 있으면 이 경로를 탄다. 없으면 위 옛 경로(레이아웃 13종)를
# 그대로 탄다 — 옛 문서는 한 글자도 안 바뀐다(test/r16_slides16b.py 가 지킨다).
# 정본 모양: build/slides_v2.schema.json · 게이트: build/slides_v2_gate.py · 서식: build/slides_v2.css
#
# 모델은 부품 트리 JSON 만 쓴다. 좌표·비율·막대 길이·눈금·SVG·▲▼·번호·색·산출 꼬리 한 줄·
# 쪽번호는 여기서 만든다. 날것 HTML·색값·클래스는 문서에 들어올 자리가 없다(스키마가 막는다).
# 속성 자리 보간은 모두 속성값.수/열거 또는 escape 로 잠근다(인라인 호출 — 정적 잠금 검사).
# ══════════════════════════════════════════════════════════════════════════
import math

_V2프리셋 = {"data": "p-data", "briefing": "p-briefing", "keynote": "p-keynote"}
_V2밀도 = {"발표": "d-talk", "보고": "d-report", "배포": "d-handout"}
_V2머리변형 = {"머리띠": "hv-band", "번호사각": "hv-numbox", "눈썹라벨": "hv-eyebrow",
            "좌측막대": "hv-bar", "무장식": "hv-plain"}
_V2테마 = {"네이비": "", "청록": " th-청록", "감청": " th-감청", "자목": " th-자목", "숲": " th-숲", "먹": " th-먹"}
_V2유형 = ("표지", "목차", "간지", "한눈에보기", "카드열", "데이터", "비교", "일정", "체계도", "분야표",
         "표", "요청", "인용", "배포글", "자유", "마무리")
_V2아이콘 = {"야간": "moon", "고령층": "elder", "상담": "chat", "시설": "home", "완료": "check", "문서": "doc",
          "안전": "shield", "전화": "phone", "일정": "cal", "사람": "people", "돈": "money", "누리집": "web",
          "가족": "family", "도구": "tool", "목표": "target", "차트": "chart"}
_V2상태 = {"완료": "is-done", "진행": "is-doing", "운영": "is-doing", "주의": "is-watch", "지연": "is-late",
         "예정": "is-plan", "목표": "is-goal"}
_V2단계상태 = {"완료": " is-done", "목표": " is-goal", "지연": " is-late", "진행": "", "운영": "", "주의": "", "예정": ""}
_V2런 = {"": "", "강조": "hl", "수치": "r-num", "단위": "r-unit", "약하게": "r-weak"}
_V2강조 = {"보고": "hl", "설득": "hl hl--brand", "설명": "hl hl--brand"}
_V2판정 = {"좋음": " is-good", "나쁨": " is-bad", "중립": ""}
_V2방향 = {"증가": "▲", "감소": "▼", "유지": "―"}
_V2지표변형 = {"기본": "", "강조": " kpi--tint", "옅게": " kpi--soft", "반전": " kpi--inv", "목표": " kpi--goal"}
_V2카드바탕 = {"기본": "", "틴트": " card--tint", "주황": " card--accent", "옅게": " card--soft", "반전": " card--inv"}
_V2열정렬 = {"글": "", "수": "n", "가운데": "c"}
_V2들여 = {0: "", 1: " off-1", 2: " off-2"}
_V2줄틀 = {"1": "rows-1", "2": "rows-2", "1a": "rows-1a", "a1": "rows-a1", "fit": "is-fit"}
_V2늘림 = ("선차트", "가로막대", "점눈금", "표", "타임라인", "세로타임라인", "체계도", "색띠행")
_V2차트형 = ("가로막대", "선차트", "점눈금", "구성띠")
_V2원문자 = "①②③④⑤⑥⑦⑧⑨⑩"
_V2링둘레 = 2 * math.pi * 56

# 선 아이콘 16종(24×24, 선 2px) — 앞 10종은 시제품 ds 그대로, 뒤 6종(돈·누리집·가족·도구·목표·차트) 신설
_V2스프라이트 = """<svg class="ds-sprite" aria-hidden="true">
 <symbol id="i-moon" viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></symbol>
 <symbol id="i-elder" viewBox="0 0 24 24"><circle cx="11" cy="5" r="2.5"/><path d="M8 21l2-7-2-3 3-3 3 4 3 1M14 14l1 7M17 11l2 10"/></symbol>
 <symbol id="i-chat" viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/><path d="M8 10h8M8 13h5"/></symbol>
 <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></symbol>
 <symbol id="i-check" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></symbol>
 <symbol id="i-doc" viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></symbol>
 <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-4.5"/></symbol>
 <symbol id="i-phone" viewBox="0 0 24 24"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></symbol>
 <symbol id="i-cal" viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/></symbol>
 <symbol id="i-people" viewBox="0 0 24 24"><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.2c2.8.3 5 2.6 5 5.8"/></symbol>
 <symbol id="i-money" viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.8"/><path d="M6.5 9.5v5M17.5 9.5v5"/></symbol>
 <symbol id="i-web" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.3 3.6 5.2 3.6 8.5s-1.1 6.2-3.6 8.5c-2.5-2.3-3.6-5.2-3.6-8.5S9.5 5.8 12 3.5z"/></symbol>
 <symbol id="i-family" viewBox="0 0 24 24"><circle cx="8" cy="6.5" r="2.5"/><circle cx="16" cy="6.5" r="2.5"/><circle cx="12" cy="13" r="2"/><path d="M4 20v-4.5C4 13 5.8 11.5 8 11.5M20 20v-4.5c0-2.5-1.8-4-4-4M9 20v-2.5c0-1.7 1.3-2.5 3-2.5s3 .8 3 2.5V20"/></symbol>
 <symbol id="i-tool" viewBox="0 0 24 24"><path d="M14.5 4.5a4 4 0 0 0 5 5L11 18a2.1 2.1 0 0 1-3-3z"/><path d="M14.5 4.5l-1.5 3 3.5 3.5 3-1.5"/><circle cx="8.3" cy="17.7" r="0.6"/></symbol>
 <symbol id="i-target" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/></symbol>
 <symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 4v16h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/></symbol>
</svg>
"""


def _v2스키마메타():
    import slides_v2_gate
    return slides_v2_gate.스키마()


def _v2수(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _v2수글(v):
    """조립기가 찍는 숫자 글 — 정수면 천 단위 쉼표, 소수면 끝 0 을 뗀다."""
    if not _v2수(v):
        return str(v if v is not None else "")
    if float(v).is_integer():
        return f"{int(v):,}"
    if abs(v) < 1:                     # 1 보다 작은 값은 유효 숫자 3자리까지('26-09-28 검토 L4: 0.125→'0.12'·0.00001→'0')
        자리 = min(6, max(2, 2 - math.floor(math.log10(abs(v)))))
        return f"{v:.{자리}f}".rstrip("0").rstrip(".")
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _v2소수자리(v):
    """소수 자리 수 — 고정 소수 10자리로 적어 끝 0 을 뗀다(지수 표기·계산 잔차에 안전)."""
    t = f"{float(v):.10f}".rstrip("0")
    return len(t.split(".")[1]) if "." in t else 0


def _v2퍼센트글(p):
    # 99.5 ≤ p < 100 은 '100%'로 반올림하면 완료를 주장한다 — 소수 한 자리를 내림으로(99.96 → 99.9%, round2 적대 검토 L1)
    if 99.5 <= p < 100:
        return f"{math.floor(p * 10) / 10:.1f}%"
    return f"{p:.0f}%" if abs(p) >= 10 or float(p).is_integer() else f"{p:.1f}%"


def _v2받침(글):
    """마지막 글자에 받침이 있나 — '38%·16시간은' / '4.2억원은' / '외 2개는'."""
    t = str(글).rstrip()
    if not t:
        return False
    ch = t[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    return ch in "0136789lmnLMN"


def _v2글자(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(str(r.get("t", "")) for r in v if isinstance(r, dict))
    return "" if v is None else str(v)


def _v2글(v, 경로, 목적, 틀=""):
    """글 슬롯 하나 → 인라인 span. 문자열이면 한 조각, 런 배열이면 묶음 span 안에 조각을
    **적힌 그대로 이어 붙인다**(조각 사이에 빈칸을 넣지 않는다 — 1단계 '가구 가' 깨짐)."""
    e = html.escape
    if isinstance(v, list):
        조각 = []
        for r, 런 in enumerate(v):
            if not isinstance(런, dict):
                continue
            역 = 속성값.열거(런.get("역할"), tuple(_V2런), f"{경로}.{r}.역할", 기본="")
            클 = _V2강조.get(목적, "hl") if 역 == "강조" else _V2런[역]
            조각.append(f'<span class="r {e(클)}" data-ent="런" data-path="{e(f"{경로}.{r}.t")}">'
                      f'{e(str(런.get("t", "")))}</span>')
        return f'<span class="{e(틀)} tx" data-path="{e(경로)}" data-runs="1">{"".join(조각)}</span>'
    return f'<span class="{e(틀)} tx" data-path="{e(경로)}">{e(_v2글자(v))}</span>'


def _v2강조쪼개기(메시지, 강조들):
    """머리.강조(메시지 안 부분 글자, 2곳까지) → [(글, 강조인가)] — 겹치면 앞의 것만."""
    구간 = []
    for k in (강조들 or [])[:2]:
        if not isinstance(k, str) or not k:
            continue
        at = 메시지.find(k)
        while at >= 0 and any(a < at + len(k) and at < b for a, b in 구간):
            at = 메시지.find(k, at + 1)
        if at >= 0:
            구간.append((at, at + len(k)))
    구간.sort()
    out, 앞 = [], 0
    for a, b in 구간:
        out.append((메시지[앞:a], False))
        out.append((메시지[a:b], True))
        앞 = b
    out.append((메시지[앞:], False))
    return [(t, h) for t, h in out if t]


def _v2아이콘(이름, 자리, 틀="ico"):
    e = html.escape
    키 = 속성값.열거(이름, tuple(_V2아이콘), 자리, 기본="")
    if not 키:
        return ""
    return f'<span class="{e(틀)}" data-derived="1"><svg><use href="#i-{_V2아이콘[키]}"/></svg></span>'


def _v2뱃지(상태, 자리):
    e = html.escape
    키 = 속성값.열거(상태, tuple(_V2상태), 자리, 기본="")
    if not 키:
        return ""
    return f'<span class="badge {_V2상태[키]}" data-derived="1">{e(키)}</span>'


def _v2증감(d, 경로, 곁글=""):
    """증감 칩 — 색은 판정(좋음/나쁨)으로, 기호(▲▼)는 방향으로. 기호는 파생 글.
    곁글(같은 칸에 이미 찍힌 글)이 칩 값과 같은 말이면 칩엔 기호만 둔다 — 표 증감 열에 '16%p ▼16%p' 처럼
    같은 값이 두 번 찍혔다('26-09-29 bench11 심사 3인)."""
    e = html.escape
    if not isinstance(d, dict):
        return ""
    방향 = 속성값.열거(d.get("방향"), tuple(_V2방향), f"{경로}.방향", 기본="유지")
    판정 = 속성값.열거(d.get("판정"), tuple(_V2판정), f"{경로}.판정", 기본="중립")
    # 곁글 부호가 방향과 반대('+9%p' 인데 감소)면 같은 값이라도 접지 않는다 — 부호 모순을 기호 하나로 가렸다(L3, 게이트 soft 가 알린다)
    반대 = (곁글.strip().startswith("+") and 방향 == "감소") or (곁글.strip()[:1] in ("-", "−", "△") and 방향 == "증가")
    값 = (f' <span class="tx" data-path="{e(경로 + ".값")}">{e(str(d.get("값")))}</span>'
         if d.get("값") and (반대 or not (곁글 and _v2같은말(re.sub(r"[+\-−△▲▼↑↓]", "", 곁글),
                                                         re.sub(r"[+\-−△▲▼↑↓]", "", str(d.get("값"))), 품기=False))) else "")
    return (f'<span class="delta{_V2판정[판정]}"><span data-derived="1">{_V2방향[방향]}</span>{값}</span>')


def _v2눈금(lo, hi, 개=4):
    """보기 좋은 눈금 — (시작, 끝, 간격, [눈금…])."""
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        d = abs(hi) * 0.1 or 1.0
        lo, hi = lo - d, hi + d
    raw = (hi - lo) / max(1, 개)
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    a = math.floor(lo / step + 1e-9) * step
    b = math.ceil(hi / step - 1e-9) * step
    n = int(round((b - a) / step))
    return a, b, step, [round(a + step * k, 10) for k in range(n + 1)]


def _v2칸폭px(폭):
    return 98 * 폭 - 24


# ── 배치 — 폭(12열)과 줄 ─────────────────────────────────────────────────
def _v2폭(c):
    w = c.get("폭") if isinstance(c, dict) else None
    return w if isinstance(w, int) and not isinstance(w, bool) and 1 <= w <= 12 else None


def _v2최소폭(항목):
    """칸(또는 조립기 세로묶음 ("묶음", [...]))의 최소 폭 — schema 부품의 x-최소폭(없으면 3)."""
    if 항목[0] == "묶음":
        return max([_v2최소폭(x) for x in 항목[1]] or [3])
    c = 항목[1]
    if c.get("부품") == "세로묶음":
        return max([_v2최소폭((0, x)) for x in c.get("칸") or [] if isinstance(x, dict)] or [3])
    m = (_v2스키마메타().get("$defs", {}).get(f"부품_{c.get('부품')}") or {}).get("x-최소폭")
    return m if isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 12 else 3


def _v2줄폭(줄):
    """한 줄의 칸들 → 폭 목록(합 12). 같은 폭으로 나눠 떨어지고 최소 폭을 지키면 같은 폭,
    아니면 최소 폭에서 시작해 남는 열을 가장 좁은 칸부터 하나씩 준다. 최소 폭 합이 12 를
    넘으면 None(이 줄에는 못 담는다)."""
    k = len(줄)
    최소 = [_v2최소폭(x) for x in 줄]
    if sum(최소) > 12:
        return None
    if 12 % k == 0 and all(12 // k >= m for m in 최소):
        return [12 // k] * k
    폭 = list(최소)
    for _ in range(12 - sum(폭)):
        j = min(range(k), key=lambda t: (폭[t], t))
        폭[j] += 1
    return 폭


def _v2고르게(묶, 요청폭=None):
    """칸 n개를 줄마다 고르게(12 를 나눠) — 부품 최소 폭(schema x-최소폭)을 지킨다.

    '26-09-28 적대 검토(렌더 M5·H1): 예전엔 폭만 12//n 으로 나눠 요청상자(최소 6)를 3열에, 체계도
    (최소 12)를 6열에, 짝카드(최소 6)를 4열에 앉혔고, 5~6칸이면 뒤 칸을 말없이 버렸다. 이제 한 줄에
    못 담으면 두 줄로 나누고(칸 수가 고른 쪽, 같으면 윗줄이 많은 쪽), 두 줄에도 못 담으면 칸마다
    한 줄씩 더 쓴다 — 버리지 않는다(2줄을 넘기면 _v2한건 이 되돌린다). `요청폭` 은 옛 호출 호환용."""
    n = len(묶)
    if n == 0:
        return []
    if n == 1:
        return [[(묶[0], 12, 0)]]
    if n <= 4:
        폭 = _v2줄폭(묶)
        if 폭 is not None:
            return [[(x, w, 0) for x, w in zip(묶, 폭)]]
    후보 = []
    for a in range(1, n):
        윗, 아랫 = 묶[:a], 묶[a:]
        if len(윗) > 4 or len(아랫) > 4:
            continue
        w1, w2 = _v2줄폭(윗), _v2줄폭(아랫)
        if w1 is not None and w2 is not None:
            후보.append((max(len(윗), len(아랫)), -len(윗), a, w1, w2))
    if 후보:
        _, _, a, w1, w2 = min(후보)
        return [[(x, w, 0) for x, w in zip(묶[:a], w1)], [(x, w, 0) for x, w in zip(묶[a:], w2)]]
    줄들, 줄 = [], []
    for x in 묶:                                   # 두 줄에도 못 담는다 — 앞에서부터 담기는 만큼씩
        if 줄 and (len(줄) >= 4 or _v2줄폭(줄 + [x]) is None):
            줄들.append(줄)
            줄 = []
        줄.append(x)
    줄들.append(줄)
    return [[(x, w, 0) for x, w in zip(z, _v2줄폭(z) or [12 // len(z)] * len(z))] for z in 줄들]


def _v2폭지킴(줄들):
    """기본 배치의 모든 칸이 최소 폭을 지키나."""
    return all(폭 >= _v2최소폭(항목) for 줄 in 줄들 for 항목, 폭, _ in 줄)


def _v2배치(유형, 칸목록):
    """칸 목록 → 줄들 [[(항목, 폭, 들여)]]. 항목 = (k, 칸) 또는 ("묶음", [(k, 칸)…])(조립기 세로묶음).

    폭을 다 적었으면 그대로 줄에 채운다(줄 합 12, 넘으면 다음 줄). 하나라도 없으면 유형별 기본
    배치(schema x-기본배치)를 쓴다 — 약한 모델은 폭을 안 쓴다."""
    묶 = [(k, c) for k, c in enumerate(칸목록) if isinstance(c, dict)]
    if not 묶:
        return []
    if all(_v2폭(c) for _, c in 묶):
        줄들, 줄, 합 = [], [], 0
        for x in 묶:
            w = _v2폭(x[1])
            if 합 + w > 12 and 줄:
                줄들.append(줄)
                줄, 합 = [], 0
            줄.append((x, w, 0))
            합 += w
        if 줄:
            줄들.append(줄)
        if 유형 == "인용" and len(줄들) == 1 and len(줄들[0]) == 1 and 줄들[0][0][1] == 10:
            줄들[0] = [(줄들[0][0][0], 10, 1)]
        return 줄들
    n = len(묶)
    if 유형 == "인용" and n == 1:
        return [[(묶[0], 10, 1)]]
    if n == 1 and 유형 == "요청":
        return [[(묶[0], 8, 2)]]                      # 요청상자 하나면 가운데 8열(넓은 빈 상자 막기)
    if n == 1:
        return [[(묶[0], 12, 0)]]
    줄들 = _v2유형배치(유형, 묶)
    # '26-09-28 적대 검토(렌더 H1·M5) — 유형별 배치가 칸을 버리거나(세로묶음 3칸·둘째 줄 4칸 상한)
    # 최소 폭을 어기면 고른 배치로 돌아간다. 버린 칸은 화면에서 말없이 사라진 자료였다.
    든 = sum(len(항목[1]) if 항목[0] == "묶음" else 1 for 줄 in 줄들 for 항목, _, _ in 줄)
    if 든 != n or not _v2폭지킴(줄들):
        return _v2고르게(묶)
    return 줄들


def _v2유형배치(유형, 묶):
    """유형별 기본 배치(schema x-기본배치) — 칸이 2개 이상일 때. 칸 수·최소 폭 확인은 부른 쪽이 한다."""
    n = len(묶)
    부품들 = [c.get("부품") for _, c in 묶]
    if 유형 == "데이터":
        차트 = next((x for x in 묶 if x[1].get("부품") in _V2차트형), None)
        if 차트 is not None:
            나머지 = [x for x in 묶 if x is not 차트]
            if len(나머지) == 1:
                return [[(차트, 7, 0), (나머지[0], 5, 0)]]
            return [[(차트, 7, 0), (("묶음", 나머지[:3]), 5, 0)]]
        return _v2고르게(묶)
    if 유형 == "요청":
        요청 = next((x for x in 묶 if x[1].get("부품") == "요청상자"), 묶[0])
        나머지 = [x for x in 묶 if x is not 요청]
        if len(나머지) == 1:
            return [[(요청, 7, 0), (나머지[0], 5, 0)]]
        return [[(요청, 7, 0), (("묶음", 나머지[:3]), 5, 0)]]
    if 유형 in ("표", "분야표"):
        if n == 2:
            return [[(묶[0], 8, 0), (묶[1], 4, 0)]]
        return [[(묶[0], 8, 0), (("묶음", 묶[1:4]), 4, 0)]]
    if 유형 == "비교":
        if n == 2:
            return [[(묶[0], 8, 0), (묶[1], 4, 0)]]
        return _v2고르게(묶)
    if 유형 == "일정":
        if "타임라인" in 부품들:
            띠 = next(x for x in 묶 if x[1].get("부품") == "타임라인")
            나머지 = [x for x in 묶 if x is not 띠]
            return [[(띠, 12, 0)]] + _v2고르게(나머지)    # 둘째 줄 칸이 많으면 줄이 늘고 _v2한건 이 되돌린다
        if "세로타임라인" in 부품들:
            세로 = next(x for x in 묶 if x[1].get("부품") == "세로타임라인")
            나머지 = [x for x in 묶 if x is not 세로]
            if len(나머지) == 1:
                return [[(세로, 4, 0), (나머지[0], 8, 0)]]
            return [[(세로, 4, 0), (("묶음", 나머지[:3]), 8, 0)]]
        return _v2고르게(묶)
    if 유형 == "배포글" and n == 2:
        return [[(묶[0], 6, 0), (묶[1], 6, 0)]]
    return _v2고르게(묶, 요청폭=True if (유형 == "한눈에보기" and "요청상자" in 부품들) else None)


def _v2어림(c, 폭, 글배율=1.0, 폭보정=1.0):
    """(늘릴 부품인가, 내용 높이 어림 px) — 빈 카드를 막는 '내용 맞춤' 판단에 쓴다.
    글배율 = 본문 글 크기 배율(밀도 × 채움 배율 --fz). 카드·글머리의 항목·하위 글은 그 크기로 줄바꿈과 줄 높이를
    다시 센다 — 글이 커지면 한 줄 글이 두세 줄로 꺾이는 것까지 든다(round3 적대 검토 H1: 하위 항목을 한 개 30px 로만
    세어, 키운 하위 글이 2~3줄로 꺾이며 카드가 쪽 밖으로 105px 넘쳤다). 글배율 1 이면 예전 어림과 같다(하위만 줄 수로)."""
    n = c.get("부품")
    if n == "세로묶음":
        자식 = [_v2어림(x, 폭) for x in c.get("칸") or [] if isinstance(x, dict)]
        return (any(a for a, _ in 자식), sum(h for _, h in 자식) + 24 * max(0, len(자식) - 1))
    if n == "체계도" and c.get("변형") == "이름만":
        return False, 64 + 16 + (80 if c.get("목표") else 0) + 150
    if n in _V2늘림:
        return True, 0
    안 = max(140, _v2칸폭px(폭) - 56)
    s = max(0.5, float(글배율 or 1.0))

    def 줄(t, fs=22, 덜=0):
        # 한글 1em · 숫자·빈칸 0.56em(폭보정 — 실제 글 폭 ÷ 이 어림은 중앙 0.82 · 최대 1.12, bench13 옛 덱 글 218개 실측)
        폭글 = 폭보정 * sum(1.0 if "가" <= ch <= "힣" else 0.56 for ch in _v2글자(t))
        return max(1, math.ceil(폭글 * fs / max(80, 안 - 덜)))

    def 하위높이(it):
        # 하위 글(css .checks .sub > li — 본문 크기 · 줄 높이 1.4 · 들여 20px)는 줄 수로 센다
        return sum(줄(x, 22 * s, 50) * round(22 * s * 1.4) + 2 for x in (it.get("하위") or []) if isinstance(x, str))
    if n == "지표타일":
        return False, 190
    if n == "카드":
        h = 48 + 50 + 12
        for it in c.get("항목") or []:
            글 = it.get("글") if isinstance(it, dict) else it
            h += 줄(글, 22 * s, 30) * round(32 * s) + 12
            if isinstance(it, dict):
                h += 하위높이(it)
        if c.get("아래줄"):
            h += 44
        if c.get("분류") or c.get("상태"):
            h += 44
        if c.get("아이콘"):
            h += 76
        return False, h
    if n == "항목타일":
        return False, (48 + (68 if c.get("아이콘") else 0) + 줄(c.get("제목"), 28 * s) * round(36 * s)
                       + 줄(c.get("글"), 22 * s) * round(32 * s) + (40 if c.get("근거") else 0))
    if n == "수량목록":
        return False, 48 + (44 if c.get("제목") else 0) + 60 * len(c.get("항목") or [])
    if n == "아이콘목록":
        m = len(c.get("항목") or [])
        return False, (24 if c.get("제목") else 0) + (84 if c.get("방향", "가로") == "가로" else 84 * m)
    if n == "요청상자":
        주 = 20 + 110 + 줄(c.get("요청문"), 28) * 36
        행 = 40 + 52 * len(c.get("행") or [])
        return False, 64 + (max(주, 행) if 안 >= 720 else 주 + 24 + 행)
    if n == "짝카드":
        m = max(len(c.get("줄") or []), len(c.get("왼항목") or []), len(c.get("오른항목") or []))
        if c.get("변형") == "대비":
            return False, 72 + 62 * m          # 따로 선 두 패널(제목 + 가는 선으로 나눈 항목 — css .vs__col, r4)
        return False, 30 + 100 * m
    if n == "인용":
        return False, (100 + 줄(c.get("인용문"), 28) * 40 + 32) if c.get("변형") == "밝게" else 320
    if n == "글머리":
        return False, sum(줄(t.get("글") if isinstance(t, dict) else t, 22 * s, 30) * round(32 * s) + 12
                          + (하위높이(t) if isinstance(t, dict) else 0) for t in c.get("항목") or [])
    return False, 200                      # 전후숫자·진행막대·비율링·구성띠·그 밖


def _v2줄틀(줄들, 가용):
    """줄 높이 틀 — 늘릴 부품이 없고 내용이 적으면 'fit'(칸을 내용 높이로, 본문 세로 가운데)."""
    어림 = []
    for 줄 in 줄들:
        늘, 높 = False, 0
        for 항목, 폭, _ in 줄:
            if 항목[0] == "묶음":
                자식 = [_v2어림(c, 폭) for _, c in 항목[1]]
                a = any(x for x, _ in 자식)
                h = sum(y for _, y in 자식) + 24 * max(0, len(자식) - 1)
            else:
                a, h = _v2어림(항목[1], 폭)
            늘 = 늘 or a
            높 = max(높, h)
        어림.append((늘, 높))
    if len(어림) == 1:
        늘, 높 = 어림[0]
        return "fit" if (not 늘 and 높 < 가용 * 0.68) else "1"
    (a1, h1), (a2, h2) = 어림[0], 어림[1]
    if not a1 and not a2 and h1 + h2 + 24 < 가용 * 0.72:
        return "fit"
    if not a2 and a1:
        return "1a"
    if not a1 and a2:
        return "a1"
    return "2"


# ── 채움 배율('26-09-29 bench13 ① — 밀도 3.2~3.4 대 기준선 4.75, 지적 1.2건/덱 '카드는 큰데 속이 비었다') ──
# 칸(그리드 줄)이 판 높이로 늘어난 장에서 부품 내용(어림 — 여백·간격 포함 제 높이)이 칸의 78% 에 못 미치면 그 칸의
# 글·아이콘 크기를 배율 --fz 로 키운다(슬라이드v2 css .v2-cell.is-z — 본문·부제·캡션 글자와 아이콘이 함께 커진다).
# 목표는 내용이 칸의 약 85%. 글이 커지면 줄바꿈도 늘어 높이가 배율보다 빨리 커지므로 지수 0.8 로 누른다. 상한은
# 밀도별(발표 1.35 — 이미 글이 크다, 보고 1.5, 배포 1.3). 늘림 부품(차트·표·타임라인)은 제 몸이 칸을 채워 건드리지 않는다.
# 렌더 뒤 빈 띠·빈 상자 넓이는 audit.js 가 잰다(render_verify soft) — 배율 상한까지 키워도 남는 장이 그 경고다.
_V2배율상한 = {"발표": 1.35, "보고": 1.5, "배포": 1.3}
_V2밀도글 = {"발표": 1.18, "보고": 1.0, "배포": 0.97}      # _v2어림 은 보고 밀도(본문 22px) 기준 — 발표 26px
# 숫자가 칸 높이·폭(cqh·cqi)을 따라 제 크기를 정하는 부품 — 글 배율을 곱하면 라벨이 숫자 자리를 먹어 숫자가 작아졌다
# (bench13 A s7 3장 전후숫자 실측). 이 부품은 칸 높이(내용 맞춤)로만 맞춘다.
_V2숫자부품 = ("지표타일", "전후숫자", "비율링", "진행막대")


# 부품별 제 높이 = _v2어림 × 보정('26-09-29 bench13 v2 덱 11벌 실측 — 늘림을 끈 렌더에서 부품 높이 ÷ 어림의 중앙값).
# 지표타일은 숫자가 칸 높이(cqh)를 따라 커져 제 높이를 잴 수 없어 숫자 한 줄(96px)을 더한 값으로 둔다.
_V2제높이보정 = {"카드": 0.91, "항목타일": 1.2, "전후숫자": 1.16, "진행막대": 1.48, "비율링": 1.7, "수량목록": 1.06,
             "요청상자": 1.1, "구성띠": 1.55, "지표타일": 1.3}
# 배율 fz 에 따른 제 높이 증가 지수(같은 실측 — fz 1.2~1.5 로 키운 렌더): 카드는 알약·안쪽 여백·항목 간격이 그대로라
# fz^0.6, 항목타일은 제목·글이 한 줄 더 꺾여 fz^1.0, 수량목록 fz^0.55, 짝카드 fz^0.5. 그 밖 0.8
_V2배율지수 = {"카드": 0.6, "항목타일": 1.0, "수량목록": 0.55, "짝카드": 0.5}


def _v2제높이(c, 폭, fz=1.0, 밀도="보고"):
    """부품 내용이 늘지 않을 때의 높이 어림(px) — 배율 fz 로 글이 커지면 fz^지수 배.
    글 부품(카드·글머리·항목타일)은 fz 크기 글로 줄바꿈을 다시 센 어림과 견줘 큰 쪽을 쓴다 — 지수 0.6 은 bench13 의
    한 줄 항목에서만 맞았다(round3 적대 검토 H1: 하위 항목·30자 항목은 글이 커지며 줄이 늘어 배율보다 빨리 높아졌다)."""
    n = c.get("부품")
    _, h = _v2어림(c, 폭)
    보정 = _V2제높이보정.get(n, 1.0)
    지수형 = h * 보정 * _V2밀도글.get(밀도, 1.0) * (fz ** _V2배율지수.get(n, 0.8))
    if n in ("카드", "글머리", "항목타일"):
        # 줄바꿈 셈은 실측 글 폭(중앙 0.82)보다 조금 넉넉한 0.9 로 — 모자라면 페이지 안 안전망(_V2배율안전망)이 내린다
        return max(지수형, _v2어림(c, 폭, fz * _V2밀도글.get(밀도, 1.0), 0.9)[1] * 보정)
    return 지수형


def _v2글폭em(t):
    return sum(1.0 if "가" <= ch <= "힣" else 0.56 for ch in _v2글자(t))


def _v2알약배율(c, 폭, 밀도="보고"):
    """카드 알약 제목(nowrap)이 카드 폭 안에 드는 배율(알약이 아니면 9) — 알약도 항목 글과 함께 키운다(round3 적대 검토
    L1: 알약만 배율에서 빼 항목 글 31.9~33px 이 제목 28px 보다 커졌다 — 위계가 뒤집혔다)."""
    if c.get("부품") != "카드" or c.get("제목모양", "알약") != "알약" or not c.get("제목"):
        return 9.0
    안 = _v2칸폭px(폭) - 2 * (32 if 밀도 == "발표" else 24) - 48
    # 실제 알약 글 폭 ÷ 어림(한글 1em) = 중앙 0.81 · 최대 0.919('26-09-30 bench13·극단·무작위 덱 알약 464개 실측)지만,
    # PPTX 는 맑은 고딕(한글 1em)으로 옮겨 그 폭으로 다시 잰다(topptx._맞춤 — 필요 폭 × 1.03). 0.93 으로 두었더니 키운 알약이
    # PPTX 에서 ×0.85~0.9 로 도로 줄었다(bench14 재조립 실측 — 주관 판정 ⑧). 맑은 고딕 폭으로 재 화면과 PPTX 가 같은 크기다
    w = _v2글폭em(c.get("제목")) * 28 * 1.03
    return max(1.0, math.floor(0.95 * 안 / w * 20) / 20) if w > 0 else 9.0


def _v2폭배율상한(c, 폭, 밀도="보고"):
    """가장 긴 어절이 글 폭을 넘지 않는 배율 — 글은 어절 단위로만 꺾여(keep-all) 긴 어절이 카드 밖으로 나간다
    ('26-09-29 bench13 m-s2 5장 '전자문서시스템' 1.5배에서 가로 넘침 16px 실측)."""
    글폭 = _v2칸폭px(폭) - (64 if 밀도 == "발표" else 48) - 30
    if c.get("부품") == "짝카드":
        글폭 = (_v2칸폭px(폭) - 56) / 2 - 48 - 68
    최장 = 1.0

    def 훑(o, 키=""):
        nonlocal 최장
        if isinstance(o, str):
            fs = 28 if 키 in _제목슬롯 else 22
            if 키 == "제목" and c.get("부품") == "카드" and c.get("제목모양", "알약") == "알약":
                # 알약 제목은 줄을 꺾지 않아(white-space: nowrap) 배율을 받지 않는다(css .v2-cell.is-z .card__pill) —
                # 예전엔 긴 알약 제목 하나가 줄 전체 배율을 1 로 눌러 카드가 작은 채 가운데 띠에 몰렸다(t6 m-s2 5장)
                return
            for w in o.split():
                최장 = max(최장, sum(1.0 if "가" <= ch <= "힣" else 0.58 for ch in w) * fs)
        elif isinstance(o, list):
            for x in o:
                훑(x, 키)
        elif isinstance(o, dict):
            for k, v in o.items():
                if k not in ("부품", "아이콘", "변형", "바탕", "제목모양", "상태", "분류", "폭", "근거"):
                    훑(v, k)
    훑(c)
    return max(1.0, 0.95 * 글폭 / (최장 * _V2밀도글.get(밀도, 1.0)))


_제목슬롯 = ("제목", "이름", "라벨", "왼제목", "오른제목")


def _v2채움배율(c, 폭, 칸높이, 밀도="보고"):
    """부품 하나의 채움 배율(1 이면 그대로). c 는 부품 dict."""
    if not isinstance(c, dict) or c.get("부품") in ("세로묶음", "요청상자", "인용"):
        return 1.0
    늘, h = _v2어림(c, 폭)
    if 늘 or h <= 0 or 칸높이 <= 0 or c.get("부품") in _V2숫자부품:
        return 1.0
    r = _v2제높이(c, 폭, 1.0, 밀도) / 칸높이
    if r >= 0.78:
        return 1.0
    상한 = min(_V2배율상한.get(밀도, 1.4), _v2폭배율상한(c, 폭, 밀도))
    # 키운 글이 두 줄로 꺾이는 것은 받아들이고 고르게 꺾는다(css .v2-cell.is-z text-wrap: balance — round3 적대 검토 M2
    # 외톨이 줄). '한 줄 항목은 한 줄로' 상한을 두었더니 줄의 가장 긴 항목 하나가 나란한 카드 셋의 배율을 1.5 → 1.2 로
    # 눌렀다(bench13 m-s6 4장 — 밀도가 이 판의 첫 과제라 걷었다). 알약 제목보다 항목 글이 커지지 않게(L1): 항목 글 ≤ 알약 글
    알약 = _v2알약배율(c, 폭, 밀도)
    if 알약 < 9.0:
        상한 = min(상한, 28 * 알약 / (22 * _V2밀도글.get(밀도, 1.0)))
    # 내용이 칸의 약 85% 가 되는 가장 큰 배율 — 키운 글로 줄바꿈까지 다시 센 높이로 고른다(H1)
    fz = math.floor(상한 * 20 + 1e-9) / 20
    while fz >= 1.05 and _v2제높이(c, 폭, fz, 밀도) / 칸높이 > 0.85:
        fz = round(fz - 0.05, 2)
    return fz if fz >= 1.05 else 1.0


# ── 부품 그리기 ──────────────────────────────────────────────────────────
def _v2지표타일(c, p, 목적, 글자수):
    e = html.escape
    변형 = 속성값.열거(c.get("변형"), tuple(_V2지표변형), p + ".변형", 기본="기본")
    맥락 = c.get("맥락") if isinstance(c.get("맥락"), dict) else {}
    out = [f'<div class="kpi{_V2지표변형[변형]}" data-ent="지표타일" data-path="{e(p)}" '
           f'style="--chars:{속성값.수(글자수, p + ".글자수", 기본=4, 최소=1, 최대=20)}">']
    out.append(_v2글(c.get("라벨"), p + ".라벨", 목적, "kpi__label"))
    단위 = (f'<span class="num__u tx" data-path="{e(p + ".단위")}">{e(str(c.get("단위")))}</span>'
          if c.get("단위") else "")
    out.append(f'<div class="num"><span class="num__v tx" data-path="{e(p + ".값")}">{e(str(c.get("값", "")))}</span>{단위}</div>')
    ctx = _v2증감(c.get("증감"), p + ".증감")
    if 맥락.get("글"):
        ctx += f'<span class="tx" data-path="{e(p + ".맥락.글")}">{e(str(맥락["글"]))}</span>'
    if ctx:
        out.append(f'<div class="kpi__ctx">{ctx}</div>')
    out.append("</div>")
    return "".join(out)


def _v2카드(c, p, 목적):
    e = html.escape
    바탕 = 속성값.열거(c.get("바탕"), tuple(_V2카드바탕), p + ".바탕", 기본="기본")
    모양 = 속성값.열거(c.get("제목모양"), ("알약", "막대", "글"), p + ".제목모양", 기본="알약")
    항목 = [x for x in c.get("항목") or [] if isinstance(x, (str, dict))]
    out = [f'<div class="card{_V2카드바탕[바탕]}" data-ent="카드" data-path="{e(p)}">']
    위 = ""
    if c.get("분류"):
        위 += _v2글(c.get("분류"), p + ".분류", 목적, "card__kicker")
    위 += _v2뱃지(c.get("상태"), p + ".상태")
    if 위:
        out.append(f'<div class="card__top">{위}</div>')
    out.append(_v2아이콘(c.get("아이콘"), p + ".아이콘", "ico ico--tint"))
    제목 = _v2글(c.get("제목"), p + ".제목", 목적, "")
    if 모양 == "알약":
        out.append(f'<span class="card__pill">{제목}</span>')
    elif 모양 == "막대":
        out.append(f'<div class="card__bar">{제목}</div>')
    else:
        out.append(f'<span class="card__title">{제목}</span>')
    펴기 = " grow" if len(항목) >= 4 else ""
    out.append(f'<ul class="checks{펴기}">')
    for j, it in enumerate(항목):
        if isinstance(it, dict):
            하위 = "".join(f'<li data-ent="항목">{_v2글(s, f"{p}.항목.{j}.하위.{m}", 목적)}</li>'
                         for m, s in enumerate(it.get("하위") or []) if isinstance(s, str))
            out.append(f'<li data-ent="항목">{_v2글(it.get("글"), f"{p}.항목.{j}.글", 목적)}'
                       f'{f"<ul class=sub>{하위}</ul>" if 하위 else ""}</li>')
        else:
            out.append(f'<li data-ent="항목">{_v2글(it, f"{p}.항목.{j}", 목적)}</li>')
    out.append("</ul>")
    if c.get("아래줄"):
        out.append(f'<div class="card__foot">{_v2글(c.get("아래줄"), p + ".아래줄", 목적)}</div>')
    out.append("</div>")
    return "".join(out)


def _v2항목타일(c, p, 목적):
    e = html.escape
    out = [f'<div class="card card--tint tile" data-ent="항목타일" data-path="{e(p)}">',
           _v2아이콘(c.get("아이콘"), p + ".아이콘", "ico"),
           _v2글(c.get("제목"), p + ".제목", 목적, "tile__t"),
           _v2글(c.get("글"), p + ".글", 목적, "tile__x")]
    if c.get("근거"):
        out.append(f'<span class="tag">{_v2글(c.get("근거"), p + ".근거", 목적)}</span>')
    out.append("</div>")
    return "".join(out)


def _v2수량목록(c, p, 목적):
    e = html.escape
    out = [f'<div class="card qty" data-ent="수량목록" data-path="{e(p)}">']
    if c.get("제목"):
        out.append(_v2글(c.get("제목"), p + ".제목", 목적, "card__title"))
    out.append('<dl class="qty__list">')
    for j, it in enumerate(c.get("항목") or []):
        if not isinstance(it, dict):
            continue
        q = f"{p}.항목.{j}"
        보조 = (f'<span class="qty__sub tx" data-path="{e(q + ".보조")}">{e(str(it["보조"]))}</span>'
              if it.get("보조") else "")
        단위 = (f'<span class="qty__u tx" data-path="{e(q + ".단위")}">{e(str(it["단위"]))}</span>'
              if it.get("단위") else "")
        out.append(f'<div class="qty__row" data-ent="항목"><dt><span class="tx" data-path="{e(q + ".라벨")}">'
                   f'{e(str(it.get("라벨", "")))}</span>{보조}</dt>'
                   f'<dd><span class="qty__v tx" data-path="{e(q + ".값")}">{e(str(it.get("값", "")))}</span>{단위}</dd></div>')
    out.append("</dl></div>")
    return "".join(out)


def _v2진행막대(c, p, 목적, 자동):
    e = html.escape
    값, 목표 = c.get("값"), c.get("목표")
    비 = (값 / 목표 * 100) if (_v2수(값) and _v2수(목표) and 목표) else 0.0
    비글 = _v2퍼센트글(비)
    자동.append(비글)
    단위 = str(c.get("단위") or "")
    글자수 = len(_v2수글(값)) + len(단위) * 0.7 + len(_v2수글(목표)) * 0.42 + 1
    out = [f'<div class="card prog" data-ent="진행막대" data-path="{e(p)}">',
           _v2글(c.get("라벨"), p + ".라벨", 목적, "kpi__label"),
           f'<div class="num num--sm num--fit" style="--chars:{속성값.수(round(글자수, 1), p + ".글자수", 기본=5, 최소=1, 최대=30)}">'
           f'<span class="num__v" data-derived="1">{e(_v2수글(값))}</span>'
           + (f'<span class="num__u tx" data-path="{e(p + ".단위")}">{e(단위)}</span>' if 단위 else "")
           + f'<span class="num__of" data-derived="1">/ {e(_v2수글(목표))}</span></div>']
    선 = ""
    if _v2수(c.get("목표선")) and _v2수(목표) and 목표:
        선 = (f'<div class="progress__target" style="--t:'
             f'{속성값.수(round(c["목표선"] / 목표 * 100, 2), p + ".목표선", 기본=100, 최소=0, 최대=100)}"></div>')
    왼 = (_v2글(c.get("표시"), p + ".표시", 목적) if c.get("표시")
         else f'<span data-derived="1">목표 {e(_v2수글(목표))}{e(단위)}</span>')
    out.append(f'<div class="progress progress--lg" style="--v:{속성값.수(round(min(비, 100), 2), p + ".비율", 기본=0, 최소=0, 최대=100)}">'
               f'<div class="progress__track"><div class="progress__fill"></div>{선}</div>'
               f'<div class="progress__legend">{왼}<span data-derived="1">{e(비글)}</span></div></div>')
    out.append("</div>")
    return "".join(out)


def _v2패널(c, p, 부품, 목적, 몸):
    """차트 패널 — 알약 제목 + 그림 + 요지 한 줄."""
    e = html.escape
    out = [f'<div class="chart-panel" data-ent="{e(부품)}" data-path="{e(p)}">',
           f'<span class="card__pill">{_v2글(c.get("제목"), p + ".제목", 목적)}</span>', 몸]
    if c.get("요지"):
        out.append(f'<p class="chart-panel__so">{_v2글(c.get("요지"), p + ".요지", 목적)}</p>')
    out.append("</div>")
    return "".join(out)


def _v2시점인가(라벨들):
    import slides_v2_gate
    return bool(라벨들) and all(slides_v2_gate.시점re.match(str(t).strip()) for t in 라벨들)


def _v2가로막대(c, p, 목적, 폭, 높이=420):
    """높이 = 칸(줄) 높이 어림. 행이 3개 이하면 막대를 굵게 하고 판 높이에 고르게 편다(hbar--few) — 두세 막대가 큰 패널
    가운데 얇게 떠 위아래가 비었다('26-09-29 bench13 ① W s2·s5·s6 3장, a-s5 3장 실측 빈 상자 넓이 0.56~0.68)."""
    e = html.escape
    행 = [(j, r) for j, r in enumerate(c.get("행") or []) if isinstance(r, dict)]
    변형 = 속성값.열거(c.get("변형"), ("기본", "전후"), p + ".변형", 기본="기본")
    종류 = 속성값.열거(c.get("전후종류"), ("실적", "계획"), p + ".전후종류", 기본="실적")
    정렬 = 속성값.열거(c.get("정렬"), ("값순", "입력순"), p + ".정렬", 기본="값순")
    척도 = 속성값.열거(c.get("척도"), ("최댓값", "백분율"), p + ".척도", 기본="최댓값")
    if 정렬 == "값순" and 변형 == "기본" and not _v2시점인가([r.get("라벨") for _, r in 행]):
        행 = sorted(행, key=lambda x: -(x[1].get("값") if _v2수(x[1].get("값")) else 0))
    최대 = max([r.get("값") for _, r in 행 if _v2수(r.get("값"))] or [0])
    단위 = str(c.get("단위") or "")
    붙임 = 단위 if 단위 in ("%", "%p") else ""
    # 한 차트 안 소수 자리를 맞춘다(1.0·1.4·0.8). '26-09-28 적대 검토(렌더 M1): repr 로 세면 지수 표기
    # (0.00005·1e16)에서 IndexError 로 덱 전체가 죽고, 0.30000000000000004 같은 계산 잔차가 17자리를
    # 모든 막대로 퍼뜨렸다 — 고정 소수 10자리로 적어 세고 2자리에서 자른다(_v2수글 과 같은 상한).
    자리 = min(2, max([_v2소수자리(r["값"]) for _, r in 행 if isinstance(r.get("값"), float) and _v2수(r.get("값"))]
                      + [1 if any(isinstance(r.get("값"), float) and _v2수(r.get("값")) for _, r in 행) else 0]))
    역할들 = [r.get("역할") for _, r in 행]
    한색 = 변형 == "기본" and not any(x in ("강조", "목표") for x in 역할들)
    W = _v2칸폭px(폭) - 56
    라벨폭 = max(72, min(int(W * 0.4), max([len(str(r.get("라벨", ""))) for _, r in 행] or [2]) * 22 + 12))
    간격 = 24 if len(행) <= 4 else 14
    적음 = 0 < len(행) <= 3
    굵기 = max(36, min(72, round((높이 - 130) / max(1, len(행)) * 0.42))) if 적음 else 36
    rows = []
    for 순, (j, r) in enumerate(행):
        v = r.get("값") if _v2수(r.get("값")) else 0
        길이 = max(0, min(100, v)) if 척도 == "백분율" else (v / 최대 * 100 if 최대 > 0 else 0)
        역 = 속성값.열거(r.get("역할"), ("기본", "강조", "목표"), f"{p}.행.{j}.역할", 기본="기본")
        if 변형 == "전후":
            틀 = (" is-focus" if 순 == len(행) - 1 else "") if 종류 == "실적" else (" is-focus" if 순 == 0 else " is-accent")
        else:
            틀 = {"기본": "", "강조": " is-focus", "목표": " is-accent"}[역]
        q = f"{p}.행.{j}"
        수글 = f"{r['값']:,.{자리}f}" if (자리 and _v2수(r.get("값"))) else _v2수글(r.get("값"))
        값글 = (_v2글(r.get("표시"), q + ".표시", 목적) if r.get("표시")
              else f'<span data-derived="1">{e(수글)}{e(붙임)}</span>')
        rows.append(f'<div class="hbar__row{틀}" data-ent="항목" style="--v:{속성값.수(round(길이, 2), q + ".길이", 기본=0, 최소=0, 최대=100)}">'
                    f'<span class="hbar__label tx" data-path="{e(q + ".라벨")}">{e(str(r.get("라벨", "")))}</span>'
                    f'<div class="hbar__track"><div class="hbar__fill"></div></div>'
                    f'<span class="hbar__val">{값글}</span></div>')
    몸 = (f'<div class="hbar grow{" hbar--mono" if 한색 else ""}{" hbar--few" if 적음 else ""}" data-scale="{"pct" if 척도 == "백분율" else "max"}" style="--hbar-label-w:'
         f'{속성값.수(라벨폭, p + ".라벨폭", 기본=120, 최소=40, 최대=400)}px;--hbar-gap:'
         f'{속성값.수(간격, p + ".간격", 기본=24, 최소=4, 최대=40)}px;--hbar-h:{속성값.수(굵기, p + ".굵기", 기본=36, 최소=20, 최대=80)}px">{"".join(rows)}</div>')
    return _v2패널(c, p, "가로막대", 목적, 몸)


def _v2글폭(t, fs):
    """글 폭 어림(px) — 한글 1em · 그 밖(숫자·영문·빈칸) 0.6em · 쉼표·마침표 0.32em."""
    w = 0.0
    for ch in str(t):
        w += 1.0 if "가" <= ch <= "힣" else (0.32 if ch in ",.·'" else 0.6)
    return w * fs


def _v2눈금글(t, 간격):
    """눈금 글 — 소수 자리는 눈금 간격으로 정한다('26-09-28 적대 검토 L4: 0.001~0.004 눈금이 전부 '0')."""
    자리 = min(6, _v2소수자리(round(간격, 10)))
    if 자리 == 0:
        return f"{int(round(t)):,}"
    return f"{t:,.{자리}f}"


def _v2겹침(a, b, 틈=2):
    """두 글 네모(x0, y0, x1, y1)가 겹치나."""
    return a[0] < b[2] + 틈 and b[0] < a[2] + 틈 and a[1] < b[3] + 틈 and b[1] < a[3] + 틈


def _v2선차트(c, p, 목적, 폭, 높이):
    """선차트 — 눈금·끝 이름표·끝값 글 폭을 재서 좌우 여백을 정하고(글이 SVG 밖 = PPTX 그림에서 잘림),
    가로축 라벨이 칸보다 넓으면 끝에서부터 건너 찍고, 점 라벨이 다른 글·다른 계열 점과 겹치면 뺀다.
    '26-09-28 적대 검토(렌더 M2·M3·M4)."""
    e = html.escape
    가로 = [str(x) for x in c.get("가로축") or []]
    계열 = [(s_i, s) for s_i, s in enumerate(c.get("계열") or []) if isinstance(s, dict)]
    N = max(1, len(가로))
    W = max(320, _v2칸폭px(폭) - 56)
    H = int(max(170, min(380, 높이 - (130 if c.get("요지") else 90))))   # 칸 높이 어림에 맞춘 그림 높이
    위, 아래 = 52, 40
    안쪽 = 28                                  # 첫 점이 세로 눈금 글과 겹치지 않게
    기준 = c.get("기준선") if isinstance(c.get("기준선"), dict) else None
    값들 = [v for _, s in 계열 for v in (s.get("값") or []) if _v2수(v)]
    if 기준 and _v2수(기준.get("값")):
        값들.append(기준["값"])
    if not 값들:
        값들 = [0, 1]
    mn, mx = min(값들), max(값들)
    r = (mx - mn) or (abs(mx) * 0.2 or 1)
    lo, hi, 간격, 눈금 = _v2눈금(mn - r * 0.15, mx + r * 0.15, 4)
    if len(눈금) > 6:
        lo, hi, 간격, 눈금 = _v2눈금(mn - r * 0.15, mx + r * 0.15, 3)
    눈금글 = [_v2눈금글(t, 간격) for t in 눈금]
    여럿 = len(계열) > 1
    # ── 여백: 왼쪽은 눈금 글, 오른쪽은 끝 이름표(끝점 +16 에서 왼쪽부터)·끝값 글(끝점 가운데)
    좌 = max(52, int(max([_v2글폭(t, 16) for t in 눈금글] or [0])) + 18)
    오른글 = [0.0]
    for _, 계 in 계열:
        역 = 계.get("역할") if 계.get("역할") in ("강조", "비교", "계획") else "강조"
        vs = [v for v in list(계.get("값") or [])[:N] if _v2수(v)]
        if not vs:
            continue
        if 여럿 or 역 == "비교":
            오른글.append(20 + _v2글폭(str(계.get("이름", "")) + (" " + _v2수글(vs[-1]) if 역 == "비교" else ""), 16))
        if 역 != "비교":
            오른글.append(_v2글폭(_v2수글(vs[-1]), 36 if 역 == "강조" else 30) / 2 + 6)
    if 가로:
        오른글.append(_v2글폭(가로[-1], 16) / 2 + 4)
    우 = max(84, int(max(오른글)) + 6)
    if 좌 + 우 + 안쪽 > W * 0.62:              # 그림 폭이 너무 줄면 여백을 비율대로 깎는다(극단 입력)
        비 = (W * 0.62 - 안쪽) / (좌 + 우)
        좌, 우 = int(좌 * 비), int(우 * 비)

    def X(n):
        return 좌 + 안쪽 + (W - 좌 - 우 - 안쪽) * ((n / (N - 1)) if N > 1 else 0.5)

    def Y(v):
        return 위 + (H - 위 - 아래) * (1 - (v - lo) / ((hi - lo) or 1))
    s = [f'<svg class="lc" viewBox="0 0 {속성값.수(W, p + ".W", 기본=600)} {속성값.수(H, p + ".H", 기본=300)}" '
         f'preserveAspectRatio="xMidYMid meet">']
    for t, 글 in zip(눈금, 눈금글):
        s.append(f'<line class="lc-grid" x1="{속성값.수(좌, "x", 기본=0)}" y1="{속성값.수(round(Y(t), 1), "y", 기본=0)}" '
                 f'x2="{속성값.수(W - 우 + 20, "x", 기본=0)}" y2="{속성값.수(round(Y(t), 1), "y", 기본=0)}"/>')
        s.append(f'<text class="lc-t" x="{속성값.수(좌 - 10, "x", 기본=0)}" y="{속성값.수(round(Y(t) + 5, 1), "y", 기본=0)}" '
                 f'text-anchor="end" data-derived="1">{e(글)}</text>')
    if 기준 and _v2수(기준.get("값")):
        yy = round(Y(기준["값"]), 1)
        s.append(f'<line class="lc-ref" x1="{속성값.수(좌, "x", 기본=0)}" y1="{속성값.수(yy, "y", 기본=0)}" '
                 f'x2="{속성값.수(W - 우 + 20, "x", 기본=0)}" y2="{속성값.수(yy, "y", 기본=0)}"/>')
        s.append(f'<text class="lc-reflab" x="{속성값.수(좌 + 8, "x", 기본=0)}" y="{속성값.수(round(yy - 8, 1), "y", 기본=0)}">'
                 f'<tspan data-path="{e(p + ".기준선.라벨")}">{e(str(기준.get("라벨", "")))}</tspan>'
                 # 라벨이 값을 이미 품으면('작년 하반기') 값 꼬리를 또 달지 않는다('26-09-28 통합 E2E)
                 + ("" if _v2수글(기준["값"]) in str(기준.get("라벨", "")) else
                    f'<tspan data-derived="1"> {e(_v2수글(기준["값"]))}</tspan>')
                 + '</text>')
    이름표 = []                                # [y, x, 계열 색인, 이름, 값 글] — 끝에 겹침을 풀어 한 번에 찍는다
    끝값 = []                                  # [x, y, 점 y, 틀, 글, fs]
    점라벨 = []                                # (x, y, 글, 계열 색인)
    점자리 = []                                # (x, y, 계열 색인) — 모든 계열의 점
    for s_i, 계 in 계열:
        역 = 속성값.열거(계.get("역할"), ("강조", "비교", "계획"), f"{p}.계열.{s_i}.역할", 기본="강조")
        선틀, 점틀, 끝틀, 끝글틀 = {"강조": ("lc-focus", "lc-pt", "lc-end", "lc-endlab"),
                              "비교": ("lc-context", "lc-pt-ctx", "lc-pt-ctx", ""),
                              "계획": ("lc-plan", "", "lc-end-acc", "lc-acclab")}[역]
        vs = list(계.get("값") or [])[:N]
        점 = [(n, v) for n, v in enumerate(vs) if _v2수(v)]
        조각, 지금 = [], []
        for n, v in enumerate(vs):
            if _v2수(v):
                지금.append((n, v))
            elif 지금:
                조각.append(지금)
                지금 = []
        if 지금:
            조각.append(지금)
        for 줄 in 조각:
            if len(줄) >= 2:
                s.append(f'<polyline class="{선틀}" points="'
                         + " ".join(f'{속성값.수(round(X(n), 1), "x", 기본=0)},{속성값.수(round(Y(v), 1), "y", 기본=0)}' for n, v in 줄)
                         + '"/>')
        if not 점:
            continue
        점자리.extend((X(n), Y(v), s_i) for n, v in 점)
        끝n, 끝v = 점[-1]
        for n, v in 점[:-1]:
            if 점틀:                             # 계획 계열은 시작점(=실적 끝점)을 다시 찍지 않는다
                s.append(f'<circle class="{점틀}" cx="{속성값.수(round(X(n), 1), "x", 기본=0)}" '
                         f'cy="{속성값.수(round(Y(v), 1), "y", 기본=0)}" r="7"/>')
            if 역 == "강조" and len(점) <= 7:
                점라벨.append((X(n), Y(v) - 16, _v2수글(v), s_i))
        s.append(f'<circle class="{끝틀}" cx="{속성값.수(round(X(끝n), 1), "x", 기본=0)}" '
                 f'cy="{속성값.수(round(Y(끝v), 1), "y", 기본=0)}" r="{"11" if 역 != "비교" else "7"}"/>')
        if 끝글틀:
            끝값.append([X(끝n), Y(끝v) - 20, Y(끝v), 끝글틀, _v2수글(끝v), 36 if 역 == "강조" else 30])
        if 여럿 or 역 == "비교":
            이름표.append([Y(끝v) + 6, X(끝n) + 16, s_i, str(계.get("이름", "")), _v2수글(끝v) if 역 == "비교" else ""])
    # 끝값 글끼리 겹치면(같은 끝점 근처 두 계열) 아래 것을 점 밑으로 내린다
    끝값.sort(key=lambda t: t[1])
    for k in range(1, len(끝값)):
        a, b = 끝값[k - 1], 끝값[k]
        if abs(a[0] - b[0]) < (_v2글폭(a[4], a[5]) + _v2글폭(b[4], b[5])) / 2 and b[1] - a[1] < max(a[5], b[5]) * 0.9:
            b[1] = b[2] + 20 + b[5] * 0.75
    이름표.sort()
    for k in range(1, len(이름표)):             # 끝 이름표끼리 20px 안쪽으로 붙으면 아래로 민다
        이름표[k][0] = max(이름표[k][0], 이름표[k - 1][0] + 20)
    이름네모 = [(x, y - 13, x + _v2글폭(이름 + (" " + 값글 if 값글 else ""), 16), y + 3) for y, x, _, 이름, 값글 in 이름표]
    막힘 = list(이름네모)                        # 점 라벨이 피해야 할 글 네모

    def 끝네모(x, y, 글, fs):
        w = _v2글폭(글, fs)
        return (x - w / 2, y - fs * 0.8, x + w / 2, y + fs * 0.2)
    for 끝 in 끝값:                             # 끝값 글이 다른 계열 이름표에 걸리면 점 밑으로(검토 M4 '71'⟷'평균 75')
        x, y, 점y, _, 글, fs = 끝
        if any(_v2겹침(끝네모(x, y, 글, fs), b) for b in 막힘):
            아래y = 점y + 20 + fs * 0.75
            if not any(_v2겹침(끝네모(x, 아래y, 글, fs), b) for b in 막힘) and 아래y < H - 24:
                끝[1] = 아래y
        막힘.append(끝네모(끝[0], 끝[1], 글, fs))
    for x, y, _, 틀, 글, fs in 끝값:
        s.append(f'<text class="{e(틀)}" x="{속성값.수(round(x, 1), "x", 기본=0)}" '
                 f'y="{속성값.수(round(y, 1), "y", 기본=0)}" text-anchor="middle" data-derived="1">{e(글)}</text>')
    for y, x, s_i, 이름, 값글 in 이름표:
        s.append(f'<text class="lc-t" x="{속성값.수(round(x, 1), "x", 기본=0)}" y="{속성값.수(round(y, 1), "y", 기본=0)}">'
                 f'<tspan data-path="{e(f"{p}.계열.{s_i}.이름")}">{e(이름)}</tspan>'
                 + (f'<tspan data-derived="1"> {e(값글)}</tspan>' if 값글 else "") + "</text>")
    for x, y, 글, s_i in 점라벨:
        w = _v2글폭(글, 22)
        네모 = (x - w / 2, y - 18, x + w / 2, y + 4)
        if any(_v2겹침(네모, b) for b in 막힘):
            continue
        if any(t != s_i and _v2겹침(네모, (px - 8, py - 8, px + 8, py + 8), 0) for px, py, t in 점자리):
            continue
        막힘.append(네모)
        s.append(f'<text class="lc-lab" x="{속성값.수(round(x, 1), "x", 기본=0)}" '
                 f'y="{속성값.수(round(y, 1), "y", 기본=0)}" text-anchor="middle" data-derived="1">{e(글)}</text>')
    # 가로축 라벨 — 점 간격보다 넓으면 마지막(가장 최근) 점에서부터 건너 찍는다
    칸 = (W - 좌 - 우 - 안쪽) / (N - 1) if N > 1 else W
    넓이 = max([_v2글폭(t, 16) for t in 가로] or [0])
    건너 = max(1, math.ceil(넓이 / max(1.0, 칸 * 0.9)))
    for n, t in enumerate(가로):
        if (N - 1 - n) % 건너:
            continue
        s.append(f'<text class="lc-t" x="{속성값.수(round(X(n), 1), "x", 기본=0)}" y="{속성값.수(H - 8, "y", 기본=0)}" '
                 f'text-anchor="middle" data-path="{e(f"{p}.가로축.{n}")}">{e(t)}</text>')
    s.append("</svg>")
    return _v2패널(c, p, "선차트", 목적, f'<div class="chart-panel__plot">{"".join(s)}</div>')


def _v2점눈금(c, p, 목적, 폭=6):
    """점눈금 — 태그(라벨+값) 폭을 칸 폭에 대어 위·아래 두 줄에 겹치지 않게 앉히고, 축 밖 값은 축 끝에
    붙인다(게이트가 hard 로 먼저 막는다). 눈금 글이 간격보다 넓으면 하나 걸러 비운다.
    '26-09-28 적대 검토(렌더 M4·L3): 가까운 세 점의 태그가 모두 위에 붙어 서로 덮었다."""
    e = html.escape
    점 = [(j, x) for j, x in enumerate(c.get("점") or []) if isinstance(x, dict) and _v2수(x.get("값"))]
    축 = c.get("축") if isinstance(c.get("축"), dict) else None
    vs = [x["값"] for _, x in 점] or [0, 1]
    if 축 and _v2수(축.get("최소")) and _v2수(축.get("최대")) and 축["최대"] > 축["최소"] \
            and not (min(vs) >= 축["최소"] and max(vs) <= 축["최대"]):
        # 축 밖 값 — 예전엔 축 끝에 붙여 그렸다(저장 경로에서 축 0~100·값 130 이 100 자리에 '130'으로, round2 적대 검토 M3).
        # 새 초안은 게이트가 hard 로 막고, 저장 경로에서는 축을 값까지 넓혀 거짓 그림을 안 만든다.
        lo, hi, 간격, 눈금 = _v2눈금(min(축["최소"], min(vs)), max(축["최대"], max(vs)), 4)
    elif 축 and _v2수(축.get("최소")) and _v2수(축.get("최대")) and 축["최대"] > 축["최소"]:
        lo, hi, 간격, 눈금 = _v2눈금(축["최소"], 축["최대"], 4)
        lo, hi = 축["최소"], 축["최대"]
        눈금 = [t for t in 눈금 if lo <= t <= hi] or [lo, hi]
    else:
        r = (max(vs) - min(vs)) or (abs(max(vs)) * 0.1 or 1)
        span = r / 0.7
        lo, hi, 간격, 눈금 = _v2눈금(min(vs) - span * 0.15, max(vs) + span * 0.15, 4)
    단위 = str(c.get("단위") or "")
    붙임 = 단위 if len(단위) <= 2 else ""
    W = max(200, _v2칸폭px(폭) - 56 - 48)          # 그림 폭 어림(패널 안쪽 · 좌우 여백)

    def 자리px(v):
        return (min(max(v, lo), hi) - lo) / ((hi - lo) or 1) * W
    차례 = sorted(점, key=lambda x: x[1]["값"])
    아래 = set()
    끝 = {"위": -1e9, "아래": -1e9}
    for j, x in 차례:
        반 = _v2글폭(f'{x.get("라벨", "")} {_v2수글(x["값"])}{붙임}', 16) / 2
        중 = 자리px(x["값"])
        줄 = "위" if 중 - 반 >= 끝["위"] + 8 else ("아래" if 중 - 반 >= 끝["아래"] + 8
                                                   else min(("위", "아래"), key=lambda k: 끝[k]))
        if 줄 == "아래":
            아래.add(j)
        끝[줄] = 중 + 반
    띠 = ""
    if len(vs) >= 2:
        띠 = (f'<div class="dotscale__band" style="--a:{속성값.수(min(max(min(vs), lo), hi), p + ".a", 기본=0)};'
             f'--b:{속성값.수(min(max(max(vs), lo), hi), p + ".b", 기본=0)}"></div>')
    pts = []
    for j, x in 점:
        역 = 속성값.열거(x.get("역할"), ("강조", "기준", "목표"), f"{p}.점.{j}.역할", 기본="기준")
        틀 = {"강조": " is-focus", "기준": "", "목표": " is-accent"}[역] + (" is-below" if j in 아래 else "")
        pts.append(f'<div class="dotscale__pt{틀}" style="--v:{속성값.수(min(max(x["값"], lo), hi), f"{p}.점.{j}.값", 기본=0)}">'
                   f'<span class="dotscale__tag"><span class="tx" data-path="{e(f"{p}.점.{j}.라벨")}">{e(str(x.get("라벨", "")))}</span>'
                   f'<span data-derived="1"> {e(_v2수글(x["값"]))}{e(붙임)}</span></span></div>')
    틱글 = [_v2눈금글(t, 간격) for t in 눈금]
    틱칸 = W * 간격 / ((hi - lo) or 1)            # 이웃 눈금 사이 실제 폭(눈금 글은 값 자리에 앉는다)
    걸러 = 2 if len(눈금) % 2 == 1 and max([_v2글폭(t, 16) for t in 틱글] or [0]) > 틱칸 * 0.9 else 1
    # 눈금 글은 **자기 값 자리**에 둔다(--v) — 예전엔 flex 로 고르게 벌려 첫 눈금이 축 최소(0%)에, 끝 눈금이
    # 축 최대에 붙었다. 축 130~180 에 눈금 140·160·180 이면 145 점이 눈금상 152 자리로 읽혔다(bench11 심사).
    틱 = "".join(f'<span data-derived="1" style="--v:{속성값.수(t, f"{p}.눈금.{k}", 기본=0)}">{e(글) if k % 걸러 == 0 else ""}</span>'
                for k, (t, 글) in enumerate(zip(눈금, 틱글)))
    몸 = (f'<div class="chart-panel__plot is-mid"><div class="dotscale{" has-below" if 아래 else ""}" '
         f'style="--min:{속성값.수(lo, p + ".최소", 기본=0)};--max:{속성값.수(hi, p + ".최대", 기본=1)}">'
         f'<div class="dotscale__track"></div>{띠}{"".join(pts)}<div class="dotscale__ticks">{틱}</div></div></div>')
    return _v2패널(c, p, "점눈금", 목적, 몸)


def _v2비율링(c, p, 목적):
    e = html.escape
    v = c.get("값") if _v2수(c.get("값")) else 0
    v = max(0, min(100, v))
    역 = 속성값.열거(c.get("역할"), ("강조", "격차"), p + ".역할", 기본="강조")
    수 = (_v2글(c.get("표시"), p + ".표시", 목적, "num__v") if c.get("표시")
         else f'<span class="num__v" data-derived="1">{e(_v2수글(v))}</span><span class="num__u" data-derived="1">%</span>')
    # 값 0 이면 호를 안 그린다 — 둥근 끝(stroke-linecap: round) 때문에 12시에 점이 찍혔다('26-09-28 검토 L3)
    # dash 주기(칠+빈칸)를 **둘레와 같게** 둔다 — 빈칸을 둘레 전체로 두면 주기가 둘레보다 길어, 12시로 당긴
    # offset(둘레/4) 만큼 호 앞머리가 경로 끝 너머로 사라졌다(64% → 약 39%, 94% → 약 69% — bench11 심사 3인).
    # 끝 모양은 butt(속성 + CSS) — round 면 양끝 둥근 끝이 호를 굵기만큼(+4.5%p) 늘려 보였다(round2 적대 검토 H2).
    # 게이트(차트되읽기)는 이 속성을 읽어 round 면 굵기만큼 더해 잰다.
    호길 = round(_V2링둘레 * v / 100, 2)
    호 = (f'<circle class="ring-val{" is-acc" if 역 == "격차" else ""}" cx="70" cy="70" r="56" stroke-width="16" stroke-linecap="butt" '
         f'stroke-dasharray="{속성값.수(호길, p + ".호", 기본=0)} {속성값.수(round(_V2링둘레 - 호길, 2), p + ".호빈칸", 기본=0)}" '
         f'stroke-dashoffset="{속성값.수(round(_V2링둘레 / 4, 2), "시작", 기본=0)}"/>') if v > 0 else ""
    링 = (f'<svg class="lc ring" viewBox="0 0 140 140"><circle class="ring-track" cx="70" cy="70" r="56" stroke-width="16"/>'
         f'{호}</svg>')
    맥락 = (f'<span class="kpi__ctx">{_v2글(c.get("맥락"), p + ".맥락", 목적)}</span>' if c.get("맥락") else "")
    글자수 = (len(_v2글자(c.get("표시"))) if c.get("표시") else len(_v2수글(v)) + 0.7) + 0.3
    return (f'<div class="card ringc" data-ent="비율링" data-path="{e(p)}">'
            f'{_v2글(c.get("라벨"), p + ".라벨", 목적, "kpi__label")}'
            f'<div class="row">{링}<div class="stack stack--tight"><div class="num num--sm" '
            f'style="--chars:{속성값.수(round(글자수, 1), p + ".글자수", 기본=4, 최소=1, 최대=20)}">{수}</div>{맥락}</div></div></div>')


def _v2구성띠(c, p, 목적, 자동):
    e = html.escape
    조각 = [(j, x) for j, x in enumerate(c.get("조각") or []) if isinstance(x, dict) and _v2수(x.get("값"))]
    합 = sum(max(0, x["값"]) for _, x in 조각) or 1
    원 = [max(0, x["값"]) / 합 * 100 for _, x in 조각]
    # 조각마다 제 값으로 반올림한다(사사오입). 예전엔 큰 나머지 방식으로 합을 100 에 맞춰 980/2,850=34.4% 를
    # 35% 로 올려 찍었다 — 심사 3인이 '계산 오류'로 짚었다('26-09-29 bench11). 합이 99·101 이 되는 것은 반올림
    # 탓이라 그대로 둔다(값이 틀린 것보다 낫다). 단위가 있으면 값(금액·분량)을 먼저 적고 비율을 곁에 둔다.
    정 = [int(math.floor(v + 0.5)) for v in 원]
    # 반올림이 0·100 을 주장하지 않게 — 0 < 비 < 0.5 면 '<1%', 99.5 ≤ 비 < 100 이면 '>99%'(round2 적대 검토 L1:
    # 3/1,500억이 '(0%)'인데 조각은 보이고, 1,497억이 '(100%)'로 찍혔다)
    비글 = [("<1%" if 0 < v < 0.5 else ">99%" if 99.5 <= v < 100 else f"{q}%") for v, q in zip(원, 정)]
    단위 = str(c.get("단위") or "")
    if not 단위:
        # 제목 끝 괄호가 금액·분량 단위('분야별 예산(억원)')면 그 단위로 금액을 찍는다 — 예산 장이 %만 보였다
        # ('26-09-29 bench11 심사 ⑭). 숫자·% 가 든 괄호('26년·%)는 단위가 아니다.
        m = re.search(r"\(([^()\d%]{1,6})\)\s*$", str(c.get("제목") or ""))
        단위 = m.group(1).strip() if m else ""
    강 = c.get("강조") if isinstance(c.get("강조"), int) and not isinstance(c.get("강조"), bool) else None
    막대, 범례 = [], []
    for 순, ((j, x), pct) in enumerate(zip(조각, 정)):
        if 강 is None:
            틀 = " is-focus" if 순 == 0 else f" k-{min(4, 순)}"
        else:
            틀 = " is-focus" if 순 == 강 else f" k-{min(4, 순 + 1 if 순 < 강 else 순)}"
        if abs(x["값"] - pct) > 1e-9:               # 자료 값이 이미 그 %면(81·19) 산출이 아니다('26-09-28 통합 E2E)
            자동.append(비글[순])
        # 0 조각은 숨긴다(최소 폭 6px 로 있는 것처럼 보였다 — L1). 자리는 남겨 범례와 짝(게이트 되읽기)을 맞춘다
        막대.append(f'<div class="share__seg{틀}{"" if 원[순] > 0 else " is-zero"}" style="--w:{속성값.수(round(원[순], 2), f"{p}.조각.{j}.비", 기본=1, 최소=0, 최대=100)}"></div>')
        범례.append(f'<div class="share__key{" is-focus" if "is-focus" in 틀 else ""}"><span class="share__sw{틀}"></span>'
                   f'<span class="tx" data-path="{e(f"{p}.조각.{j}.라벨")}">{e(str(x.get("라벨", "")))}</span>'
                   + (f'<span class="share__amt" data-derived="1">{e(_v2수글(x["값"]))}{e(단위)}</span>' if 단위 else "")
                   + f'<span class="share__pct" data-derived="1">{"(" if 단위 else ""}{e(비글[순])}{")" if 단위 else ""}</span></div>')
    합계 = (f'<div class="share__sum" data-derived="1">합계 {e(_v2수글(sum(x["값"] for _, x in 조각)))}{e(단위)}</div>'
          if 단위 and len(조각) >= 2 else "")
    몸 = (f'<div class="share"><div class="share__bar">{"".join(막대)}</div><div class="share__legend">{"".join(범례)}</div>'
         f'{합계}</div>')
    return _v2패널(c, p, "구성띠", 목적, 몸)


def _v2전후숫자(c, p, 목적, 폭=6, 높이=420):
    """폭 4열 이하·높이 360px 이상 칸이면 이전·이후를 위아래로 쌓는다(np--col) — 좁고 높은 칸에서 두 숫자를 옆으로
    놓으면 숫자가 폭에 눌려 작아지고 위아래가 비었다('26-09-29 bench13 ① A s7 3장 4칸 — 심사 '카드 속이 비었다')."""
    e = html.escape
    종류 = 속성값.열거(c.get("종류"), ("실적", "계획"), p + ".종류", 기본="실적")
    앞, 뒤 = (c.get("이전") or {}), (c.get("이후") or {})
    글자수 = max(len(str(앞.get("값", ""))) + len(str(앞.get("단위", ""))) * 0.7,
              len(str(뒤.get("값", ""))) + len(str(뒤.get("단위", ""))) * 0.7, 1)

    def 쪽(d, q, 틀):
        cap = (f'<span class="np__cap tx" data-path="{e(q + ".라벨")}">{e(str(d["라벨"]))}</span>' if d.get("라벨") else "")
        u = (f'<span class="num__u tx" data-path="{e(q + ".단위")}">{e(str(d["단위"]))}</span>' if d.get("단위") else "")
        return (f'<div class="np__side">{cap}<div class="num {e(틀)}"><span class="num__v tx" data-path="{e(q + ".값")}">'
                f'{e(str(d.get("값", "")))}</span>{u}</div></div>')
    앞틀, 뒤틀 = ("num--context", "") if 종류 == "실적" else ("", "num--accent")
    증감 = _v2증감(c.get("증감"), p + ".증감")
    세로 = 폭 <= 4 and 높이 >= 360
    return (f'<div class="card np{" np--col" if 세로 else ""}" data-ent="전후숫자" data-path="{e(p)}">'
            f'{_v2글(c.get("라벨"), p + ".라벨", 목적, "kpi__label")}'
            f'<div class="np__row" style="--chars:{속성값.수(round(글자수, 1), p + ".글자수", 기본=3, 최소=1, 최대=20)}">'
            f'{쪽(앞, p + ".이전", 앞틀)}<span class="np__arrow" data-derived="1">{"↓" if 세로 else "→"}</span>{쪽(뒤, p + ".이후", 뒤틀)}</div>'
            + (f'<div class="kpi__ctx">{증감}</div>' if 증감 else "") + "</div>")


def _v2짝칸(d, q, 목적, 틀):
    e = html.escape
    if not isinstance(d, dict):
        return f'<div class="{e(틀)}"></div>'
    보조 = (f'<span class="pair__s tx" data-path="{e(q + ".보조")}">{e(str(d["보조"]))}</span>' if d.get("보조") else "")
    아이콘 = _v2아이콘(d.get("아이콘"), q + ".아이콘", "ico ico--accent" if 틀 == "pair__from" else "ico")
    return (f'<div class="{e(틀)}" data-ent="항목">{아이콘}<div class="pair__tx">'
            f'<span class="pair__t tx" data-path="{e(q + ".글")}">{e(str(d.get("글", "")))}</span>{보조}</div></div>')


def _v2짝카드(c, p, 목적):
    e = html.escape
    변형 = 속성값.열거(c.get("변형"), ("짝", "대비"), p + ".변형", 기본="짝")
    왼제 = f'<span class="pair__h is-from tx" data-path="{e(p + ".왼제목")}">{e(str(c.get("왼제목", "")))}</span>'
    오른제 = f'<span class="pair__h is-to tx" data-path="{e(p + ".오른제목")}">{e(str(c.get("오른제목", "")))}</span>'
    if 변형 == "대비":
        왼 = "".join(_v2짝칸(d, f"{p}.왼항목.{j}", 목적, "pair__from") for j, d in enumerate(c.get("왼항목") or []))
        오른 = "".join(_v2짝칸(d, f"{p}.오른항목.{j}", 목적, "pair__to") for j, d in enumerate(c.get("오른항목") or []))
        return (f'<div class="vs" data-ent="짝카드" data-path="{e(p)}"><div class="vs__col">{왼제}{왼}</div>'
                f'<div class="vs__col">{오른제}{오른}</div></div>')
    줄 = [(j, x) for j, x in enumerate(c.get("줄") or []) if isinstance(x, dict)]
    rows = "".join(f'<div class="pair__row">{_v2짝칸(x.get("왼"), f"{p}.줄.{j}.왼", 목적, "pair__from")}'
                   f'<span class="pair__arrow" data-derived="1">→</span>'
                   f'{_v2짝칸(x.get("오른"), f"{p}.줄.{j}.오른", 목적, "pair__to")}</div>' for j, x in 줄)
    return (f'<div class="pair" data-ent="짝카드" data-path="{e(p)}"><div class="pair__head">{왼제}'
            f'<span></span>{오른제}</div>{rows}</div>')


def _v2타임라인(c, p, 목적):
    e = html.escape
    단계 = [(j, x) for j, x in enumerate(c.get("단계") or []) if isinstance(x, dict)][:6]
    steps = []
    for j, x in 단계:
        q = f"{p}.단계.{j}"
        상 = 속성값.열거(x.get("상태"), tuple(_V2단계상태), q + ".상태", 기본="예정")
        설명 = [t for t in x.get("설명") or [] if isinstance(t, str)]
        desc = ("<span class=\"ribbon__desc\">" + "".join(
            f'<span class="tx" data-path="{e(f"{q}.설명.{m}")}">{e(t)}</span>' for m, t in enumerate(설명)) + "</span>") if 설명 else ""
        steps.append(f'<div class="ribbon__step{_V2단계상태[상]}" data-ent="항목">'
                     f'<span class="ribbon__when tx" data-path="{e(q + ".시점")}">{e(str(x.get("시점", "")))}</span>'
                     f'<span class="ribbon__what tx" data-path="{e(q + ".제목")}">{e(str(x.get("제목", "")))}</span>{desc}</div>')
    띠 = ('<div class="ribbon__band"><div class="ribbon__body"></div><svg class="ribbon__tip" viewBox="0 0 40 88" '
         'preserveAspectRatio="none"><polygon points="0,0 40,44 0,88"/></svg></div>')
    상시 = "".join(f'<div class="ribbon__span" data-ent="항목"><span class="ribbon__span-k tx" data-path="{e(f"{p}.상시.{m}.기간")}">'
                 f'{e(str(x.get("기간", "")))}</span><span class="tx" data-path="{e(f"{p}.상시.{m}.제목")}">{e(str(x.get("제목", "")))}</span></div>'
                 for m, x in enumerate(c.get("상시") or []) if isinstance(x, dict))
    return (f'<div class="tl" data-ent="타임라인" data-path="{e(p)}"><div class="ribbon" style="--n:'
            f'{속성값.수(len(steps) or 1, p + ".n", 기본=4, 최소=1, 최대=6)}">{띠}{"".join(steps)}</div>{상시}</div>')


def _v2세로타임라인(c, p, 목적):
    e = html.escape
    out = [f'<div class="card vtl-card" data-ent="세로타임라인" data-path="{e(p)}"><div class="vtl">']
    for j, x in enumerate(c.get("항목") or []):
        if not isinstance(x, dict):
            continue
        q = f"{p}.항목.{j}"
        상 = 속성값.열거(x.get("상태"), tuple(_V2단계상태), q + ".상태", 기본="예정")
        설명 = (f'<span class="vtl__desc tx" data-path="{e(q + ".설명")}">{e(str(x["설명"]))}</span>' if x.get("설명") else "")
        out.append(f'<div class="vtl__item{_V2단계상태[상]}" data-ent="항목"><span class="vtl__dot"></span>'
                   f'<span class="vtl__when tx" data-path="{e(q + ".시점")}">{e(str(x.get("시점", "")))}</span>'
                   f'<div class="vtl__tx"><span class="vtl__what tx" data-path="{e(q + ".제목")}">{e(str(x.get("제목", "")))}</span>'
                   f'{설명}{_v2뱃지(x.get("상태"), q + ".상태")}</div></div>')
    out.append("</div></div>")
    return "".join(out)


def _v2요청상자(c, p, 목적):
    e = html.escape
    변형 = 속성값.열거(c.get("변형"), ("진하게", "밝게"), p + ".변형", 기본="진하게")
    금액 = c.get("금액") if isinstance(c.get("금액"), dict) else None
    main = []
    if c.get("분류"):
        main.append(_v2글(c.get("분류"), p + ".분류", 목적, "ask__kicker"))
    if 금액:
        글자수 = len(str(금액.get("값", ""))) + len(str(금액.get("단위", ""))) * 0.7 + 0.5
        u = (f'<span class="num__u tx" data-path="{e(p + ".금액.단위")}">{e(str(금액["단위"]))}</span>' if 금액.get("단위") else "")
        main.append(f'<div class="num num--xl num--fit" style="--chars:{속성값.수(round(글자수, 1), p + ".글자수", 기본=5, 최소=1, 최대=20)}">'
                    f'<span class="num__v tx" data-path="{e(p + ".금액.값")}">{e(str(금액.get("값", "")))}</span>{u}</div>')
    main.append(f'<div class="ask__what">{_v2글(c.get("요청문"), p + ".요청문", 목적)}</div>')
    행 = "".join(f'<div class="ask__row" data-ent="항목"><dt class="tx" data-path="{e(f"{p}.행.{j}.이름")}">{e(str(x.get("이름", "")))}</dt>'
                f'<dd class="tx" data-path="{e(f"{p}.행.{j}.내용")}">{e(str(x.get("내용", "")))}</dd></div>'
                for j, x in enumerate(c.get("행") or []) if isinstance(x, dict))
    return (f'<div class="ask{" ask--light" if 변형 == "밝게" else ""}" data-ent="요청상자" data-path="{e(p)}">'
            f'<div class="ask__in"><div class="ask__main">{"".join(main)}</div>'
            + (f'<dl class="ask__rows">{행}</dl>' if 행 else "") + "</div></div>")


def _v2인용(c, p, 목적):
    e = html.escape
    밝게 = c.get("변형") == "밝게"
    return (f'<blockquote class="quote{" quote--light" if 밝게 else ""}" data-ent="인용" data-path="{e(p)}">'
            f'<span class="quote__mark" data-derived="1">“</span>'
            f'<p class="quote__text">{_v2글(c.get("인용문"), p + ".인용문", 목적)}</p>'
            f'<span class="quote__by">{_v2글(c.get("말한이"), p + ".말한이", 목적)}</span></blockquote>')


def _v2표(c, p, 목적):
    e = html.escape
    머리 = [str(x) for x in c.get("머리행") or []]
    정렬 = [속성값.열거(x, tuple(_V2열정렬), f"{p}.열정렬.{k}", 기본="글") for k, x in enumerate(c.get("열정렬") or [])]
    정렬 += ["글"] * (len(머리) - len(정렬))
    강 = c.get("강조행") if isinstance(c.get("강조행"), int) and not isinstance(c.get("강조행"), bool) else None
    th = "".join(f'<th class="{_V2열정렬[정렬[k]]}" data-ent="표칸"><span class="tx" data-path="{e(f"{p}.머리행.{k}")}">{e(t)}</span></th>'
                 for k, t in enumerate(머리))
    rows = []
    for r, 행 in enumerate(c.get("행") or []):
        if not isinstance(행, list):
            continue
        tds = []
        for k, 셀 in enumerate(행[:len(머리) or None]):
            틀 = _V2열정렬[정렬[k]] if k < len(정렬) else ""
            틀 = (틀 + " k").strip() if k == 0 and 틀 != "n" else 틀
            if isinstance(셀, dict):
                칩 = _v2뱃지(셀.get("상태"), f"{p}.행.{r}.{k}.상태") + _v2증감(셀.get("증감"), f"{p}.행.{r}.{k}.증감",
                                                                   str(셀.get("글", "")))
                tds.append(f'<td class="{e(틀)}" data-ent="표칸"><span class="tx" data-path="{e(f"{p}.행.{r}.{k}.글")}">'
                           f'{e(str(셀.get("글", "")))}</span>{" " + 칩 if 칩 else ""}</td>')
            else:
                tds.append(f'<td class="{e(틀)}" data-ent="표칸"><span class="tx" data-path="{e(f"{p}.행.{r}.{k}")}">'
                           f'{e(str(셀))}</span></td>')
        rows.append(f'<tr{" class=is-focus" if r == 강 else ""}>{"".join(tds)}</tr>')
    # 요지가 있으면 표를 묶음(.stack) 안에 두는데, 예전엔 .grow 가 없어 표가 제 높이에 멈춰 판 아래 절반이 비었다 — bench14
    # 심사가 '표 아래 절반이 비었다'를 열 번 짚었다(s2 A 4쪽·s7 M 3쪽, 두 장 모두 요지 달린 표). 요지 없는 표는 칸 높이로 늘었다
    몸 = (f'<div class="tbl-wrap{" grow" if c.get("요지") else ""}" data-ent="표" data-path="{e(p)}"><table class="tbl"><thead><tr>{th}</tr></thead>'
         f'<tbody>{"".join(rows)}</tbody></table></div>')
    if c.get("요지"):
        return (f'<div class="stack" data-ent="표묶음">{몸}<p class="chart-panel__so">'
                f'{_v2글(c.get("요지"), p + ".요지", 목적)}</p></div>')
    return 몸


def _v2체계도(c, p, 목적):
    e = html.escape
    이름만 = c.get("변형") == "이름만"
    목표 = [(j, x) for j, x in enumerate(c.get("목표") or []) if isinstance(x, dict)]
    과제 = [(j, x) for j, x in enumerate(c.get("과제") or []) if isinstance(x, dict)]
    out = [f'<div class="sys{" sys--names" if 이름만 else ""}{"" if 목표 else " sys--nogoal"}" data-ent="체계도" data-path="{e(p)}">',
           f'<div class="sys__vision"><span class="sys__vk" data-derived="1">비전</span>'
           f'{_v2글(c.get("비전"), p + ".비전", 목적, "sys__vt")}</div>']
    if 목표:
        out.append(f'<div class="sys__goals" style="--n:{속성값.수(len(목표), p + ".목표수", 기본=3, 최소=1, 최대=6)}">'
                   + "".join(f'<div class="sys__goal" data-ent="항목"><span class="sys__gk tx" data-path="{e(f"{p}.목표.{j}.분류")}">'
                             f'{e(str(x.get("분류", "")))}</span><span class="sys__gt tx" data-path="{e(f"{p}.목표.{j}.값")}">'
                             f'{e(str(x.get("값", "")))}</span></div>' for j, x in 목표) + "</div>")
    칸 = []
    for 순, (j, x) in enumerate(과제):
        항목 = "" if 이름만 else "".join(f'<li class="tx" data-path="{e(f"{p}.과제.{j}.항목.{m}")}">{e(str(t))}</li>'
                                       for m, t in enumerate(x.get("항목") or []) if isinstance(t, str))
        칸.append(f'<div class="sys__task" data-ent="항목"><span class="sys__no" data-derived="1">{순 + 1}</span>'
                 f'<span class="sys__tt tx" data-path="{e(f"{p}.과제.{j}.이름")}">{e(str(x.get("이름", "")))}</span>'
                 + (f'<ul class="sys__items">{항목}</ul>' if 항목 else "") + "</div>")
    out.append(f'<div class="sys__tasks" style="--n:{속성값.수(len(과제) or 1, p + ".과제수", 기본=4, 최소=1, 최대=6)}">{"".join(칸)}</div>')
    out.append("</div>")
    return "".join(out)


def _v2색띠행(c, p, 목적):
    e = html.escape
    rows = []
    for 순, (j, x) in enumerate((j, x) for j, x in enumerate(c.get("행") or []) if isinstance(x, dict)):
        항목 = "".join(f'<li data-ent="항목"><span class="tx" data-path="{e(f"{p}.행.{j}.항목.{m}")}">{e(str(t))}</span></li>'
                     for m, t in enumerate(x.get("항목") or []) if isinstance(t, str))
        rows.append(f'<div class="rowband__row"><div class="rowband__key"><span data-derived="1">{_V2원문자[순 % 10]}</span>&#160;'
                    f'<span class="tx" data-path="{e(f"{p}.행.{j}.분야")}">{e(str(x.get("분야", "")))}</span></div>'
                    f'<div class="rowband__val"><ul class="checks">{항목}</ul></div></div>')
    return f'<div class="rowband" data-ent="색띠행" data-path="{e(p)}">{"".join(rows)}</div>'


def _v2아이콘목록(c, p, 목적):
    e = html.escape
    세로 = c.get("방향") == "세로"
    항목 = [(j, x) for j, x in enumerate(c.get("항목") or []) if isinstance(x, dict)]
    it = "".join(f'<div class="icl__i" data-ent="항목">{_v2아이콘(x.get("아이콘"), f"{p}.항목.{j}.아이콘", "ico")}'
                 f'<div class="icl__tx"><span class="icl__g tx" data-path="{e(f"{p}.항목.{j}.글")}">{e(str(x.get("글", "")))}</span>'
                 + (f'<span class="icl__s tx" data-path="{e(f"{p}.항목.{j}.보조")}">{e(str(x["보조"]))}</span>' if x.get("보조") else "")
                 + "</div></div>" for j, x in 항목)
    제목 = _v2글(c.get("제목"), p + ".제목", 목적, "icl__t") if c.get("제목") else ""
    return (f'<div class="icl{" icl--col" if 세로 else ""}" data-ent="아이콘목록" data-path="{e(p)}">{제목}'
            f'<div class="icl__items" style="--n:{속성값.수(len(항목) or 1, p + ".n", 기본=4, 최소=1, 최대=6)}">{it}</div></div>')


def _v2글머리(c, p, 목적):
    """글머리 — 항목은 글 또는 {글, 하위}(schema oneOf, 카드 항목과 같은 모양). '26-09-28 적대 검토
    (렌더 H2): 예전엔 {글, 하위} 항목을 건너뛰어 배포글 장이 빈 카드로 나왔다(다른 칸이 있으면 무경고)."""
    e = html.escape
    out = []
    for j, it in enumerate(c.get("항목") or []):
        if isinstance(it, dict):
            하위 = "".join(f'<li data-ent="항목">{_v2글(s, f"{p}.항목.{j}.하위.{m}", 목적)}</li>'
                         for m, s in enumerate(it.get("하위") or []) if isinstance(s, str))
            out.append(f'<li data-ent="항목">{_v2글(it.get("글"), f"{p}.항목.{j}.글", 목적)}'
                       f'{f"<ul class=sub>{하위}</ul>" if 하위 else ""}</li>')
        elif isinstance(it, (str, list)):
            out.append(f'<li data-ent="항목">{_v2글(it, f"{p}.항목.{j}", 목적)}</li>')
    return f'<div class="card" data-ent="글머리" data-path="{e(p)}"><ul class="checks">{"".join(out)}</ul></div>'


def _v2부품(c, p, 목적, 폭, 자동, 높이=420, 글자수=4):
    """부품 하나 → HTML. 모르는 부품은 그리지 않는다(게이트가 먼저 막는다)."""
    n = c.get("부품")
    if n == "지표타일":
        return _v2지표타일(c, p, 목적, 글자수)
    if n == "카드":
        return _v2카드(c, p, 목적)
    if n == "항목타일":
        return _v2항목타일(c, p, 목적)
    if n == "수량목록":
        return _v2수량목록(c, p, 목적)
    if n == "진행막대":
        return _v2진행막대(c, p, 목적, 자동)
    if n == "가로막대":
        return _v2가로막대(c, p, 목적, 폭, 높이)
    if n == "점눈금":
        return _v2점눈금(c, p, 목적, 폭)
    if n == "선차트":
        return _v2선차트(c, p, 목적, 폭, 높이)
    if n == "비율링":
        return _v2비율링(c, p, 목적)
    if n == "구성띠":
        return _v2구성띠(c, p, 목적, 자동)
    if n == "전후숫자":
        return _v2전후숫자(c, p, 목적, 폭, 높이)
    if n == "짝카드":
        return _v2짝카드(c, p, 목적)
    if n == "타임라인":
        return _v2타임라인(c, p, 목적)
    if n == "세로타임라인":
        return _v2세로타임라인(c, p, 목적)
    if n == "요청상자":
        return _v2요청상자(c, p, 목적)
    if n == "인용":
        return _v2인용(c, p, 목적)
    if n == "표":
        return _v2표(c, p, 목적)
    if n == "체계도":
        return _v2체계도(c, p, 목적)
    if n == "색띠행":
        return _v2색띠행(c, p, 목적)
    if n == "아이콘목록":
        return _v2아이콘목록(c, p, 목적)
    if n == "글머리":
        return _v2글머리(c, p, 목적)
    return ""


def _v2지표글자수(c):
    return len(str(c.get("값", ""))) + len(str(c.get("단위", ""))) * 0.7 + 0.3


def _v2줄계획(장, 가용):
    """장 본문의 줄 계획 — (줄들, 줄틀, 줄 높이, 칸이 가장 크게 설 높이) 또는 None(칸 없음).
    _v2본문(그리기)·_v2덱배율(덱 배율 셈)·_v2남는높이(게이트 권고)가 같은 계획을 본다."""
    줄들 = _v2배치(장.get("유형"), 장.get("칸") or [])
    if not 줄들:
        return None
    틀 = _v2줄틀(줄들[:2], 가용)
    # 두 칸짜리 짧은 글 줄은 가운데 10열로 좁힌다(넓은 칸에 짧은 글 = 빈 카드처럼 보인다)
    if 틀 == "fit" and len(줄들) == 1 and len(줄들[0]) == 2 and all(w == 6 for _, w, _ in 줄들[0]) \
            and all(항목[0] != "묶음" and not _v2폭(항목[1]) and _v2최소폭(항목) <= 5
                    and _v2어림(항목[1], 6)[1] < 가용 * 0.5 for 항목, _, _ in 줄들[0]):
        줄들 = [[(줄들[0][0][0], 5, 1), (줄들[0][1][0], 5, 0)]]
    줄높이 = 가용 if len(줄들) == 1 else (가용 - 24) / 2
    # 채움 배율(bench13 ①) — 칸이 가장 크게 설 높이(내용 맞춤이면 줄의 9할)에 견준다
    최대칸 = min(max(232, round(줄높이 * 0.9)), int(줄높이)) if 틀 == "fit" else 줄높이
    return 줄들, 틀, 줄높이, 최대칸


# 프리셋별 본문 구역 높이(머리 한 줄 · 리드·요지띠 없음)와 머리 메시지 글자·폭 — '26-09-30 r4 적대 검토 렌더 실측(CDP):
# data 510 · keynote 503 · briefing 544px. 예전엔 510 하나로 셈해 브리핑 장은 34px 모자라게, 발표 긴 머리(두 줄, 본문
# 438px)는 72px 넘치게 어림했다(R1·R5). 렌더의 내용 맞춤 칸은 실제 높이의 몫(--fit-fr)으로 서고, 이 어림은 줄 틀·배율·
# 권고(W-판아래빔)만 고른다
_V2판높이 = {"data": 510, "keynote": 503, "briefing": 544}
_V2머리글 = {"data": (40, 1152), "keynote": (52, 1104), "briefing": (34.2, 1060)}


def _v2가용(장, 프리셋="data"):
    """본문 구역 높이 어림(px) — 프리셋 판 높이에서 머리 둘째 줄부터·리드·요지띠가 먹는 높이를 뺀다(build_v2 와 같은 셈)."""
    프리셋 = 프리셋 if 프리셋 in _V2판높이 else "data"
    머리 = 장.get("머리") if isinstance(장.get("머리"), dict) else {}
    fs, 폭 = _V2머리글[프리셋]
    글 = _v2글자(머리.get("메시지")) + (" " + _v2글자(머리.get("라벨")) if 프리셋 == "briefing" and 머리.get("라벨") else "")
    # 글 폭 = 어림 em × 0.86(Noto Sans KR 800·자간 −0.02em 실측 — bench14 keynote 머리 23.7em 이 1104px 한 줄에 든다)
    줄수 = max(1, math.ceil(_v2글폭em(글) * fs * 0.86 / 폭)) if 글 else 1
    return (_V2판높이[프리셋] - round((줄수 - 1) * fs * 1.25)
            - (72 if 장.get("리드") else 0) - (88 if 장.get("요지띠") else 0))


# ── 덱 단위 채움 배율('26-09-30 bench14 — 주관 판정 ③) ──────────────────────────────────────
# 배율은 사다리 한 단이다(연속값이면 29.7·33·35.1·36.4px 같은 크기가 덱 안에 흩어진다 — r4 진단 §4, 3차 덱 본문 글자
# 크기 8~11종). 부품마다(밀도마다) 덱에서 한 배율: 그 부품이 든 모든 칸이 넘치지 않는 가장 큰 단(칸마다 내용이 칸의 85%
# 이하) — 그 부품 칸 가운데 하나라도 속이 비어 키울 까닭이 있을 때만 키운다. 넘침 안전망(_V2배율안전망)은 그대로다.
_V2배율사다리 = (1.0, 1.15, 1.3, 1.5)


def _v2배율받나(c):
    """채움 배율을 받는 부품인가 — 세로묶음·요청상자·인용·늘림 부품(차트·표·타임라인)·숫자 부품은 받지 않는다."""
    if not isinstance(c, dict) or c.get("부품") in ("세로묶음", "요청상자", "인용") or c.get("부품") in _V2숫자부품:
        return False
    return not _v2어림(c, 12)[0]


def _v2가능배율(c, 폭, 칸높이, 밀도="보고"):
    """이 칸에서 넘치지 않는 사다리 가장 큰 단(내용 ≤ 칸의 85% · 밀도 상한 · 긴 어절 폭 · 알약 위계)."""
    if not _v2배율받나(c) or 칸높이 <= 0:
        return 1.0
    상한 = min(_V2배율상한.get(밀도, 1.4), _v2폭배율상한(c, 폭, 밀도))
    알약 = _v2알약배율(c, 폭, 밀도)
    if 알약 < 9.0:
        상한 = min(상한, 28 * 알약 / (22 * _V2밀도글.get(밀도, 1.0)))
    for f in reversed(_V2배율사다리):
        if f <= 상한 + 1e-9 and (f == 1.0 or _v2제높이(c, 폭, f, 밀도) / 칸높이 <= 0.85):
            return f
    return 1.0


def _v2덱배율(doc, 밀도="보고"):
    """{(부품, 밀도): 배율} — 덱 단위 채움 배율 표(build_v2 가 한 번 셈해 모든 장에 준다).
    알약 제목 배율도 덱에 하나('알약', 밀도) — 카드마다 알약 폭이 달라 칸마다 --fzp 가 갈렸다."""
    가능, 원함, 알약 = {}, {}, {}
    for 장 in doc.get("장") or []:
        if not isinstance(장, dict) or 장.get("유형") in ("표지", "목차", "간지", "마무리"):
            continue
        장밀도 = 장.get("밀도") if 장.get("밀도") in _V2밀도 else 밀도
        계획 = _v2줄계획(장, _v2가용(장, doc.get("프리셋")))
        if not 계획:
            continue
        줄들, _, _, 최대칸 = 계획
        장가능 = {}                     # 장마다 한 표(그 장 같은 부품 칸 가운데 가장 작은 단) — 칸 수가 아니라 장 수로 센다
        for 줄 in 줄들:
            for 항목, 폭, _ in 줄:
                if 항목[0] == "묶음" or not _v2배율받나(항목[1]):
                    continue
                c, 키 = 항목[1], (항목[1].get("부품"), 장밀도)
                장가능[키] = min(장가능.get(키, 9.0), _v2가능배율(c, 폭, 최대칸, 장밀도))
                원함[키] = max(원함.get(키, 1.0), _v2채움배율(c, 폭, 최대칸, 장밀도))
                a = _v2알약배율(c, 폭, 장밀도)
                if a < 9.0:
                    알약[("알약", 장밀도)] = min(알약.get(("알약", 장밀도), 9.0), a)
        for 키, f in 장가능.items():
            가능.setdefault(키, []).append(f)
    # 덱 배율 = 그 부품의 모든 칸이 설 수 있는 가장 작은 단(주관 판정 ③ '같은 부품은 같은 배율' — 넘치는 칸이 없다).
    # 값: 빽빽한 칸 하나가 덱의 모든 같은 부품을 누른다(bench14 A s7 재조립 — 10·11장 카드 글 33 → 22px).
    # _V2덱배율많은단 이 참(기본, r4 fixup)이면 가장 많은 **장**이 설 수 있는 단(같으면 작은 단 — '같은 부품 같은 배율' 쪽)을
    # 쓰고 넘치는 칸만 제 단으로 내린다. 칸 수로 세면 빽빽한 5칸 카드 장 하나가 성긴 카드 장 셋을 이겼다(r4 EXAONE w-s7 —
    # 카드 칸 1.5 ×3 · 1.0 ×5 → 장으로는 1.5 ×3 · 1.0 ×1)
    def 많은단(vs):
        if not _V2덱배율많은단:
            return min(vs)
        return max(sorted(set(vs)), key=lambda f: (vs.count(f), -f))
    표 = {k: (max(f for f in _V2배율사다리 if f <= min(많은단(가능[k]), 원함[k]) + 1e-9) if 원함[k] > 1.0 else 1.0)
         for k in 가능}
    if _V2덱한배율:
        for d in {d for _, d in 표}:
            한 = min(v for (n, dd), v in 표.items() if dd == d)
            표.update({k: 한 for k in 표 if k[1] == d})
    for k, a in 알약.items():
        표[k] = max(1.0, min(a, max([v for (n, d), v in 표.items() if n == "카드" and d == k[1]] or [1.0])))
    return 표


def _v2남는높이(장, 밀도="보고", 프리셋="data"):
    """내용 맞춤 장에서 본문 아래로 남는 높이의 몫(0~1, 어림) — 게이트 권고(슬라이드v2 W-판아래빔)가 본다.
    늘림 부품·숫자 부품이 있는 장(칸이 판을 채운다)과 칸 없는 장은 0."""
    가용 = _v2가용(장, 프리셋)
    계획 = _v2줄계획(장, 가용)
    if not 계획 or 계획[1] != "fit":
        return 0.0
    줄들, _, _, 최대칸 = 계획
    if any(항목[0] == "묶음" or 항목[1].get("부품") in _V2숫자부품 for 줄 in 줄들 for 항목, _, _ in 줄):
        return 0.0
    내용 = [_v2제높이(항목[1], 폭, 1.0, 밀도) for 줄 in 줄들 for 항목, 폭, _ in 줄]
    if not 내용:
        return 0.0
    n줄 = len(줄들)
    칸 = min(최대칸, max(232, round(max(내용) / 0.82)))
    칸 = min(최대칸, round(칸 + max(0.0, 가용 - 칸 * n줄 - 24 * (n줄 - 1)) * _v2남는몫(줄들) / n줄))
    칸 = 칸 * n줄 + 24 * (n줄 - 1)                  # 내용 맞춤 칸은 줄마다 같은 최소 높이(--fit-h)
    return max(0.0, round((가용 - 칸) / 가용, 3))


# 덱 배율을 '가장 많은 장이 설 수 있는 단'으로(참, 기본) 할지 '모든 칸이 설 수 있는 단'으로(거짓) 할지
# '26-09-30 r4 fixup: 기본 참 — 엄격(거짓)은 빽빽한 칸 하나가 덱의 같은 부품을 모두 눌러 성긴 장 글이 33 → 22px 로 작아지고
# 판 아래가 더 비었다(r4 적대 검토 렌더 R2: a-s7 10장·합성 x-ext1 3·5장·EXAONE w-s7 3~5장). 그런데도 덱 안 본문 글자 크기
# 종류는 줄지 않았고(8.25 → 8.25, 부품마다 제 CSS 크기), bench14 심사의 '일관' 지적은 글자 크기가 아니라 색 역할(키노트+테마
# 주황 숫자·숲 파란 강조)·장마다 들쭉날쭉한 밀도였다(errs14). 넘치는 칸만 제 단으로 내린다 — 사장님 판정 거리로 남긴다
_V2덱배율많은단 = True
# 덱의 글 부품이 모두 한 배율인가(참이면 부품마다가 아니라 밀도마다 하나 — 실험 스위치)
_V2덱한배율 = False
# 내용 맞춤 장에서 남는 높이 가운데 칸이 나눠 갖는 몫 — 나머지는 본문 아래로 남는다(위는 비우지 않는다).
# 카드·글머리 칸은 키우면 속이 빈 상자가 된다(audit 빈 상자 넓이 — r16_round3 합성 성긴 카드 장 0.42) → 작은 몫,
# 짝카드·인용·아이콘목록·항목타일처럼 칸 높이에 속을 펴는 부품은 큰 몫(판 아래 빈 띠 — 본보기 8장 0.31 → 0.2대)
_V2남는몫 = 0.6
_V2남는몫카드 = 0.35


def _v2남는몫(줄들):
    # 짝카드 '대비'는 따로 선 두 패널이 제 높이로 앉아(css .vs__col) 칸이 커져도 속을 펴지 않는다
    부품들 = {("대비" if 항목[1].get("부품") == "짝카드" and 항목[1].get("변형") == "대비" else 항목[1].get("부품"))
            for 줄 in 줄들 for 항목, _, _ in 줄 if 항목[0] != "묶음"}
    if "대비" in 부품들:
        return 0.0                              # 패널이 제 높이로 앉아 칸을 키워도 빈 곳만 는다 — 남는 높이는 권고(W-판아래빔)로
    return _V2남는몫카드 if 부품들 & {"카드", "글머리"} else _V2남는몫


def _v2본문(장, i, 목적, 가용, 자동, 요청값=(), 밀도="보고", 덱배율=None):
    """칸 → 12열 본문. 줄마다 지표타일 숫자 크기를 맞춘다(가장 긴 값 기준).
    요청값 = 요청상자 금액 값 글들 — 한눈에보기에 붙은 요청 금액 타일('3,600'+'만원', 글자 6.7)은 줄 숫자 크기 셈에서 빼고
    제 글자 수로 줄인다. 예전엔 그 타일 하나 때문에 요약 장 핵심 숫자가 96px → 53.7px 로 작아졌다(round2 적대 검토 M1)."""
    e = html.escape
    계획 = _v2줄계획(장, 가용)
    if not 계획:
        return ""
    줄들, 틀, 줄높이, 최대칸 = 계획
    # 채움 배율 — bench13 ① 은 칸마다 배율을 골랐고(같은 줄의 같은 부품끼리만 맞춤), bench14 심사에서 덱 안 본문 글자
    # 크기가 8~11종(시제품 3종)으로 흩어져 '일관' 지적이 늘었다(r4 진단 §4). 이제 덱 단위로 부품마다 한 배율
    # (_v2덱배율 — 사다리 한 단)을 받아 모든 장의 같은 부품이 같은 크기다. 덱 배율 표가 없으면(옛 호출) 칸마다 고른다.
    줄배율 = []
    for 줄 in 줄들:
        배율 = {}
        for 항목, 폭, _ in 줄:
            if 항목[0] != "묶음":
                n = 항목[1].get("부품")
                if 덱배율 is not None:
                    배율[n] = min(배율.get(n, 9.0), min(덱배율.get((n, 밀도), 1.0), _v2가능배율(항목[1], 폭, 최대칸, 밀도))
                                if _v2배율받나(항목[1]) else 1.0)
                else:
                    배율[n] = min(배율.get(n, 9.0), _v2채움배율(항목[1], 폭, 최대칸, 밀도))
        줄배율.append(배율)
    if 틀 == "fit":
        # 내용 맞춤 — 칸 높이를 (배율로 키운) 내용 높이에 맞춘다(css .sl-body.is-fit). round2 는 칸을 줄의 9할로 늘려
        # 속이 빈 큰 카드가 됐고('26-09-29 bench13 심사 '카드는 큰데 속이 비었다'), round3 는 칸을 내용에 맞추고 본문을
        # 세로 가운데 두어 머리 아래 틈이 24 → 50px 로 벌어졌다(bench14 '판 가운데 떠서 위·아래가 빈다', r4 진단 §4).
        # 이제 본문은 머리 바로 아래(위)에서 시작하고, 남는 높이는 칸이 _V2남는몫 만큼 나눠 갖는다 — 나머지는 아래로
        # 남고, 넓게 남으면 게이트가 요지띠·지표타일(자료에 있는 값만)을 권한다(슬라이드v2 W-판아래빔).
        # 칸은 내용의 1/0.82 배 — 속이 8할쯤 찬다. 바닥 232 · 줄의 9할 · 줄 높이를 넘지 않는다(round2 M4).
        내용 = max([_v2제높이(항목[1], 폭, 줄배율[k].get(항목[1].get("부품"), 1.0), 밀도)
                  for k, 줄 in enumerate(줄들) for 항목, 폭, _ in 줄 if 항목[0] != "묶음"] or [최대칸])
        # 숫자 부품(지표타일·전후숫자·비율링·진행막대)은 숫자가 칸 높이를 따라 커진다 — 그 줄은 칸을 줄이지 않는다
        # (줄이면 숫자가 작아졌다: bench13 A s7 3장 전후숫자 4칸 실측)
        숫자줄 = any(항목[0] == "묶음" or 항목[1].get("부품") in _V2숫자부품 for 줄 in 줄들 for 항목, _, _ in 줄)
        n줄 = len(줄들)
        # 숫자 줄은 줄 높이를 다 쓴다 — 위에서부터 채우니 '줄의 9할'(가운데 정렬 때 값) 상한이 판 아래 10%를 늘 남겼다
        # (r4 적대 검토 렌더 R1: 숫자 줄 장 아래 틈 101px, 시제품 16px)
        바닥 = min(최대칸, 232) if 숫자줄 else min(최대칸, max(232, round(내용 / 0.82)))
        맞춤 = 줄높이 if 숫자줄 else min(최대칸, round(바닥 + max(0.0, 가용 - 바닥 * n줄 - 24 * (n줄 - 1)) * _v2남는몫(줄들) / n줄))
        # 칸 높이는 **실제 본문 높이의 몫**(--fit-fr, 줄마다 fr — 합이 1 아래면 그만큼만 먹는다)과 내용 바닥(--fit-h) 가운데
        # 큰 쪽이다. 가용(어림)은 프리셋·머리 줄 수를 다 모른다 — 실측 본문 438(발표 긴 머리)~544px(브리핑) — px 로 박으면 긴
        # 머리 장은 넘치고 브리핑 장은 모자랐다(R1·R5). 바닥은 몫을 뺀 내용 높이라 작은 판에서도 넘치지 않는다
        몫 = 맞춤 / max(1.0, 가용 - 24 * (n줄 - 1))
        바닥 = min(바닥, 맞춤)
        out = [f'<div class="sl-body {_V2줄틀[틀]}" style="--fit-h:{속성값.수(바닥, "맞춤높이", 기본=232, 최소=120, 최대=520)}px;'
               f'--fit-fr:{속성값.수(round(몫, 3), "맞춤몫", 기본=0.5, 최소=0.1, 최대=1)}fr">']
    else:
        out = [f'<div class="sl-body {_V2줄틀[틀]}">']
    for 줄, 배율 in zip(줄들, 줄배율):     # 3줄 이상은 _v2한건 이 되돌린다 — 여기서 말없이 버리지 않는다
        지표들 = [항목[1] for 항목, _, _ in 줄 if 항목[0] != "묶음" and 항목[1].get("부품") == "지표타일"]
        요청타일 = [x for x in 지표들 if 장.get("유형") == "한눈에보기" and str(x.get("값")) in 요청값]
        줄글자 = max([_v2지표글자수(x) for x in 지표들 if x not in 요청타일] or [_v2지표글자수(x) for x in 지표들] or [4])
        for 항목, 폭, 들여 in 줄:
            if 항목[0] == "묶음":
                칸높이 = (줄높이 - 16 * (len(항목[1]) - 1)) / max(1, len(항목[1]))
                안 = "".join(_v2부품(c, f"장.{i}.칸.{k}", 목적, 폭, 자동, 칸높이, _v2지표글자수(c)) for k, c in 항목[1])
                out.append(f'<div class="v2-cell c-{속성값.수(폭, "폭", 기본=12, 최소=1, 최대=12)}{_V2들여.get(들여, "")}">'
                           f'<div class="v2-stack">{안}</div></div>')
                continue
            k, c = 항목
            q = f"장.{i}.칸.{k}"
            if c.get("부품") == "세로묶음":
                자식 = [(m, x) for m, x in enumerate(c.get("칸") or []) if isinstance(x, dict)]
                묶음글자 = max([_v2지표글자수(x) for _, x in 자식 if x.get("부품") == "지표타일"] or [4])
                칸높이 = (줄높이 - 16 * (len(자식) - 1)) / max(1, len(자식))
                안 = "".join(_v2부품(x, f"{q}.칸.{m}", 목적, 폭, 자동, 칸높이, 묶음글자) for m, x in 자식)
                out.append(f'<div class="v2-cell c-{속성값.수(폭, "폭", 기본=12, 최소=1, 최대=12)}{_V2들여.get(들여, "")}">'
                           f'<div class="v2-stack" data-ent="세로묶음" data-path="{e(q)}">{안}</div></div>')
                continue
            fz = 배율.get(c.get("부품"), 1.0)
            # --fzp = 알약 제목 배율(nowrap 이라 카드 폭 안에 드는 만큼만 — round3 적대 검토 L1). 덱 배율 표가 있으면
            # 덱에 하나(가장 긴 알약이 드는 단) — 카드마다 알약 글자 크기가 갈리지 않게
            알약배 = (min(fz, 덱배율.get(("알약", 밀도), 1.0)) if 덱배율 is not None and ("알약", 밀도) in 덱배율
                   else min(fz, _v2알약배율(c, 폭, 밀도)))
            키움 = (f' is-z" style="--fz:{속성값.수(fz, "채움배율", 기본=1, 최소=1, 최대=1.6)};'
                  f'--fzp:{속성값.수(알약배, "알약배율", 기본=1, 최소=1, 최대=1.6)}'
                  if fz > 1.0 else "")
            out.append(f'<div class="v2-cell c-{속성값.수(폭, "폭", 기본=12, 최소=1, 최대=12)}{_V2들여.get(들여, "")}{키움}">'
                       f'{_v2부품(c, q, 목적, 폭, 자동, 줄높이, max(줄글자, _v2지표글자수(c)) if c in 요청타일 else 줄글자)}</div>')
    out.append("</div>")
    return "".join(out)


def _v2쪽(n):
    return f"{n:02d}"


def _v2같은말(a, b, 품기=True):
    """두 글이 띄어쓰기·가운뎃점을 빼고 같나 — 품기면 한쪽이 다른 쪽을 품어도 같다(꼬리말 기관명 중복 판정)."""
    a, b = (re.sub(r"[\s·ㆍ.,]+", "", str(x or "")) for x in (a, b))
    return bool(a and b) and (a == b or (품기 and (a in b or b in a)))


def _v2출처글(출처, 문서명):
    """꼬리말 왼쪽 출처 — (가릴 앞머리, 보일 글). 문서명(기관·부서, 오른쪽에 이미 찍힘)과 같은 말이면 ("", "")
    (그리지 않는다), 문서명 낱말로 **시작**하면 그 앞머리만 가리고 자료 이름은 보인다. round2 적대 검토 H4: 예전엔
    출처가 문서명을 품기만 해도 통째로 뺐다 — '○○공사 경영공시('25년)'가 화면에서 사라졌다. 앞머리는 지우지 않고
    가린다(편집기가 .tx 글 전체를 문서 값으로 되쓰므로 글은 그대로 남아야 한다 — 왕복 불변식)."""
    원 = str(출처 or "")
    t = 원.strip()
    # 자리표시뿐인 출처('○○' — 지어냄 교정이 자료에 없는 출처 이름을 ○○ 로 바꾼 자리, r4 EXAONE s2 채택본)는 꼬리말에 찍지 않는다
    if not t or _v2같은말(t, 문서명, 품기=False) or re.fullmatch(r"[○△□◯●\s\-–—·.,()]*", t):
        return "", ""
    앞 = 원[:len(원) - len(원.lstrip())]
    for 낱 in str(문서명 or "").split():
        남 = t[len(낱):] if t.startswith(낱) else None
        if 남 is not None and re.match(r"[\s·,]", 남 or " ") and len(re.sub(r"[\s·,()]", "", 남)) >= 2:
            뗌 = len(t) - len(남.lstrip(" ·,"))
            앞, t = 앞 + t[:뗌], t[뗌:]
    return 앞, t


def _v2꼬리(장, i, 쪽, 문서명, 자동=None):
    """꼬리말 — 출처 한 줄 · 문서명 · 쪽. 장마다 같은 자리: 왼쪽 = 출처(있을 때만), 오른쪽 = 기관·부서 + 쪽.
    '26-09-29 bench11 심사 3인: ① 모델이 출처에 기관·부서 이름을 적어 왼쪽·오른쪽에 같은 이름이 두 번(일부 장만)
    찍혔다 → 출처가 문서명(기관·부서)과 같은 말이면 화면에서 뺀다(자료 이름이 아니다). ② '…은 산출' 꼬리가
    '작성 메모 노출'로 깎였다 → 화면에서 뺀다. 산출 값·식은 발표자 노트(_v2노트)로만 간다.
    작성 메모도 여기 안 온다(노트로)."""
    e = html.escape
    앞 = ""
    가림, 출처 = _v2출처글(장.get("출처"), 문서명)
    if 출처:
        앞 = (f'<span class="sl-foot__src tx" data-ent="출처" data-path="장.{i}.출처">'
             + (f'<span class="sl-foot__org">{e(가림)}</span>' if 가림 else "") + f'{e(출처)}</span>')
    return (f'<footer class="sl-foot"><span class="sl-foot__note">{앞}</span>'
            f'<span class="sl-foot__doc" data-derived="1">{e(문서명)}</span>'
            f'<span class="sl-foot__no" data-derived="1">{e(_v2쪽(쪽))}</span></footer>')


def _v2노트(장, i, 자동=()):
    """발표자 노트·작성 메모·산출 식 — 화면에는 안 찍는다(hidden). PPTX 노트 칸의 원천.
    산출(모델이 등록한 {값, 식})과 조립기가 계산한 값(진행막대 비율·구성띠 %)은 여기서만 알린다."""
    e = html.escape
    노트 = 장.get("노트")
    out = []
    if isinstance(노트, str) and 노트.strip():
        out.append(f'<p class="tx" data-path="장.{i}.노트">{e(노트)}</p>')
    elif isinstance(노트, dict):
        if 노트.get("말"):
            out.append(f'<p class="tx" data-path="장.{i}.노트.말">{e(str(노트["말"]))}</p>')
        메모 = [(j, m) for j, m in enumerate(노트.get("메모") or []) if isinstance(m, str)]
        if 메모:
            out.append("<ul>" + "".join(f'<li class="tx" data-path="{e(f"장.{i}.노트.메모.{j}")}">{e(m)}</li>' for j, m in 메모) + "</ul>")
    식 = [s for s in 장.get("산출") or [] if isinstance(s, dict) and s.get("값")]
    이미 = {str(s.get("값")) for s in 식}
    줄 = [f'<li>{e(str(s.get("값", "")))}{" = " + e(str(s["식"])) if s.get("식") else " — 자료에서 계산"}</li>' for s in 식]
    줄 += [f'<li>{e(v)} — 조립기가 자료 값으로 계산</li>' for v in dict.fromkeys(자동) if v not in 이미]
    if 줄:
        out.append('<ul class="sl-notes__calc" data-derived="1">' + "".join(줄) + "</ul>")
    if not out:
        return ""
    return f'<aside class="sl-notes" hidden data-ent="노트">{"".join(out)}</aside>'


def _v2머리(장, i, 번호, 목적, 진한):
    e = html.escape
    머리 = 장.get("머리") if isinstance(장.get("머리"), dict) else {}
    if not 머리:
        return ""
    메시지 = str(머리.get("메시지") or "")
    # 머리 강조는 목적과 무관하게 강조색 글자다('26-09-30 주관 판정 ① — 데이터형의 옅은 머리 + 강조색 구절이 v2 표준 꼴:
    # 시제품이 머리 구절을 강조색 글자로 칠해 첫인상·일관에서 앞섰다). 진한 머리띠(브리핑형) 위는 노랑 글자 그대로.
    # 형광 노랑 마커(목적 보고)는 요지띠·런에만 남는다(_v2글)
    강클 = _V2강조.get(목적, "hl") if 진한 else "hl hl--brand"
    조각 = "".join(f'<span class="{강클}">{e(t)}</span>' if h else e(t) for t, h in _v2강조쪼개기(메시지, 머리.get("강조")))
    msg = (f'<span class="sl-head__sep" data-derived="1">:</span>'
           f'<span class="sl-head__msg tx" data-path="장.{i}.머리.메시지">{조각}</span>') if 메시지 else ""
    no = f'<span class="sl-head__no" data-derived="1">{e(str(번호))}</span>' if 번호 else ""
    return (f'<header class="sl-head{" is-dk" if 진한 else ""}" data-ent="머리">{no}<div class="sl-head__txt">'
            f'<span class="sl-head__label tx" data-path="장.{i}.머리.라벨">{e(str(머리.get("라벨") or ""))}</span>{msg}</div></header>')


def _v2리드(장, i, 목적):
    e = html.escape
    리드 = 장.get("리드")
    if isinstance(리드, dict):
        return (f'<div class="sl-lead" data-ent="리드"><span class="sl-lead__a tx" data-path="장.{i}.리드.앞">{e(str(리드.get("앞", "")))}</span>'
                f'<span class="sl-lead__arrow" data-derived="1">→</span>'
                f'<span class="sl-lead__b tx" data-path="장.{i}.리드.뒤">{e(str(리드.get("뒤", "")))}</span></div>')
    if 리드:
        return f'<div class="sl-lead" data-ent="리드">{_v2글(리드, f"장.{i}.리드", 목적)}</div>'
    return ""


def _v2요지띠(장, i, 목적, 진한):
    e = html.escape
    띠 = 장.get("요지띠")
    if not isinstance(띠, dict) or not 띠.get("메시지"):
        return ""
    라벨 = (f'<span class="sl-take__label tx" data-path="장.{i}.요지띠.라벨">{e(str(띠["라벨"]))}</span>' if 띠.get("라벨")
          else '<span class="sl-take__label" data-derived="1">요지</span>')
    return (f'<div class="sl-take{" is-dk" if 진한 else ""}" data-ent="요지띠">{라벨}'
            f'<div class="sl-take__msg">{_v2글(띠.get("메시지"), f"장.{i}.요지띠.메시지", 목적)}</div></div>')


def _v2표지(doc, 장, i):
    """표지 — 기관·부서(위) · 태그·제목·부제(가운데) · 표지 수치(오른쪽) · 회의·일자·발표자(아래).
    태그가 발표정보.회의와 같은 말이면 태그를 뺀다(1단계: 배지와 좌하단이 겹친다는 지적)."""
    e = html.escape
    정 = doc.get("발표정보") if isinstance(doc.get("발표정보"), dict) else {}
    표 = (장 or {}).get("표지") if isinstance((장 or {}).get("표지"), dict) else {}
    위 = []
    if 정.get("기관"):
        위.append(f'<span class="b tx" data-path="발표정보.기관">{e(str(정["기관"]))}</span>')
    if 정.get("부서"):
        위.append(f'<span class="tx" data-path="발표정보.부서">{e(str(정["부서"]))}</span>')
    태그 = str(표.get("태그") or "")
    회의 = str(정.get("회의") or "")
    본 = []
    if 태그 and not (회의 and (태그 == 회의 or 태그 in 회의 or 회의 in 태그)):
        본.append(f'<span class="cover__tag tx" data-path="장.{i}.표지.태그">{e(태그)}</span>')
    본.append(f'<h1 class="cover__title"><span class="tx" data-path="제목">{e(str(doc.get("제목") or ""))}</span></h1>')
    if 표.get("부제"):
        본.append(f'<p class="cover__sub tx" data-path="장.{i}.표지.부제">{e(str(표["부제"]))}</p>')
    elif doc.get("부제"):
        본.append(f'<p class="cover__sub tx" data-path="부제">{e(str(doc["부제"]))}</p>')
    수 = 표.get("수치") if isinstance(표.get("수치"), dict) else None
    수치 = ""
    if 수:
        q = f"장.{i}.표지.수치"
        글자수 = len(str(수.get("값", ""))) + len(str(수.get("단위", ""))) * 0.7 + 0.3
        수치 = (f'<div class="cover__stat" data-ent="표지수치"><span class="cover__stat-l tx" data-path="{e(q + ".라벨")}">{e(str(수.get("라벨", "")))}</span>'
              f'<div class="num num--xl num--fit" style="--chars:{속성값.수(round(글자수, 1), q + ".글자수", 기본=4, 최소=1, 최대=20)}">'
              f'<span class="num__v tx" data-path="{e(q + ".값")}">{e(str(수.get("값", "")))}</span>'
              + (f'<span class="num__u tx" data-path="{e(q + ".단위")}">{e(str(수["단위"]))}</span>' if 수.get("단위") else "")
              + "</div>"
              + (f'<span class="cover__stat-d tx" data-path="{e(q + ".맥락")}">{e(str(수["맥락"]))}</span>' if 수.get("맥락") else "")
              + "</div>")
    가운데 = (f'<div class="cover__split"><div class="stack stack--loose">{"".join(본)}</div>{수치}</div>' if 수치
            else f'<div class="stack stack--loose">{"".join(본)}</div>')
    아래왼 = " · ".join(x for x in (
        f'<span class="tx" data-path="발표정보.회의">{e(회의)}</span>' if 회의 else "",
        f'<span class="tx" data-path="발표정보.발표자">{e(str(정["발표자"]))}</span>' if 정.get("발표자") else "") if x)
    아래오른 = f'<span class="b tx" data-path="발표정보.일자">{e(str(정["일자"]))}</span>' if 정.get("일자") else ""
    return (f'<div class="cover__top">{" ".join(위)}</div><div class="cover__main">{가운데}</div>'
            f'<div class="cover__bottom"><span>{아래왼}</span>{아래오른}</div>')


def _v2목차번호(장들):
    """목차가 있으면 본문 장 머리 번호를 목차 차례에 맞춘다 — {장 색인: 번호}. 목차가 없으면 None(1부터 셈).
    '26-09-29 bench11 심사: 목차는 6개 장인데 장 번호 표지가 1~10 으로 매겨져 어긋났다. 머리.라벨이 목차 항목과
    같은 말인 장을 차례대로 짝짓고(띄어쓰기·가운뎃점 무시, 한쪽이 다른 쪽을 품어도 같다), 짝 없는 항목은 앞 짝 뒤
    첫 '다른 라벨' 장에서 시작한다고 본다. 짝이 하나도 없으면 번호를 달지 않는다(틀린 번호보다 없는 편이 낫다)."""
    목 = next((j for j in 장들 if isinstance(j, dict) and j.get("유형") == "목차"), None)
    항목 = [t for t in ((목 or {}).get("목차") or {}).get("항목") or [] if isinstance(t, str)] if 목 else []
    if not 항목:
        return None
    본 = [(색, str((j.get("머리") or {}).get("라벨") or "")) for 색, j in enumerate(장들)      # '색' — 속성잠금 정적검사는
         if isinstance(j, dict) and j.get("머리") and j.get("유형") not in ("표지", "목차", "간지", "마무리")]   # i 를 enumerate 색인으로만 본다
    시작 = {}                                   # 항목 k → 본 안 위치
    at = 0
    for k, t in enumerate(항목):
        for q in range(at, len(본)):
            if _v2같은말(본[q][1], t):
                시작[k], at = q, q + 1
                break
    if not 시작:
        return {색: 0 for 색, _ in 본}
    for k in range(len(항목)):                   # 짝 없는 항목 — 앞 짝 장 뒤, 라벨이 바뀐 첫 장부터
        if k in 시작:
            continue
        앞 = max([시작[x] for x in 시작 if x < k] or [-1])
        뒤 = min([시작[x] for x in 시작 if x > k] or [len(본)])
        for q in range(앞 + 1, 뒤):
            if 앞 < 0 or not _v2같은말(본[q][1], 본[앞][1]):
                if all(q != v for v in 시작.values()):
                    시작[k] = q
                break
    out, 지금 = {}, 0
    차례 = sorted((q, k) for k, q in 시작.items())
    for q, (색, _) in enumerate(본):
        for qq, k in 차례:
            if qq == q:
                지금 = k + 1
        out[색] = 지금
    return out


def build_v2(doc):
    """판형 v2 문서 → 16:9 슬라이드 HTML(slides_v2.css 하나만 건다)."""
    e = html.escape
    DOC_JSON = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    # 편집기 프로파일은 판형 v2 전용(slides-v2 — 부품·런·막대 칸)을 싣는다. 심긴 genre 는 slides
    # 그대로다(편집기 AI 문체·서버 airewrite 가 장르 키로 읽는다) — 어느 표인지는 '프로파일'이 말한다.
    프로 = load_profile("slides-v2")
    프로["genre"], 프로["프로파일"] = "slides", "slides-v2"
    PROFILE_JSON = json.dumps(프로, ensure_ascii=False).replace("</", "<\\/")
    프리셋 = 속성값.열거(doc.get("프리셋"), tuple(_V2프리셋), "프리셋", 기본="data")
    밀도 = 속성값.열거(doc.get("밀도"), tuple(_V2밀도), "밀도", 기본="보고")
    머리변형 = 속성값.열거(doc.get("머리변형"), tuple(_V2머리변형), "머리변형", 기본="")
    테마 = 속성값.열거(doc.get("테마"), tuple(_V2테마), "테마", 기본="네이비")
    덱목적 = 속성값.열거(doc.get("목적"), tuple(_V2강조), "목적", 기본="보고")
    머리진함 = 머리변형 == "머리띠" or (not 머리변형 and 프리셋 == "briefing")
    요지진함 = 프리셋 != "data"
    정 = doc.get("발표정보") if isinstance(doc.get("발표정보"), dict) else {}
    문서명 = " ".join(str(정.get(k)) for k in ("기관", "부서") if 정.get(k)) or str(doc.get("제목") or "")
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="slides">
<head>
<meta charset="utf-8">{기준도장()}
<title>{e(str(doc.get("제목") or ""))}</title>
<link rel="stylesheet" href="../slides_v2.css?v=">
</head>
<body>
{_문서섬(DOC_JSON, PROFILE_JSON)}""", _V2스프라이트,
             f'<main class="deck v2 {_V2프리셋[프리셋]} {_V2밀도[밀도]}'
             f'{" " + _V2머리변형[머리변형] if 머리변형 else ""}{_V2테마[테마]}">\n']
    장들 = [s for s in doc.get("장") or [] if isinstance(s, dict)]
    쪽 = 0
    if not 장들 or 장들[0].get("유형") != "표지":
        쪽 += 1
        parts.append(f'<section class="sl-page is-cover v2-표지" data-ent="표지" data-layout="표지">{_v2표지(doc, None, -1)}</section>\n')
    번호 = 0
    목차번호 = _v2목차번호(doc.get("장") or [])
    import slides_v2_gate as _게
    요청값 = {str((_게.요청금액(c) or {}).get("값")) for s in 장들 for c in (s.get("칸") or []) if isinstance(c, dict) and _게.요청금액(c)}
    덱배율 = _v2덱배율(doc, 밀도)                 # 부품마다 덱에서 한 채움 배율(bench14 ③ — 장마다 글자 크기가 갈리지 않게)
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict):
            continue
        쪽 += 1
        유형 = 속성값.열거(장.get("유형"), _V2유형, f"장.{i}.유형", 기본="자유")
        목적 = "설득" if 유형 == "요청" else 덱목적
        장밀도 = 속성값.열거(장.get("밀도"), tuple(_V2밀도), f"장.{i}.밀도", 기본="")
        밀틀 = f" {_V2밀도[장밀도]}" if 장밀도 else ""
        머리말 = f'data-ent="슬라이드" data-slide-idx="{i}" data-layout="{e(유형)}"'
        노트 = _v2노트(장, i)
        if 유형 == "표지":
            parts.append(f'<section class="sl-page is-cover v2-표지" {머리말}>{_v2표지(doc, 장, i)}{노트}</section>\n')
            continue
        if 유형 == "간지":
            간 = 장.get("간지") if isinstance(장.get("간지"), dict) else {}
            번 = (f'<span class="divider__no tx" data-path="장.{i}.간지.번호">{e(str(간["번호"]))}</span>' if 간.get("번호")
                 else f'<span class="divider__no" data-derived="1">{e(_v2쪽(sum(1 for s in 장들[:i + 1] if s.get("유형") == "간지")))}</span>')
            목록 = "".join(f'<span class="tx" data-ent="항목" data-path="{e(f"장.{i}.간지.목록.{j}")}">{e(str(t))}</span>'
                         for j, t in enumerate(간.get("목록") or []) if isinstance(t, str))
            parts.append(f'<section class="sl-page is-divider v2-간지" {머리말}><div class="cover__top" data-derived="1">{e(str(doc.get("제목") or ""))}</div>'
                         f'<div class="cover__main">{번}<h2 class="cover__title"><span class="tx" data-path="장.{i}.간지.제목">{e(str(간.get("제목", "")))}</span></h2>'
                         + (f'<div class="divider__list">{목록}</div>' if 목록 else "")
                         + f'</div><div class="cover__bottom"><span></span><span data-derived="1">{e(_v2쪽(쪽))}</span></div>{노트}</section>\n')
            continue
        if 유형 == "마무리":
            마 = 장.get("마무리") if isinstance(장.get("마무리"), dict) else {}
            문의 = 마.get("문의") if isinstance(마.get("문의"), dict) else {}
            문의글 = ""
            if 문의:
                문의글 = ('<div class="closing__ask"><span class="b" data-derived="1">문의</span>'
                        f'<span class="tx" data-path="장.{i}.마무리.문의.부서">{e(str(문의.get("부서", "")))}</span>'
                        + (f'<span class="tx" data-path="장.{i}.마무리.문의.연락처">{e(str(문의["연락처"]))}</span>' if 문의.get("연락처") else "")
                        + "</div>")
            parts.append(f'<section class="sl-page is-closing v2-마무리" {머리말}><div class="cover__top" data-derived="1">{e(문서명)}</div>'
                         f'<div class="cover__main"><h2 class="cover__title">{_v2글(마.get("문구"), f"장.{i}.마무리.문구", 목적)}</h2>'
                         + (f'<p class="cover__sub tx" data-path="장.{i}.마무리.부문구">{e(str(마["부문구"]))}</p>' if 마.get("부문구") else "")
                         + f'</div><div class="cover__bottom">{문의글 or "<span></span>"}<span data-derived="1">{e(_v2쪽(쪽))}</span></div>{노트}</section>\n')
            continue
        if 유형 == "목차":
            목 = 장.get("목차") if isinstance(장.get("목차"), dict) else {}
            줄 = "".join(f'<div class="toc__i" data-ent="항목"><span class="toc__no" data-derived="1">{순 + 1}</span>'
                        f'<span class="tx" data-path="{e(f"장.{i}.목차.항목.{j}")}">{e(str(t))}</span></div>'
                        for 순, (j, t) in enumerate((j, t) for j, t in enumerate(목.get("항목") or []) if isinstance(t, str)))
            parts.append(f'<section class="sl-page v2-목차{밀틀}" {머리말}><header class="sl-head" data-ent="머리">'
                         f'<div class="sl-head__txt"><span class="sl-head__msg" data-derived="1">목차</span></div></header>'
                         f'<div class="sl-body rows-1"><div class="v2-cell c-10 off-1"><div class="toc">{줄}</div></div></div>'
                         f'{_v2꼬리(장, i, 쪽, 문서명, [])}{노트}</section>\n')
            continue
        # ── 본문 장 ──
        if 장.get("머리"):
            번호 = 목차번호.get(i, 0) if 목차번호 is not None else 번호 + 1
        진한장 = 유형 == "인용" and all(isinstance(c, dict) and c.get("변형", "진하게") == "진하게"
                                    for c in 장.get("칸") or [] if isinstance(c, dict) and c.get("부품") == "인용")
        자동 = []
        가용 = _v2가용(장, 프리셋)
        본 = _v2본문(장, i, 목적, 가용, 자동, 요청값, 장밀도 or 밀도, 덱배율)
        노트 = _v2노트(장, i, 자동)                 # 조립기가 계산한 값은 본문을 그린 뒤에야 안다
        parts.append(f'<section class="sl-page v2-{e(유형)}{" is-dark" if 진한장 else ""}{밀틀}" {머리말}>'
                     f'{_v2머리(장, i, 번호 if 장.get("머리") else 0, 목적, 머리진함 and not 진한장)}'
                     f'{_v2리드(장, i, 목적)}{본}{_v2요지띠(장, i, 목적, 요지진함)}'
                     f'{_v2꼬리(장, i, 쪽, 문서명, 자동)}{노트}</section>\n')
    parts.append("""</main>
<script src="../jachigan.js?v="></script>
""" + _V2배율안전망 + """<script src="../audit.js?v="></script>
<script src="../present.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


# 채움 배율 안전망(round3 적대 검토 H1) — 조립기는 렌더를 못 보고 어림으로 --fz 를 고른다. 키운 칸(.is-z)이 든 장이
# 브라우저에서 넘치면(audit.js 넘침과 같은 자: 장·본문·칸·칸 속 부품·세로묶음 칸의 세로 넘침, 키운 칸 글의 가로 넘침)
# 그 장의 --fz(·알약 --fzp)를 0.05씩 내린다. 1까지 내려도 넘침이 그대로면 키운 탓이 아니라서 원래 배율로 되돌린다.
# 매번 조립기가 준 배율에서 다시 잰다(글꼴이 앉기 전 대체 글꼴로 잰 값이 쌓이지 않게) — PDF·PPTX 수확·audit 가
# 같은 DOM 을 보므로 함께 맞는다. audit.js 보다 먼저 실린다(load 듣개 차례).
_V2배율안전망 = """<script>(function () {
  var 원 = new Map();
  function 세로(p) {
    var o = p.scrollHeight - p.clientHeight;
    p.querySelectorAll('.sl-body, .v2-cell, .v2-cell > *, .v2-stack > *').forEach(function (el) {
      o = Math.max(o, el.scrollHeight - el.clientHeight);
    });
    p.querySelectorAll('.v2-cell.is-z .tx').forEach(function (el) {
      var 칸 = el.closest('.v2-cell'), rg = document.createRange();
      rg.selectNodeContents(el);
      var q = rg.getBoundingClientRect(), c = 칸.getBoundingClientRect();
      if (q.width >= 1) o = Math.max(o, c.left - q.left, q.right - c.right);
    });
    return o;
  }
  function 두기(c, z) {
    var zp = Math.min(z, 원.get(c)[1]);
    c.style.setProperty('--fz', String(z));
    c.style.setProperty('--fzp', String(zp));
  }
  function 맞춤() {
    document.querySelectorAll('.deck.v2 .sl-page').forEach(function (p) {
      var 칸 = [].slice.call(p.querySelectorAll('.v2-cell.is-z'));
      if (!칸.length) return;
      칸.forEach(function (c) {
        if (!원.has(c)) 원.set(c, [parseFloat(c.style.getPropertyValue('--fz')) || 1, parseFloat(c.style.getPropertyValue('--fzp')) || 1]);
        두기(c, 원.get(c)[0]);
      });
      var 처음 = 세로(p);
      if (처음 <= 4) return;
      for (var k = 0; k < 14 && 세로(p) > 4; k++) {
        var 줄임 = false;
        칸.forEach(function (c) {
          var z = parseFloat(c.style.getPropertyValue('--fz')) || 1;
          if (z > 1.001) { 두기(c, Math.max(1, Math.round((z - 0.05) * 100) / 100)); 줄임 = true; }
        });
        if (!줄임) break;
      }
      if (세로(p) > 4 && 세로(p) >= 처음 - 1) 칸.forEach(function (c) { 두기(c, 원.get(c)[0]); });
    });
  }
  function run() {
    맞춤();
    if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(맞춤);
  }
  if (document.readyState === 'complete') run(); else window.addEventListener('load', run);
})();
</script>
"""


_v2섹션re = re.compile(r'<section class="sl-page[^"]*"[^>]*data-slide-idx="(?P<i>\d+)"[^>]*data-layout="(?P<lo>[^"]*)"[^>]*>(?P<body>.*?)</section>', re.S)


def _v2렌더빈장(html_):
    """렌더된 v2 HTML 에서 본문(.sl-body)이 글자·그림 하나 없이 빈 장 — (색인, 유형) 목록.
    머리·꼬리말·노트는 내용으로 치지 않는다(헤드만 있는 백지 장을 막는다)."""
    빈 = []
    for m in _v2섹션re.finditer(html_):
        sec = m.group("body")
        if 'class="sl-body' not in sec:
            continue
        sec = re.sub(r'<header class="sl-head.*?</header>', "", sec, flags=re.S)
        sec = re.sub(r'<footer class="sl-foot.*?</footer>', "", sec, flags=re.S)
        sec = re.sub(r'<aside class="sl-notes.*?</aside>', "", sec, flags=re.S)
        sec = re.sub(r'<div class="sl-take.*?</div></div>', "", sec, flags=re.S)
        sec = re.sub(r'<div class="sl-lead.*?</div>', "", sec, flags=re.S)
        if "<polyline" in sec or "ring-val" in sec or "<img" in sec:
            continue                                    # 선·링 그림은 내용이다(글이 없어도)
        sec = re.sub(r"<svg.*?</svg>", "", sec, flags=re.S)   # 아이콘만으로는 내용이 아니다
        if _태그re.sub("", sec).replace("&#160;", "").strip():
            continue
        빈.append((int(m.group("i")), m.group("lo")))
    return 빈


def _v2줄넘침(doc):
    """폭 없는 본문 장이 기본 배치로 3줄 이상이 되나 — [(장 색인, 유형, 칸 수, 줄 수)].
    폭을 적은 장은 게이트(slides_v2_gate '2줄까지')가 본다. '26-09-28 적대 검토(렌더 H1): 예전엔
    배치가 넘치는 칸을 말없이 버렸다 — 이제 버리지 않고, 담을 수 없으면 여기서 되돌린다."""
    out = []
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict) or 장.get("유형") in ("표지", "목차", "간지", "마무리"):
            continue
        칸 = [c for c in 장.get("칸") or [] if isinstance(c, dict)]
        if not 칸 or all(_v2폭(c) for c in 칸):
            continue
        줄들 = _v2배치(장.get("유형"), 칸)
        if len(줄들) > 2:
            out.append((i, 장.get("유형"), len(칸), len(줄들)))
    return out


def _v2한건(doc, 이름, 로그, 저장=False):
    """판형 v2 문서 한 건 — 게이트(스키마·의미) → 조립 → 렌더 본체 백지 검사. 실패면 None.

    `저장`(등록된 문서의 저장 뒤 재조립) — 스키마는 맞는데 의미 규칙(hard)에만 걸리면 소프트로 낮춰
    그린다('26-09-28 적대 검토 ⑤: 규칙이 늘거나 soft→hard 로 오르면 옛 문서가 편집 불능이 됐다). 새로
    생긴 위반은 저장 전에 workspace/apply_edit_any.py 가 막는다. 새 초안(저장=False)은 그대로 막는다."""
    import slides_v2_gate
    try:
        import 슬라이드v2
        판오 = 슬라이드v2.판형오류(doc)
        if 판오:                              # 판형 오타가 스키마 오류 수십 줄에 묻히지 않게 첫 줄로
            로그.append(f"[게이트 위반] {이름}")
            로그.append(f"  ✗ {판오}")
            return None
        hard, soft = slides_v2_gate.검사(doc)
        낮춤 = []
        if hard and 저장 and not slides_v2_gate.스키마검사(doc):
            낮춤, hard = hard, []
        if hard:
            로그.append(f"[게이트 위반] {이름}")
            for b in hard[:40]:
                로그.append(f"  ✗ {b}")
            if len(hard) > 40:
                로그.append(f"  ✗ … 외 {len(hard) - 40}건")
            return None
        넘친줄 = _v2줄넘침(doc)
        if 넘친줄 and 저장:
            낮춤 += [f"장.{번호}({유형}): 폭 없는 칸 {n}개가 기본 배치로 {줄수}줄" for 번호, 유형, n, 줄수 in 넘친줄]
            넘친줄 = []
        if 넘친줄:
            로그.append(f"[게이트 위반] {이름}")
            for 번호, 유형, n, 줄수 in 넘친줄:
                로그.append(f"  ✗ 장.{번호}({유형}): 폭 없는 칸 {n}개가 기본 배치로 {줄수}줄이 된다(2줄까지) — "
                           "칸을 줄이거나(같은 종류 부품은 하나로 합친다) 장을 나눠라")
            return None
        html_ = genres.판찍기(build_v2(doc))
        빈장 = _v2렌더빈장(html_)
        if 빈장:
            로그.append(f"[게이트 위반] {이름}")
            for 번호, lo in 빈장:
                로그.append(f"  ✗ 장.{번호}({lo}): 렌더된 본문이 비어 있다 — 칸의 부품 슬롯(부품 이름·필수 슬롯)을 채워라")
            return None
        # 그린 값 = 적힌 값('26-09-29 bench11 — 도넛 64% 를 39% 로 그림): 차트 기하를 되읽어 1% 넘게 어긋나면 막는다
        어긋 = slides_v2_gate.차트되읽기(html_)
        if 어긋 and 저장:
            낮춤 += [f"{쪽}번 장 {부품}: 그린 값이 적힌 값과 다르다 — {말}" for 쪽, 부품, _, 말 in 어긋]
            어긋 = []
        if 어긋:
            로그.append(f"[게이트 위반] {이름}")
            for 쪽, 부품, _, 말 in 어긋:
                로그.append(f"  ✗ {쪽}번 장 {부품}: 그린 값이 적힌 값과 다르다 — {말} "
                           "(값·표시·축 최소/최대가 서로 맞는지 보라)")
            return None
        if soft or 낮춤:
            로그.append(f"[소프트 경고] {이름}")
            for w in soft:
                로그.append(f"  ! {w}")
            for w in 낮춤:
                로그.append(f"  · (저장이라 하드에서 낮춤) {w}")
        지 = slides_v2_gate.지표(doc)
        로그.append(f"[슬라이드 지표] 판형 v2 · 장 {지['장']} · 종류 {지['종류']} · 최대연속 {지['최대연속']}"
                   f" · 목적 {doc.get('목적')} · 프리셋 {doc.get('프리셋') or 'data'}")
        return html_
    except Exception:
        로그.append(f"[조립 오류] {이름}")
        로그.append("  ✗ 이 부품 트리를 렌더하지 못했다 — 장.칸 의 부품 이름·슬롯 모양을 schema 대로 채워라")
        import traceback as _tb
        sys.stderr.write(f"[조립 오류] {이름}: {_tb.format_exc()}\n")
        return None


_섹션re = re.compile(r'<section class="sl-page sl-(?P<lo>[^" ]+)"[^>]*data-slide-idx="(?P<i>\d+)"[^>]*>(?P<body>.*?)</section>', re.S)
_태그re = re.compile(r'<[^>]+>')


def _렌더본체빈장(html):
    """렌더된 HTML 에서 본체(.sl-body)가 글자·이미지·svg 하나 없이 빈 장의 (인덱스, 레이아웃) 목록.
    표지(cover)는 본체가 없어 대상 밖. 자유배치(sl-free) 장은 본체가 여러 상자라 첫 상자만 보지 않고
    섹션 전체에서 헤드·쪽번호를 뺀 나머지를 본다."""
    빈 = []
    for m in _섹션re.finditer(html):
        lo, 번호, sec = m.group("lo"), int(m.group("i")), m.group("body")   # 이름 i 는 속성잠금 검사가 enumerate 인덱스로만 쓰길 요구한다
        sec = re.sub(r'<h2 class="sl-head[^"]*".*?</h2>', "", sec, flags=re.S)
        sec = re.sub(r'<div class="sl-num".*?</div>', "", sec, flags=re.S)
        sec = re.sub(r'<div class="sl-src".*?</div>', "", sec, flags=re.S)     # 출처 줄만으로는 내용이 아니다
        if "<img" in sec or "<svg" in sec or "data-fig=" in sec:   # 도식은 svgfig.js 가 브라우저에서 data-fig 로 그린다
            continue
        if _태그re.sub("", sec).strip():
            continue
        빈.append((번호, lo))
    return 빈


def 조립하기(등록부경로, only=None, out=None, 저장=False):
    """슬라이드 등록부 → HTML. 직접 호출·subprocess 공용 몸통(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [...], "로그": …}. 게이트 위반 문서는 안 쓰고
    ok=False. 산출물뿌리는 호출마다 다시 푼다(세션 오염 방지).

    `저장`(기본 False) — True 면 차트 빈값류 하드 위반(_차트게이트_연성가능)을 소프트
    경고로 낮춘다('26-09-27, 회귀 근거: e2e_slides.py). 예전엔 이 라운드 전에 만든
    (빈 차트가 든) 덱이라도 다른 장을 고쳐 저장하면 매번 하드 게이트에 막혀 저장·이어
    받기 자체가 안 됐다 — 새 초안(새문서)에서는 여전히 하드로 막되(저장=False 기본값),
    이미 등록된 문서를 저장(재조립)할 때는 무관한 편집까지 막지 않는다."""
    낼곳 = out if out else 자료뿌리.산출물뿌리()
    os.makedirs(낼곳, exist_ok=True)
    docs = json.load(open(등록부경로, encoding="utf-8"))
    docs = genres.한건만(docs, ["--only", only] if only else [])
    fail = 0
    낸것, 로그 = [], []
    for doc in docs:
        이름 = (doc.get("filename") if isinstance(doc, dict) else None) or "?"
        if _v2문서인가(doc):
            # 판형 v2(부품 트리) — 옛 정규화·게이트(레이아웃 13종)를 타지 않는다. 게이트는
            # slides_v2_gate(스키마 + 의미 규칙), 렌더 뒤 본문 백지 검사는 _v2렌더빈장.
            # 쪽수 = 장수·장별 넘침은 옛 문서와 같은 렌더 게이트(render_verify.sh·audit.js)가 잰다.
            html = _v2한건(doc, 이름, 로그, 저장=저장)
            if html is None:
                fail = 1
                continue
            with 자료뿌리.쓰기(os.path.join(낼곳, f"{이름}.html")) as f:
                f.write(html)
            낸것.append(f"{이름}.html")
            로그.append(f"built: {이름}.html")
            continue
        # per-doc 전체를 감싼다 — 정규화·게이트·렌더 어디서 예외가 나든 그대로 올리면 조립 전체가
        # serve.py 의 "처리하다 오류"로 하드스톱되어 자가수정이 멈춘다(실측 2026-09-02: EXAONE 가
        # 표 row 를 리스트 아닌 값으로 내 _표 렌더가 죽었다). 여기서 **재시도 가능한 위반**으로 바꾼다.
        try:
            _표정규화(doc)
            정규화경고 = _레이아웃정규화(doc)
            _도식타입정규화(doc)
            _큰숫자정규화(doc)
            정규화경고 += _픽토그램정규화(doc)
            # r10 사후검토 발견(low, 중복 접수 2건) — 정규화·강등 안내를 "  ! " 로 남겼었는데
            # app.html 의 소프트 재시도 정규식(/^\s*!\s.+$/gm)이 진짜 품질 경고(_소프트지표,
            # 아래)와 이 안내를 구분 못 해 이름표만 고친 정상 덱까지 EXAONE 을 한 번 더
            # 불렀다(안내 자체는 '해소'할 거리가 없는데도). 줄 머리표만 "  · "(가운뎃점)로
            # 바꿔 그 정규식엔 안 걸리되, "[소프트 경고]" 절 이름은 그대로 둔다 — r9_asm9.py
            # (gemma_s6.저장모드_소프트경고 등)가 이 절 이름으로 이미 저장모드 강등을 확인하고
            # 있어(회귀 시험 소유 다른 라운드), 절 이름까지 바꾸면 그쪽이 깨진다. 실제 품질
            # 경고(아래 "경고", _소프트지표)는 여전히 "  ! "를 쓴다 — 그건 정말 다시 써서
            # 해소할 거리라 되시도가 맞다.
            연성 = []
            bad = gate_check(doc)
            if 저장 and bad:
                # 차트 빈값 위반만 소프트로 내린다 — 그 밖의 위반(제목 없음 등)은 저장
                # 때도 그대로 하드다(무관한 편집을 핑계로 다른 결함까지 눈감지 않는다).
                연성 = [b for b in bad if "(도식): " in b
                       and any(마 in b for 마 in _차트게이트_연성가능)]
                if 연성:
                    bad = [b for b in bad if b not in 연성]

            def _정규화안내찍기():
                # r10 사후검토 발견(low) — 하드 위반이 나는 세 갈래(gate_check·글머리만
                # 하드·렌더본체빔) 모두 이 안내를 **뒤에** 남긴다. 앞에 두면 app.html 의
                # 700자 되먹임·160자 화면표시(둘 다 로그 **앞부분**만 자른다)가 안내로
                # 다 차서 정작 막힌 이유가 잘렸다(실측: 216번째 글자에 있던 하드 사유가
                # 160자 밖으로 밀렸다). 정규화 자체는 여전히 렌더 전에 실행한다(문서를
                # 실제로 고치는 일과 그걸 알리는 순서는 다르다).
                if 정규화경고 or 연성:
                    로그.append(f"[소프트 경고] {이름}")
                    for w in 정규화경고:
                        로그.append(f"  · {w}")
                    for w in 연성:
                        로그.append(f"  · (저장이라 하드에서 낮춤) {w}")

            if bad:
                fail = 1
                로그.append(f"[게이트 위반] {이름}")
                for b in bad:
                    로그.append(f"  ✗ {b}")
                _정규화안내찍기()
                continue
            # 소프트 게이트 — 위반해도 덱은 그대로 낸다(하드와 다르다). 경고 + 지표 요약을
            # 로그 맨끝에 항상 남겨 다음 자가수정 턴이 곧바로 읽게 한다.
            경고, 지표 = _소프트지표(doc)
            if 지표["글머리만"] > 0.50:
                # 실측 보정 2026-09-07: 실물 부처 덱은 글자만 장이 0.00 — 덱 절반이 글자만이면 hard
                fail = 1
                로그.append(f"[게이트 위반] {이름}")
                로그.append(f"  ✗ 글머리만 장 비율 {지표['글머리만']:.2f} — 0.50 초과(hard). 장마다 도식·표·큰숫자·픽토그램 중 하나를 넣어라")
                _정규화안내찍기()
                continue
            html = genres.판찍기(build(doc))
            # 렌더 결과 기준 백지 검사 — JSON 단계 게이트(_텍스트있나·큰숫자 지표)는 "그 키를 읽는지"까지는
            # 못 본다. 모델이 정본 키 대신 다른 이름에 내용을 넣으면 원본엔 글자가 있어도 화면은 빈다
            # (실측 2026-09-06 라이브 덱: 큰숫자 지표를 "큰숫자" 키로 → 헤드만 남은 백지 5장, 심사 2.33).
            # 그래서 렌더된 본체(.sl-body)에 글자도 이미지도 svg 도 없으면 하드 위반으로 되돌린다.
            빈장 = _렌더본체빈장(html)
            if 빈장:
                fail = 1
                로그.append(f"[게이트 위반] {이름}")
                for 번호, lo in 빈장:
                    로그.append(f"  ✗ 슬라이드.{번호}({lo}): 렌더된 본체가 비어 있다 — 그 레이아웃의 정본 키"
                               f"(본문·마무리=항목, 큰숫자=지표, 표=표, 도식=도식, 비교=좌·우, 매트릭스=사분면,"
                               f" 타임라인=단계, 픽토그램=픽토그램, 인용=인용문)에 내용을 넣어라. 다른 키 이름은 그리지 못한다")
                _정규화안내찍기()
                continue
            _정규화안내찍기()
            if 경고:
                로그.append(f"[소프트 경고] {이름}")
                for w in 경고:
                    로그.append(f"  ! {w}")
            로그.append(f"[슬라이드 지표] 글머리만 {지표['글머리만']:.2f} · 종류 {지표['종류']} · "
                       f"최대연속 {지표['최대연속']} · 시각/장 {지표['시각당장']:.2f} · 백지 {지표['백지']}"
                       f" · 목적 {_목적(doc)}")
        except Exception:
            fail = 1
            로그.append(f"[조립 오류] {이름}")
            로그.append("  ✗ 이 구조를 렌더하지 못했다 — 표는 header·rows 를 이중배열(행마다 셀 목록)로, "
                       "도식은 유형에 맞는 스펙으로, 픽토그램은 {아이콘,라벨} 객체 목록으로 채워라")
            import traceback as _tb
            sys.stderr.write(f"[조립 오류] {이름}: {_tb.format_exc()}\n")
            continue
        with 자료뿌리.쓰기(os.path.join(낼곳, f"{이름}.html")) as f:
            f.write(html)
        낸것.append(f"{이름}.html")
        로그.append(f"built: {이름}.html")
    return {"ok": fail == 0, "낸것": 낸것, "로그": "\n".join(로그)}


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    본 = 조립하기(argv[0], only=only, out=out, 저장=("--저장" in sys.argv))
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
