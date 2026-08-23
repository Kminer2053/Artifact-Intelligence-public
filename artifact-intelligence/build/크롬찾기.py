#!/usr/bin/env python3
"""크롬(헤드리스) 실행 파일을 찾는 단 하나의 창구 — WP-S8.

왜 만들었나: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" 절대경로가
build/화면읽기.py · build/observe.py · build/verify_all.py · workspace/api.py ·
build/render_verify.sh 다섯 곳에 따로 박혀 있었다. 이 저장소는 맥에서 만들어졌지만
서버화(WP-S 트랙)로 컨테이너에 올라간다 — 그러면 다섯 곳을 전부 고쳐야 하고, 하나라도
빠지면 그 한 곳만 "크롬 없음"으로 조용히 새는 병이 난다. 손목록이 열두 번 넘게 밟은
함정과 같은 모양이다(구현계획.md 규칙 2) — **찾는 눈도 하나여야 한다.**

찾는 순서:
  ① 환경변수 문서지능_크롬 — 사람이 명시한 값이다. 이게 있으면 다른 데는 보지 않는다.
     틀린 값을 줬을 때도 그 값 그대로 "못 찾았다"고 답해야 한다 — 아니면 지정한 게
     실제로 쓰였는지 확인할 길이 없다(예: 시험 삼아 없는 경로를 줬는데 조용히 다른
     크롬을 찾아 쓰면, 그 시험은 아무것도 검증하지 못한 것이 된다).
  ② 흔한 설치 경로 — 맥 Chrome·Chromium, 그다음 리눅스 chromium·chromium-browser·
     google-chrome(컨테이너 배포 대비).
  ③ PATH — 위 둘 다 없을 때 마지막으로 훑는다.

두 함수를 낸다:
  · `찾기()` — 찾으면 경로, 못 찾으면 None. **죽지 않는다.** 브라우저가 없어도
    검사를 건너뛰고 계속 돌아야 하는 곳(verify_all 의 소프트 검사들)이 쓴다.
  · `크롬()` — 찾아서 돌려주거나, 본 곳 전부와 고치는 법을 담아 SystemExit 로 죽는다
    (구현계획.md 규칙 3 — 조용한 실패 금지). 화면을 반드시 읽어야 하는 곳(화면읽기 등)이 쓴다.
"""
from __future__ import annotations

import os
import shutil

환경변수 = "문서지능_크롬"

# 흔한 설치 경로 — 맥이 먼저(개발 환경), 그다음 리눅스(컨테이너 배포 대비).
# **일부러 이름 앞에 밑줄을 안 붙였다** — build/verify_all.py 의 check_chrome_hardcode
# 가 "하드코딩 재발" 을 이 목록에서 그대로 가져와 찾는다. 절대경로 문자열의 정본이
# 여기 하나뿐이어야 검사도 다른 곳에 그 문자열을 또 베끼지 않는다.
흔한경로 = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
]

# PATH 에서 훑을 실행 파일 이름들.
_PATH이름 = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]


def 찾기() -> str | None:
    """찾으면 경로를, 못 찾으면 None 을 돌려준다 — 죽지 않는다."""
    지정 = os.environ.get(환경변수)
    if 지정:
        # 사람이 명시했다 — 다른 곳은 보지 않는다(위 사연 참고).
        return 지정 if os.path.exists(지정) else None

    for 경로 in 흔한경로:
        if os.path.exists(경로):
            return 경로

    for 이름 in _PATH이름:
        found = shutil.which(이름)
        if found:
            return found

    return None


def 크롬() -> str:
    """찾아서 경로를 돌려주거나, 무엇을 봤고 무엇을 하면 되는지 말하며 죽는다."""
    경로 = 찾기()
    if 경로:
        return 경로

    지정 = os.environ.get(환경변수)
    본곳 = []
    if 지정:
        본곳.append(f"  · 환경변수 {환경변수}={지정} — 이 경로에 실행 파일이 없습니다"
                   " (지정했으므로 다른 곳은 보지 않았습니다)")
    else:
        본곳.append(f"  · 환경변수 {환경변수} — 설정 안 됨")
        본곳.append("  · 흔한 설치 경로:")
        본곳 += [f"      {p}" for p in 흔한경로]
        본곳.append("  · PATH: " + ", ".join(_PATH이름))

    raise SystemExit(
        "크롬(또는 Chromium)을 찾지 못했습니다 — 화면을 읽거나 인쇄할 수 없습니다.\n"
        "본 곳:\n" + "\n".join(본곳) + "\n\n"
        "고치는 법:\n"
        "  · 크롬/Chromium 을 설치하십시오"
        " (예: brew install --cask google-chrome, apt-get install -y chromium), 또는\n"
        f"  · 이미 있는 실행 파일 경로를 알려 주십시오: {환경변수}=/path/to/chrome"
    )


if __name__ == "__main__":
    print(크롬())
