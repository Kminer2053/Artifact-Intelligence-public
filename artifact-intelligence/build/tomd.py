#!/usr/bin/env python3
"""3층 JSON → 마크다운. HWPX 로 가는 다리이자, 그 자체로 산출물이다.

왜 마크다운을 거치나: kordoc generate 가 마크다운을 받아 공문서 HWPX 를 만든다.
슬롯 채우기(옛 방식)와 달리 문서 길이·구조에 제약이 없다.

**위계를 한 단 들여쓴다.** kordoc 은 목록 첫 단에 □ 를 준다. 우리는 절 제목(h2)이
이미 □ 이므로, 항목은 그 아래(○)에서 시작해야 위계가 맞는다. 안 들여쓰면
○ 항목이 □ 로 나온다(2026-08-05 실측 확인).

2026-09-26(벤치마크 진단, 내부 기록·diagnosis.json): 장르별로
거의 비어 나갔다 — 풀버전은 표지 제목 한 줄뿐('요약'·'장' 구조를 안 읽음), 슬라이드는
표지 제목뿐('슬라이드' 배열을 안 읽음), 규정은 항·호가 있어도 번호가 없고 조 제목이
장 제목과 같은 ## 수준이었고, 보도자료는 본문 level 이 정수(1~4)인데 옛 코드가 문자열
키("항"·"호"·"목")만 보는 dict.get(lv, 1) 이라 늘 기본값 1 로 떨어져 위계가 '-' 로
납작해지고 보도시점·부제·리드·담당도 안 나갔다. 장르마다 실제 3층 JSON 구조(build/*-docs.json
등록부)를 따라가는 전용 렌더러로 갈랐다.
"""
import json
import os
import re
import sys

# tomd.py 는 자료뿌리.모듈("tomd") 로도 불려(workspace/api.py) build/ 가 sys.path 에
# 없는 채로 실행될 수 있다 — 화면읽기.py 가 크롬찾기 를 불러올 때 쓰는 것과 같은
# 자기완결 패턴(어떻게 불려도 형제 모듈을 찾는다).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 수신꼴
import 표꼴
# ★ 조번호꼴 은 여기서 더 이상 import 하지 않는다('26-09-27 고침) — _규정_마크다운() 이
# 맞추기() 를 부르던 자리를 뺐다(그 함수 docstring 참고). 등록부의 주요내용은 새문서()
# 입구에서 이미 정정돼 있으므로 MD 변환은 있는 그대로만 읽는다.
try:
    # 본문에 섞인 '붙임' 표시 줄 분리 — assemble_gongmun.py 시행문 분기와 같이 부른다
    # (같은 이유로 예외). genre != "gongmun" 이면 스스로 아무것도 안 한다. 방어적
    # import(low, '26-09-27 재진단) — 미추적 새 파일이라 배포에서 커밋을 깜빡하면
    # 전 장르 MD 변환이 통째로 죽는다(tomd.py 는 6장르 모두를 거친다).
    import 붙임꼴
except Exception:
    붙임꼴 = None

# 진짜 HTML 태그만 지운다. `<고객지원처, '26. 7. 25.>` 같은 꺾쇠 표기를 태그로 보면
# 내용이 통째로 사라진다(2026-08-05에 byline 이 빈 채로 나갔다).
태그 = re.compile(r"</?(?:span|b|u|i|em|strong|br|p|div|lb)\b[^>]*/?>", re.I)


def 벗김(h):
    # 표지 제목처럼 줄바꿈이 그대로 든 값이 있다(예: "부서 업무체계(…)\n구축·확산 추진계획") —
    # 안 지우면 마크다운에서 헤딩이 둘째 줄부터 평문으로 떨어져 나간다(2026-09-26 확인).
    s = 태그.sub("", str(h or "")).strip()
    return re.sub(r"\s+", " ", s).strip()


def _안전레벨(v, 기본=2):
    """level 값을 정수로 — 스키마는 정수를 약속하지만 소형 모델이 '○'·'하위' 같은 문자열을
    낼 수 있다(2026-09-26, r2/check.json 크래시). 조립기(assemble_full·assemble_slides)는
    이런 값을 기본 클래스·기본 열거로 관용하는데, tomd 의 int() 는 그대로 ValueError 를 냈다
    — api.py 의 내보내기(hwpx 경로 포함)가 형식과 무관하게 먼저 `md = tomd.마크다운(doc)`
    를 부르므로(3028행 부근), MD 하나 쓰다 난 예외가 HWPX·'전부' 내보내기까지 함께 막았다.
    ('삼키되 안 멈춘다' 설계와 어긋난다 — 값이 이상해도 기본값으로 내고 계속 간다.)"""
    try:
        return int(v) if v else 기본
    except (TypeError, ValueError):
        return 기본


def 표를(t):
    # 정본은 절.표=단일 dict 지만, 모델이 리스트로 낼 때가 있다(assemble_full.py 의 같은
    # 흡수 주석 참조) — dict 가 아니면(list·문자열 등) t.get 호출 자체가 AttributeError로
    # 죽어 선행 호출(_풀버전_마크다운) 탓에 MD·HWPX·'전부' 내보내기가 다 막혔다(assemble:F2,
    # '26-09-27). 여기서도 방어해 어느 호출 경로로 list 가 들어와도 안 죽는다.
    if not isinstance(t, dict):
        return []
    # 한글 키 별칭(헤더/행) — 모델이 정본(header/rows) 대신 이 꼴로 낼 때가 흔하다.
    # assemble_slides._표정규화 와 같은 흡수인데, 그건 **조립기가 렌더 직전 메모리에서만**
    # 하는 정규화라 등록부(저장된 3층 JSON)는 한글 키 그대로 남는다. tomd 는 그 등록부를
    # 직접 읽으므로(assemble_slides.build() 를 안 거친다) 같은 흡수를 스스로 해야 한다 —
    # 안 하면 header 가 없다고 보고 표 전체를 [] 로 돌려줘 MD 내보내기에서 표 레이아웃
    # 슬라이드(또 절·본문에 박힌 표 전부)의 표 콘텐츠가 통째로 빠진다(고1, '26-09-27,
    # cli s6 실측: JSON·HTML·PDF·PPTX 는 정상인데 MD 만 빠짐).
    hdr = t.get("header")
    if not hdr and t.get("헤더") is not None:
        hdr = t.get("헤더")
    rows = t.get("rows")
    if not rows and t.get("행") is not None:
        펼침 = []
        for r in (t.get("행") or []):
            if isinstance(r, dict):
                펼침.append([("" if v is None else v) for v in r.values()])
            elif isinstance(r, list):
                펼침.append(r)
        rows = 펼침
    if not hdr:
        return []
    # 병합·칸 안 줄바꿈('26-09-29 표 재설계 P1, critic_impl §8) — MD 표는 병합을 못 나타낸다.
    # build/표꼴.py 가 조립기와 같은 규칙으로 직사각으로 펴 덮인 칸을 빈칸으로 두고, 캡션 아래에
    # '(병합 칸 있음)' 을 적는다. 칸 안 줄바꿈은 <br>(GFM 표 칸은 한 줄이어야 한다).
    머리, 몸, 병합있나 = 표꼴.md줄({**t, "header": hdr, "rows": rows or []})
    # 칸 글의 '|' 는 GFM 칸 경계라 \| 로 적는다(적대 검토 M3 — 머리·몸 칸 수가 어긋나 표가 깨졌다)
    칸 = lambda x: "<br>".join(벗김(y).replace("|", "\\|") for y in str(x).split("\n"))
    줄 = []
    if t.get("캡션") or t.get("caption"):
        줄.append(f"*{벗김(t.get('캡션') or t.get('caption'))}*")
    if 병합있나:
        줄.append("(병합 칸 있음)")
        줄.append("")
    줄.append("| " + " | ".join(칸(x) for x in 머리) + " |")
    줄.append("|" + "---|" * len(머리))
    for r in 몸:
        줄.append("| " + " | ".join(칸(x) for x in r) + " |")
    줄.append("")
    return 줄


def _표들(표):
    """절.표(또는 장.표)를 낸다 — 정본은 단일 dict 지만 모델이 리스트로 낼 때가 있다
    (assemble_full.py:_표리스트 와 같은 흡수, assemble:F2). list 면 dict 원소마다
    표를()을 붙여 낸다(dict 아닌 원소는 표를() 자체가 [] 로 거른다)."""
    if isinstance(표, list):
        out = []
        for t in 표:
            out += 표를(t)
        return out
    return 표를(표)


def _붙임_줄(붙임):
    """첨부 목록 — 문자열 하나 또는 문자열(장·항목) 리스트 둘 다 받는다.
    2026-09-26: 리스트를 못 받아('문자열이 아니면 빈 칸') '붙임'이라는 빈 줄만 나가고
    내용이 통째로 사라지던 문제 — 규정 빼고는 다 리스트로 오므로 원소별로 낸다."""
    if not 붙임:
        return []
    항목들 = 붙임 if isinstance(붙임, list) else [붙임]
    줄 = ["", "**붙임**", ""]
    for i, a in enumerate(항목들, 1):
        텍 = 벗김(a) if isinstance(a, str) else 벗김(
            (a or {}).get("text") or (a or {}).get("제목") or "")
        if 텍:
            줄.append(f"{i}. {텍}")
    줄.append("")
    return 줄


def _담당_줄(담당):
    """보도자료 담당자 — 부서·직위·이름·전화(2026-09-26 신설, 옛 코드는 아예 안 읽었다)."""
    if not 담당:
        return []
    줄 = ["", "**담당**", ""]
    for d in (담당 if isinstance(담당, list) else [담당]):
        if not isinstance(d, dict):
            continue
        조각 = [벗김(d.get(k) or "") for k in ("부서", "직위", "이름")]
        조각 = [c for c in 조각 if c]
        한줄 = " ".join(조각)
        if d.get("전화"):
            한줄 = (한줄 + f" ({벗김(d['전화'])})").strip()
        if 한줄:
            줄.append("- " + 한줄)
    줄.append("")
    return 줄


