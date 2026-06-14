# Task Board

CEO 최종 결정 이후 COO Agent가 담당자별 실행 업무를 분배하고 상태를 관리하는 문서입니다.

## Status Legend

- `Backlog`: 아직 시작하지 않음
- `Ready`: 바로 시작 가능
- `In Progress`: 진행 중
- `Blocked`: 막힘
- `Review`: 검토 중
- `Done`: 완료

## Current Cycle

목표: 초기 회사 운영 체계를 실제로 작동 가능한 형태로 만든다.

| Status | Owner | Task | Due | Dependency | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| Ready | CEO Agent | 이번 사이클 최상위 목표와 판단 기준 확정 | Day 1 | None | `CEO-TASK-DIRECTIVE.md`의 Current Directive가 채워짐 |
| Ready | COO Agent | 모든 팀 업무를 상태값과 담당자로 정리 | Day 1 | CEO 목표 | `TASK-BOARD.md`에 팀별 업무가 등록됨 |
| Ready | CFO Agent | 첫 달 운영 예산 초안 작성 | Day 3 | 팀별 비용 요청 | 비용 항목, 금액, 승인 기준이 정리됨 |
| Ready | CTO Agent | MVP 기술 요구사항 초안 작성 | Day 3 | CPO MVP 범위 | 기술 스택 후보와 핵심 리스크가 정리됨 |
| Ready | CPO Agent | MVP 범위와 고객 문제 정의 | Day 2 | CEO 고객군 결정 | 필수 기능과 보류 기능이 구분됨 |
| Ready | CMO Agent | 가치 제안과 첫 채널 실험 계획 작성 | Day 3 | CPO 고객 문제 | 메시지, 채널, 성공 지표가 정리됨 |
| Ready | Sales Agent | 타깃 고객 20곳과 아웃리치 문구 작성 | Day 3 | CEO 고객군 결정, CMO 메시지 | 리드 리스트와 첫 접촉 문구가 완성됨 |
| Ready | Customer Success Agent | 첫 고객 온보딩 체크리스트 작성 | Day 4 | CPO 사용자 흐름 | 첫 30일 성공 기준과 체크리스트가 완성됨 |
| Ready | HR Agent | 역할 책임표와 보고 템플릿 작성 | Day 2 | TEAM-STAFFING.md | Manager와 Staff 책임 경계가 정리됨 |
| Ready | Legal Agent | 고객 접촉과 데이터 수집 법무 체크리스트 작성 | Day 3 | Sales 접촉 방식, CTO 데이터 항목 | 필수 검토 항목과 금지 사항이 정리됨 |
| Ready | Data Analyst Agent | 핵심 지표와 실험 결과 템플릿 작성 | Day 3 | 각 팀 목표 | 회사, 제품, 마케팅, 영업 지표가 정의됨 |
| Ready | Strategy and Research Manager | 시장 선택과 경쟁 전략 가설 정리 | Day 3 | CEO 목표, CPO 고객군 | 우선 시장, 경쟁 구도, 검증 가설이 정리됨 |
| Ready | Partnerships Manager | 초기 파트너십 후보와 제휴 모델 작성 | Day 4 | CMO 메시지, Sales 고객군 | 파트너 후보, 제안 메시지, 성공 지표가 정리됨 |
| Ready | Security and Risk Manager | 보안 및 운영 리스크 등록부 초안 작성 | Day 3 | CTO 아키텍처, Legal 기준 | 상위 리스크, 소유자, 완화 액션이 정리됨 |
| Ready | Internal Systems Manager | 사내 도구와 문서 시스템 운영 기준 작성 | Day 3 | COO 운영 리듬, HR 온보딩 | 계정, 문서, 자동화 기준이 정리됨 |
| Ready | Procurement Manager | 구매 요청 및 공급업체 관리 기준 작성 | Day 4 | CFO 예산 기준, Legal 계약 기준 | 구매 승인 기준과 공급업체 목록 양식이 정리됨 |

## Manager-Level Task Split

### Chief of Staff Manager

- CEO Agent의 목표를 각 팀이 이해할 수 있는 실행 문장으로 바꾼다.
- `AGENT-OPINIONS.md`에 누락된 의견이 있는지 확인한다.
- CEO 최종 결정 후 결정 로그를 정리한다.

### Operations Manager

