# Tổng hợp lý thuyết Storage Lab Console

Tài liệu này tập hợp mục đích, kiến trúc, nguyên lý thu thập và cách hiểu dữ liệu của console. Các lệnh cài đặt/cập nhật image nằm trong [README.md](README.md) và [README triển khai](rgw-console/deploy/README.md); không dùng tài gitliệu lý thuyết làm runbook triển khai.

## 1. Mục đích và phạm vi

Storage Lab Console hỗ trợ quan sát cluster Ceph, thu bằng chứng hiện trạng và so sánh hai lần thu. Phạm vi theo daemon: MON, MGR, OSD, RGW và MDS; đồng thời giữ ngữ cảnh hệ thống/cụm.

Console đọc Ceph nhưng vẫn ghi dữ liệu của chính ứng dụng: collection As-is, lịch sử, evidence và metadata. Vì vậy, “chỉ đọc Ceph” không có nghĩa database của console không thay đổi.

Các luồng chính:

- Chỉ số cụm và daemon: đọc nguồn mới theo yêu cầu người dùng.
- Thu thập hiện trạng: lưu bộ As-is cho một hoặc nhiều daemon.
- So sánh: xét hai bộ As-is cùng cụm và cùng loại daemon.
- Xem trước OSDMap: tính giả định trên bản sao map cho phạm vi được hỗ trợ.

Console hiện không thực hiện nâng cấp, Apply hoặc ghi cấu hình Ceph; benchmark và dry-run nâng cấp đã được loại khỏi sản phẩm. Công cụ cũ được gom trong navigation thu gọn và bị khóa ở deployment chỉ đọc.

## 2. Kiến trúc và vai trò

Một application image đóng gói frontend và các role ứng dụng; mỗi container chọn role khi khởi động. Không phải chỉ chạy một container image là có đủ toàn bộ hệ thống.

```text
Trình duyệt → Ingress TLS → API ──→ PostgreSQL / kho evidence
                           │
                           ├──→ Executor → SSH → management host → Ceph
                           ├──→ nguồn telemetry / Prometheus khi được cấu hình
                           └──→ spool ↔ worker OSDMap offline, tùy chọn

Collector dung lượng / hiệu năng → dữ liệu quan sát của console
```

- Frontend: lựa chọn phạm vi, gửi yêu cầu, hiển thị thời điểm/chất lượng và tải tệp.
- API: xác minh cluster, điều phối thu thập, lưu As-is, lọc lịch sử, so sánh và xuất dữ liệu.
- Executor: thực hiện các lệnh đọc được cho phép qua SSH; không cung cấp arbitrary shell API.
- OSD info collector: helper trên management host, giữ dữ liệu môi trường và evidence chuyên sâu OSD.
- PostgreSQL: registry collection, hash, metadata, lịch sử xóa mềm và dữ liệu ứng dụng.
- Evidence store: lưu artifact/bằng chứng ngoài bản ghi metadata.
- Capacity/performance collector: nguồn quan sát nền; không thay thế yêu cầu đọc mới theo từng lần bấm.
- Ingress: TLS và đường vào API có xác thực.
- Worker OSDMap: image riêng, không có network hoặc SSH/Ceph credential; trao đổi qua spool và chỉ tính offline.

Profile xác định cluster/phạm vi; secret cấp khả năng kết nối. Không đóng gói profile thật, password, token hoặc SSH key vào image.

## 3. Định danh và phạm vi dữ liệu

FSID là định danh dùng để ràng buộc collection vào cluster. Cluster ID và profile revision là cấu hình của console; không dùng tên hiển thị thay cho việc xác minh FSID.

Daemon có khóa định danh theo loại, ví dụ `mon.ceph-master`, `mgr.ceph-master.ezhuly`, `osd.2`. Host, pool và system không được tính thành daemon trong số lượng hiển thị.

Phạm vi thu thập là các daemon đã chọn và allowlist của deployment. Chọn nhiều daemon chỉ mở rộng phạm vi dữ liệu, không gửi lệnh nâng cấp. IDs như osd.2/osd.5, pool cụ thể hoặc PG 13.0 là ví dụ theo lab, không phải giá trị áp dụng cho mọi cluster.

Mỗi môi trường phải có FSID, host/key pin, SSH target, allowlist và revision riêng. Sai cluster/phạm vi phải bị từ chối; không tự đổi sang cluster khác hoặc dùng wildcard để bỏ qua kiểm tra.

