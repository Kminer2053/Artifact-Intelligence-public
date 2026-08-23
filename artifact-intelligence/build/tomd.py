#!/usr/bin/env python3
"""3층 JSON → 마크다운. HWPX 로 가는 다리이자, 그 자체로 산출물이다.

왜 마크다운을 거치나: kordoc generate 가 마크다운을 받아 공문서 HWPX 를 만든다.
슬롯 채우기(옛 방식)와 달리 문서 길이·구조에 제약이 없다.

**위계를 한 단 들여쓴다.** kordoc 은 목록 첫 단에 □ 를 준다. 우리는 절 제목(h2)이
이미 □ 이므로, 항목은 그 아래(○)에서 시작해야 위계가 맞는다. 안 들여쓰면
○ 항목이 □ 로 나온다(2026-08-05 실측 확인).
"""
import json
import re
import sys

# 진짜 HTML 태그만 지운다. `<고객지원처, '26. 7. 25.>` 같은 꺾쇠 표기를 태그로 보면
# 내용이 통째로 사라진다(2026-08-05에 byline 이 빈 채로 나갔다).
태그 = re.compile(r"</?(?:span|b|u|i|em|strong|br|p|div|lb)\b[^>]*/?>", re.I)


def 벗김(h):
    return 태그.sub("", str(h or "")).strip()


def 표를(t):
    if not t or not t.get("header"):
        return []
    줄 = []
    if t.get("캡션") or t.get("caption"):
        줄.append(f"*{t.get('캡션') or t.get('caption')}*")
    줄.append("| " + " | ".join(str(x) for x in t["header"]) + " |")
    줄.append("|" + "---|" * len(t["header"]))
    for r in t.get("rows") or []:
        줄.append("| " + " | ".join(str(x) for x in r) + " |")
    줄.append("")
    return 줄


def 마크다운(doc):
    장르 = doc.get("genre") or "onepage"
    제목 = (doc.get("title") or doc.get("제목") or doc.get("제명")
          or (doc.get("표지") or {}).get("제목") or doc.get("filename"))
    줄 = [f"# {제목}", ""]
    if doc.get("byline"):
        줄 += [벗김(doc["byline"]).strip("<>"), ""]
    if doc.get("summary"):
        줄 += [f"> {벗김(doc['summary'])}", ""]

    def 마디(items, 표=None, 절이름=None):
        out = []
        for it in items or []:
            글 = 벗김(it.get("html") or it.get("text") or it)
            if not 글:
                continue
            lv = int(it.get("level") or 2) if isinstance(it, dict) else 2
            out.append("  " * max(lv - 1, 0) + "- " + 글)
        out.append("")
        if 표 and 표.get("after_heading") == 절이름:
            out += 표를(표)
        return out

    표 = doc.get("table")
    for sec in doc.get("sections") or []:
        줄 += [f"## {sec.get('heading') or ''}", ""]
        줄 += 마디(sec.get("items"), 표, sec.get("heading"))

    # 다른 장르 — 본문이 마디 배열로 온다(규정·보도자료·시행문)
    for 마당 in ("본문", "body"):
        for x in doc.get(마당) or []:
            if not isinstance(x, dict):
                continue
            lv = x.get("level")
            글 = 벗김(x.get("text") or "")
            제 = 벗김(x.get("제목") or "")
            if lv in ("장", "절"):
                줄 += [f"## {제}", ""]
            elif lv == "조":
                줄 += [f"## {제}", ""] if 제 else []
                if 글:
                    줄 += ["- " + 글, ""]
            elif 글:
                깊 = {"항": 1, "호": 2, "목": 3}.get(lv, 1)
                줄.append("  " * 깊 + "- " + 글)
        if doc.get(마당):
            줄.append("")

    for 붙 in (doc.get("attach"), doc.get("붙임")):
        if 붙:
            줄 += ["", f"붙임 {벗김(붙) if isinstance(붙, str) else ''}"]
    return "\n".join(줄).rstrip() + "\n"


if __name__ == "__main__":
    doc = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 \
        else json.load(sys.stdin)
    if isinstance(doc, list):
        doc = doc[0]
    sys.stdout.write(마크다운(doc))
