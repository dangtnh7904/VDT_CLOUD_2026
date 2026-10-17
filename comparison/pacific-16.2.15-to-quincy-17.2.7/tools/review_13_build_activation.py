"""Classify owner-13 build helpers, validation harnesses, and activation scripts."""

import csv
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
    "do_cmake.sh": (
        "PKG-007",
        "PKG-007: source-build helper switches its default generator to Ninja, always selects Python 3, and changes distro-specific interpreter/feature arguments.",
    ),
    "do_freebsd.sh": (
        "PKG-007",
        "PKG-007: FreeBSD source-build recipe now disables systemd explicitly, changing the generated artifact/install set for this supported build path.",
    ),
    "install-deps.sh": (
        "PKG-007",
        "PKG-007: dependency bootstrap changes Boost/pip baselines and uses Debian build profiles for Crimson/Jaeger plus revised RPM dependency handling.",
    ),
    "make-dist": (
        "PKG-007",
        "PKG-007: source distribution changes Node, Boost/liburing inputs, SUSE spec version handling, and adds the PMDK tar member used by downstream package builds.",
    ),
    "win32_deps_build.sh": (
        "PKG-007",
        "PKG-007: Windows dependency build advances curl and package prerequisites, changing the client artifact toolchain/dependency baseline.",
    ),
    "run-make-check.sh": (
        "PKG-008",
        "PKG-008: validation driver changes compiler/generator flags, ctest reporting, aio limit, and enables RBD SSD cache plus conditional RWL coverage.",
    ),
    "src/cstart.sh": (
        "PKG-008",
        "PKG-008: local cephadm harness persists ports/short IDs, forwards bootstrap arguments, and disables repo-digest lookup, changing test-cluster construction.",
    ),
    "src/mrun": (
        "PKG-008",
        "PKG-008: developer daemon runner adds a noname configuration layout and tightens shell tests, changing local harness path resolution only.",
    ),
    "src/stop.sh": (
        "PKG-008",
        "PKG-008: vstart teardown sends one SIGTERM, waits in stages, then SIGKILLs survivors; shutdown timing and cleanup signals differ in validation runs.",
    ),
    "src/vstart.sh": (
        "PKG-008",
        "PKG-008: vstart changes Crimson messenger/foreground defaults, store/device options, auth/manager module defaults and local service setup, altering lab topology and coverage.",
    ),
    "src/init-ceph.in": (
        "PKG-009",
        "PKG-009: legacy SysV activation creates /var/run/ceph before command dispatch and changes developer library/Python paths.",
    ),
    "systemd/CMakeLists.txt": (
        "PKG-009",
        "PKG-009: systemd unit install destination is discovered from pkg-config with a libdir fallback instead of the old libexec-derived cache path.",
    ),
    "src/ceph-crash.in": (
        "PKG-010",
        "PKG-010: crash collector now runs a 30-second ceph -s probe at startup to exercise its key before entering the scrape loop.",
    ),
    "src/ceph.in": (
        "PKG-010",
        "PKG-010: installed ceph CLI changes default config-list handling and partial help fallback; developer execution also composes preload/library paths differently.",
    ),
    "src/ceph_release": (
        "MSG-006",
        "MSG-006: build metadata changes release identity from Pacific 16 to stable Quincy 17, feeding generated version/release constants and CLI identity.",
    ),
}
assert len(affect) == 15
paths = set(affect)
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# PKG-007 source-build and distribution inputs.
target_cmake = show("v17.2.7", "do_cmake.sh")
assert 'ARGS="-GNinja"' in target_cmake
assert 'PYBUILD="3"' in target_cmake
assert "ARGS+=\" -DWITH_PYTHON3=${PYBUILD}\"" in target_cmake
assert "-D WITH_SYSTEMD=OFF" in show("v17.2.7", "do_freebsd.sh")
target_install_deps = show("v17.2.7", "install-deps.sh")
for marker in ("boost_ver=1.75", "pkg.ceph.crimson", "pkg.ceph.jaeger", "'pip >= 21.0'"):
    assert marker in target_install_deps
target_dist = show("v17.2.7", "make-dist")
for marker in ("--node=14.15.1", "boost_version=1.75.0", "$outfile.pmdk"):
    assert marker in target_dist
assert 'curlTag="curl-7_84_0"' in show("v17.2.7", "win32_deps_build.sh")

# PKG-008 validation-cluster construction and teardown.
target_check = show("v17.2.7", "run-make-check.sh")
for marker in ("-DCMAKE_CXX_FLAGS_DEBUG=-Werror", "-DWITH_RBD_SSD_CACHE=ON", "-DWITH_RBD_RWL=ON", "-T Test"):
    assert marker in target_check
