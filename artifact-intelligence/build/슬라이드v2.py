#!/usr/bin/env python3
"""슬라이드 v2(부품 트리) — 판형 판별 · 문서 단계 soft 게이트(신설 지표) · 지시문 조각.

정본 규칙: ontology document_types.slides 의 `*_v2` 키('26-09-28 사장님 판정 — 데이터형 부품이
기본, 브리핑형·키노트형은 프리셋, 모델은 부품 트리 JSON 만 쓰고 조립기가 그린다).

누가 무엇을 재나 — 게이트가 둘로 갈리지 않게 한 곳씩만 둔다
  · 스키마 + 조립 게이트(hard·기본 soft): build/slides_v2_gate.py (모양 = build/slides_v2.schema.json).
    조립기(build/assemble_slides.py `_v2한건`)가 부르는 그 게이트를 여기서도 **그대로** 부른다 —
    새문서가 등록 전에 막는 것과 조립이 막는 것이 같다.
  · 이 파일: '26-09-28 신설 지표 가운데 문서(JSON) 단계에서 잴 수 있는 것을 soft 로 **더한다**
    (타임라인 순서·모호 시점, 맥락 없는 큰숫자, 차트 강조 계열 1, 선차트 반복, 마무리 요청 되풀이,
    표지 태그 중복). 문체검사(build/stylelint.py doc_level_checks)가 이 soft 를 싣는다 — 옛 문서
    (판형 없음)에도 걸 수 있는 셋(타임라인 순서·막대 2개·맥락 없는 큰숫자)은 옛덱소프트 로.
  · 렌더 뒤 지표(판 채움·크기 대비·글자 대비·캡션 12pt): build/audit.js AUDIT_SPEC.slides →
    build/render_verify.sh 가 경고로 찍는다(조판게이트).
  신설 지표는 전부 soft 로 시작한다(실측 보정 뒤 hard 승격 — 온톨로지 slides.게이트._v2_승격).

옛 문서와의 공존(ontology slides.판형): 최상위 "판형" 이 "v2" 면 v2, 키가 없으면 옛 경로. 판형 없이
"장" 배열만 있고 "슬라이드" 가 없으면 판형을 빠뜨린 v2 로 보고 거부한다(옛 게이트의 "표지.제목이
없다" 같은 헛갈리는 말 대신 — 새문서가 이 판정을 먼저 한다).

사용: python3 build/슬라이드v2.py 문서.json [--약한모델]   (hard 가 있으면 종료 코드 1)
"""
import copy
import json
import os
import re
import sys

여기 = os.path.dirname(os.path.abspath(__file__))
if 여기 not in sys.path:
    sys.path.insert(0, 여기)
본보기길 = os.path.join(여기, "slides_v2_example.json")

_캐시 = {}


def 게이트():
    """조립 게이트 모듈(build/slides_v2_gate.py) — 스키마 검사·hard 규칙의 유일한 자리."""
    if "게이트" not in _캐시:
        import importlib
        _캐시["게이트"] = importlib.import_module("slides_v2_gate")
    return _캐시["게이트"]


def 스키마():
    return 게이트().스키마()


def 본보기():
    if "본보기" not in _캐시:
        with open(본보기길, encoding="utf-8") as f:
            _캐시["본보기"] = json.load(f)
    return _캐시["본보기"]


def 부품메타():
    """부품 이름 → 스키마 정의(x-* 메타 포함)."""
    return {k[3:]: v for k, v in 스키마()["$defs"].items() if k.startswith("부품_")}


def 약한모델부분집합():
    x = 스키마().get("x-약한모델") or {}
    return {"유형": list(x.get("유형") or []), "부품": list(x.get("부품") or []),
            "쓰지않는슬롯": list(x.get("쓰지않는슬롯") or [])}


def 유형들():
    return list(스키마()["$defs"]["장"]["properties"]["유형"]["enum"])


def 아이콘들():
    return list(스키마()["$defs"]["부품_카드"]["properties"]["아이콘"]["enum"])


def 상태들():
    return list(스키마()["$defs"]["부품_카드"]["properties"]["상태"]["enum"])


# ── 판형 판별 ────────────────────────────────────────────────────────────


def v2인가(doc):
    """v2 경로로 보낼 문서인가 — 판형 키가 있거나(값이 틀려도 여기서 거부하려고), 판형 없이
    v2 모양(장 배열, 슬라이드 없음)이면 참."""
    if not isinstance(doc, dict):
        return False
    if "판형" in doc:
        return True
    return isinstance(doc.get("장"), list) and "슬라이드" not in doc


def 판형오류(doc):
    if not isinstance(doc, dict):
        return "문서가 객체가 아니다"
    if "판형" not in doc:
        if isinstance(doc.get("장"), list) and "슬라이드" not in doc:
            return ("판형 키가 없다 — 부품 트리(장 배열) 문서면 최상위에 \"판형\":\"v2\" 를 넣어라"
                    "(판형이 없으면 옛 레이아웃 문서로 읽어 표지·슬라이드를 찾는다)")
        return None
    if doc["판형"] != "v2":
        return f"판형 {doc['판형']!r} — 아는 판형은 \"v2\" 하나다(키를 빼면 옛 레이아웃 문서)"
    return None


# ── 신설 soft(문서 단계) ───────────────────────────────────────────────────

_모호시점 = ("상반기", "하반기", "연중", "내내", "상시", "수시", "연간", "매월", "매년", "계속", "지속")
_요청신호 = ("요청", "승인", "건의", "의결", "재가", "협조")


