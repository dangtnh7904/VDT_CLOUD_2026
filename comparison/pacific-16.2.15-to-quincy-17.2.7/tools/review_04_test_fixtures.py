"""Screen remaining owner-04 test/fixture clusters against endpoint hunks."""

import csv
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "04-mon-osdmap-crush.csv"
expected = {
    "cli_crush": 55,
    "cli_monmap": 8,
    "common": 18,
    "crimson": 1,
    "crush": 5,
    "mon": 6,
    "daemon_config": 1,
}
reasons = {
    "cli_crush": "T04-cli-crush: endpoint cram diff/fixtures track rule id, explicit replica range, min/max removal and five-decimal output (MON-006/020); no upgrade execution gate.",
    "cli_monmap": "T04-cli-monmap: cram expected output tracks Octopus default min_mon_release and Quincy feature set (MON-002/023); no independent runtime or rollout step.",
    "common": "T04-common-unit: reviewed common test hunks cover namespace/API updates, Journald/LRU/option unit cases and config output; no identified upgrade execution or acceptance gate.",
    "crimson": "T04-crimson-unit: monc fixture only changes string_view literal syntax; no runtime MON discovery behavior.",
    "crush": "T04-crush-unit: test sources/fixtures follow rule-id API, removed min/max fields and five-decimal weight output (MON-006/020); no independent rollout gate.",
    "mon": "T04-mon-unit: MON tests adjust expected version/feature, compiler/API spelling and unit harness output; no identified upgrade acceptance gate.",
    "daemon_config": "T04-daemon-config-unit: test harness switches argv_to_vec signature and std namespace, preserving parse test intent.",
}


def cluster(p: str) -> str | None:
    if p.startswith("src/test/cli/crushtool/"):
        return "cli_crush"
    if p.startswith("src/test/cli/monmaptool/"):
        return "cli_monmap"
    if p.startswith("src/test/common/"):
        return "common"
    if p.startswith("src/test/crimson/"):
        return "crimson"
    if p.startswith("src/test/crush/"):
        return "crush"
    if p.startswith("src/test/mon/"):
        return "mon"
    if p == "src/test/daemon_config.cc":
        return "daemon_config"
    return None


with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
blank = [r for r in rows if not r["upgrade_impact"]]
assert Counter(cluster(r["path"]) for r in blank) == expected
for row in blank:
    group = cluster(row["path"])
    assert group is not None
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reasons[group]
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
