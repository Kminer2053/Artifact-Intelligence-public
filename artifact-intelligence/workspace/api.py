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
import hashlib
import importlib.util as _iu
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ROOT 는 **코드뿌리**다(조립기·온톨로지·node_modules 가 여기 있다).
# 운영 자료(등록부·산출물·inbox·요청·이력)가 어디 있는지는 build/자료뿌리.py 한 곳이
# 정한다 — 세션 격리의 주입점이 그것 하나뿐이어야 한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(ROOT, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

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
    "자료들": list, "자료": list, "예시": list,
    "판없이": bool, "n": int,
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
    # 정책 토큰(WP-S6) — 발급/활성/자동등록 op 의 인자. 별칭은 한 곳에 다 둔다.
    "메모": "memo", "지문": "fingerprint", "켜기": "enable", "라벨": "label",
    # 2층 빌드플랜 op(플랜승인) — 한글 인자 키는 MCP 에서 400 을 내므로 별칭 필수.
    "코멘트": "comment",
    # 편집기열기(로컬 편집기 서버) — 포트 인자.
    "포트": "port",
}


def 등록(이름, 받는것=(), 읽기=True, 설명="", en=None, 비동기=True, 승인필요=False,
       관리자=False, 정책=False, 공개발급=False, 숨김=False, 토큰필수=False):
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
                    "숨김": bool(숨김), "토큰필수": bool(토큰필수),
                    "설명": 설명 or (fn.__doc__ or "").strip().splitlines()[0], "함수": fn}
        if en:
            별칭[en] = 이름
        return fn
    return 감싸기


def 돌리기(cmd, timeout=180):
    # env — 지금 세션을 자식에게 물려준다(WP-S2 ②). 세션 열쇠는 스레드 지역값이라
    # (serve.py 가 요청마다 갈아 끼운다) 그냥 두면 자식 프로세스가 못 본다. 안 물려주면
    # 조립기·편집화면 생성기가 **기본 뿌리**에 쓴다 — 등록부는 세션 것을 읽고 산출물만
    # 전역으로 새는, 화면상 아무 이상이 없는 갈라짐이 된다.
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                       env=자료뿌리.자식환경())
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


def _지식조회(정책서버, path):
    """정책서버에서 온톨로지 **조각(path)만** 조회해 TTL 로 짧게 캐시한다 — 사용자 자료는
    안 보내고 온톨로지 path 만 보낸다(정책만-로컬: 사용자 정보보호 우선). TTL 로 정책서버가
    온톨로지를 갱신하면 그 최신성을 따라간다(피드백 루프로 정제되는 규칙이 클라에 반영)."""
    import time as _t
    지금 = _t.time()
    쌍 = _지식캐시.get(path)
    if 쌍 and 쌍[1] > 지금:
        return 쌍[0]
    r = _원격(정책서버, "지식", {"path": path})
    if isinstance(r, dict) and r.get("ok"):
        _지식캐시[path] = (r, 지금 + _지식캐시TTL)
    return r


@등록("지식", ["path"], 설명="1층 온톨로지 조각 조회(점 표기). 빈 값이면 최상위 키 목록. "
    "배포 트리엔 온톨로지가 없어 정책서버에서 이 path 조각만 받아 온다(사용자 자료는 안 나감)",
    en="knowledge", 정책=True, 숨김=True, 토큰필수=True)
def 지식(path=""):
    로컬 = os.path.join(ROOT, "ontology", "ontology.json")
    if not os.path.exists(로컬):
        # 배포 트리엔 온톨로지가 없다(정책만-로컬) — 정책서버에서 이 path 조각만 조회해 캐시한다.
        # 사용자 자료는 안 나가고 온톨로지 path 만 간다. 서버도 미설정이면 fail-closed(배포 안내).
        정책서버 = _정책서버설정()
        if 정책서버:
            return _지식조회(정책서버, path)
        return {"ok": False, "로그": "이 작업은 온톨로지가 필요합니다 — 환경변수 "
                "문서지능_정책서버=https://… 를 설정하세요(온톨로지는 정책서버 뒤에 있습니다). "
                "개발 환경이라면 ontology/ontology.json 을 두십시오."}
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
    if isinstance(node, dict) and len(json.dumps(node, ensure_ascii=False)) > 12000:
        return {"ok": True, "값": None, "키": sorted(node.keys()),
                "로그": "내용이 커서 키만 돌려줍니다 — 더 깊은 path 로 다시 부르세요"}
    return {"ok": True, "값": node}


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


@등록("개인", ["path", "profile"], 설명="개인화 오버레이를 얹은 조회", en="personal")
def 개인(path="", profile="default"):
    cmd = [sys.executable, "personalization/resolve.py", profile]
    if path:
        cmd.append(path)
    return 돌리기(cmd)


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
@등록("저장", ["payload", "판없이"], 읽기=False, 승인필요=True,
    설명="편집 결과를 정본에 반영하고 이력을 남긴 뒤 다시 만든다", en="save")
def 저장(payload, 판없이=None):
    """`판없이` 를 안 주면(None) **판 간격으로 스스로 정한다** — 자동 저장이 초마다
    와도 판은 `판_간격초` 에 하나만 남는다. 명시로 주면 그 값이 이긴다(관리·시험용).
    """
    if not isinstance(payload, dict):
        return {"ok": False, "로그": "payload 가 객체가 아닙니다 — "
                                  "편집 결과 한 벌({doc, ops, …})을 주세요"}
    키 = _저장키(payload)
    if 판없이 is None and 키:
        이제 = time.time()
        # 세션까지 넣어 센다(WP-S2 ②) — 문서 이름은 세션마다 겹칠 수 있다("보고서" 를
        # 둘이 동시에 만든다). 이름만으로 세면 남이 방금 자동저장한 탓에 내 첫 판이
        # 안 생긴다(부록 A-2 가 지목한 `_마지막판` 전역 문제와 같은 뿌리).
        자리 = (자료뿌리.세션열쇠(), 키)
        판만들기 = 이제 - _마지막판.get(자리, 0) >= 판_간격초
        if 판만들기:
            _마지막판[자리] = 이제
        판없이 = not 판만들기
    cmd = [sys.executable, "workspace/apply_edit_any.py", "--payload", "-"]
    if 판없이:
        cmd.append("--판없이")
    r = subprocess.run(cmd, cwd=ROOT, input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, timeout=180,
                       env=자료뿌리.자식환경())     # 세션을 물려준다(돌리기 주석 참고)
    본 = {"ok": r.returncode == 0, "로그": (r.stdout or "") + (r.stderr or "")}
    # 반영에 성공했으면 정본의 새 수정시각을 함께 돌려준다. 화면이 이걸 안 받으면
    # 다음 저장 때 낙관적 잠금이 "그 사이 바뀌었다"며 거부한다 — 우리가 바꿔 놓고.
    # (render_editor_any.py 의 `보내기()` 가 이 필드를 읽는다)
    if 본["ok"] and 키:
        본["수정시각"] = (문서(키).get("값") or {}).get("_수정시각")
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
        return {"ok": 본["ok"], "로그": 본["로그"]}
    cmd = [sys.executable, f"build/{조립기}", 등록부경로]
    if only:
        # 한 건만 — 나머지 문서의 산출 파일은 손도 안 댄다(WP-S2 ②).
        cmd += ["--only", str(only)]
    return 돌리기(cmd)


