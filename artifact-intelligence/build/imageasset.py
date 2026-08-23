#!/usr/bin/env python3
"""이미지 자산 어댑터 — 첨부에서 잘라 쓰거나, 외부 생성기로 만들어 쓴다.

두 경로:
  ① 추출(crop)  : 첨부 PDF·이미지·HWPX에서 필요한 영역만 잘라 자산으로 등록
  ② 생성(generate): 런타임의 이미지 생성 능력을 어댑터로 흡수
       host   — 실행 중인 에이전트가 이미지 생성을 할 수 있는 경우(예: ChatGPT).
                요청을 manifest에 적고, 에이전트가 그 경로에 파일을 채우면 그대로 쓴다.
       openai — OPENAI_API_KEY 로 Images API 호출(gpt-image-1 계열)
       gemini — GEMINI_API_KEY 로 이미지 생성 모델 호출
       none   — 아무 수단이 없으면 자리표시자 + 사유를 남긴다(조립은 계속된다)
  Claude API에는 이미지 생성 기능이 없다(공식) — 그래서 어댑터가 필요하다.

공공보고서 가드(온톨로지 data_elements.시각자료.생성_수단):
  사실을 주장하는 도해(조직도·절차도·통계)와 실사로 오인될 이미지는 생성 금지 —
  전자는 없는 부서·틀린 숫자를 그럴듯하게 그리고, 후자는 문서 신뢰성 문제다.
  그런 요청은 거부하고 SVG 도식(build/svgfig.py) 또는 첨부 크롭으로 유도한다.

사용:
  python3 build/imageasset.py --check                 # 쓸 수 있는 수단 점검
  python3 build/imageasset.py --훑기                   # 받은 자료 폴더에서 꺼낼 수 있는 것
  python3 build/imageasset.py --들여다보기 <파일>
  python3 build/imageasset.py --spec assets/spec.json # 스펙 배열 처리
"""
import base64
import html as _html
import json
import os
import re
import subprocess
import sys
import urllib.request

import 자료뿌리

BASE = os.path.dirname(os.path.abspath(__file__))
# 이미지 자산·명세는 **자료**다(사용자가 올린 첨부에서 잘라 낸 것) — 뿌리는
# build/자료뿌리.py 가 정한다(WP-S2 ①). 상대 경로의 기준도 코드뿌리가 아니라
# 자료뿌리의 build/ 다. 안 그러면 다른 뿌리에서 자산이 코드뿌리에 쌓인다.
#
# ★ 뿌리를 **호출마다** 다시 푼다(2026-08-09, ③ 고침 — WP-S9 의 OUT 얼림과 같은 부류).
# 전에는 모듈 적재 때 `ASSETS = 자료뿌리.자산뿌리()`(과 자료빌드·MANIFEST)를 상수로 얼렸다.
# subprocess 로 부를 땐 조립마다 새 프로세스라 매번 새로 풀렸지만, api.py 가 조립기를
# **import 로** 부르면 모듈이 딱 한 번 적재되며 ASSETS 가 **첫 세션 뿌리(대개 코드뿌리)에
# 얼어붙어**, 세션이 만든 도식/이미지 PNG 가 세션 뿌리가 아니라 공용 build/assets 로 샜다
# (세션 내용이 공용 자리에 남음 = 격리·프라이버시 결함, S9 의 OUT 과 판박이). 그래서 상수를
# 없애고 쓰는 함수마다 **머리에서 다시 푼다**(assemble*.py 의 조립하기 가 산출물뿌리 를
# 호출마다 푸는 것과 같은 손). 세션이 없으면 자산뿌리()=코드뿌리라 정본 출력은 글자 하나
# 안 달라진다(대조 38/38 무변). — 상수를 되살리면 verify_all 의 check_imageasset_not_frozen
# 이 잡는다.
def _자산뿌리():
    return 자료뿌리.자산뿌리()


def _명세길():
    return os.path.join(_자산뿌리(), "manifest.json")


def _자료빌드():
    return 자료뿌리.길("build")

