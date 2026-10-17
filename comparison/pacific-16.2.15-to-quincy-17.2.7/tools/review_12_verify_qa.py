"""Classify reviewed RGW verify suite QA coverage changes."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
paths = {
    "qa/suites/rgw/verify/proto/https.yaml",
    "qa/suites/rgw/verify/tasks/cls.yaml",
    "qa/suites/rgw/verify/validater/valgrind.yaml",
    "qa/workunits/cls/test_cls_rgw_gc.sh",
    "qa/workunits/cls/test_cls_rgw_stats.sh",
}


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{source}"],
        text=True, encoding="utf-8")


cls_old = show("v16.2.15", "qa/suites/rgw/verify/tasks/cls.yaml")
cls_new = show("v17.2.7", "qa/suites/rgw/verify/tasks/cls.yaml")
for name in ("gc", "stats"):
    workunit = f"cls/test_cls_rgw_{name}.sh"
    executable = f"ceph_test_cls_rgw_{name}"
    assert workunit not in cls_old and workunit in cls_new
    script = show("v17.2.7", f"qa/workunits/{workunit}")
    assert script == f"#!/bin/sh -e\n\n{executable}\n\nexit 0\n"

https_old = show("v16.2.15", "qa/suites/rgw/verify/proto/https.yaml")
https_new = show("v17.2.7", "qa/suites/rgw/verify/proto/https.yaml")
assert "install: [client.0, client.1]" in https_old
assert "rgw.client.1:" in https_old and "ssl certificate: rgw.client.1" in https_old
assert "install: [client.0]" in https_new
assert "rgw.client.1:" not in https_new and "ssl certificate: rgw.client.1" not in https_new
assert "client.0:" in show("v17.2.7", "qa/suites/rgw/verify/0-install.yaml")

valgrind_old = show("v16.2.15", "qa/suites/rgw/verify/validater/valgrind.yaml")
valgrind_new = show("v17.2.7", "qa/suites/rgw/verify/validater/valgrind.yaml")
assert "  rgw:\n    client.0:\n      valgrind:" not in valgrind_old
assert "  rgw:\n    client.0:\n      valgrind: [--tool=memcheck, --max-threads=1024]" in valgrind_new
runner = show("v17.2.7", "qa/tasks/rgw.py")
assert "if client_config.get('valgrind'):" in runner
assert "cmd_prefix = get_valgrind_args(" in runner

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in paths:
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if "cls" in source:
        reason = "RGW-019: Selected rgw/verify CLS variant now invokes ceph_test_cls_rgw_gc and ceph_test_cls_rgw_stats workunits, changing validation coverage and pass/fail."
    elif "https" in source:
        reason = "RGW-019: HTTPS QA variant drops certificate setup for undeclared client.1 and retains client.0, changing whether that validation job can initialize."
    else:
        reason = "RGW-019: Selected Valgrind QA variant now wraps RGW client.0 with memcheck, changing execution and validation signal."
    row.update(upgrade_impact="affect", finding_id="RGW-019", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(paths)} RGW verify QA rows affect")
