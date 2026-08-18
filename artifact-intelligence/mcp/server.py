#!/usr/bin/env python3
"""문서지능 MCP 서버 — 1p 보고서 파이프라인의 도구 계층.

로드맵(스킬 → 지식 라이브러리 → MCP → 플랫폼)의 3단계 실체. 개방 전략 원칙:
도구 인터페이스는 열고, 지식(온톨로지·원장)은 서버 뒤에 둔다 — 클라이언트는
조회 도구로 필요한 만큼만 지식을 받아 쓴다.

실행: .venv/bin/python mcp/server.py  (stdio)
등록: claude mcp add artifact-intelligence -- <이 venv python 절대경로> <이 파일 절대경로>

도구는 **workspace/api.py 의 작업 목록에서 생성**한다 — 목록이 한 곳이라 스킬·MCP·웹앱이
어긋나지 않는다. 각 작업은 검증된 CLI 를 감싸므로 로직 중복도 게이트 계약 차이도 없다.

전송:
  python mcp/server.py                 stdio     — 각자 자기 컴퓨터(로컬 스킬과 함께)
  python mcp/server.py --http [포트]    HTTP      — 한 곳에 올려 여럿이 붙는다(공유 MCP)
"""
import json
import re
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent.parent  # skill/artifact-intelligence

mcp = FastMCP(
    "artifact-intelligence",
    instructions=(
        "대한민국 공공기관 1페이지 보고서 생성 파이프라인(문서지능)의 도구 모음. "
        "지식 정본은 온톨로지(개체×3요소, 12유형 목차로직)이며 ontology_query/report_types로 조회한다. "
        "생성 흐름: 유형 판별·빌드플랜(사용자 승인) → 3층 인스턴스 JSON 작성 → style_lint → "
        "assemble_docs → render_gate(1쪽·어절분리·문체 하드 게이트). "
        "사용자 리터칭은 backtrace_scan/adopt로 정본과 동기화하고, 규칙 차원 피드백은 동의 카드를 거쳐 consentcorpus 로 남긴다 — 이때 변경(델타)과 함께 문서 기본 스펙(장르·유형·길이)을 실어야 규칙 보완의 목표물이 잡힌다."
    ),
)


# ── 도구는 **작업 목록에서 생성한다** ──────────────────────────────────
# 예전에는 도구 15개를 손으로 적고 각자 CLI 를 subprocess 로 불렀다. 그러면 문이
# 셋(스킬·MCP·웹앱)이 될 때 목록이 셋으로 갈라진다 — 하나 늘릴 때 나머지에 빠뜨린다.
# 이제 workspace/api.py 한 곳에 적고 여기서는 그것을 MCP 도구로 감싸기만 한다.
sys.path.insert(0, str(ROOT / "workspace"))
import api  # noqa: E402

import contextvars  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402

자료뿌리 = api.자료뿌리   # api 가 이미 불러 둔 그 모듈(두 벌 금지 — serve.py 와 같은 규칙)

# ── HTTP(원격) 모드의 인증 + 세션 격리 (WP-S6 · deploy-architecture #1) ─────────
# stdio(로컬)에서는 이 층이 통째로 잠잠하다 — 한 사람이 자기 컴퓨터에서 쓰니 인증도 격리도
# 필요 없다(기본 뿌리, 지금과 한 바이트도 안 다르다). HTTP 로 여럿이 붙을 때만: (1) 발급
# 토큰을 검증하고(api.정책토큰검증) (2) **토큰마다 격리된 자료뿌리 세션**을 준다. 토큰 없이/
# 틀리면 못 붙는다(fail closed). 격리를 토큰 지문에 매는 까닭 — 인증이 이미 토큰을 요구하니
# 그 신분(지문)을 그대로 칸막이로 쓰면 어긋남이 없다. 설치 하나 = 토큰 하나 = 자료뿌리 하나.
# (이게 없으면 붙는 전원이 기본 뿌리를 공유해 서로 문서를 열람·덮어쓴다 — 절대 금지.)
_현재열쇠 = contextvars.ContextVar("자료뿌리열쇠", default="")
_세션맵 = {}                    # 토큰지문 → 자료뿌리 열쇠
_세션맵락 = threading.Lock()


def _격리열쇠(지문):
    """이 토큰(지문)에 붙은 자료뿌리 열쇠. 없으면 새로 하나 만들어 맨다(설치 하나 = 뿌리 하나)."""
    if not 지문:
        return ""
    with _세션맵락:
        k = _세션맵.get(지문)
        if not k:
            k = 자료뿌리.새열쇠()
            _세션맵[지문] = k
        return k


def _부르기(이름, 인자):
    """api.부르기 를 현재 요청의 격리 세션 안에서 실행한다. 열쇠가 없으면(stdio) 기본
    뿌리에서 — 지금과 같다. FastMCP 는 동기 도구를 스레드풀에서 돌리는데, anyio 가
    contextvars 를 복사하므로 미들웨어가 심은 _현재열쇠 가 그 스레드에도 산다."""
    열쇠 = _현재열쇠.get()
    if 열쇠:
        with 자료뿌리.세션갈기(열쇠):
            return api.부르기(이름, 인자)
    return api.부르기(이름, 인자)


