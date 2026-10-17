"""Screen exact RGW test-only spelling and helper API changes."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
namespace = {
    "src/test/cls_rgw/test_cls_rgw.cc",
    "src/test/cls_rgw_gc/test_cls_rgw_gc.cc",
    "src/test/rgw/test_rgw_bencode.cc",
}
processor = {
    "src/test/rgw/test_rgw_compression.cc",
    "src/test/rgw/test_rgw_putobj.cc",
}
argv = {
    "src/test/test_rgw_admin_log.cc",
    "src/test/test_rgw_admin_meta.cc",
    "src/test/rgw/test_rgw_manifest.cc",
    "src/test/rgw/test_rgw_period_history.cc",
}
other = {
    "src/test/rgw/test_rgw_throttle.cc",
    "src/test/rgw/test_log_backing.cc",
    "src/test/rgw/test_cls_fifo_legacy.cc",
}
all_paths = namespace | processor | argv | other
assert len(all_paths) == 12


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
    if source in namespace:
        assert old == [] and new == ["using namespace std;"], source
    elif source in processor:
        assert len(old) == len(new) == 1, source
        assert old[0].replace("rgw::putobj::DataProcessor", "rgw::sal::DataProcessor") == new[0], source
    elif source in argv:
        assert old == ["vector<const char*> args;", "argv_to_vec(argc, (const char **)argv, args);"], source
        assert new == (["using namespace std;"] if source.endswith("test_rgw_period_history.cc") else []) + ["auto args = argv_to_vec(argc, argv);"], source
    elif source.endswith("test_rgw_throttle.cc"):
        assert len(old) == len(new) == 1 and old[0].replace(".create()", ".create(&no_dpp)") == new[0], source
    elif source.endswith("test_log_backing.cc"):
        assert old == ['const auto pcurs = "fded"sv;']
        assert new == ['const std::string_view pcurs = "fded";']
    else:
        assert source.endswith("test_cls_fifo_legacy.cc")
        assert old == [] and new == ["using namespace std::literals;", "using namespace std::string_literals;"], source

for tag, fragment in [
    ("v16.2.15", "args.insert(args.end(), argv + 1, argv + argc);"),
    ("v17.2.7", "return {argv + 1, argv + argc};"),
]:
    common = subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":src/common/ceph_argparse.cc"],
        text=True,
        encoding="utf-8",
    )
    assert fragment in common

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
    if source in argv:
        reason = "RGW-TEST-01: Test main still passes the same argv[1:argc] range after argv_to_vec returns a vector; no test case or upgrade acceptance criterion changes."
    elif source in processor:
        reason = "RGW-TEST-01: Test mock/sink only follows the SAL DataProcessor type move; its test operations and assertions are unchanged."
    elif source.endswith("test_rgw_throttle.cc"):
        reason = "RGW-TEST-01: Test pool creation only gains logging DPP context; test setup result and assertions are unchanged."
    else:
        reason = "RGW-TEST-01: Test file only changes standard namespace/type visibility or equivalent empty string_view spelling; test cases and assertions are unchanged."
    row.update(upgrade_impact="trivial", finding_id="", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(all_paths)} exact test-only RGW diffs trivial")
