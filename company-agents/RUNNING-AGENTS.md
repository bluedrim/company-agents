# Running Agents

이 문서는 회사 에이전트 실행 방법을 설명합니다.

## 한 번 실행

```sh
./company-agents/run-agents --once
```

실행하면 모든 executive, manager, staff 에이전트가 병렬로 한 번씩 작동합니다.
결과는 아래 위치에 생성됩니다.

- `company-agents/runtime/outputs/session-001/`, `session-002/`, ...: 실행별 독립 output 디렉터리
- `company-agents/runtime/outputs/SESSION-INDEX.md`: 세션을 순서대로 볼 수 있는 인덱스
- `company-agents/runtime/status.json`: 전체 실행 상태
- `company-agents/runtime/DASHBOARD.md`: 사람이 읽기 쉬운 요약 대시보드
- `company-agents/runtime/CYCLE-BRIEF.md`: CEO/COO가 바로 볼 수 있는 이번 사이클 운영 브리프
- `company-agents/runtime/OPERATING-REVIEW.md`: 운영 게이트, 승인 필요사항, 다음 세션 지시
- `company-agents/runtime/CEO-SESSION-REVIEW.md`: CEO의 팀별 평가와 다음 세션 지시
- `company-agents/runtime/TEAM-ACTIVITY-PLAN.md`: 팀별 선제 행동, 협업 요청, 에스컬레이션, 다음 액션
- `company-agents/runtime/TEAM-SESSION-RESULTS.md`: 이번 세션의 팀별 결과물 본문 요약
- `company-agents/runtime/team-results/{team}.md`: 팀별 실제 결과 문서
- `company-agents/runtime/TOOL-USAGE.md`: 업무별 추천 도구 리포트
- `company-agents/runtime/tool-usage.json`: 업무별 추천 도구 JSON
- `company-agents/runtime/TOOL-AUDIT.md`: 도구 커버리지, 미사용 도구, 추천 품질 리포트
- `company-agents/runtime/agent-logs/`: 에이전트별 heartbeat 로그
- `company-agents/runtime/work-products/{team}/{agent}.md`: 팀별로 정리된 최신 작업 산출물

`runtime/status.json`, `runtime/DASHBOARD.md`, `runtime/CYCLE-BRIEF.md`, `runtime/OPERATING-REVIEW.md`, `runtime/CEO-SESSION-REVIEW.md`, `runtime/TEAM-ACTIVITY-PLAN.md`, `runtime/TEAM-SESSION-RESULTS.md`, `runtime/team-results/`, `runtime/agent-logs/`, `runtime/work-products/`는 최신 실행을 가리키는 latest 출력입니다.
실행 이력은 `runtime/outputs/session-###/` 아래에 보존됩니다.
각 새 세션은 직전 세션의 `status.json`과 `CYCLE-BRIEF.md`를 읽고, 이전 결과를 개선하는 컨텍스트로 agent prompt에 포함합니다.
이전 세션이 없으면 `session_mode=initial`, 이전 세션이 있으면 `session_mode=continue`로 상태와 콘솔에 표시됩니다.
직전 세션의 `CEO-SESSION-REVIEW.md`도 함께 읽어 각 팀이 CEO 평가와 다음 지시를 반영합니다.
직전 세션의 `TEAM-ACTIVITY-PLAN.md`도 함께 읽어 각 팀이 수동 대기하지 않고 선제 행동을 이어갑니다.
직전 세션의 `work-products/{team}/` 산출물도 함께 발췌해 prompt에 넣습니다. Agent는 필요한 산출물을 발전시키고, 더 이상 필요하지 않은 산출물은 사용하지 않아도 됩니다.

## 사용자 최초 task 입력

CEO의 최초 지시를 사용자 입력에서 시작하려면 아래 옵션을 사용합니다.

```sh
./company-agents/run-agents --once --task "신규 고객 온보딩 자동화 MVP를 만든다."
./company-agents/run-agents --once --task-file ./first-task.txt
./company-agents/run-agents --once --ask-task
```

입력된 task는 `CEO-TASK-DIRECTIVE.md`의 `Current Directive`로 저장되고, `TASK-BOARD.md`의 현재 사이클 목표도 같은 내용으로 갱신됩니다.
그 다음 모든 agent가 해당 CEO 지시를 공통 컨텍스트로 받아 병렬 실행됩니다.

## 특정 에이전트만 실행

```sh
./company-agents/run-agents --once --agent "CEO"
./company-agents/run-agents --once --agent "frontend"
./company-agents/run-agents --once --team "Security"
```

사용 가능한 에이전트 목록은 아래 명령으로 확인합니다.

```sh
./company-agents/run-agents --list-agents
```

## 팀별 도구 확인

```sh
./company-agents/run-agents --list-tools
./company-agents/run-agents --list-tools --team "Security"
```

팀별 도구 정의는 `company-agents/TEAM-TOOLS.md`에 있고, 재사용 가능한 템플릿은 `company-agents/team-tools/`에 있습니다.
각 agent 산출물에는 자신의 팀에서 쓸 수 있는 도구가 `Team Tools` 섹션으로 자동 포함됩니다.

팀별 도구 파일을 실제 파일로 생성하려면 아래 명령을 사용합니다.

```sh
./company-agents/run-agents --materialize-tools
./company-agents/run-agents --materialize-tools --team "Sales"
```

