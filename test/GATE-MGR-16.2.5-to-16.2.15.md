# Kiểm soát và nghiệm thu nâng cấp Ceph MGR từ 16.2.5 lên 16.2.15

**Ngày lập:** 02/10/2026  
**Nguồn kết quả:** Lab nâng MGR ngày 30/09/2026; hồ sơ kiểm tra MGR lập ngày 01/10/2026  
**Tài liệu thao tác:** [MOP MGR](../MOP/MOP-MGR-16.2.5-to-16.2.15.md)

## 1. Kết luận của hồ sơ hiện có

Hai MGR của lab đã chạy 16.2.15; có ảnh chuyển active và ảnh cụm còn 265 PG `active+clean`. Tuy nhiên, đầu ra Prometheus của MGR 16.2.15 trong nhật ký lab lặp `HELP`/`TYPE` cho `ceph_pool_objects_repaired`: mỗi loại 11 lần khi cụm có 10 pool; `promtool 2.33.4` trả RC=1, báo `second HELP line`. **MGR-G4.2 KHÔNG ĐẠT.** Ảnh target `UP` và sample mới không làm phép kiểm định dạng này thành đạt.

Hồ sơ còn thiếu RepoDigest đích đối chiếu trên từng host, bằng chứng checkpoint/restore, thời gian HA, log I/O và checksum xuyên cửa sổ, API Dashboard có xác thực, so sánh QoS cùng mức tải và chuỗi quan sát đủ thời lượng. Kết luận của bộ GATE tại ngày lập là **CHƯA NGHIỆM THU TOÀN BỘ**. Kết quả nâng daemon và các quan sát thành công được giữ riêng, để người đọc biết chính xác điều gì đã xảy ra và điều gì chưa được chứng minh.

Ảnh ghi `HEALTH_WARN` vì `mon ceph-master is low on available space` tại mốc cuối. Cảnh báo này cần theo dõi/xử lý theo hạn riêng; ảnh `HEALTH_OK` ở mốc sớm hơn không xóa được trạng thái tại mốc cuối.

## 2. Cách dùng bộ GATE

MOP gọi từng mã **MGR-G0 đến MGR-G8** trước/sau thao tác. Mã `G00`, `G05`, `T04`, `R1` ở [checklist dự án](../comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md) là hệ mã khác; bảng mục 4 liên kết chúng. Khi chạy một change mới, ghi lần, thời gian, người thực hiện, đầu ra thô, mã thoát, đánh giá và người duyệt tại từng chặng.

| Trạng thái | Cách ghi |
| --- | --- |
| PASS | Có bằng chứng đủ phạm vi và đáp ứng tiêu chí đã chốt trước khi thực hiện |
| FAIL | Có bằng chứng vi phạm tiêu chí |
| HOLD | Có một phần bằng chứng nhưng chưa thể kết luận hoặc còn điều kiện cần xử lý |
| NOT RUN | Phép thử được xác nhận chưa thực hiện |
| N/A | Không áp dụng, kèm bằng chứng về topology/dịch vụ |

Trong rollout, FAIL/HOLD ở điều kiện bắt buộc chặn bước tiếp. Với lần lab đã qua, HOLD có nghĩa không thể hồi tố một kiểm tra chưa có log; phép đo thực hiện ngày sau chỉ chứng minh trạng thái tại ngày đó. Ngoại lệ có người phê duyệt không chuyển FAIL thành PASS. N/A chỉ dùng khi inventory chứng minh dịch vụ/nhánh đó vắng mặt.

### 2.1. Ngưỡng phải chốt trước thay đổi

| Chỉ tiêu | Ngưỡng tham chiếu cho lab | Lưu ý |
| --- | --- | --- |
| MGR active/standby | Một active và ít nhất một standby khỏe ở mọi điểm chuyển | Nếu có từ ba MGR, áp dụng topology mở rộng T26A |
| Tiếp quản HA | Không quá 60 giây từ lệnh fail tới active mới available | Đo bằng mốc thời gian; `active since` không phải duration |
| Cửa sổ canary | Ít nhất 30 phút sau khi target active | Dùng log theo thời gian, không suy từ ảnh uptime |
| Sau hoàn tất/HA | Ít nhất 30 phút theo dõi cùng mức tải | Ghi đầu/cuối và các mẫu trong khoảng |
| RGW/RBD | Không lỗi mới, timeout hoặc checksum mismatch | Cần log client và read-back; ảnh `FAILED=0` chỉ là snapshot |
| Scrape freshness | Tuổi mẫu ≤ max(60 giây, 3 × scrape interval thực tế) | Xác nhận đúng job, instance và FSID |
| Rules | Không lỗi evaluation mới; `lastEvaluation` tiếp tục tăng | Lấy ít nhất hai mẫu cách nhau hơn một evaluation interval |
| QoS | Điền p95/p99, IOPS/throughput và mức lệch được chấp nhận trước thử | Không điền ngưỡng sau khi biết kết quả |

Các giá trị thời gian là ngưỡng tham chiếu cho **lab**, không phải SLA Ceph hay số đo lab đã đạt. Nếu change dùng ngưỡng khác, ghi ngưỡng đã duyệt trước canary. Không bỏ mẫu xấu khỏi cửa sổ rồi kết luận bằng đoạn tốt.

## 3. Danh mục GATE và trạng thái hiện có

