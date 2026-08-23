#!/usr/bin/env python3
"""규정(내규·사규) 조립기 — JSON → 규정 HTML. 조문 번호 자동 부여.

정본: ontology document_types.regulation (실물 23건 전수 실측, 2026-08-01)
  구성  제명 — (제N장) — 제N조(조제목) — 부칙. 제1조 100% · 부칙 100% · 제1장 78%
  문체  jomun(조문체) — 한다체 85% + 형용사 종결 13% = 98%. 합니다체 금지
  디자인 전 위계 같은 크기(14pt) · 위계는 굵게로만 가른다
        (제N장 96% · 제N조 90% · 제N절 78% 굵게 / 항·호·목 0~5%)

문서 JSON 스키마(build/regulation-docs.json — 배열):
{
  "filename": "reg-…", "genre": "regulation",
  "기관명": "…", "제명": "정보화업무처리 규정", "규정번호": "규정 제8호",
  "본문": [                       ← 번호는 넣지 않는다(자동)
    {"level": "장", "제목": "총칙"},
    {"level": "절", "제목": "통칙"},
    {"level": "조", "제목": "목적", "text": "이 규정은 …을 목적으로 한다."},
    {"level": "항", "text": "…"},
    {"level": "호", "text": "…"},
    {"level": "목", "text": "…"}
  ],
  "부칙": [{"호": "제2019-26호", "일자": "2019. 6. 27.", "본문": ["이 규정은 … 시행한다."]}],
  "별표": [{"번호": 1, "제목": "…", "표": {"header": [...], "rows": [[...]]}}]
}

조판 규범 — 실물에서 그대로 가져왔다
  · **첫 항은 조 제목과 같은 줄에 붙는다.** "제6조(국외 출장) ① 국외 출장 시 …"
  · **항이 하나뿐이면 ① 을 붙이지 않는다.** "제8조(병가) 병가에 대해서는 …"
    (시행문의 '항목 하나뿐이면 기호 미부여'와 같은 규범)
  · 조는 둘째 줄부터 2글자 들여쓴다(내어쓰기 -10.4mm 실측)
  · 항 이하는 제 깊이만큼 통째로 들여쓴다(항 2글자 · 호 4글자 · 목 6글자)
    ※ 실측 앞칸은 항 2 · 호 2 · 목 4 인데, 호가 항 없이 조 바로 아래 오는 문서가
      많아서 그렇다. 그래서 기호가 아니라 **JSON 안 깊이**로 들여쓴다 — 두 경우가
      다 맞게 나온다.

게이트(gate_check)
  · 제1조가 있어야 한다(실측 100%)
  · 부칙이 있어야 한다(실측 100%)
  · 합니다체 금지(조문체 규범, 실측 0.1%)

사용: python3 build/assemble_regulation.py build/regulation-docs.json
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
    items = doc.get("본문", [])
    if not any(it.get("level") == "조" for it in items):
        bad.append("조가 하나도 없다 — 규정은 조로 이루어진다(실측 100%)")
    if not doc.get("부칙"):
        bad.append("부칙이 없다 — 시행일을 정하는 자리다(실측 23/23건)")
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
        "제6조(국외 출장) ① 국외 출장 시 …" 처럼 조 줄이 곧 첫 항이다.
        그래서 뒤에 항이 따라오면 조 본문에 ① 을 붙이고 다음 항은 ② 부터 센다.
        항이 안 따라오면 번호를 아예 안 붙인다("제8조(병가) 병가에 대해서는 …").
      ② 호가 항 없이 조 바로 아래 오는 규정이 많다. 그때 호는 항 자리(한 칸)에 선다.
        이름표로 "호=두 칸"이라고 박으면 그런 조가 통째로 밀린다.
        실측 앞칸이 항 2 · 호 2 · 목 4 로 나온 것이 바로 이 때문이다.

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


def build(doc):
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
    <div class="rg-org" data-ent="머리" data-path="기관명">{e(doc.get("기관명", ""))}</div>
    <h1 class="rg-title" data-ent="제명" data-path="제명">{e(doc.get("제명", ""))}</h1>
    <div class="rg-no" data-ent="머리" data-path="규정번호">{e(doc.get("규정번호", ""))}</div>
  </div>
  <div class="rg-body">
"""]
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
            parts.append(f'    <p class="rg-{lv}" data-d="{깊}" data-ent="{lv}">'
                         f'<span class="mk-h">{e(기호)}</span>{NBSP}'
                         f'<span class="tx" data-path="{p}.text">{e(it.get("text", ""))}</span>'
                         f'</p>\n')

    # ── 부칙 — 실측 100%. 시행일을 정하는 자리라 규정의 필수 부분이다
    for bi, b in enumerate(doc.get("부칙", [])):
        꼬리 = " ".join(x for x in (b.get("호", ""), b.get("일자", "")) if x)
        머리 = '<h2 class="rg-부칙" data-ent="부칙">부칙'
        if b.get("호") or b.get("일자"):
            머리 += ' &lt;'
            if b.get("호"):
                머리 += f'<span class="tx" data-path="부칙.{bi}.호">{e(b["호"])}</span>'
            if b.get("일자"):
                머리 += (", " if b.get("호") else "")
                머리 += f'<span class="tx" data-path="부칙.{bi}.일자">{e(b["일자"])}</span>'
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
            rows = "<tr>" + "".join(f"<th>{e(h)}</th>" for h in tb.get("header", [])) + "</tr>"
            for row in tb.get("rows", []):
                rows += "<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>"
            parts.append(f'    <div class="rg-table-wrap" data-ent="표" '
                         f'data-path="별표.{ti}.표"><table class="rg-table">{rows}</table></div>\n')

    parts.append("""  </div>
</div>
<script src="../jachigan.js?v="></script>\n<script src="../audit.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


def 조립하기(등록부경로, only=None, out=None):
    """자치법규 등록부 → HTML. **직접 호출·subprocess 공용 몸통**(WP-S9).

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
    본 = 조립하기(argv[0], only=only, out=out)
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
