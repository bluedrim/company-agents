# Active Agent Protocol

이 문서는 모든 에이전트가 독립적으로 항상 실행 중이며, 동시에 생각하고 작업할 수 있다는 전제로 회사를 운영하는 규칙입니다.

## 기본 전제

- 모든 에이전트는 자신의 역할 문서를 기준으로 상시 대기한다.
- CEO Agent의 새 지시가 나오면 모든 담당 에이전트가 동시에 검토를 시작한다.
- 각 에이전트는 다른 에이전트의 답변을 기다리지 않고 자신의 관점에서 의견을 제출한다.
- 의존성이 있는 업무만 순차 처리하고, 나머지는 병렬로 실행한다.
- 각 에이전트는 자신의 판단, 근거, 리스크, 필요한 결정을 문서로 남긴다.

## 실행 흐름

1. CEO Agent가 `CEO-TASK-DIRECTIVE.md`에 목표를 작성한다.
2. 모든 담당 에이전트가 `AGENT-OPINIONS.md`에 자신의 의견을 동시에 작성한다.
3. CEO Agent가 의견을 종합해 최종 방향을 결정한다.
4. COO Agent가 `TASK-BOARD.md`에 담당자별 업무를 분배한다.
5. 각 Manager가 팀원 업무를 더 작은 실행 단위로 쪼갠다.
6. 각 Staff가 자신의 업무를 수행하고 상태를 업데이트한다.
7. Data Analyst Agent가 결과 지표를 보고하고, CEO Agent가 다음 지시를 낸다.

## 병렬 작업 규칙

- `Blocked` 상태가 아닌 업무는 즉시 시작한다.
- 다른 팀의 산출물이 필요한 경우 `Dependency`에 명확히 적는다.
- 같은 문제를 여러 팀이 다룰 때는 각자의 관점을 유지하고, COO Agent가 중복을 정리한다.
- 리스크가 높거나 비용이 큰 일은 CEO Agent와 CFO Agent의 승인을 기다린다.
- 법무, 개인정보, 보안 이슈가 있는 일은 Legal Agent와 CTO Agent가 동시에 검토한다.

## 상태값

- `Backlog`: 아직 시작하지 않은 업무
- `Ready`: 바로 시작 가능한 업무
- `In Progress`: 진행 중인 업무
- `Blocked`: 의사결정, 자료, 외부 입력이 필요해 멈춘 업무
- `Review`: 결과물 검토 중
- `Done`: 완료된 업무

## 에이전트별 기본 반응 시간

- CEO Agent: 새 목표와 최종 결정 작성
- COO Agent: 업무 분배, 일정, 병목 관리
- CFO Agent: 비용, 가격, 수익성 영향 검토
- CTO Agent: 기술 가능성, 일정, 보안 영향 검토
- CPO Agent: 고객 문제, 제품 범위, 사용자 경험 검토
- CMO Agent: 시장 메시지, 채널, 캠페인 검토
- Sales Agent: 고객 반응, 영업 가능성, 계약 가능성 검토
- Customer Success Agent: 온보딩, 유지율, 고객 만족도 영향 검토
- HR Agent: 인력, 역할, 협업 방식 검토
- Legal Agent: 계약, 규제, 개인정보, 지식재산권 검토
- Data Analyst Agent: 성공 지표, 실험 설계, 데이터 수집 검토
- Strategy and Research Manager: 시장 선택, 경쟁 전략, 전략 가설 검토
- Partnerships Manager: 제휴, 채널, 외부 생태계 기회 검토
- Security and Risk Manager: 보안, 개인정보, 운영 리스크 검토
- Internal Systems Manager: 사내 도구, 계정, 문서, 자동화 운영 검토
- Procurement Manager: 구매, 외주, 공급업체, 갱신 리스크 검토

## 산출물 규칙

- 모든 의견은 실행 가능한 제안으로 끝나야 한다.
- 모든 업무는 담당자, 마감일, 완료 기준을 가져야 한다.
- 완료 기준이 모호한 업무는 `Ready`가 될 수 없다.
- 완료된 업무는 결과, 근거 자료, 다음 제안을 함께 남긴다.
