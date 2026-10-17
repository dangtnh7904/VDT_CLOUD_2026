# 13 — build, package, dependency, gitlink và systemd: v16.2.15 → v17.2.7

**Trạng thái: đã hoàn tất binary gate; kiểm chứng artifact/lab còn mở.** [CSV đầy đủ của owner](./13-build-packaging-submodules.csv) có 207 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Đã đối soát `affect = 152`, `trivial = 55`, **chưa phân loại = 0**.

## Phạm vi và phương pháp

Owner này phụ trách build, package, dependency, gitlink và systemd. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

`src/kv/CMakeLists.txt` đã được gắn `affect` và map tới [KV-001](./03-rocksdb-block-device.md): target bỏ compile/link LevelDB, phối hợp với factory và implementation bị xóa. `src/rgw/CMakeLists.txt` cũng được gắn `affect` và map tới [RGW-002](./12-rgw.md): target thêm `rgw_bucket_encryption.cc` vào `librgw_common_srcs`, khiến parser/schema bucket encryption mới được build cùng RGW. File này còn bỏ source/link FastCGI, các source/header/link Civetweb và thêm `rgw_rest_info.cc`/`rgw_rest_ratelimit.cc` cho Admin API mới; hiệu ứng runtime xem [CFG-008](./06-config-defaults.md), [RGW-004–006](./12-rgw.md). `CMakeLists.txt` gốc bỏ `WITH_RADOSGW_FCGI_FRONTEND` và `find_package(fcgi)`, còn `cmake/modules/Findfcgi.cmake` bị xóa. Hai hàng build mới gắn `affect` và trỏ CFG-008. Owner 13 giữ hunk build trong CSV riêng để partition không trùng. Toàn bộ hunk build, package, dependency, CI, systemd và helper source còn lại đã được đọc và gắn binary impact.

### PKG-001 — `ceph-volume` tách khỏi gói OSD và trở thành weak dependency

- **CSV:** 22, 71, 73, 76. **Nguồn:** `ceph.spec.in`, `debian/{control,ceph-osd.install,ceph-volume.install}`; commits `8e0e9ef382c5749954eb416107e4a7d22f92d41c` (RPM) và `c6c260f15beec0f3669d611892d1d7e579a819f0` (Debian) nêu mục tiêu tách gói, trong đó commit Debian nói rõ dùng `Recommends` để người dùng hiện hữu nhận gói khi nâng cấp.
- **Trước → sau:** Pacific đặt binary, Python module, systemd unit và man page của `ceph-volume` trong payload `ceph-osd`; các dependency đĩa cũng nằm rải ở `ceph-base`/`ceph-osd`. Quincy tạo gói `ceph-volume` riêng, chuyển toàn bộ payload và dependency `cryptsetup-bin`, `e2fsprogs`, `lvm2`, `parted`, `util-linux`, `xfsprogs` sang đó. `ceph-osd` chỉ `Recommends` đúng version ở Debian và dùng weak `Recommends` trong RPM.
- **Điều kiện và tác động:** Host nâng bằng package manager có cài recommended/weak dependencies sẽ nhận gói mới; môi trường dùng `--no-install-recommends`, tắt weak deps, mirror/allowlist gói hẹp hoặc custom repo có thể nâng `ceph-osd` nhưng thiếu `ceph-volume`, unit và runtime disk tools. OSD đang chạy không tự mất dữ liệu, nhưng prepare/activate/zap/replacement sau nâng cấp có thể không còn công cụ. Trong rolling upgrade, host Pacific lấy tool từ `ceph-osd`, host Quincy cần gói mới; rollback phải khôi phục ownership package cũ và không để dependency solver gỡ nhầm công cụ. **Độ tin cậy:** cao cho recipe/commit, chưa kiểm repo thực tế. **Kiểm chứng:** mô phỏng upgrade RPM và Debian với weak deps bật/tắt, kiểm `ceph-volume --version`, Python import, unit file, dependency và thao tác inventory/activate trên disk lab; đối chiếu mirror/allowlist As-Is.

**Activation PKG-001:** split payload có hiệu lực tự động trong package transaction, không phải khi daemon đang chạy tự tách file. Cần pin riêng `ceph-volume` và disk-tool closure trong manifest cài đặt trước restart; probe inventory chỉ đọc xác nhận tool đã sẵn sàng, còn activation của OSD phải tuân theo storage-format gate ở owner 02.

### PKG-002 — Gói `ceph-mgr` phải mang theo `object_format.py`

