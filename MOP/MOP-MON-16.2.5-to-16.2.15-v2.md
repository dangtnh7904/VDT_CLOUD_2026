# MOP lab — nâng MON từ Ceph 16.2.5 lên 16.2.15

Phiên bản tài liệu: 2.0 · ngày 01/10/2026. Tài liệu đi cùng: [GATE-MON-16.2.5-to-16.2.15-v2.md](./GATE-MON-16.2.5-to-16.2.15-v2.md).

**Nguồn kiểm soát của bản sửa:** đúng file [UPGRADE-CHECKLIST(1).md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6`, cùng các báo cáo comparison. Các mã `G00–G16`, `T00–T38`, `R2` trong file đó được giữ trong bảng đối chiếu của GATE mục 11; `MG0–MG8` là checkpoint riêng để thực hiện MOP MON, không phải đổi tên gate gốc.

Bản 2 bổ sung đối chiếu gate/test gốc, kiểm chứng dữ liệu có từ trước nâng, bằng chứng phục hồi MON, phạm vi test CephX rotation, retained maps/store và phương án giám sát độc lập. Những phút/giây nêu trong MOP là đề xuất lab cần chốt trước chạy theo checklist §1.5. Checklist còn mô tả PA2/H0 cũ; các phần đó không được đưa vào bước MON này, phù hợp quyết định hiện tại bỏ PA2 và chưa triển khai H0.

## 1. Điểm bắt đầu và kết quả cần đạt

Theo trạng thái bạn xác nhận, **MGR và một OSD đã nâng xong**. MOP này tiếp nối tại bước MON của hop Pacific `16.2.5 → 16.2.15`. MG0 xác nhận lại phiên bản và danh tính thực tế; không suy ra phiên bản toàn cụm từ `ceph -v` trên máy quản trị.

Phạm vi chuẩn của tài liệu là **ba MON trên ba host, quorum thông thường, không stretch**. Nếu inventory khác, dừng tại MG0 để điều chỉnh thứ tự và điều kiện quorum. Tên host, MON ID, OSD đã nâng và image digest được lấy từ cụm, không điền theo tên đoán trước.

Kết quả cần đạt: ba MON chạy đúng artifact `16.2.15`, quorum đủ 3/3; CephX, client I/O, MGR và các OSD đang ở hai patch level tiếp tục hoạt động. Phiên bản các daemon ngoài MON giữ nguyên so với đầu cửa sổ này. Hoàn thành MON chưa có nghĩa là hoàn thành toàn bộ hop Pacific.

Đây là phương án để chạy lab. Chưa có output của cụm trong phiên làm việc này, nên các gate ban đầu đều là **NOT RUN**, chưa phải kết luận GO.

## 2. Cách nâng đã chọn

**Rolling, chia từng daemon; canary một follower trước, follower còn lại sau, ưu tiên leader cuối.** Mỗi lần dùng:

```bash
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE"
```

Lệnh được dùng có chủ đích để giới hạn thay đổi image vào đúng một MON. Với cephadm `16.2.15`, `redeploy --image` lưu `container_image` ở scope daemon và lên lịch redeploy. Vì đây không phải vòng `orch upgrade`, người vận hành phải tự chạy `mon ok-to-stop`, theo dõi quorum và áp dụng gate trước daemon kế tiếp. Thông báo “Scheduled” chỉ xác nhận nhận yêu cầu, chưa chứng minh daemon đã chạy bản mới.

MGR mới đã hỗ trợ staggered qua `orch upgrade start --daemon-types mon --hosts ... --limit 1`. Tuy nhiên, trong source `v16.2.15`, đường này còn xử lý redeploy MGR/monitoring và khi đi đến finalization có thể đặt `global container_image`, xóa image override theo loại daemon. Nó cũng set/remove `mon_mds_skip_sanity`. Do cụm hiện còn OSD mixed-version và mục tiêu lab là riêng MON, MOP chọn cách chỉ định từng daemon ở trên. **Không chạy thêm một vòng `orch upgrade start` song song với MOP.** [S6–S7]

Thứ tự cụ thể:

| Chặng | Thao tác | Gate cho phép đi tiếp |
| --- | --- | --- |
| 0 | Xác nhận baseline, host, config và chạy tải thử ổn định | MG0–MG3 |
| 1 | Nâng một MON đang là follower | MG4 cho daemon đó, sau đó MG5 canary |
| 2 | Đọc lại vai trò; nâng MON cũ còn là follower | MG4; theo dõi MG6 nếu xảy ra đổi leader |
| 3 | Nâng MON cũ cuối cùng, thường là leader ban đầu | MG4 và MG6 |
| 4 | Soak khi toàn bộ MON đã ở target, đối chiếu tác động | MG7 |
| 5 | Dừng tải thử, hoàn nguyên thay đổi tạm và dọn dữ liệu thử | MG8 |

Vai trò leader có thể đổi trong khi làm. Đọc lại `quorum_status` trước mỗi chặng; ưu tiên follower còn ở bản cũ, không ép election chỉ để giữ thứ tự tên host ban đầu. Nếu leader đổi tự nhiên, ghi lại daemon/version của leader mới.

## 3. Chuẩn bị phiên thao tác

### 3.1. Xác định artifact và thông tin thật

Trên máy quản trị, dùng cách gọi `ceph` đang hoạt động của lab để lấy:

```bash
ceph fsid
ceph orch ps --daemon-type mgr --refresh --format json-pretty
ceph orch ps --daemon-type mon --refresh --format json-pretty
ceph versions --format json-pretty
ceph quorum_status --format json-pretty
ceph orch upgrade status --format json-pretty
```

Chọn **cùng image đã kiểm chứng cho MGR 16.2.15**, pin bằng `repository@sha256:...`. Nếu output orchestrator chưa có digest, trên host đang chạy MGR target dùng container runtime đọc `RepoDigests` của image thực tế. Docker image ID, container ID và repo digest là ba giá trị khác nhau; không ghép image ID thành repo digest.

Ví dụ đọc bằng Docker trên chính host đó, sau khi xác định đúng container MGR:

```bash
sudo docker ps --format '{{.ID}} {{.Names}} {{.Image}}'
# Điền CID của đúng MGR target từ output trên.
MGR_CID='DIEN_CID_MGR_TARGET'
MGR_IMAGE_ID=$(sudo docker inspect --format '{{.Image}}' "$MGR_CID")
sudo docker image inspect --format '{{json .RepoDigests}}' "$MGR_IMAGE_ID"
```

Dùng Podman tương ứng nếu host dùng Podman. Không đổi container runtime cho lần nâng MON này.

### 3.2. Biến dùng trong cả MOP và GATE

Chạy các block quản trị ở **Bash trên máy có cephadm**, quyền gọi Ceph admin, `jq`, Python 3 và GNU `timeout`. Các lệnh workload trong GATE chạy trên client lab riêng. Điền hai biến đầu rồi chạy block; giá trị mẫu chưa điền sẽ bị từ chối.

```bash
export FSID='DIEN_FSID_THUC_TE'
export TARGET_IMAGE='DIEN_REPOSITORY@sha256:DIGEST_CUA_MGR_16_2_15'
[[ "$FSID" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo 'STOP: FSID chưa đúng'; exit 1; }
[[ "$TARGET_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || { echo 'STOP: cần repo digest'; exit 1; }

export RUN_ID="mon-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
export EVIDENCE="$PWD/evidence-$RUN_ID"
export CLI_IMAGE="$TARGET_IMAGE"
umask 077
mkdir -p "$EVIDENCE"
set -o pipefail

# Giữ cùng image CLI trong toàn bộ phép đo; mỗi lệnh có timeout.
# JSON nằm ở stdout; log cephadm ở stderr, không gộp 2>&1 vào file JSON.
c() {
  sudo timeout --kill-after=5s 30s cephadm --image "$CLI_IMAGE" shell \
    --fsid "$FSID" --mount "$EVIDENCE:/evidence" -- ceph "$@"
}

c fsid
c versions --format json-pretty
printf '%s\n' "$FSID" > "$EVIDENCE/fsid.txt"
printf '%s\n' "$TARGET_IMAGE" > "$EVIDENCE/target-image.txt"
printf '%s\n' "$RUN_ID" > "$EVIDENCE/run-id.txt"
date -u +%FT%TZ > "$EVIDENCE/start-utc.txt"
```

Nếu `c fsid` không đúng FSID đã khai báo hoặc wrapper không hoạt động, sửa cách truy cập trước MG0. Không tăng timeout trong lúc có lỗi để biến lỗi thành PASS. Các file config/evidence có thể chứa thông tin nội bộ; lưu trong thư mục hạn chế quyền, không đưa nguyên bản vào Git.

Các terminal quản trị khác dùng cùng `FSID`, `TARGET_IMAGE`, `CLI_IMAGE`, `EVIDENCE` và hàm `c`; không tạo RUN_ID mới. Biến client được khai báo riêng trong GATE.

## 4. Những gì có thể phải sửa trước khi nâng

**Không có yêu cầu đổi hàng loạt tham số chỉ vì nâng patch MON.** Dùng MG1–MG2 quyết định từng thay đổi có điều kiện, ghi scope, giá trị cũ, giá trị mới và cách khôi phục.

| Phát hiện thực tế | Xử lý trước MON đầu tiên | Khi nào hoàn nguyên/xóa? |
| --- | --- | --- |
| Clock skew, filesystem MON thiếu dung lượng/inode, host offline hoặc MON đang sync/elect liên tục | Sửa nguyên nhân host/time/network/disk, chạy lại MG1 | Giữ bản sửa đúng; không nâng ngưỡng cảnh báo để che lỗi |
| `public_network` không đủ để cephadm redeploy MON, hoặc spec/address không khớp MonMap | Xác nhận CIDR và cấu hình triển khai đúng với địa chỉ hiện có; nếu cần, đặt tại scope `mon` | Đây là sửa cấu hình triển khai, không tự xóa sau nâng |
| Override `log_max_recent=0` thực sự áp dụng lên MON | Đổi giá trị phù hợp, tối thiểu 1, đúng scope MON/daemon; kiểm tra effective config | Giữ giá trị hợp lệ ở target; lưu baseline cho đường recovery |
| `ms_async_max_op_threads` còn nằm trong cấu hình áp dụng cho MON | Xác minh nguồn DB/local/spec và consumer; bỏ override chỉ của MON khi đã xác định không còn dùng ở target | Không đổi nó thành `ms_async_reap_threshold`; không xóa global nếu daemon cũ còn cần |
| Config mask theo host/CRUSH location/device class | Tính trước OSD nào sẽ nhận giá trị nào; so effective config theo MG2/MG5 | Không xóa mask hàng loạt. Mask sai phải được sửa như một thay đổi có tên và bằng chứng |
| Balancer/autoscaler đang tạo thay đổi placement/PG | Dừng hoạt động cạnh tranh có chủ đích, chờ PG ổn định rồi lấy baseline MG3 | Khôi phục đúng trạng thái cũ tại MG8, kể cả khi trạng thái cũ là `off`/`warn` |
| `mon_mds_skip_sanity` còn sót từ vòng trước | Xác định ownership và xem có workflow CephFS/upgrade đang sử dụng không | MOP dùng redeploy không cần set biến này. Không xóa giá trị cũ chưa rõ nguồn |

Trước khi bỏ key cũ, phải có snapshot, mapping cấu hình phục hồi và rehearsal tương ứng. Nếu chọn failback base thì thử binary base với cấu hình failback trên môi trường cô lập; nếu chọn forward-only thì chứng minh cách phục hồi ở target. Checklist §4.1 không cho xóa stale key trước khi rehearsal hoàn tất. Tên key “đã bị bỏ ở target” tự nó chưa đủ để duyệt xóa.

Các lệnh sửa dưới đây chỉ dùng khi đúng finding đã được xác nhận và điều kiện phục hồi ở trên đã đạt, **không phải block phải chạy hết**:

```bash
# Ví dụ: chỉ MON này có override 0 không hợp lệ.
c config set "mon.$MON_ID" log_max_recent 1

# Ví dụ: public_network scope mon đang thiếu và CIDR đã đối chiếu spec + MonMap.
# MON_PUBLIC_NETWORK phải là CIDR thật, có thể là danh sách CIDR theo cấu hình lab.
c config set mon public_network "$MON_PUBLIC_NETWORK"

# Ví dụ: key bị bỏ chỉ tồn tại ở scope mon này, không phải scope global dùng chung.
c config rm "mon.$MON_ID" ms_async_max_op_threads
```

Nếu cần đóng băng placement, lưu `balancer status`, `osd pool ls detail` trước khi đổi; chỉ tắt balancer nếu đang bật, chỉ đổi `pg_autoscale_mode` cho pool đang tự điều chỉnh. Không sửa `pg_num`, không xóa upmap để “làm sạch” lab. Cách ghi và khôi phục ở MG2/MG8.

Giữ nguyên `require_osd_release`/`min_mon_release` trong MOP patch này. Không bật range/CIDR blocklist, không đổi election strategy, MonMap, auth method, keyring, `mon_clock_drift_allowed`, `noout`, `norecover`, `nobackfill`, hoặc `mon_mds_skip_sanity` như bước chuẩn bị mặc định. Những mục đó không phải điều kiện bắt buộc của nâng binary MON. [S2–S5]

## 5. Chặng 0 — chốt baseline và thứ tự

1. Thực hiện MG0–MG2 trong file GATE, lập applicability và hồ sơ phục hồi theo mục 11. Hoàn thành sửa có điều kiện rồi mới lấy baseline cuối để so sánh.
2. Lưu bảng ba MON: ID, host, IP/addrvec, role hiện tại, running version, image digest. Ghi ID/version của OSD đã nâng và tất cả OSD còn lại.
3. Xác nhận không có vòng upgrade đang chạy hoặc paused, không có action redeploy còn treo từ lần trước. Nếu còn, xử lý vòng đó trước; `upgrade stop` không tự hoàn nguyên daemon/config.
4. Tạo bộ dữ liệu cố định theo GATE mục 5.0, xác minh trước nâng và giữ riêng khỏi workload đang ghi. Bắt đầu observer quorum, test fresh-client auth, RBD và RGW theo MG3. Lấy tối thiểu 10 phút baseline ổn định.
5. Chọn một follower làm canary; điền `MON_ID` và `MON_HOST` đúng inventory. Ghi lựa chọn vào nhật ký.

```bash
c quorum_status --format json-pretty | tee "$EVIDENCE/quorum-before-canary.json"
c orch ps --daemon-type mon --refresh --format json-pretty \
  | tee "$EVIDENCE/mon-before-canary.json"

export MON_ID='DIEN_ID_FOLLOWER_CANARY_KHONG_CO_TIEN_TO_mon.'
export MON_HOST='DIEN_HOST_CUA_MON_NAY'
printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$MON_ID" "$MON_HOST" \
  >> "$EVIDENCE/rollout-order.tsv"
```

MG0–MG3 phải PASS. Warning đã biết chỉ được giữ nếu có mã, nguyên nhân, tác động và lý do chấp nhận; các blocker quorum/auth/disk/time/data không được đưa vào danh sách ngoại lệ để đi tiếp.

Theo G05/T04 gốc, nếu Prometheus parse lỗi nhưng đã có telemetry độc lập đủ signal, được kiểm chứng và ghi rõ owner/guardrail, có thể dùng đường thay thế cho quyết định MON. Test Prometheus vẫn phải ghi FAIL, không chuyển thành PASS/N/A. Nếu thiếu cả hai đường quan sát thì HOLD.

## 6. Chặng 1 — nâng follower canary

### 6.1. Kiểm tra ngay trước thao tác

Đối chiếu snapshot dưới đây với điều kiện MG4: vẫn đủ 3/3, daemon chọn nâng còn ở `16.2.5`, hai MON khác khỏe, không có thao tác khác đang chạy. Chạy `ok-to-stop` bằng **MON ID không có tiền tố `mon.`**.

```bash
c quorum_status --format json-pretty \
  | tee "$EVIDENCE/$MON_ID.before-quorum.json"
c mon ok-to-stop "$MON_ID" \
  > "$EVIDENCE/$MON_ID.ok-to-stop.txt" 2> "$EVIDENCE/$MON_ID.ok-to-stop.err"
```

Nếu lệnh cuối trả khác 0, **không chạy redeploy**. Kết quả `ok-to-stop` chỉ có giá trị tại thời điểm kiểm tra; nếu bị gián đoạn hoặc trạng thái thay đổi, chạy lại trước thao tác.

### 6.2. Redeploy đúng một daemon

```bash
date -u +%FT%TZ | tee "$EVIDENCE/$MON_ID.redeploy-start.txt"
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE" \
  | tee "$EVIDENCE/$MON_ID.redeploy-request.txt"
```

Giữ nguyên tải và observer MG3. Không chạy lệnh nâng MON thứ hai ở terminal khác. Ghi lúc daemon bắt đầu dừng, lúc chạy target và lúc quay lại quorum từ journal/observer; thời gian xếp hàng redeploy không được đánh đồng với thời gian mất MON.

### 6.3. Xác nhận canary và giữ cửa sổ quan sát

```bash
c orch ps --daemon-type mon --refresh --format json-pretty \
  | tee "$EVIDENCE/$MON_ID.after-orch.json"
c tell "mon.$MON_ID" version \
  | tee "$EVIDENCE/$MON_ID.running-version.txt"
c tell "mon.$MON_ID" mon_status \
  | tee "$EVIDENCE/$MON_ID.mon-status.json"
c quorum_status --format json-pretty \
  | tee "$EVIDENCE/$MON_ID.after-quorum.json"
c health detail | tee "$EVIDENCE/$MON_ID.health.txt"
```

Chỉ coi canary xong khi MG4 PASS, sau đó MG5 PASS qua ít nhất 15 phút soak kể từ lúc quorum trở lại 3/3. Đọc lại corpus cố định của mục 5.0, kiểm tra auth mới, I/O đang chạy, effective config của OSD và các thay đổi placement/log trong cửa sổ này. Chỉ nhìn “MON running” hoặc `HEALTH_OK` là chưa đủ.

MG5 phân biệt smoke auth với T11 rotation. Nếu chưa có sự kiện rotation và bằng chứng commit/publish quanh đổi leader, ghi T11 là NOT RUN/PARTIAL và giữ yêu cầu rehearsal ở GATE mục 11; không dùng 15 phút soak thay bằng chứng này. Có thể tiếp tục phạm vi lab disposable đã khóa để thu evidence, nhưng chưa đóng R2 hoặc xin GO canary production dựa vào smoke đó.

## 7. Chặng 2–3 — mở rộng sang hai MON còn lại

Sau MG5, đọc lại vai trò và versions. Chọn MON **chưa nâng và đang follower** tiếp theo. Điền lại `MON_ID`, `MON_HOST`, ghi vào `rollout-order.tsv`, rồi thực hiện nguyên mục 6.1–6.3 cho daemon đó. Sau MG4 PASS và ít nhất 5 phút quorum 3/3 ổn định, mới xét MON cuối.

Đối với MON cuối, đặc biệt nếu nó đang là leader:

1. Chạy lại MG4 trước thao tác; giữ tải client và observer hoạt động.
2. Redeploy đúng daemon đó theo mục 6.2.
3. Kiểm tra MG4 và MG6: election, leader mới, Paxos/auth, MGR active/standby, OSD reconnect/effective config, dịch vụ client.
4. Xác nhận ba MON đều là `16.2.15` bằng runtime version và digest, không chỉ bằng desired config.

Tại sự kiện leader transition, áp dụng T10/T11 ở GATE mục 11. Không hạ MGR đã nâng để tạo tổ hợp MON-target/MGR-base; nhánh tổ hợp đó được đánh giá N/A cho run này khi inventory chứng minh mọi MGR đều target và không có đường failback base trong cửa sổ.

Nếu leader đã đổi trong chặng trước, dùng chính sự kiện đó cho MG6 và xác định phiên bản leader. Cần có quan sát khi **leader target thực sự phục vụ** vì nhiều thay đổi AuthMonitor/OSDMap/health-store phụ thuộc leader. Không tạo thêm failure test nếu lần rolling đã cung cấp đủ bằng chứng.

## 8. Chặng 4–5 — nghiệm thu MON và dọn phần của lần chạy

Sau MON cuối, giữ tải thêm tối thiểu 30 phút, thực hiện MG7. Cuối soak, dừng RBD/S3 bằng stop-file theo GATE, chờ chúng kết thúc vòng đang chạy rồi xác minh reopen/re-GET và corpus cố định tạo trước nâng để chốt MG7. Giữ observer quorum/auth đến hết cleanup. Các MON đều target nhưng OSD vẫn mixed-version là kết quả được dự kiến của MOP này.

MG7 PASS rồi mới:

1. Lưu kết quả xác minh dữ liệu đã ghi bằng client mới và kết quả MG7 trước khi xóa fixture.
2. Khôi phục các thay đổi tạm có trong sổ thay đổi: balancer/autoscaler, debug override hoặc cấu hình phục vụ quan sát, đúng giá trị/scope trước đó.
3. Chạy MG8; xóa đúng image RBD/object S3 thử theo manifest, sau đó dừng observer còn lại đúng PID/terminal. Giữ log, checksum, snapshot config và bảng kết quả.
4. Giữ `container_image` target ở từng `mon.<id>` đã redeploy. Các pin này là trạng thái mong muốn cho MON hiện tại; xóa khi `global` còn trỏ bản cũ có thể làm MON về image cũ ở lần redeploy sau. Việc gom pin về scope `mon` hoặc global được làm có chủ đích khi chốt image policy cho cả hop, không xóa mù ở đây.
5. Bàn giao kết quả: ba MON target; MGR và danh sách OSD giữ baseline; danh sách pin/cấu hình còn giữ; warning/rủi ro còn mở. Dừng tại đây, chưa chạy tiếp crash/OSD/RGW.

Ghi riêng **kết quả rollout lab MON** và **trạng thái đóng R2 theo checklist gốc**. MG7/MG8 đạt không tự đóng test chuyên sâu còn NOT RUN, cũng không đóng G00–G16 cho cả cụm. Aftercare phải có owner, thời gian theo dõi, hạn giữ evidence, expiry của ngoại lệ và điều kiện mở lại incident theo checklist §6.3/§10.

## 9. Khi nào dừng và xử lý thế nào

**HOLD rollout ngay** nếu mất quorum, MON thứ hai lỗi, canary không rejoin trong ngưỡng MG4, auth/I/O timeout hoặc sai dữ liệu, election lặp, MGR mất active kéo dài, hay effective config/placement đổi ngoài dự kiến. Không nâng daemon tiếp theo trong khi điều tra.

| Tình huống | Hành động |
| --- | --- |
| Yêu cầu redeploy chưa được thực hiện | Không gửi lặp. Xem orchestrator events/MGR log, xác định có action đang chờ. `orch upgrade stop` không hủy hàng đợi `daemon redeploy` của cách làm này |
| MON vừa nâng không lên, hai MON còn lại vẫn có quorum | Giữ nguyên hai MON tốt. Thu log của MON lỗi; sửa image pull, bind, permission, dung lượng hoặc cấu hình đúng lỗi rồi thử lại chính MON đó với target |
| MON target đã vào quorum nhưng xuất hiện regression | Dừng mở rộng, giữ evidence và tải phù hợp cho điều tra. Ưu tiên sửa cấu hình hoặc recovery tại target sau khi hiểu lỗi |
| Mất quorum | Dừng mọi thao tác nâng; chuyển quy trình khôi phục quorum riêng dựa trên trạng thái thật. Không remove MON, inject monmap hoặc rebuild store để thử ngẫu nhiên |

Thu chứng cứ quản trị:

```bash
c orch ps --daemon-type mon --refresh --format json-pretty
c health detail
c crash ls-new
c quorum_status --format json-pretty
```

Trên **host của MON lỗi**, dùng FSID/MON_ID thật:

```bash
sudo systemctl status "ceph-${FSID}@mon.${MON_ID}.service" --no-pager
sudo journalctl -u "ceph-${FSID}@mon.${MON_ID}.service" \
  --since 'DIEN_THOI_DIEM_BAT_DAU_UTC' --utc --no-pager
sudo df -hT "/var/lib/ceph/$FSID/mon.$MON_ID"
sudo df -i "/var/lib/ceph/$FSID/mon.$MON_ID"
```

Nếu CLI quorum không trả lời, vẫn dùng systemd/journal và admin socket tại host để xem `mon_status`; không tiếp tục phụ thuộc CLI đang treo. Xác định socket/container hiện hành, không đoán container name theo quy ước dấu chấm/dấu gạch.

**Rollback image không phải rollback dữ liệu MON.** Cùng major Pacific không chứng minh mọi state được target ghi đều có thể hạ binary an toàn. Không đưa một lệnh redeploy lại `16.2.5` thành phương án mặc định, không phục hồi bản copy store đang chạy, không hạ MGR hay OSD đã nâng để đồng nhất phiên bản. Một MON có thể được phục hồi từ quorum còn tốt bằng quy trình recovery riêng; muốn quay về checkpoint của cả lab phải có snapshot nhất quán đã chuẩn bị và đã thử khôi phục. MonMap/config export trong MG0 chỉ là evidence và hỗ trợ recovery, không phải full backup của MON store. [S2–S5]

## 10. Nguồn và giới hạn

- S1 — [plan-tổng.md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/plan-t%E1%BB%95ng.md), blob `df26511f40adc7c031a5706a7051bc1d4a268df2`: thứ tự theo role và chia hop.
- S2 — [04 — MON/OSDMap/CRUSH](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/04-mon-osdmap-crush.md), blob `0851a50b708db3cc65512da05ef2e8a901cf633e`.
- S3 — [05 — Messaging/auth](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/05-messaging-auth-common.md), blob `eb32dd6ddb7e4d2b52dd539c2ce25e917691a552`.
- S4 — [06 — Config/defaults](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/06-config-defaults.md), blob `ae8e7a1c791d29018cf8ff5118d6d114dd5bb8a5`.
- S5 — [08 — Cephadm/orchestrator](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/08-cephadm-orchestrator.md), blob `176b08dc716a577e2af96d427549f79bf9c8fe85`.
- S6 — Upstream [upgrade.py tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/upgrade.py), `_do_upgrade`, `_set_container_images`; [module.py](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/module.py), `_daemon_action_set_image`, `daemon_action`.
- S7 — Upstream [upgrade.rst tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/doc/cephadm/upgrade.rst); [MonCommands.h tại v16.2.5](https://github.com/ceph/ceph/blob/v16.2.5/src/mon/MonCommands.h), `mon ok-to-stop`; [MonService tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/services/cephadmservice.py).
- S8 — [UPGRADE-CHECKLIST(1).md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6`: §1.4–1.5, G00/G01/G03–G08/G13 áp dụng; §3.4/§4; T10–T11/T17A/T20/T21/T26 theo phạm vi; R2; STOP/rollback/evidence. Đây là checklist người dùng chỉ định cho bản 2, không phải bộ `ceph-upgrade-16.2.15/`.

Các báo cáo đầu vào là phân tích source; thời gian soak, ngưỡng timeout và cách tổ chức gate trong hai file này là đề xuất cho lab, cần chốt trước lần chạy, không phải cam kết của Ceph.
