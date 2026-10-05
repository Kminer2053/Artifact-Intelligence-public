#!/usr/bin/env python3
"""문체 린터 — 공문서-개조식 (1p 보고서).

규칙 정본: ontology/ontology.json > writing_profiles.gongmun-gaejosik + entities.*.문체
사람용 해설: references/writing-rules.md (메시지의 § 표기가 해설 위치)
방법론 표본: im-not-ai metrics.py + 골든테스트 (research/recon/05)

사용:
  python3 stylelint.py <docs.json>             # samples-docs.json 형식 배열 판정
  python3 stylelint.py <docs.json> --json      # 기계용 JSON 출력
  python3 stylelint.py <docs.json> --csv       # filename,PASS|FAIL:n (render_verify용)
  python3 stylelint.py --golden <golden.json>  # 골든 테스트(린터 자체 검증)

판정: hard 위반 1건 이상 = FAIL(exit 1). soft = 경고만(통과).
관측 지표(종결어 분포·군더더기 밀도)는 판정 없이 출력만 한다 — 귀납 트랙 데이터.
문서화된 규칙만 판정한다(검증된 규칙만 등록 원칙). 새 패턴 후보는 관측 지표로만.

설계 원칙(적대 검증 2026-07-25 반영):
- 종결 판정은 열거가 아니라 형태론(ㅆ/ㄴ받침+'다' = 과거·현재 평서형) + 문장 단위 분리.
- 번역투는 어절 경계를 본다(개통하여·가지급금·갖추다·고속도로부터 오탐 방지).
- 표면형으로 용법을 못 가르는 규칙('~한 관계로', '~에 있어')은 soft로만 경고.
- 알려진 의미 한계: 요약 종결의 실질(보고 vs 결정요청) 적합성은 기계 판정 불가 — 3층·사람 몫.
"""
import json
import re
import sys
import html as htmlmod
from collections import Counter

# ── 텍스트 유틸 ──────────────────────────────────────────────


def plain(s):
    """HTML 태그 제거 + 엔티티 복원 + 공백 정규화(다중 공백 우회 차단).
    표 칸이 JSON 숫자(95.5)여도 글로 바꿔 잰다 — 예전엔 re.sub 이 TypeError 로 죽어 문체검사·조판게이트가 통째로
    FAIL 이 났다(fixup3 F, verify2 §2-A N3·N5·N6·N10)."""
    if not isinstance(s, str):
        s = "" if s is None or isinstance(s, bool) else str(s)
    t = htmlmod.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\s+", " ", t).strip()


def tail(s):
    """종결 판정용 — 끝의 괄호 주석과 닫는 문장부호 제거."""
    s = re.sub(r"\([^()]*\)\s*$", "", s)
    return re.sub(r"[\s.。!！?？…‥'\"”’)\]」』]+$", "", s)


def sentences(s):
    """항목 내 다중 문장 분리 — 둘째 문장 뒤에 숨은 서술식 완결을 잡는다."""
    return [p for p in re.split(r"(?<=[.!?…！？])\s+", s) if p.strip()]


def snip(s, n=34):
    return s if len(s) <= n else s[: n - 1] + "…"


def _jong(c):
    """음절의 종성 인덱스(받침 없음=0, ㄴ=4, ㄹ=8, ㅆ=20)."""
    return (ord(c) - 0xAC00) % 28 if "가" <= c <= "힣" else -1


# ── 종결 판정 (형태론 기반) ──────────────────────────────────

END_PATTERNS = [
    (r"니다$", "하십시오체 완결 금지 → 명사형 종결(§1-2 치환표)"),
    (r"(하십시오|하시오|십시오)$", "명령형(하십시오체) 금지 → 명사형 종결(§1-1)"),
    (r"(하라|해라|말라)$", "명령형(해라체) 금지 → 명사형 종결(§1-1)"),
    (r"(해요|돼요|되요|세요|네요|지요|죠|어요|아요|여요|예요|에요|게요|까요|려요|께요|래요)$",
     "해요체 금지 → 명사형 종결(§1-1)"),
    (r"(하다|되다|이다|있다|없다|아니다|같다|많다|크다|높다|낮다|적다|작다|어렵다|쉽다|곤란하다|필요하다)$",
     "평서형 완결 금지 → 명사형 종결(§1-2 치환표)"),
]


def check_endings(t, genre=None):
    """문장별 종결 검사. 열거 패턴 + 형태론(ㅆ받침+다=과거형, ㄴ받침+다=현재형)."""
    hits = []
    for sent in sentences(t):
        st = tail(sent)
        if len(st) < 2:
            continue
        matched = False
        for rx, hint in END_PATTERNS:
            m = re.search(rx, st)
            if m:
                hits.append((m.group(0), hint))
                matched = True
                break
        if not matched and st.endswith("다") and _jong(st[-2]) in (4, 20):
            hits.append((st[-3:], "평서형 완결(과거·현재 활용형) 금지 → 명사형 종결(§1-2)"))
    return hits


# ── 번역투 (어절 경계 인식) ──────────────────────────────────

# '[와과]\s*관련(된|하여|한)' 은 이름을 따로 둔다 — 시행문(gongmun)의 정형구 '위 호와
# 관련하여'·'…와 관련하여'(편람 관행, document_types.gongmun.구성.본문_구조)만 예외로
# 빼야 해서 check_beonyeoktu() 가 genre 를 보고 이 항목 하나만 골라 뺀다(2026-09-26).
GWANRYEON_RX = r"[와과]\s*관련(된|하여|한)"

BEONYEOKTU = [
    (r"에\s*대(해|하여|한(?!민국))", "삭제하고 명사에 조사 직결(§2-1)"),
    (r"(?:^|(?<=\s))통(해|한|하여)(?=$|[\s,.·)])", "'~로/~으로'(§2-1) — 수단의 '통해'"),
    (r"에\s*있어서", "'~에서/~은·는'(§3-1)"),
    (r"에\s*의(해|하여|한)", "능동문으로(§3-1)"),
    (r"에\s*위치(한|해|하)", "'~에 있는'(§3-1)"),
    (r"필요로\s*(하|했|함)", "'~필요'(§3-1)"),
    (r"(?<![도경항진선통회판])로\s?부터", "'~에서'(§3-1)"),
    (r"중에\s*있", "'~중'(§3-1)"),
    (r"(된|됐던|되었던)\s*관계로", "'~하였으므로'(§3-1)"),
    (r"(회의|간담회|미팅|모임|회동|면담|워크숍)[을를]?\s*(갖|가지|가져|가짐)",
     "'열다/하다'(§3-1) — have-a-meeting 번역투"),
    (GWANRYEON_RX, "'~ 관련'(§2-1)"),
]

# 법령 원문 인용 구간 — 낫표(「」) 인용과, 그 낫표 **바로 뒤**에 붙는 '제N조(…)'·
# '제N조제M항(…)' 조 제목 괄호. 2026-09-26(벤치마크 진단 GATE_FORCED, diagnosis.json
# s3): 「개인정보 보호법」 제28조(개인정보취급자에 대한 감독) 같은 조 제목의 '에
# 대한'이 번역투 하드로 잡혀, 법령 제목은 고칠 수 없으니 제목을 통째로 빼는 식으로만
# 통과되던 문제 — 법령 원문은 손댈 수 없는 인용이므로 번역투 검사 대상에서 뺀다
# (장르 불문 — 1p·풀버전 등도 법령을 그대로 인용한다).
#
# 2026-09-27 재고침(r4/rules F6) — 낫표를 **전부**(「[^」]*」) 보호하고 '제N조(…)'도
# 앞뒤 맥락 없이 **전부** 보호했더니, 모델이 새로 짓는 계획·과제 이름('「AI를 통한
# 민원 혁신 계획」')도, 새로 제안하는 조 제목('제5조(민원 처리에 대한 특례)')도 함께
# 보호돼 그 안의 번역투가 하드 게이트를 안 타고 통과했다(F6 실측 — HEAD 는 잡던 것을
# 이번 판이 전부 놓쳤다. 낫표로 감싸기만 하면 빠져나가는 우회로이기도 하다). 법령
# 원문 인용은 **법령명 꼴**(「…법」·「…법 시행령/시행규칙」·「…규정」)로만 좁히고,
# 조 제목 괄호는 그 법령명 낫표 **바로 뒤에 붙을 때만** 보호한다 — 규정(jomun) 은
# H-번역투가 애초에 안 도는 장르라(금지준용 밖) 자기 조 제목을 인용하는 경우는 이
# 범위 밖이다(1p·풀버전 등에서 새 조 제목을 제안하는 경우만 남는다).
#
# 2026-09-28 재고침(R56-02·R56-07, r56) — 두 방향으로 어긋나 있었다.
#  · R56-02(놓침): 위 접미가 '법」'으로만 끝나는 꼴을 봐서 「…에 관한 법률」·
#    「…법률 시행령/시행규칙」·「○○공사 인사 규칙」·조례·훈령·예규·고시·지침·세칙으로
#    끝나는(가장 흔한 법률명 꼴을 포함한) 실제 법령명이 하나도 안 잡혔다 — 조 제목을
#    못 보호해 '「…에 관한 법률」 제N조(…에 대한 …)' 처럼 고칠 수 없는 인용이 다시
#    H-번역투 하드에 막혔다(GATE_FORCED 재발). 법령 접미를 법률·법·규정·규칙·조례·
#    훈령·예규·고시·지침·세칙(과 그 시행령/시행규칙)으로 넓힌다.
#  · R56-07(과잉): '법'으로 끝나기만 하면 법령명으로 봐서, 「AI를 통한 민원 처리
#    방법」·「…경영혁신 기법」처럼 '방법·기법·해법' 같은 **흔한 일반명사**로 끝나는
#    (법령이 아닌) 제목까지 낫표로 우회 보호됐다. 닫는 낫표 바로 앞이 이 일반명사
#    가운데 하나면 법령명에서 뺀다.
_법령_일반명사_denylist = frozenset({
    "방법", "기법", "해법", "문법", "어법", "편법", "작법", "비법", "수법", "화법",
})
_LAW_NAME_RE = re.compile(
    r"「(?P<본문>[^」]*(?:법률|법|규정|규칙|조례|훈령|예규|고시|지침|세칙))"
    r"(?:\s?시행령|\s?시행규칙)?」")
