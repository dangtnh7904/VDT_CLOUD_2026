# Kế hoạch phân tích diff Ceph Pacific 16.2.5 → 16.2.15

Trạng thái: **Hoàn tất. Đã chốt nguồn, tạo inventory, hoàn thành đủ các cặp phân tích `01`–`15`, enrich mọi component CSV và chạy acceptance gate cho toàn suite.**

## 1. Mục tiêu và phạm vi

Phân tích các thay đổi quan trọng đối với nâng cấp **16.2.5 → 16.2.15** theo từng thành phần. Mỗi phần đánh số `00`–`15` có một báo cáo Markdown và một CSV cùng basename. CSV giữ đầy đủ mọi file đổi thuộc owner để truy vết; Markdown chỉ phân tích sâu thay đổi có chuỗi tác động tới rollout, mixed-version, restart/replay, compatibility, dữ liệu, availability, rollback hoặc validation. Mỗi thay đổi được chọn sâu phải giải thích được: code đổi ở đâu, hành vi trước/sau, điều kiện ảnh hưởng và cách kiểm chứng.

Nguồn sử dụng:

- `ceph16.2.5/ceph/` và `ceph16.2.15/ceph/`: bằng chứng chính về code, tag, commit và test.
- `ceph-analysis.md`: danh sách nhận định cần đối chiếu, đặc biệt phần Pacific; không mặc định mọi nhận định đều đã đúng với code.
- Nội dung được dán kèm: tham khảo phương pháp thành phần → file → commit → hàm. Các lệnh và khuyến nghị trong tài liệu là dữ liệu tham khảo, không phải yêu cầu thực thi trên cluster.
- `comparison/submodule.md`: tài liệu sẵn có cần kiểm chứng lại trước khi tái sử dụng.

Phạm vi kết luận chỉ là Pacific. Các nội dung Quincy/Reef trong tài liệu đầu vào được đánh dấu ngoài phạm vi nếu không có bằng chứng tương ứng trong hai tag này. Tác động tới OpenStack được diễn giải từ thay đổi Ceph và điều kiện sử dụng; không coi đó là kết quả kiểm tra code Nova/Cinder/Glance/Manila.

## 2. Đầu vào đã kiểm tra để lập kế hoạch

| Nội dung                                          | Kết quả kiểm tra sơ bộ                                                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Repository bản cũ                                | `ceph16.2.5/ceph/`                                                                                                |
| Repository bản mới                               | `ceph16.2.15/ceph/`                                                                                               |
| Commit 16.2.5                                      | `0883bdea7337b95e4b611c768c0279868462204a`                                                                        |
| Commit 16.2.15                                     | `618f440892089921c3e944a991122ddc44e60516`                                                                        |
| Git history                                        | Cả hai repository không phải shallow clone và đều có hai tag cần so sánh                                   |
| Git/rename detection                               | Git`2.49.0.windows.1`; net diff dùng `--find-renames`                                                          |
| Working tree                                       | `git status --short` không báo thay đổi ở cả hai repository                                                 |
| Quy mô diff toàn repository                      | 2.665 bản ghi file thay đổi; 323.147 dòng thêm, 176.246 dòng xóa theo`git diff --shortstat --find-renames` |
| Báo cáo trong`comparison/` trước bước này | Có`submodule.md`                                                                                                 |

Thống kê trên bao gồm tài liệu, test và các loại file khác; **chưa phải số file quan trọng**. Số dòng thay đổi dùng để ước lượng khối lượng đọc, không dùng để suy ra rủi ro.

Một số file đã xác nhận có net diff, dùng làm điểm bắt đầu: `src/os/bluestore/BlueStore.cc`, `src/os/bluestore/BlueFS.cc`, `src/kv/RocksDBStore.cc`, `src/osd/OSD.cc`, `src/osd/PrimaryLogPG.cc`, `src/osd/PeeringState.cc`, `src/osd/PGLog.h`, `src/osd/ECBackend.cc`, `src/mon/OSDMonitor.cc`, `src/librbd/api/DiffIterate.cc`, `src/mds/Server.cc`, `src/pybind/mgr/cephadm/upgrade.py`. Đây chưa phải kết luận về nội dung hay mức ảnh hưởng của từng file.

## 3. Cấu trúc bộ báo cáo dự kiến

Thư mục đầu ra: `comparison/pacific-16.2.5-to-16.2.15/`.

| Phần | Markdown                             | CSV thay đổi liên quan             | Nội dung và phạm vi chính                                                                                                                                                        |
| ----: | ------------------------------------ | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
|    — | `README.md`                        | —                                    | Mục lục, hai SHA nguồn, phương pháp, kết luận chính và thứ tự đọc                                                                                                      |
|    00 | `00-file-inventory.md`             | `00-file-inventory.csv`             | Markdown giữ tổng hợp/quy ước; CSV chứa toàn bộ file đổi, A/M/D/R,`+/-`, owner, ưu tiên và quyết định phân tích                                                  |
|    01 | `01-osd-pg-recovery.md`            | `01-osd-pg-recovery.csv`            | `src/osd/`, `src/erasure-code/`: OSD, PG, peering, PGLog, recovery/backfill, scrub, replication và EC                                                                           |
|    02 | `02-bluestore-bluefs.md`           | `02-bluestore-bluefs.csv`           | `src/os/bluestore/`: đường đọc/ghi, deferred writes, OMAP, metadata, mount/replay, fsck/repair                                                                                |
|    03 | `03-rocksdb-block-device.md`       | `03-rocksdb-block-device.csv`       | `src/kv/`, `src/blk/`: tích hợp RocksDB, flush/compaction, I/O thiết bị, DB/WAL                                                                                              |
|    04 | `04-mon-osdmap-crush.md`           | `04-mon-osdmap-crush.csv`           | `src/mon/`, `src/osd/OSDMap.*`, `src/crush/`: quorum, OSD map, placement, pool flags và kiểm tra phiên bản                                                                 |
|    05 | `05-messaging-auth-common.md`      | `05-messaging-auth-common.csv`      | `src/msg/`, `src/messages/`, `src/auth/`, `src/include/`, phần dùng chung trong `src/common/`: protocol, encode/decode, feature bits, caps và tài nguyên              |
|    06 | `06-config-defaults.md`            | `06-config-defaults.csv`            | Options, defaults, giới hạn và điều kiện có hiệu lực; giữ cả`.yaml`, `.yaml.in` và các định nghĩa ngoài thư mục options                                       |
|    07 | `07-mgr-modules-monitoring.md`     | `07-mgr-modules-monitoring.csv`     | `src/mgr/`, các module trong `src/pybind/mgr/` trừ nhóm đã tách; autoscaler, balancer, dashboard, metrics, alerts và thay đổi CLI/schema                                |
|    08 | `08-cephadm-orchestrator.md`       | `08-cephadm-orchestrator.csv`       | `src/cephadm/`, `src/pybind/mgr/cephadm/`, `src/pybind/mgr/orchestrator/`: upgrade, stop checks, daemon lifecycle, redeploy và xử lý lỗi                                   |
|    09 | `09-ceph-volume-activation.md`     | `09-ceph-volume-activation.csv`     | `src/ceph-volume/`, phần liên quan trong `src/python-common/`: lsblk, LVM, activation, encryption, DB/WAL và migration                                                        |
|    10 | `10-rados-rbd-clients.md`          | `10-rados-rbd-clients.csv`          | `src/librados/`, `src/neorados/`, `src/osdc/`, `src/librbd/`, `src/cls/` và tools liên quan: RADOS, RBD, fast-diff, object-map, snapshot/backup và client compatibility |
|    11 | `11-cephfs-mds.md`                 | `11-cephfs-mds.csv`                 | `src/mds/`, `src/client/`, `src/libcephfs/`, journal và module volumes/NFS liên quan: session, caps, metadata, client và điều kiện ảnh hưởng Manila                   |
|    12 | `12-rgw.md`                        | `12-rgw.csv`                        | `src/rgw/`, RGW class/tools/test liên quan: S3, policy, auth, bucket/object, multisite và các đường xử lý ảnh hưởng correctness/availability                            |
|    13 | `13-build-packaging-submodules.md` | `13-build-packaging-submodules.csv` | CMake, dependency, gitlink,`.gitmodules`, RPM/DEB, systemd và script triển khai, gồm thay đổi quyền của dịch vụ nếu có                                                  |
|    14 | `14-security-cross-reference.md`   | `14-security-cross-reference.csv`   | Security fix/CVE đã xác minh, điều kiện áp dụng và liên kết tới phân tích chính theo thành phần                                                                     |
|    15 | `15-upgrade-validation.md`         | `15-upgrade-validation.csv`         | Ma trận thay đổi → tình huống kiểm chứng; đối chiếu nhận định của tài liệu đầu vào; câu hỏi As-Is còn thiếu và giới hạn kết luận                        |

Mỗi phần `00`–`15` bàn giao theo cặp cùng basename: `.md` để đọc kết luận và `.csv` để lọc danh sách thay đổi. Markdown không nhúng lại bảng liệt kê từng file. `README.md` là mục lục tổng hợp nên không có CSV riêng.

