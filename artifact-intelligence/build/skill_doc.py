#!/usr/bin/env python3
"""SKILL.md 의 '작업 목록' 절을 workspace/api.py 등록부에서 **세어서** 만든다.

왜 만들었나(WP-S8, 2026-08-07): SKILL.md 에 작업 이름을 손으로 나열해 둔 표가
있었다(읽기 6개 · 쓰기 6개 — 실제 등록부는 그보다 훨씬 많다). `workspace/api.py`
에 작업이 늘 때마다 SKILL.md 를 따로 고쳐야 했고, 안 고치면 모델이 스킬 문서만
읽고 실제로 있는 작업을 "목록에 없다"고 여겨 건너뛰거나 없는 이름을 지어 부른다
— 사람이 읽는 문서라 검사 없이는 아무도 정기적으로 맞춰 보지 않는다. 손목록이
이 저장소에서 열두 번 넘게 밟은 함정과 같은 모양이다(구현계획.md 규칙 2).
`build/genres.py` 가 장르를 세어서 얻듯, 여기는 작업을 세어서 얻는다 — 그리고
`build/verify_all.py` 의 `check_skill_doc` 이 SKILL.md 와 이 생성 결과가 어긋나면
잡는다(고장 주입으로 검증됨).

사용:
  python3 build/skill_doc.py             # 생성될 절을 표준출력에 보여준다
  python3 build/skill_doc.py --write     # SKILL.md 의 마커 사이를 실제로 갈아 끼운다
  python3 build/skill_doc.py --check     # SKILL.md 현재 내용과 다르면 실패(종료 1) — verify_all 이 이 함수를 그대로 불러 쓴다
"""
from __future__ import annotations

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
SKILL_MD = os.path.join(ROOT, "SKILL.md")

# 마커 문구 자체가 "손으로 고치지 마라"는 안내를 겸한다 — 표만 봐서는
# 자동 생성인지 알 길이 없어서, 옛 표는 그 자리에서 손으로 늘어나곤 했다.
시작마커 = ("<!-- 작업목록:시작 (build/skill_doc.py 가 생성 — 손으로 고치지 마라. "
          "다시 만들려면: python3 build/skill_doc.py --write) -->")
끝마커 = "<!-- 작업목록:끝 -->"


def _작업들():
    sys.path.insert(0, os.path.join(ROOT, "workspace"))
    import api
    return api.목록()


def 생성() -> str:
    """마커 사이에 들어갈 본문 — 마커 자체는 포함하지 않는다."""
    작업들 = _작업들()
    읽기 = [w["이름"] for w in 작업들 if w["읽기"]]
    쓰기 = [w["이름"] for w in 작업들 if not w["읽기"]]
    return (
        "읽기는 아무 때나, 쓰기는 정본을 바꾼다:\n\n"
        "| | 작업 |\n"
        "|---|---|\n"
        f"| 읽기 | {' · '.join(읽기)} |\n"
        f"| 쓰기 | {' · '.join(쓰기)} |\n"
    )


def 끼워넣기(원본: str, 본문: str) -> str:
    """SKILL.md 원문의 마커 사이를 본문으로 갈아 끼운다.

    마커가 없으면 **조용히 넘어가지 않는다** — 누가 SKILL.md 를 통째로 고쳐 마커를
    지우면, 이 함수가 조용히 아무것도 안 바꾸고 통과한 것처럼 보이면 안 된다.
    """
    if 시작마커 not in 원본 or 끝마커 not in 원본:
        raise SystemExit(
            "SKILL.md 에서 작업목록 마커를 못 찾았다 — 다음 두 줄이 그대로 있어야 한다:\n"
            f"  {시작마커}\n  {끝마커}"
        )
    앞, 나머지 = 원본.split(시작마커, 1)
    _, 뒤 = 나머지.split(끝마커, 1)
    return 앞 + 시작마커 + "\n\n" + 본문 + "\n" + 끝마커 + 뒤


def main():
    본문 = 생성()
    원본 = open(SKILL_MD, encoding="utf-8").read()
    기대 = 끼워넣기(원본, 본문)

    if "--write" in sys.argv:
        if 기대 != 원본:
            open(SKILL_MD, "w", encoding="utf-8").write(기대)
            print("SKILL.md 작업목록 절을 갱신했다.")
        else:
            print("SKILL.md 작업목록 절이 이미 최신이다.")
        return 0

    if "--check" in sys.argv:
        if 기대 != 원본:
            print("SKILL.md 의 작업목록 절이 등록부(workspace/api.py)와 어긋난다 — "
                  "python3 build/skill_doc.py --write 로 다시 만들어라.", file=sys.stderr)
            return 1
        print("일치.")
        return 0

    print(본문)
    return 0


if __name__ == "__main__":
    sys.exit(main())
