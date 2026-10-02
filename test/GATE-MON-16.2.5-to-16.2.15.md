# Gate và test lab — MON 16.2.5 → 16.2.15

Phiên bản 1.0 · 01/10/2026. Thực hiện cùng [MOP-MON-16.2.5-to-16.2.15.md](./MOP-MON-16.2.5-to-16.2.15.md). MOP chứa thứ tự thao tác; file này chứa phép thử, bằng chứng, điều kiện đi tiếp và xử lý cấu hình/dữ liệu thử.

## 1. Quy tắc quyết định

Baseline dự kiến: MGR đã ở `16.2.15`, một OSD đã ở target, các MON chuẩn bị nâng từ `16.2.5`. G0 phải kiểm chứng lại. Tài liệu áp dụng cho ba MON trên ba host, không stretch; không dùng nguyên điều kiện 3/3 cho topology khác.

Trạng thái của từng gate là **NOT RUN / PASS / HOLD / FAIL / N/A**. Thiếu evidence là HOLD; N/A cần có bằng chứng dịch vụ/tính năng không được dùng. Hiện chưa chạy trên cụm nên không gate nào được ghi PASS sẵn.

| Gate | Thời điểm | Trả lời câu hỏi |
| --- | --- | --- |
| G0 | Trước sửa cấu hình | Đúng cụm, đúng topology và đúng baseline MGR/OSD chưa? |
| G1 | Trước MON đầu, kiểm tra lại trước mỗi MON | Host, clock, network, disk và artifact có sẵn sàng? |
| G2 | Trước canary; đối chiếu lại ở canary/final | Có cấu hình nào phải sửa/bỏ hoặc có thể đổi tác dụng khi MON mới chạy? |
| G3 | 10 phút trước canary; giữ observer/tải xuyên rollout | Auth và client I/O ban đầu có ổn định, evidence có dùng được? |
| G4 | Cho từng MON, trước và sau redeploy | Có được dừng MON này và nó đã trở lại khỏe ở target? |
| G5 | Sau MON canary, trước mở rộng | Mixed MON/OSD có an toàn trong phạm vi quan sát? |
| G6 | Khi leader chuyển; khi leader target phục vụ | Quorum, auth và state proposal có ổn định qua election? |
| G7 | Sau khi cả ba MON target | Nghiệm thu phần MON được chưa? |
| G8 | Sau hoàn nguyên và cleanup | Chỉ giữ thay đổi mong muốn, dữ liệu thử đã xử lý đúng chưa? |

Ngưỡng mặc định đề xuất cho lab dưới đây phải được chốt **trước baseline**. Nếu môi trường cần ngưỡng khác, ghi lý do trước khi chạy; không nới ngưỡng sau lỗi để đổi FAIL thành PASS.

| Hạng mục | Ngưỡng/tiêu chí |
| --- | --- |
| Quorum trước mỗi lần restart | Đủ 3/3, đủ đúng ba tên MON trong MonMap |
| Trong rolling | Tối thiểu hai MON giữ quorum; một lần election ngắn có thể xảy ra. Mất mẫu CLI không tự chứng minh mất quorum: HOLD mở rộng và đối chiếu journal/local status |
| MON đang nâng | Trở lại quorum trong 300 giây kể từ lúc nó dừng; xếp hàng redeploy quá 300 giây cũng HOLD để điều tra |
| Sau mỗi daemon | Quorum 3/3 và không election mới trong ít nhất 5 phút |
| Soak canary | Ít nhất 15 phút kể từ khi canary trở lại quorum |
| Soak cuối | Ít nhất 30 phút sau MON cuối; kéo dài nếu còn anomaly chưa giải thích |
| Client I/O | 0 lỗi cuối cùng, 0 timeout, 0 checksum mismatch; RBD mỗi vòng write/flush/read ≤10 giây, S3 PUT/GET/verify ≤30 giây |
| Độ trễ so baseline | p95 của cùng probe ≤ max(2 × p95 baseline, 1 giây); dùng riêng RBD và S3. Đây là gate hồi quy lab, không phải benchmark hiệu năng |
| Lệnh quản trị/fresh auth | Trả thành công trong 30 giây; lỗi hoặc thiếu mẫu buộc điều tra trước bước tiếp theo |
| Health | Không có lỗi mới về quorum, auth, clock, disk, OSD/PG/data; warning phiên bản tạm thời phải khớp danh sách daemon mixed đã biết |

Tải nhẹ bên dưới kiểm tra continuity/correctness. Muốn kết luận p99/IOPS hoặc SLA ứng dụng cần workload và số mẫu phù hợp riêng. Soak 15/30 phút cũng không tự chứng minh đã đi qua toàn bộ chu kỳ CephX key rotation; ghi phạm vi quan sát, không chỉnh TTL/rotate key để ép phép thử.

## 2. G0 — inventory, baseline và evidence khôi phục

Các lệnh `c` dùng hàm/biến trong mục 3 của MOP. Kiểm tra exit code và nội dung từng file; một file rỗng hoặc lỗi JSON không phải evidence hợp lệ.

```bash
c -s --format json-pretty > "$EVIDENCE/pre-status.json"
c health detail --format json-pretty > "$EVIDENCE/pre-health.json"
c versions --format json-pretty > "$EVIDENCE/pre-versions.json"
c orch host ls --format json-pretty > "$EVIDENCE/pre-hosts.json"
c orch ps --refresh --format json-pretty > "$EVIDENCE/pre-orch-ps.json"
c orch ls --export > "$EVIDENCE/pre-service-specs.yaml"
c orch upgrade status --format json-pretty > "$EVIDENCE/pre-upgrade.json"
c quorum_status --format json-pretty > "$EVIDENCE/pre-quorum.json"
c mon dump --format json-pretty > "$EVIDENCE/pre-monmap.json"
c mon metadata --format json-pretty > "$EVIDENCE/pre-mon-metadata.json"
c mgr dump --format json-pretty > "$EVIDENCE/pre-mgr.json"
c osd metadata --format json-pretty > "$EVIDENCE/pre-osd-metadata.json"
c osd dump --format json-pretty > "$EVIDENCE/pre-osdmap.json"
c osd tree --format json-pretty > "$EVIDENCE/pre-osd-tree.json"
c osd pool ls detail --format json-pretty > "$EVIDENCE/pre-pools.json"
c pg stat --format json-pretty > "$EVIDENCE/pre-pg.json"
c fs ls --format json-pretty > "$EVIDENCE/pre-filesystems.json"
c config dump --format json-pretty > "$EVIDENCE/pre-config.json"
c crash ls-new --format json-pretty > "$EVIDENCE/pre-crashes.json"
# File binary ghi qua thư mục đã mount vào cephadm shell.
c mon getmap -o /evidence/pre-monmap.bin
c osd getmap -o /evidence/pre-osdmap.bin

jq -r '.[] | [.daemon_name,.hostname,.status_desc,.version,.container_image_name,
  (.container_image_id // ""),((.container_image_digests // [])|join(","))] | @tsv' \
  "$EVIDENCE/pre-orch-ps.json" > "$EVIDENCE/pre-daemons.tsv"
jq '{quorum_names,quorum_leader_name,election_epoch,quorum_age}' \
  "$EVIDENCE/pre-quorum.json"
```

