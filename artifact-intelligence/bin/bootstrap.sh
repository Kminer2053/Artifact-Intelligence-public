#!/usr/bin/env bash
# 문서지능 플러그인 의존성 부트스트랩 — 멱등(idempotent).
# SessionStart hook(hooks/hooks.json)과 mcp/run.sh 가 이걸 부른다. 셋(mcp/.venv·
# build/.hwpxenv·node_modules)이 다 있고 mcp/requirements.txt 가 깐 때와 같으면(해시 기록) 즉시 no-op 이라 첫 세션 외엔
# 거의 0초(해시 한 번, 수십 ms). 설치가 실패했으면 같은 요구로는 하루에 한 번만 다시 해 본다.
# 첫 1회만: 파이썬 venv 2개 생성 + pip + npm install. 재생성물이라 git 에 없다.
#
# 설계: HTML 초안 생성 경로는 순수 stdlib 라 venv 없이도 돈다. 그래서 여기서 무엇이
# 실패해도(예: 오프라인) 본류는 살리고, 그 기능(MCP·HWPX·업로드파싱)만 죽게 둔다.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 0

PY="${MUNSEO_PYTHON:-python3}"
ver="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo none)"
if ! "$PY" -c 'import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,10) else 1)' 2>/dev/null; then
  echo "[문서지능] python3 3.10+ 가 필요합니다(현재: $ver). HTML 초안은 되지만 HWPX·MCP·업로드는 3.10+ 필요." >&2
  echo "           다른 파이썬으로: MUNSEO_PYTHON=/path/to/python3.11 $0" >&2
  exit 0
fi

# ① MCP 서버용 venv (mcp 패키지)
if [ ! -x mcp/.venv/bin/python ]; then
  echo "[문서지능] MCP 도구 의존성 설치 중(첫 1회)…" >&2
  if "$PY" -m venv mcp/.venv; then
    if mcp/.venv/bin/python -m pip install --quiet --disable-pip-version-check -r mcp/requirements.txt; then
      mcp/.venv/bin/python -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' \
        mcp/requirements.txt > mcp/.venv/.requirements.sha256 2>/dev/null || true
    else
      echo "[문서지능] ⚠ mcp 설치 실패 — MCP 도구만 영향(초안 생성은 정상)." >&2
    fi
  fi