def _마디(items, 표=None, 절이름=None):
    """1p(sections/items) — 항목의 html/text 를 위계(level)만큼 들여써서 낸다."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            글 = 벗김(it.get("html") or it.get("text") or "")
            lv = _안전레벨(it.get("level"), 2)
        else:
            글 = 벗김(it)
            lv = 2
        if not 글:
            continue
        out.append("  " * max(lv - 1, 0) + "- " + 글)
    out.append("")
    if 표 and 표.get("after_heading") == 절이름:
        out += 표를(표)
    return out


# ── 규정(조문체) ────────────────────────────────────────────
#
# 번호 규칙은 assemble_regulation.py 번호매기기() 와 결이 같다(조는 문서 전체 통산,
# 항·호·목은 조마다 새로 센다) — 그 파일은 다른 작업 묶음이 동시에 고치고 있어 그대로
# import 하지 않고 이 파일 안에서 독립으로 센다. MD 는 항이 하나뿐이어도 번호를 매겨
# 읽는 이가 항이 몇 개인지 바로 보게 한다(HTML 조판의 '항 하나면 번호 생략'과는 다르다
# — 마크다운은 시각 여백이 아니라 텍스트 하나로 위계를 전달해야 해서다).
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
가나다 = "가나다라마바사아자차카타파하"

# 스키마는 "번호는 넣지 않는다(자동)"이 계약이지만, 손으로 지은 표본 문서 중 일부가
# 번호를 이미 박아 둔 채로 온다 — 그대로 두면 우리가 매긴 번호와 겹쳐 "① ② 텍스트"처럼
# 겹친다(2026-09-26 a1-04-regulation.json 표본에서 확인). 우리 번호를 붙이기 전에
# 흔한 선행 번호 표기를 한 번 벗겨 이중 표기를 막는다.
#
# 2026-09-27 고침(r3/check.json 새 결함) — 옛 `\d+[.)]` 는 자릿수 제한이 없고 뒤에
# 오는 글자도 안 가려서, '2.5일 이상'(소수점 기준값)·'2026. 9. 1. 이전'(날짜)의
# 머리 숫자까지 번호로 보고 뜯어내 조문 뜻을 소리 없이 바꿨다(규정에서 기준값·경과
# 조치 날짜가 바뀌는 것은 법적 의미가 달라지는 오류). 숫자를 1~2자리로 좁히고 바로
# 뒤가 또 숫자면(소수점 계속) 매치 자체를 접는다((?!\d)) — '2026.'은 두 자리를 넘어
# 애초에 안 걸리고, '2.5'는 뒤가 숫자라 안 걸린다. 그래도 '10. 1. 부터'(호 안의 날짜)
# 처럼 두 자리 안에 드는 우연은 남을 수 있어, **벗긴 번호가 우리가 새로 매길 번호와
# 같을 때만** 벗긴다(_번호벗김 의 기대값) — 다르면 이중 표기가 아니라 원문 그대로다.
_선행번호_RE = re.compile(
    r"^\s*(?:([①-⑳])|(\d{1,2})[.)](?!\d)|([가-하])[.)])\s*")


def _번호벗김(t, 기대값=None):
    m = _선행번호_RE.match(t)
    if not m:
        return t
    원, 숫, 가 = m.groups()
    if 원:
        발견 = CIRCLED.index(원) + 1
    elif 숫:
        발견 = int(숫)
    else:
        발견 = (가나다.index(가) + 1) if 가 in 가나다 else None
    if 기대값 is not None and 발견 != 기대값:
        return t          # 우리가 매길 번호와 다르면 우연(소수점·날짜) — 그대로 둔다
    return t[m.end():]


def _규정_조본문항여부(본문):
    """조 인덱스별로 '그 조에 항이 하나라도 따라오는가' — assemble_regulation.py
    짜기() 의 조본문항 판정과 **같은 규칙**이다(조 다음부터 다음 장·절·조 전까지 항이
    있으면 True). tomd 는 assemble_regulation 을 import 하지 않고(다른 작업 묶음이
    동시에 고치는 파일이라 — 위 머리말 주석) 이 파일 안에서 독립으로 다시 센다."""
    나온다 = {}
    조자리 = None
    for i, it in enumerate(본문):
        if not isinstance(it, dict):
            continue
        lv = it.get("level")
        if lv == "조":
            조자리 = i
            나온다[i] = False
        elif lv in ("장", "절"):
            조자리 = None
        elif lv == "항" and 조자리 is not None:
            나온다[조자리] = True
    return 나온다


def _제정이유_정규화(v):
    """제정이유(선택키)는 산문 한 단락(문자열)이 정본 모양이다 — assemble_regulation.py의
    같은 이름 함수와 같은 관용을 따른다. 모델이 배열로 낼 때도 있어 — 그때 문자열만
    받으면(옛 코드의 `isinstance(v, str)`) 조용히 빠진다 — 이어 붙여 한 단락으로 받는다."""
    if isinstance(v, list):
        return " ".join(str(x).strip() for x in v if str(x).strip())
    return v.strip() if isinstance(v, str) else ""


def _주요내용_정규화(v):
    """주요내용(선택키)은 배열(문자열 목록)이 정본 모양이다 — assemble_regulation.py의
    같은 이름 함수와 같은 관용을 따른다. 항목이 하나뿐이면 모델이 문자열 하나로 낼 때가
    흔한데 — 그대로 리스트 컴프리헨션을 돌리면(옛 코드) 글자 수만큼 가.나.다. 항목이
    생긴다 — [문자열]로 감싸 항목 하나로 받는다."""
    if isinstance(v, str):
        v = [v] if v.strip() else []
    return [str(x).strip() for x in (v or []) if str(x).strip()]


# 규정번호·부칙 호가 관행 꼴(제○○호)을 갖췄는가 — assemble_regulation.py 의 같은
# 이름 함수와 같은 관용을 따른다(그 파일 머리말과 같은 이유, '26-09-27 4차 벤치마크
# 진단). tomd 는 assemble_regulation 을 import 하지 않으므로(위 규정 섹션 머리말과
# 같은 방침) 사본을 따로 둔다.
_제호패턴 = re.compile(r"제\s*\S*?호")


def _번호꼴(v):
    v = (v or "").strip()
    if not v or _제호패턴.search(v):
        return v
    return f"제{v}호"


_일자자리표시전부 = re.compile(r"^[○\s]+$")


def _일자꼴(v):
    v = (v or "").strip()
    if v and _일자자리표시전부.match(v):
        return "○○○○. ○. ○."
    return v


def _규정_마크다운(doc):
    # ★ 여기서는 조번호꼴.맞추기 를 **부르지 않는다**('26-09-27 고침, 회귀 근거는
    # 조번호꼴.py 머리 docstring) — 이 함수의 유일한 호출부는 workspace/api.py 의
    # 내보내기()로, 사람이 편집기에서 문서를 몇 번이고 고쳐 저장한 **뒤**에도 매번
    # 다시 불린다. 여기서 맞추기를 돌리면 사람이 손으로 고친(또는 지운) 조 인용을
    # 내보낼 때마다 휴리스틱이 되돌린다 — 새문서(첫 등록) 때 이미 workspace/api.py
    # 의 새문서() 가 등록 **전에** doc 를 정정해 두므로, 등록부에는 처음부터 정정된
    # 값이 들어 있다. 여기서 또 돌 필요가 없고, 돌면 위 되돌림 위험만 남긴다.
    줄 = [f"# {벗김(doc.get('제명') or doc.get('filename') or '')}", ""]
    # 머리 기관 줄(reg12 '26-09-30 판정 B-H3) — HTML 머리(rg-org)처럼 기관명을 제명 위에 싣되, 제명이 기관명으로
    # 시작하면('○○공사 보안 점검 지침 제정(안)') 되풀이하지 않는다(assemble_regulation.머리기관겹침 과 같은 규칙).
    # tomd 는 assemble_regulation 을 import 하지 않으므로(아래 머리말) 같은 판정을 여기 한 줄로 둔다.
    _기관 = 벗김(doc.get("기관명") or "").strip()
    # 낫표 「」·『』는 떼고 견준다('「○○공사 …」 제정안' — reg12 fixup, verify.md L2)
    if _기관 and not re.sub(r"[\s「」『』]", "", 벗김(doc.get("제명") or "")).startswith(re.sub(r"[\s「」『』]", "", _기관)):
        줄 = [f"**{_기관}**", ""] + 줄
    if doc.get("규정번호"):
        # 관행 꼴로 씌운다(assemble_regulation.py build() 와 같은 자리, '26-09-27) —
        # "○○" 처럼 틀 없는 자리표시만 있으면 MD 에도 뜻 없는 한 줄이 그대로 남는다.
        줄 += [f"*{_번호꼴(벗김(doc['규정번호']))}*", ""]
    # 제정이유·주요내용(선택키, 온톨로지 document_types.regulation.구성.선택키) — 제명과
    # 제1조 사이, 조 번호 없이 산문·목록으로(assemble_regulation.py build() 와 같은 자리·
    # 같은 순서). 2026-09-26 고침(r2/check.json 추가 지시) — MD 재작성에서 두 선택키가
    # 빠져 HTML 에는 있는 입법예고 사유·요지가 MD 산출물에는 통째로 없었다. 모양 관용도
    # assemble_regulation.py 와 맞춘다(제정이유 배열은 이어 붙이고, 주요내용 문자열은
    # 항목 하나로 감싼다) — 안 맞추면 모델이 낸 배열/문자열이 통째로 빠지거나
    # (제정이유) 글자 수만큼 가.나.다. 항목이 생긴다(주요내용).
    제정이유 = _제정이유_정규화(doc.get("제정이유"))
    if 제정이유:
        줄 += ["## 제정이유", "", 벗김(제정이유), ""]
    주요내용 = _주요내용_정규화(doc.get("주요내용"))
    if 주요내용:
        줄 += ["## 주요내용", ""]
        for i, x in enumerate(주요내용):
            기호 = 가나다[i % len(가나다)]
            줄.append(f"{기호}. {벗김(x)}")
        줄.append("")
    본문 = doc.get("본문") or []
    # 조 본문이 곧 제1항이다(짜기() 규범, 위 함수 주석) — 뒤에 항이 따라오면 조 본문에
    # ①을 달고 항은 ②부터 센다. 이 판정은 **미리** 훑어야 한다: 조를 찍는 시점엔 아직
    # 그 조에 항이 있을지 모른다(2026-09-26 고침, r2/check.json #4 — 예전엔 이 선견 없이
    # 조 본문에 번호를 안 달고 항을 1부터 세어, ①로 찍힌 항이 스스로 제1항을 가리키는
    # 자기모순('① 제1항에도 불구하고…')이 났고 원문 ②도 ①로 바뀌었다).
    조본문항 = _규정_조본문항여부(본문)
    장n = 절n = 조n = 항n = 호n = 목n = 0
    항있음 = False
    조오프셋 = 0
    for idx, it in enumerate(본문):
        if not isinstance(it, dict):
            continue
        lv = it.get("level")
        제목 = 벗김(it.get("제목") or "")
        text = 벗김(it.get("text") or "")
        if lv == "장":
            # 조는 장·절 경계와 무관하게 문서 전체 통산이다(assemble_regulation.py
            # 번호매기기() 규범 — "조는 문서 전체 통산, 항 이하는 부모마다 새로") — 여기서
            # 조n 을 리셋하면 장마다 제1조가 되풀이돼 실제 조문 번호와 어긋난다.
            장n += 1
            절n = 0
            줄 += [f"## 제{장n}장 {제목}".rstrip(), ""]
        elif lv == "절":
            절n += 1
            줄 += [f"### 제{절n}절 {제목}".rstrip(), ""]
        elif lv == "조":
            조n += 1
            항n = 호n = 목n = 0
            항있음 = False
            조오프셋 = 1 if 조본문항.get(idx) else 0
            머리 = f"제{조n}조({제목})" if 제목 else f"제{조n}조"
            # 조 제목은 장·절 제목보다 한 단 깊게 — 옛 코드는 셋 다 ## 라 조가 장과
            # 같은 층으로 보였다(벤치마크 진단).
            줄 += [f"#### {머리}", ""]
            if text:
                if 조오프셋:
                    줄 += [f"{CIRCLED[0]} {_번호벗김(text, 1)}", ""]
                else:
                    줄 += [text, ""]
        elif lv == "항":
            항있음 = True
            항n += 1
            호n = 목n = 0
            if text:
                번호 = 항n + 조오프셋
                기호 = CIRCLED[번호 - 1] if 번호 <= len(CIRCLED) else f"({번호})"
                본문글 = _번호벗김(text, 번호)
                if 본문글 == text and 조오프셋:
                    # 조 본문이 ①을 차지해 항 번호가 밀린 경우(조오프셋=1), 손으로 지은
                    # 표본은 그 밀림을 모르고 항 자신의 순번(항n, 1부터)으로 이중 표기를
                    # 했을 수 있다 — 최종 번호로 안 맞으면 이 순번으로 한 번 더 본다.
                    본문글 = _번호벗김(text, 항n)
                줄.append(f"{기호} {본문글}")
        elif lv == "호":
            호n += 1
            목n = 0
            if text:
                깊 = "  " if 항있음 else ""
                줄.append(f"{깊}{호n}. {_번호벗김(text, 호n)}")
        elif lv == "목":
            목n += 1
            if text:
                깊 = "    " if 항있음 else "  "
                기호 = 가나다[목n - 1] if 목n <= len(가나다) else str(목n)
                줄.append(f"{깊}{기호}. {_번호벗김(text, 목n)}")
    줄.append("")

    부칙 = doc.get("부칙") or []
    if 부칙:
        줄 += ["## 부칙", ""]
        for b in 부칙:
            # 관행 꼴로 씌운다(assemble_regulation.py build() 와 같은 자리, '26-09-27) —
            # 호는 "제○○호" 틀로, 일자는 통짜 자리표시("○○")면 "○○○○. ○. ○." 로.
            표제 = " ".join(
                x for x in (_번호꼴(벗김(b.get("호") or "")), _일자꼴(벗김(b.get("일자") or "")))
                if x)
            if 표제:
                줄 += [f"**{표제}**", ""]
            for line in b.get("본문") or []:
                텍 = 벗김(line)
                if 텍:
                    줄.append("- " + 텍)
            줄.append("")

    # 번호 없으면 순번(ti+1)을 기본값으로 쓴다 — assemble_regulation.py 번호매기기() 와
    # 같은 관용(그 파일 318~323행). 번호 없이 그대로 보간하면 '[별표 None]'이 찍힌다
    # (assemble:F12, '26-09-27 — HEAD 의 tomd 는 별표를 아예 안 냈던 자리라 새로 생긴 결함).
    for ti, t in enumerate(doc.get("별표") or []):
        표제 = f"[별표 {t.get('번호', ti + 1)}] {벗김(t.get('제목') or '')}".strip()
        줄 += [f"## {표제}", ""]
        if t.get("표"):
            줄 += 표를(t["표"])
    return 줄


# ── 박스·도식·차트·이미지 — 풀버전(장·절)·슬라이드가 함께 쓴다 ──────────────
#
# 2026-09-26 고침(r2/check.json #5·#6) — 풀버전 MD 는 요약.정보박스·장.핵심박스·
# 장·절.박스·도식·별첨을 통째로 안 읽었고, 슬라이드 MD 는 도식 정본 배열키(converge=
# 요건·strategy=전략·relation=노드, tomd 는 process 류의 '단계'만 옛 키로 남아 있었다)와
# 조립기가 렌더 직전 **메모리에서만** 정규화하는 레이아웃·도식타입·큰숫자 키 별칭을
# 몰랐다(등록부에는 별칭·영문키가 그대로 남는다 — 실측). assemble_slides.py 는 다른
# 작업 묶음이 동시에 고치고 있어 import 하지 않고(위 규정 섹션과 같은 방침) 필요한
# 지도만 이 파일 안에 독립으로 옮겨 쓴다.
#
# 2026-09-27 고침(r10 사후검토 발견 medium) — assemble_slides.레이아웃별칭 이 3차
# 측정(EXAONE '정리'·'본페이지' 등)에 맞춰 한국어 관행어 별칭을 늘렸는데(부분일치 '도식'
# 포함) 이 사본은 그대로였다 — 그 사이 조립기(HTML·PPTX)는 그려지는 장을 MD 는 헤드
# 한 줄만 남기고 통째로 떨궜다(예: '본사 모으듯이 도식' → 어느 lo 도 안 걸려 도식 자리
# 244행 elif 사슬을 다 건너뛴다). assemble_slides.레이아웃별칭·_레이아웃부분일치 와
# **글자 그대로 같은 지도**로 다시 맞춘다 — 늘어날 때마다 또 벌어지지 않도록 tomd_슬라이드
# 시험(test/r10_asm10.py)이 이 지도가 그쪽 사본을 담고 있는지 대조한다.
_레이아웃별칭 = {
    "본체": "본문", "본론": "본문", "본페이지": "본문", "내용": "본문",
    "compare": "비교", "two-cols": "비교", "comparison": "비교", "비교표": "비교", "대조": "비교",
    "kpi": "큰숫자", "KPI": "큰숫자", "bignumber": "큰숫자", "fact": "큰숫자", "statement": "큰숫자",
    "수치": "큰숫자", "숫자": "큰숫자",
    "matrix": "매트릭스", "2x2": "매트릭스", "quadrant": "매트릭스",
    "quote": "인용", "testimonial": "인용",
    "timeline": "타임라인", "roadmap": "타임라인", "일정": "타임라인", "로드맵": "타임라인",
    "chart": "도식",
    "정리": "마무리", "요약": "마무리", "결론": "마무리", "맺음": "마무리",
    "목차": "어젠다", "순서": "어젠다",
}
# 이름에 '도식'이 그대로 들어 있으면(예: '본사 모으듯이 도식') 별칭표를 안 거쳐도 도식으로
# 본다 — assemble_slides._레이아웃부분일치 와 같은 지도(그쪽 머리말과 같은 이유).
_레이아웃부분일치 = (("도식", "도식"),)
_도식유형별칭 = {"bar_chart": "bar", "column": "bar", "line_chart": "line",
              "pie": "donut", "doughnut": "donut"}
# 도식 타입별 정본 배열키(assemble_slides._도식정본배열키 와 같은 지도, _도식자줄 안에서
# 타입별로 그대로 풀어 쓴다) — process/cycle=단계, converge=요건, relation=노드,
# strategy=전략. 영문(steps/nodes) 로 남은 등록부도 받는다.
_도식라벨키후보 = ("라벨", "label", "name", "이름", "제목", "text", "title")


def _도식원소라벨(x):
    if isinstance(x, dict):
        for k in _도식라벨키후보:
            if x.get(k):
                return 벗김(str(x[k]))
        return ""
    return 벗김(str(x)) if x is not None else ""


# 2026-09-27 고침(r3/check.json — still_partly #6·new_defects) — 2차는 이 지도의
# **절반만**(레이아웃·차트타입 별칭, steps/nodes, 지표 배열 키 별칭) 옮겼다. 조립기가
# 렌더 직전 살려 그리는 **타입↔배열키 정합**(예: {type:converge,단계:[…],시행:'',
# 결과:''} 을 process 로 강등해 그리는 것)과 strategies·layers 별칭·단계 원소의 '주체'
# 는 안 옮겨서, 화면엔 라벨이 그려지는데 MD 는 헤드 한 줄만 남았다. assemble_slides.py
# 는 다른 작업 묶음이 동시에 고치고 있어 import 하지 않고(위 머리말 주석) 이번엔
# `_도식정규화` **전체**를 옮긴다 — assemble_slides._도식정규화 와 같은 순서·같은 판단.
def _도식정규화(fg):
    if not isinstance(fg, dict):
        return fg
    fg = dict(fg)
    t = fg.get("type")

    def _라벨(x):
        return (x.get("label") or x.get("라벨") or x.get("이름") or "") if isinstance(x, dict) else str(x or "")

    def _문자열들(arr):
        return [_라벨(x) for x in arr] if isinstance(arr, list) else []

    def _주체들(arr):   # {label,desc} → {라벨, 주체(부제)}
        out = []
        for x in (arr if isinstance(arr, list) else []):
            if isinstance(x, dict):
                d = {"라벨": _라벨(x)}
                sub = x.get("desc") or x.get("주체")
                if sub:
                    d["주체"] = sub
                out.append(d)
            else:
                out.append({"라벨": str(x or "")})
        return out

    if t in ("process", "cycle") and fg.get("steps") is not None and "단계" not in fg:
        fg["단계"] = _주체들(fg.get("steps"))
    elif t == "converge" and fg.get("nodes") is not None and "요건" not in fg:
        fg["요건"] = _문자열들(fg.get("nodes"))
        if fg.get("center") is not None and not fg.get("시행"):
            fg["시행"] = _라벨(fg.get("center"))
        if fg.get("outputs") is not None and not fg.get("결과"):
            fg["결과"] = " · ".join(_문자열들(fg.get("outputs")))
    elif t == "strategy" and fg.get("strategies") is not None and "전략" not in fg:
        fg["전략"] = fg.get("strategies")
    elif t == "relation" and fg.get("nodes") is not None and "노드" not in fg:
        fg["노드"] = _주체들(fg.get("nodes"))
        if fg.get("edges") and "연결" not in fg:
            fg["연결"] = fg.get("edges")
    elif t == "stack" and fg.get("layers") is not None:
        # svgfig 의 stack 은 쌓은 막대 차트다. EXAONE 는 '계층 구조'로 오용하니 세로
        # 절차로 강등해 라벨을 살린다(조립기와 같은 판단, 빈 막대보다 낫다).
        fg["type"] = "process"
        fg["단계"] = _주체들(fg.get("layers"))

    # ---- 타입↔배열키 정합: 데이터가 진실이다(assemble_slides._도식정규화 와 같은 규칙) ----
    _정본키 = {"process": "단계", "cycle": "단계", "converge": "요건",
              "strategy": "전략", "relation": "노드"}
    _키의타입 = {"단계": "process", "요건": "converge", "전략": "strategy", "노드": "relation"}
    cur_t = fg.get("type")
    정본키 = _정본키.get(cur_t)
    if 정본키 and not fg.get(정본키):
        for 다른키, 다른타입 in _키의타입.items():
            if 다른키 != 정본키 and fg.get(다른키) and 다른타입 != cur_t:
                fg["type"] = cur_t = 다른타입
                break
    if cur_t == "converge" and fg.get("요건") and not fg.get("시행") and not fg.get("결과"):
        fg["단계"] = fg.pop("요건")
        fg["type"] = "process"

    _라벨키후보 = ("label", "name", "이름", "제목", "text", "title")
    for v in fg.values():
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and not it.get("라벨"):
                    for k in _라벨키후보:
                        if it.get(k):
                            it["라벨"] = it[k]
                            break
    return fg


# assemble_slides._차트키별칭·_계열원소별칭·_항목원소별칭·_수형·_차트정규화 와 같은
# 사본('26-09-27 신설) — 위 _도식정규화 와 같은 이유(assemble_slides.py 는 import 하지
# 않는다, 위 주석)로 여기서도 그대로 옮긴다. 안 옮기면 영문 키(labels/series/data)로
# 낸 차트가 화면(HTML)엔 정규화돼 그려지는데 MD 는 원래 키를 몰라 빈 줄만 남는다
# (review34/chart_adv.py 'eng-keys' 실측: md=''). svgfig.차트유형 은 상수라 값만
# 그대로 옮긴다(모듈을 새로 import 하지 않는다).
_차트유형 = ("line", "bar", "hbar", "donut")
_차트키별칭 = {"series": "계열", "data": "계열", "categories": "시점", "labels": "시점",
           "x": "시점", "xAxis": "시점", "items": "항목"}
_계열원소별칭 = {"name": "이름", "values": "값", "data": "값", "value": "값", "label": "이름"}
_항목원소별칭 = {"name": "이름", "value": "값", "label": "이름"}
_수형패턴_온전 = re.compile(r'^[+-]?\d+(?:\.\d+)?$')
_수형패턴_단위 = re.compile(r'^([+-]?\d+(?:\.\d+)?)\s*([^\d\s,]{1,3})$')
_배수사 = ("천", "만", "억", "조")


def _수형(v):
    if isinstance(v, bool) or not isinstance(v, str):
        return v
    s = v.strip().replace(",", "")
    if not s:
        return v
    if _수형패턴_온전.match(s):
        return float(s) if "." in s else int(s)
    m = _수형패턴_단위.match(s)
    if m:
        단위 = m.group(2)
        if any(배수 in 단위 for 배수 in _배수사):
            return v
        n = m.group(1)
        return float(n) if "." in n else int(n)
    return v


def _차트정규화(fg):
    if not isinstance(fg, dict) or fg.get("type") not in _차트유형:
        return fg
    fg = dict(fg)
    for 영, 한 in _차트키별칭.items():
        if 영 in fg and 한 not in fg:
            fg[한] = fg.pop(영)
    if fg.get("type") == "donut":
        항목 = fg.get("항목")
        if isinstance(항목, list):
            새항목 = []
            for it in 항목:
                if isinstance(it, dict):
                    it = dict(it)
                    for 영, 한 in _항목원소별칭.items():
                        if 영 in it and 한 not in it:
                            it[한] = it.pop(영)
                    if "값" in it:
                        it["값"] = _수형(it["값"])
                    새항목.append(it)
                elif isinstance(it, list) and len(it) >= 2:
                    새항목.append([it[0], _수형(it[1])])
                else:
                    새항목.append(it)
            fg["항목"] = 새항목
    else:
        계열 = fg.get("계열")
        if isinstance(계열, list):
            새계열 = []
            for s in 계열:
                if isinstance(s, dict):
                    s = dict(s)
                    for 영, 한 in _계열원소별칭.items():
                        if 영 in s and 한 not in s:
                            s[한] = s.pop(영)
                    if isinstance(s.get("값"), list):
                        s["값"] = [_수형(v) for v in s["값"]]
                    새계열.append(s)
                else:
                    새계열.append(s)
            fg["계열"] = 새계열
    return fg


def _큰숫자정규화_목록(지표):
    """assemble_slides._큰숫자정규화 와 같은 사본 — 지표 원소의 영문 키(value/unit/
    label/name/delta/change) 별칭과, 단위 자리에 지표 이름 문구가 통째로 들어간 흔한
    이탈(값 옆에 그대로 붙어 잘리는 사고)을 바로잡는다. 원소가 dict 가 아니면(문자열
    지표, '79점 만족도' 류) 값 하나짜리로 받는다 — 2026-09-27 고침(r3/check.json,
    2차가 이 정규화를 안 옮겨 MD 가 '## 헤드' 한 줄만 남기던 결함)."""
    out = []
    for m in (지표 if isinstance(지표, list) else []):
        if not isinstance(m, dict):
            out.append({"값": str(m)} if m is not None else {})
            continue
        m = dict(m)
        for 영, 한 in (("value", "값"), ("unit", "단위"), ("label", "라벨"), ("name", "라벨"),
                     ("delta", "변화"), ("change", "변화")):
            if 영 in m and 한 not in m:
                m[한] = m.pop(영)
        라벨 = str(m.get("라벨") or "").strip()
        단위 = str(m.get("단위") or "").strip()
        if 단위:
            문구다 = len(단위) > 4 or any(ch.isspace() for ch in 단위)
            if not 라벨:
                m["라벨"] = 단위
                m["단위"] = ""
            elif 문구다:
                m["단위"] = ""
        out.append(m)
    return out


def _주체줄(st):
    """process 단계·relation 노드의 부제('주체') — svgfig.js 가 '* …' 로 그린다."""
    if isinstance(st, dict) and st.get("주체"):
        return [f"  * {벗김(str(st['주체']))}"]
    return []


def _도식자줄(fg):
    """도식·차트 스펙 하나 → MD 글줄. svgfig.js 가 그리는 자리(정본 배열·시행/결과·
    목표/과제·연결 라벨·차트 계열/항목)만 보수적으로 그대로 옮긴다(생성 없음). 타입↔
    배열키 정합·영문키 별칭은 먼저 `_도식정규화`(조립기와 같은 사본)로, 차트 4종의
    영문 키·숫자 문자열은 `_차트정규화`(같은 사본)로 바로잡는다 — 안 그러면 화면(HTML)
    은 정규화돼 그려지는데 MD 만 원래 키를 몰라 빈 줄로 남는다(review34/chart_adv.py
    'eng-keys' 실측, '26-09-27)."""
    if not isinstance(fg, dict):
        return []
    fg = _차트정규화(_도식정규화(dict(fg)))
    t = fg.get("type")
    t = _도식유형별칭.get(t, t)
    out = []
    if fg.get("캡션"):
        out += [f"*{벗김(fg['캡션'])}*", ""]
    if t == "strategy":
        # 목표·과제도 {라벨, 색} 객체일 수 있다(편집기 색 역할·모델 원고) — 글만 옮긴다(svgfig lab() 과 같다,
        # 적대 검토 M3 '26-09-29: 과제 객체가 "{'라벨': …}" 로 찍혔다)
        목표 = _도식원소라벨(fg.get("목표"))
        if 목표:
            out.append("- " + 목표)
        for col in (fg.get("전략") or []):
            if not isinstance(col, dict):
                continue
            제목 = _도식원소라벨(col)
            if 제목:
                out.append("  - " + 제목)
            for tk in (col.get("과제") or []):
                줄자 = _도식원소라벨(tk)
                if 줄자:
                    out.append("    - " + 줄자)
    elif t == "converge":
        요건 = fg.get("요건")
        if not isinstance(요건, list):
            요건 = fg.get("nodes") if isinstance(fg.get("nodes"), list) else []
        for r in 요건:
            줄자 = _도식원소라벨(r) if isinstance(r, dict) else 벗김(str(r))
            if 줄자:
                out.append("- " + 줄자)
        시행 = fg.get("시행") or _도식원소라벨(fg.get("center"))
        if 시행:
            out.append(f"  → {벗김(str(시행))}")
        결과 = fg.get("결과")
        if not 결과 and isinstance(fg.get("outputs"), list):
            결과 = " · ".join(_도식원소라벨(x) if isinstance(x, dict) else 벗김(str(x))
                            for x in fg["outputs"])
        if 결과:
            out.append(f"  → {벗김(str(결과))}")
    elif t == "relation":
        노드 = fg.get("노드")
        if not isinstance(노드, list):
            노드 = fg.get("nodes") if isinstance(fg.get("nodes"), list) else []
        for nd in 노드:
            줄자 = _도식원소라벨(nd) or (nd if isinstance(nd, str) else "")
            if 줄자:
                out.append("- " + 벗김(str(줄자)))
                out += _주체줄(nd)
        for e in (fg.get("연결") or fg.get("edges") or []):
            if not isinstance(e, dict):
                continue
            줄자 = 벗김(e.get("라벨") or e.get("label") or "")
            if 줄자:
                out.append(f"  ({줄자})")
    elif t in ("process", "cycle"):
        단계 = fg.get("단계")
        if not isinstance(단계, list):
            단계 = fg.get("steps") if isinstance(fg.get("steps"), list) else []
        n = len(단계)
        for i, st in enumerate(단계):
            줄자 = _도식원소라벨(st)
            if 줄자:
                out.append("- " + 줄자)
                out += _주체줄(st)
                # svgfig.js 는 '전이' 를 단계 사이 화살표 라벨로 그린다(마지막 단계
                # 다음엔 화살표가 없다) — 2026-09-27 고침(r3/check.json, "1단계 '26.10"·
                # "급속 8기" 같은 전이 글자가 MD 에서 통째로 빠졌다).
                if i < n - 1 and isinstance(st, dict) and st.get("전이"):
                    out.append(f"  → {벗김(str(st['전이']))}")
    elif t == "compare":
        # 비교판('26-09-29 격자 도식 P2) — 화면은 [현행 | ⇨ | 개선] 두 판의 표다. MD 는 두 판을 차례로
        # 적는다(머리 없으면 svgfig.js 와 같은 기본 낱말). 두 판을 한 줄씩 짝지은 표로 적지 않는 이유:
        # 두 판의 항목 수가 달라도 되고, 줄끼리 1:1 대응을 뜻하지 않는다
        머리 = fg.get("머리") if isinstance(fg.get("머리"), list) else []
        for k, (키, 기본) in enumerate((("전", "현행"), ("후", "개선"))):
            제 = _도식원소라벨(머리[k]) if k < len(머리) else ""
            out.append(f"- **{제 or 기본}**")
            for x in (fg.get(키) if isinstance(fg.get(키), list) else []):
                줄자 = _도식원소라벨(x)
                if 줄자:
                    out.append("  - " + 줄자)
    elif t == "donut":
        for it in (fg.get("항목") or []):
            if isinstance(it, (list, tuple)) and len(it) >= 2:
                이름, 값 = it[0], it[1]
            elif isinstance(it, dict):
                이름, 값 = it.get("이름"), it.get("값")
            else:
                continue
            이름 = 벗김(str(이름 or ""))
            if 이름:
                out.append(f"- {이름}: {값}" if 값 not in (None, "") else f"- {이름}")
        if fg.get("가운데"):
            out.append(f"*{벗김(str(fg['가운데']))}*")
    elif t in ("bar", "line", "hbar"):
        시점 = fg.get("시점") or []
        단위 = 벗김(str(fg.get("단위") or ""))
        for s in (fg.get("계열") or []):
            if not isinstance(s, dict):
                continue
            이름 = 벗김(s.get("이름") or "")
            값들 = s.get("값") or []
            # 빈 값(None·'')은 화면처럼 점을 두지 않는다 — '2월:None' 이 찍히던 것(적대 검토 M3)
            쌍 = [f"{벗김(str(시점[i])) if i < len(시점) else i + 1}:{v}"
                 for i, v in enumerate(값들) if v is not None and v != ""]
            줄자 = ((이름 + " — ") if 이름 else "") + ", ".join(쌍) + (f" {단위}" if 단위 and 쌍 else "")
            if 줄자.strip():
                out.append("- " + 줄자)
    elif t == "stack":
        # 구성띠(세트마다 [이름, 값]) — 갈래가 없어 캡션만 남고 값이 통째로 빠졌다('26-09-29 fixup,
        # 40사례 MD 보존 실측: stack 2 의 세트 이름·조각 값 0/8). 세트 한 줄에 조각을 잇는다.
        단위 = 벗김(str(fg.get("단위") or ""))
        for st in (fg.get("세트") or []):
            if not isinstance(st, dict):
                continue
            조각 = []
            for it in (st.get("항목") or []):
                if isinstance(it, (list, tuple)) and len(it) >= 2:
                    이름, 값 = it[0], it[1]
                elif isinstance(it, dict):
                    이름, 값 = it.get("이름"), it.get("값")
                else:
                    continue
                이름 = 벗김(str(이름 or ""))
                if 이름:
                    조각.append(f"{이름} {값}" if 값 not in (None, "") else 이름)
            세트이름 = 벗김(str(st.get("이름") or ""))
            줄자 = ((세트이름 + " — ") if 세트이름 else "") + ", ".join(조각) + (f" {단위}" if 단위 and 조각 else "")
            if 줄자.strip():
                out.append("- " + 줄자)
    if fg.get("함의"):
        out += ["", f"*{벗김(str(fg['함의']))}*"]
    out.append("")
    return out


def _박스줄(bx, flat=False):
    """꾸밈형 글상자(shared.박스_카탈로그) — 종류로 시각 서식만 갈릴 뿐 내용은 캡션·항목·
    각주다(assemble_full.box_html 과 같은 자리). flat=True 는 장 핵심박스처럼 문자열
    배열이 바로 항목인 경우(캡션·각주 없음)."""
    if not isinstance(bx, dict):
        return []
    out = []
    if not flat and bx.get("캡션"):
        out.append(f"*< {벗김(bx['캡션'])} >*")
    for it in (bx.get("항목") or []):
        부속 = isinstance(it, dict) and it.get("부속")
        텍 = 벗김(str((it or {}).get("text") if isinstance(it, dict) else it or ""))
        if 텍:
            out.append(("  " if 부속 else "") + "- " + 텍)
    for fn in (([] if flat else bx.get("각주")) or []):
        텍 = 벗김(str(fn))
        if 텍:
            out.append(f"  *({텍})*")
    out.append("")
    return out


def _핵심박스줄(items):
    out = [f"- {벗김(str(it))}" for it in (items or []) if 벗김(str(it))]
    if out:
        out.append("")
    return out


# 그림 링크(P3 '26-09-30) — api 내보내기가 조립된 HTML 에 **실린** 그림만 {id(스펙): 링크}로 준다. None 이면 옛 방식
# (캡션·함의만 글로). 주어졌는데 그 그림이 없으면 캡션째 뺀다 — 없는 그림의 캡션만 남지 않게(주관 판정).
_그림링크 = None


def _이미지줄(img, 캡션아래=False):
    """이미지(삽화·첨부 크롭) — imageasset.render 와 같은 필드(캡션·함의, 폴백 설명). 링크가 있으면
    ![대체 글](링크) 로 그림도 싣는다(캡션 위 · 그림 · ※함의 — HTML 과 같은 차례). 보도자료 붙임 사진은 설명을
    사진 아래에(캡션아래). 옛 슬라이드 '이미지' 목록은 조립기처럼 첫 원소만 본다."""
    if isinstance(img, list):
        img = img[0] if img and isinstance(img[0], dict) else None
    if not isinstance(img, dict):
        return []
    링크 = _그림링크.get(id(img)) if isinstance(_그림링크, dict) else None
    if isinstance(_그림링크, dict) and not 링크:
        return []                  # 실리지 않은 그림 — 캡션만 남기지 않는다
    out = []
    if img.get("캡션") and not 캡션아래:
        out.append(f"*{벗김(img['캡션'])}*")
    if 링크:
        대체 = 벗김(str(img.get("대체텍스트") or img.get("캡션") or "그림")).replace("[", "(").replace("]", ")")
        out.append(f"![{대체}]({링크})")
    if img.get("캡션") and 캡션아래:
        out.append(벗김(img["캡션"]))
    노트 = img.get("함의") or img.get("설명")
    if 노트:
        out.append(벗김(str(노트)))
    if out and img.get("출처") == "생성":
        out.append("(AI 생성물)")    # 렌더의 'AI 생성물' 배지와 같다 — MD 에서 표기가 빠졌었다('26-09-30)
    if out:
        out.append("")
    return out


# ── 풀버전 보고서 ────────────────────────────────────────────


def _풀버전_마크다운(doc):
    """표지·요약·장/절/항목 구조를 그대로 따라간다 — 옛 코드는 doc["sections"]·doc["본문"]만
    보고 doc["장"]·doc["요약"]을 몰라 표지 제목 한 줄만 나갔다(벤치마크 진단, 47바이트)."""
    표지 = doc.get("표지") or {}
    줄 = [f"# {벗김(표지.get('제목') or doc.get('filename') or '')}", ""]
    if 표지.get("부제"):
        줄 += [f"*{벗김(표지['부제'])}*", ""]

    요약 = doc.get("요약") or {}
    블록들 = 요약.get("블록") or []
    if 블록들:
        줄 += ["## 요약", ""]
        for b in 블록들:
            if b.get("제목"):
                줄 += [f"### {벗김(b['제목'])}", ""]
            for it in b.get("항목") or []:
                텍 = 벗김(it.get("text") or "")
                if 텍:
                    줄.append("- " + 텍)
                for sub in it.get("세부") or []:
                    sub텍 = 벗김(sub)
                    if sub텍:
                        줄.append("  - " + sub텍)
            줄.append("")
    # 정보박스(일정·예산·협조사항) — 결재 판단에 바로 쓰이는 자리라 MD 에서도 빠지면 안
    # 된다(2026-09-26 고침, r2/check.json #5). assemble_full.py 와 같은 세 칸·같은 순서.
    정보박스 = 요약.get("정보박스") if isinstance(요약.get("정보박스"), dict) else {}
    if 정보박스:
        for k in ("일정", "예산", "협조사항"):
            v = 벗김(정보박스.get(k) or "")
            if v:
                줄.append(f"**{k}**: {v}")
        줄.append("")

    for ch in doc.get("장") or []:
        if ch.get("제목"):
            줄 += [f"## {벗김(ch['제목'])}", ""]
        # 장 시작 두괄(핵심박스)·장 전용 박스·도식 — 절보다 먼저(HTML 조판과 같은 순서,
        # r2/check.json #5).
        줄 += _핵심박스줄(ch.get("핵심박스"))
        for bx in (ch.get("박스") or []):
            줄 += _박스줄(bx)
        for fg in (ch.get("도식") or []):
            줄 += _도식자줄(fg)
        for sec in ch.get("절") or []:
            if sec.get("제목"):
                줄 += [f"### {벗김(sec['제목'])}", ""]
            for it in sec.get("항목") or []:
                텍 = 벗김(it.get("text") or "") if isinstance(it, dict) else 벗김(it)
                if not 텍:
                    continue
                lv = _안전레벨(it.get("level"), 2) if isinstance(it, dict) else 2
                줄.append("  " * max(lv - 1, 0) + "- " + 텍)
            줄.append("")
            for bx in (sec.get("박스") or []):
                줄 += _박스줄(bx)
            for fg in (sec.get("도식") or []):
                줄 += _도식자줄(fg)
            for img in (sec.get("이미지") or []):
                줄 += _이미지줄(img)
            if sec.get("표"):
                줄.append("")
                줄 += _표들(sec["표"])
        if ch.get("표"):
            줄.append("")
            줄 += _표들(ch["표"])
    return 줄


# ── 발표 슬라이드 ────────────────────────────────────────────


def _항목텍(it):
    if isinstance(it, str):
        return 벗김(it), 2
    if isinstance(it, dict):
        return 벗김(it.get("text") or it.get("텍스트") or ""), _안전레벨(it.get("level"), 2)
    return "", 2


def _슬라이드_항목들(items, 밑수준=2):
    out = []
    for it in items or []:
        텍, lv = _항목텍(it)
        if 텍:
            out.append("  " * max(lv - 밑수준, 0) + "- " + 텍)
    return out


def _슬라이드_한장(s):
    """레이아웃마다 실제로 담는 자리(항목·표·지표·픽토그램·좌우·사분면·단계…)가 달라
    각 자리를 그대로 읽는다 — 옛 코드는 이 구조를 아예 몰라 슬라이드 배열 자체를
    안 읽었다(벤치마크 진단, 44바이트)."""
    out = []
    # 조립기(assemble_slides._레이아웃정규화)가 렌더 직전 메모리에서만 바로잡는 레이아웃
    # 유의어(kpi→큰숫자·compare→비교 등)를 등록부는 그대로 들고 있을 수 있다(2026-09-26
    # 고침, r2/check.json #6 실측) — tomd 도 같은 지도로 스스로 정규화한다.
    원래레이아웃 = s.get("레이아웃")
    lo = _레이아웃별칭.get(원래레이아웃, 원래레이아웃)
    if lo == 원래레이아웃 and isinstance(원래레이아웃, str):
        # 별칭표에 정확히 없으면 부분일치(assemble_slides._레이아웃부분일치 와 같은 지도) —
        # '본사 모으듯이 도식'처럼 모델이 설명을 덧붙인 문장은 정확 일치로는 안 잡힌다.
        for 조각, 대상 in _레이아웃부분일치:
            if 조각 in 원래레이아웃:
                lo = 대상
                break
    if lo == "간지":
        줄제 = 벗김(s.get("제목") or "")
        out += [f"## {벗김(str(s.get('번호') or ''))} {줄제}".strip(), ""]
        return out
    if lo == "어젠다":
        out += ["## 목차", ""]
        # 어젠다는 제목이 늘 '목차' 고정이지만 헤드메시지(결정사항 전진배치 등)를 조용히
        # 버리면 안 된다 — HTML/PDF/PPTX(assemble_slides.build())와 같은 자리(목차 title
        # 아래 한 줄)로 낸다(cli s6, '26-09-27).
        어젠다헤드 = 벗김(s.get("헤드메시지") or "")
        if 어젠다헤드:
            out += [f"*{어젠다헤드}*", ""]
        out += _슬라이드_항목들(s.get("항목"), 밑수준=1)
        out.append("")
        return out

    헤드 = 벗김(s.get("헤드메시지") or "")
    out += [f"## {헤드}" if 헤드 else "## (슬라이드)", ""]

    if lo == "인용":
        if s.get("인용문"):
            out += [f"> {벗김(s['인용문'])}", ""]
        if s.get("출처"):
            out += [f"— {벗김(s['출처'])}", ""]
        return out

    if lo == "표" and s.get("표"):
        out += 표를(s["표"])
    elif lo == "픽토그램":
        for it in s.get("픽토그램") or []:
            if not isinstance(it, dict):
                continue
            라벨 = 벗김(it.get("라벨") or "")
            설명 = 벗김(it.get("설명") or "")
            줄자 = 라벨 + (f" — {설명}" if 설명 else "")
            if 줄자:
                out.append("- " + 줄자)
        out.append("")
    elif lo == "큰숫자":
        지표 = s.get("지표")
        if not isinstance(지표, list):
            # 지표 배열 키 별칭(assemble_slides._큰숫자정규화 와 같은 지도, r2/check.json #6)
            # — 소형 모델이 지표 배열을 레이아웃 이름과 같은 '큰숫자' 키 등으로 낸다.
            for k in ("큰숫자", "지표들", "수치", "카드", "kpi", "KPI", "metrics", "items"):
                v = s.get(k)
                if isinstance(v, list) and v:
                    지표 = v
                    break
        for m in _큰숫자정규화_목록(지표):
            값 = str(m.get("값") or "")
            단위 = str(m.get("단위") or "")
            라벨 = 벗김(m.get("라벨") or "")
            변화 = str(m.get("변화") or "")
            줄자 = f"{값}{단위} — {라벨}".strip(" —")
            if 변화:
                줄자 += f" ({변화})"
            if 줄자:
                out.append("- " + 줄자)
        out.append("")
    elif lo == "비교":
        for key in ("좌", "우"):
            col = s.get(key)
            col = col if isinstance(col, dict) else {}
            if col.get("제목"):
                out += [f"### {벗김(col['제목'])}", ""]
            out += _슬라이드_항목들(col.get("항목"), 밑수준=1)
            out.append("")
        if s.get("결론"):
            out += [f"**{벗김(str(s['결론']))}**", ""]
    elif lo == "매트릭스":
        축 = s.get("축") if isinstance(s.get("축"), dict) else {}
        가로 = 축.get("가로") if isinstance(축.get("가로"), list) else []
        세로 = 축.get("세로") if isinstance(축.get("세로"), list) else []
        if 가로 or 세로:
            out += [f"*가로: {' / '.join(벗김(str(x)) for x in 가로)}"
                    f" · 세로: {' / '.join(벗김(str(x)) for x in 세로)}*", ""]
        for q in s.get("사분면") or []:
            q = q if isinstance(q, dict) else {}
            if q.get("제목"):
                out += [f"### {벗김(q['제목'])}", ""]
            out += _슬라이드_항목들(q.get("항목"), 밑수준=1)
            out.append("")
    elif lo == "타임라인":
        for st in s.get("단계") or []:
            st = st if isinstance(st, dict) else {}
            시점 = 벗김(st.get("시점") or "")
            라벨 = 벗김(st.get("라벨") or "")
            줄자 = " ".join(x for x in (시점, 라벨) if x)
            if 줄자:
                out.append("- " + 줄자)
            if st.get("설명"):
                out.append("  - " + 벗김(str(st["설명"])))
        out.append("")
    elif lo == "도식":
        # 정본 배열키(process/cycle=단계·converge=요건·relation=노드·strategy=전략)로
        # 라벨을 뽑는다 — 옛 자리('기둥'·'분기'는 svgfig.js 에 아예 없는 키였고, 정본
        # 키 셋은 빠져 있었다, 2026-09-26 고침, r2/check.json #6). 차트(bar·line·hbar·
        # donut) 계열·항목도 같은 함수로 낸다.
        out += _도식자줄(s.get("도식"))
    elif lo == "이미지":
        out += _이미지줄(s.get("이미지"))
    if s.get("항목") and lo not in ("비교", "매트릭스", "타임라인", "어젠다"):
        out += _슬라이드_항목들(s.get("항목"), 밑수준=1)
        out.append("")
    elif lo == "마무리" and not s.get("항목") and s.get("문구"):
        out += ["- " + 벗김(str(s["문구"])), ""]
    if s.get("출처"):
        out += [f"*출처: {벗김(s['출처'])}*", ""]
    return out


def _슬라이드_마크다운(doc):
    표지 = doc.get("표지") or {}
    줄 = [f"# {벗김(표지.get('제목') or doc.get('filename') or '')}", ""]
    if 표지.get("부제"):
        줄 += [f"*{벗김(표지['부제'])}*", ""]
    if 표지.get("발표정보"):
        줄 += [벗김(표지["발표정보"]), ""]
    for s in doc.get("슬라이드") or []:
        if isinstance(s, dict):
            줄 += _슬라이드_한장(s)
    return 줄


# ── 슬라이드 판형 v2(부품 트리) ─────────────────────────────────
#
# '26-09-28 적대 검토(회귀 ③): 옛 갈래(_슬라이드_마크다운)는 표지·슬라이드만 읽어 v2 문서에서 제목 한 줄
# 짜리 빈 MD 를 내고 ok 를 돌려줬다. v2 는 최상위 제목·발표정보 + 장[] 이다. 화면에 찍히는 글만 싣는다 —
# 노트(발표자 노트·작성 메모)·산출 식은 화면 밖이라 뺀다(출처는 장 아래 한 줄로 싣는다).
_V2열거키 = {"부품", "폭", "변형", "역할", "상태", "아이콘", "종류", "방향", "판정", "정렬", "척도", "전후종류",
          "열정렬", "강조행", "강조", "제목모양", "바탕", "유형", "밀도"}


def _v2글(v):
    if isinstance(v, list):
        return 벗김("".join(str(r.get("t", "")) for r in v if isinstance(r, dict)))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:,}" if float(v).is_integer() else str(v)
    return 벗김(v) if isinstance(v, str) else ""


