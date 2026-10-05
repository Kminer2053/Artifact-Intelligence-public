#!/usr/bin/env python3
"""이미지 자산 어댑터 — 첨부에서 잘라 쓰거나, 그림을 그릴 수 있는 에이전트가 채운 것을 쓴다.

두 경로:
  ① 추출(crop)  : 첨부 PDF·그림 파일에서 필요한 영역만 잘라 자산으로 등록('26-09-30 P1: 한글·워드 문서 속 그림은
                꺼내 쓰지 않는다 — '문서 속 사진' 카드로 세어, 문서를 PDF로 저장해 함께 올리거나 사진 파일로 올려 달라고
                알린다. PDF 는 보는 사람에게 보이는 자리(CropBox·/Rotate)만 자른다 — Q1)
                한계(N3, '26-09-30 판정 — 문서화): PDF 의 보이지 않는 글(흰 글·렌더 모드 3 투명 글)은 그림 곁 글·비밀 표지로
                오를 수 있다(꺼진 층 글은 빠진다). 스캔 PDF 의 OCR 글층도 투명 글이라 가려 막지 않는다.
  ② 생성(generate): host 하나 — 실행 중인 에이전트가 그림을 그릴 수 있다고 밝혔을 때만(이미지능력 작업).
                요청(id = 프롬프트 해시)을 manifest에 적고, 에이전트가 이미지채움으로 넣은 그림을 쓴다.
                ('26-09-30) 서버·외부 키 생성(ima2·openai·gemini)은 걷었다(providers 주석).
  못 얻은 그림은 산출물(PDF·HWPX·PPTX·MD)에 빈 자리표시를 남기지 않는다 — render 가 자리를 차지하지
  않는 표식(hidden·data-miss)만 두고, 편집기만 그 표식을 검토 표지로 보여 준다.

공공보고서 가드(온톨로지 data_elements.시각자료.생성_수단):
  사실을 주장하는 도해(조직도·절차도·통계), 기관 상징, 실제 사람·기관·행사를 사진처럼 만든 그림은
  생성 금지 — 앞의 것은 없는 부서·틀린 숫자를 그럴듯하게 그리고, 뒤의 것은 증빙으로 오인된다.
  그런 요청은 거부하고 SVG 도식(build/svgfig.py) 또는 첨부 크롭으로 유도한다.

사용:
  python3 build/imageasset.py --check                 # 쓸 수 있는 수단 점검
  python3 build/imageasset.py --훑기                   # 받은 자료 폴더에서 꺼낼 수 있는 것
  python3 build/imageasset.py --들여다보기 <파일>
  python3 build/imageasset.py --spec assets/spec.json # 스펙 배열 처리
"""
import html as _html
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:    # api 가 자료뿌리.모듈("imageasset") 로 부를 때도(build/ 가 sys.path 에 없을 때) 선다
    sys.path.insert(0, BASE)
import 자료뿌리  # noqa: E402
# 이미지 자산·명세는 **자료**다(사용자가 올린 첨부에서 잘라 낸 것) — 뿌리는
# build/자료뿌리.py 가 정한다(WP-S2 ①). 상대 경로의 기준도 코드뿌리가 아니라
# 자료뿌리의 build/ 다. 안 그러면 다른 뿌리에서 자산이 코드뿌리에 쌓인다.
#
# ★ 뿌리를 **호출마다** 다시 푼다(2026-08-09, ③ 고침 — WP-S9 의 OUT 얼림과 같은 부류).
# 전에는 모듈 적재 때 `ASSETS = 자료뿌리.자산뿌리()`(과 자료빌드·MANIFEST)를 상수로 얼렸다.
# subprocess 로 부를 땐 조립마다 새 프로세스라 매번 새로 풀렸지만, api.py 가 조립기를
# **import 로** 부르면 모듈이 딱 한 번 적재되며 ASSETS 가 **첫 세션 뿌리(대개 코드뿌리)에
# 얼어붙어**, 세션이 만든 도식/이미지 PNG 가 세션 뿌리가 아니라 공용 build/assets 로 샜다
# (세션 내용이 공용 자리에 남음 = 격리·프라이버시 결함, S9 의 OUT 과 판박이). 그래서 상수를
# 없애고 쓰는 함수마다 **머리에서 다시 푼다**(assemble*.py 의 조립하기 가 산출물뿌리 를
# 호출마다 푸는 것과 같은 손). 세션이 없으면 자산뿌리()=코드뿌리라 정본 출력은 글자 하나
# 안 달라진다(대조 38/38 무변). — 상수를 되살리면 verify_all 의 check_imageasset_not_frozen
# 이 잡는다.
def _자산뿌리():
    return 자료뿌리.자산뿌리()


def _명세길():
    return os.path.join(_자산뿌리(), "manifest.json")


def _자료빌드():
    return 자료뿌리.길("build")

# 생성 금지 유형 — 프롬프트에 이 신호가 있으면 거부하고 대안을 제시한다.
# 사실을 주장하는 도해·차트, 기관 상징, 실제 사람·기관·행사를 사진처럼 만든 그림을 막는다.
# 상황 설명·예시 삽화는 허용하되 render 가 'AI 생성물' 표기를 강제한다.
# ('26-09-30 정밀화) 전에는 re.I 로 'CI' 를 찾아 facility·technician·city·social 의 ci 에 걸려
# 영어 프롬프트가 거의 다 '기관 상징'으로 거부됐고(r2/img probe §3-4·map_rules §6), '막대' 가
# '막대한'에, '흐름도'만 막아 '흐름을 보여 주는 그림'·'체계 인포그래픽'은 빠져나갔다. 영어 낱말은
# 낱말 경계로만, 'CI' 는 대문자 그대로 앞뒤에 로마자가 없을 때만 본다. 회귀 표본 문장은
# test/r26_img26.py 에 있다.
# ('26-09-30 fixup) 표본 밖 문장이 모두 빠져나갔다(r2/img review_practice2 §2-7) — 배치도·노선도·위치도·약도·조감도·
# 구성도·관계도·평면도·일정표(그림), map·timeline·floor plan 을 도해에 더한다. '지도'는 행정지도·지도점검과 겹쳐
# 그림말이 붙을 때만 본다.
_도해 = re.compile(
    r"조직도|기구표|절차도|흐름도|순서도|플로우\s*차트|구조도|체계도|다이어그램|인포그래픽|로드맵"
    r"|(?:배치|구성|관계|노선|위치|평면|계통|공정|배관|설비|안내)도(?![가-힣])|약도|조감도|투시도|일정표|연표|타임라인"
    r"|(?<![가-힣])지도\s*(?:를|로|에|가|이)?\s*(?:그림|이미지|삽화|일러스트|그려)"
    r"|(?:흐름|체계|구조|배치|절차|구성|단계|관계|일정)(?:을|를|이|가|와|과)?\s*(?:한눈에\s*)?(?:보여|나타내|정리해|그림으로)"
    r"|(?i:\b(?:organi[sz]ation(?:al)?\s+charts?|org\s+charts?|flow\s*charts?|diagrams?|infographics?|roadmaps?"
    r"|maps?|timelines?|floor\s*plans?|site\s*plans?|layouts?|schematics?)\b)")
_차트 = re.compile(
    r"그래프|차트|막대\s*(?:그래프|차트|도표)|꺾은선|추이|통계|도표"
    r"|(?i:\b(?:charts?|graphs?|statistics|histograms?)\b)")
_상징 = re.compile(
    r"로고|엠블럼|엠블렘|휘장|정부\s*상징|심[벌볼]\s*마크|(?<![A-Za-z])CI(?![A-Za-z])"
    r"|(?i:\b(?:logos?|emblems?|insignias?)\b)")
# 실제 사람·기관 — 직함 뒤에 주격이 오거나(○○공사 사장이…), 본사·청사 같은 실제 건물.
# 직함 앞에 한글이 붙으면 다른 낱말(전통시장·도매시장·○○지사 사무실)이라 보지 않는다(정밀도 우선).
_직함 = (r"(?:(?<![가-힣])|(?<=○))(?:대통령|국무총리|총리|장관|차관|청장|처장|시장|도지사|군수|구청장|의장|의원"
       r"|사장|부사장|이사장|원장|본부장|위원장|총장|교육감)(?:님)?(?:이|가|은|는|께서)(?![가-힣])"
       r"|(?i:\b(?:president|prime\s+minister|minister|mayor|governor|ceo|chairman)\b)")
_실제건물 = r"본사|청사|사옥|본관"
_사진말 = re.compile(r"사진|실사|실물|촬영|(?i:\bphoto(?:graph)?s?\b|\bphotorealistic\b|\brealistic\b)")
# 행사 — 직함 바로 뒤에 조사가 없어도('장관님 격려'·'사장 취임식'·'국무총리 방문') 행사말과 30자 안에 함께 오면 본다
# ('26-09-30 fixup, review_impl2 L1·review_practice2 §2-7 — 거부 가드는 놓침이 더 비싸다). '시장'은 전통시장·시장 방문
# (장보기)과 겹쳐 조사(이·가·과·와…)가 붙을 때만 _직함 으로 본다.
_직함맨 = (r"(?:(?<![가-힣])|(?<=○))(?:대통령|국무총리|총리|장관|차관|청장|처장|도지사|군수|구청장|국회의원|의장"
         r"|사장|부사장|이사장|원장|본부장|위원장|총장|교육감)(?:님)?")
_직함조사 = r"(?:(?<![가-힣])|(?<=○))시장(?:님)?(?:이|가|은|는|께서|과|와|의)(?![가-힣])"
_행사낱말 = r"(?:방문|참석|시찰|연설|격려|주재|악수|기념\s*촬영|기념\s*사진|인사말|현장\s*점검|취임|간담|면담|인터뷰|환담|순시|표창|수여)"
_행사말 = re.compile(r"(?:" + _직함 + "|" + _직함맨 + "|" + _직함조사 + r").{0,30}?" + _행사낱말
                   + r"|(?:" + _실제건물 + r").{0,20}?(?:행사|기념식|준공식|개소식|개청식|기념\s*촬영)"
                   # 사람 이름(한글 세 자)+직급 — '홍길동 과장 인터뷰'. 세 자 팀 이름('시설팀 과장')도 걸리지만 거부는 싸다
                   + r"|(?<![가-힣])[가-힣]{3}\s?(?:과장|부장|팀장|차장|국장|실장|주무관|사무관|서기관|대리|주임)(?:님)?"
                     r"(?:이|가|은|는|의)?\s.{0,20}?" + _행사낱말
                   + r"|(?i:\b(?:president|minister|mayor|governor|ceo|chairman)\b.{0,40}?"
                     r"\b(?:visit|attend|speech|tour|shak\w*\s+hands?|handshake|ceremony|inaugurat)\w*)")
_실존 = re.compile(_직함 + "|" + _실제건물)

FORBID = [
    (_도해, "사실 관계를 주장하는 도해(조직·체계·흐름·배치) — 생성 이미지는 검증할 수 없다. build/svgfig.py 도식으로 그릴 것"),
    (_차트, "수치를 주장하는 차트 — 생성 이미지는 숫자를 지어낸다. 데이터로 SVG 차트를 그릴 것"),
    (_상징, "기관 상징은 생성 대상이 아니다 — 공식 파일을 첨부로 넣을 것"),
]
_실존말 = "실제 사람·기관·행사를 사진처럼 만든 그림은 실물·증빙으로 오인된다 — 올린 사진을 쓰거나 그림 없이 둘 것"


def _ok(name):
    return subprocess.run(["command", "-v", name], shell=False, capture_output=True).returncode == 0


def providers():
    """사용 가능한 생성 제공자 점검.

    ('26-09-30 주관 판정) 생성은 **그림을 그릴 수 있는 에이전트가 스스로 밝힐 때만** 한다(host).
    웹앱 서버 생성(ima2·openai 호환·gemini)은 껐다 — 서버 한 곳의 키로 모든 사용자 그림을 만들고,
    플러그인에서는 사용자 셸의 OPENAI_API_KEY 가 있으면 문서 내용에서 나온 프롬프트가 조용히 밖으로
    나갔다('자료는 이 컴퓨터를 떠나지 않는다'와 어긋남, r2/img map_code #12). 스펙의 "제공자" 도 안 읽는다.
    ('26-09-30 P2) 켜는 길은 환경변수(IMAGEGEN_HOST)가 아니라 에이전트가 부르는 작업(이미지능력 → 능력()) 이다 —
    떠 있는 MCP 서버의 환경은 에이전트가 바꿀 수 없다(r2/img map_agents E1)."""
    # 웹앱 서버(문서지능_웹앱)는 host 도 없다 — 서버에는 그림을 채울 에이전트가 없다(능력() 이 늘 None)
    return {"host": bool(능력())}


def guard(prompt):
    """생성 요청 사전 검사 — 부적합이면 사유를 반환."""
    p = str(prompt or "")
    for pat, why in FORBID:
        if pat.search(p):
            return why
    if _행사말.search(p) or (_사진말.search(p) and _실존.search(p)):
        return _실존말
    return None


# 프롬프트 가드레일 — 문서 모델이 쓴 프롬프트에 **스타일을 덧대** 톤을 일정하게 만든다.
# 모델 재량에만 맡기면 이미지 모델이 제멋대로 실사화한다. 평면·비실사·**글자 없음**으로 고정한다
# (그림 속 한글은 흩어진다 — 실측 '26-09-02 "문서지능"→"문누지앙". 전에는 "라벨 또렷하게"를 붙여
# 글자 억제와 서로 반대 지시가 한 프롬프트에 들었다, r2/img map_code ⑦). IMAGE_STYLE 로 통째 바꿀
# 수 있다(빈 값이면 안 덧댐). ('26-09-30) 실사 모드("실사":true → 사진처럼 사실적)는 없앴다 —
# 공공문서에서 사진은 증빙으로 읽혀, 사진처럼 보이는 가상 장면은 표기를 달아도 위조로 읽힐 수 있다.
_기본스타일 = ("평면 벡터 아이소메트릭 일러스트, 밝고 깔끔한 단색 면, 그림 안에 글자·숫자·로고 없음, "
            "여백 넉넉히, 공공 보고서 삽화 톤. flat isometric vector illustration, clean flat colors, "
            "no text, no letters, no numbers, no logos, generous whitespace, no photorealism, not a photo")


def _스타일적용(prompt):
    s = os.environ.get("IMAGE_STYLE", _기본스타일)
    return f"{prompt}\n[스타일] {s}" if s.strip() else prompt


# ── ① 추출(crop) ──────────────────────────────────────────────────────────

def _pdf_page_png(src, page, dpi, out_prefix):
    # -cropbox('26-09-30 주관 판정 Q1) — 보는 사람에게 보이는 자리(CropBox)만 그린다. 전에는 MediaBox 전체를 그려, 작성자가 쪽
    # 자르기(Acrobat '페이지 자르기' — CropBox 만 줄이고 내용은 남긴다)로 가린 바깥이 그림 카드에 실렸다(verify_fixup4 B1).
    # /Rotate 는 pdftoppm 이 늘 반영한다(돌린 쪽은 보는 사람 방향으로 그린다).
    subprocess.run(["pdftoppm", "-cropbox", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
                    src, out_prefix], check=True, capture_output=True)
    for suf in (f"-{page}.png", f"-{page:02d}.png", f"-{page:03d}.png", ".png"):
        cand = out_prefix + suf
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(f"pdftoppm 산출 없음: {out_prefix}")


class 원본거절(ValueError):
    """그림 원본을 세션 밖에서 찾으라는 요청 — 문서에는 사람 말만 싣는다."""


class id필요(원본거절):
    """옛 꼴(파일·쪽·index)로 가리킨 그림을 싣지 않는다 — 올린 PDF 는 그림 목록 id 로만 풀고, 한글·워드 문서(HWP·HWPX·DOCX)
    속 그림은 아예 쓰지 않는다('26-09-30 P1)."""


_문서사진거절말 = "한글·워드 문서 속 사진은 쓰지 않습니다 — 문서를 PDF로 저장해 함께 올리거나 사진 파일로 올려 주세요"


def _올린이름꼴(이름):
    """웹앱 올리기(workspace/api.py 올리기)가 저장 이름을 짓는 규칙 — 확장자 12자, 앞부분 60바이트.
    모델은 **표시 이름**(사용자가 올린 원래 이름)만 안다. 긴 이름은 저장할 때 잘려 이름만으로는 못
    찾았다. 같은 규칙으로 다시 지어 보면 정확히 그 파일이다(겹쳐서 붙는 '-1' 은 어느 것인지 몰라 안 고른다).
    규칙이 갈리지 않게 test/r26_img26.py 가 두 곳을 맞대 본다."""
    뿌리, 끝 = os.path.splitext(이름)
    끝 = 끝[:12]
    _b = 뿌리.encode("utf-8")
    if len(_b) > 60:
        뿌리 = _b[:60].decode("utf-8", "ignore").rstrip() or "file"
    return 뿌리 + 끝


def _이름후보(파일):
    """이름만 적힌 원본 — 받은 자료 폴더에서 **정확히 하나로** 정해지는 꼴만 더 본다(정밀도 우선).
    ① 자료 머리처럼 대괄호로 싼 이름 '[현장점검.pdf]' ② 한글 자모 조합꼴 차이(NFC·NFD — 맥에서 올린
    파일 이름은 NFD 로 올 수 있고 모델은 NFC 로 쓴다) ③ 올리기가 잘라 저장한 긴 이름."""
    import unicodedata
    이름 = 파일.strip()
    if len(이름) > 2 and 이름[0] == "[" and 이름[-1] == "]":
        이름 = 이름[1:-1].strip()
    꼴들 = []
    for n in (이름, _올린이름꼴(이름)):
        for f in ("NFC", "NFD"):
            v = unicodedata.normalize(f, n)
            if v not in 꼴들:
                꼴들.append(v)
    return 꼴들


def 원본길(파일):
    """그림 원본 경로를 이 세션 안으로 가둔다('26-09-29 보안).

    전에는 스펙의 "파일"을 그대로 열었다 — '../../<다른 세션>/workspace/inbox/…'·절대경로로
    다른 사용자가 올린 파일이나 서버의 아무 PDF·그림을 내 문서에 끌어올 수 있었다(웹앱
    HTTP 로도 재현, r2/img/critic_impl.md §1). 파일읽기는 받은 자료 폴더에 가두는데 여기는
    안 가뒀다. 허용하는 곳은 받은 자료 폴더와 이 세션 자료 build/ 둘뿐이고, 심볼릭 링크까지
    풀어(realpath) 본다. 이름만 적으면 받은 자료 폴더에서 먼저 찾는다 — 모델은 올린 파일
    이름만 알기 때문이다(전에는 build/ 에서만 찾아 이름만 준 크롭이 모두 실패했다).
    이름만 적힌 것은 대괄호·자모 조합꼴·잘린 저장 이름까지 본다(_이름후보, '26-09-30)."""
    if not isinstance(파일, str) or not 파일.strip():
        raise 원본거절("그림 원본이 적혀 있지 않습니다")
    받은 = 자료뿌리.받은것뿌리()
    빌드 = _자료빌드()
    뿌리들 = [os.path.realpath(받은), os.path.realpath(빌드)]
    if os.path.isabs(파일):
        후보 = [파일]
    else:
        후보 = [os.path.join(받은, 파일), os.path.join(빌드, 파일)]
        if os.path.basename(파일) == 파일.strip() and not 파일.strip().startswith("."):
            후보 += [os.path.join(받은, n) for n in _이름후보(파일)]
    for c in 후보:
        r = os.path.realpath(c)
        if any(r.startswith(b + os.sep) for b in 뿌리들) and os.path.isfile(r):
            return r
    raise 원본거절("올린 자료에서 그 그림을 찾지 못했습니다")


def _원본표기(파일):
    """편집기로 싣는 스펙의 "파일"을 세션 안 상대 이름으로 — 절대경로에는 세션 열쇠가 들어 있다."""
    try:
        r = 원본길(파일)
    except Exception:
        # 못 찾은 것은 파일 이름만 남긴다 — 폴더 부분(남의 세션 열쇠·서버 경로)은 싣지 않는다
        return os.path.basename(파일) if isinstance(파일, str) else ""
    받은 = os.path.realpath(자료뿌리.받은것뿌리())
    if r.startswith(받은 + os.sep):
        return os.path.relpath(r, 받은)
    return os.path.relpath(r, os.path.realpath(_자료빌드()))


class 도구없음(RuntimeError):
    """그림을 자를 도구(Pillow)가 이 파이썬에도, 넘겨 보낼 build/.hwpxenv 에도 없다."""


def _그림파이썬():
    """Pillow 가 있는 파이썬 — 플러그인 MCP 서버(mcp/.venv)에는 없을 수 있어 build/.hwpxenv 로 넘긴다
    (tohwpx·topptx 가 .hwpxenv 로 넘기는 것과 같은 길). 없으면 None."""
    for p in (os.path.join(BASE, ".hwpxenv", "bin", "python3"), os.path.join(BASE, ".hwpxenv", "bin", "python")):
        if os.path.exists(p):
            return p
    return None


def _위임추출(spec, name):
    """Pillow 없는 파이썬에서 부른 extract — .hwpxenv 파이썬으로 같은 일을 시킨다. 세션은 자식환경으로
    물려주고(가두기는 자식이 똑같이 한다), 결과 경로가 이 세션 자산 폴더 안인지 다시 본다."""
    py = _그림파이썬()
    if not py or os.environ.get("문서지능_그림위임") == "1":
        raise 도구없음("그림을 자르는 도구(Pillow)가 없습니다 — bin/bootstrap.sh 를 다시 실행해 주세요")
    env = 자료뿌리.자식환경()
    env["문서지능_그림위임"] = "1"
    r = subprocess.run([py, os.path.abspath(__file__), "--추출"],
                       input=json.dumps({"spec": spec, "name": name}, ensure_ascii=False),
                       capture_output=True, text=True, timeout=180, env=env)
    try:
        값 = json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        raise RuntimeError(f"그림 위임 실패(rc={r.returncode})")
    if 값.get("ok"):
        경로 = os.path.realpath(값["경로"])
        if not 경로.startswith(os.path.realpath(_자산뿌리()) + os.sep):
            raise 원본거절("그림을 이 세션 밖에 만들었습니다")
        return 경로
    종류 = 값.get("종류")
    if 종류 == "id필요":
        raise id필요(값.get("말") or "문서 파일 속 그림은 그림 목록 id 로 골라 주세요")
    if 종류 == "원본거절":
        raise 원본거절(값.get("말") or "올린 자료에서 그 그림을 찾지 못했습니다")
    if 종류 == "도구없음":
        raise 도구없음(값.get("말") or "그림을 자르는 도구가 없습니다")
    raise RuntimeError(f"그림 위임 실패: {종류}")


