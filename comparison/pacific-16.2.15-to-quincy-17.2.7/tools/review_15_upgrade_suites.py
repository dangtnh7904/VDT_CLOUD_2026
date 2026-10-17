"""Review owner-15 daemon/client upgrade-suite topology for the exact release pair."""

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


def exists(tag: str, path: str) -> bool:
    return git("cat-file", "-e", f"{tag}:{path}", check=False).returncode == 0


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
    assert text.count(marker) == 1, (path, marker, text.count(marker))
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert len(rows) == 628

daemon_rows = [row for row in rows if row["path"].startswith("qa/suites/upgrade/")]
client_rows = [row for row in rows if row["path"].startswith("qa/suites/upgrade-clients/")]
assert len(daemon_rows) == 216
assert len(client_rows) == 28

daemon_affect = [
    row for row in daemon_rows
    if row["path"].startswith("qa/suites/upgrade/pacific-x/")
]
client_affect = [
    row for row in client_rows
    if row["path"].startswith("qa/suites/upgrade-clients/client-upgrade-pacific-quincy/")
    or row["old_path"].startswith("qa/suites/upgrade-clients/client-upgrade-pacific-quincy/")
]
assert len(daemon_affect) == 38
assert len(client_affect) == 11

review_rows = daemon_rows + client_rows
review_paths = {row["path"] for row in review_rows}
assert len(review_rows) == len(review_paths) == 244
diff_paths = set(
    git(
        "diff",
        "--no-renames",
        "--name-only",
        "v16.2.15",
        "v17.2.7",
        "--",
        "qa/suites/upgrade",
        "qa/suites/upgrade-clients",
    ).stdout.splitlines()
)
assert review_paths <= diff_paths, sorted(review_paths - diff_paths)

# Guard the endpoint suite transition and representative execution semantics.
base_upgrade_roots = set(git("ls-tree", "-d", "--name-only", "v16.2.15:qa/suites/upgrade").stdout.splitlines())
target_upgrade_roots = set(git("ls-tree", "-d", "--name-only", "v17.2.7:qa/suites/upgrade").stdout.splitlines())
assert base_upgrade_roots == {"nautilus-x-singleton", "nautilus-x", "octopus-x", "pacific-p2p"}
assert target_upgrade_roots == {"octopus-x", "pacific-x", "quincy-p2p"}
parallel = show("v17.2.7", "qa/suites/upgrade/pacific-x/parallel/upgrade-sequence.yaml")
assert "ceph orch upgrade start" in parallel
assert "ceph versions | jq -e '.overall | length == 1'" in parallel
stress = show("v17.2.7", "qa/suites/upgrade/pacific-x/stress-split/1-start.yaml")
assert "upgrading first half of cluster" in stress
assert "ceph orch upgrade pause" in stress and "ceph orch upgrade resume" in stress
assert "wait for half of osds to upgrade" in stress

base_client_roots = set(git("ls-tree", "-d", "--name-only", "v16.2.15:qa/suites/upgrade-clients").stdout.splitlines())
target_client_roots = set(git("ls-tree", "-d", "--name-only", "v17.2.7:qa/suites/upgrade-clients").stdout.splitlines())
assert base_client_roots == {"client-upgrade-pacific-quincy", "client-upgrade-pacific-reef"}
assert target_client_roots == {"client-upgrade-quincy-reef"}
assert exists("v16.2.15", "qa/suites/upgrade-clients/client-upgrade-pacific-quincy")
assert not exists("v17.2.7", "qa/suites/upgrade-clients/client-upgrade-pacific-quincy")
base_client_install = show(
    "v16.2.15",
    "qa/suites/upgrade-clients/client-upgrade-pacific-quincy/pacific-client-x/rbd/1-install/pacific-client-x.yaml",
)
assert "branch: pacific" in base_client_install and "install.upgrade" in base_client_install
target_client_install = show(
    "v17.2.7",
    "qa/suites/upgrade-clients/client-upgrade-quincy-reef/quincy-client-x/rbd/1-install/quincy-client-x.yaml",
)
assert "branch: quincy" in target_client_install and "install.upgrade" in target_client_install