| Mã | Điểm kiểm soát | Kết quả có trong hồ sơ | Trạng thái toàn gate |
| --- | --- | --- | --- |
| MGR-G0 | FSID, baseline, host, image, checkpoint, applicability | Có một số ảnh cluster/version; thiếu digest từng host và checkpoint | HOLD |
| MGR-G1 | Version/image và vai trò trước/sau mỗi MGR | Ảnh cuối: hai MGR 16.2.15, active/standby; thiếu digest đầy đủ và chuỗi từng bước | HOLD |
| MGR-G2 | Migration, module, cephadm và cấu hình | Ảnh state 2 → 5; thiếu đối chiếu side effect/module/config toàn diện | HOLD |
| MGR-G3 | Quorum, PG, workload và integrity | 265 PG sạch và RGW loadgen FAILED=0 tại mẫu; thiếu log liên tục/checksum | HOLD |
| MGR-G4.1 | Lấy endpoint `/metrics` của active MGR | Nhật ký ghi curl RC=0 và có metric Ceph | PASS tại mẫu |
| MGR-G4.2 | Prometheus exposition/parser | 11 HELP, 11 TYPE; promtool RC=1 | **FAIL** |
| MGR-G4.3 | Scrape target và tuổi sample | Target UP, lastError rỗng, một sample sau HA ~3,439 s | HOLD cho toàn cửa sổ |
| MGR-G4.4 | Rule engine và alert path | API có 13 rule groups, 15 alerts; còn thiếu chuỗi evaluation/delivery | HOLD |
| MGR-G5 | Dashboard, API, TLS và client | Ảnh giao diện có dữ liệu; API có xác thực/TLS chưa có biên bản | HOLD |
| MGR-G6 | HA giữa hai MGR target | Active đổi master → node3, standby hiện diện; thiếu đo ≤60 s | HOLD |
| MGR-G7 | Cửa sổ ổn định, QoS và canary | Chưa có bảng cùng tải p95/p99, log 30 phút | NOT RUN trong hồ sơ |
| MGR-G8 | Hoàn nguyên, image/config, bàn giao | Chưa có bằng chứng freeze/restore và diff cuối | HOLD |

Một gate có kết quả “PASS tại mẫu” chỉ nói về mẫu được nhìn thấy; mục tổng hợp của cả chặng vẫn có thể HOLD. MGR-G4.2 đã FAIL nên kết quả chung chưa được ký nghiệm thu.

## 4. Đối chiếu checklist chung của dự án

Nguồn đối chiếu: [UPGRADE-CHECKLIST(1).md](../comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), Git blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6`.

| Mã checklist | Ý nghĩa trong chặng MGR | GATE tài liệu này |
| --- | --- | --- |
| G00, T00 | Đúng artifact, tag/digest, đường nâng | MGR-G0, MGR-G1 |
| G01 | Health, quorum, PG, daemon và cảnh báo | MGR-G0, MGR-G3, MGR-G7 |
| G05, T04 | Prometheus parser và nguồn quan sát dùng cho stop/go | MGR-G4.1–G4.4 |
| G06, T12–T15A | Module custom, Dashboard, consumer, alerts, autoscaler | MGR-G2, MGR-G4, MGR-G5, MGR-G7 |
| G08, T26/T26A/T26B | Cephadm migration, manifest, host, registry, HA, rollback | MGR-G0, MGR-G1, MGR-G2, MGR-G6, MGR-G8 |
| G04, T20/T20A | Cấu hình hiệu lực và thay đổi default | MGR-G0, MGR-G2, MGR-G8 |
| R1 | Canary MGR/control-state trước MON | MGR-G0–MGR-G7 |

Các nhánh NFS/CephFS, private registry, module tự phát triển, Dashboard client hoặc topology ≥3 MGR chỉ được ghi N/A khi có inventory chứng minh không áp dụng. Probe RGW/RBD ở đây kiểm khả năng dịch vụ tiếp tục hoạt động khi MGR đổi vai; chúng không đóng toàn bộ bộ thử chuyên biệt cho RBD/RGW của checklist chung.

## 5. Quy tắc thu và lưu bằng chứng

Khởi tạo biến theo mục 4 của MOP. Chạy các lệnh dưới đây trên `ceph-master` trong Bash có lệnh `ceph` đúng FSID. Dùng thư mục `EVIDENCE` của MOP; không nhập secret vào log hoặc báo cáo. Các lệnh trong file này là **quy trình cho lần chạy mới**, không phải khẳng định chúng đã chạy trong lab 30/09.

```bash
umask 077
set -o pipefail

