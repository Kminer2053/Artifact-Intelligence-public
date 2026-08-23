#!/usr/bin/env python3
"""고쳐 온 기록 화면 — 이 문서가 어떻게 바뀌어 왔는지 사람이 읽게 그립니다.

읽기 전용입니다. 여기서 무엇을 바꾸지 않습니다.

기본으로 보이는 것은 **버전과 요청하신 말**뿐입니다. 고친 내역·확인할 것·만드는 방식은
접어 둡니다. 전부 시간순으로 늘어놓으면 문서가 많아졌을 때 아무도 읽지 않습니다.

사용:
  python3 history/render_history.py --all
  python3 history/render_history.py <문서>
"""
import glob
import html
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, BASE)
import version as V  # noqa: E402
import diff as D     # noqa: E402

e = html.escape

CSS = """
:root { --ink:#1F3864; --line:#C3CEDD; --dim:#5B6878; }
body { margin:0; background:#F0F2F5; color:#16202E;
  font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif; }
.sheet { width:min(180mm,100%); margin:8mm auto; background:#fff; padding:12mm 14mm 16mm;
  box-sizing:border-box; box-shadow:0 1px 8px rgba(0,0,0,.14); }
h1 { font-size:15pt; color:var(--ink); margin:0 0 1mm; }
.sub { color:var(--dim); font-size:10.5pt; margin-bottom:4mm; }
.caveat { background:#F4F6F9; border-left:3px solid var(--line); padding:2.5mm 3.5mm;
  font-size:10pt; color:var(--dim); line-height:1.6; margin-bottom:6mm; }
.ev { border-left:2px solid var(--line); padding:0 0 5mm 4mm; margin-left:2mm; position:relative; }
.ev::before { content:""; position:absolute; left:-4.6px; top:2px; width:7px; height:7px;
  border-radius:50%; background:var(--line); }
.ev.big::before { background:var(--ink); width:9px; height:9px; left:-5.6px; }
.ev .when { font-size:10pt; color:var(--dim); }
.ev .what { font-size:11.5pt; font-weight:700; margin-top:0.5mm; }
.ev .why { font-size:10.5pt; color:#35455A; margin-top:1mm; line-height:1.6; }
.ev .quote { font-size:10.5pt; color:#24344A; background:#F7FAFD; border-radius:3px;
  padding:1.5mm 2.5mm; margin-top:1.5mm; }
.ev .ba { font-size:10pt; margin-top:1.5mm; line-height:1.6; }
.ev .ba b { color:var(--dim); font-weight:600; }
.tag { float:right; font-size:9.5pt; font-weight:700; padding:0.3mm 2mm; border-radius:3px; }
details { margin:3mm 0 6mm; }
summary { cursor:pointer; font-size:10.5pt; color:var(--ink); }
details .ev { padding-bottom:3mm; }
.none { color:var(--dim); font-size:10.5pt; }
"""


def 언제(iso):
    try:
        d, t = iso.split("T")
        y, m, dd = d.split("-")
        hh, mm = t.split(":")[:2]
        ampm = "오전" if int(hh) < 12 else "오후"
        h12 = int(hh) % 12 or 12
        return f"{int(m)}월 {int(dd)}일 {ampm} {h12}:{mm}"
    except Exception:
        return iso


def 판카드(key, h):
    말 = {"직접": "직접 보관하셨습니다", "자동": "고치기 전 상태를 자동으로 보관했습니다"}
    p = [f'<div class="ev big">'
         f'<div class="when">{e(언제(h["때"]))}</div>'
         f'<div class="what">버전 {h["버전"]} — {e(말.get(h.get("종류"), ""))}</div>']
    if h.get("메모"):
        p.append(f'<div class="why">{e(h["메모"])}</div>')
    if h.get("고친 이유"):
        p.append(f'<div class="why"><b>고친 이유:</b> {e(h["고친 이유"])}</div>')
    if h.get("고친 내역"):
        p.append(f'<div class="why">{e(h["고친 내역"])}</div>')
    잰 = h.get("잰 값") or {}
    if 잰.get("_안잼"):
        p.append(f'<div class="why" style="color:#8A5A10">{e(잰["_안잼"])}</div>')
    elif 잰:
        p.append('<div class="why">' + " · ".join(f"{k} {v}" for k, v in 잰.items()
                                                 if not k.startswith("_")) + '</div>')
    p.append("</div>")
    return "".join(p)


