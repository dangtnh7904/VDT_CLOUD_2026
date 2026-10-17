"""Classify shared Dashboard table pagination, filtering and count semantics."""

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
    "e7b89f88c5339909255e6fdd700b09eb72ded8fd",
    "d154d4383c9a2196daabcc906e6077129dd1db04",
    "a1fbe19b0aae53bead3d7d4feebc71f4af2eb5a7",
    "0c48ef019c9497edf4367f21f934692be2bd1e08",
    "25b8ce92f93407bf29cb0dd4015c4a35cb37d4dd",
):
    target_only(commit)

paginate = show("v17.2.7", "shared/api/paginate.model.ts")
assert "X-Total-Count" in paginate
assert "return response['body']" in paginate

pagination = show("v17.2.7", "shared/datatable/table-pagination/table-pagination.component.ts")
assert "Math.ceil(this._count / this._size)" in pagination
assert "this._page = this.totalPages" in pagination
assert "pageChange.emit" in pagination

base_table = show("v16.2.15", "shared/datatable/table/table.component.ts")
target_table = show("v17.2.7", "shared/datatable/table/table.component.ts")
base_array = base_table.index("if (_.isArray(cellValue))")
base_object = base_table.index("if (_.isObjectLike(cellValue))")
target_array = target_table.index("if (_.isArray(cellValue))")
target_object = target_table.index("if (_.isObjectLike(cellValue))")
assert base_array < base_object
assert target_object < target_array
assert "this.cellTemplates.timeAgo = this.timeAgoTpl" in target_table

context = show("v17.2.7", "shared/models/cd-table-fetch-data-context.ts")
assert "Number.isNaN(this.pageInfo.offset)" in context
assert "this.sort = '+name'" in context

table_html = show("v17.2.7", "shared/datatable/table/table.component.html")
assert "<cd-table-pagination" in table_html
assert "[count]=\"rowCount\"" in table_html

paths = {
    "shared/api/paginate.model.ts",
    "shared/datatable/datatable.module.ts",
    "shared/datatable/table-pagination/table-pagination.component.html",
    "shared/datatable/table-pagination/table-pagination.component.ts",
    "shared/datatable/table/table.component.html",
    "shared/datatable/table/table.component.ts",
    "shared/enum/cell-template.enum.ts",
    "shared/models/cd-table-fetch-data-context.ts",
}
assert len(paths) == 8
reason = (
    "MGR-058: Shared Dashboard tables now consume X-Total-Count, normalize a NaN "
    "offset/default sort, replace the pager with a clamping page selector and "
    "change search conversion order so array-valued cells can stop matching unless "
    "object search is enabled. Host/service/RBD and alert inventories used for "
    "rollout checks can therefore show or find a different row set."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

for relative in paths:
    path = frontend + relative
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", path
        assert row["finding_id"] == "MGR-058", path
        assert row["impact_reason"] == reason, path
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-058"
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
assert affect >= 271 and trivial >= 380 and unclassified <= 75
print("Classified shared table/pagination semantics: 8 affect")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