def 글자(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(r.get("t", "") for r in v if isinstance(r, dict))
    return ""


def 칸들(장):
    """(경로, 부품) — 세로묶음 안까지 한 겹 편다."""
    for k, c in enumerate(장.get("칸") or []):
        if not isinstance(c, dict):
            continue
        if c.get("부품") == "세로묶음":
            for m, cc in enumerate(c.get("칸") or []):
                if isinstance(cc, dict):
                    yield f"칸.{k}.칸.{m}", cc
        else:
            yield f"칸.{k}", c


def _시점키(s):
    """타임라인 시점 → (연도|None, 달 수). 못 읽으면 None. '하반기'=7월, '연말'=12.5, '연초'=0.5."""
    t = str(s or "").strip()
    if not t:
        return None
    연 = None
    m = re.search(r"'(\d{2})(?:년|\.)?", t) or re.search(r"(20\d{2})\s*년?", t)
    if m:
        y = int(m.group(1))
        연 = y + 2000 if y < 100 else y
    달 = None
    m = re.search(r"([1-4])\s*분기", t)
    if m:
        달 = (int(m.group(1)) - 1) * 3 + 1
    m2 = re.search(r"(\d{1,2})\s*월", t) or re.search(r"'\d{2}\.\s*(\d{1,2})\.", t)
    if 달 is None and m2:
        달 = int(m2.group(1))
    if 달 is None:
        if "상반기" in t:
            달 = 1
        elif "연초" in t:
            달 = 0.5
        elif "하반기" in t:
            달 = 7
        elif "연말" in t:
            달 = 12.5
    if 달 is None and 연 is None:
        return None
    return (연, 달 if 달 is not None else 0)


def 시점역행(시점들):
    """앞보다 이른 시점이 뒤에 온 자리들 [(앞, 뒤)]. 연도가 빠진 시점은 앞 연도를 이어받는다."""
    역행, 앞키, 앞글, 연맥 = [], None, None, None
    for s in 시점들:
        k = _시점키(s)
        if k is None:
            continue
        if k[0] is not None:
            연맥 = k[0]
        키 = (k[0] if k[0] is not None else (연맥 or 0), k[1])
        if 앞키 is not None and 키 < 앞키:
            역행.append((앞글, s))
        앞키, 앞글 = 키, s
    return 역행


# ── 출처 일반 말·짝 잇기·브리핑 프리셋·판 아래 빔('26-09-30 bench14 주관 판정 ①②④⑤) ─────────────────────
# bench14 3차 A·M 덱 8벌 가운데 7벌이 꼬리말 출처에 자료에 없는 '…내부 자료'를 적었다(작성자가 '…현황'·'…계획(안)'이
# 확장 지어냄에 걸리자 '내부 자료'로 바꿔 통과시킨 저장 로그 — r4 진단 §0·§8). 자료가 출처 이름을 밝히지 않으면 출처는
# 비운다. 아래 말은 문서 이름이 아니라 '어딘가의 자료'라는 뜻뿐이라, 자료에 그 말이 없으면 강한 경로 soft · 약한 경로 hard.
# '공사'·'회사'는 앞이 한글·○ 가 아닐 때만 — 기관 이름 꼬리('한국○○공사 통계')를 일반 말 '공사 통계'로 읽어 맞는 출처가
# 약한 경로 hard → 두 판이면 비워졌다(r4 적대 검토 규칙 §3 B05). '○○공사 자료' 꼴은 출처자료밖(끝 낱말)이 받는다
_일반출처re = re.compile(r"(?:내부|자체|사내|부서|기관|관련|담당\s*부서|(?<![가-힣○△□◯])공사|(?<![가-힣○△□◯])회사)"
                     r"\s*(?:자료|집계|통계|보고|조사|문서|현황)")
# 자료가 출처 이름을 밝혔다고 볼 말(게이트 '수치 장 출처 없음' soft 와 같은 자) — 없으면 출처를 비우라고 알린다
_출처말re = re.compile(r"출처|통계|조사|대장|보고서|공시|백서|집계|보도시점|보도자료|자료\s*[:(（]|기준\s*\)")
# 사용자·기관이 브리핑형(진남 머리띠)을 청한 말 — '업무보고' 는 청한 말이 아니다(bench14 A s7: 작성자가 업무보고 칸이라
# briefing 을 골랐다 — 주관 판정 ① '사용자·기관이 청했을 때만')
_브리핑청함re = re.compile(r"브리핑형|briefing|머리띠|진남|재경부\s*(?:식|양식|서식|관행)|업무보고\s*(?:양식|서식|관행)")


def 출처자료밖(출처, 자료):
    """출처가 자료 밖인가 — 괄호를 뺀 출처의 끝 낱말(문서 종류)이 자료 글에 없으면 참. W-출처자료밖 과 약한 경로 hard 가
    같은 자로 잰다. 예전 자('26-09-30 round4 — 자료에 출처 말이 하나라도 있으면 끄고, 출처 낱말의 1/3 넘게가 자료에 없을
    때만)는 '만족도 조사'·'(6월 말 기준)'·'보도시점' 같은 본문 낱말 하나로 통째로 꺼졌고, 자료 낱말 셋을 엮은 이름
    ('총무처 문서 관리 현황' — r4 EXAONE s2 최종 판 초안 다섯 벌 모두)을 통과시켰다(r4 적대 검토 규칙 §4: 합성 지어냄
    3/10 → 끝 낱말 자 8/10, 맞는 덱 14벌 새 오탐 0). 남는 샘: 끝 낱말이 자료에 있는 이름('총무처 예산 계획' — 자료에
    '예산 계획')·부서 이름뿐인 출처('기획조정실').

    '26-09-30 주관 판정 W3 — 이제 판정은 지어냈나._출처_지어냄인가 하나다(찾는 눈 하나면 돌리는 손도 하나: 확장 검사·교정지시가
    쓰는 자와 슬라이드 강한 경로 soft·약한 경로 hard 가 같은 출처를 서로 다르게 보던 것 — 목록 밖 20건 17:19). 이 이름은 부르는
    쪽 호환으로 남긴다(= 출처지어냄)."""
    return 출처지어냄(출처, 자료)


def 출처지어냄(출처, 자료):
    """출처가 자료에 없는(지어낸) 출처인가 — 지어냈나._출처_지어냄인가 로 잰다(끝 낱말 문서 종류와 앞 이름이 자료에 함께
    나와야 통과, 목록 밖 끝 낱말은 낱말이 모두 자료에 있어야 통과, '○○'뿐인 앞 이름('○○ 통계')은 자료에 그 글이 그대로 없으면
    지은 출처 — fixup2 X3). 자료·출처가 비었으면 거짓."""
    if not (isinstance(자료, str) and 자료.strip() and isinstance(출처, str) and 출처.strip()):
        return False
    import 지어냈나 as F
    return bool(F._출처_지어냄인가(출처, 자료))


def 출처일반말(출처, 자료):
    """출처 글에서 자료에 없는 일반 출처 말('내부 자료'·'자체 집계' 등) — 없으면 None."""
    for m in _일반출처re.finditer(str(출처 or "")):
        말 = m.group(0)
        if not (isinstance(자료, str) and re.sub(r"\s+", "", 말) in re.sub(r"\s+", "", 자료)):
            return 말
    return None


_짝토씨 = re.compile(r"(?:으로|에서|까지|부터|이며|이고|은|는|이|가|을|를|의|에|로|과|와|도|만)$")
_잇는말re = re.compile(r"^\s*(?:그래서|이에|이를|따라서|그 결과|그결과|이 때문에|이때문에|이로 인해|이로써|그러므로|그러자|"
                    r"대책으로|대응으로)")


def _낱말들(t):
    out = set()
    for w in re.findall(r"[가-힣]{2,}", str(t or "")):
        w2 = _짝토씨.sub("", w) if len(w) > 2 else w
        if len(w2) >= 2:
            out.add(w2)
    return out


def 짝안잇는줄(c, 자료):
    """짝카드 '짝'(화살표) 줄 가운데 자료의 한 문장이 두 쪽을 함께 말하지 않는 줄 — [(줄 색인, 왼 글, 오른 글)].
    자료가 나란히 적은 두 목록(bench14 s6 '남은 과제: …'·'하반기 계획: …')을 화살표로 이으면 인과로 읽힌다(해석 지적
    VA 5→9·VM 5→12, r4 진단 §5). 양쪽에 같이 든 낱말(두 쪽 모두 '고령층')은 잇는 증거로 치지 않는다."""
    if not (isinstance(자료, str) and 자료.strip()) or c.get("변형", "짝") != "짝":
        return []
    문장0 = [x for x in re.split(r"(?<!\d)[.。](?!\d)|\n|[;；]", 자료) if x.strip()]
    # 다음 문장이 잇는 말('그래서'·'이에 따라'·'이를'·'그 결과' …)로 시작하면 두 문장이 한 관계를 말한다 — 붙여서도 본다
    # (r4 적대 검토 규칙 §1: 자료가 관계를 두 문장에 걸쳐 말한 맞는 덱 12벌 가운데 6벌이 울렸다 → 붙여 보면 2벌).
    # 잇는 말 없이 인접 문장을 다 붙이면 나란한 두 목록(줄바꿈·마침표)이 조용해진다 — 그래서 잇는 말이 있을 때만
    문장 = list(문장0) + [문장0[k] + " " + 문장0[k + 1] for k in range(len(문장0) - 1) if _잇는말re.match(문장0[k + 1])]
    out = []
    for j, 줄 in enumerate(c.get("줄") or []):
        if not isinstance(줄, dict):
            continue
        왼글 = 글자((줄.get("왼") or {}).get("글")) if isinstance(줄.get("왼"), dict) else ""
        오른글 = 글자((줄.get("오른") or {}).get("글")) if isinstance(줄.get("오른"), dict) else ""
        왼0, 오른0 = _낱말들(왼글), _낱말들(오른글)
        # 두 쪽에 같이 든 낱말·줄기('정비' ↔ '정비반')는 잇는 증거가 아니다 — 한 문장이 두 목록 이름을 다 품는다
        왼 = {w for w in 왼0 if not any(w in o or o in w for o in 오른0)}
        오른 = {w for w in 오른0 if not any(w in o or o in w for o in 왼0)}
        if not 왼 or not 오른:
            continue
        # 두 쪽 낱말의 절반 이상이 한 문장에 함께 있어야 잇는다 — 낱말 하나('응대')만 겹친 다른 문장(과제 목록)은 증거가 아니다
        반 = lambda ws, x: sum(1 for w in ws if w in x) * 2 >= len(ws)   # noqa: E731
        if not any(반(왼, x) and 반(오른, x) for x in 문장):
            out.append((j, 왼글, 오른글))
    return out


def 추가소프트(doc, 이미hard=(), 약한모델=False, 약한경로=False):
    """조립 게이트(slides_v2_gate)에 없는 신설 soft — [(규칙id, 자리, 메시지)]. 이미hard 는 조립
    게이트가 낸 hard 목록(같은 사실을 두 번 알리지 않으려고 본다). 약한경로(서버 모델 초안)면 판 채우기·짝 잇기 권고는
    싣지 않는다 — 약한 모델은 권고를 받으면 자료에 없는 값을 지어 채웠다(bench13·14 EXAONE)."""
    out = []
    자료 = _자료글(doc)
    if doc.get("프리셋") == "briefing" and 자료 and not _브리핑청함re.search(자료):
        out.append(("W-브리핑프리셋", "(최상위).프리셋",
                    "브리핑형(진남 머리띠·'구분 : 결론' 머리)은 사용자·기관이 청했을 때만 쓴다 — 자료에 그런 말이 없으면 "
                    "프리셋을 빼 기본(data: 옅은 눈썹 머리 + 강조색 구절)으로 둔다"))
    장들 = [j for j in (doc.get("장") or []) if isinstance(j, dict)]
    이미 = " ".join(이미hard)
    선차트값 = {}
    요청있음 = False
    표지 = next((j for j in 장들 if j.get("유형") == "표지"), None)
    태그 = ((표지 or {}).get("표지") or {}).get("태그")
    if 태그 and 태그 == (doc.get("발표정보") or {}).get("회의"):
        out.append(("W-표지태그중복", "장.0.표지.태그", "표지 태그가 발표정보.회의와 같은 말이다 — 태그를 빼라"))
    # 요청 금액 타일(한눈에보기의 판단 숫자, '26-09-29 ⑩)은 맥락이 요청 자체다 — '맥락 없는 큰 숫자'로 치지 않는다
    요청금액 = set()
    for 장 in 장들:
        for _, c in 칸들(장):
            if c.get("부품") == "요청상자" and isinstance(c.get("금액"), dict):
                요청금액 |= 게이트()._수들(c["금액"].get("값"))
    for i, 장 in enumerate(장들):
        유형 = 장.get("유형")
        자리 = f"장.{i}({유형})"
        for p, c in 칸들(장):
            n = c.get("부품")
            if n == "요청상자":
                요청있음 = True
            if n == "선차트":
                if sum(1 for s in c.get("계열") or [] if isinstance(s, dict) and s.get("역할", "강조") == "강조") > 1 \
                        and "강조 계열" not in 이미:
                    out.append(("W-차트강조", f"{자리}.{p}", "선차트 강조 계열이 2개 이상 — 강조는 하나, 나머지는 '비교'(회색)"))
                for s in c.get("계열") or []:
                    if isinstance(s, dict):
                        선차트값.setdefault(json.dumps(s.get("값"), ensure_ascii=False), []).append(i)
            if n == "가로막대":
                if sum(1 for r in c.get("행") or [] if isinstance(r, dict) and r.get("역할") == "강조") > 1 \
                        and "강조 행" not in 이미:
                    out.append(("W-차트강조", f"{자리}.{p}", "가로막대 강조 행이 2개 이상 — 강조는 하나"))
            if n == "지표타일":
                맥 = c.get("맥락") or {}
                if 맥.get("종류") in ("합계", "기간", "대상") and not c.get("증감") \
                        and not (요청금액 and 게이트()._수들(c.get("값")) and 게이트()._수들(c.get("값")) <= 요청금액):
                    out.append(("W-맥락없는큰숫자", f"{자리}.{p}",
                                f"지표타일 '{c.get('라벨')}' 의 맥락이 {맥.get('종류')}뿐이다 — 비교 기준(전년·이전·"
                                + ("평균·목표)이 자료에 없으면 카드 항목으로 적는다(약한 모델 부분집합)" if 약한모델
                                   else "평균·목표)이 자료에 없으면 수량목록이 맞다")))
            if n in ("타임라인", "세로타임라인"):
                단계 = c.get("단계") if n == "타임라인" else c.get("항목")
                시점들 = [x.get("시점") for x in 단계 or [] if isinstance(x, dict)]
                for 앞, 뒤 in 시점역행(시점들):
                    out.append(("W-타임라인순서", f"{자리}.{p}", f"시점 '{뒤}' 가 앞 시점 '{앞}' 보다 이르다 — 시간 순서대로"))
                모호 = [s for s in 시점들 if any(w in str(s) for w in _모호시점)]
                if 모호 and n == "타임라인":
                    out.append(("W-모호시점", f"{자리}.{p}",
                                f"한 점에 못 박을 수 없는 시점 {모호} — 리본 단계 말고 '상시' 띠에"))
        if 유형 == "표지":
            수치 = (장.get("표지") or {}).get("수치")
            if isinstance(수치, dict) and not 수치.get("맥락"):
                out.append(("W-맥락없는큰숫자", f"{자리}.표지.수치", "표지 큰 숫자에 맥락(기준 시점·비교)이 없다"))
    출처말있음 = bool(자료 and _출처말re.search(자료))
    일반장 = {}
    for i, 장 in enumerate(장들):
        유형 = 장.get("유형")
        출처 = 장.get("출처")
        # 걸지 말지는 출처지어냄(지어냈나 한 곳, W3) — 출처일반말은 되먹임 문구('내부 자료' 줄로 묶기)만 가른다
        if isinstance(출처, str) and 출처.strip() and not 약한경로 and 출처지어냄(출처, 자료):   # 약한 경로는 자료대조가 hard 로
            일반 = 출처일반말(출처, 자료)
            if 일반:
                일반장.setdefault(일반, []).append(i)
            else:
                out.append(("W-출처자료밖", f"장.{i}.출처",
                            f"출처 '{출처[:24]}' 가 자료에 없다 — 자료가 출처 이름을 밝히지 않았으면 출처 키를 지운다(비워 둔다)"))
        if 약한경로 or 유형 in ("표지", "목차", "간지", "마무리"):
            continue
        for p, c in 칸들(장):
            if c.get("부품") == "짝카드":
                for j, 왼글, 오른글 in 짝안잇는줄(c, 자료):
                    out.append(("W-짝잇기", f"장.{i}({유형}).{p}.줄.{j}",
                                f"짝 '{왼글[:16]} → {오른글[:16]}' 을 자료가 잇지 않는다(한 문장이나 '그래서·이에 따라'로 이은 두 문장이 아니다) — 화살표(짝)는 자료가 두 쪽의 "
                                "관계(문제→대응·전→후)를 말할 때만. 자료가 나란히 적은 두 목록이면 화살표 없는 두 칸(변형 '대비' "
                                "또는 카드 둘)으로, 한쪽이 없는 줄은 지어 채우지 않는다"))
        if not 장.get("요지띠"):
            try:
                import importlib
                빔 = importlib.import_module("assemble_slides")._v2남는높이(
                    장, 장.get("밀도") if 장.get("밀도") in ("발표", "보고", "배포") else (doc.get("밀도") or "보고"),
                    doc.get("프리셋") or "data")
            except Exception:
                빔 = 0.0
            if 빔 >= 0.2:
                out.append(("W-판아래빔", f"장.{i}({유형})",
                            f"본문 아래가 판의 {round(빔 * 100)}% 쯤 빈다 — 자료에 이 장의 결론 한 줄이 있으면 요지띠로, 자료에 "
                            "수치가 있으면 지표타일로 채운다(자료에 없는 값은 지어 넣지 않는다 — 없으면 앞뒤 장과 합치거나 그대로 둔다)"))
    for 일반, 번호 in 일반장.items():        # 같은 말은 한 줄(되먹임이 장마다 같은 줄로 길어지지 않게)
        out.append(("W-출처일반말", "장." + "·".join(str(n) for n in 번호) + ".출처",
                    f"출처의 '{일반}' 은 자료에 없는 일반 말이다 — 자료가 밝힌 문서 이름·시점만 적고, 밝히지 않았으면 "
                    "출처 키를 지운다('내부 자료'·'자체 집계'를 지어 붙이지 않는다)"))
    for 값, 번호 in 선차트값.items():
        if len(set(번호)) > 1:
            out.append(("W-선차트반복", "(덱)", f"같은 선차트 계열이 여러 장({sorted(set(번호))})에 — 같은 추이는 한 번만"))
    if 요청있음 and doc.get("목적") != "설득":      # 설득 덱은 마무리에서 요청을 한 줄로 되새길 수 있다('26-09-29 ⑫ — 금액 되풀이는 게이트가 본다)
        for i, 장 in enumerate(장들):
            if 장.get("유형") == "마무리":
                마 = 장.get("마무리") or {}
                마글 = 글자(마.get("문구")) + " " + str(마.get("부문구") or "")
                if any(w in 마글 for w in _요청신호):
                    out.append(("W-마무리요청", f"장.{i}(마무리)",
                                "마무리에 요청·승인 문구 — 요청은 요청상자 한 번, 마무리는 비전·행동·문의만"))
    return out


# ── 모양 정규화(새문서 입구) — 확실한 꼴만 고치고 애매하면 게이트에 맡긴다 ──────────────────
# '26-09-29 bench11: 서버 약한 모델(EXAONE) 4/4 실패의 대부분이 뜻은 맞고 모양만 틀린 것이었다 — 수 칸에
# '79점'·'4.2억'(글), 글 칸에 4.2(수), 배열 칸에 글 하나, {글} 칸에 글, 헤드 44자(40자 상한), 장 배열 안
# 글 조각. 되시도(분 단위)로 돌려보내는 대신 여기서 받아들인다. 규칙(정밀도 우선 — 메모리 auto-correct):
#   · 수 칸의 글은 '수+꼬리' 꼴만 받는다(꼬리는 부품의 단위 칸이 비었을 때만 단위로, 막대 행은 표시로).
#   · 글 칸의 수는 천 단위 쉼표 글로. 배열(글) 칸의 글은 한 항목 배열로. 필수 키가 하나뿐인 객체 칸의 글은 그 키로.
#   · 열거 밖 값은 열거 낱말을 딱 하나 품을 때·동의어 표에 있을 때만 바꾼다(그 밖은 게이트가 막는다).
#   · 제목류(메시지·라벨·제목·이름) 글자 상한 초과는 1.5배 안이면 괄호 → 절 경계 → 낱말 경계로 줄이고 원문을
#     노트.메모에 남긴다(soft 로 알린다). 헤드의 ' + ' 연결은 쉼표로(⑬).
#   · 장 배열 안 글 조각은 JSON 객체면 풀고, 아니면 빼고 알린다.
# '현재'는 뺐다 — '현재'는 비교 기준(이전)이 아니라 지금 값이다. 이전으로 바꾸면 맥락 없는 큰 숫자 soft 가 꺼졌다
# ('26-09-29 round2 적대 검토 규칙 §3-G). 모르는 낱말은 경고 쪽(대상)으로 기운다.
_열거동의어 = {"연간": "기간", "누계": "합계", "총계": "합계", "총": "합계", "작년": "전년", "전년도": "전년",
           "기존": "이전", "종전": "이전", "과거": "이전"}
_제목키 = ("메시지", "라벨", "제목", "이름", "왼제목", "오른제목")
_영문키 = {"title": "제목", "label": "라벨", "value": "값", "unit": "단위", "message": "메시지", "items": "항목"}
# 정수부는 천 단위 쉼표가 제자리일 때만('12,3%'·'1,2,3건'은 수로 읽지 않는다 — round2 적대 검토 N7)
_수꼴 = re.compile(r"^\s*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*([^\d\s][^\d]{0,7})?\s*$")
_배율 = {"조": 1e12, "억": 1e8, "천만": 1e7, "백만": 1e6, "만": 1e4, "천": 1e3}
_배율re = re.compile(r"^(조|억|천만|백만|만|천)(.*)$")


def _수읽기(v):
    """수 칸 글 → (수, 꼬리) 또는 None. 꼬리가 문장부호뿐('5.')이면 수로 읽지 않는다(N8)."""
    m = _수꼴.match(str(v))
    if not m:
        return None
    꼬 = (m.group(2) or "").strip()
    if 꼬 and re.fullmatch(r"[.,;:·!?~\-–—/]+", 꼬):
        return None
    n = float(m.group(1).replace(",", ""))
    return (int(n) if n.is_integer() and "." not in m.group(1) else n), 꼬


def _수글로(n):
    if isinstance(n, bool):
        return str(n)
    if isinstance(n, int) or (isinstance(n, float) and n.is_integer()):
        return f"{int(n):,}"
    return f"{n:,}".rstrip("0").rstrip(".") if isinstance(n, float) else str(n)


_부정꼬리 = re.compile(r"않|어렵|없|못|아니|불가|미달|미흡|부족")


def _줄이기(s, n):
    """제목류 글을 n자 안으로 — **절 경계(쉼표·가운뎃점)에서 앞 절만** 남긴다. 못 줄이면 None(= 게이트 hard,
    모델이 뜻을 살려 다시 쓴다).

    '26-09-29 round2 적대 검토 N1·N2: ① 숫자 안 쉼표('3,100만원')를 절 경계로 잘라 '연간 유지비 3'이 됐다 → 앞뒤가
    숫자인 쉼표는 경계가 아니다. ② 숫자 없는 괄호를 먼저 지워 '(잠정)'·'(목표 미달)'이 사라졌다 → 괄호는 지우지 않는다.
    ③ 낱말 경계 자르기가 '…보기 어렵다'의 부정·'…절감 효과'의 술어를 떨궜다 → 낱말 경계로는 자르지 않는다.
    남길 앞 절이 괄호를 반만 품거나, 떨굴 뒤 절이 앞 절을 부정하는 말로 시작하면 자르지 않는다."""
    t = s.strip()
    if len(t) <= n:
        return t
    끝 = [m.start() for m in re.finditer(r"(?<!\d),|,(?!\d)|·", t) if m.start() <= n]
    끝 = [k for k in 끝 if t[:k].count("(") == t[:k].count(")") and t[:k].count("（") == t[:k].count("）")]
    if not 끝 or 끝[-1] < n * 0.5:
        return None
    k = 끝[-1]
    뒤 = t[k + 1:].strip()
    # 떨굴 뒤 절 첫 두 어절에 부정·반전 말이 있으면 앞 절 뜻을 뒤집는다('…가능하다고, 보기 어렵다') — 자르지 않는다
    if _부정꼬리.search(" ".join(뒤.split()[:2])) or re.match(r"(?:다만|단|그러나|하지만)(?:\s|,|$)", 뒤):
        return None
    return t[:k].strip()


def _고침(v, sch, 뿌리, 자리, 알림, 꼬리):
    G = 게이트()
    sch = G._풀기(sch, 뿌리)
    if not isinstance(sch, dict) or not sch:
        return v
    if "oneOf" in sch and isinstance(v, dict) and "부품" in v:
        갈래 = G._부품갈래(v, sch["oneOf"], 뿌리)
        if 갈래 is not None:
            return _고침(v, 갈래, 뿌리, 자리, 알림, 꼬리)
    ts = sch.get("type")
    ts = ts if isinstance(ts, list) else ([ts] if ts else [])
    if ts and not any(G._형(v, t) for t in ts):
        if "number" in ts and isinstance(v, str):
            읽 = _수읽기(v)
            if 읽 and 자리 not in 꼬리.get("_거절", ()):
                n, 꼬 = 읽
                꼬리[자리] = 꼬, v
                알림.append(f"{자리}: 글 '{v}' 를 수 {n} 로 읽었다" + (f"(꼬리 '{꼬}')" if 꼬 else ""))
                return n
            return v
        if "string" in ts and G._형(v, "number"):
            알림.append(f"{자리}: 수 {v} 를 글로 바꿨다")
            return _수글로(v)
        if "array" in ts and isinstance(v, str) and v.strip():
            알림.append(f"{자리}: 글 하나를 한 항목 배열로 감쌌다")
            v = [v]
        elif "object" in ts and isinstance(v, str) and v.strip() and not re.fullmatch(r"장\.\d+", 자리):   # 끊긴 장 조각은 감싸지 않는다
            req = sch.get("required") or []
            if len(req) == 1 and G._형(v, (G._풀기((sch.get("properties") or {}).get(req[0], {}), 뿌리) or {}).get("type", "string")):
                알림.append(f"{자리}: 글 하나를 {{{req[0]}}} 로 감쌌다")
                return {req[0]: v}
            return v
        else:
            return v
    if "enum" in sch and v not in sch["enum"] and isinstance(v, str):
        품 = [x for x in sch["enum"] if isinstance(x, str) and x in v]
        새 = 품[0] if len(품) == 1 else _열거동의어.get(v.strip())
        if 새 is None and "default" in sch and 자리.endswith(".역할"):
            새 = sch["default"]
        if 새 is None and 자리.endswith(".맥락.종류") and "대상" in sch["enum"]:
            # 맥락.종류는 화면에 안 찍히고 '맥락 없는 큰 숫자' soft 만 가른다 — 모르는 낱말('기대효과'·'절감')은
            # 참 비교 기준(전년·이전·평균·목표)이 아니므로 설명 갈래(대상)로 둔다. 경고 쪽으로만 기운다.
            새 = "대상"
        if 새 in sch["enum"]:
            알림.append(f"{자리}: '{v}' → '{새}'")
            return 새
        return v
    if isinstance(v, str):
        키 = 자리.rsplit(".", 1)[-1]
        if 키 == "값" and re.fullmatch(r"\d{4,}(\.\d+)?", v.strip()) and not re.fullmatch(r"(19|20)\d\d", v.strip()):   # 연도는 그대로
            # 숫자 글 값('5000')에 천 단위 쉼표 — 화면에 '5000만원' 으로 찍혔다('26-09-29 EXAONE s6). 뜻은 그대로다
            정, _, 소 = v.strip().partition(".")
            새 = f"{int(정):,}" + (f".{소}" if 소 else "")
            알림.append(f"{자리}: '{v}' → '{새}'(천 단위 쉼표)")
            v = 새
        if 키 == "메시지" and (re.search(r"\S\s+\+\s+\S", v) or re.search(r"[가-힣]\+[가-힣]", v)):
            새 = re.sub(r"(?<=[가-힣])\+(?=[가-힣])", ", ", re.sub(r"\s+\+\s+", ", ", v))   # '개편+절차'도(한글 사이 '+')
            알림.append(f"{자리}: 헤드의 ' + ' 연결을 쉼표로 바꿨다")
            v = 새
        상한 = sch.get("maxLength")
        if 키 in _제목키 and isinstance(상한, int) and 상한 < len(v) <= 상한 * 1.5:
            새 = _줄이기(v, 상한)
            if 새:
                알림.append(f"~{자리}|{v}|{자리}: {len(v)}자 → {len(새)}자로 줄였다(상한 {상한}자, 원문은 노트.메모) — 확인하라")
                return 새
        return v
    if isinstance(v, list) and "items" in sch:
        return [_고침(x, sch["items"], 뿌리, f"{자리}.{n}", 알림, 꼬리) for n, x in enumerate(v)]
    if isinstance(v, dict):
        props = sch.get("properties") or {}
        for 영, 한 in _영문키.items():              # 영문 키('title')는 같은 뜻 한글 키가 비었을 때만 옮긴다
            if 영 in v and 영 not in props and 한 in props and 한 not in v:
                알림.append(f"{자리}: 키 '{영}' → '{한}'")
                v = {(한 if k == 영 else k): x for k, x in v.items()}
        새 = {}
        for k, x in v.items():
            새[k] = _고침(x, props[k], 뿌리, f"{자리}.{k}" if 자리 else k, 알림, 꼬리) if k in props else x
        # 글 칸 '값' 에 '80%'·'1,550만원' — 단위 칸이 비었으면 수와 단위로 나눈다(지표타일·금액·수량목록)
        값칸 = G._풀기(props.get("값") or {}, 뿌리) if "값" in props else {}
        if "단위" in props and isinstance(새.get("값"), str) and 값칸.get("type") == "string" and not 새.get("단위"):
            m = _수꼴.match(새["값"])
            if m and m.group(2) and m.group(2).strip() not in ("~", "-"):
                알림.append(f"{자리}.값: '{새['값']}' 를 값 '{m.group(1)}' · 단위 '{m.group(2).strip()}' 로 나눴다")
                새["값"], 새["단위"] = m.group(1), m.group(2).strip()
        # 수 칸에서 떼어 낸 꼬리 — 부품 단위 칸이 비었으면 단위로, 막대 행 값은 표시로(보이는 글을 그대로 둔다).
        # '26-09-29 round2 적대 검토 N3·N6: 단위 '원'이 이미 있는데 값 '4.2억'의 꼬리 '억'을 버려 화면이 '4.2 원'이 됐고,
        # 진행막대 목표 '48곳'의 꼬리가 표시로 가 범례 '목표 48곳'이 '48곳'이 됐다 →
        #   · 꼬리 = 단위(또는 단위가 꼬리로 시작) → 버린다(같은 말) · 배율 꼬리(억·만…) + 단위 '원' 류 → 단위를 '억원'으로 합친다
        #   · 그 밖에 단위와 다른 꼬리 → 수로 바꾸지 않고 글로 되돌린다(게이트가 막는다 — 정밀도 우선)
        #   · 표시로 보내는 것은 막대 행의 '값' 꼬리뿐
        for k in list(새):
            q = f"{자리}.{k}" if 자리 else k
            if q in 꼬리:
                끝, 원 = 꼬리.pop(q)
                if not 끝:
                    continue
                단 = str(새.get("단위") or "").strip()
                if "단위" in props and not 단:
                    새["단위"] = 끝
                elif "단위" in props and 단:
                    if 끝 == 단 or 단.startswith(끝):
                        continue
                    mm = _배율re.match(끝)
                    if mm and not mm.group(2) and not _배율re.match(단):
                        새["단위"] = 끝 + 단
                        알림.append(f"{q}: 꼬리 '{끝}' 와 단위 '{단}' 를 단위 '{끝 + 단}' 로 합쳤다")
                        continue
                    새[k] = 원
                    알림.append(f"!{q}: 글 '{원}' 의 꼬리 '{끝}' 가 단위 '{단}' 와 달라 수로 바꾸지 않았다 — 값은 수만, 단위는 단위 칸 하나에 적는다")
                elif "표시" in props and k == "값" and not 새.get("표시"):
                    새["표시"] = 원.strip()
        # 천 단위 쉼표 — 연도처럼 보이는 네 자리('2000')도 단위가 연도가 아니면 수다(N9: '2000명')
        if isinstance(새.get("값"), str) and re.fullmatch(r"(19|20)\d\d", 새["값"].strip()) and 새.get("단위") \
                and not str(새["단위"]).strip().startswith(("년", "연")) and 값칸.get("type") == "string":
            알림.append(f"{자리}.값: '{새['값']}' → '{int(새['값']):,}'(천 단위 쉼표)")
            새["값"] = f"{int(새['값']):,}"
        return 새
    return v


def _구조고침(doc, 알림):
    """스키마 걷기 전에 **뜻이 하나로 정해지는** 구조만 고친다('26-09-29 bench11 EXAONE 초안 16건에서 본 꼴).
    · 빈 글('') 선택 슬롯 → 뺀다(빈 칸 = 없는 칸)          · 칸 배열 안 글 조각 → 뺀다(부품이 아니다)
    · 마무리 장에 머리만 있고 마무리가 없음 → 머리.메시지를 마무리.문구로
    · 짝카드 변형 '대비' 에 줄[{왼,오른}] → 왼항목·오른항목 두 목록으로(대비는 줄 대응이 없다)
    · 타임라인 단계 제목이 상한을 넘고 설명이 없음 → 'A: B' 는 제목 A·설명 B, 'A(B)' 는 제목 A·설명 B
    · 항목 1개짜리 카드 → 항목타일(제목·글, 장 유형이 항목타일을 받을 때만) — 판_채우기_v2 의 '숫자 없는 효과=항목타일'
    값이 사라지는 고침은 하지 않는다(글을 옮기기만 한다). 애매하면 그대로 두고 게이트가 막는다."""
    S = 스키마()
    D = S["$defs"]
    배치 = S.get("x-기본배치") or {}
    타임제목상한 = (((D.get("부품_타임라인") or {}).get("properties") or {}).get("단계") or {}).get("items", {}) \
        .get("properties", {}).get("제목", {}).get("maxLength", 12)
    타일 = (D.get("부품_항목타일") or {}).get("properties") or {}
    타일제목, 타일글 = (타일.get("제목") or {}).get("maxLength", 14), (타일.get("글") or {}).get("maxLength", 30)

    def 빈글빼기(o, 자리):
        if isinstance(o, dict):
            for k in [k for k, v in o.items() if isinstance(v, str) and not v.strip() and k not in ("부품", "유형")]:
                o.pop(k)
                알림.append(f"{자리}.{k}: 빈 글 칸을 뺐다")
            for k, v in o.items():
                빈글빼기(v, f"{자리}.{k}" if 자리 else k)
        elif isinstance(o, list):
            for n, v in enumerate(o):
                빈글빼기(v, f"{자리}.{n}")
    빈글빼기(doc, "")
    장들 = doc.get("장")
    # 표지가 없으면 표지 장을 앞에 둔다 — 조립기가 어차피 표지를 그리는데(같은 모양: 제목·발표정보), 문서에 장이 없으면
    # 그 표지엔 장 번호가 없어 PPTX 노트(산출 식)가 통째로 빠지고(round2 적대 검토 H5 — topptx 가 장 수로 짝짓는다),
    # 게이트의 장 수(5)와 렌더 쪽수(6)가 어긋났다(§3-H). 17장(스키마 상한)이면 넣지 않는다.
    if isinstance(장들, list) and 장들 and all(isinstance(j, dict) for j in 장들[:1]) \
            and 장들[0].get("유형") != "표지" and len(장들) < 17 and not any(
                isinstance(j, dict) and j.get("유형") == "표지" for j in 장들):
        장들.insert(0, {"유형": "표지"})
        알림.append("장.0: 표지 장이 없어 앞에 넣었다(조립기가 그리던 표지와 같은 모양 — 장 번호가 하나씩 밀린다)")
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict):
            continue
        if isinstance(장.get("칸"), list):
            남 = [c for c in 장["칸"] if not isinstance(c, str)]
            if len(남) != len(장["칸"]):
                알림.append(f"장.{i}.칸: 부품이 아닌 글 조각 {len(장['칸']) - len(남)}개를 뺐다")
                장["칸"] = 남
            # 짝카드를 왼쪽만·오른쪽만 둘로 나눠 쓴 꼴 → 대비 하나로('26-09-29 EXAONE s2d 초안1: {왼제목·왼항목} +
            # {오른제목·오른항목}, 변형 '짝'인데 줄 없음 → hard 6줄). 같은 장에 붙은 두 칸이고 겹치는 키가 없을 때만.
            for k in range(len(장["칸"]) - 1):
                a, b = 장["칸"][k], 장["칸"][k + 1]
                if not (isinstance(a, dict) and isinstance(b, dict) and a.get("부품") == b.get("부품") == "짝카드"):
                    continue
                왼, 오 = {"왼제목", "왼항목"}, {"오른제목", "오른항목"}
                ka, kb = set(a) - {"부품", "변형", "폭"}, set(b) - {"부품", "변형", "폭"}
                if ka == 왼 and kb == 오 and isinstance(a["왼항목"], list) and isinstance(b["오른항목"], list):
                    장["칸"][k] = {"부품": "짝카드", "변형": "대비", "왼제목": a["왼제목"], "오른제목": b["오른제목"],
                                 "왼항목": a["왼항목"], "오른항목": b["오른항목"]}
                    장["칸"].pop(k + 1)
                    알림.append(f"장.{i}.칸.{k}: 왼쪽만·오른쪽만 쓴 짝카드 둘을 '대비' 하나로 합쳤다")
                    break
        # 자리표시뿐인 출처('○○'·'-') — 담긴 뜻이 없어 뺀다(꼬리말에 '○○'가 그대로 찍혔다, fixup EXAONE s2·s6 3장씩).
        # 빼면 게이트가 (자료에 출처 말이 있을 때) '수치 장인데 출처가 없다' soft 로 자료의 출처를 옮기라고 알린다.
        if isinstance(장.get("출처"), str) and re.fullmatch(r"[○△□◯●\s\-–—·.,()]*", 장["출처"]):
            알림.append(f"장.{i}.출처: 자리표시뿐인 출처 '{장['출처']}' 를 뺐다")
            장.pop("출처")
        if 장.get("유형") == "마무리" and not isinstance(장.get("마무리"), dict) and isinstance(장.get("머리"), dict) \
                and 장["머리"].get("메시지"):
            장["마무리"] = {"문구": 장["머리"]["메시지"]}
            장.pop("머리")
            알림.append(f"장.{i}: 마무리 장의 머리 메시지를 마무리.문구로 옮겼다")
        허용 = (배치.get(장.get("유형")) or {}).get("허용") if isinstance(배치.get(장.get("유형")), dict) else None
        for k, c in enumerate(장.get("칸") or []):
            if not isinstance(c, dict):
                continue
            p = f"장.{i}.칸.{k}"
            if c.get("부품") == "짝카드" and c.get("변형") == "대비" and isinstance(c.get("줄"), list) \
                    and not c.get("왼항목") and not c.get("오른항목") \
                    and all(isinstance(r, dict) and set(r) <= {"왼", "오른"} for r in c["줄"]):
                c["왼항목"] = [r["왼"] for r in c["줄"] if r.get("왼")]
                c["오른항목"] = [r["오른"] for r in c["줄"] if r.get("오른")]
                c.pop("줄")
                알림.append(f"{p}: 짝카드 '대비' 의 줄을 왼항목·오른항목으로 나눴다")
            # 짝카드 변형과 슬롯이 어긋난 꼴 — 뜻이 하나로 정해지는 것만('26-09-29 fixup EXAONE s2 초안 5건 중 4건):
            #   · 줄 없이 왼항목·오른항목이 다 있는데 변형이 '짝'(또는 없음) → 변형 '대비'
            #   · 변형 '짝'(또는 없음)인데 줄이 1개뿐(줄은 2개 이상) → '대비'의 한 항목씩으로(글은 그대로 옮긴다)
            if c.get("부품") == "짝카드" and c.get("변형", "짝") == "짝":
                if not c.get("줄") and isinstance(c.get("왼항목"), list) and isinstance(c.get("오른항목"), list):
                    c["변형"] = "대비"
                    알림.append(f"{p}: 줄 없이 왼항목·오른항목을 쓴 짝카드를 변형 '대비'로 했다")
                elif isinstance(c.get("줄"), list) and len(c["줄"]) == 1 and isinstance(c["줄"][0], dict) \
                        and set(c["줄"][0]) <= {"왼", "오른"} and c["줄"][0].get("왼") and c["줄"][0].get("오른") \
                        and not c.get("왼항목") and not c.get("오른항목"):
                    c["왼항목"], c["오른항목"] = [c["줄"][0]["왼"]], [c["줄"][0]["오른"]]
                    c.pop("줄")
                    c["변형"] = "대비"
                    알림.append(f"{p}: 줄 1개짜리 짝카드를 '대비'(왼항목·오른항목 한 개씩)로 했다")
            if c.get("부품") == "타임라인":
                for m, d in enumerate(c.get("단계") or []):
                    t = d.get("제목") if isinstance(d, dict) else None
                    if not isinstance(t, str) or len(t) <= 타임제목상한 or d.get("설명"):
                        continue
                    mm = re.fullmatch(r"\s*([^:：(]+?)\s*[:：]\s*(.+)", t) or re.fullmatch(r"\s*([^(]+?)\s*\(([^()]+)\)\s*", t)
                    if mm and len(mm.group(1)) <= 타임제목상한:
                        d["제목"], d["설명"] = mm.group(1).strip(), [mm.group(2).strip()]
                        알림.append(f"{p}.단계.{m}: 긴 제목을 제목 '{d['제목']}' · 설명으로 나눴다")
            if c.get("부품") == "카드" and isinstance(c.get("항목"), list) and len(c["항목"]) == 1 \
                    and (허용 is None or "항목타일" in 허용):
                x = c["항목"][0]
                글 = x.get("글") if isinstance(x, dict) and not x.get("하위") else x
                제목 = c.get("제목")
                if isinstance(글, str) and isinstance(제목, str) and len(제목) <= 타일제목 and len(글) <= 타일글:
                    새 = {"부품": "항목타일", "제목": 제목, "글": 글}
                    if c.get("아이콘"):
                        새["아이콘"] = c["아이콘"]
                    장["칸"][k] = 새
                    알림.append(f"{p}: 항목 1개짜리 카드를 항목타일로 바꿨다")