- **CSV:** 70. **Nguồn:** `debian/ceph-mgr.install`, `src/pybind/mgr/CMakeLists.txt` và import tại `src/pybind/mgr/orchestrator/module.py`; commit `95f75809425d3a26ac07c4fd5abb14adfa7d8d2e` mô tả file đã bị bỏ sót ở Debian sau khi RPM packaging được thêm.
- **Trước → sau:** Pacific định nghĩa `Format` ngay trong orchestrator module. Quincy chuyển nó sang module dùng chung `object_format.py`, CMake cài file này và manifest Debian phải thêm `usr/share/ceph/mgr/object_format.*`. Đây là dependency import runtime, không phải tài liệu package.
- **Điều kiện và tác động:** Gói upstream target có manifest sửa đúng; rủi ro nằm ở custom packaging/backport hoặc allowlist chỉ sao chép manifest cũ. Khi đó `ceph-mgr` có thể import orchestrator thất bại ngay sau restart/failover trong rolling upgrade. RPM dùng file selection rộng hơn nên cần xác nhận payload thay vì giả định tương đương. **Độ tin cậy:** cao cho import/install chain, chưa cài gói. **Kiểm chứng:** build/install package target vào image sạch, kiểm file và `python3` import theo `mgr_module_path`, bật orchestrator rồi restart/failover MGR; lặp với pipeline package nội bộ.

**Rollback PKG-002:** `object_format.py` phải cùng cohort với orchestrator module và MGR package. Nếu import thất bại, khôi phục cả payload/manifest đã pin và restart MGR sau khi giữ active/standby khỏe; copy một file từ Pacific vào Quincy không sửa contract. Import rollback không hoàn nguyên cephadm/SQLite state đã được target ghi, nên các migration gate vẫn quyết định khả năng failback MGR.

### PKG-003 — Ma trận tính năng Debian phụ thuộc architecture và build profile

- **CSV:** 80. **Nguồn:** `debian/rules`; liên quan [RADOS-002–003](./10-rados-rbd-clients.md) và [MSG-047](./05-messaging-auth-common.md).
- **Trước → sau:** Pacific bật `WITH_RBD_RWL=ON` không phân nhánh architecture. Quincy chỉ bật RWL trên `amd64`, tắt ở architecture khác, giữ `WITH_RBD_SSD_CACHE=ON` đã có ở Pacific, ép system `utf8proc`, và điều khiển Jaeger/system Arrow qua build profile; `ceph_crypto` cũng bị loại khỏi quét `dh_shlibdeps` như plugin khác. Hunk `debian/rules` không chứng minh SSD cache vừa được bật mới trong hop này.
- **Điều kiện và tác động:** Áp dụng cho gói Debian dựng từ source, đặc biệt arm64/ppc64, pipeline dùng build profile tùy chỉnh hoặc image kỳ vọng tracing/PWL plugin. Hai host khác architecture/profile có thể có capability khác dù cùng version; cấu hình RWL/tracing hiện hữu phải được so với artifact thực, không chỉ version package. Đây là thay đổi delivery/build, không khẳng định format cache đổi. **Độ tin cậy:** cao cho build flags, trung bình cho deployment. **Kiểm chứng:** lưu CMake cache và danh sách `.so`/dependencies theo từng architecture/profile, smoke-test mở image có cache cấu hình và bật tracing collector; kiểm rollback bằng artifact Pacific tương ứng.

`debian/python3-cephfs.install` còn được gắn [FS-007](./11-cephfs-mds.md): target không còn ship `ceph_volume_client.py`, nên inventory Manila/automation phải kiểm package/import chứ không chỉ nhìn source bị xóa.

**Activation/mixed và phần chưa biết:** flags được áp dụng explicit khi build package; restart nhận capability đã đóng trong artifact. Mixed architecture/profile có thể load PWL/tracing khác nhau dù package version giống nhau; full version không xóa khác biệt build đó. Chưa có architecture, build-profile, plugin inventory và cache mode của client đích, nên phải đối chiếu payload trước khi ký applicability; không suy từ tên gói rằng arm64 có RWL.

### PKG-004 — Tập source dependency bundled thay đổi theo feature target

- **CSV:** 9; các gitlink 1470, 1546, 2039–2041 và 4176 trỏ thêm tới RGW-004, RGW-039, MSG-047, PKG-003. **Nguồn:** `.gitmodules`, git tree hai tag và commit superproject tương ứng.
- **Trước → sau:** Quincy xóa submodule Civetweb cùng ba submodule OpenTracing/Jaeger/Thrift cũ, đồng thời thêm Apache Arrow 6.0.1 và utf8proc 2.2.0. Đây khớp với việc bỏ frontend RGW Civetweb, chuyển tracing sang OpenTelemetry, thêm S3 Select Parquet và cho phép bundled/system utf8proc; không phải chỉ dọn metadata Git.
- **Điều kiện và tác động:** Build từ source/offline cache phải chạy đồng bộ submodule và mirror đúng tập mới; nếu giữ cache/allowlist Pacific, build có thể thiếu Arrow/utf8proc hoặc vẫn mang source không còn caller. Capability runtime vẫn phụ thuộc CMake/profile và việc chọn system library, nên mixed deployment có thể có RGW Parquet/tracing khác nhau dù cùng version. **Độ tin cậy:** cao cho tree/build linkage, chưa dựng artifact. **Kiểm chứng:** clone sạch từng tag với recursive submodule, build ma trận bundled/system, lưu CMake cache/SBOM/link map và smoke-test RGW frontend, S3 Select Parquet, tracing.

