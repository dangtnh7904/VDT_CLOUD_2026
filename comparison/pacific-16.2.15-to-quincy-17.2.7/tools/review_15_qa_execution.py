"""Review remaining owner-15 QA rows against the Pacific-to-Quincy path."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "15-upgrade-validation.csv"
md_path = root / "15-upgrade-validation.md"
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


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected, (path, old, text.count(old))
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected, (path, new, text.count(new))


def insert_before_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if block in text:
        assert text.count(block) == 1
        return
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

# Upgrade suites and distro compositions were reviewed by the two preceding
# owner-15 scripts.  This is the stable remainder of the qa/ subtree.
excluded_prefixes = (
    "qa/suites/upgrade/",
    "qa/suites/upgrade-clients/",
    "qa/distros/",
)
qa_rows = [
    row
    for row in rows
    if row["path"].startswith("qa/")
    and not row["path"].startswith(excluded_prefixes)
]
assert len(qa_rows) == 65

affect = {
    "qa/crontab/teuthology-cronjobs": "VAL-005",
    "qa/machine_types/schedule_subset.sh": "VAL-005",
    "qa/tasks/ceph_manager.py": "VAL-004",
    "qa/tasks/workunit.py": "VAL-004",
}
assert affect.keys() <= {row["path"] for row in qa_rows}

diff_paths = set(
    git(
        "diff",
        "--no-renames",
        "--name-only",
        "v16.2.15",
        "v17.2.7",
        "--",
        "qa",
    ).stdout.splitlines()
)
assert {row["path"] for row in qa_rows} <= diff_paths

# Prove that the affected harness files are on the exact-pair execution graph.
exact_refs = git(
    "grep",
    "-n",
    "-E",
    r"(workunit:|thrashosds|ceph\.healthy)",
    "v17.2.7",
    "--",
    "qa/suites/upgrade/pacific-x",
).stdout
assert "workunit:" in exact_refs
assert "thrashosds" in exact_refs
assert "ceph.healthy" in exact_refs
cephadm = show("v17.2.7", "qa/tasks/cephadm.py")
assert "CephManager(" in cephadm

manager_base = show("v16.2.15", "qa/tasks/ceph_manager.py")
manager_target = show("v17.2.7", "qa/tasks/ceph_manager.py")
assert "chance_reset_purged_snaps_last" in manager_base
assert "chance_reset_purged_snaps_last" not in manager_target
assert "with parallel() as p:" not in manager_base
assert "with parallel() as p:" in manager_target
assert "['ceph-objectstore-tool', '--err-to-stderr']" in manager_target

workunit_base = show("v16.2.15", "qa/tasks/workunit.py")
workunit_target = show("v17.2.7", "qa/tasks/workunit.py")
assert "from teuthology.orchestra.run import CommandFailedError" in workunit_base
assert "from teuthology.exceptions import CommandFailedError" in workunit_target
assert "subdir=config.get('subdir')" not in workunit_base
assert "subdir=config.get('subdir')" in workunit_target

cron_base = show("v16.2.15", "qa/crontab/teuthology-cronjobs")
cron_target = show("v17.2.7", "qa/crontab/teuthology-cronjobs")
assert "SUITE_NAME=upgrade:pacific-x" not in cron_base
assert "SUITE_NAME=upgrade:pacific-x" in cron_target
assert "schedule_subset.sh 10" in cron_target

scheduler_base = show("v16.2.15", "qa/machine_types/schedule_subset.sh")
scheduler_target = show("v17.2.7", "qa/machine_types/schedule_subset.sh")
assert "date +%U" in scheduler_base
assert "RANDOM % partitions" in scheduler_target
assert "--newest 100" in scheduler_target

# The changed workunit bodies in this batch are not selected by Pacific-x.
changed_workunit_tokens = (
    "ceph-helpers-root",
    "cephtool/test",
    "cls/test_cls_cas",
    "cls/test_cls_cmpomap",
    "kernel_untar_build",
    "rest/test_mgr_rest_api",
    "suites/ffsb",
    "windows/run-tests",
)
for token in changed_workunit_tokens:
    result = git(
        "grep",
        "-F",
        token,
        "v17.2.7",
        "--",
        "qa/suites/upgrade/pacific-x",
        check=False,
    )
    assert result.returncode == 1 and not result.stdout, token

exact_install = show(
    "v17.2.7", "qa/suites/upgrade/pacific-x/parallel/1-tasks.yaml"
)
assert "exclude_packages:" in exact_install and "- ceph-volume" in exact_install
release_refs = git(
    "grep",
    "-F",
    "qa/releases/quincy",
    "v17.2.7",
    "--",
    "qa/suites/upgrade/pacific-x",
    check=False,
)
assert release_refs.returncode == 1 and not release_refs.stdout


def trivial_reason(path: str) -> str:
    if path.startswith(("qa/suites/smoke/", "qa/suites/perf-basic/")):
        return (
            "VAL-NONUPGRADE-SUITE: smoke/perf composition is not selected by "
            "qa/suites/upgrade/pacific-x; its test policy does not alter the "
            "exact Pacific-to-Quincy acceptance path."
        )
    if path.startswith("qa/standalone/"):
        return (
            "VAL-STANDALONE-01: standalone test/helper is not invoked by the "
            "Pacific-x suite; it changes independent developer QA, not this "
            "upgrade execution or verdict."
        )
    if path.startswith("qa/workunits/"):
        return (
            "VAL-WORKUNIT-UNSELECTED: the changed workunit body has no reference "
            "from qa/suites/upgrade/pacific-x; exact-pair workloads select other "
            "workunits."
        )
    if path.startswith("qa/tasks/"):
        return (
            "VAL-TASK-UNSELECTED: this task/test helper is not called on the "
            "Pacific-x composition path, or its changed branch is outside that "
            "path; no exact-pair execution effect was found."
        )
    if path == "qa/packages/packages.yaml":
        return (
            "VAL-QA-SUPPORT-01: the manifest adds ceph-volume, but Pacific-x "
            "explicitly excludes that package from the old install and upgrades "
            "through cephadm images; it is supporting packaging evidence only."
        )
    if path == "qa/releases/quincy.yaml":
        return (
            "VAL-QA-SUPPORT-01: release helper sets Quincy compatibility flags but "
            "has no reference from qa/suites/upgrade/pacific-x; the exact suite "
            "uses its own cephadm sequence."
        )
    return (
        "VAL-QA-SUPPORT-01: QA documentation, lint/import plumbing, xfstests, "
        "valgrind or unrelated override is outside the Pacific-x execution graph."
    )


for row in qa_rows:
    path = row["path"]
    finding_id = affect.get(path, "")
    if finding_id == "VAL-004":
        impact = "affect"
        reason = (
            "VAL-004: exact Pacific-x invokes workunit and cephadm constructs "
            "CephManager for health/OSD-thrash paths; these harness changes can "
            "alter command execution, timing or failure reporting."
        )
    elif finding_id == "VAL-005":
        impact = "affect"
        reason = (
            "VAL-005: target cron schedules upgrade:pacific-x through the changed "
            "random subset helper; coverage selection and reproducibility of the "
            "exact-pair gate therefore change."
        )
    else:
        impact = "trivial"
        reason = trivial_reason(path)

    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == impact
        assert row["finding_id"] == finding_id
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = impact
    row["finding_id"] = finding_id
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert (affect_count, trivial_count, blank_count) == (61, 311, 256)

replace_known(
    md_path,
    "Hiện `affect = 57`, `trivial = 250`, **chưa phân loại = 321**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 61`, `trivial = 311`, **chưa phân loại = 256**; binary gate của owner chưa hoàn tất.",
)

findings = """### VAL-004 — Harness task thay đổi đường chạy và tín hiệu lỗi của exact-pair suite

