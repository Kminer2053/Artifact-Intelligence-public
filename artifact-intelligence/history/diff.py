#!/usr/bin/env python3
"""무엇이 달라졌나 — 두 버전을 맞대어 사람이 읽을 수 있게 냅니다.

왜 새로 만들었나: 예전 계산기는 목록을 **위치로** 비교했습니다. 장 하나를 맨 앞에 넣으면
그 뒤가 전부 한 칸씩 밀려 51곳이 바뀐 것처럼 나왔습니다(실제로는 1곳). 실제로 재봤습니다:

    장 하나를 맨 앞에 넣었을 때 → 51건 (허위 50건)
    같은 입력을 이 계산기로     →  1건

그래서 목록은 위치가 아니라 **정체**로 맞춥니다. 항목마다 이름표(제목·표 제목 따위)를
뽑아 차례를 맞춘 뒤, 짝지어진 것만 속을 들여다봅니다.

사용:
  python3 history/diff.py <문서> <옛 버전> <새 버전>
  python3 history/diff.py --시험
"""
import difflib
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

# 등록부는 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
import importlib.util as _iu
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(ROOT, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

# 목록 원소를 무엇으로 알아볼 것인가 — 앞에 있는 것부터 찾는다
이름표키 = ("제목", "캡션", "개체", "heading", "label", "이름", "요소", "text", "html")


def 이름표(v):
    if isinstance(v, dict):
        for k in 이름표키:
            if v.get(k):
                return re.sub(r"<[^>]+>", "", str(v[k]))[:60]
        return json.dumps(v, ensure_ascii=False, sort_keys=True)[:60]
    return str(v)[:60]


def diff_doc(old, new, path=""):
    """('바뀜'|'추가'|'지움', 경로, 전, 후) 목록."""
    out = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            if str(k).startswith("_"):
                continue                      # 내부 표기는 사람이 볼 것이 아니다
            if k not in old:
                out.append(("추가", f"{path}.{k}", None, 이름표(new[k])))
            elif k not in new:
                out.append(("지움", f"{path}.{k}", 이름표(old[k]), None))
            else:
                out += diff_doc(old[k], new[k], f"{path}.{k}")
        return out
    if isinstance(old, list) and isinstance(new, list):
        a, b = [이름표(x) for x in old], [이름표(x) for x in new]
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    out += diff_doc(old[i], new[j], f"{path}.{i}")
            elif op == "insert":
                for j in range(j1, j2):
                    out.append(("추가", f"{path}.{j1}", None, b[j]))
            elif op == "delete":
                for i in range(i1, i2):
                    out.append(("지움", f"{path}.{i}", a[i], None))
            else:                              # replace — 짝지어 속을 본다
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    out += diff_doc(old[i], new[j], f"{path}.{i}")
                for j in range(j1 + (i2 - i1), j2):
                    out.append(("추가", f"{path}.{j}", None, b[j]))
                for i in range(i1 + (j2 - j1), i2):
                    out.append(("지움", f"{path}.{i}", a[i], None))
        return out
    if old != new:
        out.append(("바뀜", path, old, new))
    return out


# ── 경로를 사람이 읽는 말로 ──────────────────────────────────────────────

차례 = ["첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째", "일곱째", "여덟째", "아홉째", "열째"]
말 = {"장": "장", "절": "절", "항목": "항목", "sections": "본문", "items": "항목",
     "표지": "표지", "요약": "요약", "별첨": "참고자료", "본문": "본문", "붙임": "붙임",
     "title": "제목", "summary": "요약 상자", "heading": "큰 항목 제목", "html": "",
     "text": "", "제목": "제목", "캡션": "표 제목", "attach": "붙임", "byline": "작성자",
     "표": "표", "도식": "그림", "글꼴": "글꼴", "포인트색": "포인트색"}


def 이름(path):
    """'.장.2.절.0.제목' → '3장 첫째 절 제목'"""
    부분 = [p for p in path.split(".") if p]
    out, i = [], 0
    while i < len(부분):
        p = 부분[i]
        다음 = 부분[i + 1] if i + 1 < len(부분) else None
        if 다음 is not None and 다음.isdigit():
            n = int(다음)
            이름말 = 말.get(p, p)
            if p in ("장", "sections"):
                out.append(f"{n + 1}{이름말 if p == '장' else '번째 ' + 이름말}")
            else:
                out.append(f"{차례[n] if n < len(차례) else str(n + 1) + '번째'} {이름말}")
            i += 2
            continue
        w = 말.get(p, p)
        if w:
            out.append(w)
        i += 1
    return " ".join(out) or "문서"


def 요약(diffs):
    """사람이 읽는 묶음 — 새로 생긴 것 / 없어진 것 / 바뀐 것."""
    새, 없, 바 = [], [], []
    for 종류, path, a, b in diffs:
        if 종류 == "추가":
            새.append((이름(path), b))
        elif 종류 == "지움":
            없.append((이름(path), a))
        else:
            바.append((이름(path), a, b))
    return {"새로 생긴 것": 새, "없어진 것": 없, "바뀐 것": 바}


def 시험():
    import copy
    sys.path.insert(0, os.path.join(ROOT, "workspace"))
    from apply_edit_any import diff_keys
    d = [x for x in json.load(open(자료뿌리.등록부("fullreport"), encoding="utf-8"))
         if x["filename"] == "fr-task100-plan"][0]
    새 = copy.deepcopy(d)
    새["장"].insert(0, {"제목": "추진 배경", "절": [{"제목": "왜", "항목": [{"text": "배경", "level": 2}]}]})
    옛수, 새수 = len(diff_keys(d, 새)), len(diff_doc(d, 새))
    문구 = copy.deepcopy(d)
    문구["장"][0]["절"][0]["항목"][0]["text"] += " 보강"
    문옛, 문새 = len(diff_keys(d, 문구)), len(diff_doc(d, 문구))
    print(f"  장 하나 맨 앞에 넣기 — 예전 {옛수}건 → 지금 {새수}건 (1건이어야 함)")
    print(f"  문구 한 곳만 고치기  — 예전 {문옛}건 → 지금 {문새}건 (1건이어야 함)")
    for 종류, p, a, b in diff_doc(d, 새):
        print(f"    [{종류}] {이름(p)}  {a or ''}{' → ' if a and b else ''}{b or ''}")
    ok = 새수 == 1 and 문새 == 1
    print("  " + ("✓ 통과" if ok else "✗ 실패"))
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if not a or a[0] == "--시험":
        return 시험()
    key, n1, n2 = a[0], int(a[1]), int(a[2])
    sys.path.insert(0, BASE)
    import version as V
    옛 = json.load(open(os.path.join(V.버전방(key, n1), "doc.json"), encoding="utf-8"))
    새 = json.load(open(os.path.join(V.버전방(key, n2), "doc.json"), encoding="utf-8"))
    묶음 = 요약(diff_doc(옛, 새))
    print(f"\n■ 버전 {n1} → 버전 {n2}, 무엇이 달라졌나")
    for 제목, rows in 묶음.items():
        if not rows:
            continue
        print(f"\n  {제목}")
        for r in rows:
            if len(r) == 2:
                print(f"    · {r[0]} — {r[1]}")
            else:
                print(f"    · {r[0]}\n        고치기 전: {r[1]}\n        고친 뒤: {r[2]}")
    if not any(묶음.values()):
        print("  달라진 것이 없습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