def _목록(x):
    """배열 칸이 배열이 아니면(선차트 계열 '값': 14 처럼 수 하나) 빈 목록 — 모양 위반은 게이트가 알린다. 예전엔 TypeError 가
    새문서에서 "인자가 맞지 않습니다 — 'int' object is not iterable" 로 나가 모델이 그 말을 교정 지시로 받았다(r4 EXAONE s2
    최종 판 초안2 — 되시도 한 회를 헛썼다, r4 적대 검토 규칙 §7)."""
    return x if isinstance(x, list) else []


def _꼬리맞춤(doc, 알림, 거절):
    """한 부품 안 수 글의 꼬리(억·만·천 배율)가 섞였으면 — round2 적대 검토 N4·N5('4.2억'·'9,500만'을 따로 떼어
    4.2·9500 으로 그려 '9,500만' 막대가 '4.2억'보다 길었다, 선차트 '12%'의 꼬리가 버려져 단위가 사라졌다).
      · 가로막대 행: 모두 글이고 배율 뒤 말(원·가구…)이 같으면 가장 작은 배율로 **정확히** 환산해 값에 넣고 원래 글은
        표시로 둔다(보이는 글은 그대로, 막대 길이만 바르게).
      · 그 밖(선차트·진행막대·점눈금·구성띠)에서 배율이 섞이면 수로 바꾸지 않는다(거절 → 게이트 hard, 까닭을 알린다).
      · 선차트 값 꼬리가 모두 같고 단위가 비었으면 단위로 올린다."""
    def 쪼개기(꼬):
        m = _배율re.match(꼬)
        return (m.group(1), m.group(2).strip()) if m else (None, 꼬)
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict):
            continue
        for p, c in 칸들(장):
            q = f"장.{i}.{p}"
            n = c.get("부품")
            자리값 = []                                   # (경로, 원래 값, 읽은 (수, 꼬리) 또는 None)
            if n == "가로막대":
                자리값 = [(f"{q}.행.{j}.값", r.get("값")) for j, r in enumerate(_목록(c.get("행"))) if isinstance(r, dict)]
            elif n == "선차트":
                자리값 = [(f"{q}.계열.{s}.값.{t}", x) for s, 계 in enumerate(_목록(c.get("계열"))) if isinstance(계, dict)
                        for t, x in enumerate(_목록(계.get("값")))]
            elif n == "진행막대":
                자리값 = [(f"{q}.{k}", c.get(k)) for k in ("값", "목표", "목표선") if k in c]
            elif n == "점눈금":
                자리값 = [(f"{q}.점.{j}.값", x.get("값")) for j, x in enumerate(_목록(c.get("점"))) if isinstance(x, dict)]
            elif n == "구성띠":
                자리값 = [(f"{q}.조각.{j}.값", x.get("값")) for j, x in enumerate(_목록(c.get("조각"))) if isinstance(x, dict)]
            글들 = [(k, v, _수읽기(v)) for k, v in 자리값 if isinstance(v, str)]
            글들 = [(k, v, r) for k, v, r in 글들 if r]
            if not 글들:
                continue
            배율들 = {쪼개기(r[1])[0] for _, _, r in 글들}
            수있음 = any(isinstance(v, (int, float)) and not isinstance(v, bool) for _, v in 자리값)
            섞임 = any(배율들) and (len(배율들) > 1 or 수있음)
            if not 섞임:
                if n == "선차트" and not c.get("단위"):
                    꼬들 = {r[1] for _, _, r in 글들}
                    if len(꼬들) == 1 and next(iter(꼬들)) and len(글들) == len(자리값):
                        c["단위"] = next(iter(꼬들))
                        알림.append(f"{q}.단위: 계열 값 꼬리 '{c['단위']}' 를 부품 단위로 올렸다")
                continue
            뒤말 = {쪼개기(r[1])[1] for _, _, r in 글들}
            if n == "가로막대" and not 수있음 and len(뒤말) == 1:
                작은 = min(_배율.get(m, 1.0) if m else 1.0 for m in 배율들)
                for j, r in enumerate(_목록(c.get("행"))):
                    if not isinstance(r, dict) or not isinstance(r.get("값"), str):
                        continue
                    수, 꼬 = _수읽기(r["값"])
                    m = 쪼개기(꼬)[0]
                    환 = round(수 * (_배율.get(m, 1.0) if m else 1.0) / 작은, 6)
                    환 = int(환) if float(환).is_integer() else 환
                    if not r.get("표시"):
                        r["표시"] = r["값"].strip()
                    r["값"] = 환
                알림.append(f"{q}.행: 배율 꼬리가 섞인 값({', '.join(sorted(v for _, v, _ in 글들)[:3])})을 한 배율로 환산해 "
                          "막대 길이를 맞췄다(보이는 글은 그대로)")
                continue
            for k, _, _ in 글들:
                거절.add(k)
            알림.append(f"!{q}: 수 글의 배율 꼬리가 섞였다({', '.join(v for _, v, _ in 글들[:4])}) — 한 단위로 맞춰 수만 적고 "
                      "단위는 단위 칸에 하나로 적는다(따로 떼면 막대·선 길이가 뒤집힌다)")


