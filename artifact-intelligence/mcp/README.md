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

## 규칙은 서버에 있다

이 설치본에는 규칙(온톨로지)이 없다. `서버.conf`(또는 env `문서지능_서버`)에 정책 서버가 설정돼 있어, 판정·조립·검사·조판·변환이 모두 그 서버로 위임된다 — 규칙과 무거운 처리는 서버를 떠나지 않는다. 설치하면 첫 기동 때 정책 토큰을 자동으로 받아 연결한다.

## 필요한 것

- 파이썬 3.10 이상 (첫 기동 때 이 venv 를 자동으로 만든다)

첨부 파싱·HWPX 변환·조판 검증·이미지 생성 같은 무거운 처리는 전부 서버가 하므로, 이 컴퓨터에 크롬·poppler·Node 를 따로 갖출 필요가 없다.