def 사건카드(r):
    종 = r.get("종류")
    if 종 == "지시":
        p = [f'<div class="ev"><div class="when">{e(언제(r["때"]))}</div>'
             f'<div class="what">이렇게 요청하셨습니다</div>'
             f'<div class="quote">“{e(r.get("원문", ""))}”</div></div>']
        return "".join(p)
    if 종 == "손질":
        p = [f'<div class="ev"><div class="when">{e(언제(r["때"]))}</div>'
             f'<div class="what">{r.get("바뀐곳", 0)}군데를 고쳤습니다</div>']
        if r.get("고친 내역"):
            p.append(f'<div class="why">{e(r["고친 내역"])}</div>')
        for c in (r.get("전후") or [])[:6]:
            k = c.get("종류")
            if k == "추가":
                p.append(f'<div class="ba"><b>{e(c["경로"])}</b> 새로 생김 — {e(c.get("후", ""))}</div>')
            elif k == "지움":
                p.append(f'<div class="ba"><b>{e(c["경로"])}</b> 없어짐 — {e(c.get("전", ""))}</div>')
            else:
                p.append(f'<div class="ba"><b>{e(c["경로"])}</b><br>'
                         f'고치기 전: {e(c.get("전", ""))}<br>'
                         f'고친 뒤: {e(c.get("후", ""))}</div>')
        p.append("</div>")
        return "".join(p)
    if 종 == "되돌림":
        항 = r.get("항목") or []
        p = [f'<div class="ev"><div class="when">{e(언제(r["때"]))}</div>'
             f'<div class="what">구성 설계에서 확인하실 것이 {r.get("얹은건수", 0)}건 생겼습니다</div>']
        for it in 항[:4]:
            p.append(f'<div class="ba"><b>{e(str(it.get("개체", "")))}</b> {e(str(it.get("무엇", "")))}</div>')
        p.append("</div>")
        return "".join(p)
    if 종 == "만드는 방식":
        return (f'<div class="ev"><div class="when">{e(언제(r["때"]))}</div>'
                f'<div class="what">문서를 만드는 방식이 바뀌었습니다</div>'
                f'<div class="why">{e(r.get("말", ""))}</div></div>')
    if 종 == "되돌리기":
        return (f'<div class="ev big"><div class="when">{e(언제(r["때"]))}</div>'
                f'<div class="what">버전 {r.get("되돌린버전")} 내용으로 되돌렸습니다</div>'
                f'<div class="why">되돌리기 전 상태도 버전 {r.get("직전버전")}으로 보관했습니다.</div>'
                + (f'<div class="why"><b>고친 이유:</b> {e(r["고친이유"])}</div>'
                   if r.get("고친이유") else "")
                + '</div>')
    if 종 == "옛백업":
        return (f'<div class="ev"><div class="when">{e(언제(r.get("만든때", r["때"])))}</div>'
                f'<div class="what">이 기능을 쓰기 전에 있던 예전 파일입니다</div></div>')
    return ""


def build(key):
    L = V.기록읽기(key) or {}
    버전들 = {h["버전"]: h for h in V.목록(key)}
    사건 = V.읽기(key)
    큰것 = [r for r in 사건 if r.get("종류") in ("보관", "지시", "되돌리기")]
    나머지 = [r for r in 사건 if r.get("종류") not in ("보관", "지시", "되돌리기")]

    본문 = []
    # 같은 초에 여러 사건이 나면 시각만으로는 순서가 안 잡힌다 — 판 번호로 가른다
    def 차례키(x):
        return (x.get("때", ""), x.get("버전") or 0)

    for r in sorted(큰것, key=차례키, reverse=True):
        if r.get("종류") == "보관":
            h = 버전들.get(r.get("버전"))
            본문.append(판카드(key, h) if h else 사건카드(r))
        else:
            본문.append(사건카드(r))
    if not 본문:
        본문 = ['<div class="none">아직 기록이 없습니다. 문서를 고치고 채팅에 '
                '“다 고쳤어요”라고 알려 주시면 여기에 쌓입니다.</div>']

    접힌 = "".join(사건카드(r) for r in
                 sorted(나머지, key=lambda x: x.get("때", ""), reverse=True))
    n버전 = len(버전들)
    상태말 = {"작성 중": "작성 중입니다", "마무리": "작성을 마치셨습니다"}

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>고쳐 온 기록 — {e(key)}</title>
<style>{CSS}</style></head><body>
<div class="sheet">
  <h1>이 문서를 고쳐 온 기록</h1>
  <div class="sub">{e(key)} · {e(상태말.get(L.get('상태', ''), ''))}
    {' · 버전 ' + str(n버전) + '개' if n버전 else ''}</div>
  <div class="caveat">이 기록은 작업하실 때 참고하시라고 모아 둔 것입니다.
    기관의 공식 기록은 아닙니다.</div>
  {''.join(본문)}
  {f'<details><summary>그 밖에 있었던 일 {len(나머지)}건 보기</summary>{접힌}</details>'
   if 나머지 else ''}
</div></body></html>
"""


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    keys = a
    if a[0] == "--all":
        keys = sorted(os.path.basename(os.path.dirname(p))
                      for p in glob.glob(os.path.join(V.이력뿌리(), "*", "문서.json")))
    n = 0
    for k in keys:
        # 이력 화면도 **자료**다 — 뿌리는 version.이력뿌리() 하나가 정한다(WP-S2 ①)
        out = os.path.join(V.이력방(k), "기록.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # 원자 쓰기(WP-S2 ③) — build(k) 가 죽어도 옛 화면이 그대로 남게.
        # 자료뿌리는 version 모듈이 이미 불러 둔 **같은 객체**를 쓴다.
        with V.자료뿌리.쓰기(out) as f:
            f.write(build(k))
        n += 1
    print(f"고쳐 온 기록 {n}건을 만들었습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
