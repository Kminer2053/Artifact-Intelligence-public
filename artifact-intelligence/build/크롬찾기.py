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
import subprocess
import tempfile
import time

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


# ── 헤들리스 실행(격리 프로필 + '다 쓰면 회수') ─────────────────────────────
# 왜 여기 있나(WP-S8 의 짝): 크롬을 **찾는** 눈이 하나여야 하듯 **돌리는** 손도 하나여야
# 한다. 헤들리스 크롬은 사용자의 실행 중 Chrome 과 겹치면 산출물을 다 쓰고도 종료하지
# 않는다(macOS 실측 '26-08-24: --headless·--headless=new 동일 — PDF 를 2초에 쓰고 무한
# 대기). 컨테이너 배포엔 경쟁 Chrome 이 없어 스스로 끝난다. 그래서 ① 격리 프로필로 시작
# 락을 피하고 ② 산출물의 끝표시가 보이면 kill 로 회수한다. 이 손이 하나가 아니면
# render_verify.sh 만 고치고 api.py·observe.py 는 옛 방식으로 남아 데스크톱에서 3분씩 행한다.

# ── 부모와 함께 죽는 크롬('26-10-01 주관 판정 R3, verify_fixup5_ux B2) ─────────────────────────────────────
# 크롬은 부모(serve.py·MCP 서버·tohwpx 자식)가 SIGKILL 로 죽어도 스스로 끝나지 않는다 — 부모 쪽 지키미(serve.py
# _크롬지키기)는 1초마다 자손을 적어서, 적은 뒤 1초 안에 뜬 인쇄 크롬(PDF 는 1초 안팎만 산다)을 놓쳤다(무작위 10번 중
# 2번 고아, 20분 넘게 살아 있었다). 그래서 **자식 쪽**에서 지킨다:
#   ① 부모가 파이프를 하나 만들어 쓰는 끝을 쥔 채 감시자(작은 파이썬)를 띄운다 — 파이프는 감시자·크롬이 뜨기 **전에**
#      있으므로 떠오르는 동안의 틈이 없다. 부모가 어떤 신호로 죽든 커널이 쓰는 끝을 닫아, 감시자의 읽는 끝이 끝(EOF)을
#      본다(맥·리눅스 모두 — prctl(PR_SET_PDEATHSIG) 는 리눅스뿐이라 쓰지 않는다).
#   ② 감시자는 크롬을 **새 프로세스 그룹**(start_new_session)으로 띄우고, 파이프 끝·SIGTERM·SIGHUP·SIGINT 를 받으면 그 그룹
#      (크롬과 도우미 프로세스)을 통째로 끈다(SIGTERM → 2초 뒤 SIGKILL). 크롬이 먼저 뜨기 전에 파이프가 닫혔으면 띄우지 않는다.
#   ③ 크롬이 스스로 끝나면 감시자도 그 끝남 코드로 끝난다(남은 도우미는 그룹째 끈다).
# 이 손을 모든 헤들리스 크롬(인쇄·덤프·HWPX 화면읽기·PPTX 수확)이 쓴다. serve.py 의 지키미는 곁 방어로 둔다.
_감시코드 = r"""
import os, select, signal, subprocess, sys, time
fd = int(sys.argv[1]); 치울 = sys.argv[2]; args = sys.argv[3:]
p = None; 멈춤 = []; 부모 = os.getppid()
def 끄기(급히):
    # 급히(파이프 끝 — 부모가 죽었거나 kill) = 곧바로 SIGKILL, 아니면(SIGTERM 등) SIGTERM 뒤 2초 안에 안 끝나면 SIGKILL
    if p is not None:
        if not 급히:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
            끝 = time.monotonic() + 2
            while time.monotonic() < 끝 and p.poll() is None:
                time.sleep(0.05)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    if 치울 and os.getppid() != 부모:
        # 부모가 죽었을 때만 임시 프로필을 지운다(살아 있으면 부모가 지운다 — 둘이 함께 지우다 부딪히지 않게)
        import shutil
        shutil.rmtree(치울, ignore_errors=True)
def 받음(n, f):
    멈춤.append(n)
    if p is not None:
        끄기(False)
        os._exit(128 + n)
for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    signal.signal(s, 받음)
def 닫혔나(초):
    r, _, _ = select.select([fd], [], [], 초)
    if not r:
        return False
    try:
        return os.read(fd, 512) == b""
    except OSError:
        return True
if 닫혔나(0):
    p = None; 끄기(True); os._exit(137)
p = subprocess.Popen(args, start_new_session=True, stdin=subprocess.DEVNULL)
if 멈춤:
    끄기(False); os._exit(128 + 멈춤[0])
while True:
    if 닫혔나(0.2):
        끄기(True); os._exit(137)
    rc = p.poll()
    if rc is not None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        os._exit(rc if rc >= 0 else 128 - rc)
"""


