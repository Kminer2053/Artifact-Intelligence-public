#!/bin/bash
# samples/*.html → PDF 인쇄 + 자동 게이트 수집
# 통과: pages==1, splits==0, sumLines<=2 (하드 게이트)
# 경고(소프트): audit.sparse==true (fillRatio<0.72, 하단 여백 과다) — 내용 보강 검토
DIR="$(cd "$(dirname "$0")" && pwd)"
# 산출물·관측·등록부는 **자료**라 자료뿌리를 탄다(WP-S2 ①) — 셸에 경로를 또 적으면
# 자료뿌리를 옮겼을 때 여기만 코드뿌리를 보고 "게이트 통과"라 말한다.
SAMPLES=$(python3 "$DIR/자료뿌리.py" 산출물) || exit 1
OBSERVED=$(python3 "$DIR/자료뿌리.py" 관측) || exit 1
# ONLY(문서 key) 검증 — 경로 탈출 차단('26-09-26 2차 진단, 항목 5). api.조판게이트 가
# 이미 정규식·등록부 실재를 확인하지만, 셸을 직접 부르는 경로(예: 옛 서버, 손 시험)에도
# 같은 막음을 겹으로 둔다 — '/'·'..' 가 들어오면 $SAMPLES 밖 파일을 겨눌 수 있다.
if [ -n "$ONLY" ]; then
  case "$ONLY" in
    */*|*..*)
      echo "✗ key 값이 올바르지 않습니다(경로 문자 포함): $ONLY" >&2
      exit 1
      ;;
  esac
  echo "$ONLY" | grep -Eq '^[a-z0-9][a-z0-9-]{1,60}$' || {
    echo "✗ key 값이 올바르지 않습니다: $ONLY" >&2
    exit 1
  }
fi
# 크롬 찾는 눈은 build/크롬찾기.py 하나뿐이다(WP-S8) — 여기서 절대경로를 다시 박으면
# 다섯 곳 중 이 한 곳만 컨테이너 배포에서 조용히 "크롬 없음"으로 갈라진다.
# 못 찾으면 크롬찾기.py 가 안내 문구와 함께 죽는다(build/.hwpxenv/bin/python 을 쓴다 — 규칙: hwpxenv 는 안 건드리되 실행에는 쓴다).
CHROME=$("$DIR/.hwpxenv/bin/python" "$DIR/크롬찾기.py") || exit 1
# 헤들리스 크롬이 사용자의 **실행 중 Chrome 과 겹치면**, 산출물을 다 쓰고도 종료하지
# 않는다(macOS 실측 2026-08-24: --headless·--headless=new 둘 다 PDF 를 2초에 쓰고 무한
# 대기). 컨테이너 배포(A1)엔 경쟁 Chrome 이 없어 스스로 끝나므로 영향 없다. 데스크톱
# (플러그인) 사용자를 위해 ① 격리 프로필로 시작 락을 피하고 ② **산출물이 완성되면(끝표시)
# 죽여 회수**한다(WP: 헤들리스-크롬-행 — "다 쓰고 행"은 %%EOF 확인 후 kill 로 회복).
CHROME_PROFILE=$(mktemp -d "${TMPDIR:-/tmp}/munseo-chrome.XXXXXX")
trap 'rm -rf "$CHROME_PROFILE"' EXIT
_CF="--headless --disable-gpu --virtual-time-budget=5000 --user-data-dir=$CHROME_PROFILE --no-first-run --no-default-browser-check"

_render_pdf() {   # _render_pdf OUT URL — PDF 를 쓰고 %%EOF 가 보이면 크롬을 죽인다
  local out="$1" url="$2" pid i
  rm -f "$out"
  "$CHROME" $_CF --no-pdf-header-footer --print-to-pdf="$out" "$url" >/dev/null 2>&1 &
  pid=$!
  for i in $(seq 1 40); do                       # 최대 20s
    kill -0 "$pid" 2>/dev/null || break          # 스스로 종료(A1: 경쟁 Chrome 없음)
    [ -s "$out" ] && tail -c 600 "$out" 2>/dev/null | grep -qa '%%EOF' && break
    sleep 0.5
  done
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
}

_dump_dom() {     # _dump_dom URL — DOM 을 stdout 으로 내고 </html> 보이면 죽인다
  local url="$1" tmp pid i
  tmp="$CHROME_PROFILE/dom.$$"
  "$CHROME" $_CF --dump-dom "$url" >"$tmp" 2>/dev/null &
  pid=$!
  for i in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || break
    grep -qa '</html>' "$tmp" 2>/dev/null && break
    sleep 0.5
  done
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  cat "$tmp"; rm -f "$tmp"
}
cd "$SAMPLES" || exit 1
# ONLY(선택, 문서 key) — 조판게이트 범위 좁히기('26-09-26 벤치마크 진단, 항목 5). 지금은
# 세션 산출물 폴더의 *.html 을 매번 다 인쇄·DOM 덤프해 문서 하나에 크롬 2회 × 폴더 안
# 문서 수가 들었다. ONLY 가 있으면 문체 게이트도 조판 게이트도 그 문서 하나만 본다 —
# 옆에 남은 다른(예전) 문서가 걸려도 이 문서의 판정에 안 섞인다. 없으면 지금처럼 전부.
echo "== 문체 게이트 (stylelint) =="
# 등록부를 세어서 전 장르를 건다 — samples-docs.json 만 걸던 판은 규정·보도자료를
# 검사한 적이 없으면서 게이트가 '통과'로 보였다(2026-08-04).
STYLE_EXIT=0
if [ -n "$ONLY" ]; then
  ONLYDOC="$CHROME_PROFILE/단건-$ONLY.json"
  REGLIST="$CHROME_PROFILE/등록부목록"
  python3 "$DIR/자료뿌리.py" 등록부길 > "$REGLIST" || exit 1
  ARGS=()
  while IFS= read -r J; do
    [ -n "$J" ] && ARGS+=("$J")
  done < "$REGLIST"
  python3 - "$ONLY" "$ONLYDOC" "${ARGS[@]}" <<'PYEOF'
import json, sys
ONLY, ONLYDOC = sys.argv[1], sys.argv[2]
for J in sys.argv[3:]:
    try:
        docs = json.load(open(J, encoding="utf-8"))
    except Exception:
        continue
    for d in docs:
        if d.get("filename") == ONLY:
            json.dump([d], open(ONLYDOC, "w", encoding="utf-8"), ensure_ascii=False)
            sys.exit(0)
sys.exit(1)
PYEOF
  if [ $? -eq 0 ]; then
    python3 "$DIR/stylelint.py" "$ONLYDOC" --csv || STYLE_EXIT=1
  else
    # 헛통과 방지(항목 9, '26-09-26 2차 진단 — 재현됨: 오타 키가 ok:true 로 끝났다).
    # ONLY 모드에서 등록부에 문서가 없으면 '건너뛰고 통과'가 아니라 **실패로 끝낸다** —
    # api.조판게이트 가 먼저 등록부 실재를 확인하지만, 이 셸을 직접 부르는 경로에도
    # 같은 막음을 겹으로 둔다.
    echo "✗ '$ONLY' 를 어느 등록부에서도 찾지 못했습니다" >&2
    exit 1
  fi
else
  # 공용 /tmp 에 예측 가능한 이름을 쓰지 않는다(mktemp, '26-10-01 release04 경로 감사).
  REGLIST=$(mktemp "${TMPDIR:-/tmp}/munseo-registry.XXXXXX")
  python3 "$DIR/자료뿌리.py" 등록부길 > "$REGLIST" || { rm -f "$REGLIST"; exit 1; }
  while IFS= read -r J; do
    [ -n "$J" ] || continue
    python3 "$DIR/stylelint.py" "$J" --csv || STYLE_EXIT=1
  done < "$REGLIST"
  rm -f "$REGLIST"
fi
echo "== 조판 게이트 =="
echo "file,pages,audit"
if [ -n "$ONLY" ]; then
  set -- "$ONLY.html"
  # 등록부엔 있는데 html 이 아직 없으면(조립 실패·미조립) — 헛통과 방지(항목 9):
  # 조용히 건너뛰어 "✓ 통과"로 끝나지 않고 실패로 끝낸다.
  [ -f "$SAMPLES/$ONLY.html" ] || { echo "✗ '$ONLY.html' 이 산출물 폴더에 없습니다" >&2; exit 1; }
else
  set -- *.html
fi
# GATE_PDF_DIR(선택) — 검사 PDF 를 인쇄할 자리. 플러그인(api.조판게이트)은 세션 방 workspace/_검사 를 넘겨 산출물
# 자리에 검사 못 넘은 판의 PDF 를 남기지 않는다(fixup4 '26-09-29). 없으면 예전대로 산출물 폴더(웹앱·verify_all).
PDFDIR="${GATE_PDF_DIR:-$SAMPLES}"
mkdir -p "$PDFDIR" || exit 1
export GATE_PDF_DIR="$PDFDIR"
for f in "$@"; do
  [ -f "$f" ] || continue
  base="${f%.html}"
  _render_pdf "$PDFDIR/$base.pdf" "file://$SAMPLES/$f"
  # 원본 지문을 PDF 메타에 심는다(hwpx zip 코멘트와 대칭) — verify_all 의 PDF 낡음 검사 근거.
  "$DIR/.hwpxenv/bin/python" "$DIR/pdf낡음.py" 찍기 "$PDFDIR/$base.pdf" "$SAMPLES/$f" 2>/dev/null
  pages=$(pdfinfo "$PDFDIR/$base.pdf" 2>/dev/null | awk '/^Pages/{print $2}')
  audit=$(_dump_dom "file://$SAMPLES/$f" | grep -o 'data-audit="[^"]*"' | sed 's/^data-audit="//; s/"$//; s/&quot;/"/g')
  echo "$f,$pages,\"$audit\""
  # 이 audit 을 **이 실행이 방금 잰 값 그대로** 아래 판정 단계로 넘긴다(e2e s4 재진단,
  # '26-09-27) — 예전엔 아래 판정이 build/observed/<이름>.json(별도 op `관측`이 써야
  # 생기는 파일)만 읽어서, 관측을 따로 부르지 않은 문서는 그 파일이 없어 audit={}로
  # 읽혔다. 그러면 **바로 위 줄에 splits:4 가 찍혀도** 판정은 그 사실을 아예 못 보고
  # "통과"만 말했다(재현됨 — 실측 splitWords 그대로: 구분한다./보고하여야/사용하여야/
  # 공유하여야). observed 파일이 더 최신·완전할 수도 있어(예: sparse 판정은 fillRatio
  # 계산이 이 스크립트엔 없다) 지우거나 대체하지 않고, **이 실행의 실측**을 옆에 남겨
  # 판정이 둘 중 있는 쪽(실측 우선)을 쓰게 한다.
  [ -n "$audit" ] && printf '%s' "$audit" > "$CHROME_PROFILE/audit-$base.json"
done

# ── 판정과 권고 ──
# 값만 뱉고 끝내면 사람이 CSV 를 읽어 스스로 알아내야 한다. 넘쳤을 때 **다음에
# 무엇을 할지**는 정본에 있다(R구-48: 압축을 먼저, 그래도 안 되면 풀버전을 권한다).
# 게이트가 그걸 말하지 않아 2026-08-05 넘침 시험에서 "막기는 하는데 안내가 없다" 로 걸렸다.
echo "== 판정 =="
# 넘침은 **종료코드에 싣는다**(WP-S6). 예전에는 ✗ 를 찍고도 STYLE_EXIT 만 내보내서,
# 1p 가 두 쪽이어도 `조판게이트` 작업이 '완료'(ok:true)로 끝났다 — 게이트가 짚기만
# 하고 서지는 않는 모양이다(구현계획.md §0 "게이트는 서야 게이트다"). 성김(sparse)은
# 경고라 그대로 둔다 — 경고를 종료코드에 실으면 오탐 한 건에 게이트가 꺼진다.
VERDICT_EXIT=0
python3 - "$SAMPLES" "$OBSERVED" "$ONLY" "$CHROME_PROFILE" <<'PYEOF' || VERDICT_EXIT=1
import glob, json, os, re, subprocess, sys
SAMPLES, OBSERVED = sys.argv[1], sys.argv[2]
ONLY = sys.argv[3] if len(sys.argv) > 3 else ""
LIVE = sys.argv[4] if len(sys.argv) > 4 else ""   # 이 실행이 위에서 방금 잰 audit(e2e s4 재진단)
넘침, 성김, 슬위반, 분리 = [], [], [], []
슬인상 = []   # 슬라이드 인상 지표(soft) — 막지 않는다
인쇄실패 = []  # ONLY 인데 PDF 가 없거나 못 읽음 — 잰 것이 없으니 실패(fixup4)
# ONLY 가 있으면 그 문서 하나만 판정한다 — 안 그러면 이 세션에 남은 다른 문서가
# 걸렸을 때 '문서 하나만 검사'한 호출도 그 무관한 실패를 같이 뒤집어쓴다.
파일들 = [os.path.join(SAMPLES, ONLY + ".html")] if ONLY else sorted(glob.glob(os.path.join(SAMPLES, "*.html")))
for f in 파일들:
    if not os.path.exists(f):
        continue
    이름 = os.path.basename(f)[:-5]
    if 이름.startswith("_"):
        continue
    pdf = os.path.join(os.environ.get("GATE_PDF_DIR") or SAMPLES, 이름 + ".pdf")
    if not os.path.exists(pdf):
        if ONLY:
            # 문서 하나를 재는데 인쇄가 안 됐으면 잰 것이 없다 — 통과로 적지 않는다(fixup4 '26-09-29: 예전엔 여기서 넘어가
            # 쪽수·넘침을 안 재고 PASS 로 끝났다[코드]. 부하가 높을 때(load 81) 검사 PDF 가 안 생긴 일을 한 번 봤다).
            인쇄실패.append((이름, "PDF 를 인쇄하지 못했습니다(크롬 시간 초과 등)"))
        continue
    try:
        쪽 = int(subprocess.run(["pdfinfo", pdf], capture_output=True, text=True)
                .stdout.split("Pages:")[1].split()[0])
    except Exception:
        if ONLY:
            인쇄실패.append((이름, "인쇄한 PDF 를 읽지 못했습니다"))
        continue
    # `data-audit` 은 **브라우저가 실행 뒤에 심는다** — HTML 파일에는 없다.
    # 파일에서 찾다가 아무것도 못 읽어 "통과" 라고 적을 뻔했다(2026-08-05).
    # 관측 기록(build/observed)이 그 값을 이미 갖고 있으니 거기서 읽는다 — 다만 관측은
    # **별도 op(observe)** 가 써야 생기는 파일이라, 새문서(검사=True)로 막 만든 문서는
    # 관측을 따로 부르지 않으면 이 파일이 없다(e2e s4 재진단, '26-09-27). 그러면 위
    # "== 조판 게이트 ==" 줄에 splits:4 가 정직하게 찍혀도 여기서는 a={} 로 읽혀 판정이
    # 그 사실을 통째로 놓쳤다(재현됨). LIVE(이 스크립트가 방금 잰 audit)가 있으면 그
    # 값으로 **덮어써** 이 실행의 실측을 우선한다 — 관측 파일을 지우거나 이 읽기 자체를
    # 없애지는 않는다(예전 흐름·다른 호출자와의 호환을 남긴다).
    관 = os.path.join(OBSERVED, 이름 + ".json")
    a = {}
    if os.path.exists(관):
        try:
            a = (json.load(open(관, encoding="utf-8")) or {}).get("audit") or {}
        except Exception:
            a = {}
    실측파일 = os.path.join(LIVE, "audit-" + 이름 + ".json") if LIVE else ""
    if 실측파일 and os.path.exists(실측파일):
        try:
            실측 = json.loads(open(실측파일, encoding="utf-8").read() or "{}")
            if isinstance(실측, dict):
                a = {**a, **실측}
        except Exception:
            pass
    장르 = a.get("장르")
    시 = None
    if 장르 is None:
        시 = open(f, encoding="utf-8").read()
        m = re.search(r'data-genre="([^"]*)"', 시)
        장르 = m.group(1) if m else None
    if 장르 == "onepage" and 쪽 > 1:
        넘침.append((이름, 쪽, a.get("fillRatio")))
    if 장르 == "slides":
        # 슬라이드 — ① PDF 쪽수 == 선언 장수(pdfinfo·HTML 세기, 브라우저 없이 성립)
        # ② 장별 넘침은 관측 기록의 audit.overflows 로(overflow:hidden 이라
        #    쪽수로는 넘침을 못 잡는다 — 스텁 실측 '26-08-13, 정본 게이트._hard_뜻)
        if 시 is None:
            시 = open(f, encoding="utf-8").read()
        선언 = 시.count('class="sl-page')
        if 선언 and 쪽 != 선언:
            슬위반.append((이름, f"쪽수 {쪽} ≠ 선언 장수 {선언}"))
        for o in (a.get("overflows") or []):
            슬위반.append((이름, f"{o.get('n')}번 장이 {o.get('over')}px 넘친다"))
        # v2 가로 넘침('26-09-28 적대 검토 M7 신설 — soft): 칸 그릇 밖으로 나간 화면 글
        for o in (a.get("h_overflows") or []):
            if isinstance(o, dict):
                슬인상.append((이름, f"{o.get('n')}번 장 글이 칸 밖으로 {o.get('곳')}곳 나간다({' · '.join(o.get('보기') or [])})"))
        # v2 그린 값 ≠ 적힌 값(렌더 상자, '26-09-29 round2 — 막대 트랙 폭·링 둥근 끝처럼 HTML 속성으론 안 보이는 어긋남).
        # 거짓 그림이라 위반으로 싣는다(bench11 v2 덱 8벌·본보기 3벌·합성 극단값 덱에서 고친 뒤 0건을 재고 올렸다).
        for o in (a.get("chart_mismatch") or []):
            if isinstance(o, dict):
                슬위반.append((이름, f"{o.get('n')}번 장 그림이 적힌 값과 다르다 {o.get('곳')}곳({' · '.join(o.get('보기') or [])})"))
        # 인상 지표('26-09-28 신설 — 전부 soft, 종료코드에 안 싣는다) — audit.js impression.
        # 판 채움(보고·배포 ≥0.6 · 발표 ≥0.45) · 크기 대비(최대/중앙 ≥2.0) · 캡션 12pt · 글자 대비 4.5:1.
        인 = a.get("impression") or {}
        if isinstance(인, dict) and 인.get("장"):
            문턱 = 0.45 if 인.get("밀도") == "발표" else 0.6
            낮채 = [f"{n}장 {r}" for n, r, _ in 인["장"] if isinstance(r, (int, float)) and r < 문턱]
            낮비 = [f"{n}장 {k}" for n, _, k in 인["장"] if isinstance(k, (int, float)) and k < 2.0]
            if 낮채:
                슬인상.append((이름, f"판 채움 {문턱} 미만 {len(낮채)}장({', '.join(낮채[:6])})"))
            # 빈 띠('26-09-29 신설 — 판 채움은 가장 깊이 내려온 곳만 봐서 가운데 띠에 몰린 카드를 0.97 로 읽었다):
            # 본문 구역에서 잉크(글 줄·svg·칠 조각) 없는 가장 긴 세로 띠 비율. 문턱은 실측('26-09-29 round2 — 같은
            # audit.js 로 bench11 당시 CSS·지금 CSS 를 나란히, 진한 칠은 잉크로): bench11 v2 덱 8벌 본문 59장 칸 늘림 전
            # 중앙 0.28·상위 10% 0.35, 늘림 뒤 중앙 0.20·상위 10% 0.35. 심사가 '위아래가 빔'으로 짚은 장(보고 m-s2 2·3·4·6·8,
            # m-s6 4·5·6, a-s2 2 / 발표 a-s5·m-s5 4)은 늘림 전 0.30~0.42 — 옛 문턱(0.35·0.40 초과)은 이 11장 가운데 3장만
            # 울렸고 0.30·0.35 이상은 전부 울린다. 기준선(무프롬프트 HTML) 4벌은 DOM 이 달라 화소로만 쟀다(중앙 0.18).
            # 오른쪽 패널만 성긴 꼴(가로로 빈 칸)은 이 지표가 못 본다.
            # '26-09-29 bench13 ① 문턱 다시 정함 — 무프롬프트 기준선 덱 4벌(심사 밀도 4.75) 본문 32장을 덱 종류와 무관한 같은
            # 자(내부 측정 스크립트 — 이 audit 과 같은 잉크 정의, 구역만 쪽 높이 20~90%)로 재어 상위 10% 0.271.
            # v2 덱 156장에서 두 자는 audit ≈ 0.021 + 0.921 × m3(r 0.97)라 audit 으로도 0.27. 보고·배포 0.27 이상 ·
            # 발표 0.35 이상(기준선의 발표 덱은 1벌 7장뿐이라 발표 문턱은 round2 값을 둔다)
            빈문턱 = 0.35 if 인.get("밀도") == "발표" else 0.27
            빈장 = [f"{n}장 {g}" for n, g in (인.get("빈띠") or []) if isinstance(g, (int, float)) and g >= 빈문턱]
            if 빈장:
                슬인상.append((이름, f"본문 빈 띠 {빈문턱} 이상 {len(빈장)}장({', '.join(빈장[:6])}) — 조립기가 글·부품을 키우고도 남았다: "
                              "자료에 있는 내용이 적으면 앞뒤 장과 합친다(없는 내용을 채우지 않는다)"))
            # 빈 상자 넓이(⑥ '26-09-29 bench13 — 심사 '카드는 큰데 속이 비었다'): 같은 자로 기준선 상위 10% 0.461 →
            # audit ≈ −0.001 + 0.905 × m3(r 0.995) → 0.42 이상
            빈상자 = [f"{n}장 {g}" for n, g in (인.get("빈상자") or []) if isinstance(g, (int, float)) and g >= 0.42]
            if 빈상자:
                슬인상.append((이름, f"속 빈 상자 넓이 0.42 이상 {len(빈상자)}장({', '.join(빈상자[:6])}) — 카드·패널 속이 비었다: "
                              "칸 수를 줄이거나 장을 합친다(자료에 있는 내용만)"))
            if 낮비:
                슬인상.append((이름, f"글자 크기 대비 2.0 미만 {len(낮비)}장({', '.join(낮비[:6])})"))
            if 인.get("small_text"):
                슬인상.append((이름, f"12pt 미만 글자 {인['small_text']}곳({' · '.join(인.get('small_samples') or [])})"))
            if 인.get("low_contrast"):
                슬인상.append((이름, f"글자 대비 4.5:1 미만 {인['low_contrast']}곳({' · '.join(인.get('low_samples') or [])})"))
    if a.get("sparse"):
        성김.append((이름, a.get("fillRatio")))
    # 어절 분리(splits) — audit 은 이미 정직하게 잔존 분리 건수·낱말을 기록하는데(e2e s4
    # 재진단, '26-09-27), 요약 문구가 넘침·슬위반·성김만 보고 통과 여부만 찍어 이 잔존
    # 분리가 요약에서 통째로 가려졌다. hard/soft 정책(막느냐 마느냐)은 그대로 두고 —
    # 압축 한도(jachigan.js) 안에서 못 줄인 것은 여전히 안 막는다 — **요약 문구에만** 드러낸다.
    if a.get("splits"):
        분리.append((이름, a.get("splits"), a.get("splitWords") or []))

if 넘침:
    print(f"✗ 1페이지 보고서가 한 장에 안 듭니다 — {len(넘침)}건")
    for 이름, 쪽, fr in 넘침:
        print(f"   · {이름}: {쪽}쪽 (채움 {fr})")
    print("   → **압축을 먼저** 하십시오(항목 줄이기·세부 병합). 정본 R구-48.")
    print("     압축해도 안 들면 그때 **풀버전을 권합니다** — 장르는 자동으로 안 바꿉니다.")
if 슬위반:
    print(f"✗ 슬라이드가 지면 계약을 어겼습니다 — {len(슬위반)}건")
    for 이름, 왜 in 슬위반:
        print(f"   · {이름}: {왜}")
    print("   → 넘친 장은 항목을 줄이거나 장을 나누십시오(장당 1메시지 — 정본 구성.중핵).")
if 성김:
    print(f"⚠ 내용이 성깁니다(경고) — {len(성김)}건")
    for 이름, fr in 성김:
        print(f"   · {이름}: 채움 {fr} (0.72 미만)")
    print("   → 자료를 더 받거나 절을 줄이는 편이 낫습니다. 막지는 않습니다.")
if 분리:
    print(f"⚠ 어절 분리가 남아 있습니다(경고, 안 막습니다) — {len(분리)}건")
    for 이름, n, words in 분리:
        낱말들 = "·".join(words[:6]) + (" …" if len(words) > 6 else "")
        print(f"   · {이름}: {n}건 ({낱말들})")
    print("   → 압축 한도 안에서 못 줄인 잔존 분리입니다 — 인쇄본에서 음절이 줄 끝에서 쪼개져 보일 수 있습니다.")
if 슬인상:
    print(f"⚠ 슬라이드 인상 지표(경고, 안 막습니다) — {len(슬인상)}건")
    for 이름, 왜 in 슬인상:
        print(f"   · {이름}: {왜}")
    print("   → 판이 비면 카드·부품을 늘리지 말고 부품을 바꾸거나 장을 합치십시오. 대비·12pt 는 조립기 서식 몫입니다.")
if 인쇄실패:
    print(f"✗ 인쇄하지 못해 조판을 재지 못했습니다 — {len(인쇄실패)}건")
    for 이름, 왜 in 인쇄실패:
        print(f"   · {이름}: {왜}")
    print("   → 조판게이트를 다시 부르십시오(잰 것이 없으면 통과로 적지 않습니다).")
if not 넘침 and not 슬위반 and not 성김 and not 인쇄실패:
    print("✓ 분량 판정 통과 — 넘친 문서도 성긴 문서도 없습니다"
          + (f" (어절 분리 {sum(n for _, n, _ in 분리)}건은 위 경고 참고)" if 분리 else ""))
넘침.extend(슬위반)   # 슬라이드 위반도 같은 종료코드에 싣는다(게이트는 서야 게이트다)
넘침.extend(인쇄실패)
sys.exit(1 if 넘침 else 0)
PYEOF

# 문체가 걸렸으면 그것대로, 넘쳤으면 그것대로 — 어느 쪽이든 0 이 아니게 끝낸다.
[ "$STYLE_EXIT" -ne 0 ] && exit "$STYLE_EXIT"
exit "$VERDICT_EXIT"
