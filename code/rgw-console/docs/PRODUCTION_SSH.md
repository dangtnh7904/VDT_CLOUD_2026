# SSH và CephX cho thu thập production

Tài liệu này chuẩn bị tài khoản dành riêng cho **chỉ số, As-is và so sánh**. Guard đã có trong source, chưa được cài lên host Ceph và chưa nghiệm thu với quyền CephX của cluster đích. Các bước tạo tài khoản/key/caps dưới đây dành cho quản trị viên triển khai vào môi trường staging riêng; chúng thay đổi cấu hình SSH/Ceph khi được thực hiện.

## Kết quả audit hiện tại

`rbd-console/src/ssh.js` có transport chung cho command, sudo, SFTP và shell. Profile production tại `executor.js` chặn bề mặt ghi/RBD/terminal ở tầng ứng dụng và chỉ tạo argv cố định, nhưng tài khoản SSH lab hiện có không vì thế tự trở thành tài khoản hạn chế trên server.

`collect_osd.py` đọc bằng argv và có các probe môi trường cố định. CLI của helper còn cho phép `--ceph-bin`, `--conf`, `--name`, `--keyring`, `--output`, `--all` và `--sudo-ceph`; không cho SSH key production gọi CLI này tùy ý. Guard mới chỉ nhận khuôn lệnh hiện tại, kiểm checksum source, gọi hàm thu thập với runner có allowlist và luôn gắn CephX identity riêng. Nếu helper bắt lỗi rồi trả kết quả một phần, các lỗi từ guard vẫn khiến cả thao tác thất bại.

Guard: [`deploy/ssh/console-readonly-dispatch.py`](../deploy/ssh/console-readonly-dispatch.py). Không có shell, sudo hoặc fallback về `client.admin` khi guard thực thi. Chuỗi `sudo -n` và `--sudo-ceph` do executor cũ gửi được nhận dạng như khuôn transport rồi bỏ; chúng không được chạy.

## Tài khoản và key riêng

Trên host Linux AMD64 staging, dùng Python 3.10 trở lên, Ceph CLI tương ứng cluster, một Unix account `storage-lab-console` không có quyền sudo và group cùng tên chỉ chứa account này. Account dùng `/bin/sh` để OpenSSH chạy forced command; đăng nhập mật khẩu, terminal, forwarding và user rc bị tắt bằng cấu hình SSH.

Quản trị viên tạo account và các thư mục sau (không dùng account/key lab sẵn có):

```sh
groupadd --system storage-lab-console
useradd --system --gid storage-lab-console --home-dir /var/lib/storage-lab-console-ssh --shell /bin/sh storage-lab-console
install -d -o root -g root -m 0755 /var/lib/storage-lab-console-ssh /var/lib/storage-lab-console-ssh/.ssh
install -d -o root -g storage-lab-console -m 0750 /etc/storage-lab-console
install -d -o root -g root -m 0755 /opt/storage-lab /usr/local/libexec/storage-lab-console
```

Tạo key SSH mới trên máy triển khai bằng `ssh-keygen -t ed25519 -f storage-lab-console-production`. Private key chỉ đặt trong secret của executor; public key được quản trị viên gắn vào file `authorized_keys` root sở hữu. Lưu fingerprint host SSH từ nguồn tin cậy, rồi đặt `RBD_SSH_HOST_KEY_REQUIRED=true` và `RBD_SSH_HOST_KEY_SHA256` hoặc known-hosts đã kiểm tra. Không lấy fingerprint chỉ từ lần kết nối chưa xác minh.

## CephX identity và caps