# 생성 금지 유형 — 프롬프트에 이 신호가 있으면 거부하고 대안을 제시한다.
# 사실을 주장하는 도해·차트와 로고·상징만 막는다. 상황 설명·시뮬레이션·예시 삽화는
# 허용하되(온톨로지 시각자료.래스터_생성_정책), render 가 'AI 생성물' 표기를 강제해
# 실물 오인을 막는다. '사진·실사' 를 통째로 막던 것은 이 표기로 대체했다.
FORBID = [
    (r"조직도|기구표|절차도|흐름도|플로우|구조도|체계도|다이어그램",
     "사실 관계를 주장하는 도해 — 생성 이미지는 검증 불가. build/svgfig.py 도식으로 그릴 것"),
    (r"그래프|차트|막대|꺾은선|추이|통계",
     "수치를 주장하는 차트 — 생성 이미지는 숫자를 지어낸다. 데이터로 SVG 차트를 그릴 것"),
    (r"로고|엠블럼|휘장|CI|정부상징",
     "기관 상징은 생성 대상이 아니다 — 공식 파일을 첨부로 넣을 것"),
]


def _ok(name):
    return subprocess.run(["command", "-v", name], shell=False, capture_output=True).returncode == 0


def providers():
    """사용 가능한 생성 제공자 점검."""
    out = {}
    out["host"] = os.environ.get("IMAGEGEN_HOST") == "1"
    out["ima2"] = os.environ.get("IMA2") == "1"         # 웹앱 서버의 ima2-gen CLI(무키 OAuth)
    out["openai"] = bool(os.environ.get("OPENAI_API_KEY"))
    out["gemini"] = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return out


def guard(prompt):
    """생성 요청 사전 검사 — 부적합이면 사유를 반환."""
    for pat, why in FORBID:
        if re.search(pat, prompt, re.I):
            return why
    return None


# 프롬프트 가드레일 — 문서 모델이 쓴 프롬프트에 **스타일을 덧대** 톤을 일정하게 만든다.
# 모델 재량에만 맡기면(작은 문서 모델·미지정 스타일) 이미지 모델이 제멋대로 실사화한다.
# 기본 이미지 모델 terra(아이소메트릭 인포그래픽)에 맞춰 평면·라벨·비실사로 고정한다.
# IMAGE_STYLE 로 통째 바꿀 수 있다(빈 값이면 안 덧댐).
_기본스타일 = ("평면 벡터 아이소메트릭 일러스트, 밝고 깔끔한 단색 면, 라벨·아이콘은 또렷하고 읽기 쉽게, "
            "여백 넉넉히, 공공 보고서 삽화 톤. flat isometric vector illustration, clean flat colors, "
            "crisp legible labels, generous whitespace, no photorealism, not a photo")
# 시뮬레이션 삽화(spec["실사"]=true) — 사실성에 포커스. 상황을 그려 보이는 실사 시각화.
_실사스타일 = ("사실적인 고품질 렌더링, 자연스러운 조명·재질·그림자, 실제 상황을 그려 보이는 시뮬레이션 "
            "시각화, 사진처럼 사실적. photorealistic, realistic lighting and materials, high detail, "
            "cinematic, simulation visualization of a real-world scene")


def _스타일적용(prompt, 실사=False):
    s = (os.environ.get("IMAGE_STYLE_REAL", _실사스타일) if 실사
         else os.environ.get("IMAGE_STYLE", _기본스타일))
    return f"{prompt}\n[스타일] {s}" if s.strip() else prompt


# ── ① 추출(crop) ──────────────────────────────────────────────────────────

def _pdf_page_png(src, page, dpi, out_prefix):
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
                    src, out_prefix], check=True, capture_output=True)
    for suf in (f"-{page}.png", f"-{page:02d}.png", f"-{page:03d}.png", ".png"):
        cand = out_prefix + suf
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(f"pdftoppm 산출 없음: {out_prefix}")