capture() {
  local label="$1" output="$2" rc
  shift 2
  "$@" >"$output" 2>"$output.stderr"
  rc=$?
  printf '%s\n' "$rc" >"$output.rc"
  printf '%s\t%s\t%s\t%s\n' \
    "$(date -u +%FT%TZ)" "$label" "$rc" "$output" \
    >>"$EVIDENCE/gates/command-index.tsv"
  return "$rc"
}
```

Mỗi dòng index cho biết timestamp UTC, lệnh logic, mã thoát và vị trí dữ liệu. Lệnh trả lỗi, file trống hoặc JSON không parse được làm gate HOLD/FAIL tùy tiêu chí, kể cả khi file `.rc` được tạo. Không sửa đầu ra thô sau khi thu. Lưu tài liệu có secret ở thư mục riêng quyền hạn chế, không đính kèm bản đầy đủ cho người đọc báo cáo.

## 6. MGR-G0 — Trước khi chạy target lần đầu

### 6.1. Đúng cụm và baseline

**Mục đích:** Tạo cùng một mốc để biết daemon nào sẽ đổi, cụm đang khỏe tới đâu và cảnh báo nào đã tồn tại. MOP dùng chính các file `mgr-dump.json`, `mgr-metadata.json`, `balancer.json` và `pools.json` ở mục này.

```bash
capture fsid "$EVIDENCE/baseline/fsid.txt" ceph fsid
capture ceph-s "$EVIDENCE/baseline/ceph-s.txt" ceph -s
capture health "$EVIDENCE/baseline/health.txt" ceph health detail
capture versions "$EVIDENCE/baseline/versions.json" ceph versions -f json-pretty
capture mgr-dump "$EVIDENCE/baseline/mgr-dump.json" ceph mgr dump -f json-pretty
capture mgr-metadata "$EVIDENCE/baseline/mgr-metadata.json" ceph mgr metadata -f json-pretty
capture orch-ps "$EVIDENCE/baseline/orch-ps.json" ceph orch ps --refresh -f json-pretty
capture orch-hosts "$EVIDENCE/baseline/hosts.json" ceph orch host ls -f json-pretty
capture orch-status "$EVIDENCE/baseline/orch-status.txt" ceph orch status
capture upgrade-status "$EVIDENCE/baseline/upgrade-status.txt" ceph orch upgrade status
capture quorum "$EVIDENCE/baseline/quorum.json" ceph quorum_status -f json-pretty
capture pg "$EVIDENCE/baseline/pg-stat.txt" ceph pg stat
capture crashes "$EVIDENCE/baseline/crash-new.txt" ceph crash ls-new
capture balancer "$EVIDENCE/baseline/balancer.json" ceph balancer status -f json
capture pools "$EVIDENCE/baseline/pools.json" ceph osd pool ls detail -f json
capture autoscale "$EVIDENCE/baseline/autoscale.txt" ceph osd pool autoscale-status
```

Đối chiếu `fsid.txt` với `FSID` đã khai báo; kiểm từng `.rc=0` và các JSON bằng `jq -e .`. Chốt active/standby ngay trước redeploy; ảnh cũ không đủ vì vai trò đã thay đổi giữa các snapshot. Không bắt đầu khi upgrade khác còn chạy/paused, host MGR offline, MGR thiếu standby, PG mất khả dụng, crash mới chưa phân loại hoặc workload đang lỗi. Cảnh báo MON low space cần ghi dung lượng và kế hoạch xử lý trước lần thay đổi mới.

Trên cả hai host MGR, lưu `df -h / /var/lib/ceph`, `df -i / /var/lib/ceph`, dung lượng image/runtime, bộ nhớ khả dụng, OOM/kernel journal và status unit/container. Dòng `tcmalloc: large alloc 1073750016 bytes` trong ghi chú lab chỉ là tín hiệu kiểm thêm; nó không tự xác nhận thiếu RAM.

### 6.2. Checkpoint và image

```bash
capture config "$EVIDENCE/checkpoint/config-before.json" ceph config dump -f json-pretty
capture specs "$EVIDENCE/checkpoint/service-specs.yaml" ceph orch ls --export
capture modules "$EVIDENCE/checkpoint/modules.json" ceph mgr module ls -f json-pretty
capture services "$EVIDENCE/checkpoint/mgr-services.json" ceph mgr services -f json-pretty
capture migration "$EVIDENCE/checkpoint/migration-before.txt" \
  ceph config get mgr mgr/cephadm/migration_current
capture fs-list "$EVIDENCE/checkpoint/fs-list.json" ceph fs ls -f json-pretty
```

Nếu phải lưu config-key, dùng thư mục riêng quyền 0700, file 0600 và kiểm quy trình quản lý secret:

```bash
mkdir -p "$EVIDENCE/checkpoint/private"
chmod 700 "$EVIDENCE/checkpoint/private"
ceph config-key dump >"$EVIDENCE/checkpoint/private/config-key.json"
chmod 600 "$EVIDENCE/checkpoint/private/config-key.json"
```

Ngoài các export, quyết định và ghi ID/phạm vi checkpoint phục hồi nhất quán trước target. Đối chiếu inventory module custom/dependency của image nguồn; services NFS/CephFS; private registry; Dashboard/proxy/API client; đường Prometheus/Alertmanager; autoscale mode từng pool và ảnh hưởng PA1. Trên **mỗi** host MGR, xác minh pull được `TARGET_IMAGE`, RepoDigest khớp và chạy `ceph --version` của image trả 16.2.15. `ceph orch upgrade check --image "$TARGET_IMAGE"` phải thành công nhưng chỉ là kiểm khả năng, không phải lệnh nâng.

```bash
capture upgrade-check "$EVIDENCE/checkpoint/upgrade-check.txt" \
  ceph orch upgrade check --image "$TARGET_IMAGE"
