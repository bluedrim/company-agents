# Team Tools

이 문서는 각 팀이 업무를 실행할 때 사용하는 도구 목록입니다.
도구는 문서 템플릿, 체크리스트, 계산표, 리포트 양식, 실행 보드로 구성됩니다.

## Tool Governance

- 모든 도구는 owner team, purpose, expected output, review cadence를 가져야 한다.
- register, tracker, board 도구는 owner, status, due date, next action 필드를 반드시 포함한다.
- decision, review, checklist 도구는 decision owner와 approval 상태를 남긴다.
- 고객, 비용, 보안, 법무에 영향을 주는 도구는 관련 팀 리뷰어를 명시한다.
- 사용하지 않는 도구는 월 1회 정리하고, 중복 도구는 하나로 합친다.

## Tool Lifecycle

1. `Proposed`: 필요성이 제기된 도구
2. `Active`: 팀 업무에 사용 중인 도구
3. `Deprecated`: 더 이상 쓰지 않기로 한 도구
4. `Merged`: 다른 도구로 통합된 도구

## Tool Creation Flow

1. `TEAM-TOOLS.md`에 도구 목적과 기대 산출물을 정의한다.
2. `team-tools/tool-registry.json`에 도구 이름, 유형, 템플릿을 등록한다.
3. `./company-agents/run-agents --materialize-tools`로 실제 도구 파일을 생성한다.
4. 팀별 README에서 도구가 올바르게 생성됐는지 확인한다.
5. agent 실행 결과의 `Team Tools` 섹션에서 연결 여부를 확인한다.

## Company Layer

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| CEO Decision Log | Decision log | 중요한 결정을 배경, 선택지, 결론으로 기록 | 결정 로그 |
| Company North Star Dashboard | Dashboard | 회사 최상위 지표와 팀 KPI를 연결 | 경영 대시보드 |
| Strategic Priority Matrix | Prioritization matrix | 이번 사이클에 할 일과 하지 않을 일을 구분 | 우선순위 표 |

## Executive Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Directive Intake Form | Intake template | CEO 지시를 실행 가능한 항목으로 변환 | 실행 요청서 |
| Decision Brief Template | Brief template | 선택지, 근거, 추천안을 한 페이지로 요약 | 의사결정 브리프 |
| Priority Conflict Resolver | Review checklist | 팀 간 우선순위 충돌을 정리 | 충돌 해결 메모 |

## Operations Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Task Intake Queue | Work queue | 모든 업무 요청을 한곳에 접수 | 업무 접수표 |
| Blocker Log | Risk log | 막힌 업무의 원인, 결정권자, 다음 확인 시간을 추적 | 병목 로그 |
| Process Checklist Builder | Template builder | 반복 업무를 체크리스트로 표준화 | 운영 체크리스트 |

## Finance Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Monthly Budget Sheet | Spreadsheet template | 팀별 예산, 실제 지출, 차이를 추적 | 월간 예산표 |
| Burn Rate Calculator | Calculator | 현금 소진 속도와 runway를 계산 | runway 리포트 |
| Pricing Margin Model | Financial model | 가격, 원가, 할인 조건별 margin을 비교 | 수익성 분석표 |

## Product Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| PRD Template | Product spec | 고객 문제, 범위, 완료 기준을 정의 | PRD |
| Feature Prioritization Matrix | Prioritization matrix | 기능을 가치, 난이도, 리스크로 평가 | 기능 우선순위표 |
| User Interview Kit | Research kit | 인터뷰 질문, 노트, 인사이트를 관리 | 인터뷰 리포트 |

## Engineering Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Architecture Decision Record | Decision log | 기술 선택과 근거를 기록 | ADR |
| Release Checklist | Release checklist | 테스트, 보안, 롤백 기준을 확인 | 릴리스 체크리스트 |
| Bug Triage Board | Triage board | 버그 심각도, 재현 조건, owner를 관리 | 버그 보드 |

## Marketing Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Campaign Experiment Planner | Experiment template | 캠페인 가설, 채널, 성공 기준을 정의 | 캠페인 실험안 |
| Content Calendar | Calendar | 콘텐츠 주제, 채널, 발행일을 관리 | 콘텐츠 캘린더 |
| Message Testing Matrix | Testing matrix | 고객 문제별 메시지 반응을 비교 | 메시지 테스트표 |

