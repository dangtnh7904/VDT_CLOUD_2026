 

# Rà soát trước MOP lab nâng MGR từ Ceph 16.2.5 lên 16.2.15

**Ngày rà soát:** 30/09/2026.
**Phạm vi:** cụm cephadm của lab; chuẩn bị nâng riêng nhóm MGR, bắt đầu bằng standby rồi chuyển active.
**Nguồn dự án:** `dangtnh7904/VDT_CLOUD_2026`, nhánh `main`, commit `0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f`.
**Trạng thái tài liệu:** đã đọc repo và đối chiếu các điểm quan trọng với mã nguồn upstream; chưa kết nối cụm, chưa chạy nâng cấp hoặc kiểm thử runtime trên image của lab.

## 1. Kết luận: cần sửa gì trước khi bắt đầu?

**Không có một bộ biến OSD/MON phải đổi hàng loạt để nâng MGR từ 16.2.5 lên 16.2.15.** Những việc cần làm ngay là chốt đúng image, xác nhận MGR dự phòng, giữ ổn định PG trong bài thử và chuẩn bị phục hồi trước khi MGR mới có thể trở thành active.

Đối với bằng chứng đang có trong repo, có năm điểm cụ thể:

1. **Rà lại `mgr/cephadm/container_image_base`.** Snapshot ngày 23/09 đang đặt biến này bằng cả tên image custom và digest. Biến base được dùng để ghép thêm `:v<version>`, nên giá trị đó không phù hợp nếu gọi nâng bằng `--ceph-version`. Lab nên truyền **`--image` đầy đủ**; có thể sửa riêng biến base thành `quay.io/ceph/ceph` nếu muốn chuẩn hóa cách chọn image về sau.
2. **Kiểm tra rồi tạm dừng balancer và autoscaler đang tự thực thi.** Đây là lựa chọn để cô lập bài thử MGR, không phải yêu cầu tương thích bắt buộc của Ceph. Snapshot cũ còn bật cả hai; cần đọc lại hiện trạng vì bạn đã làm PA1 sau thời điểm đó.
3. **Có ít nhất một active MGR và một standby khỏe.** Snapshot cũ có hai MGR, nhưng tên/vai trò phải lấy lại ngay trước lab. Không lấy tên active từ tài liệu cũ để chạy failover.
4. **Chuẩn bị checkpoint trước lần chạy MGR target đầu tiên.** MGR target khi active có thể nâng cephadm migration state từ 2 tới 5. Đổi image về 16.2.5 không tự phục hồi control state này. `migration_current` là biến nội bộ để đọc và theo dõi, không phải biến cần tự sửa.
5. **Xử lý theo điều kiện đối với Prometheus, Dashboard và module custom.** Chỉ sửa consumer/cấu hình thực sự không tương thích. Không tắt các module hoặc hạ TLS đồng loạt để “đủ điều kiện nâng cấp”.

Luồng bắt đầu phù hợp là: **thu hiện trạng → xử lý vấn đề có thật → checkpoint → nâng standby → xác nhận standby khỏe → chuyển active → kiểm tra MGR target → hoàn tất nhóm MGR**. Bộ lọc staggered chỉ dùng sau khi active MGR đã hỗ trợ nó. [R1–R4, U1–U5]

## 2. Bằng chứng về cụm hiện có trong repo

Các thông tin dưới đây được đọc từ `as-is-base/pa1-prelab-20260923-090845`. Đây là **snapshot ngày 23/09, không phải trạng thái live ngày 30/09**. [R5]

| Hạng mục                           | Snapshot trong repo                                                                | Ý nghĩa cho lab MGR                                                                                             |
| ------------------------------------ | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| FSID                                 | `17c77e12-a16a-11f1-838e-cf68e9c001d8`                                           | Dùng để đối chiếu đang thao tác đúng cụm                                                               |
| Health                               | `HEALTH_OK`; 233 PG `active+clean`                                             | Có baseline cũ tốt; cần thu lại trước lab                                                                  |
| MON                                  | 3 MON trong quorum                                                                 | Không cần đổi topology để nâng MGR                                                                         |
| MGR                                  | Active`ceph-node2.fpgvro`; standby `ceph-master.ezhuly`; cả hai 16.2.5        | Đã từng có dự phòng; không mặc định tên/vai trò này còn đúng                                      |
| OSD                                  | 4 OSD trong snapshot đầu; đều 16.2.5                                           | Không dùng con số này làm hiện trạng sau PA1                                                               |
| RGW / MDS                            | 3 RGW; không có MDS được báo trong`ceph versions`                          | RGW đang thuộc workload cần quan sát; còn phải kiểm service spec để kết luận có/không có NFS/CephFS |
| `global/container_image`           | Image custom`docker.io/trangtran97/ceph@sha256:3694…`                           | Đây là image hiện hữu được pin; không thay global thủ công chỉ để thử một MGR                     |
| `mgr/cephadm/container_image_base` | Cũng chứa image custom kèm digest                                               | Cần tránh ghép thêm version vào giá trị này                                                               |
| `mgr/cephadm/migration_current`    | `2`                                                                              | Khớp mốc migration của cephadm 16.2.5 upstream                                                                 |
| Balancer                             | `active=true`, mode `upmap`                                                    | Chỉ tắt nếu hiện tại vẫn active; giữ nguyên nếu đã tắt cho PA1                                        |
| Autoscaler                           | 9 pool đều`on`                                                                 | Cần đọc mode hiện tại của từng pool trước khi freeze                                                     |
| Dashboard / monitoring               | Có cấu hình Dashboard cổng 8443 và địa chỉ Prometheus/Grafana/Alertmanager | Có lý do kiểm tra đường monitoring, không coi chúng mặc nhiên ngoài phạm vi                           |

