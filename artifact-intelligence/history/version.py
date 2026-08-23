#!/usr/bin/env python3
"""문서 기록 — 지난 상태를 버전으로 보관하고, 요청하신 말을 남기고, 되돌린다.

여기가 history/ 에 쓰는 유일한 코드다. 다른 파일은 이 함수만 부른다.

왜 만들었나: 예전에는 문서를 고치기 전에 .bak-<시각> 파일만 하나 남았다. 그 파일에는
'언제'만 있고 '무엇이 왜 바뀌었는지'가 없다. "이 문장 왜 바뀌었냐"고 물으면 답할 수
없고, 앞 내용으로 돌아가야 할 때 꺼낼 물건이 없다.

무엇이 남나
  버전 — 그때의 문서 전문 + 그때의 구성 설계 사본 + 무엇을 고쳤는지
  요청 — 사용자가 AI에게 시킨 말의 원문. 구성 변경이든 문구 수정이든 전부. 계속 남는다.
  고친 내역 — 무엇이 어디서 어디로 바뀌었는지
무엇이 안 남나
  이름·계정·접속 기록·키 입력·화면 열람. 누가 했는지는 '사람'과 '자동' 둘로만 적는다.

이 기록은 작업하실 때 참고하시라고 모아 둔 것이다. 기관의 공식 기록은 아니다.

사용:
  python3 history/version.py --목록 <문서>
  python3 history/version.py --보관 <문서> --메모 "..." --이유 "..."
  python3 history/version.py --되돌리기 <문서> --버전 2
  python3 history/version.py --시작           # 문서 기록을 만듭니다
  python3 history/version.py --정리 [--진짜로] # 오래된 자동 보관본을 지웁니다
  python3 history/version.py --옛파일정리      # 남아 있는 .bak 파일을 기록에 옮긴다
"""
import glob
import importlib.util as _iu
import json
import os
import re
import shutil
import sys
import time

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 코드뿌리