@등록("문체검사", ["docs"], 읽기=False, 설명="문체 게이트(하드·소프트)", en="stylelint")
def 문체검사(docs="build/samples-docs.json"):
    r = 돌리기([sys.executable, "build/stylelint.py", 등록부길(docs)])
    _규칙세기("문체검사", r.get("로그") or "")
    return r


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


@등록("조판게이트", 읽기=False, 설명="인쇄해 1쪽·어절분리·넘침을 잰다(헤드리스 크롬, 수 초)", en="gate")
def 조판게이트():
    return 돌리기(["bash", "build/render_verify.sh"], timeout=900)


@등록("되돌리기", ["key", "n", "이유"], 읽기=False, 설명="문서를 지정한 판으로 되돌린다", en="revert")
def 되돌리기(key, n, 이유=""):
    # 판 번호는 **`--버전 N`** 으로 넘겨야 한다. 위치 인자로 주면 CLI 가 못 읽고
    # 늘 0 으로 읽어 "버전 0이 없습니다" 만 돌려준다 — 스킬·MCP·웹앱에서 되돌리기가
    # 아예 안 되고 있었다(2026-08-06 B-3 시험에서 걸림).
    cmd = [sys.executable, "history/version.py", "--되돌리기", str(key), "--버전", str(n)]
    if 이유:
        cmd += ["--이유", 이유]
    r = 돌리기(cmd)
    if r["ok"]:
        # 되돌린 문서 내용으로 편집 화면을 새로 굽는다 — 안 하면 편집기가 옛 문서를
        # 계속 임베드해 보여준다(저장 후 apply_edit_any 가 하는 재생성과 같은 결).
        돌리기([sys.executable, "workspace/render_editor_any.py", str(key)])
    return r


@등록("지점지우기", ["key", "n"], 읽기=False,
    설명="되돌림 지점(직접 보관 버전) 하나를 지운다 — 최대 3개 제한에서 자리를 비울 때", en="delpoint")
def 지점지우기(key, n):
    # 되돌리기와 같은 결 — 버전 번호는 --버전 으로 넘긴다(위치 인자면 CLI 가 0 으로 읽는다).
    return 돌리기([sys.executable, "history/version.py", "--지우기", str(key), "--버전", str(n)])


@등록("작업화면갱신", 읽기=False, 설명="편집 화면·구성 설계 화면을 다시 만든다", en="refresh")
def 작업화면갱신():
    r1 = 돌리기([sys.executable, "workspace/render_editor_any.py", "--all"])
    r2 = 돌리기([sys.executable, "workspace/render_editor_any.py", "--skeletons"])
    return {"ok": r1["ok"] and r2["ok"], "로그": r1["로그"] + r2["로그"]}


@등록("승인화면", ["plan"], 읽기=False,
    설명="빌드플랜 → 승인 화면 HTML 을 돌려준다. plan 은 plan_id(세션 플랜) 또는 파일 경로", en="plan")
def 승인화면(plan):
    경로 = plan
    if plan and (os.sep not in str(plan)) and not str(plan).endswith(".json"):
        경로 = 자료뿌리.플랜(plan)      # plan_id → 세션 플랜 경로로 푼다
    try:
        r = subprocess.run([sys.executable, "buildplan/render_plan.py", str(경로), "--stdout", "--web"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30,
                           env=자료뿌리.자식환경())
    except Exception as e:
        return {"ok": False, "로그": f"승인 화면을 만들지 못했습니다 ({type(e).__name__})"}
    if r.returncode != 0:
        return {"ok": False, "로그": (r.stderr or "승인 화면 렌더에 실패했습니다").strip()[:300]}
    return {"ok": True, "값": {"html": r.stdout}}


@등록("관측", ["key"], 읽기=False, 설명="산출물에서 실제 분량·구성을 재어 기록(귀납 재료)", en="observe")
def 관측(key=""):
    cmd = [sys.executable, "build/observe.py"]
    cmd.append(key if key else "--all")
    return 돌리기(cmd)


@등록("되감기", ["key", "무엇"], 읽기=False,
    설명="생성 결과를 구성 설계로 되돌려 본다(scan=관측만, load=플랜에 싣기)", en="rewind")
def 되감기(key="", 무엇="scan"):
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
                            "1페이지 보고서만 지원합니다. 다른 장르는 편집기 저장(save)으로 반영하세요."}
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
    cmd = [sys.executable, "feedback/backtrace.py", "--log"]
    if key:
        cmd.append(key)
    return 돌리기(cmd)


@등록("새문서", ["doc", "장르"], 읽기=False, 승인필요=True,
    설명="3층 JSON 을 등록부에 넣고 조립·편집기까지 만든다", en="new")
