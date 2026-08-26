#!/usr/bin/env python3
"""편집 화면을 띄우고 **저장을 받는** 서버.

왜 만들었나(2026-08-04): 지금까지 편집기는 localStorage 에만 저장하고,
사람이 채팅에 "다 고쳤어요"라고 말하면 Claude 가 브라우저에서 그 값을 읽어
정본에 반영했다. 두 가지가 걸렸다.
  · 사람이 한 번 말해 줘야 한다 — 저장했는데 반영이 안 된 상태가 생긴다
  · **Claude 가 브라우저를 조작할 수 있어야 한다** — 그 능력이 없는 환경에서는
    편집 고리가 통째로 끊긴다(원격 MCP 로 옮길 때 바로 걸린다)

이 서버가 POST 를 받아 그 자리에서 반영한다. 반영·이력·재조립은 이미 있는
workspace/apply_edit_any.py 가 다 한다 — 여기는 **부르는 길**일 뿐이다.

  GET  /api                작업 목록 — 이 서버가 할 수 있는 일
  GET  /api/<이름>?...      읽기 작업 (지식·문서목록·문서·이력·유형·개인)
  POST /api/<이름>          쓰기 작업 (저장·조립·문체검사·조판게이트·되돌리기…)
  POST /save · /upload     옛 이름 — 본문을 그대로 보내는 편집기·업로더가 쓴다.
                           아래 `옛경로` 표가 등록부 인자로 옮겨 같은 길로 넘긴다.
  GET  그 밖               정적 파일(python -m http.server 와 같다)

긴 일(조판게이트 최대 900초·내보내기·LLM)은 **뒤에 걸어야 한다** — HTTP 한 방으로
받으면 브라우저·프록시가 먼저 끊는다. `작업시작`/`작업상태` 두 작업이 그 길이고,
그것 역시 여기 특별한 자리가 없다(등록부의 작업 하나일 뿐이다, WP-S4).

**작업 목록은 여기 없다.** workspace/api.py 한 곳에 있고 이 서버는 그것을 열 뿐이다 —
문이 셋(스킬·MCP·웹앱)이라 목록이 갈라지면 하나 늘릴 때 나머지에 빠뜨린다.

사용: python3 workspace/serve.py [포트] [--host 주소]     (기본 127.0.0.1:8642)
      바인드 주소는 환경변수 문서지능_바인드 로도 줄 수 있다(--host 가 우선).
"""
import base64
import hmac
import json
import os
import posixpath
import re
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mimetypes
import api
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# PWA 매니페스트 MIME — SimpleHTTPRequestHandler.guess_type 가 mimetypes 로 폴백하므로
# 여기 등록해 두면 manifest.webmanifest 가 올바른 타입으로 나간다(브라우저가 매니페스트로 인식).
mimetypes.add_type("application/manifest+json", ".webmanifest")

