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

# 아는 유형. svgfig.js 의 R 열쇠, ontology/editor-profiles.json 의 유형표와 같아야 한다.
# 세 자리가 어긋나는 것을 build/verify_all.py 의 check_figtypes() 가 막는다.
도식유형 = ("process", "cycle", "converge", "strategy", "relation", "stack")
차트유형 = ("line", "bar", "hbar", "donut")
유형 = 도식유형 + 차트유형


def render(spec):
    """도식·차트 스펙 → 빈 칸. 그리기는 브라우저의 svgfig.js 가 한다."""
    t = spec.get("type")
    if t not in 유형:
        raise ValueError(f"unknown figure type: {t}")
    spec_attr = _html.escape(_json.dumps(spec, ensure_ascii=False), quote=True)
    return f'<div class="blk fr-fig" data-ent="도식" data-fig="{spec_attr}"></div>\n'