def _v2모든글(node, out):
    """부품 안 화면 글을 차례대로(열거·배치 키 제외)."""
    if isinstance(node, str):
        if node.strip():
            out.append(벗김(node))
    elif isinstance(node, list):
        if node and all(isinstance(r, dict) and "t" in r for r in node):
            out.append(_v2글(node))
        else:
            for x in node:
                _v2모든글(x, out)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in _V2열거키 or str(k).startswith("_"):
                continue
            _v2모든글(v, out)


def _v2부품줄(c):
    n = c.get("부품")
    if n == "세로묶음":
        줄 = []
        for x in c.get("칸") or []:
            if isinstance(x, dict):
                줄 += _v2부품줄(x)
        return 줄
    if n == "표":
        머리 = [_v2글(x) for x in c.get("머리행") or []]
        행 = [[_v2글(셀.get("글")) if isinstance(셀, dict) else _v2글(셀) for 셀 in r]
             for r in c.get("행") or [] if isinstance(r, list)]
        줄 = [""] + 표를({"header": 머리, "rows": 행})
        if c.get("요지"):
            줄 += [f"*{_v2글(c['요지'])}*", ""]
        return 줄
    if n == "지표타일":
        맥 = (c.get("맥락") or {}).get("글") if isinstance(c.get("맥락"), dict) else ""
        return [f"- **{_v2글(c.get('라벨'))}** {_v2글(c.get('값'))}{_v2글(c.get('단위'))}"
                + (f" ({벗김(맥)})" if 맥 else "")]
    if n in ("가로막대", "선차트", "점눈금", "구성띠"):
        줄 = [f"- **{_v2글(c.get('제목'))}**"]
        단위 = _v2글(c.get("단위"))
        if n == "가로막대":
            줄 += [f"  - {_v2글(r.get('라벨'))}: {_v2글(r.get('표시')) or (_v2글(r.get('값')) + 단위)}"
                  for r in c.get("행") or [] if isinstance(r, dict)]
        elif n == "선차트":
            축 = [_v2글(x) for x in c.get("가로축") or []]
            for s in c.get("계열") or []:
                if isinstance(s, dict):
                    쌍 = [f"{a} {_v2글(v)}" for a, v in zip(축, s.get("값") or []) if v is not None]
                    줄.append(f"  - {_v2글(s.get('이름'))}: " + " · ".join(쌍))
        elif n == "점눈금":
            줄 += [f"  - {_v2글(x.get('라벨'))}: {_v2글(x.get('값'))}{단위}" for x in c.get("점") or [] if isinstance(x, dict)]
        else:
            줄 += [f"  - {_v2글(x.get('라벨'))}: {_v2글(x.get('값'))}" for x in c.get("조각") or [] if isinstance(x, dict)]
        if c.get("요지"):
            줄.append(f"  - {_v2글(c['요지'])}")
        return 줄
    if n == "카드" or n == "글머리":
        줄 = []
        if c.get("제목"):
            줄.append(f"- **{_v2글(c.get('제목'))}**")
        들 = "  " if c.get("제목") else ""
        for it in c.get("항목") or []:
            if isinstance(it, dict):
                줄.append(f"{들}- {_v2글(it.get('글'))}")
                줄 += [f"{들}  - {_v2글(s)}" for s in it.get("하위") or []]
            else:
                줄.append(f"{들}- {_v2글(it)}")
        if c.get("아래줄"):
            줄.append(f"{들}- {_v2글(c['아래줄'])}")
        return 줄
    if n == "인용":
        return ["", f"> {_v2글(c.get('인용문'))}" + (f" — {_v2글(c.get('말한이'))}" if c.get("말한이") else ""), ""]
    if n == "전후숫자":
        앞, 뒤 = c.get("이전") or {}, c.get("이후") or {}
        return [f"- **{_v2글(c.get('라벨'))}** {_v2글(앞.get('값'))}{_v2글(앞.get('단위'))} → "
                f"{_v2글(뒤.get('값'))}{_v2글(뒤.get('단위'))}"]
    if n == "진행막대":
        return [f"- **{_v2글(c.get('라벨'))}** {_v2글(c.get('값'))}{_v2글(c.get('단위'))} / {_v2글(c.get('목표'))}{_v2글(c.get('단위'))}"]
    if n == "체계도":
        줄 = [f"- **비전** {_v2글(c.get('비전'))}"]
        줄 += [f"- **{_v2글(x.get('분류'))}** {_v2글(x.get('값'))}" for x in c.get("목표") or [] if isinstance(x, dict)]
        for k, x in enumerate(y for y in c.get("과제") or [] if isinstance(y, dict)):
            줄.append(f"- {k + 1}. {_v2글(x.get('이름'))}")
            줄 += [f"  - {_v2글(t)}" for t in x.get("항목") or [] if isinstance(t, str)]
        return 줄
    if n in ("타임라인", "세로타임라인"):
        단계 = c.get("단계") if n == "타임라인" else c.get("항목")
        줄 = []
        for x in 단계 or []:
            if isinstance(x, dict):
                설명 = x.get("설명")
                설명 = " · ".join(_v2글(t) for t in 설명) if isinstance(설명, list) else _v2글(설명)
                줄.append(f"- **{_v2글(x.get('시점'))}** {_v2글(x.get('제목'))}" + (f" — {설명}" if 설명 else ""))
        줄 += [f"- **{_v2글(x.get('기간'))}** {_v2글(x.get('제목'))}" for x in c.get("상시") or [] if isinstance(x, dict)]
        return 줄
    if n == "요청상자":
        금 = c.get("금액") if isinstance(c.get("금액"), dict) else {}
        줄 = [f"- **{_v2글(c.get('요청문'))}**" + (f" {_v2글(금.get('값'))}{_v2글(금.get('단위'))}" if 금 else "")]
        줄 += [f"  - {_v2글(x.get('이름'))}: {_v2글(x.get('내용'))}" for x in c.get("행") or [] if isinstance(x, dict)]
        return 줄
    if n == "짝카드":
        if c.get("변형") == "대비":
            return ([f"- **{_v2글(c.get('왼제목'))}**"] + [f"  - {_v2글(d.get('글'))}" for d in c.get("왼항목") or [] if isinstance(d, dict)]
                    + [f"- **{_v2글(c.get('오른제목'))}**"] + [f"  - {_v2글(d.get('글'))}" for d in c.get("오른항목") or [] if isinstance(d, dict)])
        return [f"- {_v2글((x.get('왼') or {}).get('글'))} → {_v2글((x.get('오른') or {}).get('글'))}"
                for x in c.get("줄") or [] if isinstance(x, dict)]
    if n == "수량목록":
        줄 = [f"- **{_v2글(c.get('제목'))}**"] if c.get("제목") else []
        들 = "  " if 줄 else ""
        return 줄 + [f"{들}- {_v2글(x.get('라벨'))}: {_v2글(x.get('값'))}{_v2글(x.get('단위'))}"
                    + (f" ({_v2글(x.get('보조'))})" if x.get("보조") else "") for x in c.get("항목") or [] if isinstance(x, dict)]
    if n == "아이콘목록":
        줄 = [f"- **{_v2글(c.get('제목'))}**"] if c.get("제목") else []
        들 = "  " if 줄 else ""
        return 줄 + [f"{들}- {_v2글(x.get('글'))}" + (f" ({_v2글(x.get('보조'))})" if x.get("보조") else "")
                    for x in c.get("항목") or [] if isinstance(x, dict)]
    if n == "항목타일":
        return [f"- **{_v2글(c.get('제목'))}** {_v2글(c.get('글'))}" + (f" ({_v2글(c.get('근거'))})" if c.get("근거") else "")]
    if n == "비율링":
        return [f"- **{_v2글(c.get('라벨'))}** {_v2글(c.get('표시')) or (_v2글(c.get('값')) + '%')}"
                + (f" ({_v2글(c.get('맥락'))})" if c.get("맥락") else "")]
    if n == "색띠행":
        줄 = []
        for x in c.get("행") or []:
            if isinstance(x, dict):
                줄.append(f"- **{_v2글(x.get('분야'))}**")
                줄 += [f"  - {_v2글(t)}" for t in x.get("항목") or [] if isinstance(t, str)]
        return 줄
    글들 = []
    _v2모든글(c, 글들)
    return [f"- {' · '.join(t for t in 글들 if t)}"] if 글들 else []