_JOMUN_JEMOK_FOLLOW_RE = re.compile(r"\s*제\d+조(?:의\d+)?(?:제\d+항)?(\([^()]*\))")

# 재인용('같은 법'·'동법'·'(이하 법)' 등) — 낫표 바로 뒤가 아니라 **문서 다른 자리**에서
# 앞서 인용한 법령을 다시 가리키는 관용구다(R56-02). 이 뒤에 바로 붙는 조 제목 괄호도
# 낫표 직후와 같은 이유로 보호한다 — 고칠 수 없는 법령 원문이기는 매한가지다.
_JAEINYONG_SINHO_RE = re.compile(r"(?:같은\s*법|동법|\(이하\s*[^()]*\))\s*")


def _법령원문_구간(t):
    spans = []
    for m in _LAW_NAME_RE.finditer(t):
        if any(m.group("본문").endswith(w) for w in _법령_일반명사_denylist):
            continue
        spans.append(m.span())
        jm = _JOMUN_JEMOK_FOLLOW_RE.match(t, m.end())
        if jm:
            s2, e2 = jm.span(1)
            spans.append((s2, e2))
    for m in _JAEINYONG_SINHO_RE.finditer(t):
        jm = _JOMUN_JEMOK_FOLLOW_RE.match(t, m.end())
        if jm:
            s2, e2 = jm.span(1)
            spans.append((s2, e2))
    return spans


def _구간과_겹치나(span, protected):
    s, e = span
    return any(a < e and s < b for a, b in protected)


def check_beonyeoktu(t, genre=None):
    """번역투 — 법령 원문 인용은 검사 대상에서 빼고, '~와 관련(하여|된|한)'은
    시행문(gongmun)의 정형구라 그 장르에서만 허용한다."""
    protected = _법령원문_구간(t)
    hits = []
    for rx, hint in BEONYEOKTU:
        if genre == "gongmun" and rx == GWANRYEON_RX:
            continue
        for m in re.finditer(rx, t):
            if _구간과_겹치나(m.span(), protected):
                continue
            hits.append((m.group(0), hint))
            break
    return hits

IJUNG_PIDONG = [
    (r"(보여|되어|여겨|잊혀|쓰여|불려)[지진져질짐졌집]",
     "이중피동 → 단일피동(보이다/되다/여기다)(§2-1)"),
]

GEOT_HEDGE = [
    (r"(것으로|걸로)\s*(예상|전망|확인|판단|추정|기대|보)",
     "'~것으로 예상/확인' → '~예상/~확인'(§2-1)"),
    (r"것이\s*[^,.]{0,12}(필요|중요)", "'~필요'(§2-1)"),
]


def check_possibility(t, genre=None):
    """'~ㄹ 수 있다' 일반형 — ㄹ받침 음절 + '수' + '있'(보조사 삽입 허용, '~있도록' 제외)."""
    hits = []
    for m in re.finditer(r"(\S)\s?수(도|는|가)?\s?있(?!도록)", t):
        if _jong(m.group(1)) == 8:
            hits.append((m.group(0), "가능성 서술 금지 — 단정형이나 삭제(§2-1)"))
    return hits


HYPE = [(r"획기적|혁신적|게임\s*체인저|역대급", "hype 어휘 금지 — 사실·수치로(§5)")]
GWAJANG = [(r"주목할\s*만|괄목할", "의미 과장 금지 — 수치·사실로 대체(§5)")]

META_SOGAM = [
    (r"^정리하(자?면)(?!서)|^정리해\s*보면", "상투 메타발언 금지 — 요약박스가 그 역할(§5)"),
    (r"^다음은\s", "상투 메타발언('다음은 ~') 금지(§5)"),
    (r"[라다]고\s*생각|느꼈|느낍니|느껴집|보람|뜻깊|기쁘게|영광스럽|자랑스럽",
     "1인칭 소감 금지 — 주어는 기관·부서(§5)"),
]

# 물음표는 소감 목록에서 갈라냈다 — jomun.forbidden 이 '의문·감탄'을 명시하는데
# META_SOGAM 채로는 '보람' 오탐 때문에 규정에 못 걸기 때문이다(장르 가드 주석 참조).
QUESTION_MARK = [
    # '??'(겹 물음표)·'(?)'는 비워 둔 자리표시다('2026. 10. ??.(?)' — fixup4 '26-09-29, verify3 §3 H2). 물음표 화법이
    # 아니라 빈칸이라 여기서 막지 않고 확인할것 '빈칸'에 올린다(자리표시 꼴 정본: build/지어냈나.py 자리표시_글).
    (r"(?<![?？(])[?？](?![?？)])", "수사의문문·물음표는 공문서에 없는 화법(§5)"),
]

QUESTION_END = [
    (r"(무엇인가|않을까|아닐까|어떨까|일까|할까|는가)$", "수사의문문(의문형 종결) 금지(§5)"),
    (r"생각(함|합니다|됩니다)$", "1인칭 소감 금지(§5)"),
]

# ○ 하나는 마커지만 ○○·○○○ 연속은 익명 표기다(기관 '○○공사'·인명 '○○○ 장관',
# bodo.서술.인용이 그 꼴을 규범으로 등재). 보도자료 정본 리드가 '○○공사는…'으로
# 시작해 오탐 사례이 실측됐다(2026-08-07). 단일 '○ ' 마커는 그대로 잡는다(골든 G43).
MARKER_START = [
    (r"^([□■▣●◎◦•▶▷◇◆◈*※·]|○(?!○)|[ㅇㅁ]\s|[-–—▲▼](?=\s|[가-힣]))",
     "마커 문자 직접 입력 금지 — CSS가 그림(shared.표기)"),
]

# 이모지·장식기호. △(U+25B3)·→(U+2192)·※·㎡ 등 공문서 관용 기호는 범위 밖.
# ☎(U+260E)·☏(U+260F)는 연락처 관용 기호라 제외(적대 검증 판정).
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-☍☐-➿"
    "⬀-⯿‼⁉️\U0001F1E6-\U0001F1FF]")

GUNDEODEOGI = [
    (r"매\s?\S{0,3}마다", "의미 중복 '매~마다' → '매~'(§3-2)"),
    (r"약\s*[\d.,]+\s*[만천억]*\s*여", "의미 중복 '약~여' → 하나만(§3-2)"),
    (r"기간\s?동안", "'기간' 또는 '동안' 하나만(§3-2)"),
    (r"더\s?이상", "'이상'(§3-2)"),
    (r"제공\s?받", "'받다'(§3-2)"),
    (r"(여러|많은|각|모든)\s?\S{1,6}들(?=[\s,.·]|$)", "수식어+들 중복 → '들' 삭제(§2-1)"),
]

BEONYEOKTU_UISIM = [
    (r"(한|던)\s*관계로", "인과 '~한 관계로'면 '~하였으므로'(§3-1) — 관계 명사 수식이면 무시"),
    (r"에\s*있어(?!서)(?=[\s,]|$)", "화제 표지 '~에 있어'면 '~에서'(§3-1) — 존재 동사면 무시"),
]

UI_YEONSWAE = [(r"\S+의\s+\S+의(?=[\s,.]|$)", "'의' 연쇄 → 명사 직결이나 동사형(§2-1)")]

# 2026-09-28(cli s2 참고, r56) — 온전 연도 4자리 전부를 잡던 옛 YEONDO 는 풀버전 본문의
# '2027년부터 2029년까지 …'·'2027~2029년' 같은 **다년간 사업 기간**(자료 원문의 사업
# 연차 라벨 '1차 연도(2027)'을 그대로 옮긴 것)까지 오탐했다. shared.표기.date_day 는
# 월·일까지 갖춘 **특정 날짜**를 'YY 꼴로 줄이라는 관례이지, 기간·범위 표기까지
# 줄이라는 뜻이 아니다(작성원칙.날짜_기본.적용범위와 같은 결). 연도가 **범위**로
# 쓰인 자리(…년부터 …년까지·…~…년)만 뺀다 — G45('2026년 상반기 시행 예정'처럼
# 범위가 아닌 단일 연도)는 그대로 잡아야 하므로 그 경우는 손대지 않는다.
_YEONDO_범위_RX = re.compile(
    r"20\d{2}\s*년?\s*[~∼-]\s*20\d{2}\s*년"
    r"|20\d{2}\s*년\s*부터\s*20\d{2}\s*년\s*까지"
)


