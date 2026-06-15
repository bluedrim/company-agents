# Company Agents

이 폴더는 일반적인 회사 구조를 에이전트 단위로 나눈 운영 문서입니다.
각 에이전트는 독립적으로 판단하고 실행하되, 공통 목표와 의사결정 규칙을 공유합니다.

## 공통 목표

- 고객에게 명확한 가치를 제공한다.
- 반복 가능한 매출 구조를 만든다.
- 작게 실험하고 빠르게 학습한다.
- 문서, 지표, 회고를 통해 조직 지식을 축적한다.

## 운영 방식

- 각 에이전트는 자신의 Markdown 파일을 기준으로 업무를 수행한다.
- 모든 에이전트는 독립적으로 항상 실행 중이라고 가정한다.
- 모든 에이전트는 동시에 생각하고, 자신의 담당 범위 안에서 병렬로 작업할 수 있다.
- CEO Agent가 회사 목표와 우선순위를 제시하면 각 담당 에이전트는 독립적으로 의견을 제출한다.
- CEO Agent는 담당자 의견을 종합해 최종 결정을 내리고, COO Agent는 이를 실행 업무로 분배한다.
- 모든 에이전트는 주간 단위로 진행 상황, 위험 요소, 다음 액션을 업데이트한다.
- 중요한 의사결정은 `CEO-Agent.md`에 요약하고 관련 에이전트 문서에 상세 내용을 남긴다.
- 고객, 매출, 제품 품질에 직접 영향을 주는 이슈는 우선순위를 높인다.
- 보안, 법무, 재무 리스크가 있는 업무는 Security and Risk, Legal, Finance 관점에서 동시에 검토한다.
- 외부 파트너, 공급업체, 도구 구매가 필요한 업무는 Partnerships, Procurement, Internal Systems 관점에서 함께 검토한다.

## 에이전트 목록

- [CEO Agent](CEO-Agent.md): 비전, 전략, 최종 의사결정
- [COO Agent](COO-Agent.md): 운영 체계, 실행 관리, 프로세스 개선
- [CFO Agent](CFO-Agent.md): 재무, 예산, 수익성 관리
- [CTO Agent](CTO-Agent.md): 기술 전략, 아키텍처, 개발 생산성
- [CPO Agent](CPO-Agent.md): 제품 전략, 로드맵, 사용자 경험
- [CMO Agent](CMO-Agent.md): 브랜드, 마케팅, 성장 실험
- [Sales Agent](Sales-Agent.md): 영업 파이프라인, 제안, 계약
- [Customer Success Agent](Customer-Success-Agent.md): 온보딩, 유지율, 고객 피드백
- [HR Agent](HR-Agent.md): 채용, 조직문화, 성과 관리
- [Legal Agent](Legal-Agent.md): 계약, 리스크, 규정 준수
- [Data Analyst Agent](Data-Analyst-Agent.md): 지표, 분석, 실험 해석
- [Team Staffing](TEAM-STAFFING.md): 팀별 매니저, 직원 배치, 세부 업무
- [Team Playbooks](TEAM-PLAYBOOKS.md): 팀별 미션, KPI, 입력/출력, 개선 액션
- [Team Tools](TEAM-TOOLS.md): 팀별 실행 도구와 템플릿
- [Active Agent Protocol](ACTIVE-AGENT-PROTOCOL.md): 항상 실행 중인 병렬 에이전트 운영 규칙
- [CEO Task Directive](CEO-TASK-DIRECTIVE.md): CEO가 목표를 내리고 최종 결정을 정리하는 문서
- [Agent Opinions](AGENT-OPINIONS.md): 각 담당자가 CEO 지시에 대해 의견을 내는 문서
- [Task Board](TASK-BOARD.md): 최종 결정 이후 담당자별 실행 업무 보드
- [Running Agents](RUNNING-AGENTS.md): 모든 에이전트를 병렬 실행하는 방법
- [Organization Operating Model](ORG-OPERATING-MODEL.md): 확장 조직의 책임 경계와 의사결정 라우팅

## 실행 방법

```sh
./company-agents/run-agents --once
```

