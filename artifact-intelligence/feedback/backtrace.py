#!/usr/bin/env python3
"""수정 diff 역추적기 — 피드백 루프의 귀납 수집 장치.

사용자가 4층 산출물(HTML)을 직접 리터칭하면, 3층 정본(JSON)과의 차이를 감지해
①정본에 수용(동기화)하고 ②원시 diff를 관측 로그에 축적한다(반복 패턴 → 규칙 후보).

원리: 기대본 = assemble.build(정본 JSON)을 메모리에서 렌더 → 현재 파일과 세그먼트 비교.
조립기 자체를 임포트하므로 정규화 불일치로 인한 가짜 diff가 없다.
불변식: --adopt 직후의 --scan은 diff 0건이어야 한다(라운드트립).

사용:
  python3 feedback/backtrace.py --scan [filename]     # 수정 감지(전체 또는 특정 문서)
  python3 feedback/backtrace.py --adopt <filename>    # HTML 수정을 3층 정본에 수용(+백업)
  python3 feedback/backtrace.py --log <filename>      # diff를 edit-log.jsonl에 관측 기록
테스트용 오버라이드: --html <path> --docs <path>
"""
import argparse
import datetime
import difflib
import html as htmlmod
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 코드뿌리

# 등록부·산출물·관측 기록·백업은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다
# (WP-S2 ①). 조립기는 코드라 여기 ROOT 에서 그대로 불러 쓴다.
_사양 = importlib.util.spec_from_file_location("자료뿌리", ROOT / "build" / "자료뿌리.py")
자료뿌리 = importlib.util.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

DOCS = Path(자료뿌리.등록부("samples"))
SAMPLES = Path(자료뿌리.산출물뿌리())
EDITLOG = Path(자료뿌리.편집기록길())
BACKUPS = Path(자료뿌리.피드백백업뿌리())

spec = importlib.util.spec_from_file_location("assemble", ROOT / "build" / "assemble.py")
assemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble)


def plain(s):
    t = re.sub(r"<[^>]+>", "", s or "")
    t = htmlmod.unescape(t).replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


# ── HTML → 세그먼트 추출 (조립 출력 구조 계약: h1.doc-title / .doc-byline /
#    .doc-summary / h2.h-l1 / p.i-lN / .doc-table-wrap / .doc-attach) ──

STREAM_RE = re.compile(
    r'<h2 class="h-l1"[^>]*>(?P<head>.*?)</h2>'
    r'|<p class="(?P<lv>i-l\d)"(?P<iat>[^>]*)>(?P<item>.*?)</p>'
    r'|<div class="doc-table-wrap"[^>]*>(?P<tbl>.*?)</table>\s*</div>'
    r'|<p class="doc-attach"[^>]*>(?P<attach>.*?)</p>', re.S)


def _first(pattern, src):
    m = re.search(pattern, src, re.S)
    return m.group(1).strip() if m else ""