def _슬라이드v2_마크다운(doc):
    정 = doc.get("발표정보") if isinstance(doc.get("발표정보"), dict) else {}
    줄 = [f"# {벗김(doc.get('제목') or doc.get('filename') or '')}", ""]
    장들 = [s for s in doc.get("장") or [] if isinstance(s, dict)]
    표지 = next((s.get("표지") for s in 장들 if s.get("유형") == "표지" and isinstance(s.get("표지"), dict)), {}) or {}
    부제 = 표지.get("부제") or doc.get("부제")
    if 부제:
        줄 += [f"*{벗김(부제)}*", ""]
    정보 = [벗김(정[k]) for k in ("기관", "부서", "회의", "일자", "발표자") if isinstance(정.get(k), str) and 정.get(k)]
    if 정보:
        줄 += [" · ".join(정보), ""]
    for 장 in 장들:
        유형 = 장.get("유형")
        if 유형 == "표지":
            continue
        if 유형 == "간지":
            간 = 장.get("간지") if isinstance(장.get("간지"), dict) else {}
            줄 += [f"## {(벗김(간.get('번호')) + ' ') if 간.get('번호') else ''}{벗김(간.get('제목') or '')}".rstrip(), ""]
            줄 += [f"- {벗김(t)}" for t in 간.get("목록") or [] if isinstance(t, str)]
            줄.append("")
            continue
        if 유형 == "목차":
            목 = 장.get("목차") if isinstance(장.get("목차"), dict) else {}
            줄 += ["## 목차", ""] + [f"{k + 1}. {벗김(t)}" for k, t in enumerate(x for x in 목.get("항목") or [] if isinstance(x, str))] + [""]
            continue
        if 유형 == "마무리":
            마 = 장.get("마무리") if isinstance(장.get("마무리"), dict) else {}
            줄 += [f"## {_v2글(마.get('문구'))}", ""]
            if 마.get("부문구"):
                줄 += [벗김(마["부문구"]), ""]
            문의 = 마.get("문의") if isinstance(마.get("문의"), dict) else {}
            if 문의:
                줄 += ["문의: " + " ".join(벗김(문의[k]) for k in ("부서", "연락처") if 문의.get(k)), ""]
            continue
        머리 = 장.get("머리") if isinstance(장.get("머리"), dict) else {}
        라벨, 메시지 = 벗김(머리.get("라벨") or ""), 벗김(머리.get("메시지") or "")
        줄 += [f"## {라벨 + ' : ' if 라벨 and 메시지 else 라벨}{메시지}", ""]
        리드 = 장.get("리드")
        if isinstance(리드, dict):
            줄 += [f"{벗김(리드.get('앞') or '')} → {벗김(리드.get('뒤') or '')}", ""]
        elif 리드:
            줄 += [_v2글(리드), ""]
        for c in 장.get("칸") or []:
            if isinstance(c, dict):
                줄 += _v2부품줄(c)
        띠 = 장.get("요지띠") if isinstance(장.get("요지띠"), dict) else {}
        if 띠.get("메시지"):
            줄 += ["", f"> **{벗김(띠.get('라벨') or '요지')}** {_v2글(띠.get('메시지'))}"]
        if 장.get("출처"):
            줄 += ["", f"*출처: {벗김(장['출처'])}*"]
        줄.append("")
    return 줄