이 명령은 모든 executive, manager, staff 에이전트를 병렬로 실행하고 `company-agents/runtime/` 아래에 상태, 로그, 산출물을 생성한다.
각 실행은 `runtime/outputs/session-001/`, `session-002/`처럼 번호가 붙은 별도 output을 남기며, `runtime/status.json` 등은 최신 실행을 가리킨다.
`runtime/outputs/SESSION-INDEX.md`에서 세션을 순서대로 볼 수 있고, 새 세션은 직전 세션의 결과를 읽어 개선 컨텍스트로 사용한다.
이전 세션이 없으면 `session_mode=initial`로 최초 실행을 시작하고, 이전 세션이 있으면 `session_mode=continue`로 기록한 뒤 직전 세션을 이어서 개선한다.
각 팀의 산출물은 `runtime/outputs/session-###/work-products/{team}/{agent}.md`와 최신 mirror인 `runtime/work-products/{team}/{agent}.md`에 저장된다.
세션 종료 시 `CEO-SESSION-REVIEW.md`에 CEO의 팀별 평가와 다음 세션 지시를 따로 남긴다.
`TEAM-ACTIVITY-PLAN.md`는 각 팀이 다음 세션에서 바로 해야 할 일, 다른 팀에 요청할 일, 에스컬레이션할 일, 다음 세션까지 남길 일을 구분한다.
`TEAM-SESSION-RESULTS.md`는 이번 세션에서 각 팀이 남긴 결과물만 따로 모아 보여준다.
다음 세션은 직전 세션의 팀별 산출물, CEO 세션 리뷰, 팀 활동 계획을 읽고 필요한 것은 발전시키며, 더 이상 필요하지 않은 산출물은 사용하지 않아도 된다는 지시를 agent prompt에 포함한다.
각 실행은 `runtime/DASHBOARD.md`, `runtime/CYCLE-BRIEF.md`, `runtime/OPERATING-REVIEW.md`, `runtime/CEO-SESSION-REVIEW.md`, `runtime/TEAM-ACTIVITY-PLAN.md`, `runtime/TEAM-SESSION-RESULTS.md`를 함께 만들어 운영자가 팀별 업무량, 결과물, 실패 agent, 승인 필요사항, CEO 평가, 다음 세션 지시를 빠르게 확인할 수 있게 한다.
LLM 연결은 필수이며, 연결되지 않으면 이유를 출력하고 실행을 종료한다.
LLM 설정은 `company-agents/.env`에서 관리하며, Ollama, OpenAI-compatible `gpt_oss`, `chatgpt_oauth` bearer token provider를 사용할 수 있다.
최초 CEO task를 사용자 입력으로 시작하려면 아래처럼 실행한다.

```sh
./company-agents/run-agents --once --task "신규 고객 온보딩 자동화 MVP를 만든다."
./company-agents/run-agents --once --ask-task
```

입력된 task는 `CEO-TASK-DIRECTIVE.md`의 현재 지시와 `TASK-BOARD.md`의 현재 사이클 목표에 반영된다.
계속 실행하려면 아래 명령을 사용한다.

```sh
./company-agents/run-agents --watch --interval 60
```

watch 모드에서는 각 세션 사이에 60초 동안 대기하며, 터미널에 `stop`을 입력하고 Enter를 누르면 다음 세션을 시작하지 않고 종료한다.

백그라운드에서 항상 실행하려면 아래 명령을 사용한다.

```sh
./company-agents/start-agents 60
```

상태 확인과 중지는 아래 명령을 사용한다.

```sh
./company-agents/agent-status
./company-agents/stop-agents
```

`agent-status`와 실행 완료 화면은 cycle, output, LLM, 실패 이유, 주요 파일 경로를 한 화면에 요약한다.

특정 팀만 실행하려면 아래처럼 실행한다.

```sh
./company-agents/run-agents --once --team "Security"
./company-agents/run-agents --once --team "Partnerships"
```

팀별 도구 목록은 아래처럼 확인한다.

```sh
./company-agents/run-agents --list-tools
./company-agents/run-agents --list-tools --team "Sales"
./company-agents/run-agents --materialize-tools
./company-agents/run-agents --tools-health
./company-agents/run-tests
```

## 주간 리듬

1. CEO Agent가 이번 사이클의 목표와 판단 기준을 제시한다.
2. 각 담당 에이전트가 동시에 의견, 리스크, 필요 자원을 제출한다.
3. CEO Agent가 의견을 종합해 최종 방향을 정한다.
4. COO Agent가 최종 방향을 담당자별 실행 업무로 분배한다.
5. 각 Manager와 Staff는 자신의 업무를 독립적으로 실행하고 진행 상태를 업데이트한다.
6. 금요일에는 결과, 배운 점, 다음 사이클 제안을 정리한다.
