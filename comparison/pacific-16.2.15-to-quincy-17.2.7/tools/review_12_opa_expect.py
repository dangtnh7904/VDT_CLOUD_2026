"""Record the conditional OPA Expect header endpoint difference."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
source = "src/rgw/rgw_opa.cc"
diff = subprocess.check_output(
    ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
    text=True,
    encoding="utf-8",
)
removed, added = [], []
for line in diff.splitlines():
    if line.startswith("---") or line.startswith("+++"):
        continue
    if line.startswith("-") and line[1:].strip():
        removed.append(line[1:].strip())
    if line.startswith("+") and line[1:].strip():
        added.append(line[1:].strip())
assert not removed
assert added == ["using namespace std;", 'req.append_header("Expect", "100-continue");']

for tag in ("v16.2.15", "v17.2.7"):
    http = subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":src/rgw/rgw_http_client.cc"],
        text=True,
        encoding="utf-8",
    )
    assert 'if (method == "POST") {' in http and 'curl_slist_append(h, "Expect:")' in http
    opa = subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":src/rgw/rgw_opa.cc"],
        text=True,
        encoding="utf-8",
    )
    assert "req.set_send_length(ss.str().length());" in opa

target = subprocess.check_output(
    ["git", "-C", str(repo), "show", "v17.2.7:src/rgw/rgw_process.cc"],
    text=True,
    encoding="utf-8",
)
assert "if (s->cct->_conf->rgw_use_opa_authz)" in target
history = subprocess.check_output(
    ["git", "-C", str(repo), "log", "--format=%h", "v16.2.15..v17.2.7", "--", source],
    text=True,
    encoding="utf-8",
)
assert "871d18040b7" in history

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
row = by_path[source]
assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
row.update(
    upgrade_impact="affect",
    finding_id="RGW-012",
    impact_reason="RGW-012: With OPA authorization enabled, Quincy adds an explicit Expect: 100-continue header to each OPA POST; the shared HTTP client also appends empty Expect:, so target libcurl/proxy wire behavior and authorization latency require validation.",
)
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print("Recorded RGW-012 on the OPA Expect header row")
