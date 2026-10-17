# 13 — build, packaging, dependencies và gitlinks: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./13-build-packaging-submodules.csv) có 227 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 152`, `trivial = 75`, chưa phân loại = 0. Detailed findings chỉ được promote từ hàng `affect`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow/non-ancestor, nên kết luận dựa trên endpoint hunk, install/build graph và raw gitlink SHA; chưa có commit-range đầy đủ để chứng minh toàn bộ dependency history.

Chưa có artifact As-Is: không biết rollout dùng package upstream, custom RPM/DEB, cephadm container, source build, system hay bundled dependencies, architecture/toolchain nào. Chưa clean-build, cài/nâng/rollback package, resolve nội dung sáu gitlink, sinh SBOM/link map hoặc chạy smoke. Báo cáo không cấp quyền cài/gỡ package, restart service hay thay image production.

## Finding ảnh hưởng upgrade

### BUILDDEP-001 — Toolchain và dependency resolver của target đổi baseline

**Evidence.** Root CMake tăng system/bundled Boost `1.73/1.75→1.79`, `find_package(FUSE REQUIRED)`, non-Windows curl tối thiểu 7.32, cấu hình liburing ở top level, thêm DML/PMDK resolver và bật Jaeger mặc định. Dashboard languages mặc định từ rỗng sang `ALL`. Các module build/find đổi Arrow, ISAL/ISAL-Crypto, OpenTelemetry, RocksDB, SPDK, c-ares, PMDK, ndctl/daxctl, Motr, DAOS và atomic probing.

**Before/after.** Build host từng tạo Quincy có thể fail sớm hoặc chọn library/feature khác khi tạo Reef; hai artifact cùng version có thể khác capability nếu một bên dùng system library và bên kia bundled. Tác động delivery/reproducibility; confidence `high` cho graph, artifact applicability `UNKNOWN`.

### BUILDGRAPH-001 — Production target/source/install graph đổi mạnh

**Evidence.** `src/CMakeLists.txt` và component CMake thay source/link/install cho classic/Crimson, OSD scrub, MDS, messaging Windows, MGR/Python/Dashboard, RGW executable/library/backends, RBD encryption 1.18, monitoring và tools. `src/os/CMakeLists.txt` bỏ toàn bộ FileStore source; `src/rgw/CMakeLists.txt` chuyển `radosgw` từ shared-library wrapper sang executable, thêm config stores, optional Arrow Flight/Motr/DAOS và `rgw-policy-check`; `src/librbd/CMakeLists.txt` ship crypto flatten/magic sources và `VERSION 1.18.0`.

**Before/after.** Cache/manifest Quincy không được tái dùng để build Reef: build vẫn có thể thành công nhưng thiếu source, plugin, frontend asset hoặc utility mới. Artifact identity được nhúng là Reef 18. Cross-reference: removal FileStore là `FILESTORE-001`; RBD delivery là `RBDAPI-001`/`RBDCRYPT-001`; mirror/mapping target là `RBDMIRROR-001`/`RBDMAP-001`. Tác động payload capability; confidence `high`, cần install-manifest/SBOM thực.

### BUILDTOOL-001 — Source/container/Windows build helpers đổi quy trình và dependency cache

**Evidence.** `do_cmake.sh`, `install-deps.sh`, `make-dist`, Debian helper, MinGW/Windows scripts, NASM wrapper và container-build scripts đổi generator, dependency installation, source-tarball contents, platform detection và build invocation. `src/script/build-with-container.py` cùng supporting scripts là đường build mới lớn.

**Before/after.** Pipeline nội bộ gọi helper cũ, dùng offline cache cũ hoặc incremental build directory có thể tạo artifact thiếu/khác feature. Đây không áp dụng cho host chỉ cài official artifact đã xác minh. Tác động supply-chain/reproducibility; confidence `high`, chưa chạy pipeline.

### SUBMOD-001 — Bundled dependency set và exact gitlink SHA đổi

**Evidence.** Raw tree đổi `fmt 427b…→a337…`, `rocksdb c540…→9fa4…`, `s3select 1609…→eb40…`, `seastar ce26…→50c6…`; thêm OpenTelemetry C++ `9f3a…`, xóa RapidJSON gitlink `f54b…`, đổi ISA-L-Crypto URL sang Intel. Repo shallow và submodule content chưa được resolve, nên không suy commit count hay compatibility từ SHA.

