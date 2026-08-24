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
  "수신자란": "수신자 참조일 때 나열",
  "메타": {"기안자":"", "시행":"부서명-", "시행일":"", "주소":"", "전화":"", "팩스":"", "이메일":"", "공개":"…"}
}
메타 빈값 원칙: 시행번호·서명 등은 빈 칸으로 남긴다(실사용 시 채움).

게이트(온톨로지 document_types.gongmun.게이트):
- 발신명의 필수(하드) / 공손체 종결(level 1·2 서술문 '…다.' 완결, ~요망·~바람·~할 것 금지)
- 끝표시 규칙은 조립기가 기계 집행(붙임 유무에 따라 위치 자동)

사용: python3 build/assemble_gongmun.py build/gongmun-docs.json
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
# ★ 산출물 뿌리를 모듈 적재 시점에 상수로 굳히지 않는다(WP-S9). import 로 부르면 모듈이
#   딱 한 번 적재돼 첫 세션 뿌리에 얼어붙고, 이후 모든 세션이 첫 세션 뿌리에 쓴다
#   (WP-S2 세션 오염). 뿌리는 `조립하기()` 가 **호출마다** 다시 푼다.

GANADA = "가나다라마바사아자차카타파하"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


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
        # 서술어 완결('…다.')은 주요 서술부(1. 수준)의 규범 — 세부 개조식(가. 이하)은 명사형 허용
        if it["level"] == 1 and not POLITE_END.search(t):
            bad.append(f"본문 {i+1}번째(주요 서술부): 서술어 완결('…다.') 아님 — 「{t[-20:]}」")
    return bad


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
    <div class="gm-line"><span class="lb">수신</span><span data-ent="두문결문" data-gf="수신" data-path="수신">{html.escape(doc.get("수신",""))}</span></div>
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
            rows_html = '<tr>' + ''.join(f'<th>{html.escape(h)}</th>' for h in tb.get("header", [])) + '</tr>'
            for row in tb.get("rows", []):
                rows_html += '<tr>' + ''.join(f'<td>{html.escape(c)}</td>' for c in row) + '</tr>'
            parts.append(f'    <div class="gm-table-wrap" data-ent="표" data-path="본문.{items.index(it)}.표">'
                         f'{cap}<table class="gm-table">{rows_html}</table></div>\n')
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
            lines.append(f"{label}{num}&nbsp;&nbsp;{html.escape(a)}")
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
    recipients = html.escape(doc.get("수신자란", ""))
    parts.append(f"""  </div>
  <div class="gm-foot">
    <div class="gm-sign"><span class="gm-name" data-ent="두문결문" data-gf="발신명의" data-path="발신명의">{html.escape((doc.get("발신명의") or "").strip()) or "(발신 명의 — 서명 시 기입)"}</span>{stamp}</div>
    <div class="gm-recipients">{('수신자 ' + recipients) if recipients else ''}</div>
    <div class="gm-band"></div>
    <div class="gm-approvers"><div class="cell">기안자 {html.escape(m.get("기안자",""))}</div>
      <div class="cell">검토자</div><div class="cell">협조자</div><div class="cell">결재권자</div></div>
    <div class="gm-band"></div>
    <div class="gm-meta"><span class="k">시행</span><span class="v">{html.escape(m.get("시행",""))} ({html.escape(m.get("시행일",""))})</span>
      <span class="k">접수</span><span class="v"> ( )</span></div>
    <div class="gm-meta"><span class="k">우</span><span class="v">{html.escape(m.get("주소",""))}</span></div>
    <div class="gm-contact"><span>전화 {html.escape(m.get("전화",""))}</span><span>/ 전송 {html.escape(m.get("팩스",""))}</span>
      <span>/ {html.escape(m.get("이메일",""))}</span><span>/ {html.escape(m.get("공개",""))}</span></div>
  </div>
</div>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
<script src="../gmseal.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


def 조립하기(등록부경로, only=None, out=None):
    """시행문 등록부 → HTML + 복붙용 .txt. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 게이트 위반 문서는 안
    쓰고 ok=False 가 된다(subprocess 였다면 returncode≠0). 산출물뿌리를 **호출마다**
    다시 푼다(세션 오염 방지). `out` 을 주면(=--out) 그 자리로 뽑는다.
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
    본 = 조립하기(argv[0], only=only, out=out)
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
