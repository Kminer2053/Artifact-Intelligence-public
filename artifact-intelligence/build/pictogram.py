#!/usr/bin/env python3
"""픽토그램 애셋 — 의미 라인 아이콘. 슬라이드 등 시각 요소로 재사용한다.

정본 자산: build/pictograms.json (name → {"라벨", "inner"}). inner 는 스타일 없는 SVG
기하(<path>·<circle>·<rect>·<line>·<polyline>·<polygon>)만 담는다 — 굵기·색은 render()
가 씌우는 균일 래퍼(24×24, currentColor, stroke 1.8)가 준다. 그래서 아이콘 32개가 한 손에서
나온 듯 일관된다. 색은 currentColor 라 쓰는 자리의 글자색을 따른다.

사용:
    from pictogram import render, label, names
    svg = render("safety-shield")     # → <svg …>…</svg>
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
_LIB = None
# 라이브러리에 없는 이름을 조용히 삼키지 않는다 — 안내 아이콘(원+i)으로 눈에 띄게 둔다.
_없음 = ('<circle cx="12" cy="12" r="9"/><line x1="12" y1="10.5" x2="12" y2="16"/>'
        '<circle cx="12" cy="7.6" r="0.5"/>')


def _lib():
    global _LIB
    if _LIB is None:
        with open(os.path.join(BASE, "pictograms.json"), encoding="utf-8") as f:
            _LIB = json.load(f)
    return _LIB


def has(name):
    return name in _lib()


def names():
    return sorted(_lib().keys())


def label(name):
    ic = _lib().get(name)
    return ic["라벨"] if ic else name


def render(name, cls="picto"):
    ic = _lib().get(name)
    inner = ic["inner"] if ic else _없음
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            f'{inner}</svg>')


if __name__ == "__main__":
    lib = _lib()
    print(f"픽토그램 {len(lib)}개:", ", ".join(sorted(lib)))