def extract(src):
    doc = {
        "title": plain(_first(r'<h1 class="doc-title"[^>]*>(.*?)</h1>', src)),
        "byline": plain(_first(r'class="doc-byline"[^>]*>(.*?)</', src)),
        "summary": plain(_first(r'class="doc-summary"[^>]*>(.*?)</div>', src)),
        "sections": [], "table": None, "attach": None,
    }
    for key, pat in (("title_fs", r'<h1 class="doc-title"[^>]*font-size:\s*([\d.]+)pt'),
                     ("summary_fs", r'class="doc-summary"[^>]*font-size:\s*([\d.]+)pt')):
        fm = re.search(pat, src)
        if fm:
            doc[key] = float(fm.group(1))
    cur = None
    for m in STREAM_RE.finditer(src):
        if m.group("head") is not None:
            cur = {"heading": plain(m.group("head")), "items": []}
            doc["sections"].append(cur)
        elif m.group("item") is not None:
            level = int(m.group("lv")[-1])
            inner = m.group("item").strip()
            if cur is None:
                cur = {"heading": "", "items": []}
                doc["sections"].append(cur)
            item = {"level": level, "html": inner}
            fsm = re.search(r"font-size:\s*([\d.]+)pt", m.group("iat") or "")
            if fsm:
                item["fs"] = float(fsm.group(1))
            cur["items"].append(item)
        elif m.group("tbl") is not None:
            t = m.group("tbl")
            caption = plain(_first(r'class="doc-table-caption"[^>]*>(.*?)</div>', t))
            trs = re.findall(r"<tr>(.*?)</tr>", t, re.S)
            header, rows = [], []
            for tr in trs:
                ths = re.findall(r"<th[^>]*>(.*?)</th>", tr, re.S)
                tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                if ths:
                    header = [plain(x) for x in ths]
                elif tds:
                    rows.append([plain(x) for x in tds])
            doc["table"] = {"caption": caption, "header": header, "rows": rows,
                            "after_heading": cur["heading"] if cur else ""}
            sm_ = re.search(r'data-style="([^"]+)"', t)
            if sm_:
                doc["table"]["style"] = sm_.group(1)
        elif m.group("attach") is not None:
            txt = plain(m.group("attach"))
            doc["_attach_el"] = True
            doc["_end_mark"] = txt.endswith("끝.")
            doc["attach"] = None if txt in ("끝.", "") else txt
    doc.setdefault("_attach_el", False)
    doc.setdefault("_end_mark", False)
    return doc


# ── 비교 ──────────────────────────────────────────────────────


def diff_docs(exp, act):
    """세그먼트 diff 목록. 각 항목 {segment, before(정본 기대), after(현재 파일)}."""
    out = []

    def add(seg, b, a):
        if (b or "") != (a or ""):
            out.append({"segment": seg, "before": b or "", "after": a or ""})

    for k in ("title", "byline", "summary"):
        add(k, exp[k], act[k])
    for k in ("title_fs", "summary_fs"):
        if (exp.get(k) or None) != (act.get(k) or None):
            add(f"글자 크기({k})", str(exp.get(k) or "기본"), str(act.get(k) or "기본"))

    eh = [s["heading"] for s in exp["sections"]]
    ah = [s["heading"] for s in act["sections"]]
    sm = difflib.SequenceMatcher(a=eh, b=ah)
    pairs = []  # (exp_idx|None, act_idx|None)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            pairs += [(i, j1 + (i - i1)) for i in range(i1, i2)]
        else:
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                pairs.append((i1 + k if i1 + k < i2 else None,
                              j1 + k if j1 + k < j2 else None))
    for ei, ai in pairs:
        es = exp["sections"][ei] if ei is not None else None
        as_ = act["sections"][ai] if ai is not None else None
        if es is None:
            add(f"절 추가({as_['heading']})", "", as_["heading"])
            for it in as_["items"]:
                add(f"{as_['heading']} › 항목 추가", "", plain(it["html"]))
        elif as_ is None:
            add(f"절 삭제({es['heading']})", es["heading"], "")
            for it in es["items"]:
                add(f"{es['heading']} › 항목 삭제", plain(it["html"]), "")
        else:
            add(f"절 제목", es["heading"], as_["heading"]) if es["heading"] != as_["heading"] else None
            _diff_items(es, as_, out)

    et, at = exp.get("table"), act.get("table")
    if bool(et) != bool(at):
        add("표", "표 있음" if et else "", "표 있음" if at else "")
    elif et:
        add("표 스타일", et.get("style", "샌드위치"), at.get("style", "샌드위치"))
        add("표 캡션", et.get("caption", ""), at.get("caption", ""))
        add("표 머리행", " | ".join(et.get("header", [])), " | ".join(at.get("header", [])))
        er = [" | ".join(r) for r in et.get("rows", [])]
        ar = [" | ".join(r) for r in at.get("rows", [])]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=er, b=ar).get_opcodes():
            if tag == "equal":
                continue
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                b = er[i1 + k] if i1 + k < i2 else ""
                a = ar[j1 + k] if j1 + k < j2 else ""
                add(f"표 {i1+k+1}행" if b else "표 행 추가", b, a)

    add("붙임", exp.get("attach") or "", act.get("attach") or "")
    if exp.get("_end_mark") != act.get("_end_mark"):
        add("종결 표기(끝.)", "표시" if exp.get("_end_mark") else "숨김",
            "표시" if act.get("_end_mark") else "숨김")
    return out


