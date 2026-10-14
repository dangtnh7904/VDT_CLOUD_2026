# Lịch vận hành trên Linux — quản trị viên tự cài

Đây là template chưa cài/chưa chạy trên host đích. Cần Linux với systemd, Docker Engine rootful, Python 3.10+ và PowerShell 7.2+ đã được đơn vị kiểm nguồn. `slc-ops` là service account tin cậy vận hành Docker, không phải tài khoản web hay SSH collector; quyền Docker socket tương đương quyền mạnh trên host.

1. Thay mọi đường dẫn/user/group trong service và environment example bằng deployment riêng đã duyệt. Service account phải đọc được CA/client viewer/config alert, ghi được deployment lock/backup/state/receipt và vận hành đúng Docker Engine. Secret/config private, không đặt password/token/key trong environment file. `ProtectHome=yes` yêu cầu không dùng đường dẫn dưới home; sửa `ReadWritePaths` đúng ba thư mục thực. Không nới quyền secret thành world-readable để chạy được.
2. Chạy `run-production-maintenance.ps1` riêng với Mode Check, domain/CA/account/alert thực; xác nhận report và người nhận nhận TEST/ALERT/RECOVERY. Chạy Backup/restore trong maintenance window riêng trước khi đăng ký. Sender state tự tách `.check.json`/`.backup.json`; backup PASS không giải quyết cảnh báo Check.
3. Sau khi được duyệt user/cadence/maintenance window, admin cài vào các đường dẫn cố định, không ghi đè service cũ nếu có consumer chưa kiểm:

```sh
sudo install -o root -g slc-ops -m 0640 reviewed-maintenance.env /etc/storage-lab-console/maintenance.env
sudo install -o root -g root -m 0644 reviewed-maintenance.service /etc/systemd/system/storage-lab-console-maintenance@.service
sudo install -o root -g root -m 0644 reviewed-check.timer /etc/systemd/system/storage-lab-console-check.timer
sudo install -o root -g root -m 0644 reviewed-backup.timer /etc/systemd/system/storage-lab-console-backup.timer
sudo systemd-analyze verify /etc/systemd/system/storage-lab-console-maintenance@.service /etc/systemd/system/storage-lab-console-check.timer /etc/systemd/system/storage-lab-console-backup.timer
sudo systemctl daemon-reload
sudo systemctl start storage-lab-console-maintenance@Check.service
sudo systemctl status storage-lab-console-maintenance@Check.service
sudo systemctl enable --now storage-lab-console-check.timer storage-lab-console-backup.timer
systemctl list-timers --all storage-lab-console-check.timer storage-lab-console-backup.timer
```

Backup timer mẫu là 19:00 UTC = 02:00 UTC+7 ngày kế tiếp, **chỉ đề xuất**. `Persistent=yes` có thể chạy bù ngay khi host lên lại; phải được maintenance policy chấp thuận vì backup quiesce app. Check đề xuất 5 phút sau lần trước hoàn tất, không tạo probe chồng nhau; lock chung có thể làm lượt Check trong Backup trả lỗi có chủ đích. Không cho scheduler tự restart dịch vụ hoặc xóa dữ liệu khi báo lỗi.

4. Kiểm journal chỉ trong phạm vi private vận hành, JSON reports/receipts, backup mới đúng project, test restore và thông báo đã tới người trực. Sender lỗi phải báo job failed; không coi HTTP 2xx tại receiver như bằng chứng người trực đã đọc. Chốt log/report/state retention, retry/backoff/expiry và offsite encrypted backup theo đơn vị.
5. Rollback scheduler: `sudo systemctl disable --now storage-lab-console-check.timer storage-lab-console-backup.timer` chỉ dừng lịch, không xóa DB/volume/config/backup. Không dừng backup đang chạy giữa chừng; đợi lần đó kết thúc và kiểm writer đã phục hồi.

Template không chứng minh scheduler host đích đã đạt. Tham khảo tài liệu chính thức [service](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml), [timer](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml), [quyền filesystem](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml). Chưa chạy `systemd-analyze verify` hoặc service thật trên Linux đích; chỉ bật timer sau khi admin xác minh trên phiên bản systemd thực và ký nhận phạm vi. CA mẫu nằm trong thư mục monitor; không thêm tài khoản vận hành vào group SSH collector hoặc nới quyền thư mục guard chỉ để đọc CA.