def check_yeondo(t, genre=None):
    protected = [m.span() for m in _YEONDO_범위_RX.finditer(t)]
    for m in re.finditer(r"20\d{2}년", t):
        if _구간과_겹치나(m.span(), protected):
            continue
        return [(m.group(0), "연도는 '26년 표기(shared.표기 date_day)")]
    return []

SUMMARY_END_RE = re.compile(r"(보고드림|요청드림|요청함)$")

BODY = {"title", "heading", "summary", "item", "cell"}
# 규정 제정이유(reason)·주요내용(mainitem) — 세그먼트 단위 규칙(hard·soft 모두)을 아직 대지
# 않는다('26-09-28 규정 처방: 첫 주기에는 soft 만, 판정은 doc_level_checks 규정 갈래가 한다).
SOFT_ONLY_SEGS = {"reason", "mainitem"}

# 슬라이드 목적 판정에 쓰는 결정 요청 신호 — assemble_slides.py._설득신호 와 같은 목록을
# 이 파일 안에서 독립으로 다시 쓴다(assemble_slides.py 는 다른 작업 묶음이 동시에 고치는
# 파일이라 import 하지 않는다 — build/tomd.py 의 규정·슬라이드 섹션과 같은 방침).
_설득신호 = ("요청", "승인", "건의", "제안", "협조", "편성", "결정", "검토", "의결", "재가")


def _슬라이드_목적(doc):
    """슬라이드 문서의 목적(설득|보고) — assemble_slides.py._목적 과 같은 판정.
    최상위 '목적' 키가 우선(별칭 정규화), 없으면 표지 부제·마무리 항목의 결정 요청
    신호로 추정한다(정본: ontology slides.문체.헤드_목적별). 2026-09-26 신설
    (r2/check.json #7) — W-헤드메시지가 목적을 안 보고 보고형 덱에도 그대로 울렸다."""
    if not isinstance(doc, dict):
        return "보고"
    if "판형" in doc:
        # v2(부품 트리) 머리는 '라벨 : 메시지' 2층이고 목적별 형태(보고=메시지구, 설득=완결 주장+수치,
        # 설명=합니다체)는 build/슬라이드v2.py·slides_v2_gate 가 soft 로 잰다 — 옛 W-헤드메시지
        # ('다·요·함'으로 끝나는 완결 문장 요구)는 v2 설득 머리('…승인 요청')를 거짓으로 울린다.
        return "v2"
    v = str(doc.get("목적") or "").strip()
    if v:
        if any(k in v for k in ("설득", "제안", "승인", "요청", "persua", "propos")):
            return "설득"
        if any(k in v for k in ("보고", "현황", "결과", "report", "inform")):
            return "보고"
    표지 = doc.get("표지") if isinstance(doc.get("표지"), dict) else {}
    글 = [str(표지.get("부제") or "")]
    for sl in (doc.get("슬라이드") or []):
        if isinstance(sl, dict) and sl.get("레이아웃") == "마무리":
            글.append(str(sl.get("헤드메시지") or ""))
            for it in (sl.get("항목") or []):
                if isinstance(it, dict):
                    글.append(str(it.get("text") or it.get("텍스트") or ""))
                else:
                    글.append(str(it))
    본 = " ".join(글)
    return "설득" if any(k in 본 for k in _설득신호) else "보고"

# 이 검사기가 아는 장르. 여기 없는 장르는 **통과시키지 않고 '못 쟀다'로 남긴다** —
# 규정·보도자료가 1p 스키마로 떨어져 세그먼트 0개가 되고, 그게 '위반 0건 통과'로
# 보이던 것을 2026-08-04 에 찾았다. 못 잰 것을 통과로 적지 않는다.
아는장르 = {"onepage-report", "gongmun", "fullreport", "regulation", "press-release", "slides"}

# 어느 장르에 적용되는가 — 세 단이다. 개조식(명사형 종결)은 1페이지·풀버전의 규범이고,
# 시행문의 규범은 정반대다 — 공손체 서술어 완결('~하시기 바랍니다').
# 그래서 종결 규칙을 시행문에 걸면 안 된다(스킬 v3.6.12 장르 가드와 같은 판단).
#
# 규정(조문체)·보도자료(서술체)를 어디까지 미느냐는 실측으로 갈랐다(2026-08-07,
# 정본 등록부 + 실물 규정 문장·보도자료(내부코퍼스 정렬
# 앞 사례) 문장 — 45자 규칙과 같은 잣대, skeleton.끝말 로 문장만 골라 셈):
#
# ALL — 다섯 장르 전부. hype·과장·이중피동·의문형 종결·마커 직입·군더더기류는
#   두 장르 실물에서도 규범 언어와 부딪히지 않았고(오탐 0 — 예외였던 '○○공사'
#   마커 오탐은 패턴에서 익명 표기를 갈라냈다), 정본도 명시한다: bodo.forbidden 이
#   '과장·hype 표현'과 이중피동을, jomun.forbidden 이 '의문·감탄'을 금지.
#
# 금지준용 — gongmun-gaejosik.금지를 전면 준용하는 세 장르만(시행문은 gyeoksik의
#   '공통적용' 조항으로, 풀버전은 같은 개조식이라). jomun·bodo 프로파일엔 준용
#   조항이 없고, 아래 표면형은 그 장르의 **규범 언어**라 걸면 정본 실물이 FAIL 한다:
#   H-번역투     규정 일부('에 대한·로부터·에 의한' — 조문 관용) ·
#                보도 일부('통해' — 서술 관용. bodo 금지는
#                번역투 범주 전체가 아니라 이중피동만이다)
#   H-군더더기것 규정: 간주조항 '~것으로 본다'(경과조치 정형구, 일부) ·
#                보도: '~것으로 기대'(기대효과 정형구, 일부)
#   ~ㄹ수있다    규정: 재량조항 — jomun.종결 rule 이 '~할 수 있다'를 규범으로
#                등재(실측), 일부) · 보도: 능력 서술(일부)
#   META_SOGAM   규정: 윤리 규정류의 '긍지와 보람' 조문 오탐(일부) ·
#                보도: 기관장 인용 소감이 규범(bodo.서술.인용) + 인명 '김보람'
#                오탐(일부). 의문형 종결(QUESTION_END)은 오탐 0이라 ALL 유지.
#                물음표([?？])는 따로 갈라 규정에도 건다 — jomun 이 '의문·감탄'을
#                금지하고 실측 0/문장. 보도자료만 뺀다: bodo 는 의문 금지가
#                없고 질의응답(Q&A) 붙임 관용이 있는데, 끝말 선별이 의문문을
#                거르는 잣대라 실측을 못 했다 — 못 잰 것에 하드 게이트를 대지 않는다
#   W-의연쇄     'N분의 1'(분수)·'그 밖의 X의'·'심의·전공의' 등 의-종결 명사
#                오탐 다수(규정 일부·보도 일부)
#   W-연도표기   규정: 부칙 정형구가 'YYYY년 M월 D일부터 시행한다'(jomun 실측,
#                일부) · 보도: 대외 공표문은 온전 연도(일부) ·
#                시행문(gongmun): 본문이 자료 원문의 공식 행사·기간명을 그대로 옮기는
#                자리라 온전 연도가 정상이다(작성원칙.날짜_기본.적용범위 — 축약은
#                '이 문서를 언제 썼나'를 적는 자리에만 해당, e2e s3 실측 2026-09-27) —
#                그래서 이 규칙만 별도 장르집합(연도표기_장르, 금지준용 - {gongmun})을 쓴다.
ALL = 아는장르                # 이름 그대로 전부이도록 위 등록에서 얻는다 — 손목록 금지
GAEJOSIK = {"onepage-report", "fullreport"}
# 슬라이드는 GAEJOSIK 에 넣지 않는다 — H-종결이 heading(=헤드메시지)까지 보는데,
# 헤드메시지는 완결 주장 문장이 규범이라 명사형 종결을 대면 정본과 부딪힌다.
# 본문 항목(item)만 보는 전용 행을 RULES 에 따로 둔다(정본 문체.profile 준용).
금지준용 = {"onepage-report", "gongmun", "fullreport", "slides"}

