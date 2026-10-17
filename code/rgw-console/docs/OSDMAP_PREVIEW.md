# Xem trước thay đổi OSDMap

Mở **Thu thập hiện trạng → Xem trước thay đổi OSDMap**. Chọn một hoặc nhiều OSD, nhập CRUSH weight giả định và chọn Pool ID replicated, rồi bấm **Tính tác động**. Mỗi lần tính đọc map mới qua SSH. Để trống chỉ được tính tất cả pool khi tất cả đều replicated và thuộc allowlist; EC/kiểu pool chưa kiểm bị từ chối, không bỏ qua rồi gọi kết quả là toàn cụm.

Kết quả ghi **Dự đoán — chưa áp dụng**. Bảng PG phân biệt raw/up/acting và primary; bảng phân bố OSD chính thống kê acting, gồm cả OSD ngoài tập thay đổi. JSON còn có phân bố raw/up/acting riêng, parser version 2, digest hai binary và hash output placement/CRUSH. Nếu map thiếu thành viên thì hiện cảnh báo PARTIAL ở cả map gốc/giả định. Không tự chứng minh failure-domain hoặc sức khỏe peering; ngay cả no-change cũng không phải kết luận an toàn. Đổi primary trong phần tổng kết có thể chỉ đổi raw primary: cần xem ba giá trị để hiểu đúng. PG không tương đương số byte hay thời gian recovery. Xuất dự đoán tải JSON đã lưu, không tính lại map. Nút **Kiểm tra epoch hiện tại** đọc epoch mới; nếu khác map nguồn, hãy tính lại.

## Thao tác được hỗ trợ

Bản đầu hỗ trợ **CRUSH reweight native Pacific 16.2.15**. `--adjust-crush-weight` gọi `adjust_item_weightf` với `update_weight_sets=true`; vì vậy weight-set của OSD và parent liên quan cũng được đồng bộ. Giao diện báo weight-set có thay đổi và effective weight sau lượng tử hóa 1/65536. Việc nhập lại canonical weight đang có vẫn có thể đồng bộ một weight-set khác giá trị và làm đổi placement. Đây chưa phải adapter thay canonical weight độc lập trong khi giữ nguyên compat weight-set. [Source hàm điều chỉnh](https://github.com/ceph/ceph/blob/v16.2.15/src/crush/CrushWrapper.h#L935-L944), [đồng bộ weight-set](https://github.com/ceph/ceph/blob/v16.2.15/src/crush/CrushWrapper.cc#L2348-L2367).

Dải nhập đã kiểm là **0–32767**. Tool dùng float32/fixed-point signed int; không dùng dải 65535 vì có trường hợp tool bỏ qua overflow nhưng vẫn in thông báo đã điều chỉnh. Worker đọc CRUSH trước/sau và kiểm effective weight thật trước khi tạo báo cáo. Không hỗ trợ reweight OSD, up/down/in/out, primary-affinity, pool PG config hay chỉnh rule/topology qua form này.

Trước khi tính, API đọc config hiệu lực `osd_crush_update_weight_set` của từng MON và kiểm phiên bản MON. Adapter hiện chỉ nhận MON 16.2.15 và tất cả MON đồng bộ weight-set=true; source thiếu, mode=false hoặc release khác bị từ chối rõ. Console không đổi config để vượt qua điều kiện. Ceph MON dùng chính setting này khi thực hiện CRUSH reweight: [OSDMonitor.cc](https://github.com/ceph/ceph/blob/v16.2.15/src/mon/OSDMonitor.cc#L10352-L10353).

Map gốc giữ nguyên byte/checksum. Kịch bản thay đổi trong bộ nhớ của osdmaptool; worker xuất CRUSH nội bộ để kiểm chứng, không xuất map OSD ứng viên đã áp dụng. pg_temp/primary_temp/upmap/flags không được tự làm sạch. Artifact giữ map nguồn và hash nội bộ; file tải về giữ thông số, diff, effective weight, tool version, hash choose_args và giới hạn, không chứa SSH key/token.

## Giới hạn an ninh của worker

Worker dựa trên image Ceph Pacific cũ để giữ semantics đã kiểm. Scan release candidate `16.2.15-rc.1` ngày 12/10/2026 ghi 9 Critical, 333 High, 1333 Medium, 481 Low và 18 unspecified. **Chỉ dùng lab/offline, chưa được chấp thuận production.** Network-none, UID không root, root filesystem chỉ đọc, không credential và giới hạn tài nguyên là giảm phạm vi tác động, không phải sửa CVE. Không bật overlay này trong production mặc định. Cần worker/toolchain đã vá và nghiệm thu lại trước khi chấp thuận production. Image console chính không cần worker để dùng As-is/metric/comparison.

## Đóng gói và cấu hình

Ứng dụng và worker mô phỏng là hai image riêng. Để dùng đúng RC1 đã kiểm, tải image theo digest; không rebuild source nhánh đang sửa rồi gắn lại tag RC1:

```powershell
docker pull dang7904/storage-lab-console@sha256:36b6b7b1664958b792dda841cf7140ab9e0006d3aff436d8b8823056451c86f4
docker pull dang7904/storage-lab-osdmap@sha256:65025d1fb24e90b87ec623b805946bcc6252bce43f8bfd198e70d6ef2a63cdad
```

Worker dùng Ceph image 16.2.15 được pin digest trong Dockerfile, Python 3.6 của image và `osdmaptool`/`crushtool` cùng build. Chỉ amd64 đã kiểm; binary digests được kiểm khi startup, không nhận tool tùy ý hoặc architecture khác. Worker chạy UID 10001, root filesystem chỉ đọc, `network_mode: none`, giới hạn CPU/RAM/PID, và chỉ mount spool. Không mount SSH key, keyring, executor token, database secret hay cấu hình Ceph vào worker.

API đặt `OSDMAP_PREVIEW_SPOOL=/var/lib/storage-lab-console/osdmap-spool` và mount cùng volume mà worker nhìn tại `/spool`. Volume cần owner 10001:10001. Có overlay [compose.osdmap.yml](../deploy/compose.osdmap.yml); initialize quyền volume bằng tác vụ chown riêng trước khi bật. Ví dụ với project `storage-lab-console-production`, volume mặc định là `storage-lab-console-production_osdmap_spool`:

```powershell
docker volume create storage-lab-console-production_osdmap_spool
docker run --rm --network none --user 0:0 --cap-drop ALL --cap-add CHOWN --mount type=volume,source=storage-lab-console-production_osdmap_spool,target=/spool --entrypoint /bin/chown dang7904/storage-lab-osdmap:16.2.15-rc.1 10001:10001 /spool
```

Đặt `OSDMAP_PREVIEW_IMAGE` thành digest của image worker đã kiểm. Khi đổi Compose project name phải dùng tên volume của project đó. Với localhost hiện có, dùng [update-local-v5.ps1](../deploy/update-local-v5.ps1), script tự initialize spool, chạy migration bổ sung và giữ container cũ; script này chỉ dành cho deployment local đã xác minh, không dùng như bootstrap production.

API capability báo chưa sẵn sàng nếu worker không có heartbeat. Mỗi kịch bản giới hạn 128 OSD, map 16 MiB, 100000 PG và tối đa 90 giây mặc định; output quá lớn bị từ chối rõ. Bản này chưa có tác vụ purge kịch bản hoặc pipeline giả lập cho Ceph release khác.

## Runtime tối giản thử nghiệm chưa phát hành

Ngày 13/10/2026 đã build local `storage-lab-osdmap:16.2.15-minimal-preview.1`. Tại thời điểm build prototype này Dockerfile mặc định, Docker Hub và localhost vẫn RC1. Localhost hiện dùng app `5.1.1-preview.2` + worker `16.2.15-minimal-preview.2`, chỉ lab/chỉ đọc; [manifest hiện tại](../deploy/releases/5.1.1-preview.2.yaml). Hub/default production không đổi. Image runtime mới chỉ lấy hai executable và `libceph-common.so.2` từ donor Ceph; SHA cả ba file giữ nguyên. Các thư viện OS/Python 3.12 được cài từ [repo UBI chính thức](https://access.redhat.com/articles/4238681) trên base UBI8-minimal pinned, không lấy OS libraries cũ từ donor. Giữ license, source URL, RPM database thật, manifest dependency closure và SPDX cho phần Ceph được trích file.

17/17 worker tests qua; ba differential scenarios trên cùng map tạo offline khớp placement raw/up/acting, primary, CRUSH bytes, effective weight và choose_args. Dòng stdout thông báo đường dẫn xuất CRUSH dùng thư mục tạm khác nhau nên chỉ dòng đó được chuẩn hóa trong báo cáo so sánh, không sửa checksum evidence thật. Backend nhánh `5.1.1-preview.1` bắt buộc handshake/result đầy đủ cùng version/parser/hash/phạm vi pool; hồ sơ cũ vẫn đọc được.

Scout toàn image preview.1 báo raw findings **1 Critical/28 High/40 Medium/6 Low**, so với RC1 **9/333/1333/481**. Scanner ghi SQLite `CVE-2026-51302` Critical/Not Fixed, nhưng [CNA đã rút CVE ngày 31/07/2026](https://cveawg.mitre.org/api/cve/CVE-2026-51302) vì không phải vấn đề bảo mật; [upstream SQLite](https://www.sqlite.org/cves.html) cũng bác nhóm sáu ID liên quan. Đây là finding cần reconcile với nguồn chính thức, không phải bản vá hoặc waiver. Không sửa raw report, suppress CVE, bỏ RPM metadata hoặc dùng scan SBOM trích file không có finding để tuyên bố Ceph EOL đã an toàn. **Chưa đạt production; tại thời điểm kiểm thử preview.1 chưa promote/publish/thay deployment.** [Manifest local](../deploy/releases/5.1.1-preview.1.yaml) và [VALIDATION](../VALIDATION.md) giữ digest/scan/checksum/test đầy đủ.

Muốn build và test riêng từ thư mục `code` (không cập nhật localhost):

```powershell
docker build --platform linux/amd64 -t storage-lab-osdmap:16.2.15-minimal-preview.1 -f rgw-console/packaging/osdmap/Dockerfile.minimal rgw-console/packaging/osdmap

# Mount test source read-only, không mount key/config Ceph hoặc bật network.
$workerTests = (Resolve-Path rgw-console/packaging/osdmap).Path
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1536m --cpus 1 --pids-limit 32 --tmpfs '/tmp:rw,noexec,nosuid,size=128m,mode=1777' --mount "type=bind,src=$workerTests,dst=/tests,readonly" --workdir /tests --entrypoint /usr/bin/python3.12 storage-lab-osdmap:16.2.15-minimal-preview.1 -m unittest -v test_worker
```

Mỗi build cập nhật repo có thể cho dependency versions khác; phải kiểm manifest trong chính image, scan lại và pin digest image đã kiểm. Không thay `OSDMAP_PREVIEW_IMAGE` production hoặc chạy update-local chỉ vì prototype nhỏ hơn. Các phần còn lại (integration, residual CVE, release/site acceptance) phải hoàn tất trước quyết định promote.

### Bản thử nghiệm preview.2 có gỡ package quản lý

Flag `STRIP_PACKAGE_MANAGER_EXTRAS=true` thực hiện uninstall thật 13 package quản lý, gồm GnuTLS/GnuPG, giữ RPM database/query/chown/Python và tool closure. Bản local đã kiểm là `16.2.15-minimal-preview.2`, digest/scan/test trong [manifest riêng](../deploy/releases/osdmap-16.2.15-minimal-preview.2.yaml). Raw findings còn 1C/21H/35M/2L; Critical thuộc CVE đã bị CNA rút, ba vendor-affected thật còn OpenSSL/PCRE2/Expat. Không gọi đây là production-ready hoặc nhỏ hơn preview.1 về layer bytes.

17 worker tests, 9 guard tests và ba differential scenarios đạt; bốn replay API/worker/DB đạt 38/38. Lượt integration đầu thất bại ở kiểm tampered identity chưa được xác nhận nguyên nhân, được giữ lại với stability gate OPEN. **Không promote production hoặc coi các replay PASS là đóng lỗi đầu.** Lần chạy localhost lab theo yêu cầu riêng không đóng stability/security gate; cấu hình opt-in và kiểm sau đổi ở [hướng dẫn triển khai](../deploy/README.md#cấu-hình-localhost-hiện-tại--chỉ-lab).

Build riêng, từ thư mục `code`, không thay localhost:

```powershell
docker build --platform linux/amd64 --build-arg APP_VERSION=16.2.15-minimal-preview.2 --build-arg STRIP_PACKAGE_MANAGER_EXTRAS=true -t storage-lab-osdmap:16.2.15-minimal-preview.2 -f rgw-console/packaging/osdmap/Dockerfile.minimal rgw-console/packaging/osdmap
```
