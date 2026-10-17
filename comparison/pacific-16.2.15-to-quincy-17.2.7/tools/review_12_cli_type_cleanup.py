"""Screen exact RGW CLI API, declaration, and empty string-view cleanup diffs."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
cli = {"src/rgw/rgw_es_main.cc", "src/rgw/rgw_token.cc"}
trim = {
    "src/rgw/rgw_trim_bilog.h",
    "src/rgw/rgw_trim_datalog.h",
    "src/rgw/rgw_trim_mdlog.h",
}
forward = {"src/rgw/rgw_otp.h"}
cursor = {"src/rgw/rgw_log_backing.h"}
all_paths = cli | trim | forward | cursor
assert len(all_paths) == 7


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True,
        encoding="utf-8",
    )
    old, new = [], []
    for line in diff.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and line[1:].strip():
            old.append(line[1:].strip())
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:].strip())
    return old, new


for source in sorted(all_paths):
    old, new = changed_lines(source)
    if source in trim:
        assert old and len(old) == len(new), source
        def normalize(line):
            return line.replace("RGWRadosStore", "RadosStore").replace(" *", "*").replace("* ", "*")
        assert all(normalize(a) == normalize(b) for a, b in zip(old, new)), source
    elif source in forward:
        assert old == ["class RGWRadosStore;"] and new == ["class Store;"], source
    elif source in cursor:
        assert old == ['return { 0, ""sv };'] and new == ['return { 0, "" };'], source
    elif source == "src/rgw/rgw_es_main.cc":
        assert old == ["vector<const char*> args;", "argv_to_vec(argc, (const char **)argv, args);"]
        assert new == ["using namespace std;", "auto args = argv_to_vec(argc, argv);"]
    else:
        assert source == "src/rgw/rgw_token.cc"
        assert old == [
            "vector<const char*> args;",
            "argv_to_vec(argc, (const char **)argv, args);",
            "auto cct = global_init(NULL, args, CEPH_ENTITY_TYPE_CLIENT,",
        ]
        assert new == [
            "using namespace std;",
            "auto args = argv_to_vec(argc, argv);",
            "auto cct = global_init(nullptr, args, CEPH_ENTITY_TYPE_CLIENT,",
        ]

for tag, fragment in [
    ("v16.2.15", "args.insert(args.end(), argv + 1, argv + argc);"),
    ("v17.2.7", "return {argv + 1, argv + argc};"),
]:
    source = subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":src/common/ceph_argparse.cc"],
        text=True,
        encoding="utf-8",
    )
    assert fragment in source, tag

target = subprocess.check_output(
    ["git", "-C", str(repo), "show", "v17.2.7:src/rgw/rgw_log_backing.h"],
    text=True,
    encoding="utf-8",
)
assert "inline std::pair<uint64_t, std::string_view>\ncursorgen" in target

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in sorted(all_paths):
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source in cli:
        reason = "RGW-MECH-06: CLI argv_to_vec changes from filling an empty vector to returning the same argv[1:argc] range; remaining hunk is namespace/nullptr spelling."
    elif source in trim:
        reason = "RGW-MECH-06: Only renames the SAL RADOS store type in trim declarations; no trim algorithm, data or call argument changes in this file."
    elif source in forward:
        reason = "RGW-MECH-06: Only swaps an unused RADOS store forward declaration for the generic Store declaration; this header has no operation change."
    else:
        reason = "RGW-MECH-06: Empty string literal still constructs the same empty std::string_view in the pair returned by cursorgen."
    row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(all_paths)} exact RGW CLI/declaration cleanup diffs trivial")
