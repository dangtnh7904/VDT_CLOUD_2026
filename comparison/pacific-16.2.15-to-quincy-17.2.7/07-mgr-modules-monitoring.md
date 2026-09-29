# 07 — MGR, dashboard, exporter và monitoring: v16.2.15 → v17.2.7

**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./07-mgr-modules-monitoring.csv) có 726 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 2`, `trivial = 0`, **chưa phân loại = 724**; các số 0 không phải kết luận không có tác động.

## Phạm vi và phương pháp

Owner này phụ trách MGR, dashboard, exporter và monitoring. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### MGR-001 — `device_health_metrics` chuyển sang `.mgr` và SQLite

**CSV:** `src/pybind/mgr/mgr_module.py`, `src/pybind/mgr/devicehealth/module.py`. Pacific `devicehealth` tạo/dùng pool `device_health_metrics` và lưu metrics trong RADOS OMAP. Quincy `MgrModule.create_mgr_pool()` kiểm pool cũ, rename nó thành `.mgr`, gắn app `mgr`; `open_db()` tạo `main.db` của từng module bằng Ceph SQLite VFS. `devicehealth.check_legacy_pool()` đọc OMAP cũ theo từng lượt rồi xóa object đã import, ghi vào SQLite `DeviceHealthMetrics`. Các commit triển khai chính: `e3d771702da3bb858064b67eb6c710a659bfb08d`, `abd35d47696c208990355395d48c1c1e261de95c`, `da551b0b040671d90f5b39910baa5f610f5712c4`. [Release notes Quincy](https://docs.ceph.com/en/quincy/releases/quincy/) xác nhận rename pool. Các symbol target ở `mgr_module.py:1106,1205` và `devicehealth/module.py:280,306`; endpoint base ở `devicehealth/module.py:249` và các đường `open_connection`/`put_device_metrics`.

**Điều kiện:** cluster có device health module/pool cũ, MGR target khởi động và DB đủ điều kiện tạo; nếu chưa có pool cũ, target tạo `.mgr` mới. Đây là migration persistent state do MGR target thực hiện, không phải bước rename thủ công. Trong mixed-version MGR failover, MGR Pacific không có code SQLite migration; cần thử failover/rollback thực tế, không giả định MGR base đọc được dữ liệu mới. Sau full upgrade, health metrics qua SQLite trong `.mgr`. **Evidence confidence:** high cho rename/import path, medium cho mức độ rollback vì chưa chạy lab.

**Tác động:** tên pool, application metadata và nơi lưu metrics thay đổi; monitoring/backup script tham chiếu tên cũ cần audit. Migration đọc tối đa 10 object mỗi lượt trong `check_legacy_pool`, nên cần kiểm nó đi hết và dữ liệu device health vẫn truy vấn được. Không tuyên bố có mất dữ liệu từ code riêng. Repository `qa/suites/upgrade/octopus-x/parallel/upgrade-sequence.yaml` kiểm pool cũ biến mất, `.mgr` hiện diện và `ceph device get-health-metrics` có dữ liệu, nhưng đó là đường Octopus upgrade, không phải run result của cặp endpoint này; chưa chạy.

**Kiểm chứng:** ghi danh sách pool/PG và số metrics trước rollout; trong lab/canary nâng MGR target, quan sát rename, SQLite DB, progress import và truy vấn SMART metrics. Diễn tập MGR failover trước/sau import và rollback theo bản sao dữ liệu phù hợp. Nếu script hoặc dashboard còn dùng `device_health_metrics`, cập nhật phụ thuộc sau khi xác minh target.

Các hàng khác vẫn để trống `upgrade_impact` cho tới khi đọc diff/metadata; không gán `trivial` theo đường dẫn.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 726` và viết tóm tắt các cụm trivial.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