- 모든 업무의 상태, 담당자, 마감일을 매일 업데이트한다.
- `Blocked` 업무의 원인과 필요한 결정을 정리한다.
- 금요일에 전체 실행 결과를 요약한다.

### Finance Manager

- 팀별 예상 비용을 수집한다.
- 지출 승인 기준과 예산 초안을 작성한다.
- 비용 리스크가 큰 업무를 CEO Agent에게 표시한다.

### Product Manager

- MVP 필수 기능과 보류 기능을 구분한다.
- 사용자 흐름과 고객 인터뷰 질문지를 준비한다.
- Engineering Team이 개발 범위를 이해할 수 있게 요구사항을 정리한다.

### Engineering Manager

- MVP 요구사항을 기술 업무로 분해한다.
- Frontend, Backend, QA, DevOps 업무를 나눈다.
- 보안과 배포 리스크를 CTO Agent에게 보고한다.

### Marketing Manager

- 가치 제안과 채널 실험을 실행 업무로 쪼갠다.
- 콘텐츠, 광고, 커뮤니티 담당 업무를 분배한다.
- 캠페인별 성공 지표를 Data Team과 맞춘다.

### Sales Manager

- 리드 리스트, 아웃리치, 미팅 준비 업무를 나눈다.
- 고객 반응과 반대 의견을 구조화해 Product Team에 전달한다.
- 계약 가능성이 있는 고객을 우선순위화한다.

### Customer Success Manager

- 온보딩, 지원, 고객 인사이트 업무를 나눈다.
- 고객 성공 기준과 피드백 수집 방식을 정리한다.
- 초기 고객 리스크를 Product Team과 Sales Team에 공유한다.

### People Manager

- 역할 책임표와 보고 템플릿을 정리한다.
- Manager와 Staff의 권한 경계를 명확히 한다.
- 팀별 과부하와 역할 중복을 점검한다.

### Legal Manager

- 고객 접촉, 계약, 개인정보, 외부 도구 사용 기준을 정리한다.
- 리스크가 큰 표현이나 약속을 검토한다.
- 필요한 표준 문서 초안을 만든다.

### Data Manager

- 각 팀의 성공 지표를 한곳에 모은다.
- 대시보드 항목과 데이터 수집 책임자를 정한다.
- 실험 결과 보고 템플릿을 만든다.

### Strategy and Research Manager

- 핵심 전략 가설과 검증 순서를 정리한다.
- 경쟁 환경과 대체재 리스크를 요약한다.
- CEO Agent가 선택해야 할 전략 옵션을 만든다.

### Partnerships Manager

- 초기 파트너십 후보를 우선순위화한다.
- 제휴 유형별 가치 제안과 성공 지표를 정리한다.
- Sales Team, Marketing Team과 외부 접촉 중복을 조율한다.

### Security and Risk Manager

- 보안, 개인정보, 운영 리스크를 하나의 등록부로 모은다.
- 사고 대응 역할과 연락 순서를 정의한다.
- CTO Agent와 Legal Agent에게 즉시 검토가 필요한 리스크를 표시한다.

### Internal Systems Manager

- 사내 계정, 문서, 자동화 시스템의 운영 기준을 만든다.
- 신규 합류자와 퇴사자에 대한 접근 권한 절차를 정리한다.
- 반복 업무 자동화 후보를 Operations Team과 함께 고른다.

### Procurement Manager

- 구매 요청, 승인, 계약, 갱신 흐름을 정리한다.
- 공급업체와 SaaS 도구 목록 양식을 만든다.
- 비용과 리스크가 큰 구매를 CFO Agent와 Legal Agent에게 표시한다.

## Staff-Level First Tasks