target_cstart = show("v17.2.7", "src/cstart.sh")
assert "mgr/cephadm/use_repo_digest false" in target_cstart
assert "$@" in target_cstart
assert '[[ "$run_name" == "noname" ]]' in show("v17.2.7", "src/mrun")
target_stop = show("v17.2.7", "src/stop.sh")
assert "pkill -SIGTERM" in target_stop and "pkill -SIGKILL" in target_stop
target_vstart = show("v17.2.7", "src/vstart.sh")
for marker in ("--seastore", "ms mon client mode = crc", "mgr disabled modules = rook", "mon_data_avail_crit = 1"):
    assert marker in target_vstart

# PKG-009 installed service activation paths.
target_init = show("v17.2.7", "src/init-ceph.in")
assert "install -d -m0770 -o ceph -g ceph /var/run/ceph" in target_init
target_systemd = show("v17.2.7", "systemd/CMakeLists.txt")
assert 'pkg_get_variable(SYSTEMD_SYSTEM_UNIT_DIR "systemd" "systemd_system_unit_dir")' in target_systemd
assert "DESTINATION ${SYSTEMD_SYSTEM_UNIT_DIR}" in target_systemd

# PKG-010 operator CLI and crash collector startup.
target_crash = show("v17.2.7", "src/ceph-crash.in")
assert 'subprocess.Popen(args=[\'timeout\', \'30\', \'ceph\', \'-s\'])' in target_crash
target_ceph = show("v17.2.7", "src/ceph.in")
assert "conffile = rados.Rados.DEFAULT_CONF_FILES" in target_ceph
assert "shorten partial until we get at least one matching command prefix" in target_ceph

assert show("v16.2.15", "src/ceph_release").splitlines() == ["16", "pacific", "stable"]
assert show("v17.2.7", "src/ceph_release").splitlines() == ["17", "quincy", "stable"]
assert "### MSG-006 " in (root / "05-messaging-auth-common.md").read_text(encoding="utf-8-sig")

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

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert affect_count + trivial_count + blank_count == 207
assert (affect_count, trivial_count, blank_count) == (40, 39, 128)

replace_known(
    md_path,
    "Hiện `affect = 25`, `trivial = 39`, **chưa phân loại = 143**; binary gate của owner chưa hoàn tất.",
    "Hiện `affect = 40`, `trivial = 39`, **chưa phân loại = 128**; binary gate của owner chưa hoàn tất.",
)