**Nếu hiện tại đã có một OSD chạy 16.2.15:** ghi rõ OSD nào, version và image của nó; giữ OSD đang ổn định, rồi tiếp tục đưa nhóm MGR lên target. Không hạ OSD chỉ để làm các version giống nhau. Việc một OSD đã nâng cũng không chứng minh cephadm migration đã chạy, vì migration gắn với MGR active. Nếu OSD thực tế vẫn 16.2.5 thì chỉ ghi nhận theo kết quả mới, không suy đoán từ chữ “đã nâng”.

## 3. Phân loại thay đổi trước lab

| Hạng mục                                                | Có cần sửa trước MGR?                                                                        | Cách xử lý                                                                                                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Image đích                                              | **Phải xác định chính xác**                                                           | Dùng`quay.io/ceph/ceph:v16.2.15`, kiểm version và chốt digest thật trước redeploy; rà khác biệt nếu image cũ có module/tùy biến riêng |
| `container_image_base`                                  | Sửa nếu tiếp tục dùng đường ghép version; không bắt buộc khi luôn truyền`--image` | Giá trị base đúng là repository không kèm tag/digest:`quay.io/ceph/ceph`                                                                       |
| `global/container_image`                                | **Không đổi thủ công trước canary**                                                  | Lưu giá trị cũ; kiểm lại sau khi engine hoàn tất phase vì engine có thể thay cấu hình image                                                |
| Số MGR / standby                                         | Sửa nếu thiếu standby hoặc standby lỗi                                                       | Khôi phục/bổ sung MGR theo placement hiện có, trên host khỏe; không ghi đè placement bằng một lệnh apply chung chưa xem spec              |
| `migration_current`                                     | **Không tự set/reset**                                                                    | Chụp trước, kiểm sau; sửa lỗi migration bằng nguyên nhân thực, không ép số 2 hoặc 5                                                       |
| Balancer                                                  | Freeze nếu đang tự cân bằng                                                                  | `ceph balancer off`; lưu trạng thái gốc để hoàn trả đúng                                                                                    |
| `pg_autoscale_mode`                                     | Freeze các pool đang`on` trong bài lab                                                       | Đổi từng pool cần thiết sang`off`; giữ `warn`/`off` nếu đó là baseline; không thay `pg_num`                                          |
| `noautoscale` toàn cục                                | Không dựa vào để chuẩn bị trên nguồn 16.2.5                                              | Dùng chế độ từng pool vốn đã có ở nguồn; không lấy tính năng target làm prerequisite cho MON/MGR cũ                                    |
| `noout`, `norebalance`, `nobackfill`, `norecover` | **Không cần đặt thêm vì nâng MGR**                                                   | Không restart OSD trong bước này. Nếu có cờ từ PA1, xét theo trạng thái PA1; không gỡ hoặc bật hàng loạt                               |
| CRUSH, weight, primary-affinity, upmap                    | Không phải thao tác chuẩn bị MGR                                                             | Ghi baseline; hoàn tất hoặc ổn định việc chuyển PG đang dở trước lab; không đưa thêm PG ra/vào X đồng thời                          |
| OSD service`unmanaged`                                  | Không phải yêu cầu chung của MGR upgrade                                                     | Giữ chủ đích hiện có của PA1; không đổi mọi service sang unmanaged; không dựa vào unmanaged như hàng rào chặn mọi đường upgrade   |
| Prometheus / alert rules                                  | Sửa khi parser, query, rule hoặc route thực tế không tương thích                          | Kiểm image target và đường scrape; chuẩn bị nguồn quan sát độc lập; xem mục 6                                                              |
| Dashboard TLS                                             | Sửa nếu đường kết nối tới Dashboard không hỗ trợ TLS 1.3                               | Ưu tiên sửa client/proxy/backend TLS; không tự bật chế độ TLS yếu hơn                                                                        |
| Custom MGR modules                                        | Sửa nếu image mới thiếu module/dependency hoặc callback không tương thích                | Rà module, mount và`NOTIFY_TYPES`; kiểm chức năng sau khi target active                                                                          |
| Key chung cũ / giá trị không hợp lệ                 | Sửa đúng nguồn cấu hình nếu thực sự ảnh hưởng MGR                                     | Đặc biệt`ms_async_max_op_threads` bị bỏ; `log_max_recent` có min mới. Không xóa hàng loạt key mà daemon base còn dùng                 |
| Health, thời gian, dung lượng, SSH                     | Sửa nếu đang có vấn đề                                                                     | Xử lý quorum, clock skew, MON disk, host unreachable, daemon crash loop trước thử failover                                                         |