def _요청금액넣기(doc, 알림):
    """한눈에보기에 요청 금액이 없으면 요청상자 금액으로 지표타일 하나를 만들어 끝에 붙인다('26-09-29 ⑩).
    문서 안 값만 옮긴다(지어내지 않는다) — 요청상자·금액·한눈에보기가 다 있고, 한눈에보기 칸이 5개 이하이며,
    금액 숫자가 한눈에보기 화면 글에 없을 때만. 붙였으면 soft 로 알린다(라벨·맥락 글을 확인하라)."""
    G = 게이트()
    장들 = [j for j in doc.get("장") or [] if isinstance(j, dict)]
    요약 = next((j for j in 장들 if j.get("유형") == "한눈에보기" and isinstance(j.get("칸"), list)), None)
    상자 = next((c for j in 장들 for _, c in 칸들(j) if c.get("부품") == "요청상자" and G.요청금액(c)), None)
    if not 요약 or not 상자 or len(요약["칸"]) >= 6:
        return
    금 = G.요청금액(상자)
    if not G._수들(금.get("값")):
        return
    글 = []
    G.모든글(요약, 글)
    글 += [f"{c.get('값')}{c.get('단위') or ''}" for _, c in 칸들(요약) if c.get("값") is not None]
    if G._수들(금.get("값")) & G._수들(" ".join(str(x) for x in 글)):
        return
    # 맥락 글은 요청문에서 요청말(승인·요청·건의…)을 걷은 것 — 요청문을 그대로 옮기면 한눈에보기가 '요청 말이 요청상자 밖
    # 여러 장' soft 를 스스로 만들었다(round2 적대 검토 규칙 §2-B, EXAONE s2d 재현). 걷고 남는 게 없으면 '요청 금액'.
    요청문 = G.글자(상자.get("요청문")).strip()
    for w in sorted(set(G._요청말) | set(_요청신호) | {"을 요청", "를 요청", "드립니다", "합니다"}, key=len, reverse=True):
        요청문 = 요청문.replace(w, " ")
    요청문 = re.sub(r"\s+", " ", re.sub(r"[을를]\s*$", "", 요청문.strip(" ,·.-"))).strip()
    맥 = (요청문 if 2 <= len(요청문) <= 24 else (_줄이기(요청문, 24) if len(요청문) > 24 else None)) or "요청 금액"
    타일 = {"부품": "지표타일", "라벨": str(금.get("라벨") or "요청 금액")[:15], "값": str(금["값"]),
          "맥락": {"종류": "대상", "글": 맥}}
    if 금.get("단위"):
        타일["단위"] = str(금["단위"])
    요약["칸"].append(타일)
    알림.append(f"한눈에보기에 요청 금액 {금['값']}{금.get('단위') or ''} 지표타일을 붙였다(요청상자에서 옮김 — 라벨·맥락 글을 확인하라)")


