#!/usr/bin/env bash
# MCP 서버 실행 래퍼 — 자가치유. .mcp.json 의 command 가 이걸 가리킨다.
# venv 가 없으면(신선 설치) 먼저 만들고 mcp 를 깐 뒤 서버를 exec 한다. SessionStart
# hook 과 무관하게, 서버가 먼저/독립적으로 뜨는 경로에서도 반드시 뜨게 한다.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${MUNSEO_PYTHON:-python3}"

if [ ! -x "$HERE/.venv/bin/python" ]; then
  # 서버를 exec 하려면 mcp venv 가 지금 있어야 하므로 이 한 가지는 여기서 동기로 세운다.
  "$PY" -m venv "$HERE/.venv" >&2 2>&1 || true
  "$HERE/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
    -r "$HERE/requirements.txt" >&2 2>&1 || true
fi

# 전 클라이언트 공통 자동 부트스트랩 — MCP 서버는 Claude Code·Codex·Cursor 어디서든 이
# run.sh 로 뜬다. SessionStart hook 이 없는 클라이언트(Codex·Cursor)에서도 HWPX·kordoc·
# 정책토큰·버전확인이 준비되도록 전체 bootstrap 을 **비블로킹**으로 돌린다(멱등 — 이미 되면
# 즉시 끝나 서버 기동을 잡지 않는다). hook 이 있는 Claude Code 에선 중복이나 멱등이라 무해.
if [ -x "$HERE/../bin/bootstrap.sh" ]; then
  MUNSEO_PYTHON="$PY" "$HERE/../bin/bootstrap.sh" >&2 2>&1 &
fi

exec "$HERE/.venv/bin/python" "$HERE/server.py" "$@"
