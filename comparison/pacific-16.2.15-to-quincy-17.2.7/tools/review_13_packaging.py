"""Classify the RPM/Debian package-manifest batch in owner 13."""

import csv
import re
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "13-build-packaging-submodules.csv"
md_path = root / "13-build-packaging-submodules.md"
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


affect = {
    "ceph.spec.in": (
        "PKG-001",
        "PKG-001: RPM packaging splits ceph-volume from ceph-osd and makes it a weak dependency; the same recipe also changes the shipped package/feature set, so an upgrade must verify that the deployment tool and its runtime dependencies are installed explicitly.",
    ),
    "debian/ceph-osd.install": (
        "PKG-001",
        "PKG-001: ceph-volume executables, Python modules, unit and man pages leave the ceph-osd payload in Quincy.",
    ),
    "debian/ceph-volume.install": (
        "PKG-001",
        "PKG-001: new manifest delivers the ceph-volume executables, Python modules, systemd unit and man pages as a separate binary package.",
    ),
    "debian/control": (
        "PKG-001",
        "PKG-001: defines ceph-volume as a separate package with disk-tool dependencies while ceph-osd only Recommends the exact-version package; also changes build/runtime dependency gates used by target artifacts.",
    ),
    "debian/ceph-mgr.install": (
        "PKG-002",
        "PKG-002: target ceph-mgr packaging adds object_format.py, which is imported by the target orchestrator module and installed by CMake.",
    ),
    "debian/python3-cephfs.install": (
        "FS-007",
        "FS-007: target python3-cephfs no longer ships ceph_volume_client.py, completing the package-level removal of the legacy API used by the removed upgrade recipe.",
    ),
    "debian/rules": (
        "PKG-003",
        "PKG-003: target Debian builds make Jaeger/Arrow profile-gated, force system utf8proc, enable RWL only on amd64, enable SSD cache, and alter shlib dependency scanning; shipped capabilities now depend on architecture/profile.",
    ),
}

trivial = {
    "debian/ceph-base.install": "PKG-MAN-01: removes only the obsolete ceph-deploy man page from the package manifest; no executable, unit, library or daemon activation changes in this row.",
    "debian/ceph-common.install": "PKG-MAN-01: adds the crushdiff executable and its man page as an additive diagnostic CLI; it does not change daemon activation, persistent state or protocol compatibility.",
    "debian/ceph-common.postinst": "PKG-MAN-01: shell commands are unchanged after removing comments and normalizing whitespace; the endpoint hunk is indentation/comment numbering plus an editor modeline.",
    "debian/ceph-test.install": "PKG-MAN-01: removes only ceph_kvstorebench from the test-tools package after LevelDB removal; production LevelDB impact is already captured by KV-001.",
    "debian/cephfs-shell.install": "PKG-MAN-01: adds only the cephfs-shell man page; executable/runtime payload is unchanged by this row.",
    "debian/libjaeger.install": "PKG-MAN-01: the deleted manifest contains only three commented placeholders and installs no file; actual tracing dependency/build changes are captured by MSG-047 and PKG-003.",
    "debian/python3-ceph-argparse.install": "PKG-MAN-01: removes dh-exec syntax and an explicit destination while retaining the same ceph_argparse.py and ceph_daemon.py payloads under the standard dist-packages path.",
}

paths = set(affect) | set(trivial)
assert len(paths) == 14
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# PKG-001: ceph-volume is moved out of ceph-osd in both native package recipes.
base_spec = show("v16.2.15", "ceph.spec.in")
target_spec = show("v17.2.7", "ceph.spec.in")
assert "%package volume" not in base_spec
assert "%package volume" in target_spec
assert re.search(r"Recommends:\s+ceph-volume", target_spec)
base_control = show("v16.2.15", "debian/control")
target_control = show("v17.2.7", "debian/control")
assert "Package: ceph-volume" not in base_control
assert "Package: ceph-volume" in target_control
assert "Recommends: ceph-volume (= ${binary:Version})" in target_control
base_osd = show("v16.2.15", "debian/ceph-osd.install")
target_osd = show("v17.2.7", "debian/ceph-osd.install")
target_volume = show("v17.2.7", "debian/ceph-volume.install")
for payload in ("usr/sbin/ceph-volume", "usr/lib/python*/dist-packages/ceph_volume/*"):
    assert payload in base_osd
    assert payload not in target_osd
    assert payload in target_volume

