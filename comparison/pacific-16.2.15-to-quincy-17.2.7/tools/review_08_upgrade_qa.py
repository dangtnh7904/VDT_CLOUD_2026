"""Classify inspected cephadm upgrade and OSD QA suite selectors."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "08-cephadm-orchestrator.csv"
affect = {
    "qa/suites/orch/cephadm/upgrade/3-upgrade/simple.yaml": "Upgrade recipe now disables journald logging before the image upgrade, changing test observability and expected log path.",
    "qa/suites/orch/cephadm/upgrade/4-wait.yaml": "Removes upgrade-wait health log ignorelist, changing which failures are tolerated by this validation suite.",
    "qa/suites/orch/cephadm/upgrade/5-upgrade-ls.yaml": "Upgrade listing assertion now adds --show-all-versions before grepping 16.2.0; changes exercised CLI and acceptance check.",
    "qa/suites/orch/cephadm/upgrade/agent": "New suite selector points upgrade validation at on/off agent variants.",
    "qa/suites/orch/cephadm/smoke/agent/on.yaml": "New QA variant explicitly enables mgr/cephadm/use_agent, exercising agent metadata path.",
    "qa/suites/orch/cephadm/smoke/agent/off.yaml": "New QA variant explicitly disables mgr/cephadm/use_agent, exercising SSH fallback path.",
    "qa/suites/orch/cephadm/smoke/start.yaml": "Removes smoke-start MON/PG health log ignorelist, changing test failure acceptance.",
    "qa/suites/orch/cephadm/osds/2-ops/repave-all.yaml": "Removes MON/OSD/PG health log ignorelist from repave-all OSD suite, changing test acceptance.",
    "qa/suites/orch/cephadm/osds/2-ops/rm-zap-add.yaml": "Removes MON/OSD/PG health log ignorelist from rm-zap-add suite, changing test acceptance.",
    "qa/suites/orch/cephadm/osds/2-ops/rm-zap-flag.yaml": "Removes MON/OSD/PG health log ignorelist from rm-zap-flag suite, changing test acceptance.",
    "qa/suites/orch/cephadm/osds/2-ops/rm-zap-wait.yaml": "Removes MON/OSD/PG health log ignorelist from rm-zap-wait suite, changing test acceptance.",
    "qa/suites/orch/cephadm/osds/2-ops/rmdir-reactivate.yaml": "Removes MON/OSD/PG/stray-daemon health log ignorelist from reactivation suite, changing test acceptance.",
}
trivial = {
    "doc/cephadm/adoption.rst": "T08-adoption-typos: Corrects two spelling errors in adoption prose; commands and adoption procedure are unchanged.",
    "doc/cephadm/troubleshooting.rst": "T08-troubleshooting-typo: Corrects 'neccessary' spelling in manual deployment explanation; command and JSON recipe are unchanged.",
}
selected = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name not in selected:
        continue
    if name in affect:
        assert row["upgrade_impact"] in ("", "affect"), name
        assert row["finding_id"] in ("", "ADM-008"), name
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "ADM-008"
        row["impact_reason"] = "ADM-008: " + affect[name]
    else:
        assert row["upgrade_impact"] in ("", "trivial"), name
        assert not row["finding_id"], name
        row["upgrade_impact"] = "trivial"
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
