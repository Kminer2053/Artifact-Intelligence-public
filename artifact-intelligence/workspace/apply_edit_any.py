#!/usr/bin/env python3
"""편집 반영기 — 편집기 저장본을 정본에 되쓰고 다시 만든다. 전 장르 하나로.

편집기(범용)는 원본 모델을 복제해 경로로 패치한 doc을 저장한다:
    ws-edit-<key> = {doc, instructions, ops}
이 스크립트는 그 doc을 정본 JSON에 되쓰고, 해당 조립기를 다시 돌리고,
편집기까지 재생성한다. 즉 "고쳐놨어" 한 마디의 기계 부분 전부.

찾는 곳(키로 자동 판별):
  build/samples-docs.json      filename  → assemble.py            1페이지 보고서
  build/gongmun-docs.json      filename  → assemble_gongmun.py    시행문
  build/fullreport-docs.json   filename  → assemble_full.py       여러 장 보고서
  buildplan/plan-*.json        plan_id   → render_skeleton.py     구성 설계(골격)

하지 않는 것 — AI 지시(instructions):
  "이 부분을 표로 바꿔줘" 같은 요청은 내용을 다시 써야 하므로 기계가 처리하지 않는다.
  목록으로 출력만 하고, 사람(또는 에이전트)이 반영한 뒤 다시 돌린다.

안전장치:
  ① 쓰기 전 정본을 .bak-<시각>으로 백업
  ② 되쓴 뒤 다시 조립해 왕복 불변식(원본→화면→원본)이 성립하는지 확인
  ③ --dry 로 무엇이 바뀌는지만 보기

사용:
  python3 workspace/apply_edit_any.py --payload <payload.json> [--dry] [--판없이]
  python3 workspace/apply_edit_any.py --payload - < payload.json      # 표준입력
  (payload = 편집기 localStorage 값. 키는 payload.doc.filename 또는 plan_id로 자동 판별)
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "history"))
try:
    import version as HIST          # 이력 — 판을 뜨고 요청한 말을 남긴다
except Exception:                   # 이력 없이도 편집은 돌아야 한다
    HIST = None

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

# 장르 목록은 build/genres.py 가 세어서 준다 — 손으로 적으면 늘 때마다 빠진다.
# 여기 빠지면 그 장르는 **편집해도 정본에 되쓸 수 없다**(2026-08-04 규정·보도자료에서 겪음).
sys.path.insert(0, os.path.join(ROOT, "build"))
import genres as _genres
import 자료뿌리                    # 등록부·플랜이 어느 뿌리에 있는지(WP-S2 ①)


def _sources():
    # 조립기는 **코드**(ROOT 상대), 등록부는 **자료**(자료뿌리의 절대 경로)다.
    # 예전에는 둘 다 "build/..." 상대 문자열이라 rel() 하나로 코드뿌리에 붙었다 —
    # 자료뿌리를 옮기면 남의 뿌리의 정본을 고치게 되는 자리였다.
    return [(g["길"], "filename", ["build/" + g["조립기"], g["길"]], g["라벨"])
            for g in _genres.등록부()]


SOURCES = _sources()


def rel(p):
    """**코드뿌리** 기준 경로 — 조립기·화면 생성기 같은 스크립트 자리다."""
    return os.path.join(ROOT, p)


# ── AI 지시를 어느 단계로 보낼지 가른다 ──
# 지시 중 상당수는 문구가 아니라 '구성' 변경이다("이 절을 표로 바꿔줘" = 표를 쓸지 말지).
# 문서만 고치고 구성 설계를 두면 계획서가 실물보다 뒤처진다 → 구성 변경은 되돌린다.
#
# [설계 변경 2026-07-28] 정규식으로 의도를 분류하려던 첫 판은 실패했다.
# 적대 검증이 확정한 것: 존댓말 어미('빼 주세요')를 통째로 놓치고, '목표로·지표로'가
# '표로'에 걸리고, '통합돌봄·분리배출' 같은 사업명이 구성 지시로 잡히고, '오른쪽'의
# '쪽'이 분량으로 읽혔다. 한국어 의도 분류를 정규식으로 하는 것 자체가 무리다.
#
# 그래서 판정을 **비대칭**으로 바꾼다:
#   미탐(구성인데 문구로 → 계획서가 뒤처짐) 은 치명적이고,
#   오탐(문구인데 구성으로 → 골격에 항목 하나 더 뜸) 은 가볍다.
# → 명백히 문구인 것만 문구로 두고, 나머지는 전부 구성 설계로 보내 사람이 판단한다.
#   정규식은 '확정'이 아니라 '무엇이 바뀔 수 있는지' 힌트로만 쓴다.

STRUCTURAL = [
    (r"(?<![가-힣])표로|(?<![가-힣])표를|(?<![가-힣])표\s*(형태|형식)|도표|도식|그림|차트|그래프"
     r"|table|chart|graph", "표·그림 자리"),
    (r"(?<![가-힣])나눠|(?<![가-힣])분리(?!배출|발주|수거)|쪼개|합쳐|합치"
     r"|(?<![가-힣])통합(?!돌봄|관제|지원)", "본문을 몇 개로 나눌지"),
    (r"순서(?!대로\s*나열)|맨\s*(앞|뒤)|위로\s*올려|아래로\s*내려", "구성 순서"),
    (r"빼|삭제|제외(?!\s*대상)|없애|제거|지워|생략|덜어", "구성 요소 포함 여부"),
    (r"추가|넣어|하나\s*더|늘려", "구성 요소·항목 추가"),
    (r"(?<![가-힣])쪽수|페이지|(?<![가-힣])\d+\s*p(?![a-z])|분량|한\s*장|한\s*쪽", "분량 기준"),
    (r"(?<![가-힣])(장|절)을|항목\s*수(?!정|준|집|령)|(?<![가-힣])(장|절)\s*수", "구성 단위"),
]
# 명백히 문구 수정인 신호 — 이것만 있고 구성 신호가 없을 때만 '문구'로 둔다
TEXTUAL = [r"공손|말투|문체|어투|존댓|높임", r"오타|맞춤법|띄어쓰기|표기",
           r"다듬|간결|매끄럽|자연스럽", r"근거|출처|수치를?\s*(추가|보강)"]
SENTENCE = r"문장|한\s*줄|표현|어투|낱말|단어"


def classify(text):
    """('구성'|'문구'|'확인필요', 무엇이 바뀔 수 있는가)

    미탐이 오탐보다 훨씬 비싸므로, 명백히 문구인 것만 문구로 둔다.
    """
    import re
    t = str(text or "")
    hits = [what for pat, what in STRUCTURAL if re.search(pat, t)]
    textual = any(re.search(p, t) for p in TEXTUAL)
    sentence_scope = re.search(SENTENCE, t)

    # 문장·표현 단위를 명시했으면 구성이 아니다("이 문장을 두 개로 나눠 주세요")
    if sentence_scope and hits and hits != ["표·그림 자리"]:
        hits = [h for h in hits if h in ("표·그림 자리", "분량 기준")]

    if not hits:
        return ("문구", "") if textual else ("확인필요", "")
    if textual:
        return "확인필요", " · ".join(hits)
    return "구성", " · ".join(hits)


def plan_of(key):
    """이 문서가 어느 구성 설계에서 나왔는지 — 되돌릴 곳을 찾는다."""
    bp = 자료뿌리.플랜뿌리()
    if not os.path.isdir(bp):
        return None, None
    for f in sorted(os.listdir(bp)):
        if not (f.startswith("plan-") and f.endswith(".json")):
            continue
        full = os.path.join(bp, f)
        d = json.load(open(full, encoding="utf-8"))
        if d.get("산출물") == key or d.get("plan_id") == key:
            return full, d
    return None, None


def back_key(it):
    """같은 것으로 볼 기준. 기계가 잰 것은 관측 코드로, 사람이 낸 것은 문구로 센다."""
    return (it.get("_관측코드") or "", it.get("계획경로") or "",
            it.get("개체") or "", "" if it.get("_관측코드") else (it.get("요청") or ""))


def send_back(key, items, 출처):
    """구성 설계로 되돌린다 — 계획서가 실물보다 뒤처지지 않게.

    같은 것이 이미 대기 중이면 새로 쌓지 않고 최신 값으로 갱신한다(횟수만 올린다).
    매번 관측을 돌리는데 카드가 매번 늘어나면 화면이 못 쓰게 된다.
    """
    path, plan = plan_of(key)
    if not plan:
        return None, 0
    plan.setdefault("되돌림", [])
    stamp = time.strftime("'%y. %-m. %-d.")
    n = 0
    for it in items:
        k = back_key(it)
        prev = next((x for x in plan["되돌림"]
                     if back_key(x) == k and x.get("상태", "확인 전") in ("확인 전", "해결됨")), None)
        if prev is not None:
            prev.update({**it, "출처": 출처, "상태": "확인 전", "받은날": stamp,
                         "_횟수": (prev.get("_횟수") or 1) + 1})
            n += 1
            continue
        if any(back_key(x) == k for x in plan["되돌림"]):
            continue                      # 이미 사람이 처리한 것은 되살리지 않는다
        plan["되돌림"].append({**it, "출처": 출처, "상태": "확인 전",
                            "받은날": stamp, "_횟수": 1})
        n += 1
    if n:
        plan["_수정시각"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        shutil.copy2(path, path + ".bak-" + time.strftime("%m%d-%H%M%S"))
        자료뿌리.원자json(path, plan, indent=1)     # 원자 쓰기(WP-S2 ③, E-3)
        # 구성 설계가 바뀐 것도 이력에 남긴다 — 지금까지는 .bak 파일 하나가 전부였다
        if HIST:
            HIST.기록(key, "되돌림", 누가="자동" if 출처 == "자동 검사" else "사람",
                    출처=출처, 얹은건수=n,
                    항목=[{"개체": i.get("개체"), "무엇": i.get("관측") or i.get("요청"),
                          "성격": i.get("성격")} for i in items[:10]])
    return path, n


def 바뀐것(old, new):
    """무엇이 달라졌는지 — 항목을 정체로 맞춰 센다(history/diff.py).

    위치로 비교하던 옛 계산기는 항목 하나를 끼워 넣으면 뒤가 전부 바뀐 것으로 냈다.
    그 목록이 그대로 이력에 남으면 나중에 아무도 못 읽는다.
    """
    try:
        sys.path.insert(0, os.path.join(ROOT, "history"))
        import diff as D
        return [(D.이름(p), a, b) if 종류 == "바뀜"
                else (D.이름(p), a if 종류 == "지움" else "", b if 종류 == "추가" else "")
                for 종류, p, a, b in D.diff_doc(old, new)]
    except Exception:
        return diff_keys(old, new)


def 짧게(v, n=60):
    v = str(v)
    return v if len(v) <= n else v[:n] + "…"


def 다른데(a, b, n=90):
    """긴 값에서 실제로 달라진 대목만 잘라낸다 — 앞 60자만 보면 둘이 같아 보인다."""
    a, b = str(a), str(b)
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    s0 = max(0, i - 20)
    return (("…" if s0 else "") + a[s0:s0 + n] + ("…" if s0 + n < len(a) else ""),
            ("…" if s0 else "") + b[s0:s0 + n] + ("…" if s0 + n < len(b) else ""))


def 조작요약(ops):
    """조작 기록을 한 줄로 줄인다. 원본은 브라우저 안에만 두고 파일로 내리지 않는다."""
    if not ops:
        return ""
    from collections import Counter
    c = Counter(str(o.get("action") or "").strip() for o in ops if o.get("action"))
    return " · ".join(f"{k} {n}번" if n > 1 else k for k, n in c.most_common(6))


def find_target(key):
    """키가 어느 정본의 몇 번째 항목인지 찾는다."""
    for full, idfield, cmd, label in SOURCES:
        if not os.path.exists(full):
            continue
        docs = json.load(open(full, encoding="utf-8"))
        for i, d in enumerate(docs):
            if d.get(idfield) == key:
                return {"kind": "doc", "path": full, "index": i, "id": idfield,
                        "cmd": cmd, "label": label}
    bp = 자료뿌리.플랜뿌리()
    if not os.path.isdir(bp):
        return None
    for f in sorted(os.listdir(bp)):
        if not (f.startswith("plan-") and f.endswith(".json")):
            continue
        full = os.path.join(bp, f)
        d = json.load(open(full, encoding="utf-8"))
        if d.get("plan_id") == key:
            return {"kind": "plan", "path": full, "index": None, "id": "plan_id",
                    "cmd": ["buildplan/render_skeleton.py", full], "label": "구성 설계"}
    return None


def diff_keys(old, new, path=""):
    """[낡음] 목록을 위치로 비교한다 — 항목을 하나 끼워 넣으면 뒤가 전부 바뀐 것으로
    나온다(실측: 장 하나 추가에 51건, 실제 1건). history/diff.py 로 갈아탔고,
    이 함수는 회귀 시험이 '예전엔 이랬다'를 보여주기 위해 남겨 둔다."""
    out = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            out += diff_keys(old.get(k), new.get(k), f"{path}.{k}")
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            out.append((path, f"{len(old)}개", f"{len(new)}개"))
        for i in range(min(len(old), len(new))):
            out += diff_keys(old[i], new[i], f"{path}.{i}")
    elif old != new:
        out.append((path, str(old), str(new)))     # 자르지 않는다 — 자르면 이력에서
    return out                                     # 전과 후가 같은 줄이 남는다


def run(cmd):
    """`cmd[0]` 은 **코드뿌리 기준 스크립트**, 나머지는 **그 스크립트에 그대로 줄 인자**다.

    고침 2026-08-07 (WP-S2 ② + PR#1 합류): 예전에는 절대경로가 아닌 인자를 **전부**
    `rel()` 로 코드뿌리에 붙였다. 문서 키 "a1-04-regulation" 이 <코드뿌리>/<키> 라는
    없는 경로가 되고, `--skeletons`·`--all` 깃발까지 <코드뿌리>/--skeletons 로 결합돼
    셋 다 FileNotFoundError 로 죽었다. 그런데 render_workspace 가 세 장르(1p·시행문·
    풀버전) 편집기를 손목록으로 겸사 재생성해 줘서 **규정·보도자료만** 저장 후 편집
    화면이 낡은 채 남았고, 이 자리는 종료코드를 안 보고 ✓ 를 찍어 실패가 가려졌다.
    (render_workspace 는 2026-08-11 은퇴 — 이제 c1 하나가 전 장르 편집기를 굽고, 이
    자리가 c1 의 종료코드를 본다. check_edit_refresh 가 규정으로 그것을 실측한다.)
    조립기 인자(등록부)는 자료뿌리가 이미 절대경로로 주므로 손댈 것이 없다.

    자식에게 세션을 물려준다 — 안 물려주면 세션 뿌리에서 저장했는데 편집 화면만
    기본 뿌리에 다시 생긴다(그리고 화면은 아무 문제 없어 보인다).
    """
    스크립트 = cmd[0] if os.path.isabs(cmd[0]) else rel(cmd[0])
    r = subprocess.run([sys.executable, 스크립트] + [str(c) for c in cmd[1:]],
                       capture_output=True, text=True, cwd=ROOT,
                       env=자료뿌리.자식환경())
    if r.returncode != 0:
        # 조용한 실패 금지(구현계획 규칙 3) — 호출부가 반환값을 안 봐도 흔적은 남는다
        꼬리 = (r.stdout + r.stderr).strip().splitlines()
        print(f"  ✗ {os.path.basename(스크립트)} 실패 (exit {r.returncode})"
              + (f" — {꼬리[-1]}" if 꼬리 else ""))
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    args = sys.argv[1:]
    if "--payload" not in args:
        print(__doc__)
        return 2
    src = args[args.index("--payload") + 1]
    dry = "--dry" in args
    # 자동 저장은 몇 초마다 온다. 그때마다 판을 만들면 되돌릴 지점이 수백 개가 되어
    # 오히려 못 찾는다 — 이력(기록)은 매번 남기고 판은 서버가 간격을 두고 요청한다.
    판없이 = "--판없이" in args
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    payload = json.loads(raw)
    doc = payload.get("doc") or {}
    key = doc.get("filename") or doc.get("plan_id") or payload.get("key")
    if not key:
        print("✗ 어느 문서인지 알 수 없습니다 — payload.doc에 filename 또는 plan_id가 없습니다")
        return 1

    tgt = find_target(key)
    if not tgt:
        print(f"✗ '{key}'를 정본에서 찾지 못했습니다")
        return 1

    cur = json.load(open(tgt["path"], encoding="utf-8"))
    old = cur[tgt["index"]] if tgt["kind"] == "doc" else cur
    changes = 바뀐것(old, doc)

    print(f"■ {tgt['label']} — {key}")
    
    if not changes:
        print("  바뀐 내용 없음")
    else:
        print(f"  바뀐 곳 {len(changes)}군데")
        for p, a, b in changes[:12]:
            if not a:
                print(f"    {p} — 새로 생김: {짧게(b, 70)}")
            elif not b:
                print(f"    {p} — 없어짐: {짧게(a, 70)}")
            else:
                a2, b2 = 다른데(a, b, 70)
                print(f"    {p}\n      전: {a2}\n      후: {b2}")
        if len(changes) > 12:
            print(f"    … 외 {len(changes) - 12}군데")

    ops = payload.get("ops") or []
    if ops:
        print(f"  고친 내역 {len(ops)}건: " +
              ", ".join(f"{o.get('action')}{'→' + str(o.get('to')) if o.get('to') else ''}"
                        for o in ops[-8:]))

    inst = payload.get("instructions") or {}
    보관req = payload.get("보관요청") or {}
    if dry:
        print("  (--dry — 쓰지 않았습니다)")
        return 0
    # 되돌림 지점(보관요청)은 편집이 없어도 잡을 수 있어야 한다 — "지금 이 상태"를
    # 그대로 표시해 두는 것이 용도다. 예전엔 여기서 조기 반환해 편집 없는 지점이
    # 조용히 사라졌다(changes 블록 안에서만 보관했다).
    if not changes and not inst and not 보관req.get("종류"):
        return 0

    if changes:
        # ── 낙관적 잠금을 **창 바깥**에서 검사한다 (적대리뷰 ④) ──────────────
        #
        # 무엇이 틀렸었나 — 예전에는 314행에서 한 번 읽어 둔 `cur` 을 40줄 뒤에
        # `디스크 = cur[...]` 라 부르며 `_수정시각` 을 비교했다. 이름만 디스크이지
        # 실체는 **같은 스냅샷**이라, 화면을 오래 열어 둔 사람(순차 stale)만 잡고
        # 정작 겹쳐 들어온 동시 저장은 양쪽 다 통과시켰다. 결과가 특히 나빴다:
        # 응답이 409 가 아니라 200 ok:true 라서 편집기는 성공한 줄 알고, 실측으로
        # 동시 저장 4건이 전부 200 인데 둘만 남았다.
        #
        # 이제 **빗장을 쥐고 디스크에서 다시 읽어** 비교하고, 그 빗장 안에서 쓴다.
        # 자리(index)도 다시 찾는다 — 그 사이 남이 문서를 넣고 빼서 밀렸을 수 있다.
        # 조립·화면 재생성은 빗장 밖에서 한다(자기 문서 하나만 건드리므로 안전하고,
        # subprocess 를 쥔 채 남을 몇 초씩 세우지 않는다).
        판번호 = None
        try:
            빗장 = 자료뿌리.빗장(tgt["path"])
            빗장.__enter__()
        except 자료뿌리.못잠금 as e:
            # 조용한 실패 금지 — 못 저장했으면 못 했다고 응답에 실린다(0 아닌 종료코드).
            print(f"  ✗ 저장하지 못했습니다: {e}")
            return 1
        try:
            cur = json.load(open(tgt["path"], encoding="utf-8"))
            if tgt["kind"] == "doc":
                자리 = next((i for i, d in enumerate(cur)
                           if d.get(tgt["id"]) == key), None)
                if 자리 is None:
                    print(f"  ✗ '{key}'가 그 사이에 정본에서 사라졌습니다 — 저장하지 "
                          "않았습니다. 화면을 새로고침해 주세요.")
                    return 1
                tgt["index"] = 자리
                디스크 = cur[자리]
            else:
                디스크 = cur
            disk = (디스크 or {}).get("_수정시각")
            seen = doc.get("_수정시각")
            if disk and seen != disk:
                무엇 = "구성 설계가" if tgt["kind"] == "plan" else "이 문서가"
                print(f"  ✗ 이 화면을 연 뒤에 {무엇} 바뀌었습니다.")
                print("    화면을 새로고침한 뒤 다시 저장해 주세요 — 지금 저장하면 그 사이 "
                      "바뀐 것이 지워집니다.")
                return 1
            # 문서는 마이크로초까지(같은 초에 겹친 저장을 가르려면 필요하다),
            # 구성 설계는 초 단위 그대로 — `자료뿌리.문서수정시각` 주석에 근거를 적었다.
            doc["_수정시각"] = (자료뿌리.문서수정시각() if tgt["kind"] == "doc"
                            else time.strftime("%Y-%m-%dT%H:%M:%S"))

            # 고치기 전에 지금 상태를 판으로 남긴다 — .bak 파일은 '언제'만 알려주고
            # '무엇이 왜'를 못 알려줬다. 판에는 문서·계획서·이유가 함께 남는다.
            if HIST and tgt["kind"] == "doc":
                요약 = 조작요약(payload.get("ops") or [])
                if not 판없이:
                    판번호 = HIST.보관(key, "자동", 누가="사람", 고친내역=요약)
                HIST.기록(key, "손질", 누가="사람", 버전=판번호, 바뀐곳=len(changes),
                        **{"고친 내역": 요약},
                        전후=[{"종류": ("추가" if not c[1] else "지움" if not c[2] else "바뀜"),
                              "경로": c[0],
                              "전": (다른데(c[1], c[2])[0] if c[1] and c[2] else 짧게(c[1], 120)),
                              "후": (다른데(c[1], c[2])[1] if c[1] and c[2] else 짧게(c[2], 120))}
                            for c in changes[:20]])
            else:
                shutil.copy2(tgt["path"], tgt["path"] + ".bak-" + time.strftime("%m%d-%H%M%S"))
            if tgt["kind"] == "doc":
                cur[tgt["index"]] = doc
            else:
                cur = doc
            # 원자 쓰기(WP-S2 ③, E-1) — 정본 등록부를 자르고 흘려 넣는 사이에
            # 문서목록·조립기가 읽으면 반토막을 본다.
            자료뿌리.원자json(tgt["path"], cur,
                           indent=2 if tgt["kind"] == "doc" else 1)
        finally:
            빗장.__exit__(None, None, None)
        print("  ✓ 문서에 반영했습니다"
              + (f" (고치기 전 상태를 버전 {판번호}으로 보관했습니다)" if 판번호 else ""))

        # **자기 문서만 다시 만든다**(WP-S2 ②). 예전에는 등록부 전체를 조립해서
        # 한 건을 저장할 때마다 같은 장르의 다른 문서 HTML 이 전부 다시 써졌다 —
        # 세션을 갈라 놓아도 한 세션 안에서 그대로 남는 문제였다.
        cmd = tgt["cmd"] + (["--only", key] if tgt["kind"] == "doc" else [])
        code, out = run(cmd)
        print(f"  {'✓' if code == 0 else '✗'} 다시 만들기: {out.splitlines()[-1] if out else '완료'}")
        if code != 0:
            print("  ↳ 문서를 만들지 못했습니다")
            return 1
        # 화면 재생성 결과를 **본다.** 안 보면 여기가 죽어도 아래 ✓ 가 찍힌다
        # (그 조용한 실패로 저장 때마다 편집 화면이 안 만들어지고 있었다 — run() 주석).
        if tgt["kind"] == "plan":
            c1, o1 = run(["workspace/render_editor_any.py", "--skeletons"])
        else:
            c1, o1 = run(["workspace/render_editor_any.py", key])
        if c1:
            print("  ✗ 편집 화면을 다시 만들지 못했습니다: "
                  + (o1.splitlines()[-1] if o1 else "까닭 모름"))
            return 1
        print("  ✓ 편집 화면을 다시 만들었습니다")

    # 화면에서 누른 '되돌림 지점' — 정적 화면은 파일을 못 써서 여기까지 실려 온다.
    # **changes 블록 밖**이라 편집이 없어도 잡힌다 — 편집이 있으면 그 결과를(위에서
    # 이미 정본에 썼다), 없으면 지금 상태를 그대로 남긴다.
    if HIST and 보관req.get("종류") == "직접" and tgt["kind"] == "doc":
        n2 = HIST.보관(key, "직접", 고친이유=보관req.get("고친이유", ""),
                     메모=보관req.get("메모", ""), 누가="사람")
        print(f"  ✓ 되돌림 지점(버전 {n2})을 잡았습니다 (화면·인쇄본 함께)")

    if inst:
        back, text = [], []
        for where, what in inst.items():
            kind, target = classify(what)
            if HIST and tgt["kind"] == "doc":
                # 구성이든 문구든 원문 그대로 남긴다. 나중에 "이 문장 왜 바뀌었냐"에
                # 답할 수 있는 유일한 재료다.
                HIST.기록(key, "지시", 누가="사람", 자리=where, 원문=what,
                        성격=kind, 처리="대기")
            (back if kind in ("구성", "확인필요") else text).append(
                {"개체": where, "요청": what, "성격": kind, "바뀌는것": target})
        if back and tgt["kind"] == "doc":
            ppath, n = send_back(key, back, "문서 편집")
            if ppath and n:
                print(f"\n■ 구성 설계로 되돌렸습니다 — {n}건")
                for b in back:
                    mark = "확인 필요" if b["성격"] == "확인필요" else "구성 변경"
                    print(f"  · [{mark}] {b['개체']}: {b['요청']}")
                    if b["바뀌는것"]:
                        print(f"      바뀌는 것 — {b['바뀌는것']}")
                print(f"  ↳ {os.path.relpath(ppath, 자료뿌리.뿌리())} · 구성 설계 화면에서 확인하세요")
                run(["buildplan/render_skeleton.py", "--all"])
                run(["workspace/render_editor_any.py", "--skeletons"])
        elif back and tgt["kind"] == "plan":
            print(f"\n■ 구성 설계에 대한 지시 {len(back)}건 — 이 화면에서 직접 고쳐 주세요")
            for b in back:
                print(f"  · {b['개체']}: {b['요청']}")
        elif back:
            text += back
        if text:
            print(f"\n■ 사람이 반영할 것 — 문구 수정 {len(text)}건 (자동으로 고치지 않습니다)")
            for b in text:
                print(f"  · {b['개체']}: {b['요청']}")
            print("  ↳ 내용을 다시 쓴 뒤 이 명령을 한 번 더 돌리면 됩니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
