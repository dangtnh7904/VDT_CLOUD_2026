"""List option-name migration candidates by target service YAML file."""

import re
import subprocess
from pathlib import Path
import yaml

repo = Path(__file__).resolve().parents[3] / "ceph16.2.15" / "ceph"
old = subprocess.check_output(["git", "show", "v16.2.15:src/common/options.cc"], cwd=repo, text=True)
old_names = set(re.findall(r'Option\("([^\"]+)",\s*Option::TYPE_', old))
paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "v17.2.7", "src/common/options"], cwd=repo, text=True).splitlines()
for path in paths:
    if not path.endswith(".yaml.in"):
        continue
    raw = subprocess.check_output(["git", "show", f"v17.2.7:{path}"], cwd=repo, text=True)
    raw = re.sub(r'@[A-Za-z0-9_]+@', 'CMAKE_VALUE', raw)
    opts = yaml.safe_load(raw)["options"]
    added = [o["name"] for o in opts if o["name"] not in old_names]
    print(path, "options", len(opts), "new", len(added))
    print("  " + ", ".join(added))