# ── 보도자료 ─────────────────────────────────────────────────
#
# 실측 위계 사다리(assemble_press.py 마커 — □ → ○ → - → ※)는 글자 그대로 박지 않고
# 옛 코드와 같은 방식(들여쓴 "- " 목록)을 따른다 — kordoc 이 목록 깊이로 자기 마커를
# 매기므로(이 파일 머리말 참조), 글자를 겹쳐 넣으면 마커가 두 번 찍힌다. 옛 버그는
# 이 깊이 계산 자체가 없었던 것(level 이 정수 1~4인데 문자열 키 dict.get(lv,1) 이라
# 늘 1 로 떨어져 전부 같은 깊이가 됐다, 벤치마크 진단).
_보도위계 = (1, 2, 3, 4)


def _보도자료_마크다운(doc):
    줄 = [f"# {벗김(doc.get('제목') or doc.get('filename') or '')}", ""]
    if doc.get("부제"):
        줄 += [f"*{벗김(doc['부제'])}*", ""]

    머리 = []
    if doc.get("문서종류"):
        머리.append(벗김(doc["문서종류"]))
    보도시점 = doc.get("보도시점") if isinstance(doc.get("보도시점"), dict) else {}
    if 보도시점.get("값"):
        방식 = 벗김(보도시점.get("방식") or "")
        머리.append(f"보도시점: {(방식 + ' ') if 방식 and 방식 != '즉시' else ''}{벗김(보도시점['값'])}".strip())
    elif doc.get("보도일시"):
        머리.append(f"보도시점: {벗김(doc['보도일시'])}")
    if doc.get("배포"):
        머리.append(f"배포: {벗김(doc['배포'])}")
    if 머리:
        줄 += [" · ".join(머리), ""]

    if doc.get("리드"):
        줄 += [벗김(doc["리드"]), ""]

    개요표 = doc.get("개요표")
    if isinstance(개요표, dict) and 개요표.get("header"):
        if 개요표.get("제목"):
            줄 += [f"**{벗김(개요표['제목'])}**", ""]
        줄 += 표를(개요표)

    # 본문꼴 '서술'('26-09-28) — HTML·HWPX 는 1·2수준을 기호 없는 문단으로 짓는다(assemble_press.py).
    # MD 만 목록으로 내면 같은 문서가 산출물마다 갈린다(2단계 검토 발견 7) — 1·2수준은 빈 줄로 나눈
    # 문단, 3·4수준(-·※)만 목록으로 낸다. 문단 뒤 목록은 두 칸 덜 들인다(네 칸이면 코드 블록이 된다).
    서술 = doc.get("본문꼴") == "서술"
    for it in doc.get("본문") or []:
        if not isinstance(it, dict):
            continue
        if "표" in it:
            # 표 앞에 빈 줄을 넣는다 — 안 넣으면 바로 앞 "- 목록" 줄에 GFM 이 표를 게으른
            # 연속줄(lazy continuation)로 흡수해 <table> 이 안 만들어진다(2026-09-26 고침,
            # r2/check.json #9 — markdown-it·micromark+gfm 렌더 실측으로 확인).
            줄.append("")
            줄 += 표를(it["표"])
            continue
        글 = 벗김(it.get("text") or "")
        if not 글:
            continue
        lv = it.get("level")
        깊 = _보도위계.index(lv) if lv in _보도위계 else 0
        if 서술 and lv in (1, 2):
            if 줄 and 줄[-1] != "":
                줄.append("")
            줄 += [글, ""]
            continue
        if 서술:
            깊 = max(0, 깊 - 2)
        줄.append("  " * 깊 + "- " + 글)
    줄.append("")
    return 줄


