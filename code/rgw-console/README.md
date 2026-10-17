# Cài đặt image Storage Lab Console

Hướng dẫn cài đặt chính nằm tại [code/README.md](../README.md). Hướng dẫn này dùng image Docker Hub `5.1.1-rc.1` theo digest, không build source.

- [Cài thử trên Windows, tải image và khởi động](../README.md#1-chuẩn-bị).
- [Cài vào hệ thống thật](deploy/README.md#cài-vào-hệ-thống-thật).
- [Cấu hình SSH key, profile và helper để đọc Ceph](deploy/README.md#kết-nối-ceph-chỉ-đọc).
- [Backup, cập nhật và dừng](deploy/README.md#backup-cập-nhật-và-dừng).
- [Cài worker OSDMap cho lab](docs/OSDMAP_PREVIEW.md).

Bản `5.1.2-preview.1` đang chạy localhost chưa đăng Hub; không dùng nó làm tag tải về trên máy mới. Máy đích phải có cấu hình và secret riêng, không sao chép secret của máy đang chạy.

Phần lý thuyết được tách sang [tổng hợp.md](<../tổng hợp.md>).