Các điểm này thu hẹp từ báo cáo `06`, `07`, `08` và bản điều kiện mới trong `ceph-upgrade-16.2.15`. Không áp toàn bộ checklist nâng cả cụm vào bài lab MGR. [R1–R4]

## 4. Thu hiện trạng mới trước khi quyết định sửa

### 4.1 Nguyên tắc chạy lệnh

Các lệnh `ceph` bên dưới sử dụng cách truy cập cụm đang hoạt động của bạn trên `ceph-master` — CLI đã cấu hình hoặc wrapper `cephadm shell` hiện có. Nếu chạy shell trong container, thư mục xuất bằng chứng phải được bind-mount ra host. `jq`, `curl`, `promtool`, `docker`, `df`, `chronyc` là công cụ trên host tương ứng.

Không cần cài lệnh `cephadm` độc lập trên node2/node3 chỉ để orchestrator redeploy daemon. Cần các host vẫn được cephadm quản lý, SSH và container runtime hoạt động.

`ceph --version` chỉ báo phiên bản CLI đang gọi. Dùng `ceph versions`, `ceph mgr metadata` và `ceph orch ps` để xác định daemon. [U1, U7]

### 4.2 Lệnh đọc trạng thái

Chạy trong cùng một phiên terminal; các lệnh trong phần này không yêu cầu đổi cấu hình cụm. Lệnh nào lỗi phải đọc lỗi, không coi file đầu ra tồn tại là kiểm tra đã đạt.

```bash
umask 077
export EVIDENCE="$PWD/mgr-precheck-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$EVIDENCE"

ceph fsid > "$EVIDENCE/00-fsid.txt"
ceph -s > "$EVIDENCE/01-ceph-s.txt"
ceph health detail > "$EVIDENCE/02-health-detail.txt"
ceph versions -f json-pretty > "$EVIDENCE/03-versions.json"
ceph mgr dump -f json-pretty > "$EVIDENCE/04-mgr-dump.json"
ceph mgr metadata -f json-pretty > "$EVIDENCE/05-mgr-metadata.json"
ceph mgr module ls -f json-pretty > "$EVIDENCE/06-mgr-modules.json"
ceph mgr services -f json-pretty > "$EVIDENCE/07-mgr-services.json"
ceph orch status > "$EVIDENCE/08-orch-status.txt"
ceph orch upgrade status > "$EVIDENCE/09-upgrade-status.txt"
ceph orch ps --refresh -f json-pretty > "$EVIDENCE/10-orch-ps.json"
ceph orch ls --export > "$EVIDENCE/11-service-specs.yaml"
ceph orch host ls -f json-pretty > "$EVIDENCE/12-hosts.json"
ceph config dump -f json-pretty > "$EVIDENCE/13-config-dump.json"
ceph quorum_status -f json-pretty > "$EVIDENCE/14-quorum.json"
ceph osd dump -f json-pretty > "$EVIDENCE/15-osd-dump.json"
ceph osd pool ls detail -f json-pretty > "$EVIDENCE/16-pools.json"
ceph osd pool autoscale-status > "$EVIDENCE/17-autoscale.txt"
ceph balancer status > "$EVIDENCE/18-balancer.json"
ceph pg stat > "$EVIDENCE/19-pg-stat.txt"
ceph crash ls-new > "$EVIDENCE/20-crashes.txt"
ceph fs ls -f json-pretty > "$EVIDENCE/21-filesystems.json"
```

Nếu module tùy chọn chưa bật và lệnh của module đó không có, ghi rõ là không áp dụng. Không bật module chỉ để chạy lệnh thu thập. Với tùy chọn CLI khác ở build custom, xem `ceph orch ps --help` và dùng cú pháp được build đó hỗ trợ.

Đọc riêng các biến và cấu hình MGR thực tế:

```bash
ceph config get mgr mgr/cephadm/container_image_base
ceph config get mgr mgr/cephadm/migration_current
ceph config get global container_image

# Thay bằng tên daemon hiện tại, gồm tiền tố mgr.
ceph config show mgr.TEN_MGR_THUC_TE
```

`config get` có thể không trả giá trị cho option chưa được đặt trong config DB. Khi đó đối chiếu `config dump`, default của đúng phiên bản và log, không tự tạo một override để làm lệnh hết lỗi. Với cấu hình module có scope theo MGR, kiểm cả các entry localized/per-daemon, không chỉ entry ở `mgr`.

Trên các host chứa MGR/MON, kiểm dung lượng filesystem thực chứa dữ liệu Ceph và container runtime, RAM và đồng bộ thời gian:

```bash
df -h / /var/lib/ceph
df -i / /var/lib/ceph
free -h
timedatectl status
chronyc tracking
```

Lệnh `chronyc` chỉ áp dụng nếu host dùng chrony. Nếu còn cảnh báo MON thiếu dung lượng, cần tạo đủ chỗ cho cả image mới và image cũ để phục hồi; không chỉ hạ ngưỡng cảnh báo. Nếu có crash cũ, đọc `ceph crash info <id>` và xác định nguyên nhân, không archive tất cả để che lỗi đang tiếp diễn.

### 4.3 Kết quả tối thiểu phải rút ra

