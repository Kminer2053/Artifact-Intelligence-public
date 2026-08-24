#!/bin/bash
# samples/*.html → PDF 인쇄 + 자동 게이트 수집
# 통과: pages==1, splits==0, sumLines<=2 (하드 게이트)
# 경고(소프트): audit.sparse==true (fillRatio<0.72, 하단 여백 과다) — 내용 보강 검토
DIR="$(cd "$(dirname "$0")" && pwd)"
# 산출물·관측·등록부는 **자료**라 자료뿌리를 탄다(WP-S2 ①) — 셸에 경로를 또 적으면
# 자료뿌리를 옮겼을 때 여기만 코드뿌리를 보고 "게이트 통과"라 말한다.
SAMPLES=$(python3 "$DIR/자료뿌리.py" 산출물) || exit 1
OBSERVED=$(python3 "$DIR/자료뿌리.py" 관측) || exit 1
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
echo "== 문체 게이트 (stylelint) =="
# 등록부를 세어서 전 장르를 건다 — samples-docs.json 만 걸던 판은 규정·보도자료를
# 검사한 적이 없으면서 게이트가 '통과'로 보였다(2026-08-04).
STYLE_EXIT=0
python3 "$DIR/자료뿌리.py" 등록부길 > /tmp/.문서지능_등록부$$ || exit 1
while IFS= read -r J; do
  [ -n "$J" ] || continue
  python3 "$DIR/stylelint.py" "$J" --csv || STYLE_EXIT=1
done < /tmp/.문서지능_등록부$$
rm -f /tmp/.문서지능_등록부$$
echo "== 조판 게이트 =="
echo "file,pages,audit"
for f in *.html; do
  base="${f%.html}"
  _render_pdf "$base.pdf" "file://$SAMPLES/$f"
  # 원본 지문을 PDF 메타에 심는다(hwpx zip 코멘트와 대칭) — verify_all 의 PDF 낡음 검사 근거.
  "$DIR/.hwpxenv/bin/python" "$DIR/pdf낡음.py" 찍기 "$base.pdf" "$SAMPLES/$f" 2>/dev/null
  pages=$(pdfinfo "$base.pdf" 2>/dev/null | awk '/^Pages/{print $2}')
  audit=$(_dump_dom "file://$SAMPLES/$f" | grep -o 'data-audit="[^"]*"' | sed 's/^data-audit="//; s/"$//; s/&quot;/"/g')
  echo "$f,$pages,\"$audit\""
done

# ── 판정과 권고 ──
# 값만 뱉고 끝내면 사람이 CSV 를 읽어 스스로 알아내야 한다. 넘쳤을 때 **다음에
# 무엇을 할지**는 정본에 있다(R구-48: 압축을 먼저, 그래도 안 되면 풀버전을 권한다).
# 게이트가 그걸 말하지 않아 2026-08-05 A-5 14번에서 "막기는 하는데 안내가 없다" 로 걸렸다.
echo "== 판정 =="
# 넘침은 **종료코드에 싣는다**(WP-S6). 예전에는 ✗ 를 찍고도 STYLE_EXIT 만 내보내서,
# 1p 가 두 쪽이어도 `조판게이트` 작업이 '완료'(ok:true)로 끝났다 — 게이트가 짚기만
# 하고 서지는 않는 모양이다(구현계획.md §0 "게이트는 서야 게이트다"). 성김(sparse)은
# 경고라 그대로 둔다 — 경고를 종료코드에 실으면 오탐 한 건에 게이트가 꺼진다.
VERDICT_EXIT=0
python3 - "$SAMPLES" "$OBSERVED" <<'PYEOF' || VERDICT_EXIT=1
import glob, json, os, re, subprocess, sys
SAMPLES, OBSERVED = sys.argv[1], sys.argv[2]
넘침, 성김, 슬위반 = [], [], []
for f in sorted(glob.glob(os.path.join(SAMPLES, "*.html"))):
    이름 = os.path.basename(f)[:-5]
    if 이름.startswith("_"):
        continue
    pdf = os.path.join(SAMPLES, 이름 + ".pdf")
    if not os.path.exists(pdf):
        continue
    try:
        쪽 = int(subprocess.run(["pdfinfo", pdf], capture_output=True, text=True)
                .stdout.split("Pages:")[1].split()[0])
    except Exception:
        continue
    # `data-audit` 은 **브라우저가 실행 뒤에 심는다** — HTML 파일에는 없다.
    # 파일에서 찾다가 아무것도 못 읽어 "통과" 라고 적을 뻔했다(2026-08-05).
    # 관측 기록(build/observed)이 그 값을 이미 갖고 있으니 거기서 읽는다.
    관 = os.path.join(OBSERVED, 이름 + ".json")
    a = {}
    if os.path.exists(관):
        try:
            a = (json.load(open(관, encoding="utf-8")) or {}).get("audit") or {}
        except Exception:
            a = {}
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
    if a.get("sparse"):
        성김.append((이름, a.get("fillRatio")))

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
if not 넘침 and not 슬위반 and not 성김:
    print("✓ 분량 판정 통과 — 넘친 문서도 성긴 문서도 없습니다")
넘침.extend(슬위반)   # 슬라이드 위반도 같은 종료코드에 싣는다(게이트는 서야 게이트다)
sys.exit(1 if 넘침 else 0)
PYEOF

# 문체가 걸렸으면 그것대로, 넘쳤으면 그것대로 — 어느 쪽이든 0 이 아니게 끝낸다.
[ "$STYLE_EXIT" -ne 0 ] && exit "$STYLE_EXIT"
exit "$VERDICT_EXIT"
