# Quy trình và báo cáo nâng cấp Ceph MON từ 16.2.5 lên 16.2.15

**Ngày lập:** 02/10/2026  
**Ngày thực hiện lab:** 01/10/2026  
**Phạm vi:** Ba MON trên cụm Ceph lab quản lý bằng cephadm  
**Tài liệu kiểm tra đi kèm:** [GATE MON](./GATE-MON-16.2.5-to-16.2.15.md)

## 1 Kết quả thực hiện

Đã hoàn thành nâng cấp cả ba MON từ Ceph Pacific 16.2.5 lên 16.2.15, theo thứ tự **ceph-node2 → ceph-node3 → ceph-master**. Ảnh kết quả cuối trong hồ sơ lab ghi nhận cả ba daemon ở trạng thái `running`, phiên bản `16.2.15` và image ID `f15b41add2c0`.

Phương án thực hiện là nâng lần lượt từng MON. MON trên ceph-node2 được nâng đầu tiên để quan sát hoạt động của phiên bản mới; sau đó đến ceph-node3; MON trên ceph-master, đang giữ vai trò leader trước bước cuối, được nâng sau cùng.

Báo cáo này hợp nhất phương án thao tác đã chuẩn bị với nhật ký và ảnh thực tế trong `MOP MON.docx`. Các lệnh kiểm tra, phép thử, ngưỡng đánh giá và kết luận nghiệm thu được trình bày trong file GATE. Tại mỗi bước của MOP chỉ dẫn mã GATE cần sử dụng.

## 2 Mục đích và phạm vi thay đổi

MON duy trì thông tin điều phối của cụm, gồm bản đồ cụm, thành viên, cấu hình tập trung và dịch vụ xác thực CephX. Việc nâng MON là một chặng của kế hoạch nâng Ceph từ 16.2.5 lên 16.2.15, tiếp sau chặng MGR.

Nâng từng MON giúp giữ hai MON còn lại phục vụ trong lúc một MON được triển khai lại. Chọn một follower làm canary trước giúp quan sát khả năng khởi động, đồng bộ và tham gia quorum của bản mới trước khi thay đổi MON đang là leader. Quorum là nhóm MON đạt đa số để thống nhất trạng thái cụm.

Thay đổi trong chặng này là image chạy của ba daemon MON. Phạm vi không bao gồm nâng tiếp OSD, RGW hoặc chuyển phiên bản Ceph major. Các pool, dữ liệu người dùng và cấu trúc MonMap được giữ theo cấu hình hiện hữu.

### 2.1 Thông tin môi trường

| Nội dung | Giá trị ghi nhận |
| --- | --- |
| Mã cụm FSID | `17c77e12-a16a-11f1-838e-cf68e9c001d8` |
| Hình thức triển khai | Cephadm, daemon chạy trong container |
| Các MON | `mon.ceph-master`, `mon.ceph-node2`, `mon.ceph-node3` |
| Mạng public của MON | `10.20.20.0/24` |
| Leader tại ảnh baseline | `ceph-master` |
| MON trước nâng | 3 daemon ở 16.2.5 |
| MGR trước chặng MON | 2 daemon ở 16.2.15 |
| OSD trước chặng MON | 1 daemon ở 16.2.15 và 4 daemon ở 16.2.5 |
| RGW trước chặng MON | 3 daemon ở 16.2.5 |
| Mã lần thực hiện | `mon-20261001T092850Z-f9f494b7` |

Image đích được cố định bằng RepoDigest:

```text
quay.io/ceph/ceph@sha256:f15b41add2c01a65229b0db515d2dd57925636ea39678ccc682a49e2e9713d98
```

RepoDigest xác định image cần triển khai. Giá trị `f15b41add2c0` trong ảnh `orch ps` là image ID rút gọn; phần đối chiếu đầy đủ RepoDigest trên từng host nằm trong GATE.

```bash
# MINH CHỨNG MC01 — Cụm và phiên bản trước nâng
# Chèn ảnh 01 và 02 theo thứ tự xuất hiện trong MOP MON.docx.
# Nội dung: FSID, RUN_ID, image đích, ceph versions và danh sách MON 16.2.5.
```