| Câu hỏi                                            | Cách quyết định                                                                                                                                      |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Active và standby hiện tại là ai?                | Lấy từ`mgr dump`, đối chiếu metadata và trạng thái daemon mới refresh                                                                         |
| Có upgrade hoặc mutation khác đang chạy không? | Xem upgrade status, cephadm events, service specs và hoạt động PA1; không tạo thêm một bộ điều khiển nâng cấp chồng lên tiến trình cũ |
| MGR đích có chạy được trên host không?      | Pull/inspect/run version của đúng image trên từng host MGR                                                                                          |
| Còn pool nào tự đổi PG không?                  | Dùng mode từng pool và trạng thái PG hiện tại; đóng freeze trước canary                                                                       |
| Có NFS/CephFS không?                               | Kiểm service specs và`fs ls`; không suy từ việc đang dùng RGW/RBD rằng dịch vụ khác chắc chắn vắng mặt                                  |
| Đường monitoring thật là gì?                   | Tách exporter`/metrics` của MGR với HTTP API của Prometheus server; lấy endpoint từ `mgr services` và config scrape đang chạy               |
| Cụm có đủ ổn định để thử failover không?  | MGR dự phòng khỏe, quorum ổn định, các OSD dự kiến hoạt động bình thường, PG ổn định và workload không có lỗi chưa xử lý        |

## 5. Những chỉnh sửa tối thiểu có thể đưa vào MOP

### 5.1 Chọn image và sửa biến base nếu cần

Đặt biến shell trước; việc `export` không thay cấu hình Ceph:

```bash
export TARGET_IMAGE='quay.io/ceph/ceph:v16.2.15'
```

Trên từng host có MGR, dùng runtime đang quản lý Ceph. Ví dụ nếu dùng Docker:

```bash
sudo docker pull "$TARGET_IMAGE"
sudo docker image inspect "$TARGET_IMAGE" --format '{{json .RepoDigests}}'
sudo docker run --rm --entrypoint ceph "$TARGET_IMAGE" --version
```

Sau đó chốt `TARGET_IMAGE` bằng repo digest vừa kiểm tra nếu dùng manifest cố định. **Không dùng image ID ngắn như `f15b41add2c0` thay cho registry digest `sha256:…`.** Lưu image cũ của từng MGR; không mặc định image cũ của mọi daemon giống nhau.

Có thể kiểm đường nhận diện image của orchestrator mà chưa khởi động upgrade:

```bash
ceph orch upgrade check --image "$TARGET_IMAGE"
```

Lệnh check có thể pull/inspect image. Danh sách daemon cần nâng trong kết quả không có nghĩa nó đã bắt đầu nâng tất cả daemon.

**Chỉ khi hiện trạng vẫn có giá trị base sai và muốn sửa nó**, lưu giá trị cũ rồi thực hiện:

```bash
ceph config get mgr mgr/cephadm/container_image_base \
  > "$EVIDENCE/container-image-base-before.txt"

ceph config set mgr mgr/cephadm/container_image_base quay.io/ceph/ceph
```

Đây là sửa cách orchestrator xây dựng tên image mặc định, không phải lệnh redeploy. Trong MOP vẫn truyền `--image "$TARGET_IMAGE"` để mục tiêu không phụ thuộc biến base. **Không chạy `ceph config set global container_image ...` như bước chuẩn bị canary MGR.** [R5, U1, U5]

### 5.2 Freeze balancer và autoscaler trước khi MGR mới có thể active

Nếu `balancer status` hiện tại báo `active=true`:

```bash
ceph balancer off
```

Nếu đã `false`, giữ nguyên. Không xóa các upmap hiện hữu.

Với từng pool hiện đang `pg_autoscale_mode=on`, ghi mode gốc rồi tạm chuyển sang `off`:

```bash
# Thay POOL_THUC_TE bằng pool đã đối chiếu trong snapshot hiện tại.
ceph osd pool get POOL_THUC_TE pg_autoscale_mode
ceph osd pool set POOL_THUC_TE pg_autoscale_mode off
```

Không chạy mù cho mọi pool nếu chưa lưu mode. Pool đang `warn` không tự áp thay đổi PG; pool đã `off` không cần set lại. Không thay `target_size_ratio`, `pg_num`, `pgp_num`, `pg_num_min/max` hoặc cờ `bulk` trong bài thử này.

Sau freeze, đợi các thay đổi PG đã phát sinh trước đó hoàn tất. Tắt autoscaler/balancer không tự hủy backfill hoặc PG transition đã bắt đầu. Freeze cần làm **trước lần redeploy standby đầu tiên**, vì standby mới có thể tự được promote nếu active cũ gặp sự cố. [R2, U6]

### 5.3 Những giá trị chưa có lý do phải tune

Giữ baseline cho `mgr_ttl_cache_expire_seconds`, `mon_mgr_beacon_grace`, mức debug, `mgr_standby_modules`, `osd_memory_target`, `osd_memory_target_autotune` và `mgr/cephadm/autotune_memory_target_ratio`, trừ khi hiện trạng chứng minh có vấn đề cụ thể.

Đặc biệt, không lấy quy mô production 1.600 OSD làm lý do đặt TTL cache cho lab nhỏ ngay trong lần thử nâng đầu tiên. Theo dõi CPU/RSS/latency MGR trước và sau; tối ưu hiệu năng là phép thử tiếp theo. Nếu memory autotune đang bật, ghi cả effective target của OSD để nhận diện thay đổi do reconciliation; không coi mọi biến động bộ nhớ là do restart OSD. [R1–R3, U7–U8]