# ── 시행문(gongmun)·1페이지(onepage) — 그 밖의 장르는 이 공통 경로를 쓴다 ──


def _시행문_머리줄(doc):
    """시행문 두문 — 기관명·수신·경유(assemble_gongmun.py build() 와 같은 자리).
    2026-09-26 고침(r2/check.json #12) — 누가 누구에게 보내는 공문인지가 MD 에서
    통째로 빠져 있었다(HEAD 부터의 기존 결함, 이번에 같이 잡는다).
    2026-09-27 고침(assemble:F11) — 수신 은 build/수신꼴.py 의 단일수신 축약을 그대로
    따른다. 이 축약(구성.수신.단일수신)은 화면 전용이 아니라 문서 내용을 정하는 규칙이고
    HWPX(HTML 을 옮겨 만든다)에도 이미 적용되고 있어, MD 만 원본 필드를 그대로 내면
    같은 문서의 두문 표기가 산출물마다 갈렸다."""
    if doc.get("genre") != "gongmun":
        return []
    줄 = []
    if doc.get("기관명"):
        줄.append(f"**{벗김(doc['기관명'])}**")
    수신표시, _수신자란표시, _경로 = 수신꼴.수신정리(doc)
    if 수신표시:
        줄.append(f"수신: {벗김(수신표시)}")
    if doc.get("경유"):
        줄.append(f"(경유) {벗김(doc['경유'])}")
    if 줄:
        줄.append("")
    return 줄


