# Quy trình và báo cáo nâng cấp Ceph MGR từ 16.2.5 lên 16.2.15

**Ngày lập:** 02/10/2026  
**Phạm vi:** Hai MGR trên cụm lab do cephadm quản lý  
**Tài liệu kiểm soát đi kèm:** [GATE MGR](../test/GATE-MGR-16.2.5-to-16.2.15.md)

## 1. Kết quả thực hiện và giới hạn hồ sơ

Hồ sơ lab ghi nhận cả `mgr.ceph-master.ezhuly` và `mgr.ceph-node3.eniabu` đã chạy Ceph Pacific 16.2.15. Ảnh cuối lúc **17:15:23 ngày 30/09/2026** cho thấy hai daemon `running`, image ID rút gọn `f15b41add2c0`, một active và một standby. `ceph orch upgrade status` tại ảnh này báo `in_progress=false`. Ba MON còn trong quorum, năm OSD `up/in` và 265 PG `active+clean`; cụm có cảnh báo `mon ceph-master is low on available space`.

Phương án đã chuẩn bị là nâng MGR standby trước, chuyển active sang MGR mới, rồi nâng MGR còn lại bằng filtered upgrade. MGR active 16.2.5 chưa hỗ trợ bộ lọc `--daemon-types mgr`, nên chỉ dùng bộ lọc sau khi active đã là 16.2.15. Đây là [trình tự Ceph Pacific](https://docs.ceph.com/en/pacific/cephadm/upgrade/#upgrading-to-a-version-that-supports-staggered-upgrade-from-one-that-doesnt).

Ảnh lab xác nhận trạng thái đầu, cuối và hai mốc migration `2` → `5`. Hồ sơ ảnh chưa chứa log đủ để khẳng định chính xác thời điểm chạy `ceph mgr fail`, lệnh filtered upgrade, checkpoint, freeze cấu hình hoặc RepoDigest đích trên từng host. Các khối lệnh ở mục 4–9 là quy trình chuẩn hóa để thực hiện lại trong một change tương tự; kết quả có ảnh sẽ được ghi rõ riêng. [GATE MGR](../test/GATE-MGR-16.2.5-to-16.2.15.md) giữ các phép kiểm, ngưỡng và kết luận nghiệm thu.

## 2. Mục đích, phạm vi và thông tin cụm

MGR duy trì dịch vụ quản trị của Ceph: cephadm, Dashboard, Prometheus exporter và những module được bật. MGR active thực hiện công việc này; standby tiếp quản nếu active ngừng. Thay image MGR có thể tác động tới điều phối và monitoring dù MON, OSD, RGW không thuộc nhóm daemon đổi phiên bản trong chặng này.

| Hạng mục | Giá trị trong hồ sơ lab |
| --- | --- |
| FSID | `17c77e12-a16a-11f1-838e-cf68e9c001d8` |
| MGR | `mgr.ceph-master.ezhuly` trên `10.20.20.11`; `mgr.ceph-node3.eniabu` trên `10.20.20.13` |
| Image nguồn trong metadata | `docker.io/trangtran97/ceph@sha256:3694ab472a483b17b920e04fd8f924dd5c072096a3f0c46ca2dd00f84d094d59` |
| Image đích theo phương án | `quay.io/ceph/ceph:v16.2.15`; phải chốt RepoDigest thực tế trước redeploy |
| Ảnh cuối | Hai MGR 16.2.15, image ID `f15b41add2c0`; active `ceph-master.ezhuly`, standby `ceph-node3.eniabu` |
| Trạng thái dữ liệu tại ảnh cuối | 3 MON trong quorum; 5 OSD up/in; 10 pool; 265 PG active+clean |
| Cảnh báo tại ảnh cuối | MON `ceph-master` thiếu dung lượng khả dụng |

Image ID rút gọn trong `orch ps` không phải RepoDigest để dùng làm đầu vào redeploy. Dòng `Using recent ceph image...` trong `cephadm shell` mô tả image của CLI đang gọi lệnh; phiên bản MGR được xác định từ daemon thực tế.

Vai trò active/standby đổi theo thời điểm. Sơ đồ và ghi chú thao tác trong `Mop MGR-legacy.docx` nêu `ceph-master.ezhuly` active trước canary; một ảnh `ceph -s` khác lại cho thấy `ceph-node3.eniabu` active. Ảnh cuối quay về `ceph-master.ezhuly` active. Vì ảnh không tạo thành timeline đầy đủ, mỗi bước phải lấy vai trò mới nhất trực tiếp từ cụm.

```bash
# MINH CHỨNG MM01 — Trước và sau nâng
# Nguồn: Mop MGR-legacy.docx, ảnh 01 (hai MGR 16.2.5, image nguồn)
# và ảnh 09 (hai MGR 16.2.15, trạng thái upgrade, cảnh báo MON).
```

## 3. Phương án triển khai

| Chặng | Hành động | Lý do |
| --- | --- | --- |
| Chuẩn bị | Chốt vai trò, image, checkpoint và cấu hình | Tránh thao tác nhầm daemon; giữ dữ liệu phục hồi |
| Canary | Redeploy đúng một MGR standby | MGR active cũ vẫn phục vụ khi target khởi động |
| Chuyển active | Cho active cũ rời vai trò một lần | MGR mới nhận chức năng quản trị và chạy migration |
| Hoàn tất | Filtered upgrade nhóm MGR còn lại | Đưa hai MGR về cùng version và giới hạn daemon được chọn |
| Bàn giao | Đối chiếu config; hoàn nguyên thay đổi tạm | Không để lại freeze hoặc image override ngoài dự kiến |

`ceph orch upgrade check` chỉ kiểm image và khả năng nâng. `ceph orch daemon redeploy` trả về thông báo đã xếp lịch, chưa chứng minh daemon mới chạy xong. Chỉ chuyển bước sau khi mã GATE tương ứng đã có kết quả.

Filtered upgrade MGR có thể làm mới các daemon monitoring. Mã cephadm 16.2.15 còn có đường hoàn tất ghi `global/container_image` và xóa một số image override theo loại daemon. Do đó phải đối chiếu cấu hình image và daemon ngoài MGR sau chặng này. [Tài liệu Ceph](https://docs.ceph.com/en/pacific/cephadm/upgrade/#staggered-upgrade) nêu monitoring stack có thể được redeploy sau MGR dù phiên bản container của chúng không đổi.

## 4. Chuẩn bị phiên thao tác

**Trước bước:** MGR-G0 xác nhận cụm, topology, host, image nguồn, khả năng phục hồi và dịch vụ đang dùng; MGR-G2 ghi cấu hình/migration. Khi hai MGR đã ở 16.2.15 như ảnh lab cuối, chỉ thu hiện trạng theo GATE; không redeploy lại để tạo ảnh mới.

Các lệnh sau dùng Bash trên `ceph-master`, với `ceph` là CLI hoặc wrapper đã cấu hình đúng cluster. Nếu phiên đang dùng alias của zsh, cần đưa wrapper tương đương vào Bash. Mỗi lần thực hiện tạo `RUN_ID` mới để không ghi đè hồ sơ cũ.

```bash
export FSID='17c77e12-a16a-11f1-838e-cf68e9c001d8'
export RUN_ID="mgr-$(date -u +%Y%m%dT%H%M%SZ)"
export EVIDENCE="$PWD/mgr-mop-$RUN_ID"
export TARGET_TAG='quay.io/ceph/ceph:v16.2.15'

umask 077
mkdir -p "$EVIDENCE"/{baseline,checkpoint,canary,rollout,post,gates}
set -o pipefail
printf '%s\n' "$FSID" > "$EVIDENCE/checkpoint/expected-fsid.txt"
```

`FSID` giúp xác nhận đúng cụm. `RUN_ID` gắn các lệnh với một lượt thao tác. `umask 077` hạn chế người khác đọc hồ sơ; `pipefail` giữ mã lỗi của lệnh Ceph khi ghi qua `tee`. Không đưa nội dung keyring, token hoặc config-key dump chưa lọc vào bản báo cáo gửi rộng.

### 4.1. Chốt image đích

**Trước bước:** MGR-G0 phần nguồn image, dung lượng và runtime host. **Sau bước:** hoàn tất MGR-G0 phần digest/binary 16.2.15 trên cả hai host.

Kéo tag đã chọn trên `ceph-master` rồi lấy RepoDigest của đúng repository. Trên `ceph-node3`, kéo cùng RepoDigest này. Nếu dùng Podman, thay bằng lệnh tương đương của runtime đang vận hành.

```bash
sudo docker pull "$TARGET_TAG"
export TARGET_IMAGE="$(
  sudo docker image inspect "$TARGET_TAG" \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' |
    awk '/^quay.io\/ceph\/ceph@sha256:/ {print; exit}'
)"
test -n "$TARGET_IMAGE"
printf '%s\n' "$TARGET_IMAGE" > "$EVIDENCE/checkpoint/target-image.txt"
```

RepoDigest cố định đúng image cho cả redeploy canary và filtered upgrade. MGR-G0 xác minh digest đã pull, binary version và khả năng dùng image trên hai host. Ảnh lab MGR chỉ cho thấy image ID rút gọn, vì vậy tài liệu không tự điền một digest đích chưa được chứng minh.

### 4.2. Chốt checkpoint

**Trước bước:** MGR-G0 phần đường phục hồi và MGR-G2 phần `migration_current`, service spec, image config.

GATE lưu config DB, service specs, module, image nguồn từng MGR, balancer/autoscaler và migration. `ceph config-key dump` nếu cần phải ở vùng riêng có quyền hạn chế vì có thể chứa credential. Bản export hỗ trợ đối chiếu và sửa cấu hình; một bản checkpoint phục hồi toàn lab còn phải bao gồm control state và các VM/đĩa liên quan.

Checkpoint phải sẵn sàng **trước lần redeploy MGR target đầu tiên** vì standby target có thể tự thành active nếu active cũ lỗi. Khi 16.2.15 đã nâng migration từ `2` tới `5`, đổi image về 16.2.5 không tự phục hồi control state. Hồ sơ lab chưa chứng minh đường quay lại đầy đủ sau state `5`; phương án xử lý trong tài liệu là giữ target và sửa nguyên nhân.

```bash
# MINH CHỨNG MM02 — Migration trước và sau
# Nguồn: MOP_MGR_16.2.5_to_16.2.15.docx, ảnh 02 (giá trị 2)
# và ảnh 03 (giá trị 5 sau khi target active).
```

## 5. Giữ ổn định cấu hình trong cửa sổ lab

**Trước bước:** MGR-G0 xác nhận trạng thái balancer, mode gốc từng pool và tác động của PA1; MGR-G3 ghi trạng thái workload nền. Nếu không chọn freeze, bỏ qua lệnh dưới đây và ghi quyết định.

Tạm dừng balancer/autoscaler là cách tách một thay đổi placement/PG đồng thời ra khỏi chặng MGR, không phải điều kiện tương thích bắt buộc. Chỉ đổi thành phần đang hoạt động; các pool đang `warn` hoặc `off` được giữ nguyên. Lưu danh sách pool được đổi để hoàn nguyên đúng phạm vi.

```bash
# Chỉ chạy sau khi MGR-G0 xác nhận hai file baseline hợp lệ.
jq -r '.[] | select(.pg_autoscale_mode == "on") |
  [.pool_name, .pg_autoscale_mode] | @tsv' \
  "$EVIDENCE/baseline/pools.json" \
  > "$EVIDENCE/checkpoint/freeze-pools.tsv"

touch "$EVIDENCE/checkpoint/freeze-requested"
if jq -e '.active == true' "$EVIDENCE/baseline/balancer.json" >/dev/null; then
  ceph balancer off
fi
while IFS=$'\t' read -r pool original_mode; do
  ceph osd pool set "$pool" pg_autoscale_mode off || break
done < "$EVIDENCE/checkpoint/freeze-pools.tsv"
```

MGR-G0 đối chiếu từng pool sau vòng lặp. Nếu lệnh lỗi hoặc pool còn `on`, dừng trước canary. File `freeze-requested` được tạo từ đầu để một lỗi giữa chừng vẫn dẫn tới nhánh hoàn nguyên. Không thay CRUSH, cờ OSD, `pg_num` hay service spec chỉ để nâng MGR.

## 6. Nâng MGR standby làm canary

**Trước bước:** MGR-G0 và MGR-G1 xác nhận vai trò **ngay trước redeploy**; MGR-G2 xác nhận checkpoint/migration. **Sau bước:** MGR-G1 xác nhận target thực sự chạy và còn là standby; các MGR-G3–MGR-G5 áp dụng theo dịch vụ.

MGR ID của active không có tiền tố `mgr.`; tên daemon đầy đủ của standby có tiền tố này. Lấy tên từ `mgr dump` của chính lượt thao tác. Nếu có nhiều standby, chọn rõ daemon từ inventory thay vì lấy phần tử đầu tiên.

```bash
export OLD_ACTIVE_ID="$(jq -er '.active_name' \
  "$EVIDENCE/baseline/mgr-dump.json")"
export STANDBY_ID="$(jq -er \
  'if (.standbys | length) == 1 then .standbys[0].name
   else error("Chon standby tu inventory") end' \
  "$EVIDENCE/baseline/mgr-dump.json")"
export STANDBY_DAEMON="mgr.$STANDBY_ID"
export OLD_IMAGE="$(jq -er --arg id "$STANDBY_ID" \
  '.[] | select(.name == $id) | .container_image | select(length > 0)' \
  "$EVIDENCE/baseline/mgr-metadata.json")"

printf '%s\n' "$OLD_ACTIVE_ID" "$STANDBY_DAEMON" "$OLD_IMAGE" \
  > "$EVIDENCE/checkpoint/canary-selection.txt"
date -u +%FT%TZ | tee "$EVIDENCE/canary/redeploy-start.txt"
ceph orch daemon redeploy "$STANDBY_DAEMON" --image "$TARGET_IMAGE" \
  | tee "$EVIDENCE/canary/redeploy-request.txt"
```

Lệnh chỉ tác động tới một standby. `OLD_IMAGE` phải thuộc đúng canary để điều tra hoặc phục hồi trước migration. Phản hồi `Scheduled` chỉ xác nhận yêu cầu vào hàng đợi; không tiếp tục nếu MGR-G1 thấy vai trò đã đổi hoặc daemon chưa chạy image target.

**Ghi nhận lab:** Ghi chú trong `Mop MGR-legacy.docx` nêu schedule redeploy lúc 15:30:29 và `ceph-node3.eniabu` báo `Activating!` lúc 16:39:06. Ảnh chưa kèm chuỗi log gốc đủ để tính thời gian standby khởi động hay nguyên nhân quãng giữa hai mốc. Dòng `tcmalloc: large alloc 1073750016 bytes` ghi một lần cấp phát lớn, chưa chứng minh OOM.

## 7. Chuyển active sang MGR target

**Trước bước:** MGR-G1 xác nhận target standby khỏe, active cũ vẫn đúng ID; MGR-G0 xác nhận checkpoint. **Sau bước:** MGR-G1–MGR-G5 và cửa sổ MGR-G7 trước khi mở rộng.

`ceph mgr fail` đánh dấu MGR active hiện tại failed để MON chọn standby. Lệnh không chỉ định đích danh MGR tiếp theo. Gửi **một lần** sau khi vai trò đã được kiểm ngay sát lệnh; chỉ đi tiếp khi GATE xác nhận active thực tế chạy target.

```bash
# OLD_ACTIVE_ID phải được MGR-G1 đối chiếu với mgr dump mới nhất.
date -u +%FT%TZ | tee "$EVIDENCE/canary/failover-start.txt"
ceph mgr fail "$OLD_ACTIVE_ID" \
  | tee "$EVIDENCE/canary/failover-request.txt"
```

Khi target thành active, cephadm có thể nâng migration `2` → `5`. Trong source upstream 16.2.5, mốc cuối là `2`; bản 16.2.15 có các bước tới `5` liên quan NFS, quản trị `client.admin` và credential registry. Không chỉnh tay `migration_current` để ép MGR cũ chạy; phải xử lý theo control state thực tế.

**Ghi nhận lab:** Ảnh ghi `migration_current=2` trước nâng và `5` sau khi target đã active. Một ảnh sau đó cho thấy `ceph-node3.eniabu` là active. Đây là bằng chứng target đã nhận vai trò; mức độ hoạt động của module/orchestrator thuộc MGR-G2.

## 8. Hoàn tất MGR còn lại

**Trước bước:** MGR-G1–MGR-G5 của canary và MGR-G7 trong cửa sổ quan sát đạt tiêu chí đã chốt; MGR-G2 xác nhận migration/cephadm và không có upgrade khác đang chạy hoặc paused. **Sau bước:** MGR-G1–MGR-G8.

Sau khi active chạy 16.2.15, dùng filtered upgrade để nâng MGR còn lại. Bộ lọc `mgr` quyết định phạm vi; nếu không được nhận diện, dừng kiểm tra active và module, không bỏ bộ lọc rồi khởi chạy nâng toàn cụm.

```bash
date -u +%FT%TZ | tee "$EVIDENCE/rollout/start.txt"
ceph orch upgrade start --image "$TARGET_IMAGE" --daemon-types mgr \
  | tee "$EVIDENCE/rollout/start-request.txt"
```

Trước khi chạy, ghi manifest daemon dự kiến. Sau khi engine kết thúc, MGR-G2 và MGR-G8 đối chiếu `global/container_image`, image override, `mon_mds_skip_sanity`, service specs và daemon ngoài MGR. Mã cephadm có thể đặt tạm `mon_mds_skip_sanity` và chỉ dọn ở đường hoàn tất; nếu phase bị dừng, cần đọc lại cấu hình thật.

Ảnh cuối lab chứng minh hai MGR đã ở 16.2.15 và `in_progress=false` tại thời điểm chụp. Ảnh không chứa dòng lệnh `upgrade start` hay log filtered phase, nên không dùng nó để khẳng định chính xác đường triển khai đã chạy.

Theo bộ GATE áp dụng cho một lượt mới, lỗi parser MGR-G4.2 sẽ chặn việc mở rộng ở mục này cho tới khi được xử lý hoặc có quyết định ngoại lệ bằng văn bản. Trạng thái hai MGR đã nâng trong lab là sự kiện được ghi nhận, không phải bằng chứng rằng checkpoint này đã được thông qua.

```bash
# MINH CHỨNG MM03 — Hai MGR sau nâng
# Nguồn: MOP_MGR_16.2.5_to_16.2.15.docx, ảnh 04;
# Mop MGR-legacy.docx, ảnh 09.
# Hai MGR running 16.2.15; HEALTH_WARN do MON ceph-master thiếu chỗ.
```

## 9. Hoàn nguyên và bàn giao

**Trước bước:** MGR-G8 xác nhận manifest freeze và quyết định hiện tại của PA1. **Sau bước:** MGR-G8 đối chiếu trạng thái cấu hình; MGR-G3–MGR-G7 cung cấp kết quả vận hành cuối.

Nếu mục 5 đã tạm dừng balancer/autoscaler, trả mode đã lưu cho **các pool mà lần này đã đổi**. Nếu PA1 còn yêu cầu giữ một cấu hình khác, ghi quyết định đó trong biên bản; không bật lại tự động theo snapshot cũ.

```bash
# Điền 'yes' chỉ sau khi MGR-G8 xác nhận PA1 cho phép bật lại.
export PA1_ALLOWS_BALANCER_RESTORE='no'
if [ -f "$EVIDENCE/checkpoint/freeze-requested" ]; then
  while IFS=$'\t' read -r pool original_mode; do
    ceph osd pool set "$pool" pg_autoscale_mode "$original_mode" || break
  done < "$EVIDENCE/checkpoint/freeze-pools.tsv"

  if [ "$PA1_ALLOWS_BALANCER_RESTORE" = yes ] &&
     jq -e '.active == true' "$EVIDENCE/baseline/balancer.json" >/dev/null; then
    ceph balancer on
  fi
fi
date -u +%FT%TZ > "$EVIDENCE/post/end-utc.txt"
```

GATE đối chiếu từng pool và balancer thực tế. Hồ sơ bàn giao gồm RUN_ID, image đích đã xác minh, trạng thái hai MGR, khác biệt cấu hình trước/sau, những thành phần monitoring áp dụng, cảnh báo dung lượng MON và các mục chưa đóng. Kết quả nâng binary không thay kết luận nghiệm thu dịch vụ hay hiệu năng.

## 10. Xử lý khi triển khai không hoàn tất

**Điểm kiểm soát:** MGR-G1–MGR-G8 xác định nhánh dừng, phạm vi ảnh hưởng và điều kiện tiếp tục.

| Tình huống | Hành động vận hành |
| --- | --- |
| Target vẫn là standby, chưa từng active/migrate | Giữ active cũ phục vụ; điều tra pull, unit, module và log. Chỉ cân nhắc redeploy riêng standby về `OLD_IMAGE` khi state chưa đổi. |
| Target đã active hoặc migration lên `5` | Dừng mở rộng; giữ một MGR target hoạt động và sửa nguyên nhân. Dùng lại MGR 16.2.5 phải theo kế hoạch phục hồi control state đã diễn tập. |
| Filtered upgrade đang chạy, cần chặn bước tiếp | `ceph orch upgrade pause` để dừng chuỗi bước kế tiếp; nó không hoàn tác action đã chạy. `upgrade stop` cũng không đưa image/config trở về. |
| Orchestrator mất chức năng | Xem active MGR, module cephadm và journal trên host; giữ MON/OSD/RGW phục vụ; tránh failover lặp khi chưa rõ state phù hợp. |
| Cần quay lại toàn lab | Khôi phục checkpoint nhất quán gồm control state và các VM/đĩa liên quan theo quy trình đã thử. |

Nhánh phục hồi đúng một standby trước migration có thể dùng lệnh sau, chỉ khi MGR-G1/MGR-G2 xác nhận target chưa từng active và state chưa đổi:

```bash
ceph orch daemon redeploy "$STANDBY_DAEMON" --image "$OLD_IMAGE"
```

## 11. Nguồn hồ sơ

1. `MOP_MGR_16.2.5_to_16.2.15.docx` — phương án và năm ảnh lab; `Mop MGR-legacy.docx` — sơ đồ, ghi chú phiên lab và chín ảnh. Hai file được hợp nhất trong quy trình này; ảnh khác thời điểm không được ghép thành một baseline.
2. [GATE MGR](../test/GATE-MGR-16.2.5-to-16.2.15.md) — điều kiện trước/sau chặng, kết quả lab và mục còn thiếu.
3. [Checklist nâng Ceph của dự án](../comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), Git blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6` — G00, G01, G05, G06, G08; T04, T12–T15A, T20/T20A, T26/T26A/T26B và R1.
4. [Rà soát trước MOP](./PRE_MOP_LAB_MGR_16.2.5_to_16.2.15.md), [MGR và monitoring](../comparison/pacific-16.2.5-to-16.2.15/07-mgr-modules-monitoring.md), [Cephadm và orchestrator](../comparison/pacific-16.2.5-to-16.2.15/08-cephadm-orchestrator.md) — cơ sở chọn đường nâng và đánh giá migration.
5. [Ceph Pacific — Upgrading Ceph](https://docs.ceph.com/en/pacific/cephadm/upgrade/) — trình tự bootstrap MGR cho staggered upgrade và tác động monitoring.