# 자료뿌리 — 이력·등록부·산출물이 어디 있는지는 build/자료뿌리.py 한 곳이 정한다
# (WP-S2 ①). sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 S9).
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(CODE, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

# **BASE 라는 모듈 상수를 없앤 이유**(2026-08-07, WP-S2 ① — 부록 G-1):
# `BASE`·`SRC` 가 import 시 상수라 세션을 끼워 넣을 주입점이 없었다. 문서 이름만이
# 유일한 차원이라 세션 둘이 같은 슬러그("plan")를 쓰면 이력이 한 방에 합쳐졌다.
# 이제 뿌리는 **부를 때마다** 정해진다.
#   · 검사 격리(verify_all 의 check_cleanup·check_rewind_dedup)는 예전에
#     `V.BASE = tempdir` 로 모듈 상수를 바꿔치기했다. BASE 가 없어졌으므로 그 대입은
#     아무 데도 안 닿는다 — **조용히 깨지는** 자리라 대신 `뿌리갈기()` 를 두고
#     verify_all 도 같이 고쳤다(그 검사가 갈아끼운 뿌리를 직접 확인한다).
_덮개 = None


def 뿌리갈기(경로):
    """이 모듈이 볼 이력 뿌리를 갈아끼운다. **검사 격리 전용**이다.

    돌려주는 것은 이전 값 — 끝나면 반드시 그것으로 되돌려라. None 이면 자료뿌리를 본다.
    """
    global _덮개
    이전, _덮개 = _덮개, 경로
    return 이전


def 이력뿌리():
    return _덮개 or 자료뿌리.이력뿌리()


def 정본들():
    """(등록부 경로, 장르 키) 전수 — **세어서** 얻는다.

    예전에는 다섯 줄짜리 손목록(SRC)이었다. 장르를 늘리면서 여기 빠뜨리면
    **그 장르만 이력이 안 남는다** — genres.py 머리말의 두 번째 함정이 이것이다.
    이제 등록부 파일을 세는 build/genres.py 하나에서 온다.
    """
    genres = 자료뿌리.모듈("genres")
    return [(g["길"], g["키"]) for g in genres.등록부()]

# 버전 종류는 둘뿐이다 — 사람이 눌러 남긴 것과 고칠 때 자동으로 남은 것.
# 상신·반려로 갈랐던 것은 코드가 한 묶음으로 다루고 있어 구분이 없었다.
종류들 = ("자동", "직접")
상태들 = ("작성 중", "마무리")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def 문서방(key):
    return os.path.join(이력뿌리(), key)


def 기록길(key):
    return os.path.join(문서방(key), "문서.json")


def 기록읽기(key):
    p = 기록길(key)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None


def 기록쓰기(key, d):
    os.makedirs(문서방(key), exist_ok=True)
    자료뿌리.원자json(기록길(key), d, indent=1)     # 원자 쓰기(WP-S2 ③)


def 기록(key, 사건, **필드):
    """기록에 한 줄. 버전이 정리돼도 이건 남는다.

    첫 인자 이름이 '사건'인 이유: 버전에도 '종류'(자동·직접)가 있어 이름이 부딪혔다.
    """
    os.makedirs(문서방(key), exist_ok=True)
    row = {"때": now(), "종류": 사건}
    row.update(필드)
    # append 는 O_APPEND 한 번 쓰기로 — 여러 프로세스가 붙일 때 줄이 갈리지 않게(E-7)
    자료뿌리.원자덧쓰기(os.path.join(문서방(key), "journal.jsonl"),
                    json.dumps(row, ensure_ascii=False))
    return row


def 읽기(key):
    p = os.path.join(문서방(key), "journal.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for ln in open(p, encoding="utf-8"):
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


# ── 정본에서 문서를 찾는다 ─────────────────────────────────────────────

def 문서찾기(key):
    """(문서파일, 항목번호, 문서, 종류) — 없으면 (None, None, None, None)"""
    for p, genre in 정본들():
        if not os.path.exists(p):
            continue
        docs = json.load(open(p, encoding="utf-8"))
        for i, d in enumerate(docs):
            if d.get("filename") == key:
                return p, i, d, genre
    return None, None, None, None


def 구성설계찾기(key):
    bp = 자료뿌리.플랜뿌리()
    if not os.path.isdir(bp):
        return None, None
    for f in sorted(os.listdir(bp)):
        if not (f.startswith("plan-") and f.endswith(".json")):
            continue
        full = os.path.join(bp, f)
        try:
            d = json.load(open(full, encoding="utf-8"))
        except Exception:
            continue
        if d.get("산출물") == key or d.get("plan_id") == key:
            return full, d
    return None, None


# ── 판 ──────────────────────────────────────────────────────────────────

def 버전방(key, n):
    return os.path.join(문서방(key), f"버전-{n:04d}")


def 색인빗장(key):
    """이 문서의 이력 색인(`문서.json`)을 고치는 동안 남을 막는다. (적대리뷰 ⑦)

    무엇이 틀렸었나 — `판번호따기()` 는 `os.mkdir` 로 번호를 제대로 배타적으로 잡는데,
    그 뒤 `보관()` 이 색인을 `기록읽기() → insert → 기록쓰기()` 로 고치는 자리엔
    배타성이 없었다. 그래서 **판 디렉터리는 다 만들어지는데 색인엔 일부만 적혔다** —
    프로세스 8개로 재니 8판이 디스크에 다 있는데 색인엔 8·7·2 만 남았다(1·3·4·5·6
    다섯 판이 화면에서 사라지고 사람이 되돌릴 수도 없다). `현재 버전` 도 실제 최대치와
    어긋나 다음 `판번호따기` 의 시작값이 뒤로 밀렸다.

    등록부(`*-docs.json`)와 **다른 파일**이라 등록부만 원자화한 WP-S2 ③ 으로는 안 덮인다.
    잠그는 법은 자료뿌리의 빗장 하나로 통일한다(새 방식을 만들지 않는다).

    잠금 차례(교착 방지) — `workspace/apply_edit_any.py` 는 **등록부 빗장을 쥔 채**
    여기 색인 빗장을 잡는다(등록부 → 색인). 그 반대 차례로 잡는 자리는 없어야 한다.
    `되돌리기()` 는 `보관()`(색인 빗장, 그 안에서 놓음)을 **먼저 끝내고** 그 다음에
    등록부 빗장을 잡으므로 둘을 겹쳐 쥐지 않는다.
    """
    os.makedirs(문서방(key), exist_ok=True)
    return 자료뿌리.빗장(기록길(key))


def 판번호따기(key, 처음):
    """비어 있는 판 번호 하나를 **배타적으로** 잡는다. (WP-S2 ③ — 부록 E-2)

    예전에는 `n = 현재버전+1` 로 번호를 정하고 `os.makedirs(exist_ok=True)` 로
    방을 만들었다. 같은 문서를 둘이 동시에 저장하면 둘 다 같은 번호를 읽고
    **같은 방에 서로 덮어쓴다** — 한쪽의 판이 소리 없이 사라진다.

    `os.mkdir` 은 이미 있으면 FileExistsError 로 선다. 그 성질이 곧 잠금이다:
    먼저 만든 쪽이 그 번호를 갖고, 진 쪽은 다음 번호로 올라간다. 돌려주는 것은
    (실제로 잡은 번호, 그 방).
    """
    n = max(1, int(처음))
    os.makedirs(문서방(key), exist_ok=True)
    for _ in range(1000):
        방 = 버전방(key, n)
        try:
            os.mkdir(방)
            return n, 방
        except FileExistsError:
            n += 1
    raise RuntimeError(f"'{key}' 의 빈 판 번호를 못 찾았습니다 (마지막 시도 {n})")


def 보관(key, 종류="자동", 고친이유="", 메모="", 누가="사람", 고친내역=""):
    """지금 상태를 판으로 남긴다. 정본을 고치기 **전에** 부른다.

    반환: 판 번호. 정본에 없는 키면 None.
    """
    if 종류 not in 종류들:
        raise ValueError(f"알 수 없는 값입니다: {종류}")
    src, idx, doc, genre = 문서찾기(key)
    if doc is None:
        return None
    # 번호를 읽고 → 판을 만들고 → 색인에 끼우기까지가 한 덩이다. 갈라 놓으면 판만
    # 생기고 색인엔 안 적힌다(적대리뷰 ⑦ — `색인빗장` 주석에 실측을 적어 뒀다).
    with 색인빗장(key):
        d = 기록읽기(key) or 새기록(key, genre, src)
        n, 방 = 판번호따기(key, int(d.get("현재 버전") or 0) + 1)

        자료뿌리.원자json(os.path.join(방, "doc.json"), doc, indent=2)
        동봉 = ["doc.json"]

        ppath, plan = 구성설계찾기(key)
        if plan is not None:
            # 계획서는 언제든 되돌림이 얹혀 바뀐다. plan_id 는 파일만 가리키고
            # 그때의 상태를 가리키지 않으므로 사본을 함께 둔다(수 KB라 비용이 없다).
            자료뿌리.원자json(os.path.join(방, "plan.json"), plan, indent=1)
            동봉.append("plan.json")

        # 사람이 직접 남긴 것만 실물(화면·인쇄본)을 함께 보관한다
        if 종류 == "직접":
            for name, p in (("문서.html", 자료뿌리.산출물(key, "html")),
                            ("문서.pdf", 자료뿌리.산출물(key, "pdf"))):
                if os.path.exists(p):
                    shutil.copy2(p, os.path.join(방, name))
                    동봉.append(name)

        머리 = {"버전": n, "종류": 종류, "때": now(), "누가": 누가,
               "고친 이유": 고친이유, "메모": 메모, "고친 내역": 고친내역,
               "잰 값": 잰것(key), "함께 보관": 동봉}
        자료뿌리.원자json(os.path.join(방, "버전.json"), 머리, indent=1)

        d["현재 버전"] = n
        d["마지막 보관"] = 머리["때"]
        d.setdefault("버전", []).insert(0, {k: 머리[k] for k in ("버전", "종류", "때", "메모")})
        기록쓰기(key, d)
    # journal 은 O_APPEND 한 줄 쓰기라 빗장이 필요 없다(E-7) — 빗장 밖에서 적는다.
    기록(key, "보관", 누가=누가, 버전=n, 종류=종류,
       **({"메모": 메모} if 메모 else {}),
       **({"고친 이유": 고친이유} if 고친이유 else {}))
    return n


def 새기록(key, genre, src):
    ppath, _ = 구성설계찾기(key)
    뿌 = 자료뿌리.뿌리()
    return {"키": key, "문서 종류": genre, "문서": os.path.relpath(src, 뿌),
            "구성 설계": os.path.relpath(ppath, 뿌) if ppath else None,
            "상태": "작성 중", "현재 버전": 0, "버전": []}


def 잰것(key):
    """관측이 있으면 그때 값을 함께 남긴다 — 나중에 '그때 몇 쪽이었나'에 답한다.

    단, 관측이 산출물보다 오래됐으면 넣지 않는다. 옛 값을 이 판의 값인 것처럼 적으면
    기록이 거짓말을 한다 — 쪽수가 늘었는데 옛 쪽수가 남는 식으로.
    """
    p = os.path.join(자료뿌리.관측뿌리(), key + ".json")
    html = 자료뿌리.산출물(key, "html")
    if not os.path.exists(p):
        return {}
    if os.path.exists(html) and os.path.getmtime(p) < os.path.getmtime(html):
        return {"_안잼": "문서를 다시 만든 뒤로 쪽수·분량을 재지 않았습니다"}
    try:
        o = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    a = o.get("audit") or {}
    out = {}
    for k, v in (("쪽수", o.get("쪽수")), ("항목수", o.get("항목수")),
                 ("어절분리", a.get("splits")), ("채움도", a.get("fillRatio")),
                 ("잘린쪽", o.get("잘린쪽"))):
        if v is not None:
            out[k] = v
    return out


def 목록(key):
    d = 기록읽기(key)
    if not d:
        return []
    out = []
    for row in d.get("버전", []):
        방 = 버전방(key, row["버전"])
        hp = os.path.join(방, "버전.json")
        out.append(json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else row)
    return out


def 되돌리기(key, n, 고친이유=""):
    """옛 버전 내용으로 지금 문서를 바꾼다. 되돌리기 전 상태도 버전으로 남기므로
    지금 내용이 없어지지 않는다."""
    방 = 버전방(key, n)
    dp = os.path.join(방, "doc.json")
    if not os.path.exists(dp):
        return None, f"버전 {n}이 없습니다"
    src, idx, cur, genre = 문서찾기(key)
    if cur is None:
        return None, "그런 문서가 없습니다"
    직전 = 보관(key, "자동", 고친이유=f"버전 {n}으로 되돌리기 전 상태", 누가="사람")
    old = json.load(open(dp, encoding="utf-8"))
    # 등록부도 **읽고-고치고-쓰는** 자리다 — 빗장 안에서 다시 읽고 자리도 다시 찾는다.
    # (`보관()` 은 위에서 이미 끝났다 — 색인 빗장과 등록부 빗장을 겹쳐 쥐지 않는다)
    with 자료뿌리.빗장(src):
        docs = json.load(open(src, encoding="utf-8"))
        자리 = next((i for i, x in enumerate(docs) if x.get("filename") == key), None)
        if 자리 is None:
            return None, "그런 문서가 없습니다"
        docs[자리] = old
        자료뿌리.원자json(src, docs, indent=2)      # 원자 쓰기(WP-S2 ③, E-1)
    기록(key, "되돌리기", 누가="사람", 되돌린버전=n, 직전버전=직전, 고친이유=고친이유)
    return n, None


def 지우기(key, n):
    """되돌림 지점(사람이 직접 남긴 버전) 하나를 지운다.

    **직접 것만** 지운다 — 자동 보관본은 정리() 몫이고, 사람이 실수로 되돌림 지점
    자리를 자동본으로 비우지 않게 한다. 되돌림 지점은 최대 3개라, 새로 잡으려면
    이 함수로 하나를 비운다(웹앱에서 사용자가 고른다).
    """
    with 색인빗장(key):
        d = 기록읽기(key)
        if not d:
            return None, "그런 문서가 없습니다"
        행 = next((r for r in d.get("버전", []) if int(r.get("버전", -1)) == int(n)), None)
        if 행 is None:
            return None, f"버전 {n}이 없습니다"
        if 행.get("종류") != "직접":
            return None, "되돌림 지점(직접 보관)만 지울 수 있습니다"
        d["버전"] = [r for r in d.get("버전", []) if int(r.get("버전", -1)) != int(n)]
        기록쓰기(key, d)
    방 = 버전방(key, n)
    if os.path.isdir(방):
        shutil.rmtree(방, ignore_errors=True)     # doc·plan·실물·버전.json 한 폴더째
    기록(key, "지우기", 누가="사람", 지운버전=int(n))
    return int(n), None


# ── 도입 ────────────────────────────────────────────────────────────────

def 정리(일수=30, 진짜로=False):
    """오래된 자동 보관본을 지웁니다.

    자동 보관본은 고칠 때마다 늘어납니다. 안 지우면 문서 하나에 수백 개가 쌓입니다.
    **직접 보관하신 것과 요청하신 말은 지우지 않습니다** — 나중에 "이 문장 왜 바뀌었냐"에
    답할 재료는 요청하신 말이고, 그건 버전이 아니라 기록에 있습니다.
    """
    import datetime
    자른날 = (datetime.datetime.now() - datetime.timedelta(days=일수)).strftime("%Y-%m-%d")
    지운것 = []
    for d in sorted(glob.glob(os.path.join(이력뿌리(), "*", "문서.json"))):
        key = os.path.basename(os.path.dirname(d))
        L = 기록읽기(key)
        if not L:
            continue
        남길, 지울 = [], []
        for row in L.get("버전", []):
            방 = 버전방(key, row["버전"])
            hp = os.path.join(방, "버전.json")
            종류 = row.get("종류")
            if not 종류 and os.path.exists(hp):
                종류 = json.load(open(hp, encoding="utf-8")).get("종류")
            if 종류 == "자동" and row.get("때", "")[:10] < 자른날:
                지울.append(row)
            else:
                남길.append(row)
        if not 지울:
            continue
        지운것.append((key, len(지울)))
        if 진짜로:
            for row in 지울:
                shutil.rmtree(버전방(key, row["버전"]), ignore_errors=True)
            # 색인을 다시 읽어 **지울 판만** 뺀다 — 위에서 고른 뒤 여기 올 때까지
            # 다른 요청이 새 판을 끼웠을 수 있다(적대리뷰 ⑦과 같은 창).
            with 색인빗장(key):
                지운번호 = {row["버전"] for row in 지울}
                지금 = 기록읽기(key) or L
                지금["버전"] = [r for r in 지금.get("버전", [])
                             if r.get("버전") not in 지운번호]
                기록쓰기(key, 지금)
            기록(key, "정리", 누가="자동", 지운수=len(지울), 기준일수=일수,
               말=f"{일수}일이 지난 자동 보관본을 정리했습니다. "
                 "직접 보관하신 것과 요청하신 말은 그대로 있습니다.")
    return 지운것


def 시작():
    """문서마다 기록 자리를 만든다. 이미 있으면 그대로 둔다."""
    n = 0
    for p, genre in 정본들():
        if not os.path.exists(p):
            continue
        for d in json.load(open(p, encoding="utf-8")):
            k = d.get("filename")
            if not k or 기록읽기(k):
                continue
            기록쓰기(k, 새기록(k, genre, p))
            n += 1
    return n


BAK = re.compile(r"\.bak-(\d{4})-(\d{6})$")


def 옛파일정리():
    """예전에 남던 .bak 파일을 기록에 옮겨 적는다. 파일 자체는 지우지 않는다."""
    moved = []
    뿌 = 자료뿌리.뿌리()
    for p in sorted(glob.glob(os.path.join(뿌, "buildplan", "*.json.bak-*"))
                    + glob.glob(os.path.join(뿌, "build", "*.json.bak-*"))):
        m = BAK.search(p)
        base = p[:m.start()] if m else p
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        keys = []
        if isinstance(data, list):
            keys = [x.get("filename") for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            keys = [data.get("산출물") or data.get("plan_id")]
        keys = [k for k in keys if k]
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S",
                              time.localtime(os.path.getmtime(p)))
        for k in keys:
            기록(k, "옛백업", 행위자="기계", 파일=os.path.relpath(p, 뿌),
               원본=os.path.relpath(base, 뿌), 만든때=stamp,
               메모="이력을 만들기 전에 남아 있던 백업입니다")
        moved.append((os.path.relpath(p, 뿌), keys))
    return moved


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    cmd = a[0]

    def opt(name, default=""):
        return a[a.index(name) + 1] if name in a else default

    if cmd == "--정리":
        일수 = int(opt("--일수", "30"))
        진짜로 = "--진짜로" in a
        결과 = 정리(일수, 진짜로)
        if not 결과:
            print(f"{일수}일이 지난 자동 보관본이 없습니다")
            return 0
        전체 = sum(n for _, n in 결과)
        for k, n in 결과:
            print(f"  {k}: {n}개")
        if 진짜로:
            print(f"\n{일수}일이 지난 자동 보관본 {전체}개를 정리했습니다. "
                  "직접 보관하신 것과 요청하신 말은 그대로 있습니다.")
        else:
            print(f"\n정리 대상 {전체}개입니다. 실제로 지우려면 --진짜로 를 붙이세요.")
        return 0
    if cmd == "--시작":
        print(f"문서 기록 {시작()}건을 만들었습니다")
        return 0
    if cmd == "--옛파일정리":
        mv = 옛파일정리()
        for p, ks in mv:
            print(f"  {p} → {', '.join(ks) or '(문서를 찾지 못함)'}")
        print(f"예전 파일 {len(mv)}건을 기록에 적었습니다. 파일 자체는 그대로 두었습니다.")
        return 0
    key = a[1] if len(a) > 1 and not a[1].startswith("--") else ""
    if cmd == "--목록":
        rows = 목록(key)
        if not rows:
            print("보관한 버전이 없습니다")
            return 0
        for r in rows:
            꼬리 = r.get("메모") or r.get("고친 이유") or ""
            print(f"  버전 {r['버전']} [{r['종류']}] {r['때']}" + (f" — {꼬리}" if 꼬리 else ""))
        return 0
    if cmd == "--보관":
        n = 보관(key, "직접", opt("--이유"), opt("--메모"))
        print(f"버전 {n}으로 보관했습니다" if n else "그런 문서가 없습니다")
        return 0 if n else 1
    if cmd == "--되돌리기":
        n, err = 되돌리기(key, int(opt("--버전", "0")), opt("--이유"))
        print(err or f"버전 {n} 내용으로 되돌렸습니다. 되돌리기 전 상태도 버전으로 보관했습니다.")
        return 1 if err else 0
    if cmd == "--지우기":
        n, err = 지우기(key, int(opt("--버전", "0")))
        print(err or f"되돌림 지점(버전 {n})을 지웠습니다.")
        return 1 if err else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