# PKG-002: target orchestrator imports a newly installed common formatter.
target_mgr_manifest = show("v17.2.7", "debian/ceph-mgr.install")
target_mgr_cmake = show("v17.2.7", "src/pybind/mgr/CMakeLists.txt")
target_orch = show("v17.2.7", "src/pybind/mgr/orchestrator/module.py")
assert "usr/share/ceph/mgr/object_format.*" in target_mgr_manifest
assert "mgr_module.py mgr_util.py object_format.py" in target_mgr_cmake
assert "from object_format import Format" in target_orch

# FS-007: package payload drops the legacy client module.
base_cephfs = show("v16.2.15", "debian/python3-cephfs.install")
target_cephfs = show("v17.2.7", "debian/python3-cephfs.install")
assert "ceph_volume_client.py" in base_cephfs
assert "ceph_volume_client.py" not in target_cephfs

# PKG-003: target build capability matrix is explicit and architecture/profile dependent.
base_rules = show("v16.2.15", "debian/rules")
target_rules = show("v17.2.7", "debian/rules")
assert "extraopts += -DWITH_RBD_RWL=ON" in base_rules
assert "ifeq ($(DEB_HOST_ARCH), amd64)" in target_rules
assert "extraopts += -DWITH_RBD_RWL=OFF" in target_rules
assert "extraopts += -DWITH_RBD_SSD_CACHE=ON" in target_rules
assert "pkg.ceph.jaeger" in target_rules
assert "-DWITH_SYSTEM_UTF8PROC=ON" in target_rules

# Trivial guards validate the exact manifest-only/support nature of this batch.
assert "usr/share/man/man8/ceph-deploy.8" in show("v16.2.15", "debian/ceph-base.install")
assert "usr/share/man/man8/ceph-deploy.8" not in show("v17.2.7", "debian/ceph-base.install")
common_diff = git("diff", "--unified=0", "v16.2.15", "v17.2.7", "--", "debian/ceph-common.install").stdout
assert common_diff.count("+usr/bin/crushdiff") == 1
assert common_diff.count("+usr/share/man/man8/crushdiff.8") == 1
base_libjaeger = show("v16.2.15", "debian/libjaeger.install")
assert all(not line.strip() or line.lstrip().startswith("#") for line in base_libjaeger.splitlines())
base_argparse = show("v16.2.15", "debian/python3-ceph-argparse.install")
target_argparse = show("v17.2.7", "debian/python3-ceph-argparse.install")
for payload in ("ceph_argparse.py", "ceph_daemon.py"):
    assert payload in base_argparse and payload in target_argparse


def normalized_shell(text: str) -> str:
    # This endpoint hunk moves ``then`` onto the preceding ``if`` line and
    # reformats continuation indentation. Treat those spellings identically
    # while preserving every command/token used by the maintainer script.
    text = text.replace("; then", "\nthen").replace("\\\n", " ")
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return " ".join(" ".join(lines).split())


assert normalized_shell(show("v16.2.15", "debian/ceph-common.postinst")) == normalized_shell(
    show("v17.2.7", "debian/ceph-common.postinst")
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)
for path, (finding_id, reason) in affect.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding_id
        assert row["impact_reason"] == reason
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding_id
    row["impact_reason"] = reason
for path, reason in trivial.items():
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
assert affect_count + trivial_count + blank_count == 207
assert (affect_count, trivial_count, blank_count) == (11, 26, 170)

