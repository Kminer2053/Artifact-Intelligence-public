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
                _판캐시[파일명] = hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()[:8]
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


# ── 그림 자리('26-09-30 주관 판정) ─────────────────────────────────────────────
# 장르마다 조립기가 그림(이미지 키)을 그리는 자리 — **코드가 읽는 정책은 코드에 둔다**(온톨로지 파일이
# 빠진 설치에서도 돌게 한다 — 0.3.x 배포본엔 없었다, r2/img critic_impl #9). 1p·시행문·규정은 그림 자리가 없다. 보도자료는 끝의
# '붙임 사진'만 둘 자리인데 아직 조립기에 없다. 옛 슬라이드는 레이아웃 '이미지' 장만, 판형 v2 는 아직
# 없다. 자리 밖에 온 그림 키는 조립기가 그리지 않는다 — api 새문서가 로그·확인할것으로 알린다(조용한
# 누락 금지). 시행문 관인(관인.이미지)은 그림이 아니라 도장이라 이 셈 밖이다.
그림자리 = {
    "fullreport": "장·절 안의 \"이미지\" 목록",
    "slides": "레이아웃이 '이미지'인 장의 \"이미지\"(판형 v2 는 아직 그림 자리가 없다)",
    "press": "끝의 \"붙임사진\" 목록(본문 X)",     # '26-09-30 P1 — assemble_press 가 끝에 그린다
    "samples": None,
    "gongmun": None,
    "regulation": None,
}
그림말 = {
    "press": "보도자료 본문에는 그림 자리가 없습니다(올린 사진은 끝 \"붙임사진\"에만)",
    "samples": "1페이지 보고서에는 그림 자리가 없습니다",
    "gongmun": "시행문에는 그림 자리가 없습니다(붙임으로 보내세요)",
    "regulation": "규정 본문에는 그림 자리가 없습니다(별표·별지 서식만)",
    "fullreport": "그림은 장·절 안의 \"이미지\" 목록에만 그립니다",
    "slides": "그림은 레이아웃이 '이미지'인 장에만 그립니다",
}
# 도식 자리 — 조립기가 "도식" 스펙(svgfig)을 그리는 장르. 1p·시행문·규정·보도자료 조립기는 도식을 안 그려 그 키가
# 조용히 빠졌다(보안·약한 모델 검토 W2 '26-09-29). 지시문이 장르 이름을 손으로 적지 않게 여기 둔다('26-10-01 손목록).
도식자리 = {
    "fullreport": True,
    "slides": True,
    "samples": False,
    "gongmun": False,
    "regulation": False,
    "press": False,
}


def _그림줄기(장르):
    return 장르 if 장르 in 그림정책 else _정본에서.get(장르, 장르)


def 이미지키자리있나(장르):
    """그 장르 조립기가 절·장 안의 "이미지" 키를 그리는가(풀버전·옛 슬라이드). 보도자료의 끝 "붙임사진" 은 따로다."""
    return '"이미지"' in str(그림자리.get(_그림줄기(장르)) or "")


def 도식자리있나(장르):
    """그 장르 조립기가 "도식" 키를 그리는가."""
    return bool(도식자리.get(_그림줄기(장르)))


