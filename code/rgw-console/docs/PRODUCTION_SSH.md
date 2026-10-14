# SSH và CephX cho thu thập production

Tài liệu này chuẩn bị tài khoản dành riêng cho **chỉ số, As-is và so sánh**. Guard đã có trong source, chưa được cài lên host Ceph và chưa nghiệm thu với quyền CephX của cluster đích. Các bước tạo tài khoản/key/caps dưới đây dành cho quản trị viên triển khai vào môi trường staging riêng; chúng thay đổi cấu hình SSH/Ceph khi được thực hiện.

## Kết quả audit hiện tại

`rbd-console/src/ssh.js` có transport chung cho command, sudo, SFTP và shell. Profile production tại `executor.js` chặn bề mặt ghi/RBD/terminal ở tầng ứng dụng và chỉ tạo argv cố định, nhưng tài khoản SSH lab hiện có không vì thế tự trở thành tài khoản hạn chế trên server.

`collect_osd.py` đọc bằng argv và có các probe môi trường cố định. CLI của helper còn cho phép `--ceph-bin`, `--conf`, `--name`, `--keyring`, `--output`, `--all` và `--sudo-ceph`; không cho SSH key production gọi CLI này tùy ý. Guard mới chỉ nhận khuôn lệnh hiện tại, kiểm checksum source, gọi hàm thu thập với runner có allowlist và luôn gắn CephX identity riêng. Nếu helper bắt lỗi rồi trả kết quả một phần, các lỗi từ guard vẫn khiến cả thao tác thất bại.

Guard: [`deploy/ssh/console-readonly-dispatch.py`](../deploy/ssh/console-readonly-dispatch.py). Không có shell, sudo hoặc fallback về `client.admin` khi guard thực thi. Chuỗi `sudo -n` và `--sudo-ceph` do executor cũ gửi được nhận dạng như khuôn transport rồi bỏ; chúng không được chạy.

## Tài khoản và key riêng

Trên host Linux AMD64 staging, dùng Python 3.10 trở lên, Ceph CLI tương ứng cluster, một Unix account `storage-lab-console` không có quyền sudo và group cùng tên chỉ chứa account này. Account dùng `/bin/sh` để OpenSSH chạy forced command; đăng nhập mật khẩu, terminal, forwarding và user rc bị tắt bằng cấu hình SSH.

### Bàn giao cho quản trị viên trước khi cài

Các lệnh cài bên dưới chỉ được quản trị viên chạy trong phiên root được đơn vị cho phép; Console không dùng quyền `sudo ceph` của tài khoản lab để cài file hoặc vượt quyền hệ điều hành. Kiểm tra trước bằng các lệnh chỉ đọc:

```sh
id
python3 --version
command -v ceph
getent passwd storage-lab-console
getent group storage-lab-console
namei -l /etc/storage-lab-console /opt/storage-lab /usr/local/libexec/storage-lab-console /var/lib/storage-lab-console-ssh
```

Không có kết quả `getent` khi tài khoản/group chưa tồn tại là bình thường. Nếu identity, thư mục hoặc file đích đã có, dừng để kiểm chủ sở hữu, consumer và nguồn cài; không chạy đè, sửa caps, xóa account hay đổi quyền đệ quy. Group phải chỉ phục vụ account này; account không được thuộc `sudo`, `wheel`, `docker`, `lxd` hoặc nhóm quản trị khác và không có sudo rule riêng. Kiểm Python/Ceph/OpenSSH của host thực tế, không chỉ phiên bản trong app image.

Chuẩn bị guard/helper từ đúng commit hoặc image release đã duyệt, public key riêng và ba file quản trị viên đã rà soát: `reviewed-ceph.conf`, `reviewed-ssh-readonly.json`, `reviewed-authorized_keys`. Đây là tên file đầu vào mẫu, không phải file tự sinh sẵn. Không đưa private key, CephX keyring hoặc các file chứa secret lên Git, vào image, vào báo cáo hay terminal.

Quản trị viên tạo account và các thư mục sau (không dùng account/key lab sẵn có):

```sh
groupadd --system storage-lab-console
useradd --system --gid storage-lab-console --home-dir /var/lib/storage-lab-console-ssh --shell /bin/sh storage-lab-console
install -d -o root -g root -m 0755 /var/lib/storage-lab-console-ssh /var/lib/storage-lab-console-ssh/.ssh
install -d -o root -g storage-lab-console -m 0750 /etc/storage-lab-console
install -d -o root -g root -m 0755 /opt/storage-lab /usr/local/libexec/storage-lab-console
```