# W-연도표기 전용 장르 범위(2026-09-27 고침, r4/rules e2e s3) — shared.표기.date_day
# ('YY 꼴 축약)는 작성원칙.날짜_기본 이 밝히듯 **'이 문서를 언제 썼나'를 적는 자리**
# (1p byline·풀버전 표지 보고일)의 관례이지, 본문 속 공식 행사·기간명까지 줄이라는
# 뜻이 아니다(작성원칙.날짜_기본.적용범위). 시행문(gongmun)은 본문에 「2026년 하반기
# ○○ 교육」처럼 자료 원문이 못박은 공식 명칭·기간을 그대로 옮기는 게 정상인데,
# 금지준용 공통 집합에 얹혀 있어 이 연도까지 '26년으로 줄이라고 오탐했다(e2e s3
# 실측). 규정·보도자료는 애초에 금지준용 밖이라 이미 안 걸린다(부칙 정형구·대외
# 공표문이 온전 연도가 규범 — 위 RULES 표 주석). 시행문만 마저 뺀다.
연도표기_장르 = 금지준용 - {"gongmun"}

# (id, severity, 세그먼트, 패턴목록|callable, 설명, mode[full|tail], 장르)
RULES = [
    ("H-종결", "hard", {"title", "heading", "item", "cell"}, check_endings, "개조식 명사형 종결(§1)", None, GAEJOSIK),
    ("H-종결", "hard", {"item"}, check_endings,
     "개조식 명사형 종결(§1) — 슬라이드 본문 항목(헤드메시지는 주장문이 규범이라 제외)", None, {"slides"}),
    ("H-hype", "hard", BODY, HYPE, "hype 어휘(§5)", "full", ALL),
    ("H-과장", "hard", BODY, GWAJANG, "의미 과장(§5)", "full", ALL),
    ("H-번역투", "hard", BODY, check_beonyeoktu,
     "번역투(§2-1·§3-1) — 법령 원문 인용·시행문 관행구 제외", None, 금지준용),
    ("H-이중피동", "hard", BODY, IJUNG_PIDONG, "이중피동(§2-1)", "full", ALL),
    ("H-군더더기것", "hard", {"summary", "item"}, GEOT_HEDGE, "'것으로'류 헤지(§2-1)", "full", 금지준용),
    ("H-군더더기것", "hard", {"summary", "item"}, check_possibility, "'~ㄹ 수 있다'(§2-1)", None, 금지준용),
    ("H-메타·의문·소감", "hard", BODY, META_SOGAM, "메타발언·1인칭 소감(§5)", "full", 금지준용),
    ("H-메타·의문·소감", "hard", BODY, QUESTION_MARK, "물음표(§5)", "full", 금지준용 | {"regulation"}),
    ("H-메타·의문·소감", "hard", BODY, QUESTION_END, "의문형 종결·소감 종결(§5)", "tail", ALL),
    ("H-마커직입", "hard", {"summary", "item"}, MARKER_START, "마커 직접 입력(shared.표기)", "full", ALL),
    ("W-군더더기", "soft", {"summary", "item", "cell"}, GUNDEODEOGI, "의미 중복(§3-2)", "full", ALL),
    ("W-번역투의심", "soft", {"summary", "item", "cell"}, BEONYEOKTU_UISIM,
     "표면형으로 용법 판별 불가한 번역투 후보(§3-1)", "full", ALL),
    ("W-의연쇄", "soft", {"summary", "item"}, UI_YEONSWAE, "'의' 2회 연쇄(§2-1)", "full", 금지준용),
    ("W-연도표기", "soft", {"summary", "item", "cell", "heading"}, check_yeondo, "연도 표기(shared.표기)", None, 연도표기_장르),
]


def run_rule(text, checker, mode, genre=None):
    if callable(checker):
        return checker(text, genre)
    hits = []
    target = tail(text) if mode == "tail" else text
    for rx, hint in checker:
        m = re.search(rx, target)
        if m:
            hits.append((m.group(0), hint))
    return hits


def lint_segment(seg, text, level=2, genre="onepage-report", 목적=None):
    """한 세그먼트 판정. returns (hard[], soft[]) — 각 항목 {rule, hit, msg, text}.

    목적(설득|보고|None) — 슬라이드 헤드메시지 판정에만 쓴다(lint_doc 이 문서 하나당
    한 번 재서 넘긴다, 2026-09-26 고침 r2/check.json #7)."""
    hard, soft = [], []
    t = plain(text)
    if not t or seg in SOFT_ONLY_SEGS:
        return hard, soft

    def add(bucket, rule, hit, msg):
        bucket.append({"rule": rule, "hit": hit, "msg": msg, "text": snip(t)})

    for rule_id, sev, segs, checker, _desc, mode, genres in RULES:
        if seg not in segs or genre not in genres:
            continue
        for hit, hint in run_rule(t, checker, mode, genre):
            add(hard if sev == "hard" else soft, rule_id, hit, hint)

    # 슬라이드 헤드메시지 — 완결 주장 문장이 규범이다(정본 문체.헤드메시지).
    # 명사구 라벨이면 경고 — soft 다: 실물 부처 PPT 실측 전이라 하드 승격을 보류한다
    # (사장님 판정 '26-08-13 · '잰 것만 적는다'). 길이 40자도 같은 이유로 soft.
    # 2026-09-26 고침(r2/check.json #7) — 목적=보고 문서는 주제어형 제목이 규범이다
    # (사장님 판정 '26-09-07 · assemble_slides.py 도 목적으로 갈라 경고한다). 문체검사만
    # 목적을 안 봐 보고형 덱마다 헤드 수만큼 거짓 경고가 났다 — 목적=보고면 건너뛴다.
    if genre == "slides" and seg == "heading":
        tl = tail(t)
        if 목적 not in ("보고", "v2") and not re.search(r"(다|요|까|함|음|임)\s*[.!?]?\s*$", tl):
            add(soft, "W-헤드메시지", tl[-15:] if len(tl) > 15 else tl,
                "헤드메시지는 완결 주장 문장이 규범 — 명사구 카테고리 제목처럼 보입니다(정본 문체.헤드메시지)")
        if len(t) > 40:
            add(soft, "W-헤드길이", f"{len(t)}자",
                "헤드메시지 40자 초과 — 2줄 한계 잠정치(영문 8~14단어의 번안, 실측 전). 주장을 좁혀 주세요")

    # 시행문은 개조식이 아니라 공손체가 규범이다 — 금지 종결을 여기서도 본다
    if genre == "gongmun" and seg == "item":
        m2 = re.search(r"(요망|바람|할\s*것|하기\s*바람)\s*[.]?\s*$", t)
        if m2:
            add(hard, "H-공손체", m2.group(0).strip(),
                "시행문은 '~하시기 바랍니다'처럼 공손하게 맺습니다(gongmun-gyeoksik)")

    # 이모지 (전 세그먼트)
    m = EMOJI_RE.search(t)
    if m:
        add(hard, "H-이모지", m.group(0), "이모지·장식기호 금지 — 공문서 격식(§5)")

    # 길이 규칙 — 장르마다 분량 예산이 다르므로 강도가 다르다.
    #   1페이지: 한 장 예산에 직결 → 하드
    #   여러 장: 쪽 단위 예산을 따로 가진다 → 경고
    #   시행문: 경고 + 조언이 다르다(명사형 압축이 아니라 문장 분리)
    if seg == "item":
        n = len(t)
        # 규정·보도자료는 45자를 대지 않는다. 이 임계는 개조식 한 줄 예산에서 나온 값인데,
        # 두 장르는 서술형이라 실물 문장이 원래 그보다 훨씬 길다 — 실측(2026-08-04,
        # 규정 표본 사례·보도자료, skeleton.끝말 로 문장만 골라 셈):
        #   규정 중앙값·초과분포 / 보도자료 중앙값
        # 대면 실물 조문도 여러 글자수였다. 여기에 45자를 대면
        # 문서마다 경고가 십수 건 쏟아져 **진짜 지적이 묻힌다.**
        if genre in ("regulation", "press-release"):
            pass
        elif n > 45:
            if genre == "gongmun":
                # 2026-09-26(벤치마크 진단 GATE_FORCED, diagnosis.json s3): 안내 문구가
                # '문장을 나눠 주세요'였는데 에이전트가 문장은 그대로 두고 '참석자' 같은
                # 낱말(대상·목적어)만 빼서 줄였다 — 뜻이 흐려졌다. 무엇을 하라는지 분명히 한다.
                add(soft, "W-길이45", f"{n}자",
                    "45자 초과 — 문장을 둘로 나눠 주세요(시행문은 명사형으로 줄이면 격식이 "
                    "깨집니다). 대상·목적어 같은 낱말을 빼서 줄이지 마세요 — 뜻이 흐려집니다")
            elif genre == "onepage-report" and level == 2:
                add(hard, "H-길이45", f"{n}자", "○ 항목 45자 초과 — 압축 순서 적용(§2-2)")
            else:
                add(soft, "W-길이45", f"{n}자", "항목 45자 초과 — 압축 검토(§2-2)")
    if seg == "title" and len(t) > 30:
        add(soft, "W-제목길이", f"{len(t)}자",
            "제목 30자 초과 — 1줄 한계 실측(순한글 29·공백 포함 33, FB-013). 명사형 압축으로 단축")

    # 요약박스 전용
    if seg == "summary":
        tl = tail(t)
        if not SUMMARY_END_RE.search(tl):
            add(hard, "H-요약종결", tl[-12:],
                "요약 종결은 실질에 맞춰 '~보고드림'(단순보고)/'~요청드림'(결정요청)(§4)")
        n = len(t)
        if not (60 <= n <= 80):
            add(soft, "W-요약길이", f"{n}자", "요약 60~80자 권장(§4) — 렌더 게이트는 sumLines<=2")
        if "<span" in (text or ""):
            add(soft, "W-요약강조", "<span>", "요약박스는 강조 없음 — assemble이 제거함(shared.강조)")

    return hard, soft


