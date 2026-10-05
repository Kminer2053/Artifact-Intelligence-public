#!/usr/bin/env python3
"""명령 목록을 받아 HWPX 를 쓴다. **python-hwpx 가 있는 venv 에서만 돈다.**

    build/.hwpxenv/bin/python build/_hwpx_write.py <명령.json> <나갈.hwpx>

전에는 tohwpx.py 안의 문자열이었고 **매 실행마다 덮어써졌다.** 손으로 고치면 다음 실행에
날아갔다. 진짜 모듈로 올렸으니 이제 여기를 고치면 된다.

여기는 **판단하지 않는다.** 무엇을 어떤 값으로 옮길지는 build/역할.py 가 이미 정했고,
그 값은 화면에서 잰 것이다. 여기가 하는 일은 명령을 python-hwpx 로 실행하는 것뿐이다.

python-hwpx 6.0.2 를 직접 두드려 확인한 것만 쓴다(추측 금지):
  · `styles.ensure_run(size=…)` 의 size 단위는 **pt** 다(1800 아님).
  · 문단 배경은 `set_paragraph_format` 에 없다. header 의
    `ensure_border_fill(fill_color=…)` → `ensure_paragraph_format(border={"borderFillIDRef":…})`
    로 넣는다. 실측으로 `faceColor="#EAEAEA"` 가 들어가고 XSD 통과를 확인했다.
  · 내어쓰기는 `margins={"intent": 음수}` 또는 `first_line_indent_mm=음수`.
  · 자간은 `ensure_run(letter_spacing=…)`. 화면의 자간 사냥 결과를 옮기는 자리다.
  · `doc.set_paragraph_format` 은 6.0 에서 `doc.styles.apply_paragraph_format` 로 옮겼다.
  · 셀 병합은 반드시 `merge_cells()` — `set_span()` 을 직접 부르면 겹침 오류가 난다.
  · 글꼴 이름은 **지킬 수 있다.** 라이브러리의 빈 골격에 함초롬 두 벌만 들어 있을 뿐,
    `<hh:fontfaces>` 에 항목을 더하면 `ensure_run(font=…)` 이 그 이름을 쓴다. 그 전까지는
    없는 이름이 조용히 버려져(charPr id 가 전부 0) 함초롬 2종으로 접히고 있었다.
    → `_글꼴표_늘리기()`. 없는 PC 대비는 `<hh:substFont>` 로 우리가 정한다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from hwpx.document import HwpxDocument

HU = 283.465          # 1mm 당 HWPUNIT
알려진차이: list[str] = []
# 근사(화면 모양을 가까운 한글 꼴로 옮긴 것)는 실패(못 넣었다)와 따로 모은다. 한데 모아
# 가나다순으로 내면 근사 문구가 앞자리를 채워 **실패 문구가 잘렸다**(tohwpx 가 앞 3건만
# 싣는다, '26-09-28 P0 적대검토 L1). 쓰기() 가 실패를 먼저, 근사를 뒤에 싣는다.
알려진근사: list[str] = []
# 선 굵기 16단계 스냅은 굵기마다 한 줄씩 내면 근사만으로 자리를 채운다 — (화면, 한글) 짝을
# 모았다가 쓰기() 끝에 한 줄로 낸다.
_굵기스냅: set[tuple[float, float]] = set()

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_정본화할요소 = ("hh:charPr", "hh:refList")   # WP-H6 ② — 우리 출력이 골든과 어긋나던 둘


def 정본자식순서_읽기() -> dict[str, list[str]]:
    """`hh:charPr`·`hh:refList` 의 **정본 자식순서**를 읽어 온다 (골든 우선).

    손목록을 안 적는다(규칙 2) — build/골든요소순서.json(neolord0/hwpxlib 이 실제로 뱉는
    XML 에서 긁은 순서, 없으면 build/요소순서.json 의 hancom InitMap 순서)에서 읽는다.
    이 둘은 charPr·refList 자식순서에선 서로 같다(구현계획-부록 H6 3자대조).
    """
    from pathlib import Path
    canon: dict[str, list[str]] = {}
    for fn in ("골든요소순서.json", "요소순서.json"):
        p = Path(__file__).with_name(fn)
        if not p.exists():
            continue
        요소 = json.loads(p.read_text(encoding="utf-8")).get("요소", {})
        for 태그 in _정본화할요소:
            if 태그 not in canon and 태그 in 요소:
                canon[태그] = 요소[태그]["자식순서"]
    return canon


def _자식정렬(el, 정본태그들: list[str]) -> bool:
    """`el` 의 직계 자식을 정본 순서로 **안정 재배치**한다. 순서만 바꾸고 값은 안 바꾼다.

    정본에 있는 자식들만 자기들끼리 정본 순서로 다시 앉히고, 정본에 **없는** 자식은
    건드리지 않는다(원래 자리를 지킨다). python-hwpx 의 `ensure_run` 이 bold·italic·
    underline·strikeout 를 charPr **끝**에 붙여 outline·shadow 뒤로 밀어 둔 것을, 여기서
    정본 자리(bold<underline<strikeout<outline<shadow)로 되돌린다. refList 도 bullets 를
    styles 앞으로 되돌린다. (바뀌었으면 True)
    """
    자리 = {t: i for i, t in enumerate(정본태그들)}   # "hh:underline" → index

    def 태그이름(c):
        t = c.tag
        if isinstance(t, str) and t.startswith(_HH):
            return "hh:" + t[len(_HH):]
        return None  # hh 가 아닌(또는 주석 등) 자식 — 정본에 없는 것으로 취급, 자리 지킴

    자식들 = list(el)
    아는자리 = [i for i, c in enumerate(자식들) if 태그이름(c) in 자리]
    아는것 = [자식들[i] for i in 아는자리]
    정렬된 = sorted(아는것, key=lambda c: 자리[태그이름(c)])
    if 정렬된 == 아는것:
        return False  # 이미 정본 순서 — 손대지 않는다
    새자식 = list(자식들)
    for slot, c in zip(아는자리, 정렬된):
        새자식[slot] = c
    for c in 자식들:
        el.remove(c)
    for c in 새자식:
        el.append(c)
    return True


def 머리말_자식순서_정본화(머리말요소) -> int:
    """머리말(header.xml root) 밑 모든 charPr 와 refList 의 자식순서를 정본으로. (바뀐 수)

    붓.자식순서_정본화()(새로 쓸 때)와 표본 갱신(이미 있는 .hwpx 를 열어 다시 걸 때) 둘
    다 이 함수를 쓴다 — 정본화 로직은 여기 한 곳에만 둔다.
    """
    canon = 정본자식순서_읽기()
    if not canon:
        알려진차이.append("정본 자식순서 표(골든요소순서.json/요소순서.json)를 못 읽어 "
                      "charPr·refList 순서를 못 바로잡았다")
        return 0
    바뀜 = 0
    if "hh:charPr" in canon:
        for cp in 머리말요소.iter(f"{_HH}charPr"):
            if _자식정렬(cp, canon["hh:charPr"]):
                바뀜 += 1
    if "hh:refList" in canon:
        rl = 머리말요소.find(f"{_HH}refList")
        if rl is not None and _자식정렬(rl, canon["hh:refList"]):
            바뀜 += 1
    return 바뀜

_고딕, _명조 = "함초롬돋움", "함초롬바탕"
_명조계 = ("serif", "명조", "myungjo", "myeongjo", "바탕", "batang", "noto serif")


def 화면이_내장한_글꼴():
    """화면이 `@font-face` 로 싣는 글꼴 이름들. **손으로 적지 않는다** — tokens.css 가 정본이다.

    정본(ontology.json)이 정한 것: onepage-report.디자인.fonts.default_mode =
    "embed(올-Pretendard 고딕, OFL 내장, 전 런타임 동일)". gongmun·fullreport 도 같다
    ('26. 7. 26. 결정). 즉 글꼴은 **함초롬이 아니라 화면이 싣는 그것**이 정본이다.
    """
    from pathlib import Path
    css = Path(__file__).with_name("tokens.css")
    if not css.exists():
        return []
    import re as _re
    낸것 = []
    for 덩이 in _re.findall(r"@font-face\s*\{(.*?)\}", css.read_text(encoding="utf-8"), _re.S):
        m = _re.search(r'font-family:\s*["\']([^"\']+)["\']', 덩이)
        if m and m.group(1) not in 낸것:
            낸것.append(m.group(1))
    return 낸것


def _명조인가(이름):
    """명조 계열인가.

    **`sans-serif` 를 먼저 지워야 한다.** 안 지우면 그 안의 `serif` 에 걸려
    고딕 스택이 전부 명조로 간다 — `"Apple SD Gothic Neo", sans-serif` 가
    함초롬바탕으로 나가고 있었다(2026-08-06 발견, 원래 있던 결함).
    """
    낮 = (이름 or "").lower().replace("sans-serif", "").replace("sans serif", "")
    return any(k in 낮 for k in _명조계)


def _대체(이름):
    """그 글꼴이 없는 PC 에서 무엇으로 떨어질지. 한글이 늘 갖고 있는 두 벌 중 결이 같은 쪽."""
    return _명조 if _명조인가(이름) else _고딕


def _글꼴(이름):
    """화면이 쓴 글꼴 스택에서 **맨 앞 이름**을 고른다.

    맨 앞이 우리가 등록해 둔 얼굴이면 그 이름을 그대로 쓴다(화면과 같아진다).
    아니면 예전처럼 고딕·명조 두 벌로 사상한다.
    """
    if not 이름:
        return _고딕
    맨앞 = 이름.split(",")[0].strip().strip("\"'")
    for 등록 in 화면이_내장한_글꼴():
        if 맨앞.lower() == 등록.lower():
            return 등록
    return _명조 if _명조인가(이름) else _고딕


def _색(v):
    return v if (isinstance(v, str) and v.startswith("#")) else None


_정렬표 = {"LEFT": "LEFT", "CENTER": "CENTER", "RIGHT": "RIGHT", "JUSTIFY": "JUSTIFY"}

_OPF_NS = "{http://www.idpf.org/2007/opf/}"
_요일표 = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def _문서메타손보기(doc):
    """content.hpf(OPF 메타데이터)의 작성자·저장자·작성일·수정일을 **내보내는 시각**으로.

    python-hwpx 의 빈 골격(`HwpxDocument.new()` → data/Skeleton.hwpx)이 박아 둔
    creator·lastsaveby="synthetic-fixture-author", CreatedDate/ModifiedDate=
    2025-09-17 고정값이 손대지 않으면 그대로 결재용 산출물에 실린다 — 실제
    작성자·작성일과 무관한 가짜 값이 노출된다(mcp s2 결함, 2026-09-27).
    이 골격 파일은 서드파티 패키지(build/.hwpxenv) 소유라 거기를 고치지 않고
    여기서 내보낼 때마다 실제 시각으로 바꿔 쓴다.

    **`doc.package.set_xml(...)` 로는 안 된다** — 직접 두드려 확인했다(2026-09-27).
    저장(`save_to_path`)은 `doc.oxml.serialize()` 가 낸 갱신분으로 파일을 **덮어쓰는데**,
    `HwpxOxmlDocument` 는 제 manifest 원소(`doc.oxml.manifest`)를 문서 생성 때부터 따로
    들고 있다(add_section·add_picture 가 그 원소를 직접 고친다). package 쪽에 새로
    파싱해 얹은 XML은 이 원소와 다른 사본이라, serialize() 가 (내가 손 안 댄) **옛
    사본을 되얹어** 방금 쓴 값을 조용히 지운다 — 재현: 빈 문서에 package.set_xml 로만
    creator 를 바꾸고 저장하면 골격 값 그대로 나온다. `doc.oxml.manifest` 원소를 직접
    고치고 `_manifest_dirty` 를 켜야(공개 세터가 없다 — header 의 `mark_dirty()`처럼
    이 뜻의 공개 API 가 manifest 엔 없다) serialize() 가 그 원소를 실제로 내보낸다.
    """
    try:
        manifest = doc.oxml.manifest
        지금 = datetime.now(timezone.utc)
        지금로컬 = 지금.astimezone()
        시12 = 지금로컬.hour % 12 or 12
        한글날짜 = (f"{지금로컬.year}년 {지금로컬.month}월 {지금로컬.day}일 "
                  f"{_요일표[지금로컬.weekday()]} {'오전' if 지금로컬.hour < 12 else '오후'} "
                  f"{시12}:{지금로컬.minute:02d}:{지금로컬.second:02d}")
        갈아끼울것 = {
            "creator": "문서지능", "lastsaveby": "문서지능",
            "CreatedDate": 지금.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ModifiedDate": 지금.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": 한글날짜,
        }
        바뀜 = False
        for meta in manifest.iter(f"{_OPF_NS}meta"):
            이름 = meta.get("name")
            if 이름 in 갈아끼울것:
                meta.text = 갈아끼울것[이름]
                바뀜 = True
        if 바뀜:
            doc.oxml._manifest_dirty = True
    except Exception as e:
        알려진차이.append(f"문서 메타(작성자·날짜)를 못 손봤다 — {type(e).__name__}")


def _미리보기텍스트(지면글: str, 최대: int = 1000) -> str:
    """탐색기·한글 뷰어의 미리보기가 읽는 `Preview/PrvText.txt` 를 채울 글.

    화면읽기.py 가 이미 잰 **독립된 눈**(지면 전체 글자, 마디 짝짓기와 무관하게 페이지
    innerText 를 그대로 합친 것)을 그대로 쓴다 — 다시 훑거나 새로 뽑지 않는다.
    실물 한글 산출물(research/corpus)의 PrvText.txt 를 실측한 형식을 따른다:
    맨 앞에 빈 줄 넷(\\r\\n×4), 문단 구분은 \\r\\n, 인코딩은 BOM 없는 UTF-8.
    본문이 없으면(빈 골격을 그대로 내보내는 예외적 경우) 예전처럼 개행 두 글자만 둔다
    — 비어 있던 자리를 억지로 채우지 않는다(mcp s5 결함, 2026-09-27).
    """
    글 = (지면글 or "").replace("\r\n", "\n").strip()
    if not 글:
        return "\r\n"
    글 = 글.replace("\n", "\r\n")
    if len(글) > 최대:
        글 = 글[:최대]
    return "\r\n\r\n\r\n\r\n" + 글 + "\r\n"


class 붓:
    def __init__(self, 문서):
        self.d = HwpxDocument.new()
        self.h = self.d.oxml.headers[0]
        self._글자캐시, self._문단캐시 = {}, {}
        여 = 문서.get("여백mm") or [25, 25, 20, 25]
        # 쪽 크기는 건드리지 않는다 — 라이브러리 기본이 이미 A4 다.
        # (2026-08-05: mm 인 줄 알고 210×297 을 넣었다가 0.7mm 쪽이 되어 446쪽이 나왔다)
        # 머리말·꼬리말은 **0 이다.** 화면에는 그런 것이 없다.
        # 10mm 씩 박아 두었더니 한글이 그만큼을 위아래에서 더 깎아, 글자가 앉을 높이가
        # 232.0mm 밖에 안 됐다(35.0~267.0). 화면은 같은 문서를 244.4mm 에 담는다.
        # 12.4mm 가 모자라 1p 보고서가 **한글에서 2쪽**이 됐다(2026-08-06 a2-03-plan
        # 뷰어 실측 — 화면 28줄 1쪽 vs 한글 25줄 + 3줄이 2쪽으로).
        # 값 비교로는 절대 안 잡힌다 — 여백은 "우리가 넣은 대로" 들어 있었다.
        self.d.set_page_margins(
            top=round(여[0] * HU), right=round(여[1] * HU),
            bottom=round(여[2] * HU), left=round(여[3] * HU),
            header=0, footer=0)
        # 판면(내용) 폭 — 좁은 배경없는-테두리 상자의 hc:right 를 역산하는 데 쓴다
        # (자리잡기() 참고). 쪽 크기는 안 건드리므로(위 주석) A4 210mm 를 그대로 쓴다.
        self.판면폭mm = 210 - (여[1] or 0) - (여[3] or 0)
        self._장르 = 문서.get("장르")
        # 풀버전 쪽번호 — 화면의 '.fr-pageno'(하단 가운데 '- N -')는 역할.py 가 이미
        # 버렸다(_보통문단 참고, H5). 여기서 **한글의 실제 꼬리말 쪽 번호 필드**로
        # 대신 건다 — 화면처럼 본문 문단으로 넣으면 쪽 아래가 아니라 본문 바로 밑에
        # 낀다(2026-09-26/27, r2 벤치마크 진단 hwpx.findings, H5). doc.page.set_page_number
        # 는 python-hwpx 가 직접 두드려 확인한 실제 쪽번호 필드 API 다(_document/ns/page.py).
        #
        # **필드는 물리 쪽수만 센다 — 화면 규칙(감춤·재시작)은 구역(section)으로 옮긴다**
        # (3차 수정, "꼬리말 쪽번호" high 결함). 2차 수정까지는 장르가 fullreport 면
        # 무조건 물리 쪽수를 찍어, 정부부처형('본문재시작')처럼 화면이 본문에서 번호를
        # 1로 다시 매기면 목차의 번호와 어긋났다(표지·목차만큼 밀린다). python-hwpx 가
        # 문단 하나만 감추거나 재시작하는 API 를 안 주므로(찾아본 것 — doc.page 에는
        # hideFirstPageNum(구역의 **첫 쪽만**) 과 hp:startNum(구역 단위) 뿐이다), 화면이
        # 쪽마다 낸 번호·숨김이 바뀌는 경계마다 **한글 구역을 새로 열어**(add_section,
        # 직전 구역의 용지·여백·꼬리말 필드를 그대로 이어받는다) 그 구역에
        # hide_first_page_num·hp:startNum(page=N) 을 건다 — _새섹션()·쪽나눔() 참고.
        # 쪽정보 가 없는(장르가 fullreport 가 아니거나 화면읽기가 옛 스냅샷인) 문서는
        # 종전처럼 표지만 hideFirstPageNum 으로 감추고 구역을 안 나눈다.
        self._쪽정보 = (문서.get("쪽정보") or []) if self._장르 == "fullreport" else []
        self._쪽카운터 = 1
        # 골격의 첫 구역(section)이 이미 유령 문단 하나를 갖고 있다 — 쓰기() 끝의
        # 유령줄 줄이기가 이 목록을 훑는다. _새섹션() 이 구역을 더 열 때마다 여기에
        # 더한다(같은 유령 문단이 구역마다 하나씩 생긴다).
        self._섹션첫문단들: list[int] = [0]
        self._쪽번호상태 = {"번호숨김": False}
        self._쪽번호예상: int | None = None
        if self._장르 == "fullreport":
            첫 = self._쪽정보[0] if self._쪽정보 else {}
            첫_번호숨김 = bool(첫.get("번호숨김", True))     # 정보가 없으면 표지 관행대로 감춘다
            첫_쪽번호 = 첫.get("쪽번호")
            try:
                self.d.page.set_page_number(
                    target="footer", position="BOTTOM_CENTER", align="CENTER",
                    prefix="- ", suffix=" -", format="page")
                self.d.page.set_visibility(
                    hide_first_page_num=첫_번호숨김, hide_first_footer=첫_번호숨김)
                if 첫_쪽번호 is not None and 첫_쪽번호 != 1:
                    self.d.sections[0].properties.set_start_numbering(page=첫_쪽번호)
                self._쪽번호상태 = {"번호숨김": 첫_번호숨김}
                self._쪽번호예상 = 첫_쪽번호 if 첫_쪽번호 is not None else 1
            except Exception as e:
                알려진차이.append(f"쪽번호 꼬리말을 못 걸었다 — {type(e).__name__}")
        self._글꼴표_늘리기()

    def _글꼴표_늘리기(self):
        """화면이 쓰는 글꼴을 HWPX 글꼴 표에 더한다. **글자모양을 만들기 전에** 해야 한다.

        왜 필요한가 — `styles.ensure_run(font=…)` 은 표에 없는 이름을 **조용히 버린다**.
        셋을 서로 다르게 넣어도 charPr id 가 똑같이 0 으로 나온다(6.0.2 실측). 버려지는
        줄도 모르고 "HWPX 는 함초롬 두 벌뿐" 이라고 적어 뒀던 것이 이 함수의 내력이다.

        `<hh:substFont>` 를 함께 단다 — 그 글꼴이 없는 PC 에서 무엇으로 떨어질지 우리가
        정하는 자리다. 한컴 뷰어 실측(2026-08-06):
          · face 만 넣으면 → 깔린 PC 에서 그 글꼴로 그린다 (AppleMyungjo 로 확인)
          · substFont 를 달면 → 없는 PC 에서 지정한 글꼴로 떨어진다 (확인)
          · **isEmbedded="1" + binaryItemIDRef 로 글꼴 파일을 넣어도 뷰어가 무시한다**
            (Noto Serif KR 실물 146KB 를 넣어도 그려지지 않았다). 그래서 파일 동봉은
            안 한다 — 문서만 무거워지고 얻는 게 없다. 한글 정품(Windows)은 미검증.
        """
        # 원소는 **부모가 만들게 한다** — 이 골격은 lxml 이라 `ET.SubElement` 를 쓰면
        # "argument 1 must be Element, not lxml.etree._Element" 로 터진다.
        # `makeelement` 는 표준 ET 와 lxml 둘 다 같은 꼴로 갖고 있다.
        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        얼굴들 = 화면이_내장한_글꼴()
        if not 얼굴들:
            return
        표 = self.h.element.find(f"{HH}refList/{HH}fontfaces")
        if 표 is None:
            return
        for ff in 표.findall(f"{HH}fontface"):
            있는것 = {f.get("face") for f in ff.findall(f"{HH}font")}
            다음 = max(int(f.get("id")) for f in ff.findall(f"{HH}font")) + 1
            for 얼굴 in 얼굴들:
                if 얼굴 in 있는것:
                    continue
                e = ff.makeelement(f"{HH}font",
                                   {"id": str(다음), "face": 얼굴,
                                    "type": "TTF", "isEmbedded": "0"})
                e.append(e.makeelement(f"{HH}substFont",
                                       {"face": _대체(얼굴), "type": "TTF",
                                        "isEmbedded": "0"}))
                ff.append(e)
                다음 += 1
            ff.set("fontCnt", str(len(ff.findall(f"{HH}font"))))
        self.h.mark_dirty()

    # ── 글자 ──
    def 글자(self, 서식):
        키 = json.dumps(서식, sort_keys=True, ensure_ascii=False)
        if 키 not in self._글자캐시:
            인자 = dict(size=서식.get("pt") or 11,
                       bold=bool(서식.get("굵게")),
                       italic=bool(서식.get("기울임")),
                       underline=bool(서식.get("밑줄")),
                       strike=bool(서식.get("취소선")),
                       color=_색(서식.get("색")) or "#000000",
                       font=_글꼴(서식.get("글꼴")))
            if _색(서식.get("형광")):
                인자["highlight"] = 서식["형광"]
            # 자간은 **0 일 때도 반드시 넘긴다.** 빼면 `ensure_run` 이 그 속성을
            # "아무 값이나 좋다" 로 보고 **앞서 만든 charPr 를 그대로 돌려준다.**
            # 그래서 자간사냥이 -2% 를 건 줄 다음에 오는 보통 run 까지 -2% 를 물려받아,
            # 한 문단이 통째로 좁아졌다(2026-08-06 보도자료에서 잡음).
            # 글꼴 때와 같은 함정이다 — 이 라이브러리는 **안 준 것을 안 맞춰 준다.**
            인자["letter_spacing"] = int(max(-50, min(100,
                                                     round((서식.get("자간") or 0) * 100))))
            cid = self.h.ensure_char_property and self.d.styles.ensure_run(**인자)
            self._글꼴빈칸(cid)
            self._글자캐시[키] = cid
        return self._글자캐시[키]

    def _글꼴빈칸(self, cid):
        """`useFontSpace="1"` — **글꼴이 정한 글자 너비를 쓴다.**

        기본값 0 이면 한글은 한글 글자를 **정사각(1em) 격자**에 놓는다. Pretendard 의
        한글 글자는 0.863em 이라 그 차이만큼 글자 사이가 벌어져, 같은 글꼴·같은 크기인데도
        한글이 화면보다 **9~12% 넓게** 그린다(2026-08-06 실측 — 한컴 뷰어에서 PDF 로
        인쇄해 크롬 PDF 와 같은 줄을 재서 확인: 129.79→141.79mm, 120.86→131.84mm,
        106.90→119.27mm). 그 9~12% 때문에 판면을 꽉 채운 줄이 전부 한 어절씩 밀리고,
        1p 보고서가 2쪽이 됐다(넘침 시험 표본).
        `ensure_run` 에는 이 인자가 없다 — charPr 를 만든 뒤 직접 켠다.
        """
        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        뭉치 = self.h.element.find(f"{HH}refList/{HH}charProperties")
        if 뭉치 is None:
            return
        for cp in 뭉치:
            if cp.get("id") == str(cid):
                cp.set("useFontSpace", "1")
                self.h.mark_dirty()
                return

    def _민바탕(self):
        """**아무것도 안 그리는** 테두리·배경. 배경 없는 문단이 이걸 명시적으로 가리킨다.

        `ensure_basic_border_fill()` 을 쓰면 안 된다 — 이름과 달리 사방에 `SOLID` 0.12mm
        검정 선을 긋는다(실측). 그걸 썼더니 한글에서 **문단마다 얇은 상자**가 그려졌다.
        `active_borders=()` 로 만들면 네 변이 전부 `NONE` 이다.
        """
        if not hasattr(self, "_민바탕값"):
            self._민바탕값 = self.h.ensure_border_fill(fill_color=None, active_borders=())
        return self._민바탕값

    # OWPML borderFill 의 굵기는 임의값이 아니라 16단계 열거다(한컴 공식 모델
    # enumdef.h LWT_0_1~LWT_5_0 — 2026-08-13 명세 확인). 화면 실측 mm 를 최근접으로
    # 앉힌다. 밖 값을 그대로 실으면 뷰어가 조용히 기본값으로 뭉갠다.
    _괘선굵기단 = (0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5,
               0.6, 0.7, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0)

    # CSS 계산값 → OWPML LineType2. 안 읽으면 목차 점선·점선 박스가 실선이 된다
    # (2026-08-13 CSS 전수 갭 — dashed/dotted 사용처 8곳). double 은 DOUBLE_SLIM
    # (한컴 이중 실선). 모르는 값은 SOLID — 카탈로그 가드가 넷 밖 값을 먼저 세운다.
    _선종류표 = {"solid": "SOLID", "dashed": "DASH",
              "dotted": "DOT", "double": "DOUBLE_SLIM"}

    def _변별괘선(self, 변들, 바탕=None):
        """변마다 굵기·색이 다른 borderFill 을 만들어 id 를 돌려준다.

        왜 raw 인가 — `ensure_border_fill()` 은 활성 변 집합에 **한 스펙**만 건다.
        1p 샌드위치(윗변 0.4 / 아랫변 0.12mm)처럼 변별 위계는 그 길로 못 가고,
        OWPML 은 변마다 독립 Border 자식을 갖는다(leftBorder…bottomBorder).
        라이브러리 원시함수로 원소를 짓고 변 자식만 교정한다 — id 할당·itemCnt 갱신은
        헤더 메서드에 맡긴다(itemCnt 를 손으로 안 고치면 통째 무시되는 함정, §2-4 #2).

        `변들` = {"top"|"right"|"bottom"|"left": {"굵기mm", "색"} 또는 None}.
        스펙이 없는 변은 NONE(안 그림) — 화면에 없는 선은 안 긋는다.
        """
        # ET 를 여기서 다시 import 하지 않는다(래퍼 게이트) — 원소는 원시모듈의
        # 제 ET(_prim.ET)로 짓고, 헤더가 lxml 트리일 때만 아래에서 옮겨 심는다.
        from hwpx.oxml import _document_primitives as _prim
        from lxml import etree as _LET

        def 스냅(mm):
            return min(self._괘선굵기단, key=lambda x: abs(x - float(mm)))

        정규 = {}
        for 변 in ("top", "right", "bottom", "left"):
            s = 변들.get(변)
            정규[변] = ((f"{스냅(s['굵기mm']):g} mm", (s.get("색") or "#000000").upper(),
                       self._선종류표.get(s.get("선종류"), "SOLID")) if s else None)
            # 한글 선 굵기는 16단계라 화면 굵기가 그 사이면 가까운 단으로 옮긴다 — 근사를
            # 숨기지 않는다(P0-6). 0.03mm 안쪽은 화면 측정 흔들림이라 알리지 않는다.
            if s and abs(스냅(s["굵기mm"]) - float(s["굵기mm"])) > 0.03:
                _굵기스냅.add((round(float(s["굵기mm"]), 2), 스냅(s["굵기mm"])))
        키 = json.dumps([정규, 바탕], sort_keys=True, ensure_ascii=False)
        if not hasattr(self, "_괘선캐시"):
            self._괘선캐시 = {}
        if 키 in self._괘선캐시:
            return self._괘선캐시[키]

        통 = self.h._border_fills_element(create=True)
        새id = self.h._allocate_border_fill_id(통)
        bf = _prim._create_border_fill_element(
            새id, border_color="#000000", border_width="0.1 mm",
            fill_color=바탕, active_borders=set(), border_type="SOLID")
        for 변, 자식이름 in _prim._BORDER_SIDE_ELEMENTS.items():
            자식 = bf.find(f"{_prim._HH}{자식이름}")
            spec = 정규[변]
            새속성 = _prim._border_fill_child_attrs(
                active=bool(spec),
                color=spec[1] if spec else "#000000",
                width=spec[0] if spec else "0.1 mm",
                border_type=spec[2] if spec else "SOLID")
            자식.attrib.clear()
            자식.attrib.update(새속성)
        # 헤더가 lxml 트리면 같은 형으로 옮겨 심는다 — ensure_border_fill 과 같은 처리
        if isinstance(통, _LET._Element):
            bf = _LET.fromstring(_prim.ET.tostring(bf, encoding="utf-8"))
        통.append(bf)
        self.h._update_border_fills_item_count(통)
        self.h.mark_dirty()
        self._괘선캐시[키] = 새id
        return 새id

    # ── 문단 ──
    def 바탕서식(self, 서식, *, 띠색=None, 정렬=None):
        """배경·테두리만 든 paraPr 를 만든다. **여백·줄간격은 여기서 안 넣는다.**

        `ensure_paragraph_format(margins=…)` 은 이 골격에서 값이 안 들어간다 —
        margin·lineSpacing 이 `<hp:switch>` 안에 있어 그 함수가 못 닿고, 골격 기본값
        (intent 1400 · left 0 · 줄간격 160)이 그대로 남는다. 2026-08-05 에 이걸 모르고
        모든 문단을 왼여백 0 · 줄간격 160 으로 내보냈다.
        여백·줄간격은 문단을 만든 **뒤에** `styles.apply_paragraph_format` 로 건다
        (실측: 값이 들어가고 배경도 같이 살아남는다).
        """
        # 정렬은 align 이 paraPr **직속 자식**이라 ensure_paragraph_format 이 닿는다
        # (switch 안에 갇힌 여백·줄간격과 다르다 — 라이브러리 소스 확인 2026-08-13).
        # 셀 문단은 doc.paragraphs 에 안 들어와 자리잡기(문단번호) 길이 없으므로,
        # 표() 가 이 인자로 정렬을 심는다. 본문 문단은 종전대로 자리잡기가 건다.
        키 = json.dumps([서식, 띠색, 정렬], sort_keys=True, ensure_ascii=False)
        if 키 in self._문단캐시:
            return self._문단캐시[키]
        인자 = {}
        if 정렬:
            인자["alignment"] = 정렬
        바탕 = 띠색 or _색(서식.get("바탕색"))
        테있음 = [t for t in (서식.get("테두리") or []) if t]
        if not 바탕 and 테있음:
            # **배경 없이 테두리만 있는 상자.** 보도자료 '보 도 자 료' 표제 상자
            # (.pr-kind, border:0.4mm solid #333, 배경 없음)가 이 갈래다. 예전엔
            # "배경이 없으면 무조건 민바탕"(테두리까지 안 그리는 분기) 하나뿐이라
            # 배경 없는 테두리 상자는 표현할 길이 없어 상자째 사라졌다(2026-09-26,
            # 벤치마크 진단 hwpx.findings[4]). _변별괘선() 은 fill_color=None 이면서
            # 변마다 active_borders 만 채운 borderFill 을 표 칸에서 이미 실측으로
            # 쓰고 있다 — 문단 배경에도 그대로 재사용한다(변 없는 쪽은 NONE).
            변들 = dict(zip(("top", "right", "bottom", "left"),
                          서식.get("테두리") or [None] * 4))
            try:
                bf = self._변별괘선(변들, 바탕=None)
                위패딩 = round((서식.get("위안들여mm") or 0) * HU) or 150
                아래패딩 = round((서식.get("아래안들여mm") or 0) * HU) or 150
                인자["border"] = {"borderFillIDRef": bf, "offsetLeft": "300",
                                "offsetRight": "300", "offsetTop": str(위패딩),
                                "offsetBottom": str(아래패딩),
                                "connect": "0", "ignoreMargin": "0"}
            except Exception as e:
                알려진차이.append(f"배경 없는 테두리를 못 넣었다 — {type(e).__name__}")
        elif not 바탕:
            # **배경이 없다는 것도 명시해야 한다.** 문단모양을 안 주면 앞 문단 것을
            # 물려받아, 제목 위 청색 막대가 제목·작성자까지 파랗게 칠하고 요약박스
            # 회색이 다음 절까지 물었다(2026-08-05 한글 뷰어로 직접 보고 알았다 —
            # 값 대조는 통과했다. **재는 것만으로는 못 보는 것이 있다**).
            try:
                인자["border"] = {"borderFillIDRef": self._민바탕(), "offsetLeft": "0",
                                "offsetRight": "0", "offsetTop": "0", "offsetBottom": "0",
                                "connect": "0", "ignoreMargin": "0"}
            except Exception:
                pass
        if 바탕:
            테 = [t for t in (서식.get("테두리") or []) if t]
            try:
                if 테:
                    # **채움 + 테두리도 변마다 따로 싣는다(P0-2).** 예전엔 첫 변 하나를 네 변에
                    # 걸어, 화면이 위·아래 줄뿐인 회색 장 띠(사내표준형 .fr-chapter: 채움
                    # #EFEFEF + 위아래 0.4mm)가 한글에서 **사방 상자**가 됐고, 정부부처형 장
                    # 띠(위 1.1·아래 0.3mm)는 사방 1.06mm 상자가 됐다('26-09-28 실측).
                    # _변별괘선() 은 채움(fill_color)을 이미 받는다 — 배경 없는 테두리 갈래와
                    # 같은 길로 보낸다. 굵기도 여기서 16단계로 스냅된다(예전엔 '0.26 mm' 처럼
                    # 단 밖 값을 그대로 실었다).
                    변들 = dict(zip(("top", "right", "bottom", "left"),
                                  서식.get("테두리") or [None] * 4))
                    bf = self._변별괘선(변들, 바탕=바탕)
                else:
                    bf = self.h.ensure_border_fill(
                        fill_color=바탕, border_color=바탕, border_width="0.12 mm",
                        border_type="SOLID", active_borders=())
                # 세로 안쪽 여백(패딩)을 offset 으로 못 박는다 — 요약박스 2.6mm 같은
                # 박스 키가 화면과 같아진다(2026-08-14 육안 실측 수리). 없으면 종전 150HU.
                위패딩 = round((서식.get("위안들여mm") or 0) * HU) or 150
                아래패딩 = round((서식.get("아래안들여mm") or 0) * HU) or 150
                인자["border"] = {"borderFillIDRef": bf, "offsetLeft": "300",
                                "offsetRight": "300", "offsetTop": str(위패딩),
                                "offsetBottom": str(아래패딩),
                                "connect": "0", "ignoreMargin": "0"}
            except Exception as e:
                알려진차이.append(f"문단 배경({바탕})을 못 넣었다 — {type(e).__name__}")
        pid = self.h.ensure_paragraph_format(**인자)
        # 화면이 어절을 안 쪼개기로 한 문단(word-break: keep-all)은 HWPX 도 안 쪼갠다.
        # `ensure_paragraph_format(break_setting=…)` 로는 **안 된다** — 그 함수는
        # keepWithNext·keepLines·pageBreakBefore·widowOrphan 네 개만 다루고
        # breakNonLatinWord 는 아예 모른다(6.0.2 소스 확인). 그래서 만든 직후 직접 박는다.
        # 안전한 이유: ensure_paragraph_format 은 부를 때마다 **새 문단모양**을 만들고
        # itemCnt 도 갱신한다(공유하지 않는다). 그리고 이 값은 뒤이은
        # apply_paragraph_format 을 거쳐도 살아남는다(실측 — 테두리와 같다).
        # **값 이름이 뒤집혀 있다**('26-09-29 적대 검토 M1): 한글의 '어절' 줄 나눔은 breakNonLatinWord=
        # "BREAK_WORD", '글자'(한글 기본값)는 "KEEP_WORD" 다. 근거 셋 — 한컴 뷰어(맥) 통제 실험 두 방향(격자 칸
        # KEEP→BREAK 로 바꾸면 어절 중간 끊김 4/10 → 0/10, 1p 본문 BREAK→KEEP 로 바꾸면 글자에서 끊김), kordoc
        # index.d.ts 문단 줄바꿈 문서('어절 단위 = BREAK_WORD, 이름 역전 주의 · 글자 단위 = KEEP_WORD 한글 기본값'),
        # 대조.py '줄바꿈 위치' 실측(BREAK_WORD 문단이 한글에서 어절 끝에서 갈림). 예전엔 keep-all → KEEP_WORD 로
        # 옮겨 어절을 지키려던 칸·본문이 한글에서 오히려 글자 단위로 끊겼다. 화면 normal 문단도 자간 사냥
        # (jachigan.js)이 어절 분리를 막으므로 둘 다 어절(BREAK_WORD)이다. Windows 한글에서는 아직 안 봤다.
        self._어절분리(pid, "BREAK_WORD")   # 어절분리 keep·break 둘 다 한글 '어절'
        self._문단캐시[키] = pid
        return pid

    def _어절분리(self, pid, 값):
        try:
            HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
            뭉치 = self.h._para_properties_element(create=True)
            el = next((e for e in 뭉치.findall(f"{HH}paraPr")
                       if e.get("id") == str(pid)), None)
            if el is None:
                raise LookupError(pid)
            bs = el.find(f"{HH}breakSetting")
            if bs is None:
                # **원소는 부모가 만들게 한다** — `_글꼴표_늘리기` 와 같은 이유다. 이
                # 골격은 lxml 이라 표준 `xml.etree.ElementTree.SubElement` 를 쓰면
                # "argument 1 must be Element, not lxml.etree._Element" 로 터진다.
                # 지금까지 이 가지가 안 걸린 건 골격 기본 paraPr 에 breakSetting 이
                # 이미 있어서였을 뿐이다(2026-08-07 WP-H4 로 발견 — 잠복한 함정이었다,
                # 실제 실행에선 한 번도 안 밟혔지만 밟혔다면 TypeError 로 죽는다).
                bs = el.makeelement(f"{HH}breakSetting", {})
                el.append(bs)
            bs.set("breakNonLatinWord", 값)
            self.h.mark_dirty()
        except Exception as e:
            알려진차이.append(f"어절분리({값})를 못 넣었다 — {type(e).__name__}")

    def 자리잡기(self, 문단번호, 서식):
        """만들어 둔 문단에 여백·줄간격·정렬을 건다. **값이 실제로 들어가는 유일한 길이다.**"""
        try:
            self.d.styles.apply_paragraph_format(
                paragraph_index=문단번호,
                alignment=_정렬표.get(서식.get("정렬"), "LEFT"),
                line_spacing_percent=int(서식.get("줄간격") or 160),
                indent_left_mm=round(서식.get("왼여백mm") or 0, 2),
                # 가운데 상자(역할.문단서식 — 판면보다 좁은 가운데 정렬 문단)는 역할이 이미
                # 대칭 구간의 오른여백을 셈해 실어 보낸다. 없으면 예전 길(테두리 상자 역산).
                indent_right_mm=(round(서식["오른여백mm"], 2)
                                 if 서식.get("오른여백mm") is not None
                                 else self._상자오른여백(서식)),
                first_line_indent_mm=round(서식.get("내어쓰기mm") or 0, 2),
                spacing_before_pt=round((서식.get("위여백mm") or 0) * 72 / 25.4, 1),
                spacing_after_pt=round((서식.get("아래여백mm") or 0) * 72 / 25.4, 1),
                # **반드시 꺼서 넘긴다.** 안 주면 라이브러리가 "나머지가 같은" 기존
                # 문단모양을 재활용하는데, 쪽나눔용 모양이 거기 걸려서 보통 문단까지
                # 쪽을 넘긴다. 2026-08-05 풀보고서 쪽나눔이 8번 → **31번**이 됐다.
                page_break_before=False)
            self._줄높이못박기(문단번호, 서식)
        except Exception as e:
            알려진차이.append(f"문단 자리를 못 잡았다 — {type(e).__name__}")

    def _상자오른여백(self, 서식):
        """**배경 없이 테두리만 있는 좁은 상자**의 hc:right 를 역산한다.

        한글 문단 테두리(ignoreMargin=0)는 왼·오른 여백 사이 **전체**에 그려진다 —
        글자 폭과 무관하다. 보도자료 '보 도 자 료' 표제(50mm)·gov 목차 제목(42mm)·
        gov 표지 점선 태그(35mm)처럼 좁은 가운데 상자에 오른여백 0을 그대로 두면
        틀이 판면 오른끝까지 늘어난 큰 상자가 된다(2026-09-26/27, r2 벤치마크 진단
        hwpx.findings[1], H1). 화면에서 잰 상자 폭(상자폭mm)과 판면 폭이 있으면
        오른여백 = 판면폭 - (왼여백 + 상자폭) 으로 못 박아 상자를 그 폭에 맞춘다.

        배경이 있는 상자(요약박스 등)는 손대지 않는다 — 그쪽은 이미 화면과 같이
        나온다(그 폭이 곧 화면 상자 폭이라 왼→오른 전체가 배경으로 칠해져야 맞다).
        5mm 미만 차이는 서브픽셀 실측 흔들림으로 보고 건드리지 않는다(오탐 방지 —
        본래 판면 폭에 가까운 의도된 전폭 테두리까지 좁히지 않는다).
        """
        if 서식.get("바탕색") or not any(서식.get("테두리") or []):
            return None
        상자폭 = 서식.get("상자폭mm")
        판면폭 = getattr(self, "판면폭mm", None)
        왼 = 서식.get("왼여백mm") or 0
        if not 상자폭 or not 판면폭:
            return None
        오른 = round(판면폭 - (왼 + 상자폭), 2)
        if 오른 <= 5:            # 이미 전폭에 가깝다 — 건드리지 않는다
            return None
        return 오른

    def _줄높이못박기(self, 문단번호, 서식):
        """줄 간격을 **화면에서 잰 높이(mm)로 못 박는다** — PERCENT 로는 못 맞춘다.

        한글의 `줄간격 %` 는 글자 크기가 아니라 **글꼴이 정한 줄 높이** 기준이라,
        같은 160% 라도 화면보다 벌어진다. 2026-08-06 실측(a2-03-plan, 13pt 문단):
            화면 7.41mm  ·  한글 7.87mm  ← 6.2% 더 벌어진다
        28줄짜리 1p 보고서가 그 6.2% 때문에 한 줄을 못 담고 2쪽이 됐다.
        `FIXED` + `HWPUNIT` 로 주면 글꼴에 안 흔들리고 화면 값이 그대로 간다.

        **표·그림을 담은 문단에는 걸지 않는다.** 줄 높이가 고정되면 표가 그 안에
        안 들어가 **뒤 문단과 겹쳐 그려진다**(그렇게 해 보고 겹치는 것을 봤다).
        """
        높이mm = 서식.get("줄높이mm")
        if not 높이mm or 서식.get("표있음"):
            return
        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        p = self.d.paragraphs[문단번호]
        pid = p.para_pr_id_ref
        뭉치 = self.h.element.find(f"{HH}refList/{HH}paraProperties")
        if 뭉치 is None:
            return
        for pp in 뭉치:
            if pp.get("id") != str(pid):
                continue
            for ls in pp.iter():
                if ls.tag.endswith("}lineSpacing"):
                    ls.set("type", "FIXED")
                    ls.set("value", str(round(높이mm * HU)))
                    ls.set("unit", "HWPUNIT")
            self.h.mark_dirty()
            return

    def 문단(self, 명):
        서식 = 명.get("문단") or {}
        조각 = list(명.get("조각") or [])
        마커 = 명.get("마커")
        글머리로 = bool(마커) and not 명.get("마커가_글자냐")
        if 마커 and not 글머리로:
            # DOM 안의 진짜 글자였던 마커(보도자료·규정)는 글자 그대로 넣는다.
            # **공백을 여기서 지어 붙이지 않는다.** 예전엔 무조건 "마커 + ' '" 로
            # 넣어, 원본에 공백이 없던 자리(규정 '제1조(목적)' — mk 스팬 바로 뒤에
            # '(' 가 공백 없이 붙는다, assemble_regulation.py)까지 벌어져
            # '제1조 (목적)' 이 됐다(2026-09-26, 벤치마크 진단 hwpx.findings[2]).
            # 화면에 실제로 있던 구분 공백(NBSP)은 화면읽기.속읽기() 가 이미 조각으로
            # 실어 온다(같은 진단 hwpx.findings[3] 필터 완화) — 여기서 또 더하면
            # 두 번 벌어진다. 마커 뒤에 정말 공백이 없던 자리는 그대로 붙어야 맞다.
            # 마커 제 서식이 있으면 그것을 쓴다(P0-4 — 규정 '제1조' 는 굵고, 뒤따르는 첫
            # 조각 '(' 는 보통이다). 없으면(옛 트리) 예전처럼 첫 글 조각의 서식을 입힌다.
            첫 = next((x for x in 조각 if x.get("글")), {"pt": 서식.get("pt")})
            마커꼴 = 명.get("마커서식") or {k: v for k, v in 첫.items() if k != "글"}
            조각.insert(0, {**마커꼴, "글": 마커})
        if not 조각:
            조각 = [{"글": "", "pt": 11}]

        pid = self.바탕서식(서식)
        첫글 = next((x for x in 조각 if x.get("글")), None)
        p = self.d.add_paragraph("", para_pr_id_ref=pid)
        for x in 조각:
            if x.get("줄바꿈"):
                p.add_run("\n", char_pr_id_ref=self.글자({"pt": 11}))
                continue
            if x.get("빈자리mm"):
                # 유령 라벨(visibility:hidden) — 화면에서 자리만 차지하던 것.
                # 글자는 가짜지만 **자리는 진짜다.** 전각공백으로 폭을 맞춘다.
                p.add_run("　" * max(1, int(round(x["빈자리mm"] / 3.5))),
                          char_pr_id_ref=self.글자({"pt": x.get("pt") or 11}))
                continue
            if not x.get("글"):
                continue
            p.add_run(x["글"], char_pr_id_ref=self.글자(x))
        # 여백·줄간격·정렬은 **문단을 만든 뒤에** 건다 — 위 바탕서식 주석 참고
        self.자리잡기(len(self.d.paragraphs) - 1, 서식)
        if 글머리로:
            try:
                self.d.set_list_format(paragraph_index=len(self.d.paragraphs) - 1,
                                       kind="bullet", level=1, bullet_char=마커)
            except Exception:
                # 못 넣으면 글자로라도 넣는다 — 마커가 사라지는 게 제일 나쁘다
                p.add_run(마커 + " ", char_pr_id_ref=self.글자(첫글 or {"pt": 11}))
                알려진차이.append(f"글머리표 '{마커}' 를 목록 서식으로 못 넣어 글자로 넣었다")
        return p

    def 띠(self, 명):
        """글이 없고 배경만 있는 막대 — 1p 제목 위아래 청색 바, 시행문 회색 띠.

        높이는 **화면에서 잰 mm 값을 줄 높이로 그대로 못 박는다**(FIXED·HWPUNIT).
        예전엔 글자 크기(pt = 높이mm×2.8 근사) + 줄간격 PERCENT 100 조합으로 높이를
        흉내 냈을 뿐, 문단 실제 높이를 아무것도 못 박지 않았다 — PERCENT 줄간격은
        글꼴이 정한 줄 높이 기준이라 화면보다 벌어지는 것이 이 코드베이스가 이미
        여러 번 실측한 결함이다(_줄높이못박기 주석 참고, 본문 문단은 이미 FIXED 로
        못박는데 띠만 빠져 있었다). 위·아래 여백이 0 이라 바로 붙는 제목 문단과의
        경계가 화면과 달라지면 제목 글자 윗부분이 띠에 가려 보일 수 있다(2026-09-26,
        벤치마크 진단 hwpx.findings[7] — 원인 추정, 한컴 뷰어 육안 확인 전까지는
        미확인으로 남긴다. add_run 의 pt 근사값은 그대로 둔다 — 글자 자체의 세로
        크기이지 문단 줄 높이가 아니라 이 못박기와 겹치지 않는다).
        """
        높이mm = 명.get("높이mm") or 1.0
        띠서식 = {"줄간격": 100, "왼여백mm": 0, "위여백mm": 0, "아래여백mm": 0,
                 "줄높이mm": 높이mm}
        pid = self.바탕서식(띠서식, 띠색=명.get("바탕색"))
        p = self.d.add_paragraph("", para_pr_id_ref=pid)
        self.자리잡기(len(self.d.paragraphs) - 1, 띠서식)
        # **빈칸**(배경 없는 빈 띠 — 역할._세로배치옮기기·_띠여백빼기 가 쪽 안 세로 빈칸을
        # 채우려고 끼운다)은 글자를 1pt 로 둔다. 높이는 위 FIXED 줄 높이가 정한다 — 글자를
        # 높이에 맞춰 키우면(예전 띠 근사 높이mm×2.8pt) 40mm 빈칸에 112pt 글자가 들어가
        # 편집할 때 커서가 거대해지고, 글자 키가 줄 높이보다 크면 뷰어가 줄을 늘릴 수 있다.
        크기 = 1 if 명.get("빈칸") else max(2, round(높이mm * 2.8, 1))
        p.add_run(" ", char_pr_id_ref=self.글자({"pt": 크기}))
        return p

    def 표(self, 명):
        행들 = 명["행"]
        nr = len(행들)
        nc = max(sum(c.get("가로병합", 1) for c in r["칸"]) for r in 행들)
        # 표 폭을 **반드시** 준다. 안 주면 `set_column_widths` 가 값을 **비율**로만 쓰고
        # 표를 판면 폭까지 늘린다 — 39.5mm 짜리 결재란이 170mm 로 벌어졌다(2026-08-05 실측).
        # 폭을 주면 같은 값이 절대 치수로 들어간다(16.84mm → 16.82mm).
        폭 = 명.get("폭mm")
        # 괘선 없는 표 — 화면의 grid 칸을 옮긴 것이라 선을 그으면 안 된다
        테없음 = self._민바탕() if 명.get("괘선없음") else None
        # add_table() 은 앵커 문단을 새로 하나 만든다(python-hwpx 6.0.2, "in a neutral new
        # paragraph") — 그 문단이 이 표의 자리를 정한다. 미리 색인을 잡아 뒤에서
        # 자리잡기() 를 걸 수 있게 한다.
        앵커 = len(self.d.paragraphs)
        t = (self.d.add_table(nr, nc, width=round(폭 * HU), border_fill_id_ref=테없음) if 폭
             else self.d.add_table(nr, nc, border_fill_id_ref=테없음))
        # 역할._가로줄()·_테두리박스() 가 컨테이너 자신의 왼여백+안들여(예: 풀버전 목차
        # 절 행의 8mm)를 실어 보낸 자리 — 표 앵커 문단에 걸어야 표가 그만큼 오른쪽에서
        # 시작한다(2026-09-26/27, r2 벤치마크 진단 hwpx.findings[2]).
        #
        # **0 도 값이다 — `is not None` 으로 본다.** `if 컨왼:` 이던 옛 코드는 컨왼이
        # 정확히 0mm(가로줄 장(ch) 행처럼 컨테이너가 판면 왼끝에 붙은 경우, gov 태그처럼
        # 화면 왼쪽 끝에 붙은 테두리박스)일 때 이 블록을 통째로 건너뛰어, 그 행만 골격
        # 기본 문단모양(PERCENT 160·JUSTIFY)에 남고 이웃 행은 PERCENT 100·LEFT가 되는
        # 뒤섞임을 냈다 — 장 묶음 사이 간격(원 문단의 위·아래 여백)도 그 갈래에서만
        # 살아, 다른 행은 그대로 0으로 굳었다(3차 수정, "목차 표 앵커" low 결함 +
        # still_partly[4] 재확인). **위·아래 여백도 하드코딩 0을 버리고** 컨테이너
        # 자신이 잰 위·아래 여백(명.위여백mm/아래여백mm — 가로줄()·테두리박스()가
        # 마디 자신의 CSS margin-top/bottom을 그대로 실어 보낸다)을 쓴다 — 표가 문단이
        # 아니라 여백겹치기() 를 안 타므로, 컨테이너가 잰 값을 그대로 앵커에 옮기는 것이
        # 유일하게 화면과 같아지는 길이다.
        컨왼 = 명.get("컨왼여백mm")
        if 컨왼 is not None:
            try:
                self.자리잡기(앵커, {"정렬": "left", "줄간격": 100, "왼여백mm": 컨왼,
                                "내어쓰기mm": 0,
                                "위여백mm": 명.get("위여백mm") or 0,
                                "아래여백mm": 명.get("아래여백mm") or 0})
            except Exception as e:
                알려진차이.append(f"표 컨테이너 왼여백을 못 걸었다 — {type(e).__name__}")
        elif not self._흐르는표(명) and 명.get("정렬") in ("CENTER", "RIGHT"):
            # 판면보다 좁은 가운데·오른쪽 표('26-09-29 표 재설계 P1, critic_impl #13) — 화면읽기가
            # 기하로 잰 정렬을 앵커 문단 정렬로 건다(글자처럼 취급한 표는 문단 정렬을 따른다).
            # 예전엔 표 정렬을 아무도 안 걸어 가운데 표가 한글에서 왼쪽에 붙었다(실측 F6).
            try:
                self.자리잡기(앵커, {"정렬": 명["정렬"], "줄간격": 100, "왼여백mm": 0,
                                "내어쓰기mm": 0, "위여백mm": 0, "아래여백mm": 0})
            except Exception as e:
                알려진차이.append(f"표 정렬을 못 걸었다 — {type(e).__name__}")
        self._표채우기(t, 명)
        if 컨왼 is None and self._흐르는표(명):
            self._흐르게(t, 명)
        return t

    # 흐르는 장르 — 쪽 나눔을 한글에 맡기는 장르(보도자료·규정·시행문). 풀버전·1p 는 화면이 쪽을
    # 정해 표를 통째로 옮기므로(조판기가 블록을 안 쪼갠다) 글자처럼 취급을 그대로 둔다.
    _흐르는장르 = ("press-release", "regulation", "gongmun")

    def _흐르는표(self, 명):
        """자료 표(역할 표·개요표)이고 흐르는 장르인가 — 배치용 표(괘선없음)·서식 표(담당·보도시점)는 뺀다."""
        return (self._장르 in self._흐르는장르 and 명.get("역할") in ("표", "개요표")
                and not 명.get("괘선없음"))

    def _흐르게(self, t, 명):
        """흐르는 장르의 자료 표를 쪽을 넘어 나뉠 수 있게 한다('26-09-29 표 재설계 P1, critic_impl #12).

        글자처럼 취급(treatAsChar=1, python-hwpx 기본)한 표는 한 줄 안 개체라 여러 쪽으로 못 나뉜다
        (한컴 도움말). treatAsChar=0 + 본문과 위아래 배치(textWrap TOP_AND_BOTTOM, 기본) + 셀 단위
        나눔(pageBreak CELL, 기본)으로 두고, 머리 행 칸에 header=1 을 걸어 다음 쪽에 머리 행이 되풀이
        되게(repeatHeader=1) 한다. 가로 자리는 화면에서 잰 정렬을 단(COLUMN) 기준으로 건다.
        """
        _HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
        try:
            el = t.element
            pos = el.find(f"{_HP}pos")
            if pos is not None:
                pos.set("treatAsChar", "0")
                pos.set("horzAlign", {"CENTER": "CENTER", "RIGHT": "RIGHT"}.get(명.get("정렬"), "LEFT"))
            # 떠 있는 표 뒤 글이 표 아래 선을 덮는다(적대 검토 H1 '26-09-29, 한컴 뷰어 보도·시행문·규정 캡처).
            # 글자처럼 취급한 표는 앵커 줄이 틈을 만들었는데, 떠 있으면 다음 줄이 표 아랫변에 바로 붙는다.
            # 같은 파일에서 바깥 아래 여백 3mm(850HU)만 준 통제 실험이 겹침을 없앴다 — 그 값을 건다
            # (화면의 표 아래 틈은 장르 그릇 여백 1.5~4mm 다). 이미 더 크면 그대로 둔다.
            om = el.find(f"{_HP}outMargin")
            if om is not None:
                try:
                    om.set("bottom", str(max(int(om.get("bottom") or 0), 850)))
                except ValueError:
                    om.set("bottom", "850")
            머리행 = 0
            for r in 명["행"]:
                if r["칸"] and all(c.get("머리칸") for c in r["칸"]):
                    머리행 += 1
                else:
                    break
            if 머리행:
                el.set("repeatHeader", "1")
                for ri, tr in enumerate(el.findall(f"{_HP}tr")):
                    if ri >= 머리행:
                        break
                    for tc in tr.findall(f"{_HP}tc"):
                        tc.set("header", "1")
        except Exception as e:
            알려진차이.append(f"표를 쪽 넘김 가능하게 못 바꿨다 — {type(e).__name__}")

    def _표채우기(self, t, 명):
        """만들어 둔 표(본문 표든 배치용 표 칸 안의 표든)에 열 폭·칸 글·괘선·병합을 건다.

        표() 가 앵커 문단과 함께 표를 만든 뒤, 나란히() 는 칸 문단 안에 표를 만든 뒤 여기를
        부른다 — 칸을 채우는 규칙은 한 곳에만 둔다(둘로 갈리면 반드시 어긋난다).
        """
        행들 = 명["행"]
        nc = max(sum(c.get("가로병합", 1) for c in r["칸"]) for r in 행들)
        너비 = [None] * nc
        for r in 행들:
            ci = 0
            for c in r["칸"]:
                g = c.get("가로병합", 1)
                if g == 1 and 너비[ci] is None and c.get("폭mm"):
                    너비[ci] = c["폭mm"]
                ci += g
        if all(x for x in 너비):
            try:
                t.set_column_widths([round(x * HU) for x in 너비])
            except Exception as e:
                알려진차이.append(f"표 열너비를 못 넣었다 — {type(e).__name__}")
        병합할것 = []
        for ri, r in enumerate(행들):
            ci = 0
            for c in r["칸"]:
                # 역할이 점유 그리드로 계산한 **진짜 열 번호**를 신뢰한다. 목록 순번을
                # 그대로 쓰면 세로병합이 덮은 열을 안 건너뛰어 행1 셀들이 왼쪽으로
                # 밀려 쓰이고, 진짜 마지막 열은 손대지 않은 기본 셀로 남는다
                # (2026-08-14 괘선 대조 축이 잡은 잠복 결함 — 빈 서명란이라
                # 글자·음영 검사는 못 봤다).
                if c.get("열") is not None:
                    ci = c["열"]
                if ci >= nc:
                    break
                # 셀 글자·문단 서식은 `set_cell_text` 로 못 건다. 그 길로 넣으면 전부
                # 10pt·보통·JUSTIFY 기본값이 된다(2026-08-05 보도자료 실측).
                # 셀 문단은 `doc.paragraphs` 에도 안 들어와 paragraph_index 로도 못 잡는다.
                # 셀의 문단을 직접 만들어 거기에 걸어야 한다.
                칸서식 = {"pt": c.get("pt"), "굵게": c.get("굵게"), "색": c.get("색"),
                        "글꼴": c.get("글꼴")}
                문단인자 = {"정렬": c.get("정렬", "LEFT"), "줄간격": c.get("줄간격") or 145,
                         "왼여백mm": 0, "위여백mm": 0, "아래여백mm": 0,
                         # 칸 keep-all → 칸 문단 KEEP_WORD(바탕서식 → _어절분리). keep 일
                         # 때만 싣는다 — break 는 종전 기본값과 같아 문단모양 캐시 열쇠를
                         # 안 바꾼다('26-09-28 도식 재설계 P0-전제)
                         **({"어절분리": "keep"} if c.get("어절분리") == "keep" else {})}
                try:
                    셀 = t.cell(ri, ci)
                    # 새 셀에는 **이미 빈 문단이 하나 있다.** add_paragraph 로 얹으면
                    # 셀 글이 '\n보도시점' 처럼 앞에 빈 줄이 붙는다(2026-08-05 실측).
                    # 있는 문단에 서식을 걸고 글을 넣는다.
                    cp = 셀.paragraphs[0]
                    # 셀 정렬은 여기서 심는다 — 자리잡기(문단번호) 길이 셀엔 없다
                    # (2026-08-13 육안 실측: 머리칸 가운데 정렬이 왼쪽으로 나갔다)
                    바 = self.바탕서식(문단인자, 정렬=문단인자.get("정렬"))
                    if 바:
                        cp.para_pr_id_ref = 바
                    # **조각**(run 배열) — 역할._테두리박스() 가 배경 없는 테두리 상자를
                    # 1행 1칸 표로 옮기며 실어 보낸다(3차 수정). 문단() 의 조각 걷기와
                    # 같은 규칙(줄바꿈→개행 run, 빈자리mm→전각공백)을 셀에도 그대로
                    # 적용한다 — gov 표지 태그(data-multiline)처럼 상자 글이 여러 줄일
                    # 수 있어서다. 이 키가 없는 보통 표·가로줄 칸은 옛길(단일 "글") 그대로.
                    조각들 = c.get("조각")
                    if 조각들:
                        for x in 조각들:
                            if x.get("줄바꿈"):
                                cp.add_run("\n", char_pr_id_ref=self.글자({"pt": 칸서식.get("pt") or 11}))
                            elif x.get("빈자리mm"):
                                cp.add_run("　" * max(1, int(round(x["빈자리mm"] / 3.5))),
                                           char_pr_id_ref=self.글자({"pt": x.get("pt") or 11}))
                            elif x.get("글"):
                                cp.add_run(x["글"], char_pr_id_ref=self.글자(x))
                    else:
                        cp.add_run(c.get("글") or "", char_pr_id_ref=self.글자(칸서식))
                except Exception:
                    try:
                        t.set_cell_text(ri, ci, c.get("글") or "")
                    except Exception:
                        pass
                    알려진차이.append("표 셀 서식을 못 걸었다 — 기본값으로 나간다")
                # 셀 괘선 — 역할.py 가 실어 온 실측 테두리를 변별로 건다(2026-08-13,
                # 종전엔 이 값을 아무도 안 읽어 모든 표가 라이브러리 기본 괘선으로
                # 나갔다 — _떨어뜨림 '칸·테두리'가 걷힌 자리). 화면읽기 순서는
                # [Top, Right, Bottom, Left]. **음영보다 먼저** 걸어야 한다 —
                # set_cell_shading 은 셀의 현재 borderFill 을 base 로 fill 만 바꾼다.
                # 괘선과 음영을 **한 borderFill 로 함께** 짓는다. 처음엔 괘선을 걸고
                # set_cell_shading 으로 음영을 얹었는데, 그 파생의 중복제거가 변별
                # 테두리를 못 보고 다른 셀 것과 합쳐 — '배포' 칸이 '보도시점' 칸의
                # 변(윗변 유령·아랫변 #999)을 뒤집어썼다(2026-08-14, 새 괘선 대조
                # 축이 잡음: a1-05-press 등 9건). 우리 캐시는 (변들×바탕)이 열쇠라
                # 안 섞인다.
                테 = c.get("테두리")
                바 = _색(c.get("바탕"))
                # 격자 도식(역할 '도식' 표)의 틈 칸·화살 칸은 선도 칠도 없다 — 그냥 두면 라이브러리
                # 기본 괘선(0.12mm 검정)이 그어져 카드 사이 흰 틈에 검은 격자가 생긴다('26-09-29 격자
                # 도식 P2 실측: 화살 칸·전이 칸·틈 칸 전부 SOLID 0.12mm #000000). 도식 칸만 '안 그림'을
                # 명시한다 — 보통 표는 종전 그대로(기존 문서 XML 이 안 바뀐다).
                # 자료 표(역할 표·개요표)도 같다 — 화면에 선도 칠도 없는 칸(모양 '투명표' 전부)이 기본 괘선으로
                # 나가 한글에서 격자선 표가 됐다(적대 검토 H2 '26-09-29: 5장르 92/92 변 SOLID 0.12mm).
                # 겉선은 역할._표 가 가장자리 칸에 접어 오므로 여기서 '안 그림'이면 화면에도 선이 없다.
                if 테 or 바 or 명.get("역할") in ("도식", "표", "개요표"):
                    try:
                        변들 = ({"top": 테[0], "right": 테[1],
                               "bottom": 테[2], "left": 테[3]} if 테 else
                              {"top": None, "right": None,
                               "bottom": None, "left": None})
                        t.cell(ri, ci).element.set(
                            "borderFillIDRef", self._변별괘선(변들, 바탕=바))
                    except Exception as e:
                        알려진차이.append(f"셀 괘선·음영을 못 걸었다 — {type(e).__name__}")
                # 셀 안쪽 여백을 화면에 맞춘다. 기본이 좌우 510 HWPUNIT(1.8mm)씩이라
                # 좁은 라벨 칸에서 글자가 안 들어가 '시행' 이 '시'/'행' 두 줄로 쪼개졌다
                # (2026-08-05 시행문 결문, 한글 뷰어로 직접 보고 알았다).
                # 위·아래 안여백은 격자 도식 칸과 흐르는 장르 자료 표만 건다('26-09-29 표 재설계 P1) —
                # 역할._표 는 늘 싣지만, 1p·풀버전 보통 표는 행 높이를 화면 실측으로 못 박아 여백을
                # 얹으면 한글 줄 높이 차이만큼 행이 자랄 수 있어 종전(0)대로 둔다.
                if not (명.get("역할") == "도식" or self._흐르는표(명)):
                    c = {**c, "위안여백mm": 0, "아래안여백mm": 0}
                try:
                    안 = c.get("안여백mm")
                    셀el = t.cell(ri, ci).element
                    # `hasMargin="0"` 이면 셀 제 여백을 **안 쓰고** 표 기본값을 쓴다.
                    # 그래서 cellMargin 만 고쳐 봐야 소용이 없다 — 켜 줘야 한다
                    # (2026-08-05: 이걸 몰라 '시행' 이 계속 두 줄로 쪼개졌다).
                    셀el.set("hasMargin", "1")
                    for cm in 셀el.iter():
                        if cm.tag.endswith("cellMargin"):
                            for 변 in ("left", "right"):
                                cm.set(변, str(round((안 or 0) * HU)))
                            # 위·아래는 격자 도식 칸만 실어 온다(역할._표, 카드 칸 여백) —
                            # 없으면 종전대로 0('26-09-28 도식 재설계 P0-전제)
                            cm.set("top", str(round((c.get("위안여백mm") or 0) * HU)))
                            cm.set("bottom", str(round((c.get("아래안여백mm") or 0) * HU)))
                except Exception:
                    pass
                if c.get("높이mm"):
                    try:
                        t.cell(ri, ci).set_size(height=round(c["높이mm"] * HU))
                    except Exception:
                        pass
                가로, 세로 = c.get("가로병합", 1), c.get("세로병합", 1)
                if 가로 > 1 or 세로 > 1:
                    병합할것.append((ri, ci, ri + 세로 - 1, ci + 가로 - 1))
                ci += 가로
        for a, b, c2, d2 in 병합할것:          # 병합은 글자를 다 넣은 뒤에 한다
            try:
                t.merge_cells(a, b, c2, d2)
            except Exception as e:
                알려진차이.append(f"셀 병합({a},{b})을 못 했다 — {type(e).__name__}")
        return t

    def 나란히(self, 명):
        """가로로 나란히 앉은 표들(풀버전 표지 [문서정보 표 | 결재 표])을 **한 앵커 문단에
        글자처럼 취급한 표로 차례로** 넣고, 표의 바깥 여백으로 화면 자리를 맞춘다.

        왜 이 방식인가는 역할._나란히묶기 docstring(떠 있는 표·배치용 표 안의 표와 견준
        까닭). 앞 표의 오른 바깥 여백이 다음 표까지의 틈이고, 표마다 위·아래 바깥 여백이
        줄 안에서 제 표가 떨어진 만큼이다 — 칸마다 상자 키가 줄 키와 같아져 한 줄 안
        세로 맞춤(글자처럼 취급한 개체의 기준선 규칙)이 무엇이든 화면 자리 그대로 앉는다.
        표 하나하나는 본문 표와 똑같이 _표채우기() 가 채운다.
        """
        칸들 = 명.get("칸") or []
        if not 칸들:
            return None
        _HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
        앵커 = len(self.d.paragraphs)
        표들 = []
        for k, 칸 in enumerate(칸들):
            속 = 칸.get("명령") or {}
            행들 = 속.get("행") or []
            nr = len(행들)
            nc = max(sum(c.get("가로병합", 1) for c in r["칸"]) for r in 행들)
            인자 = {}
            if 속.get("폭mm"):
                인자["width"] = round(속["폭mm"] * HU)     # 비율로 늘지 않게 절대 치수(표() 와 같다)
            if 속.get("괘선없음"):
                인자["border_fill_id_ref"] = self._민바탕()
            if k == 0:
                # 첫 표가 앵커 문단을 만든다(add_table 은 새 문단을 연다) — 표() 와 같은 길
                t = self.d.add_table(nr, nc, **인자)
                try:
                    self.자리잡기(앵커, {"정렬": "left", "줄간격": 100,
                                    "왼여백mm": 명.get("컨왼여백mm") or 0, "내어쓰기mm": 0,
                                    "위여백mm": 명.get("위여백mm") or 0,
                                    "아래여백mm": 명.get("아래여백mm") or 0})
                except Exception as e:
                    알려진차이.append(f"나란히 표 자리를 못 잡았다 — {type(e).__name__}")
            else:
                # 둘째 표부터는 **같은 문단**에 이어 넣는다 — 글자처럼 한 줄에 앉는다
                t = self.d.paragraphs[앵커].add_table(nr, nc, **인자)
            self._표채우기(t, 속)
            try:
                om = t.element.find(f"{_HP}outMargin")
                if om is not None:
                    om.set("left", "0")
                    om.set("right", str(round((칸.get("오른틈mm") or 0) * HU)))
                    om.set("top", str(round((칸.get("위차mm") or 0) * HU)))
                    om.set("bottom", str(round((칸.get("아래차mm") or 0) * HU)))
            except Exception as e:
                알려진차이.append(f"나란히 표 바깥 여백을 못 걸었다 — {type(e).__name__}")
            표들.append(t)
        return 표들

    def 그림(self, 명):
        """화면에서 찍은 PNG 를 화면에서 잰 mm 크기로 넣는다."""
        import base64
        자료 = 명.get("png")
        if not 자료:
            알려진차이.append("도형을 못 찍어 빈 자리로 뒀다 — 화면과 다르다")
            self.d.add_paragraph("")
            return
        # 그림 정렬은 **명시한다**('26-09-28 도식 재설계 P0). 예전엔 add_picture 가 앞 문단(캡션
        # '< … >')의 문단 모양을 물려받아 가운데로 나왔을 뿐이고(실측: CENTER·줄간격 FIXED 1426HU),
        # 캡션이 없으면 앞 본문(양쪽·160%)을 물려받았다. 화면의 .fr-fig 는 가운데 정렬이다.
        # 줄간격은(고정 줄높이 안의 글자처럼 취급 그림은 뒤 문단과 겹칠 수 있다 — _줄높이못박기 주석).
        정렬 = {"center": "CENTER", "right": "RIGHT", "end": "RIGHT", "left": "LEFT",
                "start": "LEFT", "justify": "CENTER"}.get(str(명.get("정렬") or "center").lower(), "CENTER")
        그림바이트 = base64.b64decode(자료)
        if 명.get("생성"):
            # AI 생성 그림 — 한글 그림 파일(BinData) 안에도 'AI 생성물' 표기(PNG 글 조각)를 심는다(P3 '26-09-30,
            # 주관 판정 '화면 배지 + 그림 파일 안'). 화면에서 다시 찍은 PNG 라 자산의 조각이 따라오지 않았다(P2 0/1).
            try:
                import os as _os
                if _os.path.dirname(_os.path.abspath(__file__)) not in sys.path:
                    sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                import imageasset as _ia
                그림바이트 = _ia.AI표기심기(그림바이트, str(명.get("생성")), "") or 그림바이트
            except Exception as e:
                알려진차이.append(f"AI 생성 그림 파일에 표기를 못 심었다 — {type(e).__name__}")
        try:
            self.d.add_picture(그림바이트, "png",
                               width_mm=round(명.get("폭mm") or 60, 2),
                               height_mm=round(명.get("높이mm") or 40, 2),
                               para_pr_id_ref=self.바탕서식({}))
            self.자리잡기(len(self.d.paragraphs) - 1,
                         {"정렬": 정렬, "줄간격": 100, "왼여백mm": 0, "오른여백mm": 0,
                          "내어쓰기mm": 0, "위여백mm": 0, "아래여백mm": 0})
        except Exception as e:
            알려진차이.append(f"도형을 못 넣었다 — {type(e).__name__}: {str(e)[:60]}")
            self.d.add_paragraph("")
            return
        # 반폭 차트 둘 나란히(svgfig.js 짝 — .fig-pair): 한글에는 한 문단에 그림 둘을 나란히 두는
        # 길을 아직 안 냈다. 반폭 크기 그대로 위아래로 쌓고 알린다(조용히 모양을 바꾸지 않는다).
        # 첨부 사진 쌍(편집기 크기 '작게' 둘 — imageasset.그림짝, P3 '26-09-30)도 같은 짝 클래스를 단다. 그릇이
        # .fr-img 면 그림이라 말한다(critic_impl T7: 나란히 둔 사진 쌍이 알림 없이 쌓였다).
        if "fig-pair" in str(명.get("반") or ""):
            말 = (("나란히 둔 그림(사진) 둘을" if "fr-img" in str(명.get("반") or "") else "나란히 둔 차트 둘을")
                 + " 한글에서는 위아래로 쌓았다(크기는 화면 그대로)")
            if 말 not in 알려진근사:
                알려진근사.append(말)

    def 쪽나눔(self):
        # **화면 규칙이 바뀌는 경계에서만** 구역을 새로 연다 — 쪽마다 열면 문서가
        # 지나치게 잘게 쪼개진다(단순화 방향). self._쪽정보 가 비어 있으면(장르가
        # fullreport 가 아니거나 화면읽기가 옛 스냅샷) 종전과 똑같이 쪽나눔 문단만 쓴다.
        if self._쪽정보 and self._장르 == "fullreport":
            self._쪽카운터 += 1
            정보 = (self._쪽정보[self._쪽카운터 - 1]
                  if len(self._쪽정보) >= self._쪽카운터 else None)
            if 정보 is not None:
                번호숨김 = bool(정보.get("번호숨김"))
                쪽번호 = 정보.get("쪽번호")
                예상 = (self._쪽번호예상 or 0) + 1
                # 구역을 새로 여는 기준 — python-hwpx(=한글 OWPML)가 주는 쪽번호 감춤은
                # **구역의 첫 쪽에만** 걸린다(hideFirstPageNum). 그래서 ① 이 쪽 번호가
                # 화면에서 감춰져 있으면(표지·목차·간지) **늘 새 구역을 열어** 이 쪽을 그
                # 구역의 첫 쪽으로 만든다 — 안 그러면 바로 앞 쪽만 숨겨지고 이 쪽은 안
                # 가려진다(연속 두 쪽 이상 숨김 — 3차 수정 전에는 목차가 이래서 못
                # 가려졌다). ② 화면이 실제로 찍은 번호가 "그냥 이어 세면" 나올 값과
                # 달라졌으면(정부부처형 '본문재시작'·사용자 새번호시작) 새 구역을 열어
                # 그 번호로 다시 시작한다. 둘 다 아니면 물리 쪽수를 그대로 이어 세면
                # 화면과 같다 — 구역을 안 늘린다(단순화 방향).
                바뀜 = (번호숨김
                       or 번호숨김 != self._쪽번호상태.get("번호숨김", False)
                       or (쪽번호 is not None and 쪽번호 != 예상))
                if 바뀜:
                    try:
                        self._새섹션(번호숨김, 쪽번호)
                        self._쪽번호상태 = {"번호숨김": 번호숨김}
                        self._쪽번호예상 = 쪽번호 if 쪽번호 is not None else 예상
                        return
                    except Exception as e:
                        알려진차이.append(f"쪽 번호 구역을 못 나눴다 — {type(e).__name__}")
                self._쪽번호예상 = 예상
        self.d.add_paragraph("")
        try:
            self.d.styles.apply_paragraph_format(
                paragraph_index=len(self.d.paragraphs) - 1, page_break_before=True)
        except Exception as e:
            알려진차이.append(f"쪽나눔을 못 넣었다 — {type(e).__name__}")

    def _새섹션(self, 번호숨김: bool, 쪽번호: int | None):
        """한글 구역(section)을 새로 열고 그 구역에 쪽번호 감춤·재시작을 건다.

        새 구역은 **직전 구역의 용지·여백·꼬리말 필드를 그대로 이어받는다**
        (python-hwpx add_section 이 가장 가까운 구역의 레이아웃을 복제 — 실측: 용지·
        여백이 없으면 add_section 자체가 ValueError 로 거부한다, 그러니 복제가 된다는
        뜻이다). 구역 전환 자체가 새 쪽을 여니 옛 쪽나눔() 처럼 빈 문단+page_break_before
        를 따로 안 둔다 — 대신 add_section 이 만드는 구역의 첫(유령) 문단 색인을
        기억해 두었다가 쓰기() 끝에서 첫 구역의 유령 문단과 똑같이 줄여 준다.
        """
        sec = self.d.add_section()
        self._섹션첫문단들.append(len(self.d.paragraphs) - 1)
        self.d.page.set_page_number(
            target="footer", position="BOTTOM_CENTER", align="CENTER",
            prefix="- ", suffix=" -", format="page", section=sec)
        self.d.page.set_visibility(
            hide_first_page_num=번호숨김, hide_first_footer=번호숨김, section=sec)
        if 쪽번호 is not None:
            sec.properties.set_start_numbering(page=int(쪽번호))

    # ── 요소 자식순서 정본화 (WP-H6 ②) ──
    def 자식순서_정본화(self):
        """저장 직전 한 번 — 머리말의 모든 charPr 와 refList 의 자식순서를 정본으로 되돌린다.

        **오직 순서만** 바꾼다. charPr id·속성값·글꼴·색·pt 는 하나도 안 바뀐다(자식을
        지우고 같은 객체를 다른 차례로 다시 붙일 뿐이다). 그래서 대조.py(값 대조)는 안
        흔들리고 골든대조.py(순서 대조)만 초록으로 돈다.

        실제 로직은 모듈 함수 `머리말_자식순서_정본화()` 에 있다 — 이미 만들어 둔 표본
        .hwpx 를 열어 같은 정본화를 다시 걸 때(WP-H6 표본 갱신)도 그 함수를 그대로 쓰기
        위해서다(한 곳에만 로직을 둔다).
        """
        if 머리말_자식순서_정본화(self.h.element):
            self.h.mark_dirty()


# 화면읽기 근사목록 → 내보내기 결과의 '알려진 차이' 문구(P0-6). 모르는 무엇은 이름 그대로 싣는다.
# 사용자 화면에 그대로 나가는 문구다 — CSS 반 이름을 싣지 않고 자리를 사람 말로 적는다.
_근사말 = {
    "그라데이션": "그라데이션 바탕은 첫 색 하나로 칠했습니다(한글 문단 바탕은 단색만 됩니다)",
    "번호칩": "절 번호 상자는 표 칸으로 옮겼습니다. 한글에서는 상자가 줄 높이만큼 칠해집니다",
    "번호칩두줄": "두 줄짜리 절 제목은 한글에서는 제목 칸 안에서 줄이 바뀝니다(화면에서는 둘째 줄이 번호 아래로 갑니다)",
    "글자음영상자": "색칠한 글자 상자는 글자 음영으로 옮겼습니다. 상자 여백과 폭은 빠집니다",
}
# 근사가 일어난 자리 — 화면읽기가 넘기는 반(CSS class) 토큰을 사람 말로. 모르는 토큰은 싣지 않는다.
_자리말 = {"fr-chapter": "장 제목 띠", "gov-bar": "제목 띠", "fr-sec": "절 제목",
         # 제목 모양('26-09-28) — 사내표준형 표지 띠·참고자료 제목도 같은 근사를 탄다
         "fr-tt-bar": "제목 띠", "fr-annex-title": "참고자료 제목"}


def _근사알리기(근사들):
    묶음: dict[str, set] = {}
    for x in 근사들 or []:
        반 = x.get("반") or ""
        자리 = next((말 for 토큰, 말 in _자리말.items() if 토큰 in 반.split()), None)
        묶음.setdefault(x.get("무엇") or "?", set()).update({자리} if 자리 else set())
    for 무엇, 자리들 in sorted(묶음.items()):
        말 = _근사말.get(무엇, 무엇)
        알려진근사.append(f"{말} ({', '.join(sorted(자리들))})" if 자리들 else 말)


def _굵기스냅말():
    if not _굵기스냅:
        return None
    짝 = ", ".join(f"{a:g}→{b:g}mm" for a, b in sorted(_굵기스냅))
    return f"선 굵기는 한글이 지원하는 16단계 중 가장 가까운 값으로 옮겼습니다({짝})"


def 알림순서(실패들, 근사들) -> list[str]:
    """실패(못 넣었다)를 먼저, 근사를 뒤에 — 앞 몇 건만 싣는 자리(tohwpx)에서 실패가 안 잘리게."""
    근 = list(dict.fromkeys(근사들))
    return sorted(set(실패들) - set(근)) + 근


def 쓰기(꾸러미: dict, 나갈곳: str) -> dict:
    알려진근사.clear()          # 근사는 이 문서 몫만 — 한 프로세스에서 여러 번 불러도 안 쌓인다
    _굵기스냅.clear()
    _근사알리기((꾸러미.get("문서") or {}).get("근사"))
    b = 붓(꾸러미["문서"])
    센것: dict[str, int] = {}
    for 명 in 꾸러미["명령"]:
        k = 명["종류"]
        함수 = {"문단": b.문단, "표": b.표, "띠": b.띠, "그림": b.그림,
              "나란히": b.나란히}.get(k)
        if 함수:
            함수(명)
        elif k == "쪽나눔":
            b.쪽나눔()
        else:
            알려진차이.append(f"모르는 명령 '{k}' 를 건너뛰었다")
            continue
        센것[k] = 센것.get(k, 0) + 1

    # 골격의 첫 문단은 secPr 을 지녀 못 지우는데, 화면에 없는 **유령 빈 줄** 하나로
    # 렌더된다(2026-08-14 육안 3라운드 — 캐럿 'I' 자리. 빈 문단이라 글자·띠·대조
    # 어디에도 안 잡혔다). 표 앵커 센티널과 같은 수(≈120HU)로 줄 키를 못 박아
    # 지운 것처럼 만든다. 첫 명령이 이미 이 문단을 채웠으면 건드리지 않는다.
    #
    # **구역(section)마다 이 유령 줄이 하나씩 더 생긴다** — add_section() 이 새 구역을
    # 열 때도 골격과 똑같이 secPr 을 지닌 빈 문단 하나를 먼저 만든다(3차 수정, 쪽번호
    # 구역 나누기가 쓰는 _새섹션() 참고). b._섹션첫문단들 이 그 색인들을 모아 둔다
    # (첫 구역의 0 을 포함) — 전부 같은 방식으로 줄인다.
    for idx in b._섹션첫문단들:
        try:
            if not (b.d.paragraphs[idx].text or "").strip():
                b.자리잡기(idx, {"정렬": "left", "줄간격": 100, "왼여백mm": 0,
                            "내어쓰기mm": 0, "위여백mm": 0, "아래여백mm": 0,
                            "줄높이mm": 0.42})
        except Exception as e:                                    # noqa: BLE001
            알려진차이.append(f"구역 첫 유령 줄을 못 줄였다 — {type(e).__name__}")

    # 요소 자식순서 정본화 — python-hwpx 가 charPr 토글(bold·underline 등)을 끝에 붙여
    # outline·shadow 뒤로 민 것, refList 의 bullets 가 styles 뒤로 간 것을 저장 직전에
    # 정본 자리로 되돌린다(WP-H6 ②). 순서만 바꾸고 값은 안 바꾼다.
    b.자식순서_정본화()

    # 문서 메타(작성자·작성일)와 미리보기 글 — 골격이 박아 둔 가짜 값·빈 미리보기를
    # 내보내는 시점에 실제 값으로 채운다(mcp s2·s5 결함). 스키마 검증·저장보다 앞서
    # 두어, 이 손보기가 실패해도(알려진차이 에만 남기고) 문서 자체는 그대로 나간다.
    _문서메타손보기(b.d)
    try:
        b.d.package.set_part("Preview/PrvText.txt",
                            _미리보기텍스트(꾸러미.get("지면글") or "").encode("utf-8"))
    except Exception as e:
        알려진차이.append(f"미리보기 글을 못 채웠다 — {type(e).__name__}")

    try:
        r = b.d.validate()
        나쁨 = [str(x)[:160] for x in (list(getattr(r, "errors", None) or []))][:8]
    except Exception as e:
        나쁨 = [f"검증을 못 돌렸다: {type(e).__name__}"]
    b.d.save_to_path(나갈곳)
    스냅말 = _굵기스냅말()
    근사들 = 알려진근사 + ([스냅말] if 스냅말 else [])
    return {"센것": 센것, "스키마문제": 나쁨, "알려진차이": 알림순서(알려진차이, 근사들),
            "근사수": len(set(근사들))}


if __name__ == "__main__":
    print(json.dumps(쓰기(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2]),
                     ensure_ascii=False))