def _nh(s):
    """서식 비교용 — 태그 보존, 공백만 정규화."""
    return re.sub(r"\s+", " ", (s or "")).strip()


def _diff_items(es, as_, out):
    ep = [plain(i["html"]) for i in es["items"]]
    ap = [plain(i["html"]) for i in as_["items"]]
    sm = difflib.SequenceMatcher(a=ep, b=ap)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            # 텍스트 동일 — 레벨·인라인 서식(스팬) 변경을 별도 감지
            for k in range(i2 - i1):
                ei, ai = es["items"][i1 + k], as_["items"][j1 + k]
                if ei["level"] != ai["level"]:
                    out.append({"segment": f"{es['heading']} › 레벨 변경",
                                "before": f"{ep[i1+k]} ({ei['level']}단)",
                                "after": f"({ai['level']}단)"})
                elif (ei.get("fs") or None) != (ai.get("fs") or None):
                    out.append({"segment": f"{es['heading']} › 글자 크기",
                                "before": f"{ep[i1+k]} ({ei.get('fs') or '기본'}pt)",
                                "after": f"({ai.get('fs') or '기본'}pt)"})
                elif _nh(ei["html"]) != _nh(ai["html"]):
                    out.append({"segment": f"{es['heading']} › 강조·서식 변경",
                                "before": _nh(ei["html"]), "after": _nh(ai["html"])})
            continue
        n = max(i2 - i1, j2 - j1)
        for k in range(n):
            b = ep[i1 + k] if i1 + k < i2 else ""
            a = ap[j1 + k] if j1 + k < j2 else ""
            seg = f"{es['heading']} › 항목"
            if not b:
                seg = f"{es['heading']} › 항목 추가"
            elif not a:
                seg = f"{es['heading']} › 항목 삭제"
            out.append({"segment": seg, "before": b, "after": a})


# ── 수용(adopt): HTML 현재 상태를 3층 정본으로 ──────────────────


def adopt(doc, act):
    doc["title"] = act["title"]
    if act["byline"]:
        doc["byline"] = f"<{act['byline']}>" if not act["byline"].startswith("<") else act["byline"]
    doc["summary"] = act["summary"]
    for k in ("title_fs", "summary_fs"):
        if act.get(k):
            doc[k] = act[k]
        else:
            doc.pop(k, None)
    doc["sections"] = [
        {"heading": s["heading"],
         "items": [{k: v for k, v in (("level", i["level"]), ("html", i["html"]),
                    ("fs", i.get("fs"))) if v is not None} for i in s["items"]]}
        for s in act["sections"]]
    if act["table"]:
        t = dict(act["table"])
        old = doc.get("table") or {}
        if old.get("after_heading") in [s["heading"] for s in act["sections"]]:
            t["after_heading"] = old["after_heading"]
        doc["table"] = t
    else:
        doc["table"] = None
    if act["attach"]:
        raw = re.sub(r"^붙임\s*", "", act["attach"])
        raw = re.sub(r"\s*끝\.\s*$", "", raw).strip()
        doc["attach"] = assemble.norm_attach(raw) if raw else None
    else:
        doc["attach"] = None
    doc["show_end_mark"] = bool(act.get("_end_mark"))
    return doc


# ── CLI ──────────────────────────────────────────────────────


def load_pair(docs_path, fn, html_path=None):
    docs = json.load(open(docs_path, encoding="utf-8"))
    doc = next((d for d in docs if d["filename"] == fn), None)
    if doc is None:
        sys.exit(f"정본에 없는 문서: {fn}")
    hp = Path(html_path) if html_path else SAMPLES / f"{fn}.html"
    if not hp.exists():
        sys.exit(f"HTML 없음: {hp}")
    exp = extract(assemble.build(doc))
    act = extract(hp.read_text(encoding="utf-8"))
    return docs, doc, exp, act


