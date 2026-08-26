#!/usr/bin/env python3
"""자료뿌리 — **운영 자료가 사는 곳을 정하는 유일한 곳**. (구현계획.md §3 WP-S2 ①)

왜 만들었나 (2026-08-07, 부록/출시차단감사.md 의 결론 문장):
  지금까지 모든 경로가 `ROOT = os.path.dirname(__file__)` 에서 파생된 **상수**였다.
  코드와 자료가 한 뿌리에 붙어 있어서 세션을 가를 **주입점이 아예 없었다** —
  `history/version.py` 의 `BASE`·`SRC` 가 대표적이다(G-1). 세션 격리는 경로 몇 개를
  바꾸는 일이 아니라 "코드 루트"와 "자료 루트"를 가르는 **구조 변경**이고, 이 파일이
  그 구조의 전부다. 자료를 읽고 쓰는 코드는 전부 여기를 거친다.

코드냐 자료냐 — 가르는 기준 한 줄:
  **사용자·세션이 만들거나 고치는 것 = 자료 / 우리가 짜서 배포하는 것 = 코드.**
    코드: build/*.css · build/*.js · 조립기 .py · ontology/ · buildplan/rewind-rules.json ·
          buildplan/skeleton.css · build/전이카탈로그.json · SKILL.md · feedback/ledger.json
          (원장은 세션 자료가 아니라 우리가 배운 규칙이다. 코드는 읽기만 한다)
    자료: build/*-docs.json(등록부) · build/samples(산출물) · build/observed(관측) ·
          build/assets(이미지 자산) · buildplan/plan-*.json · buildplan/plan.html ·
          buildplan/skeletons/ · workspace/editors ·
          workspace/inbox · workspace/requests · history/ · feedback/edit-log.jsonl ·
          feedback/backups

기본값이면 **바이트 하나 안 달라진다**: 환경변수 `문서지능_자료뿌리` 가 없으면
자료뿌리 = 코드뿌리라서 모든 경로가 지금과 글자 하나까지 같다.

**세션**(WP-S2 ②, 2026-08-07): 익명 세션 하나 = 격리된 자료뿌리 하나다.
`문서지능_세션=<열쇠>` 가 있으면 자료뿌리가 `<기본자료뿌리>/sessions/<열쇠>` 로 풀린다.
**열쇠가 없으면 지금과 완전히 같다** — 개발·CLI·verify_all·대조·조립기 직접 실행은
전부 열쇠 없이 도는 길이라 한 줄도 안 달라진다. 열쇠는 **경로가 되므로** 반드시
검증한다(아래 `열쇠올바른가`) — 안 하면 `../..` 하나로 격리가 통째로 뚫린다.

이 모듈의 규칙 셋:
  ① 저장소의 어떤 모듈도 import 하지 않는다 — 누구나 순환 없이 부를 수 있어야 한다.
     (다른 모듈이 필요하면 `모듈("genres")` 로 **부를 때** 불러온다)
  ② 상태를 들지 않는다 — 값은 매번 환경에서 다시 읽는다. 그래서 여러 벌 불러들여도
     같게 답한다(파일 경로로 직접 불러 쓰는 곳이 많다).
     ※ 예외 하나 — 세션 열쇠는 **스레드마다** 다를 수 있어서(serve.py 는
       ThreadingHTTPServer 다) 스레드 지역 저장소에 얹을 수 있다. 그것도 상태를
       프로세스 전체로 들지 않는 길을 고른 것이다: `os.environ` 에 세션 열쇠를
       대입하면 옆 스레드가 처리 중인 **남의 세션 뿌리가 바뀐다**(격리가 요청
       사이에 무작위로 새는, 재현이 거의 안 되는 모양이다).
       **딸린 함정(2026-08-07 고침, WP-S4)**: 이 저장소는 이 파일을 `importlib` 로
       **여러 벌** 불러 쓴다(build/ 밖에서 sys.path 를 안 늘리려고). 예전에는 그 값을
       `threading.local()` 에 뒀는데 그 객체는 **모듈 복사본마다 따로** 살아서, 두
       벌째는 늘 빈 값을 보고 기본 뿌리를 돌려줬다 — 세션 안에서 hwpx 내보내기·이력
       조회가 조용히 남의 뿌리를 봤다(아래 `_열쇠칸` 주석에 실측을 적어 뒀다).
       지금은 값을 **스레드 객체 자체**에 얹으므로 복사본이 몇 벌이든 같게 답한다.
       그래도 지키는 것 둘: ① `build/세션.py` 의 함수는 전부 열쇠를 **인자로 받는다**
       (지우고 만드는 일에 지역값을 끼우지 않는다), ② 자식 프로세스는 `자식환경()` 이
       실어 준 환경변수로 받는다.
  ③ 없는 뿌리는 **스스로 세운다**. 못 세우면 조용히 넘어가지 않고 무엇이 문제인지
     말하며 죽는다(구현계획.md 규칙 3).
"""
import glob
import os
import re
import sys
import threading
import time

환경변수 = "문서지능_자료뿌리"
세션환경변수 = "문서지능_세션"

# 선로(HTTP) 위에서 세션을 잇는 쿠키 이름. **영문이어야 한다** — 파이썬
# `http.cookies` 의 열쇠 패턴이 `re.ASCII` 이고, urllib 는 헤더를 latin-1 로 인코딩해
# 한글 이름은 요청을 만들 때부터 죽는다(구현계획.md 규칙 8: 선로 위의 열쇠는 영문).
#
# 왜 자료뿌리에 두나 — 이 이름을 아는 곳이 둘이다: 쿠키를 굽고 읽는 `workspace/serve.py`
# 와, 원격 코어로 세션을 실어 보내는 `workspace/api.py` 의 `_원격()`. 양쪽에 따로
# 적으면 한쪽만 고칠 때 **세션이 조용히 안 이어진다**(요청마다 새 방이 서고, 원격
# 클라이언트는 자기가 방금 만든 문서를 못 찾는다 — 2026-08-07 실측으로 걸린 모양이다).
세션쿠키 = "mjsid"

# 자료뿌리가 코드뿌리와 다를 때, 자료 밑에 **코드 자산으로 이어 주는 다리**.
# 왜 필요한가 — 산출 HTML 은 `../report.css` 처럼 **상대 경로**로 서식을 부른다
# (build/samples/x.html → build/report.css). 자료뿌리만 옮기면 그 상대 경로가
# 자료뿌리/build/report.css 를 가리키는데 거기엔 CSS 가 없다. 그러면 파일은 열리는데
# 서식이 없는 채로 뜬다 — 이 저장소가 제일 자주 밟은 "조용한 실패" 모양이다.
# 그래서 뿌리를 세울 때 코드의 CSS·JS·글꼴을 자료뿌리 밑으로 이어 준다(심링크, 안 되면 복사).
# 목록은 손으로 안 적는다 — 확장자와 디렉터리 이름만 정하고 **세어서** 잇는다.
다리_확장자 = (".css", ".js")
다리_디렉터리 = {"build": ("fonts",)}

_세운것 = set()


