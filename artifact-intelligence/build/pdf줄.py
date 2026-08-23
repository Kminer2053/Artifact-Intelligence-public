#!/usr/bin/env python3
"""기하 오라클 1차(WP-H3) — 두 PDF 의 **줄 상자**를 대조해 쪽수·줄바꿈 일치를 잰다.

    build/.hwpxenv/bin/python build/pdf줄.py <화면.pdf> <한컴.pdf>
    build/.hwpxenv/bin/python build/pdf줄.py --자기시험

무엇을 재나 — 값 대조(대조.py)는 서식 값을 재고, 여기는 **조판 결과의 기하**를 잰다:
같은 글이 몇 쪽에, 몇 줄로, 어느 자리에서 줄이 바뀌어 앉았는가. 이 축이 없으면
"쪽수가 늘었다·줄이 밀렸다"는 사람 눈만 잡는다(구현계획 §2-3 이 계획만 있던 자리).

오라클의 한계(정직하게): 진짜 오라클은 한/글 자신이다. macOS 한/글은 자동화 API 가
없어(한컴 공식) 한컴 쪽 PDF 는 **사람이 내보내 줘야** 한다 — 이 도구는 그 수출본과
화면 인쇄본(크롬)을 받아 재는 자(尺)까지다. Windows 한/글 COM(pyhwpx)이 생기면
2차에서 자동화한다.

줄 추출은 poppler `pdftotext -bbox`(단어 상자 XHTML)를 쓴다 — 손 PDF 파서 금지.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

여기 = Path(__file__).resolve().parent


def 줄상자(pdf경로: Path) -> list[list[str]]:
    """쪽마다 줄 글 목록. 단어 상자를 yMin 근접(±2pt)으로 줄로 묶고 x 로 정렬한다."""
    r = subprocess.run(["pdftotext", "-bbox", str(pdf경로), "-"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit(f"pdftotext 실패 — {r.stderr.strip()[:200]}")
    쪽들 = []
    for 쪽xml in re.findall(r"<page\b[^>]*>(.*?)</page>", r.stdout, re.S):
        단어들 = [(float(m.group(2)), float(m.group(1)), m.group(5))
               for m in re.finditer(
                   r'<word xMin="([\d.]+)" yMin="([\d.]+)" '
                   r'xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', 쪽xml)]
        단어들.sort()
        줄들, 현재줄, 기준y = [], [], None
        for y, x, 글 in 단어들:
            if 기준y is None or abs(y - 기준y) <= 2.0:
                현재줄.append((x, 글))
                기준y = y if 기준y is None else 기준y
            else:
                줄들.append("".join(w for _, w in sorted(현재줄)))
                현재줄, 기준y = [(x, 글)], y
        if 현재줄:
            줄들.append("".join(w for _, w in sorted(현재줄)))
        # 줄 머리의 마커 기호(□○◦·• 등)는 벗겨서 비교한다 — 한컴 PDF 는 글머리
        # 글립에 ToUnicode 매핑이 없어 pdftotext 가 못 읽는 경우가 있다(2026-08-14
        # 첫 실측: 목차 '□추진배경4' vs '추진배경4' — 조판 차이가 아니라 추출기 눈).
        쪽들.append([re.sub(r"^[□○◦·•*※\-]+", "", re.sub(r"[\s　]+", "", l))
                   for l in 줄들 if l.strip()])
    return 쪽들


def 대조(화면pdf: Path, 한컴pdf: Path) -> dict:
    가 = 줄상자(화면pdf)
    나 = 줄상자(한컴pdf)
    가줄 = [l for p in 가 for l in p]
    나줄 = [l for p in 나 for l in p]
    m = SequenceMatcher(None, 가줄, 나줄)
    같은줄 = sum(b.size for b in m.get_matching_blocks())
    # 쪽 안 순서무시 보조 지표 — 표지 결재표처럼 **같은 줄들이 다른 순서**로 묶이는
    # 자리(렌더러의 셀 읽기 순서 차이)를 진짜 줄바꿈 차이와 가른다(2026-08-14 실측:
    # 표지 72%가 순서무시로는 100% — 조판이 아니라 추출 순서였다).
    from collections import Counter
    순서무시같음 = sum(sum((Counter(p1) & Counter(p2)).values())
                 for p1, p2 in zip(가, 나))
    return {
        "쪽수": {"화면": len(가), "한컴": len(나), "일치": len(가) == len(나)},
        "쪽별줄수": {"화면": [len(p) for p in 가], "한컴": [len(p) for p in 나]},
        "줄수": {"화면": len(가줄), "한컴": len(나줄)},
        # 줄바꿈 자리가 같으면 줄 목록이 같아진다 — 그 수렴도를 %로 잰다
        "줄바꿈일치%": round(같은줄 * 2 / max(len(가줄) + len(나줄), 1) * 100, 1),
        "쪽내순서무시일치%": round(순서무시같음 * 2 / max(len(가줄) + len(나줄), 1) * 100, 1),
        "안맞는줄예": [(a, b) for a, b in zip(가줄, 나줄) if a != b][:5],
    }


def main():
    if "--자기시험" in sys.argv:
        표본 = sorted((여기 / "samples").glob("[!_]*.pdf"))[:3]
        전부 = True
        for p in 표본:
            r = 대조(p, p)
            좋다 = r["줄바꿈일치%"] == 100.0 and r["쪽수"]["일치"]
            전부 &= 좋다
            print(("✓" if 좋다 else "✗"), p.stem, "—",
                  f'쪽 {r["쪽수"]["화면"]} · 줄 {r["줄수"]["화면"]} · 일치 {r["줄바꿈일치%"]}%')
        print("자기시험", "통과" if 전부 else "실패", f"({len(표본)}건 — 같은 PDF 는 100% 여야 한다)")
        sys.exit(0 if 전부 else 1)

    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    r = 대조(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    print(f'\n■ 쪽수 {"일치" if r["쪽수"]["일치"] else "불일치"}'
          f'({r["쪽수"]["화면"]} vs {r["쪽수"]["한컴"]}) · 줄바꿈 일치 {r["줄바꿈일치%"]}%')


if __name__ == "__main__":
    main()