# 이 프로세스가 처리하는 모든 api.부르기 호출은 **늘 로컬에서** 실행돼야 한다.
# 문서지능_서버 가 (예컨대 이 서버를 띄운 셸에 남아 있어서) 이 프로세스의 환경에도
# 설정돼 있으면, 이 서버가 요청을 처리하다가 api.부르기 를 부를 때 자기 자신을
# 다시 원격으로 호출하는 고리가 생긴다(구현계획.md §3 WP-S1"무한 루프 함정" — serve.py
# 는 api 를 직접 import 해 쓰므로 서버 프로세스=코어 그 자체다). 그래서 시작하는
# 순간 지워 둔다 — "코어" 는 언제나 이 프로세스이지, 이 프로세스가 가리키는 또
# 다른 서버가 아니다.
os.environ.pop("문서지능_서버", None)
# env 뿐 아니라 **conf 파일**(서버.conf·정책서버.conf)로도 위임이 켜질 수 있으니(api._서버설정),
# 코어임을 못 박는 플래그를 켠다 — 이게 있으면 api 의 두 설정 함수가 무조건 None 을 돌려
# 로컬 실행한다. 스킬 배포 트리가 실수로 서버에 섞여도 자기호출 고리가 안 생긴다(fail-safe).
os.environ["문서지능_로컬강제"] = "1"
# 웹앱임을 못 박는다 — api 의 빌드플랜 승인 게이트 중 'plan_id **요구**'는 UI 없는 플러그인
# 전용이다(웹앱은 화면으로 설계·승인을 강제하고 '자료 없이 재등록' 같은 정당한 무플랜 경로가
# 있다). 이 플래그가 있으면 api.새문서 가 plan_id 요구를 건너뛴다(승인 확인은 그대로 한다).
os.environ["문서지능_웹앱"] = "1"
# 플러그인 로컬 편집기 서버 — 코딩에이전트(Claude Code·Codex·Cursor)가 편집 단계에서 이 서버를
# 127.0.0.1 로 잠깐 띄우고(편집기열기 op) 사용자의 실제 브라우저로 편집기를 연다. 이때는 **쿠키
# 세션 격리를 끈다** — MCP·CLI 와 같은 세션 뿌리를 봐야 /save·이력이 방금 MCP 가 만든 문서를
# 찾는다(MCP stdio 는 세션 없이 기본 뿌리, 반면 쿠키별 방으로 갈리면 빈 방을 보고 문서를 못 찾는다).
# A1 웹앱은 이 플래그 없이 떠서 예전대로 쿠키 세션으로 여러 사람을 격리한다.
단일세션 = bool(os.environ.get("문서지능_단일세션"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 코드뿌리

# 자료뿌리는 api 가 이미 불러 둔 그 모듈을 그대로 쓴다 — 두 벌을 들면 서버와 코어가
# 서로 다른 뿌리를 볼 수 있다(WP-S2 ①).
자료뿌리 = api.자료뿌리
세션 = 자료뿌리.모듈("세션")

# ── 익명 세션 (WP-S2 ②) ──────────────────────────────────────────────────
# 로그인이 없다(출시계획 1-1). 그래서 **쿠키 하나가 곧 신분**이고, 그 쿠키가 가리키는
# 세션 디렉터리가 그 사람의 전부다. 문서·이력·산출물·inbox·요청이 다 그 밑으로 간다.
#
# 쿠키 이름을 ASCII 로 둔 까닭 — 작업 이름은 한국어가 정본이지만 **선로 위의 열쇠는
# 영문**이 이 저장소의 규칙이다(구현계획.md 규칙 8, 한글 열쇠로 세 번 밟았다).
# 게다가 파이썬 `http.cookies` 의 열쇠 패턴은 `re.ASCII` 라 한글 이름은 파싱 자체가
# 안 된다. 다만 사람이 손으로 시험할 때 쓰는 한국어 이름도 **읽기는** 받아 준다
# (아래 `_쿠키()` 가 헤더를 직접 가른다) — 받아 주되 검증은 똑같이 건다.
쿠키이름 = 자료뿌리.세션쿠키                     # "mjsid" — 이름은 자료뿌리 한 곳에 있다
쿠키별명 = (쿠키이름, 자료뿌리.세션환경변수)     # ("mjsid", "문서지능_세션")
쿠키수명초 = 60 * 60 * 24


class 나쁜쿠키(Exception):
    pass


# ── 내용 보안 정책(CSP) ─────────────────────────────────────────────────
# 왜 필요한가 — 로그인이 없어서 **쿠키 하나가 곧 신분**이다(위 주석). 스크립트가
# 한 줄이라도 실행되면 그 세션 전체가 남의 것이 된다. 쿠키는 HttpOnly 로 잠갔지만
# 그것만으로는 "그 사람의 브라우저에서 그 사람 권한으로 저장·삭제를 부르는" 길이
# 안 막힌다. CSP 는 조립기·화면 쪽 새니타이저(assemble.norm_rich 등)가 한 군데
# 새더라도 실행을 막는 **둘째 자물쇠**다.
#
# 줄마다 왜 그 값인지 —
#   default-src 'self'         : 기본은 우리 서버 것만.
#   script-src  'self' 'unsafe-inline'
#       편집 화면(render_editor_any.py)·조종석·app.html 이 **인라인 <script> 로**
#       돌아간다. 지금 구조에서 이걸 빼면 웹앱이 통째로 안 뜬다. nonce/해시로 조이는
#       것은 화면 배선을 다시 짜는 일이라 F1 몫이다. 다만 인라인이 허용돼도
#       **바깥 주소로는 못 나간다**(default-src 'self') — 훔친 것을 보낼 길이 막힌다.
#   style-src   'self' 'unsafe-inline'
#       조립기가 제목·요약·항목에 `style="font-size:…pt"` 를 직접 붙인다
#       (부록/시각변수전수.md — 화면읽기가 재는 값이 거기 있다). 인라인 style 을
#       막으면 산출물의 글자 크기가 통째로 무너진다.
#   img-src     'self' data:   : 자산 png/svg 와, 편집기가 만드는 data: 미리보기.
#   connect-src 'self' https://api.anthropic.com
#       모델 호출은 **브라우저가 직접** 한다(출시계획 1-3 ①, app.html:659-665 의
#       `anthropic-dangerous-direct-browser-access`). 키가 서버에 안 닿게 하려고
#       고른 길이라, 이 한 곳만 열어 둔다.
#   frame-ancestors 'none' · base-uri 'none' · form-action 'self'
#       클릭재킹과 <base> 바꿔치기를 막는다. CSP 에는 있는데 여기 안 적으면
#       default-src 가 안 덮어 주는 지시어들이다.
CSP = ("default-src 'self'; "
       "script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; "
       "font-src 'self' data:; "   # self-host 폰트(app.html)+data URI 내장 폰트(promo/landing.html) 둘 다
       # 브라우저 BYOK(사용자 키로 직접 호출) — 앤트로픽 외 OpenAI 호환 제공자도 연다.
       # 키가 localStorage 에 있어 blanket https: 는 XSS 유출 위험이 커, **알려진 LLM 호스트만** 허용.
       # 목록에 없는 커스텀 제공자를 쓰려면 여기 호스트를 더한다(정본 한 곳).
       "connect-src 'self' https://api.anthropic.com https://openrouter.ai "
       "https://api.openai.com https://api.groq.com https://generativelanguage.googleapis.com "
       "https://api.mistral.ai https://api.deepseek.com https://api.together.xyz "
       "https://api.perplexity.ai https://api.featherless.ai; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

안전헤더 = (
    ("Content-Security-Policy", CSP),
    # 브라우저가 Content-Type 을 제 마음대로 다시 알아맞히면, 올린 파일이 HTML 로
    # 해석돼 우리 출처에서 실행된다. 그 추측을 끈다.
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
)


# ── 관리자 열쇠 게이트 (WP-S5 · 출시계획 3-4) ──────────────────────────────
# 관리자 면(화면·API)은 **환경변수 열쇠 하나** 뒤에 있다. 계정 시스템을 만들지 않는다.
# 열쇠 없이/틀리게 들어오면 막는다 — 화면도 API도(출시계획 3-4 완료 기준).
#
# 왜 여기(HTTP 문)에 두나 — 화면 GET 과 관리자 작업 POST 가 **한 문**을 지나므로,
# 게이트도 한 자리다. 어느 작업이 관리자 전용인가는 **등록부의 `관리자` 플래그**에서
# 온다(api.py) — serve.py 에 이름으로 또 적지 않는다(이름별 분기 금지: 규칙 2).
#
# 열쇠는 **환경변수에서만** 온다(코드·파일에 안 박는다). 비교는 **상수시간**
# (hmac.compare_digest) — 틀린 자리를 타이밍으로 재는 공격을 막는다. 열쇠가 비어
# 있으면(관리자 면 미설정) **fail closed** — 어떤 열쇠로도 못 들어온다(빈 열쇠로 빈
# 설정을 뚫는 길을 아예 안 연다). 이 열쇠는 로그·응답·화면 어디에도 안 남긴다.
#
# 화면은 왜 Basic Auth 인가 — 브라우저는 **화면 이동에 커스텀 헤더를 못 붙인다**.
# 그래서 화면(admin.html)은 `WWW-Authenticate: Basic` 으로 브라우저 기본 열쇠 창을
# 띄운다(사용자이름은 무시, 비밀번호 자리에 열쇠). 관리자 면 JS 가 API 를 부를 때는
# `X-Admin-Key` 헤더로도 받는다 — 둘 다 같은 상수시간 비교를 지난다.
관리자열쇠환경변수 = "문서지능_관리자열쇠"
관리자화면 = "/workspace/admin.html"
# Basic Auth realm — **ASCII 여야 한다**. HTTP 헤더 값은 latin-1 로 인코딩되므로 한글을
# 넣으면 send_header 가 UnicodeEncodeError 로 죽고 연결이 그냥 끊긴다(구현계획.md 규칙 8:
# 선로 위의 열쇠·값은 영문. 이 게이트를 만들며 실제로 밟아 고쳤다 — 한글 realm 은 401 을
# 내보내다 서버가 터져 클라이언트가 RemoteDisconnected 를 받았다).
관리자영역 = "Munseo Jineung Admin"


def 관리자열쇠설정됨():
    """관리자 열쇠 — **환경변수에서만**. 비었으면 관리자 면 전체가 잠긴다(fail closed)."""
    return (os.environ.get(관리자열쇠환경변수) or "").strip()


# ── GET/HEAD 화이트리스트 ─────────────────────────────────────────────────
# 왜 만들었나(2026-08-07, WP-X1 — B-1 고침): `directory=ROOT` 로 SimpleHTTPRequestHandler
# 를 쓰면 ROOT 전체가 무인증 정적 서빙된다 — build/*-docs.json(전 문서 정본) ·
# workspace/inbox(업로드 원본) · workspace/requests(요청 원문) · history(전 판) 가
# 전부 GET 한 번으로 열리고, 디렉터리 목록까지 났다(구현계획-부록/출시차단감사.md B-1).
#
# 아래 목록은 손으로 어림잡지 않고, 웹앱(app.html·editors)이 실제로 참조하는 경로를
# grep 으로 센 결과다(2026-08-07; 조종석 workspace.html 은퇴 2026-08-11). 손목록 금지
# (구현계획.md 규칙 2) — 다시 셀 때는 이 명령들을 그대로 쓰면 된다:
#   grep -hoE '(src|href)=["\x27][^"\x27]*["\x27]' workspace/app.html \
#       workspace/editors/*.html buildplan/skeletons/*.html buildplan/skeletons/edit/*.html
#     → workspace/app.html 자신 · workspace/editors/*.html ·
#       build/*.css(6종) · build/*.js(4종: audit·gmseal·jachigan·svgfig) ·
#       build/assets/*.png · buildplan/skeleton.css · buildplan/skeletons/*.html ·
#       buildplan/skeletons/edit/*.html
#   grep -hoE 'build/samples/[^"\x27? ]*' workspace/app.html workspace/editors/*.html
#     → build/samples/<key>.{html,pdf,hwpx,txt} (링크) — 여기에 api.py 의 내보내기()
#       (workspace/api.py:575-643) 가 낼 수 있는 json·md 두 형식을 더한다(app.html:717-726
#       이 그 응답의 "경로" 를 그대로 내려받는다)
#   grep -n '@font-face' -A3 build/tokens.css → build/fonts/*.{woff2,ttf}
#   이력 링크(history/<key>/기록.html)는 조종석에서만 걸렸었다 — 은퇴로 링크 없음(파일은 남음).
#
# 새 화면·새 산출 형식이 생기면 이 목록에 안 잡히고 그냥 404가 난다 — 그게 맞다
# (규칙 3, 조용한 실패 금지). 화이트리스트를 늘릴 땐 이 grep 을 다시 돌려서 늘린다.
#
# **뿌리가 둘이다**(2026-08-07, WP-S2 ①): 같은 URL 이라도 CSS·JS·app.html 은 **코드**라
# 코드뿌리에서 열고, 산출물·편집 화면·골격·이력 화면은 **자료**라 자료뿌리에서 연다.
# 여기를 코드뿌리 하나로 두면 자료뿌리를 옮겼을 때 웹앱이 **옛 산출물을 보여 주면서
# 정상으로 보인다** — 조용한 실패라 아무도 못 알아챈다. 그래서 줄마다 뿌리를 적는다.
GET_화이트리스트 = [
    ("코드", re.compile(r"^/workspace/app\.html$")),
    ("코드", re.compile(r"^/promo/landing\.html$")),   # 홍보 랜딩(자체완결) — 루트('/')가 여기로 온다

    # WP-F1 — 앱 셸 토큰·아이콘. app.html·편집기(workspace/editors/ 와
    # buildplan/skeletons/edit/ 양쪽)가 모두 이 두 파일을 상대경로로 참조한다(어느
    # 경로에서 출발해도 브라우저가 정규화하면 여기 이 URL 하나로 모인다). tokens.css 와
    # 함께 **코드**다 — 세션마다 달라지는 자료가 아니라 우리가 배포하는 디자인 소스.
    ("코드", re.compile(r"^/workspace/ui-tokens\.css$")),
    ("코드", re.compile(r"^/workspace/icons\.svg$")),
    # PWA — 바탕화면/홈 설치. app.html 이 참조한다(매니페스트·서비스워커). 서비스워커는
    # /workspace/ 범위(scope)로 등록된다(이 경로에 있으니까). 둘 다 세션 무관 **코드**다.
    ("코드", re.compile(r"^/workspace/manifest\.webmanifest$")),
    ("코드", re.compile(r"^/workspace/sw\.js$")),
    ("코드", re.compile(r"^/workspace/약관\.html$")),   # 이용약관·개인정보 처리방침(공개 문서, 껍데기)

    # F1 v1.1 재디자인 — 실제 브랜드 로고 자산(design-app-v1.1/assets/brand 원본 PNG):
    # brand-mark.png=뇌+문서 아이콘(topbar), app-icon-primary.png=딥블루 앱아이콘(히어로),
    # logo-light.png=밝은 배경 정사각 로고. app.html 이 <img> 로 참조한다. 손으로 다시
    # 그리지 않고 브랜드 자산 원본을 그대로 낸다(색은 이미지 안에만 있어 앱 파일 hex 검사와
    # 무관). ui-tokens·icons 와 같은 **코드**(배포 디자인 소스)다.
    ("코드", re.compile(r"^/workspace/brand/[^/]+\.(svg|png)$")),
    # WP-F1 마무리 — 헤딩용 self-host 폰트(Noto Sans KR 700-900 서브셋). CSP font-src 가
    # 'self' data: 라 자기 출처 폰트 파일도, promo/landing.html 의 data: URI 내장 폰트도 통과한다
    # (font-src 를 안 적으면 default-src 'self' 를 상속해 data: 내장 폰트가 막혔었다 — '26-08-17 고침).
    # 이 화이트리스트가 막던 것은 CSP 가 아니라 GET 자체다(위 ui-tokens.css·icons.svg 와 같은 이유).
    ("코드", re.compile(r"^/workspace/fonts/[^/]+\.(woff2?|ttf|otf)$")),
    ("자료", re.compile(r"^/workspace/editors/[^/]+\.html$")),
    # build/samples 산출물 — 조립 결과(html)·내보내기 4형식(pdf·hwpx·json·md)·시행문 텍스트(txt)
    ("자료", re.compile(r"^/build/samples/[^/]+\.(html|pdf|hwpx|json|md|txt)$")),
    ("코드", re.compile(r"^/build/[^/]+\.css$")),              # 장르별 CSS 6벌
    ("코드", re.compile(r"^/build/[^/]+\.js$")),               # 편집기가 쓰는 JS 4벌
    ("코드", re.compile(r"^/build/fonts/[^/]+\.(woff2?|ttf|otf)$")),   # tokens.css @font-face
    ("자료", re.compile(r"^/build/assets/[^/]+\.(png|svg)$")),  # 이미지 자산(사용자 첨부에서 잘라 낸 것)
    ("코드", re.compile(r"^/buildplan/skeleton\.css$")),
    ("자료", re.compile(r"^/buildplan/skeletons/[^/]+\.html$")),        # 구성 설계 보기
    ("자료", re.compile(r"^/buildplan/skeletons/edit/[^/]+\.html$")),   # 구성 설계 고치기
    ("자료", re.compile(r"^/history/[^/]+/기록\.html$")),       # 사람이 보는 이력 요약 화면만 —
                                                               # 문서.json·journal.jsonl·버전-*/ 은 계속 막힌다
]


# ── 세션당 요청 rate-limit (무DB — 메모리 슬라이딩 윈도우) ─────────────────
# 온톨로지 조회(detect·compose 등)를 반복해 규칙을 근사 복원하는 남용을 어렵게 만든다.
# 단일 프로세스라 메모리 카운터로 충분하다(재시작 시 리셋 — 단기 방어라 무해). 여러
# 인스턴스로 늘리면 공유 카운터(Redis 등)로 다시 봐야 한다.
_레이트락 = threading.Lock()
_레이트기록 = {}                       # 세션열쇠 → [최근 요청 시각들]
_레이트창초 = 60
_레이트상한 = int(os.environ.get("문서지능_분당상한") or 240)


def _레이트초과(열쇠):
    """이 세션이 최근 _레이트창초 초에 상한을 넘겼나 — 넘었으면 True(막는다)."""
    지금 = time.time()
    with _레이트락:
        기록 = [t for t in _레이트기록.get(열쇠, []) if 지금 - t < _레이트창초]
        기록.append(지금)
        _레이트기록[열쇠] = 기록
        # 오래된 세션 열쇠가 무한히 쌓이지 않게 가끔 청소(창을 벗어난 열쇠 버림)
        if len(_레이트기록) > 4096:
            for k in [k for k, v in _레이트기록.items()
                      if not v or 지금 - v[-1] > _레이트창초]:
                _레이트기록.pop(k, None)
        return len(기록) > _레이트상한


# ── 관리자 인증 실패 잠금 (IP별 — 무차별 대입 속도 제한) ────────────────────
# 관리자 열쇠 자체(고엔트로피 환경변수)가 주 방어이고, 이건 단순 무차별 대입을 늦추는
# 보조 장치다. **틀린 열쇠를 실제로 보낸 경우만** 센다 — 열쇠 없이 화면을 여는 첫
# 요청(Basic 창 유도)은 정상 흐름이라 세지 않는다. IP 는 직결 주소 기준이라 리버스
# 프록시 뒤 배포에서는 X-Forwarded-For 신뢰 설정을 따로 봐야 한다.
_관리자락 = threading.Lock()
_관리자실패 = {}                       # ip → [실패 시각들]
_관리자창초 = 300
_관리자실패상한 = int(os.environ.get("문서지능_관리자실패상한") or 10)


def _관리자잠김(ip):
    지금 = time.time()
    with _관리자락:
        기록 = [t for t in _관리자실패.get(ip, []) if 지금 - t < _관리자창초]
        _관리자실패[ip] = 기록
        return len(기록) >= _관리자실패상한


def _관리자실패기록(ip):
    지금 = time.time()
    with _관리자락:
        기록 = [t for t in _관리자실패.get(ip, []) if 지금 - t < _관리자창초]
        기록.append(지금)
        _관리자실패[ip] = 기록
        if len(_관리자실패) > 4096:
            for k in [k for k, v in _관리자실패.items()
                      if not v or 지금 - v[-1] > _관리자창초]:
                _관리자실패.pop(k, None)


def _관리자성공(ip):
    with _관리자락:
        _관리자실패.pop(ip, None)


# ── 정책 토큰 게이트 (WP-S6 · 플러그인 위임 채널) ─────────────────────────────
# 정책작업(등록부 `정책` 플래그: 판정·장르·시퀀스·프롬프트조립)은 두 문으로 들어온다.
# 익명 웹앱 문(토큰 없음)은 공개다 — 지금처럼 연다(그 문의 방어는 별건 봇차단이 맡는다).
# 플러그인 위임 문(_원격)은 X-AI-Token 헤더로 오고, 그 토큰이 유효+활성이어야 한다.
# 검증은 api.정책토큰검증(원장엔 해시만 산다). 토큰별 분당 상한을 넘으면 429, 그 초과가
# 반복되면(이상사용) 토큰을 원장에서 자동 잠근다. 하드모드(문서지능_정책토큰필수=1)면
# 토큰 없는 정책요청도 막는다 — 웹앱 없는 순수 정책서버용. A1(웹앱 겸용)에선 끈다.
정책토큰헤더 = "X-AI-Token"          # ASCII — 선로 위의 열쇠는 영문(구현계획.md 규칙 8)
정책토큰필수환경 = "문서지능_정책토큰필수"

_정책락 = threading.Lock()
_정책레이트 = {}                       # 토큰지문 → [최근 요청 시각들]
_정책이상 = {}                         # 토큰지문 → 최근 창에서 상한 넘긴 횟수
_정책사용기록 = {}                     # 토큰지문 → 원장에 사용 남긴 마지막 시각(스로틀)
_정책창초 = 60
_정책상한 = int(os.environ.get("문서지능_토큰분당상한") or 120)
_정책이상상한 = int(os.environ.get("문서지능_토큰이상상한") or 5)   # 이만큼 초과 누적이면 자동 잠금
_정책사용주기 = 60                     # 원장 누적 갱신은 토큰별 ≤분당 1회(빗장 병목 회피)


def _정책토큰필수():
    return bool((os.environ.get(정책토큰필수환경) or "").strip())


def _정책레이트초과(지문):
    """이 토큰이 최근 _정책창초 초에 상한을 넘겼나 — (넘음, 잠글까). 넘김이 _정책이상상한
    회 쌓이면 잠글까=True(호출자가 원장을 자동 잠근다)."""
    지금 = time.time()
    with _정책락:
        기록 = [t for t in _정책레이트.get(지문, []) if 지금 - t < _정책창초]
        기록.append(지금)
        _정책레이트[지문] = 기록
        if len(_정책레이트) > 4096:
            for k in [k for k, v in _정책레이트.items()
                      if not v or 지금 - v[-1] > _정책창초]:
                _정책레이트.pop(k, None)
                _정책이상.pop(k, None)
                _정책사용기록.pop(k, None)
        if len(기록) > _정책상한:
            n = _정책이상.get(지문, 0) + 1
            _정책이상[지문] = n
            return True, (n >= _정책이상상한)
        return False, False


def _정책사용스로틀(지문):
    """원장 누적 갱신을 토큰별 분당 1회로 제한 — True 면 지금 원장에 남겨도 된다."""
    지금 = time.time()
    with _정책락:
        if 지금 - _정책사용기록.get(지문, 0) >= _정책사용주기:
            _정책사용기록[지문] = 지금
            return True
        return False


# ── 자동 등록(enroll) IP 발급 상한 (WP-S6) ───────────────────────────────────
# enroll(공개발급)은 관리자 열쇠 없이 열린 문 — 설치본이 자기 토큰을 자동으로 받는 자리다.
# 한 IP 가 토큰을 무한정 찍어 내지 못하게 시간당 상한을 둔다. 이건 남용 '차단'이 아니라
# '늦추기'다(익명 웹앱 문이 이미 열려 있어 토큰이 더 주는 접근은 없다) — 그래도 원장이
# 쓰레기 토큰으로 부풀지 않게 막는다. IP 는 메모리 카운터로만 세고 원장엔 안 남긴다(프라이버시).
_등록락 = threading.Lock()
_등록기록 = {}                         # ip → [최근 발급 시각들]
_등록창초 = 3600
_등록상한 = int(os.environ.get("문서지능_등록시간당상한") or 20)


def _등록초과(ip):
    지금 = time.time()
    with _등록락:
        기록 = [t for t in _등록기록.get(ip, []) if 지금 - t < _등록창초]
        기록.append(지금)
        _등록기록[ip] = 기록
        if len(_등록기록) > 4096:
            for k in [k for k, v in _등록기록.items()
                      if not v or 지금 - v[-1] > _등록창초]:
                _등록기록.pop(k, None)
        return len(기록) > _등록상한


# ── 오류 봉합 (WP-S2 ③ — 부록/출시차단감사.md D절) ────────────────────────
# 무엇이 문제였나: 코어(api.py)는 자식 프로세스의 stdout+stderr **원문**을 `로그` 에
# 담아 돌려준다. 조립·저장·게이트가 죽으면 파이썬 트레이스백이 그대로 실리고, 거기엔
# 소스 파일의 절대경로·행 번호가 붙어 있다(D-1). catch-all `f"{type(e).__name__}: {e}"`
# 도 FileNotFoundError 의 절대경로를 그대로 문다(D-2). serve.py 자신의 `{e}` 보간
# 셋도 같다(D-3).
#
# **어디서 막나 — 여기(HTTP 문)에서만 막는다.** CLI 로 직접 부르는 개발자는 지금처럼
# 자세히 봐야 한다(그게 저 로그를 만든 이유다). 그래서 api.py 의 반환값은 안 건드리고,
# HTTP 응답이 나가는 **한 곳**(`_json`)에서 씻는다.
#
# **stderr 엔 "지운 것"만 남긴다 — 원본 obj 통째는 안 남긴다** (2026-08-09, 사장님
# 프라이버시 감사 · 사례 소멸 결정). 처음엔 씻기 전 원문 obj 를 통째로 stderr 에
# 찍었다(옛 방식: `json.dumps(obj)[:4000]`). 그런데 저장 응답의 `로그` 필드엔
# apply_edit_any 가 만드는 "전: … 후: …" diff — **사용자 문서 내용 그 자체**가 실린다.
# 봉합은 그 obj 에 트레이스백·절대경로가 섞여 들어왔을 때만 발동하는데, 발동하는
# 순간 원문 전체를 찍으니 diff(사용자 내용)까지 stderr 로 샜다(실측: build/verify_all.py
# check_log_hygiene 고침 전 재현 — 응답 필드는 하나인데 트레이스백이 섞이면 그
# 필드 전체가, 문서 내용까지 통째로 stderr 에 찍혔다). "세션이 끝나면 사례가
# 사라진다"는 약속에, 서버 stderr 로그(세션과 무관하게 오래 산다)가 구멍이 됐다.
#
# 그래서 `_말씻기`/`_봉합` 이 무엇을 **지웠는지**(트레이스백 원문·소스 행·절대경로 —
# 전부 서버 내부이지 사용자가 쓴 글이 아니다)를 따로 모아 그것만 stderr 에 남긴다.
# 씻기 전/후가 "똑같은" 부분(diff 등 사용자 내용)은 애초에 지워지지 않으므로 이
# 목록에 안 들어간다 — 진단(어떤 경로·트레이스백이 있었는지)은 그대로 유지된다.
_트레이스백 = "Traceback (most recent call last)"
_소스행 = re.compile(r'^\s*File "[^"]*", line \d+.*$\n(?:\s+.*\n)?', re.M)
# 남의 컴퓨터 사정을 응답에 싣지 않는다 — 홈 디렉터리 이름은 그 자체로 사람 이름이다
_남은절대경로 = re.compile(r"(?<![\w/])/(?:Users|home|private|tmp|var|opt|etc|Library)"
                       r"(?:/[^\s'\"),;]+)*")


def _뿌리들():
    """응답에서 지워야 할 경로 앞머리 — 긴 것부터(세션 뿌리가 기본 뿌리를 품는다)."""
    out = [ROOT]
    for f in (자료뿌리.뿌리, 자료뿌리.기본뿌리):
        try:
            out.append(f())
        except Exception:
            pass
    return sorted({os.path.abspath(p) for p in out if p}, key=len, reverse=True)


def _말씻기(s, 지운것=None):
    """글 하나에서 서버 내부를 지운다. 안 바뀌면 같은 객체를 그대로 돌려준다.

    `지운것`(list)을 주면, 이 글에서 실제로 걷어낸 서버-내부 조각(트레이스백 원문·
    소스 행·절대경로)을 거기 덧붙인다. **사용자가 쓴 글(씻기 전/후가 똑같은 부분)은
    이 목록에 안 들어간다** — `_봉합` 이 이걸 모아 stderr 진단 로그를 만든다(위
    "오류 봉합" 머리말, 2026-08-09 프라이버시 결정).
    """
    본 = s
    if _트레이스백 in s:
        # 트레이스백은 통째로 걷어낸다. 앞에 찍힌 사람말(조립기가 낸 진단)은 남긴다.
        머리, _경계, 꼬리 = s.partition(_트레이스백)
        if 지운것 is not None:
            지운것.append(_트레이스백 + 꼬리)          # 지운 것: 트레이스백 자체(경로·행 포함)
        머리 = 머리.rstrip()
        s = (머리 + "\n" if 머리 else "") + "서버에서 처리하다 오류가 났습니다 — 자세한 내용은 서버 기록에 남겼습니다"
    if 지운것 is not None:
        지운것.extend(m.group(0) for m in _소스행.finditer(s))
    s = _소스행.sub("", s)
    for 뿌 in _뿌리들():
        if 뿌 in s:
            if 지운것 is not None:
                지운것.append(f"[경로뿌리] {뿌}")
            s = s.replace(뿌 + os.sep, "").replace(뿌, "")

    def _캐고(m):
        if 지운것 is not None:
            지운것.append(m.group(0))
        return os.path.basename(m.group(0)) or "(경로)"

    s = _남은절대경로.sub(_캐고, s)
    return 본 if s == 본 else s


def _봉합(값):
    """응답 객체를 훑어 글마다 `_말씻기`. (씻은값, 바뀜여부, 지운것) 을 돌려준다.

    `지운것` 은 stderr 진단 로그가 쓸, 실제로 제거된 서버-내부 조각 목록이다 —
    원본 obj 를 통째로 찍지 않고 이것만 찍는 것이 이 함수를 나눈 목적이다.
    """
    바뀜 = [False]
    지운것 = []

    def 걷기(v):
        if isinstance(v, str):
            새 = _말씻기(v, 지운것)
            if 새 is not v:
                바뀜[0] = True
            return 새
        if isinstance(v, dict):
            return {k: 걷기(x) for k, x in v.items()}
        if isinstance(v, list):
            return [걷기(x) for x in v]
        return v

    씻은값 = 걷기(값)
    return 씻은값, 바뀜[0], 지운것


def 되돌림(t):
    """날바이트로 온 한글을 되살린다. 파이썬 http 서버는 요청줄을 latin-1 로 읽는다."""
    try:
        return t.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return t


def _서버인자():
    """포트(위치 인자, 기본 8642)와 --host(선택)를 함께 읽는다.

    바인드 주소가 지금까지 `("127.0.0.1", 포트)` 로 하드코딩돼 있었다(X2 B-2) —
    컨테이너 밖으로 열 길이 없었다. `--host` 인자나 환경변수 `문서지능_바인드` 로
    열 수 있게 한다. **기본값은 그대로 127.0.0.1 로 둔다**: 이 서버엔 아직 인증이
    없어서(B-1·F-1 과 같은 뿌리 문제) `0.0.0.0` 을 기본으로 열면 인증 없이 쓰기
    작업까지 누구나 부를 수 있게 된다 — 열어야 하면 사람이 명시로 연다.
    """
    argv = sys.argv[1:]
    호스트 = os.environ.get("문서지능_바인드", "127.0.0.1")
    남은 = []
    i = 0
    while i < len(argv):
        if argv[i] == "--host" and i + 1 < len(argv):
            호스트 = argv[i + 1]
            i += 2
            continue
        남은.append(argv[i])
        i += 1
    포트 = int(남은[0]) if 남은 else 8642
    return 호스트, 포트


호스트, 포트 = _서버인자()


# ── 옛 경로 → 작업 (2026-08-07, WP-S4) ───────────────────────────────────
# 웹앱과 편집기는 `/save`·`/upload` 라는 **옛 이름**으로 POST 한다. 그 두 경로는
# 작업 인자를 봉투에 담지 않고 **본문 그대로** 보낸다(편집기는 편집 스냅샷 한 벌을,
# 업로더는 `{이름, 자료}` 를). 여기서 그것을 등록부의 인자 이름으로 옮겨 준다.
#
# **왜 이 표를 만들었나** — 예전에는 `_post` 안에 `if 이름 == "저장":` 특수분기가
# 있었고, 그 분기가 `/api/저장` 까지 삼켰다. 그래서 원격에서 규격대로 부른
# `부르기("저장", {"payload": …})` 의 봉투를 **다시 payload 로 알고 한 겹 더**
# 감쌌다(구현계획.md §3 WP-S4 에 적힌 S1 의 경고). 웹앱은 `/save` 직행이라 안
# 밟았을 뿐, 저장을 CLI·MCP 로 부르는 순간 터진다.
#
# 이제 특수분기는 없다. `/save`·`/upload` 는 **옛 URL 을 인자로 옮기는 어댑터**일
# 뿐이고, `/api/<작업>` 은 어느 작업이든 같은 한 길을 탄다. 새 작업이 늘어도 여기에
# 손댈 일이 없다 — 손댈 일이 생긴다면 그건 또 특수분기를 만드는 중이라는 신호다.
옛경로 = {
    "/save": ("저장", lambda p: {"payload": p}),
    "/저장": ("저장", lambda p: {"payload": p}),
    "/upload": ("올리기", lambda p: {"이름": p.get("이름"), "내용_base64": p.get("자료")}),
    "/올림": ("올리기", lambda p: {"이름": p.get("이름"), "내용_base64": p.get("자료")}),
}


class 손잡이(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        self._새쿠키 = None
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if self.command == "POST":
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def end_headers(self):
        # 정적 서버라 캐시 헤더가 없다. 편집기·CSS 를 고쳐도 옛것이 잡히면
        # "고쳤는데 안 바뀐다"가 된다 — 그 함정을 여러 번 밟았다.
        self.send_header("Cache-Control", "no-store")
        for k, v in 안전헤더:
            self.send_header(k, v)
        if self._새쿠키:
            # HttpOnly — 자바스크립트가 못 읽는다. XSS 가 하나라도 나면 이 쿠키가
            # 곧 남의 세션 전체이므로(로그인이 없어서 이것 말고 다른 신분이 없다).
            # SameSite=Lax — 남의 사이트가 우리 쓰기 작업을 대신 부르는 길을 좁힌다.
            self.send_header("Set-Cookie",
                             f"{쿠키이름}={self._새쿠키}; Path=/; HttpOnly; "
                             f"SameSite=Lax; Max-Age={쿠키수명초}")
            self._새쿠키 = None
        super().end_headers()

    # ── 세션 ────────────────────────────────────────────────────────────
    def _쿠키(self):
        """Cookie 헤더에서 세션 열쇠를 꺼낸다. 없으면 빈 글자.

        `http.cookies` 를 안 쓰고 직접 가르는 까닭 — 그 파서는 이상한 쿠키를 만나면
        **거기서 조용히 멈춘다.** 우리는 이상한 열쇠를 '없는 것'으로 넘기면 안 된다:
        경로 탈출을 시도한 요청이 조용히 새 세션을 받아 정상으로 보이면, 막았는지
        아닌지 아무도 확인할 수 없다(규칙 3 · 규칙 5).
        """
        생 = self.headers.get("Cookie") or ""
        for 조각 in 생.split(";"):
            이름, _, 값 = 조각.partition("=")
            이름 = 되돌림(이름.strip())
            if 이름 not in 쿠키별명:
                continue
            값 = 되돌림(값.strip().strip('"'))
            if not 자료뿌리.열쇠올바른가(값):
                raise 나쁜쿠키(값)
            return 값
        return ""

    def _세션준비(self):
        """이 요청이 어느 세션인지 정한다. 없으면 새로 낸다. 활동 시각을 적는다.

        여기서 만든 열쇠는 **응답 헤더로 나가고**(end_headers) 처리하는 동안은
        스레드 지역값으로 살아 있다 — `자료뿌리.뿌리()` 가 그 값을 보고 세션
        디렉터리를 돌려준다. `os.environ` 에 넣지 않는 까닭은 자료뿌리.py 머리말에 있다
        (ThreadingHTTPServer 라 옆 스레드의 뿌리가 바뀐다).
        """
        열쇠 = self._쿠키()
        if not 열쇠:
            열쇠 = 자료뿌리.새열쇠()
            self._새쿠키 = 열쇠
        return 열쇠

    def _세션으로(self, 일):
        """세션을 갈아 끼우고 `일()` 을 부른다. 나쁜 열쇠는 여기서 **거절**한다."""
        # 플러그인 로컬(단일세션) — 쿠키 격리·레이트리밋·세션 청소를 다 건너뛰고 MCP·CLI 와
        # 똑같이 기본 뿌리(또는 문서지능_세션 이 있으면 그 방)를 본다. 이래야 브라우저의 /save·
        # 이력이 방금 MCP 가 만든 그 문서를 찾는다. 한 사람·127.0.0.1 뿐이라 격리·상한이 불필요.
        if 단일세션:
            with 자료뿌리.세션갈기((os.environ.get(자료뿌리.세션환경변수) or "").strip()):
                일()
            return
        try:
            열쇠 = self._세션준비()
        except 나쁜쿠키:
            # 무엇이 왔는지는 응답에 안 싣는다(반사 출력은 그 자체가 공격 재료다).
            self._json(400, {"ok": False,
                             "로그": "세션 쿠키가 규칙에 안 맞습니다 — 쿠키를 지우고 "
                                   "다시 들어오시면 새 세션이 열립니다"})
            return
        # rate-limit — /api 남용(온톨로지 조회 반복 등)을 세션당 분당 상한으로 막는다.
        # 정적 파일(CSS·폰트·산출물)은 제외한다 — 화면 하나가 자산을 여럿 부른다.
        if self.path.startswith("/api") and _레이트초과(열쇠):
            self._json(429, {"ok": False,
                             "로그": "요청이 너무 잦습니다 — 잠시 후 다시 시도해 주세요"})
            return
        with 자료뿌리.세션갈기(열쇠):
            try:
                세션.활동적기(열쇠)
            except OSError as e:
                sys.stderr.write(f"세션 활동 기록 실패: {e}\n")
            try:
                # **게으른 청소** — 스레드를 따로 안 띄운다(build/세션.py 주석).
                # 지금 세션은 방금 활동을 적었으니 빼고 훑는다.
                세션.청소(지금세션=열쇠)
            except Exception as e:
                sys.stderr.write(f"세션 청소 실패: {e}\n")
            일()

    # ── 관리자 열쇠 게이트 (WP-S5) ──────────────────────────────────────
    def _관리자제공열쇠(self):
        """요청이 실어 온 관리자 열쇠. 두 갈래 — 없으면 None.

        · `X-Admin-Key` 헤더 — 관리자 면 JS 가 API 를 부를 때.
        · `Authorization: Basic <base64(user:key)>` 의 **비밀번호 자리** — 브라우저가
          화면을 볼 때(화면 이동에 커스텀 헤더를 못 붙이므로 Basic Auth 로 받는다).
          사용자이름은 무시한다(열쇠 하나만 본다 — 계정 시스템이 아니다).
        """
        h = self.headers.get("X-Admin-Key")
        if h is not None:
            return h
        auth = self.headers.get("Authorization") or ""
        if auth[:6].lower() == "basic ":
            try:
                raw = base64.b64decode(auth[6:].strip()).decode("utf-8", "replace")
            except Exception:
                return None
            return raw.partition(":")[2]        # user:pass 의 pass 자리
        return None

    def _관리자통과(self):
        """관리자 열쇠가 맞나. 맞으면 True, 아니면 401 을 내보내고 False.

        상수시간 비교(hmac.compare_digest)로 잰다. **fail closed** — 환경변수가 비어
        있으면 어떤 열쇠로도 못 들어온다. 무엇이 왔는지는 응답에 안 싣는다(반사 출력은
        그 자체가 공격 재료다) — 열쇠 값도 로그에 안 남긴다.
        """
        ip = self._클라ip()
        if _관리자잠김(ip):
            b = json.dumps({"ok": False,
                            "로그": "관리자 인증 시도가 너무 잦습니다 — 잠시 후 다시 시도해 주세요"},
                           ensure_ascii=False).encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b)
            return False
        설정된 = 관리자열쇠설정됨()
        제공 = self._관리자제공열쇠()
        # 바이트로 재고 비교한다 — compare_digest 는 비ASCII **문자열**을 거부한다
        # (TypeError). 문자열로 재면 아무나 한글 한 글자 실은 X-Admin-Key 헤더로
        # 처리 스레드를 죽일 수 있다(우회는 아니지만 요청마다 죽는 500급 구멍).
        통과 = (bool(설정된) and 제공 is not None
              and hmac.compare_digest(제공.encode("utf-8"), 설정된.encode("utf-8")))
        if 통과:
            _관리자성공(ip)
            return True
        # 틀린 열쇠를 **실제로 보낸** 경우만 실패로 센다 — 열쇠 없이 화면을 여는 첫
        # 요청(제공 is None)은 Basic 창을 띄우는 정상 흐름이라 잠금 카운트에서 뺀다.
        if 제공 is not None:
            _관리자실패기록(ip)
        b = json.dumps({"ok": False, "로그": "관리자 열쇠가 필요합니다"},
                       ensure_ascii=False).encode("utf-8")
        self.send_response(401)
        # 브라우저 기본 열쇠 창은 **직접 화면 이동(navigation)** 요청에만 띄운다. 앱 카드(X-Admin-Key)로
        # 부르는 fetch/XHR(Sec-Fetch-Dest: empty)엔 Basic 챌린지를 안 보내 이중 팝업을 없앤다
        # (A안, 사장님 요청 '26-08-17). Sec-Fetch-Dest 없는 옛 브라우저·curl 은 화면이동으로 봐 폴백 유지.
        if (self.headers.get("Sec-Fetch-Dest") or "document") == "document":
            self.send_header("WWW-Authenticate", f'Basic realm="{관리자영역}"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)
        return False

    # ── 정책 토큰 게이트 (WP-S6) ──────────────────────────────────────────
    def _정책토큰제공(self):
        """요청이 실어 온 정책 토큰(X-AI-Token 헤더). 없으면 None."""
        v = self.headers.get(정책토큰헤더)
        return v.strip() if v and v.strip() else None

    def _정책거절(self, code, 로그):
        b = json.dumps({"ok": False, "로그": 로그}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)
        return False

    def _정책통과(self, 작=None):
        """정책작업(등록부 `정책` 플래그) 게이트. 통과면 True, 아니면 401/429 를 내고 False.

        · 토큰 없음 → 하드모드(또는 이 작업이 `토큰필수`)면 401(막음), 아니면 True(익명 웹앱
          문 — 지금처럼 연다). `토큰필수` 작업(예: 지식)은 온톨로지 조각을 그대로 내주므로
          하드모드가 아니어도 토큰을 요구한다 — 설치본은 enroll 로 자동 발급받아 통과하고,
          토큰 없는 익명은 401 이라 casual 온톨로지 덤프를 막는다(웹앱의 compose·detect
          같은 결과성 정책작업은 토큰필수가 아니라 익명 문이 그대로 열려 있다).
        · 토큰 있음 → api.정책토큰검증 으로 유효+활성 확인(아니면 401). 토큰별 분당 상한을
          넘으면 429(반복되면 원장 자동 잠금). 통과하면 사용을 원장에 드물게(분당1) 남긴다.
        """
        원문 = self._정책토큰제공()
        if 원문 is None:
            if _정책토큰필수() or (작 and 작.get("토큰필수")):
                return self._정책거절(401, "정책 토큰이 필요합니다")
            return True                       # 익명/웹앱 문 — 공개(봇차단이 따로 지킨다)
        결 = api.정책토큰검증(원문)
        if not 결.get("ok"):
            return self._정책거절(401, f"정책 토큰이 유효하지 않습니다({결.get('사유','')})")
        지문 = 결["지문"]
        넘음, 잠글까 = _정책레이트초과(지문)
        if 넘음:
            if 잠글까:
                try:
                    api.정책토큰잠금(결["해시"], "이상사용 자동잠금(분당 상한 반복 초과)")
                except Exception:
                    pass
            return self._정책거절(429, "요청이 너무 잦습니다 — 잠시 후 다시 시도해 주세요")
        if _정책사용스로틀(지문):
            try:
                api.정책토큰사용(결["해시"])
            except Exception:
                pass
        return True

    def _클라ip(self):
        """이 요청의 실제 클라이언트 IP. 배포는 Cloudflare 터널(127.0.0.1) 뒤라
        self.client_address 는 늘 127.0.0.1 이다 — 그대로 IP별 상한을 걸면 전 세계가 한
        통에 들어가 함께 막힌다. Cloudflare 는 실 클라이언트를 CF-Connecting-IP 로 준다.
        이 서버는 127.0.0.1 바인드 + 터널로만 닿으므로(직접 노출 없음) 이 헤더는 믿을 수
        있다. 헤더가 없으면(로컬 직접 호출) client_address 로 떨어진다."""
        cf = self.headers.get("CF-Connecting-IP")
        if cf and cf.strip():
            return cf.strip()
        return (self.client_address or ["?"])[0]

    def _등록통과(self):
        """자동 등록(enroll·공개발급) 문 — IP당 시간당 발급 상한만 건다(관리자·토큰 불요)."""
        ip = self._클라ip()
        if _등록초과(ip):
            return self._정책거절(429, "설치 토큰 발급이 너무 잦습니다 — 잠시 후 다시 시도해 주세요")
        return True

    def _길(self):
        """경로를 유니코드로 되돌린 **후보들**. 브라우저는 퍼센트 인코딩, curl 은 날바이트."""
        생 = self.path.split("?")[0]
        return [되돌림(urllib.parse.unquote(생, encoding="utf-8", errors="replace")),
                되돌림(생)]

    def 작업이름(self):
        """경로에서 작업 이름을 뽑는다. **후보를 다 보고 나서** 판정한다 —
        처음엔 첫 후보가 안 맞으면 바로 404 를 내서, 인코딩이 다른 쪽으로 온
        요청을 통째로 놓쳤다."""
        후보 = []
        for x in self._길():
            if x.rstrip("/") == "/api":
                return "", None
            if x.startswith("/api/"):
                후보.append(x[5:].strip("/"))
        for 이름 in 후보:
            작 = api.찾기(이름)
            if 작:
                return 이름, 작
        return (후보[0], None) if 후보 else (None, None)

    def 질의(self, 작):
        q = urllib.parse.parse_qs(self.path.partition("?")[2])
        인자 = {}
        for k, v in q.items():
            k2 = 되돌림(k)
            if k2 in 작["받는것"]:
                인자[k2] = 되돌림(v[0])
        return 인자

    def _열게될길(self):
        """stdlib 이 **실제로 열게 될** 경로 하나. 판정과 서빙이 같은 글자를 봐야 한다.

        `SimpleHTTPRequestHandler.translate_path` 가 하는 일과 똑같이 한다 —
        퍼센트 인코딩을 **한 번** 풀고 `posixpath.normpath` 로 `..` 를 접는다.
        (한 번만 푸는 것이 중요하다. 두 번 풀면 stdlib 보다 넓게 봐서, 정말로
        이름에 `%` 가 든 파일을 못 열게 막는 다른 종류의 어긋남이 생긴다.)
        """
        생 = self.path.split("?")[0]
        푼것 = 되돌림(urllib.parse.unquote(생, encoding="utf-8", errors="replace"))
        return posixpath.normpath(푼것)

    def _정적허용(self):
        """이 경로가 GET_화이트리스트 에 있는가 — 있으면 **어느 뿌리에서 열지**까지 정한다.

        2026-08-07 고침(적대리뷰 §중간 "GET 화이트리스트가 %2f 로 우회됨").
        예전에는 후보 **둘**(퍼센트 해석본·날바이트본)을 다 걸어 보고 **하나라도**
        맞으면 통과시킨 뒤, 서빙은 stdlib 에 맡겼다. 날바이트본에서 `%2f` 는 그냥
        글자라 `/build/samples/..%2fsamples-docs.json` 이 `[^/]+` 패턴을 통과했고,
        그 다음 stdlib 의 `translate_path` 가 `%2f` 를 `/` 로 풀고 `..` 를 접어
        **B-1 이 막아 둔 전문서 등록부**(build/*-docs.json)를 내줬다. 직접 경로
        `/build/samples-docs.json` 은 404 인데 우회로만 200 이었다 — 판정한 글자와
        여는 글자가 달랐던 것이 전부다("`..` 는 애초에 어느 패턴과도 안 맞는다"는
        옛 주석은 **날바이트 후보에 대해서는 거짓**이었다).

        이제 후보를 하나로 줄인다. `_열게될길()` 로 stdlib 과 똑같이 풀어 접은
        경로만 걸어 보고, 통과하면 `self.path` 를 **그 경로를 다시 인코딩한 것**으로
        갈아 끼운다. stdlib 이 그것을 한 번 풀면 우리가 검사한 바로 그 글자가 된다 —
        판정과 서빙 사이에 글자가 달라질 틈이 없다.
        덤 하나 — 요청줄에 **날바이트**로 온 한글 경로가 이제 제대로 열린다.
        예전에는 날바이트 후보가 화이트리스트는 통과하는데 stdlib 이 깨진 글자로
        찾아 404 였다(2026-08-07 실측, 고침 전/후 서버를 나란히 띄워 견줌:
        `/history/smoke/기록.html` 날바이트 404 → 200,
        `/build/samples/..%2fsamples-docs.json` 200(등록부 유출) → 404).
        ※ curl 은 경로의 비ASCII 를 알아서 퍼센트로 바꾼다 — 날바이트는 소켓으로
          직접 보내야 잰다(curl 로 재고 "날바이트도 200" 이라고 적을 뻔했다).

        허용되면 `self.directory` 를 그 뿌리로 맞춘다 — stdlib 의 translate_path 가
        이 값을 쓰므로, 자료 파일은 자료뿌리에서 나간다(WP-S2 ①).
        """
        길 = self._열게될길()
        for 갈래, p in GET_화이트리스트:
            if p.fullmatch(길):
                self.directory = ROOT if 갈래 == "코드" else 자료뿌리.뿌리()
                self.path = urllib.parse.quote(길)
                return True
        return False

    def list_directory(self, path):
        """디렉터리 목록을 절대 내주지 않는다(B-1·D-5). 화이트리스트는 파일 하나를
        가리키는 패턴만 담고 있어 여기 닿을 일이 없어야 하지만, 방어적으로 막는다 —
        내부 경로를 응답에 싣지 않는다(구현계획.md 규칙: 오류에 서버 내부를 노출 금지)."""
        self.send_error(404, "Not Found")
        return None

    # 세 문(GET·HEAD·POST) 이 전부 세션을 지난다. **정적 서빙도 지난다** — 산출물·
    # 편집 화면은 자료뿌리에서 나가므로, 여기를 안 지나면 남의 세션 산출물이 보인다.
    def do_GET(self):
        self._세션으로(self._get)

    def do_HEAD(self):
        self._세션으로(self._head)

    def do_POST(self):
        self._세션으로(self._post)

    def _get(self):
        if self.path in ("/", "/index.html"):        # 뿌리는 웹앱으로
            self.send_response(302)
            self.send_header("Location", "/promo/landing.html")
            self.end_headers()
            return
        # 관리자 화면 껍데기 — **폼 마크업뿐이라 열쇠 없이 연다**(사장님 판정 2026-08-10:
        # Basic 팝업이 안 뜨는 브라우저 대응. WP-S5 조정 — 화면 껍데기는 공개, 데이터·동작은
        # 보호). **실제 관리자 데이터·동작(관리자=True 작업)은 아래 API 게이트(X-Admin-Key)가
        # 그대로 막는다** — 페이지가 떠야 admin.html 의 열쇠 카드가 나와 열쇠를 받는다.
        # admin.html 은 GET 화이트리스트에 없다 — 이 문 하나로만 나가고, `_열게될길()` 이
        # stdlib 과 똑같이 정규화하므로 `..`·%2f 우회도 **admin.html 하나로만** 모여 다른
        # 파일로 안 샌다(껍데기엔 비밀이 없어 노출 위험 0 — verify_all check_admin_gate 가 잰다).
        if self._열게될길() == 관리자화면:
            self.directory = ROOT                     # admin.html 은 코드다(app.html 과 같은 뿌리)
            self.path = urllib.parse.quote(관리자화면)
            super().do_GET()
            return
        이름, 작 = self.작업이름()
        if 이름 == "" and 작 is None:
            self._json(200, {"ok": True, "값": api.목록()})
            return
        if 이름 is None:
            if self._정적허용():
                super().do_GET()
            else:
                self._json(404, {"ok": False, "로그": "그런 경로가 없습니다"})
            return
        if not 작:
            self._json(404, {"ok": False, "로그": f"모르는 작업: {이름}",
                             "할수있는것": sorted(api.작업) + sorted(api.별칭)})
            return
        if not 작["읽기"]:
            self._json(405, {"ok": False,
                             "로그": f"'{이름}' 은 쓰기 작업입니다 — POST 로 부르세요"})
            return
        # 관리자 작업(등록부 플래그에서 파생)은 열쇠 없이 못 부른다(WP-S5).
        if 작.get("관리자") and not self._관리자통과():
            return
        # 정책 작업(위임 채널)은 발급받은 토큰으로만 부른다(WP-S6). 웹앱 익명 문은 통과.
        if 작.get("정책") and not self._정책통과(작):
            return
        self._json(200, api.부르기(이름, self.질의(작)))

    def _head(self):
        # SimpleHTTPRequestHandler.do_HEAD 는 do_GET 을 거치지 않고 곧장
        # send_head() 로 간다 — 화이트리스트를 여기서도 따로 걸지 않으면 HEAD 로
        # 우회해 화이트리스트 밖 파일의 존재·크기·타입을 캘 수 있었다
        # (2026-08-07 WP-X1 에서 발견 — B-1 과 같은 구멍의 다른 문).
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/promo/landing.html")
            self.end_headers()
            return
        # 관리자 화면 껍데기는 공개다(GET 과 같은 판정) — HEAD 도 그대로 연다.
        if self._열게될길() == 관리자화면:
            self.directory = ROOT
            self.path = urllib.parse.quote(관리자화면)
            super().do_HEAD()
            return
        if self._정적허용():
            super().do_HEAD()
        else:
            self.send_error(404, "Not Found")

    def _옛경로(self):
        """이 POST 가 옛 URL(/save·/upload)인가 — 맞으면 (작업이름, 옮기개).

        경로에 한글을 쓰면 클라이언트마다 인코딩이 갈린다(브라우저는 퍼센트
        인코딩, curl 은 날바이트). 그래서 후보 둘을 다 본다(`_길()` 주석 참고).
        """
        for x in self._길():
            짝 = 옛경로.get(x.rstrip("/"))
            if 짝:
                return 짝
        return None, None

    def _post(self):
        이름, 옮기개 = self._옛경로()
        if 이름 is None:
            이름, _작 = self.작업이름()
        if not 이름:
            self.send_error(404)
            return
        작 = api.찾기(이름)
        if not 작:
            self._json(404, {"ok": False, "로그": f"모르는 작업: {이름}",
                             "할수있는것": sorted(api.작업)})
            return
        # 읽기 작업을 POST 로 부르는 것은 막지 않는다 — 원격 코어(api._원격)가 작업
        # 이름별 분기 없이 **전부 POST** 로 보내기 때문이다(WP-S1). GET 쪽만 쓰기를
        # 막으면 된다(_get 의 405).
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 48 * 1024 * 1024:   # 통째로 메모리에 읽기 전에 막는다(올리기 30MB·base64 40MB 여유)
                self.close_connection = True   # 본문을 안 읽고 끊는다 — 소켓 어긋남 방지
                self._json(413, {"ok": False, "로그": "보내신 내용이 너무 큽니다 (한 번에 48MB까지)"})
                return
            payload = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception as e:
            # 무엇이 어떻게 안 읽혔는지는 서버 기록으로(D-3) — 응답엔 사람말만.
            sys.stderr.write(f"[payload] {type(e).__name__}: {e}\n")
            self._json(400, {"ok": False,
                             "로그": "보내신 내용을 읽지 못했습니다 (JSON 이어야 합니다)"})
            return
        # 관리자 작업(등록부 플래그에서 파생)은 열쇠 없이 못 부른다(WP-S5). 본문은 이미
        # 읽었으므로(위) 소켓이 안 엉킨다 — 열쇠가 틀리면 여기서 401 로 선다. 본문에
        # LLM 키가 실려 와도 로그·응답에 안 실린다(본문은 log_message 가 안 찍는다).
        if 작.get("관리자") and not self._관리자통과():
            return
        # 정책 작업(위임 채널)은 발급받은 토큰으로만 부른다(WP-S6). 웹앱 익명 문은 통과.
        if 작.get("정책") and not self._정책통과(작):
            return
        # 자동 등록(enroll)은 열린 문이지만 IP당 시간당 발급 상한을 건다(WP-S6).
        if 작.get("공개발급") and not self._등록통과():
            return
        # 옛 URL 이면 본문을 통째로 인자로 옮기고, `/api/<작업>` 이면 등록부가 받는
        # 인자만 골라 넘긴다. **여기가 저장·올리기·게이트에 공통인 유일한 길이다.**
        if 옮기개:
            인자 = 옮기개(payload if isinstance(payload, dict) else {})
        else:
            인자 = {k: v for k, v in (payload or {}).items() if k in 작["받는것"]}
        try:
            r = api.부르기(이름, 인자)
        except Exception:
            import traceback
            traceback.print_exc()                 # 서버 기록엔 전부 남긴다
            self._json(500, {"ok": False,
                             "로그": "처리하다 오류가 났습니다 — 서버 기록을 봐 주세요"})
            return
        self._json(200 if r.get("ok") else 400, r)

    def send_error(self, code, message=None, explain=None):
        """stdlib 기본 오류 페이지를 안 쓴다 (부록 D-5).

        기본 페이지는 요청 경로·설명을 그대로 되비추고, 디렉터리 목록까지 낸 적이
        있다(B-1). 여기는 **정해진 짧은 글**만 낸다 — 무엇을 물었는지 되비추지
        않는다(반사 출력은 그 자체가 공격 재료다).
        """
        말 = {403: "볼 수 없습니다", 404: "그런 경로가 없습니다",
             405: "그 방법으로는 부를 수 없습니다"}.get(code, "요청을 처리하지 못했습니다")
        b = json.dumps({"ok": False, "로그": 말}, ensure_ascii=False).encode("utf-8")
        self.send_response(code, message or 말)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def _json(self, code, obj):
        # 서버 내부(트레이스백·절대경로)를 응답에서 걷어낸다 — HTTP 문에서만(위 주석).
        씻은, 바뀜, 지운것 = _봉합(obj)
        if 바뀜:
            # 원본 obj 를 통째로는 안 찍는다(위 "오류 봉합" 머리말, 2026-08-09 프라이버시
            # 결정) — obj 의 다른 자리(예: 저장 응답의 `로그` = 문서 편집 전/후 diff)에
            # **사용자 문서 내용**이 함께 실려 있을 수 있고, 원문 전체를 찍으면 그것까지
            # stderr(세션과 무관하게 오래 사는 로그)로 샌다. `지운것` 은 실제로 걷어낸
            # 서버-내부 조각(트레이스백·소스 행·절대경로)만 담고 있으므로, 운영자는
            # 여전히 어떤 경로·트레이스백이 있었는지 보고 진단할 수 있다 — 사용자 글은
            # 애초에 이 목록에 안 들어간다(씻기 전/후가 같은 부분이라 안 지워졌으므로).
            sys.stderr.write(
                f"[봉합] 응답에서 서버 내부를 걷어냈습니다 ({len(지운것)}건). 지운 것:\n"
                + ("\n---\n".join(지운것))[:4000] + "\n")
        obj = 씻은
        # default=str — api.목록() 의 '모양' 필드는 파이썬 type 객체(str·dict·bool…)를
        # 그대로 담는다(MCP 는 mcp/server.py:67-70 에서 직접 매핑해 쓴다). 여기 HTTP
        # 경계는 그 객체를 그대로 못 실어 GET /api 가 연결이 끊겼다(TypeError, 2026-08-07
        # WP-X1 에서 화이트리스트 테스트 중 발견 — 이 파일을 고치는 김에 문자열로 낮춰
        # 응답하게 했다. api.py 의 작업 목록 계약 자체는 안 건드렸다 — MCP 는 원래대로).
        b = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    srv = ThreadingHTTPServer((호스트, 포트), 손잡이)
    print(f"편집 서버 — http://{호스트}:{포트}  (코드 {ROOT})")
    print(f"  자료뿌리 {자료뿌리.기본뿌리()}"
          + ("" if 자료뿌리.기본뿌리() == ROOT
             else f"  ← 환경변수 {자료뿌리.환경변수}"))
    print(f"  세션은 쿠키 {쿠키이름} 로 잇습니다 — {자료뿌리.세션들뿌리()}/<열쇠>/ · "
          f"무반응 {세션.만료초()}초면 지웁니다(설정.json 의 '세션만료초')")
    # 관리자 면(WP-S5) — 열쇠는 환경변수 하나. 열쇠 값 자체는 절대 찍지 않는다.
    if 관리자열쇠설정됨():
        print(f"  관리자 면 http://{호스트}:{포트}{관리자화면} — 열쇠 있음"
              f"(환경변수 {관리자열쇠환경변수}, 로그엔 안 남김)")
    else:
        print(f"  관리자 면 잠김 — 환경변수 {관리자열쇠환경변수} 가 없습니다"
              f"(설정하면 {관리자화면} 이 열립니다)")
    # 판 간격은 **코어(api.py)** 가 정한다 — 여기서 따로 들면 웹앱과 CLI·MCP 가
    # 서로 다른 간격으로 판을 남긴다(WP-S4 에서 옮겼다).
    print(f"  POST /save 로 편집 결과를 받습니다. 판은 {api.판_간격초}초마다 하나씩 남깁니다.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