daemon_affect_paths = {row["path"] for row in daemon_affect}
client_affect_paths = {row["path"] for row in client_affect}
for row in review_rows:
    path = row["path"]
    if path in daemon_affect_paths:
        finding_id = "VAL-001"
        impact = "affect"
        reason = (
            "VAL-001: exact Pacific-to-target daemon suite composes cephadm parallel/stress-split upgrades, pauses at mixed MON/OSD states and runs workloads/health gates."
        )
    elif path in client_affect_paths:
        finding_id = "VAL-002"
        impact = "affect"
        reason = (
            "VAL-002: exact Pacific-to-Quincy client/RBD acceptance fixture is deleted or repurposed into Quincy-to-Reef, removing native pair coverage from the target checkout."
        )
    elif path.startswith("qa/suites/upgrade-clients/"):
        finding_id = ""
        impact = "trivial"
        reason = (
            "VAL-NONPAIR-02: client-upgrade row covers Pacific-to-Reef or Quincy-to-Reef and has no old_path from the exact Pacific-to-Quincy suite; it is outside this endpoint pair's acceptance path."
        )
    else:
        finding_id = ""
        impact = "trivial"
        reason = (
            "VAL-NONPAIR-01: daemon suite row covers Nautilus/Octopus major upgrades or Pacific/Quincy point-release testing, not the exact Pacific-16.2.15-to-Quincy-17.2.7 acceptance path."
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
assert (affect_count, trivial_count, blank_count) == (49, 195, 384)

replace_known(
    md_path,
    "**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./15-upgrade-validation.csv) có 628 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 0`, `trivial = 0`, **chưa phân loại = 628**; các số 0 không phải kết luận không có tác động.",
    "**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./15-upgrade-validation.csv) có 628 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 49`, `trivial = 195`, **chưa phân loại = 384**; binary gate của owner chưa hoàn tất.",
)

findings = """### VAL-001 — Suite daemon Pacific→Quincy mới kiểm mixed state qua cephadm

- **CSV:** 38 hàng dưới `qa/suites/upgrade/pacific-x/`. **Nguồn:** endpoint suite composition và commit history; target thêm `parallel`/`stress-split`, trong khi base không có root `pacific-x`.
- **Trước → sau:** Checkout Pacific có các root Nautilus/Octopus và Pacific point-release, nhưng không có suite major `pacific-x`. Quincy tạo suite bắt đầu từ branch Pacific, dùng `ceph orch upgrade start` tới target SHA, kiểm `ceph versions`, và ở stress-split chủ động pause/resume sau minority/majority MON rồi nửa OSD; workload RADOS/RBD, MDS và OSD thrash chạy quanh trạng thái mixed-version. Suite cũng loại `ceph-volume` khỏi bước cài Pacific do package split.
- **Điều kiện và tác động:** Đây là acceptance/CI, không chạy trên cluster production. Nó cung cấp đúng đường major upgrade gần cặp đang phân tích nhưng dùng branch name `pacific` và target `sha1`, không tự chứng minh đã chạy chính xác tag 16.2.15→17.2.7. Coverage thiên về cephadm; manual package/systemd, rollback, store clone và workload As-Is vẫn thiếu. **Độ tin cậy:** cao cho topology/commands, chưa có run result. **Kiểm chứng:** pin image/hash đúng hai endpoint, chạy cả parallel và stress-split, lưu archive/JUnit/version timeline/health, buộc canary mixed MON/OSD/MDS/MGR, và bổ sung rollback cùng package path ngoài cephadm.

### VAL-002 — Target checkout không còn suite client Pacific→Quincy nguyên bản

- **CSV:** 11 hàng có `path` hoặc `old_path` dưới `client-upgrade-pacific-quincy`; gồm sáu file xóa và năm fixture bị chuyển sang `client-upgrade-quincy-reef`. **Nguồn:** endpoint tree, rename metadata và YAML install/workload.
- **Trước → sau:** Pacific giữ suite client/RBD cài branch Pacific rồi `install.upgrade` một client sang nhánh kế tiếp, kèm cluster start, distro và notification workload. Quincy bỏ root exact-pair này và tái sử dụng một phần topology cho Quincy→Reef; target tree chỉ còn `client-upgrade-quincy-reef`. Vì vậy checkout target không có gate native để tái chạy riêng client Pacific→Quincy.
- **Điều kiện và tác động:** Chỉ ảnh hưởng bằng chứng acceptance cho host client nâng độc lập, đặc biệt RBD notification/API khi cluster và client không cùng version; không đổi binary production. Thiếu suite không chứng minh incompatibility, nhưng một pass của target CI không bao phủ cặp client cần rollout. **Độ tin cậy:** cao cho mất coverage, chưa chạy suite khôi phục. **Kiểm chứng:** phục dựng fixture exact-pair với package/image pin 16.2.15 và 17.2.7, chạy client-old/cluster-new và client-new/cluster-old, kiểm map/I/O/notification/reconnect/rollback, lưu package list và kết quả theo từng hướng.

"""
replace_known(
    md_path,
    "Chưa có finding được xác minh đủ hunk, symbol hai endpoint, commit, test và điều kiện áp dụng để công bố. Các hàng `upgrade_impact` để trống cho tới khi đọc diff/metadata thực tế; không gán `trivial` theo đường dẫn.\n\n",
    findings,
)

trivial_section = """## Thay đổi trivial đã sàng lọc

195 hàng suite ngoài đúng cặp endpoint đã được đọc theo endpoint/rename topology: 178 hàng daemon thuộc Nautilus/Octopus major upgrade hoặc Pacific/Quincy point-release, và 17 hàng client thuộc Pacific→Reef hoặc Quincy→Reef mà không có `old_path` từ suite Pacific→Quincy. Chúng vẫn có giá trị cho upstream release QA, nhưng không tạo execution/acceptance signal cho đúng đường 16.2.15→17.2.7. Các fixture exact-pair được giữ `affect` ở VAL-001/002, kể cả symlink/composition file `0/0` vì chúng quyết định ma trận có được chạy hay không.

"""
insert_before_once(md_path, "## Kiểm chứng cần hoàn thành", trivial_section)

replace_known(
    readme_path,
    "1.661 hàng `affect`. 1.890 hàng `trivial`. 628 hàng chưa phân loại.",
    "1.710 hàng `affect`. 2.085 hàng `trivial`. 384 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 628 hàng còn thiếu nhãn và lý do", "vì 384 hàng còn thiếu nhãn và lý do")
replace_known(
    readme_path,
    "Dokan build; [FS-001–017](./11-cephfs-mds.md)",
    "Dokan build; [VAL-001–002](./15-upgrade-validation.md) cho suite daemon/client đúng cặp Pacific→Quincy; [FS-001–017](./11-cephfs-mds.md)",
)

replace_known(
    plan_path,
    "`affect 1.661`, `trivial 1.890`, còn **628 hàng chưa phân loại**.",
    "`affect 1.710`, `trivial 2.085`, còn **384 hàng chưa phân loại**.",
)
replace_known(
    plan_path,
    "owner 13 đã chốt `152 affect`, `55 trivial`, `0` chưa phân loại.",
    "owner 13 đã chốt `152 affect`, `55 trivial`, `0` chưa phân loại; owner 15 hiện `49 affect`, `195 trivial`, `384` chưa phân loại.",
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
assert (global_rows, global_affect, global_trivial, global_blank) == (4179, 1710, 2085, 384)

print("Reviewed owner-15 upgrade suites: 49 exact-pair affect, 195 non-pair trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
print(f"Suite totals: affect={global_affect} trivial={global_trivial} unclassified={global_blank}")
