# Lệnh tham khảo cho cephadm Pacific

[Mục lục](00-README.md) · [Phase 1](03-PHASE-1-TRUOC-NANG-CAP.md) · [Phase 2](04-PHASE-2-CANARY-VA-ROLLOUT.md)

Các lệnh là mẫu để điền vào MOP môi trường thật; **chưa được chạy trên cluster**. Thực hiện các khối riêng tại checkpoint tương ứng, không ghép thành một script chạy thẳng. Dùng CLI đúng môi trường (ví dụ wrapper `cephadm shell`) và kiểm `ceph --help` cho option ở binary thực; có thể cần `sudo` theo quyền đã cấu hình.

Phạm vi điều phối là **PA1 + H0**. File này chỉ ghi lệnh native có ích; hooks/capability/policy H0 phải theo implementation thực, không có lệnh `ceph h0 enable` được giả định sẵn. Public image 16.2.15 không tự có H0-W. Manifest phải tách digest upstream với custom H0 artifact của X và peer cần C/D ở L2/L3.

## 1. Read-only: trước nâng, trước/sau batch và sau nâng

```bash
ceph -s
ceph health detail
ceph versions
ceph quorum_status -f json-pretty
ceph mon dump -f json-pretty
ceph mgr dump -f json-pretty
ceph osd dump -f json-pretty
ceph osd tree -f json-pretty
ceph osd df tree -f json-pretty
ceph osd pool ls detail -f json-pretty
ceph df detail -f json-pretty
ceph pg stat
ceph osd perf -f json-pretty
ceph config dump -f json-pretty
ceph balancer status
ceph osd pool autoscale-status
ceph orch status
ceph orch host ls
ceph orch ps
ceph orch ls --export
ceph orch upgrade status
```

Lưu output kèm timestamp và exit status theo thư mục evidence. Config/specs có thể chứa thông tin nội bộ; lọc trước khi chia sẻ. Không export secret bằng `ceph auth export` hoặc `config-key dump` vào báo cáo.

Tại host của X, đối chiếu device bằng `lsblk`, LVM/mapper và inventory đúng kiểu LVM/raw đang dùng; không chạy `zap`/`prepare` để kiểm inventory. CLI host `ceph --version` không thay version image từng daemon.

## 2. Read-only cho candidate X

Ví dụ X=1 chỉ là cách viết biến, **không chọn osd.1 làm candidate thực tế**:

```bash
X=1
ceph osd find "$X"
ceph osd metadata "$X"
ceph pg ls-by-osd "$X"
ceph pg ls-by-primary "$X"
ceph osd ok-to-stop "$X"
```

Với nhiều OSD, đánh giá **toàn bộ tập cùng lúc** bằng các ID thực, ví dụ `ceph osd ok-to-stop 1 7`. Đây không là đề xuất dừng hai OSD đó. Capture thêm PG dump/OSDMap khi cần xác định đầy đủ tập up và acting; không dựa duy nhất vào một listing bị lọc. `ok-to-stop` phải PASS sát thời điểm stop.

Lấy stored và effective config riêng. Khi CLI hỗ trợ:

```bash
ceph config show osd.1
ceph config get osd.1 osd_op_queue
ceph config get mgr mgr/cephadm/migration_current
```

Một key không đọc được trên base có thể chưa tồn tại; ghi kết quả, không `set` thử cho qua. Config ở argv/env/local file có thể override stored config; xem process/container/spec nếu values lệch.

## 3. Mutation: bootstrap MGR để dùng staggered filters

Tiền điều kiện: G0–G3 PASS, nhiều MGR running, đã xác định active/standby, có recovery/control-state checkpoint. Điền digest và tên từ manifest, không dùng placeholder để chạy. Thử pull/inspect artifact ở từng host trước window. [S03, S12–S13](13-NGUON-VA-DOI-CHIEU.md)

```bash
TARGET_IMAGE='quay.io/ceph/ceph@sha256:<DIGEST_DA_XAC_MINH>'
STANDBY_MGR='mgr.<TEN_STANDBY_TU_ORCH_PS>'
ceph orch daemon redeploy "$STANDBY_MGR" --image "$TARGET_IMAGE"
```

**Dừng kiểm:** standby thật sự chạy target, load module được, đủ điều kiện promote. Lặp theo thứ tự với standby khác nếu có; không cố ý failover ngược về base sau khi target đã migrate state mà chưa có rehearsal.

```bash
ACTIVE_MGR_ID='<active_name_TU_MGR_DUMP_KHONG_CO_TIEN_TO_mgr.>'
ceph mgr fail "$ACTIVE_MGR_ID"
```

**Dừng kiểm G4:** active mới đúng target, migration/control/metrics/consumer đạt. Sau đó hoàn tất MGR bằng engine target:

```bash
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types mgr
ceph orch upgrade status
```

Không gửi filter này tới active MGR 16.2.5. Không tự sửa migration counter. Chỉ chuyển bước khi action đã hoàn tất thực tế, không chỉ scheduled/starting.

## 4. Mutation: MON → crash → OSD