Đối chiếu MonMap với inventory host và service spec. Điền bảng vận hành, không dựa vào thứ tự alphabet hoặc rank để đoán leader:

| MON ID | Host | Addrvec trong MonMap | Role hiện tại | Version runtime | Digest runtime | Thứ tự dự kiến |
| --- | --- | --- | --- | --- | --- | --- |
| Điền từ cụm | | | follower | 16.2.5 | | 1 — canary |
| Điền từ cụm | | | follower | 16.2.5 | | 2 |
| Điền từ cụm | | | leader | 16.2.5 | | 3, đọc lại role trước thao tác |

Ghi riêng MGR active/standby và **ID của OSD target**, không chỉ tổng số phiên bản. Tất cả MGR phục vụ/standby phải thực sự target; tránh đường MON mới nói chuyện với MGR base mà báo cáo `MSG-009` nêu. Không nâng lại OSD đã target và không hạ nó xuống để dựng baseline đồng nhất.

**PASS:** đúng FSID; đúng ba MON khỏe, MGR active và standby target; danh sách OSD mixed có bằng chứng; không còn upgrade running/paused hay redeploy chưa hoàn tất; các PG phục vụ ổn định, không có recovery/backfill/PG resize đang chạy; các warning cũ có disposition; evidence/config/image cũ được lưu và có cách truy cập host khi CLI mất quorum.

Nếu có CephFS hoặc stretch, áp dụng mục 11 trước khi duyệt G0. Không dùng `pre-monmap.bin` hay bản copy nóng RocksDB làm bằng chứng đã có full backup. Recovery một MON dựa vào quorum còn tốt cần quy trình riêng; phục hồi cả lab về checkpoint cần snapshot nhất quán đã được kiểm chứng.

## 3. G1 — host, time, network, disk và image

Chạy trên **từng host MON**, với FSID/MON_ID của host đó; lưu output vào evidence theo tên host. Runtime bên dưới minh họa Docker, thay bằng Podman nếu đó là runtime thực tế.

```bash
date -u +%FT%TZ
timedatectl status
chronyc tracking
chronyc sources -v
sudo df -hT "/var/lib/ceph/$FSID/mon.$MON_ID"
sudo df -i "/var/lib/ceph/$FSID/mon.$MON_ID"
sudo du -sh "/var/lib/ceph/$FSID/mon.$MON_ID/store.db"
sudo systemctl status "ceph-${FSID}@mon.${MON_ID}.service" --no-pager
sudo ss -lntp

# Pre-pull và kiểm tra binary trong artifact, chưa redeploy daemon.
sudo docker pull "$TARGET_IMAGE"
sudo docker image inspect --format '{{json .RepoDigests}}' "$TARGET_IMAGE"
sudo docker run --rm --entrypoint ceph "$TARGET_IMAGE" --version
```

Nếu lab dùng dịch vụ NTP khác chrony, dùng công cụ của dịch vụ đó và ghi rõ, không bỏ qua đồng bộ thời gian. Các kiểm tra thời gian phải khớp với:

```bash
c time-sync-status --format json-pretty
c health detail
c config show "mon.$MON_ID" --format json-pretty
c config get mon public_network
```

**PASS:** không có clock-skew; offset nhỏ hơn `mon_clock_drift_allowed` hiệu lực; không tăng allowance để vượt gate. Địa chỉ và các endpoint v1/v2 đang dùng trong MonMap reachable giữa các host MON và từ client; `ss` chỉ chứng minh lắng nghe local, cần kiểm kết nối thực tế với endpoint trong MonMap. Không tự bật v2 hoặc đổi port trong cửa sổ này.

Free space phải cao hơn ngưỡng `mon_data_avail_warn` hiệu lực, không cạn inode, đồng thời còn chỗ cho image pull và tăng store/log trong cửa sổ. Nếu MON store đã lớn hoặc host sát ngưỡng, giải quyết trước; bản sửa trim ở target không bảo đảm filesystem lập tức được trả lại dung lượng. Không xóa `store.db`, không force compact/rebuild như bước vệ sinh.

Image trên cả ba host phải có digest đã chọn và binary đúng `16.2.15`. Chỉ tag giống nhau hoặc image name trên orchestrator là chưa đủ. `public_network`/spec phải cho cephadm tái tạo được cấu hình MON với identity/address hiện có; nếu thiếu, xử lý theo MOP mục 4, không đoán CIDR từ một địa chỉ IP.

## 4. G2 — audit cấu hình và quyết định sửa/xóa

### 4.1. Bắt buộc phân biệt stored config và effective config

Lưu `config dump` thể hiện cấu hình trung tâm; `config show <daemon>` thể hiện cấu hình daemon báo về. Local config, command line, service spec hoặc override runtime cũng phải được đối chiếu nếu có. Không kết luận không có override chỉ từ một nguồn.

```bash
c config dump --format json-pretty > "$EVIDENCE/config-original.json"
c balancer status --format json-pretty > "$EVIDENCE/balancer-original.json"
c osd pool ls detail --format json-pretty > "$EVIDENCE/pools-original.json"

# Giữ nguyên section/mask/name; không làm mất mask khi chuẩn hóa tên option.
jq '.[] | select((.mask // "") != "" or
  ((.name // "") | test("container_image|mon_mds_skip_sanity|log_max_recent|ms_async_max_op_threads|ms_die_on_bad_msg")))' \
  "$EVIDENCE/config-original.json" > "$EVIDENCE/config-focus.json"

while IFS= read -r daemon; do
  c config show "$daemon" --format json-pretty \
    > "$EVIDENCE/$daemon.config-before.json" || break
done < <(jq -r '.[] | select(.daemon_type=="mon" or .daemon_type=="osd") | .daemon_name' \
  "$EVIDENCE/pre-orch-ps.json")
```

Nếu một lần lấy config thất bại, vòng lặp dừng; **G2 HOLD** cho đến khi có đủ file hợp lệ cho danh sách daemon. Với lab nhỏ, chụp tất cả OSD. Với lab lớn, ít nhất mỗi nhóm host/class/mask có một OSD đại diện, bao gồm OSD target và OSD base; ghi rõ phần chưa phủ.

`config dump` ở target có thay đổi tên localized của masked option. Diff phải giữ đủ `(section, mask, tên option, value)` và đối chiếu nguồn, không gộp hai mask vì cùng hậu tố tên. Epoch, timestamp và thứ tự JSON không phải cấu hình cần hoàn nguyên.

### 4.2. Bảng quyết định cấu hình

