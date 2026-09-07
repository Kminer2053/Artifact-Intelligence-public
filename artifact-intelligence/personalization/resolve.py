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

# 2026-09-06 재발 봉합 — 위 차단목록은 온톨로지가 자랄 때마다 샌다. 슬라이드 개편(462cd04)이
# document_types.slides.구성 에 레이아웃_카탈로그·서사_골격·콘텐츠_레이아웃_매핑 을 신설했는데
# 목록에 없어 `개인` 작업으로 원문이 그대로 나갔다(공개 push 전 적대감사가 잡음). 그래서
# **차단목록 → 허용목록**으로 뒤집는다: 규칙 뿌리(온톨로지 지식 정본) 아래에서는 아래 잎만
# 남기고 나머지는 전부 잘라낸다. 차단목록은 이중 안전망으로 그대로 둔다.
_규칙뿌리 = ("document_types", "entities", "data_elements", "writing_profiles", "shared",
           "장르판별", "_model", "_미확정_갈래")
_허용잎 = ("label", "aliases", "status", "이름", "설명", "id")


def _스크럽(node, 규칙안=False):
    """반환 서브트리에서 크라운주얼을 재귀로 잘라낸다 — 조상·빈 경로로 조회해도 판별·문체·
    목차·구성 정본이 새지 않게. 규칙 뿌리 아래(규칙안=True)에서는 허용 잎만 남긴다(허용목록)."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if any(f in str(k) for f in _조회금지):
                continue                                   # 이중 안전망(차단목록)
            안 = 규칙안 or (str(k) in _규칙뿌리)
            if 안 and not isinstance(v, (dict, list)) and str(k) not in _허용잎:
                continue                                   # 규칙 아래 비허용 잎은 버린다
            잘림 = _스크럽(v, 안)
            if 안 and isinstance(잘림, (dict, list)) and not 잘림:
                continue                                   # 빈 껍데기도 버린다 — 키 이름 열거(설계도)도 새지 않게
            out[k] = 잘림
        return out
    if isinstance(node, list):
        return [_스크럽(x, 규칙안) for x in node]
    return node


def load(profile_name):
    onto_path = ROOT / "ontology" / "ontology.json"
    if not onto_path.exists():
        # 정책만-로컬 배포본엔 온톨로지 로컬 정본이 없다(크라운주얼). 지식()처럼 부재를
        # 우아하게 알리고 끝낸다 — FileNotFoundError 트레이스백·설치 절대경로가 로그로 새지 않게.
        sys.exit("개인화는 온톨로지 로컬 정본이 있어야 합니다 — 정책만-로컬 배포본에는 없습니다"
                 " (개인화는 웹앱/개발 환경에서 쓰세요).")
    onto = json.load(open(onto_path, encoding="utf-8"))
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
    parts = [x for x in path.split(".") if x]
    규칙안 = bool(parts) and parts[0] in _규칙뿌리     # 규칙 뿌리 아래 경로면 허용목록 모드
    node = onto
    for p in parts:
        if isinstance(node, list):
            node = node[int(p)]
        elif isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return f"경로 오류: '{p}' 없음"
    # 규칙 뿌리 아래의 스칼라(잎)는 허용 잎 이름일 때만 — 예: …slides.label OK, …구성.중핵 거부.
    if 규칙안 and not isinstance(node, (dict, list)) and (not parts or parts[-1] not in _허용잎):
        return ("이 경로는 조회할 수 없습니다 — 구성·문체·판별 정본은 온톨로지 기밀입니다"
                " (판정·조립은 detect/compose 를 쓰세요).")
    잘림 = _스크럽(node, 규칙안)   # 반환 서브트리도 허용목록으로 잘라낸다(조상·빈 경로 우회 봉합)
    if 규칙안 and isinstance(잘림, (dict, list)) and not 잘림:
        return ("이 경로는 조회할 수 없습니다 — 구성·문체·판별 정본은 온톨로지 기밀입니다"
                " (판정·조립은 detect/compose 를 쓰세요).")
    return 잘림


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