**Activation/rollback PKG-004:** submodule chỉ tham gia khi pipeline explicit configure/build feature tương ứng; production host cài artifact không fetch dependency ở restart. Lưu gitlink, recursive source manifest và library selection trước build; rollback delivery bằng artifact/library cohort đã ký. Việc đổi checkout/submodule về Pacific không hoàn nguyên state Parquet/tracing/storage đã được feature runtime sử dụng; rollback dữ liệu phải theo owner chức năng.

### PKG-005 — Baseline thư viện bundled đổi cả fast-forward và divergent history

- **CSV:** 1982, 1999, 2038, 3635, 3649. **Nguồn:** gitlink SHA, object ISA-L cục bộ và GitHub compare API chính thức cho các repository Ceph dependency. `dmclock` đi trước 26 commit, `fmt` 961, `seastar` 679; ISA-L đi qua commit sửa text relocation aarch64. RocksDB target ở nhánh **diverged**, đi trước 832 nhưng thiếu 12 commit so với baseline Pacific; commit superproject đặt target ở dòng v6.15.5.
- **Trước → sau:** Target kéo thay đổi scheduling/Seastar trong dmclock, API/formatter mới trong fmt, compression/CRC/build và fix aarch64 trong ISA-L, một baseline RocksDB khác, cùng reactor/coroutine/alien mới của Seastar. Đây là source được compile/link khi dùng bundled dependency; không thể suy tương đương chỉ vì interface Ceph vẫn build.
- **Điều kiện và tác động:** Áp dụng theo `WITH_SYSTEM_*`, architecture và việc chạy classic hay Crimson. RocksDB là đường persistent store nên baseline divergent cần đặc biệt kiểm mở DB/compaction/rollback, nhưng source evidence chưa chứng minh format SST/MANIFEST cụ thể đã đổi. dmclock ảnh hưởng scheduler users; Seastar chỉ ảnh hưởng artifact Crimson; fmt có thể đổi output/exception tại các caller đã được owner chức năng phân tích. **Độ tin cậy:** cao về commit graph/file set, trung bình về artifact thực tế. **Kiểm chứng:** trích SBOM/link map, chạy store-open/compaction/restart trên clone DB Pacific với binary target rồi rollback lab, scheduler regression, aarch64 loader check, và Crimson canary; so cả build system-library lẫn bundled nếu pipeline hỗ trợ.

**Mixed/full PKG-005:** dependency version là local theo artifact; mixed daemons có thể dùng RocksDB/scheduler/EC implementation khác và cần test cả primary/restart direction. Full Quincy chỉ đồng nhất khi SBOM chứng minh cùng baseline theo lane. History divergent không chứng minh rollback DB an toàn hay bị cấm: phải giữ DB clone và xác minh SST/MANIFEST read/write bằng hai artifact, cùng allocation-file boundary BLU-001, trước khi cho downgrade store.

### PKG-006 — Object corpus đổi baseline kiểm tương thích, không phải runtime payload

- **CSV:** 21, 3645. **Nguồn:** gitlink và `src/script/gen-corpus.sh`; gitlink `ceph-object-corpus` đi trước năm commit. Commit superproject `13f3129f54e91053ed26ce5007c53d57ef5de6da` lấy archive `16.2.0-90-g50f1821b4c`; lịch sử dependency còn đánh dấu `MOSDScrub`/log-related classes forward-incompatible và bỏ một archive không còn backward-compatible.
- **Trước → sau:** Target dencoder corpus có thêm object encode từ nhánh Pacific và metadata expected incompatibility, nên tập type/fixture được thử và cách diễn giải failure khác baseline Pacific. Corpus không được cài vào daemon production.
- **Điều kiện và tác động:** Chỉ ảnh hưởng pipeline compatibility/dencoder có checkout submodule; bỏ qua cập nhật submodule có thể tạo false pass/false fail hoặc không kiểm type mới trước rollout. Không có mixed-version runtime effect độc lập. **Độ tin cậy:** cao về corpus history, chưa chạy corpus. **Kiểm chứng:** chạy exact corpus target với dencoder Pacific/Quincy, lưu danh sách expected pass/fail/forward-incompatible và tách regression bất ngờ khỏi incompatibility được khai báo.

**Activation/rollback PKG-006:** corpus được dùng explicit bởi encoding job, không tự chạy trên daemon. Nếu dùng corpus hoặc expected-incompatibility marker sai cohort, bỏ verdict và rerun với pinned corpus/dencoder/plugin manifest. Rollback ở đây là hoàn nguyên test inputs trên clean workspace; không đổi cluster state và không được dùng một archive bị loại để tuyên bố target compatible.

### PKG-007 — Helper source-build và source tarball đổi toolchain/artifact baseline

