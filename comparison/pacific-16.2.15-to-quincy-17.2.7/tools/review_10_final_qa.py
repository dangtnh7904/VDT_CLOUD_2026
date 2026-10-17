"""Finish owner-10 with the iSCSI validation transition and workunits."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "10-rados-rbd-clients.csv"
md_path = root / "10-rados-rbd-clients.md"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, path: str) -> str:
    return git("show", f"{tag}:{path}").stdout


def exists(tag: str, path: str) -> bool:
    return git("cat-file", "-e", f"{tag}:{path}", check=False).returncode == 0


def only_in(commit: str, included: str, excluded: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, included, check=False).returncode == 0
    assert git("merge-base", "--is-ancestor", commit, excluded, check=False).returncode != 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


for commit in ("cbd2c71398b", "a7952949a87", "9b306af4213"):
    only_in(commit, "v17.2.7", "v16.2.15")

base_install = show("v16.2.15", "qa/suites/rbd/iscsi/base/install.yaml")
target_install = show("v17.2.7", "qa/suites/rbd/iscsi/base/install.yaml")
assert "project: ceph-iscsi" in base_install
assert "project: ceph-iscsi" not in target_install
assert "cephadm.shell:" in target_install
assert exists("v16.2.15", "qa/tasks/ceph_iscsi.py")
assert not exists("v17.2.7", "qa/tasks/ceph_iscsi.py")
assert not exists("v16.2.15", "qa/tasks/ceph_iscsi_client.py")
assert exists("v17.2.7", "qa/tasks/ceph_iscsi_client.py")
assert "ceph_iscsi_client:" in show(
    "v17.2.7", "qa/suites/rbd/iscsi/workloads/cephadm_iscsi.yaml")

affect_paths = {
    "qa/suites/rbd/iscsi/0-single-container-host.yaml",
    "qa/suites/rbd/iscsi/base/install.yaml",
    "qa/suites/rbd/iscsi/cluster/fixed-3.yaml",
    "qa/suites/rbd/iscsi/conf",
    "qa/suites/rbd/iscsi/pool/datapool.yaml",
    "qa/suites/rbd/iscsi/supported-random-distro$/centos_8.yaml",
    "qa/suites/rbd/iscsi/supported-random-distro$/rhel_8.yaml",
    "qa/suites/rbd/iscsi/workloads/cephadm_iscsi.yaml",
    "qa/tasks/ceph_iscsi.py",
    "qa/tasks/ceph_iscsi_client.py",
}
trivial_reasons = {
    "qa/suites/rbd/cli/workloads/rbd_support_module_recovery.yaml":
        "RADOS-QA-37: removes the standalone rbd_support recovery suite entry after equivalent blocklist-recovery checks are consolidated into cli_generic.sh; this row changes scheduling of QA coverage, not mgr/RBD runtime.",
    "qa/workunits/rbd/cli_generic.sh":
        "RADOS-QA-37: adds assertions for empty schedule output and blocklist visibility around existing rbd_support recovery cases; it is workunit coverage only and does not implement the scheduler/runtime fix.",
    "qa/workunits/rbd/rbd-nbd.sh":
        "RADOS-QA-37: adapts and expands rbd-nbd workunit coverage for snap-id, namespace, cookie, notrim, feature-disable and discard cases whose runtime deltas are classified elsewhere; the row is not installed data-path code.",
    "qa/workunits/rbd/rbd_support_module_recovery.sh":
        "RADOS-QA-37: deletes the standalone recovery workunit after its blocklist scenarios are covered in cli_generic.sh; production rbd_support module behavior is outside this row.",
    "qa/workunits/windows/test_rbd_wnbd.py":
        "RADOS-QA-37: adds a Windows WNBD functional/resize/FIO/stamp test harness; it materially improves coverage but is not part of the shipped WNBD mapper or driver runtime.",
}
assert len(affect_paths) == 10
assert len(trivial_reasons) == 5

impact_reason = (
    "RADOS-016: Quincy replaces the upstream RBD iSCSI QA path that installed "
    "ceph-iscsi/tcmu-runner on bare-metal gateway roles with a cephadm-managed "
    "gateway plus a client-only initiator task, and removes the old distro/"
    "datapool matrix. This changes what upstream validates for upgrades and "
    "leaves legacy package-based gateway transition outside the endpoint suite; "
    "it is validation evidence, not a claim that this QA file changes runtime."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
expected = affect_paths | set(trivial_reasons)
assert expected <= set(by_path)

for path in affect_paths:
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == "RADOS-016"
        assert row["impact_reason"] == impact_reason
    row["upgrade_impact"] = "affect"
    row["finding_id"] = "RADOS-016"
    row["impact_reason"] = impact_reason

for path, reason in trivial_reasons.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert (affect_count, trivial_count, blank_count) == (58, 262, 0)

replace_known(
    md_path,
    "**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./10-rados-rbd-clients.csv) có 320 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 48`, `trivial = 257`, **chưa phân loại = 15**; đây chưa phải binary gate hoàn tất.",
    "**Trạng thái: đã hoàn tất binary gate.** [CSV đầy đủ của owner](./10-rados-rbd-clients.csv) có 320 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Kết quả `affect = 58`, `trivial = 262`, **chưa phân loại = 0**; chưa có kết quả lab/runtime.",
)
replace_known(md_path, "257 hàng đã sàng lọc", "262 hàng đã sàng lọc")
replace_known(
    md_path,
    "Tiếp tục binary gate cho 15 hàng chưa phân loại; chỉ sau đó mới đối soát `affect + trivial = 320`.",
    "Binary gate đã đối soát đủ `58 affect + 262 trivial = 320`; tiếp theo là inventory As-Is và lab/canary cho các finding có điều kiện.",
)
replace_known(
    readme_path,
    "1.422 hàng `affect`. 1.494 hàng `trivial`. 1.263 hàng chưa phân loại.",
    "1.432 hàng `affect`. 1.499 hàng `trivial`. 1.248 hàng chưa phân loại.",
)
replace_known(readme_path, "RADOS-001–015", "RADOS-001–016", expected=2)
replace_known(
    readme_path,
    "deadlock `rbd-nbd` và bộ đếm benchmark",
    "deadlock `rbd-nbd`, bộ đếm benchmark và chuyển validation iSCSI sang cephadm",
    expected=2,
)
replace_known(readme_path, "vì 1.263 hàng còn thiếu nhãn và lý do",
              "vì 1.248 hàng còn thiếu nhãn và lý do")
replace_known(
    readme_path,
    "[owner 09](./09-ceph-volume-activation.md), [owner 12]",
    "[owner 09](./09-ceph-volume-activation.md), [owner 10](./10-rados-rbd-clients.md), [owner 12]",
)
replace_known(
    plan_path,
    "Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 12, 14 đã hoàn tất binary gate",
    "Owner 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 12, 14 đã hoàn tất binary gate",
)
replace_known(
    plan_path,
    "`affect 1.422`, `trivial 1.494`, còn **1.263 hàng chưa phân loại**",
    "`affect 1.432`, `trivial 1.499`, còn **1.248 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 10 hiện `48 affect`, `257 trivial`, `15` chưa phân loại",
    "owner 10 đã chốt `58 affect`, `262 trivial`, `0` chưa phân loại",
)

print("Classified owner-10 final QA batch: 10 affect, 5 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
