NhómTiêu chí trong noteCách áp dụng trong plan		
Điều kiện bắt buộc	PG đang khỏe	Tất cả PG liên quan active+clean trước khi bắt đầu; không lỗi dữ liệu, thiếu replica hoặc recovery/backfill chưa xử lý
Điều kiện bắt buộc	Dừng được mà vẫn phục vụ	ceph osd ok-to-stop X đạt ngay trước bước dừng; đánh giá lại khi trạng thái thay đổi
Ưu tiên cao	Tải trên PG thấp	Đo IOPS/throughput theo cửa sổ đại diện; tránh OSD chứa PG nóng, kể cả khi tổng PG ít
Ưu tiên cao	Peer còn dư tài nguyên	CPU, disk IOPS/latency và network của Y/Z/S đủ nhận thêm tải primary, replication và backfill
Ưu tiên	Ít primary PG	Đặc biệt ít primary của PG nhiều I/O hoặc dịch vụ nhạy latency
Ưu tiên	Tổng số PG ít	Tính cả primary và replica, ở mọi pool chứa trên X
Ưu tiên	Ít liên quan dịch vụ quan trọng	Xác minh mapping pool/workload; không biết criticality thì chưa được gắn nhãn ít critical

giờ làm sao để giải quyết cái này

Bạn nên triển khai bảng này thành bộ chọn OSD trước khi nâng cấp: thu thập dữ liệu → loại OSD không đạt → xếp hạng OSD còn lại → kiểm tra lại trước khi dừng. Phần này phù hợp làm bằng script Python chạy trên node quản trị, đọc Ceph CLI và số liệu monitoring.

Cụ thể, từng tiêu chí được xử lý như sau:

Tiêu chí	Lấy dữ liệu ở đâu?	Cách đánh giá
PG khỏe	ceph pg dump pgs -f json, ceph health detail	Lấy tất cả PG có X trong acting hoặc up; kiểm tra trạng thái, lỗi scrub, degraded và recovery/backfill
Dừng được	ceph osd ok-to-stop X	Không đạt thì loại; chạy lại ngay trước khi dừng
Tải PG thấp	Thống kê từng PG qua nhiều lần lấy mẫu	Tính tốc độ đọc/ghi; xét cả tổng tải và PG nóng nhất
Peer dư tài nguyên	Mapping PG kết hợp Prometheus/node_exporter	Kiểm tra từng peer và host: CPU, disk latency/IOPS, network; đánh giá tải tăng thêm khi chuyển primary/backfill
Ít primary PG	Trường acting_primary hoặc ceph pg ls-by-primary X	Đếm số primary; ưu tiên hơn nữa nếu tải của các primary này thấp
Ít tổng PG	Danh sách PG có X trong acting hoặc up	Đếm PG duy nhất, bao gồm mọi pool
Ít ảnh hưởng dịch vụ quan trọng	PG → pool ID → pool name → danh mục workload	Bạn khai báo mức criticality; pool dùng chung thì đánh giá thận trọng theo workload quan trọng nhất