| Mục | Trước nâng | Trong/sau canary | Quyết định sửa/xóa |
| --- | --- | --- | --- |
| `container_image` global/type/daemon | Lưu tất cả scope, running digest và desired image | Chỉ scope `mon.<id>` được MOP đặt target; theo dõi mọi diff ngoài dự kiến | Giữ pin MON target; không reset global hoặc xóa pin OSD đã nâng |
| `log_max_recent` | Tìm override 0 áp dụng lên MON ở mọi nguồn | Effective ≥1 và không có lỗi validation | Sửa đúng scope cần thiết, giữ giá trị hợp lệ |
| `ms_async_max_op_threads` | Xác định có vào config MON và consumer cũ nào dùng | Tìm unknown/deprecated option khi target lên | Bỏ cấu hình riêng của MON nếu đã xác minh; giữ nhu cầu của daemon base. Không đổi tên sang `ms_async_reap_threshold` |
| `mon_mds_skip_sanity` | Ghi có/không, scope, giá trị và owner | Redeploy riêng MON không cần bật biến này | Giá trị cũ từ MGR/upgrade trước: chỉ xóa/restore khi đã xác minh là tạm, owner đã kết thúc |
| `ms_die_on_bad_msg` | Ghi giá trị và xác nhận toàn bộ MGR đã target | Không có unknown message/assert | Không blanket-set false để bỏ qua lỗi |
| CRUSH/location/device-class mask | Với từng mask, liệt kê OSD khớp và giá trị dự kiến; giữ snapshot effective của cả hai patch level | So effective config sau từng bước, đặc biệt sau leader target/reconnect | Delta đúng thiết kế: ghi nhận. Delta ngoài dự kiến: HOLD, sửa mask/scope đúng nguyên nhân |
| `require_osd_release`, `min_mon_release` | Lưu nguyên giá trị; cả hai patch vẫn là Pacific | Không dùng các trường này làm bằng chứng patch 16.2.15 | MOP không nâng release floor; giá trị cũ bất thường được xử lý riêng sau audit daemon legacy |
| Range/CIDR blocklist | Xem trạng thái hiện có trong OSDMap/config automation | Không tạo entry range mới trong cửa sổ mixed | Không thử feature này hoặc xóa entry đang bảo vệ client để thuận tiện nâng |
| Pool/CRUSH/upmap/PG autoscale | Lưu pool size/min_size/pg_num/autoscale/rule, upmap và cờ OSD hiện có | Theo dõi remap/recovery và config diff | Không xóa PA1/upmap còn có chủ đích. Không resize PG hay chạy balancer lớn để test MON |

Những key của OSD/MDS/RGW/RBD bị remove/rename trong báo cáo 06 vẫn có trong danh sách audit toàn hop, nhưng **không phải danh sách phải xóa ở bước MON**: `osd_mclock_max_capacity_iops`, `mds_max_retries_on_remount_failure`, `rgw_rados_pool_pg_num_min`, `rgw_bucket_quota_soft_threshold`, `rbd_persistent_cache_log_periodic_stats`. Chuyển đổi mClock và data/cache format thuộc MOP role tương ứng.

Nếu phải freeze placement để quan sát, ghi thay đổi trước khi thực hiện:

```bash
# Chỉ nếu balancer đang active và đã quyết định tạm dừng.
c balancer off

# Chỉ cho pool đã xác định, lưu mode cũ on/warn/off trong change record trước.
c osd pool set "$POOL_TO_FREEZE" pg_autoscale_mode off
```

Không disable module pg_autoscaler trên toàn cụm như thao tác mặc định. Nếu placement vốn đã ổn định và không có automation cạnh tranh thì giữ cấu hình. Chờ PG ổn định sau mọi sửa chuẩn bị, rồi chụp thêm `config-ready.json`/`pools-ready.json` làm mốc G3; `original` dùng để khôi phục phần tạm, `ready` dùng để đánh giá tác động riêng của MON.

**PASS:** mỗi finding đã được phân loại giữ/sửa/bỏ/N/A với scope và lý do; mọi thay đổi cần thiết đã xác minh; có kỳ vọng effective config cho các mask. Nếu không có mask hoặc key cũ liên quan, không phải thêm/chỉnh biến để tạo phép thử.

Sổ thay đổi tối thiểu:

| Thời điểm | Key/tài nguyên | Scope/mask/nguồn | Trước: tồn tại + giá trị | Sau | Tạm hay giữ | Lệnh khôi phục/xóa | Người thực hiện |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Điền khi có thay đổi | | | | | | | |

## 5. G3 — baseline và các probe giữ xuyên rollout

Mỗi observer/probe chạy trong một terminal riêng. Các terminal client dùng cùng RUN_ID, CLIENT_EVIDENCE và biến kết nối; terminal quản trị dùng biến/hàm của MOP. Đây là tài liệu thao tác theo chặng, không phải một script để chạy toàn bộ từ đầu đến cuối. Chốt fixture và quyền truy cập trước, rồi mới bắt đầu tính 10 phút baseline.

### 5.1. Observer quorum

Trong một terminal quản trị riêng có cùng biến/hàm `c`, chạy vòng dưới. Dừng bằng Ctrl-C sau G7. Mỗi mẫu cách nhau **ít nhất** 5 giây; thời gian thực tế còn gồm thời gian gọi cephadm/CLI. Poll không chứng minh không có sự cố giữa hai mẫu, vì vậy phải đối chiếu journal của cả ba MON.

```bash
while :; do
  at=$(date -u +%FT%TZ)
  if c quorum_status --format json > "$EVIDENCE/quorum-current.json" \
      2> "$EVIDENCE/quorum-current.err"; then
    jq -c --arg at "$at" '{at:$at,ok:true,quorum_names,quorum_leader_name,
      election_epoch,quorum_age,monmap_epoch:.monmap.epoch}' \
      "$EVIDENCE/quorum-current.json" >> "$EVIDENCE/quorum-timeline.jsonl" \
      || { echo 'HOLD: observer nhận JSON không hợp lệ'; break; }
  else
    rc=$?
    jq -nc --arg at "$at" --argjson rc "$rc" '{at:$at,ok:false,rc:$rc}' \
      >> "$EVIDENCE/quorum-timeline.jsonl"
    cat "$EVIDENCE/quorum-current.err" >> "$EVIDENCE/quorum-errors.log"
    echo 'HOLD: mất mẫu quorum, cần đối chiếu journal trước khi nâng tiếp'
  fi
  sleep 5
done
```

Chạy thêm `c health detail`, `c pg stat`, `c mgr dump`, `c orch ps --refresh`, `c crash ls-new` tại trước/sau từng MON và khi có anomaly, lưu kèm UTC. Có thể dùng `ceph -W cephadm` trong phiên Ceph riêng để xem action; wrapper `c` có timeout nên không dùng nó cho một phiên watch kéo dài.

### 5.2. Fresh-client auth và old-client compatibility

Trên client lab đang có binary, `ceph.conf`, keyring và quyền đọc status; **giữ nguyên binary/client config trong suốt rollout**. Có ít nhất một client cùng phiên bản đang dùng trước nâng để kiểm chứng client cũ. CLI quản trị target trong MOP không thay thế phép thử client cũ.

