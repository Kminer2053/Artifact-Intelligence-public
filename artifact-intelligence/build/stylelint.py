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
    """HTML 태그 제거 + 엔티티 복원 + 공백 정규화(다중 공백 우회 차단)."""
    t = htmlmod.unescape(re.sub(r"<[^>]+>", "", s or ""))
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


def check_endings(t):
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
    (r"[와과]\s*관련(된|하여|한)", "'~ 관련'(§2-1)"),
]

IJUNG_PIDONG = [
    (r"(보여|되어|여겨|잊혀|쓰여|불려)[지진져질짐졌집]",
     "이중피동 → 단일피동(보이다/되다/여기다)(§2-1)"),
]

GEOT_HEDGE = [
    (r"(것으로|걸로)\s*(예상|전망|확인|판단|추정|기대|보)",
     "'~것으로 예상/확인' → '~예상/~확인'(§2-1)"),
    (r"것이\s*[^,.]{0,12}(필요|중요)", "'~필요'(§2-1)"),
]


def check_possibility(t):
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
    (r"[?？]", "수사의문문·물음표는 공문서에 없는 화법(§5)"),
]

QUESTION_END = [
    (r"(무엇인가|않을까|아닐까|어떨까|일까|할까|는가)$", "수사의문문(의문형 종결) 금지(§5)"),
    (r"생각(함|합니다|됩니다)$", "1인칭 소감 금지(§5)"),
]

# ○ 하나는 마커지만 ○○·○○○ 연속은 익명 표기다(기관 '○○공사'·인명 '○○○ 장관',
# bodo.서술.인용이 그 꼴을 규범으로 등재). 보도자료 정본 리드가 '○○공사는…'으로
# 시작해 오탐 2건이 실측됐다(2026-08-07). 단일 '○ ' 마커는 그대로 잡는다(골든 G43).
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
YEONDO = [(r"20\d{2}년", "연도는 '26년 표기(shared.표기 date_day)")]

SUMMARY_END_RE = re.compile(r"(보고드림|요청드림|요청함)$")

BODY = {"title", "heading", "summary", "item", "cell"}

# 이 검사기가 아는 장르. 여기 없는 장르는 **통과시키지 않고 '못 쟀다'로 남긴다** —
# 규정·보도자료가 1p 스키마로 떨어져 세그먼트 0개가 되고, 그게 '위반 0건 통과'로
# 보이던 것을 2026-08-04 에 찾았다. 못 잰 것을 통과로 적지 않는다.
아는장르 = {"onepage-report", "gongmun", "fullreport", "regulation", "press-release", "slides"}

# 어느 장르에 적용되는가 — 세 단이다. 개조식(명사형 종결)은 1페이지·풀버전의 규범이고,
# 시행문의 규범은 정반대다 — 공손체 서술어 완결('~하시기 바랍니다').
# 그래서 종결 규칙을 시행문에 걸면 안 된다(스킬 v3.6.12 장르 가드와 같은 판단).
#
# 규정(조문체)·보도자료(서술체)를 어디까지 미느냐는 실측으로 갈랐다(2026-08-07,
# 정본 등록부 4건 전수 + 실물 규정 23건 1,505문장·보도자료 150건(40_정부부처 정렬
# 앞 150건) 2,843문장 — 45자 규칙과 같은 잣대, skeleton.끝말 로 문장만 골라 셈):
#
# ALL — 다섯 장르 전부. hype·과장·이중피동·의문형 종결·마커 직입·군더더기류는
#   두 장르 실물에서도 규범 언어와 부딪히지 않았고(오탐 0 — 예외였던 '○○공사'
#   마커 오탐은 패턴에서 익명 표기를 갈라냈다), 정본도 명시한다: bodo.forbidden 이
#   '과장·hype 표현'과 이중피동을, jomun.forbidden 이 '의문·감탄'을 금지.
#
# 금지준용 — gongmun-gaejosik.금지를 전면 준용하는 세 장르만(시행문은 gyeoksik의
#   '공통적용' 조항으로, 풀버전은 같은 개조식이라). jomun·bodo 프로파일엔 준용
#   조항이 없고, 아래 표면형은 그 장르의 **규범 언어**라 걸면 정본 실물이 FAIL 한다:
#   H-번역투     규정 23/23건 284회('에 대한·로부터·에 의한' — 조문 관용) ·
#                보도 137/149건 901회('통해'×345 — 서술 관용. bodo 금지는
#                번역투 범주 전체가 아니라 이중피동만이다)
#   H-군더더기것 규정: 간주조항 '~것으로 본다'(경과조치 정형구, 2/23건) ·
#                보도: '~것으로 기대'×63(기대효과 정형구, 41/149건)
#   ~ㄹ수있다    규정: 재량조항 — jomun.종결 rule 이 '~할 수 있다'를 규범으로
#                등재(실측 14.9%, 22/23건 194회) · 보도: 능력 서술(98/149건)
#   META_SOGAM   규정: 윤리 규정류의 '긍지와 보람' 조문 오탐(1/23건) ·
#                보도: 기관장 인용 소감이 규범(bodo.서술.인용) + 인명 '김보람'
#                오탐(13/149건). 의문형 종결(QUESTION_END)은 오탐 0이라 ALL 유지.
#                물음표([?？])는 따로 갈라 규정에도 건다 — jomun 이 '의문·감탄'을
#                금지하고 실측 0/1,505문장. 보도자료만 뺀다: bodo 는 의문 금지가
#                없고 질의응답(Q&A) 붙임 관용이 있는데, 끝말 선별이 의문문을
#                거르는 잣대라 실측을 못 했다 — 못 잰 것에 하드 게이트를 대지 않는다
#   W-의연쇄     'N분의 1'(분수)·'그 밖의 X의'·'심의·전공의' 등 의-종결 명사
#                오탐 다수(규정 13/23건·보도 23/149건)
#   W-연도표기   규정: 부칙 정형구가 'YYYY년 M월 D일부터 시행한다'(jomun 실측,
#                23/23건 235회) · 보도: 대외 공표문은 온전 연도(51/149건 142회)
ALL = 아는장르                # 이름 그대로 전부이도록 위 등록에서 얻는다 — 손목록 금지
GAEJOSIK = {"onepage-report", "fullreport"}
# 슬라이드는 GAEJOSIK 에 넣지 않는다 — H-종결이 heading(=헤드메시지)까지 보는데,
# 헤드메시지는 완결 주장 문장이 규범이라 명사형 종결을 대면 정본과 부딪힌다.
# 본문 항목(item)만 보는 전용 행을 RULES 에 따로 둔다(정본 문체.profile 준용).
금지준용 = {"onepage-report", "gongmun", "fullreport", "slides"}