| Owner | First Task | Output |
| --- | --- | --- |
| Strategy Operations Associate | CEO 목표를 팀별 실행 문장으로 번역 | 실행 요약 |
| Market Research Associate | 첫 고객군과 경쟁 대안을 조사 | 시장 조사 메모 |
| Project Coordinator | 모든 업무의 담당자와 마감일 확인 | 일정표 |
| Process Specialist | 의견 제출과 업무 배분 프로세스 문서화 | 운영 체크리스트 |
| Vendor and Admin Coordinator | 필요한 도구와 계정 목록 정리 | 도구 목록 |
| Accounting Associate | 예상 비용 입력 양식 작성 | 비용 입력표 |
| FP&A Analyst | 1개월 예산 시나리오 작성 | 예산 시나리오 |
| Billing and Revenue Associate | 청구와 결제 흐름 초안 작성 | 청구 프로세스 |
| Product Designer | MVP 핵심 화면 흐름 스케치 | UX 흐름 |
| Product Operations Associate | 제품 요구사항 문서 초안 작성 | PRD 초안 |
| User Researcher | 고객 인터뷰 질문지 작성 | 인터뷰 질문지 |
| Frontend Engineer | MVP 화면 구현 범위 정리 | 프론트엔드 작업 목록 |
| Backend Engineer | API와 데이터 모델 후보 정리 | 백엔드 작업 목록 |
| QA and Release Engineer | 테스트 시나리오 초안 작성 | QA 체크리스트 |
| DevOps and Security Engineer | 배포와 권한 기준 정리 | 배포 보안 체크리스트 |
| Content Marketer | 첫 콘텐츠 주제 5개 작성 | 콘텐츠 목록 |
| Performance Marketer | 첫 채널 실험 설계 | 캠페인 실험안 |
| Brand and Community Associate | 브랜드 톤과 커뮤니티 메시지 정리 | 메시지 가이드 |
| Sales Development Representative | 타깃 고객 20곳 리스트업 | 리드 리스트 |
| Account Executive | 첫 미팅 진단 질문 작성 | 미팅 질문지 |
| Sales Operations Associate | 파이프라인 단계 정의 | CRM 단계표 |
| Onboarding Specialist | 첫 고객 온보딩 단계 작성 | 온보딩 체크리스트 |
| Support Specialist | 고객 문의 분류 기준 작성 | 지원 분류표 |
| Customer Insights Associate | 고객 피드백 태그 체계 작성 | 피드백 태그 |
| Recruiter | 필요한 역할 우선순위 정리 | 채용 우선순위 |
| People Operations Associate | 계정, 문서, 권한 절차 정리 | 운영 절차 |
| Learning and Culture Associate | 신규 합류자 학습 흐름 작성 | 온보딩 학습안 |
| Contract Specialist | NDA와 고객 계약 체크 항목 정리 | 계약 체크리스트 |
| Privacy and Compliance Associate | 개인정보 수집 항목 기준 작성 | 개인정보 기준 |
| IP and Vendor Risk Associate | 외부 도구와 라이선스 리스크 점검 | 리스크 목록 |
| Product Analyst | 제품 핵심 지표 후보 작성 | 제품 지표표 |
| Growth Analyst | 마케팅, 영업 퍼널 지표 작성 | 성장 지표표 |
| Data Engineer | 데이터 수집 구조 초안 작성 | 데이터 수집 설계 |
| Competitive Intelligence Analyst | 경쟁사와 대체재 10곳 조사 | 경쟁 분석 메모 |
| Business Model Analyst | 가격 및 수익 모델 후보 비교 | 비즈니스 모델 비교표 |
| Experiment Strategist | 핵심 가설 5개를 실험 설계로 변환 | 실험 설계표 |
| Partner Development Representative | 잠재 파트너 20곳 리스트업 | 파트너 후보 목록 |
| Channel Program Associate | 추천, 리셀러, 공동 마케팅 모델 비교 | 채널 모델 비교표 |
| Ecosystem Researcher | 연동 가능한 플랫폼과 커뮤니티 조사 | 생태계 조사 메모 |
| Application Security Engineer | MVP 보안 체크리스트 작성 | 애플리케이션 보안 체크리스트 |
| Governance Risk Compliance Analyst | 리스크 등록부 양식 작성 | GRC 리스크 등록부 |
| Incident Response Coordinator | 사고 대응 플로우 초안 작성 | 사고 대응 절차 |
| IT Operations Specialist | 계정과 권한 관리 기준 작성 | IT 운영 체크리스트 |
| Automation Engineer | 반복 업무 자동화 후보 10개 도출 | 자동화 후보 목록 |
| Knowledge Manager | 문서 구조와 이름 규칙 정리 | 지식관리 가이드 |
| Vendor Manager | 공급업체와 SaaS 관리표 작성 | 공급업체 관리표 |
| Procurement Analyst | 구매 요청 평가 기준 작성 | 구매 평가표 |
| Outsourcing Coordinator | 외주 요청서 템플릿 작성 | 외주 RFP 템플릿 |
