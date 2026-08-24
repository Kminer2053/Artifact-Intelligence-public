#!/usr/bin/env python3
"""문서를 만드는 방식이 바뀌었는지, 바뀌었다면 결과가 달라지는지 확인합니다.

왜 필요한가: 만드는 방식을 고치면 이미 만든 문서가 낡습니다. 그런데 그걸 알려 주는
장치가 없으면 사람이 기억해서 다시 만들어야 하고, 잊으면 낡은 문서가 그대로 나갑니다.

두 갈래로 나눠서 봅니다(ontology/파급표.json):
  문서를 만드는 것 — 조립기·서식·화면 규칙. 바뀌면 결과가 달라질 **수** 있으므로
                   임시 폴더에 다시 만들어 맞대어 봐야 확정됩니다.
  판단의 근거    — 규칙 문서·스키마. 바뀌어도 결과는 안 바뀌므로 기록에만 한 줄 남깁니다.

안 나누면 규칙 문서의 한 글자 수정이 문서 전부를 낡음 후보로 만들고,
그때부터 아무도 알림을 읽지 않습니다.

**결과가 같으면 알리지 않습니다.** 바뀐 것만 보고 띠를 띄우면 그 순간 알림이 죽습니다.

사용:
  python3 history/stamp.py --판정          # 무엇이 낡았는지 봅니다(고치지 않음)
  python3 history/stamp.py --판정 --갱신   # 본 뒤 지금 방식을 기록해 둡니다
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, BASE)
import version as V  # noqa: E402
# 기준 기록·등록부·산출물은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# 파급표·조립기·CSS 는 코드라 ROOT(코드뿌리) 그대로 연다.
자료뿌리 = V.자료뿌리  # noqa: E402  (version 이 이미 불러 둔 그 모듈 — 두 벌 들 이유가 없다)

try:
    파급 = json.load(open(os.path.join(ROOT, "ontology", "파급표.json"), encoding="utf-8"))
except FileNotFoundError:
    # 파급표.json 은 크라운주얼 — 정책만-로컬 배포본엔 없다. 모듈 최상위에서 죽으면
    # 6개 조립기의 기준도장()이 매번 import 예외를 삼킨다. 부재 시 빈 표로 두어 import 는
    # 늘 성공시키고, 배포본은 <meta name="기준"> 지문을 생략한다(파급표 미동봉의 설계상 결과).
    파급 = {}
장르목록 = [g for g in 파급 if not g.startswith("_") and g != "규칙파일"]

# (조립기 = 코드뿌리 기준 상대 경로, 등록부 이름 = 자료뿌리에서 찾을 것)
조립 = {"onepage-report": ("build/assemble.py", "samples"),
       "gongmun": ("build/assemble_gongmun.py", "gongmun"),
       "fullreport": ("build/assemble_full.py", "fullreport")}


def 등록부길(genre):
    return 자료뿌리.등록부(조립[genre][1])

# 산출 HTML 안에는 문서 전문과 편집기 프로파일이 통째로 심겨 있다. 그대로 해시하면
# 내용이 조금만 달라져도 '기준이 바뀌었다'가 되므로, 겉모습만 남기고 지운다.
지울것 = [re.compile(r'<script[^>]*id="fr-doc"[^>]*>.*?</script>', re.S),
        re.compile(r'<script[^>]*id="fr-profile"[^>]*>.*?</script>', re.S),
        re.compile(r'<meta name="기준"[^>]*>')]


def 겉모습(html):
    for r in 지울것:
        html = r.sub("", html)
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]


def 지문(paths):
    h = hashlib.sha256()
    for rel in sorted(paths):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            h.update(b"\0missing\0" + rel.encode())
            continue
        h.update(rel.encode() + b"\0")
        h.update(open(p, "rb").read())
    return h.hexdigest()[:8]


def 자리(genre, 갈래):
    return 파급[genre]["코드자리"][갈래]


def 조판지문(genre):
    """글자·화면을 합친 조판 지문 — 산출물에 찍는 도장."""
    return 지문(자리(genre, "글자") + 자리(genre, "화면"))


def 글자지문(genre):
    return 지문(자리(genre, "글자"))


def 화면지문(genre):
    return 지문(자리(genre, "화면"))


def 규칙지문():
    return 지문(파급["규칙파일"])


def 전체글롭():
    """목록 밖 파일이 바뀐 것을 침묵시키지 않는다 — 목록은 늘 뒤처진다."""
    out = []
    for pat in ("build/*.py", "build/*.css", "build/*.js", "ontology/*.json",
                "buildplan/*.py", "buildplan/*.css"):
        out += [os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, pat))]
    return sorted(out)


def 목록밖():
    """어느 목록에도 없는 파일 — 영향이 있는지 없는지 아무도 정한 적이 없다는 뜻이다."""
    안 = set()
    for g in 장르목록:
        안 |= set(자리(g, "글자")) | set(자리(g, "화면"))
    안 |= set(파급["규칙파일"])
    안 |= set((파급.get("_출력에_영향없음") or {}).get("파일") or [])
    return [p for p in 전체글롭() if p not in 안]


def 기준기록(**필드):
    p = 자료뿌리.기준기록길()
    import time
    필드 = {"때": time.strftime("%Y-%m-%dT%H:%M:%S"), **필드}
    자료뿌리.원자덧쓰기(p, json.dumps(필드, ensure_ascii=False))   # E-7


def 재조립(genre, out):
    script, _ = 조립[genre]
    r = subprocess.run([sys.executable, os.path.join(ROOT, script),
                        등록부길(genre), "--out", out],
                       capture_output=True, text=True, cwd=ROOT)
    return r.returncode == 0, (r.stderr or r.stdout)


def 판정(갱신=False):
    바뀜, 같음, 보존, 인쇄본낡음, 못함, 확인필요 = [], [], [], [], [], []
    규칙 = 규칙지문()
    밖 = 목록밖()
    if 밖:
        print(f"⚠ 영향을 정해 두지 않은 파일이 {len(밖)}건 있습니다 — "
              f"ontology/파급표.json 에 넣어 주세요")
        for p in 밖[:6]:
            print(f"    {p}")

    for genre in 장르목록:
        if genre not in 조립:
            continue
        조판, 글자, 화면 = 조판지문(genre), 글자지문(genre), 화면지문(genre)
        keys = [d["filename"] for d in
                json.load(open(등록부길(genre), encoding="utf-8"))]
        볼것 = []
        for k in keys:
            L = V.기록읽기(k)
            if L and L.get("_예시"):
                보존.append(k)
                continue
            찍힌 = (L or {}).get("기준", {})
            if 찍힌.get("조판") == 조판:
                continue                    # 기준이 그대로다 — 볼 것이 없다
            # 화면(CSS·JS)이 바뀌었으면 HTML 글자는 그대로라 대조로 확정할 수 없다.
            # '같음'으로 적으면 거짓말이 된다 — 확인이 필요하다고 그대로 말한다.
            if 찍힌.get("화면") and 찍힌["화면"] != 화면:
                확인필요.append(k)
                continue
            볼것.append(k)
        if not 볼것:
            continue

        tmp = tempfile.mkdtemp(prefix="stamp-")
        try:
            ok, msg = 재조립(genre, tmp)
            if not ok:
                못함.append((genre, msg.strip().splitlines()[-1] if msg else "문서를 만들지 못했습니다"))
                continue
            for k in 볼것:
                새 = os.path.join(tmp, k + ".html")
                옛 = 자료뿌리.산출물(k, "html")
                if not (os.path.exists(새) and os.path.exists(옛)):
                    못함.append((k, "만들어진 파일을 찾지 못했습니다"))
                    continue
                a = 겉모습(open(옛, encoding="utf-8").read())
                b = 겉모습(open(새, encoding="utf-8").read())
                (같음 if a == b else 바뀜).append(k)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # 인쇄본은 따로 본다 — 화면이 최신이어도 내려받으신 PDF는 옛것일 수 있다
    for genre in 장르목록:
        if genre not in 조립:
            continue
        for d in json.load(open(등록부길(genre), encoding="utf-8")):
            k = d["filename"]
            h = 자료뿌리.산출물(k, "html")
            pdf = 자료뿌리.산출물(k, "pdf")
            if os.path.exists(pdf) and os.path.exists(h) \
                    and os.path.getmtime(pdf) < os.path.getmtime(h):
                인쇄본낡음.append(k)

    print("\n■ 문서를 만드는 방식 확인")
    print(f"  다시 만들면 결과가 달라지는 문서 {len(바뀜)}건"
          + (" — " + ", ".join(바뀜[:8]) if 바뀜 else ""))
    print(f"  방식은 바뀌었지만 결과가 같은 문서 {len(같음)}건")
    if 확인필요:
        print(f"  직접 열어 보고 확인하실 문서 {len(확인필요)}건 — 글꼴·여백·색이 "
              f"바뀌어 글자만으로는 알 수 없습니다")
        print("    " + ", ".join(확인필요[:8]))
    print(f"  예전 방식 그대로 두는 비교용 예시 {len(보존)}건")
    print(f"  인쇄본을 다시 뽑아야 하는 문서 {len(인쇄본낡음)}건"
          + (" — " + ", ".join(인쇄본낡음[:8]) if 인쇄본낡음 else ""))
    for k, why in 못함:
        print(f"  ✗ {k}: {why}")

    if 갱신:
        for genre in 장르목록:
            if genre not in 조립:
                continue
            조판 = 조판지문(genre)
            화면 = 화면지문(genre)
            for d in json.load(open(등록부길(genre), encoding="utf-8")):
                k = d["filename"]
                L = V.기록읽기(k)
                if not L or L.get("_예시"):
                    continue
                이전 = L.get("기준", {}).get("조판")
                if k in 확인필요:
                    L["기준바뀜"] = {"이전": 이전, "지금": 조판,
                                 "말": "글꼴·여백·색이 바뀌었습니다 — 직접 열어 보고 확인해 주세요"}
                    V.기록쓰기(k, L)
                    V.기록(k, "만드는 방식", 누가="자동", 기준전=이전, 기준후=조판,
                         영향="확인 필요",
                         말="글꼴·여백·색이 바뀌어 글자만으로는 알 수 없습니다")
                    continue
                if k in 바뀜:
                    L["상태"] = "작성 중"
                    L["기준바뀜"] = {"이전": 이전, "지금": 조판,
                                 "말": "지금 다시 만들면 결과가 달라집니다"}
                else:
                    L.pop("기준바뀜", None)
                    L["기준"] = {"조판": 조판, "화면": 화면, "규칙": 규칙}
                V.기록쓰기(k, L)
                if 이전 and 이전 != 조판:
                    V.기록(k, "만드는 방식", 누가="자동", 기준전=이전, 기준후=조판,
                         영향="결과 달라짐" if k in 바뀜 else "없음",
                         말=("지금 다시 만들면 결과가 달라집니다" if k in 바뀜
                            else "방식이 바뀌었지만 이 문서 결과는 달라지지 않아 그대로 두었습니다"))
        기준기록(무엇="조판·규칙 지문 갱신", 규칙=규칙, 결과바뀜=바뀜, 결과같음=같음,
              확인필요=확인필요, 보존=보존, 인쇄본낡음=인쇄본낡음)
        print("\n  지금 방식을 기록해 두었습니다.")
    else:
        print("\n  확인만 했습니다 — 기록하려면 --갱신을 붙이세요")
    return {"바뀜": 바뀜, "같음": 같음, "확인필요": 확인필요,
            "보존": 보존, "인쇄본낡음": 인쇄본낡음}


def main():
    a = sys.argv[1:]
    if "--판정" not in a:
        print(__doc__)
        return 2
    판정("--갱신" in a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
