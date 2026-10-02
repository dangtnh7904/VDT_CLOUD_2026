"""Screen small MGR modules whose endpoint hunks have no upgrade path."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
trivial = {
    "src/pybind/mgr/alerts/__init__.py": "T07-init-flake8: Adds flake8 suppression comment only; import remains the same.",
    "src/pybind/mgr/crash/__init__.py": "T07-init-flake8: Adds flake8 suppression comment only; import remains the same.",
    "src/pybind/mgr/hello/__init__.py": "T07-init-flake8: Adds flake8 suppression comment only; import remains the same.",
    "src/pybind/mgr/hello/module.py": "T07-hello-demo: Converts example CLI handlers/options to decorators and typed Option; output wording changes only in hello demo, with no upgrade control, health or recovery path.",
    "src/pybind/mgr/iostat/__init__.py": "T07-init-flake8: Adds flake8 suppression comment only; import remains the same.",
    "src/pybind/mgr/iostat/module.py": "T07-iostat-typing: Type annotations, self-test annotation and indentation only; iostat output calculation and poll command stay the same.",
    "src/pybind/mgr/localpool/__init__.py": "T07-init-flake8: Adds flake8 suppression comment only; import remains the same.",
    "src/pybind/mgr/localpool/module.py": "T07-localpool-typing: Converts unchanged option defaults to Option, adds help text and type casts; OSDMap pool creation logic is unchanged in the endpoint hunk.",
}
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in trivial} == set(trivial)
for row in rows:
    if row["path"] in trivial:
        assert not row["upgrade_impact"], row["path"]
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[row["path"]]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