def extract(spec, name):
    """첨부에서 영역을 잘라 assets/<name>.png 로 저장하고 경로를 반환.

    크롭 좌표는 비율(0~1) 또는 픽셀. 비율이면 렌더 크기에 맞춰 환산한다.
    PDF 도식은 한글에서 벡터로 나가 pdfimages에 안 잡히므로 '페이지 렌더 후 크롭'이 정석.
    """
    from PIL import Image
    ASSETS, 자료빌드 = _자산뿌리(), _자료빌드()   # 호출마다 세션 뿌리를 다시 푼다(③)
    os.makedirs(ASSETS, exist_ok=True)
    src = spec["파일"]
    if not os.path.isabs(src):
        src = os.path.join(자료빌드, src)
    dpi = spec.get("dpi", 300)
    out = os.path.join(ASSETS, f"{name}.png")

    if src.lower().endswith(".pdf"):
        img_path = _pdf_page_png(src, spec.get("쪽", 1), dpi,
                                 os.path.join(ASSETS, f"_{name}_pg"))
    elif src.lower().endswith(".hwpx"):
        import zipfile
        with zipfile.ZipFile(src) as z:
            bins = [n for n in z.namelist() if n.startswith("BinData/")]
            idx = spec.get("index", 0)
            if not bins:
                raise ValueError("HWPX에 BinData 없음")
            data = z.read(sorted(bins)[idx])
        img_path = os.path.join(ASSETS, f"_{name}_bin")
        자료뿌리.원자쓰기(img_path, data)
    else:
        img_path = src

    im = Image.open(img_path).convert("RGB")
    # 모델은 shape 가 시키는 대로 자를곳{x,y,w,h}(딕셔너리)를 낸다 — 리스트[x,y,w,h]로 정규화한다.
    # (엔진이 크롭[리스트]만 읽어 자를곳을 놓쳐 크롭이 조용히 실패, 첨부 PDF 전체페이지가
    #  삽입되던 것 봉합, 2026-08-13 실측. 크롭[리스트]·E-12 하위호환 유지.)
    box = spec.get("크롭") or spec.get("자를곳")
    if isinstance(box, dict):
        box = [box.get("x", 0), box.get("y", 0), box.get("w", 0), box.get("h", 0)]
    if box:
        x, y, w, h = box
        if max(box) <= 1.0:                       # 비율 좌표
            x, y, w, h = x * im.width, y * im.height, w * im.width, h * im.height
        im = im.crop((int(x), int(y), int(x + w), int(y + h)))
    im.save(out)
    for tmp in (f"_{name}_pg", f"_{name}_bin"):
        for f in os.listdir(ASSETS):
            if f.startswith(tmp):
                os.remove(os.path.join(ASSETS, f))
    return out


# ── 첨부에 무엇이 들었나 ─────────────────────────────────────────────────
# extract() 는 만들어져 있었지만 아무도 부르지 않았다 — 받은 자료 폴더에 PDF를 넣어도
# 그 안의 그림을 쓸 길이 없었다. 먼저 '무엇을 꺼낼 수 있는지' 보는 길을 낸다.

def 들여다보기(src, 미리보기=True):
    """첨부 하나에서 꺼낼 수 있는 것을 목록으로 낸다.

    PDF는 쪽마다 미리보기를 만들고, HWPX는 안에 든 그림을 센다.
    미리보기를 만들어 두면 사용자가 눈으로 보고 고를 수 있다.
    """
    ASSETS, 자료빌드 = _자산뿌리(), _자료빌드()   # 호출마다 세션 뿌리를 다시 푼다(③)
    if not os.path.isabs(src):
        src = os.path.join(자료빌드, src)
    if not os.path.exists(src):
        return {"파일": src, "_실패": "파일이 없습니다"}
    이름 = os.path.splitext(os.path.basename(src))[0]
    low = src.lower()
    out = {"파일": os.path.relpath(src, 자료빌드), "이름": 이름}

    if low.endswith(".pdf"):
        if not _ok("pdfinfo"):
            out["_실패"] = "pdfinfo 가 없어 PDF를 못 엽니다"
            return out
        r = subprocess.run(["pdfinfo", src], capture_output=True, text=True)
        m = re.search(r"Pages:\s*(\d+)", r.stdout)
        n = int(m.group(1)) if m else 0
        out["종류"] = "PDF"
        out["쪽수"] = n
        out["꺼낼수있는것"] = [{"쪽": i, "설명": f"{i}쪽 전체"} for i in range(1, n + 1)]
        if 미리보기 and n:
            os.makedirs(os.path.join(ASSETS, "_preview"), exist_ok=True)
            for i in range(1, min(n, 12) + 1):
                try:
                    png = _pdf_page_png(src, i, 72,
                                        os.path.join(ASSETS, "_preview", f"{이름}-p{i}"))
                    out["꺼낼수있는것"][i - 1]["미리보기"] = os.path.relpath(png, 자료빌드)
                except Exception as exc:
                    out["꺼낼수있는것"][i - 1]["_실패"] = str(exc)[:60]
        return out

    if low.endswith(".hwpx"):
        import zipfile
        try:
            with zipfile.ZipFile(src) as z:
                bins = sorted(n for n in z.namelist() if n.startswith("BinData/"))
                out["종류"] = "HWPX"
                out["꺼낼수있는것"] = [
                    {"index": i, "설명": os.path.basename(b),
                     "크기": z.getinfo(b).file_size} for i, b in enumerate(bins)]
        except Exception as exc:
            out["_실패"] = f"HWPX를 못 엽니다: {exc}"
        return out

    if re.search(r"\.(png|jpe?g|gif|webp|bmp|tiff?)$", low):
        out["종류"] = "그림 파일"
        try:
            from PIL import Image
            im = Image.open(src)
            out["크기"] = f"{im.width}×{im.height}"
        except Exception:
            pass
        out["꺼낼수있는것"] = [{"설명": "그림 전체"}]
        return out

    out["종류"] = "그림을 꺼낼 수 없는 형식"
    out["꺼낼수있는것"] = []
    return out


