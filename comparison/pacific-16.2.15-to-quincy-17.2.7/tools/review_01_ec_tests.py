"""Screen endpoint EC test diffs without inferring runtime impact from tests."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
reasons = {
    "src/test/erasure-code/ErasureCodeExample.h": "std namespace qualification and using declaration keep test helper methods and algorithms unchanged.",
    "src/test/erasure-code/ErasureCodePluginExample.cc": "Adds only using namespace std to test plugin example; no test case, input or assertion changes.",
    "src/test/erasure-code/TestErasureCode.cc": "Adds only using namespace std; existing erasure-code test cases and expectations remain unchanged.",
    "src/test/erasure-code/TestErasureCodeClay.cc": "Adds std using declaration and renames local ruleset variable to ruleid; create_rule result, do_rule call and assertions are unchanged.",
    "src/test/erasure-code/TestErasureCodeIsa.cc": "Adds std using declaration and renames local ruleset variable to rule; create_rule result, do_rule call and assertions are unchanged.",
    "src/test/erasure-code/TestErasureCodeJerasure.cc": "Adds std using declaration and renames local ruleset variable to rule; create_rule result, do_rule call and assertions are unchanged.",
    "src/test/erasure-code/TestErasureCodeLrc.cc": "Adds only using namespace std; no test behavior or selection change.",
    "src/test/erasure-code/TestErasureCodePlugin.cc": "Adds only using namespace std; no plugin test behavior or selection change.",
    "src/test/erasure-code/TestErasureCodePluginClay.cc": "Changes Clay scalar_mds=isa test guard from HAVE_NASM_X64_AVX2 to WITH_EC_ISA_PLUGIN; target CMake sets the latter as a cache variable but no endpoint source defines it as a C++ macro, so standard test coverage may change.",
    "src/test/erasure-code/TestErasureCodePluginIsa.cc": "Adds only using namespace std; no ISA plugin test behavior or selection change.",
    "src/test/erasure-code/TestErasureCodePluginJerasure.cc": "Adds only using namespace std; no plugin test behavior or selection change.",
    "src/test/erasure-code/TestErasureCodePluginLrc.cc": "Adds only using namespace std; no plugin test behavior or selection change.",
    "src/test/erasure-code/TestErasureCodePluginShec.cc": "Adds only using namespace std; no plugin test behavior or selection change.",
    "src/test/erasure-code/TestErasureCodeShec.cc": "Adds std using declaration and changes ruleset to rule in comments; test calls and assertions are unchanged.",
    "src/test/erasure-code/TestErasureCodeShec_all.cc": "argv_to_vec now returns the same argv[1:argc] vector previously inserted into an empty vector; test input is unchanged.",
    "src/test/erasure-code/TestErasureCodeShec_arguments.cc": "argv_to_vec now returns the same argv[1:argc] vector and RUN_ALL_TESTS result remains assigned; test behavior is unchanged.",
    "src/test/erasure-code/TestErasureCodeShec_thread.cc": "Adds only using namespace std; no test behavior or selection change.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in reasons} == set(reasons)
for row in rows:
    if row["path"] in reasons:
        assert not row["upgrade_impact"], row["path"]
        is_gate = row["path"].endswith("TestErasureCodePluginClay.cc")
        row["upgrade_impact"] = "affect" if is_gate else "trivial"
        row["finding_id"] = "OSD-051" if is_gate else ""
        row["impact_reason"] = ("OSD-051: " if is_gate else "T01-ec-tests: ") + reasons[row["path"]]
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