## 6. Những việc chỉ phải sửa khi đúng điều kiện

### 6.1 Prometheus: kiểm nội dung scrape, không chỉ HTTP 200

Repo chỉ ra nguy cơ duplicate `HELP/TYPE` của `ceph_pool_objects_repaired`. Đối chiếu upstream tag `v16.2.15` xác nhận có static metric cùng tên và các metric được dựng riêng theo pool. **Đây là bằng chứng mã nguồn; chưa phải kết quả scrape của image đang dùng trong lab.** [R2, U4]

Trước canary, chuẩn bị parser hoặc Prometheus thử nghiệm và các tín hiệu độc lập: `ceph -s`, PG state, logs và probe đọc/ghi RGW/RBD. Sau khi target làm active, lấy đúng endpoint được công bố:

```bash
ceph mgr services -f json-pretty

# Điền URL exporter MGR active vừa xác nhận; thường là cổng 9283.
export METRICS_URL='http://IP_MGR_ACTIVE:9283/metrics'
curl --fail --silent --show-error --max-time 20 \
  "$METRICS_URL" -o "$EVIDENCE/target-mgr-metrics.txt"
test -s "$EVIDENCE/target-mgr-metrics.txt"
promtool check metrics < "$EVIDENCE/target-mgr-metrics.txt"
```

Chạy từng lệnh và kiểm exit status. Đồng thời xem Prometheus target, `last_error`, `up` và các series cần cho bài thử. Lỗi lint cần phân loại; lỗi parse hoặc thiếu dữ liệu bắt buộc chặn việc mở rộng. Không dùng endpoint standby để kết luận: upstream target có thể trả `/metrics` HTTP 200 nhưng body rỗng.

Nếu gặp lỗi format, chọn build có sửa lỗi đã kiểm hoặc hoàn thiện nguồn quan sát độc lập cho bài lab trước khi tiếp tục. Báo cáo hiện tại không chứng minh một biến Ceph có thể bật/tắt để chữa regression này; không chèn một lệnh “fix” suy đoán vào MOP.

### 6.2 Alert rules và monitoring stack

So rule/route đang chạy với bộ dự kiến sau nâng, đặc biệt nơi match chính xác `alertname`. Con số 18 tên cũ và 58 tên mới trong report là so sánh artifact upstream, **không chứng minh Prometheus của lab hiện dùng đúng bộ 18 tên cũ**.

Khi dùng filtered upgrade để hoàn tất MGR, monitoring stack có thể được redeploy dù không đổi phiên bản container. Chuẩn bị baseline scrape, rule và config trước bước đó; kiểm lại sau. Vì vậy phạm vi đánh giá phải bao gồm tác động tới monitoring, dù phạm vi đổi phiên bản Ceph được chọn là `mgr`. [R2–R3, U1, U5]

### 6.3 Dashboard

Upstream 16.2.15 dùng minimum TLS 1.3 mặc định khi bật HTTPS. Nếu browser, script hoặc chặng reverse proxy → Dashboard chỉ hỗ trợ TLS 1.2, sửa đúng chặng kết nối trước khi để target phục vụ Dashboard. TLS phía người dùng → proxy hỗ trợ 1.3 chưa đủ chứng minh phía proxy → MGR cũng hỗ trợ. [R2, U9]

Nếu Dashboard chỉ là giao diện phụ của bài lab, có thể ghi nhận chưa nghiệm thu Dashboard và dùng CLI/nguồn quan sát đủ chức năng; không gọi đó là hoàn tất nghiệm thu toàn bộ MGR. `UNSAFE_TLS_v1_2` là ngoại lệ tương thích cần quyết định riêng, không là giá trị chuẩn bị mặc định.

### 6.4 Module custom và image custom

Nếu image `trangtran97/ceph` có module, Python dependency hoặc mount bổ sung, liệt kê chúng trước khi chuyển sang image public. Module override `notify()` cần khai báo đúng `NOTIFY_TYPES` theo API target. Không tự thêm declaration cho tất cả module hoặc copy nguyên site-packages cũ vào image mới.

Standby chạy được chưa chứng minh mọi module active đã thực thi đúng. Sau promote phải gọi chức năng thật của module đang dùng, kiểm import/load/callback và log. Nếu chỉ dùng module upstream tiêu chuẩn và không có tùy biến ngoài image, ghi bằng chứng rồi đánh dấu nhánh custom là không áp dụng. [R2]

### 6.5 NFS/CephFS và registry riêng

Nếu không có các dịch vụ này, không kéo toàn bộ test MDS/NFS vào lab MGR. Tuy nhiên, **NFS migration có thể bắt đầu ngay từ MGR target**, nên sự vắng mặt phải được xác nhận trước.

Nếu có NFS legacy, phải kiểm riêng spec, export và grace state trước promote. Nếu dùng private registry, kiểm pull và credential trên từng host MGR. Image public Quay không tự cần thêm credential, nhưng cấu hình registry riêng đã tồn tại vẫn phải được ghi nhận vì migration có thể chuyển vị trí lưu nó. [R3, U2–U3]

