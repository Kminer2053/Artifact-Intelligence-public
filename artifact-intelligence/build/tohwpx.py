#!/usr/bin/env python3
"""완성된 **HTML 을 그대로** HWPX 로 옮긴다.

    python3 build/tohwpx.py build/samples/<키>.html [나갈.hwpx]

길은 한 줄이다 — 자료 → 화면(HTML) → HWPX. 화면을 **베끼는** 것이지 다시 만드는 게 아니다.

되돌린 것들(같은 자리를 다시 밟지 않으려고 남긴다)
  ① `kordoc generate` 로 갔다 — 되돌렸다. 마크다운+프리셋으로 문서를 **다시 만든다.**
     우리 ○ 항목이 □ 로 나왔다. 사장님: "kordoc을 그대로 쓰면 안되지 않아?"
  ② XML 을 손으로 짰다 — 되돌렸다. `itemCnt` 를 안 고쳐 문단모양·글머리가 통째로
     무시됐고, 골격의 borderFill 을 빌려 써서 표가 파랗게 나왔다.
  ③ python-hwpx 위에 짜되 **인스턴스 JSON 을 읽었다** — 되돌렸다. 이게 제일 오래 갔다.
     길이 두 갈래로 갈려(자료→화면 / 자료→HWPX) 화면과 다른 문서가 나왔다.
     2026-08-05 실측: 풀버전 HWPX 에 남은 글이 **제목 한 줄**. 규정은 `제1조(목적)` 이
     `목적` 으로 나왔다. 사장님: "hwpx는 똑같이 안만들어지는데?"
  ④ 지금: **화면을 읽어 옮긴다.**
       build/화면읽기.py  크롬에 물어 실제 그려진 값을 트리로 받는다
       build/역할.py      그 트리를 "쓸 명령" 으로 바꾼다 (기본이 **옮김** 이다)
       build/_hwpx_write.py  명령을 python-hwpx 로 실행한다

왜 자료가 아니라 화면인가 — 글머리 `□ ○ -` 가 자료에 없다. 자료엔 "2단계" 만 있고
무슨 글자인지는 CSS 가 정하며, `[data-style="gov"]`·`[data-hier="B"]` 스위치가 그걸 바꾼다.
자료만 보면 찍어서 맞혀야 하고 틀린다. 화면에는 답이 이미 나와 있다.
게다가 장르마다 자료 모양이 전혀 달라(공통 키가 하나도 없다) 자료 읽는 코드가 그 자체로
손목록이 된다 — 이 저장소가 일곱 번 밟은 함정이다.

빌린 것 — 쓰기는 **python-hwpx 6.0.2**, 되읽어 재기는 그 안의 `read_fidelity.resolve_run_spans`,
CSS↔문서속성 사상표는 **html4docx**(MIT)를 참고했다. 손으로 짠 XML 파서는 버렸다.
`pypandoc-hwpx`·`hwp-parser` 는 둘 다 CSS 를 버리고 자기 템플릿을 씌우는 방식이라 안 쓴다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

여기 = Path(__file__).resolve().parent
ROOT = 여기.parent
_VENV = 여기 / ".hwpxenv"

sys.path.insert(0, str(여기))


def 만들기(입력, 낼곳):
    """HTML 하나를 HWPX 하나로. `(된다, 말)` 을 돌려준다.

    `입력` 은 **HTML 경로**다. 인스턴스 dict 는 더 이상 안 받는다.

    **왜 뺐나 (2026-08-07 실측, S4 와는 별개로 원래 깨져 있던 것)** — 전에는 dict 를
    주면 여기서 `import 자료뿌리` 로 그 문서의 HTML 자리를 스스로 찾았다. 그런데 이
    모듈은 서버 프로세스 안에서 `자료뿌리.모듈("tohwpx")` 로 올라오고, 그때의
    `import 자료뿌리` 는 **두 번째 복사본**을 올린다(api.py 는 자료뿌리를 파일에서
    바로 불러 sys.modules 에 안 걸어 둔다). 세션 열쇠는 스레드 지역값이라 그 복사본엔
    없다 — 그래서 세션 안에서 hwpx 를 내보내면 기본 뿌리를 보고 "HTML 이 없습니다"
    로 끝났다(자료뿌리.py 머리말의 '딸린 함정'이 실제로 문 것이다).
    재 봤다: 세션 A 에서 동기 `/api/export` 와 작업 경로가 **똑같이** 실패했고, 부르는
    쪽(workspace/api.py 내보내기)이 경로를 정해 넘기게 하자 둘 다 3.3초에 됐다.

    부르는 쪽이 뿌리를 아는 유일한 자리다. 여기서 다시 찾게 두면 같은 함정이 또 열린다.
    """
    import 역할
    import 화면읽기

    py = _VENV / "bin" / "python"
    if not py.exists():
        return False, ("HWPX 라이브러리가 없습니다 — build/.hwpxenv 를 만들고 "
                       "python-hwpx 를 설치하세요")

    if isinstance(입력, dict):
        return False, ("HWPX 는 문서 dict 가 아니라 **완성된 HTML 경로**를 받습니다 — "
                       "부르는 쪽이 자료뿌리로 경로를 정해 넘겨야 합니다 "
                       "(여기서 찾으면 세션 뿌리를 못 봅니다)")
    html경로 = Path(입력)
    if not html경로.exists():
        return False, (f"HTML 이 없습니다: {html경로.name} — HWPX 는 완성된 화면을 "
                       f"옮기는 것이라 먼저 조립해야 합니다")

    try:
        읽은것 = 화면읽기.읽기(html경로)
    except SystemExit as e:
        return False, f"화면을 못 읽었습니다 — {e}"
    꾸러미 = 역할.옮기기(읽은것, 문서이름=html경로.stem)

    # **완전성 가드** — 카탈로그가 모르는 서식을 만나면 여기서 선다(WP-H2).
    # 조용히 근사치로 옮기면 그 값은 영원히 미지로 남는다. 세우면 이름이 붙는다.
    if not 꾸러미["ok"]:
        구멍 = 꾸러미["구멍"]
        줄 = [f'{c["종류"]}·{c["속성"]}={c["값"]} ({c["사유"]})'
              f' @ {c["어디"]["문서"]}'
              + (f' / {", ".join(c["어디"]["경로"] or c["어디"]["반"])}'
                 if (c["어디"]["경로"] or c["어디"]["반"]) else "")
              for c in 구멍[:6]]
        return False, (
            f"카탈로그 밖의 서식 {len(구멍)}건 — 옮기지 않았습니다: " + " · ".join(줄)
            + (f" 외 {len(구멍) - 6}건" if len(구멍) > 6 else "")
            + " → build/카탈로그.py 를 다시 돌려 항목을 등록하고 전이규칙을 검증하십시오")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(꾸러미, fh, ensure_ascii=False)
        인자길 = fh.name
    낼곳 = os.path.abspath(낼곳)
    if os.path.exists(낼곳):
        os.remove(낼곳)
    try:
        r = subprocess.run([str(py), str(여기 / "_hwpx_write.py"), 인자길, 낼곳],
                           capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, "HWPX 만들기가 너무 오래 걸립니다"
    finally:
        os.remove(인자길)

    if r.returncode != 0 or not os.path.exists(낼곳):
        return False, ((r.stdout or "") + (r.stderr or "")).strip()[-800:]

    # 원본 지문을 zip 코멘트에 심는다 — verify_all 의 낡음 검사가 "이 hwpx 가 어느
    # html 에서 나왔나"를 대조할 유일한 근거다(mtime 은 checkout 이 지운다, 2026-08-14
    # 낡음 사건: html 재조립 후 hwpx 미재생성이 대조 16/38 로 나타남). 표준 파트
    # 밖(zip 아카이브 코멘트)이라 스키마 검증(dvc)·한글 뷰어 모두 안 건드린다.
    m기준 = re.search(r'<meta name="기준" content="([0-9a-f]+)"',
                    html경로.read_text(encoding="utf-8"))
    if m기준:
        try:
            import zipfile
            with zipfile.ZipFile(낼곳, "a") as z:
                z.comment = json.dumps({"원본기준": m기준.group(1)}).encode()
        except Exception as e:
            return False, f"원본 지문을 못 심었다 — {type(e).__name__}: {e}"

    try:
        결 = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        결 = {}
    센것 = 결.get("센것") or {}
    말 = [f"{os.path.basename(낼곳)} ({os.path.getsize(낼곳):,}바이트)",
         " · ".join(f"{k} {v}" for k, v in 센것.items()) or "빈 문서"]
    말.append("스키마 통과" if not 결.get("스키마문제")
              else f"스키마 {len(결['스키마문제'])}건 어긋남: {결['스키마문제'][0][:70]}")
    # **못 옮긴 것을 숨기지 않는다.** "화면과 같다" 는 말은 이 목록을 뺀 뜻으로만 쓴다.
    if 꾸러미["미지정"]:
        이름 = sorted({(m.get("역할") or m.get("반") or "?") for m in 꾸러미["미지정"]})
        말.append(f"등록 안 된 역할 {len(꾸러미['미지정'])}개: {', '.join(이름[:5])}")
    if 결.get("알려진차이"):
        말.append("알려진 차이 — " + " / ".join(결["알려진차이"][:3]))
    return True, " · ".join(말)


def 되읽기(hwpx경로):
    """만든 HWPX 를 **되읽어** 글자마다 실제 서식을 뽑는다.

    손으로 XML 을 파싱하지 않는다 — python-hwpx 의 `resolve_run_spans` 가
    charPr 와 fontface 표를 다 풀어서 준다(글꼴 이름까지).
    """
    py = _VENV / "bin" / "python"
    코드 = (
        "import json,sys\n"
        "from hwpx.document import HwpxDocument\n"
        "from hwpx.tools.read_fidelity import resolve_run_spans\n"
        "d=HwpxDocument.open(sys.argv[1])\n"
        "print(json.dumps([{'글':s.text,'pt':s.size_pt,'굵게':s.bold,'색':s.color,\n"
        "                   '글꼴':s.font,'밑줄':bool(s.underline)}\n"
        "                  for s in resolve_run_spans(d) if s.text.strip()],ensure_ascii=False))\n")
    r = subprocess.run([str(py), "-c", 코드, str(hwpx경로)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return None, r.stderr.strip()[-300:]
    return json.loads(r.stdout), None


if __name__ == "__main__":
    입력 = sys.argv[1]
    낼곳 = sys.argv[2] if len(sys.argv) > 2 else str(Path(입력).with_suffix(".hwpx"))
    ok, 말 = 만들기(입력, 낼곳)
    print(("✓ " if ok else "✗ ") + 말)
    sys.exit(0 if ok else 1)