# 인자 모양은 **작업 목록에서 가져온다**(api.인자모양). 여기에 손으로 적으면
# 목록이 둘로 갈린다 — 실제로 그래서 `doc` 이 글로 선언돼 문서를 못 넣었다
# (2026-08-05 A-4 11번). 목록이 한 곳이면 모양도 한 곳이다.
_형이름 = {dict: "dict", list: "list", bool: "bool", int: "int", str: "str"}


def _펴기(r):
    """작업 결과를 사람이 읽을 글로 편다. MCP 도구는 글을 돌려준다."""
    if not isinstance(r, dict):
        return json.dumps(r, ensure_ascii=False, indent=1)[:20000]
    # `물음` — 되묻기 관문의 막힘 응답(WP-S3)에는 값이 없고 물음·필요한것이 있다.
    # `[✗]+로그` 로만 펴면 물음의 구조(id·값들)가 MCP 문에서만 떨어져 나가 세 문이
    # 같지 않게 된다 — 클라이언트가 id 를 몰라 어긋남답을 못 만든다.
    if "값" in r or "키" in r or "물음" in r:
        본 = {k: v for k, v in r.items() if k != "함수"}
        return json.dumps(본, ensure_ascii=False, indent=1)[:20000]
    표 = "✓" if r.get("ok") else "✗"
    return f"[{표}]\n{(r.get('로그') or '').strip()}"[:20000]


def _도구만들기(작):
    """작업 하나를 MCP 도구로 감싼다. 인자 이름·타입을 실제 서명으로 만들어야
    클라이언트가 무엇을 넣을지 안다 — **kwargs 로 받으면 아무것도 안 보인다.

    서명의 인자 이름은 **영문 별칭**(api.인자영문)이다 — Anthropic API 가 도구
    인자 키를 `^[a-zA-Z0-9_.-]{1,64}$` 로 강제해서, 한글 키가 하나라도 실리면
    그 세션의 모든 요청이 400 으로 죽는다. api.부르기 에는 한글 이름으로 되돌려
    넘기므로 내부 계약은 그대로다."""
    이름 = 작.get("en") or 작["이름"]
    받는것 = 작["받는것"]
    모양 = 작.get("모양") or {}
    영문 = {k: api.인자영문.get(k, k) for k in 받는것}
    for k, e in 영문.items():
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}", e):
            raise SystemExit(f"도구 {이름} 의 인자 '{k}' 에 쓸 수 있는 영문 별칭이 "
                             f"없습니다('{e}') — workspace/api.py 인자영문 에 추가하세요")
    if len(set(영문.values())) != len(영문):
        raise SystemExit(f"도구 {이름} 의 영문 인자 이름이 겹칩니다: {영문}")
    파라 = ", ".join(
        f"{영문[k]}: {_형이름.get(모양.get(k, str), 'str')} = "
        f"{chr(39)*2 if 모양.get(k, str) is str else 'None'}"
        for k in 받는것)
    넘김 = ", ".join(f"{k!r}: {영문[k]}" for k in 받는것)
    설명 = 작["설명"] + (f"  (한국어 이름: {작['이름']})" if 작.get("en") else "")
    번역 = [f"{e}={k}" for k, e in 영문.items() if e != k]
    if 번역:
        설명 += f"  [인자 대응: {', '.join(번역)}]"
    소스 = (f"def {이름}({파라}) -> str:\n"
           f"    인자 = {{{넘김}}}\n"
           f"    인자 = {{k: v for k, v in 인자.items() if v not in ('', None)}}\n"
           f"    return _펴기(api.부르기({작['이름']!r}, 인자))\n")
    ns = {"api": api, "_펴기": _펴기}
    exec(소스, ns)
    fn = ns[이름]
    fn.__doc__ = 설명
    mcp.add_tool(fn, name=이름, description=설명)
    return 이름


_만든것 = [_도구만들기(w) for w in api.목록()]


if __name__ == "__main__":
    if "--http" in sys.argv:
        i = sys.argv.index("--http")
        if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit():
            mcp.settings.port = int(sys.argv[i + 1])
        # CLI 가 포트만 파싱하고 host 는 못 정했다(X2 F-4) — 컨테이너에서 바인드
        # 주소를 이 스크립트로 못 정하고 라이브러리 기본값(127.0.0.1)에 종속됐다.
        # --host 를 추가한다. 기본값은 그대로 둔다 — 인증이 없는 채로 0.0.0.0 을
        # 기본으로 열면 안 된다는 원칙은 workspace/serve.py 의 --host 와 같다.
        if "--host" in sys.argv:
            j = sys.argv.index("--host")
            if len(sys.argv) > j + 1:
                mcp.settings.host = sys.argv[j + 1]
        print(f"공유 MCP — streamable-http {mcp.settings.host}:{mcp.settings.port} "
              f"· 도구 {len(_만든것)}개", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
