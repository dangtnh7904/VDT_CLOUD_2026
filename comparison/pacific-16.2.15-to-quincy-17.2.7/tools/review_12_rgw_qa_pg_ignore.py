"""Record RGW suite PG warning ignorelist changes as validation-impacting."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
shared = "qa/rgw/ignore-pg-availability.yaml"
suites = {
    "cloud-transition",
    "hadoop-s3a",
    "lifecycle",
    "notifications",
    "singleton",
    "tempest",
    "thrash",
    "tools",
    "website",
}
links = {f"qa/suites/rgw/{suite}/ignore-pg-availability.yaml" for suite in suites}
assert len(links) == 9


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", tag + ":" + source],
        text=True,
        encoding="utf-8",
    )


base = show("v16.2.15", shared)
target = show("v17.2.7", shared)
assert r"\(PG_AVAILABILITY\)" in base and r"\(PG_DEGRADED\)" not in base
assert r"\(PG_AVAILABILITY\)" in target and r"\(PG_DEGRADED\)" in target
assert "not have an application enabled" in target and "not have an application enabled" not in base
for source in sorted(links):
    assert show("v17.2.7", source).strip() == ".qa/rgw/ignore-pg-availability.yaml", source
    absent = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", "v16.2.15:" + source],
        capture_output=True,
    )
    assert absent.returncode != 0, source

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in sorted(links | {shared}):
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source in links:
        assert row["status"] == "A" and row["new_mode"] == "120000", source
        reason = "RGW-013: New suite symlink selects shared RGW log-ignorelist; when that QA suite is used for upgrade acceptance, PG_DEGRADED warnings can be omitted from log-failure signal."
    else:
        assert row["status"] == "M"
        reason = "RGW-013: Shared RGW QA log-ignorelist adds PG_DEGRADED and application-warning patterns; selected suite results no longer fail on those matching log lines."
    row.update(upgrade_impact="affect", finding_id="RGW-013", impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Recorded RGW-013 on shared ignorelist and {len(links)} suite links")