Ceph mặc định dùng `client.admin` nếu không chọn tên client; guard luôn truyền `--name client.storage-lab-console`, keyring và conf cố định. Ceph hỗ trợ caps MGR theo command hoặc service. [Ceph Pacific user management](https://docs.ceph.com/en/pacific/rados/operations/user-management/)

Trên cluster staging, quản trị viên tạo **identity mới** và lưu key bằng `-o` để không in secret lên terminal. Mẫu caps cần kiểm tra trên phiên bản Ceph đích:

```sh
ceph auth get-or-create client.storage-lab-console \
  mon 'allow r' \
  mgr 'allow service mgr r, allow service osd r, allow service pg r, allow command "orch ps", allow command "orch host ls", allow command "device ls-by-daemon"' \
  -o /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
chown root:storage-lab-console /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
chmod 0640 /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
```

Không cấp caps OSD/MDS object, `allow *`, quyền auth, upgrade, pool write hoặc Ceph admin key. `orch ps` và `orch host ls` được khai báo là command đọc trong source Pacific 16.2.15; `--refresh` yêu cầu cập nhật quan sát của orchestrator, không điều khiển daemon. [Source orchestrator Pacific](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/orchestrator/module.py)

Nếu lệnh cần thiết bị từ chối, lưu tên action và mã lỗi không có key, đối chiếu bảng command của đúng phiên bản rồi bổ sung **đúng command đọc** cần thiết. Không tự tăng caps thành admin. Việc caps này thực sự đọc đủ `versions`, PG, capacity, config và device metadata vẫn là gate phải kiểm trên cluster đích.

`/etc/storage-lab-console/ceph.conf` là file root sở hữu, mode `0640`, group `storage-lab-console`, chứa FSID/MON addresses của cluster đích. Không thêm admin key hoặc biến môi trường `CEPH_ARGS`. Guard xóa môi trường kế thừa trước khi chạy công cụ.

## Cài guard và policy

Quản trị viên copy source release đã duyệt, kiểm checksum, rồi cài root-owned:

```sh
install -o root -g root -m 0755 console-readonly-dispatch.py /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py
install -o root -g root -m 0644 collect_osd.py /opt/storage-lab/collect_osd.py
sha256sum /opt/storage-lab/collect_osd.py
```

Tạo `/etc/storage-lab-console/ssh-readonly.json` root-owned mode `0640`, group `storage-lab-console`. Thay giá trị mẫu bằng FSID thật, OSD thuộc phạm vi và SHA256 từ source đã duyệt:

```json
{
  "expected_fsid": "11111111-2222-3333-4444-555555555555",
  "allowed_osds": [0, 2, 5],
  "collector_sha256": "REPLACE_WITH_APPROVED_HELPER_SHA256"
}
```

Guard từ chối config/helper/keyring/conf/guard nếu file hoặc thư mục cha là symlink, không thuộc root, hoặc có quyền ghi group/other. Policy không nhận đường dẫn executable/keyring/conf tùy chọn. Thay helper phải audit lại và cập nhật checksum bằng quản trị viên; tài khoản SSH không được sửa file hay policy.

Một dòng `authorized_keys` root-owned mode `0644` (thay public key; có thể thêm `from="CIDR máy triển khai"` phù hợp mạng đích):

```text
restrict,no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty,command="/usr/bin/python3 -I /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py" ssh-ed25519 REPLACE_WITH_DEDICATED_PUBLIC_KEY storage-lab-console-production
```

`restrict` tắt forwarding, PTY và user rc; `command` áp dụng cả command, shell và subsystem, guard dùng `SSH_ORIGINAL_COMMAND` để kiểm khuôn lệnh. [OpenSSH authorized keys](https://man.openbsd.org/sshd)

Thêm block cho đúng account trong cấu hình sshd staging, không sửa block của account lab:

```text
Match User storage-lab-console
    AuthenticationMethods publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PermitTTY no
    DisableForwarding yes
    X11Forwarding no
    PermitUserRC no
    AuthorizedKeysFile /var/lib/storage-lab-console-ssh/.ssh/authorized_keys
    ForceCommand /usr/bin/python3 -I /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py
Match all
```

Đối chiếu các directive được phiên bản OpenSSH trên host hỗ trợ. `ForceCommand` không tự tắt forwarding, nên cần `DisableForwarding`. [OpenSSH server configuration](https://man.openbsd.org/sshd_config)

Chạy `sshd -t` và kiểm cấu hình hiệu lực `sshd -T -C user=storage-lab-console,host=HOST,addr=CLIENT_IP` trước khi quản trị viên reload sshd. Giữ phiên quản trị độc lập để phục hồi cấu hình nếu cần. Không ghi private key/CephX key vào log nghiệm thu.

## Cấu hình executor staging

```dotenv
APP_ENV=production
CONSOLE_READ_ONLY=true
UPGRADE_MUTATIONS_ENABLED=false
RBD_TERMINAL_ENABLED=false
RBD_SSH_USER=storage-lab-console
RBD_SSH_HOST_KEY_REQUIRED=true
OSD_INFO_COLLECTOR_PATH=/opt/storage-lab/collect_osd.py
OSD_INFO_COLLECTOR_RUN_AS_SSH_USER=true
OSD_INFO_COLLECTOR_COMMAND_TIMEOUT_SECONDS=45
```

FSID và allowlist OSD của executor phải khớp policy server. Account không có shell/SFTP, nên tắt legacy RGW/RBD/terminal. Guard cho tối đa **16 OSD mỗi lượt**, mỗi lệnh tối đa 45 giây, toàn lượt 300 giây, stdout cuối 16 MiB và tổng nguồn 32 MiB; lượt quá lớn phải chia nhóm. File conf/keyring trên host không mount vào app container; app chỉ giữ SSH key riêng.

## Những chức năng chưa hỗ trợ bằng key này

| Bề mặt | Kết quả |
| --- | --- |
| Metric CLI, MON/MGR/OSD inventory, As-is, capacity | Cho phép các argv cố định trong guard; phải kiểm quyền trên cluster đích |
| Deep OSD helper | Chỉ OSD nằm trong policy, checksum helper khớp, không có caller paths/options |
| A0.1 môi trường | Chỉ phiên bản công cụ và clock probe cố định trên SSH client host |
| OSDMap binary export và MON weight-set probe | Từ chối; nghiệm thu worker/preview riêng trước khi bổ sung đọc cố định |
| RBD, object/file operations, SFTP/scp, interactive shell | Từ chối |
| Auth/config write, restart/upgrade, pool/CRUSH/OSD mutation, forwarding | Từ chối |

## Gate nghiệm thu còn phải chạy

1. Với key mới, đọc tất cả fixed inventory actions, một bộ As-is OSD và A0.1; kiểm FSID, dữ liệu, chất lượng và thời gian nguồn. Mã lỗi caps phải được xử lý bằng quyền đọc đúng action.
2. Dùng command sai nhưng vô hại như `true`, `ceph auth get client.storage-lab-console`, `python3 ... --all`; xác nhận exit `126`, không thực thi. Không thử lệnh ghi Ceph thật để chứng minh guard.
3. Xác nhận shell/SFTP/PTY/agent/TCP/Unix-socket forwarding bị chặn; account không sudo, không đọc admin key, không sửa policy/helper/authorized_keys.
4. Đổi FSID/policy/helper checksum trong **fixture hoặc host staging riêng**, kiểm chặn trước khi xuất dữ liệu; không đổi FSID của cluster thật.
5. Kiểm deadline, output cap, nhiều SSH channel và khả năng hủy trên Linux; kiểm tài nguyên của account/process và giới hạn concurrency của executor theo tải đã chốt.
6. Lưu checksum guard/helper, public-key fingerprint, host fingerprint, caps đã redacted và kết quả từng action trong biên bản. Chỉ đánh dấu gate SSH production PASS sau khi thực hiện trên môi trường đích.
