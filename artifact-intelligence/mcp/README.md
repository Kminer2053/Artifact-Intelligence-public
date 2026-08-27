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

## 온톨로지는 서버, 처리는 로컬

이 설치본에는 온톨로지 지식 정본(개체×3요소·목차·판별 신호)이 없다 — 그것은 정책 서버에만 있고, `서버.conf`(또는 env `문서지능_서버`)로 연결해 판정·작성에 필요한 조각만 그때그때 받아온다. 반면 판정·조립·검사·조판·변환은 사용자 문서를 다루므로 이 설치본에서 로컬로 돈다(자료를 서버로 보내지 않는다 — 사용자 정보보호 1순위). 그 처리에 필요한 규칙 코드는 설치본에 함께 온다. 설치하면 첫 기동 때 정책 토큰을 자동으로 받아 연결한다.

## 필요한 것

- 파이썬 3.10 이상 (첫 기동 때 이 venv 를 자동으로 만든다)

첨부 파싱·HWPX 변환·조판 검증·이미지 생성 같은 무거운 처리는 전부 서버가 하므로, 이 컴퓨터에 크롬·poppler·Node 를 따로 갖출 필요가 없다.