def print_diffs(fn, diffs):
    if not diffs:
        print(f"{fn}: 수정 없음 (정본과 일치)")
        return
    print(f"{fn}: 수정 {len(diffs)}건 감지")
    for d in diffs:
        print(f"  [{d['segment']}]")
        if d["before"]:
            print(f"    정본: {d['before'][:80]}")
        if d["after"]:
            print(f"    현재: {d['after'][:80]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", nargs="?", const="*", default=None)
    ap.add_argument("--adopt", default=None)
    ap.add_argument("--log", dest="log_fn", default=None)
    ap.add_argument("--html", default=None)
    ap.add_argument("--docs", default=str(DOCS))
    args = ap.parse_args()

    if args.scan:
        docs = json.load(open(args.docs, encoding="utf-8"))
        targets = [d["filename"] for d in docs] if args.scan == "*" else [args.scan]
        dirty = 0
        for fn in targets:
            hp = Path(args.html) if (args.html and args.scan != "*") else SAMPLES / f"{fn}.html"
            if not hp.exists():
                continue
            _, doc, exp, act = load_pair(args.docs, fn, hp)
            diffs = diff_docs(exp, act)
            if diffs or args.scan != "*":
                print_diffs(fn, diffs)
            dirty += bool(diffs)
        if args.scan == "*":
            print(f"— 전체 {len(targets)}건 중 수정 감지 {dirty}건")
        return 0

    if args.log_fn:
        _, doc, exp, act = load_pair(args.docs, args.log_fn, args.html)
        diffs = diff_docs(exp, act)
        stamp = datetime.date.today().isoformat()
        for d in diffs:                       # E-7 — 한 줄씩 O_APPEND 한 번 쓰기
            자료뿌리.원자덧쓰기(str(EDITLOG),
                            json.dumps({"date": stamp, "filename": args.log_fn, **d},
                                       ensure_ascii=False))
        print(f"관측 기록: {len(diffs)}건 → {EDITLOG.name}")
        return 0

    if args.adopt:
        docs, doc, exp, act = load_pair(args.docs, args.adopt, args.html)
        diffs = diff_docs(exp, act)
        if not diffs:
            print(f"{args.adopt}: 수용할 수정 없음")
            return 0
        BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy(args.docs, BACKUPS / f"samples-docs.{stamp}.json")
        hp = Path(args.html) if args.html else SAMPLES / f"{args.adopt}.html"
        shutil.copy(hp, BACKUPS / f"{args.adopt}.{stamp}.html")

        adopt(doc, act)
        # 고정점 수렴: 조립기의 정규화·기계 집행(쉼표 공백, 붙임 수량, 강조 상한)을
        # 정본에 한 번 더 반영 — 이후 build(doc) == 파일이 보장된다(라운드트립 불변식).
        canonical = extract(assemble.build(doc))
        adopt(doc, canonical)
        enforced = diff_docs(act, canonical)
        # 원자 쓰기(WP-S2 ③) — 등록부(E-1)와 산출물(E-5) 둘 다.
        # 특히 `assemble.build(doc)` 은 여기서 죽을 수 있다(도형·표가 깨져 있으면).
        # 예전에는 write_text 가 파일을 먼저 자른 뒤 죽어 **0바이트 산출물**이 남았다.
        자료뿌리.원자json(args.docs, docs, indent=1)
        자료뿌리.원자쓰기(str(hp), assemble.build(doc))
        print(f"{args.adopt}: 수정 {len(diffs)}건을 정본에 수용, 산출물 재동기화 (백업: backups/*.{stamp}.*)")
        for d in enforced:
            print(f"  [규범 보정] {d['segment']}: 수정 내용이 조립 규범으로 정돈됨 → {d['after'][:60]}")
        print("다음 단계: 문체 게이트 확인(python3 build/stylelint.py), PDF 재생성(bash build/render_verify.sh)")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
