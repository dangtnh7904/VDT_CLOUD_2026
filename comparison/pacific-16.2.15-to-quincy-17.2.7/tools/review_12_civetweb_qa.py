"""Classify inspected RGW QA frontend matrix and task changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "12-rgw.csv"
reasons = {
    "qa/rgw_frontend/civetweb.yaml": "RGW-004: Deletes Civetweb RGW QA override, removing an executable frontend selection from target test matrix.",
    "qa/suites/rgw/multifs/frontend": "RGW-004: Target symlink selects shared rgw_frontend directory, which contains only Beast after Civetweb removal.",
    "qa/suites/rgw/multifs/frontend/.qa": "RGW-004: Removes old nested suite link as multifs frontend selection changes to shared Beast-only directory.",
    "qa/suites/rgw/multifs/frontend/civetweb.yaml": "RGW-004: Removes explicit Civetweb multifs suite variant from RGW QA coverage.",
    "qa/suites/rgw/singleton/frontend": "RGW-004: Target symlink selects shared rgw_frontend directory, which contains only Beast after Civetweb removal.",
    "qa/suites/rgw/singleton/frontend/.qa": "RGW-004: Removes old nested suite link as singleton frontend selection changes to shared Beast-only directory.",
    "qa/suites/rgw/singleton/frontend/civetweb.yaml": "RGW-004: Removes explicit Civetweb singleton suite variant from RGW QA coverage.",
    "qa/suites/rgw/thrash/civetweb.yaml": "RGW-004: Removes Civetweb thrash suite variant, changing selectable RGW validation coverage.",
    "qa/suites/rgw/thrash/frontend": "RGW-004: Adds shared Beast-only frontend selector to RGW thrash suite in place of Civetweb variant.",
    "qa/tasks/rgw.py": "RGW-004: QA RGW task default frontend changes Civetweb to Beast and TLS port syntax uses ssl_port; this changes executed test setup. Other task hunks need review.",
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for source, reason in reasons.items():
    matches = [row for row in rows if row["path"] == source]
    assert len(matches) == 1, source
    row = matches[0]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "RGW-004"
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(reasons)} Civetweb QA matrix/task rows")