- **CSV:** 81–82, 417–418, 2427, 3647, 4179. **Nguồn:** `do_cmake.sh`, `do_freebsd.sh`, `install-deps.sh`, `make-dist`, `win32_deps_build.sh` và commit intent trong superproject.
- **Trước → sau:** Helper mặc định chuyển sang Ninja/Python 3 và nhận diện Python distro mới; FreeBSD tắt systemd rõ ràng. Dependency bootstrap chuyển Boost 1.73 → 1.75, thêm build profiles Crimson/Jaeger và pip mới. Source tarball đổi Node/Boost/liburing, thêm PMDK member và xử lý version SUSE; Windows dependency build tăng curl 7.66 → 7.84 cùng prerequisite.
- **Điều kiện và tác động:** Chỉ áp dụng cho pipeline build từ source hoặc tarball/Windows, không cho host cài nguyên gói upstream. Nếu pipeline nội bộ tiếp tục cache dependency Pacific hoặc gọi `make` trực tiếp sau khi helper tạo Ninja build, artifact có thể thiếu/khác feature hoặc build thất bại; hai artifact cùng nhãn Quincy có thể khác provenance. **Độ tin cậy:** cao cho recipe, chưa build. **Kiểm chứng:** dựng source tarball và build sạch trên distro/architecture As-Is, lưu compiler/generator/CMake cache/SBOM/hash payload; kiểm PMDK, Python bindings, dashboard và Windows client; so với package upstream trước rollout.

**Activation/rollback PKG-007:** các helper chạy explicit trên build host và có thể cài/xóa dependency; build-image snapshot là boundary trước bootstrap. Artifact không đạt thì khôi phục builder sạch và dùng artifact trước đã kiểm, không sửa build directory Pacific để tạo Quincy. Package rollback ở client/daemon vẫn phải tuân state gate riêng; checksum tarball và dependency provenance cần được giữ để tái lập.

### PKG-008 — Harness local/CI đổi topology và tín hiệu validation

- **CSV:** 1465, 1981, 2378, 3644, 3646, 3650, 4177. **Nguồn:** `run-make-check.sh`, `cstart.sh`, `mrun`, `stop.sh`, `vstart.sh`.
- **Trước → sau:** `run-make-check` chọn compiler/`-Werror`, đổi CTest reporting/aio limit và bật SSD cache cùng RWL có điều kiện. `vstart` đổi mặc định Crimson sang msgr2/foreground, thêm SeaStore/multi-device, tắt RESTful/Rook mặc định và đặt auth/MON thresholds; `cstart` thay bootstrap/digest behavior. Teardown mới gửi một SIGTERM, chờ theo giai đoạn rồi SIGKILL survivor thay vì lặp kill ngắn.
- **Điều kiện và tác động:** Đây là đường lab/CI, không tự đổi cluster production. Tuy nhiên kết quả test target không so trực tiếp được với Pacific nếu topology/module/cache/shutdown khác; lỗi chỉ xuất hiện ở RESTful, msgr1, abrupt stop hoặc cache tắt có thể bị bỏ qua. **Độ tin cậy:** cao cho harness, chưa chạy suite. **Kiểm chứng:** pin rõ mọi option khi chạy A/B, lưu `ceph config dump`, module list, messenger/store/cache và signal timeline; chạy thêm ma trận RESTful/msgr1/abrupt-kill tương ứng As-Is trước khi dùng pass target làm gate.

**Mixed/full/rollback PKG-008:** harness quyết định cách tạo mixed-version test cluster; hai job có default module/messenger khác không phải A/B tương đương. Pin topology/config để so cùng workload; khi teardown SIGKILL để lại unclean store, rollback test environment bằng snapshot hoặc recreate disposable nodes rồi rerun. Đổi helper về base không undo store/state của job cũ hoặc làm test coverage đã bỏ xuất hiện lại.

### PKG-009 — Vị trí unit systemd và bootstrap SysV thay đổi

- **CSV:** 2037, 4178. **Nguồn:** `systemd/CMakeLists.txt`, `src/init-ceph.in`; commit `8e49d3617012a70f037b506c99ddd0debd53a3e8` sửa default unit install dir và `bfbd279875f6395e203f17d2f22686f6f9ad9125` tạo run directory trước PID.
- **Trước → sau:** Pacific cài unit vào đường suy từ `CMAKE_INSTALL_LIBEXECDIR`; Quincy hỏi `pkg-config systemd_system_unit_dir`/tên cũ rồi fallback `${CMAKE_INSTALL_LIBDIR}/systemd/system`. SysV target tạo `/var/run/ceph` trước dispatch thay vì chỉ trong nhánh start và mở rộng path developer.
- **Điều kiện và tác động:** Gói distro chính thức thường override/manifest đúng, nhưng custom install/staging root có thể đặt unit sang đường khác; upgrade có thể để unit cũ và mới song song hoặc systemd không thấy file target. SysV chỉ áp dụng host còn dùng script legacy. **Độ tin cậy:** cao cho install/activation path, chưa cài gói. **Kiểm chứng:** cài vào staging root của từng distro, kiểm `systemd-analyze unit-path`, package ownership, daemon-reload/enable/start và file unit cũ còn sót; với SysV kiểm start/status khi `/var/run/ceph` chưa tồn tại và rollback.

**Mixed/full PKG-009:** unit lookup và SysV activation là local từng host; mixed packaging có thể dùng hai unit directories nên cần kiểm `FragmentPath` thực tế, không chỉ file target tồn tại. Sau full package install vẫn cần daemon-reload để bỏ cache unit cũ. Rollback recipe đã nêu phải restore đúng package-owned unit và override, xác nhận symlink/enablement rồi start từng daemon; dữ liệu store không được hoàn nguyên bởi unit rollback.