def _글막대카드로(doc, 알림, 먼저=False):
    """값이 수가 아닌 가로막대(값 칸에 'B→A'·'→'·'정부 탄소중립 투자 확대' 같은 글) → 카드('라벨 값' 항목).
    '26-09-29 bench13 W s7: 서버 약한 모델이 성과·여건을 가로막대로 적고 값 칸에 글을 넣어 초안 5벌이 모두
    '형식이 number' hard 로 막혔다(되시도 5회 소진). 막대로 그릴 수 없는 글이라 카드가 뜻에 맞다 — 행이 2~5개이고
    '라벨 값'이 30자 안이고 글 값이 행의 과반일 때만 바꾼다(아니면 게이트가 막게 둔다)."""
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict) or not isinstance(장.get("칸"), list):
            continue
        그릇들 = [(장["칸"], f"장.{i}.칸")] + [(c["칸"], f"장.{i}.칸.{k}.칸") for k, c in enumerate(장["칸"])
                                          if isinstance(c, dict) and c.get("부품") == "세로묶음" and isinstance(c.get("칸"), list)]
        for 그릇, 앞 in 그릇들:
            for k, c in enumerate(그릇):
                if not (isinstance(c, dict) and c.get("부품") == "가로막대" and isinstance(c.get("행"), list)):
                    continue
                행 = [r for r in c["행"] if isinstance(r, dict)]
                글값 = [r for r in 행 if isinstance(r.get("값"), str) and r["값"].strip()]
                if 먼저:
                    # 스키마 고침(_고침) 앞 — '152%'·'85점'·'5건' 은 아직 글이다. 수+단위 꼴은 글로 치지 않되, 단위가 행마다
                    # 다르고(한 막대 축에 못 올린다) 수 아닌 글('A')이 섞였으면 카드로 바꾼다(round3 fixup EXAONE s7: 고침이
                    # 단위를 떼어 'A' 한 행만 글로 남아 과반 규칙을 비껴갔고 '형식이 number' hard 로 두 판이 막혔다)
                    꼴 = [re.fullmatch(r"\s*[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*([^\d\s]{0,4})\s*", str(r.get("값")))
                         if isinstance(r.get("값"), str) else None for r in 행]
                    맨글 = [r for r, m in zip(행, 꼴) if isinstance(r.get("값"), str) and r["값"].strip() and not m]
                    단위들 = {m.group(1) for m in 꼴 if m}
                    if not (맨글 and len(단위들) >= 2) or not 2 <= len(행) <= 5:
                        continue
                    글값 = 맨글
                # 글 값이 행의 과반일 때만 — 한두 행만 글이면 막대 차트가 맞고 그 행을 고칠 일이다(게이트가 막는다,
                # round2 '정규화.수둘은그대로')
                elif len(글값) * 2 <= len(행) or not 2 <= len(행) <= 5:
                    continue
                단위 = str(c.get("단위") or "")
                항목 = []
                for r in 행:
                    v = r.get("값")
                    v = (_수글로(v) + 단위) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v or "").strip()
                    항목.append(f"{str(r.get('라벨') or '').strip()} {v}".strip())
                if any(not t or len(t) > 30 for t in 항목):
                    continue
                새 = {"부품": "카드", "제목": str(c.get("제목") or "주요 내용")[:20], "항목": 항목}
                그릇[k] = 새
                알림.append(f"{앞}.{k}: 값이 글인 가로막대를 카드로 바꿨다(막대로 그릴 수 없는 값 — {글값[0].get('값')!r})")


def 정규화(doc):
    """모양 정규화 — doc 을 제자리에서 고치고 알림(soft 글) 목록을 돌려준다. v2 문서가 아니면 아무것도 안 한다."""
    if not isinstance(doc, dict) or not v2인가(doc) or 판형오류(doc):
        return []
    알림 = []
    장들 = doc.get("장")
    if isinstance(장들, list):
        새장 = []
        for n, j in enumerate(장들):
            if isinstance(j, str):
                try:
                    풀 = json.loads(j)
                except ValueError:
                    풀 = None
                if isinstance(풀, dict):
                    알림.append(f"장.{n}: 글로 온 장(JSON)을 풀었다")
                    새장.append(풀)
                elif re.search(r"^\s*[\[{]|['\"]\s*:|:\s*[\[{]\s*$|^\S{1,12}['\"]?\s*:\s*\{?\s*$", j):
                    # JSON 조각('요지띠:{'·"유형':" · 끝 쉼표 하나로 글이 된 요청 장) = 초안이 중간에 끊긴 표지다. 빼고 넘기면
                    # 요청상자 없는 덱이 hard 0 으로 통과했다(round2 적대 검토 §3-E) → 그대로 두고 게이트가 막게 한다.
                    알림.append(f"!장.{n}: 초안이 중간에 끊겼다(JSON 조각 '{j.strip()[:24]}') — 이 장을 온전한 객체로 다시 쓴다"
                              "(배열을 닫은 뒤 객체를 먼저 닫지 않았나 본다)")
                    새장.append(j)
                else:
                    알림.append(f"장.{n}: 장이 객체가 아니라 뺐다('{j[:20]}')")
                continue
            새장.append(j)
        doc["장"] = 새장
    _구조고침(doc, 알림)
    뿌리 = 스키마()
    꼬리 = {"_거절": set()}
    _꼬리맞춤(doc, 알림, 꼬리["_거절"])
    _글막대카드로(doc, 알림, 먼저=True)
    새 = _고침(doc, 뿌리, 뿌리, "", 알림, 꼬리)
    doc.clear()
    doc.update(새)
    _요청금액넣기(doc, 알림)
    _글막대카드로(doc, 알림)
    # 목록 밖 아이콘(카드·항목타일의 아이콘은 골라 쓰는 꾸밈이다) — 빼고 알린다. round3 fixup EXAONE s7: '탄소' 아이콘
    # 하나로 마지막 두 판이 hard 로 막혀 생성이 실패했다(다른 hard 는 다 고친 판)
    아이콘 = set(아이콘들())

    def 아이콘걷기(o, 경로):
        if isinstance(o, dict):
            if "아이콘" in o and isinstance(o.get("아이콘"), str) and o["아이콘"] not in 아이콘 \
                    and o.get("부품") in ("카드", "항목타일"):
                알림.append(f"{경로}.아이콘: 목록에 없는 아이콘 '{o['아이콘']}' 를 뺐다")
                o.pop("아이콘")
            for k, v in o.items():
                아이콘걷기(v, f"{경로}.{k}" if 경로 else k)
        elif isinstance(o, list):
            for n, v in enumerate(o):
                아이콘걷기(v, f"{경로}.{n}")
    아이콘걷기(doc.get("장"), "장")
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict):
            continue
        for p, c in 칸들(장):
            if c.get("부품") == "가로막대" and not c.get("단위"):
                끝들 = {_수꼴.match(str(r.get("표시") or "")).group(2).strip() for r in c.get("행") or []
                       if isinstance(r, dict) and r.get("표시") and _수꼴.match(str(r["표시"])) and _수꼴.match(str(r["표시"])).group(2)}
                if len(끝들) == 1:
                    c["단위"] = 끝들.pop()
        # 막대 행 꼬리(표시)가 모두 같고 부품 단위가 비었으면 부품 단위로 올린다 / 사라진 강조 조각은 뺀다
        머리 = 장.get("머리") if isinstance(장.get("머리"), dict) else None
        if 머리 and isinstance(머리.get("강조"), list) and isinstance(머리.get("메시지"), str):
            남 = [k for k in 머리["강조"] if isinstance(k, str) and k in 머리["메시지"]]
            if len(남) > 2:
                # 장당 강조 ≤2곳(hard) — 앞 두 곳만 남긴다('26-09-29 bench13 W s7 초안 4: 강조 4곳으로 막힘)
                알림.append(f"장.{i}.머리.강조: {len(남)}곳 가운데 앞 두 곳만 남겼다({', '.join(남[2:])} 뺌)")
                남 = 남[:2]
            if len(남) != len(머리["강조"]):
                머리["강조"] = 남
                if not 남:
                    머리.pop("강조")
    for k, a in enumerate(알림):
        if a.startswith("~"):
            자리, 원, 말 = a[1:].split("|", 2)
            m = re.match(r"장\.(\d+)\.", 자리)
            if m and m.group(1).isdigit() and int(m.group(1)) < len(doc.get("장") or []):
                장 = doc["장"][int(m.group(1))]
                노 = 장.get("노트")
                if not isinstance(노, dict):
                    노 = {"말": 노} if isinstance(노, str) and 노 else {}
                    장["노트"] = 노
                노.setdefault("메모", [])
                if isinstance(노["메모"], list):
                    노["메모"].append(f"줄이기 전 원문: {원}")
            알림[k] = 말
    return 알림


# ── 자료 대조 — 약한 경로(서버 모델) 지어냄·해석 hard('26-09-29 bench13 ③④) ────────────────────────
# bench13 EXAONE 덱의 충실도 1.56 — 없는 목표치('목표 100%')·지어낸 분포 막대(대상 유형별 600·300·300)·지어낸 비교
# 기준('전년 대비')·과장('영구적 효율화 달성'). 교정(fabfix)은 채택 뒤 한 번뿐이라 막대·목표 칸 수치가 그대로 남았다.
# 그래서 약한 경로에서는 **값 칸**(지표타일·진행막대·막대 행·링·구성띠·표 칸·시점·출처)의 자료에 없는 수, 자료에 없는
# 날짜·기간·비교 기준, 판단·인과 말을 등록 전에 hard 로 되돌린다(웹앱이 사유를 되먹여 다시 쓰게 한다). 글 칸(머리·항목)의
# 수는 계산값(차이·합)일 수 있어 soft 로만. 금액은 원 단위로 바꿔 대 본다('240'+'백만원' = 자료 '2억 4천만 원').
_값칸 = frozenset({"값", "목표", "목표선", "수치", "금액", "표시", "시점", "기간", "출처", "이전", "이후"})
_기준말 = (("전년 대비", ("전년",)), ("작년 대비", ("작년", "전년")), ("지난해 대비", ("지난해", "전년", "작년")),
         ("전년도 대비", ("전년",)), ("전월 대비", ("전월",)), ("전분기 대비", ("전분기",)),
         ("상반기", ("상반기", "1~6월", "1월~6월")), ("하반기", ("하반기", "7~12월", "7월~12월")))
# 금액 단위 — '원'이 없어도 조·억·천만·백만은 금액이다('2.735'+'억' — round3 적대 검토 L06: '원'을 요구해 자료 금액을 hard 로
# 막았고, 메시지대로 하면 모델이 결재 숫자인 요청 금액을 지웠다). '만'·'천' 홀로는 '만 명'·'천 건'과 헷갈려 원이 있어야 한다
_금액단위re = re.compile(r"^\s*(?:(조|억|천만|백만|만|천)?\s*원|(조|억|천만|백만)\s*(?:$|/))")
# 값 칸이 아닌 글 칸 가운데 **비교 기준·규모 주장**이라 약한 경로 hard 로 올리는 자리(round3 적대 검토 J: 없는 목표치
# '목표 932대'가 드나드는 맥락 글·요청상자 규모·시점 행·수량목록 보조가 soft 로만 남았다)
_기준맥락 = ("목표", "전년", "이전", "평균")
_요청규모행 = ("규모", "시점", "기간", "금액", "예산", "대상", "수량", "물량")
_합계행re = re.compile(r"^\s*(?:합\s*계|소\s*계|총\s*계|계|총|평균|전체|누계)\s*$")
_꼬리 = ("[자료 대조] 값 칸은 자료 수치만 — 없는 목표·분포·비교값은 그 칸·행을 빼고(다 비면 부품·장째), "
       "계산한 값은 산출[]에 식과 함께")