Tạo key SSH mới trên máy triển khai bằng `ssh-keygen -t ed25519 -f storage-lab-console-production`. Private key chỉ đặt trong secret của executor; public key được quản trị viên gắn vào file `authorized_keys` root sở hữu. Lưu fingerprint host SSH từ nguồn tin cậy, rồi đặt `RBD_SSH_HOST_KEY_REQUIRED=true` và `RBD_SSH_HOST_KEY_SHA256` hoặc known-hosts đã kiểm tra. Không lấy fingerprint chỉ từ lần kết nối chưa xác minh.

Private key phải được bảo vệ bằng ACL/mode chỉ cho danh tính chạy executor đọc. Transport `ssh.js` hiện đọc key từ file, chưa có hỗ trợ passphrase hay SSH agent: key mã hóa chưa dùng được với cấu hình này. Chọn phương án secret/key mới được chính sách đơn vị chấp thuận; không gỡ passphrase hoặc tái sử dụng key quản trị đang có để làm shortcut. Không bật đăng nhập mật khẩu nhằm xử lý lỗi public-key/account/PAM; kiểm policy account và log xác thực bằng phiên quản trị riêng.

## CephX identity và caps

Ceph mặc định dùng `client.admin` nếu không chọn tên client; guard luôn truyền `--name client.storage-lab-console`, keyring và conf cố định. Ceph hỗ trợ caps MGR theo command hoặc service. [Ceph Pacific user management](https://docs.ceph.com/en/pacific/rados/operations/user-management/)

Trên cluster staging, quản trị viên tạo **identity mới** và lưu key bằng `-o` để không in secret lên terminal. Mẫu caps cần kiểm tra trên phiên bản Ceph đích:

```sh
umask 077
ceph auth get-or-create client.storage-lab-console \
  mon 'allow r' \
  mgr 'allow service mgr r, allow service osd r, allow service pg r, allow command "orch ps", allow command "orch host ls", allow command "device ls-by-daemon"' \
  -o /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
chown root:storage-lab-console /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
chmod 0640 /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
```

Không cấp caps OSD/MDS object, `allow *`, quyền auth, upgrade, pool write hoặc Ceph admin key. `orch ps` và `orch host ls` được khai báo là command đọc trong source Pacific 16.2.15; `--refresh` yêu cầu cập nhật quan sát của orchestrator, không điều khiển daemon. [Source orchestrator Pacific](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/orchestrator/module.py)

Nếu lệnh cần thiết bị từ chối, lưu tên action và mã lỗi không có key, đối chiếu bảng command của đúng phiên bản rồi bổ sung **đúng command đọc** cần thiết. Không tự tăng caps thành admin. Việc caps này thực sự đọc đủ `versions`, PG, capacity, config và device metadata vẫn là gate phải kiểm trên cluster đích.

Không coi mẫu MGR caps là đã nghiệm thu: action cần thiết chưa đọc được thì gate vẫn **BLOCKED**, không thêm `allow *`, `rw`, `rwx`, profile quản trị hoặc fallback `client.admin`. Tầng SSH fixed-command và tầng CephX cùng phải đạt. Trong Pacific 16.2.15, các lệnh lấy/xuất auth key yêu cầu `rx`, còn quyền MON chỉ đọc không có `x`; không bổ sung quyền này cho client Console. [Bảng command Pacific](https://github.com/ceph/ceph/blob/v16.2.15/src/mon/MonCommands.h), [MON read-only capability](https://github.com/ceph/ceph/blob/v16.2.15/src/mon/MonCap.cc)

`/etc/storage-lab-console/ceph.conf` là file root sở hữu, mode `0640`, group `storage-lab-console`, chứa FSID/MON addresses của cluster đích. Không thêm admin key hoặc biến môi trường `CEPH_ARGS`. Guard xóa môi trường kế thừa trước khi chạy công cụ.

## Cài guard và policy

Quản trị viên copy source release đã duyệt, kiểm checksum, rồi cài root-owned:

```sh
install -o root -g root -m 0755 console-readonly-dispatch.py /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py
install -o root -g root -m 0644 collect_osd.py /opt/storage-lab/collect_osd.py
sha256sum /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py
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

Sau khi điền FSID, MON addresses, allowlist và SHA256 helper thực tế vào các file đầu vào đã duyệt, quản trị viên cài conf/policy bằng:

```sh
install -o root -g storage-lab-console -m 0640 reviewed-ceph.conf /etc/storage-lab-console/ceph.conf
install -o root -g storage-lab-console -m 0640 reviewed-ssh-readonly.json /etc/storage-lab-console/ssh-readonly.json
```

Conf chỉ chứa cấu hình kết nối cần thiết, không có key/admin identity, include file chưa kiểm hoặc tham số ghi log tùy ý. Không chuyển helper từ thư mục home thuộc tài khoản lab sang chạy production nếu chưa đối chiếu hash với source release được duyệt.

Một dòng `authorized_keys` root-owned mode `0644` (thay public key; có thể thêm `from="CIDR máy triển khai"` phù hợp mạng đích):

```text
restrict,no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty,command="/usr/bin/python3 -I /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py" ssh-ed25519 REPLACE_WITH_DEDICATED_PUBLIC_KEY storage-lab-console-production
```

`restrict` tắt forwarding, PTY và user rc; `command` áp dụng cả command, shell và subsystem, guard dùng `SSH_ORIGINAL_COMMAND` để kiểm khuôn lệnh. [OpenSSH authorized keys](https://man.openbsd.org/sshd)

File đầu vào `reviewed-authorized_keys` chỉ chứa public key mới với đúng dòng hạn chế ở trên. Nếu dùng `from=`, chọn địa chỉ nguồn thực tế mà sshd quan sát, kể cả NAT của máy triển khai; không đoán CIDR từ IP bên trong container. Cài và kiểm metadata, không in keyring:

```sh
install -o root -g root -m 0644 reviewed-authorized_keys /var/lib/storage-lab-console-ssh/.ssh/authorized_keys
namei -l /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py /opt/storage-lab/collect_osd.py /etc/storage-lab-console/ssh-readonly.json /etc/storage-lab-console/ceph.conf /etc/storage-lab-console/ceph.client.storage-lab-console.keyring /var/lib/storage-lab-console-ssh/.ssh/authorized_keys
stat -c '%n %U %G %a %F' /etc/storage-lab-console/ceph.client.storage-lab-console.keyring
```

Thêm block cho đúng account trong cấu hình sshd staging, không sửa block của account lab:

```text
Match User storage-lab-console
    AuthenticationMethods publickey
    PubkeyAuthentication yes
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PermitTTY no
    PermitTunnel no
    DisableForwarding yes
    X11Forwarding no
    PermitUserRC no
    AuthorizedKeysFile /var/lib/storage-lab-console-ssh/.ssh/authorized_keys
    ForceCommand /usr/bin/python3 -I /usr/local/libexec/storage-lab-console/console-readonly-dispatch.py
Match all
```

Đối chiếu các directive được phiên bản OpenSSH trên host hỗ trợ. `ForceCommand` không tự tắt forwarding, nên cần `DisableForwarding`. [OpenSSH server configuration](https://man.openbsd.org/sshd_config)

Chạy `sshd -t` và kiểm cấu hình hiệu lực `sshd -T -C user=storage-lab-console,host=HOST,addr=CLIENT_IP` trước khi quản trị viên reload sshd. Giữ phiên quản trị độc lập để phục hồi cấu hình nếu cần. Không ghi private key/CephX key vào log nghiệm thu.

Ví dụ kiểm chỉ đọc sau khi quản trị viên đặt block đúng vị trí trong cấu hình (thay hostname/IP mẫu bằng giá trị thực tế):

```sh
/usr/sbin/sshd -t
/usr/sbin/sshd -T -C user=storage-lab-console,host=REPLACE_SERVER_HOSTNAME,addr=REPLACE_OBSERVED_CLIENT_IP
```

Chỉ reload khi cả syntax và cấu hình hiệu lực đạt: đúng `forcecommand`/`authorizedkeysfile`, `authenticationmethods publickey`, `pubkeyauthentication yes`, password/kbd-interactive/TTY/tunnel/user-rc tắt, forwarding tắt và `strictmodes yes`. Các block `Match` trước đó hoặc cấu hình include có thể ảnh hưởng kết quả; không chỉ kiểm nội dung đoạn mới thêm. `PermitUserEnvironment` hiệu lực phải là `no`; `AcceptEnv` không được nhận biến điều khiển loader/interpreter như `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PYTHONPATH`, `PYTHONHOME` hay wildcard cho mọi biến. Python `-I` và việc guard xóa môi trường không thay thế việc chặn môi trường nguy hiểm trước khi Python khởi động. `PermitUserEnvironment` là điều kiện cấu hình toàn cục, không chèn vào block `Match` nếu phiên bản sshd không cho phép. [OpenSSH environment and effective settings](https://man.openbsd.org/sshd_config)

Chốt giới hạn channel/connection và tài nguyên account theo tải đã đo. `MaxSessions` chỉ giới hạn mỗi kết nối, không phải toàn bộ account; không dùng nó làm bằng chứng đã có giới hạn tổng process/RAM. Không đặt `MaxSessions 0` vì sẽ chặn luôn các exec channel thu thập cần dùng.

## Cấu hình executor staging

```dotenv
APP_ENV=production
CONSOLE_READ_ONLY=true
UPGRADE_MUTATIONS_ENABLED=false
RBD_TERMINAL_ENABLED=false
RBD_SSH_USER=storage-lab-console
RBD_SSH_HOST_KEY_REQUIRED=true
CEPH_EXPECTED_FSID=REPLACE_WITH_TARGET_FSID
UPGRADE_ALLOWED_OSDS=0,2,5
OSD_INFO_COLLECTOR_PATH=/opt/storage-lab/collect_osd.py
OSD_INFO_COLLECTOR_RUN_AS_SSH_USER=true
OSD_INFO_COLLECTOR_COMMAND_TIMEOUT_SECONDS=45
```

FSID và allowlist OSD của executor phải khớp policy server. Account không có shell/SFTP, nên tắt legacy RGW/RBD/terminal. Guard cho tối đa **16 OSD mỗi lượt**, mỗi lệnh tối đa 45 giây, toàn lượt 300 giây, stdout cuối 16 MiB và tổng nguồn 32 MiB; lượt quá lớn phải chia nhóm. File conf/keyring trên host không mount vào app container; app chỉ giữ SSH key riêng.

Đặt `RBD_SSH_KEY_PATH` trỏ đúng secret private key mới trong executor, không dùng key lab; cấu hình host/port, fingerprint và các biến mẫu bằng dữ liệu đích đã xác minh. Phải override `RBD_SSH_USER` nếu file env mẫu còn tên account khác. Khuôn lệnh Node `sudo -n ceph ...` và `python3 /opt/storage-lab/collect_osd.py ... --sudo-ceph --timeout 45` vẫn tương thích vì guard nhận dạng rồi bỏ framing, chạy Ceph bằng client riêng không sudo. Không tạo sudo rule cho `python3`, `ceph`, shell hoặc wildcard để làm các lệnh này chạy.

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

### Kiểm dương/âm và phương án quay lại an toàn

Từ máy triển khai, dùng key riêng và host key đã pin (ví dụ lệnh bên dưới dành cho shell Linux; thay các giá trị mẫu). Không dùng `StrictHostKeyChecking=no` hoặc bỏ xác minh host:

```sh
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'ceph fsid'
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'sudo -n ceph status --format=json'
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'python3 /opt/storage-lab/collect_osd.py --osd 2 --sudo-ceph --timeout 45'
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'true'
```

Ba lượt đầu phải dùng OSD thực sự trong policy và trả dữ liệu/FSID đúng; lượt `true` phải bị từ chối với exit `126` và mã `SSH_COMMAND_REJECTED`. Sau đó kiểm toàn bộ inventory actions, environment probe, SFTP/PTY/forwarding bằng bài kiểm đã duyệt. Không dùng lệnh ghi Ceph thật làm negative test. Kiểm đọc admin key/sudo/quyền sửa file bằng phiên quản trị riêng chạy dưới Unix identity này, chỉ ghi kết quả cho phép/từ chối; không đọc/in nội dung key để chứng minh.

Nếu bất kỳ action/caps hoặc restriction nào chưa đạt, giữ gate **BLOCKED** và tắt luồng executor production; không quay về account lab/admin để gắn nhãn production. Trước khi sửa sshd, quản trị viên giữ bản sao riêng của đúng cấu hình sẽ sửa và một phiên quản trị độc lập. Khi cần quay lại, chỉ phục hồi đoạn/file vừa thay từ bản sao đã kiểm, chạy lại `sshd -t` và `sshd -T -C` rồi mới reload service đúng tên của host; không restart daemon Ceph, sửa các account khác hoặc factory reset. Giữ identity/file mới ở trạng thái chưa sử dụng để điều tra; không xóa CephX key, user, policy hay keyring khi chưa xác minh không có consumer khác. Rollback SSH không được bật `client.admin`, mật khẩu, shell hoặc forwarding cho account Console.
