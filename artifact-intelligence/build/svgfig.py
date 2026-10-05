#!/usr/bin/env python3
"""도식·차트 자리를 만든다 — 그리는 것은 브라우저의 svgfig.js 하나뿐이다.

전거: research/ontology/extracted/15_시각자료_박스_리서치.json (VP-01~30 실측)
- 인라인 SVG는 Chrome headless 인쇄에서 100% 벡터로 남고 한글도 PDF 텍스트로 추출된다.
- SVG에는 자동 줄바꿈이 없다 → 어절 경계로 사전 분할해 tspan으로 쌓는다(VP-03).
- 접근성: role="img" + <title> (VP-06).

**이 파일은 그리지 않는다.** 스펙을 실은 빈 칸만 내고, 좌표 계산과 SVG 생성은 전부
build/svgfig.js 가 한다. 편집기에서 유형·단계를 바꾸면 좌표를 다시 계산해야 하는데
생성기가 서버에도 있으면 두 벌이 어긋나기 때문이다.
  ※ 2026-08-01 정리: 여기에 파이썬으로 다시 그리는 함수 6개(230줄)가 남아 있었다.
    render() 가 그것들을 부르지 않아 **죽은 코드**였고, 거기서 고쳐 봐야 화면은 안 바뀐다.
    지웠다. 도식 생김새를 고치려면 svgfig.js 를 고쳐라.

지원 유형 — 온톨로지 data_elements.시각자료.의미구조_유형에 대응:
  절차도(process)      단계 3~5, 전이 라벨        ← 절차·전이
  순환도(cycle)        닫힌 고리                  ← 절차·전이(환류)
  수렴형(converge)     선행요건 N → 1 → 결과      ← 절차·전이(수렴)
  전략체계도(strategy) 목표1+전략2~4+과제         ← 관계·구조
  구조도(relation)     노드 + 연결(방향)          ← 관계·구조
  스택막대(stack)      구성비 2세트 대비          ← 대조·분포
  비교판(compare)      현행 전[] ⇨ 개선 후[]      ← 대조(현행 vs 개선)

격자(표) 도식('26-09-29 재설계 P2): A4 에서 체계도(strategy)·절차도(process)·비교판(compare)은 svgfig.js 가
SVG 대신 HTML <table> 로 그린다 — HWPX 에서 한글 네이티브 표가 되어 한글에서 칸·색·글을 고칠 수 있다.
스펙은 그대로다(새 키는 비교판의 전[]·후[], 선택 머리[2] 뿐). 옛 슬라이드(.sl-page)의 절차·체계는 SVG 그대로.
  꺾은선(line)         시점별 추세                ← 시계열
  막대(bar)            시점별 값 비교, 쌓기 가능  ← 시계열·대조·구성비
  가로막대(hbar)       항목 이름이 길 때          ← 대조·순위
  도넛(donut)          구성비 한 세트             ← 분포·구성비

차트 3종은 실물 공공보고서 본문 44쪽 육안 실측 규격을 따른다(2026-08-01):
격자선 없음 · 얇은 회색 테 · 범례는 판 위 가운데 · 값 라벨은 막대에 붙이고 꺾은선은
마지막 점만 · 꽉 찬 파이는 쓰지 않는다(실물 0장) · 포인트색은 문서당 하나.

사용: from svgfig import render;  html = render({"type": "process", ...})
"""
import html as _html
import json as _json

# 아는 유형. svgfig.js 의 R·G(격자) 열쇠, ontology/editor-profiles.json 의 유형표, 온톨로지
# document_types.slides.구성.도식_유형(슬라이드 지시문 목록)과 같아야 한다.
# 네 자리가 어긋나는 것을 build/verify_all.py 의 check_figtypes() 가 막는다.
도식유형 = ("process", "cycle", "converge", "strategy", "relation", "stack", "compare")
차트유형 = ("line", "bar", "hbar", "donut")
유형 = 도식유형 + 차트유형


크기들 = ("작게", "보통", "크게")


def 크기정규화(spec):
    """도식 크기 → 작게|보통|크게 한 축('26-09-28 사장님 판정). **옛 값을 접는 곳은 여기 하나다.**

    · 슬라이드 옛 '크게'·'가득' → 크게 (가득은 칸을 넘치던 값 — 19/40, measure.md)
    · 옛 설계안 '폭'(좁게·반·넓게·전폭, 또는 '60%' 꼴) → 전폭 70% 미만·좁게·반 = 작게, 나머지 = 보통.
      '폭' 은 **도식 스펙에서만** 읽고 지운다 — 이미지의 폭 %(imageasset) 와 섞이지 않게,
      그리고 카탈로그 _등록부훑기 가 이미지 폭 관측값으로 세지 않게.
    크기는 data-fig JSON 안에만 두고 svgfig.js 가 안쪽 svg 에 적용한다(그릇 폭은 안 바꾼다).
    돌려주는 값: (정규화된 새 스펙 사본, 크기)."""
    s = dict(spec)
    v = s.get("크기")
    if v in ("가득",):
        v = "크게"
    폭 = s.pop("폭", None)
    if v not in 크기들 and 폭 is not None:
        p = str(폭).strip()
        if p in ("좁게", "반"):
            v = "작게"
        elif p.endswith("%"):
            try:
                v = "작게" if float(p[:-1]) < 70 else "보통"
            except ValueError:
                v = None
        else:
            v = "보통"
    if v not in 크기들:
        v = "보통"
    if v == "보통":
        s.pop("크기", None)          # 기본값은 키를 안 남긴다(왕복 불변식 — 편집기도 같다)
    else:
        s["크기"] = v
    return s, v


def render(spec):
    """도식·차트 스펙 → 빈 칸. 그리기는 브라우저의 svgfig.js 가 한다."""
    t = spec.get("type")
    if t not in 유형:
        raise ValueError(f"unknown figure type: {t}")
    spec, _ = 크기정규화(spec)
    spec_attr = _html.escape(_json.dumps(spec, ensure_ascii=False), quote=True)
    return f'<div class="blk fr-fig" data-ent="도식" data-fig="{spec_attr}"></div>\n'