## Sales Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| CRM Pipeline Board | Pipeline board | 리드, 단계, 다음 액션, 예상 매출을 관리 | 영업 파이프라인 |
| Discovery Call Script | Script | 고객 문제, 예산, 의사결정 과정을 질문 | 미팅 스크립트 |
| Objection Log | Feedback log | 반대 의견과 대응 메시지를 축적 | 반대 의견 로그 |

## Customer Success Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Onboarding Tracker | Tracker | 고객별 첫 30일 온보딩 상태를 관리 | 온보딩 현황 |
| Health Scorecard | Scorecard | 사용량, 문의, 만족도, 이탈 위험을 점수화 | 고객 건강도 |
| Feedback Triage Board | Triage board | 피드백을 버그, 기능 요청, 교육 이슈로 분류 | 피드백 보드 |

## People Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Role Scorecard | Role template | 역할의 책임, 권한, 성공 기준을 정의 | 역할 정의서 |
| Hiring Pipeline Tracker | Pipeline tracker | 후보자 단계와 평가를 관리 | 채용 파이프라인 |
| Onboarding Plan Builder | Plan template | 신규 합류자의 30/60/90일 계획을 작성 | 온보딩 계획 |

## Legal and Compliance Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Contract Review Checklist | Review checklist | 계약서 핵심 조항과 예외를 검토 | 계약 검토표 |
| Privacy Impact Assessment | Risk assessment | 개인정보 수집, 이용, 보관 리스크를 평가 | PIA |
| Clause Library | Reference library | 표준 조항과 금지 조항을 관리 | 조항 라이브러리 |

## Data Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Metric Dictionary | Data dictionary | 지표 정의, owner, source를 관리 | 지표 사전 |
| Experiment Readout Template | Analysis template | 실험 결과와 다음 액션을 정리 | 실험 분석 리포트 |
| Data Quality Monitor | Quality checklist | 누락, 중복, 지연 데이터를 점검 | 데이터 품질 로그 |

## Strategy and Research Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Market Attractiveness Matrix | Strategy matrix | 시장을 규모, 긴급성, 접근성으로 평가 | 시장 선택표 |
| Competitive Battlecard | Competitive brief | 경쟁사 강점, 약점, 대응 메시지를 정리 | 경쟁 대응표 |
| Strategic Bet Register | Bet register | 전략 가설, 검증 계획, 폐기 기준을 추적 | 전략 가설 등록부 |

## Partnerships and Business Development Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Partner Pipeline Board | Pipeline board | 파트너 후보, 단계, 다음 액션을 관리 | 파트너 파이프라인 |
| Partner Fit Scorecard | Scorecard | 파트너 적합도와 리스크를 평가 | 파트너 점수표 |
| Co-Marketing Plan Template | Plan template | 공동 마케팅 목표, 역할, 일정 정의 | 공동 마케팅 계획 |

## Security and Risk Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Risk Register | Risk register | 리스크, owner, 완화 액션, 기한을 관리 | 리스크 등록부 |
| Security Review Checklist | Review checklist | 출시 전 인증, 권한, 데이터 보안을 점검 | 보안 검토표 |
| Incident Response Runbook | Runbook | 사고 대응 역할, 순서, 고객 안내를 정의 | 사고 대응 문서 |

## Internal Systems and IT Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Access Request Form | Request form | 계정 생성, 권한 변경, 접근 회수를 접수 | 접근 권한 요청서 |
| Automation Backlog | Backlog | 자동화 후보를 효과, 난이도, 리스크로 평가 | 자동화 백로그 |
| Knowledge Base Index | Index | 문서 위치, owner, 갱신일을 관리 | 지식관리 색인 |

## Procurement and Vendor Management Team

| Tool | Type | Purpose | Output |
| --- | --- | --- | --- |
| Vendor Register | Vendor register | 공급업체, 비용, owner, 갱신일을 관리 | 공급업체 관리표 |
| Purchase Request Form | Request form | 구매 필요성, 비용, 대안, 승인자를 기록 | 구매 요청서 |
| Outsourcing RFP Template | RFP template | 외주 범위, 산출물, 검수 기준을 정의 | 외주 요청서 |
