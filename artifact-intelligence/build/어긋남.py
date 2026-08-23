#!/usr/bin/env python3
"""자료가 서로 어긋난 자리를 **짚는다.**

    python3 build/어긋남.py <자료1> <자료2> [...]

사장님 판정(2026-08-05, 목차로직 `_판정.자료가_어긋나면_짚어서_묻는다`):
  파일과 대화가 같은 사실을 다르게 말하면 **한쪽을 골라 조용히 따르지 않는다.**
  어긋난 자리를 짚어 되묻는다.
  까닭 — 대화를 우선하면 말이 틀렸을 때 파일의 사실이 조용히 지워지고,
  파일을 우선하면 "그건 바뀌었어요" 를 못 받는다. 둘 다 **틀린 것을 소리 없이
  통과시키는** 길이다.

무엇을 어긋남으로 보는가 — **같은 것을 가리키는데 수가 다른 것**만 본다.
  · "우산 1만개" ↔ "우산 2만개"  → 어긋남
  · "10월 출시" ↔ "11월 출시"    → 어긋남
  · 한쪽에만 있는 사실            → 어긋남이 아니다(자료를 보태는 것이 정상이다)

어떻게 찾는가 — 수 앞뒤의 **말 꼬리**를 열쇠로 삼는다. 같은 열쇠에 다른 수가
붙으면 짚는다. 문장 뜻을 읽지 않으므로 놓치는 것이 있다 — 그건 아래에 적어 둔다.

**한계(적어 둔다)**
  · 같은 사실을 아주 다른 말로 적으면 못 잡는다("우산 1만개" ↔ "양산 20,000").
  · 단위가 다르면 못 잡는다("1만개" ↔ "10,000개" 는 잡지만 "1만" ↔ "1.0만" 은 놓칠 수 있다).
  · 그래서 이 자는 **어긋남이 없다**를 증명하지 못한다. 있는 것을 짚을 뿐이다.
"""
from __future__ import annotations

import html as htmlmod
import re
import sys
from pathlib import Path


def 민글(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


# 수 + 단위. 공공문서에서 실제로 쓰는 것만 — 지어내지 않는다.
_수 = re.compile(r"(?P<수>\d[\d,]*(?:\.\d+)?)\s*"
                 r"(?P<단위>만\s*개|천\s*개|개|명|건|대|기|억원|만원|원|%|퍼센트|"
                 r"월|일|년|시간|분|㎡|km|m|주|차|회|쪽|부)")
_꼬리 = re.compile(r"[가-힣A-Za-z]{2,}")
# 열쇠를 만들 때 **조사를 뗀다.** 안 떼면 '우산' 과 '우산은' 이 서로 다른 열쇠가 되어
# 뻔한 어긋남을 못 잡는다(2026-08-05 A-3 7번에서 실제로 그랬다 — 1만개↔2만개를 놓쳤다).
_조사떼기 = re.compile(r"(은|는|이|가|을|를|와|과|의|도|만|에|에서|으로|로|부터|까지|"
                     r"이라|라|이며|며)$")


def _열쇠낱말(w: str) -> str:
    깎 = _조사떼기.sub("", w)
    return 깎 if len(깎) >= 2 else w


def 재기(글: str) -> dict[str, list[tuple[str, str]]]:
    """{열쇠: [(값, 그 자리 글)]} — 열쇠는 수 **앞의 마지막 낱말**이다."""
    t = 민글(글)
    나온다: dict[str, list[tuple[str, str]]] = {}
    for m in _수.finditer(t):
        앞 = t[max(0, m.start() - 24):m.start()]
        낱말 = _꼬리.findall(앞)
        if not 낱말:
            continue
        열쇠 = _열쇠낱말(낱말[-1])
        단위 = re.sub(r"\s+", "", m.group("단위"))
        값 = _맞춤(m.group("수"), 단위)
        나온다.setdefault(f"{열쇠}|{_단위갈래(단위)}", []).append(
            (값, t[max(0, m.start() - 20):m.end() + 10].strip()))
    return 나온다


def _단위갈래(u):
    """만개·천개·개는 같은 갈래다 — 수를 맞춰 견주려고."""
    if u in ("만개", "천개", "개"):
        return "개"
    if u in ("억원", "만원", "원"):
        return "원"
    if u in ("%", "퍼센트"):
        return "%"
    return u


def _맞춤(수: str, 단위: str) -> str:
    """만·천을 풀어 같은 자리에서 견준다."""
    v = float(수.replace(",", ""))
    if 단위.startswith("만"):
        v *= 10000
    elif 단위.startswith("천"):
        v *= 1000
    elif 단위 == "억원":
        v *= 100000000
    elif 단위 == "만원":
        v *= 10000
    return f"{v:g}"


def 견주기(자료들: list[tuple[str, str]]) -> list[dict]:
    """[(이름, 글)] 을 받아 어긋난 자리를 돌려준다."""
    잰것 = [(이름, 재기(글)) for 이름, 글 in 자료들]
    열쇠들 = set()
    for _, d in 잰것:
        열쇠들 |= set(d)

    어긋남 = []
    for 열쇠 in sorted(열쇠들):
        가진곳 = [(이름, d[열쇠]) for 이름, d in 잰것 if 열쇠 in d]
        if len(가진곳) < 2:
            continue                       # 한쪽에만 있는 것은 어긋남이 아니다
        값들 = {}
        for 이름, 목록 in 가진곳:
            for 값, 자리 in 목록:
                값들.setdefault(값, []).append((이름, 자리))
        if len(값들) < 2:
            continue                       # 값이 같으면 어긋난 게 아니다
        낱말, 갈래 = 열쇠.split("|")
        어긋남.append({
            "무엇": 낱말, "단위": 갈래,
            "값들": [{"값": v, "어디": [{"자료": n, "자리": s} for n, s in ns]}
                   for v, ns in sorted(값들.items())],
        })
    return 어긋남


def 물음말(어긋남: list[dict]) -> str:
    """사람에게 보일 되묻는 말. **고르지 않는다** — 어긋난 자리를 보이고 묻는다."""
    if not 어긋남:
        return ""
    줄 = ["넣어 주신 자료가 서로 다른 곳이 있습니다. 어느 쪽이 맞습니까?", ""]
    for i, x in enumerate(어긋남, 1):
        줄.append(f"{i}. 「{x['무엇']}」")
        for v in x["값들"]:
            곳 = " · ".join(f"{a['자료']}: …{a['자리']}…" for a in v["어디"][:2])
            줄.append(f"   · {v['값']} {x['단위']}   ({곳})")
        줄.append("")
    줄.append("고르시면 그대로 씁니다. 어느 쪽도 아니면 맞는 값을 알려 주세요.")
    return "\n".join(줄)


if __name__ == "__main__":
    자료 = []
    for p in sys.argv[1:]:
        자료.append((Path(p).name, Path(p).read_text(encoding="utf-8")))
    if len(자료) < 2:
        raise SystemExit("자료를 둘 이상 주세요")
    x = 견주기(자료)
    if not x:
        print("✓ 수가 어긋난 자리 없음")
        print("  (뜻이 어긋난 것은 이 자가 못 본다 — 머리말의 한계 참고)")
        sys.exit(0)
    print(물음말(x))
    sys.exit(1)