```bash
export CLIENT_ID='DIEN_ID_KHONG_CO_TIEN_TO_client.'
export CLIENT_CONF='/etc/ceph/ceph.conf'
export RUN_ID='CHEP_RUN_ID_TU_PHIEN_QUAN_TRI'
export CLIENT_EVIDENCE="$PWD/evidence-$RUN_ID"
umask 077
mkdir -p "$CLIENT_EVIDENCE"
ceph --version > "$CLIENT_EVIDENCE/client-version.txt"

while :; do
  at=$(date -u +%FT%TZ)
  start_ns=$(date +%s%N)
  timeout --kill-after=2s 30s ceph --conf "$CLIENT_CONF" --id "$CLIENT_ID" -s \
    > "$CLIENT_EVIDENCE/auth-last.out" 2> "$CLIENT_EVIDENCE/auth-last.err"
  rc=$?
  end_ns=$(date +%s%N)
  printf '%s,%s,%s\n' "$at" "$rc" "$(( (end_ns-start_ns)/1000000 ))" \
    >> "$CLIENT_EVIDENCE/auth.csv"
  if (( rc != 0 )); then
    cat "$CLIENT_EVIDENCE/auth-last.err" >> "$CLIENT_EVIDENCE/auth-errors.log"
    echo 'HOLD: fresh client auth/status thất bại'
  fi
  sleep 5
done
```

Mỗi iteration tạo process mới, kiểm tra khả năng kết nối/auth mới thay vì chỉ nhìn session cũ. Vì client có thể nối bất kỳ MON nào, `-s` thành công không chứng minh nó đã đi qua canary. Tại G5/G7 chạy thêm `ceph --mon-host "$CANARY_ADDRVEC" ... -s` với addrvec thật trong MonMap và thu log kết nối để xác định endpoint; bootstrap address vẫn có thể dẫn tới các MON khác qua MonMap. Cần bằng chứng endpoint/daemon logs nếu ghi PASS riêng cho auth trên canary.

Không export/import hay rotate key; không sửa auth caps để làm mất lỗi. Lỗi quyền có sẵn của tài khoản probe phải được phát hiện và giải quyết ở baseline. Dùng tài khoản sẵn có phù hợp phạm vi lab, không công bố nội dung keyring.

### 5.3. RBD — session dài, write/flush/read và reopen

Áp dụng khi lab dùng RBD. Client cần `rbd`, Python 3 với module `rados` và `rbd`, config/keyring đang hoạt động. Nếu workload thật dùng krbd/QEMU, giữ một workload kiểm chứng trên đường đó nữa; probe librbd dưới đây không thay thế toàn bộ kiểm thử guest filesystem/kernel.

Chỉ dùng **image mới dành riêng cho RUN_ID trong pool RBD lab có sẵn**, không dùng volume máy ảo/application. Không tạo pool, đổi PG hoặc map/mkfs thiết bị trong phép thử này.

```bash
export RBD_POOL='DIEN_POOL_RBD_LAB'
export TEST_IMAGE="mon-gate-$RUN_ID"
python3 -c 'import rados, rbd; print("python bindings available")'
rbd --conf "$CLIENT_CONF" --id "$CLIENT_ID" --pool "$RBD_POOL" \
  create "$TEST_IMAGE" --size 64
rbd --conf "$CLIENT_CONF" --id "$CLIENT_ID" --pool "$RBD_POOL" \
  info "$TEST_IMAGE" --format json > "$CLIENT_EVIDENCE/rbd-fixture.json"
```

Nếu tên đã tồn tại, không ghi đè và không tiếp tục: tạo RUN_ID mới hoặc điều tra lần chạy cũ. Lưu script sau thành `$CLIENT_EVIDENCE/rbd_probe.py` trên client. Script không tạo/xóa image; chỉ ghi image thử đã tạo. `rbd_cache=false` chỉ áp dụng process thử để giảm khả năng read-back được trả từ cache client; không set vào config cụm.

```python
import csv, hashlib, json, os, sys, time
from pathlib import Path
import rados, rbd

mode = sys.argv[1]                  # run hoặc verify
if mode not in ("run", "verify"):
    raise ValueError("mode phải là run hoặc verify")
ev = Path(os.environ["CLIENT_EVIDENCE"])
pool = os.environ["RBD_POOL"]
name = os.environ["TEST_IMAGE"]
run_id = os.environ["RUN_ID"]
if name != "mon-gate-" + run_id:
    raise ValueError("STOP: tên image không khớp fixture")
client = rados.Rados(conffile=os.environ["CLIENT_CONF"],
                     name="client." + os.environ["CLIENT_ID"])
client.conf_set("rbd_cache", "false")
client.conf_set("rados_osd_op_timeout", "10")
client.conf_set("rados_mon_op_timeout", "10")
client.connect()
manifest_path = ev / "rbd-last-blocks.json"
blocks = {}
try:
    with client.open_ioctx(pool) as ioctx:
        with rbd.Image(ioctx, name) as im:
            if mode == "verify":
                manifest = json.loads(manifest_path.read_text())
                if (manifest["pool"], manifest["image"], manifest["run_id"]) != (pool, name, run_id):
                    raise ValueError("STOP: manifest không khớp fixture")
                if not manifest["blocks"]:
                    raise ValueError("HOLD: manifest rỗng")
                for offset, expected in manifest["blocks"].items():
                    actual = hashlib.sha256(im.read(int(offset), 4096)).hexdigest()
                    if actual != expected:
                        raise IOError("checksum mismatch offset=" + offset)
                print("PASS reopen:", len(manifest["blocks"]), "blocks")
            else:
                n = 0
                with (ev / "rbd.csv").open("a", newline="", buffering=1) as log:
                    writer = csv.writer(log)
                    try:
                        while not (ev / "stop-rbd").exists():
                            at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            start = time.monotonic()
                            offset = (n % 256) * 4096
                            data = hashlib.sha256((run_id + ":" + str(n)).encode()).digest() * 128
                            try:
                                written = im.write(data, offset)
                                if written != len(data):
                                    raise IOError("short write")
                                im.flush()
                                if im.read(offset, len(data)) != data:
                                    raise IOError("read-back mismatch")
                                ms = round((time.monotonic() - start) * 1000, 3)
                                blocks[str(offset)] = hashlib.sha256(data).hexdigest()
                                writer.writerow([at, 0, ms, n])
                                if ms > 10000:
                                    raise RuntimeError("RBD round > 10 s")
                            except Exception as err:
                                writer.writerow([at, 1, round((time.monotonic() - start) * 1000, 3), repr(err)])
                                raise
                            n += 1
                            time.sleep(1)
                        im.flush()
                        print("Probe stopped; verify bằng process mới trước cleanup")
                    except KeyboardInterrupt:
                        writer.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                         1, 0, "interrupted-mid-run"])
                        raise RuntimeError("HOLD: dùng stop-file để dừng ở ranh giới vòng")
                    finally:
                        manifest_path.write_text(json.dumps({"pool": pool, "image": name,
                            "run_id": run_id, "blocks": blocks}, indent=2))
finally:
    client.shutdown()
```

Chạy trước canary, giữ nguyên process qua tất cả MON và soak cuối:

```bash
python3 "$CLIENT_EVIDENCE/rbd_probe.py" run
# Cuối soak G7: terminal khác tạo stop-file, chờ terminal probe thoát xong.
touch "$CLIENT_EVIDENCE/stop-rbd"
# Chạy process mới sau khi probe đã đóng image:
python3 "$CLIENT_EVIDENCE/rbd_probe.py" verify \
  | tee "$CLIENT_EVIDENCE/rbd-reopen.txt"
```

Nếu script lỗi hoặc không còn mẫu mới, HOLD và giữ image/evidence; không khởi động lại rồi bỏ mất kết quả lỗi. Không dùng Ctrl-C/kill làm cách dừng thông thường: stop-file cho phép vòng write/flush/read hiện tại kết thúc. Nếu bị kill giữa write/verify, manifest chỉ có các block đã xác minh, không đủ để kết luận mọi write đã PASS.

### 5.4. RGW/S3 — PUT/GET/checksum qua endpoint thật

Áp dụng khi lab dùng RGW. Dùng AWS CLI và profile đã cấu hình trên client; endpoint là endpoint mà client thực sự dùng, bao gồm LB/TLS nếu có. Không dùng `--no-verify-ssl` để vượt lỗi mới. Fixture mặc định là một key duy nhất trong **bucket lab chưa bật versioning**; nếu bucket dùng versioning phải có manifest VersionId và cleanup tương ứng, không dùng block cleanup đơn giản ở G8.

```bash
export AWS_PROFILE='DIEN_PROFILE_LAB'
export AWS_PAGER=''
export AWS_MAX_ATTEMPTS=1
export AWS_RETRY_MODE=standard
export S3_ENDPOINT='DIEN_ENDPOINT_LAB'
export TEST_BUCKET='DIEN_BUCKET_LAB_KHONG_VERSIONING'
export TEST_KEY="mon-gate/$RUN_ID/probe.bin"
aws --version > "$CLIENT_EVIDENCE/aws-version.txt" 2>&1

s3api() {
  timeout --kill-after=2s 20s aws --endpoint-url "$S3_ENDPOINT" \
    --cli-connect-timeout 5 --cli-read-timeout 10 s3api "$@"
}
s3api get-bucket-versioning --bucket "$TEST_BUCKET" \
  > "$CLIENT_EVIDENCE/s3-versioning.json"
```

Đọc file: phải không có `Status=Enabled` hoặc `Suspended` cho nhánh cleanup này. Xác nhận key/prefix thuộc RUN_ID mới, chưa tồn tại; dùng `list-objects-v2`/quyền phù hợp để xác nhận, không coi AccessDenied là “không tồn tại”.

```bash
n=0
while [[ ! -e "$CLIENT_EVIDENCE/stop-s3" ]]; do
  at=$(date -u +%FT%TZ)
  start_ns=$(date +%s%N)
  # Payload mới mỗi vòng, tránh GET dữ liệu cũ vẫn trùng checksum.
  head -c 65536 /dev/urandom > "$CLIENT_EVIDENCE/s3-payload.bin" || break
  if ! s3api put-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
       --body "$CLIENT_EVIDENCE/s3-payload.bin" \
       > "$CLIENT_EVIDENCE/s3-put-last.json" 2> "$CLIENT_EVIDENCE/s3-put-last.err"; then
    printf '%s,1,0,PUT\n' "$at" >> "$CLIENT_EVIDENCE/s3.csv"
    echo 'HOLD: PUT lỗi'; break
  fi
  if ! s3api get-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
       "$CLIENT_EVIDENCE/s3-get.bin" \
       > "$CLIENT_EVIDENCE/s3-get-last.json" 2> "$CLIENT_EVIDENCE/s3-get-last.err"; then
    printf '%s,1,0,GET\n' "$at" >> "$CLIENT_EVIDENCE/s3.csv"
    echo 'HOLD: GET lỗi'; break
  fi
  if ! cmp -s "$CLIENT_EVIDENCE/s3-payload.bin" "$CLIENT_EVIDENCE/s3-get.bin"; then
    printf '%s,1,0,CHECKSUM\n' "$at" >> "$CLIENT_EVIDENCE/s3.csv"
    echo 'FAIL: S3 mismatch'; break
  fi
  end_ns=$(date +%s%N)
  ms=$(( (end_ns-start_ns)/1000000 ))
  printf '%s,0,%s,%s\n' "$at" "$ms" "$n" >> "$CLIENT_EVIDENCE/s3.csv"
  cp "$CLIENT_EVIDENCE/s3-payload.bin" "$CLIENT_EVIDENCE/s3-last-verified.bin"
  if (( ms > 30000 )); then echo 'HOLD: S3 round > 30 s'; break; fi
  n=$((n+1))
  sleep 2
done
```

Cuối soak G7, từ terminal khác tạo stop-file, chờ loop kết thúc vòng hiện tại rồi lấy lại object bằng process AWS CLI mới để so checksum lần cuối trước DELETE:

```bash
touch "$CLIENT_EVIDENCE/stop-s3"
# Chờ terminal loop thoát; kiểm tra không có lỗi trong log trước khi chạy tiếp.
s3api get-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
  "$CLIENT_EVIDENCE/s3-reopen.bin" > "$CLIENT_EVIDENCE/s3-reopen.json"
cmp "$CLIENT_EVIDENCE/s3-last-verified.bin" "$CLIENT_EVIDENCE/s3-reopen.bin"
sha256sum "$CLIENT_EVIDENCE/s3-last-verified.bin" "$CLIENT_EVIDENCE/s3-reopen.bin" \
  > "$CLIENT_EVIDENCE/s3-final-sha256.txt"
```

Nếu bị ngắt giữa PUT/GET, dùng log và payload của vòng đó để xác định trạng thái, không bỏ qua write đã được ACK. Lỗi bị SDK retry che mất không được tính như không có lỗi; cấu hình probe trên giảm retry tự động để ghi nhận lỗi rõ hơn.

### 5.5. Chốt baseline và cách tính kết quả

Ghi UTC bắt đầu/kết thúc baseline, từng lần redeploy, từng lần rejoin, canary soak và final soak vào `phases.tsv`; dùng cùng RUN_ID trên client/admin, đồng bộ clock. Các sample có timestamp bắt đầu; mẫu giao ranh giới restart được xếp vào cửa sổ chuyển tiếp, không loại khỏi báo cáo.

Tính số mẫu, số lỗi, max và p95 từ cột 3 (ms) của `auth.csv`, `rbd.csv`, `s3.csv` theo từng cửa sổ. Có thể dùng đoạn Python sau với các CSV đã cắt đúng pha, mỗi file không có header:

```python
import csv, math, sys
for path in sys.argv[1:]:
    rows = list(csv.reader(open(path)))
    errors = sum(int(r[1]) != 0 for r in rows)
    lat = sorted(float(r[2]) for r in rows if int(r[1]) == 0)
    if not lat:
        print(path, "HOLD: không có mẫu thành công", "errors=", errors)
        continue
    p95 = lat[max(0, math.ceil(.95 * len(lat)) - 1)]
    print(path, "samples=", len(rows), "errors=", errors, "p95_ms=", p95, "max_ms=", max(lat))
```

Nếu dùng Prometheus, chụp trạng thái scrape ngay ở baseline và lặp lại khi canary/final. Dùng API và cơ chế truy cập hiện có của lab; ví dụ endpoint không yêu cầu thêm auth:

```bash
export PROM_URL='DIEN_URL_PROMETHEUS'
curl --fail --silent --show-error --max-time 15 \
  "$PROM_URL/api/v1/targets" > "$EVIDENCE/prom-targets-baseline.json"
jq '.data.activeTargets[] | {job:.labels.job,scrapeUrl,health,lastScrape,lastError}' \
  "$EVIDENCE/prom-targets-baseline.json"
```

Kiểm tra đủ target dự kiến, scrape gần hiện tại, `health=up`, `lastError` rỗng cho các target cần theo dõi. Danh sách target rỗng hoặc target cần thiết bị thiếu không phải PASS. Scrape thực tế qua Prometheus mới kiểm tra parser/ingest, không chỉ status HTTP của `/metrics`. Nếu không có monitoring stack, ghi N/A và dùng observer/CLI/journal đầy đủ.

**G3 PASS:** ít nhất 10 phút ổn định, các probe bắt buộc thực sự chạy và có mẫu, không lỗi/checksum mismatch, độ trễ baseline dùng được, clocks đồng bộ, giám sát đang dùng hoạt động và observer không có khoảng trống chưa giải thích. Nếu RBD/RGW không dùng, ghi N/A bằng inventory; không dùng N/A vì thiếu công cụ hoặc chưa chuẩn bị fixture.

## 6. G4 — gate cho mỗi MON

| Điểm kiểm tra | Evidence | PASS / HOLD |
| --- | --- | --- |
| Ngay trước redeploy | `quorum_status`, `orch ps --refresh`, `mon ok-to-stop <id>` | Đủ đúng 3/3; không MON khác down/sync; chọn đúng daemon cũ; ok-to-stop exit 0; G1 không xuất hiện blocker mới |
| Khi MON dừng | Quorum timeline, log ba MON, probes client | Hai MON còn lại duy trì quorum; không error/timeout/data mismatch; không daemon ngoài MON bị đổi image |
| Khi MON lên | `tell mon.<id> version`, `mon_status`, runtime digest, `orch ps --refresh` | Version 16.2.15 và đúng digest; process phục vụ thật; status leader/peon hợp lệ, có tên trong quorum |
| Sau khi rejoin | 5 phút timeline/log, health/PG/MGR/OSD | Quorum 3/3 liên tục trong phần quan sát, không election mới; health trở về baseline cho phép; PG/client không có regression |

`orch ps` có cache, nên dùng `--refresh` và xác minh runtime. `mon metadata`/`ceph versions` có thể cần thời gian cập nhật sau election; không coi desired image hoặc metadata đơn lẻ là đủ. `min_mon_release=16` chỉ nói Pacific, không chứng minh patch `16.2.15`.

Nếu quá 300 giây chưa rejoin hoặc mất một MON khác: HOLD, không restart MON khác để “thử chữa”. MON recovered muộn cũng cần ghi sự cố và chạy lại gate, không tự đánh dấu PASS nhờ cuối cùng đã lên.

## 7. G5 — canary mixed MON/OSD

Canary là **một follower target cùng hai MON base**, trong khi OSD vẫn có cả base và target. Sau G4, giữ tối thiểu 15 phút và đối chiếu:

| Test | Chứng cứ phải có | Điều kiện đi tiếp |
| --- | --- | --- |
| Quorum/election | Timeline + journal, role từng MON | Đủ 3/3, không elect/sync lặp |
| Fresh auth | Probe client cũ và client quản trị, log endpoint canary khi cần | Client mới auth được; không chuỗi EAGAIN/reconnect lỗi kéo dài |
| I/O đang chạy | RBD/S3 CSV, checksum và thời điểm restart | Không lỗi cuối cùng/mismatch; p95 và max trong ngưỡng đã chốt |
| MGR/OSD continuity | `mgr dump`, `versions`, OSD inventory, health, pg stat | MGR active/standby target giữ dịch vụ; OSD up/in đúng baseline; không thêm OSD được nâng |
| Effective config | Snapshot MON/OSD sau canary so với `ready` | Delta mask đúng dự kiến; không có option invalid/unknown chưa xử lý |
| Placement/store | OSDMap, PG, disk/store size, log Paxos | Không recovery/remap bất thường hoặc tăng store lỗi; giải thích delta trước khi mở rộng |

Chụp lại config cho các daemon đã lấy ở G2, đặt hậu tố `.config-canary.json`; sau toàn bộ MON đặt `.config-final.json`. Đặc biệt so các giá trị từ mask liên quan memory/recovery/scheduler/host/class trên OSD target và OSD base.

**Nếu có mask có tác động vận hành:** unchanged effective config trên OSD chưa reconnect chưa đủ chứng minh MON mới resolve giống cũ. Cần evidence OSD/session đã nhận config từ MON target, hoặc một rehearsal reconnect riêng có phạm vi và gate OSD được duyệt trong lab. MOP MON này không tự restart OSD để ép coverage. Chưa có evidence và chưa chứng minh mask không liên quan thì G5 HOLD ở phần đó; không ghi “đã test reconnect” chỉ vì MON đã restart.

Không cần thử CIDR blocklist, resize/merge PG, remove MON, tạo pool mới, `ceph-monstore-tool` hoặc force compaction để PASS canary. Đây là các capability/recovery path có điều kiện, không phải smoke test của nâng MON.

## 8. G6 — leader transition và leader target

Thu `quorum_status` ngay trước/sau sự kiện, version leader cũ/mới và journal cả ba MON quanh khoảng đó. `election_epoch`/`quorum_age` có thể đổi do election bình thường; tiêu chí là quorum hội tụ rồi ổn định, không yêu cầu epoch bất biến.

**PASS khi:**

