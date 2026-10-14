# File secret cho deployment chỉ đọc

Tạo secret ngoài Git/image trong thư mục deployment riêng. Không chép secret lab sang cluster khác; không ghi password/token/private key vào `.env`, profile, logs hoặc biên bản công khai.

| File | Consumer | Quyền trong bộ image đã pin |
| --- | --- | --- |
| `database_url` | API và collector đọc, role `storage_lab_runtime` | UID 10001; không dùng superuser/migration |
| `migration_database_url` | Job migrate và database-permissions | UID 10001; không mount vào API |
| `database_runtime_password` | Job database-permissions | UID 10001; password riêng của runtime role |
| `postgres_password` | PostgreSQL bundled | UID 70 của image Alpine đã pin; password khác runtime |
| `console_users.json` | Consumers khi dùng compose.access-control.yml | Hash PBKDF2-SHA256 600000–2000000 iterations, viewer/operator/admin |
| `console_password_hash` | Secret tương thích base Compose | UID 10001; đăng nhập legacy bị overlay multi-account tắt |
| `executor_token` | API/collector và executor | Ngẫu nhiên ít nhất 32 ký tự |
| `ssh_private_key`, `ssh_known_hosts` | Executor duy nhất | UID 10001; account/key riêng, host fingerprint bắt buộc |
| `tls_private_key.pem`, `tls_certificate.pem` | Ingress | UID 101; key private, chain/domain do PKI duyệt |

Với bundled DB, URL migration là user `storage_lab_console` tại `postgres:5432/storage_lab_console`; URL runtime là `storage_lab_runtime` cùng DB với password runtime riêng. Với DB ngoài, DBA cấp database/schema riêng và TLS/grants theo [deploy guide](../README.md). Không dùng DB/schema chung với ứng dụng khác.

Linux rootful: file phải đọc được bởi UID container thực mà không world-readable. Compose `uid/gid/mode` không sửa bind-mounted file; kiểm theo [quyền file Linux](../README.md#quyền-file-trên-host-linux). Rootless/user namespace/Windows phải kiểm mapping/ACL riêng. Không dùng chmod 777 hoặc tăng quyền runtime để xử lý lỗi đọc secret.

Backup DB không bao gồm các secret/config/DB role. Sao lưu chúng bằng kho encrypted được phê duyệt, giữ khóa khôi phục riêng và diễn tập trên bản sao private; checksum manifest không phải encryption hoặc chữ ký. Xem [bàn giao production](../../docs/PRODUCTION_HANDOFF.md).

Đăng nhập web không thay quyền Ceph. Giữ `UPGRADE_MUTATIONS_ENABLED=false`, legacy/Lab/terminal tắt; mọi web role chỉ đọc Ceph. Admin cluster cài dedicated SSH/CephX/forced-command theo [SSH guide](../../docs/PRODUCTION_SSH.md), không dùng key lab/sudo rộng như bằng chứng least privilege.