**Before/after.** Recursive/offline source build phải mirror đúng tập target và khóa exact pointer; dùng cache Quincy có thể fail hoặc âm thầm chọn system dependency khác. RocksDB/Seastar là dependency có blast radius lớn nhưng gitlink alone không chứng minh format DB hay wire break. Tác động provenance/persistent-store risk conditional; confidence `high` cho pointer, `UNKNOWN` cho nội dung.

### PKGDEB-001 — Debian đổi dependency generation, package ownership và maintainer scripts

**Evidence.** Debian nâng compiler requirement lên g++ 11, chuyển nhiều dependency MGR sang `${python3:Depends}` sinh từ các file `.requires`, thêm `ceph-exporter`, `adduser`, PMDK/DAX dependencies và extblkdev payload. RGW gap/orphan/restore tools chuyển sang `ceph-common`; `libradosgw.so` không còn ở `radosgw.install`. `ceph-base.postinst` recursive chown crash entries; user creation/metadata trong `ceph-common` và `cephadm` đổi; Python argparse install dùng `dh-exec` để normalize dist/site-packages.

**Before/after.** Custom Debian build thiếu requirement scan hoặc stale manifest có thể cài thành công nhưng fail import/service start. Package ownership chuyển có thể làm allowlist/mirror hẹp thiếu tool/library; maintainer script có thể đổi owner hiện hữu. Tác động upgrade/install/rollback; confidence `high`, phải thử bằng package manager trên image sạch và image nâng từ Quincy.

### PKGRPM-001 — RPM feature matrix và package payload đổi

**Evidence.** `ceph.spec.in` mở rộng openEuler, thay compiler/library requirements, default Jaeger theo distro, system Arrow/PMDK logic, thêm extblkdev plugin, SNMP MIB và node-proxy packages, thêm RGW recovery tools; cephadm không còn được copy trực tiếp từ source script mà lấy install target CMake.

**Before/after.** Feature/plugin/package set phụ thuộc distro macro và build condition; custom spec/profile có thể không giống official artifact. Không dùng version RPM để suy rằng exporter, node-proxy, Arrow, tracing, VDO hay exact RGW tools đều có mặt. Tác động delivery/capability; confidence `high`, artifact applicability `UNKNOWN`.

### PKGCONT-001 — Có đường build/manifest container multi-architecture mới

**Evidence.** `container/Containerfile`, `container/build.sh` và manifest-list helper được thêm, tách khỏi Dockerfile build môi trường phát triển.

**Before/after.** Nếu rollout dùng image tạo bởi đường này, base image, architecture list và copied package payload trở thành phần của provenance; nếu dùng registry vendor khác thì finding không áp dụng. Tác động container supply chain; confidence `high`, cần digest/SBOM/signature thực.

### PKGCEPHADM-001 — cephadm trở thành generated version-stamped install artifact

**Evidence.** `src/cephadm/CMakeLists.txt` chạy `build.py`, nhúng `CEPH_GIT_VER`, nice version, release/name/type vào output `bin/cephadm`, rồi cài output đó vào sbin. RPM bỏ direct `install src/cephadm/cephadm`; Debian postinst đổi cách tạo cephadm user/home/comment.

**Before/after.** Stale source copy hoặc packaging bypass CMake có thể giao cephadm sai version/provenance; package upgrade còn tác động account/home/SSH ownership. Tác động orchestration delivery/rollback; confidence `high`. So sánh `cephadm version`, hash, embedded release và package ownership trước khi cho MGR target dùng binary.

### PKGEXP-001 — ceph-exporter có package và systemd unit riêng

**Evidence.** Debian thêm package/install manifest; RPM thêm payload; systemd build cài `ceph-exporter@.service`. Unit chạy `/usr/bin/ceph-exporter -f --id %i --setuser ceph --setgroup ceph`, restart on failure và bật hardening. Đây là delivery half của telemetry handoff `MGRMETRIC-001`.

**Before/after.** Có binary target không đồng nghĩa exporter đã enabled, được cephadm deploy hoặc Prometheus scrape. Package/unit thiếu, instance ID/config sai hay hardening chặn resource sẽ tạo blind spot đúng lúc MGR mặc định loại perf counters. Tác động observability/acceptance; confidence `high`, deployment applicability `UNKNOWN`.

### PKGSEC-001 — SELinux policy thêm quyền io_uring có điều kiện

