#!/usr/bin/env python3
"""MCP 인자 별칭 가드 — 모든 작업(@등록)의 한글 인자 키가 workspace/api.py `인자영문` 에
영문(ASCII) 별칭을 갖는지 전수 검사한다.

왜 — MCP 도구 서명은 영문 인자만 쓸 수 있다(Anthropic API 규칙). mcp/server.py 는
등록부의 인자를 `인자영문` 으로 번역하는데, 한글 키가 매핑에 없으면 **서버 기동이 통째로
SystemExit** 로 죽는다(2026-08-17 실측: 클라환경의 `글꼴보유` 누락 → MCP 42도구 전부 불능).
그 실패는 MCP 를 띄워야만 드러나므로, 여기서 소스만 훑어 배포·설치 전에 잡는다.

    python3 build/mcp별칭가드.py        # 누락 있으면 종료코드 1

소스 정적 스캔이라 api.py 의 무거운 의존(자료뿌리 등)을 import 하지 않는다."""
import os
import re
import sys

_특수 = {"key", "어긋남답"}          # server.py 가 특별 취급(ASCII·관문 주입)


def _ascii(s):
    return all(ord(c) < 128 for c in s)


def 검사(api_경로):
    src = open(api_경로, encoding="utf-8").read()
    m = re.search(r"인자영문 = \{(.*?)\n\}", src, re.S)
    if not m:
        return ["인자영문 매핑을 못 찾았습니다"]
    별칭 = dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', m.group(1)))
    나쁨 = []
    for mt in re.finditer(r'@등록\(\s*"([^"]+)"\s*,\s*\[([^\]]*)\]', src):
        도구, 인자들 = mt.group(1), re.findall(r'"([^"]+)"', mt.group(2))
        for a in 인자들:
            if a in _특수 or _ascii(a):
                continue
            영문 = 별칭.get(a)
            if 영문 is None:
                나쁨.append(f"  ✗ {도구}: 인자 '{a}' 의 영문 별칭이 인자영문 에 없다")
            elif not _ascii(영문):
                나쁨.append(f"  ✗ {도구}: 인자 '{a}' 의 별칭 '{영문}' 이 ASCII 가 아니다")
    return 나쁨


def main(경로들):
    뿌리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    api = 경로들[0] if 경로들 else os.path.join(뿌리, "workspace", "api.py")
    나쁨 = 검사(api)
    if 나쁨:
        print("\n".join(나쁨))
        print(f"[MCP별칭가드] {len(나쁨)}건 — 한글 인자에 영문 별칭이 없어 MCP 서버가 기동에 실패한다. "
              "workspace/api.py 의 인자영문 에 추가하라.")
        return 1
    print("[MCP별칭가드] 모든 작업 인자에 ASCII 별칭 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
