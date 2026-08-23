#!/usr/bin/env python3
"""PDF 낡음 스탬프 — 표본 PDF 가 어느 html 에서 나왔나를 PDF 메타(Info.Keywords)에 심는다.

hwpx 는 zip 아카이브 코멘트에 원본기준을 심어 낡음을 판별한다(build/tohwpx.py). PDF 는
zip 코멘트가 없어 그 대칭이 비어 있었다 — **표본 PDF 는 스탬프도 검사도 없어**, html 을
재조립하고 pdf 를 안 지으면 낡은 PDF 가 판면·기하 측정을 조용히 오염시킨다(HWPX 전환
피어의 기하 오라클 첫 실측에서 화면 PDF 낡음이 잡혔다, '26-08-14).

여기서 pymupdf 로 PDF Info 의 keywords 필드에 {"원본기준": "<그때 html 의 기준해시>"} 를
심는다. **본문 스트림(pdftotext·pdfinfo·판면이 재는 것)은 한 글자도 안 건드린다** — 메타
Info 딕셔너리만 증분 저장으로 덧대므로 기하 측정에 무해하다(실측: pdfinfo 쪽수·pdftotext
-bbox 좌표 무변). 사이드카(.pdf.meta.json)는 .gitignore(`**/build/samples/*.meta.json`)라
체크아웃 뒤 안 남아 못 쓴다 — **임베드라야** 커밋된 PDF 와 함께 영속한다(hwpx zip 코멘트와
같은 결). 검사는 build/verify_all.py 의 check_pdf_staleness 가 맡는다.
"""
import json
import re
import sys

_열쇠 = "원본기준"


def _html기준(html경로):
    m = re.search(r'<meta name="기준" content="([0-9a-f]+)"',
                  open(html경로, encoding="utf-8").read(1 << 16))
    return m.group(1) if m else None


def 찍기(pdf경로, html경로) -> bool:
    """PDF 메타 keywords 에 {"원본기준": html기준} 를 증분 저장으로 심는다(본문 불변).
    실패는 조용히 False — 스탬프 실패가 내보내기를 못 세우면 안 된다(부가 정보다)."""
    기준 = _html기준(html경로)
    if not 기준:
        return False
    try:
        import fitz
        doc = fitz.open(pdf경로)
        md = doc.metadata or {}
        md["keywords"] = json.dumps({_열쇠: 기준})
        doc.set_metadata(md)
        doc.save(pdf경로, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()
        return True
    except Exception:
        return False


def 읽기(pdf경로):
    """PDF 메타에서 원본기준을 읽는다. 없거나 못 읽으면 None."""
    try:
        import fitz
        kw = (fitz.open(pdf경로).metadata or {}).get("keywords") or ""
        return (json.loads(kw) or {}).get(_열쇠)
    except Exception:
        return None


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "찍기":
        sys.exit(0 if 찍기(sys.argv[2], sys.argv[3]) else 1)
    if len(sys.argv) >= 3 and sys.argv[1] == "읽기":
        print(읽기(sys.argv[2]) or "")
        sys.exit(0)
    print("사용법: pdf낡음.py 찍기 <pdf> <html>  |  읽기 <pdf>", file=sys.stderr)
    sys.exit(2)