### PKG-010 — CLI quản trị và crash collector đổi bootstrap

- **CSV:** 1496, 1518. **Nguồn:** `src/ceph-crash.in`, `src/ceph.in`; commits `9966aae66598b01c55907f2ec630113a34ff7363` và `38bfd044de5c3c7456eb9c5fcbc0702473c7bcc2`.
- **Trước → sau:** Crash collector Quincy chạy `timeout 30 ceph -s` sau khi drop privilege để buộc key được dùng rồi mới vào scrape loop; Pacific vào loop ngay. CLI target truyền `rados.Rados.DEFAULT_CONF_FILES` thay chuỗi rỗng và khi help partial không match sẽ rút ngắn prefix cho tới khi có lệnh; developer mode còn hợp nhất `LD_PRELOAD` cho ASAN/libc++.
- **Điều kiện và tác động:** Agent crash target có thể trễ tối đa 30 giây và phát auth/connect log khi key/config sai, nhưng probe failure không chặn loop. Automation dựa output help/config lookup của CLI có thể quan sát khác; đường preload chỉ cho build tree. Trong rolling upgrade đây là behavior theo host client/agent, không phải wire format. **Độ tin cậy:** cao cho control flow, chưa chạy service. **Kiểm chứng:** start `ceph-crash` với key hợp lệ, thiếu quyền và MON unreachable; đo readiness/scrape/log. Chạy CLI với `CEPH_ARGS`, `-c`, default config list và partial help ở hai tag; kiểm stdout/stderr/exit của automation.

`src/ceph_release` được gắn [MSG-006](./05-messaging-auth-common.md): build metadata đổi từ Pacific 16 sang stable Quincy 17, nhưng checkpoint persistent của MON/OSD vẫn phải đánh giá ở MON-001/002 chứ không suy chỉ từ chuỗi release.

`src/objclass/objclass.h` được gắn [OSD-019](./01-osd-pg-recovery.md) vì public header xuất API gather tương ứng implementation OSD. `src/script/set_up_stretch_mode.sh` được gắn [MON-006](./04-mon-osdmap-crush.md): script bỏ `min_size`/`max_size` đã deprecated để tạo rule theo contract Quincy.

**Rollback PKG-010:** probe crash collector chỉ đọc/auth và không đổi data format; hạ package không bù crash report bị bỏ lỡ hay sửa key/config sai. Lưu effective config/key-entity metadata và service UID trước canary; nếu readiness/CLI lookup đổi, sửa config explicit hoặc restore nguyên client package cùng dependencies. Kiểm submission lại sau restart và giữ quyền user `ceph`, không dùng root để che lỗi permission.

### PKG-011 — Resolver/toolchain CMake đổi ngưỡng và cách chọn implementation

- **CSV:** 25, 27, 39–50, 53–54, 65–66 (trừ các hàng feature được tách ở PKG-012). **Nguồn:** endpoint modules và commit intent: GCC tối thiểu 8.1, Boost 1.75/Python 3.10, bỏ `experimental/filesystem`, đổi Python executable, NUMA/OpenLDAP imported target, FIO path/link và SIMD PowerPC.
- **Trước → sau:** Target thay cả bundled-build glue lẫn `find_package` semantics: nhận Boost/Python mới, bỏ patch Boost.Python cũ và helper ExternalProject dùng chung, chỉ chấp nhận `std::filesystem`, kiểm atomic 16-byte trên MIPS, thay imported target/link hints cho NUMA/OpenLDAP/FIO và mở probe SIMD trên PowerPC. Vì vậy cùng source nhưng toolchain/cache khác có thể chọn thư viện/ABI khác hoặc fail sớm.
- **Điều kiện và tác động:** Chỉ áp dụng cho build source/custom package; official artifact phải được kiểm bằng provenance. Rủi ro chính là tái build không lặp lại, extension Python/linker mismatch, hoặc platform cũ từng build Pacific không còn qua gate Quincy. Không suy runtime regression cụ thể nếu artifact đã build và link đúng. **Độ tin cậy:** cao cho build graph, chưa dựng ma trận. **Kiểm chứng:** clean configure/build trên compiler/Python/Boost/PowerPC/MIPS As-Is, lưu CMake cache/link map; import Python bindings và chạy smoke CLI/daemon từ artifact, không tái dùng build directory Pacific.

**Activation/mixed/rollback PKG-011:** probes chạy tự động trong explicit CMake configure; daemon restart chỉ nhận artifact kết quả. Mixed cohort khác toolchain/link closure cần được version bằng SBOM; full version string không bảo đảm ABI đồng nhất. Rollback pipeline bằng clean builder/cache và artifact/library set đã pin, không đổi một shared library trên node đang chạy. Test import/link phải pass trước khi các owner runtime xét state downgrade.

### PKG-012 — Optional dependency graph quyết định feature thực có trong artifact