def 폴더훑기(폴더=None, 미리보기=True):
    """받은 자료 폴더를 통째로 훑는다."""
    폴더 = 폴더 or 자료뿌리.받은것뿌리()
    if not os.path.isdir(폴더):
        return []
    out = []
    for f in sorted(os.listdir(폴더)):
        full = os.path.join(폴더, f)
        if not os.path.isfile(full) or f.startswith(".") or f == "README.md":
            continue
        out.append(들여다보기(full, 미리보기))
    return out


# ── ② 생성(generate) ─────────────────────────────────────────────────────

def _gen_openai(prompt, size, out):
    key = os.environ["OPENAI_API_KEY"]
    body = json.dumps({"model": os.environ.get("IMAGEGEN_OPENAI_MODEL", "gpt-image-1"),
                       "prompt": prompt, "size": size, "n": 1}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    item = d["data"][0]
    raw = base64.b64decode(item["b64_json"]) if "b64_json" in item else \
        urllib.request.urlopen(item["url"], timeout=120).read()
    자료뿌리.원자쓰기(out, raw)
    return out


def _gen_gemini(prompt, size, out):
    key = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    model = os.environ.get("IMAGEGEN_GEMINI_MODEL", "gemini-3-pro-image")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
           f"?key={key}")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    for part in d["candidates"][0]["content"]["parts"]:
        blob = part.get("inlineData") or part.get("inline_data")
        if blob:
            자료뿌리.원자쓰기(out, base64.b64decode(blob["data"]))
            return out
    raise ValueError("Gemini 응답에 이미지 파트 없음")


def _gen_ima2(prompt, size, out, 실사=False):
    """ima2-gen CLI 로 생성 — 웹앱 서버에 `ima2`(npm i -g ima2-gen) 설치 + `ima2 serve` 가
    떠 있어야 한다. GPT OAuth 로 무키 생성한다(사용자가 ima2 setup 에서 한 번 로그인).

    실사=True(시뮬레이션 삽화)면 사실성 우선 — high 품질 + 실사 강한 모델(luna). 기본(삽화)은
    medium + terra(평면·라벨). 실측 2026-08-11: terra·5.4 는 평면 준수, sol·luna 는 실사화.

    **왜 HTTP 가 아니라 CLI 인가** — ima2 의 OpenAI 호환 엔드포인트(:PORT/v1)는 chat/responses
    용이고, 이미지 생성은 `ima2 gen` CLI 로만 낸다(실측 2026-08-11: /v1/images/generations
    는 Route not found, /v1/models 는 gpt-5.6-sol/luna 등 응답 모델만). CLI 는 -o 로 우리
    산출 경로에 바로 저장한다. 조율 env: IMA2_QUALITY(low)·IMA2_MODEL(luna 등)·IMA2_SERVER.
    """
    사이즈 = str(size) if "x" in str(size) else "1024x1024"
    # 품질·모델은 모드로 갈린다 — 시뮬(실사)은 사실성 우선(high·luna), 삽화는 절충(medium·terra).
    # 환경변수(IMA2_QUALITY·IMA2_MODEL)가 있으면 그게 최우선(배포가 못박고 싶을 때).
    품질 = os.environ.get("IMA2_QUALITY") or ("high" if 실사 else "medium")
    모델 = os.environ.get("IMA2_MODEL") or ("gpt-5.6-luna" if 실사 else "gpt-5.6-terra")
    cmd = ["ima2", "gen", prompt, "-o", out, "--json", "--quality", 품질, "--size", 사이즈,
           # provider 를 안 주면 ima2 가 NO_DEFAULT_MODEL 로 죽는다. 기본은 oauth(무키).
           "--provider", os.environ.get("IMA2_PROVIDER", "oauth"), "--model", 모델]
    if os.environ.get("IMA2_SERVER"):
        cmd += ["--server", os.environ["IMA2_SERVER"]]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       timeout=int(os.environ.get("IMA2_TIMEOUT", "300")))
    if r.returncode != 0 or not os.path.exists(out):
        꼬리 = (r.stdout + r.stderr).strip().splitlines()
        raise RuntimeError(f"ima2 gen 실패: {꼬리[-1] if 꼬리 else 'rc=' + str(r.returncode)}")
    return out