```

**Điều kiện đạt:** FSID đúng, một active và standby khỏe, host đủ tài nguyên, image được pin và đối chiếu trên từng host, đường phục hồi phù hợp đã được quyết định, không có workload/cảnh báo blocker chưa xử lý. Ảnh lab cho biết hai MGR 16.2.5 và migration=2 ở mốc cũ, nhưng chưa chứng minh đủ digest đích/checkpoint; **MGR-G0 hiện HOLD**.

```bash
# MINH CHỨNG TG01 — Nguồn và baseline lab
# Mop MGR-legacy.docx ảnh 01: metadata + hai daemon MGR 16.2.5.
# Mop MGR-legacy.docx ảnh 05 hoặc MOP_MGR_16.2.5_to_16.2.15.docx ảnh 02:
# migration_current=2.
# Một ảnh ceph -s khác cho node3 active, trong khi sơ đồ ghi master active;
# hai ảnh không được ghép thành cùng một thời điểm.
```

## 7. MGR-G1 — Version, image và vai trò MGR

**Thời điểm:** Ngay trước standby redeploy; sau khi standby target chạy; sau chuyển active; sau filtered phase. Lặp lại từ dữ liệu mới ở từng mốc, không ghi đè file mốc trước.

```bash
export PHASE='pre'  # đổi thành standby, canary hoặc post ở mốc tương ứng
export GATE_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
export GATE_RUN="$EVIDENCE/gates/$PHASE-$GATE_RUN_ID"
mkdir -p "$GATE_RUN"
capture mgr-dump "$GATE_RUN/mgr-dump.json" ceph mgr dump -f json-pretty
capture mgr-meta "$GATE_RUN/mgr-metadata.json" ceph mgr metadata -f json-pretty
capture mgr-ps "$GATE_RUN/mgr-ps.json" \
  ceph orch ps --daemon-type mgr --refresh -f json-pretty
capture versions "$GATE_RUN/versions.json" ceph versions -f json-pretty
capture upgrade "$GATE_RUN/upgrade-status.txt" ceph orch upgrade status
```

**Trước redeploy:** ID active vẫn là ID MOP chọn, standby có đúng daemon canary. **Sau redeploy:** canary thực sự `running` 16.2.15, image khớp digest chốt, active cũ còn phục vụ và không restart loop. Nếu target tự thành active, ghi mốc và chuyển sang nhánh kiểm sau promotion; không fail MGR khác theo kịch bản cũ. **Sau promotion:** active thực tế là target, standby còn/đăng ký lại; kiểm `deployed_by` khi build công bố. **Sau rollout:** cả hai MGR 16.2.15, một active/standby và không có upgrade paused/lỗi chưa giải quyết. `in_progress=false` riêng lẻ không đủ.

**Bằng chứng lab:** Ảnh đầu ghi hai MGR 16.2.5, ảnh cuối ghi hai MGR 16.2.15 cùng image ID rút gọn. Kết quả **nâng phiên bản** có ảnh hỗ trợ; điều kiện **digest trên hai host và timeline từng bước** chưa đủ nên MGR-G1 tổng hợp **HOLD**.

```bash
# MINH CHỨNG TG02 — MGR sau nâng
# MOP_MGR_16.2.5_to_16.2.15.docx ảnh 04 hoặc Mop MGR-legacy.docx ảnh 09.
# 30/09/2026 17:15:23: master active, node3 standby; cả hai 16.2.15;
# image ID f15b41add2c0, upgrade in_progress=false.
```

## 8. MGR-G2 — Migration, cephadm, module và cấu hình

**Mục đích:** Chứng minh MGR target thực hiện chức năng quản trị, migration hội tụ và các phụ thuộc không bị đổi ngoài ý muốn. Một con số `migration_current=5` là mốc cần thiết nhưng không thay thế hoạt động của module.

```bash
capture migration "$GATE_RUN/migration.txt" \
  ceph config get mgr mgr/cephadm/migration_current
capture modules "$GATE_RUN/modules.json" ceph mgr module ls -f json-pretty
capture services "$GATE_RUN/services.json" ceph mgr services -f json-pretty
capture orch-status "$GATE_RUN/orch-status.txt" ceph orch status
capture hosts "$GATE_RUN/hosts.json" ceph orch host ls -f json-pretty
capture specs "$GATE_RUN/specs.yaml" ceph orch ls --export
capture daemons "$GATE_RUN/daemons.json" ceph orch ps --refresh -f json-pretty
capture config "$GATE_RUN/config.json" ceph config dump -f json-pretty
capture health "$GATE_RUN/health.txt" ceph health detail
capture crashes "$GATE_RUN/crashes.txt" ceph crash ls-new
```

Đối chiếu với checkpoint: `migration_current` từ `2` tới `5`, cephadm trả lời, host/spec/action không treo, module đang dùng phản hồi chức năng thật, không có MODULE_ERROR hay restart/failover loop. Nếu có NFS, kiểm export, grace và spec; nếu có private registry, kiểm credential/pull theo host; nếu image nguồn có module custom, kiểm import, dependency và callback `NOTIFY_TYPES`. Không ghi các nhánh này N/A theo suy đoán.

Sau filtered phase, diff `config-before.json` với `config.json` cho `global/container_image`, override theo daemon/type, `mgr/cephadm/container_image_base` và `mon_mds_skip_sanity`. So image/version daemon ngoài MGR với baseline; một daemon monitoring có thể được redeploy dù version không đổi. Không gửi redeploy ngoài phạm vi trước khi biết image config cuối.

**Bằng chứng lab:** Ảnh cho migration `2` trước nâng và `5` sau khi target active. Chưa đủ log/module/config side effects để đóng gate; **MGR-G2 HOLD**.

```bash
# MINH CHỨNG TG03 — Migration
# MOP_MGR_16.2.5_to_16.2.15.docx ảnh 02 và 03.
# Hai giá trị 2 và 5 là snapshot, không tự chứng minh migration side effects.
```

## 9. MGR-G3 — Quorum, PG, RGW/RBD và toàn vẹn

**Thời điểm:** Baseline, canary standby, active target, sau rollout và xuyên HA. Cùng một mức tải mới cho phép so trước/sau.

```bash
capture ceph-s "$GATE_RUN/ceph-s.txt" ceph -s
capture health "$GATE_RUN/health-detail.txt" ceph health detail
capture quorum "$GATE_RUN/quorum.json" ceph quorum_status -f json-pretty
capture osd "$GATE_RUN/osd-stat.txt" ceph osd stat
capture pg "$GATE_RUN/pg-stat.txt" ceph pg stat
capture crashes "$GATE_RUN/crash-new.txt" ceph crash ls-new
```

Giữ load generator RGW và RBD của lab chạy trên **bucket/image thử riêng** từ trước canary đến sau HA. Lưu cấu hình workload, client version, tốc độ, request/error/timeout theo từng khoảng, log đọc lại và manifest SHA-256 phía client. RGW gồm PUT/GET/HEAD/LIST/DELETE với GET lại dữ liệu đã ghi; RBD gồm ghi/flush/đọc và so pattern/checksum. Không ghi vào image hoặc bucket dữ liệu cần giữ. Một workload chỉ RGW không chứng minh RBD.

**Đạt khi:** quorum/OSD không giảm, không phát sinh PG inactive/degraded/unfound, crash hoặc lỗi dữ liệu do thay đổi; workload không có lỗi mới và read-back đúng. Latency/QoS đánh giá thêm tại MGR-G7.

**Bằng chứng lab:** ảnh cuối có 265 PG active+clean, năm OSD up/in. Ảnh loadgen cho thấy RGW `RUNNING`, `FAILED=0` tại thời điểm chụp; có PUT/GET/HEAD/LIST/UPDATE/DELETE. Chưa có log liên tục, checksum/read-back và chứng cứ RBD tương ứng. **MGR-G3 HOLD**. Cảnh báo MON low space vẫn mở dù PG sạch.

```bash
# MINH CHỨNG TG04 — Workload và cluster snapshot
# TEST_MGR_After_Upgrade_16.2.15.docx ảnh 04: RGW loadgen RUNNING, FAILED=0.
# Ảnh 05: 265 PG active+clean, 5 OSD up/in, cảnh báo MON low space.
# Không dùng ảnh này để xác nhận integrity hoặc QoS cả cửa sổ.
```

## 10. MGR-G4 — Prometheus và cảnh báo

### 10.1. MGR-G4.1 — Đúng endpoint và có dữ liệu

Lấy URL của Prometheus exporter từ `ceph mgr services` sau **mỗi** lần đổi active. Không ghép địa chỉ messenger của MGR với cổng HTTP. `PROM_URL` bên dưới là Prometheus server của lab `http://10.20.20.11:9095`, khác endpoint `/metrics` của MGR.

