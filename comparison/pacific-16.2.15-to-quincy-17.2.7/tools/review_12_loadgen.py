"""Classify inspected RGW loadgen frontend request-path changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

source = by_path["src/rgw/rgw_loadgen_process.cc"]
assert not source["upgrade_impact"] and not source["finding_id"] and not source["impact_reason"]
source.update(
    upgrade_impact="affect",
    finding_id="RGW-007",
    impact_reason="RGW-007: Loadgen request handler now constructs a local ActiveRateLimiter without start(), but its destructor unconditionally joins the unstarted thread; conditional validation-path termination.",
)

support = by_path["src/rgw/rgw_ratelimit.h"]
assert support["upgrade_impact"] == "affect" and "RGW-007:" not in support["impact_reason"]
support["impact_reason"] += " RGW-007: ActiveRateLimiter destructor unconditionally calls runner.join(), including for an instance whose start() was never called."

helper = by_path["src/rgw/rgw_loadgen.cc"]
assert not helper["upgrade_impact"] and not helper["finding_id"] and not helper["impact_reason"]
helper.update(
    upgrade_impact="trivial",
    finding_id="RGW-007",
    impact_reason="RGW-007 support: Only adds using namespace std; no loadgen request or limiter behavior changes in this file.",
)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified RGW loadgen failure path and syntax-only support row")
