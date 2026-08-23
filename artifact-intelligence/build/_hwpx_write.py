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

from hwpx.document import HwpxDocument

HU = 283.465          # 1mm 당 HWPUNIT
알려진차이: list[str] = []

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
        1p 보고서가 2쪽이 됐다(a5-14-overflow).
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
        if not 바탕:
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
            선색 = 테[0]["색"] if 테 else None
            굵기 = f'{테[0]["굵기mm"]:.2f} mm' if 테 else "0.12 mm"
            try:
                bf = self.h.ensure_border_fill(
                    fill_color=바탕, border_color=선색 or 바탕, border_width=굵기,
                    border_type=self._선종류표.get(
                        테[0].get("선종류") if 테 else None, "SOLID"),
                    active_borders=("left", "right", "top", "bottom") if 선색 else ())
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
        self._어절분리(pid, "KEEP_WORD" if 서식.get("어절분리") == "keep" else "BREAK_WORD")
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
            첫 = next((x for x in 조각 if x.get("글")), {"pt": 서식.get("pt")})
            조각.insert(0, {**{k: v for k, v in 첫.items() if k != "글"}, "글": 마커 + " "})
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
        """글이 없고 배경만 있는 막대 — 1p 제목 위아래 청색 바, 시행문 회색 띠."""
        띠서식 = {"줄간격": 100, "왼여백mm": 0, "위여백mm": 0, "아래여백mm": 0}
        pid = self.바탕서식(띠서식, 띠색=명.get("바탕색"))
        p = self.d.add_paragraph("", para_pr_id_ref=pid)
        self.자리잡기(len(self.d.paragraphs) - 1, 띠서식)
        p.add_run(" ", char_pr_id_ref=self.글자({"pt": max(2, round((명.get("높이mm") or 1) * 2.8, 1))}))
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
        t = (self.d.add_table(nr, nc, width=round(폭 * HU), border_fill_id_ref=테없음) if 폭
             else self.d.add_table(nr, nc, border_fill_id_ref=테없음))
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
                         "왼여백mm": 0, "위여백mm": 0, "아래여백mm": 0}
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
                if 테 or 바:
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
                            for 변 in ("top", "bottom"):
                                cm.set(변, "0")
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

    def 그림(self, 명):
        """화면에서 찍은 PNG 를 화면에서 잰 mm 크기로 넣는다."""
        import base64
        자료 = 명.get("png")
        if not 자료:
            알려진차이.append("도형을 못 찍어 빈 자리로 뒀다 — 화면과 다르다")
            self.d.add_paragraph("")
            return
        try:
            self.d.add_picture(base64.b64decode(자료), "png",
                               width_mm=round(명.get("폭mm") or 60, 2),
                               height_mm=round(명.get("높이mm") or 40, 2))
        except Exception as e:
            알려진차이.append(f"도형을 못 넣었다 — {type(e).__name__}: {str(e)[:60]}")
            self.d.add_paragraph("")

    def 쪽나눔(self):
        self.d.add_paragraph("")
        try:
            self.d.styles.apply_paragraph_format(
                paragraph_index=len(self.d.paragraphs) - 1, page_break_before=True)
        except Exception as e:
            알려진차이.append(f"쪽나눔을 못 넣었다 — {type(e).__name__}")

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


def 쓰기(꾸러미: dict, 나갈곳: str) -> dict:
    b = 붓(꾸러미["문서"])
    센것: dict[str, int] = {}
    for 명 in 꾸러미["명령"]:
        k = 명["종류"]
        함수 = {"문단": b.문단, "표": b.표, "띠": b.띠, "그림": b.그림}.get(k)
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
    try:
        if not (b.d.paragraphs[0].text or "").strip():
            b.자리잡기(0, {"정렬": "left", "줄간격": 100, "왼여백mm": 0,
                        "내어쓰기mm": 0, "위여백mm": 0, "아래여백mm": 0,
                        "줄높이mm": 0.42})
    except Exception as e:                                    # noqa: BLE001
        알려진차이.append(f"첫 유령 줄을 못 줄였다 — {type(e).__name__}")

    # 요소 자식순서 정본화 — python-hwpx 가 charPr 토글(bold·underline 등)을 끝에 붙여
    # outline·shadow 뒤로 민 것, refList 의 bullets 가 styles 뒤로 간 것을 저장 직전에
    # 정본 자리로 되돌린다(WP-H6 ②). 순서만 바꾸고 값은 안 바꾼다.
    b.자식순서_정본화()

    try:
        r = b.d.validate()
        나쁨 = [str(x)[:160] for x in (list(getattr(r, "errors", None) or []))][:8]
    except Exception as e:
        나쁨 = [f"검증을 못 돌렸다: {type(e).__name__}"]
    b.d.save_to_path(나갈곳)
    return {"센것": 센것, "스키마문제": 나쁨, "알려진차이": sorted(set(알려진차이))}


if __name__ == "__main__":
    print(json.dumps(쓰기(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2]),
                     ensure_ascii=False))