def _시행문_결문줄(doc):
    """시행문 결문 — 발신명의·수신자란·시행 번호·시행일·연락처.
    2026-09-27 고침(assemble:F11) — 수신자란 도 _시행문_머리줄 과 같은
    build/수신꼴.py 판정을 쓴다(위 함수 docstring 참조) — 두문에서 수신처를 이미
    한 번 찍었으면(단일수신 축약) 결문에서 또 찍지 않는다."""
    if doc.get("genre") != "gongmun":
        return []
    줄 = []
    발신 = 벗김(doc.get("발신명의") or "")
    if 발신:
        줄.append(f"**{발신}**")
    _수신표시, 수신자란표시, _경로 = 수신꼴.수신정리(doc)
    수신자란 = 벗김(수신자란표시)
    if 수신자란:
        줄.append(f"수신자 {수신자란}")
    m = doc.get("메타") if isinstance(doc.get("메타"), dict) else {}
    시행 = 벗김(m.get("시행") or "")
    시행일 = 벗김(m.get("시행일") or "")
    if 시행 or 시행일:
        줄.append(f"시행 {시행}{f' ({시행일})' if 시행일 else ''}".strip())
    # 우편번호·주소 — assemble_gongmun._우편주소 와 같은 규칙('26-09-27 벤치마크
    # 진단: 주소가 비어도 '우' 글자만 남아 결문 한 줄을 차지하던 것을 HTML/PDF/HWPX
    # 쪽에서 고쳤다). MD 는 이미 주소가 비면 줄째 뺐지만(그 부분은 회귀가 아니었다),
    # 우편번호 필드는 안 읽어 HTML 쪽과 표기가 갈렸다 — 여기서도 같이 합친다.
    _우 = m.get("우편번호")
    # 정수로 온 우편번호는 앞자리 0 을 이미 잃었다 — 조립기(_우편번호꼴)와 같게 5자리로 맞춘다.
    우편번호 = (f"{_우:05d}" if isinstance(_우, int) and not isinstance(_우, bool) and 0 <= _우 < 100000
             else 벗김(str(_우) if _우 not in (None, "") else ""))
    주소 = 벗김(m.get("주소") or "")
    우편주소 = " ".join(x for x in (우편번호, 주소) if x)
    if 우편주소:
        줄.append(f"우 {우편주소}")
    # 연락처 — assemble_gongmun._결문줄 과 같은 키·순서(전화+내선 묶음, 전송=팩스,
    # 이메일, 공개). 2026-09-27 고침(r3/check.json 새 결함) — 스키마·조립기 어디에도
    # 없는 '전자우편' 키를 읽어서 내선·팩스·이메일·공개가 자료에 있어도 MD 에서 늘
    # 빠졌다(메타_빈값원칙: 연락처는 자료에 있으면 그대로 채운다).
    전화 = 벗김(m.get("전화") or "")
    내선 = 벗김(m.get("내선") or "")
    if 전화 and 내선:
        연락 = [f"전화 {전화}(내선 {내선})"]
    elif 전화:
        연락 = [f"전화 {전화}"]
    elif 내선:
        연락 = [f"내선 {내선}"]
    else:
        연락 = []
    for 라벨, 키 in (("전송 ", "팩스"), ("", "이메일"), ("", "공개")):
        값 = 벗김(m.get(키) or "")
        if 값:
            연락.append(f"{라벨}{값}")
    if 연락:
        줄.append(" / ".join(연락))
    if 줄:
        줄 = [""] + 줄 + [""]
    return 줄


