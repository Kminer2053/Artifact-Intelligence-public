#!/usr/bin/env python3
"""범용 인라인 편집기 — 장르를 모르는 편집기 하나로 모든 문서를 다룬다.

편집 대상: 표지 필드 · 요약(사내표준형) · 장 → 절 → 항목 드릴다운 · 박스 7종 ·
          도식 6종 · 표 · 별첨. 목차와 쪽번호는 기계 산출이라 편집 대상이 아니다.

풀버전 특유:
- 스타일 변형 전환(사내표준형 ↔ 정부부처형) + 포인트색 — 같은 3층 내용이 두 판으로 즉시 전환
- 글꼴 3종(내장 표준·명조·한글 원본) — 바꾸면 조판을 다시 잡는다
- 조작할 때마다 재조판 → 문단 분절 방지·줄간격 자동 조정이 즉시 반영, 넘침은 붉은 표식
- 박스 종류 전환 7종은 즉시 미리보기(1p 표 스타일 패턴 이식)
- 도식은 data-fig 스펙을 왕복 — 라벨 수정은 SVG를 즉시 다시 그리고(어절 wrap 이식),
  유형·단계 변경은 스펙에 기록해 재조립 때 반영

저장: ws-edit-<fn> = {doc(3층 구조 복원), instructions, ops} → "고쳐놨어"로 반영
사용: python3 workspace/render_editor_fr.py --all | <filename>
"""
import importlib.util as _iu
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 코드뿌리(CSS·JS·프로파일)

# 산출물·편집 화면·골격은 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# sys.path 를 더 심지 않으려고 파일에서 바로 읽는다(부록 A-1, 정리는 WP-S9).
_사양 = _iu.spec_from_file_location("자료뿌리", str(ROOT / "build" / "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)
# 판형 v2 슬라이드 편집(부품·런·막대) — 따로 둔 조각을 v2 문서에만 끼운다(gen 참고).
# v2 문서를 구울 때만 불러온다('26-09-28 적대 검토 ⑥: 모듈 적재 때 무조건 exec 하면 editor_v2.py 가
# 빠진 배포본에서 1p·풀버전까지 **모든 장르** 편집기 굽기가 FileNotFoundError 로 멈췄다).
_editor_v2 = None
_editor_bar = None


def _막대조각():
    """도식·차트·표 개체 위 막대 조각(workspace/editor_bar.py, '26-09-29). 파일이 빠진 배포본이면 None —
    막대 없이 옛 오른쪽 패널로 굽는다(굽기 자체를 세우지 않는다, v2 조각의 적대 검토 ⑥ 교훈)."""
    global _editor_bar
    if _editor_bar is None:
        try:
            _사양b = _iu.spec_from_file_location("editor_bar", str(Path(__file__).resolve().parent / "editor_bar.py"))
            모듈 = _iu.module_from_spec(_사양b)
            _사양b.loader.exec_module(모듈)
            _editor_bar = 모듈
        except (FileNotFoundError, OSError):
            print("[편집기] editor_bar.py 가 없어 개체 위 막대 없이 굽습니다", file=sys.stderr)
            _editor_bar = False
    return _editor_bar or None


_그림카드상한 = (40, 8 * 1024 * 1024)      # (장 수, 미리보기 data: 합 글자 수)


def _그림범위(fn):
    """편집기 서랍에 실을 받은 자료 파일 — None 이면 거르지 않는다(세션 방 = 이 세션의 자료). api._그림범위 와 같은 판단
    ('26-09-30 주관 판정 M6①): 세션 열쇠가 있거나 여러 사람 웹앱이면 방이 곧 세션이다. 플러그인(열쇠 없는 공유 뿌리·로컬
    편집기 서버 단일세션)은 이 문서에 묶인 자료(imageasset.문서자료 — 새문서·저장 때 적는다)만."""
    import os
    if os.environ.get("문서지능_웹앱") and not os.environ.get("문서지능_단일세션"):
        return None
    try:
        if 자료뿌리.세션열쇠():
            return None
        return 자료뿌리.모듈("imageasset").문서자료(fn) if fn else []
    except Exception:
        return []


def _개발트리():
    """자료뿌리가 곧 코드 체크아웃(개발 트리)인가 — 그러면 편집기에 받은 자료의 그림 흔적(썸네일·표지)을 싣지 않는다
    (추적되는 정본 편집기에 박히지 않게, review_impl2 M6②). 못 가리면 참(싣지 않는 쪽)."""
    import os
    try:
        _코 = os.path.realpath(자료뿌리.코드뿌리())
        return (os.path.realpath(자료뿌리.뿌리()) == _코 and os.path.basename(os.path.dirname(_코)) == "skill"
                and os.path.isdir(os.path.join(_코, "..", "..", ".git")))
    except Exception:
        return True


def _그림표지달기(src, 카드):
    """비밀 표지가 있는 자료에서 온 그림 블록에 등급 확인 칩 글(data-mark-note)을 심는다 — **편집기 HTML 에만**('26-09-30
    주관 판정 ①). 조립 HTML·산출물에는 표지 낱말을 싣지 않는다. 카드는 id 로만 찾는다(대화 범위와 무관 — 이미 실린 그림)."""
    import html as _h
    표지 = {c["id"]: c["비밀표지"] for c in 카드 or [] if c.get("id") and c.get("비밀표지")}
    if not 표지:
        return src

    def 달기(m):
        속 = m.group(0)
        if "data-mark-note=" in 속 or "data-miss=" in 속:
            return 속
        k = re.search(r'data-img="([^"]*)"', 속)
        try:
            cid = (json.loads(_h.unescape(k.group(1))) or {}).get("그림") if k else None
        except (ValueError, AttributeError):
            cid = None
        if not (isinstance(cid, str) and cid in 표지):
            return 속
        글 = f"등급 표시 확인: '{표지[cid]}' 표시가 있는 자료의 그림"
        return 속[:-1] + f' data-mark-note="{_h.escape(글, quote=True)}">'
    return re.sub(r'<div class="blk fr-fig fr-img[^"]*"[^>]*>', 달기, src)


def _그림카드조각(fn="", doc=None, 장르=""):
    """그림 막대 '바꾸기' 목록(그림 P3 '26-09-30) — 올린 자료에서 시스템이 꺼낸 그림 카드(imageasset 목록)를 편집기에
    JSON 으로 심는다. 미리보기는 data: 로 박는다(받은 자료 폴더는 편집기 서버가 내주지 않는다 — serve.py GET 목록 밖).
    쓸 수 있는 그림만, 받은 자료 폴더의 _그림/ 안 PNG 만 읽는다. 목록은 다시 만들지 않는다(읽기만 — PIL 없는 파이썬에서도).
    ('26-09-30 주관 판정) 이 문서(세션)에 올린 자료의 그림만 싣는다(_그림범위)."""
    import base64
    import os
    # 자료뿌리가 곧 코드 체크아웃이면(개발 트리) 싣지 않는다 — verify_all 이 --all 로 **추적되는** 정본 편집기를 다시 쓸 때
    # 코드뿌리 받은 자료의 썸네일이 박혀 git 에 들어갈 수 있다('26-09-30 fixup, review_impl2 M6). 세션 방·플러그인 설치
    # 폴더·웹앱 자료뿌리는 코드 체크아웃이 아니다.
    if _개발트리():
        return ""
    try:
        ia = 자료뿌리.모듈("imageasset")
        범위 = _그림범위(fn)
        카드 = ia.카드들(갱신=False, 파일들=범위)
        받은 = os.path.realpath(자료뿌리.받은것뿌리())
        폴더 = os.path.realpath(ia.그림폴더())
    except Exception as exc:
        print(f"[편집기] 그림 목록을 못 읽었습니다: {type(exc).__name__}", file=sys.stderr)
        return ""
    out, 합 = [], 0
    for c in 카드:
        # 글·선 그림(도식·표 캡처로 보이는 것)은 모델 목록에서는 '쓰지 않음'이지만 사람은 서랍에서 고를 수 있다('26-09-30 fixup)
        if not (c.get("쓸수있음") or c.get("종류") == "도식·글 그림") or not c.get("id") or not c.get("미리보기"):
            continue
        p = os.path.realpath(os.path.join(받은, c["미리보기"]))
        if not p.startswith(폴더 + os.sep) or not os.path.isfile(p):
            continue
        with open(p, "rb") as f:
            b = f.read()
        if b[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        uri = "data:image/png;base64," + base64.b64encode(b).decode("ascii")
        if 합 + len(uri) > _그림카드상한[1]:
            break
        합 += len(uri)
        out.append({"id": c["id"], "자리": ia._자리말(c), "종류": c.get("종류") or "", "곁글": (c.get("곁글") or "")[:80],
                    "비밀표지": c.get("비밀표지") or "", "src": uri})
        if len(out) >= _그림카드상한[0]:
            break
    # 쓰지 않은 한글·워드 문서 속 사진(P2 '26-09-30) — 서랍이 '사진이 든 자료를 올려 주세요'라고 앞뒤 안 맞게 말하지 않게
    # 확인할것과 같은 줄(imageasset.확인줄들)을 이어 싣는다('26-10-01 주관 판정 P5 — 같은 인자: 이 문서에 실린 그림 id·이 문서의
    # 자료 범위·장르의 그림 자리. 도구 검사(도구없나)는 읽기만 하는 이 프로세스에서도 한 번 한다 — verify_fixup8 N4)
    try:
        실린 = set(re.findall(r'"그림"\s*:\s*"(img-[0-9a-f]{6,40})"', json.dumps(doc, ensure_ascii=False))) \
            if isinstance(doc, dict) else set()
        자리 = True
        if 장르:
            try:
                자리 = bool(자료뿌리.모듈("genres").그림정책값(장르, "v2" if isinstance(doc, dict) and doc.get("판형") == "v2"
                                                             else None).get("자리"))
            except Exception:
                자리 = True
        알림 = " ".join(ia.확인줄들(카드, 자리=자리, 실린=실린, 범위=ia._받은파일들() if 범위 is None else 범위))
    except Exception as exc:
        print(f"[편집기] 그림 알림을 못 지었습니다: {type(exc).__name__}", file=sys.stderr)
        알림 = ""
    조각 = ""
    if 알림:
        조각 += ('<script type="application/json" id="img-cards-note">'
               + json.dumps(알림, ensure_ascii=False).replace("</", "<\\/") + '</script>')
    if out:
        조각 += ('<script type="application/json" id="img-cards">'
               + json.dumps(out, ensure_ascii=False).replace("</", "<\\/") + '</script>')
    return 조각


def _v2조각():
    global _editor_v2
    if _editor_v2 is None:
        _사양v2 = _iu.spec_from_file_location("editor_v2", str(Path(__file__).resolve().parent / "editor_v2.py"))
        모듈 = _iu.module_from_spec(_사양v2)
        _사양v2.loader.exec_module(모듈)
        _editor_v2 = 모듈
    return _editor_v2

SAMPLES = Path(자료뿌리.산출물뿌리())
EDITORS = Path(자료뿌리.편집화면뿌리())

# WP-F1 마무리 — 편집기 크롬(조작 UI)을 브랜드 토큰으로(흰 테마, 사장님 판정 2026-08-08).
# **문서 영역 셀렉터·구조는 그대로 두고 색 값만 토큰으로 간다** — body/.fr-page 오버라이드
# 같은 구조 규칙을 건드리면 편집 중 레이아웃이 달라져 §4-3 "문서 영역 스타일은 손대지
# 마라"를 어긴다. 이 화면엔 애초에 다크 모드 토글이 없었다 — edit-bar 가 밝기와 무관하게
# 늘 Ink 배경인 것도 토글과는 별개다(ui-tokens.css 의 --ai-color-*-on-dark 3색 주석 참고).
# 토큰 파일은 산출 위치가 갈린다(workspace/editors/ 와 buildplan/skeletons/edit/) — gen() 이
# @@TOKENS_HREF@@ 를 그 자리에 맞는 상대경로로 채운다(SCRIPT 의 @@FN@@ 치환과 같은 방식).
CHROME = """
<link rel="stylesheet" href="@@TOKENS_HREF@@" data-editor>
<style data-editor>
  body { padding-top: 46px !important; margin-left: 260px !important; margin-right: 268px !important; }
  /* ── 좌측 편집이력 레일 — 3단(좌 이력 / 가운데 뷰어 / 우 옵션)의 왼쪽 기둥.
     history 부르기의 판(버전)을 최신순으로 상시 표출한다(서버 있을 때만; file:// 면 안내). */
  .hist-panel { position: fixed; top: 46px; left: 0; bottom: 0; width: 260px; z-index: 98;
    overflow-y: auto; background: var(--ai-color-white); border-right: 1px solid var(--ai-color-line);
    padding: 13px; font: 13px/1.5 var(--ai-font-sans); box-sizing: border-box; }
  .hist-panel h3 { font-size: 12px; color: var(--ai-color-muted); margin: 0 0 8px; font-weight: 600; }
  .hist-panel .hrow { padding: 7px 0; border-top: 1px solid var(--ai-color-line); }
  .hist-panel .hrow:first-of-type { border-top: none; }
  .hist-panel .hrow.now { background: var(--ai-color-signal-tint); margin: 0 -6px; padding: 7px 6px; border-radius: var(--ai-radius-sm); }
  .hist-panel .hrow .hwhen { font-size: 11px; color: var(--ai-color-muted); }
  .hist-panel .hrow .hwhy { font-size: 12px; }
  .hist-panel .hrow button { margin-top: 4px; border: none; border-radius: var(--ai-radius-sm);
    padding: 3px 9px; font: 12px var(--ai-font-sans); background: var(--ai-color-signal);
    color: var(--ai-color-white); cursor: pointer; }
  .hist-panel .hmark { font-size: 10.5px; color: var(--ai-color-muted); text-transform: uppercase; letter-spacing: .04em; }
  /* 슬라이드 줌 — 16:9(960pt) 가 3단 중앙에 안 들어가 잘리던 것을 맞춤/확대·축소(사장님 지적 0904).
     zoom 은 레이아웃까지 스케일해 넘침·빈틈이 없다(크로미움). 자유배치 좌표는 rect 비율이라 무영향. */
  .sl-page { zoom: var(--sl-zoom, 1); }
  .sl-zoomctl { position: fixed; bottom: 16px; left: calc(260px + 16px); z-index: 96;
    display: flex; align-items: center; gap: 2px; background: var(--ai-color-white);
    border: 1px solid var(--ai-color-line); border-radius: 999px; padding: 3px 5px;
    box-shadow: 0 3px 12px color-mix(in srgb, var(--ai-color-ink) 12%, transparent); font: 12px var(--ai-font-sans); }
  .sl-zoomctl button { border: none; background: none; cursor: pointer; width: 26px; height: 24px;
    border-radius: 6px; font-size: 15px; color: var(--ai-color-ink); }
  .sl-zoomctl button:hover { background: var(--ai-color-signal-tint); }
  .sl-zoomctl .sl-zval { min-width: 44px; text-align: center; font-variant-numeric: tabular-nums;
    color: var(--ai-color-muted); cursor: pointer; }
  /* AI 재작성 잠금 — 그 동안 편집기를 덮어 다른 조작을 막는다(사장님 지적 0904). */
  .ai-lock { position: fixed; inset: 0; z-index: 200; display: none; align-items: center;
    justify-content: center; background: color-mix(in srgb, var(--ai-color-ink) 30%, transparent); cursor: wait; }
  .ai-lock-box { background: var(--ai-color-white); border-radius: 14px; padding: 18px 24px;
    display: flex; gap: 13px; align-items: center; box-shadow: 0 12px 40px color-mix(in srgb, var(--ai-color-ink) 28%, transparent);
    font: 14px var(--ai-font-sans); color: var(--ai-color-ink); max-width: 80vw; }
  .ai-lock-spin { width: 18px; height: 18px; flex: none; border-radius: 50%;
    border: 2.5px solid var(--ai-color-line); border-top-color: var(--ai-color-signal);
    animation: ai-lock-rot .8s linear infinite; }
  @keyframes ai-lock-rot { to { transform: rotate(360deg); } }
  .fr-page { margin-left: auto !important; margin-right: auto !important; }   /* 문서를 편집 영역 가운데로 */
  .edit-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 99; background: var(--ai-color-ink);
    color: var(--ai-color-white); font: 13px/1.4 var(--ai-font-sans);
    padding: 7px 14px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }
  .edit-bar .grp { display: flex; gap: 6px; align-items: center; }
  .edit-bar button { border: none; border-radius: var(--ai-radius-sm); padding: 5px 10px; font: inherit;
    background: color-mix(in srgb, var(--ai-color-white) 16%, transparent);
    color: var(--ai-color-white); cursor: pointer; transition: background var(--ai-motion-fast); }
  .edit-bar button:hover { background: var(--ai-color-signal); }
  .edit-bar button.on { background: var(--ai-color-signal); color: var(--ai-color-white); font-weight: 700; }
  .edit-bar .st { color: var(--ai-color-muted-on-dark); } .edit-bar .st.on { color: var(--ai-color-signal-on-dark); }
  .edit-bar .warn { color: var(--ai-color-issue-on-dark); font-weight: 700; }
  .edit-bar input[type=color] { width: 26px; height: 22px; border: none; background: none; padding: 0; }
  .font-switcher { display: none !important; }
  .crop-wrap { position: relative; display: inline-block; }
  .crop-sel { pointer-events: none; }
  /* 못 얻은 그림 — 산출물에서는 자리를 차지하지 않는 표식(imageasset.render: hidden·data-miss)이다.
     편집기에서만 떠 있는 검토 표지로 보인다. 높이 0 이라 편집기 쪽 나눔도 산출물과 같다.
     쪽 틀(.fr-content)이 넘침을 잘라 여백에는 못 둔다 — 그 자리 바로 위 오른쪽 끝에 작은 표지로 얹는다
     (본문 줄 끝은 대개 비어 있다). 눌러서 고르면 그림 막대(지우기 등)와 까닭이 뜬다. */
  html .fr-img[data-miss] { display: block !important; height: 0; overflow: visible; position: relative;
    margin: 0 !important; padding: 0 !important; border: 0 !important; }
  html .fr-img[data-miss] > :not(.ph) { display: none !important; }
  html .fr-img[data-miss] > .ph { position: absolute; right: 0; top: 0; transform: translateY(-100%); z-index: 5;
    width: auto; margin: 0; padding: 0.6mm 2mm; box-sizing: border-box; font-size: 0; line-height: 0;
    border: 1px dashed var(--ai-color-issue); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-issue-tint); cursor: pointer; }
  html .fr-img[data-miss] > .ph::before { content: "그림 못 실음"; display: block; text-align: center;
    font: 600 10px/1.3 var(--ai-font-sans); color: var(--ai-color-issue-ink); }
  /* 잇단 못 실은 자리(보도자료 붙임사진 두 장 등)는 같은 점에 놓여 칩이 겹쳤다 — 뒤 자리만 눌렸다(verify_fixup3_ux U6).
     잇단 차례(--mi)만큼 아래로 한 칸씩 내려 세로로 쌓는다(첫 칩이 맨 위 — 문서 차례와 같다). */
  html .fr-img[data-miss] + .fr-img[data-miss] { --mi: 1; }
  html .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] { --mi: 2; }
  html .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] { --mi: 3; }
  html .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] { --mi: 4; }
  html .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss] + .fr-img[data-miss]
    + .fr-img[data-miss] { --mi: 5; }
  html .fr-img[data-miss] > .ph { transform: translateY(calc(-100% + var(--mi, 0) * (100% + 2px))); }
  /* 공개 장르(보도자료·옛 판형 발표)에 실린 사진 — 편집기에서만 검토 표지('26-09-30 fixup, review_practice2 N11: 웹앱은
     확인할것 칸을 화면에 싣지 않아 '공개 전 확인' 한 줄이 사용자에게 가지 않았다). 흐름을 밀지 않게 떠 있는 표지로 둔다. */
  /* ('26-09-30 주관 판정 ①) AI 생성 그림(data-gen)은 사진이 아니라 칩을 달지 않는다. 비밀 표지 자료의 그림(어느 장르든)은
     편집기 HTML 에만 심는 data-mark-note(_그림표지달기)로 등급 표시 확인 칩을 단다. ('26-09-30 fixup3 N6) 두 칩은 따로
     선다 — 공개 전 확인은 오른쪽 위(::after), 등급 표시 확인은 왼쪽 아래(::before). 전에는 한 자리를 나눠 써 등급 칩이
     얼굴·차량 번호 칩을 덮었다(verify_fixup2 N6). 웹앱 내보내기 화면에도 같은 뜻의 한 줄(api 내보내기 '그림경고')이 뜬다. */
  html[data-genre="press-release"] .fr-img:not([data-miss]):not([data-gen]),
  html[data-genre="slides"] .fr-img:not([data-miss]):not([data-gen]), html .fr-img[data-mark-note]:not([data-miss]) {
    position: relative; }
  html[data-genre="press-release"] .fr-img:not([data-miss]):not([data-gen])::after,
  html[data-genre="slides"] .fr-img:not([data-miss]):not([data-gen])::after,
  html .fr-img[data-mark-note]:not([data-miss])::before {
    content: "공개 전 확인: 얼굴·차량 번호·보안 시설"; position: absolute; right: 0; top: 0; z-index: 4;
    max-width: 70%; padding: 0.5mm 1.6mm; border: 1px solid var(--ai-color-review-line); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-review-tint); color: var(--ai-color-review-ink);
    font: 600 10px/1.3 var(--ai-font-sans); pointer-events: none; }
  html body .fr-img.fr-fig[data-mark-note]:not([data-miss])::before {
    content: attr(data-mark-note); right: auto; top: auto; left: 0; bottom: 0; }
  @media print { html .fr-img::after, html .fr-img::before { display: none !important; } }
  /* 이어서 하기 / 판 보관 — 화면 맨 위에 붙는 알림 띠. 색은 알림.기다림/나쁨 과 같은
     토큰 쌍(review/issue tint·line·ink)을 쓴다 — app.html 의 같은 뜻 알림과 통일. */
  .resume-bar { position: fixed; top: 46px; left: 260px; right: 268px; z-index: 97;
    background: var(--ai-color-review-tint); border-bottom: 1px solid var(--ai-color-review-line);
    color: var(--ai-color-review-ink); padding: 9px 14px; font: 13px/1.5 var(--ai-font-sans); }
  .resume-bar.danger { background: var(--ai-color-issue-tint); border-bottom-color: var(--ai-color-issue-line);
    color: var(--ai-color-issue-ink); }
  .resume-bar .row { margin-top: 6px; display: flex; gap: 6px; }
  .resume-bar button { border: none; border-radius: var(--ai-radius-sm); padding: 5px 11px; font: inherit;
    background: var(--ai-color-ink); color: var(--ai-color-white); cursor: pointer; }
  /* '좋음'에 해당하는 확정 동작 — 브랜드 6색엔 Mint(AI 전용) 말고 다른 초록이 없어
     Signal Blue 를 쓴다(app.html 의 .알림.좋음 과 같은 결정, 부록 §1-1). */
  .resume-bar button.good { background: var(--ai-color-signal); }
  .resume-bar button.danger { background: var(--ai-color-issue); }
  .panel { position: fixed; top: 46px; right: 0; bottom: 0; width: 268px; z-index: 98;
    overflow-y: auto; background: var(--ai-color-white); border-left: 1px solid var(--ai-color-line);
    padding: 13px; font: 13px/1.5 var(--ai-font-sans); box-sizing: border-box; }
  .panel h3 { font-size: 12px; color: var(--ai-color-muted); margin: 0 0 4px; font-weight: 600; }
  .panel .ent { font-size: 15px; font-weight: 700; color: var(--ai-color-signal); margin-bottom: 2px; }
  .panel .hint { color: var(--ai-color-muted); font-size: 12px; margin: 4px 0 9px; }
  .panel button { display: block; width: 100%; margin: 5px 0; padding: 7px 9px; text-align: left;
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-agent-panel); cursor: pointer; font: inherit; }
  .panel button:hover { background: var(--ai-color-signal-tint); border-color: var(--ai-color-signal); }
  .panel button.sel { background: var(--ai-color-signal); color: var(--ai-color-white); border-color: var(--ai-color-signal); }
  .panel .danger { border-color: var(--ai-color-issue-line); background: var(--ai-color-issue-tint); }
  .panel .danger:hover { background: color-mix(in srgb, var(--ai-color-issue) 20%, var(--ai-color-white)); border-color: var(--ai-color-issue); }
  .panel textarea, .panel input[type=text] { width: 100%; font: inherit; font-size: 12.5px;
    padding: 6px; border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm); box-sizing: border-box; }
  .panel textarea { min-height: 66px; resize: vertical; }
  .panel .row { display: flex; gap: 5px; } .panel .row button { flex: 1; text-align: center; }
  .panel .explain { background: var(--ai-color-signal-tint-2); border-left: 3px solid var(--ai-color-signal);
    padding: 9px 10px; border-radius: 0 6px 6px 0; font-size: 12.5px; line-height: 1.65;
    color: var(--ai-color-ink-soft); margin: 6px 0 4px; }
  .panel .notes { margin-top: 12px; border-top: 1px solid var(--ai-color-line); padding-top: 9px;
    font-size: 12px; color: var(--ai-color-muted); }
  .panel .notes ul { list-style: none; margin: 4px 0 0; padding-left: 2px; }   /* 줄마다 ·/📌 가 붙어 있다 — 점 두 개 안 찍게 */
  .panel .notes li { margin: 3px 0; }
  .ent-sel { outline: 2px solid var(--ai-color-signal) !important; outline-offset: 3px; border-radius: 2px;
    background: var(--ai-color-signal-tint-strong); }
  .has-note { box-shadow: -3px 0 0 0 var(--ai-color-review); }
  [contenteditable="true"] { outline: 2px solid var(--ai-color-signal) !important; background: var(--ai-color-signal-tint); }
  /* ── 슬라이드 자유배치 — 이동 그립(fp-grip)과 8방향 크기 핸들(fp-h). 드래그는 그립·핸들에서만
     시작하므로 본문 클릭(자식 개체 선택·편집)과 안 부딪힌다. ── */
  .sl-free .sl-placed.fp-move { outline: 1.5px dashed var(--ai-color-agent); outline-offset: 2px; }
  .sl-free .sl-placed .fp-grip { position: absolute; left: -1.5px; top: -22px; height: 20px; padding: 0 7px;
    background: var(--ai-color-agent); color: var(--ai-color-white); border-radius: 4px 4px 0 0; cursor: move; z-index: 31;
    display: flex; align-items: center; gap: 4px; font: 11px var(--ai-font-sans); white-space: nowrap; }
  .sl-free .sl-placed .fp-h { position: absolute; width: 12px; height: 12px; background: var(--ai-color-agent);
    border: 2px solid var(--ai-color-white); border-radius: 50%; box-sizing: border-box; z-index: 30; }
  .fp-nw{left:-6px;top:-6px;cursor:nwse-resize} .fp-ne{right:-6px;top:-6px;cursor:nesw-resize}
  .fp-se{right:-6px;bottom:-6px;cursor:nwse-resize} .fp-sw{left:-6px;bottom:-6px;cursor:nesw-resize}
  .fp-n{left:calc(50% - 6px);top:-6px;cursor:ns-resize} .fp-s{left:calc(50% - 6px);bottom:-6px;cursor:ns-resize}
  .fp-e{right:-6px;top:calc(50% - 6px);cursor:ew-resize} .fp-w{left:-6px;top:calc(50% - 6px);cursor:ew-resize}
  #fr-toc .fr-content::after { content: "목차와 쪽번호는 자동으로 만들어집니다";
    position: absolute; left: 0; right: 0; bottom: 3mm; text-align: center;
    font: 10px var(--ai-font-sans); color: var(--ai-color-muted); }
  /* 복사 완료 토스트 — 디자인 앱 v1.1 의 .toast 그대로(흰 배경 + Ink 글자, 색을 안 쓴다) */
  .copy-note { position: fixed; bottom: 14px; left: 42%; background: var(--ai-color-white);
    color: var(--ai-color-ink); padding: 8px 18px; border-radius: 20px; font: 13px var(--ai-font-sans);
    box-shadow: var(--ai-shadow-card); display: none; z-index: 99; }
  /* 능동 동의 카드(WP-S10 2차-B, "리터칭" 훅 — 문구 다듬기 사장님 판정 2026-08-09) — "이 부분
     (비식별)" 같은 알쏭달쏭한 말을 걷어내고 머리에 로고를 얹는다. Mint 는 로고 마크
     하나에만 남긴다(부록 §1-1 "Mint 남용 금지" — 동의 신호는 허용 예외, app.html 의
     .동의카드 와 같은 결정). icons.svg 는 이 편집기의 산출 위치가 둘로 갈려(workspace/
     editors/ 와 buildplan/skeletons/edit/, gen() 의 TOKENS_HREF 참고) <use href> 상대경로가
     자리마다 다르다 — 그 자리표시자를 하나 더 늘리는 대신 logo-mark 의 path 데이터(작은
     정적 마크)를 그대로 인라인해 참조 문제를 아예 없앤다. stroke=currentColor 로 icons.svg
     의 §1-4 규칙(심볼에 색을 안 박고 쓰는 자리에서 켠다)을 그대로 잇는다. */
  .consent-card { position: fixed; right: 14px; bottom: 14px; z-index: 100; width: min(360px, 86vw);
    background: var(--ai-color-white); border-radius: var(--ai-radius-md);
    box-shadow: var(--ai-shadow-card); overflow: hidden; }
  .consent-card .cc-head { display: flex; align-items: center; gap: 9px; padding: 12px 14px 11px;
    border-bottom: 1px solid var(--ai-color-line); }
  .consent-card .cc-head .cc-logo { width: 22px; height: 22px; flex: none; color: var(--ai-color-agent);
    fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .consent-card .cc-head .cc-word { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .consent-card .cc-head .cc-word b { font-family: var(--ai-font-heading); font-weight: 800;
    font-size: 13.5px; color: var(--ai-color-ink); }
  .consent-card .cc-head .cc-word span { font-size: 10.5px; color: var(--ai-color-muted); }
  .consent-card .cc-body { padding: 12px 14px; }
  .consent-card p { margin: 0 0 10px; font: 12.5px/1.6 var(--ai-font-sans); color: var(--ai-color-ink-soft);
    white-space: pre-wrap; }
  /* "왜" 칸(신규) — 선택 입력. 값을 넣고 [남기기] 를 누르면 `지시`(이유)로 실려
     `_항목빚기` 가 비식별한 뒤 코퍼스에 남는다(feedback/corpus.py, 손 안 댐 — 부르기만). */
  .consent-card .cc-why { margin: 0 0 10px; }
  .consent-card .cc-why label { display: block; font-size: 11px; line-height: 1.5;
    color: var(--ai-color-muted); margin-bottom: 4px; }
  .consent-card .cc-why input[type="text"] { width: 100%; box-sizing: border-box; font: inherit;
    font-size: 12px; padding: 6px 8px; border: 1px solid var(--ai-color-line);
    border-radius: var(--ai-radius-sm); }
  .consent-card .cc-why input[type="text"]:focus { outline: none; border-color: var(--ai-color-signal); }
  /* 유의 안내 — 비식별기(feedback/corpus.py)는 메일·링크·숫자·기관·이름을 가리나 완벽하지
     않아 입력칸에서 미리 알린다(사장님 방침 2026-08-09). */
  .consent-card .cc-why .cc-hint { margin: 6px 0 0; font-size: 10.5px; line-height: 1.5;
    color: var(--ai-color-muted); }
  .consent-card .cc-row { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
  .consent-card button { border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    padding: 6px 10px; font: 12.5px var(--ai-font-sans); background: var(--ai-color-white);
    color: var(--ai-color-ink); cursor: pointer; }
  .consent-card button.good { background: var(--ai-color-ink); color: var(--ai-color-white); border: 0; }
  /* 되돌리기 토스트('26-09-28) — 문서 설정(제목 모양)을 바꾼 뒤 5초 동안 [되돌리기]를 붙인다. */
  .copy-note button { margin-left: 10px; border: 0; background: none; padding: 0; cursor: pointer;
    color: var(--ai-color-signal); font: 700 13px var(--ai-font-sans); }
  /* ── 문서 설정 팝오버('26-09-28) — 윗줄 '문서 설정'에서 연다(원칙 5: 개체 하나에 걸리지 않는 것은
     윗줄). 1p·풀버전 = 제목 모양(묶음 썸네일 + 자세히), 보도자료 = 본문 모양. 썸네일은 그림 파일이
     아니라 **이 문서의 CSS 로 그린 작은 조각**(iframe)이라 문서와 어긋나지 않는다. 색은 토큰만. */
  .docset-pop { position: fixed; top: 50px; right: 12px; z-index: 101; display: none;
    width: min(520px, calc(100vw - 24px)); max-height: calc(100vh - 64px); overflow-y: auto;
    box-sizing: border-box; padding: 14px 16px 12px; background: var(--ai-color-white);
    color: var(--ai-color-ink); border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-md);
    box-shadow: var(--ai-shadow-card); font: 13px/1.5 var(--ai-font-sans); }
  .docset-pop.open { display: block; }
  .docset-pop .ds-sec + .ds-sec { border-top: 1px solid var(--ai-color-line); margin-top: 14px; padding-top: 12px; }
  .docset-pop h3 { margin: 0; font-size: 13.5px; font-weight: 700; }
  .docset-pop .ds-sub { margin: 2px 0 10px; font-size: 12px; color: var(--ai-color-muted); }
  .docset-pop .ds-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 9px; }
  .docset-pop .ds-th { display: flex; flex-direction: column; gap: 3px; padding: 6px; text-align: left;
    border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm); background: var(--ai-color-white);
    color: var(--ai-color-ink); font: inherit; cursor: pointer; }
  .docset-pop .ds-th:hover { border-color: var(--ai-color-signal); }
  .docset-pop .ds-th[aria-checked="true"] { border-color: var(--ai-color-signal); box-shadow: 0 0 0 2px var(--ai-color-signal); }
  .docset-pop .ds-th:focus-visible, .docset-pop .ds-opt:focus-visible { outline: 2px solid var(--ai-color-signal); outline-offset: 2px; }
  .docset-pop .ds-pic { position: relative; overflow: hidden; border: 1px solid var(--ai-color-line);
    border-radius: 3px; background: var(--ai-color-white); }
  .docset-pop .ds-pic iframe { position: absolute; left: 0; top: 0; border: 0; transform-origin: 0 0;
    pointer-events: none; }
  .docset-pop .ds-nm { font-size: 12.5px; font-weight: 700; }
  .docset-pop .ds-hint { font-size: 11px; line-height: 1.4; color: var(--ai-color-muted); }
  .docset-pop .ds-hwp { font-size: 11px; line-height: 1.4; color: var(--ai-color-review-ink); }
  .docset-pop .ds-now { margin: 10px 0 0; font-size: 12px; color: var(--ai-color-muted); }
  .docset-pop .ds-note { margin: 6px 0 0; padding: 6px 9px; font-size: 12px; line-height: 1.5;
    background: var(--ai-color-review-tint); border-left: 3px solid var(--ai-color-review-line);
    color: var(--ai-color-review-ink); border-radius: 0 4px 4px 0; }
  .docset-pop details { margin-top: 10px; }
  .docset-pop summary { cursor: pointer; font-size: 12.5px; color: var(--ai-color-signal); }
  .docset-pop .ds-row { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; margin: 7px 0; }
  .docset-pop .ds-lb { width: 56px; flex: none; font-size: 12px; color: var(--ai-color-muted); }
  .docset-pop .ds-opt { padding: 3px 10px; border: 1px solid var(--ai-color-line); border-radius: 999px;
    background: var(--ai-color-white); color: var(--ai-color-ink); font: 12px var(--ai-font-sans); cursor: pointer; }
  .docset-pop .ds-opt:hover { border-color: var(--ai-color-signal); }
  .docset-pop .ds-opt[aria-checked="true"] { background: var(--ai-color-signal); border-color: var(--ai-color-signal);
    color: var(--ai-color-white); }
  .docset-pop .ds-foot { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 12px; }
  .docset-pop .ds-foot button { padding: 5px 10px; border: 1px solid var(--ai-color-line); border-radius: var(--ai-radius-sm);
    background: var(--ai-color-white); color: var(--ai-color-ink); font: 12.5px var(--ai-font-sans); cursor: pointer; }
  .docset-pop .ds-foot button.good { background: var(--ai-color-ink); border-color: var(--ai-color-ink); color: var(--ai-color-white); }
  .docset-pop .ds-where { flex-basis: 100%; font-size: 11px; color: var(--ai-color-muted); }
</style>
"""

SCRIPT = r"""
<script data-editor>
(() => {
// 자가검사 — ?selfcheck=1 이면 왕복 불변식을 스스로 확인하고 결과를 제목에 남긴다.
// (정적 패턴 검사는 오탐만 냈다. 진짜 검사는 '저장했다 다시 읽으면 같은가'다.)
if (location.search.includes('selfcheck=1')) {
  setTimeout(async () => {
    const w = ms => new Promise(r => setTimeout(r, ms));
    await w(1400);
    try {
      const el = document.getElementById('fr-doc');
      if (!el) { document.title = 'SELFCHECK skip 모델없음'; return; }
      const src = JSON.parse(el.textContent);
      localStorage.removeItem(KEY);
      document.dispatchEvent(new Event('input'));
      await w(900);
      const saved = (JSON.parse(localStorage.getItem(KEY) || '{}')).doc || {};
      const norm = o => JSON.stringify(o, (k, v) =>
        (v && typeof v === 'object' && !Array.isArray(v))
          ? Object.fromEntries(Object.keys(v).sort().map(x => [x, v[x]])) : v);
      const diffs = [];
      const walk = (a, b, p) => {
        if (norm(a) === norm(b)) return;
        if (a && b && typeof a === 'object' && typeof b === 'object')
          new Set([...Object.keys(a), ...Object.keys(b)]).forEach(k => walk(a[k], b[k], p + '.' + k));
        else diffs.push(p);
      };
      walk(src, saved, '');
      const ov = (window.__frOverflow || []).length;
      document.title = 'SELFCHECK ' + (diffs.length ? 'FAIL ' + diffs.slice(0, 3).join(' ') : 'OK')
        + ' overflow=' + ov;
    } catch (e) { document.title = 'SELFCHECK ERROR ' + e.message; }
  }, 0);
}
window.addEventListener('error', e => {
  if (location.search.includes('selfcheck=1'))
    document.title = 'SELFCHECK ERROR ' + e.message;
});
const FN = '@@FN@@';
const KEY = 'ws-edit-' + FN;
// 작업 채널 — 세션이 어떻게 시작됐는지로 가른다. 웹앱은 serve.py 가 http 로 서빙하고
// (세션이 자동 유지되고 편집이 /save 로 서버 정본에 확실히 저장·보관된다), 스킬·MCP 는
// 편집기를 파일로 열어(file://) 서버가 없다 — 저장·보관·반영이 채팅의 Claude 를 거쳐야 한다.
// 그래서 '채팅에 알려 주세요' 류는 스킬·MCP 에서만 옳다. 웹앱에선 감추거나 사실대로 바꾼다.
// 두 축을 가른다(예전엔 file:// 하나로 뭉쳐 있었다).
//   ① 서버있음 — /save·/api 로 정본에 바로 반영·이력 조회가 되는가. http(s) 면 참.
//   ② 플러그인 — 곁에 채팅 Claude(코딩에이전트)가 있는가. 「AI에게 고쳐달라」는 이 Claude 가
//      대기 지시를 읽어 반영하므로, 이게 있어야 산다. file:// 이거나 로컬 편집기 서버(127.0.0.1)
//      면 참 — 후자는 플러그인이 편집 단계에 잠깐 띄운 serve.py 다(사용자 실제 브라우저로 연다).
//      공개 웹앱(artifact-intelligence.app)엔 채팅 Claude 가 없어 거짓 — 거기선 감춘다.
const 서버있음 = location.protocol !== 'file:';
const 로컬서버 = 서버있음 && /^(127\.0\.0\.1|localhost|\[?::1\]?|0\.0\.0\.0)$/.test(location.hostname);
const 플러그인 = !서버있음 || 로컬서버;
// 채팅표면 — (기존 의미 그대로) 저장·반영을 채팅이 중개해야 하는가 = 서버가 없는가.
// 로컬 서버면 거짓이라 /save·되돌림지점패널(이력)·재조립이 웹앱과 똑같이 동작한다.
const 채팅표면 = !서버있음;
// 문서 글자를 HTML 로 넣기 전에 잠근다 (WP-S2 ③). 이 화면에 실리는 label·붙임 본문·
// 도식 라벨·대기 작업은 **문서에서 온 글**이라 태그가 섞여 있을 수 있다. 이 화면은
// 세션 쿠키와 같은 출처에서 도니, 한 곳만 새도 그 세션 전체가 남의 것이 된다.
const esc = s => String(s === undefined || s === null ? '' : s)
  .replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;',
                               '"': '&quot;', "'": '&#39;' }[c]));
// 1p 본문(.html)만 강조 마크업을 허용한다 — **서버 build/assemble.py 의
// `_허용마크업()` 과 같은 규칙**(강조 span 셋만 살리고 나머지 꺾쇠는 잠근다).
// 여기서 한 번 더 거르는 까닭: 이어서하기(localStorage 버퍼)와 SRCDOC 은 조립기를
// 안 지나고 곧장 innerHTML 로 들어간다 — 조립 산출물만 씻어서는 이 문이 안 닫힌다.
const 강조클래스 = ['num', 'accent', 'delta'];
function 허용마크업(s) {
  const 열림 = /^<span class="([A-Za-z][\w-]*)">/;
  let out = '', 열린 = 0, i = 0;
  s = String(s === undefined || s === null ? '' : s);
  while (i < s.length) {
    if (s[i] !== '<') { out += s[i++]; continue; }
    const m = 열림.exec(s.slice(i, i + 40));
    if (m && 강조클래스.includes(m[1])) { out += m[0]; 열린++; i += m[0].length; continue; }
    if (열린 > 0 && s.startsWith('</span>', i)) { out += '</span>'; 열린--; i += 7; continue; }
    out += '&lt;'; i++;
  }
  return out + '</span>'.repeat(열린);
}
const st = document.querySelector('.edit-bar .st');
const warn = document.querySelector('.edit-bar .warn');
const note = document.querySelector('.copy-note');
const state = { sel: null, notes: {}, ops: [], noteFor: null, editing: null };
const BOXES = ['핵심메시지','총괄목표','결론전환','통계근거','참고사례','절차나열','현황참고'];
const FIGS  = {process:'절차도', cycle:'순환도', converge:'수렴형',
               strategy:'전략체계도', relation:'구조도', stack:'스택막대',
               bar:'막대', hbar:'가로막대', line:'꺾은선', donut:'도넛'};
const LVSPEC = ((PROFILE0 => (PROFILE0['개체'] || {})['항목'])(
  (() => { try { return JSON.parse(document.getElementById('fr-profile').textContent); }
           catch (e) { return {}; } })()) || {})['레벨'] || [['i-l2','○'],['i-l3','-'],['i-l4','※']];
const LVORDER = LVSPEC.map(x => x[0]);
const LV = Object.fromEntries(LVSPEC);

// ── 조판 재실행(문단 분절 방지·줄간격 자동 조정이 매번 다시 걸린다) ──
let reT;
function repaginate() {
  clearTimeout(reT);
  reT = setTimeout(() => {
    if (window.__repaginate) window.__repaginate();   // 골격 등 조판기가 없는 문서는 건너뛴다
    const ov = window.__frOverflow || [];
    warn.textContent = ov.length ? `⚠ 내용이 쪽 밖으로 넘친 곳 ${ov.length}군데` : '';
    if (window.__hunt) window.__hunt();
    save();
  }, 60);
}

// ── 개체 판정: 문서가 선언한 data-ent 를 읽고, 프로파일에서 액션을 꺼낸다 ──
// 편집기는 장르를 모른다. 새 장르는 조립기가 data-ent/data-path를 심고
// ontology/editor-profiles.json 에 항목을 추가하면 그대로 동작한다.
const PROFILE = (() => {
  const el = document.getElementById('fr-profile');
  try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
})() || { genre: '일반', 개체: {}, 상단바: {} };
const ENTS = PROFILE['개체'] || {};
// 표 모양 프리셋 — 굽는 순간 온톨로지 data_elements.표.디자인.스타일_프리셋 에서 센다(build/표꼴.스타일들)
const 표모양들 = /*@@표모양들@@*/[];
// 문서 설정 › 제목 모양(1p·풀버전, '26-09-28) — <html> 의 data 속성 네 개가 스위치다(조립기가 같은
// 이름으로 싣는다). 선택지 정본은 프로파일 상단바.제목모양·제목틀·장모양·절모양 — 여기 또 적지 않는다.
const 상단칸 = PROFILE['상단바'] || {};
const 모양키 = ['제목모양', '제목틀', '장모양', '절모양'];
const 모양있음 = Array.isArray(상단칸['제목모양']) && 상단칸['제목모양'].length > 0;

function entInfo(el) {
  if (!el || !el.dataset) return null;
  const ent = el.dataset.ent;
  if (!ent || !ENTS[ent]) return null;
  const spec = ENTS[ent];
  let label = spec['라벨'] || ent;
  if (ent === '표지필드') label += ' — ' + (el.dataset.frf || '');
  else if (ent === '절' || ent === '장') {
    const t = el.dataset.title || (el.querySelector('.tx') || {}).textContent || '';
    if (t.trim()) label += ' — ' + t.trim();
  }
  else if (ent === '되돌림') {
    const q = (el.querySelector('.q') || {}).textContent || '';
    label += ' — ' + (q.trim().slice(0, 12) || (el.dataset.no + '번'));
  }
  else if (ent === '박스') label += ' — ' + (el.dataset.box || '');
  else if (ent === '도식') label += ' — ' + ((spec['유형'] || {})[figSpec(el).type] || figSpec(el).type);
  else if (ent === '항목' && spec['레벨']) {
    // 개체 이름은 구성 설계와 같은 말로 유지하고, 레벨은 뒤에 덧붙인다
    const lv = (spec['레벨'].find(([c]) => el.classList.contains(c)) || [])[1];
    if (lv) label += ' — ' + lv + ' 단계';
  }
  return { type: ent, spec, label };
}
// 구성 요소를 넣고 빼기 / 가능성 값 바꾸기 — 패널 단추와 되돌림 카드가 같은 함수를 쓴다.
// (되돌림의 '한 번에 바꾸기'가 배지·속성 갱신을 빠뜨리면 화면과 저장값이 어긋난다)
function applyToggle(el, next) {
  el.dataset.on = String(next);
  if (next) el.removeAttribute('data-off'); else el.setAttribute('data-off', '1');
  const nm = el.querySelector('.nm');
  if (nm) {
    const o = nm.querySelector('.off');
    if (next && o) o.remove();
    else if (!next && !o) nm.insertAdjacentHTML('beforeend', '<span class="off">제외됨</span>');
  }
}
// 잎 노드의 글자를 갈아끼운다. data-shown 은 손대지 않는다 —
// 그래야 serialize 가 '사람이 고쳤다'고 보고 새 값을 저장한다.
function setText(el, v) {
  el.textContent = v;
}
function cycPre(spec) {
  const l = spec && spec['값라벨'];
  return l === '' ? '' : (l || '가능성');   // 빈 라벨은 값만 보여준다
}
function cycShow(spec, v) { return ((spec && spec['값표시']) || {})[v] || v; }
function applyCycle(el, spec, v) {
  el.dataset.lv = v;
  const s2 = el.querySelector('.lv');
  if (s2) s2.textContent = (cycPre(spec) + ' ' + cycShow(spec, v)).trim();
}
// 되돌아온 카드가 가리키는 '고칠 자리'를 찾는다. 경로는 계획서 안의 위치다.
function planTarget(P) {
  return document.querySelector(`[data-path="${P}"],[data-flag="${P}"],[data-cycle="${P}"]`);
}
// 순서 항목(data-arr)은 컨테이너에 경로가 걸리고 실제 글자는 .tx 에 있다.
// 컨테이너에 그대로 쓰면 번호·설명·다음 단계 안내가 통째로 날아간다.
function planLeaf(t) {
  return t.dataset.arr ? (t.querySelector('.tx') || t) : t;
}
function planCur(t) {
  if (t.dataset.flag) return String(t.dataset.on !== 'false');
  if (t.dataset.cycle) return t.dataset.lv || '';
  return textOf(planLeaf(t)).trim();
}

function select(el) {
  document.querySelectorAll('.ent-sel').forEach(x => x.classList.remove('ent-sel'));
  state.sel = el; if (el) el.classList.add('ent-sel');
  renderPanel();
}
document.addEventListener('click', e => {
  if (e.target.closest('.panel,.edit-bar,.docset-pop,.copy-note')) return;
  if (e.target.isContentEditable) return;
  if (state.editing) finishEdit();
  const f = e.target.closest('[data-frf]');
  if (f) { select(f); e.preventDefault(); return; }
  // 드릴다운: 바깥 개체 → 안쪽 개체 (장 → 절 → 항목)
  const chain = [];
  for (let n = e.target; n && n !== document.body; n = n.parentElement) {
    if (entInfo(n)) chain.unshift(n);
  }
  if (!chain.length) { select(null); return; }
  // 쪽을 나눠 실은 도식의 이음 조각(판정 ⑧)은 원본 도식을 고른다 — 조각은 스펙·경로가 없는 그릇이다
  const 원본 = 도식원본(e.target);
  if (원본) chain.forEach((n, k) => { if (n.classList && n.classList.contains('fr-fig-cont')) chain[k] = 원본; });
  const i = state.sel ? chain.indexOf(state.sel) : -1;
  // 표를 고른 채 그 표의 칸을 누르면 표를 그대로 둔다('26-09-29 표 재설계 P1) — 칸 합치기·열 넣기가
  // 누른 칸을 기준으로 하는데, 드릴다운이 바깥(쪽)으로 되돌아가면 표 동작 단추가 사라졌다
  const 고른표 = state.sel && i === chain.length - 1 && e.target.closest('td,th')
    && ((entInfo(state.sel) || {}).type === '표' || (entInfo(state.sel) || {}).type === '개요표')
    && !((entInfo(state.sel) || {}).spec || {}).ui;
  if (고른표) { renderPanel(); e.preventDefault(); return; }
  // 격자(표) 도식을 고른 채 그 칸(라벨)을 누르면 고른 것을 두고 그 칸 라벨 판을 연다 — '누르면 바로 편집'
  // (적대 검토 M7 '26-09-29: 드릴다운이 바깥 장으로 되돌아가 라벨 하나에 네 번을 눌렀다). 판은 editor_bar 가 연다
  const 격자칸 = state.sel && i === chain.length - 1 && e.target.closest('td[data-gi]');
  if (격자칸 && (state.sel.contains(격자칸) || 도식원본(격자칸) === state.sel) && state.sel.querySelector('table.fig-grid')
      && typeof 격자칸고치기 === 'function') {
    renderPanel(); e.preventDefault(); 격자칸고치기(state.sel, 격자칸); return;
  }
  // 그림은 한 번에 고른다('26-09-30 fixup4 U7) — 드릴다운이 쪽을 먼저 잡아 그림 하나에 두 번 눌렀다('누르면 바로 편집').
  // 이미 고른 그림을 다시 누르면 그대로 둔다(쪽으로 돌아가지 않는다 — 쪽은 그림 밖을 눌러 고른다).
  const 속 = chain[chain.length - 1];
  if (속 && 속.classList && 속.classList.contains('fr-img')) {
    if (state.sel === 속) renderPanel(); else select(속);
    e.preventDefault(); return;
  }
  select(i >= 0 && i < chain.length - 1 ? chain[i + 1] : chain[0]);
  e.preventDefault();
}, true);

// ── 직접 수정(blur + 바깥 클릭 이중 경로 — 임베디드 브라우저 대비) ──
function unhunt(el) { el.querySelectorAll('span.jachigan-run').forEach(s => s.replaceWith(...s.childNodes)); el.normalize(); }
function finishEdit() {
  const ed = state.editing; if (!ed) return;
  state.editing = null;
  ed.el.removeAttribute('contenteditable');
  if (ed.after) ed.after();
  repaginate();                       // 재조판은 편집이 끝난 뒤에만
}
function editText(el, after) {
  unhunt(el);
  el.contentEditable = 'true'; el.focus();
  state.editing = { el, after };
  el.addEventListener('blur', finishEdit, { once: true });
}

// ── 도식: 스펙 왕복 + 라벨 즉시 반영(어절 wrap 이식) ──
// 도식마다 항목을 담는 배열 이름이 다르다 — 그리는 쪽(svgfig.js)이 읽는 이름과
// **같아야 한다**. 여기 손으로 적었다가 '전략'(전략체계도)을 빠뜨려, 그 도식에서는
// 단계 추가·삭제가 아무 일도 안 했다(2026-08-06 B-1 시험에서 걸림).
const 도식배열이름 = ['단계', '요건', '노드', '전략', '항목', '계열'];
// 배열마다 '라벨'이 담긴 필드가 svgfig.js 렌더러별로 다르다 — 전략체계도=제목, 막대(계열)=이름,
// 나머지=라벨. 이걸 모른 채 '라벨' 필드만 읽으면 전략·계열의 라벨이 전부 빈 것으로 판정돼
// AI 재작성이 대상을 못 찾고 fetch 전에 조용히 끝난다(2026-09-04 aside '도식 네트워크 0건'의 뿌리).
const 도식라벨필드 = { 단계: '라벨', 요건: '라벨', 노드: '라벨', 전략: '제목', 항목: '라벨', 계열: '이름' };
function 도식배열키(sp) {
  for (const k of 도식배열이름) if (Array.isArray(sp[k])) return k;
  return null;
}
function 도식배열(sp) {
  for (const k of 도식배열이름) if (Array.isArray(sp[k])) return sp[k];
  return null;
}
function figSpec(el) { try { return JSON.parse(el.dataset.fig || '{}'); } catch (e) { return {}; } }
function setFigSpec(el, sp) { el.dataset.fig = JSON.stringify(sp); }
function wrapKo(text, maxEm) {
  const w = s => [...s].reduce((a, c) => a + (c.codePointAt(0) > 0x2000 ? 1 : 0.55), 0);
  const out = []; let cur = '';
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const t = cur ? cur + ' ' + word : word;
    if (cur && w(t) > maxEm) { out.push(cur); cur = word; } else cur = t;
  }
  if (cur) out.push(cur);
  return out.length ? out : [''];
}
function figLabels(el) {
  // 격자(표) 도식 — 라벨 칸은 data-gi(= figSetters 차례, 정수)를 단 td 다('26-09-29 격자 도식 P2).
  // 표는 행 차례로 칸이 늘어서므로(체계도: 머리 줄 → 과제 줄) DOM 차례가 아니라 data-gi 로 줄 세운다.
  const 격 = el.querySelector('table.fig-grid');
  // 쪽을 나눠 실은 도식(판정 ⑧)은 뒤쪽 이음 조각(.fr-fig-cont)의 칸까지 한 줄로 센다 — 되풀이한 머리 칸은
  // data-gi 가 없어 겹치지 않는다
  if (격) return [el, ...도식이음들(el)].flatMap(x => [...x.querySelectorAll('table.fig-grid td[data-gi]')])
    .sort((a, b) => Number(a.dataset.gi) - Number(b.dataset.gi));
  return [...el.querySelectorAll('svg text')].filter(t => t.querySelector('tspan'));
}
// 나뉜 도식의 이음 조각들 / 이음 조각의 원본 도식(svgfig.js 나눠싣기 — data-fig-id ↔ data-fig-cont)
function 도식이음들(el) {
  const id = el && el.dataset && el.dataset.figId;
  return id ? [...document.querySelectorAll('.fr-fig-cont')].filter(x => x.dataset.figCont === id) : [];
}
function 도식원본(x) {
  const c = x && x.closest && x.closest('.fr-fig-cont');
  if (!c) return null;
  return [...document.querySelectorAll('.fr-fig[data-fig-id]')].find(f => f.dataset.figId === c.dataset.figCont) || null;
}

// ── 액션 ──
function addNote(el, info) { state.noteFor = { el, info }; renderPanel(); }
function commitNote(v) {
  const nf = state.noteFor;
  if (nf && v && v.trim()) { state.notes[nf.info.label] = v.trim(); nf.el.classList.add('has-note'); }
  state.noteFor = null; save(); renderPanel();
}
function setBox(el, kind) {
  el.dataset.box = kind;
  state.ops.push({ action: '박스 종류', to: kind }); repaginate(); renderPanel();
  save();   // **저장까지 해야 정본에 닿는다**
}
function delEl(el, info) {
  const host = el.closest('.blk') || el.closest('p') || el;
  host.remove(); state.ops.push({ action: '삭제', target: info.label });
  select(null); repaginate(); save();   // **저장까지 해야 정본에 닿는다**
}
function parentArrayOf(el, kind) {
  // 컨테이너(절·장) 자신을 고른 경우 — 그 안에 항목이 하나도 없어도(비어 있어도) 새로
  // 넣을 배열은 **이 컨테이너의 색인 경로 뒤**에 있다. 배열 필드 이름은 장르마다 다르다
  // (풀버전 항목='항목', 1p 항목='items') — kind 는 addBox·addFig 처럼 늘 풀버전에서만
  // 쓰이는 호출은 그대로 맞고, addItemBelow 만 모든 장르에 똑같이 '항목'을 건네므로
  // 여기서 장르별로 실제 필드 이름으로 바꿔 준다(asm:R7-01).
  if (el && el.dataset && (el.dataset.ent === '절' || el.dataset.ent === '장') && el.dataset.path) {
    const i = el.dataset.path.lastIndexOf('.');
    if (i > 0) {
      const 재정의 = { 'onepage-report': { '항목': 'items' } };
      const 필드 = ((재정의[PROFILE.genre] || {})[kind]) || kind;
      return el.dataset.path.slice(0, i) + '.' + 필드;
    }
  }
  // 그 밖(이미 있는 항목·표·박스·도식·픽토그램을 고른 경우)에는 형제 중 경로가 있는
  // 노드에서 소속 배열 경로를 유도한다. **배열 이름을 장르마다 손으로 적지 않는다** —
  // 배열 이름이 달라도(항목/items/본문/픽토그램 등) 경로 자체에 '배열이름.색인' 이 그대로
  // 있으니, 가장 안쪽(마지막) 숫자 조각 앞까지를 배열 경로로 쓰면 된다.
  // (예: sections.0.items.3.html → sections.0.items, 본문.2.text → 본문,
  //  슬라이드.1.항목.0.text → 슬라이드.1.항목, 슬라이드.1.픽토그램.2 → 슬라이드.1.픽토그램)
  // 예전엔 `장.N.절.M.`·`장.N.` 두 꼴만 알아봐서 그 밖 장르는 전부 null 이 나와
  // addBelow 로 넣은 항목이 저장에 전혀 안 실렸다(asm:R7-01, '26-09-27).
  //
  // **경로는 자기 자신이 아니라 안쪽 잎(.tx 류)에 달린 개체가 있다** — 시행문·보도자료·
  // 규정·슬라이드의 항목은 `<p data-ent="항목">…<span data-path="…">잎글</span></p>`
  // 꼴이라(풀버전·1p 는 반대로 그 개체 자신에 곧장 data-path 를 단다), el 자신에 경로가
  // 없다고 바로 다음 형제로 넘어가면 이 네 장르에서 늘 못 찾는다 — 자신부터 안쪽까지
  // 한 겹 내려가 본 뒤에야 다음 형제로 넘어간다.
  for (let n = el; n; n = n.previousElementSibling) {
    const leaf = (n.dataset && n.dataset.path) ? n
      : (n.querySelector && n.querySelector('[data-path]'));
    const p = leaf && leaf.dataset && leaf.dataset.path;
    if (!p) continue;
    const 조각 = p.split('.');
    for (let i = 조각.length - 1; i >= 1; i--) {
      if (/^\d+$/.test(조각[i])) return 조각.slice(0, i).join('.');
    }
  }
  return null;
}
// 규정은 위계가 숫자(i-l2 등)가 아니라 장·절·조·항·호·목 문자열이고, 조립기가 그 문자열을
// class="rg-{위계}" 로 심는다(assemble_regulation.py) — 새 항목의 위계는 그 클래스에서 읽는다.
function 규정레벨(el) {
  for (const lv of ['장', '절', '조', '항', '호', '목']) if (el.classList.contains('rg-' + lv)) return lv;
  return null;
}
// 항목 레벨(숫자)을 이 장르의 항목 클래스 순서(LVORDER)에서 되찾는다. 클래스 이름의 숫자
// 접미사가 곧 level 값이다(i-l2→2, g-l3→3, pr-l1→1, sl-l2→2 — 조립기 쪽 class="{접두}-l{level}"
// 규약과 정확히 짝을 이룬다). 전에는 'i-l4'·'i-l3' 두 글자만 알아보고 나머지(시행문 g-l*·
// 보도자료 pr-l*·슬라이드 sl-l*)는 전부 2로 뭉개, addBelow 로 넣은 항목이 실제 레벨과
// 무관하게 항상 2 로 저장됐다(asm:R7-01 이 가려 온 잠복 결함 — addBelow 가 아예 안 먹혔으니
// 드러나지 않았을 뿐이다).
function levelOf(el) {
  const c = LVORDER.find(cls => el.classList.contains(cls));
  const m = c && c.match(/(\d+)$/);
  return m ? +m[1] : 2;
}
// 새로 추가된 블록(경로 없음)이 배열 끝에 얹힐 값 — 배열 자리(parent)·장르로 원소 모양을
// 정한다. 장르마다 다르다(1p={level,html}, 규정={level:<장절조항호목>, 그 레벨이 장·절이면
// 제목 아니면 text}, 픽토그램={아이콘,라벨,설명}, 그 밖 항목류={level,text}) — 아는 모양이
// 없으면 문자열로 안전하게 떨어진다(별첨 등 원래도 문자열 배열).
function 새항목값(el, parent) {
  if (/(^|\.)픽토그램$/.test(parent)) return { '아이콘': '', '라벨': textOf(el), '설명': '' };
  if (parent === '본문' && PROFILE.genre === 'regulation') {
    const 레벨 = 규정레벨(el) || '조';
    return (레벨 === '장' || 레벨 === '절')
      ? { level: 레벨, '제목': textOf(el) }
      : { level: 레벨, text: textOf(el) };
  }
  if (parent === '본문' || /\.항목$/.test(parent)) return { level: levelOf(el), text: textOf(el) };
  if (/\.items$/.test(parent)) return { level: levelOf(el), html: textOf(el) };
  return textOf(el);
}
function addItemBelow(el, 처음단계) {
  const p = document.createElement('p');
  p.className = 'blk ' + (처음단계 ? LVORDER[0]
                          : (LVORDER.find(c => el.classList.contains(c)) || 'i-l2'));
  // **개체 이름을 반드시 붙인다** — 없으면 만들어 놓고 고를 수가 없다(박스에서 그랬다).
  // 처음단계(절·장 바로 아래 첫 항목)가 아니면 **고른 항목과 같은 개체 이름**을 물려받는다
  // — 풀버전·1p·시행문·보도자료·슬라이드는 원래도 전부 '항목'이라 그대로지만, 규정은
  // 조·항·호·목·장절처럼 항목마다 이름이 달라 이 상속이 없으면 늘 '항목'으로 잘못 붙었다.
  p.dataset.ent = 처음단계 ? '항목' : (el.dataset.ent || '항목');
  // 규정은 위계가 i-lN 클래스가 아니라 rg-{장절조항호목} 클래스로 표시돼 LVORDER 가
  // 못 찾고 늘 'i-l2'로 뭉개진다(위) — 참조 항목의 rg-* 클래스를 그대로 물려받아 둔다.
  // 안 물려받으면 새항목값()의 규정레벨()이 새 항목 자신에서 아무 것도 못 읽어(el.dataset.ent
  // 만으로는 '장절'이 장인지 절인지도 못 가른다) 무엇을 골랐든 늘 '조'로 저장됐다.
  if (!처음단계) {
    const 규정cls = [...el.classList].find(c => /^rg-(장|절|조|항|호|목)$/.test(c));
    if (규정cls) p.classList.add(규정cls);
  }
  p.dataset.new = '1';
  p.dataset.parent = parentArrayOf(el, '항목') || '';
  if (el.dataset.group) p.dataset.group = el.dataset.group;
  p.textContent = '새 항목 — 클릭해 내용을 쓰세요';
  el.after(p); state.ops.push({ action: '항목 추가' });
  select(p); editText(p);            // 재조판은 편집이 끝난 뒤(finishEdit)에만 — 포커스 파괴 방지
  save();   // **저장까지 해야 정본에 닿는다**
}
function changeLevel(el, d) {
  const cur = LVORDER.findIndex(c => el.classList.contains(c));
  const next = Math.min(LVORDER.length - 1, Math.max(0, cur + d));
  if (next === cur) return;
  el.classList.remove(LVORDER[cur]); el.classList.add(LVORDER[next]);
  state.ops.push({ action: '레벨', to: LV[LVORDER[next]] });
  repaginate(); renderPanel();
  save();   // **저장까지 해야 정본에 닿는다**
}
function moveSeq(el, d) {
  const sib = d < 0 ? el.previousElementSibling : el.nextElementSibling;
  if (!sib || sib.dataset.ent !== el.dataset.ent) return;
  if (d < 0) sib.before(el); else sib.after(el);
  renumberSeq((el.dataset.path || sib.dataset.path || '').replace(/\.\d+$/, ''));
  state.ops.push({ action: '순서 이동' }); save(); select(el);
}
function renumberSeq(base) {
  if (!base) return;
  const els = [...document.querySelectorAll('[data-arr]')].filter(x =>
    (x.dataset.path || '').replace(/\.\d+$/, '') === base || x.dataset.parent === base);
  els.forEach((x, i) => {
    const no = x.querySelector('.no'); if (no) no.textContent = (i + 1) + '.';
  });
}
function addBox(host, kind) {
  const d = document.createElement('div');
  d.className = 'blk fr-box'; d.dataset.box = kind;
  // **개체 이름을 반드시 붙인다.** 조립기는 `data-ent="박스"` 를 심는데 여기서만
  // 빠뜨려서, 새로 만든 박스는 고를 수도 없고 액션도 안 떴다 — 만들자마자
  // 손댈 수 없는 박스가 됐다(2026-08-06 B-1 시험에서 걸림).
  d.dataset.ent = '박스';
  d.dataset.new = '1'; d.dataset.parent = parentArrayOf(host, '박스') || '';
  if (host.dataset.group) d.dataset.group = host.dataset.group;
  d.innerHTML = '<p>새 박스 — 클릭해 내용을 쓰세요</p>';
  host.after(d); state.ops.push({ action: '박스 추가', to: kind });
  repaginate(); select(d);
  save();   // **저장까지 해야 정본에 닿는다**
}
function addFig(host) {
  // 도식을 새로 넣는다. 도식은 자기완결이다 — 스펙(data-fig)만 있으면 svgfig.js 가 그린다.
  // 박스와 똑같이 **개체 이름·소속 배열**을 붙여야 저장(serialize ③)이 절.도식 배열로 받는다.
  const d = document.createElement('div');
  d.className = 'blk fr-fig'; d.dataset.ent = '도식';
  d.dataset.new = '1'; d.dataset.parent = parentArrayOf(host, '도식') || '';
  if (host.dataset.group) d.dataset.group = host.dataset.group;
  // 기본은 절차(process) 2단계 — 유형·라벨·캡션은 패널에서 바로 고친다
  setFigSpec(d, { type: 'process', '캡션': '새 도식 — 유형과 라벨을 고치세요',
    '단계': [{ '라벨': '단계 1', '주체': '', '전이': '다음' }, { '라벨': '단계 2', '주체': '' }] });
  host.after(d);
  if (window.SVGFIG) window.SVGFIG.mount(d);   // data-fig 를 읽어 캡션·SVG·함의를 그린다
  state.ops.push({ action: '도식 추가' });
  repaginate(); select(d);
  save();   // **저장까지 해야 정본에 닿는다**
}

// ── 패널 ──
const panel = document.createElement('div'); panel.className = 'panel'; document.body.appendChild(panel);
// ── 좌측 편집이력 레일 (3단의 왼쪽 기둥) — history 부르기의 판(버전)을 최신순 상시 표출.
// 되돌림 지점 패널(상단 띠)이 '직접' 잡은 것만 보였다면, 이 레일은 저장마다 쌓이는 전(全) 이력을
// 늘 왼쪽에 보여 준다(가운데 뷰어·우측 옵션과 3단). 서버가 있어야 이력이 있다(file:// 면 안내). ──
const histPanel = document.createElement('div'); histPanel.className = 'hist-panel'; document.body.appendChild(histPanel);
let 이력그리는중 = false;
async function 이력그리기() {
  if (!서버있음) {
    histPanel.innerHTML = '<h3>편집 이력</h3><div style="opacity:.7;font-size:12px">저장 서버가 없어 이력을 불러올 수 없습니다.</div>';
    return;
  }
  if (이력그리는중) return; 이력그리는중 = true;
  try {
    let r = null; try { r = await 부르기('history', { key: FN }); } catch (e) {}
    const 판 = (r && r.ok && r['값'] && r['값']['판']) || [];
    let h = '<h3>편집 이력</h3>';
    if (!판.length) {
      h += '<div style="opacity:.7;font-size:12px">아직 이력이 없습니다. 고치면 여기 쌓입니다.</div>';
    } else {
      // 서버(history/version.py 목록)는 **최신 판이 먼저**다 — 예전엔 여기서 한 번 더 뒤집어 가장 오래된
      // 판에 '지금'이 붙고 그 판으로는 돌아갈 수 없었다(적대 검토 H3 '26-09-29). 판은 저장 **직전** 상태를
      // 찍으므로(보관) 최신 판도 지금 문서와 다를 수 있다 — '지금'은 따로 한 줄 두고 판마다 [되돌리기]를 단다.
      const 기록 = (r && r['값'] && r['값']['기록']) || [];
      h += '<div class="hrow now"><div class="hmark">지금</div><div class="hwhy">지금 문서</div></div>';
      판.forEach(v => {
        const 사유 = v['고친 이유'] || v['메모'] || ('버전 ' + (v['버전'] != null ? v['버전'] : ''));
        const 직접 = v['종류'] === '직접';
        // 이 판 뒤에 고친 곳 수(손질 기록의 바뀐곳 합) — 되돌리기 확인에 쓴다
        const 뒤 = 기록.filter(x => x && x['종류'] === '손질' && String(x['때'] || '') > String(v['때'] || ''))
          .reduce((a, x) => a + (Number(x['바뀐곳']) || 1), 0);
        h += '<div class="hrow">'
          + (직접 ? '<div class="hmark">되돌림 지점</div>' : '')
          + '<div class="hwhy">' + esc(사유) + '</div>'
          // ISO 그대로('2026-09-29T14:05:39')는 읽기 어려웠다(적대 검토 L1) — '09-29 14:05' 꼴로
          + '<div class="hwhen">' + esc(String(v['때'] || '').replace('T', ' ').replace(/^\d{4}-/, '').slice(0, 11)) + '</div>'
          + '<button data-v="' + esc(String(v['버전'])) + '" data-n="' + esc(사유) + '" data-after="' + 뒤 + '">되돌리기</button>'
          + '</div>';
      });
    }
    histPanel.innerHTML = h;
    histPanel.querySelectorAll('button[data-v]').forEach(b =>
      b.onclick = () => {
        // 판은 5분에 하나라 그 뒤 고친 것이 함께 사라진다 — 확인을 받는다(적대 검토 H2). 되돌리기 전 상태는 새 판으로 남는다
        const n = +b.dataset.after || 0;
        if (!confirm('이 판으로 돌아가면 그 뒤 고친 ' + (n ? n + '군데가' : '내용이')
            + ' 화면에서 사라집니다(되돌리기 전 상태는 새 판으로 남습니다). 돌아갈까요?')) return;
        지점되돌리기(+b.dataset.v, b.dataset.n);
      });
  } finally { 이력그리는중 = false; }
}
function btn(t, f, c) { const b = document.createElement('button'); b.textContent = t; b.onclick = f;
  if (c) b.className = c; return b; }
// ── 개체별 AI 편집(BYOK) — 웹앱 전용 ─────────────────────────────────────────
// 고른 개체 하나를 **사용자 브라우저에서 직접** LLM 에 보내 고쳐 받아 그 자리에 넣는다.
// 키·내용은 서버를 안 거친다(app.html 내설정·모델부르기와 같은 규칙·같은 localStorage 칸).
// 플러그인/파일 표면은 곁의 채팅 Claude 가 '메모(addNote)'로 반영하므로 여기 안 온다(renderPanel 분기).
function _llm설정() {
  let llm = {}; try { llm = JSON.parse(localStorage.getItem('ai-llm')) || {}; } catch (e) {}
  return { 제공자: llm.제공자 || 'anthropic', 베이스: llm.베이스 || '', 모델: llm.모델 || '',
           키: localStorage.getItem('ai-api-key') || '' };
}
function _키준비(c) { c = c || _llm설정(); return c.제공자 === 'ollama' ? true : !!c.키; }
const 문체규칙 = { slides: '개조식 명사형(완결 주장 문장), 군더더기 없이 짧게',
  'onepage-report': '개조식 명사형', fullreport: '개조식 명사형',
  gongmun: '서술어 완결 + 공손체(~하시기 바랍니다)', press: '보도자료 서술형', regulation: '조문체' };
// 규정은 개체(라벨)마다 문체가 다르다('26-09-28 규정 처방 P1) — '조문체' 한 단어면 호를 AI 로
// 다듬을 때 '~한다.' 문장으로 되돌린다. **서버 workspace/api.py 의 _규정개체문체 와 문구를
// 똑같이 둔다**(test/r14_reg14.py 가 대조한다).
const 규정개체문체 = [
  [['호', '목'], "조문체의 호·목 — 지금 꼴(명사구·'~할 것'·'…한 경우')을 바꾸지 말고 다듬는다. 정의 호 '“○○”란 …을 말한다.'는 그 꼴을 지킨다"],
  [['조', '항'], "조문체 — 완결 문장('~하여야 한다'·'~할 수 있다'·'~하여서는 아니 된다'). 목적·적용·시행·설치 조의 맨 '~한다'는 그대로 둔다"],
  [['제정이유'], "제정이유 — 배경과 목적을 한 단락으로 적고 '~하려는 것임.'으로 맺는다"],
  [['주요내용'], "주요내용 — '~함'·'~하도록 함'으로 맺고, 끝의 조 인용 괄호는 그대로 둔다"],
];
function _규정문체(라벨) {
  // 라벨 첫 낱말을 정확히 견주고 뒤에는 기호만 온다('항 ①'→'항', '조 제목'→없음) — 서버
  // api._재작성문체 와 같은 규칙(적대검토 F8).
  const 조각 = String(라벨 || '').trim().split(/\s+/).filter(Boolean);
  const 라 = (조각.length && !/[가-힣]{2,}/.test(조각.slice(1).join(' '))) ? 조각[0] : '';   // '가.'는 기호
  for (const [머리들, 문] of 규정개체문체) if (머리들.includes(라)) return 문;
  return 문체규칙.regulation;
}
// 편집기 AI 재작성이 참고할 '이 문서의 배경'(최초 의도·자료). BYOK 는 서버를 안 거치므로,
// 편집기에 이미 실린 문서(SRCDOC._맥락 — app.html 이 새문서 때 심음)에서 직접 읽어 프롬프트에
// 싣는다. 서버 경로의 문서키→_맥락 주입과 **같은 맥락·같은 동작**(모델만 다르다). 원자료는
// 내 키(BYOK)로만 나가고 우리 서버는 안 거친다 — 자기 데이터를 자기 모델에 주는 셈.
function _편집맥락() {
  try {
    const m = SRCDOC && SRCDOC['_맥락'];
    const 의도 = m && String(m['의도'] || '').trim();
    return 의도 ? ('\n\n[이 문서의 배경 — 이 맥락에 맞게 다듬되, 배경 자체를 출력하지는 마라]\n의도·자료: '
      + 의도.slice(0, 1200) + '\n') : '';
  } catch (e) { return ''; }
}
async function _llm다시쓰기(c, info, 원문, 지시) {
  const 문체 = PROFILE.genre === 'regulation' ? _규정문체(info.spec['라벨'] || info.type)
    : (문체규칙[PROFILE.genre] || '이 문서 종류의 문체를 그대로');
  const sys = '너는 대한민국 공공문서 편집자다. 아래 「' + (info.spec['라벨'] || info.type)
    + '」 문구 하나를 고쳐 쓴다. 규칙: ' + 문체 + '. 번호·마커(□○-·①·제N조 등)는 붙이지 마라(시스템이 붙인다).'
    + ' 없는 사실·수치를 지어내지 마라 — 모르는 값은 ○○ 한 꼴로 비워라.' + _편집맥락()
    + ' **고친 문구 한 편만 출력** — 설명·따옴표·머리말 없이 본문만.';
  const usr = 원문 + (지시 ? ('\n\n[고칠 방향] ' + 지시) : '\n\n[고칠 방향] 더 또렷하고 간결하게 다듬어라.');
  let 글 = '';
  if (c.제공자 === 'anthropic') {
    const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': c.키,
        'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true' },
      body: JSON.stringify({ model: c.모델 || 'claude-sonnet-5', max_tokens: 1200,
        system: sys, messages: [{ role: 'user', content: usr }] }) });
    if (!r.ok) throw new Error('(' + r.status + ') ' + (await r.text()).slice(0, 160));
    const j = await r.json(); 글 = (j.content || []).map(x => x.text || '').join('');
  } else {
    let base = (c.베이스 || '').trim().replace(/\/+$/, '');
    if (!base) base = c.제공자 === 'ollama' ? 'http://localhost:11434/v1' : 'https://api.featherless.ai/v1';
    const 헤더 = { 'content-type': 'application/json' };
    if (c.키) 헤더['authorization'] = 'Bearer ' + c.키;
    const r = await fetch(base + '/chat/completions', { method: 'POST', headers: 헤더,
      body: JSON.stringify({ model: c.모델 || '', max_tokens: 1200,
        messages: [{ role: 'system', content: sys }, { role: 'user', content: usr }] }) });
    if (!r.ok) throw new Error('(' + r.status + ') ' + (await r.text()).slice(0, 160));
    const j = await r.json(); const m = (((j.choices || [])[0] || {}).message || {});
    글 = m.content || m.reasoning_content || m.reasoning || '';
  }
  글 = String(글).trim().replace(/^```[a-z]*\n?|\n?```$/g, '').trim();     // 코드펜스 제거
  글 = 글.replace(/^["'「『]+|["'」』]+$/g, '').trim();                       // 감싼 따옴표 제거
  return 글;
}
function _ai대상(el, info) {              // {el, apply} 또는 {table} — 없으면 null
  if (typeof v2ai대상 === 'function') return v2ai대상(el, info);   // 판형 v2 — 부품 글 칸만(숫자는 빼고)
  const t = info.type;
  // 표를 품은 개체는 셀 단위 재작성으로 보낸다(구조 유지, 위치로 되박음). 개체 종류가
  // '표'·'개요표'(표를 감싼 컨테이너, 둘 다 표 안쪽에 [data-ent] 잎이 없다)일 때만 이
  // 길을 탄다 — 예전엔 '표'일 때만이라 개요표가 일반 leaf 로 떨어져 textContent 대입이
  // <table> 째 지워 정본이 문자열로 덮였다(assemble:F5, '26-09-27). 하지만 종류를 안
  // 가리고 el 안에 table 이 있기만 하면 잡도록 넓혔더니, 표를 품은 컨테이너(예: 슬라이드
  // 장 전체)까지 걸려 그 컨테이너의 진짜 대상(헤드메시지 등) 대신 표 셀이 재작성됐다
  // (asm:F3, '26-09-27 회귀) — '표'·'개요표' 두 종류로만 좁힌다.
  if (t === '표' || t === '개요표') {
    const tb = el.querySelector('table') || (el.matches && el.matches('table') ? el : null);
    if (tb) return { table: tb };
  }
  if (t === '도식' && el.querySelector('table.fig-grid')) {
    // 격자(표) 도식 — 칸 글(목표·머리·과제, 단계, 현행·개선 항목)을 data-gi 차례의 평평한 목록으로 펴서
    // 고치게 하고, 받은 글을 같은 차례의 설정자로 되박는다(개수·순서 유지, '26-09-29 격자 도식 P2).
    // 예전 라벨 배열 길은 체계도에서 전략 제목만 고쳤다(목표·과제가 빠짐).
    const 칸들 = figLabels(el), 원 = 칸들.map(svgLabelText);
    if (원.some(x => x.trim())) return { 리스트: 원, 되박기: (고친) => {
      const s2 = figSpec(el), S = figSetters(s2);
      칸들.forEach((td, k) => {
        const i = Number(td.dataset.gi), v = 고친[k];
        if (v != null && String(v).trim() && Number.isInteger(i) && S[i]) S[i](String(v).replace(/\s+/g, ' ').trim());
      });
      setFigSpec(el, s2); window.SVGFIG.mount(el); } };
  }
  if (t === '도식') {                       // 도식 = 라벨(단계·노드 등) 리스트 재작성 — 구조 보존
    // 원소는 문자열이거나 객체({라벨, 주체/전이/id/연결…})다(svgfig lab 과 같은 규칙). 라벨만
    // 뽑아 고치고, 객체면 라벨 필드만 되쓴다(String(obj)="[object Object]" 로 구조를 깨뜨리던 버그).
    const sp0 = figSpec(el), 키0 = 도식배열키(sp0), lf = 도식라벨필드[키0] || '라벨';
    const _lab = s => (s && typeof s === 'object')
      ? String(s[lf] ?? s['라벨'] ?? s['제목'] ?? s['이름'] ?? '') : String(s ?? '');
    const arr = 키0 ? sp0[키0] : null;
    if (Array.isArray(arr) && arr.length && arr.some(x => _lab(x).trim()))
      return { 리스트: arr.map(x => _lab(x)), 되박기: (고친) => {
        const s2 = figSpec(el), a2 = 키0 ? s2[키0] : null;
        고친.forEach((v, i) => {
          if (v == null || !a2 || a2[i] === undefined) return;
          if (a2[i] && typeof a2[i] === 'object') a2[i][lf] = String(v);   // 유형별 라벨 필드에 되쓴다
          else a2[i] = String(v);
        });
        setFigSpec(el, s2); window.SVGFIG.mount(el); } };
    const c = el.querySelector('.cap');   // 라벨 배열이 없으면 캡션만
    return c ? { el: c, apply: () => { syncFigSpec(el); window.SVGFIG.mount(el); } } : null;
  }
  if (t === '장' || t === '절') { const tx = el.querySelector('.tx') || el;
    return { el: tx, apply: () => { el.dataset.title = tx.textContent.trim(); } }; }
  if (t === '조' || t === '항' || t === '호' || t === '목' || t === '장절' || t === '별표') {
    // 규정 조·항·호·목·장절·별표 컨테이너는 번호 마커(제N조·①·1.·가.·제N장·[별표 N])와
    // [data-path] 잎 글이 한 태그 안에 있다(assemble_regulation.py build() — <p
    // data-ent="조">머리<span class="tx" data-path="…">잎글</span></p>, 장절·별표도
    // 같은 h2 한 태그 패턴). 컨테이너 el 을 통째로 대상 삼으면 결과를 el.textContent 로
    // 덮어써 마커까지 지우거나 뒤섞는다 — 제정이유를 고칠 때와 같은 함정(assemble_regulation.py
    // 상단 '4차 검토' 주석)이라 같은 방식으로 고친다: [data-path] 잎(.tx — 조문·항목·
    // 장절 제목·별표 제목)만 AI 대상으로 삼는다. 장절·별표를 빠뜨리면 el.textContent
    // 대입이 마커째 지워 serialize 의 prune 이 그 항목(본문의 장 하나)을 배열에서
    // 통째로 splice 한다(asm:F4, '26-09-27).
    const tx = el.querySelector('.tx') || el;
    return { el: tx, apply: null };
  }
  // 그림 — AI 는 캡션만 고친다(그림 P3 '26-09-30, design §7). 예전엔 일반 leaf 로 떨어져 결과 글을 그림 블록
  // textContent 에 대입해 <img> 째 지웠다. 캡션이 없으면 고칠 글이 없다(null)
  if (t === '이미지') { const c = el.querySelector('.cap');
    return c ? { el: c, apply: () => {
      const v = stripAngle(c.textContent).trim(), sp = imgSpec(el);
      if (v) { sp['캡션'] = v; imgSave(el, sp); c.textContent = c.classList.contains('cap-below') ? v : '< ' + v + ' >'; }
    } } : null; }
  if (t === '픽토그램') { const l = el.querySelector('.sl-picto-l .tx') || el.querySelector('.tx');
    return l ? { el: l, apply: null } : null; }   // 픽토 카드 → 라벨 문구
  if (t === '슬라이드') { const h = el.querySelector('.sl-head');   // 슬라이드(장) → 헤드메시지를 고친다
    return h ? { el: h, apply: null } : null; }
  return { el: el, apply: null };         // 일반 leaf(헤드메시지·항목·요약·리드·제목·출처…)
}
async function _서버다시쓰기(info, 원문, 지시) {   // 키 없는 웹앱(기본키) — 서버 모델(EXAONE)이 고친다
  const r = await 부르기('airewrite',
    { 원문, 라벨: info.spec['라벨'] || info.type, 장르: PROFILE.genre, 지시, 문서키: PROFILE.key || '' }, true);
  if (!r || !r.ok) throw new Error((r && r['로그']) || '서버 호출에 실패했습니다');
  return ((r['값'] || {}).고친글) || '';
}
async function _서버표다시쓰기(원셀, 지시) {        // 표 셀 재작성 — 서버 모델(같은 op, 셀들 모드)
  const r = await 부르기('airewrite', { 셀들: 원셀, 장르: PROFILE.genre, 지시, 문서키: PROFILE.key || '' }, true);
  if (!r || !r.ok) throw new Error((r && r['로그']) || '서버 호출에 실패했습니다');
  return (r['값'] || {}).고친셀들 || [];
}
async function _llm표다시쓰기(원셀, 지시) {          // 표 셀 재작성 — BYOK(브라우저가 내 키로)
  const c = _llm설정();
  const 문체 = 문체규칙[PROFILE.genre] || '이 문서 종류의 문체를 그대로';
  const sys = '너는 대한민국 공공문서 편집자다. 아래 표의 각 셀 문구를 고쳐 쓴다. 규칙: ' + 문체
    + '. **셀 개수와 순서를 그대로 유지**하고 없는 사실·수치는 지어내지 마라 — 모르는 값은 ○○ 한 꼴로 비워라.' + _편집맥락()
    + ' 반드시 {"고친셀들":["…",…]} JSON 하나만 출력 — 입력과 같은 길이 배열.';
  const usr = JSON.stringify({ 셀들: 원셀 }) + (지시 ? ('\n\n[고칠 방향] ' + 지시) : '');
  let 글 = '';
  if (c.제공자 === 'anthropic') {
    const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': c.키,
        'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true' },
      body: JSON.stringify({ model: c.모델 || 'claude-sonnet-5', max_tokens: 2000,
        system: sys, messages: [{ role: 'user', content: usr }] }) });
    if (!r.ok) throw new Error('(' + r.status + ') ' + (await r.text()).slice(0, 160));
    const j = await r.json(); 글 = (j.content || []).map(x => x.text || '').join('');
  } else {
    let base = (c.베이스 || '').trim().replace(/\/+$/, '');
    if (!base) base = c.제공자 === 'ollama' ? 'http://localhost:11434/v1' : 'https://api.featherless.ai/v1';
    const 헤더 = { 'content-type': 'application/json' };
    if (c.키) 헤더['authorization'] = 'Bearer ' + c.키;
    const 몸 = jm => JSON.stringify(Object.assign({ model: c.모델 || '', max_tokens: 2000,
      messages: [{ role: 'system', content: sys }, { role: 'user', content: usr }] },
      jm ? { response_format: { type: 'json_object' } } : {}));
    // JSON 모드를 거부하는 제공자·모델(OpenRouter 의 claude 등)이면 그 항목만 빼고 한 번 더(app.html 모델부르기와 같은 폴백).
    let r = await fetch(base + '/chat/completions', { method: 'POST', headers: 헤더, body: 몸(true) });
    if (!r.ok) {
      const t = await r.text();
      if (/response_format|json[_\s-]?object|schema|not supported|unsupported/i.test(t))
        r = await fetch(base + '/chat/completions', { method: 'POST', headers: 헤더, body: 몸(false) });
      else throw new Error('(' + r.status + ') ' + t.slice(0, 160));
    }
    if (!r.ok) throw new Error('(' + r.status + ') ' + (await r.text()).slice(0, 160));
    const j = await r.json(); const m = (((j.choices || [])[0] || {}).message || {});
    글 = m.content || m.reasoning_content || '';
  }
  try { const o = JSON.parse(String(글).replace(/^```[a-z]*\n?|\n?```$/g, '').trim());
    return Array.isArray(o) ? o : (o.고친셀들 || []); } catch (e) { return []; }
}
async function ai다시쓰기(el, info) {
  const c = _llm설정();
  const byok = _키준비(c);
  // 키 있으면 브라우저가 직접(BYOK), 키 없어도 서버가 있으면 서버 모델로 고친다(기본키 웹앱).
  if (!byok && !서버있음) { alert('AI로 고치려면 앱 화면에서 내 LLM(API 키)을 설정하세요 — '
    + '키는 이 브라우저에만 저장되고 서버로 가지 않습니다.'); return; }
  const tgt = _ai대상(el, info);
  if (!tgt) { alert('이 개체는 안쪽 글(헤드메시지·항목·캡션)을 골라 AI로 고쳐 주세요.'); return; }
  const 지시 = prompt('AI에게 어떻게 고칠지 적어 주세요 (비우면 더 또렷·간결하게 다듬습니다):', '');
  if (지시 === null) return;
  st.textContent = 'AI가 고치는 중…'; st.classList.add('on');
  const 풀기 = _편집잠금('AI가 「' + (info.spec['라벨'] || info.type) + '」을(를) 고쳐 쓰는 중…');
  try {
    if (tgt.table || tgt.리스트) {             // 표 셀·도식 라벨 = 리스트 재작성(개수·순서 유지)
      let cells = null, 원 = tgt.리스트;
      if (tgt.table) { cells = [...tgt.table.querySelectorAll('th,td')]; 원 = cells.map(x => (x.innerText || '').trim()); }
      if (!원 || !원.some(x => x)) throw new Error('고칠 글이 없습니다');
      const 고친 = byok ? await _llm표다시쓰기(원, 지시) : await _서버표다시쓰기(원, 지시);
      if (!Array.isArray(고친) || !고친.length) throw new Error('고쳐 받지 못했습니다');
      // 칸 수가 다르면 되박지 않는다 — 위치로 넣으므로 하나만 빠지거나 더해져도 글·숫자가 옆 칸으로 밀려
      // 그대로 저장됐다(적대 검토 H1 '26-09-29: 체계도 10→9칸, 숫자 표 20→21칸). 서버도 같은 것을 거른다.
      if (고친.length !== 원.length) throw new Error('AI가 칸 수를 바꿔 보내(' + 원.length + '칸 → ' + 고친.length
        + '칸) 적용하지 않았습니다 — 다시 시도해 주세요');
      if (cells) cells.forEach((x, i) => { if (고친[i] != null && String(고친[i]).trim()) 칸쓰기(x, String(고친[i])); });
      else tgt.되박기(고친);
    } else {
      const 원문 = (tgt.el.innerText || '').trim();
      if (!원문) throw new Error('고칠 글이 비어 있습니다');
      const 결과 = byok ? await _llm다시쓰기(c, info, 원문, 지시)
                        : await _서버다시쓰기(info, 원문, 지시);   // 키 없으면 서버 모델
      if (!결과) throw new Error('빈 응답을 받았습니다');
      tgt.el.textContent = 결과;
      if (tgt.apply) tgt.apply();
    }
    state.ops.push({ action: 'AI 다시쓰기', target: info.spec['라벨'] || info.type });
    st.classList.remove('on');
    repaginate(); save(); select(el);
  } catch (e) {
    st.textContent = '';
    alert('AI 호출에 실패했습니다: ' + (e.message || e) + '\n앱에서 키·모델·주소를 확인해 주세요.');
    renderPanel();
  } finally { 풀기(); }
}
// AI 재작성 동안 편집기 전체를 덮어 다른 조작을 막는다(사장님 지적 0904 — 재작성 중 잠금).
function _편집잠금(msg) {
  let o = document.querySelector('.ai-lock');
  if (!o) {
    o = document.createElement('div'); o.className = 'ai-lock';
    o.innerHTML = '<div class="ai-lock-box"><span class="ai-lock-spin"></span>'
      + '<span class="ai-lock-msg"></span></div>';
    document.body.appendChild(o);
  }
  o.querySelector('.ai-lock-msg').textContent = msg || 'AI가 고치는 중…';
  o.style.display = 'flex';
  return () => { o.style.display = 'none'; };
}

// ── 정렬(좌/가운데/우) — 경로별 오버레이 state.정렬 을 왕복(조립기 _정렬st 와 짝). 텍스트는
// 문자열이라 개체 필드를 못 달아, 안쪽 .tx 의 data-path 를 키로 삼는다. 좌측=기본은 키를 안 남긴다.
const _ALIGN_JS = { '좌측': 'left', '가운데': 'center', '우측': 'right' };
function _정렬키(el) {
  const t = el.querySelector && el.querySelector('.tx');
  return (t && t.dataset.path) || el.dataset.path || '';
}
function _정렬현(el) { return (state.정렬 && state.정렬[_정렬키(el)]) || '좌측'; }
function 정렬설정(el, v) {
  const k = _정렬키(el); if (!k) return;
  state.정렬 = state.정렬 || {};
  if (v && v !== '좌측') { state.정렬[k] = v; el.style.textAlign = _ALIGN_JS[v]; }
  else { delete state.정렬[k]; el.style.textAlign = ''; }   // 좌측=기본 → 키 안 남김(왕복 불변식)
  state.ops.push({ action: '정렬', to: v }); save(); renderPanel();
}

function renderPanel() {
  panel.innerHTML = '<h3>선택한 부분</h3>';
  const A = (t, f, c) => panel.appendChild(btn(t, f, c));
  if (state.noteFor) {
    panel.insertAdjacentHTML('beforeend',
      `<div class="ent">✍ AI에게 고쳐달라 하기</div><div class="hint">${esc(state.noteFor.info.label)}</div>` +
      `<textarea id="notein" placeholder="예: 이 부분을 표로 바꿔줘 / 근거 수치 추가 / 두 개로 나눠줘"></textarea>`);
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('저장', () => commitNote(document.getElementById('notein').value)));
    r.appendChild(btn('취소', () => { state.noteFor = null; renderPanel(); }));
    panel.appendChild(r);
    setTimeout(() => document.getElementById('notein').focus(), 40);
    return appendPending();
  }
  const el = state.sel, info = el && entInfo(el);
  if (!info) {
    panel.insertAdjacentHTML('beforeend',
      '<div class="ent">없음</div><div class="hint">고칠 곳을 클릭하세요.<br>' +
      '같은 자리를 다시 누르면 더 안쪽(큰 제목 → 작은 제목 → 항목)이 잡힙니다.<br>' +
      '목차와 쪽번호는 자동으로 만들어집니다.<br>' +
      '고칠 때마다 줄과 쪽을 다시 맞춥니다 — 한 덩어리 글이 쪽을 넘어 쪼개지지 않게 합니다.</div>');
    return appendPending();
  }
  // info.label 은 절 제목 등 **문서 글자**를 이어 붙여 만든다(entInfo 참고)
  panel.insertAdjacentHTML('beforeend', `<div class="ent">${esc(info.label)}</div>`);
  if (info.spec['힌트']) panel.insertAdjacentHTML('beforeend', `<div class="hint">${info.spec['힌트']}</div>`);
  // 판형 v2 — 조작은 고른 개체 위 막대(주 동작 + ⋯)에 둔다. 패널에는 이름·힌트만(workspace/editor_v2.py).
  if (info.spec['ui'] && typeof v2패널 === 'function') { v2패널(panel, el, info); return appendPending(); }
  // 슬라이드 자유배치 — 헤드·본문이 있는 슬라이드면 흐름⇄자유 토글과, 고른 개체의 좌표를 보인다.
  const 슬sec = el.closest && el.closest('.sl-page[data-slide-idx]');
  if (슬sec && (슬sec.querySelector('.sl-head') || 슬sec.querySelector('.sl-body'))) {
    const 자유 = 슬sec.classList.contains('sl-free');
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">${자유 ? '자유배치 — 그립(✥)으로 옮기고 모서리 점으로 크기 조절' : '흐름 배치 — 정해진 자리'}</div>`);
    A(자유 ? '흐름 배치로 되돌리기' : '＋ 자유배치로 전환', () => 자유배치토글(슬sec), 자유 ? '' : 'good');
    if (자유 && el.classList.contains('sl-placed')) {
      const st = el.style, vv = k => Math.round(parseFloat(st[k]) || 0);
      panel.insertAdjacentHTML('beforeend',
        `<div class="hint">이 개체 위치 — x ${vv('left')} · y ${vv('top')} · 너비 ${vv('width')} · 높이 ${vv('height')} (지면 %)</div>`);
    }
  }
  // 도식·차트·표 — 고른 개체 위 막대(주 동작 3 + ⋯, 프로파일 막대·차트막대). 패널에는 이름·힌트만
  // (workspace/editor_bar.py, '26-09-29 편집기 알잘딱깔센).
  if (info.spec['막대'] && typeof 막대패널 === 'function') { 막대패널(panel, el, info); return appendPending(); }
  const acts = info.spec['액션'] || [];
  if (!acts.length && !el.dataset.explain)
    panel.insertAdjacentHTML('beforeend',
      '<div class="explain">이 항목은 이 화면에서 고치지 않습니다.</div>');
  const has = a => acts.includes(a);

  if (has('boxkind')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">종류 — 누르면 바로 바뀝니다</div>');
    (info.spec['종류'] || []).forEach(k => A(k, () => setBox(el, k), el.dataset.box === k ? 'sel' : ''));
  }
  if (has('figtype')) {
    const sp = figSpec(el);
    panel.insertAdjacentHTML('beforeend', '<div class="hint">모양 — 누르면 바로 다시 그립니다</div>');
    Object.entries(info.spec['유형'] || {}).forEach(([k, v]) => A(v, () => {
      const s2 = figSpec(el);
      // 비교판(전[]·후[])만 배열 이름이 둘이다 — 오갈 때 글을 옮긴다(원래 배열은 지우지 않아 되돌리면 산다)
      const 글만 = x => (x && typeof x === 'object') ? String(x['라벨'] ?? x['제목'] ?? x['이름'] ?? '') : String(x ?? '');
      if (k === 'compare' && !Array.isArray(s2['전']) && !Array.isArray(s2['후'])) {
        const a = 도식배열(s2); if (Array.isArray(a)) { s2['전'] = a.map(글만); s2['후'] = []; }
      } else if (s2.type === 'compare' && k !== 'compare') {
        const 키 = { process: '단계', cycle: '단계', converge: '요건', relation: '노드' }[k];
        if (키 && !Array.isArray(s2[키])) s2[키] = [...(s2['전'] || []), ...(s2['후'] || [])].map(글만);
      }
      s2.type = k; setFigSpec(el, s2);
      window.SVGFIG.mount(el); state.ops.push({ action: '도식 유형', to: v });
      repaginate(); select(el);
    }, sp.type === k ? 'sel' : ''));
  }
  if (has('figsize')) {                     // 도식 크기 — 작게·보통·크게 한 축('26-09-28 사장님 판정)
    // 크기는 스펙(data-fig) 안에만 둔다 — svgfig.js 가 안쪽 svg 에 적용하고(칸 폭을 다시 재 배치),
    // 그릇 폭은 건드리지 않는다. '크게' = 면적과 글자를 같이 키운다. 옛 '가득' 은 크게로 본다.
    panel.insertAdjacentHTML('beforeend', '<div class="hint">도식 크기 — 크게는 글자와 면적을 함께 키웁니다</div>');
    const 지금 = (window.SVGFIG && window.SVGFIG.크기풀기)
      ? window.SVGFIG.크기풀기(figSpec(el)['크기'] === '가득' ? '크게' : figSpec(el)['크기']) : '보통';
    const r = document.createElement('div'); r.className = 'row';
    ['작게', '보통', '크게'].forEach(v =>
      r.appendChild(btn(v, () => {
        const s2 = figSpec(el); if (v !== '보통') s2['크기'] = v; else delete s2['크기']; setFigSpec(el, s2);
        delete el.dataset.크기;                // 옛 슬라이드 속성(크게·가득 CSS)은 새 도식에 안 먹는다
        window.SVGFIG.mount(el);
        state.ops.push({ action: '도식 크기', to: v }); save(); repaginate(); select(el);
      }, 지금 === v ? 'sel' : '')));
    panel.appendChild(r);
  }
  if (has('edit')) {
    if (info.type === '도식') {
      A('✏ 캡션 수정', () => { const c = el.querySelector('.cap');
        if (c) editText(c, () => { syncFigSpec(el); window.SVGFIG.mount(el); }); });
      A('✏ 그림 밑 설명(※) 수정', () => { const n = el.querySelector('.note');
        if (n) editText(n, () => { syncFigSpec(el); window.SVGFIG.mount(el); }); });
    } else if (info.type === '표') {
      A('✏ 셀 직접 수정', () => editText(el.querySelector('table')));
    } else if (info.type === '장' || info.type === '절') {
      A(`✏ ${info.spec['라벨']} 제목 수정`, () => { const tx = el.querySelector('.tx') || el;
        editText(tx, () => { el.dataset.title = tx.textContent.trim(); }); });
    } else {
      A('✏ 직접 수정', () => editText(el));
    }
  }
  if (has('figlabel')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">글자 — 고치면 바로 다시 그립니다</div>');
    const setters = figSetters(figSpec(el));
    figLabels(el).forEach((t, i) => {
      if (!setters[i]) return;
      A('✏ ' + (svgLabelText(t).slice(0, 14) || '(빈 라벨)'), () => {
        // 예전엔 따옴표 하나만 바꿔 속성 안에 밀어 넣었다 — 잠금은 전부 건다
        panel.innerHTML = `<h3>라벨 수정</h3><input type="text" id="labin" value="${esc(svgLabelText(t))}">`;
        const r = document.createElement('div'); r.className = 'row';
        r.appendChild(btn('적용', () => {
          const s2 = figSpec(el); figSetters(s2)[i](document.getElementById('labin').value);
          setFigSpec(el, s2); window.SVGFIG.mount(el);
          state.ops.push({ action: '도식 라벨' }); repaginate(); select(el);
        }));
        r.appendChild(btn('취소', () => renderPanel()));
        panel.appendChild(r);
        setTimeout(() => document.getElementById('labin').select(), 40);
      });
    });
  }
  if (has('figstep')) {
    A('＋ 단계·항목 추가', () => {
      const s2 = figSpec(el);
      if (s2.type === 'compare') {           // 비교판은 현행·개선 두 판에 한 줄씩
        ['전', '후'].forEach(k => { if (!Array.isArray(s2[k])) s2[k] = []; s2[k].push('새 항목'); });
      } else {
        const arr = 도식배열(s2);
        if (!Array.isArray(arr)) return;
        arr.push('새 항목');
      }
      setFigSpec(el, s2); window.SVGFIG.mount(el);
      state.ops.push({ action: '도식 항목 추가' }); repaginate(); select(el);
    });
    A('－ 마지막 단계 삭제', () => {
      const s2 = figSpec(el);
      if (s2.type === 'compare') {           // 긴 쪽의 끝 줄을 뺀다(두 판에 한 줄씩은 남긴다)
        const a = Array.isArray(s2['전']) ? s2['전'] : [], b = Array.isArray(s2['후']) ? s2['후'] : [];
        const m = Math.max(a.length, b.length);
        if (m <= 1) return;
        if (a.length === m) a.pop();
        if (b.length === m) b.pop();
        setFigSpec(el, s2); window.SVGFIG.mount(el);
        state.ops.push({ action: '도식 항목 삭제' }); repaginate(); select(el);
        return;
      }
      const arr = 도식배열(s2);
      if (!Array.isArray(arr) || arr.length <= 2) return;
      arr.pop(); setFigSpec(el, s2); window.SVGFIG.mount(el);
      state.ops.push({ action: '도식 항목 삭제' }); repaginate(); select(el);
    }, 'danger');
  }
  if (has('level') && info.spec['레벨']) {
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('＋ 상위 단계로', () => changeLevel(el, -1)));
    r.appendChild(btn('－ 하위 단계로', () => changeLevel(el, 1)));
    panel.appendChild(r);
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">${info.spec['레벨'].map(x => x[1]).join(' → ')}</div>`);
  }
  if (has('align')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">정렬</div>');
    const r = document.createElement('div'); r.className = 'row';
    const 현 = _정렬현(el);
    [['좌측', '좌'], ['가운데', '가운데'], ['우측', '우']].forEach(([v, 라벨]) =>
      r.appendChild(btn(라벨, () => 정렬설정(el, v), 현 === v ? 'sel' : '')));
    panel.appendChild(r);
  }
  if (has('mk2') && info.spec['2단마커']) {
    // 2단 마커는 문서 한 벌이 같아야 한다 — 항목 하나만 바꾸면 뒤죽박죽이 된다.
    // 그래서 문서 뿌리(html)에 걸고 CSS 변수로 전체에 미친다.
    const 목록 = info.spec['2단마커'], 기본 = 목록[0];
    // 제목 모양 묶음이 둘째 기호를 정하기도 한다('파랑 겹줄' = ㅇ, CSS 가 data-mk2 없을 때 건다).
    const 묶음 = (상단칸['제목모양'] || []).find(m => m[0] === document.documentElement.getAttribute('data-제목모양'));
    // 따름 = 따로 안 고르면 서는 기호(묶음이 정하면 그 기호, 아니면 ○). 그것을 고르면 속성을 지워
    // 묶음을 따르게 하고, 다른 것을 고르면 — 묶음이 ㅇ 일 때의 ○ 도 — 속성으로 남긴다. 예전엔
    // '○ 로 통일'이 속성을 지워 겹줄의 ㅇ 이 그대로 섰다('26-09-28 2단계 검토 F7·발견 6).
    const 따름 = ((묶음 || [])[4] || {})['2단마커'] || 기본;
    const cur = document.documentElement.dataset.mk2 || 따름;
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">2단 마커 — 문서 전체에 적용됩니다 (지금 ${cur})</div>`);
    목록.forEach(m => A(`${m} 로 통일${m === cur ? '  ✓' : ''}`, () => {
      if (m === 따름) delete document.documentElement.dataset.mk2;
      else document.documentElement.dataset.mk2 = m;
      state.ops = state.ops.filter(o => o.action !== '2단 마커');
      if (m !== 따름) state.ops.push({ action: '2단 마커', to: m });
      save(); repaginate(); select(el);
    }));
  }
  if (has('addBelow')) A('＋ 아래에 항목 추가', () => {
    // 절·장 아래는 첫 단계(○)로, 항목 아래는 그 항목과 같은 단계로 —
    // **한 함수로 한다.** 두 곳에 같은 코드를 두었더니 한쪽만 data-ent 를 붙였다.
    addItemBelow(el, info.type === '절' || info.type === '장');
  });
  if (has('addBox')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">박스 추가</div>');
    ((ENTS['박스'] || {})['종류'] || ['통계근거']).slice(0, 3).forEach(k =>
      A('＋ ' + k + ' 박스', () => addBox(el, k)));
  }
  if (has('addFig')) A('＋ 도식 넣기', () => addFig(el));
  if (has('addItem')) A('＋ 항목 추가', () => { const p = document.createElement('p');
    p.textContent = '새 항목'; el.appendChild(p); editText(p); });
  if (has('addNote')) A('＋ 각주 추가', () => { const p = document.createElement('p');
    p.className = 'fn'; p.textContent = '근거·출처'; el.appendChild(p); editText(p); });
  if (has('tablestyle')) {
    // 표 모양 — 1p 프리셋 여섯을 전 장르로('26-09-29 표 재설계 P1). 후보는 프로파일(1p) 또는 굽는 순간
    // 온톨로지 스타일_프리셋에서 센 목록(표모양들). '기본'은 키를 지워 장르 기본 모양으로 돌린다.
    const tb = el.querySelector('table');
    const 후보 = info.spec['스타일'] || 표모양들;
    const 지금 = el.dataset.표모양 !== undefined ? el.dataset.표모양 : (tb && tb.dataset.style) || '';
    panel.insertAdjacentHTML('beforeend', '<div class="hint">표 모양 — 누르면 바로 바뀝니다</div>');
    const r = document.createElement('div'); r.className = 'row';
    [''].concat(후보).forEach(v => r.appendChild(btn(v || '기본', () => {
      if (!tb) return;
      if (v) tb.dataset.style = v; else delete tb.dataset.style;
      el.dataset.표모양 = v;
      state.ops.push({ action: '표 모양', to: v || '기본' }); repaginate(); save(); select(el);
    }, 지금 === v ? 'sel' : '')));
    panel.appendChild(r);
  }
  if (has('tablerow')) {
    // 새 행은 **격자 열 수**만큼 칸을 만든다 — 마지막 행 칸 수로 만들면 위에서 세로로 합친 칸이
    // 내려와 있는 표에서 칸이 모자랐다(critic_impl #10). 마지막 행을 뺄 때는 그 행까지 내려온
    // 세로 병합 칸을 한 줄 줄인다.
    A('＋ 행 추가', () => { const tb = el.querySelector('table'); const g = 표격자(tb);
      const tr = tb.insertRow(-1);
      for (let i = 0; i < g.n열; i++) tr.insertCell(-1).textContent = '—';
      표조작뒤(el, '표 행 추가'); });
    A('🗑 마지막 행 삭제', () => { const tb = el.querySelector('table'); const g = 표격자(tb);
      if (tb.rows.length <= 2) return;
      const r = g.n행 - 1;
      g.자리.forEach(z => { if (z.r < r && z.r + z.세로 - 1 >= r) z.td.rowSpan = z.세로 - 1; });
      tb.deleteRow(-1); 표조작뒤(el, '표 행 삭제'); }, 'danger');
  }
  if (has('tablecol')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">열 — 누른 칸의 열을 기준으로 넣고 뺍니다</div>');
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('＋ 오른쪽에 열', () => 열넣기(el)));
    // '🗑 … 삭제' 꼴은 개체 삭제(del)의 이름이다 — 열 빼기는 다른 이름으로 둔다(헷갈려 표를 지우지 않게)
    r.appendChild(btn('－ 이 열 빼기', () => 열빼기(el)));
    panel.appendChild(r);
  }
  if (has('tablecell')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">칸 — 누른 칸을 합치거나 나누고, 강조합니다(굵게 + 연한 칠)</div>');
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('→ 합치기', () => 칸합치기(el, '오른쪽')));
    r.appendChild(btn('↓ 합치기', () => 칸합치기(el, '아래')));
    r.appendChild(btn('나누기', () => 칸나누기(el)));
    r.appendChild(btn('강조', () => 칸강조(el)));
    panel.appendChild(r);
  }
  if (has('endstyle')) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">끝 표시 위치</div>');
    // **고른 값을 들고 있어야 한다.** 전에는 조작만 기록하고 값을 아무 데도 안 담아
    // 화면도 안 바뀌고 정본에도 안 닿았다 — 액션이 통째로 죽어 있었다
    // (2026-08-06 B-1 시험에서 걸림). 조립기는 `끝표시` 필드를 읽는다.
    const 지금 = state.끝표시 !== undefined ? state.끝표시 : (getPath0('끝표시') || '같은줄');
    (info.spec['위치'] || []).forEach(v => A(v, () => {
      state.끝표시 = v;
      state.ops.push({ action: '끝 표시', to: v });
      save(); renderPanel();
    }, v === 지금 ? 'sel' : ''));
  }
  if (has('explain') && el.dataset.explain) {
    panel.insertAdjacentHTML('beforeend',
      `<div class="explain">${el.dataset.explain}</div>`);
  }
  if (has('emphasis')) {
    const spans = [...el.querySelectorAll('span.num, span.accent, span.delta')];
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">강조 — 숫자(검정 굵게) · 핵심(남색, 문서 2회까지) · 증감(빨강, △ 필요)</div>`);
    spans.forEach((sp, i) => {
      const kind = sp.classList.contains('accent') ? '핵심'
                 : sp.classList.contains('delta') ? '증감' : '숫자';
      A(`${kind} — ${sp.textContent.slice(0, 12)}`, () => {
        const order = ['num', 'accent', 'delta'];
        const cur = order.findIndex(c => sp.classList.contains(c));
        const next = order[(cur + 1) % order.length];
        if (next === 'delta' && !sp.textContent.includes('△')) {
          toast('증감 강조는 △가 있는 수치에만 씁니다'); return;
        }
        if (next === 'accent' &&
            document.querySelectorAll('span.accent').length >= 2 && cur !== 1) {
          toast('핵심 강조는 문서에 2회까지입니다'); return;
        }
        sp.className = next;
        state.ops.push({ action: '강조', to: next }); save(); renderPanel();
      });
    });
    if (spans.length) A('강조 모두 해제', () => {
      spans.forEach(sp => sp.replaceWith(...sp.childNodes));
      el.normalize(); state.ops.push({ action: '강조 해제' }); save(); renderPanel();
    }, 'danger');
  }
  if (has('endmark')) {
    // **이번 판에서 바꾼 값이 먼저다.** 정본 값만 보면, 눌러서 끝 표시를 켜 놓고도
    // 단추 이름이 "넣기" 로 남아 두 번 눌러도 안 꺼진다(2026-08-06 B-1 시험에서 걸림).
    // 저장하기 전까지 화면과 단추가 어긋나 있었다.
    const on = state.endmark !== undefined
      ? state.endmark : (getPath0('show_end_mark') === true);  // 정본 기본값 False(종결표기_옵션): 1p 표준=표기 없음
    A(on ? '⊘ 끝 표시 숨기기' : '✓ 끝 표시 넣기', () => {
      state.endmark = !on;
      const lbl = el.querySelector('.label');
      const body = el.textContent.replace(/\s*끝\s*\.?\s*$/, '').replace(/^붙임\s*/, '').trim();
      // **textContent 를 innerHTML 로 되돌리면 글자가 태그로 승격한다.** 붙임에
      // `<img src=x onerror=…>` 라고 적혀 있으면 화면에서는 글자였다가 이 한 줄에서
      // 진짜 태그가 된다 — 잠그고 넣는다(WP-S2 ③).
      el.innerHTML = (lbl ? '<span class="label">붙임</span>&nbsp;&nbsp;' : '') + esc(body) +
        (state.endmark ? '&nbsp;&nbsp;끝.' : '');
      state.ops.push({ action: '끝 표시', to: state.endmark ? '표시' : '숨김' });
      save(); renderPanel();
    });
  }
  if (has('toggle')) {
    const on = el.dataset.on !== 'false';
    A(on ? '⊘ 이 요소 빼기' : '✓ 이 요소 넣기', () => {
      applyToggle(el, !on);
      state.ops.push({ action: '구성 요소', to: !on ? '넣음' : '뺌' }); save(); renderPanel();
    }, on ? 'danger' : '');
  }
  if (has('reorder')) {
    const r = document.createElement('div'); r.className = 'row';
    r.appendChild(btn('▲ 위로', () => moveSeq(el, -1)));
    r.appendChild(btn('▼ 아래로', () => moveSeq(el, 1)));
    panel.appendChild(r);
  }
  if (has('addSeq')) A('＋ 아래에 항목 추가', () => {
    const c = el.cloneNode(true);
    c.removeAttribute('data-path'); c.dataset.new = '1';
    c.dataset.parent = el.dataset.path.replace(/\.\d+$/, '');
    const tx = c.querySelector('.tx'); if (tx) tx.textContent = '새 항목';
    const why = c.querySelector('.why'); if (why) why.remove();
    el.after(c); renumberSeq(el.dataset.path.replace(/\.\d+$/, ''));
    state.ops.push({ action: '본문 항목 추가' }); save(); select(c);
    if (tx) editText(tx);
  });
  if (has('pagehide')) {
    const idx = el.dataset.pageIdx || '?';
    const hidden = el.hasAttribute('data-no-pageno');
    panel.insertAdjacentHTML('beforeend',
      `<div class="hint">${idx}번째 쪽입니다. 번호는 표지부터 통산합니다.</div>`);
    A(hidden ? '① 이 쪽에 쪽번호 보이기' : '⊘ 이 쪽의 쪽번호 감추기', () => {
      const next = hidden;                       // 감춰져 있었으면 보이게
      el.dataset.flag = '쪽번호.표시.' + idx;    // 손댄 쪽에만 훅을 단다
      el.dataset.on = String(next);
      if (next) el.removeAttribute('data-no-pageno'); else el.setAttribute('data-no-pageno', '1');
      state.ops.push({ action: '쪽번호', to: idx + '쪽 ' + (next ? '보임' : '감춤') });
      save(); renderPanel();
    });
  }
  if (has('pagestart')) {
    const idx = el.dataset.pageIdx || '?';
    A('①→ 이 쪽부터 번호 새로 시작', () => {
      const box = document.createElement('div'); box.className = 'row';
      const inp = document.createElement('input');
      inp.type = 'number'; inp.min = '1'; inp.value = el.dataset.restart || '1';
      inp.style.cssText = 'width:70px;padding:4px;border:1px solid var(--ai-color-line-strong);border-radius:4px';
      box.appendChild(inp);
      box.appendChild(btn('적용', () => {
        const v = String(Math.max(1, parseInt(inp.value, 10) || 1));
        el.dataset.restart = v;
        // 값을 DOM에 남겨야 저장기가 집어간다 — 모델에 직접 쓰면 다시 그릴 때 지워진다
        el.dataset.cycle = '쪽번호.새번호시작.' + idx;
        el.dataset.lv = v;
        state.ops.push({ action: '쪽번호 시작', to: idx + '쪽부터 ' + v });
        save();
        if (typeof repaginate === 'function') repaginate();
        renderPanel();
      }));
      panel.appendChild(box);
    });
  }
  // 못 얻은 그림('26-09-30) — 산출물에는 빠지는 자리다. 까닭(사람 말)을 먼저 보인다.
  if (el.classList.contains('fr-img') && el.dataset.miss) {
    const 말 = ((el.querySelector('.ph') || {}).textContent || '').replace('[이미지 미확보] ', '');
    panel.insertAdjacentHTML('beforeend', '<div class="hint">' + esc(말)
      + ' — 내보낸 문서(PDF·한글·발표 파일)에는 이 자리가 빠집니다.</div>');
  }
  if (has('imgsize')) {
    const spec = imgSpec(el), img = el.querySelector('img');
    panel.insertAdjacentHTML('beforeend', '<div class="hint">지면 폭에 대한 비율입니다.</div>');
    (info.spec['크기'] || ['40%', '60%', '80%', '100%']).forEach(w => A(w, () => {
      spec['폭'] = w; imgSave(el, spec);
      if (img) img.style.width = w;
      state.ops.push({ action: '그림 크기', to: w }); save(); renderPanel();
    }, (spec['폭'] || '80%') === w ? 'sel' : ''));
  }
  if (has('imgcap')) {
    A('✏ 그림 제목 고치기', () => {
      const spec = imgSpec(el);
      줄고치기('그림 제목 (표 제목처럼 < > 안에 들어갑니다)', spec['캡션'] || '', v => {
        spec['캡션'] = v; imgSave(el, spec);
        let cap = el.querySelector('.cap');
        if (!cap && v) { cap = document.createElement('div'); cap.className = 'cap';
                         el.insertBefore(cap, el.firstChild); }
        if (cap) cap.textContent = v ? '< ' + v + ' >' : '';
        state.ops.push({ action: '그림 제목' }); save(); renderPanel();
      });
    });
    A('✏ 이 그림이 말하는 것 고치기', () => {
      const spec = imgSpec(el);
      줄고치기('이 그림에서 읽어야 할 것 (※ 로 붙습니다)', spec['함의'] || '', v => {
        spec['함의'] = v; imgSave(el, spec);
        let n = el.querySelector('.note');
        if (!n && v) { n = document.createElement('div'); n.className = 'note'; el.appendChild(n); }
        if (n) n.textContent = v;
        state.ops.push({ action: '그림 설명' }); save(); renderPanel();
      });
    });
  }
  if (has('imgcrop')) {
    A('⛶ 쓸 부분 고르기', () => 자르기시작(el));
  }
  if (has('planfix')) {
    const P = el.dataset.planPath;
    const tgt = P ? planTarget(P) : null;
    if (!tgt) {
      panel.insertAdjacentHTML('beforeend',
        '<div class="hint">이 항목은 이 화면에서 바로 고칠 자리가 없습니다 — '
        + '위에서 해당하는 곳을 직접 손봐 주세요.</div>');
    } else {
      A('↗ 바꿀 곳으로 가기', () => {
        tgt.scrollIntoView({ block: 'center', behavior: 'smooth' });
        select(tgt); renderPanel();
      });
      const sug = el.dataset.suggest;
      if (sug !== undefined) A(`이대로 바꾸기 → ${sug}`, () => {
        // 카드가 만들어진 뒤에 그 자리가 이미 바뀌었을 수 있다 — 덮어쓰지 않고 알린다
        const was = el.dataset.planWas;
        if (was !== undefined && planCur(tgt) !== was) {
          toast('이 요청이 가리키던 곳이 그새 바뀌었습니다 — 직접 확인해 주세요');
          tgt.scrollIntoView({ block: 'center' }); select(tgt); renderPanel(); return;
        }
        const tspec = (entInfo(tgt) || {}).spec || {};
        if (tgt.dataset.flag) applyToggle(tgt, sug === 'true' || sug === '넣음');
        else if (tgt.dataset.cycle) applyCycle(tgt, tspec, sug);
        else {
          const leaf = planLeaf(tgt);
          setText(leaf, sug);          // data-shown 은 건드리지 않는다(고친 걸로 인식돼야 저장된다)
          if (tgt.dataset.title !== undefined) tgt.dataset.title = sug;
        }
        applyCycle(el, info.spec, '반영');
        state.ops.push({ action: '확인할 것 반영', to: sug });
        save(); renderPanel();
        toast('구성 설계를 고쳤습니다 — 문서를 다시 만들어야 반영됩니다');
      }, 'good');
    }
  }
  if (has('cycle') && info.spec['값']) {
    panel.insertAdjacentHTML('beforeend', '<div class="hint">'
      + (info.spec['값힌트'] || '가능성 — 실제로 넣을지는 다음 단계에서 정합니다') + '</div>');
    info.spec['값'].forEach(v => A(cycShow(info.spec, v), () => {
      applyCycle(el, info.spec, v);
      state.ops.push({ action: info.spec['라벨'], to: (cycPre(info.spec) + ' ' + v).trim() });
      save(); renderPanel();
    }, el.dataset.lv === v ? 'sel' : ''));
  }
  // 남긴 지시는 apply_edit_any 가 '대기'로 기록만 하고 채팅의 Claude 가 읽어 반영한다.
  // 웹앱엔 그 Claude 가 없어 눌러도 아무 일도 안 일어나므로(죽은 기능) 감춘다.
  // 플러그인/파일 표면 — 곁의 채팅 Claude 가 메모를 읽어 반영(웹앱엔 그 Claude 가 없어 감춘다).
  if (플러그인 && has('ai')) A('✍ AI에게 고쳐달라 하기 — ' + info.spec['라벨'], () => addNote(el, info));
  // 웹앱 — 곁 채팅이 없으니 브라우저에서 사용자 키로 직접 고쳐 그 자리에 넣는다(BYOK, 서버 미경유).
  else if (서버있음 && has('ai')) A('✍ AI로 다시 써줘 — ' + info.spec['라벨'], () => ai다시쓰기(el, info));
  if (has('delSection')) A('🗑 절 전체 삭제', () => {
    const gid = el.dataset.group; const kill = [el];
    document.querySelectorAll(`.blk[data-group="${gid}"]`).forEach(n => { if (n !== el) kill.push(n); });
    kill.forEach(n => n.remove());
    state.ops.push({ action: '삭제', target: '절 ' + (el.dataset.title || '') });
    select(null); repaginate();
  }, 'danger');
  if (has('del')) A('🗑 ' + info.spec['라벨'] + ' 삭제', () => delEl(el, info), 'danger');
  appendPending();
}
function appendPending() {
  const keys = Object.keys(state.notes);
  if (!keys.length && !state.ops.length) return;
  // 열쇠는 개체 라벨(문서 글자), 값은 **사람이 적어 넣은 요청**이다 — 둘 다 잠근다
  // 제목: 「AI에게 고쳐달라」 요청(notes)이 있어야 진짜 '대기'다. 웹앱의 ops 는 이미 적용·저장된
  // 편집 로그인데 '대기 중 작업'이라 적혀 "수정이 안 되는 거냐"는 오해를 불렀다(2026-09-06).
  const 제목 = keys.length ? '대기 중 작업' : '이번에 고친 것';
  panel.insertAdjacentHTML('beforeend', '<div class="notes"><b>' + 제목 + '</b><ul>' +
    keys.map(k => `<li>📌 ${esc(k)}: ${esc(state.notes[k])}</li>`).join('') +
    // 대상은 괄호로 — '· 칸 강조 표'처럼 대상이 동작 이름에 붙어 읽혔다(적대 검토 L1 '26-09-29)
    state.ops.slice(-6).map(o => `<li>· ${esc(o.action)}${o.to ? ' → ' + esc(o.to) : ''}${o.target ? ' (' + esc(o.target) + ')' : ''}</li>`).join('') +
    '</ul><div class="hint">' + (keys.length
      // 「AI에게 고쳐달라」 지시는 곁의 채팅 Claude 가 대기 목록을 읽어 반영한다 — 로컬 서버라도
      // 저장(/save)은 지시를 정본에 얹어 둘 뿐, 실제 고쳐 쓰기는 채팅이 한다.
      ? '「AI에게 고쳐달라」 요청은 채팅에 "고쳐놨어"라고 하시면 반영합니다'
      : (채팅표면
          ? '채팅에 "고쳐놨어"라고 하시면 반영해 다시 만듭니다'
          : '고친 내용은 저장하는 즉시 문서에 반영됩니다')) + '</div></div>');
}

// ── 직렬화: 원본 모델을 복제해 '경로(data-path)'로 패치 ──
// DOM 순서 워크 + 커서 방식은 절 제목을 지우면 항목이 유실되고, jachigan 잔해까지
// 되살리는 구조적 결함이 있었다(적대 검증 확정). 원본을 신뢰하고 델타만 얹는다.
const SRCDOC = JSON.parse(document.getElementById('fr-doc').textContent);
state.정렬 = (SRCDOC['_정렬'] && JSON.parse(JSON.stringify(SRCDOC['_정렬']))) || {};   // 경로별 정렬 오버레이(왕복)
// 문서를 **처음 그렸을 때** 있었던 data-path 전부 — 저장할 때 지금(alive)과 견주어
// '배열도 top-level 키도 아닌, 부모는 그대로 살아있는데 이 자리만 사라진' 삭제를 찾는다
// (풀버전 절.표, 슬라이드 출처, 1p 붙임·표처럼 개체 이름과 정본 키가 다른 경우 포함 —
// ②-b 최상위 선택키·prune 배열 둘 다 못 보던 자리다, asm:R7-02). 처음 한 번만 재면
// 된다 — 그 뒤 새로 생긴 자리(addBelow)는 data-new 로 따로 표시돼 이 집합과 안 섞인다.
const 원본경로 = new Set([...document.querySelectorAll('[data-path]')].map(x => x.dataset.path));

// ── WP-S10 2차-B: 문체 동의 카드 — "리터칭"(사람이 직접 다듬는 것) 흐름의 훅 ──────
// 저장마다(아래 보내기()) 마지막 진단 기준(문체기준)과 지금 막 고친 내용을 backtrace
// 세그먼트 diff 로 견주어(서버 `문체후보` → feedback/backtrace.py 의 extract·diff_docs
// 그대로, 1차·2차-A 가 실측한 그 함수) 조를 만한 낱말 치환을 찾으면 F1 동의 카드를
// 띄운다. 기본은 안 묻는 상태다 — 서버가 후보를 null 로 돌려주면(변경이 없거나 이
// 문서가 backtrace 대상(1p) 이 아니면) 카드는 아예 안 뜬다.
let 문체기준 = SRCDOC;                  // 마지막으로 진단한 기준 — 첫 저장 전엔 원본 그대로
const 물어본문체델타 = new Set();
// 한글 받침 유무로 조사를 고른다(을/를·으로/로) — 낱말이 사용자가 쓴 임의 값이라
// 고정 조사를 박으면 절반은 어색해진다("설치"를 "구축"**로** 는 맞지만 "이전"을
// "이후"**으로** 처럼 받침이 있으면 "로"가 틀린다).
function 받침있나(s) {
  const c = String(s || '').trim().slice(-1).codePointAt(0);
  if (c === undefined || c < 0xAC00 || c > 0xD7A3) return false;   // 한글 완성형이 아니면 판단 보류
  return (c - 0xAC00) % 28 !== 0;
}
function 동의카드보이기(항목, 설명) {
  if (document.querySelector('.consent-card')) return;   // 이미 하나 떠 있으면 겹치지 않는다
  const el = document.createElement('div');
  el.className = 'consent-card';
  el.innerHTML = `<div class="cc-head">
      <svg class="cc-logo" viewBox="0 0 100 100" aria-hidden="true">
        <path d="M17 9h45l21 21v61H17z"/><path d="M62 9v24h21"/><path d="M31 47h37M31 60h37M31 73h25"/>
      </svg>
      <div class="cc-word"><b>문서지능</b><span>피드백으로 문서 품질을 함께 높입니다</span></div>
    </div><div class="cc-body">
    <p>${esc(설명)}</p>
    <div class="cc-why">
      <label for="cc-why-input">왜 바꾸셨는지 한 줄 남겨 주시면 더 정확히 반영됩니다 (선택)</label>
      <input type="text" id="cc-why-input" placeholder="분량이 많아 풀버전이 맞다고 봤습니다">
      <p class="cc-hint">이름·연락처 등 개인정보는 빼고 적어 주세요.</p>
    </div>
    <div class="cc-row">
      <button data-d="이번만 아니오">이번만 아니오</button>
      <button data-d="앞으로 묻지 않기">다시 묻지 않기</button>
      <button data-d="남깁니다" class="good">남기기</button>
    </div></div>`;
  document.body.appendChild(el);
  el.querySelector('.cc-row').onclick = async e => {
    const b = e.target.closest('button[data-d]'); if (!b) return;
    const 결정 = b.dataset.d;
    // "왜" 칸은 선택 — el.remove() 전에 값을 챙긴다.
    const 왜 = ((el.querySelector('#cc-why-input') || {}).value || '').trim();
    el.remove();
    if (결정 === '앞으로 묻지 않기') sessionStorage.setItem('ai-consent-skip-style', '1');
    if (결정 !== '남깁니다') return;    // **동의 없이는 저장 API 를 아예 안 부른다**(왜칸 값이 있어도 마찬가지)
    try {
      // 왜칸 값을 `지시`(이유)로 실어 보낸다 — 엔진(`_항목빚기`, feedback/corpus.py 손 안 댐)이
      // 동의 뒤 한 번에 비식별한다. 안 쓰면 항목이 이미 들고 있던 지시(문체는 늘 없음)를 그대로 둔다.
      await fetch('/api/동의코퍼스', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 결정, 항목: { ...항목, 지시: 왜 || 항목.지시 || null } }) });
    } catch (e) { /* 반영(/save) 은 이미 끝났다 — 코퍼스 기록만 못 갔을 뿐, 조용히 넘어간다 */ }
  };
}
async function 문체동의진단(이후) {
  const 이전 = 문체기준;
  문체기준 = 이후;                       // 이 진단 이후로는 "지금"이 새 기준이다(중복 질문 방지)
  if (sessionStorage.getItem('ai-consent-skip-style')) return;
  try {
    const r = await fetch('/api/문체후보', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: FN, 이전, 이후 }) });
    const j = await r.json();
    const 항목 = j.ok ? j['값'] : null;
    if (!항목) return;                   // 변경 없음·1p 아님·주목할 변경 아님 — 조용히 넘어간다
    const d = 항목['델타'] || {};
    const 델타키 = String(d['전']) + '→' + String(d['후']);
    if (물어본문체델타.has(델타키)) return;    // 같은 치환은 이 화면에서 한 번만 묻는다
    물어본문체델타.add(델타키);
    동의카드보이기(항목,
      `방금 「${d['전']}」${받침있나(d['전']) ? '을' : '를'} 「${d['후']}」${받침있나(d['후']) ? '으로' : '로'} 다듬으셨습니다.\n\n` +
      `이런 손질이 규칙을 다듬는 데 큰 도움이 됩니다.\n피드백으로 남겨도 될까요?\n\n` +
      `원문도 개인정보도 저장하지 않습니다.\n무엇을 어떻게 바꾸셨는지만 익명으로 남습니다.`);
  } catch (e) { /* 서버가 없거나 file:// 로 열렸을 때(자가검사)는 조용히 건너뛴다 */ }
}

function stripAngle(t) {   // '< 제목 >' → '제목'
  return String(t).replace(/^\s*[<＜]\s*/, '').replace(/\s*[>＞]\s*$/, '').trim();
}
function getPath0(p) { try { return getPath(SRCDOC, p); } catch (e) { return undefined; } }
function getPath(o, path) {
  const ks = path.split('.');
  for (const k of ks) { if (o == null) return undefined; o = o[/^\d+$/.test(k) ? +k : k]; }
  return o;
}
function setPath(o, path, v) {
  const ks = path.split('.');
  for (let i = 0; i < ks.length - 1; i++) {
    const k = /^\d+$/.test(ks[i]) ? +ks[i] : ks[i];
    if (o[k] == null) o[k] = /^\d+$/.test(ks[i + 1]) ? [] : {};
    o = o[k];
  }
  const last = ks[ks.length - 1];
  o[/^\d+$/.test(last) ? +last : last] = v;
}
// ── 경로 조각 모으기 ────────────────────────────────────────────────────
// 자간 조정(jachigan)은 줄에 걸친 범위를 span 으로 감싼다. 그런데
// Range.extractContents() 는 **걸친 요소를 속성까지 복제**하므로, data-path 를 단
// span 하나가 조각 수십 개로 흩어진다. 조각 하나만 읽으면 글이 잘린 채 저장된다
// — 2026-08-04 규정·보도자료 왕복 실패의 원인이었다(규정 본문 1문단이 64조각).
// 1p·풀버전이 멀쩡했던 것은 경로를 블록(<p>)에 걸어 블록 자체는 안 쪼개졌기 때문이다.
// 경로를 잎(span)에 거는 장르가 늘면 또 샌다. 그래서 클래스가 아니라 **경로로 모은다.**
function 경로조각() {
  const m = new Map();
  document.querySelectorAll('[data-path]').forEach(el => {
    const p = el.dataset.path;
    if (!m.has(p)) m.set(p, []);
    m.get(p).push(el);
  });
  return [...m.entries()];
}
function 이어붙임(els) {
  if (els.length === 1) return els[0];
  // 조각은 문서 순서대로 온다. innerHTML 을 이어 붙이면 조각 사이 공백과
  // 강조 태그가 그대로 살아난다(조각마다 trim 하면 어절이 붙어버린다).
  const box = document.createElement('span');
  box.className = els[0].className;
  box.innerHTML = els.map(x => x.innerHTML).join('');
  return box;
}
function textOf(el) {                    // jachigan 잔해·빈 강조 껍데기를 걷어낸 3층 표기
  const c = el.cloneNode(true);
  c.querySelectorAll('span.jachigan-run').forEach(s => s.replaceWith(...s.childNodes));
  c.querySelectorAll('.no,.cap,.fn').forEach(x => { if (x !== c) x.remove(); });
  c.querySelectorAll('b,u,span.lb').forEach(x => { if (!x.textContent.trim()) x.remove(); });
  c.normalize();
  c.querySelectorAll('span.lb').forEach(x => x.replaceWith(document.createTextNode('<lb>' + x.textContent + '</lb>')));
  c.querySelectorAll('b').forEach(x => x.replaceWith(document.createTextNode('<b>' + x.textContent + '</b>')));
  c.querySelectorAll('u').forEach(x => x.replaceWith(document.createTextNode('<u>' + x.textContent + '</u>')));
  let t = c.innerHTML !== undefined ? c.innerHTML : c.textContent;
  t = t.replace(/<br\s*\/?>/gi, '\n');                 // 표지 제목 2줄 보존
  t = t.replace(/<[^>]+>/g, '');                        // 남은 태그 제거
  const d = document.createElement('textarea'); d.innerHTML = t; t = d.value;
  // 인접 중복 강조 병합(<b>a</b><b>b</b> → <b>ab</b>)
  t = t.replace(/<\/(b|u)><\1>/g, '').replace(/<\/lb><lb>/g, '');
  return t.replace(/ /g, ' ').replace(/[ \t]+/g, ' ').trim();
}
// 도식: 라벨 순서 → 유형별 필드 설정자(적대 검증 확정 결함 — _labels는 아무도 안 읽었다)
function figSetters(sp) {
  const S = [];
  const put = (fn) => S.push(fn);
  if (sp.type === 'process') (sp['단계'] || []).forEach((st, i) => put(v => {
    if (typeof sp['단계'][i] === 'object') sp['단계'][i]['라벨'] = v; else sp['단계'][i] = v; }));
  else if (sp.type === 'cycle') (sp['단계'] || []).forEach((st, i) => put(v => {
    if (typeof sp['단계'][i] === 'object') sp['단계'][i]['라벨'] = v; else sp['단계'][i] = v; }));
  else if (sp.type === 'converge') {
    (sp['요건'] || []).forEach((r, i) => put(v => sp['요건'][i] = v));
    // 시행이 비면 svgfig.js 가 가운데 상자를 안 그린다 — 설정자도 안 만든다(라벨 차례가 맞고, 열기만 해도
    // 빈 '시행' 키가 채워지던 것도 멎는다. 적대 검토 M6 '26-09-29)
    const 시행글 = x => (x && typeof x === 'object')      // svgfig.js lab() 과 같은 읽기
      ? String(x['라벨'] ?? x.label ?? x.name ?? x['이름'] ?? x['제목'] ?? x.text ?? x.title ?? '') : String(x ?? '');
    if (시행글(sp['시행']).trim()) put(v => sp['시행'] = v);
    put(v => sp['결과'] = v);
  } else if (sp.type === 'strategy') {
    put(v => sp['목표'] = v);
    (sp['전략'] || []).forEach((c, i) => {
      // 원소가 라벨 필드를 이미 가졌으면(정규화가 제목 곁에 라벨을 채운 꼴) 그리는 쪽(lab: 라벨 먼저)이
      // 읽는 자리도 같이 고친다 — 제목만 고치면 화면은 옛 라벨을 그려 고친 것이 사라진다
      put(v => { const o = sp['전략'][i];
        if (!o || typeof o !== 'object') { sp['전략'][i] = v; return; }
        if (o['라벨'] != null) o['라벨'] = v;
        if (o['제목'] != null || o['라벨'] == null) o['제목'] = v; });
      (Array.isArray(c && c['과제']) ? c['과제'] : []).forEach((t, j) =>
        put(v => 라벨넣기(sp['전략'][i]['과제'], j, v.replace(/^▪\s*/, ''))));
    });
  } else if (sp.type === 'relation') (sp['노드'] || []).forEach((n, i) => put(v => {
    if (typeof sp['노드'][i] === 'object') sp['노드'][i]['라벨'] = v; else sp['노드'][i] = v; }));
  else if (sp.type === 'compare') {
    // 비교판 — 차례는 svgfig.js G.compare 의 data-gi 와 같다: 현행 머리, 전[], 개선 머리, 후[].
    // 머리는 스펙에 없으면 기본 낱말(현행·개선)이라, 안 고쳤으면 키를 새로 만들지 않는다(왕복 불변식)
    const 머리넣기 = (k, 기본) => put(v => {
      const h = Array.isArray(sp['머리']) ? sp['머리'].slice(0, 2) : [];
      const 지금 = (h[k] && typeof h[k] === 'object') ? String(h[k]['라벨'] ?? h[k]['이름'] ?? '') : String(h[k] ?? '');
      if (v === (지금 || 기본)) return;
      while (h.length < 2) h.push(h.length === 0 ? '현행' : '개선');
      h[k] = v; sp['머리'] = h; });
    머리넣기(0, '현행');
    (Array.isArray(sp['전']) ? sp['전'] : []).forEach((x, i) => put(v => 라벨넣기(sp['전'], i, v)));
    머리넣기(1, '개선');
    (Array.isArray(sp['후']) ? sp['후'] : []).forEach((x, i) => put(v => 라벨넣기(sp['후'], i, v)));
  }
  return S;
}
// 배열 원소 라벨을 원소 모양 그대로 되쓴다 — 문자열이면 문자열로, 객체면 그리는 쪽(svgfig lab)이 읽는
// 첫 라벨 필드에. 객체를 문자열로 덮으면 색 역할·주체 같은 곁 키가 날아간다
function 라벨넣기(arr, i, v) {
  const x = arr[i];
  if (x && typeof x === 'object') {
    const k = ['라벨', 'label', 'name', '이름', '제목', 'text', 'title'].find(k => x[k] != null) || '라벨';
    x[k] = v;
  } else arr[i] = v;
}
function svgLabelText(t) {   // tspan 사이에 공백을 넣어 어절 손실 방지
  // 격자 칸(td) — 칸 하나가 라벨 하나다. 자간 조정이 쪼갠 조각·<br> 은 공백 하나로 잇는다
  if (t.tagName === 'TD') return (t.textContent || '').replace(/\s+/g, ' ').trim();
  return [...t.querySelectorAll('tspan')].map(x => x.textContent.trim()).join(' ').trim();
}
// 격자(표) 도식 저장('26-09-29 격자 도식 P2, critic_impl §5) — 칸 글을 data-gi 차례로 스펙에 되박는다.
// 스펙은 그대로다(체계도 {목표, 전략[{제목, 과제[]}]} · 흐름 {단계[]} · 비교판 {전[], 후[]}). 표 모양(병합·칠·
// 열폭)은 저장하지 않는다 — 그리는 쪽(svgfig.js)이 스펙에서 다시 짓는다. 그래서 저장을 되풀이해도 칸이
// 밀리지 않는다. tableOf() 로 저장하면 스펙이 header·rows 로 바뀌어 도식이 표가 된다(그래서 쓰지 않는다).
function gridOf(el, sp) {
  const S = figSetters(sp);
  [el, ...도식이음들(el)].flatMap(x => [...x.querySelectorAll('table.fig-grid td[data-gi]')]).forEach(td => {
    const i = Number(td.dataset.gi);
    if (Number.isInteger(i) && S[i]) S[i](svgLabelText(td));
  });
  return sp;
}
function syncFigSpec(el) {
  const sp = figSpec(el);
  const cap = el.querySelector('.cap'), nt = el.querySelector('.note');
  if (cap) sp['캡션'] = stripAngle(cap.textContent);
  if (nt) sp['함의'] = nt.textContent.replace(/^※\s*/, '').trim();
  if (el.querySelector('table.fig-grid')) gridOf(el, sp);
  else {
    const setters = figSetters(sp), labs = figLabels(el);
    labs.forEach((t, i) => { if (setters[i]) setters[i](svgLabelText(t)); });
  }
  setFigSpec(el, sp);
  return sp;
}
function boxOf(el) {
  const items = [], fns = [];
  [...el.children].forEach(p => {
    if (p.classList.contains('cap')) return;
    if (p.classList.contains('fn')) fns.push(textOf(p)); else items.push(textOf(p));
  });
  const cap = el.querySelector('.cap');
  const o = { '종류': el.dataset.box, '항목': items };
  if (cap) o['캡션'] = stripAngle(cap.textContent);
  if (fns.length) o['각주'] = fns;
  return o;
}
// 그림 — 스펙을 통째로 실어 두고(data-img) 읽고 쓴다. 도식(syncFigSpec)과 같은 방식이다.
// 한 줄 고치기 — prompt() 를 못 쓰므로 패널 안에서 받는다
function 줄고치기(라벨, 지금값, 끝나면) {
  const bar = document.createElement('div');
  bar.className = 'resume-bar';
  bar.innerHTML = '<b>' + 라벨 + '</b>';
  const inp = document.createElement('input');
  inp.type = 'text'; inp.value = 지금값;
  inp.style.cssText = 'display:block;width:100%;margin-top:6px;padding:6px 8px;'
    + 'border:1px solid var(--ai-color-line-strong);border-radius:5px;font:inherit;box-sizing:border-box';
  bar.appendChild(inp);
  const row = document.createElement('div'); row.className = 'row';
  row.appendChild(btn('저장', () => { 끝나면(inp.value.trim()); bar.remove(); }, 'good'));
  row.appendChild(btn('취소', () => bar.remove()));
  bar.appendChild(row);
  document.body.insertBefore(bar, document.body.firstChild);
  inp.focus(); inp.select();
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { 끝나면(inp.value.trim()); bar.remove(); }
    if (e.key === 'Escape') bar.remove();
  });
}

// 쓸 부분 고르기 — 화면의 그림 위에 상자를 끌어 그린다.
// 여기서 정하는 것은 '어디를' 뿐이고, 실제로 자르는 것은 반영할 때 원본에서 한다.
function 자르기시작(el) {
  const img = el.querySelector('img');
  if (!img) { toast('아직 그림이 들어오지 않았습니다'); return; }
  document.querySelectorAll('.crop-wrap').forEach(x => {          // 끝내지 않은 자르기 — 그림 모양을 되돌리고 벗긴다
    x.querySelectorAll('img[data-crop-style]').forEach(i => {
      const s = i.dataset.cropStyle; if (s) i.setAttribute('style', s); else i.removeAttribute('style');
      i.removeAttribute('data-crop-style'); });
    x.querySelectorAll('.crop-sel').forEach(s => s.remove());
    x.replaceWith(...x.childNodes);
  });
  const spec = imgSpec(el);
  // 자르는 동안 그림 크기·비율을 그대로 둔다(그림 P3 '26-09-30 실입력) — 예전엔 inline-block 그릇에 넣는 순간 그림의
  // 폭(mm·%)이 그릇 기준으로 다시 풀려 비율이 찌그러지고(368×458, 원래 1.6:1), 끈 상자가 원본 자리와 어긋났다.
  // 그릇에 보이던 크기를 px 로 박고 그림은 그 그릇을 채운다. 끝나면 그림 모양(style)을 되돌린다.
  const 본 = img.getBoundingClientRect();
  img.dataset.cropStyle = img.getAttribute('style') || '';
  const wrap = document.createElement('span');
  wrap.className = 'crop-wrap';
  wrap.style.cssText = `position:relative;display:block;width:${본.width}px;height:${본.height}px;margin:0 auto;line-height:0`;
  img.replaceWith(wrap); wrap.appendChild(img);
  img.style.cssText = 'display:block;width:100%;height:100%;max-width:none;max-height:none;margin:0';
  const sel = document.createElement('div');
  sel.className = 'crop-sel';
  wrap.appendChild(sel);
  const 풀기 = () => {
    window.removeEventListener('click', 클릭막기, true);
    const s = img.dataset.cropStyle; if (s) img.setAttribute('style', s); else img.removeAttribute('style');
    img.removeAttribute('data-crop-style');
    wrap.replaceWith(...[...wrap.childNodes].filter(n => n !== sel));
  };

  // 보이는 그림은 이미 잘린 그림이다(조립이 스펙의 크롭으로 자른 것) — 새로 끈 상자는 **보이는 그림 기준**이라
  // 원본(카드 그림·첨부) 기준으로 합성해 저장한다(그림 P3 '26-09-30, design §5-3·critic_impl #21). 예전엔 보이는
  // (잘린) 그림 위 비율을 원본 기준 크롭으로 그대로 적어, 두 번째 자르기가 엉뚱한 곳을 잘랐다. 보이는 그림이 어떤
  // 크롭을 반영하는지는 data-shown-crop 에 적어 둔다(바꾸기 직후 = 전체, 이번 화면에서 자른 뒤 = 새 크롭).
  const 상자 = v => {
    if (Array.isArray(v) && v.length === 4 && v.every(n => typeof n === 'number' && isFinite(n))) return v;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const b = [v.x, v.y, v.w, v.h].map(Number); return b.every(isFinite) ? b : null; }
    return null;
  };
  let 보임 = null;
  try { 보임 = el.dataset.shownCrop !== undefined ? 상자(JSON.parse(el.dataset.shownCrop))
        : 상자(spec['크롭']) || (spec['그림'] ? null : 상자(spec['자를곳'])); } catch (e) { 보임 = null; }
  let x0 = 0, y0 = 0, 끄는중 = false;
  const 놓기 = (l, t, w, h) => {
    sel.style.cssText = `position:absolute;left:${l * 100}%;top:${t * 100}%;`
      + `width:${w * 100}%;height:${h * 100}%;border:2px solid var(--ai-color-issue);`
      + 'background:color-mix(in srgb, var(--ai-color-issue) 10%, transparent);box-sizing:border-box';
  };
  놓기(0, 0, 1, 1);

  const 비율 = e => {
    const r = img.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
            Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  // 끄는 동안은 창 전체에서 받는다 — 그림 밖(오른쪽 편집 패널 위 등)으로 나가도 가장자리까지 잡힌다(비율이 0~1 로
  // 잘린다). 예전엔 그릇 위에서만 받아, 패널에 가린 오른쪽 끝까지 끌면 상자가 95% 에서 멈췄다(그림 P3 실입력)
  const 끌기 = e => {
    if (!끄는중) return;
    const [x, y] = 비율(e);
    놓기(Math.min(x0, x), Math.min(y0, y), Math.abs(x - x0), Math.abs(y - y0));
  };
  // 끌기를 놓을 때 따라오는 click 이 문서 드릴다운으로 가 고른 그림이 '쪽'으로 바뀌던 것을 막는다(실입력에서 잡음)
  let 막을클릭 = false;
  const 클릭막기 = e => {
    if (막을클릭 || (e.target.closest && e.target.closest('.crop-wrap'))) { e.stopPropagation(); e.preventDefault(); }
    막을클릭 = false;
  };
  if (window.__자르기클릭) window.removeEventListener('click', window.__자르기클릭, true);   // 끝내지 않은 앞 자르기
  window.__자르기클릭 = 클릭막기;
  window.addEventListener('click', 클릭막기, true);
  const 놓음 = e => {
    if (끄는중) { 끌기(e); 막을클릭 = true; setTimeout(() => { 막을클릭 = false; }, 0); }
    끄는중 = false;
    window.removeEventListener('mousemove', 끌기, true); window.removeEventListener('mouseup', 놓음, true);
  };
  wrap.onmousedown = e => {
    e.preventDefault(); [x0, y0] = 비율(e); 끄는중 = true;
    window.addEventListener('mousemove', 끌기, true); window.addEventListener('mouseup', 놓음, true);
  };

  const bar = document.createElement('div');
  bar.className = 'resume-bar';
  bar.innerHTML = '<b>그림 위에서 쓸 부분을 끌어 주세요.</b> '
    + '여기서는 자리만 정하고, 실제로 자르는 것은 문서에 반영할 때 원본에서 합니다.';
  const row = document.createElement('div'); row.className = 'row';
  row.appendChild(btn('이 부분으로', () => {
    const st = sel.style;
    const v = k => parseFloat(st[k]) / 100;
    const box = [v('left'), v('top'), v('width'), v('height')].map(n => +n.toFixed(4));
    if (box[2] < 0.02 || box[3] < 0.02) { toast('너무 좁습니다 — 다시 끌어 주세요'); return; }
    // 원본 기준 합성: 보이는 그림이 크롭 b 를 반영하면 새 상자 s 는 b 안의 비율이다 → [b0+s0·b2, b1+s1·b3, s2·b2, s3·b3]
    // (b 가 픽셀이면 픽셀로, 비율이면 비율로 — 같은 식이다)
    const 비율꼴 = !보임 || Math.max(...보임) <= 1;
    const 합 = 보임 ? [보임[0] + box[0] * 보임[2], 보임[1] + box[1] * 보임[3], box[2] * 보임[2], box[3] * 보임[3]] : box;
    const 새크롭 = 합.map(n => 비율꼴 ? +n.toFixed(4) : Math.round(n));
    const sp = imgSpec(el); sp['크롭'] = 새크롭; delete sp['자를곳']; imgSave(el, sp);
    state.ops.push({ action: '그림 자르기' });
    // 미리보기 — 보이는 그림을 그 자리에서 잘라 보여 준다(같은 출처·data: 그림만 캔버스로 읽힌다. 안 되면 그대로 두고
    // 보이는 그림이 반영하는 크롭도 그대로 적어 다음 자르기의 합성 기준이 어긋나지 않게 한다)
    let 미리 = false;
    try {
      const nw = img.naturalWidth, nh = img.naturalHeight;
      if (nw && nh) {
        const c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(box[2] * nw)); c.height = Math.max(1, Math.round(box[3] * nh));
        c.getContext('2d').drawImage(img, box[0] * nw, box[1] * nh, box[2] * nw, box[3] * nh, 0, 0, c.width, c.height);
        img.src = c.toDataURL('image/png'); 미리 = true;
      }
    } catch (e) { 미리 = false; }
    el.dataset.shownCrop = JSON.stringify(미리 ? 새크롭 : (보임 || []));
    풀기();
    bar.remove(); save(); renderPanel();
    toast('반영할 때 원본에서 이 부분만 다시 잘라 넣습니다');
  }, 'good'));
  row.appendChild(btn('전체 쓰기', () => {
    const sp = imgSpec(el); delete sp['크롭']; delete sp['자를곳']; imgSave(el, sp);
    state.ops.push({ action: '그림 자르기', to: '전체' });
    풀기();
    bar.remove(); save(); renderPanel();
    toast('반영하면 자르지 않은 전체 그림으로 돌아갑니다');
  }));
  row.appendChild(btn('취소', () => {
    풀기();
    bar.remove();
  }));
  bar.appendChild(row);
  document.body.insertBefore(bar, document.body.firstChild);
}

function imgSpec(el) {
  try { return JSON.parse(el.dataset.img || '{}'); } catch (e) { return {}; }
}
function imgSave(el, spec) {
  el.dataset.img = JSON.stringify(spec);
}

// ── 표: 점유 격자('26-09-29 표 재설계 P1, critic_impl #10) ──
// 병합 칸(colSpan·rowSpan)이 있으면 행마다 칸 수가 다르다. 예전 tableOf 는 행의 칸을 그대로 늘어놔
// 들쭉날쭉한 rows 를 돌려줬고, 다음 조립이 병합을 다시 걸면 덮인 자리에 진짜 값이 들어가 저장할
// 때마다 칸이 한 칸씩 밀렸다. 이제 점유 격자로 **직사각** rows 를 되살리고(덮인 칸은 ""), 병합·
// 강조는 저장 때마다 DOM 의 colSpan·rowSpan·data-강조 에서, 사람이 정한 열폭·열정렬은 <col data-*>
// 에서 되읽는다(좌표 목록을 따로 들고 있으면 행·열을 넣고 뺄 때 어긋난다).
function 칸글(td) {                          // <br> = 칸 안 줄바꿈(textContent 는 그것을 지운다)
  let s = '';
  const walk = n => { for (const c of n.childNodes) {
    if (c.nodeType === 3) s += c.nodeValue;
    else if (c.nodeType === 1) { if (c.tagName === 'BR') s += '\n'; else walk(c); } } };
  walk(td);
  return s.split('\n').map(x => x.trim()).join('\n').trim();
}
function 칸쓰기(td, s) {                     // 칸글 의 짝 — \n 은 <br> 로 되살린다(AI 다시쓰기가 칸 글을 되박을 때)
  td.textContent = '';
  String(s).split('\n').forEach((줄, k) => {
    if (k) td.appendChild(document.createElement('br'));
    td.appendChild(document.createTextNode(줄));
  });
}
function 표격자(tb) {
  const 판 = new Map(), 자리 = [], trs = [...tb.rows], n행 = trs.length;
  trs.forEach((tr, r) => { let c = 0;
    [...tr.cells].forEach(td => {
      while (판.has(r + ',' + c)) c++;
      const z = { td, tr, r, c, 가로: Math.max(1, td.colSpan || 1),
                  세로: Math.max(1, Math.min(td.rowSpan || 1, n행 - r)) };
      자리.push(z);
      for (let i = 0; i < z.세로; i++) for (let j = 0; j < z.가로; j++) 판.set((r + i) + ',' + (c + j), z);
      c += z.가로; }); });
  let n열 = 0; 자리.forEach(z => { n열 = Math.max(n열, z.c + z.가로); });
  const 머리 = trs.length > 0 && [...trs[0].cells].some(c => c.tagName === 'TH');
  return { n행, n열, 자리, 판, trs, 머리 };
}
function tableOf(el) {
  const tb = el.querySelector('table'); if (!tb) return null;
  const cap = el.querySelector('[class*="cap"]');   // 장르마다 클래스명이 다르다
  const g = 표격자(tb);
  const 칸 = Array.from({ length: g.n행 }, () => Array(g.n열).fill(''));
  const 병합 = [], 강조 = [];
  g.자리.forEach(z => {
    칸[z.r][z.c] = 칸글(z.td);
    if (z.가로 > 1 || z.세로 > 1) {
      const m = { '행': z.r, '열': z.c };
      if (z.가로 > 1) m['가로'] = z.가로;
      if (z.세로 > 1) m['세로'] = z.세로;
      병합.push(m);
    }
    const h = z.td.dataset.강조;
    if (h) 강조.push(h === '강조' ? { '행': z.r, '열': z.c } : { '행': z.r, '열': z.c, '색': h });
  });
  const out = { '캡션': cap ? cap.textContent.trim() : '',
    header: g.머리 ? (칸[0] || []) : [], rows: g.머리 ? 칸.slice(1) : 칸, 병합, 강조, _n행: g.n행, _n열: g.n열,
    _머리: g.머리 };
  // 표 크기(작게·크게, '26-09-29 편집기 막대) — 보통은 속성이 없다(build/표꼴.py 와 같은 규칙)
  if (tb.dataset.크기 === '작게' || tb.dataset.크기 === '크게') out['크기'] = tb.dataset.크기;
  const cols = [...tb.querySelectorAll(':scope > colgroup > col')];
  if (cols.length === g.n열) {
    const w = cols.map(c => (c.dataset.w ? +c.dataset.w : null));
    if (w.every(x => x)) out['열폭'] = w;
    const a = cols.map(c => c.dataset.a || '');
    if (a.some(x => x)) out['열정렬'] = a;
  }
  return out;
}
// 적힌 병합·강조가 지금 DOM 과 **같은 칸들**을 뜻하면 적힌 꼴을 그대로 둔다(열 단위 강조 {열: 3}
// 을 칸 목록으로 풀어 쓰지 않게 — 저장이 뜻 없는 차이를 만들지 않는다). build/표꼴.정규화 와 같은 규칙.
function 같은칸들(키, 적힌, t) {
  if (!Array.isArray(적힌)) return (t[키] || []).length === 0 && 적힌 === undefined;
  const 몸시작 = t._머리 ? 1 : 0, 쓴 = new Set(), 본 = new Set();
  if (키 === '병합') {
    적힌.forEach(m => { const 가 = +(m['가로'] || 1), 세 = +(m['세로'] || 1);
      if (가 > 1 || 세 > 1) 쓴.add([m['행'], m['열'], Math.min(가, t._n열 - m['열']), Math.min(세, t._n행 - m['행'])].join(',')); });
    (t['병합'] || []).forEach(m => 본.add([m['행'], m['열'], m['가로'] || 1, m['세로'] || 1].join(',')));
  } else {
    const 덮임 = new Set();
    (t['병합'] || []).forEach(m => { for (let i = 0; i < (m['세로'] || 1); i++) for (let j = 0; j < (m['가로'] || 1); j++)
      if (i || j) 덮임.add((m['행'] + i) + ',' + (m['열'] + j)); });
    적힌.forEach(h => { const 색 = h['색'] || '강조';
      const rs = h['행'] !== undefined && h['행'] !== null ? [h['행']] : [...Array(Math.max(0, t._n행 - 몸시작)).keys()].map(x => x + 몸시작);
      const cs = h['열'] !== undefined && h['열'] !== null ? [h['열']] : [...Array(t._n열).keys()];
      rs.forEach(r => cs.forEach(c => { if (!덮임.has(r + ',' + c)) 쓴.add(r + ',' + c + ',' + 색); })); });
    (t['강조'] || []).forEach(h => 본.add(h['행'] + ',' + h['열'] + ',' + (h['색'] || '강조')));
  }
  return 쓴.size === 본.size && [...쓴].every(x => 본.has(x));
}
// 지금 칸 — 표를 고친 뒤 칸 합치기·열 넣기가 이 칸을 기준으로 한다(누른 칸 또는 커서가 있는 칸)
function 표칸기억(n) {
  const e = n && (n.nodeType === 1 ? n : n.parentElement);
  const td = e && e.closest && e.closest('td,th');
  if (td && td.closest('[data-ent]') && !td.closest('.panel,.edit-bar')) state.표칸 = td;
}
document.addEventListener('click', e => 표칸기억(e.target), true);
document.addEventListener('selectionchange', () => { const s = getSelection(); if (s) 표칸기억(s.anchorNode); });
function 지금칸(el) {
  const td = state.표칸;
  return td && el.contains(td) && td.isConnected ? td : null;
}
function 표조작뒤(el, 이름) {
  state.ops.push({ action: 이름, target: '표' });
  repaginate(); save(); select(el);
}
function 새칸(태그, 글) { const x = document.createElement(태그); x.textContent = 글; return x; }
// 한 행(r)에 격자 열 c 자리에 새 칸을 끼운다 — 그 행에서 c 보다 오른쪽에서 시작하는 첫 칸 앞
function 칸끼우기(g, r, c, 칸) {
  const 뒤 = g.자리.find(z => z.r === r && z.c > c);
  if (뒤) g.trs[r].insertBefore(칸, 뒤.td); else g.trs[r].appendChild(칸);
}
function 열폭맞춤(tb) {                        // <col data-w> 원값 → 화면 폭(합 100 %)
  const cols = [...tb.querySelectorAll(':scope > colgroup > col')];
  const w = cols.map(c => +c.dataset.w || 0), 합 = w.reduce((a, b) => a + b, 0);
  if (합 > 0 && w.every(x => x)) cols.forEach((c, j) => { c.style.width = (w[j] * 100 / 합).toFixed(2) + '%'; });
}
function 열넣기(el) {
  const tb = el.querySelector('table'); const g = 표격자(tb);
  const td = 지금칸(el); const z0 = td ? g.자리.find(z => z.td === td) : null;
  const c = z0 ? z0.c + z0.가로 - 1 : g.n열 - 1;      // 이 열 오른쪽에 넣는다
  const 늘림 = new Set();
  for (let r = 0; r < g.n행; r++) {
    const z = g.판.get(r + ',' + c), 옆 = g.판.get(r + ',' + (c + 1));
    if (z && 옆 && z === 옆) {                      // 병합 칸 안쪽 경계 — 그 칸을 한 칸 넓힌다
      if (!늘림.has(z)) { z.td.colSpan = z.가로 + 1; 늘림.add(z); }
      continue;
    }
    칸끼우기(g, r, c, 새칸(r === 0 && g.머리 ? 'th' : 'td', '—'));
  }
  const cols = [...tb.querySelectorAll(':scope > colgroup > col')];
  if (cols.length === g.n열) {
    const 새 = document.createElement('col'), 앞 = cols[c];
    if (앞.dataset.w) { const 반 = Math.round(+앞.dataset.w / 2 * 100) / 100; 앞.dataset.w = 반; 새.dataset.w = 반; }
    앞.after(새); 열폭맞춤(tb);
  }
  표조작뒤(el, '표 열 추가');
}
function 열빼기(el) {
  const tb = el.querySelector('table'); const g = 표격자(tb);
  if (g.n열 <= 2) { toast('열이 둘 남으면 더 뺄 수 없습니다'); return; }
  const td = 지금칸(el); const z0 = td ? g.자리.find(z => z.td === td) : null;
  const c = z0 ? z0.c : g.n열 - 1;
  const 본 = new Set();
  for (let r = 0; r < g.n행; r++) {
    const z = g.판.get(r + ',' + c); if (!z || 본.has(z)) continue; 본.add(z);
    if (z.가로 > 1) z.td.colSpan = z.가로 - 1; else z.td.remove();
  }
  const cols = [...tb.querySelectorAll(':scope > colgroup > col')];
  if (cols.length === g.n열) {
    // 뺀 열의 폭은 이웃(왼쪽, 없으면 오른쪽)에 돌려준다 — 넣을 때 반으로 나눈 폭을 안 돌려줘 열을 넣었다 빼면
    // 첫 열이 24% → 약 13.6% 로 줄었다(적대 검토 M8 '26-09-29)
    const 이웃 = cols[c - 1] || cols[c + 1];
    if (이웃 && 이웃.dataset.w && cols[c].dataset.w)
      이웃.dataset.w = Math.round((+이웃.dataset.w + +cols[c].dataset.w) * 100) / 100;
    cols[c].remove(); 열폭맞춤(tb);
  }
  if (state.표칸 && !state.표칸.isConnected) state.표칸 = null;
  표조작뒤(el, '표 열 삭제');
}
function 칸합치기(el, 쪽) {
  const tb = el.querySelector('table'); const g = 표격자(tb);
  const td = 지금칸(el); const z = td ? g.자리.find(x => x.td === td) : null;
  if (!z) { toast('합칠 칸을 먼저 누르세요'); return; }
  const 남 = 쪽 === '오른쪽' ? g.판.get(z.r + ',' + (z.c + z.가로)) : g.판.get((z.r + z.세로) + ',' + z.c);
  const 맞음 = 남 && (쪽 === '오른쪽' ? (남.r === z.r && 남.c === z.c + z.가로 && 남.세로 === z.세로)
                                      : (남.c === z.c && 남.r === z.r + z.세로 && 남.가로 === z.가로));
  if (!맞음 || (쪽 === '아래' && g.머리 && z.r === 0)) {
    toast(쪽 === '아래' && g.머리 && z.r === 0 ? '머리 칸은 아래 칸과 합칠 수 없습니다'
      : '크기가 맞는 옆 칸이 없어 합칠 수 없습니다'); return; }
  const 글 = [칸글(z.td), 칸글(남.td)].filter(Boolean).join(' ');
  z.td.textContent = 글;
  if (쪽 === '오른쪽') z.td.colSpan = z.가로 + 남.가로; else z.td.rowSpan = z.세로 + 남.세로;
  남.td.remove();
  표조작뒤(el, '칸 합치기');
}
function 칸나누기(el) {
  const tb = el.querySelector('table'); const g = 표격자(tb);
  const td = 지금칸(el); const z = td ? g.자리.find(x => x.td === td) : null;
  if (!z || (z.가로 === 1 && z.세로 === 1)) { toast('합친 칸을 먼저 누르세요'); return; }
  for (let i = 0; i < z.세로; i++) {
    const r = z.r + i;
    const 뒤 = g.자리.find(x => x.r === r && x.c > z.c + z.가로 - 1);
    for (let j = 0; j < z.가로; j++) {
      if (!i && !j) continue;
      const 새 = 새칸(r === 0 && g.머리 ? 'th' : 'td', '');
      if (뒤) g.trs[r].insertBefore(새, 뒤.td); else g.trs[r].appendChild(새);
    }
  }
  z.td.colSpan = 1; z.td.rowSpan = 1;
  표조작뒤(el, '칸 나누기');
}
function 칸강조(el) {
  const td = 지금칸(el);
  if (!td || td.tagName === 'TH') { toast('강조할 칸을 먼저 누르세요 — 머리 칸은 강조하지 않습니다'); return; }
  if (td.dataset.강조) delete td.dataset.강조; else td.dataset.강조 = '강조';
  표조작뒤(el, '칸 강조');
}
function serialize() {
  if (typeof v2직렬화 === 'function') return v2직렬화();   // 판형 v2 슬라이드(workspace/editor_v2.py 가 끼운다)
  const doc = JSON.parse(JSON.stringify(SRCDOC));      // 원본 신뢰 — 화면에 없는 것도 보존
  // ① 경로가 있는 노드의 현재 텍스트를 모델에 되쓴다
  //    같은 경로가 여러 조각으로 흩어져 있을 수 있다(자간 조정이 span 을 쪼갠다).
  경로조각().forEach(([path, els]) => {
    const el = els[0];
    if (el.classList.contains('fr-box')) {
      const b = boxOf(el);
      // 장 핵심박스는 문자열 배열(경로가 …핵심박스) — 항목만 넣는다
      setPath(doc, path, path.endsWith('핵심박스') ? b['항목'] : b);
      return;
    }
    // 그림이 먼저다 — .fr-img 도 .fr-fig 클래스를 함께 갖고 있어 순서가 뒤바뀌면
    // 도식 처리로 새어 스펙이 통째로 날아간다.
    if (el.classList.contains('fr-img')) { setPath(doc, path, imgSpec(el)); return; }
    if (el.classList.contains('fr-fig')) { setPath(doc, path, syncFigSpec(el)); return; }
    // 표를 감싼 컨테이너 — 장르마다 클래스명이 달라(fr-/doc-/gm-) 하나라도 빠지면
// 표 객체가 통째로 문자열로 덮어써진다. 클래스 대신 '표가 들어 있는가'로 판정한다.
    if (el.querySelector('table')) {
      const t = tableOf(el);
      if (t) {
        const prev = getPath(doc, path);
        // 원본의 스키마(1p는 after_heading·caption, 풀버전은 캡션)를 지키며 값만 갱신
        if (prev && typeof prev === 'object' && !Array.isArray(prev)) {
          const merged = Object.assign({}, prev);
          if ('캡션' in prev) merged['캡션'] = t['캡션']; else if ('caption' in prev) merged.caption = t['캡션'];
          else if ('제목' in prev) merged['제목'] = t['캡션'];   // 보도자료 개요표는 표 제목 키가 '제목'
          merged.header = t.header; merged.rows = t.rows;
          // 병합·강조는 DOM 에서 매번 되읽는다('26-09-29 표 재설계 P1) — 적힌 꼴이 같은 칸들이면 둔다
          for (const k of ['병합', '강조']) {
            if (같은칸들(k, prev[k], t)) continue;
            if (t[k].length) merged[k] = t[k]; else delete merged[k];
          }
          for (const k of ['열폭', '열정렬']) { if (t[k]) merged[k] = t[k]; else delete merged[k]; }
          if (t['크기']) merged['크기'] = t['크기'];
          else if (merged['크기'] !== '보통') delete merged['크기'];   // 적힌 '보통'은 둔다(기본값 — 왕복 불변)
          if (el.dataset.표모양 !== undefined) {                 // 표 모양(프리셋)을 이 화면에서 바꿨다
            if (el.dataset.표모양) merged.style = el.dataset.표모양; else delete merged.style;
          }
          setPath(doc, path, merged);
        } else {
          const t2 = { '캡션': t['캡션'], header: t.header, rows: t.rows };
          for (const k of ['병합', '강조']) if (t[k].length) t2[k] = t[k];
          for (const k of ['열폭', '열정렬', '크기']) if (t[k]) t2[k] = t[k];
          setPath(doc, path, t2);
        }
      }
      return;
    }
    if (el.dataset.arr) return;                         // 시퀀스는 ①-b가 통째로 처리
    if (el.classList.contains('doc-attach')) {
      const c = 이어붙임(els).cloneNode(true);
      c.querySelectorAll('span.jachigan-run').forEach(x => x.replaceWith(...x.childNodes));
      c.querySelectorAll('.label').forEach(x => x.remove());     // '붙임' 라벨은 조립기가 붙인다
      let t = c.textContent.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
      t = t.replace(/\s*끝\s*\.?\s*$/, '').trim();             // 끝 표시도 조립기 몫
      t = t.replace(/\.$/, '').trim();                        // 수량 뒤 마침표도 조립기 몫
      const had = getPath(doc, path);
      // 조립기가 수량 뒤 마침표를 보장하므로, 마침표만 다르면 '안 고친 것'이다
      const bare = x => String(x).replace(/\.$/, '').trim();
      if (typeof had === 'string' && bare(had) === bare(t)) return;
      if (t || (had !== undefined && had !== null)) setPath(doc, path, t);
      return;
    }
    if (path.endsWith('.html')) {
      // 1p 본문 — 강조 span(num/accent/delta)을 살려 마크업 그대로 저장
      const c = 이어붙임(els).cloneNode(true);
      c.querySelectorAll('span.jachigan-run').forEach(x => x.replaceWith(...x.childNodes));
      c.normalize();
      setPath(doc, path, c.innerHTML.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim());
      return;
    }
    if (el.dataset.orig !== undefined) {
      // 화면에는 사람말로 다듬어 보여준 값 — 사용자가 고치지 않았으면 원본을 그대로 둔다
      const now = textOf(이어붙임(els));
      setPath(doc, path, now === (el.dataset.shown || '') ? el.dataset.orig : now);
      return;
    }
    if (el.classList.contains('fr-sum-block')) return;   // 컨테이너
    if (el.closest('.fr-box')) return;                  // 박스 내부는 boxOf가 통째로 처리
    if (el.closest('.fr-fig')) return;                  // 도식 내부는 syncFigSpec이 처리
    // 픽토그램 — 나열(sl-pictos)은 배열 경로, 카드(sl-picto)는 배열 원소 경로를 달고 있어
    // 폴백 텍스트로 새면 배열/객체{아이콘·라벨·설명}가 통째로 문자열로 덮여 왕복이 깨진다
    // (도식·이미지가 전용 처리로 피하는 것과 같은 함정). 아이콘은 화면에 SVG 만 있고
    // 이름이 없으므로 data-icon 로 보존하고, 라벨·설명은 안쪽 .tx 하위 경로가 패치한다.
    if (el.classList.contains('sl-pictos')) return;      // 나열 컨테이너 — 손대지 않는다(원소 경로가 처리)
    if (el.classList.contains('sl-picto')) {             // 카드 — 아이콘만 data-icon 로 되쓰고 라벨·설명은 하위 경로에 맡긴다
      if (el.dataset.icon != null && el.dataset.icon !== '') setPath(doc, path + '.아이콘', el.dataset.icon);
      return;
    }
    setPath(doc, path, textOf(이어붙임(els)));
  });
  // ①-b data-arr 로 표시된 시퀀스는 DOM 순서로 통째 재구성한다
  //     (순서 이동·추가·삭제가 한 번에 반영된다 — 경로 인덱스에 기대지 않는다)
  const seqGroups = {};
  document.querySelectorAll('[data-arr]').forEach(el => {
    const base = (el.dataset.path || el.dataset.parent || '').replace(/\.\d+$/, '');
    if (!base) return;
    (seqGroups[base] = seqGroups[base] || []).push(el);
  });
  Object.entries(seqGroups).forEach(([base, els]) => {
    setPath(doc, base, els.map(x => {
      const txs = [...x.querySelectorAll('.tx')];
      return textOf(txs.length ? 이어붙임(txs) : x);
    }));
  });
  // ①-c 포함/제외 플래그
  document.querySelectorAll('[data-flag]').forEach(el => {
    setPath(doc, el.dataset.flag, el.dataset.on !== 'false');
  });
  // ①-d 값 순환(등장요소 가능성 등)
  document.querySelectorAll('[data-cycle]').forEach(el => {
    if (el.dataset.lv) setPath(doc, el.dataset.cycle, el.dataset.lv);
  });
  // ② 화면에서 사라진 경로는 모델에서도 지운다(삭제 반영) — 배열은 뒤에서부터
  const alive = new Set([...document.querySelectorAll('[data-path]')].map(x => x.dataset.path));
  const anyAlive = base => [...alive].some(p => p.startsWith(base + '.'));
  // 부모가 화면에 있으면, 자식이 **다 지워져 비어도** 정리한다.
  // `anyAlive` 만 보면 '마지막 하나를 지운 절' 이 "화면에 없는 영역" 으로 오인돼
  // 지운 것이 되살아난다(2026-08-06 실측: 절은 살아 있는데 items 가 0 이 되자 그랬다).
  const 부모가_살아있나 = base => {
    const i = base.lastIndexOf('.');
    if (i < 0) return true;                   // 최상위 배열(별첨 등)은 문서에 늘 있다
    const 부모 = base.slice(0, i);            // sections.3.items → sections.3
    return alive.has(부모) || [...alive].some(p => p.startsWith(부모 + '.'));
  };
  function prune(arr, base) {
    // 이 영역이 화면에 아예 없으면(gov 의 요약처럼 장르가 안 그리는 곳) 손대지 않는다
    if (!anyAlive(base) && !부모가_살아있나(base)) return;
    for (let i = arr.length - 1; i >= 0; i--) {
      // **열쇠를 하나로 고정하지 않는다.** 같은 배열 안에서도 마디마다 열쇠가 다르다 —
      // 규정 본문은 장·조가 `제목`, 항·호·목은 `text` 다. 열쇠 하나만 보면
      // 다른 열쇠를 쓴 마디를 '지워진 것' 으로 오인해 통째로 날린다
      // (2026-08-06: 이 실수로 규정·시행문·보도자료의 왕복이 깨졌다).
      const 앞 = `${base}.${i}`;
      const 살았나 = alive.has(앞) ||
        [...alive].some(p => p === 앞 || p.startsWith(앞 + '.'));
      if (!살았나) arr.splice(i, 1);
    }
  }
  // **배열 경로를 손으로 적지 않는다.** 화면에 있는 data-path 에서 배열 자리를
  // 세어 낸다 — 전에는 풀버전 경로(장·절·별첨·요약)만 적혀 있어서
  // 1p 의 `sections.N.items` 와 시행문·규정·보도자료의 `본문.N` 은 **아예 안 돌았다.**
  // 그래서 그 네 장르에서 **삭제가 정본에 닿지 않았다**(2026-08-06 B-1 시험에서 걸림).
  // 화면에서 지웠는데 저장하면 되살아났고, 아무 신호도 없었다.
  const 배열자리 = new Map();          // '경로.접두' → 열쇠(마지막 조각) 또는 null
  alive.forEach(p => {
    const 조각 = p.split('.');
    for (let i = 조각.length - 1; i >= 1; i--) {
      if (!/^\d+$/.test(조각[i])) continue;
      const base = 조각.slice(0, i).join('.');
      const key = 조각.slice(i + 1).join('.') || null;
      if (!배열자리.has(base)) 배열자리.set(base, key);
    }
  });
  // 화면에서 **통째로 비어 버린 배열**은 위 수집에 안 잡힌다(살아 있는 경로가 없으니).
  // 같은 꼴의 형제 경로에서 이름을 빌려 와 채운다 — sections.0.items 가 있으면
  // sections.3.items 도 봐야 한다.
  [...배열자리.keys()].forEach(base => {
    const m = base.match(/^(.*)\.(\d+)\.(.+)$/);
    if (!m) return;
    const [, 뿌리, , 끝] = m;
    const 형제 = getPath(doc, 뿌리);
    if (!Array.isArray(형제)) return;
    형제.forEach((_, i) => {
      const b = `${뿌리}.${i}.${끝}`;
      if (!배열자리.has(b)) 배열자리.set(b, 배열자리.get(base));
    });
  });
  배열자리.forEach((key, base) => {
    const arr = getPath(doc, base);
    if (Array.isArray(arr)) prune(arr, base);
  });
  // ②-b 최상위 선택키(개요표·주요내용·부칙·붙임·부제·별표 …) — 위 배열자리 는 살아 있는
  //     항목이 하나라도 있어야 그 배열/자리를 찾는다. **마지막 항목까지 지우면**(개요표
  //     처럼 배열이 아닌 통짜 값도 마찬가지) 살아 있는 data-path 가 하나도 안 남아 이
  //     자리 자체가 안 보이므로, 지운 것이 저장할 때마다 되살아났다(assemble:F7·F8c,
  //     '26-09-27). 'del' 액션이 있는 개체 이름 가운데, 그 이름과 같은 최상위 키가
  //     doc 에 실제로 있는 것만 대상으로 삼는다 — 표·박스·항목처럼 같은 이름을 배열
  //     원소마다 재사용하는 개체는 그런 top-level 키가 애초에 없어 자연히 안 걸린다.
  //
  //     '화면이 그렸는가'를 **data-path 유무로 추정하지 않는다.** 시행문 붙임(gm-attach)은
  //     data-ent="붙임"만 달고 data-path 를 아예 안 그리고, 정본 밖 모양의 부칙({제목,text}
  //     처럼 호·일자·본문 키가 없는 부칙)도 <h2 data-ent="부칙">부칙</h2> 뿐 data-path 가
  //     없다. 이런 요소를 data-path 로만 재면 손을 안 댔는데도 매번 '지워졌다'로 오판해
  //     저장할 때마다 정본 값을 비웠다(asm:F1, '26-09-27 회귀). **그 개체를 그리는 요소
  //     자신(data-ent=name)이 지금도 DOM에 있는가**로 재면, 사용자가 실제로 지운 경우
  //     (delEl 이 host.remove() 로 그 요소를 뽑아낸 경우)만 걸리고, 화면에 그대로 남아
  //     있는데 안쪽에 data-path 가 없을 뿐인 경우는 건드리지 않는다.
  Object.entries(ENTS).forEach(([name, spec]) => {
    if (!spec || !Array.isArray(spec['액션']) || !spec['액션'].includes('del')) return;
    if (!(name in doc)) return;
    const v = doc[name];
    const isArr = Array.isArray(v);
    const empty = isArr ? v.length === 0 : (v == null || v === ''
      || (typeof v === 'object' && Object.keys(v).length === 0));
    if (empty) return;                                   // 이미 비었다 — 더 지울 것 없다
    const stillDrawn = !!document.querySelector('[data-ent="' + name + '"]');
    if (!stillDrawn) { if (isArr) doc[name] = []; else delete doc[name]; }
  });
  // ②-c 배열도 top-level 키도 아닌 자리(풀버전 절.표, 슬라이드 출처, 1p 붙임·표 등) —
  //     ②-b 는 '개체 이름 == 최상위 키'일 때만 보고, 위 prune 은 배열 원소만 본다.
  //     둘 사이에 낀 자리(부모는 배열 원소 자체가 아니라 그 원소 **안의 필드 하나**)는
  //     어느 쪽도 못 봐서 화면에서 지워도 저장·재조립·내보내기에서 되살아났다(asm:R7-02).
  //     처음 그렸을 때 있었는데(원본경로) 지금은 없고(!alive) **바로 한 단계 위(그 자리가
  //     속한 배열 원소 자신)는 아직 살아 있는** 경우만 그 필드를 지운다. 한 단계 위까지
  //     같이 죽었으면 그 원소 자체가 사라진 것이니 이미 위 prune()이 통째로 지운다 —
  //     거기 또 손대면(마침 그 인덱스에 다른 원소가 들어온 뒤라면) 엉뚱한 원소를 지울
  //     위험이 있어 **한 단계 위가 살아 있을 때만** 손댄다.
  원본경로.forEach(p => {
    if (alive.has(p)) return;                              // 아직 살아 있다 — 안 지워짐
    const i = p.lastIndexOf('.');
    const 부모길 = i < 0 ? '' : p.slice(0, i);
    const 부모살았나 = i < 0 ? true                          // top-level 단일 키(1p attach·table)
      : (alive.has(부모길) || [...alive].some(q => q.startsWith(부모길 + '.')));
    if (!부모살았나) return;                                // 배열 원소 자체가 사라짐 — prune 몫
    const 부모 = i < 0 ? doc : getPath(doc, 부모길);
    if (!부모 || typeof 부모 !== 'object' || Array.isArray(부모)) return;
    const 키 = i < 0 ? p : p.slice(i + 1);
    const cur = 부모[키];
    if (cur === undefined) return;                          // 이미 없다
    if (typeof cur === 'string') 부모[키] = '';               // 문자열 자리는 빈 문자열로(직접수정 지우기와 같은 표기)
    else delete 부모[키];                                     // 표·객체 자리는 키째 지운다
  });
  // ③ 새로 추가된 블록(경로 없음)을 소속 배열 끝에 얹는다
  document.querySelectorAll('[data-new]:not([data-arr])').forEach(el => {
    const parent = el.dataset.parent; if (!parent) return;
    let arr = getPath(doc, parent);
    // **없으면 만든다.** 문서에 아직 그 배열이 없으면(박스를 처음 넣는 절 등)
    // 여기서 조용히 되돌아가 새로 만든 것이 통째로 사라졌다
    // (2026-08-06: addBox 로 만든 박스가 저장에 한 번도 안 실렸다).
    if (!Array.isArray(arr)) {
      const i = parent.lastIndexOf('.');
      const 뿌리 = i < 0 ? null : getPath(doc, parent.slice(0, i));
      if (!뿌리 || typeof 뿌리 !== 'object') return;
      arr = []; 뿌리[parent.slice(i + 1)] = arr;
    }
    if (el.classList.contains('fr-box')) arr.push(boxOf(el));
    // 그림이 먼저다 — .fr-img 도 .fr-fig 클래스를 함께 갖고 있어(①의 1137행과 같은 함정),
    // 순서가 뒤바뀌면 새 그림이 도식 스펙(figSpec)으로 잘못 저장된다.
    else if (el.classList.contains('fr-img')) arr.push(imgSpec(el));
    else if (el.classList.contains('fr-fig')) arr.push(figSpec(el));
    // 그 밖(항목·픽토그램 등)은 장르마다 원소 모양이 달라 새항목값()이 판정한다
    // (1p={level,html}, 규정={level:<장절조항호목>,제목|text}, 픽토그램={아이콘,라벨,설명},
    // 그 밖 항목류={level,text}) — 예전엔 '항목'으로 끝나는 배열만 {level,text}로 넣고
    // 나머지(1p items·규정 본문·슬라이드 픽토그램)는 문자열로 뭉개, 재조립 때 크래시하거나
    // (규정 level 검증 실패로) 항목이 조용히 사라졌다(asm:R7-01).
    else arr.push(새항목값(el, parent));
  });
  // ④ 항목 레벨 변경 반영
  document.querySelectorAll('.blk[data-path$=".text"]').forEach(el => {
    if (!LVORDER.some(c => el.classList.contains(c))) return;
    const lv = el.classList.contains('i-l4') ? 4 : el.classList.contains('i-l3') ? 3 : 2;
    const base = el.dataset.path.replace(/\.text$/, '');
    const it = getPath(doc, base);
    if (it && typeof it === 'object') it.level = lv;
  });
  // ④-b 끝 표시 옵션
  if (state.endmark !== undefined) doc.show_end_mark = state.endmark;
  if (state.끝표시 !== undefined) doc['끝표시'] = state.끝표시;
  // ⑤ 스타일(대기 반영)
  const styleNow = document.documentElement.dataset.style === 'gov' ? '정부부처형' : null;
  const styleWant = state.pendingStyle || styleNow;
  if (styleWant === '정부부처형') {
    doc['스타일'] = '정부부처형';
    const pt = getComputedStyle(document.documentElement).getPropertyValue('--pt').trim();
    if (pt) doc['포인트색'] = pt;
  } else delete doc['스타일'];
  // 글꼴·포인트색은 화면 토글이 아니라 문서의 선택이다. 안 남기면 다시 만들 때
  // 원복돼 "바꿨다"는 기록만 남고 결과가 안 남는다 — 이력이 거짓말하게 된다.
  // 다만 고른 적 없는 문서에 키를 만들면 안 고쳤는데 바뀐 것이 되므로 고른 것만 쓴다.
  if (state.글꼴) doc['글꼴'] = state.글꼴;
  if (state.포인트색) doc['포인트색'] = state.포인트색;
  if (state.팔레트) doc['팔레트'] = state.팔레트;       // 도식·차트 팔레트(이름만 — 색은 조립기가 계산)
  // ⑥ 2단 마커 — 글꼴과 같은 이치다. 기본값(○)이면 키를 안 남긴다(왕복 불변식).
  const mk2 = document.documentElement.dataset.mk2;
  if (mk2) doc['2단마커'] = mk2; else delete doc['2단마커'];
  // ⑥-b 제목 모양(1p·풀버전) — 누르면 바로 <html> 에 걸리므로 화면의 data 속성이 정본이다.
  //     없으면(기본) 키를 지운다(왕복 불변식). 밑줄 없는 키라 저장 diff 가 변화로 센다.
  if (모양있음) 모양키.forEach(k => {
    const v = document.documentElement.getAttribute('data-' + k);
    if (v) doc[k] = v; else delete doc[k];
  });
  // ⑥-c 보도자료 본문꼴 — 구조가 바뀌어 다시 만들 때 반영된다(스타일과 같은 성격). 기본(개조식)이면 키를 지운다.
  if (state.본문꼴 !== undefined) {
    const 기본꼴 = ((상단칸['본문꼴'] || [])[0] || [])[0];
    if (state.본문꼴 && state.본문꼴 !== 기본꼴) doc['본문꼴'] = state.본문꼴; else delete doc['본문꼴'];
  }
  // ⑦ 슬라이드 디자인 영역 — 테마·효과·화면(문서 단위). 기본값이면 키를 안 남긴다(왕복 불변식).
  if (state.테마 !== undefined) { if (state.테마 && state.테마 !== '네이비') doc['테마'] = state.테마; else delete doc['테마']; }
  if (state.효과 !== undefined) { if (state.효과 && state.효과 !== '페이드') doc['효과'] = state.효과; else delete doc['효과']; }
  if (state.화면 !== undefined) doc['화면'] = state.화면;
  // ⑦-b 정렬 오버레이 — 경로별 정렬(state.정렬). 비면 키를 안 남긴다(왕복 불변식).
  if (state.정렬 !== undefined) { if (Object.keys(state.정렬).length) doc['_정렬'] = state.정렬; else delete doc['_정렬']; }
  // ⑧ 슬라이드 자유배치 — 각 슬라이드의 배치모드(자유 여부)와 개체 절대좌표(배치)를 되쓴다.
  //    좌표는 sl-placed 의 inline %(left/top/width/height)를 읽는다. 흐름이면 배치모드·배치를
  //    지운다(기본값 불변식). 슬라이드 아닌 장르엔 .sl-page[data-slide-idx]가 없어 무해하다.
  document.querySelectorAll('.sl-page[data-slide-idx]').forEach(sec => {
    const i = sec.dataset.slideIdx;
    const s = (doc['슬라이드'] || [])[i];
    if (!s || typeof s !== 'object') return;
    if (sec.classList.contains('sl-free')) {
      s['배치모드'] = '자유';
      const b = {};
      sec.querySelectorAll('[data-배치경로]').forEach(el => {
        const role = el.dataset['배치경로'].split('.').pop();
        const st = el.style, num = k => parseFloat(st[k]) || 0;   // 화면 값 그대로(반올림은 드래그가 함)
        b[role] = { x: num('left'), y: num('top'), w: num('width'), h: num('height') };
      });
      s['배치'] = b;
    } else { delete s['배치모드']; delete s['배치']; }
  });
  // ops 는 **지난 저장 뒤의 조작만** 싣는다(2단계 UI 검토 F5) — state.ops 는 패널의
  // '이번에 고친 것' 목록으로 계속 두되, 서버 이력(고친 내역)에는 한 번만 간다. 예전엔
  // 글만 고친 저장에도 앞서 바꾼 '제목 모양 3번 · 되돌림 2번'이 매번 다시 붙었다.
  return { doc, instructions: state.notes, ops: state.ops.filter(o => !보낸op().has(o)),
           보관요청: state.보관요청 || null };
}
// 저장에 실려 서버가 받은 조작(객체 그대로)과 되돌림 지점 요청 — 성공 응답 뒤 다시 안 보낸다.
// 지점 요청을 안 비우면 저장할 때마다 같은 이름의 지점이 또 생겼다(F9).
// (함수 선언이라 끌어올려진다 — serialize 가 이 줄보다 먼저 불려도 안전하다)
function 보낸op() { return 보낸op.s || (보낸op.s = new WeakSet()); }
function 저장뒤비우기(snap) {
  (snap.ops || []).forEach(o => { if (o && typeof o === 'object') 보낸op().add(o); });
  if (typeof 모양기록_저장뒤 === 'function') 모양기록_저장뒤(snap);   // 다른 편집이 저장되면 모양 기록을 비운다(F4)
  if (typeof 크기기록_저장뒤 === 'function') 크기기록_저장뒤(snap);   // 도식·표 크기 되돌리기도 같은 규칙(editor_bar.py)
  if (typeof 팔레트기록_저장뒤 === 'function') 팔레트기록_저장뒤(snap); // 도식·차트 색 되돌리기도 같은 규칙
  const 지점 = snap.보관요청;
  if (지점 && state.보관요청 === 지점) state.보관요청 = null;
  if (최근스냅 && 최근스냅 !== snap) {     // 그 사이 직렬화된 다음 저장에도 같은 것이 실려 있다
    최근스냅.ops = (최근스냅.ops || []).filter(o => !보낸op().has(o));
    if (지점 && 최근스냅.보관요청 === 지점) 최근스냅.보관요청 = null;
  } else {
    // 마지막 화면까지 문서에 반영됐다 — 버퍼는 할 일을 다 했다. 안 지우면 잘 저장하고 닫아도
    // 다시 열 때마다 '고치시던 내용이 남아 있습니다'가 떴다(2단계 UI 검토 F11).
    try { localStorage.removeItem(KEY); } catch (e) {}
  }
}
let sT;
// 저장은 두 겹이다.
//   ① 화면(localStorage) — 400ms 마다. 창이 닫혀도 안 잃는다. 서버가 없어도 된다.
//   ② 문서(서버 POST /save) — 1.5초 동안 손을 멈추면. 정본 반영·이력·재조립까지 간다.
// 예전에는 ①만 하고 사람이 채팅에 "다 고쳤어요"라고 말해야 ②가 됐다. 그러면
// 저장했는데 반영 안 된 상태가 생기고, Claude 가 브라우저를 읽을 수 있어야만 돌았다.
let sT2, 보내는중 = false;
// 최근스냅 — 마지막으로 직렬화한 화면(메모리 사본). 브라우저 저장(localStorage)이 막혀도
// (사생활 모드·사이트 데이터 차단 — 2단계 UI 검토 F6) 문서 반영은 이 사본으로 이어진다.
// 예전엔 버퍼 쓰기가 성공해야 보내기()를 불렀고 보내기()도 버퍼에서 다시 읽어, 저장이
// 막힌 브라우저에서는 등록부가 끝까지 안 바뀌었다.
let 최근스냅 = null;
function 버퍼쓰기(snap) { try { localStorage.setItem(KEY, JSON.stringify(snap)); return true; } catch (e) { return false; } }
function save() { clearTimeout(sT); sT = setTimeout(() => {
  let snap;
  try { snap = serialize(); }
  catch (e) { st.textContent = 채팅표면
      ? '저장하지 못했습니다 — 창을 닫지 말고 채팅으로 알려 주세요'
      : '저장하지 못했습니다 — 새로고침한 뒤 다시 시도해 주세요'; return; }
  snap._저장때 = new Date().toLocaleString('ko-KR',
    { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  최근스냅 = snap;
  const 버퍼됨 = 버퍼쓰기(snap);
  st.classList.add('on');
  if (!버퍼됨 && 채팅표면) {       // 서버도 버퍼도 없다 — 남길 곳이 채팅뿐이다
    st.textContent = '저장하지 못했습니다 — 창을 닫지 말고 채팅으로 알려 주세요'; return; }
  st.textContent = 버퍼됨 ? '화면에 저장했습니다 — 문서에 반영하는 중…' : '문서에 반영하는 중…';
  보내기();
}, 400); }

// 마지막으로 보낸(또는 연) 문서 — 고친 것이 없는 저장을 거른다(M6). var 인 까닭: 함수 선언보다 먼저 불려도 TDZ 가 없게
var 보낸기준 = { doc: SRCDOC };
function 같은문서(a, b) {
  const 편 = x => {
    if (Array.isArray(x)) return x.map(편);
    if (x && typeof x === 'object') {
      const o = {};
      Object.keys(x).sort().forEach(k => {
        if (k === '_수정시각' || k === '_저장때' || x[k] === '' || x[k] === undefined) return;   // 빈 글 키 = 없는 키
        o[k] = 편(x[k]);
      });
      return o;
    }
    return x;
  };
  try { return JSON.stringify(편(a)) === JSON.stringify(편(b)); } catch (e) { return false; }
}
function 보내기() { clearTimeout(sT2); sT2 = setTimeout(async () => {
  if (보내는중) { 보내기(); return; }          // 앞 요청이 끝난 뒤에 다시
  보내는중 = true;
  try {
    let snap = 최근스냅;
    if (!snap) { try { snap = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { snap = {}; } }
    if (!snap.doc) { 보내는중 = false; return; }
    // 고친 것이 없으면 보내지 않는다 — 편집기는 뜰 때 조판(repaginate)이 save 를 부르는데, 그 직렬화가 스펙에
    // 없던 빈 키(수렴 '시행', 표지 '부제')를 채워 **열기만 해도** 판 1개와 '손질 2군데'(고친 내역 빈 글)가
    // 생겼다(적대 검토 M6 '26-09-29). 빈 글 키는 없는 키와 같게 보고 마지막으로 보낸 문서와 대 본다.
    if (!(snap.ops || []).length && !snap.보관요청 && !Object.keys(snap.instructions || {}).length
        && 같은문서(snap.doc, 보낸기준.doc)) {
      st.classList.remove('on'); st.textContent = ''; 보내는중 = false; return;
    }
    // 자기 탭의 순차 저장 경합 방지 — 연달아 고치면(예: 개체 여럿을 빠르게 AI 재작성) 뒤 저장이
    // **직렬화 시점에 얼어붙은 옛 _수정시각**을 실어, 앞 저장 응답이 갱신한 최신 시각과 어긋나
    // 낙관적 잠금 400('문서에 반영하지 못했습니다')으로 편집이 유실됐다. 전송은 보내는중 가드로
    // 이미 직렬(앞 응답이 SRCDOC._수정시각 을 갱신한 뒤에 다음이 나감)이므로, **전송 시점의**
    // 최신 확인 시각으로 다시 찍는다. 타 편집자 감지는 유지된다(SRCDOC._수정시각 은 내 저장
    // 성공 응답으로만 갱신되므로, 남이 정본을 바꾸면 그 값과 어긋나 여전히 잠금에 걸린다).
    if (SRCDOC && SRCDOC._수정시각) { snap.doc._수정시각 = SRCDOC._수정시각;
      if (snap === 최근스냅) 버퍼쓰기(snap); }
    // WP-S10 2차-B — 문체 진단은 반영(/save)과 **따로** 흐른다(await 안 한다). 카드를
    // 띄우는 일이 반영을 늦추거나, 반영 실패가 진단을 막으면 안 된다 — 둘은 별개 관심사다.
    문체동의진단(snap.doc);
    const r = await fetch('/save', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(snap) });
    const j = await r.json();
    if (j.ok) {
      // **정본의 새 수정시각을 받아 원본에 반영한다.** 안 받으면 다음 저장 때
      // 낙관적 잠금이 "그 사이 바뀌었다"며 거부한다 — 바꾼 게 우리인데도.
      if (j.수정시각) { SRCDOC._수정시각 = j.수정시각; snap.doc._수정시각 = j.수정시각;
                     if (snap === 최근스냅) 버퍼쓰기(snap); }
      저장뒤비우기(snap);   // 이번 저장에 실린 조작·지점 요청은 한 번만 이력에 싣는다(F5·F9)
      보낸기준.doc = snap.doc;   // 다음 저장은 이 문서와 대 본다(고친 것 없으면 안 보낸다, M6)
      const 몇 = (j.로그.match(/바뀐 곳 (\d+)군데/) || [])[1];
      st.textContent = 몇 ? `문서에 반영했습니다 — ${몇}군데` : '문서에 반영했습니다';
      이력그리기();                     // 저장으로 새 판이 쌓였으니 좌측 이력 갱신
      if (typeof v2저장뒤 === 'function') v2저장뒤(j, snap);   // 판형 v2 — 차트 값·장 추가·프리셋은 다시 조립한 판을 다시 연다(응답 온 저장본을 넘겨 그 뒤 편집이 있나 대 본다)
    } else if (typeof v2저장뒤 === 'function' && v2저장뒤(j)) {
      st.textContent = v2저장뒤(j);    // 판형 v2 — 판 규칙(게이트)에 걸려 쓰지 않은 까닭
    } else if (/이 화면을 연 뒤에/.test(j.로그 || '')) {
      st.textContent = '다른 곳에서 이 문서가 바뀌었습니다 — 새로고침한 뒤 다시 고쳐 주세요';
    } else if (/찾지 못했습니다|사라졌습니다|세션/.test(j.로그 || '')) {
      // 정본(등록부)에서 문서 자체가 사라졌다는 응답 — "잠시 후 다시 시도"는 헛수고이므로
      // 표면별로 실제 복귀 동선을 알려준다(로컬서버=편집기열기 재실행, 공개 웹앱=앱 화면).
      st.textContent = 로컬서버
        ? '세션이 끝나 저장할 곳이 없습니다 — 편집기열기(editor)로 다시 열어 주세요'
        : '세션이 만료되었습니다 — 앱 화면에서 이 문서를 다시 열어 주세요';
    } else {
      st.textContent = 채팅표면
        ? '화면에만 저장했습니다 — 문서 반영은 채팅으로 알려 주세요'
        : '문서에 반영하지 못했습니다 — 잠시 후 다시 시도해 주세요';
    }
  } catch (e) {
    // 서버가 없어도 편집은 계속돼야 한다. 화면 저장은 이미 끝났다.
    // 스킬·MCP 는 서버가 없는 게 정상(채팅이 반영)이지만, 웹앱에선 서버 장애다.
    st.textContent = 채팅표면
      ? '화면에만 저장했습니다 — 문서에 반영하려면 채팅에 알려 주세요'
      : '문서에 반영하지 못했습니다 — 연결을 확인하고 다시 시도해 주세요';
  } finally { 보내는중 = false; }
}, 1500); }
document.addEventListener('input', save);

// ── 무입력 10분 → 미저장분 확정(save) + 만료 안내 ─────────────────────────────
// 웹앱 편집기는 별도 탭이라 앱 화면을 첫 화면으로 되돌릴 수는 없다. 대신 앱과 같은 무입력
// 기준(600s, 서버 세션.py 기본만료초와 맞춤)으로 미저장분을 서버에 확정하고 만료를 알린다 —
// 편집 중 유실 방지가 우선이라 화면을 파괴하지 않는다. 채팅표면(file://)엔 만료가 없다 —
// 로컬서버(플러그인 편집기)는 서버가 있으니 이 타이머도 돈다, 다만 안내 문구·복귀 동선이 다르다.
if (서버있음) (function () {
  const 만료ms = 600000; let 타이머 = null, 끝남 = false;
  function 되감기() { if (끝남) return; clearTimeout(타이머); 타이머 = setTimeout(만료, 만료ms); }
  function 만료() {
    끝남 = true;
    try { clearTimeout(sT); save(); } catch (e) {}          // 미저장분 즉시 확정
    const ov = document.createElement('div'); ov.className = 'ai-lock'; ov.style.display = 'flex';
    const 문구 = 로컬서버
      ? '10분 동안 입력이 없어 저장을 확정했습니다.<br>이 편집 화면을 새로고침하면 이어서 고칠 수 있습니다.'
      : '10분 동안 입력이 없어 세션이 만료되었습니다.<br>수정한 내용은 저장했습니다 — 이어서 작업하시려면 앱 화면에서 이 문서를 다시 열어 주세요.';
    const 새로고침버튼 = 로컬서버
      ? '<div style="margin-top:14px"><button onclick="location.reload()" '
        + 'style="padding:8px 18px;border:0;border-radius:8px;background:var(--ai-color-ink);'
        + 'color:var(--ai-color-white);font-size:14px;cursor:pointer">새로고침</button></div>'
      : '';
    ov.innerHTML = '<div style="max-width:420px;padding:18px 22px;background:var(--ai-color-white);'
      + 'border-radius:10px;color:var(--ai-color-ink);font-size:14px;line-height:1.7;text-align:center;'
      + 'box-shadow:0 8px 30px color-mix(in srgb, var(--ai-color-ink) 25%, transparent)">' + 문구 + 새로고침버튼 + '</div>';
    document.body.appendChild(ov);
  }
  ['pointerdown', 'keydown', 'input', 'change', 'wheel'].forEach(ev =>
    document.addEventListener(ev, 되감기, { passive: true, capture: true }));
  되감기();
})();

// ── 슬라이드 자유배치 — 개체(헤드·본문)를 그립으로 옮기고 8방향 핸들로 크기를 바꾼다 ──
// 픽토 자르기의 포인터 패턴과 같은 이치: inline left/top/width/height(%) 를 갱신하고 save()
// → serialize ⑧ 이 data-배치경로 로 되짚어 doc.배치 에 되쓴다(왕복). 드래그는 그립·핸들에서만
// 시작하므로 본문 클릭(자식 개체 선택)과 안 부딪힌다. 슬라이드 아닌 장르엔 sl-placed 가 없어 무해.
function 자유_비율(sec, e) {
  const r = sec.getBoundingClientRect();
  return [(e.clientX - r.left) / r.width * 100, (e.clientY - r.top) / r.height * 100];
}
// 값은 여기서만 2자리로 다듬는다 — 드래그가 만든 float 을 깔끔히 하되, serialize 는 화면 값을
// 그대로 읽어(반올림 안 함) 손으로 적은 임의 정밀도도 왕복이 정확하다(자리를 둘로 안 나눈다).
const 자유_고정 = v => Math.round(Math.max(0, Math.min(100, v)) * 100) / 100;
const 자유_둥글 = v => Math.round(v * 100) / 100;
function 자유핸들달기(el) {
  if (el.querySelector(':scope > .fp-grip')) return;
  const grip = document.createElement('div');
  grip.className = 'fp-grip'; grip.dataset.dir = 'move'; grip.textContent = '✥ 옮기기';
  el.appendChild(grip);
  ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].forEach(d => {
    const h = document.createElement('div'); h.className = 'fp-h fp-' + d; h.dataset.dir = d; el.appendChild(h);
  });
}
function 자유배치_달기(sec) {
  sec.querySelectorAll('.sl-placed').forEach(el => { el.classList.add('fp-move'); 자유핸들달기(el); });
}
let 자유끌기 = null;
// 마우스 이벤트를 쓴다(포인터가 아니라) — 픽토 자르기 선례와 같고, 임베디드 브라우저·자동화
// 도구가 포인터 이벤트를 늘 합성하진 않기 때문이다. 데스크톱 편집이라 터치는 대상 아님.
document.addEventListener('mousedown', e => {
  const grip = e.target.closest('.fp-grip'), handle = e.target.closest('.fp-h');
  if (!grip && !handle) return;                    // 그립·핸들에서만 끈다(본문 클릭은 선택으로)
  const el = e.target.closest('.sl-placed'); if (!el) return;
  const sec = el.closest('.sl-page.sl-free'); if (!sec) return;
  e.preventDefault();
  const [px, py] = 자유_비율(sec, e), st = el.style, v = k => parseFloat(st[k]) || 0;
  자유끌기 = { el, sec, dir: handle ? handle.dataset.dir : null, px, py,
    x: v('left'), y: v('top'), w: v('width') || 100, h: v('height') || 100 };
  select(el);
}, true);
document.addEventListener('mousemove', e => {
  const g = 자유끌기; if (!g) return;
  const [mx, my] = 자유_비율(g.sec, e), dx = mx - g.px, dy = my - g.py, st = g.el.style;
  if (!g.dir) {                                    // 이동 — 개체가 지면 밖으로 안 나가게 x+w·y+h 를 가둔다
    st.left = 자유_둥글(Math.max(0, Math.min(100 - g.w, g.x + dx))) + '%';
    st.top = 자유_둥글(Math.max(0, Math.min(100 - g.h, g.y + dy))) + '%';
  } else {                                         // 크기 조절(방향별) — 지면 안에 가둔다
    let x = g.x, y = g.y, w = g.w, h = g.h;
    if (g.dir.includes('e')) w = g.w + dx;
    if (g.dir.includes('s')) h = g.h + dy;
    if (g.dir.includes('w')) { w = g.w - dx; x = g.x + dx; }
    if (g.dir.includes('n')) { h = g.h - dy; y = g.y + dy; }
    if (x < 0) { w += x; x = 0; }                  // 왼/위로 나가면 0 에서 멈추고 폭·높이를 흡수
    if (y < 0) { h += y; y = 0; }
    w = Math.max(6, Math.min(w, 100 - x)); h = Math.max(6, Math.min(h, 100 - y));   // 최소 6%·지면 안
    st.left = 자유_둥글(x) + '%'; st.top = 자유_둥글(y) + '%';
    st.width = 자유_둥글(w) + '%'; st.height = 자유_둥글(h) + '%';
  }
}, true);
document.addEventListener('mouseup', () => {
  const g = 자유끌기; if (!g) return; 자유끌기 = null;
  state.ops.push({ action: g.dir ? '개체 크기' : '개체 이동' });
  save(); if (state.sel === g.el) renderPanel();
}, true);
// 토글: 흐름 ⇄ 자유. 흐름→자유면 헤드·본문에 기본 배치를 주고 sl-placed·경로·핸들을 단다.
function 자유배치토글(sec) {
  if (!sec) return;
  const i = sec.dataset.slideIdx, head = sec.querySelector('.sl-head'), body = sec.querySelector('.sl-body');
  if (!head && !body) { toast('이 슬라이드는 자유배치를 지원하지 않습니다'); return; }
  if (sec.classList.contains('sl-free')) {         // 자유 → 흐름
    sec.classList.remove('sl-free');
    sec.querySelectorAll('.sl-placed').forEach(el => {
      el.classList.remove('sl-placed', 'fp-move'); el.removeAttribute('style');
      el.removeAttribute('data-배치경로');
      el.querySelectorAll(':scope > .fp-grip, :scope > .fp-h').forEach(h => h.remove());
    });
    state.ops.push({ action: '흐름 배치로' });
  } else {                                          // 흐름 → 자유
    sec.classList.add('sl-free');
    const 기본 = { 헤드: { x: 5, y: 6, w: 62, h: 16 }, 본문: { x: 6, y: 30, w: 88, h: 62 } };
    const 앉히기 = (el, role) => {
      if (!el) return; const b = 기본[role];
      el.classList.add('sl-placed');
      el.style.cssText = `left:${b.x}%;top:${b.y}%;width:${b.w}%;height:${b.h}%`;
      el.setAttribute('data-배치경로', `슬라이드.${i}.배치.${role}`);
    };
    앉히기(head, '헤드'); 앉히기(body, '본문'); 자유배치_달기(sec);
    state.ops.push({ action: '자유 배치로' });
  }
  save(); renderPanel();
}
// 편집기가 뜰 때, doc 에서 이미 자유인 슬라이드에 그립·핸들을 단다.
document.querySelectorAll('.sl-page.sl-free').forEach(자유배치_달기);

// ── 상단바: 스타일·포인트색·글꼴·재조판 ──
// 타이머는 하나를 같이 쓴다 — 되돌리기 토스트(5초)가 떠 있는데 짧은 토스트의 옛 타이머가 그것을 먼저 닫지 않게.
function toast(m, ms) { note.textContent = m; note.style.display = 'block'; note._모양토스트 = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => note.style.display = 'none', ms || 1800); }
// 되돌리기 토스트 — 글 + [되돌리기] 단추. 누르면 fn 을 부르고 닫는다(Cmd/Ctrl+Z 와 같은 일).
function 되돌리기토스트(m, fn) {
  toast(m, 5000);
  const b = document.createElement('button'); b.type = 'button'; b.textContent = '되돌리기';
  b.onclick = () => { note.style.display = 'none'; fn(); };
  note.appendChild(b);
  note._모양토스트 = fn === 모양되돌리기;      // 이 토스트가 떠 있는 동안만 Cmd/Ctrl+Z 가 모양을 되돌린다(F4)
}
// 스타일 전환은 표지·목차·요약의 '구조'를 바꾸므로 CSS만으로는 미리보기가 불가능하다.
// 어중간한 혼합 상태를 보여주는 대신, 의도를 기록하고 재조립 때 반영한다.
const CUR_STYLE = document.documentElement.dataset.style === 'gov' ? 'gov' : 'std';
document.querySelectorAll('.edit-bar [data-style-btn]').forEach(b => b.onclick = () => {
  const want = b.dataset.styleBtn;
  document.querySelectorAll('.edit-bar [data-style-btn]').forEach(x => x.classList.toggle('on', x === b));
  state.pendingStyle = (want === CUR_STYLE) ? null : (want === 'gov' ? '정부부처형' : '기관 표준형');
  state.ops = state.ops.filter(o => o.action !== '스타일');
  if (state.pendingStyle) state.ops.push({ action: '스타일', to: state.pendingStyle });
  pendingBar(); save();
});
function pendingBar() {
  const p = [];
  if (state.pendingStyle) p.push('문서 모양 → ' + state.pendingStyle);
  if (state.본문꼴대기) p.push('본문 모양 → ' + state.본문꼴대기);

  const el = document.getElementById('pending-note');
  // 서버가 있는 화면(웹앱·로컬 편집기)은 저장할 때 문서를 다시 만든다 — '다시 만들 때'라고 쓰면
  // 문서를 새로 생성해야 하는 것처럼 읽혔다(2단계 UI 검토 F11). 파일로 연 화면만 옛 문구다.
  el.textContent = !p.length ? ''
    : 채팅표면 ? '문서를 다시 만들 때 반영: ' + p.join(' · ')
              : p.join(' · ') + ': 저장하면 문서에 반영되고 새로고침하면 보입니다';
}
const pick = document.getElementById('ptcolor');
if (pick) pick.oninput = () => {
  document.documentElement.style.setProperty('--pt', pick.value);
  state.포인트색 = pick.value;
  state.ops.push({ action: '강조색', to: pick.value }); save();
};
// 도식·차트 팔레트('26-09-28) — 표(#fig-palettes)는 build/도식색.py 가 계산한 hex 다. 여기서는
// --fig-* 만 바꾸고 도식을 다시 그린다. 문서에는 이름만 남는다(doc['팔레트']).
// 고르는 칸은 윗줄 '문서 설정' 팝오버 한 곳이다('26-09-29 — 문서 전체 설정은 윗줄, 개체 막대에는 역할 칩만).
const 팔레트판 = (() => { try { const o = JSON.parse(document.getElementById('fig-palettes').textContent);
  return (o && typeof o === 'object' && o['표']) ? o : null; } catch (e) { return null; } })();
function 팔레트지금() { return state.팔레트 || (팔레트판 && 팔레트판['지금']) || ''; }
function 팔레트걸기(v) {
  const t = 팔레트판 && 팔레트판['표'][v];
  if (!t || typeof t !== 'object') return false;
  Object.entries(t).forEach(([k, c]) => {
    if (/^[a-z0-9-]+$/.test(k) && /^#[0-9A-Fa-f]{6}$/.test(String(c)))   // 표 머리·첫 열(판정 ⑤)은 --doc-table-*
      document.documentElement.style.setProperty((/^doc-table-/.test(k) ? '--' : '--fig-') + k, c);
  });
  state.팔레트 = v;
  document.querySelectorAll('.docset-pop [data-palette-btn]').forEach(x =>
    x.setAttribute('aria-checked', String(x.dataset.paletteBtn === v)));
  if (window.SVGFIG && window.SVGFIG.refresh) window.SVGFIG.refresh();
  return true;
}
// 되돌리기 — 모양·도식 크기와 같은 규율('26-09-29 편집기 막대): 5초 토스트가 떠 있는 동안만 Cmd/Ctrl+Z 가
// 색을 되돌리고, 색을 바꾼 뒤 다른 편집이 문서에 저장되면 기록을 거둔다. 예전엔 색에 되돌리기가 없어,
// 문서 설정 창에서 모양 → 색을 차례로 바꾼 뒤 Cmd+Z 를 누르면 (마지막 조작인 색이 아니라) 모양이 돌아갔다.
var 팔레트되돌림 = null, 팔레트뒤편집 = false;
document.addEventListener('input', e => {
  if (!(e.target && e.target.closest && e.target.closest('.panel, .docset-pop'))) 팔레트뒤편집 = true;
}, true);
function 팔레트토스트떠있나() {           // 색 바꾸기가 마지막 조작일 때만(그 뒤 다른 조작·글 고침이 있으면 무효)
  if (!팔레트되돌림 || note.style.display !== 'block' || note.textContent !== 팔레트되돌림.글 || 팔레트뒤편집) return false;
  const 앞 = 팔레트되돌림.앞;
  return !state.ops.some(o => o && !앞.has(o) && o.action !== '도식 색');
}
function 팔레트기록_저장뒤(snap) {
  if (!팔레트되돌림) return;
  const 앞 = 팔레트되돌림.앞;
  const 다른op = (snap.ops || []).some(o => o && !앞.has(o) && o.action !== '도식 색');
  if (!(팔레트뒤편집 || 다른op)) return;
  const 떠있다 = note.style.display === 'block' && note.textContent === 팔레트되돌림.글;
  팔레트되돌림 = null; 팔레트뒤편집 = false;
  if (떠있다) note.style.display = 'none';
}
function 팔레트고르기(v) {
  const 전 = 팔레트지금();
  if (전 === v || !팔레트걸기(v)) return;
  state.ops.push({ action: '도식 색', to: v }); save();
  if (!전 || !(팔레트판['표'][전])) return;
  const fn = () => {
    if (!팔레트걸기(전)) return;
    state.ops.push({ action: '도식 색', to: 전 }); save();
    toast(`도식·차트 색을 ${전}${로(전)} 되돌렸습니다`, 2400);
  };
  되돌리기토스트(`도식·차트 색을 ${v}${로(v)} 바꿨습니다`, fn);
  팔레트되돌림 = { 글: note.textContent, fn, 앞: new Set(state.ops) }; 팔레트뒤편집 = false;
}
// 잡기 단계 — 색 토스트가 떠 있으면(가장 최근 조작) 색만 되돌리고 멈춘다(창이 열려 있어도 모양까지 되돌리지 않게).
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.isComposing || e.keyCode === 229) return;
  if ((e.key || '').toLowerCase() !== 'z') return;
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
  if (!팔레트토스트떠있나()) return;
  const f = 팔레트되돌림.fn; 팔레트되돌림 = null; note.style.display = 'none';
  e.preventDefault(); e.stopImmediatePropagation(); f();
}, true);
document.querySelectorAll('.edit-bar [data-font]').forEach(b => b.onclick = () => {
  document.documentElement.dataset.fonts = b.dataset.font;
  state.글꼴 = b.dataset.font;
  document.querySelectorAll('.edit-bar [data-font]').forEach(x => x.classList.toggle('on', x === b));
  state.ops.push({ action: '글꼴', to: b.textContent });
  if (typeof repaginate === 'function') repaginate();
});
// ── 슬라이드 디자인 영역 — 테마(라디오)·효과(라디오)·화면(토글) ──
document.querySelectorAll('.edit-bar [data-theme-btn]').forEach(b => b.onclick = () => {
  const v = b.dataset.themeBtn;
  document.querySelectorAll('.edit-bar [data-theme-btn]').forEach(x => x.classList.toggle('on', x === b));
  state.테마 = v;
  if (v === '네이비') document.documentElement.removeAttribute('data-테마');
  else document.documentElement.setAttribute('data-테마', v);   // 라이브 미리보기(색이 즉시 바뀐다)
  state.ops.push({ action: '테마', to: b.textContent });
  save();
});
document.querySelectorAll('.edit-bar [data-fx-btn]').forEach(b => b.onclick = () => {
  document.querySelectorAll('.edit-bar [data-fx-btn]').forEach(x => x.classList.toggle('on', x === b));
  state.효과 = b.dataset.fxBtn;
  state.ops.push({ action: '효과', to: b.textContent });   // 발표 보기에서 적용(편집 화면은 정적)
  save();
});
document.querySelectorAll('.edit-bar [data-screen-btn]').forEach(b => b.onclick = () => {
  const k = b.dataset.screenBtn, now = !b.classList.contains('on');
  b.classList.toggle('on', now);
  if (state.화면 === undefined) state.화면 = Object.assign({}, SRCDOC['화면'] || {});
  if (now) delete state.화면[k]; else state.화면[k] = false;   // 켬=키 없음(기본) · 끔=false
  state.ops.push({ action: '화면', to: b.textContent + (now ? ' 켬' : ' 끔') });
  save();
});
// ── 문서 설정 › 제목 모양(1p·풀버전) · 본문 모양(보도자료) — '26-09-28 ─────────────────────
// 윗줄 '문서 설정'에서 연다. 개체 막대·오른쪽 패널에는 올리지 않는다(원칙 5 — 개체 하나에 걸리지 않는
// 것은 윗줄). 제목 모양은 CSS 스위치(<html data-제목모양·제목틀·장모양·절모양>)라 누르면 **바로**
// 문서 전체에 걸린다 — 구조·경로·조판기는 그대로다. 스타일처럼 '다시 만들 때 반영'이 아니다.
// 호버 미리 보기는 두지 않는다. 누르면 적용이고, 되돌리기(토스트·Cmd/Ctrl+Z)가 미리 보기 노릇을 한다.
// 본문 모양(보도자료 본문꼴)은 짜임이 바뀌어(기호 없는 문단) 스타일과 같이 다시 만들 때 반영된다.
const 기본모양칸 = '문서지능-기본모양';   // workspace/app.html 과 같은 이름 — 웹앱은 같은 출처라 새 문서가 읽는다
const 모양장르 = ({ onepage: 'samples' })[document.documentElement.dataset.genre]
  || document.documentElement.dataset.genre || '';            // 등록부 이름(samples·fullreport)
const 요소줄 = [['제목틀', '제목 틀'], ['장모양', '장'], ['절모양', '절']].filter(([k]) => Array.isArray(상단칸[k]));
const 모양묶음 = 상단칸['제목모양'] || [];                      // [값, 라벨, 힌트, 한글 판정, 묶음 구성]
const 본문꼴들 = 상단칸['본문꼴'] || [];                        // [값, 라벨, 힌트] — 첫 값이 기본
function 로(s) {      // 받침에 따라 '로'·'으로' — "(으)로" 같은 괄호 표기를 화면에 안 쓴다
  const c = String(s || '').trim().slice(-1).charCodeAt(0) - 0xAC00;
  if (!(c >= 0 && c <= 11171)) return '로';
  return (c % 28 === 0 || c % 28 === 8) ? '로' : '으로';
}
function 지금모양() {
  const o = {};
  모양키.forEach(k => { const v = document.documentElement.getAttribute('data-' + k); if (v) o[k] = v; });
  return o;
}
function 모양걸기(o) {
  모양키.forEach(k => {
    if (o && o[k]) document.documentElement.setAttribute('data-' + k, o[k]);
    else document.documentElement.removeAttribute('data-' + k);
  });
}
const 같은모양 = (a, b) => 모양키.every(k => ((a || {})[k] || '') === ((b || {})[k] || ''));
const 요소덮음 = o => 요소줄.some(([k]) => (o || {})[k]);
function 기본칸() {                         // 첫 썸네일(키 없음) — [라벨, 힌트, 한글 판정]
  const d = 상단칸['제목모양_기본'] || {};
  return d[CUR_STYLE] || d.std || ['기본 모양', '', '✓'];
}
const 묶음찾기 = v => 모양묶음.find(m => m[0] === v);
const 선택지찾기 = (k, v) => (상단칸[k] || []).find(m => m[0] === v);
function 모양이름(o) {
  const 바탕 = !(o || {})['제목모양'] ? 기본칸()[0] : (묶음찾기(o['제목모양']) || [0, o['제목모양']])[1];
  if (!요소덮음(o)) return 바탕;
  // 요소를 따로 골랐으면 '직접 고름'이라는 상태 이름 대신 실제 모양을 말한다(2단계 UI 검토 F11) —
  // "연한 띠 바탕, 장은 짙은 띠". 토스트·기본값 줄이 무엇으로 시작하는지 읽히게.
  const 덧 = 요소줄.filter(([k]) => o[k]).map(([k, 이름]) => `${이름}은 ${(선택지찾기(k, o[k]) || [o[k], o[k]])[1]}`);
  return `${바탕} 바탕, ${덧.join(', ')}`;
}
const 근사말 = v => (typeof v === 'string' && v.startsWith('△')) ? v.replace(/^△\s*/, '') : '';
// 한글(HWPX)로 옮길 때 근사가 되는 자리 — 판정 칸이 '△ …'인 것만 모은다(✓ 는 그대로 옮겨진다).
function 근사알림(o) {
  const 말 = [], 더 = v => { const t = 근사말(v); if (t && !말.includes(t)) 말.push(t); };
  const 묶 = o['제목모양'] ? 묶음찾기(o['제목모양']) : null;
  if (!요소덮음(o)) { 더(묶 ? 묶[3] : 기본칸()[2]); return 말; }
  let 기본남음 = false;                     // 요소를 따로 골랐으면 요소마다 본다
  요소줄.forEach(([k]) => {
    const v = o[k] || (묶 && (묶[4] || {})[k]);
    if (v) 더((선택지찾기(k, v) || [])[3]); else 기본남음 = true;
  });
  if (기본남음 && !묶) 더(기본칸()[2]);
  return 말;
}
// 되돌리기 — 이 설정만의 작은 스택(전·후). 이력(state.ops)에도 남는다.
const 모양기록 = { 뒤: [], 앞: [] };
// Cmd/Ctrl+Z 가 모양을 되돌리는 것은 **문서 설정 창이 열려 있거나 모양 되돌리기 토스트가 떠
// 있는 동안**뿐이다(2단계 UI 검토 F4) — 모양을 바꾼 뒤 글을 고치고 Cmd+Z 를 누르면 몇 분 전
// 모양이 뜻밖에 돌아갔다. 그리고 모양을 바꾼 뒤 **다른 편집이 문서에 저장되면 모양 기록을
// 비운다**(저장뒤비우기 가 부른다) — 그 뒤에는 토스트·단축키 어느 쪽으로도 옛 모양이 안 돌아온다.
let 모양끝op = null, 모양뒤편집 = false;
const 모양op들 = new Set(['제목 모양', '제목 모양 되돌림']);
document.addEventListener('input', () => { 모양뒤편집 = true; }, true);
function 모양토스트떠있나() {
  return note.style.display === 'block' && note._모양토스트 === true;
}
function 모양이_마지막인가() {
  return !!document.querySelector('.docset-pop.open') || 모양토스트떠있나();
}
// 저장 응답 뒤 — 이번 저장에 모양 말고 다른 편집(글 입력·다른 조작)이 실렸으면 모양 기록을 비운다.
function 모양기록_저장뒤(snap) {
  const 다른op = (snap.ops || []).some(o => o && !모양op들.has(o.action));
  if (!(모양뒤편집 || 다른op)) return;
  모양기록.뒤 = []; 모양기록.앞 = []; 모양뒤편집 = false;
  if (모양토스트떠있나()) note.style.display = 'none';
}
function 모양적용(새, 무엇) {
  모양걸기(새);
  모양끝op = { action: 무엇 || '제목 모양', to: 모양이름(새) };
  state.ops.push(모양끝op); 모양뒤편집 = false;
  repaginate();                             // 장·절 높이가 바뀌니 쪽을 다시 나눈다(끝에서 save())
  모양판표시();
}
function 모양바꾸기(새, 말) {
  const 전 = 지금모양();
  if (같은모양(전, 새)) return;
  모양적용(새);
  모양기록.뒤.push({ 전, 후: 지금모양() }); 모양기록.앞 = [];
  const 이름 = 모양이름(새);
  되돌리기토스트(말 || `제목 모양을 ${이름}${로(이름)} 바꿨습니다`, 모양되돌리기);
}
function 모양되돌리기() {
  const r = 모양기록.뒤.pop(); if (!r) return false;
  모양적용(r.전, '제목 모양 되돌림'); 모양기록.앞.push(r);
  const 이름 = 모양이름(r.전);
  toast(`제목 모양을 ${이름}${로(이름)} 되돌렸습니다`, 2600);
  return true;
}
function 모양다시하기() {
  const r = 모양기록.앞.pop(); if (!r) return false;
  모양적용(r.후); 모양기록.뒤.push(r);
  const 이름 = 모양이름(r.후);
  toast(`제목 모양을 다시 ${이름}${로(이름)} 바꿨습니다`, 2600);
  return true;
}
// Cmd/Ctrl+Z · Shift+Cmd/Ctrl+Z · Ctrl+Y — 글 칸 안(편집 중·입력칸)은 브라우저 되돌리기에 맡긴다.
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey) || e.altKey || e.isComposing || e.keyCode === 229) return;
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
  const k = (e.key || '').toLowerCase();
  if (!모양이_마지막인가()) return;
  if (k === 'z' && !e.shiftKey) { if (모양되돌리기()) e.preventDefault(); }
  else if ((k === 'z' && e.shiftKey) || (k === 'y' && e.ctrlKey)) { if (모양다시하기()) e.preventDefault(); }
});
function 요소고르기(k, v) {
  const 새 = 지금모양();
  const 묶 = 새['제목모양'] ? 묶음찾기(새['제목모양']) : null;
  // 고른 묶음이 이미 그 값이면 덮어쓰지 않는다 — 문서 키를 깔끔히 둔다(기본이면 키를 안 남기는 규칙과 같은 결).
  if (!v || (묶 && (묶[4] || {})[k] === v)) delete 새[k]; else 새[k] = v;
  const 요소 = (요소줄.find(([x]) => x === k) || [k, k])[1];
  const 라벨 = v ? ((선택지찾기(k, v) || [v, v])[1]) : '';
  const 무엇 = 요소 === '제목 틀' ? '제목 틀을' : `${요소} 모양을`;
  모양바꾸기(새, v ? `${무엇} ${라벨}${로(라벨)} 바꿨습니다` : `${무엇} 묶음대로 돌렸습니다`);
}
// 썸네일 — 그림 파일이 아니다. 이 문서의 CSS 링크를 그대로 실은 iframe 에 이 문서의 첫 제목·장·절·
// 항목 두 줄을 복제해 넣고 줄여 보인다. 그래서 문서와 썸네일이 어긋날 일이 없다(스펙 ③-2).
const 조각꾸밈 = '<style>html,body{margin:0!important;padding:0!important;overflow:hidden!important;'
  + 'background:transparent!important}.font-switcher{display:none!important}'
  + '.fr-page{width:210mm!important;height:auto!important;min-height:0!important;margin:0!important;'
  + 'box-shadow:none!important;padding:7mm 20mm 3mm!important;box-sizing:border-box}'
  + '.ds-cover{display:block!important}.ds-cover .fr-cover-mid,.ds-cover .gov-cover-mid{margin:0!important;'
  + 'flex:none!important;display:block!important}.fr-content{height:auto!important;overflow:visible!important}'
  + '.sheet{width:210mm!important;height:auto!important;min-height:0!important;margin:0!important;'
  + 'box-shadow:none!important;padding:8mm 22mm 4mm!important;box-sizing:border-box}'
  + '.ds-body .i-l2,.ds-body .i-l3{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}<' + '/style>';
function 조각본문() {
  const q = s => document.querySelector(s);
  const 복제 = el => {
    if (!el) return '';
    const c = el.cloneNode(true);
    [c, ...c.querySelectorAll('[contenteditable]')].forEach(x => x.removeAttribute('contenteditable'));
    c.classList.remove('ent-sel', 'has-note');
    return c.outerHTML;
  };
  const 항목 = () => 복제(q('.i-l2')) + 복제(q('.i-l3'));
  const 표지 = q('.fr-cover');
  if (표지) {                                 // 풀버전 — 표지 제목 틀 + 첫 장·절
    const mid = 표지.querySelector('.fr-cover-mid, .gov-cover-mid');
    let 글 = '';
    if (mid) { const c = mid.cloneNode(true); c.querySelectorAll('.fr-date, .fr-subtitle').forEach(x => x.remove()); 글 = c.outerHTML; }
    return '<div class="' + esc(표지.className.replace(/\bent-sel\b/g, '')) + ' ds-cover">' + 글 + '</div>'
      + '<div class="fr-page ds-body"><div class="fr-content">' + 복제(q('.fr-chapter')) + 복제(q('.fr-sec'))
      + 항목() + '</div></div>';
  }
  return '<div class="sheet ds-body">' + 복제(q('.doc-titlebar:not(.bottom)')) + 복제(q('.doc-title'))
    + 복제(q('.doc-titlebar.bottom')) + 복제(q('.h-l1')) + 항목() + '</div>';
}
function 조각HTML(모양) {
  const de = document.documentElement;
  const 속성 = [...de.attributes].filter(a => !/^data-(제목모양|제목틀|장모양|절모양)$/.test(a.name))
    .map(a => ' ' + a.name + '="' + esc(a.value) + '"').join('')
    + 모양키.filter(k => 모양[k]).map(k => ' data-' + k + '="' + esc(모양[k]) + '"').join('');
  const 링크 = [...document.querySelectorAll('link[rel="stylesheet"]:not([data-editor])')]
    .map(l => '<link rel="stylesheet" href="' + esc(l.href) + '">').join('');
  const 꾸밈 = [...document.querySelectorAll('head style:not([data-editor])')].map(s => s.outerHTML).join('');
  return '<!doctype html><html' + 속성 + '><head><meta charset="utf-8">' + 링크 + 꾸밈 + 조각꾸밈
    + '<' + '/head><body>' + 조각본문() + '<' + '/body><' + '/html>';
  // 닫는 태그 글자를 쪼갠다(편집기 HTML 에 body 닫는 태그 글자가 하나 더 있으면 그 글자를 찾아 스크립트를
  // 끼우는 도구 — 시험 탐침 등 — 가 이 스크립트 한가운데에 끼워 편집기가 죽는다).
}
function 조각맞추기(f, pic) {
  const 배 = (pic.clientWidth || 200) / 794;
  let h = 0;
  try { h = f.contentDocument.body.scrollHeight; } catch (e) { /* 막히면 아래 기본 높이 */ }
  if (!h) h = 모양장르 === 'samples' ? 250 : 440;
  f.style.width = '794px'; f.style.height = h + 'px'; f.style.transform = 'scale(' + 배 + ')';
  pic.style.height = Math.ceil(h * 배) + 'px';
}
function 썸네일그리기() {
  if (!설정판) return;
  설정판.querySelectorAll('.ds-th').forEach(b => {
    const pic = b.querySelector('.ds-pic'), v = b.dataset.shape;
    const html = 조각HTML(v ? { 제목모양: v } : {});
    let f = pic.querySelector('iframe');
    if (f && f._조각 === html) return;        // 바뀐 것이 없으면 다시 안 그린다
    if (!f) {
      f = document.createElement('iframe');
      f.setAttribute('tabindex', '-1'); f.setAttribute('aria-hidden', 'true');
      f.onload = () => 조각맞추기(f, pic);
      pic.appendChild(f);
    }
    f._조각 = html; f.srcdoc = html;
  });
}
function 방향키(root, sel) {                 // radiogroup — 방향키로 옮기고 Enter·Space 로 고른다
  return e => {
    if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
    const xs = [...root.querySelectorAll(sel)], i = xs.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const 앞 = e.key === 'ArrowRight' || e.key === 'ArrowDown';
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? xs.length - 1 : (i + (앞 ? 1 : -1) + xs.length) % xs.length;
    xs.forEach((x, n) => { x.tabIndex = n === j ? 0 : -1; });
    xs[j].focus();
  };
}
function 한자리만(xs) {                       // 고른 것 하나만 Tab 으로 닿게(없으면 첫 칸)
  const on = xs.find(x => x.getAttribute('aria-checked') === 'true') || xs[0];
  xs.forEach(x => { x.tabIndex = x === on ? 0 : -1; });
}
function 모양판표시() {
  if (!설정판) return;
  const o = 지금모양(), 덮음 = 요소덮음(o);
  const 칸들 = [...설정판.querySelectorAll('.ds-th')];
  칸들.forEach(b => b.setAttribute('aria-checked',
    String(!덮음 && (b.dataset.shape || '') === (o['제목모양'] || ''))));
  if (칸들.length) 한자리만(칸들);
  설정판.querySelectorAll('.ds-row[data-el]').forEach(row => {
    const xs = [...row.querySelectorAll('.ds-opt')];
    xs.forEach(b => b.setAttribute('aria-checked', String((o[row.dataset.el] || '') === b.dataset.v)));
    한자리만(xs);
  });
  const now = 설정판.querySelector('.ds-now');
  if (now) {
    now.textContent = '지금 모양: ' + 모양이름(o);   // 요소를 따로 골랐으면 "…바탕, 장은 …"까지 이름이 말한다
  }
  const n = 설정판.querySelector('.ds-note');
  if (n) { const 말 = 근사알림(o); n.hidden = !말.length; n.textContent = 말.join(' · '); }
  const bk = 본문꼴지금();
  설정판.querySelectorAll('.ds-opt[data-bk]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.bk === bk)));
  const bkr = 설정판.querySelector('.ds-row[data-bkrow]');
  if (bkr) 한자리만([...bkr.querySelectorAll('.ds-opt')]);
  const bh = 설정판.querySelector('.ds-bkhint');
  if (bh) bh.textContent = ((본문꼴들.find(m => m[0] === bk) || [])[2]) || '';
}
function 본문꼴지금() {
  return state.본문꼴 !== undefined ? state.본문꼴 : (SRCDOC['본문꼴'] || (본문꼴들[0] || [])[0] || '');
}
function 본문꼴고르기(v, 라벨) {
  const 원래 = SRCDOC['본문꼴'] || (본문꼴들[0] || [])[0];
  if (v === 본문꼴지금()) return;
  state.본문꼴 = v;
  state.본문꼴대기 = v === 원래 ? null : 라벨;
  state.ops = state.ops.filter(o => o.action !== '본문 모양');
  if (state.본문꼴대기) state.ops.push({ action: '본문 모양', to: 라벨 });
  pendingBar(); 모양판표시(); save();
  toast(state.본문꼴대기 ? `본문 모양을 ${라벨}${로(라벨)} 바꿉니다 — `
                          + (채팅표면 ? '문서를 다시 만들 때 반영됩니다' : '저장하면 문서에 반영되고 새로고침하면 보입니다')
                        : '본문 모양을 원래대로 둡니다', 2600);
}
// '이 모양을 기본으로' — 다음 새 문서부터 이 모양으로 시작한다(스펙 ③-3). 기관 이름은 싣지 않는다.
//   웹앱: 계정이 없어 1차는 **이 브라우저에만**(localStorage, 판정 D5) — 실패해도 편집은 그대로 간다.
//   플러그인(로컬 편집기 서버): 이 설치본의 개인 설정(개인기본모양 작업) — 새문서가 거기서 읽는다.
//   파일로 연 편집기(서버 없음): 저장할 곳이 없어 채팅으로 돌린다.
function 기본모양값() {
  const o = 지금모양(), pt = state.포인트색 || SRCDOC['포인트색'];
  if (pt && 모양장르 === 'fullreport') o['포인트색'] = pt;
  return o;
}
async function 기본읽기() {
  if (로컬서버) {
    try { const r = await 부르기('personaldefault', { 장르: 모양장르, 결정: '보기' }, true);
          return (r && r.ok && r['값']) || null; } catch (e) { return null; }
  }
  if (채팅표면) return null;
  try { return (JSON.parse(localStorage.getItem(기본모양칸) || '{}') || {})[모양장르] || null; }
  catch (e) { return null; }
}
async function 기본표시() {
  const w = 설정판 && 설정판.querySelector('.ds-where'); if (!w) return;
  if (채팅표면) { w.textContent = '파일로 연 편집 화면에서는 기본값을 저장할 수 없습니다.'; return; }
  const 값 = await 기본읽기();
  const 어디 = 로컬서버 ? '이 컴퓨터의 개인 설정에 저장됩니다.' : '이 브라우저에만 저장됩니다.';
  // 저장한 적이 없는데 "이 모양으로 시작합니다"라고 쓰면 이미 저장된 것처럼 읽힌다(2단계 UI 검토 F11).
  w.textContent = 값 && Object.keys(값).some(k => 모양키.includes(k))
    ? `지금 기본: ${모양이름(값)}. 다음 새 문서부터 이 모양으로 시작합니다. ${어디}`
    : `'이 모양을 기본으로'를 누르면 다음 새 문서부터 지금 모양으로 시작합니다. ${어디}`;
}
async function 기본모양저장(지우기) {
  if (채팅표면) { toast("이 화면에서는 기본값을 저장할 수 없습니다 — 채팅에 '이 제목 모양을 기본으로 해 줘'라고 알려 주세요", 4200); return; }
  const 항목 = 지우기 ? null : 기본모양값();
  if (로컬서버) {
    try {
      const r = await 부르기('personaldefault', { 장르: 모양장르, 항목, 결정: 지우기 ? '지우기' : '저장' }, true);
      if (!r || !r.ok) { toast((r && r['로그']) || '기본 모양을 저장하지 못했습니다', 3200); return; }
    } catch (e) { toast('기본 모양을 저장하지 못했습니다 — 편집기 서버 연결을 확인해 주세요', 3200); return; }
  } else {
    try {
      const all = JSON.parse(localStorage.getItem(기본모양칸) || '{}') || {};
      if (지우기) delete all[모양장르]; else all[모양장르] = 항목;
      localStorage.setItem(기본모양칸, JSON.stringify(all));
    } catch (e) {
      // 브라우저가 저장을 막아도 문서 편집은 메모리 사본으로 서버에 반영된다(F6) — 막힌 것은 기본값뿐이다.
      toast('기본 모양을 이 브라우저에 저장하지 못했습니다 — 문서에 고친 내용은 그대로 저장됩니다', 3200);
      const w = 설정판 && 설정판.querySelector('.ds-where');
      if (w) w.textContent = '이 브라우저가 저장을 막고 있어 기본 모양을 남길 수 없습니다.';
      return;
    }
  }
  // 기본값 저장은 이 문서의 편집이 아니다 — 문서 이력(ops)에 넣지 않는다(2단계 UI 검토 F5).
  toast(지우기 ? '기본 모양을 지웠습니다 — 다음 새 문서는 스타일 기본 모양으로 시작합니다'
               : `다음 새 문서부터 ${모양이름(항목)}${로(모양이름(항목))} 시작합니다`, 3200);
  기본표시();
}
const 설정단추 = document.getElementById('btn-docset');
let 설정판 = null;
function 설정판만들기() {
  설정판 = document.createElement('div');
  설정판.className = 'docset-pop'; 설정판.setAttribute('data-editor', '');
  설정판.setAttribute('role', 'dialog'); 설정판.setAttribute('aria-label', '문서 설정');
  if (모양있음) {
    const s = document.createElement('div'); s.className = 'ds-sec';
    s.innerHTML = '<h3>제목 모양</h3><p class="ds-sub">누르면 문서 전체에 바로 적용됩니다. '
      + 'Cmd/Ctrl+Z 로 되돌릴 수 있습니다.</p>';
    const grid = document.createElement('div'); grid.className = 'ds-grid';
    grid.setAttribute('role', 'radiogroup'); grid.setAttribute('aria-label', '제목 모양');
    [['', ...기본칸()], ...모양묶음].forEach(([v, 라벨, 힌트, 판정]) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'ds-th'; b.dataset.shape = v; b.setAttribute('role', 'radio');
      const 근사 = 근사말(판정);
      b.setAttribute('aria-label', [라벨, 힌트, 근사].filter(Boolean).join(' — '));
      b.innerHTML = '<div class="ds-pic"></div><div class="ds-nm">' + esc(라벨) + '</div>'
        + (힌트 ? '<div class="ds-hint">' + esc(힌트) + '</div>' : '')
        + (근사 ? '<div class="ds-hwp" title="' + esc(근사) + '">한글 파일에서는 조금 다르게 나옵니다</div>' : '');
      b.onclick = () => 모양바꾸기(v ? { 제목모양: v } : {});
      grid.appendChild(b);
    });
    grid.addEventListener('keydown', 방향키(grid, '.ds-th'));
    s.appendChild(grid);
    s.insertAdjacentHTML('beforeend', '<p class="ds-now"></p><div class="ds-note" hidden></div>');
    if (요소줄.length) {
      const det = document.createElement('details');
      det.innerHTML = '<summary>자세히 — 요소마다 고르기</summary>';
      요소줄.forEach(([k, 이름]) => {
        const row = document.createElement('div');
        row.className = 'ds-row'; row.dataset.el = k;
        row.setAttribute('role', 'radiogroup'); row.setAttribute('aria-label', 이름 + ' 모양');
        row.innerHTML = '<span class="ds-lb">' + esc(이름) + '</span>';
        [['', '묶음대로', '고른 묶음을 따릅니다', '✓'], ...상단칸[k]].forEach(([v, 라벨, 힌트, 판정]) => {
          const o = document.createElement('button');
          o.type = 'button'; o.className = 'ds-opt'; o.dataset.v = v; o.setAttribute('role', 'radio');
          o.textContent = 라벨;
          o.title = [힌트, 근사말(판정)].filter(Boolean).join(' — ');
          o.onclick = () => 요소고르기(k, v);
          row.appendChild(o);
        });
        row.addEventListener('keydown', 방향키(row, '.ds-opt'));
        det.appendChild(row);
      });
      s.appendChild(det);
    }
    const foot = document.createElement('div'); foot.className = 'ds-foot';
    foot.appendChild(btn('이 모양을 기본으로', () => 기본모양저장(false), 'good'));
    foot.appendChild(btn('기본 되돌리기', () => 기본모양저장(true)));
    foot.insertAdjacentHTML('beforeend', '<span class="ds-where"></span>');
    s.appendChild(foot);
    설정판.appendChild(s);
  }
  if (본문꼴들.length) {
    const s = document.createElement('div'); s.className = 'ds-sec';
    s.innerHTML = '<h3>본문 모양</h3><p class="ds-sub">' + (채팅표면
      ? '본문 구조가 바뀌어 문서를 다시 만들 때 반영됩니다.'
      : '본문 구조가 바뀌어 화면에는 바로 안 보입니다. 저장하면 문서에 반영되고 새로고침하면 보입니다.') + '</p>';
    const row = document.createElement('div');
    row.className = 'ds-row'; row.dataset.bkrow = '1';
    row.setAttribute('role', 'radiogroup'); row.setAttribute('aria-label', '본문 모양');
    본문꼴들.forEach(([v, 라벨, 힌트]) => {
      const o = document.createElement('button');
      o.type = 'button'; o.className = 'ds-opt'; o.dataset.bk = v; o.setAttribute('role', 'radio');
      o.textContent = 라벨; o.title = 힌트 || '';
      o.onclick = () => 본문꼴고르기(v, 라벨);
      row.appendChild(o);
    });
    row.addEventListener('keydown', 방향키(row, '.ds-opt'));
    s.appendChild(row);
    s.insertAdjacentHTML('beforeend', '<p class="ds-sub ds-bkhint" style="margin:4px 0 0"></p>');
    설정판.appendChild(s);
  }
  if (팔레트판) {                                       // 도식·차트 색 — 문서 전체에 한 벌(개체 막대에는 역할 칩만)
    const s = document.createElement('div'); s.className = 'ds-sec';
    s.innerHTML = '<h3>도식·차트 색</h3><p class="ds-sub">문서 안 도식·차트와 표 머리·첫 열 칠이 함께 바뀝니다. '
      // 막는 폭은 도식색.적색인가(25° 아래·330° 위, '26-09-29 판정 ①) — 주황빛 빨강(21°)·주황 CI(23°)·진홍(334°)도
      // 막는다. 표 머리·첫 열도 팔레트를 따른다(판정 ⑤). 장·절 제목색은 기관색 그대로다
      + '빨강 계열 기관색(주황빛 빨강·진홍 포함)은 도식·표에 쓰지 않고 남색으로 둡니다(빨강은 경고·역방향 전용). 장·절 제목은 기관색 그대로입니다.</p>';
    const row = document.createElement('div');
    row.className = 'ds-row'; row.dataset.palrow = '1';
    row.setAttribute('role', 'radiogroup'); row.setAttribute('aria-label', '도식·차트 색');
    Object.keys(팔레트판['표']).forEach(v => {
      const t = 팔레트판['표'][v] || {};
      const o = document.createElement('button');
      o.type = 'button'; o.className = 'ds-opt'; o.dataset.paletteBtn = v; o.setAttribute('role', 'radio');
      o.setAttribute('aria-checked', String(v === 팔레트지금()));
      const sw = document.createElement('span');
      sw.style.cssText = 'display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px';
      if (/^#[0-9A-Fa-f]{6}$/.test(String(t['accent'] || ''))) sw.style.background = t['accent'];
      o.appendChild(sw); o.appendChild(document.createTextNode(v));
      o.onclick = () => 팔레트고르기(v);
      row.appendChild(o);
    });
    row.addEventListener('keydown', 방향키(row, '.ds-opt'));
    s.appendChild(row);
    설정판.appendChild(s);
  }
  if (typeof v2설정절 === 'function') v2설정절(설정판);   // 판형 v2 슬라이드 — 판 모양(프리셋)·밀도
  document.body.appendChild(설정판);
}
function 설정판열기(열기) {
  if (!설정단추) return;
  if (!설정판) 설정판만들기();
  const 연다 = 열기 === undefined ? !설정판.classList.contains('open') : !!열기;
  설정판.classList.toggle('open', 연다);
  설정단추.setAttribute('aria-expanded', String(연다));
  설정단추.classList.toggle('on', 연다);
  if (!연다) return;
  모양판표시(); 썸네일그리기(); 기본표시();
  const 첫 = 설정판.querySelector('[role="radio"][tabindex="0"]');
  if (첫) 첫.focus();
}
if (설정단추) 설정단추.onclick = () => 설정판열기();
document.addEventListener('mousedown', e => {                 // 바깥을 누르면 닫는다
  if (설정판 && 설정판.classList.contains('open')
      && !e.target.closest('.docset-pop, #btn-docset, .copy-note')) 설정판열기(false);
}, true);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && 설정판 && 설정판.classList.contains('open')) {
    설정판열기(false); if (설정단추) 설정단추.focus();
  }
});
if (pick) pick.addEventListener('input', () => {             // 포인트색이 바뀌면 썸네일도 같은 색으로
  if (설정판 && 설정판.classList.contains('open')) 썸네일그리기();
});

// 여러 장 전용 단추 — 1페이지·시행문·구성 설계 화면에는 없다.
// (없는 걸 null 째로 건드려 스크립트가 통째로 죽던 자리. on()으로 감싼다.)
const on = (id, f) => { const e = document.getElementById(id); if (e) e.onclick = f; };
on('btn-repag', () => { repaginate(); toast('줄과 쪽을 다시 맞췄습니다'); });
on('btn-copy', () => {
  const d = serialize().doc;
  const lines = [d.표지?.제목 || '', ''];
  (d.장 || []).forEach((c, i) => {
    lines.push(`${['Ⅰ','Ⅱ','Ⅲ','Ⅳ','Ⅴ','Ⅵ','Ⅶ','Ⅷ','Ⅸ','Ⅹ'][i] || (i + 1)}. ${c.제목}`);
    (c.절 || []).forEach(s => { lines.push(`  □ ${s.제목}`);
      (s.항목 || []).forEach(it => lines.push('    '.repeat(it.level - 1) +
        ({2:'○ ',3:'- ',4:'※ '}[it.level] || '') + it.text.replace(/<\/?[a-z]+>/g, ''))); });
  });
  const ta = document.createElement('textarea'); ta.value = lines.join('\n');
  document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); toast('본문 복사됨'); } catch (e) { toast('복사 실패'); }
  ta.remove();
});
// ── 판 보관 요청 ────────────────────────────────────────────────────
// 이 화면은 파일을 못 쓴다. 그래서 단추는 '요청'만 남기고, 실제 판은
// "고쳐놨어" 때 apply_edit_any 가 뜬다. 새 쓰기 경로를 만들지 않는다.
// prompt() 는 이 화면(임베디드 브라우저)에서 예외를 던지고 confirm() 은 조용히 false를
// 돌려준다 — 둘 다 쓰면 단추가 아무 일도 안 하고 사용자는 눌렀다고 믿는다.
// 그래서 묻는 것은 전부 화면 안에서 한다.
function 줄입력(라벨, 필수) {
  const wrap = document.createElement('label');
  wrap.style.cssText = 'display:block;margin-top:6px;font-size:12.5px';
  wrap.textContent = 라벨 + (필수 ? ' (필수)' : ' (선택)');
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.style.cssText = 'display:block;width:100%;margin-top:3px;padding:5px 7px;'
    + 'border:1px solid var(--ai-color-line-strong);border-radius:5px;font:inherit;box-sizing:border-box';
  wrap.appendChild(inp);
  return { wrap: wrap, get: () => inp.value.trim(), focus: () => inp.focus() };
}
// ── 되돌림 지점 — 여기로 돌아올 수 있게 이름 붙여 잡아 두는 자리(최대 3개) ──────
// 웹앱(http)은 서버가 목록·되돌리기·지우기를 처리한다. 스킬·MCP(file://)는 서버가
// 없어 채팅이 반영하므로, 잡기만 하고 목록·되돌리기는 이력(채팅) 몫으로 둔다.
const 지점최대 = 3;
async function 부르기(이름, 인자, 쓰기) {
  const r = 쓰기
    ? await fetch('/api/' + 이름, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(인자 || {}) })
    : await fetch('/api/' + 이름 + '?' + new URLSearchParams(인자 || {}));
  return r.json();
}
function 되돌림지점열기() {
  if (채팅표면) return 지점잡기();      // 스킬·MCP — 잡기만(채팅이 반영·되돌리기)
  되돌림지점패널();                     // 웹앱 — 목록 + 잡기 + 되돌리기 + 지우기
}
async function 되돌림지점패널() {
  document.querySelectorAll('.keep-bar').forEach(x => x.remove());
  const bar = document.createElement('div');
  bar.className = 'resume-bar keep-bar';
  bar.innerHTML = '<b>되돌림 지점</b> — 여기로 돌아올 수 있게 이름을 붙여 잡아 둡니다 (최대 '
    + 지점최대 + '개). 잡아 둔 지점으로 언제든 되돌릴 수 있습니다.';
  const 목록 = document.createElement('div'); 목록.style.cssText = 'margin-top:8px';
  bar.appendChild(목록);
  const row = document.createElement('div'); row.className = 'row'; bar.appendChild(row);
  const note = document.createElement('div');
  note.style.cssText = 'margin-top:6px;font-size:11.5px;opacity:.8';
  note.textContent = '이 기록은 작업하실 때 참고하시라고 모아 둔 것입니다. 기관의 공식 기록은 아닙니다.';
  bar.appendChild(note);
  document.body.insertBefore(bar, document.body.firstChild);
  async function 그리기() {
    목록.innerHTML = '<div style="opacity:.6;font-size:12px">불러오는 중…</div>';
    const r = await 부르기('history', { key: FN });
    const 지점 = ((r && r.ok && r['값'] && r['값']['판']) || []).filter(v => v['종류'] === '직접');
    목록.innerHTML = '';
    if (!지점.length)
      목록.innerHTML = '<div style="opacity:.7;font-size:12px">아직 잡아 둔 지점이 없습니다.</div>';
    지점.forEach(v => {
      const 이름 = v['메모'] || v['고친 이유'] || ('버전 ' + v['버전']);
      const 사유 = v['고친 이유'] || '';
      const d = document.createElement('div');
      d.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 0;'
        + 'border-top:1px solid var(--ai-color-line)';
      d.innerHTML = '<div style="flex:1"><b>' + esc(이름) + '</b>'
        + (사유 ? '<div style="font-size:11.5px;opacity:.75">' + esc(사유) + '</div>' : '')
        + '<div style="font-size:11px;opacity:.55">' + esc(v['때'] || '') + '</div></div>';
      d.appendChild(btn('되돌리기', () => 지점되돌리기(v['버전'], 이름), 'good'));
      d.appendChild(btn('지우기', () => 지점지우기(v['버전'], 그리기), 'danger'));
      목록.appendChild(d);
    });
    row.innerHTML = '';
    if (지점.length < 지점최대) {
      row.appendChild(btn('＋ 되돌림 지점 잡기', () => { bar.remove(); 지점잡기(); }, 'good'));
    } else {
      const m2 = document.createElement('div');
      m2.style.cssText = 'flex:1;font-size:12px;color:var(--ai-color-issue)';
      m2.textContent = '지점 ' + 지점최대 + '개가 찼습니다 — 하나를 지우고 다시 잡아 주세요.';
      row.appendChild(m2);
    }
    row.appendChild(btn('닫기', () => bar.remove()));
  }
  그리기();
}
// 지점 잡기 — 이름 + 사유를 받아 저장에 실어 보낸다(서버가 apply_edit_any 로 남긴다).
function 지점잡기() {
  document.querySelectorAll('.keep-bar').forEach(x => x.remove());
  const bar = document.createElement('div');
  bar.className = 'resume-bar keep-bar';
  bar.innerHTML = (채팅표면
      ? '<b>되돌림 지점을 잡습니다</b> — 채팅에 알려 주시면 그때 남깁니다. '
      : '<b>되돌림 지점을 잡습니다</b> — 저장되는 대로 서버가 남깁니다. ')
    + '여기로 돌아올 수 있게 이름과 사유를 적어 주세요. 화면·인쇄본도 함께 남습니다.';
  const m = 줄입력('이 지점의 이름 (예: 검토 요청 전)', false);
  bar.appendChild(m.wrap);
  const w = 줄입력('왜 여기에 지점을 잡나요 (사유)', true);
  bar.appendChild(w.wrap);
  const row = document.createElement('div'); row.className = 'row';
  row.appendChild(btn('지점 잡기', () => {
    if (!w.get()) { toast('사유를 한 줄 적어 주시면 잡습니다'); w.focus(); return; }
    state.보관요청 = { 종류: '직접', 메모: m.get(), 고친이유: w.get() };
    save(); bar.remove();
    toast(채팅표면
      ? '채팅에 "다 고쳤어요"라고 알려 주시면 지점을 남깁니다'
      : '지점을 잡습니다 — 저장되는 대로 목록에 나타납니다');
  }, 'good'));
  row.appendChild(btn('취소', () => bar.remove()));
  bar.appendChild(row);
  const note = document.createElement('div');
  note.style.cssText = 'margin-top:6px;font-size:11.5px;opacity:.8';
  note.textContent = '이 기록은 작업하실 때 참고하시라고 모아 둔 것입니다. 기관의 공식 기록은 아닙니다.';
  bar.appendChild(note);
  document.body.insertBefore(bar, document.body.firstChild);
  m.focus();
}
async function 지점되돌리기(n, 이름) {
  const r = await 부르기('revert', { key: FN, n: n, 이유: '되돌림 지점 「' + (이름 || '') + '」으로 복귀' }, true);
  if (!r || !r.ok) { toast((r && r['로그']) || '되돌리지 못했습니다'); return; }
  localStorage.removeItem(KEY);     // 옛 화면 버퍼가 되돌린 것을 덮지 않게
  toast('되돌렸습니다 — 화면을 새로 불러옵니다');
  setTimeout(() => location.reload(), 600);
}
async function 지점지우기(n, 다시그리기) {
  const r = await 부르기('delpoint', { key: FN, n: n }, true);
  if (!r || !r.ok) { toast((r && r['로그']) || '지우지 못했습니다'); return; }
  toast('지웠습니다'); if (다시그리기) 다시그리기();
}
const bk = document.getElementById('btn-keep');
if (bk) bk.onclick = () => 되돌림지점열기();

// 완료·닫기 — /workspace/app.html 로의 이동은 **웹앱에서만** 유효하다. 플러그인(file://)엔
// 그 서버·파일이 없어 location.replace 하면 방금까지 편집하던 화면이 브라우저 오류페이지
// (ERR_FILE_NOT_FOUND)로 대체된다. 그래서 채팅표면이면 이동하지 않고, 마지막 편집을 잃지
// 않게 화면을 **즉시** 저장(400ms 디바운스 건너뜀)한 뒤 반영을 시도하고 탭만 닫는다.
function 편집마침() {
  try {
    clearTimeout(sT);
    const snap = serialize();
    snap._저장때 = new Date().toLocaleString('ko-KR',
      { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    localStorage.setItem(KEY, JSON.stringify(snap));
  } catch (e) { /* 화면 저장 실패해도 아래로 진행 — 창을 오류로 대체하진 않는다 */ }
  보내기();   // 서버가 있으면 반영 시도, 없으면(플러그인) 화면 저장만 — 반영은 채팅의 Claude
  if (채팅표면) {
    toast('편집을 마쳤습니다 — 이 탭을 닫고 채팅으로 돌아가세요. 반영은 채팅이 합니다');
    window.close();   // 스크립트가 연 탭이면 닫히고, 아니면 무해한 no-op(오류페이지로 안 감)
    return;
  }
  // http(s) — 웹앱이면 SPA 홈으로 돌아가고, **무서버 정적 제공(플러그인)이면 이동하지 않는다.**
  // /workspace/app.html 이 없으면 location.replace 가 편집 화면을 404 오류페이지로 대체하기
  // 때문(코덱스·커서가 file:// 대신 정적 HTTP 로 편집기를 열 때 실측, 2026-08-24). 먼저 도달
  // 가능한지 HEAD 로 확인하고, 되면 이동·아니면 토스트+닫기만 한다(화면을 오류로 안 날린다).
  var _닫기 = function () { toast('편집을 마쳤습니다 — 이 탭을 닫으세요'); window.close(); };
  try {
    fetch('/workspace/app.html', { method: 'HEAD' }).then(function (r) {
      if (r && r.ok) { window.close(); setTimeout(function () { location.replace('/workspace/app.html'); }, 200); }
      else _닫기();
    }).catch(_닫기);
  } catch (e) { _닫기(); }
}
['btn-done', 'btn-close'].forEach(function (id) {
  const b = document.getElementById(id);
  if (b) b.addEventListener('click', 편집마침);
});

// ── 이어서 하기 ─────────────────────────────────────────────────────
// 고치다 만 것이 이 화면에만 남아 있다가 창을 닫으면 사라진다.
// 그런데 복구를 그냥 붙이면 **새 손실 경로**가 열린다 — 그 사이 문서가 다시
// 만들어졌다면 옛 버퍼를 되살리는 순간 새 내용이 조용히 지워진다.
// 그래서 반드시 _수정시각을 대조하고, 기계가 둘을 합치지 않는다.
function 이어서하기() {
  let buf;
  try { buf = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return; }
  if (!buf || !buf.doc) return;
  const 그때 = (buf.doc || {})['_수정시각'];
  const 지금 = (SRCDOC || {})['_수정시각'];
  const 같다 = !그때 || !지금 || 그때 === 지금;
  const 언제 = (buf.doc && buf._저장때) || '';

  const bar = document.createElement('div');
  bar.className = 'resume-bar' + (같다 ? '' : ' danger');
  bar.innerHTML = 같다
    ? `<b>고치시던 내용이 남아 있습니다.</b>${언제 ? ' ' + 언제 + '에 마지막으로 저장했습니다.' : ''}`
    : '<b>그 사이에 문서를 다시 만들었습니다.</b> 고치시던 내용을 되살리면 '
      + '새로 만든 내용이 지워집니다.';
  const row = document.createElement('div'); row.className = 'row';
  let 각오 = false;
  const go = btn(같다 ? '이어서 고치기' : '그래도 되살리기', () => {
    if (!같다 && !각오) {
      각오 = true;
      go.textContent = '한 번 더 누르면 새로 만든 내용이 지워집니다';
      return;                                   // confirm() 을 못 쓰므로 두 번 누르기로
    }
    되살리기(buf); bar.remove();
  }, 같다 ? 'good' : 'danger');
  row.appendChild(go);
  row.appendChild(btn(같다 ? '버리고 처음부터' : '버리고 새 문서로 시작', () => {
    localStorage.removeItem(KEY); bar.remove(); toast('고치던 내용을 버렸습니다');
  }));
  bar.appendChild(row);
  document.body.insertBefore(bar, document.body.firstChild);
}
// 되살리기는 화면을 다시 그리는 것이 아니라 '무엇이 달랐는지'만 알려준다.
// 기계가 두 쪽을 합치면 어느 쪽 뜻도 아닌 문서가 나오고 그 사실이 안 남는다.
function 되살리기(buf) {
  state.notes = buf.instructions || {};
  state.ops = buf.ops || [];
  // 저장기와 **같은 잣대**로 읽어야 한다. 경로 하나가 여러 조각으로 흩어져 있으면
  // 조각마다 부분 문자열이 나와 전부 '달라졌다'가 되고, 그 다음 줄이 조각마다
  // 온전한 문장을 써 넣어 한 문단이 조각 수만큼 반복된다 — 사용자가 한 글자도
  // 안 고쳤는데 문서가 망가진다(2026-08-04 확정, 규정 99자 → 645자·같은 문장 7회).
  // 지금은 자간 조정이 요소를 안 쪼개지만, 읽는 잣대가 두 벌이면 언제든 다시 갈린다.
  const diff = [];
  경로조각().forEach(([path, els]) => {
    const v = getPath(buf.doc, path);
    if (typeof v !== 'string') return;
    // 1p 본문(.html)은 값에 강조 마크업이 있어 글자와 그대로 대면 늘 '달라졌다'가 됐다 — 고친 것이
    // 없어도 "고치시던 내용 1군데와 …"를 말했다('26-09-28 2단계 UI 검토 F3 재측). 마크업을 벗겨 댄다.
    let 댈 = v;
    if (path.endsWith('.html')) { const t = document.createElement('div'); t.innerHTML = 허용마크업(v); 댈 = t.textContent.trim(); }
    if (댈 !== textOf(이어붙임(els)).trim()) diff.push([path, els, v]);
  });
  diff.forEach(([path, els, v]) => {
    const leaf = planLeaf(els[0]);
    // 1p 본문(.html)은 값에 강조 마크업이 들어 있다. textContent 로 넣으면 태그가
    // **글자로 박혀** 화면에 <span class="num"> 이 그대로 보이고, 그게 저장까지 된다
    // (2026-08-04 실측: bt01 한 문서에서 8군데). 마크업은 마크업으로 넣는다.
    if (path.endsWith('.html')) leaf.innerHTML = 허용마크업(v);
    else setText(leaf, v);
    els.slice(1).forEach(x => { x.textContent = ''; });   // 조각이 남아 있으면 글이 겹쳐 보인다
  });
  const 설정 = 설정되살리기(buf.doc || {});   // 저장(save)까지 부른다 — 되살린 글 잎과 설정을 한 번에 보낸다
  if (typeof repaginate === 'function') repaginate();
  const 무엇 = [diff.length ? `고치시던 내용 ${diff.length}군데` : '', 설정.join('·')].filter(Boolean).join('와 ');
  toast(무엇 ? `${무엇}${을를(무엇)} 되살렸습니다`
             : '고치신 글자는 없고, 남기신 요청만 되살렸습니다');
}
// 문서 설정(제목 모양·본문 모양·포인트색·글꼴·2단 마커)도 버퍼에서 되살린다(2단계 UI 검토 F3).
// 글 잎만 되살리면, 저장이 서버에 닿기 전에 창이 닫혔을 때 고른 모양이 사라지고 이력만 남았다.
// 되살린 설정 이름 목록을 돌려준다(토스트가 실제로 되살린 것만 말하게).
function 을를(s) { const c = String(s).charCodeAt(String(s).length - 1);
  return (c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28) ? '을' : '를'; }
function 설정되살리기(bd) {
  const 됨 = [], 루트 = document.documentElement;
  if (모양있음) {
    const 새 = {}; 모양키.forEach(k => { if (bd[k]) 새[k] = bd[k]; });
    if (!같은모양(지금모양(), 새)) { 모양걸기(새); 됨.push('제목 모양'); }
  }
  if (본문꼴들.length) {
    const 기본꼴 = (본문꼴들[0] || [])[0], 그때 = bd['본문꼴'] || 기본꼴;
    if (그때 !== 본문꼴지금()) {
      const 원래 = SRCDOC['본문꼴'] || 기본꼴, 라벨 = ((본문꼴들.find(m => m[0] === 그때) || [])[1]) || 그때;
      state.본문꼴 = 그때; state.본문꼴대기 = 그때 === 원래 ? null : 라벨;
      state.ops = state.ops.filter(o => o.action !== '본문 모양');
      if (state.본문꼴대기) state.ops.push({ action: '본문 모양', to: 라벨 });
      됨.push('본문 모양');
    }
  }
  const 색같다 = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  if (bd['포인트색'] && !색같다(bd['포인트색'], state.포인트색 || SRCDOC['포인트색'])) {
    루트.style.setProperty('--pt', bd['포인트색']); state.포인트색 = bd['포인트색'];
    const p = document.getElementById('ptcolor'); if (p) p.value = bd['포인트색'];
    됨.push('포인트색');
  }
  if (bd['글꼴'] && bd['글꼴'] !== (state.글꼴 || SRCDOC['글꼴'])) {
    루트.dataset.fonts = bd['글꼴']; state.글꼴 = bd['글꼴'];
    document.querySelectorAll('.edit-bar [data-font]').forEach(x => x.classList.toggle('on', x.dataset.font === bd['글꼴']));
    됨.push('글꼴');
  }
  if ((bd['2단마커'] || '') !== (루트.dataset.mk2 || '')) {
    if (bd['2단마커']) 루트.dataset.mk2 = bd['2단마커']; else delete 루트.dataset.mk2;
    됨.push('2단 마커');
  }
  if (됨.length) { if (typeof 모양판표시 === 'function') 모양판표시(); if (typeof pendingBar === 'function') pendingBar(); }
  // 본문 모양 요청(state.ops)을 쌓았으면 이 함수가 저장까지 부른다 — 화면만 고치고 저장을 안 부르는 조작이 없게
  // (verify_all 삭제도달). 부르는 곳(이어서하기)은 이 뒤에 따로 save() 를 부르지 않는다 — 차례는 전과 같다
  save();
  return 됨;
}
if (location.search.indexOf('selfcheck=1') < 0) 이어서하기();
이력그리기();                          // 좌측 편집이력 레일 최초 채우기(3단 왼쪽 기둥)
// ── 슬라이드 줌 — 3단 중앙에 16:9 를 맞춘다(맞춤=폭, ±로 조절). 슬라이드 문서만(.sl-page 있을 때). ──
(function 슬라이드줌초기() {
  const page = document.querySelector('.sl-page');
  if (!page) return;
  let z = 1, 수동 = false;
  const 폭px = () => {
    const cur = document.documentElement.style.getPropertyValue('--sl-zoom');
    document.documentElement.style.setProperty('--sl-zoom', '1');
    const w = page.getBoundingClientRect().width;      // 줌 1 기준 실제 폭
    document.documentElement.style.setProperty('--sl-zoom', cur || '1');
    return w;
  };
  const 적용 = () => {
    document.documentElement.style.setProperty('--sl-zoom', String(z));
    const v = document.querySelector('.sl-zval'); if (v) v.textContent = Math.round(z * 100) + '%';
  };
  const 맞춤 = () => {
    수동 = false;
    const 좌 = document.querySelector('.hist-panel') ? 260 : 0;
    const avail = window.innerWidth - 좌 - 268 - 48;
    const w = 폭px();
    z = Math.max(0.3, Math.min(1, avail / (w || 1280))); 적용();
  };
  const 줌 = d => { 수동 = true; z = Math.max(0.3, Math.min(2, +(z + d).toFixed(2))); 적용(); };
  const ctl = document.createElement('div'); ctl.className = 'sl-zoomctl';
  const b = (t, f) => { const x = document.createElement('button'); x.textContent = t; x.onclick = f; return x; };
  ctl.appendChild(b('－', () => 줌(-0.1)));
  const val = document.createElement('span'); val.className = 'sl-zval'; val.textContent = '100%';
  val.title = '눌러서 폭에 맞춤'; val.onclick = 맞춤; ctl.appendChild(val);
  ctl.appendChild(b('＋', () => 줌(0.1)));
  document.body.appendChild(ctl);
  맞춤();
  window.addEventListener('resize', () => { if (!수동) 맞춤(); });
})();
/*@@BAR@@*/
/*@@V2@@*/
renderPanel();
pendingBar();
if (typeof repaginate === 'function') setTimeout(repaginate, 200);
})();
</script>
"""


SKELETONS = Path(자료뿌리.골격뿌리())


def gen(fn, out_prefix="editor-", src_dir=None):
    """산출물·골격 HTML → 편집기 HTML. 장르는 문서에 심긴 프로파일이 알려준다."""
    base = Path(src_dir) if src_dir else SAMPLES
    src = (base / f"{fn}.html").read_text(encoding="utf-8")
    if base == SKELETONS:                      # 편집본은 buildplan/skeletons/edit/ 로 한 단계 더 들어간다
        src = src.replace('href="../../build/tokens.css', 'href="../../../build/tokens.css')
        src = src.replace('href="../skeleton.css', 'href="../../skeleton.css')
    # 편집기는 workspace/editors/ 에 놓이므로 산출물의 ../ 참조를 한 칸 더 올려야 한다.
    # 예전에는 파일 이름을 여덟 개 손으로 적어 뒀는데, 장르가 늘 때 regulation.css·
    # press.css·gmseal.js 가 빠져 편집 화면이 404 를 물고 **서식 없이** 떴다(2026-08-04).
    # 그래서 이름을 적지 않고, build/ 에 실제로 있는 파일이면 옮긴다.
    def _자산(m):
        속성, 경로, 꼬리 = m.group(1), m.group(2), m.group(3)
        실물 = (ROOT / "build" / 경로.split("/")[0]) if "/" in 경로 else (ROOT / "build" / 경로)
        return (f'{속성}="../../build/{경로}{꼬리}"' if 실물.exists()
                else m.group(0))
    src = re.sub(r'(href|src)="\.\./(?!\.\./)([^"?]+)([^"]*)"', _자산, src)

    prof = {}
    m = re.search(r'<script type="application/json" id="fr-profile">(.*?)</script>', src, re.S)
    if m:
        try:
            prof = json.loads(m.group(1))
        except Exception:
            prof = {}
    # 편집기 AI 재작성(개체고쳐)이 서버에서 이 문서의 배경(최초 의도·자료)을 되찾을 수 있게
    # 문서키(파일명)를 프로파일에 심는다 — 서버가 자기 등록부에서 조회하므로 원자료는 안 실린다.
    if m:
        prof["key"] = fn
        src = src.replace(m.group(0),
            '<script type="application/json" id="fr-profile">'
            + json.dumps(prof, ensure_ascii=False) + '</script>', 1)
    bar_spec = prof.get("상단바", {})
    gov = 'data-style="gov"' in src
    # 슬라이드 디자인 영역 초기 상태 — 현재 doc 의 테마·효과·화면(없으면 기본값)
    cur_doc = {}
    md = re.search(r'<script type="application/json" id="fr-doc">(.*?)</script>', src, re.S)
    if md:
        try:
            cur_doc = json.loads(md.group(1))
        except Exception:
            cur_doc = {}
    cur_테마 = cur_doc.get("테마") or "네이비"
    cur_효과 = cur_doc.get("효과") or "페이드"
    cur_화면 = cur_doc.get("화면") or {}
    grp = []
    for key, label in bar_spec.get("스타일", []):
        on = " class=on" if (key == "gov") == gov else ""
        grp.append(f'<button data-style-btn="{key}"{on}>{label}</button>')
    if bar_spec.get("포인트색"):
        # <input type=color> 의 value 속성은 HTML5 명세상 #rrggbb 리터럴만 받는다(var() 불가) —
        # 이 값은 앱 크롬 색이 아니라 **풀버전 문서 자신의 포인트색 기본값**(기관표준형 파랑)이라
        # 브랜드 토큰과 무관하다. build/verify_all.py 의 check_app_no_raw_hex 가 이 줄만 면제한다.
        grp.append('<input type="color" id="ptcolor" value="#0070C0" title="강조색">')
    if bar_spec.get("팔레트"):
        # 도식·차트 팔레트('26-09-28 사장님 판정) — 남색·청·청록·먹 + 기관색(문서 포인트색, 적색이면
        # 남색). 색 값은 여기 적지 않는다 — build/도식색.py 가 hex 로 계산한 표를 JSON 으로 싣고,
        # 단추는 이름만 보인다. 누르면 --fig-* 를 바꿔 도식을 다시 그리고, 저장하면 doc['팔레트'].
        _색사양 = _iu.spec_from_file_location("도식색", str(ROOT / "build" / "도식색.py"))
        도식색 = _iu.module_from_spec(_색사양)
        _색사양.loader.exec_module(도식색)
        지금팔레트, _ = 도식색.문서강조(cur_doc)
        # 표 머리·첫 열 칠도 같은 표에 싣는다('26-09-29 판정 ⑤ — 키가 doc-table- 로 시작하면 SCRIPT 가
        # --doc-table-* 에 건다). 남색 기본은 재경부 실측 값 그대로다(도식색.표색 — 값은 거기에만 적는다)
        def _한벌(c):
            return {**도식색.팔레트(c), **도식색.표색(도식색.막은강조(c))}
        표 = {이름: _한벌(c) for 이름, c in 도식색.프리셋.items()}
        표[도식색.기관색이름] = _한벌(도식색.문서강조({**cur_doc, "팔레트": 도식색.기관색이름})[1])
        # 단추는 윗줄이 아니라 '문서 설정' 팝오버에 한 번만 둔다('26-09-29 편집기 막대 — 팔레트는 문서 전체
        # 설정이라 개체 막대·윗줄 단추 줄에 안 올린다). SCRIPT 가 이 표에서 칩을 짓는다(이름·차례 = 표 키).
        grp.append('<script type="application/json" id="fig-palettes">'
                   + json.dumps({"표": 표, "지금": 지금팔레트 if 지금팔레트 in 표 else ""},
                                ensure_ascii=False).replace("</", "<\\/") + '</script>')
    # 문서 설정('26-09-28) — 문서 전체에 걸리는 설정(제목 모양·본문 모양)을 여는 윗줄 단추(원칙 5:
    # 개체 하나에 걸리지 않는 것은 윗줄). 팝오버는 SCRIPT 가 프로파일(상단바)에서 짓는다.
    if bar_spec.get("제목모양") or bar_spec.get("본문꼴") or bar_spec.get("프리셋") or bar_spec.get("팔레트"):
        무엇 = ("제목 모양" if bar_spec.get("제목모양") else "판 모양·밀도" if bar_spec.get("프리셋")
              else "본문 모양" if bar_spec.get("본문꼴") else "도식·차트 색")
        if bar_spec.get("팔레트") and 무엇 != "도식·차트 색":
            무엇 += " · 도식·차트 색"
        grp.append('<button id="btn-docset" aria-haspopup="dialog" aria-expanded="false" '
                   f'title="문서 전체에 걸리는 설정 — {무엇}">문서 설정</button>')
    if grp:
        grp.append('<span style="width:8px"></span>')
    for i, (key, label) in enumerate(bar_spec.get("글꼴", [])):
        grp.append(f'<button data-font="{key}"{" class=on" if i == 0 else ""}>{label}</button>')
    if bar_spec.get("글꼴"):
        grp.append('<span style="width:8px"></span>')
    # 슬라이드 디자인 영역 — 테마·효과(라디오, 하나 켬)·화면(토글, 기본 켬)
    if bar_spec.get("테마"):
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">테마</span>')
        for key, label in bar_spec["테마"]:
            grp.append(f'<button data-theme-btn="{key}"{" class=on" if key == cur_테마 else ""}>{label}</button>')
        grp.append('<span style="width:8px"></span>')
    if bar_spec.get("효과"):
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">효과</span>')
        for key, label in bar_spec["효과"]:
            grp.append(f'<button data-fx-btn="{key}"{" class=on" if key == cur_효과 else ""}>{label}</button>')
        grp.append('<span style="width:8px"></span>')
    if bar_spec.get("화면"):
        grp.append('<span style="font-size:11px;color:var(--ai-color-muted);align-self:center;margin:0 3px 0 2px">화면</span>')
        for key, label in bar_spec["화면"]:
            켬 = cur_화면.get(key) is not False
            grp.append(f'<button data-screen-btn="{key}"{" class=on" if 켬 else ""}>{label}</button>')
        grp.append('<span style="width:8px"></span>')
    if bar_spec.get("재조판"):
        grp.append('<button id="btn-repag">↻ 줄·쪽 다시 맞춤</button>')
    if bar_spec.get("복사"):
        grp.append(f'<button id="btn-copy">📋 {bar_spec["복사"]} 복사</button>')
    auto = " · ".join(prof.get("자동", []))
    bar = (
        '<div class="edit-bar" data-editor>'
        f'<span class="grp"><b>{prof.get("라벨", "문서")}</b>'
        '<span class="warn"></span>'
        '<span id="pending-note" style="color:var(--ai-color-review);font-size:12px"></span></span>'
        f'<span class="grp">{"".join(grp)}'
        '<button id="btn-keep" title="여기로 돌아올 수 있게 이름 붙여 지점을 잡아 둡니다 (최대 3개)">되돌림 지점</button>'
        '<span class="st">아직 수정 없음</span>'
        '<span style="width:10px"></span>'
        '<button id="btn-done" title="편집을 마칩니다 — 수정은 자동 저장됩니다" '
        'style="background:var(--ai-color-signal);color:var(--ai-color-white);font-weight:700">완료</button>'
        '<button id="btn-close" title="편집 탭을 닫습니다 (수정은 자동 저장됨)">닫기</button>'
        '</span></div>'
        '<div class="copy-note" data-editor></div>'
        + (f'<!-- 자동 산출(편집 대상 아님): {auto} -->' if auto else ''))
    src = src.replace("<body>", "<body>\n" + bar, 1)
    # 그림 막대 '바꾸기' 목록 — 그림 개체가 있는 문서에만(그림 P3)
    if 'class="blk fr-fig fr-img' in src:
        src = src.replace("</body>", _그림카드조각(fn, cur_doc, prof.get("genre") or "") + "</body>", 1)
        try:        # 비밀 표지 자료의 그림 — 편집기 칩(등급 표시 확인). 개발 트리 정본 편집기에는 싣지 않는다
            if not _개발트리():
                src = _그림표지달기(src, 자료뿌리.모듈("imageasset").카드들(갱신=False))
        except Exception as exc:
            print(f"[편집기] 그림 표지를 못 달았습니다: {type(exc).__name__}", file=sys.stderr)
    # ui-tokens.css 는 workspace/ 에 산다 — 편집기 출력 위치가 갈리니(workspace/editors/
    # 와 buildplan/skeletons/edit/) 상대경로도 갈린다. 값을 여기 손으로 두 번 적는 대신
    # CHROME 의 자리표시자 하나를 그 위치에 맞게 채운다(SCRIPT 의 @@FN@@ 치환과 같은 결).
    TOKENS_HREF = "../../../workspace/ui-tokens.css" if base == SKELETONS else "../ui-tokens.css"
    # 판형 v2 슬라이드(부품 트리)면 v2 조각을 끼운다 — 옛 문서 편집 화면엔 자리표시만 비워진다.
    v2판 = 'class="deck v2' in src
    # 도식·차트·표 개체 위 막대 — 옛 편집 화면에만(v2 는 자기 막대가 있다). 조각이 없으면 자리표시만 비운다
    막대 = None if v2판 else _막대조각()
    src = src.replace("</head>", CHROME.replace("@@TOKENS_HREF@@", TOKENS_HREF)
                      + (막대.CHROME_BAR if 막대 else "")
                      + (_v2조각().CHROME_V2 if v2판 else "") + "</head>", 1)
    src = src.replace("</body>", SCRIPT.replace("@@FN@@", fn)
                      .replace("/*@@BAR@@*/", 막대.SCRIPT_BAR if 막대 else "")
                      .replace("/*@@V2@@*/", _v2조각().SCRIPT_V2 if v2판 else "")
                      .replace("/*@@표모양들@@*/[]", json.dumps(list(자료뿌리.모듈("표꼴").스타일들()),
                                                          ensure_ascii=False)) + "</body>", 1)
    EDITORS.mkdir(parents=True, exist_ok=True)
    out = EDITORS / f"{out_prefix}{fn}.html"
    if base == SKELETONS:
        (SKELETONS / "edit").mkdir(parents=True, exist_ok=True)
        out = SKELETONS / "edit" / f"{fn}.html"
    자료뿌리.원자쓰기(str(out), src)             # 원자 쓰기(WP-S2 ③)
    return out


def SOURCES():
    """장르 등록부는 세어서 얻는다 — 손으로 적으면 늘 때마다 빠진다.

    2026-08-04: 여기에 규정·보도자료가 빠져 있어 `--all` 이 그 둘의 편집기를 한 번도
    다시 만들지 않았다. 저장기를 고쳐도 화면은 옛 코드 그대로였고, 왕복 검사가
    '고쳤는데 안 고쳐졌다'고 나왔다. 같은 함정을 다섯 번째로 밟았다
    (자치간 SEL · 이력 SRC · verify_all BUILDS · 파급표 · 여기).
    """
    return [g["길"] for g in 자료뿌리.모듈("genres").등록부()]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] == "--skeletons":
        n = 0
        if SKELETONS.exists():
            for f in sorted(SKELETONS.glob("*.html")):
                gen(f.stem, src_dir=SKELETONS)
                n += 1
        print(f"구성 설계 화면: {n}건")
        return 0
    if sys.argv[1] == "--all":
        n = 0
        for srcname in SOURCES():
            path = Path(srcname)
            if not path.exists():
                continue
            for d in json.load(open(path, encoding="utf-8")):
                if (SAMPLES / f"{d['filename']}.html").exists():
                    gen(d["filename"])
                    n += 1
        print(f"editors: {n}건 (범용)")
    else:
        print("written:", gen(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
