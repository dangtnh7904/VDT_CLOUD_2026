"""Classify Dashboard v3 summary pipes and metric display formatters."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
frontend = "src/pybind/mgr/dashboard/frontend/src/app/"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, relative: str) -> str:
    return git("show", f"{tag}:{frontend}{relative}").stdout


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


for commit in (
    "6f5b9533b333521f7dc32b1879082d7bdaca71c5",
    "e17dc5593b28cec3c81635aec3e12d74600bf0aa",
    "4338f947f179898d5ec7fb76fe98a13bc3d1a925",
    "9fdd4ee886c192312047386b94adda0486124d92",
    "d534ac26108dde57eda0e6abd484258668e64463",
):
    target_only(commit)

mds = show("v17.2.7", "shared/pipes/mds-summary.pipe.ts")
mgr = show("v17.2.7", "shared/pipes/mgr-summary.pipe.ts")
osd = show("v17.2.7", "shared/pipes/osd-summary.pipe.ts")
assert "up:standby-replay" in mds
assert "const totalCount = activeCount + standbyCount" in mds
assert "let activeCount: number" in mgr
assert "const totalCount = activeCount + standbyCount" in mgr
assert "nearfull" in osd and "full" in osd and "downCount" in osd

target_pipes_module = show("v17.2.7", "shared/pipes/pipes.module.ts")
for pipe in ("HealthIconPipe", "MgrSummaryPipe", "MdsSummaryPipe", "OsdSummaryPipe"):
    assert pipe in target_pipes_module

base_binary = show("v16.2.15", "shared/pipes/dimless-binary-per-second.pipe.ts")
target_binary = show("v17.2.7", "shared/pipes/dimless-binary-per-second.pipe.ts")
assert "'kB/s'" in base_binary
assert "'KiB/s'" in target_binary

target_formatter = show("v17.2.7", "shared/services/formatter.service.ts")
target_number = show("v17.2.7", "shared/services/number-formatter.service.ts")
assert "formatNumberFromTo(" in target_formatter
assert "formatBytesPerSecondFromTo(" in target_number
assert "formatSecondsFromTo(" in target_number
area_chart = git(
    "show",
    "v17.2.7:src/pybind/mgr/dashboard/frontend/src/app/ceph/dashboard-v3/dashboard-area-chart/dashboard-area-chart.component.ts",
).stdout
assert "NumberFormatterService" in area_chart
assert "formatBytesPerSecondFromTo(" in area_chart
assert "formatSecondsFromTo(" in area_chart

target_duration = show("v17.2.7", "shared/pipes/duration.pipe.ts")
target_empty = show("v17.2.7", "shared/pipes/empty.pipe.ts")
assert "seconds === null || seconds <= 0" in target_duration
assert "_.isNaN(value)" in target_empty

mgr020_paths = {
    "shared/enum/health-icon.enum.ts",
    "shared/pipes/health-icon.pipe.ts",
    "shared/pipes/mds-summary.pipe.ts",
    "shared/pipes/mgr-summary.pipe.ts",
    "shared/pipes/osd-summary.pipe.ts",
    "shared/pipes/pipes.module.ts",
}
mgr057_paths = {
    "shared/pipes/dimless-binary-per-second.pipe.ts",
    "shared/pipes/duration.pipe.ts",
    "shared/pipes/empty.pipe.ts",
    "shared/services/formatter.service.ts",
    "shared/services/number-formatter.service.ts",
}
trivial_paths = {
    "ceph/dashboard/health-pie/health-pie.component.html",
    "shared/components/usage-bar/usage-bar.component.html",
    "shared/components/usage-bar/usage-bar.component.ts",
    "shared/helpers/helpers.module.ts",
    "shared/models/cd-details.ts",
}
assert len(mgr020_paths) == 6 and len(mgr057_paths) == 5 and len(trivial_paths) == 5
assert not (mgr020_paths & mgr057_paths or mgr020_paths & trivial_paths or mgr057_paths & trivial_paths)

reasons = {
    "MGR-020": (
        "MGR-020: New Dashboard v3 health/icon and MDS/MGR/OSD summary pipes "
        "derive the counts and status visuals used by the default landing page, so "
        "active-MGR version can change the rollout acceptance signal."
    ),
    "MGR-057": (
        "MGR-057: Frontend metric formatting now performs explicit unit conversion, "
        "uses IEC byte-rate labels, renders NaN as N/A and hides null/non-positive "
        "durations. The backend sample is unchanged but the operator-visible value "
        "or unit used for rollout assessment can differ."
    ),
}
trivial_reason = (
    "MGR-FRONTEND-SIGNAL-SUPPORT-08: Adds an empty helper module, a TypeScript-only "
    "DashboardDetails interface, ARIA/title inputs for a usage bar, or removes an "
    "empty tooltip table. No value derivation, backend call or rollout command is "
    "changed in these endpoints."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

for finding, relatives in (("MGR-020", mgr020_paths), ("MGR-057", mgr057_paths)):
    for relative in relatives:
        path = frontend + relative
        row = by_path[path]
        if row["upgrade_impact"]:
            assert row["upgrade_impact"] == "affect", path
            assert row["finding_id"] == finding, path
            assert row["impact_reason"] == reasons[finding], path
        else:
            row["upgrade_impact"] = "affect"
            row["finding_id"] = finding
            row["impact_reason"] = reasons[finding]

for relative in trivial_paths:
    path = frontend + relative
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", path
        assert row["finding_id"] == "", path
        assert row["impact_reason"] == trivial_reason, path
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial_reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect >= 263 and trivial >= 380 and unclassified <= 83
print("Classified Dashboard signal formatters: 11 affect, 5 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
