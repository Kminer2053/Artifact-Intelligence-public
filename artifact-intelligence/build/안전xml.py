"""올린 파일의 XML 을 읽기 전에 DTD·엔티티 선언을 거절한다('26-10-01 감사 code F4).

사용자가 올린 HWPX·DOCX(압축 속 XML)·HWPML(.hml) 을 표준 xml.etree 로 읽는 자리가 늘었다. ElementTree 는 외부
엔티티를 풀지 않고 파이썬에 딸린 expat 은 엔티티 폭증(십억 웃음)을 막지만, 그 보호는 판마다 다르고 kordoc(node)
쪽 파서는 우리가 고를 수 없다. 그래서 **파서에 넘기기 전에** 바이트를 보고 거절한다.

거절하는 것: `<!ENTITY` 선언(어디에 있든), 내부 부분집합(`[ … ]`)이나 외부 식별자(SYSTEM·PUBLIC)가 붙은 `<!DOCTYPE`.
한글·워드가 저장한 문서에는 둘 다 없다. 이름만 있는 `<!DOCTYPE 이름>` 은 엔티티를 정의할 수 없어 그대로 둔다(정밀도 우선).
UTF-16·UTF-32 로 적은 XML 도 같이 본다(널 바이트를 걷어 내고 다시 본다).

쓰는 법:
    import 안전xml
    root = 안전xml.fromstring(z.read("word/document.xml"))   # 위험하면 안전xml.위험XML
    안전xml.파일검사(경로)   # 압축 문서·hml 을 통째로 미리 본다 — 위험하면 사람 말 한 줄, 아니면 None
"""
import codecs
import re
import xml.etree.ElementTree as _ET

사람말 = ("이 파일은 읽지 않았습니다. 파일 속 XML 에 문서 형식 선언(DTD·엔티티)이 들어 있습니다. "
       "한글이나 워드에서 다시 저장해 올려 주세요.")

# 압축 속 XML 하나를 볼 때 읽는 바이트 상한 — 이보다 큰 항목은 앞부분(선언은 문서 맨 앞, 루트 요소 전에만 올 수 있다)만 본다
_머리바이트 = 1 << 20

_엔티티 = re.compile(rb"<!\s*ENTITY", re.I)
_문서형 = re.compile(rb"<!\s*DOCTYPE(.{0,4096}?)>", re.I | re.S)
_외부식별 = re.compile(rb"\b(?:SYSTEM|PUBLIC)\b", re.I)
_인코딩 = re.compile(rb"""<\?xml[^>]{0,200}?encoding\s*=\s*["']([A-Za-z0-9._:-]{1,40})["']""", re.I)
_아스키계 = {"utf-8", "utf_8", "ascii", "latin-1", "iso8859-1", "cp1252", "euc_kr", "cp949", "johab", "utf-8-sig"}


class 위험XML(ValueError):
    """DTD·엔티티 선언이 든 XML — 읽기 전에 거절했다. str() 은 사람 말이다."""

    def __init__(self, 까닭=""):
        super().__init__(사람말)
        self.까닭 = 까닭


def _위험한가(b):
    if _엔티티.search(b):
        return "ENTITY 선언"
    for m in _문서형.finditer(b):
        속 = m.group(1)
        if b"[" in 속 or _외부식별.search(속):
            return "DOCTYPE 선언(내부 부분집합·외부 식별자)"
    if b"<!" in b and re.search(rb"<!\s*DOCTYPE", b, re.I) and not _문서형.search(b):
        return "닫히지 않은 DOCTYPE 선언"
    return ""


def 까닭(바이트):
    """위험하면 그 까닭(짧은 글), 아니면 '' — 바이트(또는 글)를 본다."""
    b = 바이트.encode("utf-8", "replace") if isinstance(바이트, str) else bytes(바이트 or b"")
    r = _위험한가(b)
    if r:
        return r
    if b"\x00" in b[:4096]:            # UTF-16·UTF-32 — ASCII 범위 글자는 널을 걷으면 그대로 읽힌다
        r = _위험한가(b.replace(b"\x00", b""))
        if r:
            return r
    m = _인코딩.search(b[:400].replace(b"\x00", b""))
    if m:
        try:
            이름 = codecs.lookup(m.group(1).decode("ascii")).name
        except (LookupError, UnicodeDecodeError):
            이름 = ""
        if 이름 and 이름 not in _아스키계 and not 이름.startswith(("utf-16", "utf-32", "iso8859", "latin")):
            # ASCII 와 바이트가 다른 인코딩(EBCDIC 류) — 풀어서 다시 본다
            try:
                r = _위험한가(b.decode(이름, "ignore").encode("utf-8"))
            except Exception:
                r = ""
            if r:
                return r
    return ""


def 검사(바이트):
    """위험하면 위험XML 을 던진다."""
    r = 까닭(바이트)
    if r:
        raise 위험XML(r)


def fromstring(바이트):
    """xml.etree.ElementTree.fromstring 과 같되, DTD·엔티티 선언이 있으면 위험XML."""
    검사(바이트)
    return _ET.fromstring(바이트)


def parse(경로):
    """xml.etree.ElementTree.parse 와 같되(ElementTree 를 돌려준다), 읽기 전에 검사한다."""
    with open(경로, "rb") as f:
        b = f.read()
    return _ET.ElementTree(fromstring(b))


def 파일검사(경로):
    """올린 파일 하나를 미리 본다 — 압축 문서(HWPX·DOCX·XLSX·PPTX 등)는 속의 .xml·.rels·.hpf 항목을, 그 밖의 XML 파일(.hml
    등, 첫 바이트가 '<' 또는 BOM)은 파일 자체를 본다. 위험하면 사람 말 한 줄, 아니면 None. 못 읽으면(깨진 압축 등) None —
    거절은 이 검사의 몫이 아니다(읽는 쪽이 제 말로 거절한다)."""
    import zipfile
    try:
        if zipfile.is_zipfile(경로):
            with zipfile.ZipFile(경로) as z:
                for info in z.infolist():
                    n = info.filename.lower()
                    if info.is_dir() or not n.endswith((".xml", ".rels", ".hpf", ".xhtml", ".svg", ".opf")):
                        continue
                    with z.open(info) as f:
                        if 까닭(f.read(_머리바이트)):
                            return 사람말
            return None
        with open(경로, "rb") as f:
            머리 = f.read(_머리바이트)
    except Exception:
        return None
    # XML 로 보이는 파일만(<?xml·<!·<HWPML 로 시작) — 글 파일 속 '<!ENTITY' 글자를 거절하지 않게
    벗김 = 머리[:64].replace(b"\x00", b"").lstrip(b"\xef\xbb\xbf\xff\xfe \t\r\n").lower()
    if 벗김.startswith((b"<?xml", b"<!", b"<hwpml")) and 까닭(머리):
        return 사람말
    return None
