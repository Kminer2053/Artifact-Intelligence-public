# 문서지능 MCP 서버

`workspace/api.py` 의 작업 목록에서 도구를 자동 생성하는 stdio MCP 서버. 스킬·MCP·웹앱
세 문이 그 단일 목록을 공유하므로 어긋나지 않는다. 관리자 작업은 `목록()` 이 걸러 MCP 에
안 실린다.

## 설치 (배포 후 한 번)

배포 트리에는 `.venv` 가 없다(재생성물). 파이썬 가상환경을 만들고 의존성을 넣는다:

```bash
python3 -m venv mcp/.venv
mcp/.venv/bin/pip install -r mcp/requirements.txt
```

## 등록

Claude Code **플러그인**으로 설치하면 `.mcp.json` 이 자동 등록한다
(`command: ${CLAUDE_PLUGIN_ROOT}/mcp/.venv/bin/python`).

수동 등록(예: Claude Code CLI):

```bash
claude mcp add artifact-intelligence -- <절대경로>/mcp/.venv/bin/python <절대경로>/mcp/server.py
```

이 설치본은 로컬 stdio 로 쓴다. (원격 HTTP 공유 MCP 는 인증·세션 격리를 갖춰 정책 서버 쪽에서 별도로 제공된다.)

## 규칙도 처리도 로컬

온톨로지 지식 정본(개체×3요소·목차·판별 신호, `ontology/ontology.json`)은 이 설치본에 함께 들어 있다('26-09-25 완전 공개). 판정·작성 지침·조립·검사·조판·변환이 모두 이 파일과 설치본 코드로 로컬에서 돈다. 사용자 문서를 다루는 일이라 자료를 서버로 보내지 않는다(사용자 정보보호 1순위). 예외는 편집 화면의 'AI로 고치기'를 사용자 API 키 없이 쓸 때뿐이다 — 고른 글 조각(표 셀 포함)만 정책 서버의 모델로 보낸다. (`서버.conf`/`문서지능_서버`는 다른 스위치 — 문서 처리까지 전부 서버에 맡기는 얇은 설치 모드라, 이 설치본에서는 쓰지 않는다.)

## 필요한 것

- 파이썬 3.10 이상 (첫 기동 때 이 venv 를 자동으로 만든다)

- 크롬(조판 검사·PDF), poppler(`pdftotext`·`pdftoppm`), Node(`npm` — 파일 업로드 파서) — 판정·조립·조판·변환이 이 컴퓨터에서 로컬로 돌기 때문이다

파이썬 쪽 의존성(HWPX 변환 venv·업로드 파서 kordoc·그림 자르기용 Pillow)은 첫 기동 때 자동으로 깔린다. `mcp/requirements.txt` 가 바뀌면 다음 기동 때 있는 venv 에도 다시 깐다. 크롬이 없으면 실행 시 설치 방법을 안내한다.