생성된 도구 파일은 `company-agents/team-tools/generated/` 아래에 팀별 폴더로 저장됩니다.
생성된 도구 파일은 `TEAM-TOOLS.md`의 purpose/output을 반영하며, CSV 도구에는 바로 편집할 수 있는 예시 행이 포함됩니다.
agent 실행 시 현재 업무에 맞는 추천 도구가 자동으로 산출물과 `runtime/TOOL-USAGE.md`에 기록됩니다.

도구 정의와 템플릿이 빠짐없이 연결되어 있는지 확인하려면 아래 명령을 사용합니다.

```sh
./company-agents/run-agents --tools-health
./company-agents/run-agents --show-tool-audit
./company-agents/run-agents --doctor
```

agent 실행 후 도구 추천에는 `score`, `confidence`, `matched terms`가 포함됩니다.
`TOOL-AUDIT.md`에서는 전체 등록 도구 중 실제 추천된 도구 비율과 미사용 도구를 확인할 수 있습니다.

전체 구조가 정상 연결되어 있는지 확인하려면 `--doctor`를 사용합니다.
이 명령은 agent, task, playbook, tool 연결 누락을 점검합니다.

## 자동 테스트

```sh
./company-agents/run-tests
```

테스트는 agent 수, task 연결, playbook/tools 연결, doctor, filtered run cycle을 검증합니다.

## LLM 연결

LLM 설정은 `company-agents/.env`에서 관리합니다.

Ollama를 사용할 때:

```sh
ollama pull gpt-oss:20b
ollama serve
```

```env
LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
LLM_CONCURRENCY=2
```

OpenAI-compatible gpt-oss 서버를 사용할 때:

```env
LLM_ENABLED=true
LLM_PROVIDER=gpt_oss
GPT_OSS_BASE_URL=http://localhost:8000/v1
GPT_OSS_MODEL=gpt-oss
GPT_OSS_API_KEY=
LLM_CONCURRENCY=2
```

ChatGPT OAuth bearer token을 사용할 때:

```env
LLM_ENABLED=true
LLM_PROVIDER=chatgpt_oauth
CHATGPT_OAUTH_BASE_URL=https://api.openai.com/v1
CHATGPT_OAUTH_MODEL=<model-name>
CHATGPT_OAUTH_ACCESS_TOKEN=
CHATGPT_OAUTH_TOKEN_FILE=~/.config/company-agents/chatgpt-oauth-token
LLM_CONCURRENCY=2
```

`CHATGPT_OAUTH_ACCESS_TOKEN`은 shell 환경변수로 주입하는 것을 권장합니다.
토큰 파일을 쓰는 경우 해당 파일은 repo 밖 또는 `.gitignore`에 포함된 위치에 둡니다.
이 provider는 bearer token을 OpenAI-compatible `/chat/completions` 엔드포인트에 전달합니다.

LLM 연결은 필수입니다.
LLM이 꺼져 있거나 설정이 불완전하거나 연결에 실패하면 실행은 즉시 종료되고, 실패 이유가 터미널과 `runtime/CYCLE-BRIEF.md`에 기록됩니다.
fallback 산출물은 생성하지 않습니다.
LLM 응답이 너무 짧거나 필수 섹션이 부족하면 runner가 한 번 더 구체적인 산출물을 요청합니다.
재요청 후에도 얕은 답변이면 해당 agent는 실패 처리되어 한두 줄짜리 결과가 성공으로 기록되지 않습니다.
동시에 너무 많은 로컬 모델 호출이 부담되면 `LLM_AGENT_LIMIT`를 줄이는 대신 `--agent` 또는 `--team`으로 실행 대상을 줄입니다.
선택된 agent 수보다 `LLM_AGENT_LIMIT`가 작으면 실행은 실패합니다.
로컬 모델이 한 번에 여러 요청을 감당하지 못하면 `LLM_CONCURRENCY` 값을 `1`로 둡니다.

연결만 확인하려면 아래 명령을 사용합니다.

```sh
./company-agents/run-agents --test-llm
```

## 계속 실행

```sh
./company-agents/run-agents --watch --interval 60
```

60초마다 모든 에이전트가 다시 병렬 실행됩니다.
각 에이전트는 자신의 문서, `TASK-BOARD.md`, 팀 배치 문서를 읽고 현재 담당 업무를 갱신합니다.
대기 중 터미널에 `stop`을 입력하고 Enter를 누르면 다음 세션을 시작하지 않고 종료합니다.

## 백그라운드로 항상 실행

```sh
./company-agents/start-agents 60
```

위 명령은 에이전트들을 백그라운드에서 계속 실행합니다.
실행 중지와 상태 확인은 아래 명령을 사용합니다.

```sh
./company-agents/agent-status
./company-agents/stop-agents
```

`agent-status`는 process 상태, cycle, 실행별 output, LLM 연결 상태, 실패 이유, 주요 파일 경로를 터미널 화면에 요약합니다.
백그라운드 출력은 `company-agents/runtime/company-agents.out`에 저장됩니다.

## 실행 모델

- 모든 에이전트는 독립 worker로 실행된다.
- 실행은 병렬 ThreadPool로 처리된다.
- LLM 호출은 `LLM_CONCURRENCY` 값으로 별도 제한된다.
- 각 에이전트는 자기 로그와 자기 산출물만 쓴다.
- 전체 상태는 `runtime/status.json`에 모인다.
- 요약 대시보드는 `runtime/DASHBOARD.md`에 생성된다.
- LLM 연결은 필수이며 실패 시 이유를 출력하고 실행을 종료한다.

## 다음 확장 지점

- `TASK-BOARD.md`의 상태를 자동으로 갱신하도록 확장할 수 있다.
- 장기 실행 모드에서 특정 에이전트만 재실행하는 옵션을 추가할 수 있다.
