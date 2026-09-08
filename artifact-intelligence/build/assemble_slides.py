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
    배포 트리엔 온톨로지가 없을 수 있어(정책만-로컬) None 을 돌려줄 수 있다 — 그땐 아래 폴백."""
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
레이아웃별칭 = {
    "본체": "본문", "본론": "본문",
    "compare": "비교", "two-cols": "비교", "comparison": "비교",
    "kpi": "큰숫자", "bignumber": "큰숫자", "fact": "큰숫자", "statement": "큰숫자",
    "matrix": "매트릭스", "2x2": "매트릭스", "quadrant": "매트릭스",
    "quote": "인용", "testimonial": "인용",
    "timeline": "타임라인", "roadmap": "타임라인",
    "chart": "도식",
}
# 도식 type 유의어 → svgfig 정본 이름(차트 4종 도입, '26-09-06). 게이트·렌더 모두 이 뒤에 온다.
도식유형별칭 = {"bar_chart": "bar", "column": "bar", "line_chart": "line",
             "pie": "donut", "doughnut": "donut"}
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


def _레이아웃정규화(doc):
    """모델이 레이아웃 이름을 정본 유의어로 흘리는 흔한 이탈(본체→본문)을 정본 이름으로 옮긴다 —
    _표정규화와 같은 자리·같은 취지(게이트에 통째로 걸리는 것보다 낫다). 별칭표 밖 미지 이름은
    안 건드린다(그건 게이트가 '모르는 이름'으로 잡는다). 실측 2026-09-02 스윕: '본체' 가
    입력 여럿에서 반복돼 5회 자가수정을 낭비했다."""
    for s in (doc.get("슬라이드") or []):
        if isinstance(s, dict) and s.get("레이아웃") in 레이아웃별칭:
            s["레이아웃"] = 레이아웃별칭[s["레이아웃"]]
    return doc


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
                bad.append(f"슬라이드.{i}(인용): 출처가 없다 — 인용은 출처가 필수다")
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
            미상 = [_객체(p).get("아이콘") for p in ps if not pictogram.has(_객체(p).get("아이콘", ""))]
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
    _s = lambda x: "" if x is None else str(x)
    hdr = tb.get("header")
    hdr = hdr if isinstance(hdr, list) else ([] if hdr is None else [hdr])
    rows = "<tr>" + "".join(f"<th>{e(_s(h))}</th>" for h in hdr) + "</tr>"
    for row in (tb.get("rows") or []):
        cells = row if isinstance(row, list) else (list(row.values()) if isinstance(row, dict) else [row])
        rows += "<tr>" + "".join(f"<td>{e(_s(c))}</td>" for c in cells) + "</tr>"
    return (f'      <div class="sl-table-wrap" data-ent="표"{_정렬속성(tb)} data-path="{e(base)}">'
            f'{cap}<table class="sl-table">{rows}</table></div>\n')


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
              "relation": "노드", "strategy": "전략"}


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
    return [s for s in out if s.strip()]


def _도식(fg, base, e):
    """SVG 도식 — 풀버전과 같은 svgfig(.fr-fig) 재사용. jachigan.js 가 그린다."""
    fg = _도식정규화(fg or {})
    크기 = (fg or {}).get("크기")
    크기attr = f' data-크기="{e(str(크기))}"' if 크기 in ("크게", "가득") else ""
    return "      " + svgfig.render(fg).replace(
        'class="blk fr-fig"',
        f'class="blk fr-fig sl-fig"{크기attr} data-path="{e(base)}"', 1)


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
        # data-layout(신설 '26-09-06) — audit.js 가 이 속성으로 장별 레이아웃 다양성·연속을 잰다.
        parts.append(f'<section class="sl-page sl-{e(lo)}'
                     f'{" sl-free" if 자유 else ""}" data-ent="슬라이드" '
                     f'data-layout="{e(lo)}" data-slide-idx="{i}">\n')
        if lo == "어젠다":
            parts.append('      <h2 class="sl-head sl-head-plain">목차</h2>\n')
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
        이름 = (doc.get("filename") if isinstance(doc, dict) else None) or "?"
        # per-doc 전체를 감싼다 — 정규화·게이트·렌더 어디서 예외가 나든 그대로 올리면 조립 전체가
        # serve.py 의 "처리하다 오류"로 하드스톱되어 자가수정이 멈춘다(실측 2026-09-02: EXAONE 가
        # 표 row 를 리스트 아닌 값으로 내 _표 렌더가 죽었다). 여기서 **재시도 가능한 위반**으로 바꾼다.
        try:
            _표정규화(doc)
            _레이아웃정규화(doc)
            _도식타입정규화(doc)
            _큰숫자정규화(doc)
            bad = gate_check(doc)
            if bad:
                fail = 1
                로그.append(f"[게이트 위반] {이름}")
                for b in bad:
                    로그.append(f"  ✗ {b}")
                continue
            # 소프트 게이트 — 위반해도 덱은 그대로 낸다(하드와 다르다). 경고 + 지표 요약을
            # 로그 맨끝에 항상 남겨 다음 자가수정 턴이 곧바로 읽게 한다.
            경고, 지표 = _소프트지표(doc)
            if 지표["글머리만"] > 0.50:
                # 실측 보정 2026-09-07: 실물 부처 덱은 글자만 장이 0.00 — 덱 절반이 글자만이면 hard
                fail = 1
                로그.append(f"[게이트 위반] {이름}")
                로그.append(f"  ✗ 글머리만 장 비율 {지표['글머리만']:.2f} — 0.50 초과(hard). 장마다 도식·표·큰숫자·픽토그램 중 하나를 넣어라")
                continue
            if 경고:
                로그.append(f"[소프트 경고] {이름}")
                for w in 경고:
                    로그.append(f"  ! {w}")
            로그.append(f"[슬라이드 지표] 글머리만 {지표['글머리만']:.2f} · 종류 {지표['종류']} · "
                       f"최대연속 {지표['최대연속']} · 시각/장 {지표['시각당장']:.2f} · 백지 {지표['백지']}"
                       f" · 목적 {_목적(doc)}")
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
                continue
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
    본 = 조립하기(argv[0], only=only, out=out)
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
