#!/usr/bin/env python3
"""보도자료 조립기 — JSON → 보도자료 HTML. 머리표·위계 마커 자동 부여.

정본: ontology document_types.press-release (실물 4,523건 전수 실측, 2026-08-01)
  구성  기관 로고 — 문서종류 라벨 — 보도시점·배포 표 — 제목 — 부제 — 리드 — 본문 — 붙임
        문서종류 라벨 89%(첫 문단) · 보도시점 89% · 배포 77% · 붙임 13% · 참고 3%
  문체  bodo — 몸통은 서술 완결(63%), 붙임·요약 항목만 명사형(32%). 하나로 강제하지 않는다
  디자인 본문 14pt(58%)·15pt(34%) · 바탕(45%)·휴먼명조(34%) · 줄간격 160% · 양쪽맞춤 99%
  위계  □ 15pt → ○ 15pt → - 15pt → ※ 12pt (실측 사다리)

**'보도일시'가 아니라 '보도시점'이 실물 표기다** — 보도시점 89% 대 보도일시 2%.

문서 JSON 스키마(build/press-docs.json — 배열):
{
  "filename": "pr-…", "genre": "press-release",
  "기관명": "…", "문서종류": "보도자료|보도참고자료|보도설명자료|동정자료",
  "보도시점": {"방식": "즉시|엠바고|시각지정", "값": "2026. 8. 3.(월) 09:00"},
  "배포": "2026. 8. 1.(금)",
  "제목": "…", "부제": "- … -",
  "리드": "첫 문단. 결론을 여기 담는다(두괄식)",
  "본문": [ {"level": 1~4, "text": "…"} … ],       ← 마커는 넣지 않는다(자동)
  "붙임": ["… 1부."] | [],
  "담당": [{"부서": "…", "직위": "…", "이름": "…", "전화": "…"}]
}

게이트(gate_check)
  · 제목·리드 필수 — 리드가 없으면 두괄식이 아니다
  · 보도시점 필수(실측 89%)
  · 문서종류는 실측에서 나온 넷 중 하나
  · 리드·본문 1~2수준은 서술 완결 — 명사형으로 끝나면 경고(하드 아님).
    실물이 섞여 쓰므로(서술 63% · 명사형 32%) 막지 않고 알린다.

사용: python3 build/assemble_press.py build/press-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import 속성값
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
#
# ★ 산출물 뿌리를 모듈 적재 시점에 상수로 굳히지 않는다(WP-S9). import 로 부르면 모듈이
#   딱 한 번 적재돼 첫 세션 뿌리에 얼어붙고, 이후 모든 세션이 첫 세션 뿌리에 쓴다
#   (WP-S2 세션 오염). 뿌리는 `조립하기()` 가 **호출마다** 다시 푼다.

# 마커 뒤 공백 — 양쪽맞춤이 늘리지 못하게 줄바꿈 없는 공백을 쓴다.
# 보통 공백이면 justify 가 그 자리를 벌려 마커와 글이 멀어진다(실제로 그랬다).
# 복붙하면 보통 공백으로 붙으므로 '□글' 처럼 붙는 일도 없다.
NBSP = "&#160;"

# 실측 사다리 — □ 15pt → ○ 15pt → - 15pt → ※ 12pt
마커 = {1: "□", 2: "○", 3: "-", 4: "※"}
문서종류들 = ("보도자료", "보도참고자료", "보도설명자료", "동정자료", "참고자료")
보도방식 = {"즉시": "배포 즉시 보도 가능", "엠바고": "", "시각지정": ""}

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
    try:
        sys.path.insert(0, os.path.join(ROOT, "history"))
        import stamp
        # 속성 자리엔 잠금 없는 보간을 하나도 안 남긴다(assemble.기준도장 과 같은 이유)
        return (f'<meta name="기준" '
                f'content="{html.escape(stamp.조판지문("press-release"))}">')
    except Exception:
        return ""


def gate_check(doc):
    """보도자료 꼴을 갖췄는가. 실측에서 예외가 드문 것만 하드로 건다."""
    bad = []
    if not doc.get("제목"):
        bad.append("제목이 없다")
    if not (doc.get("리드") or "").strip():
        bad.append("리드가 없다 — 첫 문단에 결론을 담는 것이 보도자료의 골격이다")
    # 보도시점은 비면 '즉시'로 안전하게 기본을 준다(render 참조) — 예전엔 하드 거부해 초안·HWPX 를
    # 막았다(코덱스·커서 교차 테스트 지적, 2026-08-24). 정확한 시점 되묻기는 에이전트(SKILL) 몫이고,
    # 게이트는 초안이 나가게 두는 초안 도구 규범을 따른다(제목·리드 같은 내용 흠만 하드로 막는다).
    종류 = doc.get("문서종류")
    if 종류 and 종류 not in 문서종류들:
        bad.append(f"문서종류 '{종류}' — 실측에서 나온 것은 {', '.join(문서종류들)}")
    return bad


def 문체경고(doc):
    """몸통이 서술로 닫히는가. 막지 않고 알린다 — 실물이 섞어 쓴다.

    실측 종결: 명사형 32% · 했다체 23% · 한다체 23% · 이다체 10% · 형용사 7% · 합니다체 5%.
    서술 완결의 합이 63%로 몸통이고 명사형 32%는 붙임·요약 항목 몫이다.
    그래서 리드와 큰 항목(1~2수준)만 서술로 닫혔는지 본다.
    """
    말 = []
    명사형 = re.compile(r"(함|됨|임|음|필요|추진|완료|예상|전망|계획|검토|확대|강화|마련|시행)\.?$")
    if doc.get("리드") and 명사형.search(doc["리드"].strip()):
        말.append("리드가 명사형으로 끝난다 — 리드는 서술로 닫는 자리다")
    for it in doc.get("본문", []):
        t = (it.get("text") or "").strip()
        # 사다리 밖 level 은 여기서 안 잰다(9 = 잴 자리 아님). 예전엔 `it.get("level",9)`
        # 를 곧장 `<= 2` 로 비교해 문자열이 오면 TypeError 로 죽었다 — 그것도 **HTML 을
        # 이미 쓴 뒤에** 죽었다. 값이 틀렸다는 말은 build() 의 속성 잠금이 이미 한다.
        수준 = it.get("level") if it.get("level") in 마커 else 9
        if 수준 <= 2 and len(t) > 18 and 명사형.search(t):
            말.append(f"{it['level']}수준이 명사형으로 끝난다: “{t[:30]}…”")
    return 말[:5]


def build(doc):
    e = html.escape
    DOC_JSON = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    PROFILE_JSON = json.dumps(load_profile("press-release"),
                              ensure_ascii=False).replace("</", "<\\/")
    시점 = doc.get("보도시점") or {}
    방식 = 시점.get("방식") or ("시각지정" if 시점.get("값") else "즉시")   # 비면 '즉시'가 안전한 기본
    시점값 = 시점.get("값") or 보도방식.get(방식, "")
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="press-release">
<head>
<meta charset="utf-8">{기준도장()}
<title>{e(doc.get("제목", ""))}</title>
<link rel="stylesheet" href="../tokens.css?v=">
<link rel="stylesheet" href="../press.css?v=">
</head>
<body>
<script type="application/json" id="fr-doc">{DOC_JSON}</script>
<script type="application/json" id="fr-profile">{PROFILE_JSON}</script>
<div class="pr-sheet">
  <div class="pr-head">
    <div class="pr-org" data-ent="머리"><span class="tx" data-path="기관명">{e(doc.get("기관명", ""))}</span></div>
    <div class="pr-kind" data-ent="머리"><span class="tx" data-path="문서종류">{e(doc.get("문서종류", "보도자료"))}</span></div>
  </div>
  <table class="pr-when" data-ent="보도시점">
    <tr><th>보도시점</th><td><span class="tx" data-path="보도시점.값">{e(시점값)}</span></td></tr>
    <tr><th>배포</th><td><span class="tx" data-path="배포">{e(doc.get("배포", ""))}</span></td></tr>
  </table>
  <h1 class="pr-title" data-ent="제목"><span class="tx" data-path="제목">{e(doc.get("제목", ""))}</span></h1>
"""]
    if doc.get("부제"):
        parts.append(f'  <p class="pr-sub" data-ent="부제">'
                     f'<span class="tx" data-path="부제">{e(doc["부제"])}</span></p>\n')
    parts.append(f'  <div class="pr-body">\n')
    if doc.get("리드"):
        parts.append(f'    <p class="pr-lead" data-ent="리드">'
                     f'<span class="tx" data-path="리드">{e(doc["리드"])}</span></p>\n')
    for i, it in enumerate(doc.get("본문", [])):
        if "표" in it:
            tb = it["표"]
            cap = (f'<div class="pr-tbl-caption">{e(tb.get("캡션", ""))}</div>'
                   if tb.get("캡션") else "")
            rows = "<tr>" + "".join(f"<th>{e(h)}</th>" for h in tb.get("header", [])) + "</tr>"
            for row in tb.get("rows", []):
                rows += "<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>"
            parts.append(f'    <div class="pr-table-wrap" data-ent="표" '
                         f'data-path="본문.{i}.표">{cap}'
                         f'<table class="pr-table">{rows}</table></div>\n')
            continue
        # level 은 `class="pr-l{lv}"` 로 **속성 자리**에 들어간다 — 위 실측 사다리
        # `마커` 표의 열쇠 넷이 곧 값 집합이다(press.css 의 .pr-l1~4 와 짝). 예전엔
        # 값을 그대로 보간해 `1" onmouseover="…" x="` 로 <p> 에 라이브 핸들러를
        # 붙일 수 있었다(2026-08-07 크롬 실측 — 다섯 조립기가 같은 부류였다).
        lv = 속성값.열거(it.get("level"), tuple(마커), f"본문.{i}.level", 기본=1)
        mk = 마커.get(lv, "-")
        parts.append(f'    <p class="pr-l{lv}" data-ent="항목">'
                     f'<span class="mk">{mk}</span>{NBSP}'
                     f'<span class="tx" data-path="본문.{i}.text">{e(it.get("text", ""))}</span>'
                     f'</p>\n')
    att = [a for a in doc.get("붙임", []) if a.strip()]
    for ai, a in enumerate(att):
        라벨 = "붙임" if ai == 0 else ""
        번호 = f" {ai + 1}." if len(att) > 1 else ""
        parts.append(f'    <p class="pr-attach" data-ent="붙임">'
                     f'<span class="mk">{라벨}{번호}</span>{NBSP}'
                     f'<span class="tx" data-path="붙임.{ai}">{e(a)}</span></p>\n')
    parts.append("  </div>\n")
    # 담당 — 실물은 문서 끝에 둔다
    담당 = doc.get("담당") or []
    if 담당:
        parts.append('  <table class="pr-contact" data-ent="담당">\n')
        parts.append("    <tr><th>담당 부서</th><th>직위</th><th>성명</th><th>전화</th></tr>\n")
        for ci, c in enumerate(담당):
            parts.append(
                "    <tr>"
                + "".join(f'<td><span class="tx" data-path="담당.{ci}.{k}">'
                          f'{e(c.get(k, ""))}</span></td>'
                          for k in ("부서", "직위", "이름", "전화"))
                + "</tr>\n")
        parts.append("  </table>\n")
    parts.append("""</div>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


def 조립하기(등록부경로, only=None, out=None):
    """보도자료 등록부 → HTML. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 게이트 위반 문서는 안
    쓰고 ok=False 가 된다. 산출물뿌리를 **호출마다** 다시 푼다(세션 오염 방지).
    `out` 을 주면(=--out) 그 자리로 뽑는다.
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
        bad = gate_check(doc)
        if bad:
            fail = 1
            로그.append(f"[게이트 위반] {doc['filename']}")
            for b in bad:
                로그.append(f"  ✗ {b}")
            continue
        with 자료뿌리.쓰기(os.path.join(낼곳, f"{doc['filename']}.html")) as f:
            f.write(genres.판찍기(build(doc)))   # 원자 쓰기(WP-S2 ③)
        낸것.append(f"{doc['filename']}.html")
        로그.append(f"built: {doc['filename']}.html")
        for w in 문체경고(doc):
            로그.append(f"  ⚠ {w}")
    return {"ok": fail == 0, "낸것": 낸것, "로그": "\n".join(로그)}


def main():
    # --out DIR 로 다른 곳에 뽑을 수 있다(history/stamp.py). 정본을 안 건드리고 뽑는다.
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