# ── 문서 단위 ────────────────────────────────────────────────
# (아는장르 는 장르 가드와 붙어 있어야 해서 RULES 위로 올라갔다)


def doc_genre(doc):
    """이 문서가 어느 장르인가. 1페이지 문서에는 genre 필드가 없을 수도 있다.

    **한 장르가 이름을 둘 갖는다** — 화면에 심는 값(data-genre)과 내부 키가 다르다.
    1p 는 화면 'onepage' / 내부 'onepage-report'. genres.py 가 그 둘을 다 들고 있다.
    2026-08-05 A-2 시험에서 드러난 것: `api.새문서` 가 화면 이름을 문서에 심는데
    여기서는 내부 키만 알아봐서, 그렇게 만든 문서 **7건이 문서 단위 검사를 통째로
    건너뛰고 있었다**(표금지·요약실질·강조한도·delta기호가 한 번도 안 돌았다).
    조용히 통과였다 — 그래서 아무도 몰랐다.
    """
    g = doc.get("genre")
    if not g:
        return "onepage-report"
    if g in 아는장르:
        return g
    옮김 = _화면이름표().get(g)
    if 옮김:
        return 옮김
    return "_모름:" + g


def _화면이름표():
    """화면 이름(data-genre)·등록부 그루터기(이름) → 내부 키. **등록부에서 가져온다.**

    2026-09-26 고침(r2/check.json #8) — api.py 의 새문서가 화면 이름 대신 **등록부
    그루터기**('press')를 genre 에 심는 경로가 있다(`{"samples":"onepage"}.get(장르,장르)` —
    특례가 없는 장르는 그루터기 그대로 심긴다). 화면 이름만 찾던 이 표가 그 값을 못
    알아봐 doc_genre 가 '_모름:press'를 돌려주고, W-리드중복 을 비롯한 보도자료 문체
    게이트 전체가 그런 문서에서 한 번도 안 돌았다. 등록부 그루터기(이름)도 같이 키로
    얹는다 — 손목록이 아니라 genres.등록부() 가 이미 들고 있는 값이다."""
    global _화면표
    try:
        return _화면표
    except NameError:
        pass
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import genres as _g
    _화면표 = {}
    for x in _g.등록부():
        _화면표[x["장르"]] = x["키"]
        _화면표.setdefault(x["이름"], x["키"])
    return _화면표


def _cells(tb):
    for h in tb.get("header", []):
        yield "cell", h, 0
    for row in tb.get("rows", []):
        for c in row:
            yield "cell", c, 0


def iter_segments(doc):
    """문서에서 (seg, raw_text, level) 나열 — 장르마다 담는 그릇이 다르다.

    1페이지 스키마만 훑던 판은 시행문·풀버전에 '위반 0건'을 냈는데, 그건 통과가 아니라
    검사를 안 한 것이었다(2026-07-30 확인). 못 잰 것을 통과로 적지 않는다.
    """
    g = doc_genre(doc)
    if g == "regulation":
        # 규정은 조문 문체(§규정)를 쓴다 — 개조식 규칙과 다르므로 장르로 갈린다.
        yield "title", doc.get("제명", ""), 0
        for it in doc.get("본문", []) or []:
            if it.get("제목"):
                yield "heading", it["제목"], 0
            if it.get("text"):
                yield "item", it["text"], 2
        for b_ in doc.get("부칙", []) or []:
            for line in b_.get("본문", []) or []:
                yield "item", line, 2
        for t in doc.get("별표", []) or []:
            yield "heading", t.get("제목", ""), 0
            if t.get("표"):
                yield from _cells(t["표"])
        # 제정이유·주요내용 — 개조식 '~함'이 규범인 자리라 조문(item)과 다른 **새 세그먼트
        # 이름**으로 낸다('26-09-28 규정 처방 3단계). BODY 밖이라 기존 hard 규칙이 안 닿고,
        # doc_metrics(item 만 셈)·G77 기대값도 그대로다. 첫 주기에는 soft 만(SOFT_ONLY_SEGS).
        이유 = doc.get("제정이유")
        if isinstance(이유, list):
            이유 = " ".join(str(x) for x in 이유)
        if 이유:
            yield "reason", str(이유), 0
        주요 = doc.get("주요내용")
        if isinstance(주요, str):
            주요 = [x for x in 주요.split("\n") if x.strip()]
        for x in 주요 or []:
            if isinstance(x, str) and x.strip():
                yield "mainitem", x, 2
        return
    if g == "press-release":
        yield "title", doc.get("제목", ""), 0
        if doc.get("부제"):
            yield "heading", doc["부제"], 0
        if doc.get("리드"):
            yield "item", doc["리드"], 2
        for it in doc.get("본문", []) or []:
            if "표" in it:
                yield from _cells(it["표"])
            else:
                yield "item", it.get("text", ""), it.get("level", 2)
        for a_ in doc.get("붙임", []) or []:
            yield "item", a_ if isinstance(a_, str) else str(a_), 3
        return
    if g == "slides" and ("판형" in doc or (isinstance(doc.get("장"), list) and "슬라이드" not in doc)):
        # 슬라이드 v2(부품 트리, '26-09-28) — 머리 메시지는 heading, 개조식 항목 자리(카드·글머리·
        # 색띠행·체계도 과제 항목·항목타일 글)는 item, 표 칸은 cell. 라벨·요지띠·리드·차트 글은 메시지구·
        # 라벨이라 개조식 종결 잣대를 대지 않는다(정본 문체.문체_v2). 출처·노트는 규칙 밖.
        yield "title", doc.get("제목", ""), 0
        for 장 in doc.get("장") or []:
            if not isinstance(장, dict):
                continue
            머리 = 장.get("머리") if isinstance(장.get("머리"), dict) else {}
            if 머리.get("메시지"):
                yield "heading", 머리["메시지"], 0
            칸목록 = []
            for c in 장.get("칸") or []:
                if isinstance(c, dict) and c.get("부품") == "세로묶음":
                    칸목록 += [x for x in c.get("칸") or [] if isinstance(x, dict)]
                elif isinstance(c, dict):
                    칸목록.append(c)
            for c in 칸목록:
                n = c.get("부품")
                if n in ("카드", "글머리"):
                    for it in c.get("항목") or []:
                        if isinstance(it, str):
                            yield "item", it, 2
                        elif isinstance(it, dict):
                            yield "item", it.get("글", ""), 2
                            for sub in it.get("하위") or []:
                                yield "item", sub, 3
                elif n == "항목타일" and c.get("글"):
                    yield "item", c["글"], 2
                elif n == "색띠행":
                    for r in c.get("행") or []:
                        for it in (r.get("항목") or []) if isinstance(r, dict) else []:
                            yield "item", it, 2
                elif n == "체계도":
                    for t in c.get("과제") or []:
                        for it in (t.get("항목") or []) if isinstance(t, dict) else []:
                            yield "item", it, 2
                elif n == "표":
                    for c0 in c.get("머리행") or []:
                        yield "cell", c0, 0
                    for row in c.get("행") or []:
                        for cell in row if isinstance(row, list) else []:
                            yield "cell", (cell.get("글", "") if isinstance(cell, dict) else cell), 0
        return
    if g == "slides":
        # 슬라이드 — 헤드메시지는 heading 으로 낸다. H-종결의 슬라이드 행은 item 만
        # 보므로 헤드메시지(주장문)엔 종결 규칙이 안 닿는다. 표지 부제는 잣대가 아직
        # 없어 안 낸다(실측 후). 출처 줄도 규칙 밖(관용 표기).
        yield "title", (doc.get("표지") or {}).get("제목", ""), 0
        for s in doc.get("슬라이드", []) or []:
            if s.get("헤드메시지"):
                yield "heading", s["헤드메시지"], 0
            for it in s.get("항목", []) or []:
                if isinstance(it, str):
                    yield "item", it, 2
                else:
                    yield "item", it.get("text", ""), it.get("level", 2)
            if s.get("표"):
                yield from _cells(s["표"])
        return
    if g == "gongmun":
        yield "title", doc.get("제목", ""), 0
        for it in doc.get("본문", []):
            if "표" in it:
                yield from _cells(it["표"])
            else:
                yield "item", it.get("text", ""), it.get("level", 2)
        for a in doc.get("붙임", []) or []:
            yield "item", a, 3
        return
    if g == "fullreport":
        yield "title", (doc.get("표지") or {}).get("제목", ""), 0
        for b in (doc.get("요약") or {}).get("블록", []) or []:
            yield "heading", b.get("제목", ""), 0
            for it in b.get("항목", []) or []:
                yield "item", it.get("text", ""), 2
                for sub in it.get("세부", []) or []:
                    yield "item", sub, 3
        for ch in doc.get("장", []) or []:
            yield "heading", ch.get("제목", ""), 0
            for sec in ch.get("절", []) or []:
                yield "heading", sec.get("제목", ""), 0
                for it in sec.get("항목", []) or []:
                    yield "item", it.get("text", ""), it.get("level", 2)
                if sec.get("표"):
                    yield from _cells(sec["표"])
            if ch.get("표"):
                yield from _cells(ch["표"])
        return
    yield "title", doc.get("title", ""), 0
    yield "summary", doc.get("summary", ""), 0
    for sec in doc.get("sections", []):
        yield "heading", sec.get("heading", ""), 0
        for it in sec.get("items", []):
            yield "item", it.get("html", ""), it.get("level", 2)
    tb = doc.get("table")
    if tb:
        yield from _cells(tb)


