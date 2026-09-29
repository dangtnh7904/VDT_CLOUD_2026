"""Candidate-only default comparison: Pacific C++ options against Quincy YAML.

This extracts plain set_default/set_daemon_default calls. Complex C++ expressions
need manual review; output is a reading queue, never an impact verdict.
"""

import ast
import re
import subprocess
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[3] / "ceph16.2.15" / "ceph"

def show(path):
    return subprocess.check_output(["git", "show", f"v16.2.15:{path}"], cwd=REPO, text=True)

def target(path):
    return subprocess.check_output(["git", "show", f"v17.2.7:{path}"], cwd=REPO, text=True)

old = show("src/common/options.cc")
old_options = {}
hits = list(re.finditer(r'Option\("([^\"]+)",\s*Option::TYPE_', old))
for i, hit in enumerate(hits):
    body = old[hit.start():hits[i+1].start() if i + 1 < len(hits) else len(old)]
    defaults = {}
    for field in ("default", "daemon_default"):
        found = re.search(rf'\.set_{field}\(([^\n]+?)\)\s*(?:\.|,|$)', body, re.M)
        if found:
            defaults[field] = found.group(1).strip()
    old_options[hit.group(1)] = defaults

new_options = {}
files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "v17.2.7", "src/common/options"], cwd=REPO, text=True).splitlines()
for path in files:
    if not path.endswith(".yaml.in"):
        continue
    # CMake substitutes @VAR@ before the project's YAML parser sees the file.
    raw = re.sub(r'@[A-Za-z0-9_]+@', 'CMAKE_VALUE', target(path))
    data = yaml.safe_load(raw)
    for option in data["options"]:
        new_options[option["name"]] = (path, option)

def canonical(value):
    if value in (None, "<absent>"):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    value = str(value).strip()
    if value in ("true", "false"):
        return value == "true"
    if value in ("", '""'):
        return ""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    multipliers = {"min": 60, "hr": 3600, "day": 86400,
                   "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    for unit, mul in multipliers.items():
        match = re.fullmatch(rf'(\d+)_{unit}', value)
        if match:
            return int(match.group(1)) * mul
    try:
        tree = ast.parse(value, mode="eval")
        def evaluate(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return node.value
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                return -evaluate(node.operand)
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.LShift)):
                a, b = evaluate(node.left), evaluate(node.right)
                return {ast.Add: lambda: a+b, ast.Sub: lambda: a-b,
                        ast.Mult: lambda: a*b, ast.Div: lambda: a/b,
                        ast.LShift: lambda: a<<b}[type(node.op)]()
            raise ValueError
        return evaluate(tree.body)
    except (SyntaxError, ValueError, TypeError):
        return value

print(f"# old options={len(old_options)}, target YAML options={len(new_options)}")
print(f"# removed={sorted(set(old_options)-set(new_options))}")
print(f"# added={sorted(set(new_options)-set(old_options))}")
print("name\tfield\tbase_raw\ttarget_raw\ttarget_yaml")
for name in sorted(set(old_options)&set(new_options)):
    old_defaults = old_options[name]
    path, option = new_options[name]
    for field in ("default", "daemon_default"):
        before = old_defaults.get(field, "<absent>")
        after = str(option.get(field, "<absent>"))
        if canonical(before) != canonical(option.get(field, "<absent>")):
            print(f"{name}\t{field}\t{before}\t{after}\t{path}")
