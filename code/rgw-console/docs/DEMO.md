# Demo Storage Lab Console — localhost 5.1.2-rc.1

Phạm vi: console **chỉ đọc Ceph**, xem dữ liệu mới, lưu hiện trạng và so sánh; không chạy benchmark, nâng cấp, dry-run hoặc Apply. Worker OSDMap tùy chọn chỉ dùng lab/offline. Localhost ngày 14/10/2026 chạy `5.1.2-rc.1`, chưa đăng Hub; [manifest preview](../deploy/releases/5.1.2-rc.1.yaml) ghi kiểm API/Browser theo phạm vi bản sửa. Image Hub vẫn là `5.1.1-rc.1`; [manifest Hub](../deploy/releases/5.1.1-rc.1.yaml) ghi digest và giới hạn riêng.

## Chuẩn bị trước buổi demo

- Bật Docker Desktop (Linux containers), chờ các container `storage-lab-console-local-*` chạy và mở [trang chỉ số](http://127.0.0.1:8080/#view=metrics).
- Kiểm phiên bản `v5.1.2-rc.1`, “Console sẵn sàng”, FSID đã xác minh và thời điểm lần thu. Nếu đang dùng tab cũ, tải lại trang. Trên màn hình hẹp bấm nút menu trước khi chọn navigation; trên màn hình rộng navigation nằm bên trái.
- Localhost đã có `.env.local-readonly`, profile, SSH key/known_hosts và volumes. **Không tạo lại hoặc ghi đè cấu hình này**. Máy đích khác cần cấu hình riêng theo [hướng dẫn triển khai](../deploy/README.md).
- Nguồn thực tế có thể cần vài giây; thu sâu OSD có thể lâu hơn. Chờ thông báo hoàn tất, không bấm lặp liên tục. Giao diện khóa thao tác trùng; hàng chờ server có giới hạn và không chia sẻ dữ liệu cache.

Kiểm nhanh bằng PowerShell, không in secret:

```powershell
docker ps --filter label=storage-lab-console.scope=local-preview
Invoke-RestMethod http://127.0.0.1:8080/api/ready
```

`ready=true` là trạng thái console/dependency, không phải kết luận sức khỏe hoặc nâng cấp thành công của Ceph.

## Kịch bản khoảng 5 phút

1. **Chỉ số cụm và daemon:** bấm “Đọc lại toàn bộ danh mục”. Trình bày FSID, sức khỏe hệ thống, IOPS/throughput có cửa sổ đo và 10 daemon mỗi trang. Cluster lab hiện có 14 daemon (3 MON, 2 MGR, 6 OSD, 3 RGW); MDS trống vì cluster không triển khai MDS, không tạo daemon giả.
2. Chọn một MON và một OSD (có thể chọn qua các trang). Bấm **“Xem chỉ số mới (2 daemon)”** ngay dưới lựa chọn: kết quả riêng hiện cạnh các nút, danh mục 14 daemon vẫn giữ nguyên. Bấm **“Xuất 2 daemon (JSON)”** để tải đúng phạm vi đã chọn. File được thu **mới tại lần bấm xuất**, không phải tải lại kết quả xem; đã kiểm SHA-256 trước khi trình duyệt tải, thường nằm trong Downloads. Bấm “Xem mới” ở từng hàng để xem riêng một daemon.
3. **Thu thập hiện trạng:** chọn `osd.2`, `osd.5` (hoặc daemon cần theo dõi), chọn nhãn Trước/Trong/Sau, ghi chú “Demo — chỉ thu dữ liệu, không nâng cấp” rồi “Lấy As-is”. Kết quả có ID, thời gian, chất lượng và dữ liệu chuyên sâu OSD. “Lấy As-is và xuất” lưu/tải cùng một lần thu, không đọc thêm lần thứ hai để tạo tệp.
4. **So sánh:** chọn loại OSD, chọn hai bộ cùng FSID làm A/B rồi “So sánh A với B”. Sau khi cài sạch, tạo hai bộ As-is mới cho cùng daemon; lịch sử cũ đã nằm trong bản backup riêng. Đổi bộ lọc ngày/giai đoạn vẫn giữ A/B; đổi loại daemon xóa A/B để không so khác loại. Kết quả là B − A, không bắt buộc Before/After. Bấm “Xuất so sánh (JSON)” để tải đúng hai nguồn đã lưu.
5. **Lịch sử:** xem bản đã lưu và lọc ID/ghi chú/ngày. Chọn loại OSD: bộ có MON + OSD vẫn xuất hiện nhưng chỉ hiện các OSD; “Daemon cụ thể” có thể giới hạn tới osd.2. **“Xuất daemon đã lọc”** tải bản lọc có tham chiếu SHA bộ gốc; **“Xuất bộ gốc”** vẫn tải toàn bộ nội dung. Xóa là xóa mềm **cả collection gốc**, có xác nhận; “Bao gồm đã xóa” cho xem và khôi phục. Không xóa collection vận hành chỉ để demo. **Công cụ cũ** nằm trong nhóm thu gọn và bị khóa ở chế độ chỉ đọc.

## Những điểm cần giải thích khi trình bày

- “Dữ liệu một phần” không đồng nghĩa cluster lỗi: tool thiếu, metric không có nguồn hoặc thống kê container do orchestrator cache đều được ghi rõ. Bấm **biểu tượng cảnh báo tam giác nhỏ** để xem danh sách thiếu/cũ; không còn khối nguồn/phạm vi JSON dài trên trang chính. Chất lượng/thời điểm vẫn có trong metric và nguồn đầy đủ trong bộ gốc. Không biến null thành 0 hoặc gắn nhãn dữ liệu cũ là real-time.
- Client Ceph CLI của máy SSH có thể khác phiên bản daemon. Phiên bản daemon lấy từ nguồn daemon/orchestrator, không suy từ client.
- Banner dung lượng là **chỉ quan sát** theo policy console: cảnh báo 67%, dừng admission của console 68%, nguy cấp 70% trong cấu hình lab hiện tại. Đây không phải ngưỡng full của Ceph và console **không dừng daemon/I/O hoặc đổi cấu hình cluster**. Không chỉnh ngưỡng để che cảnh báo khi demo.
- As-is là bằng chứng tại thời điểm thu. Nhãn Trước/Trong/Sau chỉ do người vận hành chọn, không chứng minh đã nâng cấp. So sánh không tự kết luận PASS nâng cấp.
- OSDMap là “Dự đoán — chưa áp dụng”: tính offline trên bản sao map, chỉ operation/pool/version được hỗ trợ. Không có nút Apply và không suy ra cải thiện hiệu năng từ placement. Worker còn finding bảo mật và chưa được duyệt production.

## Image đã phát hành

```powershell
docker pull --platform linux/amd64 dang7904/storage-lab-console@sha256:35dd7b3d32b05ae6d726b1fe6b5875d47edbcf94f0481aebc25f83d81c9f79ee
docker run --rm --network none dang7904/storage-lab-console@sha256:35dd7b3d32b05ae6d726b1fe6b5875d47edbcf94f0481aebc25f83d81c9f79ee version
```

Image đa role không phải container standalone: cần PostgreSQL, profile/secret và executor khi đọc Ceph. Dùng Compose image-only theo [deployment README](../deploy/README.md); không đưa SSH key, `.env` hoặc dữ liệu collection vào image. Pin dependency theo digest; không chạy `down --volumes` để cập nhật.