fi
# ①-b requirements 가 바뀌면 있는 venv 에도 다시 깐다('26-10-01 주관 판정 R2, verify_fixup5_ux B1) — 깐 때의
#     mcp/requirements.txt 해시를 mcp/.venv/.requirements.sha256 에 적어 두고, 지금 해시와 다르면 다시 깐다. 전에는
#     venv 가 **없을 때만** 깔아, 뒤에 requirements 에 들어간 Pillow 가 이미 있는 venv(git pull 로 갱신한 클론 설치)에는
#     들어가지 않았다. 해시가 같아도 requirements 가 pillow 를 적었는데 import 가 안 되면 다시 깐다.
#     실패하면 그 해시를 표지에 적고, **같은 요구로는** 하루 동안 다시 돌지 않는다('26-09-30 fixup — 닿지 않는 색인에서
#     실패 한 번에 9초가 걸려 기동마다 늦어졌다, review_impl2 L4). 요구가 또 바뀌면 곧바로 다시 해 본다. 동시에 뜬
#     SessionStart·run.sh 가 겹쳐 깔지 않게 빗장 폴더를 둔다(10분 넘은 빗장은 죽은 것으로 본다).
#     못 깔아도 imageasset 이 그림 자르기·카드·짝 셈을 build/.hwpxenv 로 넘긴다.
REQ=mcp/requirements.txt
REQ_REC=mcp/.venv/.requirements.sha256
REQ_FAIL=mcp/.venv/.requirements-failed
REQ_LOCK=mcp/.venv/.requirements.lock
if [ -x mcp/.venv/bin/python ] && [ -f "$REQ" ]; then
  _want="$(mcp/.venv/bin/python -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$REQ" 2>/dev/null)"
  _have="$(cat "$REQ_REC" 2>/dev/null)"
  _need=""
  if [ -n "$_want" ] && [ "$_want" != "$_have" ]; then
    _need=1
  elif grep -qiE '^[[:space:]]*pillow' "$REQ" && ! mcp/.venv/bin/python -c 'import PIL' >/dev/null 2>&1; then
    _need=1
  fi
  if [ -n "$_need" ]; then
    if [ -f "$REQ_FAIL" ] && [ "$(cat "$REQ_FAIL" 2>/dev/null)" = "$_want" ] \
       && [ -n "$(find "$REQ_FAIL" -mmin -1440 2>/dev/null)" ]; then
      :   # 같은 요구로 하루 안에 실패했다 — 기동을 늦추지 않는다
    else
      if [ -d "$REQ_LOCK" ] && [ -n "$(find "$REQ_LOCK" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then
        rmdir "$REQ_LOCK" 2>/dev/null
      fi
      if mkdir "$REQ_LOCK" 2>/dev/null; then
        if mcp/.venv/bin/python -m pip install --quiet --disable-pip-version-check -r "$REQ" >/dev/null 2>&1; then
          printf '%s\n' "$_want" > "$REQ_REC"
          rm -f "$REQ_FAIL" mcp/.venv/.pillow-install-failed
        else
          printf '%s\n' "$_want" > "$REQ_FAIL"
          echo "[문서지능] ⚠ MCP 도구 의존성(mcp/requirements.txt)을 설치하지 못했습니다. 첨부 그림은 HWPX 내보내기용 파이썬으로 자르고, 하루 뒤(또는 요구가 바뀌면) 다시 설치해 봅니다." >&2
        fi
        rmdir "$REQ_LOCK" 2>/dev/null
      fi
    fi
  elif [ -f "$REQ_FAIL" ]; then
    rm -f "$REQ_FAIL"   # 요구가 깐 것과 같아졌다 — 옛 실패 표지는 뜻이 없다
  fi
fi

# ②③ 은 **전부-A1(얇은 스킬)** 에선 건너뛴다 — HWPX 변환·업로드 파싱을 서버가 하므로 로컬에
# python-hwpx·크롬·Node 를 깔 필요가 없다(설치가 가볍고 빠르다). 서버.conf 가 그 표식이다.
if [ ! -f 서버.conf ]; then
  # ② HWPX 내보내기용 venv (python-hwpx 등 7종) — 자기완결(로컬 온톨로지) 배포에서만
  if [ ! -x build/.hwpxenv/bin/python ]; then
    echo "[문서지능] 한글(HWPX) 내보내기 의존성 설치 중(첫 1회)…" >&2
    if "$PY" -m venv build/.hwpxenv; then
      build/.hwpxenv/bin/python -m pip install --quiet --disable-pip-version-check -r build/requirements.txt \
        || echo "[문서지능] ⚠ hwpxenv 설치 실패 — HWPX 내보내기만 영향(HTML·PDF는 정상)." >&2
    fi
  fi

  # ③ 업로드 파서(kordoc, node_modules) — HWP/HWPX/PDF/XLSX/DOCX/OCR 파싱
  if [ ! -e node_modules/.bin/kordoc ]; then
    if command -v npm >/dev/null 2>&1; then
      echo "[문서지능] 파일 업로드 파서(kordoc) 설치 중(첫 1회)…" >&2
      # ONNXRUNTIME_NODE_INSTALL=skip (kordoc #99) — CUDA 바이너리 받기가 막혀 실패하면 npm 이 sharp 까지 뺀다
      ONNXRUNTIME_NODE_INSTALL="${ONNXRUNTIME_NODE_INSTALL:-skip}" npm install --no-audit --no-fund --silent >/dev/null 2>&1 \
        || echo "[문서지능] ⚠ npm install 실패 — 파일 업로드 파싱만 영향." >&2
    else
      echo "[문서지능] ⚠ npm 이 없어 업로드 파서를 건너뜀 — 파일 업로드 파싱만 영향." >&2
    fi
  fi
fi

# ④ 정책 토큰 자동 등록(WP-S6) — 설치본이 자기 토큰을 한 번 받아 온다(즉시 활성).
#    이미 있으면(env 문서지능_정책토큰 또는 conf 의 주석 아닌 줄) 건너뛴다(멱등). 정책서버가
#    없으면(개발/전체 트리) 조용히 넘긴다. ('26-10-01 부터 작성 규칙은 설치본의 ontology/ 에 함께
#    실려 토큰 없이도 문서 작업이 돈다. 토큰은 정책서버를 쓰는 예비 길 — 키 없는 'AI로 고치기'(서버
#    모델)와 온톨로지 파일이 빠진 옛 설치의 조각 조회 — 에만 실린다. 이 단계를 남길지는 따로 정한다.)
#    urllib 은 Cloudflare 봇차단에 막히니 curl + 제품
#    UA 로 부른다. 실패해도(오프라인 등) 본류는 산다 — 다음 기동에 다시 시도한다.
# 선로 위의 이름은 ASCII — bash 는 한글 변수·함수명을 못 쓰고, 한글 env 는 $-치환이
# 안 돼 printenv(인자)로 읽는다(구현계획.md 규칙 8 의 셸판). 파일명(정책서버*.conf)은
# 문자열이라 한글 그대로 둔다.
_has_token() {
  [ -n "$(printenv '문서지능_정책토큰' 2>/dev/null)" ] && return 0
  [ -f 정책서버토큰.conf ] && grep -qvE '^[[:space:]]*(#|$)' 정책서버토큰.conf 2>/dev/null && return 0
  return 1
}
if command -v curl >/dev/null 2>&1 && ! _has_token; then
  server="$(printenv '문서지능_정책서버' 2>/dev/null)"
  [ -z "$server" ] && [ -f 정책서버.conf ] && server="$(grep -vE '^[[:space:]]*(#|$)' 정책서버.conf 2>/dev/null | head -1)"
  if [ -n "$server" ]; then
    label="$( { hostname 2>/dev/null; uname -s 2>/dev/null; } | tr -d '\n' | tr -cs 'A-Za-z0-9._-' '_' | cut -c1-60 )"
    resp="$(curl -fsS -m 20 -A 'artifact-intelligence-policy/0.1' -H 'Content-Type: application/json' \
              -X POST "${server%/}/api/enroll" --data "{\"라벨\":\"${label:-plugin}\"}" 2>/dev/null)" || resp=""
    token="$(printf '%s' "$resp" | "$PY" -c 'import sys, json
try:
    print(json.load(sys.stdin).get("값", {}).get("토큰", ""))
except Exception:
    pass' 2>/dev/null)"
    if [ -n "$token" ]; then
      printf '# 설치 시 자동 발급된 정책 토큰 (WP-S6) — 지우면 다음 기동에 다시 받습니다.\n%s\n' "$token" > 정책서버토큰.conf
      chmod 600 정책서버토큰.conf 2>/dev/null || true
      echo "[문서지능] 정책 토큰 자동 등록 완료." >&2
    fi
  fi
fi

# ⑤ 버전 안내 — 설치본이 최신인지 공개 마켓 버전과 대조해, 뒤처지면 한 줄로 알린다(강제 아님).
#    **같은 버전 재릴리스는 캐시가 안 바뀌므로 버전만이 갱신 신호다** — 사용자가 구버전에
#    묶여 고친 버그를 못 받는 일을 막는다. 네트워크 실패·오프라인이면 조용히 넘긴다(본류 무영향).
if command -v curl >/dev/null 2>&1; then
  _local="$("$PY" -c 'import json;print(json.load(open(".claude-plugin/plugin.json"))["version"])' 2>/dev/null || echo "")"
  _remote="$(curl -fsS -m 8 -A 'artifact-intelligence-policy/0.1' \
      https://raw.githubusercontent.com/Kminer2053/Artifact-Intelligence-public/main/.claude-plugin/marketplace.json 2>/dev/null \
      | "$PY" -c 'import json,sys
try:
    print(json.load(sys.stdin)["plugins"][0]["version"])
except Exception:
    pass' 2>/dev/null || echo "")"
  if [ -n "$_local" ] && [ -n "$_remote" ] && [ "$_local" != "$_remote" ] \
     && "$PY" -c "import sys
def t(v):
    return tuple(int(x) for x in v.split('.'))
try:
    sys.exit(0 if t('$_remote') > t('$_local') else 1)
except Exception:
    sys.exit(1)" 2>/dev/null; then
    # ⑥ 자동 갱신(사장님 Q2) — git 클론 설치(Cursor·Codex)면 스스로 최신으로 당긴다(다음 서버
    #    기동부터 적용). **안전 가드**: git 작업트리가 아니거나(마켓 캐시=Claude Code 는 여기서
    #    걸려 안내로 빠진다), 로컬 변경이 있거나, fast-forward 가 안 되면 강제하지 않는다 —
    #    force·reset·merge 를 절대 안 해 사용자의 로컬 수정을 지우지 않는다. 끄려면 문서지능_자동갱신=0.
    _updated=""   # bash 변수명은 ASCII 만(한글 이름은 'command not found' 로 새어 조용히 오작동)
    if [ "$(printenv '문서지능_자동갱신' 2>/dev/null || echo 1)" != "0" ] \
       && command -v git >/dev/null 2>&1 \
       && git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
       && git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
      if git pull --ff-only --quiet 2>/dev/null; then
        _updated=1
        echo "[문서지능] 자동 갱신 완료 — 다음 세션부터 최신($_remote)이 적용됩니다(이 세션은 $_local)." >&2
      fi
    fi
    if [ -z "$_updated" ]; then
      echo "[문서지능] 새 버전 $_remote 이 있습니다(설치본 $_local). 갱신을 권합니다 — 고친 버그가 담깁니다:" >&2
      echo "           · Claude Code: /plugin marketplace update artifact-intelligence  →  /plugin install artifact-intelligence@artifact-intelligence" >&2
      echo "           · Codex: codex plugin marketplace update  ·  Cursor: 클론 폴더에서 git pull(자동 갱신이 못 미친 경우)" >&2
    fi
  fi
fi

echo "[문서지능] 준비 완료." >&2
