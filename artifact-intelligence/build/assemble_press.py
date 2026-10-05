#!/usr/bin/env python3
"""보도자료 조립기 — JSON → 보도자료 HTML. 머리표·위계 마커 자동 부여.

정본: ontology document_types.press-release (실물 사례, 2026-08-01)
  구성  기관 로고 — 문서종류 라벨 — 보도시점·배포 표 — 제목 — 부제 — 리드 — 본문 — 붙임
        문서종류 라벨(첫 문단) · 보도시점· 배포· 붙임· 참고
  문체  bodo — 몸통은 서술 완결, 붙임·요약 항목만 명사형. 하나로 강제하지 않는다
  디자인 본문 14pt·15pt · 바탕·휴먼명조 · 줄간격· 양쪽맞춤
  위계  □ 15pt → ○ 15pt → - 15pt → ※ 12pt (실측 사다리)

**'보도일시'가 아니라 '보도시점'이 실물 표기다** — 보도시점대 보도일시.

문서 JSON 스키마(build/press-docs.json — 배열):
{
  "filename": "pr-…", "genre": "press-release",
  "기관명": "…", "문서종류": "보도자료|보도참고자료|보도설명자료|동정자료",
  "보도시점": {"방식": "즉시|엠바고|시각지정", "값": "2026. 8. 3.(월) 09:00"},
  "배포": "2026. 8. 1.(금)",
  "제목": "…", "부제": "- … -",
  "리드": "첫 문단. 결론을 여기 담는다(두괄식)",
  "개요표": {"제목": "…", "header": ["구분","내용"], "rows": [["…","…"]…]}  ← 선택. 수치가
    여럿일 때 리드 다음·본문 앞에 두는 한눈 요약 표(구성.선택키, '26-09-26 벤치마크 진단).
    없으면 지금처럼 리드 다음 바로 본문이 온다(회귀 없음).
  "본문": [ {"level": 1~4, "text": "…"} … ],       ← 마커는 넣지 않는다(자동)
  "붙임": ["… 1부."] | [],
  "붙임사진": [{"그림": "img-…", "캡션": "사진 아래 한 줄 설명"}]  ← 선택('26-09-30). 올린 사진만(목록 id),
    끝에 둔다. 본문에는 그림을 넣지 않는다. 생성 그림은 싣지 않는다.
  "담당": [{"부서": "…", "직위": "…", "이름": "…", "전화": "…"}]
}

조판('26-09-27, 4차 벤치마크 진단)
  · 제목이 두 줄로 갈리면 text-wrap:balance(press.css)로 줄 길이를 고르게 나눈다 —
    전에는 "…50% / 확대"처럼 낱말 하나만 둘째 줄에 떨어졌다(심사 지적). --print-to-pdf
    로 직접 찍어 실측(스크래치패드 실험) — 크롬 153 은 인쇄 매체에서도 그대로 적용한다.
  · 소량 넘침 당기기(--pr-tighten, build() 끝 인라인 스크립트) — 인용 문단·담당자 표
    만 2쪽으로 넘어가 2쪽이 거의 비면, 문서 전체 줄간격·여백을 살짝(최대 줄여
    1쪽에 들어오게 한다. 1쪽에 들 수 있는 분량일 때만 — 안 되면 원래대로 둔다.
    regulation.css 의 --rg-tighten 과 같은 메커니즘(주석은 그쪽이 더 자세하다).

게이트(gate_check)
  · 제목·리드 필수 — 리드가 없으면 두괄식이 아니다
  · 본문 필수 — 문단(서술) 또는 표가 하나도 없으면 리드만 있는 반쪽 보도자료다('26-09-27,
    3차 측정: 서버 EXAONE 가 요약격인 리드만 채우고 본문을 통째로 비우는 이탈이 풀버전과
    같은 결로 보도자료에서도 일어날 수 있다 — 실측 표본엔 없었지만 가능한 이탈을 미리 막는다)
  · 보도시점 필수(실측)
  · 문서종류는 실측에서 나온 넷 중 하나
  · 리드·본문 1~2수준은 서술 완결 — 명사형으로 끝나면 경고(하드 아님).
    실물이 섞여 쓰므로(서술· 명사형 막지 않고 알린다.

사용: python3 build/assemble_press.py build/press-docs.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import genres
import imageasset
import 속성값
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
    # 본문 — 문단(text)이든 표든 하나도 없으면 리드만 있는 반쪽 보도자료다. 풀버전의
    # '장이 통째로 비었다' 이탈(3차 측정, run.json steps)과 같은 결의 이탈이 이 장르에서도
    # 날 수 있어 미리 막는다 — 실측 표본(press-docs.json 사례·bench2/3 사례)엔 없었지만
    # 리드만으로 요약 삼는 이탈은 형태상 구분이 안 되므로 게이트로 막는 것이 맞다.
    본문 = doc.get("본문")
    if not isinstance(본문, list) or not any(
        isinstance(it, dict) and (("표" in it) or str(it.get("text") or "").strip())
        for it in 본문
    ):
        bad.append("본문이 비어 있다 — 리드만으로는 보도자료가 아니다. 자료로 본문 문단을 채워라")
    # 보도시점은 비면 '즉시'로 안전하게 기본을 준다(render 참조) — 예전엔 하드 거부해 초안·HWPX 를
    # 막았다(코덱스·커서 교차 테스트 지적, 2026-08-24). 정확한 시점 되묻기는 에이전트(SKILL) 몫이고,
    # 게이트는 초안이 나가게 두는 초안 도구 규범을 따른다(제목·리드 같은 내용 흠만 하드로 막는다).
    종류 = doc.get("문서종류")
    if 종류 and 종류 not in 문서종류들:
        bad.append(f"문서종류 '{종류}' — 실측에서 나온 것은 {', '.join(문서종류들)}")
    return bad


def 문체경고(doc):
    """몸통이 서술로 닫히는가. 막지 않고 알린다 — 실물이 섞어 쓴다.

    실측 종결: 명사형· 했다체· 한다체· 이다체· 형용사· 합니다체.
    서술 완결의 합이로 몸통이고 명사형는 붙임·요약 항목 몫이다.
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
    # 본문꼴('26-09-28, 사장님 판정) — '개조식'(기본, □○-※ 사다리)과 '서술'(재정 부처 보도자료
    # 관행: 본문 96문단 중 62문단이 기호 없는 서술 문단이고 □ㅇ 개조식은 붙임·참고 쪽에 주로 나온다,
    # 내부 기록 §4-2). 서술이면 1·2수준(□○)을 기호 없는 문단으로 짓고
    # -·※(3·4수준)는 세부·주석 줄로 그대로 둔다. 기호를 CSS 로 감추지 않고 **안 짓는다** — 감춘
    # .mk 글자도 화면읽기가 읽어 HWPX 에 □ 가 새기 때문이다. 선택지 정본은 편집기 프로파일의
    # 상단바.본문꼴(손목록 금지) — <html> data 속성으로 들어가므로 속성값.열거 를 여기서 직접 부른다.
    본문꼴 = 속성값.열거(doc.get("본문꼴"), tuple(
        m[0] for m in ((load_profile("press-release").get("상단바") or {}).get("본문꼴") or ())),
        "본문꼴", 기본="개조식")
    서술 = 본문꼴 == "서술"
    본문꼴속성 = f' data-본문꼴="{본문꼴}"' if 서술 else ""
    parts = [f"""<!doctype html>
<html lang="ko" data-genre="press-release"{본문꼴속성}>
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
    # 개요표(선택키, '26-09-26 벤치마크 진단) — 수치가 여럿일 때 리드 다음·본문 앞에 두는
    # 한눈 요약 표. 구성.선택키.개요표 — 없으면 지금처럼 본문이 바로 이어진다(회귀 없음).
    # 게이트가 구조를 걸러도, 렌더는 절대 안 죽어야 한다(백스톱) — header·row 가 리스트가
    # 아니어도 강제하고, 셀 값도 문자열로 강제한다(e()=html.escape 는 숫자·None 을 받으면
    # 죽는다: 모델이 수치 셀을 문자열이 아닌 int 로 내는 흔한 이탈, assemble_slides._표
    # 와 같은 방어, assemble:F9 '26-09-27).
    _s = lambda x: "" if x is None else str(x)
    개요표 = doc.get("개요표") if isinstance(doc.get("개요표"), dict) else None
    if 개요표 and (개요표.get("header") or 개요표.get("rows")):
        cap = (f'<div class="pr-overview-caption">{e(개요표.get("제목", ""))}</div>'
               if 개요표.get("제목") else "")
        # '26-09-29 표 재설계 P1: 표 몸은 build/표꼴.py 공용. 개요표는 한눈 요약(보고서형) —
        # 첫 열 칠은 통계형 관행(무채움)대로 끈다
        parts.append(f'    <div class="pr-overview-wrap" data-ent="개요표" data-path="개요표">'
                     f'{cap}{표꼴.표html(개요표, "pr-overview", 첫열기본=False)}</div>\n')
    for i, it in enumerate(doc.get("본문", [])):
        if "표" in it:
            tb = it["표"]
            cap = (f'<div class="pr-tbl-caption">{e(tb.get("캡션", ""))}</div>'
                   if tb.get("캡션") else "")
            # '26-09-29 표 재설계 P1: 표 몸은 build/표꼴.py 공용. 보도자료 본문 표 = 통계형 —
            # 숫자 열 오른쪽, 첫 열 무채움(design 5-2 통계형 열)
            parts.append(f'    <div class="pr-table-wrap" data-ent="표" '
                         f'data-path="본문.{i}.표">{cap}'
                         f'{표꼴.표html(tb, "pr-table", 통계=True, 첫열기본=False)}</div>\n')
            continue
        # level 은 `class="pr-l{lv}"` 로 **속성 자리**에 들어간다 — 위 실측 사다리
        # `마커` 표의 열쇠 넷이 곧 값 집합이다(press.css 의 .pr-l1~4 와 짝). 예전엔
        # 값을 그대로 보간해 `1" onmouseover="…" x="` 로 <p> 에 라이브 핸들러를
        # 붙일 수 있었다(2026-08-07 크롬 실측 — 다섯 조립기가 같은 부류였다).
        lv = 속성값.열거(it.get("level"), tuple(마커), f"본문.{i}.level", 기본=1)
        mk = 마커.get(lv, "-")
        if 서술 and lv in (1, 2):
            # 서술 문단 — 기호 없이 첫 줄만 한 자 들여 쓴다(press.css .pr-p). level 은 등록부에
            # 그대로 남아(class pr-l{lv}) 개조식으로 되돌리면 □○ 사다리가 다시 선다.
            parts.append(f'    <p class="pr-l{lv} pr-p" data-ent="항목">'
                         f'<span class="tx" data-path="본문.{i}.text">{e(it.get("text", ""))}</span>'
                         f'</p>\n')
            continue
        # 마커 뒤 공백은 글자(NBSP)로 두되 **고정 폭 칸(.sp)에 담는다**('26-09-28) — 맨 글자로
        # 두면 양쪽맞춤이 첫 줄에서 그 공백을 늘려 첫 줄 글이 둘째 줄보다 0.5~1.4mm 늦게 섰다
        # (둘째 줄 = 기호 뒤 첫 글자 규칙이 깨진다). 칸 안 글자는 늘지 않는다(inline-block).
        # 글자는 그대로라 복붙·HWPX 에서 마커와 글이 붙지 않는다.
        parts.append(f'    <p class="pr-l{lv}" data-ent="항목">'
                     f'<span class="mk">{mk}</span><span class="sp">{NBSP}</span>'
                     f'<span class="tx" data-path="본문.{i}.text">{e(it.get("text", ""))}</span>'
                     f'</p>\n')
    att = [a for a in doc.get("붙임", []) if a.strip()]
    for ai, a in enumerate(att):
        라벨 = "붙임" if ai == 0 else ""
        번호 = f" {ai + 1}." if len(att) > 1 else ""
        parts.append(f'    <p class="pr-attach" data-ent="붙임">'
                     f'<span class="mk">{라벨}{번호}</span>{NBSP}'
                     f'<span class="tx" data-path="붙임.{ai}">{e(a)}</span></p>\n')
    # 붙임 사진('26-09-30 주관 판정) — 보도자료는 본문에 그림을 넣지 않고 끝에 올린 사진만 둔다(build/genres.py
    # 그림정책). 설명은 사진 아래 한 줄(보도자료 작성 길잡이). 그림은 목록 id — 생성 그림은 싣지 않는다
    # (사진은 증빙으로 읽힌다 — api 새문서가 빼고 알린다. 여기선 한 번 더 거른다).
    _사진들 = doc.get("붙임사진") if isinstance(doc.get("붙임사진"), list) else (
        [doc["붙임사진"]] if isinstance(doc.get("붙임사진"), dict) else [])
    for pi, sp in enumerate(_사진들):
        if not isinstance(sp, dict) or sp.get("출처") == "생성":
            continue
        parts.append("    " + imageasset.render(sp, f"{doc['filename']}-pp{pi}", 캡션아래=True).replace(
            'class="blk fr-fig fr-img"', f'class="blk fr-fig fr-img pr-photo" data-path="붙임사진.{pi}"', 1))
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
<script>
/* 소량 넘침 당기기('26-09-27, 4차 벤치마크 진단) — assemble_regulation.py 의 같은
   스크립트와 같은 메커니즘·같은 이유(주석은 거기 더 자세하다). 보도자료는 "1쪽 안에
   들 수 있는 분량만" 당긴다 — 인용 문단·담당자 표만 2쪽으로 넘어가 2쪽이 거의 비는
   실측 사례(front-s5 심사)가 바로 이 경우다. --pr-tighten(줄간격·여백 배율)을 문서
   전체에 살짝만(최대 10%) 낮춰 시도하고, 그래도 1쪽에 안 들면 원래대로 둔다(여러
   쪽짜리 긴 보도자료를 억지로 구기지 않는다).

   안전배율(0.95) — assemble_regulation.py 의 같은 상수와 같은 이유(그 주석이 더
   자세하다): 화면에서 잰 mm 로 인쇄 쪽수를 내다보면 실제 --print-to-pdf 결과보다
   낙관적일 수 있다(실측, test/r11_asm11.py) — "쪽 하나가 사라졌다"를 빠듯하게
   확인하지 않고 그 쪽 용량의 95% 안에 들 때만 성공으로 친다. */
(() => {
  const sheet = document.querySelector('.pr-sheet');
  if (!sheet) return;
  const 문서 = document.documentElement;
  const PXPERMM = 96 / 25.4;
  const 안전배율 = 0.95;
  function 재기() {
    const cs = getComputedStyle(sheet);
    const 패딩mm = ((parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0)) / PXPERMM;
    // .pr-sheet 의 **화면 전용** min-height(297mm, press.css)가 한 쪽이 채 안 되는
    // 문서의 내용mm 를 부풀린다(assemble_regulation.py 의 같은 발견·같은 고침, '26-09-27
    // 재검토) — 재는 순간만 지웠다가 되돌린다.
    const 원래최소높이 = sheet.style.minHeight;
    sheet.style.setProperty('min-height', '0px');
    const 내용mm = sheet.scrollHeight / PXPERMM - 패딩mm;
    if (원래최소높이) sheet.style.setProperty('min-height', 원래최소높이);
    else sheet.style.removeProperty('min-height');
    const rs = getComputedStyle(문서);
    const 상 = parseFloat(rs.getPropertyValue('--pr-mt')) || 0;
    const 하 = parseFloat(rs.getPropertyValue('--pr-mb')) || 0;
    return { 내용mm, 쪽높이mm: 297 - 상 - 하 };
  }
  function 시도() {
    문서.style.removeProperty('--pr-tighten');
    const { 내용mm, 쪽높이mm } = 재기();
    if (쪽높이mm <= 0) return;
    const 쪽수 = Math.ceil(내용mm / 쪽높이mm);
    if (쪽수 < 2) return;
    const 남는것mm = 내용mm - (쪽수 - 1) * 쪽높이mm;
    if (남는것mm > 쪽높이mm * 0.15) return;
    // 2쪽→1쪽(가장 흔한 경우, 경계 하나) 은 곱셈 안전배율(0.95)이 사실상 늘 막는다
    // ('26-09-27 재검토 발견, medium) — 실측(test/r11_asm11.py, 합성 표본으로 스케일
    // 0.90~0.99 전수 실 인쇄 대조): 화면 재기와 실제 --print-to-pdf 쪽수가 이 문서
    // 부류에서는 1mm 안쪽으로 맞아떨어졌다(0.95 곱셈은 regulation 의 훨씬 큰 어긋남
    // ―3쪽 문서에서 494mm 문턱을 493.7mm 로도 못 맞힌 사례, 이 파일 위 실측 주석 참고―
    // 에 맞춘 값이라 press 에 그대로 쓰면 실제로 되는 경우까지 되돌렸다). 그래서 한
    // 경계(쪽수-1==1)일 때만 더 가벼운 고정 mm 여유로 한 번 더 본다 — 여러 쪽을
    // 한꺼번에 줄이는 경우(경계 2개 이상)는 원래 곱셈 배율만 쓴다(그 쪽은 이번에
    // 실측하지 않았다, 안전한 쪽으로 그대로 둔다).
    const 여유mm = 1;
    let 완화후보 = null;
    for (let s = 0.99; s >= 0.90 - 1e-9; s -= 0.01) {
      문서.style.setProperty('--pr-tighten', s.toFixed(2));
      const 잰것 = 재기();
      if (잰것.내용mm <= (쪽수 - 1) * 잰것.쪽높이mm * 안전배율) return;
      if (완화후보 === null && (쪽수 - 1) === 1 && 잰것.내용mm <= 잰것.쪽높이mm - 여유mm) {
        완화후보 = s;
      }
    }
    if (완화후보 !== null) { 문서.style.setProperty('--pr-tighten', 완화후보.toFixed(2)); return; }
    문서.style.removeProperty('--pr-tighten');
  }
  // 글꼴이 실제로 앉기 전(대체 글꼴)에는 화면 높이가 다르다 — assemble_regulation.py
  // 의 같은 스크립트와 같은 이유(그 주석이 더 자세하다): 대체 글꼴로 잰 높이가 더 커서
  // '넘침이 15%보다 많다'며 시도조차 안 하고 넘어간 실측이 있었다. 글꼴 로드 뒤 한
  // 번 더 잰다(jachigan.js 와 같은 사유).
  function run() {
    시도();
    if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(시도);
  }
  if (document.readyState === 'complete') run(); else window.addEventListener('load', run);
})();
</script>
<script src="../jachigan.js?v="></script>
<script src="../audit.js?v="></script>
</body>
</html>
""")
    return "".join(parts)