- **CSV:** 24, 26, 28–38, 43, 45, 49, 51, 55–63. **Nguồn:** 25 module build/find; liên quan [RGW-039](./12-rgw.md), [MSG-047](./05-messaging-auth-common.md), [KV-001](./03-rocksdb-block-device.md), [RADOS-003](./10-rados-rbd-clients.md) và dependency gitlink PKG-004/005.
- **Trước → sau:** Quincy thêm Arrow/Parquet, utf8proc, system/bundled zstd, Linux ZNS và QAT driver finder; thay OpenTracing/Jaeger bằng OpenTelemetry; bỏ build bundled Thrift/yaml-cpp và LevelDB finder. DPDK/SPDK/RocksDB/liburing/PMDK/QATzip cũng đổi flags, version/components và link mode. Đây là quyết định compile/link của RGW Parquet, tracing, compressor, RWL, zoned/accelerated IO và backend KV.
- **Điều kiện và tác động:** Feature hiện hữu phụ thuộc CMake option, architecture, package dev files và system-vs-bundled. Rolling cluster có thể chạy artifact cùng version nhưng capability khác; rollback cần đúng library/plugin set, đặc biệt PMDK/RWL, tracing collector, QAT/SPDK/DPDK và RocksDB. Các module không tự chứng minh format state đổi. **Độ tin cậy:** cao cho dependency graph, trung bình cho artifact As-Is. **Kiểm chứng:** lập SBOM/link map/CMake cache cho từng artifact, chạy positive/negative smoke cho từng feature được bật; với RGW giải mã S3 Select/trace, với RWL mở cache clone, với storage accelerator chạy init/error path trên hardware lab.

**Activation PKG-012:** optional graph chỉ được build khi CMake flag/dependency discovery tương ứng có hiệu lực; feature runtime còn cần config/hardware riêng. Ví dụ `WITH_SYSTEM_ARROW` chọn library source, không tự bật traffic S3 Select, còn QAT finder không chứng minh accelerator usable. Pin resolved cache và smoke từng feature trước deployment để tránh capability drift giữa cohort.

### PKG-013 — CMake test/resource orchestration đổi tín hiệu CI

- **CSV:** 23, 52, 64. **Nguồn:** `AddCephTest.cmake`, `FindSanitizers.cmake`, `LimitJobs.cmake`.
- **Trước → sau:** Test wrapper target truyền tham số `PARALLEL`/fixture thay vì giữ wiring cũ; sanitizer finder ưu tiên `libasan.so.6`; Ninja có compile/link job pools tính theo bộ nhớ với ngưỡng 3500/4500 MiB. Những thay đổi này quyết định test concurrency/setup, sanitizer runtime và việc build có OOM/throttle.
- **Điều kiện và tác động:** Chỉ là build/validation infrastructure, không chạy trên daemon production. Tuy nhiên thiếu fixture, sanitizer khác hoặc job pool quá chặt/lỏng có thể đổi pass/fail/coverage và thời gian gate. **Độ tin cậy:** cao cho CMake behavior, chưa chạy CI. **Kiểm chứng:** chạy CTest verbose với fixture/parallel, ASAN build đúng distro, Ninja trên worker bộ nhớ thấp/cao; lưu test inventory, skipped tests, sanitizer path và peak RSS trước khi chấp nhận gate.

**Activation/mixed/rollback PKG-013:** CTest wrapper, sanitizer loader và Ninja job pool được dùng explicit trong CI/build; không có daemon migration. Mixed test resource settings phải được ghi vào job manifest để tránh quy OOM/harness error cho Ceph. Rollback bằng recreate build worker, pin ASAN/runtime/fixture rồi rerun cùng test inventory; verdict trước đó không được giữ nếu oracle/resource contract đã đổi.

### PKG-014 — Production target graph đổi binary/plugin/module thực được giao

- **CSV:** 41 hàng CMake production từ monitoring, core/classic/Crimson, compressor/crypto/EC, MGR/dashboard/Python, RGW DBStore, exporter và tools. **Nguồn:** endpoint target membership và commit history; owner chức năng giữ semantics runtime, owner 13 giữ hunk delivery để partition không trùng.
- **Trước → sau:** Target graph thêm `ceph-exporter`, generated option YAML/legacy headers, on-wire compression, RGW DBStore/SQLite, Dashboard frontend build tách riêng, `object_format.py`, dencoder plugins và nhiều SeaStore/Crimson target; đồng thời đổi source/link của tracing, QAT/zstd, allocator, RBD PWL, MGR/SQLite, RGW frontend và Python modules. Các thay đổi này quyết định code đã phân tích ở owner khác có thật sự vào binary/package hay không.
- **Điều kiện và tác động:** Áp dụng theo CMake option, platform và package split. Custom build có thể compile thành công nhưng thiếu target/module/asset nếu mang cache/list cũ; mixed cluster cùng version có thể khác capability. Finding này không nhân đôi từng behavior: exporter xem CFG-013/MGR, compression xem MSG, DBStore/S3 Select xem RGW, PWL xem RADOS, SeaStore/Crimson xem OSD/SEA. **Độ tin cậy:** cao cho graph, chưa kiểm artifact. **Kiểm chứng:** clean-build từng profile, đối chiếu target/install manifest, symbols/plugins/Python imports/frontend assets và SBOM; smoke-test từng feature bật, rồi so package payload với chính artifact rollout.

