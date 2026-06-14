#!/usr/bin/env python3
"""Generate RTL module hierarchy and signal-level datapath diagrams from a filelist."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple


MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)")
ENDMODULE_RE = re.compile(r"\bendmodule\b")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
COMMENT_LINE_RE = re.compile(r"//.*?$", re.M)
COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.S)
PORT_BLOCK_RE = re.compile(
    r"\bmodule\s+[A-Za-z_][A-Za-z0-9_$]*\s*(?:#\s*\((?P<params>.*?)\)\s*)?\((?P<ports>.*?)\)\s*;",
    re.S,
)
DECL_RE = re.compile(
    r"\b(?P<direction>input|output|inout)\b\s*(?P<body>.*?);",
    re.S,
)
NET_DECL_RE = re.compile(
    r"\b(?:wire|reg|logic)\b\s*(?P<body>.*?);",
    re.S,
)

DIRECTION_WORDS = {"input", "output", "inout"}
DECL_WORDS = {
    "wire",
    "reg",
    "logic",
    "signed",
    "unsigned",
    "tri",
    "bit",
}
CONTROL_KEYWORDS = {
    "if",
    "for",
    "while",
    "case",
    "assign",
    "always",
    "always_ff",
    "always_comb",
    "module",
    "function",
    "task",
    "begin",
    "end",
    "generate",
}
EXPRESSION_KEYWORDS = CONTROL_KEYWORDS | {
    "default",
    "localparam",
    "parameter",
    "posedge",
    "negedge",
}
DATAPATH_KEYWORDS = {
    "data",
    "datapath",
    "alu",
    "mac",
    "mul",
    "adder",
    "sum",
    "acc",
    "regfile",
    "fifo",
    "pipe",
    "execute",
    "decode",
    "memory",
    "mem",
    "vector",
    "lane",
    "payload",
    "result",
    "operand",
    "src",
    "dst",
}
CONTROL_SIGNAL_EXACT = {"clk", "clock", "rst", "reset", "en", "ce"}
CONTROL_SIGNAL_KEYWORDS = {
    "rst_",
    "reset",
    "valid",
    "ready",
    "enable",
    "stall",
    "flush",
    "sel",
    "ctrl",
    "control",
}
FILE_SUFFIXES = {".v", ".sv", ".vh", ".svh"}


@dataclass(frozen=True)
class Port:
    name: str
    direction: str = "unknown"
    width: str = ""


@dataclass(frozen=True)
class Instance:
    module: str
    name: str
    connections: Dict[str, Tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class DataEdge:
    source: str
    target: str
    net: str
    parent: str


@dataclass
class Module:
    name: str
    file: Path
    body: str
    instances: List[Instance] = field(default_factory=list)
    ports: Dict[str, Port] = field(default_factory=dict)
    nets: Set[str] = field(default_factory=set)


@dataclass
class Design:
    modules: Dict[str, Module]
    top: str
    hierarchy_edges: List[Tuple[str, str, str]] = field(default_factory=list)
    data_edges: List[DataEdge] = field(default_factory=list)


def strip_comments(text: str) -> str:
    text = COMMENT_BLOCK_RE.sub("", text)
    return COMMENT_LINE_RE.sub("", text)


def remove_inline_filelist_comment(line: str) -> str:
    for marker in ("//", "#"):
        index = line.find(marker)
        if index != -1:
            line = line[:index]
    return line.strip()


def expand_path(token: str, base: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(token))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def add_if_rtl_file(files: List[Path], candidate: Path) -> None:
    if candidate.suffix.lower() in FILE_SUFFIXES and candidate.exists():
        files.append(candidate)


def parse_filelist(path: Path, seen: Set[Path] | None = None) -> List[Path]:
    """Parse a common simulator filelist, including nested -f entries."""

    filelist = path.resolve()
    if seen is None:
        seen = set()
    if filelist in seen:
        return []
    seen.add(filelist)

    files: List[Path] = []
    base = filelist.parent

    for raw in filelist.read_text(encoding="utf-8").splitlines():
        line = remove_inline_filelist_comment(raw)
        if not line:
            continue
        tokens = shlex.split(line)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in {"-f", "-F"} and index + 1 < len(tokens):
                files.extend(parse_filelist(expand_path(tokens[index + 1], base), seen))
                index += 2
                continue
            if token.startswith("-f") and len(token) > 2:
                files.extend(parse_filelist(expand_path(token[2:], base), seen))
                index += 1
                continue
            if token in {"-v", "-include"} and index + 1 < len(tokens):
                add_if_rtl_file(files, expand_path(tokens[index + 1], base))
                index += 2
                continue
            if token.startswith("+incdir+") or token.startswith("+define+"):
                index += 1
                continue
            if token == "-y" and index + 1 < len(tokens):
                libdir = expand_path(tokens[index + 1], base)
                if libdir.is_dir():
                    for suffix in FILE_SUFFIXES:
                        files.extend(sorted(libdir.glob(f"*{suffix}")))
                index += 2
                continue

            add_if_rtl_file(files, expand_path(token, base))
            index += 1

    return sorted(set(files))


def find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def split_top_level(text: str, delimiter: str = ",") -> List[str]:
    parts: List[str] = []
    start = 0
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    for index, char in enumerate(text):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
        elif char == delimiter and paren_depth == bracket_depth == brace_depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def signal_names(expression: str) -> List[str]:
    expression = re.sub(r"\b\d*\s*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+\b", " ", expression)
    expression = re.sub(r"\b\d+\b", " ", expression)
    names: List[str] = []
    for name in IDENT_RE.findall(expression):
        if name not in DECL_WORDS and name not in DIRECTION_WORDS and name not in EXPRESSION_KEYWORDS:
            names.append(name)
    return list(dict.fromkeys(names))


def declaration_names(body: str) -> List[str]:
    body = re.sub(r"\[[^\]]+\]", " ", body)
    body = re.sub(r"\b(?:wire|reg|logic|signed|unsigned|tri|bit)\b", " ", body)
    names: List[str] = []
    for item in split_top_level(body):
        item = item.split("=", 1)[0]
        found = IDENT_RE.findall(item)
        if found:
            names.append(found[-1])
    return names


def parse_port_item(item: str, previous_direction: str = "unknown") -> Port | None:
    item = item.split("=", 1)[0].strip()
    if not item:
        return None
    direction_match = re.search(r"\b(input|output|inout)\b", item)
    direction = direction_match.group(1) if direction_match else previous_direction
    width_match = re.search(r"\[[^\]]+\]", item)
    width = width_match.group(0) if width_match else ""
    cleaned = re.sub(r"\[[^\]]+\]", " ", item)
    cleaned = re.sub(r"\b(?:input|output|inout|wire|reg|logic|signed|unsigned|tri|bit)\b", " ", cleaned)
    found = IDENT_RE.findall(cleaned)
    if not found:
        return None
    return Port(name=found[-1], direction=direction, width=width)


def parse_ports(block: str) -> Dict[str, Port]:
    ports: Dict[str, Port] = {}
    header = PORT_BLOCK_RE.search(block)
    previous_direction = "unknown"
    if header:
        for item in split_top_level(header.group("ports")):
            port = parse_port_item(item, previous_direction)
            if port:
                ports[port.name] = port
                if port.direction != "unknown":
                    previous_direction = port.direction

    for decl in DECL_RE.finditer(block):
        direction = decl.group("direction")
        body = decl.group("body")
        width_match = re.search(r"\[[^\]]+\]", body)
        width = width_match.group(0) if width_match else ""
        for name in declaration_names(body):
            ports[name] = Port(name=name, direction=direction, width=width)

    return ports


def parse_nets(block: str, ports: Dict[str, Port]) -> Set[str]:
    nets = set(ports)
    for decl in NET_DECL_RE.finditer(block):
        nets.update(declaration_names(decl.group("body")))
    return nets


def extract_module_blocks(verilog: str, source: Path) -> Dict[str, Module]:
    modules: Dict[str, Module] = {}
    cleaned = strip_comments(verilog)
    starts = [m for m in MODULE_RE.finditer(cleaned)]
    ends = [m for m in ENDMODULE_RE.finditer(cleaned)]
    end_idx = 0

    for start in starts:
        while end_idx < len(ends) and ends[end_idx].start() < start.start():
            end_idx += 1
        if end_idx >= len(ends):
            break

        end = ends[end_idx]
        end_idx += 1
        block = cleaned[start.start() : end.end()]
        name = start.group(1)
        ports = parse_ports(block)
        modules[name] = Module(
            name=name,
            file=source,
            body=block,
            ports=ports,
            nets=parse_nets(block, ports),
        )

    return modules


def parse_ordered_connections(argument_text: str, child: Module) -> Dict[str, Tuple[str, ...]]:
    connections: Dict[str, Tuple[str, ...]] = {}
    ordered_ports = list(child.ports)
    for index, expression in enumerate(split_top_level(argument_text)):
        if index >= len(ordered_ports):
            break
        names = signal_names(expression)
        if names:
            connections[ordered_ports[index]] = tuple(names)
    return connections


def parse_named_connections(argument_text: str) -> Dict[str, Tuple[str, ...]]:
    connections: Dict[str, Tuple[str, ...]] = {}
    for item in split_top_level(argument_text):
        match = re.match(r"\.([A-Za-z_][A-Za-z0-9_$]*)\s*\((.*)\)\s*$", item, re.S)
        if not match:
            continue
        port_name = match.group(1)
        expression = match.group(2)
        names = signal_names(expression)
        if names:
            connections[port_name] = tuple(names)
    return connections


def parse_instance_entry(entry: str, child: Module) -> Instance | None:
    match = IDENT_RE.match(entry.strip())
    if not match:
        return None

    text = entry.strip()
    inst_name = match.group(0)
    cursor = match.end()
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    while cursor < len(text) and text[cursor] == "[":
        close_bracket = text.find("]", cursor)
        if close_bracket == -1:
            return None
        cursor = close_bracket + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
    if cursor >= len(text) or text[cursor] != "(":
        return None

    close_paren = find_matching_paren(text, cursor)
    if close_paren == -1:
        return None
    argument_text = text[cursor + 1 : close_paren]
    if "." in argument_text:
        connections = parse_named_connections(argument_text)
    else:
        connections = parse_ordered_connections(argument_text, child)
    return Instance(module=child.name, name=inst_name, connections=connections)


def parse_instances_for_module(module: Module, modules: Dict[str, Module]) -> List[Instance]:
    instances: List[Instance] = []
    known = set(modules)
    tokens = list(IDENT_RE.finditer(module.body))
    index = 0
    while index < len(tokens):
        module_name = tokens[index].group(0)
        if module_name not in known or module_name == module.name or module_name in CONTROL_KEYWORDS:
            index += 1
            continue

        cursor = tokens[index].end()
        while cursor < len(module.body) and module.body[cursor].isspace():
            cursor += 1
        if module.body.startswith("#", cursor):
            open_paren = module.body.find("(", cursor)
            if open_paren == -1:
                index += 1
                continue
            close_paren = find_matching_paren(module.body, open_paren)
            if close_paren == -1:
                index += 1
                continue
            cursor = close_paren + 1
            while cursor < len(module.body) and module.body[cursor].isspace():
                cursor += 1

        inst_match = IDENT_RE.match(module.body, cursor)
        if not inst_match:
            index += 1
            continue
        inst_name = inst_match.group(0)
        cursor = inst_match.end()
        while cursor < len(module.body) and module.body[cursor].isspace():
            cursor += 1
        if cursor >= len(module.body) or module.body[cursor] != "(":
            index += 1
            continue
        close_paren = find_matching_paren(module.body, cursor)
        if close_paren == -1:
            index += 1
            continue
        semicolon = module.body.find(";", close_paren)
        if semicolon == -1:
            index += 1
            continue

        instance_text = module.body[inst_match.start() : semicolon]
        for entry in split_top_level(instance_text):
            instance = parse_instance_entry(entry, modules[module_name])
            if instance:
                instances.append(instance)

        while index < len(tokens) and tokens[index].start() < semicolon:
            index += 1

    return instances


def infer_top(modules: Dict[str, Module]) -> str:
    all_mods = set(modules)
    children = {inst.module for mod in modules.values() for inst in mod.instances if inst.module in all_mods}
    tops = sorted(all_mods - children)
    if not tops:
        return sorted(all_mods)[0]
    return tops[0]


def is_datapath_name(text: str) -> bool:
    low = text.lower()
    return any(keyword in low for keyword in DATAPATH_KEYWORDS)


def is_control_signal(text: str) -> bool:
    low = text.lower()
    return low in CONTROL_SIGNAL_EXACT or any(keyword in low for keyword in CONTROL_SIGNAL_KEYWORDS)


def is_datapath_net(net: str) -> bool:
    return not is_control_signal(net) and (is_datapath_name(net) or not re.fullmatch(r"[01xXzZ]+", net))


def build_hierarchy_edges(modules: Dict[str, Module]) -> List[Tuple[str, str, str]]:
    edges: List[Tuple[str, str, str]] = []
    known = set(modules)
    for parent_name, module in sorted(modules.items()):
        for inst in module.instances:
            if inst.module in known:
                edges.append((parent_name, inst.module, inst.name))
    return edges


def build_data_edges(modules: Dict[str, Module]) -> List[DataEdge]:
    edges: List[DataEdge] = []
    known = set(modules)
    for parent_name, parent in modules.items():
        endpoints_by_net: Dict[str, Dict[str, List[str]]] = {}
        for inst in parent.instances:
            child = modules.get(inst.module)
            if child is None:
                continue
            for port_name, nets in inst.connections.items():
                port = child.ports.get(port_name, Port(port_name))
                endpoint = f"{inst.name}:{inst.module}.{port_name}"
                for net in nets:
                    if not net or not is_datapath_net(net):
                        continue
                    bucket = endpoints_by_net.setdefault(net, {"drivers": [], "loads": [], "unknown": []})
                    if port.direction == "output":
                        bucket["drivers"].append(endpoint)
                    elif port.direction == "input":
                        bucket["loads"].append(endpoint)
                    else:
                        bucket["unknown"].append(endpoint)

        for net, endpoints in endpoints_by_net.items():
            drivers = endpoints["drivers"] or endpoints["unknown"]
            loads = endpoints["loads"]
            for driver in drivers:
                for load in loads:
                    if driver != load:
                        edges.append(DataEdge(source=driver, target=load, net=net, parent=parent_name))
            if not loads and len(drivers) > 1:
                for driver, load in zip(drivers, drivers[1:]):
                    edges.append(DataEdge(source=driver, target=load, net=net, parent=parent_name))

    return edges


def build_design(filelist: Path, explicit_top: str | None) -> Design:
    files = parse_filelist(filelist)
    if not files:
        raise ValueError(f"No Verilog/SystemVerilog files found in filelist: {filelist}")

    modules: Dict[str, Module] = {}
    for rtl_file in files:
        modules.update(extract_module_blocks(rtl_file.read_text(encoding="utf-8", errors="ignore"), rtl_file))

    if not modules:
        raise ValueError("No module declarations found.")

    for module in modules.values():
        module.instances = parse_instances_for_module(module, modules)

    top = explicit_top or infer_top(modules)
    if top not in modules:
        raise ValueError(f"Top module '{top}' not found in parsed modules.")

    return Design(
        modules=modules,
        top=top,
        hierarchy_edges=build_hierarchy_edges(modules),
        data_edges=build_data_edges(modules),
    )


def dot_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def emit_hierarchy_dot(design: Design) -> str:
    lines = [
        "digraph RTLHierarchy {",
        '  rankdir="LR";',
        '  graph [fontname="Helvetica", labelloc="t", label="RTL module hierarchy (orange = datapath candidate)"];',
        '  node [shape=box, style="rounded,filled", fillcolor="#ECEFF1", color="#607D8B", fontname="Helvetica"];',
        '  edge [color="#546E7A", fontname="Helvetica", fontsize=10];',
    ]

    for name, mod in sorted(design.modules.items()):
        if name == design.top:
            fill = "#BBDEFB"
            border = "#1565C0"
            penwidth = "2"
        elif is_datapath_name(name) or any(is_datapath_name(port_name) for port_name in mod.ports):
            fill = "#FFE0B2"
            border = "#EF6C00"
            penwidth = "2"
        else:
            fill = "#ECEFF1"
            border = "#607D8B"
            penwidth = "1"

        label = f"{name}\\n({mod.file.name})"
        lines.append(
            f'  "{dot_quote(name)}" [label="{dot_quote(label)}", fillcolor="{fill}", color="{border}", penwidth={penwidth}];'
        )

    for parent, child, inst_name in design.hierarchy_edges:
        edge_color = "#D84315" if any(is_datapath_name(item) for item in (parent, child, inst_name)) else "#546E7A"
        penwidth = "2" if edge_color == "#D84315" else "1"
        lines.append(
            f'  "{dot_quote(parent)}" -> "{dot_quote(child)}" [label="{dot_quote(inst_name)}", color="{edge_color}", penwidth={penwidth}];'
        )

    lines.append("}")
    return "\n".join(lines) + "\n"


def emit_datapath_dot(design: Design) -> str:
    lines = [
        "digraph RTLDataPath {",
        '  rankdir="LR";',
        '  graph [fontname="Helvetica", labelloc="t", label="RTL inferred datapath by shared nets"];',
        '  node [shape=box, style="rounded,filled", fillcolor="#FFF3E0", color="#EF6C00", fontname="Helvetica"];',
        '  edge [color="#D84315", penwidth=2, fontname="Helvetica", fontsize=10];',
    ]

    nodes: Set[str] = set()
    for edge in design.data_edges:
        nodes.add(edge.source)
        nodes.add(edge.target)

    if not nodes:
        lines.append('  "no_datapath_edges" [label="No signal-level datapath edges inferred", fillcolor="#FFECB3", color="#FFA000"];')
    else:
        for node in sorted(nodes):
            label = node.replace(":", "\\n")
            lines.append(f'  "{dot_quote(node)}" [label="{dot_quote(label)}"];')
        for edge in design.data_edges:
            label = f"{edge.net} @ {edge.parent}"
            lines.append(
                f'  "{dot_quote(edge.source)}" -> "{dot_quote(edge.target)}" [label="{dot_quote(label)}"];'
            )

    lines.append("}")
    return "\n".join(lines) + "\n"


def write_dot_outputs(design: Design, out_prefix: Path) -> Tuple[Path, Path]:
    hierarchy_dot = out_prefix.with_name(f"{out_prefix.name}_hierarchy.dot")
    datapath_dot = out_prefix.with_name(f"{out_prefix.name}_datapath.dot")
    hierarchy_dot.write_text(emit_hierarchy_dot(design), encoding="utf-8")
    datapath_dot.write_text(emit_datapath_dot(design), encoding="utf-8")
    return hierarchy_dot, datapath_dot


def maybe_render_png(dot_file: Path, png_file: Path) -> bool:
    dot_bin = shutil.which("dot")
    if not dot_bin:
        return False
    subprocess.run([dot_bin, "-Tpng", str(dot_file), "-o", str(png_file)], check=True)
    return True


def render_outputs(dot_files: Sequence[Path], out_prefix: Path, legacy_png: Path | None = None) -> List[Path]:
    rendered: List[Path] = []
    for index, dot_file in enumerate(dot_files):
        suffix = dot_file.stem.replace(out_prefix.name, "", 1).lstrip("_")
        if legacy_png and index == 0:
            png_file = legacy_png
        elif legacy_png:
            png_file = legacy_png.with_name(f"{legacy_png.stem}_{suffix}{legacy_png.suffix or '.png'}")
        else:
            png_file = out_prefix.with_name(f"{out_prefix.name}_{suffix}.png")
        if maybe_render_png(dot_file, png_file):
            rendered.append(png_file)
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read an RTL filelist and generate module hierarchy plus datapath-highlight diagrams"
    )
    parser.add_argument("filelist", type=Path, help="Path to rte/filelist.f style file list")
    parser.add_argument("--top", type=str, default=None, help="Top module name (optional)")
    parser.add_argument(
        "--out-prefix",
        type=Path,
        default=Path("rtl_datapath"),
        help="Output prefix. Creates <prefix>_hierarchy.dot and <prefix>_datapath.dot",
    )
    parser.add_argument("--out", type=Path, default=None, help="Backward-compatible alias for --out-prefix")
    parser.add_argument("--png", type=Path, default=None, help="Backward-compatible PNG path for the hierarchy image")
    parser.add_argument("--no-png", action="store_true", help="Skip PNG rendering even when Graphviz dot is available")
    args = parser.parse_args()

    out_prefix = args.out_prefix
    if args.out is not None:
        out_prefix = args.out.with_suffix("") if args.out.suffix == ".dot" else args.out

    design = build_design(args.filelist, args.top)
    dot_files = write_dot_outputs(design, out_prefix)

    print(f"[OK] hierarchy DOT generated: {dot_files[0]}")
    print(f"[OK] datapath DOT generated: {dot_files[1]}")
    print(f"[INFO] top module: {design.top}")
    print(f"[INFO] module count: {len(design.modules)}")
    print(f"[INFO] hierarchy edge count: {len(design.hierarchy_edges)}")
    print(f"[INFO] datapath edge count: {len(design.data_edges)}")

    if args.no_png:
        return

    try:
        rendered = render_outputs(dot_files, out_prefix, args.png)
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] dot rendering failed: {exc}")
        rendered = []

    if rendered:
        for png_file in rendered:
            print(f"[OK] PNG generated: {png_file}")
    else:
        print("[WARN] graphviz 'dot' not available (or rendering failed). DOT files are ready.")


if __name__ == "__main__":
    main()