### 2.2 Hồ sơ của lần thực hiện

Thư mục minh chứng quản trị được ghi nhận trong lab:

```text
/home/dangg/mgr-mop-20260930T093558Z/evidence-mon-20261001T092850Z-f9f494b7
```

Các bản ghi dùng thời gian UTC, thể hiện bằng hậu tố `Z`. Khi đối chiếu với giờ Việt Nam, cộng thêm 7 giờ. Tên thư mục có tiền tố `mgr-mop` là thư mục làm việc được sử dụng tại lab; mã `RUN_ID` xác định đây là lần nâng MON.

## 3 Phương án triển khai

### 3.1 Nâng lần lượt từng daemon

Lệnh triển khai được sử dụng:

```bash
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE"
```

`redeploy` yêu cầu cephadm triển khai lại một daemon bằng image được chỉ định. Tham số `mon.$MON_ID` giới hạn đối tượng thay đổi; `--image` cố định image cho daemon đó. Trong source cephadm 16.2.15, thao tác này cũng ghi cấu hình `container_image` tại phạm vi daemon.

Lệnh trả thông báo đã lên lịch không đồng nghĩa daemon đã nâng xong. Quyết định chuyển sang MON tiếp theo dựa vào GATE của daemon vừa thực hiện. Không gửi đồng thời yêu cầu nâng hai MON và không chạy thêm `orch upgrade start` trong cùng cửa sổ thao tác.

### 3.2 Thứ tự đã thực hiện

| Thứ tự | Daemon | Vai trò trước bước tương ứng | Mục đích |
| --- | --- | --- | --- |
| 1 | `mon.ceph-node2` | Follower | Canary để quan sát bản mới cùng hai MON còn chạy bản cũ |
| 2 | `mon.ceph-node3` | Follower | Mở rộng sau canary, duy trì nâng lần lượt |
| 3 | `mon.ceph-master` | Leader trước bước cuối | Hoàn tất ba MON sau khi hai follower đã chạy bản mới |

Vai trò MON có thể thay đổi sau bầu chọn. Khi tái sử dụng quy trình, thứ tự được quyết định theo vai trò tại thời điểm thao tác, không cố định theo tên host.

## 4 Chuẩn bị phiên thao tác

**Tham chiếu trước bước:** MG0 và MG1 trong file GATE để xác nhận cụm, trạng thái các daemon, host và image.

### 4.1 Khai báo thông tin lần thực hiện

Các giá trị dưới đây tương ứng với lần lab đã hoàn thành. `FSID` nhận diện cụm; `TARGET_IMAGE` là image cần triển khai; `RUN_ID` nhận diện lần nâng; `EVIDENCE` là nơi lưu lệnh và kết quả. Khi chạy một lần nâng mới, tạo RUN_ID và thư mục mới để giữ nguyên hồ sơ cũ.

```bash
export FSID='17c77e12-a16a-11f1-838e-cf68e9c001d8'
export TARGET_IMAGE='quay.io/ceph/ceph@sha256:f15b41add2c01a65229b0db515d2dd57925636ea39678ccc682a49e2e9713d98'
export CLI_IMAGE="$TARGET_IMAGE"
export RUN_ID='mon-20261001T092850Z-f9f494b7'
export EVIDENCE='/home/dangg/mgr-mop-20260930T093558Z/evidence-mon-20261001T092850Z-f9f494b7'

umask 077
mkdir -p "$EVIDENCE"
set -o pipefail
```

`umask 077` giới hạn quyền đọc hồ sơ. `set -o pipefail` giúp phát hiện lỗi của lệnh Ceph khi kết quả được đưa qua `tee`. Các khối lệnh quản trị sử dụng Bash trên ceph-master, ở ngoài container.

### 4.2 Tạo hàm gọi Ceph

Hàm `c` rút gọn cách gọi Ceph qua cephadm, dùng đúng FSID và image CLI đã chọn. Thư mục minh chứng trên host được đưa vào container tại `/evidence` để các lệnh xuất file có thể ghi đúng vị trí.

