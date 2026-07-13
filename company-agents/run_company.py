#!/usr/bin/env python3
"""Run the company agents in parallel.

The runner treats the Markdown files in this folder as the company operating
system. Each agent reads the shared context, finds its assigned work, and writes
an independent log plus work product into the runtime folder.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import http.server
import json
import queue
import re
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from llm_config import LLMConfig, build_llm_config, call_llm, parse_int


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
OUTPUTS_DIR = RUNTIME_DIR / "outputs"
LOG_DIR = RUNTIME_DIR / "agent-logs"
PRODUCT_DIR = RUNTIME_DIR / "work-products"
TEAM_RESULT_DIR = RUNTIME_DIR / "team-results"
STATUS_FILE = RUNTIME_DIR / "status.json"
STOP_FILE = RUNTIME_DIR / "stop.requested"
DASHBOARD_FILE = RUNTIME_DIR / "DASHBOARD.md"
CYCLE_BRIEF_FILE = RUNTIME_DIR / "CYCLE-BRIEF.md"
OPERATING_REVIEW_FILE = RUNTIME_DIR / "OPERATING-REVIEW.md"
CEO_SESSION_REVIEW_FILE = RUNTIME_DIR / "CEO-SESSION-REVIEW.md"
TEAM_ACTIVITY_FILE = RUNTIME_DIR / "TEAM-ACTIVITY-PLAN.md"
TEAM_SESSION_RESULTS_FILE = RUNTIME_DIR / "TEAM-SESSION-RESULTS.md"
TOOL_USAGE_FILE = RUNTIME_DIR / "tool-usage.json"
TOOL_USAGE_MD_FILE = RUNTIME_DIR / "TOOL-USAGE.md"
TOOL_AUDIT_FILE = RUNTIME_DIR / "TOOL-AUDIT.md"
TEAM_TOOLS_FILE = ROOT / "team-tools" / "tool-registry.json"
GENERATED_TOOLS_DIR = ROOT / "team-tools" / "generated"
STOP_COMMANDS = {"stop", "quit", "exit", "q"}
INPUT_QUEUE: queue.Queue[str] | None = None
INPUT_THREAD_STARTED = False
DASHBOARD_RUN_LOCK = threading.Lock()
DASHBOARD_RUN_THREAD: threading.Thread | None = None
DASHBOARD_LAST_MESSAGE = "Dashboard server idle."

AGENT_FILES = {
    "CEO Agent": "CEO-Agent.md",
    "COO Agent": "COO-Agent.md",
    "CFO Agent": "CFO-Agent.md",
    "CTO Agent": "CTO-Agent.md",
    "CPO Agent": "CPO-Agent.md",
    "CMO Agent": "CMO-Agent.md",
    "Sales Agent": "Sales-Agent.md",
    "Customer Success Agent": "Customer-Success-Agent.md",
    "HR Agent": "HR-Agent.md",
    "Legal Agent": "Legal-Agent.md",
    "Data Analyst Agent": "Data-Analyst-Agent.md",
}


@dataclasses.dataclass(frozen=True)
class WorkItem:
    status: str
    owner: str
    task: str
    due: str
    dependency: str
    done_criteria: str
    source: str


@dataclasses.dataclass(frozen=True)
class AgentRuntime:
    name: str
    role_file: str | None
    kind: str
    parent: str | None = None

    @property
    def slug(self) -> str:
        return slugify(self.name)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "agent"


def session_number_from_name(name: str) -> int | None:
    match = re.fullmatch(r"session-(\d{3,})", name)
    return int(match.group(1)) if match else None


def list_session_dirs() -> list[Path]:
    if not OUTPUTS_DIR.exists():
        return []
    dirs = []
    for path in OUTPUTS_DIR.iterdir():
        if path.is_dir() and session_number_from_name(path.name) is not None:
            dirs.append(path)
    return sorted(dirs, key=lambda path: session_number_from_name(path.name) or 0)


def next_session_number() -> int:
    sessions = list_session_dirs()
    if not sessions:
        return 1
    return max(session_number_from_name(path.name) or 0 for path in sessions) + 1


def output_dir_for_session(session_number: int) -> Path:
    return OUTPUTS_DIR / f"session-{session_number:03d}"


def previous_session_dir(session_number: int) -> Path | None:
    if session_number <= 1:
        return None
    path = output_dir_for_session(session_number - 1)
    return path if path.exists() else None


def session_mode_for_previous(path: Path | None) -> str:
    return "continue" if path else "initial"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def previous_session_context(path: Path | None) -> str:
    if path is None:
        return "이전 세션이 없습니다. 이번 세션이 첫 실행입니다."
    status = load_json(path / "status.json")
    brief = read_text(path / "CYCLE-BRIEF.md")
    lines = [
        f"Previous Session: {path.name}",
        f"- Cycle: {status.get('cycle_id', 'unknown')}",
        f"- State: {'FAILED' if status.get('error') or status.get('failed_agent_count') else 'OK'}",
        f"- Agents: {status.get('agent_count', 0)}",
        f"- Failed Agents: {status.get('failed_agent_count', 0)}",
        f"- Work Items: {status.get('work_item_count', 0)}",
    ]
    if status.get("error"):
        lines.append(f"- Failure: {status.get('error')}")
    if brief:
        excerpt = "\n".join(brief.splitlines()[:80])
        lines.extend(["", "Previous Session Brief Excerpt:", excerpt])
    ceo_review = read_text(path / "CEO-SESSION-REVIEW.md")
    if ceo_review:
        excerpt = "\n".join(ceo_review.splitlines()[:120])
        lines.extend(["", "Previous CEO Session Review:", excerpt])
    team_activity = read_text(path / "TEAM-ACTIVITY-PLAN.md")
    if team_activity:
        excerpt = "\n".join(team_activity.splitlines()[:120])
        lines.extend(["", "Previous Team Activity Plan:", excerpt])
    product_context = previous_team_products_context(path)
    if product_context:
        lines.extend(["", product_context])
    return "\n".join(lines).strip()


def previous_team_products_context(path: Path, max_products: int = 10, max_lines_per_product: int = 35) -> str:
    products_dir = path / "work-products"
    if not products_dir.exists():
        return ""
    product_files = sorted(products_dir.glob("*/*.md"))[:max_products]
    if not product_files:
        product_files = sorted(products_dir.glob("*.md"))[:max_products]
    if not product_files:
        return ""
    lines = [
        "Previous Team Work Products:",
        "필요한 산출물은 발전시키고, 더 이상 유효하지 않거나 불필요한 산출물은 사용하지 않아도 됩니다.",
    ]
    for product_file in product_files:
        rel = product_file.relative_to(path)
        excerpt = "\n".join(read_text(product_file).splitlines()[:max_lines_per_product]).strip()
        if not excerpt:
            continue
        lines.extend(["", f"### {rel}", excerpt])
    return "\n".join(lines).strip()


def render_session_index() -> str:
    lines = [
        "# Session Index",
        "",
        "| Session | Generated | Cycle | State | Agents | Failed | Output |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for session_dir in list_session_dirs():
        status = load_json(session_dir / "status.json")
        state = "FAILED" if status.get("error") or int(status.get("failed_agent_count") or 0) else "OK"
        lines.append(
            f"| {session_dir.name} | {status.get('generated_at', '')} | {status.get('cycle_id', '')} | "
            f"{state} | {status.get('agent_count', 0)} | {status.get('failed_agent_count', 0)} | "
            f"[{session_dir.name}]({session_dir.name}/CYCLE-BRIEF.md) |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_session_index() -> None:
    atomic_write_text(OUTPUTS_DIR / "SESSION-INDEX.md", render_session_index())


def blue_text(value: str) -> str:
    return f"\033[34m{value}\033[0m"


def summarize_session_activity(status: dict[str, object]) -> list[str]:
    agents = status.get("agents", [])
    if not isinstance(agents, list) or not agents:
        return ["No agent activity recorded for this session."]

    execution = status.get("execution", {})
    if isinstance(execution, dict):
        total = int(execution.get("total_agents") or 0)
        completed = int(execution.get("completed_agents") or 0)
        running = int(execution.get("running_agents") or 0)
        queued = int(execution.get("queued_agents") or 0)
        percent = float(execution.get("percent_complete") or 0)
        if total:
            lines = [
                f"Progress    : {completed}/{total} ({percent:.1f}%)",
                f"Running     : {running}",
                f"Queued      : {queued}",
            ]
            current_agents = execution.get("current_agents", [])
            if isinstance(current_agents, list) and current_agents:
                lines.append("Current     : " + ", ".join(str(name) for name in current_agents[:5]))
            recent_events = execution.get("recent_events", [])
            if isinstance(recent_events, list) and recent_events:
                lines.append("Recent      : " + " | ".join(str(event) for event in recent_events[-3:]))
            lines.append("")
        else:
            lines = []
    else:
        lines = []

    connected = 0
    failed = 0
    assigned_tasks = 0
    tool_recommendations = 0
    active_names: list[str] = []
    failed_names: list[str] = []
    for item in agents:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "unknown")
        state = str(item.get("state") or "")
        if item.get("llm") == "connected":
            connected += 1
        if state == "failed":
            failed += 1
            failed_names.append(name)
        else:
            active_names.append(name)
        assigned_tasks += int(item.get("task_count") or 0)
        recommendations = item.get("recommended_tools", [])
        if isinstance(recommendations, list):
            tool_recommendations += len(recommendations)

    lines.extend([
        f"Agents Run  : {len(agents)}",
        f"Connected   : {connected}",
        f"Failed      : {failed}",
        f"Tasks       : {assigned_tasks}",
        f"Tool Uses   : {tool_recommendations}",
    ])
    if active_names:
        lines.append("Active      : " + ", ".join(active_names[:5]) + (" ..." if len(active_names) > 5 else ""))
    if failed_names:
        lines.append("Failed List : " + ", ".join(failed_names[:5]) + (" ..." if len(failed_names) > 5 else ""))
    return lines


def section_between(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_table(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def parse_current_cycle_tasks(task_board: str) -> list[WorkItem]:
    current_cycle = section_between(task_board, "Current Cycle")
    rows = parse_table(current_cycle)
    items: list[WorkItem] = []
    for cells in rows[1:]:
        if len(cells) < 6:
            continue
        items.append(
            WorkItem(
                status=cells[0],
                owner=cells[1],
                task=cells[2],
                due=cells[3],
                dependency=cells[4],
                done_criteria=cells[5],
                source="Current Cycle",
            )
        )
    return items


def parse_staff_tasks(task_board: str) -> list[WorkItem]:
    staff_section = section_between(task_board, "Staff-Level First Tasks")
    rows = parse_table(staff_section)
    items: list[WorkItem] = []
    for cells in rows[1:]:
        if len(cells) < 3:
            continue
        items.append(
            WorkItem(
                status="Ready",
                owner=cells[0],
                task=cells[1],
                due="This cycle",
                dependency="Manager guidance",
                done_criteria=f"{cells[2]} 산출물이 작성됨",
                source="Staff-Level First Tasks",
            )
        )
    return items


def parse_manager_tasks(task_board: str) -> list[WorkItem]:
    manager_section = section_between(task_board, "Manager-Level Task Split")
    blocks = re.findall(
        r"^### (?P<name>.+?)\s*$\n(?P<body>[\s\S]*?)(?=^### |\Z)",
        manager_section,
        re.MULTILINE,
    )
    items: list[WorkItem] = []
    for manager, body in blocks:
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            task = line[2:].strip()
            items.append(
                WorkItem(
                    status="Ready",
                    owner=manager.strip(),
                    task=task,
                    due="This cycle",
                    dependency="CEO final decision",
                    done_criteria="업무 결과와 다음 액션이 문서화됨",
                    source="Manager-Level Task Split",
                )
            )
    return items


def parse_staffing_agents(staffing: str) -> list[AgentRuntime]:
    agents: list[AgentRuntime] = []
    current_team: str | None = None
    for line in staffing.splitlines():
        line = line.strip()
        if line.startswith("## ") and not line.startswith("## 전체"):
            current_team = line.replace("## ", "").strip()
        elif line.startswith("### Manager:"):
            name = line.replace("### Manager:", "").strip()
            agents.append(AgentRuntime(name=name, role_file=None, kind="manager", parent=current_team))
        elif line.startswith("#### "):
            name = line.replace("#### ", "").strip()
            agents.append(AgentRuntime(name=name, role_file=None, kind="staff", parent=current_team))
    return agents


def build_agents(agent_filter: str | None = None, team_filter: str | None = None) -> list[AgentRuntime]:
    staffing = read_text(ROOT / "TEAM-STAFFING.md")
    core_agents = [
        AgentRuntime(name=name, role_file=file_name, kind="executive")
        for name, file_name in AGENT_FILES.items()
    ]
    team_agents = parse_staffing_agents(staffing)
    seen: set[str] = set()
    result: list[AgentRuntime] = []
    for agent in [*core_agents, *team_agents]:
        if agent.name in seen:
            continue
        seen.add(agent.name)
        result.append(agent)
    if team_filter:
        team_needle = team_filter.lower()
        result = [
            agent for agent in result
            if team_needle in (agent.parent or "Company").lower()
            or team_needle in slugify(agent.parent or "Company")
        ]
    if agent_filter:
        agent_needle = agent_filter.lower()
        result = [
            agent for agent in result
            if agent_needle in agent.name.lower() or agent_needle in slugify(agent.name)
        ]
    return result


def pick_tasks(agent: AgentRuntime, items: list[WorkItem]) -> list[WorkItem]:
    direct = [item for item in items if item.owner == agent.name]
    if direct:
        return direct
    if agent.kind == "executive":
        short_name = agent.name.replace(" Agent", "")
        return [item for item in items if item.owner.startswith(short_name)]
    return []


def summarize_role(agent: AgentRuntime) -> str:
    if agent.role_file is None:
        parent = f"{agent.parent} 소속 " if agent.parent else ""
        return f"{parent}{agent.kind} 역할로 배정된 실행 담당자입니다."
    text = read_text(ROOT / agent.role_file)
    role = section_between(text, "역할")
    return " ".join(role.split()) if role else f"{agent.name} 역할 문서를 기준으로 실행합니다."


def team_name_for_agent(agent: AgentRuntime) -> str:
    team = agent.parent or "Company Layer"
    return "Company Layer" if team == "Company" else team


def team_slug_for_agent(agent: AgentRuntime) -> str:
    return slugify(team_name_for_agent(agent))


def agent_product_path(product_dir: Path, agent: AgentRuntime) -> Path:
    return product_dir / team_slug_for_agent(agent) / f"{agent.slug}.md"


def team_playbook(agent: AgentRuntime) -> str:
    playbooks = read_text(ROOT / "TEAM-PLAYBOOKS.md")
    team = team_name_for_agent(agent)
    section = section_between(playbooks, team)
    if not section:
        return "팀 플레이북이 아직 정의되지 않았습니다."
    lines = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if line:
            lines.append(line)
        if len(lines) >= 18:
            break
    return "\n".join(lines)


def shared_directive_context() -> str:
    directive = read_text(ROOT / "CEO-TASK-DIRECTIVE.md")
    opinions = read_text(ROOT / "AGENT-OPINIONS.md")
    sections = []
    current_directive = section_between(directive, "Current Directive")
    final_decision = section_between(directive, "Final Decision")
    agent_opinions = section_between(opinions, "Submitted Opinions")
    if not agent_opinions and "## COO Agent Opinion" in opinions:
        agent_opinions = opinions.split("## COO Agent Opinion", 1)[1].strip()
        agent_opinions = "## COO Agent Opinion\n\n" + agent_opinions
    if current_directive:
        sections.append("## CEO Current Directive\n\n" + current_directive)
    if final_decision:
        sections.append("## CEO Final Decision\n\n" + final_decision)
    if agent_opinions:
        sections.append("## Submitted Agent Opinions\n\n" + agent_opinions)
    return "\n\n".join(sections) if sections else "CEO 지시와 담당자 의견 문서가 아직 채워지지 않았습니다."


def render_user_directive(task: str) -> str:
    task = task.strip()
    return "\n".join(
        [
            "# CEO Task Directive",
            "",
            "CEO Agent가 사용자의 최초 입력을 회사의 현재 목표로 받아 각 담당 에이전트에게 의견을 요청하는 문서입니다.",
            "",
            "## Current Directive",
            "",
            "### 목표",
            "",
            task,
            "",
            "### 배경",
            "",
            "- 이 목표는 사용자가 이번 실행 사이클의 최초 task로 입력했습니다.",
            "- CEO Agent는 이 입력을 회사 목표로 해석하고, 각 담당 agent가 실행 가능한 의견을 내도록 요청합니다.",
            "- COO Agent는 의견과 완료 기준을 바탕으로 업무 보드와 의존성을 정리합니다.",
            "",
            "### 판단 기준",
            "",
            "- 고객 가치 또는 회사 운영 개선에 직접 연결되는가",
            "- 1주 안에 검토 가능한 산출물을 만들 수 있는가",
            "- 담당자와 완료 기준이 명확한가",
            "- 여러 agent가 병렬로 실행할 수 있는가",
            "- 비용, 법무, 기술, 보안 리스크가 관리 가능한가",
            "",
            "### CEO 요청",
            "",
            "각 담당 에이전트는 아래 항목에 대해 의견을 제출한다.",
            "",
            "- 이 목표를 달성하기 위해 자신의 팀이 해야 할 가장 중요한 일",
            "- 지금 바로 시작할 수 있는 일",
            "- 다른 팀의 도움이 필요한 일",
            "- 예상되는 리스크",
            "- 1주 안에 제출할 수 있는 산출물",
            "- CEO 결정이 필요한 부분",
            "",
            "## Final Decision",
            "",
            "### CEO 최종 방향",
            "",
            "아직 확정되지 않았습니다. 각 agent 의견을 받은 뒤 CEO Agent가 최종 방향을 정리합니다.",
            "",
            "### 우선순위",
            "",
            "1. 사용자 최초 task를 회사 목표로 해석한다.",
            "2. 각 담당 agent가 독립적으로 의견을 낸다.",
            "3. CEO Agent가 의견을 종합해 최종 방향을 확정한다.",
            "4. COO Agent가 담당자별 실행 업무로 분배한다.",
            "5. Manager와 Staff가 산출물을 작성하고 상태를 업데이트한다.",
            "",
            "### 승인된 실행 방식",
            "",
            "- CEO Agent는 사용자 입력을 목표와 판단 기준으로 정리한다.",
            "- 각 담당 에이전트는 독립적으로 의견을 낸다.",
            "- COO Agent는 최종 결정 이후 업무를 담당자에게 배분한다.",
            "- Manager는 팀원 업무를 세분화하고 상태를 관리한다.",
            "- Staff는 산출물을 만들고 진행 상태를 업데이트한다.",
            "",
        ]
    )


def update_task_board_goal(task: str) -> None:
    path = ROOT / "TASK-BOARD.md"
    text = read_text(path)
    if not text:
        return
    updated = re.sub(r"(?m)^목표: .*$", f"목표: {task.strip()}", text, count=1)
    if updated != text:
        atomic_write_text(path, updated)


def set_user_initial_task(task: str) -> None:
    task = task.strip()
    if not task:
        raise ValueError("Initial task cannot be empty.")
    atomic_write_text(ROOT / "CEO-TASK-DIRECTIVE.md", render_user_directive(task))
    update_task_board_goal(task)


def resolve_initial_task(args: argparse.Namespace) -> str | None:
    task = args.task.strip() if args.task else ""
    if args.task_file:
        task = read_text(Path(args.task_file)).strip()
    if args.ask_task:
        print("이번 실행 사이클의 최초 task를 입력하세요. 입력을 마치려면 빈 줄에서 Enter를 누르세요.")
        lines = []
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not line.strip() and lines:
                break
            if line.strip():
                lines.append(line)
        task = "\n".join(lines).strip()
    return task or None


def tools_for_team(team: str) -> list[dict[str, str]]:
    registry = load_json(TEAM_TOOLS_FILE)
    metadata = tool_metadata_from_markdown()
    tools = registry.get(team, [])
    if not isinstance(tools, list):
        return []
    normalized = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        meta = metadata.get(team, {}).get(str(item.get("name", "")), {})
        normalized.append(
            {
                "name": str(item.get("name", "")),
                "type": str(item.get("type", "")),
                "template": str(item.get("template", "")),
                "purpose": str(item.get("purpose", meta.get("purpose", ""))),
                "output": str(item.get("output", meta.get("output", ""))),
            }
        )
    return normalized


def tokenize(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", " ", value.lower())
    return {token for token in normalized.split() if len(token) >= 2}


def recommend_tools_for_tasks(team: str, tasks: list[WorkItem]) -> list[dict[str, object]]:
    tools = tools_for_team(team)
    if not tools:
        return []
    recommendations: list[dict[str, object]] = []
    if not tasks:
        for tool in tools[:2]:
            recommendations.append(
                {
                    "tool": tool["name"],
                    "type": tool["type"],
                    "template": tool["template"],
                    "score": 1,
                    "confidence": "low",
                    "matched_terms": [],
                    "reason": "직접 배정된 업무는 없지만 팀 기본 운영 도구로 관찰과 준비에 사용",
                    "matched_task": None,
                }
            )
        return recommendations

    for task in tasks:
        task_tokens = tokenize(" ".join([task.task, task.done_criteria, task.dependency, task.source]))
        scored: list[tuple[int, list[str], dict[str, str]]] = []
        for tool in tools:
            tool_text = " ".join([tool["name"], tool["type"], tool.get("purpose", ""), tool.get("output", "")])
            matched_terms = sorted(task_tokens & tokenize(tool_text))
            score = len(matched_terms)
            if score == 0:
                # Keep at least one useful team tool attached to each task.
                score = 1 if tool == tools[0] else 0
            scored.append((score, matched_terms, tool))
        scored.sort(key=lambda item: (-item[0], item[2]["name"]))
        for score, matched_terms, tool in scored[:2]:
            if score <= 0:
                continue
            confidence = "high" if score >= 3 else "medium" if score == 2 else "low"
            recommendations.append(
                {
                    "tool": tool["name"],
                    "type": tool["type"],
                    "template": tool["template"],
                    "score": score,
                    "confidence": confidence,
                    "matched_terms": matched_terms,
                    "reason": tool.get("purpose") or "팀 업무 표준화에 사용",
                    "matched_task": task.task,
                }
            )

    seen: set[tuple[object, object]] = set()
    unique: list[dict[str, object]] = []
    for recommendation in recommendations:
        key = (recommendation["tool"], recommendation["matched_task"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(recommendation)
    return unique


def tool_metadata_from_markdown() -> dict[str, dict[str, dict[str, str]]]:
    text = read_text(ROOT / "TEAM-TOOLS.md")
    metadata: dict[str, dict[str, dict[str, str]]] = {}
    team_blocks = re.findall(
        r"^## (?P<team>.+?)\s*$\n(?P<body>[\s\S]*?)(?=^## |\Z)",
        text,
        re.MULTILINE,
    )
    for team, body in team_blocks:
        rows = parse_table(body)
        if not rows:
            continue
        team_meta: dict[str, dict[str, str]] = {}
        for cells in rows[1:]:
            if len(cells) < 4:
                continue
            team_meta[cells[0]] = {
                "type": cells[1],
                "purpose": cells[2],
                "output": cells[3],
            }
        metadata[team] = team_meta
    return metadata


def team_tools(agent: AgentRuntime) -> str:
    team = team_name_for_agent(agent)
    tools = tools_for_team(team)
    if not tools:
        return "팀 도구가 아직 정의되지 않았습니다."
    lines = []
    for tool in tools:
        template = tool["template"]
        template_path = f"team-tools/{template}" if template else "N/A"
        output = f" -> {tool['output']}" if tool.get("output") else ""
        lines.append(f"- {tool['name']} ({tool['type']}): {template_path}{output}")
    return "\n".join(lines)


def recommended_tools(agent: AgentRuntime, tasks: list[WorkItem]) -> str:
    team = team_name_for_agent(agent)
    recommendations = recommend_tools_for_tasks(team, tasks)
    if not recommendations:
        return "추천 도구가 없습니다."
    lines = []
    for item in recommendations[:6]:
        matched = f" for `{item['matched_task']}`" if item.get("matched_task") else ""
        score = item.get("score", 0)
        confidence = item.get("confidence", "unknown")
        terms = ", ".join(item.get("matched_terms", []) or [])
        term_text = f"; terms: {terms}" if terms else ""
        lines.append(f"- {item['tool']} ({item['type']}){matched}: {item['reason']} [score={score}, confidence={confidence}{term_text}]")
    return "\n".join(lines)


def print_tools(team_filter: str | None = None) -> None:
    registry = load_json(TEAM_TOOLS_FILE)
    metadata = tool_metadata_from_markdown()
    for team in sorted(registry):
        if team_filter:
            needle = team_filter.lower()
            if needle not in team.lower() and needle not in slugify(team):
                continue
        print(f"[{team}]")
        tools = registry.get(team, [])
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict):
                    name = str(tool.get("name", ""))
                    meta = metadata.get(team, {}).get(name, {})
                    purpose = meta.get("purpose", "")
                    output = meta.get("output", "")
                    suffix = f" | {purpose} | output: {output}" if purpose or output else ""
                    print(f"- {name} ({tool.get('type')}) -> team-tools/{tool.get('template')}{suffix}")
        print()


def render_materialized_tool(team: str, tool: dict[str, str], template_body: str) -> str:
    purpose = tool.get("purpose", "")
    output = tool.get("output", "")
    return "\n".join(
        [
            f"# {tool['name']}",
            "",
            f"- Owner Team: {team}",
            f"- Type: {tool['type']}",
            f"- Source Template: {tool['template']}",
            f"- Purpose: {purpose or '정의 필요'}",
            f"- Expected Output: {output or '정의 필요'}",
            "",
            "## When To Use",
            "",
            f"- {purpose or '이 도구의 사용 목적을 구체화한다.'}",
            "- 업무 owner, 상태, 다음 액션을 명확히 남겨야 할 때 사용한다.",
            "- 다른 팀 리뷰가 필요한 산출물을 표준 형태로 공유할 때 사용한다.",
            "",
            "## Required Fields",
            "",
            "- Owner",
            "- Status",
            "- Due Date",
            "- Inputs",
            "- Decision or Output",
            "- Next Action",
            "",
            "## Working Template",
            "",
            template_body.strip(),
            "",
        ]
    )


def materialize_tools(team_filter: str | None = None) -> int:
    registry = load_json(TEAM_TOOLS_FILE)
    metadata = tool_metadata_from_markdown()
    count = 0
    GENERATED_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    global_index = ["# Generated Team Tools", ""]
    for team in sorted(registry):
        if team_filter:
            needle = team_filter.lower()
            if needle not in team.lower() and needle not in slugify(team):
                continue
        tools = registry.get(team, [])
        if not isinstance(tools, list):
            continue
        team_dir = GENERATED_TOOLS_DIR / slugify(team)
        team_dir.mkdir(parents=True, exist_ok=True)
        index_lines = [f"# {team} Tools", "", "| Tool | Type | Purpose | Output | File |", "| --- | --- | --- | --- | --- |"]
        for item in tools:
            if not isinstance(item, dict):
                continue
            meta = metadata.get(team, {}).get(str(item.get("name", "")), {})
            tool = {
                "name": str(item.get("name", "")),
                "type": str(item.get("type", "")),
                "template": str(item.get("template", "")),
                "purpose": str(item.get("purpose", meta.get("purpose", ""))),
                "output": str(item.get("output", meta.get("output", ""))),
            }
            template_path = ROOT / "team-tools" / tool["template"]
            template_body = read_text(template_path)
            suffix = ".csv" if tool["template"].endswith(".csv") else ".md"
            output_path = team_dir / f"{slugify(tool['name'])}{suffix}"
            if suffix == ".csv":
                atomic_write_text(output_path, render_csv_tool(tool, template_body))
            else:
                atomic_write_text(output_path, render_materialized_tool(team, tool, template_body))
            index_lines.append(
                f"| {tool['name']} | {tool['type']} | {tool['purpose']} | {tool['output']} | [{output_path.name}]({output_path.name}) |"
            )
            count += 1
        atomic_write_text(team_dir / "README.md", "\n".join(index_lines).rstrip() + "\n")
        global_index.append(f"- [{team}]({slugify(team)}/README.md): {len(tools)} tool(s)")
    atomic_write_text(GENERATED_TOOLS_DIR / "README.md", "\n".join(global_index).rstrip() + "\n")
    print(f"Materialized {count} tool file(s) in {GENERATED_TOOLS_DIR.relative_to(ROOT)}")
    return 0


def render_tool_usage_reports(
    status: dict[str, object],
    usage_json_path: Path = TOOL_USAGE_FILE,
    usage_md_path: Path = TOOL_USAGE_MD_FILE,
    audit_path: Path = TOOL_AUDIT_FILE,
) -> None:
    agents = status.get("agents", [])
    usage_rows: list[dict[str, object]] = []
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            for item in agent.get("recommended_tools", []) or []:
                if not isinstance(item, dict):
                    continue
                usage_rows.append(
                    {
                        "agent": agent.get("name"),
                        "team": agent.get("tool_team") or agent.get("parent") or "Company",
                        "tool": item.get("tool"),
                        "type": item.get("type"),
                        "score": item.get("score"),
                        "confidence": item.get("confidence"),
                        "matched_terms": item.get("matched_terms") or [],
                        "matched_task": item.get("matched_task"),
                        "reason": item.get("reason"),
                    }
                )
    atomic_write_json(usage_json_path, {"generated_at": now_iso(), "tools": usage_rows})

    lines = ["# Tool Usage", "", f"- Generated At: {now_iso()}", f"- Recommended Tool Uses: {len(usage_rows)}", ""]
    by_team: dict[str, int] = {}
    for row in usage_rows:
        team = str(row["team"])
        by_team[team] = by_team.get(team, 0) + 1
    lines.extend(["## By Team", ""])
    for team in sorted(by_team):
        lines.append(f"- {team}: {by_team[team]} recommendation(s)")
    lines.extend(["", "## Recommendations", ""])
    lines.append("| Agent | Team | Tool | Confidence | Score | Task | Reason |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in usage_rows[:100]:
        lines.append(
            f"| {row['agent']} | {row['team']} | {row['tool']} | {row.get('confidence') or ''} | {row.get('score') or ''} | {row.get('matched_task') or ''} | {row.get('reason') or ''} |"
        )
    atomic_write_text(usage_md_path, "\n".join(lines).rstrip() + "\n")
    render_tool_audit_report(usage_rows, audit_path=audit_path)


def render_tool_audit_report(usage_rows: list[dict[str, object]], audit_path: Path = TOOL_AUDIT_FILE) -> None:
    registry = load_json(TEAM_TOOLS_FILE)
    all_tools: list[tuple[str, str]] = []
    for team, tools in registry.items():
        if not isinstance(tools, list):
            continue
        for tool in tools:
            if isinstance(tool, dict):
                all_tools.append((str(team), str(tool.get("name", ""))))

    usage_by_tool: dict[tuple[str, str], int] = {}
    score_by_tool: dict[tuple[str, str], int] = {}
    confidence_counts: dict[str, int] = {}
    for row in usage_rows:
        key = (str(row.get("team")), str(row.get("tool")))
        usage_by_tool[key] = usage_by_tool.get(key, 0) + 1
        try:
            score_by_tool[key] = score_by_tool.get(key, 0) + int(row.get("score") or 0)
        except (TypeError, ValueError):
            pass
        confidence = str(row.get("confidence") or "unknown")
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

    unused = [item for item in all_tools if usage_by_tool.get(item, 0) == 0]
    ranked = sorted(usage_by_tool.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    coverage = 0 if not all_tools else round(((len(all_tools) - len(unused)) / len(all_tools)) * 100, 1)

    lines = [
        "# Tool Audit",
        "",
        f"- Generated At: {now_iso()}",
        f"- Total Registered Tools: {len(all_tools)}",
        f"- Used Tools: {len(all_tools) - len(unused)}",
        f"- Unused Tools: {len(unused)}",
        f"- Coverage: {coverage}%",
        "",
        "## Confidence Mix",
        "",
    ]
    for confidence in sorted(confidence_counts):
        lines.append(f"- {confidence}: {confidence_counts[confidence]}")

    lines.extend(["", "## Most Recommended Tools", ""])
    if not ranked:
        lines.append("- None")
    for (team, tool), count in ranked[:20]:
        total_score = score_by_tool.get((team, tool), 0)
        avg_score = round(total_score / count, 2) if count else 0
        lines.append(f"- {team} / {tool}: {count} recommendation(s), avg score {avg_score}")

    lines.extend(["", "## Unused Tools", ""])
    if not unused:
        lines.append("- None")
    for team, tool in unused:
        lines.append(f"- {team} / {tool}")

    atomic_write_text(audit_path, "\n".join(lines).rstrip() + "\n")


def tools_health(team_filter: str | None = None) -> int:
    registry = load_json(TEAM_TOOLS_FILE)
    metadata = tool_metadata_from_markdown()
    total = 0
    issues: list[str] = []
    print("# Tools Health")
    print()
    for team in sorted(registry):
        if team_filter:
            needle = team_filter.lower()
            if needle not in team.lower() and needle not in slugify(team):
                continue
        tools = registry.get(team, [])
        if not isinstance(tools, list):
            issues.append(f"{team}: registry value is not a list")
            continue
        print(f"- {team}: {len(tools)} tool(s)")
        total += len(tools)
        for item in tools:
            if not isinstance(item, dict):
                issues.append(f"{team}: malformed tool entry")
                continue
            name = str(item.get("name", ""))
            template = str(item.get("template", ""))
            if not name:
                issues.append(f"{team}: tool missing name")
            if not template:
                issues.append(f"{team}/{name}: missing template")
            elif not (ROOT / "team-tools" / template).exists():
                issues.append(f"{team}/{name}: template not found: {template}")
            meta = metadata.get(team, {}).get(name, {})
            if not meta.get("purpose"):
                issues.append(f"{team}/{name}: missing purpose in TEAM-TOOLS.md")
            if not meta.get("output"):
                issues.append(f"{team}/{name}: missing output in TEAM-TOOLS.md")
    print()
    print(f"Total tools: {total}")
    if issues:
        print(f"Issues: {len(issues)}")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Issues: 0")
    return 0


def show_tool_audit() -> int:
    if not TOOL_AUDIT_FILE.exists():
        print("Tool audit has not been generated yet. Run agents first.")
        return 1
    print(read_text(TOOL_AUDIT_FILE))
    return 0


def doctor(agent_filter: str | None = None, team_filter: str | None = None) -> int:
    issues: list[str] = []
    agents = build_agents(agent_filter=agent_filter, team_filter=team_filter)
    task_board = read_text(ROOT / "TASK-BOARD.md")
    work_items = [
        *parse_current_cycle_tasks(task_board),
        *parse_manager_tasks(task_board),
        *parse_staff_tasks(task_board),
    ]
    registry = load_json(TEAM_TOOLS_FILE)
    metadata = tool_metadata_from_markdown()

    if not agents:
        issues.append("No agents matched the current filters.")
    if not work_items:
        issues.append("No work items found in TASK-BOARD.md.")

    agent_names = {agent.name for agent in agents}
    assigned_owners = {item.owner for item in work_items}
    orphan_tasks = sorted(owner for owner in assigned_owners if owner not in {agent.name for agent in build_agents()})
    if orphan_tasks:
        issues.append(f"Tasks reference unknown owner(s): {', '.join(orphan_tasks[:10])}")

    agents_without_playbook = []
    agents_without_tools = []
    agents_without_tasks = []
    for agent in agents:
        team = team_name_for_agent(agent)
        if "아직 정의" in team_playbook(agent):
            agents_without_playbook.append(agent.name)
        if not tools_for_team(team):
            agents_without_tools.append(agent.name)
        if not pick_tasks(agent, work_items):
            agents_without_tasks.append(agent.name)

    for team, tools in registry.items():
        if not isinstance(tools, list):
            issues.append(f"Tool registry for {team} is not a list.")
            continue
        for tool in tools:
            if not isinstance(tool, dict):
                issues.append(f"Malformed tool entry in {team}.")
                continue
            name = str(tool.get("name", ""))
            template = str(tool.get("template", ""))
            if not name:
                issues.append(f"{team} has a tool without a name.")
            if not template or not (ROOT / "team-tools" / template).exists():
                issues.append(f"{team}/{name} has missing template: {template}")
            meta = metadata.get(str(team), {}).get(name, {})
            if not meta.get("purpose") or not meta.get("output"):
                issues.append(f"{team}/{name} is missing purpose/output in TEAM-TOOLS.md.")

    print("# Company Agents Doctor")
    print()
    print(f"- Agents checked: {len(agents)}")
    print(f"- Work items found: {len(work_items)}")
    print(f"- Agents with tasks: {len(agent_names & assigned_owners)}")
    print(f"- Agents without direct tasks: {len(agents_without_tasks)}")
    print(f"- Agents without playbook: {len(agents_without_playbook)}")
    print(f"- Agents without tools: {len(agents_without_tools)}")
    print(f"- Tool teams: {len(registry)}")
    print()

    if agents_without_tasks:
        print("## Agents Without Direct Tasks")
        for name in agents_without_tasks[:20]:
            print(f"- {name}")
        if len(agents_without_tasks) > 20:
            print(f"- ...and {len(agents_without_tasks) - 20} more")
        print()

    if issues:
        print("## Issues")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("## Issues")
    print("- None")
    return 0


def render_csv_tool(tool: dict[str, str], template_body: str) -> str:
    header = template_body.strip() or "id,title,status,owner,priority,due_date,next_action,notes"
    example = {
        "id": "1",
        "title": tool["name"],
        "status": "Backlog",
        "owner": "",
        "priority": "Medium",
        "due_date": "",
        "source": tool.get("purpose", ""),
        "dependency": "",
        "next_action": tool.get("output", ""),
        "last_updated": now_iso(),
        "notes": "",
    }
    columns = header.splitlines()[0].split(",")
    row = ",".join(escape_csv(example.get(column, "")) for column in columns)
    return f"{','.join(columns)}\n{row}\n"


def escape_csv(value: str) -> str:
    if any(char in value for char in [",", '"', "\n"]):
        return '"' + value.replace('"', '""') + '"'
    return value


def proactive_team_mandate(agent: AgentRuntime, tasks: list[WorkItem]) -> str:
    team = team_name_for_agent(agent)
    lines = [
        f"- Team: {team}",
        "- 이번 세션에는 관찰만 하지 말고 최소 하나의 검토 가능한 산출물을 만들거나 기존 산출물을 개선하세요.",
        "- 반드시 `do now`, `ask another team`, `escalate`, `next session` 네 가지 행동을 구분하세요.",
        "- 다른 팀을 기다리는 일이 있으면 기다리지 말고 임시 가정, 필요한 입력, 요청 대상, 차단 해소 조건을 쓰세요.",
        "- 팀 도구 중 하나를 선택해 산출물 또는 다음 액션과 연결하세요.",
    ]
    if tasks:
        lines.append("- 직접 배정 업무가 있으므로 가장 빠르게 검토 가능한 초안을 우선 제출하세요.")
    else:
        lines.append("- 직접 배정 업무가 없어도 팀 플레이북 기준으로 리스크 제거, 의존성 정리, 산출물 개선 중 하나를 수행하세요.")
    if agent.kind == "manager":
        lines.append("- Manager는 팀원 2명 이상에게 다음 액션을 배정하고 상태 확인 기준을 써야 합니다.")
    elif agent.kind == "staff":
        lines.append("- Staff는 자신이 직접 만들 파일, 표, 체크리스트, 질문지, 분석 메모 중 하나를 명시해야 합니다.")
    else:
        lines.append("- Executive는 팀 간 충돌, 승인 필요사항, 하지 않을 일을 분명히 정해야 합니다.")
    return "\n".join(lines)


def build_agent_prompt(agent: AgentRuntime, tasks: list[WorkItem], cycle_id: str, previous_context: str = "") -> tuple[str, str]:
    task_lines = []
    for item in tasks:
        task_lines.append(
            "\n".join(
                [
                    f"- Task: {item.task}",
                    f"  Status: {item.status}",
                    f"  Due: {item.due}",
                    f"  Dependency: {item.dependency}",
                    f"  Done Criteria: {item.done_criteria}",
                    f"  Source: {item.source}",
                ]
            )
        )
    task_text = "\n".join(task_lines) if task_lines else "- 현재 직접 배정된 업무 없음"
    system_prompt = (
        "You are an autonomous company agent. "
        "Answer in Korean. Be concrete, operational, and concise. "
        "Return Markdown only. Do not invent external facts. "
        "Focus on the assigned work, risks, dependencies, and next actions."
    )
    user_prompt = "\n".join(
        [
            f"Cycle: {cycle_id}",
            f"Agent: {agent.name}",
            f"Kind: {agent.kind}",
            f"Parent: {agent.parent or 'Company'}",
            "",
            "Role:",
            summarize_role(agent),
            "",
            "Team Playbook:",
            team_playbook(agent),
            "",
            "Shared CEO Directive And Cross-Agent Opinions:",
            shared_directive_context(),
            "",
            "Previous Session Context To Improve From:",
            previous_context or "이전 세션 컨텍스트가 없습니다.",
            "이전 팀 산출물 중 현재 업무에 필요한 것은 발전시키고, 더 이상 필요하지 않거나 유효하지 않은 것은 사용하지 않아도 됩니다.",
            "",
            "Available Team Tools:",
            team_tools(agent),
            "",
            "Recommended Tools For Current Work:",
            recommended_tools(agent, tasks),
            "",
            "Assigned Work:",
            task_text,
            "",
            "Proactive Team Activity Mandate:",
            proactive_team_mandate(agent, tasks),
            "",
            "Company Operating Discipline:",
            "- 모든 판단은 owner, due date, next action 중 최소 하나로 끝내세요.",
            "- KPI 또는 성공 지표에 어떤 영향을 주는지 명시하세요.",
            "- CEO/CFO/Legal/Security 승인이 필요한 항목은 Decision Request로 분리하세요.",
            "- Blocker, dependency, risk는 각각 owner와 해소 조건을 붙이세요.",
            "- 다음 세션에서 발전시킬 산출물과 폐기해도 되는 산출물을 구분하세요.",
            "- 예시나 빈 템플릿만 제출하지 말고, 이번 세션 기준의 실제 내용으로 표, 목록, 기준, 초안, 결정 요청을 채우세요.",
            "",
            "Write the agent's work product with these sections:",
            "## 판단",
            "## 실행 계획",
            "## 산출물 초안",
            "## Proactive Team Activity",
            "## KPI 영향",
            "## Decision Requests",
            "## Blockers",
            "## 이전 세션 대비 개선",
            "## 리스크와 의존성",
            "## 다음 업데이트",
        ]
    )
    return system_prompt, user_prompt


class LLMConnectionError(RuntimeError):
    """Raised when required LLM output cannot be produced."""


def validate_llm_ready(config: LLMConfig) -> None:
    if not config.enabled:
        raise LLMConnectionError("LLM is disabled. Set LLM_ENABLED=true.")
    if config.provider == "none":
        raise LLMConnectionError("LLM provider is none. Set LLM_PROVIDER to ollama, gpt_oss, or chatgpt_oauth.")
    if not config.base_url:
        raise LLMConnectionError(f"{config.provider} base URL is empty.")
    if not config.model:
        raise LLMConnectionError(f"{config.provider} model is empty.")
    if config.requires_bearer_token and not config.api_key:
        raise LLMConnectionError(f"{config.provider} requires a bearer token.")


def render_work_product(
    agent: AgentRuntime,
    tasks: list[WorkItem],
    cycle_id: str,
    llm_content: str,
    previous_context: str = "",
) -> str:
    title = f"# {agent.name} Work Product\n"
    lines = [
        title,
        f"- Cycle: {cycle_id}",
        f"- Agent: {agent.name}",
        f"- Kind: {agent.kind}",
        f"- Parent: {agent.parent or 'Company'}",
        f"- Generated At: {now_iso()}",
        "- LLM: connected",
        "",
        "## Role Understanding",
        "",
        summarize_role(agent),
        "",
        "## Team Playbook",
        "",
        team_playbook(agent),
        "",
        "## Shared CEO Directive",
        "",
        shared_directive_context(),
        "",
        "## Previous Session Context",
        "",
        previous_context or "이전 세션 컨텍스트가 없습니다.",
        "",
        "## Team Tools",
        "",
        team_tools(agent),
        "",
        "## Recommended Tools",
        "",
        recommended_tools(agent, tasks),
        "",
        "## Assigned Work",
        "",
    ]
    if not tasks:
        lines.extend(
            [
                "- 현재 직접 배정된 업무는 없습니다.",
                "- 관련 팀의 산출물을 관찰하고 의존성, 리스크, 지원 요청이 생기면 즉시 기록합니다.",
            ]
        )
    for index, item in enumerate(tasks, start=1):
        lines.extend(
            [
                f"### {index}. {item.task}",
                "",
                f"- Source: {item.source}",
                f"- Status: In Progress",
                f"- Due: {item.due}",
                f"- Dependency: {item.dependency}",
                f"- Done Criteria: {item.done_criteria}",
                "",
                "#### Action Plan",
                "",
                f"- 완료 기준을 기준으로 산출물의 목차를 먼저 잡는다.",
                f"- 필요한 협업 또는 의사결정을 명확히 표시한다.",
                f"- 이번 사이클 안에 검토 가능한 초안을 만든다.",
                "",
                "#### Current Output",
                "",
                f"- `{item.task}` 업무를 시작했고, 완료 기준 `{item.done_criteria}`에 맞춰 초안을 작성합니다.",
                f"- 막힌 지점이 생기면 `Blocked`로 표시하고 COO Agent에게 공유합니다.",
                "",
            ]
        )
    lines.extend(
        [
            "## Proactive Team Activity",
            "",
            proactive_team_mandate(agent, tasks),
            "",
            "## LLM Work Product",
            "",
            llm_content,
            "",
        ]
    )
    lines.extend(
        [
            "## Next Update",
            "",
            "- 다음 heartbeat에서 진행 상태, 리스크, 필요한 결정을 갱신합니다.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_log(agent: AgentRuntime, tasks: list[WorkItem], cycle_id: str, product_path: Path, log_dir: Path) -> str:
    task_summary = ", ".join(item.task for item in tasks) if tasks else "watching for dependencies"
    product_ref = os.path.relpath(product_path, start=log_dir).replace(os.sep, "/")
    return "\n".join(
        [
            f"# {agent.name} Log",
            "",
            f"- Last Heartbeat: {now_iso()}",
            f"- Cycle: {cycle_id}",
            f"- State: active",
            f"- Mode: parallel",
            "- LLM: connected",
            "- LLM Error: None",
            f"- Current Focus: {task_summary}",
            f"- Work Product: {product_ref}",
            "",
        ]
    )


def run_agent(
    agent: AgentRuntime,
    items: list[WorkItem],
    cycle_id: str,
    llm_config: LLMConfig,
    llm_enabled_for_agent: bool,
    llm_semaphore: threading.Semaphore,
    log_dir: Path = LOG_DIR,
    product_dir: Path = PRODUCT_DIR,
    previous_context: str = "",
) -> dict[str, object]:
    tasks = pick_tasks(agent, items)
    product_path = agent_product_path(product_dir, agent)
    log_path = log_dir / f"{agent.slug}.md"

    if not llm_enabled_for_agent:
        raise LLMConnectionError(f"{agent.name} skipped by LLM_AGENT_LIMIT. Increase LLM_AGENT_LIMIT or reduce selected agents.")

    system_prompt, user_prompt = build_agent_prompt(agent, tasks, cycle_id, previous_context=previous_context)
    llm_content, llm_error = call_llm(llm_config, system_prompt, user_prompt, llm_semaphore)
    if llm_error:
        raise LLMConnectionError(f"{agent.name} LLM failed: {llm_error}")
    if not llm_content:
        raise LLMConnectionError(f"{agent.name} LLM returned empty content.")

    work_product = render_work_product(agent, tasks, cycle_id, llm_content, previous_context=previous_context)
    log_content = render_log(agent, tasks, cycle_id, product_path, log_dir)
    atomic_write_text(product_path, work_product)
    atomic_write_text(log_path, log_content)
    latest_product_path = agent_product_path(PRODUCT_DIR, agent)
    if product_path != latest_product_path:
        atomic_write_text(latest_product_path, work_product)
    if log_path != LOG_DIR / f"{agent.slug}.md":
        atomic_write_text(LOG_DIR / f"{agent.slug}.md", log_content)
    recommendations = recommend_tools_for_tasks(team_name_for_agent(agent), tasks)
    return {
        "name": agent.name,
        "kind": agent.kind,
        "parent": agent.parent,
        "tool_team": team_name_for_agent(agent),
        "state": "active",
        "llm": "connected",
        "llm_error": None,
        "task_count": len(tasks),
        "tasks": [dataclasses.asdict(item) for item in tasks],
        "recommended_tools": recommendations,
        "log": str(log_path.relative_to(ROOT)),
        "work_product": str(product_path.relative_to(ROOT)),
        "last_heartbeat": now_iso(),
    }


def failed_agent_result(agent: AgentRuntime, error: BaseException, log_dir: Path = LOG_DIR, product_dir: Path = PRODUCT_DIR) -> dict[str, object]:
    log_path = log_dir / f"{agent.slug}.md"
    product_path = agent_product_path(product_dir, agent)
    error_text = f"{type(error).__name__}: {error}"
    log_content = "\n".join(
        [
            f"# {agent.name} Log",
            "",
            f"- Last Heartbeat: {now_iso()}",
            "- State: failed",
            f"- Error: {error_text}",
            "",
        ]
    )
    product_content = "\n".join(
        [
            f"# {agent.name} Work Product",
            "",
            "## Error",
            "",
            f"- Agent execution failed: {error_text}",
            "",
        ]
    )
    atomic_write_text(log_path, log_content)
    atomic_write_text(product_path, product_content)
    if log_path != LOG_DIR / f"{agent.slug}.md":
        atomic_write_text(LOG_DIR / f"{agent.slug}.md", log_content)
    latest_product_path = agent_product_path(PRODUCT_DIR, agent)
    if product_path != latest_product_path:
        atomic_write_text(latest_product_path, product_content)
    return {
        "name": agent.name,
        "kind": agent.kind,
        "parent": agent.parent,
        "tool_team": team_name_for_agent(agent),
        "state": "failed",
        "error": error_text,
        "llm": "failed",
        "llm_error": error_text,
        "task_count": 0,
        "tasks": [],
        "recommended_tools": [],
        "log": str(log_path.relative_to(ROOT)),
        "work_product": str(product_path.relative_to(ROOT)),
        "last_heartbeat": now_iso(),
    }


def pending_agent_result(
    agent: AgentRuntime,
    items: list[WorkItem],
    lifecycle: str,
    log_dir: Path,
    product_dir: Path,
) -> dict[str, object]:
    tasks = pick_tasks(agent, items)
    product_path = agent_product_path(product_dir, agent)
    log_path = log_dir / f"{agent.slug}.md"
    recommendations = recommend_tools_for_tasks(team_name_for_agent(agent), tasks)
    return {
        "name": agent.name,
        "kind": agent.kind,
        "parent": agent.parent,
        "tool_team": team_name_for_agent(agent),
        "state": lifecycle,
        "lifecycle": lifecycle,
        "llm": "pending" if lifecycle == "queued" else "running",
        "llm_error": None,
        "task_count": len(tasks),
        "tasks": [dataclasses.asdict(item) for item in tasks],
        "recommended_tools": recommendations,
        "log": str(log_path.relative_to(ROOT)),
        "work_product": str(product_path.relative_to(ROOT)),
        "last_heartbeat": now_iso(),
    }


def execution_snapshot(
    lifecycle_by_agent: dict[str, str],
    total_agents: int,
    started_at: str,
    recent_events: list[str],
) -> dict[str, object]:
    completed_states = {"completed", "failed"}
    completed = sum(1 for state in lifecycle_by_agent.values() if state in completed_states)
    failed = sum(1 for state in lifecycle_by_agent.values() if state == "failed")
    running = sum(1 for state in lifecycle_by_agent.values() if state == "running")
    queued = sum(1 for state in lifecycle_by_agent.values() if state == "queued")
    percent = 100.0 if total_agents == 0 else round((completed / total_agents) * 100, 1)
    current_agents = [
        name
        for name, state in sorted(lifecycle_by_agent.items(), key=lambda item: item[0])
        if state == "running"
    ]
    return {
        "state": "failed" if failed else "completed" if completed == total_agents else "running",
        "started_at": started_at,
        "updated_at": now_iso(),
        "total_agents": total_agents,
        "completed_agents": completed,
        "running_agents": running,
        "queued_agents": queued,
        "failed_agents": failed,
        "percent_complete": percent,
        "current_agents": current_agents,
        "recent_events": recent_events[-12:],
    }


def build_runtime_status(
    *,
    cycle_id: str,
    session_number: int,
    session_mode: str,
    output_dir: Path,
    prev_session_dir: Path | None,
    work_item_count: int,
    llm_config: LLMConfig,
    agents: list[dict[str, object]],
    execution: dict[str, object],
    error: str | None = None,
) -> dict[str, object]:
    team_counts: dict[str, int] = {}
    for result in agents:
        team = str(result.get("parent") or "Company")
        team_counts[team] = team_counts.get(team, 0) + 1
    failed_count = sum(1 for result in agents if result.get("state") == "failed" or result.get("lifecycle") == "failed")
    status: dict[str, object] = {
        "cycle_id": cycle_id,
        "session": f"session-{session_number:03d}",
        "session_number": session_number,
        "session_mode": session_mode,
        "output_dir": str(output_dir.relative_to(ROOT)),
        "previous_output_dir": str(prev_session_dir.relative_to(ROOT)) if prev_session_dir else None,
        "generated_at": now_iso(),
        "agent_count": len(agents),
        "failed_agent_count": failed_count,
        "work_item_count": work_item_count,
        "team_count": len(team_counts),
        "teams": team_counts,
        "llm": {
            "enabled": llm_config.enabled,
            "provider": llm_config.provider,
            "base_url": llm_config.base_url,
            "model": llm_config.model,
            "agent_limit": llm_config.agent_limit,
            "concurrency": llm_config.concurrency,
            "connected_count": sum(1 for result in agents if result.get("llm") == "connected"),
        },
        "execution": execution,
        "agents": agents,
    }
    if error:
        status["error"] = error
        cast_llm = status["llm"]
        if isinstance(cast_llm, dict):
            cast_llm["error"] = error
    return status


def render_dashboard(status: dict[str, object]) -> str:
    llm = status.get("llm", {})
    agents = status.get("agents", [])
    execution = status.get("execution", {})
    top_error = str(status.get("error") or "")
    taskful_agents = []
    failed_agents = []
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            if int(agent.get("task_count", 0)) > 0:
                taskful_agents.append(agent)
            if agent.get("state") == "failed":
                failed_agents.append(agent)
    team_counts: dict[str, int] = {}
    team_task_counts: dict[str, int] = {}
    tool_recommendation_counts: dict[str, int] = {}
    total_tool_recommendations = 0
    used_tool_keys: set[tuple[str, str]] = set()
    all_tool_count = 0
    registry = load_json(TEAM_TOOLS_FILE)
    for team, tools in registry.items():
        if isinstance(tools, list):
            all_tool_count += len(tools)
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            team = str(agent.get("parent") or "Company")
            team_counts[team] = team_counts.get(team, 0) + 1
            team_task_counts[team] = team_task_counts.get(team, 0) + int(agent.get("task_count", 0))
            recommendations = agent.get("recommended_tools", [])
            tool_team = str(agent.get("tool_team") or team)
            if isinstance(recommendations, list):
                total_tool_recommendations += len(recommendations)
                tool_recommendation_counts[team] = tool_recommendation_counts.get(team, 0) + len(recommendations)
                for item in recommendations:
                    if isinstance(item, dict):
                        used_tool_keys.add((tool_team, str(item.get("tool"))))

    lines = [
        "# Company Agent Dashboard",
        "",
        f"- Generated At: {status.get('generated_at')}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Agents Active: {status.get('agent_count')}",
        f"- Failed Agents: {status.get('failed_agent_count', len(failed_agents))}",
        f"- Work Items Loaded: {status.get('work_item_count')}",
        "",
    ]
    if isinstance(execution, dict) and execution.get("total_agents") is not None:
        current_agents = execution.get("current_agents", [])
        recent_events = execution.get("recent_events", [])
        lines.extend(
            [
                "## Live Progress",
                "",
                f"- State: {execution.get('state')}",
                f"- Started At: {execution.get('started_at')}",
                f"- Updated At: {execution.get('updated_at')}",
                f"- Progress: {execution.get('completed_agents')}/{execution.get('total_agents')} ({execution.get('percent_complete')}%)",
                f"- Running: {execution.get('running_agents')}",
                f"- Queued: {execution.get('queued_agents')}",
                f"- Failed: {execution.get('failed_agents')}",
            ]
        )
        if isinstance(current_agents, list) and current_agents:
            lines.append("- Current Agents: " + ", ".join(str(name) for name in current_agents[:10]))
        if isinstance(recent_events, list) and recent_events:
            lines.extend(["", "### Recent Events", ""])
            for event in recent_events[-8:]:
                lines.append(f"- {event}")
        lines.append("")
    lines.extend(["## LLM", ""])
    if isinstance(llm, dict):
        lines.extend(
            [
                f"- Enabled: {llm.get('enabled')}",
                f"- Provider: {llm.get('provider')}",
                f"- Model: {llm.get('model')}",
                f"- Agent Limit: {llm.get('agent_limit')}",
                f"- Concurrency: {llm.get('concurrency')}",
                f"- Connected: {llm.get('connected_count')}",
                "",
            ]
        )
    lines.extend(["## Teams", ""])
    for team in sorted(team_counts):
        lines.append(f"- {team}: {team_counts[team]} agent(s), {team_task_counts.get(team, 0)} task(s)")
    lines.append("")
    lines.extend(["## Tools", ""])
    coverage = 0 if all_tool_count == 0 else round((len(used_tool_keys) / all_tool_count) * 100, 1)
    lines.append(f"- Recommended Tool Uses: {total_tool_recommendations}")
    lines.append(f"- Tool Coverage: {coverage}% ({len(used_tool_keys)}/{all_tool_count})")
    lines.append(f"- Cycle Brief: {CYCLE_BRIEF_FILE.relative_to(ROOT)}")
    lines.append(f"- Operating Review: {OPERATING_REVIEW_FILE.relative_to(ROOT)}")
    lines.append(f"- CEO Session Review: {CEO_SESSION_REVIEW_FILE.relative_to(ROOT)}")
    lines.append(f"- Team Activity Plan: {TEAM_ACTIVITY_FILE.relative_to(ROOT)}")
    lines.append(f"- Team Session Results: {TEAM_SESSION_RESULTS_FILE.relative_to(ROOT)}")
    lines.append(f"- Team Result Documents: {TEAM_RESULT_DIR.relative_to(ROOT)}")
    lines.append(f"- Usage Report: {TOOL_USAGE_MD_FILE.relative_to(ROOT)}")
    lines.append(f"- Audit Report: {TOOL_AUDIT_FILE.relative_to(ROOT)}")
    for team in sorted(tool_recommendation_counts):
        lines.append(f"- {team}: {tool_recommendation_counts[team]} recommendation(s)")
    lines.append("")
    lines.extend(["## Agents With Work", ""])
    for agent in taskful_agents[:25]:
        lines.append(f"- {agent.get('name')}: {agent.get('task_count')} task(s), LLM {agent.get('llm')}")
    if len(taskful_agents) > 25:
        lines.append(f"- ...and {len(taskful_agents) - 25} more")
    lines.extend(["", "## Failed Agents", ""])
    if top_error:
        lines.append(f"- Run failed: {top_error}")
    if not failed_agents:
        if not top_error:
            lines.append("- None")
    for agent in failed_agents:
        lines.append(f"- {agent.get('name')}: {agent.get('error')}")
    return "\n".join(lines).rstrip() + "\n"


def render_cycle_brief(status: dict[str, object]) -> str:
    agents = status.get("agents", [])
    llm = status.get("llm", {})
    top_error = str(status.get("error") or "")
    by_team: dict[str, dict[str, object]] = {}
    failed_agents: list[dict[str, object]] = []
    top_agent_actions: list[tuple[int, str, str, str]] = []

    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            team = str(agent.get("parent") or "Company")
            summary = by_team.setdefault(
                team,
                {
                    "agents": 0,
                    "tasks": 0,
                    "failed": 0,
                    "tools": 0,
                    "actions": [],
                },
            )
            summary["agents"] = int(summary["agents"]) + 1
            task_count = int(agent.get("task_count", 0))
            summary["tasks"] = int(summary["tasks"]) + task_count
            recommendations = agent.get("recommended_tools", [])
            if isinstance(recommendations, list):
                summary["tools"] = int(summary["tools"]) + len(recommendations)
            if agent.get("state") == "failed":
                summary["failed"] = int(summary["failed"]) + 1
                failed_agents.append(agent)
            tasks = agent.get("tasks", [])
            if isinstance(tasks, list):
                for task in tasks[:2]:
                    if not isinstance(task, dict):
                        continue
                    action = str(task.get("task") or "")
                    due = str(task.get("due") or "")
                    if action:
                        top_agent_actions.append((task_count, team, str(agent.get("name")), f"{action} ({due})"))

    sorted_teams = sorted(
        by_team.items(),
        key=lambda item: (-int(item[1]["tasks"]), item[0]),
    )
    top_agent_actions.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))

    lines = [
        "# Cycle Brief",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Session Mode: {status.get('session_mode') or 'unknown'}",
        f"- Generated At: {status.get('generated_at')}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Previous Session: {status.get('previous_output_dir') or 'none'}",
        f"- Agents: {status.get('agent_count')}",
        f"- Work Items: {status.get('work_item_count')}",
        f"- Failed Agents: {status.get('failed_agent_count', 0)}",
        "",
        "## Executive Readout",
        "",
    ]
    if isinstance(llm, dict):
        lines.append(
            "- LLM: "
            f"{llm.get('provider')} / {llm.get('model')} "
            f"connected {llm.get('connected_count')} agent(s)"
        )
    if sorted_teams:
        busiest_team, busiest = sorted_teams[0]
        lines.append(f"- Highest workload: {busiest_team} with {busiest['tasks']} assigned task(s)")
    if top_error:
        lines.append(f"- Attention needed: {top_error}")
    elif failed_agents:
        lines.append(f"- Attention needed: {len(failed_agents)} failed agent(s)")
    else:
        lines.append("- Attention needed: none detected")

    lines.extend(["", "## Team Load", "", "| Team | Agents | Tasks | Tool Recommendations | Failed |"])
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for team, summary in sorted_teams:
        lines.append(
            f"| {team} | {summary['agents']} | {summary['tasks']} | {summary['tools']} | {summary['failed']} |"
        )

    lines.extend(["", "## Priority Actions", ""])
    if not top_agent_actions:
        lines.append("- No direct task actions found.")
    for _, team, agent_name, action in top_agent_actions[:20]:
        lines.append(f"- {team} / {agent_name}: {action}")

    lines.extend(["", "## Failure Reasons", ""])
    if top_error:
        lines.append(f"- RUN FAILED: {top_error}")
    if failed_agents:
        for agent in failed_agents:
            lines.append(f"- FAILED {agent.get('name')}: {agent.get('error') or agent.get('llm_error')}")
    if not failed_agents and not top_error:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Recommended Operator Commands",
            "",
            "- `./company-agents/agent-status`",
            "- `./company-agents/run-agents --doctor`",
            "- `./company-agents/run-agents --show-tool-audit`",
            f"- `sed -n '1,220p' {OPERATING_REVIEW_FILE.relative_to(ROOT)}`",
            f"- `sed -n '1,220p' {CEO_SESSION_REVIEW_FILE.relative_to(ROOT)}`",
            f"- `sed -n '1,220p' {TEAM_ACTIVITY_FILE.relative_to(ROOT)}`",
            f"- `sed -n '1,220p' {TEAM_SESSION_RESULTS_FILE.relative_to(ROOT)}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def operating_health_score(status: dict[str, object]) -> int:
    agent_count = int(status.get("agent_count") or 0)
    failed_count = int(status.get("failed_agent_count") or 0)
    work_item_count = int(status.get("work_item_count") or 0)
    llm = status.get("llm", {})
    connected_count = int(llm.get("connected_count") or 0) if isinstance(llm, dict) else 0
    score = 100
    if agent_count == 0:
        score -= 35
    if work_item_count == 0:
        score -= 20
    if agent_count and failed_count:
        score -= min(35, round((failed_count / agent_count) * 35))
    if agent_count and connected_count < agent_count:
        score -= min(25, round(((agent_count - connected_count) / agent_count) * 25))
    if status.get("error"):
        score -= 20
    return max(0, min(100, score))


def render_operating_review(status: dict[str, object]) -> str:
    agents = status.get("agents", [])
    llm = status.get("llm", {})
    top_error = str(status.get("error") or "")
    score = operating_health_score(status)
    by_team: dict[str, dict[str, int]] = {}
    failed_agents: list[dict[str, object]] = []
    decision_request_owners = {
        "CEO Agent",
        "CFO Agent",
        "Legal Agent",
        "Security and Risk Manager",
        "CTO Agent",
    }

    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            team = str(agent.get("parent") or "Company")
            summary = by_team.setdefault(team, {"agents": 0, "tasks": 0, "failed": 0, "tools": 0})
            summary["agents"] += 1
            summary["tasks"] += int(agent.get("task_count") or 0)
            recommendations = agent.get("recommended_tools", [])
            if isinstance(recommendations, list):
                summary["tools"] += len(recommendations)
            if agent.get("state") == "failed":
                summary["failed"] += 1
                failed_agents.append(agent)

    gates = [
        ("CEO directive", bool(status.get("cycle_id")), "이번 세션 목표와 판단 기준"),
        ("COO task board", int(status.get("work_item_count") or 0) > 0, "담당자, 마감일, 완료 기준"),
        ("LLM execution", isinstance(llm, dict) and int(llm.get("connected_count") or 0) > 0, "agent가 실제로 판단을 생성했는지"),
        ("Risk and blocker review", not top_error and not failed_agents, "실패, 블로커, 승인 필요사항 관리"),
        ("Session continuity", bool(status.get("previous_output_dir")) or status.get("session_mode") == "initial", "직전 세션 산출물 재활용"),
        ("Team accountability", bool(by_team), "팀별 업무량과 실패 상태"),
    ]

    lines = [
        "# Operating Review",
        "",
        "이 문서는 각 세션이 실제 회사 운영처럼 다음 의사결정과 실행으로 이어지는지 점검합니다.",
        "",
        "## Company Readiness",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Health Score: {score}/100",
        f"- State: {'FAILED' if top_error or failed_agents else 'OPERATING'}",
        f"- Required Attention: {top_error or (str(len(failed_agents)) + ' failed agent(s)' if failed_agents else 'none')}",
        "",
        "## Operating Gates",
        "",
        "| Gate | Status | Purpose |",
        "| --- | --- | --- |",
    ]
    for name, passed, purpose in gates:
        lines.append(f"| {name} | {'OK' if passed else 'NEEDS ATTENTION'} | {purpose} |")

    lines.extend(
        [
            "",
            "## Executive Decisions Needed",
            "",
        ]
    )
    decision_lines: list[str] = []
    if top_error:
        decision_lines.append(f"- CEO/CTO: LLM 실행 실패 해결 필요 - {top_error}")
    if failed_agents:
        for agent in failed_agents[:10]:
            decision_lines.append(f"- {agent.get('name')}: 실패 원인 확인 및 재실행 결정 - {agent.get('error')}")
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            tasks = agent.get("tasks", [])
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                owner = str(task.get("owner") or agent.get("name") or "")
                dependency = str(task.get("dependency") or "")
                if owner in decision_request_owners or "CEO" in dependency or "Legal" in dependency or "CFO" in dependency:
                    decision_lines.append(f"- {owner}: {task.get('task')} (dependency: {dependency or 'none'})")
                if len(decision_lines) >= 15:
                    break
            if len(decision_lines) >= 15:
                break
    lines.extend(decision_lines or ["- No executive decision requests detected from structured task data."])

    lines.extend(["", "## Team Accountability", "", "| Team | Agents | Tasks | Tool Recommendations | Failed |"])
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for team, summary in sorted(by_team.items(), key=lambda item: (-item[1]["tasks"], item[0])):
        lines.append(f"| {team} | {summary['agents']} | {summary['tasks']} | {summary['tools']} | {summary['failed']} |")
    if not by_team:
        lines.append("| None | 0 | 0 | 0 | 0 |")

    lines.extend(
        [
            "",
            "## Next Session Mandate",
            "",
            "- CEO Agent: 최상위 목표, 하지 않을 일, 승인 필요한 결정을 명확히 정리합니다.",
            "- COO Agent: 실패 agent와 blocked 업무를 재배정하고 다음 세션의 우선순위를 좁힙니다.",
            "- Managers: 팀별 산출물 중 계속 발전시킬 것과 폐기할 것을 표시합니다.",
            "- Staff: 산출물마다 owner, due date, KPI 영향, next action을 남깁니다.",
            "- Reviewers: CFO, Legal, Security, Data 관점의 승인 필요사항을 별도 항목으로 분리합니다.",
            "",
            "## Operating Cadence",
            "",
            "- Every session: CEO directive, team execution, operating review, next session mandate.",
            "- Every 3 sessions: KPI와 리스크를 기준으로 우선순위를 줄입니다.",
            "- Every 5 sessions: 유지할 팀/중단할 업무/자동화할 업무를 정리합니다.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_ceo_session_review(status: dict[str, object]) -> str:
    agents = status.get("agents", [])
    top_error = str(status.get("error") or "")
    by_team: dict[str, dict[str, object]] = {}

    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            team = str(agent.get("parent") or "Company")
            summary = by_team.setdefault(
                team,
                {
                    "agents": 0,
                    "tasks": 0,
                    "failed": 0,
                    "tools": 0,
                    "agent_names": [],
                    "actions": [],
                    "failures": [],
                },
            )
            summary["agents"] = int(summary["agents"]) + 1
            summary["tasks"] = int(summary["tasks"]) + int(agent.get("task_count") or 0)
            cast_agent_names = summary["agent_names"]
            if isinstance(cast_agent_names, list):
                cast_agent_names.append(str(agent.get("name") or "unknown"))
            recommendations = agent.get("recommended_tools", [])
            if isinstance(recommendations, list):
                summary["tools"] = int(summary["tools"]) + len(recommendations)
            if agent.get("state") == "failed":
                summary["failed"] = int(summary["failed"]) + 1
                failures = summary["failures"]
                if isinstance(failures, list):
                    failures.append(f"{agent.get('name')}: {agent.get('error') or agent.get('llm_error')}")
            tasks = agent.get("tasks", [])
            actions = summary["actions"]
            if isinstance(tasks, list) and isinstance(actions, list):
                for task in tasks[:3]:
                    if isinstance(task, dict) and task.get("task"):
                        actions.append(str(task.get("task")))

    if not by_team:
        by_team["Company"] = {
            "agents": int(status.get("agent_count") or 0),
            "tasks": 0,
            "failed": int(status.get("failed_agent_count") or 0),
            "tools": 0,
            "agent_names": [],
            "actions": [],
            "failures": [top_error] if top_error else [],
        }

    lines = [
        "# CEO Session Review",
        "",
        "CEO Agent가 이번 세션 결과를 팀별로 평가하고 다음 세션 지시를 정리하는 문서입니다.",
        "",
        "## Executive Summary",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Generated At: {status.get('generated_at')}",
        f"- Overall Assessment: {'LLM/agent execution must be fixed before company operation can continue.' if top_error else 'Company agents completed the session and can continue with focused follow-up.'}",
        f"- Required CEO Attention: {top_error or 'Review team directives and narrow next session priorities.'}",
        "",
        "## CEO Team Evaluations",
        "",
    ]

    for team, summary in sorted(by_team.items(), key=lambda item: (-int(item[1]["tasks"]), item[0])):
        failed = int(summary["failed"])
        tasks = int(summary["tasks"])
        tools = int(summary["tools"])
        if failed:
            rating = "Needs Intervention"
            evaluation = "이번 세션에서 실패가 발생했으므로 다음 세션 전에 실행 가능 상태를 회복해야 합니다."
        elif tasks == 0:
            rating = "Watch"
            evaluation = "직접 배정 업무가 적거나 관찰 역할에 머물렀습니다. 다음 세션에서 명확한 산출물을 배정해야 합니다."
        elif tools == 0:
            rating = "Needs Sharpening"
            evaluation = "업무는 수행했지만 도구 활용 신호가 약합니다. 산출물을 운영 도구와 연결해야 합니다."
        else:
            rating = "On Track"
            evaluation = "담당 업무와 도구 활용이 확인됩니다. 다음 세션에서 산출물 품질과 실행 결과를 더 구체화합니다."

        actions = summary["actions"]
        failures = summary["failures"]
        agent_names = summary["agent_names"]
        lines.extend(
            [
                f"### {team}",
                "",
                f"- CEO Rating: {rating}",
                f"- Team Coverage: {summary['agents']} agent(s), {tasks} task(s), {tools} tool recommendation(s), {failed} failed",
                f"- Evaluation: {evaluation}",
                f"- Key Agents: {', '.join(agent_names[:6]) if isinstance(agent_names, list) and agent_names else 'none recorded'}",
                "",
                "#### What To Continue",
                "",
            ]
        )
        if isinstance(actions, list) and actions:
            for action in actions[:5]:
                lines.append(f"- Continue or refine: {action}")
        else:
            lines.append("- Maintain team monitoring, but convert the next session into concrete deliverables.")

        lines.extend(["", "#### What To Change Or Add", ""])
        if failed:
            lines.append("- Fix failed agent execution first; do not expand scope until the team can produce a valid work product.")
        elif tasks == 0:
            lines.append("- Add at least one explicit owner, due date, and reviewable deliverable for this team.")
        else:
            lines.append("- Tighten next actions so each deliverable has owner, due date, KPI impact, and approval requirement.")
        if tools == 0:
            lines.append("- Connect work to at least one team tool or explain why no tool is needed.")

        lines.extend(["", "#### Next Session CEO Directive", ""])
        if failed:
            lines.append("- Re-run this team after the LLM/runtime issue is fixed and submit a recovery note.")
        elif tasks == 0:
            lines.append("- Submit a concrete work product instead of only observing cross-team dependencies.")
        else:
            lines.append("- Improve the prior work product and explicitly mark keep, change, add, and drop decisions.")

        if isinstance(failures, list) and failures:
            lines.extend(["", "#### Failure Notes", ""])
            for failure in failures[:5]:
                lines.append(f"- {failure}")
        lines.append("")

    lines.extend(
        [
            "## Company-Wide Next Session Instructions",
            "",
            "- CEO Agent: review this file first and narrow the next session to the highest-leverage decisions.",
            "- COO Agent: update task routing from the team directives above.",
            "- Managers: assign each team member a next action based on keep, change, add, and drop decisions.",
            "- Staff: read the team section before using prior work products.",
            "- Reviewers: escalate approval, legal, security, finance, or KPI gaps before execution expands.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_team_activity_plan(status: dict[str, object]) -> str:
    agents = status.get("agents", [])
    top_error = str(status.get("error") or "")
    by_team: dict[str, dict[str, object]] = {}

    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            team = str(agent.get("parent") or "Company")
            summary = by_team.setdefault(
                team,
                {
                    "agents": 0,
                    "tasks": 0,
                    "failed": 0,
                    "tools": 0,
                    "owners": [],
                    "actions": [],
                    "asks": [],
                },
            )
            summary["agents"] = int(summary["agents"]) + 1
            summary["tasks"] = int(summary["tasks"]) + int(agent.get("task_count") or 0)
            if agent.get("state") == "failed":
                summary["failed"] = int(summary["failed"]) + 1
            owners = summary["owners"]
            if isinstance(owners, list):
                owners.append(str(agent.get("name") or "unknown"))
            recommendations = agent.get("recommended_tools", [])
            if isinstance(recommendations, list):
                summary["tools"] = int(summary["tools"]) + len(recommendations)
            tasks = agent.get("tasks", [])
            actions = summary["actions"]
            asks = summary["asks"]
            if isinstance(tasks, list):
                for task in tasks[:4]:
                    if not isinstance(task, dict):
                        continue
                    action = str(task.get("task") or "")
                    dependency = str(task.get("dependency") or "")
                    if action and isinstance(actions, list):
                        actions.append(action)
                    if dependency and dependency.lower() != "none" and isinstance(asks, list):
                        asks.append(f"{task.get('owner') or agent.get('name')}: {dependency}")

    if not by_team:
        by_team["Company"] = {
            "agents": int(status.get("agent_count") or 0),
            "tasks": 0,
            "failed": int(status.get("failed_agent_count") or 0),
            "tools": 0,
            "owners": [],
            "actions": [],
            "asks": [top_error] if top_error else [],
        }

    lines = [
        "# Team Activity Plan",
        "",
        "각 팀이 다음 세션에서 더 적극적으로 움직이도록 CEO/COO 관점의 행동 계획을 정리합니다.",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Generated At: {status.get('generated_at')}",
        f"- Run Attention: {top_error or 'none'}",
        "",
        "## Activity Rules For Next Session",
        "",
        "- 모든 팀은 `do now`, `ask another team`, `escalate`, `next session`을 구분합니다.",
        "- 직접 업무가 없어도 팀 플레이북 기준으로 산출물 개선, 리스크 제거, 의존성 정리 중 하나를 수행합니다.",
        "- Manager는 팀원별 다음 액션을 재배정하고, Staff는 검토 가능한 산출물을 남깁니다.",
        "- 실패한 팀은 범위를 넓히지 말고 실행 복구와 원인 기록을 먼저 합니다.",
        "",
        "## Team Activity Directives",
        "",
    ]

    for team, summary in sorted(by_team.items(), key=lambda item: (-int(item[1]["tasks"]), item[0])):
        tasks = int(summary["tasks"])
        failed = int(summary["failed"])
        tools = int(summary["tools"])
        owners = summary["owners"]
        actions = summary["actions"]
        asks = summary["asks"]
        lines.extend(
            [
                f"### {team}",
                "",
                f"- Activity Level: {'Recover First' if failed else ('High' if tasks else 'Needs Activation')}",
                f"- Coverage: {summary['agents']} agent(s), {tasks} task(s), {tools} tool recommendation(s), {failed} failed",
                f"- Active Owners: {', '.join(owners[:8]) if isinstance(owners, list) and owners else 'none recorded'}",
                "",
                "#### Do Now",
                "",
            ]
        )
        if failed:
            lines.append("- Recover failed execution and produce a short recovery note before expanding scope.")
        elif isinstance(actions, list) and actions:
            for action in actions[:5]:
                lines.append(f"- Advance: {action}")
        else:
            lines.append("- Pick one team playbook output and create or improve it in the next session.")

        lines.extend(["", "#### Ask Another Team", ""])
        if isinstance(asks, list) and asks:
            for ask in asks[:5]:
                lines.append(f"- Request input for: {ask}")
        else:
            lines.append("- Identify one dependency or useful review request for another team.")

        lines.extend(["", "#### Escalate", ""])
        if failed:
            lines.append("- Escalate runtime/LLM failure to CEO Agent and CTO Agent.")
        elif tools == 0:
            lines.append("- Escalate missing tool usage or explain why no tool is needed.")
        else:
            lines.append("- Escalate only approval, legal, security, finance, or KPI gaps.")

        lines.extend(
            [
                "",
                "#### Next Session",
                "",
                "- Return with keep/change/add/drop decisions for this team's prior output.",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def read_result_content(path_text: str, max_lines: int = 140) -> str:
    if not path_text:
        return ""
    path = ROOT / path_text
    if not path.exists() or not path.is_file():
        return ""
    lines = read_text(path).splitlines()
    excerpt = "\n".join(lines[:max_lines]).strip()
    if len(lines) > max_lines:
        excerpt += f"\n\n...truncated after {max_lines} lines..."
    return excerpt


def render_team_session_results(status: dict[str, object]) -> str:
    agents = status.get("agents", [])
    by_team: dict[str, list[dict[str, object]]] = {}
    if isinstance(agents, list):
        for agent in agents:
            if isinstance(agent, dict):
                team = str(agent.get("parent") or "Company")
                by_team.setdefault(team, []).append(agent)

    lines = [
        "# Team Session Results",
        "",
        "이번 세션에서 각 팀이 남긴 결과물만 팀별로 정리합니다.",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Generated At: {status.get('generated_at')}",
        f"- Output: {status.get('output_dir') or 'runtime latest only'}",
        "",
        "## Team Result Index",
        "",
        "| Team | Agents | Tasks | Failed | Work Products |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for team, team_agents in sorted(by_team.items()):
        task_count = sum(int(agent.get("task_count") or 0) for agent in team_agents)
        failed_count = sum(1 for agent in team_agents if agent.get("state") == "failed")
        product_count = sum(1 for agent in team_agents if agent.get("work_product"))
        lines.append(f"| {team} | {len(team_agents)} | {task_count} | {failed_count} | {product_count} |")
    if not by_team:
        lines.append("| None | 0 | 0 | 0 | 0 |")

    lines.extend(["", "## Team Results", ""])
    if not by_team:
        lines.extend(
            [
                "### No Agent Results",
                "",
                "#### Result Content",
                "",
                "- No team result content was produced because no agent reached execution.",
                "",
            ]
        )
    for team, team_agents in sorted(by_team.items()):
        lines.extend([f"### {team}", ""])
        for agent in sorted(team_agents, key=lambda item: str(item.get("name") or "")):
            name = str(agent.get("name") or "unknown")
            state = str(agent.get("state") or "unknown")
            product = str(agent.get("work_product") or "")
            log_path = str(agent.get("log") or "")
            tasks = agent.get("tasks", [])
            recommendations = agent.get("recommended_tools", [])
            lines.extend(
                [
                    f"#### {name}",
                    "",
                    f"- State: {state}",
                    f"- Work Product: {product or 'none'}",
                    f"- Log: {log_path or 'none'}",
                    f"- Task Count: {agent.get('task_count', 0)}",
                    "",
                    "##### Tasks",
                    "",
                ]
            )
            if isinstance(tasks, list) and tasks:
                for task in tasks[:8]:
                    if not isinstance(task, dict):
                        continue
                    lines.append(
                        f"- {task.get('task')} "
                        f"(status: {task.get('status')}, due: {task.get('due')}, dependency: {task.get('dependency')})"
                    )
            else:
                lines.append("- No structured tasks recorded.")

            lines.extend(["", "##### Recommended Tools", ""])
            if isinstance(recommendations, list) and recommendations:
                for item in recommendations[:8]:
                    if isinstance(item, dict):
                        lines.append(f"- {item.get('tool')} ({item.get('type')})")
                    else:
                        lines.append(f"- {item}")
            else:
                lines.append("- None recorded.")

            error = agent.get("error") or agent.get("llm_error")
            if error:
                lines.extend(["", "##### Failure", "", f"- {error}"])
            result_content = read_result_content(product)
            lines.extend(["", "##### Result Content", ""])
            if result_content:
                lines.extend(["```markdown", result_content, "```"])
            else:
                lines.append("- No work product content available for this session.")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_single_team_result(status: dict[str, object], team: str, team_agents: list[dict[str, object]]) -> str:
    lines = [
        f"# {team} Session Result",
        "",
        "이번 세션에서 이 팀이 실제로 남긴 결과물 본문을 모은 문서입니다.",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Cycle: {status.get('cycle_id')}",
        f"- Generated At: {status.get('generated_at')}",
        "",
        "## Team Summary",
        "",
        f"- Agents: {len(team_agents)}",
        f"- Tasks: {sum(int(agent.get('task_count') or 0) for agent in team_agents)}",
        f"- Failed: {sum(1 for agent in team_agents if agent.get('state') == 'failed')}",
        "",
        "## Results By Agent",
        "",
    ]
    for agent in sorted(team_agents, key=lambda item: str(item.get("name") or "")):
        name = str(agent.get("name") or "unknown")
        product = str(agent.get("work_product") or "")
        result_content = read_result_content(product, max_lines=180)
        lines.extend(
            [
                f"### {name}",
                "",
                f"- State: {agent.get('state') or 'unknown'}",
                f"- Work Product: {product or 'none'}",
                "",
                "#### Actual Result",
                "",
            ]
        )
        if result_content:
            lines.extend(["```markdown", result_content, "```"])
        else:
            lines.append("- No work product content available for this session.")
        error = agent.get("error") or agent.get("llm_error")
        if error:
            lines.extend(["", "#### Failure", "", f"- {error}"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_team_result_documents(status: dict[str, object], result_dir: Path) -> None:
    agents = status.get("agents", [])
    by_team: dict[str, list[dict[str, object]]] = {}
    if isinstance(agents, list):
        for agent in agents:
            if isinstance(agent, dict):
                team = str(agent.get("parent") or "Company")
                by_team.setdefault(team, []).append(agent)
    lines = [
        "# Team Result Documents",
        "",
        f"- Session: {status.get('session') or 'n/a'}",
        f"- Cycle: {status.get('cycle_id')}",
        "",
        "| Team | Result |",
        "| --- | --- |",
    ]
    for team, team_agents in sorted(by_team.items()):
        filename = f"{slugify(team)}.md"
        atomic_write_text(result_dir / filename, render_single_team_result(status, team, team_agents))
        lines.append(f"| {team} | [{filename}]({filename}) |")
    if not by_team:
        lines.append("| None | none |")
    atomic_write_text(result_dir / "README.md", "\n".join(lines).rstrip() + "\n")


def write_status(status: dict[str, object], output_dir: Path | None = None) -> None:
    atomic_write_json(STATUS_FILE, status)
    render_tool_usage_reports(status)
    atomic_write_text(DASHBOARD_FILE, render_dashboard(status))
    atomic_write_text(CYCLE_BRIEF_FILE, render_cycle_brief(status))
    atomic_write_text(OPERATING_REVIEW_FILE, render_operating_review(status))
    atomic_write_text(CEO_SESSION_REVIEW_FILE, render_ceo_session_review(status))
    atomic_write_text(TEAM_ACTIVITY_FILE, render_team_activity_plan(status))
    atomic_write_text(TEAM_SESSION_RESULTS_FILE, render_team_session_results(status))
    write_team_result_documents(status, TEAM_RESULT_DIR)
    if output_dir is not None:
        atomic_write_json(output_dir / "status.json", status)
        render_tool_usage_reports(
            status,
            usage_json_path=output_dir / "tool-usage.json",
            usage_md_path=output_dir / "TOOL-USAGE.md",
            audit_path=output_dir / "TOOL-AUDIT.md",
        )
        atomic_write_text(output_dir / "DASHBOARD.md", render_dashboard(status))
        atomic_write_text(output_dir / "CYCLE-BRIEF.md", render_cycle_brief(status))
        atomic_write_text(output_dir / "OPERATING-REVIEW.md", render_operating_review(status))
        atomic_write_text(output_dir / "CEO-SESSION-REVIEW.md", render_ceo_session_review(status))
        atomic_write_text(output_dir / "TEAM-ACTIVITY-PLAN.md", render_team_activity_plan(status))
        atomic_write_text(output_dir / "TEAM-SESSION-RESULTS.md", render_team_session_results(status))
        write_team_result_documents(status, output_dir / "team-results")
        write_session_index()


def write_llm_failure_status(
    cycle_id: str,
    config: LLMConfig,
    error: str,
    output_dir: Path | None = None,
    session_number: int | None = None,
    previous_output_dir: Path | None = None,
    session_mode: str | None = None,
) -> None:
    status = {
        "cycle_id": cycle_id,
        "session": f"session-{session_number:03d}" if session_number else None,
        "session_number": session_number,
        "session_mode": session_mode or session_mode_for_previous(previous_output_dir),
        "output_dir": str(output_dir.relative_to(ROOT)) if output_dir else None,
        "previous_output_dir": str(previous_output_dir.relative_to(ROOT)) if previous_output_dir else None,
        "generated_at": now_iso(),
        "agent_count": 0,
        "failed_agent_count": 0,
        "work_item_count": 0,
        "team_count": 0,
        "teams": {},
        "llm": {
            "enabled": config.enabled,
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "agent_limit": config.agent_limit,
            "concurrency": config.concurrency,
            "connected_count": 0,
            "error": error,
        },
        "agents": [],
        "error": error,
    }
    write_status(status, output_dir=output_dir)


def run_cycle(
    max_workers: int,
    cycle_id: str,
    agent_filter: str | None = None,
    team_filter: str | None = None,
) -> dict[str, object]:
    RUNTIME_DIR.mkdir(exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    session_number = next_session_number()
    output_dir = output_dir_for_session(session_number)
    prev_session_dir = previous_session_dir(session_number)
    session_mode = session_mode_for_previous(prev_session_dir)
    prev_context = previous_session_context(prev_session_dir)
    output_log_dir = output_dir / "agent-logs"
    output_product_dir = output_dir / "work-products"
    output_log_dir.mkdir(parents=True, exist_ok=True)
    output_product_dir.mkdir(parents=True, exist_ok=True)

    task_board = read_text(ROOT / "TASK-BOARD.md")
    work_items = [
        *parse_current_cycle_tasks(task_board),
        *parse_manager_tasks(task_board),
        *parse_staff_tasks(task_board),
    ]
    agents = build_agents(agent_filter=agent_filter, team_filter=team_filter)
    llm_config = build_llm_config()
    try:
        validate_llm_ready(llm_config)
    except LLMConnectionError as error:
        write_llm_failure_status(
            cycle_id,
            llm_config,
            str(error),
            output_dir=output_dir,
            session_number=session_number,
            previous_output_dir=prev_session_dir,
            session_mode=session_mode,
        )
        raise
    if llm_config.agent_limit < len(agents):
        error = (
            f"LLM_AGENT_LIMIT={llm_config.agent_limit} is lower than selected agent count {len(agents)}. "
            "No fallback execution is allowed."
        )
        write_llm_failure_status(
            cycle_id,
            llm_config,
            error,
            output_dir=output_dir,
            session_number=session_number,
            previous_output_dir=prev_session_dir,
            session_mode=session_mode,
        )
        raise LLMConnectionError(error)
    llm_semaphore = threading.Semaphore(llm_config.concurrency)
    llm_enabled_agents = {agent.name for agent in agents}
    started_at = now_iso()
    lifecycle_by_agent = {agent.name: "queued" for agent in agents}
    for agent in agents[:max_workers]:
        lifecycle_by_agent[agent.name] = "running"
    recent_events = [f"{started_at} session started with {len(agents)} agent(s)"]
    result_by_agent: dict[str, dict[str, object]] = {
        agent.name: pending_agent_result(
            agent,
            work_items,
            lifecycle_by_agent[agent.name],
            output_log_dir,
            output_product_dir,
        )
        for agent in agents
    }

    def publish_progress(error: str | None = None) -> dict[str, object]:
        ordered_results = [result_by_agent[agent.name] for agent in agents]
        status = build_runtime_status(
            cycle_id=cycle_id,
            session_number=session_number,
            session_mode=session_mode,
            output_dir=output_dir,
            prev_session_dir=prev_session_dir,
            work_item_count=len(work_items),
            llm_config=llm_config,
            agents=ordered_results,
            execution=execution_snapshot(lifecycle_by_agent, len(agents), started_at, recent_events),
            error=error,
        )
        write_status(status, output_dir=output_dir)
        return status

    publish_progress()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_agent = {
            executor.submit(
                run_agent,
                agent,
                work_items,
                cycle_id,
                llm_config,
                agent.name in llm_enabled_agents,
                llm_semaphore,
                output_log_dir,
                output_product_dir,
                prev_context,
            ): agent
            for agent in agents
        }
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_agent):
            agent = future_to_agent[future]
            try:
                result = future.result()
                result["lifecycle"] = "completed"
                result_by_agent[agent.name] = result
                lifecycle_by_agent[agent.name] = "completed"
                completed_count += 1
                recent_events.append(f"{now_iso()} completed {agent.name}")
                next_index = max_workers + completed_count - 1
                if next_index < len(agents):
                    next_agent = agents[next_index]
                    if lifecycle_by_agent.get(next_agent.name) == "queued":
                        lifecycle_by_agent[next_agent.name] = "running"
                        result_by_agent[next_agent.name] = pending_agent_result(
                            next_agent,
                            work_items,
                            "running",
                            output_log_dir,
                            output_product_dir,
                        )
                        recent_events.append(f"{now_iso()} started {next_agent.name}")
                publish_progress()
            except Exception as error:
                failed_result = failed_agent_result(agent, error, log_dir=output_log_dir, product_dir=output_product_dir)
                failed_result["lifecycle"] = "failed"
                result_by_agent[agent.name] = failed_result
                lifecycle_by_agent[agent.name] = "failed"
                recent_events.append(f"{now_iso()} failed {agent.name}: {error}")
                for pending in future_to_agent:
                    if pending is not future:
                        pending.cancel()
                publish_progress(error=str(error))
                raise LLMConnectionError(str(error)) from error

    return publish_progress()


def render_console_report(status: dict[str, object]) -> str:
    llm = status.get("llm", {})
    error = str(status.get("error") or "")
    failed = int(status.get("failed_agent_count") or 0)
    agent_count = int(status.get("agent_count") or 0)
    execution = status.get("execution", {})
    execution_state = str(execution.get("state") or "").upper() if isinstance(execution, dict) else ""
    state = "FAILED" if error or failed else execution_state or "OK"
    session = str(status.get("session") or "n/a")
    lines = [
        "",
        blue_text(f"Session {session}"),
        "Company Agents Runtime",
        "======================",
        f"State       : {state}",
        f"Session     : {session}",
        f"Mode        : {status.get('session_mode') or 'unknown'}",
        f"Cycle       : {status.get('cycle_id')}",
        f"Generated   : {status.get('generated_at')}",
        f"Output      : {status.get('output_dir') or 'runtime latest only'}",
        f"Previous    : {status.get('previous_output_dir') or 'none'}",
        "",
        "LLM",
        "---",
    ]
    if isinstance(llm, dict):
        lines.extend(
            [
                f"Provider    : {llm.get('provider')}",
                f"Model       : {llm.get('model')}",
                f"Base URL    : {llm.get('base_url')}",
                f"Connected   : {llm.get('connected_count')}",
            ]
        )
        if llm.get("error"):
            lines.append(f"LLM Error   : {llm.get('error')}")
    lines.extend(
        [
            "",
            "Work",
            "----",
            f"Agents      : {agent_count}",
            f"Failed      : {failed}",
            f"Work Items  : {status.get('work_item_count')}",
        ]
    )
    teams = status.get("teams", {})
    if isinstance(teams, dict) and teams:
        top_teams = sorted(teams.items(), key=lambda item: (-int(item[1]), str(item[0])))[:5]
        lines.append("Top Teams   : " + ", ".join(f"{team}={count}" for team, count in top_teams))
    lines.extend(["", "Current Session Activity", "------------------------"])
    lines.extend(summarize_session_activity(status))
    if error:
        lines.extend(["", "Failure", "-------", error])
    lines.extend(
        [
            "",
            "Files",
            "-----",
            f"Status      : {STATUS_FILE.relative_to(ROOT)}",
            f"Dashboard   : {DASHBOARD_FILE.relative_to(ROOT)}",
            f"Cycle Brief : {CYCLE_BRIEF_FILE.relative_to(ROOT)}",
            f"Ops Review  : {OPERATING_REVIEW_FILE.relative_to(ROOT)}",
            f"CEO Review  : {CEO_SESSION_REVIEW_FILE.relative_to(ROOT)}",
            f"Team Plan   : {TEAM_ACTIVITY_FILE.relative_to(ROOT)}",
            f"Team Results: {TEAM_SESSION_RESULTS_FILE.relative_to(ROOT)}",
            f"Team Docs   : {TEAM_RESULT_DIR.relative_to(ROOT)}",
            f"Logs        : {LOG_DIR.relative_to(ROOT)}",
            f"Products    : {PRODUCT_DIR.relative_to(ROOT)}",
        ]
    )
    return "\n".join(lines)


def print_summary(status: dict[str, object]) -> None:
    print(render_console_report(status))


def runtime_process_state(status: dict[str, object]) -> dict[str, object]:
    generated_at = str(status.get("generated_at") or "")
    age: float | None = None
    if generated_at:
        try:
            generated = dt.datetime.fromisoformat(generated_at)
            age = (dt.datetime.now(generated.tzinfo) - generated).total_seconds()
        except ValueError:
            age = None

    pid = ""
    pid_path = RUNTIME_DIR / "company-agents.pid"
    if pid_path.exists():
        pid = read_text(pid_path).strip()

    stop_requested_now = STOP_FILE.exists()
    if stop_requested_now:
        state = "stop requested"
    elif pid and age is not None and age <= 120:
        state = "running"
    elif age is not None and age <= 120:
        state = "recently ran"
    elif pid:
        state = "unknown"
    else:
        state = "not running"
    return {
        "state": state,
        "pid": pid or None,
        "age_seconds": round(age, 1) if age is not None else None,
        "stop_requested": stop_requested_now,
    }


def read_runtime_file(path: Path, max_chars: int = 12000) -> str:
    text = read_text(path)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]"


def dashboard_agent_details(status: dict[str, object], max_chars: int = 8000) -> list[dict[str, object]]:
    agents = status.get("agents", [])
    if not isinstance(agents, list):
        return []
    details: list[dict[str, object]] = []
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            continue
        item = dict(agent)
        item["dashboard_index"] = index
        item["team"] = str(agent.get("parent") or "Company")
        product = str(agent.get("work_product") or "")
        log_path = str(agent.get("log") or "")
        item["report_content"] = read_runtime_file(ROOT / product, max_chars=max_chars) if product else ""
        item["log_content"] = read_runtime_file(ROOT / log_path, max_chars=max_chars // 2) if log_path else ""
        details.append(item)
    return details


def dashboard_payload() -> dict[str, object]:
    status = load_json(STATUS_FILE)
    agent_details = dashboard_agent_details(status)
    if isinstance(status, dict):
        status = dict(status)
        status["agents"] = agent_details
    files = {
        "dashboard": str(DASHBOARD_FILE.relative_to(ROOT)),
        "cycle_brief": str(CYCLE_BRIEF_FILE.relative_to(ROOT)),
        "operating_review": str(OPERATING_REVIEW_FILE.relative_to(ROOT)),
        "team_activity": str(TEAM_ACTIVITY_FILE.relative_to(ROOT)),
        "team_results": str(TEAM_SESSION_RESULTS_FILE.relative_to(ROOT)),
    }
    snippets = {
        "dashboard": read_runtime_file(DASHBOARD_FILE, max_chars=10000),
        "cycle_brief": read_runtime_file(CYCLE_BRIEF_FILE, max_chars=10000),
    }
    execution = status.get("execution", {}) if isinstance(status, dict) else {}
    return {
        "generated_at": now_iso(),
        "status": status,
        "execution": execution if isinstance(execution, dict) else {},
        "process": runtime_process_state(status),
        "files": files,
        "snippets": snippets,
        "message": DASHBOARD_LAST_MESSAGE,
    }


def render_dashboard_html(port: int = 8778) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Company Agents Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #18202f;
      --muted: #657086;
      --line: #d7deea;
      --accent: #1d6fd8;
      --good: #087f5b;
      --bad: #b42318;
      --warn: #b15c00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    h1 {{ font-size: 20px; margin: 0; letter-spacing: 0; }}
    main {{
      padding: 20px 24px 32px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 18px;
      align-items: start;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    h2 {{ margin: 0 0 12px; font-size: 15px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-height: 74px;
    }}
    .label {{ color: var(--muted); font-size: 12px; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; overflow-wrap: anywhere; }}
    .bar {{ height: 12px; background: #e9eef7; border-radius: 999px; overflow: hidden; border: 1px solid var(--line); }}
    .fill {{ height: 100%; width: 0%; background: var(--accent); transition: width .2s ease; }}
    .statusline {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
    .wide {{ grid-column: 1 / -1; }}
    .top-grid {{
      display: grid;
      grid-template-columns: minmax(280px, 1fr) minmax(360px, 1.2fr) minmax(260px, .9fr);
      gap: 18px;
      align-items: stretch;
    }}
    .top-grid section {{ height: 100%; }}
    .dashboard-grid {{
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(420px, 2.5fr) minmax(360px, 1.5fr);
      gap: 18px;
      align-items: start;
    }}
    .current-panel {{
      position: sticky;
      top: 92px;
    }}
    .team-panel {{
      min-width: 0;
    }}
    .detail-panel {{
      min-width: 0;
      position: sticky;
      top: 92px;
    }}
    .dashboard-markdown-panel {{
      grid-column: 2 / -1;
    }}
    .team-block {{
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 12px;
      overflow: hidden;
    }}
    .team-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      width: 100%;
      color: var(--ink);
      text-align: left;
      border-left: 0;
      border-right: 0;
      border-top: 0;
    }}
    .team-head:hover {{ background: #eef4ff; }}
    .team-toggle {{ color: var(--muted); font-weight: 700; margin-right: 6px; }}
    .agent-list {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
      gap: 8px;
      padding: 10px;
    }}
    .agent-list.collapsed {{ display: none; }}
    .agent-button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 10px;
      text-align: left;
      font-weight: 600;
      min-height: 74px;
    }}
    .agent-button:hover, .agent-button.selected {{ border-color: var(--accent); box-shadow: 0 0 0 2px rgba(29,111,216,.12); }}
    .agent-meta {{ display: block; color: var(--muted); font-weight: 500; font-size: 12px; margin-top: 5px; }}
    .detail-meta {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }}
    .detail-box {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      min-height: 58px;
      background: #fbfcfe;
    }}
    .detail-content {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }}
    .compact-list {{
      padding-left: 16px;
      max-height: 360px;
      overflow: auto;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 5px 0; }}
    textarea, input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }}
    textarea {{ min-height: 118px; resize: vertical; }}
    label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
    .field {{ margin-bottom: 12px; }}
    .row {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    button {{
      border: 1px solid #155bb0;
      background: var(--accent);
      color: white;
      border-radius: 6px;
      padding: 10px 12px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{ background: #fff; color: var(--ink); border-color: var(--line); }}
    button:disabled {{ opacity: .55; cursor: not-allowed; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
      line-height: 1.45;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 520px;
      overflow: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 8px 6px; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .ok {{ color: var(--good); }}
    .bad {{ color: var(--bad); }}
    .warn {{ color: var(--warn); }}
    @media (max-width: 920px) {{
      main {{ grid-template-columns: 1fr; padding: 16px; }}
      .grid, .row, .top-grid, .dashboard-grid, .detail-meta {{ grid-template-columns: 1fr; }}
      .current-panel, .detail-panel {{ position: static; }}
      .dashboard-markdown-panel {{ grid-column: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Company Agents Dashboard</h1>
      <div class="statusline">Polling <code>/api/status</code> on port {port}</div>
    </div>
    <button class="secondary" id="refresh">Refresh</button>
  </header>
  <main>
    <div class="top-grid">
      <section>
        <h2>Runtime</h2>
        <div class="metrics">
          <div class="metric"><div class="label">State</div><div class="value" id="state">-</div></div>
          <div class="metric"><div class="label">Session</div><div class="value" id="session">-</div></div>
          <div class="metric"><div class="label">Agents</div><div class="value" id="agents">-</div></div>
          <div class="metric"><div class="label">Failed</div><div class="value" id="failed">-</div></div>
        </div>
        <div style="margin-top:14px">
          <div class="bar"><div class="fill" id="fill"></div></div>
          <div class="statusline" id="progressText">No progress data.</div>
        </div>
        <div class="statusline" id="message"></div>
      </section>
      <section>
        <h2>Input</h2>
        <form id="taskForm">
          <div class="field">
            <label for="task">CEO task</label>
            <textarea id="task" name="task" required placeholder="이번 실행 사이클의 목표를 입력하세요."></textarea>
          </div>
          <div class="row">
            <div class="field">
              <label for="workers">Workers</label>
              <input id="workers" name="workers" type="number" min="1" value="16">
            </div>
            <div class="field">
              <label for="team">Team filter</label>
              <input id="team" name="team" placeholder="optional">
            </div>
            <div class="field">
              <label for="agent">Agent filter</label>
              <input id="agent" name="agent" placeholder="optional">
            </div>
          </div>
          <button type="submit" id="submitTask">Submit and run</button>
          <button type="button" class="secondary" id="stop">Request stop</button>
        </form>
        <div class="statusline" id="formStatus"></div>
      </section>
      <section>
        <h2>Recent Events</h2>
        <ul id="events"><li>No events.</li></ul>
      </section>
    </div>
    <div class="dashboard-grid">
      <section class="current-panel">
        <h2>Current Agents</h2>
        <ul class="compact-list" id="currentAgents"><li>No running agents.</li></ul>
      </section>
      <section class="team-panel">
        <h2>Agents By Team</h2>
        <div id="teamAgents">No agent data.</div>
      </section>
      <section class="detail-panel">
        <h2>Agent Detail</h2>
        <div class="detail-meta">
          <div class="detail-box"><div class="label">Name</div><div id="detailName">-</div></div>
          <div class="detail-box"><div class="label">Team</div><div id="detailTeam">-</div></div>
          <div class="detail-box"><div class="label">State</div><div id="detailState">-</div></div>
          <div class="detail-box"><div class="label">Tasks</div><div id="detailTasks">-</div></div>
        </div>
        <div class="detail-content">
          <div>
            <h2>Current Situation</h2>
            <pre id="detailSituation">Select an agent.</pre>
          </div>
          <div>
            <h2>Report</h2>
            <pre id="detailReport">Select an agent.</pre>
          </div>
        </div>
      </section>
      <section class="dashboard-markdown-panel">
        <h2>Dashboard Markdown</h2>
        <pre id="dashboardMd">No dashboard file.</pre>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let latestAgents = [];
    let selectedAgentIndex = null;
    const expandedTeams = new Set();
    function clsForState(value) {{
      const lower = String(value || '').toLowerCase();
      if (lower.includes('fail')) return 'bad';
      if (lower.includes('run')) return 'ok';
      if (lower.includes('stop') || lower.includes('unknown')) return 'warn';
      return '';
    }}
    function list(target, items, empty) {{
      target.innerHTML = '';
      if (!items || !items.length) {{
        const li = document.createElement('li');
        li.textContent = empty;
        target.appendChild(li);
        return;
      }}
      items.forEach((item) => {{
        const li = document.createElement('li');
        li.textContent = item;
        target.appendChild(li);
      }});
    }}
    function summarizeAgent(agent) {{
      const tasks = Array.isArray(agent.tasks) ? agent.tasks : [];
      const tools = Array.isArray(agent.recommended_tools) ? agent.recommended_tools : [];
      const lines = [
        `Lifecycle: ${{agent.lifecycle || agent.state || '-'}}`,
        `LLM: ${{agent.llm || '-'}}`,
        `Last heartbeat: ${{agent.last_heartbeat || '-'}}`,
        `Work product: ${{agent.work_product || '-'}}`,
        `Log: ${{agent.log || '-'}}`
      ];
      if (agent.error || agent.llm_error) lines.push(`Error: ${{agent.error || agent.llm_error}}`);
      lines.push('', 'Tasks:');
      if (tasks.length) {{
        tasks.slice(0, 10).forEach((task) => lines.push(`- ${{task.task || task.owner || 'Task'}} (status: ${{task.status || '-'}}, due: ${{task.due || '-'}})`));
      }} else {{
        lines.push('- No structured tasks recorded.');
      }}
      lines.push('', 'Recommended tools:');
      if (tools.length) {{
        tools.slice(0, 10).forEach((tool) => lines.push(`- ${{tool.tool || tool.name || String(tool)}}`));
      }} else {{
        lines.push('- None recorded.');
      }}
      return lines.join('\\n');
    }}
    function showAgentDetail(index) {{
      selectedAgentIndex = index;
      document.querySelectorAll('.agent-button').forEach((button) => button.classList.toggle('selected', Number(button.dataset.index) === index));
      const agent = latestAgents.find((item) => Number(item.dashboard_index) === index) || latestAgents[index];
      if (!agent) return;
      const teamName = agent.team || agent.parent || 'Company';
      expandedTeams.add(teamName);
      document.querySelectorAll('.team-block').forEach((block) => {{
        if (block.dataset.team !== teamName) return;
        const listEl = block.querySelector('.agent-list');
        const toggle = block.querySelector('.team-toggle');
        if (listEl) listEl.classList.remove('collapsed');
        if (toggle) toggle.textContent = 'v';
      }});
      $('detailName').textContent = agent.name || '-';
      $('detailTeam').textContent = agent.team || agent.parent || 'Company';
      $('detailState').textContent = agent.lifecycle || agent.state || '-';
      $('detailTasks').textContent = String(agent.task_count ?? 0);
      $('detailSituation').textContent = summarizeAgent(agent);
      $('detailReport').textContent = agent.report_content || agent.log_content || 'No report content available.';
    }}
    function renderTeamAgents(agents) {{
      latestAgents = agents;
      const container = $('teamAgents');
      container.innerHTML = '';
      if (!agents.length) {{
        container.textContent = 'No agent data.';
        selectedAgentIndex = null;
        $('detailSituation').textContent = 'Select an agent.';
        $('detailReport').textContent = 'Select an agent.';
        return;
      }}
      const byTeam = new Map();
      agents.forEach((agent, index) => {{
        const normalizedIndex = Number(agent.dashboard_index ?? index);
        agent.dashboard_index = normalizedIndex;
        const team = agent.team || agent.parent || 'Company';
        if (!byTeam.has(team)) byTeam.set(team, []);
        byTeam.get(team).push(agent);
      }});
      [...byTeam.keys()].sort().forEach((team) => {{
        const teamAgents = byTeam.get(team).sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));
        const expanded = expandedTeams.has(team);
        const block = document.createElement('div');
        block.className = 'team-block';
        block.dataset.team = team;
        const head = document.createElement('button');
        head.type = 'button';
        head.className = 'team-head';
        const title = document.createElement('span');
        const toggle = document.createElement('span');
        toggle.className = 'team-toggle';
        toggle.textContent = expanded ? 'v' : '>';
        title.appendChild(toggle);
        title.appendChild(document.createTextNode(team));
        const count = document.createElement('span');
        count.textContent = `${{teamAgents.length}} agent(s)`;
        head.append(title, count);
        const listEl = document.createElement('div');
        listEl.className = expanded ? 'agent-list' : 'agent-list collapsed';
        head.addEventListener('click', () => {{
          if (expandedTeams.has(team)) {{
            expandedTeams.delete(team);
            listEl.classList.add('collapsed');
            toggle.textContent = '>';
          }} else {{
            expandedTeams.add(team);
            listEl.classList.remove('collapsed');
            toggle.textContent = 'v';
          }}
        }});
        teamAgents.forEach((agent) => {{
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'agent-button';
          button.dataset.index = String(agent.dashboard_index);
          button.textContent = agent.name || 'unknown';
          const meta = document.createElement('span');
          meta.className = 'agent-meta';
          meta.textContent = `${{agent.lifecycle || agent.state || '-'}} · tasks ${{agent.task_count ?? 0}} · ${{agent.llm || '-'}}`;
          button.appendChild(meta);
          button.addEventListener('click', () => showAgentDetail(Number(button.dataset.index)));
          listEl.appendChild(button);
        }});
        block.append(head, listEl);
        container.appendChild(block);
      }});
      if (selectedAgentIndex !== null && agents.some((agent) => Number(agent.dashboard_index) === selectedAgentIndex)) {{
        showAgentDetail(selectedAgentIndex);
      }} else {{
        selectedAgentIndex = null;
        $('detailName').textContent = '-';
        $('detailTeam').textContent = '-';
        $('detailState').textContent = '-';
        $('detailTasks').textContent = '-';
        $('detailSituation').textContent = 'Select an agent.';
        $('detailReport').textContent = 'Select an agent.';
      }}
    }}
    async function loadStatus() {{
      const res = await fetch('/api/status', {{cache: 'no-store'}});
      const data = await res.json();
      const status = data.status || {{}};
      const execution = data.execution || {{}};
      const process = data.process || {{}};
      const state = status.error ? 'failed' : (execution.state || process.state || 'unknown');
      $('state').textContent = state;
      $('state').className = 'value ' + clsForState(state);
      $('session').textContent = status.session || '-';
      $('agents').textContent = status.agent_count ?? '-';
      $('failed').textContent = status.failed_agent_count ?? '-';
      const total = Number(execution.total_agents || status.agent_count || 0);
      const done = Number(execution.completed_agents || 0);
      const pct = total ? Number(execution.percent_complete || (done / total * 100)) : 0;
      $('fill').style.width = Math.max(0, Math.min(100, pct)) + '%';
      $('progressText').textContent = total ? `${{done}}/${{total}} complete · running ${{execution.running_agents || 0}} · queued ${{execution.queued_agents || 0}}` : 'No progress data.';
      $('message').textContent = data.message || '';
      list($('currentAgents'), execution.current_agents || [], 'No running agents.');
      list($('events'), execution.recent_events || [], 'No events.');
      const agents = Array.isArray(status.agents) ? status.agents : [];
      renderTeamAgents(agents);
      $('dashboardMd').textContent = (data.snippets && data.snippets.dashboard) || 'No dashboard file.';
    }}
    async function submitTask(event) {{
      event.preventDefault();
      $('submitTask').disabled = true;
      $('formStatus').textContent = 'Submitting...';
      const payload = {{
        task: $('task').value,
        workers: Number($('workers').value || 16),
        team: $('team').value,
        agent: $('agent').value
      }};
      try {{
        const res = await fetch('/api/task', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        $('formStatus').textContent = data.message || (res.ok ? 'Started.' : 'Failed.');
        await loadStatus();
      }} catch (error) {{
        $('formStatus').textContent = String(error);
      }} finally {{
        $('submitTask').disabled = false;
      }}
    }}
    async function requestStop() {{
      const res = await fetch('/api/stop', {{method: 'POST'}});
      const data = await res.json();
      $('formStatus').textContent = data.message || 'Stop requested.';
      await loadStatus();
    }}
    $('taskForm').addEventListener('submit', submitTask);
    $('stop').addEventListener('click', requestStop);
    $('refresh').addEventListener('click', loadStatus);
    loadStatus();
    setInterval(loadStatus, 2000);
  </script>
</body>
</html>
"""


