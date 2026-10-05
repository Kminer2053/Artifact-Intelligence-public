#!/usr/bin/env python3
"""이 스킬이 할 수 있는 일의 **유일한 목록**.

왜 여기 모으나(2026-08-04): 문 셋을 낼 참이다 — 스킬(채팅) · 공유 MCP · 웹앱.
셋이 각자 코어를 부르면 목록이 셋으로 갈라지고, 하나를 늘릴 때 나머지에 빠뜨린다.
그 병을 오늘 하루에만 여섯 군데에서 겪었다(장르 등록부·문체 게이트·작업 화면·
편집 반영기·관측기·감사). **한 곳에 적고 셋이 읽는다.**

  workspace/api.py   ← 작업 목록(여기)
       ├── workspace/serve.py    HTTP 껍데기 (웹앱·원격 MCP 가 쓴다)
       ├── mcp/server.py         MCP 껍데기
       └── (스킬은 CLI 로 직접)

작업 하나 = 이름 · 무엇을 받나 · 무엇을 하나 · 읽기인가 쓰기인가.
읽기는 아무나, 쓰기는 자기 것에만 — 나중에 세션 열쇠를 붙일 자리가 여기다.
"""
import contextvars
import hashlib
import importlib.util as _iu
import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import unicodedata
import uuid

import urllib.error
import urllib.request


def _http전용열기():
    """urllib 열기를 http/https 로만 — file:// 등 다른 스킴 핸들러를 아예 싣지 않는다.
    urlopen 기본 opener 는 FileHandler·FTPHandler·DataHandler 까지 갖고 있어 동적 URL 이
    들어오면 로컬 파일을 읽을 수 있다(정적 보안검사 Semgrep 'dynamic-urllib-use' 규칙 대응).
    프록시·리다이렉트·HTTP 오류(HTTPError) 동작은 기본 opener 와 같다. 알 수 없는 스킴은
    UnknownHandler 가 URLError 로 거부한다."""
    od = urllib.request.OpenerDirector()
    for h in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(),
              urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(),
              urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPRedirectHandler(),
              urllib.request.HTTPErrorProcessor()):
        od.add_handler(h)
    return od


_HTTP열기 = _http전용열기()


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ROOT 는 **코드뿌리**다(조립기·온톨로지·node_modules 가 여기 있다).
# 운영 자료(등록부·산출물·inbox·요청·이력)가 어디 있는지는 build/자료뿌리.py 한 곳이
# 정한다 — 세션 격리의 주입점이 그것 하나뿐이어야 한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(ROOT, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)


# ── 접속·사용 통계(무DB, 파일) ─────────────────────────────────────────────
# rate-limit 용 메모리 카운터(serve.py)와 달리 재시작·재배포에도 남아야 하므로 파일에
# 일자별로 누적한다. sessions/ 는 배포 rsync 에서 제외되는 운영 경로라 코드 재배포로
# 지워지지 않는다. 통계 실패는 서비스에 영향을 주지 않는다(전부 감싼다).
_통계경로 = os.environ.get("문서지능_통계경로") or os.path.join(ROOT, "sessions", "접속통계.json")


def 접속기록(종류):
    """일자별 접속·사용 카운터를 하나 올린다(방문·생성·내보내기 등). serve.py 가 부른다."""
    try:
        오늘 = time.strftime("%Y-%m-%d")
        os.makedirs(os.path.dirname(_통계경로), exist_ok=True)
        with 자료뿌리.빗장(_통계경로):
            data = {}
            if os.path.exists(_통계경로):
                try:
                    data = json.load(open(_통계경로, encoding="utf-8"))
                except Exception:
                    data = {}
            날 = data.setdefault("일자별", {}).setdefault(오늘, {})
            날[종류] = int(날.get(종류) or 0) + 1
            합 = data.setdefault("합계", {})
            합[종류] = int(합.get(종류) or 0) + 1
            자료뿌리.원자json(_통계경로, data, indent=2)
    except Exception:
        pass


작업 = {}


# 작업 이름은 한국어가 정본이다. 다만 HTTP 로 부를 때 클라이언트마다 인코딩이 갈려
# (curl 은 질의를 날바이트로 보내 요청줄이 거부된다) ASCII 별칭을 함께 둔다.
별칭 = {}


# 인자가 **무슨 모양인가.** 여기 적지 않은 것은 글(str)이다.
# 왜 여기 있나 — 전에는 mcp/server.py 가 이 표를 따로 들고 있었고 세 개만 적혀 있었다.
# 그래서 MCP 로 부르면 `doc`(문서 한 벌)이 글로 선언돼 **객체를 아예 못 넣었다**
# (2026-08-05 A-4 11번에서 걸림: "Input should be a valid string").
# 작업 목록이 한 곳이면 인자 모양도 한 곳이어야 한다.
인자모양 = {
    "doc": dict, "payload": dict, "plan": dict, "인자": dict, "어긋남답": dict,
    "항목": dict,
    "자료들": list, "자료": list, "예시": list, "고침": list,
    "판없이": bool, "n": int, "검사": bool, "전체": bool,
    # 편집기열기 포트 — 글로만 받아 MCP 에서 정수 8833 이 입력 오류로 죽었다(verify3 §7 E2E-B). 정수로 선언한다
    # (MCP 느슨한 검증은 "8833" 같은 숫자 글도 받는다 — 편집기열기는 int() 로 한 번 더 편다).
    "포트": int,
    # 새문서·저장의 읽은 자료 파일 이름 목록(S3, '26-10-01)
    "자료파일": list,
}

# 인자의 **영문 별칭.** Anthropic API 가 도구 인자 키를 영문·숫자로 강제한다
# (`^[a-zA-Z0-9_.-]{1,64}$`) — 한글 키가 하나라도 실리면 그 세션의 **모든 요청**이
# 400 으로 죽는다(2026-08-13 문서지능 세션이 이걸로 먹통이 됐다). 도구 이름에 en
# 별칭이 있듯 인자에도 별칭을 두고, MCP 문이 서명에서만 이걸 쓴다 — 내부(api·웹앱·
# 스킬)는 한글 이름 그대로다. 여기 없는 한글 인자가 생기면 mcp/server.py 가 뜨다가
# 죽는다(조용한 재발 방지).
인자영문 = {
    "유형id": "type_id", "판없이": "skip_version", "어긋남답": "conflict_answers",
    "이유": "reason", "무엇": "mode", "장르": "genre", "이름": "name",
    "내용_base64": "content_base64", "경로": "path", "형식": "format",
    "자료": "material", "자료들": "materials", "예시": "examples",
    "추가지시": "extra_instruction", "지시문": "prompt", "인자": "args",
    "원문": "source_text", "결정": "decision", "항목": "item",
    "이전": "before", "이후": "after", "판별": "detected", "고른": "chosen",
    "지시": "instruction", "규칙맥락": "rule_context",
    "제안": "proposed", "채택": "adopted", "파일": "file",
    # 클라환경(clientenv)·재현신고 — MCP 에 실리는 도구라 영문 별칭 필수(빠지면 서버 기동 실패).
    "글꼴보유": "fonts_present", "os계열": "os_family",
    "어디": "where", "내용": "content",
    # 관리자설정저장 — 웹앱 전용(목록() 이 MCP 에서 거른다)이나 별칭을 한 곳에 다 둔다.
    "세션만료초": "session_ttl_sec", "llm키": "llm_key", "모델": "model",
    "세션당상한": "per_session_limit", "하루총량": "daily_total", "장르토큰": "genre_tokens",
    "제공자": "provider", "베이스": "base_url", "표시": "display",
    # 온도(temperature, r10 재검토) — 관리자설정저장 인자. 빠지면 위 머리말대로 MCP 기동이 죽는다.
    "온도": "temperature",
    # 정책 토큰(WP-S6) — 발급/활성/자동등록 op 의 인자. 별칭은 한 곳에 다 둔다.
    "메모": "memo", "지문": "fingerprint", "켜기": "enable", "라벨": "label",
    # 2층 빌드플랜 op(플랜승인) — 한글 인자 키는 MCP 에서 400 을 내므로 별칭 필수.
    "코멘트": "comment",
    # 편집기열기(로컬 편집기 서버) — 포트 인자.
    "포트": "port",
    # 개체고쳐(편집기 AI 재작성, 서버맥락주입) — 표 셀 배열·문서 맥락 조회 키.
    "셀들": "cells", "문서키": "doc_key",
    # 규칙마당(공개 규칙 카드 의견·제안) — 웹앱 전용(숨김)이나 별칭은 한 곳에 다 둔다.
    "종류": "kind",
    # 새문서 한 번에 검사까지(항목 3, '26-09-26) — 새 인자라 MCP 스키마에 실리려면
    # ASCII 별칭이 있어야 한다(위 머리말 — 한글 인자 키가 스키마에 실리면 세션 전체가 400).
    "검사": "check",
    # 지식 통째 조회(항목 8, '26-09-26 2차 진단) — 정책서버가 한 번에 값을 다 주는지
    # 알아보는 선택 인자. '지식'은 숨김 작업(MCP 미노출)이라 꼭 필요친 않지만, 서버-투-서버
    # HTTP 호출에도 별칭 규칙을 한 곳에서 지킨다.
    "전체": "full",
    # 지어냄 교정 루프(r9, '26-09-27) — 교정적용 의 '고침'(모델이 낸 [{경로,글}] 목록).
    "고침": "fixes",
    # 작업방식(workmode, '26-09-29) — 바로 완성/함께 검수 선택. "mode" 는 '무엇' 이 이미 쓴다.
    "방식": "work_mode", "요청": "request",
    # 내보내기 관문(H2, '26-09-29) — 검사 기록 없이 사람이 확인하고 낼 때의 이유.
    "강행이유": "override_reason",
    # 그림 생성 핸드오프(P2, '26-09-30) — 이미지능력·이미지채움 의 에이전트 이미지 도구 이름.
    "도구": "tool",
    # 새문서·저장의 읽은 자료 파일 목록('26-10-01 주관 판정 S3) — CLI 는 대화를 몰라 에이전트가 파일읽기로 읽은 파일 이름을 넘긴다.
    "자료파일": "source_files",
}


def 등록(이름, 받는것=(), 읽기=True, 설명="", en=None, 비동기=True, 승인필요=False,
       관리자=False, 정책=False, 공개발급=False, 숨김=False, 토큰필수=False, 공개쓰기=False,
       서버모델=False):
    """작업 하나를 등록부에 적는다.

    `비동기` — 이 작업을 `작업시작` 으로 뒤에 걸 수 있는가. 기본은 **된다**이고,
    일감 자체를 다루는 작업(작업시작·작업상태)만 False 다. 왜 값으로 두나 —
    "이건 뒤에 못 건다" 목록을 다른 파일에 손으로 또 적으면 그 순간 목록이 둘로
    갈린다(구현계획.md 규칙 2). 등록부에 적으면 `목록()` 을 타고 세 문에 그대로 간다.

    `승인필요` (WP-S3) — 이 작업이 **되묻기 관문** 뒤에 있는가. 어긋남 물음에 답이
    안 왔으면 부르기() 가 이 작업을 실행하지 않고 물음을 돌려준다(출시계획 1-5:
    코어가 거부해서 강제한다). 여기 값으로 두는 까닭도 `비동기` 와 같다 — "막히는
    작업 목록"을 관문 코드에 손으로 적으면 재조립하는 새 작업이 늘 때 그 목록만
    빠진다. 등록부 한 곳에서 파생돼야 세 문이 같게 막힌다.

    `관리자` (WP-S5, 출시계획 3-4) — 이 작업이 **관리자 열쇠 뒤에** 있는가. 열쇠
    게이트는 `workspace/serve.py` 가 이 플래그를 보고 건다 — 어느 작업이 관리자
    전용인지 serve.py 에 이름으로 또 적지 않는다(손목록 금지, 이름별 분기 금지:
    구현계획.md 규칙 2). 등록부 한 곳의 플래그에서 파생돼야 관리자 작업을 하나
    늘렸을 때 게이트가 자동으로 따라온다. 게다가 관리자 작업은 **웹앱 문 하나에만**
    두고 스킬·MCP·공개 목록에는 안 낸다 — `목록()` 이 이 플래그로 걸러 낸다(그
    함수 주석에 왜 거르는지 적었다).

    `토큰필수` — 이 정책작업은 **발급받은 정책토큰 없이는 못 부른다**(익명 거부).
    `정책` 게이트는 하드모드(문서지능_정책토큰필수=1)가 아니면 토큰 없는 익명도 통과시켜
    웹앱 문을 연 채로 둔다 — compose·detect 같은 결과성 작업은 그래도 된다. 하지만
    `지식`은 온톨로지 조각을 그대로 돌려주므로 익명 무제한 조회면 온톨로지가 통째로
    새어 나간다. 그래서 이 작업만 하드모드와 무관하게 토큰을 요구한다(설치본은 부트스트랩
    enroll 로 자동 발급받으니 조회 가능, 캐주얼 익명 덤프는 401). serve.py `_정책통과`
    가 이 플래그를 보고 건다 — 이름별 분기 없이 등록부 한 곳에서 파생.

    `공개쓰기` — 로그인 없는 **공개 게시**(누구나 쓰고 누구나 본다, 규칙마당 의견·제안).
    serve.py `_post` 가 이 플래그를 보고 ① 본문이 JSON(Content-Type application/json)이 아니면
    거절하고(남의 사이트 폼이 text/plain 으로 대신 올리는 CSRF 차단) ② Origin 이 있으면 우리
    Host 와 같아야 하며 ③ IP 당 10분 상한을 건다(세션 쿠키는 버리면 새로 나오므로 세션 상한만으론
    못 막는다). 이름별 분기 없이 등록부 한 곳에서 파생.

    `서버모델` ('26-10-01) — 이 정책작업은 규칙이 아니라 **서버 LLM** 이 있어야 돈다(편집기 키 없는
    AI 다시쓰기). 설치본에 온톨로지가 함께 실리면서 부르기() 는 정책작업을 로컬에서 돌리는데,
    서버 모델이 필요한 작업만은 이 컴퓨터에 LLM 설정이 없을 때 지금처럼 정책서버로 넘긴다.
    """
    def 감싸기(fn):
        받는 = tuple(받는것)
        if 승인필요 and "어긋남답" not in 받는:
            # 답을 실어 보낼 자리(어긋남답)는 관문이 받아서 기록한다 — 작업 함수는
            # 이 인자를 모른다(부르기() 가 관문에서 빼고 넘긴다). 그래도 받는것에
            # 적어야 하는 까닭: MCP 도구 서명·HTTP 인자 거름망(serve.py `_post`)이
            # 받는것으로 인자를 거르므로, 여기 없으면 답이 관문까지 오지도 못한다.
            받는 = 받는 + ("어긋남답",)
        작업[이름] = {"이름": 이름, "받는것": 받는, "읽기": 읽기, "en": en,
                    "모양": {k: 인자모양.get(k, str) for k in 받는},
                    "비동기": 비동기, "승인필요": bool(승인필요),
                    "관리자": bool(관리자), "정책": bool(정책), "공개발급": bool(공개발급),
                    "숨김": bool(숨김), "토큰필수": bool(토큰필수), "공개쓰기": bool(공개쓰기),
                    "서버모델": bool(서버모델),
                    "설명": 설명 or (fn.__doc__ or "").strip().splitlines()[0], "함수": fn}
        if en:
            별칭[en] = 이름
        return fn
    return 감싸기


def 돌리기(cmd, timeout=180, 환경추가=None):
    # env — 지금 세션을 자식에게 물려준다(WP-S2 ②). 세션 열쇠는 스레드 지역값이라
    # (serve.py 가 요청마다 갈아 끼운다) 그냥 두면 자식 프로세스가 못 본다. 안 물려주면
    # 조립기·편집화면 생성기가 **기본 뿌리**에 쓴다 — 등록부는 세션 것을 읽고 산출물만
    # 전역으로 새는, 화면상 아무 이상이 없는 갈라짐이 된다.
    # `환경추가` — 이 한 번의 호출에만 더 얹을 환경변수(예: 조판게이트의 ONLY 선택 인자,
    # '26-09-26). 세션 환경 자체를 바꾸지 않도록 자식환경() 사본에만 얹는다.
    env = 자료뿌리.자식환경()
    if 환경추가:
        env = dict(env)
        env.update(환경추가)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                       env=env)
    return {"ok": r.returncode == 0, "로그": (r.stdout or "") + (r.stderr or "")}


def 등록부들():
    """장르 등록부는 **세어서** 얻는다 — 손으로 적으면 장르가 늘 때 빠뜨린다."""
    return 자료뿌리.등록부들()


def 등록부길(docs):
    """`조립`·`문체검사` 가 받는 docs 인자를 **자료뿌리의 실제 경로**로 바꾼다.

    받는 모양 셋을 다 받는다: "samples" · "samples-docs.json" · "build/samples-docs.json".
    왜 필요한가 — 예전에는 이 문자열을 그대로 조립기에 넘겼고 조립기는 cwd(=코드뿌리)
    기준으로 열었다. 자료뿌리를 옮겨도 **코드뿌리의 정본을 읽고 코드뿌리에 산출물을
    쓰는** 갈라짐이 여기서 났다(WP-S2 ①).
    """
    이름 = os.path.basename(str(docs or "samples"))
    if 이름.endswith("-docs.json"):
        이름 = 이름[:-len("-docs.json")]
    return 자료뿌리.등록부(이름)


# ── 읽기 ────────────────────────────────────────────────────────────────

_지식캐시 = {}                 # path → (결과, 만료시각) — 조각 조회를 프로세스 안에서 짧게 캐시
_지식캐시TTL = int(os.environ.get("문서지능_지식캐시초") or 300)


def _지식조회(정책서버, path, 전체=False):
    """정책서버에서 온톨로지 **조각(path)만** 조회해 TTL 로 짧게 캐시한다 — 사용자 자료는
    안 보내고 온톨로지 path 만 보낸다(정책만-로컬: 사용자 정보보호 우선). TTL 로 정책서버가
    온톨로지를 갱신하면 그 최신성을 따라간다(피드백 루프로 정제되는 규칙이 클라에 반영).

    `전체` — 참이면 12,000자 한도 없이 통째로 받는다(항목 8, '26-09-26 2차 진단). 한도
    적용 여부로 결과가 달라지므로 **캐시 칸도 따로 쓴다**(전체=True/False 를 해시에 넣는다) —
    아니면 먼저 부른 쪽의 짧은(키만) 응답이 캐시에 앉아 나중의 전체 요청까지 잘못 돌려준다."""
    import time as _t
    지금 = _t.time()
    캐시키 = f"{path}|전체={bool(전체)}"
    쌍 = _지식캐시.get(캐시키)
    if 쌍 and 쌍[1] > 지금:
        return 쌍[0]
    # 디스크 캐시 — 플러그인 CLI 는 작업마다 새 프로세스라 위 메모리 캐시가 다음 호출로 안 이어진다.
    # 설계지시문내기·프롬프트조립이 같은 조각을 서버에서 매번 다시 받아(한 쌍에 17~22회 × 0.2~0.4초)
    # 느렸다('26-09-26 실측). 같은 TTL 로 설치 트리 안에 남긴다 — 버전을 올리면 트리가 바뀌어 저절로 비워진다.
    import hashlib
    칸 = os.path.join(ROOT, ".지식캐시",
                     hashlib.sha1(f"{정책서버}|{캐시키}".encode("utf-8"), usedforsecurity=False).hexdigest() + ".json")
    try:
        with open(칸, encoding="utf-8") as f:
            쌓인 = json.load(f)
        if 쌓인.get("만료", 0) > 지금 and isinstance(쌓인.get("r"), dict):
            _지식캐시[캐시키] = (쌓인["r"], 쌓인["만료"])
            return 쌓인["r"]
    except (OSError, ValueError):
        pass
    r = _원격(정책서버, "지식", {"path": path, **({"전체": True} if 전체 else {})})
    if isinstance(r, dict) and r.get("ok"):
        _지식캐시[캐시키] = (r, 지금 + _지식캐시TTL)
        try:
            os.makedirs(os.path.dirname(칸), exist_ok=True)
            임시 = 칸 + f".{os.getpid()}.tmp"
            with open(임시, "w", encoding="utf-8") as f:
                json.dump({"만료": 지금 + _지식캐시TTL, "r": r}, f, ensure_ascii=False)
            os.replace(임시, 칸)
        except OSError:
            pass      # 캐시는 속도용일 뿐 — 못 쓰면 매번 받으면 된다
    return r


@등록("지식", ["path", "전체"], 설명="1층 온톨로지 조각 조회(점 표기). 빈 값이면 최상위 키 목록. "
    "설치본에 함께 실린 ontology/ontology.json 을 로컬로 읽는다. 그 파일이 없을 때만 정책서버에 "
    "이 path 조각을 묻는다(사용자 자료는 안 나감). "
    "전체(기본 거짓)가 참이면 12,000자 한도 없이 통째로 돌려준다",
    en="knowledge", 정책=True, 숨김=True, 토큰필수=True)
def 지식(path="", 전체=False):
    # 토큰필수 는 **정책서버 쪽** 게이트(serve.py _정책통과)다 — 로컬 온톨로지를 읽는 이 길엔
    # 토큰이 필요 없다. '26-10-01 부터 공개 플러그인도 온톨로지를 함께 싣는다(완전 공개 '26-09-25).
    로컬 = os.path.join(ROOT, "ontology", "ontology.json")
    if not os.path.exists(로컬):
        # 예비 길 — 온톨로지 파일이 빠진 설치(옛 0.3.x 트리·손으로 지운 경우)만 정책서버에서
        # 이 path 조각을 조회해 캐시한다. 사용자 자료는 안 나가고 온톨로지 path 만 간다.
        정책서버 = _정책서버설정()
        if 정책서버:
            return _지식조회(정책서버, path, 전체)
        return {"ok": False, "로그": "작성 규칙 파일(ontology/ontology.json)이 없습니다. "
                "설치본에 함께 들어 있어야 하니 플러그인을 다시 설치하거나 업데이트하세요. "
                "규칙 원본은 https://github.com/Kminer2053/Artifact-Intelligence-source 에도 공개돼 있습니다."}
    o = json.load(open(로컬, encoding="utf-8"))
    node = o
    for part in [p for p in str(path).split(".") if p]:
        if isinstance(node, list) and part.isdigit():
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return {"ok": False, "로그": f"'{part}' 를 찾지 못했습니다",
                    "키": sorted(node.keys()) if isinstance(node, dict) else None}
    # 전체=True(항목 8) — 작성·설계 지시문(_지식전체)이 규칙 묶음을 한 번에 받으려는 요청.
    # 대화형 조회(전체=False, 기본값)만 12,000자 한도로 거대한 덩어리를 막는다.
    if not 전체 and isinstance(node, dict) and len(json.dumps(node, ensure_ascii=False)) > 12000:
        return {"ok": True, "값": None, "키": sorted(node.keys()),
                "로그": "내용이 커서 키만 돌려줍니다 — 더 깊은 path 로 다시 부르세요"}
    return {"ok": True, "값": node}


def _지식전체(path):
    """작성·설계 지시문 전용 — 크기 한도 없이 규칙 묶음을 통째로 받는다.

    지식()은 12,000자 넘는 묶음을 키 이름만 돌려준다(대화형 조회가 거대한 덩어리를 쏟지 않게
    하는 안전장치). 그 한도가 지시문 조립에도 걸려, 1p 장르 규칙(약 2.4만 자)이 작성 모델에게
    **키 이름 10개로만** 갔다('26-09-26 벤치마크 실측 — 작성 지시문의 규칙 칸 139자).
    로컬 온톨로지(개발 트리·'26-10-01 이후 설치본)는 한도 없이 바로 읽고, 온톨로지 파일이 없는
    옛 설치본만 정책서버에서 키가 오면 한 단계씩 더 깊이 조회해 다시 합친다 — 서버를 다시
    배포하지 않아도 옛 서버에서 그대로 동작한다.
    다시 합칠 때 메타 키(_전거·_판정 …)와 점(.)이 든 키는 건너뛴다(지시문에서 어차피 걷는다)."""
    로컬 = os.path.join(ROOT, "ontology", "ontology.json")
    if os.path.exists(로컬):
        node = json.load(open(로컬, encoding="utf-8"))
        for part in [p for p in str(path).split(".") if p]:
            if isinstance(node, list) and part.isdigit():
                node = node[int(part)]
            elif isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return {"ok": False, "로그": f"'{part}' 를 찾지 못했습니다"}
        return {"ok": True, "값": node}

    # 통째 조회 한 방(항목 8, '26-09-26 2차 진단) — 정책서버가 이 버전이면 요청 한 번으로
    # 끝난다. 옛 서버는 '전체' 인자를 모르는 인자로 거절하거나(모르는 인자 오류, ok:False)
    # 예전처럼 12,000자 한도로 키만 돌려주므로(값이 그대로 None), 두 경우 다 실패로 보고
    # 아래 너비 우선 조회로 물러선다 — 재배포 없이 옛 서버에서도 그대로 동작해야 한다.
    한방 = 지식(path, 전체=True)
    if isinstance(한방, dict) and 한방.get("ok") and 한방.get("값") is not None:
        return 한방
    r = 지식(path)

    def _더깊이(rr):
        return isinstance(rr, dict) and rr.get("ok") and rr.get("값") is None and rr.get("키")

    if not _더깊이(r):
        return r

    def _아래(p, rr):
        return [f"{p}.{k}" if p else str(k) for k in rr["키"] if not _메타키인가(k) and "." not in str(k)]

    # 한 단계씩 너비 우선으로, 같은 깊이는 동시에 조회한다 — 1p 는 조회가 50번 남짓이라
    # 차례로 부르면 한 번 0.2~0.4초  = 10~20초가 든다('26-09-26 실측). 동시에 부르면 깊이 수만큼만.
    # 동시성은 4로 낮춘다(항목 8, 2차 진단) — 8이면 분당 상한(120)·자동 잠금(초과 5회)에
    # 너무 빨리 다가간다(벤치마크처럼 같은 설치 토큰으로 여러 세션이 겹칠 때 특히).
    from concurrent.futures import ThreadPoolExecutor
    결과 = {path: r}
    실패 = []      # 자식 조회가 끝내 실패한 path — 조용히 빼지 않고 이름을 남긴다(항목 8)
    한도초과 = False   # 429(요청 상한)를 하나라도 받으면 재시도로 요청을 더 늘리지 않고
                     # 그 자리에서 멈춘다(still_partly 항목 8 재발 — LIMIT=30 흉내에서 한
                     # 번의 일괄 백오프 재시도가 초과 횟수를 39→79 로 두 배로 늘렸다. 실서버는
                     # 이 초과가 5회 반복되면 토큰을 자동 잠근다, serve.py _정책이상상한).
    앞줄 = _아래(path, r)
    while 앞줄 and not 한도초과:
        with ThreadPoolExecutor(max_workers=min(4, len(앞줄))) as 일꾼:
            for p, rr in zip(앞줄, 일꾼.map(지식, 앞줄)):
                결과[p] = rr
        if any(isinstance(결과[p], dict) and 결과[p].get("_한도초과") for p in 앞줄):
            한도초과 = True     # 429 를 봤으니 아래 재시도도 건너뛴다 — 재시도 자체가 요청을 늘린다
        else:
            # 실패(5xx·순단)한 자식은 짧게 **한 번만**(지수 백오프 없이) 다시 시도한다 —
            # 그래도 실패하면 그 path 를 실패 목록에 남긴다(조용히 빼지 않는다, 구현계획 규칙 3).
            재시도대상 = [p for p in 앞줄 if not (isinstance(결과[p], dict) and 결과[p].get("ok"))]
            if 재시도대상:
                time.sleep(0.5)
                for p in 재시도대상:
                    결과[p] = 지식(p)
                if any(isinstance(결과[p], dict) and 결과[p].get("_한도초과") for p in 재시도대상):
                    한도초과 = True
        for p in 앞줄:
            if not (isinstance(결과[p], dict) and 결과[p].get("ok")):
                실패.append(p)
        앞줄 = [c for p in 앞줄 if _더깊이(결과[p]) for c in _아래(p, 결과[p])]

    def _짓기(p):
        rr = 결과[p]
        if not _더깊이(rr):
            return rr.get("값")
        return {c.rsplit(".", 1)[-1]: _짓기(c) for c in _아래(p, rr)
                if isinstance(결과.get(c), dict) and 결과[c].get("ok")}

    if 한도초과:
        return {"ok": False, "값": _짓기(path),
                "로그": f"정책서버 요청 상한(429)에 걸려 더 조회하지 않고 멈췄습니다 — "
                       f"규칙 일부가 빠졌습니다({len(실패)}개): "
                       + ", ".join(sorted(실패)[:10]) + (" 등" if len(실패) > 10 else "")}
    if 실패:
        return {"ok": False, "값": _짓기(path),
                "로그": f"규칙 일부를 정책서버에서 못 받았습니다({len(실패)}개) — "
                       + ", ".join(sorted(실패)[:10]) + (" 등" if len(실패) > 10 else "")}
    return {"ok": True, "값": _짓기(path)}


def 제목뽑기(d):
    """장르마다 제목을 담는 자리가 다르다 — 1p title · 시행문/보도 제목 · 규정 제명 ·
    풀버전은 표지 안에 있다. 손으로 적은 목록이 아니라 **차례로 찾아본다.**"""
    for k in ("title", "제목", "제명"):
        if d.get(k):
            return d[k]
    표지 = d.get("표지") or {}
    if isinstance(표지, dict):
        for k in ("제목", "주제목", "title"):
            if 표지.get(k):
                return 표지[k]
    return None


@등록("문서목록", 설명="모든 장르의 문서 목록", en="docs")
def 문서목록():
    out = []
    for p in 등록부들():
        장르 = os.path.basename(p).replace("-docs.json", "")
        try:
            for d in json.load(open(p, encoding="utf-8")):
                out.append({"key": d.get("filename"), "장르": d.get("genre") or 장르,
                            "제목": 제목뽑기(d),
                            "고친때": d.get("_수정시각")})
        except Exception as e:
            # 예외 원문을 목록에 실으면 등록부 **절대경로**가 화면까지 간다
            # (부록/출시차단감사.md D-4). 사람말만 내보내고 상세는 서버 로그로.
            sys.stderr.write(f"[문서목록] 등록부를 읽지 못했습니다: {p} — "
                             f"{type(e).__name__}: {e}\n")
            out.append({"key": None, "장르": 장르, "제목": "(등록부를 읽지 못했습니다)"})
    return {"ok": True, "값": out}


@등록("문서", ["key"], 설명="문서 하나의 3층 JSON", en="doc")
def 문서(key):
    for p in 등록부들():
        try:
            for i, d in enumerate(json.load(open(p, encoding="utf-8"))):
                if d.get("filename") == key:
                    return {"ok": True, "값": d,
                            "등록부": os.path.relpath(p, 자료뿌리.뿌리())}
        except Exception:
            pass
    return {"ok": False, "로그": f"'{key}' 를 찾지 못했습니다"}


@등록("이력", ["key"], 설명="문서의 판 목록과 사건 기록", en="history")
def 이력(key):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    try:
        V = 자료뿌리.모듈("version", "history")
    except Exception as e:
        return {"ok": False, "로그": f"이력 장치를 불러오지 못했습니다: {e}"}
    try:
        return {"ok": True, "값": {"판": V.목록(key), "기록": V.읽기(key)}}
    except Exception as e:
        return {"ok": False, "로그": str(e)}


@등록("유형", 설명="1p 12유형의 판별신호·시퀀스(관리자 전용 — 크라운주얼, 클라 미노출)", en="types", 관리자=True)
def 유형():
    r = 지식("document_types.onepage-report.구성.목차로직.types")
    return r


@등록("시퀀스", ["유형id"],
    설명="판정된 유형 하나의 목차 시퀀스(절 제목)만 — fabcheck 절제목 대조용(판별신호는 안 나간다)",
    en="seq", 정책=True)
def 시퀀스(유형id=""):
    """이 문서에 판정된 유형의 표준·압축 시퀀스만 돌려준다 — 판정·조립 때 이미 완성
    프롬프트에 실렸던 것과 같은 노출 수준(12유형 통째가 아니다). 지어냈나 게이트가
    '지어낸 절 제목'을 이 시퀀스와 대조해 잡는다."""
    types = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
    t = next((x for x in types if x.get("id") == 유형id), None)
    if not t:
        return {"ok": True, "값": []}
    return {"ok": True, "값": list((t.get("표준시퀀스") or []) + (t.get("압축시퀀스") or []))}


# 2026-09-06 공개 push 전 적대감사: 이 작업이 관리자·정책·토큰 어느 게이트도 없이 공개 웹앱 GET
# 과 MCP 도구로 노출돼, 온톨로지 신설 키(슬라이드 구성 정본)가 resolve.py 차단목록에 없던 틈에
# 익명으로 원문이 나갔다. 웹앱(app.html)은 이 작업을 쓰지 않고 플러그인은 자동 발급 토큰이
# 있으니 **정책토큰 필수**로 잠근다(resolve.py 쪽은 허용목록 스크럽으로 이중 봉합).
@등록("개인", ["path", "profile"], 설명="개인화 오버레이를 얹은 조회(정책토큰 필수 — 온톨로지 조각은 허용 잎만)",
    en="personal", 정책=True, 토큰필수=True)
def 개인(path="", profile="default"):
    cmd = [sys.executable, "personalization/resolve.py", profile]
    if path:
        cmd.append(path)
    return 돌리기(cmd)


# ── 개인 기본 제목 모양('26-09-28) — 편집기 '문서 설정 › 제목 모양 › 이 모양을 기본으로' ──────────
# 플러그인(한 사람이 쓰는 설치본) 전용 개인 설정이다. 자료뿌리의 **기본 뿌리**(설정길()과 같은 자리)에
# 개인설정.json 으로 둔다 — 세션 밑에 두면 세션이 끝날 때 같이 사라진다. 웹앱(여러 사람이 한 서버)은
# 계정이 없어 여기 쓰면 남의 새 문서까지 바뀐다. 그래서 거절하고, 웹앱은 브라우저 저장을 쓴다(판정 D5).
# 받는 값은 허용목록으로만 거른다: 장르는 편집기 프로파일 상단바에 제목모양이 있는 장르, 키는
# 제목모양·제목틀·장모양·절모양(+ 풀버전 포인트색), 값은 프로파일 선택지(색은 #rrggbb). 기관 이름은 안 싣는다.
_개인모양키 = ("제목모양", "제목틀", "장모양", "절모양")


def _개인설정길():
    """개인설정.json 자리. 자료뿌리 환경변수가 있으면 그 기본뿌리(개발·시험 길 그대로).

    없고 `CLAUDE_PLUGIN_DATA` 가 있으면(Claude Code 설치본) 그 밑에 둔다('26-09-29) — 설치본의
    기본뿌리는 판마다 다른 캐시 폴더(…/plugins/cache/…/<판>/)라, 거기 두면 판을 올릴 때마다 설정이
    사라져 '다음부터 묻지 않고'(작업방식)·기본 제목 모양이 되살아나지 않는다. 옛 자리에만 파일이
    있으면 한 번 옮겨 온다(복사 — 옛 파일은 그 판 폴더와 함께 사라진다).
    """
    옛 = os.path.join(자료뿌리.기본뿌리(), "개인설정.json")
    d = (os.environ.get("CLAUDE_PLUGIN_DATA") or "").strip()
    # 웹앱 판단은 _여러사람웹앱() 으로 — 편집기열기(editor)가 띄우는 로컬 편집기 서버(serve.py)는
    # 문서지능_웹앱=1 을 얹지만 MCP 와 같은 설치본이다. 여기서 '웹앱'으로 보면 편집기의 '이 모양을
    # 기본으로'는 판 폴더에, 새문서는 PLUGIN_DATA 에서 읽어 둘이 갈라진다(fixup '26-09-29 재현).
    if (os.environ.get(자료뿌리.환경변수) or "").strip() or _여러사람웹앱() or not d:
        return 옛
    d = os.path.abspath(os.path.expanduser(d))
    새 = os.path.join(d, "개인설정.json")
    try:
        os.makedirs(d, exist_ok=True)
        if not os.path.exists(새) and os.path.exists(옛):
            import shutil
            shutil.copyfile(옛, 새)
    except OSError:
        pass
    return 새


def _여러사람웹앱():
    """공개 웹앱(쿠키 세션으로 여러 사람을 가르는 serve.py)인가 — 로컬 편집기 서버(단일세션)는 아니다."""
    return bool(os.environ.get("문서지능_웹앱")) and not os.environ.get("문서지능_단일세션")


def _개인모양거르기(장르, 값):
    """(정리된 값, 버린 키) — 프로파일 선택지에 없는 값·모르는 키는 버린다."""
    try:
        g = next(x for x in 자료뿌리.모듈("genres").등록부() if x["이름"] == 장르)
        상단 = (json.load(open(os.path.join(ROOT, "ontology", "editor-profiles.json"), encoding="utf-8"))
              ["장르"].get(g["키"]) or {}).get("상단바") or {}
    except (StopIteration, OSError, ValueError, KeyError):
        return None, []
    if not 상단.get("제목모양"):
        return None, []
    out, 버림 = {}, []
    for k, v in (값 or {}).items():
        if k in _개인모양키 and isinstance(v, str) and v in {m[0] for m in 상단.get(k) or ()}:
            out[k] = v
        elif (k == "포인트색" and 장르 == "fullreport" and isinstance(v, str)
              and re.fullmatch(r"#[0-9A-Fa-f]{6}", v)):
            out[k] = v
        else:
            버림.append(str(k))
    return out, 버림


@등록("개인기본모양", ["장르", "항목", "결정"], 읽기=False, 비동기=False,
    설명="편집기 '이 모양을 기본으로' — 제목 모양 기본값을 이 설치본의 개인 설정에 두거나(결정=저장·지우기) "
        "읽는다(보기). 다음 새문서가 비어 있는 제목 모양 키에 싣는다(플러그인 전용 — 웹앱은 브라우저에 저장)",
    en="personaldefault")
def 개인기본모양(장르="", 항목=None, 결정="보기"):
    if _여러사람웹앱():
        return {"ok": False, "로그": "웹앱에서는 기본 모양을 이 브라우저에 저장합니다 — 서버에는 두지 않습니다"}
    장르 = str(장르 or "").strip()
    if isinstance(항목, str) and 항목.strip():
        try:
            항목 = json.loads(항목)
        except ValueError:
            return {"ok": False, "로그": "항목은 {제목모양: …} 모양의 객체여야 합니다"}
    결정 = str(결정 or "보기").strip()
    if 결정 not in ("보기", "저장", "지우기"):
        return {"ok": False, "로그": f"결정은 보기·저장·지우기 가운데 하나입니다 (받은 값: {결정})"}
    정리, 버림 = _개인모양거르기(장르, 항목 if isinstance(항목, dict) else {})
    if 정리 is None:
        return {"ok": False, "로그": f"제목 모양을 고를 수 있는 장르가 아닙니다: {장르 or '(비어 있음)'} "
                "— samples(1페이지)·fullreport(풀버전)만 됩니다"}
    길 = _개인설정길()
    try:
        설정 = json.load(open(길, encoding="utf-8"))
        if not isinstance(설정, dict):
            설정 = {}
    except (OSError, ValueError):
        설정 = {}
    칸 = 설정.get("제목모양기본") if isinstance(설정.get("제목모양기본"), dict) else {}
    if 결정 == "보기":
        return {"ok": True, "값": 칸.get(장르) or None}
    if 결정 == "저장" and not 정리:
        return {"ok": False, "로그": "저장할 제목 모양 값이 없습니다 — 기본으로 돌리려면 결정=지우기 를 쓰세요"}
    with 자료뿌리.빗장(길):
        if 결정 == "지우기":
            칸.pop(장르, None)
        else:
            칸[장르] = 정리
        설정["제목모양기본"] = 칸
        자료뿌리.원자json(길, 설정, ensure_ascii=False, indent=1)
    return {"ok": True, "값": 칸.get(장르) or None,
            "로그": ("기본 제목 모양을 지웠습니다" if 결정 == "지우기"
                    else "다음 새 문서부터 이 제목 모양으로 시작합니다")
                   + (f" (버린 키: {', '.join(버림)})" if 버림 else "")}


def _개인기본모양_싣기(doc, 장르):
    """새문서 입구 — 개인 기본 제목 모양을 **비어 있는 키에만** 싣는다(플러그인만). 실었으면 알림 한 줄."""
    if _여러사람웹앱() or not isinstance(doc, dict):
        return None
    try:
        칸 = (json.load(open(_개인설정길(), encoding="utf-8")) or {}).get("제목모양기본") or {}
    except (OSError, ValueError, AttributeError):
        return None
    정리, _ = _개인모양거르기(장르, 칸.get(장르) if isinstance(칸, dict) else None)
    실음 = []
    # 모양 키 넷은 한 벌로 싣는다 — 초안이 이미 하나라도 골랐으면(틀·계획이 정한 것) 섞지 않는다.
    골랐나 = any(doc.get(k) not in (None, "") for k in _개인모양키)
    for k, v in (정리 or {}).items():
        if (k in _개인모양키 and 골랐나) or doc.get(k) not in (None, ""):
            continue
        doc[k] = v
        실음.append(f"{k}={v}")
    return ("개인 기본 제목 모양을 실었습니다: " + ", ".join(실음)) if 실음 else None


# ── 작업 방식('26-09-29 사장님 요청) — 바로 완성 / 함께 검수 ─────────────────────────────
# 플러그인에서 사람 검수(판정 확인·빌드플랜 승인·편집기 리터칭·내보내기 승인)를 거칠지 고른다.
# 바로 완성은 **게이트를 없애지 않는다** — plan_id·승인 기록은 그대로이고 에이전트가 스스로
# 플랜승인을 부른다(코멘트에 '바로 완성'). 고르는 차례: 에이전트가 대화를 읽고 넘긴 방식 → 이 대화에서 정한
# 방식 → 저장된 선택 → 없으면 한 번 묻기. 요청 말투 판별은 힌트일 뿐이다(fixup3 주관 판정 '26-09-29 — 자연어를
# 정규식으로 읽는 두더지 잡기를 멈춘다). 저장 = "앞으로도 이대로"(개인설정.json 최상위 '작업방식', 방식 인자 필수).
# 웹앱(여러 사람)은 거절한다 — 웹앱은 편집 화면이 곧 작업 화면이다.
_작업방식들 = ("바로완성", "함께검수")
_방식별말 = {"바로완성": "바로 완성", "함께검수": "함께 검수"}
# 검수를 **빼라는** 말 — 이것부터 걷어 낸 뒤 함께 검수 신호를 찾는다("편집기 없이"가 '편집기'로 잡히지 않게).
_말투_빼기 = re.compile(
    r"(검수|검토|확인|편집기|편집\s*화면|승인|리뷰)\s*(?:은|는)?\s*(없이|안\s*하고|하지\s*말고|생략|건너뛰고)"
    r"|(묻지|물어보지|질문하지|확인하지|검토하지|검수하지|멈추지)\s*(말고|않고)")
# '다음부터·앞으로·매번 … 묻지 말고/않고' 는 **방식 질문을 다시 하지 말라**는 말이지 검수를 빼라는 말이 아니다
# ('26-09-29 적대 검토 H1 재현: 질문에 "2번(함께 검수), 다음부터 묻지 않고 이대로"라고 답하면 바로 완성이
# 영구 저장됐다). 빼기보다 **먼저** 걷어 내고, 기억말로만 센다(주관 판정 '26-09-29).
_말투_다시묻지 = re.compile(
    r"(다음부터|다음번부터|앞으로\s*(?:는|도)?|이제부터|매번|또|다시는?|더\s*이상)\s*(?:\S+\s+){0,2}?"
    r"(묻지|물어보지|질문하지)\s*(말고|않고|마|말아)")
# 요청 한 줄에는 **문서 주제**도 섞여 온다("정책 바로알기 …", "주민과 함께 보듬는 …", "단계별로 추진하는 …",
# "한 번에 처리하는 원스톱 …"). 그래서 부사 하나만으로 잡지 않고 **만들라는 말(요청형 동사)** 이 곧바로
# (또는 두 낱말 안에) 따라올 때만 신호로 센다 — 정밀도 우선: 놓치면 한 번 묻고 끝나지만, 잘못 잡으면
# 검수를 조용히 건너뛴다('26-09-29 적대 검토 재현: 주제어 11줄 중 10줄 오판 → 0).
# 동사 뒤에 '-는·-던·-진·-신'이 붙으면 꾸미는 말이다("알아서 해주는 민원 챗봇", "만들어진 보고서") — 요청이 아니다
# (fixup3 '26-09-29, verify2 §1-D 재현).
_말투_동사 = (r"((?:만들어|만들자|작성해|작성하자|써\s*줘|써\s*주|뽑아|완성해|진행해|진행하자|끝내\s*줘|끝내\s*주"
             r"|해\s*줘|해\s*주|내\s*줘|내\s*주|가자|부탁)(?![는던진신]))")
# 검수를 빼라는 말이 **신호**가 되려면 요청 동사(또는 바로·그냥·끝까지 …)가 한 낱말 안에 따라와야 한다 —
# "검토 없이 진행된 사업", "승인 없이 집행한 예산", "검수 생략 관행", "편집기 없이도 열리게"는 문서 주제·형식
# 설명이다(verify2 §1-D: 조용한 건너뜀 8줄). 걷어 내기(_말투_빼기)는 넓게 그대로 둔다('편집기'가 함께로 안 잡히게).
_말투_빼기요청 = re.compile(
    r"(?:(?:검수|검토|확인|편집기|편집\s*화면|승인|리뷰)\s*(?:은|는)?\s*(?:없이|안\s*하고|하지\s*말고|생략하고|생략해|건너뛰고)"
    r"|(?:묻지|물어보지|질문하지|확인하지|검토하지|검수하지|멈추지)\s*(?:말고|않고))"
    r"\S*\s*(?:\S+\s+)?(?:" + _말투_동사[1:-1] + r"|바로|그냥|빨리|곧장|곧바로|끝까지|한\s*번에|결과만)")
# 함께 검수 신호도 **요청 동사 가까이**에서만 센다(M2 '26-09-29 재현: "민원 처리 결과를 확인하면서 느낀 점 …",
# "편집기로 작성된 문서를 …", "주민과 함께 보며 만드는 …"이 함께 검수로 잡혀 저장된 바로 완성을 덮었다).
# 편집기·편집 화면·같이·함께·…하며/하면서 바로 뒤(한 낱말 안)에 보자·보여·다듬·고치·만들어 따위가 와야 한다.
_말투_함께목적 = (r"(보자|봐|보여|보면서|보며|보고|볼게|볼래|열어|같이|함께|다듬|고치|고쳐|손보|수정|검토|확인|검수"
                r"|작업|만들어|만들자|작성해|작성하자|진행해|진행하자|해\s*줘|해\s*주|가자|하자|할게)")
_말투_함께 = re.compile(
    r"(편집기\s*(?:로|에서|로서)|편집\s*화면\s*(?:에서|으로|로))\s*(?:\S+\s+)?" + _말투_함께목적
    + r"|(같이|함께)\s*(보면서|보며|보자|봐|보고\s*싶|다듬|고치|고쳐|검토|확인|검수)\S*\s*(?:\S+\s+)?"
    + r"(" + _말투_동사[1:-1] + r"|보자|봐요|봐\s*줘|보고\s*싶|다듬자|고치자|검토하자|확인하자|하자|해요|할게|할래)"
    r"|(같이|함께)\s*(보자|봐요|봐\s*줘|보고\s*싶|다듬자|고치자|검토하자|확인하자|만들자|만들어요|만들어\s*봐요|만들어\s*봅시다)"
    # '보며·보면서' 홀로는 참고하라는 말이다("과거 사례를 보며 작성해줘", verify2 §1-D) — 검토·확인·검수만 센다.
    r"|(검토|확인|검수|컨펌)\s*하?\s*(며|면서)\s*(?:\S+\s+)?" + _말투_동사
    + r"|구성안?\s*(부터|먼저)"
    r"|(나오면|만들면|만든\s*뒤|만들고|되면)\s*(?:\S+\s+)?편집\s*(?:기|화면)\s*(?:을|를)?\s*(띄워|열어|보여)"
    r"|중간\s*중간\s*(?:\S+\s+)?(보여|확인|검토)"
    r"|(단계별로|단계마다|하나씩)\s*(?:\S+\s+)?((확인|검토|검수|컨펌)\s*(해\s*줘|해\s*주|하자|해요|받아|받으)"
    r"|(확인|검토|검수|보)\s*하?\s*(며|면서)\s*(?:\S+\s+)?" + _말투_동사
    + r"|보여\s*(줘|주)|물어\s*(봐|보)|멈춰|진행해|진행하자|가자)"
    r"|(같이|함께)\s*(작성해|써)\s*(봐요|봅시다|보자)"
    r"|내가\s*(직접\s*)?(고칠|다듬을|다듬|손볼|볼)\s*(게|수\s*있게)")
_말투_바로 = re.compile(
    r"바로\s*(완성|줘|주세요|" + _말투_동사[1:]
    + r"|(?<!빨리)(빨리|얼른|그냥|알아서|빠르게|신속하게|신속히|곧장|곧바로)(?!빨리)\s*(\S+\s+){0,2}?" + _말투_동사
    + r"|(한\s*번에|끝까지)\s*(\S+\s+)?" + _말투_동사 + r"|논스톱"
    # '한글'은 언어(한글로만 써 줘)와 형식(한글 파일로만)이 같은 낱말이다 — 파일·문서가 붙을 때만 형식으로 센다(M2).
    # '…만' 뒤에는 달라는 말이 곧바로 와야 한다 — "PDF만 있는 자료", "한글 파일만 받았는데"는 자료 설명이다(§1-D).
    r"|(결과|파일|완성본)\s*만\s*(줘|주[세시]|내\s*줘|받을게|받고\s*싶|받으면)"
    r"|(PDF|pdf|HWPX|hwpx|PPTX|pptx|한글\s*(?:파일|문서))\s*(로|으로)?\s*만\s*(줘|주[세시]|내\s*줘|받을게|받고\s*싶|받으면)")
# 기억말도 방식 말·요청 동사가 한 낱말 안에 붙을 때만 — "앞으로도 계속될 민원", "다음부터 적용되는 규정"은 주제다(§1-D).
_말투_기억 = re.compile(
    r"(?<![가-힣])(앞으로\s*(?:는|도|쭉)?|다음부터|다음번부터|이제부터|항상|매번|언제나|늘)\s*(?:\S+\s+)?"
    r"(이렇게|이대로|그렇게|그대로|바로|그냥|알아서|빨리|편집기|같이|함께|" + _말투_동사[1:-1] + r")"
    r"|앞으로\s*이런\s*(요청|문서|건)|(다음부터|다음번부터|앞으로|이제부터)\s*도\s*요"
    r"|(?<![가-힣])(다음부터|다음번부터|앞으로\s*(?:는|도)?|이제부터|매번|또|다시는?|더\s*이상)\s*(?:\S+\s+)?"
    r"(묻지|물어보지|질문하지)")


def _작업방식말투(글):
    """요청 한 줄 → (방식|None, 기억말 있나) — **힌트**다(fixup3 주관 판정 '26-09-29: 방식은 에이전트가 대화를
    읽고 정해 방식 인자로 넘기고, 이 판별은 명시 방식을 절대 이기지 않는다). 함께 검수 신호가 바로 신호보다
    앞선다("빨리 편집기로 보자"는 함께 검수) — 검수를 빼라는 말("편집기 없이")은 먼저 걷어 낸다. 애매하면 None."""
    s = str(글 or "").strip()
    if not s:
        return None, False
    남은 = _말투_다시묻지.sub(" ", s)       # '다음부터 묻지 않고'는 방식 신호가 아니다(H1) — 기억말로만 센다
    뺌 = bool(_말투_빼기요청.search(남은))
    남은 = _말투_빼기.sub(" ", 남은)
    if _말투_함께.search(남은):
        방식 = "함께검수"
    elif 뺌 or _말투_바로.search(남은):
        방식 = "바로완성"
    else:
        방식 = None
    return 방식, bool(방식 and _말투_기억.search(s))


def _방식정규화(v):
    s = re.sub(r"\s+", "", str(v or ""))
    별 = {"바로": "바로완성", "바로완성": "바로완성", "direct": "바로완성", "auto": "바로완성",
         "함께": "함께검수", "함께검수": "함께검수", "같이검수": "함께검수", "review": "함께검수"}
    return 별.get(s) or 별.get(s.lower())


# 이번 대화(= 이 MCP 프로세스 · 같은 자료뿌리·세션 열쇠)에서 정한 방식과 '물었나'(M6·M1, '26-09-29).
# stdio MCP 는 프로세스가 곧 대화라고 봤는데, 같은 서버가 /clear·채팅 바꾸기를 넘어 살 수 있다(verify3 §1 — 앞
# 채팅의 '이번만 바로'가 새 채팅에서 묻지 않고 쓰였다). 그래서 칸에 **무활동 수명**(_대화칸_수명초)을 둔다 —
# 마지막으로 쓴 뒤 그만큼 지나면 버린다(fixup4 주관 ⑤).
# CLI 는 대화 경계를 전혀 모른다. fixup3 가 세션 방(대화방식.json)에 3시간 두던 '최근'은 같은 뿌리의 동시 대화를
# 섞고 새 대화에 앞 대화의 방식을 물려줬다(verify3 §6 C3·C4·C8) — 걷어 냈다. CLI 넛지는 **그 호출에 실린
# work_mode** 만 따르고, 없으면 두 방식을 다 적는다(_알려진방식). 방식을 요청마다 싣는 것은 에이전트 몫(SKILL).
_이번대화 = {}
_대화칸_수명초 = 2 * 3600
# 이번 호출에 실린 방식(work_mode) — 방식 인자를 받지 않는 작업(새문서·저장·편집기열기 …)에 실려 오면 부르기()가
# 떼어 여기 둔다(CLI 넛지용). 스레드·호출마다 따로 산다.
_호출방식 = contextvars.ContextVar("문서지능_호출방식", default=None)


def _CLI표면():
    return (os.environ.get("문서지능_표면") or "").strip() == "cli" and not os.environ.get("문서지능_웹앱")


def _대화칸():
    try:
        열쇠 = 자료뿌리.세션열쇠()
        k = (자료뿌리.기본뿌리(), 열쇠)
    except Exception:
        열쇠, k = "", ("", "")
    if not 열쇠 and _공유연결():
        # 세션 열쇠 없는 공유 연결(`mcp/server.py --http` — 토큰 미들웨어가 아직 없어 열쇠가 안 끼워진다)에서는 붙는
        # 사람 모두가 같은 칸을 본다(verify2 §2-D: A 의 답이 B 의 '이번 대화'가 됐다). 대화 기억을 끈다 — 부를
        # 때마다 빈 칸이고 어디에도 안 쓴다.
        return {"답": None, "최근": None, "물었나": False, "공유": True}
    지금 = time.time()
    칸 = _이번대화.get(k)
    if 칸 is None or 지금 - float(칸.get("마지막") or 지금) > _대화칸_수명초:
        칸 = {"답": None, "최근": None, "물었나": False}
        _이번대화[k] = 칸
    칸["마지막"] = 지금
    return 칸


def _공유연결():
    """여러 사람이 붙는 플러그인 연결인가 — 공유 MCP(`mcp/server.py --http`, 토큰마다 세션 열쇠).
    거기서 개인설정.json(기본 뿌리 한 파일)에 방식을 쓰면 한 사람의 선택이 모두의 방식이 된다(M3)."""
    try:
        if 자료뿌리.세션열쇠():
            return True
    except Exception:
        return True
    main = str(getattr(sys.modules.get("__main__"), "__file__", "") or "").replace("\\", "/")
    return "--http" in sys.argv and main.endswith("mcp/server.py")


def _저장된방식읽기():
    if _여러사람웹앱() or _공유연결():
        return None
    try:
        칸 = (json.load(open(_개인설정길(), encoding="utf-8")) or {}).get("작업방식")
    except (OSError, ValueError, AttributeError):
        return None
    return 칸.get("방식") if isinstance(칸, dict) and 칸.get("방식") in _작업방식들 else None


def _알려진방식():
    """넛지가 쓸 방식 — 이 호출에 실린 방식(work_mode) → (MCP 만) 이 대화에서 작업방식(보기)이 알려 준 것 → 저장된
    선택 → None(모름: 두 갈래를 다 적는다). CLI 는 호출에 실린 방식만 본다(대화를 모른다 — fixup4 ⑤).
    웹앱은 None(화면이 흐름을 쥔다)."""
    if os.environ.get("문서지능_웹앱"):
        return None
    m = _호출방식.get()
    if m:
        return m
    if _CLI표면():
        return None
    return _대화칸().get("최근") or _저장된방식읽기()


def _갈래(함께말, 바로말, 머리=True):
    """넛지 한 줄 — 방식을 알면 그 갈래만, 모르면 두 갈래를 다 적는다. 함께 검수로 정해진 대화에는
    '스스로 승인하라' 같은 바로 완성 갈래를 싣지 않는다(M1 '26-09-29 재현)."""
    m = _알려진방식()
    if m == "함께검수":
        return ("함께 검수: " if 머리 else "") + 함께말
    if m == "바로완성":
        return ("바로 완성: " if 머리 else "") + 바로말
    return f"함께 검수면 {함께말} / 바로 완성이면 {바로말}"


@등록("작업방식", ["방식", "결정", "요청"], 읽기=False, 비동기=False,
    설명="플러그인 작업 방식(바로 완성=검수 없이 끝까지 / 함께 검수=판정·구성 승인·편집기 리터칭에서 멈춤)을 "
        "고른다. 방식은 에이전트가 대화(와 방식 질문의 답)를 읽고 정해 방식 인자로 넘긴다. 결정=보기(기본): 넘긴 "
        "방식→이번 대화에서 정한 방식→저장된 선택 순으로 알려 주고, 셋 다 없으면 물을까=true(한 대화에 한 번). "
        "요청 글은 말투 **힌트**(값.힌트)로만 읽고 방식을 이기지 않는다. 저장+방식=다음부터 묻지 않음(저장은 방식 "
        "인자 필수, 요청 글만으로는 저장하지 않는다). 지우기=다시 묻기. 웹앱·공유 MCP 에서는 저장 거절",
    en="workmode")
def 작업방식(방식="", 결정="보기", 요청=""):
    if _여러사람웹앱():
        return {"ok": False, "로그": "웹앱은 편집 화면에서 단계마다 확인하며 만듭니다 — 진행 방식 설정은 "
                                   "플러그인에서만 씁니다"}
    결정 = str(결정 or "보기").strip()
    if 결정 not in ("보기", "저장", "지우기"):
        return {"ok": False, "로그": f"결정은 보기·저장·지우기 가운데 하나입니다 (받은 값: {결정})"}
    지정 = None
    if str(방식 or "").strip():
        지정 = _방식정규화(방식)
        if not 지정:
            return {"ok": False, "로그": f"방식은 바로완성·함께검수 가운데 하나입니다 (받은 값: {방식})"}
    공유 = _공유연결()
    if 공유 and 결정 in ("저장", "지우기"):
        # 공유 MCP 는 붙는 사람 모두가 기본 뿌리 한 곳을 본다 — 여기 쓰면 남의 검수까지 꺼진다(M3).
        return {"ok": False, "로그": "여러 사람이 함께 쓰는 연결(공유 MCP·세션 열쇠가 붙은 연결)에서는 진행 방식을 "
                                   "저장하지 않습니다 — 이번 요청의 방식은 말로 정하고 결정=보기에 방식을 실어 주세요"}
    말, 기억 = _작업방식말투(요청)
    길 = _개인설정길()

    def _읽기():
        try:
            d = json.load(open(길, encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}
    설정 = {} if 공유 else _읽기()
    칸 = 설정.get("작업방식")
    저장된 = 칸.get("방식") if isinstance(칸, dict) and 칸.get("방식") in _작업방식들 else None
    대화 = _대화칸()
    로그 = ""
    # 쓰기는 빗장 **안에서 다시 읽어** 고친다 — 같은 파일을 편집기 서버의 개인기본모양도 쓰므로, 빗장 밖에서
    # 읽은 것을 통째로 쓰면 그 사이 남이 쓴 제목모양기본이 사라진다(fixup '26-09-29 끼어들기 재현).
    if 결정 == "저장":
        # 저장은 **방식 인자가 있을 때만** 한다(fixup3 주관 판정 '26-09-29) — 답 글·요청 글은 코어가 읽지 않는다.
        # 에이전트(언어 모델)가 대화와 답("바로 완성은 싫고 함께 검수로", "그냥 2번")을 읽고 정한 방식을 넘긴다.
        # 말투 판별로 저장하던 길은 부정·까닭("검수 없이 하는 건 불안해서 2번")을 못 갈라 반대 방식을 영구
        # 저장했다(verify2 §1-A: 40길 중 28길).
        if not 지정:
            return {"ok": False, "로그": "저장할 방식이 없습니다 — 대화와 사용자의 답을 읽고 정한 방식"
                                       "(바로완성·함께검수)을 방식(work_mode)에 실어 주세요. 요청 글만으로는 "
                                       "저장하지 않습니다"}
        고른 = 지정
        with 자료뿌리.빗장(길):
            설정 = _읽기()
            설정["작업방식"] = {"방식": 고른, "정한때": time.strftime("%Y-%m-%dT%H:%M:%S")}
            자료뿌리.원자json(길, 설정, ensure_ascii=False, indent=1)
        저장된 = 고른
        대화.update({"답": None, "최근": 고른})     # 새로 저장한 선택이 이 대화의 앞선 답보다 나중 결정이다
        로그 = ({"바로완성": "앞으로는 바로 완성으로 만듭니다.", "함께검수": "앞으로는 함께 검수로 만듭니다."}[고른]
               + " " + ("편집 화면에서 같이 보고 싶으시면 '이번엔 편집기로 보자'라고 말씀해 주세요."
                        if 고른 == "바로완성" else "빨리 받고 싶으시면 '바로 만들어줘'라고 말씀해 주세요."))
    elif 결정 == "지우기":
        if "작업방식" in 설정:
            with 자료뿌리.빗장(길):
                설정 = _읽기()
                if 설정.pop("작업방식", None) is not None:
                    자료뿌리.원자json(길, 설정, ensure_ascii=False, indent=1)
        저장된 = None
        대화.update({"답": None, "최근": None, "물었나": False})     # '다시 물어봐' — 이 대화에서도 다시 묻는다
        로그 = "다음 요청 때 진행 방식을 다시 여쭙니다."
    if 결정 == "보기" and 지정:
        대화["답"] = 지정            # 에이전트가 정한 방식(질문의 답 포함) — 저장은 안 함, 이 대화에서만 따른다
    # 이번 요청의 방식: 에이전트가 넘긴 방식 → 이 대화에서 정한 방식 → 저장된 선택. 요청 말투는 **힌트**로만
    # 돌려주고 어느 것도 이기지 않는다(fixup3 주관 판정 — verify2 §1-A b·c길: 방식을 실어도 같은 호출의 요청
    # 글이 말투로 방식을 뒤집어 함께 검수를 고른 사람의 첫 문서가 바로 완성으로 나갔다. §1-D: 주제어 말투가
    # 저장된 함께 검수를 덮었다).
    if 지정:
        지금, 근거 = 지정, "지정"
    elif 대화.get("답"):
        지금, 근거 = 대화["답"], "이번 대화"
    elif 저장된:
        지금, 근거 = 저장된, "저장"
    else:
        지금, 근거 = None, "없음"
    물을까 = False
    # 말투 힌트는 로그에 싣지 않는다(fixup4 주관 ⑧, verify3 §1: "바로 완성 말고요"를 '바로 완성'으로 읽은 힌트가 로그 끝에
    # 붙어 에이전트를 반대로 이끌었다). 값.힌트 에만 둔다 — 방식은 에이전트가 대화를 읽고 정한다.
    if 결정 == "보기":
        if 지금 is None and not 대화.get("물었나"):
            물을까 = True
            대화["물었나"] = True
            로그 = ("에이전트가 넘긴 방식도, 이 대화에서 정한 방식도, 저장된 선택도 없습니다 — 대화를 읽어 사용자가 "
                   "방식을 분명히 말했으면 묻지 말고 그 방식을 방식(work_mode)에 실어 다시 부르세요. 아니면 지금 한 "
                   "번만 물으세요: ① 바로 완성(검수 없이 끝까지, 확인할 곳은 끝에 모아 알림) ② 함께 검수(구성안 "
                   "확인·편집 화면에서 다듬은 뒤 내보냄) + '앞으로도 이대로'. 답은 에이전트가 읽고 정한 방식을 실어 "
                   "다시 부르세요 — '앞으로도 이대로'면 결정=저장, 아니면 결정=보기")
        elif 지금 is None:
            # 한 대화에서 두 번 묻지 않는다(M6) — 답을 못 받았으면 멈추는 쪽(함께 검수)으로 간다.
            지금, 근거 = "함께검수", "기본"
            로그 = ("이 대화에서 이미 한 번 물었습니다 — 다시 묻지 말고, 사용자가 답한 방식을 방식 인자로 "
                   "알려 주세요(결정=보기면 이번 대화만, 저장이면 다음부터). 답이 없었으면 함께 검수로 갑니다")
        else:
            로그 = (f"이번 요청은 {_방식별말[지금]}("
                   + {"지정": "에이전트가 정한 방식", "이번 대화": "이 대화에서 정한 방식",
                      "저장": "저장된 선택"}[근거] + ")")
            if _CLI표면():
                로그 += (" — CLI 는 대화를 기억하지 않습니다. 이 방식을 뒤 호출(new·save·editor·export …)에도 "
                        "work_mode 로 실어 부르세요(안 실으면 안내가 두 방식을 다 적습니다)")
    if 지금:
        대화["최근"] = 지금
    return {"ok": True, "값": {"방식": 지금, "근거": 근거, "물을까": 물을까, "저장된방식": 저장된,
                             "힌트": {"방식": 말, "기억": 기억}, "말투": {"방식": 말, "기억": 기억},
                             "산출물자리": _내보낼곳()},
            "로그": 로그}


# ── 쓰기 ────────────────────────────────────────────────────────────────

# 자동 저장은 몇 초마다 온다. 그때마다 판을 만들면 되돌릴 지점이 수백 개가 되어
# 오히려 못 찾는다. 이력(기록)은 매번 남기고, **판은 이 간격을 지나야** 만든다.
#
# **왜 serve.py 에서 여기로 옮겼나 (2026-08-07, WP-S4)** — 예전에는 이 정책이
# serve.py 의 `반영()` 안에 있었고, `/api/저장` 만 `이름=="저장"` 특수분기로 그 길을
# 탔다. 그래서 원격 `부르기("저장", {"payload": …})` 가 오면 `반영()` 이 그 **바깥
# 봉투**를 payload 로 알고 한 겹 더 감쌌다 — 문서 이름을 못 찾아 "어느 문서인지 알
# 수 없습니다" 로 끝났다(S1 이 남긴 경고). 정책이 코어에 있으면 특수분기가 필요
# 없고, 세 문(웹앱·CLI·MCP) 이 같은 판 간격을 쓴다.
판_간격초 = 300
_마지막판 = {}


# 2층 빌드플랜(_설계지시문조립 의 "[돌려줄 것]" 스키마, 아래 2704행 부근)에만 있는
# 최상위 키 — 3층 문서(초안) 스키마 어디에도 이 이름들은 안 쓴다(_문서모양키 처럼
# "판정"·"승인" 같은 낱말이 온톨로지 규칙 설명 안에는 나오지만 doc 최상위 키로는
# 안 쓰인다, ontology.json 확인). 저장()의 "플랜 대상 거절" 가드가 이 함수로 doc 가
# 플랜 그 자체인지를 가른다(F1) — genre 유무로 가르면 genre 없는 정상 문서(1p 예시가
# 그렇다)까지 가드를 빠져나간다.
_플랜전용키 = ("요구분석", "개체구성", "적용방법론", "본문순서", "등장요소_전망",
           "미확정_3층위임", "request")


def _플랜모양인가(d):
    """payload.doc 이 실은 2층 빌드플랜(구성 설계) JSON인가 — 플랜에만 있는 키로 가른다."""
    if not isinstance(d, dict):
        return False
    if any(k in d for k in _플랜전용키):
        return True
    승인 = d.get("승인")
    if isinstance(승인, dict) and "status" in 승인:
        return True
    판정 = d.get("판정")
    if isinstance(판정, dict) and ("보고목적유형" in 판정 or "문서유형" in 판정):
        return True
    return False


def _A정규화_시도(모듈이름, 함수이름, doc):
    """구현자 A 의 정규화 모듈(build/붙임꼴.py·build/조번호꼴.py)을 부른다 — 이 묶음이
    먼저 커밋될 수 있어 아직 파일이 없을 수 있다(try-import, r9). 있으면 doc 를
    제자리에서 고치고, 없거나 실패하면 조용히 건너뛰되 **소프트 알림**은 남긴다
    (호출부가 로그에 그대로 붙인다 — 조용한 성공도 조용한 실패도 아니다).

    r9 검토자 발견(asm-correctness·loop-channels·regression, 같은 근본원인을 세 검토자가
    각자 잡아 세 번 적었다) — 예전엔 fn(doc) 의 반환값(맞추기() 의 정정 목록·분리하기()
    의 옮긴 수)을 버리고 늘 None 을 돌려줬다. 그 결과 새문서·저장 두 입구 모두에서 내용이
    (주요내용 조번호·본문의 붙임 표시)가 조용히 다시 쓰여도 로그 어디에도 안 남았다
    (재현: api_new_silent.py — 규정·공문 두 장르 다 정정 언급 0건). 반환값이 비어 있지
    않으면 짧게 알린다."""
    try:
        모듈 = 자료뿌리.모듈(모듈이름)
    except Exception:
        return None      # 아직 A 가 파일을 안 만들었다 — 정상 경로, 알릴 것도 없다
    fn = getattr(모듈, 함수이름, None)
    if fn is None:
        return f"{모듈이름}.py 는 있지만 {함수이름}() 함수가 없어 건너뛰었습니다"
    try:
        결과 = fn(doc)
    except Exception as e:
        return f"{모듈이름}.{함수이름}() 을 불렀지만 실패({type(e).__name__}) — 정규화를 건너뛰었습니다"
    if isinstance(결과, list) and 결과:
        return (f"{모듈이름}.{함수이름}() 이 {len(결과)}곳 정정: "
                + "; ".join(str(x)[:60] for x in 결과[:5])
                + (f" 외 {len(결과) - 5}곳" if len(결과) > 5 else ""))
    if isinstance(결과, int) and 결과 > 0:
        return f"{모듈이름}.{함수이름}() 이 {결과}건을 옮겼습니다"
    return None       # 바뀐 것 없음 — 잡음을 늘리지 않는다(문제 있을 때만 로그에 남긴다)


def _B정규화_시도(doc, 장르):
    """구현자 B 의 표기 교정층(build/표기꼴.py)을 부른다 — _A정규화_시도(위)와 짝이지만,
    이 모듈은 이번 커밋에 함께 실려 파일이 없을 리 없어(try-import 로 존재 자체를 봐줄
    필요가 없어) 자료뿌리.모듈로 바로 부르고 **실행 실패만** 감싼다(표기 교정은 부가
    기능이라 그 안의 버그가 새문서·저장 전체를 막으면 안 된다).

    새문서·저장 두 입구가 '장르'를 서로 다른 말로 준다 — 새문서는 등록부 이름
    ("samples"·"press" …), 저장은 doc.genre 값("onepage"·"press-release" …). 표기꼴.교정()
    이 이 둘을 다 받아 스스로 가른다(아래 모듈 docstring) — 여기선 그대로 넘기기만 한다."""
    try:
        모듈 = 자료뿌리.모듈("표기꼴")
        결과 = 모듈.교정(doc, 장르)
        # 문장 중간이라 고치지 못한 자기 호칭 — 한 문서 안에서 약칭과 섞였을 때만 나온다.
        섞임 = 모듈.섞인호칭(doc, 장르) if hasattr(모듈, "섞인호칭") else []
    except Exception as e:
        return f"표기꼴.교정() 을 불렀지만 실패({type(e).__name__}) — 표기 교정을 건너뛰었습니다"
    줄 = []
    if isinstance(결과, list) and 결과:
        줄.append(f"표기꼴.교정() 이 {len(결과)}곳 고침: "
                 + "; ".join(str(x)[:60] for x in 결과[:5])
                 + (f" 외 {len(결과) - 5}곳" if len(결과) > 5 else ""))
    if 섞임:
        줄.append(f"자기 호칭이 섞였습니다 {len(섞임)}곳(확인 필요, 고치지 않음): "
                 + "; ".join(f"{p} 「{곁}」" for p, 곁 in 섞임[:3])
                 + " — 이 문서 자신을 가리키는 말이면 다른 곳처럼 약칭으로 맞추세요")
    return "\n▸ ".join(줄) or None     # 바뀐 것 없음 — 잡음을 늘리지 않는다(부르는 쪽이 첫 줄에 ▸ 를 붙인다)


def _규정선택키_정규화(doc):
    """규정 선택키(제정이유·주요내용) 모양을 **정본 자체에서** 고정한다(assemble:F8 (a),
    '26-09-27) — build/assemble_regulation.py 의 _제정이유_정규화·_주요내용_정규화는
    화면에 낼 때만 문자열↔배열을 서로 바꿔 보여주고, 등록부에 저장되는 정본 doc 는
    그대로 둔다. 그래서 정본이 문자열인데 편집기가 배열로 알고 setPath(doc,
    '주요내용.0', …)를 하면 조용히 무시된다(재현됨, F8). 여기서 **정본 자체를** 조립기
    출력과 같은 모양으로 고쳐 저장한다 — 제정이유는 문자열(배열이면 이어 붙인다),
    주요내용은 배열(문자열이면 [문자열]로 감싼다). 새문서·저장 두 입구 모두에서 부른다.

    '확인요청'(reg13d 판정 D1, '26-10-01) — 작성 모델이 스스로 정한 것을 적는 칸을 문서에서 **떼어 돌려준다**. 등록부에 남기면
    지어냈나·문체검사·확인할것 빈칸 걷기가 문서 글로 읽는다. 새문서는 돌려받은 것을 확인 물음으로 옮기고, 저장은 버린다."""
    if not isinstance(doc, dict):
        return None
    if "제정이유" in doc:
        v = doc.get("제정이유")
        if isinstance(v, list):
            doc["제정이유"] = " ".join(str(x).strip() for x in v if str(x).strip())
    if "주요내용" in doc:
        v = doc.get("주요내용")
        if isinstance(v, str):
            doc["주요내용"] = [v] if v.strip() else []
    return doc.pop("확인요청", None)


def _저장키(payload):
    """이 payload 가 어느 문서를 고치는가 — 판 간격을 세고 수정시각을 되돌려 주는 데 쓴다.

    못 찾아도 **거절하지 않는다.** apply_edit_any 는 payload 모양을 더 많이 알고
    (구성 설계·plan_id) 스스로 대상을 찾는다. 여기서 못 찾으면 판 간격만 못 재는
    것이라, 그때는 `판없이` 를 손대지 않고 부르는 쪽이 준 값 그대로 간다.
    """
    doc = payload.get("doc") if isinstance(payload, dict) else None
    doc = doc if isinstance(doc, dict) else {}
    return doc.get("filename") or doc.get("plan_id") or (payload or {}).get("key")


# 승인필요 — 저장은 명세(WP-S3)가 지목한 조립·새문서에 없지만, apply_edit_any 가
# **재조립까지 하므로** 열어 두면 "답 없이 기존 문서에 내용을 쓰고 다시 조립하는"
# 우회로가 된다(구현계획.md §3 WP-S3 완료 기준의 '우회로 없음'). 셋이 같이 막혀야
# 관문이 관문이다.
@등록("저장", ["payload", "판없이", "key", "doc", "검사", "원문", "자료파일"], 읽기=False, 승인필요=True,
    설명="편집 결과를 정본에 반영하고 이력을 남긴 뒤 다시 만든다. "
        "정식 모양은 payload={'doc':{...},...} 지만 최상위 {key, doc} 로 불러도 자동으로 감싼다. "
        "검사=true 면 반영한 판에 문체검사·조판게이트·지어냈나(원문이 있을 때)를 돌려 붙인다 — 플러그인 "
        "내보내기는 지금 판의 이 검사 기록을 본다. 자료파일(생략 가능)은 이 문서에 쓴 받은 자료 파일 이름 목록 — "
        "CLI 는 파일읽기로 읽은 파일 이름을 모두 싣는다(첨부 사진 알림을 이 목록으로 센다)",
    en="save")
def 저장(payload=None, 판없이=None, key=None, doc=None, 검사=None, 원문="", 자료파일=None):
    try:        # 그림 카드 범위 — 이 대화의 자료를 이 문서에 묶는다(편집기 다시 굽기 전에, _그림범위)
        _봉 = payload if isinstance(payload, dict) else {}
        _묶을doc = doc if isinstance(doc, dict) else (_봉.get("doc") if isinstance(_봉.get("doc"), dict) else None)
        _그림문서묶기(str(key or (_묶을doc or {}).get("filename") or _봉.get("key") or "").strip(), _묶을doc, 원문, 자료파일)
    except Exception as _e:
        print(f"[그림] 저장 묶기 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    본 = _저장본(payload, 판없이, key, doc)
    키 = str(key or (doc.get("filename") if isinstance(doc, dict) else "")
            or ((payload.get("doc") or {}).get("filename") if isinstance(payload, dict)
                and isinstance(payload.get("doc"), dict) else "")
            or (payload.get("key") if isinstance(payload, dict) else "") or "").strip()
    if 본.get("ok") and 키:
        _산출지문적기(키)          # 저장이 다시 조립한 산출 HTML 지문(X5)
    건너뜀 = False
    if 검사 and 본.get("ok") and 키:
        # 저장 뒤 검사(H2, '26-09-29) — 새문서와 같은 세 검사를 이 판에 돌려 기록을 새로 한다. 원문은 이 문서가
        # 처음 받은 것을 쓴다(fixup3 — 원문을 빼고 저장해 지어냄 FAIL 을 '건너뜀'으로 세탁하던 길, verify2 X1).
        값 = {"문체검사": 문체검사(key=키), "조판게이트": 조판게이트(key=키)}
        요약 = [f"문체검사 {'PASS' if 값['문체검사'].get('ok') else 'FAIL'}",
              f"조판게이트 {'PASS' if 값['조판게이트'].get('ok') else 'FAIL'}"]
        쓸원문, _ = _검사원문(키, 원문)
        if 쓸원문.strip():
            값["지어냈나"] = 지어냈나검수(키, 원문 if str(원문 or "").strip() else 쓸원문)
            요약.append(f"지어냈나 {'PASS' if 값['지어냈나'].get('ok') else 'FAIL'}")
            # 확장 칸(출처·월·붙임 …)도 새문서와 같은 모양으로 싣는다 — 검사 켠 저장 뒤 확인할것에서 출처 줄이 빠졌다(X4,
            # wire_verify §3-4: 이름 줄 '총무처'만 남았다). 지어냈나검수 와 같은 원문(처음 받은 것)으로 잰다.
            try:
                _확장 = 자료뿌리.모듈("지어냈나").검토하기(_자료글(쓸원문), 문서(키).get("값") or {})
                if _확장:
                    값["지어냈나확장"] = {"ok": False, "걸림": _확장}
            except Exception as _e:
                print(f"[지어냈나확장] 저장 검사 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
        else:
            _검사적기(키, "지어냄", True, 건너뜀="원문 없음")
            요약.append("지어냈나 건너뜀(원문 없음)")
            건너뜀 = True
        본 = dict(본)
        본["값"] = 값
        본["로그"] = (본.get("로그") or "") + "\n▸ 검사 결과: " + " · ".join(요약)
    # 끝 보고의 '확인할 것'은 저장 응답에도 싣는다(fixup3 E — 바로 완성이 save 로 고친 뒤에도 목록이 있어야 한다).
    if 본.get("ok") and 키 and not os.environ.get("문서지능_웹앱"):
        try:
            지금doc = (문서(키).get("값") or {})
            본 = dict(본)
            # 확인 물음·본문 출처('26-09-30 W1·W2)는 이 문서가 처음 받은 원문(보관본)으로, 없으면 이번에 받은 원문으로 잰다
            try:
                _확원 = str((_검사자료읽기().get(str(키)) or {}).get("원문") or "")
            except Exception:
                _확원 = ""
            _확원 = _확원 or (str(_자료글(원문)) if 원문 else "")
            본["확인할것"] = _확인할것모으기(지금doc, 지금doc.get("genre") or "samples", [], [], [], [],
                                        본.get("값") if isinstance(본.get("값"), dict) else {}, key=키, 건너뜀=건너뜀,
                                        원문확인=_원문확인줄(지금doc, 지금doc.get("genre") or "samples", _확원))
        except Exception as e:
            print(f"[확인할것] 저장 목록 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    return 본


def _저장본(payload=None, 판없이=None, key=None, doc=None):
    """`판없이` 를 안 주면(None) **판 간격으로 스스로 정한다** — 자동 저장이 초마다
    와도 판은 `판_간격초` 에 하나만 남는다. 명시로 주면 그 값이 이긴다(관리·시험용).

    (2026-09-26, 벤치마크 진단 — 항목 4 '저장 인자 마찰') payload 봉투({doc,
    instructions, ops})가 안내되지 않아 에이전트가 문서마다 소스를 읽었다:
    (a) 최상위 {key, doc} 로 불러도 봉투를 자동으로 씌우고, doc 에 genre 가 없으면
        저장된 문서에서 채운다.
    (b) _수정시각 없이 부르면(경합 보호는 그대로 거절하되) 지금 저장된 값과 그대로
        다시 보낼 수 있는 모양을 거절 메시지에 담는다 — apply_edit_any.py 는 다른
        묶음이 만지므로 여기(래퍼)에서 로그에 덧붙인다.

    (2026-09-26 2차 진단 — 항목 0, 실제 재현된 결함) 위 (a)에서 key 만 주고 doc.filename
    을 비우면, 문서에 plan_id 가 있을 때 apply_edit_any.py(이 묶음 밖 파일)의 대상 우선순위
    (doc.filename → doc.plan_id → payload.key)가 plan_id 로 넘어가 **승인된 빌드플랜
    파일을 문서 내용으로 통째로 덮어썼다**(ok:true 로 성공한 것처럼 보이면서). 그 우선순위는
    고치지 못하므로 여기서 (i) key 로 filename 을 채우고 서로 다르면 거절, (ii) 문서 모양
    (genre)인데 filename 이 등록부에 없고 plan_id 만 있으면 plan_id 로 새는 것을 미리 막는다.
    """
    if not isinstance(payload, dict):
        if isinstance(doc, dict) or key:
            payload = {}
            if isinstance(doc, dict):
                payload["doc"] = doc
            if key:
                payload["key"] = key
        else:
            return {"ok": False, "로그": "payload 가 객체가 아닙니다 — "
                                      "편집 결과 한 벌({doc, ops, …}) 또는 최상위 "
                                      "{key, doc} 를 주세요"}
    _doc = payload.get("doc")
    _A정규화알림 = None      # gongmun 붙임꼴 정규화 소프트 알림(r9) — doc 아니면 그대로 None
    _B정규화알림 = None      # 표기꼴 교정(구현자 B) 소프트 알림 — doc 아니면 그대로 None
    if isinstance(_doc, dict):
        # key 로 filename 을 채운다(항목 0) — {key, doc} 로 부르는데 doc.filename 이
        # 비어 있으면 대상이 plan_id 로 새는 길이 열린다(위 docstring). 서로 다르면 —
        # 어느 쪽이 맞는 문서인지 알 수 없으니 조용히 하나를 고르지 않고 거절한다.
        _키인자 = str(payload.get("key") or "").strip()
        _doc파일명 = str(_doc.get("filename") or "").strip()
        if _키인자 and _doc파일명 and _키인자 != _doc파일명:
            return {"ok": False, "로그": f"key(\"{_키인자}\")와 doc.filename(\"{_doc파일명}\") "
                    "이 서로 다릅니다 — 어느 문서를 저장할지 알 수 없어 거절합니다."}
        if _키인자 and not _doc파일명:
            _doc["filename"] = _키인자
            _doc파일명 = _키인자
        if not _doc.get("genre"):
            _키후보 = (_doc파일명 or _키인자)
            if _키후보:
                _기존장르 = (문서(_키후보).get("값") or {}).get("genre")
                if _기존장르:
                    _doc["genre"] = _기존장르
        # 표기꼴 교정(항목①·②) — 저장(편집 반영) 입구에서도 부른다. 금액 단위 띄어쓰기는
        # 장르 무관, 자기 호칭 통일(회사→약칭)은 표기꼴.교정() 안에서 규정·시행문·보도자료로
        # 좁힌다 — 여기서 장르로 미리 가르지 않는다(편집기에서 사람이 손으로 고친 표기도
        # 같은 규칙으로 다시 훑는다, 붙임꼴.분리하기() 와 같은 취지).
        # reg13e 판정 E4('26-10-01) — 규정 '확인요청' 칸은 표기 교정 **전에** 뗀다(저장은 버린다 — 교정 기록에 그 칸이 나오지 않게).
        if _doc.get("genre") == "regulation":
            _doc.pop("확인요청", None)
        _B정규화알림 = _B정규화_시도(_doc, _doc.get("genre"))
        if _doc.get("genre") == "slides":
            # 자리표시뿐인 출처('○○')는 저장할 때 뺀다('26-09-30 주관 판정 W1 — 출처는 ○○로 둘 칸이 아니다). 교정적용도 이 길로 저장한다
            _출처빈칸알림 = _슬라이드출처빈칸빼기(_doc)
            if _출처빈칸알림:
                _B정규화알림 = "\n▸ ".join(x for x in (_B정규화알림, _출처빈칸알림) if x)
            # 옛 판형은 등록부에 쓰기 **전에** 조판 게이트를 잰다('26-09-30 주관 판정 X1 — 인용 장의 말한 사람을 뺀 저장이 정본을 먼저
            # 쓰고 조립에서 실패해 깨진 판이 남았다, wire_verify §1). 편집 전부터 있던 위반은 막지 않는다(새로 생긴 위반만 — v2 는
            # apply_edit_any 가 같은 방식으로 이미 잰다). 문구는 편집기가 읽는 '판 규칙에 걸려 저장하지 않았습니다' 그대로다.
            if isinstance(_doc.get("슬라이드"), list) and not str(_doc.get("판형") or "") == "v2":
                _새위반 = _장르게이트확인(_doc)
                if _새위반:
                    import collections as _col
                    _옛doc = 문서(str(_doc.get("filename") or payload.get("key") or "")).get("값") or {}
                    _옛위반 = _col.Counter(_장르게이트확인(_옛doc) if isinstance(_옛doc, dict) and _옛doc else [])
                    _막힘 = []
                    for _b in _새위반:
                        if _옛위반[_b] > 0:
                            _옛위반[_b] -= 1
                        else:
                            _막힘.append(_b)
                    if _막힘:
                        return {"ok": False, "로그": "  ✗ 판 규칙에 걸려 저장하지 않았습니다 — 고친 곳을 되돌리거나 바꿔 주세요\n"
                                + "\n".join(f"    · {b}" for b in _막힘[:5])
                                + (f"\n    · … 외 {len(_막힘) - 5}건" if len(_막힘) > 5 else "")}
        try:        # 그림 스펙 글 칸의 올린 파일 이름 걷기 — 새문서와 같은 함수(fixup3 N1). 사람이 고른 그림은 바꾸지 않는다
            _그림저장정리(_doc)
        except Exception as _e:
            print(f"[그림] 저장 글 정리 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
        if _doc.get("genre") == "regulation":
            _규정선택키_정규화(_doc)
            # 조번호꼴.맞추기() 는 **새문서 입구에서만** 부른다(아래 새문서 참고) — 저장(편집
            # 반영) 입구에서 부르면 사람이 편집기에서 손으로 고친 조 번호·구조를 저장할 때마다
            # 되돌릴 위험이 있다(r9 설계 지침). 저장 입구는 선택키 모양 고정만 그대로 한다.
        elif _doc.get("genre") == "gongmun":
            # 붙임꼴.분리하기() 는 두 입구 모두에서 부른다 — 편집기에서 본문에 "붙임 …"
            # 줄을 손으로 다시 쳐 넣어도(사람이 낼 수 있는 실수) 같은 규칙으로 갈라낸다.
            _A정규화알림 = _A정규화_시도("붙임꼴", "분리하기", _doc)
        # 문서 저장이 플랜 파일을 대상으로 잡으면 거절(항목 0, '26-09-27 재진단 — F1) —
        # 처음엔 "genre 가 있으면"으로 갈랐으나, 1p '돌려줄 것' 예시엔 genre 키가 아예
        # 없다(filename 도 생략 가능하다고 안내한다). 그래서 모델이 예시 그대로 낸
        # genre-없는 1p doc(title·summary·sections 만 있고 plan_id 만 유효)이 가드를
        # 그냥 지나가 버렸다. genre 유무 대신 **doc 가 플랜(2층 빌드플랜) 모양이 아닌가**로
        # 가른다 — plan_id 만 유효하고(filename 이 비었거나 등록부에 없고) doc 가
        # 플랜에만 있는 키(승인·판정·개체구성·요구분석 …)를 안 갖고 있으면(=문서든 아니든
        # 플랜은 아니다) 거절한다. 정상 문서 저장(편집기·{key,doc}·payload.doc)은 genre
        # 유무와 무관하게 그대로 통과한다 — 플랜 저장(플랜저장/플랜승인)은 이 경로를 안 탄다.
        if not _플랜모양인가(_doc) and (_doc.get("plan_id") or "").strip() \
                and not (_doc파일명 and 문서(_doc파일명).get("ok")):
            return {"ok": False, "로그":
                    (f"'{_doc파일명}' 를 문서 등록부에서 찾지 못했습니다 — " if _doc파일명
                     else "doc.filename(또는 key)이 없습니다 — ")
                    + "저장(save)은 있는 문서만 고치며, plan_id 로 구성 설계(빌드플랜) "
                    "파일을 대신 덮어쓰지 않습니다. 문서(key)로 다시 확인한 뒤 그 filename "
                    "으로 저장하십시오."}
    키 = _저장키(payload)
    자리 = 이제 = 판만들기 = None
    if 판없이 is None and 키:
        이제 = time.time()
        # 세션까지 넣어 센다(WP-S2 ②) — 문서 이름은 세션마다 겹칠 수 있다("보고서" 를
        # 둘이 동시에 만든다). 이름만으로 세면 남이 방금 자동저장한 탓에 내 첫 판이
        # 안 생긴다(부록 A-2 가 지목한 `_마지막판` 전역 문제와 같은 뿌리).
        자리 = (자료뿌리.세션열쇠(), 키)
        판만들기 = 이제 - _마지막판.get(자리, 0) >= 판_간격초
        판없이 = not 판만들기
    cmd = [sys.executable, "workspace/apply_edit_any.py", "--payload", "-"]
    if 판없이:
        cmd.append("--판없이")
    r = subprocess.run(cmd, cwd=ROOT, input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, timeout=180,
                       env=자료뿌리.자식환경())     # 세션을 물려준다(돌리기 주석 참고)
    본 = {"ok": r.returncode == 0, "로그": (r.stdout or "") + (r.stderr or "")}
    if _A정규화알림:
        본["로그"] += "\n▸ " + _A정규화알림
    if _B정규화알림:
        본["로그"] += "\n▸ " + _B정규화알림
    # 판 슬롯(판_간격초에 하나)은 **판이 실제로 생겼을 때만** 소비한다. 예전엔 돌리기 전에 미리
    # 소비해서, 변화 없는 저장(정렬만 바꿈·되풀이 자동저장 등)이 슬롯을 먹으면 그 뒤 진짜 편집이
    # 5분간 '판없이'로 저장돼 이력(판)이 비었다(2026-09-06). 보관 문구는 apply_edit_any 가 찍는다.
    if 판만들기 and 본["ok"] and "으로 보관했습니다" in (r.stdout or ""):
        _마지막판[자리] = 이제
    # 반영에 성공했으면 정본의 새 수정시각을 함께 돌려준다. 화면이 이걸 안 받으면
    # 다음 저장 때 낙관적 잠금이 "그 사이 바뀌었다"며 거부한다 — 우리가 바꿔 놓고.
    # (render_editor_any.py 의 `보내기()` 가 이 필드를 읽는다)
    if 본["ok"] and 키:
        본["수정시각"] = (문서(키).get("값") or {}).get("_수정시각")
    elif not 본["ok"] and 키 and "바뀌었습니다" in (본["로그"] or ""):
        # (2026-09-26 2차 진단 — 항목 4, api8 재진단 '26-09-27: cli s1·s2 friction) 경합
        # 보호(낙관적 잠금)가 거절한 두 갈래를 나눈다 — **값을 알려 주면 안 된다**는 원칙은
        # 그대로 유지한다(에이전트가 그 값만 그대로 붙여 낡은 사본을 다시 보내고, 그 사이
        # 사람이 편집기에서 고친 내용이 조용히 지워지는 사고가 재현됐다).
        _보냄 = isinstance(_doc, dict) and _doc.get("_수정시각")
        if not _보냄:
            # ① _수정시각을 아예 안 보내 거절된 경우 — cli s1·s2 e2e 재현('26-09-27):
            # 이 안내가 없던 때는 "다시 받아 고쳐 보내라"만 보고 **새 시각으로 손수
            # 재스탬프**해 2차 시도도 (아래 ②로) 또 거절당했다. 그 값을 **손대지 말고
            # 그대로** 실어 보내야 함을 못박는다.
            본["로그"] += (f"\n\n▸ payload.doc._수정시각 이 없어 경합 보호로 거절됐습니다 — "
                        f"문서(key=\"{키}\")로 지금 저장된 문서를 다시 받아, 그 결과의 "
                        "doc._수정시각 값을 **직접 새로 만들거나 고치지 말고 받은 그대로** "
                        "이번 doc 에 실어 고친 내용과 함께 다시 보내십시오(그 사이 사람이 "
                        "편집기에서 고쳤을 수 있습니다 — 값을 모른 채 덮어쓰지 않도록, 이 "
                        "메시지는 지금 저장된 값을 알려 주지 않습니다).")
        else:
            # ② _수정시각을 보냈는데도 거절된 경우 — 진짜 경합(그 사이 다른 편집이 있었다)
            # 이거나, ①의 안내를 오해해 **새 시각으로 재스탬프**해 보낸 경우다(cli s2 재현:
            # "문서(get) 뒤 직접 새 타임스탬프로 재스탬프" → 이 두 번째 거절). 어느 쪽이든
            # 다시 문서(get)부터 시작해야 한다는 점은 같다.
            본["로그"] += ("\n\n▸ doc._수정시각 을 실었는데도 경합 보호로 거절됐습니다 — "
                        f"보낸 값이 지금 저장된 값과 다릅니다. 문서(key=\"{키}\")로 **지금** "
                        "저장된 문서를 다시 받아, 그 doc._수정시각 값을 손대지 말고 그대로 "
                        "옮겨 고친 내용과 함께 다시 보내십시오(직접 새 시각을 만들어 넣지 "
                        "마십시오 — 그 값은 이 정본 파일만 알며, 여기서도 알려 주지 않습니다).")
    return 본


@등록("조립", ["docs", "only"], 읽기=False, 승인필요=True,
    설명="3층 JSON → HTML. only 를 주면 그 문서 한 건만 다시 만든다", en="build")
def 조립(docs="build/samples-docs.json", only=""):
    # 조립기 이름은 **등록부에서 가져온다.** 여기에 손으로 적으면 새 장르가 조용히
    # 빠진다 — genres.py 머리말이 여섯 번 겪었다고 적어 둔 그 함정이다(2026-08-05 발견).
    이름 = os.path.basename(docs).replace("-docs.json", "")
    genres = 자료뿌리.모듈("genres")
    표 = {g["이름"]: g["조립기"] for g in genres.등록부()}
    조립기 = 표.get(이름)
    if 조립기 is None:
        return {"ok": False, "로그": f"모르는 장르 등록부입니다: {이름} — "
                                  f"build/genres.py 의 표에 한 줄 더해야 합니다"}
    # 승인 없는 플랜에 매인 문서는 조립하지 않는다(WP-S3 '승인 없음'). 어긋남 관문은
    # 부르기() 가 이미 지났고, 여기는 **이 작업만 아는** 검사다 — 어느 문서를 만들
    # 참인지는 인자(docs·only)를 아는 이 함수만 안다(이름별 분기가 아니라 작업 자신의
    # 로직이다). 등록부를 못 읽는 경우는 조립기가 곧바로 큰 소리로 죽으므로 여기서
    # 따로 안 막는다 — 같은 실패를 두 곳에서 다르게 말하면 부르는 쪽이 헷갈린다.
    try:
        대상 = json.load(open(등록부길(이름), encoding="utf-8"))
        if only:
            대상 = [d for d in 대상 if d.get("filename") == str(only)]
        막힘 = _플랜승인막힘(대상)
        if 막힘:
            return 막힘
    except (OSError, ValueError):
        pass
    # 조립기는 코드(ROOT), 등록부는 자료(자료뿌리) — 둘을 갈라 넘긴다(WP-S2 ①)
    등록부경로 = 등록부길(이름)
    # WP-S9: subprocess 자기호출을 함수 직접호출로 단계적 전환한다. 조립기가 `조립하기`
    # 를 내놓으면 그걸 **이 프로세스에서 바로** 부른다 — 프로세스를 새로 안 띄운다.
    # 아직 안 바꾼 조립기는 예전대로 subprocess 로(직접 경로가 증명될 때까지 병존).
    # 세션 오염 주의: `조립하기` 는 산출물 뿌리를 **호출마다** 다시 푼다(그 함수 머리말).
    # 직접 경로는 이 스레드의 세션 열쇠를 그대로 보므로(자료뿌리.세션열쇠 는 스레드
    # 지역값 우선), subprocess 처럼 자식환경()·env 로 열쇠를 물려줄 필요가 없다.
    모듈이름 = 조립기[:-3] if 조립기.endswith(".py") else 조립기
    조립모듈 = 자료뿌리.모듈(모듈이름)
    직접 = getattr(조립모듈, "조립하기", None)
    if 직접 is not None:
        try:
            본 = 직접(등록부경로, only=(str(only) or None))
        except SystemExit as e:
            # genres.한건만 이 없는 --only 키에 SystemExit 을 던진다 — subprocess 였다면
            # returncode≠0 이 됐을 실패를 여기서 ok=False 로 옮긴다(규칙 3, 조용한 실패 금지).
            return {"ok": False, "로그": str(e)}
        except Exception:
            import traceback
            # 직접 경로는 예외가 이 프로세스로 올라온다 — subprocess 의 stderr 자리를
            # 대신해 traceback 을 로그로 돌려준다(규칙 3: 삼키지 않고 큰 소리로).
            return {"ok": False, "로그": traceback.format_exc()}
        if 본.get("ok"):
            _산출지문적기(*([str(only)] if only else [d.get("filename") for d in (locals().get("대상") or [])
                                                      if isinstance(d, dict)]))
        return _조립대기붙이기({"ok": 본["ok"], "로그": 본["로그"]},
                           [str(only)] if only else [d.get("filename") for d in (locals().get("대상") or [])
                                                     if isinstance(d, dict)])
    cmd = [sys.executable, f"build/{조립기}", 등록부경로]
    if only:
        # 한 건만 — 나머지 문서의 산출 파일은 손도 안 댄다(WP-S2 ②).
        cmd += ["--only", str(only)]
    결과 = 돌리기(cmd)
    if 결과.get("ok"):
        _산출지문적기(*([str(only)] if only else [d.get("filename") for d in (locals().get("대상") or [])
                                                  if isinstance(d, dict)]))
    return _조립대기붙이기(결과, [str(only)] if only else [d.get("filename") for d in (locals().get("대상") or [])
                                                        if isinstance(d, dict)])


def _조립대기붙이기(결과, 키들):
    """조립 결과에 그림 생성 대기(P2)를 싣는다 — 절대 경로 포함(웹앱·공유 연결은 경로 없이, 웹앱은 목록 없음)."""
    if not (isinstance(결과, dict) and 결과.get("ok")):
        return 결과
    try:
        대기 = _그림대기들([k for k in 키들 if k])
    except Exception as e:
        print(f"[그림] 대기 목록 오류(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
        대기 = []
    if 대기:
        결과 = dict(결과)
        결과["그림대기"] = 대기
        결과["로그"] = (결과.get("로그") or "") + "\n" + _그림대기글(대기)
    return 결과


@등록("문체검사", ["docs", "key"], 읽기=False,
    설명="문체 게이트(하드·소프트). docs 없이 부르면 세션의 등록부 전부를, key 를 주면 "
        "그 문서가 든 등록부에서 그 문서 하나만 잰다", en="stylelint")
def 문체검사(docs="", key=""):
    """예전엔 docs 기본값이 'samples-docs.json' 이라, 인자 없이(예: 빈 {}) 부르면 다른 장르
    (시행문·규정·보도자료 …)는 아예 안 재고도 ok:true 로 헛통과했다('26-09-26 벤치마크 진단
    — 심사 지적 102건 가운데 여러 건이 이 헛통과 뒤에서 났다). docs 를 명시하면 예전 그대로
    그 등록부만 재고, key 를 주면 그 문서가 든 등록부를 찾아 **그 문서 하나만** 재
    (새문서 한 번에 검사까지 붙일 때 세션 전체를 다시 재지 않도록 — 항목 3).
    """
    if key:
        for p in 등록부들():
            try:
                문서들 = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            대상 = next((d for d in 문서들 if d.get("filename") == key), None)
            if 대상 is None:
                continue
            임시 = p + f".단건-{os.getpid()}-{uuid.uuid4().hex[:6]}.json"
            잰 = _잰판(key, 대상)       # 실제로 재는 내용(대상)의 지문 — 결과는 이 판에 묶는다(fixup5 ①)
            try:
                자료뿌리.원자json(임시, [대상], indent=2)
                r = 돌리기([sys.executable, "build/stylelint.py", 임시])
            finally:
                try:
                    os.remove(임시)
                except OSError:
                    pass
            _규칙세기("문체검사", r.get("로그") or "")
            그대로, 알림 = _잰판그대로(key, 잰, "문체검사")
            적음 = 그대로 and _검사적기(key, "문체", r.get("ok"), 잰=잰)       # 내보내기 관문이 보는 이 판의 기록(H2)
            if 그대로 and not 적음:
                알림 = "\n⚠ 문체검사 결과를 검사 기록에 적지 못했습니다 — 이 결과로는 내보낼 수 없습니다. 문체검사를 다시 부르세요."
            if not 적음:
                # 기록이 없는 검사는 통과가 아니다(fixup6, verify5 N8)
                r = dict(r)
                r["ok"] = False
                r["기록"] = False
                r["로그"] = (r.get("로그") or "") + 알림
            return r
        return {"ok": False, "로그": f"'{key}' 를 어느 등록부에서도 찾지 못했습니다"}
    if docs:
        r = 돌리기([sys.executable, "build/stylelint.py", 등록부길(docs)])
        _규칙세기("문체검사", r.get("로그") or "")
        return r
    # docs 도 key 도 없으면 — 세션에 문서가 든 등록부 전부를 등록부별로 잰다.
    결과 = {}
    통과 = True
    for p in 등록부들():
        try:
            문서들 = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not 문서들:
            continue     # 빈 등록부는 잴 것이 없다
        이름 = os.path.basename(p).replace("-docs.json", "")
        r = 돌리기([sys.executable, "build/stylelint.py", p])
        _규칙세기("문체검사", r.get("로그") or "")
        결과[이름] = r
        통과 = 통과 and bool(r.get("ok"))
    if not 결과:
        return {"ok": True, "값": {}, "로그": "이 세션에 검사할 문서가 없습니다"}
    return {"ok": 통과, "값": 결과,
            "로그": "\n".join(f"[{이름}]\n{r.get('로그') or ''}" for 이름, r in 결과.items())}


def _규칙세기(출처, 로그):
    """문체 게이트가 짚은 **규칙 id 만** 세션 기록에 적는다 (출시계획 1-6 A안).

    `[soft] W-의연쇄 「…」 — …` 처럼 규칙 id 가 로그의 정해진 자리에 있다. 문서 글자는
    그 뒤에 오는데 **그건 가져오지 않는다** — 여기서 본문을 한 자라도 남기면 "세션이
    끝나면 내용은 지운다"가 거짓이 된다.

    세션이 없으면 `자료뿌리.규칙적기()` 가 아무것도 안 한다(개발·CLI 경로 무변화).
    """
    import re as _re
    셈 = {}
    for 세기, 규칙 in _re.findall(r"\[(hard|soft)\] (\S+)", 로그 or ""):
        열 = f"{세기}:{규칙}"
        셈[열] = 셈.get(열, 0) + 1
    자료뿌리.규칙적기(출처, 셈)


_조판키규칙 = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


@등록("조판게이트", ["key"], 읽기=False,
    설명="인쇄해 1쪽·어절분리·넘침을 잰다(헤드리스 크롬, 수 초). key 를 주면 그 문서 하나만",
    en="gate")
def 조판게이트(key=""):
    # key 없이는 예전 그대로 세션 산출물 폴더 전부(render_verify.sh 가 알아서 돈다).
    # key 를 주면 ONLY 환경변수로 그 문서 하나만 인쇄·DOM 덤프하게 좁힌다 — 문서 하나
    # 검사에 세션 안의 다른 문서 수만큼 크롬을 돌리던 것을 없앤다('26-09-26 벤치마크
    # 진단 — 항목 5, 새문서 한 번에 검사를 붙일 때 특히 크다).
    if key:
        key = str(key)
        # 경로 탈출 차단(항목 5, '26-09-26 2차 진단 — 실제 재현: '../../../rvfl.../2026'
        # 로 세션 밖 html 을 인쇄해 그 옆에 PDF 를 쓰거나 지웠다). key 는 새문서와 같은
        # 정규식으로 검증하고, 등록부에 실재하는지도 확인한다 — 없는 키는 PASS 가 아니라
        # 실패로 끝낸다(항목 9, 헛통과 방지). render_verify.sh 에도 같은 검증을 겹으로 둔다.
        if not _조판키규칙.fullmatch(key):
            return {"ok": False, "로그": f"key 값이 올바르지 않습니다: '{key}' — "
                    "영소문자·숫자·하이픈만, 2~61자(경로 문자 금지)"}
        if not 문서(key).get("ok"):
            return {"ok": False, "로그": f"'{key}' 를 등록부에서 찾지 못했습니다"}
    환경 = {"ONLY": key} if key else {}
    검방 = 실행방 = None
    if _플러그인표면():
        # 플러그인은 검사용 PDF 를 세션 방 workspace/_검사/ 에 인쇄한다 — 내보내기 자리(build/exports)에도, 작업 자리
        # (build/samples)에도 검사 못 넘은 판의 PDF 를 두지 않는다(fixup4 주관 ②, verify3 L2). 웹앱·verify_all 은 그대로.
        검방 = 자료뿌리.검사뿌리()
        os.makedirs(검방, exist_ok=True)
        환경["GATE_PDF_DIR"] = 검방
        if key:
            # 문서 하나를 잴 때는 **실행마다 따로 방**에 인쇄한다(fixup6, verify5 N1 — 같은 문서에 게이트 둘이 겹치면 한
            # 자리(<key>.pdf)를 나눠 써, 늦게 떨어진 남의 인쇄를 제 것으로 읽고 PASS·PDF 지문을 적었다). 기록한 판의
            # 인쇄만 검사 자리(<key>.pdf)로 옮긴다.
            import tempfile as _tf
            실행방 = _tf.mkdtemp(prefix=f".{key}-", dir=검방)
            환경["GATE_PDF_DIR"] = 실행방
    잰 = _잰판(key) if key else None       # 재기 시작 때의 지문 — 결과는 이 판에 묶는다(fixup5 ①)
    try:
        r = 돌리기(["bash", "build/render_verify.sh"], timeout=900, 환경추가=(환경 or None))
        if key:
            # 내보내기 관문이 보는 이 판의 기록(H2). 재는 도중 판이 바뀌었으면 적지 않는다. 인쇄한 검사 PDF 의 지문을
            # 곁들여, 내보내기 pdf 가 같은 판·같은 화면·**같은 파일**일 때만 이 PDF 를 다시 쓰게 한다.
            그대로, 알림 = _잰판그대로(key, 잰, "조판게이트")
            적음 = False
            if 그대로:
                더 = None
                if 실행방:
                    인쇄 = os.path.join(실행방, f"{key}.pdf")
                    지문 = _파일지문(인쇄)
                    if 지문:
                        os.replace(인쇄, os.path.join(검방, f"{key}.pdf"))
                    더 = {"pdf": 지문}
                elif 검방:
                    더 = {"pdf": _파일지문(os.path.join(검방, f"{key}.pdf"))}
                적음 = _검사적기(key, "조판", r.get("ok"), 더=더, 잰=잰)
                if not 적음:
                    알림 = ("\n⚠ 조판게이트 결과를 검사 기록에 적지 못했습니다 — 이 결과로는 내보낼 수 없습니다. "
                          "조판게이트를 다시 부르세요.")
            if not 적음:
                # 기록이 없는 게이트는 통과가 아니다(fixup6, verify5 N8 — 예전엔 기록을 건너뛰고도 ok true 일 수 있었다)
                r = dict(r)
                r["ok"] = False
                r["기록"] = False
                r["로그"] = (r.get("로그") or "") + 알림
    finally:
        if 실행방:
            import shutil as _sh
            _sh.rmtree(실행방, ignore_errors=True)
    return r


@등록("되돌리기", ["key", "n", "이유"], 읽기=False, 설명="문서를 지정한 판으로 되돌린다", en="revert")
def 되돌리기(key, n, 이유=""):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    # 판 번호는 **`--버전 N`** 으로 넘겨야 한다. 위치 인자로 주면 CLI 가 못 읽고
    # 늘 0 으로 읽어 "버전 0이 없습니다" 만 돌려준다 — 스킬·MCP·웹앱에서 되돌리기가
    # 아예 안 되고 있었다(2026-08-06 B-3 시험에서 걸림).
    cmd = [sys.executable, "history/version.py", "--되돌리기", str(key), "--버전", str(n)]
    if 이유:
        cmd += ["--이유", 이유]
    r = 돌리기(cmd)
    if r["ok"]:
        # 되돌린 등록부로 **산출물부터 다시 조립한다**('26-09-28, 2단계 UI 검토 F2) —
        # 편집기(render_editor_any.gen)는 등록부가 아니라 산출물 HTML 에서 굽는다. 예전엔
        # 등록부만 되돌리고 편집기를 구워, 옛(되돌리기 전) 화면이 떴고 그 화면의 첫 자동
        # 저장이 되돌린 것을 조용히 덮었다. 저장 뒤 apply_edit_any 와 같은 길(--only --저장).
        재 = _한건재조립(key)
        if 재 is not None and not 재["ok"]:
            r = {"ok": False, "로그": r["로그"] + "\n  ✗ 되돌렸지만 문서를 다시 만들지 못했습니다: "
                 + ((재["로그"] or "").strip().splitlines() or ["까닭 모름"])[-1]}
            return r
        # 되돌린 문서 내용으로 편집 화면을 새로 굽는다 — 안 하면 편집기가 옛 문서를
        # 계속 임베드해 보여준다(저장 후 apply_edit_any 가 하는 재생성과 같은 결).
        돌리기([sys.executable, "workspace/render_editor_any.py", str(key)])
    return r


def _한건재조립(key):
    """key 가 든 등록부를 찾아 그 문서 한 건만 다시 조립한다(못 찾으면 None)."""
    genres = 자료뿌리.모듈("genres")
    for g in genres.등록부():
        try:
            문서들 = json.load(open(g["길"], encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if any(isinstance(d, dict) and d.get("filename") == str(key) for d in 문서들):
            결과 = 돌리기([sys.executable, f"build/{g['조립기']}", g["길"],
                         "--only", str(key), "--저장"])
            if 결과.get("ok"):
                _산출지문적기(str(key))
            return 결과
    return None


@등록("지점지우기", ["key", "n"], 읽기=False,
    설명="되돌림 지점(직접 보관 버전) 하나를 지운다 — 최대 3개 제한에서 자리를 비울 때", en="delpoint")
def 지점지우기(key, n):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    # 되돌리기와 같은 결 — 버전 번호는 --버전 으로 넘긴다(위치 인자면 CLI 가 0 으로 읽는다).
    return 돌리기([sys.executable, "history/version.py", "--지우기", str(key), "--버전", str(n)])


@등록("작업화면갱신", 읽기=False, 설명="편집 화면·구성 설계 화면을 다시 만든다", en="refresh")
def 작업화면갱신():
    r1 = 돌리기([sys.executable, "workspace/render_editor_any.py", "--all"])
    r2 = 돌리기([sys.executable, "workspace/render_editor_any.py", "--skeletons"])
    return {"ok": r1["ok"] and r2["ok"], "로그": r1["로그"] + r2["로그"]}


def _승인화면_경로(plan):
    """plan_id(또는 플랜 파일)를 **플랜 뿌리 안의 파일로만** 푼다. 밖이면 None.

    옛 판은 값에 경로 구분자가 있거나 .json 으로 끝나면 그대로 열었다 — 웹에서 절대 경로를
    주면 세션 밖 JSON 을 렌더해 돌려주었다('26-10-01 보안). 플랜 뿌리는 웹이면 그 세션 방,
    개발·플러그인이면 buildplan/ 이라 동봉 예시도 그 안에 든다."""
    값 = str(plan or "").strip()
    if not 값 or "\0" in 값:
        return None
    if os.sep not in 값 and "/" not in 값:
        # plan_id('mine01') 또는 파일 이름만('plan-mine01.json') — 둘 다 플랜 뿌리 안에서 찾는다
        try:
            후보 = os.path.join(자료뿌리.플랜뿌리(), 값) if 값.endswith(".json") else 자료뿌리.플랜(값)
        except 자료뿌리.플랜아이디틀림:
            return None
    else:
        후보 = 값 if os.path.isabs(값) else os.path.join(ROOT, 값)
    뿌리 = os.path.realpath(자료뿌리.플랜뿌리())
    진짜 = os.path.realpath(후보)
    if not 진짜.startswith(뿌리 + os.sep) or not 진짜.endswith(".json") or not os.path.isfile(진짜):
        return None
    return 진짜


@등록("승인화면", ["plan_id", "plan"], 읽기=False,
    설명="빌드플랜 → 승인 화면 HTML 을 돌려준다. plan_id 는 세션 플랜의 plan_id 문자열 또는 "
        "파일 경로다(플랜승인과 같은 인자 이름) — {\"plan_id\": \"…\"} 처럼 dict 로 감싸 와도 받는다. "
        "plan 은 옛 이름(옛 웹앱·CLI 호환)이라 plan_id 를 쓰세요",
    en="plan")
def 승인화면(plan_id=None, plan=None):
    """(mcp:R7 s2 재진단, '26-09-27) — 예전엔 이 인자 이름이 'plan'이었다. api.인자모양
    표(105행)는 '오브젝트를 받는' 다른 작업(플랜저장)의 'plan' 인자(2층 빌드플랜 JSON,
    dict)와 이름이 겹쳐, 인자 이름 하나로 타입을 정하는 이 표 구조상 이 작업의 'plan'도
    dict 로 강제됐다 — 그런데 이 작업이 실제로 받는 값은 문자열(plan_id 또는 파일 경로)
    이라 설명과 스키마가 어긋났다. MCP 로 plan_id 문자열을 그대로 주면 스키마가 즉시
    거절했고("Input should be a valid dictionary"), {"plan_id": "…"} 로 감싸면 스키마는
    통과하지만 그 dict 를 그대로 파일 경로로 오인해 render_plan.py 가 못 여는 파일을
    열려다 트레이스백을 던졌다(그것도 returncode 는 0 이라 아래에서 따로 잡는다).

    인자 이름을 이미 문자열로 굳어 있는 'plan_id'(플랜승인과 같다)로 바꿔 이 충돌을
    없앤다 — api.인자모양에 'plan_id' 항목이 없으니 기본값(str)으로 스키마가 나간다.
    그래도 dict 로 감싸 오는 옛 호출(또는 CLI 로 스키마 검증 없이 곧장 오는 호출)은
    아래에서 풀어 받는다 — 한쪽으로 인자 모양을 맞추되, dict·문자열 둘 다 안전하게."""
    # fixup3 Z1('26-10-01 주관 판정) — 옛 이름 'plan' 도 받는다. 이름을 바꾼 뒤 app.html(1860행)은 그대로 {plan: plan_id} 로 불렀고
    # serve.py 는 받는것 밖 인자를 걸러, 웹앱이 2단계(작성 계획)에서 멈췄다(wire_fixup2 §2-3). 이미 떠 있는 옛 화면(라이브 웹앱의
    # 캐시된 app.html)·옛 CLI 도 살아야 하므로 받는 이름을 둘 다 두고, 둘 다 오면 plan_id 가 이긴다.
    대상 = plan_id or plan
    if isinstance(대상, dict):
        대상 = 대상.get("plan_id") or 대상.get("plan") or 대상.get("path") or 대상.get("경로")
    if not 대상:
        return {"ok": False, "로그": "plan_id(세션 플랜의 plan_id) 또는 파일 경로가 없습니다"}
    # 보안('26-10-01): 플랜 뿌리 안의 파일로만 푼다 — 옛 판은 경로 구분자·.json 이 붙으면 그대로 열어
    # 웹 POST /api/plan 에 절대 경로를 주면 세션 밖 JSON 을 렌더해 돌려주었다(test/r34_plansec34.py).
    경로 = _승인화면_경로(대상)
    # fixup4 G8('26-10-01 주관 판정) — 없는 plan_id 면 render_plan.py 트레이스백 대신 사람 말로(wire_fixup3_verify §3-6)
    if not 경로:
        return {"ok": False, "로그": f"그 작성 계획을 찾지 못했습니다('{str(대상)[:60]}') — 작성 계획을 저장할 때(saveplan) 받은 "
                                  "plan_id 를 그대로 주세요"}
    try:
        r = subprocess.run([sys.executable, "buildplan/render_plan.py", str(경로), "--stdout", "--web"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30,
                           env=자료뿌리.자식환경())
    except Exception as e:
        return {"ok": False, "로그": f"승인 화면을 만들지 못했습니다 ({type(e).__name__})"}
    # (mcp:R7 s2 재진단) render_plan.py 가 내부 오류를 "[✗]"+트레이스백으로 표준출력에
    # 찍고도 0 으로 끝날 수 있다 — returncode 만 보면 그 트레이스백을 성공 html 로 그대로
    # 돌려준다(MCP 응답이 isError:false 인데 내용은 실패인 상태). 표준출력 내용도 본다.
    if r.returncode != 0 or (r.stdout or "").lstrip().startswith("[✗]"):
        try:       # 꼴이 틀린 플랜이면 트레이스백 대신 틀린 칸을 말한다(fixup6, verify5 N6)
            틀림 = _플랜꼴문제(json.load(open(경로, encoding="utf-8")))
        except Exception:
            틀림 = []
        if 틀림:
            return {"ok": False, "로그": "작성 계획 형식이 맞지 않아 승인 화면을 만들지 못했습니다. " + " ".join(틀림[:5])
                    + " (고쳐 saveplan 으로 다시 저장하세요)"}
        # 트레이스백은 싣지 않는다(G8) — 마지막 오류 한 줄만
        _끝 = [l.strip() for l in (r.stderr or r.stdout or "").splitlines() if l.strip() and not l.strip().startswith("[✗]")]
        return {"ok": False, "로그": "승인 화면을 만들지 못했습니다" + (f" — {_끝[-1][:200]}" if _끝 else "")}
    return {"ok": True, "값": {"html": r.stdout}}


@등록("관측", ["key"], 읽기=False, 설명="산출물에서 실제 분량·구성을 재어 기록(귀납 재료)", en="observe")
def 관측(key=""):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각(앞 '-' 깃발 금지)
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    cmd = [sys.executable, "build/observe.py"]
    cmd.append(key if key else "--all")
    return 돌리기(cmd)


@등록("되감기", ["key", "무엇"], 읽기=False,
    설명="생성 결과를 구성 설계로 되돌려 본다(scan=관측만, load=플랜에 싣기)", en="rewind")
def 되감기(key="", 무엇="scan"):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각(앞 '-' 깃발 금지)
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    깃발 = "--load" if 무엇 == "load" else "--scan"
    return 돌리기([sys.executable, "buildplan/rewind.py", 깃발, key or "--all"])


@등록("원장", ["무엇"], 설명="피드백 원장 현황(대기 큐 포함)", en="ledger", 관리자=True)
def 원장(무엇=""):
    # 관리자=True (온톨로지 기밀) — 원장 엔트리에는 규칙 해석·검증 수단이 실려 있어
    # 일반 문(MCP·웹)에 내면 규칙 정보가 통째로 새어 나간다. 열쇠 문 하나만 지난다.
    cmd = [sys.executable, "feedback/feedback.py"]
    if 무엇 == "대기":
        cmd.append("--pending")
    return 돌리기(cmd)


@등록("역추적", ["key", "무엇"], 읽기=False,
    설명="사람이 HTML을 직접 고친 흔적을 찾고(scan) 정본에 수용한다(adopt)", en="backtrace")
def 역추적(key="", 무엇="scan"):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각(앞 '-' 깃발 금지)
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    if key:
        # 역추적(HTML 손편집 수용)은 1페이지 조립기·스키마 전용이다 — feedback/backtrace.py 는
        # samples 등록부(assemble.py)만 쓴다. 다른 장르 key 를 넘기면 옛 코드는 samples 에서
        # 못 찾아 '정본에 없는 문서'라 **틀린** 실패를 냈다(문서는 다른 등록부에 있는데). 어느
        # 등록부에 있는지 먼저 가려, 비-samples 면 정확히 안내하고 편집기 저장(장르 인식) 경로로
        # 돌린다(1p 스키마로 다른 장르를 파괴하는 잠재 위험도 여기서 차단).
        for _p in 등록부들():
            try:
                _docs = json.load(open(_p, encoding="utf-8"))
            except Exception:
                continue
            if any(isinstance(d, dict) and d.get("filename") == key for d in _docs):
                if os.path.basename(_p) != "samples-docs.json":
                    _장르 = os.path.basename(_p).replace("-docs.json", "")
                    return {"ok": False, "로그":
                            f"'{key}'는 {_장르} 문서입니다 — 역추적(HTML 직접 수정 수용)은 현재 "
                            "1페이지 보고서만 지원합니다. 다른 장르는 편집기 저장(save)으로 반영하세요. "
                            "AI 지시 목록은 이력(history, key=<문서키>)에서 처리='대기' 항목으로 확인하세요."}
                break   # samples 에 있으니 정상 진행
    if 무엇 == "adopt":
        if not key:
            return {"ok": False, "로그": "adopt 는 문서 이름이 있어야 합니다"}
        return 돌리기([sys.executable, "feedback/backtrace.py", "--adopt", key])
    cmd = [sys.executable, "feedback/backtrace.py", "--scan"]
    if key:
        cmd.append(key)
    return 돌리기(cmd)


@등록("편집기록", ["key"], 읽기=False, 설명="사람이 고친 내역을 관측으로 적재(edit-log)", en="editlog")
def 편집기록(key=""):
    if key and not 자료뿌리.키맞나(str(key)):     # 보안('26-10-01): 키는 파일 이름 한 조각(앞 '-' 깃발 금지)
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    cmd = [sys.executable, "feedback/backtrace.py", "--log"]
    if key:
        cmd.append(key)
    return 돌리기(cmd)


def _문서손탔나(키):
    """이 문서가 사람 손(편집기 저장·되돌리기 등)을 탄 이력이 있는지 **이력 모듈로** 본다
    (항목 2, 2026-09-26 벤치마크 진단). '이력' 작업이 쓰는 것과 같은 두 자리 —
    판 목록(V.목록)과 사건 기록(V.읽기) — 을 보되, **누가="사람"인 항목만** 센다.
    apply_edit_any(저장)는 자동저장이라도 항상 누가="사람"으로 남긴다(사람이 연
    화면에서 났으니). 반면 이 함수 바로 아래(새문서)가 '덮어쓰기 전' 스냅샷을 남길
    때는 누가="자동"이라 여기 안 걸린다 — 그래야 같은 filename 재시도가 두 번째부터도
    계속 덮어써진다(첫 덮어쓰기가 만든 판 기록 자체를 '사람 손 탄 증거'로 오판하지
    않는다). 이력 모듈을 못 불러오면 **탔다고 본다**(안전한 쪽 — 불확실하면 새 키를
    만든다, 정본을 덮어쓰지 않는다)."""
    try:
        V = 자료뿌리.모듈("version", "history")
        return (any((v or {}).get("누가") == "사람" for v in (V.목록(키) or []))
                or any((j or {}).get("누가") == "사람" for j in (V.읽기(키) or [])))
    except Exception:
        return True


def _전역키목록():
    """모든 등록부(전 장르)와 산출물 폴더(build/samples, 장르끼리 공유)에 있는 filename
    전부(항목 1, '26-09-26 2차 진단) — 자동 생성 키의 중복 확인은 **이 장르 등록부만**
    보면 안 된다. 산출물 폴더는 장르가 달라도 한 곳을 같이 쓰므로, 1p '2026'과 보도자료
    '2026'처럼 등록부가 갈려도 html 이 서로를 덮을 수 있었다."""
    이름들 = set()
    for p in 등록부들():
        try:
            for d in json.load(open(p, encoding="utf-8")):
                fn = d.get("filename")
                if fn:
                    이름들.add(fn)
        except (OSError, ValueError):
            continue
    try:
        import glob as _glob
        for hp in _glob.glob(os.path.join(자료뿌리.산출물뿌리(), "*.html")):
            이름들.add(os.path.splitext(os.path.basename(hp))[0])
    except OSError:
        pass
    return 이름들


def _고유키만들기(뿌리, 존재집합):
    """뿌리 뒤에 -2, -3 … 을 붙여 존재집합에 없는 첫 키를 만든다.

    접미사 길이만큼 뿌리를 잘라 결과가 늘 조판키규칙(2~61자)을 넘지 않게 한다
    (new_defects, '26-09-26 3차 진단) — 안 자르면 61자 뿌리(_유효한슬러그가 만드는
    최대 길이) + '-2' 가 63자가 되어, 새문서 자신의 기본 검사(조판게이트)가 그 키를
    '올바르지 않은 key'로 FAIL 시켰다. 경로 문자(/·..)는 애초에 슬러그 정규식이 막는다."""
    n = 2
    while True:
        접미 = f"-{n}"
        여유 = 61 - len(접미)
        후보뿌리 = 뿌리 if len(뿌리) <= 여유 else 뿌리[:여유].rstrip("-")
        후보 = f"{후보뿌리}{접미}"
        if 후보 not in 존재집합:
            return 후보
        n += 1


def _미매인승인플랜(장르):
    """이 세션에서 **이 장르**로 승인됐지만 아직 어느 문서의 plan_id 로도 쓰이지 않은
    플랜 id — 최신순(항목 0·2, '26-09-26 2차 진단). plan_id 자동 채움을 걷어내는 대신,
    거절 메시지에 안내로 실어 왕복을 줄인다(자동으로 채우지는 않는다 — 채우면 세션의
    **다른 문서**가 이미 쓴 플랜을 재활용해 승인 게이트를 무력화한 것이 이번에 걷어낸
    결함이다)."""
    _플랜뿌리 = 자료뿌리.플랜뿌리()
    if not os.path.isdir(_플랜뿌리):
        return []
    쓰인 = set()
    for p in 등록부들():
        try:
            for d in json.load(open(p, encoding="utf-8")):
                pid = (d.get("plan_id") or "").strip()
                if pid:
                    쓰인.add(pid)
        except (OSError, ValueError):
            continue
    항목 = []
    for _f in os.listdir(_플랜뿌리):
        if not (_f.startswith("plan-") and _f.endswith(".json")):
            continue
        _fp = os.path.join(_플랜뿌리, _f)
        try:
            _p = json.load(open(_fp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _p.get("장르") != 장르:
            continue
        if ((_p.get("승인") or {}).get("status") or "").strip() != "승인":
            continue
        pid = (_p.get("plan_id") or "").strip()
        if not pid or pid in 쓰인:
            continue
        항목.append((os.path.getmtime(_fp), pid))
    항목.sort(reverse=True)
    return [pid for _, pid in 항목]


# ── 속성값 거부를 구조화된 응답에 싣기(mcp:s5 수정, e2e r6 재진단 '26-09-27) ──────────
# build/속성값.py._거부(내 파일이 아니다)는 잘못된 값을 조용히 버리지 않고
# `print(f"[속성 거부] …", file=sys.stderr)` 로 큰 소리를 낸다 — 그런데 조립기가 전부
# 직접호출(조립하기, WP-S9)로 바뀌면서 이 stderr 는 이 프로세스의 **진짜** stderr 로
# 바로 나가, 새문서() 의 구조화된 응답(값.문체검사/조판게이트/지어냈나)에는 전혀 안
# 실린다 — JSON 만 보는 클라이언트(MCP)는 본문이 기본값(level=1)으로 조용히 뭉개진
# 것을 놓친다. 이 파일(api.py)의 조립() 호출 지점에서만 그 stderr 를 같이 챙긴다.
#
# 전역 sys.stderr 를 그냥 바꿔치기(contextlib.redirect_stderr)하면 이 서버가 실제로
# 스레드 여럿으로 돈다(threading.Lock 여러 개가 이미 있다 — 세션마다 스레드)는 점에서
# 위험하다 — 동시에 다른 세션이 조립 중이면 그 프린트까지 내 버퍼에 섞이거나, 내
# 버퍼로 바뀐 sys.stderr 에 그쪽이 써 진짜 stderr 로 하나도 안 나갈 수 있다. 그래서
# **한 번만** 진짜 stderr 를 감싸는 얇은 테이프를 심어 두고(스레드별 버퍼는
# threading.local), 각 스레드는 자기 버퍼가 켜져 있을 때만 자기 몫을 더 받는다 —
# 진짜 stderr 로는 항상 그대로 흘려보내므로(다른 로그가 사라지지 않는다) 새 위험은
# '이 캡처 구간에 한해 그 스레드가 낸 것만 안전하게 더 받는다' 정도로 좁다.
class _stderr테이프:
    def __init__(self, 진짜):
        self._진짜 = 진짜
        self._local = threading.local()

    def write(self, s):
        self._진짜.write(s)
        버퍼 = getattr(self._local, "버퍼", None)
        if 버퍼 is not None:
            버퍼.write(s)
        return len(s)

    def flush(self):
        self._진짜.flush()

    def isatty(self):
        return False

    def 시작(self):
        self._local.버퍼 = io.StringIO()

    def 끝(self):
        버퍼 = getattr(self._local, "버퍼", None)
        self._local.버퍼 = None
        return 버퍼.getvalue() if 버퍼 is not None else ""


_stderr테이프설치락 = threading.Lock()


def _속성거부_감시시작():
    with _stderr테이프설치락:
        if not isinstance(sys.stderr, _stderr테이프):
            sys.stderr = _stderr테이프(sys.stderr)
    sys.stderr.시작()


def _속성거부_감시끝():
    """[감시시작, 감시끝) 사이 **이 스레드**가 stderr 에 쓴 "[속성 거부] …" 줄만 골라
    (자리, 원문줄) 목록으로 낸다 — 다른 스레드 몫은 안 섞인다(위 클래스 docstring)."""
    본문 = sys.stderr.끝() if isinstance(sys.stderr, _stderr테이프) else ""
    out = []
    for 줄 in 본문.splitlines():
        if not 줄.startswith("[속성 거부] "):
            continue
        속 = 줄[len("[속성 거부] "):]
        자리 = 속.split("=", 1)[0].strip()
        out.append({"자리": 자리, "줄": 줄})
    return out


def _제목비슷한가(a, b, 문턱=0.4):
    """두 제목의 두 글자 묶음(한글·숫자·영문만, 공백·부호 뺌) 자카드 겹침이 문턱 이상인가."""
    def _묶음(t):
        t = re.sub(r"[^가-힣0-9A-Za-z]", "", str(t or ""))
        return {t[i:i + 2] for i in range(len(t) - 1)}
    x, y = _묶음(a), _묶음(b)
    if not x or not y:
        return False
    return len(x & y) / len(x | y) >= 문턱


@등록("새문서", ["doc", "장르", "원문", "검사", "자료파일"], 읽기=False, 승인필요=True,
    설명="3층 JSON 을 등록부에 넣고 조립·편집기까지 만든다. 검사(기본값은 CLI·MCP 는 참, "
        "웹앱은 거짓)면 문체검사·조판게이트·지어냈나(원문이 있을 때)까지 그 문서 하나로 "
        "같이 돌려 붙인다. plan_id 는 생략할 수 없다(승인된 빌드플랜) — 웹앱만 면제. "
        "doc.filename 을 직접 주려면 영문 소문자·숫자·하이픈만, 4자 이상, 영문자 1개 "
        "이상 포함해야 한다(짧거나 숫자뿐이면 자동 교정하고 로그로 알린다) — 장르는 "
        "문서 유형의 등록부 이름이다(예: samples·gongmun·press, 표시 이름 아님). 자료파일(생략 가능)은 이 문서에 쓴 "
        "받은 자료 파일 이름 목록 — CLI 는 파일읽기로 읽은 파일 이름을 모두 싣는다(첨부 사진 알림을 이 목록으로 센다)", en="new")
def 새문서(doc, 장르="samples", 원문="", 검사=None, 자료파일=None):
    """새로 만드는 길은 '저장'과 다르다 — 저장은 **있는 문서**를 찾아 고치는 길이라
    새 문서를 넘기면 '찾지 못했습니다'로 끝난다. 여기서 등록부에 넣는다."""
    import re as _re
    if not isinstance(doc, dict):
        return {"ok": False, "로그": "doc 이 객체가 아닙니다"}
    if 검사 is None:
        # 검사 기본값(항목 7, '26-09-26 2차 진단) — 웹앱(문서지능_웹앱 환경)은 app.html 이
        # stylelint·gate 를 세션 전체로 따로 돌린다(검사하기()). 그 위에 이 새문서 안에서
        # 동기 검사(문체검사 + 헤들리스 크롬 조판게이트)까지 겹치면 /api/new 한 번마다 크롬이
        # 두 배로 뜨고, 900초짜리 긴 일이 HTTP 요청 안에서 동기로 돈다(serve.py 머리말의
        # 설계 규율과 어긋난다). CLI·MCP(플러그인)만 기본으로 켠다 — 거긴 새문서 뒤에 따로
        # 검사를 돌리라고 안내할 사람(웹 화면)이 없다.
        검사 = not os.environ.get("문서지능_웹앱")
    # 웹앱 경로의 이름 규칙은 HEAD(1차 이전) 그대로 둔다(3차 수정) — 2차가 넓힌 개명 조건
    # (교차 장르·산출물 겹침, 숫자뿐·4자 미만 배제)은 app.html 이 새문서 응답의 key 를
    # 안 읽고 자기 doc.filename 을 그대로 쓰는 것과 맞물려, 겹치지도 않은 문서를 조용히
    # 다른 문서로 보내 버렸다(new_defects, '26-09-26 3차 진단). app.html 을 같이 고치지
    # 않고도(다른 작업 묶음의 파일이라 손대지 않는다) 여기서 웹앱만 좁혀 막는다.
    _웹앱 = bool(os.environ.get("문서지능_웹앱"))
    호출자filename = str(doc.get("filename") or "").strip()
    키 = 호출자filename
    if not 키:
        # filename 생략(항목 7) — 시스템이 알 수 있는 값이라 모델이 안 써도 되게 한다.
        # 제목에서 영문 소문자·하이픈을 시도하고, 한글 제목이라 아무것도 안 남으면
        # (로마자 변환은 안 한다 — 새 의존을 더하지 않는다) 아래 기존 교정 경로가
        # 장르 기반 이름으로 대체한다('26-09-26 벤치마크 진단).
        _제목 = str(제목뽑기(doc) or "")
        키 = _re.sub(r"-+", "-", _re.sub(r"[^a-z0-9-]+", "-", _제목.lower())).strip("-")

    def _유효한슬러그(s):
        # 규칙(영소문자·숫자·하이픈)을 지켜도 **숫자뿐이거나 너무 짧으면** 버린다(항목 1,
        # '26-09-26 2차 진단) — 예: '2026년 상반기 …'와 '2026년 청사 …'가 둘 다 '2026'이
        # 되어 서로 다른 문서가 뭉개졌다. **웹앱은 이 배제를 넣지 않는다** — HEAD 규칙
        # 그대로(위 주석) — '2026'처럼 짧은 호출자 filename 도 그대로 받아 app.html 이
        # 기대하는 이름과 어긋나지 않게 한다.
        if _웹앱:
            return bool(_re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", s))
        return bool(_re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", s)
                    and _re.search(r"[a-z]", s) and len(s) >= 4)

    if not _유효한슬러그(키):
        # LLM(특히 소형 모델)이 파일명 규칙을 못 지키는 일이 잦다 — 앞뒤·연속 하이픈,
        # 장식성 대시('--------ai--------'), 대문자·공백·한글 섞임 등. 규칙을 못 넘겼다고
        # 생성을 통째로 실패시키지 말고 **슬러그로 자동 교정**한다(모든 모델에서 이 사고 제거).
        슬러그 = _re.sub(r"[^a-z0-9-]+", "-", 키.lower())
        슬러그 = _re.sub(r"-+", "-", 슬러그).strip("-")[:61]
        if not _유효한슬러그(슬러그):
            # (api:F6 수정, e2e r6 재진단 '26-09-27) — doc.get("genre") 는 **호출자가
            # 준 표시용 값**일 수 있다(한글·공백 섞임, 예: "발표 슬라이드"). 그 값으로
            # 대체 이름을 지으면 대체 이름 자체가 규칙(영문 소문자·하이픈)을 어겨 조판게이트가
            # 다시 거절한다. 등록부 이름(장르 인자, 늘 영문 소문자)만으로 짓고, 대체 뒤에도
            # 다시 검증한다(만에 하나를 대비한 방어 — 장르 인자는 이미 등록부에서 검증됐다).
            슬러그 = f"{('onepage' if 장르 == 'samples' else 장르)}-doc"
            if not _유효한슬러그(슬러그):
                슬러그 = "doc"
        키 = 슬러그
    doc["filename"] = 키
    # 시스템이 만든 키인가(항목 1) — 호출자가 준 **그대로**가 아니면(비웠거나, 위 교정·
    # 대체를 거쳤으면) 시스템이 지은 이름이다. 시스템이 지은 이름은 **절대 덮어쓰지 않고
    # 늘 유일하게 만든다** — 덮어쓰기는 호출자가 명시한 그 filename 이 그대로 겹쳤을 때만
    # (아래 등록부 쓰기 블록에서 가른다).
    자동생성 = (키 != 호출자filename)
    # 호출자가 filename 을 **명시했는데** 규칙(영문 소문자·하이픈, 4자 이상, 영문자 포함)에
    # 안 맞아 교정·대체됐나(F3, '26-09-27 재진단) — 비어서 자동으로 지은 것과는 다르다.
    # 교정은 알림 없이 조용했고(응답 key·로그 첫 줄에만 실제 키가 드러났다), 재시도
    # 판정(진짜재시도)도 늘 "자동생성이 아니다"만 봐서 교정된 이름은 절대 덮어쓰기로
    # 안 잡혀 같은 이름으로 다시 불러도 -2·-3 …으로 계속 쌓였다. 교정은 같은 입력이면
    # 같은 결과라 — 재시도 판정은 **호출자가 준 그대로**가 아니라 **교정 결과(키)** 기준
    # 으로 일관되게 본다(아래 진짜재시도·겹침알림).
    교정됨 = bool(호출자filename) and (키 != 호출자filename)
    교정메시지 = (f"filename \"{호출자filename}\" 은 규칙(영문 소문자·숫자·하이픈, 4자 "
               f"이상, 영문자 1개 이상 포함)에 안 맞아 \"{키}\" 로 바꿨습니다."
               if 교정됨 else None)
    # byline 의 날짜(항목 7, '26-09-27 재진단 — F2) — 1p 는 byline 을 통째로 모델이
    # 쓰지만, 지시문은 "부서명만 알면 그것만 채워라, 날짜는 시스템이 자동"이라고 안내한다.
    # 처음엔 byline 이 통째로 비었을 때만 채웠는데, 그러면 모델이 지시문대로 부서명만
    # 낸 byline('총무팀'·'<총무팀>')은 날짜 없이 그대로 나갔다(지시문·코드 불일치). **1p
    # byline 은 shared.표기.date_day('YY 꼴, 예 '26. 9. 26.)가 관례다**('26-09-26 2차
    # 진단 — 온톨로지 shared.작성원칙.날짜_기본의 2차검토 메모가 이 코드 쪽 정합을 지목
    # 했다) — 예전엔 여기서도 4자리 연도 꼴을 썼다(_오늘날짜글 한 곳에서 두 꼴을 다 만든다).
    _byline전 = doc.get("byline")      # 시스템이 채운 날짜를 '확인할 것'에 올리려고 받은 그대로 적어 둔다(M5)
    if 장르 == "samples":
        doc["byline"] = _byline_정규화(doc.get("byline"))
    # 표기꼴 교정(항목①·②, 구현자 B) — 여섯 장르 전부 부른다. 금액 단위 띄어쓰기는 장르
    # 무관(1p 대안검토 표에도 '만원'이 나온다), 자기 호칭 통일은 표기꼴.교정() 안에서
    # 규정·시행문·보도자료로 좁힌다.
    # reg13e 판정 E4('26-10-01) — 규정 '확인요청'(작성 모델이 스스로 정한 것, D1)은 표기 교정 **전에** 뗀다: 교정이 모델 글을 문서
    # 글처럼 고쳐 쓰고('회사는' → '공사는'), 그 칸 이름이 교정 기록('확인요청.0.가정: …')으로 사용자 앞에 나왔다(verify13d 2-5).
    _규정확인요청 = doc.pop("확인요청", None) if 장르 == "regulation" else None
    _B정규화알림 = _B정규화_시도(doc, 장르)
    # 보도자료 초안 정리(배포 날짜 꼴 자리표시·부제 붙임표·인용 머리 어순) — 새문서에서만
    # 부른다(저장은 사람이 고친 글이라 안 건드린다, 조번호꼴·붙임꼴과 같은 결).
    if 장르 in ("press", "press-release"):
        try:
            _보도정리 = 자료뿌리.모듈("표기꼴").보도초안정리(doc, 장르)
        except Exception as _e:
            _보도정리 = [f"보도초안정리() 실패({type(_e).__name__}) — 건너뜀"]
        if _보도정리:
            _B정규화알림 = "\n▸ ".join(x for x in (_B정규화알림, "보도자료 초안 정리 "
                                   f"{len(_보도정리)}곳: " + "; ".join(_보도정리[:4])) if x)
    _A정규화알림 = None
    # 사람이 이미 손본 문서를 다시 들이는 길 — 이어받기(resume, `_이어받음`)와 app.html '이 틀로 다시
    # 만들기'의 자료 없는 재등록(`_틀재등록`). 이 길에서는 규정초안정리를 끈다: 문체 선택(퍼센트·현대형)을
    # 바꾸는 교정이라 사람이 되돌린 값을 다시 고치게 된다('26-09-28 적대검토 F3). 표식은 여기서 뗀다
    # (`_이어받음`은 아래 승인 게이트가 따로 뗀다).
    _사람손본문서 = bool(doc.pop("_틀재등록", False) or doc.get("_이어받음"))
    if 장르 == "regulation":
        # reg13d 판정 D1 — 작성 모델이 스스로 정한 것('확인요청')은 문서에서 떼어 확인 물음으로만 옮긴다(아래 확인할것 · 등록 뒤
        # 검사자료 보관 → 웹앱 '확인할 것' 칸). 등록부·조립·검사 도구에는 들어가지 않는다. 떼기는 위 표기 교정 전에 했다(E4).
        _규정선택키_정규화(doc)
        # 조번호꼴.맞추기() 는 **새문서 입구에서만** 부른다 — 갓 지은 초안의 "주요내용"
        # 조번호를 실제 조 번호에 맞춰 고치는 일이라, 이미 등록된 문서를 사람이 편집기에서
        # 손으로 고친 뒤 저장(save)할 때 또 부르면 그 손질을 덮어쓸 위험이 있다(r9 설계
        # 지침 — 저장 입구는 _규정선택키_정규화 모양 고정만 그대로 한다).
        _A정규화알림 = _A정규화_시도("조번호꼴", "맞추기", doc)
        # 규정 초안 정리(C-1 비율 '100분의 N'·'퍼센트' / C-2 술어 계열 전통형 / C-3 시각·기산점·
        # 부칙 날짜, '26-09-28 규정 법제 문체 처방) — 조번호꼴 **뒤에**, 새문서에서만 부른다.
        # 표기꼴.교정() 안에 넣지 않는 까닭: 교정() 은 저장 입구에서도 돌아, 사람이 편집기에서
        # 되돌린 값을 저장할 때마다 다시 고친다(조번호꼴·보도초안정리와 같은 결).
        # 부칙의 시행일·시행 방식의 값은 코드가 고쳐 쓰지 않는다(사장님 판정 '26-09-29, 세 번째로 좁힘 — 내부 기록
        # reg10/date_norewrite.md: 자료를 갈래 나눠 부칙 때 자리를 고치던 R3 가 고칠 때마다 맞는 초안을 새로 깨뜨렸다).
        # 표기 교정(날로부터·온점 날짜·%·술어·호칭)은 다른 조문과 같이 부칙에도 한다 — 값은 그대로다(3차 M1, round3.md).
        # 그래서 규정초안정리엔 원문을 넘기지 않고, 원문은 확인 물음(늘 한 줄)에만 쓴다.
        _규정확인 = []
        _규정원문 = _자료글(원문) if 원문 else None
        try:
            _규정정리 = [] if _사람손본문서 else 자료뿌리.모듈("조문꼴").규정초안정리(doc, 장르)
        except Exception as _e:
            _규정정리 = [f"규정초안정리() 실패({type(_e).__name__}) — 건너뜀"]
        # 확인 물음은 따로 감싼다 — 같은 try 에 두면 확인할것() 이 터질 때 이미 고친 기록이 "실패 — 건너뜀"으로
        # 덮였다(reg10 적대검토 fidelity L1). 원문을 주면 부칙 시행일을 늘 한 줄로 묻는다(자료 구절을 싣는다).
        try:
            _규정확인 = [] if _사람손본문서 else 자료뿌리.모듈("조문꼴").확인할것(doc, 원문=_규정원문,
                                                                           확인요청=_규정확인요청 or [])
        except Exception as _e:
            _규정확인 = [f"확인할것() 실패({type(_e).__name__}) — 확인 물음을 만들지 못했습니다"]
        if _규정정리:
            _A정규화알림 = "\n▸ ".join(x for x in (_A정규화알림, "규정 초안 조문 표기 정리 "
                                   f"{len(_규정정리)}곳: " + "; ".join(_규정정리[:6])
                                   + (f" 외 {len(_규정정리) - 6}곳" if len(_규정정리) > 6 else "")) if x)
        # 사용자에게 되물을 거리(R3 부칙 시행일·R5 빈칸 주체·절차 빈틈) — 고치지 않고 묻는다(절차 사실은
        # 자료에 없으면 지어내지 않는다). 에이전트가 이 줄을 그대로 사용자에게 물어야 한다.
        if _규정확인:
            # 머리 "사용자에게 확인할 것(규정)" 은 그대로 둔다(test/r14_reg14b 가 이 앞머리를 본다).
            # 작업 방식('26-09-29): 함께 검수는 편집 전에 묻고, 바로 완성은 비운 채 끝 보고로 올린다.
            _A정규화알림 = "\n▸ ".join(x for x in (_A정규화알림, "사용자에게 확인할 것(규정) — "
                                   + ("편집 화면을 열기 전에 물어 채우세요" if os.environ.get("문서지능_웹앱") else
                                      _갈래("편집 화면을 열기 전에 물어 채우세요",
                                           "비운 채 끝 보고의 '확인할 것'에 올리세요"))
                                   + ":\n    · " + "\n    · ".join(_규정확인[:8])
                                   + (f"\n    · … 외 {len(_규정확인) - 8}곳" if len(_규정확인) > 8 else "")) if x)
    elif 장르 == "gongmun":
        _A정규화알림 = _A정규화_시도("붙임꼴", "분리하기", doc)
    # 빌드플랜 승인 게이트(사장님 지침 '26-08-25, WP-S3 강화 · '26-09-26 2차 진단 — 항목
    # 0·2로 plan_id **자동 채움을 걷어낸다**) — 새로 짓는 문서는 **승인된 구성 설계
    # (빌드플랜)**에 매여야 한다. plan_id 는 시스템이 지어낼 수 없는 값(사람의 승인 그
    # 자체)이라 자동으로 채우지 않는다 — 예전에 채웠던 '이 장르 최신 승인 플랜'은 세션의
    # **다른 문서**가 이미 쓴 플랜을 조용히 재활용해, 승인 게이트를 사실상 무력화했다
    # (그 plan_id 로 만든 문서가 둘이 되면 이후 새문서·조립이 '승인 없음'으로 막혔다).
    # 이어받기(resume)로 되살린 문서는 이미 승인·완성돼 낸 것이라 면제한다(표식 소거 후 통과).
    _이어 = doc.pop("_이어받음", False)
    if not _이어:
        # plan_id **요구**는 UI 없는 플러그인에서만 건다 — 웹앱(serve.py)은 화면으로 설계·승인을
        # 강제하고 '자료 없이 재등록' 같은 정당한 무플랜 경로(app.html)가 있어, 여기서 또 막으면
        # 웹앱이 깨진다. 승인 확인(_플랜승인막힘)은 양쪽 다: plan_id 가 있으면 승인됐는지 본다.
        if not os.environ.get("문서지능_웹앱") and not (doc.get("plan_id") or "").strip():
            후보 = _미매인승인플랜(장르)
            안내 = ""
            if 후보:
                안내 = ("\n  (참고 — 이 세션에 이 장르로 승인됐지만 아직 어느 문서에도 매이지 "
                       f"않은 플랜이 있습니다: {', '.join(후보[:5])}"
                       + (" 등" if len(후보) > 5 else "") + ". 이 자료에 맞는 것이면 그 "
                       "plan_id 를 그대로 써 왕복을 줄이십시오 — 다른 자료로 짠 설계일 "
                       "수 있으니 내용을 먼저 확인하십시오.)")
            return {"ok": False, "필요한것": "빌드플랜 승인", "로그":
                    "빌드플랜 승인 게이트 — 새 문서는 승인된 구성 설계(빌드플랜)에 매여야 합니다:\n"
                    "  ① 설계지시문내기(composeplan)로 빌드플랜을 짜서 플랜저장(saveplan) → plan_id\n"
                    "  ② " + _갈래("사용자에게 승인화면(plan)을 보여 주고 플랜승인(approveplan)으로 "
                                  "'승인'을 받으세요", "플랜승인을 직접 부르되 코멘트에 '바로 완성'을 적으세요") + "\n"
                    "  ③ 그 plan_id 를 doc 에 넣어 새문서 다시 호출" + 안내 +
                    "\n승인 없는 초안 조립을 막는 게이트입니다(작업 방식은 작업방식(workmode)으로 봅니다)."}
        막힘 = _플랜승인막힘([doc])
        if 막힘:
            return 막힘
        # purpose_type 생략 — plan_id 를 **명시로 준 경우에만** 그 플랜의 판정에서 채운다.
        if not doc.get("purpose_type") and (doc.get("plan_id") or "").strip():
            try:
                _plan = json.load(open(자료뿌리.플랜(doc["plan_id"]), encoding="utf-8"))
                _pt = ((_plan.get("판정") or {}).get("보고목적유형") or "").strip()
                if _pt:
                    doc["purpose_type"] = _pt
            except (OSError, ValueError):
                pass
    # 개인 기본 제목 모양('26-09-28) — 편집기에서 '이 모양을 기본으로' 해 둔 값을 새 초안의 **비어 있는**
    # 키에만 싣는다(플러그인만 — 웹앱은 app.html 이 브라우저 저장에서 싣는다). 사람이 손본 문서를
    # 다시 들이는 길(틀 재등록·이어받기)은 그 문서의 서식이 먼저라 건너뛴다.
    if not _사람손본문서 and not _이어:
        _기본모양알림 = _개인기본모양_싣기(doc, 장르)
        if _기본모양알림:
            _B정규화알림 = "\n▸ ".join(x for x in (_B정규화알림, _기본모양알림) if x)
    # 슬라이드 v2(부품 트리) 판별·검사('26-09-28) — 문서의 판형 키로 가른다(서버 판형 설정과 무관:
    # 옛 문서는 그대로 옛 경로). v2 모양이면 등록부에 넣기 **전에** 스키마·의미 규칙을 잰다 — hard 면
    # 등록하지 않고 위반 목록을 그대로 돌려준다(되돌릴 것이 없다, 자가수정이 바로 읽는다). 조립은
    # build/assemble_slides.py 가 판형 v2 문서를 v2 조립기로 보낸다(없으면 조립 오류로 되돌린다).
    _v2소프트 = []
    _v2출처고침 = []            # 약한 경로 출처 자동 비움(주관 판정 ⑦) — [(어디, 지운 글)]
    # 서버 모델 초안 표지(_서버채움, bench13 ③④) — 무엇이든 등록 전에 뗀다(v2 검사가 못 돌아도 문서에 남지 않게)
    _v2약한 = bool(doc.pop("_서버모델", False)) if isinstance(doc, dict) else False
    if 장르 == "slides":
        if isinstance(doc, dict) and isinstance(doc.get("슬라이드"), list):
            _슬라이드출처빈칸빼기(doc)   # 옛 판형도 자리표시뿐인 출처는 등록 전에 뺀다(W1). v2 는 아래 검사의 모양 정규화가 빼고 알린다
        try:
            _v2 = 자료뿌리.모듈("슬라이드v2")
            _v2판 = _v2.v2인가(doc)
        except Exception as _e:
            _v2, _v2판 = None, False
            print(f"[슬라이드v2] 모듈을 못 불렀습니다(옛 경로로 둡니다): {type(_e).__name__}: {_e}", file=sys.stderr)
        if _v2판:
            # 원문(플러그인 자료)은 _맥락이 없을 때 게이트에만 빌려 준다 — 요청 장수·판단 숫자 자료 대조('26-09-29 round2 §6)
            # 서버 모델 초안(_서버채움 표지)은 약한 경로 — 값 칸 지어냄·날짜·비교 기준·판단 인과를 hard 로 되먹인다(bench13 ③④)
            _v2하드, _v2소프트 = _v2.검사(doc, 원문=(_자료글(원문) if 원문 else None), 약한경로=_v2약한)
            # 약한 경로 출처 hard 가 두 회 연속 같으면 그 출처 칸을 비운다('26-09-30 주관 판정 ⑦ — 확실한 꼴: bench14 EXAONE
            # s2 다섯째 초안의 hard 가 출처 연도 한 건뿐이었다). 고친 곳은 확인할것에 남긴다
            if _v2약한 and (doc.get("plan_id") or "").strip():
                try:
                    _v2하드, _v2소프트 = _v2출처되먹임(doc, _v2, _v2하드, _v2소프트, 원문, _v2출처고침)
                except Exception as _e:
                    print(f"[슬라이드v2] 출처 되먹임 기록 실패(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
            if _v2하드:
                return {"ok": False, "필요한것": "v2 문서 고침", "로그":
                        f"[게이트 위반] {doc.get('filename') or '?'} (판형 v2 — 등록하지 않았습니다)\n"
                        + "\n".join(f"  ✗ {h}" for h in _v2하드[:40])
                        + (f"\n  … 외 {len(_v2하드) - 40}건" if len(_v2하드) > 40 else "")
                        + ("\n[소프트 경고]\n" + "\n".join(f"  ! {s}" for s in _v2소프트[:20]) if _v2소프트 else "")}
            # 모양 정규화로 고친 것('79점'→수 79 등, '26-09-29 ⑰)은 알림(▸)으로만 — '!' 소프트 줄이 아니라서
            # app.html 의 슬라이드 소프트 재시도(모델 한 번 더)를 부르지 않는다. 등록되는 doc 은 고친 뒤 모양이다.
            _v2고친 = [s[len("(모양 정규화) "):] for s in _v2소프트 if s.startswith("(모양 정규화) ")]
            if _v2고친:
                _B정규화알림 = "\n▸ ".join(x for x in (_B정규화알림, "슬라이드 모양을 고쳐 받았습니다 — "
                                                       + " · ".join(_v2고친[:8])
                                                       + (f" 외 {len(_v2고친) - 8}건" if len(_v2고친) > 8 else "")) if x)
    # 그림 스펙 정리('26-09-30) — 목록 id 확인·모델 좌표 지우기·옛 꼴 id 로·파일 이름 빼기·설계 그림 계획 대조.
    # 조립 **전에** 한다(모양이 틀린 그림 키가 조립기를 크래시시키지 않게). 사람이 고친 저장(save)에는 걸지 않는다.
    try:
        _그림정리줄, _그림정리항목 = _그림정리(doc, 장르)
    except Exception as _e:
        _그림정리줄, _그림정리항목 = None, []
        print(f"[그림] 정리 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    if _그림정리줄:
        _B정규화알림 = "\n▸ ".join(x for x in (_B정규화알림, _그림정리줄) if x)
    try:
        등록 = 자료뿌리.등록부(장르)
    except 자료뿌리.이름틀림:
        등록 = ""
    if not 등록 or not os.path.exists(등록):
        있는것 = [os.path.basename(x).replace("-docs.json", "") for x in 등록부들()]
        return {"ok": False, "로그": f"모르는 장르: {장르} (있는 것: {있는것})"}
    # (api:F6 수정, e2e r6 재진단 '26-09-27) — SKILL.md·skill_doc.py 는 "doc 에 genre
    # 키가 없다 — 넣어도 무시된다"고 안내한다. 새로 짓는 문서는 그 안내대로 **항상
    # 등록부에서 파생한 값으로 덮어써** 호출자가 준 genre(한글 표시 이름일 수 있다,
    # 예: "발표 슬라이드")를 무시한다(이 문서가 실제로 들어가는 등록부는 아래 `등록`
    # 이 가리키는 장르 하나뿐이라, genre 는 그 등록부 값과 달라질 이유가 없다).
    #
    # (api:R7-4 재수정, '26-09-27 3차 진단) — 위 "항상 덮어쓰기"가 **이어받기(resume)
    # 왕복을 깼다.** 손으로 적은 {"samples":"onepage"} 짝은 press 를 빠뜨려(등록부
    # 이름 "press"를 그대로 돌려줬다) 매번 doc["genre"]="press"로 다시 박았다. 그런데
    # 조립기(assemble_press.py)가 실제로 <html data-genre> 에 심는 값은 "press-release"
    # 다(build/genres.py 표의 '장르' 필드) — 등록부 이름과 data-genre 값이 갈린 장르는
    # press 하나뿐이다. 그 결과 막 이어받은 문서를 다시 조립하면 fr-doc.genre("press")
    # 와 data-genre("press-release")가 어긋나, **그다음** 이어받기가 거절됐다(재현:
    # 이어받기→새문서→조립까지는 되지만, 그 산출물을 다시 이어받으면 실패).
    #
    # 고침 둘: ① 손목록 대신 genres.등록부()에서 세어서 얻는다(규칙 2, 새 장르가 늘 때
    # 이 자리만 조용히 안 빠지게). ② **이어받기로 들어와 이미 genre 값이 있으면 그대로
    # 둔다** — 조립기가 심은 값을 다시 등록부 이름으로 바꾸는 왕복 자체를 없앤다. 다만
    # 이어받기인데 genre 가 비어 있으면(2026-08-08 실측대로 <html data-genre> 속성에만
    # 있던 옛 문서 — _장르찾기 가 doc 를 직접 고치지 않고 이름만 돌려준다) 여기서마저
    # 안 채우면 genre 없는 문서가 등록부에 들어가므로, 그 경우엔 새 문서와 똑같이 채운다.
    if not _이어 or not doc.get("genre"):
        _이름장르값 = {g["이름"]: g["장르"] for g in 자료뿌리.모듈("genres").등록부()}
        doc["genre"] = _이름장르값.get(장르, 장르)
    doc["_수정시각"] = 자료뿌리.문서수정시각()   # 낙관적 잠금의 표 — 형식은 한 곳에서
    # 등록부에 한 줄 붙이는 일은 **읽고-고치고-쓰는** 세 걸음이라 빗장을 쥐고 한다
    # (적대리뷰 ③). 안 쥐면 둘이 같은 등록부를 각자 읽고 각자 append 해서, 뒤에 쓴
    # 쪽이 앞 쪽의 문서를 통째로 지운다 — 앞 쪽 사용자는 200 ok 를 받아 놓고.
    덮어씀 = False
    옛doc = None       # 덮어쓴 자리 — 조립이 실패하면 이걸로 되돌린다(항목 3)
    겹침알림 = None    # 겹쳐서 새 키로 바뀐 사실을 알리는 문구(항목 1·2)
    판번호 = None      # 덮어쓰기 전에 남긴 옛 초안의 판 번호(new_defects 3차 재발 고침)
    try:
        with 자료뿌리.빗장(등록):
            cur = json.load(open(등록, encoding="utf-8"))
            기존이름 = {d.get("filename") for d in cur}
            if _웹앱:
                # 웹앱 경로의 겹침 판정은 HEAD(1차 이전) 그대로 — **이 등록부 안**만 본다.
                # 2차가 넓힌 교차 장르·산출물 겹침 확인은 여기서 끄고, 아래 덮어쓰기 재시도
                # 판정도 건너뛰어 늘 새 키(-N)로만 유일화한다(위 _유효한슬러그 주석과 짝).
                겹침 = 키 in 기존이름
            else:
                겹침 = (키 in 기존이름 or 키 in _전역키목록()
                      or os.path.exists(자료뿌리.산출물(키, "html")))
            # "진짜 재시도"만 덮어쓴다(new_defects 재발 — 제목이 전혀 다른 문서에 기존 키를
            # 명시하니 사람 손 안 탄 초안이 조용히 덮어써졌다) — 호출자가 **명시한 그
            # filename** 과 정확히 같거나(자동생성이 아니다), **교정 결과가 같거나**(F3,
            # 교정됨 — 같은 입력은 같은 교정 결과를 내므로 이것도 "같은 이름"이다), 사람
            # 손을 탄 적이 없고, **같은 plan_id·같은 제목**일 때만 재시도로 본다. 웹앱은
            # 위에서 이미 겹침을 좁혀 놨으니 이 판정 자체를 타지 않는다(HEAD 처럼 늘 새 키).
            진짜재시도 = False
            if (not _웹앱) and 겹침 and (not 자동생성 or 교정됨) and 키 in 기존이름 and not _문서손탔나(키):
                _기존doc = next((d for d in cur if d.get("filename") == 키), None)
                if _기존doc is not None:
                    _같은플랜 = (str(doc.get("plan_id") or "").strip()
                              == str(_기존doc.get("plan_id") or "").strip())
                    _새제목 = str(제목뽑기(doc) or "").strip()
                    # 같은 제목만이 아니라 **비슷한 제목**도 재시도로 본다('26-09-28 5~7차 벤치 —
                    # 제목 길이 경고를 받고 제목을 줄여 다시 등록하면 매번 새 키(-2·-3)가 생겨 세션에
                    # 고아 초안이 쌓였다, 에이전트 여럿이 SKILL.md 의 '같은 filename 은 덮어쓴다'와
                    # 다르다고 짚음). plan_id 가 같고(빈 값 아님) 두 글자 묶음이 40% 이상 겹칠 때만 —
                    # 제목이 전혀 다른 문서(new_defects 재발 사례)는 여전히 새 키로 간다.
                    _옛제목 = str(제목뽑기(_기존doc) or "").strip()
                    _같은제목 = bool(_새제목) and (_새제목 == _옛제목 or _제목비슷한가(_새제목, _옛제목))
                    진짜재시도 = _같은플랜 and bool(str(doc.get("plan_id") or "").strip()) and _같은제목
            if 진짜재시도:
                덮어씀 = True
                for _i, _d in enumerate(cur):
                    if _d.get("filename") == 키:
                        옛doc = cur[_i]
                        # 판 기록은 **덮어쓰기 전에** 남긴다(new_defects — 조립 성공 뒤로
                        # 옮겼던 2차 수정은 보관()이 등록부의 '지금' 문서를 찍어 옛 초안이
                        # 아니라 새 초안을 판에 담았다. 아직 등록부엔 옛doc 이 있는 지금이
                        # 옛 초안을 찍을 수 있는 유일한 시점이다).
                        try:
                            판번호 = 자료뿌리.모듈("version", "history").보관(
                                키, "자동", 고친이유="같은 filename 재호출(새문서) — 같은 "
                                "plan_id·제목의 재시도로 보고 이전 초안을 덮어씀", 누가="자동")
                        except Exception:
                            판번호 = None   # 판 기록 실패해도 덮어쓰기 자체는 막지 않는다(규칙 3)
                        cur[_i] = doc
                        break
            elif 겹침:
                # 진짜 재시도가 아니면 **절대 덮어쓰지 않고** 유일하게 만든다 — 시스템이
                # 만든 키(자동생성)가 겹친 경우, 사람 손 탄 문서, 같은 filename 이라도
                # plan_id·제목이 달라 다른 문서인 경우, 다른 장르·산출물과 겹친 경우 모두.
                원래키 = 키
                if _웹앱:
                    이유 = None    # 웹앱은 HEAD 그대로 — 알림 없이 조용히 유일화한다
                elif 키 in 기존이름 and _문서손탔나(키):
                    이유 = "사람 손(편집기 저장·되돌리기)을 탄 적이 있어"
                elif 키 in 기존이름:
                    이유 = "같은 filename 이지만 다른 계획(plan_id)이나 제목의 문서로 보여"
                else:
                    이유 = "다른 장르 문서나 산출물과 이름이 겹쳐"
                전체존재 = 기존이름 if _웹앱 else (기존이름 | _전역키목록())
                키 = _고유키만들기(키, 전체존재)
                doc["filename"] = 키
                cur.append(doc)
                if (not 자동생성 or 교정됨) and 이유:
                    겹침알림 = f"'{원래키}' 는 이미 있고 {이유} 덮어쓰지 않고 새 키 '{키}' 로 만들었습니다."
            else:
                cur.append(doc)
            # 원자 쓰기(WP-S2 ③, E-1) — 등록부는 이 세션 문서 전부가 든 **정본 한 파일**이다.
            # 쓰는 도중에 문서목록·조립 subprocess 가 읽으면 반토막 JSON 을 받는다.
            자료뿌리.원자json(등록, cur, indent=2)
    except 자료뿌리.못잠금 as e:
        return {"ok": False, "로그": str(e)}
    # reg13d 판정 D1 — 작성 모델의 '확인요청'을 이 문서 키로 보관한다(웹앱 '확인할 것' 칸·확인할것 op 가 다시 읽는다). 사람이 손본
    # 문서를 다시 들이는 길은 건드리지 않는다. 같은 키로 다시 만들면 새 초안의 것으로 바꾼다(없으면 비운다). 세션 밖(라이브러리로 부르는
    # 도구)에서는 보관하지 않는다 — 기본 자료뿌리에 파일을 새로 만들지 않는다.
    if 장르 == "regulation" and not _사람손본문서 and 자료뿌리.세션열쇠():
        try:
            # reg13e 판정 E3 — 작성 당시 조 제목을 함께 싣는다(사람이 조를 지우거나 옮긴 뒤 확인할것 op 가 가리키던 조를 따라가게).
            # reg13g 판정 H2 — 스냅은 조 칸이 '제N조' 한 꼴일 때만 둔다(다른 꼴은 거르지 않는다)
            _보관요청 = 자료뿌리.모듈("조문꼴").확인요청보관(_규정확인요청, doc)
            _검사자료고치기(키, lambda 줄, v=_보관요청: 줄.__setitem__("규정확인요청", v))
        except Exception as _e:
            print(f"[확인요청] 보관 실패(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)

    # **자기 문서만 조립한다**(WP-S2 ②). 전에는 등록부 전체를 다시 만들어서, 문서를
    # 하나 새로 만들 때마다 같은 세션의 다른 문서 산출물이 전부 다시 써졌다.
    _속성거부_감시시작()
    try:
        r = 조립(f"build/{장르}-docs.json", only=키)
    finally:
        _속성거부목록 = _속성거부_감시끝()
    if not r["ok"]:
        # 조립이 안 되면 등록부를 되돌린다 — 반쯤 들어간 문서가 남으면 다음이 다 걸린다.
        # **되돌리기는 되돌리기여야 한다**(적대리뷰 ③, 항목 3 — 덮어쓴 경우도 마찬가지다):
        # 덮어쓴 자리는 **옛 doc 으로 되돌린다**(그 자리를 비우면 문서 자체가 사라진다).
        # 새 줄로 붙인 경우는 다시 읽어서 **내가 넣은 줄 하나만** 뺀다(조립은 수백 ms~수 초라
        # 그 사이 남이 성공시킨 문서까지 스냅샷으로 같이 되감기지 않게).
        if 덮어씀:
            복원됨, 사고, 비켜감 = False, "", False
            try:
                with 자료뿌리.빗장(등록):
                    cur2 = json.load(open(등록, encoding="utf-8"))
                    for _i, _d in enumerate(cur2):
                        if _d.get("filename") == 키:
                            # 그 사이 다른 호출이 같은 자리를 또 썼으면(경합, new_defects
                            # 재발 — 반대 순서 재현) 되돌리지 않는다. 스냅샷 복원이 남의
                            # 성공을 되감을 수 있어, 내가 쓴 doc 그대로인지(_수정시각)만
                            # 확인해서 판단한다(등록부 전체가 아니라 이 한 자리만 본다).
                            if _d.get("_수정시각") == doc.get("_수정시각"):
                                cur2[_i] = 옛doc
                                복원됨 = True
                            else:
                                비켜감 = True
                            break
                    if 복원됨:
                        자료뿌리.원자json(등록, cur2, indent=2)
            except 자료뿌리.못잠금 as e:
                사고 = str(e)
            if 사고:
                말 = "조립하지 못했고 이전 초안으로 되돌리지도 못했습니다 — " + 사고
            elif 복원됨:
                말 = "조립하지 못해 이전 초안으로 되돌렸습니다"
            elif 비켜감:
                말 = ("조립하지 못했지만, 그 사이 다른 호출이 이 문서를 바꿔 되돌리지 "
                      "않았습니다 — 지금 등록부 내용을 확인하세요.")
            else:
                말 = "조립하지 못했고 이전 초안으로 되돌리지도 못했습니다 — 등록부에서 이 문서를 찾지 못함"
        else:
            뺀수, 사고 = _등록부에서한줄빼기(등록, 키)
            고아 = _고아산출물치우기(키)
            말 = "조립하지 못해 되돌렸습니다"
            if 사고:
                말 = "조립하지 못했고 되돌리지도 못했습니다 — " + 사고
            elif 뺀수 != 1:
                말 = f"조립하지 못해 되돌렸습니다 (등록부에서 뺀 줄 {뺀수}개)"
            말 += ("" if not 고아 else f" · 고아 산출물 {고아}개 치움")
        return {"ok": False, "로그": 말 + "\n" + r["로그"]}
    if 덮어씀:
        # 남의 문서를 조립해 놓고 내 성공으로 보고하지 않는다(new_defects 재발 — 반대
        # 순서 재현: A 가 쓴 뒤 B 가 같은 자리를 또 덮어쓰고, A 의 조립이 그 사이 B 가
        # 쓴 내용을 읽어 성공했는데도 A 가 'ok:true 만들었습니다'를 받았다). 조립 시점
        # 등록부의 _수정시각이 내가 쓴 값과 다르면, 그 사이 다른 호출이 같은 자리를 또
        # 덮어써 조립은 **그쪽 내용**으로 된 것이다 — 그 경우 실패로 보고한다(등록부는
        # 이미 그 다른 호출의 몫이니 여기서 되돌리지 않는다).
        try:
            cur3 = json.load(open(등록, encoding="utf-8"))
            _지금시각 = next((d.get("_수정시각") for d in cur3 if d.get("filename") == 키), None)
        except (OSError, ValueError):
            _지금시각 = doc.get("_수정시각")
        if _지금시각 != doc.get("_수정시각"):
            return {"ok": False, "로그":
                    f"'{키}' 조립은 됐지만, 그 사이 다른 호출이 같은 문서를 또 덮어써 "
                    "지금 결과가 이 요청 내용이 아닙니다 — 등록부를 확인하고 필요하면 다시 부르세요."}
    _그림문서묶기(키, doc, 원문, 자료파일)  # 이 대화의 자료·문서가 쓴 그림·읽은 자료(자료파일 — 없으면 원문에 든 자료)의 파일을 문서에 묶는다 — 편집기 서랍이 이 범위로 선다
    돌리기([sys.executable, "workspace/render_editor_any.py", 키])
    로그 = f"'{키}' 를 만들었습니다\n" + r["로그"]
    if 교정메시지:
        로그 += "\n▸ " + 교정메시지
    if _A정규화알림:
        로그 += "\n▸ " + _A정규화알림
    if _B정규화알림:
        로그 += "\n▸ " + _B정규화알림
    if 덮어씀:
        로그 += ("\n▸ 같은 filename 이 이미 있었고 같은 plan_id·같거나 비슷한 제목의 재시도로 보여 그 초안을 "
                 "덮어썼습니다" + ("(판 기록은 남았습니다)." if 판번호 else "."))
    elif 겹침알림:
        로그 += "\n▸ " + 겹침알림
    값 = {}
    if _속성거부목록:
        # (mcp:s5 수정, e2e r6 재진단 '26-09-27) — 문체검사·조판게이트·지어냈나 **어느
        # 것도 이걸 못 본다**(값이 조용히 기본값으로 뭉개진 것이지 문체·분량·지어낸
        # 사실 문제가 아니다). 셋과 나란히 값에 구조화해서 싣고, 로그도 검사요약과
        # 갈라 따로 경고한다 — JSON 만 읽는 클라이언트(MCP)도 놓치지 않게.
        값["속성거부"] = {"건수": len(_속성거부목록),
                       "경로": [x["자리"] for x in _속성거부목록]}
        _자리목록 = ", ".join(sorted({x["자리"] for x in _속성거부목록}))
        로그 += (f"\n\n⚠ 속성값 거부 {len(_속성거부목록)}건 — 지정한 값을 조립기가 받지 않아 "
                 f"기본값으로 대체했습니다(문체·조판·지어냈나 검사와는 별개 문제입니다 — "
                 f"편집 화면에서 그 자리를 직접 확인하세요"
                 + ("" if os.environ.get("문서지능_웹앱") or _알려진방식() == "함께검수"
                    else " — 바로 완성이면 끝 보고의 '확인할 것'에 올리세요")
                 + f"): {_자리목록}")
    # 글자 깨짐 검사(build/깨짐.py, r10 W2 실측) — **검사 플래그·채널과 무관하게 늘
    # 돈다**(모든 채널) — 정규식 스캔이라 조판게이트(헤들리스 크롬)처럼 비싸지 않고,
    # 웹앱도 이 문제는 검사=거짓 기본값으로 그냥 넘겨선 안 된다(소형 서버 모델이
    # temperature 없이 낼 때 글자가 깨진다 — _LLM온도 참고). 사람이 편집기에서 고친
    # 저장(save) 입구에는 안 건다 — 사람 글은 검열하지 않는다(이 함수는 새문서 전용).
    # **문서 자체는 등록된 채로 남는다**(ok=True 로 낸다) — app.html 의 초안등록되시도()
    # 가 값["깨짐"].ok===false 를 되먹여 재시도하고(글자깨짐확인 op 로 나중에도 다시
    # 잴 수 있다), 여기서 등록을 막으면 이미 조립·렌더까지 끝난 뒤라 되돌리기가
    # 더 복잡해진다(r10 재검토, 검토 발견 반박 — "값에만 싣고 ok 는 참"이라는 지적은
    # 맞지만, 그건 이 함수의 '통과' 여부지 '아무도 안 읽는다'는 뜻은 아니다: 아래
    # try/except 는 별개로 모듈이 없을 때 새문서 전체가 죽는 걸 막는다 — r10 재검토,
    # HIGH — build/깨짐.py 가 미추적이라 배포 트리에서 빠지면 기존엔 여기서 그대로
    # ImportError 가 터져 등록·조립이 다 끝난 뒤에도 '처리하다 오류'로 실패 보고됐다).
    try:
        _깨짐발견 = 자료뿌리.모듈("깨짐").검사(doc)
    except Exception as _e:
        _깨짐발견 = []
        print(f"[깨짐] 검사 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
        값["깨짐"] = {"ok": False, "오류": type(_e).__name__}
    if _깨짐발견:
        값["깨짐"] = {"ok": False, "걸림": _깨짐발견}
        로그 += "\n\n▸ " + 자료뿌리.모듈("깨짐").메시지(_깨짐발견)
    # 그림 상태('26-09-30 주관 판정) — 자리 없는 장르에 온 그림 키·못 얻은 그림을 조용히 흘리지 않는다.
    # 모든 채널(웹앱 포함)에 한 줄로 알린다. 확인할것에는 _확인할것모으기 가 같은 것을 싣는다.
    try:
        _그림줄 = _그림살피기(doc, 장르, 키)[0]
    except Exception as _e:
        _그림줄 = None
        print(f"[그림] 살피기 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    if _그림줄:
        로그 += "\n\n▸ " + _그림줄
    # 그림 생성 대기(P2) — 채울 요청을 절대 경로와 함께 응답에 싣는다(에이전트가 manifest 를 찾아 헤매지 않게).
    # 로그 블록은 위 조립 로그(_조립대기붙이기)에 이미 들었다 — 여기서는 구조 칸만 옮긴다.
    _그림대기 = (r.get("그림대기") if isinstance(r, dict) else None) or []
    if 검사:
        # 새문서 한 번에 검사까지(항목 3) — 문체검사·조판게이트는 **이 문서 하나만**
        # (등록부·세션 산출물 전부를 다시 재지 않는다, 항목 1·5 와 짝). 지어냈나는
        # 원문이 왔을 때만(대조할 원문이 없으면 잴 수 없다).
        r문체 = 문체검사(key=키)
        값["문체검사"] = r문체
        r조판 = 조판게이트(key=키)
        값["조판게이트"] = r조판
        검사요약 = [f"문체검사 {'PASS' if r문체.get('ok') else 'FAIL'}",
                 f"조판게이트 {'PASS' if r조판.get('ok') else 'FAIL'}"]
        # 슬라이드 '글머리만' 비율이 한 응답 안에서 두 값으로 보였다(F6, e2e s6 재진단,
        # '26-09-27) — 조립(build/assemble_slides.py._소프트지표)이 **문서 JSON 단계**에서
        # 미리 잰 값(하드·소프트 판정은 이 값을 쓴다, 위 조립 로그의 "[슬라이드 지표]"·
        # "글머리만 비율")과, 조판게이트(build/audit.js)가 **렌더된 DOM** 에서 다시 잰
        # bullet_only_ratio 는 측정 단계가 달라 값이 어긋날 수 있다(assemble_slides.py의
        # _소프트지표 docstring이 이미 그렇게 설계됐다고 밝힌다 — 판정을 하나로 합치는 건
        # 이번 범위가 아니다). 둘 다 응답에 그대로 실리면 사람이 "어느 게 진짜냐"고 헷갈리니,
        # **판정에 쓰인 쪽(조립 시점 값)**을 밝히고 둘이 다르면 그 사실을 요약에 남긴다.
        _글머리만_불일치 = None
        if 장르 == "slides":
            _조립글머리만 = _돔글머리만 = None
            _m = re.search(r"글머리만\s*(?:장\s*비율|비율)?\s*([\d.]+)", r.get("로그") or "")
            if _m:
                _조립글머리만 = float(_m.group(1))
            _m2 = re.search(r'"bullet_only_ratio"\s*:\s*([\d.]+)', r조판.get("로그") or "")
            if _m2:
                _돔글머리만 = float(_m2.group(1))
            if _조립글머리만 is not None and _돔글머리만 is not None \
                    and abs(_조립글머리만 - _돔글머리만) >= 0.01:
                _글머리만_불일치 = (
                    f"글머리만 비율은 **조립 시점(문서 JSON) 값 {_조립글머리만:.2f} 로 판정했습니다** "
                    f"— 조판 게이트가 렌더된 화면에서 다시 잰 값은 {_돔글머리만:.2f} 로 다를 수 있습니다"
                    "(그림 배치 등 렌더 세부는 화면 쪽이 더 정확하지만, 하드·소프트 판정 자체는 "
                    "조립 시점 값을 씁니다 — 정책은 바뀌지 않았습니다).")
        _확장걸림 = []
        # 플러그인은 이 문서가 처음 받은 원문으로 잰다(fixup3, verify2 §1-B X1b·X2 — 같은 파일 이름을 원문 없이,
        # 또는 초안 자신의 글을 원문으로 다시 불러 FAIL 을 풀던 길). 웹앱·라이브러리는 받은 원문 그대로.
        원문, _새원문알림 = _검사원문(키, 원문)
        if 원문:
            r지어냄 = 지어냈나검수(키, 원문)
            값["지어냈나"] = r지어냄
            검사요약.append(f"지어냈나 {'PASS' if r지어냄.get('ok') else 'FAIL'}")
            # 확장 지어냄 검사(월표현·메타칸·출처·붙임·인용·보도시점, r9) — 지어냈나검수
            # (숫자·이름)와 별개 칸을 본다. 여기서도 값만 값에 싣고, 로그엔 건수·경로와
            # "교정지시로 받아 교정적용으로 보내라"는 한 줄만 남긴다(원문·값 자체는 안 남긴다,
            # 지어냈나검수 와 같은 결).
            try:
                _확장걸림 = 자료뿌리.모듈("지어냈나").검토하기(_자료글(원문), doc)
            except Exception as _e:
                # r9 검토자 발견(loop-channels LOW) — 예전엔 예외를 조용히 삼켜 값·로그
                # 어디에도 흔적이 없었다(규칙 3 '조용한 실패 금지' 위반) — 터진 사실을
                # stderr 와 값에 남긴다(원문이 배열이면 _자료글 로 먼저 문자열로 통일한다).
                _확장걸림 = []
                print(f"[지어냈나확장] 검사 오류: {type(_e).__name__}: {_e}", file=sys.stderr)
                값["지어냈나확장"] = {"ok": False, "오류": type(_e).__name__}
            if _확장걸림:
                # 값 아래 다른 칸들(문체검사·조판게이트·지어냈나)이 전부 {"ok":…} 모양이라
                # (아래 "not all(v.get('ok') ...)" 줄이 그 모양을 그대로 믿는다) 이 칸도
                # 맨 목록이 아니라 같은 {"ok","걸림"} 모양으로 싣는다.
                값["지어냈나확장"] = {"ok": False, "걸림": _확장걸림}
        else:
            # 원문이 없으면 지어냈나를 **건너뛴다** — 조용히 빠지지 않게 요약·기록에 '건너뜀'을 남긴다(H2).
            검사요약.append("지어냈나 건너뜀(원문 없음)")
            _검사적기(키, "지어냄", True, 건너뜀="원문 없음")
        로그 += "\n\n▸ 검사 결과: " + " · ".join(검사요약)
        if _새원문알림:
            로그 += "\n▸ " + _새원문알림
        if _글머리만_불일치:
            로그 += "\n▸ " + _글머리만_불일치
        if _확장걸림:
            _확장경로 = ", ".join(sorted({g["어디"] for g in _확장걸림})[:20])
            로그 += (f"\n▸ 확장 지어냄 검사에도 {len(_확장걸림)}건 걸렸습니다({_확장경로}) — "
                     "교정지시(fabfix) 작업을 불러 받은 지시대로 고친 JSON 을 "
                     "교정적용(fabfixapply) 작업으로 보내면 자료에 없는 값만 골라 고칠 수 있습니다.")
        if not all(v.get("ok") for v in 값.values()):
            로그 += "\n  (FAIL 이 있으면 그 로그를 보고 고친 뒤 저장(save)으로 반영하고 다시 검사하세요.)"
    elif not os.environ.get("문서지능_웹앱"):
        로그 += ("\n\n▸ 검사를 건너뛰었습니다(검사=false) — 이 판은 검사 기록이 없어 내보내기(export)가 "
                 "거절합니다. 검사 true·원문으로 다시 부르거나 문체검사·조판게이트·지어냈나를 돌리세요.")
    # 끝 보고의 '확인할 것'(M5) — 코어가 아는 것을 구조로 싣는다. 에이전트는 여기에 가정·추론한 값만 더한다.
    # 값(값 dict)이 아니라 최상위 칸에 둔다: 값 아래 칸은 전부 {"ok":…} 모양이라고 믿는 줄(위)이 있다.
    확인할것 = None
    if not os.environ.get("문서지능_웹앱"):
        try:
            확인할것 = _확인할것모으기(doc, 장르, [교정메시지, _A정규화알림, _B정규화알림],
                                  locals().get("_규정확인") or [], _v2소프트, _속성거부목록, 값, _byline전,
                                  key=키, 건너뜀=bool(검사 and not 원문),
                                  원문확인=_원문확인줄(doc, 장르, _자료글(원문) if 원문 else ""))
        except Exception as _e:
            print(f"[확인할것] 모으기 실패(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
            확인할것 = [{"종류": "오류", "어디": "", "내용": f"확인할 것 목록을 만들지 못했습니다({type(_e).__name__})"}]
        # 그림 정리에서 나온 확인거리(목록에 없는 id·로고 추정·비밀 표지·같은 그림 두 번·설계 계획에서 빠진 그림)
        for _종, _어, _내 in (locals().get("_그림정리항목") or []):
            if not any(x.get("어디") == _어 and x.get("내용") == _내 for x in (확인할것 or [])):
                확인할것 = (확인할것 or []) + [{"종류": _종, "어디": _어, "내용": _내}]
        if 확인할것:
            로그 += f"\n▸ 확인할 것 {len(확인할것)}건을 값 밖 '확인할것' 칸에 실었습니다(끝 보고에 그대로 씁니다)."
    # 다음 할 일 — 작업 방식('26-09-29)에 따라 갈린다. 이 대화에서 작업방식(workmode)이 정한 방식이나 저장된
    # 선택을 알면 그 갈래만, 모르면 두 갈래를 다 적는다(M1). 웹앱은 화면이 흐름을 쥐어 붙이지 않는다.
    if not os.environ.get("문서지능_웹앱"):
        로그 += "\n\n▸ 다음 — " + _갈래(
            "검사(문체·조판·지어냈나)를 통과시킨 뒤 편집기열기(editor)로 편집 화면을 열어 사용자가 다듬게 하고, "
            "'이대로 좋다'는 확인 뒤에만 내보내세요(export).",
            "FAIL 은 사유대로 고쳐(최대 3회) 통과하면 내보내기(export) 뒤 끝 보고(만든 파일·요지·확인할 것·"
            "'편집기 열어줘' 안내)를 하세요 — 3회 안에 못 넘으면 내보내지 말고 까닭을 알리세요.")
    본 = {"ok": True, "key": 키, "편집화면": f"workspace/editors/editor-{키}.html",
          "값": 값, "로그": 로그}
    for _어, _글 in _v2출처고침:          # 웹앱(약한 경로)에도 싣는다 — 사람이 끝에 볼 자리
        확인할것 = (확인할것 or []) + [{"종류": "고친 곳", "어디": _어, "내용":
                                   f"출처 '{_글}' 가 출처 검사(자료에 없는 이름·연도·일반 말)에 거듭 걸려 그 출처를 뺐습니다 — 자료의 출처 이름이 있으면 적어 주세요"}]
    if os.environ.get("문서지능_웹앱"):
        # 웹앱에도 확인 물음·본문 출처 줄을 싣는다('26-09-30 W2 — 바로 완성 끝 보고와 웹앱 확인할것 모두). 플러그인·라이브러리는 위 모으기가 싣는다.
        # app.html 은 새문서에 원문을 보내지 않는다(자료는 doc._맥락 으로만 온다 — 편집기 AI 재작성이 되찾는 배경). 원문이 없으면
        # 서버에 온 그 맥락으로 잰다(X2 — 클라가 원문을 새로 왕복하지 않는다, wire_verify §2: 실제 웹 흐름에서 한 줄도 안 나왔다).
        # fixup3 Z2 — 맥락은 앞 4,000자 조각이다. 서버가 가진 자료 전문(이 세션의 판정·설계 등에서 받은 글, _웹전체원문)으로 재고,
        # 잘린 조각뿐이면 자료 밖 판정(본문 출처)은 싣지 않고 '일부만 대조' 한 줄을 알린다.
        # fixup4 G5 — 이 문서를 만들 때 쓴 원문(앞 맞춤으로 고른 보관본)을 문서 키에 묶는다. 뒤의 확인할것은 이 묶음으로만 찾는다.
        if not 원문:
            _웹원문묶기(키, doc)
        _웹원문, _웹온전 = (_자료글(원문), True) if 원문 else _웹전체원문(doc, 키)
        if _웹원문:
            확인할것 = (확인할것 or []) + _원문확인줄(doc, 장르, _웹원문, 출처=_웹온전) or 확인할것
            if not _웹온전:
                확인할것 = [{"종류": "자료 일부", "어디": "", "내용": _일부대조말}] + (확인할것 or [])
        _잘림 = None if 원문 else _자료잘림줄(doc, 키)       # G4 — 예산에 맞춰 앞 일부로 만든 자료
        if _잘림:
            확인할것 = [_잘림] + (확인할것 or [])
    if 확인할것 is not None:
        본["확인할것"] = 확인할것
    if locals().get("_그림대기"):
        본["그림대기"] = _그림대기          # 값 밖 최상위(값 아래 칸은 {"ok":…} 모양이라고 믿는 줄이 있다)
    return 본


def _그림생성되나():
    """이 실행에서 그림을 만들 수 있나 — 그림을 그릴 수 있는 에이전트(host)만. 웹앱 서버는 늘 아니다('26-09-30)."""
    if os.environ.get("문서지능_웹앱"):
        return False
    try:
        return bool(자료뿌리.모듈("imageasset").providers().get("host"))
    except Exception:
        return False


# ── 첨부 그림 목록 카드를 지시문·새문서에 잇기('26-09-30 주관 판정) ─────────────────────────
# 카드는 build/imageasset.py 가 받은 자료에서 꺼내 만든다(_그림/목록.json, 세션 방 안). 정책(자리·넣는 때·상한)은
# build/genres.py 그림정책 한 곳. 모델은 "그림":"img-…" id 만 쓰고, 경로·좌표는 시스템이 푼다.
def _그림카드들(key=None, 전부=False):
    """이 대화·이 문서의 받은 자료 그림 카드(_그림범위) — 못 만들면 [](지시문·새문서가 막히지 않게, 까닭은 stderr).
    전부=True 는 거르지 않는다 — id 가 실제로 있는지 볼 때만(새문서 정리·내보내기 경고). 목록에 싣는 데는 쓰지 않는다."""
    try:
        return 자료뿌리.모듈("imageasset").카드들(파일들=None if 전부 else _그림범위(key))
    except Exception as e:
        print(f"[그림] 목록 오류(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
        return []


# 카드는 이 문서(세션)에 올린 자료의 그림만('26-09-30 주관 판정, review_impl2 M6①). 플러그인(stdio·CLI)은 세션 열쇠가 없어
# 받은 자료 폴더 하나를 모든 대화가 같이 쓴다 — 전에는 지난주 다른 과제의 첨부 사진이 새 초안의 후보·편집기 서랍에 떴다.
#   · 세션 열쇠가 있으면(웹앱·공유 연결) 방이 곧 그 세션이다 — 거르지 않는다.
#   · MCP stdio: 이 대화(대화 칸 — 작업방식과 같은 칸, 무활동 2시간이면 잊음)에서 올리기·파일읽기 한 파일.
#   · CLI: 대화를 모른다(작업방식과 같은 판단) — 이 호출의 문서에 묶인 자료만. 파일읽기 응답의 '그림' 칸이 그 파일의 카드다.
#   · 문서 key 가 있으면 그 문서에 묶인 자료(imageasset.문서자료 — 새문서·저장 때 적는다)를 더한다.
def _그림범위(key=None):
    """카드를 실을 받은 자료 파일 이름 모음 — None 이면 거르지 않는다. 로컬 편집기 서버(serve.py 단일세션 — 웹앱 표지가
    서지만 플러그인의 공유 뿌리다)는 거른다."""
    if os.environ.get("문서지능_웹앱") and not os.environ.get("문서지능_단일세션"):
        return None
    try:
        if 자료뿌리.세션열쇠():
            return None
    except Exception:
        return set()
    파일 = set(_대화그림파일())
    if key:
        try:
            파일 |= set(자료뿌리.모듈("imageasset").문서자료(str(key)))
        except Exception as e:
            print(f"[그림] 문서 자료 읽기 오류(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    return 파일


def _대화그림파일():
    if _CLI표면():
        return []
    return list(_대화칸().get("그림파일") or [])


def _대화그림적기(이름):
    """이 대화에서 올리거나 읽은 받은 자료 파일 — 카드 범위에 든다(MCP 대화 칸, CLI·공유 연결은 적지 않는다)."""
    if not 이름 or _CLI표면() or os.environ.get("문서지능_웹앱"):
        return
    칸 = _대화칸()
    if 칸.get("공유"):
        return
    칸.setdefault("그림파일", [])
    if 이름 not in 칸["그림파일"]:
        칸["그림파일"].append(이름)


def _자료파일풀기(자료파일):
    """자료파일 인자(이름·경로 목록, 또는 줄마다 하나인 글) → 받은 자료 폴더의 파일 이름들, 못 찾은 것('26-10-01 주관 판정 S3).
    경로를 주면 파일 이름만 본다(받은 자료 폴더 밖은 받지 않는다). 이름은 유니코드 정규화(NFC)로 맞댄다."""
    import unicodedata
    if not 자료파일:
        return [], []
    값들 = 자료파일 if isinstance(자료파일, (list, tuple)) else str(자료파일).splitlines()
    try:
        받은 = {unicodedata.normalize("NFC", f): f for f in 자료뿌리.모듈("imageasset")._받은파일들()}
    except Exception:
        받은 = {}
    찾음, 없음 = [], []
    for x in 값들:
        이름 = os.path.basename(str(x or "").strip().rstrip("/"))
        if not 이름:
            continue
        f = 받은.get(unicodedata.normalize("NFC", 이름))
        if f:
            if f not in 찾음:
                찾음.append(f)
        elif 이름 not in 없음:
            없음.append(이름)
    return 찾음, 없음


def _그림문서묶기(키, doc=None, 원문="", 자료파일=None):
    """문서 key 에 이 대화의 자료와 문서가 쓴 그림 id 의 파일을 묶는다 — 새 대화·편집기 서버에서도 그 문서의 카드가 서게.
    자료파일(새문서·저장 인자 — 에이전트가 파일읽기로 읽은 파일 이름)을 주면 그 파일들을 묶는다('26-10-01 주관 판정 S3,
    verify_fixup7 F3 — 원문에 한 문서만 통째로 담기면 나머지 문서의 사진 줄이 빠졌다). 자료파일이 없을 때만 **원문에 본문이 든
    받은 자료**(글지문 담김 ≥ 0.7)를 묶는다('26-10-01 주관 판정 R5) — CLI 는 대화를 몰라 전에는 한글 문서가 묶이지 않아 새문서
    확인할것에 문서 속 사진 줄이 서지 않았다(verify_fixup5_ux B4). 다른 과제의 첨부는 원문에 그 본문이 들지 않으면 묶이지 않는다.
    MCP 는 대화 칸(이 대화에서 읽은 파일)도 늘 묶는다."""
    if not 키 or _그림범위() is None:
        return
    try:
        ia = 자료뿌리.모듈("imageasset")
        파일 = list(_대화그림파일())
        ids = set(re.findall(r'"그림"\s*:\s*"(img-[0-9a-f]{6,40})"', json.dumps(doc, ensure_ascii=False))) if doc else set()
        if ids:
            for c in ia.카드들(갱신=False):
                if c.get("id") in ids and c.get("파일") and c["파일"] not in 파일:
                    파일.append(c["파일"])
        준, 못 = _자료파일풀기(자료파일)
        if 못:
            print(f"[그림] 자료파일 가운데 받은 자료 폴더에 없는 이름(건너뜀): {', '.join(못[:10])}", file=sys.stderr)
        for f in 준:
            if f not in 파일:
                파일.append(f)
        if 원문 and not 준:
            for f in ia.원문에든자료(_자료글(원문)):
                if f not in 파일:
                    파일.append(f)
        if 파일:
            ia.문서자료묶기(str(키), 파일)
    except Exception as e:
        print(f"[그림] 문서 자료 묶기 오류(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)


def _그림범위밖수(카드):
    """범위 밖이라 싣지 않은 받은 자료 수(카드 목록이 빌 때 까닭을 말하려고) — 거르지 않을 때는 0."""
    if _그림범위() is None:
        return 0
    try:
        안 = {c.get("파일") for c in 카드}
        return len([f for f in 자료뿌리.모듈("imageasset")._받은파일들() if f not in 안])
    except Exception:
        return 0


def _그림범위빈말(밖):
    """범위가 비었을 때의 한 줄(사람·에이전트) — '올린 자료에 그림이 없다'로 거짓말하지 않는다."""
    if _CLI표면():
        return ("CLI 는 대화를 기억하지 않아 그림 목록을 싣지 않습니다. 파일읽기(readfile) 응답의 '그림' 칸에 나온 id 만 "
                "쓰세요" + (f"(받은 자료 폴더의 다른 파일 {밖}개는 싣지 않습니다)" if 밖 else ""))
    return (f"이 대화에서 올리거나 읽은 자료가 없어 그림 목록이 비었습니다. 쓸 자료를 파일읽기(readfile)로 읽으면 그 자료의 "
            f"그림이 목록에 오릅니다(다른 대화에서 올린 자료 {밖}개는 싣지 않습니다)")


# 공개 전 확인('26-09-30 주관 판정 ①·⑥) — 공개 장르(보도자료·옛 판형 발표)에 올린 사진이 실리면 게시 전 확인 한 줄,
# 비밀 표지가 있는 자료의 그림이 실리면(어느 장르든) 등급 표시 확인 한 줄. 플러그인은 확인할것에, 웹앱은 내보내기 응답의
# '그림경고'(app.html 내보내기 화면)와 편집기 칩으로 — 막지는 않는다.
그림게시말 = "게시 전 확인: 얼굴·차량 번호·보안 시설"
_그림경고중 = contextvars.ContextVar("문서지능_그림경고중", default=False)   # 내보내기 바깥 호출 표시(경고를 한 번만)


def _그림등급말(표지, cid):
    return f"'{표지}' 표시가 있는 자료에서 가져온 그림({cid})입니다. 이 문서에도 같은 등급 표시를 달아야 하는지 확인해 주세요."


def _공개사진있나(doc, stem, 실):
    """공개 장르에 실린 그림 가운데 사진(올린 자료의 그림 — AI 생성 그림이 아닌 것)이 있나."""
    if not 실 or not (stem == "press" or (stem == "slides" and (doc or {}).get("판형") != "v2")):
        return False
    for p in 실:
        s = _경로값(doc, p)
        for x in (s if isinstance(s, list) else [s]):
            if not (isinstance(x, dict) and x.get("출처") == "생성"):
                return True
    return False


def _그림내보내기경고(key, doc):
    """내보내기 한 줄 경고들 — 조립된 HTML 에 실제로 실린 그림으로 판단한다(편집기에서 바꾼 사진도 여기서 다시 본다)."""
    g = 자료뿌리.모듈("genres")
    ia = 자료뿌리.모듈("imageasset")
    if not isinstance(doc, dict) or not key:
        return []
    장르 = str(doc.get("genre") or "")
    stem = 장르 if 장르 in g.표 else next((s for s, m in g.표.items() if 장르 in (m["장르"], m["키"])), 장르)
    try:
        with open(자료뿌리.산출물(str(key)), encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return []
    실 = ia.실린것들(html)
    out = []
    if _공개사진있나(doc, stem, 실):
        out.append(그림게시말)
    카드 = None
    for p in 실:
        s = _경로값(doc, p)
        for x in (s if isinstance(s, list) else [s]):
            cid = x.get("그림") if isinstance(x, dict) else (x if isinstance(x, str) else None)
            if not (isinstance(cid, str) and cid.startswith("img-")):
                continue
            카드 = _그림카드들(전부=True) if 카드 is None else 카드
            c = ia.그림찾기(cid, 카드)
            if c and c.get("비밀표지"):
                말 = _그림등급말(c["비밀표지"], cid)
                if 말 not in out:
                    out.append(말)
    return out


def _쓸그림들(카드, 정책):
    return [c for c in 카드 if c.get("쓸수있음") and not (정책.get("공개") and c.get("비밀표지"))]


def _플랜그림계획(장르, plan_id=None):
    """승인된 설계의 그림 계획 → (계획, plan_id). 계획: None(칸 없음·승인 전) | [](그림 없이) | [{그림, 절, 목적, 짝}].
    plan_id 가 없으면 이 장르로 승인됐고 아직 문서에 매이지 않은 가장 새 설계를 본다(지시문에 싣기만 한다 — 새문서
    승인 게이트는 여전히 doc.plan_id 로 따로 건다)."""
    pid = str(plan_id or "").strip() or next(iter(_미매인승인플랜(장르)), "")
    if not pid:
        return None, ""
    try:
        plan = json.load(open(자료뿌리.플랜(pid), encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None, pid
    if ((plan.get("승인") or {}).get("status") or "").strip() != "승인":
        return None, pid
    계 = plan.get("그림계획")
    if not isinstance(계, list):
        return None, pid
    정리 = []
    for x in 계:
        if isinstance(x, str) and x.strip():
            x = {"그림": x.strip()}
        if isinstance(x, dict) and isinstance(x.get("그림"), str) and x["그림"].strip():
            정리.append({k: str(x[k]).strip() for k in ("그림", "절", "목적", "짝") if x.get(k)})
    return 정리, pid


def _그림지시(장르, 약한모델=False, 판형=None, plan_id=None, 카드=None):
    """초안 지시문의 그림 줄 — 장르 정책 + 첨부 그림 카드 + 승인된 설계의 그림 계획. 강·약 같은 부품(약은 짧게)."""
    g = 자료뿌리.모듈("genres")
    ia = 자료뿌리.모듈("imageasset")
    정 = g.그림정책값(장르, 판형)
    카드 = _그림카드들() if 카드 is None else 카드
    쓸 = _쓸그림들(카드, 정)
    if not 정["자리"]:
        말 = f"· 그림: 이 문서 종류에는 그림(이미지) 자리가 없다 — {정['넣지않는때']}. \"이미지\" 키를 넣지 마라."
        if 쓸:
            말 += f" 올린 자료에 그림 {len(쓸)}장이 있어도 이 문서에는 싣지 않는다."
        return [말]
    생성 = bool(정.get("생성")) and _그림생성되나()
    # 약한 모델(서버 소형)은 같은 정책을 짧은 한 줄로(genres.그림정책 '짧게') — 순증을 줄인다(critic_impl #30)
    머리 = (f"· 그림 — {정['짧게']}. " if (약한모델 and 정.get("짧게")) else
           f"· 그림 — 넣는 때: {정['넣는때']}. 넣지 않는 때: {정['넣지않는때']}. 상한 {정['상한']}. ")
    줄 = [머리
         + ("올린 그림 중 맞는 것이 없고 상황 설명·예시가 꼭 필요할 때만 \"출처\":\"생성\"·\"프롬프트\"로 AI 생성을 "
            "요청한다(자동으로 'AI 생성물' 표기가 붙는다). 도해·차트·로고·실제 사람·기관 사진은 만들지 않는다. "
            "프롬프트에는 실명·실제 기관 이름을 쓰지 않고(○○), 그림 속 글자를 시키지 않는다."
            if 생성 else "맞는 그림이 없으면 그림 없이 쓴다(그림을 새로 만들지 않는다).")]
    # 그림 도구가 없거나 깨져 올린 사진 파일을 못 쓸 때의 사람 말('26-10-01 주관 판정 S2) — 문서 속 사진 카드가 목록을 채워도
    # 싣는다(verify_fixup7 F1: 카드가 있으면 도구 없음 줄이 가려져 사진 파일이 조용히 빠졌다)
    # ('26-10-01 주관 판정 P1) 도구는 있는데 위임 자식이 한 번 죽었으면 도구 줄이 아니라 그 파일 줄(못쓴줄들)
    # ('26-10-01 주관 판정 Q1·Q3) 위임 자식을 죽인 범인 파일·깨진 사진 파일 줄은 목록을 다 만든 뒤(카드오류 없음)에도 옮긴다
    _범위 = _그림범위()
    _도구줄 = " ".join(ia.못쓴줄들(_범위))
    # ('26-10-01 주관 판정 Q5, verify_fixup9 N1) 막연한 '첨부 그림을 쓰지 못했다'는 처리 못 한 파일도 문서에 실을 사진도 없으면
    # 내지 않는다(P2 셈과 같게 — 그림 없는 한글·글만 든 PDF 에 거짓 줄이 서지 않게)
    _알릴 = bool(_도구줄) or bool(ia.처리못한파일들(_범위)) or any(
        c.get("종류") in (ia.문서사진, "사진·삽화") or ia._사진모름(c) for c in 카드 or [])
    if 카드:
        줄.append(ia.카드글(카드, 약한=약한모델, 공개=bool(정.get("공개"))))
        if ia.카드오류():
            줄.append("· 올린 자료 가운데 그림 목록을 만들지 못한 것이 있다(" + ia.카드오류() + ") — 위 목록에 없는 그림은 넣지 "
                     + (("말고, 끝 보고에 " + (f"'{_도구줄}'라고" if _도구줄 else "'첨부 그림 일부를 쓰지 못했다'고") + " 알려라.")
                        if _알릴 else "마라."))
    elif ia.카드오류():
        # 도구가 없어 목록을 못 만든 것을 '그림이 없다'로 말하지 않는다(review_impl2 M5) — 사람에게 알릴 까닭도 싣는다
        줄.append("· 올린 자료의 그림 목록을 만들지 못했다(" + ia.카드오류() + ") — 이번 초안에는 \"이미지\" 키를 넣지 "
                 + (("말고, 끝 보고에 " + (f"'{_도구줄}'라고" if _도구줄 else "'첨부 그림을 쓰지 못했다'고") + " 알려라.")
                    if _알릴 else "마라."))
    elif _CLI표면() and _그림범위() is not None:
        # CLI 는 대화를 모른다(카드 범위 — _그림범위) — 목록 대신 파일읽기 응답의 카드 id 를 쓰게 한다
        줄.append("· 그림 목록: CLI 는 대화를 기억하지 않아 싣지 않는다 — 파일읽기(readfile) 응답의 '그림' 칸에 나온 id 만 "
                 "\"그림\"에 쓴다. 그 밖에는 " + ("위 생성 조건이 아니면 " if 생성 else "") + "\"이미지\" 키를 넣지 마라.")
    else:
        줄.append("· 올린 자료에 그림이 없다 — " + ("위 생성 조건이 아니면 " if 생성 else "") + "\"이미지\" 키를 넣지 마라.")
    if _도구줄 and not ia.카드오류():
        # 목록은 다 만들었지만 범인 파일·깨진 사진 파일이 있다(Q1·Q3·Q7) — 그 줄을 끝 보고로
        줄.append("· 올린 자료 가운데 그림을 꺼내지 못한 파일이 있다 — 그 파일의 그림은 넣지 말고, 끝 보고에 "
                 f"'{_도구줄}'라고 알려라.")
    계, _pid = _플랜그림계획(정["등록부"], plan_id)
    if 계 is not None:
        if 계:
            줄.append("[승인된 설계의 그림 계획 — 이대로 넣는다. 넣지 못할 까닭이 있으면 그 그림은 빼라(시스템이 확인할 것에 올린다)]")
            for x in 계:
                줄.append(f"· {x['그림']} → " + (f"'{x['절']}'" if x.get("절") else "알맞은 절")
                         + (f" ({x['목적']})" if x.get("목적") else "") + (f" · 짝 {x['짝']}" if x.get("짝") else ""))
        else:
            줄.append("· 승인된 설계는 그림을 넣지 않기로 했다 — \"이미지\" 키를 넣지 마라.")
    if 정.get("모양") and (쓸 or 생성):
        줄.append(f"· 모양: {정['모양']} — \"그림\"에는 위 목록의 id 만 쓴다. 캡션은 곁 글에서 따오고, 올린 파일 "
                 "이름은 캡션·설명(출처)에 쓰지 않는다.")
    return 줄


def _설계그림지시(장르, 약한모델=False, 판형=None, 카드=None):
    """설계 지시문의 그림 줄 — 자리 있는 장르에 쓸 그림이 있을 때만 카드와 '그림계획' 칸을 싣는다."""
    g = 자료뿌리.모듈("genres")
    정 = g.그림정책값(장르, 판형)
    카드 = _그림카드들() if 카드 is None else 카드
    쓸 = _쓸그림들(카드, 정)
    if not 정["자리"]:
        return ([f"· 그림: {정['넣지않는때']} — 설계에 그림을 넣지 마라(\"그림계획\" 칸 없음)."] if 쓸 else [])
    ia = 자료뿌리.모듈("imageasset")
    if not 쓸:
        if not 카드 and ia.카드오류():
            return [f"· 그림: 올린 자료의 그림 목록을 만들지 못했다({ia.카드오류()}) — \"그림계획\"은 빈 배열 [] 로 둔다."]
        return ["· 그림: 올린 자료에 쓸 그림이 없다 — \"그림계획\"은 빈 배열 [] 로 둔다."]
    return ["",
            (f"[그림 계획 — {정['짧게']}]" if (약한모델 and 정.get("짧게")) else
             f"[그림 계획 — 넣는 때: {정['넣는때']}. 넣지 않는 때: {정['넣지않는때']}. 상한 {정['상한']}]"),
            ia.카드글(카드, 약한=약한모델, 공개=bool(정.get("공개"))),
            ("· 돌려줄 JSON 에 \"그림계획\": [{\"그림\": \"img-…\", \"절\": \"본문순서의 절·장 제목\"}] 를 더한다 — 맞는 그림이 "
             "없으면 [] (억지로 넣지 않는다)." if 약한모델 else
             "· 돌려줄 JSON 에 \"그림계획\": [{\"그림\": \"img-…\", \"절\": \"넣을 절·장(본문순서의 제목)\", \"목적\": "
             "\"현장 실태|전후 대조|예시\", \"짝\": \"img-…(전·후 쌍일 때만)\"}] 를 더한다. 목록의 id 만 쓰고, 맞는 그림이 "
             "없으면 [] 로 둔다(억지로 넣지 않는다 — 공공문서에서 엉뚱한 그림은 빠진 그림보다 해롭다).")]


def _그림이름꼴들(카드=None):
    """올린 파일 이름 꼴(정규식) 목록 — 새문서·저장·JSON 내보내기가 같은 것으로 캡션·설명에서 파일 이름을 걷는다('26-09-30 fixup3 N1).

    · 자모 조합꼴을 NFC 로 펴고(맥은 NFD 로 올린다), 확장자를 뗀 이름(5자 이상)도 찾는다(fixup, review_practice2 N9).
    · 올리기가 긴 이름을 60바이트에서 잘라 저장하면 모델은 원래 이름을 쓴다 — 잘린 앞부분만 걷혀 꼬리('사진.png')가 남았다
      (verify_fixup2 N7). 저장 이름 앞부분 + 띄어쓰기 없는 꼬리 + 같은 확장자까지 한 이름으로 본다. 잘린 이름이면 확장자 없이
      쓴 꼬리('… 1쪽' 앞)도 본다. 잘린 끝의 외톨이 자모는 뗀다."""
    import unicodedata as _ud
    if 카드 is None:
        카드 = _그림카드들(전부=True)
    받은이름들 = sorted({c.get("파일") for c in 카드 if c.get("파일")}, key=len, reverse=True)
    try:
        받은이름들 += [f for f in os.listdir(자료뿌리.받은것뿌리()) if f not in 받은이름들 and "." in f]
    except OSError:
        pass
    꼴 = []
    for 원 in 받은이름들:
        뿌리, 끝 = os.path.splitext(str(원))
        잘림 = len(뿌리.encode("utf-8")) >= 55
        n = _ud.normalize("NFC", 원)
        뿌리n = _ud.normalize("NFC", 뿌리)
        깎 = re.sub(r"[ᄀ-ᇿ㄰-㆏]+$", "", 뿌리n).rstrip()
        잘림 = 잘림 or 깎 != 뿌리n
        뿌리n = 깎
        if len(뿌리n) >= 5 and 끝:
            꼴.append((len(뿌리n) + 100, re.escape(뿌리n) + r"[^\s/\\<>\"'|]{0,40}?" + re.escape(_ud.normalize("NFC", 끝))))
        if 잘림 and len(뿌리n) >= 5:
            꼴.append((len(뿌리n) + 50, re.escape(뿌리n) + r"[^\s/\\<>\"'|()\[\]]{0,24}"))
        for v in (n, 뿌리n):
            if len(v) >= 5:
                꼴.append((len(v), re.escape(v)))
    본, out = set(), []
    for _, k in sorted(꼴, key=lambda x: -x[0]):
        if k not in 본:
            본.add(k)
            out.append(re.compile(k + r"(?:\s*\d+\s*(?:쪽|페이지|p\.?))?"))
    return out


def _그림이름빼기(글, 꼴들):
    """(고친 글, 파일 이름이 있었나) — 앞 ※ 는 늘 걷는다(풀버전 .note 가 스스로 붙인다). 로그는 이름이 있었을 때만."""
    import unicodedata as _ud
    s = _ud.normalize("NFC", str(글))
    맞음 = False
    for k in 꼴들:
        s, n = k.subn("", s)
        맞음 = 맞음 or n > 0
    if 맞음:
        s = re.sub(r"\(\s*\)|\[\s*\]", "", s)
        s = re.sub(r"[ \t]{2,}", " ", s)          # 이름이 빠진 자리의 겹 띄어쓰기
        s = re.sub(r"^[\s,·:※\-–—]+|[\s,·:\-–—]+$", "", s)
        s = re.sub(r"^(?:출처|자료)\s*[:：]?\s*$", "", s)
    else:
        s = re.sub(r"^[\s※]+", "", s).rstrip()
    return s, 맞음


def _그림글걷기(spec, 어디, 말, 꼴들):
    """그림 스펙 하나의 글 칸 정리(새문서·저장·JSON 공통) — 옛 '폭'은 숫자만, '출처'는 생성 표지만, 캡션·설명·함의·대체텍스트의
    올린 파일 이름은 뺀다. spec(dict)을 고쳐 돌려준다(빈 칸은 지운다)."""
    ia = 자료뿌리.모듈("imageasset")
    if "폭" in spec:
        # 옛 '폭'(%)은 숫자만 — 렌더도 거르지만(imageasset._옛폭) 문서 JSON 에 주입 글이 남지 않게(review_impl2 H1)
        spec = dict(spec, 폭=ia._옛폭(spec) + "%")
    if "출처" in spec and spec.get("출처") != "생성":
        # 그림의 '출처' 칸은 생성 표지 말고는 쓰지 않는다 — 모델이 올린 파일 이름('현장사진.png')을 적으면 편집 흔적으로
        # 남았다(N9). 출처를 밝힐 곳은 설명(※)이다
        spec = {k: v for k, v in spec.items() if k != "출처"}
    for k in ("캡션", "설명", "함의", "대체텍스트"):
        if isinstance(spec.get(k), str):
            새, 맞음 = _그림이름빼기(spec[k], 꼴들)
            if 맞음:
                말.append(f"{어디}.{k}: 올린 파일 이름을 글에서 뺐습니다(출처 줄에 파일 이름을 쓰지 않습니다)")
            if 새 != spec[k]:
                if 새:
                    spec[k] = 새
                else:
                    spec.pop(k, None)
    return spec


def _그림스펙걷기(doc, 고치기):
    """문서의 그림 키(genres.그림키이름, 관인 제외) 스펙마다 고치기(spec, 경로) → 새 spec 또는 None(뺌)."""
    g = 자료뿌리.모듈("genres")

    def 걷(n, 경로):
        if isinstance(n, dict):
            for k in list(n.keys()):
                v = n[k]
                p = f"{경로}.{k}" if 경로 else str(k)
                if k in g.그림키이름 and p != "관인.이미지" and v:
                    if isinstance(v, list):
                        새 = [x for x in ((고치기(x, f"{p}.{i}") if isinstance(x, dict) else x) for i, x in enumerate(v))
                             if x is not None]
                        if 새:
                            n[k] = 새
                        else:
                            del n[k]
                    elif isinstance(v, dict):
                        x = 고치기(v, p)
                        if x is None:
                            del n[k]
                        else:
                            n[k] = x
                    continue
                걷(v, p)
        elif isinstance(n, list):
            for i, v in enumerate(n):
                걷(v, f"{경로}.{i}" if 경로 else str(i))
    걷(doc, "")


def _그림저장정리(doc):
    """저장(모델 save·편집기 저장·AI 다시쓰기 — 모두 이 입구) 때 그림 스펙의 글 칸만 새문서와 같은 함수로 정리한다
    ('26-09-30 fixup3 N1: 저장 길은 대체텍스트·캡션·설명에 적은 올린 파일 이름을 그대로 냈다 — 대체텍스트는 단독 HTML alt·MD
    ![…]에 실린다). id 확인·좌표 지우기처럼 사람이 고른 것을 바꾸는 정리는 하지 않는다. 로그 줄 목록을 돌려준다."""
    if not isinstance(doc, dict):
        return []
    g = 자료뿌리.모듈("genres")
    if not g.그림키들(doc):
        return []
    말, 꼴 = [], None

    def 고치기(spec, 어디):
        nonlocal 꼴
        if 꼴 is None:
            꼴 = _그림이름꼴들()
        return _그림글걷기(spec, 어디, 말, 꼴)
    _그림스펙걷기(doc, 고치기)
    return 말


def _그림json사본(doc, key):
    """JSON 내보내기 사본 — 조립 HTML 에 실리지 않은(data-miss) 그림 스펙을 빼고, 남은 스펙의 글 칸을 새문서와 같이 정리한다
    ('26-09-30 fixup3 N8: 못 실은 그림 스펙의 파일 이름·캡션과 주입 글이 문서 그대로 나갔다). 등록부의 문서는 그대로 둔다."""
    import copy as _copy
    g = 자료뿌리.모듈("genres")
    if not isinstance(doc, dict) or not g.그림키들(doc):
        return doc
    사본 = _copy.deepcopy(_그림빠진doc(doc, str(key)))     # 못 실은 그림(data-miss 자리)을 뺀 사본 — MD 와 같은 길
    꼴 = _그림이름꼴들()
    말 = []
    # 실린 옛 꼴 스펙의 '파일'(올린 파일 이름·세션 build/ 경로)도 걷는다('26-10-01 주관 판정 R6, verify_fixup5 N3) — 못 실은 것을
    # 빼는 규칙의 짝. 그림은 id("그림")와 캡션·설명으로 남는다
    _그림스펙걷기(사본, lambda spec, 어디: {k: v for k, v in _그림글걷기(spec, 어디, 말, 꼴).items() if k != "파일"})
    return 사본


def _그림정리(doc, 장르):
    """새문서 입구의 그림 스펙 정리('26-09-30) → (로그 줄 | None, 확인할것 [(종류, 어디, 내용)]).

    · 모양: 풀버전 절.이미지 dict → [dict], 옛 슬라이드 이미지 list → 첫 원소(전에는 조립기가 크래시했다, map_code ⑤).
    · "그림":"img-…" id — 목록에 없으면 빼고 알린다(되돌리지 않는다: 약한 모델 왕복 한 번이 비싸다, critic_impl #13).
      꺼낼 수 없는(스캔·가림) 그림도 뺀다. 로고 추정·비밀 표지(공개 장르)는 두되 확인할 것에 올린다.
    · 모델이 쓴 좌표·경로(파일·쪽·index·자를곳·크롭·dpi)는 id 가 있으면 지운다 — 경로·경계는 시스템이 푼다.
    · 옛 꼴("파일"+"쪽") — 목록에서 그 파일·쪽의 쓸 그림이 **정확히 하나**면 id 로 바꾼다(정밀도 우선, 아니면 그대로).
    · 캡션·설명에 올린 파일 이름을 쓰지 않는다(파일 이름에 '내부'·'비공개'가 있을 수 있다, critic_practice §3).
    · 승인된 설계의 그림 계획에 있는데 초안에 없는 그림 → 확인할 것(강제로 넣지 않는다 — 편집기 왕복과 부딪친다)."""
    g = 자료뿌리.모듈("genres")
    ia = 자료뿌리.모듈("imageasset")
    stem = 장르 if 장르 in g.표 else next((s for s, m in g.표.items() if 장르 in (m["장르"], m["키"])), 장르)
    정 = g.그림정책값(stem, "v2" if (isinstance(doc, dict) and doc.get("판형") == "v2") else None)
    키들 = g.그림키들(doc) if isinstance(doc, dict) else []
    계, _pid = (_플랜그림계획(stem, doc.get("plan_id")) if isinstance(doc, dict) and doc.get("plan_id")
               else (None, ""))
    if not 키들 and not 계:
        return None, []
    # id 가 실제로 있는지는 받은 자료 전부로 본다 — 목록에 싣는 범위(_그림범위)로 좁히면 CLI·새 대화가 파일읽기 응답에서
    # 받은 id·앞 대화에 만든 문서의 id 를 '목록에 없다'며 뺀다. id 는 내용 해시라 보지 않은 그림을 맞힐 수 없다.
    카드 = _그림카드들(전부=True)
    표 = {c["id"]: c for c in 카드 if c.get("id")}
    말, 항목, 쓴 = [], [], []
    _좌표키 = ("파일", "쪽", "index", "자를곳", "크롭", "dpi")
    # 올린 파일 이름 꼴 — 저장·JSON 내보내기와 같은 함수(_그림이름꼴들, fixup3 N1·N7)
    _이름꼴 = _그림이름꼴들(카드)

    def 고치기(spec, 어디):
        """spec 하나 → 남길 spec(dict) 또는 None(뺌)."""
        if isinstance(spec, str) and re.fullmatch(r"img-[0-9a-f]{6,40}", spec.strip()):
            spec = {"그림": spec.strip()}
        if not isinstance(spec, dict):
            return spec
        if spec.get("출처") == "생성":
            # 생성 그림은 정책이 허락한 장르(옛 판형 슬라이드)에만('26-09-30 주관 판정 — 풀버전·보도자료의 사진은 증빙으로
            # 읽힌다). 자리 없는 장르는 _그림살피기 의 '자리 없음' 알림이 맡는다. P2: 전에는 지시문만 막고 조립기는 실었다.
            if 정.get("자리") and not 정.get("생성"):
                말.append(f"{어디}: 이 문서 종류에는 생성 그림을 싣지 않아 뺐습니다")
                항목.append(("그림", 어디, "생성 그림을 뺐습니다 — 이 문서에는 올린 사진만 씁니다(사진은 증빙으로 "
                                        "읽힙니다). 필요한 사진이 있으면 올려 주세요"))
                return None
            return spec
        if not spec.get("그림") and spec.get("파일") and 카드:
            후 = []
            for c in 카드:
                if not c.get("쓸수있음") or not c.get("id"):
                    continue
                if c.get("파일") not in ia._이름후보(os.path.basename(str(spec["파일"]))):
                    continue
                쪽 = (c.get("자리") or {}).get("쪽")
                if spec.get("쪽") is not None and 쪽 is not None and str(spec.get("쪽")) != str(쪽):
                    continue
                후.append(c)
            if len(후) == 1:
                spec = dict(spec, 그림=후[0]["id"])
                말.append(f"{어디}: 옛 꼴(파일·쪽) 그림을 목록 id {후[0]['id']} 로 바꿨습니다")
        if spec.get("그림"):
            cid = str(spec["그림"]).strip()
            c = 표.get(cid)
            if not c:
                말.append(f"{어디}: 목록에 없는 그림 '{cid[:20]}' 을 뺐습니다")
                항목.append(("그림", 어디, f"올린 자료 그림 목록에 없는 그림(id '{cid[:20]}')이라 뺐습니다 — 필요하면 편집기에서 넣어 주세요"))
                return None
            지운 = [k for k in _좌표키 if k in spec]
            if 지운:
                spec = {k: v for k, v in spec.items() if k not in _좌표키}
                말.append(f"{어디}: 그림 id 가 있어 모델이 쓴 경로·좌표({'·'.join(지운)})를 지웠습니다(시스템이 풉니다)")
            spec["그림"] = cid
            if c.get("종류") == "로고 추정":
                항목.append(("그림", 어디, f"로고로 보이는 그림({cid})을 넣었습니다 — 본문 그림이 맞는지 보세요"))
            elif not c.get("쓸수있음"):
                # 목록이 '쓰지 않음'으로 둔 그림(글·선 그림 등) — 빼지 않고 사람이 보게 한다(편집기 서랍에서는 사람이 고를 수 있다)
                항목.append(("그림", 어디, f"쓰지 않기로 분류된 그림({cid}, {c.get('까닭') or c.get('종류')})이 들어갔습니다. 맞는지 확인해 주세요."))
            if 정.get("공개") and c.get("비밀표지"):
                항목.append(("그림", 어디, f"비밀 표지('{c['비밀표지']}')가 있는 파일의 그림({cid})입니다 — 공개 문서에 실어도 되는지 확인하세요"))
            elif c.get("비밀표지"):
                # 내부 장르도 알린다 — 새 문서는 원 자료의 등급 표시를 달지 않아 옮겨 싣는 순간 등급이 내려간다(N11①)
                항목.append(("그림", 어디, _그림등급말(c["비밀표지"], cid)))
            if cid in 쓴 or any(x in 쓴 for x in (c.get("같은그림") or [])):
                항목.append(("그림", 어디, f"같은 그림({cid})을 두 번 넣었습니다 — 하나를 빼는 게 맞는지 보세요"))
            쓴.append(cid)
        # 폭·출처·캡션류의 올린 파일 이름 — 저장·JSON 내보내기와 같은 함수(fixup3 N1)
        return _그림글걷기(spec, 어디, 말, _이름꼴)

    def 걷(n, 경로):
        if isinstance(n, dict):
            for k in list(n.keys()):
                v = n[k]
                p = f"{경로}.{k}" if 경로 else str(k)
                if k in g.그림키이름 and p != "관인.이미지" and v:
                    if (stem == "fullreport" or k == "붙임사진") and isinstance(v, dict):
                        v = [v]
                        말.append(f"{p}: 그림 하나(객체)를 목록 [ ] 로 감쌌습니다")
                    if k == "붙임사진" and isinstance(v, list):
                        _생 = [x for x in v if isinstance(x, dict) and x.get("출처") == "생성"]
                        if _생:
                            v = [x for x in v if x not in _생]
                            말.append(f"{p}: 붙임 사진에는 생성 그림을 싣지 않아 {len(_생)}장을 뺐습니다")
                            항목.append(("그림", p, f"생성 그림 {len(_생)}장을 뺐습니다 — 보도자료 붙임 사진은 올린 사진만 씁니다"))
                    if stem == "slides" and isinstance(v, list):
                        if len(v) > 1:
                            말.append(f"{p}: 한 장에는 그림 하나 — 첫 그림만 남겼습니다")
                        v = v[0] if v else None
                    if isinstance(v, list):
                        새 = [x for x in (고치기(x, f"{p}.{i}") for i, x in enumerate(v)) if x is not None]
                        if 새:
                            n[k] = 새
                        else:
                            del n[k]
                    else:
                        x = 고치기(v, p)
                        if x is None:
                            del n[k]
                        else:
                            n[k] = x
                    continue
                걷(v, p)
        elif isinstance(n, list):
            for i, v in enumerate(n):
                걷(v, f"{경로}.{i}" if 경로 else str(i))

    if 키들:
        걷(doc, "")
    if 계:
        빠진 = [x for x in 계 if x["그림"] not in 쓴]
        for x in 빠진:
            c = 표.get(x["그림"])
            항목.append(("그림", x.get("절") or "",
                       f"설계에서 계획한 그림 {x['그림']}" + (f"({_자리말(c)})" if c else "")
                       + (f"이 '{x['절']}' 절" if x.get("절") else "이") + " 초안에 없습니다 — 넣을지 보세요"))
        if 빠진:
            말.append(f"설계의 그림 계획 {len(계)}장 중 {len(빠진)}장이 초안에 없습니다(확인할 것에 올렸습니다)")
    # 상한(가설) — 막지 않고 알린다(genres.그림정책 '상한수', review_practice2 §2-7: 주석과 달리 알림 코드가 없었다)
    for 어디, n, 한 in g.그림상한넘침(stem, doc):
        항목.append(("그림", 어디, f"그림이 {n}장으로, 이 문서 종류의 권장 상한({한}장)보다 많습니다. 줄일지 검토해 주세요."))
    줄 = ("그림 정리: " + "; ".join(말[:8]) + (f" 외 {len(말) - 8}건" if len(말) > 8 else "")) if 말 else None
    return 줄, 항목


def _자리말(c):
    return 자료뿌리.모듈("imageasset")._자리말(c) if c else ""


def _경로값(doc, 경로):
    """'장.0.절.1.이미지.0' 같은 점 경로의 값 — 없으면 None."""
    n = doc
    for 조각 in str(경로 or "").split("."):
        if isinstance(n, list) and 조각.isdigit() and int(조각) < len(n):
            n = n[int(조각)]
        elif isinstance(n, dict) and 조각 in n:
            n = n[조각]
        else:
            return None
    return n


def _그림빠진doc(doc, 키):
    """MD 처럼 문서 JSON 으로 짓는 산출물에 못 얻은 그림의 캡션만 남지 않게('26-09-30 주관 판정) — 조립된 HTML
    의 표식(data-miss)이 가리키는 그림을 뺀 사본. HTML·PDF·HWPX·PPTX 는 표식이 자리를 차지하지 않아 따로 뺄 게 없다.
    못 읽으면 그대로 돌려준다(MD 가 막히지 않게)."""
    try:
        with open(자료뿌리.산출물(키), encoding="utf-8") as f:
            미 = [p for p, _ in 자료뿌리.모듈("imageasset").미확보들(f.read()) if p]
    except Exception:
        return doc
    if not 미:
        return doc
    사본 = json.loads(json.dumps(doc, ensure_ascii=False))
    _그림빼기(사본, 미)
    return 사본


def _그림빼기(사본, 미):
    """사본에서 data-path 목록 미 가 가리키는 그림을 제자리에서 뺀다."""
    # 같은 목록의 뒤 원소부터 지운다(앞을 지우면 뒤 번호가 당겨진다)
    def 열쇠(p):
        조각 = p.split(".")
        return [(0, int(x)) if x.isdigit() else (1, x) for x in 조각]
    for p in sorted(미, key=열쇠, reverse=True):
        부모길, _, 끝 = p.rpartition(".")
        부모 = _경로값(사본, 부모길) if 부모길 else 사본
        if isinstance(부모, list) and 끝.isdigit() and int(끝) < len(부모):
            del 부모[int(끝)]
        elif isinstance(부모, dict) and 끝 in 부모:
            del 부모[끝]
    return 사본


def _md그림(doc, 키, 낼곳):
    """MD 내보내기 몫(P3 '26-09-30, design §8) — (못 얻은 그림을 뺀 사본, {id(그림 스펙): 링크} 또는 None).

    링크는 조립된 HTML 에 **실제로 실린** 그림만 준다(tomd 는 링크 없는 그림을 캡션째 뺀다 — 없는 그림의 캡션만
    남지 않게). 웹앱·편집기 서버(문서지능_웹앱 — 한 장만 내려받는다)는 data: 로 박고, 그 밖(플러그인 MCP·CLI·
    라이브러리 — 파일이 디스크에 남는다)은 MD 옆 자산으로 가는 상대 경로다. 못 읽으면 (옛 방식 사본, None) — tomd 가
    캡션만 글로 남긴다."""
    ia = 자료뿌리.모듈("imageasset")
    try:
        with open(자료뿌리.산출물(키), encoding="utf-8") as f:
            htm = f.read()
    except Exception:
        return _그림빠진doc(doc, 키), None
    사본 = json.loads(json.dumps(doc, ensure_ascii=False))
    기준, 플 = 자료뿌리.산출물뿌리(), not os.environ.get("문서지능_웹앱")
    링크 = {}
    for p, src, gen in ia.실린그림들(htm):
        obj = _경로값(사본, p) if p else None
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            obj = obj[0]          # 옛 슬라이드 '이미지' 목록 — 조립기는 첫 원소를 그린다
        if not isinstance(obj, dict):
            continue
        if src.startswith("data:"):
            링크[id(obj)] = src
            continue
        실물 = os.path.normpath(os.path.join(기준, src))
        if not ia._안전한그림길(실물):
            continue
        if 플:
            링크[id(obj)] = os.path.relpath(실물, 낼곳).replace(os.sep, "/")
        else:
            uri = ia.데이터URI(실물, 생성=bool(gen))
            if uri:
                링크[id(obj)] = uri
    _그림빼기(사본, [p for p, _ in ia.미확보들(htm) if p])
    return 사본, 링크


def _그림살피기(doc, 장르, 키):
    """그림 상태를 사람 말로('26-09-30 주관 판정) — (새문서 로그 한 줄 | None, 확인할것 [(종류, 어디, 내용)]).

    자리(genres.그림자리) 밖에 온 그림 키는 조립기가 그리지 않는다 — 전에는 1p·시행문·보도자료에 넣은 그림이
    오류도 로그도 없이 사라졌다(r2/img map_code ⑤). 못 얻은 그림은 산출물에 자리를 차지하지 않는 표식만 남는다
    (imageasset.render) — 그 까닭(data-miss)을 여기서 사람 말로 옮긴다. 판단은 **조립된 HTML** 로 한다: 조립기가
    실제로 그린 자리(data-path)와 문서 JSON 의 그림 키를 맞대면 장르·레이아웃 별칭 규칙을 베끼지 않아도 된다."""
    g = 자료뿌리.모듈("genres")
    ia = 자료뿌리.모듈("imageasset")
    키들 = g.그림키들(doc) if isinstance(doc, dict) else []
    # 쓰지 않은 한글·워드 문서 속 사진('26-09-30 주관 판정 P2) — 그림 키가 없어도(설계가 그림을 빼도) 사용자가 알아야 한다
    문사 = _문서사진항목(doc, 장르, 키) if 키 else []
    if not 키들 or not 키:
        return (("그림: " + " ".join(x[2] for x in 문사)) if 문사 else None), 문사
    stem = 장르 if 장르 in g.표 else next((s for s, m in g.표.items() if 장르 in (m["장르"], m["키"])), 장르)
    try:
        with open(자료뿌리.산출물(키), encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return None, 문사        # 산출물이 없으면(조립 전·실패) 셀 수 없다
    미 = ia.미확보들(html)
    실 = ia.실린것들(html)
    그린 = set(실) | {p for p, _ in 미}
    자리밖 = [p for p in 키들 if p not in 그린]
    말 = g.그림말.get(stem, "이 자리에는 그림을 그리지 않습니다")
    항목 = []
    _판형 = "v2" if doc.get("판형") == "v2" else None
    생성뺌 = [p for p in 자리밖 if isinstance(_경로값(doc, p), dict) and not ia.싣는가(_경로값(doc, p), stem, _판형)]
    자리밖 = [p for p in 자리밖 if p not in 생성뺌]
    for p in 생성뺌:
        # 저장(save)·편집기로 들어온 생성 그림 — 조립기가 장르 정책으로 뺐다(H2). 조용히 버리지 않고 알린다
        항목.append(("그림", p, "이 문서에는 AI로 만든 그림을 싣지 않습니다(사진은 증빙으로 읽히기 때문입니다). 올린 사진으로 바꾸거나 이 자리를 지워 주세요."))
    for p in 자리밖:
        항목.append(("그림", p, f"그림을 넣을 자리가 아니라 문서에 싣지 않았습니다 — {말}"))
    for p, 까 in 미:
        항목.append(("그림", p, "그림을 싣지 못했습니다 — " + ia.미확보말.get(까, "까닭을 모릅니다")
                    + ". 산출물에는 빈 자리 없이 빠지고 편집기에서만 표지로 보입니다"))
    for p in 실:
        spec = _경로값(doc, p)
        if isinstance(spec, dict) and spec.get("출처") == "생성":
            항목.append(("AI 그림", p, "AI로 만든 그림입니다(문서에 'AI 생성물'로 표시). 내용이 맞는지 확인해 주세요."))
    # 공개 장르(보도자료·옛 판형 슬라이드)에 사진이 실렸을 때만 — 사진 속 사람·번호판·보안 시설은 사람이 본다('26-09-30
    # 주관 판정 ⑥). AI 생성 그림은 사진이 아니다(위 'AI 그림' 줄이 따로 선다).
    if _공개사진있나(doc, stem, 실):
        항목.append(("그림", "", 그림게시말))
    항목 += 문사
    요 = [f"{이름} {n}" for 이름, n in (("실음", len(실)), ("못 실음", len(미)), ("자리 없음", len(자리밖)),
                                        ("생성 그림 뺌", len(생성뺌))) if n]
    줄 = "그림: " + " · ".join(요)
    if 자리밖:
        줄 += f" — {말}: " + ", ".join(자리밖[:6]) + (f" 외 {len(자리밖) - 6}곳" if len(자리밖) > 6 else "")
    if 미:
        줄 += (" — 못 실은 까닭: " + "; ".join(ia.미확보말.get(k, k) for k in sorted({k for _, k in 미}))
              + ". 산출물(PDF·HWPX·PPTX·MD)에는 빈 자리 없이 빠지고, 편집기에서만 검토 표지로 보입니다")
        if any(k == "대기" for _, k in 미) and not os.environ.get("문서지능_웹앱"):
            # 그림을 그릴 에이전트에게 — 요청(id·프롬프트·크기·저장 경로)은 응답의 '그림대기' 칸·이미지대기(imagequeue)
            줄 += (" — 그릴 그림은 아래 '그림 대기' 목록(응답의 그림대기 칸, 이미지대기 imagequeue)에 있습니다. 그린 파일을 "
                  "이미지채움(imagefill)에 넘기면 시스템이 검사·복사하고 이 문서를 다시 조립합니다")
    if 문사:
        줄 = (줄 + " — " if 요 else "그림: ") + " ".join(x[2] for x in 문사)
    return 줄, 항목


def _문서사진항목(doc, 장르, 키):
    """쓰지 않은 한글·워드 문서 속 사진 한 줄('26-09-30 주관 판정 P2) — [("그림", "", 말)] 또는 [].

    한글·워드 문서(HWP·HWPX·DOCX) 속 그림은 꺼내 쓰지 않는다(imageasset P1) — 사용자가 사진을 넣어 달라고 해도 조용히 빠졌다
    (verify_fixup3_ux U1: 확인할것 0·끝 보고 0). 이 문서의 그림 범위(_그림범위 — 이 대화·이 문서의 자료)에 그런 카드가 있으면
    **장르와 상관없이** 한 줄('26-09-30 주관 판정 Q4, verify_fixup4_ux V3) — 그림 자리 없는 장르(1p·시행문·규정·판형 v2)는
    '이 문서 종류에는 사진을 넣는 자리가 없어…'. 자리 있는 장르는 ('26-10-01 주관 판정 S1 — 빼지 않는다) (가) 문서 N개·사진 M장
    한 줄 + (나) 짝 PDF 에서 찾은 사진 한 줄(이 문서에 그 PDF 의 그림이 실렸으면 없음), 그림 도구가 없거나 깨져 올린 사진 파일을 못
    쓰면(S2) 도구 한 줄 — 줄마다 한 항목. 글은 imageasset.확인줄들 한 곳에서 짓는다('26-10-01 주관 판정 P1~P5 — 위임 자식이
    한 번 죽으면 도구 줄이 아니라 그 파일 줄, 자리 없는 장르에 사진 파일만 올려도 한 줄, 편집기 서랍도 같은 인자)."""
    try:
        g = 자료뿌리.모듈("genres")
        ia = 자료뿌리.모듈("imageasset")
        판형 = "v2" if isinstance(doc, dict) and doc.get("판형") == "v2" else None
        자리 = bool(g.그림정책값(장르, 판형).get("자리"))
        카드 = _그림카드들(키)
        범위 = _그림범위(키)
        범위 = ia._받은파일들() if 범위 is None else 범위
        실린 = set(re.findall(r'"그림"\s*:\s*"(img-[0-9a-f]{6,40})"', json.dumps(doc, ensure_ascii=False))) \
            if isinstance(doc, dict) else set()
        # ('26-10-01 주관 판정 P1~P5) 편집기 서랍(render_editor_any)과 같은 인자·같은 글 — imageasset.확인줄들 한 곳에서 짓는다
        줄들 = ia.확인줄들(카드, 자리=자리, 실린=실린, 범위=범위)
        return [("그림", "", x) for x in 줄들]
    except Exception as e:
        print(f"[그림] 문서 속 사진 알림 오류(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
        return []


# ── 그림 생성 대기 목록(P2, '26-09-30) ────────────────────────────────────────────
# 판단은 조립된 HTML 로 한다(_그림살피기 와 같은 결): 생성 자리(data-gen)마다 요청 id 가 있고, 표식이 '대기'면 아직
# 채우지 않은 것이다. 요청의 프롬프트·크기는 manifest(요청 목록)에서, 저장 경로는 세션 자산 폴더의 절대 경로로 푼다 —
# 플러그인 자료뿌리는 에이전트 작업 폴더 밖이라 상대 경로로는 찾지 못한다(map_agents E3). 웹앱에는 싣지 않는다.
def _경로보임():
    """절대 경로를 응답에 실어도 되나 — 웹앱·공유 연결(남의 서버 경로)은 아니다."""
    return not os.environ.get("문서지능_웹앱") and not _공유연결()


def _그림대기들(키들=None):
    """[{id, 문서, 자리, 상태, 크기, 프롬프트, 저장경로}] — 키들이 없으면 세션의 모든 문서."""
    if os.environ.get("문서지능_웹앱"):
        return []
    ia = 자료뿌리.모듈("imageasset")
    요 = ia.요청들()
    if 키들 is None:
        키들 = []
        for 등 in 등록부들():
            try:
                키들 += [d.get("filename") for d in json.load(open(등, encoding="utf-8")) if isinstance(d, dict)]
            except (OSError, ValueError):
                pass
    out, 본것 = [], set()
    for 키 in [k for k in 키들 if k]:
        try:
            with open(자료뿌리.산출물(str(키)), encoding="utf-8") as f:
                html = f.read()
        except OSError:
            continue
        for 자리, rid, 까닭 in ia.생성자리들(html):
            if 까닭 != "대기" or (키, rid, 자리) in 본것:
                continue
            본것.add((키, rid, 자리))
            e = 요.get(rid) or {}
            항 = {"id": rid, "문서": 키, "자리": 자리, "상태": e.get("상태") or "대기", "크기": e.get("크기") or "",
                 "프롬프트": e.get("프롬프트") or ""}
            # 저장 경로는 싣지 않는다('26-09-30 fixup, review_impl2 H3③) — 그 자리에 바로 놓은 파일은 채움 검사를 건너뛰었다.
            # 이제 바로 놓은 파일은 쓰지 않으므로(imageasset.generate) 경로를 줄 까닭도 없다. 채움은 이미지채움 하나다.
            out.append(항)
    return out


def _그림대기글(대기):
    """대기 목록 → 로그 블록(사람·에이전트가 읽는 줄)."""
    if not 대기:
        return ""
    ids = []
    for x in 대기:
        if x["id"] not in ids:
            ids.append(x["id"])
    줄 = [f"▸ 그림 대기 {len(ids)}건 — 그리기 전에 이 대화에서 사용자에게 한 줄로 물어 보세요(이용 한도를 쓰고, 그림 설명이 "
         "이미지 도구의 제공자로 갑니다). 좋다고 하면 한 장씩 그려 이미지채움(imagefill)에 id·tool(이미지 도구 이름)·"
         "path(그린 파일)를 넘기세요(경로가 없으면 content_base64). 올린 사진은 넣지 않습니다. 풀버전·보도자료에는 생성 "
         "그림을 넣지 않습니다"]
    for rid in ids:
        x = next(v for v in 대기 if v["id"] == rid)
        자리 = ", ".join(sorted({f"{v['문서']}:{v['자리']}" for v in 대기 if v["id"] == rid}))
        줄.append(f"  · {rid} [{x['상태']}] {x['크기']} ({자리})"
                 + f"\n    프롬프트: {x['프롬프트'][:400]}")
    return "\n".join(줄)


# _맥락·_요청 은 웹앱이 문서에 심은 자료(편집기 AI 재작성의 배경)다 — 문서 글이 아니다(X2: 자료 속 ○○가 빈칸으로 올랐다)
_확인할것_메타 = frozenset({"filename", "plan_id", "genre", "_수정시각", "purpose_type", "스타일", "레이아웃", "_맥락", "_요청"})


# 빈칸 꼴 — ○(U+25CB)만 세면 모양이 같은 〇(U+3007)·'(미정)'·'추후 확정'·'TBD'가 빠졌다(verify2 §2-B, fixup3 E).
# fixup4(주관 ⑥, verify3 §3: 심은 자리표시·미결 표현 26개 중 목록에 오른 것 0) — 자리표시 **토큰**(OOO·XXXX·YYYY. MM. DD.·
# 00. 00.·0,000·02-000-0000·N곳·제N조·??·(?)·___·{…}·[… 파일명] …)은 build/지어냈나.py 자리표시_글 한 곳을 쓰고(지어냈나도
# 같은 꼴을 가리고 읽는다), 여기에는 **미결 말**(미정·추후 안내·별도 통보·협의 중·검토 중·잠정·가칭·(작성 필요)·예시 이름
# 홍길동)만 더한다.
_빈칸말 = (r"(?<![가-힣])미정(?:이다|입니다|임|이며|이고|인)?(?![가-힣])|\(\s*미정\s*\)"
         r"|추후\s*(?:확정|결정|안내|통보|공지|협의|작성)|별도\s*(?:통보|안내|공지|통지)"
         r"|(?<![가-힣])(?:협의|검토|조율)\s*중(?:이다|입니다|이며|이고|인|임)?(?![가-힣])"
         r"|잠정|가칭|\(\s*(?:작성|확인|기재)\s*필요\s*\)|\[\s*확인\s*필요\s*\]|홍길동")
_빈칸꼴캐시 = []


def _빈칸꼴():
    if not _빈칸꼴캐시:
        _빈칸꼴캐시.append(re.compile(자료뿌리.모듈("지어냈나").자리표시_글 + "|" + _빈칸말))
    return _빈칸꼴캐시[0]


# 값 칸 하나가 통째로 자리표시인 꼴(슬라이드 지표 값 '-'·'—'·'?') — 표 칸의 '-'(해당 없음)는 관행이라 값·목표 칸만 본다.
_빈값꼴 = frozenset({"-", "—", "–", "?", "N/A", "n/a", "TBD", "TBA", "미정"})
_빈값키 = ("값", "목표", "목표선", "수치")
# 비면 확인할 메타 칸(시행문 시행일 — verify3 H2 빈 `메타.시행일`).
_빈메타칸 = frozenset({"메타.시행일"})
# 빈칸은 끝 보고 **첫머리**에 적는다(주관 ⑥) — 목록 차례의 맨 앞. 80건을 넘으면 이 차례로 남기고 끝에 '외 N건'
# (빈칸이 많은 규정 별표에서 셈한 값이 소리 없이 잘렸다 — verify2 §2-B F2).
_확인할것_차례 = ("빈칸(○○)", "지어냄 의심", "고친 곳", "지어냈나 건너뜀", "자료 일부", "어긋남", "확인 물음", "작성일 날짜", "셈한 값", "그림", "AI 그림",
              "속성거부", "자동 교정", "조립기가 채움", "경고")
_확인할것_상한 = 80
_확인할것_그림몫 = 10      # 상한을 넘을 때 그림 줄은 이만큼 먼저 남긴다('26-10-01 주관 판정 Q6)


# 사용자용 말과 에이전트용 말을 나눈다('26-09-30 주관 판정 X2) — 지어냈나.검토하기() 의 '설명'은 교정 지시(에이전트·모델용:
# '글을 빈 문자열로 보내 키를 지운다')다. 확인할것·웹앱 화면에는 무엇이 자료에 없는지와 사람이 할 일만 적는다.
def _확장사람말(g):
    종류 = str(g.get("종류") or "")
    값 = str(g.get("값") if g.get("값") is not None else "")[:40]
    설명 = str(g.get("설명") or "")
    if 종류 == "출처":
        남 = str(g.get("남길글") or "")
        if 남:
            return f"출처 '{값}'에 자료에 없는 부분이 있습니다 — 자료에 있는 '{남[:40]}'만 남겨 주세요"
        return f"자료에 없는 출처 '{값}' — 자료에 적힌 출처가 아니면 빼 주세요"
    if 종류 == "말한 사람":
        if g.get("고칠꼴") == "키지움":      # 판형 v2 인용 말한이(fixup4 G7) — 교정은 키를 지운다(요지 장으로 바꾸지 않는다)
            return f"인용한 말을 한 사람('{값}')이 자료에 없습니다 — 자료에 적힌 사람이 아니면 빼 주세요(말한 사람 없는 인용이 됩니다)"
        return f"인용한 말을 한 사람('{값}')이 자료에 없습니다 — 자료에 없는 사람이면 인용 대신 요지로 바꿔 주세요"
    if 종류 == "월표현":
        m = re.search(r"\((\d{1,2})월\)", 설명)
        return (f"자료에 없는 {m.group(1)}월이 적혀 있습니다" if m else "자료에 없는 달이 적혀 있습니다") + f" — 맞는지 봐 주세요('{값}')"
    if 종류 == "작성일자":
        return f"작성일·배포일 자리의 날짜가 자료에 없습니다 — 맞는 날짜인지 봐 주세요('{값}')"
    if 종류 == "메타칸":
        return f"분류·번호 칸의 '{값}'이 자료에 없습니다 — 맞는 값인지 봐 주세요"
    if 종류 == "붙임":
        return f"자료에 없는 붙임 '{값}' — 실제로 붙일 문서인지 봐 주세요"
    if 종류 == "인용":
        return f"자료에 없는 발언으로 보입니다 — '{값}'을 실제로 한 말인지 봐 주세요"
    if 종류 == "보도시점":
        return f"보도 시점에 자료에 없는 시각·날짜가 있습니다 — '{값}'"
    if 종류 == "부칙시행":
        m = re.search(r"자료에 없는 날짜\(([^)]+)\)", 설명)
        return (f"부칙 시행일 {m.group(1)}이 자료에 없습니다" if m else "부칙의 시행일이 자료와 다릅니다") + " — 시행일을 확인해 주세요"
    if 종류 == "술어강도":
        return f"조문의 의무·재량 표현이 자료와 다를 수 있습니다 — '{값}'"
    return f"자료와 맞는지 봐 주세요 — '{값}'"


def _출처경고사람말(글):
    """슬라이드 v2 출처 soft 경고(에이전트용 '출처 키를 지운다')를 사람 말로."""
    m = re.match(r"출처 '(.+?)' 가 자료에 없다", str(글 or ""))
    if m:
        return f"자료에 없는 출처 '{m.group(1)}' — 자료에 적힌 출처가 아니면 빼 주세요"
    m = re.match(r"출처의 '(.+?)' 은 자료에 없는 일반 말", str(글 or ""))
    if m:
        return f"출처에 자료에 없는 두루뭉술한 말('{m.group(1)}')이 있습니다 — 자료에 적힌 출처가 아니면 빼 주세요"
    return str(글 or "")


# ── 사용자용 말 · 에이전트용 말(fixup3 Z5, '26-10-01 주관 판정) ─────────────────────────────────────────────────────
# 확인할것의 '내용'은 사용자에게 그대로 보이는 말이다(웹앱 칸·플러그인 끝 보고). 조문꼴.확인할것()·슬라이드 게이트 soft·문체검사 [soft] 는
# 에이전트(모델)에게 주는 말이라 '사용자에게 확인하세요'·'○○로 비운다'·경로('장.1(카드열)')·규칙 번호가 샜다(wire_fixup2_verify §2-2·
# §3-8). 여기 한 곳(_확인할것모으기)에서 두 문구를 나눈다 — '내용'은 사용자용, '에이전트'는 원래 말(달라질 때만 싣는다).
_규정물음_사람말표 = (
    (re.compile(r"자료에 있으면 그대로 옮기고, 없으면 지어 정하지 말고 사용자에게 확인하세요"), "어떻게 정할지 알려 주세요"),
    (re.compile(r"자료에 없는 권한이면 빼거나 '○○'로 비우고 사용자에게 확인하세요"), "자료에 없는 권한이면 빼야 하는지 확인해 주세요"),
    (re.compile(r"자료에 없으면 '○○'로 비우고 사용자에게 물으세요"), "누가 맡는지 알려 주세요"),
    (re.compile(r"자료에 없으면 지어 정하지 말고\s*(?:\([^()]*\))?\s*,?\s*사용자에게 물으세요"), "어떻게 정할지 알려 주세요"),
    (re.compile(r"자료에 없으면 지어 정하지 말고\s*(?:\([^()]*\))?\s*,?\s*"), ""),
    (re.compile(r"\s*\([^()]*(?:비운다|비우고|지어 정하지)[^()]*\)"), ""),
    (re.compile(r"(?:을|를)?\s*사용자에게 물어 채우세요"), "을 알려 주세요"),
    (re.compile(r"사용자에게 확인하세요"), "확인해 주세요"),
    (re.compile(r"사용자에게 확인받으세요"), "확인해 주세요"),
    (re.compile(r"사용자에게 물으세요"), "알려 주세요"),
    (re.compile(r"사용자에게\s*"), ""),
)
_사람말_경로_RX = re.compile(r"(?<![\w.])(장|슬라이드)\.(\d+)(?:\(([^()\s]{1,12})\))?(?:\.[\w가-힣.]*)?")
_사람말_딴경로_RX = re.compile(r"(?<![\w.])(?:sections|items|본문|부칙|표지|리드|요약|붙임|메타|별첨|항목|절|html|text)"
                           r"(?:\.[\w가-힣]+)*\.\d+(?:\.[\w가-힣]+)*|\(최상위\)(?:\.[\w가-힣]+)*")
_사람말_지시끝_RX = re.compile(r"(?:라|어라|아라|해라|하라|마라|넣는다|넣어라|바꾼다|뺀다|빼라|둔다|쓴다|적는다|옮긴다|비운다|맞춘다|줄인다|"
                          r"합친다|늘린다|나눈다|고친다|채운다|올린다|내린다|정한다|붙인다|단다|않는다|한다|된다)\)?\s*[.。]?$")


def _규정물음사람말(q):
    글 = str(q or "")
    for rx, 새 in _규정물음_사람말표:
        글 = rx.sub(새, 글)
    글 = re.sub(r"—\s*알려 주세요$", "— 어떻게 정할지 알려 주세요", 글.strip())
    return re.sub(r"\s{2,}", " ", 글).strip()


def _규정줄자르기(글, 한도=200):
    """reg13f 판정 F4('26-10-01) — 확인할것 '내용'은 200자에서 잘린다(_확인할것모으기 더). 규정 물음은 끝이 물음('— 맞는지 확인해
    주세요')이라 그냥 자르면 물음이 사라졌다(verify13e 3-4: 가정 160 + 근거 100 이면 257자). 한도를 넘으면 끝의 물음 토막(마지막
    ' — ' 뒤, 60자 안)은 그대로 두고, 앞 토막을 문장 경계에서 잘라 '…'를 붙인다(연 따옴표·괄호는 닫는다). 공유 자리라 규정 줄에만 쓴다."""
    글 = str(글 or "")
    if len(글) <= 한도:
        return 글
    i = 글.rfind(" — ")
    꼬리 = 글[i:] if 0 < i and len(글) - i <= 60 else ""
    머리 = 글[:i] if 꼬리 else 글
    여유 = max(20, 한도 - len(꼬리) - 3)          # '…' + 닫는 따옴표·괄호 자리
    끝 = max((m.end() for m in re.finditer(r"[.。?!](?=\s|[\"”’)]|$)", 머리) if m.end() <= 여유), default=0)
    if 끝 < 여유 // 2:                       # 앞쪽에 문장 끝이 없으면 낱말 경계
        끝 = 머리.rfind(" ", 0, 여유)
        끝 = 끝 if 끝 > 여유 // 2 else 여유
    자른 = 머리[:끝].rstrip(" ,;·—(")

    def _닫기(s):
        return ('"' if s.count('"') % 2 else "") + ")" * max(0, s.count("(") - s.count(")"))
    나온 = 자른 + "…" + _닫기(자른) + 꼬리
    if len(나온) > 한도:
        자른 = 자른[:len(자른) - (len(나온) - 한도)].rstrip(" ,;·—(")
        나온 = 자른 + "…" + _닫기(자른) + 꼬리
    return 나온


# ── 자리 사람 말(fixup4 G3·G6, '26-10-01 주관 판정) — 경로('sections.0.items.1.html'·'장.0.절.1.항목.2.text'·'부칙.0.일자'·
# '절1 항목2')를 'N번째 절 N번째 항목' 같은 사람 말로 푼다. 예전엔 경로를 지우기만 해 '「56자」 항목 45자 초과'처럼 어느 항목인지 모르는
# 줄이 남았다(wire_fixup3_verify §2-1). app.html 검사 단계의 같은 이름 함수(자리사람말)와 같은 규칙이다(test/r33 가 두 쪽을 견준다).
_자리_순번키 = {"sections": "절", "items": "항목", "절": "절", "항목": "항목", "장": "장", "행": "행", "rows": "행", "세부": "세부 항목"}
_자리_묶음키 = {"본문": "본문", "주요내용": "주요내용", "요약": "요약", "제정이유": "제정 이유", "리드": "리드"}
_자리_번호키 = {"붙임": "붙임", "별첨": "별첨", "별표": "별표", "담당": "담당"}
_자리_끝키 = {"heading": "제목", "제목": "제목", "title": "제목", "제명": "제명", "summary": "요약", "byline": "작성 부서·날짜 줄",
            "attach": "붙임", "부제": "부제", "배포": "배포일", "일자": "일자", "호": "호수", "출처": "출처", "말한이": "말한 사람",
            "노트": "노트", "캡션": "캡션", "이름": "이름", "전화": "전화", "부서": "부서", "직위": "직위", "시행일": "시행일"}
_자리_버림키 = frozenset({"html", "text", "t", "글", "값", "칸", "머리", "메시지", "cells", "table", "표"})
_자리_경로_RX = re.compile(
    r"(?<![\w가-힣.])(?:sections|장|슬라이드|본문|부칙|주요내용|요약|붙임|별표|별첨|메타|표지|리드|담당|절|항목|제정이유)"
    r"(?:\.[\w가-힣]+)+(?:\([^()\s]{1,12}\))?|(?<![\w가-힣])절(\d+)\s*(?:제목|항목(\d+))")


def _자리사람말(어디, 장르):
    """경로 하나 → 사람 말('2번째 절 3번째 항목'). 풀 수 없으면 ''."""
    s = str(어디 or "").strip()
    if not s:
        return ""
    m = re.fullmatch(r"절(\d+)\s*(?:(제목)|항목(\d+))", s)
    if m:
        return f"{m.group(1)}번째 절 " + ("제목" if m.group(2) else f"{m.group(3)}번째 항목")
    if s in _자리_끝키:
        return _자리_끝키[s]
    유형 = ""
    m = re.match(r"^(.*?)\(([^()\s]{1,12})\)$", s)
    if m:
        s, 유형 = m.group(1), m.group(2)
    조각 = [x for x in s.split(".") if x != ""]
    꼬리 = ""
    if 조각:
        # 글 속 경로 뒤에 붙은 조사('…items.1.html의 「320」') — 영문 끝 조각의 한글 꼬리는 조사로 떼어 끝에 다시 붙인다
        m = re.fullmatch(r"([A-Za-z0-9_]+)([가-힣]{1,3})", 조각[-1])
        if m:
            조각[-1], 꼬리 = m.group(1), m.group(2)
    if 장르 == "slides" and 조각 and 조각[0] in ("장", "슬라이드") and len(조각) > 1 and 조각[1].isdigit():
        n = int(조각[1]) + (1 if 조각[0] == "장" else 2)      # 옛 판형은 표지가 1쪽이고 슬라이드.0 이 2쪽이다
        끝 = _자리_끝키.get(조각[-1], "") if 조각[-1] in ("출처", "말한이", "노트") else ""
        return f"{n}번째 장" + (f"({유형})" if 유형 else "") + (f" {끝}" if 끝 else "") + 꼬리
    말 = []
    i = 0
    while i < len(조각):
        k = 조각[i]
        다음 = 조각[i + 1] if i + 1 < len(조각) else None
        번 = int(다음) + 1 if 다음 is not None and 다음.isdigit() else None
        if k in _자리_순번키 and 번:
            말.append(f"{번}번째 {_자리_순번키[k]}")
            i += 2
            continue
        if k in _자리_묶음키:
            말.append(_자리_묶음키[k] + (f" {번}번째 항목" if 번 else ""))
            i += 2 if 번 else 1
            continue
        if k in _자리_번호키:
            말.append(_자리_번호키[k] + (f" {번}" if 번 and not (k == "담당" and 번 == 1) else ""))
            i += 2 if 번 else 1
            continue
        if k == "부칙":
            말.append("부칙")
            i += 2 if 번 else 1
            continue
        if k == "메타" or k.isdigit() or k in _자리_버림키:
            i += 1
            continue
        if k in _자리_끝키:
            말.append(_자리_끝키[k])
        elif re.search(r"[가-힣]", k):
            말.append(k)
        i += 1
    # '부칙 본문 1번째 항목' → '부칙 1번째 줄'(부칙의 본문은 줄이다)
    글 = " ".join(말)
    글 = re.sub(r"^부칙 본문 (\d+)번째 항목$", r"부칙 \1번째 줄", 글)
    return (글 + (f"({유형})" if 유형 and 글 else "") + 꼬리) if 글 else ""


def _경로사람말(글, 장르):
    """글 속 경로('장.1(카드열)'·'슬라이드.2'·'sections.0.items.1.html'·'부칙.0.일자')를 사람 말로 — 풀 수 없는 경로는 뺀다."""
    def 장말(m):
        if 장르 != "slides":
            return _자리사람말(m.group(0), 장르)
        n = int(m.group(2))
        몇 = n + 1 if m.group(1) == "장" else n + 2          # 옛 판형은 표지가 1쪽이고 슬라이드.0 이 2쪽이다
        return f"{몇}번째 장" + (f"({m.group(3)})" if m.group(3) else "")
    글 = _사람말_경로_RX.sub(장말, str(글 or ""))
    글 = _자리_경로_RX.sub(lambda m: _자리사람말(m.group(0), 장르), 글)
    글 = _사람말_딴경로_RX.sub(lambda m: _자리사람말(m.group(0), 장르), 글)
    return 글


def _경고사람말(s, 장르):
    """조립 게이트 soft·문체검사 [soft] 경고(에이전트용 지시 포함)를 사람 말로 — 문제만 남기고 '한번 봐 주세요'."""
    글 = re.sub(r"^\s*\[soft\]\s*", "", str(s or ""))
    글 = re.sub(r"^\s*W-[^\s「]+\s*", "", 글)
    글 = re.sub(r"「([^」]*)」", lambda m: "「" + (_경로사람말(m.group(1), 장르).strip() or "해당 자리") + "」", 글)
    머리, _, 꼬리 = 글.partition(" — ")
    if re.fullmatch(r"「[^」]*」", 머리.strip()) and 꼬리.strip():
        # 문체검사 꼴 '「자리」 — 무엇 — 어떻게' — 자리 뒤의 '무엇'까지가 문제다
        _무엇, _, 꼬리 = 꼬리.partition(" — ")
        머리 = 머리.strip() + " " + _무엇.strip()
    꼬리 = 꼬리.partition(" — ")[0]

    def 지시인가(문):
        return bool(_사람말_지시끝_RX.search(문) or re.search(r"(?:넣어라|바꿔라|빼라|적어라|옮겨라|고쳐라)", 문)
                    or re.search(r"(?:으면|하면|이면|없으면|있으면)\s", 문))

    # 머리는 첫 문장만 늘 남기고, 뒤 문장은 지시가 나오기 전까지만(예: '헤드가 길다. 50자 안으로 줄인다' → '헤드가 길다')
    머리문 = [x for x in re.split(r"(?<=[.。])\s+", 머리.strip()) if x]
    머리 = ". ".join([머리문[0].rstrip(".")] + [x.rstrip(".") for x in
                   __import__("itertools").takewhile(lambda x: not 지시인가(x), 머리문[1:])]) if 머리문 else ""
    남 = []
    for 문 in re.split(r"(?<=[.。])\s+", 꼬리.strip()) if 꼬리.strip() else []:
        문 = re.sub(r"\([^()]*(?:않는다|말라|마라)\)", "", 문).strip()
        if not 문 or 지시인가(문):
            break
        남.append(문.rstrip("."))
    글 = 머리.strip() + (" — " + ". ".join(남) if 남 else "")
    글 = _경로사람말(글, 장르)
    글 = re.sub(r"^\s*[:：,·]\s*", "", 글).strip()
    글 = re.sub(r"^「(\d+번째 장[^」]*)」\s+(?=\S)", r"\1 ", 글)
    m = re.match(r"^(\d+번째 장(?:\([^()]*\))?)\s+", 글)
    if m:
        글 = m.group(1) + ": " + 글[m.end():]
    return (글.rstrip(" .") + " — 한번 봐 주세요") if 글 else "슬라이드 권고가 있습니다 — 한번 봐 주세요"


def _사람말다듬기(글, 장르):
    """확인할것 '내용' 마지막 거름 — 어느 갈래에서 왔든 경로·규칙 번호·'사용자에게' 같은 에이전트 말이 남지 않게."""
    글 = str(글 or "")
    if re.search(r"사용자에게|'○○'로 비우|비운다\)|지어 정하지", 글):
        글 = _규정물음사람말(글)
    if re.search(r"\[soft\]|(?<![\w가-힣])W-[^\s]+", 글):
        글 = re.sub(r"\[soft\]\s*", "", 글)
        글 = re.sub(r"(?<![\w가-힣])W-[^\s「]+\s*", "", 글)
    if _사람말_경로_RX.search(글) or _사람말_딴경로_RX.search(글) or _자리_경로_RX.search(글):
        글 = _경로사람말(글, 장르)
        글 = re.sub(r"^\s*[:：,·]\s*", "", 글)
    글 = _에이전트말거름(글)
    return re.sub(r"\s{2,}", " ", 글).strip()


# ── 에이전트 말 안전 거름(fixup4 G3) — 문구 표(_문체경고말표·_자동교정말표)에 없는 말도 뜻만 남긴다 ──────────────────────
# 온톨로지 경로('document_types.fullreport.골격.요약_본문_중복_금지'·'shared.표기 date_day')·규칙 번호('FB-013'·'§2-2'·'R구-48')·
# 함수 이름('표기꼴.교정() 이')·영문 식별자('date_day')·반말 지시('확인하라')를 걷는다. 괄호 안에 이것들이 있으면 괄호째 걷는다.
_에이전트말_괄호_RX = re.compile(
    r"\s*[(（][^()（）]*(?:document_types|writing_profiles|data_elements|entities\.|shared\.|§|FB-\d|R[구문레진유지]\s*-|"
    r"정본|실측|사장님|판정|잠정치|[A-Za-z]+_[A-Za-z_]+|\.py\b|assemble|gate|build/|\(\))[^()（）]*[)）]")
_에이전트말_낱_RX = (
    (re.compile(r"(?:document_types|writing_profiles|data_elements|entities|shared)(?:\.[\w가-힣·\[\]]+)+(?:\s+[a-z]+_[a-z_]+)?"), ""),
    (re.compile(r"(?<![\w가-힣])(?:FB-\d+|R[구문레진유지]\s*-\s*\d+[①-⑳]?|§\s*[\d][\d\-]*)"), ""),
    (re.compile(r"[\w가-힣]+(?:\.[\w가-힣]+)*\(\)\s*(?:이|을|를|가|은|는|의)?\s*"), ""),
    (re.compile(r"(?<![\w가-힣])[\w가-힣]+\.py(?![\w가-힣])"), ""),
    (re.compile(r"(?<![A-Za-z])[a-z]+_[a-z_]+(?![A-Za-z])"), ""),
    (re.compile(r"확인하라(?=[)）\s.]|$)"), "확인해 주세요"),
    (re.compile(r"(?<=[가-힣])하라(?=[)）\s.]|$)"), "해 주세요"),
    (re.compile(r"\s*:\s*:\s*"), ": "),
    (re.compile(r"\(\s*[,·]?\s*\)|（\s*）"), ""),
)
# 따옴표 이름 뒤 괄호 덧말의 조사('부서장'(승인자)를 → '부서장'(승인자)을) — 조사는 괄호 앞 이름에 맞춘다(G6)
_괄호조사_RX = re.compile(r"'([^']{1,30})'(\([^()]{1,20}\))(을|를|은|는|이|가|과|와)(?![가-힣])")
_조사짝 = {"을": ("을", "를"), "를": ("을", "를"), "은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"), "가": ("이", "가"),
         "과": ("과", "와"), "와": ("과", "와")}


def _받침있나(글자):
    return "가" <= 글자 <= "힣" and (ord(글자) - 0xAC00) % 28 != 0


def _에이전트말거름(글):
    글 = str(글 or "")
    글 = _에이전트말_괄호_RX.sub("", 글)
    for rx, 새 in _에이전트말_낱_RX:
        글 = rx.sub(새, 글)
    글 = _괄호조사_RX.sub(lambda m: f"'{m.group(1)}'{m.group(2)}"
                     + _조사짝[m.group(3)][0 if _받침있나(m.group(1)[-1]) else 1], 글)
    return re.sub(r"\s+([,.)）])", r"\1", 글)


# ── 문구 표 한 곳(fixup4 G3, '26-10-01 주관 판정) — 규칙 id → 사용자에게 보일 말 ────────────────────────────────────────
# 문체검사 [soft] 줄은 에이전트(모델)에게 주던 말이라 온톨로지 경로·규칙 번호·반말 지시가 섞였다('「1,1550」 요약의 수치·사실이 … 생략을
# 검토하세요(document_types.fullreport.골격.요약_본문_중복_금지)'·'「56자」 항목 45자 초과 — 압축 검토(§2-2)'). 표에 있는 규칙은 표의 말로,
# 없는 규칙은 _경고사람말 + _에이전트말거름 으로 뜻만 남긴다. {n}=걸린 값의 수, {값}=걸린 값, {수}=걸린 수들('·'로 이음).
_문체경고말표 = {
    "W-길이45": "항목이 {n}자로 깁니다(45자 넘음)",
    "W-제목길이": "제목이 {n}자로 깁니다(30자 넘으면 한 줄에 안 들 수 있습니다)",
    "W-헤드길이": "머리 메시지가 {n}자로 깁니다(40자 넘음)",
    "W-헤드메시지": "머리 메시지가 주장 문장이 아니라 제목처럼 보입니다('{값}')",
    "W-요약길이": "요약이 {n}자입니다(60~80자 권장)",
    "W-요약강조": "요약에 강조 표시가 있습니다(요약에서는 강조가 빠집니다)",
    "W-요약본문중복": "요약과 본문이 같은 수치({수})를 되풀이합니다(요약·본문 중복)",
    "W-리드중복": "리드와 본문 첫 항목이 같은 수치({수})를 되풀이합니다(리드·본문 중복)",
    "W-연도표기": "연도 '{값}'은 「'{yy}년」처럼 줄여 적는 것이 관행입니다",
    "W-의연쇄": "'의'가 이어집니다('{값}')",
    "W-군더더기": "뜻이 겹치는 말이 있습니다('{값}')",
    "W-번역투의심": "번역투일 수 있는 표현이 있습니다('{값}')",
    "W-요약실질": "요약 끝맺음(보고드림·요청드림)이 문서 유형과 맞는지 봐 주세요",
    "W-표개수": "표가 {n}개입니다 — 하나로 합칠 수 있는지 봐 주세요",
    "W-항목묶음": "한 절에 ○ 항목이 많습니다('{값}')",
    "W-강조한도": "강조 표시를 {n}번 썼습니다(문서당 2번까지만 강조로 보입니다)",
    "W-delta기호": "증감 표시('{값}')에 △가 없어 강조가 빠집니다",
    "W-슬라이드검사못함": "슬라이드 권고 검사를 돌리지 못했습니다",
    "W-조문검사못함": "조문 권고 검사를 돌리지 못했습니다",
}
_문체soft_RX = re.compile(r"^\s*\[soft\]\s+(\S+)\s+「(.*?)」\s+—\s+(.*)$")


def _문체경고사람말(줄, 장르, 자리=""):
    """문체검사 [soft] 한 줄 → 사용자용 말. 자리(사람 말)를 알면 앞에 붙인다."""
    m = _문체soft_RX.match(str(줄 or ""))
    if not m:
        return _경고사람말(줄, 장르)
    규칙, 값, 말 = m.group(1), m.group(2), m.group(3)
    틀 = _문체경고말표.get(규칙)
    if 틀:
        n = (re.search(r"\d+", 값) or [""])[0] if re.search(r"\d", 값) else ""
        yy = (re.search(r"20(\d{2})", 값) or ["", ""])[1] if re.search(r"20\d{2}", 값) else ""
        수 = "·".join(x for x in 값.split(",") if x.strip())
        글 = 틀.format(n=n, 값=값, 수=수, yy=yy)
        글 = 글 if 글.endswith("주세요") else 글 + " — 한번 봐 주세요"
    else:
        # 표에 없는 규칙(규정 조문 경고 등) — 에이전트 말(경로·규칙 번호·함수 이름)을 먼저 걷고, 자리 조각(「…」)을 걸린 값으로 두고
        # 문제만 남긴다(지시 문장은 _경고사람말 이 뗀다)
        글 = _사람말다듬기(_경고사람말(f"「{값}」 — {_에이전트말거름(말)}", 장르), 장르)
    return (f"{자리}: " if 자리 else "") + 글


def _문체자리표(doc, 장르):
    """{(규칙, 걸린 값): [자리 사람 말, …]} — 문체검사 [soft] 줄이 어느 절·항목인지. 문체 게이트 판정 함수(build/stylelint.py)를
    같은 문서에 한 번 더 돌려 걸린 글 조각을 얻고, 문서글에서 그 조각이 든 자리를 찾는다. 못 찾으면 빈 표(자리 없이 싣는다)."""
    표 = {}
    try:
        린 = 자료뿌리.모듈("stylelint")
        검 = 자료뿌리.모듈("지어냈나")
        r = 린.lint_doc(doc)
        글들 = [(a, re.sub(r"\s+", " ", 린.plain(b))) for a, b in 검.문서글(doc)]
        for x in r.get("soft") or []:
            조 = str(x.get("text") or "").rstrip("…").strip()
            if not 조:
                continue
            어디 = next((a for a, b in 글들 if b.startswith(조) or (len(조) >= 12 and 조 in b)), None)
            if 어디:
                말 = _자리사람말(어디, 장르)
                if 말:
                    표.setdefault((str(x.get("rule")), str(x.get("hit"))), []).append(말)
    except Exception as e:
        print(f"[확인할것] 문체 경고 자리 찾기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    return 표


# 자동 교정·조립기가 채움 알림 — 함수 이름·모듈 이름을 사람 말로(표 한 곳). 틀은 match 뒤 그룹을 쓴다.
_자동교정말표 = (
    (re.compile(r"^표기꼴\.교정\(\) 이 (\d+)곳 고침:\s*(?::\s*)?"), r"표기를 \1곳 고쳤습니다: "),
    (re.compile(r"^표기꼴\.교정\(\) 을 불렀지만 실패\([^)]*\) — .*$"), "표기 교정을 돌리지 못해 건너뛰었습니다"),
    (re.compile(r"^조번호꼴\.맞추기\(\) 이 (\d+)곳 정정:\s*"), r"주요내용의 조 번호를 \1곳 맞췄습니다: "),
    (re.compile(r"^붙임꼴\.분리하기\(\) 이 (\d+)건을 옮겼습니다"), r"본문의 붙임 표시 \1건을 붙임으로 옮겼습니다"),
    (re.compile(r"^[\w가-힣]+\.[\w가-힣]+\(\) 이 (\d+)곳 정정:\s*"), r"\1곳을 정리했습니다: "),
    (re.compile(r"^[\w가-힣]+\.[\w가-힣]+\(\) 이 (\d+)건을 옮겼습니다"), r"\1건을 정리했습니다"),
    (re.compile(r"^[\w가-힣]+\.[\w가-힣]+\(\) 을 불렀지만 실패\([^)]*\) — .*$"), "초안 정리 하나를 돌리지 못해 건너뛰었습니다"),
    (re.compile(r"^[\w가-힣]+\.py 는 있지만 .*$"), "초안 정리 하나를 돌리지 못해 건너뛰었습니다"),
    (re.compile(r"^보도초안정리\(\) 실패\([^)]*\) — 건너뜀$"), "보도자료 초안 정리를 돌리지 못해 건너뛰었습니다"),
    (re.compile(r"^filename \"([^\"]*)\" 은 규칙\([^)]*\)에 안 맞아 \"([^\"]*)\" 로 바꿨습니다\.?$"),
     r"문서 이름 '\1'에 쓸 수 없는 글자가 있어 '\2'로 바꿨습니다"),
    (re.compile(r"^자기 호칭이 섞였습니다 (\d+)곳\(확인 필요, 고치지 않음\):\s*"), r"이 문서를 부르는 말이 섞였습니다(\1곳, 고치지 않았습니다): "),
)


def _자동교정사람말(줄, 장르):
    글 = str(줄 or "").strip()
    for rx, 새 in _자동교정말표:
        if rx.search(글):
            글 = rx.sub(새, 글, count=1)
            break
    글 = re.sub(r"(?<=: )\s*:\s*", "", 글)            # '… 2곳: : 조문의 …' — 빈 자리 이름 앞 쌍점
    글 = re.sub(r";\s*:\s*", "; ", 글)
    return _사람말다듬기(글, 장르)


def _날짜겹침빼기(목록, doc):
    """한 칸의 날짜 하나가 여러 줄(값 '9'·값 '27'·작성일 자리·작성일 날짜)로 뜨는 것을 한 줄로(fixup4 G6). 같은 자리에 날짜 줄(작성일·배포일·
    부칙 시행일·월 표현·작성일 날짜)이 있으면, 그 칸의 날짜 속 수('자료에 없는 값 'N'')와 두 번째 날짜 줄을 뺀다."""
    try:
        글표 = dict(자료뿌리.모듈("지어냈나").문서글(doc))
    except Exception:
        글표 = {}
    날짜줄 = lambda x: x.get("종류") == "작성일 날짜" or (x.get("종류") == "지어냄 의심" and re.match(
        r"(?:작성일·배포일 자리의 날짜|부칙 시행일|부칙의 시행일|자료에 없는 \d{1,2}월|자료에 없는 달)", str(x.get("내용") or "")))
    자리들 = {}
    for x in 목록:
        if 날짜줄(x) and x.get("어디"):
            자리들.setdefault(x["어디"], []).append(x)
    if not 자리들:
        return 목록
    날짜수 = {}
    for 어디 in 자리들:
        t = str(글표.get(어디) or "")
        수 = set()
        for m in re.finditer(r"(?:20\d{2}|'?\d{2})\s*[.년]\s*\d{1,2}\s*[.월](?:\s*\d{1,2}\s*[.일]?)?|\d{1,2}\s*월\s*\d{1,2}\s*일", t):
            수 |= set(re.findall(r"\d+", m.group(0)))
            수 |= {x.lstrip("0") for x in re.findall(r"\d+", m.group(0))}
        날짜수[어디] = 수
    out = []
    for x in 목록:
        어디 = x.get("어디")
        if 어디 in 자리들:
            m = re.fullmatch(r"자료에 없는 값 '(\d+)'", str(x.get("내용") or ""))
            if m and x.get("종류") == "지어냄 의심" and (m.group(1) in 날짜수.get(어디, set())):
                continue
            if 날짜줄(x) and x is not 자리들[어디][0]:
                continue
        out.append(x)
    return out


def _말한이없는인용줄(doc, 장르):
    """판형 v2 인용 부품에 말한이가 없으면 한 줄(fixup4 G7 — 교정이 지은 말한이를 키째 지운 인용)."""
    out = []
    if 장르 != "slides" or not isinstance(doc, dict) or not isinstance(doc.get("장"), list):
        return out
    for i, 장 in enumerate(doc["장"]):
        for j, c in enumerate((장 or {}).get("칸") or [] if isinstance(장, dict) else []):
            if isinstance(c, dict) and c.get("부품") == "인용" and not str(c.get("말한이") or "").strip():
                out.append((f"장.{i}.칸.{j}", f"{i + 1}번째 장: 말한 사람이 없는 인용으로 보입니다 — 누가 한 말인지 자료에서 찾아 적거나, "
                                            "인용 대신 요지로 바꿔 주세요"))
    return out


def _빈칸사람말(어디, 장르, 찾은, 민):
    """빈칸 줄 — 비운 자리표시를 맨 앞에(fixup4 ⑥), 그 뒤에 자리(사람 말)와 비운 글을 보인다(fixup4 G6: '○○○○·○ — ○○○○. ○. ○.'처럼
    자리표시 토막만 이어져 알아보기 어려웠다). 칸 전체가 자리표시면 그 글을 통째로 머리에 둔다."""
    자리 = _자리사람말(어디, 장르) or "이 칸"
    글 = 민.strip()
    나머지 = 글
    for t in 찾은:
        나머지 = 나머지.replace(t, "")
    # 대시(—) 이음 꼴을 걷고 빈 칸 줄(D3)과 같은 말로 맺는다 — '…이(가) 비어 있습니다. 채울 값을 알려 주세요.'('26-10-01
    # gates E2E: 'ㅇㅇ — 기관명: 「ㅇㅇ공사」 — 비어 있는 곳을 채워 주세요'). 인용은 낱말 경계에서 자르고 '…'(_인용줄임)
    if not re.sub(r"[○〇\s.·\-–—,()（）:：/]", "", 나머지):
        return f"{자리}{'이' if _받침있나(자리[-1]) else '가'} 비어 있습니다(「{_인용줄임(글, 40)}」). 채울 값을 알려 주세요."
    return f"{', '.join(찾은[:4])} 자리가 비어 있습니다({자리}: 「{_인용줄임(글, 80)}」). 채울 값을 알려 주세요."


def _인용줄임(글, n):
    """인용 글을 n 자 안에서 **낱말 경계**(띄어쓰기)에서 자르고 '…' 을 붙인다 — 글자 가운데서 자르면 '…밝혔」' 처럼
    낱말이 잘려 보였다('26-10-01 gates E2E). n 자 안에 띄어쓰기가 앞 절반에도 없으면(한 낱말이 긴 글) n 자에서 자른다."""
    글 = re.sub(r"\s+", " ", str(글 or "")).strip()
    if len(글) <= n:
        return 글
    앞 = 글[:n + 1]
    끝 = 앞.rfind(" ")
    앞 = 앞[:끝] if 끝 >= n // 2 else 글[:n]
    return 앞.rstrip(" ,·:;-–—(（「『\"'") + "…"


def _확인할것모으기(doc, 장르, 알림들, 규정확인, v2소프트, 속성거부, 값, byline전=None, key=None, 건너뜀=False, 원문확인=None):
    """새문서·저장 결과의 '확인할 것' 목록(M5, '26-09-29) — [{종류, 어디, 내용}]. 바로 완성 끝 보고가 그대로 쓴다.

    종류: 지어냄 의심 · 고친 곳(앞 판에서 지어냄 의심이었다가 고친 값) · 지어냈나 건너뜀 · 어긋남 · 확인 물음 ·
    작성일 날짜 · 셈한 값 · AI 그림 · 속성거부 · 자동 교정 · 조립기가 채움 · 경고 · 빈칸(○○). 80건을 넘으면 이 차례로
    남기고 '외 N건'.
    코어가 알 수 없는 것(에이전트가 가정한 값·추론해 쓴 문장·차점 유형)은 에이전트가 끝 보고에서 더한다."""
    목록 = []

    def 더(종류, 어디, 내용, 에이전트=None):
        # '내용'은 사용자용 말, '에이전트'는 에이전트(모델)용 원래 말 — 달라질 때만 싣는다(fixup3 Z5, 두 문구를 이 한 곳에서 나눈다)
        # 200자 상한도 낱말 경계에서 자르고 '…'(_인용줄임, '26-10-01 gates E2E — 글자 가운데서 잘렸다)
        _내 = str(내용 or "")
        줄 = {"종류": 종류, "어디": str(어디 or ""), "내용": _내 if len(_내) <= 200 else _인용줄임(_내, 199)}
        if 에이전트 and str(에이전트).strip() != 줄["내용"]:
            줄["에이전트"] = str(에이전트)[:300]
        목록.append(줄)

    def 걷기(n, 경로=""):
        if isinstance(n, dict):
            # "이미지" 키의 그림은 _그림살피기 가 **실제로 실린** 것에만 'AI 그림'을 단다('26-09-30 — 전에는 못 만든
            # 그림에도 달렸다). 그 밖의 생성 표시(판형 v2 '그림' 부품 등)는 전처럼 여기서 단다.
            if n.get("출처") == "생성" and not re.search(r"(?:^|\.)이미지(?:\.\d+)?$", 경로):
                더("AI 그림", 경로, "AI로 만든 그림입니다(문서에 'AI 생성물'로 표시). 내용이 맞는지 확인해 주세요.")
            for k, v in n.items():
                if k not in _확인할것_메타:
                    걷기(v, f"{경로}.{k}" if 경로 else str(k))
        elif isinstance(n, list):
            for i, v in enumerate(n):
                걷기(v, f"{경로}.{i}" if 경로 else str(i))
        elif isinstance(n, str):
            민 = re.sub(r"</?[A-Za-z][^>]*>", "", n)          # HTML 꼬리표만 걷는다(byline '<○○팀>')
            말단 = 경로.rsplit(".", 1)[-1]
            if 말단 in _빈값키 and 민.strip() in _빈값꼴:
                더("빈칸(○○)", 경로, f"'{민.strip()}'으로 비워 둔 칸입니다. 채울 값을 알려 주세요.")
            elif 경로 in _빈메타칸 and not 민.strip():
                더("빈칸(○○)", 경로, f"{말단}이(가) 비어 있습니다. 채울 값을 알려 주세요.")
            else:
                찾은 = []
                for m in _빈칸꼴().finditer(민):
                    t = m.group(0).strip()
                    if t in ("○", "〇"):
                        # ○ 는 한 글자씩 잡히므로 이어진 무리('○○'·'○○○')로 적는다(fixup6, verify5 N7 — 머리가 '○ — …'로 나왔다)
                        t = re.match(r"[○〇]+", 민[m.start():]).group(0)
                        if m.start() > 0 and 민[m.start() - 1] in "○〇":
                            continue
                    if t and t not in 찾은:
                        찾은.append(t)
                if 찾은:
                    # 찾은 자리표시와 자리(사람 말)를 함께 적는다 — 긴 글에서도 무엇이 어디서 비었는지 보이게(fixup4 ⑥·fixup4 G6)
                    더("빈칸(○○)", 경로, _빈칸사람말(경로, 장르, 찾은, 민))
            if re.search(r"\d\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}", n):
                날짜칸.append((경로, n))
    날짜칸 = []
    걷기(doc)
    # 작성일 자리(byline·배포·보고일·시행일·발표정보 …)의 날짜 — 오늘도 아니고 자료에도 없으면 확인할 것에 올린다
    # (fixup3 E, verify2 §2-B: 작성일 자리는 오늘 날짜를 지어냄 대조에서 빼는데, 그 자리의 **어떤 날짜든** 빠져
    # 자료 밖 '2026. 2. 24.'가 통과했다). 막지는 않는다 — 다른 날 다시 저장한 문서의 제 날짜일 수 있다.
    if 날짜칸:
        try:
            검 = 자료뿌리.모듈("지어냈나")
            원글 = str(((_검사자료읽기().get(str(key)) or {}).get("원문") if key else "") or "")
            원쌍 = 검._월일쌍들(원글)
            import datetime as _dt
            오늘 = _dt.date.today()
            for 어디, 글 in 날짜칸:
                if not 검._작성일자리인가(어디):
                    continue
                for m in list(검._바이라인_날짜_YYYY_RX.finditer(글)) + list(검._바이라인_날짜_YY_RX.finditer(글)):
                    월, 일 = int(m.group(2)), int(m.group(3))
                    if (월, 일) == (오늘.month, 오늘.day) or (월, 일) in 원쌍:
                        continue
                    더("작성일 날짜", 어디, f"작성일 '{m.group(0).strip()}'는 오늘 날짜도 아니고 자료에도 없습니다. "
                                         "맞는지 확인해 주세요.")
                    break
        except Exception as e:
            print(f"[확인할것] 작성일 날짜 보기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    # 규정 '내년' 물음은 한 번(X4) — 조문꼴의 부칙 시행일 물음이 같은 자료 말('내년')을 이미 인용하면 상대 연도 물음(W2)은 그 줄에
    # 셈한 연도만 덧붙이고 따로 싣지 않는다(예전엔 같은 시행일을 두 번 물었다 — wire_verify §3-4).
    규정줄 = [str(q) for q in (규정확인 or [])]
    남은확인 = []
    for x in 원문확인 or []:
        m = re.match(r"자료의 '(.+?)'[을를] (\d{4})년으로", str(x.get("내용") or "")) if x.get("종류") == "확인 물음" else None
        j = next((k for k, q in enumerate(규정줄) if m and m.group(1) in q), None) if m else None
        if j is not None:
            규정줄[j] += f" (초안은 자료의 '{m.group(1)}'을 {m.group(2)}년으로 셈해 적었습니다 — 연도도 함께 봐 주세요)"
            continue
        남은확인.append(x)
    for q in 규정줄:          # reg13f 판정 F4 — 200자를 넘는 규정 줄은 문장 경계에서 자르고 물음 끝을 남긴다(_규정줄자르기)
        더("확인 물음", "", _규정줄자르기(_규정물음사람말(q)), 에이전트=q)
    for x in 남은확인:          # 확인물음(상대 연도)·보도자료·1p·풀버전 본문 출처 — _원문확인줄('26-09-30 W1·W2·X4)
        더(x.get("종류"), x.get("어디"), x.get("내용"))
    # 출처 하나에 줄 하나(X4) — 이 자리의 출처 줄(확장 검사 출처·말한 사람, 본문 괄호 출처)이 있으면 그 출처 글 속의 이름·수(재기)와
    # 같은 자리의 슬라이드 출처 경고는 따로 싣지 않는다(예전엔 지은 출처 한 곳이 이름 줄·출처 줄·경고 줄 세 줄이 됐다).
    확장걸림 = [g for g in (((값 or {}).get("지어냈나확장") or {}).get("걸림") or []) if isinstance(g, dict)]
    출처자리 = {}
    for g in 확장걸림:
        if g.get("종류") in ("출처", "말한 사람"):
            출처자리.setdefault(str(g.get("어디") or ""), []).append(str(g.get("값") or ""))
    본문지은출처 = [m.group(1) for x in 남은확인 if x.get("종류") == "지어냄 의심"
                for m in [re.match(r"자료에 없는 출처 '(.+?)'", str(x.get("내용") or ""))] if m]
    if 본문지은출처:
        try:
            for 어디, 글 in 자료뿌리.모듈("지어냈나").문서글(doc):
                for 출 in 본문지은출처:
                    if 출 in str(글 or ""):
                        출처자리.setdefault(str(어디), []).append(출)
        except Exception as e:
            print(f"[확인할것] 본문 출처 자리 보기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    # 어긋남 — 이 세션에서 되물은 자리와 받은 답(바로 완성은 '미정(○○)' 답일 수 있다). 두 값을 함께 싣는다.
    try:
        for k, v in sorted((_미결어긋남읽기() or {}).items()):
            값들 = ", ".join(
                f"{x.get('값')}({'·'.join(str(d.get('자료')) for d in (x.get('어디') or []) if isinstance(d, dict)) or '자료'})"
                if isinstance(x, dict) else str(x) for x in (v.get("값들") or []))
            더("어긋남", v.get("무엇") or k, f"자료끼리 다름: {값들} — 답: {v.get('답') or '(없음)'}")
    except Exception:
        pass
    if byline전 is not None and 장르 == "samples" and doc.get("byline") != byline전:
        더("조립기가 채움", "byline", f"작성 부서·날짜 줄을 '{doc.get('byline')}'(으)로 채웠습니다.")
    for 알림 in 알림들:
        for 줄 in str(알림 or "").split("\n▸ "):
            줄 = 줄.strip()
            if not 줄 or 줄.startswith("사용자에게 확인할 것(규정)"):
                continue
            # 함수 이름·모듈 이름·경로는 사람 말로(fixup4 G3 — 표 한 곳 _자동교정말표), 원래 말은 에이전트 칸에
            if 줄.startswith(("슬라이드 모양을 고쳐 받았습니다", "개인 기본 제목 모양을 실었습니다")):
                더("조립기가 채움", "", _자동교정사람말(줄, 장르), 에이전트=줄)
            else:
                더("자동 교정", "", _자동교정사람말(줄, 장르), 에이전트=줄)
    for s in v2소프트 or []:
        if str(s).startswith("(모양 정규화) "):
            continue
        m = re.match(r"^(장\.([\d·]+)\.출처) (.*)$", str(s))
        if m:
            자리들 = [f"장.{n}.출처" for n in m.group(2).split("·") if n]
            if 자리들 and all(p in 출처자리 for p in 자리들):
                continue                              # 같은 자리 출처 줄이 이미 있다(출처 하나에 줄 하나)
            더("경고", m.group(1), _출처경고사람말(m.group(3)), 에이전트=s)
            continue
        _자 = re.match(r"^((?:장|슬라이드)\.\d+)", str(s))
        더("경고", _자.group(1) if _자 else "", _경고사람말(s, 장르), 에이전트=s)
    문 = (값 or {}).get("문체검사") or {}
    # 문체검사 [soft] 줄 — 줄 전체를 읽고(예전엔 160자에서 잘려 '…요약_본문_중'처럼 경로 토막이 남았다) 규칙 id 표(_문체경고말표)로
    # 사람 말을 고른다. 어느 절·항목인지는 같은 문서를 판정 함수로 다시 재어 찾는다(fixup4 G3 — '「56자」'만 남지 않게).
    _soft줄 = [m.group(0) for m in re.finditer(r"(?m)^\s*\[soft\][^\n]*", 문.get("로그") or "")]
    _자리표 = _문체자리표(doc, 장르) if _soft줄 else {}
    for 줄 in _soft줄:
        _m = _문체soft_RX.match(줄)
        _자리 = ""
        if _m:
            _후보 = _자리표.get((_m.group(1), _m.group(2))) or []
            _자리 = _후보.pop(0) if _후보 else ""
        더("경고", "", _문체경고사람말(줄, 장르, _자리), 에이전트=줄.strip())
    # 말한 사람 없는 v2 인용(fixup4 G7 — 교정이 지은 말한이를 키째 지웠다)
    for _어, _말 in _말한이없는인용줄(doc, 장르):
        더("경고", _어, _말)
    for 자리 in sorted({x["자리"] for x in (속성거부 or [])}):
        더("속성거부", 자리, "지정한 값을 조립기가 받지 않아 기본값으로 대체했습니다")
    지 = ((값 or {}).get("지어냈나") or {}).get("값") or {}
    for x in (지.get("수치") or []) + (지.get("이름") or []):
        v = str(x.get("값") or "")
        if v and any(v in s for s in 출처자리.get(str(x.get("어디") or ""), [])):
            continue                                  # 출처 글 속 이름·수 — 그 자리 출처 줄 하나로 싣는다
        더("지어냄 의심", x.get("어디"), f"자료에 없는 값 '{x.get('값')}'")
    # 같은 지은 출처가 여러 장에 있으면 한 줄로(fixup3 Z6 — 본문 괄호 출처의 '(2곳)'과 같은 자. 예전엔 장마다 한 줄이었다)
    _출처곳 = {}
    for g in 확장걸림:
        if g.get("종류") == "출처":
            _열 = re.sub(r"\s+", "", str(g.get("값") or ""))
            _출처곳[_열] = _출처곳.get(_열, 0) + 1
    _실은출처 = set()
    for g in 확장걸림:
        # 사용자에게 보이는 말만 싣는다(X2 — '글을 빈 문자열로' 같은 에이전트 지시문은 교정지시 쪽에만 남긴다)
        if g.get("종류") == "출처":
            _열 = re.sub(r"\s+", "", str(g.get("값") or ""))
            if _열 in _실은출처:
                continue
            _실은출처.add(_열)
            _말 = _확장사람말(g)
            _앞 = f"자료에 없는 출처 '{str(g.get('값') if g.get('값') is not None else '')[:40]}'"
            if _출처곳.get(_열, 1) > 1 and _말.startswith(_앞):
                _말 = _앞 + f"({_출처곳[_열]}곳)" + _말[len(_앞):]
            더("지어냄 의심", g.get("어디"), _말, 에이전트=g.get("설명"))
            continue
        더("지어냄 의심", g.get("어디"), _확장사람말(g), 에이전트=g.get("설명"))
    산출들 = [("산출", s) for s in (doc.get("산출") or [])] if isinstance(doc.get("산출"), list) else []
    for i, 장 in enumerate(doc.get("장") or [] if isinstance(doc.get("장"), list) else []):
        if isinstance(장, dict) and isinstance(장.get("산출"), list):
            산출들 += [(f"장.{i}.산출", s) for s in 장["산출"]]
    for 어디, s in 산출들:
        if isinstance(s, dict) and (s.get("값") or s.get("식")):
            더("셈한 값", 어디, f"{s.get('값')} = {s.get('식')}")
    if 건너뜀:
        더("지어냈나 건너뜀", "", "자료 원문 없이 만들어 자료 대조를 하지 못했습니다. 수치와 이름이 맞는지 확인해 주세요.")
    if key:
        try:
            for 종류, 어디, 내용 in _그림살피기(doc, 장르, key)[1]:
                더(종류, 어디, 내용)
        except Exception as e:
            print(f"[확인할것] 그림 보기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    if key:
        # 앞 판에서 지어냄 의심이었다가 이번 판에서 사라진 값(고친 곳) — 세션 검사자료에 쌓인다(fixup3 E).
        # 산출(식)로 받아들인 값은 고친 것이 아니라 셈한 값이다 — '셈한 값' 줄에만 싣는다(fixup6, verify5 N7)
        셈수 = {re.sub(r"[,\s]", "", x) for _, s in 산출들 if isinstance(s, dict)
               for x in re.findall(r"\d[\d,.]*", str(s.get("값") or ""))}
        셈수 = {x.rstrip(".") for x in 셈수}
        try:
            for v in ((_검사자료읽기().get(str(key)) or {}).get("고친곳") or []):
                if str(v).replace(",", "").strip() in 셈수:
                    continue
                더("고친 곳", "", f"자료에 없는 값 '{v}'이 있어 고쳤습니다. 고친 값이 자료와 맞는지 확인해 주세요.")
        except Exception:
            pass
    # 한 칸의 날짜 하나는 한 줄로(fixup4 G6 — 배포일 '2026. 9. 27.'이 값 '9'·값 '27'·작성일 자리·작성일 날짜 네 줄로 떴다)
    목록[:] = _날짜겹침빼기(목록, doc)
    # 마지막 거름(Z5) — 어느 갈래(알림·그림·자동 교정 …)에서 왔든 '내용'에 경로·규칙 번호·'사용자에게' 같은 에이전트 말이 남지 않게.
    # 바뀐 줄은 원래 말을 '에이전트' 칸에 남긴다(이미 있으면 그대로).
    for x in 목록:
        if x.get("종류") in ("빈칸(○○)", "셈한 값", "그림"):
            # 문서 글을 그대로 옮긴 줄 — 글을 고치지 않는다. 그림 줄은 imageasset 이 지은 사람 말에 사용자 파일 이름이 든다
            # ('26-10-01 주관 판정 Q4, verify_fixup9 B2 — site_photo.png·report_final.pdf 의 이름이 깎였다)
            continue
        _원 = x.get("내용") or ""
        _새 = _사람말다듬기(_원, 장르)
        if _새 != _원:
            x.setdefault("에이전트", _원)
            x["내용"] = _새 if len(_새) <= 200 else _인용줄임(_새, 199)
    차례 = {k: i for i, k in enumerate(_확인할것_차례)}
    if len(목록) > _확인할것_상한:
        # 남길 것을 고를 때는 빈칸을 **맨 뒤**로 본다 — 빈칸이 수십 건인 규정 별표에서 셈한 값·지어냄 의심이 밀려나지
        # 않게(verify2 §2-B F2). 남긴 목록을 보일 때는 빈칸이 맨 앞이다(아래 정렬).
        고름 = {k: i for i, k in enumerate(_확인할것_차례[1:] + _확인할것_차례[:1])}
        # ('26-10-01 주관 판정 Q6, verify_fixup9 N2) 그림 줄은 고르기 전에 몫(_확인할것_그림몫)을 남긴다 — 지어냄 의심이 많은
        # 덱에서 사진을 못 쓴 까닭이 '더 있음'으로 밀려 사라졌다
        _그림앞 = {id(x) for x in [y for y in 목록 if y.get("종류") == "그림"][:_확인할것_그림몫]}
        목록.sort(key=lambda x: -1 if id(x) in _그림앞 else 고름.get(x["종류"], len(고름)))
        남는 = 목록[_확인할것_상한 - 1:]
        세기 = {}
        for x in 남는:
            세기[x["종류"]] = 세기.get(x["종류"], 0) + 1
        목록 = 목록[:_확인할것_상한 - 1]
        목록.sort(key=lambda x: 차례.get(x["종류"], len(차례)))
        목록.append({"종류": "더 있음", "어디": "",
                   "내용": f"이 밖에 {len(남는)}건이 더 있습니다(" + ", ".join(f"{k} {n}" for k, n in 세기.items())
                          + "). 편집 화면이나 문서에서 확인해 주세요."})
    else:
        목록.sort(key=lambda x: 차례.get(x["종류"], len(차례)))      # 안정 정렬 — 빈칸이 맨 앞, 같은 종류 안의 차례는 그대로
    return 목록


def _등록부에서한줄빼기(등록, 키):
    """등록부에서 **그 이름 한 줄만** 뺀다. (뺀 줄 수, 사고 문구)

    빗장을 쥐고 다시 읽어서 뺀다 — 스냅샷 복원이 아니라 진짜 되돌리기다.
    """
    try:
        with 자료뿌리.빗장(등록):
            cur = json.load(open(등록, encoding="utf-8"))
            남을것 = [d for d in cur if d.get("filename") != 키]
            뺀수 = len(cur) - len(남을것)
            if 뺀수:
                자료뿌리.원자json(등록, 남을것, indent=2)
        return 뺀수, ""
    except (자료뿌리.못잠금, OSError, ValueError) as e:
        # 조용히 넘어가지 않는다(규칙 3) — 못 되돌린 채로 400 만 내면, 등록부에는
        # 조립 안 된 문서가 남아 다음 조립이 통째로 걸린다.
        return 0, f"{type(e).__name__}: {e}"


def _고아산출물치우기(키):
    """조립이 실패했을 때 남은 산출 파일을 치운다 — 어느 등록부도 안 가리키는 고아다.

    조립기는 `with open(...)` 안에서 본문을 만들기 때문에 doc 이 깨져 있으면 정확히
    그 사이에서 죽어 0바이트 html 이 남는다(적대리뷰 ③의 '함께 드러난 것').
    """
    n = 0
    for 끝 in ("html", "pdf", "hwpx"):
        p = 자료뿌리.산출물(키, 끝)
        try:
            if os.path.exists(p):
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


@등록("세션마감", 읽기=False,
    설명="이 세션을 지금 끝낸다 — 내용은 지우고 익명 원장 후보만 남긴다", en="endsession")
def 세션마감():
    """명시적 마감(출시계획 1-1: "무반응 10분 **또는** 최종본 내려받음").

    세 문 어디서 불러도 같다 — 등록부에 한 줄 적었으므로 MCP 도구·HTTP 경로·CLI 가
    자동으로 생긴다. 웹앱 배선(F1)과 '내려받으면 마감' 흐름은 다음 단계 몫이고,
    여기는 **작업 하나**가 있으면 된다.

    세션이 없을 때(개발·CLI)는 지울 것이 없다 — 조용히 성공을 내지 않고 거절한다.
    기본 뿌리를 지우는 길을 여기 열어 두면 언젠가 운영 자료가 통째로 사라진다.
    """
    세션 = 자료뿌리.모듈("세션")
    try:
        열쇠 = 자료뿌리.세션열쇠()
    except Exception as e:
        return {"ok": False, "로그": str(e)}
    if not 열쇠:
        return {"ok": False, "로그": "지금은 세션이 아닙니다 — 마감할 것이 없습니다 "
                                  f"(세션은 환경변수 {자료뿌리.세션환경변수} 나 "
                                  f"웹앱 쿠키로 이어집니다)"}
    return 세션.끝내기(열쇠, "마감")


@등록("장르", 설명="만들 수 있는 장르와 판별 신호 — **세어서** 얻는다", en="genres", 정책=True)
def 장르():
    """장르 목록을 손으로 적지 않는다. 등록부(build/*-docs.json)와 정본을 맞춰 센다.

    2026-08-04: 웹앱 드롭다운에 셋만 손으로 적어 두 장르가 빠졌다 — 오늘 하루 종일
    고쳐 온 바로 그 병을 새 화면에서 또 저질렀다. 목록은 언제나 세어서 얻는다.
    """
    # 온톨로지는 지식()으로 조각만 받는다(정책만-로컬엔 로컬 ontology.json 이 없다 · A1 조회).
    # A1(로컬강제)에선 지식()이 로컬 온톨로지를 읽어 같은 결과가 난다. document_types 는 커서
    # 지식()이 키 목록만 준다(값=None·키=[…]) → 키로 존재를 보고 status 는 조각으로 받는다.
    # (예전엔 여기서 ontology.json 을 직접 읽어 정책만-로컬 배포본의 판정이 통째로 죽었다.)
    _dt = 지식("document_types")
    타입키 = list((_dt.get("값") or {}).keys()) or (_dt.get("키") or [])
    def _상태(k):
        r = 지식("document_types." + str(k) + ".status")
        return r.get("값") if isinstance(r, dict) and r.get("ok") else None
    이름표 = {"samples": "onepage-report"}
    사람말 = {"onepage-report": "1페이지 보고서", "gongmun": "시행문",
            "fullreport": "풀버전 보고서", "regulation": "규정", "press-release": "보도자료",
            "slides": "발표 슬라이드"}
    out = []
    for p in 등록부들():
        키 = os.path.basename(p).replace("-docs.json", "")
        정본키 = 이름표.get(키, 키)
        if 정본키 not in 타입키:
            정본키 = next((k for k in 타입키 if k.startswith(키)), None)
        if not 정본키 or _상태(정본키) != "만들수있음":
            continue
        out.append({"등록부": 키, "정본": 정본키,
                    "이름": 사람말.get(정본키, 정본키)})
    # 판별신호(장르판별)는 **더 이상 클라이언트로 안 내린다** — 서버 판정(detect)이
    # 쓰고, 브라우저엔 장르 목록만 준다(2026-08-12 온톨로지 유출 차단).
    return {"ok": True, "값": {"장르": out}}


# ── 파일 올리기 · 읽기 · 서식 분석 ─────────────────────────────────────────

@등록("올리기", ["이름", "내용_base64"], 읽기=False,
    설명="파일을 base64 로 올려 inbox 에 놓는다 — 원격 MCP 클라이언트가 파일읽기·"
        "서식분석·어긋남 을 쓰려면 먼저 이 문으로 파일을 올려야 한다(X2 F-2)", en="upload")
def 올리기(이름, 내용_base64):
    """serve.py 의 옛 `/올림` 업로드가 하던 검증(경로 밖 이탈 금지·크기 제한·이름
    충돌 시 개명)을 그대로 옮긴 것이다. 로직이 둘로 갈리면 한쪽만 고쳐질 때
    어긋난다 — 이제 serve.py 의 `/올림` 도 이 작업을 부르기만 한다."""
    import base64
    이름 = os.path.basename(str(이름 or "")).strip()
    자료 = 내용_base64 or ""
    if not 이름 or not 자료:
        return {"ok": False, "로그": "파일 이름과 내용이 있어야 합니다"}
    if len(자료) > 40 * 1024 * 1024:
        return {"ok": False, "로그": "파일이 너무 큽니다(30MB 어름까지)"}
    안 = 자료뿌리.받은것뿌리()
    os.makedirs(안, exist_ok=True)
    # 같은 이름이 오면 덮어쓰지 않는다 — 남의 자료를 지우게 된다. 실제로 저장된
    # 이름(개명됐을 수 있다)을 응답으로 돌려준다 — 부르는 쪽이 그 이름으로 이어
    # 읽어야 한다(X2 C-2 와 같은 함정: 응답의 이름을 안 쓰면 남의 파일을 읽는다).
    뿌리, 끝 = os.path.splitext(이름)
    # 파일명이 길면(한글은 글자당 3바이트) 임시·충돌 접미사까지 붙어 파일시스템 이름 한도
    # (암호화 홈은 ~143바이트)를 넘겨 [Errno 36] File name too long 이 난다. 확장자는 지키고
    # 앞부분만 **바이트 기준**으로 잘라 저장한다 — 표시용 원본 이름은 브라우저가 따로 갖는다.
    끝 = 끝[:12]
    _b = 뿌리.encode("utf-8")
    if len(_b) > 60:
        뿌리 = _b[:60].decode("utf-8", "ignore").rstrip() or "file"
    이름 = 뿌리 + 끝
    n, 놓을곳 = 0, os.path.join(안, 이름)
    while os.path.exists(놓을곳):
        n += 1
        이름 = f"{뿌리}-{n}{끝}"
        놓을곳 = os.path.join(안, 이름)
    데이터 = base64.b64decode(자료.split(",")[-1])
    def _써넣기(대상):
        with 자료뿌리.쓰기(대상, "wb") as f:        # 반쪽 업로드가 inbox 에 안 남게
            f.write(데이터)
    try:
        _써넣기(놓을곳)
    except OSError as e:
        # [Errno 36] ENAMETOOLONG — 어떤 이유로든 이름/경로가 길면 **짧은 이름으로 물러선다**.
        # 표시용 원본 이름은 브라우저가 따로 가지므로 저장 이름이 짧아도 사용자에겐 안 보인다.
        if getattr(e, "errno", None) == 36:
            import secrets
            이름 = "up-" + secrets.token_hex(6) + 끝
            놓을곳 = os.path.join(안, 이름)
            try:
                _써넣기(놓을곳)
            except Exception as e2:
                return {"ok": False, "로그": f"파일을 놓지 못했습니다: {e2}"}
        else:
            return {"ok": False, "로그": f"파일을 놓지 못했습니다: {e}"}
    except Exception as e:
        return {"ok": False, "로그": f"파일을 놓지 못했습니다: {e}"}
    _대화그림적기(이름)          # 이 대화에서 올린 자료 — 그림 목록 범위에 든다(_그림범위)
    return {"ok": True, "값": {"이름": 이름, "크기": os.path.getsize(놓을곳)}}


def _kordoc경로():
    """고정 설치된 kordoc 실행 파일 경로 — 없으면 None (WP-S8, X2 C-3).

    이전에는 실행 시점마다 `npx -y kordoc` 으로 네트워크에서 받아 왔다. 밀폐
    컨테이너(네트워크 없음)에 올리면 파일읽기·서식분석 두 작업이 통째로 죽는
    원인이었다. 이제는 이 저장소 루트(package.json)에 버전을 고정해 두고
    `npm install` 로 node_modules 에 미리 깔아 둔다 — 실행 시점에는 그 실행
    파일만 찾고, **네트워크로 새로 받으려 하지 않는다.**
    """
    p = os.path.join(ROOT, "node_modules", ".bin", "kordoc")
    return p if os.path.exists(p) else None


def _kordoc(경로, 형식="markdown", 쪽=""):
    """kordoc CLI 로 문서를 읽는다. HWP·HWPX·PDF·XLSX·DOCX·이미지(OCR) 를 다 받는다."""
    import tempfile
    # 글 파일은 **kordoc 을 거치지 않는다.** 파서가 할 일이 없는데 거절당한다
    # ("지원하지 않는 파일 형식입니다"). 사용자가 제일 자주 던지는 것이 붙여 넣은
    # 글인데 그게 막혀 있었다(2026-08-05 A-3 시험에서 걸림).
    if os.path.splitext(경로)[1].lower() in (".txt", ".md", ".markdown"):
        try:
            글 = open(경로, encoding="utf-8", errors="replace").read()
        except OSError as e:
            return None, f"글 파일을 못 읽었습니다 — {e}"
        if 형식 in ("json", "chunks"):
            return {"markdown": 글, "text": 글}, ""
        return 글, ""
    kordoc = _kordoc경로()
    if not kordoc:
        return None, ("kordoc 이 설치되어 있지 않습니다 — 이 저장소 루트"
                       f"({ROOT})에서 `npm install` 을 한 번 실행해야 합니다"
                       " (package.json 에 버전이 고정돼 있습니다). 조용히 "
                       "인터넷에서 새로 받아 오지 않습니다.")
    # 개인 폴더에 쓰고 **폴더째** 지운다('26-09-28, kordoc 4.16 올림 때 잼). kordoc 은 -o 옆
    # (4.15.4 는 <그 폴더>/images/, 4.16 은 images/<문서 이름>/)에 문서 속 그림과
    # manifest.json 을 풀어 놓는다. 예전엔 공용 임시 폴더에 -o 를 두고 그 파일 하나만 지워서
    # 사용자 문서의 그림이 공용 /tmp/images/ 에 쌓이고 다른 문서 그림을 덮어썼다(4.15.4 실측:
    # 합성 DOCX 1장·HWPX 4장·PDF 1장이 세 형식 모두 남음). 우리는 글만 쓰므로 --no-images 로
    # 그림 바이트를 아예 안 뽑는다(chunks 는 바이트 단위로 같다. markdown 은 4.15.4 에선 같았고
    # 4.16 에선 끊긴 그림 참조 경로만 짧아진다. json 에서는 images·imageData 가 빠진다 — 셋 다
    # 읽는 곳이 없다). 폴더째 지우기는 그래도 남을 것의 안전망이다.
    # node 쪽 임시 파일(OCR 런타임의 mat-debug-*.log·.ses 등, '26-09-29 검토자 실측)도 이 폴더에
    # 떨어지도록 TMPDIR 을 이 폴더로 준다 — 공용 임시 폴더에 쌓이지 않고 폴더와 함께 지워진다.
    import shutil
    작업폴더 = tempfile.mkdtemp(prefix="kordoc-")
    환경 = dict(os.environ, TMPDIR=작업폴더)
    마감 = time.monotonic() + 600          # 한 번 읽기에 쓰는 시간 전체(PDF 여러 번 읽기 포함)
    # 첨자 태그 끄기 옵션 — 이 옵션을 모르는 kordoc(4.15.4·4.16.0)은 'unknown option' 으로 **모든** 읽기를 거절했다
    # ('26-09-30 검토자 fv5 16/16 실패: 배포 되돌리기·나눠 커밋으로 새 코드 + 옛 kordoc 이 되는 길). 그 답을 받으면 옵션
    # 없이 한 번 다시 부르고(4.16.2 미만은 태그를 내지 않으니 글이 같다) 경고를 로그에 남긴다(주관 판정 K1).
    태그끔 = ["--no-script-tags"]

    def 한번(형식_, ocr끔, 쪽_=None, 강제=False):
        e = 환경
        쪽_ = 쪽 if 쪽_ is None else 쪽_
        if ocr끔:
            # 빈 전용 모델 캐시 — kordoc 4.16 은 모델이 캐시에 있으면 PDF 에 자동 OCR 을 켜고
            # CLI 로는 끌 수 없다(--no-ocr 없음). PDF 는 모델을 받지 않으므로 이 폴더는 비어 있다.
            빈캐시 = os.path.join(작업폴더, "ocr-off")
            os.makedirs(빈캐시, exist_ok=True)
            e = dict(환경, KORDOC_MODEL_CACHE=빈캐시)
        낼곳 = os.path.join(작업폴더, f"out-{형식_}-{'off' if ocr끔 else 'on'}{'-force' if 강제 else ''}"
                          + (".json" if 형식_ in ("json", "chunks") else ".md"))
        # --no-script-tags('26-09-29 주관 판정): kordoc 4.16.2 부터 HWPX·HWP·DOCX 의 위·아래첨자를 <sup>·<sub> 태그로
        # 낸다. 우리 소비 코드(파일읽기 글 → 초안 자료·지어냈나 원문, 서식분석 절 이름)는 태그를 글로 받아 절 이름이
        # '추진 배경<sup>1)</sup>' 가 되고 모델 자료에 태그가 섞였다(검토자 U15). 이 옵션 하나로 4.16.0 과 같은 평문
        # ('추진 배경1)', '104 m2')이 된다 — 영향받은 4파일이 markdown·chunks 바이트까지 4.16.0 과 같다(실측).
        cmd = [kordoc, 경로, "--format", 형식_, "--silent", "--no-images", *태그끔, "-o", 낼곳]
        if 쪽_:
            cmd += ["-p", str(쪽_)]
        if 강제:
            cmd += ["--ocr-force"]         # 스캔 쪽 — 글층이 있어도 OCR(판정 S1, 아래 강제 참고). 4.15.4 도 아는 옵션이다
        r = subprocess.run(cmd, capture_output=True, text=True, env=e,
                           timeout=max(1.0, 마감 - time.monotonic()))
        if not os.path.exists(낼곳) or os.path.getsize(낼곳) == 0:
            탈 = (r.stdout or "") + (r.stderr or "")
            if 태그끔 and "unknown option" in 탈 and "--no-script-tags" in 탈:
                print(f"[kordoc] 설치된 kordoc 이 --no-script-tags 를 모릅니다(4.16.2 미만) — 옵션 없이 다시 읽습니다. "
                      f"package.json 고정판과 node_modules 를 맞추세요({kordoc})", file=sys.stderr)
                태그끔.clear()
                return 한번(형식_, ocr끔, 쪽_, 강제)
            # kordoc 4.10+ 는 실패를 stdout 에 JSON({success:false, error, code})으로 낸다 —
            # 사용자에게는 그 안의 오류 문장만 보인다(JSON 덩어리를 그대로 내보내지 않는다).
            try:
                j = json.loads((r.stdout or "").strip() or "null")
                if isinstance(j, dict) and j.get("error"):
                    탈 = str(j["error"]) + (f" ({j['code']})" if j.get("code") else "")
                    if j.get("code") == "MISSING_DEPENDENCY":      # 그림 파일 OCR — onnxruntime-node·sharp 가 빠진 설치(kordoc #99)
                        탈 = ("이 기계의 kordoc 설치에 OCR 실행기(onnxruntime-node·sharp)가 빠져 그림을 읽지 못했습니다"
                              " (MISSING_DEPENDENCY)")
            except ValueError:
                pass
            return None, 탈 or "읽지 못했습니다"
        본 = open(낼곳, encoding="utf-8", errors="replace").read()
        return (json.loads(본) if 형식_ in ("json", "chunks") else 본), ""

    try:
        if not _PDF인가(경로):
            # 모델 지문은 **그림 파일**(OCR 하는 길)에서만 잰다 — hwp·hwpx·docx·xlsx 는 OCR 을 하지 않는데, 읽는 사이 다른
            # 세션이 모델을 다시 받으면 '모델이 깨져 다시 받았습니다' 가 거짓으로 붙었다('26-09-30 검토자 fv6 ④ 3/3).
            그림 = _그림파일인가(경로)
            전지문 = _OCR모델지문(환경) if 그림 else None
            t0 = time.monotonic()
            본, 탈 = 한번(형식, False)          # 그림 파일(PNG·JPG…)은 예전처럼 OCR 로 읽는다
            받음 = (_모델다시받음(전지문, _OCR모델지문(환경), time.monotonic() - t0)
                  if 그림 and 본 is not None else "")
            return 본, (f"{탈} · {받음}" if 탈 else 받음) if 받음 else 탈
        # PDF 는 먼저 **OCR 없이** 읽는다('26-09-29 판정). 4.16 의 자동 OCR 은 글층이 적고 큰 그림이
        # 있는 쪽의 글층을 OCR 결과로 통째로 갈아 끼워, 글꼴이 임베드 안 된 PDF 는 글이 다 사라지고
        # 임베드된 것도 □ 표지·띄어쓰기가 빠졌다(합성 사례 실측). 서버에서 이미지 한 번으로 모델이
        # 받아지면 그때부터 모든 PDF 에 켜진다 — 사용 이력에 따라 결과가 바뀌면 안 된다.
        # 판정은 **쪽 단위**다(_OCR할쪽 — 형식과 무관하게 OCR 끈 json 한 번으로 정한다, 그래서 markdown·
        # json·chunks 가 같은 쪽을 OCR 한다). 글층이 0자인 쪽, 그리고 글층이 몇 자(쪽 번호·'사본' 등, _쪽문턱
        # 이하)뿐이면서 그 쪽에 그림이 있는 쪽만 OCR 로 읽어(-p 그 쪽들) 그 쪽 자리에 합친다 — 원래 글층 글은
        # 버리지 않고 OCR 글에 없을 때만 덧붙인다(_쪽글합치기). 그 밖의 쪽은 OCR 없이 읽은 글을 **지킨다**.
        # 예전의 문서 단위 문턱(쪽당 8자)은 쪽마다 짧은 제목 + 큰 사진인 정상 PDF(5쪽 22자)를 OCR 결과로 갈아
        # 끼워 7자로 만들었고, 표지(글층) + 스캔 9쪽은 chunks 가 쪽 수를 1로 세어 스캔을 놓쳤다('26-09-29 검토자 반례).
        # OCR 은 형식과 무관하게 **json** 으로 한 번 읽는다 — chunks 로 읽으면 kordoc 이 떨어진 쪽들(-p 2,5,6)을
        # 조각 하나(page=2)에 몰아 담아 쪽 차례가 [1,2,5,6,3,4] 로 섞였다('26-09-29 검토자 Q12). chunks 는 합친
        # json 의 쪽 글로 채운다(_쪽채우기_chunks) — 그래서 markdown·json·chunks 가 같은 글, 같은 쪽 차례다.
        # OCR 이 실패하거나 시간을 넘기면 OCR 없이 읽은 글로 물러서되 **조용히 넘기지 않는다** — 두 번째 값에
        # 경고를 싣는다(파일읽기 가 '경고' 로 낸다). 예전엔 스캔 문서가 오류 없이 빈 글로 나왔다(검토자 Q4).
        j, 탈 = 한번("json", True)
        if j is None:
            return None, 탈
        # 스캔 쪽(그림이 쪽의 80% 이상을 덮는 쪽)은 글층 글자 수와 상관없이 OCR 하고 그 OCR 줄을 절·항목으로 올린다(판정 S1)
        넓음 = set()                       # 그림이 쪽의 80% 이상을 덮는 쪽(몸글 보정과 상관없이) — 아래 '건너뜀' 경고
        스캔 = _스캔쪽들(경로, 넓음)
        쪽들 = _OCR할쪽(j, 스캔, 넓음)
        if 형식 == "chunks":
            본, 탈 = 한번("chunks", True)
            if 본 is None:
                return None, 탈
        else:
            본 = j
        경고 = ""
        if 쪽들:
            전지문 = _OCR모델지문(환경)
            t0 = time.monotonic()
            # 스캔 쪽은 --ocr-force 로 읽는다 — kordoc 의 자동 OCR 은 글층이 몇십 자 있는 전면 스캔 쪽을 제 판정으로 건너뛰어
            # (글층만 내고 OCR_APPLIED 도 없음) 우리가 고른 쪽이 조용히 OCR 되지 않았다('26-09-30 잼, 4.16.3: 전면 스캔 + 머리 도장
            # 30·50자 — 자동 0쪽, 강제 1쪽). 스캔 아닌 쪽은 예전대로 자동 OCR 로 읽는다(판정 S1 '지금처럼'). 모델이 없으면 강제하지
            # 않는다 — 강제는 모델을 망에서 받으려 해 결과가 사용 이력·망에 따라 달라진다. 그 쪽은 아래 '모델 없음' 경고로 간다.
            강제 = sorted(set(쪽들) & 스캔) if _OCR모델있나(환경) else []
            보통 = sorted(set(쪽들) - set(강제))
            켠, 켠탈, 못읽음, 건너뜀 = None, "", {}, set()
            for 묶음, 힘 in ((보통, False), (강제, True)):
                if not 묶음:
                    continue
                try:
                    x, 탈x = 한번("json", False, ",".join(map(str, 묶음)), 힘)
                except subprocess.TimeoutExpired:
                    x, 탈x = None, "시간 초과"
                if isinstance(x, dict):
                    if not 힘 and 태그끔:
                        # 자동 OCR 이 **건너뛴** 쪽 — 쪽 품질에 ocrApplied 가 없다(4.16.3 은 OCR 한 쪽에만 참을 적는다). 그 가운데 그림이
                        # 쪽을 거의 다 덮는 쪽(몸글 보정으로 스캔에서 빠진 쪽)은 경고 없이 글층만 남았다('26-10-01 검토자 fv7 ①: 전면
                        # 스캔 + 가운데 출력 표지 24자 — kordoc 은 글층이 20자를 넘어 OCR 대상이 아니라 보고 경고 코드도 내지 않는다,
                        # 본문 0자). 쪽 전체가 그림이 아닌 쪽(작은 그림 + 글층 20~49자 — 재경부 m34·m42·m64 실측)은 알리지 않는다.
                        품 = {_쪽번호(q.get("page")): q for q in x.get("pageQuality") or [] if isinstance(q, dict)}
                        if 품:
                            건너뜀 |= {n for n in 묶음 if n in 넓음 and n in 품 and not 품[n].get("ocrApplied")}
                    켠 = x if 켠 is None else _켠잇기(켠, x)
                else:
                    못읽음[tuple(묶음)] = str(탈x or "읽기 실패")[:80]
                    켠탈 = 켠탈 or 탈x
            받음 = _모델다시받음(전지문, _OCR모델지문(환경), time.monotonic() - t0)
            채운 = set()
            if isinstance(켠, dict):
                합, 채운 = _쪽합치기(j, 켠, 쪽들, 스캔)
                if 채운:
                    본 = _쪽채우기_chunks(본, j, 합, 채운) if 형식 == "chunks" else 합
            실행불가, 실패쪽, 빈쪽 = _OCR실패(켠) if isinstance(켠, dict) else ("", {}, [])
            # OCR 이 아예 돌지 않은 읽기 — 옛 kordoc(4.15.4·4.16.0: --no-script-tags 를 몰라 옵션 없이 다시 부른 판)은 글층이
            # 몇 자 있는 스캔 쪽을 OCR 하지 않고(SKIPPED_IMAGE 만), 4.15.4 는 글층 0자 스캔도 NEEDS_OCR 만 적는다. 켠 json 에
            # OCR_APPLIED·OCR_FAILED 가 없으면 조용한 0자였다('26-09-30 검토자 fv6 ①: 되돌리기·나눠 커밋 길에서 K6 이득이 경고
            # 없이 꺼짐). 4.16.3 은 OCR 을 돌리면 (글을 못 찾아도) OCR_APPLIED 를 적으므로 이 경고가 붙지 않는다.
            안돔 = isinstance(켠, dict) and not 채운 and _OCR안돔(켠, not 태그끔)
            if not isinstance(켠, dict) or not _OCR모델있나(환경) or 실행불가 or 안돔:
                # 모델 캐시가 비었으면 kordoc 은 OCR 을 켜지 않고 글층만 낸다(자동 OCR 게이트 ocrModelsCached) — 성공처럼
                # 보이는 빈 글이 된다('26-09-29 검토자 ⓒ: 캐시 없는 기계에서 스캔 PDF 가 경고 없이 0자). 사실대로 알린다.
                # onnxruntime-node 가 빠진 설치도 같다 — kordoc 은 켠 json 의 warnings 에 OCR_FAILED 만 적고 글층만
                # 낸다('26-09-30 검토자 fv5 ⓓ 0/4 경고 없음, 주관 판정 K5).
                까닭 = (str(켠탈 or "읽기 실패")[:80] if not isinstance(켠, dict)
                      else 실행불가 if 실행불가 and _OCR모델있나(환경)
                      else "OCR 모델이 이 기계에 없음 — 첫 그림 OCR 때 받거나 `kordoc models` 로 받는다" if not _OCR모델있나(환경)
                      else ("설치된 kordoc 이 package.json 고정판보다 옛 판(4.16.2 미만)이라 OCR 을 하지 않음" if not 태그끔
                            else "kordoc 이 OCR 을 하지 않음(NEEDS_OCR)"))
                경고 = (f"스캔으로 보이는 {len(쪽들)}쪽({_쪽목록(쪽들)})을 OCR 로 읽지 못해({까닭}) "
                       "글층 글만 넣었습니다 — 그 쪽의 글이 빠졌을 수 있습니다")
            else:
                줄 = [f"{_쪽목록(묶음)}은 OCR 로 읽지 못해({탈x}) 글층 글만 넣었습니다 — 그 쪽의 글이 빠졌을 수 있습니다"
                     for 묶음, 탈x in 못읽음.items()]          # 스캔 쪽(강제)·그 밖의 쪽(자동) 두 번 가운데 한 번만 실패
                if 실패쪽:
                    줄.append(f"{_쪽목록(실패쪽)}은 OCR 이 실패해({next(iter(실패쪽.values()))}) 글층 글만 넣었습니다 — "
                             "그 쪽의 글이 빠졌을 수 있습니다")
                if 빈쪽:
                    줄.append(f"{_쪽목록(빈쪽)}은 OCR 로도 글을 찾지 못했습니다(빈 쪽이면 괜찮습니다)")
                건너뜀 = sorted(건너뜀 - 채운 - set(실패쪽) - set(빈쪽))
                if 건너뜀:
                    줄.append(f"{_쪽목록(건너뜀)}은 쪽 전체가 그림인데 kordoc 이 OCR 하지 않아 글층 글만 넣었습니다 — "
                             "스캔한 쪽이면 그 쪽의 글이 빠졌을 수 있습니다")
                경고 = " · ".join(줄)
            if 받음:
                경고 = f"{경고} · {받음}" if 경고 else 받음
        if 형식 == "markdown":
            return 본.get("markdown") or "", 경고
        return 본, 경고
    except subprocess.TimeoutExpired:
        return None, "읽는 데 너무 오래 걸립니다"
    finally:
        shutil.rmtree(작업폴더, ignore_errors=True)


def _PDF인가(경로):
    """PDF 는 확장자가 아니라 **파일 머리(%PDF-)** 로도 가린다 — 올리기는 사용자가 준 이름을 그대로 두므로
    확장자 없는 PDF 가 OCR 거르기를 피해 가 글층이 OCR 결과로 갈아 끼워졌다('26-09-29 검토자 반례:
    korea.pdf 15자 → 확장자 없는 korea 0자). 명세상 머리는 첫 1024 바이트 안에 있다."""
    if os.path.splitext(경로)[1].lower() == ".pdf":
        return True
    try:
        with open(경로, "rb") as f:
            return b"%PDF-" in f.read(1024)
    except OSError:
        return False


_그림확장자 = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
_그림머리 = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*")


def _그림파일인가(경로):
    """그림 파일(kordoc 이 OCR 로 읽는 것)인가 — 확장자, 없으면 파일 머리로 본다(WEBP 는 RIFF…WEBP)."""
    if os.path.splitext(str(경로))[1].lower() in _그림확장자:
        return True
    try:
        with open(경로, "rb") as f:
            머 = f.read(12)
    except OSError:
        return False
    return 머.startswith(_그림머리) or (머[:4] == b"RIFF" and 머[8:12] == b"WEBP")


def _DOCX인가(경로):
    """DOCX 는 확장자가 아니라 **파일 속(word/document.xml)** 으로도 가린다 — 올리기는 사용자가 준 이름을 그대로
    두므로 확장자 없는 DOCX 는 서식분석의 Word 번호 목록·제목 규칙을 비껴갔다('26-09-29 검토자 D3 0→3절)."""
    if os.path.splitext(str(경로))[1].lower() == ".docx":
        return True
    try:
        import zipfile
        with zipfile.ZipFile(경로) as z:
            return "word/document.xml" in z.namelist()
    except Exception:
        return False


def _DOCX제목글(경로):
    """DOCX 에서 Word 'Title' 스타일 문단의 글(정규) 모음 — kordoc 4.16.3 은 이 문단을 보통 문단으로 내서(json·chunks
    모두 paragraph) 서식분석이 문서 제목을 못 알아봤다('26-09-30 검토자 fv5 C4). 스타일 id 는 한국어 Word 에서 'a3' 처럼
    달라지므로 styles.xml 의 이름(w:name='Title')으로 찾는다. 못 읽으면 빈 모음."""
    try:
        import zipfile
        ET = 자료뿌리.모듈("안전xml")   # 올린 파일 — DTD·엔티티 선언이 있으면 읽기 전에 거절(감사 code F4)
        w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(경로) as z:
            이름들 = set(z.namelist())
            ids = {"Title"}
            if "word/styles.xml" in 이름들:
                for st in ET.fromstring(z.read("word/styles.xml")).iter(f"{w}style"):
                    nm = st.find(f"{w}name")
                    if nm is not None and str(nm.get(f"{w}val") or "").strip().lower() == "title":
                        ids.add(st.get(f"{w}styleId"))
            out = set()
            for p in ET.fromstring(z.read("word/document.xml")).iter(f"{w}p"):
                ps = p.find(f"{w}pPr/{w}pStyle")
                if ps is not None and ps.get(f"{w}val") in ids:
                    글 = _정규("".join(t.text or "" for t in p.iter(f"{w}t")))
                    if 글:
                        out.add(글)
            return out
    except Exception:
        return set()


def _HWPX인가(경로):
    """HWPX 는 확장자가 아니라 파일 속(Contents/header.xml)으로도 가린다(_DOCX인가 와 같은 까닭)."""
    if os.path.splitext(str(경로))[1].lower() == ".hwpx":
        return True
    try:
        import zipfile
        with zipfile.ZipFile(경로) as z:
            return "Contents/header.xml" in z.namelist()
    except Exception:
        return False


def _제목스타일(이름, 영문):
    """문서 제목 스타일 이름인가 — '제목'·'문서 제목'·'표제'·Title(영문 이름 포함). 괄호 속 글꼴 설명('제목(신명조20)')은 떼고
    본다. '차례 제목'·'중제목'·'표제목'·'별지제목'·'장-제목' 같은 것은 문서 제목이 아니다(재경부 공개 hwpx·말뭉치의 스타일
    이름 62파일 실측 — 그런 이름뿐이고 위 셋·Title 은 없었다. 정밀도 우선)."""
    a = re.sub(r"\([^)]*\)|[^0-9A-Za-z가-힣]", "", str(이름 or "")).lower()
    b = re.sub(r"[^0-9A-Za-z]", "", str(영문 or "")).lower()
    return a in ("제목", "문서제목", "표제", "title", "documenttitle") or b in ("title", "documenttitle")


def _HWPX제목글(경로):
    """HWPX 에서 문서 제목 스타일(_제목스타일) 문단의 글(정규) 모음 — _DOCX제목글 의 HWPX 판('26-09-30 주관 판정 S2: HWPX 도
    스타일 이름이 제목·Title 류면 Word Title 규칙과 같이 — 그 문단은 문서 제목, 첫 제목 스타일부터 절). kordoc 은 '개요 N'
    스타일·개요 문단만 제목으로 내고 이 문단은 보통 문단으로 낸다. 스타일 id 는 header.xml 의 이름으로 찾는다. 못 읽으면 빈 모음.
    PDF 는 스타일 정보가 없어 이 규칙이 없다."""
    try:
        import zipfile
        ET = 자료뿌리.모듈("안전xml")   # 올린 파일 — DTD·엔티티 선언이 있으면 읽기 전에 거절(감사 code F4)
        with zipfile.ZipFile(경로) as z:
            이름들 = z.namelist()
            if "Contents/header.xml" not in 이름들:
                return set()
            ids = {st.get("id") for st in ET.fromstring(z.read("Contents/header.xml")).findall(".//{*}style")
                   if _제목스타일(st.get("name"), st.get("engName"))}
            ids.discard(None)
            if not ids:
                return set()
            out = set()
            for n in sorted(x for x in 이름들 if re.fullmatch(r"Contents/section\d+\.xml", x)):
                for p in ET.fromstring(z.read(n)).findall(".//{*}p"):
                    if p.get("styleIDRef") in ids:
                        글 = _정규("".join(t.text or "" for t in p.findall("{*}run/{*}t")))
                        if 글:
                            out.add(글)
            return out
    except Exception:
        return set()


def _OCR모델있나(환경=None):
    """kordoc 의 OCR 모델(PP-OCRv5: det.onnx·rec_korean.onnx·rec_korean.yml)이 모델 캐시에 있나 — kordoc 의
    ocrModelsCached 와 같은 판정(KORDOC_MODEL_CACHE 또는 ~/.cache/kordoc/models 아래 ppocr/, 크기 0 이 아닌 파일)."""
    뿌리 = _OCR모델자리(환경)
    for 이름 in _OCR모델파일:
        try:
            if not os.path.getsize(os.path.join(뿌리, "ppocr", 이름)):
                return False
        except OSError:
            return False
    return True


_OCR모델파일 = ("det.onnx", "rec_korean.onnx", "rec_korean.yml")


def _OCR모델자리(환경=None):
    """kordoc 모델 캐시 폴더 — KORDOC_MODEL_CACHE, 없으면 그 환경의 HOME 아래 .cache/kordoc/models."""
    e = 환경 if 환경 is not None else os.environ
    return (e.get("KORDOC_MODEL_CACHE") or "").strip() or os.path.join(
        e.get("HOME") or os.path.expanduser("~"), ".cache", "kordoc", "models")


def _OCR모델지문(환경=None):
    """모델 세 파일의 (이름, 크기, 고친 때) — 없는 파일은 None. 읽기 앞뒤로 견줘 kordoc 이 모델을 다시 받았는지 본다."""
    뿌리 = _OCR모델자리(환경)
    out = []
    for 이름 in _OCR모델파일:
        try:
            st = os.stat(os.path.join(뿌리, "ppocr", 이름))
            out.append((이름, st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((이름, None, None))
    return tuple(out)


def _모델다시받음(전, 후, 걸린초):
    """읽기 앞에 모델 파일이 (하나라도) 있었는데 뒤에 바뀌었으면 — kordoc 이 깨진(잘린) 모델을 알아보고 읽는 도중 새로
    받은 것이다('26-09-30 검토자 fv5: rec 모델을 1MB 로 자른 캐시 → 첫 읽기가 45.5초, 주관 판정 K5). 조용히 느려지지 않게
    알린다. 앞에 하나도 없었으면(그림 파일 첫 OCR 때 받기 — 뜻한 동작) 알리지 않는다."""
    if 전 == 후 or all(크기 is None for _, 크기, _ in 전):
        return ""
    바뀐 = [이름 for (이름, *a), (_, *b) in zip(전, 후) if a != b]
    if any(크기 is None for _, 크기, _ in 후):      # 망이 막혀(KORDOC_OFFLINE 등) 깨진 파일을 지우고 못 받았다
        return (f"OCR 모델 파일({'·'.join(바뀐)})이 깨져 있어 kordoc 이 지웠고 다시 받지 못했습니다 — "
                "`kordoc models` 로 다시 받아야 스캔 쪽 OCR 이 됩니다")
    return (f"OCR 모델 파일({'·'.join(바뀐)})이 깨져 있어 kordoc 이 읽는 도중 다시 받았습니다({걸린초:.0f}초 걸림) — "
            "글은 읽었습니다. 망이 막힌 기계라면 다음 읽기부터 OCR 이 안 될 수 있습니다")


def _OCR실패(켠):
    """OCR 켠 json 의 warnings 에서 OCR_FAILED 를 읽는다 → (실행 불가 까닭, {실패 쪽: 까닭}, [글 못 찾은 쪽]).
    kordoc 은 onnxruntime-node 가 없으면 쪽 없는 OCR_FAILED('OCR 실행 불가 …')를, 쪽 OCR 이 터지면 쪽 번호가 든
    OCR_FAILED('페이지 N OCR 실패: …')를, 글을 못 찾으면 'OCR 결과 없음' 을 적고 **글층만** 낸다 — 우리가 안 읽으면 조용한
    빈 글이다(fv5 ⓓ). 까닭 문장에서 서버 경로는 뺀다."""
    실행불가, 실패쪽, 빈쪽 = "", {}, []
    for w in (켠 or {}).get("warnings") or []:
        if not isinstance(w, dict) or w.get("code") != "OCR_FAILED":
            continue
        말 = str(w.get("message") or "")
        n = _쪽번호(w.get("page"))
        # 쪽 번호가 든 실패('페이지 2 OCR 실패: onnxruntime session …')는 그 쪽만의 실패다 — 문장에 'onnxruntime' 이 있다고
        # '실행기 없음'으로 몰면 채운 쪽이 있어도 'N쪽 모두 못 읽음'이 됐다('26-09-30 검토자 fv6 ④ 덤). 꾸러미가 없다는
        # 문장(Cannot find … onnxruntime)만 쪽이 있어도 실행 불가다.
        없는꾸러미 = "onnxruntime" in 말 and ("Cannot find" in 말 or "필요합니다" in 말)
        if (n is None and ("onnxruntime" in 말 or "실행 불가" in 말)) or 없는꾸러미:
            실행불가 = ("OCR 실행기(onnxruntime-node)가 이 기계의 kordoc 설치에 없음" if "onnxruntime" in 말
                     else re.sub(r"(?:/[^\s/'\"]+)+/?", "…", 말)[:80])
        elif "결과 없음" in 말 or "인식하지 못" in 말:
            if n is not None:
                빈쪽.append(n)
        elif n is not None:
            실패쪽[n] = re.sub(r"(?:/[^\s/'\"]+)+/?", "…", 말)[:80]
        else:
            실행불가 = 실행불가 or re.sub(r"(?:/[^\s/'\"]+)+/?", "…", 말)[:80]
    return 실행불가, 실패쪽, sorted(set(빈쪽))


def _OCR안돔(켠, 옛판):
    """OCR 켠 json 을 보고 OCR 이 **아예 돌지 않았나** — OCR_APPLIED·OCR_FAILED 가 있으면 돌았다(4.16.3 은 OCR 을 돌리면 글을
    못 찾아도 OCR_APPLIED 를 적는다, dist parser 에서 읽음). 없을 때 NEEDS_OCR(이미지 PDF 인데 OCR 안 함)가 있거나, 옵션 없이
    다시 부른 옛 kordoc(4.16.2 미만 — 글층 몇 자 + 스캔 쪽을 OCR 하지 않는다, fv6 ① 4.15.4·4.16.0 실측)이면 참."""
    코드 = {w.get("code") for w in (켠 or {}).get("warnings") or [] if isinstance(w, dict)}
    if "OCR_APPLIED" in 코드 or "OCR_FAILED" in 코드:
        return False
    return "NEEDS_OCR" in 코드 or bool(옛판)


# 쪽당 글층 글자가 이 이하이면서 그 쪽에 그림이 있으면 OCR 한다(쪽 번호·'사본'·접수 도장·짧은 캡션·긴 제목 한 줄).
# '26-09-30 실측으로 10 → 29(주관 판정 ② — 19 이상 후보 19·29·49 를 말뭉치 사례·합성으로 잼, fu4/thresh7·ocr7):
#  · 19: 합성 도장 14자 스캔 0→147자·글층 11자 스캔 0→75자·캡션+스캔 표 35→87자, 말뭉치 행정업무운영편람 42쪽 12→509자.
#  · 29: 거기에 워터마크 20자+ 스캔 0→99자·긴 제목+스캔 본문 51→102자가 더해진다. 말뭉치 20~29자+그림 4쪽은 더해진
#    글 0·잃은 줄 0(시간만 든다). 49 는 29 보다 더 읽는 것이 없었다(30~49자+그림 1쪽, 더한 글 0).
#  · 옛 판정(10)의 근거였던 '글꼴 안 심은 글층 15자 + 큰 그림'(korea·ttc·r19 저글층)은 29 에서도 글층 15자·□ 1개가
#    그대로다 — 합치기(_쪽글합치기)가 원래 글층 줄을 잃지 않는다. 글층 20~29자 제목 + 사진 5쪽 덱은 글이 그대로였다.
# '26-09-30 주관 판정 K6 으로 29 → 49: 스캔 쪽의 머리 도장·출력 표지(30·37자)로 쪽 전체를 조용히 잃는 것이 가장 나쁘다
#  (검토자 fv5 B2·B3: 29 에서 0자·경고 없음, 49 에서 126자). 대가였던 '캡션 20자대 + 글자 든 그림 쪽의 그림 속 □ 가 절이 됨'
#  (fv5 B10 절 2→5·B11 1→2)은 합치기가 막는다 — 글층이 있는 쪽에서 OCR 로만 나온 □ 줄은 절 표지로 두지 않는다(_쪽글합치기).
_쪽문턱 = 49

# 스캔 쪽 — 그림이 쪽을 덮는 넓이(쪽 안으로 자른 그림 경계 넓이의 합)가 쪽의 80% 이상인 쪽('26-09-30 주관 판정 S1). 그림
# 작업의 '스캔 쪽' 카드(build/imageasset.py _pdf그림들, N4: 복합기 검색 가능 PDF 는 보이지 않는 OCR 글층이 있고 띠 여러
# 장으로 나뉘어 박히기도 한다)와 **같은 셈·같은 문턱**이다 — 찾는 눈 하나면 돌리는 손도 하나. imageasset 에는 이 셈이 함수로
# 떨어져 있지 않고 _pdf그림들 안에 들어 있어(고치지 않는 파일) 여기 얇게 옮겨 두었다. 한쪽을 바꾸면 다른 쪽도 바꾼다.
# **보정 하나(판정 뒤 잼 — 주관 확인 거리, followups6)**: 넓이만 보면 '쪽 전체 바탕 그림 + 그 위에 보이는 본문 글' 로 만든 문서가
# 스캔이 된다 — 말뭉치 행정업무운영편람_2025.pdf 383쪽 가운데 287쪽(바탕 그림+머리 띠, 보이는 글 245~788자), 재경부
# m56·m57 슬라이드 덱은 모든 쪽. 판정대로 두면 행정업무운영편람 읽기가 72초 → 1,800초(강제 OCR 이 600초 마감에 걸려 '읽지
# 못해' 거짓 경고, 글 537자 줄어듦)였다. 그래서 스캔 쪽은 넓이 80% 이상 **이고** 쪽 몸통(위아래 12% 띠 밖)에 **보이는** 글자
# (texttrace type≠3 — 검색 가능 스캔의 OCR 글층은 보이지 않는 글 type 3)가 _스캔몸글 이하인 쪽이다. 머리 도장·쪽 번호는 위아래
# 띠에 있어 글자 수와 상관없이 스캔으로 남는다(전면 스캔 + 머리 도장 0~120자 합성 11건·검색 가능 스캔·띠 스캔 모두 그대로).
_스캔덮음 = 0.8
_스캔몸글 = 10


def _몸글(pg):
    """쪽 몸통(위아래 12% 띠 밖)에 **보이게** 그린 글자 수(빈칸 빼고). 보이지 않는 글(texttrace type 3 — 검색 가능 스캔의 OCR
    글층)은 세지 않는다. 못 재면 0(넓이만으로 가른다)."""
    try:
        H = pg.rect.height or 1
        n = 0
        for s in pg.get_texttrace():
            if s.get("type") == 3:
                continue
            for ch in s.get("chars") or ():
                bb = ch[3]
                if 0.12 * H < (bb[1] + bb[3]) / 2 < 0.88 * H and chr(ch[0]).strip():
                    n += 1
        return n
    except Exception:
        return 0


def _스캔쪽들(경로, 넓음=None):
    """PDF 에서 스캔 쪽(그림이 쪽의 _스캔덮음 이상을 덮고 몸통에 보이는 글이 _스캔몸글 이하인 쪽) 번호 모음 — PDF 가 아니거나 PyMuPDF 가 없거나 못 열면 빈 모음
    (그러면 옛 판정 _OCR할쪽 그대로). 스캔 쪽은 글층 글자 수와 상관없이 OCR 하고, 그 쪽 OCR 줄(□·○·번호)은 절·항목으로
    올린다(_쪽합치기). 머리 도장·출력 표지 50자 넘는 스캔이 글층만 남아 쪽 전체를 조용히 잃던 것(fv6 ⑤)을 막는다.
    넓음(모음)을 주면 몸글과 상관없이 그림이 _스캔덮음 이상을 덮는 쪽 번호를 거기에 더한다(보정으로 빠진 쪽 — _kordoc 의 '건너뜀' 경고)."""
    if not _PDF인가(경로):
        return set()
    try:
        import fitz
    except ImportError:
        return set()
    out = set()
    try:
        d = fitz.open(경로)
    except Exception:
        return set()
    try:
        if d.needs_pass:                   # 암호 걸린 PDF — 쪽을 열 수 없다(여는 순간 ValueError, fv4 A9 실측). kordoc 이 알린다
            return set()
        for pno in range(len(d)):
            try:
                pg = d[pno]
                쪽넓이 = pg.rect.get_area() or 1
                덮음 = sum((fitz.Rect(i["bbox"]) & pg.rect).get_area() for i in pg.get_image_info()
                         if not (fitz.Rect(i["bbox"]) & pg.rect).is_empty)
            except Exception:
                continue
            if 덮음 >= _스캔덮음 * 쪽넓이 and 넓음 is not None:
                넓음.add(pno + 1)
            if 덮음 >= _스캔덮음 * 쪽넓이 and _몸글(pg) <= _스캔몸글:
                out.add(pno + 1)
    except Exception:
        return out
    finally:
        d.close()
    return out


def _쪽번호(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _OCR할쪽(j, 스캔=(), 넓음=()):
    """OCR 없이 읽은 PDF json 에서 **OCR 로 채울 쪽 번호**(쪽 단위 판정, '26-09-29 판정).

    · **스캔 쪽**(스캔 — _스캔쪽들: 그림이 쪽의 80% 이상을 덮는 쪽) — 글층 글자 수·그림 블록과 상관없이 OCR 한다('26-09-30
      주관 판정 S1). 머리 도장 50·60자 + 스캔 본문이 글층만 남던 것(fv6 ⑤)이다. 글층을 버리지는 않는다(_쪽글합치기).
    · 글층 글자(pageQuality[].textChars)가 _쪽문턱(49자) 이하이고 **그 쪽에 그림 블록이 있는** 쪽 — 스캔 위에
      쪽 번호·'사본'·접수 도장만 글층으로 찍힌 쪽이다. 예전엔 1자라도 있으면 지켜서 그런 스캔이 통째로 0자가
      됐다('26-09-29 검토자 Q2 쪽 번호 3자·Q3 '사본' 2자: HEAD 119자 → 0자).
    · 글층이 **0자**인 쪽 — 문서에 그림 블록이 하나라도 있으면 OCR 한다(그 쪽에 그림 블록이 없어도).
      kordoc 은 스캔 쪽 그림을 블록으로 다 내지 않는다: 쉬운공문서쓰기길잡이_2022 는 0자 92쪽 가운데 그림 블록이
      있는 쪽이 4쪽뿐인데 OCR 하면 글이 5만 자 넘게 되살아나고, 같은 그림이 되풀이되면 블록을 한 번만 내며
      (스캔 10쪽 합성에서 1개), 윤곽선으로 바꾼 글자 쪽은 그림도 글층도 없다('26-09-29 잼).
    글층 글자를 **출력 글(쪽 markdown)이 아니라 textChars** 로 세는 것은 겹침 때문이다 — kordoc 은 어떤 쪽의
    글을 다른 쪽 markdown 에 합쳐 내기도 해서(대통령비서실 요약2: textChars 557~893 인 8쪽이 쪽 markdown 0자),
    출력 글로 세면 그 쪽들을 OCR 해 이미 있는 글 6천여 자가 한 번 더 들어간다(검토자 실측).
    pageQuality 가 없으면 pages[].markdown 의 실글자로 센다(pages 에 없는 쪽 = 0자). 그림 블록이 하나도 없는
    문서는 OCR 할 것이 없다(빈 쪽뿐 — 스캔 쪽이 있으면 그림이 있는 문서다). markdown·json·chunks 가 모두 이 판정을 쓴다.
    json 에 없는 쪽 번호의 스캔은 뺀다."""
    if not isinstance(j, dict):
        return []
    스캔 = set(스캔 or ())
    # 넓음(그림이 쪽의 80% 이상을 덮는 쪽, _스캔쪽들)도 그림 쪽으로 본다 — kordoc 은 같은 그림이 되풀이되면 블록을 한 번만 내서
    # 둘째 쪽부터의 전면 그림 + 출력 표지 24자 쪽이 대상에서 빠졌다('26-10-01 fx10 잼, fv7 ① 꼴 두 쪽 중 1쪽만)
    그림쪽 = {_쪽번호(b.get("pageNumber")) for b in j.get("blocks") or []
            if isinstance(b, dict) and b.get("type") == "image"} | set(넓음 or ())
    if not 그림쪽 and not 스캔:
        return []
    품질 = [(_쪽번호(q.get("page")), q.get("textChars") or 0) for q in j.get("pageQuality") or [] if isinstance(q, dict)]
    품질 = [(n, t) for n, t in 품질 if n is not None and isinstance(t, (int, float))]
    if not 품질:
        쪽수 = j.get("pageCount") or (j.get("metadata") or {}).get("pageCount") or 0
        글 = {_쪽번호(p.get("pageNumber")): _실글자(p.get("markdown")) for p in j.get("pages") or [] if isinstance(p, dict)}
        품질 = [(n, 글.get(n, 0)) for n in range(1, int(쪽수) + 1)]
    return sorted({n for n, t in 품질 if n in 스캔 or not t or (t <= _쪽문턱 and n in 그림쪽)})


def _쪽목록(쪽들):
    """[2,3,4,7] → '2~4·7쪽' (길면 앞 몇 묶음만)."""
    묶음, 쪽들 = [], sorted(쪽들)
    for n in 쪽들:
        if 묶음 and n == 묶음[-1][1] + 1:
            묶음[-1][1] = n
        else:
            묶음.append([n, n])
    글 = [f"{a}~{b}" if a != b else f"{a}" for a, b in 묶음]
    return "·".join(글[:6]) + ("…" if len(글) > 6 else "") + "쪽"


def _정규(s):
    """겹침 판정용 — 그림 참조·태그·기호·공백을 뺀 글(한글·영문·숫자)."""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", str(s or ""))
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s)


_그림줄 = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")


# 줄 머리 표지 — □·○·-·※·'1.'·'가.'·①·Ⅱ (앞의 마크다운 '#'·'- ' 는 건너 읽는다)
_표지머리 = re.compile(r"^\s*(?:#{1,6}\s+)?(?:[-*]\s+(?=\S))?"
                    r"([□■◇◆▣○●◦・·※*\-–]|\d{1,3}\s*[.)]|[가-하]\s*[.)]|[①-⑳]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)")


def _머리(줄):
    m = _표지머리.match(str(줄 or ""))
    return re.sub(r"\s", "", m.group(1)) if m else ""


def _머리떼기(ocr줄):
    """OCR 줄의 머리 표지(□·○·'1.' 과 OCR 이 □ 를 읽은 'ㅁ'·'口' 같은 잡음, 마크다운 '#')를 뗀다 — 원래 글층 줄을 그 앞에
    표지째 남길 때, 같은 표지가 두 번 들어 절·항목이 늘지 않게 한다('26-09-30 K7)."""
    s = re.sub(r"^\s*(?:#{1,6}\s+)?", "", str(ocr줄 or ""))
    m = _표지머리.match(s)
    if m:
        s = s[m.end():]
    return re.sub(r"^[^0-9A-Za-z가-힣]*", "", s).strip()


def _글층대조(k, 머, 정들, ocr들, 쓴):
    """원래 글층 줄(정규 글 k, 머리 표지 머)이 **같은 쪽** OCR 줄들(정규 정들)에 어떻게 들었나('26-09-29 주관 판정 — 원래
    글층 줄을 잃지 않는다, '26-09-30 K7 — 잃는 것이 겹치는 것보다 나쁘다). →
      ('같음', j)  같은 줄(아직 안 쓴 것)이 있다 — 그 OCR 줄을 원래 줄로 바꿔 끼운다(표지·띄어쓰기는 글층이 맞다)
      ('덮임', -1) 표지 없는 줄이 OCR 글에 이미 들었다 — 다시 넣지 않는다
      ('앞둠', j)  OCR 줄 j 가 이 줄 글로 시작하고 더 길다(OCR 이 뒷 줄과 이었거나 글층이 잘렸다) — 원래 줄을 표지째 j 바로
                   앞에 두고 j 의 머리 표지는 뗀다(같은 표지가 두 번 들지 않게). 예전엔 j 에 원래 표지를 되붙여 원래 줄이
                   제 줄로 남지 않았고 절 이름이 '추진 배경 처리 기간이 길다' 가 됐다('26-09-30 검토자 fv6 K7 M3·M8)
      ('남김뒤', j) 표지 있는 줄의 글이 OCR 줄 j 의 **가운데**에 들었거나(OCR 이 앞 줄과 이음) j 가 이미 다른 원래 줄
                   몫이다(같은 줄 두 번) — 원래 줄을 표지째 j 바로 뒤에 넣는다(글이 겹치는 것은 감수. j 가 남의 몫이면
                   _대조판 이 이웃 원래 줄 자리에 둔다)
      ('남김앞', j) OCR 이 이 줄을 갈랐다(j 가 이 줄 글의 앞부분) — 원래 줄을 표지째 j 바로 앞에 넣는다
      ('남김', -1) 같은 쪽 OCR 글에 없다 — 원래 줄을 제자리(그림 앞·뒤)에 덧붙인다.
    예전엔 표지를 뺀 글자만 대조해 '□ 기록물' 을 OCR 의 '기록물' 로 보고 버려 사진덱 □ 5줄이 0줄이 됐고('26-09-29 검토자
    A6·A13), 이은 줄('□ 추진 배경' + '○ 처리 기간이 길다' → OCR 한 줄)의 ○ 줄·같은 ○ 줄 두 번 가운데 하나·갈린 □ 줄의
    절 이름을 잃었다(fv5 U1·U3·U4). **다른 쪽** OCR 글에 같은 말이 있다고 버리던 규칙(몰린 줄 두 번 막기)은 표지 없는
    제목을 잃게 해서(fv5 B5 '사업 개요') 없앴다 — 몰린 줄은 두 번 들 수 있다(K7: 겹침 감수)."""
    for j, s in enumerate(정들):
        if s == k and j not in 쓴:
            return "같음", j
    if k not in "".join(정들):
        return "남김", -1
    if not 머:
        return "덮임", -1
    for j, s in enumerate(정들):
        if s and s.startswith(k) and j not in 쓴:
            return "앞둠", j
    for j, s in enumerate(정들):
        if s and k in s:
            return "남김뒤", j
    for j, s in enumerate(정들):
        if s and k.startswith(s):
            return "남김앞", j
    return "남김", -1


_절표지 = "□■◇◆▣"


def _절머리(줄):
    """서식분석이 절로 세는 머리인가 — □ 계열, 그리고 번호('1.'·'2)')."""
    머 = _머리(줄)
    return bool(머) and (머 in _절표지 or bool(re.fullmatch(r"\d{1,3}[.)]", 머)))


def _셈머리(줄):
    """서식분석이 절·항목으로 세는 머리인가 — _절머리(□ 계열·번호)와 ○ 계열 항목 표지. ○ 계열은 서식분석 '하위' 와 같은
    꼴이다: 같은 글자가 곧바로 이어지는 '○○공사'·'ㅇㅇ' 익명 표기는 표지가 아니다('26-09-30 주관 판정 S1)."""
    if _절머리(줄):
        return True
    s = re.sub(r"^\s*(?:#{1,6}\s+)?(?:[-*]\s+(?=\S))?", "", str(줄 or ""))
    return bool(re.match(r"([○●◦・·ㅇ])(?!\1)\s*\S", s))


def _강등(글):
    """글층이 있는 쪽에서 OCR 로만 나온 □·번호·○ 줄('#### □ 안전 점검의 날'·'1. 추진 배경'·'○ 창구를 모은다' — 사진 속
    현수막·견본 화면 글)을 인용 줄로 둔다('> □ 안전 점검의 날'). 글은 그대로 두되 서식분석이 절·항목으로 세지 않는다(K6 —
    fv5 B10 절 2→5·B11 1→2, '26-09-30 검토자 fv6 ⑥ 번호 꼴 K6n2 절 2→5, 주관 판정 S1: ○ 줄도 — K6n2 항목 [1,3]·B10 [2,5]).
    스캔 쪽(_스캔쪽들)은 글층이 있어도 여기에 오지 않는다 — 그 쪽 OCR 줄은 절·항목으로 올린다(_쪽합치기).
    '-'·'※' 줄(3·4단 항목)은 판정 범위(번호·○) 밖이라 두었다."""
    return "> " + re.sub(r"^\s*(?:#{1,6}\s+)?", "", str(글 or "")).strip()


def _대조판(원들, ocr들, 글층있음):
    """합치기 한 쪽 — 원들: 원래 글층 줄(블록)의 글 차례(None = 그림), ocr들: 같은 쪽 OCR 줄(블록) 글.
    → (바꿈 {j: ('같음'|'떼기', i)}, 넣기 [(i, '앞'|'뒤'|('앞붙'|'뒤붙', j))] — i 차례, 강등 {j}).
    '같음' 은 OCR 줄 j 를 원래 줄 i 로 바꿔 끼우고, '떼기' 는 j 의 머리 표지를 뗀다(원래 줄은 넣기로 j 앞에 든다).
    정확히 같은 줄을 **먼저 모두** 짝짓는다 — 원래 줄을 차례로 보면 앞의 짧은 줄('○ 기간')이 뒷줄 몫 OCR 줄('○ 기간 연장
    검토')을 먼저 차지해, 뒷줄이 짝을 못 찾아 두 번 들고 앞 줄은 사라졌다('26-09-30 검토자 fv6 ⑪ M1·M2). 남의 몫이 된 OCR
    줄 가운데에 든 원래 줄은 이웃 원래 줄(앞 줄, 없으면 뒷줄)의 짝 곁에 두어 원래 차례를 지킨다."""
    정들 = [_정규(x) for x in ocr들]
    원문 = "\n".join(ocr들)
    쓴, 바꿈, 넣기, 그림뒤 = set(), {}, [], False
    줄들 = []                                        # (i, 원래 줄, 정규 글, 제자리)
    for i, t in enumerate(원들):
        if t is None:
            그림뒤 = True
            continue
        s = str(t).strip()
        if not s:
            continue
        제자리 = "뒤" if 그림뒤 else "앞"
        k = _정규(s)
        if not k:                                   # 기호만인 줄도 OCR 글에 없으면 남긴다
            if s not in 원문:
                넣기.append((i, 제자리))
            continue
        줄들.append((i, s, k, 제자리))
    닻 = {}                                          # 원래 줄 i → 짝이 된 OCR 줄 j
    for i, s, k, _ in 줄들:                          # 1차: 정확히 같은 줄
        for j, x in enumerate(정들):
            if x == k and j not in 쓴:
                바꿈[j] = ("같음", i)
                쓴.add(j)
                닻[i] = j
                break
    남의몫 = []
    for i, s, k, 제자리 in 줄들:
        if i in 닻:
            continue
        how, j = _글층대조(k, _머리(s), 정들, ocr들, 쓴)
        if how == "같음":
            바꿈[j] = ("같음", i)
            쓴.add(j)
            닻[i] = j
        elif how == "앞둠":
            바꿈[j] = ("떼기", i)
            쓴.add(j)
            닻[i] = j
            넣기.append((i, ("앞붙", j)))
        elif how == "남김":
            넣기.append((i, 제자리))
        elif how == "남김뒤" and j in 쓴:
            남의몫.append((i, 제자리))
        elif how in ("남김뒤", "남김앞"):
            넣기.append((i, ("뒤붙" if how == "남김뒤" else "앞붙", j)))
    for i, 제자리 in 남의몫:
        앞 = [x for x in 닻 if x < i]
        뒤 = [x for x in 닻 if x > i]
        넣기.append((i, ("뒤붙", 닻[max(앞)]) if 앞 else ("앞붙", 닻[min(뒤)]) if 뒤 else 제자리))
    넣기.sort(key=lambda x: x[0])
    강등 = {j for j, x in enumerate(ocr들) if j not in 쓴 and _셈머리(x)} if 글층있음 else set()
    return 바꿈, 넣기, 강등


def _네모올림(글):
    """스캔 쪽 OCR 줄 머리의 'ㅁ'·'口'(OCR 이 □ 를 읽은 꼴 — '# ㅁ민원 추진 배경')를 □ 로 되돌린다('26-09-30 판정 S1: 스캔 쪽
    OCR 줄은 □ 절로 올린다 — 4.16.3 --ocr-force 가 전면 스캔의 □ 5줄을 모두 'ㅁ' 으로 읽어 절이 0 이었다). 줄 머리의 낱자모
    'ㅁ' 뒤에 한글 음절이 오는 꼴만 고친다(정밀도 우선 — 글층 글과 스캔 아닌 쪽은 건드리지 않는다)."""
    return re.sub(r"^(\s*(?:#{1,6}\s+)?)[ㅁ口](?=\s*[가-힣])", r"\1□", str(글 or ""))


def _탭가름(글):
    """스캔 쪽 OCR 줄에서 **탭 뒤가 □·○·번호 표지로 시작하면** 거기서 줄을 가르고 조각마다 _네모올림 한다('26-10-01 검토자 fv7
    ⑤: kordoc --ocr-force 가 같은 높이의 두 줄(좌우로 나뉜 스캔)을 탭으로 이어 절 이름이 '민원 추진 배경\\tㅁ민원 개선 과제'
    가 되고 절이 하나 줄었다). 탭 뒤가 표지가 아니면('□ 추진 배경\\t○○공사 기획처 2026.09.30' 같은 도장 줄, '재정경제부\\t10'
    같은 표 꼴 줄) 가르지 않는다 — 정밀도 우선. '○○공사'·'ㅇㅇ' 익명 표기는 표지가 아니다(_셈머리)."""
    조각 = str(글 or "").split("\t")
    out = [조각[0]]
    for x in 조각[1:]:
        if x.strip() and _셈머리(_네모올림(x.strip())):
            out.append(x.strip())
        else:
            out[-1] += "\t" + x
    return "\n\n".join(_네모올림(x) for x in out)


def _쪽글합치기(원, ocr, 글층있음=None, 네모=False):
    """OCR 로 읽은 쪽 글(ocr)을 바탕으로 **원래 글층 줄을 하나도 잃지 않게** 합친다(_글층대조): 같은 줄은 원래 줄로
    바꿔 끼우고, OCR 이 뒷 줄과 이어 읽은 줄은 원래 줄을 표지째 그 앞에 두고(OCR 줄 표지는 뗀다), OCR 글에 없는 줄은
    제자리(그림 앞·뒤)에, OCR 이 잇거나 가른 표지 줄은 그 OCR 줄 곁에 표지째 덧붙인다. OCR 이 이미 똑같이 읽은 줄은 다시
    넣지 않는다. 글층이 있는 쪽(글층있음 — 안 주면 원래 글에 실글자가 있나로 본다)에서 OCR 로만 나온 □·번호·○ 줄은 절·항목
    표지로 두지 않는다(_강등). 네모(스캔 쪽)면 OCR 로만 나온 줄 머리의 'ㅁ' 을 □ 로 되돌린다(_네모올림)."""
    조각 = re.split(r"(\n+)", str(ocr or "").strip())
    자리 = list(range(0, len(조각), 2))            # 짝수 칸이 줄, 홀수 칸이 줄바꿈
    ocr들 = [조각[i] for i in 자리]
    원들 = [None if _그림줄.match(줄) else 줄 for 줄 in re.split(r"\n+", str(원 or ""))]
    if 글층있음 is None:
        글층있음 = _실글자(원) > 0
    바꿈, 넣기, 강등 = _대조판(원들, ocr들, 글층있음)
    for j in 강등:
        조각[자리[j]] = _강등(조각[자리[j]])
    if 네모:
        for j in range(len(자리)):
            if j not in 바꿈 and j not in 강등:
                조각[자리[j]] = _탭가름(조각[자리[j]])      # 머리 'ㅁ' → □, 탭으로 이은 표지 줄은 가른다
    for j, (how, i) in 바꿈.items():
        s = 원들[i].strip()
        조각[자리[j]] = s if how == "같음" else _머리떼기(조각[자리[j]])
    앞, 뒤, 곁 = [], [], {}
    for i, 곳 in 넣기:
        s = 원들[i].strip()
        if 곳 == "앞":
            앞.append(s)
        elif 곳 == "뒤":
            뒤.append(s)
        else:
            곁.setdefault(곳[1], ([], []))[0 if 곳[0] == "앞붙" else 1].append(s)
    for j, (a, b) in 곁.items():
        조각[자리[j]] = "\n\n".join([*a, 조각[자리[j]], *b])
    return "\n\n".join(x for x in [*앞, "".join(조각).strip(), *뒤] if x)


def _켠잇기(a, b):
    """OCR 켠 json 두 벌(자동으로 읽은 쪽들·--ocr-force 로 읽은 스캔 쪽들)을 하나로 — 쪽·블록·경고·쪽 품질을 잇는다.
    두 벌은 서로 다른 쪽이라 겹치지 않는다(_쪽합치기 는 쪽 번호로 골라 쓴다)."""
    out = dict(a)
    for k in ("pages", "blocks", "warnings", "pageQuality"):
        out[k] = list(a.get(k) or []) + list(b.get(k) or [])
    return out


def _쪽합치기(끈, 켠, 쪽들, 스캔=()):
    """OCR 없이 읽은 json(끈)의 OCR 대상 쪽 자리에 OCR 로 읽은 json(켠)의 같은 쪽을 합친다 → (json, 채운 쪽 집합).
    OCR 이 글을 못 찾은 쪽은 끈 그대로 둔다. 채운 쪽의 원래 글층 줄(블록)은 OCR 글에 없을 때만 남긴다.
    스캔(_스캔쪽들)에 든 쪽은 글층이 있어도 '글층 없는 쪽' 으로 합친다 — 그 쪽 OCR 줄(□·○·번호)은 인용으로 내리지 않고
    절·항목으로 올린다('26-09-30 주관 판정 S1: 머리 도장만 글층인 스캔의 본문 구성이 스캔 쪽의 몫이다)."""
    쪽들 = set(쪽들)
    스캔 = set(스캔 or ())
    켠쪽 = {}
    for p in (켠 or {}).get("pages") or []:
        n = _쪽번호(p.get("pageNumber")) if isinstance(p, dict) else None
        if n in 쪽들 and _실글자(p.get("markdown")):
            켠쪽[n] = p
    if not 켠쪽:
        return 끈, set()
    끈쪽 = {_쪽번호(p.get("pageNumber")): p for p in 끈.get("pages") or [] if isinstance(p, dict)}
    # 글층이 있는 쪽(OCR 끈 json 의 textChars > 0, 없으면 그 쪽 글) — 거기서 OCR 로만 나온 □·번호·○ 줄은 절·항목 표지로 두지
    # 않는다(K6·S1). 스캔 쪽은 글층이 있어도 여기서 빠진다(S1)
    글자 = {_쪽번호(q.get("page")): q.get("textChars") for q in 끈.get("pageQuality") or [] if isinstance(q, dict)}
    글층 = {n: n not in 스캔 and (bool(글자[n]) if isinstance(글자.get(n), (int, float))
                                 else _실글자((끈쪽.get(n) or {}).get("markdown")) > 0)
           for n in 켠쪽}
    새쪽 = {n: dict(p, pageNumber=n, markdown=_쪽글합치기((끈쪽.get(n) or {}).get("markdown"), p.get("markdown"), 글층[n],
                                                      n in 스캔))
           for n, p in 켠쪽.items()}
    # 합쳐도 글이 그대로인 쪽은 채우지 않는다 — 모델 캐시가 없으면 OCR 켠 읽기가 글층만 돌려줘 같은 글로 '채워' 졌고,
    # 그러면 chunks 가 쪽 조각 하나로 바뀌어 캐시 유무에 따라 조각 모양이 달라졌다(fu4 r19 저글층 chunks, 문턱 29).
    새쪽 = {n: p for n, p in 새쪽.items() if _정규(p.get("markdown")) != _정규((끈쪽.get(n) or {}).get("markdown"))}
    if not 새쪽:
        return 끈, set()
    j = dict(끈)
    쪽 = [p for p in 끈.get("pages") or [] if not (isinstance(p, dict) and _쪽번호(p.get("pageNumber")) in 새쪽)]
    쪽 = sorted(쪽 + list(새쪽.values()), key=lambda p: (_쪽번호(p.get("pageNumber")) or 0) if isinstance(p, dict) else 0)
    j["pages"] = 쪽
    # kordoc 의 markdown 은 쪽 markdown 을 빈 줄로 이은 것이다(글은 말뭉치 51건 모두 같고, 17건은 쪽 사이 빈 줄 수만 다르다)
    j["markdown"] = "\n\n".join(str(p.get("markdown") or "") for p in 쪽 if isinstance(p, dict))

    def _블쪽(b):
        return _쪽번호(b.get("pageNumber")) if isinstance(b, dict) else None
    묶음, 앞쪽 = {}, 0
    for b in 끈.get("blocks") or []:
        n = _블쪽(b)
        앞쪽 = 앞쪽 if n is None else n        # 쪽 없는 블록은 앞 블록의 쪽에 붙인다(자리 유지)
        묶음.setdefault(앞쪽, []).append(b)
    for n in 새쪽:                           # 블록도 쪽 글과 같은 규칙(_글층대조)으로 — 원래 글층 블록을 잃지 않는다
        켠블 = [b for b in 켠.get("blocks") or [] if _블쪽(b) == n]
        ocr들 = [str(b.get("text") or "") if isinstance(b, dict) else "" for b in 켠블]
        원블 = 묶음.get(n, [])
        원들 = [None if isinstance(b, dict) and b.get("type") == "image"
               else (str(b.get("text") or "") if isinstance(b, dict) else "") for b in 원블]
        바꿈, 넣기, 강등 = _대조판(원들, ocr들, 글층[n])
        for 곳 in 강등:
            켠블[곳] = dict(켠블[곳], text=_강등(ocr들[곳]))
        if n in 스캔:                        # 스캔 쪽 OCR 만의 블록 머리 'ㅁ' → □(_네모올림, 판정 S1)
            for 곳 in range(len(켠블)):
                if 곳 not in 바꿈 and 곳 not in 강등 and isinstance(켠블[곳], dict) and _네모올림(ocr들[곳]) != ocr들[곳]:
                    켠블[곳] = dict(켠블[곳], text=_네모올림(ocr들[곳]))
        for 곳, (how, i) in 바꿈.items():
            켠블[곳] = 원블[i] if how == "같음" else dict(켠블[곳], text=_머리떼기(ocr들[곳]))
        앞, 뒤, 곁 = [], [], {}
        for i, 곳 in 넣기:
            if 곳 == "앞":
                앞.append(원블[i])
            elif 곳 == "뒤":
                뒤.append(원블[i])
            else:
                곁.setdefault(곳[1], ([], []))[0 if 곳[0] == "앞붙" else 1].append(원블[i])
        묶음[n] = 앞 + [x for 곳, b in enumerate(켠블) for x in (*곁.get(곳, ([], []))[0], b, *곁.get(곳, ([], []))[1])] + 뒤
    j["blocks"] = [b for n in sorted(묶음) for b in 묶음[n]]
    if isinstance(끈.get("pageQuality"), list):
        새품질 = {_쪽번호(q.get("page")): q for q in 켠.get("pageQuality") or [] if isinstance(q, dict)}
        j["pageQuality"] = [새품질.get(_쪽번호(q.get("page")), q)
                          if isinstance(q, dict) and _쪽번호(q.get("page")) in 새쪽 else q for q in 끈["pageQuality"]]
    return j, set(새쪽)


def _쪽채우기_json(끈, 켠, 쪽들):
    """json 판 — _쪽합치기 의 json 만."""
    return _쪽합치기(끈, 켠, 쪽들)[0]


def _쪽채우기_chunks(끈, 끈json, 합, 채운):
    """chunks 판 — OCR 없이 읽은 조각에서 **채운 쪽의 몫만** 떼어 내고, 채운 쪽마다 합친 쪽 글(합 json 의 쪽
    markdown — markdown·json 과 같은 글)로 조각 하나를 만들어 **쪽 차례대로** 끼운다.

    조각은 쪽 경계를 넘는다(스캔 2쪽 그림 + 3쪽 글이 한 조각). 그래서 조각의 blockRange 로 같은 OCR 끈 json 의
    블록 쪽을 보고, 조각 글을 블록 수만큼 빈 줄로 나눌 수 있으면 채운 쪽 부분만 버리고 남은 부분을 쪽마다 조각으로
    가른다. 못 나누면 채운 쪽 블록의 글·그림 참조만 떼어 낸다. 예전엔 OCR 을 chunks 로(-p 2,5,6) 읽어 조각 하나에
    세 쪽 글이 몰려 차례가 [1,2,5,6,3,4] 가 됐다('26-09-29 검토자 Q12)."""
    목록 = [c for c in (끈 if isinstance(끈, list) else (끈 or {}).get("chunks") or []) if isinstance(c, dict)]
    if not 채운:
        return 끈
    블록 = [b if isinstance(b, dict) else {} for b in (끈json or {}).get("blocks") or []]

    def 블쪽(k):
        return _쪽번호(블록[k].get("pageNumber"))
    새, 차례 = [], 0

    def 넣기(n, c):
        nonlocal 차례
        새.append((n if n is not None else 0, 차례, c))
        차례 += 1
    앞쪽 = 0
    for c in 목록:
        rng = c.get("blockRange")
        if not (isinstance(rng, list) and len(rng) == 2 and all(isinstance(x, int) for x in rng)
                and 0 <= rng[0] <= rng[1] < len(블록)):
            n = _쪽번호(c.get("page"))
            앞쪽 = 앞쪽 if n is None else n
            if 앞쪽 not in 채운:
                넣기(앞쪽, c)
            continue
        ks = list(range(rng[0], rng[1] + 1))
        쪽들 = []
        for k in ks:
            n = 블쪽(k)
            앞쪽 = 앞쪽 if n is None else n
            쪽들.append(앞쪽)
        if not any(n in 채운 for n in 쪽들):
            넣기(쪽들[0], c)
            continue
        부분 = [x for x in re.split(r"\n\s*\n", str(c.get("text") or "")) if x.strip()]
        if len(부분) == len(ks):
            무리 = []                                   # [(쪽, [블록 번호], [글])]
            for k, n, t in zip(ks, 쪽들, 부분):
                if n in 채운:
                    continue
                if 무리 and 무리[-1][0] == n:
                    무리[-1][1].append(k)
                    무리[-1][2].append(t)
                else:
                    무리.append((n, [k], [t]))
            for n, kk, ts in 무리:
                넣기(n, dict(c, text="\n\n".join(ts), page=n, blockRange=[kk[0], kk[-1]]))
            continue
        글 = str(c.get("text") or "")
        for k, n in zip(ks, 쪽들):
            if n not in 채운:
                continue
            t = str(블록[k].get("text") or "")
            if t:
                글 = 글.replace(f"![image]({t})" if 블록[k].get("type") == "image" else t, "", 1)
        글 = re.sub(r"\n{3,}", "\n\n", 글).strip()
        남은쪽 = [n for n in 쪽들 if n not in 채운]
        if 글 and 남은쪽:
            넣기(남은쪽[0], dict(c, text=글, page=남은쪽[0]))
    for p in (합 or {}).get("pages") or []:
        n = _쪽번호(p.get("pageNumber")) if isinstance(p, dict) else None
        if n in 채운:
            넣기(n, {"id": "", "type": "text", "breadcrumb": [], "text": str(p.get("markdown") or ""), "page": n})
    합조각 = [c for _, _, c in sorted(새, key=lambda t: (t[0], t[1]))]
    합조각 = [dict(c, id=f"c{i + 1:04d}") if "id" in c else c for i, c in enumerate(합조각)]
    if isinstance(끈, dict):
        return dict(끈, chunks=합조각)
    return 합조각


def _실글자(md):
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md or "")
    md = re.sub(r"<[^>]+>", "", md)            # 표를 HTML 로 낸 것(<table><td>…)의 태그는 글이 아니다
    return len(re.sub(r"[\s|#*>\-–—:]+", "", md))


@등록("파일읽기", ["경로", "형식"], 읽기=False,
    설명="올린 파일에서 내용을 뽑는다(HWP·HWPX·PDF·XLSX·DOCX·이미지 OCR)", en="readfile")
def 파일읽기(경로, 형식="markdown"):
    안 = os.path.abspath(자료뿌리.받은것뿌리())
    참 = os.path.abspath(경로 if os.path.isabs(경로) else os.path.join(안, 경로))
    # 올린 파일만 읽는다 — 경로를 받아 아무 데나 읽으면 서버의 모든 파일이 열린다
    if not 참.startswith(안 + os.sep):
        return {"ok": False, "로그": "올린 파일만 읽을 수 있습니다"}
    if not os.path.exists(참):
        return {"ok": False, "로그": f"파일이 없습니다: {os.path.basename(참)}"}
    # 파일 속 XML 에 DTD·엔티티 선언이 있으면 읽기 전에 거절한다('26-10-01 감사 code F4) — kordoc·서식분석이 같은 말로 멈춘다
    _위험 = 자료뿌리.모듈("안전xml").파일검사(참)
    if _위험:
        return {"ok": False, "로그": _위험}
    if os.path.dirname(참) == 안:
        _대화그림적기(os.path.basename(참))      # 이 대화에서 읽은 자료 — 그림 목록 범위에 든다(_그림범위)
    # 사진 파일은 OCR 로 읽지 않는다('26-09-30 주관 판정 ⑥) — 간판·번호판·이름표·화면 글자가 자료 원문에 실려 사실로 읽혔다.
    # 스캔 쪽·글 그림(카드 종류가 사진이 아닌 것)은 그대로 OCR 한다. 카드를 못 만들면(도구 없음) 전처럼 읽는다.
    _사진 = False
    if os.path.dirname(참) == 안:
        try:
            _사진 = 자료뿌리.모듈("imageasset").사진파일인가(os.path.basename(참), _그림카드들(전부=True))
        except Exception as _e:
            print(f"[그림] 사진 판정 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    if _사진:
        본, 탈 = "(사진 — 사진 속 글자는 자료로 읽지 않습니다)", ""
    else:
        본, 탈 = _kordoc(참, 형식)
    if 본 is None:
        # 그림 도구가 없거나 깨져 사진 파일을 카드로도 못 만들고 OCR 도 못 했으면 까닭 한 줄('26-10-01 주관 판정 S2)
        _도 = ""
        if os.path.dirname(참) == 안:
            try:
                _도 = " ".join(자료뿌리.모듈("imageasset").못쓴줄들({os.path.basename(참)}))
            except Exception:
                _도 = ""
        return {"ok": False, "로그": (탈 or "") + (("\n" + _도) if _도 else ""), **({"그림안내": _도} if _도 else {})}
    r = {"ok": True, "값": 본, "파일": os.path.basename(참)}
    if _사진:
        r["안내"] = "사진이라 사진 속 글자(OCR)를 자료 원문에 싣지 않았습니다 — 그림은 아래 '그림' 칸의 id 로 씁니다"
    if 탈:
        r["경고"] = 탈              # 읽긴 했지만 빠진 것이 있다(스캔 쪽 OCR 실패·시간 초과 — _kordoc)
    # 이 파일에서 꺼낸 그림 카드('26-09-30) — 글 읽기와 함께 만든다(받은 자료 폴더 _그림/, 세션 방 안).
    # 글에 남는 ![image](…) 자국은 가리키는 파일이 없다 — 그림은 이 id 로만 쓴다.
    if os.path.dirname(참) == 안:
        try:
            _카 = [c for c in _그림카드들(전부=True) if c.get("파일") == os.path.basename(참)
                  or os.path.basename(참) in " ".join(c.get("또있음") or [])]
            if _카:
                r["그림"] = [{k: c[k] for k in ("id", "자리", "종류", "쓸수있음", "까닭", "곁글", "비밀표지") if k in c}
                            for c in _카]
                # 한글·워드 문서 속 사진은 쓰지 않는다(P1) — 사람 말 한 줄(웹앱 자료 칸이 그대로 보인다, P2). 짝 찾기(같은 사진을
                # 따로 올림·같은 문서의 PDF — Q4)는 이 대화·세션의 범위 카드로, 알리는 것은 이 파일 하나
                _범 = _그림카드들()
                _있 = {(c.get("파일"), json.dumps(c.get("자리"), sort_keys=True)) for c in _범}
                _범 = _범 + [c for c in _카 if (c.get("파일"), json.dumps(c.get("자리"), sort_keys=True)) not in _있]
                _그범 = _그림범위()
                _그범 = (자료뿌리.모듈("imageasset")._받은파일들() if _그범 is None else set(_그범) | {os.path.basename(참)})
                _안 = 자료뿌리.모듈("imageasset").문서사진말(_범, 파일={os.path.basename(참)}, 범위=_그범)
                if _안:
                    r["그림안내"] = _안
                if _안 and _CLI표면():
                    # CLI 는 대화를 몰라 짝(같은 문서의 PDF)을 이 파일 카드로만 센다('26-10-01 주관 판정 R5). 에이전트에게만 하는
                    # 말은 그림안내에 붙이지 않고 '에이전트' 칸으로 뗀다('26-10-01 주관 판정 S4 — 그대로 옮기면 사용자에게 에이전트
                    # 말이 보였다). 새문서·저장에 자료파일(source_files)을 넘기면 확인할것의 사진 줄이 문서 전체로 선다(S3)
                    r["에이전트"] = ("그림안내는 이 파일만 보고 센 값입니다(CLI 는 대화를 기억하지 않습니다). 새문서(new)·저장(save)에 "
                                  "읽은 자료 파일 이름을 모두 자료파일(source_files)로 넘기면 확인할것의 사진 줄이 문서 전체로 섭니다 — "
                                  "끝 보고에는 그 확인할것 줄을 옮기고, 사진 줄이 없을 때만 이 그림안내를 옮기세요. 이 칸은 사용자에게 "
                                  "옮기지 않습니다.")
        except Exception as _e:
            print(f"[그림] 파일읽기 카드 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
        if not r.get("그림안내"):
            # 그림 도구가 없거나 깨져 이 사진 파일을 쓸 수 없다('26-10-01 주관 판정 S2) — 카드가 없어도 사람에게 알린다
            try:
                _도 = " ".join(자료뿌리.모듈("imageasset").못쓴줄들({os.path.basename(참)}))
                if _도:
                    r["그림안내"] = _도
            except Exception as _e:
                print(f"[그림] 그림 도구 안내 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
        if os.environ.get("문서지능_웹앱") and _그림범위() is None:
            # 웹앱 자료 칸('26-10-01 주관 판정 R4, verify_fixup5_ux B3) — 올릴 때마다 이 세션의 올린 파일 전체로 한글·워드 문서
            # 줄을 다시 셈해 {파일: 말('' 이면 줄을 지운다)} 로 준다. app.html 이 앞서 올린 줄까지 갈아 끼운다(순서 무관 —
            # 한글 문서를 먼저 올리고 짝 PDF·사진을 뒤에 올려도 앞 줄이 남지 않는다)
            try:
                _ia = 자료뿌리.모듈("imageasset")
                _범 = _그림카드들()
                _모두 = _ia._받은파일들()
                r["그림안내들"] = {f: _ia.문서사진말(_범, 파일={f}, 범위=_모두)
                                for f in sorted({c.get("파일") for c in _범 if c.get("파일") and (c.get("종류") == _ia.문서사진
                                                                                            or _ia._사진모름(c))})}
            except Exception as _e:
                print(f"[그림] 자료 칸 그림안내 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    return r


@등록("그림목록", ["장르"], 설명="올린 자료에서 시스템이 꺼낸 그림 목록 카드(id·파일·쪽·순번·종류 추정·곁 글·크기·같은 "
    "그림·비밀 표지·미리보기 경로). 문서 JSON 에는 \"그림\":\"img-…\" id 만 쓴다(경로·좌표는 시스템이 푼다). "
    "장르를 주면 그 장르의 그림 정책(자리·넣는 때·상한)도 싣는다", en="figures")
def 그림목록(장르=""):
    카드 = _그림카드들()
    ia = 자료뿌리.모듈("imageasset")
    g = 자료뿌리.모듈("genres")
    _밖 = _그림범위밖수(카드) if not 카드 else 0
    # 카드가 있어도 목록을 다 못 만들었으면(그림 도구 없음·깨짐) 그 까닭을 함께 싣는다('26-10-01 주관 판정 S2, verify_fixup7 F1)
    값 = {"요약": ((ia.카드요약(카드) + (" — " + ia.카드오류() if ia.카드오류() else "")) if 카드 else "")
                 or (ia.카드오류() if ia.카드오류() else
                     _그림범위빈말(_밖) if (_밖 or (_CLI표면() and _그림범위() is not None))
                     else "올린 자료에 그림이 없습니다"),
         "카드": [{k: c[k] for k in ("id", "파일", "자리", "종류", "쓸수있음", "까닭", "곁글", "표시mm", "원본px",
                                  "같은그림", "또있음", "비밀표지", "가림", "미리보기") if k in c} for c in 카드]}
    if 장르:
        정 = g.그림정책값(장르)
        값["정책"] = {k: 정.get(k) for k in ("자리", "넣는때", "넣지않는때", "상한", "공개", "모양")}
        값["글"] = ia.카드글(카드, 공개=bool(정.get("공개")))
    else:
        값["글"] = ia.카드글(카드)
    if _경로보임():
        # 에이전트가 미리보기 그림을 열어 볼 수 있게 — 웹앱·공유 연결(남의 서버 경로·세션 열쇠)에는 싣지 않는다(review_impl2 L2)
        값["미리보기뿌리"] = 자료뿌리.받은것뿌리()
    return {"ok": True, "값": 값, "로그": 값["요약"]}


@등록("본", ["장르"], 설명="그 장르의 문서 JSON 이 실제로 어떤 모양인지 — 등록부의 실물에서 뽑는다", en="shape")
def 본(장르="samples"):
    """돌려줄 JSON 의 **모양**을 실물에서 뽑아 준다.

    왜 필요한가 — 웹앱 지시문이 1p 모양만 예시로 갖고 있었고, 나머지 장르에는
    "정본 구조를 그대로 따르는 JSON" 이라는 한 줄뿐이었다(2026-08-05 A-4 12번, 가설 H1).
    모델이 무슨 키를 넣어야 할지 알 길이 없으니 1p 외 장르가 안 서는 게 당연했다.

    **여기에 모양을 손으로 적지 않는다** — 등록부의 실물 문서에서 뽑는다.
    조립기가 바뀌면 실물이 먼저 바뀌고 이 모양이 따라온다.
    """
    # 모양은 **정본(코드루트)** 등록부에서 뽑는다 — 세션 등록부(자료뿌리.등록부)를 읽으면
    # 사용자가 아직 그 장르 문서를 안 만든 세션에서 빈 [] 가 나와 모양이 사라진다. 그러면
    # 초안 지시문이 else 가지("실물 본을 못 가져왔다")로 떨어져, 모델이 스키마를 지어내
    # 조립기가 크래시한다(시행문·보도자료·규정·슬라이드가 첫 제작에서 통째로 깨졌다).
    # 모양은 "우리가 배포하는 것"(코드길)이므로 세션과 무관하게 코드루트에서 읽는다.
    if not 자료뿌리.장르맞나(장르):   # 보안('26-10-01)
        return {"ok": False, "로그": f"'{str(장르)[:40]}' 등록부가 없습니다"}
    등록 = 자료뿌리.코드길("build", f"{장르}-docs.json")
    if not os.path.exists(등록):
        return {"ok": False, "로그": f"'{장르}' 등록부가 없습니다"}
    문서들 = json.load(open(등록, encoding="utf-8"))
    if not 문서들:
        return {"ok": False, "로그": f"'{장르}' 에 실물 문서가 없어 모양을 못 뽑습니다"}

    # r9 검토자 발견(fab-precision·regression, MEDIUM) + r10 W2 재발(구현자B, 2026-09-27) —
    # 본보기 실물 문서의 말단 글 값을 깎기()가 40자까지 그대로(또는 '○○' 한 단어로만) 보여
    # 주면, 모델이 그 값을 그대로 베낀다(재현: 프론티어 M/s3 도 '대내공개' 로 걸렸고, W2
    # 실측에서는 '보존기간 5년'·'09:00 이후'(보도시점.값)·'…1부.'(붙임 항목)·파일명
    # 'rc-press-aidoc' 까지 베꼈다). 그렇다고 값을 전부 가리면 모델이 **유효한 열거 이름**
    # (레이아웃·아이콘·테마 등)을 몰라 지어내고, 그건 지어낸 이름이 하드 게이트에 막힌다
    # (P3 실측: '정리'·'본페이지' 레이아웃, 'chat'·'alert' 아이콘). 그래서 말단 글 값을
    # 세 갈래로 나눈다 — 모양(키·중첩·목록 첫 원소)은 그대로 두고:
    #   ① 구조·열거 값 — 조립기·속성값 카탈로그가 **이름으로 분기**하는 키(build/assemble*.py
    #      의 속성값.열거·등호비교 실측으로 뽑았다). 모델이 유효 이름을 봐야 하니 그대로 둔다.
    #   ② 메타 칸 — 실제 연락처·문서번호·시행일 같은 개인·기관 정보. 있으면 쓰고 없으면
    #      ○○ 로 비우라는 안내로 바꾼다(문서에 흔히 없는 칸이라 빈 채도 정상임을 알려준다).
    #   ③ 그 외 자유글(제목·요약·본문 등) — "자료로 채울 글" 안내로 바꾼다.
    # 숫자·불리언 말단은 속성 범위 신호라 그대로 둔다(예전과 동일). filename 은 따로 안내한다.
    _구조열거키 = frozenset({
        "레이아웃", "type", "level", "아이콘", "스타일", "style", "위계체계",
        "포인트색", "테마", "효과", "2단마커", "글꼴", "단위",
        "문서종류", "목적", "purpose_type", "배치모드", "여백", "개체간격",
        # 제목 모양·보도 본문꼴('26-09-28) — 조립기가 속성값.열거로 이름 분기하는 키
        "제목모양", "제목틀", "장모양", "절모양", "본문꼴",
    })
    # 닫힌 열거지만 **실물 값을 그대로 보여 주면 안 되는** 키(r10 재검토, MEDIUM 반박
    # 수용) — _구조열거키 처럼 "그대로 두면 유효 이름"이 아니다: 위 사실규칙(_사실규칙_기본)
    # 이 정한 선택지가 커밋된 표본 값과 실제로 다르다(공개=사실규칙은 '공개·부분공개·
    # 비공개'인데 표본은 전부 '대내공개' — 표본을 그대로 보이면 W2 가 잡았던 바로 그
    # 유출 재발이다). 방식(보도시점)도 표본 3건이 전부 '엠바고' 하나뿐이라 그대로
    # 보이면 모델이 실제로 즉시 배포인 자료에도 늘 엠바고를 고른다(shape_probe 실측).
    # 그래서 실물 값 대신 **선택지 자체**를 파이프(|)로 보여 준다 — build/assemble_press.py
    # 의 스키마 주석이 이미 이 꼴('즉시|엠바고|시각지정')을 쓰고 있어 그대로 맞춘다.
    _닫힌열거_힌트 = {"공개": "공개|부분공개|비공개", "방식": "즉시|엠바고|시각지정"}
    _메타키 = frozenset({
        "보도시점", "배포", "담당", "연락처", "전화", "주소", "우편번호",
        "문서번호", "보존기간", "시행일", "출처", "붙임", "별첨",
        "팩스", "이메일", "기안자", "시행", "보고일",
    })
    _메타글 = "(자료에 있을 때만 — 없으면 ○○)"
    # 목록형 메타 칸(붙임·별첨·출처) 전용 안내(r10 재검토, MEDIUM 반박 수용) — 옛 문구는
    # 선택지 1건짜리 배열([_메타글])만 보여 줘 "적어도 하나는 채워라"로 읽혔다(사실규칙
    # "출처·붙임을 자료에 없이 새로 만들지 마라"와 반대 방향). 빈 배열이 정상 기본임을
    # 대놓고 적는다.
    _메타글_목록 = "(자료에 있을 때만 — 없으면 빈 배열 [])"
    _내용글 = "(자료로 채울 글)"
    _파일명글 = "(영문 소문자·하이픈 파일명)"

    def 깎기(v, 깊이=0, 메타=False):
        """값을 **모양만 남기고** 줄인다 — 내용을 베끼게 하지 않으려고.

        `메타` 는 부모 키가 이미 메타 칸(담당·보도시점 등)이라 그 밑 자식도 통째로
        메타로 보라는 상속 표시다 — 컨테이너 자체는 dict/list 라 `k in _메타키` 로 안
        잡히지만, 자식(전화·값 등)까지 다 가려야 해서 이 인자로 아래까지 물려준다."""
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                if k.startswith("_"):
                    continue
                자식메타 = 메타 or k in _메타키
                if k == "filename" and isinstance(x, str) and x.strip():
                    out[k] = _파일명글
                elif k in _닫힌열거_힌트 and isinstance(x, str):
                    out[k] = _닫힌열거_힌트[k] if x.strip() else x   # 실물 값 대신 선택지 자체
                elif k in _구조열거키 and isinstance(x, str):
                    out[k] = x                     # 유효 이름 — 그대로(모델이 지어내면 하드 게이트에 막힌다)
                elif (isinstance(x, list) and x and 자식메타
                      and all(isinstance(e, str) for e in x)):
                    out[k] = [_메타글_목록] if any(e.strip() for e in x) else []
                elif isinstance(x, str):
                    out[k] = (_메타글 if 자식메타 else _내용글) if x.strip() else x
                else:
                    out[k] = 깎기(x, 깊이 + 1, 자식메타)
            return out
        if isinstance(v, list):
            return [깎기(v[0], 깊이 + 1, 메타)] if v else []
        if isinstance(v, str):
            return (_메타글 if 메타 else _내용글) if v.strip() else v
        return v

    # 본보기는 장르마다 **합성 표본으로 고정**한다 — 등록부에 문서가 더해져도 모양 응답이
    # 흔들리지 않게. 고정 본보기가 없는 장르만 가장 채워진 문서로 둔다(빈 문서를 본으로 주면
    # 키가 빠진다).
    _본보기 = {"samples": "a2-11-budget", "gongmun": "rc-gongmun-energy",
              "fullreport": "rc-fullreport-energy", "press": "rc-press-aidoc",
              "regulation": "reg-ai-usage", "slides": "sl-charger-brief"}
    본문서 = next((d for d in 문서들 if d.get("filename") == _본보기.get(장르)), None) \
        or max(문서들, key=lambda d: len(json.dumps(d, ensure_ascii=False)))
    모양 = 깎기({k: v for k, v in 본문서.items()
               if not k.startswith("_") and k != "genre"})
    # 시각요소(표·도식·이미지)는 특정 절에만 있어 깎기(절[0]만 남김)가 놓친다 → 모델이 **구조**를
    # 못 봐 시각자료를 거의 안 만든다(2026-08-11 실측, E4B/31B 풀버전 사례). 절 예시에 심어
    # 키·중첩을 보여 준다. **넣을지 말지는 지시문의 시각자료 트리거가 정한다**(여기선 모양만).
    _시각요소예시(장르, 모양)
    return {"ok": True, "값": {"장르": 장르, "모양": 모양,
                             "키": [k for k in 모양],
                             "_뽑은곳": f"build/{장르}-docs.json 의 '{본문서.get('filename')}'"}}


def _시각요소예시(장르, 모양):
    """shape 에 표·도식·이미지 예시 구조를 심는다(깎기가 놓친 것). 풀버전은 절 안, 1p 는 table(top).
    실물 키·중첩과 동일 — 값은 자리표시자(모델은 '값은 베끼지 마라' 지시로 새로 채운다)."""
    표예 = {"캡션": "(표 제목 — 필요할 때만)", "header": ["구분", "항목A", "항목B"],
           "rows": [["행1", "값", "값"], ["행2", "값", "값"]]}
    도식예 = [{"type": "process", "캡션": "(도식 캡션 — 절차/구조/대조/분포/시계열일 때만)",
             "단계": [{"라벨": "단계1", "주체": "담당", "전이": "행위"}, {"라벨": "단계2"}]}]
    # 그림은 목록 id 로만('26-09-30) — 파일·쪽·자를곳 좌표는 모델에게 보이지 않는다(시스템이 푼다)
    이미지예 = [{"그림": "(올린 자료 속 그림 목록의 id, 예: img-…)", "캡션": "(그림 제목)",
              "설명": "(※ 자료에 출처 표기가 있을 때만)", "폭": "60%"}]
    if isinstance(모양.get("장"), list) and 모양["장"] and isinstance(모양["장"][0], dict):
        절들 = 모양["장"][0].get("절")
        if isinstance(절들, list) and 절들 and isinstance(절들[0], dict):
            절들[0].setdefault("표", 표예)
            절들[0].setdefault("도식", 도식예)
            절들[0].setdefault("이미지", 이미지예)
    if "table" in 모양 and not 모양.get("table"):     # 1p — 고정스키마 table 슬롯 채워 보이기
        모양["table"] = {"after_heading": "대안검토", "caption": "(단위 표기)",
                       "header": ["구분", "안A", "안B"], "rows": [["비용", "값", "값"]]}
    # 규정 "본문" — 깎기()가 리스트를 **첫 원소만** 남겨서(위 깎기 docstring), 본보기 문서의
    # 본문[0]이 흔히 "장"(장 제목만, "text" 없음)이면 조문 본문 글자를 어느 키에 담는지
    # 지시문에서 단 한 번도 안 보였다(e2e s4 재진단, '26-09-27 — '조' 항목이 실제 조문
    # 텍스트를 어떤 키로 담는지 세 도구 응답 모두 안 보여줘, 모델이 "본문":[문자열…] 로
    # 잘못 추측해 완성 문서의 조문 본문 전체가 최종 렌더에서 사라졌다). 장 하나 + "text"
    # 키를 쓰는 조 하나를 나란히 보여준다.
    # 이 장/조 example 은 regulation 전용이다 — 조건 없이 심으면 보도자료·시행문처럼
    # "본문" 이 list 인 다른 장르까지 이 규정 전용 모양을 그대로 물려받는다. 그 장르
    # 조립기(assemble_press.py·assemble_gongmun.py)는 level 을 정수 1~6 으로만 받아
    # '장'/'조' 문자열을 [속성 거부]로 튕기거나(보도자료) TypeError 로 죽는다(시행문).
    # (api:F1, e2e r6 재발 — 회귀 시험: test/r7_api7.py)
    # '26-09-28 규정 처방 P2 — 장을 빼고 조부터 시작한다(장은 조문이 많을 때만 쓴다, 온톨로지
    # 구성.장_사용). 장 값 이름은 _지시문조립 규정 분기의 평면 목록 설명 줄이 계속 보여 준다.
    if 장르 == "regulation" and isinstance(모양.get("본문"), list):
        모양["본문"] = [
            {"level": "조", "제목": "(예시) 목적", "text":
             "이 조의 본문 글은 반드시 이 \"text\" 키(문자열 한 문장)에 쓴다 — 값은 베끼지 말고 자료로 새로 채운다."},
        ]


# 규정 조문 평면 목록 예시 — _지시문조립 규정 분기가 한 줄 JSON 으로 싣는다('26-09-28 규정
# 처방 P2, 내부 기록). 소재는 공용 물품 대여(벤치·본보기 표본·과적합 대조
# 시나리오 어디에도 없는 것). 조 5·항 1·호 6 — test/r14_reg14.py 가 짜기()로 번호를 확인한다.
_규정조문예시 = [
    # 제1조에서 기관 약칭을 정의한다(reg12 '26-09-30 판정 A — 실물 규정·지침에서 가장 흔한 꼴). 정의한 약칭은 뒤 조문에서
    # 쓴다(reg12 fixup, verify.md L5 — 정의만 하고 안 쓰는 꼴을 본뜨지 않게)
    # reg13('26-09-30 bench15 J3) — 본보기도 법제 말투로(빌려 쓰다→대여하여 사용하다, 돌려주다→반납하다, 끝나면 바로→종료되면
    # 즉시). 베낄 꼴이 구어면 말투 규칙이 무너진다. 제한 주체(제3조)가 승인자(제4조)와 같은 '총무 부서의 장'인 것은 J1 꼴이다.
    # reg13d 판정 D3('26-10-01) — 기관 이름은 자리표시('○○(이하 “기관 약칭”…)', 뜻이 드러나는 꼴)다 — 예전 '○○공사(이하
    # “공사”…)'가 공단·연구원 문서로 샜다(verify13c 2-1). reg13e 판정 E5 — 지시문에도 이 자리표시 그대로 싣는다(자료 첫머리를
    # 정규식으로 읽어 채우던 _자료기관이름은 걷었다: 남의 기관·공사(工事)·직함을 이 문서 기관으로 채웠다, verify13d 3-2).
    {"level": "조", "제목": "목적", "text": "이 규정은 ○○(이하 “기관 약칭”이라 한다)의 임직원이 공용 물품을 대여하여 사용할 때 지켜야 할 사항을 정함을 목적으로 한다."},
    {"level": "조", "제목": "정의", "text": "이 규정에서 사용하는 용어의 뜻은 다음과 같다."},
    {"level": "호", "text": "“공용 물품”이란 기관 약칭의 여러 부서가 공동으로 사용하도록 총무 부서의 장이 지정한 물품을 말한다."},
    {"level": "호", "text": "“대여 기간”이란 공용 물품을 받은 날부터 반납한 날까지의 기간을 말한다."},
    {"level": "조", "제목": "대여 제한", "text": "총무 부서의 장은 다음 각 호의 어느 하나에 해당하는 경우에는 공용 물품의 대여를 제한한다."},
    {"level": "호", "text": "같은 물품을 이미 대여하여 사용하고 있는 경우"},
    {"level": "호", "text": "반납하지 아니한 물품이 있는 경우"},
    {"level": "조", "제목": "대여 승인", "text": "공용 물품을 대여받으려는 임직원은 총무 부서의 장에게 신청하여 승인을 받아야 한다."},
    {"level": "항", "text": "총무 부서의 장은 제1항에 따른 신청을 받은 날부터 2일 이내에 승인 여부를 결정하여야 한다."},
    {"level": "조", "제목": "준수사항", "text": "공용 물품을 대여받은 임직원은 다음 각 호의 사항을 지켜야 한다."},
    {"level": "호", "text": "대여 기간이 종료되면 즉시 반납할 것"},
    {"level": "호", "text": "물품을 다른 사람에게 사용하게 하지 아니할 것"},
]


# ── reg13d 판정 D3 · reg13e 판정 E5('26-10-01) — 규정 템플릿·본보기의 기관 이름 자리 ─────────────────────────────────
# 늘 뜻이 드러나는 자리표시로 둔다('○○(이하 “기관 약칭”이라 한다)'·'○○ ○○ 지침 제정(안)'). '예시의 기관 이름을 옮기지 말고 자료의
# 기관 이름으로' 뜻은 지시 줄·핵심 용어 줄이 맡는다. 모델이 자리표시를 그대로 베끼면 조문꼴.확인할것()이 '기관 약칭' 글자를 한 줄로
# 묻는다(글자 대조). 자료 첫머리 정규식으로 기관 이름을 채우던 길(_자료기관이름)은 걷었다 — 첫 기관 이름이 남의 기관('○○공사의
# 권고에 따라 ○○재단 …')·공사(工事)('승강기교체공사')·직함('선임연구원')이면 틀리게 채웠다(verify13d 3-2, 옛 누설보다 나쁘다).
_규정기관틀 = "○○(이하 “기관 약칭”이라 한다)"
_규정제명틀 = "○○ ○○ 지침 제정(안)"


@등록("어긋남", ["자료들"], 설명="넣은 자료들이 서로 다르게 말하는 자리를 짚는다 — 고르지 않고 되묻는다", en="conflicts")
def 어긋남찾기(자료들):
    """자료가 서로 어긋나면 **한쪽을 골라 조용히 따르지 않는다.**

    사장님 판정 2026-08-05 (목차로직 `_판정.자료가_어긋나면_짚어서_묻는다`) —
    대화를 우선하면 말이 틀렸을 때 파일의 사실이 조용히 지워지고, 파일을 우선하면
    "그건 바뀌었어요" 를 못 받는다. 둘 다 **틀린 것을 소리 없이 통과시키는** 길이다.

    `자료들` 은 [{"이름": …, "글": …}, …] 이거나 inbox 파일 이름 목록이다.
    """
    _어 = 자료뿌리.모듈("어긋남")
    묶음 = []
    for x in (자료들 or []):
        if isinstance(x, dict):
            묶음.append((x.get("이름") or "자료", x.get("글") or ""))
            continue
        r = 파일읽기(str(x))
        if not r["ok"]:
            return {"ok": False, "로그": r["로그"]}
        v = r["값"]
        묶음.append((str(x), v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)))
    if len(묶음) < 2:
        return {"ok": False, "로그": "자료를 둘 이상 주세요 — 견줄 것이 있어야 어긋남을 봅니다"}
    난것 = _어.견주기(묶음)
    # 되묻기가 몇 번 일어났나 — **무엇이 어긋났는지는 안 적는다**(그건 자료 내용이다).
    # 단위 갈래(개·원·%·…)까지만 남긴다 — 규칙 차원에서 쓸 수 있는 최대치다.
    자료뿌리.규칙적기("되묻기", [f"어긋남:{x.get('단위') or '?'}" for x in 난것])
    # 짚은 물음을 **미결로 적는다**(WP-S3) — 이 기록이 있어야 관문(_되묻기관문)이
    # 조립·새문서·저장을 세울 수 있다. 여기 안 적으면 되묻기는 도로 규범일 뿐이다.
    _미결어긋남적기(난것)
    막는것 = "·".join(sorted(w["이름"] for w in 작업.values() if w.get("승인필요")))
    return {"ok": True, "값": {"어긋남": 난것, "물음": _어.물음말(난것),
                            "갯수": len(난것)},
            "로그": ("어긋난 자리 없음 — 다만 뜻이 어긋난 것은 이 자가 못 봅니다"
                   if not 난것 else
                   f"어긋난 자리 {len(난것)}곳 — 되물어야 합니다. "
                   f"답이 오기 전에는 {막는것} 이 서지 않습니다"
                   f"(어긋남답 인자로 답을 실어 보내세요)")}


# ── 되묻기·승인 강제 (구현계획.md §3 WP-S3) ──────────────────────────────
# 출시계획 1-5: "고르지 않고 되묻는다"(사장님 판정 2026-08-05)는 규범만으로는 안
# 지켜진다 — 무인 흐름에서 Claude 가 조용히 한쪽을 골라도 아무 일이 안 일어난다.
# 그래서 **코어가 거부한다**: 어긋남 물음에 답이 안 왔으면 승인필요 작업(등록부의
# 플래그 — 손목록 아님)이 서고, 물음이 응답에 실려 나간다. Claude 는 그 물음을
# 사용자에게 전달할 수밖에 없다(대신 답해도 그 답이 응답·기록에 남는다).
#
# 관문이 사는 곳은 부르기() **하나**다 — 세 문(웹앱 serve.py · MCP server.py ·
# CLI __main__)과 작업시작 스레드가 전부 그 길을 타는 것을 2026-08-08 실측으로
# 확인했다(serve.py 의 POST 는 전부 api.부르기, MCP 도구는 생성 코드가 api.부르기,
# 옛경로 /save·/upload 도 어댑터를 지나 같은 길이다).

def _미결어긋남읽기():
    """미결 파일을 읽는다. 없으면 {} · 깨져 있으면 None — 부르는 쪽이 갈라 다룬다.

    깨진 파일을 {} 로 읽으면 관문이 **조용히 열린다**(규칙 3). None 을 돌려 관문이
    막힌 채로 사람말을 내게 한다. 원자 쓰기(자료뿌리.원자json)라 반토막은 없지만,
    디스크가 하는 일을 다 믿지는 않는다.
    """
    길 = 자료뿌리.미결어긋남길()
    if not os.path.exists(길):
        return {}
    try:
        본 = json.load(open(길, encoding="utf-8"))
        return 본 if isinstance(본, dict) else None
    except (OSError, ValueError):
        return None


def _미결어긋남적기(난것):
    """어긋남찾기가 짚은 물음을 미결로 적는다. 물음 하나 = `무엇|단위` 열쇠 하나.

    같은 물음(값들까지 같은)이 다시 짚혀도 **이미 받은 답은 살린다** — 웹앱·재시도
    흐름이 어긋남찾기를 두 번 부르는 일이 흔한데, 그때마다 답이 증발하면 관문이
    같은 것을 두 번 묻는다(되묻기가 아니라 조르기가 된다). 값들이 달라졌으면 다른
    물음이므로 답을 지우고 다시 묻는다.
    """
    if not 난것:
        return
    길 = 자료뿌리.미결어긋남길()
    # 읽고-고치고-쓰는 세 걸음이라 빗장을 쥔다(적대리뷰 ③과 같은 뿌리) — 안 쥐면
    # 어긋남찾기 둘이 동시에 오면 뒤엣것이 앞엣것의 물음을 통째로 덮는다.
    with 자료뿌리.빗장(길):
        본 = _미결어긋남읽기()
        if 본 is None:
            본 = {}          # 깨진 기록은 새 물음으로 다시 세운다 — 어차피 답도 못 믿는다
        for x in 난것:
            열쇠 = f"{x['무엇']}|{x['단위']}"
            있 = 본.get(열쇠)
            값들 = sorted(v.get("값") for v in x.get("값들") or [])
            if (있 and sorted(v.get("값") for v in 있.get("값들") or []) == 값들
                    and (있.get("답") or "").strip()):
                continue
            본[열쇠] = {"무엇": x["무엇"], "단위": x["단위"], "값들": x["값들"],
                      "물은때": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "답": None, "답한때": None}
        자료뿌리.원자json(길, 본, indent=1)


def _되묻기관문(인자):
    """승인필요 작업 앞의 관문. 통과면 None, 막히면 응답 한 벌을 돌려준다.

    `어긋남답` 은 여기서 받아 **기록부터 한다** — 작업 함수는 이 인자를 모른다
    (부르기() 가 관문을 지난 뒤의 인자만 넘긴다). 답의 정본은 세션의 미결 파일
    (자료뿌리.미결어긋남길)이다: 같은 세션의 다음 부름은 답을 다시 실을 필요가 없다.
    """
    답 = 인자.pop("어긋남답", None)
    if isinstance(답, str) and 답.strip():
        # MCP·CLI 클라이언트가 JSON 을 글로 실어 보내는 일이 잦다(doc 인자에서 겪은
        # 그 모양). 여기서 안 받아 주면 "답을 보냈는데도 막힌다"가 된다.
        try:
            답 = json.loads(답)
        except ValueError:
            return {"ok": False, "로그": "어긋남답을 JSON 으로 읽지 못했습니다 — "
                                      '예: {"충전기|기": "6"}'}
    if 답 is not None and not isinstance(답, dict):
        return {"ok": False, "로그": "어긋남답은 객체여야 합니다 — "
                                  '예: {"충전기|기": "6"} (열쇠는 물음의 id)'}
    길 = 자료뿌리.미결어긋남길()
    if 답:
        with 자료뿌리.빗장(길):
            본 = _미결어긋남읽기()
            if 본 is None:
                return {"ok": False, "로그": "미결 어긋남 기록이 깨져 있어 답을 못 "
                                          "받습니다 — 어긋남 검사를 다시 돌려 주세요"}
            모르는 = sorted(k for k in 답 if k not in 본)
            if 모르는:
                # 조용히 버리지 않는다(규칙 3) — 오타 난 답이 버려진 채 "여전히
                # 막힌다"만 보이면 부르는 쪽은 영영 이유를 모른다.
                return {"ok": False,
                        "로그": f"모르는 물음에 답이 왔습니다: {모르는} — 지금 물음 id: "
                              f"{sorted(본) or '(없음)'}"}
            답한단위 = []
            for k, v in 답.items():
                v = str(v).strip()
                if not v:
                    continue                  # 빈 답은 답이 아니다 — 아래 '남은'에 남는다
                본[k]["답"] = v
                본[k]["답한때"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                답한단위.append(본[k].get("단위") or "?")
            자료뿌리.원자json(길, 본, indent=1)
        # 답도 규칙 차원만 원장 후보로 — 값 자체는 세션 파일에만 남는다(1-6 A안)
        자료뿌리.규칙적기("되묻기답", [f"어긋남답:{u}" for u in 답한단위])
        본따로 = 본
    else:
        본따로 = _미결어긋남읽기()
        if 본따로 is None:
            return {"ok": False, "로그": "미결 어긋남 기록을 읽지 못했습니다 — 조용히 "
                                      "통과시키지 않습니다. 어긋남 검사를 다시 돌려 주세요"}
    남은 = {k: v for k, v in 본따로.items() if not (v.get("답") or "").strip()}
    if not 남은:
        return None
    _어 = 자료뿌리.모듈("어긋남")
    물음들 = [{"id": k, "무엇": v["무엇"], "단위": v["단위"], "값들": v["값들"]}
            for k, v in sorted(남은.items())]
    return {"ok": False, "필요한것": "답", "물음": 물음들,
            "로그": _어.물음말(물음들) + "\n같은 부름에 어긋남답 인자로 답을 실어 다시 "
                  '보내세요 — 예: {"어긋남답": {"' + 물음들[0]["id"] + '": "맞는 값"}}'}


def _플랜승인물음(문서들):
    """승인 안 된 구성 설계(plan)에 매인 문서를 짚는다 → 물음 목록 (WP-S3 '승인 없음').

    출시계획 1-5: 빌드플랜 승인(제품 5단계 ③)도 되묻기와 같은 모양이다 — 성실하기를
    바라지 않고 진행을 막는다. plan_id 가 없는 문서는 검사하지 않는다(플랜 없이 만든
    문서가 정상 경로에 많다 — 등록부 실물 대다수가 그렇다, 2026-08-08 실측).
    답의 기록처는 **플랜 JSON 의 승인 필드**다(plan.html 이 쓰는 그 자리) — 어긋남답
    같은 별도 통로를 안 만든 까닭은, 통로가 둘이면 승인 상태의 정본이 갈라져서다.
    """
    물음 = []
    for d in 문서들:
        pid = (d or {}).get("plan_id")
        if not pid:
            continue
        try:
            상태 = ((json.load(open(자료뿌리.플랜(pid), encoding="utf-8"))
                    .get("승인") or {}).get("status") or "").strip() or "기록없음"
        except OSError:
            상태 = "플랜없음"     # plan_id 만 있고 플랜이 없다 — 승인을 확인할 길이 없으니 막는다
        except ValueError:
            상태 = "플랜깨짐"
        if 상태 != "승인":
            물음.append({"id": f"플랜|{pid}", "무엇": f"구성 설계 {pid}", "단위": "승인",
                       "문서": d.get("filename"), "상태": 상태})
    return 물음


def _플랜승인막힘(문서들):
    """문서들 중 승인 없는 플랜이 있으면 막힘 응답 한 벌, 없으면 None."""
    물음들 = _플랜승인물음(문서들)
    if not 물음들:
        return None
    줄 = ["구성 설계(빌드플랜)가 아직 승인되지 않아 진행하지 않습니다:"]
    for q in 물음들:
        줄.append(f"  · {q['문서']} ← {q['무엇']} (현재: {q['상태']})")
    줄.append("승인 화면(plan.html)에서 확인받아 플랜의 승인 상태를 '승인' 으로 "
             "바꾼 뒤 다시 부르세요 — 코어는 성실을 바라지 않고 진행을 막습니다(출시계획 1-5).")
    if not os.environ.get("문서지능_웹앱") and _알려진방식() != "함께검수":
        # 플러그인 작업 방식('26-09-29) — 웹앱(app.html)도 이 로그를 받으므로 플러그인에서만 붙인다.
        # 함께 검수로 정해진 대화(이번 대화의 답·저장된 선택)에는 스스로 승인하는 길을 알려 주지 않는다(M1).
        줄.append("바로 완성이면 플랜승인(approveplan)을 직접 불러 기록한 뒤(코멘트에 '바로 완성') 다시 부르세요.")
    return {"ok": False, "필요한것": "답", "물음": 물음들, "로그": "\n".join(줄)}


@등록("서식분석", ["경로"], 읽기=False,
    설명="예시 서식에서 **구성 설계(2층)** 를 읽어낸다 — 어떤 절을 어떤 차례로 놓았는가",
    en="analyzeform")
def 서식분석(경로):
    """사용자가 '이렇게 만들어 줘' 하며 준 예시에서 **뼈대**를 뽑는다.

    이것이 아키텍처가 미뤄 둔 입력 3유형 중 ③(예시문서 역추출)이다. 내용을 베끼는 것이
    아니라 **구성**을 읽는다 — 절이 몇이고 무슨 차례이며 위계를 몇 단으로 쓰는가.
    """
    import re as _re
    r = 파일읽기(경로, "chunks")
    if not r["ok"]:
        return r
    청크 = r["값"] if isinstance(r["값"], list) else (r["값"] or {}).get("chunks") or []

    상위 = _re.compile(r"^\s*([□■◇◆▣])\s*(.+)$")
    # '○○공사'·'ㅇㅇ' 같은 익명 표기는 마커가 아니다 — 같은 글자가 곧바로 이어지면 뺀다.
    하위 = _re.compile(r"^\s*([○●◦・·ㅇ])(?!\1)\s*(.+)$")
    # kordoc 4.8+ 는 PDF 에서 제목에 '#', 목록에 '- '·'* ' 를 붙여 내보낸다. 그 뒤에 한국식
    # 마커(□○-*※·가.·1.)가 또 오면 마크다운 기호는 떼고 읽는다 — 안 떼면 '- 가. …' 가
    # 3단 항목(-)으로 잘못 세진다(4.15.4 올림 시 a1-02-notice.pdf 에서 확인).
    마크다운 = _re.compile(r"^\s*(?:#{1,6}\s+|[-*]\s+(?=[□■◇◆▣○●◦・·ㅇ\-–*※]|[가-하]\.|\d+\s*\.))")
    셋째 = _re.compile(r"^\s*[-–]\s*(.+)$")
    넷째 = _re.compile(r"^\s*[*※]\s*(.+)$")
    조 = _re.compile(r"^\s*제\s*\d+\s*조")
    번호 = _re.compile(r"^\s*(\d+)\s*\.\s+(.+)$")

    # 날짜 줄('2026. 9. 29.(화)', "'26. 12.", '2026. 9.29.', '2026. 10월')은 번호 줄이 아니다 — 절도 아니고 소속도
    # 바꾸지 않는다. 네 자리 해는 '월'·붙은 날('9.29.')까지 날짜로 본다('26-09-29 검토자 T6: 옛 판도 그 둘을 절로
    # 셌다). 두 자리 해에 따옴표가 없으면 옛 규칙대로 점 뒤에 숫자가 붙으면 날짜가 아니다('12. 3.5배 향상').
    날짜꼴 = _re.compile(r"^\s*(?:(\d{4})|[’'‘](\d{2})|(\d{2}))\s*\.\s*(\d{1,2})\s*(\.|월)")

    # 따옴표 없는 두 자리 수로 시작하는 날짜꼴('10. 3월 중 …', '11. 12월 결산 …')은 **모호**하다 — 번호 절 제목일 수
    # 있다('26-09-29 검토자 U3: 번호 절 11개 가운데 10·11 번이 날짜로 빠져 11→9). 앞에 그 번호 바로 앞 번호(n-1)의
    # 번호 줄이 있으면 번호로, 없으면 날짜로 본다(아래 종류들 다듬기). 네 자리 해·따옴표 해는 늘 날짜다.
    # 'N. N.' 뒤에 요일 괄호·시각이 붙으면 늘 날짜다 — '10. 1.(수) 접수 시작'·'10. 7.(수) 14:00 차기 회의'·'9. 30.(화) 공고'
    # ('26-09-30 검토자 fv5 C6·C7: 위 '모호' 규칙이 앞 번호 9 에서 이어진다며 일정 줄을 절로 올렸다 — 주관 판정 K4).
    # 날 뒤 점이 없는 요일('10. 1(수)')과 한글 시각('10. 7. 오후 2시'·'10. 7. 14시 회의')도 같다('26-09-30 검토자 fv6 ⑦ — 세
    # 형식 모두 절 10). '시간'·'시군' 처럼 '시' 뒤에 글자가 붙으면 시각이 아니다.
    # 'NN. N월 …'(달 이름)은 판정 K4 대로 **보통 줄이면 늘 날짜**다(fv6 ⑦ '안건 1~9 뒤 10. 3월 중 착수 보고' 10→9). 모호로
    # 남기는 것은 마크다운 제목(#)·Word 번호 목록으로 나온 줄뿐이다 — 일정 줄은 제목·자동 번호로 쓰지 않는다([판단]).
    # 그래서 fu4 U3(보통 줄 번호 절 '10. 3월 중 착수 보고'·'11. 12월 결산 보고')는 다시 날짜가 된다(판정이 앞선다).
    # **한계**('26-09-30 주관 판정 S3 — 고치지 않고 적어 둔다): 보통 줄(제목·자동 번호가 아닌 줄)로 쓴 번호 절의 제목이 달
    # 이름으로 시작하면('10. 3월 중 착수 보고') 그 절은 날짜로 읽혀 절 목록에서 빠진다(U3 꼴: 번호 절 11개 → 9개). 같은 꼴의
    # 일정 줄('안건 1~9 뒤 10. 3월 중 착수 보고')과 줄 하나만으로는 가를 수 없어, 흔한 일정 줄 쪽을 택했다. 그 절 아래 ○ 항목은
    # 앞 절의 항목으로 셈해진다. 번호 절을 제목 스타일·Word 번호 목록으로 쓴 문서는 해당하지 않는다(모호 → 앞 번호 n-1 이면 번호).
    # 'NN. N. 글'(점 뒤 숫자·요일·시각이 아닌 글)은 예전대로 모호다(앞 번호 n-1 이 있으면 번호).
    요일꼴 = _re.compile(r"^\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*\(\s*[월화수목금토일]\s*\)")
    시각꼴 = _re.compile(r"^\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(?:\d{1,2}\s*:\s*\d{2}|(?:오전|오후)\s*\d{1,2}\s*시"
                      r"|\d{1,2}\s*시(?=\s|$|\d|분|까지|부터|[~∼)]))")

    def 날짜(줄):
        for 꼴 in (요일꼴, 시각꼴):
            m = 꼴.match(줄)
            if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
                return True
        m = 날짜꼴.match(줄)
        if not m or not 1 <= int(m.group(4)) <= 12:
            return False
        if m.group(3) and m.group(5) == "." and _re.match(r"\d", 줄[m.end():]):
            return False
        return ("달" if m.group(5) == "월" else "모호") if m.group(3) else True
    로마 = _re.compile(r"^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|(?:I{1,3}|IV|VI{0,3}|IX|X)(?=\s*\.))\s*[.．]?\s*\S")
    붙임 = _re.compile(r"^\s*(?:[-*]\s*)?붙\s*임(?:\s|\d|$)")
    그림 = _re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")

    절, 마디, 표수 = [], {2: 0, 3: 0, 4: 0}, 0
    조문수 = 0
    # 번호 줄('1. …')은 **줄마다** 판정한다('26-09-29 판정 — 문서 전체 '모드'를 처음 나온 표지 하나로 정하던 것을
    # 버렸다). 옛 판(4.15.4) 뼈대를 기준으로 삼는다('26-09-29 주관: a1-02 시행문 +□ 와 검토자 반례 21파일 대조).
    #  · **Word 자동 번호 목록**(DOCX 의 List Number — kordoc json 블록 type=list, listType=ordered)은 늘 **항목**이다.
    #    4.15.4 는 그 번호를 내지 않아 절로 셀 일이 없었는데, 4.16 이 실제 번호로 내면서 □ 아래 번호 항목이 절로
    #    올라가 초안 지시문('이 절 이름과 차례를 그대로')에 들어갔다(syn.docx 2→5절). 손으로 친 '1. 현황' 은 보통
    #    문단이라 아래 규칙을 탄다(검토자 T8.docx: □ 요지 뒤 번호 절 제목 3개).
    #  · □ 줄(또는 DOCX 제목 스타일 줄) **바로 아래**(사이에 그림만) '1.' 로 시작하는 번호 줄 = 그 표지에 딸린 항목.
    #    그 뒤 같은 소속 안의 '2.·3.…'(앞 번호 +1)도 항목이다 — 사이에 ○ 설명이 껴도, 하나뿐이어도(검토자 T1·T2).
    #    소속은 다음 □·제목(#)·로마 숫자 제목(Ⅱ.)·붙임 줄에서 끝난다(T3: Ⅱ 가 □ 현황의 범위를 끊는다).
    #    다만 소속이 끝난 뒤 번호가 이어지면(□ 개요 / 1. 추진 배경 / □ 현황 / 2. 추진 계획) 그 번호들은 □ 보다
    #    위 차례라 **절**이다(검토자 교란: 실물 앞에 □ 한 줄).
    #  · 그 밖의 번호 줄 = **절**(□ 요지 뒤 ○ 설명 다음에 오는 번호 제목 — T8·a1-02 시행문 +□). 마크다운 제목(#)으로
    #    나온 번호 줄도 늘 절이다.
    #  · '붙임' 줄 뒤에 **이어지는** 번호 줄('붙임 1. …' 다음 '2. … 끝.', '붙임' 다음 '1. …')은 붙임 목록이다 — 절도
    #    항목도 아니다(T7). 번호가 이어지지 않으면 붙임이 끝난 것으로 본다(공공언어바로쓰기: 예시 공문 여럿이 한 문서에
    #    있어 '붙임1.' 뒤 다음 예시의 '3. …' 까지 붙임으로 삼키던 것을 말뭉치 대조에서 잡음).
    #  · 제목 아래 소속은 **DOCX 의 제목 스타일**에서만 연다(문서 제목 = 첫 제목 1 은 빼고 — 앞에 날짜·'대외비' 같은
    #    머리 표지 줄만 있어도 문서 제목이다(아래 제목i). 제목 2 로
    #    시작하는 문서는 연다, T4). PDF 의 '#' 은 kordoc 이 글자 크기로 짐작한 것이고(시행문 PDF 는 '수신'·'제목'
    #    칸이 제목이 된다) HWPX 의 제목은 장·조 제목이라, 거기서는 □ 의 소속을 끊기만 한다. 다만 HWPX 에 문서 제목 스타일
    #    ('제목'·Title 류) 문단이 첫 제목 앞에 있으면 DOCX 와 같이 연다('26-09-30 주관 판정 S2 — 아래 제목규칙).
    #  · DOCX 는 확장자가 아니라 파일 속(word/document.xml)으로도 가린다 — 올리기는 사용자가 준 이름을 그대로
    #    둔다(검토자 D3: 확장자 없는 DOCX 0→3절).
    참 = 경로
    if not os.path.isabs(str(참)):
        try:
            참 = os.path.join(자료뿌리.받은것뿌리(), str(경로))
        except Exception:
            pass
    워드 = os.path.splitext(str(r.get("파일") or 경로))[1].lower() == ".docx" or _DOCX인가(참)
    목록글 = set()
    if 워드:
        rj = 파일읽기(경로, "json")
        블록 = (rj.get("값") or {}).get("blocks") if rj.get("ok") and isinstance(rj.get("값"), dict) else None
        for b in 블록 or []:
            if isinstance(b, dict) and b.get("type") == "list" and b.get("listType") == "ordered":
                목록글.add(str(b.get("text") or "").strip())
    줄들 = []
    for c in 청크:
        if (c.get("type") or "") == "table":
            표수 += 1
        for 줄 in str(c.get("text") or "").split("\n"):
            m제 = _re.match(r"^\s*(#{1,6})\s", 줄)
            줄 = 마크다운.sub("", 줄.strip()).strip()
            if 줄:
                줄들.append((len(m제.group(1)) if m제 else 0, 줄))

    def 종류(i):
        수준, 줄 = 줄들[i]
        if 조.match(줄):
            return "조"
        d = 날짜(줄)
        if d == "달":                          # 'NN. N월 …' — 보통 줄은 늘 날짜, 제목(#)·Word 번호 목록이면 모호(판정 K4)
            d = "모호" if (수준 or 줄 in 목록글) else True
        if d is True or (d == "모호" and not 번호.match(줄)):
            return "날짜"
        if d == "모호":
            return "날짜?"                     # 앞 번호에서 이어지면 번호 줄(아래 다듬기)
        if 상위.match(줄):
            return "상위"
        if 그림.match(줄):
            return "그림"
        if 로마.match(줄):
            return "로마"
        if 붙임.match(줄):
            return "붙임"
        if 번호.match(줄):
            return "제목번호" if 수준 else ("목록" if 줄 in 목록글 else "번호")
        return "제목" if 수준 else "기타"

    종류들 = [종류(i) for i in range(len(줄들))]
    본번호 = set()                             # 앞에 나온 번호 줄의 번호들
    for i, t in enumerate(종류들):
        if t == "날짜?":
            n = int(번호.match(줄들[i][1]).group(1))
            if n >= 2 and n - 1 in 본번호:
                수준, 줄 = 줄들[i]
                종류들[i] = t = "제목번호" if 수준 else ("목록" if 줄 in 목록글 else "번호")
            else:
                종류들[i] = t = "날짜"
        if t in ("번호", "제목번호", "목록"):
            본번호.add(int(번호.match(줄들[i][1]).group(1)))
    # 문서 제목 = 첫 제목 1 줄 — 그 앞에 머리 표지 줄(날짜·'대외비'·'(안)'·'○○공사 기획처' 같은, 표지 없는 보통 글
    # 줄)이나 그림만 있어도 문서 제목이다. 앞에 □·번호·○ 같은 구성 줄이 먼저 나오면 문서 제목이 아니다. 예전엔
    # '첫 줄'만 봐서 날짜 줄이 먼저 온 DOCX 는 둘째 줄 제목 1 이 소속을 열어 번호 절이 모두 항목이 됐다('26-09-29
    # 검토자 U14 4→0·U14b 3→0·U17 3→0 — 같은 구성의 HWPX·PDF 는 3, 옛 판 뼈대도 3).
    # '26-09-30 주관 판정 K4: '- 대외비 -'·'※ 내부 검토용'·'- 1 -' 처럼 줄표·※ 로 감싼 머리 표지도 건넌다(검토자 fv5 C1·C2·C10
    # DOCX 0절 → 3). ○ 로 시작하는 줄은 본문 항목이라 여전히 멈춘다. 그리고 첫 제목 1 앞에 **Word 'Title' 스타일 문단**이나
    # **소개 문단**(15자 넘는 끝맺은 문장)이 있으면 그것이 문서 제목이다 — 첫 제목 1 도 절 제목으로 세어, 같은 구성의 두
    # 부분이 달리 셈해지지 않게 한다(fv5 C4 절 ['현황 분석','문제점'] 항목 [0,2]·C5 [0,0,0,2]).
    # '26-09-30 주관 판정 S2: HWPX 도 문서 제목 스타일('제목'·'문서 제목'·'표제'·Title — _제목스타일) 문단이 있으면 Word Title
    # 규칙과 같이 한다 — 그 문단이 문서 제목이고 첫 제목(개요) 스타일부터 절, 그 제목은 DOCX 제목처럼 아래 번호 줄의 소속을 연다.
    # HWPX 에는 소개 문단 규칙을 넓히지 않았다(판정은 스타일만). PDF 는 스타일 정보가 없어 두지 않는다.
    제목문단 = _DOCX제목글(참) if 워드 else (_HWPX제목글(참) if _HWPX인가(참) else set())
    한글제목 = not 워드 and bool(제목문단)

    # 줄표·※ 로 시작하는 머리 표지('- 대외비 -'·'※ 이 자료는 … 금합니다.')는 소개 문단보다 **먼저** 건넌다 — 끝맺은 ※ 안내문이
    # 소개 문단으로 잡혀 DOCX 절이 3 → 0 이 됐다('26-09-30 검토자 fv6 ②). 첫 구성 줄 앞의 이런 줄은 항목으로도 세지 않는다
    # — 위계 깊이가 2 → 3(줄표)·4(※)로 부풀었다(fv6 ⑧, 세 형식 모두). 구성 줄이 끝내 없는 문서(줄표 항목뿐)는 그대로 센다.
    # Title·소개 문단이 문서 제목이면 **첫 제목(Heading)부터 절**이다 — 번호 없는 제목도 그 수준이면 절로 센다(판정 K4,
    # fv6 ③: Title + 번호 없는 제목 1 '추진 배경'·'추진 계획' 이 절 0 이었다).
    def 소개문단(줄):
        return _실글자(줄) >= 15 and bool(_re.search(r"(?:다|요|음|함|임)\s*[.。]\s*$", 줄))
    제목i, 머리들, 문서제목앞 = -1, set(), -1
    for i, (수준, 줄) in enumerate(줄들):
        if 수준 == 1 and 종류들[i] in ("제목", "제목번호"):
            제목i = i
            break
        if 종류들[i] == "기타" and (셋째.match(줄) or 넷째.match(줄)):
            머리들.add(i)
            continue
        if 종류들[i] == "기타" and not 하위.match(줄) and (
                (워드 and (_정규(줄) in 제목문단 or 소개문단(줄))) or (한글제목 and _정규(줄) in 제목문단)):
            문서제목앞 = i
            break                              # 문서 제목이 앞에 있다 — 첫 제목 1 은 절 제목(제목i 없음)
        if 종류들[i] in ("날짜", "그림") or (종류들[i] == "기타" and not 하위.match(줄)):
            continue
        break
    else:
        머리들 = set()
    절수준 = next((수준 for k, (수준, _) in enumerate(줄들)
                if k > 문서제목앞 and 수준 and 종류들[k] in ("제목", "제목번호")), 0) if 문서제목앞 >= 0 else 0
    제목규칙 = 워드 or (한글제목 and 문서제목앞 >= 0)      # 제목 스타일이 번호 줄의 소속을 여는 문서(DOCX, 판정 S2 의 HWPX)
    # 절수준의 번호 없는 제목 아래(다음 같은·윗 수준 제목 앞)에 □ 줄이 있으면 그 제목은 **장(묶음)** 이지 절이 아니다 — □ 가
    # 절이다('26-10-01 검토자 fv7 S2 겹침: 제목 스타일 + 개요 1 '추진 배경' + □ 현황 → 절 ['추진 배경','현황','추진 계획','과제']
    # [0,1,0,1], 스타일 없는 같은 본문은 ['현황','과제'] [1,1] — 스타일 유무 하나로 같은 구성이 달리 셈해졌다, K4 와 같은 꼴).
    # 번호 붙은 제목('1. 추진 배경')은 예전대로 늘 절이다(DOCX·HWPX 같음).
    def _장제목(i):
        for k in range(i + 1, len(줄들)):
            if 줄들[k][0] and 줄들[k][0] <= 절수준 and 종류들[k] in ("제목", "제목번호"):
                return False
            if 종류들[k] == "상위":
                return True
        return False

    def 번호값(i):
        return int(번호.match(줄들[i][1]).group(1))

    def 뒤에_이어짐(i):
        """i('1.' 로 시작하는 딸린 번호 줄)의 소속이 끝난 뒤 번호가 이어지면(k+1) True — 그 번호들은 절이다."""
        k, j = 1, i + 1
        while j < len(줄들) and 종류들[j] not in ("상위", "로마", "붙임", "제목", "제목번호"):
            if 종류들[j] == "번호" and 번호값(j) == k + 1:
                k += 1
            j += 1
        while j < len(줄들):
            t = 종류들[j]
            if t == "붙임":
                return False
            if t == "번호":
                return 번호값(j) == k + 1
            j += 1
        return False

    def 항목세기(lv):
        마디[lv] += 1
        if 절:
            절[-1]["항목수"] += 1

    소속, 여는, 끝번호 = None, -1, None      # 소속: "상위"(□ 아래)·"제목"(DOCX 제목 스타일 아래)·"붙임"·None
    for i, (수준, 줄) in enumerate(줄들):
        t = 종류들[i]
        if t == "조":
            조문수 += 1
            continue
        if t in ("날짜", "그림") or i in 머리들:
            continue
        if t == "상위":
            절.append({"제목": 상위.match(줄).group(2).strip()[:40], "항목수": 0})
            소속, 여는, 끝번호 = "상위", i, None
            continue
        if t == "로마":
            소속, 여는, 끝번호 = None, i, None
            continue
        if t == "붙임":
            m붙 = _re.match(r"^\s*(?:[-*]\s*)?붙\s*임\s*(\d+)\s*\.", 줄)
            소속, 여는, 끝번호 = "붙임", i, (int(m붙.group(1)) if m붙 else 0)
            continue
        if t == "목록":
            항목세기(2)
            continue
        if t in ("번호", "제목번호"):
            n = 번호값(i)
            if t == "번호" and 소속 == "붙임":
                if n == 끝번호 + 1:            # 붙임 목록이 이어진다('붙임 1. …' 다음 '2. …', '붙임' 다음 '1. …')
                    끝번호 = n
                    continue
                소속, 끝번호 = None, None      # 이어지지 않으면 붙임이 끝났다 — 보통 번호 줄로 본다(아래)
            if t == "번호" and 소속 in ("상위", "제목"):
                if 끝번호 is not None and n == 끝번호 + 1:
                    끝번호 = n
                    항목세기(2)
                    continue
                if (끝번호 is None and n == 1 and all(종류들[k] == "그림" for k in range(여는 + 1, i))
                        and not 뒤에_이어짐(i)):
                    끝번호 = 1
                    항목세기(2)
                    continue
            절.append({"제목": 번호.match(줄).group(2).strip()[:40], "항목수": 0})
            소속 = "제목" if (t == "제목번호" and 제목규칙 and i != 제목i) else None
            여는, 끝번호 = i, None
            continue
        for rx, lv in ((하위, 2), (셋째, 3), (넷째, 4)):
            if rx.match(줄):
                항목세기(lv)
                break
        else:
            if t == "제목":
                if 절수준 and 수준 == 절수준 and 제목규칙 and not _장제목(i):  # Title·소개 문단 뒤 첫 제목 수준의 번호 없는 제목 = 절
                    절.append({"제목": 줄.strip()[:40], "항목수": 0})
                소속 = "제목" if (제목규칙 and i != 제목i) else None
                여는, 끝번호 = i, None

    뼈대 = {
        "절": [x["제목"] for x in 절],
        "절수": len(절),
        "절당_항목": [x["항목수"] for x in 절],
        "위계_깊이": max([lv for lv, n in 마디.items() if n] or [0]),
        "마디수": 마디,
        "표": 표수,
        "조문수": 조문수,
    }
    # 뼈대→장르 귀띔의 문턱(조문수·절수 ≥5)은 규칙이라 build/판별로직.py 에 있다(로컬 실행 — 위 판정 주석 참고).
    귀띔 = 자료뿌리.모듈("판별로직").서식귀띔(뼈대)
    결과 = {"ok": True, "값": {"뼈대": 뼈대, "읽은것": 귀띔, "파일": r["파일"]}}
    if r.get("경고"):
        결과["경고"] = r["경고"]      # 스캔 쪽을 OCR 로 못 읽어 뼈대가 모자랄 수 있다(_kordoc)
    return 결과


# ── AI 대기열 — 키 없이 쓰는 길 ─────────────────────────────────────────
# 웹앱이 모델을 부르는 길은 둘이다.
#   ① 사장님 키로 브라우저가 직접 부른다(자동, 빠름)
#   ② **키 없이** 여기에 요청을 남기면 채팅에 붙은 Claude 가 집어 간다(사람이 낀다)
# ②가 있어야 키 없는 사람도 쓸 수 있고, 무엇보다 **판단이 필요한 자리에 사람이 낀다**.

def _대기():
    """AI 대기열 — 자료라서 자료뿌리를 탄다. 모듈 상수로 두면 주입점이 사라진다(G-1)."""
    return 자료뿌리.요청뿌리()


def _요청길(rid):
    안 = os.path.abspath(_대기())
    참 = os.path.abspath(os.path.join(안, os.path.basename(str(rid)) + ".json"))
    return 참 if 참.startswith(안 + os.sep) else None


# ── 서버 기본 LLM(웹앱 전용) ──────────────────────────────────────────────
# 키가 없거나 서버 제공에 동의한 사용자를, **서버가 대신** 부른다(출시계획 1-3 ②).
# MCP·스킬은 호출자가 이미 LLM 을 쥐고 있어 이 길을 안 탄다(웹앱만). 키는 **환경변수나
# 설정.json 에만** 있고 브라우저로 절대 안 나간다 — 그래서 서버가 프록시한다(브라우저
# 직접 호출은 CSP·키 노출 때문에 서버 기본 키엔 못 쓴다). 키는 이 아래 함수들이 **헤더로만**
# 실어 보내고, 응답·화면·로그 어디에도 담기지 않는다.
_기본LLM베이스 = "https://api.featherless.ai/v1"   # Featherless(OpenAI 호환) 기본. env·관리자로 바꾼다.


def _서버LLM설정():
    """서버 기본 LLM 설정 — **환경변수 우선**, 없으면 설정.json 의 llm. 키가 없으면 None
    (→ 서버가 안 부르고 요청을 대기열에 남긴다, 채팅이 채운다). 반환 dict 의 '키'는 이
    함수 밖(응답·로그)으로 절대 나가면 안 된다."""
    env = os.environ
    if env.get("문서지능_LLM키"):
        return {"키": env["문서지능_LLM키"], "모델": env.get("문서지능_모델", ""),
                "베이스": env.get("문서지능_LLM베이스") or _기본LLM베이스,
                "제공자": env.get("문서지능_LLM제공자") or "openai호환"}
    llm = _설정읽기().get("llm") or {}
    if llm.get("키"):
        return {"키": llm["키"], "모델": llm.get("모델") or "",
                "베이스": llm.get("베이스") or _기본LLM베이스,
                "제공자": llm.get("제공자") or "openai호환"}
    return None


@등록("기본안내", 설명="키 없이 쓸 때 보이는 기본 모델 안내(관리자가 정함)와 서버 LLM 유무 — 키·주소는 안 낸다",
    en="defaultnote")
def 기본안내():
    """웹앱 탑바가 키 없이 진행할 때 뭘 보여줄지 — **공개 읽기**(관리자 게이트 없음)다.
    관리자가 모델을 바꾸면 안내 문구도 관리자 면에서 바꾸고, 그 문구를 여기서 앱에 내려 준다.
    **키·베이스 URL 은 절대 안 담는다** — 문구(표시)와 서버 LLM 있음/없음만 낸다."""
    llm = _설정읽기().get("llm") or {}
    return {"ok": True, "값": {"표시": llm.get("표시") or "", "서버있음": bool(_서버LLM설정())}}


def _베이스URL검증(url):
    """서버측 base URL 을 검증한다 — **SSRF 방어**. 반환 (정규화url, None) 또는 (None, 오류).

    서버가 이 주소로 키를 실어 POST 하므로, 악의적 주소(내부망·클라우드 메타데이터)를
    넣으면 내부 접근·키 유출이 된다. 관리자만 설정하지만(게이트됨) 실수·탈취 대비 방어심화다.
      · https 만 — 단 로컬 Ollama(http://localhost)는 명시 예외.
      · 사설·링크로컬·루프백·예약 IP 차단(169.254.169.254 등 메타데이터 포함).
      · 빈 값은 허용(제공자 기본값으로 폴백).
    한계(정직히): 호스트명이 나중에 사설 IP 로 풀리는 DNS 재바인딩까지는 문자열 검증으로
    못 막는다 — 관리자 신뢰가 전제이고, 배포 시 이그레스 방화벽으로 덮는 게 정석이다.
    """
    import ipaddress, urllib.parse
    url = (url or "").strip()
    if not url:
        return "", None                       # 빈 값 = 제공자 기본값 폴백(허용)
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return None, "URL 을 해석할 수 없습니다"
    host = (u.hostname or "").lower()
    if u.scheme not in ("https", "http") or not host:
        return None, "http/https 주소여야 합니다"
    로컬 = host in ("localhost", "127.0.0.1", "::1")
    if u.scheme == "http" and not 로컬:
        return None, "원격 주소는 https 만 됩니다(http 는 로컬 Ollama 예외)"
    if host in ("169.254.169.254", "metadata", "metadata.google.internal"):
        return None, "클라우드 메타데이터 주소는 막혀 있습니다(SSRF 차단)"
    if not 로컬:
        try:
            ip = ipaddress.ip_address(host)
            if (ip.is_private or ip.is_link_local or ip.is_loopback
                    or ip.is_reserved or ip.is_multicast):
                return None, "사설·내부 IP 로는 못 나갑니다(SSRF 차단)"
        except ValueError:
            pass                              # 호스트명이면 통과(원격 https) — DNS 재바인딩은 배포 방화벽 몫
    return url, None


def _LLM온도(명시만=False):
    """서버 모델 호출의 temperature — **몸에 안 실으면 제공자 기본값(1.0 안팎)이 나가
    작은 모델일수록 글자가 깨진다**(bench3 exaone-s6 실측: 라이브 EXAONE 4.0 32B 가
    '스코지 공사 총무총 무억헤너트로노' 류로 깨지고 점수 2.33 — 온도만 0.3 으로 바꾼 A/B
    (bench3/runs/Pt)에서 3.28·6/6 성공. r10 구현자B, 2026-09-27).

    우선순위: **관리자 설정 llm.온도** → **환경변수 문서지능_LLM온도** → (명시만 이면 None,
    아니면) **0.3**(회귀 기본값). openai호환 제공자는 이 값을 몸에 먼저 넣고 그 뒤
    llm.본문추가(관리자가 손수 얹는 값)로 덮어쓴다 — 본문추가에 temperature 가 있으면
    그게 이긴다(호출부의 순서가 그 우선순위를 보장한다, 여기서 본문추가는 안 본다).
    범위는 0~2(관리자 저장 때도 같은 범위로 잠근다, _온도검증).

    `명시만=True` — **관리자·환경변수가 실제로 값을 뒀을 때만** 돌려주고, 아무 데도
    없으면 0.3 으로 내려가지 않고 None 을 낸다(r10 재검토, HIGH 반박 수용). anthropic
    갈래가 쓴다 — 현행 Claude(Sonnet 5·Opus 4.7 이상)는 temperature 를 기본값이 아닌
    값으로 조금만 건드려도 **그 요청 자체를 400 으로 거부한다**(claude-api 스킬의
    shared/model-migration.md, Sampling 행: 'Removed - 400'). 글자깨짐의 실제 원인은
    소형 openai호환 모델(EXAONE 등)이라, anthropic 갈래에 매번 0.3 을 강제로 실으면
    최신 Claude 를 쓰는 모든 서버 호출이 깨진다 — 관리자가 (구세대 anthropic 모델처럼
    temperature 를 실제로 받는 모델을 위해) 명시적으로 설정했을 때만 싣는다."""
    llm = _설정읽기().get("llm") or {}
    for 값 in (llm.get("온도"), os.environ.get("문서지능_LLM온도")):
        if 값 is None or str(값).strip() == "":
            continue
        try:
            n = float(값)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= 2:
            return n
    return None if 명시만 else 0.3


def _온도검증(v):
    """0~2 범위의 실수만 받는다(temperature 계약) — 밖이거나 못 읽으면 None(저장 거부 신호)."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 2 else None


def _JSON뽑기(글):
    """모델이 ```json 울타리나 앞뒤 산문을 붙여도 3층 JSON 객체만 뽑는다."""
    글 = (글 or "").strip()
    if 글.startswith("```"):
        조각 = 글.split("```")
        글 = 조각[1] if len(조각) >= 2 else 글
        if 글.lower().startswith("json"):
            글 = 글[4:]
    a, b = 글.find("{"), 글.rfind("}")
    if a >= 0 and b > a:
        글 = 글[a:b + 1]
    return json.loads(글)


# LLM 동시 호출을 상류 제공자 상한(Featherless 동시 2 등)에 맞춘다 — 초과분은 탈락이
# 아니라 세마포에서 **대기**한다(2026-08-12 실측: 큐가 없어 429→즉시재시도→'실패'였다).
# 세마포는 이 프로세스 안의 동시 호출을 막을 뿐이다 — 여러 인스턴스로 늘리면 공유
# 카운터(예: Redis)로 다시 봐야 한다(지금은 단일 프로세스라 충분).
_LLM세마포 = threading.BoundedSemaphore(int(os.environ.get("문서지능_LLM동시") or 2))
_LLM대기최대초 = int(os.environ.get("문서지능_LLM대기초") or 240)


def _서버LLM호출(지시문, 자료, 예시=None, 장르=None):
    """동시 호출을 세마포로 상류 상한에 맞추는 래퍼 — 초과분은 대기한다(탈락 아님).
    실제 호출은 _LLM호출_실제. 대기 시간이 한도를 넘으면 사람말로 알린다."""
    if not _서버LLM설정():
        return None
    if not _LLM세마포.acquire(timeout=_LLM대기최대초):
        raise RuntimeError("동시 생성 요청이 많아 대기 시간을 초과했습니다 — 잠시 후 다시 시도해 주세요")
    try:
        return _LLM호출_실제(지시문, 자료, 예시, 장르)
    finally:
        _LLM세마포.release()


def _자료글(자료):
    """`자료` 인자를 판정·조립용 문자열 하나로 통일한다 — 자료는 문자열이거나(직접 붙여
    쓴 글) 리스트(여러 조각을 배열로 낸 것, SKILL.md 예시·app.html·MCP 클라이언트가 흔히
    이 모양으로 보낸다)로 올 수 있다. 리스트면 줄바꿈으로 이어 붙인다 — 문자열이 아닌
    조각(dict 등)은 JSON 으로 편다(cli:s2 수정, e2e r6 재진단 '26-09-27 — 예전엔
    str(자료)로 그냥 문자열화해 배열이 "['…']" 꼴 그대로 들어가, 판정(detect)의 낱말
    매칭·유형 판별이 자료 속 낱말을 못 찾아 조용히 다른 장르로 판정됐다). 아래
    _LLM호출_실제 가 먼저 쓰던 것과 같은 규칙이다(그쪽은 OpenAI 호환 제공자가 리스트
    content 를 422 로 거부해 문자열화가 필요했다) — 여기서 하나로 모은다."""
    if isinstance(자료, str):
        return 자료
    if isinstance(자료, (list, tuple)):
        return "\n".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
                          for x in 자료)
    return str(자료 or "")


def _LLM호출_실제(지시문, 자료, 예시=None, 장르=None):
    """설정된 제공자로 초안 3층 JSON 을 받아 온다. 키는 **헤더로만** 나가고 로그·응답엔 안 담긴다.
    제공자: openai호환(Featherless·Ollama·OpenAI·custom) / anthropic. 없으면 None."""
    import urllib.request, urllib.error
    cfg = _서버LLM설정()
    if not cfg:
        return None
    # max_tokens 우선순위: **장르별 관리자 설정** → 전역 세션당상한(하위호환) → **장르별 코드 기본값**.
    # (풀버전은 JSON 이 커서 넉넉히 — 안 그러면 배열 중간에서 잘려 반토막 JSON 이 난다. 관리자가
    #  장르마다 따로 상한을 줄 수 있다 — 사장님 지적으로 저장만 되던 걸 실제 연결·장르 분리, '26-08-19.)
    _llm설정 = _설정읽기().get("llm") or {}
    _장르토큰 = _llm설정.get("장르토큰") if isinstance(_llm설정.get("장르토큰"), dict) else {}
    # slides 12000 → 4000('26-09-29 bench11 ⑱ 실측): 서버 모델(EXAONE) 슬라이드 초안 JSON 은 최대 3.3천 자(초안 사례),
    # 정상 초안의 출력은 845~995 토큰(5건, 약 2.2자/토큰)이고, 강한 모델 12장 덱(5.8천 자)도 약 2.6천 토큰이다.
    # 나머지 5건은 끝없이 이어 쓰다 상한에서 잘렸다(6000 토큰 = 106~116초, 약 53토큰/초) — 12000 이면 180초 시간
    # 초과를 넘겨 제공자 쪽에서 계속 돌고(동시 1 키) 다음 되시도가 그 뒤에 줄을 섰다. 4000 이면 헛돈 호출도 약 75초에 끝난다.
    _장르기본 = {"fullreport": 16000, "press": 12000, "regulation": 12000, "slides": 4000, "gongmun": 8000}.get(장르 or "", 8000)
    def _양의(x):
        try:
            return int(x) if x and int(x) > 0 else 0
        except (TypeError, ValueError):
            return 0
    최대토큰 = _양의(_장르토큰.get(장르)) or _양의(_llm설정.get("세션당상한")) or _장르기본
    # 자료는 대개 리스트(타입맵 "자료": list)다 — 문자열로 합쳐야 한다. 리스트를 그대로
    # content 에 실으면 OpenAI 호환 제공자가 422("messages.content Invalid input")로 막는다
    # (2026-08-13 Featherless 실측). _자료글 이 문자열·리스트 모두 같은 규칙으로 잇는다.
    사용자글 = _자료글(자료)
    if 예시:
        사용자글 += "\n\n[참고 예시]\n" + json.dumps(예시, ensure_ascii=False)
    if cfg["제공자"] == "anthropic":
        정상, 오류 = _베이스URL검증(cfg["베이스"] or "https://api.anthropic.com")
        if 오류:
            raise ValueError(f"서버 주소가 안전하지 않습니다: {오류}")   # 키는 안 담긴다
        url = (정상 or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        헤더 = {"x-api-key": cfg["키"], "anthropic-version": "2023-06-01",
              "content-type": "application/json"}
        몸 = {"model": cfg["모델"], "max_tokens": 최대토큰, "system": 지시문,
             "messages": [{"role": "user", "content": 사용자글}]}
        # temperature — **기본으로는 안 싣는다**(r10 재검토, HIGH). 현행 Claude(Sonnet 5·
        # Opus 4.7 이상)는 이 값을 조금만 건드려도 요청째 400 으로 막는다(_LLM온도 명시만
        # 인자 docstring 참고) — 글자깨짐의 원인은 소형 openai호환 모델이지 anthropic 이
        # 아니다. 관리자가 llm.온도 를 실제로 뒀을 때만(예: temperature 를 받는 구세대
        # anthropic 모델) 싣고, anthropic 실제 계약(0~1)에 맞춰 자른다(_온도검증 은 저장
        # 때 0~2 까지 받는다 — 그 값을 그대로 anthropic 에 보내면 1 을 넘는 값이 거절될
        # 수 있어 호출 시점에 한 번 더 자른다).
        _명시온도 = _LLM온도(명시만=True)
        if _명시온도 is not None:
            몸["temperature"] = min(_명시온도, 1.0)
    else:                                    # openai호환 — Featherless·Ollama·OpenAI·custom
        정상, 오류 = _베이스URL검증(cfg["베이스"] or _기본LLM베이스)   # SSRF 방어(호출 시점)
        if 오류:
            raise ValueError(f"서버 주소가 안전하지 않습니다: {오류}")
        베이스 = (정상 or _기본LLM베이스).rstrip("/")
        url = 베이스 + ("/chat/completions" if 베이스.endswith("/v1") else "/v1/chat/completions")
        헤더 = {"Authorization": "Bearer " + cfg["키"], "content-type": "application/json"}
        # JSON 모드 — 모델이 **유효 JSON 만** 뱉게 강제한다(작은 모델의 쉼표 누락 등 문법
        # 오류 방지, 2026-08-10 실측). OpenAI 호환 제공자 대부분 지원(Featherless 포함).
        몸 = {"model": cfg["모델"], "response_format": {"type": "json_object"},
             "max_tokens": 최대토큰,          # 안 주면 제공자 기본값에서 잘려 반토막 JSON 이 난다
             # 이 갈래(Featherless·Ollama 등)는 기본값 0.3 을 그대로 싣는다 — 글자깨짐이
             # 실측된 자리가 여기다(_LLM온도 참고). anthropic 갈래와 달리 명시만=True 를
             # 안 쓴다 — 소형 openai호환 모델은 temperature 를 받아야 글자가 안 깨진다.
             "temperature": _LLM온도(),
             "messages": [{"role": "system", "content": 지시문},
                          {"role": "user", "content": 사용자글}]}
        # 제공자·모델별 추가 요청 옵션 — 추론(thinking) 모델은 기본으로 토큰을 추론에 다 써
        # 본문이 빈 채 돌아온다('26-09-27 Featherless Qwen3.8-27B 실측: content 빈 값).
        # {"chat_template_kwargs": {"enable_thinking": false}} 같은 값을 env(JSON)나 설정.json
        # llm.본문추가 로 얹는다. model·messages·response_format 은 덮지 못하게 막는다.
        _추가 = os.environ.get("문서지능_LLM본문추가") or _llm설정.get("본문추가")
        if _추가:
            try:
                _추가 = json.loads(_추가) if isinstance(_추가, str) else _추가
            except ValueError:
                _추가 = None
            if isinstance(_추가, dict):
                몸.update({k: v for k, v in _추가.items() if k not in ("model", "messages", "response_format")})
    # User-Agent — 안 붙이면 urllib 기본값('Python-urllib/…')이 Cloudflare 봇 차단(error 1010,
    # HTTP 403)에 걸린다(Featherless 가 CF 뒤에 있다, 2026-08-10 실측). 정식 클라이언트 UA 를 붙인다.
    헤더.setdefault("User-Agent", "artifact-intelligence/1.0 (+https://github.com/Kminer2053/Artifact-Intelligence-public)")

    def _보내기(몸):
        req = urllib.request.Request(url, data=json.dumps(몸).encode("utf-8"),
                                     headers=헤더, method="POST")
        _t0 = time.monotonic()
        with _HTTP열기.open(req, timeout=180) as r:
            답 = json.load(r)
        # 시간·토큰 실측 한 줄(키·본문 없음) — 상한·시간 초과를 실측으로 고르려고('26-09-29 ⑱)
        _u = 답.get("usage") if isinstance(답, dict) else None
        _끝 = (((답.get("choices") or [{}])[0].get("finish_reason")) if isinstance(답, dict) and 답.get("choices")
              else (답.get("stop_reason") if isinstance(답, dict) else None))
        sys.stderr.write(f"[서버LLM] {장르 or '-'} {time.monotonic() - _t0:.1f}초 상한 {최대토큰} "
                         f"입력 {(_u or {}).get('prompt_tokens', (_u or {}).get('input_tokens', '?'))} "
                         f"출력 {(_u or {}).get('completion_tokens', (_u or {}).get('output_tokens', '?'))} 끝 {_끝}\n")
        return 답

    try:
        답 = _보내기(몸)
    except urllib.error.HTTPError as e:
        # 제공자 응답 본문(왜 막혔나 — 모델 없음·권한 등)을 진단에 싣는다. **키는 요청
        # 헤더에만 있고 응답 본문엔 없다** — 로그·오류에 담겨도 유출이 아니다.
        몸글 = ""
        try:
            몸글 = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        # temperature 를 문제 삼는 400 이면 그 키만 빼고 한 번 더 부른다(r10 재검토, HIGH).
        # anthropic 갈래는 이제 명시적으로 설정했을 때만 temperature 를 싣지만, 관리자가
        # 그렇게 설정해 둔 모델이 하필 이 값을 안 받는 최신 모델로 바뀌는 경우·openai호환
        # 갈래의 추론(reasoning) 계열 모델이 temperature 를 거부하는 경우 둘 다를 덮는
        # 마지막 방어선이다 — 대부분의 호출은 이 문턱을 아예 안 밟는다.
        if e.code == 400 and "temperature" in 몸 and re.search("temperature", 몸글, re.IGNORECASE):
            몸 = {k: v for k, v in 몸.items() if k != "temperature"}
            try:
                답 = _보내기(몸)
            except urllib.error.HTTPError as e2:
                몸글2 = ""
                try:
                    몸글2 = e2.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                raise RuntimeError(f"제공자 HTTP {e2.code}: {몸글2}")
        else:
            raise RuntimeError(f"제공자 HTTP {e.code}: {몸글}")
    if cfg["제공자"] == "anthropic":
        글 = "".join(b.get("text", "") for b in (답.get("content") or []))
    else:
        글 = (((답.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    return _JSON뽑기(글)


def _시간초과인가(e):
    """읽기·연결 시간 초과인가 — socket.timeout(=TimeoutError) 이나 그걸 품은 URLError."""
    import socket as _so
    import urllib.error as _ue
    if isinstance(e, (TimeoutError, _so.timeout)):
        return True
    return isinstance(e, _ue.URLError) and isinstance(getattr(e, "reason", None), (TimeoutError, _so.timeout))


def _서버채움(rid, 열쇠):
    """서버가 대기열 요청을 스스로 채운다(응답주기와 같은 자리에 쓴다). 세션 열쇠는
    스레드지역이라 붙잡아 넘겨 다시 끼운다(작업시작 돌기 와 같은 이유). 실패는 상태='실패'
    +오류(유형만)로 남긴다 — **키·헤더는 오류·응답 어디에도 안 담는다**."""
    with 자료뿌리.세션갈기(열쇠):
        길 = _요청길(rid)
        if not 길:
            return
        try:
            본 = json.load(open(길, encoding="utf-8"))
        except Exception:
            return
        지시문 = 본.get("지시문") or ""
        자료 = 본.get("자료") or ""
        예시 = 본.get("예시")
        장르 = 본.get("장르")             # 장르별 max_tokens 기본값에 쓴다(풀버전은 넉넉히)
        # 작은 모델(예: gemma-4-E4B)은 JSON 모드를 켜도 이따금 반토막·잡말 섞인
        # JSON 을 낸다. 파싱까지 성공한 답이 나올 때까지 몇 번 되시도한다. doc 이
        # None 이면 키가 사라진 것이라 되시도 없이 대기로 되돌린다(채팅 폴백).
        doc, 마지막오류, 키사라짐 = None, None, False
        for 시도 in range(3):
            try:
                doc = _서버LLM호출(지시문, 자료, 예시, 장르)
                if doc is None:      # 키 없음 → 되시도 무의미, 대기로
                    키사라짐 = True
                    break
                break                # 유효 3층 JSON 확보
            except Exception as e:
                마지막오류 = e       # 대개 JSONDecodeError — 다음 회차에서 다시
                if 시도 < 2:         # 백오프 — 429·일시 오류에 상류를 즉시 두들기지 않는다
                    import time as _t2
                    # 읽기 시간 초과 뒤엔 길게 쉰다('26-09-29 bench11 ⑱ 실측: EXAONE 시간 초과 사례 중 사례은 바로 앞
                    # 호출도 시간 초과 — 끊긴 요청이 제공자 쪽에서 계속 돌아(동시 1 키) 1.5초 뒤 되시도가 그 뒤에 섰다)
                    _t2.sleep(20.0 if _시간초과인가(e) else 1.5 * (시도 + 1))
        if doc is not None:
            # 슬라이드 v2 초안이면 '서버 모델이 쓴 것' 표지를 단다 — 새문서가 이 표지를 보고 약한 경로 자료 대조(값 칸
            # 지어냄·날짜·비교 기준·판단 인과 hard)를 켠 뒤 표지는 떼고 등록한다('26-09-29 bench13 ③④). 표지를 떼고 보내도
            # 강한 경로 검사로 돌 뿐이다(막는 장치가 아니라 되먹임을 고르는 표지다)
            if 장르 == "slides" and isinstance(doc, dict) and doc.get("판형") == "v2":
                doc["_서버모델"] = True
            본["답"] = doc
            본["상태"] = "됐음"
        elif 키사라짐:
            본["답"] = None
            본["상태"] = "기다림"    # 키 사라졌으면 도로 대기(채팅 폴백)
        else:
            본["상태"] = "실패"
            본["오류"] = f"서버 모델 호출에 실패했습니다 ({type(마지막오류).__name__})"   # 유형만, 키 없음
            sys.stderr.write(f"[서버LLM] {rid} 실패(3회): {type(마지막오류).__name__}: {마지막오류}\n")
        try:
            자료뿌리.원자json(길, 본, indent=1)
        except Exception as e:
            sys.stderr.write(f"[서버LLM] {rid} 결과 못 씀: {type(e).__name__}: {e}\n")


# ── 서버측 지시문 조립(온톨로지 유출 차단, 2026-08-12 사장님 지침) ─────────
# 예전에는 브라우저(app.html)가 규칙모으기()로 온톨로지 6종을 통째로 당겨 지시문()
# 을 조립했다 — 12유형 판별신호(크라운주얼)까지 프롬프트에 실려 브라우저에 노출됐다.
# 이제 **판정도 조립도 서버가 한다.** 판별신호는 여기서만 읽고, 프롬프트에는 판정된
# 유형 하나의 시퀀스만 넣는다(온톨로지는 통째로 안 내린다 — 최소만 나간다).
def _유형판정(자료):
    """자료 글에서 1p 12유형을 **판별키워드 매칭**으로 점수내어 최고 유형을 고른다.
    판별신호(정본 노하우)는 이 함수 안에서만 읽고, 결과(선택 유형)만 조립에 넘긴다."""
    types = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
    글 = _자료글(자료)      # cli:s2 수정 — 자료가 배열이어도 낱말 매칭이 되게 문자열로 통일
    best, best점 = None, -1
    for t in types:
        점 = sum(1 for w in (t.get("판별키워드") or []) if str(w) in 글)
        if 점 > best점:
            best점, best = 점, t
    return best or (types[0] if types else None)


def _유형점수(자료):
    """12유형을 판별키워드로 각각 점수낸다 — 1단계에서 사용자에게 보여줄 추천·후보용.
    판별키워드 원문은 내지 않고 이름·점수·두루뭉술한 까닭만 담는다(판별 노하우는 서버에만)."""
    types = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
    글 = _자료글(자료)      # cli:s2 수정 — 자료가 배열이어도 낱말 매칭이 되게 문자열로 통일
    out = []
    for t in types:
        n = sum(1 for w in (t.get("판별키워드") or []) if str(w) in 글)
        out.append({"id": t.get("id"), "label": t.get("label"), "점": n,
                    "까닭": (f"목적 신호 {n}곳" if n else "")})
    out.sort(key=lambda x: -x["점"])
    return out


def _장르정본(장르명):
    """등록부(장르) → 정본 키. genres 가 세어 주는 목록에서 찾는다(손매핑 안 한다)."""
    for g in (장르().get("값", {}).get("장르") or []):
        if g.get("등록부") == 장르명:
            return g.get("정본")
    return "onepage-report"


_아이콘목록캐시 = None


def _아이콘목록():
    """슬라이드 픽토그램 라이브러리의 아이콘 이름(정본: build/pictograms.json 의 키, 32개).
    프롬프트에 실어 모델이 없는 아이콘을 지어내지 않게 한다(실측 2026-09-02: EXAONE 가
    'building'·'brain'·'people' 를 지어내 게이트에 반복해 걸렸다). pictogram.has 와 같은 집합."""
    global _아이콘목록캐시
    if _아이콘목록캐시 is None:
        try:
            with open(os.path.join(ROOT, "build", "pictograms.json"), encoding="utf-8") as f:
                _아이콘목록캐시 = sorted(json.load(f).keys())
        except Exception:
            _아이콘목록캐시 = []
    return _아이콘목록캐시


# 밑줄(_) 키 필터 — 낱말 목록에서 **명시 허용 목록**으로 바꾼다(F4+rules:F9, '26-09-27
# 재진단). 예전엔 "이 낱말들 중 하나가 이름 어딘가에 있으면 거른다"(_메타키말·_주석키말,
# 2026-09-07·09-26)였다 — 낱말 하나로는 두 방향 다 틀렸다. ① "정정"이 들어간 **진짜
# 규칙** _압축이름_정정까지 걸러졌다(압축형은 절을 빼는 것, 남기는 절은 표준형 이름
# 그대로 — 아래 허용목록으로 되살렸다). ② 어느 낱말도 안 걸리는 **개발·조립기 메모**는
# 그대로 새어 나갔다 — _어디에_있나("build/stylelint.py 의 REQUEST_TYPES … verify_all 의
# check_summary_end_sync() 가 본다")·_용법("build/assemble_full.py 의 _연속쓰기_기준()
# 이 이 값을 읽는다")·_css_ref("build/tokens.css …")·_조판무관("slide_overflow 측정
# 밖")·_새쪽_조건부_2026_09_26(조립기 페이지 넘김 알고리즘 자체 — 왜·어떻게·기준._용법
# 까지 통째로) 가 실제 조립한 지시문(6개 장르)에서 확인됐다(내부 기록·f9 재현).
#
# ontology 의 document_types·shared·writing_profiles·entities 아래 밑줄 키 134개를
# (build/판별로직.py 와 달리 이 파일엔 온톨로지 접근이 있다) 전수 읽고 나눴다 — 아래
# 목록에 **없는** 밑줄 키는 전부 개발·조립기 메모로 보고 뺀다(과다 노출 아닌 쪽을
# 기본으로 둔다 — 새 밑줄 키가 늘어도 여기 안 넣으면 조용히 빠질 뿐, 예전처럼 조용히
# 새지는 않는다). 각 항목 옆 주석이 "왜 작성 규칙인가"의 근거다. _메타키인가·_주석키인가
# 둘 다 이 하나의 허용목록을 쓴다(약한모델 경로 _프롬프트용정리 도 _메타키인가 를 거치므로
# 같이 좋아진다 — 다만 이 변경은 그 경로의 **길이 한도**(잘라내는 자리)는 그대로 둔다,
# 잘리기 전 내용이 조금 더 정확해질 뿐이다).
_규칙키_허용목록 = frozenset({
    "_원칙",           # "예시 양식이 있으면 그 실측을 따르고, 없을 때만 이 기본값" — 값을 정하는 규칙
    "_제목길이",        # "장 20자·절 30자 상한" — 그대로 지킬 수치 그 자체
    "_내부보고_시퀀스",  # 유형별 절 순서 뼈대(배경·경과→현황·분석→검토(안)→기대효과…) — 목차 그대로 쓴다
    "_첫단계",         # "테마 선택은 편집의 거의 첫 단계에서 한다" — 순서 규칙
    "_압축이름_정정",    # 압축형 절 이름 대응(옛 이름→표준형 이름 그대로 남긴다) — 그대로 써야 하는 이름
    "_note",          # "□○-* 전용, 체계 B(Ⅰ.1.가.)는 혼용 금지" — 위계 기호 규칙
    "_고르는_차례",      # 값을 정하는 우선순위(① 사용자값 → ② 예시 양식 실측 → ③ 유형별 기본값)
    "_공통",          # 제정이유·주요내용을 제명과 제1조 사이에 두는 배치 규칙(조 번호 안 매김)
    "_기본은_흐름",      # 슬라이드 배치모드 기본값(흐름)과 자유배치를 쓰는 조건
    "_노트",          # "발표자 노트는 MVP 제외" — 범위 제약(쓰지 않는다)
    "_마커_판정",       # "○ 를 원칙으로, ◦ 도 고를 수 있다" — 위계 마커 선택 규칙
    "_목적에_맞게",      # 슬라이드 테마를 주제·청자·격식에 맞춰 고르는 규칙(대외=네이비/자목 …)
    "_목차_실측",       # 이름은 "_실측"이지만 내용이 곧 규칙이다 — 쪽수별 목차 포함/생략 문턱
    # (api:F4 수정, e2e r6 재진단 '26-09-27) — 옛 필터(_메타키말·_주석키말)엔 실리고 이
    # 허용목록엔 없어 빠졌던 진짜 작성 규칙 9개(+_정의). 전부 코드·파일 경로를 안 가리키는
    # 순수 규칙값임을 ontology.json 전수 스캔으로 확인했다(re.search(r"\.py\b|build/|
    # assemble_|_기준\(\)" …) 매치 0건) — _새쪽_조건부_2026_09_26._용법 처럼 코드 경로를
    # 가리키는 자리는 그 **부모 키 자체**가 이 허용목록에 없어 여전히 안 실린다(이름만으로
    # 거르므로 부모가 막히면 그 안의 자식도 통째로 안 내려간다).
    "_기본",          # 위계_카탈로그._기본="도형식", 스타일_변형._기본="사내표준형" 등 — 선택 기본값
    "_선택",          # gongmun 끝표시._선택="기본은 같은줄" — 선택 가능한 값과 기본
    "_선택_위치",       # 위계_카탈로그._선택_위치 — 무엇을 언제(몇 층) 고르는가
    "_용법",          # 장_시퀀스_카탈로그._용법("유형 불명 시 계획서형이 기본") 등 — 이 값을 어떻게 쓰는가
    "_언제",          # slides 배치._언제 — 자유배치를 쓰는 조건(_기본은_흐름 은 이걸 담는다고 오분류돼 있었다)
    "_읽는_법",        # 검토보고._읽는_법 — 절 순서를 어떻게 읽는가(첫 절에 결론 안 놓기 등)
    "_눈에_띄는_것",     # 결과보고._눈에_띄는_것 — 표본에서 두드러지는 구성 특징
    "_보도자료만_예외",   # shared.제목_문체._보도자료만_예외 — 제목 종결 문체의 장르별 예외
    "_왜",           # gongmun-gyeoksik.긴문장._왜 등 — 규칙의 근거(문체가 왜 그런가)
    "_정의",          # 여러 구조 항목의 정의(예: gongmun 여백._정의="위에서부터 순서대로 본다") — 규칙 그 자체
    "_상태_뜻",        # slides 부품_목록_v2._상태_뜻 — 뱃지는 자료가 상태를 말할 때만(규칙 문장, '26-09-28 적대 검토: 빠지고 있었다)
})


def _메타키인가(k):
    ks = str(k)
    if ks.startswith("_"):
        return ks not in _규칙키_허용목록
    # 밑줄 없는 출처성 키 + **코드·도구 경로 키**(F4+rules:F9 재진단, '26-09-27) — "runner"·
    # "measurer"·"css_genre"·"revise_on_fail"·"산출물"은 밑줄이 없어 위 검사도, 옛 낱말
    # 목록도 안 걸려서 build/render_verify.sh·build/audit.js·build/assemble_*.py·
    # build/tokens.css 같은 코드 경로가 실제 조립한 6개 장르 지시문에 그대로 남았다
    # (재현: grep 'build/'). 이 키들은 조립기가 무엇으로 만드는가를 적어 둔 개발 메모지
    # 작성 규칙이 아니다(작성 모델은 출력 형식·도구를 고르지 않는다).
    # "적용범위"(검토 발견②, '26-09-28 되짚음) — _원칙문() 은 이미 "근거·적용범위는 사람이
    # 볼 온톨로지 주석이지 모델 지시가 아니다"라고 스스로 적어 두고도(바로 아래 _원칙문
    # 정의), 그 옆의 "작성원칙" 통째 JSON 덤프(_문체블록)는 이 필터를 안 거쳐 그 "적용범위"
    # 텍스트를 그대로 실었다 — shared.작성원칙.날짜_기본.적용범위 원문(온톨로지, '조간'은
    # 그 전날 …)이 옛 규칙 그대로 남아 있어, 같은 지시문 안에서 새 규칙(배포일 계산 금지)과
    # 정면으로 부딪혔다(재현: api._지시문조립(…, 장르="press") 출력에 둘 다 실림). 온톨로지
    # 문구 자체는 다른 담당이 고치는 정본이라 손대지 않고, 여기(모델에 낼 지시문을 고르는
    # 필터)에서 _원칙문 이 이미 하던 약속을 raw 덤프에도 지킨다.
    if ks == "적용범위":
        return True
    return ks.endswith("근거") or ks in ("지위", "판정이력", "전거", "출처",
                                       "runner", "measurer", "css_genre", "revise_on_fail", "산출물")
_출처조각 = re.compile(r"\s*[—(\-]?\s*사장님(\s*판정)?[^\n\",.)]*[.)]?")


def _프롬프트용정리(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if _메타키인가(k):
                continue
            out[k] = _프롬프트용정리(v)
        return out
    if isinstance(node, list):
        # 메타키는 **dict 키에만** 의미가 있다(항목 6, '26-09-26 2차 진단) — 목록 속
        # 문자열은 절 제목·개체 이름 같은 규칙 값이지 메타 기록이 아니다. '산출근거'(끝말
        # '근거')·'출처' 처럼 우연히 메타 말과 겹치는 값을 여기서 걸러 왔다가 표준시퀀스·
        # 개체목록에서 진짜 절 이름을 빠뜨렸다. 그래서 목록 항목은 거르지 않는다.
        return [_프롬프트용정리(x) for x in node]
    if isinstance(node, str):
        return _출처조각.sub("", node)
    return node


def _주석키인가(k):
    """밑줄(_) 로 시작하는 키 가운데 **개발·조립기 메모**인가 — _메타키인가 와 같은
    허용목록을 쓴다(둘을 하나로 합쳤다). _지시문조립._절이름자리아래 자리에서 홀로
    쓰인다 — 그 자리는 "근거로 끝나는 밑줄 없는 키"까지 메타로 보는 _메타키인가 의
    나머지 절반을 원하지 않기 때문이다(절 이름 자체가 그런 모양일 수 있어서)."""
    ks = str(k)
    return ks.startswith("_") and ks not in _규칙키_허용목록


# 절 이름이 곧 dict 키로 오는 자리(항목 6, '26-09-26 2차 진단 — types[10].절별_핵심질문.
# 산출근거처럼, 값이 아니라 **키 자체**가 절 제목이다). 일반 메타키 추정("근거"로 끝남 등)이
# 여기서는 오작동해 진짜 절 이름을 지운다 — 이 자리 바로 아래 키만 그 추정을 끈다(더 깊이
# 들어가면 다시 일반 규칙 — 연구 주석(_주석키인가)은 그 안에서도 여전히 거른다).
_절이름키자리 = ("절별_핵심질문",)


def _지시문용정리(node, _절이름자리아래=False):
    """강한 모델용 온전한 지시문 전용 정리 — _프롬프트용정리 에 더해 연구 주석(_원문_대조·
    _필드정의·_구버전_폐기 …)도 걷는다. 규칙을 통째로 싣게 되면서 주석이 지시문 절반을 차지해
    '실제 작성 규칙을 찾기 어렵다'는 작성자 보고가 나왔다('26-09-26 반사실 실험).
    _ref(다른 규칙 가리킴)는 여기서 걷고 _문체블록이 펼쳐 싣는다."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if _절이름자리아래:
                if _주석키인가(k):
                    continue    # 절 이름 자리에서도 연구 주석(_구버전 등)은 그대로 거른다
            elif _메타키인가(k) or _주석키인가(k):
                continue
            out[k] = _지시문용정리(v, _절이름자리아래=(str(k) in _절이름키자리))
        return out
    if isinstance(node, list):
        # 목록 속 문자열은 메타키 추정을 안 받는다 — _프롬프트용정리와 같은 이유(위 주석).
        return [_지시문용정리(x) for x in node]
    if isinstance(node, str):
        return _출처조각.sub("", node)
    return node


# 문체 프로필에서 작성과 무관한 운영 키 — 검사기 경로·골든 테스트·쓰는 곳 목록.
_프로필운영키 = ("검증", "used_by")


def _문체블록(정본):
    """이 장르의 문체 프로필(writing_profiles.<이름>) 본문과 공통 표기 규칙을 지시문 줄로 낸다.

    장르 규칙의 문체 칸은 {"profile": …, "_ref": "writing_profiles.…"} 처럼 **가리킴만** 들고
    있어, 종결어 허용·금지 목록·번역투·hype 금지어·날짜 표기 같은 공통 문체 노하우가 작성
    모델에게 한 글자도 가지 않고 문체검사(사후 게이트)로만 존재했다('26-09-26 진단: api.py 에
    writing_profiles·shared 조회 0건). 쓰기 전에 알려 주려고 여기서 펼친다. 표기·강조·제목 문체는
    글쓴이가 정하는 몫이라 싣고, 글꼴·판면·박스 같은 조판 값은 조립기 몫이라 싣지 않는다."""
    줄 = []
    경고 = []   # 실패를 조용히 버리지 않는다(still_partly 항목 8 재발 — entities·writing_profiles·
               # shared 는 장르 규칙(규칙누락경고)과 같은 방식으로 지시문에 경고 줄을 단다.
    이름결과 = _지식전체(f"document_types.{정본}.writing_profile")
    이름 = 이름결과.get("값")
    if not 이름결과.get("ok"):
        경고.append(f"[!] 정책서버에서 {이름결과.get('로그') or '문체 프로필 이름을 못 받았습니다'} "
                   "— 문체 프로필이 빠졌을 수 있다.")
    if isinstance(이름, str) and 이름:
        프로필결과 = _지식전체(f"writing_profiles.{이름}")
        프로필 = 프로필결과.get("값")
        if not 프로필결과.get("ok"):
            경고.append(f"[!] 정책서버에서 {프로필결과.get('로그') or f'문체 프로필({이름})을 못 받았습니다'}")
        if isinstance(프로필, dict):
            프로필 = {k: v for k, v in _지시문용정리(프로필).items() if k not in _프로필운영키}
            줄 += ["", f"[문체 프로필 — {이름}. 종결·금지 표현을 쓰기 전에 지켜라(문체검사가 같은 규칙으로 잰다)]",
                   json.dumps(프로필, ensure_ascii=False, indent=1)]
    공통 = {}
    # "작성원칙" 추가(항목 8, '26-09-26) — 날짜 기본값·판단 서술 허용 같은 전 장르 공통
    # 작성 원칙의 정본은 shared.작성원칙(온톨로지, 다른 묶음이 채운다). 강한 모델에는
    # 여기서 통째로 실어 보여준다 — 짧은 두 줄(오늘 날짜·판단 서술)은 온전 여부와
    # 무관하게 _지시문조립의 [공통으로 지킬 것]에서 따로 챙긴다(약한모델에도 실리게).
    for k in ("표기", "강조", "제목_문체", "작성원칙"):
        결과 = _지식전체(f"shared.{k}")
        v = 결과.get("값")
        if not 결과.get("ok"):
            경고.append(f"[!] 정책서버에서 {결과.get('로그') or f'공통 표기 규칙(shared.{k})을 못 받았습니다'}")
        if v:
            공통[k] = _지시문용정리(v)
    # 규정 전용 잡음 빼기('26-09-28 규정 처방 P7, 내부 기록) — 색 강조(num·
    # delta·accent)는 규정 조립기가 쓰지도 강제하지도 않고, 제목 문체의 보도자료 예외와 'YY. M. D.
    # 날짜 꼴(date_day)은 조문과 반대로 간다(부칙 날짜 꼴은 regulation.문체.핵심 7번이 맡는다).
    # 온톨로지 shared.* 는 그대로 두고 이 장르 지시문에서만 뺀다(_지시문용정리 가 새 dict 를
    # 만들어 돌려주므로 여기서 빼도 정본은 안 바뀐다).
    if 정본 == "regulation":
        공통.pop("강조", None)
        if isinstance(공통.get("제목_문체"), dict):
            공통["제목_문체"].pop("_보도자료만_예외", None)
        if isinstance(공통.get("표기"), dict):
            공통["표기"].pop("date_day", None)
    # 슬라이드 전용 잡음 빼기('26-09-28 슬라이드 제로베이스 해부 R5) — 1p·풀버전의 강조 규칙(num·
    # delta·accent, '본문 항목만·2회')과 표기 delta_sign('△=감소 전용')이 슬라이드에도 실려 줄어서
    # 좋은 지표(△18%)가 경고 빨강으로 칠해졌다(S2). 슬라이드 조립기는 그 강조 마크업을 쓰지도
    # 강제하지도 않는다 — 옛·v2 두 판형 모두 뺀다(v2 증감은 slides.디자인.증감_의미색_v2 가 맡는다).
    if 정본 == "slides":
        공통.pop("강조", None)
        if isinstance(공통.get("표기"), dict):
            공통["표기"].pop("delta_sign", None)
    if 공통:
        줄 += ["", "[공통 표기·강조·제목 문체·작성원칙 — 모든 문서 종류 공통]",
               json.dumps(공통, ensure_ascii=False, indent=1)]
    줄 += 경고
    return 줄


def _오늘날짜꼴들():
    """오늘 날짜를 이 코드베이스가 실제로 쓰는 **두 표기 꼴**로 — 한 곳에서만 만든다
    ('26-09-26 2차 진단, 온톨로지 shared.작성원칙.날짜_기본의 '26-09-26 2차검토 메모: "이
    규칙이 가리키던 shared.표기.date_day 하나로는 1p byline('YY 꼴)과 풀버전 표지 보고일
    (4자리 꼴)을 동시에 못 맞춘다 … workspace/api.py 의 오늘 날짜 삽입 문구는 코드 쪽 정합이
    남아 있다"). shared.표기.date_day 는 'YY. M. D.(예 '26. 9. 26.)이고, shared.작성원칙.
    날짜_기본은 풀버전 표지 보고일 자리는 4자리 연도 꼴(예 2026. 9. 26.)이 관례라고 적는다.
    자리마다 어느 꼴이 관례인지는 **호출부**가 정한다(1p byline='YY, 풀버전 표지='4자리)."""
    import datetime as _dt
    오늘 = _dt.date.today()
    return {
        "4자리": f"{오늘.year}. {오늘.month}. {오늘.day}.",
        "YY": f"'{오늘.year % 100:02d}. {오늘.month}. {오늘.day}.",
    }


def _오늘날짜글(꼴="4자리"):
    """`_오늘날짜꼴들()` 중 하나만 필요할 때 쓰는 짧은 길. 기본은 4자리 연도 꼴(예전과
    같은 겉모습 유지) — 1p byline 처럼 'YY 꼴이 관례인 자리는 호출부가 꼴="YY" 로 명시한다."""
    return _오늘날짜꼴들()[꼴]


# (api:F5 수정, e2e r6 재진단 '26-09-27) — 점(.) 구분 꼴만 알아봐서 'N월 N일'·'YYYY-MM-DD'
# 로 이미 날짜가 있어도 못 알아채 다시 이어붙였다(날짜 두 번). 연도를 생략한 'M. D.' 꼴도
# 있는 그대로 날짜로 인정한다(연도 있는 꼴과 한 정규식으로 — 앞부분이 통째로 선택적).
_날짜꼴있나 = re.compile(
    r"(?:'?\d{2,4}\s*\.\s*)?\d{1,2}\s*\.\s*\d{1,2}\s*\.?"   # 'YY. M. D. / M. D.(연도 생략도 인정)
    r"|\d{4}\s*-\s*\d{1,2}\s*-\s*\d{1,2}"                    # YYYY-MM-DD
    r"|\d{1,2}\s*월\s*\d{1,2}\s*일"                          # N월 N일
)


def _byline_정규화(값):
    """1p byline 정규화(F2, '26-09-27) — 지시문은 "부서명만 알면 그것만 채워라, 날짜는
    시스템이 자동"이라고 안내하지만, 모델이 부서명만 낸 byline('총무팀'·'<총무팀>')을 그대로
    두면 1p 관례(<부서명, 'YY. M. D.>)가 깨진 채(날짜 없이) 조립·출력됐다. 날짜 꼴('YY.
    M. D. 또는 4자리 연도 꼴)이 이미 있으면 손대지 않고, 없으면 부서명 뒤에 오늘 날짜를
    붙인다(꺾쇠 유무 모두 — '총무팀'→'<총무팀, 'YY. M. D.>', '<총무팀>'→'<총무팀, 'YY. M.
    D.>'). 통째로 비었으면(부서명도 모른다) '부서' 같은 자리표시 글자를 박지 않고
    날짜만 넣는다 — 이 자리는 사람이 편집기에서 부서명을 채우게 하려는 것이다.

    (api:F5 수정) — 꺾쇠가 없어도 **항상 꺾쇠로 감싸** 1p 관례(<부서명, 'YY. M. D.>)를
    지킨다(예전엔 꺾쇠 없는 입력에 그냥 날짜만 붙여 관례가 깨졌다). 이미 날짜꼴이 있으면
    꺾쇠만 보정하고 값은 그대로 둔다(날짜 두 번 붙이지 않는다)."""
    s = (값 or "").strip()
    날짜 = _오늘날짜글("YY")
    if not s:
        return f"<{날짜}>"
    괄호됨 = s.startswith("<") and s.endswith(">") and len(s) >= 2
    속 = s[1:-1].strip() if 괄호됨 else s
    if _날짜꼴있나.search(속):
        return s if 괄호됨 else f"<{속}>"
    속 = 속.rstrip(",").rstrip()
    return f"<{속}, {날짜}>"


# ── 슬라이드 판형(옛 레이아웃 13종 ↔ v2 부품 트리) — '26-09-28 사장님 판정 ─────────────
# 새 초안을 v2 로 쓸지는 **서버 설정**이 정한다(모델이 고르지 않는다 — 온톨로지 slides.판형.선택).
# 환경변수 문서지능_슬라이드판형=v2 면 v2, 없거나 다른 값이면 옛 판형. 문서가 들어올 때(새문서·
# 조립)는 이 설정과 무관하게 **문서의 판형 키**로 가른다(build/슬라이드v2.py).
_슬라이드판형_환경 = "문서지능_슬라이드판형"
# 온톨로지 slides.판형.옛_키 를 못 받았을 때(정책서버 순단·옛 서버의 메타키 거르기)만 쓰는 대체 —
# 규칙 문장이 아니라 **키 이름 목록**이다(정본은 온톨로지, 대체는 같은 목록이어야 한다 — r16 이 대조).
_슬라이드옛키_대체 = (
    "구성.중핵", "구성.덱_시퀀스", "구성.레이아웃_카탈로그", "구성.도식_유형", "구성.콘텐츠_레이아웃_매핑",
    "구성.간지_규칙", "구성.어젠다_규칙", "구성.결정사항_전진배치", "구성.장간_중복_금지",
    "문체.헤드메시지", "문체.헤드_목적별", "문체.차트_제목", "디자인.여백", "디자인.타이포_사다리",
    "디자인.색", "디자인.데이터_의미색", "디자인.배경_변형", "분량예산.장당_항목", "분량예산.헤드메시지",
    "분량예산._어절상한", "게이트.hard", "게이트.soft", "개체목록", "배치",
    "구성.수직논리", "구성.헤드_종결_통일", "_노트",
    # '26-09-28 적대 검토 — 1p 12유형 재사용(목차로직)·3앵커 서사(서사_골격 '결론 2~3장'·슬로건형 부제)가
    # v2 지시문에 남아 서사_v2('결론 앞 2장')·본보기(사실 요약형 부제)와 부딪쳤다
    "구성.목차로직", "구성.서사_골격")


def _슬라이드판형(판형=None):
    """'v2' | '옛' — 인자가 있으면 그 값(시험·호출부 지정), 없으면 서버 설정."""
    v = 판형 if 판형 is not None else os.environ.get(_슬라이드판형_환경, "")
    return "v2" if str(v).strip().lower() == "v2" else "옛"


def _슬라이드규칙판형별(장르값, v2=False, 약한모델=False):
    """슬라이드 규칙 칸을 판형에 맞게 거른 **사본**. 옛 판형은 `*_v2` 키를 전부 빼고(옛 문서
    지시문엔 v2 규칙을 싣지 않는다), v2 는 slides.판형.옛_키 가 가리키는 옛 문서 전용 키를 뺀다
    (같은 자리의 _v2 키가 대신한다 — 두 규칙이 한 지시문에서 부딪치지 않게). 판형 설명(판형)은
    둘 다 뺀다(작성 규칙이 아니라 공존 방식이다). 약한 모델 v2 는 부품·장 유형을 부분집합으로
    줄인다(slides.약한모델_v2). 온톨로지 정본은 안 바뀐다(깊은 복사)."""
    if not isinstance(장르값, dict):
        return 장르값
    import copy as _copy
    본 = _copy.deepcopy(장르값)
    판 = 본.pop("판형", None)
    if not v2:
        def _v2빼기(node):
            if isinstance(node, dict):
                return {k: _v2빼기(x) for k, x in node.items() if not str(k).endswith("_v2")}
            if isinstance(node, list):
                return [_v2빼기(x) for x in node]
            return node
        return _v2빼기(본)
    옛키 = (판 or {}).get("옛_키") if isinstance(판, dict) else None
    if not isinstance(옛키, list) or not 옛키:
        옛키 = list(_슬라이드옛키_대체)
    for 길 in 옛키:
        조각 = str(길).split(".")
        자리 = 본
        for p in 조각[:-1]:
            자리 = 자리.get(p) if isinstance(자리, dict) else None
        if isinstance(자리, dict):
            자리.pop(조각[-1], None)
    if 약한모델:
        약 = 본.get("약한모델_v2") if isinstance(본.get("약한모델_v2"), dict) else {}
        부품들, 유형들 = set(약.get("부품") or []), set(약.get("유형") or [])
        구성 = 본.get("구성") if isinstance(본.get("구성"), dict) else {}
        전부품 = [k for k in (구성.get("부품_목록_v2") or {}) if not str(k).startswith("_") and k not in ("아이콘", "상태")]
        if 부품들 and isinstance(구성.get("부품_목록_v2"), dict):
            구성["부품_목록_v2"] = {k: x for k, x in 구성["부품_목록_v2"].items()
                                if k in 부품들 or k in ("_원칙", "아이콘", "상태")}
        if 유형들 and isinstance(구성.get("장_유형_v2"), dict):
            구성["장_유형_v2"] = {k: x for k, x in 구성["장_유형_v2"].items()
                               if k in 유형들 or k == "_원칙"}
        if 부품들 and isinstance(구성.get("관계_부품_v2"), dict):
            # 첫 선택 부품이 부분집합 밖인 줄은 뺀다(약한 모델에게 못 쓰는 부품을 권하지 않는다).
            구성["관계_부품_v2"] = {k: x for k, x in 구성["관계_부품_v2"].items()
                                if str(k).startswith("_") or
                                str(x).split(" ")[0] in (부품들 | {"요지띠"})}
        return _슬라이드약한v2압축(본, 부품들, 전부품)
    return 본


_약한v2_앞묶음 = (
    ("문체", ("헤드_2층_v2", "목적별_메시지_v2", "문체_v2", "강조_규칙_v2", "애매수식어_금지", "수치_표기")),
    ("게이트", ("hard_v2",)),
    ("분량예산", ("장수", "요청장수_v2", "밀도_등급_v2", "장당_부품_v2", "머리_글자수_v2")),   # 요청장수_v2 — round2 적대 검토 §2-D
    ("약한모델_v2", None),
    ("구성", ("요청_한번_v2", "과정메모_v2", "판_채우기_v2", "요지_사실_v2", "증거_짝_v2", "장간_중복_금지_v2",
             "관계_부품_v2", "서사_v2", "부품_금지_v2", "장당_1메시지", "타임라인_순서", "중핵_v2", "장_유형_v2")),   # 장 유형은 모양 블록이 싣는다(뒤에 둔다)
)
# 약한 v2 규칙 칸 예산(자) — 키를 통째로 담다가 넘으면 뒤 키부터 뺀다(예전엔 6,000자에서 글 한복판을 잘랐다).
# '26-09-29 ⑱: 서사_v2(마무리·한눈에보기 판단 숫자 순서)까지 담기는 크기 — 부품_금지_v2 는 관계_부품_v2 의
# '(금지: …)' 와 겹쳐 뒤로 뺐다.
_약한v2_예산 = 5200
# 약한 모델이 쓰지 않는 슬롯·다른 장르와의 관계를 말하는 하위 키 — 약한 v2 규칙 칸에서 뺀다
# (리드·런·인용·배포 밀도는 약한 부분집합 밖이다 — 온톨로지 약한모델_v2.쓰지_않는_것).
_약한v2_뺄키 = {("문체", "문체_v2"): ("리드", "인용"), ("문체", "강조_규칙_v2"): ("런", "1p_강조와"),
              ("구성", "관계_부품_v2"): ("자료가 나란히 적은 두 목록",),     # 강한 경로 짝 잇기 soft 짝 — 약한 예산 밖('26-09-30)
              ("문체", "목적별_메시지_v2"): ("문체_프로필과",), ("분량예산", "밀도_등급_v2"): ("어절_세는_법", "배포", "_원칙")}
# 약한 v2 규칙 칸에서 뺄 hard_v2 줄 — 조립기 안쪽 검사라 모델이 글로 지킬 것이 아니다('26-09-29 ⑱)
_약한v2_hard안쪽 = r"(판형 ==|스키마 통과|칸 폭|렌더 뒤|그린 값|\(약한 모델\)|선차트 값 길이)"


def _슬라이드약한v2압축(본, 부품들, 전부품=()):
    """약한 모델 v2 규칙 칸 — 6,000자 절단(_장르규칙글) 안에 들 우선 묶음만 차례대로.

    '26-09-28 적대 검토(지시문 높음): 온톨로지 차례 그대로면 구성.부품_목록_v2(슬롯 3.5천 자 — [v2 문서
    모양] 블록과 같은 말) 한복판에서 잘려, 문체(헤드 2층·목적별 메시지·강조)·분량·hard_v2·약한모델_v2 가
    약한 지시문 어디에도 없었다(합 ≤50·선차트 값 개수 hard 를 모른 채 쓴다). 그래서 문체 → hard →
    분량 → 약한모델_v2 → 구성(우선순위 차례)으로 싣고, 부품은 슬롯 대신 '금지'만(슬롯은 모양 블록이
    싣는다), 옛 판·화면 키(서사_골격·목차로직·배치_v2·디자인·화면기능·애니메이션·테마)는 뺀다 — 약한
    모델은 폭·프리셋·디자인을 고르지 않는다. 부분집합 밖 부품을 권하는 문장은 약한모델_v2.대체_문장으로
    바꾸고, 장 유형은 뜻과 부분집합 안 부품만 남긴다(기본배치는 폭을 안 쓰는 모델에 뜻이 없다)."""
    import re as _re
    구성 = 본.get("구성") if isinstance(본.get("구성"), dict) else {}
    약 = dict(본.get("약한모델_v2") or {}) if isinstance(본.get("약한모델_v2"), dict) else {}
    대체 = 약.pop("대체_문장", None)
    for k, v in (대체 or {}).items():
        if not str(k).startswith("_") and isinstance(v, str) and k in 구성:
            구성[k] = v
    부품 = 구성.get("부품_목록_v2") if isinstance(구성.get("부품_목록_v2"), dict) else {}
    밖부품 = [k for k in (전부품 or ()) if k not in 부품들]
    구성["부품_금지_v2"] = {}
    for k, x in 부품.items():
        if isinstance(x, dict) and x.get("금지") and (not 부품들 or k in 부품들):
            # 부분집합 밖 부품을 대안으로 드는 금지 문장은 뺀다(따르면 hard — 검토)
            남 = [t for t in x["금지"] if not any(n in str(t) for n in 밖부품 + ["수량목록", "아이콘목록"])]
            if 남:
                구성["부품_금지_v2"][k] = 남
    for (칸이름, 키), 뺄 in _약한v2_뺄키.items():
        자리 = (본.get(칸이름) or {}).get(키) if isinstance(본.get(칸이름), dict) else None
        if isinstance(자리, dict):
            (본[칸이름])[키] = {a: b for a, b in 자리.items() if a not in 뺄}
    유 = 구성.get("장_유형_v2")
    if isinstance(유, dict):
        새유 = {}
        for k, x in 유.items():
            if isinstance(x, dict):
                쓸 = [p.strip() for p in str(x.get("부품") or "").split("·") if p.strip() in 부품들]
                새유[k] = f"{x.get('뜻', '')} — 부품 {' · '.join(쓸)}" if 쓸 else str(x.get("뜻", ""))
            elif k == "_원칙" and isinstance(x, str):
                문장 = [s for s in x.split(". ") if s.strip()]      # 첫 문장과 끝 문장만(폭·자유 유형 말은 뺀다)
                새유[k] = (문장[0] + ". " + 문장[-1]) if len(문장) > 1 else x
            else:
                새유[k] = x
        구성["장_유형_v2"] = 새유
    관 = 구성.get("관계_부품_v2")
    if isinstance(관, dict) and 부품들:
        # '(대안 점눈금 …)'처럼 부분집합 밖 부품을 대안으로 권하는 조각을 걷는다
        def _대안걷기(t):
            def 괄호(m):
                조각 = [x for x in m.group(2).split(" · ")
                      if not (x.startswith("대안 ") and x[3:].split(" ")[0] not in 부품들)]
                return f"{m.group(1)}({' · '.join(조각)})" if 조각 else ""
            return _re.sub(r"(\s*)\(([^()]*)\)", 괄호, str(t)).strip()
        구성["관계_부품_v2"] = {k: (_대안걷기(x) if isinstance(x, str) else x) for k, x in 관.items()}
    # '26-09-29 bench11 ⑱ — 약한 지시문 11.8k자 → 줄인다(EXAONE 초안 호출 절반이 180초 시간 초과).
    # 약한모델_v2 의 유형·부품 목록은 [v2 문서 모양] 블록이 같은 말로 싣고, hard_v2 가운데 조립기 안쪽 검사
    # (판형 값·스키마·칸 폭·렌더 뒤·그린 값·약한 부분집합)는 모델이 글로 지킬 수 있는 규칙이 아니다 — 뺀다.
    약 = {k: v for k, v in 약.items() if k == "쓰지_않는_것"}
    게 = 본.get("게이트") if isinstance(본.get("게이트"), dict) else {}
    if isinstance(게.get("hard_v2"), list):
        게["hard_v2"] = [t for t in 게["hard_v2"] if not _re.match(_약한v2_hard안쪽, str(t))]
    본["약한모델_v2"] = 약
    새 = {}
    for 칸이름, 키들 in _약한v2_앞묶음:
        칸 = 본.get(칸이름)
        if 키들 is None:
            if 칸:
                새[칸이름] = 칸
            continue
        if isinstance(칸, dict):
            골라 = {k: 칸[k] for k in 키들 if k in 칸}
            if 골라:
                새[칸이름] = 골라
    끝칸 = 새.get("구성") if isinstance(새.get("구성"), dict) else {}
    잰길이 = lambda: len(json.dumps(_지시문용정리(새), ensure_ascii=False, indent=1))   # noqa: E731 — 실릴 글 그대로 잰다
    뺀 = []
    while 끝칸 and 잰길이() > _약한v2_예산:
        k = list(끝칸)[-1]
        뺀.append((k, 끝칸.pop(k)))
    # 한 번 넘기면 끝에서 계속 빼던 탓에 60자짜리 장당_1메시지 같은 짧은 키도 같이 빠졌다(round2 적대 검토 §5) —
    # 뺀 키를 원래 차례대로 다시 넣어 보고, 예산 안이면 둔다(건너뛰고 이어 담기)
    for k, v in reversed(뺀):
        끝칸[k] = v
        if 잰길이() > _약한v2_예산:
            끝칸.pop(k)
    return 새


def _슬라이드v2목적분량(자료, 유형id=None):
    """v2 지시문의 [목적·밀도·프리셋] 블록 — 옛 _슬라이드목적분량 의 v2 판. 목적은 보고·설득·설명
    가운데 하나가 **필수**다(조립기가 추정하지 않는다). 판정된 1p 유형이 있으면 헤드_목적별.유형_매핑
    (옛 규칙이지만 유형→목적 매핑 자체는 판형과 무관하다)으로 목적을 정해 준다."""
    줄 = ["", "[목적·밀도·프리셋 — v2 정본(문체.목적별_메시지_v2 · 분량예산.밀도_등급_v2 · 디자인.프리셋_v2)]"]
    목적별 = (지식("document_types.slides.문체.헤드_목적별").get("값")) or {}
    매핑 = 목적별.get("유형_매핑") if isinstance(목적별, dict) else None
    목적 = None
    try:
        _ts = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
        선택 = next((t for t in _ts if t.get("id") == 유형id), None) if 유형id else None
        선택 = 선택 or _유형판정(자료)
    except Exception:
        선택 = None
    if isinstance(선택, dict) and isinstance(매핑, dict):
        sid = str(선택.get("id") or "")
        목적 = next((k for k, ids in 매핑.items() if isinstance(ids, list) and sid in ids), None)
    if 목적:
        줄.append(f"· 이 덱의 목적은 **{목적}**(판정 유형 {선택.get('id')} {선택.get('label') or ''}) — 최상위에 "
                  f"\"목적\": \"{목적}\" 를 적는다. 대외 설명회·기관장 연설처럼 청중에게 알리는 자리라면 \"설명\"")
    else:
        줄.append("· 최상위 \"목적\" 을 보고|설득|설명 중 하나로 반드시 적는다 — 결정·승인·예산·협조를 구하면 설득, "
                  "현황·성과를 알리면 보고, 대외 설명회·기관장 연설이면 설명")
    줄.append("· 머리 메시지 형태는 장 목적을 따른다(요청 유형 장은 늘 설득). 강조는 장당 2곳까지, 형광 노랑은 목적 보고 장의 요지띠·런에만")
    줄.append("· \"프리셋\" 은 보통 뺀다(기본 data). briefing(진남 머리띠)은 사용자·기관이 청했을 때만, 대외 설명회면 keynote. "
              "\"밀도\" 는 보통 뺀다(기본 보고 — 장당 90어절). 설명회·발표면 발표(40), 사전 배포면 배포(150)")
    장수 = (지식("document_types.slides.분량예산.장수").get("값")) or ""
    # 사용자가 장수를 말했으면('10장 안팎') 그 범위가 먼저다 — bench11 에서 '10장 안팎' 요청에 7~8장을 냈다('26-09-29 ⑪)
    try:
        요 = 자료뿌리.모듈("슬라이드v2").게이트().요청장수("\n".join(str(x) for x in (자료 or [])))
    except Exception:
        요 = None
    if 요:
        줄.append(f"· 장수: 사용자가 장수를 말했다({요[1]}~{요[2]}장) → 표지·마무리를 넣어 **{요[1]}~{요[2]}장**으로 쓴다. "
                  f"자료가 모자라 {요[1]}장 밑으로 쓰면 마지막 장 노트.메모에 까닭(장수: …)을 적는다")
    elif isinstance(장수, str) and 장수:
        줄.append("· 장수: " + 장수 + " — 내용이 적으면 장을 늘리지 않는다(구성.판_채우기_v2)")
    return 줄


def _슬라이드목적분량(자료, 유형id=None):
    """슬라이드 지시문의 [목적·분량] 블록 — 정본(문체.헤드_목적별·헤드메시지·분량예산.장수)을 그대로 싣고,
    판정된 1p 유형(유형id 또는 판별)이 있으면 유형→목적 매핑으로 이 덱의 목적을 정해 최상위 "목적" 키로
    선언하게 한다. 정본이 없으면(정책서버 미연결) 빈 목록 — 조립기가 목적을 추정한다."""
    줄 = []
    목적별 = (지식("document_types.slides.문체.헤드_목적별").get("값")) or {}
    헤드규칙 = (지식("document_types.slides.문체.헤드메시지").get("값")) or ""
    장수 = (지식("document_types.slides.분량예산.장수").get("값")) or ""
    if not isinstance(목적별, dict):
        return 줄
    매핑 = 목적별.get("유형_매핑") or {}
    선택 = None
    try:
        _ts = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
        if 유형id:
            선택 = next((t for t in _ts if t.get("id") == 유형id), None)
        선택 = 선택 or _유형판정(자료)
    except Exception:
        선택 = None
    목적 = None
    if isinstance(선택, dict) and isinstance(매핑, dict):
        sid = str(선택.get("id") or "")
        목적 = next((k for k, ids in 매핑.items() if isinstance(ids, list) and sid in ids), None)
    줄 += ["", "[목적·분량 — 정본]"]
    if isinstance(헤드규칙, str) and 헤드규칙:
        줄.append("· 헤드메시지 문체: " + 헤드규칙)
    if 목적별.get("_원칙"):
        줄.append("· " + str(목적별["_원칙"]))
    if 목적:
        줄.append(f"· 이 덱의 목적은 **{목적}**(판정 유형 {선택.get('id')} {선택.get('label') or ''}) — "
                  f"최상위에 \"목적\": \"{목적}\" 를 적고, 헤드메시지는 그 목적의 문체로 써라")
    else:
        값들 = 목적별.get("값") or ["설득", "보고"]
        줄.append("· 최상위에 \"목적\" 키를 " + "|".join(str(v) for v in 값들)
                  + " 중 하나로 적어라 — 결정·승인·예산·협조를 구하면 설득, 알리는 덱이면 보고")
    if isinstance(장수, str) and 장수:
        줄.append("· 장수: " + 장수)
    return 줄


def _슬라이드카탈로그():
    """슬라이드 프롬프트에 실을 **정본 카탈로그** — 레이아웃·도식 type·아이콘의 유효값을 명시한다.
    조립 게이트가 '모르는 이름을 조용히 본문으로 떨어뜨리지 않는' 하드 검사라, 모델이 카탈로그
    밖 이름을 내면 그 장이 통째로 버려진다(실측 2026-09-02: EXAONE 가 없는 레이아웃·도식 type·
    아이콘을 지어내 5회 자가수정에도 못 넘었다). 유효값과 각 슬롯 원칙을 정본에서 받아 싣는다 —
    온톨로지(지식)가 곧 정본이라 카탈로그를 코드에 복제하지 않는다(레이아웃·도식 type 한 곳)."""
    줄 = []
    레이 = (지식("document_types.slides.구성.레이아웃_카탈로그").get("값")) or {}
    if isinstance(레이, dict):
        본문형 = [(k, v) for k, v in 레이.items() if not k.startswith("_") and k != "표지"]
        if 본문형:
            줄.append("· 슬라이드[].레이아웃 은 정확히 아래 이름만(한글 그대로). "
                      "표지는 최상위 \"표지\"라 슬라이드 배열엔 넣지 않는다:")
            for k, v in 본문형:
                줄.append(f"    {k}: {v}" if isinstance(v, str) else f"    {k}")
    도식 = (지식("document_types.slides.구성.도식_유형").get("값")) or {}
    if isinstance(도식, dict):
        낱 = []
        for k, v in 도식.items():
            if k.startswith("_"):
                continue
            뜻 = v.split("(")[0].strip() if isinstance(v, str) else ""
            낱.append(f"{k}({뜻})" if 뜻 else k)
        if 낱:
            줄.append("· \"도식\".type 은 정확히 이 중 하나: " + " · ".join(낱)
                      + ". 이 밖의 값은 못 그린다 — 그런 내용은 본문으로 풀어 써라.")
    아이콘 = _아이콘목록()
    if 아이콘:
        줄.append("· \"픽토그램\"[].아이콘 은 이 라이브러리 이름에서만 고른다(없는 이름 지어내기 금지): "
                  + ", ".join(아이콘))
    if 줄:
        줄.append("· 흔한 실수(피하라): 본문을 '본체'로 쓰지 마라 — 정확히 \"본문\". "
                  "\"표\"는 header 배열과 rows 배열(실제 데이터 행, 행마다 셀 목록)을 반드시 채워라(빈 표 금지). "
                  "\"표지\"는 최상위에 한 번만 두고 슬라이드 배열엔 넣지 마라. "
                  "목록에 맞는 아이콘이 없으면 픽토그램 말고 본문·도식으로 풀어라(아이콘 이름을 지어내지 마라).")
        줄.append("· [좋은 장표의 요령] 헤드메시지 = 그 장의 결론을 담은 완결 주장 한 문장(2줄 이내). "
                  "본문 항목은 그 주장을 증명한다. 한 장에 메시지 하나 — 'and'로 두 주장이 "
                  "이어지면 두 장으로 나눠라.")
        줄.append("· [절대 금지] '요소·전망·판정·근거' 같은 **판단 과정(메타) 표를 만들지 마라** — 그건 "
                  "이 지시문의 내부 규칙이지 발표에 실을 내용이 아니다. 자료에 없는 항목·수치·요소를 "
                  "지어내지 마라. 표는 실제 수치·대안 비교가 있을 때만, 도식은 절차·구조·관계가 실재할 때만.")
        # 아래부터 P3 계약(0906) 추가분 — 콘텐츠→레이아웃 매핑·3앵커 서사·문체는 **온톨로지 정본에서 받아**
        # 싣는다(레이아웃 카탈로그와 같은 지식() 패턴). 처음엔 리터럴로 박았다가 적대감사(2026-09-06)가
        # "공개 플러그인 트리에 크라운주얼 원문이 실린다"로 잡아 정본 조회로 되돌림 — 코드에 규칙 문장을
        # 복제하지 않는다. few-shot 본보기(본보기 변수)와 약한모델 게이트(호출부)는 손대지 않는다(계약 명시).
        매핑 = (지식("document_types.slides.구성.콘텐츠_레이아웃_매핑").get("값")) or {}
        if isinstance(매핑, dict):
            쌍 = [f"{k} → {v}" for k, v in 매핑.items() if not k.startswith("_") and isinstance(v, str)]
            if 쌍:
                줄.append("· [콘텐츠→레이아웃 매핑] " + " · ".join(쌍)
                          + ". 큰숫자의 단위는 %·억·분처럼 4자 이내 짧은 단위만 넣고, 지표 이름은 라벨에 써라.")
        서사 = (지식("document_types.slides.구성.서사_골격").get("값")) or {}
        if isinstance(서사, dict):
            문 = [v for k, v in 서사.items() if isinstance(v, str) and (k == "_원칙" or not k.startswith("_"))]
            if 문:
                줄.append("· [서사] " + " ".join(문))
        문체 = (지식("document_types.slides.문체").get("값")) or {}
        if isinstance(문체, dict):
            문 = [문체[k] for k in ("헤드메시지", "애매수식어_금지", "수치_표기", "차트_제목") if isinstance(문체.get(k), str)]
            if 문:
                줄.append("· [문체] " + " ".join(문))
        줄.append("· [다양성] 10장이 넘으면 레이아웃 원형을 5종 이상 섞어라. 같은 원형(예: 본문만, 도식만)을 "
                  "연속 3장 이상 쓰지 마라 — 연속은 2장까지.")
        줄.append("· [assertion-evidence] 장마다 그 장의 결론 문장을 헤드메시지로 먼저 쓰고, 그 문장을 "
                  "증명할 시각 요소(도식·표·차트·큰숫자·비교·매트릭스·타임라인·인용 중 1개)를 지정해라 — "
                  "헤드메시지만 있고 증명할 시각이 없는 장을 만들지 마라.")
        줄.append("· [백지 금지] 간지에는 반드시 제목을 채워라. 어젠다는 항목 2개 이상. 마무리에는 "
                  "요청 사항이나 다음 단계 내용을 반드시 담아라 — 어떤 장도 빈 텍스트로 두지 마라.")
    if not 줄:
        return []
    # EXAONE 등 약한 모델 최적화(2026-09-02) — 규칙 '나열'보다 유효값을 그대로 쓴 **완결 본보기**를
    # 모방하게 한다. 이름 환각(없는 레이아웃·도식 type·아이콘)이 여기서 크게 준다. 출력 지점 바로 앞.
    본보기 = (
        '{"filename":"sl-sample-deck","genre":"slides","목적":"설득",\n'
        ' "표지":{"제목":"…","부제":"…","발표정보":"기관 · \'26. 9. 2. · 내부 회의"},\n'
        ' "슬라이드":[\n'
        '  {"레이아웃":"어젠다","항목":["배경","방안","기대효과"]},\n'
        '  {"레이아웃":"본문","헤드메시지":"완결 주장 한 문장","항목":[{"level":1,"text":"근거"},{"level":2,"text":"세부"}],"출처":"자료명"},\n'
        '  {"레이아웃":"도식","헤드메시지":"세 단계로 추진한다","도식":{"type":"process","단계":["준비","시범","확산"]}},\n'
        '  {"레이아웃":"표","헤드메시지":"대안을 비교한다","표":{"header":["구분","A안","B안"],"rows":[["비용","3억","2억"],["기간","6개월","4개월"]]}},\n'
        '  {"레이아웃":"픽토그램","헤드메시지":"세 축으로 확보한다","픽토그램":[{"아이콘":"safety-shield","라벨":"안전"},{"아이콘":"data","라벨":"데이터"},{"아이콘":"network","라벨":"연계"}]},\n'
        '  {"레이아웃":"마무리","헤드메시지":"협조를 요청드린다","항목":["일정 확정","예산 승인"]}\n'
        ' ]}')
    return (["", "[슬라이드 카탈로그 — 아래 유효값만 쓴다. 카탈로그 밖 이름을 내면 그 장이 통째로 버려진다]"]
            + 줄
            + ["", "[이대로 만들어라 — 유효값(레이아웃·도식 type·아이콘)을 쓴 완결 본보기다. 값 내용은 이 "
               "자료에 맞게 새로 채우되, 레이아웃·도식 type·아이콘 **이름은 반드시 위 목록에서만** 골라라 "
               "— 목록 밖 이름을 새로 지어내지 마라]", 본보기])


# (api:R7-5, '26-09-26 2차 진단) — 약한모델(서버 소형 모델) 경로는 글자 수(자르기, 6,000·
# 5,000 그대로 — 사장님 지시로 한도 자체는 안 바꾼다)로 자른다. F4 가 규칙키_허용목록을
# 넓히며 "설명성" 키(_정의·_왜·_기본·_선택·_선택_위치·_용법·_언제·_읽는_법·_눈에_띄는_것·
# _보도자료만_예외)가 온톨로지가 준 그 자리(대개 각 구획의 맨 앞)에 새로 실렸다. fullreport
# 는 그 커진 만큼(5,961→6,719자)이 뒤로 밀려 절단선이 개체목록 한복판을 지나며 위계_카탈로그
# 가 통째로 잘렸다. **길이 한도는 그대로 두고**, 무엇이 먼저 잘리느냐(최상위 키 순서)만
# 약한모델 경로에서 조정한다 — 설명성 키는 각 구획 안에서 뒤로 미루고(값 자체는 여전히
# 실리되, 그 구획이 잘릴 자리라면 설명보다 본문이 먼저 살아남는다), 온톨로지 순서상
# "개체목록" 바로 뒤에 있던 "위계_카탈로그"는 그 앞으로 옮긴다 — 위계_카탈로그(519자
# 남짓)는 개체목록(661자 남짓)보다 작아 이 조정만으로 절단선 안에 통째로 들어간다(실측:
# 내부 기록 회귀). 둘 다 "_선택_위치·_용법 이 '구성 설계(2층)에서 고른다'"고
# 스스로 적어 3층 초안 모델에게는 원래 참고용이라, 어느 쪽이 잘려도 초안 품질 영향은
# 비슷하게 작다 — 그래도 순서 조정만으로 신고된 그 결손(위계_카탈로그 소거) 자체는 없앤다.
_약한모델_설명성키 = ("_정의", "_왜", "_기본", "_선택", "_선택_위치", "_용법", "_언제",
                  "_읽는_법", "_눈에_띄는_것", "_보도자료만_예외")


def _약한모델용재정렬(node):
    """설명성 키를 각 dict 의 **자기 형제들 중 맨 뒤**로 민다(재귀) — 어느 구획이든 그
    구획의 본문(실제 값)이 그 구획의 설명(정의·근거)보다 먼저 잘 살아남게 한다. 키를
    지우거나 값을 바꾸지 않는다 — 순서만 바꾼다."""
    if isinstance(node, dict):
        나머지 = {k: _약한모델용재정렬(v) for k, v in node.items() if k not in _약한모델_설명성키}
        설명 = {k: _약한모델용재정렬(node[k]) for k in _약한모델_설명성키 if k in node}
        return {**나머지, **설명}
    if isinstance(node, list):
        return [_약한모델용재정렬(x) for x in node]
    return node


def _규정지시문용(장르값, 선택키빼기=False):
    """규정 지시문의 [이 문서 종류의 규칙] 칸에서 잡음을 뺀 **사본**('26-09-28 규정 처방 P7,
    내부 기록). '디자인'(글꼴·pt·들여쓰기)은 렌더러 몫이라 조문을 쓰는 모델이
    손댈 수 없는 값인데 조문체 규칙과 섞여 신호를 흐렸다. 온톨로지 키는 지우지 않는다 —
    verify_all.check_measured_sync 가 document_types.regulation.디자인 을 실측과 대조한다
    (밑줄 키로 옮기거나 _메타키인가 에 넣으면 전 장르에서 빠지거나 그 검사가 소리 없이 죽는다).
    선택키빼기 — 초안 지시문은 [선택 키] 블록에 제정이유·주요내용 뜻·예시를 따로 싣는다(약 800자
    중복). 그 경우에만 규칙 JSON 쪽 두 키를 뺀다(배치 규칙 _공통·모양 문장은 남긴다)."""
    if not isinstance(장르값, dict):
        return 장르값
    import copy as _copy
    본 = _copy.deepcopy(장르값)
    본.pop("디자인", None)
    # reg13d 판정 D6('26-10-01) — 판정·등록부 표지(별칭 목록·상태·프로필 이름)도 조문을 쓰는 모델에게는 잡음이다(장르는 이미 정해졌고
    # 프로필 본문은 따로 싣는다). 약한 경로 한도 안에 핵심·구성이 온전히 들게 사본에서만 뺀다(온톨로지 키는 그대로).
    for _표지 in ("aliases", "status", "writing_profile"):
        본.pop(_표지, None)
    # reg13e 판정 E6('26-10-01) — 문체.profile('jomun')도 프로필 이름 표지다(본문은 _문체블록이 강한 경로에 펼쳐 싣는다). 약한 경로
    # 여유(최소 150자)를 위해 사본에서 뺀다.
    if isinstance(본.get("문체"), dict):
        본["문체"] = {k: v for k, v in 본["문체"].items() if k != "profile"}
    if 선택키빼기:
        선택 = (본.get("구성") or {}).get("선택키") if isinstance(본.get("구성"), dict) else None
        if isinstance(선택, dict):
            for k in [k for k, v in 선택.items() if not str(k).startswith("_") and isinstance(v, dict)]:
                선택.pop(k)
    return 본


def _핵심먼저(본):
    """약한 경로 규칙 칸 순서(reg13d 판정 D6, '26-10-01) — '문체'를 맨 앞에, 그 안에서 '핵심'을 맨 앞에 둔다(나머지는 원순서).
    규정은 핵심 줄이 JSON 맨 끝이라, 끝에서 글자 수로 자르면 가장 중요한 줄(말투·절차)이 먼저 잘렸다(verify13c 6절)."""
    if not isinstance(본, dict):
        return 본
    문체 = 본.get("문체")
    if isinstance(문체, dict) and "핵심" in 문체:
        문체 = {"핵심": 문체["핵심"], **{k: v for k, v in 문체.items() if k != "핵심"}}
    앞 = {"문체": 문체} if "문체" in 본 else {}
    if "구성" in 본:
        앞["구성"] = 본["구성"]          # 구성 다음 — 이름·별칭 같은 머리 키는 맨 뒤(자를 때 먼저 빠진다)
    return {**앞, **{k: v for k, v in 본.items() if k not in 앞}}


# reg13e 판정 E6('26-10-01) — 규정 약한 경로 규칙 칸을 한도에 맞출 때 **무엇부터 빼나**(명시 우선순위). 앞에 있을수록 먼저 뺀다.
# 옛 D6 은 '뒤 키부터'였다 — 구성의 맨 끝 하위 키일 뿐인 선택키(제정안 뜻을 옮겨 둔 곳, fix13c K7)가 여유 +70자에서 두 번째로
# 통째로 빠졌다(verify13d 4절). 핵심 줄은 끝까지 두고, 그래도 넘치면 덜 중요한 줄부터 뺀다(주체·절차가 맨 끝). 목록에 없는 키(새로
# 생긴 키)는 '머리 표지' 다음·구성 설명 앞에서, 목록에 없는 핵심 줄은 핵심 줄 가운데 맨 먼저 뺀다(_키단위자르기). 경로 'a.b'는
# dict 키, '문체.핵심:라벨'은 핵심 목록에서 '라벨:'로 시작하는 줄이다.
_규정약한자르기순서 = (
    # 1 예시 — 본보기 값(뜻은 남는다)
    "구성.선택키.제정이유.예시", "구성.선택키.주요내용.예시",
    # 2 선택키 설명 — 두 키의 배치·모양 설명(뜻 칸이 같은 말을 한다)
    "구성.선택키._공통", "구성.선택키.모양",
    # 3 머리 표지
    "label",
    # 4 구성 설명 — 지시문 다른 줄·조립기가 맡는 것(표는 '별표에만' 줄, 부칙은 핵심 부칙 줄)
    "구성.표", "구성.분량", "구성.장_사용", "구성.위계체계", "구성.첫조", "구성.부칙", "구성.골격",
    # 5 문체 곁 설명(종결·금지는 핵심 술어·호·목 줄과 겹친다)
    "문체.profile", "문체.금지", "문체.종결",
    # 6 선택키 뜻 — 제정안 뜻(핵심 제정안 줄이 요지를 갖는다)
    "구성.선택키.제정이유", "구성.선택키.주요내용",
    # 7 핵심 줄 — 끝까지 둔다. 넘치면 덜 중요한 줄부터
    "문체.핵심:열거", "문체.핵심:호·목", "문체.핵심:표기", "문체.핵심:제정안", "문체.핵심:용어", "문체.핵심:부칙",
    "문체.핵심:술어", "문체.핵심:말투", "문체.핵심:강도", "문체.핵심:절차", "문체.핵심:주체",
)


def _키단위자르기(본, 한도, 순서=None):
    """(자른 dict, 뺀 경로 목록) — JSON(indent=1)으로 폈을 때 한도를 넘으면 순서(_규정약한자르기순서)대로 키·핵심 줄을 **통째로**
    뺀다(글 한복판을 자르지 않는다, reg13d 판정 D6 · reg13e 판정 E6). 빈 칸이 된 상위 dict 도 뺀다. 원본은 바꾸지 않는다."""
    import copy as _copy
    순서 = tuple(_규정약한자르기순서 if 순서 is None else 순서)
    본 = _copy.deepcopy(본)
    뺀것 = []
    if not isinstance(본, dict):
        return 본, 뺀것

    def 길이():
        return len(json.dumps(본, ensure_ascii=False, indent=1))
    if 길이() <= 한도:
        return 본, 뺀것

    def 핵심라벨(x):
        return str(x).split(":")[0].strip()
    # 목록 밖 키 — 목록에 적힌 경로와 그 조상만 '아는 것'이다
    안다 = set()
    for p in 순서:
        조각 = p.split(":")[0].split(".")
        for i in range(1, len(조각) + 1):
            안다.add(".".join(조각[:i]))

    def 모르는(d, 앞, 깊이):
        나온다 = []
        for k, v in d.items():
            p = f"{앞}{k}"
            if p not in 안다:
                나온다.append(p)
            elif isinstance(v, dict) and 깊이 < 3 and p != "문체.핵심":
                나온다 += 모르는(v, p + ".", 깊이 + 1)
        return 나온다
    밖 = [p for p in 모르는(본, "", 0) if not any(p.startswith(q + ".") for q in 순서 if ":" not in q)]
    핵 = (본.get("문체") or {}).get("핵심") if isinstance(본.get("문체"), dict) else None
    아는라벨 = {p.split(":", 1)[1] for p in 순서 if p.startswith("문체.핵심:")}
    밖핵 = [f"문체.핵심:{핵심라벨(x)}" for x in (핵 if isinstance(핵, list) else []) if 핵심라벨(x) not in 아는라벨]
    차례 = list(순서)
    i = 차례.index("label") + 1 if "label" in 차례 else 0
    차례[i:i] = 밖
    j = next((n for n, p in enumerate(차례) if p.startswith("문체.핵심:")), len(차례))
    차례[j:j] = 밖핵

    def 빼기(p):
        경, _, 라벨 = p.partition(":")
        조각 = 경.split(".")
        자리 = [본]
        for k in 조각[:-1]:
            v = 자리[-1].get(k) if isinstance(자리[-1], dict) else None
            if not isinstance(v, dict):
                return False
            자리.append(v)
        끝 = 조각[-1]
        if not isinstance(자리[-1], dict) or 끝 not in 자리[-1]:
            return False
        if 라벨:
            목록 = 자리[-1][끝]
            if not isinstance(목록, list):
                return False
            남 = [x for x in 목록 if 핵심라벨(x) != 라벨]
            if len(남) == len(목록):
                return False
            자리[-1][끝] = 남
        else:
            자리[-1].pop(끝)
        for n in range(len(자리) - 1, 0, -1):         # 빈 칸이 된 상위 dict 도 뺀다
            if not 자리[n] and isinstance(자리[n - 1], dict):
                자리[n - 1].pop(조각[n - 1], None)
        return True
    for p in 차례:
        if 길이() <= 한도:
            break
        if 빼기(p):
            뺀것.append(p)
    return 본, 뺀것


def _장르규칙글(장르값, 한장=False, 온전=True, 자르기=6000, 핵심먼저=False):
    """지시문의 [이 문서 종류의 규칙] 칸 글. 온전이면 연구 주석만 걷고 **자르지 않는다** —
    예전 [:6000]·[:5000] 절단이 풀버전·슬라이드 규칙 뒷부분(위계 카탈로그·테마·배치)을 잘랐다.
    1p 는 목차로직의 12유형 목록이 규칙의 절반(약 1만 자)이라 빼고, 판정된 한 유형만 따로
    통째로 싣는다(지시문이 불필요하게 커지면 느려지고 비싸진다). 온전이 아니면 예전 그대로
    (다만 R7-5 재정렬은 받는다 — 위 _약한모델용재정렬 참고).
    핵심먼저(규정, reg13d 판정 D6) — 약한 경로에서 문체.핵심을 맨 앞에 두고 글자 수가 아니라 **키 단위로** 자른다(_키단위자르기).
    한도는 그대로다. 강한 경로(온전)에는 뜻이 없다."""
    본 = _지시문용정리(장르값)
    if 한장 and isinstance(본, dict):
        목차 = (본.get("구성") or {}).get("목차로직") if isinstance(본.get("구성"), dict) else None
        if isinstance(목차, dict) and "types" in 목차:
            목차.pop("types")
            목차["types_안내"] = "12유형 가운데 이 자료에 맞게 판정된 유형 하나를 아래 [보고목적 유형]에 싣는다"
    if not 온전 and isinstance(본, dict):
        본 = _약한모델용재정렬(본)
        if "위계_카탈로그" in 본 and "개체목록" in 본:
            # (api:R7-5) 온톨로지 원순서는 개체목록 다음에 위계_카탈로그다 — 개체목록이
            # 커서(설명성 키를 안으로 품고도) 절단선을 그 안으로 밀어 위계_카탈로그가
            # 통째로 빠졌다. 더 작은 쪽(위계_카탈로그)을 앞으로 옮긴다.
            순서 = [k for k in 본 if k != "위계_카탈로그"]
            i = 순서.index("개체목록")
            순서.insert(i, "위계_카탈로그")
            본 = {k: 본[k] for k in 순서}
        if 핵심먼저:
            본, _뺀것 = _키단위자르기(_핵심먼저(본), 자르기)
            if _뺀것:
                print(f"[규칙칸] 약한 경로 {자르기}자 한도로 키 {len(_뺀것)}개를 뺐습니다: {', '.join(_뺀것[:6])}", file=sys.stderr)
            return json.dumps(본, ensure_ascii=False, indent=1)
    글 = json.dumps(본, ensure_ascii=False, indent=1)
    # 서버 소형 모델은 예전 상한(6,000자)을 지킨다 — 다만 이제 그 안에 키 이름 대신 실제 규칙이 든다
    # (1p 는 주석·12유형을 걷으면 5,800자 남짓이라 상한 안에 온전히 들어간다).
    return 글 if 온전 else 글[:자르기]


def _지시문조립(자료, 장르="samples", 예시=None, 추가지시="", 유형id=None, 약한모델=False, 판형=None, plan_id=None):
    # 판형 — 슬라이드만 본다('v2'|'옛'|None=서버 설정 문서지능_슬라이드판형). v2 면 부품 트리 규칙·
    # 모양·합성 본보기를 싣고 옛 레이아웃 13종 안내·1p 의미구조 블록을 싣지 않는다('26-09-28).
    # 약한모델 — 서버가 자기 소형 모델(EXAONE 등)로 직접 초안을 쓸 때만 True(요청내기/ask 경로).
    # BYOK 웹앱·플러그인(compose 경로)은 강한 모델(사용자 키·곁 코딩에이전트 Claude)이 쓰므로
    # False — 그쪽엔 슬라이드 카탈로그·few-shot 크러치를 얹지 않는다(현행 유지, 사장님 지침 0902).
    """초안 생성용 시스템 프롬프트를 **서버에서** 만든다(온톨로지 원문은 나가지 않는다).
    기존 app.html 의 규칙모으기()+지시문() 을 그대로 옮기되, 12유형 전체 대신 판정된
    유형 하나의 시퀀스만 싣는다."""
    한장 = (장르 == "samples")
    정본 = _장르정본(장르)
    # 온전 — 강한 모델(BYOK 웹앱·플러그인·MCP)에는 규칙을 한도·절단 없이 통째로 싣는다.
    # 서버 소형 모델(약한모델=True, EXAONE 등)은 문맥 창이 좁아 예전 분량을 그대로 둔다.
    온전 = not 약한모델
    장르규칙 = _지식전체("document_types." + str(정본))
    장르값 = 장르규칙.get("값")
    if 장르값 is None:
        장르값 = {"키": 장르규칙.get("키")}
    # 규칙 일부 누락 경고(항목 8) — _지식전체 가 정책서버 순단·429 로 자식 조각을 못 받으면
    # ok:False 로 알린다(조용히 빼지 않는다). 조립을 막지는 않되(자료가 이미 있으면 최선껏
    # 쓴다), 작성 모델에게도 알려 빠진 규칙을 마치 "그런 규칙이 없다"로 오독하지 않게 한다.
    규칙누락경고 = None if 장르규칙.get("ok") else (장르규칙.get("로그") or "규칙 일부를 못 받았습니다")
    # 슬라이드 판형('26-09-28) — 옛 판형은 *_v2 키를, v2 는 옛 문서 전용 키(slides.판형.옛_키)를 뺀
    # 사본을 싣는다. v2 는 등록부 실물 모양(옛 sl-* 표본)을 쓰지 않는다 — 모양은 build/슬라이드v2.py 가
    # 스키마에서 뽑고, 본보기는 합성 v2 본보기(○○공사)다.
    슬v2 = (정본 == "slides" and _슬라이드판형(판형) == "v2")
    if 정본 == "slides":
        장르값 = _슬라이드규칙판형별(장르값, v2=슬v2, 약한모델=약한모델)
    모양 = None if 슬v2 else ((본(장르).get("값") or {}).get("모양"))
    # 모양의 그림 예시(풀버전 장[0].절[0].이미지)는 쓸 그림이 있을 때만 둔다 — 쓸 그림이 없는데 예시가 보이면
    # 예시 꼴을 그대로 베낀다(critic_impl #30, 예시 값이 새던 선례). 모양은 본()이 부를 때마다 새로 짓는다.
    if isinstance(모양, dict) and isinstance(모양.get("장"), list) and 모양["장"]:
        try:
            _절0 = 모양["장"][0].get("절")[0]
            if isinstance(_절0, dict) and "이미지" in _절0 and not _쓸그림들(
                    _그림카드들(), 자료뿌리.모듈("genres").그림정책값(장르)):
                _절0.pop("이미지", None)
        except (AttributeError, IndexError, TypeError):
            pass
    시각 = (지식("data_elements.시각자료").get("값")) or {}
    시각의미 = 시각.get("의미구조_유형") or 시각
    # 1p·풀버전용 의미구조_유형(인라인 화살표·도형 금지·원그래프 금지)은 슬라이드에 싣지 않는다
    # (해부 R5 — 같은 블록 머리의 '시각 우선'과 정면으로 부딪쳤다). 옛·v2 두 판형 모두.
    if 정본 == "slides":
        시각의미 = None
    선택 = None
    if 한장:
        if 유형id:
            _ts = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
            선택 = next((t for t in _ts if t.get("id") == 유형id), None)
        선택 = 선택 or _유형판정(자료)
    부 = ["너는 대한민국 공공기관 문서를 만드는 도구다. 아래 **정본 규칙만** 따른다.",
         "지금 만드는 것: " + str(정본), "",
         "[이 문서 종류의 규칙]",
         # reg13c 판정 K7('26-10-01) — 모양이 비면(등록부 없음) 선택키가 규칙 JSON 에 남아 규정 규칙칸이 설계 경로와 같은
         # 크기가 된다. 6,000자에서 핵심 끝 두 줄(절차·말투)이 잘렸다(실측, 내부 기록) → 그 경우만 설계 경로와
         # 같은 7,000자. 모양이 있으면(보통) 6,000자 그대로.
         # reg13d 판정 D6('26-10-01) — 규정 약한 경로는 핵심 줄을 앞에 두고 키 단위로 자른다(끝에서 글자 수로 잘라 핵심이 먼저 잘리던 구조).
         _장르규칙글(_규정지시문용(장르값, 선택키빼기=bool(모양)) if 정본 == "regulation" else 장르값,
                    한장, 온전, 자르기=(7000 if 정본 == "regulation" and not 모양 else 6000),
                    핵심먼저=(정본 == "regulation"))]
    if 규칙누락경고:
        부.append(f"[!] 정책서버에서 {규칙누락경고} — 위 규칙이 온전하지 않을 수 있다. "
                 "빠진 것으로 보이면 지금 자료로 판단할 수 있는 만큼만 쓰고, 사람에게 재시도를 권하라.")
    if 온전:
        부 += _문체블록(정본)
    if 한장:
        if 선택 and 온전:
            부 += ["",
                  "[보고목적 유형 — 이 자료에 맞게 판정된 유형이다. 표준시퀀스 순서로 □ 절을 짜고, "
                  "절마다 절별_핵심질문에 답하는 내용을 쓰고, 표정책을 따르라]",
                  json.dumps(_지시문용정리(선택), ensure_ascii=False, indent=1)]
        elif 선택:
            부 += ["",
                  "[보고목적 유형과 목차 — 이 자료에 맞게 판정된 유형이다. 이 □ 시퀀스 순서를 따르라]",
                  json.dumps(_프롬프트용정리({"id": 선택.get("id"), "이름": 선택.get("label"),
                              "표준시퀀스": 선택.get("표준시퀀스"),
                              "압축시퀀스": 선택.get("압축시퀀스")}), ensure_ascii=False, indent=1)]
        개체들 = ("제목", "작성자", "요약박스", "본문") if 온전 else ("요약박스", "본문")
        for 개체 in 개체들:
            개체결과 = (_지식전체 if 온전 else 지식)("entities." + 개체)
            값 = 개체결과.get("값")
            if 온전 and not 개체결과.get("ok"):
                # 실패를 조용히 버리지 않는다(still_partly 항목 8 재발 — 장르 규칙과 같은 방식).
                부.append(f"[!] 정책서버에서 {개체결과.get('로그') or f'entities.{개체} 를 못 받았습니다'} "
                         "— 위 항목 규칙이 온전하지 않을 수 있다.")
            if 값:
                부 += ["", f"[{개체}]",
                      json.dumps((_지시문용정리 if 온전 else _프롬프트용정리)(값), ensure_ascii=False, indent=1)]
    if 예시:
        뼈대 = 예시.get("뼈대") or {}
        부 += ["",
              "[사용자가 \"이렇게 만들어 달라\"며 주신 예시의 **구성**]",
              "절 %s개: %s" % (뼈대.get("절수"), json.dumps(뼈대.get("절"), ensure_ascii=False)),
              "절마다 항목 수: " + json.dumps(뼈대.get("절당_항목"), ensure_ascii=False),
              "위계 깊이 %s단 · 표 %s개" % (뼈대.get("위계_깊이"), 뼈대.get("표")),
              "**이 절 이름과 차례를 그대로 따라라.** 내용은 사용자가 준 자료로 채우되,",
              "자료에 없는 절은 빼고, 자료에 있는데 예시에 없는 것은 가장 가까운 절에 넣어라.",
              "예시의 **문구를 베끼지 마라** — 가져오는 것은 구성뿐이다."]
    # 슬라이드 목적·분량 — 사장님 판정 2026-09-07: 헤드 문체는 목적(설득|보고)에 따라 다르고, 기본 장수는
    # 10±6. 규칙 문장은 정본(지식)에서 받는다 — 코드에 복제하지 않는다(적대감사 2026-09-06 교훈).
    if 슬v2:
        부 += _슬라이드v2목적분량(자료, 유형id)
    elif 정본 == "slides":
        부 += _슬라이드목적분량(자료, 유형id)
    # 슬라이드만 시각 우선으로 뒤집는다(다른 장르 문구는 그대로) — 사장님 지침(P3 계약 0906):
    # 1p·풀버전 등은 여전히 "기본은 텍스트"지만, 슬라이드는 장마다 시각 프리미티브를 먼저 고르게 한다.
    시각헤더 = ("[슬라이드는 시각 우선 — 장마다 먼저 시각 프리미티브(큰숫자·차트·비교·매트릭스·타임라인·"
             "도식·픽토그램·표·이미지)를 고르고, 글머리만 본문 장은 전체의 30% 이내로]"
             if 정본 == "slides" else
             "[표·도식·이미지 — 기본은 텍스트, 아래 의미구조가 잡힐 때만 시각요소로 승격 (억지로 넣지 마라)]")
    # 오늘 날짜·판단 서술 허용(항목 8, 사장님 결정 '26-09-26) — 정본 문구는 shared.작성원칙
    # (온톨로지, 다른 묶음이 채운다)에서 읽고, 없으면 아래 하드코딩이 대체한다(정본이
    # 아직 없을 때만 쓰는 대체 — 새 규칙을 코드에 복제하는 게 아니다). 짧은 두 줄이라
    # 서버 소형 모델 경로(약한모델=True)에도 그대로 싣는다 — _문체블록 은 온전일 때만
    # 불리지만 이 [공통으로 지킬 것] 블록은 온전 여부와 무관하게 항상 실린다.
    _작성원칙 = 지식("shared.작성원칙").get("값")
    if not isinstance(_작성원칙, dict):
        _작성원칙 = {}

    def _원칙문(_키, _기본):
        # 정본(shared.작성원칙.<키>)은 {"rule": "...", "적용범위"/"근거": …} 처럼 규칙 문장에
        # 곁가지 근거를 같이 담은 **딕셔너리**로 올 수 있다(묶음 D 스키마, '26-09-26 확인) —
        # 지시문에는 rule 하나만 싣는다(근거·적용범위는 사람이 볼 온톨로지 주석이지 모델
        # 지시가 아니다). 그냥 문자열이면 그대로, 아예 없으면(정본 미도입) 대체 문구.
        v = _작성원칙.get(_키)
        if isinstance(v, dict):
            return v.get("rule") or _기본
        if isinstance(v, str) and v.strip():
            return v
        return _기본
    _날짜기본문 = _원칙문(
        "날짜_기본", "표기는 이 문서 종류의 관례를 따른다 — 1p byline 은 'YY 꼴, 풀버전 "
        "표지 보고일은 4자리 연도 꼴이 관례다(같은 자리 안에서 두 꼴을 섞지 마라). "
        "자료에 없으면 이 날짜를 써라(사실이 아니라 문서 정보다)")
    _판단서술문 = _원칙문(
        "판단_서술", "자료에 없는 새 사실·수치·이름은 쓰지 마라. 다만 자료로부터 판단할 수 있는 "
        "쟁점·한계·후속 조치(예: 반복 비용의 재원 확보 필요, 다른 기관 수치를 그대로 "
        "옮길 때의 한계)는 판단 문장으로 써도 된다 — 단정 대신 필요·검토 등으로.")
    # 오늘 날짜는 **두 꼴을 함께** 준다('26-09-26 2차 진단 — 온톨로지 shared.작성원칙.
    # 날짜_기본의 2차검토 메모: "shared.표기.date_day 하나로는 1p byline('YY 꼴)과 풀버전
    # 표지 보고일(4자리 꼴)을 동시에 못 맞춘다"). 어느 꼴을 쓸지는 위 규칙 문장(이 문서
    # 종류의 관례)이 정하므로, 모델이 날짜 계산 없이 그대로 골라 쓰게 둘 다 싣는다.
    # 사실 규칙(수정 2, r9 — map-evidence.md 근거: 월·출처·붙임·인용 지어냄이 전 방식 공통
    # 최다 약점 항목이었다). 이 블록도 [공통으로 지킬 것] 안에 있어 약한모델 경로에도
    # 절단(_장르규칙글 의 6,000자 한도) **밖**에서 늘 실린다 — 그 절단은 앞선 [이 문서
    # 종류의 규칙] 칸 자체에서 끝나므로, 뒤에 이어붙는 이 블록은 길이와 무관하게 항상 든다
    # (r8_api8 위계_카탈로그 절단은 절단 칸 **안쪽** 순서 문제였지, 이 블록과는 자리가 다르다).
    # r9 검토자 발견(fab-precision·regression, MEDIUM/LOW) — 두 군데를 좁혔다(근거는 아래
    # 문장별로 남긴다). 문구 자체를 한 곳(여기)만 고치면 강한/약한 모델 두 지시문에 함께
    # 반영된다(_원칙문 이 그대로 편다).
    # '보도 배포일'을 자동 채움 예외 예시로 들던 옛 문구는 뺐다(검토 발견②, '26-09-28
    # 되짚음) — 배포일은 더 이상 자동 채움 대상이 아니다(아래 "배포" 모양 안내가 "계산해
    # 채우지 마라"로 바꿨다, F8). 예시를 남겨 두면 이 문장 하나가 "배포일도 자동으로
    # 채워도 되는 예외"라고 반대로 읽혀 아래 지시와 부딪힌다 — 작성일(byline·보고일)만
    # 예시로 남긴다.
    _사실규칙_기본 = (
        "자료에 없는 날짜·월·일정·금액·수치를 새로 만들지 마라(없으면 빈 자리표시 ○○). "
        "표지·결문의 분류·번호 칸(보존기간·문서번호 등)은 자료에 없으면 ○○로 비워 둬라 "
        "— 채우지 않는 것이 정본이다(작성일=오늘처럼 이 문서 종류가 따로 정한 자동 채움 "
        "규칙은 예외다). "
        # 공개구분은 '비워라' 대상에서 뺀다 — 닫힌 열거(공개·부분공개·비공개) 값 자체는
        # 자료에 근거가 없어도 정상이다(그 열거 밖의 말, 예: '대내공개'만 흠이다). 본()의
        # 모양 예시도 이 값을 '○○'로 가려 지시문과 서로 다른 말을 하지 않게 맞췄다(위 깎기 참고).
        "공개구분은 '공개·부분공개·비공개' 중 하나로만 써라 — 자료에 근거가 없어도 이 "
        "열거 값 자체는 정상이다(그 밖의 말은 쓰지 마라). "
        "인용문·발언은 자료에 있는 말만 그대로 옮기고 늘려 쓰지 마라. 출처·붙임(첨부)을 "
        "자료에 없이 새로 만들지 마라. "
        # '건의·대안 항목을 새로 만들지 마라'는 슬라이드 마무리(건의) 장·대안검토 표준
        # 시퀀스·판단_서술 규칙(아래)과 부딪혔다(그 절 자체를 만들지 말라는 말로 읽힐 수
        # 있었다) — 범위를 절 안의 '새 사실'로 좁힌다.
        "건의·대안 항목의 절 자체는 표준시퀀스대로 두되, 그 안에 자료에 없는 새 수치· "
        "이름·사실을 지어내지 마라 — 자료로 판단한 문장이나 빈 자리표시(○○)로 채워라. "
        "헤드·결론 문구는 수치와 같은 방향으로 써라(목표에 못 미쳤으면 '상회'라고 "
        "쓰지 마라 — 미달·부족처럼 실제 방향으로).")
    _사실규칙문 = _원칙문("사실_기본", _사실규칙_기본)
    # 결재 요소 — 위 사실 규칙은 금지문뿐이라 약한 모델이 "적게·조심스럽게"로 넓혀 읽었다
    # ('26-09-27 4차 실측, EXAONE: fidelity 2.94→3.69 로 올랐지만 approvable 2.67→2.44 —
    # 요약 상자에 결재 요청이 없고 '대안검토'에 대안이 없다는 지적이 늘었다). 자료의 사실로
    # 결론을 세우는 것은 지어냄이 아니라 작성자의 일이라고 **긍정으로** 못박는다. 결재를
    # 받는 보고서류(1p·풀버전·발표)에만 싣는다 — 시행문·보도자료·규정엔 결재 요청 문장이 없다.
    _결재요소문 = _원칙문(
        "결재_요소", "자료의 사실만으로 결론을 세우는 것은 지어냄이 아니라 작성자가 할 일이다 — 반드시 "
        "써라. 요약(첫머리)에 무엇을 결정·요청하는지 한 문장으로 쓰고(예: '…을 도입하고자 결재를 "
        "요청드림'), 자료에 선택지가 있으면 대안(현행 유지 대 제안안)을 나란히 비교한 뒤 '○안이 "
        "적정' 같은 판단을 쓰며, 비용이 있으면 한 번 드는 비용과 매년 드는 비용·재원을 구분해 "
        "적어라. 이 문장들에 쓰는 수치는 모두 자료에 있는 것이어야 한다.")
    # 보도자료 해석 금지(구현자 B, '26-09-27 4차 벤치마크) — 위 판단_서술 규칙은 보고서류
    # (1p·풀버전·발표)에 '자료로 판단한 문장을 써도 된다'고 열어 준 규칙인데, 그 지시밖에
    # 없다 보니 보도자료에도 그대로 번져 자료에 없는 취지·기대 문장('…덜려는 취지다',
    # '…기대하고 있다', '누리집 이용이 어려운 가구도…')을 덧붙였다(심사 3인 모두 지적,
    # X2·X5 재현). 보도자료는 사실만 전하는 장르라 판단_서술과 반대로 막아야 한다 — 이
    # 문구는 press-release 에만 싣고(정본별 분기), 판단_서술 자체를 건드리지 않는다.
    # '…할 수 있다' 류를 어미로 걸었던 판은 절차·방법을 그대로 옮긴 사실 문장('신청은
    # 주민센터에서 할 수 있다')까지 덩달아 막았다(검토 발견③, '26-09-28 되짚음 — 심사가
    # 실제로 지적한 것은 '누리집 이용이 어려운 가구도 …' 같은 자료에 없는 대상·효과를
    # 덧붙인 것이지 '할 수 있다'라는 어미가 아니었다). 어미가 아니라 **내용**으로 좁힌다.
    _보도해석금지문 = _원칙문(
        "보도_해석금지", "인용문 밖 본문은 자료의 사실만 쓴다 — 자료에 없는 대상·효과·이유를 "
        "덧붙이는 취지·기대 문장(…하려는 취지다, …기대하고 있다, 자료에 없는 대상에게도 "
        "도움이 될 것이다 같은 문장)을 쓰지 마라. 자료의 절차·방법을 그대로 옮긴 사실 "
        "문장('…에서 신청할 수 있다'처럼)은 그대로 써도 된다. 기대·평가는 인용문(자료의 "
        "발언) 안에서만 써라.")
    _날짜꼴 = _오늘날짜꼴들()
    if 슬v2 and 약한모델:
        # 약한 v2 — 다른 장르(byline·결문 분류·공개구분·시행문 문체) 이야기를 걷고 슬라이드에 닿는 것만
        # ('26-09-29 bench11 ⑱ 지시문 줄이기). 판단 서술 허용(_판단서술문)은 슬라이드 요지에 대지 않는다(⑯).
        부 += ["", "[공통으로 지킬 것]",
              f"· 오늘 날짜: {_날짜꼴['4자리']} — 이 날짜로 표지 날짜(발표정보.일자)를 채우지 않는다(자료에 발표·회의 날짜가 있을 때만)",
              "· 자료에 없는 사실·수치·날짜·금액·이름·출처를 새로 만들지 마라(없으면 뺀다). 요지·머리에 자료에 없는 "
              "판단('추가 검토 필요')·인과('~덕분')를 덧붙이지 않는다. 헤드·결론은 수치와 같은 방향으로 쓴다(목표 미달이면 '상회' 금지)",
              # bench13 ③ — EXAONE 충실도 1.56: 없는 목표치('목표 100%')·기간 한정('전년 대비')·'도입 완료' 과장. 값 칸은 hard 로 되돌아온다
              "· 자료에 없는 목표·기간('전년 대비'·'상반기')·'완료' 판단을 붙이지 않는다 — 진행 중이면 진행 중, 값 칸(막대·목표·출처)의 없는 수는 되돌아온다",
              # fixup5 ③('26-09-30) — 빈칸 꼴을 하나로(끝 보고의 '채울 곳'이 이 꼴을 센다). 약한 v2 는 뺄 수 있으면 뺀다
              "· 꼭 적을 칸인데 모르는 값은 반드시 ○○ 한 꼴로 비운다(〇〇·OO·XX·[ ]·빈 밑줄 금지)",
              # round3 fixup — s7 다섯 판 내내 요청상자 '시점' 행을 지어 채웠고(''27년 상반기'), 머리가 65~75자(상한 40)였다
              "· 머리 메시지는 40자 이하로 그 장의 결론을 쓴다. 결정·승인을 구하면 요청상자 하나에 자료에 있는 무엇을·규모·"
              "시점만 모으고(없는 행은 만들지 않는다), 요청 금액은 한눈에보기에 지표타일로 둔다", ""]
    else:
        부 += ["", "[공통으로 지킬 것]",
              f"· 오늘 날짜: {_날짜꼴['4자리']} ('YY 꼴로는 {_날짜꼴['YY']}) — {_날짜기본문}",
              f"· {_판단서술문}",
              f"· {_사실규칙문}",
              # fixup5 ③('26-09-30) — 빈칸 꼴을 하나로. 코어는 ○○·흔한 변형을 끝 보고 '채울 곳'으로 센다(고쳐 쓰지 않는다)
              "· 모르는 값은 반드시 ○○ 한 꼴로 비운다 — 〇〇·OO·XX·○○○·[ ]·{ }·<기관명>·빈 밑줄 같은 다른 꼴은 쓰지 마라"]
    if 슬v2 and 약한모델:
        pass
    elif 슬v2:
        # v2 는 '요약(첫머리)에 결정 요청 한 문장'을 싣지 않는다 — 건의·요청은 덱에서 한 번(사장님 판정
        # '26-09-28, 구성.요청_한번_v2). 결론을 자료의 사실로 세우라는 앞 절반만 v2 모양으로 옮긴다.
        부 += ["· 자료의 사실만으로 결론을 세우는 것은 지어냄이 아니라 작성자가 할 일이다 — 머리 메시지마다 "
              "그 장의 결론을 쓴다. 결정·승인을 구하는 덱이면 요청상자 하나(짧은 덱은 한눈에보기 칸 안, "
              "아니면 끝 요청 장)에 무엇을·규모·시점·기대효과를 모으고, 다른 장에서 요청을 되풀이하지 않는다. "
              "이 수치는 모두 자료에 있는 것이어야 한다.",
              # 위 '오늘 날짜' 줄의 예외('26-09-28 적대 검토) — 스키마·모양 블록은 '자료에 있는 것만'인데 이 줄만
              # '작성일 자리는 오늘'이라 갈렸고, 1단계 심사는 표지의 오늘 날짜를 지어낸 날짜로 감점했다.
              "· 발표정보.일자(표지 날짜)는 자료에 발표·회의 날짜가 있을 때만 적는다 — 위 오늘 날짜로 채우지 않는다(없으면 뺀다)",
              # 위 판단 서술 허용은 슬라이드 요지에 대지 않는다('26-09-29 bench11 ⑯ — 심사가 '추가 검토 필요' 를 지어냄으로 깎았다)
              "· 슬라이드 요지·요지띠·머리에는 자료에 없는 판단('추가 검토 필요')·인과 단정('~덕분')을 덧붙이지 않는다(구성.요지_사실_v2)"]
    elif 정본 in ("onepage-report", "fullreport", "slides"):
        부 += [f"· {_결재요소문}"]
    if 정본 == "press-release":
        부 += [f"· {_보도해석금지문}"]
    if not (슬v2 and 약한모델):
        부 += [
              "· 문체는 이 문서 종류의 규칙을 따른다 — 1p·풀버전은 개조식 명사형, 시행문은 서술어 완결+공손체,",
              "  보도자료는 서술형, 규정은 조문체다(호·목만 명사구·'~할 것'). 섞지 마라.",
              ""]
    # 규정은 본문 스키마에 표·도식 자리가 없다(표는 최상위 "별표"에만) — 1,762자짜리
    # 표·도식·이미지 안내 대신 한 줄만 싣는다('26-09-28 규정 처방 P7, 내부 기록).
    if 정본 == "regulation":
        # reg13d 판정 D3 · reg13e 판정 E5 — 템플릿의 기관 이름 자리는 늘 뜻이 드러나는 자리표시(자료를 정규식으로 읽어 채우지 않는다)
        _기관틀, _제명틀 = _규정기관틀, _규정제명틀
        부 += ["· 규정 본문에는 표·도식을 넣지 않는다 — 수치·목록 표는 '별표'에만",
              # 위 '오늘 날짜' 줄의 예외('26-09-28 적대검토 M8) — 부칙 머리 '<제○호, 날짜>'와 시행일은
              # 발령할 때 채우는 값이다(canon R60). 오늘로 채우면 머리와 시행일이 한 문서에서 어긋난다.
              "· 위 오늘 날짜로 부칙의 호수·일자('부칙' 머리)와 시행일을 채우지 마라 — 호수·일자는 자료에 없으면 비운다(발령할 때 채운다)",
              # bench9 R3·R4·R5('26-09-28 reg10) — 약한 모델 경로에도 실리는 짧은 판(규칙 본문은 regulation.문체.핵심
              # 강도·절차·부칙 줄, 긴 판은 writing_profiles.jomun.강도·절차).
              # reg10 적대검토('26-09-28) — 웹앱 new 는 원문을 안 보내 확인 물음이 돌지 않으므로 '시스템이 묻는다'를
              # 걷었고(M-5), 주체는 자료의 주관 부서의 장으로 세운다(빈칸 주체는 심사 12/12 감점, M-4).
              # 사장님 판정 ②('26-09-29) — 시행일 세 갈래: 자료대로 · 자료 침묵이면 관행 '발령한 날부터' · 미정이면 빈칸.
              # 이 줄(과 핵심 7번)은 모델에게 주는 작성 규칙일 뿐이다 — 코드는 부칙의 시행일 값을 고쳐 강제하지 않는다
              # ('26-09-29 세 번째로 좁힘, 표기 교정은 한다). 새문서는 원문이 오면 확인 물음 한 줄을, 지어냈나는 자료에 없는 부칙 날짜만 건다.
              # 사장님 판정 ①~④('26-09-30, bench12 충실 4.78→3.97) — ① 자료에 없는 절차 요소는 확정하지 않고 '○○'
              # (위 M-4 '주관 부서의 장' 주체 끌어내기는 자료가 그 일을 맡긴 때로 좁혔다 — 위촉권자 확정이 지어냄으로 짚였다)
              # ② 술어 강도 양쪽(약화 금지·한정어 보존) ③ 약칭(reg12 '26-09-30 판정 A 로 되돌림: 제1조에서 약칭을 정의하는
              # 꼴이 기본 — 실물 규정·지침에서 가장 흔하고, 제1조에 기관 이름 없는 꼴은 드묾 · 법제처 형은 허용) ④ 제정안 머리.
              # 부칙 문장(둘째·셋째 조각 앞머리)은 그대로 둔다.
              # reg11 적대검토('26-09-30 fixup) — '제한'의 기본은 기속 '제한한다'(12차 '제한할 수 있다' 재량화 24/24 지적),
              # 빈칸은 조문이 서는 데 꼭 필요한 자리에만·같은 사람은 같은 빈칸 하나, 제1조에서 빼는 것은 기관 이름뿐
              # (이 마지막 뜻은 reg12 판정 A('26-09-30)로 걷었다 — 제1조에서 약칭 정의가 기본, 부서·대상 한정은 그대로).
              "· 규정은 자료의 술어 강도를 올리지도 내리지도 마라 — 자료의 한정어('사전에'·'정기적으로')를 빼지 않고, "
              "'제한'을 '할 수 없다'나 '제한할 수 있다'로(자료가 '제한'이면 '제한한다'), '권고'·'할 수 있다'를 '하여야 한다'로, 조건에 못박은 효과('기한을 넘기면 중지')나 "
              "'하여야 한다'를 '할 수 있다'로 "
              "바꾸지 않는다. 부칙 시행일은 자료대로 쓰되, 자료가 시행을 말하지 않으면 '발령한 날부터'(관행 문형), 자료가 "
              "미정이라 하면 '○○○○년 ○월 ○일'로 비운다. 자료에 없는 권한·기간·상대방·거치는 단계·위원 위촉·위임은 조문으로 "
              "확정하지 말고, 조문이 전제하는데 자료가 비면 그 자리를 '○○'로 비운다(같은 사람은 문서 전체에서 같은 빈칸 하나로 쓰고 "
              "자료에 없는 절차 조를 세우려고 빈칸을 만들지 않는다. 주체를 부서의 장으로 세우는 것은 자료가 그 "
              "일을 그 부서에 맡겼을 때만(그 승인·허가에 딸린 결정은 맡긴 것으로 본다), 세부 사항 위임 조항은 자료가 따로 정한다고 할 때만). "
              # reg13('26-09-30 bench15 주관 판정 J1~J6) — 주체 이어받기(자료가 밝힌 권한의 범위, 11차 ① 절차 비우기는 권한자
              # 없는 절차·새 절차 요소에만) · 의무 조문 주체 · 역할어·요건 정의 · 법제 말투(뜻·세기 그대로) · 약칭은 쓸 때만 ·
              # 주요내용 부칙 항목은 부칙 문언 요약 · 조 배열. 긴 판은 regulation.문체.핵심(주체·용어·말투·제정안·절차)과 jomun.
              # reg13d 판정 D5('26-10-01) — 자기 결정의 결과 통보도 딸린 결정이다
              "자료가 승인자·허가권자·신청을 받는 자를 밝혔으면 그 절차에 딸린 제외·제한·연장·점검·취소 결정과 그 결과 통보의 주체도 "
              "그 권한자로 쓰고(지어냄이 아니다. 자료에 있는 결정의 주어만 채우고 없는 결정은 새로 만들지 않는다. 한 사람은 문서 전체에서 "
              "한 이름), 권한자가 자료에 없는 절차와 이의신청 처리·위임·위원 위촉만 "
              "'○○'로 비운다. "
              # reg13 주관 판정 ③('26-10-01) — 기관 전체의 의무·행위는 맡을 부서가 자료에 없으면 기관 약칭(내규 관행, 지어냄
              # 아님). 긴 판은 핵심 주체 줄·jomun.절차.
              # reg13c 주관 판정 K1~K4('26-10-01) — K4 조건을 핵심 줄과 같게('권한자·맡을 부서'), K2 기관 주체는 제1조에서 정한
              # 기관 약칭('공사'를 글자 그대로 쓰지 않는다), K3 뭉뚱그리지 않는 것은 직원 개인에 대한 처분(열린 목록)이고 외부 계약
              # 상대에 대한 계약상 행위는 기관 약칭 가능, K1 한 절차의 주체는 한 이름(조마다 섞지 않는다).
              # reg13d 판정 D3·D5('26-10-01) — 예시 약칭 글자('공사는')를 걷고 '자료의 기관 이름에서 딴 약칭', 한 이름은 이름 없는 단계에만
              "기관 전체의 의무·행위(교육 실시·공개·계획 수립 등)는 권한자·맡을 부서가 자료에 없으면 제1조에서 정한 기관 약칭"
              "(자료의 기관 이름에서 딴 약칭)을 주체로 쓴다(내규 관행 — 직원 개인에 대한 허가·취소·징계·비용 부담·신청 제한 등의 처분과 "
              "그 통보는 제외, 외부 계약 상대에 대한 계약상 행위는 기관 약칭 가능). 한 절차의 주체는 한 이름이다 — 권한자가 "
              "있으면 그 사람, 없고 기관 전체의 일이면 모두 기관 약칭, 둘 다 아니면 모두 같은 '○○장'(조마다 이름을 섞지 않는다). "
              "이 한 이름은 이름 없는 단계에만 댄다 — 자료가 단계마다 다른 사람을 밝혔으면 자료대로, 이의신청 처리·위임·위촉은 "
              "사슬 안에서도 '○○', 기관 약칭 사슬 안의 직원 개인 처분은 권한자(없으면 '○○장'), 위원회를 두는 조는 사슬 밖이다. "
              "의무·금지 조문에는 주체를 쓴다. 주체로 쓰는 역할어는 처음 나오는 곳에서 '소속 부서의 장(이하 "
              "“부서장”이라 한다)'처럼 정하고, 정의문은 정의되는 말을 되풀이하지 않고 요건으로 쓴다. 자료의 구어는 뜻·세기를 그대로 "
              "두고 법제 말로 옮긴다(해마다→매년, 끝나면→종료되면, 바로→즉시, 상한 '…까지'→'… 이내에서'). 조는 절차 순서로 놓는다"
              "(결과를 쓰는 조는 통보·이의신청 뒤에). 위 '판단 서술' 허용(쟁점·후속 "
              "조치)은 규정 조문에 대지 않는다. 기관 약칭은 제1조(목적)에서 "
              f"'{_기관틀}의 …'로 만든다(부서·대상 한정은 그대로 두고, 자료가 목적 조 다음에 약칭을 두는 꼴이면 따른다. "
              "약칭은 뒤 조문에서 쓸 때만 만든다. '○○'·'기관 약칭'은 자리표시다 — 예시의 기관 이름·약칭을 글자 그대로 옮기지 말고 "
              "자료의 기관 이름에서 딴다). "
              f"제정안이면 제명을 '{_제명틀}'(앞 ○○ 자리는 자료의 기관 이름)"
              "으로 쓰고, 주요내용 끝 항목에 부칙(시행일·경과조치)을 적는다"
              "(부칙 문언대로 줄이고 '시행일은 결재 후 정함' 같은 작성 메모를 쓰지 않는다)",
              # reg13d 판정 D1('26-10-01) — 주체를 정규식으로 짐작해 묻던 검사(K5)를 걷고, 작성 모델이 스스로 정한 것을 적게 한다.
              # 새문서가 이 칸을 문서에서 떼어 확인 물음(사람 말)으로 옮긴다 — 조립기는 그리지 않는다. 강·약 두 경로에 같은 줄.
              # reg13e 판정 E2('26-10-01) — '비운 ○○장'을 뺐다: 빈칸은 코드가 정확히 찾아 묻는다(같은 빈칸을 두세 번 묻고 코드 줄을
              # 8줄 밖으로 밀었다, verify13d 2-4). 본보기에서도 빈칸 항목을 뺐다.
              "· 자료에 없어 스스로 정한 것 — 이어받은 권한자, 기관 약칭 주체, 정족수 기준 읽기 — 은 최상위 "
              "\"확인요청\" 목록에 조·무엇을 가정했나·자료 근거(자료 문장, 없으면 '자료에 없음')로 한 항목씩 적는다(조립기는 그리지 "
              "않고, 시스템이 사용자 확인 물음으로 옮긴다. 조문에 남긴 '○○' 빈칸은 시스템이 따로 찾아 물으니 적지 않는다). 예: "
              '"확인요청":[{"조":"제3조","가정":"대여 승인자를 반납 점검 주체로도 씀","근거":"대여는 총무 부서의 장이 승인한다"},'
              '{"조":"제5조","가정":"물품 목록 공개 의무의 주체를 기관 약칭으로 씀","근거":"자료에 없음"}]',
              # reg13f 판정 F1('26-10-01) — 절차 빈틈 정규식 물음(통보·이의·정족수)을 걷었다(맞는 초안 헛질문 15/20, verify13e 1절).
              # 그 자리는 작성 모델의 확인요청이 맡는다 — 채우라고 밀지 않고(11차 판정) 넣지 않은 것을 적게만 한다. 강·약 두 경로에 같은 줄.
              # reg13g 판정 H3('26-10-01) — 바로 앞 줄의 "'○○' 빈칸은 적지 않는다"와 이 줄의 "넣지 않은 절차는 적는다"가 한 낱말('비운')로
              # 겹쳤다(verify13f 3절). 앞 줄은 '조문에 남긴 ○○ 빈칸', 이 줄은 '조문에 넣지 않은 절차'로 가른다.
              "· 자료에 없어 조문에 넣지 않은 절차(이의신청 제출처·처리 기한, 통보 주체·기한, 정족수)도 \"확인요청\"에 "
              "한 항목씩 적는다(시스템은 절차 빈틈을 따로 찾아 묻지 않는다)"]
    elif 슬v2:
        # v2 는 표·도식·이미지 키가 없다 — 보여줄 관계에서 부품을 고른다(구성.관계_부품_v2).
        부 += ["[슬라이드 v2는 부품 우선 — 장마다 먼저 보여줄 관계(구성.관계_부품_v2)를 정하고 그에 맞는 부품을 "
              "고른다. 글자만 있는 장은 만들지 않는다(글머리 부품은 배포 밀도 전용)]",
              "· 차트는 값만 준다 — 좌표·눈금·SVG·색·막대 길이는 조립기가 그린다. 막대 2개짜리 차트 대신 "
              + ("지표타일 둘을 쓴다" if 약한모델 else "지표타일·전후숫자를 쓴다")   # 약한 부분집합엔 전후숫자가 없다(검토)
              + ". 이 판형에는 이미지·자유 도식 자리가 없다.",
              "· 작성 과정 메모(짝 배치 근거·자료에 없어 뺀 것·산출 식)는 화면 글·출처에 쓰지 않고 노트.메모로. "
              "계산해서 화면에 쓴 값은 그 장의 산출[]에 등록한다(조립기가 발표자 노트로 보낸다 — 화면에는 안 찍는다).",
              # 문체 프로필(gongmun-gaejosik)의 '요약박스 서술형(…드림)' 예외·합니다체 금지가 v2 머리
              # 메시지 규칙(설명 목적은 합니다체)과 부딪치지 않게 적용 범위를 못박는다(문체.목적별_메시지_v2).
              "· 문체 프로필(개조식 명사형 종결)은 카드·글머리·색띠행 항목에만 댄다. 프로필의 요약박스 서술형 "
              "예외(…보고드림·…요청드림)는 슬라이드에 없다 — 머리 메시지 형태는 목적을 따른다(설명 목적 머리만 합니다체)."]
    else:
        부 += [
          시각헤더,
          (json.dumps(_프롬프트용정리(시각의미), ensure_ascii=False, indent=1)[:(None if 온전 else 1500)] if 시각의미 else ""),
          # '이미지' 는 그림 자리가 있는 장르(풀버전·옛 슬라이드, build/genres.py 그림자리)에만 — 1p·시행문·보도자료는
          # 조립기에 그림 자리가 없어 이 줄을 보고 넣은 그림이 조용히 사라졌다('26-09-30, r2/img map_code ⑤)
          ("· 넣는 자리: 절 안에 \"표\"·\"도식\"·\"이미지\" 키로(돌려줄 모양의 예시 구조 그대로). 1p 는 top 의 \"table\"."
           if 자료뿌리.모듈("genres").이미지키자리있나(정본) else
           "· 넣는 자리: 절 안에 \"표\"·\"도식\" 키로(돌려줄 모양의 예시 구조 그대로). 1p 는 top 의 \"table\"."),
          # 도식 유형 줄은 도식을 그리는 장르(풀버전·옛 슬라이드)에만 — 1p·시행문·보도자료 조립기는 도식을 안
          # 그려, 이 줄을 보고 쓴 도식 키가 조용히 빠졌다(보안·약한 모델 검토 W2 '26-09-29)
          ("· 도식 type: 절차=process, 되돌아오면 cycle, 수렴 converge, 관계·구조 strategy/relation, 현행→개선 대조 compare(\"전\"·\"후\" 목록), 차트 line/bar/donut/hbar/stack."
           if 자료뿌리.모듈("genres").도식자리있나(정본) else None),
          "· 도식·표는 반드시 그 절의 \"도식\"·\"표\" 키에 위 예시 구조(스펙)로 넣어라. 본문 항목 text 에 \"[도식] …\"·\"[표] …\"·\"[그림] …\" 처럼 자리표시 설명만 쓰지 마라 — 시스템이 그리지 못한다. 도식으로 만들 수 없으면 그 내용을 대괄호 없는 평범한 설명 문장으로 풀어 써라.",
          "· 표는 수치·비교(대안 비교·현행vs개선·일정표)일 때."]
        # 그림 줄('26-09-30 주관 판정) — 장르 정책(genres.그림정책) + 시스템이 꺼낸 첨부 그림 카드 + 승인된 설계의
        # 그림 계획. 모델은 "그림":"img-…" id 만 쓴다(전에는 "파일"·"쪽"·"자를곳"을 짐작해 9건 중 0건이 맞았다,
        # r2/img probe). 실사 모드는 없앴고, 생성 요청은 에이전트가 그릴 수 있을 때·옛 슬라이드에서만 가르친다.
        # 웹앱 서버는 그림을 만들지 않는다. 자리 없는 장르에는 넣지 말라고만 한다. 강·약 같은 부품(약은 짧게).
        부 += _그림지시(장르, 약한모델, _슬라이드판형(판형) if 정본 == "slides" else None, plan_id)
    if 정본 == "slides" and not 슬v2:
        # 레이아웃별 콘텐츠 키 예시(cli:s6 수정, e2e r6 재진단 '26-09-27) — 아래 few-shot
        # 본보기(_슬라이드카탈로그)는 서버 소형 모델 전용 크러치라(약한모델 게이트, P3
        # 계약 0906 — 손대지 않는다) BYOK·플러그인·MCP(강한 모델) 경로엔 안 실린다. 그
        # 경로는 어젠다·큰숫자·타임라인·비교·매트릭스·인용 하위 키를 산문 설명만 보고
        # 추측해야 했다(재현: 어젠다 콘텐츠 키를 레이아웃명과 같은 "어젠다"로 잘못 짚어
        # 새문서 게이트 "목차 항목이 0개"로 막힘). 조립기(build/assemble_slides.py)가
        # 실제로 읽는 키 그대로, 레이아웃마다 한 줄씩 — 약한모델 여부와 무관하게 늘 싣는다.
        부 += ["",
             "[레이아웃별 콘텐츠 키 — 아래 키 이름 그대로(다른 이름을 쓰면 그 장이 통째로 버려진다)]",
             '· 어젠다: {"레이아웃":"어젠다","항목":["배경","방안","기대효과"]} — "항목" 2개 이상 필수.',
             '· 표: {"레이아웃":"표","헤드메시지":"…","표":{"header":["구분","A안","B안"],"rows":[["비용","3억","2억"]]}}.',
             '· 큰숫자: {"레이아웃":"큰숫자","헤드메시지":"…","지표":[{"값":"1,200","단위":"명","라벨":"이용자 수","변화":"+8%"},{"값":"94","단위":"%","라벨":"만족도"}]} — "지표" 2~4개, 단위·변화는 선택.',
             '· 타임라인: {"레이아웃":"타임라인","헤드메시지":"…","단계":[{"시점":"1월","라벨":"착수","설명":"…"},{"시점":"6월","라벨":"확산"}]} — "설명"은 선택.',
             '· 마무리: {"레이아웃":"마무리","헤드메시지":"…","항목":["일정 확정","예산 승인"]} — 항목 대신 짧은 문장 하나면 "문구" 키도 된다.',
             '· 비교: {"레이아웃":"비교","헤드메시지":"…","좌":{"제목":"현행","항목":["…"]},"우":{"제목":"개선","항목":["…"]},"결론":"…"} — "결론"은 선택.',
             '· 매트릭스: {"레이아웃":"매트릭스","헤드메시지":"…","축":{"가로":["유지","전환"],"세로":["현재","향후"]},"사분면":[{"제목":"…","항목":["…"]},{"제목":"…"},{"제목":"…"},{"제목":"…"}]} — 사분면은 좌상·우상·좌하·우하 순서로 4개.',
             '· 인용: {"레이아웃":"인용","인용문":"…","출처":"…"} — 헤드메시지는 이 레이아웃만 선택이다.']
    if 정본 == "slides" and 약한모델 and not 슬v2:   # 서버 EXAONE 전용 크러치 — BYOK·플러그인엔 안 얹는다
        부 += _슬라이드카탈로그()
    if 슬v2:
        # v2 모양(스키마에서 뽑은 뼈대 — 약한 모델은 부분집합 슬롯까지)·합성 본보기(○○공사, 강한 모델은
        # 7장 축약·약한 모델은 부분집합 4장)·돌려줄 것. 옛 레이아웃 카탈로그·옛 모양 덤프는 싣지 않는다.
        _v2 = 자료뿌리.모듈("슬라이드v2")
        부 += _v2.모양지시(약한모델) + _v2.본보기지시(약한모델) + _v2.돌려줄것(약한모델)
    else:
        부 += ["", "[돌려줄 것 — JSON 하나만, 다른 말 없이]"]
    if 슬v2:
        pass    # 모양·돌려줄 것은 위 v2 블록이 다 실었다
    elif 한장:
        부.append('{"filename":"영문소문자-하이픈","title":"제목","byline":"<부서, \'26. 8. 5.>",\n'
                 ' "summary":"…보고드림","purpose_type":"' + str((선택 or {}).get("id") or "②") + '",\n'
                 ' "sections":[{"heading":"검토결과","items":[{"level":2,"html":"…"},{"level":3,"html":"…"}]}],\n'
                 ' "table":null,"attach":null}')
        # 표 스키마 — 예전엔 "table":null 만 보여 줘 작성자가 조립기 코드를 뒤져 키를 찾았다('26-09-26 실험 보고).
        부.append('표를 넣을 때 "table" 모양(표는 한 장에 하나, 넣을 □ 절 제목을 after_heading 에): '
                 '{"after_heading":"대안검토","caption":"(단위: 만원)","header":["구분","1안 …","2안 …"],'
                 '"rows":[["항목","값","값"]]} — 칸 값은 문자열, 단위는 caption 이나 행 이름에 적는다.')
        # 군더더기 줄이기(항목 7) — 시스템이 이미 아는 값은 안 써도 새문서가 자동으로
        # 채운다. **plan_id 는 여기서 뺐다**(항목 0·2, '26-09-26 2차 진단) — 승인 그
        # 자체는 시스템이 지어낼 수 없는 값이라 생략할 수 없다(플러그인·MCP; 웹앱은 화면이
        # 이미 승인을 거쳐 채운다). 생략하면 새문서가 거절하며 아직 문서에 안 매인 승인
        # 플랜이 있으면 후보 id 를 알려준다.
        부.append("생략 가능(시스템이 채운다) — filename(비우면 제목에서 자동 생성), "
                 "purpose_type(plan_id 의 판정에서 자동), byline 의 날짜(부서명만 알면 "
                 "그것만 채워라 — 시스템이 뒤에 오늘 날짜를 자동으로 붙인다. 통째로 "
                 "비워도 오늘 날짜만이라도 채운다). **plan_id 는 생략할 수 "
                 "없다** — 승인된 빌드플랜의 id 를 반드시 채워라.")
    elif 모양:
        _키목록 = ", ".join(f'"{k}"' for k in 모양.keys())
        # 선택키(항목 9) — document_types.<장르>.구성.선택키 = {"키": {"뜻":…, "예시":…}}.
        # 정본(다른 묶음이 채운다)에 있을 때만 최상위 키 허용 목록에 더하고 예시를 붙인다 —
        # 없으면(정본 미도입) 지금 그대로 동작한다.
        _선택키원본 = _지식전체(f"document_types.{정본}.구성.선택키").get("값")
        if not isinstance(_선택키원본, dict):
            _선택키원본 = {}
        # "_공통" 같은 밑줄 설명 항목은 뺀다(항목 11) — _선택키목록 은 키를 거르지 않고
        # 다 나열해서, 예전엔 "_공통"이 규정 지시문에 '쓸 수 있는 최상위 키'로 그대로 실렸다.
        # 선택키는 {"키": {"뜻":…, "예시":…}} 모양의 dict 값만 진짜 키다.
        _선택키 = {k: v for k, v in _선택키원본.items()
                 if not str(k).startswith("_") and isinstance(v, dict)}
        _선택키목록 = ", ".join(f'"{k}"' for k in _선택키.keys())
        부 += ["아래는 이 문서 종류의 **실제 모양**이다(등록부의 실물에서 뽑은 것).",
              "",
              "[반드시 지킬 키 규칙 — 어기면 문서가 통째로 비어 버린다]",
              "· **최상위 키는 정확히 이것들만 쓴다(한글 그대로). 번역·개명·영문화 절대 금지: " + _키목록
              + (f" — 자료에 해당 내용이 있으면 아래 선택 키도 더 쓸 수 있다: {_선택키목록}" if _선택키목록 else "")
              # reg13d 판정 D1 — 규정은 스스로 정한 것을 적는 "확인요청" 목록도 쓴다(위 규정 줄, 그리지 않는 칸)
              + (' · 그리고 스스로 정한 것을 적는 "확인요청"(위 규정 줄)' if 정본 == "regulation" else "")
              + "**"]
        # 장/절/항목 중첩은 **풀버전 보고서 전용** 구조다(모양에 최상위 "장" 키가 있을 때만).
        # 이 지시를 시행문·보도자료·규정·슬라이드에도 실으면 모델이 아래 모양 덤프(예: 규정의
        # 평면 조(條) 리스트)를 무시하고 장/절/항목으로 내 게이트에 걸린다(규정 "조가 하나도 없다").
        # 그 장르들은 아래 모양 덤프만으로 구조를 이끈다.
        if "장" in 모양:
            부 += ['· **본문은 반드시 "장"(배열)에 담는다.** 구조는 '
                  '[{"제목":"…","절":[{"제목":"…","항목":[{"level":2,"text":"…"}]}]}] 다.',
                  '· **각 "장"·"절"의 "제목"에는 자료에 맞는 구체적 제목을 반드시 써라 — null·빈 문자열 금지.** (예: "추진 배경 및 필요성", "시스템 구축 방안")',
                  '· **"보고내용 요약"은 "장"이 아니라 "요약":{"블록":[{"제목":"…","항목":[{"text":"…","세부":["…"]}]}]} 필드에 담아라** — 요약 페이지는 별도로 있다.',
                  '· "sections"·"body"·"chapters"·"toc"·"cover"·"summary" 같은 **영문 키를 쓰지 마라** — 조립기가 못 읽어 표지만 남는다.']
        if "배포" in 모양:
            # 보도자료 '배포' 안내(F8, e2e s5 재진단, '26-09-27) — '배포'는 필수 최상위
            # 키인데 자료에 배포 날짜를 어떻게 채우라는 지침이 어디에도 없어, 자료의
            # 보도시점(엠바고) 날짜를 그대로 재사용해야 하는지 모델이 스스로 판단해야
            # 했다(친절 항목). byline 처럼 '자료에 없으면 오늘 날짜'로 명시한다 — 배포는
            # 보도시점(엠바고 해제일)과 다른 개념(발송일)일 수 있다는 것도 함께 밝힌다.
            # '26-09-27 2차 벤치마크: '자료에 없으면 오늘'로 두었더니 배포일이 보도시점보다 두 달
            # 앞서 심사 3인 모두 '실무상 고쳐야 한다'고 했다 — 보도시점에 맞추게 바꾼다
            # (shared.작성원칙.날짜_기본.적용범위 와 같은 규칙).
            # '26-09-27 4차 벤치마크(구현자 B) — '보도시점에 맞춰 전날/같은날로 계산하라'는
            # 지시 자체가 **추정**이었다(조간=전날 규칙은 실무 관행일 뿐 자료의 사실이 아니다).
            # 심사 3인 모두 '2026. 11. 19.(목)'을 "자료에 없는 날짜"로 감점했고, 같은 표본에서
            # kordoc 은 날짜를 계산하지 않고 "2026. 11. ○○.(○)"처럼 아는 부분(연·월)만 채우고
            # 모르는 자리(일·요일)는 자리표시로 비워 감점을 피했다. 그 관행을 그대로 지시한다 —
            # 계산해서 채우지 말고, 모르면 비운다(자리표시는 build/지어냈나.py 가 봐준다).
            부.append('· "배포"는 이 보도자료를 실제로 배포(발송)하는 날짜다 — 자료에 배포일이 '
                      '명시돼 있으면 그 값을 쓰고, 없으면 ○○ 자리표시로 비운다(예: '
                      '"2026. 11. ○○.(○)" — 아는 부분만 채우고 모르는 일·요일은 ○○로 둔다). '
                      "조간이면 전날일 것이다 같은 계산으로 날짜를 추정해 채우지 마라.")
        if 정본 == "regulation":
            # 항·호·목 중첩 인코딩(cli:s4 수정, e2e r6 재진단 '26-09-27) — 위 모양 덤프는
            # 장·조 한 쌍만 보여줘 조 하나에 항·호·목이 여럿 딸린 실제 문서의 인코딩을 못
            # 보여준다. 규칙은 build/assemble_regulation.py 의 짜기() 가 갖고 있다(평면
            # 목록 + level 로만 깊이·번호를 센다) — 그 규칙을 짧은 예시로 그대로 옮긴다.
            # 예시 교체('26-09-28 규정 처방 P2, 내부 기록) — 옛 예시(재택근무·
            # 원격지)는 벤치마크 소재와 같았고, 제1조가 '정의'라 '첫 조=목적' 규칙과 어긋났으며,
            # '승인을 받아 신청한다'처럼 주어 없는 맨 '~한다'를 가르쳤다. 새 소재(공용 물품 대여)는
            # 벤치(재택근무)·본보기 표본(생성형 인공지능)·과적합 대조(업무용 차량) 어디에도 없다.
            # 정의 둘(하나짜리 정의는 호로 쓰지 않는다)·①항에 신청 행위·②항은 '제1항에 따른'·다른
            # 조 번호 교차 인용 없음·제1조에 기관명 없음. 한 줄 JSON(r7 s4.예시_찾음 정규식이
            # DOTALL 없이 읽는다) — 목록은 모듈 상수 _규정조문예시 가 정본이다.
            부.append(
                '· 규정 "본문"의 항·호·목은 **평면 목록**에 순서대로 담는다(중첩 JSON 아니다)'
                ' — 번호·깊이는 조립기가 앞뒤 "level" 을 보고 스스로 센다. "조" 바로 뒤에 '
                '"항"이 이어지면 그 조의 "text"가 자동으로 ①이 되고 다음 항부터 ②·③…으로 '
                '센다(항이 안 이어지면 조 본문엔 번호를 안 붙인다). "호"가 "항" 없이 조 '
                '바로 아래 오면 항과 같은 자리(한 칸 들여쓰기)에 선다. 예: '
                + json.dumps(_규정조문예시, ensure_ascii=False, separators=(",", ":"))     # reg13e E5 — 기관 이름은 자리표시 그대로
                + ' → 제1조(목적) → 제2조(정의) 1.·2. → 제3조(대여 제한) 1.·2. → '
                '제4조(대여 승인) ①②(항이 이어져 조 본문이 ①) → 제5조(준수사항) 1.·2.'
                '(호가 항 없이 항 자리에 섬). 예시의 소재·수치·조 제목은 베끼지 말고 '
                '문형(주어·술어·호 꼴)만 따른다. 정의할 말이 하나뿐이면 호를 두지 않고 '
                "'이 규정에서 “○○”란 …을 말한다.' 한 문장으로 쓴다. 장이 필요하면 "
                '{"level":"장","제목":"…"}을 그 장의 첫 조 앞에 둔다.')
        부 += ['· **제목·본문·항목에 번호·마커를 붙이지 마라** — 장 번호(Ⅰ.Ⅱ.)·조 번호(제N조)·절 마커(□)·항목 마커(○·-·※)는 시스템이 자동으로 붙인다. 순수 문구만 써라.',
              "· 아래 모양의 키·중첩 구조를 **글자 그대로** 따르고 값만 새로 채워라(값은 베끼지 마라).",
              "",
              json.dumps(모양, ensure_ascii=False, indent=1)[:(None if 온전 else 6000)],
              "",
              '"filename" 은 영문 소문자·하이픈으로 반드시 넣어라. **그 밖의 키 이름은 위 한글 그대로, 하나도 바꾸지 마라.**']
        if _선택키:
            부 += ["", "[선택 키 — 자료에 해당 내용이 있을 때만 위 최상위 키에 더해 써라(뜻·예시는 참고, 값은 자료로 채운다)]",
                  json.dumps((_지시문용정리 if 온전 else _프롬프트용정리)(_선택키), ensure_ascii=False, indent=1)]
        부.append("생략 가능(시스템이 채운다) — filename(비우면 제목에서 자동 생성), "
                 "purpose_type(plan_id 의 판정에서 자동, 있는 장르만). **plan_id 는 생략할 "
                 "수 없다** — 승인된 빌드플랜의 id 를 반드시 채워라.")
    else:
        부 += ["이 문서 종류의 정본 구조를 그대로 따르는 JSON. \"filename\" 은 영문 소문자·하이픈으로 반드시 넣어라.",
              "**주의: 이 종류의 실물 본을 못 가져왔다 — 키를 지어내지 말고 사용자에게 알려라.**"]
    if 추가지시:
        부 += ["", str(추가지시)]
    return "\n".join(x for x in 부 if x is not None)


def _설계지시문조립(자료, 장르="samples", 유형id=None, 추가지시="", 약한모델=False, 판형=None):
    """**2층 빌드플랜(작성 계획)** 을 짜는 시스템 프롬프트를 서버에서 만든다 — _지시문조립
    (초안용)과 같은 온톨로지를 당기되, 본문 대신 **buildplan/schema.json 구조의 설계 JSON**
    을 요청한다. '방법론까지만'(2층 경계)을 못박고, 실제 개수·문구·표 등장은 3층으로 미룬다."""
    한장 = (장르 == "samples")
    정본 = _장르정본(장르)
    온전 = not 약한모델      # _지시문조립 과 같은 원칙 — 강한 모델엔 통째로, 서버 소형 모델엔 예전 분량
    장르규칙 = _지식전체("document_types." + str(정본))
    장르값 = 장르규칙.get("값") or {"키": 장르규칙.get("키")}
    if 정본 == "slides":
        # 초안 지시문과 같은 판형으로 설계한다('26-09-28) — 설계와 초안이 서로 다른 규칙을 보면 안 된다.
        장르값 = _슬라이드규칙판형별(장르값, v2=(_슬라이드판형(판형) == "v2"), 약한모델=약한모델)
    # 규칙 일부 누락 경고(항목 8) — _지시문조립과 같은 원칙, 조용히 빼지 않는다.
    규칙누락경고 = None if 장르규칙.get("ok") else (장르규칙.get("로그") or "규칙 일부를 못 받았습니다")
    선택 = None
    if 한장:
        _ts = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
        if 유형id:
            선택 = next((t for t in _ts if t.get("id") == 유형id), None)
        선택 = 선택 or _유형판정(자료)
    부 = ["너는 대한민국 공공기관 문서의 **작성 계획(2층 빌드플랜)** 을 짜는 설계자다.",
         "아직 본문을 쓰지 마라 — **어떻게 만들지 설계만** 하고, 그 설계를 사용자가 승인한 뒤에야 초안을 쓴다.",
         "지금 설계할 문서 종류: " + str(정본), "",
         "[이 문서 종류의 규칙]",
         # 규정은 약한 설계 경로도 초안과 같은 6,000자까지 — 설계 지시문은 [선택 키] 블록이 없어 규칙 JSON 에 선택키가
         # 남고 문체.핵심이 그 뒤 맨 끝에 온다. 5,000자에서 핵심 10번(절차)이 잘렸다('26-09-30 판정 ①~④ 반영 뒤 실측
         # 5,203자, 내부 기록). 다른 장르는 그대로 5,000자.
         # reg13('26-09-30 bench15 J1~J6) — 핵심 줄(주체 이어받기·역할어 정의·말투 등)이 늘어 6,000자에서 끝 두 줄(절차·말투)이
         # 잘렸다(실측 -398자) → 규정만 약한 설계 7,000자(여유 602자). 초안 경로는 6,000자 그대로(여유 724자).
         # reg13d 판정 D6('26-10-01) — 규정은 핵심 줄을 앞에 두고 키 단위로 자른다(초안 경로와 같다).
         _장르규칙글(_규정지시문용(장르값) if 정본 == "regulation" else 장르값, 한장, 온전,
                    자르기=(7000 if 정본 == "regulation" else 5000), 핵심먼저=(정본 == "regulation"))]
    if 정본 == "regulation":
        # 설계 JSON 의 '적용방법론.본문.디자인' 칸은 여전히 채워야 하는데 P7 이 규칙 JSON 에서 '디자인'을
        # 뺐다 — 근거 없이 채우면 개조식 □○ 위계가 들어갈 수 있다('26-09-28 적대검토 F4). 글꼴·pt·들여쓰기
        # 수치(렌더러 몫)는 빼고 위계 원리 한 줄만 싣는다(온톨로지 document_types.regulation.디자인
        # 위계_크기·위계_굵게·들여쓰기의 요지).
        부.append("· 규정 디자인(적용방법론.본문.디자인 칸의 근거): 위계는 글자 크기가 아니라 굵기로 가른다 — "
                 "제N장·제N조 표제는 굵게, ①·1.·가.는 굵게 쓰지 않고 크기는 모두 같다. 항·호·목은 기호를 "
                 "왼쪽으로 빼는 내어쓰기로 가른다(조판 수치는 시스템이 정한다).")
    if 규칙누락경고:
        부.append(f"[!] 정책서버에서 {규칙누락경고} — 위 규칙이 온전하지 않을 수 있다.")
    if 온전:
        부 += _문체블록(정본)
    if 한장 and 선택:
        부 += ["",
              "[이 자료에 맞게 판정된 보고목적 유형과 목차 시퀀스 — 설계의 뼈대로 삼아라"
              + (". 절마다 절별_핵심질문에 답할 거리를 설계에 적어라]" if 온전 else "]"),
              json.dumps(_지시문용정리(선택) if 온전 else
                         {"id": 선택.get("id"), "이름": 선택.get("label"),
                          "표준시퀀스": 선택.get("표준시퀀스"),
                          "압축시퀀스": 선택.get("압축시퀀스")}, ensure_ascii=False, indent=1)]
    if 정본 == "slides" and _슬라이드판형(판형) == "v2":
        # 설계에도 초안과 같은 [목적·밀도·프리셋] 을 싣는다('26-09-28 v2 통합 E2E — 설계 지시문에 목적
        # 안내가 없어 설계가 보고/설득을 스스로 짐작했고, 아래 돌려줄 것의 1p 말(요약박스·□○)만 보였다).
        부 += _슬라이드v2목적분량(자료, 유형id)
        부.append("· 슬라이드 설계에서 '개체구성'의 개체는 장 유형(표지·한눈에보기·카드열·데이터·비교·일정·"
                 "체계도·표·요청·마무리 등), '본문순서'는 장 유형 순서다. 목적·프리셋·밀도와 요청 장을 둘지"
                 "(요청은 덱에서 한 번)를 판정 근거에 적고, 장별 부품·폭·머리 문구는 3층으로 미룬다.")
    부 += ["",
         "[사용자가 준 자료(사용자 메시지에 있다)를 읽고 요구 — 독자·목적·상황 — 를 분석하라]",
         "",
         "[돌려줄 것 — 아래 구조의 **JSON 하나만**, 다른 말 없이. 이것은 '작성 계획'이지 본문이 아니다]",
         "{",
         '  "request": {"원문요약": "자료 핵심 1~2줄", "입력유형": "명확지정|목적만|예시문서", "첨부": []},',
         '  "요구분석": {"독자": "누가 읽고 판단하나", "목적": "독자가 이 문서를 받고 무엇을 해야 하나(유형 판정 기준)",',
         '    "상황": "어떤 계기·배경에서 나온 보고인가",',
         '    "확인필요": [{"항목": "모호한 것", "질문": "사용자에게 물을 것", "왜": "왜 필요한지"}]},',
         '  "판정": {"문서유형": "' + str(정본) + '", "보고목적유형": "' + str((선택 or {}).get("id") or "") + '",',
         '    "근거": "왜 이 유형으로 판정했나 — 사용자가 반박할 수 있게 구체적으로",',
         '    "대안후보": [{"유형": "갈렸던 다른 유형", "탈락사유": "왜 그건 아닌가"}], "확신도": "높음|중간|낮음"},',
         '  "개체구성": [{"개체": "제목|요약박스|본문|붙임", "포함": true, "비고": "왜 넣나/빼나"}],',
         '  "적용방법론": {"본문": {"구성": "목차 패턴 요약", "문체": "이 종류의 문체 규칙", "디자인": "마커·시각 위계"}},',
         '  "본문순서": ["본문을 이 순서로 쓸 절 제목 목록 — 판정 유형의 표준 시퀀스를 따르되 자료에 맞게(3~5개)"],',
         '  "등장요소_전망": [{"요소": "표|이미지", "가능성": "높음|중간|낮음", "근거": "왜 그렇게 보나", "확정": "3층"}],',
         '  "제약": {"분량예산": "표 유무별 기준", "게이트": ["통과 기준"]},',
         '  "미확정_3층위임": ["일부러 안 정한 것 — 실제 절 개수·항목 수·최종 문구·표 등장 여부 등"],',
         '  "승인": {"status": "대기"}',
         "}"] + _설계그림지시(장르, 약한모델, _슬라이드판형(판형) if 정본 == "slides" else None) + [
         "",
         "[경계 — 반드시 지켜라]",
         "· 2층은 **방법론까지만** 정한다. 실제 □·○ 개수, 절 최종 문구, 표 등장 여부는 정하지 마라 — 자료를 보고 3층(초안)에서 정한다.",
         "· 안 정한 것은 '미확정_3층위임'에 반드시 적어라(경계를 지켰다는 증거다).",
         "· 모호한 것을 지어내지 마라 — '요구분석.확인필요'에 질문으로 남겨라(성실하기보다 되묻는다)."]
    if 추가지시:
        부 += ["", str(추가지시)]
    return "\n".join(x for x in 부 if x is not None)


# 요청에 적힌 문서 종류(fixup3 H, verify2 §2-E) — 점수 판정은 자료 신호를 세므로 "보도자료를 부탁드립니다"·
# "…요청하는 공문입니다"가 1p 기본값 2점에 졌다(시행문 0점으로 상위 3개 밖). 요청 한 줄(없으면 자료 첫 줄)에 종류
# 이름이 **요청의 목적어로** 있으면(바로 뒤 한 낱말 안에 만들라는 말·'입니다'·끝) 명시 장르 힌트로 싣는다. 두 종류가
# 같이 나오면 힌트 없음(애매하면 안 싣는다). 점수·순위는 그대로 둔다(웹앱 고름은 바뀌지 않는다).
_명시장르말 = (
    ("press", "보도자료", r"보도\s*자료|보도문"),
    ("gongmun", "시행문", r"시행문|공문"),
    ("regulation", "규정", r"규정|내규|규칙"),
    ("slides", "발표 슬라이드", r"슬라이드|발표\s*자료|프레젠테이션|PPT|ppt|피피티"),
    ("fullreport", "풀버전 보고서", r"풀\s*버전|정식\s*보고서"),
    ("samples", "1페이지 보고서", r"1\s*페이지|한\s*장\s*(?:짜리\s*)?보고서|1p\b|원\s*페이지"),
)
_명시장르뒤 = (r"(?:을|를|로|으로|이요|요|이에요|예요|입니다|이며|이고)?\s*(?:개정안|제정안|초안|보고서|문서|파일|안)?"
            r"\s*(?:\S+\s+)?(?:" + _말투_동사[1:-1] + r"|입니다|이에요|예요|필요|원합니다|좀|$|[.!?])")


def _명시장르(글):
    s = str(글 or "").strip()
    if not s:
        return None
    찾음 = {}
    for 등록부, 이름, 꼴 in _명시장르말:
        for m in re.finditer(r"(?:" + 꼴 + r")", s):
            if re.match(_명시장르뒤, s[m.end():]):
                찾음.setdefault(등록부, (이름, s[max(0, m.start() - 10):m.end() + 12].strip()))
                break
    if len(찾음) != 1:
        return None
    등록부, (이름, 말) = next(iter(찾음.items()))
    return {"등록부": 등록부, "이름": 이름, "말": 말}


@등록("판정", ["자료", "예시", "요청"],
    설명="자료 신호로 장르·1페이지 보고서 보고목적 유형을 점수 낸다(브라우저 고름용). 플러그인에서 장르는 에이전트가 "
        "요청을 읽고 정한다 — 이 점수는 1페이지 보고서 안에서 유형을 고를 때만 쓴다. 요청에 문서 종류 이름이 보이면 "
        "값.명시장르 에 참고로 싣는다",
    en="detect", 정책=True)
def 판정(자료="", 예시=None, 요청=""):
    """브라우저 신호읽기() 를 서버로 옮긴 것 — 장르판별.신호(정본)를 여기서만 읽고
    등록부별 점수·까닭만 돌려준다. 판별신호 자체는 클라이언트로 안 나간다."""
    # 예시 모양 검증(F4 e2e, '26-09-27 재진단) — 예시는 서식분석(analyzeform)이 돌려준
    # {"뼈대": {"절수":…, "조문수":…, "절당_항목":[…]}, …} 모양(dict)이다. 문서화된 예시가
    # 어디에도 없어, 자연스러운 문자열을 그대로 넣으면 build/판별로직.py 의 `예시.get("뼈대")`
    # 에서 AttributeError 로 그냥 죽었다(재현됨) — 우아한 검증 오류로 바꾼다.
    if 예시 is not None:
        if not isinstance(예시, dict):
            return {"ok": False, "로그":
                    "예시 는 객체(dict)여야 합니다 — 서식분석(analyzeform)이 돌려준 결과"
                    "({\"뼈대\": {\"절수\":…, \"조문수\":…, \"절당_항목\":[…]}, …})를 그대로 "
                    f"넣으세요. 받은 값의 종류: {type(예시).__name__}"}
        if not isinstance(예시.get("뼈대", {}) or {}, dict):
            return {"ok": False, "로그": "예시.뼈대 는 객체(dict)여야 합니다 — "
                    f"받은 값의 종류: {type(예시.get('뼈대')).__name__}"}
    # (cli:s2 수정, e2e r6 재진단 '26-09-27) — SKILL.md 의 '판정' 인자 예시는 자료를
    # 배열로 보여주는데(app.html·MCP 클라이언트도 흔히 배열로 보낸다) 예전엔 str(자료)로
    # 그냥 문자열화해 "['…']" 꼴 그대로 들어가, 문서화된 예시를 그대로 따르면 에러 없이
    # 조용히 다른 장르로 오판정됐다. _자료글 이 문자열·배열 모두 받아 이어 붙인다.
    글 = _자료글(자료)
    신호 = 지식("장르판별.신호").get("값") or {}
    장르목록 = 장르().get("값", {}).get("장르") or []
    # 세는 법·가중치·1p↔풀버전 판별 문구·문턱은 **규칙**이라 build/판별로직.py 에 있다.
    # 판정은 사용자 자료를 받으므로 정책 서버로 위임하지 않고 로컬에서 돈다(_자료작 분기,
    # 정책만-로컬: 사용자 정보보호 1순위). 따라서 이 규칙 모듈은 설치본에 함께 온다 —
    # 서버에서 받는 건 온톨로지 신호(장르판별.신호) 조각뿐, 사용자 자료는 안 나간다.
    # (정정 2026-08-27: 이전엔 "배포서 빠짐 · A1 에만 산다"로 적었으나 로컬 실행이라 사실
    #  아님. 온톨로지 지식 정본은 서버에만 있지만, 판정 규칙 코드는 설치본에 노출된다.)
    로직 = 자료뿌리.모듈("판별로직")
    결과 = 로직.점수매기기(글, 신호, 장르목록, 예시, _유형점수)
    # 1p 유형 동률 힌트(항목 10, e2e s1 friction, '26-09-27) — 유형(보고목적) 점수가
    # 동률이면 이를 가르는 우선순위규칙이 훨씬 뒤 설계지시문내기(composeplan) 응답에만
    # 실려 있어, 판정(detect) 만 보는 첫 호출자는 근거 없이 동률을 추측해야 했다. 판정
    # 응답에도 **같이** 실어 이 자리에서 바로 보이게 한다(온톨로지는 완전 공개라 노출
    # 문제는 없다 — _유형점수 의 "판별키워드는 안 낸다" 원칙과는 다른 결의 정보다).
    유형들 = 결과.get("유형") or []
    if len(유형들) >= 2 and (유형들[0].get("점") or 0) > 0 \
            and 유형들[0].get("점") == 유형들[1].get("점"):
        _우선 = 지식("document_types.onepage-report.구성.목차로직.우선순위규칙").get("값")
        if _우선:
            결과["유형_동률"] = True
            결과["유형_우선순위규칙"] = _우선
    _명 = _명시장르(요청 if str(요청 or "").strip() else (글.strip().splitlines() or [""])[0][:200])
    if _명:
        _명["근거"] = "요청" if str(요청 or "").strip() else "자료 첫 줄"
        결과["명시장르"] = _명
        _일위 = ((결과.get("장르") or [{}])[0] or {}).get("등록부")
        if _일위 and _일위 != _명["등록부"]:
            결과["명시장르_안내"] = (f"요청에 '{_명['이름']}'이(가) 보입니다(참고) — 장르는 요청을 읽고 정하세요. 점수 1위"
                               f"({(결과['장르'][0] or {}).get('이름')})는 자료 신호로 셈한 것입니다")
    # 장르는 **에이전트가 요청을 읽고 정한다**(fixup4 주관 ① '26-09-29, verify3 §5: 1p 기본값 2점 대 0점이 '뚜렷한 1위'로
    # 읽혀 "보도자료로 정리해 주세요" 12줄 중 10줄이 1페이지 보고서로 갔다). 점수·순위는 웹앱 화면용 그대로 두고, 명시장르
    # 힌트는 참고로만 싣는다(정규식 넓히기는 멈춤).
    결과["안내"] = ("장르는 에이전트가 요청을 읽고 정합니다 — 문서 종류를 말했으면 그 장르, 말이 없으면 내용으로 고릅니다. "
                  "이 점수는 1페이지 보고서 안에서 보고목적 유형을 고를 때만 씁니다(장르 점수는 참고)")
    # 올린 자료 속 그림('26-09-30) — 판정 확인 때 한 줄로 보인다. 그림을 어디에 쓸지는 장르 정책(genres.그림정책)이
    # 정하므로 장르마다 '이 문서에 그림 자리가 있나'를 같이 싣는다. 목록 전체는 그림목록(figures) 작업.
    try:
        _카 = _그림카드들()
        if _카:
            _g = 자료뿌리.모듈("genres")
            결과["그림"] = {"요약": 자료뿌리.모듈("imageasset").카드요약(_카),
                          "자리있는장르": [s for s in _g.그림정책 if _g.그림정책값(s)["자리"]]}
            결과["안내"] += " · " + 결과["그림"]["요약"]
    except Exception as _e:
        print(f"[그림] 판정 요약 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    return {"ok": True, "값": 결과, "로그": 결과["안내"]}


@등록("프롬프트조립", ["자료", "장르", "유형id", "예시", "추가지시", "plan_id"],
    설명="서버가 온톨로지로 조립한 완성 시스템 프롬프트만 돌려준다(원문은 안 나간다) — 키 있는 브라우저가 이걸로 직접 모델을 부른다. "
        "plan_id(승인된 설계)를 주면 그 설계의 그림 계획을 싣는다(없으면 이 장르로 승인된 가장 새 설계)",
    en="compose", 정책=True)
def 프롬프트조립(자료, 장르="samples", 유형id=None, 예시=None, 추가지시="", plan_id=None):
    return {"ok": True, "값": {"지시문": _지시문조립(자료, 장르, 예시, 추가지시, 유형id, plan_id=plan_id)}}


# 장르별 문체 — 개체 재작성 프롬프트에 실어 개조식/공손체를 지킨다(_지시문조립 문체규칙과 같은 뜻).
_문체규칙 = {
    "slides": "개조식 명사형(완결 주장 문장), 군더더기 없이 짧게",
    "onepage-report": "개조식 명사형", "fullreport": "개조식 명사형",
    "gongmun": "서술어 완결 + 공손체(~하시기 바랍니다)",
    "press-release": "보도자료 서술형", "regulation": "조문체",
}

# 규정은 개체(라벨)마다 문체가 다르다('26-09-28 규정 처방 P1, 내부 기록) —
# '조문체' 한 단어만 실으면 편집기에서 호를 AI 로 다듬을 때 모델이 '~한다.' 문장으로 되돌려,
# 초안에서 고친 호 꼴을 리터칭 단계가 다시 깼다. 라벨은 편집기 프로필(editor-profiles.json
# regulation: '조'·'항 ①'·'호 1.'·'목 가.'·'제정이유'·'주요내용')의 것. **BYOK 쪽
# workspace/render_editor_any.py 의 _규정문체() 와 문구를 똑같이 둔다**(두 벌이 어긋나면
# 편집기 경로마다 결과가 달라진다 — test/r14_reg14.py 가 대조한다).
_규정개체문체 = (
    (("호", "목"), "조문체의 호·목 — 지금 꼴(명사구·'~할 것'·'…한 경우')을 바꾸지 말고 다듬는다. 정의 호 '“○○”란 …을 말한다.'는 그 꼴을 지킨다"),
    (("조", "항"), "조문체 — 완결 문장('~하여야 한다'·'~할 수 있다'·'~하여서는 아니 된다'). 목적·적용·시행·설치 조의 맨 '~한다'는 그대로 둔다"),
    (("제정이유",), "제정이유 — 배경과 목적을 한 단락으로 적고 '~하려는 것임.'으로 맺는다"),
    (("주요내용",), "주요내용 — '~함'·'~하도록 함'으로 맺고, 끝의 조 인용 괄호는 그대로 둔다"),
)


def _재작성문체(장르, 라벨=""):
    정본 = _장르정본(장르)
    if 정본 == "regulation":
        # 라벨 첫 낱말을 **정확히** 견주고, 뒤에는 기호('①'·'1.'·'가.')만 올 수 있다 — 앞머리 startswith 는
        # '항목'·'조 제목' 같은 라벨도 조·항 문체로 보냈다(적대검토 F8). BYOK(render_editor_any.py
        # _규정문체)와 같은 규칙.
        조각 = str(라벨 or "").split()
        라 = 조각[0] if 조각 and not re.search(r"[가-힣]{2,}", " ".join(조각[1:])) else ""   # '가.'는 기호
        for 머리들, 문 in _규정개체문체:
            if 라 in 머리들:
                return 문
    return _문체규칙.get(정본) or "이 문서 종류의 문체를 그대로"


def _재작성배경(장르, 문서키):
    """편집기 AI 재작성(개체고쳐)에 실을 '이 문서의 배경' — 최초 의도·자료.

    원자료는 **클라이언트를 왕복하지 않는다**. 편집기는 자기 문서키(파일명)만 넘기고,
    서버가 자기 세션 등록부에서 그 문서의 `_맥락`(app.html 이 새문서 때 심은 의도+자료)을
    찾아 쓴다. 없으면 빌드플랜(plan_id)의 증류 맥락(원문요약·요구분석)으로 폴백한다.
    둘 다 없으면 빈 문자열 — 문체만으로 국소 재작성(현행 동작)한다.
    """
    문서키 = str(문서키 or "").strip()
    if not 문서키:
        return ""
    # 편집기가 보내는 장르(문체용, 예: onepage)와 등록부 이름(예: samples)이 어긋날 수 있어,
    # 문서키로 이 세션의 등록부를 훑어 찾는다 — 준 장르 것을 먼저 보고, 없으면 전수.
    d = None
    try:
        후보 = []
        주등록 = 자료뿌리.등록부(장르)
        if 주등록 not in 후보:
            후보.append(주등록)
        for p in 자료뿌리.등록부들():
            if p not in 후보:
                후보.append(p)
        for 등록 in 후보:
            if not os.path.exists(등록):
                continue
            try:
                docs = json.load(open(등록, encoding="utf-8"))
            except Exception:
                continue
            d = next((x for x in docs if isinstance(x, dict) and x.get("filename") == 문서키), None)
            if d:
                break
    except Exception:
        d = None
    if not isinstance(d, dict):
        return ""
    조각 = []
    맥락 = d.get("_맥락")
    if isinstance(맥락, dict):
        의도 = str(맥락.get("의도") or "").strip()
        if 의도:
            조각.append("의도·자료: " + 의도[:1200])
    if not 조각:                                    # 폴백 — 빌드플랜의 증류 맥락
        pid = str(d.get("plan_id") or "").strip()
        if pid:
            try:
                plan = json.load(open(자료뿌리.플랜(pid), encoding="utf-8"))
                req = plan.get("request") or {}
                요구 = plan.get("요구분석") or {}
                요약 = str(req.get("원문요약") or "").strip()
                if 요약:
                    조각.append("핵심: " + 요약[:600])
                지향 = " · ".join(str(요구.get(k) or "").strip()
                                for k in ("독자", "목적", "상황") if str(요구.get(k) or "").strip())
                if 지향:
                    조각.append("독자·목적: " + 지향[:400])
            except Exception:
                pass
    if not 조각:
        return ""
    return ("\n\n[이 문서의 배경 — 아래 문구를 이 맥락에 맞게 다듬되, 배경 자체를 출력하지는 마라]\n"
            + "\n".join(조각))


@등록("개체고쳐", ["원문", "라벨", "장르", "지시", "셀들", "문서키"], 읽기=False,
    설명="고른 개체(문구 하나 또는 표 셀들)를 서버 모델로 고쳐 돌려준다 — 키 없는 웹앱(기본키)의 "
    "편집기 AI 편집. 브라우저 대신 서버가 호출하므로 BYOK 키가 없어도 된다. 문서키를 주면 "
    "그 문서의 최초 의도·자료 맥락을 서버가 되찾아 함께 싣는다(원자료는 클라를 안 거친다).",
    en="airewrite", 정책=True, 서버모델=True)
def 개체고쳐(원문="", 라벨="개체", 장르="samples", 지시="", 셀들=None, 문서키=""):
    if not _서버LLM설정():
        return {"ok": False, "로그": "서버 모델이 설정되어 있지 않습니다 — 관리자에게 문의하세요"}
    문체 = _재작성문체(장르, 라벨)
    _배경 = _재작성배경(장르, 문서키)          # 최초 의도·자료(있으면) — 국소 재작성이 문서 맥락에 맞게
    _방향 = ("\n\n[고칠 방향] " + str(지시)) if str(지시 or "").strip() else "\n\n[고칠 방향] 더 또렷하고 간결하게 다듬어라."
    if isinstance(셀들, list) and 셀들:          # 표 셀 재작성 — 개수·순서 유지, 위치로 되박는다
        지시문 = ("너는 대한민국 공공문서 편집자다. 아래 표의 각 셀 문구를 고쳐 쓴다. 규칙: " + 문체
                 + ". 셀 개수와 순서를 그대로 유지하고, 없는 사실·수치는 지어내지 마라 — 모르는 값은 ○○ 한 꼴로 비워라." + _배경
                 + " 반드시 {\"고친셀들\":[\"…\"]} JSON 하나만 출력한다 — 입력과 같은 길이 배열.")
        사용자 = json.dumps({"셀들": [str(c) for c in 셀들]}, ensure_ascii=False) + _방향
        # 편집기는 받은 칸을 **위치로** 되박는다 — 칸 수가 다르면 글·숫자가 옆 칸으로 밀려 저장됐다(적대 검토 H1
        # '26-09-29). 길이가 다르면 한 번 되묻고, 그래도 다르면 적용하지 않는다(편집기도 같은 것을 거른다).
        n = len(셀들)
        for 차례 in range(2):
            try:
                doc = _서버LLM호출(지시문, 사용자 if not 차례 else
                                  사용자 + f"\n\n[주의] 입력은 {n}칸이다. 고친셀들도 정확히 {n}개, 같은 차례로.",
                                  None, 장르)
            except Exception as e:
                return {"ok": False, "로그": f"서버 모델 호출에 실패했습니다: {type(e).__name__}"}
            고친 = (doc or {}).get("고친셀들") if isinstance(doc, dict) else None
            if not isinstance(고친, list) or not 고친:
                return {"ok": False, "로그": "서버 모델이 표를 못 고쳤습니다 — 잠시 후 다시 시도해 주세요"}
            if len(고친) == n:
                return {"ok": True, "값": {"고친셀들": [str(c) for c in 고친]}}
        return {"ok": False, "로그": f"AI가 칸 수를 바꿔 보내({n}칸 → {len(고친)}칸) 적용하지 않았습니다 — 다시 시도해 주세요"}
    원문 = str(원문 or "").strip()
    if not 원문:
        return {"ok": False, "로그": "고칠 글이 비었습니다"}
    지시문 = ("너는 대한민국 공공문서 편집자다. 아래 「" + str(라벨) + "」 문구 하나를 고쳐 쓴다. "
             "규칙: " + 문체 + ". 번호·마커(□○-·①·제N조 등)는 붙이지 마라(시스템이 붙인다). "
             "없는 사실·수치를 지어내지 마라 — 모르는 값은 ○○ 한 꼴로 비워라." + _배경
             + " 반드시 {\"고친글\":\"고친 문구\"} JSON 하나만 출력한다.")
    사용자 = 원문 + _방향
    try:
        doc = _서버LLM호출(지시문, 사용자, None, 장르)
    except Exception as e:
        return {"ok": False, "로그": f"서버 모델 호출에 실패했습니다: {type(e).__name__}"}
    고친 = (doc or {}).get("고친글") if isinstance(doc, dict) else None
    if not 고친 or not str(고친).strip():
        return {"ok": False, "로그": "서버 모델이 고친 글을 못 냈습니다 — 잠시 후 다시 시도해 주세요"}
    return {"ok": True, "값": {"고친글": str(고친).strip()}}


@등록("요청내기", ["자료", "장르", "유형id", "예시", "추가지시", "지시문"], 읽기=False,
    설명="AI 에게 초안을 부탁하는 요청을 대기열에 남긴다(키 없이 쓰는 길). 지시문을 안 주면 서버가 온톨로지로 조립한다",
    en="ask")
def 요청내기(자료="", 장르="samples", 유형id=None, 예시=None, 추가지시="", 지시문=None):
    import time as _t, uuid
    # ask 경로 = 서버가 자기 소형 모델로 직접 초안을 쓴다 → 약한모델=True(카탈로그·few-shot 크러치 ON).
    지시 = 지시문 if 지시문 else _지시문조립(자료, 장르, 예시, 추가지시, 유형id, 약한모델=True)
    os.makedirs(_대기(), exist_ok=True)
    rid = _t.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    본 = {"id": rid, "낸때": _t.strftime("%Y-%m-%dT%H:%M:%S"), "상태": "기다림",
         "장르": 장르, "지시문": 지시, "자료": 자료, "예시": 예시, "답": None}
    # 5초마다 폴링하는 화면이 반토막 JSON 을 집지 않게(E-4)
    자료뿌리.원자json(_요청길(rid), 본, indent=1)
    # 서버 기본 LLM 키가 있으면 **서버가 스스로 채운다**(채팅을 안 기다린다). 없으면 그대로
    # 대기열에 남아 채팅이 집어 간다(무키 폴백). 세션 열쇠는 스레드지역이라 붙잡아 넘긴다.
    서버처리 = bool(_서버LLM설정())
    if 서버처리:
        열쇠 = 자료뿌리.세션열쇠()
        threading.Thread(target=_서버채움, args=(rid, 열쇠), name=f"llm-{rid}", daemon=True).start()
    return {"ok": True, "값": {"id": rid, "서버처리": 서버처리}}


# ── 2층 빌드플랜(작성 계획) — 판정과 초안 사이의 '설계 확정' 단계 (제품 5단계 ③) ──────
# 세 표면 공용: 웹앱·스킬·MCP 모두 여기를 거친다. 초안(3층)과 같은 두 갈래다 —
# 키 있는 브라우저·에이전트는 '설계지시문내기'로 지시문만 받아 **자기 모델**로 플랜을
# 짓고(플랜저장), 키 없는 웹앱은 '설계'가 **서버 기본 모델**로 대신 짓는다. 지은 플랜은
# 승인화면(plan.html)으로 사람이 보고 '플랜승인' 한다 — 승인돼야 초안이 등록·조립된다
# (_플랜승인막힘 게이트, 이미 저장·새문서에 물려 있음).
@등록("설계지시문내기", ["자료", "장르", "유형id", "추가지시"], 정책=True,
    설명="서버가 온톨로지로 조립한 '작성 계획(2층)' 설계 프롬프트만 돌려준다(원문은 안 나간다) — 키 있는 브라우저·에이전트가 이걸로 직접 모델을 불러 빌드플랜 JSON 을 짓는다",
    en="composeplan")
def 설계지시문내기(자료, 장르="samples", 유형id=None, 추가지시=""):
    return {"ok": True, "값": {"지시문": _설계지시문조립(자료, 장르, 유형id, 추가지시)}}


# 빌드플랜에서 승인화면(buildplan/render_plan.py)이 **객체 목록으로만** 읽는 칸 — (위치, 칸, 객체가 가질 키). 여기에 글
# 목록을 주면 저장은 되고 승인화면이 트레이스백으로 죽었다(verify5 N6: 판정.대안후보 ["②","⑤"]). 저장할 때 무엇이
# 틀렸는지 말한다. 승인화면이 스스로 걸러 읽는 칸(개체구성·등장요소_전망의 글 항목, 객체가 아닌 판정·요구분석)은
# 막지 않는다(정밀도 우선 — 화면이 죽는 꼴만).
_플랜객체목록칸 = (("판정", "대안후보", ("유형", "탈락사유")), ("요구분석", "확인필요", ("항목", "질문", "왜")))


def _플랜꼴문제(plan):
    """빌드플랜 꼴 검사 → 틀린 곳을 사람말로(없으면 [])."""
    틀림 = []
    for 위, 칸, 키들 in _플랜객체목록칸:
        몸 = plan.get(위)
        v = 몸.get(칸) if isinstance(몸, dict) else None
        if not isinstance(v, list):
            continue
        for i, x in enumerate(v):
            if not isinstance(x, dict):
                틀림.append(f"'{위}.{칸}[{i}]' 값이 {json.dumps(x, ensure_ascii=False)[:20]}입니다. "
                          + "{" + ", ".join(f'"{k}": …' for k in 키들) + "} 형식의 객체 목록이어야 합니다.")
                break
    return 틀림


@등록("플랜저장", ["plan", "장르"], 읽기=False,
    설명="모델이 지은 작성 계획(빌드플랜) JSON 을 승인 대기 상태로 저장한다 — plan_id 를 돌려준다",
    en="saveplan")
def 플랜저장(plan=None, 장르="samples"):
    import time as _t, uuid
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except Exception:
            return {"ok": False, "로그": "작성 계획이 JSON 이 아닙니다"}
    if not isinstance(plan, dict):
        return {"ok": False, "로그": "작성 계획(JSON 객체)이 필요합니다"}
    틀림 = _플랜꼴문제(plan)
    if 틀림:
        return {"ok": False, "로그": "작성 계획 형식이 맞지 않아 저장하지 않았습니다. " + " ".join(틀림[:5])}
    pid = plan.get("plan_id") or (_t.strftime("plan-%m%d-%H%M%S-") + uuid.uuid4().hex[:4])
    try:
        자료뿌리.플랜(pid)            # 꼴 검사(보안 '26-10-01 — 경로 조각이 든 plan_id 로 세션 밖에 쓰지 않게)
    except 자료뿌리.플랜아이디틀림:
        # 거절하지 않고 안전한 새 이름을 붙인다 — 서버 모델이 지은 plan_id 에 공백 등이 섞여도 흐름이 멈추지 않게.
        # 돌려준 plan_id 로만 승인·조립하므로 밖으로 새는 길은 없다.
        pid = _t.strftime("plan-%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    plan["plan_id"] = pid
    plan["장르"] = 장르
    승인 = plan.get("승인") if isinstance(plan.get("승인"), dict) else {}
    if (승인.get("status") or "").strip() not in ("대기", "승인", "수정요청", "되묻기중"):
        승인["status"] = "대기"
    plan["승인"] = 승인
    자료뿌리.원자json(자료뿌리.플랜(pid), plan, indent=1)
    return {"ok": True, "값": {"plan_id": pid}}


@등록("설계", ["자료", "장르", "유형id", "추가지시"], 읽기=False,
    설명="서버가 자료로 '작성 계획(2층 빌드플랜)' 을 짓는다(키 없이 쓰는 길) — 서버 기본 모델이 설계 프롬프트로 빌드플랜 JSON 을 만들어 저장하고 plan_id 를 돌려준다",
    en="drawplan")
def 설계(자료="", 장르="samples", 유형id=None, 추가지시=""):
    if not _서버LLM설정():
        return {"ok": False, "로그": "서버 기본 모델이 설정되어 있지 않습니다 — 오른쪽 위 “API 키”를 넣고 브라우저에서 직접 설계해 주세요"}
    지시 = _설계지시문조립(자료, 장르, 유형id, 추가지시, 약한모델=True)   # 서버 소형 모델이 직접 설계
    try:
        plan = _서버LLM호출(지시, str(자료))      # _JSON뽑기 경유 파싱된 dict (반토막 대비 3회 되시도)
    except Exception as e:
        return {"ok": False, "로그": f"작성 계획을 만들지 못했습니다 ({type(e).__name__})"}
    if not isinstance(plan, dict):
        return {"ok": False, "로그": "작성 계획을 JSON 으로 받지 못했습니다 — 다시 시도해 주세요"}
    return 플랜저장(plan, 장르)


@등록("플랜승인", ["plan_id", "status", "코멘트"], 읽기=False,
    설명="작성 계획(빌드플랜)의 승인 상태를 기록한다 — 승인/수정요청. 승인돼야 초안(3층)이 조립·등록된다",
    en="approveplan")
def 플랜승인(plan_id="", status="승인", 코멘트=""):
    import time as _t
    try:
        plan = json.load(open(자료뿌리.플랜(plan_id), encoding="utf-8"))
    except 자료뿌리.플랜아이디틀림:
        return {"ok": False, "로그": "그 작성 계획을 찾지 못했습니다"}
    except OSError:
        return {"ok": False, "로그": "그 작성 계획을 찾지 못했습니다"}
    except ValueError:
        return {"ok": False, "로그": "작성 계획 파일이 깨졌습니다"}
    if status not in ("승인", "수정요청", "대기", "되묻기중"):
        status = "승인"
    plan["승인"] = {"status": status, "코멘트": 코멘트 or "",
                  "일시": _t.strftime("%Y-%m-%dT%H:%M:%S")}
    자료뿌리.원자json(자료뿌리.플랜(plan_id), plan, indent=1)
    return {"ok": True, "값": {"plan_id": plan_id, "status": status}}


@등록("요청목록", ["id"], 설명="기다리는 요청들 — AI 가 이것을 보고 초안을 쓴다", en="asks")
def 요청목록(id=""):
    import glob as _g
    if id:
        길 = _요청길(id)
        if not 길 or not os.path.exists(길):
            return {"ok": False, "로그": f"그런 요청이 없습니다: {id}"}
        return {"ok": True, "값": json.load(open(길, encoding="utf-8"))}
    out = []
    for f in sorted(_g.glob(os.path.join(_대기(), "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        out.append({"id": d.get("id"), "상태": d.get("상태"), "장르": d.get("장르"),
                    "낸때": d.get("낸때"), "자료앞": (d.get("자료") or "")[:120],
                    "예시있음": bool(d.get("예시"))})
    return {"ok": True, "값": out}


@등록("응답주기", ["id", "doc"], 읽기=False,
    설명="AI 가 쓴 3층 JSON 을 요청에 물려 준다 — 웹앱이 그것을 받아 이어간다", en="answer")
def 응답주기(id, doc):
    길 = _요청길(id)
    if not 길 or not os.path.exists(길):
        return {"ok": False, "로그": f"그런 요청이 없습니다: {id}"}
    본 = json.load(open(길, encoding="utf-8"))
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except Exception as e:
            return {"ok": False, "로그": f"doc 이 JSON 이 아닙니다: {e}"}
    본["답"] = doc
    본["상태"] = "됐음"
    자료뿌리.원자json(길, 본, indent=1)          # E-4
    return {"ok": True, "값": {"id": id, "상태": "됐음"}}


# ── 비동기 작업(일감) — 긴 일을 HTTP 한 방에서 떼어낸다 ──────────────────
# 왜 필요한가 (구현계획.md §3 WP-S4): 조판게이트는 **최대 900초**다. 그것을 HTTP 한
# 방으로 받으면 브라우저·중간 프록시가 먼저 끊는다 — 서버는 멀쩡히 다 돌고 나서
# 아무에게도 전하지 못한다. 내보내기(hwpx·pdf)와 LLM 호출도 같은 성질이다.
#
# 그래서 위 대기열 3짝(요청내기·요청목록·응답주기)이 하던 모양을 **일반화**한다:
#     작업시작(이름, 인자) → id     뒤에 걸고 곧바로 돌아온다
#     작업상태(id)                  5초마다 물어본다 — 웹앱이 이미 쓰는 그 폴링
#
# **작업 이름별 분기는 두지 않는다.** 등록부에 적힌 것이면 무엇이든 뒤에 걸린다.
# 여기에 "게이트·내보내기·LLM" 같은 목록을 손으로 적으면 그 순간 목록이 둘로
# 갈리고, 새 작업이 늘 때 뒤에 걸 수 있는 것만 빠진다(구현계획.md 규칙 2).
#
# 상태는 셋뿐이다 — 진행 · 완료 · 실패.
#   · 작업이 예외로 죽으면 실패
#   · 작업이 `ok: False` 를 돌려줘도 **실패**다. 여기서 "돌기는 다 돌았으니 완료"
#     라고 적으면 게이트가 넘침을 짚었는데 화면에는 초록이 뜬다 — 이 저장소가
#     제일 자주 밟은 조용한 실패 모양이다(구현계획.md 규칙 3).
_일감꼴 = re.compile(r"[0-9]{4}-[0-9]{6}-[0-9a-f]{8}")
_이프로세스 = os.getpid()


def _일감길(jid):
    안 = os.path.abspath(자료뿌리.일감뿌리())
    이름 = os.path.basename(str(jid or ""))
    if not _일감꼴.fullmatch(이름):
        return None
    참 = os.path.abspath(os.path.join(안, 이름 + ".json"))
    # 세션 격리는 **경로가 곧 방**이라는 데 기대고 있다(구현계획.md 규칙 5).
    # 일감뿌리() 가 이미 세션 밑이므로, 남의 id 를 물어도 자기 방을 볼 뿐이다.
    # 꼴 검사와 이 확인은 그 방 밖으로 나가는 길을 한 번 더 막는다.
    return 참 if 참.startswith(안 + os.sep) else None


def _일감적기(길, 본):
    """일감 기록은 **원자적으로** 놓는다(WP-S2 ③) — 5초마다 폴링하는 화면이
    반토막 JSON 을 집으면 "그런 작업이 없습니다" 로 보인다."""
    자료뿌리.원자json(길, 본, indent=1)


def _살아있나(pid):
    """그 프로세스가 아직 있나. 없으면 그 일감을 돌리던 스레드도 없다."""
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


@등록("작업시작", ["이름", "인자"], 읽기=False, 비동기=False,
    설명="긴 작업을 뒤에 걸고 작업id 를 곧바로 돌려준다(조판게이트·내보내기·LLM)",
    en="startjob")
def 작업시작(이름, 인자=None):
    작 = 찾기(이름)
    if not 작:
        return {"ok": False, "로그": f"모르는 작업입니다: {이름}",
                "할수있는것": sorted(작업)}
    if not 작.get("비동기", True):
        # 일감을 다루는 작업을 다시 일감으로 걸면 껍데기만 쌓인다 — 부르는 쪽은
        # 상태를 물으려고 또 상태를 물어야 한다. 조용히 받아 두지 않고 여기서 선다.
        return {"ok": False, "로그": f"'{작['이름']}' 은 뒤에 걸 수 없는 작업입니다 — "
                                  f"그대로 부르세요"}
    # 관리자 작업은 작업시작으로 못 건다 (적대 리뷰 2026-08-09 치명 — 열쇠 없이
    # 설정.json 을 덮어썼다). 열쇠 게이트(WP-S5)는 오직 경계인 serve.py 에만 있고
    # **직접 이름으로 불린 작업**만 검사한다. 작업시작은 게이트 없는 만능 디스패처라,
    # 관리자 작업을 여기 태우면 serve.py 게이트를 통째로 건너뛴다 — 열쇠 없는
    # `작업시작{이름:관리자설정저장,…}` 이 배경 스레드에서 부르기()로 실행돼 설정을
    # 덮었다(HTTP·MCP 두 문 다 뚫렸다: MCP startjob 도 이 함수를 탄다). 관리자
    # 작업은 빨라 뒤에 걸 이유가 없으니 여기서 거부하고, 게이트 통과 경로(serve.py 가
    # 열쇠 확인 후 부르기()로 직접 부르는 길)만 남긴다. 부르기()에 관리자 블랭킷
    # 거부를 넣지 않는 까닭 — 그 정당한 경로까지 깨진다. 게이트는 경계에, 거부는 이 길목.
    # 공개 쓰기(규칙마당 게시)도 못 건다 — serve.py 의 공개쓰기 문(JSON 본문·출처·IP 상한)이 이 작업의
    # 게이트인데, 작업시작{이름:규칙마당남기기} 로 태우면 그 문을 통째로 건너뛴다('26-09-25 점검).
    if 작.get("공개쓰기"):
        return {"ok": False, "로그": f"'{작['이름']}' 은 공개 게시라 작업시작으로 못 겁니다 — 직접 부르세요"}
    if 작.get("관리자"):
        return {"ok": False, "로그": f"'{작['이름']}' 은 관리자 작업이라 작업시작으로 못 겁니다 — "
                                  f"관리자 면에서 직접 부르세요"}
    if 인자 is not None and not isinstance(인자, dict):
        return {"ok": False, "로그": "인자는 객체여야 합니다 — 예: {\"key\": \"…\"}"}

    jid = time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    길 = _일감길(jid)
    if not 길:
        return {"ok": False, "로그": "작업 id 를 만들지 못했습니다"}
    os.makedirs(자료뿌리.일감뿌리(), exist_ok=True)
    본 = {"id": jid, "이름": 작["이름"], "상태": "진행",
          # **인자 값은 안 적는다 — 이름만 적는다.** 저장의 payload 에는 문서 한 벌이
          # 통째로 들어 있어, 값을 적으면 일감 기록이 문서의 사본이 된다. 무엇을 시켰나는
          # 이름으로 충분하고, 무엇이 났나는 아래 `결과` 에 그대로 있다.
          "인자이름": sorted((인자 or {}).keys()),
          "낸때": time.strftime("%Y-%m-%dT%H:%M:%S"), "시작": time.time(),
          "pid": _이프로세스, "결과": None}
    _일감적기(길, 본)

    # 세션 열쇠는 **스레드 지역값**이다(자료뿌리.py 머리말). 새 스레드는 그 값을 물려
    # 받지 못하므로 여기서 붙잡아 두고 저쪽에서 다시 끼운다 — 안 하면 일감이 기본
    # 뿌리에서 돌아 남의 자리에 산출물을 쓴다(격리가 조용히 새는 모양).
    열쇠 = 자료뿌리.세션열쇠()

    def 돌기():
        with 자료뿌리.세션갈기(열쇠):
            try:
                결과 = 부르기(작["이름"], dict(인자 or {}))
            except BaseException as e:      # 스레드에서 새는 예외는 아무도 못 본다
                결과 = {"ok": False, "로그": f"{type(e).__name__}: {e}"}
            본["결과"] = 결과
            본["상태"] = "완료" if (isinstance(결과, dict) and 결과.get("ok")) else "실패"
            본["끝난때"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            본["걸린초"] = round(time.time() - 본["시작"], 1)
            try:
                _일감적기(_일감길(jid), 본)
            except Exception as e:
                # 여기서 못 적으면 부르는 쪽은 영영 '진행'으로 본다. 조용히 넘어가지
                # 않고 서버 기록에 남긴다 — 그것이 이 실패를 볼 수 있는 유일한 곳이다.
                sys.stderr.write(f"[일감] 결과를 적지 못했습니다: {jid} — "
                                 f"{type(e).__name__}: {e}\n")

    threading.Thread(target=돌기, name=f"일감-{jid}", daemon=True).start()
    return {"ok": True, "값": {"id": jid, "이름": 작["이름"], "상태": "진행"}}


@등록("작업상태", ["id"], 비동기=False,
    설명="뒤에 건 작업의 진행·완료·실패와 (끝났으면) 결과", en="jobstatus")
def 작업상태(id):
    길 = _일감길(id)
    if not 길 or not os.path.exists(길):
        # 남의 세션 id 도 여기로 온다 — **있다/없다를 갈라 말하지 않는다.**
        return {"ok": False, "로그": f"그런 작업이 없습니다: {id}"}
    try:
        본 = json.load(open(길, encoding="utf-8"))
    except ValueError as e:
        return {"ok": False, "로그": f"작업 기록을 읽지 못했습니다: {e}"}

    if 본.get("상태") == "진행" and not _살아있나(본.get("pid")):
        # 서버가 중간에 내려가면 그 일감을 돌리던 스레드도 같이 죽는다. 파일은
        # '진행' 인 채로 남아 폴링이 **영원히** 돈다 — 그것이 조용한 실패다.
        # pid 가 없어진 것을 봤을 때만 실패로 적는다(pid 가 살아 있으면 다른
        # 서버 프로세스가 같은 자료뿌리를 볼 수도 있으니 손대지 않는다).
        본["상태"] = "실패"
        본["결과"] = {"ok": False, "로그": "작업을 돌리던 서버가 내려갔습니다 — 다시 걸어 주세요"}
        본["걸린초"] = round(time.time() - (본.get("시작") or time.time()), 1)
        try:
            _일감적기(길, 본)
        except OSError as e:
            sys.stderr.write(f"[일감] 끊긴 작업을 적지 못했습니다: {id} — {e}\n")

    값 = {k: v for k, v in 본.items() if k != "시작"}
    if 본.get("상태") == "진행":
        값["걸린초"] = round(time.time() - (본.get("시작") or time.time()), 1)
    # 실패한 일감은 **바깥 ok 도 거짓**이다. 물어보기가 성공했다고 ok:true 를 내면
    # 부르는 쪽이 그걸 작업 성공으로 읽는다(구현계획.md 규칙 3).
    if 본.get("상태") == "실패":
        결 = 본.get("결과") or {}
        return {"ok": False, "값": 값,
                "로그": (결.get("로그") or "작업이 실패했습니다")}
    return {"ok": True, "값": 값}


# ── 내보내기 — 산출물 다섯 ───────────────────────────────────────────────

def _단독html(html):
    """내보내기용 자기완결 HTML — 서버 밖(file://)에서 열어도 서식이 살아 있게
    `../*.css`·`../*.js`(코드뿌리 build/)를 인라인하고 기본 폰트 Pretendard 를 data: 로 임베드한다.
    명조(NotoSerifKR 23MB)는 임베드하지 않고 시스템 폰트로 폴백, audit.js(원격 기록)는 뺀다.
    2026-08-17 사장님 지적: 내려받아 file:// 로 열면 ../tokens.css·../*.js 가 404 라 서식이 통째로 빠진다."""
    import base64
    빌드 = os.path.join(ROOT, "build")

    def 읽기(이름):
        try:
            return open(os.path.join(빌드, 이름), encoding="utf-8").read()
        except OSError:
            return None

    def 폰트박기(css):
        f = os.path.join(빌드, "fonts", "PretendardVariable.woff2")
        try:
            b = base64.b64encode(open(f, "rb").read()).decode("ascii")
            css = re.sub(r'url\((["\']?)fonts/PretendardVariable\.woff2\1\)',
                         'url("data:font/woff2;base64,' + b + '")', css)
        except OSError:
            pass
        # 명조는 파일이 23MB 라 임베드하면 산출물이 못 쓰게 커진다 — 시스템 세리프로 폴백
        css = re.sub(r'url\((["\']?)fonts/NotoSerifKR\.ttf\1\)\s*format\([^)]*\)',
                     'local("Noto Serif KR")', css)
        return css

    def css치환(m):
        이름 = m.group(1)
        c = 읽기(이름 + ".css")
        if c is None:
            return m.group(0)
        if 이름 == "tokens":
            c = 폰트박기(c)
        return '<style data-inlined="' + 이름 + '.css">\n' + c + '\n</style>'

    html = re.sub(r'<link\b[^>]*href="\.\./([A-Za-z0-9_-]+)\.css(?:\?[^"]*)?"[^>]*>', css치환, html)

    def js치환(m):
        이름 = m.group(1)
        if 이름 == "audit":
            return "<!-- audit.js 제외(단독본) -->"
        c = 읽기(이름 + ".js")
        if c is None:
            return m.group(0)
        return '<script data-inlined="' + 이름 + '.js">\n' + c + '\n</script>'

    html = re.sub(r'<script\b[^>]*src="\.\./([A-Za-z0-9_-]+)\.js(?:\?[^"]*)?"[^>]*>\s*</script>', js치환, html)
    return _그림박기(html)


_단독그림상한 = 60 * 1024 * 1024       # 한 문서에 박는 그림 합(base64 전) — 넘으면 남은 그림은 상대 경로 그대로 두고 알린다


def _그림박기(html):
    """단독 HTML 의 그림을 data: 로 박는다(P3 '26-09-30, design §8) — 상대 경로(../assets/…)라 내려받아 열면 그림이
    깨졌다. 이 세션 자산 폴더(세션 build/) 안의 래스터만 박고(imageasset._안전한그림길), 사진은 더 작으면 JPEG 로,
    AI 생성 그림(자산 이름 gen-…)은 파일 안 'AI 생성물' 표기가 남게 PNG 그대로 둔다."""
    import html as _h
    ia = 자료뿌리.모듈("imageasset")
    기준 = 자료뿌리.산출물뿌리()
    합, 넘침 = [0], [0]

    def 바꿈(m):
        src = _h.unescape(m.group(1))
        if src.startswith("data:") or re.match(r"^[a-z][a-z0-9+.-]*:", src, re.I):
            return m.group(0)
        길 = os.path.normpath(os.path.join(기준, src))
        uri = ia.데이터URI(길, 생성=bool(re.match(r"gen-[0-9a-f]{12}\.png$", os.path.basename(길))))
        if not uri:
            return m.group(0)
        if 합[0] + len(uri) > _단독그림상한:
            넘침[0] += 1
            return m.group(0)
        합[0] += len(uri)
        return '<img src="' + uri + '"'

    html = re.sub(r'<img src="([^"]+)"', 바꿈, html)
    if 넘침[0]:
        print(f"[html단독] 그림 {넘침[0]}장은 크기 상한을 넘어 박지 않았습니다(상대 경로 그대로)", file=sys.stderr)
    return _그림흔적걷기(html)


_단독화면키 = ("목차", "쪽번호", "화면")      # 단독본의 인라인 스크립트(풀버전 조판·목차, present.js)가 읽는 화면 설정


def _문서섬빼기(html):
    """단독 HTML 에서 문서 JSON 섬(#fr-doc)을 통째로 뺀다('26-09-30 주관 판정 ③) — 화면에 안 보이는 칸(못 쓴 캡션·
    올린 파일 이름·원문에서 온 값)이 '소스 보기'로 그대로 읽혔다. 인라인 스크립트가 이 섬에서 읽던 화면 설정(목차 깊이·
    쪽번호·목차 점프·발표 화면 기능)만 스크립트 안의 글자로 옮긴다 — 섬이 없으면 기본값으로 조판돼 PDF·작업 화면과
    달라진다. 작업 HTML·편집기 HTML 에는 섬을 둔다(편집기·다시 굽기가 읽는다). 이 파일로는 이어받기(resume)를 할 수 없다."""
    m = re.search(r'<script\b[^>]*\bid="fr-doc"[^>]*>(.*?)</script>\n?', html, flags=re.S)
    if not m:
        return html
    try:
        d = json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        d = {}
    설정 = {k: d[k] for k in _단독화면키 if isinstance(d, dict) and k in d}
    글 = json.dumps(json.dumps(설정, ensure_ascii=False), ensure_ascii=False).replace("</", "<\\/")
    html = html[:m.start()] + html[m.end():]
    html = re.sub(r"""document\.getElementById\((['"])fr-doc\1\)\.textContent""", lambda _m: 글, html)
    html = re.sub(r"""document\.getElementById\((['"])fr-doc\1\)""", lambda _m: "{textContent: " + 글 + "}", html)
    return html


def _그림흔적걷기(html):
    """밖으로 나가는 단독 HTML 에서 그림 편집 흔적을 걷는다('26-09-30 fixup, review_practice2 N10) — 못 실은 그림의 표식
    블록(hidden·data-miss)은 통째로, 실린 그림 블록의 스펙(data-img: 올린 파일 이름·못 쓴 캡션·함의)과 요청 id(data-gen)
    속성은 뺀다. 화면에는 안 보여도 '소스 보기'로 읽혔다. 작업 HTML(편집기가 쓴다)은 그대로 둔다.
    문서 JSON 섬(#fr-doc)은 통째로 뺀다(_문서섬빼기, '26-09-30 주관 판정 ③)."""
    html = _문서섬빼기(html)
    html = re.sub(r'<div class="blk fr-fig fr-img[^"]*"[^>]*\bdata-miss="[^"]*"[^>]*>.*?</div></div>\n?', "", html,
                  flags=re.S)

    def 속걷기(m):
        return re.sub(r'\s(?:data-img|data-gen|data-miss)="[^"]*"', "", m.group(0))
    return re.sub(r'<div class="blk fr-fig fr-img[^"]*"[^>]*>', 속걷기, html)


# ── 검사 기록과 내보내기 관문(H2, '26-09-29 주관 판정) ─────────────────────────────────────
# 바로 완성은 마지막 사람(편집기에서 "이대로 좋다")을 뺐다. 그래서 "게이트는 그대로"가 plan_id 에만 참이던 것을
# 코드로 닫는다: 문체검사·조판게이트·지어냈나가 **문서 하나(key)** 로 돌 때마다 그 판(내용 해시)의 결과를 적고,
# 플러그인(MCP·CLI)의 내보내기는 **지금 판**의 기록이 없거나 hard·지어냄 실패면 거절한다. 사람이 확인한 뒤
# 굳이 내보낼 때만 강행이유(이유 필수)로 넘긴다. 웹앱·로컬 편집기 서버(문서지능_웹앱)는 사람이 화면을 쥐므로
# 면제한다. 기록은 세션 뿌리의 workspace/검사기록.json — 키마다 {판, 문체, 조판, 지어냄, 확장}.
def _판해시(doc):
    """문서 내용의 지문 — 낙관적 잠금 표(_수정시각)는 뺀다(내용이 같으면 같은 판)."""
    d = {k: v for k, v in (doc or {}).items() if k != "_수정시각"} if isinstance(doc, dict) else doc
    return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()[:20]


def _검사기록길():
    return os.path.join(자료뿌리.작업뿌리(), "검사기록.json")


def _검사기록읽기():
    try:
        d = json.load(open(_검사기록길(), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _잰판(key, doc=None):
    """재기 **시작 때**의 내용 지문 {판: 문서 JSON 해시, html: 조립 HTML 지문|None} — 검사 결과는 이 지문에 묶어 적는다
    (fixup5 주관 ①, verify4 §5 경합: 조판게이트가 v1 을 재는 동안 v2 가 저장되면, 기록을 **적는 순간** 문서를 다시 읽던
    예전 길은 v1 의 PASS 를 v2 의 기록으로 적었고 내보내기 pdf 가 v1 인쇄본을 '같은 판'으로 베꼈다). doc 을 주면 그
    내용(검사가 실제로 읽은 판)으로 판을 매긴다. 문서가 없으면 None."""
    if doc is None:
        r = 문서(key)
        if not r.get("ok"):
            return None
        doc = r["값"]
    return {"판": _판해시(doc), "html": _산출지문(key) if _산출지문쓰나() else None}


def _같은지문(x, 지금):
    """기록 칸 x 가 지금 지문(_잰판)과 같은 판을 잰 것인가 — 판이 같고, 둘 다 HTML 지문이 있으면 그것도 같아야 한다."""
    if not (isinstance(x, dict) and isinstance(지금, dict) and x.get("판") and x.get("판") == 지금.get("판")):
        return False
    return not (x.get("html") and 지금.get("html") and x["html"] != 지금["html"])


def _검사줄고치기(key, 고치기, 잰=None):
    """key 문서의 검사 기록 한 줄을 빗장 안에서 고친다. 칸마다 **잰 판의 지문**을 달아 두므로 줄 전체를 판으로 갈아
    엎지 않는다(늦게 끝난 옛 판의 결과가 새 판의 칸을 지우지 않게 — 옛 판 칸은 지문이 달라 내보내기가 보지 않는다).
    `잰` 이 없으면(조립 때의 산출 지문) 지금 판을 읽는다. 실패해도 검사 자체를 막지 않는다(기록이 없으면 내보내기가
    거절할 뿐이다)."""
    if 잰 is None:
        잰 = _잰판(key)
    if not 잰:
        return
    길 = _검사기록길()
    os.makedirs(os.path.dirname(길), exist_ok=True)
    with 자료뿌리.빗장(길):
        기록 = _검사기록읽기()
        줄 = 기록.get(str(key)) if isinstance(기록.get(str(key)), dict) else {}
        줄["판"] = 잰["판"]           # 마지막으로 적은 칸의 판(참고용) — 내보내기는 칸마다의 지문을 본다
        고치기(줄)
        기록[str(key)] = 줄
        자료뿌리.원자json(길, 기록, ensure_ascii=False, indent=1)


def _검사적기(key, 칸, ok, 건너뜀=None, 더=None, 잰=None):
    """key 문서의 검사 한 칸의 결과를 **잰 판의 지문**(`잰` — 재기 시작 때 _잰판)과 함께 적는다. `잰` 이 없으면 지금 판
    (검사 없이 바로 적는 '건너뜀' 기록). 같은 판에 이미 적힌 FAIL 은 '건너뜀'(원문 없는 재검사)이 덮지 못한다(fixup3,
    verify2 §1-B X1). `더` 는 칸에 곁들일 값(조판: 인쇄한 검사 PDF 의 지문 — 내보내기 pdf 재사용 판단).
    적었으면 True, 못 적었으면 False(fixup6 — 부르는 쪽이 '기록 없는 통과'를 내지 않게)."""
    if 잰 is None:
        잰 = _잰판(key)
    if not 잰:
        return False

    def 고치기(줄):
        옛 = 줄.get(칸)
        if (건너뜀 and isinstance(옛, dict) and 옛.get("ok") is False and not 옛.get("건너뜀")
                and 옛.get("판") == 잰["판"]):
            return
        줄[칸] = {"ok": bool(ok), "시각": time.strftime("%Y-%m-%dT%H:%M:%S"), "판": 잰["판"]}
        if 잰.get("html"):
            줄[칸]["html"] = 잰["html"]
        if 건너뜀:
            줄[칸]["건너뜀"] = str(건너뜀)
        if isinstance(더, dict):
            줄[칸].update(더)
    try:
        _검사줄고치기(key, 고치기, 잰)
        return True
    except Exception as e:
        print(f"[검사기록] {key}/{칸} 적기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
        return False


def _잰판그대로(key, 잰, 이름):
    """재기가 끝난 뒤 지문이 시작 때와 같은가 — 다르면 (False, 알림). 그 결과는 어느 판을 쟀는지 모르므로 적지 않는다."""
    if 잰 is None or _잰판(key) == 잰:
        return True, ""
    return False, (f"\n⚠ {이름}을(를) 재는 도중 문서가 바뀌었습니다(다른 저장·편집기 자동 저장) — 이 결과는 어느 판을 잰 것인지 "
                   f"알 수 없어 검사 기록에 적지 않았습니다. 지금 판에 {이름}을(를) 다시 부르세요.")


# 산출 HTML 지문(X5, fixup3) — 판 해시는 JSON 만 본다. 검사를 다 통과한 뒤 산출 HTML(build/samples/<key>.html)을
# 직접 고치면 PDF·HWPX·PPTX 는 그 HTML 에서 나오므로 검사하지 않은 내용이 나갔다(verify2 §1-B X5 재현: 9,900만).
# 조립(새문서·저장·되돌리기 재조립) 때 HTML 지문을 이 판 기록에 적고, 내보내기 때 다르면 거절한다. html
# 내보내기가 단독본으로 인라인하는 것은 제 손이라 지문을 따라 고친다(_산출지문갈기).
def _산출지문(key):
    try:
        with open(자료뿌리.산출물(str(key), "html"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:20]
    except OSError:
        return None


def _산출지문쓰나():
    return _플러그인표면() or bool(os.environ.get("문서지능_단일세션"))


def _파일지문(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:20]
    except OSError:
        return None


def _낸파일지우기(결과):
    """내보내기 결과 값이 가리키는 파일(값.파일 / 값.낸것[].파일)을 지운다 — 내는 도중 판이 바뀐 결과를 거둔다."""
    v = (결과 or {}).get("값") if isinstance(결과, dict) else None
    v = v if isinstance(v, dict) else {}
    for 파일 in [v.get("파일")] + [x.get("파일") for x in (v.get("낸것") or []) if isinstance(x, dict)]:
        if 파일:
            try:
                os.remove(파일)
            except OSError:
                pass


# 형식마다 이번 내보내기가 exports 에 쓰는 파일(곁 파일 포함) — hwpx 는 가는 길에 .md 를 덤으로, 끝에 .hwpx.meta.json 을 쓴다
_형식이쓰는것 = {"json": (".json",), "md": (".md",), "html": (".html",), "pdf": (".pdf",), "pptx": (".pptx",),
             "hwpx": (".hwpx", ".hwpx.meta.json", ".md")}


def _곁파일지우기(key, 형식):
    """내보내는 사이 문서가 바뀌어 거절할 때, 그 형식이 이번에 쓴 파일을 exports(플러그인 자리)에서 거둔다 — 거절
    결과는 값.파일을 싣지 않으므로 _낸파일지우기 만으로는 곁 파일(.md·.hwpx.meta.json)과 실패한 형식의 파일이 남았다."""
    if not _플러그인표면():
        return
    형식들 = (["html", "pdf", "hwpx", "pptx", "md", "json"] if 형식 in ("전부", "all", "모두") else [형식])
    낼곳 = _내보낼곳()
    for f in 형식들:
        for 꼬리 in _형식이쓰는것.get(f, ()):
            try:
                os.remove(os.path.join(낼곳, f"{key}{꼬리}"))
            except OSError:
                pass


def _산출지문적기(*keys):
    if not _산출지문쓰나():
        return
    for key in keys:
        if not key:
            continue
        h = _산출지문(key)
        if not h:
            continue
        try:
            _검사줄고치기(key, lambda 줄, h=h: 줄.__setitem__("산출", {"html": h}))
        except Exception as e:
            print(f"[검사기록] {key}/산출 적기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)


def _산출지문갈기(key, 옛, 새):
    if not (_산출지문쓰나() and 옛 and 새 and 옛 != 새):
        return

    def 고치기(줄):
        # 산출 지문과 함께 검사 칸마다의 HTML 지문도 따라 고친다(fixup5 ① — 칸이 잰 화면의 지문을 들고 있다)
        for x in 줄.values():
            if isinstance(x, dict) and x.get("html") == 옛:
                x["html"] = 새
    try:
        _검사줄고치기(key, 고치기)
    except Exception as e:
        print(f"[검사기록] {key}/산출 갈기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)


# 검사 원문 보관(fixup3, verify2 §1-B X1·X1b·X2) — 지어냈나는 원문과 견주는데, 원문을 빼고 다시 재면 '건너뜀'이
# FAIL 을 덮었고, 원문 자리에 초안 자신의 글을 넣으면 PASS 가 났다. 그래서 문서(key)마다 **처음 받은 원문**을
# 세션 뿌리의 workspace/검사자료.json 에 보관하고, 뒤 검사는 늘 그 원문으로 돈다(새 원문이 와도 보관 원문 우선).
# 같은 파일에 지어냄 의심 값과 '고친 곳'(의심이 사라진 값)도 적어 끝 보고의 확인할것에 싣는다(E). 첫 원문이 이미
# 초안 글이면 막을 길이 없다 — 로컬 도구의 한계(SKILL: 첫 새문서에 받은 자료를 그대로 싣는다).
def _v2출처되먹임길():
    return os.path.join(자료뿌리.작업뿌리(), "v2출처되먹임.json")


def _v2출처되먹임(doc, _v2, 하드, 소프트, 원문, 고침):
    """약한 경로 슬라이드 v2 초안의 출처 hard 를 빌드플랜(plan_id)마다 적어 두고, 바로 앞 회차와 같은 출처 hard(같은 수·같은
    일반 말)가 또 나오면 그 출처 칸을 비워(슬라이드v2.출처비우기) 다시 잰다 → (hard, soft). 비운 곳은 고침에 더한다.
    되시도 고리는 웹앱(app.html 초안등록되시도)이 쥐어 회차를 모른다 — 그래서 새문서 사이에 세션 파일로 잇는다."""
    서명 = lambda hs: sorted({m.group(1) for h in hs for m in [re.match(r"^장\.[\d·]+\.출처 (자료에 없는 숫자 \S+|'.*?' 의 '.+?'|자료가 출처를 밝히지 않았다)", h)] if m})
    지금 = 서명(하드)
    길, 열쇠 = _v2출처되먹임길(), str(doc.get("plan_id")).strip()
    os.makedirs(os.path.dirname(길), exist_ok=True)
    with 자료뿌리.빗장(길):
        try:
            기록 = json.load(open(길, encoding="utf-8"))
            기록 = 기록 if isinstance(기록, dict) else {}
        except (OSError, ValueError):
            기록 = {}
        앞 = [re.sub(r"^'.*?' 의 ", "", x) for x in 기록.get(열쇠) or []]
        같음 = bool(지금) and bool(set(re.sub(r"^'.*?' 의 ", "", x) for x in 지금) & set(앞))
        비웠다 = False
        if 같음:
            지운 = _v2.출처비우기(doc, _v2._자료글(doc, _자료글(원문) if 원문 else None))
            if 지운:
                비웠다 = True
                고침.extend(지운)
                하드, 소프트 = _v2.검사(doc, 원문=(_자료글(원문) if 원문 else None), 약한경로=True)
                소프트 = [f"(모양 정규화) 출처가 출처 검사(자료에 없는 이름·연도·일반 말)에 거듭 걸려 "
                        f"{', '.join(a for a, _ in 지운)} 을 비웠다"] + list(소프트)
                지금 = 서명(하드)
        # 비운 서명은 지우지 않고 남긴다 — 되시도는 비운 문서를 모델에 돌려주지 않고 새로 쓰게 해 모델이 같은 출처를 거의
        # 늘 다시 단다. 예전엔 비운 뒤 기록을 지워 hard → 비움 → hard → 비움으로 번갈아 돌았다(r4 적대 검토 규칙 §5 D1,
        # r4 EXAONE s6 초안 1·3·5 hard · 2·4 비움). 남겨 두면 다음 판부터 같은 서명은 첫 등장에 곧바로 비운다
        if 비웠다:
            기록[열쇠] = sorted(set(앞) | {re.sub(r"^'.*?' 의 ", "", x) for x in 지금})
        elif 하드 and 지금:
            기록[열쇠] = sorted(set(앞) | set(지금)) if 기록.get(열쇠 + "#비움") else 지금
        elif not 기록.get(열쇠 + "#비움"):
            기록.pop(열쇠, None)
        if 비웠다:
            기록[열쇠 + "#비움"] = True
        자료뿌리.원자json(길, 기록, ensure_ascii=False, indent=1)
    return 하드, 소프트


def _검사자료길():
    return os.path.join(자료뿌리.작업뿌리(), "검사자료.json")


def _검사자료읽기():
    try:
        d = json.load(open(_검사자료길(), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _검사자료고치기(key, 고치기):
    길 = _검사자료길()
    os.makedirs(os.path.dirname(길), exist_ok=True)
    with 자료뿌리.빗장(길):
        d = _검사자료읽기()
        줄 = d.get(str(key)) if isinstance(d.get(str(key)), dict) else {}
        고치기(줄)
        d[str(key)] = 줄
        자료뿌리.원자json(길, d, ensure_ascii=False, indent=1)


def _검사원문(key, 원문):
    """(쓸 원문 글, 알림|None) — 처음 받은 원문을 보관하고 그것을 돌려준다. 보관도 받은 것도 없으면 ("", None).
    플러그인 입구(MCP·CLI)에서만 보관한다 — 웹앱·라이브러리(verify_all 등)는 받은 원문을 그대로 쓴다."""
    글 = str(_자료글(원문) if 원문 else "")
    if not _플러그인표면():
        return 글, None
    try:
        보관 = str((_검사자료읽기().get(str(key)) or {}).get("원문") or "")
    except Exception:
        보관 = ""
    if 보관.strip():
        if 글.strip() and 글.strip() != 보관.strip():
            return 보관, ("지어냈나는 이 문서가 처음 받은 원문으로 쟀습니다 — 뒤에 준 원문은 검사에 쓰지 않습니다"
                        "(원문을 바꿔 걸림을 푸는 길을 막습니다). 사용자가 자료를 더 줬다면 사용자에게 확인받아 "
                        "강행이유(override_reason)로 내보내거나 새 파일 이름으로 다시 만드세요")
        return 보관, None
    if 글.strip():
        try:
            _검사자료고치기(key, lambda 줄: 줄.update({"원문": 글, "받은때": time.strftime("%Y-%m-%dT%H:%M:%S")}))
        except Exception as e:
            print(f"[검사자료] {key} 원문 보관 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
        return 글, None
    return "", None


def _의심적기(key, 의심들):
    """이번 지어냈나의 의심 값들을 적고, 앞선 의심 가운데 사라진 것(고친 곳)을 쌓는다(플러그인 입구만)."""
    if not _플러그인표면():
        return
    지금 = sorted({str(x) for x in 의심들 if str(x).strip()})

    def 고치기(줄):
        고친 = [x for x in (줄.get("의심") or []) if x not in 지금]
        쌓인 = 줄.get("고친곳") if isinstance(줄.get("고친곳"), list) else []
        for x in 고친:
            if x not in 쌓인:
                쌓인.append(x)
        줄["고친곳"] = [x for x in 쌓인 if x not in 지금][-40:]
        줄["의심"] = 지금
    try:
        _검사자료고치기(key, 고치기)
    except Exception as e:
        print(f"[검사자료] {key} 의심 적기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)


def _플러그인표면():
    """사람이 화면을 쥐지 않는 플러그인 입구(MCP·CLI)인가 — 내보내기 관문은 여기서만 선다.
    웹앱·로컬 편집기 서버(문서지능_웹앱)와 라이브러리로 부르는 도구(verify_all 등)는 아니다.
    이 표식은 환경변수라 밖에서 덮을 수 있다(verify2 X3) — 로컬 도구의 한계로 둔다(SKILL 에 적음)."""
    if os.environ.get("문서지능_웹앱"):
        return False
    v = (os.environ.get("문서지능_표면") or "").strip()
    if v:
        return v in ("mcp", "cli")
    main = str(getattr(sys.modules.get("__main__"), "__file__", "") or "").replace("\\", "/")
    return main.endswith("mcp/server.py")


def _내보낼곳():
    """내보내기가 파일을 쓰는 곳 — 플러그인(MCP·CLI)은 내보낸 것만 사는 build/exports(fixup4 ②, verify3 L2: 조판게이트가
    인쇄한 FAIL 판 PDF·조립 HTML 이 끝 보고가 가리키는 자리에 먼저 있었다). 웹앱·편집기 서버는 build/samples 그대로."""
    return 자료뿌리.내보내기뿌리() if _플러그인표면() else 자료뿌리.산출물뿌리()


def _관문문제(key, doc, 지금=None):
    """(문제 줄들, 알림 줄들) — 지금 판(문서 JSON·조립 HTML 지문)과 **같은 지문을 잰** 검사 기록만 인정한다(fixup5 ①).
    `지금` 은 내보내기가 시작 때 뜬 지문(없으면 여기서 뜬다)."""
    줄 = _검사기록읽기().get(str(key))
    줄 = 줄 if isinstance(줄, dict) else {}
    문제, 알림 = [], []
    지금 = 지금 or {"판": _판해시(doc), "html": _산출지문(key) if _산출지문쓰나() else None}
    if not 줄 or not any(_같은지문(줄.get(칸), 지금) for 칸 in ("문체", "조판", "지어냄")):
        if any(isinstance(줄.get(칸), dict) and 줄[칸].get("판") == 지금["판"] for 칸 in ("문체", "조판", "지어냄")):
            문제.append("산출 HTML 이 검사한 화면과 다릅니다(조립 뒤에 HTML 이 바뀌었습니다) — HTML 을 직접 고치지 말고 "
                      "문서 JSON 을 저장(save, 검사 true)으로 고쳐 다시 조립하세요")
        else:
            문제.append("이 판(지금 내용)의 검사 기록이 없습니다" + (" — 검사 뒤에 내용이 바뀌었습니다" if 줄 else ""))
        return 문제, 알림
    남판 = "{} 기록이 이 판 것이 아닙니다(잰 뒤에 내용이 바뀌었거나 재는 도중 저장됐습니다) — 이 판에 다시 재세요"
    for 칸, 이름 in (("문체", "문체검사"), ("조판", "조판게이트")):
        x = 줄.get(칸)
        if not isinstance(x, dict):
            문제.append(f"{이름} 기록이 없습니다")
        elif not _같은지문(x, 지금):
            문제.append(남판.format(이름))
        elif not x.get("ok"):
            문제.append(f"{이름} FAIL(hard)")
    x = 줄.get("지어냄")
    if not isinstance(x, dict):
        문제.append("지어냈나 기록이 없습니다")
    elif not _같은지문(x, 지금):
        문제.append(남판.format("지어냈나"))
    elif x.get("건너뜀"):
        # 원문 없이 만든 문서는 내보내지 않는다(fixup4 주관 ③, verify3 L1·L1b: 새 key 를 원문 없이 만들면 지어낸 값이
        # 확인할것 한 줄만 남기고 PDF 로 나갔다). 자료가 따로 없는 요청이면 요청 글이 곧 자료다.
        문제.append(f"지어냈나를 건너뛰었습니다({x['건너뜀']}) — 자료 원문을 원문(source_text)에 실어 새문서·저장"
                  "(검사 true)으로 다시 재세요. 따로 준 자료가 없는 요청이면 사용자 요청 글을 원문으로 넘기세요")
    elif not x.get("ok"):
        문제.append("지어냈나 FAIL(자료에 없는 수치·이름)")
    x = 줄.get("확장")
    if isinstance(x, dict) and _같은지문(x, 지금) and not x.get("ok"):     # 확장은 지어냄과 한 번에 적힌다(같은 지문)
        문제.append("지어냈나확장 FAIL(월표현·출처·메타 칸 등)")
    x = 줄.get("산출")
    if isinstance(x, dict) and x.get("html"):
        지금h = _산출지문(key)
        if 지금h and 지금h != x["html"]:
            문제.append("산출 HTML 이 조립 뒤에 바뀌었습니다(검사한 내용과 다른 화면) — HTML 을 직접 고치지 말고 "
                      "문서 JSON 을 저장(save, 검사 true)으로 고쳐 다시 조립하세요")
    return 문제, 알림


def _내보내기관문(key, doc, 강행이유="", 지금=None):
    """(막힘 응답|None, 알림 줄들). 지금 판의 검사 기록을 본다. 로컬 편집기 서버(사람이 화면을 쥔 단일 세션)는
    막지 않고 검사 상태를 알림으로만 싣는다(verify2 X4 — 사람 조작이라 막지 않는다). `지금` 은 내보내기 시작 때 뜬
    지문(fixup5 ①)."""
    if not _플러그인표면():
        if os.environ.get("문서지능_단일세션"):
            try:
                문제, _ = _관문문제(key, doc)
            except Exception:
                문제 = []
            if 문제:
                return None, ["검사를 통과하지 못한 항목이 있습니다: " + " · ".join(문제)
                              + ". 편집 화면에서 직접 내보내는 것이라 막지는 않습니다."]
        return None, []
    문제, 알림 = _관문문제(key, doc, 지금)
    if not 문제:
        return None, 알림
    이유 = str(강행이유 or "").strip()
    if 이유:
        자료뿌리.규칙적기("내보내기강행", {"건수": 1})
        return None, 알림 + [f"검사 관문을 사람 확인으로 넘겼습니다(이유: {이유[:120]}) — 걸린 것: " + " · ".join(문제)]
    return ({"ok": False, "필요한것": "검사 통과", "값": {"걸림": 문제},
             "로그": "내보내기 관문 — 지금 판이 검사를 통과한 기록이 없어 내보내지 않습니다: " + " · ".join(문제)
                    + "\n  고친 뒤 새문서(new, 검사 true·원문) 또는 저장(save, 검사 true·원문)으로 다시 재거나, "
                      "문체검사(stylelint key)·조판게이트(gate key)·지어냈나(fabcheck key·원문)를 이 판에 돌리세요."
                    + "\n  사람이 확인하고 이대로 내보내기로 했으면 강행이유(override_reason)에 그 이유를 적어 다시 "
                      "부르세요(에이전트가 스스로 적지 않습니다)."},
            알림)


@등록("내보내기", ["key", "형식", "강행이유"], 읽기=False,
    설명="문서를 json·md·html·pdf·hwpx·pptx 로 낸다. hwpx 는 정본 실측 수치를 그대로 "
        "먹이고, pptx 는 발표 슬라이드 전용(편집 가능한 네이티브 요소)이다. 플러그인에서는 지금 판이 "
        "문체검사·조판게이트·지어냈나(원문 대조)를 통과한 기록이 있어야 낸다(원문 없이 만든 문서는 거절 — 자료가 "
        "없으면 요청 글을 원문으로) — 파일은 내보낸 것만 사는 build/exports 에 쓰고 값.파일에 절대 경로. 사람이 "
        "확인하고 그대로 낼 때만 강행이유(이유 필수)를 준다",
    en="export")
def 내보내기(key, 형식="hwpx", 강행이유="", _관문지남=False):
    if not _관문지남 and not _그림경고중.get():
        # 그림 한 줄 경고('26-09-30 주관 판정 ①) — 바깥 호출에서 한 번만 붙인다(막지 않는다). 웹앱은 확인할것 칸이 없어
        # app.html 내보내기 화면이 이 '그림경고'를 싣는다. 플러그인은 로그 끝에도 적는다.
        _표 = _그림경고중.set(True)
        try:
            결과 = 내보내기(key, 형식, 강행이유, _관문지남)
        finally:
            _그림경고중.reset(_표)
        if isinstance(결과, dict) and 결과.get("ok"):
            try:
                _경 = _그림내보내기경고(key, 문서(key).get("값"))
            except Exception as _e:
                _경 = []
                print(f"[그림] 내보내기 경고 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
            if _경:
                결과 = dict(결과, 그림경고=_경)
                결과["로그"] = ((결과.get("로그") or "") + "\n▸ " + "\n▸ ".join(_경)).lstrip("\n")
        return 결과
    r = 문서(key)
    if not r["ok"]:
        return r
    doc = r["값"]
    _관문알림 = []
    if not _관문지남:
        # 플러그인은 **내보내기 시작 때의 지문**으로 관문을 보고, 다 낸 뒤 지문이 그대로인지 다시 본다(fixup5 ① — 관문을
        # 지난 뒤 내는 도중 저장이 끼면 검사하지 않은 판이 파일로 나갈 수 있다). 바뀌었으면 낸 파일을 지우고 거절한다.
        _지금 = _잰판(key, doc) if _플러그인표면() else None
        막힘, _관문알림 = _내보내기관문(key, doc, 강행이유, _지금)
        if 막힘:
            return 막힘
        if _지금 is not None:
            결과 = 내보내기(key, 형식, _관문지남=True)
            if isinstance(결과, dict) and _잰판(key) != _지금:
                # 성공이든 실패든 — 그 형식이 이번에 쓴 파일과 곁 파일(.md·.hwpx.meta.json)까지 거둔다(fixup6, verify5 N2:
                # 거절된 hwpx 가 검사받지 않은 값이 든 .md 를 남겼고, 인쇄 도중 저장이 낀 pdf 는 옛 인쇄를 남겼다)
                _낸파일지우기(결과)
                _곁파일지우기(key, 형식)
                결과 = {"ok": False, "필요한것": "검사 통과",
                      "로그": "내보내는 동안 다른 저장(편집기 자동 저장 포함)이 끼어 그 사이 문서가 바뀌었습니다 — 검사하지 "
                             "않은 판이 섞였을 수 있어 이번에 낸 파일을 지웠습니다. 바뀐 판을 다시 재고(save 검사 true 또는 "
                             "stylelint·gate·fabcheck) 내보내세요"}
            if _관문알림 and isinstance(결과, dict):
                결과 = dict(결과)
                결과["로그"] = ((결과.get("로그") or ("내보냈습니다" if 결과.get("ok") else "")) + "\n▸ "
                              + "\n▸ ".join(_관문알림)).lstrip("\n")
            return 결과
    if _관문알림:
        # 알림은 결과 로그 끝에 붙인다 — 한 번만(전부의 형식별 내부 호출은 _관문지남=True 로 온다)
        결과 = 내보내기(key, 형식, _관문지남=True)
        if isinstance(결과, dict):
            결과 = dict(결과)
            결과["로그"] = ((결과.get("로그") or ("내보냈습니다" if 결과.get("ok") else "")) + "\n▸ "
                          + "\n▸ ".join(_관문알림)).lstrip("\n")
        return 결과
    # 웹앱처럼 **모든 형식을 한 번에** 낸다(사장님 지침 '26-08-25) — 사용자가 전부 받아 골라
    # 쓰게. 슬라이드는 HTML·PDF·PPTX, 그 외 세로 A4 장르는 HTML·PDF·HWPX. 각 형식은 아래
    # 형식별 경로를 그대로 재사용한다(전환이지 재생성 아님).
    if 형식 in ("전부", "all", "모두"):
        # 이 문서에 맞는 **모든 형식**: 편집형(HWPX/PPTX)·인쇄(PDF)·웹(HTML)·본문(MD)·원천(JSON).
        # 슬라이드는 세로 A4 가 아니라 HWPX 대신 PPTX. 순서는 주 산출물 먼저, md·json 은 끝에.
        형식들 = (["html", "pdf", "pptx", "md", "json"] if doc.get("genre") == "slides"
                else ["html", "pdf", "hwpx", "md", "json"])
        낸것, 실패 = [], []

        # 세션 열쇠는 **스레드 지역**이라 새 스레드는 물려받지 않는다(build/자료뿌리.py
        # 머리말 — "새 스레드는 값을 물려받지 않는다"). 여기서 놓치면 pdf·hwpx 스레드가
        # 세션 자료뿌리를 못 보고 **기본 뿌리**를 읽고 쓴다(HTTP 공유 MCP·웹앱처럼 열쇠가
        # 스레드지역에만 있고 환경변수가 없는 경로에서 특히 그렇다) — _서버채움 이 여는
        # 자리와 같은 이유로 열쇠를 붙잡아 세션갈기 로 다시 끼운다.
        _열쇠 = 자료뿌리.세션열쇠()

        def _한형식(_f):
            with 자료뿌리.세션갈기(_열쇠):
                rr = 내보내기(key, _f, _관문지남=True)     # 관문은 '전부' 입구에서 한 번 지났다
            if isinstance(rr, dict) and rr.get("ok"):
                낸것.append({"형식": _f, **(rr.get("값") or {})})
            else:
                실패.append({"형식": _f, "로그": (rr or {}).get("로그", "")})

        # html 은 먼저 순서대로 만든다 — pdf·hwpx(또는 pptx) 둘 다 **완성된 html**을
        # 입력으로 읽는다(전환이지 재생성이 아니다, 위 주석). 그 둘은 서로 입력만 같이
        # 읽고 서로에게 안 쓰므로 스레드로 동시에 돌린다('26-09-26 벤치마크 진단, 항목
        # 6b) — 각자 헤들리스 크롬을 **독립 임시 프로필**로 띄우고 디버그 포트도
        # 0(자동배정)이라(build/화면읽기.py·build/topptx.py, --remote-debugging-port=0)
        # 인쇄(크롬찾기.인쇄, CDP 안 씀)와 겹쳐도 서로의 포트를 잡지 않는다(코드 확인,
        # 크롬 디버그 포트 충돌은 예전에 고정 9333 을 쓰던 시절의 얘기다).
        _한형식("html")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as _일꾼:
            list(_일꾼.map(_한형식, 형식들[1:3]))    # pdf · hwpx(또는 pptx)
        for _f in 형식들[3:]:                        # md · json — 가볍다, 그대로 순서대로
            _한형식(_f)
        return {"ok": bool(낸것), "값": {"낸것": 낸것, "실패": 실패},
                "로그": f"{len(낸것)}개 형식 생성" + (f" · {len(실패)}개 실패" if 실패 else "")
                + "".join(f"\n  ✓ {x['형식']}: {x.get('경로', '')} ({x.get('크기', '?')}B)" for x in 낸것)
                + "".join(f"\n  ✗ {x['형식']}: {x['로그']}" for x in 실패)}
    # 발표 슬라이드는 가로(16:9) 화면 산출물이라 HWPX(세로 A4 전제)로 내보낼 수 없다 —
    # 화면읽기가 지면을 폭≈210mm로 재 가로 슬라이드는 요소 0개(빈 hwpx)가 된다. 명시 거부한다.
    if 형식 == "hwpx" and doc.get("genre") == "slides":
        # 미전이=True 는 **의도된 거부**라는 구조 표식이다 — 검사(verify_all HWPX재현)가
        # 이 표식으로 '못 뽑은 실패' 와 '안 뽑는 게 맞음' 을 가른다(로그 문자열 매칭 금지).
        return {"ok": False, "미전이": True,
                "로그": "발표 슬라이드는 HWPX로 내보낼 수 없습니다 — 가로(16:9) 화면 "
                "산출물이라 세로 A4 규격의 HWPX와 맞지 않습니다. PDF나 HTML로 내보내세요."}
    # 플러그인은 내보낸 것만 사는 자리(build/exports)에 쓰고, 조립 HTML(build/samples — 작업 자리)은 **읽기만** 한다
    # (fixup4 주관 ②). 웹앱·편집기 서버는 낼곳 = build/samples 라 예전과 글자 하나 다르지 않다.
    _플 = _플러그인표면()
    낼곳 = _내보낼곳()
    os.makedirs(낼곳, exist_ok=True)
    _작업html = 자료뿌리.산출물(str(key), "html")
    _접두 = "/build/exports/" if _플 else "/build/samples/"

    def _값(p, **더):
        v = {"경로": _접두 + os.path.basename(p), **더}
        if _플:
            v["파일"] = os.path.abspath(p)      # 끝 보고가 그대로 적는 절대 경로
        return v

    if 형식 == "json":
        p = os.path.join(낼곳, f"{key}.json")
        # 못 실은 그림 스펙·올린 파일 이름은 걷은 사본으로 낸다(fixup3 N8) — 등록부의 문서는 그대로
        try:
            _낼doc = _그림json사본(doc, key)
        except Exception as _e:
            print(f"[그림] json 사본 오류 — 그림 키를 모두 뺀다: {type(_e).__name__}: {_e}", file=sys.stderr)
            _낼doc = json.loads(json.dumps(doc, ensure_ascii=False))
            _그림스펙걷기(_낼doc, lambda spec, 어디: None)
        자료뿌리.원자json(p, _낼doc, indent=2)      # 재조립 중 내려받기 = 반쪽 파일(E-5)
        return {"ok": True, "값": _값(p)}

    if 형식 == "html" and _플:
        if not os.path.exists(_작업html):
            return {"ok": False, "로그": "HTML 이 없습니다 — 조립을 먼저 돌리세요"}
        p = os.path.join(낼곳, f"{key}.html")
        원 = open(_작업html, encoding="utf-8").read()
        # 작업 HTML 은 그대로(X5 지문 불변). 이미 인라인된 옛 판이어도 밖으로 나가는 흔적·문서 JSON 섬은 걷는다(③)
        자료뿌리.원자쓰기(p, _그림흔적걷기(원) if "data-inlined" in 원 else _단독html(원))
        return {"ok": True, "값": _값(p)}

    if 형식 == "html":
        p = os.path.join(낼곳, f"{key}.html")
        if not os.path.exists(p):
            return {"ok": False, "로그": "HTML 이 없습니다 — 조립을 먼저 돌리세요"}
        # 내려받아 단독으로 열리는 자기완결본으로 만든다(CSS/JS 인라인 + 기본 폰트 data: 임베드).
        # ('26-09-30 주관 판정 ③) 단독본은 문서 JSON 섬(#fr-doc)을 뺀다 — 그래서 작업 HTML 을 그 자리에서 바꾸지 않고
        # **따로** 쓴다({key}.export.html). 전에는 제자리에서 바꿔, 편집기 다시 굽기(render_editor_any 가 이 HTML 의 섬을
        # 편집기에 옮긴다)·그림 살피기가 읽을 것을 잃었다. 내려받는 이름은 값.이름({key}.html, app.html 이 a.download 로 쓴다).
        # tohwpx·크롬 PDF 는 작업 HTML 을 읽는다(무영향).
        낸 = os.path.join(낼곳, f"{key}.export.html")
        try:
            원 = open(p, encoding="utf-8").read()
            자료뿌리.원자쓰기(낸, _그림흔적걷기(원) if "data-inlined" in 원 else _단독html(원))
        except Exception as e:
            print(f"[html단독] {key}: {type(e).__name__}: {e}", file=sys.stderr)
            return {"ok": False, "로그": "내려받을 HTML 을 만들지 못했습니다"}
        return {"ok": True, "값": {"경로": f"/build/samples/{key}.export.html", "이름": f"{key}.html"}}

    if 형식 == "pdf":
        # 없으면 **그 자리에서 뽑는다.** 게이트가 만들어 주기를 기다리게 하면
        # 사용자는 "왜 PDF 만 안 되지" 하고 막힌다(2026-08-05 화면 시험에서 걸림).
        htm = _작업html
        if not os.path.exists(htm):
            return {"ok": False, "로그": "HTML 이 없습니다 — 조립을 먼저 돌리세요"}
        p = os.path.join(낼곳, f"{key}.pdf")
        if _플:
            # 플러그인 내보내기 pdf 는 **늘 지금 HTML 로** 낸다(fixup4 주관 ②, verify3 §7: 'PDF 가 HTML 보다 새로우면 그대로'
            # 길로 조판게이트가 인쇄한 파일이 내보낸 파일이 됐다). 다시 쓰는 것은 조판게이트가 이 판·이 화면(HTML 지문)을
            # 인쇄해 통과로 적은 PDF 뿐이다(관문 문제가 하나라도 있으면 새로 인쇄).
            try:
                os.remove(p)
            except OSError:
                pass
            검pdf = os.path.join(자료뿌리.검사뿌리(), f"{key}.pdf")
            try:
                # 같은 판 = 조판 칸이 지금 JSON·HTML 지문을 잰 통과 기록이고, 검사 PDF 가 **그 기록이 인쇄한 파일**(지문)일
                # 때만(fixup5 ① — 다른 판의 게이트가 같은 이름으로 다시 인쇄했거나 바꿔치기한 파일을 베끼지 않는다)
                조 = (_검사기록읽기().get(str(key)) or {}).get("조판") or {}
                같은판 = (os.path.exists(검pdf) and 조.get("ok") and 조.get("html") and 조.get("pdf")
                        and _같은지문(조, _잰판(key, doc)) and 조.get("pdf") == _파일지문(검pdf)
                        and not _관문문제(key, doc)[0])
            except Exception:
                같은판 = False
            if 같은판:
                import shutil as _sh
                _sh.copyfile(검pdf, p)
                return {"ok": True, "값": _값(p, 크기=os.path.getsize(p), 다시씀="검사 통과한 같은 판의 인쇄")}
        elif os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(htm):
            return {"ok": True, "값": {"경로": f"/build/samples/{key}.pdf"}}
        # 크롬 찾는 눈은 build/크롬찾기.py 하나뿐이다(WP-S8) — 여기 서버 코드에서
        # 못 찾았다고 프로세스를 죽이면(SystemExit) 그 요청 하나 때문에 서버 전체가
        # 내려간다. 그래서 죽지 않는 `찾기()`를 쓰고 실패는 평소처럼 ok:False 로 만든다.
        씀 = 자료뿌리.모듈("크롬찾기").찾기()
        if not 씀:
            return {"ok": False, "로그": "크롬을 찾지 못해 PDF 를 뽑을 수 없습니다"}
        # 헤들리스 크롬 실행·회수는 크롬찾기.인쇄() 한 손이 맡는다(WP-S8 짝). 격리 프로필로
        # 사용자의 실행 중 Chrome 과의 프로필 락을 피하고, PDF 꼬리 %%EOF 가 보이면 kill 로
        # 회수한다 — 데스크톱에서 '다 쓰고 행'을 180초 기다리지 않고 수 초에 끝낸다.
        자료뿌리.모듈("크롬찾기").인쇄(씀, "file://" + htm, p)
        # 온전함: 이번에 새로 쓰였고(캐시 검사와 같은 신선도 잣대) 꼬리 %%EOF 가 있어야 한다.
        # %%EOF 는 크롬이 마지막에 쓰는 표식이라 부분 쓰기를 결정적으로 거른다(poppler 는
        # 깨진 xref 를 수선해 읽어 주므로 pdfinfo 하나로는 반쪽을 놓칠 수 있다).
        if not os.path.exists(p):
            return {"ok": False, "로그": "PDF 를 뽑지 못했습니다"}
        if os.path.getmtime(p) < os.path.getmtime(htm):
            # 인쇄는 됐는데 그 사이 조립 HTML 이 새로 써졌다(저장이 끼었다) — 옛 판 인쇄를 남기지 않는다(fixup6, verify5 N2)
            try:
                os.remove(p)
            except OSError:
                pass
            return {"ok": False, "로그": "PDF를 만드는 사이에 문서가 새로 저장되어 이번 PDF는 지웠습니다. "
                                        "다시 내보내 주세요."}
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - 1024))
            if b"%%EOF" not in f.read():
                return {"ok": False, "로그": "PDF 가 온전하지 않습니다 (크롬 렌더 실패)"}
        # 원본 지문을 PDF 메타에 심는다 — verify_all 의 PDF 낡음 검사가 "이 pdf 가 어느
        # html 에서 나왔나"를 대조할 근거다(hwpx zip 코멘트와 대칭, build/pdf낡음.py).
        # 스탬프는 부가 정보라 실패해도 내보내기는 세운다(try/except 로 삼킨다).
        try:
            자료뿌리.모듈("pdf낡음").찍기(p, htm)
        except Exception:
            pass
        return {"ok": True, "값": _값(p, 크기=os.path.getsize(p))}

    if 형식 == "pptx":
        # PPTX 전환은 16:9 발표 슬라이드 전용이다 — 세로 A4 장르는 옮길 슬라이드 지면이
        # 없다. hwpx 가 slides 를 거부하는 것(위 1714줄)과 **대칭**으로 명시 거부하고,
        # 미전이=True 로 검사(verify_all)가 '못 뽑은 실패'와 '안 뽑는 게 맞음'을 가른다.
        if doc.get("genre") != "slides":
            return {"ok": False, "미전이": True,
                    "로그": "PPTX 로는 발표 슬라이드만 내보낼 수 있습니다 — 세로 A4 규격 "
                    "문서는 HWPX나 PDF로 내보내세요."}
        htm = _작업html
        if not os.path.exists(htm):
            return {"ok": False, "로그": "HTML 이 없습니다 — 조립을 먼저 돌리세요"}
        낼 = os.path.join(낼곳, f"{key}.pptx")
        # tohwpx 와 같은 사상 — 완성 규격을 다른 그릇에 그대로 옮긴다(전환이지 생성 아님).
        # **topptx 는 PIL·python-pptx 를 모듈 최상위에서 import** 하므로, MCP 서버(mcp/.venv)
        # 에서 `자료뿌리.모듈("topptx")` 로 부르면 import 단계에서 ModuleNotFoundError(PIL/pptx)
        # 로 죽는다 — 이 의존은 build/.hwpxenv 에만 있다(코덱스·커서·클로드코드 교차 테스트
        # 3사 공통 실측, 2026-08-24). 그래서 tohwpx 가 _hwpx_write.py 를 .hwpxenv 로 subprocess
        # 위임하듯, topptx 의 CLI(python topptx.py <html> <out>)도 .hwpxenv 로 돌린다.
        _py = os.path.join(ROOT, "build", ".hwpxenv", "bin", "python")
        if not os.path.exists(_py):
            return {"ok": False, "로그": "PPTX 라이브러리가 없습니다 — build/.hwpxenv 를 만들고 "
                    "python-pptx·Pillow 를 설치하세요(bin/bootstrap.sh 가 자동으로 합니다)."}
        try:
            r = subprocess.run([_py, os.path.join(ROOT, "build", "topptx.py"), htm, 낼],
                               capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return {"ok": False, "로그": "PPTX 전환이 너무 오래 걸립니다"}
        if r.returncode != 0 or not os.path.exists(낼):
            줄 = (r.stdout or "").strip().splitlines() or (r.stderr or "").strip().splitlines()
            return {"ok": False, "로그": "PPTX 전환 실패 — " + (줄[-1] if 줄 else "알 수 없음")}
        말 = None       # topptx __main__ 은 "OK {json}" 를 stdout 에 낸다(되읽기 요약)
        _out = (r.stdout or "").strip()
        if _out.startswith("OK "):
            try:
                말 = json.loads(_out[3:])
            except Exception:
                말 = None
        return {"ok": True, "값": _값(낼, 크기=os.path.getsize(낼), 되읽기=말)}

    # md 는 hwpx 가는 길에 덤으로 만든다 — 그 덤이 죽었다고 hwpx 까지 막지는 않는다
    # ('26-09-27 적대검토: 풀버전 절.표 리스트에서 tomd 가 죽자 md·hwpx·전부가 한꺼번에 멈췄다).
    try:
        # 못 얻은 그림은 캡션째 빼고('26-09-30), 실린 그림은 링크(플러그인 상대 경로 · 웹앱 data:)로 싣는다(P3)
        _md사본, _md링크 = _md그림(doc, key, 낼곳)
        md = 자료뿌리.모듈("tomd").마크다운(_md사본, 그림링크=_md링크)
        mdp = os.path.join(낼곳, f"{key}.md")
        자료뿌리.원자쓰기(mdp, md)                   # E-5
    except Exception as e:
        if 형식 == "md":
            return {"ok": False, "로그": f"마크다운 변환 실패 — {type(e).__name__}: {e}"}
        print(f"[md] {key}: 마크다운 변환 실패(hwpx 는 계속) — {type(e).__name__}: {e}", file=sys.stderr)
    if 형식 == "md":
        return {"ok": True, "값": _값(os.path.join(낼곳, f"{key}.md"))}

    if 형식 != "hwpx":
        return {"ok": False, "로그": f"모르는 형식: {형식} (json·md·html·pdf·hwpx·pptx)"}

    # **kordoc generate 를 쓰지 않는다.** 그것은 자기 프리셋으로 문서를 다시 만든다 —
    # 우리가 실물 사례 재서 세운 규칙이 남의 규칙으로 덮인다(2026-08-05 사장님 지적).
    # 여기서 하는 것은 생성이 아니라 **전환**이다: 완성된 규격을 HWPX 그릇에 그대로 옮긴다.
    tohwpx = 자료뿌리.모듈("tohwpx")
    낼 = os.path.join(낼곳, f"{key}.hwpx")
    htm = _작업html
    # hwpx 는 캐시하지 않는다('26-09-26 적대검토) — html 지문만 보는 캐시는 변환기 코드가
    # 바뀌어도(배포·수정) 낡은 hwpx 를 돌려주고, 배포본에서는 스탬프가 달라 맞지도 않았다.
    # 절감은 같은 html 을 두 번 내보낼 때 2초 남짓뿐이라 틀린 파일 위험을 질 까닭이 없다.
    # **doc 을 주지 않고 HTML 경로를 우리가 정해 넘긴다.** doc(dict)을 주면 tohwpx 가
    # 스스로 `import 자료뿌리` 로 산출물 자리를 찾는데, 그 import 는 이 프로세스가
    # 이미 들고 있는 자료뿌리 객체가 아니라 **두 번째 복사본**을 올린다(api.py 는
    # importlib 로 파일에서 바로 불러 sys.modules 에 안 걸어 둔다). 세션 열쇠는
    # 스레드 지역값이라 그 복사본에는 없다 — 그래서 세션 안에서 hwpx 를 내보내면
    # 기본 뿌리를 보고 "HTML 이 없습니다" 로 끝났다(자료뿌리.py 머리말의 '딸린 함정').
    # 2026-08-07 실측: 세션 A 에서 동기 `/api/export`·작업 경로 **둘 다** 같은 실패였고
    # (S4 이전부터 그랬다), 경로를 넘기게 고치자 둘 다 됐다. `낼곳` 은 위에서
    # 자료뿌리.산출물뿌리() 로 잡은 **이 세션의** 자리다.
    ok, 말 = tohwpx.만들기(htm, 낼)
    if not ok:
        # 완전성 가드(WP-H2)가 세운 것이면 **몇 건인지만** 세션 기록에 남긴다 —
        # 구멍 내용에는 문서의 서식값·경로가 붙어 있어 그대로는 못 남긴다.
        import re as _re
        m = _re.match(r"카탈로그 밖의 서식 (\d+)건", 말 or "")
        if m:
            자료뿌리.규칙적기("가드", {"카탈로그밖서식": int(m.group(1))})
            # 상세(서식값·변환식·build/ 경로)는 서버 자리에만 남긴다 — stdout 은
            # MCP stdio 와 겹치므로 stderr 로. 클라 '로그'는 app.html 토스트로
            # 그대로 나가는 자리라(알림3) 축약 문안만 보낸다.
            print(f"[가드] {key}: {말}", file=sys.stderr)
            # '어느 자리의 어떤 서식'만은 사용자에게 알린다('26-09-28 — 8차 벤치 에이전트 넷이
            # "무엇을 고쳐야 할지 알 수 없다"고 짚음). 서식 **값**과 build/ 경로는 여전히 뺀다 —
            # 문서 안 자리(data-path)와 서식 이름(위여백mm·어절분리 …)만 싣는다.
            자리들 = []
            for 항목 in 말.split("옮기지 않았습니다: ", 1)[-1].split(" → ")[0].split(" · ")[:3]:
                mm = _re.match(r"\s*([^·\s]+)·([^=\s]+)=.*?(?: / ([^@]+?))?\s*$", 항목)
                if mm:
                    자리 = (mm.group(3) or "").split(",")[0].strip() or mm.group(1)
                    자리들.append(f"{자리}의 {mm.group(2)}")
            return {"ok": False,
                    "로그": f"표준 양식 밖의 서식 {m.group(1)}건이 있어 "
                          f"HWPX 로 옮기지 못했습니다"
                          + (f" — 자리: {', '.join(자리들)}. 편집기에서 그 개체의 서식을 기본으로 "
                             f"되돌리면 내보낼 수 있습니다" if 자리들 else "")}
        return {"ok": False, "로그": 말}
    # 환경 메타 사이드카(방법론 전환 3단계) — 글꼴·버전·크롬이 변환 품질을 가르므로
    # "이 hwpx 가 어떤 환경에서 나왔나"를 산출물 곁에 남긴다. 메타가 내보내기를
    # 죽이면 안 되지만 조용히 삼키지도 않는다(규칙 3) — stderr 로 세어 둔다.
    try:
        메타 = 자료뿌리.모듈("내보내기메타").모으기()
        메타.update({"문서": key, "형식": "hwpx",
                   "크기": os.path.getsize(낼), "결과말": 말})
        with open(낼 + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump(메타, fh, ensure_ascii=False, indent=1)
    except Exception as e:                                    # noqa: BLE001
        print(f"[내보내기메타] {key}: 기록 실패 — {e}", file=sys.stderr)
    return {"ok": True, "값": _값(낼, 크기=os.path.getsize(낼)), "로그": 말}


# ── 이어 고치기 입구 (구현계획.md §3 WP-S7 · 출시계획 1-4) ────────────────
# 세션은 문서를 돌려주고 끝난다 — 유예가 없다(출시계획 1-1). 그래서 고치려면
# **낸 파일을 다시 넣는** 문이 있어야 하고, 그 파일이 HTML 인 이유는 조립기 다섯이
# 전부 `<script type="application/json" id="fr-doc">` 로 3층 JSON 을 통째로 심어
# 왕복이 무손실이기 때문이다(HWPX 재입력 길은 만들지 않는다 — 출시계획 1-4).
#
# **넣는 HTML 은 바깥에서 온 글이다** — 우리가 낸 것과 같아 보여도 손을 탔을 수
# 있다. 여기서 꺼낸 JSON 을 **새문서를 지나** 등록부에 넣는 것이 방어의 전부다:
# 새문서가 이름 규칙·장르 실재를 검사하고, 조립기가 본문을 _허용마크업(assemble.py)
# 으로, 속성 자리를 build/속성값.py 계약으로 잠근다(2026-08-07 에 닫은 XSS 두 부류).
# 여기서 문자열을 따로 씻지 **않는** 까닭: 씻는 자리가 둘이 되면 목록이 둘로 갈리고
# (규칙 2), 이 자리의 계약("이미 HTML 인 글")을 모른 채 &amp; 를 다시 잠그면
# F&B 가 화면에 F&amp;B 로 인쇄된다 — 새니타이저 머리말이 적어 둔 그 함정이다.

# 조립기 다섯이 심는 모양 그대로: type="application/json" 과 id="fr-doc" 둘 다 본다.
# id 만 보면 손으로 지어낸 `<script id="fr-doc">`(실행 스크립트)도 "우리 것"으로
# 받아들이게 된다 — 우리가 낸 파일의 지문을 최대한 그대로 요구한다.
_fr독꼴 = re.compile(
    r'<script\b[^>]*\btype\s*=\s*["\']application/json["\'][^>]*'
    r'\bid\s*=\s*["\']fr-doc["\'][^>]*>(.*?)</script\s*>', re.S | re.I)


def _fr문서뽑기(글):
    """낸 HTML 에서 fr-doc JSON 섬을 꺼낸다 → (doc, 왜못꺼냈나).

    거부는 소리 내서 한다(규칙 3) — 못 꺼낸 이유마다 다른 사람말을 돌려준다.
    검사(verify_all.check_resume_entry)가 이 함수를 직접 불러 다섯 장르 산출물
    전수로 왕복을 재므로, 꺼내는 눈은 여기 하나뿐이어야 한다.
    """
    if not isinstance(글, str):
        return None, f"html 이 글(str)이 아니라 {type(글).__name__} 입니다"
    if not 글.strip():
        return None, "빈 HTML 입니다 — 내려받은 보고서 HTML 파일의 내용을 주세요"
    if len(글) > 20 * 1024 * 1024:
        # 올리기(base64 40MB≈원본 30MB)와 같은 자리의 상한 — 무한정 받으면 정규식
        # 한 번에 서버가 몇 초씩 묶인다. 우리가 낸 HTML 은 커야 수백 KB 다.
        return None, "HTML 이 너무 큽니다(20MB 어름까지) — 우리가 낸 파일이 맞는지 봐 주세요"
    조각들 = _fr독꼴.findall(글)
    if not 조각들:
        # 단독 HTML(내려받은 한 파일)은 문서 원본 섬을 싣지 않는다('26-09-30 주관 판정 ③) — 이어 고칠 입구는 편집기 파일이다
        return None, ('fr-doc 을 찾지 못했습니다 — 내려받은 단독 HTML 에는 문서 원본이 없어 이어서 고칠 수 없습니다. '
                      '편집기 파일(editor-문서이름.html)을 넣거나 문서함에서 그 문서를 골라 편집기로 여세요. '
                      '다른 문서로 시작하려면 서식분석·새문서 쪽입니다')
    if len(조각들) > 1:
        # 우리 산출물엔 정확히 하나다(2026-08-08 실측: 사례 전부 1개). 둘 이상이면
        # 손을 탄 파일이다 — 어느 것이 진짜인지 여기서 고르면 고른 쪽이 뚫린다.
        return None, (f"fr-doc 이 {len(조각들)}개 있습니다 — 우리가 낸 HTML 에는 정확히 "
                      f"하나입니다. 손대지 않은 원본 파일로 다시 넣어 주세요")
    try:
        doc = json.loads(조각들[0])          # 조립기의 "</"→"<\/" 는 JSON 표준 이스케이프라 그대로 읽힌다
    except ValueError as e:
        return None, (f"fr-doc 의 JSON 이 깨져 있습니다 — {e}. 손으로 고친 파일이면 "
                      f"고치기 전 원본을 넣어 주세요")
    if not isinstance(doc, dict):
        return None, (f"fr-doc 이 문서 한 벌(객체)이 아니라 {type(doc).__name__} 입니다 — "
                      f"우리가 낸 HTML 이 맞는지 봐 주세요")
    return doc, ""


# 조립기 다섯이 전부 <html …> 에 심는 장르 표식 — fr-doc 의 genre 가 비었을 때의
# 예비 눈이다(아래 _장르찾기 주석).
_장르속성꼴 = re.compile(r'<html\b[^>]*\bdata-genre\s*=\s*["\']([^"\']+)["\']', re.I)


def _장르찾기(doc, 글=""):
    """fr-doc 의 genre(조립기가 심는 data-genre 값)를 등록부 이름으로 되돌린다.

    fr-doc 에 genre 가 없으면 `<html data-genre>` 속성을 본다 — 등록부에 genre 가
    없던 옛 문서가 실재해서다(2026-08-08 실측: 1p 정본 사례 중 사례. 그 문서의 낸
    HTML 은 fr-doc 에도 genre 가 없다). 조립기 다섯이 전부 이 속성을 심으므로
    (산출물 전수 실측) 우리 파일이면 반드시 한쪽에는 있다. **둘 다 있는데 서로
    다르면 고르지 않고 거절한다** — 손탄 파일에서 어느 쪽을 고르든 고른 쪽이 뚫린다.

    표는 **genres.등록부()에서 세어서** 만든다(규칙 2) — 'onepage'→'samples' 같은
    짝을 여기 손으로 적으면 장르가 늘 때 이 문만 조용히 빠진다.
    """
    genre = doc.get("genre")
    genre = genre.strip() if isinstance(genre, str) else ""
    m = _장르속성꼴.search(글 or "")
    속성 = m.group(1).strip() if m else ""
    if genre and 속성 and genre != 속성:
        return None, (f"fr-doc 의 genre({genre!r})와 문서의 data-genre({속성!r})가 "
                      f"서로 다릅니다 — 어느 쪽이 맞는지 고르지 않고 거절합니다. "
                      f"손대지 않은 원본 파일로 다시 넣어 주세요")
    genre = genre or 속성
    if not genre:
        return None, ("fr-doc 에도 <html data-genre> 에도 장르가 없습니다 — 어느 "
                      "장르로 세울지 알 수 없어 거절합니다. 우리가 낸 HTML 에는 "
                      "둘 중 하나가 반드시 있습니다")
    genres = 자료뿌리.모듈("genres")
    표 = {g["장르"]: g["이름"] for g in genres.등록부()}
    이름 = 표.get(genre)
    if 이름 is None:
        return None, f"모르는 장르입니다: {genre!r} (아는 것: {sorted(표)})"
    return 이름, ""


@등록("편집기열기", ["key", "포트"], 읽기=False,
    설명="로컬 편집기 서버(127.0.0.1)를 잠깐 띄우고 편집기를 사용자의 기본 브라우저에서 연다 — "
        "저장·이력(되돌림 지점)·재조립이 웹앱처럼 정본에 바로 반영된다(편집 단계 협업용). "
        "이미 떠 있으면 재사용한다",
    en="editor")
def 편집기열기(key, 포트=8642):
    """편집 단계에서 부른다. serve.py 를 **단일세션**(쿠키 격리 없이 이 세션 뿌리)으로 127.0.0.1 에
    띄우고 editor-<key>.html 을 OS 기본 브라우저로 연다.

    왜 서버인가 — file:// 로 열면 코딩에이전트의 내장 브라우저가 JS·저장을 제대로 못 돌리고(정적
    스냅샷), 저장·이력이 채팅 중개라 UI 에 안 뜬다. http://127.0.0.1 이면 편집기의 서버 경로가 살아
    저장→정본 반영·이력(되돌림 지점)·재조립이 웹앱과 똑같이 돈다. 데이터는 localhost 를 안 떠난다
    (기본 127.0.0.1 바인드, 관리자 면은 열쇠 없으면 잠김)."""
    if _여러사람웹앱() or 자료뿌리.세션열쇠():   # 보안('26-10-01): 웹앱·공유 세션에서는 서버에 편집 서버를 띄우지 않는다
        return {"ok": False, "로그": "웹앱에서는 편집 화면이 곧 편집기입니다 — 이 작업은 플러그인(로컬)에서만 씁니다"}
    if not 자료뿌리.키맞나(str(key or "")):
        return {"ok": False, "로그": "문서 이름(key) 꼴이 맞지 않습니다"}
    import urllib.request
    import urllib.error
    import webbrowser
    import shutil
    try:
        포트 = int(포트)
    except Exception:
        포트 = 8642
    # 편집기 파일은 **자료 쪽**(세션 뿌리 workspace/editors)에 구워진다 — serve.py 도 /workspace/editors/ 를 자료
    # 쪽에서 내준다. 예전엔 코드뿌리(ROOT)를 봐 자료뿌리·세션 방에서는 늘 '편집기 파일이 없습니다'였다
    # ('26-09-29 E2E §4-A 재현: 함께 검수 2건 모두 여기서 막힘).
    편집기 = os.path.join(자료뿌리.편집화면뿌리(), f"editor-{key}.html")
    if not os.path.exists(편집기):
        return {"ok": False, "로그": f"편집기 파일이 없습니다: workspace/editors/editor-{key}.html "
                "— 먼저 새문서(new)로 문서를 만들어 편집기를 구우세요"}
    url = f"http://127.0.0.1:{포트}/workspace/editors/editor-{key}.html"
    베이스 = f"http://127.0.0.1:{포트}/"

    def _받나(u, timeout=0.6):
        try:
            with _HTTP열기.open(u, timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return None

    떠있음 = _받나(url) == 200
    if not 떠있음:
        # 포트에 남의 서버가 있으면(우리 편집기 URL 이 200 이 아닌데 뭔가 응답) 막지 말고 알린다.
        if _받나(베이스) is not None:
            return {"ok": False, "로그": f"{포트} 포트에 이미 다른 서버가 있습니다 — 다른 포트를 "
                    f"주세요(예: 편집기열기 key={key} 포트={포트 + 1})"}
        # serve.py 를 단일세션으로 백그라운드 기동. env 는 현재 것을 복사해(자료뿌리·PATH·세션 보존)
        # 문서지능_단일세션만 얹는다 — 이 세션 뿌리를 그대로 봐 /save 가 방금 만든 문서를 찾는다.
        환경 = dict(os.environ)
        환경["문서지능_단일세션"] = "1"
        srv = os.path.join(ROOT, "workspace", "serve.py")
        try:
            _로그 = open(os.path.join(자료뿌리.기본뿌리(), ".편집서버.log"), "ab")
        except Exception:
            _로그 = subprocess.DEVNULL
        try:
            subprocess.Popen([sys.executable, srv, str(포트)], cwd=ROOT, env=환경,
                             stdout=_로그, stderr=_로그, start_new_session=True)
        except Exception as e:
            return {"ok": False, "로그": f"편집기 서버를 띄우지 못했습니다: {e}"}
        for _ in range(30):                    # 뜰 때까지 대기(최대 ~6초)
            if _받나(url) == 200:
                떠있음 = True
                break
            time.sleep(0.2)
        if not 떠있음:
            return {"ok": False, "로그": f"편집기 서버가 {포트} 포트에서 뜨지 않았습니다 — "
                    "잠시 후 다시 시도하거나, 로그(.편집서버.log)를 확인하세요"}
    # 사용자의 기본 브라우저로 연다. 원격·헤드리스면 실패할 수 있으니 URL 은 늘 돌려준다.
    열림 = False
    try:
        열림 = bool(webbrowser.open(url))
    except Exception:
        열림 = False
    if not 열림:
        for 명령 in (["open", url], ["xdg-open", url]):
            if shutil.which(명령[0]):
                try:
                    subprocess.Popen(명령, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    열림 = True
                    break
                except Exception:
                    pass
    return {"ok": True, "값": {"url": url, "브라우저열림": 열림},
            "로그": (f"편집기를 브라우저에서 열었습니다 — {url}\n"
                    "▸ 사용자가 직접 다듬도록 두세요. 저장·이력(되돌림 지점)·재조립이 정본에 "
                    "바로 반영됩니다. " + _갈래("'이대로 좋다' 확인 뒤에 내보내세요.",
                                             "이미 내보낸 뒤라면 고친 뒤 내보내기(export)를 다시 불러 새 파일을 만드세요.")
                    + " 사람이 고치면 판이 바뀌어 검사 기록이 비므로, 내보내기 전에 검사를 다시 돌리세요(저장 검사 "
                    "true·원문, 또는 문체검사·조판게이트·지어냈나)."
                    if 열림 else
                    "서버는 떴지만 브라우저 자동 열기에 실패했습니다(원격·헤드리스일 수 있음) — "
                    f"이 주소를 사용자에게 전해 직접 여시게 하세요: {url}")}


@등록("이어받기", ["html"], 읽기=False,
    설명="낸 HTML 을 다시 넣어 이어 고친다 — fr-doc JSON 을 꺼내 새문서로 세운다",
    en="resume")
def 이어받기(html):
    """최초 입력 4갈래 중 ②(출시계획 1-4). 장르별 분기가 **없다** — 조립기 다섯이
    전부 같은 fr-doc id 로 심는 것을 2026-08-08 실측으로 확인했다(산출물 사례 전부
    정확히 1개·JSON 파싱 성공). 장르는 fr-doc 안의 genre 값으로 되돌린다.
    """
    doc, 탈 = _fr문서뽑기(html)
    if doc is None:
        return {"ok": False, "로그": 탈}
    장르, 탈 = _장르찾기(doc, html)
    if 장르 is None:
        return {"ok": False, "로그": 탈}
    # 부르기() 를 지나 새문서로 간다 — 직접 부르면 등록부에 뒤에 생길 관문(승인·
    # 되묻기 따위)을 이 문만 조용히 건너뛰게 된다. 이름 규칙·중복·조립 실패 시
    # 되돌리기는 전부 새문서 몫이고, 그 실패 문구가 그대로 사용자에게 간다(규칙 3).
    # 다만 **빌드플랜 승인 게이트만은 면제**한다 — resume 는 새 문서를 짓는 게 아니라 이미
    # 승인·완성돼 낸 문서를 되살려 이어 고치는 것이라, 새 설계·승인을 다시 받을 대상이 아니다.
    # 원본이 플랜 흐름으로 났으면 fr-doc 에 남은 plan_id 는 이 세션에 없을 수 있으니 소거한다.
    doc.pop("plan_id", None)
    doc["_이어받음"] = True
    r = 부르기("새문서", {"doc": doc, "장르": 장르})
    if isinstance(r, dict) and r.get("ok"):
        키 = r.get("key") or doc.get("filename")
        r.setdefault("값", {})
        r["값"].update({"key": 키, "장르": 장르, "genre": doc.get("genre")})
        r["로그"] = f"낸 HTML 에서 '{키}' 를 이어받았습니다({장르})\n" + (r.get("로그") or "")
    return r


인자별칭 = {"path": "path", "key": "key", "docs": "docs", "payload": "payload", "only": "only",
          "profile": "profile", "n": "n", "reason": "이유", "nosnap": "판없이",
          "plan": "plan", "what": "무엇",
          "doc": "doc", "genre": "장르", "path": "path", "file": "경로", "fmt": "형식",
          "id": "id", "prompt": "지시문", "material": "자료", "sample": "예시",
          "answers": "어긋남답", "decision": "결정", "item": "항목",
          "check": "검사", "full": "전체"}


def 찾기(이름):
    """이름이나 ASCII 별칭으로 작업 하나를 찾는다. **찾는 길은 여기 하나뿐이다** —
    서버가 따로 찾다가 별칭이 한쪽에만 붙는 일이 있었다(2026-08-04)."""
    return 작업.get(별칭.get(이름, 이름))


def _원격(서버, 이름, 인자):
    """코어 서버로 작업을 위임한다 — POST {서버}/api/{이름}, JSON 그대로 (구현계획.md §3 WP-S1).

    urllib 만 쓴다(의존성 추가 금지). 연결 실패·시간초과를 조용히 로컬 실행으로 넘기지
    않는다(규칙 3 — 조용한 실패 금지): 여기서 로컬로 빠지면 원격 코어가 죽었는데도
    이 프로세스가 자기 로컬 산출물을 마치 원격 결과인 것처럼 돌려주게 된다.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    길 = f"{서버.rstrip('/')}/api/{urllib.parse.quote(str(이름), safe='')}"
    본 = json.dumps(인자 or {}, ensure_ascii=False).encode("utf-8")
    # User-Agent 를 명시한다 — urllib 기본 UA(Python-urllib/x)를 Cloudflare Bot Fight Mode 가
    # 봇으로 403 차단한다(2026-08-18 실측: curl·브라우저·커스텀 UA 는 200, Python-urllib 만 403).
    # 브라우저 위장이 아니라 이 정책 클라이언트를 정직히 식별하는 UA 다.
    머리 = {"Content-Type": "application/json; charset=utf-8",
          "User-Agent": "artifact-intelligence-policy/0.1"}
    # **정책 토큰을 실어 보낸다** — 플러그인 위임 문은 발급받은 토큰으로만 열린다(WP-S6).
    # 없으면 안 붙인다: 개발 트리(로컬 온톨로지)나 토큰 미설정 서버는 토큰 없이도 돌아야
    # 하므로 여기서 강제하지 않는다. 강제는 **받는 쪽**(serve.py 정책 게이트)의 몫이다.
    토큰 = _정책토큰설정()
    if 토큰:
        머리["X-AI-Token"] = 토큰
    # **세션을 실어 보낸다** (2026-08-07, WP-S4 실측으로 걸림). 전에는 쿠키를 안 붙여서
    # 원격 호출이 갈 때마다 코어가 **새 세션 방을 하나씩** 세웠다 — 재 봤다: 원격
    # `문서목록` 두 번에 sessions/ 가 5→6→7 로 늘었다. 그러면 원격 클라이언트는 방금
    # 자기가 만든 문서를 다음 호출에서 못 찾는다(매번 빈 방이다). 저장을 원격으로 부르는
    # 길을 여는 것이 이 작업의 절반인데, 세션이 안 이어지면 그 길은 열려도 못 쓴다.
    # 쿠키 이름은 자료뿌리 한 곳에서 온다 — serve.py 와 갈리면 조용히 안 이어진다.
    try:
        열쇠 = 자료뿌리.세션열쇠()
    except Exception:
        열쇠 = ""                       # 열쇠가 규칙에 안 맞으면 세션 없이 간다(서버가 새로 준다)
    if not 열쇠:
        # 스킬(전부-A1 모드)엔 세션 env 가 없다 — 발급 토큰에서 **안정된** 세션 열쇠를 뽑는다.
        # 그래야 이 설치의 문서가 A1 세션에 계속 머문다(초안→조립→검사→내보내기 한 자리에서
        # 이어짐). 토큰이 곧 신분이니 그 해시(소문자 32 hex, _열쇠꼴에 맞음)를 세션 열쇠로
        # 쓴다 — 토큰만큼 비밀이라 세션을 남이 가로채지 못한다. 토큰이 없으면(개발/무토큰)
        # 세션 없이 가고 서버가 새로 준다(지금과 같다).
        try:
            t = _정책토큰설정()
            if t:
                열쇠 = hashlib.sha256(("세션:" + t).encode("utf-8")).hexdigest()[:32]
        except Exception:
            열쇠 = ""
    if 열쇠:
        머리["Cookie"] = f"{자료뿌리.세션쿠키}={열쇠}"
    요청 = urllib.request.Request(길, data=본, method="POST", headers=머리)
    try:
        # 조판게이트(최대 900초, §3 WP-S4)까지 기다려야 하니 넉넉히 잡는다.
        with _HTTP열기.open(요청, timeout=920) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        본문 = e.read()
        try:
            결과 = json.loads(본문.decode("utf-8"))
        except Exception:
            결과 = {"ok": False, "로그": f"코어 서버에 못 닿았다: HTTP {e.code} {e.reason}"}
        # 429(요청 상한) 표를 남긴다(still_partly 항목 8) — _지식전체 의 너비 우선 조회가
        # 이 표를 보고 **재시도로 요청을 더 늘리지 않고 즉시 멈춘다**(자동 잠금은 상한
        # 초과가 반복될 때 걸린다 — serve.py _정책레이트초과).
        if isinstance(결과, dict) and e.code == 429:
            결과["_한도초과"] = True
        return 결과
    except Exception as e:
        return {"ok": False, "로그": f"코어 서버에 못 닿았다: {e}"}


def _로컬강제():
    """코어 서버(serve.py)가 기동 때 켠다 — 이게 켜지면 어떤 conf/env 가 있어도 위임하지
    않고 로컬에서 돈다(서버가 자기 자신을 다시 부르는 고리 차단). 스킬 프로세스엔 안 켜진다."""
    return bool(os.environ.get("문서지능_로컬강제"))


def _서버설정():
    """'전부 A1' 모드 — 이게 있으면 **모든 작업**을 이 서버로 넘긴다(스킬·로컬MCP 배포용).
    env(문서지능_서버) 우선, 없으면 ROOT/서버.conf(배포준비.py 가 A1 URL 로 씀). 정책서버설정과
    같은 폴백 논리. 코어 서버(A1)는 _로컬강제 라 이 파일이 있어도 자기 자신을 안 부른다."""
    if _로컬강제():
        return None
    u = os.environ.get("문서지능_서버")
    if u and u.strip():
        return u.strip()
    try:
        p = os.path.join(ROOT, "서버.conf")
        if os.path.exists(p):
            v = open(p, encoding="utf-8").read().strip()
            return v or None
    except OSError:
        pass
    return None


def _정책서버설정():
    """정책서버 URL — env(문서지능_정책서버)가 우선, 없으면 배포 트리에 실린 설정 파일
    (ROOT/정책서버.conf, 배포준비.py 가 A1 URL 로 씀)을 읽는다. 개발 트리엔 그 파일이 없어
    None → 로컬 온톨로지로 폴백. 한글 env 변수 전파가 불안정한 플러그인 host 에서도
    파일 폴백으로 A1 위임이 성립하게 하는 것이 목적(한글 env 함정 회피)."""
    if _로컬강제():
        return None
    u = os.environ.get("문서지능_정책서버")
    if u and u.strip():
        return u.strip()
    try:
        p = os.path.join(ROOT, "정책서버.conf")
        if os.path.exists(p):
            v = open(p, encoding="utf-8").read().strip()
            return v or None
    except OSError:
        pass
    return None


def _정책토큰설정():
    """플러그인이 정책서버에 낼 토큰 — env(문서지능_정책토큰)가 우선, 없으면 배포 트리의
    ROOT/정책서버토큰.conf. 설치자는 발급받은 토큰을 둘 중 한 곳에 둔다(README). 없으면
    None → 토큰 없이 간다(개발 트리·토큰 미설정 서버는 그대로 돌고, 강제는 받는 쪽이 한다).
    정책서버.conf 와 같은 폴백 논리 — 한글 env 전파가 불안정한 host 에서 파일로 성립시킨다."""
    v = os.environ.get("문서지능_정책토큰")
    if v and v.strip():
        return v.strip()
    try:
        p = os.path.join(ROOT, "정책서버토큰.conf")
        if os.path.exists(p):
            t = open(p, encoding="utf-8").read().strip()
            # 주석·빈 줄은 무시한다(설치자가 파일에 안내 주석을 남겨 둬도 토큰으로 안 읽는다).
            for 줄 in t.splitlines():
                줄 = 줄.strip()
                if 줄 and not 줄.startswith("#"):
                    return 줄
    except OSError:
        pass
    return None


def _자료작(작):
    """이 작업이 사용자 자료(문서 내용)를 인자로 받나 — 받으면 정책서버로 위임하지 않고
    로컬에서 돈다(정책만-로컬: 사용자 정보보호 최우선). 자료 없는 정책작업만 위임한다."""
    return any(a in (작.get("받는것") or ()) for a in ("자료", "자료들", "payload", "doc", "docs"))


def 부르기(이름, 인자=None):
    """이름으로 작업 하나를 부른다. 세 껍데기가 다 이 함수만 쓴다."""
    서버 = _서버설정()
    if 서버:
        # 원격 코어로 위임한다 — **작업 이름별 분기를 절대 두지 않는다.** 등록부
        # 일반화가 이 구조의 심장이다(구현계획.md §3 WP-S1). serve.py 자기 자신은
        # 시작할 때 이 환경변수를 지워서, 서버가 요청을 처리하는 도중 자기 자신을
        # 다시 원격 호출하는 고리가 생기지 않게 막아 둔다(workspace/serve.py 참고).
        return _원격(서버, 이름, 인자)
    작 = 찾기(이름)
    # 정책작업은 **로컬 온톨로지를 먼저 쓴다**('26-10-01). 공개 플러그인도 ontology/ontology.json 을
    # 함께 싣게 되면서, 배포 트리에 정책서버.conf 가 있어도 장르·시퀀스·개인·지식을 로컬에서 돌린다
    # (전에는 conf 만 있으면 로컬 온톨로지와 상관없이 서버로 넘겨, 서버가 닿지 않으면 "코어 서버에
    # 못 닿았다"로 죽었다 — release04 인벤토리 B4 실측). 정책서버로 넘기는 것은 두 경우뿐이다:
    #   ① 이 설치에 온톨로지 파일이 없다(옛 0.3.x 트리 등) — 자료 없는 정책작업만 예전처럼 넘긴다.
    #   ② 서버 모델이 있어야 도는 작업(등록부 '서버모델', 키 없는 AI 다시쓰기)인데 이 컴퓨터에 LLM
    #      설정이 없다.
    # **사용자 자료를 받는 정책작업(판정·프롬프트조립·설계지시문내기)은 어느 경우에도 넘기지 않는다**
    # (_자료작 — 정책만-로컬: 사용자 정보보호 최우선). 이름별 분기가 아니라 등록부 플래그에서 파생.
    정책서버 = _정책서버설정()
    로컬규칙 = os.path.exists(os.path.join(ROOT, "ontology", "ontology.json"))
    if (정책서버 and 작 and 작.get("정책") and not _자료작(작)
            and (not 로컬규칙 or (작.get("서버모델") and not _서버LLM설정()))):
        return _원격(정책서버, 이름, 인자)
    # 정책작업인데 로컬 온톨로지도 정책서버도 없으면 — 조용한 FileNotFoundError 대신 명시 거절한다
    # (fail-closed). 서버 모델 작업은 규칙 파일이 아니라 LLM 이 필요하므로 이 거절에서 뺀다
    # (그 작업이 스스로 'LLM 설정 없음'을 알린다).
    if (작 and 작.get("정책") and not 정책서버 and not 로컬규칙 and not 작.get("서버모델")):
        return {"ok": False, "로그": "작성 규칙 파일(ontology/ontology.json)이 없습니다. "
                "설치본에 함께 들어 있어야 하니 플러그인을 다시 설치하거나 업데이트하세요. "
                "개발 환경이라면 ontology/ontology.json 을 두십시오."}
    이름 = 별칭.get(이름, 이름)
    if not 작:
        return {"ok": False, "로그": f"모르는 작업입니다: {이름}",
                "할수있는것": sorted(작업)}
    _겹침 = _인자겹침(작, 인자)
    인자 = _인자풀기(작, 인자)
    # 이번 호출의 방식(work_mode) — 방식 인자를 받지 않는 작업에 실려 오면 떼어 넛지에만 쓴다(fixup4 ⑤ — CLI 는 대화를
    # 기억하지 않으므로 에이전트가 호출마다 싣는다).
    호출방식 = None
    if "방식" in 인자 and "방식" not in 작["받는것"]:
        v = 인자.pop("방식")
        if str(v or "").strip():
            호출방식 = _방식정규화(v)
            if not 호출방식:
                return {"ok": False, "로그": f"방식(work_mode)은 바로완성·함께검수 가운데 하나입니다 (받은 값: {v})"}
    # 이번 호출의 이미지 도구(image_tool, '26-09-30 주관 판정) — 이미지능력은 대화 단위라 CLI 는 호출마다 싣는다(작업방식과
    # 같은 방식). 떼어 imageasset.호출능력 에 이 호출 동안만 둔다.
    호출그림도구 = None
    if "이미지도구" in 인자 and "이미지도구" not in 작["받는것"]:
        호출그림도구 = re.sub(r"\s+", " ", str(인자.pop("이미지도구") or "")).strip()[:60] or None
    모르는 = [k for k in 인자 if k not in 작["받는것"]]
    if 모르는:
        예시글 = ""
        try:
            # 기대 인자 모양을 오류에 담는다(항목 10, '26-09-26 벤치마크 진단) — SKILL.md
            # 예시와 **같은 것**을 쓴다(build/skill_doc.py 흐름예시, 손목록을 두 곳에
            # 두지 않는다). 그 파일이 없거나 이 작업이 목록 밖이면 조용히 생략한다.
            예시 = 자료뿌리.모듈("skill_doc").흐름예시.get(이름)
            if 예시:
                예시글 = f" · 예시: {예시}"
        except Exception:
            pass
        return {"ok": False, "로그": f"{이름} 이 안 받는 인자: {모르는} "
                                  f"(받는 것: {list(작['받는것'])}){예시글}"}
    # 웹앱 자료 원문 전체를 세션에 보관한다(fixup3 Z2) — 자료를 받는 작업은 등록부 받는것('자료'·'원문')에서 파생(이름별 분기 없음).
    # 웹앱 '확인할 것'이 문서의 _맥락(앞 4,000자 조각) 대신 이 전문으로 잰다(_웹전체원문).
    if os.environ.get("문서지능_웹앱"):
        _받은자료 = 인자.get("자료") if 인자.get("자료") else 인자.get("원문")
        if _받은자료:
            try:
                _웹자료적기(_받은자료)
            except Exception as _e:
                print(f"[웹자료] 보관 실패(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    # 되묻기 관문(WP-S3) — 어느 작업이 막히는가는 등록부의 승인필요 하나에서 온다
    # (이름별 분기 금지). 세 문과 작업시작 스레드가 전부 이 함수를 타므로 관문도
    # 여기 하나다. 관문이 어긋남답을 받아 기록하고, 남은 물음이 있으면 여기서 선다.
    표 = _호출방식.set(호출방식) if 호출방식 else None
    그림표 = None
    if 호출그림도구 and not os.environ.get("문서지능_웹앱"):
        try:
            그림표 = (자료뿌리.모듈("imageasset"), 자료뿌리.모듈("imageasset").호출능력.set(호출그림도구))
        except Exception as _e:
            print(f"[그림] 호출 이미지 도구 오류(건너뜀): {type(_e).__name__}: {_e}", file=sys.stderr)
    try:
        if 작.get("승인필요"):
            막힘 = _되묻기관문(인자)
            if 막힘 is not None:
                return 막힘
        try:
            결과 = 작["함수"](**인자)
            if _겹침 and isinstance(결과, dict):
                결과 = dict(결과)
                결과["로그"] = ((결과.get("로그") or "") + "\n⚠ 같은 인자를 두 이름으로 다르게 받았습니다 — "
                              + " · ".join(_겹침) + ". 한 이름으로만 실어 부르세요").lstrip("\n")
            return 결과
        except TypeError as e:
            return {"ok": False, "로그": f"인자가 맞지 않습니다 — {e}"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "로그": "너무 오래 걸립니다"}
        except Exception as e:
            return {"ok": False, "로그": f"{type(e).__name__}: {e}"}
    finally:
        if 표 is not None:
            _호출방식.reset(표)
        if 그림표 is not None:
            그림표[0].호출능력.reset(그림표[1])


def _인자겹침(작, 인자):
    """같은 인자를 한글·영문(또는 옛 별칭) 두 이름으로 **다른 값**으로 받았는가 — ['형식/format: 뒤의 값('md')을 씁니다' …]
    (fixup5 주관 ⑤, verify4 §4: {"형식":"json","format":"md"} 는 뒤에 적은 쪽이 경고 없이 이겼다). 값이 같으면 조용하다."""
    받는 = tuple(작.get("받는것") or ())
    영문 = {인자영문.get(a, a): a for a in 받는}
    본 = {}
    for k, v in (인자 or {}).items():
        한 = k if k in 받는 else 영문.get(k) or ("방식" if k in ("work_mode", "방식") else 인자별칭.get(k, k))
        본.setdefault(한, []).append((k, v))
    나온다 = []
    for 한, 쌍 in 본.items():
        if len(쌍) > 1 and len({json.dumps(v, ensure_ascii=False, sort_keys=True, default=str) for _, v in 쌍}) > 1:
            나온다.append("/".join(k for k, _ in 쌍) + f": 뒤의 값({json.dumps(쌍[-1][1], ensure_ascii=False, default=str)[:40]})을 씁니다")
    return 나온다


def _인자풀기(작, 인자):
    """받은 인자 이름을 작업의 한글 이름으로 푼다 — 작업이 받는 이름 그대로 → 그 작업 인자의 **MCP 영문 이름**
    (api.인자영문 — MCP 가 서명에 쓰는 바로 그 표) → 옛 CLI 별칭(인자별칭) 차례. CLI 도 MCP 와 같은 영문 이름을
    받는다(fixup4 주관 ④, verify3 §6 C10: format·comment·conflict_answers·port … 29개를 못 받았다). 영문 이름은
    작업마다 푼다 — 같은 영문('path')이 작업에 따라 다른 한글(경로·path)일 수 있다. work_mode 는 방식을 받지 않는
    작업에도 '방식'으로 푼다(부르기가 떼어 넛지에 쓴다)."""
    받는 = tuple(작.get("받는것") or ())
    영문 = {인자영문.get(a, a): a for a in 받는}
    풀림 = {}
    for k, v in (인자 or {}).items():
        if k in 받는:
            풀림[k] = v
        elif k in 영문:
            풀림[영문[k]] = v
        elif k in ("work_mode", "방식"):
            풀림["방식"] = v
        else:
            풀림[인자별칭.get(k, k)] = v
    return 풀림


def 목록(관리자포함=False):
    """작업 하나에 대해 아는 것을 **다** 내보낸다.

    전에는 키를 손으로 다섯 개만 적었다. 그래서 `모양`(인자가 무슨 꼴인가)을
    등록부에 넣어도 MCP 까지 안 갔고, 문서를 넣는 자리가 계속 글로 선언됐다
    (2026-08-05 A-4 11번). **여기서 고르지 않는다** — 못 쓰는 것(함수)만 뺀다.

    **관리자 작업은 뺀다**(WP-S5, 출시계획 3-4). 이 목록을 읽는 세 곳이 전부
    관리자 작업을 그냥 노출하면 안 되기 때문이다:
      · `mcp/server.py` — 목록의 작업마다 MCP 도구를 만든다. 관리자 작업이 들면
        **열쇠 없는 MCP 도구**가 생겨 게이트가 통째로 우회된다(serve.py 밖의 문).
      · `build/skill_doc.py` — SKILL.md 작업 표를 만든다. 관리자 작업을 스킬
        문서에 광고할 이유가 없다.
      · `serve.py _get` 의 `GET /api` — 공개 목록에 관리자 작업을 실을 이유가 없다.
    관리자 면(admin.html)은 작업 이름을 **알고** 부르므로 이 목록에 안 실려도 된다.
    거르는 기준은 등록부의 `관리자` 플래그 하나다 — 이름을 손으로 나열하지 않는다
    (손목록 금지: 구현계획.md 규칙 2). `관리자포함=True` 는 검사·디버그 전용이다.
    """
    # 관리자 작업과 함께 **공개발급(enroll)** 도 뺀다 — enroll 은 설치 부트스트랩이 고정
    # 경로(/api/enroll)로 부르는 인프라 문이지 에이전트가 쓰는 문서 도구가 아니다. MCP
    # 도구·SKILL 표·공개 목록에 실을 이유가 없다(HTTP 디스패치는 전체 등록부에서 풀어 무영향).
    return [{k: (list(v) if k == "받는것" else v) for k, v in w.items() if k != "함수"}
            for w in 작업.values()
            if 관리자포함 or not (w.get("관리자") or w.get("공개발급") or w.get("숨김"))]


# ── WP-S6: 게이트 배선 — 지어냈나(환각 검수) ─────────────────────────────
# 파일 끝쪽에 두는 까닭 — 같은 자리(중간)에 끼우다 add/add 충돌이 하루 세 번 났다.
# 새 작업은 끝에 붙이고 등록만 한다. 인자 별칭도 사전 리터럴을 고치지 않고 덧댄다.
인자별칭["source"] = "원문"
# r9 검토자 발견(loop-channels LOW) — MCP 설명·SKILL 안내가 "[인자 대응: fixes=고침]"
# 이라고 적어 놓고도 정작 별칭이 없어 fabfixapply 를 fixes/source_text 로 부르면
# "안 받는 인자"로 거절됐다. 다른 영문 별칭(reason·source 등)과 같은 자리에 마저 단다.
인자별칭["fixes"] = "고침"
인자별칭["source_text"] = "원문"
# 작업방식·내보내기 관문('26-09-29) — CLI 로 영문 키를 실어도 받게(MCP 는 인자영문 서명으로 이미 푼다).
인자별칭["work_mode"] = "방식"
인자별칭["request"] = "요청"
인자별칭["override_reason"] = "강행이유"
# 이미지능력은 대화 단위('26-09-30) — CLI 는 그림 요청이 생길 호출마다 이미지 도구 이름을 싣는다(부르기가 떼어 쓴다).
인자별칭["image_tool"] = "이미지도구"


@등록("지어냈나", ["key", "원문"], 읽기=False, en="fabcheck",
    설명="초안이 자료 원문에 없는 숫자·이름을 지어냈는지 재고, 있으면 되묻는다")
def 지어냈나검수(key, 원문=""):
    """초안(3층 JSON)이 등록된 직후 부른다(출시계획 3-5, 확정 2026-08-07).

    걸리면 **ok:false 다** — "재기는 다 재었으니 성공"이라고 적으면 부르는 쪽이
    통과로 읽는다(구현계획.md 규칙 3 · WP-S4 일감의 상태 규칙과 같은 결). 무엇이
    걸렸는지는 값의 `물음`(사람에게 그대로 보일 되묻는 말)과 `수치`·`이름`에 있다.
    원문에 없다 ≠ 반드시 거짓이라(사용자 머릿속의 사실일 수 있다) 지우지 않고
    **되묻는다** — 판단은 사람이 하고, 조용한 통과만 금지다.
    """
    r = 문서(key)
    if not r["ok"]:
        return r
    잰 = _잰판(key, r["값"])       # 재는 내용의 지문 — 결과는 이 판에 묶는다(fixup5 ①)
    # 이 문서가 처음 받은 원문으로 잰다(fixup3, verify2 §1-B X1·X2) — 원문을 빼면 보관 원문으로, 다른 원문을
    # 주어도 보관 원문으로. 보관도 받은 것도 없을 때만 거절한다.
    원문, _원문알림 = _검사원문(key, 원문)
    if not str(원문 or "").strip():
        # 원문이 없으면 잴 수 없다 — 조용한 통과가 아니라 명확한 거절이다(규칙 3).
        return {"ok": False, "로그": "자료 원문이 없습니다 — 초안을 무엇과 대조할지 "
                                  "알 수 없어 지어냈는지 잴 수 없습니다"}
    검 = 자료뿌리.모듈("지어냈나")
    # 이 문서 유형의 시퀀스만 받아 넘긴다(판정 때 확보한 것 — 온톨로지 통째 로컬 read 아님).
    # 시퀀스는 정책=True 라 온톨로지 파일이 없는 옛 설치에서만 정책서버로 위임된다(부르기 참고).
    유형id = (r["값"] or {}).get("purpose_type")
    시퀀스 = (부르기("시퀀스", {"유형id": 유형id}).get("값") or []) if 유형id else []
    숫, 이 = 검.재기(str(원문), r["값"], 시퀀스)
    # 몇 건이 걸렸는지만 세션 기록에 남긴다 — 걸린 값 자체는 문서·자료 내용이라
    # 적지 않는다(출시계획 1-6 A안, _규칙세기·어긋남과 같은 결).
    자료뿌리.규칙적기("지어냈나", {"수치": len(숫), "이름": len(이)})
    값 = {"수치": [{"어디": a, "값": b, "곁": c} for a, b, c in 숫],
         "이름": [{"어디": a, "값": b, "곁": c} for a, b, c in 이],
         "갯수": len(숫) + len(이), "물음": 검.물음말(숫, 이)}
    # 내보내기 관문이 보는 이 판의 기록(H2) — 숫자·이름(재기)과 확장 칸(검토하기)을 같이 적는다. 재는 도중 판이
    # 바뀌었으면 적지 않는다(fixup5 ①).
    확장, 확장오류 = [], False
    try:
        확장 = 검.검토하기(_자료글(원문), r["값"], 시퀀스) or []
    except Exception as e:
        print(f"[지어냈나확장] 기록용 검사 오류: {type(e).__name__}: {e}", file=sys.stderr)
        확장오류 = True
    그대로, _경합알림 = _잰판그대로(key, 잰, "지어냈나")
    적음 = False
    if 그대로:
        적음 = _검사적기(key, "지어냄", not 값["갯수"], 잰=잰)
        적음 = _검사적기(key, "확장", not 확장 and not 확장오류, 잰=잰) and 적음
        if not 적음:
            _경합알림 = "\n⚠ 지어냈나 결과를 검사 기록에 적지 못했습니다 — 이 결과로는 내보낼 수 없습니다. 지어냈나를 다시 부르세요."
    if _경합알림:
        _원문알림 = ((_원문알림 + "\n") if _원문알림 else "") + _경합알림.strip()
    # 의심 값을 적어 두고, 앞선 판에서 걸렸다가 사라진 값은 '고친 곳'으로 쌓는다(fixup3 E — 끝 보고의 확인할것).
    if 그대로:
        _의심적기(key, [b for _, b, _c in 숫 + 이] + [f"{g.get('종류')}: {g.get('값')}" for g in 확장 if isinstance(g, dict)])
    머리 = (_원문알림 + "\n") if _원문알림 else ""
    if not 값["갯수"]:
        if not 적음:
            # 기록이 없는 검사는 통과가 아니다(fixup6, verify5 N8)
            return {"ok": False, "기록": False, "값": 값, "로그": 머리 + "원문에 없는 수치·이름 없음 — 다만 검사 기록에 적지 못했습니다"}
        return {"ok": True, "값": 값, "로그": 머리 + "원문에 없는 수치·이름 없음 — 지어낸 사실 없음"}
    return {"ok": False, "값": 값,
            "로그": 머리 + f"원문에 없는 수치 {len(숫)}건 · 이름 {len(이)}건 — 되물어야 합니다\n\n"
                  + 값["물음"]
                  + ("" if os.environ.get("문서지능_웹앱") or _알려진방식() == "함께검수" else
                     "\n\n(바로 완성이면 묻지 말고 자료대로 고치거나 ○○로 비우세요. 자료 값으로 셈한 합계·비율·"
                     "차이는 doc 의 산출(슬라이드 v2 는 그 장의 산출)에 {\"값\": \"62.5%\", \"식\": \"5/8\"} 처럼 식을 "
                     "적으면 식을 풀어 확인하고 통과시킵니다. 고친 곳은 끝 보고의 '확인할 것'에 올립니다.)")}


@등록("글자깨짐확인", ["key"], en="garblecheck",
    설명="등록된 문서를 build/깨짐.py 로 다시 잰다 — 새문서() 가 값.깨짐 에 실어 둔 결과를 "
        "검사하기() 화면(리터칭 뒤 등)에서도 다시 볼 수 있게 한다(r10 재검토, HIGH — 값에만 "
        "실리고 아무도 안 읽던 문제의 보완: app.html 이 이 op 도 함께 부른다)")
def 글자깨짐확인(key):
    """새문서 는 등록 시점 한 번만 잰다 — 사람이 편집기에서 고친 뒤(save)나 소프트
    재시도로 다른 문서가 채택된 뒤에도 검사하기() 가 **현재 등록된 내용**을 다시 잴
    수 있어야 한다. 이 op 은 그 재확인 창구다(사람이 고친 글은 검열하지 않는다는
    원칙은 그대로다 — save 경로 자체엔 안 걸고, 이건 사람이 "다시 검사"를 눌렀을 때만
    호출된다)."""
    r = 문서(key)
    if not r["ok"]:
        return r
    try:
        발견 = 자료뿌리.모듈("깨짐").검사(r["값"] or {})
    except Exception as e:
        return {"ok": False, "로그": f"글자 깨짐 검사를 못 돌렸습니다 — {type(e).__name__}: {e}"}
    if not 발견:
        return {"ok": True, "값": {"걸림": []}, "로그": "글자 깨짐 없음"}
    # 지어냈나검수 와 같은 결 — top-level ok 는 "이 검사를 통과했나"다(호출 자체의
    # 성패가 아니다). 걸린 게 있으면 ok=False.
    return {"ok": False, "값": {"걸림": 발견}, "로그": 자료뿌리.모듈("깨짐").메시지(발견)}


# ── r9(구현자 B) — 지어냄 교정 루프: 검토 → 교정지시 → 교정적용 ─────────────
# map-gen-path.md 4)가 지목한 자리(검사→모델 되먹임이 세 경로 다 빈다)를 메운다.
# 지어냈나.검토하기() 의 확장 검사(월표현·메타칸·출처·붙임·인용·보도시점)가 걸린
# 칸만 모아 교정.교정지시문() 으로 짧은 지시문을 짓고(교정지시), 모델이 돌려준
# 고침을 교정.교정적용() 으로 **서버가 다시 잰 허용경로 안에서만** 적용해 저장한다
# (교정적용). 모델은 두 작업 어느 쪽에서도 이 서버가 부르지 않는다 — 부르는 것은
# 호출자(BYOK 브라우저·플러그인 에이전트·서버 약한모델 요청내기) 몫이다.
# ── 지어낸 출처·확인 물음 배선('26-09-30 주관 판정 W1·W2) ─────────────────────────────────────────────────────
# W1 출처는 ○○로 둘 칸이 아니다 — 교정적용은 지어낸 출처의 키를 지우고(교정.py), 저장된 슬라이드 문서의 '○○'만 든 출처도
#    저장할 때 뺀다(교정적용은 저장을 거치므로 여기서 함께 닫힌다). 보도자료·1p 는 출처 키가 없고 본문 괄호에 적으므로
#    지우지 않고 확인할것에 '자료에 없는 출처' 한 줄로 올린다(판정은 지어냈나._출처_지어냄인가 하나 — 슬라이드·풀버전과 같은 자).
# W2 지어냈나.확인물음()(기준 없는 상대 연도를 셈한 연도)을 확인할것('확인 물음')에 싣는다 — 바로 완성 끝 보고와 웹앱 모두.
_출처자리표시뿐_RX = re.compile(r"[○〇△□◯●\s\-–—·.,()]*")      # 슬라이드v2._구조고침·교정._자리표시뿐_RX 와 같은 자
# fixup3 Z6 — 표지 '※ 자료:'·'※ 출처 -'·'Source:'도 출처로 읽고(wire_fixup2_verify §3-5: `출처:`만 봐 세 꼴을 놓쳤다), 출처 글 속 괄호
# ('현황('25.12월)')는 짝째 넘는다(예전엔 여는 괄호 뒤에서 잘려 '…현황('25.12월'로 보였다).
_본문출처_RX = re.compile(r"(?:출처\s*(?:[:：]|[-–]\s)|※\s*자료\s*[:：]|(?<![A-Za-z])[Ss]ource\s*[:：])\s*"
                       r"((?:[^()（）\[\]\n]|\([^()\n]{0,30}\)|（[^（）\n]{0,30}）){2,80}?)\s*(?=[)）\]\n]|\.\s|\.?$)")
# 풀버전의 출처는 4수준 항목 '※ 출처: …'다(조립기는 표.출처를 그리지 않는다 — wire_verify §3-5). 걸리면 확인할것 한 줄, 본문은 둔다(X4).
_본문출처_장르 = frozenset({"press", "press-release", "samples", "onepage", "fullreport"})   # doc.genre 는 조립기 값(press-release·onepage)이다(저장 길)
_인용레이아웃 = frozenset({"인용", "quote", "testimonial"})      # 지어냈나._인용레이아웃 과 같은 자(옛 판형 인용 장 — 출처 = 말한 사람)


def _슬라이드출처빈칸빼기(doc):
    """슬라이드 문서의 장(판형 v2 '장.N')·슬라이드(옛 판형 '슬라이드.N')에서 자리표시뿐인 출처('○○'·'-')의 키를 뺀다.
    뺀 것이 있으면 알림 한 줄, 없으면 None. 칸 속 부품의 '출처'(그림 생성·첨부, 인용 발언자)는 건드리지 않는다.
    옛 판형 '인용' 장의 출처는 말한 사람이라 빼지 않는다('26-09-30 주관 판정 X1 — 빼면 게이트가 인용 장을 막아 새문서·교정적용·저장이
    깨졌다, wire_verify §1). 말한 사람의 '○○'는 빈칸으로 확인할것에 오른다."""
    if not isinstance(doc, dict):
        return None
    뺀 = []
    for 목록키 in ("장", "슬라이드"):
        목록 = doc.get(목록키)
        if not isinstance(목록, list):
            continue
        for i, 장 in enumerate(목록):
            if 목록키 == "슬라이드" and isinstance(장, dict) and str(장.get("레이아웃") or "").strip() in _인용레이아웃:
                continue
            if isinstance(장, dict) and isinstance(장.get("출처"), str) and _출처자리표시뿐_RX.fullmatch(장["출처"]):
                뺀.append(f"{목록키}.{i}.출처")
                장.pop("출처")
    if not 뺀:
        return None
    return ("자리표시뿐인 출처를 뺐습니다(출처는 ○○로 두지 않습니다 — 자료가 밝힌 출처만 적습니다): "
            + ", ".join(뺀[:8]) + (f" 외 {len(뺀) - 8}곳" if len(뺀) > 8 else ""))


def _원문확인줄(doc, 장르, 원문, 출처=True):
    """확인할것에 더할 줄 [{종류, 어디, 내용}] — ① 지어냈나.확인물음()(W2) ② 보도자료·1p 본문 괄호 출처가 자료에 없는 것(W1).
    원문이 없거나 검사가 터지면 [](확인할것 모으기를 막지 않는다 — 실패는 stderr 에 남긴다).
    `출처`=False 면 ②(자료 밖 판정)를 싣지 않는다 — 원문이 자료의 앞 조각뿐일 때(fixup3 Z2)."""
    원문 = str(원문 or "")
    if not 원문.strip() or not isinstance(doc, dict):
        return []
    out = []
    try:
        검 = 자료뿌리.모듈("지어냈나")
        for 줄 in 검.확인물음(원문, doc) or []:
            out.append({"종류": "확인 물음", "어디": "", "내용": str(줄)})
        if 출처 and (장르 or doc.get("genre") or "samples") in _본문출처_장르:
            # 출처 하나에 줄 하나(X4) — 같은 지은 출처가 리드·본문 여러 자리에 있으면 첫 자리에 한 줄로 적고 자리 수를 붙인다
            본 = {}
            for 어디, 글 in 검.문서글(doc):
                for m in _본문출처_RX.finditer(re.sub(r"</?[A-Za-z][^>]*>", "", str(글 or ""))):
                    출 = m.group(1).strip().rstrip(".,;·")
                    열쇠 = re.sub(r"\s+", "", 출)
                    if not re.sub(r"[○〇\s]", "", 출):
                        continue
                    if 열쇠 in 본:
                        if 본[열쇠] is not None:
                            본[열쇠]["_곳"] += 1
                        continue
                    if 검._출처_지어냄인가(출, 원문):
                        줄 = {"종류": "지어냄 의심", "어디": 어디, "_출처": 출, "_곳": 1}
                        본[열쇠] = 줄
                        out.append(줄)
                    else:
                        본[열쇠] = None
            for 줄 in out:
                if "_출처" in 줄:
                    출, 곳 = 줄.pop("_출처"), 줄.pop("_곳")
                    # 출처가 여럿이고 일부만 지었으면('※ 출처: A(맞음), B(지음)') 지은 조각만 짚고 맞는 조각을 알린다(fixup3 — 예전엔 A 까지
                    # 칸 전체를 '자료에 없는 출처'로 적었다, wire_fixup2_verify §3-5). 가르는 자는 지어냈나.출처남길글 하나다.
                    남 = 검.출처남길글(출, 원문) or ""
                    지은 = [a for a, _ in 검._출처조각들(출) if 검._출처_지어냄인가(a, 원문)] if 남 else []
                    if 남 and 지은:
                        줄["내용"] = (f"자료에 없는 출처 '{', '.join(지은)[:40]}'" + (f"({곳}곳)" if 곳 > 1 else "")
                                    + f" — 본문의 출처는 지우지 않았습니다. 자료에 있는 '{남[:40]}'만 남겨 주세요")
                    else:
                        줄["내용"] = (f"자료에 없는 출처 '{출[:40]}'" + (f"({곳}곳)" if 곳 > 1 else "")
                                    + " — 본문의 출처는 지우지 않았습니다. 자료가 밝힌 출처가 아니면 빼거나 자료에 적힌 이름으로 고쳐 주세요")
    except Exception as e:
        print(f"[확인할것] 확인 물음·본문 출처 보기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    return out


def _맥락원문(doc):
    """웹앱이 새문서 때 문서에 심은 자료(doc._맥락.의도 — app.html _맥락만들기, 앞 4,000자). 없으면 ''."""
    맥 = doc.get("_맥락") if isinstance(doc, dict) else None
    t = str(맥.get("의도") or "") if isinstance(맥, dict) else ""
    return t if t.strip() else ""


# ── 웹앱 자료 원문 전체(fixup3 Z2, '26-10-01 주관 판정) ─────────────────────────────────────────────────────────────
# 웹앱 '확인할 것'이 doc._맥락.의도(앞 4,000자 조각)로 재어, 긴 자료에서는 4,000자 뒤의 맞는 출처·수·이름이 '자료에 없음'으로 떴고
# 확인해야 할 '내년' 물음은 빠졌다(wire_fixup2_verify §1-2 — 같은 화면의 지어냈나는 전문으로 재어 서로 어긋났다). 이제 **서버가 가진
# 전체 원문**으로 잰다: 이 세션에 자료가 온 입구(판정·설계·요청내기·지어냈나 … — 등록부 받는것에 '자료'·'원문'이 있는 작업)에서 받은
# 글을 세션 작업뿌리에 보관하고(세션 만료 때 등록부와 함께 지워진다), 문서의 _맥락 조각과 앞이 같은 것을 찾는다. 못 찾고 조각이 잘린
# 것이면 온전하지 않다고 알려 — 자료 밖 판정 줄을 싣지 않고 '일부만 대조' 한 줄을 알린다(헛걸림보다 침묵+알림).
_웹자료_상한 = 6
_웹자료_글상한 = 200_000
_일부대조말 = "자료가 길어 일부만 대조했습니다 — 자료 뒤쪽의 수치·이름·출처가 초안과 맞는지는 직접 봐 주세요"


def _웹자료길():
    return os.path.join(자료뿌리.작업뿌리(), "웹자료.json")


def _웹자료읽기():
    try:
        v = json.load(open(_웹자료길(), encoding="utf-8"))
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _웹자료적기(자료):
    """웹앱 입구에서 받은 자료 원문 전체를 세션에 보관한다(최근 6벌). 웹앱이 아니면 아무것도 하지 않는다."""
    if not os.environ.get("문서지능_웹앱"):
        return
    글 = str(_자료글(자료) or "").strip()
    if len(글) < 20:
        return
    길 = _웹자료길()
    os.makedirs(os.path.dirname(길), exist_ok=True)
    with 자료뿌리.빗장(길):
        목록 = [x for x in _웹자료읽기() if isinstance(x, dict) and x.get("원문") != 글[:_웹자료_글상한]]
        목록.append({"원문": 글[:_웹자료_글상한], "받은때": time.strftime("%Y-%m-%dT%H:%M:%S")})
        자료뿌리.원자json(길, 목록[-_웹자료_상한:], ensure_ascii=False)


def _웹글지문(글):
    return hashlib.sha1(re.sub(r"\s+", "", str(글 or "")).encode("utf-8"), usedforsecurity=False).hexdigest()[:20]


def _웹앞맞춤(doc):
    """세션 보관본 가운데 _맥락 조각과 앞이 같은 가장 최근 것 — 없으면 None."""
    맥 = _맥락원문(doc)
    if not 맥:
        return None
    민 = lambda s: re.sub(r"\s+", "", str(s or ""))
    머리 = 민(맥)[:-2] if len(민(맥)) > 8 else 민(맥)
    for x in reversed(_웹자료읽기()):
        글 = str((x or {}).get("원문") or "")
        if 글 and 민(글).startswith(머리):
            return 글
    return None


# fixup4 G5('26-10-01 주관 판정) — 문서 키에 **그 문서를 만들 때 쓴 원문**의 지문을 묶는다. 예전엔 확인할것을 부를 때마다 앞 4,000자가
# 같은 가장 최근 보관본을 골라, 같은 세션에서 뒤쪽만 다른 자료로 두 문서를 만들면 앞 문서가 뒤 자료로 재져 헛줄('자료에 없는 값 320')이
# 떴다(wire_fixup3_verify §3-2). 새문서(웹앱) 때 한 번 앞 맞춤으로 고른 원문을 묶고, 그 뒤로는 지문으로만 찾는다(못 찾으면 조각 — 알림).
# G4 — 그때 같은 앞을 가진 더 긴 보관본이 있으면(서버 예산 12,000자·BYOK 120,000자에 맞춰 app.html 이 뒤를 뗐다) 전체 길이를 함께 적는다.
def _웹원문묶기(key, doc):
    if not os.environ.get("문서지능_웹앱") or not key:
        return
    글 = _웹앞맞춤(doc)
    if not 글:
        return
    민 = lambda s: re.sub(r"\s+", "", str(s or ""))
    쓴 = 민(글)
    전체 = max([len(str(x.get("원문") or "")) for x in _웹자료읽기() if isinstance(x, dict)
               and len(민(x.get("원문"))) > len(쓴) and 민(x.get("원문")).startswith(쓴)] or [0])

    def 고치기(줄):
        줄["웹원문지문"] = _웹글지문(글)
        줄["웹원문길이"] = len(글)
        if 전체 > len(글):
            줄["웹자료전체길이"] = 전체
        else:
            줄.pop("웹자료전체길이", None)
    try:
        _검사자료고치기(key, 고치기)
    except Exception as e:
        print(f"[웹자료] 원문 묶기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)


def _자료잘림줄(doc, key=None):
    """G4 — 자료가 모델 예산을 넘어 앞 일부로 만들었으면 확인할것 한 줄(조용히 넘기지 않는다). 아니면 None."""
    맥 = doc.get("_맥락") if isinstance(doc, dict) and isinstance(doc.get("_맥락"), dict) else {}
    묶 = (_검사자료읽기().get(str(key)) or {}) if key else {}
    수 = lambda v: v if isinstance(v, int) and not isinstance(v, bool) else None
    원래 = 수(맥.get("원래길이")) or 수(묶.get("웹자료전체길이"))
    쓴 = 수(묶.get("웹원문길이")) or 수(맥.get("길이"))
    if not 원래 or not 쓴 or 원래 <= 쓴:
        return None
    return {"종류": "자료 일부", "어디": "",
            "내용": f"자료가 길어 앞 일부로 만들고 대조했습니다(전체 {원래:,}자 가운데 앞 {쓴:,}자) — 뒤쪽 내용은 초안에 빠졌을 수 있습니다"}


def _웹전체원문(doc, key=None):
    """(원문 글, 온전한가) — 웹앱 문서의 자료 원문. 문서 키에 묶은 원문(G5, 지문) → (묶음이 없는 옛 문서만) 세션 보관본 가운데 _맥락
    조각과 앞이 같은 것(가장 최근) → 잘리지 않은 _맥락 조각 → 잘린 조각(온전하지 않음). 맥락이 없으면 ("", True)."""
    맥 = _맥락원문(doc)
    if not 맥:
        return "", True
    지문 = ((_검사자료읽기().get(str(key)) or {}).get("웹원문지문") if key else None)
    if 지문:
        for x in reversed(_웹자료읽기()):
            글 = str((x or {}).get("원문") or "")
            if 글 and _웹글지문(글) == 지문:
                return 글, True
    else:
        글 = _웹앞맞춤(doc)
        if 글:
            return 글, True
    길이 = (doc.get("_맥락") or {}).get("길이") if isinstance(doc.get("_맥락"), dict) else None
    잘림 = (길이 > len(맥.strip())) if isinstance(길이, int) and not isinstance(길이, bool) else len(맥) >= 4000
    return 맥, not 잘림


# 웹앱 편집 화면 곁 '확인할 것' 칸과 플러그인 모두 쓴다 — fixup3 Z4-④('26-10-01 주관 판정)로 목록(스킬·MCP)에 공개했다
# (예전엔 숨김: 플러그인은 새문서·저장 응답의 확인할것으로만 받아 교정 뒤 판을 다시 모을 길이 없었다).
@등록("확인할것", ["key", "원문"], en="checklist",
    설명="지금 판에서 사람이 확인할 것 목록([{종류, 어디, 내용, 에이전트}])을 모은다 — 빈칸(○○)·자료에 없는 값·출처·말한 사람·"
        "상대 연도 물음·셈한 값 등. 자료 원문은 서버가 가진 것(이 문서가 처음 받은 원문, 웹앱은 세션에 온 자료 전문)을 먼저 쓴다. "
        "읽기만 한다(문서·검사 기록을 바꾸지 않는다). 내용은 사용자에게 그대로 보일 말, 에이전트(있을 때만)는 고칠 때 읽을 원래 말이다")
def 확인할것목록(key, 원문=""):
    """웹앱 편집 화면 곁 '확인할 것' 칸이 부른다('26-09-30 주관 판정 X2). 교정(fabfixapply)·편집 뒤의 **지금 판**으로 모은다 —
    새문서 응답의 확인할것은 교정 전 판이라 화면에 그대로 두면 이미 고친 것이 남는다."""
    r = 문서(key)
    if not r.get("ok"):
        return r
    doc = r.get("값") or {}
    장르 = str(doc.get("genre") or "samples")
    try:
        보관 = str((_검사자료읽기().get(str(key)) or {}).get("원문") or "")
    except Exception:
        보관 = ""
    try:        # reg13d 판정 D1 — 새문서가 보관한 작성 모델의 '확인요청'(규정)
        보관요청 = (_검사자료읽기().get(str(key)) or {}).get("규정확인요청") or []
    except Exception:
        보관요청 = []
    # 원문 — 처음 받은 원문 보관본(플러그인) → 서버가 가진 웹앱 자료 전문(fixup3 Z2 — _맥락 조각과 앞이 같은 것) → 받은 원문 →
    # 잘리지 않은 _맥락 조각. 잘린 조각뿐이면 온전하지 않다: 자료 밖 판정 줄(재기·검토하기·본문 출처·규정 자료 대조)을 싣지 않고 알린다.
    온전 = True
    if 보관:
        쓸 = 보관
    else:
        웹, 온전 = _웹전체원문(doc, key)
        받은 = str(_자료글(원문) or "") if 원문 else ""
        if 받은.strip() and not (웹 and 온전):
            쓸, 온전 = 받은, True
        else:
            쓸 = 웹
    값, 규정확인 = {}, []
    if 쓸.strip():
        검 = 자료뿌리.모듈("지어냈나")
        유형id = doc.get("purpose_type")
        시퀀스 = (부르기("시퀀스", {"유형id": 유형id}).get("값") or []) if 유형id else []
        if 온전:
            try:
                숫, 이 = 검.재기(쓸, doc, 시퀀스)
                값["지어냈나"] = {"값": {"수치": [{"어디": a, "값": b} for a, b, _ in 숫],
                                    "이름": [{"어디": a, "값": b} for a, b, _ in 이]}}
                확장 = 검.검토하기(쓸, doc, 시퀀스) or []
                if 확장:
                    값["지어냈나확장"] = {"ok": False, "걸림": 확장}
            except Exception as e:
                print(f"[확인할것] 지어냄 보기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
        if 장르 == "regulation":
            try:
                규정확인 = 자료뿌리.모듈("조문꼴").확인할것(doc, 원문=쓸 if 온전 else None, 확인요청=보관요청) or []
            except Exception as e:
                print(f"[확인할것] 규정 물음 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    elif 장르 == "regulation" and 보관요청:
        # 원문이 없어도 작성 모델이 스스로 적은 가정은 싣는다(D1 — 웹앱 new 는 원문을 보내지 않는다). reg13e 판정 E3 — 지금 판
        # (사람이 저장한 판)에서 확실히 사라진 조의 줄만 뺀다(reg13f 판정 F2, 위 확인할것() 길도 같은 거르기). reg13f 판정 F3 —
        # 빈칸 꼴 요청도 빼지 않는다: 아래 '빈칸(○○)' 줄과 같은 ○○를 말해도 느슨한 꼴 추정으로 합치거나 지우지 않는다(중복은 받아들인다).
        # reg13g 판정 H2 — 빼는 것은 조 칸이 '제N조' 한 꼴이고 지금 판에 그 번호의 조가 없으며 작성 당시 제목·첫 문장 지문도 어디에도
        # 없을 때뿐이다(다른 내규 인용·여러 조·제목 없는 조·「」·법 인용은 모두 남긴다 — 조문꼴._유효요청)
        try:
            규정확인 = 자료뿌리.모듈("조문꼴").확인요청줄(보관요청, doc=doc)
        except Exception as e:
            print(f"[확인할것] 확인요청 옮기기 실패(건너뜀): {type(e).__name__}: {e}", file=sys.stderr)
    목록 = _확인할것모으기(doc, 장르, [], 규정확인, [], [], 값, key=key, 건너뜀=not 쓸.strip(),
                      원문확인=_원문확인줄(doc, 장르, 쓸, 출처=온전))
    for x in 목록:
        if x.get("종류") == "지어냈나 건너뜀":      # 도구 이름(지어냈나) 대신 사람 말로
            x["내용"] = "자료 원문이 없어 수치·이름이 자료와 맞는지 재지 못했습니다 — 직접 봐 주세요"
            x.pop("에이전트", None)
    if 쓸.strip() and not 온전:
        목록.insert(0, {"종류": "자료 일부", "어디": "", "내용": _일부대조말})
    _잘림 = _자료잘림줄(doc, key) if not 보관 else None     # G4 — 예산에 맞춰 앞 일부로 만든 자료(조용히 넘기지 않는다)
    if _잘림:
        목록.insert(0, _잘림)
    if os.environ.get("문서지능_웹앱"):
        for x in 목록:
            x.pop("에이전트", None)            # 웹앱 화면은 사람만 본다 — 에이전트용 말은 싣지 않는다(Z5)
    return {"ok": True, "값": 목록, "로그": f"확인할 것 {len(목록)}건"}


def _장르게이트확인(doc):
    """이 문서를 저장하기 **전에** 장르 조립기의 gate_check(하드 위반)을 미리 돌려 본다
    (r9 검토자 발견, regression·loop-channels HIGH — 교정적용 전용 안전망).

    apply_edit_any.py 는 정본을 먼저 쓰고 재조립이 실패하면 그제서야 실패를 알린다 —
    그 사이 등록부는 이미 게이트 위반 상태로 남는다(재현: e2e_gate3.py·probe3 F. 시행문
    본문에서 '11월'만 지우자(빈 글 → 문자열 칸 ○○) 서술어 완결 게이트가 깨졌는데,
    등록부 본문은 이미 ['…', '○○']로 바뀐 채 저장됐고 HTML 은 옛 '11월'을 그대로 보여
    줬다). 저장 전에 미리 재서 위반이 있으면 아예 쓰지 않는다 — 등록부가 조립 안 되는
    상태로 남는 일 자체를 없앤다. gate_check 가 없는 장르(1p·fullreport 는 하드 게이트가
    없다, build/genres.py 확인)는 통과로 본다."""
    genre = doc.get("genre") if isinstance(doc, dict) else None
    if not genre:
        return []
    if genre == "slides":
        # 슬라이드 v2(부품 트리)는 옛 판형 gate_check(표지·슬라이드 키)로 재면 늘 '표지.제목이 없다'로 선다
        # ('26-09-29 E2E §4-B 재현: 교정적용이 v2 덱을 매번 거절). v2 면 새문서와 같은 v2 hard 규칙으로 잰다.
        try:
            _v2 = 자료뿌리.모듈("슬라이드v2")
            if _v2.v2인가(doc):
                import copy as _copy
                return [str(x) for x in (_v2.검사(_copy.deepcopy(doc))[0] or [])]
        except Exception as e:
            return [f"v2 게이트 사전확인이 실패했습니다({type(e).__name__}) — 안전하게 거절합니다"]
    try:
        genres = 자료뿌리.모듈("genres")
        표 = {g["장르"]: g["조립기"] for g in genres.등록부()}
        조립기 = 표.get(genre)
        if not 조립기:
            return []
        모듈이름 = 조립기[:-3] if 조립기.endswith(".py") else 조립기
        모듈 = 자료뿌리.모듈(모듈이름)
        gate = getattr(모듈, "gate_check", None)
        if gate is None:
            return []
        옛슬라이드 = genre == "slides" and isinstance(doc.get("슬라이드"), list)
        if 옛슬라이드:
            # fixup3 Z3('26-10-01 주관 판정) — 조립기는 게이트 전에 모양 정규화 5종(레이아웃 별칭 풀기 포함)을 돌린다. 등록부에는
            # 별칭이 원래 이름대로 남으므로(quote·testimonial·본체) 정규화 전 문서를 재면 ① 인용 별칭 장은 '인용' 규칙을 안 타 말한
            # 사람을 뺀 저장이 통과하고 ② 본체→본문 이 글머리만 비율에 안 잡혀 쓰기 뒤 조립이 깨졌다(wire_fixup2_verify §1-1) ③ 옛
            # 위반을 빼지 않는 교정적용은 '카탈로그에 없다'로 늘 거절됐다(§3-7). 사본에 조립기와 같은 차례로 돌린 뒤 잰다.
            import copy as _copy
            doc = _copy.deepcopy(doc)
            for _정 in ("_표정규화", "_레이아웃정규화", "_도식타입정규화", "_큰숫자정규화", "_픽토그램정규화"):
                _f = getattr(모듈, _정, None)
                if callable(_f):
                    _f(doc)
        위반 = [str(x) for x in (gate(doc) or [])]
        # 옛 판형 슬라이드는 조립기가 gate_check 밖에서 덱 전체 '글머리만 장 비율 > 0.50'도 hard 로 막는다 — 여기서 같이 재야
        # 쓰기 전 검사가 '다 통과'라고 보고 정본을 쓴 뒤 조립에서 깨지는 일이 없다('26-09-30 X1: 인용 장을 요지 장으로 바꾼 교정이
        # 저장된 뒤 조립이 이 규칙에 막혔다 — 실측). 문구는 조립기와 같다.
        if 옛슬라이드 and hasattr(모듈, "_소프트지표"):
            try:
                _비 = 모듈._소프트지표(doc)[1].get("글머리만", 0.0)
                if _비 > 0.50:
                    위반.append(f"글머리만 장 비율 {_비:.2f} — 0.50 초과(hard). 장마다 도식·표·큰숫자·픽토그램 중 하나를 넣어라")
            except Exception:
                pass
        # 조립기의 셋째 hard(렌더된 본체가 빈 장)도 쓰기 전에 잰다 — 앞 두 갈래가 통과했을 때만(조립기와 같은 차례)
        if 옛슬라이드 and not 위반 and callable(getattr(모듈, "build", None)) and callable(getattr(모듈, "_렌더본체빈장", None)):
            try:
                for _번, _lo in 모듈._렌더본체빈장(genres.판찍기(모듈.build(doc))) or []:
                    위반.append(f"슬라이드.{_번}({_lo}): 렌더된 본체가 비어 있다 — 그 레이아웃의 정본 키에 내용을 넣어라")
            except Exception as _e:
                위반.append(f"이 구조를 렌더하지 못했다({type(_e).__name__}) — 조립기가 받는 모양으로 고쳐라")
        return 위반
    except Exception as e:
        return [f"게이트 사전확인이 실패했습니다({type(e).__name__}) — 안전하게 거절합니다"]


@등록("교정지시", ["key", "원문"], 읽기=False, en="fabfix",
    설명="지어냄 확장 검사(월표현·메타칸·출처·붙임·인용·보도시점)로 걸린 칸만 모아 "
        "모델에게 줄 교정 지시문을 만든다 — 모델은 여기서 부르지 않는다. 걸린 칸이 "
        "없으면 값.걸림 이 빈 배열이고 지시문도 빈 문자열이다. 위치가 모호해 자동으로 "
        "못 고치는 자리(1p '표 머리'·'표 칸' 등)는 지시문·허용경로에서 빼고 값.사람확인 "
        "으로 따로 돌려준다")
def 교정지시(key, 원문=""):
    r = 문서(key)
    if not r.get("ok"):
        return r
    doc = r.get("값") or {}
    원문 = str(원문 or "")
    if not 원문.strip():
        return {"ok": False, "로그": "자료 원문이 없어 교정 지시를 만들 수 없습니다"}
    검 = 자료뿌리.모듈("지어냈나")
    유형id = doc.get("purpose_type")
    시퀀스 = (부르기("시퀀스", {"유형id": 유형id}).get("값") or []) if 유형id else []
    걸림 = 검.검토하기(원문, doc, 시퀀스)
    if not 걸림:
        return {"ok": True, "값": {"걸림": [], "지시문": "", "허용경로": [], "사람확인": []},
                "로그": "확장 검사에 걸린 칸이 없습니다"}
    for g in 걸림:          # 화면에 보일 말(X2) — '설명'은 모델용 지시라 사람에게는 이 말을 보인다(app.html 검사 단계)
        if isinstance(g, dict):
            g["사람말"] = _확장사람말(g)
    교정 = 자료뿌리.모듈("교정")
    # r9 검토자 발견(loop-channels LOW) — _경로풀기 로 애초에 못 푸는 자리(1p '표 머리'·
    # '표 칸')는 지시문·허용경로에서 뺀다. 실려도 교정적용 이 늘 거절하니 모델의 시도만
    # 헛수고가 된다 — 사람이 볼 목록으로 따로 돌려준다.
    풀리는것 = [g for g in 걸림 if 교정.풀수있나(doc, g["어디"])]
    사람확인 = [g for g in 걸림 if g not in 풀리는것]
    if not 풀리는것:
        return {"ok": True, "값": {"걸림": 걸림, "지시문": "", "허용경로": [], "사람확인": 사람확인},
                "로그": f"확장 검사에 {len(걸림)}건 걸렸지만 위치가 모호해 자동으로 못 고치는 "
                       "자리뿐입니다 — 사람이 직접 확인해 주십시오"}
    지시문 = 교정.교정지시문(doc, 풀리는것, 원문)
    # 몇 건이 걸렸는지만 세션 기록에 남긴다(지어냈나검수 와 같은 결 — 값 자체는 안 적는다).
    자료뿌리.규칙적기("교정지시", {"걸림": len(걸림)})
    return {"ok": True, "값": {"걸림": 걸림, "지시문": 지시문,
                              "허용경로": [g["어디"] for g in 풀리는것],
                              "사람확인": 사람확인},
            "로그": f"확장 검사에 {len(걸림)}건 걸려 교정 지시문을 만들었습니다"
                  + (f" · 자동으로 못 고치는 자리 {len(사람확인)}건은 사람 확인이 필요합니다"
                     if 사람확인 else "")}


@등록("교정적용", ["key", "고침", "원문"], 읽기=False, 승인필요=True, en="fabfixapply",
    설명="교정지시로 받은 고침([{경로,글}])을 적용한다 — 허용경로는 클라이언트가 준 "
        "값을 믿지 않고 서버가 지금 문서·원문으로 다시 잰다. 걸림이 줄지 않았거나 "
        "본문이 크게 줄면(내용을 지워 피한 것) 적용하지 않는다")
def 교정적용(key, 고침=None, 원문=""):
    # r9 검토자 발견(loop-channels·regression MEDIUM) — 이 작업에 승인필요=True 를 달아
    # 두어야 저장과 같은 되묻기 관문(_되묻기관문)을 탄다. 예전엔 이 플래그가 없어서, 미결
    # 어긋남이 있어 저장(save) 자체는 부르기() 관문이 막는 상태에서도 교정적용은 그 관문을
    # 우회해 저장·재조립까지 마쳐 버렸다(재현: e2e_gate2.py (A)).
    r = 문서(key)
    if not r.get("ok"):
        return r
    doc = r.get("값") or {}
    원문 = str(원문 or "")
    if not 원문.strip():
        return {"ok": False, "로그": "자료 원문이 없어 허용경로를 다시 잴 수 없습니다"}
    검 = 자료뿌리.모듈("지어냈나")
    유형id = doc.get("purpose_type")
    시퀀스 = (부르기("시퀀스", {"유형id": 유형id}).get("값") or []) if 유형id else []
    걸림전 = 검.검토하기(원문, doc, 시퀀스)
    if not 걸림전:
        return {"ok": False, "로그": "지금 이 문서엔 확장 검사에 걸린 칸이 없어 적용할 것이 없습니다"}
    허용경로 = {g["어디"] for g in 걸림전}
    종류표 = {g["어디"]: g["종류"] for g in 걸림전}
    # r9 검토자 발견(loop-channels·regression HIGH) — 재기()의 숫자·이름 걸림은 검토하기()
    # 걸림과 종류가 달라 여기서만 따로 잰다(적용 전/후를 비교해 **새로** 생긴 것만 본다).
    재기전_숫, 재기전_이 = 검.재기(원문, doc, 시퀀스)
    교정 = 자료뿌리.모듈("교정")
    # 고칠꼴(키지움 — 지어낸 출처, '26-09-30 주관 판정 W1)도 서버가 다시 잰 걸림에서 넘긴다: 모델이 빈 글이든 '○○'든 보내면 키를 지운다
    고칠꼴표 = {g["어디"]: g["고칠꼴"] for g in 걸림전 if g.get("고칠꼴")}
    # 출처 조각 가운데 맞는 것(남길글, X3) — 키를 지우는 대신 그 글로 둔다
    남길글표 = {g["어디"]: g["남길글"] for g in 걸림전 if g.get("남길글")}
    새doc, 적용수, 거절 = 교정.교정적용(doc, 고침 or [], 허용경로, 종류표=종류표, 고칠꼴표=고칠꼴표, 남길글표=남길글표)
    if 적용수 == 0:
        return {"ok": False, "로그": "적용된 고침이 없습니다 — 경로가 이번 걸림 밖이거나 "
                "문서에서 못 찾았습니다", "값": {"거절": 거절}}
    # 출처 칸은 한 가지만 한다(X3) — 모델이 키지움 칸에 다른 지은 이름을 보내 그 칸이 다시 지은 출처로 걸리면, 묶음 전체를
    # 거절하지 않고 서버가 그 키를 지운다(맞는 조각이 있으면 그 조각만 남긴다). 모델이 보낸 칸만 — 안 보낸 칸은 건드리지 않는다.
    _보낸 = {str(x.get("경로") or "").strip() for x in 교정.고침목록(고침 or []) if isinstance(x, dict)}
    _다시 = [g for g in 검.검토하기(원문, 새doc, 시퀀스)
            if g.get("고칠꼴") == "키지움" and g.get("어디") in _보낸 and 고칠꼴표.get(g.get("어디")) == "키지움"]
    if _다시:
        새doc, _n, _ = 교정.교정적용(새doc, [{"경로": g["어디"], "글": ""} for g in _다시], {g["어디"] for g in _다시},
                               고칠꼴표={g["어디"]: "키지움" for g in _다시},
                               남길글표={g["어디"]: g["남길글"] for g in _다시 if g.get("남길글")})
    # 지시대로 지운 출처 칸(키지움)은 '내용을 지워 피한 것'으로 세지 않는다 — 두 쪽 다 그 칸을 빼고 센다
    이전글자수 = sum(len(b) for a, b in 검.문서글(doc) if a not in 고칠꼴표)
    이후글자수 = sum(len(b) for a, b in 검.문서글(새doc) if a not in 고칠꼴표)
    if 이전글자수 > 0 and 이후글자수 < 이전글자수 * 0.7:
        return {"ok": False, "로그": f"고침을 적용하면 본문이 크게 줄어듭니다"
                f"({이전글자수}자 → {이후글자수}자) — 내용을 지워서 피한 것으로 보여 "
                "적용하지 않았습니다.", "값": {"거절": 거절}}
    걸림후 = 검.검토하기(원문, 새doc, 시퀀스)
    if len(걸림후) >= len(걸림전):
        return {"ok": False, "로그": f"고침을 적용해도 걸림이 줄지 않습니다"
                f"({len(걸림전)}건 → {len(걸림후)}건) — 적용하지 않았습니다.",
                "값": {"거절": 거절}}
    # r9 검토자 발견(loop-channels·regression MEDIUM) — 걸림 건수가 순감이어도, 고친
    # 자리가 **새 숫자·이름**(재기() 대상)을 지어 넣었으면 받지 않는다(재현: probe1 P4 —
    # 월표현 하나를 고치며 '3회에 걸쳐 김철수 강사가'처럼 새 수치·이름을 끼워 넣었다).
    재기후_숫, 재기후_이 = 검.재기(원문, 새doc, 시퀀스)
    새수치 = {v for _, v, _ in 재기후_숫} - {v for _, v, _ in 재기전_숫}
    새이름 = {w for _, w, _ in 재기후_이} - {w for _, w, _ in 재기전_이}
    if 새수치 or 새이름:
        return {"ok": False, "로그": f"고침이 자료에 없는 새 숫자·이름을 지어낸 것으로 "
                f"보입니다({sorted(새수치 | 새이름)[:5]}) — 적용하지 않았습니다.",
                "값": {"거절": 거절}}
    # r9 검토자 발견(regression·loop-channels HIGH) — 저장 전에 장르 하드 게이트를 미리
    # 재서, 위반이 새로 생기면 아예 쓰지 않는다(위 _장르게이트확인 참고).
    게이트위반 = _장르게이트확인(새doc)
    if 게이트위반:
        return {"ok": False, "로그": "고침을 적용하면 조판 하드 게이트에 걸립니다 — "
                + " / ".join(게이트위반[:5]) + " · 적용하지 않았습니다.",
                "값": {"거절": 거절, "게이트위반": 게이트위반}}
    새doc["_수정시각"] = doc.get("_수정시각")     # 낙관적 잠금 표 — 손대지 않고 그대로 넘긴다
    # r9 검토자 발견(loop-channels LOW) — 판없이 를 안 주면 판_간격초 안에 사람이 방금
    # 저장했을 때(자동저장 코앞) 이 자동 교정이 그 슬롯을 못 받아 되돌릴 판이 안 생긴다.
    # 자동 교정은 사람 저장과 분리된 별개 사건이니 판을 강제로 남긴다.
    저장결과 = 저장({"doc": 새doc, "key": key,
                  "ops": [{"action": "지어냄 교정"}]}, 판없이=False)   # 판 사유 라벨(조작요약() 이 그대로 편다)
    if not 저장결과.get("ok"):
        return {"ok": False, "로그": "고쳐서 저장하려 했지만 실패했습니다 — " + (저장결과.get("로그") or ""),
                "값": {"거절": 거절}}
    자료뿌리.규칙적기("교정적용", {"적용": 적용수, "거절": len(거절),
                              "걸림전": len(걸림전), "걸림후": len(걸림후)})
    return {"ok": True, "값": {"적용": 적용수, "거절": 거절, "걸림전": len(걸림전),
                              "남은걸림": len(걸림후), "수정시각": 저장결과.get("수정시각")},
            "로그": f"{적용수}건 고쳐 저장했습니다(걸림 {len(걸림전)}건 → {len(걸림후)}건)"
                  + (f" · 거절 {len(거절)}건" if 거절 else "")
                  + ("" if os.environ.get("문서지능_웹앱") else
                     "\n▸ 고친 판은 검사 기록이 비었습니다 — 내보내기 전에 저장(save, 검사 true·원문)이나 "
                     "문체검사·조판게이트·지어냈나로 다시 재세요.")}


# ── WP-S5: 관리자 면 (출시계획 3-4) ──────────────────────────────────────
# 다섯 기능(LLM 설정 · 세션 무반응 시간 · 원장 후보 검토 · 관측 · 정본 수정 없음)을
# **작업으로** 낸다 — 관리자 작업도 등록부에서 파생한다(이름별 분기 금지, 손목록
# 금지: 구현계획.md 규칙 2). 열쇠 게이트는 serve.py 가 `관리자` 플래그를 보고 걸고,
# `목록()` 이 그 플래그로 걸러 스킬·MCP·공개 목록에는 안 낸다(관리자 면 웹앱 문 하나).
#
# ★ LLM 키 두 종류를 헷갈리지 마라 (보안 하드 기준, WP-S5) ★
#   · **서버 관리자 키**(여기): 관리자가 설정하는 LLM 키다. 서버가 사용자 대신 모델을
#     부를 때(출시계획 1-3 ②, "키가 없거나 서버 제공에 동의") 쓸 값이라 `설정.json`
#     (기본 뿌리, 서버 파일)에 **평문으로 저장한다**. 단 밖(로그·HTTP 응답·화면)으로는
#     **끝 4자리만**(`_llm키가리기`) 나간다 — 평문은 파일 안에만 있다.
#   · **세션 사용자 키**(WP-S2③, 여기 아님): 사용자가 브라우저에 넣는 키다. **절대
#     서버에 저장도, 전송도 안 한다** — 브라우저가 api.anthropic.com 을 직접 부를 때만
#     쓰고(app.html `모델부르기`, `anthropic-dangerous-direct-browser-access`), 보관은
#     sessionStorage 다. 서버는 이 키를 아예 못 본다.
#   성질이 반대다: 하나는 서버가 관리하는 공용 키(저장 O·마스킹), 하나는 사용자
#   개인 키(저장 X). 이 둘을 한 저장소에 섞으면 사용자 키가 새는 사고가 난다.
#
# 아직 안 한 것(정직히 적는다): 서버측 모델 호출 경로는 이 WP 에서 배선하지 않았다.
# 그래서 세션당상한·하루총량은 지금은 **설정 값으로만** 저장된다(그 경로가 생기면
# 읽어 쓴다). 실제 토큰 소비 계량은 서버가 모델을 부를 때 생긴다 — 지금은 없다.

_설정잠금이름 = "설정"


def _설정읽기():
    """설정.json 을 읽는다. 없거나 깨졌으면 빈 dict. (서버가 멈추면 안 되므로 안 죽는다)"""
    try:
        with open(자료뿌리.설정길(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except (ValueError, OSError):
        # 값이 있는데 못 읽은 것은 관리자 실수다 — 화면이 '설정을 못 읽었다'를 보여
        # 주도록 표시를 남기되(아래 관리자설정보기), 여기서 죽지는 않는다.
        return {"_깨짐": True}


def _llm키가리기(v):
    """LLM 키를 밖으로 낼 때 **끝 4자리만** 남긴다(예: `sk-…wxyz`). (WP-S5 보안)

    설정.json 안에는 평문이 있어도, 응답·화면·로그로는 이 마스킹만 나간다. 짧은 값도
    통째로 흘리지 않는다 — 끝 두 자리만 남긴다.
    """
    v = str(v or "")
    if not v:
        return ""
    if len(v) <= 8:
        return "…" + v[-2:]
    return v[:3] + "…" + v[-4:]


def _양의정수(v, 기본):
    try:
        n = int(v)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


# ── 정책 토큰 원장 (WP-S6 · 플러그인 위임 채널의 열쇠) ─────────────────────────
# 왜 있나 — A1 은 두 문으로 정책작업(판정·장르·시퀀스·프롬프트조립)을 받는다. 익명 웹앱
# 문은 공개(봇차단이 따로 지킨다)지만, 플러그인 위임 문(_원격, 서버-투-서버)은 **발급받은
# 토큰**으로만 연다. 관리자가 설치요청 때 하나씩 발급하고, 활성/비활성으로 끊고, 이상사용
# 이면 자동 잠근다. 저장 원칙 — 원문 토큰은 **발급 순간 1회만** 밖으로 나가고, 원장엔
# **SHA-256 해시만** 둔다(원장 파일이 새도 토큰이 안 샌다, API 키 방식). 검증은 들어온
# 토큰을 해시로 바꿔 사전에서 찾는다(원문 추론 불가라 dict 조회 타이밍은 안전). 원장은
# 설정.json 과 같은 **기본 뿌리**에 살고(세션이 지워져도 안 지워진다), 빗장으로 잠근다.
def _토큰원장길():
    return os.path.join(자료뿌리.기본뿌리(), "토큰원장.json")


def _토큰해시(원문):
    return hashlib.sha256(("문서지능정책토큰\x00" + str(원문)).encode("utf-8")).hexdigest()


def _토큰원장읽기():
    try:
        with open(_토큰원장길(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except (ValueError, OSError):
        return {"_깨짐": True}


def _토큰원장쓰기(d):
    길 = _토큰원장길()
    tmp = 길 + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, 길)


def _불변환(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "on", "yes", "y", "켜", "켜기", "활성")


def 정책토큰검증(원문):
    """들어온 토큰이 유효+활성인가 — **읽기전용**(빗장 없이, 초 단위 낡음 허용). 요청마다
    부르는 자리라 잠그지 않는다. 돌려주는 것: {ok, 지문, 해시, 사유}. 지문은 앞 12자만,
    해시(전체)는 serve 가 사용/잠금 기록에 쓰라고 넘기는 **인프로세스** 값 — 클라엔 안 나간다."""
    원문 = (원문 or "").strip()
    if not 원문:
        return {"ok": False, "사유": "토큰 없음"}
    d = _토큰원장읽기()
    if d.get("_깨짐"):
        return {"ok": False, "사유": "원장 손상"}
    h = _토큰해시(원문)
    rec = d.get(h)
    if not isinstance(rec, dict):
        return {"ok": False, "사유": "모르는 토큰", "지문": h[:12]}
    if not rec.get("활성", False):
        return {"ok": False, "사유": "비활성 토큰", "지문": h[:12], "해시": h}
    return {"ok": True, "지문": h[:12], "해시": h, "이름": rec.get("이름", "")}


def 정책토큰사용(해시, 지금=None):
    """이 토큰이 방금 쓰였음을 원장에 남긴다(누적+1, 마지막=지금). serve.py 가 토큰별로
    **드물게**(≤분당 1회) 부르는 자리 — 요청마다 부르면 빗장이 병목이 된다. 해시(전체)로
    정확히 찾는다(지문 접두어 충돌 회피)."""
    지금 = 지금 or time.strftime("%Y-%m-%d %H:%M:%S")
    with 자료뿌리.빗장(_토큰원장길()):
        d = _토큰원장읽기()
        rec = d.get(해시) if not d.get("_깨짐") else None
        if isinstance(rec, dict):
            rec["누적"] = int(rec.get("누적") or 0) + 1
            rec["마지막"] = 지금
            _토큰원장쓰기(d)


def 정책토큰잠금(해시, 사유="이상사용 자동잠금", 지금=None):
    """이상사용으로 토큰을 자동 비활성한다(serve.py 가 부른다). 해시로 정확히 찾아 활성=False."""
    지금 = 지금 or time.strftime("%Y-%m-%d %H:%M:%S")
    with 자료뿌리.빗장(_토큰원장길()):
        d = _토큰원장읽기()
        rec = d.get(해시) if not d.get("_깨짐") else None
        if isinstance(rec, dict):
            rec["활성"] = False
            rec["이상"] = int(rec.get("이상") or 0) + 1
            rec["잠금사유"] = str(사유)
            rec["잠금시각"] = 지금
            _토큰원장쓰기(d)


def _토큰생성(이름, 메모, 자동=False):
    """토큰 하나를 만들어 원장에 적는다(즉시 활성). (원문, None) 또는 (None, 오류dict) 반환.
    발급(관리자 수동)·등록(설치 자동) 두 길이 공유한다 — 원장 형태를 한 곳에 둔다."""
    원문 = secrets.token_urlsafe(24)
    h = _토큰해시(원문)
    지금 = time.strftime("%Y-%m-%d %H:%M:%S")
    with 자료뿌리.빗장(_토큰원장길()):
        d = _토큰원장읽기()
        if d.get("_깨짐"):
            return None, {"ok": False, "로그": "토큰원장.json 이 깨져 있어 발급을 멈춥니다"}
        d[h] = {"이름": str(이름 or ""), "메모": str(메모 or ""), "활성": True,
                "발급": 지금, "누적": 0, "마지막": None, "이상": 0, "자동": bool(자동)}
        _토큰원장쓰기(d)
    return 원문, None


@등록("토큰발급", ["이름", "메모"], 읽기=False, en="tokenissue", 관리자=True,
    설명="정책 토큰을 손으로 하나 발급한다(특정 설치자 지정용 — 보통은 설치 시 자동 등록). 원문은 응답에 딱 한 번만")
def 토큰발급(이름="", 메모=""):
    원문, 오류 = _토큰생성(이름, 메모, 자동=False)
    if 오류:
        return 오류
    return {"ok": True,
            "값": {"토큰": 원문, "지문": _토큰해시(원문)[:12], "이름": str(이름 or "")},
            "로그": "이 토큰은 지금 한 번만 보입니다 — 설치자에게 안전히 전달하세요"}


@등록("토큰등록", ["라벨"], 읽기=False, en="enroll", 공개발급=True,
    설명="설치본이 자기 정책 토큰을 자동으로 받아 간다(설치 시 1회, 즉시 활성). 원문은 응답에 딱 한 번만")
def 토큰등록(라벨=""):
    """플러그인 설치 부트스트랩이 부른다 — 토큰이 없으면 하나 받아 정책서버토큰.conf 에 적는다.
    발급은 자동·즉시활성(사장님 결정: 무마찰). 남용은 IP당 발급상한(serve.py 공개발급 게이트)·
    토큰별 분당상한·이상 자동잠금·관리자 비활성으로 막는다. 관리자 열쇠 없이 열린 문이지만
    웹앱 익명 문과 같은 수준의 공개다(토큰이 더 주는 접근은 없다 — 통치·귀속용). 원장엔 해시만."""
    라벨 = str(라벨 or "")[:120]
    원문, 오류 = _토큰생성(라벨 or "자동등록", "설치 자동등록(enroll)", 자동=True)
    if 오류:
        return 오류
    return {"ok": True, "값": {"토큰": 원문, "지문": _토큰해시(원문)[:12]},
            "로그": "설치 토큰을 발급했습니다"}


@등록("토큰목록", 읽기=True, en="tokens", 관리자=True,
    설명="발급된 정책 토큰들 — 지문·이름·활성·발급·누적·마지막·이상만(원문·해시전체는 안 낸다)")
def 토큰목록():
    d = _토큰원장읽기()
    if d.get("_깨짐"):
        return {"ok": False, "로그": "토큰원장.json 이 깨져 있습니다"}
    목 = []
    for h, rec in d.items():
        if not isinstance(rec, dict):
            continue
        목.append({"지문": h[:12], "이름": rec.get("이름", ""), "활성": bool(rec.get("활성")),
                  "발급": rec.get("발급"), "누적": int(rec.get("누적") or 0),
                  "마지막": rec.get("마지막"), "이상": int(rec.get("이상") or 0),
                  "메모": rec.get("메모", ""), "잠금사유": rec.get("잠금사유")})
    목.sort(key=lambda x: (x["발급"] or ""), reverse=True)
    return {"ok": True, "값": 목}


@등록("토큰활성", ["지문", "켜기"], 읽기=False, en="tokenset", 관리자=True,
    설명="정책 토큰을 활성/비활성한다 — 지문(앞자리)으로 지목. 비활성하면 그 토큰의 위임이 즉시 막힌다")
def 토큰활성(지문="", 켜기=None):
    지문 = (지문 or "").strip()
    if not 지문:
        return {"ok": False, "로그": "지문(토큰 앞자리)이 필요합니다"}
    if 켜기 is None or str(켜기).strip() == "":
        return {"ok": False, "로그": "켜기(true/false)를 주세요"}
    켬 = _불변환(켜기)
    with 자료뿌리.빗장(_토큰원장길()):
        d = _토큰원장읽기()
        if d.get("_깨짐"):
            return {"ok": False, "로그": "토큰원장.json 이 깨져 있습니다"}
        맞은 = [h for h in d if isinstance(d[h], dict) and h.startswith(지문)]
        if not 맞은:
            return {"ok": False, "로그": f"지문 '{지문}' 에 맞는 토큰이 없습니다"}
        if len(맞은) > 1:
            return {"ok": False, "로그": f"지문 '{지문}' 이 여러 토큰에 걸립니다 — 더 길게 주세요"}
        d[맞은[0]]["활성"] = 켬
        if 켬:
            d[맞은[0]].pop("잠금사유", None)
            d[맞은[0]].pop("잠금시각", None)
        _토큰원장쓰기(d)
    return {"ok": True, "값": {"지문": 맞은[0][:12], "활성": 켬}}


@등록("관리자설정보기", 읽기=True, en="admincfg", 관리자=True,
    설명="관리자 설정(LLM·세션 무반응 시간)을 읽는다 — LLM 키는 마스킹해서 낸다")
def 관리자설정보기():
    """설정.json 을 읽어 화면에 보여 준다. **LLM 키는 절대 평문으로 안 낸다.**

    무반응 시간은 세션.만료초() 가 실제로 쓰는 값과 같은 것을 보여 준다(top-level
    '세션만료초') — 관리자가 고치면 그 함수가 바로 읽는다(출시계획 3-4 ②).
    """
    세션 = 자료뿌리.모듈("세션")
    d = _설정읽기()
    llm = d.get("llm") if isinstance(d.get("llm"), dict) else {}
    return {"ok": True, "값": {
        "세션만료초": d.get("세션만료초"),
        "실효만료초": 세션.만료초(),          # 설정이 비었거나 이상하면 기본값(600)이 실효값
        "기본만료초": 세션.기본만료초,
        "llm": {
            # 키는 **가린 것만** 내보낸다(평문 금지). 있는지 없는지와 끝 4자리만.
            "키있음": bool(llm.get("키")),
            "키가림": _llm키가리기(llm.get("키")),
            "제공자": llm.get("제공자") or "openai호환",   # openai호환·anthropic·ollama·custom
            "베이스": llm.get("베이스") or "",              # 서버 주소(비면 제공자 기본값). 키 아님 — 평문 OK
            "모델": llm.get("모델") or "",
            "표시": llm.get("표시") or "",                  # 키 없이 진행 시 탑바 안내 문구(관리자가 정함)
            "세션당상한": llm.get("세션당상한"),
            "하루총량": llm.get("하루총량"),
            "장르토큰": llm.get("장르토큰") if isinstance(llm.get("장르토큰"), dict) else {},
            "온도": llm.get("온도"),           # 없으면 None → openai호환은 환경변수·0.3, anthropic 은 안 실음(_LLM온도)
        },
        "설정깨짐": bool(d.get("_깨짐")),
        "설정경로있음": os.path.exists(자료뿌리.설정길()),
    }}


@등록("관리자설정저장",
    ["세션만료초", "llm키", "모델", "세션당상한", "하루총량", "제공자", "베이스", "표시", "장르토큰", "온도"],
    읽기=False, en="admincfgset", 관리자=True,
    설명="관리자 설정 저장 — LLM 제공자·서버·키·모델·상한(장르별 max_tokens 포함)·온도(0~2)·안내문구와 세션 무반응 시간. 응답에도 키는 마스킹")
def 관리자설정저장(세션만료초=None, llm키=None, 모델=None, 세션당상한=None, 하루총량=None,
             제공자=None, 베이스=None, 표시=None, 장르토큰=None, 온도=None):
    """설정.json 에 관리자 설정을 저장한다(빗장으로 읽고-고치고-쓰기를 잠근다).

    부분 저장이다 — 준 값만 바꾸고 나머지는 그대로 둔다. **빈 llm키는 '지우기'가
    아니라 '그대로 두기'** 다(마스킹 때문에 화면이 키를 못 되받아 빈 채로 저장을
    다시 누르는 흔한 실수로 키가 날아가면 안 된다). 응답으로도 키는 마스킹만 낸다.
    """
    변경 = []
    with 자료뿌리.빗장(자료뿌리.설정길()):
        d = _설정읽기()
        if d.get("_깨짐"):
            return {"ok": False, "로그": "설정.json 이 깨져 있어 덮어쓰지 않습니다 — "
                                      "관리자가 파일을 확인해야 합니다(값을 잃지 않으려고 멈춥니다)"}
        # 세션 무반응 시간(출시계획 3-4 ②) — 세션.만료초() 가 읽는 바로 그 top-level 값
        if 세션만료초 is not None and str(세션만료초).strip() != "":
            n = _양의정수(세션만료초, None)
            if n is None:
                return {"ok": False, "로그": "세션만료초는 1 이상의 정수여야 합니다"}
            d["세션만료초"] = n
            변경.append(f"세션만료초={n}")
        llm = d.get("llm") if isinstance(d.get("llm"), dict) else {}
        # LLM 키 — 준 값이 비어 있지 않을 때만 바꾼다(위 주석의 '그대로 두기').
        if llm키 is not None and str(llm키).strip() != "":
            llm["키"] = str(llm키).strip()
            변경.append(f"llm키={_llm키가리기(llm['키'])}")   # 로그에도 마스킹만
        if 모델 is not None and str(모델).strip() != "":
            llm["모델"] = str(모델).strip()
            변경.append(f"모델={llm['모델']}")
        # 기본 모델 안내 문구 — 키 없이 진행할 때 탑바에 뜬다(관리자가 모델을 바꾸면 여기서 표기도
        # 바꾼다). 빈 값은 '지우기'(기본 문구로 돌아감)라 키와 다르게 빈 값도 반영한다. 키·주소는 안 담는다.
        if 표시 is not None:
            llm["표시"] = str(표시).strip()[:80]
            변경.append("표시=" + (llm["표시"][:24] if llm["표시"] else "(비움)"))
        # 제공자 — 아는 것만(openai호환·anthropic·ollama·custom)
        if 제공자 is not None and str(제공자).strip() != "":
            제공자v = str(제공자).strip()
            if 제공자v not in ("openai호환", "anthropic", "ollama", "custom"):
                return {"ok": False, "로그": f"모르는 제공자입니다: {제공자v}"}
            llm["제공자"] = 제공자v
            변경.append(f"제공자={제공자v}")
        # 서버(base URL) — **SSRF 검증**을 지나야 저장한다(빈 값은 기본값 폴백이라 허용).
        if 베이스 is not None:
            정상, 오류 = _베이스URL검증(베이스)
            if 오류:
                return {"ok": False, "로그": f"서버 주소가 안전하지 않습니다 — {오류}"}
            llm["베이스"] = 정상                     # 정상=검증 통과값(빈 값이면 "" 로 두어 기본값 폴백)
            if 정상:
                변경.append(f"베이스={정상}")
        for 이름, 값 in (("세션당상한", 세션당상한), ("하루총량", 하루총량)):
            if 값 is not None and str(값).strip() != "":
                n = _양의정수(값, None)
                if n is None:
                    return {"ok": False, "로그": f"{이름}은 1 이상의 정수여야 합니다"}
                llm[이름] = n
                변경.append(f"{이름}={n}")
        # 장르별 max_tokens — 관리자가 장르마다 따로 상한을 준다. {장르: 양의정수} 로 저장한다.
        # 빈 값/0 은 그 장르에서 빼(→ 코드 기본값으로 돌아간다). 아는 장르만 받는다.
        if isinstance(장르토큰, dict):
            표 = llm.get("장르토큰") if isinstance(llm.get("장르토큰"), dict) else {}
            아는장르 = set(자료뿌리.모듈("genres").표)        # 등록부 이름 — 손으로 적지 않는다(장르가 늘면 빠진다)
            for g, v in 장르토큰.items():
                if g not in 아는장르:
                    continue
                n = _양의정수(v, None) if (v is not None and str(v).strip() != "") else None
                if n:
                    표[g] = n
                else:
                    표.pop(g, None)
            llm["장르토큰"] = 표
            변경.append("장르토큰=" + (", ".join(f"{k}:{x}" for k, x in 표.items()) or "(비움)"))
        # 온도(temperature) — 서버 모델 호출 몸에 실리는 값(_LLM온도 참고). openai호환
        # 갈래는 안 주면 회귀 기본값 0.3 이 나간다(작은 모델 글자깨짐, r10 W2 실측).
        # anthropic 갈래는 반대로 **명시적으로 여기 값을 두지 않으면 아예 안 싣는다**
        # (r10 재검토 — 현행 Claude 는 temperature 를 건드리면 400 을 낸다). 그래서
        # 빈 문자열은 llm키·표시와 달리 **지우기**로 받는다 — 관리자가 실수로 넣은
        # temperature 를 빼서 anthropic 호출을 되살릴 방법이 있어야 한다(그 전엔 지울
        # 방법이 없었다).
        if 온도 is not None:
            if str(온도).strip() == "":
                if llm.pop("온도", None) is not None:
                    변경.append("온도=(비움 — 이제 갈래별 기본값을 씁니다)")
            else:
                n = _온도검증(온도)
                if n is None:
                    return {"ok": False, "로그": "온도는 0~2 사이의 수여야 합니다"}
                llm["온도"] = n
                변경.append(f"온도={n}")
        if llm:
            d["llm"] = llm
        d.pop("_깨짐", None)
        자료뿌리.원자json(자료뿌리.설정길(), d, indent=1)      # 원자 쓰기(WP-S2 ③)
    # 저장한 것을 **가려서** 되돌려 준다 — 화면이 곧바로 새 상태를 그린다(키는 마스킹).
    return {"ok": True, "값": {"바뀐것": 변경, "설정": 관리자설정보기()["값"]},
            "로그": ("바뀐 것: " + ", ".join(변경)) if 변경 else "바뀐 값이 없습니다"}


def _후보안전이름(이름):
    """후보 파일 이름이 안전한가 — 경로 탈출·엉뚱한 파일을 막는다.

    후보 파일은 세션.py 가 `YYYYMMDD-<익명id 8자리>.json` 으로만 낸다. 그 꼴만 받는다 —
    `..`·`/` 는 애초에 이 정규식과 안 맞으므로 경로 탈출이 불가능하다(자료뿌리 열쇠꼴
    검증과 같은 논리).
    """
    return bool(re.fullmatch(r"\d{8}-[0-9a-f]{6,16}\.json", str(이름 or "")))


def _후보읽기(경로):
    try:
        with open(경로, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (ValueError, OSError):
        return None


@등록("관리자후보목록", 읽기=True, en="admincands", 관리자=True,
    설명="검토 대기 중인 익명 원장 후보 목록(문서 내용 없음 — 규칙 id·횟수만)")
def 관리자후보목록():
    """아직 채택/기각 안 한 후보 파일을 보여 준다(출시계획 3-4 ③).

    후보 파일은 이미 익명이다 — 문서 이름·본문은 없고 규칙 id·횟수뿐이다(1-6 A안,
    세션.py 후보뽑기). 채택/기각한 것은 하위 폴더(adopted·rejected)로 옮겨 두므로
    여기 top-level glob 에는 **대기 중인 것만** 잡힌다.
    """
    import glob as _glob
    뿌리 = 자료뿌리.후보뿌리()
    out = []
    for p in sorted(_glob.glob(os.path.join(뿌리, "*.json"))):
        d = _후보읽기(p)
        if d is None:
            continue
        out.append({"파일": os.path.basename(p),
                    "때": d.get("때"), "익명id": d.get("익명id"),
                    "사유": d.get("사유"), "산것초": d.get("산것초"),
                    "후보수": d.get("후보수"), "후보": d.get("후보") or []})
    out.sort(key=lambda x: x.get("때") or "", reverse=True)
    return {"ok": True, "값": {"대기수": len(out), "후보들": out}}


@등록("관리자후보처리", ["파일", "결정"], 읽기=False, en="admincand", 관리자=True,
    설명="원장 후보를 채택 또는 기각한다(정본은 안 고친다 — 1-7, 결정만 기록)")
def 관리자후보처리(파일="", 결정=""):
    """후보 하나를 채택/기각한다(출시계획 3-4 ③).

    **정본(온톨로지)은 여기서 안 고친다**(출시계획 1-7). 채택은 "이 후보를 개발
    흐름에서 반영하기로 했다"는 표시일 뿐이고, 실제 온톨로지 수정은 verify_all 이
    지키는 개발 흐름에서 한다(1-7 의 까닭: 웹에서 고치면 그 검사가 안 돈다). 그래서
    여기는 파일을 adopted/ 또는 rejected/ 로 **옮기기만** 한다 — 대기 목록에서 빠지고
    결정이 남는다.
    """
    if not _후보안전이름(파일):
        return {"ok": False, "로그": "후보 파일 이름이 규칙에 안 맞습니다"}
    if 결정 not in ("채택", "기각"):
        return {"ok": False, "로그": "결정은 '채택' 또는 '기각' 이어야 합니다"}
    뿌리 = 자료뿌리.후보뿌리()
    원본 = os.path.join(뿌리, 파일)
    if not os.path.exists(원본):
        return {"ok": False, "로그": "그 후보가 없습니다(이미 처리됐을 수 있습니다)"}
    하위 = "adopted" if 결정 == "채택" else "rejected"
    낼방 = os.path.join(뿌리, 하위)
    os.makedirs(낼방, exist_ok=True)
    with 자료뿌리.빗장(원본):
        if not os.path.exists(원본):
            return {"ok": False, "로그": "그 후보가 없습니다(이미 처리됐을 수 있습니다)"}
        try:
            os.rename(원본, os.path.join(낼방, 파일))
        except OSError as e:
            return {"ok": False, "로그": f"후보를 옮기지 못했습니다: {type(e).__name__}"}
    return {"ok": True, "값": {"파일": 파일, "결정": 결정, "간곳": 하위},
            "로그": f"후보를 {결정}했습니다 — {하위}/ 로 옮겼습니다(정본은 안 고칩니다, 1-7)"}


@등록("관리자관측요약", 읽기=True, en="adminobserve", 관리자=True,
    설명="관측 — 세션이 얼마나 쓰였나·어느 규칙이 자주 울렸나(익명 후보에서 집계)")
def 관리자관측요약():
    """얼마나 쓰였나·어디서 걸렸나를 익명 후보에서 집계한다(출시계획 3-4 ④).

    왜 후보에서 집계하나 — 세션 관측 기록(build/observed/*)은 세션이 끝날 때 지워진다
    (1-6 A안). 살아남는 유일한 통계가 익명 후보 파일이다: 후보 파일 한 개 = 지나간
    세션 하나, 그 안의 규칙 id·횟수 = 어디서 걸렸나. 그래서 여기가 관측의 정본이다.
    대기·채택·기각 셋을 다 세어 "얼마나 쓰였나"의 분모가 정확하다.
    """
    import glob as _glob
    뿌리 = 자료뿌리.후보뿌리()
    파일들 = _glob.glob(os.path.join(뿌리, "*.json"))
    파일들 += _glob.glob(os.path.join(뿌리, "adopted", "*.json"))
    파일들 += _glob.glob(os.path.join(뿌리, "rejected", "*.json"))
    상태of = {"": "대기", "adopted": "채택", "rejected": "기각"}
    세션수 = 0
    처리분포 = {"대기": 0, "채택": 0, "기각": 0}
    사유분포 = {}
    규칙셈 = {}
    산것초들 = []
    for p in 파일들:
        d = _후보읽기(p)
        if d is None:
            continue
        세션수 += 1
        상위 = os.path.basename(os.path.dirname(p))
        처리분포[상태of.get(상위 if 상위 in ("adopted", "rejected") else "", "대기")] += 1
        사유 = str(d.get("사유") or "?")
        사유분포[사유] = 사유분포.get(사유, 0) + 1
        if isinstance(d.get("산것초"), int):
            산것초들.append(d["산것초"])
        for c in (d.get("후보") or []):
            열 = (str(c.get("출처") or "?"), str(c.get("규칙") or "?"))
            규칙셈[열] = 규칙셈.get(열, 0) + int(c.get("횟수") or 0)
    규칙상위 = [{"출처": 출처, "규칙": 규칙, "횟수": n}
             for (출처, 규칙), n in sorted(규칙셈.items(), key=lambda kv: -kv[1])][:20]
    산것초들.sort()
    def _통계():
        if not 산것초들:
            return {"평균": None, "중앙": None, "최대": None}
        return {"평균": round(sum(산것초들) / len(산것초들)),
                "중앙": 산것초들[len(산것초들) // 2], "최대": 산것초들[-1]}
    return {"ok": True, "값": {
        "세션수": 세션수, "처리분포": 처리분포, "사유분포": 사유분포,
        "산것초": _통계(), "규칙종수": len(규칙셈), "규칙상위": 규칙상위}}


@등록("관리자생성통계", 읽기=True, en="admingen", 관리자=True,
    설명="일자별 생성 세션 수(익명 후보 파일 = 지나간 세션) — 최근 60일. 테스트·자동 실행 포함")
def 관리자생성통계():
    """생성 추이 — 익명 후보 파일을 날짜별로 센다(대시보드 카드용).

    후보 파일 한 개 = 지나간 세션 하나(1-6 A안, `관리자관측요약`과 같은 근거). 여기는
    "얼마나 자주 만들었나"를 **일자별로** 세어 막대 차트로 보여 주기 위한 집계다.
    대기·채택·기각 셋을 다 세어(같은 glob 세 자리) 세션이 어디로 갔든 분모가 맞다.

    날짜는 **파일 내용을 열지 않고** 얻는다 — 후보 파일 이름이 `YYYYMMDD-<익명id>.json`
    으로 그날 날짜를 이미 품고 있어(세션.py 후보뽑기, 파일 안 `때`의 날짜부와 같다),
    이름 앞 8자리를 날짜로 쓴다. 이름이 그 꼴이 아니면(예외) 파일 mtime 으로 접는다.
    수천 개가 쌓여도 stat 한 번씩만 하고 json 파싱은 안 한다.

    정직성 — 이 셈에는 우리 E2E·자동 실행이 섞여 있다(실사용자만이 아니다). 화면이
    그 주석을 단다(admin.html 생성 추이 카드).
    """
    import glob as _glob
    뿌리 = 자료뿌리.후보뿌리()
    파일들 = _glob.glob(os.path.join(뿌리, "*.json"))
    파일들 += _glob.glob(os.path.join(뿌리, "adopted", "*.json"))
    파일들 += _glob.glob(os.path.join(뿌리, "rejected", "*.json"))
    # 최근 60일만 — 그 밖은 합계에는 넣되 일자별 목록에서는 접는다.
    자름 = time.strftime("%Y-%m-%d", time.localtime(time.time() - 60 * 86400))
    일자별 = {}
    합계 = 0
    _이름꼴 = re.compile(r"(\d{4})(\d{2})(\d{2})-")
    for p in 파일들:
        m = _이름꼴.match(os.path.basename(p))
        if m:
            날 = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            try:
                날 = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(p)))
            except OSError:
                continue
        합계 += 1
        if 날 >= 자름:
            일자별[날] = 일자별.get(날, 0) + 1
    목록 = [{"날": k, "건수": v} for k, v in sorted(일자별.items())]
    return {"ok": True, "값": {"합계": 합계, "일자별": 목록}}


# ── 동의 코퍼스 (WP-S10 1차) ─────────────────────────────────────────────
# 피드백 엔진의 프라이버시 심장 — "동의 없이는 아무것도 안 남는다"·"비식별이 진짜
# 지운다". 관문·비식별·저장은 feedback/corpus.py 한 곳에 있고, 여기는 그 문을 세 껍데기
# (스킬·MCP·웹앱)에 낸다. 자료뿌리처럼 파일에서 바로 불러 쓴다(sys.path 를 안 늘린다).
_사양코퍼스 = _iu.spec_from_file_location(
    "동의코퍼스엔진", os.path.join(ROOT, "feedback", "corpus.py"))
_코퍼스 = _iu.module_from_spec(_사양코퍼스)
_사양코퍼스.loader.exec_module(_코퍼스)


@등록("동의코퍼스", ["결정", "항목"], 읽기=False, en="consentcorpus",
    설명="피드백 항목을 동의받아 코퍼스에 남긴다 — '남깁니다' 일 때만 저장(비식별 후)")
def 동의코퍼스(결정="", 항목=None):
    """동의 게이트 (WP-S10 1차 — 구현계획.md §3).

    F1 에이전트 카드가 [남깁니다]/[이번만 아니오]/[앞으로 묻지 않기] 중 하나와, 감지가
    빚은 코퍼스 항목(차원·델타·규칙맥락)을 실어 보낸다. **오직 '남깁니다'** 일 때만
    비식별을 거쳐 코퍼스(기본 뿌리)에 한 줄 남긴다 — 그 밖은 파일도 안 건드린다.

    저장 로직(관문·비식별)은 feedback/corpus.py 에 모아 뒀다 — 세 껍데기가 저마다
    관문을 두면 한쪽만 새는(동의 없이 남는) 사고가 난다. 여기는 그 함수 하나를 부른다.
    """
    if not isinstance(항목, dict):
        return {"ok": False, "로그": "항목이 객체가 아닙니다 — 감지가 빚은 코퍼스 항목이 필요합니다"}
    try:
        결과 = _코퍼스.동의저장(결정, 항목)
    except ValueError as e:
        return {"ok": False, "로그": f"항목이 스키마에 안 맞습니다: {e}"}
    if 결과.get("남김"):
        return {"ok": True, "값": 결과,
                "로그": f"동의('{결정}') — 코퍼스에 1건 남겼습니다"
                       f"(비식별 후, 차원={결과.get('차원')}, 동의시각={결과.get('동의시각')})"}
    return {"ok": True, "값": 결과,
            "로그": f"동의가 아니어서('{결정 or '빈 결정'}') 코퍼스에 아무것도 안 남겼습니다"}


# ── 흐름 훅 + 관리자 검토 (WP-S10 2차-B) ───────────────────────────────────
# 2차-A 는 세 차원(문체·구성·디자인)을 순수 함수로 완성했다(구성_항목·디자인_항목·
# 문체_항목·주목할변경인가, 전부 feedback/corpus.py). 이 슬라이스는 그 함수들을
# **실제 흐름에 건다** — 감지는 여기(서버)가 하고, F1 동의 카드는 화면(app.html·
# render_editor_any.py)이 띄우고, 저장은 이미 있는 `동의코퍼스`(바로 위) 한 문을 그대로
# 쓴다. 아래 두 새 작업은 **아무것도 저장하지 않는다** — 항목을 빚어 돌려줄 뿐이다.
# "동의 없이는 아무것도 안 남는다"는 관문이 `동의코퍼스`→`동의저장` 한 곳에만 있어야
# 한다 — 문이 둘이면 그중 하나가 샌다. 인자 모양은 사전 리터럴을 고치지 않고 등록
# 직전에 덧댄다(구현계획.md 규칙 2 — `인자별칭["source"]` 와 같은 자리 규칙).

인자모양["이전"] = dict
인자모양["이후"] = dict
인자모양["제안"] = dict
인자모양["채택"] = dict


def _문서길이(doc):
    """문서 분량 — 규칙 보완 목표물의 한 축(짧은 문서와 긴 문서는 규칙이 다르다).
    절·항목 수만 센다(통제 수치, 내용 없음). 장르 무관하게 흔한 자리들을 훑는다."""
    if not isinstance(doc, dict):
        return None
    상단절 = (doc.get("장") or doc.get("절") or doc.get("sections")
             or doc.get("슬라이드") or doc.get("조문") or [])
    항목수 = [0]

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("항목", "items") and isinstance(v, list):
                    항목수[0] += len(v)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(doc)
    return {"절": len(상단절) if isinstance(상단절, list) else 0, "항목": 항목수[0]}


@등록("문체후보", ["key", "이전", "이후"], 읽기=False, en="stylecandidate",
    설명="리터칭(직접 다듬기) 저장 직전 — backtrace 세그먼트 diff 로 문체 동의 후보를 만든다(저장 안 함)")
def 문체후보(key="", 이전=None, 이후=None):
    """문체 훅의 감지 지점 (WP-S10 2차-B) — render_editor_any.py 편집기가 `/save` 로
    반영하기 직전에 이 작업을 불러 "마지막 기준(이전) vs 지금 고친 것(이후)"의
    backtrace 세그먼트 diff 를 뜬다(1차·2차-A 가 실측한 그 extract·diff_docs 그대로).
    `주목할변경인가` 로 조를 만한 낱말 치환을 찾으면 `문체_항목` 을 빚어 돌려준다 —
    **여기서 저장하지 않는다.** 화면이 이 항목을 들고 F1 동의 카드를 띄우고, 동의하면
    그제서야 `동의코퍼스` 를 따로 부른다(동의 관문은 그 작업 하나뿐이어야 한다).

    backtrace(feedback/backtrace.py)는 **1p(samples) 조립기 하나만** 안다 — 이 편집기는
    장르를 모르고 다섯 장르 모두에 같은 저장 흐름을 쓰므로, 이 문서가 samples 등록부
    소속이 아니면(또는 조립이 안 맞으면) 조용히 후보 없음(None)을 돌려준다. 에러가
    아니다 — 저장 자체는 이 진단과 무관하게 그대로 간다(2차-A 가 이미 적어 둔 "backtrace
    는 1p 전용"이라는 한계를 이어받을 뿐, 새로 숨기는 것은 없다).
    """
    if not isinstance(이전, dict) or not isinstance(이후, dict):
        return {"ok": True, "값": None}
    cur = 문서(key) if key else {"ok": False}
    if not cur.get("ok") or not os.path.basename(str(cur.get("등록부") or "")).startswith("samples"):
        return {"ok": True, "값": None}
    try:
        bt = 자료뿌리.모듈("backtrace", "feedback")
        exp = bt.extract(bt.assemble.build(이전))
        act = bt.extract(bt.assemble.build(이후))
    except Exception:
        # 조립이 안 되는 중간 상태(빈 절 등)일 수 있다 — 능동 동의를 못 켤 뿐, 저장을
        # 막을 일은 아니다(이 작업은 진단 전용, 조용히 후보 없음으로 넘어간다).
        return {"ok": True, "값": None}
    # 기본 스펙 — 규칙 보완의 목표물(장르·유형·길이)을 변경과 함께 남긴다.
    스펙 = {"장르": cur.get("장르") or 이후.get("genre") or "samples",
           "유형": 이후.get("유형") or 이후.get("보고목적유형"),
           "길이": _문서길이(이후)}
    for d in bt.diff_docs(exp, act):
        if _코퍼스.주목할변경인가(d):
            값 = _코퍼스.문체_항목(d, 규칙맥락="리터칭")
            값["기본스펙"] = 스펙
            return {"ok": True, "값": 값}
    return {"ok": True, "값": None}


# 클라 환경 통제어휘 — 이 밖의 열쇠·값은 **버린다**(핑거프린팅 방지). 정본은 feedback/
# corpus.py 한 곳(_클라얼굴들·_클라OS들)에 두고 여기서 참조한다 — 두 사본이 어긋나면
# 사이드카와 환경 코퍼스가 다르게 걸러 '같은 표준'(사장님 판정 B)이 조용히 깨진다.


@등록("클라환경", ["key", "글꼴보유", "os계열", "결정"], 읽기=False, en="clientenv",
    설명="hwpx 내려받기 때 클라 환경(등록 얼굴 보유 여부·OS 계열)을 동의 시에만 사이드카에 남긴다")
def 클라환경(key="", 글꼴보유=None, os계열="", 결정=""):
    """클라 텔레메트리 수신 창구(방법론 전환 8단계, 사장님 승인 2026-08-14).

    동의 게이트는 코퍼스와 같은 관문(동의했나)을 그대로 쓴다 — 동의가 아니면
    **아무것도 안 쓴다.** 값은 전부 통제어휘다: 글꼴보유는 등록 얼굴 목록의
    불리언만 받고(밖의 열쇠는 버림 — 전체 글꼴 목록을 실어 보내도 안 남는다),
    os계열은 셋 중 하나 밖이면 '기타'로 접는다. 자유 문자열은 한 자도 안 남는다.
    저장 자리는 {key}.hwpx.meta.json 사이드카의 '클라' 절 — gitignore·세션 소멸
    규율을 따르고 원장·코퍼스로는 안 간다(영속 집계는 별도 재논의).
    """
    if not _코퍼스.동의했나(결정):
        return {"ok": True, "값": {"남김": False, "결정": 결정}}
    보유 = {}
    if isinstance(글꼴보유, dict):
        for 얼굴 in _코퍼스._클라얼굴들:          # 통제어휘 정본은 corpus.py 한 곳
            if 얼굴 in 글꼴보유:
                보유[얼굴] = bool(글꼴보유[얼굴])
    깨끗 = {"글꼴보유": 보유,
          "os계열": os계열 if os계열 in _코퍼스._클라OS들 else "기타",
          "동의시각": time.strftime("%Y-%m-%dT%H:%M:%S")}
    # key 는 클라가 준다 — basename 으로 경로를 접어 산출물뿌리 밖에 못 쓰게 한다(트래버설
    # 차단, 다른 쓰기 경로도 다 basename 을 쓴다). 사이드카 접미사는 .hwpx.meta.json 고정.
    안전키 = os.path.basename(str(key or ""))
    길 = os.path.join(자료뿌리.산출물뿌리(), f"{안전키}.hwpx.meta.json")
    메타 = {}
    if os.path.exists(길):
        try:
            메타 = json.load(open(길, encoding="utf-8"))
        except Exception:
            메타 = {}
    메타["클라"] = 깨끗
    with open(길, "w", encoding="utf-8") as fh:
        json.dump(메타, fh, ensure_ascii=False, indent=1)
    # 사이드카(이 문서용)에 더해, 편집 코퍼스와 **같은 표준**으로 환경 코퍼스에도 남긴다 —
    # 규칙개선 기초자료(전달·글꼴 규칙, 사장님 판정 B '26-08-16). 관문은 환경저장 안에 또 있어
    # 동의 없이는 안 쓴다. 코퍼스 기록 실패가 사이드카·응답을 못 세우되(부가), 규칙3대로
    # **조용히 삼키진 않는다** — stderr 로 세어 영속 재료 유실을 관측 가능하게 둔다(1858 선례).
    try:
        _코퍼스.환경저장(결정, 글꼴보유, os계열)
    except Exception as e:
        print(f"[환경코퍼스] {안전키}: 기록 실패 — {e}", file=sys.stderr)
    return {"ok": True, "값": {"남김": True, "클라": 깨끗}}


@등록("재현신고", ["key", "무엇", "어디", "내용"], 읽기=False, en="reproreport",
    설명="한글(HWPX)에서 화면과 다르게 보인 곳 — 재현 동의 후보를 만든다(저장 안 함)")
def 재현신고(key="", 무엇="", 어디="", 내용=""):
    """재현 훅의 감지 지점(방법론 전환 4층, 2026-08-14) — hwpx 수신자가 "한글에서
    이렇게 보인다"를 알려 오는 유일한 문이다. `feedback/corpus.py 재현_항목` 을 그대로
    부른다 — `무엇` 은 통제어휘(대조 검사 갈래), 자유 신고문은 `내용`→`지시` 로 실려
    저장 경로(동의코퍼스)가 동의 확인 뒤 비식별한다. **여기서 저장하지 않는다** —
    동의 관문은 동의코퍼스 하나뿐이어야 한다(문체후보·디자인후보와 같은 규율).
    """
    값 = _코퍼스.재현_항목(무엇 or "기타", 어디=어디 or None, 지시=(내용 or None))
    cur = 문서(key) if key else {"ok": False}
    if cur.get("ok"):
        값["기본스펙"] = {"장르": cur.get("장르"), "유형": None, "길이": None}
    return {"ok": True, "값": 값}


@등록("디자인후보", ["판별", "고른", "지시", "규칙맥락"], 읽기=False, en="designcandidate",
    설명="추천 양식과 고른 양식이 다를 때 — 디자인 동의 후보를 만든다(저장 안 함)")
def 디자인후보(판별="", 고른="", 지시=None, 규칙맥락=None):
    """디자인 훅의 감지 지점 (WP-S10 2차-B) — app.html 양식 선택 화면(`상태.추천장르` vs
    `상태.고른장르`)이 사용자가 추천과 다른 양식을 고르는 순간 이 작업을 부른다.
    `feedback/corpus.py 디자인_항목` 을 그대로 부른다 — 델타 구성·주목 판정·저장 게이트는
    전부 그 순수 함수(2차-A)의 몫이고, 여기는 부르기만 한다. 추천=고른이면 그 함수가
    None 을 돌려주므로(안 조른다) 화면은 카드를 안 띄운다.
    """
    try:
        값 = _코퍼스.디자인_항목(판별, 고른, 지시, 규칙맥락)
        if 값:
            값["기본스펙"] = {"장르": 고른 or 판별}   # 디자인 훅은 양식 선택이라 장르가 곧 스펙
        return {"ok": True, "값": 값}
    except Exception as e:
        return {"ok": False, "로그": f"디자인 후보를 만들지 못했습니다: {type(e).__name__}: {e}"}


@등록("구성후보", ["제안", "채택", "지시", "규칙맥락"], 읽기=False, en="compositioncandidate",
    설명="제안 빌드플랜과 채택 빌드플랜이 다를 때 — 구성 동의 후보를 만든다(저장 안 함)")
def 구성후보(제안=None, 채택=None, 지시=None, 규칙맥락=None):
    """구성 훅의 감지 지점 (WP-S10 2차-B) — 빌드플랜 승인이 채팅/MCP 흐름이라(웹 단계
    없음, Explore 지도) 이 감지도 그 흐름에 산다. 에이전트가 제안 플랜을 저작해 승인
    화면을 보이고, 사용자가 재구성(수정요청)하면 최종 플랜이 나온다 — 그 **제안·채택 두
    플랜 dict** 를 넣어 부른다(에이전트가 문맥에 이미 쥔 것, app.html 이 상태의 추천/고른
    양식을 디자인후보에 넘기는 것과 같은 결). `수정요청` 답변 자유 프롬프트는 `지시` 로
    싣는다(저장 경로에서 비식별). `feedback/corpus.py 구성_항목` 을 그대로 부른다 — 델타
    구성(유형·목차·배치)·주목 판정·저장 게이트는 전부 그 순수 함수(2차-A)의 몫이고, 여기는
    부르기만 한다. 제안=채택이면 그 함수가 None 을 돌려주므로(안 조른다) 카드/물음이 안 뜬다.

    **여기서 저장하지 않는다**(문체후보·디자인후보와 같은 계약) — 항목을 빚어 돌려줄 뿐,
    동의하면 그제서야 `동의코퍼스` 한 문을 따로 부른다. 동의 관문은 그 작업 하나뿐이다.
    """
    if not isinstance(제안, dict) or not isinstance(채택, dict):
        return {"ok": True, "값": None}
    try:
        값 = _코퍼스.구성_항목(제안, 채택, 지시, 규칙맥락)
        if 값:
            값["기본스펙"] = {"장르": 채택.get("장르") or 채택.get("genre"),
                            "유형": 채택.get("유형"),
                            "길이": _문서길이(채택)}
        return {"ok": True, "값": 값}
    except Exception as e:
        return {"ok": False, "로그": f"구성 후보를 만들지 못했습니다: {type(e).__name__}: {e}"}


@등록("관리자접속통계", 읽기=True, en="adminaccess", 관리자=True,
    설명="일자별 접속·사용 통계(방문·생성·내보내기) — 재배포에도 남는 파일 누적")
def 관리자접속통계():
    """접속통계.json 을 읽어 합계와 최근 30일 일자별을 돌려준다(관측=원장집계와 별개)."""
    data = {}
    try:
        if os.path.exists(_통계경로):
            data = json.load(open(_통계경로, encoding="utf-8"))
    except Exception:
        data = {}
    일 = data.get("일자별", {}) or {}
    최근 = sorted(일.items(), key=lambda kv: kv[0], reverse=True)[:30]
    return {"ok": True, "값": {
        "합계": data.get("합계", {}) or {},
        "일자별": [dict(날=k, **(v or {})) for k, v in 최근],
    }}


@등록("관리자코퍼스목록", 읽기=True, en="admincorpus", 관리자=True,
    설명="동의 코퍼스를 차원별로 보여준다(문체/구성/디자인) — 규칙 승격은 표시까지만(1-7)")
def 관리자코퍼스목록():
    """S5 관리자 면의 코퍼스 검토 (WP-S10 2차-B, 구현계획.md §3).

    **읽기·표시까지만** 한다 — 실제 규칙 승격(온톨로지 수정)은 정본 판정이라 이 화면이
    안 한다(출시계획 1-7, `관리자후보처리`와 같은 원칙: 웹에서 고치면 조립기·린터·
    게이트 검사가 안 돈다). 코퍼스는 저장 시점에 이미 비식별을 거쳤다(`동의저장` 한
    곳) — 여기는 그 결과를 차원별로 묶어 보여줄 뿐, 한 번 더 손대지 않는다.
    """
    항목들 = _코퍼스.코퍼스읽기()
    차원별 = {d: [] for d in _코퍼스.차원들}
    for it in 항목들:
        차 = it.get("차원")
        if 차 in 차원별:
            차원별[차].append(it)
    for v in 차원별.values():
        v.sort(key=lambda x: x.get("동의시각") or "", reverse=True)
    환경 = _코퍼스.환경코퍼스읽기()   # 8단계 클라 환경 — 전달·글꼴 규칙 재료(편집 델타와 다른 축)
    환경.sort(key=lambda x: x.get("동의시각") or "", reverse=True)
    return {"ok": True, "값": {
        "전체수": len(항목들),
        "차원별수": {k: len(v) for k, v in 차원별.items()},
        "차원별": 차원별,
        "환경수": len(환경),
        "환경": 환경}}


@등록("규칙시사점", 읽기=True, en="ruleinsights", 관리자=True,
    설명="쌓인 동의 코퍼스를 규칙별로 취합해 AI 가 규칙개선 시사점을 뽑는다(온디맨드) — 규칙 수정은 관리자 몫")
def 규칙시사점():
    """8단계 활용 ② — **온디맨드 시사점 엔진**(사장님 판정 '26-08-16).

    관리자가 부를 때 코퍼스를 규칙맥락·차원별로 취합(corpus.규칙별취합)하고, 서버 LLM 에
    넣어 '이 규칙을 사용자들이 이렇게 고친다 → 이런 방향' 시사점을 뽑는다. **규칙은 안
    고친다** — 관리자가 커멘트해 정본에 반영하는 재료만 낸다(사람+AI 협업, 자동 반영 없음).
    LLM 미설정·실패면 취합만 돌려준다(집계는 LLM 없이도 유효). 코퍼스는 저장 시 비식별됨.
    """
    취합 = _코퍼스.규칙별취합()
    if not 취합["규칙별"] and not 취합["환경"]["표본수"]:
        return {"ok": True, "값": {"취합": 취합, "시사점": None,
                                 "안내": "아직 쌓인 코퍼스가 없습니다 — 동의된 편집·환경이 모이면 시사점을 뽑습니다"}}
    지시문 = (
        "너는 대한민국 공공문서 작성 규칙(온톨로지)의 개선을 돕는 분석가다. 아래 자료는 사용자들이 "
        "편집기에서 문서를 어떻게 고쳤는지 규칙별·차원(문체·구성·디자인·재현)별로 묶은 비식별 집계와, "
        "여는 기기의 글꼴·OS 분포다. 각 규칙에 대해 사용자 수정의 공통 방향을 읽어 규칙개선 시사점을 "
        "뽑아라. 규칙을 네가 바꾸지 말고, 관리자가 판단할 재료로서 관찰·제안방향·근거건수만 낸다. 집계에 "
        "실제로 있는 것만 근거로 삼고 지어내지 마라. 출력은 오직 이 JSON: {\"시사점\": [{\"규칙\": \"규칙맥락 값\", "
        "\"차원\": \"문체|구성|디자인|재현\", \"관찰\": \"사용자들이 이렇게 고친다\", \"방향\": \"규칙을 이렇게 다듬는 "
        "것을 검토\", \"근거건수\": 정수}], \"환경시사점\": \"글꼴·OS 분포로 본 전달·글꼴 규칙 제안(없으면 빈 문자열)\"}")
    # 서버 LLM 미설정이면 취합만 — '미설정'과 '빈 응답'을 가른다(빈답을 미설정으로 오표기 방지).
    if not _서버LLM설정():
        return {"ok": True, "값": {"취합": 취합, "시사점": None,
                                 "안내": "서버 LLM 미설정 — 취합만 보여드립니다(관리자설정에서 LLM 을 켜면 AI 시사점이 붙습니다)"}}
    # 거대 코퍼스에서 입력이 컨텍스트를 넘지 않게 규칙 그룹은 **상위 40개만** LLM 에 넣는다
    # (건수 내림차순 정렬돼 있음). 전체 취합은 화면에 그대로 나가고 LLM 입력만 절제한다.
    LLM입력 = {**취합, "규칙별": 취합["규칙별"][:40]}
    잘린 = len(취합["규칙별"]) - 40
    try:
        raw = _서버LLM호출(지시문, json.dumps(LLM입력, ensure_ascii=False))
    except Exception as e:
        return {"ok": True, "값": {"취합": 취합, "시사점": None,
                                 "안내": f"AI 시사점을 못 뽑았습니다({type(e).__name__}) — 취합만 보여드립니다"}}
    # 모델이 빈답(null)·배열 등 예상 밖 형태를 낼 수 있다 — 계약(딕트+시사점 배열)을 확인한다.
    if not isinstance(raw, dict) or not isinstance(raw.get("시사점"), list):
        return {"ok": True, "값": {"취합": 취합, "시사점": None,
                                 "안내": "AI 응답이 비었거나 형식이 예상과 달라 취합만 보여드립니다"}}
    값 = {"취합": 취합, "시사점": raw}
    if 잘린 > 0:
        값["안내"] = f"규칙 그룹이 많아 상위 40갈래만 AI 에 넣었습니다(생략 {잘린}갈래) — 취합 전체는 위에 있습니다"
    return {"ok": True, "값": 값}


# ── 규칙마당(Rules Commons) — 공개 규칙 카드에 남기는 의견·노하우 제안 ─────────────
# 규칙마당(/rules/)은 규칙 카드 227장을 사람 언어로 펼쳐 둔 **공개** 페이지다(사장님 결정
# '26-09-16: 퍼블릭·몽땅 공개·실명 표기). 그 위에서 사람들이 남기는 것은 두 가지뿐이다 —
#   · 의견: 카드 하나에 동의 / 조건부 / 반대(현장은 다릅니다) + 사유 한 줄
#   · 제안: 규칙에 없는 '이럴 때 이렇게 합니다' 노하우 한 조각(문서·부분·요령·왜·전후)
# 저장은 무DB 파일(JSONL, 한 줄 한 건)이다. 세션 방(sessions/)에 두지 않는다 — 세션은 문서
# 한 건이 끝나면 지워지는 자리이고, 이것은 모두가 보는 공용 게시판이라 오래 남아야 한다.
# feedback/commons/ 는 배포 rsync 가 건드리지 않는 운영 경로다(deploy/deploy-ncp.sh 제외 목록).
# 남긴 글은 **공개된다**(이름·소속은 적은 그대로 표기). 그래서 연락처처럼 보이는 글은 받지
# 않고, 길이를 자르고, 세션·하루 상한을 둔다. 숨길 글은 운영자가 그 줄에 "숨김": true 를 단다.
_마당경로 = os.environ.get("문서지능_규칙마당경로") or os.path.join(ROOT, "feedback", "commons")
_마당판정 = ("동의", "조건부", "반대")
_마당문서 = ("한 장 보고서", "풀버전 보고서", "시행문(공문)", "규정·내규", "보도자료", "발표 슬라이드")
_마당부분 = ("제목·표지", "요약(두괄)", "본문 글머리·위계", "표", "그림·도식·차트", "글꼴·크기",
          "여백·판면", "붙임·별첨", "수신·발신·결재선", "문장 표현", "문서 전체 구성", "판정·유형")
# 관리자 처리 상태 — 규칙마당에 그대로 공개된다. '반영 예정'은 개발 흐름(온톨로지 수정)으로 넘길 것,
# '반영 완료'는 온톨로지·규칙 카드에 실제로 옮긴 것. 관리 화면은 정본을 고치지 않는다(출시계획 1-7).
_마당상태 = ("수집", "검토 중", "반영 예정", "반영 완료", "보류", "반영 안 함")
_마당채택 = ("반영 예정", "반영 완료")          # 노하우 제안이 이 상태면 규칙마당에 '현장 노하우'로 게시
_마당상황 = ("결재 상신", "상급기관 보고", "국감·감사 대응", "예산 요구", "보도·홍보", "회의·협의",
          "민원 회신", "대외 공문", "발표·브리핑")
# 연락처로 보이는 글 — 이메일·전화번호. 공개 게시판이라 받지 않고 되돌려 보낸다.
_마당연락처 = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|(?<!\d)0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_마당제어문자 = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_마당락 = threading.Lock()
_마당하루 = {"날": "", "수": 0}         # 하루 전체 상한(IP 당 10분 상한은 serve.py 공개쓰기 문)
_마당하루상한 = int(os.environ.get("문서지능_규칙마당하루상한") or 2000)
_마당카드캐시 = {"때": 0.0, "ids": frozenset()}


def _마당카드들():
    """규칙 카드 id 집합 — 의견은 실재하는 카드에만 단다(rules/cards.json 이 정본 사본)."""
    f = os.path.join(ROOT, "rules", "cards.json")
    try:
        때 = os.path.getmtime(f)
    except OSError:
        return frozenset()
    if 때 != _마당카드캐시["때"]:
        try:
            ids = frozenset(str(c.get("card_id")) for c in json.load(open(f, encoding="utf-8")))
        except Exception:
            ids = frozenset()
        _마당카드캐시.update({"때": 때, "ids": ids})
    return _마당카드캐시["ids"]


def _마당글(v, 최대):
    """사람이 적은 한 칸 — 제어문자를 걷고 앞뒤 공백을 자르고 길이를 넘기면 자른다."""
    v = _마당제어문자.sub("", str(v or ""))
    # 눈에 안 보이는 서식 문자(제로폭 공백·결합자·BOM 등, 유니코드 Cf)도 걷는다 — 이것을 끼워
    # 넣으면 '010\u200b-1234…' 가 화면엔 전화번호로 보이면서 연락처 검사를 빠져나간다.
    v = "".join(ch for ch in v if unicodedata.category(ch) != "Cf").strip()
    return v[:최대]


def _마당파일(종류):
    return os.path.join(_마당경로, "의견.jsonl" if 종류 == "의견" else "제안.jsonl")


def _마당줄들(f):
    if not os.path.exists(f):
        return []
    out = []
    with open(f, encoding="utf-8") as fh:
        for 줄 in fh:
            try:
                x = json.loads(줄)
            except Exception:
                continue
            if isinstance(x, dict):
                out.append(x)
    return out


def _마당처리들():
    """관리자 처리 기록(처리.jsonl, 한 줄 한 번) — 글 id 마다 **마지막 처리**가 이긴다(지난 처리는 감사용으로 남는다)."""
    끝 = {}
    for x in _마당줄들(os.path.join(_마당경로, "처리.jsonl")):
        if x.get("id"):
            끝[x["id"]] = x
    return 끝


def _마당읽기(종류, 숨김포함=False):
    """글 목록 — 관리자 처리(상태·답변·숨김)를 얹어 돌려준다. 공개 쪽은 숨긴 글을 뺀다."""
    처리 = _마당처리들()
    out = []
    for x in _마당줄들(_마당파일(종류)):
        c = 처리.get(x.get("id"), {})
        x = dict(x)
        x["상태"] = c.get("상태") or x.get("상태") or "수집"
        x["답변"] = c.get("답변", "")
        x["숨김"] = bool(c["숨김"]) if "숨김" in c else bool(x.get("숨김"))
        x["처리일"] = c.get("시각", "")[:10]
        if 숨김포함 or not x["숨김"]:
            out.append(x)
    return out


def _마당상한초과():
    """하루 전체 상한 — 넘으면 사람말 한 줄, 아니면 None(그리고 한 건 센다).
    IP 당 10분 상한은 serve.py 의 공개쓰기 문이 먼저 건다(세션 쿠키는 버리면 새로 나와서
    세션 기준 상한은 도배를 못 막는다 — '26-09-25 검토에서 재현)."""
    오늘 = time.strftime("%Y-%m-%d")
    with _마당락:
        if _마당하루["날"] != 오늘:
            _마당하루.update({"날": 오늘, "수": 0})
        if _마당하루["수"] >= _마당하루상한:
            return "오늘 받을 수 있는 양을 채웠습니다 — 내일 다시 남겨 주세요"
        _마당하루["수"] += 1
    return None


@등록("규칙마당보기", 설명="규칙마당 — 카드별 의견 집계와 최근 노하우 제안(공개)", en="commons", 숨김=True)
def 규칙마당보기():
    순서 = {"검토 중": 1, "반영 예정": 2, "반영 완료": 3}
    의견 = {}
    for x in _마당읽기("의견"):
        c = 의견.setdefault(x.get("카드"), {"동의": 0, "조건부": 0, "반대": 0, "최근": [], "반영": ""})
        if x.get("판정") in _마당판정:
            c[x["판정"]] += 1
        c["최근"].append({k: x.get(k, "") for k in ("판정", "사유", "이름", "소속", "날짜", "상태", "답변")})
        if 순서.get(x["상태"], 0) > 순서.get(c["반영"], 0):
            c["반영"] = x["상태"]          # 카드에 걸린 의견 중 가장 앞선 처리(검토 중 < 반영 예정 < 반영 완료)
    for c in 의견.values():
        c["최근"] = c["최근"][-5:]
    칸 = ("id", "문서", "부분", "상황", "요령", "왜", "전", "후", "이름", "소속", "날짜", "상태", "답변", "처리일")
    모든제안 = [{k: x.get(k, "") for k in 칸} for x in _마당읽기("제안")]
    return {"ok": True, "값": {"의견": 의견, "제안": 모든제안[-60:],
                             "노하우": [p for p in 모든제안 if p["상태"] in _마당채택],
                             "합계": {"의견": sum(c["동의"] + c["조건부"] + c["반대"] for c in 의견.values()),
                                    "제안": len(모든제안)}}}


@등록("규칙마당남기기", ["종류", "항목"], 읽기=False,
      설명="규칙마당 — 카드 의견(동의·조건부·반대) 또는 노하우 제안 한 건을 남긴다(공개 게시)",
      en="commons_post", 숨김=True, 공개쓰기=True, 비동기=False)
def 규칙마당남기기(종류="", 항목=None):
    항목 = 항목 if isinstance(항목, dict) else {}
    if 종류 not in ("의견", "제안"):
        return {"ok": False, "로그": "종류는 '의견' 또는 '제안'이어야 합니다"}
    이름 = _마당글(항목.get("이름"), 30)
    소속 = _마당글(항목.get("소속"), 40)
    if 종류 == "의견":
        카드 = _마당글(항목.get("카드"), 40)
        판정 = _마당글(항목.get("판정"), 4)
        사유 = _마당글(항목.get("사유"), 300)
        if 카드 not in _마당카드들():
            return {"ok": False, "로그": "그런 규칙 카드가 없습니다"}
        if 판정 not in _마당판정:
            return {"ok": False, "로그": "판정은 동의·조건부·반대 가운데 하나여야 합니다"}
        if not 사유:
            return {"ok": False, "로그": "사유를 한 줄 적어 주세요"}
        글들 = (사유, 이름, 소속)
        기록 = {"카드": 카드, "판정": 판정, "사유": 사유}
    else:
        문서 = _마당글(항목.get("문서"), 20)
        부분 = _마당글(항목.get("부분"), 20)
        상황 = _마당글(항목.get("상황"), 20)
        요령 = _마당글(항목.get("요령"), 120)
        왜 = _마당글(항목.get("왜"), 400)
        전 = _마당글(항목.get("전"), 300)
        후 = _마당글(항목.get("후"), 300)
        if 문서 not in _마당문서 or 부분 not in _마당부분 or (상황 and 상황 not in _마당상황):
            return {"ok": False, "로그": "문서·부분·상황은 목록에 있는 것으로 골라 주세요"}
        if not 요령:
            return {"ok": False, "로그": "한 줄 요령을 적어 주세요"}
        if 항목.get("동의") is not True:
            return {"ok": False, "로그": "공개에 동의하셔야 올릴 수 있습니다"}
        글들 = (요령, 왜, 전, 후, 이름, 소속)
        기록 = {"문서": 문서, "부분": 부분, "상황": 상황, "요령": 요령, "왜": 왜, "전": 전, "후": 후,
              "상태": "수집"}
    if any(_마당연락처.search(g) for g in 글들 if g):
        return {"ok": False, "로그": "연락처(이메일·전화번호)는 빼고 남겨 주세요 — 이 페이지는 누구나 봅니다"}
    막힘 = _마당상한초과()
    if 막힘:
        return {"ok": False, "로그": 막힘}
    기록.update({"이름": 이름, "소속": 소속, "날짜": time.strftime("%Y-%m-%d"), "id": uuid.uuid4().hex[:12]})
    f = _마당파일(종류)
    try:
        os.makedirs(_마당경로, exist_ok=True)
        with 자료뿌리.빗장(f):
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(기록, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"[규칙마당] 저장 실패: {type(e).__name__}\n")
        return {"ok": False, "로그": "저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요"}
    return {"ok": True, "값": {"종류": 종류, "id": 기록["id"]}}


@등록("규칙마당관리", 설명="규칙마당 검토 — 올라온 의견·노하우 전부(숨긴 글 포함)와 처리 상태", en="commons_admin",
      관리자=True)
def 규칙마당관리():
    제목 = {}
    try:
        for c in json.load(open(os.path.join(ROOT, "rules", "cards.json"), encoding="utf-8")):
            제목[str(c.get("card_id"))] = c.get("title", "")
    except Exception:
        pass
    글 = []
    for 종류 in ("제안", "의견"):
        for x in _마당읽기(종류, 숨김포함=True):
            x["종류"] = 종류
            if 종류 == "의견":
                x["카드제목"] = 제목.get(x.get("카드"), "")
            글.append(x)
    글.sort(key=lambda x: (x.get("날짜", ""), x.get("id", "")), reverse=True)
    셈 = {"전체": len(글), "처리 안 함": 0, "반영 예정": 0, "반영 완료": 0, "숨김": 0}
    for x in 글:
        if x["숨김"]:
            셈["숨김"] += 1
        elif x["상태"] == "수집":
            셈["처리 안 함"] += 1
        if x["상태"] in ("반영 예정", "반영 완료") and not x["숨김"]:
            셈[x["상태"]] += 1
    return {"ok": True, "값": {"글": 글, "셈": 셈, "상태들": list(_마당상태)}}


@등록("규칙마당처리", ["항목"], 읽기=False, 설명="규칙마당 검토 — 글 하나의 상태·공개 답변·숨김을 정한다",
      en="commons_moderate", 관리자=True)
def 규칙마당처리(항목=None):
    항목 = 항목 if isinstance(항목, dict) else {}
    글id = _마당글(항목.get("id"), 20)
    있는 = {x.get("id") for 종류 in ("의견", "제안") for x in _마당줄들(_마당파일(종류))}
    if not 글id or 글id not in 있는:
        return {"ok": False, "로그": "그런 글이 없습니다"}
    이전 = _마당처리들().get(글id, {})
    새 = {k: 이전[k] for k in ("상태", "답변", "숨김") if k in 이전}
    if "상태" in 항목:
        if 항목["상태"] not in _마당상태:
            return {"ok": False, "로그": "상태는 " + "·".join(_마당상태) + " 가운데 하나여야 합니다"}
        새["상태"] = 항목["상태"]
    if "답변" in 항목:
        새["답변"] = _마당글(항목.get("답변"), 300)
    if "숨김" in 항목:
        새["숨김"] = bool(항목.get("숨김") is True)
    새.update({"id": 글id, "시각": time.strftime("%Y-%m-%dT%H:%M:%S")})
    f = os.path.join(_마당경로, "처리.jsonl")
    try:
        os.makedirs(_마당경로, exist_ok=True)
        with 자료뿌리.빗장(f):
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(새, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"[규칙마당] 처리 저장 실패: {type(e).__name__}\n")
        return {"ok": False, "로그": "저장하지 못했습니다"}
    return {"ok": True, "값": {k: 새.get(k) for k in ("id", "상태", "답변", "숨김")},
            "로그": "처리했습니다 — 규칙마당에 바로 보입니다"}


# ── 그림 생성 핸드오프(P2, '26-09-30 주관 판정) ─────────────────────────────────────
# 켜기 = 에이전트가 제 도구 목록에서 본 이미지 도구 이름을 밝힌다(이미지능력). 환경변수 스위치(IMAGEGEN_HOST)는 걷었다 —
# 떠 있는 MCP 서버의 환경은 에이전트가 못 바꾼다(r2/img map_agents E1). 요청 = 조립된 HTML 의 생성 자리(data-gen)와
# 요청 목록(build/assets/manifest.json, id = 프롬프트 해시). 채움 = 에이전트가 그린 파일을 이미지채움에 넘기면 시스템이
# 검사·메타 벗기기·파일 안 'AI 생성물' 표기·복사를 하고 그 그림이 든 문서만 다시 조립한다(검사 기록도 새로 한다).
# 생성 그림을 싣는 곳은 옛 판형 슬라이드 '이미지' 장뿐이다(genres.그림정책 '생성').
_채움확장 = (".png", ".jpg", ".jpeg", ".webp")
_채움시각여유초 = 120


def _채움막는곳():
    """이미지채움 경로로 받지 않는 폴더 — 문서지능 자료 폴더 전체(올린 자료·잘라 낸 그림·남의 세션). 올린 실물 사진이
    'AI 생성물'로 들어가거나(표기가 틀린다) 남의 세션 파일을 끌어오지 않게(critic_practice §4-4·critic_impl #22)."""
    out = []
    for f in (자료뿌리.기본뿌리, 자료뿌리.뿌리, 자료뿌리.받은것뿌리):
        try:
            out.append(os.path.realpath(f()))
        except Exception:
            pass
    return out


def _채움원본읽기(경로, 요):
    if not _경로보임():
        raise ValueError("이 연결에서는 파일 경로를 받지 않습니다 — 그림 내용을 content_base64 로 넘겨 주세요")
    p = os.path.realpath(os.path.expanduser(str(경로)))
    if not os.path.isfile(p):
        raise ValueError("그 경로에 파일이 없습니다")
    if not p.lower().endswith(_채움확장):
        raise ValueError("PNG·JPEG·WebP 파일만 받습니다")
    for 막 in _채움막는곳():
        if p == 막 or p.startswith(막 + os.sep):
            raise ValueError("문서지능 자료 폴더 안의 파일(올린 자료·잘라 낸 그림)은 AI 생성물로 넣지 않습니다 — "
                             "이미지 도구가 만든 파일의 경로를 주세요")
    크기 = os.path.getsize(p)
    if 크기 > 20 * 1024 * 1024:
        raise ValueError("그림이 너무 큽니다(20MB 넘음)")
    요청시각 = (요 or {}).get("요청시각")
    try:
        if 요청시각 and os.path.getmtime(p) < float(요청시각) - _채움시각여유초:
            raise ValueError("요청보다 먼저 만들어진 파일입니다 — 이 요청으로 새로 그린 그림만 받습니다")
    except (TypeError, OSError):
        pass
    with open(p, "rb") as f:
        return f.read()


def _그림든문서들(rid):
    """조립된 HTML 에 그 요청 id 의 생성 자리가 있는 문서 [(등록부 이름, filename)]."""
    ia = 자료뿌리.모듈("imageasset")
    out = []
    for 등 in 등록부들():
        try:
            docs = json.load(open(등, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for d in docs if isinstance(docs, list) else []:
            키 = d.get("filename") if isinstance(d, dict) else None
            if not 키:
                continue
            try:
                with open(자료뿌리.산출물(str(키)), encoding="utf-8") as f:
                    html = f.read()
            except OSError:
                continue
            if any(g == rid for _, g, _ in ia.생성자리들(html)):
                out.append((자료뿌리.등록부이름(등), 키))
    return out


def _채움뒤검사(키):
    """다시 조립한 문서의 검사 기록을 새로 한다 — 그림이 들어가면 화면(쪽 나눔)이 바뀌어 옛 기록은 내보내기가 받지 않는다.
    저장(검사 true)과 같은 세 검사, 원문은 이 문서가 처음 받은 것."""
    값 = {"문체검사": 문체검사(key=키), "조판게이트": 조판게이트(key=키)}
    요약 = [f"문체검사 {'PASS' if 값['문체검사'].get('ok') else 'FAIL'}",
          f"조판게이트 {'PASS' if 값['조판게이트'].get('ok') else 'FAIL'}"]
    쓸원문, _ = _검사원문(키, "")
    if str(쓸원문 or "").strip():
        값["지어냈나"] = 지어냈나검수(키, 쓸원문)
        요약.append(f"지어냈나 {'PASS' if 값['지어냈나'].get('ok') else 'FAIL'}")
    else:
        _검사적기(키, "지어냄", True, 건너뜀="원문 없음")
        요약.append("지어냈나 건너뜀(원문 없음)")
    return 값, 요약


@등록("이미지능력", ["도구", "결정"], 읽기=False, 비동기=False,
    설명="그림 생성 능력을 밝힌다(플러그인 전용). 당신의 도구 목록에 이미지 생성 도구가 있을 때만 그 이름을 tool 에 넣어 "
        "켠다(예: Codex image_gen · OpenClaw image_generate · Gemini CLI generate_image · 이미지 생성 MCP). 없으면 켜지 "
        "않는다 — 그러면 생성 요청이 생기지 않고 지시문도 생성을 시키지 않는다. 결정=보기(기본)·켜기·끄기. 켜 두면 "
        "이 대화에서만 유지된다(2시간 무활동이면 잊는다). 새 대화에서는 다시 밝히고 사용자에게 묻는다. CLI 는 대화를 "
        "기억하지 않으므로 그림 요청이 생길 호출마다 image_tool 을 싣는다. 생성 그림을 싣는 곳은 옛 판형 슬라이드 '이미지' "
        "장뿐이다",
    en="imagegen")
def 이미지능력(도구="", 결정=""):
    if os.environ.get("문서지능_웹앱"):
        return {"ok": False, "로그": "웹에서는 그림을 만들지 않습니다 — 그림 생성은 플러그인에서 이미지 도구가 있을 때만 씁니다"}
    ia = 자료뿌리.모듈("imageasset")
    결정 = str(결정 or "").strip() or ("켜기" if str(도구 or "").strip() else "보기")
    if 결정 not in ("보기", "켜기", "끄기"):
        return {"ok": False, "로그": f"결정은 보기·켜기·끄기 가운데 하나입니다 (받은 값: {결정})"}
    # 능력은 대화 단위('26-09-30 주관 판정) — 작업방식(work_mode)과 같은 방식. CLI 는 대화를 모르므로 켜 두지 않고 호출마다
    # 싣게 한다. 세션 열쇠 없는 공유 연결은 붙는 사람 모두가 한 칸이라 켜 두지 않는다(_대화칸 '공유').
    if 결정 == "켜기" and _CLI표면():
        이름 = re.sub(r"\s+", " ", str(도구 or "")).strip()[:60]
        return {"ok": True, "값": {"켜짐": False, "도구": 이름 or None, "호출마다": True},
                "로그": (f"CLI 는 대화를 기억하지 않아 켜 두지 않습니다 — 그림 요청이 생길 호출(new·save·build·imagequeue)마다 "
                        f"\"image_tool\": \"{이름 or '이미지 도구 이름'}\" 을 실어 부르세요. 그리기 전에는 이 대화에서 사용자에게 "
                        "한 줄로 묻습니다(이용 한도를 쓰고 그림 설명이 그 도구의 제공자로 갑니다)")}
    if 결정 == "켜기" and _대화칸().get("공유"):
        return {"ok": False, "로그": "이 연결(세션 열쇠 없는 공유 연결)은 대화를 가르지 못해 그림 생성을 켜 두지 않습니다"}
    if 결정 == "켜기":
        if not str(도구 or "").strip():
            return {"ok": False, "로그": "켤 이미지 도구 이름(tool)이 없습니다 — 당신의 도구 목록에서 본 이름을 넣어 주세요. "
                                       "없으면 켜지 마세요(사진은 사용자에게 청하거나 그림 없이 씁니다)"}
        ia.능력정하기(도구)
    elif 결정 == "끄기":
        ia.능력정하기("")
    능 = ia.능력()
    값 = {"켜짐": bool(능), "도구": (능 or {}).get("도구"), "싣는곳": "옛 판형 슬라이드 '이미지' 장",
         "안싣는곳": "풀버전·보도자료·1페이지·시행문·규정·판형 v2 슬라이드", "수명": "이 대화에서만(2시간 무활동이면 잊음)"}
    if 능:
        로그 = (f"그림 생성: 켜짐({능['도구']}) — 이 대화에서만 유지됩니다(2시간 무활동이면 잊고, 새 대화에서는 다시 밝히고 "
               "묻습니다). 옛 판형 슬라이드 '이미지' 장에만 생성 그림을 요청합니다 — 만들기 전에 "
               "사용자에게 한 줄로 묻고(이용 한도를 쓰고 그림 설명이 그 도구의 제공자로 갑니다), 새문서·조립 응답의 '그림 대기' "
               "목록대로 그려 이미지채움(imagefill)에 넘기세요")
    else:
        로그 = ("그림 생성: 꺼짐 — 생성 요청을 만들지 않습니다. 필요한 사진은 사용자에게 올려 달라고 하거나 그림 없이 씁니다"
               + (" (끄기 전 요청은 이미지대기로 볼 수 있고, 이미 넣은 그림은 그대로 씁니다)" if 결정 == "끄기" else ""))
    return {"ok": True, "값": 값, "로그": 로그}


@등록("이미지대기", ["key"],
    설명="채울 그림 생성 요청 목록 — id·문서·자리·크기·프롬프트. key 를 주면 그 문서만. 그린 파일은 이미지채움(imagefill)"
        "으로만 넣는다(자산 폴더에 바로 놓은 파일은 쓰지 않는다)",
    en="imagequeue")
def 이미지대기(key=""):
    if os.environ.get("문서지능_웹앱"):
        return {"ok": False, "로그": "웹에서는 그림을 만들지 않습니다"}
    ia = 자료뿌리.모듈("imageasset")
    대기 = _그림대기들([str(key)] if str(key or "").strip() else None)
    능 = ia.능력()
    로그 = _그림대기글(대기) or "채울 그림 요청이 없습니다"
    if not 능:
        로그 += ("\n(그림 생성이 꺼져 있습니다 — 이미지 도구가 있으면 "
               + ("그림 요청이 생길 호출마다 image_tool 을 실으세요(CLI 는 대화를 기억하지 않습니다)" if _CLI표면() else
                  "이미지능력(imagegen)에 tool 을 넣어 켜세요(이 대화에서만 유지됩니다)")
               + ". 켜지 않아도 이미 있는 요청은 이미지채움으로 넣을 수 있습니다)")
    return {"ok": True, "값": {"대기": 대기, "능력": {"켜짐": bool(능), "도구": (능 or {}).get("도구")}}, "로그": 로그}


@등록("이미지채움", ["id", "도구", "경로", "내용_base64"], 읽기=False, 승인필요=True,
    설명="그림 생성 요청(id, 이미지대기의 gen-…)에 당신의 이미지 도구가 그린 파일을 넣는다. path(그린 파일의 경로 — "
        "공유 연결에서는 받지 않는다) 또는 content_base64, tool(그린 도구 이름) 필수. 시스템이 형식(PNG·JPEG·WebP)·크기를 "
        "보고 메타데이터를 벗긴 뒤 파일 안에 'AI 생성물' 표기를 심어 복사하고, 그 그림이 든 문서만 다시 조립·검사한다. "
        "올린 자료·웹·스톡 사진은 넣지 않는다(요청보다 먼저 만든 파일은 거절)",
    en="imagefill")
def 이미지채움(id="", 도구="", 경로="", 내용_base64=""):
    if os.environ.get("문서지능_웹앱"):
        return {"ok": False, "로그": "웹에서는 그림을 만들지 않습니다"}
    import base64 as _b64
    ia = 자료뿌리.모듈("imageasset")
    rid = str(id or "").strip()
    요 = ia.요청들().get(rid)
    if not 요:
        return {"ok": False, "로그": f"요청 목록에 '{rid[:30]}' 가 없습니다 — 이미지대기(imagequeue)로 지금 요청의 id 를 보세요"}
    능 = ia.능력()
    도 = re.sub(r"\s+", " ", str(도구 or "")).strip() or (능 or {}).get("도구") or ""
    if not 도:
        return {"ok": False, "로그": "그린 이미지 도구 이름(tool)이 없습니다 — 어떤 도구로 그렸는지 적어 주세요"}
    try:
        if str(경로 or "").strip():
            내용 = _채움원본읽기(경로, 요)
        elif str(내용_base64 or "").strip():
            s = re.sub(r"^data:[^,]*,", "", str(내용_base64).strip())
            if len(s) > 28 * 1024 * 1024:
                raise ValueError("그림이 너무 큽니다(20MB 넘음)")
            내용 = _b64.b64decode(s, validate=False)
        else:
            raise ValueError("그린 파일의 경로(path) 또는 내용(content_base64)이 없습니다")
        값 = ia.채우기(rid, 내용, 도)
    except (ValueError, ia.채움거절) as e:
        return {"ok": False, "로그": f"그림을 넣지 않았습니다 — {e}"}
    except ia.도구없음 as e:
        return {"ok": False, "로그": f"그림을 넣지 못했습니다 — {e}"}
    ia.능력이어가기()
    로그 = [f"{rid} 에 그림을 넣었습니다({값['px'][0]}×{값['px'][1]}, 'AI 생성물' 표기를 파일 안에도 심었습니다)"]
    다시, 검사들 = [], {}
    for 등, 키 in _그림든문서들(rid):
        r = 조립(f"build/{등}-docs.json", only=키)
        if not r.get("ok"):
            로그.append(f"{키}: 다시 조립하지 못했습니다 — {(r.get('로그') or '')[-300:]}")
            continue
        돌리기([sys.executable, "workspace/render_editor_any.py", 키])
        다시.append(키)
        검사값, 요약 = _채움뒤검사(키)
        검사들[키] = 검사값
        로그.append(f"{키}: 다시 조립했습니다 — 검사 결과: " + " · ".join(요약))
    if not 다시:
        로그.append("이 요청이 든 조립된 문서를 찾지 못했습니다 — 조립(build)을 부르면 그림이 실립니다")
    남은 = _그림대기들()
    if 남은:
        로그.append(_그림대기글(남은))
    else:
        로그.append("▸ 남은 그림 대기 없음")
    return {"ok": True, "값": dict(값, 다시조립=다시, 검사=검사들, 남은대기=len({x['id'] for x in 남은})),
            "로그": "\n".join(로그)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("할 수 있는 일:")
        for w in 목록():
            표 = "읽기" if w["읽기"] else "쓰기"
            print(f"  [{표}] {w['이름']:<12}{'(' + ', '.join(w['받는것']) + ')' if w['받는것'] else '':<28}"
                  f"{w['설명']}")
        sys.exit(0)
    이름 = sys.argv[1]
    인자 = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    # 플러그인 CLI 입구 표식 — 내보내기 관문(_플러그인표면)이 이 입구를 사람 없는 입구로 본다.
    os.environ.setdefault("문서지능_표면", "cli")
    # **절단하지 않는다.** 예전 [:4000] 은 `프롬프트조립`(compose) 의 지시문(7천자↑)을 4001자에서
    # 잘라 JSON 을 깨뜨렸다 — CLI 경로로 부른 Codex 가 1~6 전 시나리오에서 막혔다(2026-08-24).
    # 결과를 소비하는 쪽이 필요하면 스스로 자른다(silent 절단이 JSON 을 망치는 게 더 나쁘다).
    print(json.dumps(부르기(이름, 인자), ensure_ascii=False, indent=1))
