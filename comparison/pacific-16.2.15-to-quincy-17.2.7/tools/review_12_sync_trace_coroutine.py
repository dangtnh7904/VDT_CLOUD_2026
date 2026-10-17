"""Classify exact RGW sync-trace and coroutine implementation plumbing."""

import csv
import re
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
paths = {
    "src/rgw/rgw_sync_trace.cc",
    "src/rgw/rgw_sync_trace.h",
    "src/rgw/rgw_coroutine.cc",
}


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{source}"],
        text=True, encoding="utf-8")


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True, encoding="utf-8")
    old, new = [], []
    for line in diff.splitlines():
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("-") and line[1:].strip():
            old.append(line[1:].strip())
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:].strip())
    return old, new


old_cc, new_cc = changed_lines("src/rgw/rgw_sync_trace.cc")
assert old_cc == ["int ret = store->update_service_map(std::move(status));"]
assert new_cc == ["using namespace std;", "int ret = store->update_service_map(dpp, std::move(status));", "const bufferlist&,"]
old_h, new_h = changed_lines("src/rgw/rgw_sync_trace.h")
assert len(new_h) == len(old_h) + 1
assert "const bufferlist&," in new_h
new_h.remove("const bufferlist&,")
for before, after in zip(old_h, new_h):
    assert before != after
    assert re.sub(r"(?<![:\w])string\b", "std::string", before) == after, (before, after)
old_rados = show("v16.2.15", "src/rgw/rgw_rados.cc")
new_rados = show("v17.2.7", "src/rgw/rgw_rados.cc")
assert "rados.service_daemon_update_status(move(status));" in old_rados
assert "rados.service_daemon_update_status(move(status));" in new_rados

old_cr, new_cr = changed_lines("src/rgw/rgw_coroutine.cc")
assert not old_cr
assert new_cr.count("using namespace std;") == 1
assert new_cr.count("const bufferlist&,") == 1
old_header = show("v16.2.15", "src/rgw/rgw_coroutine.h")
new_source = show("v17.2.7", "src/rgw/rgw_coroutine.cc")
old_dtor = re.search(r"virtual ~RGWCoroutinesManager\(\)\s*\{(.*?)\n  \}", old_header, re.S)
new_dtor = re.search(r"RGWCoroutinesManager::~RGWCoroutinesManager\(\)\s*\{(.*?)\n\}", new_source, re.S)
assert old_dtor and new_dtor
assert re.sub(r"\s+", "", old_dtor.group(1)) == re.sub(r"\s+", "", new_dtor.group(1))
assert "virtual ~RGWCoroutinesManager();" in show("v17.2.7", "src/rgw/rgw_coroutine.h")

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in paths:
    row = by_path[source]
    assert row["status"] == "M" and not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row.update(
        upgrade_impact="trivial", finding_id="",
        impact_reason="RGW-PLUMB-01: Exact endpoint diff only qualifies standard types, passes an unused admin argument or logging context, or moves an identical coroutine destructor body out of the header; no sync status payload, coroutine lifecycle sequence, or upgrade acceptance behavior changes in this file.")
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print("Classified three exact sync-trace/coroutine plumbing rows trivial")