REQUEST_TYPES = {"②", "⑩", "⑪", "⑫"}   # 결정·승인·협조 요청이 유형의 정의 → 요약은 요청드림류가 자연
REPORT_TYPES = {"①", "⑤", "⑥", "⑧"}  # 공유·기록이 유형의 정의 → 요약은 보고드림이 자연
# ③④⑦⑨는 실질이 갈려 중립(판정 없음). 정밀 판정은 빌드플랜 목적 연계 후속(FB-016).


# 표를 넣지 않는 유형 — 표정책 '비권장'은 **금지**다(사장님 판정 2026-08-04).
# ⑤ 이슈·리스크(속도 우선·서술 위주) · ⑦ 회의안건(회의 자료가 따로 있으니 안건은 짧게).
# 온톨로지 목차로직 types[].표정책 이 정본이고 여기는 집행이다 —
# verify_all 의 check_table_policy_sync() 가 둘이 갈리는지 본다.
NO_TABLE_TYPES = {"⑤", "⑦"}


_리드중복_수치_RE = re.compile(r"\d[\d,.]*")
# 완전한 날짜·시각 꼴만 미리 지우고 남은 수만 비교한다(2026-09-27 단순화, r3/check.json —
# still_partly #8·new_defects). 옛 방식은 수 바로 뒤 글자 두 개(년·월·일·시·분)만 보고
# **개별 수마다** 뺐다 — 그러면 기간·시간·연수 되풀이('7일→3일'·'14분→6분'·'3년간
# 120기', 보도자료의 핵심 성과 수치)까지 통째로 못 잡았다(새 결함). 완전한 날짜 패턴
# (YYYY년 M월 D일 · M월 D일 · 'YY. M. D. · 2026. 9. 1. · HH:MM)을 문자열에서 먼저
# 지우면 날짜 자체는 비교에서 빠지고, 단독 '7일'·'14분'·'3년간'은 수로 그대로 남는다.
_완전날짜_RX = re.compile(
    r"(?:'?\d{2,4}년\s*)?\d{1,2}월\s*\d{1,2}일"    # 2026년 9월 1일 · '26년 9월 1일 · 9월 1일
    r"|'\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?"           # '26. 9. 1.
    r"|\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?"            # 2026. 9. 1.
    r"|\d{1,2}:\d{2}"                                # 13:00
)


def _수치토큰집합(t):
    """숫자만 뽑아 표기 흔들림(쉼표) 없이 견준다 — 지어냈나.py 숫자들()과 같은 결.
    단, 완전한 날짜·시각 꼴은 먼저 지운다(위 주석) — 기간·시간·연수(7일·14분·3년간)는
    그대로 남는다."""
    t = _완전날짜_RX.sub(" ", t or "")
    out = set()
    for m in _리드중복_수치_RE.finditer(t):
        v = m.group(0).strip(".,").replace(",", "")
        if v:
            out.add(v)
    return out


def _본문_첫_항목_text(doc):
    """리드 바로 다음에 오는 첫 □·○ 항목 — 표(level 0/'표' 키)는 건너뛴다."""
    for it in doc.get("본문") or []:
        if isinstance(it, dict) and "표" not in it and it.get("text"):
            return it["text"]
    return ""


def _press_lead_dup_check(doc, soft):
    """W-리드중복 — 보도자료 리드의 핵심 수치가 바로 다음 항목에서 거의 그대로
    되풀이되는지 본다. 2026-09-26(벤치마크 진단): 리드는 전체 요지, 본문 첫 항목은
    구체 사실을 펼치는 자리인데 둘이 같은 내용을 되풀이하면 본문이 리드의 동어반복이
    된다 — 정본 규칙은 document_types.press-release '리드와 본문 첫 항목 중복 금지'
    (묶음 D). 공유하는 **독립된 수 토큰**(날짜가 아닌 것)이 3개 이상이면 경고한다.

    2026-09-27 단순화(r3/check.json) — 어절 자카드(문장 유사도) 경로는 뺐다. 그
    경로는 리드·첫 항목이 같은 사업명을 쓰는 정상적인 경우(예: '겨울철 난방비 지원'
    3어절)만 겹쳐도 울려, 멀쩡한 첫 항목을 되풀이로 오탐했다(새 결함) — 좁은 표본
    (양성 1·음성 1)으로 정한 임계라 변별력도 약했다. 수치는 표현이 달라져도 값이
    그대로라 안전한 신호지만, 어절 겹침은 사업명 같은 공유 맥락과 진짜 중복을 못
    가른다. 숫자 없는 문장 되풀이(예: '요지만 넣으면 …')는 이 단순화로 못 잡게
    됐다 — 안전이 속도보다 먼저이므로, 애매한 신호로 매번 되묻느니 놓치는 쪽을 고른다."""
    리드 = plain(doc.get("리드") or "")
    첫항목 = plain(_본문_첫_항목_text(doc))
    if not 리드 or not 첫항목:
        return
    겹침 = _수치토큰집합(리드) & _수치토큰집합(첫항목)
    if len(겹침) >= 3:
        soft.append({"rule": "W-리드중복", "hit": ",".join(sorted(겹침)),
                     "msg": "리드의 핵심 수치가 바로 다음 □·○ 항목에서 거의 그대로 되풀이됩니다 "
                            "— 리드는 전체 요지, 본문 첫 항목은 다른 사실을 펼치도록 검토하세요"
                            "(document_types.press-release 리드·본문 중복 금지, 묶음 D)",
                     "text": snip(첫항목)})


def _fullreport_summary_items(doc):
    """풀버전 요약(있으면) 항목·세부 문장 — plain 텍스트만."""
    out = []
    for b in (doc.get("요약") or {}).get("블록", []) or []:
        for it in b.get("항목", []) or []:
            t = plain(it.get("text", "") if isinstance(it, dict) else str(it))
            if t:
                out.append(t)
            for sub in it.get("세부", []) or [] if isinstance(it, dict) else []:
                t2 = plain(sub if isinstance(sub, str) else str(sub))
                if t2:
                    out.append(t2)
    return out


def _fullreport_body_items(doc):
    """풀버전 본문(장·절) 항목 문장 — plain 텍스트만(표 칸 제외)."""
    out = []
    for ch in doc.get("장", []) or []:
        for sec in ch.get("절", []) or []:
            for it in sec.get("항목", []) or []:
                t = plain(it.get("text", "") if isinstance(it, dict) else str(it))
                if t:
                    out.append(t)
    return out


# R56-08(2026-09-28) — 연도 약칭·범위('YY·YYYY년·'YY~'YY)와 서수 라벨(N단계·N차·
# N개년·N분기)은 "같은 사업을 가리키는 기간·차수 표시"라 요약·본문에 같이 나오는
# 게 정상이다(_수치토큰집합 은 완전한 날짜만 지우고 이 부류는 그대로 남긴다 —
# W-리드중복 쪽은 실측·골든이 그대로 커버하는 영역이라 그 쪽은 손대지 않는다).
# 735행(옛) 문턱 len(겹침)>=2 를 연도 하나 + 서수 하나만으로 채워, 정본 표본
# (rc-fullreport-energy)과 합성 문서 양쪽에서 본문이 왜·어떻게로 관점을 바꿨는데도
# 경고가 났다(R56-08 실측) — 요약·본문 중복 검사에서만 이 부류를 겹침 셈에서 뺀다.
_연도_서수_라벨_RX = re.compile(
    r"'?\d{2,4}\s*년(?:\s*[~\-]\s*'?\d{2,4}\s*년)?"   # '25년 · 2025년 · '26~'27년
    r"|'\d{2}(?=\D|$)"                                  # 낱개 '26(년 생략, 연도 약칭 관용)
    r"|\d{1,2}\s*(?:단계|차|개년|분기)"                  # 1단계 · 2차 · 3개년 · 1분기
)