1. Có sự kiện election quan sát được trong rolling, leader mới và các follower hội tụ; sau đó 3/3 ổn định ít nhất 5 phút, không election loop.
2. Các probe fresh auth và I/O xuyên qua cửa sổ đó không có lỗi cuối cùng/timeout/mismatch. Internal retry/EAGAIN ngắn có thể là cơ chế phục hồi; phải phân biệt với retry loop hoặc lỗi trả về ứng dụng.
3. Khi leader là target, MGR active/standby và OSD heartbeat/report vẫn hoạt động; không unknown-message/assert, Paxos stuck hoặc auth lỗi kéo dài.
4. OSDMap/pool/CRUSH có delta được giải thích. Target có thể dọn stale `pg_temp`/invalid upmap và cho trim tiến; không so nguyên file map rồi coi mọi khác biệt là lỗi, cũng không tự xóa các entry hợp lệ để khớp baseline.
5. Theo dõi dung lượng/log MON sau leader target; không đòi store phải nhỏ ngay lập tức. Nếu base từng bị retained-map/health-store growth, cần evidence xu hướng ổn định/trim phù hợp trước khi đóng finding.

Nếu lần canary follower chưa chuyển leader, đó chưa phải bằng chứng cho các fix AuthMonitor/health-store chạy ở leader target. Tiếp tục đến chặng nâng leader theo MOP; không tuyên bố đã kiểm chứng fix chỉ từ một follower target.

## 9. G7 — sau khi toàn bộ MON target

Giữ probe thêm ít nhất 30 phút kể từ MON cuối rejoin; lưu snapshot cuối cùng bằng các lệnh G0 với prefix `post-`, cùng log trên cả ba host. Khi lấy config cuối, đối chiếu cả bản `ready` lẫn sổ thay đổi.

**Tất cả điều kiện sau phải đạt để chốt phần MON:**

| Nhóm | Kết quả cần ghi |
| --- | --- |
| Runtime | Đúng ba MON 16.2.15, digest đúng, 3/3 quorum ổn định; không còn MON base hay daemon MON lạc ngoài inventory |
| MGR/OSD và role khác | MGR vẫn target và phục vụ; OSD target ban đầu vẫn target, OSD base ban đầu vẫn base; không mất OSD/up/in hoặc có image change ngoài phạm vi |
| Auth/messaging | Client cũ và mới kết nối được; leader target phục vụ; không auth loop, bad/unknown-message hay crash mới chưa giải thích |
| Dữ liệu/dịch vụ | RBD/S3 không lỗi/timeout/mismatch; sample đủ cho các pha; kiểm chứng reopen/re-GET bằng process mới thành công trước cleanup |
| Config/placement | Mọi delta về image pin, mask/effective values, flags/pool/upmap đã được phân loại; không có thay đổi bất ngờ còn mở |
| Host/MON store | Clock/network ổn định, free disk/inode đủ; không chờ upgrade “tự sửa” một store/full disk chưa giải quyết |
| MGR monitoring | Các target giám sát đang dùng vẫn scrape thành công qua parser thật; không chỉ HTTP 200; không có khoảng mù trùng cửa sổ upgrade chưa giải thích |

Báo cáo 07 nêu nguy cơ duplicate `HELP/TYPE` tại MGR 16.2.15. Vì MGR đã nâng xong, đây là bằng chứng cần kế thừa từ gate MGR và kiểm tra còn hoạt động, không phải yêu cầu nâng lại MGR. Nếu scrape đã lỗi từ trước, ghi rõ và giải quyết khả năng quan sát trước khi tuyên bố gate giám sát PASS; không mute alert để che lỗi. Nếu lab không có monitoring stack, ghi N/A cho scrape và dùng đầy đủ observer/CLI/journal làm evidence cho các gate còn lại.

Không yêu cầu `ceph versions` toàn cụm chỉ còn một phiên bản ở chặng này. Warning về mixed phiên bản có thể còn, phải khớp đúng daemon base đã biết. `HEALTH_OK` đơn lẻ không thay các điều kiện trên.

## 10. G8 — restore và cleanup có ownership

### 10.1. Khôi phục cấu hình tạm

Với mỗi mục trong sổ thay đổi:

- Nếu trước đó **có override**, khôi phục đúng giá trị, scope/mask và nguồn trước đó.
- Nếu trước đó **không có override**, chỉ xóa override do lần chạy này tạo; không set “default đoán được” để thay cho việc xóa.
- Bản sửa lỗi cấu hình cần cho target và pin image MON target là thay đổi giữ lại, không rollback trong cleanup.
- Balancer/autoscaler khôi phục đúng active/mode cũ; nếu mode cũ là `warn` thì trả `warn`, không bật tất cả thành `on`.

Ví dụ các lệnh cần tham số từ change record, không chạy đồng loạt:

```bash
c config set "$ORIGINAL_WHO" "$OPTION_NAME" "$ORIGINAL_VALUE"
# Hoặc chỉ khi record ghi option trước đó không tồn tại:
c config rm "$CREATED_WHO" "$OPTION_NAME"
c osd pool set "$POOL_TO_RESTORE" pg_autoscale_mode "$ORIGINAL_AUTOSCALE_MODE"
# Chỉ nếu balancer vốn active và chính lần chạy này đã tắt:
c balancer on
```

Không xóa `mon_mds_skip_sanity` chỉ vì thấy nó trong dump; phải xác minh workflow đã kết thúc và ownership ở G2. Không chạy `config rm` hàng loạt cho sáu key cũ, không xóa toàn bộ PG-upmap, không unset hàng loạt cờ OSD còn do PA1/lần chạy khác quản lý. Không `crash archive-all` để đổi health thành xanh. Không xóa store, keyring, daemon/service MON, image cũ hoặc evidence trong cleanup.

### 10.2. Dừng tải, verify lần cuối rồi xóa fixture chính xác

Trên client, xác nhận RBD/S3 đã dừng theo stop-file và kết quả verify/re-GET cuối G7 đã PASS; không `pkill` theo tên công cụ chung. Giữ observer quorum/auth để theo dõi restore, dừng chúng đúng PID/terminal khi G8 hoàn tất. Cả hai kết quả xác minh dữ liệu phải được lưu trước khi xóa fixture.

```bash
# RBD: xác nhận đúng image vừa tạo, không có watcher/snapshot ngoài probe.
test "$TEST_IMAGE" = "mon-gate-$RUN_ID" || { echo 'STOP: sai fixture'; exit 1; }
rbd --conf "$CLIENT_CONF" --id "$CLIENT_ID" --pool "$RBD_POOL" status "$TEST_IMAGE"
rbd --conf "$CLIENT_CONF" --id "$CLIENT_ID" --pool "$RBD_POOL" snap ls "$TEST_IMAGE"
# Chỉ sau khi đã đọc output và verify PASS:
rbd --conf "$CLIENT_CONF" --id "$CLIENT_ID" --pool "$RBD_POOL" rm "$TEST_IMAGE"

# S3: chỉ nhánh bucket chưa bật versioning, đúng key của lần chạy này.
test "$TEST_KEY" = "mon-gate/$RUN_ID/probe.bin" || { echo 'STOP: sai key'; exit 1; }
s3api delete-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
  > "$CLIENT_EVIDENCE/s3-delete.json"
```

