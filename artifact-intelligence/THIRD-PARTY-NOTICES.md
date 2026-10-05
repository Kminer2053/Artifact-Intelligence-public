# Third-Party Notices · 서드파티 고지

이 프로젝트의 원본 소스 코드는 MIT 라이선스입니다([LICENSE](LICENSE)). 아래 구성요소는
각자의 라이선스를 따릅니다.

---

## A. 이 저장소에 함께 들어 있는 것

### 글꼴 (SIL Open Font License 1.1 — 전문은 [OFL.txt](OFL.txt))

| 글꼴 | 저작권 | 출처 |
|---|---|---|
| Noto Serif KR (`artifact-intelligence/fonts/NotoSerifKR.ttf`) | © 2017–2024 Adobe (http://www.adobe.com/) | https://github.com/notofonts/noto-cjk |
| Noto Sans KR (`artifact-intelligence/workspace/fonts/NotoSansKR-heading-700-900.woff2`) | © 2014–2021 Adobe, Reserved Font Name 'Source' | https://github.com/notofonts/noto-cjk |
| Pretendard (`artifact-intelligence/fonts/PretendardVariable.woff2`) | © 2023 Kil Hyung-jin, Reserved Font Name 'Pretendard' | https://github.com/orioncactus/pretendard |

세 글꼴 모두 SIL Open Font License, Version 1.1 을 따릅니다. 플러그인만 따로 설치해도 라이선스 전문이
따라가도록 글꼴 폴더 안에도 같은 `OFL.txt` 를 둡니다(`artifact-intelligence/fonts/OFL.txt`,
`artifact-intelligence/workspace/fonts/OFL.txt`).

### HWPX 서식 데이터 (Apache License 2.0 — 전문은 [LICENSE-APACHE](LICENSE-APACHE))

아래 JSON은 공개 오픈소스에서 HWPX(OWPML) 요소 순서를 뽑아낸 파생 데이터입니다.
각 파일의 `_출처` 필드에 저장소·커밋·라이선스를 함께 적어 두었습니다.

| 파일 | 출처 | 라이선스 |
|---|---|---|
| `artifact-intelligence/build/요소순서.json` | https://github.com/hancom-io/hwpx-owpml-model (Hancom Inc.) | Apache-2.0 |
| `artifact-intelligence/build/골든요소순서.json` | https://github.com/neolord0/hwpxlib | Apache-2.0 |

### 작성 규칙 원본

작성 규칙 원본(`artifact-intelligence/ontology/ontology.json`)도 이 저장소에 함께 공개합니다.
사람이 읽기 쉽게 풀어 쓴 규칙 카드는 규칙마당(https://rules.artifact-intelligence.app)에서 볼 수 있습니다.

---

## B. 따로 설치되어 실행되는 의존성 (이 저장소에 코드가 들어 있지 않음)

설치할 때 각 패키지 매니저로 받아 오며, 저장소에는 코드가 들어 있지 않습니다
(`node_modules/`, 파이썬 `.venv/`·`.hwpxenv/` 는 `.gitignore` 로 뺍니다). 각자의 라이선스를 따릅니다.

### npm (`artifact-intelligence/package.json`)
- **kordoc** 4.16.3 — 첨부 파일 읽기(HWP·HWPX·PDF·XLSX·DOCX·OCR). MIT.
- kordoc 이 함께 받는 것은 대부분 MIT 이고, 나머지도 Apache-2.0·BSD·ISC 같은 허용형 라이선스입니다.
  조건을 따로 살펴야 하는 것은 아래 둘입니다:
  - **sharp** 0.35.4(선택 의존성) — Apache-2.0. 함께 받는 libvips 바이너리 `@img/sharp-libvips-*` 1.3.3 은
    **LGPL-3.0-or-later** 입니다. 설치할 때 내려받으며 저장소에는 들어 있지 않습니다.
  - **jszip** 3.10.1 — MIT 또는 GPL-3.0-or-later 가운데 고를 수 있는 이중 라이선스입니다.

### PyPI (`artifact-intelligence/build/requirements.txt`, `mcp/requirements.txt`)
- pillow (MIT-CMU), lxml (BSD-3-Clause), fonttools (MIT), brotli (MIT),
  python-pptx (MIT), python-hwpx (Apache-2.0), mcp (MIT).
- **pymupdf** 1.28.0 — **GNU AGPL-3.0**(또는 Artifex 상용 라이선스). 배포하거나 서비스할 때 AGPL 조건을
  살펴 주세요. https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright
