# 13 — Build, packaging, systemd, dependency và submodule

> **Trạng thái:** hoàn thành audit code-level cho owner `13-build-packaging-submodules`.
>
> **Hai đầu so sánh:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`), net diff lấy từ `ceph16.2.15/ceph` với `--find-renames`.
>
> **Ledger đầy đủ:** [13-build-packaging-submodules.csv](./13-build-packaging-submodules.csv). Báo cáo này chỉ phân tích source và thiết kế kiểm thử; không cấp quyền build/install/deploy, restart daemon hay thay đổi cluster thật.

## 1. Phạm vi, phương pháp và độ phủ

CSV là tập con giữ nguyên thứ tự và nguyên vẹn 21 cột đầu của inventory, gồm **51 dòng**:

| Chỉ số tổng hợp | Giá trị |
| --- | --- |
| Git status | `A 1`, `M 49`, `R 1` |
| Text churn | `+802/-282` |
| Reading priority | `P1 45`, `P2 6` |
| File type | `build/package 44`, `test/QA 5`, `dependency 1`, `documentation 1` |
| Final disposition | `conditional 24`, `mixed 6`, `support 7`, `trivial 14` |

Sáu cột phân tích được nối bên phải CSV: `upgrade_disposition`, `finding_id`, `disposition_reason`, `symbols`, `commit_shas`, `evidence_status`. Mỗi dòng đã được đọc endpoint hunk hoặc metadata gitlink, đối chiếu range history và gán disposition cuối; `P1/P2` chỉ là thứ tự đọc, không phải mức rủi ro.

Các finding dưới đây chỉ được giữ lại khi thay đổi có đường nhân quả tới package transaction, restart/activation, artifact dùng để nâng cấp hoặc validation. CI metadata, doc pipeline và test wiring không có tác động độc lập được gom ở mục 5; danh sách từng file chỉ nằm trong CSV.

## 2. Kết luận điều hành

| ID | Quyết định nâng cấp | Điều kiện kích hoạt | Rủi ro | Confidence |
| --- | --- | --- | --- | --- |
| `BLD-001` | Unit MON đổi `PrivateDevices=yes` → `false`; sau restart MON có thể nhìn thấy block devices để thu thập device health | MON cài bằng package/systemd và dùng unit target | Trung bình | high |
| `BLD-002` | Sudoers và quyền sở hữu package chuyển từ OSD-specific sang `ceph-base`; command allow-list không đổi | RPM/DEB, nhất là node không có package OSD | Trung bình về observability/package completeness | high |
| `BLD-003` | `smartmontools`/`nvme-cli` chuyển từ MON/OSD sang `ceph-base` | Package manager có cài weak dependencies/Recommends | Thấp–trung bình | high |
| `BLD-004` | Dependency graph và Python install layout của Debian package thay đổi | Tự build hoặc cài artifact Debian/Ubuntu target | Trung bình nếu pipeline tự đóng gói | high |
| `BLD-005` | Bootstrap dependency và source-tarball scripts đổi Boost/Jammy/venv/PMDK/liburing handling | Build từ source hoặc tự tạo DEB/tarball | Thấp–trung bình | high |
| `BLD-006` | `ceph-dencoder` chuyển type registry sang plugin `.so`; binary và module package phải đồng bộ | Dùng tool offline `ceph-dencoder` | Trung bình cho validation/recovery tooling | high |
| `BLD-007` | CMake/toolchain được siết cho Python, Boost, PMDK, fmt, LTO và các build variant | Tự build target, kể cả variant DPDK/PMEM/Windows | Trung bình nếu custom build; không áp dụng cho artifact đã kiểm chứng | high |
| `BLD-008` | Gitlink ISA-L chứa fix text relocation cho AArch64; internal diff đã đọc được | Build ISA-L EC trên AArch64 | Trung bình có điều kiện | high |
| `BLD-009` | Target sửa lifecycle RPM, nhưng direct `v16.2.5` → target vẫn chạy `%postun` của package base; không được suy ra user/key đã an toàn chỉ từ target spec | RPM non-SUSE có cephadm; thêm nhánh SELinux/cache | Cao | high |
| `BLD-010` | Debian `cephfs-mirror` bắt đầu chứa systemd unit và man page | Dùng CephFS mirroring qua Debian package | Thấp–trung bình | high |

Không finding nào tự tạo kết luận GO/NO-GO. Trước rollout cần chốt delivery model thực tế: container/cephadm, RPM, DEB hay artifact tự build; nhiều finding trở thành không áp dụng nếu chỉ dùng image đã được nhà cung cấp kiểm chứng.

## 3. Findings chi tiết

### BLD-001 — MON systemd unit mở device namespace cho health collection

**Owner/evidence.** CSV row `2664`, `systemd/ceph-mon@.service.in`, symbol `PrivateDevices`; commit `403590ef750f518ce9afc12138e5ed700fb96ab9` (`systemd: Set PrivateDevices=false in ceph-mon@.service`). Endpoint và commit đều nêu MON cần truy cập block device chứa DB store để kiểm tra health.

**Trước → sau.** Base đặt `PrivateDevices=yes`; target đặt `PrivateDevices=false` và thêm comment rằng có thể override về `true` nếu không dùng feature. Các hardening khác vẫn tồn tại, nhưng device namespace isolation này bị nới.

**Kích hoạt và mixed/full.** Thay đổi có hiệu lực khi package target cung cấp unit, systemd reload unit và MON được restart. Trong rolling upgrade, MON đã restart bằng target có view thiết bị khác MON base; không có thay đổi wire protocol. Khi toàn bộ MON liên quan chạy target, hành vi đồng nhất. Đây là thay đổi tự động từ artifact/unit, không phải migration dữ liệu.

**Tác động.** Availability/observability và security-hardening trade-off. Rủi ro `medium`: giữ `true` có thể làm device-health signal thiếu; dùng `false` mở rộng thiết bị nhìn thấy bởi process MON. Confidence `high`; As-Is còn thiếu là operator có override unit hoặc tắt device-health hay không.

**Validation đề xuất.** Trên staging package node, so sánh unit vendor với drop-in, xác nhận effective `PrivateDevices`, restart một MON theo runbook và quan sát MON quay lại quorum cùng device-health scrape. Stop condition: unit override ngoài dự kiến, MON không vào quorum, hoặc health query lỗi. Không thử nghiệm này đã được chạy trong audit source.

### BLD-002 — Sudoers/device-health files chuyển sang `ceph-base`

**Owner/evidence.** CSV rows `12`, `24`, `26`, `32`, `2663`; paths package manifests, `debian/rules` và rename `sudoers.d/ceph-osd-smartctl` → `sudoers.d/ceph-smartctl`. Commit `3aee6971531de6eebeb5d67d5772fa4c55e4e172` chuyển ownership sang `ceph-base` cho RPM lẫn DEB.

**Trước → sau.** Base package OSD sở hữu file có comment OSD-specific. Target `ceph-base` sở hữu tên mới, comment nói “ceph daemons”. Principal vẫn là user `ceph`, và hai command allow-list (`smartctl ... /dev/*`, `nvme ... /dev/*`) không đổi; vì vậy đây không phải mở rộng sudo command ở endpoint. Thay đổi thực là file có mặt trên mọi server daemon package phụ thuộc `ceph-base`, kể cả MON-only node.

**Kích hoạt và mixed/full.** Package transaction cài target manifest. Trong rollout, node base còn tên/ownership cũ; node target dùng tên mới. Không có protocol skew, nhưng monitoring có thể lệch theo node nếu transaction thiếu file hoặc package set không đồng bộ. Tác động tự động khi artifact đúng; operator chỉ cần xử lý local override/leftover bất thường.

**Tác động.** Observability/package correctness; `medium` vì mất sudoers file làm SMART/NVMe scrape thất bại nhưng không trực tiếp làm hỏng dữ liệu. Confidence `high` từ endpoint manifests và commit intent.

**Validation đề xuất.** Với cả RPM và DEB đang dùng, kiểm tra package file list, mode `0440`, parser sudoers và một health scrape không tương tác trên staging. Xác nhận file cũ không còn do package quản lý, nhưng không tự xóa file local không rõ nguồn gốc trong bước audit. Stop condition: missing/new file sai mode, invalid sudoers, hoặc scrape mất dữ liệu.

### BLD-003 — weak dependency của SMART/NVMe chuyển lên package nền

**Owner/evidence.** CSV rows `12`, `29`; `ceph.spec.in` và `debian/control`; cùng commit `3aee6971531de6eebeb5d67d5772fa4c55e4e172`.

**Trước → sau.** Base gắn `nvme-cli` và `smartmontools` vào MON/OSD. Target bỏ chúng khỏi hai package này và thêm vào `ceph-base` (`Recommends`, riêng nhánh SUSE RPM giữ `smartmontools` là `Requires`). Điều này khớp việc sudoers cũng chuyển lên package nền.

**Kích hoạt và mixed/full.** Áp dụng cho RPM/DEB; kết quả phụ thuộc policy cài weak dependencies như `--no-install-recommends`. Node target có thể thiếu executable dù sudoers đã đúng nếu policy bỏ Recommends. Không có mixed-version protocol effect.

**Tác động.** Package/observability, `low–medium`; confidence `high`. Validation cần kiểm tra resolved transaction trong đúng repository/distro của môi trường, không suy ra chỉ từ spec nguồn.

### BLD-004 — Debian dependency closure và Python install layout

**Owner/evidence.** CSV rows `29–31`, `1624`, `2513`; symbols `Build-Depends`, `pkg.ceph.check`, `PYTHON3_INSTDIR`, `sysconfig.get_path`, dh-exec mappings. Các commit chính gồm `f0eba544b0b29bffb997f1bcd20200243a7b7944`, `94ba1b1bf2c2313fea984df4ffbc9a35556bee3f`, `0a61febd36010468ae8a97c847852eec63a3d2e5`, `bcfe4fb8dc1fc0210ea261f7410e7092fe560f48`, `bfa86c88cd6b9c0ba0e042feb9764383245c8a49`.

**Trước → sau.** Target:

- dùng build profile `<pkg.ceph.check>` thay các dòng dependency make-check chỉ được comment;
- bỏ `cython`, `dh-systemd`, `virtualenv`, `lsb-release` và `python3-nose`, thêm/chuẩn hóa `golang`, `python3-venv`, `python3-pkg-resources` cùng `debhelper >= 10`;
- bổ sung dependency closure cho `ceph-mgr`, dashboard và `libsqlite3-mod-ceph`;
- thay `distutils` bằng `sysconfig`; chọn scheme `deb_system` khi có, và dh-exec đưa pure Python modules từ `*-packages` về `/usr/lib/python3/dist-packages/`.

**Kích hoạt và mixed/full.** Áp dụng lúc build/install DEB. Cluster dùng prebuilt target chỉ chịu kết quả artifact; pipeline tự đóng gói phải cập nhật build host/profile. Trong rolling upgrade, Python modules và native packages trên từng node phải đến từ cùng transaction; wire protocol không đổi. Thay đổi là tự động trong build/package, không phải runtime migration.

**Tác động.** Delivery correctness, `medium` với custom DEB pipeline; confidence `high`. Failure signal là build dependency không resolve, module bị đặt sai path hoặc MGR import lỗi sau restart.

**Repository evidence/validation.** `src/test/pybind/CMakeLists.txt` chuyển các test liên quan sang runner target, nhưng audit không chạy build/test. Đề xuất dựng source package với và không với `pkg.ceph.check`, kiểm tra package dependencies/files, import ba pure-Python modules trong clean install root, rồi smoke-start MGR trên staging. Stop condition: missing dependency, file ngoài `dist-packages`, import/link error.

### BLD-005 — scripts dựng dependency, DEB và source tarball

**Owner/evidence.** CSV rows `33`, `268–270`, `1093`; `install-deps.sh`, `make-debs.sh`, `make-dist`, `do_cmake.sh`, `run-make-check.sh`. Commit tiêu biểu: `3ac0bf38688f67da90540ce9315b1010e0a49327`, `572e7ebbbe24f3ba23b4fa02ca3eee690b5bfce1`, `0c17567b791d79b260ed1437d672a90dcc3cf49e`, `7882ad35fd572448de585b2d4e4e801e11b86b05`, `4aef0bbfcd5b6c26db67b08480c7fe6ed7bcd2fb`.

**Trước → sau.** `install-deps.sh` dọn các Ceph Boost packages cũ, dùng system Boost trên Jammy, chuyển sang `python3 -m venv` và dùng Debian build profile; `make-debs.sh` lấy codename từ `/etc/os-release`; `make-dist` vendoring PMDK 1.10 và đổi nguồn tải liburing/Boost. Đây là thay đổi pipeline đầu vào, không phải daemon code.

**Kích hoạt và mixed/full.** Chỉ pipeline dùng chính các scripts này bị tác động. Prebuilt package/image không chạy chúng trong rolling upgrade. Nếu các node nhận artifact khác nhau do build không tái lập, đó là artifact skew chứ không phải protocol skew.

**Tác động.** Maintainability/delivery, `low–medium`; confidence `high`. Đề xuất build cùng commit hai lần trong clean supported builders, so manifest/checksum, chạy package smoke tests và lưu compiler/dependency provenance. Audit không chạy script vì chúng cài/xóa dependency trên build host.

### BLD-006 — `ceph-dencoder` yêu cầu plugin package đồng bộ

**Owner/evidence.** CSV rows `12`, `25`, `1094`, `2397`, `2551`; symbols `ceph-dencoder-modules`, `add_denc_mod`, `CEPH_DENC_MOD_DIR`; commit `8da660fe8ae15da3ed873af517358c76f298c417`.

**Trước → sau.** Base link các type registries trực tiếp vào executable. Target tạo `denc-mod-common`, `denc-mod-osd` và các module có điều kiện RGW/RBD/CephFS, cài dưới `${CEPH_INSTALL_PKGLIBDIR}/denc`; RPM/DEB manifests thêm các `.so`. Executable target dùng `CEPH_DENC_MOD_DIR` và loader source (owner report 15) chỉ nhận prefix `denc-mod-` rồi gọi `register_dencoders()`.

**Kích hoạt và mixed/full.** Không ảnh hưởng daemon bình thường; kích hoạt khi operator dùng `ceph-dencoder` để validation/recovery. Binary target ghép với package module thiếu/sai version có thể không liệt kê hoặc decode đủ types. Không nên trộn binary base với module target hay ngược lại; sau transaction đầy đủ, executable và modules đồng bộ tự động.

**Tác động.** Validation/recovery tooling, `medium`; confidence `high`. Không có bằng chứng thay đổi wire/on-disk format chỉ từ build refactor này.

**Repository evidence/validation.** Build targets `tests` và `cephfs_testing` thêm dependency `ceph-dencoder-modules`; các scripts encoding hiện có dùng `list_types` và encode/decode round-trip. Đề xuất kiểm tra package contents, chạy `ceph-dencoder list_types`, chọn representative common/OSD/RBD/RGW/CephFS types theo feature build và chạy test encoding trong staging. Stop condition: `dlopen`/symbol error, thiếu family types, hoặc round-trip khác kỳ vọng. Chưa test nào được thực thi ở đây.

### BLD-007 — custom CMake/toolchain compatibility thay đổi

**Owner/evidence.** CSV rows `6`, `14–23`, `32–33`, `1094`, `1624`, `2665` cùng support rows `16`, `1093`; symbols `find_package(Python3 ... EXACT)`, `BuildBoost`, `Buildpmem`, `WITH_FMT_HEADER_ONLY`, `HAVE_ATTR_SYMVER`. Các commit tiêu biểu: `65549d41f2e29ddbadd9d8c9db8d1f595ca1b9f0`, `dc14e97d63d47ccb56873b7d1bee6f5e50f1c185`, `b9dbf4ecfcd250dae895f9b0d1f2bf43b9d2c7b0`, `06bd71cfee135ee59280bb0e3f2d9318d6dca988`, `33d249c245f6dcb6ce342b595e9936d255d5cad2`.

**Trước → sau.** Target khóa đúng Python version được chọn, bỏ API `distutils`, patch bundled Boost cho Python 3.10, chuẩn hóa PMDK 1.10/system discovery, hỗ trợ fmt header-only/static và kiểm tra symbol version/LTO. Các variant DPDK, bundled RocksDB/FIO và Windows dependency build cũng đổi flags/source pins. `debian/rules` đồng thời chuyển nguồn monitoring artifact sang `ceph-mixin`.

**Kích hoạt và mixed/full.** Chỉ custom build/variant tương ứng kích hoạt. Artifact vendor đã qua build acceptance không bị thay đổi tại thời điểm node restart; custom artifacts phải nhất quán trên mọi node để tránh khác feature/link closure. Đây không phải một migration dữ liệu tự động.

**Tác động.** Build compatibility, `medium` khi tự build và không áp dụng nếu dùng artifact chuẩn đã kiểm chứng; confidence `high`. Đề xuất cấu hình/build đúng matrix production (distro, compiler, Python, PMEM/DPDK/RGW/RBD/CephFS flags), chạy `ctest`/make-check có chọn lọc và kiểm tra linked-library manifest. Stop condition: CMake chọn sai interpreter, unresolved symbol, missing feature module hoặc artifact khác manifest chuẩn.

### BLD-008 — ISA-L AArch64 text-relocation fix đã được kiểm nội bộ

**Owner/evidence.** CSV row `1264`, gitlink mode `160000`: `806b55ee578efd8158962b90121a4568eb1ecb66` → `4b36e413c9ac28b4757b297779470693b699aeae`; superproject commit `ee31277dbe8c85108ec115b47a32397ba103697f`. Cả hai submodule objects có sẵn. Internal range chỉ có merge và commit `9c242d38321847acf04e9ccfc394ebf4506b239e`.

**Trước → sau.** Sáu assembly routines `gf_*vect_mad_neon` thay literal load bằng `adrp` + `:lo12:` và chuyển `const_tbl` từ `.data` sang `.rodata`, đúng mục tiêu loại text relocation trên AArch64. Không có thay đổi thuật toán EC hoặc persistent encoding được thấy trong internal diff.

**Kích hoạt và mixed/full.** Chỉ artifact AArch64 build kèm ISA-L EC plugin dùng code này. x86_64 không đi qua hunk. Trong rolling upgrade, khác biệt nằm trong local plugin implementation; không có bằng chứng endpoint về feature bit hay on-disk format mới.

**Tác động.** Build/load hardening và availability của EC path trên AArch64, `medium` có điều kiện; confidence `high` vì internal dependency diff đã đọc, không còn gap “thiếu submodule object”. Đề xuất build/link AArch64 với relocation checks, chạy ISA-L unit/EC non-regression tests và workload ghi/đọc/scrub trên EC pool staging. Stop condition: text relocation còn tồn tại, loader error hoặc data mismatch.

### BLD-009 — RPM lifecycle có transition hazard từ scriptlet của package base

**Owner/evidence.** CSV row `12`, `ceph.spec.in`. Bốn hunk độc lập cùng nằm trong endpoint:

- `23065e08ca36082557a5eb6cb1040e69b3338916`: `authorized_keys` đổi thành `%config(noreplace)`;
- `fb6d4bfd4e70c8587d408b77fc0d3e59ae993283`: `%postun -n cephadm` chỉ `userdel` khi `$1 == 0`, không xóa account trong upgrade;
- `f844c70be053826459ecc562df07984fc287f359`: SELinux scriptlets chỉ stop/start `ceph.target` khi `CEPH_AUTO_RESTART_ON_UPGRADE=yes`;
- `8146c6fbe970d67c6183b27129151235a2fb65bf`: immutable-object-cache `%postun` dùng trực tiếp `$1` thay `$FIRST_ARG`.

**Trước → sau ở hai endpoint.** Base coi key như file thường, chạy `userdel -r cephadm` vô điều kiện trong non-SUSE `%postun`, luôn stop/start Ceph khi SELinux file contexts đổi, và dùng `$FIRST_ARG` cho cache. Target đánh dấu key `%config(noreplace)`, chỉ xóa account khi `$1 == 0`, tôn trọng policy auto-restart, và dùng positional parameter RPM chuẩn để chỉ `try-restart` cache service trên upgrade khi policy là `yes`.

**Transition hazard của chính cặp endpoint.** Theo [execution order chính thức của RPM scriptlets](https://rpm.org/docs/latest/man/rpm-scriptlets.7#execution-order), `%pre/%post` của package mới chạy trước `%preun/%postun` của package cũ. Vì vậy direct upgrade từ RPM `v16.2.5` không-SUSE vẫn có thể chạy `%postun` base với `userdel -r` *sau* khi target `%pre` đã tạo/kiểm account và sau khi file mới được unpack. Target spec sửa các lần upgrade kế tiếp nhưng không thể sửa scriptlet đã lưu trong package base; `%config(noreplace)` cũng không tự chứng minh key/home sống sót trước old `userdel -r`. Đây là finding chuyển tiếp, không chỉ là endpoint improvement.

Nhánh SELinux `%post` target có thể điều khiển stop/start ngay trong first hop; còn thay đổi `%postun` của immutable-object-cache, giống cephadm, cần được kiểm đúng package/scriptlet thực sự chạy. Tác động xảy ra trên từng host, không phải wire skew. Operator phải đặt và kiểm chứng `CEPH_AUTO_RESTART_ON_UPGRADE` theo runbook.

**Tác động.** Availability và access continuity, risk `high`: mất cephadm user/key có thể chặn orchestration; restart ngoài kế hoạch có thể phá sequencing. Confidence `high` cho code và RPM execution order, nhưng applicability vẫn cần artifact/distro thật; chưa giải macro expansion hoặc chạy transaction của repository đang dùng.

**Validation đề xuất.** Trước production, bắt buộc chạy đúng direct transaction base RPM → target RPM trong disposable node có state đại diện: key đã sửa, cephadm account/home, policy `yes/no`, SELinux và cache service theo As-Is. Thu lại scriptlet expansion/order và kiểm key/account/UID sau old `%postun`, daemon restart events, labels và cache-service state. Thử upgrade tiếp từ target và uninstall riêng để tách first-hop hazard khỏi hành vi đã sửa. Stop condition: key/account mất, restart trái policy, relabel error hoặc cache state sai; nếu first hop tái hiện xóa account thì phải có mitigation/package path do owner RPM phê duyệt trước rollout. Không transaction nào được chạy trong audit source.

### BLD-010 — Debian package bổ sung service assets cho `cephfs-mirror`

**Owner/evidence.** CSV row `27`, `debian/cephfs-mirror.install`; commit `4f8b7e3fd5f6db6549a287e05c9e0c1167c076a0`.

**Trước → sau.** Base manifest chỉ chứa executable. Target thêm `lib/systemd/system/cephfs-mirror*` và man page. Runtime mirroring code thuộc report [11 — CephFS/MDS](./11-cephfs-mds.md); finding này chỉ kết luận artifact target có đủ service-management files.

**Kích hoạt và mixed/full.** Chỉ Debian deployments dùng cephfs-mirror. Node đã nâng target có unit, node base có thể không có; operator action vẫn cần theo runbook để enable/start service, manifest không tự chứng minh service đã chạy.

**Tác động.** Service manageability/availability, `low–medium`; confidence `high`. Đề xuất kiểm package contents, systemd unit parse, enable/start/stop trong staging và mirror failover scenario ở report 11. Stop condition: unit absent/unloadable hoặc mirror không reconnect.

## 4. Validation matrix đề xuất

Các scenario dưới đây là thiết kế kiểm thử, chưa được thực thi:

| Scenario | Finding | Phase và precondition | Expected / failure signal |
| --- | --- | --- | --- |
| V13-01 | `BLD-001` | Staging MON package/systemd, sau target restart | MON vào quorum; effective device namespace khớp policy; device-health scrape không lỗi |
| V13-02 | `BLD-002`, `BLD-003` | Resolve và cài đúng RPM/DEB transaction với policy weak-deps thật | Sudoers đúng owner/mode/syntax; `smartctl`/`nvme` có mặt khi được yêu cầu; không mất metrics |
| V13-03 | `BLD-004` | Clean Debian builder + clean install root | Build profiles resolve; Python modules nằm đúng `dist-packages`; MGR import/link thành công |
| V13-04 | `BLD-005`, `BLD-007` | Supported custom-build matrix | Build tái lập, đúng interpreter/dependency/link manifest; selected tests pass |
| V13-05 | `BLD-006` | Target executable và packages trong clean root | `list_types` có đủ enabled families; representative encode/decode round-trip không có loader error |
| V13-06 | `BLD-008` | AArch64 + ISA-L EC | Không còn text relocation; unit/non-regression và EC read/write/scrub pass |
| V13-07 | `BLD-009` | Disposable RPM upgrade, stateful cephadm + SELinux + cache | Key/user được giữ; restart khớp policy; labels/service state đúng; uninstall cleanup đúng |
| V13-08 | `BLD-010` | Debian cephfs-mirror staging node | Unit có thể load/enable/start; mirror reconnect/failover pass |

Mọi scenario khi sau này chạy trên môi trường đều cần snapshot/log trước, rollback/stop condition rõ ràng và owner phê duyệt. Báo cáo không coi việc source hunk tồn tại là bằng chứng test production đã pass.

## 5. Trivial/support changes

Disposition khớp chính xác CSV: **`conditional 24 + mixed 6 + support 7 + trivial 14 = 51`**.

- `support 7`: changelog, build/test runner, dencoder test dependency, Python test wiring và MON-tool link context. Chúng củng cố findings nhưng không tự thay đổi production rollout.
- `trivial 14`: GitHub ownership/label/workflow, ReadTheDocs/doc dependencies, AIX doc, test verbosity/tox và các hunk QA-only. Endpoint hunk và range history không cho thấy đường nhân quả tới artifact/runtime upgrade.
- `mixed 6`: một file chứa đồng thời hunk finding-relevant và hunk build/test/metadata không có tác động độc lập; CSV ghi rõ ID và lý do từng dòng.

Không dùng churn, path hay priority để kết luận trivial. Enumeration đầy đủ, symbols và commit mapping nằm trong CSV; Markdown cố ý không lặp bảng changed-file.

## 6. As-Is cần chốt và giới hạn bằng chứng

- Delivery thực tế là cephadm container, RPM, DEB hay custom source; distro/repository nào tạo artifact target?
- Có host RPM dùng cephadm user/key, SELinux, `CEPH_AUTO_RESTART_ON_UPGRADE` hoặc immutable-object-cache không?
- Có Debian `cephfs-mirror`, offline `ceph-dencoder`, custom PMEM/DPDK/fmt/Python build hay AArch64 ISA-L EC không?
- Có local systemd/sudoers/package override nào khiến endpoint vendor files không phải effective state không?

Đã kiểm endpoint diff, range commits và internal ISA-L diff; chưa build Ceph, chưa chạy repository tests, chưa giải RPM/DEB transaction trên distro cụ thể và chưa tác động cluster. Vì vậy report cung cấp gating/validation evidence, không thay cho acceptance của artifact hoặc quyết định production GO.