```bash
c() {
  sudo timeout --kill-after=5s 30s \
    cephadm --image "$CLI_IMAGE" shell \
    --fsid "$FSID" \
    --mount "$EVIDENCE:/evidence" \
    -- ceph "$@"
}
```

Giới hạn 30 giây áp dụng cho từng lệnh quản trị nhằm tránh terminal chờ vô hạn. Đây không phải thời hạn để MON hoàn thành redeploy. `CLI_IMAGE` chỉ chọn image chạy công cụ quản trị; daemon MON chỉ đổi phiên bản sau thao tác triển khai lại.

Một số ảnh lab có dòng `Using recent ceph image trangtran97/ceph...`. Dòng này mô tả image của phiên CLI đang gọi lệnh. Phiên bản MON được xác định từ daemon đang chạy, như bảng kết quả trong ảnh cuối, không lấy từ dòng thông báo chọn image CLI.

### 4.3 Chuẩn bị image trên các host

Image được tải sẵn trên từng host MON để giảm công việc phải thực hiện khi daemon dừng. Lệnh dưới đây chạy trên từng host bằng runtime Docker đang sử dụng trong lab.

```bash
sudo docker pull "$TARGET_IMAGE"
```

Việc xác nhận image đã tải đúng digest và binary 16.2.15 thuộc MG1. Hồ sơ đính kèm chưa có đủ ảnh tải image riêng của cả ba host; kết quả này không được coi là đã có minh chứng chỉ từ ảnh trạng thái cuối.

## 5 Chuẩn bị cấu hình và theo dõi vận hành

**Tham chiếu trước bước:** MG2 để đánh giá cấu hình; MG3 để chuẩn bị dữ liệu thử và các luồng theo dõi trước canary.

### 5.1 Kết quả rà soát cấu hình trong lab

Ảnh cấu hình hiệu lực của ba MON ghi nhận `container_image` trỏ tới image đích và `public_network=10.20.20.0/24`. Giá trị public network từ file cấu hình phù hợp với cấu hình trung tâm. Nhật ký lab ghi nhận không cần sửa public network tại bước rà soát này.

Cấu hình image mong muốn có thể đã trỏ tới 16.2.15 trong khi daemon còn chạy 16.2.5. Vì vậy, cấu hình này được dùng để chuẩn bị triển khai; kết quả nâng được xác nhận từ phiên bản của daemon sau redeploy.

```bash
# MINH CHỨNG MC02 — Cấu hình trước redeploy
# Chèn ảnh 04, 05 và 06 trong MOP MON.docx.
# Nội dung: các phạm vi container_image và public_network hiệu lực trên ba MON.
# Ảnh 02 dùng đối chiếu MON thực tế vẫn chạy 16.2.5 trước nâng.
```

### 5.2 Thao tác cấu hình khi phát hiện sai lệch

Các lệnh dưới đây chỉ áp dụng khi MG2 xác định có cấu hình cần sửa. Đây là phương án xử lý có điều kiện khi tái sử dụng MOP, không phải danh sách thao tác được xác nhận đã chạy trong lab.

| Phát hiện | Hành động và mục đích |
| --- | --- |
| Public network thiếu hoặc không khớp mạng đã xác nhận | Sửa đúng phạm vi MON để cephadm dựng lại daemon với mạng hiện có |
| `log_max_recent=0` áp dụng cho MON | Sửa giá trị hợp lệ theo finding của checklist để tránh lỗi validation |
| Key cũ áp dụng cho MON nhưng không còn hợp lệ ở target | Xử lý đúng key và phạm vi sau khi có phương án phục hồi cấu hình |
| Balancer hoặc autoscaler đang tạo thay đổi placement | Tạm dừng phần hoạt động cạnh tranh đã xác định, để tách tác động đó khỏi chặng nâng MON |

Ví dụ lệnh cho các trường hợp đã được xác định:

```bash
# Chỉ dùng khi public_network cần sửa và CIDR đã được xác nhận.
c config set mon public_network '10.20.20.0/24'

# Chỉ dùng khi MON được chọn đang có log_max_recent=0.
c config set "mon.$MON_ID" log_max_recent 1

# Chỉ dùng khi key cũ nằm đúng phạm vi daemon này và đã đủ điều kiện loại bỏ.
c config rm "mon.$MON_ID" ms_async_max_op_threads

# Chỉ dùng nếu lần nâng này cần tạm dừng balancer đang hoạt động.
c balancer off

# POOL_TO_FREEZE là pool đã ghi trong sổ thay đổi.
c osd pool set "$POOL_TO_FREEZE" pg_autoscale_mode off
```

Mỗi thay đổi phải ghi giá trị trước, giá trị sau, phạm vi áp dụng và cách hoàn nguyên. Không xóa key ở phạm vi global khi daemon phiên bản cũ còn sử dụng; không thay `ms_async_max_op_threads` bằng `ms_async_reap_threshold` vì đây không phải phép đổi tên tương đương.

Chặng MON không đặt thêm cờ OSD, không thay release flag, không xóa upmap đang dùng và không thay cấu trúc MonMap. Các cấu hình tạm của chặng PA1 được quản lý theo hồ sơ của chặng đó.

### 5.3 Tổ chức các terminal

Lab sử dụng bốn luồng theo dõi chạy độc lập và một terminal quản trị để gửi lệnh nâng. Có thể mở các terminal trên cùng máy nếu máy đáp ứng công cụ và quyền truy cập.

| Terminal | Nhiệm vụ | Mục đích |
| --- | --- | --- |
| Quản trị | Gửi yêu cầu redeploy và ghi mốc thời gian | Điều khiển thứ tự từng MON |
| Theo dõi quorum | Ghi thành viên quorum, leader và election epoch | Đối chiếu trạng thái MON theo thời gian |
| Client xác thực | Tạo kết nối Ceph mới theo chu kỳ | Quan sát khả năng truy cập từ client cũ |
| Client RBD | Chạy tải trên image thử riêng | Quan sát đường dịch vụ RBD |
| Client RGW | Chạy tải S3 trên object thử riêng | Quan sát đường dịch vụ RGW |

Lệnh khởi tạo và vận hành các luồng theo dõi nằm trong MG3. Các luồng này được giữ hoạt động trong lúc thay đổi MON và trong thời gian theo dõi sau nâng.

Trong lab, RBD probe được chạy trong container client cũ với file cấu hình và keyring được gắn vào container. Cách bố trí này giữ được phiên bản client dùng để đối chiếu trước và sau nâng MON.

```bash
# MINH CHỨNG MC03 — Các luồng theo dõi vận hành
# Chèn ảnh 07 và 08 trong MOP MON.docx.
# Nội dung: quorum observer, vòng xác thực, RBD probe trong container và S3 probe.
```

## 6 Thực hiện nâng ba MON

Các khối lệnh trong phần này ghi lại phương pháp đã sử dụng. Ba MON trong lần lab nêu trên đã nâng xong; không cần chạy lại redeploy để bổ sung báo cáo.

### 6.1 Nâng MON canary trên ceph-node2

**Tham chiếu trước bước:** MG0–MG3 và MG4 phần trước redeploy.  
**Tham chiếu sau bước:** MG4 phần sau redeploy và MG5 trước khi chuyển sang MON thứ hai.

ceph-node2 được chọn vì đang là follower. Nâng MON này trước giúp quan sát bản mới tham gia cùng hai MON cũ mà chưa chủ động dừng leader ceph-master.

```bash
export MON_ID='ceph-node2'
export MON_HOST='ceph-node2'

printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$MON_ID" "$MON_HOST" \
  >> "$EVIDENCE/rollout-order.tsv"

date -u +%FT%TZ | tee "$EVIDENCE/$MON_ID.redeploy-start.txt"
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE" \
  | tee "$EVIDENCE/$MON_ID.redeploy-request.txt"
```

`rollout-order.tsv` ghi thứ tự thực hiện. File `redeploy-start.txt` ghi thời điểm gửi lệnh; `redeploy-request.txt` giữ phản hồi của orchestrator để đối chiếu với nhật ký khởi động daemon.

**Kết quả ghi nhận:** Ảnh trước MON thứ hai thể hiện ceph-node2 đã chạy 16.2.15; ceph-master và ceph-node3 vẫn chạy 16.2.5. Đây là bằng chứng canary đã được triển khai trước khi mở rộng sang MON tiếp theo.

```bash
# MINH CHỨNG MC04 — Canary ceph-node2
# Chèn ảnh 09 và 13 trong MOP MON.docx.
# Nội dung: ok-to-stop trả rc=0 và bảng phiên bản sau canary.
```

### 6.2 Nâng MON thứ hai trên ceph-node3

**Tham chiếu trước bước:** MG5 của canary và MG4 phần trước redeploy cho ceph-node3.  
**Tham chiếu sau bước:** MG4 phần sau redeploy; MG6 nếu có sự kiện bầu chọn.

Sau canary, ceph-node3 được nâng để đưa follower còn lại lên 16.2.15. Việc hoàn tất hai follower trước bước cuối tạo cơ sở quan sát cụm có hai MON target trong khi ceph-master vẫn giữ vai trò leader.

```bash
export MON_ID='ceph-node3'
export MON_HOST='ceph-node3'

printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$MON_ID" "$MON_HOST" \
  >> "$EVIDENCE/rollout-order.tsv"

date -u +%FT%TZ | tee "$EVIDENCE/$MON_ID.redeploy-start.txt"
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE" \
  | tee "$EVIDENCE/$MON_ID.redeploy-request.txt"
```

**Kết quả ghi nhận:** Ảnh trước bước cuối thể hiện ceph-node2 và ceph-node3 cùng chạy 16.2.15; ceph-master còn 16.2.5. Tại ảnh đó, quorum đủ ba MON, leader là ceph-master, `election_epoch=550` và `quorum_age=765` giây.

```bash
# MINH CHỨNG MC05 — Hoàn tất hai follower
# Chèn ảnh 17 trong MOP MON.docx.
# Nội dung: hai MON 16.2.15, ceph-master 16.2.5 và quorum trước bước cuối.
```

### 6.3 Nâng MON cuối trên ceph-master

**Tham chiếu trước bước:** MG4 phần trước redeploy cho ceph-master.  
**Tham chiếu sau bước:** MG4 phần sau redeploy, MG6 và MG7.

ceph-master được nâng cuối vì đang là leader tại mốc trước thao tác. Khi daemon này dừng để triển khai lại, các MON còn lại xử lý bầu chọn theo cơ chế của Ceph. Việc đổi leader hoặc tăng election epoch được đánh giá trong GATE theo diễn biến thực tế.

```bash
export MON_ID='ceph-master'
export MON_HOST='ceph-master'

printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$MON_ID" "$MON_HOST" \
  >> "$EVIDENCE/rollout-order.tsv"

date -u +%FT%TZ | tee "$EVIDENCE/$MON_ID.redeploy-start.txt"
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE" \
  | tee "$EVIDENCE/$MON_ID.redeploy-request.txt"
```

**Kết quả ghi nhận:** Ảnh cuối thể hiện cả ba MON chạy 16.2.15. Các giá trị thời gian `running` trong ảnh là tuổi tiến trình tại thời điểm chụp, không phải thời lượng gián đoạn dịch vụ.

```bash
# MINH CHỨNG MC06 — Nâng MON cuối
# Chèn ảnh 18 và 19 trong MOP MON.docx.
# Nội dung: chọn mon.ceph-master và kết quả ok-to-stop trước thao tác.
```

## 7 Hoàn tất và bàn giao

**Tham chiếu trước khi đóng hồ sơ:** MG7 cho kết quả sau nâng và MG8 cho hoàn nguyên, dọn tài nguyên thử.