def 새문서(doc, 장르="samples"):
    """새로 만드는 길은 '저장'과 다르다 — 저장은 **있는 문서**를 찾아 고치는 길이라
    새 문서를 넘기면 '찾지 못했습니다'로 끝난다. 여기서 등록부에 넣는다."""
    import re as _re
    if not isinstance(doc, dict):
        return {"ok": False, "로그": "doc 이 객체가 아닙니다"}
    키 = (doc.get("filename") or "").strip()
    if not _re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", 키):
        return {"ok": False, "로그": f"문서 이름이 규칙에 안 맞습니다: {키!r} "
                                  f"(영문 소문자·숫자·하이픈)"}
    # 빌드플랜 승인 게이트(사장님 지침 '26-08-25, WP-S3 강화) — 새로 짓는 문서는 **승인된
    # 구성 설계(빌드플랜)**에 매여야 한다. 웹앱은 화면으로 판정→설계 승인→초안을 강제하는데
    # 플러그인엔 UI 가 없어 에이전트가 논스톱으로 달렸다. 그래서 plan_id 를 요구한다: 없으면
    # 설계·승인을 먼저 하라고 막고, 있으면 아래 _플랜승인막힘 이 '승인' 상태를 확인한다(넣기 전에).
    # 이어받기(resume)로 되살린 문서는 이미 승인·완성돼 낸 것이라 면제한다(표식 소거 후 통과).
    _이어 = doc.pop("_이어받음", False)
    if not _이어:
        # plan_id **요구**는 UI 없는 플러그인에서만 건다 — 웹앱(serve.py)은 화면으로 설계·승인을
        # 강제하고 '자료 없이 재등록' 같은 정당한 무플랜 경로(app.html)가 있어, 여기서 또 막으면
        # 웹앱이 깨진다. 승인 확인(_플랜승인막힘)은 양쪽 다: plan_id 가 있으면 승인됐는지 본다.
        if not os.environ.get("문서지능_웹앱") and not (doc.get("plan_id") or "").strip():
            return {"ok": False, "필요한것": "빌드플랜 승인", "로그":
                    "빌드플랜 승인 게이트 — 새 문서는 승인된 구성 설계(빌드플랜)에 매여야 합니다:\n"
                    "  ① 설계지시문내기(composeplan)로 빌드플랜을 짜서 플랜저장(saveplan) → plan_id\n"
                    "  ② 사용자에게 승인화면(plan)을 보여주고 플랜승인(approveplan)으로 '승인' 받기\n"
                    "  ③ 그 plan_id 를 doc 에 넣어 새문서 다시 호출\n"
                    "사람이 구성부터 확인하는 협업 게이트입니다 — 승인 없는 초안 조립을 막습니다."}
        막힘 = _플랜승인막힘([doc])
        if 막힘:
            return 막힘
    등록 = 자료뿌리.등록부(장르)
    if not os.path.exists(등록):
        있는것 = [os.path.basename(x).replace("-docs.json", "") for x in 등록부들()]
        return {"ok": False, "로그": f"모르는 장르: {장르} (있는 것: {있는것})"}
    doc.setdefault("genre", {"samples": "onepage"}.get(장르, 장르))
    doc["_수정시각"] = 자료뿌리.문서수정시각()   # 낙관적 잠금의 표 — 형식은 한 곳에서
    # 등록부에 한 줄 붙이는 일은 **읽고-고치고-쓰는** 세 걸음이라 빗장을 쥐고 한다
    # (적대리뷰 ③). 안 쥐면 둘이 같은 등록부를 각자 읽고 각자 append 해서, 뒤에 쓴
    # 쪽이 앞 쪽의 문서를 통째로 지운다 — 앞 쪽 사용자는 200 ok 를 받아 놓고.
    try:
        with 자료뿌리.빗장(등록):
            cur = json.load(open(등록, encoding="utf-8"))
            if any(d.get("filename") == 키 for d in cur):
                return {"ok": False, "로그": f"'{키}' 는 이미 있습니다 — 다른 이름을 쓰거나 "
                                          f"편집 화면에서 고치세요"}
            cur.append(doc)
            # 원자 쓰기(WP-S2 ③, E-1) — 등록부는 이 세션 문서 전부가 든 **정본 한 파일**이다.
            # 쓰는 도중에 문서목록·조립 subprocess 가 읽으면 반토막 JSON 을 받는다.
            자료뿌리.원자json(등록, cur, indent=2)
    except 자료뿌리.못잠금 as e:
        return {"ok": False, "로그": str(e)}

    # **자기 문서만 조립한다**(WP-S2 ②). 전에는 등록부 전체를 다시 만들어서, 문서를
    # 하나 새로 만들 때마다 같은 세션의 다른 문서 산출물이 전부 다시 써졌다.
    r = 조립(f"build/{장르}-docs.json", only=키)
    if not r["ok"]:
        # 조립이 안 되면 등록부를 되돌린다 — 반쯤 들어간 문서가 남으면 다음이 다 걸린다.
        # **되돌리기는 되돌리기여야 한다**(적대리뷰 ③): 예전에는 조립 전에 떠 둔
        # 스냅샷(`cur[:-1]`)을 통째로 덮어썼다. 조립은 수백 ms~수 초라 그 사이에 남이
        # 성공시킨 문서까지 같이 되감겼다 — 동시 사례이면 등록부가 빈다. 이제 다시
        # 읽어서 **내가 넣은 줄 하나만** 뺀다.
        뺀수, 사고 = _등록부에서한줄빼기(등록, 키)
        고아 = _고아산출물치우기(키)
        말 = "조립하지 못해 되돌렸습니다"
        if 사고:
            말 = "조립하지 못했고 되돌리지도 못했습니다 — " + 사고
        elif 뺀수 != 1:
            말 = f"조립하지 못해 되돌렸습니다 (등록부에서 뺀 줄 {뺀수}개)"
        return {"ok": False, "로그": 말 + ("" if not 고아 else f" · 고아 산출물 {고아}개 치움")
                + "\n" + r["로그"]}
    돌리기([sys.executable, "workspace/render_editor_any.py", 키])
    return {"ok": True, "key": 키, "편집화면": f"workspace/editors/editor-{키}.html",
            "로그": f"'{키}' 를 만들었습니다\n" + r["로그"]
            + f"\n\n▸ 다음(협업): 검사(문체·조판·지어냈나)를 통과시킨 뒤, **편집 화면"
            + f"(workspace/editors/editor-{키}.html)을 사용자에게 열어 리터칭을 받으세요.** "
            + "사용자가 '이대로 좋다'고 확인하기 전에는 내보내기(export) 하지 마세요 — "
            + "이 플러그인은 사람이 단계마다 확인하는 협업 도구입니다."}


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
    with tempfile.NamedTemporaryFile(suffix=".out", delete=False) as fh:
        낼곳 = fh.name
    cmd = [kordoc, 경로, "--format", 형식, "--silent", "-o", 낼곳]
    if 쪽:
        cmd += ["-p", str(쪽)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if not os.path.exists(낼곳) or os.path.getsize(낼곳) == 0:
            return None, (r.stdout or "") + (r.stderr or "") or "읽지 못했습니다"
        본 = open(낼곳, encoding="utf-8", errors="replace").read()
        return (json.loads(본) if 형식 in ("json", "chunks") else 본), ""
    except subprocess.TimeoutExpired:
        return None, "읽는 데 너무 오래 걸립니다"
    finally:
        if os.path.exists(낼곳):
            os.remove(낼곳)


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
    본, 탈 = _kordoc(참, 형식)
    if 본 is None:
        return {"ok": False, "로그": 탈}
    return {"ok": True, "값": 본, "파일": os.path.basename(참)}


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
    등록 = 자료뿌리.코드길("build", f"{장르}-docs.json")
    if not os.path.exists(등록):
        return {"ok": False, "로그": f"'{장르}' 등록부가 없습니다"}
    문서들 = json.load(open(등록, encoding="utf-8"))
    if not 문서들:
        return {"ok": False, "로그": f"'{장르}' 에 실물 문서가 없어 모양을 못 뽑습니다"}

    def 깎기(v, 깊이=0):
        """값을 **모양만 남기고** 줄인다 — 내용을 베끼게 하지 않으려고."""
        if isinstance(v, dict):
            return {k: 깎기(x, 깊이 + 1) for k, x in v.items() if not k.startswith("_")}
        if isinstance(v, list):
            return [깎기(v[0], 깊이 + 1)] if v else []
        if isinstance(v, str):
            return (v[:40] + "…") if len(v) > 40 else v
        return v

    # 가장 채워진 문서를 본으로 삼는다 — 빈 문서를 본으로 주면 키가 빠진다
    본문서 = max(문서들, key=lambda d: len(json.dumps(d, ensure_ascii=False)))
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
    이미지예 = [{"파일": "올린파일.pdf", "쪽": 1, "자를곳": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.3},
              "캡션": "(그림 제목)", "설명": "(※ 근거·출처)", "폭": "60%"}]
    if isinstance(모양.get("장"), list) and 모양["장"] and isinstance(모양["장"][0], dict):
        절들 = 모양["장"][0].get("절")
        if isinstance(절들, list) and 절들 and isinstance(절들[0], dict):
            절들[0].setdefault("표", 표예)
            절들[0].setdefault("도식", 도식예)
            절들[0].setdefault("이미지", 이미지예)
    if "table" in 모양 and not 모양.get("table"):     # 1p — 고정스키마 table 슬롯 채워 보이기
        모양["table"] = {"after_heading": "대안검토", "caption": "(단위 표기)",
                       "header": ["구분", "안A", "안B"], "rows": [["비용", "값", "값"]]}


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
                                      '예: {"우산|개": "10000"}'}
    if 답 is not None and not isinstance(답, dict):
        return {"ok": False, "로그": "어긋남답은 객체여야 합니다 — "
                                  '예: {"우산|개": "10000"} (열쇠는 물음의 id)'}
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
    하위 = _re.compile(r"^\s*([○●◦・·ㅇ])\s*(.+)$")
    셋째 = _re.compile(r"^\s*[-–]\s*(.+)$")
    넷째 = _re.compile(r"^\s*[*※]\s*(.+)$")
    조 = _re.compile(r"^\s*제\s*\d+\s*조")
    번호 = _re.compile(r"^\s*(\d+)\s*\.\s+(.+)$")

    절, 마디, 표수 = [], {2: 0, 3: 0, 4: 0}, 0
    조문수 = 0
    for c in 청크:
        if (c.get("type") or "") == "table":
            표수 += 1
        for 줄 in str(c.get("text") or "").split("\n"):
            줄 = 줄.strip()
            if not 줄:
                continue
            if 조.match(줄):
                조문수 += 1
                continue
            m = 상위.match(줄) or 번호.match(줄)
            if m:
                절.append({"제목": m.group(2).strip()[:40], "항목수": 0})
                continue
            for rx, lv in ((하위, 2), (셋째, 3), (넷째, 4)):
                if rx.match(줄):
                    마디[lv] += 1
                    if 절:
                        절[-1]["항목수"] += 1
                    break

    뼈대 = {
        "절": [x["제목"] for x in 절],
        "절수": len(절),
        "절당_항목": [x["항목수"] for x in 절],
        "위계_깊이": max([lv for lv, n in 마디.items() if n] or [0]),
        "마디수": 마디,
        "표": 표수,
        "조문수": 조문수,
    }
    # 뼈대→장르 귀띔의 문턱(조문수·절수 ≥5)은 규칙이라 build/판별로직.py 에 있다(배포에서 빠짐).
    귀띔 = 자료뿌리.모듈("판별로직").서식귀띔(뼈대)
    return {"ok": True, "값": {"뼈대": 뼈대, "읽은것": 귀띔, "파일": r["파일"]}}


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
    _장르기본 = {"fullreport": 16000, "press": 12000, "regulation": 12000, "slides": 12000, "gongmun": 8000}.get(장르 or "", 8000)
    def _양의(x):
        try:
            return int(x) if x and int(x) > 0 else 0
        except (TypeError, ValueError):
            return 0
    최대토큰 = _양의(_장르토큰.get(장르)) or _양의(_llm설정.get("세션당상한")) or _장르기본
    # 자료는 대개 리스트(타입맵 "자료": list)다 — 문자열로 합쳐야 한다. 리스트를 그대로
    # content 에 실으면 OpenAI 호환 제공자가 422("messages.content Invalid input")로 막는다
    # (2026-08-13 Featherless 실측). 문자열이면 그대로, 아니면 줄바꿈으로 잇는다.
    if isinstance(자료, str):
        사용자글 = 자료
    elif isinstance(자료, (list, tuple)):
        사용자글 = "\n".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
                          for x in 자료)
    else:
        사용자글 = str(자료 or "")
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
             "messages": [{"role": "system", "content": 지시문},
                          {"role": "user", "content": 사용자글}]}
    # User-Agent — 안 붙이면 urllib 기본값('Python-urllib/…')이 Cloudflare 봇 차단(error 1010,
    # HTTP 403)에 걸린다(Featherless 가 CF 뒤에 있다, 2026-08-10 실측). 정식 클라이언트 UA 를 붙인다.
    헤더.setdefault("User-Agent", "artifact-intelligence/1.0 (+https://github.com/Kminer2053/Artifact-Intelligence)")
    req = urllib.request.Request(url, data=json.dumps(몸).encode("utf-8"),
                                 headers=헤더, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            답 = json.load(r)
    except urllib.error.HTTPError as e:
        # 제공자 응답 본문(왜 막혔나 — 모델 없음·권한 등)을 진단에 싣는다. **키는 요청
        # 헤더에만 있고 응답 본문엔 없다** — 로그·오류에 담겨도 유출이 아니다.
        몸글 = ""
        try:
            몸글 = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise RuntimeError(f"제공자 HTTP {e.code}: {몸글}")
    if cfg["제공자"] == "anthropic":
        글 = "".join(b.get("text", "") for b in (답.get("content") or []))
    else:
        글 = (((답.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    return _JSON뽑기(글)


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
                    _t2.sleep(1.5 * (시도 + 1))
        if doc is not None:
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
    글 = str(자료 or "")
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
    글 = str(자료 or "")
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


def _지시문조립(자료, 장르="samples", 예시=None, 추가지시="", 유형id=None):
    """초안 생성용 시스템 프롬프트를 **서버에서** 만든다(온톨로지 원문은 나가지 않는다).
    기존 app.html 의 규칙모으기()+지시문() 을 그대로 옮기되, 12유형 전체 대신 판정된
    유형 하나의 시퀀스만 싣는다."""
    한장 = (장르 == "samples")
    정본 = _장르정본(장르)
    장르규칙 = 지식("document_types." + str(정본))
    장르값 = 장르규칙.get("값")
    if 장르값 is None:
        장르값 = {"키": 장르규칙.get("키")}
    모양 = ((본(장르).get("값") or {}).get("모양"))
    시각 = (지식("data_elements.시각자료").get("값")) or {}
    시각의미 = 시각.get("의미구조_유형") or 시각
    선택 = None
    if 한장:
        if 유형id:
            _ts = 지식("document_types.onepage-report.구성.목차로직.types").get("값") or []
            선택 = next((t for t in _ts if t.get("id") == 유형id), None)
        선택 = 선택 or _유형판정(자료)
    부 = ["너는 대한민국 공공기관 문서를 만드는 도구다. 아래 **정본 규칙만** 따른다.",
         "지금 만드는 것: " + str(정본), "",
         "[이 문서 종류의 규칙]",
         json.dumps(장르값, ensure_ascii=False, indent=1)[:6000]]
    if 한장:
        if 선택:
            부 += ["",
                  "[보고목적 유형과 목차 — 이 자료에 맞게 판정된 유형이다. 이 □ 시퀀스 순서를 따르라]",
                  json.dumps({"id": 선택.get("id"), "이름": 선택.get("label"),
                              "표준시퀀스": 선택.get("표준시퀀스"),
                              "압축시퀀스": 선택.get("압축시퀀스")}, ensure_ascii=False, indent=1)]
        부 += ["", "[요약박스]",
              json.dumps(지식("entities.요약박스").get("값"), ensure_ascii=False, indent=1),
              "", "[본문]",
              json.dumps(지식("entities.본문").get("값"), ensure_ascii=False, indent=1)]
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
    부 += ["", "[공통으로 지킬 것]",
          "· 없는 사실을 지어내지 마라. 자료에 없으면 그 항목을 빼라. 수치를 만들어 내지 마라.",
          "· 문체는 이 문서 종류의 규칙을 따른다 — 1p·풀버전은 개조식 명사형, 시행문은 서술어 완결+공손체,",
          "  보도자료는 서술형, 규정은 조문체다. 섞지 마라.",
          "",
          "[표·도식·이미지 — 기본은 텍스트, 아래 의미구조가 잡힐 때만 시각요소로 승격 (억지로 넣지 마라)]",
          (json.dumps(시각의미, ensure_ascii=False, indent=1)[:1500] if 시각의미 else ""),
          "· 넣는 자리: 절 안에 \"표\"·\"도식\"·\"이미지\" 키로(돌려줄 모양의 예시 구조 그대로). 1p 는 top 의 \"table\".",
          "· 도식 type: 절차=process, 되돌아오면 cycle, 수렴 converge, 관계·구조 strategy/relation, 차트 line/bar/donut/hbar/stack.",
          "· 도식·표는 반드시 그 절의 \"도식\"·\"표\" 키에 위 예시 구조(스펙)로 넣어라. 본문 항목 text 에 \"[도식] …\"·\"[표] …\"·\"[그림] …\" 처럼 자리표시 설명만 쓰지 마라 — 시스템이 그리지 못한다. 도식으로 만들 수 없으면 그 내용을 대괄호 없는 평범한 설명 문장으로 풀어 써라.",
          "· 표는 수치·비교(대안 비교·현행vs개선·일정표)일 때. 이미지는 상황 설명·가상 시뮬·예시에 효과적일 때만 — 1차로 올린 첨부에서 잘라(\"파일\"·\"쪽\"·\"자를곳\") 쓰고, 적합한 첨부가 없으면 \"출처\":\"생성\"·\"프롬프트\"로 AI 생성을 요청한다(자동으로 'AI 생성물' 표기가 붙는다). 시뮬레이션·사실적 장면이면 \"실사\":true 를 함께 넣는다(고품질 실사로 나감). 도해·차트·로고는 생성 말고 도식(SVG)·첨부로.",
          "",
          "[돌려줄 것 — JSON 하나만, 다른 말 없이]"]
    if 한장:
        부.append('{"filename":"영문소문자-하이픈","title":"제목","byline":"<부서, \'26. 8. 5.>",\n'
                 ' "summary":"…보고드림","purpose_type":"' + str((선택 or {}).get("id") or "②") + '",\n'
                 ' "sections":[{"heading":"검토결과","items":[{"level":2,"html":"…"},{"level":3,"html":"…"}]}],\n'
                 ' "table":null,"attach":null}')
    elif 모양:
        _키목록 = ", ".join(f'"{k}"' for k in 모양.keys())
        부 += ["아래는 이 문서 종류의 **실제 모양**이다(등록부의 실물에서 뽑은 것).",
              "",
              "[반드시 지킬 키 규칙 — 어기면 문서가 통째로 비어 버린다]",
              "· **최상위 키는 정확히 이것들만 쓴다(한글 그대로). 번역·개명·영문화 절대 금지: " + _키목록 + "**"]
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
        부 += ['· **제목·본문·항목에 번호·마커를 붙이지 마라** — 장 번호(Ⅰ.Ⅱ.)·조 번호(제N조)·절 마커(□)·항목 마커(○·-·※)는 시스템이 자동으로 붙인다. 순수 문구만 써라.',
              "· 아래 모양의 키·중첩 구조를 **글자 그대로** 따르고 값만 새로 채워라(값은 베끼지 마라).",
              "",
              json.dumps(모양, ensure_ascii=False, indent=1)[:6000],
              "",
              '"filename" 은 영문 소문자·하이픈으로 반드시 넣어라. **그 밖의 키 이름은 위 한글 그대로, 하나도 바꾸지 마라.**']
    else:
        부 += ["이 문서 종류의 정본 구조를 그대로 따르는 JSON. \"filename\" 은 영문 소문자·하이픈으로 반드시 넣어라.",
              "**주의: 이 종류의 실물 본을 못 가져왔다 — 키를 지어내지 말고 사용자에게 알려라.**"]
    if 추가지시:
        부 += ["", str(추가지시)]
    return "\n".join(x for x in 부 if x is not None)


def _설계지시문조립(자료, 장르="samples", 유형id=None, 추가지시=""):
    """**2층 빌드플랜(작성 계획)** 을 짜는 시스템 프롬프트를 서버에서 만든다 — _지시문조립
    (초안용)과 같은 온톨로지를 당기되, 본문 대신 **buildplan/schema.json 구조의 설계 JSON**
    을 요청한다. '방법론까지만'(2층 경계)을 못박고, 실제 개수·문구·표 등장은 3층으로 미룬다."""
    한장 = (장르 == "samples")
    정본 = _장르정본(장르)
    장르규칙 = 지식("document_types." + str(정본))
    장르값 = 장르규칙.get("값") or {"키": 장르규칙.get("키")}
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
         json.dumps(장르값, ensure_ascii=False, indent=1)[:5000]]
    if 한장 and 선택:
        부 += ["",
              "[이 자료에 맞게 판정된 보고목적 유형과 목차 시퀀스 — 설계의 뼈대로 삼아라]",
              json.dumps({"id": 선택.get("id"), "이름": 선택.get("label"),
                          "표준시퀀스": 선택.get("표준시퀀스"),
                          "압축시퀀스": 선택.get("압축시퀀스")}, ensure_ascii=False, indent=1)]
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
         "}",
         "",
         "[경계 — 반드시 지켜라]",
         "· 2층은 **방법론까지만** 정한다. 실제 □·○ 개수, 절 최종 문구, 표 등장 여부는 정하지 마라 — 자료를 보고 3층(초안)에서 정한다.",
         "· 안 정한 것은 '미확정_3층위임'에 반드시 적어라(경계를 지켰다는 증거다).",
         "· 모호한 것을 지어내지 마라 — '요구분석.확인필요'에 질문으로 남겨라(성실하기보다 되묻는다)."]
    if 추가지시:
        부 += ["", str(추가지시)]
    return "\n".join(x for x in 부 if x is not None)


@등록("판정", ["자료", "예시"],
    설명="자료로 장르를 규칙 판정한다 — 판별신호는 서버에만 두고 점수·까닭만 낸다(브라우저 고름용)",
    en="detect", 정책=True)
def 판정(자료="", 예시=None):
    """브라우저 신호읽기() 를 서버로 옮긴 것 — 장르판별.신호(정본)를 여기서만 읽고
    등록부별 점수·까닭만 돌려준다. 판별신호 자체는 클라이언트로 안 나간다."""
    글 = str(자료 or "")
    신호 = 지식("장르판별.신호").get("값") or {}
    장르목록 = 장르().get("값", {}).get("장르") or []
    # 세는 법·가중치·1p↔풀버전 판별 문구·문턱은 **규칙**이라 build/판별로직.py 에 있다
    # (배포 트리에서 빠짐 · A1 에만 산다). 신호는 온톨로지, 규칙은 이 모듈 — 둘 다 서버에만
    # 있어 클라 소스로 안 샌다(유출 감사 2026-08-18: 전엔 이 함수에 문구·가중치가 박혔다).
    로직 = 자료뿌리.모듈("판별로직")
    return {"ok": True, "값": 로직.점수매기기(글, 신호, 장르목록, 예시, _유형점수)}


@등록("프롬프트조립", ["자료", "장르", "유형id", "예시", "추가지시"],
    설명="서버가 온톨로지로 조립한 완성 시스템 프롬프트만 돌려준다(원문은 안 나간다) — 키 있는 브라우저가 이걸로 직접 모델을 부른다",
    en="compose", 정책=True)
def 프롬프트조립(자료, 장르="samples", 유형id=None, 예시=None, 추가지시=""):
    return {"ok": True, "값": {"지시문": _지시문조립(자료, 장르, 예시, 추가지시, 유형id)}}


@등록("요청내기", ["자료", "장르", "유형id", "예시", "추가지시", "지시문"], 읽기=False,
    설명="AI 에게 초안을 부탁하는 요청을 대기열에 남긴다(키 없이 쓰는 길). 지시문을 안 주면 서버가 온톨로지로 조립한다",
    en="ask")
def 요청내기(자료="", 장르="samples", 유형id=None, 예시=None, 추가지시="", 지시문=None):
    import time as _t, uuid
    지시 = 지시문 if 지시문 else _지시문조립(자료, 장르, 예시, 추가지시, 유형id)
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
    pid = plan.get("plan_id") or (_t.strftime("plan-%m%d-%H%M%S-") + uuid.uuid4().hex[:4])
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
    지시 = _설계지시문조립(자료, 장르, 유형id, 추가지시)
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
    return html


@등록("내보내기", ["key", "형식"], 읽기=False,
    설명="문서를 json·md·html·pdf·hwpx·pptx 로 낸다. hwpx 는 정본 실측 수치를 그대로 "
        "먹이고, pptx 는 발표 슬라이드 전용(편집 가능한 네이티브 요소)이다",
    en="export")
def 내보내기(key, 형식="hwpx"):
    r = 문서(key)
    if not r["ok"]:
        return r
    doc = r["값"]
    # 웹앱처럼 **모든 형식을 한 번에** 낸다(사장님 지침 '26-08-25) — 사용자가 전부 받아 골라
    # 쓰게. 슬라이드는 HTML·PDF·PPTX, 그 외 세로 A4 장르는 HTML·PDF·HWPX. 각 형식은 아래
    # 형식별 경로를 그대로 재사용한다(전환이지 재생성 아님).
    if 형식 in ("전부", "all", "모두"):
        # 이 문서에 맞는 **모든 형식**: 편집형(HWPX/PPTX)·인쇄(PDF)·웹(HTML)·본문(MD)·원천(JSON).
        # 슬라이드는 세로 A4 가 아니라 HWPX 대신 PPTX. 순서는 주 산출물 먼저, md·json 은 끝에.
        형식들 = (["html", "pdf", "pptx", "md", "json"] if doc.get("genre") == "slides"
                else ["html", "pdf", "hwpx", "md", "json"])
        낸것, 실패 = [], []
        for _f in 형식들:
            rr = 내보내기(key, _f)
            if isinstance(rr, dict) and rr.get("ok"):
                낸것.append({"형식": _f, **(rr.get("값") or {})})
            else:
                실패.append({"형식": _f, "로그": (rr or {}).get("로그", "")})
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
    낼곳 = 자료뿌리.산출물뿌리()
    os.makedirs(낼곳, exist_ok=True)

    if 형식 == "json":
        p = os.path.join(낼곳, f"{key}.json")
        자료뿌리.원자json(p, doc, indent=2)      # 재조립 중 내려받기 = 반쪽 파일(E-5)
        return {"ok": True, "값": {"경로": f"/build/samples/{key}.json"}}

    if 형식 == "html":
        p = os.path.join(낼곳, f"{key}.html")
        if not os.path.exists(p):
            return {"ok": False, "로그": "HTML 이 없습니다 — 조립을 먼저 돌리세요"}
        # 내려받아 단독으로 열리는 자기완결본으로 만든다(CSS/JS 인라인 + 기본 폰트 data: 임베드).
        # 이미 단독본이면(data-inlined) 다시 안 부풀린다 — 멱등. 편집기는 editor-*.html 별도라 무영향,
        # tohwpx·크롬 PDF 는 본문 inline 스타일만 읽으므로 head 인라인에 영향 없음(실측).
        try:
            원 = open(p, encoding="utf-8").read()
            if "data-inlined" not in 원:
                자료뿌리.원자쓰기(p, _단독html(원))
        except Exception as e:
            print(f"[html단독] {key}: {type(e).__name__}: {e}", file=sys.stderr)
        return {"ok": True, "값": {"경로": f"/build/samples/{key}.html"}}

    if 형식 == "pdf":
        # 없으면 **그 자리에서 뽑는다.** 게이트가 만들어 주기를 기다리게 하면
        # 사용자는 "왜 PDF 만 안 되지" 하고 막힌다(2026-08-05 화면 시험에서 걸림).
        htm = os.path.join(낼곳, f"{key}.html")
        if not os.path.exists(htm):
            return {"ok": False, "로그": "HTML 이 없습니다 — 조립을 먼저 돌리세요"}
        p = os.path.join(낼곳, f"{key}.pdf")
        if os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(htm):
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
        if not (os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(htm)):
            return {"ok": False, "로그": "PDF 를 뽑지 못했습니다"}
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
        return {"ok": True, "값": {"경로": f"/build/samples/{key}.pdf",
                                 "크기": os.path.getsize(p)}}

    if 형식 == "pptx":
        # PPTX 전환은 16:9 발표 슬라이드 전용이다 — 세로 A4 장르는 옮길 슬라이드 지면이
        # 없다. hwpx 가 slides 를 거부하는 것(위 1714줄)과 **대칭**으로 명시 거부하고,
        # 미전이=True 로 검사(verify_all)가 '못 뽑은 실패'와 '안 뽑는 게 맞음'을 가른다.
        if doc.get("genre") != "slides":
            return {"ok": False, "미전이": True,
                    "로그": "PPTX 로는 발표 슬라이드만 내보낼 수 있습니다 — 세로 A4 규격 "
                    "문서는 HWPX나 PDF로 내보내세요."}
        htm = os.path.join(낼곳, f"{key}.html")
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
        return {"ok": True, "값": {"경로": f"/build/samples/{key}.pptx",
                                 "크기": os.path.getsize(낼), "되읽기": 말}}

    md = 자료뿌리.모듈("tomd").마크다운(doc)
    mdp = os.path.join(낼곳, f"{key}.md")
    자료뿌리.원자쓰기(mdp, md)                   # E-5
    if 형식 == "md":
        return {"ok": True, "값": {"경로": f"/build/samples/{key}.md"}}

    if 형식 != "hwpx":
        return {"ok": False, "로그": f"모르는 형식: {형식} (json·md·html·pdf·hwpx·pptx)"}

    # **kordoc generate 를 쓰지 않는다.** 그것은 자기 프리셋으로 문서를 다시 만든다 —
    # 우리가 실물 사례 재서 세운 규칙이 남의 규칙으로 덮인다(2026-08-05 사장님 지적).
    # 여기서 하는 것은 생성이 아니라 **전환**이다: 완성된 규격을 HWPX 그릇에 그대로 옮긴다.
    tohwpx = 자료뿌리.모듈("tohwpx")
    낼 = os.path.join(낼곳, f"{key}.hwpx")
    # **doc 을 주지 않고 HTML 경로를 우리가 정해 넘긴다.** doc(dict)을 주면 tohwpx 가
    # 스스로 `import 자료뿌리` 로 산출물 자리를 찾는데, 그 import 는 이 프로세스가
    # 이미 들고 있는 자료뿌리 객체가 아니라 **두 번째 복사본**을 올린다(api.py 는
    # importlib 로 파일에서 바로 불러 sys.modules 에 안 걸어 둔다). 세션 열쇠는
    # 스레드 지역값이라 그 복사본에는 없다 — 그래서 세션 안에서 hwpx 를 내보내면
    # 기본 뿌리를 보고 "HTML 이 없습니다" 로 끝났다(자료뿌리.py 머리말의 '딸린 함정').
    # 2026-08-07 실측: 세션 A 에서 동기 `/api/export`·작업 경로 **둘 다** 같은 실패였고
    # (S4 이전부터 그랬다), 경로를 넘기게 고치자 둘 다 됐다. `낼곳` 은 위에서
    # 자료뿌리.산출물뿌리() 로 잡은 **이 세션의** 자리다.
    ok, 말 = tohwpx.만들기(os.path.join(낼곳, f"{key}.html"), 낼)
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
            return {"ok": False,
                    "로그": f"표준 양식 밖의 서식 {m.group(1)}건이 있어 "
                          f"HWPX 로 옮기지 못했습니다"}
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
    return {"ok": True, "값": {"경로": f"/build/samples/{key}.hwpx",
                             "크기": os.path.getsize(낼)}, "로그": 말}


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
        return None, ('fr-doc 을 찾지 못했습니다 — 이어 고치기는 이 서비스가 낸 HTML'
                      '(안에 <script type="application/json" id="fr-doc"> JSON 섬이 '
                      '있는 것)만 받습니다. 다른 문서로 시작하려면 서식분석·새문서 쪽입니다')
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
    (산출물 41/41 실측) 우리 파일이면 반드시 한쪽에는 있다. **둘 다 있는데 서로
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
    import urllib.request
    import urllib.error
    import webbrowser
    import shutil
    try:
        포트 = int(포트)
    except Exception:
        포트 = 8642
    편집기 = os.path.join(ROOT, "workspace", "editors", f"editor-{key}.html")
    if not os.path.exists(편집기):
        return {"ok": False, "로그": f"편집기 파일이 없습니다: workspace/editors/editor-{key}.html "
                "— 먼저 새문서(new)로 문서를 만들어 편집기를 구우세요"}
    url = f"http://127.0.0.1:{포트}/workspace/editors/editor-{key}.html"
    베이스 = f"http://127.0.0.1:{포트}/"

    def _받나(u, timeout=0.6):
        try:
            with urllib.request.urlopen(u, timeout=timeout) as r:
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
                    "▸ 사용자가 직접 리터칭하도록 두세요. 저장·이력(되돌림 지점)·재조립이 정본에 "
                    "바로 반영됩니다. 손편집은 역추적(backtrace)으로 정본에 반영하고, "
                    "'이대로 좋다' 확인 전엔 내보내지 마세요."
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
          "answers": "어긋남답", "decision": "결정", "item": "항목"}


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
        with urllib.request.urlopen(요청, timeout=920) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        본문 = e.read()
        try:
            return json.loads(본문.decode("utf-8"))
        except Exception:
            return {"ok": False, "로그": f"코어 서버에 못 닿았다: HTTP {e.code} {e.reason}"}
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
    # 온톨로지를 읽는 정책 작업만 정책서버로 위임하되, **사용자 자료를 받는 정책작업
    # (판정·프롬프트조립)은 위임하지 않고 로컬에서 돈다** — 자료가 정책서버로 나가지 않게
    # (정책만-로컬: 사용자 정보보호 최우선, plugin-local-first-architecture). 그런 작업은 로컬
    # 실행 중 지식()이 필요한 온톨로지 조각만 정책서버에서 조회한다. 자료 없는 정책작업
    # (장르·시퀀스·지식)만 위임. 이름별 분기가 아니라 등록부 '정책'+받는것에서 파생(손목록 금지).
    정책서버 = _정책서버설정()
    if 정책서버 and 작 and 작.get("정책") and not _자료작(작):
        return _원격(정책서버, 이름, 인자)
    # 배포 트리엔 온톨로지가 없다(정책서버 뒤에 둔다). 정책작업인데 정책서버도 미설정이고
    # 로컬 온톨로지도 없으면 — 조용한 FileNotFoundError 대신 명시 거절한다(fail-closed, 배포 안내).
    if (작 and 작.get("정책") and not 정책서버
            and not os.path.exists(os.path.join(ROOT, "ontology", "ontology.json"))):
        return {"ok": False, "로그": "이 작업은 온톨로지가 필요합니다 — 환경변수 "
                "문서지능_정책서버=https://… 를 설정하세요(배포 트리엔 온톨로지가 정책서버 뒤에 "
                "있습니다). 개발 환경이라면 ontology/ontology.json 을 두십시오."}
    이름 = 별칭.get(이름, 이름)
    if not 작:
        return {"ok": False, "로그": f"모르는 작업입니다: {이름}",
                "할수있는것": sorted(작업)}
    인자 = {인자별칭.get(k, k): v for k, v in (인자 or {}).items()}
    모르는 = [k for k in 인자 if k not in 작["받는것"]]
    if 모르는:
        return {"ok": False, "로그": f"{이름} 이 안 받는 인자: {모르는} "
                                  f"(받는 것: {list(작['받는것'])})"}
    # 되묻기 관문(WP-S3) — 어느 작업이 막히는가는 등록부의 승인필요 하나에서 온다
    # (이름별 분기 금지). 세 문과 작업시작 스레드가 전부 이 함수를 타므로 관문도
    # 여기 하나다. 관문이 어긋남답을 받아 기록하고, 남은 물음이 있으면 여기서 선다.
    if 작.get("승인필요"):
        막힘 = _되묻기관문(인자)
        if 막힘 is not None:
            return 막힘
    try:
        return 작["함수"](**인자)
    except TypeError as e:
        return {"ok": False, "로그": f"인자가 맞지 않습니다 — {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "로그": "너무 오래 걸립니다"}
    except Exception as e:
        return {"ok": False, "로그": f"{type(e).__name__}: {e}"}


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
    if not str(원문 or "").strip():
        # 원문이 없으면 잴 수 없다 — 조용한 통과가 아니라 명확한 거절이다(규칙 3).
        return {"ok": False, "로그": "자료 원문이 없습니다 — 초안을 무엇과 대조할지 "
                                  "알 수 없어 지어냈는지 잴 수 없습니다"}
    r = 문서(key)
    if not r["ok"]:
        return r
    검 = 자료뿌리.모듈("지어냈나")
    # 이 문서 유형의 시퀀스만 받아 넘긴다(판정 때 확보한 것 — 온톨로지 통째 로컬 read 아님).
    # 정책서버가 설정되면 이 조회도 서버로 위임된다(시퀀스가 정책=True).
    유형id = (r["값"] or {}).get("purpose_type")
    시퀀스 = (부르기("시퀀스", {"유형id": 유형id}).get("값") or []) if 유형id else []
    숫, 이 = 검.재기(str(원문), r["값"], 시퀀스)
    # 몇 건이 걸렸는지만 세션 기록에 남긴다 — 걸린 값 자체는 문서·자료 내용이라
    # 적지 않는다(출시계획 1-6 A안, _규칙세기·어긋남과 같은 결).
    자료뿌리.규칙적기("지어냈나", {"수치": len(숫), "이름": len(이)})
    값 = {"수치": [{"어디": a, "값": b, "곁": c} for a, b, c in 숫],
         "이름": [{"어디": a, "값": b, "곁": c} for a, b, c in 이],
         "갯수": len(숫) + len(이), "물음": 검.물음말(숫, 이)}
    if not 값["갯수"]:
        return {"ok": True, "값": 값, "로그": "원문에 없는 수치·이름 없음 — 지어낸 사실 없음"}
    return {"ok": False, "값": 값,
            "로그": f"원문에 없는 수치 {len(숫)}건 · 이름 {len(이)}건 — 되물어야 합니다\n\n"
                  + 값["물음"]}


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
        },
        "설정깨짐": bool(d.get("_깨짐")),
        "설정경로있음": os.path.exists(자료뿌리.설정길()),
    }}


@등록("관리자설정저장",
    ["세션만료초", "llm키", "모델", "세션당상한", "하루총량", "제공자", "베이스", "표시", "장르토큰"],
    읽기=False, en="admincfgset", 관리자=True,
    설명="관리자 설정 저장 — LLM 제공자·서버·키·모델·상한(장르별 max_tokens 포함)·안내문구와 세션 무반응 시간. 응답에도 키는 마스킹")
def 관리자설정저장(세션만료초=None, llm키=None, 모델=None, 세션당상한=None, 하루총량=None,
             제공자=None, 베이스=None, 표시=None, 장르토큰=None):
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
            아는장르 = {"samples", "fullreport", "gongmun", "regulation", "press", "slides"}
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
    # **절단하지 않는다.** 예전 [:4000] 은 `프롬프트조립`(compose) 의 지시문(7천자↑)을 4001자에서
    # 잘라 JSON 을 깨뜨렸다 — CLI 경로로 부른 Codex 가 1~6 전 시나리오에서 막혔다(2026-08-24).
    # 결과를 소비하는 쪽이 필요하면 스스로 자른다(silent 절단이 JSON 을 망치는 게 더 나쁘다).
    print(json.dumps(부르기(이름, 인자), ensure_ascii=False, indent=1))