def 코드뿌리():
    """코드가 사는 곳 — 이 파일(build/자료뿌리.py)의 두 단계 위."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 세션 열쇠 ───────────────────────────────────────────────────────────
# 열쇠는 **디렉터리 이름이 된다.** 그러므로 검증이 곧 격리다.
#   · 영소문자·숫자만: `.`·`/` 를 아예 못 쓰므로 `../../..` 류 경로 탈출이 불가능하다.
#     대문자를 뺀 까닭 — macOS·Windows 파일계는 대소문자를 안 가려서 `AbC` 와 `abc`
#     가 **같은 방**을 쓴다. 열쇠가 다른 두 사람이 한 세션을 공유하게 된다.
#   · 16자 이상: 추측 불가 길이. 우리가 내는 열쇠는 `secrets.token_hex(16)`(32자,
#     128비트)다. 짧은 열쇠를 손으로 넣어 쓰는 길을 아예 안 열어 둔다.
세션방이름 = "sessions"
_열쇠꼴 = re.compile(r"[a-z0-9]{16,64}")

# 지금 스레드의 세션 열쇠를 **스레드 객체 자체**에 얹는다 (2026-08-07 고침).
#
# 왜 `threading.local()` 이 아닌가 — 머리말의 '딸린 함정'이 실제로 물었다. 이 저장소는
# 이 파일을 `importlib` 로 **여러 벌** 불러 쓰는데(build/ 밖에서 sys.path 를 안 늘리려고),
# `threading.local()` 객체는 불러들인 **모듈 복사본마다 따로** 산다. 그래서 첫 벌에
# 열쇠를 끼워도 두 벌째는 늘 빈 값을 보고 **기본 뿌리**를 돌려줬다. 재 봤다(2026-08-07,
# WP-S4):
#   · `자료뿌리.모듈("tohwpx")` → tohwpx 의 `import 자료뿌리` 가 두 벌째 → 세션 안
#     hwpx 내보내기가 "HTML 이 없습니다" 로 죽었다(동기·비동기 경로 똑같이).
#   · `자료뿌리.모듈("version","history")` → api.이력() 이 **세션 이력을 못 봤다**
#     (세션 방에 기록을 심어 두고 불러도 `{"판": [], "기록": []}`).
#   · `자료뿌리.모듈("genres")` → 등록부를 기본 뿌리에서 셌다.
# 셋 다 **부르는 쪽이 경로를 넘기게** 고칠 수도 있지만, 그러면 새 모듈이 생길 때마다
# 같은 함정이 다시 열린다. 값이 사는 자리를 복사본 밖으로 옮기는 것이 뿌리 고침이다.
#
# 스레드 객체는 복사본이 몇 벌이든 **하나**다 — 같은 스레드면 어느 복사본이 물어도 같은
# 답이 나온다. 격리 성질은 그대로다: 스레드마다 객체가 다르고(옆 요청의 뿌리가 안 바뀐다),
# 새 스레드는 값을 물려받지 않는다(`threading.local()` 과 같다 — 그래서 작업 스레드는
# `세션갈기` 로 명시로 끼운다).
_열쇠칸 = "_문서지능_세션열쇠"


def _열쇠읽기():
    return getattr(threading.current_thread(), _열쇠칸, None)


def _열쇠쓰기(v):
    setattr(threading.current_thread(), _열쇠칸, v)


class 나쁜열쇠(ValueError):
    """세션 열쇠가 규칙에 안 맞는다 — 조용히 무시하지 않고 여기서 선다."""


def 열쇠올바른가(v):
    return bool(v) and _열쇠꼴.fullmatch(str(v)) is not None


def 새열쇠():
    """추측 못 할 세션 열쇠 하나. 로그인이 없으므로 이 열쇠가 곧 신분이다."""
    import secrets
    return secrets.token_hex(16)


def 세션열쇠():
    """지금 처리 중인 세션의 열쇠. 없으면 빈 글자.

    스레드 지역값이 먼저다 — serve.py 가 요청마다 갈아 끼운다. 자식 프로세스
    (조립기·apply_edit_any)는 환경변수로 받는다(`자식환경()`).
    """
    v = _열쇠읽기()
    if v is None:
        v = os.environ.get(세션환경변수) or ""
    v = str(v).strip()
    if not v:
        return ""
    if not 열쇠올바른가(v):
        raise 나쁜열쇠(
            f"세션 열쇠가 규칙에 안 맞습니다 (영소문자·숫자 16~64자여야 합니다). "
            f"열쇠는 디렉터리 이름이 되므로 여기서 막지 않으면 남의 세션을 읽습니다")
    return v


class _세션갈기:
    """`with 자료뿌리.세션갈기(열쇠):` — 이 블록 동안만 그 세션 뿌리를 본다.

    열쇠에 빈 값을 주면 **세션 없음**(기본 뿌리)으로 갈린다. 끝나면 반드시
    이전 값으로 되돌린다 — 안 되돌리면 스레드가 재사용될 때 남의 세션이 샌다.
    """

    def __init__(self, 열쇠):
        self.열쇠 = (str(열쇠).strip() if 열쇠 else "")
        if self.열쇠 and not 열쇠올바른가(self.열쇠):
            raise 나쁜열쇠(f"세션 열쇠가 규칙에 안 맞습니다: 영소문자·숫자 16~64자")

    def __enter__(self):
        self.전 = _열쇠읽기()
        _열쇠쓰기(self.열쇠)
        return self.열쇠

    def __exit__(self, *a):
        _열쇠쓰기(self.전)
        return False


def 세션갈기(열쇠):
    return _세션갈기(열쇠)


def 쓰이는열쇠들():
    """지금 **어느 스레드가 쥐고 있는** 세션 열쇠 전부 (2026-08-07, WP-S2 ④).

    왜 필요한가 — `마지막활동` 은 요청이 **시작할 때** 한 번 찍힌다(serve.py `_세션으로`).
    그래서 오래 도는 요청 하나가 있으면 그동안 그 세션의 시계가 **멈춰 있다**. 실측:
    `/api/build` 0.13초 · `/api/refresh` 0.37초 짜리도 끝난 시점의 mtime 나이가 정확히
    걸린 시간만큼이었다. 조판게이트는 최대 900초(`api.조판게이트` timeout=900), 저장·
    조립은 180초를 쓴다 — 무반응 한도 600초보다 길다. 즉 **일하는 중인 세션이 만료로
    보여** 남의 요청이 그 방을 지울 수 있다. 시각을 두 번 재는 것으로는 못 막는다(두
    번 다 멈춘 시계를 보니까).
    그래서 시각 말고 **쥐고 있는가**를 본다. serve.py 는 요청 전체를 `세션갈기` 로
    감싸므로, 그 스레드에는 처리하는 동안 열쇠가 얹혀 있다.

    왜 스레드 객체를 훑나 — 이 값은 `threading.local()` 이 아니라 **스레드 객체 자체**에
    얹혀 있다(위 `_열쇠칸` 주석). 그래서 이 파일이 importlib 로 몇 벌 올라와 있든
    `threading.enumerate()` 로 한 번에 다 보인다. 끝난 스레드는 목록에 없으므로 값이
    남아 새는 일도 없다.

    **한계는 숨기지 않는다** — 이것은 *이 프로세스* 안의 일만 본다. 서버가 여러 벌이면
    A 에서 도는 긴 요청을 B 는 못 본다. 거기까지 막으려면 요청이 도는 동안 주기적으로
    `활동적기()` 를 다시 찍어야 하는데 그것은 serve.py 몫이라 여기서 안 한다.
    값(실측): 스레드 1개 0.79µs · 10개 1.83µs · 50개 6.08µs(p99 22.9µs) — 요청마다
    한 번이고, 요청 하나가 조립 subprocess 에 쓰는 수백 ms 에 견주면 없는 값이다.
    """
    난것 = set()
    for t in threading.enumerate():
        v = getattr(t, _열쇠칸, None)
        if v:
            난것.add(str(v))
    return 난것


def 자식환경(바탕=None):
    """자식 프로세스에 넘길 환경 — 지금 세션을 **그대로 물려준다.**

    왜 필요한가: 세션 열쇠는 스레드 지역값이라 `subprocess.run` 이 그냥은 못 본다.
    안 물려주면 조립기·apply_edit_any 가 **기본 뿌리**에 쓴다 — 세션이 격리된 것처럼
    보이는데 산출물만 전역으로 새는, 제일 알아채기 어려운 모양이다.
    """
    e = dict(바탕 if 바탕 is not None else os.environ)
    k = 세션열쇠()
    if k:
        e[세션환경변수] = k
    else:
        e.pop(세션환경변수, None)
    return e


# ── 뿌리 ────────────────────────────────────────────────────────────────

def 기본뿌리():
    """세션을 걷어낸 자료뿌리 — 세션들이 사는 집이자, 원장 후보·설정이 놓이는 곳."""
    v = (os.environ.get(환경변수) or "").strip()
    if not v:
        return 코드뿌리()
    p = os.path.abspath(os.path.expanduser(v))
    _세우기(p)
    return p


def 뿌리():
    """운영 자료가 사는 곳.

    · 세션 열쇠가 없으면 **현행 위치** — 환경변수가 없으면 코드뿌리다(무변화).
    · 세션 열쇠가 있으면 `<기본자료뿌리>/sessions/<열쇠>` — 그 세션만의 뿌리다.
    """
    기본 = 기본뿌리()
    k = 세션열쇠()
    if not k:
        return 기본
    p = os.path.join(기본, 세션방이름, k)
    _세우기(p)
    return p


def 세션들뿌리():
    """세션 디렉터리들이 사는 곳 — 청소기가 여기를 훑는다."""
    return os.path.join(기본뿌리(), 세션방이름)


def 세션방(열쇠):
    if not 열쇠올바른가(열쇠):
        raise 나쁜열쇠(f"세션 열쇠가 규칙에 안 맞습니다: 영소문자·숫자 16~64자")
    return os.path.join(세션들뿌리(), 열쇠)


def 마지막활동길(열쇠):
    """세션의 마지막 활동 시각. **파일의 mtime 이 정본**이고 내용은 사람이 읽으라고 둔다."""
    return os.path.join(세션방(열쇠), "마지막활동")


def 설정길():
    """관리자가 고치는 서버 설정(무반응 시간 등) — 세션이 아니라 **기본 뿌리**에 산다.
    세션 밑에 두면 세션이 지워질 때 같이 지워진다."""
    return os.path.join(기본뿌리(), "설정.json")


def 후보뿌리():
    """세션이 끝날 때 남기는 **익명 원장 후보** — 기본 뿌리에 쌓인다(출시계획 1-6)."""
    return os.path.join(기본뿌리(), "feedback", "candidates")


def 코퍼스뿌리():
    """**동의 코퍼스**가 사는 곳 — 기본 뿌리에 쌓인다(구현계획.md §3 WP-S10).

    왜 **기본 뿌리**이고 세션이 아닌가 — 코퍼스는 사용자가 **동의해서** 세션 밖으로
    남기기로 한 피드백 예시다. 세션 뿌리에 두면 세션이 끝날 때 같이 지워진다(1-6 A안:
    세션 내용은 소멸). 그래서 후보(익명 원장)와 같은 자리, 세션을 걷어낸 기본 뿌리에
    둔다 — 세션이 살아 있는 동안 써도 **여기로 가지 세션층엔 흔적이 안 남는다**
    (WP-S10 하드 기준: 세션 소멸 안 깨짐).

    익명 원장 후보(candidates)와 **다른** 자리인 까닭 — 후보는 규칙 id·횟수만 든
    익명 카운트다(문서 내용 없음). 코퍼스는 **동의 기반**이고 비식별을 거친 **예시**
    (용어 델타·구조 델타)를 담는다. 둘을 한 폴더에 섞으면 관리자 검토가 "카운트"와
    "예시"를 못 가른다 — 그래서 옆에 corpus/ 로 따로 둔다.

    디렉터리는 첫 쓰기 때 `원자덧쓰기`(안의 makedirs)가 세운다 — 자료디렉터리 목록에
    안 넣는 까닭은 그 목록이 **세션 뿌리** 밑에 만들어지는데(_세우기하나), 코퍼스는
    세션이 아니라 기본 뿌리에 살기 때문이다(세션마다 빈 corpus/ 를 세울 이유가 없다).
    """
    return os.path.join(기본뿌리(), "feedback", "corpus")


def 규칙기록길():
    """그 세션에서 **어느 규칙이 울렸나**만 적는 곳. 문서 글자는 한 자도 안 적는다.

    자리를 build/observed 밑으로 잡은 까닭 — 여기가 이미 "잰 것이 쌓이는 곳"이다
    (observe.py 의 `_ledger-candidates.json` 이 옆에 있다). 새 자리를 만들면
    다음 사람이 둘 중 어디를 봐야 하는지 모른다.
    """
    return os.path.join(관측뿌리(), "_규칙기록.jsonl")


# ── 규칙 id 꼴 강제 (WP-S2 적대리뷰 ①, 2026-08-09) ──────────────────────────
# 왜 sink 에서 막나 — `규칙적기` 가 적는 `_규칙기록.jsonl` 은 세션이 끝날 때 지워지지만,
# 그 내용을 `세션.py 후보뽑기` 가 긁어 **feedback/candidates** 로 옮긴다. 후보 파일은
# 세션이 **세션 밖에 남기는 유일한 흔적**이다(출시계획 1-6 A안: 사례는 소멸, 규칙 id·
# 횟수만 익명으로 남긴다). 그 불변식("규칙 id·횟수만, 문서 이름·내용 0")이 지금까지
# **부르는 쪽 규율에만** 기대고 있었다 — sink 는 넘어온 키를 `str()` 로 그대로 규칙명에
# 썼다. 부르는 자리 하나만 실수로 문장·고유명사를 키에 넣으면 그게 후보 파일로 샌다.
# 그래서 **sink 가 강제한다**: 규칙명은 규칙 id 꼴만, 값은 정수 횟수만.
#
# 왜 이 경계인가 — 실측된 규칙 id 는 전부 **짧은 라벨**이다:
#   soft:W-delta기호 · hard:H-표금지 · 어긋남:개 · 어긋남:% · 어긋남:? · 되묻기답 ·
#   카탈로그밖서식 · 수치 · 이름
# 공통점: **공백·문장부호·따옴표가 없고 짧다.** 문서 내용(제목·문장·고유명사구·자유글)은
# 반대로 공백/문장부호를 끼거나 길다(observe.py 의 실패 사유 "계측 실패 — <오류>" 처럼).
# 그래서 **허용 문자 집합**(`\w` = 영숫자·밑줄·한글, 그리고 `: % - ?`)과 **길이 상한**으로
# 가른다. 실측 id 최대 길이가 ~14 이므로 32 는 넉넉한 여유이자 "그보다 길면 내용스럽다"는
# 선이다. `?` 를 허용하는 까닭 — 단위를 못 구했을 때 `어긋남:?` 처럼 규칙 id 의 정당한
# 자리표시로 쓰인다(문장이면 공백 때문에 어차피 걸린다). 완벽 판별은 불가하니(구현계획
# 1-6) **애매하면 버린다**(과잉차단, 프라이버시 우선) — 짧고 공백 없는 단일 고유명사
# 토큰은 통과할 수 있으나, 그 경계까지 좁히면 진짜 규칙 id 를 깨뜨린다.
_규칙id꼴 = re.compile(r'[\w:%?-]{1,32}', re.UNICODE)
거른버킷 = "_거른내용"     # 내용스러워 버린 라벨의 횟수를 여기 한 자리에 합산한다


def 규칙라벨정리(라벨):
    """규칙 id 꼴이면 그 라벨을, 아니면 None. sink(규칙적기)·후보뽑기가 함께 쓴다.

    한 곳에 두는 까닭 — 경계(무엇이 규칙 id 이고 무엇이 내용인가)를 두 벌로 적으면
    한쪽만 고칠 때 갈린다. 세션 밖으로 나가는 흔적은 이 한 함수를 반드시 지난다.
    """
    s = str(라벨).strip()
    if not s or not _규칙id꼴.fullmatch(s):
        return None
    return s


def 규칙적기(출처, 규칙들):
    """규칙 id 와 횟수만 적는다 — **세션이 있을 때만.**

    `규칙들` 은 {규칙id: 횟수} 이거나 규칙 id 목록이다. 문서 이름·본문 글자는
    받지도 않는다(출시계획 1-6 A안: 세션이 끝나면 내용은 버리고 어느 규칙이
    어긋났는지만 남긴다).

    **sink 가 강제한다**(위 `규칙라벨정리` 주석) — 키가 규칙 id 꼴이 아니면(문장·
    고유명사구·자유글) 버리고, 대신 '거른 수'만 `거른버킷` 에 정수로 합산해 신호(몇 번
    울렸나)는 살린다. 값은 정수 횟수만 받고 못 세는 것은 버린다. 출처도 같은 규율을
    지난다(그 값 역시 후보 파일로 나간다).

    세션이 없으면 **아무것도 안 한다.** 개발·CLI·verify_all 은 세션 없이 도는 길이라
    여기서 파일을 쓰면 "열쇠 없으면 지금과 완전 동일" 이라는 약속이 깨진다.
    """
    try:
        if not 세션열쇠():
            return False
    except 나쁜열쇠:
        return False
    if not isinstance(규칙들, dict):
        from collections import Counter
        규칙들 = dict(Counter(str(x) for x in (규칙들 or [])))
    깨끗 = {}
    거른수 = 0
    for k, v in 규칙들.items():
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue                       # 못 세는 값은 후보의 분모가 아니다
        if n <= 0:
            continue
        라벨 = 규칙라벨정리(k)
        if 라벨 is None:                    # 내용스러운 키 — 라벨은 버리고 횟수만 버킷에
            거른수 += n
            continue
        깨끗[라벨] = 깨끗.get(라벨, 0) + n
    if 거른수:
        깨끗[거른버킷] = 깨끗.get(거른버킷, 0) + 거른수
    if not 깨끗:
        return False
    import json
    import time
    출처정 = 규칙라벨정리(출처) or 거른버킷
    원자덧쓰기(규칙기록길(),
            json.dumps({"때": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "출처": 출처정, "규칙": 깨끗}, ensure_ascii=False))
    return True


def 길(*조각):
    """자료뿌리 밑의 경로. 자료를 여는 모든 코드가 이 함수를 지난다."""
    return os.path.join(뿌리(), *조각)


# ── 원자 쓰기 (WP-S2 ③, 부록/출시차단감사.md E절) ────────────────────────
# 왜 여기 있나 — 자료 쓰기는 **전부** 이 모듈을 지나므로, 어떻게 쓰는지도 여기 한 곳에
# 두면 새 쓰기 자리가 생겨도 같은 길을 탄다. (뿌리 규칙 ①②는 그대로 지킨다: 저장소
# 모듈을 안 부르고 상태를 안 든다.)
#
# 무엇을 고치나 — 지금까지 모든 쓰기가 `open(경로, "w")` 였다. 그 한 줄이 하는 일이 둘이다:
#   ① 목적지 파일을 **먼저 0바이트로 자른다**  ② 그 다음 내용을 흘려 넣는다
# ①과 ② 사이에서 죽으면 **빈 파일이 남는다.** 2026-08-07 실측: 새문서가 실패했을 때
# `build/samples/<키>.html` 이 0바이트로 남았다(조립기가 `with open(...)` 안에서
# `build(doc)` 을 부르는 모양이라 doc 이 깨져 있으면 정확히 그 사이에서 죽는다).
# 동시 요청도 같은 뿌리다 — 쓰는 도중에 읽는 쪽(문서목록·조립 subprocess·정적 GET)이
# **반토막 JSON** 을 받는다.
#
# 고침: 같은 디렉터리에 tmp 를 쓰고 `os.replace` 로 갈아 끼운다. os.replace 는 같은
# 파일계 안에서 원자적이라, 읽는 쪽은 **옛 파일 아니면 새 파일**만 본다(중간이 없다).
# tmp 를 같은 디렉터리에 두는 까닭 — 다른 파일계(예: /tmp)에 두면 os.replace 가
# `EXDEV` 로 죽는다. 실패하면 tmp 를 치우고 목적지는 **손도 안 댄 채로** 둔다.
_tmp꼴 = ".tmp-{pid}-{n}"
_tmp번호 = [0]


def _tmp길(경로):
    _tmp번호[0] += 1
    return 경로 + _tmp꼴.format(pid=os.getpid(),
                              n=f"{threading.get_ident():x}{_tmp번호[0]}")


class _원자열기:
    """`with 자료뿌리.쓰기(경로) as f:` — `open(경로, "w")` 를 그대로 대신한다.

    블록이 예외로 끝나면 목적지는 **건드리지도 않는다**(tmp 만 지운다).
    그래서 `with 쓰기(p) as f: f.write(만들기())` 처럼 **블록 안에서 내용을 만들어도**
    안전하다 — 만들다 죽어도 옛 파일이 그대로 살아 있다.
    """

    def __init__(self, 경로, 모드="w", encoding="utf-8", newline=None):
        if "w" not in 모드:
            raise ValueError(f"원자 쓰기는 쓰기 모드만 받는다: {모드!r}")
        self.경로 = str(경로)
        self.모드 = 모드
        self.여는것 = {"mode": 모드}
        if "b" not in 모드:
            self.여는것["encoding"] = encoding
            self.여는것["newline"] = newline
        self.tmp = None
        self.f = None

    def __enter__(self):
        방 = os.path.dirname(os.path.abspath(self.경로))
        if 방:
            os.makedirs(방, exist_ok=True)
        self.tmp = _tmp길(self.경로)
        self.f = open(self.tmp, **self.여는것)
        return self.f

    def __exit__(self, 종류, 값, 자취):
        try:
            if self.f is not None:
                self.f.close()
            if 종류 is None:
                os.replace(self.tmp, self.경로)
                return False
        finally:
            # 성공했으면 tmp 는 이미 옮겨졌고, 실패했으면 여기서 치운다.
            # **잔재를 남기지 않는다** — 남으면 다음 사람이 그것을 산출물로 오해한다.
            if self.tmp and os.path.exists(self.tmp):
                try:
                    os.remove(self.tmp)
                except OSError:
                    pass
        return False


def 쓰기(경로, 모드="w", encoding="utf-8", newline=None):
    """원자 쓰기 컨텍스트. `open(경로, "w", encoding=...)` 자리에 그대로 넣는다."""
    return _원자열기(경로, 모드, encoding, newline)


def 원자쓰기(경로, 내용, encoding="utf-8"):
    """글(str) 또는 바이트(bytes) 한 벌을 통째로 원자적으로 놓는다."""
    if isinstance(내용, (bytes, bytearray)):
        with 쓰기(경로, "wb") as f:
            f.write(내용)
    else:
        with 쓰기(경로, "w", encoding=encoding) as f:
            f.write(내용)
    return 경로


def 원자json(경로, 값, **덤프인자):
    """JSON 한 벌을 원자적으로 놓는다. `json.dump(v, open(p,"w"), ...)` 자리."""
    import json as _json
    덤프인자.setdefault("ensure_ascii", False)
    with 쓰기(경로) as f:
        _json.dump(값, f, **덤프인자)
    return 경로


def 원자덧쓰기(경로, 줄):
    """append 전용(journal.jsonl 류). 원자 교체가 아니라 **한 번의 write** 로 붙인다.

    E-7 이 저위험이라 부른 자리다 — 여러 프로세스가 같은 파일에 붙일 때, 한 줄을
    나눠 쓰면 남의 줄 사이에 끼어 깨진다. `O_APPEND` 로 열고 한 번에 쓰면 파이프
    크기(4096바이트) 아래에서는 커널이 갈라 놓지 않는다. 줄이 그보다 길면 어차피
    보장이 없으므로 그 사실을 숨기지 않고 그대로 붙인다(조용한 실패 금지).
    """
    방 = os.path.dirname(os.path.abspath(경로))
    if 방:
        os.makedirs(방, exist_ok=True)
    if not 줄.endswith("\n"):
        줄 += "\n"
    fd = os.open(경로, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, 줄.encode("utf-8"))
    finally:
        os.close(fd)
    return 경로


# ── 빗장 — "읽고 → 판단하고 → 쓰는" 사이를 잠근다 (적대리뷰 ①③④⑥⑦, 2026-08-07) ──
#
# 왜 원자 쓰기로 안 되나 — 위 원자 쓰기는 **쓰는 순간**이 갈라지지 않게 할 뿐이다.
# 정작 터진 자리들은 전부 세 걸음이 열려 있었다: 등록부를 읽고 한 줄 붙여 쓰는 사이,
# 이력 색인을 읽고 판 하나 끼워 쓰는 사이, 만료 세션을 재고 지우는 사이. 둘 다
# 원자적으로 써도 **뒤엣것이 앞엣것을 통째로 덮는다** — 그래서 이 셋은 반창고 자리가
# 다를 뿐 한 뿌리다. 자리마다 다른 수를 쓰지 않고 여기 하나를 골라 다 같이 쓴다.
#
# 왜 os.mkdir 인가 — 저장소에 이미 선례가 있다(`history/version.py 판번호따기` 가 판
# 번호를 os.mkdir 의 배타성으로 잡는다). 잠그는 법이 둘이 되면 어느 것이 어느 것을
# 막는지 아무도 못 따진다. mkdir 은 같은 파일계 위에서 **스레드도 프로세스도** 가리지
# 않고 배타적이라 "서버가 여러 벌"인 경우까지 한 번에 덮는다. (fcntl.flock 은 프로세스가
# 죽으면 저절로 풀려 편하지만, 같은 프로세스 안 두 스레드가 각자 연 fd 는 서로 안
# 막는다 — 여기 주된 경합이 ThreadingHTTPServer 의 스레드끼리라 그 길은 못 쓴다.)
#
# 임자 표 — 잠금 방 안에 누가 쥐었는지 적고, 풀 때 그 표가 **내 것일 때만** 치운다.
# 묵은 잠금을 남이 깨고 새로 쥔 뒤에 내가 풀면 남의 잠금을 푸는 셈이 되기 때문이다.
#
# 실측(2026-08-07, 이 기계·APFS · scratchpad/rc/m_빗장.py):
#   · 잡고 놓기 한 벌(mkdir + 임자쓰기 + rmtree): 중앙 437µs · p99 3.3ms · 최대 17.8ms.
#     요청 하나가 조립 subprocess 에 쓰는 수백 ms 에 견주면 없는 값이라 캐시로 안 숨긴다.
#   · 실제로 **쥐고 있는** 시간(가장 나쁜 쪽으로 재려고 등록부에 문서 사례·658KB 를
#     쌓아 놓고 쟀다): 등록부 append 중앙 17.1ms·최대 87.3ms · 이력 보관 한 판 중앙
#     8.9ms·최대 18.1ms · 세션 끝내기 중앙 5.7ms·최대 29.0ms.
#     가장 긴 것이 87ms 이므로 묵힘초 60초는 그 **690배**다 — 살아 있는 임자를 깨는
#     일은 없고, 죽은 임자가 남긴 잠금은 1분이면 풀린다.
빗장꼬리 = ".잠금"
빗장기다림초 = 20.0        # 실측 최대 보유 87ms 의 230배 — 여기까지 기다렸으면 남이 죽은 것이다
빗장묵힘초 = 60.0          # 이보다 오래 안 놓인 잠금은 임자가 죽은 것으로 보고 깬다


class 못잠금(RuntimeError):
    """빗장을 못 잡았다 — **조용히 넘어가지 않는다**(구현계획.md 규칙 3).

    여기서 삼키면 읽고-쓰는 사이가 도로 열린 채로 200 ok 가 나간다. 그것이 이
    묶음의 공통 증상이라 부르는 쪽이 반드시 보게 만든다.
    """


def 빗장길(경로):
    """그 경로를 지키는 잠금 방. 파일 이름 옆에 `.잠금` 을 붙인 **디렉터리**다.

    옆에 두는 까닭 — 같은 파일계여야 배타성이 성립하고, 지키는 대상과 붙어 있어야
    나중에 사람이 봤을 때 무엇을 지키는 잠금인지 안다. `.잠금` 이 붙은 이름은
    등록부 glob(`*-docs.json`)·세션 열쇠꼴 검사·GET 화이트리스트 어디에도 안 걸린다.
    """
    return str(경로) + 빗장꼬리


class _빗장:
    def __init__(self, 경로, 기다림초=빗장기다림초, 묵힘초=빗장묵힘초, 필수=True):
        self.방 = 빗장길(경로)
        self.기다림초 = float(기다림초)
        self.묵힘초 = float(묵힘초)
        self.필수 = bool(필수)
        self.표 = None

    def _임자길(self):
        return os.path.join(self.방, "임자")

    def _묵었나(self):
        try:
            return (time.time() - os.path.getmtime(self.방)) > self.묵힘초
        except OSError:
            return False

    def __enter__(self):
        import uuid
        내표 = f"{os.getpid()}:{threading.get_ident():x}:{uuid.uuid4().hex[:8]}"
        벽 = os.path.dirname(os.path.abspath(self.방))
        if 벽:
            os.makedirs(벽, exist_ok=True)
        끝 = time.monotonic() + self.기다림초
        쉼 = 0.0005
        깬적 = False
        while True:
            try:
                os.mkdir(self.방)
            except FileExistsError:
                pass
            else:
                with open(self._임자길(), "w", encoding="utf-8") as f:
                    f.write(내표)
                self.표 = 내표
                return True
            if not 깬적 and self._묵었나():
                # 한 번만 깬다 — 서로 깨고 뺏는 고리를 안 만든다. 깬 사실은 반드시 남긴다.
                깬적 = True
                sys.stderr.write(f"[빗장] {self.묵힘초:.0f}초 넘게 안 놓인 잠금을 깹니다: "
                                 f"{self.방} (임자 프로세스가 죽은 것으로 봅니다)\n")
                import shutil
                shutil.rmtree(self.방, ignore_errors=True)
                continue
            if time.monotonic() >= 끝:
                if self.필수:
                    raise 못잠금(
                        f"다른 요청이 같은 것을 고치는 중이라 {self.기다림초:.0f}초를 "
                        f"기다렸는데도 차례가 안 왔습니다: {os.path.basename(self.방)} — "
                        f"잠시 뒤 다시 시도해 주세요")
                return False
            time.sleep(쉼)
            쉼 = min(쉼 * 2, 0.005)

    def __exit__(self, *a):
        if self.표 is None:
            return False
        import shutil
        try:
            with open(self._임자길(), encoding="utf-8") as f:
                지금 = f.read().strip()
        except OSError:
            지금 = ""
        if 지금 != self.표:
            # 내 잠금이 묵은 것으로 몰려 깨졌고 지금은 남이 쥐고 있다 — 그것까지 치우면
            # 남의 임계구역을 여는 셈이다. 치우지 않고 **말한다**(규칙 3).
            sys.stderr.write(f"[빗장] 내 잠금이 아니었습니다(깨진 뒤 남이 다시 쥠): "
                             f"{self.방} 내표={self.표} 지금={지금!r}\n")
            self.표 = None
            return False
        shutil.rmtree(self.방, ignore_errors=True)
        self.표 = None
        return False


def 빗장(경로, 기다림초=빗장기다림초, 묵힘초=빗장묵힘초, 필수=True):
    """`with 자료뿌리.빗장(파일경로):` — 그 파일을 읽고-고치고-쓰는 동안 남을 막는다.

    · `필수=True`(기본): 못 잡으면 `못잠금` 으로 **선다**. 부르는 쪽은 그 사실을
      응답에 실어야 한다(조용한 실패 금지).
    · `필수=False`: 못 잡으면 `False` 를 준다 — "남이 이미 그 일을 하고 있으니 나는
      건너뛴다"가 맞는 자리(만료 세션 청소)에서만 쓴다.
    """
    return _빗장(경로, 기다림초, 묵힘초, 필수)


def 문서수정시각():
    """문서 정본의 `_수정시각` — **마이크로초까지** 적는다.

    왜 여기 있나 — 이 값은 낙관적 잠금의 **표**다. 적는 곳(workspace/api.py 새문서 ·
    workspace/apply_edit_any.py)과 견주는 곳(apply_edit_any)이 갈라져 있어서, 자릿수를
    한쪽만 고치면 잠금이 조용히 무력해진다. 형식을 한 곳에 둔다.

    왜 초로는 모자란가(2026-08-07 실측) — 예전 값은 `%Y-%m-%dT%H:%M:%S` 였다. 같은
    문서에 동시 저장 2건을 10회 돌리면 **9회가 둘 다 200 ok** 였다: 이긴 쪽이 적은 새
    시각이 진 쪽이 본 시각과 **글자까지 같아서**(같은 초) 진 쪽의 검사가 통과했다.
    빗장으로 순서를 세워도 표가 안 바뀌면 잠금이 아니다. 빗장이 쓰기를 줄 세우므로
    두 쓰기 사이가 벌어진다 — 빗장 안에서 이 값을 2000번 뽑아 보니 **겹친 것 0개**,
    이웃 간격 최소 283µs·중앙 495µs 였다(scratchpad/rc/m_빗장.py ⑤).

    화면은 안 깨진다 — `workspace/app.html:803` 이 `slice(0,16)`(분까지)만 보여 주고
    정렬은 앞자리가 고정폭이라 글자 비교로 그대로 맞는다.

    **구성 설계(plan)의 `_수정시각` 은 초 단위 그대로 둔다** — buildplan/render_skeleton.py
    가 산출물 mtime(초 단위)과 **글자로 견주므로**, 자릿수가 늘면 같은 초에
    "다시 만들어야 합니다" 헛경고가 뜬다.
    """
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")


def 코드길(*조각):
    """코드뿌리 밑의 경로 — CSS·조립기·온톨로지처럼 **우리가 배포하는 것**."""
    return os.path.join(코드뿌리(), *조각)


# ── 등록부(정본) ────────────────────────────────────────────────────────

def 등록부(장르):
    """`build/<장르>-docs.json` — 문서 정본이 담기는 곳."""
    return 길("build", f"{장르}-docs.json")


def 등록부들():
    """등록부 전수 — **세어서** 얻는다(구현계획.md 규칙 2, 손목록 금지)."""
    return sorted(glob.glob(길("build", "*-docs.json")))


def 등록부이름(경로):
    return os.path.basename(경로)[:-len("-docs.json")]


# ── 산출물·관측·자산 ────────────────────────────────────────────────────

def 산출물뿌리():
    return 길("build", "samples")


def 산출물(키, 끝="html"):
    return os.path.join(산출물뿌리(), f"{키}.{끝}")


def 관측뿌리():
    return 길("build", "observed")


def 자산뿌리():
    return 길("build", "assets")


# ── 구성 설계(빌드플랜) ──────────────────────────────────────────────────

def 플랜뿌리():
    return 길("buildplan")


def 플랜(plan_id):
    return os.path.join(플랜뿌리(), f"plan-{plan_id}.json")


def 플랜들():
    return sorted(glob.glob(os.path.join(플랜뿌리(), "plan-*.json")))


def 승인화면길():
    return os.path.join(플랜뿌리(), "plan.html")


def 골격뿌리():
    return os.path.join(플랜뿌리(), "skeletons")


def 골격편집뿌리():
    return os.path.join(골격뿌리(), "edit")


# ── 작업 공간 ───────────────────────────────────────────────────────────

def 작업뿌리():
    return 길("workspace")


def 편집화면뿌리():
    return os.path.join(작업뿌리(), "editors")


def 받은것뿌리():
    """올린 파일이 놓이는 곳(inbox)."""
    return os.path.join(작업뿌리(), "inbox")


def 요청뿌리():
    """AI 대기열(requests)."""
    return os.path.join(작업뿌리(), "requests")


def 미결어긋남길():
    """답을 아직 못 받은 되묻기(어긋남 물음)가 사는 곳 (구현계획.md §3 WP-S3).

    왜 자료이고 왜 **세션 밑**인가 — 물음에는 자료의 실제 수치·문장 조각이 들어 있다
    (그건 문서 내용이다). 세션 뿌리 밑에 있어야 세션이 끝날 때 같이 지워지고
    (출시계획 1-6 A안: 내용은 안 남긴다 — 규칙 차원 기록은 규칙적기가 따로 한다),
    남의 세션 물음을 읽거나 남 대신 답하는 길도 경로 차원에서 막힌다(일감뿌리와 같은 논리).
    """
    return os.path.join(작업뿌리(), "미결어긋남.json")


def 일감뿌리():
    """비동기 작업(job) 한 건의 **진행 기록**이 사는 곳 (구현계획.md §3 WP-S4).

    왜 자료이고, 왜 **세션 밑**인가 — 일감 하나에는 그 세션이 시킨 일의 이름·인자·
    결과가 통째로 들어 있다(조판게이트 로그에는 그 세션 문서의 넘침 자리가, 내보내기
    결과에는 산출물 경로가 붙는다). 기본 뿌리에 두면 작업 id 하나로 남의 세션 결과를
    읽게 된다 — 그건 격리가 아니라 구멍이다(구현계획.md 규칙 5). 여기를 지나면
    세션 B 가 세션 A 의 id 를 물어도 **자기 방에 그 파일이 없어서** 못 본다.

    이름을 `작업…` 으로 안 지은 까닭: 이 저장소에서 '작업'은 등록부에 적힌 **일의
    종류**(조립·저장·조판게이트…)를 가리키고 `작업뿌리()` 는 workspace 디렉터리를
    이미 차지하고 있다. 돌고 있는 그 한 건은 '일감'이라 부른다.
    """
    return os.path.join(작업뿌리(), "jobs")


# ── 이력 ────────────────────────────────────────────────────────────────

def 이력뿌리():
    return 길("history")


def 이력방(key):
    return os.path.join(이력뿌리(), key)


def 기준기록길():
    return os.path.join(이력뿌리(), "기준.jsonl")


# ── 피드백 ──────────────────────────────────────────────────────────────

def 피드백뿌리():
    return 길("feedback")


def 편집기록길():
    return os.path.join(피드백뿌리(), "edit-log.jsonl")


def 피드백백업뿌리():
    return os.path.join(피드백뿌리(), "backups")


def 원장길():
    """피드백 원장 — **코드뿌리에 둔다.**

    세션이 만드는 자료가 아니라 우리가 재서 배운 규칙이고, 코드는 읽기만 한다
    (부록/출시차단감사.md §2 의 마지막 줄). 세션마다 갈리면 배운 것이 흩어진다.
    """
    return 코드길("feedback", "ledger.json")


# ── 뿌리 세우기 ─────────────────────────────────────────────────────────

# 자료가 사는 디렉터리 전수 — 부록/출시차단감사.md §2 "파일 쓰기 전수 목록" 에서 왔다.
자료디렉터리 = (
    ("build",), ("build", "samples"), ("build", "observed"), ("build", "assets"),
    ("buildplan",), ("buildplan", "skeletons"), ("buildplan", "skeletons", "edit"),
    ("workspace",), ("workspace", "editors"), ("workspace", "inbox"),
    ("workspace", "requests"), ("workspace", "jobs"),
    ("history",),
    ("feedback",), ("feedback", "backups"),
)


def _잇기(원본, 놓을곳):
    """코드 자산을 자료뿌리 밑으로 이어 준다. 심링크가 안 되면 복사한다.

    **이미 있으면 그냥 둔다.** `lexists` 로 한 번 보고 나서도 심링크가
    FileExistsError 로 설 수 있다 — serve.py 는 ThreadingHTTPServer 라, 빈 뿌리에
    첫 요청 둘이 같이 들어오면 두 스레드가 같은 다리를 동시에 놓는다. 그때 예전
    코드는 복사로 넘어가 `SameFileError` 로 죽었고, 그 예외가 **요청 응답에 실려**
    나갔다(2026-08-07, ③ 실측 중 발견).
    """
    if os.path.lexists(놓을곳):
        return
    try:
        os.symlink(원본, 놓을곳)
        return
    except FileExistsError:
        return                       # 옆 스레드가 방금 놓았다 — 그게 맞는 상태다
    except OSError:
        pass
    import shutil
    try:
        if os.path.isdir(원본):
            shutil.copytree(원본, 놓을곳)
        else:
            shutil.copy2(원본, 놓을곳)
    except (FileExistsError, shutil.SameFileError):
        pass


_세우기잠금 = threading.Lock()

# 뿌리를 다 세웠다는 **표**. 메모(`_세운것`)만으로는 못 믿는다 — 적대리뷰 ②⑤.
#
# 무엇이 틀렸었나: `_세운것` 은 프로세스가 죽을 때까지 안 비워지는데, 세션 뿌리는
# **바깥에서 사라진다**(세션.끝내기 의 마감·만료 청소). 사라진 뒤 같은 쿠키로 돌아오면
# `활동적기()` 가 `마지막활동` 파일만 되살리고 `_세우기()` 는 메모를 보고 곧장 돌아가서
# 등록부도 CSS 다리도 다시 안 세웠다. 세션은 살아 있는데(열쇠 유효·isdir·mtime 신선)
# 안이 텅 빈 껍데기가 되고, 사용자는 쿠키를 손으로 지우기 전엔 아무것도 못 만든다
# (오류 문구까지 거짓말을 했다: 장르는 멀쩡한데 "모르는 장르: samples (있는 것: [])").
#
# 고침: 다 세운 자리에 표 파일을 하나 남기고, 빠른 길은 **메모 ∧ 표** 일 때만 탄다.
# 세션방이 통째로 사라지면 표도 같이 사라지므로 다음 요청이 저절로 다시 세운다.
# 값(2026-08-07 실측): 표를 보는 `os.path.exists` 한 번이 3.31µs, `뿌리()` 는 기본뿌리와
# 세션뿌리를 각각 보므로 +6.6µs — `뿌리()` 한 번이 3.6µs → 10µs 가 된다. 요청 하나가
# 조립 subprocess 하나에 쓰는 수십 ms 에 견주면 없는 값이라 캐시로 숨기지 않는다.
세움표 = ".세움표"


def _세움표길(뿌리경로):
    return os.path.join(뿌리경로, 세움표)


def _다세웠나(뿌리경로):
    if 뿌리경로 not in _세운것:
        return False
    if os.path.abspath(뿌리경로) == os.path.abspath(코드뿌리()):
        return True                  # 현행 위치 — 세운 것이 없으니 표도 없다
    return os.path.exists(_세움표길(뿌리경로))


def _세우기(뿌리경로):
    """빈 뿌리를 쓸 수 있는 상태로 만든다. **세워져 있는지는 매번 표로 확인한다.**

    잠금을 거는 까닭 — 스레드 둘이 같은 빈 뿌리를 동시에 세우면 디렉터리·등록부·
    다리를 서로 밟는다(위 `_잇기` 주석의 그 사고). 잠금 안에서 한 번 더 보는 까닭 —
    앞 스레드가 다 세우고 표를 남겼으면 두 번째는 다시 세울 필요가 없다.
    """
    if _다세웠나(뿌리경로):
        return
    with _세우기잠금:
        if _다세웠나(뿌리경로):
            return
        _세우기하나(뿌리경로)


def _세우기하나(뿌리경로):
    코드 = 코드뿌리()
    if os.path.abspath(뿌리경로) == os.path.abspath(코드):
        _세운것.add(뿌리경로)
        return                       # 현행 위치 — 세울 것이 없다(바이트 하나 안 달라진다)
    try:
        for 조각 in 자료디렉터리:
            os.makedirs(os.path.join(뿌리경로, *조각), exist_ok=True)
    except OSError as e:
        raise RuntimeError(
            f"자료뿌리를 세우지 못했습니다: {뿌리경로} — {e}\n"
            f"  환경변수 {환경변수} 가 가리키는 곳에 쓸 수 있어야 합니다. "
            f"(비우면 현행 위치인 {코드} 를 씁니다)") from e

    # 등록부는 **빈 배열**로 선다. 이름 목록은 손으로 안 적고 코드뿌리에 실제로 있는
    # 등록부 파일에서 센다 — 장르를 늘렸을 때 여기만 빠지는 그 함정(genres.py 머리말)
    # 을 다시 밟지 않으려고.
    본 = sorted(glob.glob(os.path.join(코드, "build", "*-docs.json")))
    if not 본:
        raise RuntimeError(
            f"코드뿌리({코드})에 등록부(build/*-docs.json)가 하나도 없습니다 — "
            f"자료뿌리를 세울 본을 찾지 못했습니다")
    for p in 본:
        새 = os.path.join(뿌리경로, "build", os.path.basename(p))
        if not os.path.exists(새):
            원자쓰기(새, "[]")

    # 코드 자산(서식·스크립트·글꼴)으로 가는 다리 — 위 '다리_확장자' 주석 참고
    for 하위 in ("build", "buildplan"):
        원본방 = os.path.join(코드, 하위)
        if not os.path.isdir(원본방):
            continue
        for 이름 in sorted(os.listdir(원본방)):
            원본 = os.path.join(원본방, 이름)
            if os.path.isfile(원본) and 이름.endswith(다리_확장자):
                _잇기(원본, os.path.join(뿌리경로, 하위, 이름))
        for 이름 in 다리_디렉터리.get(하위, ()):
            원본 = os.path.join(원본방, 이름)
            if os.path.isdir(원본):
                _잇기(원본, os.path.join(뿌리경로, 하위, 이름))
    # 표는 **맨 마지막**에 남긴다 — 중간에 죽으면 표가 없어 다음 요청이 다시 세운다.
    원자쓰기(_세움표길(뿌리경로),
          f"세운때 {time.strftime('%Y-%m-%dT%H:%M:%S')} pid {os.getpid()}\n"
          f"코드뿌리 {코드}\n"
          f"이 표가 있어야 '이 자료뿌리는 다 세웠다'로 봅니다. 지우면 다음 요청이 "
          f"디렉터리·등록부·서식 다리를 다시 세웁니다(적대리뷰 ②⑤).\n")
    _세운것.add(뿌리경로)


def 세우기():
    """빈 뿌리를 손으로 세운다(자료뿌리()가 알아서 부르므로 보통은 필요 없다)."""
    return 뿌리()


# ── 코드뿌리의 이웃 모듈을 순환 없이 불러오는 길 ─────────────────────────

_모듈잠금 = threading.RLock()
_다올린것 = set()


def 모듈(이름, 어디="build"):
    """코드뿌리 `<어디>/<이름>.py` 를 sys.path 를 건드리지 않고 불러온다.

    왜 여기 있나 — `history/version.py` 처럼 build/ 가 sys.path 에 없는 자리에서도
    `genres` 같은 공용 모듈을 써야 한다. 호출마다 `sys.path.insert` 를 더 심는 것이
    부록 A-1 이 지목한 병이라(장수 프로세스에서 무한 증식) 그 길은 안 쓴다.
    정리(패키지화)는 WP-S9 몫이다.

    **잠근다**(2026-08-07, WP-S2 ③ 실측 중 발견): `sys.modules[이름] = m` 을
    `exec_module` **전에** 놓아야 자기참조 import 가 돌아간다. 그래서 그 사이에
    들어온 다른 스레드는 **아직 안 채워진 모듈**을 받아 갔다 —
    `AttributeError: module 'genres' has no attribute '등록부'` 로 터진다.
    serve.py 는 ThreadingHTTPServer 라 이 창이 실제로 열린다(빈 뿌리에 동시에
    조립 요청이 둘 오면 재현된다). 그래서 **다 올라간 것만** 빠른 길로 돌려준다.
    """
    if 이름 in _다올린것:
        import sys
        return sys.modules[이름]
    import importlib.util
    import sys
    with _모듈잠금:
        if 이름 in _다올린것:
            return sys.modules[이름]
        있는것 = sys.modules.get(이름)
        if 있는것 is not None:            # 평소 import 로 이미 올라와 있는 것
            _다올린것.add(이름)
            return 있는것
        사양 = importlib.util.spec_from_file_location(이름, 코드길(어디, f"{이름}.py"))
        m = importlib.util.module_from_spec(사양)
        sys.modules[이름] = m
        try:
            사양.loader.exec_module(m)
        except Exception:
            sys.modules.pop(이름, None)   # 반쯤 올라간 것을 남기지 않는다
            raise
        _다올린것.add(이름)
        return m


if __name__ == "__main__":
    # 셸(build/render_verify.sh)도 경로를 여기서 물어본다 — 산출물 자리를 셸에 또
    # 적으면 자료뿌리를 옮겼을 때 그 한 곳만 코드뿌리를 본다(조용한 갈라짐).
    import json
    import sys
    본 = {"코드뿌리": 코드뿌리(), "자료뿌리": 뿌리(), "환경변수": 환경변수,
         "기본자료뿌리": 기본뿌리(), "세션": 세션열쇠(), "세션환경변수": 세션환경변수,
         "세션들": 세션들뿌리(), "설정": 설정길(), "후보": 후보뿌리(),
         "코퍼스": 코퍼스뿌리(),
         "등록부": [os.path.relpath(p, 뿌리()) for p in 등록부들()],
         "산출물": 산출물뿌리(), "이력": 이력뿌리(), "요청": 요청뿌리(),
         "일감": 일감뿌리(),
         "받은것": 받은것뿌리(), "편집화면": 편집화면뿌리(), "플랜": 플랜뿌리(),
         "관측": 관측뿌리(), "자산": 자산뿌리(), "피드백": 피드백뿌리(),
         "원장": 원장길()}
    if len(sys.argv) > 1:
        이름 = sys.argv[1]
        if 이름 == "등록부길":
            print("\n".join(등록부들()))
        elif 이름 in 본:
            print(본[이름])
        else:
            sys.stderr.write(f"모르는 이름: {이름} (있는 것: {', '.join(본)}, 등록부길)\n")
            sys.exit(2)
    else:
        json.dump(본, sys.stdout, ensure_ascii=False, indent=1)
        print()
