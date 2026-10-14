# Xem trước thay đổi OSDMap

Mở **Thu thập hiện trạng → Xem trước thay đổi OSDMap**. Chọn một hoặc nhiều OSD, nhập CRUSH weight giả định và chọn Pool ID replicated, rồi bấm **Tính tác động**. Mỗi lần tính đọc map mới qua SSH. Để trống chỉ được tính tất cả pool khi tất cả đều replicated và thuộc allowlist; EC/kiểu pool chưa kiểm bị từ chối, không bỏ qua rồi gọi kết quả là toàn cụm.

Kết quả ghi **Dự đoán — chưa áp dụng**. Bảng PG phân biệt raw/up/acting và primary; bảng phân bố OSD chính thống kê acting, gồm cả OSD ngoài tập thay đổi. JSON còn có phân bố raw/up/acting riêng, parser version 2, digest hai binary và hash output placement/CRUSH. Nếu map thiếu thành viên thì hiện cảnh báo PARTIAL ở cả map gốc/giả định. Không tự chứng minh failure-domain hoặc sức khỏe peering; ngay cả no-change cũng không phải kết luận an toàn. Đổi primary trong phần tổng kết có thể chỉ đổi raw primary: cần xem ba giá trị để hiểu đúng. PG không tương đương số byte hay thời gian recovery. Xuất dự đoán tải JSON đã lưu, không tính lại map. Nút **Kiểm tra epoch hiện tại** đọc epoch mới; nếu khác map nguồn, hãy tính lại.

## Thao tác được hỗ trợ

Bản đầu hỗ trợ **CRUSH reweight native Pacific 16.2.15**. `--adjust-crush-weight` gọi `adjust_item_weightf` với `update_weight_sets=true`; vì vậy weight-set của OSD và parent liên quan cũng được đồng bộ. Giao diện báo weight-set có thay đổi và effective weight sau lượng tử hóa 1/65536. Việc nhập lại canonical weight đang có vẫn có thể đồng bộ một weight-set khác giá trị và làm đổi placement. Đây chưa phải adapter thay canonical weight độc lập trong khi giữ nguyên compat weight-set. [Source hàm điều chỉnh](https://github.com/ceph/ceph/blob/v16.2.15/src/crush/CrushWrapper.h#L935-L944), [đồng bộ weight-set](https://github.com/ceph/ceph/blob/v16.2.15/src/crush/CrushWrapper.cc#L2348-L2367).

Dải nhập đã kiểm là **0–32767**. Tool dùng float32/fixed-point signed int; không dùng dải 65535 vì có trường hợp tool bỏ qua overflow nhưng vẫn in thông báo đã điều chỉnh. Worker đọc CRUSH trước/sau và kiểm effective weight thật trước khi tạo báo cáo. Không hỗ trợ reweight OSD, up/down/in/out, primary-affinity, pool PG config hay chỉnh rule/topology qua form này.

Trước khi tính, API đọc config hiệu lực `osd_crush_update_weight_set` của từng MON và kiểm phiên bản MON. Adapter hiện chỉ nhận MON 16.2.15 và tất cả MON đồng bộ weight-set=true; source thiếu, mode=false hoặc release khác bị từ chối rõ. Console không đổi config để vượt qua điều kiện. Ceph MON dùng chính setting này khi thực hiện CRUSH reweight: [OSDMonitor.cc](https://github.com/ceph/ceph/blob/v16.2.15/src/mon/OSDMonitor.cc#L10352-L10353).

Map gốc giữ nguyên byte/checksum. Kịch bản thay đổi trong bộ nhớ của osdmaptool; worker xuất CRUSH nội bộ để kiểm chứng, không xuất map OSD ứng viên đã áp dụng. pg_temp/primary_temp/upmap/flags không được tự làm sạch. Artifact giữ map nguồn và hash nội bộ; file tải về giữ thông số, diff, effective weight, tool version, hash choose_args và giới hạn, không chứa SSH key/token.

## Giới hạn an ninh của worker

Worker đã phát hành cho lab là `16.2.15-minimal-preview.2`, giữ hai tool Ceph Pacific 16.2.15 đã kiểm trong runtime tối giản Python 3.12. Báo cáo Scout trong [manifest phát hành ngày 13/10/2026](../deploy/releases/5.1.1-rc.1.yaml) ghi **1 Critical, 21 High, 35 Medium, 2 Low** trên 133 package; đây là kết quả scan tại thời điểm ghi nhận, không phải scan mới. Triage lưu trong repo ghi Critical thuộc CVE đã bị CNA rút và vẫn còn ba finding vendor-affected thuộc OpenSSL, PCRE2, Expat. **Chỉ dùng lab/offline, chưa được chấp thuận production.** Network-none, UID không root, root filesystem chỉ đọc, không credential và giới hạn tài nguyên là giảm phạm vi tác động, không phải sửa CVE. Không bật overlay này trong production mặc định. Cần worker/toolchain đã vá và nghiệm thu lại trước khi chấp thuận production. Image console chính không cần worker để dùng As-is/metric/comparison.

## Đóng gói và cấu hình

Ứng dụng và worker mô phỏng là hai image riêng. Cài image ứng dụng theo ref và các bước trong [README cài đặt](../../README.md). Worker tùy chọn đã phát hành dùng ref cố định sau; không rebuild source rồi gắn lại tag đã phát hành:

```powershell
docker pull dang7904/storage-lab-osdmap@sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893
```

Worker được build bằng [Dockerfile.minimal](../packaging/osdmap/Dockerfile.minimal): chỉ lấy `osdmaptool`, `crushtool` và `libceph-common.so.2` từ donor Ceph 16.2.15 pin digest; runtime UBI8-minimal dùng Python 3.12 và thư viện hệ điều hành từ repo UBI. Hash ba file Ceph giữ nguyên so với donor. Chỉ amd64 đã kiểm; binary digests được kiểm khi startup, không nhận tool tùy ý hoặc architecture khác. Worker chạy UID 10001, root filesystem chỉ đọc, `network_mode: none`, giới hạn CPU/RAM/PID, và chỉ mount spool. Không mount SSH key, keyring, executor token, database secret hay cấu hình Ceph vào worker.

API đặt `OSDMAP_PREVIEW_SPOOL=/var/lib/storage-lab-console/osdmap-spool` và mount cùng volume mà worker nhìn tại `/spool`. Volume cần owner 10001:10001. Có overlay [compose.osdmap.yml](../deploy/compose.osdmap.yml); initialize quyền volume bằng tác vụ chown riêng trước khi bật. Ví dụ với project `storage-lab-console-production`, volume mặc định là `storage-lab-console-production_osdmap_spool`:

```powershell
docker volume create storage-lab-console-production_osdmap_spool
docker run --rm --network none --user 0:0 --cap-drop ALL --cap-add CHOWN --mount type=volume,source=storage-lab-console-production_osdmap_spool,target=/spool --entrypoint /bin/chown dang7904/storage-lab-osdmap@sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893 10001:10001 /spool
```

Đặt `OSDMAP_PREVIEW_IMAGE` thành ref worker theo digest ở trên. Khi đổi Compose project name phải dùng tên volume của project đó. Luồng cài mới nằm trong [README cài đặt](../../README.md); với stack localhost đã có sẵn, xem [hướng dẫn cập nhật local](../deploy/README.md#localhost-đã-có-sẵn). Updater local chỉ dành cho deployment đã xác minh, không dùng như bootstrap máy mới hoặc production.

API capability báo chưa sẵn sàng nếu worker không có heartbeat. Mỗi kịch bản giới hạn 128 OSD, map 16 MiB, 100000 PG và tối đa 90 giây mặc định; output quá lớn bị từ chối rõ. Bản này chưa có tác vụ purge kịch bản hoặc pipeline giả lập cho Ceph release khác.

<a id="runtime-tối-giản-thử-nghiệm-chưa-phát-hành"></a>

## Lịch sử thử nghiệm runtime tối giản preview.1

Phần này giữ kết quả prototype ngày 13/10/2026, không phải hướng dẫn chọn image hiện tại. Khi build local `storage-lab-osdmap:16.2.15-minimal-preview.1`, Dockerfile mặc định, Docker Hub và localhost lúc đó vẫn RC1. Lần chuyển localhost sang app `5.1.1-preview.2` + worker `16.2.15-minimal-preview.2` sau đó được ghi riêng trong [manifest lịch sử](../deploy/releases/5.1.1-preview.2.yaml); việc phát hành worker preview.2 được ghi trong [manifest phát hành](../deploy/releases/5.1.1-rc.1.yaml). Image runtime tối giản chỉ lấy hai executable và `libceph-common.so.2` từ donor Ceph; SHA cả ba file giữ nguyên. Các thư viện OS/Python 3.12 được cài từ [repo UBI chính thức](https://access.redhat.com/articles/4238681) trên base UBI8-minimal pinned, không lấy OS libraries cũ từ donor. Giữ license, source URL, RPM database thật, manifest dependency closure và SPDX cho phần Ceph được trích file.

17/17 worker tests qua; ba differential scenarios trên cùng map tạo offline khớp placement raw/up/acting, primary, CRUSH bytes, effective weight và choose_args. Dòng stdout thông báo đường dẫn xuất CRUSH dùng thư mục tạm khác nhau nên chỉ dòng đó được chuẩn hóa trong báo cáo so sánh, không sửa checksum evidence thật. Backend nhánh `5.1.1-preview.1` bắt buộc handshake/result đầy đủ cùng version/parser/hash/phạm vi pool; hồ sơ cũ vẫn đọc được.

Scout toàn image preview.1 khi đó báo raw findings **1 Critical/28 High/40 Medium/6 Low**, so với worker RC1 cũ ngày 12/10/2026 **9 Critical/333 High/1333 Medium/481 Low/18 unspecified**. Scanner ghi SQLite `CVE-2026-51302` Critical/Not Fixed, nhưng [CNA đã rút CVE ngày 31/07/2026](https://cveawg.mitre.org/api/cve/CVE-2026-51302) vì không phải vấn đề bảo mật; [upstream SQLite](https://www.sqlite.org/cves.html) cũng bác nhóm sáu ID liên quan. Đây là finding cần reconcile với nguồn chính thức, không phải bản vá hoặc waiver. Không sửa raw report, suppress CVE, bỏ RPM metadata hoặc dùng scan SBOM trích file không có finding để tuyên bố Ceph EOL đã an toàn. **Chưa đạt production; tại thời điểm kiểm thử preview.1 chưa promote/publish/thay deployment.** [Manifest local](../deploy/releases/5.1.1-preview.1.yaml) và [VALIDATION](../VALIDATION.md) giữ digest/scan/checksum/test đầy đủ.

Muốn build và test riêng từ thư mục `code` (không cập nhật localhost):

```powershell
docker build --platform linux/amd64 -t storage-lab-osdmap:16.2.15-minimal-preview.1 -f rgw-console/packaging/osdmap/Dockerfile.minimal rgw-console/packaging/osdmap

# Mount test source read-only, không mount key/config Ceph hoặc bật network.
$workerTests = (Resolve-Path rgw-console/packaging/osdmap).Path
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1536m --cpus 1 --pids-limit 32 --tmpfs '/tmp:rw,noexec,nosuid,size=128m,mode=1777' --mount "type=bind,src=$workerTests,dst=/tests,readonly" --workdir /tests --entrypoint /usr/bin/python3.12 storage-lab-osdmap:16.2.15-minimal-preview.1 -m unittest -v test_worker
```

Mỗi build cập nhật repo có thể cho dependency versions khác; phải kiểm manifest trong chính image, scan lại và pin digest image đã kiểm. Không thay `OSDMAP_PREVIEW_IMAGE` production hoặc chạy update-local chỉ vì prototype nhỏ hơn. Các phần còn lại (integration, residual CVE, release/site acceptance) phải hoàn tất trước quyết định promote.

### Preview.2: từ thử nghiệm đến bản phát hành cho lab

Flag `STRIP_PACKAGE_MANAGER_EXTRAS=true` thực hiện uninstall thật 13 package quản lý, gồm GnuTLS/GnuPG, giữ RPM database/query/chown/Python và tool closure. Bản đã kiểm là `16.2.15-minimal-preview.2`; [manifest thử nghiệm](../deploy/releases/osdmap-16.2.15-minimal-preview.2.yaml) giữ kết quả trước khi phát hành, còn [manifest phát hành ngày 13/10/2026](../deploy/releases/5.1.1-rc.1.yaml) xác nhận push/pull Docker Hub đúng digest. Raw findings tại lần scan đó còn 1C/21H/35M/2L; Critical thuộc CVE đã bị CNA rút, ba vendor-affected thật còn OpenSSL/PCRE2/Expat. Không gọi đây là production-ready hoặc nhỏ hơn preview.1 về layer bytes.

Trong đợt kiểm thử preview.2: 17 worker tests, 9 guard tests và ba differential scenarios đạt; bốn replay API/worker/DB đạt 38/38. Lượt integration đầu thất bại ở kiểm tampered identity chưa được xác nhận nguyên nhân, được giữ lại với stability gate OPEN. **Không promote production hoặc coi các replay PASS là đóng lỗi đầu.** Việc phát hành và chạy localhost lab không đóng stability/security gate; cấu hình opt-in và kiểm sau đổi ở [hướng dẫn triển khai](../deploy/README.md#localhost-đã-có-sẵn).

Build riêng, từ thư mục `code`, không thay localhost:

```powershell
docker build --platform linux/amd64 --build-arg APP_VERSION=16.2.15-minimal-preview.2 --build-arg STRIP_PACKAGE_MANAGER_EXTRAS=true -t storage-lab-osdmap:16.2.15-minimal-preview.2 -f rgw-console/packaging/osdmap/Dockerfile.minimal rgw-console/packaging/osdmap
```
