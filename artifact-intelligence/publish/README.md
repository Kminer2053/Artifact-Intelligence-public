# 문서지능 · Artifact Intelligence

의도와 자료만 주면, 대한민국 공공기관 보고서를 **결재 가능한 시각 품질**로 만들어 주는 플러그인입니다. 1페이지 보고서·풀버전·시행문·규정·보도자료를 HTML·인쇄용 PDF·한글(HWPX)로 냅니다. 문서 3요소(구성·문체·디자인)의 규칙에 근거해 거의 완성된 초안을 만들고, 사람은 리터칭만 합니다.

**먼저 써 보기:** 설치 없이 웹에서 바로 — **https://artifact-intelligence.app**

---

## Claude Code 에서 설치

```
/plugin marketplace add Kminer2053/Artifact-Intelligence-public
/plugin install artifact-intelligence@artifact-intelligence
```

`/plugin` 을 열면 Discover 탭에서 찾아 설치할 수도 있습니다. 설치하면 스킬과 MCP 도구 42종이 함께 붙습니다.

## Codex 에서 설치

스킬과 MCP 를 둘 다 그대로 씁니다.

```bash
# 이 저장소를 받은 뒤 (또는 원하는 위치에 clone)
git clone https://github.com/Kminer2053/Artifact-Intelligence-public
cd Artifact-Intelligence-public/artifact-intelligence

# MCP 도구 등록
codex mcp add artifact-intelligence -- "$(pwd)/mcp/run.sh"

# 스킬 인식(폴더째 두면 됩니다)
mkdir -p ~/.agents/skills && ln -s "$(pwd)" ~/.agents/skills/artifact-intelligence
```

---

## 어떻게 도나요

- **규칙(온톨로지)은 서버에만 있습니다.** 설치본에는 규칙이 없고, 판정·프롬프트 조립 같은 규칙 작업만 정책 서버(artifact-intelligence.app)에 위임합니다. 초안 작성과 렌더링(HTML·PDF·HWPX)은 설치한 컴퓨터에서 돕니다.
- **설치하면 토큰을 자동으로 하나 받아 갑니다.** 첫 기동 때 부트스트랩이 정책 서버에서 토큰을 받아 둡니다(사용량은 이 토큰으로 관리됩니다). 웹앱은 토큰 없이 누구나 쓸 수 있습니다.
- **개인정보:** 문서 내용은 세션 안에서만 다루고, 무응답 10분이면 세션과 자료가 지워집니다.

## 필요한 것

- Python 3.10 이상 (HWPX·MCP·업로드 파싱에 필요 — 없으면 HTML 초안까지는 됩니다)
- Node.js (파일 업로드 파싱 kordoc 에만 필요, 선택)
- 첫 기동 때 의존성을 자동으로 한 번 설치합니다(부트스트랩).

## 무엇을 만들 수 있나

| 양식 | 쓰임 |
|---|---|
| 1페이지 보고서 | 의사결정자용 한 장 요약 |
| 풀버전 보고서 | 표지·목차·요약·본문의 다쪽 보고서 |
| 시행문 | 외부기관·국민 대상 공문 |
| 규정 | 내규·지침 |
| 보도자료 | 언론 배포용 |

---

문의 · 토큰 발급: park2053@gmail.com
