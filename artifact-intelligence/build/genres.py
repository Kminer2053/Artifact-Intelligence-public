#!/usr/bin/env python3
"""장르 등록부 — 한 곳에서 세어서 얻는다.

왜 만들었나: 손으로 적은 장르 목록이 장르가 늘 때마다 빠져서 같은 함정을 여덟 번 밟았다.
  ① build/jachigan.js 의 SEL — 그 장르만 조판이 벌어짐
  ② history/version.py 의 SRC — 그 장르만 이력이 안 남음
  ③ build/verify_all.py 의 BUILDS — 그 장르만 조립 검사에서 빠짐
  ④ 파급표
  ⑤ workspace/render_editor_any.py 의 SOURCES — 그 장르만 편집기가 안 만들어짐
  ⑥ 2026-08-04 에 한꺼번에 드러난 다섯 곳 — 문체검사기(무검사 통과) · 작업 화면(문서가
     아예 안 보임) · 편집 반영기(고쳐도 정본에 못 씀) · 관측기(한 번도 관측 안 됨) ·
     조판 감사(지면을 못 찾아 '못 쟀다')
  ⑦ 조립기들의 캐시 판번호 ?v=N — 숫자도 목록이다(아래 판번호() 참고)
  ⑧ 2026-08-07 workspace/render_workspace.py main() 의 편집기 재생성 — samples 에
     시행문·풀버전 두 장르만 손으로 더해 돌아서 규정·보도자료만 편집 화면이 낡았고,
     편집 반영기의 인자 결합 버그가 세 장르에서 가려졌다. 등록부 이름을 나란히 적은
     줄은 이제 verify_all 의 check_hand_genre_lists 가 잡는다
증상이 매번 다르고 **어느 것도 "빠졌다"고 말해 주지 않는다.** 그래서 목록이 아니라
파일을 세어서 얻고, 장르마다 진짜로 다른 것만 아래 표에 둔다.

새 장르를 들일 때: build/<이름>-docs.json 을 두고 표에 한 줄 더하면 전부 따라온다.
표에 없는 등록부 파일이 있으면 **조용히 넘어가지 않고 예외로 알린다** —
"모르는 장르를 만났다"는 것이 곧 이 함정의 신호이기 때문이다.
"""
import importlib.util as _iu
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

