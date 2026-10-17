"""Review owner-15 QA distro definitions against the exact Pacific-x suites."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "15-upgrade-validation.csv"
md_path = root / "15-upgrade-validation.md"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
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
distro_rows = [row for row in rows if row["path"].startswith("qa/distros/")]
assert len(distro_rows) == 63
selected_rows = [row for row in distro_rows if row["path"].startswith("qa/distros/container-hosts/")]
assert len(selected_rows) == 8
selected_paths = {row["path"] for row in selected_rows}

diff_paths = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", "qa/distros").stdout.splitlines()
)
assert {row["path"] for row in distro_rows} <= diff_paths

# Both exact-pair Pacific-x scenarios select every composition in container-hosts.
parallel_distro = show("v17.2.7", "qa/suites/upgrade/pacific-x/parallel/0-random-distro$")
stress_distro = show("v17.2.7", "qa/suites/upgrade/pacific-x/stress-split/0-distro")
assert parallel_distro == ".qa/distros/container-hosts"
assert stress_distro == ".qa/distros/container-hosts"
base_hosts = set(git("ls-tree", "-r", "--name-only", "v16.2.15:qa/distros/container-hosts").stdout.splitlines())
target_hosts = set(git("ls-tree", "-r", "--name-only", "v17.2.7:qa/distros/container-hosts").stdout.splitlines())
assert base_hosts == {
    ".qa",
    "centos_8.stream_container_tools.yaml",
    "rhel_8.6_container_tools_3.0.yaml",
    "rhel_8.6_container_tools_rhel8.yaml",
    "ubuntu_18.04.yaml",
    "ubuntu_20.04.yaml",
}
assert target_hosts == {
    ".qa",
    "centos_8.stream_container_tools.yaml",
    "centos_8.stream_container_tools_crun.yaml",
    "rhel_8.4_container_tools_3.0.yaml",
    "rhel_8.4_container_tools_rhel8.yaml",
    "ubuntu_20.04.yaml",
}
crun = show("v17.2.7", "qa/distros/container-hosts/centos_8.stream_container_tools_crun.yaml")
assert 'runtime = "crun"' in crun and "module install container-tools" in crun
ubuntu_base = show("v16.2.15", "qa/distros/container-hosts/ubuntu_20.04.yaml")
ubuntu_target = show("v17.2.7", "qa/distros/container-hosts/ubuntu_20.04.yaml")
assert "hwe: true" in ubuntu_base and "hwe: true" not in ubuntu_target

for row in distro_rows:
    if row["path"] in selected_paths:
        impact = "affect"
        finding_id = "VAL-003"
        reason = (
            "VAL-003: exact Pacific-x suites select qa/distros/container-hosts; this row changes the OS/container-runtime matrix or host preparation used by those upgrade jobs."
        )
    else:
        impact = "trivial"
        finding_id = ""
        reason = (
            "VAL-DISTRO-01: distro definition is outside qa/distros/container-hosts selected by the exact Pacific-x suites; it changes other QA scheduling, not this pair's acceptance execution."
        )
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == impact
        assert row["finding_id"] == finding_id
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = impact
    row["finding_id"] = finding_id
    row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert (affect_count, trivial_count, blank_count) == (57, 250, 321)

replace_known(
    md_path,
    "Hiện `affect = 49`, `trivial = 195`, **chưa phân loại = 384**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 57`, `trivial = 250`, **chưa phân loại = 321**; binary gate của owner chưa hoàn tất.",
)

finding = """### VAL-003 — Distro/container-host matrix của suite exact-pair thay đổi

- **CSV:** tám hàng dưới `qa/distros/container-hosts/`. **Nguồn:** hai symlink composition của `qa/suites/upgrade/pacific-x/{parallel,stress-split}` đều trỏ tới đúng thư mục này; endpoint tree và YAML host preparation.
- **Trước → sau:** Matrix Pacific có CentOS 8 Stream, RHEL 8.6 với hai stream container-tools, Ubuntu 18.04 và Ubuntu 20.04 ép HWE kernel. Matrix Quincy bỏ RHEL 8.6/Ubuntu 18.04, dùng RHEL 8.4, thêm CentOS 8 Stream chạy `crun`, giữ bản `runc`, và Ubuntu 20.04 không còn ép HWE. Host setup còn reset/install container-tools với `--allowerasing --nobest` và bảo toàn registry config.
- **Điều kiện và tác động:** Chỉ ảnh hưởng môi trường thực thi acceptance suite, không đổi cluster binary. Kết quả pass/fail có thể khác do kernel, Podman/container-tools/runtime và distro package set; đặc biệt NVMe-loop từng là lý do ép HWE trên Ubuntu. Vì suite random/combinatorial lấy cả thư mục, việc thêm/xóa file đổi job matrix ngay cả khi YAML workload giữ nguyên. **Độ tin cậy:** cao cho composition, chưa có lịch sử job. **Kiểm chứng:** expand suite để lưu danh sách job thực, pin image/kernel/container runtime/package versions, chạy exact pair trên ít nhất Ubuntu 20.04 và CentOS Stream runc/crun; tách infrastructure failure khỏi Ceph regression và không coi một distro pass là phủ toàn matrix.

"""
insert_before_once(md_path, "## Thay đổi trivial đã sàng lọc", finding)
extra_trivial = """55 hàng distro còn lại (`qa/distros/all`, `podman`, root link và `single-container-host`) không nằm trong thư mục mà hai suite Pacific-x chọn. Phần lớn chỉ thêm `ktype: distro`, bổ sung Ubuntu 22.04 hoặc quản lý profile của suite khác; chúng được gắn `trivial` cho đúng cặp này, không phải tuyên bố vô nghĩa với toàn bộ upstream QA.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", extra_trivial)

replace_known(
    readme_path,
    "1.710 hàng `affect`. 2.085 hàng `trivial`. 384 hàng chưa phân loại.",
    "1.718 hàng `affect`. 2.140 hàng `trivial`. 321 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 384 hàng còn thiếu nhãn và lý do", "vì 321 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[VAL-001–002]", "[VAL-001–003]")
replace_known(
    readme_path,
    "suite daemon/client đúng cặp Pacific→Quincy",
    "suite daemon/client và distro matrix đúng cặp Pacific→Quincy",
)

replace_known(
    plan_path,
    "`affect 1.710`, `trivial 2.085`, còn **384 hàng chưa phân loại**.",
    "`affect 1.718`, `trivial 2.140`, còn **321 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 15 hiện `49 affect`, `195 trivial`, `384` chưa phân loại.",
    "owner 15 hiện `57 affect`, `250 trivial`, `321` chưa phân loại.",
)

global_affect = 0
global_trivial = 0
global_blank = 0
global_rows = 0
component_csvs = [
    path for path in sorted(root.glob("[0-1][0-9]-*.csv"))
    if not path.name.startswith("00-")
]
assert len(component_csvs) == 15
for component_csv in component_csvs:
    with component_csv.open(encoding="utf-8-sig", newline="") as stream:
        component_rows = list(csv.DictReader(stream, delimiter=";"))
    global_rows += len(component_rows)
    global_affect += sum(row["upgrade_impact"] == "affect" for row in component_rows)
    global_trivial += sum(row["upgrade_impact"] == "trivial" for row in component_rows)
    global_blank += sum(not row["upgrade_impact"] for row in component_rows)
assert (global_rows, global_affect, global_trivial, global_blank) == (4179, 1718, 2140, 321)

print("Reviewed owner-15 distro matrix: 8 exact-suite affect, 55 out-of-scope trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
print(f"Suite totals: affect={global_affect} trivial={global_trivial} unclassified={global_blank}")
