"""Record only the explicitly screened owner-06 rows."""

import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "06-config-defaults.csv"
review = {
    "doc/man/8/librados-config.rst": ("trivial", "", "T06-url: single hunk updates docs URL to https; commit 5757c69b06d; no daemon configuration or upgrade recipe change."),
    "doc/dev/config.rst": ("trivial", "", "T06-dev-doc: hunks document YAML option authoring and fix example/grammar; source generator and runtime behavior are reviewed separately."),
    "src/sample.ceph.conf": ("trivial", "", "T06-comment: one hunk changes 'CRUSH ruleset' comment to 'CRUSH rule'; commit d67bad8f311; sample setting unchanged."),
    "src/common/config_proxy.h": ("trivial", "", "T06-copy-constructor: single hunk removes explicit on public copy constructor; commit 9162613acf1; no config lookup/default path change."),
    "src/common/legacy_config_opts.h": ("affect", "CFG-005", "CFG-005: hard-coded legacy option declaration header is removed; target generates per-service declarations from YAML at build time."),
    "src/common/config.cc": ("affect", "CFG-005", "CFG-005: md_config_t now includes generated options/legacy_config_opts.h; target source build requires YAML-generated declarations."),
    "src/common/config_values.h": ("affect", "CFG-005", "CFG-005: ConfigValues legacy members now depend on generated per-service header rather than old hard-coded header."),
    "src/common/options.h": ("affect", "CFG-005", "CFG-005: target option value type and user-defined unit literals are consumed by YAML-generated option code."),
    "src/common/options/build_options.cc": ("affect", "CFG-005", "CFG-005: target composes service YAML-generated options and auto-adds service tags; delivery and option scope can differ."),
    "src/common/options/build_options.h": ("affect", "CFG-005", "CFG-005: declares new build_options() entry point for generated option composition."),
    "src/common/options/legacy_config_opts.h": ("affect", "CFG-005", "CFG-005: target aggregates generated per-service legacy option headers, changing source-build input path."),
    "src/common/options/y2c.py": ("affect", "CFG-005", "CFG-005: target build invokes PyYAML-based y2c.py to generate C++ and legacy headers from service YAML files."),
    "src/common/options/validate-options.py": ("affect", "CFG-005", "CFG-005: target CMake test invokes validator on generated service YAML, changing source-build acceptance gate."),
}
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
for row in rows:
    if row["path"] in review:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == review[row["path"]][0]
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = review[row["path"]]
assert len(review) == sum(row["path"] in review for row in rows)
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