def _자료글(doc, 원문=None):
    맥 = doc.get("_맥락") if isinstance(doc.get("_맥락"), dict) else {}
    t = 맥.get("의도") or doc.get("_요청") or 원문
    # 웹앱 _맥락.의도 는 앞 4,000자로 잘린다 — 원문(전문)이 더 길면 전문으로 대 본다(round3 적대 검토 ①)
    if isinstance(원문, str) and isinstance(t, str) and len(원문) > len(t) and 원문.strip().startswith(t.strip()[:200]):
        t = 원문
    return t if isinstance(t, str) and t.strip() else None


def _자리따라(doc, 어디):
    """'장.2.칸.0.행.1.값' → (그 값을 품은 dict, 가장 가까운 부품 dict)."""
    node, 부품, 품은 = doc, None, None
    for 조각 in 어디.split("."):
        품은 = node if isinstance(node, dict) else 품은
        if isinstance(node, dict) and node.get("부품"):
            부품 = node
        if isinstance(node, list) and 조각.isdigit() and int(조각) < len(node):
            node = node[int(조각)]
        elif isinstance(node, dict) and 조각 in node:
            node = node[조각]
        else:
            return 품은, 부품
    return 품은, 부품


def _부품경로(어디):
    """'장.2.칸.0.행.1.값' → '장.2.칸.0' (세로묶음 안이면 '장.2.칸.0.칸.1')."""
    m = re.match(r"^(장\.\d+(?:\.칸\.\d+)+)", 어디)
    return m.group(1) if m else 어디


def _표행(몸, 어디):
    """표 칸 경로('장.3.칸.0.행.1.2' 또는 '….행.1.2.글')면 (그 행 list) 아니면 None."""
    m = re.match(r"^(장\.\d+(?:\.칸\.\d+)+)\.행\.(\d+)\.\d+(?:\.글)?$", 어디)
    if not m:
        return None
    _, 부품 = _자리따라(몸, m.group(1) + ".행")
    if not (isinstance(부품, dict) and 부품.get("부품") == "표"):
        return None
    행 = (부품.get("행") or [])[int(m.group(2))] if int(m.group(2)) < len(부품.get("행") or []) else None
    return 행 if isinstance(행, list) else None


def _출처뺀글(원, v):
    """출처 글에서 수 v 가 든 괄호 한 덩이('…('26년 상반기)')를 뺀 글 — 괄호가 없으면 None."""
    v = str(v)
    for m in re.finditer(r"\s*[(（][^()（）]*[)）]", 원):
        if re.search(r"(?<!\d)'?" + re.escape(v.lstrip("'")) + r"(?!\d)", m.group(0)):
            남 = (원[:m.start()] + 원[m.end():]).strip()
            return 남 or None
    return None


def 출처고칠말(원, v, 자료=None):
    """출처 연도·수 hard 의 고칠 말 — 괄호째 뺀 글을 주거나, 뺄 괄호가 없으면 출처 키를 지우라고. 괄호를 뺀 이름도 자료
    밖이면(출처자료밖) 키를 지우라고 한다 — 예전엔 같은 장에 "출처를 "…"로 바꾼다"와 "키를 지운다"가 함께 나오거나,
    지어낸 이름('총무처 문서 관리 현황')을 남기라고 했다(r4 적대 검토 규칙 §5 D5)."""
    남 = _출처뺀글(원, v)
    # 괄호를 뺀 이름이 맞는 출처인가 — 자료가 있으면 출처지어냄(지어냈나 한 곳, W3), 없으면 예전처럼 일반 말만 본다
    if 남 and not (출처지어냄(남, 자료) if 자료 else 출처일반말(남, None)):
        return f"출처를 \"{남}\" 로 바꾼다(괄호의 연도·수를 지운다 — 자료에 없는 연도를 붙이지 않는다)"
    return "\"출처\" 키를 지운다(자료가 밝힌 이름·시점이 아니면 출처는 비워 둔다)"


def 출처비우기(doc, 자료):
    """약한 경로에서 출처 hard 가 두 회 연속 같을 때 새문서가 부른다(주관 판정 ⑦ — 확실한 꼴: 출처 칸을 비운다).
    자료에 없는 수가 든 출처·자료에 없는 일반 출처 말을 든 출처를 지우고 [(경로, 지운 글)] 을 돌려준다."""
    import 지어냈나 as F
    h, _ = 자료대조(doc, 자료, 약한경로=True)
    지울 = set()
    for x in h:
        m = re.match(r"^장\.([\d·]+)\.출처 ", x)
        if m:
            지울 |= {int(k) for k in m.group(1).split("·")}
    out = []
    for i in sorted(지울):
        장 = (doc.get("장") or [])[i] if i < len(doc.get("장") or []) else None
        if isinstance(장, dict) and isinstance(장.get("출처"), str):
            # 출처가 여럿인 칸('A 대장 · B 현황')에서 일부만 지었으면 지은 조각만 뺀다('26-09-30 주관 판정 X3 — 맞는 조각까지
            # 잃지 않게). 판정은 지어냈나.출처남길글(= _출처_지어냄인가 조각마다) 하나다.
            남 = F.출처남길글(장["출처"], 자료) if (isinstance(자료, str) and 자료.strip()) else None
            if 남 and 남 != 장["출처"]:
                옛 = 장["출처"]
                장["출처"] = 남
                남은조각 = {a for a, _ in F._출처조각들(남)}
                out.append((f"장.{i}.출처", " · ".join(a for a, _ in F._출처조각들(옛) if a not in 남은조각)))
                continue
            out.append((f"장.{i}.출처", 장.pop("출처")))
    return out


