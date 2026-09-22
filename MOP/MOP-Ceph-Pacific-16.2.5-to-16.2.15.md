# MOP nâng cấp Ceph Pacific 16.2.5 → 16.2.15

**Dự án:** PRJ GD2 — RGW/RBD, thử PA1/PA2 và kiểm chứng H0/H1  
**Mã tài liệu:** MOP-CEPH-PACIFIC-001 · **Phiên bản:** 1.0 · **Ngày:** 21/09/2026  
**Đường triển khai:** cephadm, container image cố định bằng digest  
**Đơn vị thao tác:** một OSD mỗi lượt; canary ban đầu 1–2 PG  
**Trạng thái:** MOP phục vụ rehearsal lab và chuẩn bị pilot; **HOLD production** theo hai tài liệu đầu vào. Chưa có kết quả thực thi cụm trong tài liệu này.

MOP chuyển kế hoạch thành trình tự thao tác, điểm kiểm tra và nhánh xử lý. Những trường đánh dấu **ĐIỀN** cần lấy từ cụm và kết quả lab; không dùng giá trị trong ví dụ thay cho inventory. Chỉ đánh dấu PASS khi có thời điểm, người xác nhận và bằng chứng.

**Cách dùng:** chạy phần chuẩn bị và control plane một lần cho mỗi hop. Với mỗi X, chọn **một** nhánh PA1 hoặc PA2, dùng chung bước nâng X và kiểm chứng, rồi đóng lượt trước khi chọn OSD tiếp theo. Khi so sánh hai phương án trong lab, bắt đầu từ các trạng thái nguồn tương đương; không chạy PA1 rồi coi PA2 trên store đã nâng là phép so sánh cùng điều kiện.

## Mục lục