def _요약본문중복_수치토큰집합(t):
    """W-요약본문중복 전용 — 연도 약칭·범위·서수 라벨을 겹침 셈에서 뺀 수치 토큰
    집합(R56-08, 위 주석). W-리드중복(보도자료)은 이 좁힘을 안 쓴다 — 결함의 재현·
    근거가 전부 풀버전 요약·본문 겹침에서만 났다(실측 범위 밖으로 넓히지 않는다).

    **완전한 날짜부터 먼저 지운다.** _연도_서수_라벨_RX 를 먼저 걸면 그 안의 낱개
    '\\d{2}(?=\\D|$)' 갈래가 '「'26. 6. 26.」' 같은 완전한 날짜의 **앞머리만**
    ('26) 잘라 먹어, 뒤에 남은 '. 6. 26.' 을 _완전날짜_RX 가 더는 통째로 못 알아보고
    '6'·'26' 이 낱개 수 토큰으로 살아남았다(정본 rc-fullreport-energy 실측 —
    R56-08 을 고치다 새로 낼 뻔한 회귀, G81 재현으로 잡음). 완전한 날짜를 먼저
    지우면 그 다음에 연도 약칭·서수 라벨을 걸어도 서로 안 부딪힌다."""
    t = _완전날짜_RX.sub(" ", t or "")
    t = _연도_서수_라벨_RX.sub(" ", t)
    return _수치토큰집합(t)


def _fullreport_summary_dup_check(doc, soft):
    """W-요약본문중복 — 풀버전 요약 항목·세부가 본문(장·절 항목)과 같은 수치를
    그대로 되풀이하는지 본다(2026-09-27, r4/rules e2e s2 — 실측: 요약 세부의 '임차료
    3,100만 원·1인당 1.5시간' 문장이 본문 Ⅱ장 항목에 그대로 재기술됨. 정본:
    document_types.fullreport.골격.요약_본문_중복_금지 — '요약에서 이미 쓴 문장은
    본문에서 관점을 바꾸거나(왜·어떻게) 생략한다'). 보도자료 W-리드중복과 같은 결로
    잰다 — 표현이 달라져도 값이 그대로인 **수치 토큰의 겹침**을 신호로 삼는다(문장
    유사도는 사업명 같은 정상적 공유 맥락과 진짜 중복을 못 가른다, 위 주석 참고).
    한 요약 문장이 본문 어느 한 문장과 독립 수치를 2개 이상 공유하면 경고한다 —
    단, 연도·서수 라벨은 그 겹침에서 뺀다(R56-08, 위 _요약본문중복_수치토큰집합)."""
    요약문장 = _fullreport_summary_items(doc)
    본문문장 = _fullreport_body_items(doc)
    if not 요약문장 or not 본문문장:
        return
    본 = [(t, _요약본문중복_수치토큰집합(t)) for t in 본문문장]
    본 = [(t, s) for t, s in 본 if s]
    본겹침 = set()
    for s in 요약문장:
        s수 = _요약본문중복_수치토큰집합(s)
        if len(s수) < 2:
            continue
        for t, t수 in 본:
            겹침 = s수 & t수
            if len(겹침) >= 2:
                본겹침.add((tuple(sorted(겹침)), snip(t)))
    for 겹침, 본문스닙 in sorted(본겹침):
        soft.append({"rule": "W-요약본문중복", "hit": ",".join(겹침),
                     "msg": "요약의 수치·사실이 본문 항목에서 거의 그대로 되풀이됩니다 "
                            "— 본문은 관점을 바꾸거나(왜·어떻게) 생략을 검토하세요"
                            "(document_types.fullreport.골격.요약_본문_중복_금지)",
                     "text": 본문스닙})


_조문꼴_모듈 = None


def _조문꼴():
    """build/조문꼴.py 를 이 파일 옆에서 불러온다(sys.path 를 건드리지 않는다 — 이 파일은
    스크립트로도·모듈로도 불린다). 한 번 올린 것은 다시 쓴다."""
    global _조문꼴_모듈
    if _조문꼴_모듈 is None:
        import importlib.util
        import os
        m = sys.modules.get("조문꼴")
        if m is None:
            spec = importlib.util.spec_from_file_location(
                "조문꼴", os.path.join(os.path.dirname(os.path.abspath(__file__)), "조문꼴.py"))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        _조문꼴_모듈 = m
    return _조문꼴_모듈


_슬라이드v2_모듈 = None


def _슬라이드v2():
    """build/슬라이드v2.py(슬라이드 신설 soft·판형 판별) — _조문꼴 과 같은 방식으로 이 파일 옆에서."""
    global _슬라이드v2_모듈
    if _슬라이드v2_모듈 is None:
        import importlib.util
        import os
        m = sys.modules.get("슬라이드v2")
        if m is None:
            spec = importlib.util.spec_from_file_location(
                "슬라이드v2", os.path.join(os.path.dirname(os.path.abspath(__file__)), "슬라이드v2.py"))
            m = importlib.util.module_from_spec(spec)
            sys.modules["슬라이드v2"] = m
            spec.loader.exec_module(m)
        _슬라이드v2_모듈 = m
    return _슬라이드v2_모듈


def doc_level_checks(doc):
    """개별 세그먼트가 아닌 문서 단위 점검. (hard, soft) 를 돌려준다."""
    soft, hard = [], []
    if doc_genre(doc) == "slides":
        # 슬라이드 신설 soft('26-09-28, 전부 soft 로 시작) — v2(부품 트리)는 타임라인 순서·모호 시점·
        # 맥락 없는 큰숫자·차트 강조 계열·선차트 반복·마무리 요청·표지 태그, 옛 문서는 타임라인 순서·
        # 막대 2개·맥락 없는 큰숫자. 판정은 build/슬라이드v2.py 한 곳에 있다(hard 는 새로 만들지 않는다 —
        # v2 hard 는 조립 게이트 build/slides_v2_gate.py 몫).
        try:
            soft += _슬라이드v2().소프트규칙(doc)
        except Exception as e:     # 모듈이 빠진 배포본 등 — 못 잰 것을 통과로 적지 않는다
            soft.append({"rule": "W-슬라이드검사못함", "hit": type(e).__name__,
                         "msg": "슬라이드 soft 검사(build/슬라이드v2.py)를 돌리지 못했습니다", "text": ""})
        return hard, soft
    if doc_genre(doc) == "press-release":
        _press_lead_dup_check(doc, soft)
        return hard, soft
    if doc_genre(doc) == "fullreport":
        _fullreport_summary_dup_check(doc, soft)
        return hard, soft
    if doc_genre(doc) == "regulation":
        # 규정 갈래('26-09-28 규정 처방 3단계) — soft: W-주요내용수치·W-비율섞임·W-술어섞임·W-조문물결, 적대검토 뒤
        # W-조문퍼센트·W-조문날짜, bench9 reg10 뒤 W-약칭자리·W-분수표기, reg13 뒤 W-안쓴약칭. 걷은 것 — W-기산점통보·
        # W-이의신청처리(reg13f F1), W-미정의용어·W-순환정의·W-역할어정의(reg13g H1, '26-10-01: 맞는 초안 헛경고). 판정은
        # build/조문꼴.py 한 곳에 있다(새문서의 결정론 교정과 같은 눈으로 본다). hard 는 새로 만들지 않는다.
        try:
            soft += _조문꼴().조문경고(doc)
        except Exception as e:     # 모듈이 빠진 배포본 등 — 못 잰 것을 통과로 적지 않는다
            soft.append({"rule": "W-조문검사못함", "hit": type(e).__name__,
                         "msg": "규정 조문 soft 검사(build/조문꼴.py)를 돌리지 못했습니다", "text": ""})
        return hard, soft
    if doc_genre(doc) != "onepage-report":
        return hard, soft    # 요약 실질·강조 한도는 1페이지 개념이다
    표수0 = (1 if doc.get("table") else 0) + sum(1 for s_ in doc.get("sections") or [] if s_.get("표"))
    if 표수0 and doc.get("purpose_type") in NO_TABLE_TYPES:
        hard.append({"rule": "H-표금지", "hit": f"{doc.get('purpose_type')} 표 {표수0}개",
                     "msg": "이 유형에는 표를 넣지 않습니다 — 상세는 별도 자료로 "
                            "(목차로직 표정책 '비권장'=금지, 사장님 판정 '26-08-04)",
                     "text": ""})
    ptype = doc.get("purpose_type")
    if ptype:
        end = tail(plain(doc.get("summary", "")))
        is_request = end.endswith(("요청드림", "요청함"))
        if ptype in REQUEST_TYPES and not is_request:
            soft.append({"rule": "W-요약실질", "hit": f"{ptype}+{end[-6:]}",
                         "msg": "결정·승인 유형인데 요약이 보고드림류 — 실질 확인(§4, FB-016)",
                         "text": ""})
        if ptype in REPORT_TYPES and is_request:
            soft.append({"rule": "W-요약실질", "hit": f"{ptype}+{end[-6:]}",
                         "msg": "공유·기록 유형인데 요약이 요청드림류 — 실질 확인(§4, FB-016)",
                         "text": ""})
    # 읽는 부담 — 한 장에 들어가도 걸릴 수 있다. 조판 게이트는 '드는가'만 보고
    # '읽히는가'는 안 본다. 사장님 판정 2026-08-04.
    표수 = (1 if doc.get("table") else 0) + sum(1 for s_ in doc.get("sections") or [] if s_.get("표"))
    if 표수 >= 2:
        soft.append({"rule": "W-표개수", "hit": f"{표수}개",
                     "msg": "표가 둘 이상 — 하나로 합치거나 풀버전을 검토(R구-35, 사장님 판정 '26-08-04)",
                     "text": ""})
    for s_ in doc.get("sections") or []:
        n = sum(1 for it in (s_.get("items") or []) if (it.get("level") or 2) == 2)
        if n >= 5:
            soft.append({"rule": "W-항목묶음", "hit": f"{snip(plain(s_.get('heading','')),10)} {n}개",
                         "msg": "한 절에 ○ 항목이 다섯 이상 — 묶어서 줄이면 읽기 쉬워집니다"
                            "(원문 R구-40④는 7개, 실무 판정으로 5개부터 '26-08-04)",
                         "text": ""})
    raw = json.dumps(doc, ensure_ascii=False)
    n_accent = raw.count('class=\\"accent\\"') + raw.count("class=\"accent\"")
    if n_accent > 2:
        soft.append({"rule": "W-강조한도", "hit": f"accent {n_accent}회",
                     "msg": "accent는 문서당 2회 이하 — assemble이 3회차부터 평문화(shared.강조)",
                     "text": ""})
    # `raw` 는 json.dumps 결과라 따옴표가 `\"` 로 이스케이프돼 있다.
    # 바로 위 accent 검사는 두 모양을 다 세는데 여기만 안 그래서 **한 번도 안 울렸다**
    # (2026-08-05 A-2 시험에서 발견). 증가 수치에 delta 를 붙여도 통과했고,
    # assemble 이 조용히 num 으로 강등해 빨강이 사라지는데 아무도 몰랐다.
    for m in re.finditer(r'<span class=\\?"delta\\?">(.*?)</span>', raw):
        if "△" not in m.group(1):
            soft.append({"rule": "W-delta기호", "hit": snip(plain(m.group(1)), 16),
                         "msg": "delta는 △ 포함 시만 — assemble이 num으로 강등(shared.강조)",
                         "text": ""})
    return hard, soft
    return soft