def parse_dashboard_request_body(handler: http.server.BaseHTTPRequestHandler) -> dict[str, object]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    parsed = urllib.parse.parse_qs(raw)
    return {key: values[-1] for key, values in parsed.items() if values}


def start_dashboard_cycle(task: str, workers: int, agent_filter: str | None, team_filter: str | None) -> tuple[int, dict[str, object]]:
    global DASHBOARD_RUN_THREAD, DASHBOARD_LAST_MESSAGE
    task = task.strip()
    if not task:
        return 400, {"ok": False, "message": "Task is required."}
    with DASHBOARD_RUN_LOCK:
        if DASHBOARD_RUN_THREAD is not None and DASHBOARD_RUN_THREAD.is_alive():
            return 409, {"ok": False, "message": "A dashboard-triggered run is already active."}
        cycle_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        DASHBOARD_LAST_MESSAGE = f"Queued dashboard task for cycle {cycle_id}."

        def run_from_dashboard() -> None:
            global DASHBOARD_LAST_MESSAGE
            try:
                set_user_initial_task(task)
                DASHBOARD_LAST_MESSAGE = f"Running dashboard task for cycle {cycle_id}."
                run_cycle(
                    max_workers=max(1, workers),
                    cycle_id=cycle_id,
                    agent_filter=agent_filter or None,
                    team_filter=team_filter or None,
                )
                DASHBOARD_LAST_MESSAGE = f"Completed dashboard task for cycle {cycle_id}."
            except LLMConnectionError as error:
                DASHBOARD_LAST_MESSAGE = f"Run failed: {error}"
            except Exception as error:
                DASHBOARD_LAST_MESSAGE = f"Run failed: {type(error).__name__}: {error}"

        DASHBOARD_RUN_THREAD = threading.Thread(target=run_from_dashboard, name="dashboard-agent-run", daemon=True)
        DASHBOARD_RUN_THREAD.start()
    return 202, {"ok": True, "message": DASHBOARD_LAST_MESSAGE, "cycle_id": cycle_id}


