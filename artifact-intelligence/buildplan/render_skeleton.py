#!/usr/bin/env python3
"""골격 편집기 렌더러 — 2층 빌드플랜 JSON → 편집 가능한 와이어프레임.

왜 필요한가: 2층의 존재 이유는 '내용을 쓰기 전에 사용자가 판단을 교정하는 것'인데,
지금까지 승인 화면(plan.html)은 그걸 글로만 했다. 구성과 위계를 눈으로 보고 고치게 한다.

층 경계(온톨로지 editor-profiles.장르.빌드플랜._층경계):
  만질 수 있는 것 — 개체 포함 여부·방법론, 절 제목·순서·개수, 등장요소 자리, 분량 배분
  만질 수 없는 것 — 항목 개수·실제 문구·강조 배치(3층 재량)
  화면에서 실선(확정)과 점선(3층 위임)으로 구분해 경계 자체를 보이게 한다.

편집은 범용 편집기(workspace/render_editor_any.py)가 맡는다. 이 파일은 골격을
data-ent/data-path 로 선언해 그리기만 한다 — 새 편집기를 만들지 않는다.

사용: python3 buildplan/render_skeleton.py <plan.json> [...]
      python3 buildplan/render_skeleton.py --all
"""
import html
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))   # 코드뿌리/buildplan (스키마·CSS)
ROOT = os.path.dirname(BASE)                        # 코드뿌리

