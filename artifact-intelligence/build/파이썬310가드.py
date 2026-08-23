#!/usr/bin/env python3
"""Python 3.10 호환 가드 — 배포 서버가 3.10(Ubuntu 22.04 LTS)이라, 3.12+ 전용 문법이
소스에 섞이면 서버에서 SyntaxError 로 터진다. 개발기가 3.12+ 면 로컬 py_compile 은
통과해 못 잡는다('26-08-17 실측: assemble_full.py f-string 백슬래시가 서버 3.10 에서만 터짐).

이 스캐너는 그 대표 함정 — **f-string 표현식({...}) 안의 백슬래시**(3.10/3.11 금지, 3.12+ 허용) —
를 AST 로 실측 검출한다(파싱은 버전 무관이라 3.14 에서도 잡힌다). 더 완전한 검사는
python3.10 으로 전 .py 를 py_compile 하는 것이고, 배포 게이트가 그렇게 한다.

    python3 build/파이썬310가드.py [경로...]   # 기본: 스킬 뿌리 전체. 위반 있으면 종료코드 1.
"""
import ast, os, sys

_제외 = (".venv", ".hwpxenv", "__pycache__", "node_modules", ".git", ".claude")


def 위반들(소스, 파일):
    out = []
    try:
        나무 = ast.parse(소스, 파일)
    except SyntaxError:
        return out  # 이미 못 파싱하면 py_compile 이 잡는다 — 여긴 유효소스의 버전함정만
    for 노드 in ast.walk(나무):
        if not isinstance(노드, ast.JoinedStr):
            continue
        for 조각 in 노드.values:
            if isinstance(조각, ast.FormattedValue):
                seg = ast.get_source_segment(소스, 조각.value)
                if seg and "\\" in seg:
                    out.append((조각.value.lineno, seg[:60]))
    return out


def main(경로들):
    뿌리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    대상 = 경로들 or [뿌리]
    파일들 = []
    for p in 대상:
        if os.path.isdir(p):
            for r, _, fs in os.walk(p):
                if any(x in r.split(os.sep) for x in _제외):
                    continue
                파일들 += [os.path.join(r, f) for f in fs if f.endswith(".py")]
        elif p.endswith(".py"):
            파일들.append(p)
    총 = 0
    for f in 파일들:
        try:
            소스 = open(f, encoding="utf-8").read()
        except Exception:
            continue
        for 줄, 조각 in 위반들(소스, f):
            총 += 1
            print(f"  ✗ {os.path.relpath(f, 뿌리)}:{줄}  f-string 표현식 백슬래시: {조각}")
    if 총:
        print(f"[파이썬310가드] 비호환 {총}건 — 3.12+ 전용 문법. 배포 서버(3.10)에서 SyntaxError.")
        return 1
    print(f"[파이썬310가드] 3.10 호환 OK — {len(파일들)}파일, f-string 백슬래시 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