class CompanyDashboardHandler(http.server.BaseHTTPRequestHandler):
    default_workers = 16

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[dashboard] {self.address_string()} - {format % args}\n")

    def send_text(self, status_code: int, content: str, content_type: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status_code: int, payload: dict[str, object]) -> None:
        self.send_text(status_code, json.dumps(payload, ensure_ascii=False), "application/json")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/dashboard"}:
            self.send_text(200, render_dashboard_html(port=getattr(self.server, "dashboard_port", 8778)), "text/html")
            return
        if parsed.path == "/api/status":
            self.send_json(200, dashboard_payload())
            return
        self.send_json(404, {"ok": False, "message": "Not found."})

    def do_POST(self) -> None:
        global DASHBOARD_LAST_MESSAGE
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/task":
            payload = parse_dashboard_request_body(self)
            workers = parse_int(str(payload.get("workers") or self.default_workers), self.default_workers, minimum=1)
            status_code, response = start_dashboard_cycle(
                task=str(payload.get("task") or ""),
                workers=workers,
                agent_filter=str(payload.get("agent") or "").strip() or None,
                team_filter=str(payload.get("team") or "").strip() or None,
            )
            self.send_json(status_code, response)
            return
        if parsed.path == "/api/stop":
            atomic_write_text(STOP_FILE, f"Stop requested from dashboard at {now_iso()}\n")
            DASHBOARD_LAST_MESSAGE = "Stop requested from dashboard."
            self.send_json(200, {"ok": True, "message": DASHBOARD_LAST_MESSAGE})
            return
        self.send_json(404, {"ok": False, "message": "Not found."})


class ThreadingDashboardServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_dashboard(port: int = 8778, host: str = "127.0.0.1", workers: int = 16) -> int:
    RUNTIME_DIR.mkdir(exist_ok=True)
    CompanyDashboardHandler.default_workers = workers
    server = ThreadingDashboardServer((host, port), CompanyDashboardHandler)
    server.dashboard_port = port
    print(f"Company agents dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0


def test_llm() -> int:
    config = build_llm_config()
    print(f"Provider: {config.provider}")
    print(f"Base URL: {config.base_url}")
    print(f"Model: {config.model}")
    content, error = call_llm(
        config,
        "You are a connection test. Answer in Korean with one short sentence.",
        "LLM 연결 테스트입니다. 한 문장으로 응답하세요.",
    )
    if content:
        print("LLM connected.")
        print(content)
        return 0
    print(f"LLM failed: {error}")
    return 1


def stop_requested() -> bool:
    return STOP_FILE.exists()


def start_input_reader() -> bool:
    global INPUT_QUEUE, INPUT_THREAD_STARTED
    if not sys.stdin.isatty():
        return False
    if INPUT_QUEUE is None:
        INPUT_QUEUE = queue.Queue()
    if INPUT_THREAD_STARTED:
        return True

    def read_stdin_lines() -> None:
        while True:
            try:
                line = sys.stdin.readline()
            except OSError:
                return
            if line == "":
                return
            assert INPUT_QUEUE is not None
            INPUT_QUEUE.put(line)

    thread = threading.Thread(target=read_stdin_lines, name="stdin-stop-reader", daemon=True)
    thread.start()
    INPUT_THREAD_STARTED = True
    return True


def handle_sleep_input(value: str) -> bool:
    value = value.strip().lower()
    if value in STOP_COMMANDS:
        atomic_write_text(STOP_FILE, f"Stop requested at {now_iso()}\n")
        return True
    if value:
        print(f"Ignored input during sleep: {value}. Type 'stop' to exit.")
    return False


def stop_input_requested() -> bool:
    if not start_input_reader() or INPUT_QUEUE is None:
        return False
    stopped = False
    while True:
        try:
            value = INPUT_QUEUE.get_nowait()
        except queue.Empty:
            break
        if handle_sleep_input(value):
            stopped = True
    return stopped


def wait_for_next_cycle(seconds: int) -> bool:
    print(f"Sleeping for {seconds} seconds. Type 'stop' and press Enter to exit.")
    for _ in range(max(0, seconds)):
        if stop_requested() or stop_input_requested():
            print("Stop requested. Exiting watch loop.")
            return False
        time.sleep(1)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run company agents in parallel.")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    parser.add_argument("--watch", action="store_true", help="Keep running cycles.")
    parser.add_argument("--list-agents", action="store_true", help="Print available agents and exit.")
    parser.add_argument("--list-tools", action="store_true", help="Print team tools and exit.")
    parser.add_argument("--materialize-tools", action="store_true", help="Generate per-team tool files from the registry.")
    parser.add_argument("--tools-health", action="store_true", help="Validate tool registry, templates, and metadata.")
    parser.add_argument("--show-tool-audit", action="store_true", help="Print the latest tool audit report.")
    parser.add_argument("--doctor", action="store_true", help="Run structural checks for agents, tasks, playbooks, and tools.")
    parser.add_argument("--test-llm", action="store_true", help="Test the configured LLM connection and exit.")
    parser.add_argument("--dashboard", action="store_true", help="Serve the local monitoring dashboard.")
    parser.add_argument("--dashboard-port", type=int, default=8778, help="Dashboard HTTP port.")
    parser.add_argument("--dashboard-host", default="127.0.0.1", help="Dashboard bind host.")
    parser.add_argument("--interval", type=int, default=60, help="Watch interval in seconds.")
    parser.add_argument("--workers", type=int, default=16, help="Maximum parallel workers.")
    parser.add_argument("--agent", help="Run only agents whose name or slug contains this value.")
    parser.add_argument("--team", help="Run only agents whose team contains this value.")
    parser.add_argument("--cycle-id", default=dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--task", help="Use this user input as the first CEO task for the cycle.")
    parser.add_argument("--task-file", help="Read the first CEO task from a text file.")
    parser.add_argument("--ask-task", action="store_true", help="Prompt for the first CEO task before running.")
    args = parser.parse_args()

    initial_task = resolve_initial_task(args)
    if initial_task:
        set_user_initial_task(initial_task)
        print("Updated CEO-TASK-DIRECTIVE.md from user input.")

    if args.list_agents:
        for agent in build_agents(agent_filter=args.agent, team_filter=args.team):
            print(f"{agent.name}\t{agent.kind}\t{agent.parent or 'Company'}")
        return 0

    if args.list_tools:
        print_tools(team_filter=args.team)
        return 0

    if args.materialize_tools:
        return materialize_tools(team_filter=args.team)

    if args.tools_health:
        return tools_health(team_filter=args.team)

    if args.show_tool_audit:
        return show_tool_audit()

    if args.doctor:
        return doctor(agent_filter=args.agent, team_filter=args.team)

    if args.test_llm:
        return test_llm()

    if args.dashboard:
        return serve_dashboard(port=args.dashboard_port, host=args.dashboard_host, workers=args.workers)

    if not args.once and not args.watch:
        args.once = True

    if args.once:
        try:
            status = run_cycle(
                max_workers=args.workers,
                cycle_id=args.cycle_id,
                agent_filter=args.agent,
                team_filter=args.team,
            )
        except LLMConnectionError as error:
            print(f"LLM connection failed: {error}")
            status = load_json(STATUS_FILE)
            if status:
                print(render_console_report(status))
            return 1
        print_summary(status)
        return 0

    if STOP_FILE.exists():
        STOP_FILE.unlink()

    while True:
        if stop_requested():
            print("Stop requested. Exiting watch loop.")
            return 0
        try:
            status = run_cycle(
                max_workers=args.workers,
                cycle_id=args.cycle_id,
                agent_filter=args.agent,
                team_filter=args.team,
            )
        except LLMConnectionError as error:
            print(f"LLM connection failed: {error}")
            status = load_json(STATUS_FILE)
            if status:
                print(render_console_report(status))
            return 1
        print_summary(status)
        if not wait_for_next_cycle(args.interval):
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