def extract(spec, name):
    """첨부에서 영역을 잘라 assets/<name>.png 로 저장하고 경로를 반환.

    크롭 좌표는 비율(0~1) 또는 픽셀. 비율이면 렌더 크기에 맞춰 환산한다.
    PDF 도식은 한글에서 벡터로 나가 pdfimages에 안 잡히므로 '페이지 렌더 후 크롭'이 정석.
    늘 PIL 로 다시 써서(PNG) EXIF·GPS 같은 메타데이터가 산출물로 따라가지 않는다.
    """
    try:
        from PIL import Image
    except ImportError:
        return _위임추출(spec, name)
    ASSETS = _자산뿌리()   # 호출마다 세션 뿌리를 다시 푼다(③)
    os.makedirs(ASSETS, exist_ok=True)
    카드길 = False
    if spec.get("그림"):
        # 목록 카드 id('26-09-30) — 경로·경계·자르기는 카드를 만들 때 이미 풀었다. 모델 좌표(자를곳·쪽·index)는
        # 읽지 않고, 편집기 자르기(크롭 — 보이는 그림 기준 비율)만 적용한다.
        카 = 그림찾기(spec.get("그림"))
        if 카 and 문서파일인가(카.get("파일")):
            # 옛 목록(판 3 이하)에 남은 한글·워드 문서 카드 — 목록을 다시 만들기 전에도 싣지 않는다(P1)
            raise id필요(_문서사진거절말)
        if not 카 or not 카.get("그림파일"):
            raise 원본거절("올린 자료 그림 목록에 그 그림이 없습니다")
        spec = {"파일": 카["그림파일"], "크롭": spec.get("크롭")}
        카드길 = True
    src = 원본길(spec.get("파일"))   # 세션 밖은 거절(보안) — 이름만 주면 받은 자료 폴더에서 찾는다
    _받은 = os.path.realpath(자료뿌리.받은것뿌리())
    if not 카드길 and src.startswith(_받은 + os.sep) and os.path.dirname(src) != _받은:
        # 받은 자료 **하위 폴더**의 파일(_그림/ 의 카드 그림·옛 판 파일, 에이전트가 문서를 풀어 둔 word/media·BinData, kordoc 이
        # 풀다 남긴 것)은 옛 꼴 경로로 싣지 않는다 — 카드 id 로만('26-09-30 Q6, verify_fixup4 N1·N2). 웹앱 올리기는 하위 폴더를
        # 만들지 않는다(이름만 받는다). 받은 자료 바로 아래의 그림 파일 옛 꼴은 전과 같다.
        raise id필요("받은 자료 하위 폴더의 그림은 그림 목록 id 로 골라 주세요")
    _빌드 = os.path.realpath(_자료빌드())
    if not 카드길 and src.startswith(_빌드 + os.sep) and not src.lower().endswith(".pdf"):
        # 이 세션 build/ 의 그림 파일도 옛 꼴 경로로 싣지 않는다 — 카드 id 로만('26-10-01 주관 판정 R6, verify_fixup5 N3: 에이전트가
        # 문서를 풀어 꺼낸 원본을 build/ 에 두면 카드 없이 실렸다). 서비스가 만든 표본 PDF(build/samples 의 쪽 렌더)는 전과 같다.
        raise id필요("그림은 그림 목록 id 로 골라 주세요")
    if 문서파일인가(src):
        # 옛 꼴("파일"+"index") HWPX·DOCX·HWP — 그릇 속 원본은 화면에 보이는 모습과 다를 수 있어(가림·자르기·숨김·지운 변경)
        # 한글·워드 문서의 그림은 쓰지 않는다('26-09-30 주관 판정 P1). 새문서·저장·편집기 저장이 모두 여기를 지나므로 입구가
        # 아니라 이 자리에서 막는다(표식 id필요 — 편집기에서 다른 그림으로 바꾸거나 자리를 지운다).
        raise id필요(_문서사진거절말)
    elif src.lower().endswith(".pdf") and os.path.realpath(src).startswith(os.path.realpath(자료뿌리.받은것뿌리()) + os.sep):
        # 옛 꼴("파일"+"쪽") **올린** PDF — 쪽을 통째로 렌더하면 목록이 뺀 쪽(스캔·도장·서명)이 그대로 실렸다(verify_fixup2 N2:
        # 카드 '스캔 쪽 · 쓰지 않음'인데 새문서·저장이 쪽을 싣고, 자를곳으로 도장 자리만 잘라 실었다). 카드로만 푼다 — 그 파일
        # (쪽을 적었으면 그 쪽)의 쓸 그림이 정확히 하나면 그 카드, 아니면 거절. 쪽 기준 자를곳은 카드 그림에 맞지 않아 버리고
        # 편집기 자르기(크롭, 보이는 그림 기준)만 둔다. 이 세션 build/ 의 PDF(서비스가 만든 표본)는 전처럼 쪽을 렌더한다.
        이름 = os.path.basename(src)
        목 = 카드들(갱신=False)
        if not any(c.get("파일") == 이름 for c in 목):
            목 = 카드들()          # 목록을 아직 안 만든 흐름(CLI 등) — 바뀐 파일만 새로 만든다
        try:
            쪽 = None if spec.get("쪽") is None else int(float(spec.get("쪽")))
        except (TypeError, ValueError):
            쪽 = -1               # 읽히지 않는 쪽 — 어느 카드와도 맞지 않는다(거절)
        쓸 = [c for c in 목 if c.get("파일") == 이름 and c.get("쓸수있음") and c.get("그림파일")
             and (쪽 is None or (c.get("자리") or {}).get("쪽") == 쪽)]
        if len(쓸) != 1:
            raise id필요("문서 파일 속 그림은 그림 목록 id 로 골라 주세요")
        spec = {"파일": 쓸[0]["그림파일"], "크롭": spec.get("크롭")}
        src = 원본길(spec["파일"])
    # dpi 는 스펙 값이 곧바로 pdftoppm -r 로 간다 — 72~300 으로 자른다(큰 값 하나로 서버가 멈추지 않게)
    try:
        dpi = int(float(spec.get("dpi", 300)))
    except (TypeError, ValueError):
        dpi = 300
    dpi = min(300, max(72, dpi))
    out = os.path.join(ASSETS, f"{name}.png")
    try:
        if src.lower().endswith(".pdf"):
            try:
                쪽 = max(1, int(float(spec.get("쪽", 1))))
            except (TypeError, ValueError):
                쪽 = 1
            img_path = _pdf_page_png(src, 쪽, dpi, os.path.join(ASSETS, f"_{name}_pg"))
        else:
            img_path = src

        Image.MAX_IMAGE_PIXELS = _채움최대화소
        im = Image.open(img_path)
        im.load()
        # 모델은 shape 가 시키는 대로 자를곳{x,y,w,h}(딕셔너리)를 낸다 — 리스트[x,y,w,h]로 정규화한다.
        # (엔진이 크롭[리스트]만 읽어 자를곳을 놓쳐 크롭이 조용히 실패, 첨부 PDF 전체페이지가
        #  삽입되던 것 봉합, 2026-08-13 실측. 크롭[리스트]·E-12 하위호환 유지.)
        box = spec.get("크롭") or spec.get("자를곳")
        if isinstance(box, dict):
            box = [box.get("x", 0), box.get("y", 0), box.get("w", 0), box.get("h", 0)]
        상자 = None
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                x, y, w, h = (float(v) for v in box)
            except (TypeError, ValueError):
                x = y = w = h = 0.0
            if max(x, y, w, h) <= 1.0:                       # 비율 좌표
                x, y, w, h = x * im.width, y * im.height, w * im.width, h * im.height
            # 그림 경계 안으로 자른다 — 전에는 600×400 카드에 [0,0,3000,3000] 을 주면 3000×3000 새 그림을 잡았다(웹앱
            # 저장 한 번으로 서버 메모리를 수 GB 잡게 하는 길, review_impl2 M3). 폭·높이가 0 이하면 자르지 않는다.
            l, t = max(0, min(im.width, int(x))), max(0, min(im.height, int(y)))
            r, b = max(0, min(im.width, int(x + w))), max(0, min(im.height, int(y + h)))
            if r - l >= 1 and b - t >= 1:
                상자 = (l, t, r, b)
        if 상자:
            im = im.crop(상자)
        # 새 그림으로 옮겨 쓴다 — EXIF 는 물론 ICC 프로필(기기 이름이 들 수 있다)도 따라가지 않게(review_practice2 N14)
        _정규화(im).save(out, "PNG")
    finally:
        # 임시 쪽 렌더·꺼낸 원본은 실패해도 지운다 — 전에는 예외가 나면 assets 에 남았다(critic_impl #2)
        for tmp in (f"_{name}_pg", f"_{name}_bin"):
            for f in os.listdir(ASSETS):
                if f.startswith(tmp):
                    os.remove(os.path.join(ASSETS, f))
    return out


# ── 첨부에 무엇이 들었나 ─────────────────────────────────────────────────
# extract() 는 만들어져 있었지만 아무도 부르지 않았다 — 받은 자료 폴더에 PDF를 넣어도
# 그 안의 그림을 쓸 길이 없었다. 먼저 '무엇을 꺼낼 수 있는지' 보는 길을 낸다.

def 들여다보기(src, 미리보기=True):
    """첨부 하나에서 꺼낼 수 있는 것을 목록으로 낸다.

    PDF는 쪽마다 미리보기를 만들고, HWPX는 안에 든 그림을 센다.
    미리보기를 만들어 두면 사용자가 눈으로 보고 고를 수 있다.
    """
    ASSETS, 자료빌드 = _자산뿌리(), _자료빌드()   # 호출마다 세션 뿌리를 다시 푼다(③)
    try:
        src = 원본길(src)     # extract 와 같은 가두기 — 받은 자료 폴더·이 세션 build/ 밖은 안 연다
    except 원본거절 as exc:
        return {"파일": os.path.basename(str(src)), "_실패": str(exc)}
    _받은 = os.path.realpath(자료뿌리.받은것뿌리())
    if src.startswith(_받은 + os.sep) and os.path.dirname(src) != _받은:
        # 받은 자료 하위 폴더(_그림/·풀어 둔 문서 속)는 들여다보지 않는다 — extract 와 같은 규칙(N1)
        return {"파일": os.path.basename(src), "_실패": "받은 자료 하위 폴더의 파일은 살피지 않습니다"}
    이름 = os.path.splitext(os.path.basename(src))[0]
    low = src.lower()
    out = {"파일": os.path.relpath(src, 자료빌드), "이름": 이름}

    if low.endswith(".pdf"):
        if not _ok("pdfinfo"):
            out["_실패"] = "pdfinfo 가 없어 PDF를 못 엽니다"
            return out
        r = subprocess.run(["pdfinfo", src], capture_output=True, text=True)
        m = re.search(r"Pages:\s*(\d+)", r.stdout)
        n = int(m.group(1)) if m else 0
        out["종류"] = "PDF"
        out["쪽수"] = n
        out["꺼낼수있는것"] = [{"쪽": i, "설명": f"{i}쪽 전체"} for i in range(1, n + 1)]
        if 미리보기 and n:
            os.makedirs(os.path.join(ASSETS, "_preview"), exist_ok=True)
            for i in range(1, min(n, 12) + 1):
                try:
                    png = _pdf_page_png(src, i, 72,
                                        os.path.join(ASSETS, "_preview", f"{이름}-p{i}"))
                    out["꺼낼수있는것"][i - 1]["미리보기"] = os.path.relpath(png, 자료빌드)
                except Exception as exc:
                    out["꺼낼수있는것"][i - 1]["_실패"] = str(exc)[:60]
        return out

    if 문서파일인가(src):
        # 한글·워드 문서 속 그림은 꺼내 쓰지 않는다('26-09-30 P1) — 옛 index 목록을 내주지 않는다(파일 머리로도 가린다, N4)
        out["종류"] = "한글·워드 문서"
        out["꺼낼수있는것"] = []
        out["안내"] = _문서사진거절말
        return out

    if re.search(r"\.(png|jpe?g|gif|webp|bmp|tiff?)$", low):
        out["종류"] = "그림 파일"
        try:
            from PIL import Image
            im = Image.open(src)
            out["크기"] = f"{im.width}×{im.height}"
        except Exception:
            pass
        out["꺼낼수있는것"] = [{"설명": "그림 전체"}]
        return out

    out["종류"] = "그림을 꺼낼 수 없는 형식"
    out["꺼낼수있는것"] = []
    return out


def 폴더훑기(폴더=None, 미리보기=True):
    """받은 자료 폴더를 통째로 훑는다."""
    폴더 = 폴더 or 자료뿌리.받은것뿌리()
    if not os.path.isdir(폴더):
        return []
    out = []
    for f in sorted(os.listdir(폴더)):
        full = os.path.join(폴더, f)
        if not os.path.isfile(full) or f.startswith(".") or f == "README.md":
            continue
        out.append(들여다보기(full, 미리보기))
    return out


# ── ③ 첨부 그림 목록 카드('26-09-30 주관 판정) ─────────────────────────────
# 모델은 첨부 속 그림을 모른 채 경로·쪽·좌표를 짐작해 썼다 — 9개 시나리오에서 맞게 들어간 그림 0건
# (r2/img probe §0: 좌표 눈대중으로 머리띠가 끼고, HWPX 는 로고가 '개선 후' 자리에 들어갔다). 이제 시스템이
# 첨부에서 그림을 먼저 꺼내 받은 자료 폴더 아래 _그림/ 에 두고 카드를 만든다. 모델은 "그림":"img-…" id 만
# 쓰고, 경로·경계·해상도는 여기서 푼다(좌표 키 자를곳·크롭은 모델에게서 없앤다 — 편집기 자르기만 크롭을 쓴다).
#   · PDF  : 쪽을 pdftoppm 으로 렌더한 뒤 박힌 그림 경계(PyMuPDF get_image_info)로 자른다. 원본을 떼어 내면
#            작성자가 잘라 둔 바깥·도형으로 가린 자리가 되살아난다(critic_practice X2·X3). 스캔 쪽은 후보가 아니다.
#   · HWP·HWPX·DOCX : 그림을 꺼내지 않는다('26-09-30 주관 판정 P1, fixup4) — 그림 자리를 세어 '문서 속 사진' 카드(id·그림
#            파일 없음)로만 적는다. 그릇 속 원본은 화면에 보이는 모습(가림·자르기·숨김·지운 변경)과 다를 수 있다(아래 §문서 속 그림).
#   · 그림 파일: 통째. XLSX·PPTX 는 하지 않는다.
#   모두 PIL 로 새 그림을 만들어 PNG 로 쓴다 — EXIF·GPS·XMP 가 따라가지 않고, 투명·CMYK·JPEG2000 은 흰 바탕 RGB 로 편다.
# id 는 그림 내용 해시에서 짓는다(img-<6자리>) — 첨부를 더 올리거나 다시 읽어도 이미 쓴 id 가 다른 그림에
# 붙지 않는다(critic_impl #3). 같은 그림이 여러 파일에 있으면 한 카드로 묶고, 거의 같은 그림(JPEG·PNG 로 따로
# 저장된 같은 사진)은 '같은 그림' 으로 서로 가리킨다. 카드는 세션 방(받은 자료) 안에만 산다.
_그림폴더명 = "_그림"
_카드판 = 5          # ('26-09-30 fixup5) PDF 는 CropBox·/Rotate 로 자르고, 문서 속 그림은 거절 해시·글지문을 둔다(Q1·Q2·Q4)
#                     (4: 한글·워드 문서 속 그림을 꺼내지 않는다(P1), 3: 허용 목록, 2: 스캔·가림·비밀 표지) — 옛 목록은 다시 만든다
_작은mm = 12        # 이보다 작게 놓인 그림(글머리 아이콘·장식)은 목록에서 뺀다
_작은px = 48
# 32×32 RGB 평균 차 — 같은 사진 PNG·JPEG 0.45, 개선 전·후 2.75(합성 표본 실측). ('26-09-30 fixup) 1.0 에서 0.6 으로 —
# 사람 자리를 모자이크하고 번호판을 검게 덮은 사본(0.853)과 넓이 0.6% 만 다른 연속 사진이 '같은 그림'으로 묶여 약한
# 카드에서 숨었다(review_practice2 N7·§2-7). 같은 사진의 PNG·JPEG(0.45)는 여전히 묶인다.
_닮음문턱 = 0.6
_쪽상한 = 60          # PDF 한 파일에서 그림을 꺼내 볼 쪽 수(앞에서부터) — 쪽당 0.27초라 수천 쪽이면 요청이 멈춘다(M4)
_파일카드상한 = 200    # 한 파일에서 만들 카드 수
_래스터꼴 = re.compile(r"\.(png|jpe?g|gif|bmp|tiff?|webp|jp2)$", re.I)
# 비밀 표지 — ('26-09-30 fixup, review_practice2 N5) 도장처럼 글자를 띄운 '대 외 비'·공기업의 '사외비'·'대외주의'·
# '내부 검토용'·'외부 유출 금지'·'배포 금지'·FOUO·RESTRICTED 를 더하고, '대외비용·대외비중·대외비율'은 뺀다.
# 이 표지는 쓸 그림을 빼지 않고 공개 장르 목록에서만 돌린다(내부 장르는 확인할 것 한 줄) — 오탐 값이 낮다.
_비밀꼴 = re.compile(r"대\s?외\s?비(?![용중율])|사\s?외\s?비(?![용중율])|대외\s*주의|(?:[ⅠⅡⅢ]|[123])\s*급\s*비밀"
                  r"|(?<![가-힣])비밀(?![번가-힣])|(?<![가-힣])비\s?공\s?개(?![가-힣])"
                  r"|대\s?내\s?한|(?<![가-힣])내부\s*(?:검토\s*|보고\s*)?용(?![가-힣])|외부\s*유출\s*금지|(?<![가-힣])배포\s*금지"
                  r"|열람\s*제한|취급\s*주의|보안\s*문서"
                  r"|(?i:\b(?:confidential|top\s+secret|secret|internal\s+use\s+only)\b)|\b(?:FOUO|RESTRICTED)\b")
_캡션꼴 = re.compile(r"^\s*[<〈＜《]\s*(?:사진|그림|도|이미지|전경)")


def 그림폴더():
    """꺼낸 그림이 사는 곳 — 이 세션 받은 자료 폴더 안(세션이 끝나면 함께 지워진다)."""
    return os.path.join(자료뿌리.받은것뿌리(), _그림폴더명)


def _목록길():
    return os.path.join(그림폴더(), "목록.json")