def 자료대조(doc, 자료, 약한경로=False):
    """(hard, soft) — 자료 글과 대 본 지어냄·해석. 약한경로면 값 칸 수·날짜·비교 기준·판단 인과를 hard 로,
    아니면 비교 기준만 soft 로(강한 경로의 수·날짜는 지어냈나검수·교정지시가 따로 본다). 자료 글이 없으면 ([], []).
    되먹임 모양(round3 적대 검토 ⑤): 같은 칸은 한 줄, 한 부품의 값 칸이 셋 이상 걸리면 부품 한 줄, 설명은 맨 앞에 한 번.
    자료 글이 4,000자 이상이면(웹앱 _맥락.의도 는 앞 4,000자에서 잘린다) 잘린 뒤 자료를 못 보므로 수·이름·말 대조를
    hard 대신 soft 로 둔다(게이트 ⑯과 같은 규칙 — 고칠 수 없는 hard 로 되시도 5회를 헛쓰지 않게)."""
    if not isinstance(자료, str) or not 자료.strip():
        return [], []
    G = 게이트()
    hard, soft = [], []
    잘림 = len(자료) >= 4000
    몸 = {k: v for k, v in doc.items() if not str(k).startswith("_")}
    # 새문서는 등록부 장르(genre)를 v2 검사 **뒤에** 싣는다 — genre 가 없으면 지어냈나.문서글 이 1p 옛 스키마 길로 가
    # 슬라이드 글을 하나도 못 모은다(초안 5벌 모두 0건으로 통과하는 것을 재현했다)
    몸["genre"] = "slides"
    if 약한경로:
        import 지어냈나 as F
        자료원 = G._원단위(자료)
        원수 = {v for _, v in F.수값들(자료)}
        더한숫자, _ = F.재기(자료, 몸)
        # 자료의 '월. 일.' 날짜('12. 1.~12. 19.') — 칸에 '12.1'로 옮기면 재기가 소수 12.1 로 읽어 '자료에 없는 숫자'로
        # 막았다(round3 EXAONE s5 초안 2·4·5: 신청 기간 시점 칸). 같은 (월, 일) 짝이 자료 날짜에 있으면 숫자로 치지 않는다.
        # 범위의 끝 날('12월 1일~19일'·'12. 1.~19.' → (12, 19))도 같은 달로 잇는다(round3 적대 검토 L07)
        자료날짜 = {(int(a), int(b)) for a, b in re.findall(r"(?<![\d.])(\d{1,2})\s*\.\s*(\d{1,2})\s*\.", 자료)}
        자료날짜 |= {(int(a), int(b)) for a, b in re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", 자료)}
        자료날짜 |= {(int(a), int(c)) for a, _b, c in re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*[~∼\-–]\s*(\d{1,2})\s*일", 자료)}
        자료날짜 |= {(int(a), int(c)) for a, _b, c in
                 re.findall(r"(?<![\d.])(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*[~∼]\s*(\d{1,2})\s*\.(?!\s*\d)", 자료)}
        값걸림 = {}                     # 어디 → [값] (값 칸 hard 후보)
        출처걸림 = {}                   # 값 → [출처 경로]
        본 = set()
        for 어디, v, 곁 in 더한숫자:
            if ".노트" in 어디 or ".산출." in f"{어디}." or (어디, v) in 본:
                continue                                       # 산출 등록 칸은 화면 글이 아니다(L04)
            본.add((어디, v))
            날 = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", str(v))
            if 날 and (int(날.group(1)), int(날.group(2))) in 자료날짜:
                continue
            조각 = 어디.split(".")
            끝 = next((x for x in reversed(조각) if not x.isdigit()), "")
            품은, 부품 = _자리따라(몸, 어디)
            단위 = str((품은 or {}).get("단위") or (부품 or {}).get("단위") or "")
            m = _금액단위re.match(단위) if 끝 in ("값", "금액") else None
            try:
                수 = float(str(v).replace(",", ""))
            except ValueError:
                수 = None
            자릿수 = None
            if m and 수 is not None:
                배키 = m.group(1) or m.group(2)
                배 = G._배율.get(배키, 1.0) if 배키 else 1.0
                if any(abs(수 * 배 - w) <= max(1.0, 1e-6 * w) for w in 자료원):
                    continue                                   # 단위만 바꾼 자료 금액('240'+'백만원'·'2.735'+'억')
                # 자릿수만 틀린 금액('240'+'만원' ↔ 자료 2억 4천만 원) — 무엇이 틀렸는지 알려 준다(round3 EXAONE s5: '자료에
                # 없는 숫자 240' 만 받고 다섯 번 같은 값을 냈다)
                자릿수 = next((w for w in sorted(자료원) for k in (-4, -3, -2, -1, 1, 2, 3, 4)
                            if abs(수 * 배 * 10 ** k - w) <= max(1.0, 1e-6 * w)), None)
            보완 = 수 is not None and 0 < 수 < 100 and any(abs((100 - 수) - w) < 1e-9 for w in 원수) \
                and ("%" in 단위 or "%" in str(곁) or "%" in str((부품 or {}).get("제목") or "")
                     or (부품 or {}).get("부품") in ("구성띠", "비율링"))       # 100 − 자료 비율(나머지 몫)은 계산값
            # 반올림(자료 82.7 → 83·82.7 → 82.7%)은 지어냄이 아니다 — 자료 값을 알려 주고 soft(L05)
            반올림 = next((w for w in 원수 if 수 is not None and w != 수 and not float(w).is_integer()
                        and (abs(round(w) - 수) < 1e-9 or abs(round(w, 1) - 수) < 1e-9)), None)
            글 = f"{어디} 자료에 없는 숫자 {v}"
            # 글 칸 가운데 비교 기준·규모 주장 자리(J02·J06·J10·J11·J12) · 표 칸(합계·소계 행은 계산값이라 뺀다, J09)
            맥락종류 = (품은 or {}).get("종류") if 끝 == "글" and len(조각) >= 2 and 조각[-2] == "맥락" else None
            요청행 = 끝 == "내용" and (부품 or {}).get("부품") == "요청상자" \
                and any(x in str((품은 or {}).get("이름") or "") for x in _요청규모행)
            표행 = _표행(몸, 어디) if 끝 in ("행", "글") else None
            표칸 = 표행 is not None and not (표행 and _합계행re.match(G.글자(표행[0]) if isinstance(표행[0], (str, list)) else
                                                         str((표행[0] or {}).get("글") or "")))
            # 글 한 줄 맥락(비율링·표지 수치 '목표 936%')은 앞 낱말로 종류를 읽는다 · 선차트 가로축 눈금(지어낸 시점 '935년')도
            # 값 칸처럼 본다(J05·J06·J12)
            글맥락 = 끝 == "맥락" and re.match(r"\s*(?:목표|전년|이전|평균|작년|지난해|계획)", str(곁 or ""))
            가로축 = 끝 == "가로축" and (부품 or {}).get("부품") == "선차트"
            주장칸 = (맥락종류 in _기준맥락 or 요청행 or (끝 == "보조" and (부품 or {}).get("부품") == "수량목록") or 표칸
                   or bool(글맥락) or 가로축)
            if ".증감." in f".{어디}.":
                # 증감은 자료 두 값의 차이(계산값)라 hard 로 막지 않는다('26-09-29 round3 EXAONE s7 초안 2: 168→152·81→85 의
                # 차이 16·4 를 '자료에 없는 숫자'로 막았다) — 알리기만
                soft.append(글 + "(증감) — 자료 두 값의 차이인지 확인한다")
            elif 반올림 is not None:
                soft.append(f"{글} — 자료 값은 {반올림:g} 이다(반올림했으면 자료 값 그대로 쓰는 편이 낫다)")
            elif 잘림:
                soft.append(글 + " — 자료 글이 4,000자를 넘어 뒤쪽을 대 보지 못했다. 자료 수치인지 확인한다")
            elif 자릿수 is not None:
                자료글 = f"{자릿수 / 1e8:g}억 원" if 자릿수 >= 1e8 else f"{자릿수 / 1e4:,.0f}만 원"
                hard.append(f"{어디} 금액 {v}{단위} 의 자릿수가 자료와 다르다 — 자료 금액은 {자료글}이다. 값과 단위를 자료대로 "
                          f"맞춘다(예: 값 '{자릿수 / 1e8:g}' · 단위 '억원')" if 자릿수 >= 1e8 else
                          f"{어디} 금액 {v}{단위} 의 자릿수가 자료와 다르다 — 자료 금액은 {자료글}이다. 값과 단위를 자료대로 맞춘다")
            elif 끝 == "출처":
                출처걸림.setdefault(str(v), []).append(어디)
            elif (끝 in _값칸 or 주장칸) and not 보완:
                값걸림.setdefault(어디, []).append(str(v))
            else:
                soft.append(글 + "(글 칸) — 자료 수치를 옮기거나, 계산했으면 산출[]에 식과 함께 등록한다")
        # 같은 칸은 한 줄, 한 부품에서 값 칸 셋 이상이면 부품 한 줄(L03 — 행→부품→장 순으로 빼느라 4회가 걸렸다)
        부품별 = {}
        for 어디, vs in 값걸림.items():
            부품별.setdefault(_부품경로(어디), []).append((어디, vs))
        값줄 = []
        for 경로, 칸 in 부품별.items():
            _, 부품 = _자리따라(몸, 경로 + ".x")
            이름 = (부품 or {}).get("부품") or "부품"
            if len(칸) >= 3:
                값들 = " · ".join(dict.fromkeys(v for _, vs in 칸 for v in vs))
                값줄.append(f"{경로}({이름}) 값 칸 {len(칸)}곳({값들[:60]})이 자료에 없다 — 부품째 빼거나 자료 수치로 바꾼다")
            else:
                값줄 += [f"{어디} 자료에 없는 숫자 {' · '.join(dict.fromkeys(vs))}" for 어디, vs in 칸]
        if 값줄:
            hard += [_꼬리] + 값줄
        # 출처 — 같은 수를 여러 장 출처에 붙였으면 한 줄로(bench13 W s6 초안: 같은 설명 꼬리 다섯 줄이 되먹임 700자를 먹었다)
        # 되먹임은 무엇을 지울지 정확히 — bench14 EXAONE s2·s6 열 판이 '자료에 연도가 없으면 연도를 붙이지 않는다'를 받고도
        # 연도를 다시 붙였다(r4 진단 §6). 출처 글에서 그 수가 든 괄호(없으면 그 수)를 뺀 글을 고칠 값으로 준다.
        for v, 곳 in 출처걸림.items():
            자리 = 곳[0] if len(곳) == 1 else "장." + "·".join(x.split(".")[1] for x in 곳) + ".출처"
            원 = str((_자리따라(몸, 곳[0])[0] or {}).get("출처") or "")
            hard.append(f"{자리} 자료에 없는 숫자 {v} — " + 출처고칠말(원, v, 자료))
        밖출처 = []
        for i, 장 in enumerate(몸.get("장") or []):
            # 걸지 말지는 출처지어냄(지어냈나 한 곳, W3 '26-09-30) — 강한 경로 soft 와 같은 자. 출처일반말은 문구만 가른다
            if not (isinstance(장, dict) and 출처지어냄(장.get("출처"), 자료)):
                continue
            일반 = 출처일반말(장.get("출처"), 자료)
            if 일반:
                (soft if 잘림 else hard).append(
                    f"장.{i}.출처 '{str(장.get('출처'))[:30]}' 의 '{일반}' 은 자료에 없는 일반 출처 말이다 — 자료가 출처 이름을 "
                    "밝히지 않았으면 \"출처\" 키를 지운다")
            else:
                밖출처.append(i)
        # 자료가 출처 이름을 밝히지 않았는데 지어 붙인 출처('총무처 문서 관리 현황' — bench14 EXAONE s2 다섯 판 모두,
        # 주관 판정 ⑤ '약한 경로 hard') — 장마다 줄을 늘리지 않고 한 줄로
        if 밖출처 and not 잘림:
            hard.append("장." + "·".join(str(n) for n in 밖출처) + ".출처 자료가 출처를 밝히지 않았다 — 자료에 없는 출처 이름을 "
                        "지어 붙이지 않는다. 이 장들의 \"출처\" 키를 지운다")
        for g in F.검토하기(자료, 몸):
            if g.get("종류") == "월표현" and ".노트" not in str(g.get("어디")) and ".산출." not in f"{g.get('어디')}.":
                (soft if 잘림 else hard).append(f"{g.get('어디')} 자료에 없는 날짜·기간 '{str(g.get('값'))[:20]}' — 자료에 적힌 시점만 쓴다")
        for 자리, t, w in G.판단인과걸림(몸, 자료):
            if w == "완료":
                (soft if 잘림 else hard).append(f"{자리} '{t[:24]}' — 자료에 없는 '완료' 판단. 자료가 착수·진행이라 하면 그대로 적는다"
                                              "(상태는 '진행'·'예정', 글은 '착수'·'진행 중')")
            else:
                (soft if 잘림 else hard).append(f"{자리} '{t[:24]}' — 자료에 없는 판단·인과('{w}'). 자료의 사실·수치만 적는다")
    # 비교 기준·기간 — 걸린 칸의 경로와 글을 함께 알린다(round3 EXAONE s7: 장 번호만 받고 요청상자 '시점' 행의
    # ''27년 상반기' 를 다섯 번 되풀이했다)
    def 칸글(o, 경로):
        if isinstance(o, str):
            yield 경로, o
        elif isinstance(o, list):
            if o and all(isinstance(r, dict) and "t" in r for r in o):
                yield 경로, G.글자(o)
            else:
                for n, x in enumerate(o):
                    yield from 칸글(x, f"{경로}.{n}")
        elif isinstance(o, dict):
            for k, x in o.items():
                if k in ("노트", "출처", "산출") or k in G._열거키 or str(k).startswith("_"):
                    continue
                yield from 칸글(x, f"{경로}.{k}")
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict):
            continue
        본말 = set()
        for 경로, t in 칸글(장, f"장.{i}"):
            for 말, 같은 in _기준말:
                if 말 in t and 말 not in 본말 and not any(x in 자료 for x in 같은):
                    본말.add(말)
                    (hard if 약한경로 and not 잘림 else soft).append(
                        f"{경로} '{t[:24]}' 자료에 없는 비교 기준·기간 '{말}' — 자료가 말한 기준·기간만 붙인다(없으면 그 말이나 그 행을 뺀다)")
    return hard, soft


def 검사(doc, 약한모델=False, 원문=None, 약한경로=False):
    """(hard 글 목록, soft 글 목록) — 모양 정규화 → 조립 게이트 그대로 + 신설 soft. 새문서가 등록 전에 부른다.
    정규화는 doc 을 제자리에서 고친다(새문서는 고친 doc 을 등록한다) — 고친 내용은 soft 로 알린다.
    정규화가 **고치지 않기로 한 까닭**('!' 알림 — 배율 꼬리 섞임·단위 충돌·끊긴 장)은 hard 앞머리에 싣는다.
    원문(플러그인 새문서의 자료 글)을 주면 문서에 _맥락·_요청이 없을 때 게이트에만 _요청으로 빌려 준다 — 요청 장수(⑪)와
    판단 숫자 자료 대조(⑯)가 웹앱(_맥락)에서만 돌았다(round2 적대 검토 규칙 §6). 등록되는 doc 엔 남기지 않는다."""
    판 = 판형오류(doc)
    if 판:
        return [f"(최상위): {판}"], []
    알림 = 정규화(doc)
    거절 = [a[1:] for a in 알림 if a.startswith("!")]
    고친 = [f"(모양 정규화) {a}" for a in 알림 if not a.startswith("!")]
    빌림 = isinstance(원문, str) and 원문.strip() and not doc.get("_맥락") and not doc.get("_요청")
    if 빌림:
        doc["_요청"] = 원문.strip()
    try:
        hard, soft = 게이트().검사(doc, 약한모델)
        if 거절:
            hard = [f"(모양 정규화 안 함) {a}" for a in 거절] + list(hard)
        soft = 고친 + list(soft)
        # 자료 대조(bench13 ③④) — 약한 경로는 값 칸 지어냄·날짜·비교 기준·판단 인과를 hard 로(게이트의 판단·인과 soft 는
        # 같은 사실이라 뺀다), 강한 경로는 비교 기준만 soft 로 더한다. 모양이 틀린 초안에도 약한 경로 hard 는 함께 싣는다 —
        # 되시도가 5회뿐이라 모양을 고친 다음 회차에야 지어냄을 알려 주면 한 회를 버린다(bench13 W 초안 19벌 재현)
        대h, 대s = 자료대조(doc, _자료글(doc, 원문), 약한경로)
        if hard and (거절 or 게이트().스키마검사(doc)):
            # 모양(스키마)이 틀린 문서는 신설 soft 가 엉뚱한 자리를 짚는다 — 모양부터 고치게 한다
            return list(hard) + (대h if 약한경로 else []), []
        추가 = 추가소프트(doc, list(hard) + list(soft), 약한모델, 약한경로)
        if 약한경로 and 대h:
            soft = [s for s in soft if "판단·인과" not in s]
            # 게이트 ⑯ 요청 금액 줄과 자료대조의 자릿수 줄이 같은 칸이면 고칠 값을 알려 주는 자료대조 줄만 둔다
            자릿 = {m.group(1) for x in 대h for m in [re.match(r"^(장\.\d+(?:\.칸\.\d+)+)\.금액(?:\.값)? 금액 ", x)] if m}
            hard = [x for x in hard if not any(x.startswith(p + ".금액 ") for p in 자릿)]
        hard = list(hard) + 대h
        soft = list(soft) + 대s
    finally:
        if 빌림:
            doc.pop("_요청", None)
    # 이미 = 조립 게이트 hard+soft — 게이트가 이미 알린 사실(차트 강조 계열 등)을 두 번 싣지 않는다
    return list(hard), list(soft) + [f"{자리} {말}" for _, 자리, 말 in 추가]


def 소프트규칙(doc):
    """문체검사(build/stylelint.py doc_level_checks) 용 soft — {rule, hit, msg, text}.
    v2 문서면 신설 soft(조립 게이트 soft 는 조립 로그가 이미 싣는다), 옛 문서면 옛덱소프트."""
    if not isinstance(doc, dict):
        return []
    if v2인가(doc):
        if 판형오류(doc):
            return []
        try:
            이미 = 게이트().검사(doc)[0]
        except Exception:
            이미 = []
        return [{"rule": 규칙, "hit": 자리, "msg": 말, "text": ""} for 규칙, 자리, 말 in 추가소프트(doc, 이미)]
    return 옛덱소프트(doc)


def 옛덱소프트(doc):
    """옛 레이아웃 문서(판형 없음)에 거는 신설 soft 3종 — 규칙은 있었는데 게이트가 없어 무시됐던
    것(해부 S3: 타임라인 '하반기 → 10월 → 연말')과 막대 2개·맥락 없는 큰숫자."""
    out = []
    for i, s in enumerate(doc.get("슬라이드") or []):
        if not isinstance(s, dict):
            continue
        lo = s.get("레이아웃")
        if lo == "타임라인":
            시점들 = [x.get("시점") for x in s.get("단계") or [] if isinstance(x, dict)]
            for 앞, 뒤 in 시점역행(시점들):
                out.append({"rule": "W-타임라인순서", "hit": f"슬라이드.{i}",
                            "msg": f"시점 '{뒤}' 가 앞 시점 '{앞}' 보다 이르다 — 시간 순서대로(정본 구성.타임라인_순서)",
                            "text": ""})
        if lo == "도식":
            fg = s.get("도식") if isinstance(s.get("도식"), dict) else {}
            if fg.get("type") in ("bar", "hbar"):
                시점 = fg.get("시점") if isinstance(fg.get("시점"), list) else []
                계열 = fg.get("계열") if isinstance(fg.get("계열"), list) else []
                if len(시점) == 2 and len(계열) <= 1:
                    out.append({"rule": "W-막대2개", "hit": f"슬라이드.{i}",
                                "msg": "막대 2개짜리 차트 — 두 값의 대비는 큰숫자(전·후)가 낫다", "text": ""})
        if lo == "큰숫자":
            for j, m in enumerate(s.get("지표") or []):
                if isinstance(m, dict) and str(m.get("값") or "").strip() and not str(m.get("변화") or "").strip():
                    out.append({"rule": "W-맥락없는큰숫자", "hit": f"슬라이드.{i}.지표.{j}",
                                "msg": "큰숫자에 비교 맥락(전년·목표·평균 대비 변화)이 없다", "text": ""})
    return out


# ── 지시문 조각(workspace/api.py _지시문조립 이 부른다) ───────────────────────


def _참조(뿌리, ref):
    node = 뿌리
    for p in ref[2:].split("/"):
        node = node[p]
    return node


def _슬롯말(이름, s, 뿌리, 깊이=0):
    """한 슬롯 스키마 → 짧은 글. 예: '라벨≤15' · '맥락{*종류: 전년|이전, *글≤24}' · '항목[2~5]: ≤30'."""
    if "$ref" in s:
        if s["$ref"].split("/")[-1] == "런배열":
            return f"{이름}(글 또는 런[])"
        return _슬롯말(이름, _참조(뿌리, s["$ref"]), 뿌리, 깊이)
    if "oneOf" in s:
        글상한 = s.get("x-글자상한")
        if 글상한:
            return f"{이름}≤{글상한}(글 또는 런[])"
        말들 = [_슬롯말("", b, 뿌리, 깊이 + 1).strip() for b in s["oneOf"]]
        return f"{이름}(" + " 또는 ".join(x for x in 말들 if x) + ")"
    if "enum" in s:
        if set(s["enum"]) == set(아이콘들()):
            return f"{이름}: 아이콘 목록 중 하나"
        return f"{이름}: {'|'.join(map(str, s['enum']))}"
    if "const" in s:
        return f"{이름}={s['const']}"
    t = s.get("type")
    if t == "string":
        return f"{이름}≤{s['maxLength']}" if "maxLength" in s else f"{이름}(글)"
    if t in ("number", "integer"):
        범 = ""
        if "minimum" in s or "maximum" in s:
            범 = f" {s.get('minimum', '')}~{s.get('maximum', '')}"
        return f"{이름}(수{범})"
    if t == "array":
        개 = f"[{s.get('minItems', 0)}~{s.get('maxItems', '')}]"
        안 = _슬롯말("", s.get("items") or {}, 뿌리, 깊이 + 1).strip().lstrip(":").strip()
        return f"{이름}{개}" + (f": {안}" if 안 else "")
    if t == "object" and 깊이 < 4:
        req = set(s.get("required") or [])
        속 = [(("*" if k in req else "") + _슬롯말(k, v, 뿌리, 깊이 + 1)) for k, v in (s.get("properties") or {}).items()]
        return f"{이름}{{" + ", ".join(속) + "}"
    return 이름


def 부품슬롯글(이름):
    """부품 하나의 슬롯 요약 한 줄(* = 필수). 온톨로지 구성.부품_목록_v2.<이름>.슬롯 과 같아야 한다
    (test/r16_slides16a.py 가 대조한다 — 스키마가 바뀌면 온톨로지 문구도 같이 바꾼다)."""
    뿌리 = 스키마()
    s = 뿌리["$defs"]["부품_" + 이름]
    # x-생성필수 — 초안에는 늘 적되 스키마 필수는 아닌 칸(인용 말한이, fixup4 G7)도 '*'로 보인다(모델 지시·온톨로지 슬롯 문구는 그대로)
    req = set(s.get("required") or []) | set(s.get("x-생성필수") or [])
    조각 = []
    for k, v in (s.get("properties") or {}).items():
        if k in ("부품", "폭"):
            continue
        조각.append(("*" if k in req else "") + _슬롯말(k, v, 뿌리))
    return " · ".join(조각)


def 모양지시(약한모델=False):
    """[v2 문서 모양] 블록 줄들. 강한 모델은 부품 슬롯을 규칙 칸(구성.부품_목록_v2)에서 읽으니 여기선
    뼈대만, 약한 모델은 부분집합의 슬롯까지 싣는다(규칙 칸이 6,000자에서 잘릴 수 있다)."""
    부분 = 약한모델부분집합()
    배치 = 스키마().get("x-기본배치") or {}
    줄 = ["", "[v2 문서 모양 — 부품 트리 JSON. 모델은 이 JSON 만 쓴다. 좌표·색·글자 크기·HTML·CSS·클래스 이름은 "
         "쓸 자리가 없다(조립기가 그린다). 모르는 키를 쓰면 게이트가 막는다]",
         '· 최상위: {"판형":"v2"(필수), "목적":"보고|설득|설명"(필수), "제목"(≤40, 필수), "장":[…](3~17, 필수), '
         '"부제"(≤40), "발표정보":{기관,부서,회의,일자,발표자}(자료에 있는 것만), "프리셋":"data|briefing|keynote"(기본 data, briefing 은 청할 때만), '
         '"밀도":"발표|보고|배포"(기본 보고), "머리변형"(기관 선호, 보통 뺀다), "filename", "plan_id"}',
         ('· 장: {"유형"(필수), "머리":{"라벨"≤16,"메시지"≤40,"강조":[메시지 안 부분 문자열, ≤2]}, '
          '"요지띠":{"라벨"2~5자,"메시지"≤40}, "출처"≤60(자료가 밝힌 이름·시점만), "노트":{"말":발표자 말,"메모":[작성 메모]}, '
          '"산출":[{"값":화면 글 그대로,"식":계산식}], "칸":[부품…](1~6)} — 배열(칸·항목·행)은 그 객체의 맨 끝 키로 쓴다'
          if 약한모델 else     # 배열뒤로 docstring — 배열 뒤 키 자리에서 중괄호를 먼저 닫는 깨짐을 피한다
          '· 장: {"유형"(필수), "머리":{"라벨"≤16,"메시지"≤40,"강조":[메시지 안 부분 문자열, ≤2]}, "칸":[부품…](1~6), '
          '"요지띠":{"라벨"2~5자,"메시지"≤40}, "출처"≤60(자료가 밝힌 이름·시점만 — 없으면 키를 뺀다), '
          '"산출":[{"값":화면 글 그대로,"식":계산식}], "노트":{"말":발표자 말,"메모":[작성 메모]}'
          ', "리드"(≤40 또는 {앞,뒤}), "밀도"(장별 덮어쓰기)}'),
         '· 칸 = {"부품":"이름", …슬롯} ' + ("— 폭·세로묶음·런 배열은 쓰지 않는다(조립기 기본 배치)" if 약한모델 else
                                        '또는 {"부품":"세로묶음","폭":n,"칸":[부품 2~3]}. "폭"(12열 중 칸 수)은 전부 적거나 전부 뺀다 — 줄마다 합 12, 2줄까지'),
         ]
    유형목록 = 부분["유형"] if 약한모델 else 유형들()
    줄.append("· 장 유형(이 이름만): " + " · ".join(유형목록))
    for 유 in 유형목록:
        허 = (배치.get(유) or {}).get("허용")
        if isinstance(허, list):
            허 = [x for x in 허 if (not 약한모델) or x in 부분["부품"]]
            줄.append(f"    {유}: 부품 {' · '.join(허)}")
    줄.append("    표지: {\"유형\":\"표지\",\"표지\":{태그,부제" + ("" if 약한모델 else ",수치{라벨,값,단위,맥락}") + "}} · 마무리: "
              "{\"유형\":\"마무리\",\"마무리\":{문구,부문구,문의{부서,연락처}}} — 표지·마무리엔 머리·칸이 없다"
              + ("" if 약한모델 else " · 간지: {간지:{번호,제목,목록}} · 목차: {목차:{항목[3~7]}}"))
    줄.append("· 아이콘 목록: " + " · ".join(아이콘들()) + " — 이 밖의 이름은 쓰지 않는다. 상태 목록: "
              + " · ".join(상태들()) + " — 자료가 상태를 말할 때만 붙인다")
    if 약한모델:
        줄.append("· 부품(이 이름만, * = 필수 슬롯):")
        for n in 부분["부품"]:            # 약한 모델은 런 배열을 쓰지 않는다 — '(글 또는 런[])' 을 알리지 않는다(검토)
            줄.append(f"    {n}: {부품슬롯글(n).replace('(글 또는 런[])', '')}"
                     # EXAONE 이 짝카드를 왼쪽만·오른쪽만 둘로 나눠 쓰거나 '짝'에 항목 목록을 달았다(s2c·s2d·fixup s2 초안 4/5)
                     + (" — 왼·오른을 한 부품에 함께 쓴다(둘로 나누지 않는다). 줄 2개 이상이면 변형 '짝'+줄, "
                        "아니면 변형 '대비'+왼항목·오른항목" if n == "짝카드" else ""))
    else:
        줄.append("· 부품 슬롯은 위 규칙 칸 구성.부품_목록_v2 의 '슬롯'(* = 필수)을 글자 그대로 따른다. "
                  "런 배열 [{\"t\":글,\"역할\":\"강조|수치|단위|약하게\"}] 은 적힌 그대로 이어 붙인다(띄어쓰기는 t 안에).")
    return 줄


def 배열뒤로(o):
    """객체마다 배열 값 키를 맨 뒤로 옮긴 사본(값·중첩은 그대로, 키 순서만) — 약한 모델 본보기용.

    '26-09-29 round2 ⑱ 실측: EXAONE(JSON 모드) 슬라이드 초안이 깨진 사례 중 사례은 배열을 닫은 뒤 같은 객체에 키가
    더 올 자리(칸 뒤 요지띠·출처, 왼항목 뒤 오른제목)에서 중괄호를 하나 먼저 닫았다(`]}]},"요지띠:{"`). 그 자리는
    배열 원소 자리라 문법이 콜론을 막아 키가 글 조각이 되고, 그 뒤로는 빈칸만 허락돼 상한(4000 토큰·약 75초)까지
    헛돌았다. 배열을 객체의 끝 키로 두면 배열을 닫은 뒤 곧바로 그 객체를 닫게 된다."""
    if isinstance(o, list):
        return [배열뒤로(x) for x in o]
    if isinstance(o, dict):
        return {k: 배열뒤로(v) for k, v in sorted(o.items(), key=lambda kv: isinstance(kv[1], list))}
    return o


def 약한본보기(덱):
    """약한 본보기에서 예시 값이 그대로 새는 자리를 뺀다 — 마무리 부문구('다음 보고: '27년 1월 설치 결과')를 서버 약한
    모델이 글자 그대로 옮겨, 자료에 없는 날짜로 hard 에 걸린 초안이 되풀이됐다('26-09-29 round3 EXAONE s7 초안 2·4).
    다음 일정은 자료에 있을 때만 쓰는 슬롯이라 본보기에 두지 않는다(모양 줄 '마무리: {마무리:{문구,부문구,문의}}' 는 그대로)."""
    덱 = copy.deepcopy(덱)
    for j in 덱.get("장") or []:
        if isinstance(j, dict) and j.get("유형") == "마무리" and isinstance(j.get("마무리"), dict):
            j["마무리"].pop("부문구", None)
        # 요청상자 '시점' 행('27년 1월)도 같은 꼴로 샜다 — round3 fixup EXAONE s7 두 판 아홉 초안 가운데 여덟이 자료에 시점이
        # 없는 요청에 ''27년 상반기' 행을 지어 붙였다. 시점은 자료에 있을 때만 쓰는 행이라 본보기에서 뺀다
        # 출처의 연도 괄호('총무팀 물품 대장('26년 3~8월)')도 같은 꼴로 샜다 — bench14 EXAONE s2·s6 초안 열 판이 모두 자료에
        # 연도가 없는데 "부서 + 문서종류 + ('26년 …)" 꼴 출처를 붙여 출처 연도 hard 에 걸렸다(r4 진단 §6). 이름만 남긴다
        if isinstance(j, dict) and isinstance(j.get("출처"), str):
            남 = re.sub(r"\s*[(（][^()（）]*\d[^()（）]*[)）]", "", j["출처"]).strip()
            if 남:
                j["출처"] = 남
            else:
                j.pop("출처")
        for c in (j.get("칸") or []) if isinstance(j, dict) else []:
            if isinstance(c, dict) and c.get("부품") == "요청상자" and isinstance(c.get("행"), list):
                c["행"] = [r for r in c["행"] if not (isinstance(r, dict) and r.get("이름") == "시점")] or c["행"]
    return 덱


def 본보기지시(약한모델=False):
    """[본보기] 줄들 — 합성 본보기(○○공사)를 줄여 싣는다. 값은 베끼지 말라고 못박는다."""
    b = 본보기()
    if 약한모델:
        덱 = 배열뒤로(약한본보기(b["약한"]))
        고른 = 덱["장"]
    else:
        덱 = b["강한"]
        # 축약 — 부품 조합이 서로 다른 8장(표지·한눈에보기·데이터(세로묶음)·표·비교·일정·요청·마무리).
        고른 = [덱["장"][n] for n in (0, 1, 2, 6, 7, 8, 9, 10) if n < len(덱["장"])]   # 10 = 마무리(보고: 요약·다음 일정)
    머리 = {k: v for k, v in 덱.items() if k != "장" and not str(k).startswith("_")}
    글 = json.dumps(머리, ensure_ascii=False, separators=(",", ":"))[:-1] + ',"장":[\n'
    글 += ",\n".join(" " + json.dumps(j, ensure_ascii=False, separators=(",", ":")) for j in 고른)
    글 += "\n]}"
    return ["", "[본보기 — 합성 원고(○○공사, 지어낸 수치)로 만든 모양 본보기다. **키·중첩·부품 고르는 법만** "
            "따르고 기관·수치·문장은 한 글자도 베끼지 마라 — 값은 사용자 자료로 새로 채운다"
            + (f". 장 수는 본보기({len(고른)}장)가 아니라 위 '장수:' 줄을 따른다" if 약한모델 else ". 8장만 줄여 실었다") + "]", 글]


def 돌려줄것(약한모델=False):
    return ["", "[돌려줄 것 — JSON 하나만, 다른 말 없이]",
            '위 v2 모양의 문서 하나: {"판형":"v2","목적":…,"제목":…,"장":[…]}. 최상위 "슬라이드"·"표지" 키(옛 모양)는 '
            "쓰지 않는다 — 섞으면 게이트가 막는다.",
            "생략 가능(시스템이 채운다) — filename(비우면 제목에서 자동 생성), genre. **plan_id 는 생략할 수 "
            "없다** — 승인된 빌드플랜의 id 를 반드시 채워라."]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    doc = json.load(open(args[0], encoding="utf-8"))
    docs = doc if isinstance(doc, list) else [doc]
    나쁨 = 0
    for d in docs:
        hard, soft = 검사(d, 약한모델="--약한모델" in sys.argv)
        print(f"== {d.get('filename') or d.get('제목') or '?'}: hard {len(hard)} · soft {len(soft)}")
        for h in hard:
            print("  HARD", h)
        for s in soft:
            print("  soft", s)
        나쁨 += 1 if hard else 0
    return 1 if 나쁨 else 0


if __name__ == "__main__":
    sys.exit(main())