## 7. Checkpoint và ranh giới phục hồi của MGR

Mã nguồn upstream cho thấy:

- `v16.2.5`: `LAST_MIGRATION = 2`; điều kiện “migration đang diễn ra” so khác 2.
- `v16.2.15`: có các bước tới `LAST_MIGRATION = 5`, liên quan NFS, quản lý `client.admin` và credential registry.
- Sau khi state lên 5, code base không có transition xử lý ngược về 2. Vì vậy failover về MGR base không chứng minh cephadm đã có thể reconcile/apply service bình thường. [U2–U3]

**Chốt checkpoint trước lần redeploy MGR target đầu tiên**, vì target có thể được promote ngoài dự kiến. Lần chủ động `ceph mgr fail` là mốc kiểm soát chính, nhưng không phải con đường duy nhất để target trở thành active.

Gói bằng chứng tối thiểu gồm config DB, module state/cephadm store cần thiết, service specs, host inventory, mapping image cũ/mới và các cấu hình monitoring đang chạy. Nếu cần dump config-key, lưu riêng có quyền hạn chế:

```bash
umask 077
ceph config-key dump > "$EVIDENCE/private-config-key-dump.json"
chmod 600 "$EVIDENCE/private-config-key-dump.json"
```

File này có thể chứa credential và khóa; không đưa nguyên vào repo hoặc báo cáo chia sẻ. Một bản export config-key/spec là bằng chứng hỗ trợ, **không phải bản backup có thể tự restore đầy đủ bằng một lệnh import**.

Với lab VM nhỏ, nếu muốn có đường quay lại trước thử nghiệm, nên chuẩn bị checkpoint nhất quán của toàn bộ lab theo hypervisor: quiesce workload, dừng đồng bộ các VM theo kế hoạch và bao gồm toàn bộ disk liên quan. Chỉ có thể gọi đây là đường rollback sau khi đã biết cách phục hồi cả tập checkpoint. Không restore riêng một MON về thời điểm cũ giữa cụm đang chạy; không coi snapshot riêng VM MGR là đã sao lưu control state lưu ở MON/RADOS.

Nếu chưa có checkpoint phục hồi được, ghi rõ chọn hướng giữ target/forward-fix và giới hạn chấp nhận của lab; không ghi “rollback = đổi lại image”. Không sửa `migration_current` để ép qua kiểm tra.

## 8. Trình tự dùng để bắt đầu MOP lab MGR

Đây là trình tự thao tác sau khi hoàn tất phần chuẩn bị ở trên. Chạy từng bước, đọc kết quả rồi mới đi tiếp; không dán toàn bộ thành một script chạy liên tục.

### Bước 1 — Chốt vai trò, target và trạng thái trước đổi

Đọc lại `ceph mgr dump`, `ceph mgr metadata`, `ceph orch ps --refresh`, health và upgrade status. Điền:

| Biến               | Giá trị phải lấy từ cụm                     |
| ------------------- | ------------------------------------------------- |
| `TARGET_IMAGE`    | Tag/digest đã kiểm trên host MGR              |
| `OLD_ACTIVE_ID`   | ID active không có tiền tố`mgr.`            |
| `STANDBY_DAEMON`  | Tên đầy đủ`mgr.<id>` của standby          |
| Image cũ từng MGR | Tên và digest đang chạy trước lần đổi    |
| Checkpoint          | ID/thời điểm và phạm vi phục hồi thực tế |

Không dùng tên ví dụ trong snapshot 23/09 nếu hiện trạng đã đổi.

### Bước 2 — Redeploy standby lên target

```bash
ceph orch daemon redeploy "$STANDBY_DAEMON" --image "$TARGET_IMAGE"
```

Chỉ thực hiện khi các biến đã được điền đúng. Lệnh trả “scheduled” chưa đủ: chờ daemon thực sự chạy target, còn xuất hiện trong danh sách standby, không restart loop, active cũ còn khỏe. Nếu có nhiều standby, nâng lần lượt và xác nhận tất cả ứng viên có thể được promote đều chạy target trước lần failover chủ động. [U1]

### Bước 3 — Chuyển active có kiểm soát

Xác nhận lần cuối `OLD_ACTIVE_ID` vẫn là active và standby target khỏe, rồi:

```bash
ceph mgr fail "$OLD_ACTIVE_ID"
```

Lệnh này đánh dấu active hiện tại failed để MON chọn standby; nó không phải lệnh chỉ định đích danh một MGR mới. Sau lệnh, đọc lại `mgr dump` và metadata để chứng minh active thực tế là target. Không fail liên tiếp khi chưa biết active mới là ai. [U7]

### Bước 4 — Đánh giá MGR target active trước khi mở rộng

Kiểm các kết quả sau:

- Active chạy đúng version/image; module cần thiết phản hồi; orchestrator dùng được, không crash/failover loop.
- `migration_current` đạt trạng thái hoàn tất phù hợp target upstream, thông thường 5 với nguồn 2; không còn lỗi migration đang treo. Giá trị 5 riêng lẻ không thay thế kiểm dịch vụ.
- Prometheus parser/scrape và Dashboard/module áp dụng đã được kiểm; luôn có nguồn quan sát hoạt động trong thời gian chuyển vai trò.
- PG, quorum, OSD và workload RGW/RBD ổn định so với baseline; không có hành động placement ngoài dự kiến.

