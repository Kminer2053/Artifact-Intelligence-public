#!/usr/bin/env python3
"""유효 온톨로지 조회기 — 1층 정본 + 개인 프로파일 오버라이드 병합(출처 표시).

개인화 레이어의 실행부: 2층(빌드플랜)이 온톨로지를 조회할 때 이 도구로 읽으면
개인 오버라이드가 반영된 '유효 값'을 받고, 어떤 값이 개인화인지 출처가 표시된다.
공통 정본(ontology.json)은 절대 수정되지 않는다.

사용:
  python3 personalization/resolve.py <프로파일> [점.경로]
  python3 personalization/resolve.py default entities.요약박스.문체
  python3 personalization/resolve.py default --성향
등재 검증: 하드 게이트 관련 경로(분량예산·게이트)는 오버라이드 금지 — 로드 시 거부.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES = Path(__file__).resolve().parent / "profiles"

FORBIDDEN = ("게이트", "분량예산")  # 하드 게이트는 공통 불변 — 개인화 오버라이드 금지 경로

# 조회 금지(2026-08-13 온톨로지 기밀) — 판별·문체·목차 정본은 개인화 문으로도 클라에
# 내보내지 않는다. 개인화는 성향·비민감 값만 반환하고, 판정·조립이 필요하면 정책서버의
# detect/compose 를 쓴다. (감사: '개인' 작업이 경로 제약 없이 크라운주얼을 되돌리던 구멍)
_조회금지 = ("목차로직", "장르판별", "판별신호", "판별키워드", "표준시퀀스", "압축시퀀스",
           "writing_profiles", "문체", "표정책", "생성_수단")


def _스크럽(node):
    """반환 서브트리에서 크라운주얼 키를 재귀로 잘라낸다 — 조상·빈 경로로 조회해도 판별·문체·
    목차 정본이 새지 않게(요청 path 만 검사하던 구멍 봉합, 2026-08-13). 성향·비민감 값은 남는다."""
    if isinstance(node, dict):
        return {k: _스크럽(v) for k, v in node.items()
                if not any(f in str(k) for f in _조회금지)}
    if isinstance(node, list):
        return [_스크럽(x) for x in node]
    return node


def load(profile_name):
    onto = json.load(open(ROOT / "ontology" / "ontology.json", encoding="utf-8"))
    pf = PROFILES / f"{profile_name}.json"
    if not pf.exists():
        sys.exit(f"프로파일 없음: {pf.name} (profiles/ 안에 생성 필요)")
    prof = json.load(open(pf, encoding="utf-8"))
    applied = []
    for ov in prof.get("overrides", []):
        path = ov["path"]
        if any(f in path for f in FORBIDDEN):
            print(f"[거부] 하드 게이트 경로는 개인화 불가: {path}", file=sys.stderr)
            continue
        node = onto
        parts = path.split(".")
        ok = True
        for p in parts[:-1]:
            if isinstance(node, list):
                try:
                    node = node[int(p)]
                except (ValueError, IndexError):
                    ok = False
                    break
            elif isinstance(node, dict) and p in node:
                node = node[p]
            else:
                ok = False
                break
        if not ok or not isinstance(node, (dict, list)):
            print(f"[무시] 경로 없음: {path}", file=sys.stderr)
            continue
        leaf = parts[-1]
        node[leaf] = ov["value"]
        applied.append(path)
    return onto, prof, applied


def query(onto, path):
    if any(f in path for f in _조회금지):
        return ("이 경로는 조회할 수 없습니다 — 판별·문체·목차 정본은 온톨로지 기밀입니다"
                " (판정·조립은 detect/compose 를 쓰세요).")
    node = onto
    for p in [x for x in path.split(".") if x]:
        if isinstance(node, list):
            node = node[int(p)]
        elif isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return f"경로 오류: '{p}' 없음"
    return _스크럽(node)   # 반환 서브트리도 크라운주얼 제거(조상·빈 경로 우회 봉합)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    profile = sys.argv[1]
    onto, prof, applied = load(profile)
    if len(sys.argv) > 2 and sys.argv[2] == "--성향":
        print(json.dumps(prof.get("성향", {}), ensure_ascii=False, indent=1))
        return 0
    path = sys.argv[2] if len(sys.argv) > 2 else ""
    node = query(onto, path)
    out = json.dumps(node, ensure_ascii=False, indent=1)
    print(out[:6000])
    hits = [a for a in applied if not path or a.startswith(path) or path.startswith(a)]
    if hits:
        print("\n[개인화] 이 결과에 반영된 오버라이드:")
        for h in hits:
            print(f"  · {h}")
    elif applied:
        print(f"\n(프로파일 오버라이드 {len(applied)}건 있음 — 이 경로에는 해당 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