replace_known(
    md_path,
    "Hiện `affect = 4`, `trivial = 19`, **chưa phân loại = 184**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 11`, `trivial = 26`, **chưa phân loại = 170**; binary gate của owner chưa hoàn tất.",
)
replace_known(
    md_path,
    "Các hunk CMake khác và 203 hàng còn lại vẫn cần review.",
    "Các hunk CMake, dependency, CI và systemd còn lại vẫn cần review.",
)

findings = """### PKG-001 — `ceph-volume` tách khỏi gói OSD và trở thành weak dependency

- **CSV:** 22, 71, 73, 76. **Nguồn:** `ceph.spec.in`, `debian/{control,ceph-osd.install,ceph-volume.install}`; commits `8e0e9ef382c5749954eb416107e4a7d22f92d41c` (RPM) và `c6c260f15beec0f3669d611892d1d7e579a819f0` (Debian) nêu mục tiêu tách gói, trong đó commit Debian nói rõ dùng `Recommends` để người dùng hiện hữu nhận gói khi nâng cấp.
- **Trước → sau:** Pacific đặt binary, Python module, systemd unit và man page của `ceph-volume` trong payload `ceph-osd`; các dependency đĩa cũng nằm rải ở `ceph-base`/`ceph-osd`. Quincy tạo gói `ceph-volume` riêng, chuyển toàn bộ payload và dependency `cryptsetup-bin`, `e2fsprogs`, `lvm2`, `parted`, `util-linux`, `xfsprogs` sang đó. `ceph-osd` chỉ `Recommends` đúng version ở Debian và dùng weak `Recommends` trong RPM.
- **Điều kiện và tác động:** Host nâng bằng package manager có cài recommended/weak dependencies sẽ nhận gói mới; môi trường dùng `--no-install-recommends`, tắt weak deps, mirror/allowlist gói hẹp hoặc custom repo có thể nâng `ceph-osd` nhưng thiếu `ceph-volume`, unit và runtime disk tools. OSD đang chạy không tự mất dữ liệu, nhưng prepare/activate/zap/replacement sau nâng cấp có thể không còn công cụ. Trong rolling upgrade, host Pacific lấy tool từ `ceph-osd`, host Quincy cần gói mới; rollback phải khôi phục ownership package cũ và không để dependency solver gỡ nhầm công cụ. **Độ tin cậy:** cao cho recipe/commit, chưa kiểm repo thực tế. **Kiểm chứng:** mô phỏng upgrade RPM và Debian với weak deps bật/tắt, kiểm `ceph-volume --version`, Python import, unit file, dependency và thao tác inventory/activate trên disk lab; đối chiếu mirror/allowlist As-Is.

### PKG-002 — Gói `ceph-mgr` phải mang theo `object_format.py`

- **CSV:** 70. **Nguồn:** `debian/ceph-mgr.install`, `src/pybind/mgr/CMakeLists.txt` và import tại `src/pybind/mgr/orchestrator/module.py`; commit `95f75809425d3a26ac07c4fd5abb14adfa7d8d2e` mô tả file đã bị bỏ sót ở Debian sau khi RPM packaging được thêm.
- **Trước → sau:** Pacific định nghĩa `Format` ngay trong orchestrator module. Quincy chuyển nó sang module dùng chung `object_format.py`, CMake cài file này và manifest Debian phải thêm `usr/share/ceph/mgr/object_format.*`. Đây là dependency import runtime, không phải tài liệu package.
- **Điều kiện và tác động:** Gói upstream target có manifest sửa đúng; rủi ro nằm ở custom packaging/backport hoặc allowlist chỉ sao chép manifest cũ. Khi đó `ceph-mgr` có thể import orchestrator thất bại ngay sau restart/failover trong rolling upgrade. RPM dùng file selection rộng hơn nên cần xác nhận payload thay vì giả định tương đương. **Độ tin cậy:** cao cho import/install chain, chưa cài gói. **Kiểm chứng:** build/install package target vào image sạch, kiểm file và `python3` import theo `mgr_module_path`, bật orchestrator rồi restart/failover MGR; lặp với pipeline package nội bộ.

### PKG-003 — Ma trận tính năng Debian phụ thuộc architecture và build profile

- **CSV:** 80. **Nguồn:** `debian/rules`; liên quan [RADOS-002–003](./10-rados-rbd-clients.md) và [MSG-047](./05-messaging-auth-common.md).
- **Trước → sau:** Pacific bật `WITH_RBD_RWL=ON` không phân nhánh architecture. Quincy chỉ bật RWL trên `amd64`, tắt ở architecture khác, bật `WITH_RBD_SSD_CACHE=ON`, ép system `utf8proc`, và chỉ bật Jaeger/Arrow khi có build profile tương ứng; `ceph_crypto` cũng bị loại khỏi quét `dh_shlibdeps` như plugin khác.
- **Điều kiện và tác động:** Áp dụng cho gói Debian dựng từ source, đặc biệt arm64/ppc64, pipeline dùng build profile tùy chỉnh hoặc image kỳ vọng tracing/PWL plugin. Hai host khác architecture/profile có thể có capability khác dù cùng version; cấu hình RWL/tracing hiện hữu phải được so với artifact thực, không chỉ version package. Đây là thay đổi delivery/build, không khẳng định format cache đổi. **Độ tin cậy:** cao cho build flags, trung bình cho deployment. **Kiểm chứng:** lưu CMake cache và danh sách `.so`/dependencies theo từng architecture/profile, smoke-test mở image có cache cấu hình và bật tracing collector; kiểm rollback bằng artifact Pacific tương ứng.

`debian/python3-cephfs.install` còn được gắn [FS-007](./11-cephfs-mds.md): target không còn ship `ceph_volume_client.py`, nên inventory Manila/automation phải kiểm package/import chứ không chỉ nhìn source bị xóa.

"""
insert_before_once(md_path, "## Thay đổi trivial", findings)
replace_known(
    md_path,
    "19 hàng `PKG-DOC-01` đã được đọc theo endpoint: contributor ownership/identity, PR template, license/style và tài liệu build/install/troubleshooting chỉ đổi metadata hoặc hướng dẫn cho con người. `doc/man/8/CMakeLists.txt` chỉ đổi tập RST được sinh thành man page, không build/activate daemon hay thư viện. Các hunk packaging, dependency và CI còn lại chưa được suy thành `trivial` từ đường dẫn.",
    "26 hàng đã được đọc theo endpoint. Ngoài 19 hàng `PKG-DOC-01`, bảy hàng `PKG-MAN-01` chỉ đổi man page/additive CLI, comment/indent, test benchmark hoặc cú pháp manifest tương đương; deletion `debian/libjaeger.install` chỉ bỏ ba dòng comment và không từng cài artifact. Những thay đổi package có đường delivery/runtime thực được giữ `affect` ở PKG-001–003, FS-007 hoặc cross-reference liên quan.",
)

replace_known(
    readme_path,
    "1.513 hàng `affect`. 1.854 hàng `trivial`. 812 hàng chưa phân loại.",
    "1.520 hàng `affect`. 1.861 hàng `trivial`. 798 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 812 hàng còn thiếu nhãn và lý do", "vì 798 hàng còn thiếu nhãn và lý do")
replace_known(
    readme_path,
    "; [VOL-001–003](./09-ceph-volume-activation.md) cho inventory, encrypted zap và tox gate; [FS-001–017]",
    "; [VOL-001–003](./09-ceph-volume-activation.md) cho inventory, encrypted zap và tox gate; [PKG-001–003](./13-build-packaging-submodules.md) cho split `ceph-volume`, payload MGR và ma trận build Debian; [FS-001–017]",
)
replace_known(
    plan_path,
    "`affect 1.513`, `trivial 1.854`, còn **812 hàng chưa phân loại**",
    "`affect 1.520`, `trivial 1.861`, còn **798 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 13 hiện `4 affect`, `19 trivial`, `184` chưa phân loại.",
    "owner 13 hiện `11 affect`, `26 trivial`, `170` chưa phân loại.",
)

print("Classified owner-13 native packaging batch: 7 affect, 7 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