Có thể chọn cửa sổ quan sát **10–15 phút cho lab nhỏ**, sau khi dịch vụ đã hồi phục, để lấy bằng chứng ban đầu. Đây là đề xuất cho bài lab, không phải ngưỡng đảm bảo của Ceph hoặc thời gian nghiệm thu production.

Nếu có lỗi, dừng mở rộng và dùng mục 9. Không mặc định failback về MGR cũ sau khi migration đã chạy.

### Bước 5 — Hoàn tất nhóm MGR bằng engine target

Chỉ thực hiện sau khi active target, migration và các kiểm tra thiết yếu đã đạt; monitoring stack đã sẵn sàng chịu refresh; không còn phiên upgrade cũ đang chạy hoặc paused:

```bash
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types mgr
```

**Không gọi lệnh có `--daemon-types mgr` khi active còn 16.2.5.** Hỗ trợ bộ lọc được bổ sung từ Pacific 16.2.11. Cũng không thay bằng lệnh upgrade toàn cụm rồi trông chờ pause kịp. [U1]

Theo dõi:

```bash
ceph orch upgrade status
ceph orch ps --refresh -f json-pretty
ceph versions
ceph -W cephadm
```

`ceph -W cephadm` là lệnh theo dõi liên tục; mở ở terminal riêng hoặc dùng Ctrl+C để thoát.

**Hai tác động cần ghi trong MOP:**

1. Engine có thể redeploy monitoring stack sau MGR để cập nhật cách triển khai/config. Không hứa rằng mọi daemon ngoài MGR tuyệt đối không bị chạm tới.
2. Trong source 16.2.15, đường hoàn tất upgrade có bước ghi `global/container_image` và dọn một số override theo loại daemon. Vì vậy so config image trước/sau ngay cả với filtered phase; việc ghi config không đồng nghĩa mọi daemon còn lại đã tự restart, nhưng có thể đổi image dùng cho lần deploy/redeploy sau. Không chạy redeploy ngoài phạm vi trong lúc chưa đối chiếu xong. [U5]

Nếu mục tiêu buổi thử chỉ dừng ở “standby target chạy được”, dừng **trước bước 3** và ghi rõ chưa thử active/migration. Nếu đã promote và muốn nghiệm thu cả nhóm MGR, cần hoàn thành bước 5 và kiểm kết quả; không để trạng thái mixed MGR kéo dài như một phương án phục hồi đã được chứng minh.

### Bước 6 — Kết thúc bài lab MGR

- Mọi MGR dự kiến đều đúng target; có active và standby khỏe; upgrade status đã kết thúc phase.
- Kiểm version/image và metadata triển khai (`deployed_by` nếu build công bố), không chỉ chuỗi version trên một MGR.
- Đối chiếu lại daemon ngoài MGR, monitoring và config image; ghi rõ mọi thay đổi do engine.
- Chụp lại config DB, service specs, migration state, health, PG và kết quả probe.
- Kiểm cả `mon_mds_skip_sanity` nếu dùng engine upgrade: source target có thể đặt trong đường chạy và xóa khi hoàn tất. Nếu phase bị ngắt hoặc baseline đã có override, đối chiếu trước/sau rồi xử lý đúng giá trị cũ; không tự set nó trước lab. [U5]
- Chỉ bật lại balancer nếu baseline của buổi thử là active và việc PA1 không còn yêu cầu giữ tắt. Khôi phục autoscale theo **mode gốc từng pool**, sau khi đọc recommendation của MGR mới; việc bật lại có thể gây đổi PG nên theo dõi riêng.
- Chưa chuyển sang MON trong cùng lần thử nếu mục tiêu đã chốt là nghiệm thu MGR.

## 9. Khi có lỗi thì dừng ở đâu?

| Tình huống                                                     | Hành động trước tiên                                                                                                                                                                                     |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pull image hoặc standby startup lỗi, target chưa từng active | Giữ active cũ; dừng thao tác tiếp; kiểm image, config, mount và log. Chỉ quay binary standby về bản cũ sau khi xác nhận chưa có target active/migration và còn đủ dữ liệu triển khai cũ |
| Target đã active, module hoặc monitoring lỗi                 | Dừng mở rộng; giữ quorum/data service; thu log, sửa module/config/consumer hoặc dùng nguồn quan sát độc lập đã kiểm. Không tự ép migration state về 2                                       |
| Engine đang chạy filtered phase và cần dừng                 | Dùng`ceph orch upgrade pause`; xác nhận trạng thái paused. Pause không hoàn tác daemon hoặc migration đã diễn ra                                                                                 |
| Thao tác đang là chuỗi manual redeploy/failover              | Dừng gửi lệnh tiếp theo.`upgrade pause` không phải nút undo các lệnh manual đã schedule                                                                                                           |
| Orchestrator mất chức năng sau failover                       | Kiểm MGR active, module cephadm và journal trên host đó; dùng đường quản trị host đã chuẩn bị nếu API không phản hồi; không failover vòng lặp hoặc chỉnh state để che lỗi           |
| Cần trở về toàn bộ trạng thái trước lab                 | Chỉ restore theo checkpoint nhất quán và quy trình đã thử; chấp nhận RPO từ thời điểm checkpoint. Không phục hồi riêng một thành phần cũ vào cụm đang tiếp tục ghi                  |

`ceph orch pause` tạm dừng hoạt động điều phối rộng hơn và có thể làm các thao tác cần cho lab không chạy. Không dùng nó như bước freeze mặc định thay cho balancer/autoscaler. `ceph orch upgrade stop` cũng không tự rollback image/config; nếu dùng, vẫn phải đối chiếu các thay đổi tạm và state còn lại. [R4, U5, U8]

## 10. Quyết định có thể đưa ra lúc này

**Đã đủ căn cứ để soạn và bắt đầu phần thu hiện trạng của MOP lab MGR. Chưa đủ dữ liệu live để kết luận cụm đang sẵn sàng redeploy.**

Các đầu vào còn thiếu là: active/standby hiện tại, health mới, image/digest thật, trạng thái upgrade, mode balancer/autoscaler sau PA1, module/service đang dùng và checkpoint phục hồi.

Nếu kiểm tra mới xác nhận cụm ổn định, standby khỏe và không có dependency không tương thích, thì phần thay đổi trước lab chỉ cần: **chốt image; xử lý biến base nếu chọn sửa; freeze đúng automation đang bật; chuẩn bị phục hồi; xử lý các consumer có lỗi thật.**

Không cần đưa vào prerequisite của bài lab này: drain OSD, PA1 mới, H0, đổi scheduler mClock, reshard RocksDB, migrate DB/WAL, tăng `require_osd_release`, nâng client RBD hay nâng MON. Các nội dung đó thuộc những phase sau, trừ khi hiện trạng cụ thể đang gây mất ổn định và phải xử lý trước.

## 11. Nguồn đã đối chiếu

### Repo dự án — cố định theo commit đã đọc

- **R1 — Cấu hình:** [06-config-defaults.md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/comparison/pacific-16.2.5-to-16.2.15/06-config-defaults.md).
- **R2 — MGR/monitoring:** [07-mgr-modules-monitoring.md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/comparison/pacific-16.2.5-to-16.2.15/07-mgr-modules-monitoring.md).
- **R3 — Cephadm/migration:** [08-cephadm-orchestrator.md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/comparison/pacific-16.2.5-to-16.2.15/08-cephadm-orchestrator.md).
- **R4 — Bộ kế hoạch mới:** [02 — Điều kiện và thay đổi](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/comparison/pacific-16.2.5-to-16.2.15/ceph-upgrade-16.2.15/02-DIEU-KIEN-VA-THAY-DOI.md), [04 — Canary và rollout](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/comparison/pacific-16.2.5-to-16.2.15/ceph-upgrade-16.2.15/04-PHASE-2-CANARY-VA-ROLLOUT.md), [10 — Fallback/rollback](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/comparison/pacific-16.2.5-to-16.2.15/ceph-upgrade-16.2.15/10-STOP-FALLBACK-ROLLBACK.md).
- **R5 — Snapshot lab 23/09:** [pa1-prelab-20260923-090845](https://github.com/dangtnh7904/VDT_CLOUD_2026/tree/0d6d1cc05a12821599ab2d2685ff3b3c6066bc7f/as-is-base/pa1-prelab-20260923-090845); đã đọc `01-ceph-s.txt`, `03-versions.txt`, `09-config-dump.txt`, `19-balancer-status.txt`, `20-autoscale-status.txt`.

### Tài liệu và mã nguồn Ceph

- **U1:** [Pacific — Upgrading Ceph, đặc biệt bước chuyển sang staggered upgrade](https://docs.ceph.com/en/pacific/cephadm/upgrade/).
- **U2:** [migrations.py tại v16.2.5](https://github.com/ceph/ceph/blob/v16.2.5/src/pybind/mgr/cephadm/migrations.py).
- **U3:** [migrations.py tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/migrations.py).
- **U4:** [Prometheus module tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/prometheus/module.py), các hàm `_setup_static_metrics`, `get_pool_repaired_objects`, `str_expfmt` và standby `/metrics`.
- **U5:** [upgrade.py tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/upgrade.py) và [module.py tại v16.2.5](https://github.com/ceph/ceph/blob/v16.2.5/src/pybind/mgr/cephadm/module.py), cho image selection, redeploy, filter, monitoring và finalize.
- **U6:** [Pacific — Placement Groups/autoscaling](https://docs.ceph.com/en/pacific/rados/operations/placement-groups/).
- **U7:** [Pacific — ceph-mgr administrator’s guide](https://docs.ceph.com/en/pacific/mgr/administrator/).
- **U8:** [Pacific — Cephadm Operations](https://docs.ceph.com/en/pacific/cephadm/operations/) và [serve.py tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/serve.py).
- **U9:** [Dashboard module.py](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/dashboard/module.py) và [settings.py](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/dashboard/settings.py) tại v16.2.15.

Các kết luận mã nguồn áp dụng cho tag upstream đã đọc. Image custom/public thực tế vẫn phải đối chiếu provenance và kiểm runtime; tài liệu này không gán kết quả PASS cho các phép thử chưa chạy.