## 4. Dữ liệu mới và “real-time”

Mỗi lần bấm Xem hoặc Xuất dữ liệu mới tạo một lần đọc nguồn mới. Xuất dữ liệu mới không chỉ tải lại bảng đã xem trước đó.

Một lần thu có nhiều lệnh/nguồn, do đó không phải snapshot nguyên tử của toàn cluster. Dữ liệu giữ:

- `started_at` / `completed_at`: khoảng thực hiện lần thu.
- `observed_at`: thời điểm nguồn quan sát được.
- `window_seconds`: cửa sổ đo nếu nguồn cung cấp.
- `quality`, lý do thiếu/cũ và thông tin nguồn.

Nguồn được gọi lại ngay không đồng nghĩa mọi giá trị có timestamp hiện tại. Orchestrator có thể trả mẫu CPU/RAM container đã cache; console phải giữ timestamp đó và đánh dấu cũ khi cần.

IOPS/throughput từ Prometheus cần hai lần scrape trong cùng yêu cầu cùng cửa sổ đo. Không suy hiệu năng từ CRUSH weight, PG placement hoặc mức đầy OSD. Khi chưa có nguồn phù hợp, chỉ số vẫn thiếu; không đổi null thành 0.

Số 0 có thể là giá trị hợp lệ, ví dụ PG count bằng 0. Nó khác dữ liệu chưa có.

## 5. Thu nhẹ, thu sâu và điều phối yêu cầu

Danh mục nhẹ phục vụ nhận diện, lọc, phân trang và chọn daemon. Thu sâu đọc thêm evidence/ngữ cảnh chi tiết, đặc biệt cho OSD; chi phí và thời gian cao hơn.

Từ bản 5.1.2 (preview.1 và rc.1):

- Mở Inventory đọc danh mục nhẹ, không tự thu sâu tất cả OSD.
- Chọn daemon trong Chỉ số cụm có nút xem/xuất riêng. Kết quả mới nằm cạnh thao tác; danh mục toàn bộ không bị thu hẹp.
- Xem chi tiết/xuất/lưu As-is theo luồng tương ứng mới lấy dữ liệu sâu khi cần.
- Đọc thường có ngân sách 60 giây; đọc sâu thêm budget collector đã cấu hình.

Backend giới hạn hai lần thu đang chạy và tối đa hai lượt chờ. Hàng chờ có giới hạn để bảo vệ nguồn; tải vượt mức vẫn có thể trả 429 `COLLECTION_BUSY`.

Giao diện ngăn thao tác trùng. Rời trang/hủy request gửi tín hiệu để ngừng lượt chờ và lệnh backend chưa bắt đầu. Slot đang chạy chỉ được trả sau khi các HTTP nguồn đã nhận kết thúc; SSH đã chạy không bị dừng tức thì, vẫn kết thúc theo timeout riêng. Đây không phải bảo đảm không còn 429 trong mọi điều kiện hoặc bằng chứng đã đạt kiểm tải dài hạn.

## 6. As-is và giai đoạn thu

As-is là bộ dữ liệu đã lưu tại một lần thu: định danh cụm, daemon, thời điểm, chất lượng, nguồn, cấu hình/revision và checksum.

Người dùng có thể gắn nhãn:

- Trước nâng cấp.
- Trong nâng cấp.
- Sau nâng cấp.

Nhãn chỉ mô tả mục đích thời điểm theo người vận hành. Nó không chứng minh nâng cấp đã bắt đầu, đã kết thúc hoặc thành công. Không cần Upgrade session để tạo hay so sánh collection.

“Lấy As-is và xuất” lưu và tải cùng một lần thu, không thu Ceph lại để tạo một bộ khác.

Xem/xuất lịch sử sử dụng dữ liệu đã lưu; không đọc mới Ceph. Vì vậy phải phân biệt rõ bộ As-is lịch sử với observation vừa đọc theo yêu cầu.

## 7. Bộ lọc lịch sử và collection nhiều daemon

Lịch sử hỗ trợ ngày UTC+7, loại daemon, daemon cụ thể, giai đoạn, chất lượng và ID/ghi chú. Mỗi trang lấy 10 collection từ server; không giới hạn tổng lịch sử ở 200 bộ. Giới hạn tối đa 200 dòng của API là giới hạn mỗi trang, không phải tổng dữ liệu.

