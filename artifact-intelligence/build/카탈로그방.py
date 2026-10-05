"""전이 카탈로그를 **세션 방에서** 다시 만드는 정규 절차('26-09-28 2단계 검토 발견 3).

왜 방에서 만드나 — 카탈로그의 값 집합은 표본을 실측해 얻는다. 추적 표본(build/samples)은
제목 모양·보도 서술 본문꼴·1p 4단(*)·규정 새 들여쓰기 같은 모양을 한 번도 안 밟아서, 트리에서
그대로 만들면 그 모양의 값이 빠진 **좁은 카탈로그**가 나오고 그 모양의 HWPX 내보내기가 막힌다.
그 값은 합성 표본(test/fixtures/r15_style15, ○○공사 — 실업무 문서 아님)에서만 나온다.
합성 표본을 추적 등록부·build/samples 에 넣지 않고(추적 표본은 사람이 판정한 실물 서식이다)
세션 방에서만 짓는다. 그래서 `카탈로그.py` 는 합성 표본이 없는 자리에서 불리면 스스로 이 절차로
넘어오고, 방 안에서도 합성 표본이 빠지면 멈춘다(조용히 좁은 카탈로그를 내지 않는다).

하는 일(트리는 건드리지 않는다 — 쓰는 곳은 세션 방과 --out 뿐이다)
  1. 세션 방에 추적 표본 HTML·등록부·그림을 복사한다.
  2. 합성 등록부를 방의 등록부에 더하고, 지금 조립기로 합성 표본만 조립한다(--only).
  3. 방의 모든 표본 HWPX 를 지금 코드로 다시 만든다(대조로 검증상태를 올리려면 필요하다).
  4. 방에서 `카탈로그.py --out <경로>` 를 돌린다(CATALOG_ROOM=1 — 되넘김 없이, 합성 표본이 빠지면 멈춘다).
  5. 방을 지운다(--남기기 면 둔다).

사용: build/.hwpxenv/bin/python3 build/카탈로그방.py --out <경로> [--세션 열쇠] [--대조없이] [--남기기]
  `카탈로그.py` 를 트리에서 그냥 불러도(합성 표본이 없는 자리) 스스로 이 절차로 넘어온다.
  --out 을 build/전이카탈로그.json 으로 주면 트리 카탈로그를 바로 바꾼다. 먼저 스크래치에
  내고 diff 를 본 뒤 옮기는 쪽을 권한다.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

여기 = Path(__file__).resolve().parent
ROOT = 여기.parent
PY = sys.executable
sys.path.insert(0, str(여기))

# 등록부 이름 → 조립기(verify_all.BUILDS 와 같은 짝). 합성 등록부가 있는 장르만 쓴다.
_조립기 = {"samples": "assemble.py", "fullreport": "assemble_full.py", "press": "assemble_press.py",
         "regulation": "assemble_regulation.py", "gongmun": "assemble_gongmun.py"}


def _추적만(폴더: Path, 꼴: str) -> list[str]:
    """폴더 바로 밑에서 꼴에 맞는 파일 가운데 git 이 추적하는 것만 고른다('26-10-05 release04 감사 P1·P2).

    카탈로그는 공개 트리에 실리는 정본이다. 예전엔 samples/*.html 을 통째로 집어서 미추적 생성물
    (시험 찌꺼기 mcp-test.html·rc-press-overview.html)까지 입력이 됐다. 그러면 커밋한 카탈로그가
    깨끗한 클론에서 다시 지은 것과 달라지고, 공개본에 없는 표본을 출처로 싣는다. 이 파일 머리말
    1번('추적 표본')대로 추적 파일만 쓴다. git 작업본이 아니면(설치본 등) 꼴대로 모두 쓴다.
    """
    후보 = sorted(glob.glob(str(폴더 / 꼴)))
    try:
        r = subprocess.run(["git", "-C", str(폴더), "ls-files", "-z", "--", 꼴],
                           capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return 후보
    추적 = {str((폴더 / p).resolve()) for p in r.stdout.decode("utf-8").split("\0") if p}
    return [h for h in 후보 if str(Path(h).resolve()) in 추적]


def main() -> int:
    ap = argparse.ArgumentParser(description="세션 방에서 전이 카탈로그를 다시 만든다(합성 표본 포함)")
    ap.add_argument("--out", required=True, help="카탈로그를 쓸 곳")
    ap.add_argument("--세션", default="", help="세션 열쇠(영소문자·숫자 16~64자). 없으면 새로 짓는다")
    ap.add_argument("--대조없이", action="store_true", help="카탈로그.py --대조없이 로 돌린다")
    ap.add_argument("--남기기", action="store_true", help="끝나도 세션 방을 지우지 않는다")
    a = ap.parse_args()
    열쇠 = a.세션 or f"catalogroom{int(time.time() * 1000):x}"
    os.environ["문서지능_세션"] = 열쇠
    import 자료뿌리
    import 카탈로그
    방 = 자료뿌리.뿌리()
    if not 방.endswith(os.sep + 열쇠):
        print(f"✗ 세션 방이 서지 않았다: {방}", file=sys.stderr)
        return 2
    env = dict(os.environ)
    out = Path(a.out).resolve()
    try:
        샘 = Path(자료뿌리.산출물뿌리())
        샘.mkdir(parents=True, exist_ok=True)
        for h in _추적만(여기 / "samples", "*.html"):
            shutil.copy(h, 샘)
        for r in _추적만(여기, "*-docs.json"):
            shutil.copy(r, Path(방) / "build" / os.path.basename(r))
        그림 = Path(방) / "build" / "assets"
        if (여기 / "assets").is_dir() and not 그림.exists():
            추적그림 = {os.path.basename(p) for p in _추적만(여기 / "assets", "*")}
            shutil.copytree(여기 / "assets", 그림, ignore=lambda d, 이름들: [
                n for n in 이름들 if Path(d) == 여기 / "assets"
                and os.path.isfile(os.path.join(d, n)) and n not in 추적그림])

        합성 = {}
        for 이름, 경로 in 카탈로그.합성표본().items():
            합성.setdefault(경로, []).append(이름)
        틀림 = 0
        for 경로, 이름들 in sorted(합성.items()):
            장르 = Path(경로).name[:-len("-docs.json")]
            조립기 = _조립기.get(장르)
            if not 조립기:
                print(f"✗ 조립기를 모르는 합성 등록부: {경로}", file=sys.stderr)
                return 2
            본 = Path(방) / "build" / f"{장르}-docs.json"
            있던 = json.load(open(본, encoding="utf-8")) if 본.exists() else []
            겹침 = {d.get("filename") for d in 있던} & set(이름들)
            if 겹침:
                print(f"✗ 합성 표본 이름이 추적 표본과 겹친다: {sorted(겹침)}", file=sys.stderr)
                return 2
            더할 = json.load(open(ROOT / 경로, encoding="utf-8"))
            json.dump(있던 + 더할, open(본, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            for 이름 in 이름들:
                r = subprocess.run([PY, str(여기 / 조립기), str(본), "--only", 이름],
                                   capture_output=True, text=True, env=env)
                ok = r.returncode == 0 and (샘 / f"{이름}.html").exists()
                틀림 += 0 if ok else 1
                print(("✓" if ok else "✗"), "조립", 이름, "" if ok else r.stderr.strip()[-300:], flush=True)
        if 틀림:
            print(f"✗ 합성 표본 {틀림}건을 못 지었다 — 멈춘다", file=sys.stderr)
            return 1

        import 화면읽기
        import 역할
        for h in sorted(샘.glob("*.html")):
            if h.name.startswith("_probe-") or 'data-genre="slides"' in h.read_text(encoding="utf-8")[:1500]:
                continue
            hx = h.with_suffix(".hwpx")
            k = 역할.옮기기(화면읽기.읽기(h), 가드=False, 문서이름=h.stem)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
                json.dump(k, fh, ensure_ascii=False)
                임시 = fh.name
            hx.unlink(missing_ok=True)
            r = subprocess.run([PY, str(여기 / "_hwpx_write.py"), 임시, str(hx)], capture_output=True, text=True)
            os.remove(임시)
            print(("✓" if hx.exists() else "✗"), "HWPX", h.stem, flush=True)

        cmd = [PY, str(여기 / "카탈로그.py"), "--out", str(out)] + (["--대조없이"] if a.대조없이 else [])
        # CATALOG_ROOM=1 — 카탈로그.py 가 합성 표본이 없을 때 이 절차로 되넘기는 길을 끈다(방에서는
        # 합성 표본이 있어야 한다 — 빠지면 넘기지 않고 멈춘다).
        r = subprocess.run(cmd, env=dict(env, CATALOG_ROOM="1"))
        return r.returncode
    finally:
        if not a.남기기:
            shutil.rmtree(방, ignore_errors=True)
            print(f"세션 방을 지웠다: {방}")
        else:
            print(f"세션 방을 남겼다: {방}")


if __name__ == "__main__":
    sys.exit(main())
