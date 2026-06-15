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
                    "work_product": "runtime/outputs/session-001/work-products/engineering-team/backend-engineer.md",
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