- **CSV:** `qa/tasks/ceph_manager.py` (index 1347) và `qa/tasks/workunit.py` (index 1425). **Nguồn:** composition `qa/suites/upgrade/pacific-x`, caller trong `cephadm.py`/`thrashosds.py`, endpoint hunk và commit context.
- **Trước → sau:** Exact suite gọi nhiều `workunit`, khởi tạo `CephManager` qua cephadm và chạy `ceph.healthy`/`thrashosds`. Quincy đổi nguồn `CommandFailedError`, truyền `subdir` vào runner, chuẩn hóa command/prefix theo cephadm, chạy `flush_pg_stats` song song, chuyển output lỗi của `ceph-objectstore-tool` sang stderr và bỏ action ngẫu nhiên `reset_purged_snaps_last` từng mặc định có xác suất 0,3.
- **Điều kiện và tác động:** Đây là thay đổi test harness, không phải binary production. Đường `subdir` chỉ hoạt động khi fixture đặt option đó, nhưng exception import, manager command path và việc bỏ thrasher action nằm ngay trên target suite; thời gian hoàn tất, loại stress và nguyên nhân fail/archive có thể khác Pacific. **Độ tin cậy:** cao cho call graph, chưa có archive chạy. **Kiểm chứng:** pin cùng phiên bản teuthology, expand job để lưu task/workunit list, so command log/thrasher action/timeline/exit status; chạy lại exact pair với timeout cố định và tách harness failure khỏi Ceph regression.

### VAL-005 — Lịch exact-pair chuyển sang một tập con ngẫu nhiên, khó tái lập coverage