# 플랜·골격·산출물·이력은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
import importlib.util as _iu
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(ROOT, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

OUT = 자료뿌리.골격뿌리()

e = html.escape

# 화면에 나가는 말은 전부 일반 사용자 기준(schema._사람말_원칙 — 층 용어·규칙 ID·은어 금지)
PICK_KO = {"표기방식": "항목 기호 체계", "목차설정": "목차", "목차깊이": "목차에 실을 깊이",
           "간지설정": "간지"}
DOCTYPE_KO = {"onepage-report": "1페이지 보고서", "gongmun": "시행문",
              "fullreport": "여러 장 보고서", "email": "이메일"}
CONF_KO = {"높음": "높음", "중간": "보통", "보통": "보통", "낮음": "낮음"}

# 자동 검사 항목 — 클릭하면 오른쪽에 뜨는 설명
RULE_HELP = {
    "1쪽": "이 문서는 A4 한 장을 넘기지 않습니다. 넘치면 부가 설명 → 비고 → 중복 표현 순으로 "
           "줄이고, 그래도 안 되면 여러 장 보고서로 바꾸도록 권해 드립니다.",
    "어절분리 0": "낱말이 줄 끝에서 잘려 다음 줄로 넘어가지 않게 합니다. 글자 사이 간격을 아주 "
                 "조금씩 조절해 낱말 단위로 줄을 바꿉니다. 사람이 손으로 다듬던 작업입니다.",
    "요약 2줄 이내": "맨 위 요약 상자는 두 줄을 넘지 않습니다. 읽는 분이 처음 몇 초 안에 결론을 "
                    "잡을 수 있게 하려는 제한입니다.",
    "문체 하드 위반 0": "공문서 문체에서 반드시 지켜야 하는 항목에 위반이 하나도 없어야 합니다. "
                       "번역 말투(~에 대하여), 구어체, 문장 끝맺음 불일치 같은 것을 문장 단위로 "
                       "자동 검사합니다.",
    "채움도 0.72 이상": "한 장을 너무 성기게 쓰지 않도록 지면의 72% 이상을 채웁니다. 너무 비면 "
                       "내용이 부족해 보이기 때문입니다.",
    "발신명의": "시행문은 보내는 사람의 이름(발신 명의)이 반드시 있어야 합니다. 없으면 형식상 "
               "흠이 있는 문서가 됩니다.",
    "요약 1쪽": "맨 앞 요약은 한 쪽 안에 담습니다. 읽는 분이 요약만 보고도 "
                "판단할 수 있게 하려는 제한이라, 넘치면 본문으로 내립니다.",
    "쪽 넘침 0": "어느 쪽에서도 내용이 잘리지 않아야 합니다. 넘칠 것 같으면 줄 간격을 아주 "
                "조금 줄여 앞 쪽으로 당기고, 그래도 안 되면 문단째로 다음 쪽에 넘깁니다.",
    "장 5개 이하": "장(Ⅰ, Ⅱ …)을 다섯 개 이하로 둡니다. 더 늘어나면 읽는 분이 "
                  "전체 구조를 한 번에 잡기 어려워집니다.",
    "공손체 종결": "받는 분에게 보내는 문서이므로 문장을 '~하시기 바랍니다'처럼 공손하게 맺습니다. "
                  "'~요망', '~할 것' 같은 표현은 쓰지 않습니다.",
}


RULE_NAME = {
    "1쪽": "한 장 넘지 않기", "어절분리 0": "낱말 안 자르기",
    "요약 2줄 이내": "요약 두 줄 이내", "문체 하드 위반 0": "공문서 문체 지키기",
    "채움도 0.72 이상": "지면 너무 비우지 않기",
    "요약 1쪽": "요약 한 쪽 안에", "쪽 넘침 0": "내용 잘리지 않기",
    "장 5개 이하": "장 다섯 개 이하", "발신명의": "보내는 이 이름 넣기",
    "공손체 종결": "공손하게 맺기",
}


def rule_name(g):
    return RULE_NAME.get(g, g)


def rule_help(g):
    # 앞머리만 같으면 갖다 붙이던 폴백을 뺐다. 여러 장 보고서의 '요약 1쪽'이
    # '1쪽'에 걸려 "이 문서는 A4 한 장을 넘기지 않습니다"로 뒤집혀 나갔다.
    return RULE_HELP.get(g, "이 문서 유형에 적용되는 자동 검사 항목입니다.")


# 작업 메모 말투 → 사용자가 읽는 말. 플랜 JSON은 기계·감사용이라 축약이 섞이는데,
# 화면에는 그대로 나가면 안 된다(schema._사람말_원칙).
SHORTHAND = [
    ("무표", "표를 안 쓸 때"), ("유표", "표를 쓸 때"),
    ("명사구 1줄", "명사로 끝나는 한 줄"), ("명사구", "명사로 끝나는 표현"),
    ("결론 선행", "결론을 맨 앞에"),
    ("종결", "맺음말"), ("개조식", "개조식(항목을 짧게 끊어 쓰는 방식)"),
    ("위계", "단계"), ("(수평)", ""), ("수평 부서 대상", "같은 급 부서에 보내는 문서"),
    (" vs ", " 또는 "), ("요약박스", "요약 상자"), ("절 개수", "본문을 몇 개로 나눌지"),
    ("표 행", "표 줄"), ("~에 연동", "에 맞춰 정함"), ("에 연동", "에 맞춰 정함"),
]


def shown(path, raw):
    """표시용으로 다듬은 값 + 원본을 함께 내보내는 속성 문자열.

    화면은 사람말로 보여주되 저장은 원본을 지킨다 — 사용자가 실제로 고쳤을 때만 바뀐다.
    """
    disp = plain(raw)
    a = f' data-path="{e(path)}"'
    if disp != str(raw or ""):
        a += f' data-orig="{e(str(raw or ""))}" data-shown="{e(disp)}"'
    return a, disp


def plain(t):
    """화면에 나가는 말에서 내부 표기·작업 메모 말투를 걷어낸다."""
    import re as _re
    t = str(t or "")
    t = _re.sub(r"\s*\(?(FB|R[가-힣])-\d+[^)]*\)?", "", t)          # 추적 코드
    t = _re.sub(r"\(?\s*확인필요\s*[\d·,\s]*번[에]?\s*연?동?\s*\)?", "", t)   # 화면에 없는 내부 참조
    t = _re.sub(r"\(\s*\)", "", t)
    t = _re.sub(r"^\s*[①-⑮]\s*", "", t)                              # 선택지 잔여 번호
    t = _re.sub(r"^\s*[①-⑮]\s*", "", t)
    t = _re.sub(r"(\d+)절\s*←\s*", r"\1번 항목을 두는 이유: ", t)      # 개발자 축약 표기
    t = _re.sub(r"^\s*[①-⑮]\s+", "", t)
    t = t.replace("1층", "규칙").replace("2층", "구성 설계").replace("3층", "내용 작성 단계")
    t = t.replace("유형 공백 — ", "").replace("잠정 프레임으로 진행", "비슷한 유형을 응용해 진행")
    t = _re.sub(r"^[①-⑮]\s*", "", t)
    for a, b in SHORTHAND:
        t = t.replace(a, b)
    t = _re.sub(r"\s{2,}", " ", t)
    return t.strip(" ·-")


def load_profile():
    with open(os.path.join(ROOT, "ontology", "editor-profiles.json"), encoding="utf-8") as f:
        p = dict(json.load(f)["장르"]["빌드플랜"])
    p["genre"] = "빌드플랜"
    return p


def seq_path(plan):
    """구성 순서가 들어있는 개체를 찾는다 — 장르마다 그 개체가 다르다.

    1p는 본문, 여러 장 보고서는 본문(장 시퀀스), 시행문도 본문.
    '본문'으로 고정하면 다른 장르에서 순서를 못 그리므로 전체를 훑는다.
    """
    m = plan.get("적용방법론", {})
    for host, spec in m.items():
        if host.startswith("_") or not isinstance(spec, dict):
            continue
        pat = spec.get("구성", {}).get("목차패턴", {})
        if "표준시퀀스" in pat:
            return f"적용방법론.{host}.구성.목차패턴.표준시퀀스", pat, host
    return None, {}, None


DOC_EST = {
    "onepage-report": ("A4 한 장", 18),
    "gongmun": ("A4 한 장", 12),
    "fullreport": (None, None),      # 절 수로 계산
}


def estimate(plan, nsec):
    """예상 분량 — 승인 판단에 필요한 최소 근거만. 확정이 아니라 범위로 말한다."""
    budget = plan.get("제약", {}).get("분량예산", {})
    doctype = plan.get("판정", {}).get("문서유형", "onepage-report")
    fixed, default_n = DOC_EST.get(doctype, (None, None))
    if fixed:
        cap = (budget.get("표를 안 쓸 때") or budget.get("무표")
               or next((v for k, v in budget.items() if not k.startswith("_")), ""))
        n = default_n
        import re as _re
        m = _re.search(r"(\d+)", str(cap))
        if m:
            n = int(m.group(1))
        if nsec:
            return fixed, (f"본문에 들어갈 항목은 모두 {n}개, 큰 항목 {nsec}개로 나누면 "
                           f"하나당 {round(n / max(nsec, 1), 1)}개씩입니다")
        return fixed, f"본문에 들어갈 항목은 모두 {n}개"
    # 여러 장 보고서 — 장마다 새 쪽에서 시작하므로 장 수가 쪽수의 바닥이다(실측 fr-task100-plan 9쪽)
    chapters = nsec                       # 본문 시퀀스 = 장
    per_sec = 2.5                         # 장당 큰 항목(관측)
    per_item = 4.0                        # 큰 항목당 세부 항목(관측)
    lines = chapters * (2 + per_sec * (1 + per_item * 1.5))
    body = max(chapters, round(lines / 30))     # 장 새 쪽 규칙이 바닥
    front = 2 + (1 if any(o.get("개체") == "요약" and o.get("포함", True)
                          for o in plan.get("개체구성", [])) else 0)   # 표지·목차(+요약)
    annex = 1 if any(o.get("개체") in ("참고자료", "붙임") and o.get("포함", True)
                     for o in plan.get("개체구성", [])) else 0
    return (f"본문 약 {body}~{body + 1}쪽",
            f"장 {chapters}개(장마다 새 쪽에서 시작) · 앞부분 {front}쪽 · 참고자료 {annex}쪽 "
            f"→ 전체 {body + front + annex}쪽 내외")


def stale_note(plan):
    """계획을 고쳐도 문서가 저절로 다시 만들어지지는 않는다 — 화면이 그 사실을 말한다."""
    out = plan.get("산출물")
    if not out or not plan.get("_수정시각"):
        return ""
    import datetime
    h = 자료뿌리.산출물(out, "html")
    if not os.path.exists(h):
        return ""
    made = datetime.datetime.fromtimestamp(os.path.getmtime(h)).strftime("%Y-%m-%dT%H:%M:%S")
    if made >= plan["_수정시각"]:
        return ""
    return ('<div class="sk-stale">구성 설계를 고치셨습니다 — '
            '문서를 다시 만들어야 반영됩니다.</div>')


def basis_note(plan):
    """기준이 바뀌어 다시 봐야 하는가 — **결과가 실제로 달라질 때만** 알린다.

    지문만 보고 띠를 띄우면 결과가 같은 문서에도 뜨고, 그 순간부터 아무도 안 읽는다.
    """
    out = plan.get("산출물")
    if not out:
        return ""
    p = os.path.join(자료뿌리.이력방(out), "문서.json")
    if not os.path.exists(p):
        return ""
    try:
        L = json.load(open(p, encoding="utf-8"))
    except Exception:
        return ""
    b = L.get("기준바뀜")
    if not b:
        return ""
    return ('<div class="sk-basis">문서를 만드는 방식이 바뀌었습니다 — '
            + e(b.get("말", "다시 만들면 결과가 달라집니다"))
            + '</div>')


def build(plan):
    # 표기 선택의 기본값을 모델에 먼저 넣는다 — 화면에만 넣으면 저장할 때 없던 키가
    # 새로 생겨 '안 고쳤는데 바뀐 것'이 된다(왕복 불변식 위반).
    if plan.get("판정", {}).get("문서유형") == "fullreport":
        n = plan.setdefault("표기", {})
        n.setdefault("항목기호", "도형식")
        n.setdefault("목차", "자동")
        n.setdefault("목차깊이", "자동")
        n.setdefault("간지", "안 넣음")
    prof = json.dumps(load_profile(), ensure_ascii=False).replace("</", "<\\/")
    doc = json.dumps(plan, ensure_ascii=False).replace("</", "<\\/")
    req = plan.get("request", {})
    ana = plan.get("요구분석", {})
    ver = plan.get("판정", {})
    spath, pat, seq_host = seq_path(plan)
    seq = pat.get("표준시퀀스", [])
    해설 = pat.get("이_문서_소재_대응", "") or pat.get("시퀀스_해설", "")
    대응 = [x.strip() for x in 해설.split("/")] if 해설 else []

    stale = stale_note(plan) + basis_note(plan)
    P = [f"""<!doctype html>
<html lang="ko" data-genre="buildplan">
<head>
<meta charset="utf-8">
<title>구성 설계 — {e(DOCTYPE_KO.get(ver.get('문서유형',''), ver.get('문서유형','')))}</title>
<link rel="stylesheet" href="../../build/tokens.css?v=13">
<link rel="stylesheet" href="../skeleton.css?v=5">
</head>
<body>
<script type="application/json" id="fr-doc">{doc}</script>
<script type="application/json" id="fr-profile">{prof}</script>
<div class="sk-sheet">
  <div class="sk-head">
    <div class="kind">구성 설계 — 내용을 쓰기 전에 문서의 뼈대를 확인하고 고칩니다</div>{stale}
    <div class="req">{e(req.get('원문요약',''))}</div>
    <dl class="sk-facts">
      <dt>읽는 사람</dt><dd>{e(plain(ana.get("독자","")))}</dd>
      <dt>이 문서로 해야 하는 일</dt><dd>{e(ana.get('목적',''))}</dd>
      <dt>문서 종류</dt><dd>{e(DOCTYPE_KO.get(ver.get('문서유형',''), ver.get('문서유형','')))}
        <span class="sub">{e(plain(ver.get('보고목적유형','')))}</span></dd>
      <dt>이 판단이 얼마나 확실한가</dt><dd>{e(CONF_KO.get(ver.get('확신도',''), ver.get('확신도','')))}
        <span class="sub">{e(plain(ver.get('근거','')))}</span></dd>
    </dl>
  </div>
  <div class="sk-legend">
    <span class="solid"><i></i>지금 이 화면에서 정합니다</span>
    <span class="dash"><i></i>내용을 채우면서 정해지는 것 — 지금은 정하지 않습니다</span>
  </div>
"""]

    # 되묻기 답변(있으면 골격 위에 올려 구조와 함께 보이게)
    ask = ana.get("_되묻기_답변") or {}
    if ask:
        P.append('  <div class="sk-sect-h">확인해주신 사항</div>\n'
                 '  <div class="sk-note">요청만으로는 알 수 없어 여쭤봤고, 아래 답변대로 씁니다. '
                 '틀렸으면 여기서 고쳐 주세요.</div>\n')
        for k, v in ask.items():
            if str(k).startswith("_"):
                continue
            at, disp = shown(f"요구분석._되묻기_답변.{k}", v)
            P.append(f'  <div class="sk-ask"><div class="q">{e(k)}</div>'
                     f'<div class="a" data-ent="확인답변"{at}>{e(disp)}</div></div>\n')

    # 되돌아온 것 — 문서를 편집하다 나온 구성 변경 요청, 만들어보니 드러난 문제
    # 경로에는 원본 배열의 번호를 써야 한다 — 화면 순서(반영된 것을 걸러낸 순서)를 쓰면
    # 고칠 때 엉뚱한 항목을 덮어쓴다(반영된 것이 하나 있으면 통째로 한 칸씩 밀린다).
    # 처리한 것(반영·보류·해소)은 화면에서 뺀다 — 화이트리스트라 상태가 늘어도 안전하다.
    # 상태 키가 없는 옛 항목은 '대기'로 본다.
    back = [(i, b) for i, b in enumerate(plan.get("되돌림", []))
            if b.get("상태", "확인 전") == "확인 전"]
    if back:
        P.append('  <div class="sk-sect-h">확인할 것</div>\n'
                 '  <div class="sk-note">문서를 만들어 보니 구성 설계와 다른 곳입니다. '
                 '여기서 구성을 고치시면 다시 만들 때 반영됩니다.</div>\n')
        SEV = {}          # 값 자체가 이미 사람말이다 — 번역 사전을 두면 새 값이 원문으로 샌다
        # 처리 상태 표기는 편집기 프로파일과 같은 사전을 쓴다 —
        # 처음 그린 글자와 누른 뒤 글자가 다르면 사용자는 값이 바뀐 줄 안다
        SHOW = ((load_profile().get("개체", {}).get("확인할것", {}))
                .get("값표시") or {})
        for i, b in back:
            mark = b.get("성격") or "만든 결과"
            sev = b.get("심각도", "")
            what = b.get("요청") or b.get("관측") or ""
            # 사람이 낸 지시만 고칠 수 있다 — 기계가 잰 사실은 표시 전용이다
            bt2, bdisp3 = shown(f"되돌림.{i}.요청", what) if b.get("요청") else ("", what)
            st = b.get("상태", "확인 전")
            # 경로에는 반드시 원본 배열 번호(i)를 쓴다. 화면 순서를 쓰면 처리한 것이
            # 앞에 있을 때 한 칸씩 밀려 엉뚱한 항목을 덮어쓴다.
            at = (f' data-ent="확인할것" data-kind="{e(mark)}" data-no="{i}"'
                  f' data-cycle="되돌림.{i}.상태" data-lv="{e(st)}"')
            if b.get("계획경로"):
                at += f' data-plan-path="{e(b["계획경로"])}"'
                if b.get("_계획값") is not None and not isinstance(b["_계획값"], (list, dict)):
                    at += f' data-plan-was="{e(str(b["_계획값"]))}"'
                if b.get("제안값") is not None:
                    at += f' data-suggest="{e(str(b["제안값"]))}"'
            P.append(f'  <div class="sk-back"{at}>'
                     f'<span class="tag">{e(mark)}</span>'
                     + (f'<span class="sev" data-sev="{e(b.get("심각도", ""))}">'
                        f'{e(sev)}</span>' if sev else '')
                     + f'<span class="lv">{e(SHOW.get(st, st))}</span>'
                     f'<b>{e(b.get("개체", ""))}</b>'
                     f'<div class="q"{bt2}>{e(bdisp3)}</div>'
                     f'<div class="src">{e(b.get("출처", ""))} · {e(b.get("받은날", ""))}'
                     + (f' · 바뀌는 것: {e(b["바뀌는것"])}' if b.get("바뀌는것") else '')
                     + '</div></div>\n')

    # 문서 구성 요소 — 제목·요약 상자·본문·붙임을 나란히. 본문 안에 순서가 중첩된다.
    # 클릭 한 번이면 구성 전체, 다시 누르면 요소 하나, 또 누르면 본문 안 항목이 잡힌다.
    comp = plan.get("개체구성", [])
    bi = next((i for i, o in enumerate(comp) if o.get("개체") == (seq_host or "본문")), None)
    P.append('  <div class="sk-sect-h">문서 구성 요소</div>\n'
             '  <div class="sk-note">클릭하면 구성 전체가 잡힙니다. 한 번 더 누르면 요소 하나, '
             '본문 안에서 또 누르면 항목 하나가 잡힙니다.</div>\n'
             '  <div class="sk-slots" data-ent="구성전체">\n')
    for i, o in enumerate(comp):
        name = o.get("개체", "")
        on = o.get("포함", True)
        off = "" if on else " data-off=1"
        bt, bdisp = shown(f"개체구성.{i}.비고", o.get("비고", ""))
        if i == bi:
            P.append(f'    <div class="sk-slot sk-slot-body" data-ent="본문슬롯">\n'
                     f'      <div class="nm">{e(name)}</div>\n'
                     f'      <div class="how"{bt}>{e(bdisp)}</div>\n')
            meth = (plan.get("적용방법론", {}).get(seq_host or "본문", {})
                    .get("구성", {}).get("방법론", ""))
            if meth:
                mt, mdisp = shown(f"적용방법론.{seq_host}.구성.방법론", meth)
                P.append(f'      <div class="sk-lock"><b>쓰는 방식</b> '
                         f'<span{mt}>{e(mdisp)}</span></div>\n')
            for j, sq in enumerate(seq):
                why = plain(대응[j]) if j < len(대응) else ""
                whyhtml = f'<div class="why">{e(why)}</div>' if why else ""
                P.append(f'      <div class="sk-sec" data-ent="절" data-arr="1" data-path="{spath}.{j}">\n'
                         f'        <div class="t"><span class="no">{j+1}.</span>'
                         f'<span class="tx">{e(sq)}</span></div>\n'
                         f'        {whyhtml}\n'
                         f'        <div class="sk-lock"><b>세부 항목</b> 3~5개 예상 — '
                         f'몇 개를 쓸지와 문구는 내용을 채우면서 정해집니다</div>\n'
                         f'      </div>\n')
            P.append('    </div>\n')
        else:
            offmark = "" if on else '<span class="off">제외됨</span>'
            P.append(f'    <div class="sk-slot" data-ent="개체슬롯" '
                     f'data-flag="개체구성.{i}.포함" data-on="{str(on).lower()}"{off}>\n'
                     f'      <div class="nm">{e(plain(name))}{offmark}</div>\n'
                     f'      <div class="how"{bt}>{e(bdisp)}</div>\n'
                     f'    </div>\n')
    P.append('  </div>\n')

    # 등장요소 자리
    els = plan.get("등장요소_전망", [])
    if els:
        P.append('  <div class="sk-sect-h">표·그림이 들어갈 자리</div>\n')
        for i, el in enumerate(els):
            lv = el.get("가능성", "없음")
            gt, gdisp = shown(f"등장요소_전망.{i}.근거", el.get("근거", ""))
            P.append(f'''  <div class="sk-elem" data-ent="요소자리" data-lv="{e(lv)}"
       data-cycle="등장요소_전망.{i}.가능성">
    <span class="lv">가능성 {e(lv)}</span><b>{e(el.get("요소",""))}</b>
    <div{gt} style="margin-top:1mm">{e(gdisp)}</div>
  </div>\n''')

    # 분량·게이트
    con = plan.get("제약", {})
    bud = con.get("분량예산", {})
    if bud:
        P.append('  <div class="sk-sect-h">분량 기준</div>\n  <div class="sk-budget">\n')
        for k, v in bud.items():
            if str(k).startswith("_"):
                continue                    # 내부 메모는 화면에 내보내지 않는다
            bat, bdisp2 = shown(f"제약.분량예산.{k}", v)
            P.append(f'    <div class="b" data-ent="분량">'
                     f'<span class="k">{e(plain(k))}</span>'
                     f'<span{bat}>{e(bdisp2)}</span></div>\n')
        P.append('  </div>\n')
    # 표기·목차 선택 — 정답이 하나가 아니라 고르는 것들('26.7.30. 실무자 판정)
    if plan.get("판정", {}).get("문서유형") == "fullreport":
        옵 = plan.get("표기", {})
        picks = [("표기방식", "표기.항목기호", 옵.get("항목기호", "도형식"),
                  {"도형식": "도형 □ ○ - ※", "번호식": "번호 1. 가. (1)", "5단 번호식": "5단 번호"}),
                 ("목차설정", "표기.목차", 옵.get("목차", "자동"),
                  {"자동": "자동 (본문 4쪽 이하면 넣지 않음)", "넣음": "항상 넣음", "뺌": "넣지 않음"}),
                 ("목차깊이", "표기.목차깊이", 옵.get("목차깊이", "자동"),
                  {"자동": "자동 (길면 장까지만)", "장과 큰 항목": "장 + 큰 항목(□)", "장만": "장까지만"}),
                 ("간지설정", "표기.간지", 옵.get("간지", "안 넣음"),
                  {"안 넣음": "안 넣음", "장마다": "장마다 넣음"})]
        P.append('  <div class="sk-sect-h">표기 방식</div>\n'
                 '  <div class="sk-note">기관·작성자마다 관행이 달라 정답이 하나가 아닙니다. '
                 '쓰시는 방식을 고르세요.</div>\n  <div class="sk-picks">\n')
        for ent, path, val, show in picks:
            P.append(f'    <div class="sk-pick" data-ent="{e(ent)}" '
                     f'data-cycle="{e(path)}" data-lv="{e(val)}">'
                     f'<span class="k">{e(PICK_KO[ent])}</span>'
                     f'<span class="lv">{e(show.get(val, val))}</span></div>\n')
        P.append('  </div>\n')
    if con.get("게이트"):
        P.append('  <div class="sk-sect-h">자동 검사 항목</div>\n'
                 '  <div class="sk-note">문서를 만든 뒤 아래 항목을 자동으로 검사하고, '
                 '어긋나면 고쳐서 다시 만듭니다. 하나를 누르면 설명이 오른쪽에 나옵니다.</div>\n'
                 '  <div class="sk-gate">'
                 + "".join(f'<span data-ent="검사규칙" data-explain="{e(rule_help(g))}">{e(rule_name(g))}</span>'
                           for g in con["게이트"]) + '</div>\n')

    # 3층 위임 목록
    deleg = plan.get("미확정_3층위임", [])
    if deleg:
        P.append('  <div class="sk-sect-h">내용을 채우면서 정해지는 것</div>\n'
                 '  <div class="sk-note">아래는 실제 내용을 채우면서 정해집니다. '
                 '여기서 미리 확정하지 않습니다.</div>\n')
        for i, d in enumerate(deleg):
            dt2, ddisp = shown(f"미확정_3층위임.{i}", d)
            P.append(f'  <div class="sk-lock" data-ent="위임"{dt2}>{e(ddisp)}</div>\n')

    # 예상 분량
    est, sub = estimate(plan, len(seq))
    P.append(f'''  <div class="sk-est"><b>예상 분량 — {e(est)}</b>
    <div class="sub">{e(sub)}</div>
    <div class="sub">문서를 만든 뒤 분량이 크게 어긋나면 이 화면으로 돌아와 함께 다시 조정합니다.</div>
  </div>
</div>
</body>
</html>
''')
    return "".join(P)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    os.makedirs(OUT, exist_ok=True)
    플랜방 = 자료뿌리.플랜뿌리()
    if args[0] == "--all":
        args = 자료뿌리.플랜들()
    for a in args:
        path = a if os.path.isabs(a) else os.path.join(플랜방, a)
        plan = json.load(open(path, encoding="utf-8"))
        fn = plan.get("plan_id") or os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(OUT, f"{fn}.html")
        with 자료뿌리.쓰기(out) as f:              # 원자 쓰기(WP-S2 ③)
            f.write(build(plan))
        print("skeleton:", os.path.relpath(out, 자료뿌리.뿌리()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