def generate(spec, name):
    """이미지 생성 — 가용 제공자를 자동 선택. 실패해도 조립은 계속된다."""
    ASSETS, 자료빌드 = _자산뿌리(), _자료빌드()   # 호출마다 세션 뿌리를 다시 푼다(③)
    os.makedirs(ASSETS, exist_ok=True)
    out = os.path.join(ASSETS, f"{name}.png")
    prompt, size = spec.get("프롬프트"), spec.get("크기", "1024x1024")
    if not prompt:   # 프롬프트 누락 시 KeyError 로 전체 조립을 크래시내지 않고 자리표시자로 강등(추출과 대칭)
        return None, "생성 프롬프트 없음 — \"프롬프트\" 를 넣어야 한다"
    why = guard(prompt)
    if why:
        return None, f"생성 거부 — {why}"
    실사 = bool(spec.get("실사"))          # 시뮬레이션·사실적 장면 → 실사 스타일 + 고품질 + 실사 모델
    prompt = _스타일적용(prompt, 실사)     # 가드레일 — 문서 모델 프롬프트에 톤을 덧댄다(기본 평면, 실사면 실사)

    want = spec.get("제공자", "auto")
    avail = providers()
    # host(스킬·MCP) → ima2(웹앱 서버) → openai → gemini. 환경변수로 표면이 갈린다.
    order = [want] if want != "auto" else [p for p in ("host", "ima2", "openai", "gemini") if avail[p]]
    for prov in order:
        try:
            if prov == "host":
                # 호스트 에이전트가 생성 능력을 가진 경우: 요청만 남기고, 파일이 이미 있으면 채택.
                _log_request(name, prompt, size, out)
                if os.path.exists(out):
                    return out, None
                return None, f"host 생성 대기 — {os.path.relpath(out, 자료빌드)} 에 이미지를 넣으면 반영"
            if prov == "ima2" and avail["ima2"]:
                return _gen_ima2(prompt, size, out, 실사), None
            if prov == "openai" and avail["openai"]:
                return _gen_openai(prompt, size, out), None
            if prov == "gemini" and avail["gemini"]:
                return _gen_gemini(prompt, size, out), None
        except Exception as exc:                    # 제공자 실패는 다음 후보로
            last = f"{prov} 실패: {exc}"
            continue
    _log_request(name, prompt, size, out)
    return None, ("사용 가능한 이미지 생성 수단 없음 — 웹앱은 서버에 ima2 설치·ima2 serve 실행·IMA2=1, "
                  "스킬·MCP 는 생성 가능한 런타임에서 IMAGEGEN_HOST=1, 또는 "
                  "OPENAI_API_KEY / GEMINI_API_KEY 설정")


def _log_request(name, prompt, size, out):
    """호스트 에이전트가 채워 넣을 수 있도록 요청을 manifest에 남긴다."""
    ASSETS, MANIFEST, 자료빌드 = _자산뿌리(), _명세길(), _자료빌드()   # 호출마다 다시 푼다(③)
    os.makedirs(ASSETS, exist_ok=True)
    man = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {}
    man[name] = {"프롬프트": prompt, "크기": size, "저장경로": os.path.relpath(out, 자료빌드),
                 "상태": "대기"}
    자료뿌리.원자json(MANIFEST, man, indent=1)   # 원자 쓰기(WP-S2 ③, E-6)


