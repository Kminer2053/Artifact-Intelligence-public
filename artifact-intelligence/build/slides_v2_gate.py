#!/usr/bin/env python3
"""슬라이드 v2(부품 트리) 문서 게이트 — 스키마 + 스키마로 못 적는 의미 규칙.

판형 "v2" 문서만 본다(옛 레이아웃 13종 문서는 assemble_slides.gate_check 가 그대로 본다).
정본 모양: build/slides_v2.schema.json(JSON Schema 2020-12, '26-09-28 설계 v0.1 을 옮긴 것).
jsonschema 패키지가 배포 환경에 없어서, 스키마가 실제로 쓰는 낱말(type·enum·const·required·
properties·additionalProperties·patternProperties·items·min/max·oneOf·anyOf·allOf·if/then/else·
not·$ref)만 읽는 작은 검사기를 여기 둔다. 그 밖의 낱말이 스키마에 생기면 검사기가 알린다
(모르는 규칙을 조용히 통과시키지 않는다).

hard 는 조립을 막고, soft 는 경고만 한다. 1단계 흠(제작 메모 각주 · '산출' 칩 과다 · 빈 카드 ·
건의 중복 · 같은 수치 반복 · 연차 막대 값순)은 여기 규칙과 조립기 배치로 막는다.
사용: python3 build/slides_v2_gate.py 문서.json [--약한모델]
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
_스키마 = None

_아는낱말 = {"$schema", "$id", "title", "description", "type", "properties", "const", "enum", "default",
          "minLength", "maxLength", "additionalProperties", "items", "$ref", "minItems", "maxItems",
          "patternProperties", "required", "$defs", "oneOf", "allOf", "if", "then", "else", "not",
          "anyOf", "minimum", "maximum", "examples"}


def 스키마():
    global _스키마
    if _스키마 is None:
        _스키마 = json.load(open(os.path.join(BASE, "slides_v2.schema.json"), encoding="utf-8"))
    return _스키마


# ── 작은 JSON Schema 검사기 ─────────────────────────────────────────────
def _형(v, t):
    if t == "string":
        return isinstance(v, str)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "object":
        return isinstance(v, dict)
    if t == "array":
        return isinstance(v, list)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "null":
        return v is None
    return False


def _풀기(sch, 뿌리):
    while isinstance(sch, dict) and "$ref" in sch:
        ref = sch["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"모르는 $ref {ref}")
        node = 뿌리
        for 조각 in ref[2:].split("/"):
            node = node[조각]
        sch = node
    return sch


def _검(v, sch, 뿌리, 자리, 오류):
    sch = _풀기(sch, 뿌리)
    if not isinstance(sch, dict) or not sch:
        return
    for k in sch:
        if not k.startswith("x-") and k not in _아는낱말:
            오류.append((자리, f"검사기가 모르는 스키마 낱말 '{k}' — slides_v2_gate.py 를 넓혀라"))
    if "type" in sch:
        ts = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_형(v, t) for t in ts):
            오류.append((자리, f"형식이 {'/'.join(ts)} 이어야 한다"))
            return
    if "const" in sch and v != sch["const"]:
        오류.append((자리, f"값이 {sch['const']!r} 이어야 한다"))
    if "enum" in sch and v not in sch["enum"]:
        오류.append((자리, f"{v!r} 는 고를 수 없다 — {', '.join(map(str, sch['enum']))} 가운데 하나"))
    if isinstance(v, str):
        if "minLength" in sch and len(v) < sch["minLength"]:
            오류.append((자리, "비어 있다" if not v or sch["minLength"] <= 1 else f"{len(v)}자 — {sch['minLength']}자 이상"))
        if "maxLength" in sch and len(v) > sch["maxLength"]:
            오류.append((자리, f"{len(v)}자 — {sch['maxLength']}자 이하"))
    if _형(v, "number"):
        if "minimum" in sch and v < sch["minimum"]:
            오류.append((자리, f"{v} < 최소 {sch['minimum']}"))
        if "maximum" in sch and v > sch["maximum"]:
            오류.append((자리, f"{v} > 최대 {sch['maximum']}"))
    if isinstance(v, list):
        if "minItems" in sch and len(v) < sch["minItems"]:
            오류.append((자리, f"{len(v)}개 — {sch['minItems']}개 이상"))
        if "maxItems" in sch and len(v) > sch["maxItems"]:
            오류.append((자리, f"{len(v)}개 — {sch['maxItems']}개 이하"))
        if "items" in sch:
            for n, x in enumerate(v):
                _검(x, sch["items"], 뿌리, f"{자리}.{n}", 오류)
    if isinstance(v, dict):
        props = sch.get("properties") or {}
        pats = sch.get("patternProperties") or {}
        for r in sch.get("required") or []:
            if r not in v:
                오류.append((자리, f"'{r}' 가 없다"))
        for k, x in v.items():
            if k in props:
                _검(x, props[k], 뿌리, f"{자리}.{k}" if 자리 else k, 오류)
            elif any(re.search(p, k) for p in pats):
                continue
            elif sch.get("additionalProperties") is False:
                오류.append((자리 or "(최상위)", f"모르는 키 '{k}'"))
    for s in sch.get("allOf") or []:
        _검(v, s, 뿌리, 자리, 오류)
    if "if" in sch:
        if not _통과(v, sch["if"], 뿌리):
            if "else" in sch:
                _검(v, sch["else"], 뿌리, 자리, 오류)
        elif "then" in sch:
            _검(v, sch["then"], 뿌리, 자리, 오류)
    if "not" in sch and _통과(v, sch["not"], 뿌리):
        오류.append((자리, "허용하지 않는 모양(이 유형에 둘 수 없는 키가 있다)"))
    if "anyOf" in sch and not any(_통과(v, s, 뿌리) for s in sch["anyOf"]):
        오류.append((자리, "어느 모양에도 맞지 않는다"))
    if "oneOf" in sch and isinstance(v, list) and all(isinstance(r, dict) for r in v):
        # 런 배열이 글 갈래의 글자 상한을 우회하지 못하게 — 조각 글을 합쳐 같은 상한으로 잰다
        # ('26-09-28 적대 검토 렌더 M7: 40자 요지띠가 런 8×60 = 480자까지 통과했다).
        상한 = [_풀기(b, 뿌리).get("maxLength") for b in sch["oneOf"] if _풀기(b, 뿌리).get("type") == "string"]
        상한 = [m for m in 상한 if isinstance(m, int)]
        합 = sum(len(str(r.get("t", ""))) for r in v)
        if 상한 and 합 > max(상한):
            오류.append((자리, f"런 글 합 {합}자 — {max(상한)}자 이하(문자열로 적을 때와 같은 상한)"))
    if "oneOf" in sch:
        맞음 = [s for s in sch["oneOf"] if _통과(v, s, 뿌리)]
        if not 맞음:
            갈래 = _부품갈래(v, sch["oneOf"], 뿌리)
            if 갈래 is not None:                  # 부품 이름이 맞는 갈래의 오류를 그대로 보여 준다
                _검(v, 갈래, 뿌리, 자리, 오류)
            elif isinstance(v, dict) and "부품" in v:
                오류.append((자리, f"모르는 부품 '{v.get('부품')}'"))
            else:
                오류.append((자리, "글(문자열) 또는 정해진 모양이어야 한다"))


def _부품갈래(v, 갈래들, 뿌리):
    if not isinstance(v, dict) or "부품" not in v:
        return None
    for s in 갈래들:
        r = _풀기(s, 뿌리)
        if "oneOf" in r:
            안 = _부품갈래(v, r["oneOf"], 뿌리)
            if 안 is not None:
                return 안
        c = ((r.get("properties") or {}).get("부품") or {}).get("const")
        if c == v.get("부품"):
            return r
    return None


def _통과(v, sch, 뿌리):
    e = []
    _검(v, sch, 뿌리, "", e)
    return not e


def 스키마검사(doc):
    오류 = []
    _검(doc, 스키마(), 스키마(), "", 오류)
    return [f"{자리 or '(최상위)'}: {왜}" for 자리, 왜 in 오류]


# ── 의미 규칙 ──────────────────────────────────────────────────────────
메모표현 = ("자료에 없", "옮긴 것", "나란히 둔", "막대 길이", "뺌", "적지 않",
          "지어내지", "기준으로 그", "추정함", "임의로", "로 판정",
          # '26-09-28 통합 E2E — '…집계표로 직접 계산함' 이 출처에 그대로 찍혔다(1단계 흠 재현)
          "직접 계산", "계산함", "작성 메모",
          # '26-09-28 적대 검토(지시문) — 1단계 심사가 짚은 메모 가운데 낱말 목록을 빠져나간 꼴
          "옮김", "이은 것", "짝지은 것", "줄여 적음", "줄여 씀", "에서 시작")
# 낱말 하나로 막으면 정상 자료 이름까지 막는다('26-09-28 적대 검토: 자료 그대로인 '…사업비 산출 결과(총무팀)'
# 가 hard → '산출'을 빼면 지어냈나가 '자료에 없는 출처' — 이중 구속). 그래서 '산출'은 자료 이름에 흔한
# 명사구(산출 내역·근거·기준·결과…)를 빼고 보고, '=100' 은 지수 기준 표기('(2020=100)')를 빼고 본다.
출처산출re = re.compile(r"산출(?!\s*(?:내역|근거|기준|결과|자료|방식|방법|서|표|액|식\b|값\s*표))")
지수기준re = re.compile(r"\(\s*'?\d{2,4}\s*년?\s*=\s*100\s*\)")
기준100re = re.compile(r"=\s*100")
# 화면 글(출처 밖) 어디든 '(산출)' 칩 흉내·'작성 메모' 가 들어가면 막는다 — 1단계 흠('산출' 칩 과다·
# 제작 메모 각주)이 슬롯 밖으로는 못 나오지만 글 안에 적어 되살아나는 길('26-09-28 통합 E2E 재현).
# '26-09-28 적대 검토(지시문): '(계산)'·'(추정)'·'〈산출〉'·'※ 산출값'·'산출: 식' 흉내도 같이 본다.
화면메모re = re.compile(r"[(（\[〈<]\s*(?:산출|계산|추정)(?:값)?\s*[)）\]〉>]|작성\s*메모|※\s*산출|산출\s*[:：]")
# 문장꼴 작성 메모(화면 글) — '협조 항목은 … 옮김'·'과제 꼬리표는 … 이은 것'·'눈금은 140%에서 시작'.
# 정상 글과 겹칠 수 있어 soft 로 알린다(실측 보정 뒤 승격 — 온톨로지 slides.게이트._v2_승격).
문장메모re = re.compile(r"(?:옮김|옮긴 것|이은 것|짝지은 것|나란히 둔 것|줄여 적음|줄여 씀|뺀 것|판정함|정함|추정함|계산함)\s*[.)]?\s*$"
                    r"|(?:은|는)\s.*에서 시작\s*$|자료에 없어")


def 출처메모(출처):
    """출처 글에서 작성 메모 표현 — [표현…]."""
    t = 지수기준re.sub("", 출처 or "")
    out = [w for w in 메모표현 if w in t]
    if 출처산출re.search(t):
        out.append("산출")
    if 기준100re.search(t):
        out.append("=100")
    return out
시점re = re.compile(r"^('?\d{2,4}년?|\d{1,2}월|\d차|[1-4]분기|상반기|하반기|\d{4}|'\d{2}년? ?[1-4]?분기?|\d{1,2}월말|\d차년도?)$")
_열거키 = ("노트", "산출", "출처", "부품", "역할", "변형", "정렬", "척도", "종류", "방향", "판정",
         "상태", "아이콘", "제목모양", "바탕", "열정렬", "유형", "전후종류", "폭", "밀도", "강조행")
밀도상한 = {"발표": 40, "보고": 90, "배포": 150}


def 글자(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(str(r.get("t", "")) for r in v if isinstance(r, dict))
    return ""


_요청말 = ("승인 요청", "승인을 요청", "예산 요청", "건의", "의결", "재가", "협조 요청", "협조를 요청")


def _런있나(node):
    if isinstance(node, list):
        return bool(node) and all(isinstance(r, dict) and "t" in r for r in node) or any(_런있나(x) for x in node)
    if isinstance(node, dict):
        return any(_런있나(v) for k, v in node.items() if not str(k).startswith("_") and k != "노트")
    return False


def 강조런수(v):
    return sum(1 for r in v if isinstance(r, dict) and r.get("역할") == "강조") if isinstance(v, list) else 0


def 칸들(장):
    for k, c in enumerate(장.get("칸") or []):
        if not isinstance(c, dict):
            continue
        if c.get("부품") == "세로묶음":
            for m, cc in enumerate(c.get("칸") or []):
                if isinstance(cc, dict):
                    yield f"칸.{k}.칸.{m}", cc
        else:
            yield f"칸.{k}", c


def 모든글(node, out):
    """화면에 찍히는 글(노트·산출·출처·열거값 제외)."""
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        if node and all(isinstance(r, dict) and "t" in r for r in node):
            out.append(글자(node))
        else:
            for x in node:
                모든글(x, out)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in _열거키 or str(k).startswith("_"):
                continue
            모든글(v, out)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.append(str(node))


def 어절수(장):
    out = []
    모든글(장, out)
    return sum(1 for t in out for w in t.split() if not re.fullmatch(r"[\W_]+", w))


def _차트수(c):
    """차트형 부품이 그림으로 쓰는 숫자 — (슬롯, 값). 크기 한도 검사용."""
    n = c.get("부품")
    out = []
    if n == "선차트":
        for s in c.get("계열") or []:
            out += [("계열.값", v) for v in s.get("값") or [] if isinstance(v, (int, float)) and not isinstance(v, bool)]
    elif n == "가로막대":
        out += [("행.값", r.get("값")) for r in c.get("행") or []]
    elif n == "점눈금":
        out += [("점.값", x.get("값")) for x in c.get("점") or []]
    elif n == "구성띠":
        out += [("조각.값", x.get("값")) for x in c.get("조각") or []]
    elif n == "진행막대":
        out += [("값", c.get("값")), ("목표", c.get("목표"))]
    return [(k, v) for k, v in out if isinstance(v, (int, float)) and not isinstance(v, bool)]


def 장목적(doc, 장):
    """요청 장은 덱 목적과 관계없이 설득으로 친다(SCHEMA §4-2)."""
    return "설득" if 장.get("유형") == "요청" else (doc.get("목적") or "보고")


def 검사(doc, 약한모델=False):
    hard = 스키마검사(doc)
    soft = []
    if hard:
        return hard, soft
    S = 스키마()
    부품메타 = {k[3:]: v for k, v in S["$defs"].items() if k.startswith("부품_")}
    약 = S.get("x-약한모델") or {}
    배치 = S.get("x-기본배치") or {}
    요청들, 주인공 = [], {}
    강조장, 요청신호장, 머리들 = [], [], {}
    유형열 = []
    for i, 장 in enumerate(doc["장"]):
        유형 = 장["유형"]
        자리 = f"장.{i}({유형})"
        if 유형 not in ("표지", "목차", "간지", "마무리"):
            유형열.append(유형)
        머리 = 장.get("머리") or {}
        if 머리 and 유형 in ("표지", "마무리"):
            soft.append(f"{자리} 표지·마무리에는 머리를 두지 않는다(조립기가 그리지 않는다)")
        if 머리.get("메시지") and 유형 not in ("표지", "목차", "간지", "마무리"):
            머리들.setdefault(머리["메시지"].strip(), []).append(i)
        if 약한모델:
            # 약한 모델 '쓰지 않는 것'(x-약한모델.쓰지않는슬롯) — 지시문만 말하고 막지 않았다('26-09-28 적대 검토)
            if 장.get("리드"):
                hard.append(f"{자리} 약한 모델은 리드를 쓰지 않는다(요지는 요지띠로)")
            if 장.get("밀도"):
                hard.append(f"{자리} 약한 모델은 장별 밀도를 쓰지 않는다(덱 밀도 하나)")
            if isinstance(장.get("표지"), dict) and 장["표지"].get("수치"):
                hard.append(f"{자리} 약한 모델은 표지 수치를 쓰지 않는다(한눈에보기 지표타일로)")
            if _런있나(장):
                hard.append(f"{자리} 약한 모델은 런 배열을 쓰지 않는다(글로 적고 강조는 머리.강조로)")
        합 = len(머리.get("라벨", "")) + len(머리.get("메시지", ""))
        if 합 > 50:
            hard.append(f"{자리} 머리 라벨+메시지 {합}자 > 50")
        if len(머리.get("메시지", "")) > 30:
            soft.append(f"{자리} 머리 메시지 {len(머리['메시지'])}자 > 30(목표)")
        for k in 머리.get("강조") or []:
            if k not in 머리.get("메시지", ""):
                hard.append(f"{자리} 머리.강조 '{k}' 가 메시지 안에 없다 — 메시지에 그대로 있는 부분 글자로 적는다")
        강조 = (len(머리.get("강조") or []) + 강조런수((장.get("요지띠") or {}).get("메시지")) + 강조런수(장.get("리드"))
              + 강조런수((장.get("마무리") or {}).get("문구")))      # 마무리 런도 센다('26-09-28 적대 검토)
        if 강조:
            강조장.append(i)
        for _, c in 칸들(장):
            for key in ("요지", "요청문"):
                강조 += 강조런수(c.get(key))
        if 강조 > 2:
            hard.append(f"{자리} 강조 {강조}곳 > 2(장당, 머리·요지띠·런 합계)")
        출처 = 장.get("출처", "")
        의도0 = ((doc.get("_맥락") or {}).get("의도") if isinstance(doc.get("_맥락"), dict) else None) or doc.get("_요청")
        출처말 = isinstance(의도0, str) and bool(re.search(r"출처|통계|조사|대장|보고서|공시|백서|집계|자료\s*[:(（]|기준\s*\)", 의도0))
        if not 출처 and 유형 in ("한눈에보기", "데이터", "표") and (not isinstance(의도0, str) or not 의도0.strip() or 출처말):
            # 예전 안내('○○공사 내부 자료('25년)'처럼)를 모델이 그대로 따라 자료에 없는 '내부 자료'·연도를 붙였다 — bench13
            # 심사 6인이 주민 설명회 덱의 '내부 자료' 꼬리말을 짚었고, 약한 경로에서는 자료 연도와 다른 ''25년'이 hard 가 됐다
            # (round3 적대 검토 L09). 이제 자료에 출처 말이 있을 때(또는 자료 글이 없을 때)만 알리고, 예시 이름을 주지 않는다.
            soft.append(f"{자리} 수치 장인데 출처(자료·기준 시점)가 없다 — 자료에 적힌 출처 이름·기준 시점을 그대로 옮긴다"
                        "(자료에 없으면 비워 둔다 — '내부 자료'·연도를 지어 붙이지 않는다)")
        for w in 출처메모(출처):
            hard.append(f"{자리} 출처에 작성 메모 표현 '{w}' — 작성 과정 메모는 노트.메모로 옮긴다(화면에 안 찍힌다)")
        폭들 = [c.get("폭") for c in 장.get("칸") or [] if isinstance(c, dict)]
        if any(폭들) and not all(폭들):
            hard.append(f"{자리} 칸 폭을 일부만 적었다(전부 적거나 전부 뺀다)")
        if 폭들 and all(폭들):
            줄, 줄들 = 0, []
            for w in 폭들:
                if 줄 + w > 12:
                    줄들.append(줄)
                    줄 = 0
                줄 += w
            줄들.append(줄)
            if 유형 != "인용" and any(x != 12 for x in 줄들):
                hard.append(f"{자리} 칸 폭 줄 합 {줄들} — 줄마다 12")
            if len(줄들) > 2:
                hard.append(f"{자리} 칸이 {len(줄들)}줄 — 2줄까지")
        if 유형 == "자유" and 폭들 and not all(폭들):
            hard.append(f"{자리} 자유 유형은 폭을 모두 적는다")
        허용 = (배치.get(유형) or {}).get("허용")
        for c in 장.get("칸") or []:
            if not isinstance(c, dict):
                continue
            if c.get("부품") == "세로묶음":
                if any(isinstance(cc, dict) and "폭" in cc for cc in c.get("칸") or []):
                    hard.append(f"{자리} 세로묶음 안 칸에 폭을 적었다")
                continue
            m = 부품메타.get(c.get("부품"), {})
            if c.get("폭") and c["폭"] < m.get("x-최소폭", 2):
                hard.append(f"{자리} {c['부품']} 폭 {c['폭']} < 최소 {m['x-최소폭']}")
        for p, c in 칸들(장):
            n = c.get("부품")
            if isinstance(허용, list) and n not in 허용:
                soft.append(f"{자리}.{p} {n} 는 {유형} 유형의 부품 후보가 아니다(그리기는 한다) — 필요하면 자유 유형")
            if 약한모델 and n not in 약.get("부품", []):
                hard.append(f"{자리}.{p} 약한 모델 부분집합 밖 부품 {n}")
            if n == "요청상자":
                요청들.append(i)
            if n == "선차트":
                L = len(c["가로축"])
                for s in c["계열"]:
                    if len(s["값"]) != L:
                        hard.append(f"{자리}.{p} 계열 '{s['이름']}' 값 {len(s['값'])}개 ≠ 가로축 {L}개")
                    if not any(isinstance(x, (int, float)) for x in s["값"]):
                        hard.append(f"{자리}.{p} 계열 '{s['이름']}' 에 숫자가 하나도 없다")
                # 차트 강조 계열 1 — '26-09-28 신설 지표는 전부 soft 로 시작한다(온톨로지 slides.게이트.
                # soft_v2·_v2_승격). 두 계열을 강조해도 조립기는 그린다(둘 다 focus 색).
                if sum(1 for s in c["계열"] if s.get("역할", "강조") == "강조") > 1:
                    soft.append(f"{자리}.{p} 선차트 강조 계열 2개 이상 — 강조는 하나, 나머지는 '비교'(회색)")
            if n == "가로막대":
                if sum(1 for r in c["행"] if r.get("역할") == "강조") > 1:
                    soft.append(f"{자리}.{p} 가로막대 강조 행 2개 이상 — 강조는 하나")
                if all(시점re.match(r["라벨"].strip()) for r in c["행"]) and c.get("정렬", "값순") == "값순":
                    soft.append(f"{자리}.{p} 행이 시점인데 정렬 값순 — 조립기가 입력순으로 고정한다")
                if len(c["행"]) == 2 and c.get("변형", "기본") == "기본":
                    soft.append(f"{자리}.{p} 막대 2개 — 변형 '전후'나 전후숫자로")
            if n == "표":
                w = len(c["머리행"])
                for r, row in enumerate(c["행"]):
                    if len(row) != w:
                        hard.append(f"{자리}.{p} 표 행 {r} 칸 {len(row)} ≠ 머리행 {w}")
                if c.get("열정렬") and len(c["열정렬"]) != w:
                    hard.append(f"{자리}.{p} 열정렬 길이 ≠ 머리행")
                if c.get("강조행") is not None and c["강조행"] >= len(c["행"]):
                    hard.append(f"{자리}.{p} 강조행 색인 밖")
            if n == "구성띠":
                if c.get("강조") is not None and c["강조"] >= len(c["조각"]):
                    hard.append(f"{자리}.{p} 구성띠 강조 색인 밖")
                if sum(x["값"] for x in c["조각"]) <= 0:
                    hard.append(f"{자리}.{p} 구성띠 조각 합이 0 이하")
            if n == "진행막대" and not c["목표"]:
                hard.append(f"{자리}.{p} 진행막대 목표가 0 — 비율을 못 낸다")
            # '26-09-28 적대 검토(렌더 L3·L4) — 음수·축 밖·터무니없이 큰 값이 경고 없이 그림을 비틀었다
            if n == "진행막대" and isinstance(c.get("목표"), (int, float)) and c["목표"] < 0:
                hard.append(f"{자리}.{p} 진행막대 목표가 음수 — 목표 대비 비율을 못 낸다")
            if n == "구성띠" and any(x["값"] < 0 for x in c["조각"]):
                hard.append(f"{자리}.{p} 구성띠 조각에 음수 — 구성비는 0 이상(증감은 전후숫자·표로)")
            if n == "점눈금" and isinstance(c.get("축"), dict):
                lo, hi = c["축"].get("최소"), c["축"].get("최대")
                if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                    if hi <= lo:
                        hard.append(f"{자리}.{p} 점눈금 축 최대 {hi} ≤ 최소 {lo}")
                    밖 = [x["값"] for x in c["점"] if not lo <= x["값"] <= hi]
                    if hi > lo and 밖:
                        hard.append(f"{자리}.{p} 점눈금 값 {밖} 이 축 {lo}~{hi} 밖 — 축을 넓히거나 빼라(빼면 조립기가 정한다)")
            if n == "가로막대" and any(isinstance(r.get("값"), (int, float)) and r["값"] < 0 for r in c["행"]):
                soft.append(f"{자리}.{p} 가로막대에 음수 값 — 막대 길이 0 으로 그린다(증감은 전후숫자·표로)")
            if n == "가로막대" and c.get("척도") == "백분율" and any(
                    isinstance(r.get("값"), (int, float)) and r["값"] > 100 for r in c["행"]):
                soft.append(f"{자리}.{p} 가로막대 척도 백분율인데 100 넘는 값 — 막대는 100 에서 멈춘다(척도 최댓값으로)")
            for 키, 값 in _차트수(c):
                if abs(값) >= 1e15:
                    hard.append(f"{자리}.{p} {키} 값 {값:g} 이 너무 크다 — 단위를 키워(억원·조원) 적는다")
            큰 = [v for _, v in _차트수(c) if 1e9 <= abs(v) < 1e15]
            if 큰:
                # 10억 넘는 수를 원 단위로 그리면 눈금·끝값 글이 그림 폭을 먹어 SVG 밖으로 나간다(round2 적대 검토 L2)
                soft.append(f"{자리}.{p} 차트 값 {큰[0]:,.0f} 처럼 큰 수 — 단위를 키워(억원·조원) 적으면 눈금·끝값 글이 짧아진다")
            if n == "표":
                for r, row in enumerate(c.get("행") or []):
                    for k, 셀 in enumerate(row if isinstance(row, list) else []):
                        if isinstance(셀, dict) and isinstance(셀.get("증감"), dict):
                            글, 방 = str(셀.get("글") or "").strip(), 셀["증감"].get("방향")
                            if (글.startswith("+") and 방 == "감소") or (글[:1] in ("-", "−", "△") and 방 == "증가"):
                                soft.append(f"{자리}.{p} 표 행 {r} 칸 {k} 글 '{글}' 의 부호와 증감 방향 '{방}' 이 반대다")
            if n == "지표타일":
                주인공.setdefault(c["값"] + c.get("단위", ""), []).append(i)
            if n == "카드" and len(c.get("항목") or []) < 2:
                hard.append(f"{자리}.{p} 빈 카드(항목 2개 미만)")
            if n == "카드":
                # 항목 수만 채운 빈 카드('○○'·'-'·한 낱말) — 1단계 흠이 항목 2개로 되살아났다('26-09-28 적대 검토)
                낱 = [글자(x.get("글") if isinstance(x, dict) else x).strip() for x in c.get("항목") or []]
                얕음 = [t for t in 낱 if re.fullmatch(r"[○△□◯\-–—·.\s]*", t) or len(t.split()) < 2]
                if 낱 and len(얕음) * 2 > len(낱):
                    soft.append(f"{자리}.{p} 카드 항목이 자리표시·한 낱말뿐({', '.join(얕음[:3])}) — 내용이 적으면 카드를 줄이거나 부품을 바꾼다")
        if 약한모델 and 유형 not in 약.get("유형", []):
            hard.append(f"{자리} 약한 모델 부분집합 밖 유형")
        if 약한모델 and any(isinstance(c, dict) and c.get("부품") == "세로묶음" for c in 장.get("칸") or []):
            hard.append(f"{자리} 약한 모델은 세로묶음을 쓰지 않는다")
        if 약한모델 and any(isinstance(c, dict) and "폭" in c for c in 장.get("칸") or []):
            hard.append(f"{자리} 약한 모델은 폭을 쓰지 않는다")
        화면 = []
        모든글(장, 화면)
        화면글 = " ".join(화면)
        if 화면메모re.search(화면글):
            hard.append(f"{자리} 화면 글에 '(산출)' 표시·작성 메모 — 계산값은 산출[]에 등록하고(조립기가 발표자 노트로 알린다 — 화면엔 안 찍는다) "
                        "작성 메모는 노트.메모로 옮긴다")
        문장메모 = [t for t in 화면 if 문장메모re.search(t.strip())]
        if 문장메모:
            soft.append(f"{자리} 화면 글이 작성 메모처럼 보인다('{문장메모[0][:24]}') — 작성 과정 설명은 노트.메모로")
        # 값+단위 두 슬롯에 나뉜 수치('18'+'%')도 화면 글로 친다 — 산출 '18%' 거짓 경고 막기(검토)
        붙인글 = " ".join(f"{c.get('값')}{c.get(u) or ''} {c.get('값')} {c.get(u) or ''}"
                        for _, c in 칸들(장) for u in ("단위",) if c.get("값") is not None)
        비교글 = (화면글 + " " + 붙인글).replace(" ", "")
        for s in 장.get("산출") or []:
            if s["값"] not in 화면글 and str(s["값"]).replace(" ", "") not in 비교글:
                soft.append(f"{자리} 산출 '{s['값']}' 이 화면 글에 없다")
        밀도 = 장.get("밀도") or doc.get("밀도", "보고")
        n어절 = 어절수(장)
        if n어절 > 밀도상한[밀도]:
            soft.append(f"{자리} 어절 {n어절} > {밀도상한[밀도]}(밀도 {밀도})")
        부품수 = sum(1 for _ in 칸들(장))
        if 유형 not in ("표지", "목차", "간지", "마무리", "인용") and n어절 < 밀도상한[밀도] * 0.25 \
                and (부품수 == 1 or 유형 != "요청"):
            soft.append(f"{자리} 빈 장 의심 — 부품 {부품수}개·어절 {n어절}(상한 {밀도상한[밀도]}의 25% 미만). "
                        "앞뒤 장과 합치거나 부품을 바꾼다(판을 억지로 늘리지 않는다)")
        # 설득 덱의 마무리는 요청을 한 줄로 되새길 수 있다(⑫ · 온톨로지 soft_v2) — 요청말 soft 에서 뺀다. 금액 되풀이는
        # 아래 '요청 금액 … 화면에도' soft 가 따로 본다(round2 적대 검토 규칙 §2-A: EXAONE s2d 마무리가 이 soft 로 헛재시도)
        if 유형 not in ("표지", "요청") and not (유형 == "마무리" and doc.get("목적") == "설득"):
            밖글 = []
            모든글({k: v for k, v in 장.items() if k != "칸"}, 밖글)
            for _, c in 칸들(장):
                if c.get("부품") != "요청상자":
                    모든글(c, 밖글)
            if any(w in " ".join(밖글) for w in _요청말):
                요청신호장.append(i)
        if 장목적(doc, 장) in ("보고", "설득") and re.search(r"(습니다|합니다|입니다)[.]?$", 머리.get("메시지", "")):
            soft.append(f"{자리} 보고·설득 머리를 '~습니다'로 맺었다 — 메시지구·완결 주장으로")
        if 장목적(doc, 장) == "설득" and 머리.get("메시지") and not re.search(r"\d", 머리["메시지"]):
            soft.append(f"{자리} 설득 머리에 수치가 없다")
    if len(요청들) > 1:
        hard.append(f"요청상자가 {len(요청들)}개(장 {요청들}) — 건의·요청은 덱에서 한 번")
    for 키, 장번호 in 주인공.items():
        if len(set(장번호)) > 1:
            soft.append(f"지표타일 주인공 수치 '{키}' 가 여러 장({sorted(set(장번호))})에 반복")
    for i in 요청들:
        for _, c in 칸들(doc["장"][i]):
            if c.get("부품") == "요청상자" and c.get("금액"):
                금액 = c["금액"]["값"] + c["금액"].get("단위", "")
                # 마무리 장 한 곳의 금액 되새김은 된다('26-09-29 bench13 ② — 온톨로지 구성.요청_한번_v2 와 같은 말)
                되새김 = next((j for j, x in enumerate(doc["장"]) if x.get("유형") == "마무리"), None)
                for j, 장 in enumerate(doc["장"]):
                    if j == i or j == 되새김 or 장.get("유형") == "한눈에보기":   # 요약 장은 판단 숫자로 금액을 둔다('26-09-29 ⑩)
                        continue
                    out = []
                    모든글(장, out)
                    if 금액.replace(" ", "") in " ".join(out).replace(" ", ""):
                        soft.append(f"요청 금액 '{금액}' 이 장.{j} 화면에도 나온다(요청은 덱에서 한 번)")
    # '마무리 — 요청 되풀이' 는 build/슬라이드v2.py W-마무리요청 이 마무리 글을 보고 알린다(여기서 늘 울리던
    # '확인' 경고는 깨끗한 마무리에도 떠서 지웠다 — '26-09-28 적대 검토).
    if len(요청신호장) + (1 if 요청들 else 0) >= 2:
        soft.append(f"요청·승인·건의 말이 요청상자 밖 여러 장(장 {요청신호장})에 — 건의·요청은 덱에서 한 번(요청상자 하나)")
    if len(강조장) >= 4 and len(강조장) * 2 > sum(1 for x in doc["장"] if x["유형"] not in ("표지", "목차", "간지")):
        soft.append(f"강조가 있는 장이 {len(강조장)}장 — 덱 절반을 넘는다(강조는 그 장의 핵심 한두 곳만, 매 장 되풀이하지 않는다)")
    for 메, 번호 in 머리들.items():
        if len(번호) > 1:
            soft.append(f"같은 머리 메시지가 여러 장({번호})에 — 복제한 장이면 머리를 새로 쓰거나 장을 지운다")
    글머리장 = sum(1 for 장 in doc["장"] if any(c.get("부품") == "글머리" for _, c in 칸들(장)))
    본문장 = sum(1 for 장 in doc["장"] if 장["유형"] not in ("표지", "목차", "간지", "마무리"))
    if 글머리장 and 글머리장 * 2 > 본문장:
        hard.append(f"글머리 부품이 든 장 {글머리장}/{본문장} — 본문 장의 절반까지(온톨로지 게이트.hard_v2)")
    if doc.get("프리셋") == "keynote" and doc.get("목적") in ("보고", "설득"):
        soft.append("키노트형 프리셋은 대외 설명회용 — 보고·설득 덱은 데이터형·브리핑형이 격식에 맞다")
    if len(set(유형열)) < 4 and len(doc["장"]) >= 8:            # 온톨로지 soft_v2 '8장 이상이면 4종 이상'과 맞춘다
        soft.append(f"본문 장 유형 {len(set(유형열))}종 — 4종 이상 권장")
    연속, 최대, 앞 = 0, 0, None
    for t in 유형열:
        연속 = 연속 + 1 if t == 앞 else 1
        최대 = max(최대, 연속)
        앞 = t
    if 최대 >= 3:
        soft.append(f"같은 유형이 {최대}장 연속 — 3연속 금지(유형 다양성)")
    배포 = sum(1 for 장 in doc["장"] for _, c in 칸들(장)
             if c.get("부품") == "글머리" and (장.get("밀도") or doc.get("밀도", "보고")) != "배포")
    if 배포:
        soft.append(f"글머리 부품 {배포}개 — 배포 밀도 전용")
    _덱규칙(doc, hard, soft)
    return hard, soft


# ── 덱 규칙('26-09-29 bench11 심사 3인 × 4 시나리오의 공통 지적 → 규칙) ──────────────────────
# '결과로'는 뺐다 — '점검 결과로 결함 12건 확인'처럼 자료의 사실을 잇는 말에도 걸렸다(round2 적대 검토 규칙 §3-D)
# 판단·인과 말 목록(_판단말)은 아래 '자료 밖 판단·인과'(bench13 ④)에 둔다.
_인사말 = ("감사합니다", "지속 추진", "노력하겠", "최선을 다", "힘쓰겠", "이상입니다")


_수re = re.compile(r"(?<!['’\d,.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")


def _수들(t):
    """글 안 숫자들(쉼표 뗌) — 연도(19xx·20xx·'yy)는 판단 숫자가 아니라 뺀다. 쉼표가 제자리인 것만 한 수로 읽는다
    ('1,2,3건' → 1·2·3). 쉼표를 품었거나 금액·수량 단위가 곧바로 붙은 네 자리('2,000만원'·'2000명')는 연도가 아니다
    (round2 적대 검토 규칙 §3-C: '2,000만원'을 연도로 빼서 ⑩·⑯이 둘 다 건너뛰었다)."""
    out = set()
    글 = str(t or "")
    for m in _수re.finditer(글):
        원 = m.group(1)
        s = 원.replace(",", "")
        try:
            v = float(s)
        except ValueError:
            continue
        if re.fullmatch(r"(19|20)\d\d", s) and "," not in 원 and not re.match(r"\s*(?:조|억|천만|백만|만|천|원|명|건|개|곳|가구|%)", 글[m.end():]):
            continue
        out.add(v)
    return out


_배율 = {"조": 1e12, "억": 1e8, "천만": 1e7, "백만": 1e6, "만": 1e4, "천": 1e3}
_금액식 = re.compile(r"(?<![\d.,])((?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)\s*)*"
                   r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)?\s*원)")
_금액조각 = re.compile(r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(조|억|천만|백만|만|천)?")


def _원단위(t):
    """글 안 금액들을 원 단위 값 집합으로 — '2억 7천만원'·'2억7,000만 원'·'270백만원'·'270,000천원'·'4.2억 원'·'1,550만 원'.
    round2 적대 검토 규칙 §3-B: 공공 예산서 기본 단위(백만원·천원)와 복합 표기를 {2, 7} 따위로 읽어, 자료에 있는 금액을
    '자료에 없다' hard 로 막았다. 배율이 이어 붙은 묶음은 더한다(2억 + 7천만). '원'으로 끝나는 것만 금액으로 친다."""
    out = set()
    for m in _금액식.finditer(str(t or "")):
        합 = 0.0
        for 수, 배 in _금액조각.findall(m.group(1)):
            합 += float(수.replace(",", "")) * (_배율[배] if 배 else 1.0)
        out.add(합)
    return out


def 요청금액(c):
    """요청상자의 요청 금액 — {값, 단위[, 라벨]} 또는 None. 금액 슬롯이 없고 요청문에 금액이 딱 하나 있으면 그것
    (round2 적대 검토 규칙 §3-F: 금액을 요청문 글로만 쓰면 ⑩이 꺼졌다)."""
    if not isinstance(c, dict) or c.get("부품") != "요청상자":
        return None
    금 = c.get("금액")
    if isinstance(금, dict) and 금.get("값") not in (None, ""):
        return 금
    m = list(re.finditer(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(조\s*원|억\s*원|천만\s*원|백만\s*원|만\s*원|원|억|만)",
                         글자(c.get("요청문"))))
    if len(m) == 1:
        return {"값": m[0].group(1), "단위": re.sub(r"\s+", "", m[0].group(2))}
    return None


def _금액원(값, 단위):
    """요청 금액(값 글·단위) → 원 단위 값과 반올림 너그러움(원) — 못 읽으면 None."""
    수 = _수들(값)
    if len(수) != 1:
        return None
    v = next(iter(수))
    u = re.sub(r"\s+", "", str(단위 or ""))
    m = re.fullmatch(r"(조|억|천만|백만|만|천)?원?", u)
    if not m:
        return None
    배 = _배율.get(m.group(1), 1.0) if m.group(1) else 1.0
    s = str(값).replace(",", "").strip()
    자리 = len(s.split(".")[1]) if "." in s else 0
    return v * 배, 0.5 * 10 ** (-자리) * 배


def 요청장수(글):
    """사용자 글에서 요청 장수 — (가운데, 아래, 위) 또는 None. '10장 안팎'·'8~10장'·'12장 이내'·'10장 내외'.
    슬라이드·발표·장표·PPT 가 같은 문장에 있을 때만 읽는다(보고서 '제2장' 같은 말을 잘못 잡지 않게)."""
    for 문장 in re.split(r"[.\n。!?]", str(글 or "")):
        if not re.search(r"슬라이드|발표|장표|PPT|피피티|프레젠테이션|덱", 문장, re.I):
            continue
        m = re.search(r"(?<![제\d])(\d{1,2})\s*[~∼\-–]\s*(\d{1,2})\s*장", 문장)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            return ((a + b) // 2, a, b)
        m = re.search(r"(?<![제\d])(\d{1,2})\s*장\s*(안팎|내외|정도|쯤|가량|이내|이하|이상|남짓|분량|짜리|으로|로|[,\s])", 문장 + " ")
        if m:
            n = int(m.group(1))
            # 스키마 상한(17장)을 넘는 요청은 상한으로 읽는다 · '이상'·'최소'는 하한만 있는 말(round2 적대 검토 규칙 §8-6)
            if m.group(2) == "이상" or re.search(r"최소\s*$", 문장[:m.start()]):
                return (min(n, 17), min(n, 17), 17)
            n = min(n, 17)
            if m.group(2) in ("이내", "이하"):
                return (n, max(3, n - 4), n)
            return (n, max(3, n - 2), min(17, n + 2))
    return None


def 플러스연결(메):
    """머리 메시지의 '+' 가 두 말을 잇는 연결인가(⑬). 부호('+16%'·'+3.2%p' — 빈칸 뒤 '+' 가 숫자에 붙음)·등급('AA+'·
    'BBB+'·'S+'·'평가B+'·'B+ 등급')은 연결이 아니다(round2 적대 검토 규칙 §3-A: 이것들이 hard 오탐이었다).
    자리마다 가른다 — 한 곳이 등급이라고 문장 전체를 면제하지 않는다('평가 B+ 등급 달성 + 부채비율 감소'는 연결)."""
    t = str(메 or "")
    for m in re.finditer(r"\+", t):
        k = m.start()
        앞, 뒤 = t[:k], t[k + 1:]
        if re.search(r"(?:^|[^A-Za-z])[A-Z]{1,3}$", 앞) and (not 뒤 or re.match(r"[\s,·)）/]", 뒤)):
            continue                                     # 등급
        if (not 앞 or re.search(r"[\s(（~∼]$", 앞)) and re.match(r"\d", 뒤):
            continue                                     # 부호
        if 앞.strip() and 뒤.strip():
            return True
    return False


# ── 같은 수치 되풀이('26-09-29 bench13 ② — CLI 덱에서 지적 0.75건/덱: 한 수치가 요약·본문·마무리 3~4장에 거듭 나왔다) ──
# 값+단위를 한 수치로 본다('5,000만 원' = '5,000'+'만원' = 5천만 원 · '82점' · '18%'). 금액은 원 단위로 맞춘다.
# 단위 없는 맨 수(차트 눈금·번호)·연도·날짜는 세지 않는다. '5대 과제' 같은 서수 '대'도 뺀다.
# '대'(승강기 1,240대)·'분'(24분)도 센다(round3 적대 검토 R08) — '대상·대비·대응'·'분기·분야' 같은 낱말과 '5대 과제'·
# '10대 전략' 같은 서수는 뺀다
_단위수re = re.compile(r"(?<![\d.,'’])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(%p|%|퍼센트|점|명|건|곳|개소|개월|개년|개|가구|시간|쪽|배|톤|MW|kW|km|회"
                    r"|대(?![상비학응책규형표로란량회구출리외내])(?!\s*(?:과제|분야|전략|사업|핵심|추진|중점|혁신|목표|방향|원칙|정책|과업|영역|지표|기관|도시|권역))"
                    r"|분(?![기야석류담배포할의석]))")
# 개수 단위의 작은 수(10 미만 — '3개 과제'·'2곳'·'0건')는 덱 짜임을 말하는 수라 되풀이로 치지 않는다
_개수단위 = ("개", "개소", "개년", "개월", "곳", "건", "명", "회", "배", "대")
_큰금액re = re.compile(r"(?<![\d.,'’])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(조|억|천만|백만)(?!\s*[원\d])")
되풀이허용 = 2          # 한눈에보기 + 그 수치를 증명하는 본문 장 — 두 번까지(온톨로지 구성.장간_중복_금지_v2)


def _수치열(t):
    """글 안 수치 [(열쇠, 보이는 글)] — 열쇠 = (단위, 값). 금액은 ('원', 원 단위 값)."""
    글 = str(t or "")
    out = []
    for m in _금액식.finditer(글):
        합 = 0.0
        for 수, 배 in _금액조각.findall(m.group(1)):
            합 += float(수.replace(",", "")) * (_배율[배] if 배 else 1.0)
        out.append((("원", round(합, 2)), m.group(1).strip()))
        글 = 글[:m.start()] + " " * (m.end() - m.start()) + 글[m.end():]
    for m in _큰금액re.finditer(글):
        out.append((("원", round(float(m.group(1).replace(",", "")) * _배율[m.group(2)], 2)), m.group(0).strip()))
        글 = 글[:m.start()] + " " * (m.end() - m.start()) + 글[m.end():]
    for m in _단위수re.finditer(글):
        u = "%" if m.group(2) == "퍼센트" else m.group(2)
        v = float(m.group(1).replace(",", ""))
        if u in _개수단위 and v < 10:
            continue
        out.append(((u, v), m.group(0).strip()))
    return out


def _장수치(장):
    """장 화면 글의 수치 Counter(열쇠 → 횟수)와 보이는 글. 값+단위 두 슬롯은 붙여 한 번으로 센다.
    머리.강조(메시지 속 조각을 가리키는 표지)와 칸 값과 같은 증감 값(조립기가 칩에 기호만 찍는다)은 세지 않는다."""
    from collections import Counter
    센 = Counter()
    글들 = {}

    def 걸음(node):
        if isinstance(node, str):
            for k, g in _수치열(node):
                센[k] += 1
                글들.setdefault(k, g)
        elif isinstance(node, list):
            if node and all(isinstance(r, dict) and "t" in r for r in node):
                걸음(글자(node))
            else:
                for x in node:
                    걸음(x)
        elif isinstance(node, dict):
            남 = dict(node)
            남.pop("강조", None)
            # 기준값 자리는 세지 않는다 — 전후숫자 '이전'(앞 장 결과가 다음 계획의 출발점)·맥락 종류 이전·전년(비교 기준)은
            # 그 수치를 다시 주장하는 곳이 아니라 근거 자리다(round3 적대 검토 R12 — 실물 soft 사례 가운데 사례이 이 꼴,
            # 구성.장간_중복_금지_v2 '뒤 장에서는 다른 부품으로 근거만')
            if node.get("부품") == "전후숫자":
                남.pop("이전", None)
            if isinstance(node.get("맥락"), dict) and node["맥락"].get("종류") in ("이전", "전년"):
                남.pop("맥락", None)
            붙열쇠 = set()
            if node.get("값") is not None and isinstance(node.get("단위"), str) and not isinstance(node.get("값"), (list, dict)):
                붙 = f"{node['값']}{node['단위']}"
                붙열쇠 = {k for k, _ in _수치열(붙)}
                걸음(붙)
                남.pop("값", None)
                남.pop("단위", None)
                증 = node.get("증감")
                if isinstance(증, dict) and str(증.get("값") or "").replace(" ", "") == 붙.replace(" ", ""):
                    남.pop("증감", None)
            # 같은 막대·행의 표시 글('누적 49건')이 값+단위(49건)를 다시 적은 것은 한 번으로 센다(R11 — 한 부품을 두 번 셌다)
            if 붙열쇠 and isinstance(남.get("표시"), str):
                for k, g in _수치열(남.pop("표시")):
                    if k not in 붙열쇠:
                        센[k] += 1
                        글들.setdefault(k, g)
            for k, v in 남.items():
                if k in _열거키 or str(k).startswith("_"):
                    continue
                걸음(v)
    걸음({k: v for k, v in 장.items() if k not in ("노트", "산출", "출처")})
    return 센, 글들


def _금액오차(글):
    """보이는 금액 글의 반올림 너그러움(원) — 끝자리 절반('2.7억' → 0.05억, '2억 7,350만' → 0.5만). 금액이 아니면 0."""
    조각 = _금액조각.findall(str(글 or ""))
    if not 조각:
        return 0.0
    수, 배 = 조각[-1]
    자리 = len(수.split(".")[1]) if "." in 수 else 0
    return 0.5 * 10 ** (-자리) * (_배율[배] if 배 else 1.0)


def 수치되풀이(doc):
    """(덱 soft, 장 soft) — 같은 수치(값+단위)가 세 장 이상(요약 장·본문 장 두 번까지 허용, 마무리·요청 장의 금액
    되새김 한 번은 세지 않는다) · 한 장 안에서 세 번 이상. 표지·목차·간지는 세지 않는다(표지 수치는 한눈에보기에
    다시 두라는 규칙이 따로 있다)."""
    장들 = doc.get("장") or []
    어디 = {}
    보임 = {}
    오차 = {}
    장soft = []
    for i, 장 in enumerate(장들):
        if not isinstance(장, dict) or 장.get("유형") in ("표지", "목차", "간지"):
            continue
        센, 글들 = _장수치(장)
        for k, n in 센.items():
            어디.setdefault(k, []).append(i)
            보임.setdefault(k, 글들[k])
            if k[0] == "원":
                오차[k] = max(오차.get(k, 0.0), _금액오차(글들[k]))
            if n >= 3:
                장soft.append(f"장.{i}({장.get('유형')}) 한 장에 같은 수치 '{글들[k]}' 가 {n}번 — 한 번 적고 나머지는 '같은 기간'·'이 금액'처럼 가리킨다")
    # 반올림 금액은 같은 수치다('2.7억원' ↔ '2억 7,350만 원' — round3 적대 검토 R06: 다른 열쇠로 세어 다섯 장에 나와도 조용했다).
    # 끝자리 절반 안이면 한 열쇠로 묶는다(보이는 글이 가장 자세한 쪽을 남긴다)
    금액 = sorted(k for k in 어디 if k[0] == "원")
    for a in 금액:
        for b in 금액:
            if a < b and a in 어디 and b in 어디 and abs(a[1] - b[1]) <= max(오차.get(a, 0), 오차.get(b, 0)) + 1e-6:
                남길, 뗄 = (a, b) if 오차.get(a, 0) <= 오차.get(b, 0) else (b, a)
                어디[남길] = 어디[남길] + 어디.pop(뗄)
                오차[남길] = max(오차.get(a, 0), 오차.get(b, 0))
    덱soft = []
    for k, 번호 in 어디.items():
        번호 = sorted(set(번호))
        if k[0] == "원":
            되새김 = [j for j in 번호 if 장들[j].get("유형") in ("마무리", "요청")]
            if 되새김:
                번호 = [j for j in 번호 if j != 되새김[-1]]     # 마무리·요청 장의 금액 되새김 한 번은 세지 않는다
        if len(번호) > 되풀이허용:
            덱soft.append(f"같은 수치 '{보임[k]}' 가 {len(번호)}장(장 {번호})에 나온다 — 한눈에보기와 그 수치를 증명하는 본문 장, "
                        "두 번까지(마무리·요청 장의 금액 되새김 한 번은 된다). 다른 장에서는 수치를 다시 적지 않고 가리킨다")
    return 덱soft, 장soft


# ── 자료 밖 판단·인과('26-09-29 bench13 ④ — 강한 경로 0.5건/덱, 약한 경로는 '영구적 효율화 달성'류) ──
# 목적·인과·효과 판정 말은 자료가 그 말을 쓰지 않았으면 해석이다. 자료 글에 그 말이 있으면 조용하다(정밀도 우선).
_판단말 = ("추가 검토", "검토 필요", "검토가 필요", "효과 확인", "효과를 확인", "효과가 확인", "덕분", "기여했",
         "기여한", "때문에", "로 인해", "영향으로")
# 목적·인과 말(bench13 ④) — 공공 문서에 흔한 말이라('~를 위한 기반') 자료 글이 있을 때만, 자료가 그 말을 안 쓸 때만 본다
_목적인과말 = ("위한", "위해", "위하여", "대응 목적", "목적으로", "효과 입증")
# 말 묶음 — 초안의 말이 자료에 **같은 뜻의 다른 꼴**(활용·띄어쓰기)로 있으면 조용하다(round3 적대 검토 C01~C05: 낱말을 글자
# 그대로 대 봐서 자료 '안전을 위해' ↔ 초안 '안전을 위한', '효과가 확인됐다' ↔ '효과 확인'이 약한 경로 hard 가 됐다).
# 짝 말(효과+확인·검토+필요)은 자료의 한 문장 안에 둘 다 있으면 같은 말로 본다.
_위해危害 = r"위해\s*(?:요인|요소|성|물질|우려|방지|도(?![록])|평가|정보|식품|환경|등급|가능|예방|사범|행위)"


def _자료문장들(의도):
    return [s for s in re.split(r"[.\n。!?]|(?<=다)\s", str(의도 or "")) if s.strip()]


def _자료가쓰나(말, 의도):
    t = str(의도 or "")
    민 = re.sub(r"\s+", "", t)
    if 말 in ("위한", "위해", "위하여"):
        return bool(re.search(r"위(?:하|해|한|할|함)", re.sub(_위해危害, "", t)))
    if 말 in ("대응 목적", "목적으로"):
        return "목적" in t
    if 말 in ("효과 확인", "효과를 확인", "효과가 확인"):
        return any("효과" in s and "확인" in s for s in _자료문장들(t))
    if 말 in ("추가 검토", "검토 필요", "검토가 필요"):
        return any("검토" in s and ("필요" in s or "추가" in s) for s in _자료문장들(t))
    if 말 == "효과 입증":
        return "입증" in t
    if 말 == "덕분":
        return "덕분" in t or "덕택" in t
    if 말 in ("기여했", "기여한"):
        return "기여" in t
    if 말 == "때문에":
        return "때문" in t
    if 말 == "로 인해":
        return bool(re.search(r"인(?:해|한|하여|하)", t))
    if 말 == "영향으로":
        return "영향" in t
    return 말 in t or re.sub(r"\s+", "", 말) in 민


def _괄호까닭(t, 말, 의도):
    """초안 '… 지연 때문에'의 까닭 낱말이 자료에서 괄호로 밝힌 까닭이면(자료 '미조치 8건(부품 수급 지연)') 인과를 옮긴
    것으로 본다(round3 적대 검토 C06)."""
    m = re.search(r"(\S+?)(?:이|가|은|는|의)?\s*(?:때문에|(?:으)?로\s*인해)", t)
    if not m or 말 not in ("때문에", "로 인해"):
        return False
    낱 = m.group(1)
    return len(낱) >= 2 and any(낱 in 괄 for 괄 in re.findall(r"\(([^()]*)\)", str(의도 or "")))


# '완료' 과장(round3 적대 검토 C11) — 자료가 착수·진행이라 한 일을 상태 '완료'·'교체 완료'로 적었다. 자료가 끝났다는 말을
# 하나도 안 쓰면 걸린다. '완료율'·'완료 예정·목표·시점·후' 같은 지표·계획 말은 판단이 아니라 뺀다
_완료말re = re.compile(r"완료(?!율|\s*(?:예정|목표|시점|시한|기한|일정|계획|후|뒤|까지|시기|하면|할|하겠|하기|를\s*목표))")
_끝났다말 = ("완료", "마쳤", "마침", "마무리했", "끝냈", "끝났", "완공", "준공", "완수", "종료", "개통", "완비", "달성했")


def _끝났다(s):
    return any(w in s for w in _끝났다말 if w != "완료") or bool(_완료말re.search(s))


def _완료과장(대상글, 의도, 자료끝남):
    """'12월 교체 완료'(또는 제목 '교체'의 상태 완료)가 자료에 없는 완료 판단인가 — 대상 낱말('교체')이 나오는 자료 문장이
    있으면 그 문장들이 끝났다고 말하는지로 가르고(자료가 딴 일의 '점검 완료'를 말해도 '교체 착수'는 착수다), 대상이 자료에
    없으면 자료 전체로 가른다."""
    낱말 = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", str(대상글 or "")) if w not in ("완료", "상태")]
    관련 = [s for s in _자료문장들(의도) if any(w in s for w in 낱말[-2:])]
    if 관련:
        return not any(_끝났다(s) for s in 관련)
    return not 자료끝남


def 판단인과걸림(doc, 의도):
    """[(자리, 글, 말)] — 머리 메시지·요지띠·칸 요지·리드(자료 글이 있으면 카드·항목타일·글머리 글, 요청상자 행 내용, 마무리
    문구, 표지 부제까지)에 자료에 없는 판단·인과 말. 자료가 같은 뜻을 다른 꼴로 쓰면 조용하다(말 묶음).
    자료 글이 있으면 '완료' 과장(상태 '완료'·머리·항목의 '완료')도 본다 — 말은 '완료'.
    자료 글(의도)이 없으면 옛 판단말만 머리·요지띠·요지에서 본다(round2 ⑯ 그대로 — 조립 때 자료 글이 없는 문서)."""
    자료있음 = isinstance(의도, str) and bool(의도.strip())
    말들 = _판단말 + (_목적인과말 if 자료있음 else ())
    자료끝남 = 자료있음 and _끝났다(의도)
    out = []
    for i, 장 in enumerate(doc.get("장") or []):
        if not isinstance(장, dict):
            continue
        글들 = [(f"장.{i}.머리.메시지", (장.get("머리") or {}).get("메시지") or ""),
              (f"장.{i}.요지띠", 글자((장.get("요지띠") or {}).get("메시지"))),
              (f"장.{i}.리드", 글자(장.get("리드")) if not isinstance(장.get("리드"), dict) else 글자(장["리드"].get("글")))]
        if not 자료있음:
            글들 = 글들[:2]
        else:
            # 마무리 문구·부문구·표지 부제도 본다(C09 — 같은 지어낸 목적이 이 자리에서는 조용했다)
            마 = 장.get("마무리") if isinstance(장.get("마무리"), dict) else {}
            글들.append((f"장.{i}.마무리.문구", 글자(마.get("문구"))))
            글들.append((f"장.{i}.마무리.부문구", 글자(마.get("부문구"))))
            표 = 장.get("표지") if isinstance(장.get("표지"), dict) else {}
            글들.append((f"장.{i}.표지.부제", 글자(표.get("부제"))))
        상태들 = []
        for p, c in 칸들(장):
            글들.append((f"장.{i}.{p}.요지", 글자(c.get("요지"))))
            if 자료있음 and c.get("부품") in ("카드", "항목타일", "글머리"):
                글들.append((f"장.{i}.{p}.글", 글자(c.get("글"))))
                for j, it in enumerate(c.get("항목") or []):
                    글들.append((f"장.{i}.{p}.항목.{j}", 글자(it.get("글")) if isinstance(it, dict) else 글자(it)))
            if 자료있음 and c.get("부품") == "요청상자":
                for j, r in enumerate(c.get("행") or []):
                    if isinstance(r, dict):
                        글들.append((f"장.{i}.{p}.행.{j}.내용", 글자(r.get("내용"))))
            if 자료있음:
                if c.get("상태") == "완료":
                    상태들.append((f"장.{i}.{p}.상태", str(c.get("제목") or "완료")))
                for 키 in ("단계", "항목"):
                    for j, s in enumerate(c.get(키) or []):
                        if isinstance(s, dict) and s.get("상태") == "완료" and c.get("부품") in ("타임라인", "세로타임라인"):
                            상태들.append((f"장.{i}.{p}.{키}.{j}.상태", f"{s.get('시점') or ''} {s.get('제목') or ''} 완료".strip()))
        for 자리, t in 글들:
            if not t:
                continue
            걸 = [w for w in 말들 if w in t and not (w == "위해" and re.search(_위해危害, t))
                 and not (자료있음 and (_자료가쓰나(w, 의도) or _괄호까닭(t, w, 의도)))]
            if 걸:
                out.append((자리, t, 걸[0]))
            # '2029년까지 3단계 완료'처럼 '까지'가 앞선 완료는 계획 말이라 뺀다(bench13 A s2 강한 경로 soft 오탐)
            elif 자료있음 and any(_완료과장(t[:m.start()], 의도, 자료끝남) and not re.search(r"까지[^,.·]{0,12}$", t[:m.start()])
                              for m in _완료말re.finditer(t)):
                out.append((자리, t, "완료"))
        out += [(자리, t, "완료") for 자리, t in 상태들 if _완료과장(t, 의도, 자료끝남)]
    return out


def _덱규칙(doc, hard, soft):
    장들 = doc["장"]
    목적 = doc.get("목적", "보고")
    화면 = []
    for i, 장 in enumerate(장들):
        t = []
        모든글(장, t)
        # 값+단위 슬롯을 붙여 화면 글로(지표타일 '4.2'+'억원')
        for _, c in 칸들(장):
            if c.get("값") is not None:
                t.append(f"{c.get('값')}{c.get('단위') or ''}")
            if isinstance(c.get("금액"), dict):
                t.append(f"{c['금액'].get('값')}{c['금액'].get('단위') or ''}")
        화면.append(" ".join(str(x) for x in t))
    # ⑬ 헤드의 '+' 연결 금지 — 쉼표·가운뎃점·두 절로('A 등급 + 부채비율 16%p 감소' 가 이사회 격식에 가볍다)
    for i, 장 in enumerate(장들):
        메 = (장.get("머리") or {}).get("메시지") or ""
        if 플러스연결(메):
            hard.append(f"장.{i}({장['유형']}) 머리 메시지를 '+' 로 이었다 — 쉼표·가운뎃점이나 두 절로 쓴다('A 달성, B 감소')")
    # ⑩ 한눈에 보기 = 판단 숫자(요청 금액·총액·표지의 핵심 수치)가 있어야 한다
    요약 = [i for i, 장 in enumerate(장들) if 장["유형"] == "한눈에보기"]
    if 요약:
        요약수 = set().union(*(_수들(화면[i]) for i in 요약))
        for i, 장 in enumerate(장들):
            for _, c in 칸들(장):
                금액 = 요청금액(c)
                if 금액:
                    금 = _수들(금액.get("값"))
                    if 금 and not (금 & 요약수):
                        hard.append(f"한눈에보기(장 {요약[0]})에 요청 금액 {금액.get('값')}{금액.get('단위') or ''} 이 없다 — "
                                    "결재권자가 첫 장에서 판단할 숫자다(지표타일 하나로 넣는다. 요청 문구는 요청 장에만)")
        표 = next((j for j in 장들 if j["유형"] == "표지"), None)
        표수 = _수들(" ".join([str(doc.get("제목") or ""), str(doc.get("부제") or ""),
                             str(((표 or {}).get("표지") or {}).get("부제") or "")]))
        빠짐 = sorted(v for v in 표수 - 요약수 if v >= 10 or not float(v).is_integer())   # 작은 개수(3곳)는 판단 숫자로 치지 않는다
        if 빠짐:
            soft.append(f"표지·제목의 핵심 수치 {', '.join(f'{v:g}' for v in 빠짐[:3])} 이 한눈에보기에 없다 — 요약 장에 판단 숫자를 둔다")
    # ⑪ 요청 장수 — 사용자가 장수를 말했으면 그 범위 안에서(자료가 모자라면 까닭을 노트.메모에)
    의도 = ((doc.get("_맥락") or {}).get("의도") if isinstance(doc.get("_맥락"), dict) else None) or doc.get("_요청")
    # ⑯ 판단 숫자가 자료에 있나 — 요청 금액은 hard, 지표타일 값은 soft('26-09-29 EXAONE s2 실측: 자료 '총 4.2억 원'을
    # '42억 원'으로 적은 초안이 게이트를 지나 요청 장·한눈에보기에 그대로 나갔다). 자료 글(_맥락.의도)이 온전할 때만
    # (4,000자에서 잘린 글이면 뒤 숫자를 못 본다) · 산출[]에 등록한 값은 계산값이라 통과 · 만↔억(10⁴) 단위 바꿈은 같은 값.
    if isinstance(의도, str) and 0 < len(의도) < 4000:
        자료수 = _수들(의도)
        산출수 = set()
        for 장 in 장들:
            for x in 장.get("산출") or []:
                if isinstance(x, dict):
                    산출수 |= _수들(x.get("값"))

        자료원 = set(_원단위(의도))
        for 장 in 장들:
            for x in 장.get("산출") or []:
                if isinstance(x, dict):
                    자료원 |= _원단위(f"{x.get('값')}원" if not str(x.get("값") or "").rstrip().endswith("원") else x.get("값"))

        def 있나(v):
            return any(abs(v * f - w) < 1e-6 * max(1.0, abs(w)) for w in 자료수 | 산출수 for f in (1, 1e4, 1e-4))

        def 금액있나(금액):
            # 원 단위로 바꿔 대 본다(억·천만·백만·만·천 복합 표기, 반올림 표기 '2.7억' ↔ 자료 '2억 7,350만원')
            원 = _금액원(금액.get("값"), 금액.get("단위"))
            if 원 and any(abs(원[0] - w) <= 원[1] + 1e-6 * max(1.0, w) for w in 자료원):
                return True
            return all(있나(v) for v in _수들(금액.get("값")))
        for i, 장 in enumerate(장들):
            for p, c in 칸들(장):
                금액 = 요청금액(c)
                if 금액:
                    if _수들(금액.get("값")) and not 금액있나(금액):
                        hard.append(f"장.{i}.{p}.금액 {금액.get('값')}{금액.get('단위') or ''} 이 자료에 없다 — "
                                    "자료의 금액을 그대로 옮긴다(계산한 값이면 산출[]에 식과 함께 등록한다)")
                elif c.get("부품") == "지표타일" and c.get("값") is not None:
                    # 금액 단위 타일은 요청 금액과 같은 원 단위 대조('27,350'+'만원' = 자료 '2억 7,350만 원' — round3 적대 검토 ⑧:
                    # 맨 수만 봐 대조군 덱부터 "자료에 없다" soft 가 울렸고, 웹앱 소프트 재시도가 그 줄을 '해소하라'로 되먹였다)
                    if re.fullmatch(r"\s*(?:조|억|천만|백만|만|천)?\s*원\s*(?:/.*)?|\s*(?:조|억|천만|백만)\s*", str(c.get("단위") or "")) \
                            and 금액있나({"값": c.get("값"), "단위": re.sub(r"\s*/.*$", "", str(c.get("단위")))}):
                        continue
                    없음 = [v for v in _수들(c.get("값")) if not 있나(v)]
                    if 없음:
                        soft.append(f"장.{i}({장['유형']}).{p} 지표타일 값 {c.get('값')}{c.get('단위') or ''} 이 자료에 없다 — "
                                    "자료 수치를 옮기거나, 계산했으면 산출[]에 등록한다")
    요 = 요청장수(의도)
    # 장 수는 렌더 쪽수로 센다 — 첫 장이 표지가 아니면 조립기가 표지를 붙인다(round2 적대 검토 §3-H: 게이트 5장·렌더 6쪽)
    쪽수 = len(장들) + (0 if 장들 and 장들[0].get("유형") == "표지" else 1)
    if 요 and not (요[1] <= 쪽수 <= 요[2]):
        메모 = any("장수" in str(m) or "분량" in str(m) for 장 in 장들
                 for m in ((장.get("노트") or {}).get("메모") or [] if isinstance(장.get("노트"), dict) else []))
        # 까닭을 노트.메모에 적었으면 soft 를 내지 않는다 — 웹앱 소프트 재시도가 '!' 줄을 '해소하라'로 되먹여, 자료가 모자란
        # 덱을 부풀리라고 떠밀었다(round2 적대 검토 규칙 §2-C · 판_채우기_v2 '억지로 늘리지 않는다')
        if not 메모:
            soft.append(f"요청 장수 {요[0]}장 안팎({요[1]}~{요[2]}장)인데 {쪽수}장 — 자료가 모자라면 까닭을 노트.메모에 "
                        "'장수: …'로 적고, 아니면 범위 안으로 맞춘다")
    # ⑫ 마무리 — 6장 이상 덱은 마무리 장을 둔다. 보고: 한 줄 요약·다음 일정 / 설득: 요청 재확인 한 줄은 된다
    본문 = [j for j in 장들 if j["유형"] not in ("표지", "목차", "간지")]
    마 = [i for i, j in enumerate(장들) if j["유형"] == "마무리"]
    if len(장들) >= 6 and not 마:
        soft.append("마무리 장이 없다 — " + ("보고는 한 줄 요약(문구 — 앞 장 수치는 다시 적지 않는다)·다음 일정(부문구 — 자료에 있는 일정만)으로" if 목적 == "보고" else
                                     "설득은 요청 장 뒤에 요청을 한 줄로 되새기고(금액 되새김은 한 번까지) 문의처로"
                                     if 목적 == "설득" else "설명은 행동(신청·문의)과 문의처로") + " 맺는다")
    for i in 마:
        m = 장들[i].get("마무리") or {}
        글 = 글자(m.get("문구")) + " " + str(m.get("부문구") or "")
        if 목적 == "보고" and any(w in 글 for w in _인사말):
            soft.append(f"장.{i}(마무리) 인사·다짐 문구('{글.strip()[:20]}') — 보고 마무리는 한 줄 요약과 다음 일정(자료에 있는 일정만)")
    # ⑮ 목차 — 10장 이하 덱은 목차 장을 두지 않는다(번호 맞춤은 조립기가 한다)
    if any(j["유형"] == "목차" for j in 장들) and len(장들) <= 10:
        soft.append(f"{len(장들)}장 덱에 목차 장 — 10장 이하는 목차를 두지 않는다(한눈에보기가 길잡이)")
    # ⑯·④ 머리·요지띠·요지·리드·카드 항목에 자료에 없는 판단·인과('추가 검토 필요'·'효과 확인'·'~를 위한'·'대응 목적') —
    # 강한 경로 soft · 약한 경로(서버 모델)는 슬라이드v2.검사 가 같은 목록을 hard 로 올린다(bench13 ④). 자료 글이 없으면
    # (플러그인 원문 없이 부름) 무엇이 자료 밖인지 모르므로 조용하다 — 예전엔 자료 없이도 목록 말만 보면 울렸다.
    본장 = set()
    for 자리, t, w in 판단인과걸림(doc, 의도 if isinstance(의도, str) else ""):
        i = int(자리.split(".")[1])
        if i in 본장:
            continue
        본장.add(i)
        soft.append(f"{자리}({장들[i]['유형']}) '{t[:28]}' — 자료에 없는 판단·인과('{w}')일 수 있다. 자료의 사실·수치만 적는다")
    # ② 같은 수치 되풀이 — 세 장 이상·한 장 세 번 이상(soft)
    덱되, 장되 = 수치되풀이(doc)
    soft.extend(덱되 + 장되)


# ── 그린 값 = 적힌 값 — 조립된 HTML 의 차트 기하를 되읽어 화면 글 숫자와 대 본다('26-09-29 bench11) ──
# 심사 3인이 도넛 64% 를 약 40% 로(링 dash 주기가 둘레보다 길어 12시 앞 구간이 사라짐), 점눈금 145 를
# 152 자리에(눈금 글을 flex 로 고르게 벌려 눈금 값과 자리가 어긋남) 그린 것을 잡았다. JSON 게이트는
# 그림을 안 보므로, 조립기가 낸 기하(링 stroke-dash*, 점눈금 --v·눈금 자리, 막대·띠·진행 --v/--w, 선차트
# 점 y ↔ 눈금 격자)를 CSS 배치 규칙 그대로 풀어 값으로 되돌리고, 그 장에 찍힌 글 숫자와 1% 안인지 본다.
# 배치 규칙: 링 = 둘레 2πr·12시(경로 3/4 지점)부터 시계 방향. 점눈금 = left:(v-min)/(max-min), 눈금 글은
# --v 가 있으면 그 자리, 없으면 flex space-between(첫 0 · 끝 100%). 문턱 = 축 폭(또는 100%)의 1%.
from html.parser import HTMLParser as _HP


class _마디:
    __slots__ = ("태그", "속", "자식", "글", "부모")

    def __init__(self, 태그, 속, 부모):
        self.태그, self.속, self.자식, self.글, self.부모 = 태그, 속, [], [], 부모

    def 틀(self):
        return set((self.속.get("class") or "").split())

    def 모든글(self):
        out = list(self.글)
        for c in self.자식:
            out.append(c.모든글())
        return "".join(out)

    def 찾기(self, 조건):
        for c in self.자식:
            if 조건(c):
                yield c
            yield from c.찾기(조건)


class _나무(_HP):
    _빈 = {"meta", "link", "br", "img", "input", "hr", "use", "circle", "line", "polyline", "path", "rect"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.뿌리 = _마디("#", {}, None)
        self.지금 = self.뿌리

    def handle_starttag(self, tag, attrs):
        n = _마디(tag, dict(attrs), self.지금)
        self.지금.자식.append(n)
        if tag not in self._빈:
            self.지금 = n

    def handle_startendtag(self, tag, attrs):
        self.지금.자식.append(_마디(tag, dict(attrs), self.지금))

    def handle_endtag(self, tag):
        n = self.지금
        while n is not None and n.태그 != tag:
            n = n.부모
        if n is not None and n.부모 is not None:
            self.지금 = n.부모

    def handle_data(self, data):
        self.지금.글.append(data)


def _스타일값(n, 이름):
    m = re.search(r"--" + re.escape(이름) + r"\s*:\s*(-?[\d.]+(?:e-?\d+)?)", n.속.get("style") or "")
    return float(m.group(1)) if m else None


def _글수(t, 하나만=False):
    """화면 글 → 첫 숫자(쉼표 뗌). 없으면 None. 하나만이면 숫자가 딱 하나일 때만(모델이 쓴 표시 글 —
    '2,100→3,400건'·'3건 중 2건'처럼 숫자가 여럿이면 어느 것이 그린 값인지 모르니 대 보지 않는다: 정밀도 우선)."""
    수들 = re.findall(r"-?\d[\d,]*(?:\.\d+)?", str(t or ""))
    if not 수들 or (하나만 and len(수들) > 1):
        return None
    return float(수들[0].replace(",", ""))


def _배율글수(t):
    """막대 값 글 → 수(억·천만·백만·만·천 배율을 곱한다 — '4.2억'·'9,500만'을 같은 자로 대 보려고, round2 적대 검토 N4).
    숫자가 둘 이상이면 None(어느 것이 그린 값인지 모른다)."""
    글 = str(t or "")
    수들 = re.findall(r"-?\d[\d,]*(?:\.\d+)?", 글)
    if len(수들) != 1:
        return None
    v = float(수들[0].replace(",", ""))
    m = re.search(re.escape(수들[0]) + r"\s*(조|억|천만|백만|만|천)", 글)
    return v * (_배율[m.group(1)] if m else 1.0)


def _링덮음(L, G, O, C, 칸=3600):
    """stroke-dasharray L G · dashoffset O 인 원(둘레 C)에서 칠해진 경로 조각 — (비율, 시작 비율)."""
    P = (L + G) or 1.0
    칠 = [((k + 0.5) / 칸 * C + O) % P < L for k in range(칸)]
    비 = sum(칠) / 칸
    시작 = None
    for k in range(칸):                          # 칠 안 된 칸 바로 다음의 칠 된 칸 = 호의 시작
        if 칠[k] and not 칠[k - 1]:
            시작 = k / 칸
            break
    return 비, 시작


def 차트되읽기(html_):
    """[(장 번호(1부터), 부품, 경로, 말)] — 그림에서 되읽은 값이 화면 글 숫자와 1% 넘게 어긋난 곳."""
    나무 = _나무()
    나무.feed(html_)
    out = []
    쪽 = [n for n in 나무.뿌리.찾기(lambda n: n.태그 == "section" and "sl-page" in n.틀())]
    for 번호, sec in enumerate(쪽, 1):
        # ① 비율링
        for 카 in sec.찾기(lambda n: n.속.get("data-ent") == "비율링"):
            호 = next(카.찾기(lambda n: n.태그 == "circle" and "ring-val" in n.틀()), None)
            수 = next(카.찾기(lambda n: "num" in n.틀()), None)
            적힌 = _글수(수.모든글(), 하나만=True) if 수 is not None else None
            if 적힌 is None:
                continue
            if 호 is None:
                if 적힌 > 1:
                    out.append((번호, "비율링", 카.속.get("data-path"), f"호가 없는데 {적힌:g}% 라고 적혀 있다"))
                continue
            try:
                r = float(호.속.get("r") or 56)
                L, G = [float(x) for x in re.split(r"[\s,]+", (호.속.get("stroke-dasharray") or "").strip())[:2]]
                O = float(호.속.get("stroke-dashoffset") or 0)
            except ValueError:
                out.append((번호, "비율링", 카.속.get("data-path"), "호 dash 값을 읽지 못했다"))
                continue
            C = 2 * 3.141592653589793 * r
            비, 시작 = _링덮음(L, G, O, C)
            if (호.속.get("stroke-linecap") or "butt") in ("round", "square") and 0 < 비 < 1:
                # 둥근·네모 끝은 호 양끝에 굵기 절반씩 더 칠한다 — 보이는 호 = dash + 굵기(round2 적대 검토 H2: +4.5%p)
                비 = min(1.0, 비 + float(호.속.get("stroke-width") or 0) / C)
            if abs(비 * 100 - 적힌) > 1:
                out.append((번호, "비율링", 카.속.get("data-path"), f"호가 {비 * 100:.0f}% 인데 {적힌:g}% 라고 적혀 있다"))
            elif 시작 is not None and 0 < 비 < 1 and abs(시작 - 0.75) > 0.01:
                out.append((번호, "비율링", 카.속.get("data-path"), f"호가 12시가 아닌 곳({시작 * 360 + 90:.0f}°)에서 시작한다"))
        # ② 점눈금
        for 판 in sec.찾기(lambda n: "dotscale" in n.틀()):
            lo, hi = _스타일값(판, "min"), _스타일값(판, "max")
            if lo is None or hi is None or hi <= lo:
                continue
            틱판 = next(판.찾기(lambda n: "dotscale__ticks" in n.틀()), None)
            틱 = [c for c in (틱판.자식 if 틱판 is not None else []) if c.태그 == "span"]
            자리들 = []
            for k, t in enumerate(틱):
                v = _스타일값(t, "v")
                x = ((v - lo) / (hi - lo)) if v is not None else (k / max(1, len(틱) - 1))
                값 = _글수(t.모든글())
                if 값 is not None:
                    자리들.append((x, 값))
            for pt in 판.찾기(lambda n: "dotscale__pt" in n.틀()):
                v = _스타일값(pt, "v")
                파 = [c for c in pt.찾기(lambda n: n.속.get("data-derived") == "1")]
                적힌 = _글수(파[0].모든글()) if 파 else None
                if v is None or 적힌 is None:
                    continue
                if not (lo - (hi - lo) * 0.01 <= 적힌 <= hi + (hi - lo) * 0.01):
                    # 축 밖 값 — 조립기는 이제 축을 값까지 넓힌다. 그래도 밖이면 끝에 붙여 그린 거짓 그림이다
                    # (round2 적대 검토 M3: 저장 경로에서 축 0~100·값 130 이 100 자리에 '130'으로 찍혔다)
                    out.append((번호, "점눈금", "", f"값 {적힌:g} 이 축 {lo:g}~{hi:g} 밖인데 축 끝에 찍혔다"))
                    continue
                x = (v - lo) / (hi - lo)
                if abs(v - 적힌) > (hi - lo) * 0.01:
                    out.append((번호, "점눈금", 판.부모.속.get("data-path") if 판.부모 else "", f"점 --v {v:g} 인데 {적힌:g} 라고 적혀 있다"))
                    continue
                if len(자리들) >= 2:
                    (x0, a), (x1, b) = 자리들[0], 자리들[-1]
                    읽음 = a + (x - x0) / ((x1 - x0) or 1) * (b - a)
                    if abs(읽음 - 적힌) > (hi - lo) * 0.01:
                        out.append((번호, "점눈금", "", f"점이 눈금으로 {읽음:.1f} 자리에 찍혔는데 {적힌:g} 라고 적혀 있다"))
        # ③ 가로막대(척도 최댓값: 길이 비 = 값 비 / 백분율: 길이 = 값) · 구성띠 · 진행막대
        for 판 in sec.찾기(lambda n: "hbar" in n.틀() and n.태그 == "div"):
            줄 = []
            for 행 in 판.자식:
                if "hbar__row" not in 행.틀():
                    continue
                값칸 = next(행.찾기(lambda n: "hbar__val" in n.틀()), None)
                줄.append((_스타일값(행, "v"), _배율글수(값칸.모든글()) if 값칸 is not None else None))
            줄 = [(l, v) for l, v in 줄 if l is not None and v is not None and v >= 0]
            if 판.속.get("data-scale") == "pct":
                # 척도 백분율 — 길이 = 값(100 에서 멈춤). 비율만 대 보면 60·30 을 최댓값 비(100·50)로 그려도 통과했다(M2)
                for l, v in 줄:
                    if abs(l - min(100.0, v)) > 1:
                        out.append((번호, "가로막대", "", f"백분율 막대 길이 {l:g}% 인데 {v:g}% 라고 적혀 있다"))
                continue
            if len(줄) >= 2:
                큰 = max(줄, key=lambda x: x[1])
                if 큰[1] > 0 and 큰[0] > 0:
                    for l, v in 줄:
                        if abs(l / 큰[0] - v / 큰[1]) > 0.01:
                            out.append((번호, "가로막대", "", f"막대 길이 비 {l / 큰[0]:.3f} ↔ 값 비 {v / 큰[1]:.3f}"))
        for 판 in sec.찾기(lambda n: "share" in n.틀() and n.태그 == "div"):
            막 = [_스타일값(c, "w") for c in 판.찾기(lambda n: "share__seg" in n.틀())]
            표 = [_글수(c.모든글()) for c in 판.찾기(lambda n: "share__pct" in n.틀())]
            for w, t in zip(막, 표):
                if w is not None and t is not None and abs(w - t) > 1:
                    out.append((번호, "구성띠", "", f"조각 폭 {w:g}% 인데 {t:g}% 라고 적혀 있다"))
        for 판 in sec.찾기(lambda n: "progress" in n.틀() and n.태그 == "div"):
            v = _스타일값(판, "v")
            범 = next(판.찾기(lambda n: "progress__legend" in n.틀()), None)
            끝 = [c for c in (범.자식 if 범 is not None else []) if c.태그 == "span"]
            t = _글수(끝[-1].모든글()) if 끝 else None
            if v is not None and t is not None and abs(v - min(t, 100)) > 1:
                out.append((번호, "진행막대", "", f"막대 {v:g}% 인데 {t:g}% 라고 적혀 있다"))
        # ④ 선차트 — 눈금 격자(y ↔ 눈금 글)로 점 y 를 값으로 되돌려, 점 옆 글(끝값·점 라벨)과 대 본다
        for svg in sec.찾기(lambda n: n.태그 == "svg" and "lc" in n.틀() and "ring" not in n.틀()):
            격 = [float(n.속["y1"]) for n in svg.자식 if n.태그 == "line" and "lc-grid" in n.틀()]
            눈 = [(float(n.속["y"]) - 5, _글수(n.모든글())) for n in svg.자식
                 if n.태그 == "text" and "lc-t" in n.틀() and n.속.get("text-anchor") == "end"]
            눈 = [(y, v) for y, v in 눈 if v is not None]
            if len(눈) < 2 or len(격) < 2:
                continue
            (y0, a), (y1, b) = 눈[0], 눈[-1]
            if y0 == y1:
                continue
            읽 = lambda y: a + (y - y0) / (y1 - y0) * (b - a)   # noqa: E731
            범위 = abs(b - a) or 1
            점 = [(float(n.속["cx"]), float(n.속["cy"])) for n in svg.자식 if n.태그 == "circle"]
            for n in svg.자식:
                if n.태그 != "text" or not ({"lc-lab", "lc-endlab", "lc-acclab"} & n.틀()):
                    continue
                t = _글수(n.모든글())
                x = float(n.속.get("x") or 0)
                y = float(n.속.get("y") or 0)
                곁 = [p for p in 점 if abs(p[0] - x) < 1.5]
                if t is None or not 곁:
                    continue
                cy = min(곁, key=lambda p: abs(p[1] - y))[1]
                if abs(읽(cy) - t) > 범위 * 0.01:
                    out.append((번호, "선차트", "", f"점이 눈금으로 {읽(cy):.2f} 자리인데 {t:g} 라고 적혀 있다"))
    return out


def 지표(doc):
    유형열 = [장.get("유형") for 장 in doc.get("장") or [] if isinstance(장, dict)
            and 장.get("유형") not in ("표지", "목차", "간지", "마무리")]
    연속, 최대, 앞 = 0, 0, None
    for t in 유형열:
        연속 = 연속 + 1 if t == 앞 else 1
        최대 = max(최대, 연속)
        앞 = t
    return {"장": len(doc.get("장") or []), "종류": len(set(유형열)), "최대연속": 최대}


if __name__ == "__main__":
    doc = json.load(open(sys.argv[1], encoding="utf-8"))
    if isinstance(doc, list):
        doc = doc[0]
    hard, soft = 검사(doc, "--약한모델" in sys.argv)
    for h in hard:
        print("HARD", h)
    for s in soft:
        print("soft", s)
    print(f"결과: hard {len(hard)} · soft {len(soft)}")
    sys.exit(1 if hard else 0)