findings = """### PKG-007 — Helper source-build và source tarball đổi toolchain/artifact baseline

- **CSV:** 81–82, 417–418, 4179. **Nguồn:** `do_cmake.sh`, `do_freebsd.sh`, `install-deps.sh`, `make-dist`, `win32_deps_build.sh` và commit intent trong superproject.
- **Trước → sau:** Helper mặc định chuyển sang Ninja/Python 3 và nhận diện Python distro mới; FreeBSD tắt systemd rõ ràng. Dependency bootstrap chuyển Boost 1.73 → 1.75, thêm build profiles Crimson/Jaeger và pip mới. Source tarball đổi Node/Boost/liburing, thêm PMDK member và xử lý version SUSE; Windows dependency build tăng curl 7.66 → 7.84 cùng prerequisite.
- **Điều kiện và tác động:** Chỉ áp dụng cho pipeline build từ source hoặc tarball/Windows, không cho host cài nguyên gói upstream. Nếu pipeline nội bộ tiếp tục cache dependency Pacific hoặc gọi `make` trực tiếp sau khi helper tạo Ninja build, artifact có thể thiếu/khác feature hoặc build thất bại; hai artifact cùng nhãn Quincy có thể khác provenance. **Độ tin cậy:** cao cho recipe, chưa build. **Kiểm chứng:** dựng source tarball và build sạch trên distro/architecture As-Is, lưu compiler/generator/CMake cache/SBOM/hash payload; kiểm PMDK, Python bindings, dashboard và Windows client; so với package upstream trước rollout.

### PKG-008 — Harness local/CI đổi topology và tín hiệu validation

- **CSV:** 1465, 1981, 2378, 3650, 4177. **Nguồn:** `run-make-check.sh`, `cstart.sh`, `mrun`, `stop.sh`, `vstart.sh`.
- **Trước → sau:** `run-make-check` chọn compiler/`-Werror`, đổi CTest reporting/aio limit và bật SSD cache cùng RWL có điều kiện. `vstart` đổi mặc định Crimson sang msgr2/foreground, thêm SeaStore/multi-device, tắt RESTful/Rook mặc định và đặt auth/MON thresholds; `cstart` thay bootstrap/digest behavior. Teardown mới gửi một SIGTERM, chờ theo giai đoạn rồi SIGKILL survivor thay vì lặp kill ngắn.
- **Điều kiện và tác động:** Đây là đường lab/CI, không tự đổi cluster production. Tuy nhiên kết quả test target không so trực tiếp được với Pacific nếu topology/module/cache/shutdown khác; lỗi chỉ xuất hiện ở RESTful, msgr1, abrupt stop hoặc cache tắt có thể bị bỏ qua. **Độ tin cậy:** cao cho harness, chưa chạy suite. **Kiểm chứng:** pin rõ mọi option khi chạy A/B, lưu `ceph config dump`, module list, messenger/store/cache và signal timeline; chạy thêm ma trận RESTful/msgr1/abrupt-kill tương ứng As-Is trước khi dùng pass target làm gate.

### PKG-009 — Vị trí unit systemd và bootstrap SysV thay đổi

- **CSV:** 2037, 4178. **Nguồn:** `systemd/CMakeLists.txt`, `src/init-ceph.in`; commit `8e49d3617012a70f037b506c99ddd0debd53a3e8` sửa default unit install dir và `bfbd279875f6395e203f17d2f22686f6f9ad9125` tạo run directory trước PID.
- **Trước → sau:** Pacific cài unit vào đường suy từ `CMAKE_INSTALL_LIBEXECDIR`; Quincy hỏi `pkg-config systemd_system_unit_dir`/tên cũ rồi fallback `${CMAKE_INSTALL_LIBDIR}/systemd/system`. SysV target tạo `/var/run/ceph` trước dispatch thay vì chỉ trong nhánh start và mở rộng path developer.
- **Điều kiện và tác động:** Gói distro chính thức thường override/manifest đúng, nhưng custom install/staging root có thể đặt unit sang đường khác; upgrade có thể để unit cũ và mới song song hoặc systemd không thấy file target. SysV chỉ áp dụng host còn dùng script legacy. **Độ tin cậy:** cao cho install/activation path, chưa cài gói. **Kiểm chứng:** cài vào staging root của từng distro, kiểm `systemd-analyze unit-path`, package ownership, daemon-reload/enable/start và file unit cũ còn sót; với SysV kiểm start/status khi `/var/run/ceph` chưa tồn tại và rollback.

### PKG-010 — CLI quản trị và crash collector đổi bootstrap

- **CSV:** 1496, 1518. **Nguồn:** `src/ceph-crash.in`, `src/ceph.in`; commits `9966aae66598b01c55907f2ec630113a34ff7363` và `38bfd044de5c3c7456eb9c5fcbc0702473c7bcc2`.
- **Trước → sau:** Crash collector Quincy chạy `timeout 30 ceph -s` sau khi drop privilege để buộc key được dùng rồi mới vào scrape loop; Pacific vào loop ngay. CLI target truyền `rados.Rados.DEFAULT_CONF_FILES` thay chuỗi rỗng và khi help partial không match sẽ rút ngắn prefix cho tới khi có lệnh; developer mode còn hợp nhất `LD_PRELOAD` cho ASAN/libc++.
- **Điều kiện và tác động:** Agent crash target có thể trễ tối đa 30 giây và phát auth/connect log khi key/config sai, nhưng probe failure không chặn loop. Automation dựa output help/config lookup của CLI có thể quan sát khác; đường preload chỉ cho build tree. Trong rolling upgrade đây là behavior theo host client/agent, không phải wire format. **Độ tin cậy:** cao cho control flow, chưa chạy service. **Kiểm chứng:** start `ceph-crash` với key hợp lệ, thiếu quyền và MON unreachable; đo readiness/scrape/log. Chạy CLI với `CEPH_ARGS`, `-c`, default config list và partial help ở hai tag; kiểm stdout/stderr/exit của automation.

`src/ceph_release` được gắn [MSG-006](./05-messaging-auth-common.md): build metadata đổi từ Pacific 16 sang stable Quincy 17, nhưng checkpoint persistent của MON/OSD vẫn phải đánh giá ở MON-001/002 chứ không suy chỉ từ chuỗi release.

"""
insert_before_once(md_path, "## Thay đổi trivial", findings)

replace_known(
    readme_path,
    "1.534 hàng `affect`. 1.874 hàng `trivial`. 771 hàng chưa phân loại.",
    "1.549 hàng `affect`. 1.874 hàng `trivial`. 756 hàng chưa phân loại.",
)
replace_known(readme_path, "vì 771 hàng còn thiếu nhãn và lý do", "vì 756 hàng còn thiếu nhãn và lý do")
replace_known(readme_path, "[PKG-001–006]", "[PKG-001–010]")
replace_known(
    readme_path,
    "source dependency/gitlink và corpus tương thích",
    "source dependency/gitlink, corpus tương thích, toolchain, harness và activation",
)
replace_known(
    plan_path,
    "`affect 1.534`, `trivial 1.874`, còn **771 hàng chưa phân loại**",
    "`affect 1.549`, `trivial 1.874`, còn **756 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 13 hiện `25 affect`, `39 trivial`, `143` chưa phân loại.",
    "owner 13 hiện `40 affect`, `39 trivial`, `128` chưa phân loại.",
)

print("Classified owner-13 build/validation/activation batch: 15 affect")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
