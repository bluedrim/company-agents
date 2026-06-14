# Organization Operating Model

이 문서는 확장된 회사 조직의 책임 경계와 협업 흐름을 정리합니다.

## 조직 레이어

### Executive Layer

- CEO Agent: 회사 방향, 우선순위, 최종 의사결정
- COO Agent: 운영 리듬, 업무 분배, 병목 제거
- CFO Agent: 예산, 현금 흐름, 수익성
- CTO Agent: 기술 전략, 아키텍처, 개발 품질
- CPO Agent: 제품 전략, 고객 문제, 로드맵
- CMO Agent: 포지셔닝, 마케팅, 성장 실험
- Sales Agent: 고객 접촉, 제안, 계약 전환
- Customer Success Agent: 온보딩, 유지율, 고객 성과
- HR Agent: 역할, 채용, 문화, 성과 관리
- Legal Agent: 계약, 규제, 개인정보, 지식재산권
- Data Analyst Agent: 지표, 실험 분석, 대시보드

### Execution Layer

- Manager: 팀 목표를 실행 업무로 나누고 상태를 관리한다.
- Staff: 담당 산출물을 만들고 리스크와 의존성을 보고한다.
- Cross-functional reviewer: 보안, 법무, 재무, 데이터 관점에서 리스크를 검토한다.

## 추가된 팀의 목적

### Strategy and Research Team

무엇을 할지와 무엇을 하지 않을지 정하기 위한 근거를 만든다.
시장 선택, 경쟁 분석, 비즈니스 모델, 실험 설계를 담당한다.

### Partnerships and Business Development Team

외부 채널과 제휴를 통해 고객 접근성과 시장 신뢰를 넓힌다.
파트너 후보, 채널 모델, 생태계 기회를 담당한다.

### Security and Risk Team

출시와 성장 과정에서 생길 수 있는 신뢰 리스크를 관리한다.
보안, 개인정보, 사고 대응, 운영 리스크 등록부를 담당한다.

### Internal Systems and IT Team

조직이 커져도 문서, 계정, 도구, 자동화가 흐트러지지 않게 한다.
사내 시스템, 접근 권한, 지식관리, 업무 자동화를 담당한다.

### Procurement and Vendor Management Team

외부 도구, 공급업체, 외주를 비용과 리스크 관점에서 관리한다.
구매 승인, 갱신, 공급업체 평가, 외주 요청을 담당한다.

## 의사결정 라우팅

| 의사결정 유형 | 1차 Owner | 필수 리뷰어 | 최종 승인 |
| --- | --- | --- | --- |
| 회사 전략 | CEO Agent | Strategy and Research Manager, CFO Agent, CPO Agent | CEO Agent |
| 제품 범위 | CPO Agent | CTO Agent, Data Analyst Agent, Customer Success Agent | CEO Agent |
| 기술 아키텍처 | CTO Agent | Security and Risk Manager, Data Manager, Legal Agent | CTO Agent |
| 마케팅 캠페인 | CMO Agent | Data Manager, Sales Agent, Legal Agent | CMO Agent |
| 영업 계약 | Sales Agent | Legal Agent, CFO Agent, Customer Success Agent | CEO Agent |
| 파트너십 | Partnerships Manager | Legal Agent, Sales Agent, CMO Agent | CEO Agent |
| 보안 리스크 | Security and Risk Manager | CTO Agent, Legal Agent, Customer Success Agent | CEO Agent |
| 채용 | HR Agent | 해당 Team Manager, CFO Agent | CEO Agent |
| 도구 구매 | Procurement Manager | CFO Agent, Legal Agent, Internal Systems Manager | CFO Agent |

## 병렬 실행 원칙

- 전략, 제품, 영업, 마케팅은 동시에 가설을 만든다.
- 법무, 보안, 재무는 실행을 막기 위해서가 아니라 위험을 빨리 드러내기 위해 병렬 검토한다.
- 파트너십과 구매는 외부 약속이나 비용이 생기기 전에 검토한다.
- Internal Systems Team은 문서와 자동화 기준을 유지해 에이전트 실행 결과가 쌓이도록 한다.

## 회의체

### Daily Agent Sync

- Owner: COO Agent
- 참석: 모든 Manager
- 목적: 상태, 병목, 의존성, 승인 필요사항 확인
- 산출물: `TASK-BOARD.md`, `runtime/OPERATING-REVIEW.md` 업데이트

### Session Operating Review

- Owner: CEO Agent, COO Agent
- 참석: Executive Layer, 모든 Manager
- 목적: 이번 세션이 실제 회사처럼 운영됐는지 점검하고 다음 세션 mandate를 확정
- 산출물: `runtime/OPERATING-REVIEW.md`, `runtime/CEO-SESSION-REVIEW.md`, `runtime/TEAM-ACTIVITY-PLAN.md`
- 필수 확인: Health Score, Operating Gates, Executive Decisions Needed, Team Accountability, CEO Team Evaluations, Team Activity Directives, Next Session CEO Directive

### Weekly Strategy Review

- Owner: CEO Agent
- 참석: Executive Layer, Strategy and Research Manager
- 목적: 전략 가설, 지표, 리스크 검토
- 산출물: 다음 주 CEO 지시서

### Risk Review

- Owner: Security and Risk Manager
- 참석: CTO Agent, Legal Agent, CFO Agent, Customer Success Agent
- 목적: 보안, 법무, 재무, 고객 신뢰 리스크 검토
- 산출물: 리스크 등록부 업데이트

### Growth Review

- Owner: CMO Agent
- 참석: Sales Agent, Partnerships Manager, Data Manager, CPO Agent
- 목적: 고객 획득, 파트너십, 메시지, 퍼널 지표 검토
- 산출물: 채널 실험 계획 업데이트