**Evidence.** `selinux/ceph.te` gọi `kernel_io_uring_use(ceph_t)` khi interface policy tồn tại.

**Before/after.** Binary bật io_uring trên host enforcing nhưng policy package cũ có thể bị deny; policy target trên distribution không có macro vẫn phải compile theo conditional. Tác động availability/performance conditional; confidence `high`. Kiểm AVC, loaded module version và fallback I/O path trên host thật.

### NODEPROXY-001 — Target thêm hardware-monitoring node-proxy/Redfish agent

**Evidence.** Một package Python mới gồm API, Redfish base/Dell system, reporter, client, utility, setup và CMake install; RPM định nghĩa package `node-proxy`.

**Before/after.** Quincy artifact không có agent này; Reef có thể deploy nếu orchestrator/hardware-monitoring path bật. Nó không cần thiết cho core upgrade khi không dùng, nhưng khi dùng phải inventory credential, BMC reachability, vendor model và report destination. Tác động optional service/security; confidence `high`, applicability `UNKNOWN`.

### EXTBLK-001 — External block-device/VDO plugin được thêm và đóng gói

**Evidence.** Target thêm interface/plugin loader, VDO implementation và CMake; block layer link `extblkdev`; Debian/RPM cài `libceph_extblkdev` plugin. Root build còn thêm PMDK/DML/ndctl/daxctl discovery.

**Before/after.** Artifact target có thể nhận external device capability/failure path mới; không tự áp dụng nếu không có config/device/plugin load. Mixed hosts có plugin set khác dù cùng cluster version. Tác động storage capability; confidence `high`, cần plugin discovery/init/error test trên disposable hardware fixture.

### COMPRESS-001 — Compressor ABI nội bộ và QAT zlib lifecycle đổi

**Evidence.** Compressor API chuyển `boost::optional→std::optional`; QAT accelerator thành singleton với session pool giới hạn bởi `qat_compressor_session_max_number`, chỉ init zlib, đặt default raw-deflate window marker và thay fallback/error flow. Zlib chỉ dùng QAT decompress với compatible window; plugin có lựa chọn ISA-L. CMake thay build/link zlib/ISA-L.

**Before/after.** Artifact không bật QAT/ISA-L chủ yếu đi software path; artifact bật accelerator có concurrency/session/fallback và CPU/latency khác. Reviewed hunk không chứng minh on-wire compression format break nhưng data round-trip phải được test trước mixed deployment. Tác động performance/correctness conditional; confidence `high`.

### DOKAN-001 — Windows CephFS Dokan client đổi build và runtime utilities

**Evidence.** Dokan sources thay option parsing, string conversion/common Windows utility use và runtime handling; Windows build/dependency scripts cũng đổi.

**Before/after.** Chỉ áp dụng nếu có Windows CephFS/Dokan clients hoặc custom Windows artifact. Target phải clean-build với SDK/Boost/MinGW tương ứng và smoke mount/read/write/unmount/reconnect; Linux daemon rollout không kích hoạt trực tiếp. Tác động client delivery; confidence `high`, applicability `UNKNOWN`.

### OBJCLASS-001 — Public object-class API/build surface đổi

**Evidence.** Header/API expose target config và object-info accessors; classic `cls_log` implementation chuyển khỏi generic `class_api.cc` sang OSD object-class implementation, trong khi public declaration giữ lại.

**Before/after.** Built-in classes được build cùng tree; external object-class plugins cần rebuild/symbol-check và negative load test. Không có bằng chứng persisted object encoding đổi chỉ từ các hunk này. Tác động plugin source/binary compatibility; confidence `high`, applicability phụ thuộc custom cls inventory.

### TRACE-001 — librados tracepoint schema đổi cùng public API

**Evidence.** `src/tracing/librados.tp` thêm/đổi tracepoints cho stat2/write-op paths và target librados operations; liên kết với `RADOSAPI-001`.

**Before/after.** BPF/LTTng/SystemTap consumers hoặc generated probe bindings theo schema Quincy có thể không attach/parse target event đúng. Không áp dụng nếu không dùng tracepoint tooling. Tác động observability; confidence `high`, cần regenerate và replay collector.

### MGRDB-001 — Delivery owner xác nhận reconnect path nằm trong libcephsqlite