```bash
export PROM_URL='http://10.20.20.11:9095'
capture mgr-services "$GATE_RUN/mgr-services.json" \
  ceph mgr services -f json
export PROM_BASE="$(jq -er '.prometheus | select(type=="string" and length>0)' \
  "$GATE_RUN/mgr-services.json")"
export METRICS_URL="$(printf '%s' "$PROM_BASE" | sed 's:/*$::')/metrics"
curl --fail --location --silent --show-error --max-time 20 \
  --dump-header "$GATE_RUN/metrics-headers.txt" \
  "$METRICS_URL" -o "$GATE_RUN/mgr-metrics.txt"
printf '%s\n' "$?" > "$GATE_RUN/metrics-curl.rc"
```

PASS nếu RC=0, body khác rỗng và có metric Ceph cần dùng. Nhật ký lab ghi curl RC=0 và có `ceph_*`: **PASS tại mẫu**. Mẫu này được lấy khi metadata MGR đã là 16.2.15; tên thư mục `g4-before` trong hồ sơ cũ không biến nó thành baseline 16.2.5.

### 10.2. MGR-G4.2 — Định dạng exposition và parser

Chạy `promtool check metrics` của stack thực sẽ dùng; ghi phiên bản tool, stderr và RC. Nếu Prometheus ở container, chọn đúng instance dựa vào host/name/config; không lấy container đầu tiên khi nhiều instance.

```bash
sudo docker ps --format '{{.ID}}  {{.Names}}' | grep prometheus
export PROM_CID='<ID-Prometheus-da-xac-nhan>'
sudo docker exec "$PROM_CID" promtool --version \
  >"$GATE_RUN/promtool-version.txt" 2>&1
sudo docker exec -i "$PROM_CID" promtool check metrics \
  <"$GATE_RUN/mgr-metrics.txt" \
  >"$GATE_RUN/promtool.txt" 2>&1
printf '%s\n' "$?" >"$GATE_RUN/promtool.rc"
grep -c '^# HELP ceph_pool_objects_repaired ' \
  "$GATE_RUN/mgr-metrics.txt"
grep -c '^# TYPE ceph_pool_objects_repaired ' \
  "$GATE_RUN/mgr-metrics.txt"
```