# 등록부(build/*-docs.json)는 **자료**다 — 어느 뿌리에서 찾을지는 build/자료뿌리.py
# 한 곳이 정한다(WP-S2 ①). 여기서 `import 자료뿌리` 로 안 쓰는 이유: 이 모듈은
# history/version.py 처럼 build/ 가 sys.path 에 없는 자리에서도 불려 온다.
# sys.path 를 더 심지 않으려고(부록 A-1) 파일에서 바로 읽는다 — 정리는 WP-S9.
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(BASE, "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)


def _풀버전제목(d):
    return (d.get("표지") or {}).get("제목", d["filename"]).replace("\n", " ")


# 등록부 파일 이름(-docs.json 앞부분) → 장르마다 다른 것들
#   장르   = 조립기가 문서에 심는 data-genre 값 (audit.js 가 이 값으로 가른다)
#   키     = 내부 장르 키 (editor-profiles·rewind-rules·observe·stylelint 가 쓴다)
#            **둘은 다르다** — 1p 는 화면에 'onepage', 내부로는 'onepage-report' 다.
#            2026-08-04 에 이 둘을 뭉개서 관측기가 규칙표를 못 찾을 뻔했다.
#   조립기 = build/ 안의 파일명
#   라벨   = 사람에게 보일 이름
#   제목   = 문서 하나에서 제목을 꺼내는 법 (장르마다 필드가 다르다)
표 = {
    "samples": dict(장르="onepage", 키="onepage-report", 조립기="assemble.py", 라벨="1p 보고서",
                    제목=lambda d: d.get("title", d["filename"])),
    "gongmun": dict(장르="gongmun", 키="gongmun", 조립기="assemble_gongmun.py", 라벨="시행문",
                    제목=lambda d: d.get("제목", d["filename"])),
    "fullreport": dict(장르="fullreport", 키="fullreport", 조립기="assemble_full.py", 라벨="여러 장 보고서",
                       제목=_풀버전제목),
    "regulation": dict(장르="regulation", 키="regulation", 조립기="assemble_regulation.py", 라벨="규정",
                       제목=lambda d: d.get("제명", d["filename"])),
    "press": dict(장르="press-release", 키="press-release", 조립기="assemble_press.py", 라벨="보도자료",
                  제목=lambda d: d.get("제목", d["filename"])),
    "slides": dict(장르="slides", 키="slides", 조립기="assemble_slides.py", 라벨="발표 슬라이드",
                   제목=lambda d: (d.get("표지") or {}).get("제목", d["filename"])),
}


def 등록부():
    """build/*-docs.json 을 세어 장르 목록을 만든다. 항상 이 함수를 거쳐라."""
    out = []
    for p in 자료뿌리.등록부들():
        stem = 자료뿌리.등록부이름(p)
        meta = 표.get(stem)
        if meta is None:
            raise KeyError(
                f"모르는 장르 등록부: build/{stem}-docs.json — build/genres.py 의 표에 "
                f"한 줄 더해야 한다. 여기서 조용히 넘어가면 그 장르만 검사·편집·관측에서 "
                f"빠진 채 '통과'로 보인다(여섯 번 겪은 함정이다)")
        # 자료 = 보여 주는 이름(코드뿌리 기준 상대 경로) · 길 = **실제로 열 곳**.
        # 등록부는 자료라서 자료뿌리를 탄다 — 상대 경로를 ROOT 에 붙여 여는 옛 습관이
        # 남아 있으면 다른 뿌리에서 조용히 코드뿌리의 정본을 연다(WP-S2 ①).
        out.append(dict(이름=stem, 자료=f"build/{stem}-docs.json", 길=p, **meta))
    return out


def 키값들():
    """내부 장르 키 모음 — editor-profiles·rewind-rules·stylelint 와 맞춰야 한다."""
    return {g["키"] for g in 등록부()}


def 한건만(docs, argv):
    """`--only <문서키>` 가 있으면 그 문서 하나만 남긴다 — 조립기 다섯이 공통으로 쓴다.

    왜 필요한가(WP-S2 ②): 등록부 하나에 그 장르 문서가 **전부** 들어 있고 조립기가
    그 배열을 처음부터 끝까지 다시 만들었다. 세션을 갈라도 한 세션 안에서 문서 둘을
    만들면 하나를 저장할 때 나머지가 통째로 다시 써진다 — 남이 그 사이에 고친 것이
    조용히 덮이고, 무엇보다 바꾸지도 않은 파일의 시각·내용이 흔들린다.
    (출시계획 3-2 완료 기준 ①: "한 건 조립 후 다른 문서 파일이 안 바뀌었는지")

    **없는 키를 주면 조용히 0건을 만들지 않고 선다**(규칙 3) — 오타 하나에
    "조립 성공, 만든 것 없음" 이 되면 아무도 못 알아챈다.
    """
    if "--only" not in argv:
        return docs
    i = argv.index("--only")
    키 = argv[i + 1] if i + 1 < len(argv) else ""
    남은 = [d for d in docs if d.get("filename") == 키]
    if not 남은:
        raise SystemExit(f"✗ --only {키!r} — 이 등록부에 그런 문서가 없습니다 "
                         f"(있는 것 {len(docs)}건)")
    return 남은


def 자료파일들():
    """등록부의 **실제 경로** 모음 — 자료뿌리 기준이다."""
    return [g["길"] for g in 등록부()]


def 장르값들():
    """조립기가 심는 data-genre 값 모음 — audit.js·stylelint 의 장르 키와 맞춰야 한다."""
    return {g["장르"] for g in 등록부()}


# ── 판번호 ──────────────────────────────────────────────────────────────────
_판캐시 = {}


def 판번호(파일명):
    """`build/<파일명>` 의 **내용**에서 짧은 판번호를 만든다.

    왜 — 조립기들이 `?v=13` 같은 숫자를 손으로 달고 있었다(다섯 조립기에 17개).
    CSS 를 고쳐도 이 숫자를 안 올리면 브라우저가 옛 파일을 계속 쓴다.
    2026-08-05 에 실제로 겪었다: press.css 의 마커 결함을 고쳤는데 `?v=1` 이 그대로라
    PDF 가 옛 규칙으로 계속 나왔고, "안 고쳐졌다"고 한참 뒤졌다.
    genres.py 머리말에 적힌 손목록 함정의 일곱 번째다 — **숫자도 목록이다.**
    """
    if 파일명 not in _판캐시:
        import hashlib
        p = os.path.join(BASE, 파일명)
        try:
            with open(p, "rb") as f:
                _판캐시[파일명] = hashlib.sha1(f.read()).hexdigest()[:8]
        except FileNotFoundError:
            _판캐시[파일명] = "0"
    return _판캐시[파일명]


def 판찍기(html):
    """완성된 HTML 안의 `?v=…` 를 전부 그 파일의 내용 판번호로 바꾼다.

    조립기 다섯이 저장 직전에 이것을 통과한다. 새 조립기가 이걸 안 부르면
    `check_cache_version` 이 잡는다 — 검사도 손목록이 아니라 조립기 파일을 세어서 돈다.
    """
    import re

    def 바꿈(m):
        return f'{m.group(1)}="{m.group(2)}?v={판번호(m.group(3))}"'

    # href="../report.css?v=13"  ·  src="../jachigan.js?v=9"
    return re.sub(r'\b(href|src)="(\.\./([\w.\-]+))\?v=[^"]*"', 바꿈, html)