**Evidence.** `src/libcephsqlite.cc` chuyển cluster handle sang shared pointer có mutex, re-open trên `-EBLOCKLISTED` ở lock/unlock/read/write/truncate/sync/filesize và cung cấp handle mới cho subsequent VFS operations. Đây là implementation evidence bổ sung cho finding `MGRDB-001` ở [owner 07](./07-mgr-modules-monitoring.md).

**Before/after.** Sau MGR failover/blocklist, target VFS có thể reconnect thay vì tiếp tục handle cũ; package phải ship đúng library đồng bộ với MGR Python code. Tác động persisted module availability; confidence `high`, runtime test còn mở.

**Closure.** Mixed-version phải failover old/new active MGR against cloned `.mgr` state; full-Reef lặp blocklist/reconnect/restart với cùng package set. Rollback bằng promote known-good MGR and restore pinned library only before target schema/state mutation; DB backup/clone is required after writes. Kiểm chứng cần handle reopen, transaction integrity and idempotent recovery.

## Operational closure addenda

#### BUILDDEP-001 — Closure

Dependency/toolchain selection tự động occurs at configure/build; mixed/full delivery must use one resolved build manifest per cohort. Rollback is restore prior signed artifact/dependency lock, not reuse target build cache. Validation needs clean configure/build, versions, symbols, SBOM and exact digest.

#### BUILDGRAPH-001 — Closure

Áp dụng to every production target expected in the deployed payload. Mixed/full must compare installed files/services/modules before cohort rollout. Rollback by prior package/image manifest and transaction rehearsal; missing/added target can change service ownership. Validate build/install graph, skipped targets and payload cross-check.

#### BUILDTOOL-001 — Closure

Helper/cache logic tự động activates during source/container/Windows builds. Mixed/full artifacts must be produced from clean target caches and same profiles. Rollback is prior reproducible artifact/cache lock, not incremental rebuild. Validate source provenance, cache hits, dependencies and output hashes.

#### SUBMOD-001 — Closure

Gitlink resolution tự động at recursive checkout/build; floating/missing objects are forbidden. Mixed/full artifacts must record exact recursive SHAs. Rollback by prior gitlink lock/artifact and dependency-compatible data test. Validate fetch, diff, ABI, license/CVE and SBOM.

#### PKGDEB-001 — Closure

Applicability covers Debian/Ubuntu cohorts. Maintainer scripts and dependency solver tự động run during package transaction. Mixed/full must rehearse upgrade/rollback on each supported release. Validate conffile, users/units, Python imports and file ownership; never infer from RPM result.

#### PKGRPM-001 — Closure

RPM scripts/feature payload tự động apply at transaction/install. Mixed/full must rehearse each supported distro/profile. Rollback by signed prior NEVRA plus database/files backup; service/data compatibility gates still apply. Validate solver, scripts, units, ownership and enabled feature modules.

#### PKGCONT-001 — Closure

Manifest/architecture selection tự động at pull/run. Mixed/full must pin per-arch digest and test every host architecture. Rollback by prior digest and image availability; no floating tags. Validate manifest list, signature, entrypoint, embedded versions and smoke behavior.

#### PKGCEPHADM-001 — Closure

Generated artifact/version stamping tự động during build/install and cephadm invocation. Mixed/full must compare script/package/MGR call path. Rollback by pinned prior cephadm artifact and image digest. Chưa có exact artifact; validate hash, `version`, package owner and read-only inventory/bootstrap fixture.

#### PKGEXP-001 — Closure

Mixed/full must install/start exporter per host while retaining old metric source until coverage PASS. Rollback by disable/remove target unit and restore scrape config/package without losing dual telemetry. Validate user/group, systemd hardening, admin-socket access, labels and discovery.

#### PKGSEC-001 — Closure

SELinux policy tự động applies after package/policy load; io_uring path depends host config. Mixed/full must test enforcing on every relevant distro. Rollback by prior signed policy/package, never disable enforcing as acceptance. Chưa có AVC/runtime evidence; validate enabled/disabled io_uring, startup and fallback. This gate also requires policy module/version and audit-log artifacts.

#### NODEPROXY-001 — Closure

Mixed/full must canary one agent/node-proxy with target MGR and preserve legacy inventory source. Rollback by stop target service, restore spec/image/certs and reconcile hardware state. Validate Redfish auth/TLS/report, timeout/failure and no control-plane outage.

#### EXTBLK-001 — Closure