Một collection có thể chứa nhiều loại daemon. Ví dụ bộ gốc gồm:

```text
mon.ceph-master
osd.2
osd.5
```

Trong bản 5.1.2, lọc OSD vẫn tìm thấy collection này nhưng chỉ hiện osd.2 và osd.5, kèm “2/3 daemon trong bộ gốc”. Lọc tiếp osd.2 chỉ hiện một daemon.

Đây là projection của bộ gốc, không sửa payload hoặc checksum của collection:

- Xuất bộ gốc: giữ toàn bộ daemon và thông tin gốc.
- Xuất daemon đã lọc: loại `FILTERED_AS_IS_EXPORT`, có filter và tham chiếu ID/SHA collection gốc.
- Hash của tệp xuất là hash riêng; không gán SHA bộ gốc cho nội dung đã lọc.

Xóa mềm luôn áp dụng cho cả collection gốc, không chỉ daemon đang lọc. Bộ đã xóa có thể được xem/khôi phục qua bộ lọc bao gồm đã xóa; không tự khôi phục trong quá trình kiểm tra.

## 8. Nguyên lý so sánh hai As-is

Hai bộ A/B phải thuộc cùng FSID và cùng loại daemon. Thứ tự/giai đoạn tự do; không bắt buộc Before/After. Có thể chọn nguồn ở các trang lịch sử khác nhau.

Với số liệu đủ điều kiện, chênh lệch là:

```text
delta = giá trị B − giá trị A
```

Kết quả phân biệt:

- Daemon có ở cả A và B.
- Daemon chỉ có ở A.
- Daemon chỉ có ở B.
- Trường thay đổi và trường không đủ điều kiện tính delta.

Không tạo delta giả khi thiếu nguồn, đơn vị khác, chất lượng chưa đủ, counter reset hoặc daemon thay đổi incarnation. CPU/RAM có mẫu cũ có thể được hiển thị nhưng không mặc nhiên là chênh lệch hiệu năng hợp lệ.

Bản local mới hỗ trợ giới hạn comparison tới daemon cụ thể, ví dụ chỉ osd.2 dù A/B chứa các daemon khác. Bộ lọc ngày/giai đoạn/từ khóa giữ lựa chọn A/B; đổi loại daemon xóa lựa chọn để tránh so khác loại.

So sánh là mô tả khác biệt giữa hai lần thu, không phải kết luận PASS nâng cấp hay xác nhận thay đổi do duy nhất một nguyên nhân.

## 9. Bằng chứng A0.1–A0.8

Các nhóm này là khung dữ liệu cần giữ theo plan. Độ phủ thực tế có thể đầy đủ, một phần hoặc thiếu; phải xét `system.coverage`, chất lượng nguồn và evidence của từng collection, không suy rằng có bảng A0 là đã thu đủ mọi mục.

| Nhóm | Dữ liệu cần giữ | Ý nghĩa |
|---|---|---|
| A0.1 — Môi trường | Host/OS/kernel, shell có nguồn, thời gian, Python/công cụ, client version | Xác định môi trường đã thực hiện thu |
| A0.2 — Cluster | Health, MON quorum, MGR, capacity, flags | Ngữ cảnh cluster tại lần thu |
| A0.3 — OSD | Tree, UUID, thiết bị/network, up/in, weight/reweight/primary-affinity, capacity, version/image | Đối chiếu daemon nguồn/đích và trạng thái |
| A0.4 — CRUSH | Map/rules, compat weight-set, choose_args | Bằng chứng cấu hình placement |
| A0.5 — PG | Up/acting, phân bố PG/primary trên OSD, override | Xác định phạm vi placement/drain cần xem xét |
| A0.6 — Pool/RBD | Pool config, PG được chọn, RBD mapping/image | Ràng buộc phạm vi dữ liệu storage |
| A0.7 — Orchestration | Daemon version/image, service spec, upgrade status khi nguồn có | Quan sát rollout từ nguồn orchestrator |
| A0.8 — An toàn | Clock/NTP, crash, scrub, recovery, dung lượng, helper/tool capability | Đầu vào cho đánh giá vận hành, không tự chứng nhận PASS |

Môi trường A0.1 phản ánh management/SSH client host, không thay cho telemetry của mọi daemon host/container. Shell khai báo không phải bằng chứng shell tương tác; NTP synchronized không phải phép đo offset/PASS của toàn cluster.

OSD có dữ liệu sâu hơn các loại daemon khác: BlueStore/device, CRUSH JSON, PG dump brief toàn cụm, override và ngữ cảnh MON/MGR/pool. Raw evidence được redact trước khi lưu; thiếu tool hoặc probe lỗi giữ trạng thái một phần, không tự cài công cụ.

## 10. Chất lượng và cảnh báo thiếu/cũ

Chất lượng luôn đi cùng nguồn/thời gian, không chỉ là một badge trang trí:

- Dữ liệu hợp lệ: giá trị có nguồn đáp ứng kiểm tra tương ứng.
- Dữ liệu một phần: có phần sử dụng được nhưng thiếu/lỗi nguồn hoặc không đủ độ phủ.
- Dữ liệu cũ: mẫu nguồn đã quá ngưỡng tuổi cho phép.
- Không hỗ trợ/thiếu: nguồn không cung cấp hoặc capability chưa có; không giả thành số 0.

Bản local mới thay các khối JSON nguồn/phạm vi dài trên trang chính bằng biểu tượng cảnh báo tam giác nhỏ. Bấm vào chỉ liệt kê các phần thiếu/cũ; thông tin đầy đủ vẫn ở dữ liệu gốc. Timestamp/chất lượng của từng metric không bị bỏ để làm đẹp giao diện.

Hiện chưa có telemetry host/process/network đầy đủ hoặc percentile latency; RGW/MDS chưa có đầy đủ request/session/latency riêng. Danh tính triển khai/version/image/host có thể đến từ orchestrator. Cluster không triển khai MDS trả danh sách rỗng từ FSMap đã kiểm, không tạo daemon giả.

## 11. Dung lượng và chế độ chỉ quan sát

Banner dung lượng hiển thị OSD đầy nhất trong phạm vi và độ mới của nguồn. Ngưỡng cảnh báo/admission là policy của console, không phải ngưỡng full của Ceph.

Trong chế độ quan sát, console không tạm dừng daemon, I/O hoặc đổi cấu hình cluster. Cảnh báo không chứng minh Ceph đã ngừng ghi và không được che bằng cách đổi ngưỡng chỉ để trình diễn.

Các tỷ lệ ngưỡng do deployment cấu hình; không dùng giá trị lab làm chuẩn chung cho mọi môi trường.

## 12. Xem trước thay đổi OSDMap

Tính tác động được thực hiện offline trên bản sao map mới. Mục tiêu là thấy khác biệt placement dự kiến trước khi thay đổi thật, không chạy thao tác trên cluster.

Kết quả có thể xét PG/raw/up/acting/primary và phân bố OSD. Nhãn bắt buộc là “Dự đoán — chưa áp dụng”; không có nút Apply.

Phạm vi đã kiểm hiện tại:

- Pool replicated; EC bị từ chối, kể cả khi phạm vi tất cả pool có chứa EC.
- MON Pacific 16.2.15 với `osd_crush_update_weight_set=true` phù hợp ở mọi MON.
- Giả định thay đổi CRUSH weight trong phạm vi operation được hỗ trợ.

CRUSH weight khác OSD reweight và primary-affinity. Không áp dụng semantics của một tham số cho tham số khác hoặc tự đoán hành vi ở release chưa được kiểm.

Mapping thiếu thành viên so với pool.size phải mang trạng thái một phần. Không có PG thay đổi không chứng minh mapping đầy đủ/an toàn; failure domain chưa được kiểm chứng độc lập. Placement không cho phép suy ra cải thiện throughput, IOPS hoặc độ trễ.

Worker bị giới hạn network, quyền, CPU/RAM/PID và chỉ đọc root filesystem; isolation không xóa các lỗ hổng còn trong image.

## 13. Xuất dữ liệu và tính toàn vẹn

Tệp được tải về thư mục trình duyệt chọn, thường là Downloads. Frontend kiểm SHA-256 và giới hạn kích thước trước khi hoàn tất tải; cần HTTPS hoặc localhost có Web Crypto. Không bỏ checksum trên HTTP ngoài localhost.

SHA payload collection dùng để kiểm nội dung gốc đã lưu. SHA của tệp export dùng để kiểm bytes của tệp tải về; hai hash có thể khác vì export chứa metadata/manifest hoặc là bản lọc.

Giới hạn hiện tại: tối đa 128 daemon mỗi lần thu và JSON 16 MiB. Thu đồng bộ chưa có job progress đầy đủ cho cluster lớn; không xem một lần kiểm nhỏ là nghiệm thu tải lớn.

