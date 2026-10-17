"""Classify Dashboard locale/style support and TypeScript gate changes."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


locale_dir = "src/pybind/mgr/dashboard/frontend/src/locale/"
languages = (
    "cs", "de-DE", "es-ES", "fr-FR", "id-ID", "it-IT",
    "ja-JP", "ko-KR", "pl-PL", "pt-BR", "zh-CN", "zh-TW",
)
locale_paths = {locale_dir + f"messages.{language}.xlf" for language in languages}
for path in locale_paths:
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    assert base.count("<trans-unit ") == 1535, path
    assert target.count("<trans-unit ") == 1406, path
    assert 'version="1.2"' in base and 'version="1.2"' in target

i18n_path = "src/pybind/mgr/dashboard/frontend/i18n.config.json"
base_i18n = show("v16.2.15", i18n_path)
target_i18n = show("v17.2.7", i18n_path)
assert '"resource": "Pacific:pacific"' in base_i18n
assert '"resource": "Master:master"' in target_i18n

style_paths = {
    "src/pybind/mgr/dashboard/frontend/src/styles/bootstrap-extends.scss",
    "src/pybind/mgr/dashboard/frontend/src/styles/ceph-custom/_basics.scss",
    "src/pybind/mgr/dashboard/frontend/src/styles/ceph-custom/_buttons.scss",
    "src/pybind/mgr/dashboard/frontend/src/styles/ceph-custom/_forms.scss",
    "src/pybind/mgr/dashboard/frontend/src/styles/defaults/_bootstrap-defaults.scss",
}
target_bootstrap = show(
    "v17.2.7",
    "src/pybind/mgr/dashboard/frontend/src/styles/bootstrap-extends.scss",
)
target_defaults = show(
    "v17.2.7",
    "src/pybind/mgr/dashboard/frontend/src/styles/defaults/_bootstrap-defaults.scss",
)
assert "@extend .ps-2" in target_bootstrap
assert "$health-color-error: $red" in target_defaults
assert "$health-color-warning: $yellow" in target_defaults

tsconfig_path = "src/pybind/mgr/dashboard/frontend/tsconfig.json"
tslint_path = "src/pybind/mgr/dashboard/frontend/tslint.json"
base_tsconfig = show("v16.2.15", tsconfig_path)
target_tsconfig = show("v17.2.7", tsconfig_path)
base_tslint = show("v16.2.15", tslint_path)
assert '"skipLibCheck": true' in base_tsconfig
assert '"skipLibCheck": true' not in target_tsconfig
assert '"resolveJsonModule": true' in target_tsconfig
assert '"rulesDirectory"' in base_tslint
target_tslint = subprocess.run(
    ["git", "-C", str(repo), "cat-file", "-e", f"v17.2.7:{tslint_path}"],
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
assert target_tslint.returncode != 0

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

trivial_rows = locale_paths | style_paths | {i18n_path}
assert len(trivial_rows) == 18
for path in trivial_rows:
    row = by_path[path]
    reason = (
        "MGR-I18N-CATALOG-01: Regenerates the twelve XLIFF 1.2 locale catalogs "
        "from 1535 to the same 1406 target message IDs and switches the manual "
        "Transifex resource from Pacific to Master; this changes translated UI "
        "text/workflow inputs but is not invoked by the daemon upgrade or the "
        "repository rollout gate."
        if path in locale_paths or path == i18n_path
        else
        "MGR-FRONTEND-STYLE-01: Updates Bootstrap 5 class aliases, form/button "
        "styling and accessible theme colors; semantic health states, API data, "
        "daemon behavior and the upgrade acceptance command are unchanged."
    )
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = reason

affect_rows = {
    tsconfig_path: (
        "MGR-047",
        "MGR-047: Frontend TypeScript compilation enables JSON modules and no "
        "longer skips library declaration checks, so the Quincy build/typecheck "
        "gate can fail on dependencies that Pacific ignored; this does not "
        "change an already-built daemon at runtime.",
    ),
    tslint_path: (
        "MGR-044",
        "MGR-044: Deletes the TSLint rule set as the frontend gate migrates to "
        "Angular ESLint, changing which source/template violations pass or fail "
        "the target validation pipeline.",
    ),
}
for path, (finding, reason) in affect_rows.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = finding
        row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect + trivial + unclassified == 726
assert affect >= 214 and trivial >= 170 and unclassified <= 342
print("Classified frontend support batch: 2 affect, 18 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