def _기본_마크다운(doc):
    제목 = (doc.get("title") or doc.get("제목") or doc.get("제명")
          or (doc.get("표지") or {}).get("제목") or doc.get("filename"))
    줄 = [f"# {벗김(제목)}", ""]
    줄 += _시행문_머리줄(doc)
    if doc.get("byline"):
        줄 += [벗김(doc["byline"]).strip("<>"), ""]
    if doc.get("summary"):
        줄 += [f"> {벗김(doc['summary'])}", ""]

    표 = doc.get("table")
    for sec in doc.get("sections") or []:
        줄 += [f"## {벗김(sec.get('heading') or '')}", ""]
        줄 += _마디(sec.get("items"), 표, sec.get("heading"))

    # 시행문(gongmun) 본문 — level 은 정수(1: 본 문단, 2 이상: 그 아래 세부)다.
    # 옛 코드는 문자열 키 dict({"항":1,"호":2,"목":3})로만 깊이를 찾아 정수 level 이
    # 늘 기본값(1단)으로 떨어졌다 — 여기서는 level 값 자체를 깊이로 쓴다.
    for 마당 in ("본문", "body"):
        본문값 = doc.get(마당)
        if not 본문값:
            continue
        for x in 본문값:
            if not isinstance(x, dict):
                continue
            if "표" in x:
                줄.append("")   # 표 앞 빈 줄(위 보도자료 주석과 같은 이유, r2/check.json #9)
                줄 += 표를(x["표"])
                continue
            글 = 벗김(x.get("text") or "")
            if not 글:
                continue
            lv = x.get("level")
            깊 = max(int(lv) - 1, 0) if isinstance(lv, (int, float)) else 0
            줄.append("  " * 깊 + "- " + 글)
        줄.append("")
    줄 += _시행문_결문줄(doc)
    return 줄


def 마크다운(doc, 그림링크=None):
    global _그림링크
    _그림링크 = 그림링크
    try:
        return _md무력화(_마크다운(doc))
    finally:
        _그림링크 = None


# MD 로 들어간 글의 HTML·링크 문법 무력화('26-09-30 fixup3 N4) — 캡션·본문·표·목록에 적힌 `<img src="http://…">`·
# `[x](http://…)`·`![x](http://…)` 가 HTML 을 그리는 MD 뷰어에서 받는 사람 쪽 바깥 주소를 불렀다(verify_fixup2 N4).
# 글자 뒤 `<`(태그 시작 꼴)는 &lt; 로, 링크를 여는 `](`·`][`·`]:` 의 `]` 는 &#93; 로 바꾼다(글로 보이고 문법은 아니다 —
# 한글 앞 꺾쇠 '<고객지원처, …>' 는 태그 꼴이 아니라 그대로). 표 칸 줄바꿈 `<br>` 과 tomd 가 스스로 쓰는 그림 줄
# `![대체](data:image/…|상대 경로)` 의 링크만 둔다(대체 글은 같이 무력화).
_md태그꼴 = re.compile(r"<(?!br>)(?=[A-Za-z/!?])")
_md링크꼴 = re.compile(r"\](?=[(\[:])")
_md그림줄 = re.compile(r"^!\[(.*)\]\((data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]*|(?![A-Za-z][A-Za-z0-9+.-]*:|//)[^()\s]*)\)$")


def _md글무력화(s):
    return _md링크꼴.sub("&#93;", _md태그꼴.sub("&lt;", s))


def _md무력화(md):
    out = []
    for 줄 in md.split("\n"):
        m = _md그림줄.match(줄)
        if m:
            out.append(f"![{_md글무력화(m.group(1)).replace('[', '(').replace(']', ')')}]({m.group(2)})")
        else:
            out.append(_md글무력화(줄))
    return "\n".join(out)


def _마크다운(doc):
    # 시행문 붙임 분리 — HTML(assemble_gongmun.조립하기)과 이 MD 가 같은 doc 을 거치지
    # 않고 각자 따로 불릴 수 있어(자료뿌리.모듈 호출) 여기서도 한 번 더 건다(멱등 —
    # genre != "gongmun" 이거나 이미 분리돼 있으면 아무것도 안 바뀐다). 아래
    # `doc.get("붙임")` 을 읽기 **전에** 돌아야 옮겨진 항목이 붙임 목록에 실린다.
    if 붙임꼴:
        붙임꼴.분리하기(doc)
    장르 = doc.get("genre") or "onepage"
    if 장르 == "regulation":
        줄 = _규정_마크다운(doc)
    elif 장르 == "fullreport":
        줄 = _풀버전_마크다운(doc)
    elif 장르 == "slides":
        줄 = _슬라이드v2_마크다운(doc) if doc.get("판형") == "v2" else _슬라이드_마크다운(doc)
    elif 장르 in ("press-release", "press"):
        # "press" — build/genres.py 표의 등록부 파일명 그루터기와 같은 값인데,
        # 실제 문서 genre 필드에 이 값 그대로 든 것이 세션 표본에서 여럿 확인됐다
        # (2026-09-26). 정본 내부 키·화면 이름 둘 다 "press-release"다 — stylelint.py
        # doc_genre() 도 이제 등록부 그루터기를 화면 이름과 함께 받는다(2026-09-26
        # 고침, r2/check.json #8). 여기서는 MD 내보내기가 빈 채로 나가지 않게 그대로 둔다.
        줄 = _보도자료_마크다운(doc)
        # 끝 붙임 사진('26-09-30 P1 — 본문이 아니라 끝에 올린 사진만). 링크 없이 부르면 옛 방식대로 설명만
        _사진 = doc.get("붙임사진")
        for sp in (_사진 if isinstance(_사진, list) else [_사진] if isinstance(_사진, dict) else []):
            줄 += _이미지줄(sp, 캡션아래=True)
        줄 += _담당_줄(doc.get("담당"))
    else:
        줄 = _기본_마크다운(doc)

    if 장르 != "regulation":       # 규정은 부칙·별표를 붙임 대신 이미 자기 절에서 냈다
        # 풀버전은 첨부 키가 '별첨'이다(스키마 — attach·붙임이 아니다) — 2026-09-26 고침
        # (r2/check.json #5): 새로 쓴 _붙임_줄 은 이 키를 안 받아 풀버전 첨부 목록이
        # 한 번도 안 나갔다.
        줄 += _붙임_줄(doc.get("attach") or doc.get("붙임") or doc.get("별첨"))

    return "\n".join(줄).rstrip() + "\n"


if __name__ == "__main__":
    doc = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 \
        else json.load(sys.stdin)
    if isinstance(doc, list):
        doc = doc[0]
    sys.stdout.write(마크다운(doc))
