"""Classify owner-11 feature QA suites and workunits with no upgrade causal path."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "11-cephfs-mds.csv"
md_path = root / "11-cephfs-mds.md"
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


def ancestor(commit: str, ref: str) -> bool:
    return git("merge-base", "--is-ancestor", commit, ref, check=False).returncode == 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected


feature_suite_paths = {
    "qa/suites/fs/cephadm/multivolume/distro/centos_latest.yaml",
    "qa/suites/fs/cephadm/multivolume/distro/single-container-host.yaml",
    "qa/suites/fs/cephadm/renamevolume/%",
    "qa/suites/fs/cephadm/renamevolume/.qa",
    "qa/suites/fs/cephadm/renamevolume/0-start.yaml",
    "qa/suites/fs/cephadm/renamevolume/1-rename.yaml",
    "qa/suites/fs/cephadm/renamevolume/distro/.qa",
    "qa/suites/fs/cephadm/renamevolume/distro/single-container-host.yaml",
    "qa/suites/fs/cephadm/renamevolume/overrides/.qa",
    "qa/suites/fs/cephadm/renamevolume/overrides/ignorelist_health.yaml",
}

filter_paths = {
    "qa/suites/fs/functional/tasks/client-recovery.yaml",
    "qa/suites/fs/thrash/multifs/overrides/client-shutdown.yaml",
    "qa/suites/fs/thrash/workloads/overrides/client-shutdown.yaml",
}

subvolume_test_paths = {
    "qa/suites/fs/volumes/tasks/volume-client.yaml",
    "qa/suites/fs/volumes/tasks/volumes/test/basic.yaml",
    "qa/suites/fs/workload/subvolume/with-namespace-isolated-and-quota.yaml",
    "qa/suites/fs/workload/subvolume/with-namespace-isolated.yaml",
    "qa/suites/fs/workload/subvolume/with-no-extra-options.yaml",
    "qa/suites/fs/workload/subvolume/with-quota.yaml",
    "qa/workunits/fs/misc/subvolume.sh",
}

workunit_paths = {
    "qa/workunits/fs/damage/test-first-damage.sh",
    "qa/workunits/fs/misc/filelock_interrupt.py",
    "qa/workunits/fs/snaps/snaptest-git-ceph.sh",
}

paths = feature_suite_paths | filter_paths | subvolume_test_paths | workunit_paths
assert len(feature_suite_paths) == 10
assert len(filter_paths) == 3
assert len(subvolume_test_paths) == 7
assert len(workunit_paths) == 3
assert len(paths) == 23

# Inventory rename detection pairs several empty markers/symlinks with unrelated
# sources. Prove each endpoint path independently with rename detection disabled.
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

for commit in (
    "4e69fa871a2ee6967874347c5f7e5f3d0a8acc55",
    "99e63d3a5965680ebfd99e2b60c74123c0ac2cdf",
    "9c353b7ebff8b653225dabb16cb8f90f4e602910",
    "b7bb3343403f10c6a8cfb311b5befc9adce2eb7e",
    "41765a285861fbfd2610ba32e09cc8a54c640462",
    "81305b0da9a3e04633c022b12644e2975aa46a0d",
    "c160e972ab8b2f253cd147e4a02f1ade11f0d75a",
):
    assert ancestor(commit, "v17.2.7"), commit

assert "ceph fs volume rename foo bar --yes-i-really-mean-it" in show(
    "v17.2.7", "qa/suites/fs/cephadm/renamevolume/1-rename.yaml")
assert "single-container-host.yaml" in show(
    "v17.2.7", "qa/suites/fs/cephadm/multivolume/distro/single-container-host.yaml")
base_recovery = show("v16.2.15", "qa/suites/fs/functional/tasks/client-recovery.yaml")
target_recovery = show("v17.2.7", "qa/suites/fs/functional/tasks/client-recovery.yaml")
for warning in ("Degraded data redundancy", "MDS_CLIENTS_LAGGY", "Reduced data availability"):
    assert warning in base_recovery and warning not in target_recovery
for path in filter_paths - {"qa/suites/fs/functional/tasks/client-recovery.yaml"}:
    assert exists("v16.2.15", path) and not exists("v17.2.7", path)

assert exists("v16.2.15", "qa/suites/fs/volumes/tasks/volume-client.yaml")
assert not exists("v17.2.7", "qa/suites/fs/volumes/tasks/volume-client.yaml")
target_basic = show("v17.2.7", "qa/suites/fs/volumes/tasks/volumes/test/basic.yaml")
assert "tasks.cephfs.test_subvolume.TestSubvolume" not in target_basic
for path in subvolume_test_paths:
    if path == "qa/workunits/fs/misc/subvolume.sh":
        assert exists("v17.2.7", path)
    elif path != "qa/suites/fs/volumes/tasks/volumes/test/basic.yaml":
        assert exists("v16.2.15", path) and not exists("v17.2.7", path)
assert "ceph.dir.subvolume" in show("v17.2.7", "qa/workunits/fs/misc/subvolume.sh")

assert "cephfs-journal-tool" in show("v17.2.7", "qa/workunits/fs/damage/test-first-damage.sh")
assert 'setattr(fcntl, "F_OFD_SETLK", 37)' in show(
    "v17.2.7", "qa/workunits/fs/misc/filelock_interrupt.py")
snaptest = show("v17.2.7", "qa/workunits/fs/snaps/snaptest-git-ceph.sh")
assert "timeout 1800 git clone" in snaptest and "timeout 3600 git clone" in snaptest

reasons = {
    "FS-QA-06": (
        "FS-QA-06: endpoint delta only changes ordinary cephadm feature-test coverage: "
        "multivolume uses the recommended single-container host and a new suite exercises "
        "volume rename. It changes neither an upgrade recipe nor shipped MDS/client behavior."
    ),
    "FS-QA-07": (
        "FS-QA-07: client-recovery merely stops ignoring three health strings and the generic "
        "thrash suites drop a client_shutdown_timeout test override. These are non-upgrade QA "
        "filters/configuration and do not alter a production default or binary."
    ),
    "FS-QA-08": (
        "FS-QA-08: the legacy volume-client test is removed and subvolume feature coverage is "
        "moved/reverted between Python test fragments and a shell workunit. These files only "
        "exercise target behavior; the actual legacy upgrade-gate loss is FS-007."
    ),
    "FS-QA-09": (
        "FS-QA-09: added damage recovery coverage, a mypy-compatible fcntl constant assignment, "
        "and retry/timeout handling for a snapshot workunit are test-only changes with no "
        "independent upgrade execution, runtime, wire, or persistent-format effect."
    ),
}

cluster_for_path = {}
for path in feature_suite_paths:
    cluster_for_path[path] = "FS-QA-06"
for path in filter_paths:
    cluster_for_path[path] = "FS-QA-07"
for path in subvolume_test_paths:
    cluster_for_path[path] = "FS-QA-08"
for path in workunit_paths:
    cluster_for_path[path] = "FS-QA-09"
assert set(cluster_for_path) == paths

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)

for path, cluster in cluster_for_path.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "trivial"
        assert not row["finding_id"]
        assert row["impact_reason"] == reasons[cluster]

for path, cluster in cluster_for_path.items():
    row = by_path[path]
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = reasons[cluster]

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert affect_count + trivial_count + blank_count == 427
totals = (affect_count, trivial_count, blank_count)
assert totals in {(59, 77, 291), (59, 108, 260), (61, 115, 251)}
if totals != (59, 77, 291):
    print("Classified owner-11 CephFS QA support batch: 0 affect, 23 trivial")
    print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
    raise SystemExit(0)

replace_known(
    md_path,
    "`affect = 59`, `trivial = 54`, chưa phân loại = 314",
    "`affect = 59`, `trivial = 77`, chưa phân loại = 291",
)
replace_known(
    md_path,
    "**54 hàng** đã sàng lọc: 134 chỉ thêm anchor Sphinx; 619 và 622 chỉ đổi câu `print`; 50 hàng `FS-QA-04` đổi layout/ignorelist QA; hàng 1382 (`FS-QA-05`) chỉ bỏ test hỗ trợ cho legacy volume client, còn mất gate upgrade thực tế đã được giữ là `affect` trong FS-007.",
    "**77 hàng** đã sàng lọc: ngoài anchor/print và 50 hàng layout (`FS-QA-04`), hàng 1382 chỉ bỏ test hỗ trợ legacy volume client (`FS-QA-05`); 23 hàng `FS-QA-06–09` chỉ đổi feature suite, filter test, vị trí subvolume coverage hoặc độ bền workunit. Mất gate import legacy thực tế vẫn được giữ là `affect` trong FS-007.",
)
replace_known(md_path, "Phân loại 314 hàng còn trống", "Phân loại 291 hàng còn trống")
replace_known(
    readme_path,
    "1.484 hàng `affect`. 1.550 hàng `trivial`. 1.145 hàng chưa phân loại.",
    "1.484 hàng `affect`. 1.573 hàng `trivial`. 1.122 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 1.145 hàng còn thiếu nhãn và lý do", "vì 1.122 hàng còn thiếu nhãn và lý do")
replace_known(
    plan_path,
    "`affect 1.484`, `trivial 1.550`, còn **1.145 hàng chưa phân loại**",
    "`affect 1.484`, `trivial 1.573`, còn **1.122 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `59 affect`, `54 trivial`, `314` chưa phân loại",
    "owner 11 hiện `59 affect`, `77 trivial`, `291` chưa phân loại",
)

print("Classified owner-11 CephFS QA support batch: 0 affect, 23 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
