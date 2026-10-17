"""Classify the inspected RGW mixed-version multisite QA suite."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
prefix = "qa/suites/rgw-multisite-upgrade/"

reasons = {
    ".qa": "RGW-001: Root .qa link enables the dedicated RGW multisite upgrade suite tree; endpoint target has the suite, base does not. Git R100 is a content-match heuristic, not evidence of a logical move.",
    "pacific-x/%": "RGW-001: Empty % suite marker participates in the new pacific-x upgrade QA matrix; the target path is new as a suite choice although Git reports an unrelated R100 match.",
    "pacific-x/.qa": "RGW-001: .qa link connects the pacific-x upgrade QA branch to shared suite fragments, changing the selectable test matrix.",
    "pacific-x/clusters.yaml": "RGW-001: Defines separate c1/c2 MON, MGR, OSD and RGW client roles for cross-cluster mixed-version validation.",
    "pacific-x/frontend.yaml": "RGW-001: Selects Beast frontend for the mixed-version RGW multisite acceptance scenario.",
    "pacific-x/overrides.yaml": "RGW-001: QA overrides select Pacific rgw_multi tests, RGW compression/KMS/sync settings, and ignore PG_AVAILABILITY plus scrub wait; they change test workload and health acceptance signal.",
    "pacific-x/realm.yaml": "RGW-001: Defines master/secondary RGW zones on c1/c2 and runs tests.py; this is the multisite sync topology and assertion set used after one side upgrades.",
    "pacific-x/supported-random-distro$": "RGW-001: Distro selector link is part of the new mixed-version suite matrix; unrelated R100 source path does not establish a logical move.",
    "pacific-x/tasks.yaml": "RGW-001: Installs Pacific on both clusters, invokes upgrade-task before RGW start, then runs rgw-multisite-tests with reconfigure_delay 60; this is the execution recipe.",
    "pacific-x/upgrade/.qa": "RGW-001: .qa link enables shared suite fragments for the two upgrade direction variants.",
    "pacific-x/upgrade/primary.yaml": "RGW-001: install.upgrade moves c1 roles to current while c2 remains Pacific, creating one directional mixed-version acceptance case.",
    "pacific-x/upgrade/secondary.yaml": "RGW-001: install.upgrade moves c2 roles to current while c1 remains Pacific, creating the reverse mixed-version acceptance case.",
}

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for suffix, reason in reasons.items():
    matches = [row for row in rows if row["path"] == prefix + suffix]
    assert len(matches) == 1, suffix
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "RGW-001"
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(reasons)} RGW multisite upgrade QA rows")
