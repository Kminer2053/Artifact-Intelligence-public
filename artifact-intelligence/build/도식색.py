#!/usr/bin/env python3
"""도식·차트 색 — 문서 팔레트 하나에서 파생색을 **16진으로 미리** 계산한다('26-09-28 재설계 P0).

왜 파이썬에서 미리 계산하나
  CSS `color-mix()` 로 파생하면 크롬 계산값이 `color(srgb …)` 꼴이 되고, 그 꼴을 읽는 수확기
  (화면읽기·topptx)에 기대게 된다. 대비(4.5:1) 검사도 CSS 에서는 못 한다. 그래서 팔레트
  파생(진한 강조·중간 머리·옅은 몸통·분야색 짝·차트색)은 여기 한 곳에서 hex 로 정하고,
  `--fig-*` CSS 변수로 싣는다. svgfig.js 는 이 변수만 읽는다(자기 색 상수가 없다).

팔레트 (사장님 판정 '26-09-28)
  남색·청·청록·먹 네 벌 + 기관색 하나(문서의 포인트색). **적색 계열은 막는다** — 적색은
  경고·역방향에만 쓴다(정본 풀버전 색_규격 VC-32). 기관색이 적색이면 남색으로 대신한다.
  예: 정부부처형 가계부채 문서의 포인트색 #C00000 은 장·절 머리에만 남고 도식은 남색이다.

역할 (스펙에는 hex 를 쓰지 않는다 — 역할만 쓴다. svgfig.js 가 이 표로 칠한다)
  강조 = accent 진하게 + 흰 글(대비 4.5:1 보장) · 보조 = soft · 머리 = mid · 회색 = gray
  분야1·분야2 = 다른 색상 두 벌의 mid(머리)·soft(몸통) 짝 · 차트 = chart(강조) + chart-mid(비교)

슬라이드(옛 도식)와 tokens.css 기본값도 이 모듈이 낸 값을 그대로 적어 둔 것이다 —
test/r18_figs18.py 가 CSS 에 적힌 값과 이 계산이 같은지 대조한다(드리프트 가드).
"""
import colorsys
import re
import sys

# 프리셋 — 이름 → 강조색. 순서가 편집기 단추 순서다. '기관색' 은 문서 포인트색을 쓴다.
프리셋 = {"남색": "#1F3864", "청": "#0070C0", "청록": "#12695F", "먹": "#404040"}
기관색이름 = "기관색"
기본팔레트 = "남색"
# 분야색 후보(색상각이 강조색과 40° 넘게 떨어진 것부터 둘) — 청·청록·주황·보라 계열
_분야후보 = ("#2F6FB5", "#1F8A70", "#C8742A", "#6B4FA0")
_고정 = {"gray": "#F2F2F2", "line": "#6E6E6E", "ink": "#111111", "sub": "#444444",
        "frame": "#B8B8B8", "bg": "#FFFFFF"}
_꼴 = re.compile(r"^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$")


def _rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def 섞기(색, 비율, 바탕="#FFFFFF"):
    """색 × 비율 + 바탕 × (1 − 비율). 비율 0.35 = '강조 35% 파스텔'."""
    a, b = _rgb(색), _rgb(바탕)
    return _hex(tuple(x * 비율 + y * (1 - 비율) for x, y in zip(a, b)))