class 크롬프로세스:
    """띄우기() 가 돌려주는 Popen 닮은 손잡이 — poll·wait·terminate·kill·pid(감시자). kill 도 감시자를 통해 크롬 그룹째 끈다."""

    def __init__(self, p, 쓰는끝):
        self._p = p
        self._w = 쓰는끝
        self.pid = p.pid

    def _닫기(self):
        if self._w is not None:
            try:
                os.close(self._w)
            except OSError:
                pass
            self._w = None

    def poll(self):
        rc = self._p.poll()
        if rc is not None:
            self._닫기()
        return rc

    @property
    def returncode(self):
        return self._p.returncode

    def wait(self, timeout=None):
        rc = self._p.wait(timeout=timeout)
        self._닫기()
        return rc

    def terminate(self):
        try:
            self._p.terminate()        # 감시자가 SIGTERM 을 받아 크롬 그룹을 끄고 끝난다
        except OSError:
            pass

    def kill(self):
        # 감시자를 SIGKILL 하면 크롬이 고아가 된다 — 파이프를 닫아(=부모가 죽은 것과 같다) 감시자가 그룹째 곧바로 끄게 하고,
        # 그래도 안 끝나면 그때 감시자를 죽인다
        self._닫기()
        try:
            self._p.wait(timeout=6)
        except Exception:
            try:
                self._p.kill()
            except OSError:
                pass


def 띄우기(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 치울=""):
    """헤들리스 크롬을 **부모와 함께 죽게** 띄운다(위 ①~③). args 는 크롬 명령줄 그대로. 치울 = 부모가 죽었을 때 감시자가 지울
    임시 프로필 폴더(부모가 살아 있으면 부모가 지운다). 돌려주는 값은 Popen 닮은 크롬프로세스."""
    import sys as _sys
    r, w = os.pipe()                 # 둘 다 이어받지 않는 fd(PEP 446) — 감시자에게만 r 을 넘긴다
    try:
        p = subprocess.Popen([_sys.executable, "-c", _감시코드, str(r), 치울 or ""] + list(args),
                             stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, pass_fds=(r,))
    except Exception:
        os.close(w)
        raise
    finally:
        os.close(r)
    return 크롬프로세스(p, w)


def _돌려서_회수(args, 감시파일, 끝표시, 최대초, stdout_path=None):
    """헤들리스 크롬을 격리 프로필로 띄우고, 감시파일 꼬리에 끝표시가 보이면(또는 스스로
    종료하면) kill 로 회수한다. stdout_path 를 주면 크롬 stdout 을 그 파일로 받는다."""
    prof = tempfile.mkdtemp(prefix="munseo-chrome.")
    out = open(stdout_path, "wb") if stdout_path else subprocess.DEVNULL
    try:
        p = 띄우기(
            args + ["--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check"],
            stdout=out, stderr=subprocess.DEVNULL, 치울=prof)
        기한 = time.monotonic() + 최대초
        while time.monotonic() < 기한:
            if p.poll() is not None:          # 스스로 종료(컨테이너: 경쟁 Chrome 없음)
                break
            try:
                if os.path.exists(감시파일) and os.path.getsize(감시파일) > 0:
                    with open(감시파일, "rb") as f:
                        f.seek(max(0, os.path.getsize(감시파일) - 600))
                        if 끝표시 in f.read():
                            break
            except OSError:
                pass
            time.sleep(0.4)
        if p.poll() is None:
            p.kill()
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    finally:
        if stdout_path:
            try:
                out.close()
            except Exception:
                pass
        shutil.rmtree(prof, ignore_errors=True)


def 인쇄(씀, url, 출력pdf, 예산=8000, 최대초=25):
    """헤들리스 크롬으로 url 을 출력pdf 로 인쇄한다(격리 프로필 + %%EOF 회수). 만들어졌으면 True."""
    # **옛 산출물을 먼저 지운다** — 안 지우면 이전 PDF 의 꼬리 %%EOF 를 폴링이 즉시 보고
    # 크롬이 새로 쓰기도 전에 kill 해 옛 파일을 돌려준다(레이스). 지워야 이번 렌더만 잡는다.
    try:
        os.remove(출력pdf)
    except OSError:
        pass
    args = [씀, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--virtual-time-budget={예산}", f"--print-to-pdf={출력pdf}", url]
    _돌려서_회수(args, 출력pdf, b"%%EOF", 최대초)
    return os.path.exists(출력pdf)


def 덤프(씀, url, 예산=6000, 최대초=25):
    """헤들리스 크롬으로 url 의 렌더된 DOM 을 돌려준다(--dump-dom, 격리 프로필 + </html> 회수).
    못 얻으면 None."""
    fd, tmp = tempfile.mkstemp(suffix=".dom")
    os.close(fd)
    args = [씀, "--headless", "--disable-gpu", f"--virtual-time-budget={예산}", "--dump-dom", url]
    try:
        _돌려서_회수(args, tmp, b"</html>", 최대초, stdout_path=tmp)
        with open(tmp, encoding="utf-8", errors="replace") as f:
            s = f.read()
        return s or None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    print(크롬())
