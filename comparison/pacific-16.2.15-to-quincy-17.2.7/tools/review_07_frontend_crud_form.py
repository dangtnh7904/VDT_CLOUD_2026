"""Classify the generic Dashboard Formly CRUD form framework as opt-in UI."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
crud_prefix = "src/pybind/mgr/dashboard/frontend/src/app/shared/forms/crud-form/"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


for commit in (
    "36e32132f1cb26f89cc6825c29194aaf05b5c663",
    "4654d60ea675945ea5f60169ac97b190e1f4fdf9",
    "9c256e0a7721523828892a72c71e3ccbd8a559c9",
    "12f78b48b0f905331bfbc53b5f279bd1bd7fc0cb",
):
    target_only(commit)

history = git(
    "log", "--format=%H", "v16.2.15..v17.2.7", "--", crud_prefix
).stdout.splitlines()
assert set(history) == {
    "36e32132f1cb26f89cc6825c29194aaf05b5c663",
    "4654d60ea675945ea5f60169ac97b190e1f4fdf9",
    "9c256e0a7721523828892a72c71e3ccbd8a559c9",
    "12f78b48b0f905331bfbc53b5f279bd1bd7fc0cb",
}

target_component = git(
    "show", f"v17.2.7:{crud_prefix}crud-form.component.ts"
).stdout
assert "ngOnInit(): void" in target_component
assert "this.dataGatewayService.form(" in target_component
assert "async submit(" in target_component
assert "call: this.dataGatewayService.submit(" in target_component
assert target_component.index("async submit(") < target_component.index(
    "call: this.dataGatewayService.submit("
)
assert "setInterval(" not in target_component
assert "setTimeout(" not in target_component

target_validator = git(
    "show", f"v17.2.7:{crud_prefix}validators/rgw-role-validator.ts"
).stdout
assert "export function formlyRgwRolePath" in target_validator
assert "export function formlyRgwRoleNameValidator" in target_validator
assert "HttpClient" not in target_validator

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

reason_prefix = "MGR-FRONTEND-CRUD-SUPPORT-07:"
selected = {
    row["path"]
    for row in rows
    if row["path"].startswith(crud_prefix)
    and (not row["upgrade_impact"] or row["impact_reason"].startswith(reason_prefix))
}
assert len(selected) == 20
reason = (
    reason_prefix
    + " Generic Formly renderers, file/JSON/RGW-role validators and the CRUD form "
    "component only fetch form metadata when its route is opened; the write call "
    "is under the explicit submit handler. These endpoints do not run during an "
    "upgrade, poll cluster state or provide an independent acceptance signal."
)

for row in rows:
    if row["path"] not in selected:
        continue
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial", row["path"]
        assert row["finding_id"] == "", row["path"]
        assert row["impact_reason"] == reason, row["path"]
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
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
assert affect >= 237 and trivial >= 374 and unclassified <= 115
print("Classified generic Formly CRUD framework: 20 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