def 조립하기(등록부경로, only=None, out=None, 저장=False):
    """보도자료 등록부 → HTML. **직접 호출·subprocess 공용 몸통**(WP-S9).

    돌려주는 값: {"ok": bool, "낸것": [파일명…], "로그": …}. 게이트 위반 문서는 안
    쓰고 ok=False 가 된다. 산출물뿌리를 **호출마다** 다시 푼다(세션 오염 방지).
    `out` 을 주면(=--out) 그 자리로 뽑는다.

    `저장`(기본 False) — True 면 gate_check 의 "본문이 비어 있다"(내용 결손) 위반만
    소프트 경고로 낮춘다(assemble_full·assemble_slides 의 같은 인자와 같은 취지, r10
    사후검토 발견 medium) — 이미 등록된(빈 본문) 문서를 저장할 때 등록부(JSON)는
    편집이 반영됐는데 HTML 은 재조립 실패로 옛 채로 남는 어긋남을 막는다. 새 초안에서는
    여전히 하드로 막힌다(저장=False 기본값).
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
        if 저장 and bad:
            연성 = [b for b in bad if b.startswith("본문이 비어 있다")]
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
    # --저장 — apply_edit_any.py 가 저장(편집 반영) 뒤 재조립할 때만 붙인다(조립하기()
    # docstring 참고, assemble_regulation.py 의 같은 깃발과 같은 방침).
    본 = 조립하기(argv[0], only=only, out=out, 저장=("--저장" in sys.argv))
    if 본["로그"]:
        print(본["로그"])
    return 0 if 본["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