## 14. API theo nhóm chức năng

| Nhóm | Endpoint |
|---|---|
| Đọc mới / xuất mới | `POST /api/v1/as-is/observe`, `POST /api/v1/as-is/export` |
| Tạo / tìm lịch sử | `POST` và `GET /api/v1/as-is/collections` |
| Xem / xuất bộ đã lưu | `GET /api/v1/as-is/collections/{id}`, `GET .../{id}/export` |
| Xóa mềm / khôi phục | `DELETE .../{id}`, `POST .../{id}/restore` |
| So sánh / xuất so sánh | `POST /api/v1/as-is/compare`, `POST .../compare/export` |
| OSDMap tùy chọn | `GET .../osdmap-previews/capabilities`, `POST .../osdmap-previews`, xem/xuất theo ID |

Bản lọc collection hỗ trợ `daemon_type` và `daemon_key` trên luồng export tương ứng của bản local mới. Các POST ghi metadata không phải Ceph write. Tạo collection có idempotency key; origin/header guard và xác thực là các kiểm tra riêng, không thay thế xác minh FSID/allowlist.

## 15. Phiên bản và trạng thái kiểm chứng

Tình trạng ngày 14/10/2026, Asia/Saigon:

| Phạm vi | Phiên bản / trạng thái |
|---|---|
| Application đã đăng Docker Hub | 5.1.2-rc.1; dùng cho hướng dẫn cài máy mới |
| Application localhost | 5.1.2-preview.1; chưa đăng Hub |
| Worker lab/offline đã đăng Hub | 16.2.15-minimal-preview.2 |
| Database schema | 21 |
| Nghiệm thu production toàn bộ | Chưa đạt |

Các nút xem/xuất daemon riêng, cảnh báo thu gọn, filter nội bộ collection hỗn hợp và cancellation mô tả ở trên có trong image Hub 5.1.2-rc.1. Bản 5.1.1-rc.1 cũ không có đầy đủ các cải tiến này.

Bản local mới đã có 319 backend test với PostgreSQL không skip, 31 frontend test, TypeScript/build và 10 kiểm tra render component SSR đạt. SSR không thay thế kiểm Browser. Kiểm trực tiếp Browser theo phạm vi bản sửa đã đạt: xem/xuất hai daemon mới, lọc OSD trong bộ hỗn hợp, tải riêng osd.2 và so sánh đúng osd.2; dữ liệu gốc không đổi. Một smoke test hủy hai request rồi đọc lại trả 200 không phải kiểm tải dài hạn.

App scan ghi 0 findings ở các mức đã báo cáo; không phải bảo đảm không có lỗ hổng. Worker minimal preview.2 raw scan vẫn 1 Critical, 21 High, 35 Medium, 2 Low; triage vendor/CNA được giữ riêng, không sửa raw scan để coi là production-ready.

Nguyên nhân một lỗi integration lịch sử vẫn chưa được xác nhận. Worker security, integration stability, cluster thứ hai, ARM64/signing và nghiệm thu môi trường đích chưa được đóng thành PASS. Migration lịch sử và report cũ không bị sửa để làm kết quả mới đẹp hơn.

Ngày 14/10/2026 đã dọn 60 container rollback cũ trên máy local; giữ image, volume và dữ liệu. Điều này không đổi phiên bản ứng dụng hoặc chứng minh readiness của môi trường khác.

## 16. Tài liệu đối chiếu

- [Plan hiện tại](plan%285%29.md): yêu cầu và các lát cắt triển khai.
- [VALIDATION.md](rgw-console/VALIDATION.md): kết quả/bằng chứng kiểm thử theo từng thời điểm.
- [Manifest local 5.1.2-preview.1](rgw-console/deploy/releases/5.1.2-preview.1.yaml).
- [Manifest Hub 5.1.1-rc.1](rgw-console/deploy/releases/5.1.1-rc.1.yaml).
- [Giới hạn OSDMap](rgw-console/docs/OSDMAP_PREVIEW.md).
- [Security triage](rgw-console/docs/OSDMAP_SECURITY_TRIAGE.md).
- [Điều tra integration lịch sử](rgw-console/docs/INTEGRATION_FAILURE_INVESTIGATION.md).
- [Kịch bản demo riêng](rgw-console/docs/DEMO.md).