Sau MON cuối, giữ các luồng theo dõi đến hết cửa sổ đánh giá trong GATE. Dữ liệu thử được giữ cho đến khi có kết quả đọc lại và hồ sơ đầy đủ. Việc dừng probe, đọc lại dữ liệu và xóa đúng tài nguyên thử được thực hiện theo MG7–MG8.

Nếu chặng này có tạo cấu hình tạm, hoàn nguyên theo sổ thay đổi. Chỉ bật lại balancer khi trước đó nó đang bật; chỉ trả autoscaler về chế độ đã lưu cho từng pool.

```bash
# Chỉ áp dụng cho pool được chính lần nâng này đổi tạm.
c osd pool set "$POOL_TO_RESTORE" pg_autoscale_mode "$ORIGINAL_AUTOSCALE_MODE"

# Chỉ áp dụng nếu balancer đã bật trước khi bị tắt trong lần nâng này.
c balancer on
```

Giữ cấu hình image đích cho các MON đã nâng. Việc hợp nhất cấu hình image giữa phạm vi daemon, MON và global thuộc bước quản lý cấu hình tiếp theo; không tự xóa các pin khi chưa xác định image mà daemon sẽ kế thừa.

Hồ sơ bàn giao gồm MOP này, file GATE, nhật ký triển khai, kết quả các luồng theo dõi và danh sách cấu hình giữ lại. Minh chứng gốc tiếp tục được lưu cùng RUN_ID.

## 8 Xử lý khi triển khai không hoàn tất

Phần này quy định hành động vận hành khi gặp sự cố trong một lần thực hiện tương tự. Tín hiệu dừng, lệnh chẩn đoán và điều kiện tiếp tục được dẫn từ MG4–MG7.

### 8.1 Một MON không khởi động hoặc chưa trở lại quorum

Dừng mở rộng sang MON khác và giữ nguyên hai MON đang phục vụ. Thu log theo GATE để phân biệt lỗi tải image, cấu hình, quyền truy cập, mạng, đồng bộ thời gian hoặc dung lượng đĩa.

Sau khi xử lý đúng nguyên nhân, chỉ gửi lại yêu cầu redeploy cho MON lỗi bằng image đích. Không gửi lặp khi yêu cầu trước vẫn đang chờ xử lý.

```bash
# MON_ID phải là đúng MON đang được xử lý sau khi nguyên nhân đã được khắc phục.
c orch daemon redeploy "mon.$MON_ID" --image "$TARGET_IMAGE"
```

Sau phục hồi, áp dụng lại MG4 và cửa sổ theo dõi tương ứng trước khi tiếp tục.

### 8.2 Mất quorum

Dừng toàn bộ thao tác nâng và chuyển sang quy trình phục hồi quorum. Khi lệnh Ceph không trả lời, truy cập từng host để lấy trạng thái systemd, journal và admin socket theo GATE.

Không dừng thêm MON đang hoạt động; không tự xóa MON, chép đè store hoặc sửa MonMap khi chưa xác định bản trạng thái dùng để phục hồi. Phục hồi một MON từ các MON còn khỏe phải dùng quy trình phục hồi đã được diễn tập.

### 8.3 Quay về phiên bản cũ

Quay về image 16.2.5 chỉ là một phần của failback. MON còn phải đọc được trạng thái đã lưu và tham gia lại quorum. Theo checklist dự án, đường failback này cần bằng chứng tương thích state và diễn tập an toàn quorum trước khi áp dụng.

Hồ sơ lab đính kèm chưa có minh chứng diễn tập failback MON. Vì vậy, phương án xử lý trong phạm vi báo cáo là sửa lỗi và phục hồi trên 16.2.15. Không xác nhận khả năng downgrade chỉ vì hai phiên bản đều thuộc Pacific. Bản xuất MonMap và cấu hình hỗ trợ điều tra, nhưng không thay thế bản sao MON store nhất quán.

## 9 Tổng hợp kết quả lab

### 9.1 Kết quả phiên bản trên ba MON

