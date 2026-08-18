#!/usr/bin/env python3
"""피드백 원장 도구 — 정합성 검증 + 대기 큐 조회.

사용:
  python3 feedback.py            # 원장 검증 + 상태별 요약
  python3 feedback.py --pending  # 처리 대기 큐(후보/검증중/보류) 상세
"""
import json
import sys
from collections import Counter
from pathlib import Path

# 원장은 **코드뿌리**에 남는다 — 세션이 만드는 자료가 아니라 우리가 재서 배운 규칙이고,
# 코드는 읽기만 한다(WP-S2 ①, 부록 §2). 자리를 정하는 곳은 build/자료뿌리.py 하나다.
import importlib.util as _iu
_사양 = _iu.spec_from_file_location(
    "자료뿌리", Path(__file__).resolve().parent.parent / "build" / "자료뿌리.py")
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

LEDGER = Path(자료뿌리.원장길())
REQUIRED = {"id", "date", "source", "원문", "해석", "분류", "상태", "검증"}
BUNRYU = {"요소": {"구성", "문체", "디자인", "재현"}, "층": {1, 2, 3, 4},
          "범위": {"공통", "개인", "미정"}}   # 재현 = 변환(HWPX) 품질(2026-08-14)


def load():
    data = json.load(open(LEDGER))
    states = set(data["상태값"])
    errors = []
    seen = set()
    for e in data["entries"]:
        eid = e.get("id", "?")
        if eid in seen:
            errors.append(f"{eid}: ID 중복")
        seen.add(eid)
        missing = REQUIRED - set(e)
        if missing:
            errors.append(f"{eid}: 필수 필드 누락 {sorted(missing)}")
        if e.get("상태") not in states:
            errors.append(f"{eid}: 상태값 오류 '{e.get('상태')}'")
        b = e.get("분류", {})
        for k, allowed in BUNRYU.items():
            if b.get(k) not in allowed:
                errors.append(f"{eid}: 분류.{k} 오류 '{b.get(k)}'")
        if e.get("상태") == "등재" and not e.get("처리"):
            errors.append(f"{eid}: 등재인데 처리(개정 위치) 미기록")
        if e.get("상태") in ("검증중", "등재") and not e.get("검증"):
            errors.append(f"{eid}: 검증 수단 미기록")
    return data, errors


def main():
    data, errors = load()
    entries = data["entries"]
    if errors:
        print(f"원장 정합성: 오류 {len(errors)}건")
        for x in errors:
            print(f"  ✗ {x}")
        return 1
    print(f"원장 정합성: OK ({len(entries)}건)")
    print("상태별:", dict(Counter(e["상태"] for e in entries)))
    print("요소별:", dict(Counter(e["분류"]["요소"] for e in entries)))

    if "--pending" in sys.argv:
        print("\n== 처리 대기 큐 ==")
        for e in entries:
            if e["상태"] in ("수집", "후보", "검증중", "보류"):
                print(f"[{e['상태']}] {e['id']} ({e['분류']['요소']}/{e['분류']['층']}층) {e['해석']}")
                print(f"        검증: {e['검증']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
