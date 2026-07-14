import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_company  # noqa: E402
import llm_config  # noqa: E402


class CompanyAgentRunnerTests(unittest.TestCase):
    def setUp(self):
        os.environ["LLM_ENABLED"] = "false"

    def test_build_agents_has_expected_coverage(self):
        agents = run_company.build_agents()
        self.assertEqual(len(agents), 75)
        self.assertTrue(any(agent.name == "CEO Agent" for agent in agents))
        self.assertTrue(any(agent.parent == "Security and Risk Team" for agent in agents))

    def test_all_agents_have_direct_tasks(self):
        task_board = run_company.read_text(ROOT / "TASK-BOARD.md")
        work_items = [
            *run_company.parse_current_cycle_tasks(task_board),
            *run_company.parse_manager_tasks(task_board),
            *run_company.parse_staff_tasks(task_board),
        ]
        self.assertEqual(len(work_items), 112)
        agents_without_tasks = [
            agent.name
            for agent in run_company.build_agents()
            if not run_company.pick_tasks(agent, work_items)
        ]
        self.assertEqual(agents_without_tasks, [])

    def test_every_team_has_playbook_and_tools(self):
        for agent in run_company.build_agents():
            self.assertNotIn("아직 정의", run_company.team_playbook(agent), agent.name)
            self.assertTrue(run_company.tools_for_team(run_company.team_name_for_agent(agent)), agent.name)

    def test_shared_directive_context_is_loaded(self):
        context = run_company.shared_directive_context()
        self.assertIn("CEO Current Directive", context)
        self.assertIn("CEO Final Decision", context)
        self.assertIn("Submitted Agent Opinions", context)
        self.assertIn("초기 회사 운영 체계", context)
        self.assertIn("COO Agent Opinion", context)

    def test_user_initial_task_updates_ceo_directive(self):
        directive_path = ROOT / "CEO-TASK-DIRECTIVE.md"
        task_board_path = ROOT / "TASK-BOARD.md"
        old_directive = run_company.read_text(directive_path)
        old_task_board = run_company.read_text(task_board_path)
        try:
            run_company.set_user_initial_task("신규 고객 온보딩 자동화 MVP를 만든다.")
            directive = run_company.read_text(directive_path)
            task_board = run_company.read_text(task_board_path)
            self.assertIn("사용자의 최초 입력", directive)
            self.assertIn("신규 고객 온보딩 자동화 MVP를 만든다.", directive)
            self.assertIn("목표: 신규 고객 온보딩 자동화 MVP를 만든다.", task_board)
        finally:
            run_company.atomic_write_text(directive_path, old_directive)
            run_company.atomic_write_text(task_board_path, old_task_board)

    def test_tools_registry_is_healthy(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(run_company.tools_health(), 0)

    def test_session_mode_for_previous(self):
        self.assertEqual(run_company.session_mode_for_previous(None), "initial")
        self.assertEqual(run_company.session_mode_for_previous(ROOT), "continue")

    def test_llm_config_is_loaded_from_separate_module(self):
        old_values = {
            key: os.environ.get(key)
            for key in [
                "LLM_ENABLED",
                "LLM_PROVIDER",
                "GPT_OSS_BASE_URL",
                "GPT_OSS_MODEL",
                "LLM_AGENT_LIMIT",
                "LLM_CONCURRENCY",
            ]
        }
        try:
            os.environ["LLM_ENABLED"] = "true"
            os.environ["LLM_PROVIDER"] = "gpt-oss"
            os.environ["GPT_OSS_BASE_URL"] = "http://localhost:8000/v1/"
            os.environ["GPT_OSS_MODEL"] = "gpt-oss-test"
            os.environ["LLM_AGENT_LIMIT"] = "7"
            os.environ["LLM_CONCURRENCY"] = "3"
            config = llm_config.build_llm_config()
            self.assertTrue(config.enabled)
            self.assertEqual(config.provider, "gpt_oss")
            self.assertEqual(config.base_url, "http://localhost:8000/v1")
            self.assertEqual(config.model, "gpt-oss-test")
            self.assertEqual(config.agent_limit, 7)
            self.assertEqual(config.concurrency, 3)
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_agent_product_path_uses_team_folder(self):
        agent = run_company.AgentRuntime(
            name="Backend Engineer",
            role_file=None,
            kind="staff",
            parent="Engineering Team",
        )
        path = run_company.agent_product_path(Path("work-products"), agent)
        self.assertEqual(path, Path("work-products/engineering-team/backend-engineer.md"))

    def test_previous_team_products_context_reads_team_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            product_path = session_dir / "work-products" / "engineering-team" / "backend-engineer.md"
            run_company.atomic_write_text(product_path, "# Backend Engineer Work Product\n\n## 다음 업데이트\n\n- API 개선")
            context = run_company.previous_team_products_context(session_dir)
            self.assertIn("Previous Team Work Products", context)
            self.assertIn("work-products/engineering-team/backend-engineer.md", context)
            self.assertIn("API 개선", context)

    def test_previous_session_context_reads_ceo_session_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            run_company.atomic_write_json(session_dir / "status.json", {"cycle_id": "prior", "agent_count": 1})
            run_company.atomic_write_text(
                session_dir / "CEO-SESSION-REVIEW.md",
                "# CEO Session Review\n\n## CEO Team Evaluations\n\n- 다음 세션에는 Engineering Team이 API를 개선한다.",
            )
            context = run_company.previous_session_context(session_dir)
            self.assertIn("Previous CEO Session Review", context)
            self.assertIn("Engineering Team", context)

    def test_previous_session_context_reads_team_activity_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            run_company.atomic_write_json(session_dir / "status.json", {"cycle_id": "prior", "agent_count": 1})
            run_company.atomic_write_text(
                session_dir / "TEAM-ACTIVITY-PLAN.md",
                "# Team Activity Plan\n\n## Team Activity Directives\n\n- Engineering Team은 do now를 정리한다.",
            )
            context = run_company.previous_session_context(session_dir)
            self.assertIn("Previous Team Activity Plan", context)
            self.assertIn("Engineering Team", context)

    def test_build_agent_prompt_requires_proactive_activity(self):
        agent = run_company.AgentRuntime(
            name="Backend Engineer",
            role_file=None,
            kind="staff",
            parent="Engineering Team",
        )
        _, prompt = run_company.build_agent_prompt(agent, [], "unit-test")
        self.assertIn("Proactive Team Activity Mandate", prompt)
        self.assertIn("do now", prompt)
        self.assertIn("## Proactive Team Activity", prompt)

    def test_operating_review_renders_governance_gates(self):
        status = {
            "session": "session-001",
            "session_mode": "initial",
            "cycle_id": "unit-test",
            "generated_at": "2026-06-12T00:00:00+09:00",
            "agent_count": 1,
            "failed_agent_count": 0,
            "work_item_count": 1,
            "previous_output_dir": None,
            "llm": {"connected_count": 1},
            "agents": [
                {
                    "name": "CEO Agent",
                    "parent": None,
                    "state": "active",
                    "task_count": 1,
                    "tasks": [{"owner": "CEO Agent", "task": "우선순위 결정", "dependency": "None"}],
                    "recommended_tools": [{"tool": "CEO Decision Log"}],
                }
            ],
        }
        review = run_company.render_operating_review(status)
        self.assertIn("# Operating Review", review)
        self.assertIn("Company Readiness", review)
        self.assertIn("Operating Gates", review)
        self.assertIn("Executive Decisions Needed", review)
        self.assertIn("CEO Agent", review)

    def test_dashboard_and_console_render_live_progress(self):
        status = {
            "session": "session-001",
            "session_mode": "initial",
            "cycle_id": "unit-test",
            "generated_at": "2026-06-12T00:00:00+09:00",
            "agent_count": 2,
            "failed_agent_count": 0,
            "work_item_count": 1,
            "previous_output_dir": None,
            "teams": {"Company": 2},
            "llm": {"provider": "test", "model": "test-model", "connected_count": 1},
            "execution": {
                "state": "running",
                "started_at": "2026-06-12T00:00:00+09:00",
                "updated_at": "2026-06-12T00:00:05+09:00",
                "total_agents": 2,
                "completed_agents": 1,
                "running_agents": 1,
                "queued_agents": 0,
                "failed_agents": 0,
                "percent_complete": 50.0,
                "current_agents": ["COO Agent"],
                "recent_events": ["completed CEO Agent", "started COO Agent"],
            },
            "agents": [
                {
                    "name": "CEO Agent",
                    "parent": None,
                    "state": "active",
                    "lifecycle": "completed",
                    "llm": "connected",
                    "task_count": 1,
                    "recommended_tools": [],
                },
                {
                    "name": "COO Agent",
                    "parent": None,
                    "state": "running",
                    "lifecycle": "running",
                    "llm": "running",
                    "task_count": 0,
                    "recommended_tools": [],
                },
            ],
        }
        dashboard = run_company.render_dashboard(status)
        console = run_company.render_console_report(status)
        self.assertIn("## Live Progress", dashboard)
        self.assertIn("Progress: 1/2 (50.0%)", dashboard)
        self.assertIn("Current Agents: COO Agent", dashboard)
        self.assertIn("State       : RUNNING", console)
        self.assertIn("Progress    : 1/2 (50.0%)", console)
        self.assertIn("Current     : COO Agent", console)

    def test_dashboard_html_exposes_monitoring_and_input(self):
        html = run_company.render_dashboard_html(port=8778)
        self.assertIn("Company Agents Dashboard", html)
        self.assertIn("/api/status", html)
        self.assertIn("/api/task", html)
        self.assertIn("/api/stop", html)
        self.assertIn("port 8778", html)
        self.assertIn("Submit and run", html)
        self.assertIn("Agents By Team", html)
        self.assertIn("Agent Detail", html)
        self.assertIn("showAgentDetail", html)
        self.assertIn("top-grid", html)
        self.assertIn("dashboard-grid", html)
        self.assertIn("current-panel", html)
        self.assertIn("team-panel", html)
        self.assertIn("detail-panel", html)
        self.assertIn("expandedTeams", html)
        self.assertIn("agent-list collapsed", html)
        self.assertIn("team-toggle", html)

    def test_dashboard_payload_has_status_shape(self):
        payload = run_company.dashboard_payload()
        self.assertIn("status", payload)
        self.assertIn("process", payload)
        self.assertIn("files", payload)
        self.assertIn("snippets", payload)
        self.assertIn("message", payload)

    def test_dashboard_agent_details_includes_report_content(self):
        run_company.RUNTIME_DIR.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=run_company.RUNTIME_DIR) as tmp:
            product_path = Path(tmp) / "agent-report.md"
            log_path = Path(tmp) / "agent-log.md"
            run_company.atomic_write_text(product_path, "# Agent Report\n\n- 현재 상황 정리")
            run_company.atomic_write_text(log_path, "# Agent Log\n\n- heartbeat")
            status = {
                "agents": [
                    {
                        "name": "Backend Engineer",
                        "parent": "Engineering Team",
                        "work_product": str(product_path.relative_to(run_company.ROOT)),
                        "log": str(log_path.relative_to(run_company.ROOT)),
                    }
                ]
            }
            details = run_company.dashboard_agent_details(status)
            self.assertEqual(details[0]["team"], "Engineering Team")
            self.assertIn("Agent Report", details[0]["report_content"])
            self.assertIn("Agent Log", details[0]["log_content"])

    def test_ceo_session_review_renders_team_directives(self):
        status = {
            "session": "session-001",
            "cycle_id": "unit-test",
            "generated_at": "2026-06-12T00:00:00+09:00",
            "agents": [
                {
                    "name": "Backend Engineer",
                    "parent": "Engineering Team",
                    "state": "active",
                    "task_count": 1,
                    "tasks": [{"task": "API와 데이터 모델 후보 정리"}],
                    "recommended_tools": [{"tool": "Architecture Decision Record"}],
                }
            ],
        }
        review = run_company.render_ceo_session_review(status)
        self.assertIn("# CEO Session Review", review)
        self.assertIn("Engineering Team", review)
        self.assertIn("CEO Rating", review)
        self.assertIn("Next Session CEO Directive", review)

    def test_team_activity_plan_renders_active_directives(self):
        status = {
            "session": "session-001",
            "cycle_id": "unit-test",
            "generated_at": "2026-06-12T00:00:00+09:00",
            "agents": [
                {
                    "name": "Backend Engineer",
                    "parent": "Engineering Team",
                    "state": "active",
                    "task_count": 1,
                    "tasks": [{"owner": "Backend Engineer", "task": "API와 데이터 모델 후보 정리", "dependency": "CPO scope"}],
                    "recommended_tools": [{"tool": "Architecture Decision Record"}],
                }
            ],
        }
        plan = run_company.render_team_activity_plan(status)
        self.assertIn("# Team Activity Plan", plan)
        self.assertIn("Engineering Team", plan)
        self.assertIn("Do Now", plan)
        self.assertIn("Ask Another Team", plan)

    def test_team_session_results_renders_team_outputs_only(self):
        product_path = ROOT / "runtime" / "test-products" / "backend-engineer.md"
        run_company.atomic_write_text(product_path, "# Backend Result\n\n- 실제 API 초안\n- 데이터 모델 후보")
        status = {
            "session": "session-001",
            "cycle_id": "unit-test",
            "generated_at": "2026-06-12T00:00:00+09:00",
            "output_dir": "runtime/outputs/session-001",
            "agents": [
                {
                    "name": "Backend Engineer",
                    "parent": "Engineering Team",
                    "state": "active",
                    "task_count": 1,
                    "work_product": "runtime/test-products/backend-engineer.md",
                    "log": "runtime/outputs/session-001/agent-logs/backend-engineer.md",
                    "tasks": [{"status": "Ready", "task": "API와 데이터 모델 후보 정리", "due": "Day 3", "dependency": "CPO scope"}],
                    "recommended_tools": [{"tool": "Architecture Decision Record", "type": "Decision log"}],
                }
            ],
        }
        results = run_company.render_team_session_results(status)
        self.assertIn("# Team Session Results", results)
        self.assertIn("Engineering Team", results)
        self.assertIn("Backend Engineer", results)
        self.assertIn("Work Product:", results)
        self.assertIn("API와 데이터 모델 후보 정리", results)
        self.assertIn("Result Content", results)
        self.assertIn("실제 API 초안", results)

    def test_team_result_documents_write_actual_team_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            product_path = ROOT / "runtime" / "test-products" / "frontend-engineer.md"
            run_company.atomic_write_text(product_path, "# Frontend Result\n\n- 실제 화면 흐름")
            status = {
                "session": "session-001",
                "cycle_id": "unit-test",
                "generated_at": "2026-06-12T00:00:00+09:00",
                "agents": [
                    {
                        "name": "Frontend Engineer",
                        "parent": "Engineering Team",
                        "state": "active",
                        "task_count": 1,
                        "work_product": "runtime/test-products/frontend-engineer.md",
                    }
                ],
            }
            result_dir = Path(tmp) / "team-results"
            run_company.write_team_result_documents(status, result_dir)
            index = run_company.read_text(result_dir / "README.md")
            team_doc = run_company.read_text(result_dir / "engineering-team.md")
            self.assertIn("Engineering Team", index)
            self.assertIn("Frontend Engineer", team_doc)
            self.assertIn("실제 화면 흐름", team_doc)

    def test_filtered_cycle_exits_when_llm_is_disabled(self):
        with self.assertRaises(run_company.LLMConnectionError):
            run_company.run_cycle(max_workers=2, cycle_id="self-test", agent_filter="CEO")
        status = run_company.load_json(run_company.STATUS_FILE)
        console = run_company.render_console_report(status)
        self.assertIn("Company Agents Runtime", console)
        self.assertIn("\033[34mSession session-", console)
        self.assertIn("State       : FAILED", console)
        self.assertIn("Session     : session-", console)
        self.assertIn("Mode        :", console)
        self.assertIn("Current Session Activity", console)
        self.assertIn("LLM is disabled", console)
        self.assertIn(status["session_mode"], {"initial", "continue"})
        output_dir = ROOT / str(status["output_dir"])
        self.assertRegex(output_dir.name, r"^session-\d{3}$")
        self.assertTrue(output_dir.exists())
        self.assertTrue((output_dir / "status.json").exists())
        self.assertTrue((output_dir / "CYCLE-BRIEF.md").exists())
        self.assertTrue((output_dir / "OPERATING-REVIEW.md").exists())
        self.assertTrue((output_dir / "CEO-SESSION-REVIEW.md").exists())
        self.assertTrue((output_dir / "TEAM-ACTIVITY-PLAN.md").exists())
        self.assertTrue((output_dir / "TEAM-SESSION-RESULTS.md").exists())
        self.assertTrue((run_company.OUTPUTS_DIR / "SESSION-INDEX.md").exists())
        self.assertTrue(run_company.CYCLE_BRIEF_FILE.exists())
        self.assertTrue(run_company.OPERATING_REVIEW_FILE.exists())
        self.assertTrue(run_company.CEO_SESSION_REVIEW_FILE.exists())
        self.assertTrue(run_company.TEAM_ACTIVITY_FILE.exists())
        self.assertTrue(run_company.TEAM_SESSION_RESULTS_FILE.exists())
        cycle_brief = run_company.read_text(run_company.CYCLE_BRIEF_FILE)
        self.assertIn("# Cycle Brief", cycle_brief)
        self.assertIn("- Session Mode:", cycle_brief)
        self.assertIn("LLM is disabled", cycle_brief)
        operating_review = run_company.read_text(run_company.OPERATING_REVIEW_FILE)
        self.assertIn("# Operating Review", operating_review)
        self.assertIn("Health Score", operating_review)
        ceo_review = run_company.read_text(run_company.CEO_SESSION_REVIEW_FILE)
        self.assertIn("# CEO Session Review", ceo_review)
        self.assertIn("CEO Team Evaluations", ceo_review)
        team_plan = run_company.read_text(run_company.TEAM_ACTIVITY_FILE)
        self.assertIn("# Team Activity Plan", team_plan)
        self.assertIn("Activity Rules For Next Session", team_plan)
        team_results = run_company.read_text(run_company.TEAM_SESSION_RESULTS_FILE)
        self.assertIn("# Team Session Results", team_results)
        self.assertIn("Team Result Index", team_results)
        self.assertIn("Result Content", team_results)

    def test_run_agent_requires_llm_content(self):
        agent = run_company.AgentRuntime(name="CEO Agent", role_file="CEO-Agent.md", kind="executive")
        config = run_company.LLMConfig(
            enabled=False,
            provider="none",
            base_url="",
            model="",
            api_key="",
            timeout_seconds=1,
            temperature=0.2,
            max_tokens=10,
            agent_limit=1,
            concurrency=1,
        )
        with self.assertRaises(run_company.LLMConnectionError):
            run_company.run_agent(agent, [], "self-test", config, True, run_company.threading.Semaphore(1))

    def test_run_agent_retries_shallow_llm_output(self):
        agent = run_company.AgentRuntime(
            name="Backend Engineer",
            role_file=None,
            kind="staff",
            parent="Engineering Team",
        )
        config = run_company.LLMConfig(
            enabled=True,
            provider="gpt_oss",
            base_url="http://localhost:8000/v1",
            model="test",
            api_key="",
            timeout_seconds=1,
            temperature=0.2,
            max_tokens=2200,
            agent_limit=1,
            concurrency=1,
        )
        rich_content = "\n".join(
            [
                "## 판단",
                "- Backend Team은 이번 세션에서 API 후보를 실제 검토 가능한 수준으로 정리한다.",
                "- owner: Backend Engineer, due: 이번 세션 종료, next action: API 목록 확정.",
                "## 실행 계획",
                "- 인증, 고객, 피드백 API를 우선순위로 나누고 각 API의 입력과 출력을 적는다.",
                "- CTO Agent에게 기술 리스크 확인을 요청한다.",
                "## 산출물 초안",
                "| API | Method | Input | Output | Owner | Due |",
                "| --- | --- | --- | --- | --- | --- |",
                "| 고객 생성 | POST | email, name | customer_id | Backend Engineer | Day 1 |",
                "| 피드백 등록 | POST | customer_id, text | feedback_id | Backend Engineer | Day 1 |",
                "## Proactive Team Activity",
                "- do now: API 목록과 데이터 모델 후보를 작성한다.",
                "- ask another team: Product Team에 필수 고객 흐름을 확인한다.",
                "- escalate: 인증 범위가 불명확하면 CTO Agent에게 올린다.",
                "- next session: API별 검증 기준을 추가한다.",
                "## KPI 영향",
                "- 첫 고객 온보딩 시간 단축과 피드백 수집률 개선에 직접 연결된다.",
                "- 성공 지표: 필수 API 3개 정의, 오류 케이스 5개 이상 작성.",
                "## Decision Requests",
                "- CTO Agent: 인증 방식 후보를 세션 종료 전 선택해야 한다.",
                "- CPO Agent: MVP에서 제외할 고객 속성을 결정해야 한다.",
                "## Blockers",
                "- CPO scope가 확정되지 않으면 데이터 모델 필드가 흔들린다.",
                "- 해소 조건: 필수 화면 흐름과 고객 속성 목록 수신.",
                "## 이전 세션 대비 개선",
                "- 기존에는 작업명만 있었고, 이번에는 API 단위와 owner를 분리했다.",
                "- 다음에는 에러 응답과 테스트 시나리오를 추가한다.",
                "## 리스크와 의존성",
                "- 개인정보 필드가 늘어나면 Legal Agent 검토가 필요하다.",
                "- 배포 전 Security Team의 권한 검토가 필요하다.",
                "## 다음 업데이트",
                "- API별 request/response 초안과 테스트 체크리스트를 제출한다.",
                "- Product, Security, Legal의 확인 결과를 반영한다.",
            ]
        )
        old_call_llm = run_company.call_llm
        calls: list[str] = []

        def fake_call_llm(config_arg, system_prompt, user_prompt, semaphore=None):
            calls.append(user_prompt)
            if len(calls) == 1:
                return "완료", None
            return rich_content, None

        try:
            run_company.call_llm = fake_call_llm
            run_company.RUNTIME_DIR.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=run_company.RUNTIME_DIR) as tmp:
                result = run_company.run_agent(
                    agent,
                    [],
                    "self-test",
                    config,
                    True,
                    run_company.threading.Semaphore(1),
                    log_dir=Path(tmp) / "logs",
                    product_dir=Path(tmp) / "products",
                )
        finally:
            run_company.call_llm = old_call_llm

        self.assertEqual(len(calls), 2)
        self.assertTrue(result["llm_quality_retry"])
        self.assertEqual(result["state"], "active")

    def test_doctor_passes(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(run_company.doctor(), 0)

    def test_chatgpt_oauth_config_from_token_file(self):
        keys = [
            "LLM_ENABLED",
            "LLM_PROVIDER",
            "CHATGPT_OAUTH_BASE_URL",
            "CHATGPT_OAUTH_MODEL",
            "CHATGPT_OAUTH_ACCESS_TOKEN",
            "CHATGPT_OAUTH_TOKEN_FILE",
        ]
        old_values = {key: os.environ.get(key) for key in keys}
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
                handle.write("test-oauth-token\n")
                token_path = handle.name

            os.environ["LLM_ENABLED"] = "true"
            os.environ["LLM_PROVIDER"] = "chatgpt-oauth"
            os.environ["CHATGPT_OAUTH_BASE_URL"] = "https://example.test/v1"
            os.environ["CHATGPT_OAUTH_MODEL"] = "test-model"
            os.environ.pop("CHATGPT_OAUTH_ACCESS_TOKEN", None)
            os.environ["CHATGPT_OAUTH_TOKEN_FILE"] = token_path

            config = run_company.build_llm_config()
            self.assertEqual(config.provider, "chatgpt_oauth")
            self.assertEqual(config.base_url, "https://example.test/v1")
            self.assertEqual(config.model, "test-model")
            self.assertEqual(config.api_key, "test-oauth-token")
            self.assertTrue(config.available)
            self.assertTrue(config.requires_bearer_token)
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if "token_path" in locals():
                Path(token_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
