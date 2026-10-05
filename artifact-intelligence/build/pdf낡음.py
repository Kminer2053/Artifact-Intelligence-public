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


_AI_XMP = ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
           '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
           'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
           'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia">'
           '<dc:description><rdf:Alt><rdf:li xml:lang="x-default">AI 생성물이 포함된 문서</rdf:li></rdf:Alt></dc:description>'
           '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')


def _AI그림있나(html경로):
    """조립된 HTML 에 실린(표식이 아닌) AI 생성 그림이 있나 — imageasset.render 가 data-gen 을 달고, 못 얻으면 data-miss."""
    try:
        h = open(html경로, encoding="utf-8").read()
    except OSError:
        return False
    return any("data-miss=" not in m.group(0)
               for m in re.finditer(r'<div class="blk fr-fig fr-img[^>]*data-gen="gen-[0-9a-f]{12}"[^>]*>', h))


def 찍기(pdf경로, html경로) -> bool:
    """PDF 메타 keywords 에 {"원본기준": html기준} 를 증분 저장으로 심는다(본문 불변).
    AI 생성 그림이 실린 문서면 문서 정보(주제·키워드)와 XMP(IPTC DigitalSourceType)에도 'AI 생성물'을 적는다
    ('26-09-30 fixup, review_impl2 M7 — PDF 속 그림은 크롬이 다시 인코딩해 PNG 글 조각 표기가 사라진다).
    실패는 조용히 False — 스탬프 실패가 내보내기를 못 세우면 안 된다(부가 정보다)."""
    기준 = _html기준(html경로)
    ai = _AI그림있나(html경로)
    if not 기준 and not ai:
        return False
    try:
        import fitz
        doc = fitz.open(pdf경로)
        md = doc.metadata or {}
        kw = {_열쇠: 기준} if 기준 else {}
        if ai:
            kw["AI생성물"] = True
            md["subject"] = "그림 일부를 AI로 만든 문서"
            try:
                doc.set_xml_metadata(_AI_XMP)
            except Exception:
                pass
        md["keywords"] = json.dumps(kw)
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
