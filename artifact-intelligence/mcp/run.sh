#!/usr/bin/env bash
# MCP 서버 실행 래퍼 — 자가치유. .mcp.json 의 command 가 이걸 가리킨다.
# venv 가 없으면(신선 설치) 먼저 만들고 mcp 를 깐 뒤 서버를 exec 한다. SessionStart
# hook 과 무관하게, 서버가 먼저/독립적으로 뜨는 경로에서도 반드시 뜨게 한다.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${MUNSEO_PYTHON:-python3}"

if [ ! -x "$HERE/.venv/bin/python" ]; then
  # MCP 만 필요하므로 여기선 mcp venv 만 세운다(npm·hwpxenv 는 부트스트랩 hook 몫).
  "$PY" -m venv "$HERE/.venv" >&2 2>&1 || true
  "$HERE/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
    -r "$HERE/requirements.txt" >&2 2>&1 || true
fi

exec "$HERE/.venv/bin/python" "$HERE/server.py" "$@"