PASS khi parser chấp nhận toàn body; nếu family này được xuất, mỗi tên metric chỉ có một dòng HELP và một dòng TYPE. [Định dạng Prometheus](https://prometheus.io/docs/instrumenting/exposition_formats/) quy định metadata của mỗi metric name là duy nhất.

**Kết quả lab theo nhật ký chữ trong hai hồ sơ TEST:** cụm có 10 pool, `HELP=11`, `TYPE=11`, `promtool 2.33.4` trả RC=1 với lỗi `second HELP line for metric name "ceph_pool_objects_repaired"`. Bộ ảnh nhúng không có ảnh riêng đủ rõ cho chính dòng promtool; cần kèm file đầu ra thô khi nộp nghiệm thu. Kết quả đã ghi là **MGR-G4.2 FAIL**.

Đối chiếu [mã Prometheus module ở tag v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/prometheus/module.py) cho thấy một Metric tĩnh và các Metric riêng theo pool có thể cùng tên xuất `pool_objects_repaired`. Mỗi object tự sinh HELP/TYPE khi format; với 10 pool, mô hình này giải thích 11 cặp. Đây là giải thích phù hợp giữa source và runtime; không kết luận image Quay bị build sai chỉ từ hiện tượng đó.

### 10.3. MGR-G4.3 — Scrape, ingest và freshness

```bash
curl -fsS --max-time 20 "$PROM_URL/api/v1/targets" \
  >"$GATE_RUN/targets.json"
jq '.data.activeTargets[] |
  select(.scrapeUrl | contains(":9283")) |
  {scrapeUrl, health, lastError, lastScrape}' \
  "$GATE_RUN/targets.json"

curl -fsSG --max-time 20 "$PROM_URL/api/v1/query" \
  --data-urlencode 'query=time() - timestamp(ceph_health_status)' \
  >"$GATE_RUN/freshness-1.json"
```

Lặp query vào `freshness-2.json` sau hơn một scrape interval thực tế. Đọc `status=success`, result không rỗng, labels/instance thuộc đúng cụm/job và tuổi mẫu nằm trong ngưỡng mục 2. Target `UP` của standby có thể do redirect; không suy ra có hai active. Một target khác vẫn UP cũng không chứng minh MGR đang kiểm có dữ liệu.

**Bằng chứng lab sau HA:** các target cổng 9283 `UP`, `lastError` rỗng trong ảnh; query có sample timestamp `1790826257.247` và mốc đánh giá `1790826260.686`, tuổi khoảng **3,439 giây**. Hai mốc là **03:44:17 và 03:44:20 UTC ngày 01/10/2026** (10:44 giờ Việt Nam). Đây là freshness tại một mẫu, chưa chứng minh không có khoảng mất scrape xuyên failover. **MGR-G4.3 HOLD cho toàn cửa sổ.**

```bash
# MINH CHỨNG TG05 — Sau HA
# TEST_MGR_After_Upgrade_16.2.15.docx ảnh 06: timestamp sample/query.
# Ảnh 12: hai target cổng 9283 UP, lastError rỗng.
# Ảnh 12 là target snapshot, không phải biên bản kiểm parser.
```

### 10.4. MGR-G4.4 — Rule, alert và thông báo

```bash
curl -fsS --max-time 20 "$PROM_URL/api/v1/rules" \
  >"$GATE_RUN/rules-1.json"
curl -fsS --max-time 20 "$PROM_URL/api/v1/alerts" \
  >"$GATE_RUN/alerts.json"
jq '{status, groups: (.data.groups | length)}' \
  "$GATE_RUN/rules-1.json"
jq '[.data.groups[].rules[] | select(.health != "ok") |
  {name, health, lastError}]' "$GATE_RUN/rules-1.json"
```

Lấy `rules-2.json` sau hơn một evaluation interval; so `lastEvaluation`, `evaluationTime` và lỗi mới. Đối chiếu runtime rule checksum, mapping alertname, Alertmanager route/inhibition/silence và bằng chứng thông báo tới đích nếu delivery nằm trong phạm vi. `/api/v1/alerts` chỉ nói trạng thái ở rule engine, không chứng minh người nhận đã nhận thông báo.

Nhật ký lab ghi API success, **13 rule groups, 15 alerts**, và có một ảnh lọc rule health khác `ok` trả danh sách rỗng sau HA. Ảnh `TEST_MGR_After_Upgrade_16.2.15.docx` số 07 có chú thích “sau HA” nhưng thực tế là file `evidence-g4/rules.json` trước HA; ảnh sau HA tương ứng nằm trong `MGR TEST-legacy.docx`, ảnh 12. Chưa có hai mốc evaluation và bằng chứng delivery; **MGR-G4.4 HOLD**. Alert `CephNodeDiskspaceWarning` và `CephMonDiskspaceLow` gắn với vấn đề dung lượng phải được phân loại riêng.

```bash
# MINH CHỨNG TG06 — Rules/alerts
# TEST_MGR_After_Upgrade_16.2.15.docx ảnh 07: rules snapshot trước HA.
# MGR TEST-legacy.docx ảnh 12: rule health sau HA.
# Không dùng số 15 alerts làm ngưỡng cố định; đọc nội dung từng alert.
```

## 11. MGR-G5 — Dashboard, API và TLS

Lấy URL Dashboard từ `ceph mgr services` sau mỗi lần chuyển active; so health, host, MON, OSD và PG trên giao diện với CLI tại cùng thời điểm. Với tài khoản được cấp, thực hiện một GET API đọc chỉ với method, URL path, HTTP status và body đã loại token; giữ log đăng nhập và kiểm lại sau failover. Xác minh TLS của cả đường người dùng → proxy và proxy → Dashboard nếu có proxy/VIP. Nếu client phụ thuộc TLS 1.2, đánh giá khả năng tương thích với mặc định minimum TLS 1.3 của Dashboard target trước khi đóng GATE.

```bash
capture dashboard-services "$GATE_RUN/dashboard-services.json" \
  ceph mgr services -f json
jq -r '.dashboard' "$GATE_RUN/dashboard-services.json"
# Dùng endpoint GET có xác thực đã được phê duyệt cho Dashboard hiện tại.
# Lưu HTTP status/body đã loại token vào GATE_RUN; không ghi password/token.
```

Ảnh lab hiển thị Dashboard với 3 host, 3 MON, 5 OSD, 265 PG và `HEALTH_WARN` phù hợp CLI. Chưa có biên bản API có xác thực, các trang dịch vụ sau HA hoặc kết quả TLS/client tương ứng. **MGR-G5 HOLD.** Chứng chỉ tự ký của lab, nếu được chấp nhận khi mở giao diện, không tự chứng minh kiểm tra TLS đạt.

```bash
# MINH CHỨNG TG07 — Dashboard
# TEST_MGR_After_Upgrade_16.2.15.docx ảnh 09.
# Ảnh chứng minh giao diện có dữ liệu tại một mốc, chưa chứng minh API/TLS.
```

## 12. MGR-G6 — HA giữa hai MGR đã lên target

Thực hiện sau khi MGR-G1 xác nhận **cả hai** MGR đang 16.2.15 và standby khỏe. Giữ workload cùng phép đo monitoring đang chạy. Lần failover này kiểm HA giữa hai target, khác lần promote canary ở MOP. Không chạy lệnh fail lần hai khi kết quả đầu chưa rõ.

```bash
export PHASE='ha'
export GATE_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
export GATE_RUN="$EVIDENCE/gates/$PHASE-$GATE_RUN_ID"
mkdir -p "$GATE_RUN"
capture ha-before "$GATE_RUN/before.json" ceph mgr dump -f json
export ACTIVE_BEFORE="$(jq -er '.active_name' "$GATE_RUN/before.json")"
export EXPECTED_ACTIVE="$(jq -er \
  'if (.standbys | length) == 1 then .standbys[0].name
   else error("Can chon ro standby") end' "$GATE_RUN/before.json")"

date -u +%FT%TZ >"$GATE_RUN/t0-utc.txt"
date +%s >"$GATE_RUN/t0-epoch.txt"
ceph mgr fail "$ACTIVE_BEFORE" \
  >"$GATE_RUN/fail.stdout" 2>"$GATE_RUN/fail.stderr"
printf '%s\n' "$?" >"$GATE_RUN/fail.rc"
```

Chỉ poll khi `fail.rc=0`. Trong tối đa 60 giây, lấy `mgr dump` mỗi khoảng 2 giây, lưu mọi mẫu cùng mã thoát và ghi mốc đầu tiên có `active_name=$EXPECTED_ACTIVE` và `available=true`. Sau đó đo riêng thời gian endpoint trở lại, standby cũ đăng ký lại và đối chiếu MGR-G2–MGR-G5. Nếu quá 60 giây hoặc active khác dự kiến, giữ quan sát/điều tra, không fail tiếp.

```bash
export T0="$(cat "$GATE_RUN/t0-epoch.txt")"
while [ $(( $(date +%s) - T0 )) -le 60 ]; do
  now="$(date +%s)"
  timeout 10s ceph mgr dump -f json >"$GATE_RUN/mgr-$now.json" \
    2>"$GATE_RUN/mgr-$now.stderr"
  rc=$?
  printf '%s\n' "$rc" >"$GATE_RUN/mgr-$now.rc"
  if [ "$rc" -eq 0 ] && jq -e --arg id "$EXPECTED_ACTIVE" \
    '.active_name == $id and .available == true' \
    "$GATE_RUN/mgr-$now.json" >/dev/null; then
    printf '%s\n' "$(( $(date +%s) - T0 ))" \
      >"$GATE_RUN/takeover-seconds.txt"
    break
  fi
  sleep 2
done
capture ha-after "$GATE_RUN/after.json" ceph mgr dump -f json-pretty
```

**Bằng chứng lab:** ảnh ghi lần fail active `ceph-master.ezhuly` và sau đó `ceph-node3.eniabu` active, `ceph-master.ezhuly` standby; 265 PG sạch, I/O xuất hiện tại mẫu. Dòng `active since 54s` là tuổi active lúc chụp, **không phải** thời gian takeover. Không có cặp t0/t1 đồng bộ hoặc log workload toàn khoảng; **MGR-G6 HOLD**, dù hành vi đổi active đã được thấy.

```bash
# MINH CHỨNG TG08 — HA
# TEST_MGR_After_Upgrade_16.2.15.docx ảnh 10: lệnh fail và BEFORE/AFTER.
# Ảnh 11: node3 active, master standby, PG sạch và I/O tại thời điểm chụp.
```

## 13. MGR-G7 — Canary, ổn định và QoS

Chia log thành các cửa sổ **baseline**, **standby target**, **canary target active**, **HA** và **sau rollout**. Ghi timestamp UTC đầu/cuối, image/active ở từng cửa sổ, cấu hình load generator và số client. Canary và sau rollout mỗi khoảng tối thiểu 30 phút theo ngưỡng lab mục 2. Sau khi hoàn tất cần duy trì cùng bộ dữ liệu, cỡ I/O, tốc độ và công cụ đo để so p95/p99, IOPS/throughput.

| Chỉ số cần điền từ log gốc | Baseline | Canary/HA | Sau ổn định |
| --- | --- | --- | --- |
| Thời gian và cấu hình tải | … | … | … |
| Request/I/O; lỗi, timeout | … | … | … |
| Read-back và checksum mismatch | … | … | … |
| Latency p95/p99 | … | … | … |
| IOPS/throughput | … | … | … |
| CPU/RAM/restart MGR | … | … | … |
| Scrape gap lớn nhất | … | … | … |
| Quyết định theo ngưỡng đã duyệt | … | … | … |

Đạt khi cửa sổ đủ thời gian, không active flap, crash/module error mới, mất mẫu kéo dài, lỗi I/O hoặc sai dữ liệu, và QoS trong ngưỡng chốt trước. Hồ sơ Word có ảnh workload/PG tại mẫu nhưng chưa có bảng thời gian hoặc phân vị cùng tải. **MGR-G7 NOT RUN trong hồ sơ nghiệm thu hiện tại**; số liệu tương lai phải ghi thời điểm mới, không gán hồi tố cho cửa sổ nâng 30/09.

## 14. MGR-G8 — Hoàn nguyên và bàn giao

Đối chiếu `freeze-pools.tsv` với autoscale mode thực tế từng pool. Nếu balancer đã được tắt trong change, xác nhận baseline `active=true` **và** PA1 cho phép bật lại trước khi thực hiện; nếu baseline đã off thì giữ off. Lưu output sau từng hành động, đối chiếu health/PG/OSD sau khi bật lại vì autoscaler có thể tạo PG action mới.

Diff config DB, service specs, image/digest và `deployed_by` từng MGR, monitoring daemons, `global/container_image`, per-type/per-daemon overrides và `mon_mds_skip_sanity`. Mọi thay đổi ngoài manifest phải có nguyên nhân và người nhận xử lý. Kiểm upgrade status terminal, active/standby ổn định, các GATE còn mở và cảnh báo MON low space. Không xóa crash hoặc cảnh báo để làm bảng kết quả đẹp hơn.

**Hồ sơ lab:** ảnh cuối có hai MGR đúng version và upgrade status không còn chạy. Chưa có bằng chứng freeze/restore, diff config, checksum và nghiệm thu đầy đủ; **MGR-G8 HOLD**.

```bash
# MINH CHỨNG TG09 — Bàn giao trạng thái
# MOP_MGR_16.2.5_to_16.2.15.docx ảnh 04 (MGR/upgrade/HEALTH_WARN),
# ảnh 05 (loadgen FAILED=0 tại một mẫu).
# Bổ sung file trạng thái sau hoàn nguyên nếu chạy lại change tương tự.
```

## 15. Vấn đề mở và quyết định nghiệm thu

| Mã | Hiện trạng | Điều kiện đóng |
| --- | --- | --- |
| MGR-005 | Exposition lặp HELP/TYPE; parser RC=1 | Bản sửa/image có nguồn gốc; chạy lại G4.1–G4.4 và HA, parser chấp nhận toàn body |
| ENV-001 | MON `ceph-master` low available space ở ảnh cuối | Số liệu dung lượng, xử lý nguyên nhân và health/alert sau xử lý hoặc ngoại lệ có hạn |
| EVD-001 | Thiếu t0/t1 HA, log client/đọc lại/checksum và QoS | Bổ sung log xuyên cửa sổ, phép đo HA và integrity; chốt ngưỡng trước thử |
| EVD-002 | Thiếu digest đích trên từng host, module/API/TLS | Đối chiếu G0/G1/G2/G5 bằng bằng chứng truy vết được |
| EVD-003 | Thiếu checkpoint/freeze/restore/config diff và log filtered phase | Có manifest, lệnh/log gốc và trạng thái sau bàn giao |

**Kết luận:** Chưa nghiệm thu toàn bộ chặng MGR. Hai daemon đã được nâng lên 16.2.15, nhưng G4.2 FAIL và các mục HOLD/NOT RUN nêu trên chưa được đóng. Nếu tiếp tục các chặng lab khi MGR-005 còn mở, biên bản phải ghi phạm vi chấp nhận, phiên bản parser/Prometheus đã kiểm, nguồn telemetry thay thế, người quyết định và hạn xử lý; trạng thái phép thử lỗi vẫn giữ FAIL.

Theo điều kiện chuyển bước của MOP áp dụng cho lần triển khai mới, MGR-G4.2 đang FAIL sẽ chặn mở rộng từ canary sang MGR còn lại. Hồ sơ lab đã có ảnh hai MGR ở target, nhưng chưa có quyết định ngoại lệ và chuỗi log đủ để xác nhận checkpoint này đã được phê duyệt ở thời điểm thực hiện.

| Trường ký nhận | Nội dung điền từ hồ sơ thực tế |
| --- | --- |
| RUN_ID, thư mục evidence | … |
| Giờ bắt đầu/kết thúc, múi giờ | … |
| Image nguồn/đích và digest từng host | … |
| Gate PASS/FAIL/HOLD/NOT RUN/N/A | … |
| Ngoại lệ, người nhận và hạn | … |
| Người thực hiện, rà soát, duyệt | … |

## 16. Nguồn

1. `TEST_MGR_After_Upgrade_16.2.15.docx` — phương án kiểm và 12 ảnh; `MGR TEST-legacy.docx` — nhật ký diễn giải và 14 ảnh. Chú thích ảnh mới số 07 không phản ánh đúng mốc sau HA, đã sửa dẫn chiếu tại MGR-G4.4.
2. [MOP MGR](../MOP/MOP-MGR-16.2.5-to-16.2.15.md), `MOP_MGR_16.2.5_to_16.2.15.docx` và `Mop MGR-legacy.docx` — phương án và mốc thực hiện.
3. [Checklist dự án](../comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), [MGR/monitoring diff](../comparison/pacific-16.2.5-to-16.2.15/07-mgr-modules-monitoring.md), [cephadm diff](../comparison/pacific-16.2.5-to-16.2.15/08-cephadm-orchestrator.md).
4. [Ceph Pacific — Upgrading Ceph](https://docs.ceph.com/en/pacific/cephadm/upgrade/), [Prometheus exposition formats](https://prometheus.io/docs/instrumenting/exposition_formats/) và [Prometheus module trong Ceph v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/prometheus/module.py).