**Activation/rollback PKG-014:** target membership được sinh tự động trong explicit configure/build/install; cài package quyết định binary/plugin thật sau restart. Nếu thiếu module/asset, restore nguyên package cohort đã ký hoặc forward-fix manifest và smoke-test lại, không copy `.so`/Python module khác branch. Plugin/package rollback không hoàn nguyên `.mgr`, RGW encryption, BlueStore hoặc MDS state mà target đã ghi; các owner runtime giữ ranh giới đó.

### PKG-015 — Test target graph đổi coverage và execution contract

- **CSV:** 17 hàng `qa`, `src/test/*` và DBStore tests. **Nguồn:** endpoint target registration/link/args cùng commit history.
- **Trước → sau:** Quincy đăng ký thêm mypy/dead-symlink, DBStore, on-wire compression registry, journald, lazy OMAP stats, remote-read class, RBD migration/QCOW, RGW stats và nhiều SeaStore/FLTree/RBM test; một số test Crimson đổi `--smp`/memory/logging, tên target hoặc được bật/tắt lại. Link dependencies cũng theo production graph mới.
- **Điều kiện và tác động:** Chỉ ảnh hưởng validation, không chạy trong daemon production. Pass/fail giữa hai branch không đồng nghĩa cùng coverage: target có case mới nhưng cũng có test tạm disable/đổi runtime resource. **Độ tin cậy:** cao cho registration, chưa chạy CTest. **Kiểm chứng:** xuất `ctest -N -V` hai build sạch, so tên/label/command/skipped test; chạy nhóm DBStore, msgr compression, RBD, RGW, OSD/SeaStore và QA mypy với timeout/resource cố định, lưu JUnit/log đầy đủ.

**Mixed/full/rollback PKG-015:** test graph kiểm mixed cluster chỉ khi job đã compose đúng các endpoint; toàn bộ CTest PASS vẫn cần expanded test inventory để chứng minh những case nào thực chạy. Không có persistent production state trong graph này. Muốn rollback coverage phải pin test registration/args/resource và rerun trên disposable fixtures; không đổi tên hoặc bỏ test failed để giữ verdict cũ.

### PKG-016 — QAT chỉ còn tăng tốc zlib và đổi vòng đời session

- **CSV:** 1712–1713. **Nguồn:** `src/compressor/QatAccel.{cc,h}`; commits `414c028284c` (thay Snappy/LZ4 bằng zlib) và `6609aadfc9c` (tương thích QATzip API).
- **Trước → sau:** Pacific ánh xạ QATzip cho `snappy`, `zlib` và `lz4`, giữ `QzSession_T` trực tiếp. Quincy chỉ chấp nhận `zlib`; constructor LZ4 vẫn gọi `init("lz4")` nhưng nhận `false` rồi dùng phần mềm. Session chuyển sang `unique_ptr` với deleter teardown/close, và `qzMaxCompressedLength`/compress/decompress đều nhận session theo API mới. Hai hunk LZ4/zlib còn lại chỉ refactor tương đương và được gắn `trivial`.
- **Điều kiện và tác động:** Chỉ artifact bật `HAVE_QATZIP`, cấu hình `qat_compressor_enabled` và host có/cho phép QAT. Workload LZ4/Snappy mất hardware offload sau nâng nhưng giữ codec phần mềm, nên rủi ro chính là CPU, latency và capacity asymmetry giữa daemon Pacific/Quincy; không có bằng chứng đổi on-wire format. Zlib tiếp tục offload nhưng phụ thuộc QATzip ABI/session mới. **Độ tin cậy:** cao cho control flow, chưa đo hardware. **Kiểm chứng:** build đúng QATzip target, chạy vector zlib/LZ4/Snappy qua software và hardware path, kiểm byte round-trip, fallback, restart/leak và throughput/CPU trên mixed/full Quincy; lưu SBOM và log QAT init.

**Rollback PKG-016:** QAT session là runtime, còn dữ liệu codec đã commit là persistent. Hunk giữ software codec nên có thể kiểm hardware/software cross-decode bằng test vectors; nó không chứng minh toàn store Quincy→Pacific downgrade an toàn. Failback artifact QAT phải drain I/O, clean stop và khôi phục QATzip/library cohort đã pin; hạ package không giảm CPU spike đã xảy ra hoặc undo compressed writes.

### PKG-017 — `libcephsqlite` đóng RADOS trước static destruction