# (id, severity, 세그먼트, 패턴목록|callable, 설명, mode[full|tail], 장르)
RULES = [
    ("H-종결", "hard", {"title", "heading", "item", "cell"}, check_endings, "개조식 명사형 종결(§1)", None, GAEJOSIK),
    ("H-종결", "hard", {"item"}, check_endings,
     "개조식 명사형 종결(§1) — 슬라이드 본문 항목(헤드메시지는 주장문이 규범이라 제외)", None, {"slides"}),
    ("H-hype", "hard", BODY, HYPE, "hype 어휘(§5)", "full", ALL),
    ("H-과장", "hard", BODY, GWAJANG, "의미 과장(§5)", "full", ALL),
    ("H-번역투", "hard", BODY, BEONYEOKTU, "번역투(§2-1·§3-1)", "full", 금지준용),
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
    ("W-연도표기", "soft", {"summary", "item", "cell", "heading"}, YEONDO, "연도 표기(shared.표기)", "full", 금지준용),
]


def run_rule(text, checker, mode):
    if callable(checker):
        return checker(text)
    hits = []
    target = tail(text) if mode == "tail" else text
    for rx, hint in checker:
        m = re.search(rx, target)
        if m:
            hits.append((m.group(0), hint))
    return hits


def lint_segment(seg, text, level=2, genre="onepage-report"):
    """한 세그먼트 판정. returns (hard[], soft[]) — 각 항목 {rule, hit, msg, text}."""
    hard, soft = [], []
    t = plain(text)
    if not t:
        return hard, soft

    def add(bucket, rule, hit, msg):
        bucket.append({"rule": rule, "hit": hit, "msg": msg, "text": snip(t)})

    for rule_id, sev, segs, checker, _desc, mode, genres in RULES:
        if seg not in segs or genre not in genres:
            continue
        for hit, hint in run_rule(t, checker, mode):
            add(hard if sev == "hard" else soft, rule_id, hit, hint)

    # 슬라이드 헤드메시지 — 완결 주장 문장이 규범이다(정본 문체.헤드메시지).
    # 명사구 라벨이면 경고 — soft 다: 실물 부처 PPT 실측 전이라 하드 승격을 보류한다
    # (사장님 판정 '26-08-13 · '잰 것만 적는다'). 길이 40자도 같은 이유로 soft.
    if genre == "slides" and seg == "heading":
        tl = tail(t)
        if not re.search(r"(다|요|까|함|음|임)\s*[.!?]?\s*$", tl):
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
        # 사용자제공 규정 23건·보도자료 150건, skeleton.끝말 로 문장만 골라 셈):
        #   규정 중앙 64자·46자 초과 69.7% / 보도자료 중앙 77자·80.5%
        # 대면 실물 조문도 84·66·93·99·123·102·144자였다. 여기에 45자를 대면
        # 문서마다 경고가 십수 건 쏟아져 **진짜 지적이 묻힌다.**
        if genre in ("regulation", "press-release"):
            pass
        elif n > 45:
            if genre == "gongmun":
                add(soft, "W-길이45", f"{n}자",
                    "45자 초과 — 문장을 나눠 주세요(시행문은 명사형으로 줄이면 격식이 깨집니다)")
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
    """화면 이름(data-genre) → 내부 키. **등록부에서 가져온다.**"""
    global _화면표
    try:
        return _화면표
    except NameError:
        pass
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import genres as _g
    _화면표 = {x["장르"]: x["키"] for x in _g.등록부()}
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


def doc_level_checks(doc):
    """개별 세그먼트가 아닌 문서 단위 점검. (hard, soft) 를 돌려준다."""
    soft, hard = [], []
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
    """관측 지표 — 판정하지 않음. 귀납 트랙 데이터."""
    items = [plain(it.get("html", "")) for sec in doc.get("sections", [])
             for it in sec.get("items", [])]
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
    hard, soft = [], []
    for seg, text, level in iter_segments(doc):
        h, s = lint_segment(seg, text, level, genre)
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
        h, s = lint_segment(c["seg"], c["text"], c.get("level", 2))
        got_h = {x["rule"] for x in h}
        got_s = {x["rule"] for x in s}
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
        if exp_s - got_s:
            problems.append(f"미검출(soft): {sorted(exp_s - got_s)}")
        if problems:
            failures.append((c, problems, got_h, got_s))
    print(f"골든 테스트: {len(cases)}건 중 {len(cases)-len(failures)}건 통과")
    for c, problems, got_h, got_s in failures:
        print(f"  ✗ {c['id']} [{c['seg']}] {snip(c['text'], 40)}")
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