def 휘도(색):
    def 선형(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (선형(v) for v in _rgb(색))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def 대비(a, b):
    la, lb = sorted((휘도(a), 휘도(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def 색상각(색):
    r, g, b = (v / 255 for v in _rgb(색))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, l, s


def 적색인가(색):
    """색상각이 적색 쪽이고 채도가 있으면 적색 계열이다 — 도식에는 안 쓴다(경고·역방향 전용).

    폭('26-09-29 판정 ①): 25° 까지(주황빛 빨강 #E8590C 21°·주황 CI #F37321 23° 도 막는다) ·
    자주 쪽은 330° 위. 판정 문구는 '340~25°(주황빨강·진홍 포함)'인데, 판정이 가리킨 진홍 #AD1457 은
    333.7° 이고 예전 폭(335° 위)이 막던 #E0115F 는 337° 라 340° 로는 둘 다 새어 나간다 — 판정이 이름으로
    든 색을 막는 쪽(330°)을 택했다. 26° 넘는 주황(#C8742A 28°)은 그대로 쓴다. 장·절 제목색(포인트색)은
    이 검사와 무관하게 그대로다(도식·차트·표 칠에만 건다).
    """
    h, l, s = 색상각(색)
    return (h <= 25 or h >= 330) and s >= 0.35 and 0.08 <= l <= 0.95


def 진하게(색, 최소대비=4.5):
    """흰 글이 올라갈 수 있게(대비 ≥ 4.5) 검정 쪽으로 조금씩 민다."""
    c = 색
    for _ in range(20):
        if 대비(c, "#FFFFFF") >= 최소대비:
            return c
        c = 섞기(c, 0.9, "#000000")
    return c


def 올바른색(v):
    return isinstance(v, str) and bool(_꼴.match(v.strip()))


def 팔레트(강조, *, 적색막기=True):
    """강조색 하나 → 도식 토큰 전부(hex). 적색이면 남색으로 대신한다(적색막기)."""
    if not 올바른색(강조):
        강조 = 프리셋[기본팔레트]
    강조 = _hex(_rgb(강조.strip()))
    if 적색막기 and 적색인가(강조):
        강조 = 프리셋[기본팔레트]
    acc = 진하게(강조)
    h0, _, s0 = 색상각(acc)
    분야 = []
    for c in _분야후보:
        h, _, _ = 색상각(c)
        d = min(abs(h - h0), 360 - abs(h - h0))
        if s0 < 0.12 or d >= 40:          # 먹(무채색)이면 거리를 안 본다
            분야.append(c)
        if len(분야) == 2:
            break
    t = {"accent": acc, "on-accent": "#FFFFFF",
         "mid": 섞기(acc, 0.35), "soft": 섞기(acc, 0.12),
         "chart": acc, "chart-mid": 섞기(acc, 0.42)}
    for i, c in enumerate(분야, 1):
        t[f"cat{i}-mid"] = 섞기(c, 0.35)
        t[f"cat{i}-soft"] = 섞기(c, 0.13)
    t.update(_고정)
    return t


# 표 머리·첫 열 옅은 색('26-09-29 판정 ⑤) — 문서 팔레트가 표에도 닿는다. 기본(남색)은 재경부 실측 값
# 그대로(머리 #DFE6F7 · 첫 열 #F2F2F2 — tokens.css --doc-p-blue-soft·--doc-p-gray-soft). 다른 팔레트는
# #DFE6F7 의 밝기·채도(HLS l 0.92·s 0.60)를 강조색의 색상각으로 옮기고, 첫 열은 같은 색상각의 더 옅은
# 칠(l 0.95·s 0.30)이다. 무채색(먹)은 행안부 표준 회색 머리(#D9D9D9)와 회색 첫 열이다.
_표기본 = {"doc-table-head-bg": "#DFE6F7", "doc-table-first-bg": "#F2F2F2"}


def _hls(h, l, s):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l, s)
    return _hex((r * 255, g * 255, b * 255))


def 표색(강조):
    """강조색(적색 막기를 거친 뒤) → 표 머리·첫 열 칠 hex. 남색 기본이면 재경부 값 그대로."""
    강조 = _hex(_rgb(강조)) if 올바른색(강조) else 프리셋[기본팔레트]
    if 강조 == 프리셋[기본팔레트]:
        return dict(_표기본)
    h, _, s = 색상각(강조)
    if s < 0.12:
        return {"doc-table-head-bg": "#D9D9D9", "doc-table-first-bg": "#F2F2F2"}
    return {"doc-table-head-bg": _hls(h, 0.9216, 0.60), "doc-table-first-bg": _hls(h, 0.95, 0.30)}


def 문서강조(doc, 장르="fullreport"):
    """문서 설정 → (팔레트 이름, 강조색). 키가 없으면 정부부처형은 기관색(포인트색), 그 밖은 남색."""
    doc = doc if isinstance(doc, dict) else {}
    이름 = doc.get("팔레트")
    포인트 = doc.get("포인트색")
    if 이름 not in (*프리셋, 기관색이름):
        if 이름 is not None:
            print(f"[속성 거부] 팔레트={이름!r} — 고를 수 있는 것: "
                  f"{', '.join((*프리셋, 기관색이름))}", file=sys.stderr)
        이름 = 기관색이름 if doc.get("스타일") == "정부부처형" else 기본팔레트
    if 이름 == 기관색이름:
        c = 포인트 if 올바른색(포인트) else ("#0070C0" if doc.get("스타일") == "정부부처형"
                                         else 프리셋[기본팔레트])
        if 적색인가(c):
            print(f"[팔레트] 기관색 {c} 은 적색 계열이라 도식·차트·표 칠에는 남색을 씁니다"
                  " (적색은 경고·역방향 전용, 장·절 제목색은 그대로)", file=sys.stderr)
        return 이름, c
    return 이름, 프리셋[이름]


def 변수줄(t):
    return ";".join(f"--fig-{k}:{v}" for k, v in t.items())


def 표변수줄(t):
    return ";".join(f"--{k}:{v}" for k, v in t.items())


def 막은강조(c):
    """문서 강조색 → 도식·표에 실제로 쓰는 강조색(적색이면 남색 — 팔레트() 와 같은 규칙)."""
    c = _hex(_rgb(c.strip())) if 올바른색(c) else 프리셋[기본팔레트]
    return 프리셋[기본팔레트] if 적색인가(c) else c


def 스타일(doc, 장르="fullreport"):
    """<head> 에 넣을 <style> 한 조각. 기본(남색)과 같으면 빈 글자 — tokens.css 가 이미 그 값이다.
    도식 토큰(--fig-*)과 표 머리·첫 열 칠(--doc-table-head-bg·--doc-table-first-bg, 판정 ⑤)을 함께 싣는다."""
    _, c = 문서강조(doc, 장르)
    t = 팔레트(c)
    if t == 팔레트(프리셋[기본팔레트]):
        return ""
    return f"<style>:root{{{변수줄(t)};{표변수줄(표색(막은강조(c)))}}}</style>"


if __name__ == "__main__":
    # 사용: 도식색.py [강조hex] — 토큰 줄을 찍는다(CSS 에 옮겨 적을 때 쓴다)
    for a in (sys.argv[1:] or list(프리셋.values())):
        print(a, 변수줄(팔레트(a, 적색막기=False)))