- **CSV:** `qa/crontab/teuthology-cronjobs` (index 450) và `qa/machine_types/schedule_subset.sh` (index 514). **Nguồn:** endpoint cron, shell helper và commit `69567f16f32`/`1ef08db5756`.
- **Trước → sau:** Pacific chưa có cron `upgrade:pacific-x`; Quincy thêm job master hàng tuần gọi `schedule_subset.sh 10`. Helper cũ chọn partition theo tuần/ngày với mẫu xác định theo branch; helper mới chọn `RANDOM % partitions`, luôn thêm `--newest 100` và chuyển các đối số còn lại thẳng sang `teuthology-suite`. Vì vậy mỗi lần cron exact-pair chỉ chạy ngẫu nhiên một phần mười ma trận thay vì coverage có thể suy ra từ lịch.
- **Điều kiện và tác động:** Chỉ ảnh hưởng bằng chứng CI tự động; chạy thủ công full suite không phụ thuộc cron này. Job có thể pass nhưng bỏ sót tổ hợp distro/workload/upgrade-sequence khác, và rerun không bảo đảm lấy lại cùng tập con. **Độ tin cậy:** cao cho semantics script, chưa có scheduler history. **Kiểm chứng:** lưu expanded matrix cùng partition đã chọn, commit/image hash và teuthology version; chạy đủ 10 partition hoặc full matrix trước GO/NO-GO, rồi rerun đúng job IDs khi điều tra lỗi.

"""
insert_before_once(md_path, "## Thay đổi trivial đã sàng lọc", findings)

trivial_summary = """61 hàng QA còn lại được loại khỏi binary gate sau khi lần caller: 19 fixture `smoke`/`perf-basic` không được Pacific-x compose, 19 task/test helper không được gọi hoặc chỉ đổi nhánh ngoài exact path, năm test `standalone`, chín workunit có nội dung thay đổi nhưng không được suite chọn, và chín file support (README, xfstests, lint/import, valgrind, override/package/release helper). Riêng `qa/packages/packages.yaml` bổ sung `ceph-volume` là evidence cho PKG-001, nhưng exact suite chủ động `exclude_packages: ceph-volume` ở bước cài Pacific và nâng target bằng image cephadm; `qa/releases/quincy.yaml` cũng không có caller từ Pacific-x. Nhãn `trivial` ở đây chỉ có nghĩa không đổi execution/verdict của đúng cặp, không phủ nhận giá trị của các test đó với upstream QA.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", trivial_summary)

replace_known(
    readme_path,
    "1.718 hàng `affect`. 2.140 hàng `trivial`. 321 hàng chưa phân loại.",
    "1.722 hàng `affect`. 2.201 hàng `trivial`. 256 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 321 hàng còn thiếu nhãn và lý do", "vì 256 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[VAL-001–003]", "[VAL-001–005]")
replace_known(
    readme_path,
    "suite daemon/client và distro matrix đúng cặp Pacific→Quincy",
    "suite daemon/client, distro matrix, task executor và lịch chạy đúng cặp Pacific→Quincy",
)

replace_known(
    plan_path,
    "`affect 1.718`, `trivial 2.140`, còn **321 hàng chưa phân loại**.",
    "`affect 1.722`, `trivial 2.201`, còn **256 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 15 hiện `57 affect`, `250 trivial`, `321` chưa phân loại.",
    "owner 15 hiện `61 affect`, `311 trivial`, `256` chưa phân loại.",
)

global_affect = 0
global_trivial = 0
global_blank = 0
global_rows = 0
component_csvs = [
    path
    for path in sorted(root.glob("[0-1][0-9]-*.csv"))
    if not path.name.startswith("00-")
]
assert len(component_csvs) == 15
for component_csv in component_csvs:
    with component_csv.open(encoding="utf-8-sig", newline="") as stream:
        component_rows = list(csv.DictReader(stream, delimiter=";"))
    global_rows += len(component_rows)
    global_affect += sum(
        row["upgrade_impact"] == "affect" for row in component_rows
    )
    global_trivial += sum(
        row["upgrade_impact"] == "trivial" for row in component_rows
    )
    global_blank += sum(not row["upgrade_impact"] for row in component_rows)
assert (global_rows, global_affect, global_trivial, global_blank) == (
    4179,
    1722,
    2201,
    256,
)

print("Reviewed remaining owner-15 QA rows: 4 affect, 61 trivial")
print(
    f"Owner totals: affect={affect_count} trivial={trivial_count} "
    f"unclassified={blank_count}"
)
print(
    f"Suite totals: affect={global_affect} trivial={global_trivial} "
    f"unclassified={global_blank}"
)
