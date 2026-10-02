"""Record screened OSD unit-test endpoint adaptations."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"
trivial = {
    "src/test/osd/TestECBackend.cc": "Only adds std namespace import; stripe-info test inputs and assertions are unchanged.",
    "src/test/osd/TestMClockScheduler.cc": "Fixture passes new scheduler constructor arguments with zero IDs and null MonClient and drops an unused mock get_op_type override; test cases and assertions are unchanged.",
    "src/test/osd/TestOSDMap.cc": "Test setup adapts to CRUSH rule API without ruleset/min-max mask and JSON getter API; existing scenario assertions remain, while runtime rule behavior is analyzed in MON-006/OSD-030.",
    "src/test/osd/TestOSDScrub.cc": "Fixture passes unique_ptr ObjectStore into OSD and calls the moved scrub_time_permit service method; the same time-permit test assertions remain.",
    "src/test/osd/TestOpStat.h": "Qualifies map, multiset and string as std types without changing latency accounting in test helper.",
    "src/test/osd/TestPGLog.cc": "Endpoint hunk only adds std namespace import; PGLog trim experiments in intermediate commits do not survive endpoint diff.",
    "src/test/osd/ceph_test_osd_stale_read.cc": "Switches to argv_to_vec return-value API with the same argv[1:argc] inputs, plus std namespace and nullptr spelling; stale-read assertions unchanged.",
    "src/test/osd/osdcap.cc": "Only adds std namespace import; capability parse fixtures and assertions unchanged.",
    "src/test/osd/test_extent_cache.cc": "Only adds std namespace import; extent-cache test inputs and assertions unchanged.",
    "src/test/osd/test_pg_transaction.cc": "Only adds std namespace import; PG transaction test inputs and assertions unchanged.",
    "src/test/osd/types.cc": "Only adds std namespace import; hobject type test inputs and assertions unchanged.",
}
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in trivial} == set(trivial)
for row in rows:
    if row["path"] in trivial:
        assert not row["upgrade_impact"], row["path"]
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-osd-unit-adapt: {trivial[row['path']]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