1. [Phạm vi và hồ sơ change](#scope)
2. [Ngưỡng, thời gian và trạng thái an toàn](#budget)
3. [Chuẩn bị và thu thập bằng chứng](#prepare)
4. [Nâng MGR, MON và crash trước OSD](#control)
5. [Chuẩn bị riêng cho OSD X](#osd-prep)
6. [PA1 — Dừng X giữ store, upmap sang spare](#pa1)
7. [PA2 — Drain CRUSH weight, nhận lại PG từng nấc](#pa2)
8. [U10 — Nâng chính xác daemon X](#upgrade-x)
9. [H0/H1, SQLite, canary và cấp quyền](#verify)
10. [STOP, xử lý sự cố và phục hồi](#incident)
11. [Đóng lượt OSD và hoàn tất hop](#closure)
12. [Rehearsal, chọn phương án và pilot](#rehearsal)
13. [Biểu mẫu biên bản và bảng liên kết gate](#records)
14. [Nguồn và giới hạn xác minh](#sources)

<a id="scope"></a>
## 1. Phạm vi và hồ sơ change

### 1.1. Phạm vi áp dụng

| Nội dung | Quy định của MOP |
| --- | --- |
| Hop có checklist hỗ trợ | **16.2.5 → 16.2.15**. Không kế thừa PASS sang 17.2.7 hoặc 18.2.7 |
| Daemon/dịch vụ | Cephadm MGR → MON → crash → OSD, sau đó các dịch vụ đang dùng theo thứ tự engine; dữ liệu tập trung RGW và RBD |
| Pool ban đầu | Replicated; ghi size/min_size thực tế. Mô hình thử là size=3/min_size=2, không tự đổi pool production theo mô hình |
| OSD có cả PG EC | Loại khỏi MVP này, hoặc mở rộng MOP và rehearsal EC trước khi chọn |
| PA1 | Giữ X dừng trước khi thế chỗ xong để thử mở store cũ bằng target; chấp nhận cửa sổ giảm replica có giới hạn |
| PA2 | X chạy trong lúc drain; chỉ dừng khi PG đã rời X và đủ replica; sau nâng tăng **CRUSH weight** có kiểm soát |
| H0/H1 khởi đầu | H-LAB + BATCH_CHECKPOINT theo plan; khả năng đọc đúng X, journal và SQLite phải được triển khai/test trước khi ghi kết quả |
| H-ENFORCE / STRICT_CURRENT | Nhánh phát triển riêng; cần enforcement trong các đường phục vụ liên quan, không có sẵn bằng affinity/upmap |
| Phục hồi | Nguồn payload đã kiểm cùng version hoặc điểm phục hồi độc lập còn tốt. H0 chỉ chứa hash, không thay payload |
| Cụm 100 TB | Không bắt buộc dựng để bắt đầu lab. Quyết định bỏ yêu cầu bản phục hồi độc lập ở production phải được đóng trong G16 |
| Ngoài change này | Zap/recreate OSD, migrate DB/WAL, reshard/repair hàng loạt, đổi pool size/min_size, đổi CRUSH rule, bật tính năng định dạng mới, nâng nhiều OSD đồng thời |

Nếu deployment thực tế là package/manual hoặc orchestrator khác, giữ lại phần gate dữ liệu nhưng phải thay phần lifecycle bằng MOP tương ứng. Không trộn lệnh systemd của package với daemon do cephadm quản lý.

### 1.2. Phiếu thông tin trước khi chạy

| Trường | Giá trị cần ghi |
| --- | --- |
| Change ID / môi trường / FSID thực tế | ĐIỀN |
| Phạm vi phiên | LAB cơ chế / LAB H0 / PILOT một OSD / ROLLOUT hop |
| Người chỉ huy / người thao tác / người kiểm tra | ĐIỀN |
| Owner RGW/RBD, monitoring, verifier; đầu mối incident | ĐIỀN |
| Ngày giờ bắt đầu, múi giờ, hạn kết thúc | ĐIỀN; timestamp bằng chứng dùng UTC |
| Artifact nguồn theo từng cohort | Repo@sha256, Ceph version, commit, vendor/custom delta |
| Artifact đích | Repo@sha256, version 16.2.15, build provenance và kết quả rehearsal |
| Máy quản trị / CLI / cephadm / container runtime | ĐIỀN; xác nhận CLI đang dùng, không suy từ ceph-common trên host |
| X / host / class / root / failure domain | ĐIỀN |
| Peer và spare theo từng PG | ĐIỀN; spare cùng FSID, đúng rule/class/failure domain |
| PA chọn cho lượt này | PA1 hoặc PA2 |
| W0 / R0 / A0 | CRUSH weight / override reweight / primary-affinity ban đầu của X |
| C: PG canary và pool | ĐIỀN 1–2 PG; inventory chứng minh dữ liệu được phép thử |
| Cơ chế H0 / chính sách version | H-LAB hoặc H-ENFORCE; BATCH_CHECKPOINT hoặc STRICT_CURRENT |
| Phạm vi bắt buộc / lấy mẫu | PG, object/version/range, metadata; ghi riêng hai phạm vi |
| Verifier/local-reader/mutation-feed/enforcement | Build, checksum, runbook thao tác thực đã test; chưa có thì ghi NOT_IMPLEMENTED |
| Nguồn payload tốt / thời hạn giữ / RPO-RTO | ĐIỀN; quyết định H/B100 và trạng thái G16 |
| Strategy khi target đã mở store | Forward-fix/rebuild đã diễn tập, hoặc restore nhất quán đã test |
| Evidence root / retention / bảo vệ manifest | ĐIỀN; ngoài X và ngoài phạm vi lỗi đang thử |
| Kết quả cuối | NOT_RUN / PASS LAB / HOLD / GO PILOT / PASS OSD / PASS HOP |

H0 chưa có local-reader hoặc enforcement không ngăn việc học cơ chế native trên dữ liệu lab có thể tạo lại. Tuy nhiên phải ghi đúng **NOT_PROVEN** cho chức năng chưa có; không dùng kết quả native làm PASS cho G15/HG.

### 1.3. Người chịu trách nhiệm

| Vai trò | Trách nhiệm tại điểm quyết định |
| --- | --- |
| Change owner (CO) | Chọn phạm vi, ngưỡng và trạng thái kết thúc; quyết định dừng/resume theo bằng chứng |
| Operator (OP) | Chạy từng bước, lưu output/exit code và journal thay đổi |
| Reviewer (RV) | Đối chiếu FSID, X, image, mapping trước mỗi mutation; xác nhận gate chuyển bước |
| Service owner (SO) | Xác nhận QoS và correctness RGW/RBD, workload và điểm phục hồi ứng dụng |
| Verifier owner (VO) | Manifest, local-read, version binding, dirty queue, nguồn repair và giới hạn coverage |

Lab nhỏ có thể kiêm nhiệm. Khi một người kiêm nhiệm, vẫn ghi riêng kết quả kiểm tra trước/sau; không bỏ bước đối chiếu.

<a id="budget"></a>
## 2. Ngưỡng, thời gian và trạng thái an toàn

### 2.1. Điền ngưỡng trước mutation đầu tiên

Các số sau là **điểm khởi đầu cho lab từ plan**, không phải SLO production. Production phải thay bằng ngưỡng đã thống nhất từ baseline đại diện 24–72 giờ hoặc chu kỳ dài hơn.

| Signal | Ngưỡng lab khởi đầu / giá trị cần điền | Khi vượt |
| --- | --- | --- |
| Dữ liệu mismatch; inconsistent/unfound/incomplete mới | Không chấp nhận trong bài bình thường | STOP ngay, giữ bằng chứng và xử lý dữ liệu |
| p99 theo từng loại I/O | Vượt SLO tuyệt đối đã điền, hoặc >1,20 × baseline trong 2 cửa sổ 1 phút | Dừng mở batch/nấc mới |
| Throughput với cùng offered load | <90% baseline, chưa giải thích được | HOLD mở rộng, điều tra bottleneck |
| Lỗi I/O cuối cùng | Không có lỗi mới trong bài không fault injection | STOP và phân loại; retry/timeout vẫn phải đo riêng |
| Quorum / clock / MON store | Quorum ổn định; các ngưỡng clock/free/trend: ĐIỀN | Không nâng daemon kế tiếp |
| Dung lượng mỗi đích, DB/WAL và filesystem host | Dự báo vẫn dưới guardrail nội bộ, thấp hơn ngưỡng nearfull/backfillfull tương ứng; reserve: ĐIỀN | Không ép remap, không nâng full-ratio để tiếp tục |
| PA1 giảm replica | Tối đa số PG, thời gian và degraded PG-seconds: ĐIỀN | Khôi phục dự phòng theo I02; không nâng X |
| PA2/PA1 canary | Số PG ngoài C có X trong up/acting = 0 | Canary FAIL về phạm vi; ngừng mở rộng |
| Backfill/drain không tiến triển | Cửa sổ không tiến triển và tổng timeout: ĐIỀN từ lab | Chẩn đoán, lập lại kế hoạch từ trạng thái hiện tại |
| H0 batch | Mismatch bắt buộc = 0; remaining mandatory = 0 để CHECKPOINT_READY | Giữ gate; không loại record khó kiểm khỏi mẫu số |
| Head mới chờ hậu kiểm | Max pending bytes / tuổi job / tốc độ tăng backlog: ĐIỀN | Dừng mở rộng, giải quyết backlog |
| Telemetry stale/missing | Max sample age / khoảng mất dữ liệu: ĐIỀN | Không mở bước mới nếu không còn nguồn thay thế đã test |
| Resume | Ví dụ 5 cửa sổ 1 phút ổn định, p99 trong +10% baseline và trong SLO | CO/RV xác nhận nguyên nhân và các gate dữ liệu trước resume |

Đếm PG giảm replica theo thời gian: **degraded PG-seconds = tích phân số PG degraded theo thời gian**. Một OSD dừng có thể làm toàn bộ P_X giảm dự phòng dù mới áp upmap cho vài PG.

### 2.2. Time budget và deadline

| Mã | Nội dung | Phải chốt |
| --- | --- | --- |
| T_CTRL | Redeploy/failover và soak từng MGR/MON/crash | Timeout, soak và thứ tự cụ thể theo rehearsal |
| T_MOVE | Drain hoặc recovery sang spare | Ước lượng byte/tốc độ thực + biên; timeout không tiến triển |
| T_DEGRADED | Cửa sổ PA1 thiếu replica | Bắt đầu khi X dừng, kết thúc khi đủ replica; độc lập T_MOVE |
| T_BOOT | Stop/redeploy/start X | Hạn daemon lên, mount/replay ổn và đúng digest |
| T_SCRUB | Deep-scrub từng PG bắt buộc | Hạn hoàn thành dựa trên kích thước/tải; thời điểm lần scrub mới |
| T_H0 | Kiểm tập bắt buộc / drain backlog | Byte còn thiếu, tốc độ đọc/rehash và tuổi chờ |
| T_CANARY | Soak canary | Lab 30–60 phút sau hội tụ, đủ request và verify; production theo SLO |
| T_RESERVE | Thời gian đưa cụm về trạng thái giữ an toàn | ĐIỀN, không phân bổ hết cửa sổ cho nâng |
| T_AFTERCARE | Giám sát sau lượt/hop | ĐIỀN, gồm ít nhất chu kỳ tải cần đánh giá |

Nếu dùng cửa sổ đêm 3 giờ, đó là **giới hạn của phiên đã được bố trí**, không phải dự đoán toàn bộ drain, trả dữ liệu và hash sẽ xong trong 3 giờ. Chỉ một lượt đọc 15 TB ở 200 MB/s đã khoảng 20,8 giờ; di chuyển ra và về còn có chi phí riêng. Đây là phép tính minh họa, không phải số đo cluster.

Chuẩn bị baseline, scrub, artifact và phần kiểm được phép làm trước cửa sổ. Chỉ bố trí drain ngoài cửa sổ khi tác động placement/QoS đã nằm trong phạm vi change. Trước mỗi bước không dễ đảo, phải còn đủ thời gian cho bước đó và T_RESERVE; nếu không, giữ trạng thái an toàn rồi bàn giao.

### 2.3. Các mốc giữ an toàn

| Mốc | Trạng thái có thể giữ | Điều kiện bắt buộc |
| --- | --- | --- |
| S0 | Chưa thay placement; X còn nguồn A | Health và manifest ổn |
| S1 | PA1: X dừng trên A, PG đang thiếu replica | Chỉ là trạng thái chuyển tiếp có T_DEGRADED; không bàn giao kéo dài như trạng thái an toàn |
| S2 | PG đã ở peer/spare, đủ replica; X không thuộc up/acting | Nguồn tốt còn sẵn, không có remap kẹt; đây là mốc hoãn nâng thuận lợi |
| S3 | X đã mở bằng B, đang cô lập placement | Giữ đủ replica bên ngoài X; coi đã vượt ranh giới downgrade store |
| S4 | X chỉ nhận C hoặc batch đã ghi; phần còn lại ở peer/spare | Dữ liệu, QoS, quyền và hậu kiểm đúng policy; có owner tiếp tục |

Hết thời gian không đồng nghĩa tăng weight về W0 hoặc gỡ mọi cờ cho nhanh. Khả năng phục hồi dữ liệu quan trọng hơn việc đưa các con số cấu hình về baseline ngay lập tức.

<a id="prepare"></a>
## 3. Chuẩn bị và thu thập bằng chứng

### P01 — Chốt runtime, artifact và biến thao tác

**Người làm:** OP/RV. **Điều kiện ra:** đúng FSID, đúng runtime, artifact đủ; G00/G12/G13 theo phase.

Lệnh trong tài liệu dùng Bash ở máy quản trị hoặc cephadm shell đã có quyền đúng cluster. Nếu dùng shell container, bảo đảm thư mục bằng chứng được bind vào nơi lưu bền đã chọn. `ceph --version` là phiên bản CLI, không chứng minh phiên bản daemon.

```bash
# Điền từ phiếu change trước khi chạy. Không dùng ID mẫu.
CHANGE_ID=''
EXPECTED_FSID=''
OSD_ID=''
OSD_HOST=''
TARGET_IMAGE=''          # registry/repository@sha256:<digest đã chốt>
EVIDENCE_ROOT=''         # thư mục được cấp quyền, ngoài X

: "${CHANGE_ID:?Dien CHANGE_ID}"
: "${EXPECTED_FSID:?Dien FSID da xac minh}"
: "${OSD_ID:?Dien OSD_ID}"
: "${OSD_HOST:?Dien OSD_HOST}"
: "${TARGET_IMAGE:?Dien image digest}"
: "${EVIDENCE_ROOT:?Dien EVIDENCE_ROOT}"

[[ "$OSD_ID" =~ ^[0-9]+$ ]] || exit 1
[[ "$TARGET_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || exit 1
[[ "$(ceph fsid)" == "$EXPECTED_FSID" ]] || exit 1

umask 077
set -o pipefail
RUN_DIR="$EVIDENCE_ROOT/$CHANGE_ID/$(date -u +%Y%m%dT%H%M%SZ)-osd.$OSD_ID"
mkdir -p "$RUN_DIR"
ceph --version > "$RUN_DIR/cli-version.txt"
ceph fsid > "$RUN_DIR/fsid.txt"
ceph orch upgrade status > "$RUN_DIR/upgrade-status.before.txt"
ceph orch upgrade check --image "$TARGET_IMAGE"
```

Kiểm tra exit code sau từng lệnh; lỗi thu thập không được bỏ qua để chạy tiếp. `upgrade check` không thay test store, QoS hay restore. Pull/inspect target theo runtime thực trên từng host trong cohort; lưu digest thực, không chỉ tag hoặc tên image. Nếu dùng custom Ceph/H0, giữ riêng commit, patch, build, dependency và kết quả mixed-version.

### P02 — Snapshot trạng thái trước thay đổi

```bash
date -u +%FT%TZ > "$RUN_DIR/baseline-time.txt"
ceph -s > "$RUN_DIR/status.before.txt"
ceph health detail > "$RUN_DIR/health.before.txt"
ceph versions -f json-pretty > "$RUN_DIR/versions.before.json"
ceph quorum_status -f json-pretty > "$RUN_DIR/quorum.before.json"
ceph mon dump -f json-pretty > "$RUN_DIR/mon.before.json"
ceph mgr dump -f json-pretty > "$RUN_DIR/mgr.before.json"
ceph osd dump -f json-pretty > "$RUN_DIR/osd.before.json"
ceph osd tree -f json-pretty > "$RUN_DIR/tree.before.json"
ceph osd df tree -f json-pretty > "$RUN_DIR/df.before.json"
ceph osd crush rule dump -f json-pretty > "$RUN_DIR/rules.before.json"
ceph osd pool ls detail -f json-pretty > "$RUN_DIR/pools.before.json"
ceph pg dump pgs -f json-pretty > "$RUN_DIR/pgs.before.json"
ceph osd getmap -o "$RUN_DIR/osdmap.before"
ceph osd getcrushmap -o "$RUN_DIR/crushmap.before"
ceph config dump -f json-pretty > "$RUN_DIR/config.before.json"
ceph config show "osd.$OSD_ID" > "$RUN_DIR/osd-effective.before.txt"
ceph balancer status > "$RUN_DIR/balancer.before.txt"
ceph osd pool autoscale-status > "$RUN_DIR/autoscale.before.txt"
ceph features -f json-pretty > "$RUN_DIR/features.before.json"
ceph orch ps --format json > "$RUN_DIR/daemons.before.json"
ceph orch ls --export > "$RUN_DIR/specs.before.yaml"
ceph crash ls-new > "$RUN_DIR/crashes.before.txt"
```

Snapshot config/spec dùng quyền hạn chế; tách hoặc che credential trước khi chia sẻ gói review. Không đưa keyring, registry password hay dump toàn bộ config-key vào biên bản thông thường.

Bổ sung inventory host/device/LV/raw/dm-crypt, block/DB/WAL, unit/container, NTP, dung lượng root và MON store; lưu effective config của peer/spare. Kiểm xem có weight sets, pg_temp, full upmap và upmap-items trước phiên. Backup control-plane theo runbook nhất quán đã test; các output trên không phải bản backup đầy đủ MON store hay payload.

### P03 — Lập P_X và bảng mapping

P_X là hợp mọi PG có X trong **up hoặc acting**, ở mọi pool. Dùng PG dump đầy đủ để đối chiếu với `ls-by-osd`.

```bash
ceph pg ls-by-osd "$OSD_ID" -f json-pretty

# Chuẩn hóa hai dạng JSON thường gặp; schema khác phải dừng sửa parser.
jq -e '
  (if (.pg_stats | type) == "array" then .pg_stats
   elif (.pg_map.pg_stats | type) == "array" then .pg_map.pg_stats
   else error("Unknown PG dump schema") end)
  | if length == 0 then error("Empty PG inventory") else . end
  | if all(.[];
      (.up | type) == "array" and
      (.acting | type) == "array" and
      (.pgid | type) == "string")
    then . else error("Missing PG fields") end
' "$RUN_DIR/pgs.before.json" > "$RUN_DIR/pgs.normalized.before.json"

jq --argjson x "$OSD_ID" '
  [.[] | select(
      ((.up | index($x)) != null) or
      ((.acting | index($x)) != null))
   | {pgid, state, up, acting, up_primary, acting_primary, stat_sum}]
' "$RUN_DIR/pgs.normalized.before.json" > "$RUN_DIR/pgs-X.before.json"
```

Lưu danh sách P_X ban đầu để kiểm các PG đã rời X về sau. Khi X đã drain, `pgs-X` rỗng **không** chứng minh các PG cũ đã khỏe. Mỗi mốc lấy PG dump và OSDMap mới, kiểm cả P_X gốc, mọi PG bị remap thêm và toàn bộ PG hiện vào X. Giữ epoch/thời gian của các mẫu; không ghép snapshot cũ thành một trạng thái hiện tại giả định.

| Trường record mapping | Nội dung |
| --- | --- |
| Identity | PG ID, pool ID/name, rule/class/failure domain, epoch |
| Before | up, acting, up_primary, acting_primary; raw/effective mapping đã đối chiếu |
| Ngoại lệ có trước | Toàn bộ entry pg-upmap/pg-upmap-items, pg_temp liên quan |
| Dự kiến | Danh sách cặp đầy đủ, đích hợp lệ, byte và ảnh hưởng ngoài P_X |
| After | Mapping thực qua các epoch, đủ replica, owner và timestamp |
| Hoàn nguyên | Giá trị trước, giá trị phiên đã đặt, lệnh restore có điều kiện |

`pg-upmap-items` đặt **cả danh sách cặp** cho PG; không coi một cặp mới là append. Khi có entry cũ hoặc full upmap, phải lập lại phương án hoàn chỉnh; ví dụ một cặp trong MOP chỉ dành cho PG không có ngoại lệ xung đột.

### P04 — Đóng điều kiện đầu vào

| Điều kiện | Bằng chứng phải có trước khi mở phase tương ứng |
| --- | --- |
| Health | Không lỗi dữ liệu, mount/replay, quorum, clock hay phần cứng chưa giải thích; WARN có disposition |
| PG | Tất cả PG của phạm vi tác động active+clean, đủ replica; không recovery/backfill/remap đang tranh chấp |
| Dung lượng/peer | Đích từng PG hợp lệ, free-after có growth/reserve; CPU/disk/network đủ nhận tải |
| Chọn X | Xếp hạng từ workload đại diện: criticality, PG I/O, headroom peer, primary PG, tổng PG và byte |
| Client | Upmap compatibility đã đáp ứng, gồm client offline có thể quay lại; không nâng client floor tại bước canary chỉ để lệnh chạy |
| Test dữ liệu | H0/checkpoint và payload source đã giữ; workload RGW/RBD dùng dữ liệu được phép |
| Config | Xử lý key/default/applicability theo checklist; scheduler thực đã biết, không tự chuyển WPQ sang mClock |
| Monitoring | Client latency/error và nguồn Ceph/host hoạt động; có đường kiểm độc lập khi MGR metrics lỗi |
| Recovery | G02/G08/G16 rõ; store và control-state có ranh giới forward-only được ghi nhận |
| Time/ownership | Mỗi timeout, người quyết định, trạng thái cờ, entry tạm và cách bàn giao đã điền |

Deep-scrub các PG bắt buộc trước đợt theo ngân sách, từng PG hoặc nhóm nhỏ đã đo:

```bash
: "${PG_ID:?Dien PG da duyet}"
ceph pg deep-scrub "$PG_ID"
ceph pg "$PG_ID" query
rados list-inconsistent-pg "${POOL_NAME:?Dien pool}"
```

Đợi **lần deep-scrub mới hoàn tất**: timestamp/counter đã cập nhật, không còn trạng thái đang scrub, không lỗi mới. Lệnh được tiếp nhận chưa phải PASS. Nếu mismatch, sang I04; không tự repair. Cú pháp dùng [PG deep-scrub API của Pacific](https://docs.ceph.com/en/pacific/api/mon_command_api/#pg-deep-scrub); theo dõi bằng [tài liệu kiểm tra PG](https://docs.ceph.com/en/pacific/rados/operations/monitoring-osd-pg/).

**P04 PASS →** chạy control plane nếu chưa hoàn tất trên target; nếu đã hoàn tất có bằng chứng, sang C01. Thông tin applicability của T00–T29 trong checklist vẫn phải được đóng, không chỉ các mục OSD hiển thị ở đây.

<a id="control"></a>
## 4. Nâng MGR, MON và crash trước OSD

**Người làm:** OP/RV, SO kiểm dịch vụ. **Timeout:** T_CTRL từng daemon/phase. **Khi không đạt:** I01/I05; chưa chạy phase kế tiếp.

### K00 — Khóa phạm vi điều khiển

1. Đối chiếu `ceph orch upgrade status`: không có tác vụ nâng khác đang chạy hoặc bị pause nhưng có thể được người khác resume.
2. Ghi state cephadm, migration, action queue, service spec và phương án phục hồi control-plane **trước target MGR active**. Checklist nêu ranh giới migration state 5; chưa diễn tập failback thì chọn forward-fix, không tự đưa MGR 16.2.5 quản lý lại state mới.
3. Khóa các automation thay topology, PG count và placement theo phạm vi change. Lưu mode từng pool trước khi đổi; không khôi phục tất cả thành `on`.
4. Tắt balancer nếu đang bật; với pool trong phạm vi đang autoscale `on`, chuyển `off` theo danh sách đã duyệt. Mode `warn/off` giữ theo quyết định đã ghi.

```bash
ceph balancer off
# Lặp thủ công cho từng pool đã nằm trong phạm vi freeze, nếu cần:
ceph osd pool set "${POOL_NAME:?Dien pool da duyet}" pg_autoscale_mode off
```

Lệnh trên chỉ chạy khi đã ghi before/after/owner vào journal. Giữ nguyên `pg_num/pgp_num`, rule, class, pool size và client floor trong phiên. Việc tắt balancer không dừng các tác vụ di chuyển đã bắt đầu; chờ chúng hội tụ trước baseline thao tác OSD.

### K01 — Bootstrap MGR từ 16.2.5

16.2.5 chưa có staggered filters của target. Cần nhiều MGR đang hoạt động và nâng standby trước. Cách bootstrap này được Ceph mô tả trong [hướng dẫn staggered upgrade](https://docs.ceph.com/en/reef/cephadm/upgrade/#staggered-upgrade).

```bash
ceph mgr dump -f json-pretty
ceph orch ps --daemon_type mgr --format json

# Điền ID đầy đủ từ inventory; phải là standby tại thời điểm thao tác.
ceph orch daemon redeploy "mgr.${MGR_STANDBY_ID:?Dien standby ID}" \
  --image "$TARGET_IMAGE"
```

Thực hiện tuần tự trên các standby cần nâng. Sau mỗi daemon: đợi container chạy thật, đúng version/digest, standby load/can-run được và không restart loop. Không chuyển active khi chưa có target standby khỏe.

Ngay trước handoff, đọc lại active ID và xác nhận ranh giới control-state:

```bash
ceph mgr dump -f json-pretty
ceph mgr fail "${MGR_ACTIVE_ID:?Dien active ID vua xac minh}"
ceph mgr dump -f json-pretty
ceph orch ps --daemon_type mgr --format json
```

**PASS handoff:** active hiện tại chạy target; module, service URI và cephadm hoạt động. Kiểm Prometheus parser/scrape và golden queries trước, rồi Dashboard/API, autoscaler, custom module và client QoS. Nếu không đạt, giữ OSD/MON chưa nâng và đi I05.

Khi active target đã được xác minh, hoàn tất cohort MGR:

```bash
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types mgr
ceph orch upgrade status
```

Đợi phase terminal, mọi MGR đúng target, rồi soak T_CTRL. Trong staggered upgrade, monitoring daemons có thể được refresh sau MGR; đưa chúng vào manifest tác động và kiểm telemetry sau refresh. Không coi mọi daemon ngoài MGR đổi container đều tự động là bất thường; phải đối chiếu đúng hành vi đã rehearsal.

### K02 — MON từng daemon

Đảm bảo toàn bộ MGR đã hoàn tất trước MON. Chọn MON follower trước trong rehearsal, giữ quorum và NTP ổn định; không dừng thêm MON khi MON trước chưa trở lại quorum.

```bash
ceph quorum_status -f json-pretty
ceph mon dump -f json-pretty
ceph orch ps --daemon_type mon --format json

# Chỉ dùng khi tập MON còn nguồn A trên host này đã xác nhận đúng một daemon.
ceph orch upgrade start --image "$TARGET_IMAGE" \
  --daemon-types mon --hosts "${MON_HOST:?Dien host}" --limit 1
ceph orch upgrade status
ceph quorum_status -f json-pretty
```

**PASS từng MON:** đúng digest/version, đủ quorum trở lại, election/Paxos/auth ổn định, MON store và client I/O trong ngưỡng qua T_CTRL. Nếu tập lọc có hơn một ứng viên, `--limit 1` không chứng minh engine chọn đúng daemon dự kiến; chỉnh manifest trước khi phát lệnh.

Lặp cho các MON còn lại. Không nâng release flag, tạo CIDR range-blocklist hoặc đổi MonMap topology trong canary.

### K03 — Crash cohort, rồi đóng điều kiện OSD

```bash
# Chạy từng host/cohort nhỏ đã ghi trong manifest.
ceph orch upgrade start --image "$TARGET_IMAGE" \
  --daemon-types crash --hosts "${CRASH_HOST:?Dien host}" --limit 1
ceph orch upgrade status
ceph crash ls-new
ceph versions -f json-pretty
ceph orch ps --format json
```

Đợi terminal, kiểm ceph-crash đúng version, quyền truy cập crash directory và backlog; lặp đến khi hoàn tất crash cohort. Thứ tự target trong checklist là **MGR → MON → crash → OSD**, sau đó các role còn lại; không dùng filter bỏ qua role bắt buộc.

**Gate K-PASS:** MGR/MON/crash đủ điều kiện, không upgrade task chạy nền, không mất monitoring, control-state/rollback decision đã lưu. Chụp lại baseline P02/P03 vì state có thể đã đổi sau control-plane transition.

<a id="osd-prep"></a>
## 5. Chuẩn bị riêng cho OSD X

### C01 — Chọn lại X, spare và canary tại thời điểm chạy

**Người làm:** OP/RV/SO/VO. **Gate:** U0/U1, G14 và HG0 theo chế độ.

1. Đối chiếu X với host, class, root và store identity; đọc lại toàn bộ P_X, pool và peer. Các PG trong scope phải active+clean.
2. Lưu **W0/R0/A0 từ cấu hình thực**, không đặt mặc định W0=1. PA2 dùng CRUSH weight; R0 phải dương và được giữ nguyên trừ nhánh incident đã được lập riêng.
3. Chọn spare hợp lệ cho **từng PG**. Với `{X,Y,Z} → {S,Y,Z}`, S chưa thuộc PG, không trùng failure domain không được phép với Y/Z, đủ dung lượng và tài nguyên sau toàn bộ mapping.
4. Spare đã được thêm và ổn định trước baseline. Lab chỉ có 3 host × 1 OSD với size=3 theo host chưa có chỗ thay thế hợp lệ nếu rút một OSD; phải giải quyết topology trước bài drain.
5. Chọn C có tham chiếu dữ liệu, kích thước nhỏ và được phép thử. Muốn test X làm primary bằng khôi phục affinity, ưu tiên PG có raw mapping thích hợp đã mô phỏng. Primary thực vẫn phải kiểm lại.
6. Hoàn tất HG0 và nguồn phục hồi. Nếu chỉ có hash tầng S3/RBD mà chưa có bridge/local-reader, ghi coverage tầng ứng dụng, chưa chứng nhận bản cục bộ X.
7. Xác nhận mọi cờ có trước, balancer/autoscaler và freeze K00 vẫn đúng; topology/map drift phải được reconcile trước thao tác.

```bash
ceph osd find "$OSD_ID"
ceph osd metadata "$OSD_ID" -f json-pretty
ceph osd tree -f json-pretty
ceph osd dump -f json-pretty
ceph osd ok-to-stop "$OSD_ID"
```

`ok-to-stop` được chạy lại **ngay trước lần dừng/restart**; kết quả ở C01 không dùng mãi cho những bước sau. Nó không chứng minh checksum đúng, đạt SLO hay an toàn để xóa OSD.

### C02 — Chuyển primary khỏi X

```bash
ceph osd primary-affinity "$OSD_ID" 0
ceph pg dump pgs -f json-pretty > "$RUN_DIR/pgs.affinity-zero.json"
ceph osd perf
```

Đối chiếu `acting_primary` và `up_primary` của mọi PG; chỉ tiếp tục khi primary đã rời X theo mục tiêu và peer nhận tải vẫn đạt QoS. Đừng chỉ nhìn vị trí đầu tiên trong danh sách.

Affinity bằng 0 không chặn X nhận replication/ACK, replica-read hoặc làm nguồn recovery. Đây là điều phối vai trò; hàng rào H-ENFORCE phải được kiểm riêng ở H01.

**Chọn PA1 → A01. Chọn PA2 → B01.**

<a id="pa1"></a>
## 6. PA1 — Dừng X giữ store, upmap sang spare

### A01 — Chuẩn bị toàn bộ mapping trước khi dừng

**Đầu vào:** C01/C02 đạt; snapshot store/recovery policy rõ. **Timeout:** chưa tiêu T_DEGRADED.

- RV duyệt danh sách X→S cho toàn bộ P_X, lệnh đầy đủ cho PG có ngoại lệ cũ và phương án hoàn nguyên từng entry.
- Dự báo dung lượng/tốc độ từ Y/Z sang S khi X dừng, tính thời gian giảm replica của toàn bộ P_X.
- Kiểm `nobackfill/norecover` và các cờ/scheduler/reservation cản recovery. Cờ của change khác phải được giải quyết với owner; không tự unset.
- Ghi trạng thái `norebalance` và scoped `noout` trước phiên. Nếu không thống nhất quyền quản lý cờ toàn cụm, chưa chạy PA1.

### A02 — Đặt cờ và dừng đúng X trên A

**Đầu vào:** mapping đã sẵn, U1 còn hiệu lực. **Deadline:** bắt đầu T_DEGRADED khi X dừng.

```bash
# Chỉ đặt khi phiên có quyền sở hữu và đã lưu trạng thái ban đầu.
ceph osd set norebalance
ceph osd set-group noout "osd.$OSD_ID"
ceph osd ok-to-stop "$OSD_ID"
```

Chỉ khi lệnh cuối PASS, chạy riêng bước dừng:

```bash
ceph orch daemon stop "osd.$OSD_ID"
ceph orch ps --daemon_type osd --daemon_id "$OSD_ID" --format json
ceph osd tree
date -u +%FT%TZ
```

Xác nhận tiến trình/container đã dừng thật và MON ghi nhận trạng thái. Giữ nguyên block/DB/WAL; nếu bài thử cần checkpoint store, lấy bản nhất quán khi X đã dừng, bao gồm đầy đủ thành phần. Không đưa clone cùng danh tính OSD lên cụm sống.

**Kỳ vọng:** X giữ store tại thời điểm dừng; workload chuyển qua peer, có thể peering/retry/latency spike. Đây là ngoại lệ dừng trước U2 có chủ đích của PA1. Nếu X tự chạy lại hoặc T_DEGRADED vượt ngưỡng, đi I02.

### A03 — Thế chỗ bằng spare và chờ đủ replica

**Người làm:** OP/RV; SO theo dõi QoS. **Timeout:** T_DEGRADED và T_MOVE; hết trước thì xử lý ngay.

Áp danh sách đã duyệt cho toàn bộ P_X. Ví dụ một PG chưa có entry cần bảo tồn:

```bash
ceph osd pg-upmap-items "${PG_ID:?Dien PG}" "$OSD_ID" "${SPARE_ID:?Dien spare}"
ceph pg "$PG_ID" query
ceph osd dump -f json-pretty
```

Kiểm mapping sau từng mutation; thu byte/object, progress, trạng thái degraded/misplaced và tải đích. X đang dừng nên nguồn recovery là replica còn sống theo Ceph. Hành vi `norebalance` với PG degraded là giả thiết đã được plan đối chiếu source, vẫn phải thử đúng image và trạng thái thực tế.

**U2 PASS khi đồng thời:**

1. Toàn bộ P_X và các PG bị ảnh hưởng thêm đủ replica, active+clean, up/acting hội tụ.
2. X không còn trong up/acting trên toàn bộ map, không phải primary phục vụ PG nào.
3. Nguồn S/Y/Z ổn, kiểm dữ liệu bắt buộc ở tầng đã khai báo đạt; không có lỗi mới.
4. Không có remap không được giải thích, QoS và thời gian giảm dự phòng nằm trong budget.

Không đợi vô hạn nếu backfill không tiến. Nếu phải mở `norebalance` mới đi tiếp, kiểm mọi remap đang chờ, ghi **biến thể PA1 đã thay đổi**; bài giữ cờ xuyên suốt không được báo PASS.

**U2 PASS → U10. U10 PASS → A04.** Nếu U2 chưa đạt, không mở store bằng B.

### A04 — Trả C về X

**Đầu vào:** X chạy B ổn; chỉ chuẩn bị quyền nhận dữ liệu theo H01, source tốt còn giữ.

1. Giữ ngoại lệ sang S cho mọi PG ngoài C.
2. Với từng PG trong C, khôi phục entry trước phiên hoặc xóa đúng entry do phiên tạo để effective map đưa PG về X.
3. Không mặc định thêm cặp ngược S→X: `FROM` phải hợp lệ với mapping đang áp dụng.

```bash
# Chỉ khi entry trước phiên KHÔNG tồn tại và toàn bộ entry hiện tại là của phiên:
ceph osd rm-pg-upmap-items "${PG_ID:?Dien canary PG}"
ceph pg "$PG_ID" query
```

Đọc lại **toàn bộ PG dump**: `P_X hiện tại ⊆ C`; không chỉ query hai PG vừa sửa. Đọc mọi remap đang chờ trước khi thả backfill cân bằng:

```bash
# Chỉ gỡ nếu phiên đã đặt và không có owner khác đang phụ thuộc.
ceph osd unset norebalance
```

PG đã đủ replica ở S/Y/Z thường cần mở backfill cân bằng để về X. Cờ này không phải cơ chế chặn mọi I/O; nếu xuất hiện degraded/remap ngoài dự kiến thì chuyển I02/I03.

Đợi C đồng bộ, active+clean và kiểm H02–H05. Sau PASS canary, sang A05.

### A05 — Trả PG theo batch

Lập batch bằng **số PG, byte, tải peer và coverage còn thiếu**, không gỡ mọi upmap cùng lúc. Mỗi batch:

1. Chụp map/epoch; lập danh sách PG thêm vào X và ngân sách.
2. Với H-LAB, hạ lại affinity X về 0 trước khi nhận batch chưa kiểm; đo ảnh hưởng chuyển primary của các PG đã có. Với H-ENFORCE, gate riêng từng PG/version phải hoạt động.
3. Khôi phục từng entry do phiên sở hữu, kiểm cả PG ngoài danh sách.
4. Chờ hội tụ; chạy H02–H05 cho toàn bộ phạm vi mới và quyền định cấp.
5. Chỉ mở batch tiếp khi dữ liệu, QoS, thời gian và nguồn phục hồi đạt.

Ghi local PG/byte còn lại sau start, cleanup và dữ liệu thực sự được tái dùng. Nếu native cleanup xóa PG cũ thì báo kết quả đó; không kết luận chỉ copy delta khi chưa đo.

**Kết thúc PA1:** hoàn tất H06 và E01; chưa chuyển OSD kế tiếp khi journal tạm hoặc coverage bắt buộc chưa được xử lý.

<a id="pa2"></a>
## 7. PA2 — Drain CRUSH weight, nhận lại PG từng nấc

### B01 — Drain khi X còn chạy

**Đầu vào:** C01/C02 đạt, W0/R0/A0 đã lưu. **Timeout:** T_MOVE; X vẫn chạy cho tới U2.

Kiểm không có `norebalance/nobackfill/norecover` cản drain. Nếu phiên trước để cờ, đối chiếu ownership và giải quyết trước khi phát lệnh. Lập dự báo đích toàn cụm: giảm weight X có thể ảnh hưởng thêm PG ngoài P_X và không chỉ đẩy dữ liệu vào một spare.

```bash
ceph osd crush reweight "osd.$OSD_ID" 0
ceph osd tree -f json-pretty
ceph pg stat
ceph osd perf
```

Giữ **override reweight R0** theo baseline. Không dùng `ceph osd reweight X 0` thay lệnh trên trong cùng run; đó là biến thể khác.

Theo dõi up/acting của P_X gốc, mọi remap mới, byte/object, headroom và QoS. Điều tiết recovery theo scheduler/config đã rehearsal; không phát một bộ tuning chung cho Pacific/Quincy/Reef.

**U2 PASS:** không PG còn phục vụ/chuyển dữ liệu phụ thuộc X; các PG rời X và mọi PG bị tác động đã đủ replica, hội tụ; không lỗi dữ liệu mới. Đĩa trống hoặc lệnh weight thành công không thay gate này.

Nếu drain chậm, ngừng kế hoạch nâng tiếp và đi I02. Khôi phục W0 ngay lập tức có thể gây đợt remap ngược, nên phải tính từ trạng thái hiện tại.

**U2 PASS → U10. U10 PASS → B02.**

### B02 — Mô phỏng weight dương cho canary

**Đầu vào:** X chạy B ổn ở CRUSH weight=0, A=0, R0 dương; H01 sẵn sàng theo chế độ. **Gate ra:** có phương án chỉ C vào X và không drift.

```bash
ceph osd getmap -o "$RUN_DIR/osdmap.canary-current"
cp "$RUN_DIR/osdmap.canary-current" "$RUN_DIR/osdmap.canary-preview"
osdmaptool "$RUN_DIR/osdmap.canary-preview" \
  --adjust-crush-weight "$OSD_ID:${W_EPS:?Dien weight da tinh}" \
  --test-map-pgs-dump-all > "$RUN_DIR/canary-placement-preview.txt"
```

Đây là mô phỏng trên file, không nhập map vào cụm. Dùng đúng tool version và kiểm hỗ trợ tùy chọn; xem [osdmaptool Pacific](https://docs.ceph.com/en/pacific/man/8/osdmaptool/).

1. Chọn Wε dương biểu diễn được, không bị làm tròn thành 0.
2. Kiểm toàn bộ PG dự kiến vào X và ảnh hưởng ngoài X, gồm weight sets và ngoại lệ hiện có.
3. Cần upmap C thì xác định FROM và danh sách cặp đầy đủ; không coi một OSD trong acting đương nhiên là FROM hợp lệ.
4. Nếu Wε kéo PG ngoài C vào X, giảm Wε hoặc thiết kế ngoại lệ hợp lệ trước; không đổi định nghĩa C sau sự kiện chỉ để báo đạt.
5. Map online đã thay đổi so với preview thì mô phỏng/reconcile lại.

Weight nhỏ là trọng số phân bố, **không phải quota PG hoặc byte/giây**. Upmap không phải allowlist. Nếu không kiểm soát được đúng 1–2 PG, bài canary này FAIL về phạm vi.

### B03 — Áp Wε và mapping, rồi thả backfill

Chỉ khi cụm khỏe, không có movement đang chạy ngoài kiểm soát, lab có thể dùng `norebalance` trong cửa sổ ngắn để kiểm map trước backfill cân bằng. Ghi owner/TTL; không dùng cờ như một hàng rào nguyên tử.

```bash
# Tùy chọn đã được chọn trong run và có ownership:
ceph osd set norebalance

ceph osd crush reweight "osd.$OSD_ID" "$W_EPS"

# Ví dụ PG chưa có entry xung đột; cần bảo tồn entry cũ nếu có:
ceph osd pg-upmap-items "${CANARY_PG:?Dien canary PG}" \
  "${FROM_OSD:?Dien FROM hop le}" "$OSD_ID"
ceph osd dump -f json-pretty
ceph pg dump pgs -f json-pretty
```

Đọc lại weight hiệu lực và mapping qua các epoch; X chỉ được xuất hiện trong C. Các lệnh weight/upmap không nguyên tử; PG degraded có thể di chuyển dù có `norebalance`. Nếu xuất hiện PG ngoài C, ghi thời điểm/tác động, HOLD và sang I03; không tiếp tục tăng weight để thử.

Khi mapping ổn và không có remap chờ ngoài phạm vi:

```bash
# Chỉ khi phiên sở hữu cờ.
ceph osd unset norebalance
```

Chờ đồng bộ C và chạy H02–H05. Không áp upmap vào X vẫn có effective weight=0 rồi giả định mapping sẽ tồn tại.

### B04 — Tăng weight từng nấc

**Đầu vào:** canary PASS, không lỗi mới, đủ thời gian cho nấc kế và T_RESERVE.

| Trình tự mỗi nấc | Điều kiện bắt buộc |
| --- | --- |
| Đề xuất W_NEXT | Dựa trên PG/byte/headroom và kết quả nấc trước |
| Preview map mới | Liệt kê mọi PG thêm/rời, primary chuyển và ngoại lệ sẽ hết hiệu lực |
| Chuẩn bị quyền | H-LAB hạ affinity trước nhận PG chưa kiểm; H-ENFORCE giữ gate từng PG/version |
| Áp đúng một nấc | Đọc lại giá trị hiệu lực và toàn bộ mapping |
| Chờ hội tụ | PG đủ replica, không inconsistent, QoS trong guardrail |
| Verify/soak | H02–H05 cho phạm vi mới, không kế thừa PASS từ C |
| Quyết định | Giữ nấc / mở nấc mới / STOP, ghi người xác nhận |

```bash
ceph osd crush reweight "osd.$OSD_ID" "${W_NEXT:?Dien weight da duyet}"
ceph osd tree -f json-pretty
ceph pg dump pgs -f json-pretty
```

Có thể khảo sát các mức 0,5% → 1% → 2% → 5% → 10% → … → 100% W0 theo plan, nhưng mỗi nấc phải được tính lại bằng mapping/byte thực. Không chạy lịch tăng tự động theo phút.

**Kết thúc PA2:** chỉ về W0 khi toàn bộ phạm vi nhận mới vượt gate; xử lý entry tạm theo journal, hoàn tất H06/E01. Việc drain không xóa hết metadata BlueStore; cần bài store có lịch sử riêng để đánh giá hop đầy đủ.

<a id="upgrade-x"></a>
## 8. U10 — Nâng chính xác daemon X

**Dùng chung:** sau A03 hoặc B01 đạt U2. **Người làm:** OP/RV/VO. **Timeout:** T_BOOT.  
**Điểm không được tự đảo:** kể từ lần target có thể đã mở/ghi store; mặc định chuyển sang strategy forward-fix/restore đã chọn.

### U10.1 — Kiểm ngay trước redeploy

1. Đúng X/host/device/image; MGR/MON/crash prerequisite đạt K-PASS.
2. Không upgrade engine khác chạy nền; `ceph orch pause` cũng không được đang chặn lifecycle đã dự kiến. Nếu orchestrator đang pause do change khác, giải quyết ownership trước.
3. PA1: X đang dừng, toàn bộ PG ở peer/spare, mapping giữ X ngoài up/acting. PA2: X đã drain ở W=0.
4. Phiên bản target và store-risk đã qua T01 hoặc forward-only/rebuild rehearsal theo G02. Ghi boundary trước khi phát lệnh.
5. H-ENFORCE: hàng rào H01 phải có hiệu lực ngay khi tiến trình lên, không đợi redeploy xong mới bật. H-LAB: chỉ tiếp tục đúng phạm vi lab và ghi NOT_PROVEN cho enforcement.
6. Scoped noout đã có ownership; nếu PA2 chưa đặt, đặt để tránh X tự out làm đổi R0 khi dừng lâu.

```bash
ceph orch upgrade status
ceph osd set-group noout "osd.$OSD_ID"
```

Nếu PA2 và X còn chạy, đánh giá lại ngay trước dừng:

```bash
ceph osd ok-to-stop "$OSD_ID"
```

Chỉ sau PASS của lệnh trên mới phát bước dừng:

```bash
ceph orch daemon stop "osd.$OSD_ID"
```

PA1 đã dừng thì kiểm trạng thái thực, không cần phát lại thao tác. Đợi daemon dừng trước khi lưu checkpoint cuối nếu strategy yêu cầu.

### U10.2 — Đổi image đúng một daemon

```bash
ceph orch daemon redeploy "osd.$OSD_ID" --image "$TARGET_IMAGE"
```

Redeploy tái tạo và khởi động container; không phát thêm restart/start chỉ vì action chưa trả trạng thái terminal. Ghi request time, actual stop/start, image ID/digest và daemon identity.

Lệnh chỉ định **đúng daemon X**; operator phải tự áp đầy đủ prerequisites và kiểm ok-to-stop trước lần dừng thực tế. Lệnh và lifecycle phải được xác nhận trên build thực trong rehearsal. Nếu endpoint không hỗ trợ `--image`, HOLD và sửa runbook; không đổi thành upgrade toàn cụm để thay thế. Tham số name/image được mô tả trong [API redeploy của Pacific](https://docs.ceph.com/en/pacific/api/mon_command_api/#orch-daemon-redeploy); hành vi tạo lại container tham khảo [Cephadm daemon control](https://docs.ceph.com/en/latest/cephadm/operations/#redeploying-or-reconfiguring-a-daemon).

### U10.3 — Chứng minh target chạy đúng

```bash
ceph orch ps --daemon_type osd --daemon_id "$OSD_ID" --format json --refresh
ceph tell "osd.$OSD_ID" version
ceph osd metadata "$OSD_ID" -f json-pretty
ceph config show "osd.$OSD_ID"
ceph osd tree -f json-pretty
ceph pg dump pgs -f json-pretty
ceph health detail
ceph crash ls-new
```

Trên host X, xem log unit thực tế đã xác minh; với unit cephadm thông thường:

```bash
# Chạy trên OSD_HOST; điền thời điểm bắt đầu để giới hạn log.
journalctl -u "ceph-$EXPECTED_FSID@osd.$OSD_ID.service" \
  --since "${PHASE_START:?Dien thoi diem}" --no-pager
```

**U3 PASS:** process chạy đúng target digest/version và đúng identity/device; mount/replay sạch; không crash loop; phase terminal; QoS ổn; X chưa nhận PG ngoài phạm vi. PA2 đọc lại W=0/R0/A=0 sau start; PA1 ghi local cleanup/reuse bằng công cụ quan sát đã test.

`ceph --version`, action “scheduled/starting” hay chỉ dòng “up” không đủ thành PASS. `ceph osd df` không chứng minh payload cũ trên X còn nguyên.

**Không đạt → I06. Đạt → A04 hoặc B02 theo nhánh đang chạy.**

<a id="verify"></a>
## 9. H0/H1, SQLite, canary và cấp quyền

Phần này chạy trong cả PA1 và PA2. **H0 là hash tham chiếu độc lập; H1 là hash quan sát đúng bản/version cần kiểm.** SQLite giữ tham chiếu và tiến độ, không tự tạo snapshot, không tự đọc replica X và không tự chặn Ceph.

Các bước tích hợp dưới đây là procedure cho công cụ dự án. Phiếu change phải trỏ tới **lệnh/API thật đã triển khai và rehearsal** cho local-reader, journal, verifier, gate và repair. MOP không đặt ra lệnh giả như “ceph h0 verify”. Chưa có một thành phần thì ghi NOT_IMPLEMENTED/NOT_PROVEN và giới hạn bài thử tương ứng.

### H00 — Chốt chính sách của run

| Chế độ | Điều được làm/kết luận | Điều chưa được suy ra |
| --- | --- | --- |
| H-LAB + BATCH_CHECKPOINT | Kiểm một tập version hữu hạn; đo chi phí/phát hiện/coverage; ghi mới vào batch sau | Chưa chứng minh chặn primary/source/read trước dùng dữ liệu |
| H-LAB chưa đọc được local X | Chỉ kiểm ứng dụng, mapping và native scrub; ghi rõ coverage | GET qua Y khớp không chứng minh X khớp |
| H-ENFORCE + BATCH_CHECKPOINT | Thực thi quyền đúng contract cho tập đã kiểm; báo riêng head chờ | Checkpoint cũ không bảo đảm head mới |
| H-ENFORCE + STRICT_CURRENT | Chỉ cấp quyền cho version hiện tại có evidence hợp lệ và enforcement tại điểm sử dụng | Một lần canary PASS không bảo đảm mọi ghi tiếp theo không có lỗi |

Đối với production theo yêu cầu chặn bản chưa kiểm của checklist: **H-LAB không đủ đóng G15**. Nếu chọn policy production khác, phải ghi rõ phạm vi bảo vệ và nguồn phục hồi đã được quyết định; không đổi nhãn để coi checkpoint là STRICT_CURRENT.

### H01 — Chuẩn bị manifest, nguồn phục hồi và sổ tiến độ

**Thực hiện lần đầu trước thay placement; đối chiếu lại trước U10/rejoin.**

1. Chốt inventory bắt buộc theo PG nhưng khóa identity theo object/version/range: FSID, pool/namespace, oid/app identity, locator nếu dùng, incarnation, snapshot/version, offset/length, thuật toán, manifest ID.
2. Ghi tầng dữ liệu: RGW payload, RBD logical range hay RADOS local object. Bridge cho multipart/head/tail, sparse/discard, snapshot, mã hóa/nén phải có bằng chứng. Payload hash không tự bao phủ OMAP/xattr/index/metadata.
3. H0 dữ liệu mới lấy trước đường có thể làm sai; dữ liệu cũ ghi provenance `preupgrade_baseline`. Giữ H0 bất biến; không “học lại” tham chiếu từ X bị nghi lỗi.
4. Giữ được version/checkpoint bắt buộc để đọc lại. Timestamp trong DB không tạo snapshot. Object/version không còn đọc được phải là VERSION_UNAVAILABLE, chưa được bỏ khỏi mẫu số.
5. Ghi ít nhất một nguồn payload cùng version đã kiểm và thời hạn giữ; xác minh khả năng đọc/restore chứ không chỉ tên OSD.
6. Chuẩn bị DB trên filesystem cục bộ của máy verifier độc lập; H0/journal và backup ngoài phạm vi cụm đang nâng. Không đặt DB WAL đang mở trên NFS/CephFS trong thiết kế MVP.
7. Bắt đầu một worker đọc/hash và một writer, batch tối đa **1.000 object hoặc 256 MiB** theo đề xuất lab; giới hạn I/O riêng. Object lớn đọc streaming; chỉ chia chunk nếu có H0 tương ứng.
8. Kiểm mutation-feed có replay/gap detection cho write, truncate/discard, delete/recreate, recovery/backfill và metadata thuộc scope. Không mặc định PG log là change-feed vĩnh viễn.
9. H-ENFORCE: chứng minh quyền mặc định của X khi boot/rejoin, mất controller hoặc failover là đóng; chặn primary/replica-read/source ngoài phạm vi đã cấp ngay từ đầu.

DB cần các nhóm dữ liệu logic: H0 tham chiếu; placement; checkpoint/inventory; việc cần kiểm; H1; dirty/retry queue; tiến độ/watermark. Kết quả phân biệt từng X/build/incarnation, không dùng H1 của peer làm H1 của X.

SQLite WAL vẫn có một writer; dùng transaction ngắn, không giữ transaction khi đọc payload. Backup DB đang mở phải nhất quán và tính cả WAL; restore phải reconcile journal. Xem [SQLite WAL](https://www.sqlite.org/wal.html) và [Online Backup API](https://www.sqlite.org/backup.html). Các tên bảng trong plan là thiết kế logic, không phải schema đã được MOP này cài đặt.

**HG0:** tham chiếu/nguồn/budget rõ. **HG1:** chỉ PASS khi enforcement đã được kiểm thực tế. Trong H-LAB, ghi mức quan sát và giới hạn, không đánh HG1 PASS chỉ từ A=0.

### H02 — Verify replica sau khi C/batch đã vào X

**Người làm:** VO, OP hỗ trợ PG. **Timeout:** T_H0/T_SCRUB. **Đầu vào:** dữ liệu đã đồng bộ, PG khỏe, nguồn tốt còn giữ.

1. Lấy PG interval/membership và identity X hiện tại; chỉ dùng H1 sau khi X đã chạy target. Hash từ trước nâng vẫn là baseline.
2. Lấy batch từ inventory cố định hoặc dirty/retry queue; ghi generation/version dự kiến trước đọc.
3. Đọc payload thật của local X qua đường đã review. Ghi version trước/sau đọc, source thực, build/incarnation và đường cache/media theo fault model.
4. Tính H1, đối chiếu đúng H0 cùng identity/version/range. Nếu version đổi, trả STALE; thiếu H0/coverage trả UNKNOWN; thiếu version cần giữ trả VERSION_UNAVAILABLE.
5. Commit H1, work status và progress/watermark trong cùng transaction SQLite. Chỉ đóng dirty entry khi generation hiện tại vẫn là generation vừa kiểm; mutation mới hơn phải còn pending.
6. Thực hiện kiểm metadata và deep-scrub theo phạm vi. Không xem hash payload là bằng chứng cho RGW index hoặc RBD metadata.
7. Xuất báo cáo bắt buộc/đã kiểm/còn thiếu theo object, byte, PG, metadata; báo phần sampling riêng.

**HG2 hoặc checkpoint PASS đúng scope:** tất cả mục bắt buộc có evidence còn hiệu lực, không mismatch chưa giải quyết, native consistency đạt. Nếu sampling, chỉ kết luận cho mẫu đã kiểm.

### H03 — Reconcile ngay trước mở primary/source

| Kiểm tra tại cửa chuyển bước | BATCH_CHECKPOINT | STRICT_CURRENT |
| --- | --- | --- |
| Inventory checkpoint còn thiếu/mismatch | HOLD | HOLD |
| Checkpoint hoàn tất, head mới chờ | Có thể CHECKPOINT_READY; công bố pending bytes/age và owner hậu kiểm | Chưa cấp quyền cho head chưa kiểm |
| X restart, PG interval/build thay đổi | Reconcile H1 và token, không tự giữ PASS | Thu hồi/reconcile token trước cấp lại |
| Chỉ một PG PASS | Chỉ cấp kết luận cho PG/scope đó | Không mở quyền toàn OSD |
| Ghi mới giữa verify và promote | Vào journal/batch sau theo contract, đo detection lag | Barrier/version tracking và gate nguyên tử phải bao phủ |

Không phải quét lại toàn bộ OSD ở mỗi cửa promote: dùng lại H1 đã commit còn hợp lệ, kiểm phần bắt buộc còn thiếu hoặc mất hiệu lực. H1 tồn tại trong SQLite không tự chứng minh token hiện tại hợp lệ.

Với **H-LAB**, chỉ thử khôi phục affinity khi toàn bộ PG đang vào X đều nằm trong tập đã cho phép thử và đã hoàn tất gate của policy:

```bash
ceph osd primary-affinity "$OSD_ID" "${A0:?Dien affinity ban dau}"
ceph pg dump pgs -f json-pretty
```

Khôi phục A0 tác động toàn X, không phải riêng một PG. Kiểm primary thực tế; nếu không PG canary nào dùng X làm primary thì chưa hoàn tất bài primary canary. Không tự hạ affinity của hàng loạt peer để ép kết quả; điều chỉnh fixture/lựa chọn C trong lab rồi thử lại.

Với **H-ENFORCE**, quyền primary/source/read dùng API tích hợp đã test, ràng buộc từng PG/version; thay affinity chỉ là đầu vào placement. HG3 chỉ PASS khi evidence hợp lệ tại điểm cấp quyền, gồm tình huống failover.

### H04 — Workload và soak canary

| Tầng | Bài kiểm | Bằng chứng |
| --- | --- | --- |
| RGW đọc | GET đúng immutable key/version; đủ byte, SHA-256 so H0 | Endpoint, bucket/key/version, size, expected/observed hash |
| RGW ghi | PUT/overwrite, multipart hoàn tất/đọc lại, LIST, delete trên fixture được phép | Expected version/bytes, final error và retry; ETag không thay payload SHA-256 |
| RBD đọc | Đọc snapshot/range đã ghim, offset/length rõ | Expected bytes/hash, image/snap và flush/quiesce policy |
| RBD ghi | Tải read/write/overwrite/flush/discard nếu áp dụng trên **image test riêng** | Expected version/checkpoint, checksum và client latency |
| Metadata | Các chức năng RGW index/OMAP, RBD snapshot/clone/features đang dùng | Kết quả kiểm riêng, không suy từ payload |
| Role | X thực sự làm replica rồi primary của PG trong phạm vi | PG query theo thời điểm + workload cùng thời gian |
| Durability/failover | Restart X có kiểm soát và đọc lại trong lab; controller failover nếu thuộc scope | Before/after identity, token, mount/replay và byte kiểm lại |

Trước restart canary, chạy lại `ok-to-stop`, kiểm peer và thời gian; sau restart phải reconcile evidence. Fault injection gây sai byte, mất source hoặc mất feed chỉ chạy trên fixture disposable.

Lab có thể tái dùng ma trận Warp trong plan: 4 KiB và 1 MiB với concurrency 1/8/32; 64 MiB với 1/8/16, tùy capacity và phạm vi run. Bucket benchmark riêng như `rgw-warp-bench`; không dùng bucket ứng dụng `rgw-lab-data` làm đối tượng ghi/xóa benchmark. RBD cũng phải có tên image test xác định.

Giữ workload giống baseline về offered load, endpoint, size/concurrency và client version. Soak tối thiểu T_CANARY tính từ khi dữ liệu/PG hội tụ; đo cả spike peering. Không lấy trung bình các p99 để tạo p99 tổng; thiếu request thì kết quả chưa đủ bằng chứng.

**U4/HG4:** đủ bài replica/primary theo scope, dữ liệu đúng, QoS đạt, không PG ngoài phạm vi; SO/RV/VO ký kết quả trước batch/nấc tiếp.

### H05 — Dirty queue, resume và lỗi verifier

1. Ghi mới sau checkpoint vào hàng đợi; không thêm yêu cầu đợi H1 vào ACK trong MVP BATCH_CHECKPOINT.
2. Theo dõi byte phải rehash và tuổi entry từ lần đầu; ghi nhỏ có thể buộc đọc lại cả object. Coalescing về version mới nhất không chứng minh version trung gian đã đúng.
3. Sau verifier restart, phục hồi work chưa commit, reconcile watermark/identity/version/placement; dùng lại phần H1 hợp lệ. Không đặt toàn bộ progress về 0 một cách máy móc.
4. X restart, đổi build/interval hoặc hết thời hạn evidence: xử lý theo contract token; giữ bằng chứng lịch sử riêng.
5. Journal gap hoặc restore DB cũ: đánh dấu scope có thể bị ảnh hưởng UNKNOWN, replay/recheck. Không khoanh được scope thì phải kiểm lại tập liên quan lớn hơn.
6. DB/WAL đầy, lỗi I/O, mất manifest hoặc backlog vượt budget: HOLD mở rộng; H-ENFORCE không tự mở quyền vì verifier lỗi.
7. Không xóa record lỗi, đổi H0 theo H1 hoặc giảm inventory để đạt “100%”.

**Điều kiện resume:** feed/DB được phục hồi nhất quán, các job không chắc chắn được reconcile, ngưỡng dữ liệu/QoS đạt qua cửa sổ ổn định. Một lần SQLite mở được chưa đủ.

### H06 — Hoàn tất coverage và bàn giao hậu kiểm

Mọi PG thực nhận ở X đã được xét, không chỉ C. Ghi rõ `CHECKPOINT_READY` cho version nào; nếu có head chờ, ghi bytes/age, nguồn H0, deadline và owner hậu kiểm. H-ENFORCE/STRICT_CURRENT còn phải có quyền hợp lệ cho mọi scope đang phục vụ.

Giữ nguồn tốt tới hết retention/aftercare. Trước nâng peer tiếp theo, đánh giá việc mất nguồn đó và lỗi chung phần mềm; peer chạy A không tự động là nguồn đúng. **HG5/U5 chỉ PASS trong phạm vi và policy được khai báo.**

<a id="incident"></a>
## 10. STOP, xử lý sự cố và phục hồi

### I00 — Hành động chung khi STOP

1. Ngừng phát batch/nấc/daemon mới; giữ nguồn tốt và manifest.
2. Nếu upgrade engine đang hoạt động, yêu cầu pause và xác minh state; nếu đang thao tác từng daemon thì dừng hàng đợi thao tác riêng.
3. Thu health, quorum, PG/OSDMap, config, log/crash, metrics client/host, journal và evidence H0 theo timestamp.
4. Xác định phase, PG/workload bị ảnh hưởng và ranh giới store/control-state đã vượt.
5. Chọn một nhánh dưới đây. Resume chỉ khi có nguyên nhân/disposition, gate đạt và CO/RV xác nhận.

```bash
# Chỉ khi có upgrade engine đang chạy:
ceph orch upgrade pause
ceph orch upgrade status

# Thu read-only cho incident:
ceph -s
ceph health detail
ceph quorum_status -f json-pretty
ceph pg dump pgs -f json-pretty
ceph osd dump -f json-pretty
ceph crash ls-new
```

`upgrade pause/stop` không rollback daemon đã nâng, không dừng backfill và không bảo đảm hủy action đã bắt đầu. `ceph orch pause` dừng phạm vi reconciliation rộng hơn, cũng có thể cản stop/redeploy cần thiết; không dùng thay `upgrade pause` một cách mặc định.

### I01 — QoS vượt ngưỡng, chưa có lỗi dữ liệu

- Giữ weight/mapping hiện tại nếu không có sự cố an toàn; chưa cấp thêm việc.
- Giảm việc tùy chọn H0/scrub theo policy, điều tiết background bằng cấu hình **đã rehearsal** cho scheduler thực.
- Giữ kiểm chứng bắt buộc; không bỏ H0 gate để đạt p99. Nếu replica thiếu, ưu tiên khôi phục dự phòng trong cân bằng SLO đã định.
- Khi ổn định qua cửa sổ resume, lập lại batch nhỏ hơn. Nếu hết cửa sổ, bàn giao S2/S3/S4 phù hợp.

Không mặc định bật `norecover/nobackfill` toàn cụm; giữ thiếu replica kéo dài có thể làm rủi ro tăng.

### I02 — PG không hội tụ, peer/spare lỗi hoặc thiếu capacity

**Chẩn đoán:** query PG, đích hợp lệ, full/backfillfull, flags, reservation, network/disk, nguyên nhân không tiến và epoch drift.

| Trạng thái | Hướng xử lý |
| --- | --- |
| PA1, X còn store A chưa mở bằng B | Nếu nguyên nhân không phải dữ liệu/phần cứng X và việc rejoin A đã được kiểm, cân nhắc start đúng A để khôi phục dự phòng; reconcile mapping hiện tại trước |
| PA1, S đã đủ và X không cần cho I/O | Giữ S2, hoãn mở target khi điều kiện khác chưa đạt |
| PA2 đang drain, X còn chạy | Giữ X phục vụ, điều tiết/đổi kế hoạch đích; không kéo weight về W0 mù quáng |
| X đã mở B | Giữ B/cô lập theo incident; không hạ binary trên store hiện tại |
| Không đủ peer hợp lệ | Incident dữ liệu/availability; không dừng thêm OSD, không hạ min_size để vượt gate |

Lệnh start trước target chỉ dùng khi runtime/image X đã xác minh vẫn là A và không có redeploy B đang chờ:

```bash
ceph orch daemon start "osd.$OSD_ID"
```

Start lại không tự hoàn nguyên upmap và không chứng minh mọi ghi sau thời điểm X dừng đã được cập nhật. Đợi peering/recovery và kiểm dữ liệu trước kết luận phục hồi.

### I03 — PG ngoài canary hoặc mapping drift

1. HOLD việc trả PG/tăng weight; ghi `P_X thực tế − C`, thời điểm và byte đã di chuyển.
2. Xác định nguyên nhân: raw CRUSH, cleanup upmap, autoscaler, topology, weight sets, failover hoặc thao tác khác.
3. Với H-ENFORCE, thu hồi/giữ đóng quyền ngoài scope theo contract. Với H-LAB, công bố khoảng hở; không tuyên bố đã chặn dữ liệu.
4. Lập mapping/weight điều chỉnh từ **state hiện tại**; không nạp OSDMap cũ hoặc xóa toàn bộ upmap.
5. Nếu không lập được canary chính xác thì kết thúc run FAIL về phạm vi, giữ workload trên nguồn khỏe; chưa đưa phương án này sang production.

### I04 — H0 mismatch hoặc dữ liệu không nhất quán

**Luồng phục hồi bắt buộc:**

1. Giữ manifest/bytes/hash/version/log và khoanh phạm vi; kiểm mismatch thật cùng version hay chỉ version drift.
2. Chặn quyền X liên quan bằng enforcement đã có. Nếu H-LAB không có hàng rào, chọn cách dừng/cô lập đã rehearsal theo incident và kiểm availability; không mặc định affinity=0 đã chặn.
3. Liệt kê các nguồn payload theo PG history hiện tại, đọc/hash cùng identity/version/range. Chọn nguồn **khớp H0**, kể cả chỉ một nguồn khớp.
4. Kiểm lại interval/version; ghim source hoặc staging đã verify và tuần tự hóa với ghi mới theo contract.
5. Dùng recovery/rebuild procedure đã review có khả năng ràng buộc nguồn/version; ghi **actual source**. Nếu chưa triển khai khả năng này, dừng ở đề xuất, không tự sửa live.
6. Truyền payload và metadata đúng; hoàn tất durability rồi đọc lại X, kiểm H1=H0, metadata và consistency.
7. Chạy lại H02/H03, sau đó canary/soak. Success của lệnh repair chưa phải VERIFIED.

Ceph native không nhận manifest H0 bên ngoài làm chỉ thị chọn nguồn theo MOP này. Không tự `pg repair` theo đa số, không sửa checksum metadata để hợp thức hóa payload sai, không chép block device trực tiếp giữa OSD đang chạy. Tham khảo [giới hạn PG repair](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/).

**Không nguồn khớp:** NO_VALID_SOURCE. Nếu có bản payload độc lập/checkpoint tốt, thực hiện restore ứng dụng theo runbook và RPO đã chọn; restore về version cũ khác repair current replica. Nếu chỉ còn hash, không thể phục hồi payload bằng H0; giữ incident và báo phạm vi mất dữ liệu chưa phục hồi.

### I05 — MGR/MON/cephadm hoặc monitoring lỗi

- Chưa nâng role tiếp theo; giữ quorum và telemetry độc lập.
- Nếu MGR target đã làm migration control-state, dùng strategy forward-fix đã chọn. Không tự promote base MGR về active để thử khi chưa chứng minh decode/reconciliation.
- Nếu mất metrics Ceph, chỉ tiếp tục quan sát bằng nguồn thay thế đã test; không mở rộng khi stop/go không còn đáng tin.
- MON lỗi: xử lý theo runbook quorum/control-plane riêng, giữ state và log; không sửa map/trim/repair store trong lượt nâng này.
- Action ngoài manifest hoặc image sai: dừng nguồn automation, đối chiếu action queue/runtime và scope đã thay đổi trước khi sửa.

### I06 — Target OSD không mở được store hoặc crash

1. Chặn mở rộng và giữ workload trên S/Y/Z nếu còn đủ nguồn; không retry restart vô hạn.
2. Thu mount/replay/BlueFS/RocksDB log, crash, effective config, device ownership và image thực.
3. Coi store đã vượt boundary nếu B có thể đã ghi, dù daemon chưa lên “healthy”.
4. Chọn fix-forward bằng artifact đã sửa và test, hoặc rebuild/restore theo strategy đã diễn tập.
5. Nếu cần xóa/reprovision, mở procedure thay OSD riêng: giữ nguồn tốt, xác nhận `safe-to-destroy` và device identity; **không** dùng `ok-to-stop` thay điều kiện xóa. MOP này không phát lệnh zap/purge/destroy.

### I07 — Ma trận hoàn nguyên

| Đối tượng | Có thể hoàn nguyên thế nào? | Bằng chứng cần trước khi làm |
| --- | --- | --- |
| Affinity / weight / cờ / autoscale | Khôi phục từng giá trị do phiên sở hữu, sau khi tính ảnh hưởng map | Journal before/applied/current không xung đột |
| Upmap | Restore entry trước phiên hoặc xóa entry do phiên tạo, từng PG/batch | Entry hiện tại còn đúng giá trị phiên sở hữu; mapping mới hợp lệ |
| X chưa mở target | Có thể start A trên store chưa bị B sửa nếu phù hợp incident | Runtime A, store/peer đủ tin cậy, không pending action B |
| X đã mở/ghi bằng B | Forward-fix/rebuild; hoặc restore nhất quán đã test | Nguồn payload tốt / snapshot đủ block-DB-WAL, rejoin hợp lịch sử |
| MGR control-state mới | Forward-fix hoặc failback theo rehearsal cụ thể | Migration/checkpoint và behavior consumer đã chứng minh |
| MON | Runbook quorum-safe theo state thực | Quorum, decode/state và failback đã thử |
| RGW / client | Theo endpoint/cache/shared-state và giới hạn security | Traffic drain, retained state, cache sạch và tương thích |
| Cả cluster | Không có rollback “đổi image về A” chung | Recovery plan theo từng thành phần và dữ liệu |

Không nạp đè OSDMap/CRUSHMap cũ lên cụm đã có epoch và ghi mới. Snapshot một OSD không đưa toàn cụm về thời điểm đó.

<a id="closure"></a>
## 11. Đóng lượt OSD và hoàn tất hop

### E01 — Khôi phục có đối chiếu ownership

**Đầu vào:** PA đã hoàn tất hoặc đang bàn giao mốc giữ được duyệt; H06 và QoS đạt đúng scope.

Với mỗi thay đổi, so ba giá trị **before / last-applied-by-change / current**. Current khác last-applied là conflict; chưa ghi đè. Khôi phục theo từng mục, tính tác động mapping và chờ ổn định:

| Mục | Thao tác kết thúc |
| --- | --- |
| CRUSH weight | PA2 đã tăng từng nấc về W0; PA1 giữ/đối chiếu W0. Nếu chưa về W0 vì HOLD, bàn giao rõ state, không gọi hoàn tất |
| Override R0 | Thường không đổi. Nếu auto-out hoặc incident đã đổi, lập bước đưa lại R0 với tác động map và gate tương ứng |
| Primary affinity | Trả A0 khi mọi PG/quyền liên quan đủ điều kiện; kiểm primary thực sau đổi |
| Upmap | Restore/xóa đúng entry của phiên từng batch; bảo toàn entry có trước |
| Scoped noout | Gỡ chỉ nếu phiên đã tạo và X ổn, không có công việc khác còn cần |
| norebalance hoặc cờ khác | Gỡ chỉ cờ do phiên sở hữu; kiểm toàn bộ remap chờ trước khi mở |
| Scheduler/config tạm | Restore đúng scope và trạng thái có/không có override trước phiên; không “config rm” mọi key |
| Autoscale | Restore mode từng pool; nếu tiếp tục campaign có thể bàn giao freeze với owner/expiry |
| Balancer | Restore trạng thái trước phiên hoặc bàn giao freeze giữa lượt; bật lại có thể sinh remap mới |
| Alert silence / traffic drain | Hoàn tất theo journal, không làm mất cảnh báo thật hoặc trả traffic vào daemon chưa đạt |

Ví dụ scoped noout do phiên tạo:

```bash
ceph osd unset-group noout "osd.$OSD_ID"
```

Nếu baseline balancer là bật và không còn phase quản lý mapping thủ công:

```bash
ceph balancer on
```

Theo dõi sau cleanup/bật lại, không chỉ chụp trước đó. Không để cờ toàn cụm không owner/không hạn xử lý khi kết thúc ca.

### E02 — Điều kiện PASS OSD và bàn giao

- [ ] X đúng target digest/version và identity, qua restart/replay test áp dụng; không crash loop.
- [ ] Các PG ở X, P_X ban đầu và mọi PG bị ảnh hưởng đều hội tụ, đủ replica; không inconsistent/unfound hoặc sự cố chưa giải thích.
- [ ] PA1 có số đo degraded time và cleanup/reuse; PA2 có số đo PG thực vào từng nấc và mọi drift.
- [ ] Canary replica/primary và workload đúng scope đạt, đủ soak và đủ mẫu QoS.
- [ ] Coverage H0/checkpoint/current được ghi đúng; phần chưa triển khai/lấy mẫu/chờ hậu kiểm không bị ghi thành PASS toàn OSD.
- [ ] Nguồn payload tốt và aftercare còn theo retention; nâng OSD tiếp theo không làm mất nguồn bảo vệ bắt buộc.
- [ ] Thay đổi tạm đã hoàn nguyên hoặc có record bàn giao owner/expiry; không còn xung đột config/mapping.
- [ ] SO/VO/RV và CO xác nhận kết quả, evidence và residual risk của lượt.

Chạy lại tập read-only P02 với tên hậu tố `after`, thêm báo cáo diff baseline, tổng thời gian, byte ra/về, PG-seconds, p95/p99/error/throughput và verifier backlog.

**PASS một X mới được chọn X tiếp theo.** Chọn lại dựa trên map/tải hiện tại; vẫn một OSD mỗi lượt. Nếu đây là LAB/PILOT một X thì kết thúc ở đây, ghi rõ các daemon khác còn A; không tự tiếp tục whole-cluster upgrade.

### E03 — Hoàn tất các role của hop trong phiên rollout riêng

Chỉ dùng khi phạm vi change bao gồm hoàn tất hop. Nâng xong X không đồng nghĩa nâng xong cluster.

1. Lặp C01 → PA đã chọn → U10/H → E02 cho các OSD trong manifest. Mỗi cohort media/layout/host cần bằng chứng phù hợp; inventory daemon offline phải có disposition và kế hoạch rejoin.
2. Sau khi **mọi OSD trong scope cluster đã được chứng minh target**, đối soát phase OSD với cephadm. Không dùng phase này để nâng hộ một OSD nguồn bị bỏ sót.

```bash
ceph versions -f json-pretty
ceph orch ps --format json
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types osd
ceph orch upgrade status
```

3. Theo order engine, MDS trước RGW nếu thực tế có MDS. Dự án chỉ RGW/RBD có thể ghi N/A khi inventory chứng minh; phát hiện CephFS thì bổ sung MDS runbook/checklist trước khi vượt role.
4. RGW: dùng LB/endpoint procedure thực tế để drain daemon canary, chờ in-flight request theo timeout và bảo đảm endpoint còn đủ tải. Không giả định lab và production cùng dùng HAProxy.
5. Chỉ nâng một candidate RGW đã drain và được filter xác định duy nhất:

```bash
ceph orch upgrade start --image "$TARGET_IMAGE" \
  --services "${RGW_SERVICE:?Dien ten service}" \
  --hosts "${RGW_HOST:?Dien host}" --limit 1
ceph orch upgrade status
```

6. Chờ đúng digest/terminal; kiểm trực tiếp endpoint mới: PUT/GET/multipart/LIST, checksum, auth/TLS/MON connection, Browser POST và worker/notification/lifecycle/multisite nếu áp dụng theo checklist. Traffic chỉ quay lại sau PASS; không bỏ quên endpoint nguồn vẫn phục vụ đường cần sửa lỗi security.
7. Lặp từng RGW. Nếu có rbd-mirror/cephfs-mirror/iSCSI/NFS, chạy cohort tiếp theo đúng order và runbook ứng dụng tương ứng. RBD client không phải daemon OSD: nâng client/cache là phạm vi riêng có test G10; không xóa cache dirty.
8. Đối chiếu monitoring stack, rendered config, alert route, scrape/parser và client SLO. Không áp target Ceph image cho Prometheus/Grafana; dùng image dịch vụ phù hợp theo spec.
9. Khi inventory chứng minh không còn Ceph daemon nguồn chưa xử lý, mọi role đã qua gate và manifest đã bao gồm monitoring refresh, chạy completion/reconciliation cuối hop:

```bash
ceph orch upgrade check --image "$TARGET_IMAGE"
ceph orch upgrade start --image "$TARGET_IMAGE"
ceph orch upgrade status
```

Đây là lệnh toàn phạm vi chỉ dành cho **completion sau kiểm toàn bộ inventory**, không dùng ở bước canary hoặc khi còn OSD A chưa qua quy trình. Nếu `upgrade check` phát hiện daemon chưa được xử lý, quay lại đúng phase trước; không phát start. Theo dõi actual actions và HOLD nếu ngoài manifest.

10. Khi engine terminal, đối chiếu container_image default và các override với artifact đã chốt; xử lý pin tạm theo journal. Cập nhật cephadm/CLI host tương thích qua package procedure đã rehearsal; không coi package host là bằng chứng daemon đã target.

### E04 — PASS hop và chuẩn bị hop sau

- [ ] Mọi daemon trong scope có version/digest mong đợi; daemon/client ngoài scope có disposition, owner và deadline.
- [ ] Health, quorum, PG và correctness RGW/RBD đạt; monitoring/parser/alert hoạt động.
- [ ] G00–G16 áp dụng, test matrix và exceptions được đóng; không có PASS kế thừa từ tài liệu thay cho runtime evidence.
- [ ] Journal lifecycle/migration và action queue terminal; các thay đổi tạm được xử lý hoặc bàn giao có thời hạn.
- [ ] Không nâng feature floor/bật format mới chỉ để clear warning. Patch Pacific này không đòi biến nó thành một major-release transition.
- [ ] Soak T_AFTERCARE và chu kỳ tải quan trọng đạt; nguồn phục hồi, manifest và bằng chứng còn giữ đúng retention.
- [ ] Có biên bản chọn phương án, giới hạn H0 và kết quả hồi phục thực tế; CO/SO/RV/VO xác nhận.

Sau đó mới lập MOP riêng cho 16.2.15 → 17.2.7 và 17.2.7 → 18.2.7 với release note, artifact được hỗ trợ, scheduler, compatibility và boundary của từng hop. Tài liệu này không xác nhận các mốc dự án là lựa chọn patch được hỗ trợ tại thời điểm triển khai.

<a id="rehearsal"></a>
## 12. Rehearsal, chọn phương án và pilot

### 12.1. Bộ bài chạy tối thiểu cho quyết định

| Run | Nội dung | Điều kiện được ghi PASS |
| --- | --- | --- |
| L00 | Base→target artifact/config/control-plane, lifecycle pause/resume | G00–G13 áp dụng có bằng chứng, bootstrap MGR đúng |
| L01 | Store có lịch sử, mount/replay/BlueFS, device mapping, strategy khi lỗi | T01/T02 và các bài durability áp dụng đạt; boundary rõ |
| L02 | Rolling native đối chứng | Workload/coverage giống PA, đủ dữ liệu so lợi ích và chi phí |
| L03 | PA1: dừng giữ store → spare → nâng → canary → batch | A/U/H/E đạt; đo degraded window và cleanup, không suy đoán |
| L04 | PA2: drain → nâng ở W=0 → Wε/C → từng nấc | B/U/H/E đạt; không bỏ qua PG ngoài C |
| L05 | H0 local-reader và bridge app/RADOS/metadata | Phát hiện X sai dù client GET qua peer vẫn đúng; T32 |
| L06 | Enforce, chọn nguồn, concurrent mutation, không nguồn tốt | T33–T37; FAIL/NOT_IMPLEMENTED vẫn giữ blocker cho claim tương ứng |
| L07 | Batch/SQLite/resume | Checkpoint không thay đổi âm thầm; crash/replay không mất việc; journal gap thành UNKNOWN |
| L08 | Faults và cửa sổ kết thúc | Peer/spare lỗi, capacity, QoS, drift, target crash, hết giờ; giữ được mốc an toàn |
| L09 | B100 nếu có | Sync/retention/restore/RPO-RTO thực; chưa chạy ghi NOT_RUN, không coi H0 thay backup |

L07 phải bao gồm: overwrite sau cursor; mutation mới trong lúc commit H1 cũ; worker crash trước commit; verifier restart; DB restore cũ; disk/WAL đầy; version không còn đọc được; object lớn vượt batch; X restart/đổi interval; backlog tăng dưới tải ghi. Đây là kiểm coverage/resume, không chỉ kiểm SQLite có mở file được.

PA1/PA2 dùng cùng dataset history, dung lượng, placement đầu vào tương đương, offered load, budget verify/scrub và timeout. Reset/rebuild lab disposable bằng quy trình đã kiểm để trở về A; không downgrade in-place store đã ghi bằng B. Ghi tác động warm-up/cache và lặp lại đủ để hiểu biến thiên.

### 12.2. Bảng so sánh ra quyết định

| Chỉ số | Rolling đối chứng | PA1 | PA2 |
| --- | --- | --- | --- |
| Artifact/workload/coverage tương đương | NOT_RUN | NOT_RUN | NOT_RUN |
| Dữ liệu / gate bắt buộc | Chưa có kết quả | Chưa có kết quả | Chưa có kết quả |
| p95/p99, lỗi cuối cùng và throughput | ĐIỀN | ĐIỀN | ĐIỀN |
| Degraded PG-seconds / peering time | ĐIỀN | ĐIỀN | ĐIỀN |
| Tổng byte ra/về / thời gian thực | ĐIỀN | ĐIỀN | ĐIỀN |
| H1 valid reused / remaining / rehash | ĐIỀN | ĐIỀN | ĐIỀN |
| PG ngoài canary / mapping drift | ĐIỀN | ĐIỀN | ĐIỀN |
| Store history/cleanup/reuse | ĐIỀN | ĐIỀN | ĐIỀN |
| Fault recovery / hành vi hết cửa sổ | ĐIỀN | ĐIỀN | ĐIỀN |
| Công sức vận hành / mutation / cờ toàn cụm | ĐIỀN | ĐIỀN | ĐIỀN |
| Kết luận và phạm vi áp dụng | ĐIỀN | ĐIỀN | ĐIỀN |

Loại phương án còn lỗi dữ liệu, không giới hạn canary, thiếu nguồn phục hồi, thiếu coverage hoặc vượt SLO/budget không có xử lý đã thử. Trong các phương án đạt, chọn theo mức ảnh hưởng dịch vụ, dự phòng dữ liệu, thời gian/byte và khả năng lặp lại. Nếu cả hai không đạt, HOLD hai phương án và đánh giá lại từ rolling đối chứng; không buộc chọn một.

### 12.3. Chuyển sang pilot production

Điền MOP bằng As-Is production mới nhất, thresholds số thực, X/S/C cụ thể và mapping đã duyệt. Hoàn tất G14/G15/G16, đặc biệt policy H0 và quyết định nguồn payload độc lập; pilot một X có canary riêng. Sau pilot, quan sát qua chu kỳ tải đã chốt rồi mới quyết định rollout. Chưa tăng concurrency từ thành công một X.

<a id="records"></a>
## 13. Biểu mẫu biên bản và bảng liên kết gate

### 13.1. Phiếu theo dõi từng bước

| Run / Step | Bắt đầu–kết thúc UTC | Operator / reviewer | FSID / X / epoch | Lệnh hoặc action thực | Kỳ vọng | Kết quả / exit code | Evidence | Quyết định tiếp theo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | NOT_RUN | ĐIỀN | HOLD |

Mỗi mutation ghi trước/đã áp/hiện tại và phạm vi ảnh hưởng. Không cần copy toàn bộ log vào bảng; liên kết đến file bằng chứng có timestamp và checksum.

### 13.2. Journal thay đổi và hoàn nguyên

| Loại / scope | Before | Applied | Current khi cleanup | Owner / lý do | Entry có trước? | Restore đã duyệt | Kết quả / thời điểm |
| --- | --- | --- | --- | --- | --- | --- | --- |
| W/R/A của X | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | Có | ĐIỀN | NOT_RUN |
| Cờ global/scoped | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | NOT_RUN |
| Upmap từng PG | Toàn bộ entry | Toàn bộ entry | Toàn bộ entry | ĐIỀN | ĐIỀN | Restore/xóa có điều kiện | NOT_RUN |
| Config / autoscale / balancer | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | NOT_RUN |
| Image / lifecycle / control-state | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | ĐIỀN | Boundary/forward-fix | NOT_RUN |

### 13.3. Record H0 và kết quả batch

| Nhóm | Trường bắt buộc |
| --- | --- |
| Identity | FSID, pool, namespace/locator, object/app key, incarnation, snap/version, offset/length, algorithm, manifest ID |
| Scope | Run, checkpoint, PG, interval, target X, build/digest/incarnation, metadata scope |
| Read | Actual source/path, version trước/sau, generation, timestamp, H0/H1 và kết quả |
| Progress | Inventory count/bytes cố định, committed, remaining, retry, dirty generation/watermark |
| Coverage | Mandatory/sample, app/RADOS/local-X/metadata, UNKNOWN/STALE/VERSION_UNAVAILABLE |
| Quyền | Enforcement mode, policy, token/binding/expiry, thời điểm cấp/thu hồi, lý do |
| Repair | Incident, nguồn khớp, actual source, expected version/interval, durability/read-back, retry budget |
| Aftercare | Pending head bytes/age, feed continuity, payload retention, owner/deadline |

### 13.4. Biên bản STOP/resume hoặc bàn giao

| Trường | Nội dung |
| --- | --- |
| Step cuối thành công / step lỗi | ĐIỀN |
| State hiện tại | S0/S1/S2/S3/S4; image X, W/R/A, flags, PG/replica |
| Boundary đã vượt | Target store mount/write; MGR migration; cache/shared-state khác |
| Dữ liệu/dịch vụ ảnh hưởng | PG/workload/version/range, final error/QoS, nguồn còn tốt |
| Việc đã dừng / action còn chạy | Upgrade engine, daemon action, backfill, verifier |
| Quyết định | Giữ state / fix-forward / restore / kết thúc run FAIL |
| Điều kiện resume | Signal, thời gian ổn định, reverify và người xác nhận |
| Bàn giao | Owner, deadline, các cờ/entry còn giữ và next safe action |

### 13.5. Liên kết với checklist và plan

| Gate nguồn | Bước MOP / bằng chứng |
| --- | --- |
| G00 Artifact; G12 Package/build; G13 Validation | P01/P04, L00/L01, manifest và acceptance theo cohort |
| G01 Health; G03 MON; G04 Device/config | P02–P04, K02, C01, U10 |
| G05 Monitoring; G06 MGR; G08 Cephadm | K00–K03, U10, I05, E03/E04 |
| G07 Service; G10 RBD; G11 RGW/CephFS | P04 applicability, H04, E03/E04 |
| G02 Rollback; G09 Activation | P01/P04, U10, I06/I07 và recovery rehearsal |
| G14 / U0–U5 | C01/C02, A hoặc B, U10, H04/H06, E01/E02 |
| G15 / HG0–HG5 / R3H | H00–H06, I04 và T32–T37 theo đúng mức triển khai |
| G16 Phục hồi / yêu cầu 100 TB | Phiếu change, H01, I04/I07, L09, quyết định pilot |
| R0/R1/R2 | P/K: chuẩn bị, MGR bootstrap, MON |
| R3A/R3B | A/B cùng U10/H |
| R4/R5 | E02–E04: mở rộng, dịch vụ, stabilization |
| Plan batch/SQLite mục 8.8 | H01/H02/H05, L07; phân biệt với các test T13–T16 cùng số trong checklist |

Các finding chi tiết 00–15 và test T00–T29 được giữ trong checklist nguồn; bảng trên định vị phase thực hiện, không rút gọn chúng thành “không cần test”.

<a id="sources"></a>
## 14. Nguồn và giới hạn xác minh

### 14.1. Tài liệu dự án dùng để lập MOP

| Nguồn | Phiên bản đọc / cách dùng |
| --- | --- |
| `ceph-osd-upgrade-lab-production-plan(1)(1)(2).md` | Bản đính kèm, cập nhật 21/09/2026: PA1/PA2, U/HG, H0/H1 batch/PG/SQLite, policy và ma trận lỗi |
| `UPGRADE-CHECKLIST(1)(2).md` | Bản đính kèm: hop 16.2.5→16.2.15, G00–G16, rollout, test, STOP và boundary rollback |

Checksum SHA-256 để nhận diện đúng bản nguồn:

```text
PLAN  ac74b9b097e55025bf9b08638ae242ffcb30256398aee4e5f680ac71a184499e
CHECK 5ba49e198e94513852bb350763250abd7ead57672854e67a215440c097fe3de3
```

Các finding source-comparison như BlueFS downgrade, cephadm migration state 5, key/default/security và test coverage được **kế thừa từ checklist**; lần lập MOP này không tái audit bộ 00–15 chưa đính kèm. Các trang Notion được hai file dẫn không phải nguồn trạng thái mới được xác minh trong MOP này.

### 14.2. Tài liệu Ceph đối chiếu cho thao tác

- [Cephadm upgrade — Pacific](https://docs.ceph.com/en/pacific/cephadm/upgrade/) và [staggered/bootstrap MGR](https://docs.ceph.com/en/reef/cephadm/upgrade/#staggered-upgrade): khả năng lọc theo phase và bootstrap từ bản chưa hỗ trợ.
- [Cephadm services — Pacific](https://docs.ceph.com/en/pacific/cephadm/services/): inventory service/daemon và service spec.
- [Cephadm operations — Pacific](https://docs.ceph.com/en/pacific/cephadm/operations/): trạng thái orchestration và daemon logs.
- [Daemon redeploy](https://docs.ceph.com/en/latest/cephadm/operations/#redeploying-or-reconfiguring-a-daemon): cú pháp đối chiếu; hỗ trợ trên image thực phải được rehearsal.
- [Command API — Pacific](https://docs.ceph.com/en/pacific/api/mon_command_api/): đối chiếu PG deep-scrub, scoped flags và daemon redeploy.
- [Using pg-upmap — Pacific](https://docs.ceph.com/en/pacific/rados/operations/upmap/): compatibility và quản lý mapping thủ công.
- [Control commands — Pacific](https://docs.ceph.com/en/pacific/rados/operations/control/): các lệnh OSD/weight.
- [osdmaptool — Pacific](https://docs.ceph.com/en/pacific/man/8/osdmaptool/): mô phỏng CRUSH weight trên bản map cục bộ.
- [PG monitoring](https://docs.ceph.com/en/pacific/rados/operations/monitoring-osd-pg/), [health checks](https://docs.ceph.com/en/pacific/rados/operations/health-checks/) và [PG repair](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/): trạng thái và điều kiện kiểm dữ liệu.

**Trạng thái bằng chứng khi ban hành:** đã biên soạn và kiểm cấu trúc/lệnh mẫu ở mức tài liệu; chưa chạy các lệnh lên cụm, chưa đo QoS, chưa thử restore và chưa triển khai verifier/enforcement. Các ô NOT_RUN/ĐIỀN là phần cần hoàn tất bằng rehearsal và As-Is trước khi thực hiện phase tương ứng.
