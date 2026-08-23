#!/usr/bin/env python3
"""내보내기 환경 메타 — 변환 품질에 영향을 주는 **서버 환경**을 기록한다(방법론 전환 3단계).

왜: 글꼴 보유·라이브러리 버전·런타임(OS)·크롬 버전이 변환 품질을 가른다(사장님
지시 2026-08-13). 재현점수(불일치)와 짝을 이뤄 "어떤 환경에서 얼마나 어긋났나"를
나중에 물을 수 있도록 export 마다 산출물 곁 사이드카로 남긴다.

서버 것만 모은다 — 개인정보가 아니다. 클라이언트 환경(보유 글꼴·UA)은 핑거프린팅급
데이터라 동의 게이트·통제 어휘 설계(부록 방법론전환 §5, 8단계) 전에는 손대지 않는다.

수집은 프로세스당 한 번 캐시한다 — 버전·글꼴 목록은 프로세스가 사는 동안 안 변하고,
크롬 `--version` 서브프로세스를 export 마다 띄우는 것은 낭비다. 잰시각만 호출마다 찍는다.

남기지 못한 것(공유 파일 협의 필요, 커밋 메시지에도 적음):
  · substFont 대체 발생 여부 — _hwpx_write.py 가 이벤트를 돌려줘야 안다
  · 문서별 사용 서식 요소 — tohwpx 꾸러미에서 파생해야 한다(만들기 반환 계약 확장)
"""
from __future__ import annotations

import importlib.util
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

여기 = Path(__file__).resolve().parent
_캐시: dict | None = None


def _형제(이름: str):
    """build/ 형제 모듈을 sys.path 를 건드리지 않고 불러온다(부록 A-1 의 병 회피)."""
    spec = importlib.util.spec_from_file_location(이름, 여기 / f"{이름}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _hwpx엔진버전() -> str | None:
    py = 여기 / ".hwpxenv" / "bin" / "python"
    if not py.exists():
        return None
    try:
        r = subprocess.run(
            [str(py), "-c",
             "import importlib.metadata as m; print(m.version('python-hwpx'))"],
            capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except Exception:
        return None


def _크롬() -> dict:
    try:
        경로 = _형제("크롬찾기").찾기()
    except Exception:
        경로 = None
    if not 경로:
        return {"경로": None, "버전": None}
    try:
        r = subprocess.run([경로, "--version"], capture_output=True, text=True,
                           timeout=15)
        버전 = r.stdout.strip() or None
    except Exception:
        버전 = None
    return {"경로": 경로, "버전": 버전}


def _서버글꼴() -> dict:
    """실파일 기준 — 등록부를 따로 두면 손목록이 된다. 이름과 크기만 센다."""
    나옴 = {}
    for 자리 in (여기.parent / "fonts", 여기.parent / "workspace" / "fonts"):
        if 자리.is_dir():
            나옴[str(자리.relative_to(여기.parent))] = {
                p.name: p.stat().st_size for p in sorted(자리.iterdir())
                if p.is_file() and not p.name.startswith(".")}
    return 나옴


def 모으기() -> dict:
    """환경 메타 한 벌. 잰시각 말고는 프로세스당 한 번만 잰다."""
    global _캐시
    if _캐시 is None:
        _캐시 = {
            "플랫폼": platform.platform(),
            "파이썬": platform.python_version(),
            "python_hwpx": _hwpx엔진버전(),
            "크롬": _크롬(),
            "서버글꼴": _서버글꼴(),
        }
    return dict(_캐시, 잰시각=datetime.now(timezone.utc).astimezone()
                .isoformat(timespec="seconds"))


if __name__ == "__main__":
    import json
    print(json.dumps(모으기(), ensure_ascii=False, indent=1))
