#!/usr/bin/env python3
"""만들어 본 결과를 잽니다.

무엇을 하나: 만들어진 화면과 문서 내용을 읽어 "실제로 이렇게 나왔다"를 기록합니다.
무엇을 안 하나: 구성 설계를 건드리지 않습니다. 어긋났는지 판단도 하지 않습니다.
                (판단과 반영은 buildplan/rewind.py 몫입니다)

왜 나눴나: 문서를 만드는 쪽이 구성 설계를 쓰면 검사가 돌 때마다 원본이 오염됩니다.
          여기서는 build/observed/ 에만 씁니다.

**못 잰 것을 '통과'로 적지 않습니다.** 문체 검사기가 1페이지 형식만 훑으면서 시행문과
여러 장 보고서에 '위반 0건'을 내던 것이 그 병이었습니다(2026-07-30 수정).
못 재면 사유를 남깁니다.

사용:
  python3 build/observe.py --all          # 전 문서
  python3 build/observe.py <문서>
  python3 build/observe.py --all --pdf    # 시행문 쪽수까지(인쇄 한 번 더)
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 산출물·관측 기록은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# 규칙표(rewind-rules.json)는 코드라 아래에서 ROOT(코드뿌리)로 연다.
import 자료뿌리
SAMPLES = 자료뿌리.산출물뿌리()
OUT = 자료뿌리.관측뿌리()

# 장르 목록은 build/genres.py 가 세어서 준다. 여기 빠진 장르는 --all 로도
# **한 번도 관측되지 않는다** — 귀납 재료가 조용히 비어 간다(2026-08-04).
import genres as _genres
# 크롬 찾는 눈도 하나뿐이어야 한다(build/크롬찾기.py, WP-S8) — CHROME 절대경로를
# 여기 또 박으면 다섯 곳 중 이 한 곳만 컨테이너 배포에서 조용히 갈라진다.
# 여기는 관측(귀납 재료 수집)이라 브라우저가 없으면 죽지 않고 건너뛴다 — `찾기()`(비파괴)를 쓴다.
from 크롬찾기 import 찾기

SRC = [(g["길"], g["키"]) for g in _genres.등록부()]


def load_docs():
    """문서키 → (3층 문서, 장르)"""
    out = {}
    for p, genre in SRC:
        if not os.path.exists(p):
            continue
        for d in json.load(open(p, encoding="utf-8")):
            out[d["filename"]] = (d, genre)
    return out


# ── DOM 회수 ────────────────────────────────────────────────────────────
# 페이지네이터가 인라인 스크립트로 산출 HTML 안에 들어 있다. 순진하게 문자열을
# 찾으면 자기 소스에 걸린다(class="fr-page 가 17건 나오는데 실제 쪽은 9개).
# 그래서 ① script 블록을 먼저 지우고 ② 속성형 정규식만 쓴다.

def strip_scripts(html):
    return re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)


def dump_dom(path):
    """헤드리스로 조판까지 끝난 DOM을 받는다. 없으면 None."""
    크롬 = 찾기()
    if not 크롬:
        return None
    try:
        r = subprocess.run(
            [크롬, "--headless", "--disable-gpu", "--virtual-time-budget=6000",
             "--dump-dom", "file://" + path],
            capture_output=True, text=True, timeout=90)
        return r.stdout or None
    except Exception:
        return None


def pdf_pages(path):
    """PDF로 찍어 쪽수를 센다 — 시행문은 이 길밖에 없다."""
    크롬 = 찾기()
    if not 크롬:
        return None
    tmp = os.path.join(OUT, "_tmp.pdf")
    try:
        subprocess.run(
            [크롬, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             "--virtual-time-budget=6000", f"--print-to-pdf={tmp}", "file://" + path],
            capture_output=True, timeout=120)
        r = subprocess.run(["pdfinfo", tmp], capture_output=True, text=True)
        m = re.search(r"Pages:\s*(\d+)", r.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_dom(dom):
    """조판 결과에서 재는 값들. 없는 값은 키를 만들지 않는다."""
    d = strip_scripts(dom)
    o = {}
    pages = len(re.findall(r'class="fr-page[" ]', d))
    if pages:
        o["쪽수"] = pages
    ov = re.findall(r'data-overflow="1"', d)
    if "data-overflow" in d or pages:
        o["잘린쪽"] = len(ov)
    lhs = re.findall(r"style=\"[^\"]*--lhs:\s*([\d.]+)", d)
    if lhs:
        o["줄간격조정"] = [float(x) for x in lhs]
    tight = len(re.findall(r'data-tighten="', d))
    fill = len(re.findall(r'data-fill="1"', d))
    if pages:
        o["쥐어짬"] = {"당김": tight, "채움": fill}
    jach = re.findall(r'class="jachigan-run"[^>]*letter-spacing:\s*(-?[\d.]+)em', d)
    o["자간압축"] = {"구간": len(jach), "값": [float(x) for x in jach]}
    m = re.search(r'<body[^>]*data-audit="([^"]*)"', d)
    if m:
        try:
            import html as _h
            o["audit"] = json.loads(_h.unescape(m.group(1)))
        except Exception:
            pass
    rows = len(re.findall(r'class="fr-toc-row', d))
    if rows:
        o["목차행"] = rows
    return o


# ── 3층 문서에서 세는 값 ────────────────────────────────────────────────

def dig(doc, spec):
    """'장[].절[].표' 같은 경로로 값을 훑어 존재하는 것만 모은다."""
    cur = [doc]
    for part in spec.split("."):
        nxt = []
        arr = part.endswith("[]")
        key = part[:-2] if arr else part
        for c in cur:
            if not isinstance(c, dict):
                continue
            v = c.get(key)
            if v is None:
                continue
            if arr:
                nxt.extend(v if isinstance(v, list) else [v])
            else:
                nxt.append(v)
        cur = nxt
    return cur


def count_items(doc, genre):
    if genre == "onepage-report":
        return sum(len(s.get("items") or []) for s in doc.get("sections") or [])
    if genre == "gongmun":
        return len(doc.get("본문") or [])
    return sum(len(s.get("항목") or []) for c in doc.get("장") or []
               for s in c.get("절") or [])


def read_doc(doc, genre, rules):
    o = {"장르": genre}
    o["항목수"] = count_items(doc, genre)
    seq = (rules["시퀀스_필드"] or {}).get(genre)
    if seq:
        o["큰항목_제목"] = [str(x) for x in dig(doc, seq)]
    for name, specs in (rules["요소_필드"].get(genre) or {}).items():
        n = 0
        for sp in specs:
            n += sum(1 for v in dig(doc, sp) if v)
        o.setdefault("요소개수", {})[name] = n
    filled = {}
    for name, field in (rules["개체_필드"].get(genre) or {}).items():
        if field is None:
            continue                      # 기계가 만드는 것(목차·끝표시)은 대상이 아니다
        v = doc.get(field)
        filled[name] = bool(v) if not isinstance(v, (int, float)) else True
    o["개체_채워짐"] = filled
    if genre == "fullreport":
        o["장수"] = len(doc.get("장") or [])
    return o


# ── 관측 1건 ────────────────────────────────────────────────────────────

def observe(key, doc, genre, rules, want_pdf=False):
    # _실패 = 재려 했는데 못 잰 것 / _해당없음 = 이 장르에서는 일부러 안 재는 것.
    # 섞으면 설계 판단이 결함처럼 보이고, 진짜 실패가 묻힌다.
    rec = {"문서": key, "장르": genre,
           "때": time.strftime("%Y-%m-%dT%H:%M"), "_실패": [], "_해당없음": []}
    rec.update(read_doc(doc, genre, rules))

    html = os.path.join(SAMPLES, key + ".html")
    if not os.path.exists(html):
        rec["_실패"].append("산출 HTML이 없다 — 조립부터 해야 한다")
        return rec
    rec["산출물_시각"] = time.strftime("%Y-%m-%dT%H:%M",
                                 time.localtime(os.path.getmtime(html)))
    dom = dump_dom(html)
    if dom is None:
        rec["_실패"].append("브라우저로 조판 결과를 볼 수 없었다(Chrome 없음)")
    else:
        rec.update(read_dom(dom))
        a = rec.get("audit") or {}
        if "audit" not in rec:
            rec["_실패"].append("계측값(audit)이 없다 — 조립기가 audit.js를 안 넣었다")
        elif a.get("_못잼"):
            rec["_실패"].append("계측 실패 — " + a["_못잼"])
        elif a.get("_안잰것"):
            rec.setdefault("_해당없음", []).append(a["_안잰것"])
    if genre == "gongmun":
        # 시행문 지면은 min-height 297mm라 넘쳐도 DOM에 표식이 안 남는다.
        # 쪽수만은 인쇄해 봐야 안다.
        if want_pdf:
            p = pdf_pages(html)
            if p:
                rec["쪽수"] = p
            else:
                rec["_실패"].append("인쇄로 쪽수를 세지 못했다")
        else:
            rec["_실패"].append("쪽수를 재지 않았다 — --pdf 를 붙여야 잰다")
    return rec


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args and "--all" not in flags:
        print(__doc__)
        return 2
    os.makedirs(OUT, exist_ok=True)
    rules = json.load(open(os.path.join(ROOT, "buildplan", "rewind-rules.json"),
                           encoding="utf-8"))
    docs = load_docs()
    keys = sorted(docs) if "--all" in flags else args
    want_pdf = "--pdf" in flags

    rows, cands = [], []
    for k in keys:
        if k not in docs:
            print("모르는 문서:", k)
            continue
        doc, genre = docs[k]
        rec = observe(k, doc, genre, rules, want_pdf)
        자료뿌리.원자json(os.path.join(OUT, k + ".json"), rec, indent=1)
        a = rec.get("audit") or {}
        rows.append([k, genre, rec.get("쪽수", ""), rec.get("항목수", ""),
                     a.get("sheetMm", ""), a.get("splits", ""),
                     a.get("sumLines", ""), a.get("fillRatio", ""),
                     rec.get("잘린쪽", ""), len(rec["_실패"])])
        for why in rec["_실패"]:
            cands.append({"문서": k, "장르": genre, "사실": why})
        print(f"관측: {k}" + (f"  (못 잰 것 {len(rec['_실패'])}건)" if rec["_실패"] else ""))

    with 자료뿌리.쓰기(os.path.join(OUT, "_summary.csv")) as f:
        f.write("문서,장르,쪽수,항목수,sheetMm,어절분리,요약줄,채움도,잘린쪽,못잰것\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")

    # 도구·규칙의 문제로 보이는 것은 따로 모은다 — 원장에 자동으로 쓰지는 않는다
    자료뿌리.원자json(os.path.join(OUT, "_ledger-candidates.json"),
                   {"_doc": "규칙·도구 차원의 문제로 보이는 것. 사람이 읽고 원장에 옮긴다.",
                    "항목": cands}, indent=1)
    # 관측 기록은 **자료**다 — 자료뿌리 기준으로 적는다(WP-S2 ②). 코드뿌리 기준으로
    # 적으면 세션·다른 뿌리에서 `../../../..` 로 나와 어디에 썼는지 아무도 못 읽는다.
    print(f"\n{len(rows)}건 → {os.path.relpath(OUT, 자료뿌리.뿌리())}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