| Daemon | Trước nâng | Sau nâng trong ảnh cuối | Trạng thái | Image ID trong ảnh |
| --- | --- | --- | --- | --- |
| `mon.ceph-node2` | 16.2.5 | 16.2.15 | running | `f15b41add2c0` |
| `mon.ceph-node3` | 16.2.5 | 16.2.15 | running | `f15b41add2c0` |
| `mon.ceph-master` | 16.2.5 | 16.2.15 | running | `f15b41add2c0` |

```bash
# MINH CHỨNG MC07 — Kết quả hoàn tất ba MON
# Chèn ảnh 20 trong MOP MON.docx.
# Nội dung: orch ps --daemon-type mon --refresh,
# ba MON running, cùng phiên bản 16.2.15 và image ID f15b41add2c0.
```

### 9.2 Diễn biến vận hành có trong minh chứng

Ảnh baseline ghi nhận quorum gồm ceph-master, ceph-node2 và ceph-node3, với leader ceph-master và `election_epoch=530`. Các ảnh trong quá trình thực hiện ghi nhận election epoch 546 rồi 550. Epoch tăng cho thấy đã có bầu chọn; riêng các giá trị này chưa xác định thời gian gián đoạn hoặc chứng minh có election loop.

Ảnh trước MON cuối xác nhận quorum 3/3 sau khi đã nâng hai follower. Ảnh PG trong giai đoạn này ghi nhận `265 active+clean`, khoảng 18 GiB dữ liệu và 55 GiB đã sử dụng. Đây là số liệu tại thời điểm ảnh được chụp, không được sử dụng thay cho số liệu sau toàn bộ rollout.

Ảnh log observer có bốn mẫu `ok=false, rc=1` tại 13:26:38Z, 13:31:35Z, 14:37:09Z và 14:41:28Z ngày 01/10/2026. Các mẫu này cho biết lệnh truy vấn quorum đã thất bại. Cần đối chiếu stderr, journal MON và log client cùng thời điểm để xác định nguyên nhân và tác động. Phần đánh giá được ghi tại MG6 của file GATE.

```bash
# MINH CHỨNG MC08 — Quorum và trạng thái PG trong quá trình nâng
# Chèn ảnh 03, 11, 16 và 17 trong MOP MON.docx.
# Nội dung: quorum baseline, các mẫu thành công, bốn mẫu truy vấn lỗi
# và trạng thái trước MON cuối.
```

### 9.3 Phần hồ sơ nghiệm thu cần hoàn thiện

Kết quả nâng phiên bản của ba MON đã có minh chứng. Hồ sơ đính kèm chưa bao gồm toàn bộ CSV của các probe, bản đối chiếu checksum sau nâng, log đầy đủ quanh bốn mẫu observer lỗi và chuỗi theo dõi sau MON cuối.

Các tài liệu này cần được bổ sung để kết luận về tính liên tục của dịch vụ, toàn vẹn dữ liệu thử và hoàn tất nghiệm thu theo checklist. Việc bổ sung sử dụng log gốc của lần chạy; các kiểm tra thực hiện sau đó được ghi thời gian riêng trong GATE.

## 10 Tài liệu tham chiếu

1. `MOP MON.docx` — nhật ký thực hiện và 20 ảnh minh chứng của lần lab ngày 01/10/2026.
2. `MOP-MON-16.2.5-to-16.2.15-v2(3).md` và `GATE-MON-16.2.5-to-16.2.15-v2(3).md` — phương án và tiêu chí đã chuẩn bị.
3. [UPGRADE-CHECKLIST(1).md của dự án](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md) — bản đối chiếu có Git blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6`; phần MON tại mục 3.4, T10–T11, R2 và mục 9.
4. [Cephadm module.py tại v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/module.py) — `daemon_action` và `_daemon_action_set_image`, dùng để xác định phạm vi của redeploy và cấu hình image.
5. [Ceph Pacific — Upgrading Ceph](https://docs.ceph.com/en/pacific/cephadm/upgrade/) và [Troubleshooting Monitors](https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-mon/) — nguyên tắc nâng theo daemon và xử lý sự cố MON.