Sau nhóm MGR, MON có thể nâng từng lượt theo filter/limit được target hỗ trợ:

```bash
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types mon --limit 1
```

Kiểm G4, version/quorum và expected/actual selection sau mỗi lượt; tiếp tục MON cho đến hết manifest. Chỉ sau MON đạt mới đến crash:

```bash
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types crash
```

Sau crash đạt, chọn **một** đường OSD sau:

**A. Engine chọn OSD trong scope host:** chỉ dùng nếu xác định được mọi candidate engine có thể chọn đều đã hoàn tất chuẩn bị PA1 và đạt G5/DR_READY. Host chứa nhiều OSD chưa chuẩn bị thì không dùng lệnh này để nâng một X đã chọn.

```bash
OSD_HOST='<HOST_TRONG_MANIFEST>'
ceph orch upgrade start --image "$TARGET_IMAGE" \
  --daemon-types osd --hosts "$OSD_HOST" --limit 1
```

`--limit` là số daemon tối đa của lượt, không phải tham số concurrency và không nhận OSD ID cụ thể. Không dùng A để hứa chỉ nâng X khi host có nhiều candidate.

**B. Redeploy đúng X:** dùng cho PA1 đã chuẩn bị một OSD cụ thể khi engine không bảo đảm chọn đúng X. Chỉ dùng khi các role trước đã đạt, engine không có rollout cạnh tranh, image policy đã chốt và G5/**DR_READY** PASS. X phải còn online trong suốt quá trình chuyển PG sang S/peers; không dừng để chờ backfill sau. Đây là đường điều phối thủ công; phải tự chạy gate vì redeploy không thay toàn bộ orchestration safety.

```bash
ceph osd ok-to-stop "$X"
```

Kiểm exit status và output, các gate khác phải đạt rồi mới thực hiện khối kế tiếp:

```bash
ceph orch daemon redeploy "osd.$X" --image "$TARGET_IMAGE"
```

Sau restart X: G6 cho activation, rồi return PG theo [11](11-PA1-H0-LEVEL-1-2-3.md); mỗi batch qua H0-GR trước H0-GW và workload primary, rồi G7 mới mở rộng. Nếu đường B để lại per-daemon image override thì ghi vào journal và reconcile image policy cuối change để lần redeploy sau không dùng sai image.

## 5. Mutation có điều kiện: flags và automation

Chỉ đặt cờ khi [07](07-BAT-TAT-VA-KHOI-PHUC.md) đã chọn dùng. Ví dụ scope X:

```bash
ceph osd set-group noout "osd.$X"
```

Sau khi X đạt điều kiện và chỉ nếu cờ này do change tạo:

```bash
ceph osd unset-group noout "osd.$X"
```

Autoscaler từng pool: chụp mode cũ, rồi đặt `warn`/`off` theo kế hoạch. Không tự cho mọi pool on ở cuối:

```bash
ceph osd pool set '<POOL_DA_CHON>' pg_autoscale_mode warn
```

Balancer: `ceph balancer off` chỉ khi đã chọn freeze; cuối change `ceph balancer on` chỉ khi baseline là on và đã review remap. Các lệnh này không đóng băng CRUSH khi có weight/map mutation khác.

## 6. Mutation: pause/stop và resume

```bash
ceph orch upgrade pause
ceph orch upgrade status
```

Nếu quyết định hủy rollout hiện tại, dùng `ceph orch upgrade stop`; lệnh này không rollback daemon đã nâng. Nếu đang điều phối manual, phải dừng hàng đợi manual; pause engine không hủy mọi lệnh redeploy riêng đã phát.

Chỉ sau xử lý lỗi, gate PASS lại và đúng scope mới dùng `ceph orch upgrade resume`. Không đặt resume tự động theo đồng hồ khi chưa kiểm signal.

## 7. H0-R: yêu cầu deep-scrub cho PG đã return

Chỉ sau recovery/backfill hội tụ đủ replica và có budget I/O, xác định PG từ manifest rồi yêu cầu deep-scrub mới. Nếu có cờ hoãn scrub, xử lý theo [07](07-BAT-TAT-VA-KHOI-PHUC.md) và hành vi binary thực.

```bash
PG='<PG_DA_RETURN_VA_HOI_TU>'
ceph pg "$PG" query
ceph pg deep-scrub "$PG"
```

Lệnh được nhận **không có nghĩa scrub đã xong**. Lưu mốc request, theo dõi query/status/log và bằng chứng completion sau recovery, đúng PG/participants/epoch; nếu map đổi thì đánh giá lại coverage. Sau đó local-X verify đối chiếu H0-static mới có thể đạt H0-GR. Không dùng `ceph pg repair` thay verify, không dùng GET bình thường để giả lập local reader.

## 8. Thao tác không đưa thành lệnh mặc định

Không có lệnh `zap`, `mark_unfound_lost`, repair, DB/WAL migrate, force-remove, set-release-floor hoặc upmap hàng loạt trong file này. Chúng cần identity/state cụ thể và procedure riêng; thiếu dữ liệu cluster không thể sinh một chuỗi mutation đúng cho mọi môi trường.