Rollback extblkdev/VDO by drain OSD, restore plugin+binary package and reopen cloned device; plugin state already reported is not data migration. Validate load/missing/wrong-version paths and capacity metadata on exact artifact.

#### COMPRESS-001 — Closure

Compressor/QAT lifecycle tự động activates when configured codec/backend loads. Rollback requires pinned prior plugin/library and software fallback after draining; compressed data must round-trip with old/new readers. Chưa có build-feature inventory; validate ABI, init/finalize, fallback, checksums and failure injection.

#### DOKAN-001 — Closure

Windows Dokan utility/runtime path tự động activates at client start. Rollback by unmount/drain, restore pinned driver/client and remount after namespace checksum. Validate build artifact, mount/reconnect/unmount, credentials and service lifecycle on supported Windows version.

#### OBJCLASS-001 — Closure

Mixed/full must rebuild external class consumers against target headers and test old/new OSD/class combinations. Rollback by prior plugin/artifact before class-state mutation; persisted object changes need clone/manifest. Validate symbols, load, method calls and data checksum.

#### TRACE-001 — Closure

Mixed/full must regenerate BPF/LTTng/SystemTap consumers and run dual schema until full-Reef. Rollback by old probe/collector, not trace history rewrite. Validate attach, field decode, event rate and correlation on exact target artifact; this adds enough runtime evidence beyond source schema alone.

## Trivial changes

75 hàng `trivial` gồm 18 documentation/documentation-build rows, 17 test-target rows chưa chạy, 16 CI/repository-governance rows và 24 helper release-engineering, local vstart/Crimson harness, lint, log/help hoặc developer utility rows. Chúng vẫn là context cho build/test nhưng không tự thay production artifact hay chứng minh acceptance. Lý do ổn định từng hàng nằm trong CSV.

## Validation đề xuất

1. **Artifact As-Is:** ghi package/container source, architecture, compiler, CMake cache/profile, system-vs-bundled choices, installed-file manifest, image digest, SBOM và signatures cho từng daemon/client cohort.
2. **Clean build matrix:** dựng Reef từ checkout sạch, exact recursive gitlinks và official/custom profiles; không dùng build directory/cache Quincy. Lưu configure log, link map, symbols, skipped targets và dependency versions.
3. **Package transaction:** mô phỏng upgrade + rollback RPM/DEB trên image Quincy có dữ liệu/user/unit hiện hữu; kiểm solver, maintainer script, ownership, Python imports, service enablement, conffile và file moved giữa packages.
4. **Exporter delivery:** cài/start `ceph-exporter@<id>`, kiểm user/group, systemd hardening, restart, admin-socket/config access, metrics/labels và Prometheus discovery trước khi cho MGR áp telemetry split.
5. **cephadm provenance:** so hash/version/embedded release/package owner; bootstrap/read-only inventory trong lab và MGR call path. Fail nếu package script và generated binary không cùng target.
6. **Dependency/gilink:** mirror exact SHA, sinh SBOM và scan license/CVE; với RocksDB chạy open/compact/restart/rollback trên clone DB nhưng không suy format compatibility từ SHA alone.
7. **Feature smoke:** node-proxy Redfish auth/report, extblkdev/VDO load/error, QAT/ISA-L software fallback + round-trip, Arrow/Jaeger options và Dashboard assets theo đúng artifact feature set.
8. **Client/plugin:** build external cls consumer, librados trace consumer và Windows Dokan artifact; test symbol/probe/mount lifecycle bằng target package.
9. **SELinux:** enforcing host với io_uring enabled/disabled; theo dõi AVC, service start và fallback. Không xử lý denial bằng tắt enforcing trong acceptance.
10. **Payload cross-check:** đối chiếu behavior findings với file thực trong artifact: `FILESTORE-001`, `MGRMETRIC-001`, `RADOSAPI-001`, `RBDAPI-001`, `RBDCRYPT-001`, `RBDMIRROR-001`, `RBDMAP-001`. Source finding không đủ nếu binary/module/plugin không được giao.

## Kết luận owner

Owner 13 đã khép binary gate. Gate quan trọng nhất không phải “source có build được” mà là chứng minh artifact sắp rollout có đúng dependency/payload/service đã phân tích: đặc biệt exact gitlinks, generated cephadm, ceph-exporter, package dependency generation và production target graph. Không có artifact/SBOM/install rehearsal nên chưa có GO/NO-GO production.