def _글정리(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _비밀표지(글):
    m = _비밀꼴.search(글 or "")
    return m.group(0).strip() if m else ""


def _정규화(im):
    """꺼낸 그림을 흰 바탕 RGB 로 편다(투명→흰색, CMYK·팔레트·16비트→RGB). EXIF 방향만 읽어 돌리고 버린다."""
    from PIL import Image, ImageOps
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        바탕 = Image.new("RGB", im.size, (255, 255, 255))
        바탕.paste(im, mask=im.split()[-1])
        im = 바탕
    else:
        im = im.convert("RGB")
    # 새 그림으로 옮겨 쓴다 — info(EXIF·XMP·ICC·PNG 글 조각)를 하나도 물려받지 않게
    return Image.frombytes("RGB", im.size, im.tobytes())


def _그림id(im, 쓰인):
    """(id, 내용 해시) — 앞 6자리가 다른 그림과 겹치면 더 길게 짓는다(같은 그림이면 같은 id)."""
    import hashlib
    h = hashlib.sha1(f"{im.size}".encode() + im.tobytes(), usedforsecurity=False).hexdigest()
    for n in (6, 8, 10, 40):
        cid = "img-" + h[:n]
        if 쓰인.get(cid, h) == h:
            쓰인[cid] = h
            return cid, h
    return "img-" + h, h


def _종류추정(im, 표시mm, 이름=""):
    """사진·삽화 / 로고 추정 / 도식·글 그림 — 추정일 뿐이다(모델·사람이 뒤집을 수 있게 카드에 '추정'으로 싣는다)."""
    w, h = im.size
    if re.search(r"로고|logo|엠블[럼렘]|심[벌볼]|(?<![A-Za-z])CI(?![A-Za-z])", 이름 or "", re.I):
        return "로고 추정"
    정사각 = 0.75 <= (w / h if h else 0) <= 1.33
    if 정사각 and 표시mm and min(표시mm) < 30:
        return "로고 추정"
    작은 = im.resize((64, 64))
    b = 작은.tobytes()
    흰 = sum(1 for i in range(0, len(b), 3) if min(b[i], b[i + 1], b[i + 2]) > 235) / (len(b) // 3)
    return "도식·글 그림" if 흰 > 0.5 else "사진·삽화"


def _pdf곁글(블록들, bb):
    """그림 위·아래 40pt 안의 글 — '< 사진 … >' 꼴을 먼저, 없으면 가장 가까운 글."""
    후보 = []
    for b in 블록들:
        글 = _글정리(b[4])
        if not 글:
            continue
        아래 = b[1] - bb.y1
        위 = bb.y0 - b[3]
        거리 = 아래 if 0 <= 아래 <= 40 else (위 if 0 <= 위 <= 40 else None)
        if 거리 is not None:
            후보.append((0 if _캡션꼴.match(글) else 1, 거리, 글))
    후보.sort()
    return 후보[0][2][:80] if 후보 else ""


def _흰테두리깎기(im, 문턱=250, 최소=0.03):
    """(깎은 그림, 남긴 상자 px) — 렌더해 자른 PDF 그림의 가장자리 흰 띠를 깎는다 — PDF 박힌 그림 경계(get_image_info)는 작성자가 잘라 둔 뒤가
    아니라 놓인 자리 전체라, 잘라 둔 바깥이 흰 여백으로 남는다(critic_practice X2). 흰 띠가 한 변 길이의 3% 이상일 때만
    깎는다(사진 가장자리의 밝은 칸을 깎지 않게). 그림 안쪽은 건드리지 않는다."""
    g = im.convert("L")
    w, h = g.size
    px = g.tobytes()

    def 흰줄(y):
        return min(px[y * w:(y + 1) * w]) >= 문턱

    def 흰칸(x, y0, y1):
        return all(px[y * w + x] >= 문턱 for y in range(y0, y1))
    위, 아래 = 0, h
    while 위 < 아래 and 흰줄(위):
        위 += 1
    while 아래 > 위 and 흰줄(아래 - 1):
        아래 -= 1
    왼, 오 = 0, w
    while 왼 < 오 and 흰칸(왼, 위, 아래):
        왼 += 1
    while 오 > 왼 and 흰칸(오 - 1, 위, 아래):
        오 -= 1
    if 오 - 왼 < 8 or 아래 - 위 < 8:
        return im, (0, 0, w, h)      # 거의 흰 그림 — 그대로 둔다
    깎 = [위 >= 최소 * h, (h - 아래) >= 최소 * h, 왼 >= 최소 * w, (w - 오) >= 최소 * w]
    상자 = (왼 if 깎[2] else 0, 위 if 깎[0] else 0, 오 if 깎[3] else w, 아래 if 깎[1] else h)
    return (im.crop(상자) if any(깎) else im), 상자


def _pdf그림들(src, 덧=None):
    import fitz
    import shutil
    import tempfile
    from PIL import Image
    out = []
    d = fitz.open(src)
    임시 = tempfile.mkdtemp(prefix=".쪽-", dir=그림폴더())
    try:
        # 글지문(Q4 짝 PDF) — 앞 _지문쪽상한 쪽의 글. 보이지 않는 글(흰 글·투명 글)도 든다(짝 찾기에는 상관없다 — N3 은 곁 글 쪽 한계)
        if 덧 is not None:
            try:
                덧["글지문"] = _글지문(" ".join(d[i].get_text() for i in range(min(len(d), _지문쪽상한))))
            except Exception:
                pass
        # 파일 단위 비밀 표지('26-09-30 fixup, review_practice2 N6) — 표지(1쪽)에만 찍힌 등급, 쪽 가운데 워터마크(글 덩어리
        # 하나가 표지 낱말뿐), 문서 정보(제목·주제·키워드)도 본다. 쪽마다 머리·꼬리 12% 는 그 쪽 그림에 따로 붙인다.
        쪽수 = min(len(d), _쪽상한)
        모은 = []
        try:
            모은 += [str(v) for k, v in (d.metadata or {}).items() if k in ("title", "subject", "keywords") and v]
        except Exception:
            pass
        # 좌표('26-09-30 주관 판정 Q1) — PyMuPDF 의 그림·글·선 좌표는 **CropBox 왼쪽 위가 원점, 돌리기 전** 좌표다. 보는 사람의
        # 쪽은 CropBox 를 /Rotate 만큼 돌린 것(pg.rect)이고 렌더(pdftoppm -cropbox)도 그 쪽이다. 그래서 그림 경계는 CropBox 안으로
        # 자른 뒤(판 — 밖으로 걸친 그림은 안 부분만) rotation_matrix 로 돌려 렌더 좌표로 옮긴다. 전에는 MediaBox 를 그리고 배율만
        # 곱해 CropBox 밖 부분이 카드가 되고(B1), 돌린 쪽에서는 엉뚱한 자리를 잘랐다(N7).
        # ('26-10-01 R6, verify_fixup5 N1) 보이는 자리(판)는 CropBox 크기가 아니라 **pg.rect 를 돌리기 전으로 되돌린 것**이다 —
        # pg.rect 는 CropBox 와 MediaBox 의 겹침이고 UserUnit 배율까지 들어 있다(그림·글 경계도 같은 공간이다). 전에는
        # Rect(0,0,cropbox.w,cropbox.h)(배율 전·겹침 전)를 쓰고 돌림은 pg.rotation_matrix(겹침 전 크기로 옮긴다)로 해, UserUnit 2
        # 쪽에서 엉뚱한 자리를 잘랐고 CropBox 가 MediaBox 밖으로 넘친 쪽을 돌리면 카드가 사라졌다. 돌림도 판 크기로 직접 한다.
        def _판(pg):
            R = pg.rect
            if pg.rotation % 360 in (90, 270):
                return fitz.Rect(0, 0, R.height, R.width)
            return fitz.Rect(0, 0, R.width, R.height)

        def _돌림(pg, r):
            # 돌리기 전 판 좌표 → 보는 사람 방향(돌린 뒤, 렌더와 같은 방향) 좌표 — /Rotate 는 시계 방향
            r = fitz.Rect(r)
            판_ = _판(pg)
            w, h = 판_.width, 판_.height
            rot = pg.rotation % 360
            if rot == 90:
                return fitz.Rect(h - r.y1, r.x0, h - r.y0, r.x1)
            if rot == 180:
                return fitz.Rect(w - r.x1, h - r.y1, w - r.x0, h - r.y0)
            if rot == 270:
                return fitz.Rect(r.y0, w - r.x1, r.y1, w - r.x0)
            return r

        def _띠(pg, b):
            # 머리·꼬리 12% 띠 — 보는 사람 방향(돌린 뒤)으로 잰다
            r = _돌림(pg, b[:4])
            H = pg.rect.height or 1
            return r.y1 <= H * 0.12 or r.y0 >= H * 0.88
        for pno in range(쪽수):
            pg = d[pno]
            for b in pg.get_text("blocks"):
                if len(b) >= 7 and b[6] != 0:
                    continue
                t = _글정리(b[4])
                if pno == 0 or _띠(pg, b) or (_비밀표지(t) and len(t) <= 12):
                    모은.append(t)
        파일비밀 = _비밀표지(" ".join(모은))
        for pno in range(1, 쪽수 + 1):
            pg = d[pno - 1]
            W, H = pg.rect.width, pg.rect.height       # 보는 사람의 쪽(돌린 뒤) — 렌더와 짝
            판 = _판(pg)                                 # 보이는 자리(돌리기 전 좌표)
            # 표지 낱말뿐인 글 덩어리(워터마크·도장 글)는 곁 글로 쓰지 않는다(N6③: 워터마크 '대외비'가 사진 곁 글이 됐다)
            블록 = [b for b in pg.get_text("blocks") if (len(b) < 7 or b[6] == 0)
                   and not (_비밀표지(_글정리(b[4])) and len(_글정리(b[4])) <= 12)]
            비밀 = _비밀표지(" ".join(_글정리(b[4]) for b in 블록 if _띠(pg, b))) or 파일비밀
            infos = pg.get_image_info()
            쪽넓이 = 판.get_area() or 1
            # 스캔 쪽 — 한 그림이 쪽의 80% 이상이거나 그림 넓이 합이 80% 이상이면 글 층이 있어도 스캔으로 본다(N4: 복합기가
            # 낸 검색 가능 PDF 는 보이지 않는 OCR 글 층이 있고, 띠 여러 장으로 나뉘어 박히기도 한다 — 도장·서명이 든 확인서
            # 한 쪽 전체가 '쓸 수 있음' 카드가 됐다)
            덮음 = sum((fitz.Rect(i["bbox"]) & 판).get_area() for i in infos
                     if not (fitz.Rect(i["bbox"]) & 판).is_empty)
            if 덮음 >= 0.8 * 쪽넓이:
                out.append(dict(자리={"쪽": pno}, 종류="스캔 쪽", 비밀표지=비밀,
                                까닭="스캔한 쪽이라 본문 그림으로 쓰지 않습니다(필요하면 붙임으로 보냅니다)"))
                continue
            후보 = []
            for i in infos:
                bb = fitz.Rect(i["bbox"]) & 판
                if bb.is_empty or min(bb.width, bb.height) / 72 * 25.4 < _작은mm:
                    continue
                if any(abs(bb.x0 - c.x0) < 1 and abs(bb.y0 - c.y0) < 1 and abs(bb.x1 - c.x1) < 1
                       and abs(bb.y1 - c.y1) < 1 for c in 후보):
                    continue       # 같은 자리에 겹친 그림(알파 마스크 따로 든 것 등)은 한 장
                후보.append(bb)
            선 = []
            try:
                선 = [fitz.Rect(x["rect"]) for x in pg.get_drawings() if x.get("rect") is not None]
            except Exception:
                선 = []
            if 후보:
                dpi = 200      # 175mm 폭 그림이 약 1,380px — 인쇄에 충분하고 HWPX 는 어차피 화면을 다시 찍는다
                png = _pdf_page_png(src, pno, dpi, os.path.join(임시, f"p{pno}"))
                with Image.open(png) as 쪽:
                    쪽.load()
                    sx, sy = 쪽.width / W, 쪽.height / H
                    for bb in 후보:
                        rb = _돌림(pg, bb)                 # 보는 사람 방향(돌린 뒤) 좌표
                        상자 = (max(0, int(round(rb.x0 * sx))), max(0, int(round(rb.y0 * sy))),
                               min(쪽.width, int(round(rb.x1 * sx))), min(쪽.height, int(round(rb.y1 * sy))))
                        if 상자[2] - 상자[0] < 2 or 상자[3] - 상자[1] < 2:
                            continue
                        겹 = sum((r & bb).get_area() for r in 선 if not (r & bb).is_empty)
                        깎은, (l, t, r_, b_) = _흰테두리깎기(쪽.crop(상자))
                        보인 = fitz.Rect(상자[0] / sx + l / sx, 상자[1] / sy + t / sy,
                                       상자[0] / sx + r_ / sx, 상자[1] / sy + b_ / sy)
                        out.append(dict(자리={"쪽": pno}, im=깎은, 비밀표지=비밀,
                                        경계pt=[round(v, 1) for v in (보인.x0, 보인.y0, 보인.x1, 보인.y1)],
                                        표시mm=[보인.width / 72 * 25.4, 보인.height / 72 * 25.4],
                                        곁글=_pdf곁글(블록, bb),
                                        가림=겹 >= 0.03 * (bb.get_area() or 1)))
            나머지 = [r for r in 선 if not any(c.contains(r) or (c & r).get_area() > 0.5 * (r.get_area() or 1)
                                             for c in 후보) and r.width * r.height > 4]
            if len(나머지) >= 3:
                u = fitz.Rect(나머지[0])
                for r in 나머지[1:]:
                    u |= r
                out.append(dict(자리={"쪽": pno}, 종류="선 도식·표", 비밀표지=비밀, 곁글=_pdf곁글(블록, u),
                                까닭="선으로 그린 표·도식은 그림으로 옮기지 않고 표·도식으로 다시 씁니다"))
            if len(out) >= _파일카드상한:
                break
        if len(d) > 쪽수:
            out.append(dict(자리={}, 종류="꺼낼 수 없음", 비밀표지=파일비밀,
                            까닭=f"앞 {쪽수}쪽만 살폈습니다. 뒤쪽 {len(d) - 쪽수}쪽의 그림은 목록에 없으니, 필요하면 그림만 따로 올려 주세요."))
    finally:
        d.close()
        shutil.rmtree(임시, ignore_errors=True)
    return out


def _이름(el):
    return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def _글(el):
    return _글정리("".join(t.text or "" for t in el.iter() if _이름(t) == "t"))


def _곁문단(글들, i, 그림문단, 쪽):
    """그림 문단 i 의 바로 앞(쪽=-1)·뒤(+1) 글 — 두 문단 안에서만, 사이에 다른 그림 문단이 있으면 빌려 오지 않는다
    ('26-09-30 fixup, review_practice2 N8: 결재란 서명 그림이 사진 두 장 너머의 '< 사진 > 점검 현장' 캡션을 곁 글로 받았다)."""
    if i is None:
        return ""
    for k in range(i + 쪽, i + 쪽 * 3, 쪽):
        if k < 0 or k >= len(글들) or k in 그림문단:
            return ""
        if 글들[k]:
            return 글들[k]
    return ""


# ── 한글·워드 문서 속 그림은 꺼내 쓰지 않는다('26-09-30 주관 판정 P1, fixup4) ─────────────────────────────────────
# HWP·HWPX·DOCX 그릇 속 그림 원본(BinData·word/media)은 화면에 보이는 모습과 다를 수 있다 — 도형·바탕쪽·머리말 개체로 가린
# 자리, 문서 안 자르기, 숨은 글·변경 추적으로 지운 원본, mc:Fallback … 구조 검사로 '보이는 그대로'를 증명하려던 두 차수
# (fixup2 가림 꼴 찾기 → fixup3 허용 목록)가 연달아 우회됐다(verify_fixup3 B3: 허용 목록을 빠져나가는 16꼴, 공개
# 행정업무운영편람 8구역 바탕쪽). kordoc 렌더도 바탕쪽·머리말·앞 순서 개체·변경 추적을 못 그려 대안이 못 된다(rendercrop
# measure). 그래서 사진 카드는 **렌더해 보이는 그대로 자르는 원천**에서만 만든다 — PDF 쪽(pdftoppm -cropbox 렌더 후 자르기 —
# 한글·워드가 PDF 로 저장한 파일이 '보이는 그대로'다)과 그림 파일(PNG·JPG 등, PIL 로 다시 써 EXIF 를 걷는다). 문서 파일의 그림은
# 도식·표 캡처 같은 글 그림까지 모두 '문서 속 사진' 카드로만 적는다 — id·그림 파일·미리보기를 만들지 않는다. 몇 장인지 세어
# 사용자에게 알린다(api._그림살피기 확인할것 · 파일읽기 '그림안내' · 편집기 서랍 — 문서사진말 한 곳에서 짓는다).
# 대가: 공개 HWPX 24·HWP 12 에서 쓸 수 있던 카드 3·15장 → 0(fixup4 보고 §P1).
#
# 거절용 지각 해시('26-09-30 주관 판정 Q2, fixup5) — 문서 속 그림(자리에 놓인 것 + 그릇 속 나머지 원본: 지운 변경·숨은 설명·
# 바탕쪽)의 바이트는 **지각 해시(_지각해시들 10벌)와 색결을 셈하는 데만** 쓰고 저장·출력하지 않는다. 해시는 세션 방 목록
# (목록.json 파일 항목의 '거절')에만 둔다 — 카드에 싣지 않아 파일읽기·그림목록·편집기·지시문 어디에도 나가지 않는다. 쓰는 곳 둘:
# ① 이미지채움이 문서 속 원본을 'AI 생성물'로 받지 않는다(verify_fixup4 B2 — P1 로 미리보기가 빠지자 대조 대상에서 사라졌다)
# ② 사용자가 같은 사진을 그림 파일로 따로 올렸으면 알림 수를 그만큼 줄인다(Q4, 문서사진남은수) — '26-10-01 주관 판정 S1 로
#    알림은 더 이상 빼지 않는다(문서사진줄들). 문서사진남은수·_짝셈은 셈 도구로만 남는다(--짝셈).
# 짝 PDF(Q4) — 같은 문서를 PDF 로 저장해 함께 올렸는지는 **파일 이름이 아니라 본문 겹침**으로 본다(글지문: 글자·숫자만 남긴 5글자
# 조각의 crc32 를 모듈러 표본으로 줄인 모음, 원문은 남기지 않는다). 공개 HWPX 24 × PDF 실측(fx5 exp/twin.py, 상한 2000): 같은
# 문서 HWPX·PDF 쌍 21건의 서로 담김 최솟값 0.867~0.993, 다른 문서끼리 가장 높은 값 0.072 — 문턱 _짝문턱 0.7.
문서사진 = "문서 속 사진"
문서사진까닭 = "문서를 PDF로 저장해 함께 올리거나 사진 파일로 올려 주세요"
자리없음말 = "이 문서 종류에는 사진을 넣는 자리가 없어 첨부 사진을 싣지 않았습니다."
# HWP(바이너리)를 kordoc 이 못 셌을 때('26-10-01 주관 판정 T1) — 사진이 있는지 모르므로 '들었을 수 있다'고만 한다
사진모름머리 = "첨부한 한글 문서에 사진이 들었을 수 있습니다(HWP 파일 속 그림은 살피지 못했습니다)."
사진모름말 = 사진모름머리 + " 넣으려면 한글에서 PDF로 저장해 함께 올리거나, 사진 파일로 올려 주세요."
# 짝 PDF(본문 겹침 ≥ _짝문턱)에 사진 카드가 있을 때('26-10-01 주관 판정 T4) — 같은 사진인지 단정하지 않고 사람에게 확인을 맡긴다
짝PDF말 = "함께 올린 PDF에서 사진 {n}장을 찾았습니다. 문서 속 사진과 같은지 편집 화면에서 확인해 주세요."
# ('26-10-01 주관 판정 S1) 짝 PDF 가 있는데 그 PDF 에 사진 카드가 없을 때 (가) 의 뒷문장 — PDF 를 이미 올렸으니 PDF 길을 또 권하지 않는다
짝무사진꼬리 = "함께 올린 PDF에서도 사진을 찾지 못했습니다. 사진 파일로 올려 주세요."
# ('26-10-01 주관 판정 S2) 그림 도구(Pillow·PyMuPDF — 이 파이썬에도 build/.hwpxenv 에도)가 없거나 깨져 올린 사진 파일을 못 쓸 때
그림도구말 = "그림을 처리하는 도구가 없어 올린 사진을 쓰지 못했습니다. bin/bootstrap.sh 를 다시 실행하거나 관리자에게 알려 주세요."
# ('26-10-01 주관 판정 P3) 짝 PDF 에 사진 카드가 있을 때 (가) 의 뒷문장 — PDF 를 이미 올렸으니 'PDF로 저장해'를 다시 권하지 않는다
짝사진꼬리 = "함께 올린 PDF의 사진을 편집 화면에서 골라 넣을 수 있습니다."
# ('26-10-01 주관 판정 P4) 그림 자리 없는 장르(1p·판형 v2)에 사진 **파일**만 올렸을 때(문서 속 사진이 없을 때)
자리없음사진말 = "이 문서 종류에는 사진을 넣는 자리가 없어 올린 사진을 싣지 않았습니다."
# ('26-10-01 주관 판정 P1) 도구는 있는데 위임 자식(--카드)이 시간 초과·충돌로 죽어 그 파일의 카드를 못 만들었을 때 — 파일마다 한 줄
처리못함말 = "{이름}: 그 파일을 처리하지 못했습니다. 다시 올려 보시고, 또 안 되면 관리자에게 알려 주세요."
# ('26-10-01 주관 판정 Q3, verify_fixup9 B1) 위임 자식을 죽인 범인 파일 줄 — 이름을 대고 '다시 올려'를 뺀다(같은 파일을 다시
# 올려도 또 죽는다). 문서·PDF 와 사진 파일이 다르다. 도구 있는 곳에서 깨진 사진 파일(잘림·0바이트, Q7)도 범인사진말
범인문서말 = "{이름}: 이 파일에서 사진을 꺼내다 멈춰서, 이 파일의 사진은 쓰지 않았습니다. 넣어야 할 사진은 사진 파일(PNG·JPG)로 따로 올려 주세요."
범인사진말 = "{이름}: 이 사진 파일을 열지 못해 쓰지 않았습니다. PNG나 JPG로 다시 저장해 올려 주세요."
_문서꼴 = re.compile(r"\.(hwpx|hwp|docx)$", re.I)
_OLE머리 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_HWP머리 = b"HWP Document File"
_HWP3머리 = b"HWP Document File V3.00"
_문서종류캐시 = {}


def _hwpml인가(앞):
    try:
        글 = 앞.decode("utf-8", "ignore").lstrip("﻿").lstrip()
    except Exception:
        return False
    return 글.startswith("<?xml") and "<HWPML" in 글
_거절해시상한 = 120                  # 한 파일에서 해시를 셀 그림 수(자리 + 그릇 속 나머지)
_거절바이트상한 = 40 * 1024 * 1024    # 이보다 큰 그림 하나는 해시를 세지 않는다
_짝문턱 = 0.7
_짝지각문턱 = 8              # 알림 짝(같은 사진을 그림 파일로 따로 올림) — 채우기 거절 문턱(12)보다 좁다
_짝색도문턱 = 0.03
_지문조각 = 5
_지문상한 = 2000          # 표본 조각 수 상한 — 목록.json 이 커지지 않게(공개 쌍 실측은 이 상한으로 쟀다)
_지문쪽상한 = 400          # PDF 글지문을 셀 쪽 수(383쪽 행정업무운영편람 전부가 든다)


def _문서종류(경로):
    """'hwpx'·'docx'·'hwp'·'hwp3'·'hwpml' 또는 '' — 확장자가 아니라 **파일 머리(시그니처)** 로 가린다('26-09-30 Q6, verify_fixup4 N4: 확장자가
    없거나 .docm·.hwtx·.zip 으로 바꾼 DOCX 는 kordoc 이 글로 읽는데 그림 알림이 빠졌다). ZIP 은 속 이름(word/document.xml ·
    Contents/section·header), OLE 는 HWP 머리 글('HWP Document File')을 본다(.doc·.xls 같은 다른 OLE 는 아니다)."""
    try:
        st = os.stat(경로)
    except (OSError, ValueError, TypeError):
        return ""
    import stat as _st
    if not _st.S_ISREG(st.st_mode):
        return ""
    열쇠 = (os.path.realpath(경로), st.st_size, int(st.st_mtime))
    if 열쇠 in _문서종류캐시:
        return _문서종류캐시[열쇠]
    종 = ""
    try:
        with open(경로, "rb") as f:
            머 = f.read(8)
            f.seek(0)
            앞 = f.read(512)
            if 앞.startswith(_HWP3머리):
                # 한글 97 이전 HWP 3.0(OLE 가 아니다) — kordoc 의 detectFormat 과 같은 머리('26-10-01 R6, verify_fixup5 N4)
                종 = "hwp3"
            elif _hwpml인가(앞):
                # HWPML(.hml, 한글 XML) — '<?xml' 로 시작하고 앞 512바이트에 <HWPML 이 있다(kordoc isHwpmlFile 과 같은 잣대)
                종 = "hwpml"
            elif 머[:4] == b"PK\x03\x04":
                import zipfile
                with zipfile.ZipFile(경로) as z:
                    이름들 = set(z.namelist())
                if "word/document.xml" in 이름들:
                    종 = "docx"
                elif "Contents/header.xml" in 이름들 or any(re.match(r"Contents/section\d+\.xml$", n) for n in 이름들):
                    종 = "hwpx"
            elif 머 == _OLE머리:
                f.seek(0)
                꼬리 = b""
                while True:
                    조 = f.read(1 << 20)
                    if not 조:
                        break
                    if _HWP머리 in 꼬리 + 조:
                        종 = "hwp"
                        break
                    꼬리 = 조[-32:]
    except Exception:
        종 = ""
    if len(_문서종류캐시) > 512:
        _문서종류캐시.clear()
    _문서종류캐시[열쇠] = 종
    return 종


def 문서파일인가(이름):
    """한글·워드 문서(HWP·HWPX·DOCX)인가 — 확장자로, 또는 그 파일이 있으면 파일 머리(_문서종류)로. 이름만 주면 받은 자료
    폴더에서 찾는다."""
    s = str(이름 or "")
    if _문서꼴.search(s):
        return True
    if not s.strip():
        return False
    try:
        p = s if os.path.isabs(s) else os.path.join(자료뿌리.받은것뿌리(), s)
    except Exception:
        return False
    return bool(_문서종류(p))


def _문서이름(종):
    return "워드" if 종 == "docx" else "한글"


def _문서사진(ent, 종="hwpx"):
    ent.update(종류=문서사진, 까닭=문서사진까닭, 문서=_문서이름(종))
    return ent


def _거절해시(b):
    """그림 바이트 → {"지각": [63비트 ×10], "색": [r, g, 채도, 편차]} 또는 None(열리지 않거나 너무 큼·작음).
    바이트는 이 자리에서만 쓰고 버린다 — 저장·출력하지 않는다(Q2). 카드 미리보기와 같은 길(정규화 → 320px)로 줄여 잰다.
    Pillow 가 없으면 None — 자리는 세되 해시만 없다('26-10-01 주관 판정 T1: 도구가 하나도 없어도 문서 속 사진 알림은 선다)."""
    import io
    try:
        from PIL import Image
    except ImportError:
        return None
    if not b or len(b) > _거절바이트상한:
        return None
    Image.MAX_IMAGE_PIXELS = _채움최대화소
    try:
        with Image.open(io.BytesIO(b)) as im:
            try:
                im.draft("RGB", (640, 640))
            except Exception:
                pass
            im.load()
            t = _정규화(im)
    except Exception:
        return None
    t.thumbnail((320, 320))
    if min(t.size) < 8:
        return None
    return {"지각": _지각해시들(t), "색": [round(v, 5) for v in _색결(t)]}


def _글지문(글):
    """본문 글 → {"모": m, "값": [crc32 …]} — 글자·숫자만 남긴 5글자 조각의 해시를 모듈러 표본(모 m)으로 줄인 모음. 원문은
    남기지 않는다. 짝 PDF 찾기(_글겹침)에만 쓴다."""
    import unicodedata
    import zlib
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", unicodedata.normalize("NFC", str(글 or ""))).lower()
    k = _지문조각
    모 = 4
    값 = {h for h in (zlib.crc32(s[i:i + k].encode("utf-8")) for i in range(max(0, len(s) - k + 1))) if h % 모 == 0}
    while len(값) > _지문상한:
        모 *= 2
        값 = {h for h in 값 if h % 모 == 0}
    import array
    import base64
    return {"모": 모, "수": len(값), "값": base64.b64encode(array.array("I", sorted(값)).tobytes()).decode("ascii")}


def _지문값(fp):
    """글지문의 조각 해시 모음 — 목록에는 uint32 묶음(base64)으로 둔다(정수 목록이면 목록.json 이 파일마다 수십 KB 로 불었다)."""
    import array
    import base64
    v = fp.get("값")
    if isinstance(v, list):
        return set(v)
    a = array.array("I")
    a.frombytes(base64.b64decode(v or ""))
    return set(a)


def _글겹침(a, b):
    """두 글지문의 서로 담김 최솟값(0~1) — 한쪽이 너무 짧으면(표본 30 미만) 0(짝으로 보지 않는다)."""
    try:
        m = max(int(a["모"]), int(b["모"]))
        A = {h for h in _지문값(a) if h % m == 0}
        B = {h for h in _지문값(b) if h % m == 0}
    except Exception:
        return 0.0
    if len(A) < 30 or len(B) < 30:
        return 0.0
    j = len(A & B)
    return min(j / len(A), j / len(B))


def 원문에든자료(원문, 문턱=None):
    """원문(자료 글)에 본문이 든 받은 자료 파일 이름들 — 파일 글지문의 조각이 원문 조각에 문턱(기본 _짝문턱) 이상 담기면 든 것이다
    ('26-10-01 주관 판정 R5). CLI 는 대화를 몰라 새문서가 어느 자료로 만들어졌는지를 이것으로 가린다(api._그림문서묶기). 글지문이
    없는 파일(그림 파일·짧은 글)은 들지 않는다. 목록을 새로 만들지 않고 읽기만 한다."""
    import unicodedata
    import zlib
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", unicodedata.normalize("NFC", str(원문 or ""))).lower()
    k = _지문조각
    if len(s) < 60:
        return []
    원 = {zlib.crc32(s[i:i + k].encode("utf-8")) for i in range(len(s) - k + 1)}
    문 = _짝문턱 if 문턱 is None else 문턱
    out = []
    for f, e in sorted((_목록읽기().get("파일들") or {}).items()):
        fp = (e or {}).get("글지문")
        if not fp:
            continue
        try:
            A = _지문값(fp)
        except Exception:
            continue
        if len(A) >= 30 and len(A & 원) / len(A) >= 문:
            out.append(f)
    return out


def _hwpx그림들(src, 덧=None):
    """HWPX 의 그림 자리를 문서 차례로 센다(구역 → hp:pic). 카드에는 크기(표시mm)·곁 글·비밀 표지만. 그림 바이트는 거절 해시
    (덧["거절"])에만 쓴다 — 자리에 놓인 그림(순번)과 그릇 속 나머지(BinData — 지운 변경·바탕쪽·숨은 설명의 원본)."""
    import zipfile
    import 안전xml as ET     # 올린 파일 — DTD·엔티티 선언이 있으면 읽기 전에 거절(감사 code F4)
    out = []
    덧 = {} if 덧 is None else 덧
    거절, 글조각 = 덧.setdefault("거절", []), []
    with zipfile.ZipFile(src) as z:
        이름들 = z.namelist()
        항목 = {}
        for n in 이름들:
            if n.lower().endswith(".hpf"):
                try:
                    for it in ET.fromstring(z.read(n)).iter():
                        if _이름(it) == "item" and it.get("id") and it.get("href"):
                            항목[it.get("id")] = it.get("href")
                except Exception:
                    pass

        def 그림바이트(href):
            for c in (href, "Contents/" + href, href.lstrip("/")):
                if c in 이름들:
                    if z.getinfo(c).file_size > _거절바이트상한:
                        return None
                    return z.read(c)
            return None
        쓴 = set()
        절들 = sorted((n for n in 이름들 if re.match(r"Contents/section\d+\.xml$", n)),
                    key=lambda s: int(re.search(r"(\d+)\.xml$", s).group(1)))
        머리꼬리, 첫글, 순번 = "", "", 0
        for 절 in 절들:
            root = ET.fromstring(z.read(절))
            부모 = {c: p for p in root.iter() for c in p}
            for el in root.iter():
                if _이름(el) in ("header", "footer"):
                    머리꼬리 += " " + _글(el)
            위문단 = [p for p in root if _이름(p) == "p"]
            if not 첫글:
                첫글 = next((_글(p) for p in 위문단 if _글(p)), "")
            자리 = {p: i for i, p in enumerate(위문단)}
            글들 = [_글(p) for p in 위문단]
            글조각 += 글들

            def 윗문단(el):
                n = el
                while n in 부모:
                    n = 부모[n]
                    if n in 자리:
                        break
                return n
            그림문단 = {자리.get(윗문단(el)) for el in root.iter() if _이름(el) == "pic"}
            for pic in root.iter():
                if _이름(pic) != "pic":
                    continue
                순번 += 1
                i = 자리.get(윗문단(pic))
                앞, 뒤 = _곁문단(글들, i, 그림문단, -1), _곁문단(글들, i, 그림문단, +1)
                제 = 글들[i] if i is not None else ""
                곁 = next((x for x in (뒤, 앞, 제) if _캡션꼴.match(x)), "") or 제 or 뒤 or 앞
                ent = dict(자리={"순번": 순번}, 곁글=곁[:80])
                sz = next((e for e in pic.iter() if _이름(e) in ("sz", "curSz") and e.get("width")), None)
                if sz is not None:
                    try:
                        ent["표시mm"] = [int(sz.get("width")) / 7200 * 25.4, int(sz.get("height") or 0) / 7200 * 25.4]
                    except (TypeError, ValueError):
                        pass
                ref = next((e.get("binaryItemIDRef") for e in pic.iter() if e.get("binaryItemIDRef")), None)
                href = 항목.get(ref) if ref else None
                if href and len(거절) < _거절해시상한:
                    h = _거절해시(그림바이트(href))
                    if h:
                        거절.append(dict(h, 순번=순번))
                        쓴.add(href)
                out.append(_문서사진(ent, "hwpx"))
        for n in 이름들:
            if len(거절) >= _거절해시상한:
                break
            if n.startswith("BinData/") and n not in 쓴 and ("Contents/" + n) not in 쓴:
                h = _거절해시(그림바이트(n))
                if h:
                    거절.append(dict(h, 순번=None))
    덧["글지문"] = _글지문(" ".join(글조각))
    비밀 = _비밀표지(머리꼬리 + " " + 첫글)
    for e in out:
        e["비밀표지"] = 비밀
    return out


def _docx그림들(src, 덧=None):
    """DOCX 본문의 그림(w:drawing 속 a:blip)을 문서 차례로 센다. 카드에는 크기·곁 글·비밀 표지만. 그림 바이트는 거절 해시에만
    (본문 자리 + word/media 나머지 — 머리말·지운 변경·mc:Fallback 의 원본)."""
    import posixpath
    import zipfile
    import 안전xml as ET     # 올린 파일 — DTD·엔티티 선언이 있으면 읽기 전에 거절(감사 code F4)
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    out = []
    덧 = {} if 덧 is None else 덧
    거절 = 덧.setdefault("거절", [])
    with zipfile.ZipFile(src) as z:
        이름들 = z.namelist()
        관계 = {}
        try:
            for r in ET.fromstring(z.read("word/_rels/document.xml.rels")).iter():
                if r.get("Id") and r.get("Target") and r.get("TargetMode") != "External":
                    관계[r.get("Id")] = posixpath.normpath(posixpath.join("word", r.get("Target"))).lstrip("/")
        except Exception:
            pass

        def 그림바이트(n):
            if n in 이름들 and z.getinfo(n).file_size <= _거절바이트상한:
                return z.read(n)
            return None
        쓴 = set()
        root = ET.fromstring(z.read("word/document.xml"))
        부모 = {c: p for p in root.iter() for c in p}
        머리꼬리 = " ".join(_글(ET.fromstring(z.read(n))) for n in 이름들
                        if re.match(r"word/(header|footer)\d*\.xml$", n))
        문단 = [p for p in root.iter() if _이름(p) == "p"]
        자리 = {p: i for i, p in enumerate(문단)}
        글들 = [_글(p) for p in 문단]
        첫글 = next((g for g in 글들 if g), "")

        def 윗문단(el):
            n = el
            while n in 부모:
                n = 부모[n]
                if n in 자리:
                    break
            return n

        def 그림인가(dr):
            return any(_이름(e) == "blip" for e in dr.iter())
        그림문단 = {자리.get(윗문단(el)) for el in root.iter() if _이름(el) == "drawing" and 그림인가(el)}
        순번 = 0
        for dr in root.iter():
            if _이름(dr) != "drawing" or not 그림인가(dr):
                continue      # 그림이 아닌 도형·글상자 — 카드가 아니다
            순번 += 1
            i = 자리.get(윗문단(dr))
            앞, 뒤 = _곁문단(글들, i, 그림문단, -1), _곁문단(글들, i, 그림문단, +1)
            제 = 글들[i] if i is not None else ""
            곁 = next((x for x in (뒤, 앞, 제) if _캡션꼴.match(x)), "") or 제 or 뒤 or 앞
            ent = dict(자리={"순번": 순번}, 곁글=곁[:80])
            ext = next((e for e in dr.iter() if _이름(e) == "extent"), None)
            if ext is not None and ext.get("cx"):
                try:
                    ent["표시mm"] = [int(ext.get("cx")) / 36000, int(ext.get("cy") or 0) / 36000]
                except (TypeError, ValueError):
                    pass
            rid = next((e.get(R + "embed") for e in dr.iter() if _이름(e) == "blip" and e.get(R + "embed")), None)
            n = 관계.get(rid) if rid else None
            if n and len(거절) < _거절해시상한:
                h = _거절해시(그림바이트(n))
                if h:
                    거절.append(dict(h, 순번=순번))
                    쓴.add(n)
            out.append(_문서사진(ent, "docx"))
        for n in 이름들:
            if len(거절) >= _거절해시상한:
                break
            if n.startswith("word/media/") and n not in 쓴:
                h = _거절해시(그림바이트(n))
                if h:
                    거절.append(dict(h, 순번=None))
    덧["글지문"] = _글지문(" ".join(글들))
    비밀 = _비밀표지(머리꼬리 + " " + 첫글)
    for e in out:
        e["비밀표지"] = 비밀
    return out


def _hml그림들(src, 덧=None):
    """HWPML(.hml — 한글 XML) 의 그림 자리를 문서 차례로 센다('26-10-01 R6, verify_fixup5 N4). 그림 바이트는 꼬리(BINDATASTORAGE)의
    base64 BINDATA 에 있다 — HWPX 처럼 거절 해시에만 쓰고(자리: IMAGE BinItem → BINDATALIST 의 BINITEM(1부터) → BinData Id),
    가리키지 않는 나머지도 해시한다. 카드에는 크기(표시mm)·곁 글·비밀 표지만."""
    import base64
    import 안전xml as ET     # 올린 파일 — DTD·엔티티 선언이 있으면 읽기 전에 거절(감사 code F4)
    out = []
    덧 = {} if 덧 is None else 덧
    거절 = 덧.setdefault("거절", [])
    if os.path.getsize(src) > 8 * _거절바이트상한:
        return [dict(자리={}, 종류="꺼낼 수 없음", 까닭="이 파일에서 그림을 꺼내지 못했습니다")]
    root = ET.parse(src).getroot()
    binitem = [e for e in root.iter() if _이름(e) == "BINITEM"]
    bindata = {e.get("Id"): e for e in root.iter() if _이름(e) == "BINDATA"}

    def 바이트(el):
        if el is None or (el.get("Encoding") or "Base64").lower() != "base64":
            return None
        글 = "".join((el.text or "").split())
        if len(글) * 3 // 4 > _거절바이트상한:
            return None
        try:
            return base64.b64decode(글)
        except Exception:
            return None
    def 글(el):
        return _글정리("".join(x.text or "" for x in el.iter() if _이름(x) == "CHAR"))
    머리꼬리 = " ".join(글(e) for e in root.iter() if _이름(e) in ("HEADER", "FOOTER"))
    문단 = [p for p in root.iter() if _이름(p) == "P"]
    자리 = {p: i for i, p in enumerate(문단)}
    부모 = {c: p for p in root.iter() for c in p}
    글들 = [글(p) for p in 문단]
    첫글 = next((g for g in 글들 if g), "")

    def 윗문단(el):
        n = el
        while n in 부모:
            n = 부모[n]
            if n in 자리:
                break
        return n
    그림들 = [e for e in root.iter() if _이름(e) == "PICTURE"]
    그림문단 = {자리.get(윗문단(e)) for e in 그림들}
    쓴 = set()
    순번 = 0
    for pic in 그림들:
        if True:
            순번 += 1
            i = 자리.get(윗문단(pic))
            앞, 뒤 = _곁문단(글들, i, 그림문단, -1), _곁문단(글들, i, 그림문단, +1)
            제 = 글들[i] if i is not None else ""
            곁 = next((x for x in (뒤, 앞, 제) if _캡션꼴.match(x)), "") or 제 or 뒤 or 앞
            ent = dict(자리={"순번": 순번}, 곁글=곁[:80])
            sz = next((e for e in pic.iter() if _이름(e) == "SIZE" and e.get("Width")), None)
            if sz is not None:
                try:
                    ent["표시mm"] = [int(sz.get("Width")) / 7200 * 25.4, int(sz.get("Height") or 0) / 7200 * 25.4]
                except (TypeError, ValueError):
                    pass
            im = next((e for e in pic.iter() if _이름(e) == "IMAGE" and e.get("BinItem")), None)
            bid = None
            if im is not None:
                try:
                    k = int(im.get("BinItem"))
                    bid = binitem[k - 1].get("BinData") if 0 < k <= len(binitem) else im.get("BinItem")
                except (TypeError, ValueError):
                    bid = im.get("BinItem")
            if bid is not None and len(거절) < _거절해시상한:
                h = _거절해시(바이트(bindata.get(str(bid))))
                if h:
                    거절.append(dict(h, 순번=순번))
                    쓴.add(str(bid))
            out.append(_문서사진(ent, "hwpml"))
    for k, el in bindata.items():
        if len(거절) >= _거절해시상한:
            break
        if k not in 쓴:
            h = _거절해시(바이트(el))
            if h:
                거절.append(dict(h, 순번=None))
    덧["글지문"] = _글지문(" ".join(글들))
    비밀 = _비밀표지(머리꼬리 + " " + 첫글)
    for e in out:
        e["비밀표지"] = 비밀
    return out


def _묵은임시치우기(묵힘초=600):
    """그림 폴더의 묵은 임시 폴더(.hwp-* kordoc 풀이·.쪽-* PDF 쪽 렌더)를 지운다('26-09-30 Q6, verify_fixup4 N6) — finally 가
    지우지만 서버가 도중에 죽으면(SIGKILL) 남아 받은 자료 하위 폴더에 원본 그림이 남았다. 카드 목록 빗장 안에서 부른다. kordoc
    은 120초 안에 끝나므로 10분 넘은 것은 죽은 작업의 것이다."""
    import shutil
    import time
    폴더 = 그림폴더()
    try:
        이름들 = os.listdir(폴더)
    except OSError:
        return
    지금 = time.time()
    for n in 이름들:
        if not (n.startswith(".hwp-") or n.startswith(".쪽-")):
            continue
        p = os.path.join(폴더, n)
        try:
            if 지금 - os.path.getmtime(p) > 묵힘초:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def _kordoc길():
    return os.path.join(os.path.dirname(BASE), "node_modules", ".bin", "kordoc")


def _머리크기(b):
    """그림 바이트 머리 → (가로, 세로) px 또는 None — Pillow 없이(표준 라이브러리) PNG·GIF·BMP·JPEG 만 읽는다('26-10-01 T1).
    다른 형식(TIFF·WebP·JPEG2000)은 None — 부르는 쪽은 크기를 모르면 센다(알림이 빠지지 않는 쪽)."""
    import struct
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n" and b[12:16] == b"IHDR":
            return tuple(struct.unpack(">II", b[16:24]))
        if b[:6] in (b"GIF87a", b"GIF89a"):
            return tuple(struct.unpack("<HH", b[6:10]))
        if b[:2] == b"BM" and len(b) >= 26:
            w, h = struct.unpack("<ii", b[18:26])
            return (abs(w), abs(h))
        if b[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m == 0xFF:
                    i += 1
                    continue
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", b[i + 5:i + 9])
                    return (w, h)
                i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    except Exception:
        pass
    return None


def _hwp그림들(src, 덧=None):
    """HWP(바이너리) — 설치된 kordoc 이 꺼낸 그림 파일을 **세기만** 한다(카드에는 싣지 않고, 바이트는 거절 해시에만). 못 세면
    '꺼낼 수 없음' 하나(사진모름 — 알림은 '사진이 들었을 수 있습니다', '26-10-01 주관 판정 T1)로 둔다 — 사진이 있는지 모르면서
    '사진 N장을 쓰지 않았다'고 말하지 않게. 풀린 파일은 finally 에서 지우고, 도중에 죽어 남은 것은 다음 카드 만들기가 지운다
    (_묵은임시치우기). Pillow 가 없으면(T1) 해시 없이 세고, 작은 그림(글머리 아이콘)은 파일 머리의 크기로 뺀다."""
    import glob
    import shutil
    import tempfile
    kd = _kordoc길()
    덧 = {} if 덧 is None else 덧
    거절 = 덧.setdefault("거절", [])
    없음 = [dict(자리={}, 종류="꺼낼 수 없음", 문서="한글", 사진모름=True,
               까닭="HWP 파일 속 그림은 살피지 못했습니다. 넣을 사진은 한글에서 PDF로 저장해 함께 올리거나 사진 파일로 올려 주세요")]
    pil = _pil있나()
    if not os.path.exists(kd):
        return 없음
    임시 = tempfile.mkdtemp(prefix=".hwp-", dir=그림폴더())
    try:
        r = subprocess.run([kd, src, "-o", os.path.join(임시, "out.md")], capture_output=True, timeout=120,
                           env=dict(os.environ, TMPDIR=임시))
        if r.returncode != 0:
            return 없음
        try:
            with open(os.path.join(임시, "out.md"), encoding="utf-8", errors="replace") as f:
                덧["글지문"] = _글지문(re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", f.read()))
        except OSError:
            pass
        그림 = sorted(p for p in glob.glob(os.path.join(임시, "**", "*"), recursive=True) if _래스터꼴.search(p))
        out = []
        for p in 그림:
            머 = None
            try:
                with open(p, "rb") as f:
                    b = f.read(_거절바이트상한 + 1)
                h = _거절해시(b) if pil else None
                if not pil:
                    머 = _머리크기(b)
            except OSError:
                h = None
            finally:
                b = None
            if pil:
                if not h:
                    continue
                # 크기 문턱(글머리 아이콘·장식)은 꺼낸 그림에 거는 것과 같다 — 해시 셈에 쓴 썸네일이 아니라 원래 크기를 본다
                try:
                    from PIL import Image
                    with Image.open(p) as im:
                        크기 = im.size
                except Exception:
                    continue
                if min(크기) < _작은px:
                    continue
            elif 머 and min(머) < _작은px:
                continue
            out.append(_문서사진(dict(자리={"순번": len(out) + 1}, 곁글=""), "hwp"))
            if h and len(거절) < _거절해시상한:
                거절.append(dict(h, 순번=len(out)))
        return out
    except Exception:
        return 없음
    finally:
        shutil.rmtree(임시, ignore_errors=True)


def _꺼내기(p, 이름, 덧=None):
    """첨부 하나 → 카드 재료 목록. 덧(dict)에 거절 해시·글지문(짝 PDF 찾기)을 채운다. 한글·워드 문서는 확장자가 아니라 파일
    머리로 가린다(N4)."""
    덧 = {} if 덧 is None else 덧
    low = 이름.lower()
    종 = _문서종류(p)
    if 종 in ("hwpx", "docx", "hwpml"):
        import 안전xml
        위험 = 안전xml.파일검사(p)     # DTD·엔티티 선언 — 읽기 전에 거절하고 까닭을 사람 말로(감사 code F4)
        if 위험:
            return [dict(자리={}, 종류="꺼낼 수 없음", 까닭=위험)]
    if 종 == "hwpx":
        return _hwpx그림들(p, 덧)
    if 종 == "docx":
        return _docx그림들(p, 덧)
    if 종 in ("hwp", "hwp3"):
        return _hwp그림들(p, 덧)
    if 종 == "hwpml":
        return _hml그림들(p, 덧)
    if low.endswith((".hwpx", ".hwp", ".docx", ".hml")):
        # 이름은 문서인데 머리가 아니다(깨진 파일) — 그림을 꺼내지 않는다
        return [dict(자리={}, 종류="꺼낼 수 없음", 까닭="이 파일에서 그림을 꺼내지 못했습니다")]
    if low.endswith(".pdf"):
        return _pdf그림들(p, 덧)
    if _래스터꼴.search(low):
        from PIL import Image
        im = Image.open(p)
        im.load()
        return [dict(자리={}, im=im, 곁글="", 비밀표지=_비밀표지(이름))]
    return []      # XLSX·PPTX·글 파일 — 그림을 꺼내지 않는다


def _카드마무리(이름, 원, 폴더, 쓰인):
    받은 = 자료뿌리.받은것뿌리()
    os.makedirs(os.path.join(폴더, "thumb"), exist_ok=True)
    카드 = []
    import unicodedata
    # 파일 이름의 비밀 표지는 형식과 무관하게 그 파일의 모든 그림에(전에는 그림 파일일 때만 봤다, review_practice2 N6②)
    이름표지 = _비밀표지(unicodedata.normalize("NFC", 이름))
    for e in 원[:_파일카드상한]:
        c = {"파일": 이름, "자리": e.get("자리") or {}, "곁글": e.get("곁글", ""),
             "비밀표지": e.get("비밀표지") or 이름표지}
        if e.get("문서"):
            c["문서"] = e["문서"]          # '한글'·'워드' — 알림 글(문서사진말)이 파일 머리로 가린 종류를 쓴다(N4)
        if e.get("사진모름"):
            c["사진모름"] = True            # HWP 를 kordoc 이 못 셌다 — 알림은 '사진이 들었을 수 있습니다'(T1)
        if e.get("표시mm"):
            c["표시mm"] = [int(round(v)) for v in e["표시mm"]]
        if e.get("경계pt"):
            c["경계pt"] = e["경계pt"]
        im = e.get("im")
        if im is None:
            if c.get("표시mm") and min(c["표시mm"]) < _작은mm:
                continue      # 작게 놓인 그림(글머리 아이콘·장식)은 꺼낸 그림처럼 목록에서 뺀다 — '가림 있음' 카드가 쌓이지 않게
            c.update(종류=e.get("종류") or "꺼낼 수 없음", 쓸수있음=False,
                     까닭=e.get("까닭") or "그림을 꺼낼 수 없습니다")
            카드.append(c)
            continue
        im = _정규화(im)
        if min(im.size) < _작은px or (c.get("표시mm") and min(c["표시mm"]) < _작은mm):
            continue
        cid, 해시 = _그림id(im, 쓰인)
        길 = os.path.join(폴더, cid + ".png")
        if not os.path.exists(길):
            im.save(길, "PNG")
        썸 = os.path.join(폴더, "thumb", cid + ".png")
        if not os.path.exists(썸):
            t = im.copy()
            t.thumbnail((320, 320))
            t.save(썸, "PNG")
        c.update(id=cid, 해시=해시, 원본px=list(im.size), 그림파일=os.path.relpath(길, 받은),
                 미리보기=os.path.relpath(썸, 받은))
        # 로고 이름 판정은 그림 파일 자신의 이름으로만 — 문서 이름('2026 CI 개편 추진 결과.hwpx')으로 재면 그 안의 사진까지
        # 모두 '로고 추정'이 됐다(review_practice2 N8 덧)
        종류 = e.get("종류") or _종류추정(im, c.get("표시mm"), 이름 if _래스터꼴.search(이름) else "")
        c["종류"] = 종류
        if 종류 == "로고 추정":
            c.update(쓸수있음=False, 까닭="로고·상징으로 보여 본문 그림으로 쓰지 않습니다")
        elif 종류 == "도식·글 그림":
            # 흰 바탕에 글·선이 많은 그림(도식·표 캡처, 결재란 서명·도장) — 정책이 '표·도식으로 다시 쓴다'인 것을 목록이
            # '쓸 수 있음'으로 올리면 약한 모델은 목록을 믿는다(review_practice2 §2-7·N8). 사람은 편집기에서 고를 수 있다
            c.update(쓸수있음=False, 까닭="글자나 선이 많은 그림(도식·표 캡처·서명)으로 보여 본문 그림으로 쓰지 않습니다. "
                                        "이런 내용은 표나 도식으로 다시 만듭니다.")
        else:
            c["쓸수있음"] = True
        if e.get("가림"):
            c["가림"] = True      # PDF — 렌더에서 잘랐으니 가린 그대로 보인다
        카드.append(c)
    return 카드


def _같은그림묶기(목록):
    """거의 같은 그림(같은 사진을 PNG·JPEG 로 따로 저장한 것)을 서로 '같은그림' 으로 가리킨다."""
    from PIL import Image
    받은 = 자료뿌리.받은것뿌리()
    표 = {}
    for ent in 목록.get("파일들", {}).values():
        for c in ent.get("카드") or []:
            c.pop("같은그림", None)
            if c.get("id") and c["id"] not in 표 and c.get("미리보기"):
                try:
                    with Image.open(os.path.join(받은, c["미리보기"])) as t:
                        표[c["id"]] = t.convert("RGB").resize((32, 32)).tobytes()
                except Exception:
                    pass
    ids = sorted(표)
    짝 = {}
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            a, b = 표[ids[x]], 표[ids[y]]
            if sum(abs(a[k] - b[k]) for k in range(len(a))) / len(a) < _닮음문턱:
                짝.setdefault(ids[x], []).append(ids[y])
                짝.setdefault(ids[y], []).append(ids[x])
    for ent in 목록.get("파일들", {}).values():
        for c in ent.get("카드") or []:
            if c.get("id") in 짝:
                c["같은그림"] = 짝[c["id"]]


def _안쓰는그림치우기(목록):
    폴더 = 그림폴더()
    산 = {c["id"] for ent in 목록.get("파일들", {}).values() for c in ent.get("카드") or [] if c.get("id")}
    for 곳 in (폴더, os.path.join(폴더, "thumb")):
        if not os.path.isdir(곳):
            continue
        for f in os.listdir(곳):
            if f.startswith("img-") and f.endswith(".png") and f[:-4] not in 산:
                try:
                    os.remove(os.path.join(곳, f))
                except OSError:
                    pass


def _목록읽기():
    try:
        with open(_목록길(), encoding="utf-8") as f:
            v = json.load(f)
        v = v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}
    if v.get("판") != _카드판:
        _옛판문서그림치우기(v)
    return v


def _옛판문서그림치우기(목록):
    """옛 판 목록(판 3 이하)이 한글·워드 문서에서 꺼내 둔 그림 파일·썸네일을 **읽는 즉시** 지운다('26-09-30 Q6, verify_fixup4 N2 —
    목록을 다시 만들기 전에는 그 파일이 받은 자료 폴더에 남아 옛 꼴 경로로 실렸다). 카드 줄은 카드들()이 걸러 싣지 않는다."""
    받은 = os.path.realpath(자료뿌리.받은것뿌리())
    폴더 = os.path.realpath(그림폴더())
    for f, ent in ((목록.get("파일들") or {}).items() if isinstance(목록.get("파일들"), dict) else []):
        if not 문서파일인가(f) or not isinstance(ent, dict):
            continue
        for c in ent.get("카드") or []:
            for k in ("그림파일", "미리보기"):
                v = c.get(k) if isinstance(c, dict) else None
                if not isinstance(v, str) or not v:
                    continue
                r = os.path.realpath(os.path.join(받은, v))
                if r.startswith(폴더 + os.sep) and os.path.basename(r).startswith("img-") and os.path.isfile(r):
                    try:
                        os.remove(r)
                    except OSError:
                        pass


def _받은파일들():
    받은 = 자료뿌리.받은것뿌리()
    if not os.path.isdir(받은):
        return []
    return sorted(f for f in os.listdir(받은)
                  if not f.startswith(".") and f != "README.md" and os.path.isfile(os.path.join(받은, f)))


def _도구지문():
    """위임하는 쪽(그림 도구 없는 파이썬 — 플러그인 mcp/.venv)이 넘기는 그림 도구 파이썬의 지문 — '경로|바뀐 시각(ns)'
    ('26-10-01 주관 판정 Q2). bootstrap 이 .hwpxenv 를 다시 만들면 바뀐다. 이 파이썬에 도구가 있거나 위임 자식이면 None(넘기지
    않으니 견줄 도구가 없다)."""
    if os.environ.get("문서지능_그림위임") == "1":
        return None
    try:
        import fitz  # noqa: F401
        from PIL import Image  # noqa: F401
        return None
    except ImportError:
        pass
    py = _그림파이썬()
    if not py:
        return None
    try:
        return f"{py}|{os.lstat(py).st_mtime_ns}"
    except OSError:
        return py


def _범인그대로(e, st, 도구=None):
    """위임 자식을 죽인 범인 항목('26-10-01 주관 판정 Q2)이 그대로인가 — 파일 지문(크기·수정 시각 ns)이 같고, 도구(넘기는 그림
    도구 파이썬 지문)를 주면 그것도 같을 때. 그대로인 동안은 위임에서 빼고 낡았다고 보지 않는다(매 부름 전체 재위임·대기를 멈춘다)."""
    if not e.get("범인"):
        return False
    if e.get("크기") != st.st_size or e.get("시각ns") != st.st_mtime_ns:
        return False
    return 도구 is None or e.get("도구") == 도구


def _낡았나(목록):
    파일들 = 목록.get("파일들") or {}
    지금 = _받은파일들()
    if set(파일들) != set(지금) or 목록.get("판") != _카드판:
        return True
    받은 = 자료뿌리.받은것뿌리()
    도구 = _도구지문() if any((e or {}).get("범인") for e in 파일들.values()) else None
    for f in 지금:
        st = os.stat(os.path.join(받은, f))
        e = 파일들.get(f) or {}
        if e.get("범인"):
            if not _범인그대로(e, st, 도구):
                return True     # 범인 파일이나 도구 파이썬이 바뀌었다 — 다시 시도한다(Q2)
            continue
        if e.get("크기") != st.st_size or e.get("시각") != int(st.st_mtime) or e.get("판") != _카드판:
            return True        # 판이 다르다 = 도구 없이 표준 라이브러리로만 센 항목(_표준판, T1) — 도구가 있으면 다시 만든다
    return False


_위임카드상한초 = 300      # --카드 자식 한 번의 상한(큰 PDF 시간 초과 — 넘으면 죽이고 일지로 범인을 가린다)
# 카드 목록 갱신(_위임카드) 한 번에 띄울 --카드 자식 수 상한 — 범인이 잇따라도 기다림이 끝없이 늘지 않게(남은 것은 다음 갱신에.
# 도구 한 번 부름(파일읽기 등)이 갱신을 여러 번 부를 수 있어 부름 단위 상한은 아니다)
_위임되풀이상한 = 3
_일지환경 = "문서지능_그림일지"


def _일지쓰기(말, 이름):
    """위임 자식의 처리 일지('26-10-01 주관 판정 Q1) — 파일마다 시작 전·끝난 뒤 한 줄씩. 자식이 죽어도 남게 줄마다 flush·fsync.
    부모가 넘긴 임시 파일(_일지환경)이 있을 때만 쓴다(위임 자식만)."""
    길 = os.environ.get(_일지환경) if os.environ.get("문서지능_그림위임") == "1" else None
    if not 길:
        return
    try:
        with open(길, "a", encoding="utf-8") as f:
            f.write(json.dumps([말, 이름], ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


def _일지범인(길):
    """일지에서 시작만 있고 끝이 없는 파일 **하나** — 없거나 둘 이상이면 None(가리지 못함 → 옛 동작)."""
    시작, 끝 = [], set()
    try:
        with open(길, encoding="utf-8") as f:
            for 줄 in f:
                try:
                    말, 이름 = json.loads(줄)
                except Exception:
                    continue
                if 말 == "시작" and 이름 not in 시작:
                    시작.append(이름)
                elif 말 == "끝":
                    끝.add(이름)
    except OSError:
        return None
    남 = [x for x in 시작 if x not in 끝]
    return 남[0] if len(남) == 1 else None


def _죽은빗장치우기(pid):
    """죽은 위임 자식이 쥐고 있던 카드 목록 빗장을 치운다 — 임자 표가 그 자식(pid)일 때만(남의 잠금은 건드리지 않는다).
    두면 다음 부름이 20초를 기다린 뒤 못잠금으로 선다(빗장 묵힘 60초)."""
    import shutil
    방 = 자료뿌리.빗장길(_목록길())
    try:
        with open(os.path.join(방, "임자"), encoding="utf-8") as f:
            임자 = f.read().strip()
    except OSError:
        return
    if 임자.split(":", 1)[0] == str(pid):
        shutil.rmtree(방, ignore_errors=True)


def _범인적기(이름):
    """범인 파일을 지문(경로·크기·수정 시각 ns)·도구 지문과 함께 목록에 '처리못함'으로 남긴다('26-10-01 주관 판정 Q2) — 같은
    동안은 위임에서 빼고(_범인그대로), 바뀌면 다시 시도한다. 끝난 파일 항목(자식이 파일마다 써 둔 것)은 그대로 둔다."""
    받은 = 자료뿌리.받은것뿌리()
    폴더 = 그림폴더()
    os.makedirs(폴더, exist_ok=True)
    with 자료뿌리.빗장(_목록길()):
        try:
            st = os.stat(os.path.join(받은, 이름))
        except OSError:
            return
        목록 = _목록읽기()
        파일들 = 목록.setdefault("파일들", {})
        파일들[이름] = {"판": _카드판, "크기": st.st_size, "시각": int(st.st_mtime), "시각ns": st.st_mtime_ns,
                     "올린차례": st.st_mtime, "범인": True, "처리못함": True, "도구": _도구지문(),
                     "카드": _카드마무리(이름, [dict(자리={}, 종류="꺼낼 수 없음", 까닭="이 파일에서 그림을 꺼내다 멈췄습니다")],
                                       폴더, {})}
        목록["판"] = _카드판
        자료뿌리.원자json(_목록길(), 목록, ensure_ascii=False, indent=1)


def _범인다시보기():
    """파일이나 도구 파이썬이 바뀐 범인 항목을 지운다 — 자식이 다시 시도한다(Q2). 그대로인 범인은 남긴다(자식이 건너뛴다)."""
    목록 = _목록읽기()
    if not any((e or {}).get("범인") for e in (목록.get("파일들") or {}).values()):
        return
    받은 = 자료뿌리.받은것뿌리()
    도구 = _도구지문()
    with 자료뿌리.빗장(_목록길()):
        목록 = _목록읽기()
        파일들 = 목록.get("파일들") or {}
        바뀜 = False
        for f, e in list(파일들.items()):
            if not (e or {}).get("범인"):
                continue
            try:
                st = os.stat(os.path.join(받은, f))
            except OSError:
                continue
            if not _범인그대로(e, st, 도구):
                del 파일들[f]
                바뀜 = True
        if 바뀜:
            자료뿌리.원자json(_목록길(), 목록, ensure_ascii=False, indent=1)


def _위임한번(py, 일지):
    """--카드 자식 한 번 — (돌림값, 표준출력, 표준오류, 시간초과). 상한을 넘으면 죽인다(SIGKILL)."""
    env = 자료뿌리.자식환경()
    env["문서지능_그림위임"] = "1"
    env[_일지환경] = 일지
    p = subprocess.Popen([py, os.path.abspath(__file__), "--카드"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=env)
    try:
        out, err = p.communicate(timeout=_위임카드상한초)
        초과 = False
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        초과 = True
    for 줄 in (err or "").splitlines():
        if 줄.startswith("[그림]"):
            print(줄, file=sys.stderr)       # 자식이 남긴 까닭(도구가 없어 표준 라이브러리로 셌다 …)을 버리지 않는다
    return p.returncode, out or "", p.pid, 초과


def _위임카드():
    """Pillow·PyMuPDF 없는 파이썬이 build/.hwpxenv 의 --카드 자식에게 카드 만들기를 넘긴다.
    ('26-10-01 주관 판정 Q1·Q2, verify_fixup9 B1) 자식은 파일마다 시작 전·끝난 뒤 일지를 적는다. 자식이 시간 초과·충돌로 죽으면
    일지에서 시작만 있고 끝이 없는 파일 하나를 범인으로 목록에 남기고(지문과 함께 — 같은 동안은 다시 넘기지 않는다), 끝난 파일의
    카드는 살린 채 남은 파일을 다시 넘긴다(갱신 한 번에 자식 _위임되풀이상한 번까지). 범인을 못 가리면(시작 줄 없음 등) 옛 동작 —
    RuntimeError 로 올려 카드갱신이 처리 못 한 파일마다 표지를 둔다."""
    py = _그림파이썬()
    if not py or os.environ.get("문서지능_그림위임") == "1":
        raise 도구없음("올린 자료에서 그림을 꺼낼 도구(Pillow·PyMuPDF)가 없습니다. bin/bootstrap.sh를 다시 실행해 주세요.")
    import tempfile
    _범인다시보기()
    까닭 = ""
    for _ in range(_위임되풀이상한):
        fd, 일지 = tempfile.mkstemp(prefix="문서지능-그림일지-", suffix=".jsonl")
        os.close(fd)
        try:
            rc, out, pid, 초과 = _위임한번(py, 일지)
            if rc == 0 and not 초과:
                return _목록읽기()
            if not 초과:
                try:
                    값 = json.loads(out.strip().splitlines()[-1])
                except Exception:
                    값 = {}
                if 값.get("종류") == "도구없음":
                    # 넘긴 .hwpxenv 에도 도구가 없다(bootstrap 에서 pip 가 막혀 빈 venv — verify_fixup7 N-T1b)
                    raise 도구없음(값.get("말") or "올린 자료에서 그림을 꺼낼 도구(Pillow·PyMuPDF)가 없습니다.")
            범 = _일지범인(일지)
        finally:
            try:
                os.remove(일지)
            except OSError:
                pass
        _죽은빗장치우기(pid)
        까닭 = "시간 초과" if 초과 else f"rc={rc}"
        if not 범:
            raise RuntimeError(f"그림 목록 위임 실패({까닭})")
        _범인적기(범)
        print(f"[그림] 그림 도구 자식이 '{범}' 에서 멈춰({까닭}) 그 파일만 빼고 다시 넘깁니다 — 그 파일은 바뀌기 전까지 다시 "
              "넘기지 않습니다", file=sys.stderr)
    raise RuntimeError(f"그림 목록 위임 실패({까닭} — 갱신 한 번의 자식 {_위임되풀이상한}번을 다 썼습니다)")


_표준판 = "표준"      # 도구 없이 표준 라이브러리로만 센 파일 항목의 판(T1) — _카드판 과 달라 도구가 생기면 다시 만든다
_표준알림 = False


def _표준카드갱신(처리못함=False):
    """그림 도구가 하나도 없을 때(이 파이썬에 Pillow·PyMuPDF 가 없고 넘길 build/.hwpxenv 도 없다 — '26-10-01 주관 판정 T1,
    verify_fixup6 B1) 한글·워드 문서의 그림 **자리만** 표준 라이브러리(zip·XML)로 세어 목록에 둔다. 해시 없는 '문서 속 사진'
    카드(id·그림 파일 없음)와 글지문이 서고, 알림 줄(문서사진말)은 짝 없이 문서 사진 수로 선다 — 조용히 빠지지 않게. HWP 는
    kordoc 이 세면 그 수, 못 세면 '사진이 들었을 수 있습니다'(사진모름). PDF·그림 파일은 카드가 없다(카드오류가 알린다).
    도구로 만든 항목(판 _카드판)은 그대로 둔다. 이렇게 센 항목은 판이 _표준판이라 도구가 생기면 다시 만든다(_낡았나).
    처리못함=참 — 도구는 있는데 위임 자식이 죽었다('26-10-01 주관 판정 P1): 도구로 만들지 못한 그림 파일·PDF 항목에 '처리못함'
    표지를 둔다(목록에 남아 편집기 서버 같은 읽기만 하는 새 프로세스도 같은 줄을 세운다 — 처리못한파일들)."""
    global _표준알림
    받은 = 자료뿌리.받은것뿌리()
    폴더 = 그림폴더()
    os.makedirs(폴더, exist_ok=True)
    with 자료뿌리.빗장(_목록길()):
        _묵은임시치우기()
        목록 = _목록읽기()
        파일들 = 목록.setdefault("파일들", {})
        지금 = _받은파일들()
        바뀜 = 목록.get("판") != _카드판
        for f in list(파일들):
            if f not in 지금:
                del 파일들[f]
                바뀜 = True
        센 = 0
        for f in 지금:
            p = os.path.join(받은, f)
            st = os.stat(p)
            옛 = 파일들.get(f) or {}
            if 옛.get("판") in (_카드판, _표준판) and 옛.get("크기") == st.st_size and 옛.get("시각") == int(st.st_mtime):
                continue
            덧 = {}
            원 = []
            if _문서종류(p):
                try:
                    원 = _꺼내기(p, f, 덧)
                except Exception as exc:
                    print(f"[imageasset] 그림 자리 세기 실패 {f}: {type(exc).__name__}", file=sys.stderr)
                    원 = [dict(자리={}, 종류="꺼낼 수 없음", 까닭="이 파일에서 그림을 꺼내지 못했습니다")]
                센 += 1
            파일들[f] = {"판": _표준판, "크기": st.st_size, "시각": int(st.st_mtime), "올린차례": st.st_mtime,
                       "카드": _카드마무리(f, 원, 폴더, {})}
            if 덧.get("글지문") and (덧["글지문"].get("수") or 0) >= 30:
                파일들[f]["글지문"] = 덧["글지문"]
            바뀜 = True
        if 처리못함:
            for f in 지금:
                e = 파일들.get(f) or {}
                if e.get("판") != _카드판 and not e.get("처리못함") and not _문서종류(os.path.join(받은, f)) \
                        and (_래스터꼴.search(f) or f.lower().endswith(".pdf")):
                    e["처리못함"] = True
                    바뀜 = True
        if 바뀜:
            목록["판"] = _카드판
            자료뿌리.원자json(_목록길(), 목록, ensure_ascii=False, indent=1)
    if 처리못함:
        print("[그림] 그림 도구로 목록을 만들다 멈춰(위임 자식이 죽음·시간 초과), 한글·워드 문서 속 사진 자리만 표준 라이브러리로 "
              "셉니다 — 도구로 처리하지 못한 그림 파일·PDF 는 확인할 것에 파일마다 올립니다", file=sys.stderr)
    elif 센 or not _표준알림:
        _표준알림 = True
        print("[그림] 그림 도구(Pillow·PyMuPDF)가 이 파이썬에도 build/.hwpxenv 에도 없어, 한글·워드 문서 속 사진 자리만 표준 "
              "라이브러리(zip·XML)로 셉니다 — 해시·미리보기가 없어 짝(따로 올린 사진·같은 문서의 PDF)은 세지 못하고, PDF·그림 "
              "파일의 그림 카드는 만들지 않습니다(bin/bootstrap.sh 를 다시 실행해 주세요)", file=sys.stderr)
    return 목록


def 카드갱신():
    """받은 자료 폴더의 첨부마다 그림 카드를 만든다(바뀐 파일만 다시). 목록(dict)을 돌려준다.
    Pillow·PyMuPDF 가 없는 파이썬(플러그인 mcp/.venv)에서는 build/.hwpxenv 로 넘긴다. 넘길 곳도 없으면 문서 속 사진 자리만
    표준 라이브러리로 세어 목록에 두고(_표준카드갱신, T1) 도구없음을 그대로 올린다(카드들 이 카드오류로 알린다)."""
    목록 = _목록읽기()
    if not _받은파일들() and not 목록.get("파일들"):
        return {"판": _카드판, "파일들": {}}
    if not _낡았나(목록):
        return 목록
    try:
        import fitz  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        try:
            목록 = _위임카드()
            _도구검사기억(False)
            return 목록
        except Exception as exc:
            # 넘길 곳이 없거나(도구없음) 넘긴 .hwpxenv 파이썬이 뜨지 못하거나 PIL 을 못 불러오면 '도구 없음'('26-10-01 주관 판정
            # P1 — 가벼운 검사 _도구검사 를 새로 한 번). 검사가 멀쩡하면 자식이 한 번 죽은 것(시간 초과·충돌 — verify_fixup8 V1)이라
            # 도구 없음이 아니다: 처리하지 못한 파일에만 표지를 둔다. 어느 쪽이든 문서 속 사진 자리는 표준 라이브러리로 센다
            없음 = isinstance(exc, 도구없음) or _도구검사(새로=True)
            if isinstance(exc, 도구없음):
                _도구검사기억(True)
            try:
                _표준카드갱신(처리못함=not 없음)
            except Exception as exc2:
                print(f"[imageasset] 문서 속 사진 자리를 세지 못했습니다: {type(exc2).__name__}: {exc2}", file=sys.stderr)
            raise
    import hashlib
    받은 = 자료뿌리.받은것뿌리()
    폴더 = 그림폴더()
    os.makedirs(폴더, exist_ok=True)
    with 자료뿌리.빗장(_목록길()):
        _묵은임시치우기()
        목록 = _목록읽기()
        파일들 = 목록.setdefault("파일들", {})
        지금 = _받은파일들()
        for f in list(파일들):
            if f not in 지금:
                del 파일들[f]
        쓰인 = {}
        for ent in 파일들.values():
            for c in ent.get("카드") or []:
                if c.get("id") and c.get("해시"):
                    쓰인[c["id"]] = c["해시"]
        일지 = bool(os.environ.get(_일지환경)) and os.environ.get("문서지능_그림위임") == "1"
        for f in 지금:
            p = os.path.join(받은, f)
            st = os.stat(p)
            옛 = 파일들.get(f) or {}
            if 옛.get("범인"):
                if _범인그대로(옛, st):
                    continue       # 위임 자식을 죽인 파일 — 바뀌기 전까지 다시 꺼내지 않는다('26-10-01 주관 판정 Q2)
                옛 = {}
            if 옛.get("판") == _카드판 and 옛.get("크기") == st.st_size and 옛.get("시각") == int(st.st_mtime):
                continue
            _일지쓰기("시작", f)        # (Q1) 시작 전·끝난 뒤 — 자식이 죽으면 부모가 시작만 있는 파일 하나를 범인으로 본다
            with open(p, "rb") as fh:
                h = hashlib.sha1(fh.read(), usedforsecurity=False).hexdigest()[:16]
            if 옛.get("판") == _카드판 and 옛.get("해시") == h:
                옛.update(크기=st.st_size, 시각=int(st.st_mtime))
                _일지쓰기("끝", f)
                continue
            덧 = {}
            try:
                원 = _꺼내기(p, f, 덧)
            except Exception as exc:
                print(f"[imageasset] 그림 꺼내기 실패 {f}: {type(exc).__name__}", file=sys.stderr)
                원 = [dict(자리={}, 종류="꺼낼 수 없음", 까닭="이 파일에서 그림을 꺼내지 못했습니다")]
            파일들[f] = {"판": _카드판, "해시": h, "크기": st.st_size, "시각": int(st.st_mtime),
                       "올린차례": st.st_mtime, "카드": _카드마무리(f, 원, 폴더, 쓰인)}
            # 거절 해시(문서 속 그림 — Q2)·글지문(짝 PDF — Q4)은 카드 밖, 이 파일 항목에만 둔다(카드를 싣는 어느 길로도 나가지 않게)
            if 덧.get("거절"):
                파일들[f]["거절"] = 덧["거절"]
            if 덧.get("글지문") and (덧["글지문"].get("수") or 0) >= 30:
                파일들[f]["글지문"] = 덧["글지문"]
            if 일지:
                # 위임 자식은 파일마다 목록을 써 둔다 — 다음 파일에서 죽어도 끝난 파일의 카드를 살린다(Q1)
                목록["판"] = _카드판
                자료뿌리.원자json(_목록길(), 목록, ensure_ascii=False, indent=1)
            _일지쓰기("끝", f)
        _같은그림묶기(목록)
        _안쓰는그림치우기(목록)
        목록["판"] = _카드판
        자료뿌리.원자json(_목록길(), 목록, ensure_ascii=False, indent=1)
    return 목록


def _자리말(c):
    자 = c.get("자리") or {}
    if "쪽" in 자:
        return f"{c.get('파일')} {자['쪽']}쪽"
    if "순번" in 자:
        return f"{c.get('파일')} {자['순번']}번째 그림"
    return str(c.get("파일") or "")


_카드오류말 = ""
# ('26-10-01 주관 판정 P1) 그림 도구 검사 — {파이썬 경로: (잰 시각, 없나)}. 이 프로세스 안에 잠깐(_도구검사수명 초)만 기억한다:
# bootstrap 을 다시 돌리면 곧 다시 잰다. 파일로 남기지 않는다(편집기 서버 같은 새 프로세스는 제가 한 번 잰다 — P5).
_도구검사표 = {}
_도구검사수명 = 60.0


def _도구검사(새로=False):
    """그림 도구가 없나 — **그림 도구 파이썬이 뜨지 못하거나 PIL(·PyMuPDF)을 불러오지 못할 때만** 참('26-10-01 주관 판정 P1).
    이 파이썬에 있으면 거짓. 없으면 넘길 build/.hwpxenv 파이썬을 `-c import` 로 한 번 띄워 본다(가벼운 검사, 잠깐 기억).
    위임 자식이 큰 PDF 에서 시간 초과·충돌로 한 번 죽은 것은 여기서 가리지 않는다(verify_fixup8 V1 — 파일 단위 줄로 간다)."""
    try:
        import fitz  # noqa: F401
        from PIL import Image  # noqa: F401
        return False
    except ImportError:
        pass
    py = _그림파이썬()
    if not py or os.environ.get("문서지능_그림위임") == "1":
        return True
    import time
    지금 = time.time()
    e = _도구검사표.get(py)
    if e and not 새로 and 지금 - e[0] < _도구검사수명:
        return e[1]
    try:
        r = subprocess.run([py, "-c", "from PIL import Image; import fitz"], capture_output=True, timeout=30)
        없 = r.returncode != 0
    except (OSError, subprocess.SubprocessError):
        없 = True
    _도구검사표[py] = (지금, 없)
    return 없


def _도구검사기억(없):
    """카드갱신이 도구 있음(위임 성공)·없음(자식이 도구없음을 알림)을 알았으면 검사 없이 기억한다."""
    py = _그림파이썬()
    if py:
        import time
        _도구검사표[py] = (time.time(), bool(없))


def 도구없나():
    """그림 도구(Pillow·PyMuPDF — 이 파이썬에도 넘길 build/.hwpxenv 에도)가 없거나 뜨지 못해 올린 그림 파일·PDF 의 카드를 만들 수
    없나('26-10-01 주관 판정 S2 → P1). 가벼운 검사(_도구검사, 잠깐 기억)로 본다 — 자식이 한 번 죽은 것은 도구 없음이 아니다."""
    return _도구검사()


_pdf그림캐시 = {}


def _pdf그림있나(p):
    """PDF 에 그림(이미지 XObject)이 드나 — 표준 라이브러리로 파일 바이트에서 '/Subtype /Image' 를 찾는다(도구 없이, P2). 스트림은
    객체 스트림 안에 들 수 없어(PDF 명세) 이미지 사전은 압축 밖에 보인다. 본문 속 인라인 그림(BI … ID)은 못 본다(드물다)."""
    try:
        st = os.stat(p)
    except OSError:
        return False
    열쇠 = (p, st.st_size, int(st.st_mtime))
    if 열쇠 not in _pdf그림캐시:
        try:
            with open(p, "rb") as f:
                b = f.read(200 * 1024 * 1024)
            _pdf그림캐시[열쇠] = bool(re.search(rb"/Subtype\s*/Image\b", b))
        except OSError:
            _pdf그림캐시[열쇠] = False
    return _pdf그림캐시[열쇠]


def 처리못한파일들(파일들=None, 표지만=False):
    """도구로 카드를 만들지 못한 그림 파일·그림 든 PDF 이름들('26-10-01 주관 판정 P2) — 목록 항목이 없거나 도구 판(_카드판)이
    아닌 것(표준 라이브러리로만 센 항목), 또는 위임 자식이 죽어 '처리못함' 표지가 선 것. 도구로 이미 카드가 선 파일(쓸 수 있는
    사진 카드 — 실렸든 아니든)은 세지 않는다(verify_fixup8 V1). PDF 는 그림이 드는 것만(_pdf그림있나 — 글만 든 PDF 는 아니다).
    표지만=참 — '처리못함' 표지가 선 것만(도구는 있는데 자식이 죽음). 파일들 = 이 대화·이 문서의 자료 이름(None 이면 전부)."""
    import unicodedata
    받은 = 자료뿌리.받은것뿌리()
    있는 = {unicodedata.normalize("NFC", f): f for f in _받은파일들()}
    이름들 = list(있는.values()) if 파일들 is None else \
        [있는[k] for k in dict.fromkeys(unicodedata.normalize("NFC", str(x)) for x in 파일들 if x) if k in 있는]
    목 = _목록읽기().get("파일들") or {}
    out = []
    for f in 이름들:
        if not (_래스터꼴.search(f) or f.lower().endswith(".pdf")):
            continue
        p = os.path.join(받은, f)
        if _문서종류(p):
            continue
        e = 목.get(f) or {}
        if 표지만:
            if not e.get("처리못함"):
                continue
        elif e.get("판") == _카드판 and not e.get("처리못함"):
            continue
        if f.lower().endswith(".pdf") and not _pdf그림있나(p):
            continue
        out.append(f)
    return out


def 그림도구줄(파일들=None):
    """그림 도구가 없거나 뜨지 못해 **카드를 못 만든 그림 파일·그림 든 PDF** 가 있을 때의 한 줄 — 없으면 ''('26-10-01 주관 판정
    S2 → P2, verify_fixup7 F1·verify_fixup8 V2). 문서 속 사진 카드가 목록을 채워도 가려지지 않는다. 도구로 이미 카드가 선 사진은
    세지 않는다. 파일들 = 이 대화·이 문서의 자료 이름(None 이면 받은 자료 폴더 전체)."""
    if not 도구없나():
        return ""
    return 그림도구말 if 처리못한파일들(파일들) else ""


def 못쓴줄들(파일들=None):
    """올린 그림 파일·PDF 를 도구로 처리하지 못했을 때 사람에게 알릴 줄들 — 도구가 없으면 도구 줄 하나(그림도구줄), 도구는 있는데
    위임 자식이 죽었으면 그 파일마다 처리못함말('26-10-01 주관 판정 P1 — 거짓 '도구 없음' 금지). 없으면 [].
    ('26-10-01 주관 판정 Q3·Q7·Q8) 위임 자식을 죽인 범인은 범인문서말·범인사진말(이름을 대고 '다시 올려' 없음 — 범위 밖 범인은
    줄 없음), 도구 있는 곳에서 깨진 사진 파일(잘림·0바이트 — 카드가 모두 '꺼낼 수 없음')은 범인사진말. 차례는 올린 차례(같으면
    이름) — 확인할것·편집기 서랍·파일읽기가 범위 이름 차례와 상관없이 같은 차례를 본다(N5)."""
    if 도구없나():
        도 = 그림도구줄(파일들)
        return [도] if 도 else []
    import unicodedata
    받은 = 자료뿌리.받은것뿌리()
    있는 = {unicodedata.normalize("NFC", f): f for f in _받은파일들()}
    이름들 = list(있는.values()) if 파일들 is None else \
        [있는[k] for k in dict.fromkeys(unicodedata.normalize("NFC", str(x)) for x in 파일들 if x) if k in 있는]
    목 = _목록읽기().get("파일들") or {}
    못 = set(처리못한파일들(이름들, 표지만=True))
    줄 = []
    for f in 이름들:
        e = 목.get(f) or {}
        p = os.path.join(받은, f)
        사진 = bool(_래스터꼴.search(f)) and not _문서종류(p)
        if e.get("범인"):
            if f.lower().endswith(".pdf") and not _pdf그림있나(p):
                continue                      # 글만 든 PDF — 쓰지 못한 사진이 없다
            말 = (범인사진말 if 사진 else 범인문서말).format(이름=f)
        elif f in 못:
            말 = 처리못함말.format(이름=f)
        elif 사진 and e.get("판") == _카드판 and e.get("카드") \
                and all(c.get("종류") == "꺼낼 수 없음" and not c.get("id") for c in e["카드"]):
            말 = 범인사진말.format(이름=f)       # (Q7) 도구는 있는데 사진 파일이 깨졌다
        else:
            continue
        차 = e.get("올린차례")
        if not isinstance(차, (int, float)):
            try:
                차 = os.stat(p).st_mtime
            except OSError:
                차 = 0
        줄.append((차, f, 말))
    return [m for _, _, m in sorted(줄)]


def 카드오류():
    """마지막 카드들() 이 목록을 만들지 못한 까닭(사람 말) — 없으면 ''. 도구가 없을 때 지시문·그림목록이 '올린 자료에
    그림이 없다'고 거짓으로 말하지 않게('26-09-30 fixup, review_impl2 M5)."""
    return _카드오류말


def 카드들(갱신=True, 파일들=None):
    """카드 한 줄 목록 — 올린 차례, 파일 안 자리 차례. 같은 id 는 한 장(첫 자리)으로 두고 뒤 자리는 '또있음'.

    파일들(이름 모음)을 주면 그 파일의 카드만 싣는다('26-09-30 주관 판정, review_impl2 M6①) — 플러그인은 받은 자료 폴더
    하나를 모든 대화가 같이 써서, 다른 작업·다른 대화의 첨부가 카드·편집기 서랍에 올랐다. 무엇을 싣는지(이 대화에서 올리거나
    읽은 자료·이 문서에 묶인 자료)는 부르는 쪽(api._그림범위)이 정한다. None 이면 거르지 않는다(세션 방 = 이 세션의 자료)."""
    global _카드오류말
    try:
        목록 = 카드갱신() if 갱신 else _목록읽기()
        if 갱신:
            _카드오류말 = ""
    except Exception as exc:
        print(f"[imageasset] 그림 목록을 못 만들었습니다: {type(exc).__name__}: {exc}", file=sys.stderr)
        _카드오류말 = ("올린 자료에서 그림을 꺼낼 도구(Pillow·PyMuPDF)가 없어 그림 목록을 만들지 못했습니다. "
                    "bin/bootstrap.sh를 다시 실행해 주세요." if isinstance(exc, 도구없음) else
                    # 넘긴 .hwpxenv 파이썬이 뜨지 못함·PIL 을 못 불러옴('26-10-01 주관 판정 S2·P1 — 도구가 깨짐). 뜨고 PIL 도
                    # 불러오는데 자식이 한 번 죽은 것(시간 초과·충돌)은 아래 '멈춰서'(P1 — 도구 없음이 아니다)
                    "그림 도구(build/.hwpxenv)가 깨져 올린 자료의 그림 목록을 만들지 못했습니다. bin/bootstrap.sh를 다시 "
                    "실행해 주세요." if 도구없나() else
                    "그림을 꺼내다 멈춰서 올린 자료의 그림 목록을 만들지 못했습니다.")
        목록 = _목록읽기()
    import unicodedata
    고른 = None if 파일들 is None else {unicodedata.normalize("NFC", str(x)) for x in 파일들 if x}
    out, 본 = [], {}
    for f, ent in sorted((목록.get("파일들") or {}).items(), key=lambda kv: (kv[1].get("올린차례", 0), kv[0])):
        if 고른 is not None and unicodedata.normalize("NFC", f) not in 고른:
            continue
        for c in ent.get("카드") or []:
            if 문서파일인가(f) and (c.get("id") or c.get("그림파일")):
                # 옛 목록(판 3 이하)을 다시 만들기 전에 읽은 한글·워드 문서 카드 — id·그림 파일 없는 '문서 속 사진'으로(P1)
                c = {k: v for k, v in c.items() if k in ("파일", "자리", "곁글", "비밀표지", "표시mm", "문서")}
                c.update(종류=문서사진, 쓸수있음=False, 까닭=문서사진까닭)
            cid = c.get("id")
            if cid and cid in 본:
                본[cid].setdefault("또있음", []).append(_자리말(c))
                continue
            cc = dict(c)
            out.append(cc)
            if cid:
                본[cid] = cc
    return out


def _문서자료길():
    return os.path.join(그림폴더(), "문서자료.json")


def 문서자료(키):
    """이 문서(key)에 묶인 받은 자료 파일 이름들 — 새문서·저장 때 그 대화에서 올리거나 읽은 자료와 문서가 쓴 그림의 파일을
    적어 둔다('26-09-30 주관 판정 M6①). 대화가 바뀌어도(편집기 서버·새 대화) 이 문서의 카드·서랍은 이 파일들로 좁힌다."""
    if not 키:
        return []
    try:
        with open(_문서자료길(), encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return []
    e = v.get(str(키)) if isinstance(v, dict) else None
    return [x for x in (e.get("파일") if isinstance(e, dict) else []) or [] if isinstance(x, str)]


def 문서자료묶기(키, 파일들):
    """문서 key 에 받은 자료 파일 이름을 더한다(지우지 않는다). 받은 자료 폴더에 없는 이름은 뺀다."""
    import time
    받은 = set(_받은파일들())
    새 = [x for x in (파일들 or []) if isinstance(x, str) and x in 받은]
    if not 키 or not 새:
        return 문서자료(키)
    길 = _문서자료길()
    os.makedirs(os.path.dirname(길), exist_ok=True)
    with 자료뿌리.빗장(길):
        try:
            with open(길, encoding="utf-8") as f:
                v = json.load(f)
            v = v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            v = {}
        e = v.get(str(키)) if isinstance(v.get(str(키)), dict) else {}
        옛 = [x for x in e.get("파일") or [] if isinstance(x, str)]
        합 = 옛 + [x for x in 새 if x not in 옛]
        if 합 != 옛:
            v[str(키)] = {"파일": 합, "시각": time.time()}
            자료뿌리.원자json(길, v, ensure_ascii=False, indent=1)
    return 합


def 사진파일인가(이름, 카드=None):
    """올린 그림 파일(PNG·JPEG…)이 사진인가 — 카드가 모두 '사진·삽화'면 참. 사진 속 글자(간판·번호판·이름표·화면)는 OCR 로
    읽어도 자료의 사실이 아니다('26-09-30 주관 판정 ⑥: 사진 OCR 글을 자료 원문에 싣지 않는다). 스캔 쪽·글 그림은 아니다."""
    if not _래스터꼴.search(str(이름 or "")):
        return False
    if 카드 is None:
        카드들()                  # 목록을 새로 만든다(바뀐 파일만)
    # 파일마다의 카드(같은 그림 묶기 전) — 같은 사진을 두 이름으로 올리면 묶인 목록에는 앞 이름만 남는다
    내 = [c for c in (((_목록읽기().get("파일들") or {}).get(이름) or {}).get("카드") or []) if c.get("id")]
    return bool(내) and all(c.get("종류") == "사진·삽화" for c in 내)


def 그림찾기(cid, 카드=None):
    """id → 카드(없으면 None). 목록을 다시 만들지 않고 읽기만 한다(조립·편집기 저장에서 불린다)."""
    if not isinstance(cid, str) or not cid.startswith("img-"):
        return None
    for c in (카드 if 카드 is not None else 카드들(갱신=False)):
        if c.get("id") == cid:
            return c
    return None


def 카드요약(카드=None):
    """'올린 자료 속 그림 5장(사진·삽화 3 · 로고 추정 1 · 선 도식·표 1)' — 판정 화면·로그용 한 줄."""
    카드 = 카드들() if 카드 is None else 카드
    if not 카드:
        return ""
    셈 = {}
    for c in 카드:
        셈[c.get("종류", "?")] = 셈.get(c.get("종류", "?"), 0) + 1
    쓸 = sum(1 for c in 카드 if c.get("쓸수있음"))
    return (f"올린 자료 속 그림 {len(카드)}장(" + " · ".join(f"{k} {v}" for k, v in sorted(셈.items(), key=lambda x: -x[1]))
            + f") — 본문에 쓸 수 있는 것 {쓸}장")


_카드지각캐시 = {}


def _카드지각(c):
    """그림 카드(미리보기 있음)의 (지각 해시, 색결) — 알림 짝 찾기용(Q4). 못 재면 None."""
    from PIL import Image
    if not c.get("미리보기"):
        return None
    길 = os.path.join(자료뿌리.받은것뿌리(), c["미리보기"])
    try:
        열쇠 = (길, os.path.getmtime(길))
    except OSError:
        return None
    if 열쇠 not in _카드지각캐시:
        try:
            with Image.open(길) as t:
                t.load()
                _카드지각캐시[열쇠] = (_지각해시(t.convert("RGB")), _색결(t))
        except Exception:
            _카드지각캐시[열쇠] = None
    return _카드지각캐시[열쇠]


def 문서사진남은수(카드=None):
    """{문서 파일: 알릴 장수} — 한글·워드 문서 속 사진 가운데 **짝이 채우지 않은** 것('26-09-30 주관 판정 Q4, '26-10-01 R1·R2).
    ('26-10-01 주관 판정 S1) 알림 줄(문서사진줄들)은 이 셈으로 빼지 않는다 — 셈 도구로만 남긴다.

    짝은 자리(문서 속 사진 한 장)마다 센다 — 이 범위(카드)에 든 파일만 본다:
      ① 같은 사진을 **그림 파일**(PNG·JPG 등)로 따로 올렸다 — 그 자리의 거절 해시(Q2)와 그림 파일 카드 미리보기의 지각 해시가
         닮으면 채워진 것이다.
      ② 같은 문서를 PDF 로 저장해 함께 올렸다 — 본문 겹침(글지문 서로 담김 ≥ _짝문턱) **그리고** 그 자리의 거절 해시가 그 PDF
         의 카드 하나와 닮을 때만 채워진 것이다(한 PDF 카드는 한 자리만 채운다). ('26-10-01 주관 판정 R1, verify_fixup5 B1)
         전에는 겹침만 보고 그 PDF 의 카드 수만큼 뺐다 — 같은 서식의 **다른 달 보고서**·개정판 PDF(겹침 0.76~0.84, 사진은 다름)
         나 머리 로고 한 장이 문서 사진 알림을 지웠다. 겹침은 '같은 사진이 든 다른 문서의 PDF'를 거르는 문이고, 해시는 그 PDF
         에 이 사진이 실제로 보이는지를 본다.
    잣대는 둘 다 좁게(8비트·색도 0.03 — 채우기 거절 12·0.06 보다 좁다): 알림을 거두는 쪽이라 정밀도 우선이다. 가까운 사본 실측
    (fixup3 N3: 변형 13꼴 0~8비트·색도 0.000~0.009)은 들고, 같은 배치를 다른 색으로 그린 다른 그림(합성 r32 P1)은 뺀다. 한계:
    한글이 문서 안에서 크게 자른 사진은 PDF 판과 해시가 어긋나 알림이 남을 수 있다(정밀도 우선 쪽).

    Pillow 가 없는 파이썬(플러그인 mcp/.venv)은 해시 셈을 build/.hwpxenv 로 넘긴다(자르기·카드 만들기와 같은 길, R2). 넘길 곳도
    없으면 알림을 빼지 않고 짝 없이 문서 사진 수 그대로 돌려준다(까닭은 stderr)."""
    카드 = 카드들() if 카드 is None else 카드
    문서 = {}
    for c in 카드 or []:
        if c.get("종류") == 문서사진:
            문서.setdefault(c.get("파일"), []).append(c)
    if not 문서:
        return {}
    if not _pil있나():
        남 = _위임짝셈(카드)
        if 남 is not None:
            return {f: 남.get(f, len(칸들)) for f, 칸들 in 문서.items()}
        return {f: len(칸들) for f, 칸들 in 문서.items()}
    return _짝셈(카드, 문서)


def _짝셈(카드, 문서):
    목 = _목록읽기().get("파일들") or {}
    범위 = sorted({str(c.get("파일")) for c in 카드 or [] if c.get("파일")})

    def 파일지각(f):
        # 그 파일 자신의 카드(같은 그림 묶기 전 — 묶인 목록에는 앞 파일만 남는다) 가운데 미리보기가 있는 것
        return [v for v in (_카드지각(c) for c in (목.get(f) or {}).get("카드") or [] if c.get("id") and c.get("미리보기"))
                if v]
    그림 = [v for f in 범위 if _래스터꼴.search(f) for v in 파일지각(f)]
    pdf들 = [f for f in 범위 if f.lower().endswith(".pdf")]
    남 = {}
    for f, 칸들 in 문서.items():
        e = 목.get(f) or {}
        거절 = {x.get("순번"): x for x in e.get("거절") or [] if isinstance(x, dict) and x.get("순번") is not None}
        fp = e.get("글지문")
        짝pdf = [p for p in pdf들 if fp and (목.get(p) or {}).get("글지문") and _글겹침(fp, 목[p]["글지문"]) >= _짝문턱]
        pdf그림 = [v for p in 짝pdf for v in 파일지각(p)]
        쓴 = set()
        채움 = 0
        for c in 칸들:
            x = 거절.get((c.get("자리") or {}).get("순번"))
            if not x:
                continue
            try:
                옛 = (list(x["지각"]), tuple(x["색"]))
            except Exception:
                continue
            if any(_지각같음(v, 옛, 문턱=_짝지각문턱, 색도=_짝색도문턱) for v in 그림):
                채움 += 1
                continue
            for i, v in enumerate(pdf그림):
                if i not in 쓴 and _지각같음(v, 옛, 문턱=_짝지각문턱, 색도=_짝색도문턱):
                    쓴.add(i)
                    채움 += 1
                    break
        남[f] = max(0, len(칸들) - 채움)
    return 남


def _위임짝셈(카드):
    """Pillow 없는 파이썬의 짝 셈 — .hwpxenv 로 넘긴다. 못 넘기면 None(부르는 쪽이 짝 없이 전부 알린다) — 까닭은 stderr."""
    py = _그림파이썬()
    if not py or os.environ.get("문서지능_그림위임") == "1":
        print("[그림] 문서 속 사진의 짝(따로 올린 사진·같은 문서의 PDF)을 세지 못했습니다 — 그림 도구(Pillow)가 이 파이썬에도 "
              "build/.hwpxenv 에도 없습니다. 짝을 빼지 않고 문서 속 사진 수 그대로 알립니다(bin/bootstrap.sh 를 다시 실행해 주세요)",
              file=sys.stderr)
        return None
    env = 자료뿌리.자식환경()
    env["문서지능_그림위임"] = "1"
    try:
        r = subprocess.run([py, os.path.abspath(__file__), "--짝셈"], input=json.dumps({"카드": 카드}, ensure_ascii=False),
                           capture_output=True, text=True, timeout=180, env=env)
        값 = json.loads((r.stdout or "").strip().splitlines()[-1])
        return {str(k): int(v) for k, v in (값.get("남") or {}).items()}
    except Exception as exc:
        print(f"[그림] 문서 속 사진의 짝 셈을 build/.hwpxenv 로 넘기지 못했습니다({type(exc).__name__}) — 그림 도구(Pillow)가 "
              "이 파이썬에 없어 짝을 빼지 않고 문서 속 사진 수 그대로 알립니다", file=sys.stderr)
        return None


def 문서사진줄들(카드=None, 자리=True, 파일=None, 실린=(), 범위=None):
    """쓰지 않은 한글·워드 문서 속 사진을 사용자에게 알리는 줄들('26-09-30 주관 판정 P2 → '26-10-01 주관 판정 S1 단순화) — [].

    카드 = 이 대화·이 문서의 범위(짝 PDF 찾기도 이 안에서), 파일 = 알릴 문서 파일 이름 모음(None 이면 범위의 문서 모두 — 파일
    읽기는 그 파일 하나), 실린 = 이 문서에 실린 그림 id(새문서·저장 — (나) 를 거둔다), 범위 = 이 대화·이 문서의 자료 이름(카드
    없는 PDF 도 짝으로 보려고 — _짝pdf사진). 자리=False(그림 자리 없는 장르 — 1p·
    시행문·규정·판형 v2)면 문서 속 사진이 있을 때 자리없음말 한 줄. 파일 이름은 쓰지 않는다('첨부한 한글 문서').
    확인할것(api._그림살피기)·파일읽기 '그림안내'·웹앱 자료 칸·편집기 서랍이 같은 글을 쓴다(한 곳에서 짓는다).

    **빼지 않는다**(S1 — 짝 셈으로 장수를 줄이던 규칙이 차수마다 조용한 빠짐을 새로 냈다: verify_fixup7 F2 PDF 사진이 문서보다
    적거나 두 문서가 PDF 하나에 묶이면 나머지 문서 사진이 사라짐). 두 줄을 각각 센다:
      (가) '첨부한 한글·워드 문서 N개에 든 사진 M장은 쓰지 않았습니다. 넣으려면 …' — 문서 속 사진 카드(도식·표 캡처 같은 글
           그림도 센다) 그대로. 같은 사진을 사진 파일로 올려 실었어도, 짝 PDF 가 있어도 줄이지 않는다(사람이 확인한다).
           뒷문장: 모든 문서에 짝 PDF(본문 겹침 ≥ _짝문턱)가 있으면 — 그 PDF 들에 사진 카드가 있으면 짝사진꼬리('편집 화면에서
           골라 넣을 수 있습니다', P3 — 이미 한 일을 다시 권하지 않는다), 없으면 짝무사진꼬리. 그림 도구가 없거나 뜨지 못하면
           (도구없나 — PDF·사진 파일 카드를 만들 수 없다) 할 수 없는 방법을 권하지 않고 뒷문장을 빼며, 대신 (가) 바로 뒤에 도구 줄
           (그림도구말)을 둔다(P3 — 고칠 길 한 줄은 늘 있게).
      (나) 짝 PDF 에 '사진·삽화' 카드가 있으면 짝PDF말(K = 그 PDF 들의 사진 카드 가운데 이 문서에 **실리지 않은** 수, id 기준) —
           같은 사진인지 단정하지 않는다. 실린 수만큼 줄고 다 실리면 없다(P3).
    HWP 를 kordoc 이 못 셌으면(사진모름) 사진모름말 한 줄을 덧붙인다(자리 있는 장르만, 도구가 없으면 앞 문장 + 도구 줄).
    확인할것·편집기 서랍은 이 줄들에 그림 파일·PDF 줄(못쓴줄들)과 자리 없는 장르의 사진 파일 줄을 더한 확인줄들 을 쓴다."""
    카드 = 카드들() if 카드 is None else 카드
    고른 = None if 파일 is None else set(파일)
    문서카드 = [c for c in 카드 or [] if c.get("종류") == 문서사진 and (고른 is None or c.get("파일") in 고른)]
    모름 = [c for c in 카드 or [] if _사진모름(c) and (고른 is None or c.get("파일") in 고른)]
    if not 문서카드 and not 모름:
        return []
    if not 자리:
        return [자리없음말] if 문서카드 else []
    도구없 = 도구없나()
    줄들 = []
    if 문서카드:
        문서들 = list(dict.fromkeys(str(c.get("파일")) for c in 문서카드))
        종류 = []
        for f in 문서들:
            k = next((c.get("문서") for c in 문서카드 if c.get("파일") == f and c.get("문서")), None) \
                or ("워드" if f.lower().endswith(".docx") else "한글")
            if k not in 종류:
                종류.append(k)
        이름 = "·".join(k for k in ("한글", "워드") if k in 종류)
        짝 = _짝pdf사진(카드, 문서들, 범위)
        말 = f"첨부한 {이름} 문서 {len(문서들)}개에 든 사진 {len(문서카드)}장은 쓰지 않았습니다."
        if 도구없:
            pass
        elif all(짝.get(f) for f in 문서들):
            # 모든 문서에 짝 PDF 가 있다 — PDF 를 이미 올렸으니 'PDF로 저장해'를 다시 권하지 않는다(P3). 그 PDF 에 사진이
            # 있으면 서랍에서 고를 수 있다고, 없으면 사진 파일로
            말 += " " + (짝사진꼬리 if any(ids for f in 문서들 for ids in 짝[f].values()) else 짝무사진꼬리)
        else:
            말 += f" 넣으려면 {이름}에서 PDF로 저장해 함께 올리거나, 사진 파일로 올려 주세요."
        줄들.append(말)
        if 도구없:
            줄들.append(그림도구말)       # 도구 없는 곳은 (가) 뒤에 도구 줄 — 고칠 길 한 줄은 늘 있게(P3, verify_fixup8 N5)
        실 = {x for x in (실린 or ()) if isinstance(x, str)}
        찾은 = set()
        for f in 문서들:
            for ids in (짝.get(f) or {}).values():
                찾은 |= set(ids) - 실          # 실린 수만큼 줄이고 다 실리면 걷는다(P3 — 옛: 한 장만 실어도 그 PDF 를 통째로 걷음)
        if 찾은:
            줄들.append(짝PDF말.format(n=len(찾은)))
    if 모름:
        줄들.append(사진모름머리 if 도구없 else 사진모름말)
        if 도구없 and 그림도구말 not in 줄들:
            줄들.append(그림도구말)
    return 줄들


def 확인줄들(카드=None, 자리=True, 실린=(), 범위=None):
    """확인할것(api._문서사진항목)·편집기 서랍(render_editor_any)이 같은 인자로 쓰는 그림 알림 줄들('26-10-01 주관 판정 P5) — [].
    카드 = 이 대화·이 문서의 범위 카드, 실린 = 이 문서에 실린 그림 id, 범위 = 이 대화·이 문서의 자료 이름(None 이면 받은 자료 전부).
      자리 있는 장르: 문서사진줄들((가)·(나)·HWP 모름·도구 없음이면 도구 줄) + 못쓴줄들(카드를 못 만든 그림 파일·PDF — 도구 없음이면
                    도구 줄 하나, 위임 자식이 죽었으면 그 파일마다, P1·P2). 같은 줄은 한 번.
      자리 없는 장르(1p·판형 v2): 문서 속 사진이 있으면 자리없음말, 없고 올린 사진 파일만 있으면 자리없음사진말(P4)."""
    카드 = 카드들() if 카드 is None else 카드
    if not 자리:
        줄들 = 문서사진줄들(카드, 자리=False)
        if not 줄들 and _사진파일들(범위):
            줄들 = [자리없음사진말]
        return 줄들
    줄들 = 문서사진줄들(카드, 자리=True, 실린=실린, 범위=범위)
    for x in 못쓴줄들(범위):
        if x not in 줄들:
            줄들.append(x)
    return 줄들


def _사진파일들(파일들=None):
    """범위 안의 올린 사진 파일(PNG·JPG …) — 도구로 만든 카드가 있으면 '사진·삽화' 카드가 있는 것만(스캔 쪽·로고·도식은 아니다),
    카드가 없으면(도구 없음·처리 못 함) 파일 이름 꼴로 센다(P4)."""
    import unicodedata
    있는 = {unicodedata.normalize("NFC", f): f for f in _받은파일들()}
    이름들 = list(있는.values()) if 파일들 is None else \
        [있는[k] for k in dict.fromkeys(unicodedata.normalize("NFC", str(x)) for x in 파일들 if x) if k in 있는]
    목 = _목록읽기().get("파일들") or {}
    out = []
    for f in 이름들:
        if not _래스터꼴.search(f) or _문서종류(os.path.join(자료뿌리.받은것뿌리(), f)):
            continue
        e = 목.get(f) or {}
        if e.get("판") == _카드판 and not e.get("처리못함") \
                and not any(c.get("id") and c.get("종류") == "사진·삽화" for c in e.get("카드") or []):
            continue
        out.append(f)
    return out


def 문서사진말(카드=None, 자리=True, 파일=None, 실린=(), 범위=None):
    """문서사진줄들 을 한 줄로 이은 글 — 없으면 ''(파일읽기 그림안내·웹앱 자료 칸·편집기 서랍)."""
    return " ".join(문서사진줄들(카드, 자리=자리, 파일=파일, 실린=실린, 범위=범위))


def _사진모름(c):
    """HWP 를 kordoc 이 못 세어 사진이 있는지 모르는 카드(T1) — 옛 목록(표지 없음)은 까닭 글로 알아본다."""
    return bool(c.get("사진모름")) or (c.get("종류") == "꺼낼 수 없음"
                                     and str(c.get("까닭") or "").startswith("HWP 파일 속 그림은 살피지 못했습니다"))


def _짝pdf사진(카드, 문서들, 범위=None):
    """{문서 파일: {짝 PDF 파일: {사진 카드 id …}}} — 이 범위의 PDF 가운데 그 문서와 본문 겹침 ≥ _짝문턱 인 것마다 그 PDF 의
    **사진 카드**('사진·삽화', 없으면 빈 모음)('26-10-01 주관 판정 T4·S1). 글지문·카드 종류만 보므로 Pillow 없이도 센다. 범위 =
    이 대화·이 문서의 자료 이름 — 카드가 없는 PDF(글만 든 PDF)도 짝으로 보려면 준다. 없으면 카드의 파일 이름만 본다(글만 든
    PDF 는 짝으로 못 본다 — (가) 뒷문장이 전 문구로 남는 쪽). 카드는 파일마다의 목록(같은 그림 묶기 전)에서."""
    목 = _목록읽기().get("파일들") or {}
    이름들 = {str(c.get("파일")) for c in 카드 or [] if c.get("파일")} | {str(x) for x in 범위 or () if x}
    pdf들 = sorted(f for f in 이름들 if f.lower().endswith(".pdf"))
    out = {}
    for f in 문서들:
        fp = (목.get(f) or {}).get("글지문")
        if not fp:
            continue
        짝 = {}
        for p in pdf들:
            e = 목.get(p) or {}
            if e.get("글지문") and _글겹침(fp, e["글지문"]) >= _짝문턱:
                짝[p] = {c["id"] for c in e.get("카드") or [] if c.get("id") and c.get("종류") == "사진·삽화"}
        if 짝:
            out[f] = 짝
    return out


def 카드글(카드=None, 약한=False, 공개=False):
    """지시문에 싣는 글 카드. 강한 모델은 전부(상한 30), 약한 모델은 쓸 수 있는 것만 짧게(8줄·800자 안).
    공개 장르(보도자료·발표)는 비밀 표지가 있는 그림을 쓰지 않는 쪽으로 돌린다."""
    카드 = 카드들() if 카드 is None else 카드
    if not 카드:
        return ""
    쓸, 안 = [], []
    for c in 카드:
        if c.get("쓸수있음") and not (공개 and c.get("비밀표지")):
            쓸.append(c)
        else:
            안.append(c)
    상한, 곁길이 = (8, 40) if 약한 else (30, 70)
    if 약한:
        # 약한 모델에는 거의 같은 그림(같은 사진을 따로 저장한 것) 중 한 장만 — 같은 사진을 두 번 넣는 과용을 막는다.
        # 남기는 것은 곁 글(캡션)이 있는 판, 둘 다 같으면 **나중에 올린** 판이다(review_practice2 N7: 사람 자리를 가려 다시
        # 올린 사본이 먼저 올린 원본에 가려 약한 모델이 원본만 봤다). 카드들() 은 올린 차례다.
        점 = {c.get("id"): (bool(c.get("곁글")), k) for k, c in enumerate(쓸)}
        쓸 = [c for c in 쓸 if not any(x in 점 and 점[x] > 점[c.get("id")] for x in (c.get("같은그림") or []))]
    줄 = ["[올린 자료 속 그림 — 시스템이 꺼낸 목록] 쓸 그림은 \"그림\":\"img-…\" id 로만 고른다. 경로·쪽·좌표"
         "(파일·쪽·자를곳·크롭)는 쓰지 않는다 — 시스템이 푼다. 자료 글 속 ![image](…) 자국은 무시한다."]
    for c in 쓸[:상한]:
        크기 = f"{c['표시mm'][0]}×{c['표시mm'][1]}mm" if c.get("표시mm") else (
            f"{c['원본px'][0]}×{c['원본px'][1]}px" if c.get("원본px") else "")
        곁 = (c.get("곁글") or "")[:곁길이]
        꼬리 = []
        if c.get("비밀표지"):
            꼬리.append(f"비밀 표지 '{c['비밀표지']}'")
        if c.get("가림") and not 약한:
            꼬리.append("가린 자리 있음")
        if c.get("같은그림") and not 약한:
            꼬리.append("같은 그림: " + ", ".join(c["같은그림"][:3]))
        if c.get("또있음") and not 약한:
            꼬리.append("같은 그림이 " + ", ".join(c["또있음"][:2]) + "에도")
        줄.append(f"- {c['id']} · {_자리말(c)} · {c.get('종류')}" + (f" · {크기}" if 크기 else "")
                 + (f" · 곁 글 \"{곁}\"" if 곁 else " · 곁 글 없음(파일 이름만 단서)")
                 + ("".join(f" · {x}" for x in 꼬리)))
    if len(쓸) > 상한:
        줄.append(f"(그 밖에 쓸 수 있는 그림 {len(쓸) - 상한}장은 목록에서 줄였다)")
    if 안:
        if 약한:
            셈 = {}
            for c in 안:
                k = "비밀 표지" if (c.get("쓸수있음") and c.get("비밀표지")) else c.get("종류", "?")
                셈[k] = 셈.get(k, 0) + 1
            줄.append("쓰지 않는 것: " + " · ".join(f"{k} {v}" for k, v in 셈.items()))
        else:
            안줄 = []
            for c in 안[:12]:
                까 = ("공개 문서에 쓰지 않음(비밀 표지)" if c.get("쓸수있음") else
                     {"로고 추정": "로고", "스캔 쪽": "스캔 쪽 — 붙임으로", "선 도식·표": "표·도식으로 다시 쓴다",
                      "도식·글 그림": "글·선 그림 — 표·도식으로 다시 쓴다",
                      문서사진: "문서 속 사진 — " + 문서사진까닭}.get(c.get("종류"), c.get("종류", "")))
                안줄.append((f"{c['id']} " if c.get("id") else "") + f"{_자리말(c)}({까})")
            줄.append("쓰지 않는 것: " + " · ".join(안줄) + (f" 외 {len(안) - 12}" if len(안) > 12 else ""))
    글 = "\n".join(줄)
    if 약한 and len(글) > 800:
        while len(줄) > 3 and len("\n".join(줄)) > 800:
            줄.pop(-2)
        글 = "\n".join(줄)
    return 글


# ── ② 생성(generate) ─────────────────────────────────────────────────────
# ('26-09-30) 생성 수단은 host 하나다 — 그림을 그릴 수 있는 에이전트가 요청 목록(manifest)을 보고 그린다.
# 서버·외부 키 생성(ima2·openai 호환·gemini)은 걷었다(providers 주석).
#
# ('26-09-30 P2 — 생성 핸드오프, r2/img design §6-1·critic_impl #22·#23·critic_practice §4)
#  · 켜기: 에이전트가 제 도구 목록에서 본 이미지 도구 이름을 이미지능력(imagegen) 작업으로 밝힌다. 환경변수 스위치는 없다.
#    ('26-09-30 주관 판정) **대화 단위**다 — 작업방식(work_mode)과 같은 방식: MCP 는 이 프로세스 안의 대화 칸(자료뿌리·세션
#    열쇠마다, 무활동 _능력수명초=2시간이면 잊음), CLI 는 대화를 모르므로 그 호출에 실린 image_tool(호출능력) 만 본다.
#    파일(생성능력.json)로 남기지 않는다 — 전에는 6시간 창이 다른 대화로 이어져, 사용자에게 묻지 않은 새 대화에서도 그림
#    설명이 이미지 도구의 제공자로 갔다(review_practice2 §2-6). 새 대화에서는 다시 밝히고 사용자에게 묻는다.
#  · 요청 id = 모델이 쓴 프롬프트 + 해상도의 해시(gen-<12자>). 파일 이름도 id 다 — 자리 순서가 바뀌어도 다른 그림에
#    붙지 않고, 프롬프트가 바뀌면 옛 그림을 쓰지 않는다(새 요청 '다시 그려야 함'). 스타일(IMAGE_STYLE)은 해시에 넣지
#    않는다 — 설정 하나로 모든 그림이 다시 그려야 함이 되지 않게.
#  · 채택: 그 id 의 파일이 있으면 **능력 선언과 무관하게** 쓴다 — 선언이 끝난 뒤의 다시 조립·편집기 저장(별도
#    프로세스)에서도 그림이 유지된다(전에는 IMAGEGEN_HOST 없는 재조립에서 PPTX 그림 2→1, critic_impl T2).
#  · 채움은 채우기()(이미지채움 작업)로 — 형식·크기 검사, PIL 로 다시 써 메타데이터를 벗기고, 파일 안에
#    'AI 생성물' 표기(PNG 글 조각: AI-Generated·Description·XMP DigitalSourceType)를 심는다.
#  · manifest 는 빗장 안에서 읽고-고치고-쓴다(생성 요청·채움·조립이 겹쳐도 항목을 잃지 않게, critic_impl #23).

_능력수명초 = 2 * 3600      # 대화 칸 수명(api._대화칸_수명초)과 같다 — 마지막으로 밝히거나 그림 요청을 다룬 뒤 이만큼이면 잊는다
_비율표 = {"1:1": "1024x1024", "4:3": "1024x768", "3:4": "768x1024", "3:2": "1536x1024", "2:3": "1024x1536",
         "16:9": "1536x864", "9:16": "864x1536"}
_대화능력 = {}               # (기본뿌리, 세션 열쇠) → {"도구", "정한때", "마지막"} — 이 프로세스(MCP 대화) 안에만 산다
import contextvars as _cv   # noqa: E402
# 이번 호출에 실린 이미지 도구 이름(CLI 의 image_tool) — api.부르기 가 떼어 여기 둔다. 스레드·호출마다 따로 산다.
호출능력 = _cv.ContextVar("문서지능_호출이미지도구", default=None)


def _능력길():
    """옛 자리(P2~fixup 의 세션 자산 폴더 생성능력.json) — 이제 읽지 않고, 켜고 끌 때 남은 것을 지운다."""
    return os.path.join(_자산뿌리(), "생성능력.json")


def _대화열쇠():
    try:
        return (자료뿌리.기본뿌리(), 자료뿌리.세션열쇠())
    except Exception:
        return ("", "")


def _여러사람웹앱():
    """공개 웹앱 서버(여러 사람) — 로컬 편집기 서버(serve.py 단일세션)는 아니다. api._여러사람웹앱 과 같은 판단('26-09-30
    fixup, review_impl2 M2: 로컬 편집기에서 저장해 다시 조립하면 대기 요청이 '수단없음'으로 바뀌어 대기 목록에서 사라졌다)."""
    return bool(os.environ.get("문서지능_웹앱")) and not os.environ.get("문서지능_단일세션")


def _단일세션():
    return bool(os.environ.get("문서지능_단일세션"))


def 능력():
    """지금 밝혀진 생성 능력 {"도구", "정한때", "마지막"} 또는 None. 공개 웹앱 서버는 늘 None.
    이 호출에 실린 이미지 도구(CLI image_tool)가 먼저, 없으면 이 대화 칸(무활동 2시간이면 잊음)."""
    if _여러사람웹앱():
        return None
    v = 호출능력.get()
    if v and str(v).strip():
        return {"도구": re.sub(r"\s+", " ", str(v)).strip()[:60], "호출": True}
    import time
    k = _대화열쇠()
    d = _대화능력.get(k)
    if not isinstance(d, dict) or not str(d.get("도구") or "").strip():
        return None
    try:
        if time.time() - float(d.get("마지막") or 0) > _능력수명초:
            _대화능력.pop(k, None)
            return None
    except (TypeError, ValueError):
        return None
    return d


def 능력정하기(도구):
    """에이전트가 밝힌 이미지 도구 이름을 이 대화 칸에 적는다(빈 값·'없음' = 끈다). 돌려주는 값: 적은 dict 또는 None."""
    import time
    이름 = re.sub(r"\s+", " ", str(도구 or "")).strip()[:60]
    try:
        os.remove(_능력길())       # 옛 파일 — 남아 있으면 옛 판 프로세스가 다른 대화에 이어 쓴다
    except OSError:
        pass
    k = _대화열쇠()
    if not 이름 or 이름.lower() in ("없음", "none", "off", "끄기", "no"):
        _대화능력.pop(k, None)
        return None
    d = {"도구": 이름, "정한때": time.strftime("%Y-%m-%dT%H:%M:%S"), "마지막": time.time()}
    _대화능력[k] = d
    return d


def 능력이어가기():
    """생성 요청을 다루는 작업(이미지대기·이미지채움)이 불리면 무활동 수명을 늘린다."""
    d = 능력()
    if d and not d.get("호출"):
        import time
        d["마지막"] = time.time()
    return d


def _해상도(spec):
    """생성 해상도 — '비율'(16:9 · 1536x864) 또는 옛 '크기'(1024x1024). 도식·이미지의 표시 크기(작게·보통·크게)와
    섞이지 않게 숫자 꼴만 읽는다(critic_impl #19)."""
    for k in ("비율", "크기"):
        v = str(spec.get(k) or "").strip().replace("×", "x").replace(" ", "").lower()
        if re.fullmatch(r"\d{3,4}x\d{3,4}", v):
            return v
        if v in _비율표:
            return _비율표[v]
    return "1024x1024"


def 생성id(spec):
    """생성 요청 id — 모델이 쓴 프롬프트(공백 정리) + 해상도의 해시. 프롬프트가 없으면 None."""
    import hashlib
    p = re.sub(r"\s+", " ", str((spec or {}).get("프롬프트") or "")).strip()
    if not p:
        return None
    h = hashlib.sha256(json.dumps({"프롬프트": p, "해상도": _해상도(spec)}, ensure_ascii=False,
                                  sort_keys=True).encode("utf-8")).hexdigest()
    return "gen-" + h[:12]


def 생성길(rid):
    """요청 id 의 그림 파일(세션 자산 폴더 안) — id 꼴이 아니면 None(경로 조각이 끼지 않게)."""
    if not re.fullmatch(r"gen-[0-9a-f]{12}", str(rid or "")):
        return None
    return os.path.join(_자산뿌리(), f"{rid}.png")


# ── 파일 안 'AI 생성물' 표기 — PNG 글 조각(PIL 없이도 된다: 플러그인 MCP 파이썬에는 PIL 이 없을 수 있다) ──
# AI 기본법 제31조 투명성 — 밖으로 나가는 콘텐츠는 파일 자체에도 표시(critic_practice §4-2). 캡션 배지는 문단이라 지우면
# 끝이다. HWPX·PPTX 로 옮길 때 이 조각이 살아남는지는 형식마다 다르다(보고 r2/img/impl_p2.md 에 잰 값).
_PNG머리 = b"\x89PNG\r\n\x1a\n"
AI표기키 = "AI-Generated"
# 남길 조각은 **허용 목록**으로 고른다('26-09-30 fixup, review_impl2 H3②) — 전에는 걷을 조각을 적어(tEXt·zTXt·iTXt·eXIf·tIME)
# 모르는 보조 조각(prVt 등)에 심은 글이 그대로 남았다. 그림을 그리는 데 드는 조각과 색 해석 조각만 남긴다(iCCP 는 기기
# 이름이 들 수 있어 뺀다).
_남길조각 = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND", b"sRGB", b"gAMA", b"cHRM", b"pHYs"}
_XMP = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" Iptc4xmpExt:DigitalSourceType='
        '"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia">'
        '<dc:description><rdf:Alt><rdf:li xml:lang="x-default">AI 생성물</rdf:li></rdf:Alt></dc:description>'
        '</rdf:Description></rdf:RDF></x:xmpmeta>')


def _png조각들(b):
    """PNG 바이트 → [(종류 bytes, 속 bytes)] — PNG 가 아니거나 깨졌으면 None."""
    import struct
    import zlib
    if not isinstance(b, (bytes, bytearray)) or not b.startswith(_PNG머리):
        return None
    i, out = len(_PNG머리), []
    while i + 12 <= len(b):
        n = struct.unpack(">I", b[i:i + 4])[0]
        t = bytes(b[i + 4:i + 8])
        d = bytes(b[i + 8:i + 8 + n])
        if len(d) != n or struct.unpack(">I", b[i + 8 + n:i + 12 + n])[0] != (zlib.crc32(t + d) & 0xFFFFFFFF):
            return None
        out.append((t, d))
        i += 12 + n
        if t == b"IEND":
            break
    return out if out and out[0][0] == b"IHDR" and out[-1][0] == b"IEND" else None


def _조각(t, d):
    import struct
    import zlib
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def AI표기심기(b, rid="", 도구=""):
    """PNG 바이트에서 글·EXIF·시각 조각을 걷고 'AI 생성물' 표기 조각 셋을 IHDR 뒤에 심는다. PNG 가 아니면 None."""
    조각들 = _png조각들(b)
    if 조각들 is None:
        return None
    도 = re.sub(r"[^\x20-\x7e]", "", str(도구 or ""))[:60]
    값 = f"true; source=trainedAlgorithmicMedia; request={rid}" + (f"; tool={도}" if 도 else "")
    설명 = f"AI 생성물 — 문서지능 그림 요청 {rid}" + (f", 도구 {도}" if 도 else "")

    def itxt(키, 글):
        return 키.encode("latin-1") + b"\x00\x00\x00" + b"\x00" + b"\x00" + 글.encode("utf-8")
    심을 = [(b"tEXt", AI표기키.encode("latin-1") + b"\x00" + 값.encode("latin-1")),
           (b"iTXt", itxt("Description", 설명)),
           (b"iTXt", itxt("XML:com.adobe.xmp", _XMP))]
    남길 = [c for c in 조각들 if c[0] in _남길조각]
    return _PNG머리 + b"".join(_조각(t, d) for t, d in 남길[:1] + 심을 + 남길[1:])


def AI표기있나(경로또는바이트):
    """PNG 안에 'AI-Generated' 글 조각이 있나."""
    b = 경로또는바이트
    if isinstance(b, str):
        try:
            with open(b, "rb") as f:
                b = f.read()
        except OSError:
            return False
    조각들 = _png조각들(b) or []
    return any(t == b"tEXt" and d.split(b"\x00", 1)[0] == AI표기키.encode("latin-1") for t, d in 조각들)


class 채움거절(ValueError):
    """이미지채움이 받은 그림을 쓰지 않는다 — 까닭은 사람 말로."""


_채움형식 = ("PNG", "JPEG", "WEBP")
_채움상한바이트 = 20 * 1024 * 1024
_채움최소변 = 256
_채움최대화소 = 40_000_000


def _명세읽기():
    try:
        with open(_명세길(), encoding="utf-8") as f:
            man = json.load(f)
        return man if isinstance(man, dict) else {}
    except (OSError, ValueError):
        return {}


def _명세고치기(고침):
    """manifest 를 빗장 안에서 읽고 고쳐 쓴다 — 고침(man) 이 참을 돌려주면 쓴다. 빗장을 못 잡으면 건너뛰고 알린다."""
    MANIFEST = _명세길()
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    try:
        with 자료뿌리.빗장(MANIFEST):
            man = _명세읽기()
            if 고침(man):
                자료뿌리.원자json(MANIFEST, man, indent=1)   # 원자 쓰기(WP-S2 ③, E-6)
            return man
    except Exception as e:
        print(f"[imageasset] 요청 목록을 고치지 못했다(건너뜀): {type(e).__name__}", file=sys.stderr)
        return _명세읽기()


def 요청들():
    """manifest 의 생성 요청(id 꼴 항목만) {id: 항목} — 옛 자리 이름 항목은 뺀다."""
    return {k: v for k, v in _명세읽기().items() if isinstance(v, dict) and re.fullmatch(r"gen-[0-9a-f]{12}", k)}


def _옛채움옮기기(name, styled, out, rid=""):
    """P2 전의 꼴(자리 이름 파일 <name>.png + manifest[name])로 채워 둔 그림 — 프롬프트가 같으면 id 파일로 옮기고
    요청 목록에 '채움'(도구 '옛 채움')으로 적는다. 글 조각은 허용 목록으로 걷는다(AI표기심기)."""
    import time
    옛 = _명세읽기().get(name)
    옛길 = os.path.join(_자산뿌리(), f"{name}.png")
    if not (isinstance(옛, dict) and 옛.get("프롬프트") == styled and os.path.isfile(옛길)):
        return False
    rid = rid or os.path.basename(out)[:-4]
    try:
        with open(옛길, "rb") as f:
            b = AI표기심기(f.read(), rid, "옛 채움")
    except OSError:
        return False
    if not b:
        return False
    자료뿌리.원자쓰기(out, b)

    def 고침(man):
        ent = man.get(rid) if isinstance(man.get(rid), dict) else {"id": rid}
        ent.update({"상태": "채움", "도구": "옛 채움(P2 전)", "채운시각": time.time()})
        man[rid] = ent
        return True
    _명세고치기(고침)
    return True


def _요청적기(rid, spec, styled, 해상도, out, name, 바로놓임=False):
    """요청을 manifest 에 적는다(id 항목). 이 자리(name)가 전에 다른 요청에 붙어 있었으면 떼고, 그 요청이 채워져
    있었으면 새 요청은 '다시 그려야 함'(프롬프트가 바뀌었다)."""
    import time
    자료빌드 = _자료빌드()

    def 고침(man):
        앞 = None
        for k, v in man.items():
            if k != rid and isinstance(v, dict) and name in (v.get("자리") or []):
                v["자리"] = [x for x in v["자리"] if x != name]
                if v.get("상태") == "채움":
                    앞 = k
        ent = man.get(rid) if isinstance(man.get(rid), dict) else {}
        옛 = json.dumps(ent, ensure_ascii=False, sort_keys=True)
        ent.update({"id": rid, "프롬프트": styled, "원프롬프트": re.sub(r"\s+", " ", str(spec.get("프롬프트"))).strip(),
                    "크기": 해상도, "저장경로": os.path.relpath(out, 자료빌드)})
        ent["자리"] = sorted(set(ent.get("자리") or []) | {name})
        ent.setdefault("요청시각", time.time())
        if os.path.exists(out) and not 바로놓임:
            ent["상태"] = "채움"
        elif 바로놓임 and ent.get("상태") != "다시 그려야 함":
            ent["상태"] = "대기"          # 이미지채움을 거치지 않고 놓인 파일 — 채움으로 치지 않는다(H3)
        elif 앞 or ent.get("상태") == "다시 그려야 함":
            ent["상태"] = "다시 그려야 함"
            if 앞:
                ent["앞그림"] = 앞
        else:
            ent["상태"] = "대기"
        man[rid] = ent
        return 옛 != json.dumps(ent, ensure_ascii=False, sort_keys=True) or 앞 is not None
    _명세고치기(고침)


def generate(spec, name):
    """이미지 생성 — 그 요청 id 의 그림이 채워져 있으면 쓰고, 없으면(능력이 밝혀졌을 때만) 요청을 남긴다.
    실패해도 조립은 계속된다.

    돌려주는 값: (경로, None) 또는 (None, 사유). 사유의 머리말(대기·거부·수단없음·프롬프트없음)을
    render 가 data-miss 로 옮긴다 — 내부 설정 이름은 싣지 않는다."""
    ASSETS = _자산뿌리()   # 호출마다 세션 뿌리를 다시 푼다(③)
    os.makedirs(ASSETS, exist_ok=True)
    prompt = spec.get("프롬프트")
    if not prompt:   # 프롬프트 누락 시 KeyError 로 전체 조립을 크래시내지 않고 자리표시로 강등(추출과 대칭)
        return None, "프롬프트없음: 생성 프롬프트가 없다"
    why = guard(prompt)
    if why:
        return None, f"거부: {why}"
    if spec.get("실사"):
        # 실사 모드는 없앴다(_기본스타일 주석) — 값이 와도 평면 삽화로 만든다. 조용히 삼키지 않고 남긴다.
        print(f"[imageasset] '실사' 는 더 쓰지 않는다 — {name} 은 평면 삽화 요청으로 남긴다", file=sys.stderr)
    rid = 생성id(spec)
    out = 생성길(rid)
    해상도 = _해상도(spec)
    styled = _스타일적용(prompt)     # 가드레일 — 문서 모델 프롬프트에 톤을 덧댄다(평면·글자 없음)
    if not os.path.exists(out):
        _옛채움옮기기(name, styled, out, rid)
    if os.path.exists(out):
        # 해시 채택 — 능력 선언과 무관하게 쓴다. 단 **이미지채움(채우기)이 넣은 그림만**('26-09-30 fixup, review_impl2 H3):
        # 전에는 저장 경로에 바로 놓인 파일이면 PNG 인지만 보고 채택해 채움의 검사(최소 크기·화소 상한·메타데이터
        # 벗기기·도구 이름·올린 사진 대조)를 모두 건너뛰었다. 채우기가 manifest 에 남긴 기록(상태 채움·채운시각)이 없으면
        # 쓰지 않는다 — 그 파일은 그대로 두고 표식은 대기다(이미지채움으로 넣게).
        기록 = _명세읽기().get(rid) or {}
        if not (isinstance(기록, dict) and 기록.get("상태") == "채움" and 기록.get("채운시각")
                and AI표기있나(out)):
            print(f"[imageasset] {rid}: 그 자리의 파일은 이미지채움으로 넣은 것이 아니라 쓰지 않는다 — "
                  "이미지채움(imagefill)으로 넣을 것", file=sys.stderr)
            if not _여러사람웹앱():
                _요청적기(rid, spec, styled, 해상도, out, name, 바로놓임=True)
            return None, "대기: 이미지채움으로 넣지 않은 파일이라 쓰지 않는다"
        if not _여러사람웹앱():
            _요청적기(rid, spec, styled, 해상도, out, name)     # 자리 기록만(상태 채움)
        return out, None
    if not providers()["host"]:
        # 능력이 밝혀지지 않았으면 요청을 만들지 않는다(design §6-3) — 산출물에서는 빠지고 편집기에만 표지.
        # 로컬 편집기 서버(단일세션, 별도 프로세스)는 대화 칸을 모른다('26-09-30 주관 판정 — 능력은 대화 단위). 그 대화가
        # 이미 남긴 요청(대기·다시 그려야 함)은 편집기 저장으로 다시 조립해도 대기로 둔다(M2) — 새 요청은 만들지 않는다.
        옛 = 요청들().get(rid) if _단일세션() else None
        if isinstance(옛, dict) and 옛.get("상태") in ("대기", "다시 그려야 함"):
            _요청적기(rid, spec, styled, 해상도, out, name)
            return None, "대기: 에이전트가 이미지채움으로 그림을 넣으면 반영된다"
        return None, "수단없음: 그림을 만들 수 있는 에이전트가 없다"
    _요청적기(rid, spec, styled, 해상도, out, name)
    return None, "대기: 에이전트가 이미지채움으로 그림을 넣으면 반영된다"


def _pil있나():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _위임채움(rid, 내용, 도구):
    """PIL 없는 파이썬(mcp/.venv)의 채우기 — .hwpxenv 로 넘긴다(_위임추출과 같은 길). 결과 경로를 다시 본다."""
    import base64
    py = _그림파이썬()
    if not py or os.environ.get("문서지능_그림위임") == "1":
        raise 도구없음("그림을 다시 쓰는 도구(Pillow)가 없습니다 — bin/bootstrap.sh 를 다시 실행해 주세요")
    env = 자료뿌리.자식환경()
    env["문서지능_그림위임"] = "1"
    r = subprocess.run([py, os.path.abspath(__file__), "--채움"],
                       input=json.dumps({"id": rid, "b64": base64.b64encode(내용).decode("ascii"), "도구": 도구}),
                       capture_output=True, text=True, timeout=180, env=env)
    try:
        값 = json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        raise RuntimeError(f"그림 위임 실패(rc={r.returncode})")
    if 값.get("ok"):
        경로 = os.path.realpath(값["경로"])
        if 경로 != os.path.realpath(생성길(rid)):
            raise 채움거절("그림을 이 세션 밖에 놓았습니다")
        return 값
    if 값.get("종류") == "채움거절":
        raise 채움거절(값.get("말") or "그림을 쓸 수 없습니다")
    if 값.get("종류") == "도구없음":
        raise 도구없음(값.get("말") or "그림을 다시 쓰는 도구가 없습니다")
    raise RuntimeError(f"그림 위임 실패: {값.get('종류')}")


def _요약32(im):
    """카드 미리보기와 같은 길(320px 썸네일 → 32×32 RGB)의 요약 바이트."""
    t = im.convert("RGB").copy()
    t.thumbnail((320, 320))
    return t.resize((32, 32)).tobytes()


# 지각 해시('26-09-30 fixup3 N3) — 32×32 회색 DCT 의 낮은 8×8(직류 뺀 63칸)을 가운데값으로 가른 63비트. 밝기·흑백·크기·JPEG 는
# 해시가 거의 그대로이고, 자르기·좌우 뒤집기는 올린 쪽을 같은 꼴(가장자리 0·3·6·10·15% 자름 × 뒤집기, 10벌)로 만들어 맞댄다.
# 문턱 12비트 — 합성 실측(fx3/phash_proto): 올린 사진 변형 13꼴 0~8비트, 같은 주제·다른 배치 6장 18~28, 다른 장면 6장 26~30.
# 두 가지 곁 조건 — ① 색 — 해시는 밝기(회색) 구조만 보아 같은 배치를 다른 색으로 그린 그림(바탕색만 다른 합성 그림, r28)도
# 같게 본다. 둘 다 색이 있으면 평균 색도(r·g 비율 합, 밝기와 무관) 차가 0.06 안일 때만 같다고 본다(변형 0.000~0.009, 바탕색만
# 다른 쌍 0.311). 한쪽이 흑백(평균 채도 8 미만)이면 색은 보지 않는다(흑백 사본). ② 평평한 그림(회색 표준편차 3 미만 — 단색)은
# 해시가 뜻이 없어(모든 계수 0) 해시로 견주지 않는다(평균 차 잣대만).
# 한계('26-09-30 주관 판정 P5 — 지금 판을 두고 적어 둔다): 지각 해시는 원리상 뚫리는 한 겹 더한 방어다. verify_fixup3 N9 실측에서
# 올린 사진을 5°·90° 돌린 것, 위아래 뒤집은 것, 흰 테두리 12%를 두른 것, 가운데에 80%·60%로 줄여 끼운 것, 가운데 20% 확대,
# 한쪽 25% 자름은 원본 셋 모두에서 '다른 그림'으로 통과했다(검은 테두리 8%·가림 조각·반쪽 합성·색조 +60 은 원본에 따라).
# 이 꼴을 막으려 회전·테두리 벌을 더 늘리지 않는다 — 벌이 늘수록 다른 그림을 같다고 보는 오탐이 늘고, 실사진끼리의 오탐은 아직
# 재지 않았다(N10). 통과한 사본은 '출처:생성'이 되어 공개 장르 '게시 전 확인' 줄에서 빠질 수 있다 — 사람 검수가 남은 방어다.
# ('26-10-01 주관 판정 R6 — verify_fixup5 N5) 색 곁 조건 때문에 **채도 낮춤·세피아(색조 입힘)** 사본도 빠진다: 채도를 0.4 로 낮춘
# 사본은 5장 중 2장만, 세피아는 0장을 거절했다(흑백으로 완전히 뺀 사본은 5/5 — 흑백은 색을 보지 않는다). 색도 차를 넓히면 바탕색만
# 다른 다른 그림(0.311)과 가까워져 오탐이 늘어 넓히지 않는다. 문서 속 사진 거절 해시(Q2)와 올린 사진 파일 거절이 같은 한계다.
_지각N, _지각K = 32, 8
_지각문턱 = 12
_색도문턱 = 0.06
_흑백채도 = 8
_평평편차 = 3
_지각자름 = (0.0, 0.03, 0.06, 0.1, 0.15)
_지각COS = None
_지각캐시 = {}


def _지각해시(im):
    import math
    from PIL import Image
    global _지각COS
    N, K = _지각N, _지각K
    if _지각COS is None:
        _지각COS = [[math.cos((2 * x + 1) * u * math.pi / (2 * N)) for x in range(N)] for u in range(K)]
    C = _지각COS
    g = im.convert("L").resize((N, N), Image.BOX)
    p = g.tobytes()
    행 = [[sum(p[y * N + x] * C[u][x] for x in range(N)) for u in range(K)] for y in range(N)]
    칸 = [sum(행[y][u] * C[v][y] for y in range(N)) for v in range(K) for u in range(K)][1:]
    가운데 = sorted(칸)[len(칸) // 2]
    return sum(1 << i for i, x in enumerate(칸) if x > 가운데)


def _색결(im):
    """(평균 색도 r, 평균 색도 g, 평균 채도, 회색 표준편차) — 32×32 에서."""
    from PIL import Image
    t = im.convert("RGB").resize((32, 32), Image.BOX)
    px = t.tobytes()
    R = G = B = 채 = 0
    회 = []
    for i in range(0, len(px), 3):
        r, g, b = px[i], px[i + 1], px[i + 2]
        R, G, B = R + r, G + g, B + b
        채 += max(r, g, b) - min(r, g, b)
        회.append((r * 299 + g * 587 + b * 114) / 1000)
    n = len(px) // 3
    합 = (R + G + B) or 1
    평 = sum(회) / n
    return (R / 합, G / 합, 채 / n, (sum((x - 평) ** 2 for x in 회) / n) ** 0.5)


def _지각같음(새, 옛, 문턱=None, 색도=None):
    """새(해시, 색결)·옛(해시들, 색결) — 가까운 사본인가. 문턱·색도를 주면 그 잣대로(알림 짝 찾기는 더 좁게 — 문서사진남은수)."""
    (h, c), (hs, oc) = 새, 옛
    문턱 = _지각문턱 if 문턱 is None else 문턱
    색도 = _색도문턱 if 색도 is None else 색도
    if c[3] < _평평편차 or oc[3] < _평평편차:
        return False
    if c[2] >= _흑백채도 and oc[2] >= _흑백채도 and abs(c[0] - oc[0]) + abs(c[1] - oc[1]) >= 색도:
        return False
    return min(bin(h ^ x).count("1") for x in hs) <= 문턱


def _지각해시들(im):
    """올린 그림 쪽 — 뒤집기 × 가장자리 자르기 10벌."""
    from PIL import ImageOps
    out = []
    for 판 in (im, ImageOps.mirror(im)):
        w, h = 판.size
        for c in _지각자름:
            out.append(_지각해시(판.crop((int(w * c), int(h * c), int(w * (1 - c)), int(h * (1 - c))))))
    return out


def _올린그림과닮음(im):
    """새 그림이 올린 자료의 그림 카드와 거의 같으면 그 카드의 자리 말('현장.jpg' 등), 아니면 ''.

    두 잣대 — ① 32×32 요약 평균 차(카드 '같은그림'과 같은 잣대, 크기·재압축) ② 지각 해시(자르기·밝기·뒤집기·흑백,
    verify_fixup2 N3: 가장자리 3·10% 자름·밝기 ±5%·뒤집기·회색이 'AI 생성물'로 들어갔다)."""
    from PIL import Image
    try:
        카드 = 카드들()
    except Exception:
        카드 = []
    받은 = 자료뿌리.받은것뿌리()
    a = _요약32(im)
    try:
        새해시 = (_지각해시(im), _색결(im))
    except Exception:
        새해시 = None
    for c in 카드:
        if not c.get("미리보기"):
            continue
        길 = os.path.join(받은, c["미리보기"])
        try:
            with Image.open(길) as t:
                t.load()
                b = t.convert("RGB").resize((32, 32)).tobytes()
                if 새해시 is not None:
                    열쇠 = (길, os.path.getmtime(길))
                    if 열쇠 not in _지각캐시:
                        _지각캐시[열쇠] = (_지각해시들(t.convert("RGB")), _색결(t))
                    해시들 = _지각캐시[열쇠]
                else:
                    해시들 = None
        except Exception:
            continue
        if sum(abs(a[k] - b[k]) for k in range(len(a))) / len(a) < _닮음문턱 * 2:
            return _자리말(c)
        if 새해시 is not None and 해시들 is not None and _지각같음(새해시, 해시들):
            return _자리말(c)
    # 한글·워드 문서 속 그림(Q2) — 카드에는 미리보기가 없어 위 대조에서 빠진다(verify_fixup4 B2). 목록에 둔 거절 해시로 맞댄다
    if 새해시 is not None:
        for f, ent in sorted((_목록읽기().get("파일들") or {}).items()):
            for x in (ent.get("거절") or []) if isinstance(ent, dict) else []:
                try:
                    if _지각같음(새해시, (list(x["지각"]), tuple(x["색"]))):
                        return f"{f} {x['순번']}번째 그림" if x.get("순번") else f"{f} 속 그림"
                except Exception:
                    continue
    return ""


def 채우기(rid, 내용, 도구=""):
    """생성 요청 rid 에 에이전트가 만든 그림(바이트)을 넣는다 → {"id","경로","px"}.

    형식(PNG·JPEG·WebP)·용량·크기를 보고, PIL 로 새로 써서(EXIF·GPS·글 조각 없이, 투명→흰 바탕) 파일 안에
    'AI 생성물' 표기를 심은 뒤 id 자리에 원자적으로 놓고, manifest 를 '채움'으로 바꾼다. 거절은 채움거절."""
    import time
    import io
    if not re.fullmatch(r"gen-[0-9a-f]{12}", str(rid or "")):
        raise 채움거절("요청 id 꼴이 아닙니다(gen-로 시작하는 12자)")
    요 = 요청들().get(rid)
    if not 요:
        raise 채움거절(f"요청 목록에 {rid} 가 없습니다 — 이미지대기(imagequeue)로 지금 요청을 보세요")
    if not isinstance(내용, (bytes, bytearray)) or not 내용:
        raise 채움거절("그림 내용이 비었습니다")
    if len(내용) > _채움상한바이트:
        raise 채움거절(f"그림이 너무 큽니다({len(내용) // 1024 // 1024}MB > 20MB)")
    if not _pil있나():
        return _위임채움(rid, bytes(내용), 도구)
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = _채움최대화소
    try:
        im = Image.open(io.BytesIO(내용))
        형식 = (im.format or "").upper()
        im.load()
    except Exception as e:
        raise 채움거절(f"그림 파일로 읽히지 않습니다({type(e).__name__})")
    if 형식 not in _채움형식:
        raise 채움거절(f"PNG·JPEG·WebP 만 받습니다(받은 형식 {형식 or '모름'})")
    if min(im.size) < _채움최소변:
        raise 채움거절(f"그림이 너무 작습니다({im.size[0]}×{im.size[1]} — 짧은 변 {_채움최소변}px 이상)")
    if im.size[0] * im.size[1] > _채움최대화소:
        raise 채움거절("그림 화소 수가 너무 많습니다")
    im = _정규화(im)          # EXIF 방향만 읽어 돌리고 info 를 하나도 물려받지 않는 새 그림
    닮은 = _올린그림과닮음(im)
    if 닮은:
        # 올린 실물 사진을 복사(cp)해 넘기거나 base64 로 넘기면 'AI 생성물'로 들어갔다(review_impl2 M1·review_practice2 N12 —
        # 경로 길은 시각만, base64 길은 아무것도 안 봤다). 올린 자료의 그림 카드와 32×32 요약을 맞댄다(카드 '같은그림'과
        # 같은 잣대)와 지각 해시(자르기·밝기·뒤집기·흑백 — fixup3 N3)로 맞댄다. 웹·스톡 사진은 여전히 못 가린다.
        raise 채움거절(f"올린 자료에 있는 그림({닮은})과 같은 그림입니다. 올린 사진은 AI 생성물로 넣지 않습니다. "
                     "이 요청으로 이미지 도구가 새로 그린 그림만 받습니다.")
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    b = AI표기심기(buf.getvalue(), rid, 도구)
    out = 생성길(rid)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    자료뿌리.원자쓰기(out, b)

    def 고침(man):
        ent = man.get(rid) if isinstance(man.get(rid), dict) else {"id": rid}
        ent.update({"상태": "채움", "도구": re.sub(r"\s+", " ", str(도구 or "")).strip()[:60],
                    "채운시각": time.time(), "px": list(im.size)})
        man[rid] = ent
        return True
    _명세고치기(고침)
    return {"id": rid, "경로": out, "px": list(im.size)}

# ── 조립기 연결 ──────────────────────────────────────────────────────────

# 못 얻은 그림의 까닭(data-miss) — api 가 새문서 로그·확인할것에 사람 말로 옮긴다. 내부 설정 이름은 싣지 않는다.
미확보말 = {
    "못찾음": "올린 자료에서 그 그림을 찾지 못했습니다(파일 이름·쪽을 확인해 주세요)",
    # ('26-09-30 fixup4) 끝 마침표를 뗐다 — 부르는 쪽이 '. 산출물에는 …'을 이어 붙여 '주세요..'가 됐다(verify_fixup3_ux U1)
    "id필요": ("파일 이름과 쪽으로 적은 그림은 싣지 않습니다. PDF 속 그림은 편집기의 그림 목록에서 고르고 한글·워드 문서 속 "
             "사진은 문서를 PDF로 저장해 함께 올리거나 사진 파일로 올려 주세요"),
    "도구없음": "그림을 자르는 도구(Pillow)가 없어 가져오지 못했습니다 — bin/bootstrap.sh 를 다시 실행해 주세요",
    "추출실패": "올린 자료에서 그림을 잘라 내지 못했습니다",
    "대기": "그림을 만들 에이전트가 아직 넣지 않았습니다(이미지대기·이미지채움)",
    "거부": "만들면 안 되는 그림이라 만들지 않았습니다(도해·차트·상징·실제 사람·기관 사진)",
    "수단없음": "이 환경에서는 그림을 만들지 않습니다 — 올린 자료의 그림으로 바꾸거나 지워 주세요",
    "프롬프트없음": "무엇을 그릴지(프롬프트)가 비어 있습니다",
}


def 싣는가(spec, 장르, 판형=None):
    """조립기가 이 그림 스펙을 그려도 되나 — 생성 그림은 장르 정책(genres.그림정책 '생성')이 허락한 곳에서만.
    ('26-09-30 fixup, review_impl2 H2) 전에는 새문서 입구(_그림정리)에서만 막아, 저장(save)·편집기 AI 다시쓰기로 넣은 생성
    그림이 풀버전 PDF 에 'AI 생성물'로 실렸다. 조립기가 부르는 이 한 곳에서 막는다(못 그린 자리는 api._그림살피기 가 알린다)."""
    if not isinstance(spec, dict):
        return False
    if spec.get("출처") != "생성":
        return True
    import genres
    return bool(genres.그림정책값(장르, 판형).get("생성"))


def render(spec, name, 캡션아래=False):
    """이미지 스펙 → HTML 조각(.fr-fig 재사용: 꺾쇠 캡션 + ※ 함의).

    못 얻은 그림은 **자리를 차지하지 않는 표식**만 낸다('26-09-30 주관 판정) — `hidden` + data-miss.
    전에는 점선 자리표시가 PDF·HWPX 본문에 그대로 실렸고, 인쇄 때만 숨기면 풀버전 쪽 나눔이 화면에서
    먼저 정해져 PDF 에 구멍이 남았다(critic_impl T3②: 3쪽 대 블록 없는 2쪽). hidden 은 화면·인쇄 모두
    display:none 이라 조판·HWPX(화면읽기 보임 검사)·PPTX(display:none 건너뜀)에서 빠진다. 인라인 style 은
    조판기가 display 를 지우므로 쓰지 않는다. 편집기(render_editor_any)만 이 표식을 검토 표지로 띄운다."""
    e = _html.escape
    src, err, 까닭 = None, None, None
    생성 = spec.get("출처") == "생성"
    if 생성:
        src, err = generate(spec, name)
        if err:
            까닭 = err.split(":", 1)[0] if err.split(":", 1)[0] in 미확보말 else "대기"
    else:
        try:
            src = extract(spec, name)
        except id필요 as exc:
            err, 까닭 = f"추출 실패: {type(exc).__name__}", "id필요"
        except 원본거절 as exc:
            err, 까닭 = f"추출 실패: {type(exc).__name__}", "못찾음"
        except 도구없음 as exc:
            err, 까닭 = f"추출 실패: {type(exc).__name__}", "도구없음"
        except Exception as exc:
            err, 까닭 = f"추출 실패: {type(exc).__name__}", "추출실패"
    if err and os.environ.get("문서지능_그림로그"):
        # 자세한 까닭은 서버 로그로만 — 문서(PDF·HWPX)에는 경로·세션 열쇠·내부 오류 글을
        # 싣지 않는다('26-09-29 보안: 자리표시에 서버 절대경로와 세션 열쇠가 찍혀 나갔다).
        # ('26-09-30 Q5) 로그 등급을 낮췄다 — 조립기의 stderr 꼬리가 편집기 저장 로그에 '✓ 다시 만들기: [imageasset] 그림 미확보:
        # 추출 실패: id필요'로 사용자에게 보였다(verify_fixup4_ux V8). 사용자에게는 api._그림살피기(확인할것·새문서 로그)와 편집기
        # 칩이 사람 말로 알린다. 운영자가 까닭을 보려면 환경변수 문서지능_그림로그=1.
        print(f"[imageasset] 그림 미확보: {err[:120]}", file=sys.stderr)

    # 편집기가 손댈 수 있게 스펙을 싣는다 — 도식(.fr-fig)·표와 같은 방식.
    # 브라우저는 원본 PDF를 자를 수 없으므로, 화면에서는 '어디를 자를지'만 정하고
    # 실제 잘라내기는 반영할 때 여기(extract)가 다시 한다. "파일"은 세션 안 상대 이름으로 싣는다.
    실을 = dict(spec)
    if "파일" in 실을:
        실을["파일"] = _원본표기(실을["파일"])
    실을.pop("실사", None)      # 실사 모드는 없앴다 — 편집기 저장으로 되살아나지 않게 싣지 않는다
    스펙 = _html.escape(json.dumps(실을, ensure_ascii=False), quote=True)
    # 생성 요청 id(P2) — api 가 조립된 HTML 에서 대기 목록·다시 조립할 문서를 이것으로 찾는다
    _rid = 생성id(spec) if 생성 else None
    gen속 = f' data-gen="{e(_rid)}"' if _rid else ""
    if not src:
        사람말 = ("그림을 아직 만들지 못했습니다 — 편집기에서 그림을 넣거나 이 자리를 지워 주세요"
                if 생성 else
                "올린 자료에서 그림을 가져오지 못했습니다 — 편집기에서 그림을 바꾸거나 이 자리를 지워 주세요")
        # 캡션·함의도 싣지 않는다 — 그림 없는 캡션이 산출물에 남지 않게(스펙 안에는 그대로 있다)
        return (f'<div class="blk fr-fig fr-img" data-ent="이미지"{gen속} data-miss="{e(까닭)}" hidden '
                f'data-img="{스펙}"><div class="ph">[이미지 미확보] {e(사람말)}</div></div>\n')
    parts = [f'<div class="blk fr-fig fr-img" data-ent="이미지"{gen속} data-img="{스펙}">']
    if spec.get("캡션") and not 캡션아래:
        parts.append(f'<div class="cap">&lt; {e(spec["캡션"])} &gt;</div>')
    rel = os.path.relpath(src, 자료뿌리.산출물뿌리())
    # 표시 크기 — 편집기 그림 막대의 세 단(작게·보통·크게, P3 '26-09-30)이 있으면 그것, 없으면 옛 '폭'(%)
    크 = 표시크기(spec)
    폭글 = _표시폭[크] if 크 else "width:" + _옛폭(spec) + "%"
    parts.append(f'<img src="{e(rel)}" alt="{e(spec.get("대체텍스트") or spec.get("캡션", ""))}" '
                 f'style="{폭글}">')
    # AI 생성물 표기 강제(온톨로지 시각자료.AI표기_필수) — 렌더가 붙이므로 스펙에서
    # 지워도 다시 나온다. 표기가 실물 오인을 막는 신뢰성 장치다.
    if spec.get("출처") == "생성":
        parts.append('<div class="ai-gen">🅰 AI 생성물</div>')
    if spec.get("캡션") and 캡션아래:
        # 보도자료 붙임 사진 — 설명은 사진 **아래** 짧게(보도자료 작성 길잡이 49쪽, critic_practice §6). 꺾쇠 없이
        parts.append(f'<div class="cap cap-below">{e(spec["캡션"])}</div>')
    노트 = spec.get("함의") or spec.get("설명")   # shape 는 '설명'(※근거·출처)을 가르치므로 폴백(유실 봉합)
    if 노트:
        parts.append(f'<div class="note">{e(노트)}</div>')
    parts.append("</div>\n")
    return "".join(parts)


# ── 표시 크기 세 단(P3 '26-09-30, design §7) ─────────────────────────────────────────
# 편집기 그림 막대의 '크기'는 도식·표와 같은 한 축 세 단이다. A4 판면 170mm 기준으로 작게 = 반폭 약 80mm(짝이
# 있으면 나란히), 보통 = 약 130mm, 크게 = 전폭(재경부 실물 반폭 차트 77mm·구조도 140mm·전폭 170mm). 키는
# 스펙의 '크기'(도식 크기와 같은 이름)다. 생성 해상도는 '비율'(또는 숫자 꼴 옛 '크기')에서만 읽는다(_해상도) —
# 편집기가 숫자 꼴 옛 '크기'를 '비율'로 옮긴 뒤 세 단을 적으므로 요청 id 가 바뀌지 않는다.
_표시폭 = {"작게": "width:80mm;max-width:100%", "보통": "width:130mm;max-width:100%",
         "크게": "width:100%;max-width:100%"}


def _옛폭(spec):
    """옛 '폭'(%) — 숫자(10~100)만 받는다. ('26-09-30 fixup, review_impl2 H1) 전에는 값을 html.escape 만 해 style 에 넣어
    '60%;background-image:url(http://…)' 한 줄로 PDF 인쇄 때 서버 크롬이 바깥 주소를 불렀다. 계약은 숫자다(속성값.수)."""
    import 속성값
    v = str((spec or {}).get("폭") or "80%").strip()
    v = v[:-1].strip() if v.endswith("%") else v
    return 속성값.수(v, "그림폭", 기본="80", 최소=10, 최대=100)


def 표시크기(spec):
    """스펙의 표시 크기 단(작게·보통·크게) — 없거나 숫자 꼴(생성 해상도)이면 None."""
    v = (spec or {}).get("크기")
    return v if isinstance(v, str) and v in _표시폭 else None


def 크기접기(spec):
    """편집기가 보일 지금 단 — 세 단이 없으면 옛 '폭'(%)을 가까운 단으로 접는다(≤50 작게 · ≤85 보통 · 그 위 크게)."""
    크 = 표시크기(spec)
    if 크:
        return 크
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%\s*$", str((spec or {}).get("폭") or "80%"))
    if not m:
        return "보통"
    v = float(m.group(1))
    return "작게" if v <= 50 else "보통" if v <= 85 else "크게"


def 그림짝(htmls, 스펙들):
    """한 절 안에서 이웃한 두 그림이 둘 다 '작게'면 나란히 — [짝 클래스 조각('' · ' fig-pair fig-pair-l' ·
    ' fig-pair fig-pair-r')]. 못 얻은 그림(표식)은 건너뛴다(자리를 차지하지 않는다). 홀수 끝은 홀로 선다.
    편집기(workspace/editor_bar.py 그림짝다시)가 크기를 바꿀 때 같은 규칙으로 다시 짝짓는다."""
    out = [""] * len(htmls)
    run = []

    def 끊기():
        for k in range(0, len(run) - 1, 2):
            out[run[k]], out[run[k + 1]] = " fig-pair fig-pair-l", " fig-pair fig-pair-r"
        run.clear()

    for i, (h, s) in enumerate(zip(htmls, 스펙들)):
        if "data-miss=" in (h or ""):
            continue
        if isinstance(s, dict) and 표시크기(s) == "작게":
            run.append(i)
        else:
            끊기()
    끊기()
    return out


def 실린그림들(html):
    """조립된 HTML 에서 실린 그림 [(data-path 또는 '', img src, 생성 id 또는 '')] — MD 링크·단독 HTML·PPTX 에 쓴다."""
    out = []
    for m in re.finditer(r'<div class="blk fr-fig fr-img[^"]*"([^>]*)>(.*?)</div>\n', html or "", re.S):
        속, 안 = m.group(1), m.group(2)
        if "data-miss=" in 속:
            continue
        s = re.search(r'<img src="([^"]+)"', 안)
        if not s:
            continue
        경 = re.search(r'data-path="([^"]*)"', 속)
        g = re.search(r'data-gen="(gen-[0-9a-f]{12})"', 속)
        out.append((_html.unescape(경.group(1)) if 경 else "", _html.unescape(s.group(1)), g.group(1) if g else ""))
    return out


def _안전한그림길(길):
    """단독 HTML·MD 가 읽어도 되는 그림인가 — 이 세션 자산 폴더(또는 세션 build/) 안의 래스터 그림만."""
    try:
        rp = os.path.realpath(길)
    except (TypeError, ValueError):
        return None
    뿌리들 = [os.path.realpath(_자산뿌리()), os.path.realpath(_자료빌드())]
    if not any(rp.startswith(r + os.sep) for r in 뿌리들):
        return None
    if not re.search(r"\.(png|jpe?g|webp)$", rp, re.I) or not os.path.isfile(rp):
        return None
    return rp


def 데이터URI(길, 생성=False, 상한=12 * 1024 * 1024):
    """그림 파일 → data: URI(단독 HTML 내보내기, design §8). 못 쓰면 None.

    사진(첨부)은 PNG 가 수 MB 라 Pillow 가 있으면 JPEG(품질 85)로 다시 써 더 작을 때만 바꾼다(critic_impl #28).
    AI 생성 그림은 바꾸지 않는다 — 파일 안 'AI 생성물' 표기(PNG 글 조각)가 JPEG 로 옮기면 사라진다."""
    import base64
    rp = _안전한그림길(길)
    if not rp:
        return None
    b = open(rp, "rb").read()
    if len(b) > 상한:
        return None
    꼴 = "image/png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if b[:2] == b"\xff\xd8" else (
        "image/webp" if b[:4] == b"RIFF" and b[8:12] == b"WEBP" else None)
    if not 꼴:
        return None
    if not 생성 and 꼴 == "image/png" and len(b) > 300 * 1024:
        try:
            import io
            from PIL import Image
            with Image.open(io.BytesIO(b)) as im:
                o = io.BytesIO()
                im.convert("RGB").save(o, "JPEG", quality=85, optimize=True)
            if o.tell() < len(b):
                b, 꼴 = o.getvalue(), "image/jpeg"
        except Exception:
            pass
    return f"data:{꼴};base64," + base64.b64encode(b).decode("ascii")


def 미확보들(html):
    """조립된 HTML 에서 못 얻은 그림 표식 [(data-path 또는 '', 까닭)] — api 가 로그·확인할것·MD 내보내기에 쓴다."""
    out = []
    for m in re.finditer(r'<div class="blk fr-fig fr-img[^"]*"([^>]*)>', html or ""):
        속 = m.group(1)
        까 = re.search(r'data-miss="([^"]*)"', 속)
        if not 까:
            continue
        경 = re.search(r'data-path="([^"]*)"', 속)
        out.append((_html.unescape(경.group(1)) if 경 else "", _html.unescape(까.group(1))))
    return out


def 실린것들(html):
    """조립된 HTML 에서 실제로 실린 그림의 data-path 목록(표식 제외)."""
    out = []
    for m in re.finditer(r'<div class="blk fr-fig fr-img[^"]*"([^>]*)>', html or ""):
        속 = m.group(1)
        if "data-miss=" in 속:
            continue
        경 = re.search(r'data-path="([^"]*)"', 속)
        out.append(_html.unescape(경.group(1)) if 경 else "")
    return out


def 생성자리들(html):
    """조립된 HTML 의 생성 그림 자리 [(data-path 또는 '', 요청 id, 까닭 또는 None(실림))] — P2 대기 목록·다시 조립용."""
    out = []
    for m in re.finditer(r'<div class="blk fr-fig fr-img[^"]*"([^>]*)>', html or ""):
        속 = m.group(1)
        g = re.search(r'data-gen="(gen-[0-9a-f]{12})"', 속)
        if not g:
            continue
        경 = re.search(r'data-path="([^"]*)"', 속)
        까 = re.search(r'data-miss="([^"]*)"', 속)
        out.append((_html.unescape(경.group(1)) if 경 else "", g.group(1), _html.unescape(까.group(1)) if 까 else None))
    return out


def _채움_자식():
    """--채움: PIL 없는 파이썬(mcp/.venv)이 넘긴 채우기를 여기서 한다(_위임채움). 결과는 JSON 한 줄."""
    import base64
    try:
        받음 = json.loads(sys.stdin.read() or "{}")
        값 = 채우기(str(받음.get("id") or ""), base64.b64decode(받음.get("b64") or ""), str(받음.get("도구") or ""))
        print(json.dumps(dict(값, ok=True), ensure_ascii=False))
    except 채움거절 as exc:
        print(json.dumps({"ok": False, "종류": "채움거절", "말": str(exc)}, ensure_ascii=False))
    except 도구없음 as exc:
        print(json.dumps({"ok": False, "종류": "도구없음", "말": str(exc)}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "종류": type(exc).__name__}, ensure_ascii=False))
    return 0


def _추출_자식():
    """--추출: Pillow 없는 파이썬(mcp/.venv)이 넘긴 extract 를 여기서 한다(_위임추출). 결과는 JSON 한 줄."""
    try:
        받음 = json.loads(sys.stdin.read() or "{}")
        경로 = extract(받음.get("spec") or {}, str(받음.get("name") or "asset"))
        print(json.dumps({"ok": True, "경로": 경로}, ensure_ascii=False))
    except 원본거절 as exc:
        print(json.dumps({"ok": False, "종류": "id필요" if isinstance(exc, id필요) else "원본거절", "말": str(exc)},
                         ensure_ascii=False))
    except 도구없음 as exc:
        print(json.dumps({"ok": False, "종류": "도구없음", "말": str(exc)}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "종류": type(exc).__name__}, ensure_ascii=False))
    return 0


def main():
    a = sys.argv[1:]
    if "--추출" in a:
        return _추출_자식()
    if "--채움" in a:
        return _채움_자식()
    if "--짝셈" in a:
        # Pillow 없는 파이썬(mcp/.venv)이 넘긴 문서 사진 짝 셈(_위임짝셈, '26-10-01 R2) — 카드 범위는 표준입력으로 받는다
        값 = json.loads(sys.stdin.read() or "{}")
        print(json.dumps({"ok": True, "남": 문서사진남은수(값.get("카드") or [])}, ensure_ascii=False))
        return 0
    if "--카드" in a:
        # Pillow·PyMuPDF 없는 파이썬(mcp/.venv)이 넘긴 카드 만들기(_위임카드) — 목록은 _그림/목록.json 에 쓴다
        try:
            목록 = 카드갱신()
        except 도구없음 as exc:
            # 이 파이썬에도 도구가 없다 — 표준 라이브러리로 센 목록은 이미 썼다(카드갱신). 부모가 도구 없음으로 알게 한다
            print(json.dumps({"ok": False, "종류": "도구없음", "말": str(exc)}, ensure_ascii=False))
            return 3
        print(json.dumps({"ok": True, "파일수": len(목록.get("파일들") or {})}, ensure_ascii=False))
        if "--보기" in a:
            print(카드글())
        return 0
    if "--훑기" in a or "--들여다보기" in a:
        미리 = "--미리보기없이" not in a
        if "--들여다보기" in a:
            목록 = [들여다보기(a[a.index("--들여다보기") + 1], 미리)]
        else:
            목록 = 폴더훑기(미리보기=미리)
        if not 목록:
            print("받은 자료 폴더가 비어 있습니다.")
            return 0
        for it in 목록:
            print(f"\n■ {it.get('이름') or it['파일']}  ({it.get('종류', '?')})")
            if it.get("_실패"):
                print("  ✗", it["_실패"])
                continue
            것들 = it.get("꺼낼수있는것") or []
            if not 것들:
                print("  꺼낼 수 있는 그림이 없습니다.")
                continue
            print(f"  꺼낼 수 있는 것 {len(것들)}개")
            for x in 것들[:12]:
                꼬리 = ("  미리보기: " + x["미리보기"]) if x.get("미리보기") else ""
                print(f"    · {x['설명']}{꼬리}")
            if len(것들) > 12:
                print(f"    … 외 {len(것들) - 12}개")
        return 0
    if "--check" in sys.argv:
        av = providers()
        print("이미지 생성 제공자:")
        for k, v in av.items():
            print(f"  {k:8} {'가용' if v else '—'}")
        print("추출 도구:")
        for t in ("pdftoppm", "pdftotext", "pdfimages"):
            r = subprocess.run(["which", t], capture_output=True)
            print(f"  {t:10} {'가용' if r.returncode == 0 else '—'}")
        try:
            import PIL  # noqa
            print("  PIL        가용")
        except ImportError:
            print("  PIL        —")
        return 0
    if "--spec" in sys.argv:
        path = sys.argv[sys.argv.index("--spec") + 1]
        for i, sp in enumerate(json.load(open(path, encoding="utf-8"))):
            print(render(sp, sp.get("이름", f"asset{i}"))[:200])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