Mỗi file nguồn có một nhóm phân tích chính. CSV của báo cáo owner chứa file đó; báo cáo khác đặt liên kết tham chiếu thay vì sao chép toàn bộ phân tích. Ví dụ `OSDMap.*` thuộc báo cá	o MON/OSDMap, còn phân tích OSD chỉ dẫn tới đó. Test và QA đi kèm thay đổi được ghi trong CSV của báo cáo thành phần; ma trận kiểm chứng tổng hợp ở phần 15.

File không có net diff nhưng cần đọc để hiểu caller/callee hoặc dữ liệu dùng chung được ghi là **ngữ cảnh**, không đưa vào danh sách file đã đổi. Với nhóm không có thay đổi quan trọng sau rà soát, ghi rõ kết quả thay vì tạo ra nhận định để lấp nội dung.

## 4. Các bước thực hiện

### Bước 1 — Chốt nguồn và tạo inventory

1. Ghi tag, SHA, trạng thái working tree và tình trạng submodule để có thể tái lập kết quả.
2. Lấy `--name-status --find-renames`, `--numstat`, mode change và gitlink diff giữa **hai đầu tag trực tiếp**.
3. Lập `00-file-inventory.csv` đầy đủ trước khi lọc, gồm runtime, cấu hình, scripts, packaging, tests, docs và dependency; `00-file-inventory.md` chỉ giữ thống kê và quy ước.
4. Tách file generated, dữ liệu lớn, dashboard assets hoặc thay đổi cơ học để tránh làm nhiễu việc ưu tiên. Không bỏ qua chúng nếu ảnh hưởng build, runtime hay bảo mật.
5. Đối chiếu số dòng CSV, tổng A/M/D/R, `+/-`, binary, mode và gitlink để không có file bị bỏ quên hoặc đếm hai lần.

Lệnh nền tảng chạy trong repository đã có đủ tag:

```bash
git diff --name-status --find-renames v16.2.5 v16.2.15
git diff --numstat --find-renames v16.2.5 v16.2.15
git diff --raw --find-renames v16.2.5 v16.2.15
```

Không cần fetch tag cho bước này vì hai repository hiện đã có đủ tag và history.

Schema chung bắt buộc của CSV inventory: `index`, `base_tag`, `target_tag`, `path`, `old_path`, `status`, `status_detail`, `additions`, `deletions`, `binary`, `old_mode`, `new_mode`, `old_blob`, `new_blob`, `group`, `owner_report`, `priority`, `file_type`, `review_mode`, `analysis_decision`, `diff_note`. CSV dùng UTF-8; `additions`/`deletions` để trống cho file nhị phân.

### Bước 2 — Chọn file quan trọng từ diff thực tế

Ưu tiên theo hành vi và điều kiện ảnh hưởng:

- **P0:** toàn vẹn dữ liệu, mount/replay, crash/deadlock, mất quorum/availability, quyền truy cập và tương thích ảnh hưởng việc nâng cấp.
- **P1:** hiệu năng data path, recovery/backfill, defaults, activation, orchestration, client/workload và automation.
- **P2:** quan sát, giao diện, công cụ phụ trợ và thay đổi ít ảnh hưởng trực tiếp; vẫn nâng ưu tiên nếu có bằng chứng tác động vận hành lớn.

Ưu tiên đọc ban đầu: BlueStore/BlueFS và OSD/PG → MON/protocol/config → MGR/cephadm/ceph-volume → RBD/CephFS/RGW → packaging/dependency và tổng hợp security. Thứ tự có thể điều chỉnh khi diff chỉ ra vấn đề quan trọng hơn.

Không giới hạn tùy ý ở “top N file”. Chưa biết dịch vụ nào đang dùng thì vẫn rà cả RBD, CephFS và RGW, đồng thời ghi rõ điều kiện áp dụng. Mức ưu tiên đọc và mức rủi ro khi nâng cấp là hai thông tin riêng.

Sau khi rà, một thay đổi chỉ được nâng thành finding Markdown khi có chuỗi tác động nâng cấp đáng tin cậy. Tác động hiếm hoặc phụ thuộc deployment vẫn được giữ và gắn điều kiện; test/doc/frontend/client/refactor/build-only không có chuỗi tác động đó được tổng hợp là `trivial/support`, nhưng không bị xóa khỏi CSV.

### Bước 3 — Đọc hunk, hàm và lịch sử commit

Với từng file quan trọng:

1. Đọc patch có đủ ngữ cảnh và hai phiên bản của hàm/kiểu dữ liệu liên quan.
2. Lần caller/callee, schema hoặc option nếu chỉ nhìn hunk chưa giải thích được hành vi.
3. Tìm commit trong `v16.2.5..v16.2.15`, đọc toàn bộ commit và test sửa cùng lúc.
4. Theo PR/issue hoặc commit backport khi cần làm rõ lý do; ghi “chưa xác minh” nếu nguồn chưa đủ.
5. Nhóm nhiều file cùng sửa một vấn đề thành một mục thay đổi; ghi danh sách đường dẫn và metadata diff đầy đủ vào CSV của phần tương ứng.

Phải phân biệt **net diff ở hai đầu** với **lịch sử thay đổi ở giữa**. Một lỗi chỉ xuất hiện ở bản trung gian rồi được sửa không tự động là lỗi tồn tại trên 16.2.5. Commit từng được thêm rồi revert có thể có ý nghĩa lịch sử nhưng không nhất thiết tạo khác biệt cuối cùng.

### Bước 4 — Đối chiếu tài liệu và dependencies

Nhận định trong `ceph-analysis.md` là các câu hỏi để kiểm chứng, gồm:

- Deferred writes và OMAP conversion/quick-fix; phạm vi áp dụng theo lịch sử cluster.
- PGLog inflation, công cụ trim và các thay đổi peering/recovery.
- MGR deadlock và thay đổi autoscaler/bulk/noautoscale.
- ceph-volume activation, LVM/lsblk và DB/WAL.
- MDS session metadata, path restriction và điều kiện liên quan CephFS/Manila.
- RBD diff-iterate, fast-diff, object-map và exclusive-lock.
- RGW POST policy và các security/availability fix được tài liệu nêu.
- ceph-crash, quyền chạy dịch vụ và packaging.

Tra release notes/PR/advisory chính thức khi cần xác minh phiên bản, CVE hoặc điều kiện lỗi; không lấy số CVE hoặc tuyên bố hiệu năng từ tài liệu đầu vào làm bằng chứng duy nhất.

Đối chiếu gitlink trực tiếp trước khi dùng lại `comparison/submodule.md`. Nếu dependency đổi SHA, đọc thay đổi bên trong dependency khi source/object có sẵn; nếu thiếu thì ghi rõ phần chưa thể kết luận. Nếu gitlink giữ nguyên, vẫn kiểm tra integration code và build flags có đổi hay không.

Những chủ đề như mClock trở thành default ở Quincy, RocksDB 7.9.2 của Reef hoặc đường nâng Pacific → Reef chỉ được ghi trong phần ngoài phạm vi, trừ khi phát hiện một thay đổi Pacific độc lập và có bằng chứng.

### Bước 5 — Viết báo cáo theo mẫu thống nhất

Mỗi phần bàn giao một cặp Markdown/CSV cùng basename. Báo cáo Markdown có:

1. Vai trò của thành phần và phạm vi file đã rà.
2. Liên kết tới CSV chứa các file thay đổi liên quan; không lặp bảng file trong Markdown.
3. Các thay đổi chính, có hunk ngắn hoặc đoạn code trước/sau khi cần.
4. Tác động lúc rolling upgrade và sau khi toàn cụm lên 16.2.15.
5. Tình huống kiểm chứng, test liên quan và các điểm còn thiếu bằng chứng.
6. Một mục tổng hợp `trivial/support` cho phần diff không ảnh hưởng quyết định nâng cấp; không viết một finding cho từng file.

CSV của từng phần là tập con theo owner từ `00-file-inventory.csv`, giữ nguyên schema chung và thứ tự cột. Khi hoàn tất phân tích, có thể bổ sung `upgrade_disposition`, `finding_id`, `disposition_reason`, `symbols`, `commit_shas` hoặc `evidence_status` ở bên phải; các cột nền không được bỏ hay đổi. File ngữ cảnh không có net diff chỉ được nhắc trong Markdown, không được đưa vào CSV thay đổi.

Mẫu cho một thay đổi:

| Trường                 | Nội dung bắt buộc                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| ID                       | Mã ổn định, ví dụ`BS-001`, để liên kết giữa các báo cáo                                    |
| File/hàm                | Đường dẫn, symbol và vị trí ở cả hai tag nếu xác định được                                 |
| Bằng chứng             | Hunk/đoạn code, commit SHA; PR/issue và test nếu tìm thấy                                            |
| Trước → sau           | Hành vi khác nhau, diễn giải từ code                                                                  |
| Điều kiện kích hoạt | Cấu hình, loại pool/image/client, deployment mode hoặc trạng thái dữ liệu                          |
| Tác động              | Correctness, availability, security, performance hoặc vận hành; phân biệt mixed-version và sau nâng |
| Có hiệu lực khi nào  | Tự có sau nâng daemon, phụ thuộc cấu hình/feature hay cần thao tác riêng                         |
| Mức đánh giá         | Ưu tiên đọc, rủi ro có lý do, độ chắc chắn và phần còn là suy luận                         |
| Kiểm chứng             | Test trong repository và kịch bản kiểm chứng đề xuất; ghi rõ chưa chạy nếu chỉ đọc test     |

Liên kết code được cố định theo tag/SHA để tránh trôi dòng theo nhánh. Dùng đoạn diff đủ để giải thích; không chép toàn bộ patch lớn vào từng báo cáo.

### Bước 6 — Kiểm tra bộ báo cáo

- Mỗi file trong inventory được gán nhóm hoặc có lý do chỉ liệt kê, không phân tích sâu.
- Mọi file được gọi là “đã đổi” đều có trong diff thực tế; file ngữ cảnh được phân biệt rõ.
- Mỗi phần `00`–`15` có đủ cặp `.md`/`.csv`; Markdown không chứa bảng liệt kê file thay đổi.
- Mỗi CSV thành phần là tập con hợp lệ của `00-file-inventory.csv`; tổng các dòng owner chính bằng 2.665 và không trùng owner.
- Header, kiểu dữ liệu, UTF-8, số dòng và tổng A/M/D/R, `+/-`, binary, mode/gitlink được kiểm tra trước khi bàn giao.
- Mỗi kết luận quan trọng có bằng chứng code, điều kiện áp dụng và cách kiểm chứng.
- Mọi dòng CSV được bao phủ bởi finding có liên quan nâng cấp hoặc mục tổng hợp `trivial/support`; Markdown không phân tích sâu phần không ảnh hưởng.
- Không lẫn thay đổi trước baseline hoặc Quincy/Reef vào lợi ích của 16.2.5 → 16.2.15.
- Các nhận định đầu vào được đánh dấu: đã xác nhận, cần sửa, ngoài phạm vi hoặc chưa đủ bằng chứng.
- Security cross-reference và báo cáo thành phần không mâu thuẫn, không phân tích lặp toàn bộ cùng một vấn đề.
- Liên kết nội bộ, đường dẫn code, tag/SHA và thống kê được kiểm tra nhất quán.

## 5. Điều kiện hoàn thành và giới hạn

Hoàn thành khi có cặp inventory đầy đủ, đủ cặp Markdown/CSV cho từng nhóm, và ma trận kiểm chứng truy được từ thay đổi → bằng chứng → tác động có điều kiện. Markdown giữ phân tích upgrade-relevant cùng một tóm tắt trivial/support; CSV giữ đầy đủ danh sách file thay đổi và metadata diff.

Không cần As-Is inventory để bắt đầu phân tích code. Thông tin deployment mode, dịch vụ đang sử dụng, client, storage layout và cấu hình override sẽ được ghi thành các câu hỏi áp dụng cho cluster cụ thể. Chưa có các thông tin và kết quả thử nghiệm đó thì không đưa ra kết luận GO/NO-GO Production hoặc số liệu cải thiện hiệu năng.

Đây là công việc phân tích và tạo tài liệu. Các lệnh repair, trim, migrate, thay cấu hình hay nâng daemon không thuộc bước thực hiện báo cáo. Build và chạy test tích hợp Ceph cũng không phải điều kiện để hoàn thành việc đọc diff; nếu chỉ đọc test trong repository thì báo cáo ghi đúng trạng thái đó.

## 6. Thứ tự bàn giao

1. Cặp inventory `.md`/`.csv`, nguồn và phân nhóm để thấy toàn bộ phạm vi thay đổi.
2. Các cặp báo cáo lõi lưu trữ: OSD/PG, BlueStore/BlueFS, RocksDB/device và MON/OSDMap.
3. Các cặp báo cáo protocol/config, MGR/monitoring, cephadm và ceph-volume.
4. Các cặp báo cáo RADOS/RBD, CephFS và RGW.
5. Các cặp packaging/submodules, security, validation và README tổng hợp.

Plan đã được áp dụng cho `00-file-inventory.{md,csv}` và đủ mười lăm cặp `01`–`15`. Component partition, immutable CSV prefix, disposition/evidence, thống kê và liên kết chéo đã được đối soát; giới hạn còn lại là dữ liệu As-Is và runtime/lab/canary evidence của cluster đích, không phải scope phân tích source.