def doc_metrics(doc):
    """관측 지표 — 판정하지 않음. 귀납 트랙 데이터.

    2026-09-27 고침(r4/rules e2e s4·s5) — 예전엔 doc.get('sections') → item['html']
    (1p·samples 스키마)만 읽어서, 그 밖의 장르(규정·시행문·보도자료·풀버전·슬라이드)
    에서는 실제 내용과 무관하게 **항상 항목 0개·0자**로 찍혔다(판정 lint_doc 은
    iter_segments 로 장르별 분기가 이미 돼 있어 정확했지만, 이 관측 통계만 못 미쳤다
    — s4 는 조문 본문이 렌더에서 통째로 비었을 때도 이 진단이 똑같이 '0개'라 정상
    시도와 못 갈랐고, s5 는 보도자료 8개 세그먼트가 있는데도 0으로 찍혀 '이 장르는
    안 재는 것' 처럼 보이게 했다). iter_segments(doc) 로 장르 공통(같은 컨테이너
    분기)으로 바꿔, 판정이 보는 것과 같은 본문 세그먼트(item)를 관측한다."""
    items = [plain(text) for seg, text, _level in iter_segments(doc)
             if seg == "item" and plain(text)]
    endings = Counter(t.split()[-1] if t.split() else "" for t in map(tail, items))
    lens = [len(t) for t in items]
    joined = " ".join(items)
    filler = {
        "적(어말)": len(re.findall(r"[가-힣]적(?=[\s인의,.]|$)", joined)),
        "의": len(re.findall(r"[가-힣]의(?=\s)", joined)),
        "것": joined.count("것"),
        "들(어말)": len(re.findall(r"[가-힣]들(?=[\s,.·]|$)", joined)),
    }
    return {
        "항목수": len(items),
        "평균길이": round(sum(lens) / len(lens), 1) if lens else 0,
        "최장": max(lens) if lens else 0,
        "종결어_상위": endings.most_common(5),
        "군더더기_근사": filler,
    }


def lint_doc(doc):
    genre = doc_genre(doc)
    목적 = _슬라이드_목적(doc) if genre == "slides" else None
    hard, soft = [], []
    for seg, text, level in iter_segments(doc):
        h, s = lint_segment(seg, text, level, genre, 목적)
        hard += h
        soft += s
    _h, _s = doc_level_checks(doc)
    hard += _h
    soft += _s
    return {"filename": doc.get("filename", "?"), "genre": genre,
            "hard": hard, "soft": soft, "metrics": doc_metrics(doc)}


# ── 골든 테스트 ──────────────────────────────────────────────


def run_golden(path):
    cases = json.load(open(path))["cases"]
    failures = []
    for c in cases:
        # "doc" 케이스 — 세그먼트가 아니라 문서 단위 검사(doc_level_checks) 회귀용.
        # 2026-09-26 W-리드중복(보도자료 리드·본문 첫 항목 중복) 처럼 한 세그먼트가
        # 아니라 문서 전체를 봐야 판정되는 규칙은 lint_doc 을 그대로 돌려 견준다.
        if "doc" in c:
            r = lint_doc(c["doc"])
            got_h, got_s = {x["rule"] for x in r["hard"]}, {x["rule"] for x in r["soft"]}
            label = f"[doc:{c['doc'].get('genre','?')}] {c.get('note','')}"
        else:
            h, s = lint_segment(c["seg"], c["text"], c.get("level", 2),
                                c.get("genre", "onepage-report"), c.get("목적"))
            got_h, got_s = {x["rule"] for x in h}, {x["rule"] for x in s}
            label = f"[{c['seg']}] {snip(c['text'], 40)}"
        exp_h = set(c.get("expect", []))
        exp_s = set(c.get("expect_soft", []))
        problems = []
        if exp_h:
            missing = exp_h - got_h
            if missing:
                problems.append(f"미검출(hard): {sorted(missing)}")
        else:
            if got_h:
                problems.append(f"오탐(hard): {sorted(got_h)}")
        # doc 케이스는 새로 도입한 문서단위 규칙 전용이라 soft 도 엄격 대조한다(과대·과소
        # 둘 다 회귀) — 세그먼트 케이스는 예전부터 soft 과다검출을 안 봤으므로(G53·P09·P16
        # 처럼 부수 soft가 섞여도 통과해 왔다) 그 관행을 그대로 둔다(하위호환).
        if "doc" in c:
            if got_s != exp_s:
                problems.append(f"soft 불일치 — 기대 {sorted(exp_s)} / 실제 {sorted(got_s)}")
            # 관측 지표(doc_metrics, 판정과 무관) 회귀 가드 — 2026-09-27(r4/rules e2e
            # s4·s5): 장르별 컨테이너를 안 읽으면 항목수가 늘 0으로 찍히는 회귀가
            # 판정(PASS/FAIL) 대조만으로는 안 드러난다. 케이스가 최소 항목수를
            # 명시하면 그 이상인지만 본다(정확한 수는 세그먼트 셈법이 바뀔 때마다
            # 깨지기 쉬워, '0이 아니다'를 잡는 최소선만 지킨다).
            if "expect_metrics_항목수_최소" in c:
                got_n = r["metrics"]["항목수"]
                if got_n < c["expect_metrics_항목수_최소"]:
                    problems.append(f"관측 항목수 미달 — 기대 ≥{c['expect_metrics_항목수_최소']} / 실제 {got_n}")
        elif exp_s - got_s:
            problems.append(f"미검출(soft): {sorted(exp_s - got_s)}")
        if problems:
            failures.append((c, problems, got_h, got_s, label))
    print(f"골든 테스트: {len(cases)}건 중 {len(cases)-len(failures)}건 통과")
    for c, problems, got_h, got_s, label in failures:
        print(f"  ✗ {c['id']} {label}")
        for p in problems:
            print(f"      {p}")
        print(f"      실제: hard={sorted(got_h)} soft={sorted(got_s)}")
    return 1 if failures else 0


# ── CLI ──────────────────────────────────────────────────────


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--golden":
        return run_golden(args[1])

    docs = json.load(open(args[0]))
    results = [lint_doc(d) for d in docs]
    any_fail = any(r["hard"] for r in results)

    if "--json" in args:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    elif "--csv" in args:
        for r in results:
            verdict = f"FAIL:{len(r['hard'])}" if r["hard"] else "PASS"
            print(f"{r['filename']},{verdict},soft:{len(r['soft'])}")
    else:
        print("== 문체 게이트 (stylelint) ==")
        for r in results:
            verdict = "FAIL" if r["hard"] else "PASS"
            print(f"{r['filename']}: {verdict} (hard {len(r['hard'])}, soft {len(r['soft'])})")
            for x in r["hard"]:
                print(f"  [hard] {x['rule']} 「{x['hit']}」 — {x['msg']}")
                if x["text"]:
                    print(f"         └ {x['text']}")
            for x in r["soft"]:
                print(f"  [soft] {x['rule']} 「{x['hit']}」 — {x['msg']}")
            m = r["metrics"]
            top = " ".join(f"{w}({n})" for w, n in m["종결어_상위"] if w)
            print(f"  관측: 항목 {m['항목수']}개 · 평균 {m['평균길이']}자 · 최장 {m['최장']}자"
                  f" · 종결어 {top}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