# 장르 그림 정책('26-09-30 주관 판정) — 지시문(판정·설계·초안, 강·약)과 새문서 검사가 **이 표 하나**를 읽는다.
# 사람 말(넣는 때·넣지 않는 때)도 여기 둔다: 온톨로지 파일이 빠진 설치(0.3.x 배포본)에서는 지시문이 온톨로지 조각을
# 못 받아 그림 규칙이 통째로 빠진다(critic_impl #9). 상한은 실물 근거가 약한 **가설**이라 막지 않고 알린다.
#   공개 = 널리 공개되는 장르(보도자료·옛 판형 발표) — 비밀 표지 있는 그림을 쓰지 않고, 실리면 사람 확인 한 줄
#   생성 = 에이전트가 그림을 만들 수 있을 때 생성 요청을 가르치는 장르(옛 판형 슬라이드만, 풀버전·보도자료 X)
그림정책 = {
    "fullreport": dict(
        넣는때="현황·점검·실태·개선 결과처럼 사실을 보여 주는 절에, 올린 자료에 있는 사진(현장 개선 전·후는 두 장을 "
             "같은 절에 전→후 차례로 넣고 캡션에 '개선 전'·'개선 후')·설비·제품 예시(캡션에 '(예시)')",
        넣지않는때="로고·상징, 표 캡처(→ \"표\"로), 도식 캡처(→ \"도식\"으로), 스캔 쪽(→ 붙임), 꾸밈용 단독 사진, "
               "곁 글이 본문과 무관한 그림 — 맞는 그림이 없으면 그림 없이 쓴다",
        상한="절당 2장·문서당 6장(가설)", 공개=False, 생성=False,
        짧게="현황·점검·결과 절에 올린 사진만(전·후는 같은 절에 전→후). 로고·표·도식 캡처·스캔·꾸밈·무관한 그림은 안 넣는다",
        모양='"이미지": [{"그림": "img-…", "캡션": "그림 제목", "설명": "※ 자료에 출처 표기가 있을 때만 그 출처"}]'),
    "slides": dict(
        넣는때="레이아웃 '이미지' 장에 한 장씩 — 현장·상황·사례를 보여 주는 올린 사진",
        넣지않는때="수치·구조(→ 차트·도식 장), 로고, 표 캡처, 스캔 쪽, 비밀 표지가 있는 파일의 그림(발표는 공개된다)",
        상한="장 수의 1/4(가설)", 공개=True, 생성=True,
        짧게="'이미지' 장에 현장·사례 사진 한 장씩. 수치·구조는 차트·도식 장으로, 로고·스캔·비밀 표지 그림은 안 넣는다",
        모양='{"레이아웃": "이미지", "헤드메시지": "…", "이미지": {"그림": "img-…", "캡션": "그림 제목"}}'),
    "press": dict(
        넣는때="끝 \"붙임사진\"에만(본문 X) — 행사·현장·시설처럼 보도 내용을 보여 주는 올린 사진, 설명은 사진 아래 한 줄",
        넣지않는때="본문 안, 로고·상징, 표·도식 캡처, 스캔 쪽, 비밀 표지가 있는 파일의 그림(보도자료는 공개된다), "
               "생성 그림(사진은 증빙으로 읽힌다)",
        상한="2장(가설)", 공개=True, 생성=False,
        짧게="끝 \"붙임사진\"에만(본문 X) 올린 현장·행사 사진(설명은 사진 아래 한 줄). 로고·스캔·비밀 표지·생성 그림은 안 넣는다",
        모양='"붙임사진": [{"그림": "img-…", "캡션": "사진 아래 한 줄 설명"}]  (최상위 키, 본문 항목 안이 아니다)'),
    "samples": dict(넣는때=None, 넣지않는때="1페이지 보고서에는 그림을 넣지 않는다", 상한="0", 공개=False, 생성=False, 모양=None),
    # 붙임은 파일 이름이 아니라 '첨부물의 명칭과 수량'(행정업무운영편람 — 예: 붙임 1. 서식승인 목록 1부.) — 파일 이름에는
    # '대외비'·사람 이름이 들 수 있다('26-09-30 fixup, review_practice2 §2-4)
    "gongmun": dict(넣는때=None, 넣지않는때="시행문 본문에는 그림을 넣지 않는다 — 올린 사진은 붙임으로(사진이 무엇인지 적은 "
                                         "이름과 수량, 예: 붙임 1. 현장 사진 2부. — 파일 이름은 쓰지 않는다)",
                    상한="0", 공개=False, 생성=False, 모양=None),
    "regulation": dict(넣는때=None, 넣지않는때="규정 본문에는 그림을 넣지 않는다(별표·별지 서식만)", 상한="0",
                       공개=False, 생성=False, 모양=None),
}
_정본에서 = {"onepage-report": "samples", "press-release": "press", "fullreport": "fullreport", "gongmun": "gongmun",
          "regulation": "regulation", "slides": "slides", "onepage": "samples"}


def 그림정책값(장르, 판형=None):
    """장르(등록부 이름·내부 키·data-genre 무엇이든) → 그림 정책 dict. 판형 v2 슬라이드는 자리가 없다."""
    stem = 장르 if 장르 in 그림정책 else _정본에서.get(장르, 장르)
    값 = dict(그림정책.get(stem) or 그림정책["samples"])
    값["등록부"] = stem
    if stem == "slides" and 판형 == "v2":
        값.update(넣는때=None, 넣지않는때="판형 v2 에는 그림 자리가 없다(사진 부품은 아직 없다)", 상한="0",
                 생성=False, 모양=None)
    값["자리"] = bool(값.get("넣는때"))
    return 값


그림키이름 = ("이미지", "붙임사진")     # 붙임사진 = 보도자료 끝 사진('26-09-30)

# 상한(가설) 숫자 — 위 '상한' 사람 말과 같은 값. 막지 않고 알린다(api._그림정리 → 확인할것).
_상한수 = {"fullreport": {"절": 2, "문서": 6}, "press": {"문서": 2}, "slides": {"비율": 0.25}}


def 그림상한넘침(장르, doc):
    """[(어디, 장수, 상한)] — 문서의 그림이 장르 상한(가설)을 넘는 곳. 절 단위(풀버전)와 문서 단위."""
    stem = 장르 if 장르 in 그림정책 else _정본에서.get(장르, 장르)
    한 = _상한수.get(stem)
    if not 한 or not isinstance(doc, dict):
        return []
    경로들 = 그림키들(doc)
    out = []
    if "절" in 한:
        묶음 = {}
        for p in 경로들:
            머리 = p.rsplit(".이미지", 1)[0]
            묶음[머리] = 묶음.get(머리, 0) + 1
        out += [(머리, n, 한["절"]) for 머리, n in 묶음.items() if n > 한["절"]]
    if "문서" in 한 and len(경로들) > 한["문서"]:
        out.append(("", len(경로들), 한["문서"]))
    if "비율" in 한:
        장들 = doc.get("슬라이드") if isinstance(doc.get("슬라이드"), list) else []
        상 = max(1, int(len(장들) * 한["비율"]))
        if 장들 and len(경로들) > 상:
            out.append(("", len(경로들), 상))
    return out


def 그림키들(doc):
    """문서 JSON 안의 그림 키(이미지·붙임사진) 경로 목록 — 목록이면 원소 경로, 객체면 그 경로. 관인은 뺀다."""
    out = []

    def 걷(n, 경로):
        if isinstance(n, dict):
            for k, v in n.items():
                p = f"{경로}.{k}" if 경로 else str(k)
                if k in 그림키이름 and p != "관인.이미지" and v:
                    if isinstance(v, list):
                        out.extend(f"{p}.{i}" for i, x in enumerate(v) if x)
                    else:
                        out.append(p)
                    continue
                걷(v, p)
        elif isinstance(n, list):
            for i, v in enumerate(n):
                걷(v, f"{경로}.{i}" if 경로 else str(i))

    걷(doc, "")
    return out