# ── 조립기 연결 ──────────────────────────────────────────────────────────

def render(spec, name):
    """이미지 스펙 → HTML 조각(.fr-fig 재사용: 꺾쇠 캡션 + ※ 함의)."""
    e = _html.escape
    src, err = (None, None)
    if spec.get("출처") == "생성":
        src, err = generate(spec, name)
    else:
        try:
            src = extract(spec, name)
        except Exception as exc:
            err = f"추출 실패: {exc}"

    # 편집기가 손댈 수 있게 스펙을 통째로 싣는다 — 도식(.fr-fig)·표와 같은 방식.
    # 브라우저는 원본 PDF를 자를 수 없으므로, 화면에서는 '어디를 자를지'만 정하고
    # 실제 잘라내기는 반영할 때 여기(extract)가 다시 한다.
    스펙 = _html.escape(json.dumps(spec, ensure_ascii=False), quote=True)
    parts = [f'<div class="blk fr-fig fr-img" data-ent="이미지" data-img="{스펙}">']
    if spec.get("캡션"):
        parts.append(f'<div class="cap">&lt; {e(spec["캡션"])} &gt;</div>')
    if src:
        rel = os.path.relpath(src, 자료뿌리.산출물뿌리())
        w = spec.get("폭", "80%")
        parts.append(f'<img src="{e(rel)}" alt="{e(spec.get("대체텍스트") or spec.get("캡션", ""))}" '
                     f'style="width:{e(str(w))}">')
        # AI 생성물 표기 강제(온톨로지 시각자료.AI표기_필수) — 렌더가 붙이므로 스펙에서
        # 지워도 다시 나온다. 표기가 실물 오인을 막는 신뢰성 장치다.
        if spec.get("출처") == "생성":
            parts.append('<div class="ai-gen">🅰 AI 생성물</div>')
    else:
        parts.append(f'<div class="ph">[이미지 미확보] {e(err or "")}</div>')
    노트 = spec.get("함의") or spec.get("설명")   # shape 는 '설명'(※근거·출처)을 가르치므로 폴백(유실 봉합)
    if 노트:
        parts.append(f'<div class="note">{e(노트)}</div>')
    parts.append("</div>\n")
    return "".join(parts)


def main():
    a = sys.argv[1:]
    if "--훑기" in a or "--들여다보기" in a:
        미리 = "--미리보기없이" not in a
        if "--들여다보기" in a:
            목록 = [들여다보기(a[a.index("--들여다보기") + 1], 미리)]
        else:
            목록 = 폴더훑기(미리보기=미리)
        if not 목록:
            print("받은 자료 폴더가 비어 있습니다.")
            return 0
        for it in 목록:
            print(f"\n■ {it.get('이름') or it['파일']}  ({it.get('종류', '?')})")
            if it.get("_실패"):
                print("  ✗", it["_실패"])
                continue
            것들 = it.get("꺼낼수있는것") or []
            if not 것들:
                print("  꺼낼 수 있는 그림이 없습니다.")
                continue
            print(f"  꺼낼 수 있는 것 {len(것들)}개")
            for x in 것들[:12]:
                꼬리 = ("  미리보기: " + x["미리보기"]) if x.get("미리보기") else ""
                print(f"    · {x['설명']}{꼬리}")
            if len(것들) > 12:
                print(f"    … 외 {len(것들) - 12}개")
        return 0
    if "--check" in sys.argv:
        av = providers()
        print("이미지 생성 제공자:")
        for k, v in av.items():
            print(f"  {k:8} {'가용' if v else '—'}")
        print("추출 도구:")
        for t in ("pdftoppm", "pdftotext", "pdfimages"):
            r = subprocess.run(["which", t], capture_output=True)
            print(f"  {t:10} {'가용' if r.returncode == 0 else '—'}")
        try:
            import PIL  # noqa
            print("  PIL        가용")
        except ImportError:
            print("  PIL        —")
        return 0
    if "--spec" in sys.argv:
        path = sys.argv[sys.argv.index("--spec") + 1]
        for i, sp in enumerate(json.load(open(path, encoding="utf-8"))):
            print(render(sp, sp.get("이름", f"asset{i}"))[:200])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