- **CSV:** 2064. **Nguồn:** `src/libcephsqlite.cc`; commits `664c2590010` và `7985b282cac`.
- **Trước → sau:** Pacific đặt `sqlite3_vfs` trong app-data và không gọi `cluster.shutdown()` khi process thoát. Quincy cấp phát VFS riêng, kiểm lỗi đăng ký, đăng ký `atexit`, xóa app-data và đóng RADOS trước khi static-duration objects bị hủy. Commit giải thích đường lỗi của `/bin/sqlite3` có thể gọi `exit(3)` khi thread librados còn sống.
- **Điều kiện và tác động:** Chỉ process nạp Ceph SQLite VFS, nổi bật CLI SQLite và lỗi I/O/blocklist khi thoát; đường MGR dùng VFS cũng cần smoke-test restart. Thay đổi nhằm tránh exception/segfault khi shutdown, không cho thấy schema hay object layout đổi. Mixed-version theo process, rollback không cần chuyển format nhưng phải kiểm không để handle/thread treo. **Độ tin cậy:** cao cho lifecycle, chưa tái hiện crash. **Kiểm chứng:** mở database Ceph VFS, chạy read/write rồi normal exit và fault/blocklist exit dưới Pacific/Quincy; kiểm exit code, crash/core, thread/leak và MGR failover/restart với store clone.

### PKG-018 — Build CephFS Dokan dùng định nghĩa `NTSTATUS` chuẩn của Windows

- **CSV:** 1985. **Nguồn:** `src/dokan/ceph_dokan.h`; commit `8589bc0d408` ghi rõ xung đột typedef sau khi chuyển Boost 1.79.
- **Trước → sau:** Pacific tự khai báo `NTSTATUS` là `DWORD`; Quincy bỏ typedef đó và include `bcrypt.h`, nơi MinGW/Windows SDK khai báo kiểu chuẩn. Việc này loại lỗi compile do Boost.Asio kéo `bcrypt.h` trước header Dokan.
- **Điều kiện và tác động:** Chỉ pipeline build client CephFS Dokan trên Windows/MinGW với dependency tạo xung đột; package Linux và host chỉ cài binary có sẵn không bị ảnh hưởng. Nếu custom pipeline giữ header/dependency Pacific, artifact Quincy có thể không build; thay đổi không tự đổi hành vi mount. **Độ tin cậy:** cao cho lỗi compiler/commit, chưa dựng Windows artifact. **Kiểm chứng:** clean-build Dokan với Boost/MinGW/Windows SDK đúng ma trận triển khai, kiểm symbol/header order, chạy map/unmap và smoke I/O, rồi lưu toolchain/SBOM cùng artifact.

**Activation/mixed PKG-018:** include/type fix được áp dụng tự động trong explicit build Dokan; binary đã build thành công không có runtime toggle cho header này. Mixed Windows-client/Linux-server matrix vẫn cần smoke I/O theo version client thực tế, nhưng header diff không tạo daemon protocol hoặc metadata migration. Full rollout chỉ là delivery của artifact đã build; architecture/SDK/Boost provenance còn thiếu thì giữ applicability conditional.

**Rollback boundary:** header/type selection nằm trong artifact Windows, không phải config toggle. Trước build/cài giữ SDK/MinGW/Boost, Dokan driver/client và DLL closure đã pin; build fail thì dùng builder sạch/artifact đã kiểm. Client failback cần quiesce/unmap rồi khôi phục cả cohort tương thích, không thay một typedef/DLL trên process đang mount. Đổi package không undo CephFS write đã commit hoặc metadata MDS; chưa có Windows build/mount kết quả để chứng minh failback cụ thể.

## Thay đổi trivial

55 hàng đã được đọc theo endpoint. Ngoài 19 hàng `PKG-DOC-01`, bảy hàng `PKG-MAN-01` và 13 hàng `PKG-CI-01`, lô cuối có 10 hunk cơ học/tài liệu (`PKG-MECH-02`/`PKG-DOC-02`) và sáu helper release-engineering (`PKG-RELENG-01`). Nhóm cơ học giữ nguyên tham số, framing, nhánh lỗi hoặc chỉ đổi namespace/API tương đương; riêng LZ4/zlib vẫn giữ software codec và QAT check ở overload đích. Helper backport, release note và debug container không được cài làm payload daemon/client hay dùng làm upgrade gate. Các thay đổi có đường build, delivery, runtime hoặc validation thực được giữ `affect` và map tới finding tương ứng.

## Kiểm chứng cần hoàn thành

- Dựng ma trận artifact official/custom theo architecture, compiler, CMake option và system-vs-bundled dependency; lưu CMake cache, SBOM, link/install manifest và hash payload.
- Mô phỏng cài/nâng/rollback package trong image sạch, kiểm split `ceph-volume`, MGR module, unit systemd/SysV và source tarball/offline submodule cache.
- Chạy CTest/corpus/harness với topology cố định; bổ sung smoke QAT, `libcephsqlite`, Dokan Windows, CRUSH stretch và object-class gather theo finding tương ứng.
- Đã đối soát binary gate: `152 affect + 55 trivial = 207`; mọi hàng `affect` đều trỏ tới finding có trước/sau, điều kiện, confidence và kịch bản kiểm chứng.

## Giới hạn hiện tại

Chưa có As-Is cluster, artifact triển khai hoặc lab/canary cho cặp endpoint. Binary gate hoàn tất không thay thế build/install/runtime validation; chưa đưa GO/NO-GO production.