Sau DELETE, kiểm chứng key/image không còn bằng list/info có quyền truy cập phù hợp; AccessDenied/timeouts không phải bằng chứng đã xóa. Không xóa bucket/pool, không dùng wildcard hay `--recursive`. Nếu versioning được dùng theo nhánh riêng, xóa đúng các VersionId/delete-marker do probe tạo theo manifest, giữ mọi phiên bản khác.

Sau restore có thể có hoạt động cân bằng đúng thiết kế quay lại. Theo dõi tối thiểu 5 phút, xác nhận không có lỗi mới, chụp `cleanup-config.json`, `cleanup-health.json`, `cleanup-pools.json`. Phân biệt thay đổi do restore này với thay đổi trong cửa sổ đo nâng MON.

**G8 PASS:** hết probe của lần chạy, dữ liệu verify đã PASS, fixture được xóa hoặc có lý do giữ và owner cụ thể; cấu hình tạm trả đúng baseline; pin/sửa đổi giữ lại có danh sách; evidence được giữ; không có dọn dẹp lan sang tài nguyên của MGR/OSD/PA1 hoặc người dùng.

## 11. Applicability và coverage từ bộ so sánh

| Finding | Chuyển thành gate/test MON | Giới hạn hoặc nhánh riêng |
| --- | --- | --- |
| MON-001, MSG-007 — range blocklist | G2 giữ feature state tương thích, không tạo range trong mixed | Test add/expire/enforce CIDR là change riêng sau audit compatibility, không thử ở MOP này |
| MON-002 — release floor | G0/G2 chụp baseline, không tăng để đánh dấu patch | Audit cả OSD down nếu cần thay floor ở một change khác |
| MON-003 — election/rank/shutdown | G4/G6 serial MON, follower trước, leader sau | Không remove/add MON hoặc đổi rank topology |
| MON-004, MSG-001/002 — auth/reconnect | G3/G5/G6 fresh process + session dài + log | Soak ngắn không bảo đảm bao phủ key rotation; ghi nhận cửa sổ chưa phủ |
| MON-005 — FSMap/MDS | Nếu `fs ls` không rỗng: chụp `fs dump`, `fs status`, client CephFS read/write/reconnect trước/trong/sau MON; kiểm damaged/laggy/standby state | Cần fixture CephFS và tiêu chí riêng trước GO; MDS failover/standby-replay không tự chèn vào lúc MON election. Nếu chưa bổ sung được: HOLD applicability |
| MON-006 — map trim/placement | G2/G5/G6/G7 theo dõi map/PG/store, giải thích delta | Không chủ động PG merge để tạo tình huống |
| MON-007 — stretch | G0 đọc MonMap/OSDMap và spec xác định có stretch/tiebreaker | Nếu có stretch: HOLD MOP ba MON này, cần kế hoạch quorum/site riêng trước chạy |
| MON-008 — pool/autoscaler | G2 đóng băng hoạt động cạnh tranh có điều kiện; G8 restore | Không tạo pool/đổi bulk/pg_num/ratio để test MON |
| MON-009 — MGR/Paxos/health-store | G1 disk, G6 leader target, G7 MGR/trim | Không ép MGR fail trùng lúc nâng MON |
| MON-010 — offline tools | Giữ ngoài rollout; dùng quy trình recovery nếu cần | Không monstore rebuild/repair trong preflight |
| MON-011 — config masks | G2 inventory/expectation, G5/G7 so effective của các cohort OSD | Nếu chưa có reconnect/receipt evidence khi mask có tác động thì HOLD coverage, không tự restart OSD |
| MSG-009 — MMgrUpdate | G0 mọi MGR phục vụ/standby đã target; G6 log unknown message | Không dùng `ms_die_on_bad_msg=false` làm cách né vấn đề |
| CFG-007 — option validation | G2 sửa/bỏ đúng key và đúng consumer | Không gom tuning của OSD/RGW/MDS thành việc bắt buộc cho MON |
| ADM-003 — staggered và image finalization | MOP chọn per-daemon redeploy, G2 giữ image scope rõ ràng | Không trộn với vòng native upgrade đang chạy |
| MGR-005 — scrape parser | G3/G7 kế thừa gate MGR và xem parser/target thật | HTTP 200 không chứng minh Prometheus ingest thành công |

## 12. Mẫu kết quả một lần chạy

Ghi một hàng cho mỗi gate và **mỗi lần G4**, thêm evidence theo thời điểm; không gộp ba MON thành một ô “đã test”.

| Gate/daemon | Bắt đầu–kết thúc UTC | Kết quả | Evidence/file/log | Delta hoặc lỗi quan sát | Quyết định tiếp theo |
| --- | --- | --- | --- | --- | --- |
| G0 | | NOT RUN | | | |
| G1 — từng host | | NOT RUN | | | |
| G2 | | NOT RUN | | | |
| G3 | | NOT RUN | | | |
| G4 — canary | | NOT RUN | | | |
| G5 | | NOT RUN | | | |
| G4 — MON thứ hai | | NOT RUN | | | |
| G4 — MON cuối | | NOT RUN | | | |
| G6 — leader transition | | NOT RUN | | | |
| G7 | | NOT RUN | | | |
| G8 | | NOT RUN | | | |

Chỉ kết luận **“hoàn thành nâng MON”** khi các gate bắt buộc PASS và các nhánh conditional có disposition. Không suy rộng kết quả sang toàn bộ OSD/RGW/MDS/client upgrade hoặc an toàn downgrade.

## 13. Nguồn

Nguồn repo và blob SHA của các báo cáo 04/05/06/08 được ghi tại mục 10 của MOP. Bổ sung:

- [README bộ so sánh](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/README.md): các báo cáo là source analysis, không phải runtime run result.
- [07 — MGR/modules/monitoring](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/07-mgr-modules-monitoring.md), MGR-005.
- [15 — Upgrade validation](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/15-upgrade-validation.md): giới hạn coverage và đối chiếu recipe với evidence thật.
- [Ceph monitor configuration](https://docs.ceph.com/en/pacific/rados/configuration/mon-config-ref/) và [troubleshooting monitors](https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-mon/): quorum, clock và store.
- [Librbd Python](https://docs.ceph.com/en/pacific/rbd/api/librbdpy/) và [librados Python](https://docs.ceph.com/en/pacific/rados/api/python/): API của probe. Script là probe lab soạn cho tài liệu này, chưa được chạy với cluster của bạn.
- [AWS CLI PUT](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html), [GET](https://docs.aws.amazon.com/cli/latest/reference/s3api/get-object.html) và [Prometheus targets API](https://prometheus.io/docs/prometheus/latest/querying/api/#targets): cú pháp công cụ client/giám sát; kiểm phiên bản công cụ đang dùng ở baseline.

Thứ tự ưu tiên khi gặp khác biệt tài liệu: runtime của lab + source đúng tag `v16.2.15`/`v16.2.5` → phân tích có evidence → hướng dẫn web chung. Gate về thời gian và độ trễ là tiêu chí lab đề xuất, không phải đảm bảo từ upstream.
