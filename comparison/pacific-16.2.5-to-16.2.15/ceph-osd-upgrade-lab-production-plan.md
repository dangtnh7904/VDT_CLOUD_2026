# Kế hoạch thử nghiệm hai phương án nâng cấp OSD và lựa chọn triển khai production

**Dự án:** PRJ GD2 — Nâng cấp Ceph cho RGW và RBD  
**Ngày lập:** 18/09/2026  
**Trạng thái:** kế hoạch thiết kế và kiểm thử; chưa có kết quả chạy lab trong tài liệu này.  
**Đầu ra:** thử hai phương án trên cùng điều kiện, đánh giá bằng dữ liệu, chọn một phương án đạt yêu cầu để làm MOP và pilot production.

Tài liệu dựa trên [trang tổng hợp dự án](https://app.notion.com/p/3dcac177517c814cafc2d4db50e481b0), [bản V2](https://app.notion.com/p/3ddac177517c81708502f5c76c17ac5d) và [note tiêu chí chọn OSD](https://app.notion.com/p/3d7ac177517c8086a3eed25414b34cb9). Yêu cầu mới nhất là **đánh giá cả hai phương án trước khi chọn**, thay cho việc mặc định chọn phương án spare/upmap.

> **Phương án 1:** chuyển primary khỏi OSD nguồn, dùng upmap chuyển placement sang spare cùng cụm, thử giữ store cũ bằng cách dừng OSD nguồn trong khi các replica còn lại phục hồi sang spare; nâng OSD nguồn rồi trả PG về có kiểm soát. Thử `norebalance` để hạn chế backfill cân bằng, nhưng vẫn phải đo khả năng phục hồi PG degraded và việc Ceph dọn dữ liệu cũ khi nguồn chạy lại.
>
> **Phương án 2:** giữ OSD nguồn chạy để drain bằng weight về 0, đợi các PG đã chuyển xong rồi nâng cấp. Sau đó mở weight dương rất nhỏ đã kiểm tra mapping, dùng `pg-upmap-items` đưa 1–2 PG ít critical vào canary; dữ liệu và QoS đạt mới tăng weight từng nấc đến giá trị ban đầu.

Các lệnh dưới đây là mẫu để xây dựng runbook lab. ID, image, weight, mapping và ngân sách phải lấy từ cụm thực tế. Chưa có thao tác nào được thực hiện lên cụm của bạn khi tạo tài liệu này.

## Mục lục

1. [Mục tiêu và phạm vi](#muc-tieu)
2. [Quy ước và các cơ chế phải hiểu đúng](#co-che)
3. [Mô hình lab và bộ dữ liệu](#lab)
4. [Cách chọn OSD, spare và PG canary](#chon-osd)
5. [Chuẩn bị chung và các điều kiện chuyển bước](#chuan-bi)
6. [Phương án 1 — Primary affinity, upmap, spare và store cũ](#pa1)
7. [Phương án 2 — Drain weight về 0, canary rồi tăng weight](#pa2)
8. [Kiểm chứng dữ liệu và QoS](#kiem-chung)
9. [Ma trận thử nghiệm và xử lý sự cố](#ma-tran)
10. [So sánh và chọn phương án production](#lua-chon)
11. [Kế hoạch triển khai production](#production)
12. [Lộ trình, đầu ra và mẫu biên bản](#dau-ra)
13. [Nguồn và phạm vi xác minh](#nguon)

<a id="muc-tieu"></a>
## 1. Mục tiêu và phạm vi

### 1.1. Các câu hỏi lab phải trả lời

1. Có cô lập được OSD đang nâng khỏi **tập PG đang phục vụ thực tế**, kể cả vai trò replica, hay mới chỉ chuyển primary?
2. PA1 có giữ được store có dữ liệu đến thời điểm mở bằng phiên bản mới? Khi khởi động lại, dữ liệu nào bị dọn, dữ liệu nào được dùng lại và dữ liệu nào phải backfill?
3. PA2 có thực sự giới hạn giai đoạn đầu ở đúng 1–2 PG được chọn? Có PG ngoài danh sách tự đi vào do CRUSH, weight hoặc thay đổi khác không?
4. Hai phương án ảnh hưởng p95/p99, lỗi client, throughput, dự phòng dữ liệu và thời gian hoàn tất thế nào?
5. Khi QoS xấu, peer/spare hỏng, OSD mới crash hoặc checksum sai, có dừng mở rộng và phục hồi được bằng quy trình đã thử không?
6. Lợi ích so với rolling thông thường có đủ lớn để bù việc di chuyển dữ liệu, quản lý mapping và thời gian vận hành không?

### 1.2. Phạm vi ban đầu

| Nội dung | Phạm vi MVP |
| --- | --- |
| Dịch vụ | RGW và RBD |
| Pool | Replicated pool; bài mẫu `size=3`, `min_size=2`, sau khi xác nhận cấu hình phù hợp |
| Đơn vị nâng | Một OSD mỗi lượt; chưa chạy nhiều OSD đồng thời |
| Canary sau nâng | 1–2 PG có dữ liệu thử và mức quan trọng thấp; kiểm tra toàn bộ PG thực sự vào OSD |
| Spare | OSD thông thường trong **cùng FSID**, hợp lệ với CRUSH rule/class/failure domain |
| Backup riêng | Cụm 100 TB cho tập dữ liệu ưu tiên, có retention và bài restore; không nhận PG native qua upmap |
| Kiểm chứng | Cơ chế Ceph hiện có, deep-scrub theo PG và H0 phía client có giới hạn tải |
| Phần phát triển | Công cụ chọn OSD/lập mapping, journal và điều phối theo QoS nếu triển khai tự động |
| Ngoài MVP | EC, nhiều OSD đồng thời, sửa replication/ACK, mô hình AI tự quyết định thay đổi cụm |

Nếu một OSD production đồng thời chứa PG replicated và EC, OSD đó **không thuộc phạm vi MVP chỉ replicated**. Không được bỏ qua các PG EC khi lập danh sách ảnh hưởng.

Đường phiên bản đang nghiên cứu là `16.2.5 → 16.2.15 → 17.2.7 → 18.2.7`. Mỗi mũi tên là một hop độc lập. Các mốc này lấy từ dự án, không phải xác nhận đây là patch nên chọn tại ngày triển khai. Trước mỗi hop phải chốt bản được tổ chức hỗ trợ, release note, image digest, feature floor và điều kiện client.

Với cephadm, phải hoàn thành phần MGR/MON và các bước trước OSD theo runbook của hop. Khả năng staggered upgrade xuất hiện từ `16.2.11` và `17.2.1`; xuất phát `16.2.5` cần quy trình chuẩn bị tương ứng. `--limit 1` không tự có nghĩa chọn đúng OSD đã xếp hạng. [Cephadm upgrade](https://docs.ceph.com/en/reef/cephadm/upgrade/).

<a id="co-che"></a>
## 2. Quy ước và các cơ chế phải hiểu đúng

### 2.1. Ký hiệu

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `X` | OSD nguồn cần nâng cấp |
| `S` | Spare nhận phần dữ liệu thay cho X; có thể cần nhiều spare cho các PG khác nhau |
| `Y`, `Z` | Các OSD còn lại giữ replica của một PG |
| `A`, `B` | Phiên bản nguồn và đích của hop đang thử |
| `P_X` | Hợp tất cả PG có X trong `up` hoặc `acting`, kèm thông tin primary |
| `C` | Danh sách 1–2 PG được phép làm canary |
| `W0` | CRUSH weight ban đầu đã lưu của X |
| `R0` | OSD override reweight ban đầu đã lưu của X |
| `A0` | Primary affinity ban đầu đã lưu của X |

Ví dụ tập replica `{X,Y,Z} → {S,Y,Z}` chỉ mô tả **thành viên**, không chỉ ra primary. `pg-upmap-items` thay một thành viên; nó không tự tạo replica thứ tư hay một cơ chế “3.5 replica”.

### 2.2. Phân biệt weight để tránh thao tác nhầm

| Thông số | Lệnh | Ý nghĩa | Quy ước trong kế hoạch |
| --- | --- | --- | --- |
| CRUSH weight | `ceph osd crush reweight osd.X W` | Trọng số dung lượng trong cây CRUSH; thường tương ứng TiB | **PA2 dùng loại này làm biến điều khiển chính**; từ `W0` về 0 rồi tăng dần về `W0` |
| OSD reweight | `ceph osd reweight X R` | Hệ số override trong khoảng 0–1 | Giữ nguyên `R0 > 0` khi dùng PA2 theo CRUSH weight; không trộn hai loại giữa lượt thử |
| Primary affinity | `ceph osd primary-affinity X A` | Ảnh hưởng lựa chọn primary, trong khoảng 0–1 | Dùng giảm vai trò primary, xác nhận bằng primary thực tế |

Nếu chọn biến thể PA2 bằng **override reweight**, chuỗi sẽ là `R0 → 0 → Rε → … → R0`, còn CRUSH weight giữ nguyên. Ghi thành một cấu hình thử riêng; không ghi chung chung “rw=1”.

Ví dụ ổ có **CRUSH weight thực tế bằng 15**: tăng CRUSH weight lên 1 vẫn chỉ là một phần trọng số bình thường; còn `ceph osd reweight X 1` là hệ số override đầy đủ. Ổ 15 TB và 15 TiB cũng không giống nhau. Luôn phục hồi giá trị đã lưu, không mặc định mọi OSD phải có CRUSH weight bằng 1. [Control commands](https://docs.ceph.com/en/pacific/rados/operations/control/), [CRUSH weights](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#adjust-osd-weight).

### 2.3. Primary affinity không cô lập OSD

`primary-affinity=0` là cách tránh lựa chọn X làm primary trong cấu hình phù hợp; phải kiểm tra `acting_primary` thực tế sau thay đổi. X vẫn có thể giữ replica, nhận ghi replication, tham gia ACK và xử lý recovery khi còn trong tập phục vụ. Vì vậy “đã chuyển primary” chưa đủ để nói X không ảnh hưởng dữ liệu.

Chỉ chuyển bước cô lập khi đã kiểm tra đầy đủ `up`, `acting`, primary và tiến trình recovery/backfill. Không dùng riêng thứ tự hiển thị của OSD trong một danh sách để suy ra trạng thái đã hội tụ. [Primary affinity](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#primary-affinity).

### 2.4. “Tắt rebalance” phải tách thành những việc khác nhau

| Cơ chế | Tác dụng | Giới hạn trong hai phương án |
| --- | --- | --- |
| `ceph balancer off` | Dừng balancer tự tối ưu placement | Weight, CRUSH, down/out, PG split/merge và mapping thủ công vẫn có thể đổi placement |
| `ceph osd set norebalance` | Hoãn backfill cân bằng trong trường hợp PG không degraded | Không đóng băng OSDMap; không phải danh sách chỉ cho phép một vài PG; không bảo đảm dừng ngay I/O đã bắt đầu |
| `nobackfill` | Chặn backfill | Có thể chặn chính việc đồng bộ sang spare hoặc trả PG về |
| `norecover` | Chặn recovery | Không bật như một bước thường lệ của kế hoạch |
| `noout` cho X | Tránh X bị tự đánh dấu out khi đang dừng | Không giữ đủ replica, không ngăn cleanup và không biến X thành backup |

Đối chiếu `PrimaryLogPG::start_recovery_ops()` ở các tag `v16.2.5`, `v16.2.15`, `v17.2.7`, `v18.2.7` cho thấy nhánh `norebalance` hoãn backfill khi **PG không degraded**. Nhánh này không tự chặn backfill phục hồi PG degraded. Đây là cơ sở để thiết kế bài PA1; vẫn phải tái hiện với đúng image, trạng thái PG và scheduler, không suy rằng mọi PG mang nhãn degraded chắc chắn sẽ hoàn thành. [Mã nguồn Pacific](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/PrimaryLogPG.cc), [OSDMap flags](https://docs.ceph.com/en/pacific/rados/operations/health-checks/#osdmap-flags).

**Cách dùng trong plan:** tắt balancer khi quản lý mapping thủ công; PA1 thử `norebalance` trong giai đoạn cô lập. PA2 phải cho phép backfill khi drain và khi đưa PG về. Không đồng thời bật `nobackfill`/`norecover` rồi chờ dữ liệu tự đồng bộ.

### 2.5. Weight nhỏ và upmap không tự tạo giới hạn cứng 1–2 PG

- Weight nhỏ là điều chỉnh phân bố, không phải quota PG hay giới hạn byte/giây.
- `pg-upmap-items` là ngoại lệ placement cho PG được chỉ định, không phải allowlist chặn tất cả PG khác vào X.
- Đích có override reweight bằng 0 bị bỏ qua trong đường áp dụng upmap. Kiểm tra/cleanup upmap cũng có thể loại mapping tới OSD có effective weight bằng 0, gồm trường hợp CRUSH weight bằng 0.
- Vì vậy phải chuyển X sang **weight dương nhỏ hợp lệ**, kiểm tra mọi PG tự đi vào theo map mới, rồi mới mở backfill cho canary.
- Khi weight đổi, một mapping cũ có thể thành no-op, không còn hợp lệ hoặc bị cleanup. Lệnh báo thành công chưa đủ; phải đọc lại map sau các epoch tiếp theo.

Các điểm về weight và cleanup đã đối chiếu tại `_apply_upmap()` và `check_pg_upmaps()` của [OSDMap.cc v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/OSDMap.cc). Upmap còn yêu cầu client tương thích; phải inventory cả client tạm offline có thể quay lại. [Using pg-upmap](https://docs.ceph.com/en/pacific/rados/operations/upmap/).

### 2.6. Giữ dữ liệu trên ổ không đồng nghĩa giữ một bản backup hợp lệ

Nếu X còn chạy sau khi PG chuyển hẳn sang S, Ceph có thể xóa các PG stray không còn cần trên X. `norebalance` không phải cờ bảo vệ dữ liệu khỏi cleanup. Để thử mở store cũ, PA1 có một bước dừng X trước khi hoàn tất việc thế chỗ; bản trên X sẽ cũ dần so với ghi mới trên cụm.

Khi X chạy lại, nó phải tuân theo peering và lịch sử PG hiện tại. Không ép store cũ làm nguồn chuẩn, không coi việc đổi image về A hoặc phục hồi snapshot một OSD là rollback cả cụm. Luồng stray/deletion có trong [PeeringState.cc](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/PeeringState.cc).

<a id="lab"></a>
## 3. Mô hình lab và bộ dữ liệu

### 3.1. Mô hình đề xuất

| Thành phần | Bố trí lab đề xuất | Mục đích |
| --- | --- | --- |
| MON/MGR | 3 MON, ít nhất 2 MGR | Quorum và thử quy trình nâng đúng thứ tự |
| OSD | Khoảng 6–8 OSD trên 4 host/failure domain phù hợp | Có lựa chọn X, peer và spare; đo thêm PG ngoài phạm vi |
| Spare | Ít nhất một spare đủ chỗ; thêm spare nếu rule yêu cầu | Thế chỗ hợp lệ, không dồn tất cả PG vào một đích không phù hợp |
| RGW client | Endpoint cố định cho mỗi run | Tránh đổi endpoint làm sai so sánh |
| RBD client | Image thử riêng, đường librbd/krbd xác định | Đo latency và verify byte/checkpoint |
| Monitoring | Client metrics, Ceph, host/disk/network; đồng hồ đồng bộ | So sánh đúng thời điểm và phân biệt nguyên nhân |
| Nơi lưu bằng chứng | Ngoài X và ngoài tập dữ liệu đang thử | Giữ journal, manifest H0 và báo cáo khi X lỗi |

Đây là bố trí đề xuất, không phải inventory xác nhận của lab hiện tại. Nếu lab vẫn chỉ có 3 host × 1 OSD và replica theo host, phải bổ sung khả năng thế chỗ trước khi thử drain toàn bộ một OSD mà vẫn giữ đủ 3 replica. Spare cùng host với X có thể hợp lệ cho một số bài khi X đã rút khỏi PG, nhưng không mô phỏng được mất cả host đó; ghi rõ giới hạn.

Spare mới phải được đưa vào topology có kiểm soát. Việc thêm spare với weight bình thường có thể tự gây remap trước khi đặt upmap. Ưu tiên chuẩn bị và ổn định spare trước baseline; nếu “thêm spare trong cửa sổ nâng” là một phần phương án production, phải đo riêng chính bước đó.

### 3.2. Bộ dữ liệu và workload chung

1. **Dữ liệu có lịch sử:** tạo object nhỏ/lớn, overwrite, delete, multipart, RGW index/OMAP; RBD snapshot và các thao tác image thực sự dùng. Lưu cấu hình và lịch sử tạo dữ liệu để kiểm thử mở store cũ.
2. **Dữ liệu canary:** immutable object/version hoặc RBD snapshot/range, có manifest hash độc lập. Chọn PG chứa tập dữ liệu được phép thử; bắt đầu bằng dữ liệu không critical.
3. **Tải ứng dụng:** RGW PUT/GET/LIST/multipart và RBD random/sequential read/write, bao gồm tải hỗn hợp. Sử dụng workload sát production sau bài kiểm tra cơ chế nhỏ.
4. **Tải nền:** chạy thêm bài có backup/H0/streaming với budget giống nhau cho PA1 và PA2; lưu tổng lưu lượng của các tác vụ này.

Với lab RGW đang dùng, benchmark chạy trên bucket riêng như `rgw-warp-bench`; dữ liệu ứng dụng/website ở `rgw-lab-data` không được dùng thay cho bucket benchmark. Chỉ chạy bài ghi RBD trên image test được chỉ định.

Baseline thực nghiệm đề xuất: warm-up 10–15 phút, đo ổn định 30–60 phút mỗi cấu hình, lặp ít nhất 3 lần nếu đủ tài nguyên. Đây là điểm khởi đầu để đo độ biến thiên, không thay cửa sổ đo production ở mục 4.2.

<a id="chon-osd"></a>
## 4. Cách chọn OSD, spare và PG canary

### 4.1. Áp dụng tiêu chí từ note

| Nhóm | Tiêu chí trong note | Cách áp dụng trong plan |
| --- | --- | --- |
| Điều kiện bắt buộc | PG đang khỏe | Tất cả PG liên quan `active+clean` trước khi bắt đầu; không lỗi dữ liệu, thiếu replica hoặc recovery/backfill chưa xử lý |
| Điều kiện bắt buộc | Dừng được mà vẫn phục vụ | `ceph osd ok-to-stop X` đạt ngay trước bước dừng; đánh giá lại khi trạng thái thay đổi |
| Ưu tiên cao | Tải trên PG thấp | Đo IOPS/throughput theo cửa sổ đại diện; tránh OSD chứa PG nóng, kể cả khi tổng PG ít |
| Ưu tiên cao | Peer còn dư tài nguyên | CPU, disk IOPS/latency và network của Y/Z/S đủ nhận thêm tải primary, replication và backfill |
| Ưu tiên | Ít primary PG | Đặc biệt ít primary của PG nhiều I/O hoặc dịch vụ nhạy latency |
| Ưu tiên | Tổng số PG ít | Tính cả primary và replica, ở mọi pool chứa trên X |
| Ưu tiên | Ít liên quan dịch vụ quan trọng | Xác minh mapping pool/workload; không biết criticality thì chưa được gắn nhãn ít critical |

Nguồn: [Tải PG nên đo trong một khoảng thời gian đại diện — Tiêu chí chọn OSD](https://app.notion.com/p/3d7ac177517c8086a3eed25414b34cb9).

Bổ sung điều kiện của hai phương án:

- Dung lượng đích đủ cho PG chuyển đến, tăng trưởng trong thời gian thử và biên dự phòng khi một thành phần khác lỗi.
- Spare đúng root/rule/device class/failure domain; không trùng với replica còn lại của cùng PG.
- Không có vấn đề phần cứng, DB/WAL, disk latency hoặc network chưa rõ nguyên nhân làm nhiễu thử nghiệm nâng cấp.
- MON/MGR, thời gian hệ thống và filesystem hệ điều hành khỏe. Xử lý clock skew hoặc thiếu chỗ MON trước lượt thử.
- Chưa có thay đổi topology, autoscaler, thay OSD hay tác vụ cân bằng khác xung đột với đợt.
- Có dữ liệu, quyền đọc và công cụ để verify tập bắt buộc; có backup/restore cho workload ưu tiên cần bảo vệ.

`ok-to-stop` là kiểm tra khả năng duy trì hoạt động theo trạng thái cụm; nó không chứng minh dữ liệu đúng, không cam kết SLO và không thay `safe-to-destroy` khi thực sự xóa/reprovision OSD.

### 4.2. Đo tải trong khoảng thời gian đại diện

**Production:** đề xuất tối thiểu 24–72 giờ bao gồm giờ cao điểm, batch/backup ban đêm và cửa sổ dự kiến nâng. Nếu tải có chu kỳ tuần, lấy khoảng 7 ngày hoặc cửa sổ đủ chứa chu kỳ đó. Không chọn OSD chỉ từ một lần `ceph -s` lúc rảnh.

**Lab:** chạy các profile tải thấp, tải thường và tải cao đã định nghĩa; lưu đồng thời số liệu trước/trong/sau. Hai phương án phải nhận cùng offered load, không chỉ so throughput thực đạt.

| Tầng đo | Dữ liệu cần thu | Cách sử dụng |
| --- | --- | --- |
| PG | `num_read`, `num_write`, `num_read_kb`, `num_write_kb` nếu bản đang dùng cung cấp; số object/byte; primary/up/acting | Tính rate từ chênh lệch counter; theo dõi PG nóng và dữ liệu cần di chuyển |
| OSD | Commit/apply latency, CPU, RAM, disk await/IOPS/throughput, DB/WAL, network | Xác định headroom của nguồn và peer; không chỉ nhìn % dung lượng |
| Client | p50/p95/p99, error/timeout, request count, throughput theo thao tác | Là dữ liệu quyết định QoS của RGW/RBD |
| Background | Recovery/backfill, deep-scrub, backup, H0 | Phân biệt chi phí của từng thành phần |

Ví dụ tính rate giữa hai mẫu cách nhau `Δt` giây:

```text
PG_IOPS = (Δnum_read + Δnum_write) / Δt
PG_MiB_s = (Δnum_read_kb + Δnum_write_kb) / (1024 × Δt)
```

Đây là proxy tải logic của PG, không phải disk IOPS vật lý của mỗi replica. Không cộng số liệu replica lặp lại thành tổng request client. Bỏ mẫu bị reset counter, đổi định danh hoặc thiếu timestamp; tính đến độ trễ cập nhật PG stats. Không lấy hiệu hai counter âm để kết luận tải thấp.

### 4.3. Quy trình xếp hạng OSD

1. **Loại ứng viên không đạt điều kiện an toàn.** Không dùng điểm tải thấp để bù cho thiếu replica, lỗi dữ liệu hoặc spare sai failure domain.
2. **Ưu tiên ít workload critical**, sau đó tải PG thấp trong cả cửa sổ bình thường và cao điểm.
3. **Kiểm tra tải sau chuyển primary:** Y/Z nào nhận thêm việc, còn bao nhiêu headroom? Chuyển primary khỏi X có thể làm một peer thành nút nghẽn.
4. **So phạm vi ảnh hưởng:** số PG, số primary PG, byte cần chuyển, số peer và host chịu tải.
5. **So thời gian và khả năng nhận dữ liệu:** spare hợp lệ, lượng trống sau chuyển, thời gian backfill dự kiến và ngân sách đêm.
6. Lấy danh sách ngắn 2–3 ứng viên, xuất lý do chọn/loại. Chọn lại nếu metrics cũ hoặc map đã thay đổi.

Không dùng công thức “ít PG nhất luôn tốt nhất”. OSD có 30 PG nóng của dịch vụ quan trọng có thể kém phù hợp hơn OSD có 60 PG ít tải.

Mẫu bảng lựa chọn:

| OSD | Host/class | PG/primary PG | Tải PG bình thường/cao điểm | Criticality | Byte dự kiến chuyển | Headroom peer/spare | ok-to-stop | Kết luận |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| X1 | Điền số liệu | Điền số liệu | Điền số liệu | Đã biết/chưa biết | Điền số liệu | Đủ/thiếu | PASS/FAIL + giờ | Chọn/loại + lý do |
| X2 | Điền số liệu | Điền số liệu | Điền số liệu | Đã biết/chưa biết | Điền số liệu | Đủ/thiếu | PASS/FAIL + giờ | Chọn/loại + lý do |

### 4.4. Chọn spare cho từng PG

Với PG có tập `{X,Y,Z}`, chỉ chấp nhận S nếu:

- S thuộc cùng cụm, online, version phù hợp và có effective weight hợp lệ.
- S chưa là thành viên của PG và không vi phạm failure domain với Y/Z.
- S được phép bởi CRUSH rule và device class của pool.
- S đủ dung lượng sau tất cả PG dự kiến nhận, không chỉ PG đầu tiên.
- Host/network/DB/WAL của S không tạo nút nghẽn chung với peer.

Ước lượng theo từng đích: `free_after = free_before − incoming_physical_bytes − growth − reserve`. Byte logic của PG chỉ là đầu vào ước lượng; đối chiếu compression, metadata/OMAP và số liệu thực tế. Kiểm tra các ngưỡng full/backfillfull đang cấu hình, không nâng ngưỡng để ép bài thử hoàn thành.

### 4.5. Chọn đúng 1–2 PG canary

Chọn từ pool được phép thử, tải thấp, số byte/object đủ nhỏ, dữ liệu có tham chiếu kiểm chứng và peer khỏe. Tránh PG RGW index/metadata quan trọng trong lượt đầu; mở rộng sang loại dữ liệu này ở bài kiểm tra chức năng riêng.

Một PG có thể chứa dữ liệu của nhiều workload. Một object S3 multipart hoặc một RBD image có thể trải qua nhiều RADOS object/PG. Chỉ được gắn nhãn “ít critical” hoặc “đã verify toàn PG” khi đã có mapping/bộ dữ liệu chứng minh; nếu chưa có, dùng pool test có phạm vi rõ ràng.

<a id="chuan-bi"></a>
## 5. Chuẩn bị chung và các điều kiện chuyển bước

### 5.1. Thu thập trạng thái trước lượt thử

Chạy trong môi trường quản trị Ceph đúng version, ví dụ cephadm shell của lab. Lưu output và timestamp của mỗi giai đoạn; tránh lấy một dump cũ làm trạng thái hiện tại.

```bash
RUN_DIR="ceph-upgrade-evidence/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"

ceph fsid > "$RUN_DIR/fsid.txt"
ceph versions -f json-pretty > "$RUN_DIR/versions.json"
ceph health detail > "$RUN_DIR/health.txt"
ceph osd dump -f json-pretty > "$RUN_DIR/osd-dump.json"
ceph osd tree -f json-pretty > "$RUN_DIR/osd-tree.json"
ceph osd df tree -f json-pretty > "$RUN_DIR/osd-df-tree.json"
ceph osd pool ls detail -f json-pretty > "$RUN_DIR/pools.json"
ceph osd crush rule dump -f json-pretty > "$RUN_DIR/crush-rules.json"
ceph pg dump pgs -f json-pretty > "$RUN_DIR/pgs.json"
ceph balancer status > "$RUN_DIR/balancer.txt"
ceph config dump -f json-pretty > "$RUN_DIR/config.json"
ceph osd getmap -o "$RUN_DIR/osdmap.before"
ceph osd getcrushmap -o "$RUN_DIR/crushmap.before"
ceph orch ps --format json > "$RUN_DIR/daemons.json"
```

Lưu thêm scheduler/config hiệu lực của X/Y/Z/S, image digest thực chạy, client versions, PG autoscale mode, weight sets nếu có, trạng thái NTP và các cờ đã tồn tại từ trước. Cấu hình trong config DB chưa chắc là mọi override hiệu lực của daemon.

Ví dụ kiểm tra ứng viên; thay ID mẫu bằng ID đã chọn:

```bash
OSD_ID=0
ceph pg ls-by-osd "$OSD_ID" -f json-pretty
ceph osd ok-to-stop "$OSD_ID"
ceph osd perf
```

Dùng toàn bộ PG dump để đối chiếu hợp `up ∪ acting`; không chỉ đếm các PG source đang làm primary. Schema JSON cần được kiểm tra với từng phiên bản trước khi viết parser.

### 5.2. Hồ sơ mapping và ownership

Mỗi PG có một record gồm: pool, PG ID, epoch, up/acting/primary trước, raw mapping nếu đã phân tích, toàn bộ upmap/upmap-items đang có, thay đổi dự kiến, spare, byte ước lượng, trạng thái thực tế và lệnh hoàn nguyên ở cấp cấu hình.

`pg-upmap-items PG FROM TO` đặt danh sách cặp thay thế của PG. Nếu PG đã có nhiều cặp, một lệnh chỉ chứa cặp mới có thể thay mất danh sách cũ. Phải đọc–hợp nhất–kiểm tra toàn bộ danh sách, không coi lệnh là append tự động. `FROM` cũng không mặc nhiên bằng một OSD đang thấy trong `acting` khi có mapping hoặc `pg_temp` trước đó.

Khi trả PG đã được chuyển bằng cặp `X → S` về X, thao tác có thể là **xóa/khôi phục ngoại lệ cũ** để quay lại raw mapping. Không mặc định thêm cặp ngược `S → X` sẽ có cùng tác dụng.

Tắt balancer trong lúc quản lý thủ công, lưu trạng thái ban đầu. Giữ ổn định PG count/topology trong cửa sổ thử; mọi thay đổi không do phiên sở hữu phải được phát hiện như drift. Không xóa toàn bộ upmap của cụm để “dọn cho sạch”.

### 5.3. Các gate chung

| Gate | Điều kiện PASS | Nếu không đạt |
| --- | --- | --- |
| G0 — Khởi đầu | Inventory, baseline, SLO, backup tập ưu tiên, health và mapping đầy đủ | Chưa thay đổi placement |
| G1 — Trước chuyển/dừng | PG khỏe, đích hợp lệ, đủ headroom, ok-to-stop đúng thời điểm | Chọn lại hoặc hoãn |
| G2 — Đã thế chỗ/drain | X không còn trong up/acting của tập đã rút; PG đủ bản sao và hội tụ | Chưa mở bước nâng tiếp theo |
| G3 — Sau nâng | Image/version đúng, daemon ổn, placement chưa vượt phạm vi | Giữ cô lập, điều tra/fix-forward |
| G4 — Canary | Chỉ PG được phép vào X; dữ liệu, QoS và role test đạt | Không tăng weight/không trả thêm PG |
| G5 — Kết thúc OSD | Đạt coverage bắt buộc, quan sát đủ, cấu hình/mapping được đối chiếu | Chưa chuyển OSD tiếp theo |

PA1 có **ngoại lệ trình tự có chủ đích:** dừng X để giữ store trước khi G2 đạt, sau khi G1 đạt. Phải đo và chấp nhận cửa sổ giảm replica này trong lab; chỉ bắt đầu mở store bằng B sau khi spare đã đồng bộ và G2 đạt. PA2 giữ X chạy đến G2 rồi mới dừng.

<a id="pa1"></a>
## 6. Phương án 1 — Primary affinity, upmap, spare và store cũ

### 6.1. Mục tiêu và đánh đổi

Mục tiêu là chuyển workload sang tập replica thay thế, giữ store của X đến thời điểm thử nâng, rồi trả từng nhóm PG về. Không dùng weight về 0 làm cách drain chính của phương án này; giữ weight của X ổn định để quản lý ngoại lệ theo PG.

**Đánh đổi quan trọng:** muốn giữ dữ liệu trên X bằng cách dừng daemon trước cleanup, sẽ có giai đoạn các PG liên quan thiếu một replica hoạt động, trước khi S nhận đủ dữ liệu. Giới hạn canary 1–2 PG **sau nâng không giới hạn giai đoạn này**: khi dừng X, toàn bộ `P_X` đều cần được xét.

### 6.2. A0 — Chuẩn bị placement và cơ chế dừng

1. Chọn X/S theo mục 4, hoàn tất G0/G1; lập mapping cho toàn bộ `P_X`, gồm cả PG ở pool metadata/index nếu có.
2. Chuẩn bị spare với weight dương hợp lệ, kiểm tra mọi remap do việc đưa spare vào cụm.
3. Lưu weight, affinity, balancer, cờ, mapping và image cũ. Tắt balancer; kiểm soát các thay đổi autoscaler/topology trong bài thử.
4. Xác minh cơ chế stop/start đúng daemon trong cephadm; không dùng tên service kiểu package nếu cụm chạy container.
5. Chốt timeout cho giai đoạn giảm replica. Nếu ước lượng sao chép toàn bộ phần dữ liệu của X vượt mức chấp nhận, không chọn biến thể giữ store này cho production.

### 6.3. A1 — Chuyển primary khỏi X

```bash
# OSD_ID phải là ứng viên đã vượt G1.
ceph osd primary-affinity "${OSD_ID:?set OSD_ID}" 0
```

Đợi các PG ổn định; xác nhận không còn primary trên X trong phạm vi cần rút, đồng thời p95/p99 của các peer nhận primary đạt yêu cầu. X vẫn đang làm replica và giữ dữ liệu cập nhật ở bước này.

Nếu spare cũng cần tránh làm primary ở lượt đầu, cấu hình và ghi journal tương ứng cho spare, bảo đảm mỗi PG vẫn có peer đủ điều kiện làm primary. Nếu primary không chuyển như dự kiến, dừng và tìm nguyên nhân thay vì tiếp tục dựa vào giá trị affinity.

### 6.4. A2 — Bật norebalance và dừng X để giữ store cũ

Chỉ thiết lập các cờ sau nếu chúng chưa có và đã được ghi nhận quyền sở hữu của phiên:

```bash
ceph osd set norebalance
ceph osd set-group noout "osd.${OSD_ID:?set OSD_ID}"
ceph osd ok-to-stop "$OSD_ID"
```

1. Xác nhận không có `nobackfill` hoặc `norecover` làm chặn bài thử. Nếu các cờ do công việc khác đặt, giải quyết xung đột trước khi tiếp tục.
2. Kiểm tra lại `ok-to-stop`; chỉ dừng đúng X nếu đạt.
3. Dừng X bằng quy trình cephadm đã thử. Ví dụ môi trường hỗ trợ:

```bash
ceph orch daemon stop "osd.${OSD_ID:?set OSD_ID}"
```

4. Ghi timestamp X dừng và thời điểm PG bắt đầu degraded. X phải thực sự ngừng chạy; cờ `noout` giữ X không tự bị đánh dấu out trong lúc áp mapping.
5. Bảo toàn block/DB/WAL. Nếu cần checkpoint phục vụ nghiên cứu lab, lấy bản nhất quán khi daemon đã dừng, bao gồm các thành phần liên quan; không cho bản clone có cùng danh tính OSD kết nối vào cụm đang chạy.

**Trạng thái mong đợi:** store cũ trên X còn tại thời điểm dừng; ứng dụng chuyển sang peer còn sống sau peering, nhưng có thể có độ trễ/gián đoạn ngắn. Không cam kết zero latency spike hoặc không có retry.

### 6.5. A3 — Upmap sang spare và phục hồi đủ replica

Áp nhanh danh sách mapping đã chuẩn bị cho toàn bộ `P_X`; theo dõi từng PG và trạng thái cụm. Không dừng thêm OSD khác trong lúc replica chưa đủ.

Ví dụ dưới đây chỉ áp dụng cho PG đã xác nhận chưa có ngoại lệ cần bảo tồn, `FROM` hợp lệ và S chưa thuộc tập replica:

```bash
ceph osd pg-upmap-items "${PG_ID:?set PG_ID}" \
  "${OSD_ID:?set OSD_ID}" "${SPARE_ID:?set SPARE_ID}"
ceph pg "$PG_ID" query
```

Nguồn dữ liệu đồng bộ sang S là các replica còn sống theo cơ chế recovery/backfill của Ceph; X đang dừng nên không truyền các ghi mới. Với nhánh đã đối chiếu trong source, `norebalance` không tự cản backfill khi PG degraded, còn các điều kiện như reservation, dung lượng và scheduler vẫn phải thỏa.

Theo dõi số PG giảm dự phòng, tốc độ tiến triển và thời gian cho đến khi `{S,Y,Z}` đã đủ dữ liệu. Việc lập batch mapping không loại bỏ thực tế rằng các PG chưa được thế chỗ cũng đang thiếu X; khi đã dừng X, khôi phục dự phòng phải được ưu tiên.

**Gate G2:** tất cả PG trong `P_X` đã hội tụ, đủ replica, không còn X trong up/acting; dữ liệu bắt buộc kiểm chứng qua dịch vụ đạt; không có remap ngoài kế hoạch chưa giải thích. Chỉ khi đó mới bắt đầu bước nâng/mở store bằng B.

Nếu PG không tiến triển:

- Kiểm tra degraded thực tế, flags, đích, full/backfillfull, reservation, peer và mapping.
- Nếu chính `norebalance` giữ PG không degraded ở trạng thái chờ, bài “giữ norebalance xuyên suốt” chưa đạt. Có thể thử nhánh mở cờ có kiểm soát sau khi kiểm tra toàn bộ remap chờ, nhưng phải ghi đây là thay đổi biến thể.
- Nếu không khôi phục đủ replica trong ngân sách, dừng thử nâng. Xem xét đưa X chạy lại **trên A khi chưa mở store bằng B**, đối chiếu mapping hiện tại và để Ceph phục hồi; không tự xóa mapping hàng loạt.

### 6.6. A4 — Nâng X khi workload đã ở spare/peer

1. Giữ mapping sang S và affinity của X bằng 0; bảo đảm không có automation đưa PG mới về X.
2. Nâng đúng daemon X theo MOP của hop, giữ nguyên store, không zap/recreate ở bài này. Một lệnh redeploy theo image chỉ được dùng khi bản cephadm hỗ trợ và các daemon prerequisite đã hoàn tất.
3. Khởi động X bằng B; xác nhận binary/image digest thực chạy, log BlueStore/BlueFS/RocksDB và trạng thái daemon.
4. Kiểm tra toàn bộ PG vào X sau khởi động; X chưa được phục vụ ngoài phạm vi được phép.
5. Ghi nhận local PG/byte còn lại, thời điểm cleanup, lỗi mở/replay store và chi phí khởi động. `ceph osd df` một mình không chứng minh toàn bộ dữ liệu cũ còn nguyên.

**Điểm cần kết luận sau lab:** B có mở store có lịch sử trước khi cleanup không? PG nào còn dữ liệu để tái sử dụng? Có phải copy đầy đủ khi đưa PG về không? Không ghi kết luận “PA1 giữ nguyên dữ liệu và chỉ đồng bộ delta” nếu chưa có bằng chứng.

Nếu X chạy lại và các PG cũ bị dọn, đó là hành vi phải đưa vào báo cáo. PA1 vẫn kiểm tra một đường mở store cũ, nhưng lợi ích giảm lưu lượng khi trả dữ liệu có thể không còn. Không sửa cơ chế cleanup hoặc replication trong MVP chỉ để giữ giả định này.

### 6.7. A5 — Trả 1–2 PG về làm canary

1. Chọn `C` theo mục 4.5. Giữ ngoại lệ sang S cho toàn bộ PG còn lại.
2. Xóa/khôi phục đúng ngoại lệ do phiên sở hữu của C để raw/effective mapping đưa chúng về X. Không mặc định dùng cặp ngược S → X.
3. Đọc toàn bộ mapping: chỉ C được phép có X trong up/acting; không có PG khác vào do drift.
4. Khi S/Y/Z đang đầy đủ, đưa PG về X thường là backfill cân bằng của PG không degraded; phải mở `norebalance` để tiến triển. Trước khi mở, kiểm tra tất cả remap đang chờ trên cụm.
5. Đợi canary đồng bộ, active+clean, chạy H0/deep-scrub và kiểm tra QoS. Ban đầu giữ X ở vai trò replica; sau đó có bài riêng xác minh X làm primary với phạm vi canary đã kiểm soát.

Ví dụ xóa ngoại lệ chỉ khi record xác nhận entry trước phiên không tồn tại và toàn bộ entry hiện tại là của phiên:

```bash
ceph osd rm-pg-upmap-items "${PG_ID:?set PG_ID}"
# Chỉ unset nếu phiên này đã đặt và hiện không có công việc khác phụ thuộc cờ.
ceph osd unset norebalance
```

Nếu entry trước phiên đã tồn tại, khôi phục danh sách đã đối chiếu thay vì dùng lệnh xóa trên.

### 6.8. A6 — Trả các PG còn lại và hoàn tất

Sau G4, trả từng nhóm PG theo budget byte/IOPS/QoS; không gỡ toàn bộ mapping một lần. Mỗi nhóm phải đồng bộ, được verify đúng coverage và ổn định trước khi cấp nhóm sau. Không cần giữ `norebalance` giữa mọi nhóm nếu placement đã được kiểm soát và không có công việc ngoài kế hoạch.

Kết thúc khi X chạy B ổn định, đủ PG cần nhận lại, dữ liệu/QoS đạt G5, affinity về giá trị phù hợp đã chốt và các ngoại lệ tạm được xử lý. Spare có thể giữ lại làm năng lực dự phòng cho lượt sau; việc rút spare khỏi CRUSH là một thay đổi placement riêng cần đánh giá.

### 6.9. PA1 được coi là đạt khi

- Chuyển primary và cô lập source có bằng chứng về up/acting/primary.
- Backfill phục hồi sang S hoạt động trong chế độ cờ đã chọn; đo được thời gian giảm dự phòng trên toàn bộ `P_X`.
- Store có lịch sử được mở bằng B; báo rõ cleanup và mức dữ liệu còn dùng lại.
- Canary và trả PG theo batch không vượt phạm vi đã đặt.
- QoS, dữ liệu, xử lý lỗi và tổng thời gian đạt ngưỡng đã định nghĩa.

Nếu yêu cầu là **S phải đầy đủ trước khi dừng X, đồng thời X vẫn giữ nguyên mọi PG cũ sau chuyển**, các cơ chế native nêu trên không tự bảo đảm cả hai. Nhánh nguồn luôn online giúp giữ dự phòng trong lúc copy nhưng có thể cleanup X; phải ghi thành kết quả/biến thể khác, không gọi là đã đạt yêu cầu giữ store nguyên vẹn.

<a id="pa2"></a>
## 7. Phương án 2 — Drain weight về 0, canary rồi tăng weight

### 7.1. Mục tiêu và đánh đổi

Mục tiêu là rút hết PG đang phục vụ khỏi X khi daemon vẫn chạy, nâng X ở trạng thái đã drain, sau đó cho nhận dữ liệu trở lại có kiểm soát. So với PA1 giữ store bằng cách dừng sớm, PA2 thuận lợi hơn cho việc chờ đủ replica ở đích trước khi dừng X; đổi lại có thể phải di chuyển phần lớn dữ liệu ra rồi về và không giữ được payload/PG cũ để thử đầy đủ đường nâng store có lịch sử.

### 7.2. B0 — Chốt loại weight và ngân sách drain

1. Lưu `W0`, `R0`, `A0`; kế hoạch chính dùng **CRUSH weight**, giữ override reweight dương như ban đầu.
2. Chuẩn bị capacity/headroom trên tất cả đích CRUSH có thể chọn. Weight về 0 không có nghĩa dữ liệu chỉ sang một spare duy nhất.
3. Tắt balancer, ổn định topology và lập dự đoán mapping sau drain.
4. Xử lý các ngoại lệ upmap liên quan có thể hết hiệu lực khi X weight=0; ghi lại thay đổi và ownership.
5. Chuyển primary khỏi X nếu đã thử và có lợi; xác nhận peer chịu được tải.
6. Xác nhận backfill/recovery được phép chạy. Không giữ `norebalance` để vừa chặn di chuyển vừa yêu cầu drain hoàn tất.

### 7.3. B1 — Đưa CRUSH weight về 0, giữ X chạy đến khi drain xong

```bash
ceph osd crush reweight "osd.${OSD_ID:?set OSD_ID}" 0
```

Ceph sẽ tính placement mới và di chuyển dữ liệu. X tiếp tục hoạt động trong giai đoạn cần thiết cho peering/replication/backfill. Một lần đổi về 0 có thể làm rất nhiều PG cùng chờ di chuyển; giới hạn recovery/backfill theo scheduler đã thử để bảo vệ client, nhưng không gọi đây là giới hạn chỉ 1–2 PG.

**Theo dõi:** up/acting từng PG liên quan, byte/object misplaced/degraded, nguồn/đích, disk/network, client latency và lỗi. Ghi riêng mức ảnh hưởng ngoài các PG vốn nằm trên X do thay trọng số của cây CRUSH.

**G2 trước khi dừng:** không còn PG phục vụ hoặc đang chuyển phụ thuộc X; các PG đã rời X đủ replica và hội tụ; cụm không có sự cố dữ liệu mới. Kiểm tra `ok-to-stop` tại thời điểm dừng. Không dùng việc đĩa đã “gần trống” thay cho các điều kiện này.

Nếu drain không tiến triển hoặc QoS vượt ngưỡng, dừng kế hoạch nâng tiếp và điều tiết/đánh giá lại. Đưa weight về giá trị cũ ngay lập tức cũng có thể gây thêm remap; phải lập lại phương án từ trạng thái hiện tại. [Theo dõi di chuyển khi rút OSD](https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/#observe-the-data-migration).

### 7.4. B2 — Nâng cấp khi X đã drain

1. Dừng X đúng quy trình cephadm.
2. Nâng sang B theo MOP của hop; không xóa/recreate store trừ khi đang chạy bài store sạch riêng.
3. Khởi động X, xác nhận đúng image và daemon ổn định; CRUSH weight vẫn bằng 0.
4. Kiểm tra không có PG mới vào X do cấu hình khác hoặc thay đổi tự động.

Drain hết PG không có nghĩa mọi metadata BlueStore đều biến mất. Tuy nhiên bài này không thay hoàn toàn bài mở store chứa lịch sử object/OMAP/snapshot phong phú. Giữ thêm bài rolling/store có lịch sử trong ma trận để đánh giá rủi ro nâng phiên bản.

### 7.5. B3 — Mở weight rất nhỏ và thiết lập canary 1–2 PG

**Điều kiện trước bước này:** các PG đã drain đều khỏe, không có recovery/backfill bất thường, X chạy B và chưa nhận workload. `C` đã được chọn, có mapping và dữ liệu kiểm chứng.

Thực hiện theo thứ tự:

1. Lấy OSDMap mới, mô phỏng một `Wε > 0` nhỏ với đúng tool version. Đếm tất cả PG dự kiến có X và tất cả thay đổi ngoài phạm vi. Nếu có weight sets, phải đưa chúng vào mô hình.
2. Chọn `Wε` sao cho tập PG tự vào X không vượt phạm vi canary; lý tưởng chưa có PG ngoài C. Weight quá nhỏ có thể bị làm tròn về 0, nên đọc lại giá trị hiệu lực.
3. Trong lab, có thể dùng `norebalance` ở cửa sổ ngắn để kiểm tra map trước khi thả backfill của PG không degraded. Chỉ làm khi không có I/O di chuyển đang chạy cần chặn và đã lưu trạng thái cờ.
4. Đặt `Wε`, đọc map mới; thêm các cặp `pg-upmap-items` hợp lệ để đưa C vào X. Bảo tồn toàn bộ ngoại lệ trước đó.
5. Nếu có PG ngoài C tự vào X, giảm/chọn lại `Wε` hoặc thiết kế ngoại lệ giữ PG đó ở đích cũ hợp lệ. Kiểm tra lại toàn bộ ảnh hưởng; không chấp nhận “chỉ 1–2 PG” khi thực tế nhiều hơn.
6. Kiểm tra qua nhiều epoch rằng mapping vẫn tồn tại, không bị cleanup, X chỉ xuất hiện ở tập được phép và có đủ peer để đồng bộ.
7. Mở `norebalance` do phiên sở hữu, cho backfill canary hoàn thành. Nếu không thiết lập được giới hạn này, dừng bài canary; chưa tăng weight tiếp.

Mẫu mô phỏng CRUSH weight trên **bản sao map cục bộ**; lệnh không thay đổi cụm:

```bash
ceph osd getmap -o "$RUN_DIR/osdmap.current"
cp "$RUN_DIR/osdmap.current" "$RUN_DIR/osdmap.preview"
osdmaptool "$RUN_DIR/osdmap.preview" \
  --adjust-crush-weight "${OSD_ID:?set OSD_ID}:${W_NEXT:?set W_NEXT}" \
  --test-map-pgs-dump-all > "$RUN_DIR/placement-preview.txt"
```

`osdmaptool` hỗ trợ mô phỏng mapping và chỉnh CRUSH weight; kiểm tra `--help` của đúng build. Bản preview là bằng chứng lập kế hoạch, không bảo đảm map online sẽ giữ nguyên nếu cụm có sự kiện khác. Không nhập lại toàn bộ OSDMap cũ vào production để hoàn nguyên. [osdmaptool](https://docs.ceph.com/en/pacific/man/8/osdmaptool/).

Ví dụ lệnh áp canary, chỉ sau khi đã hoàn tất các kiểm tra trên:

```bash
ceph osd crush reweight "osd.${OSD_ID:?set OSD_ID}" "${W_EPS:?set W_EPS}"
ceph osd pg-upmap-items "${CANARY_PG:?set CANARY_PG}" \
  "${FROM_OSD:?set FROM_OSD}" "$OSD_ID"
ceph pg "$CANARY_PG" query
```

Các lệnh đổi weight và upmap không tạo thành một transaction nguyên tử. Phải đo peering và trạng thái trung gian. Nếu có PG degraded ngoài kế hoạch, `norebalance` không phải hàng rào ngăn mọi di chuyển; chuyển sang xử lý sự cố, không tiếp tục phát lệnh để cố giữ danh sách canary.

### 7.6. B4 — Verify canary trước khi tăng weight

Giữ weight ở mức hiện tại; chưa cấp PG mới. Canary phải:

- Đồng bộ xong, active+clean, up/acting đúng và không có lỗi mới.
- Chứa dữ liệu đã biết, đọc/ghi theo workload thử và verify đúng version/snapshot/range.
- Vượt deep-scrub có ngân sách; xác nhận thời điểm hoàn thành mới, không chỉ lệnh được tiếp nhận.
- Đạt p95/p99, throughput và error budget ở tải thường lẫn tải cao đã chọn.
- Có bài restart X sau khi dữ liệu đã vào để kiểm tra mở lại/lưu bền trong phạm vi thử.
- Có bài X làm primary trong phạm vi nhỏ trước khi coi vai trò primary đã được kiểm chứng. Thay affinity chỉ là đầu vào; xác nhận primary thực tế.

Nếu chỉ kiểm tra X ở vai trò replica, ghi đúng kết luận đó; chưa kết luận đã kiểm thử toàn bộ đường xử lý của primary.

### 7.7. B5 — Tăng weight theo nấc và theo số PG thực tế

Sau G4, thực hiện vòng lặp:

```text
Đề xuất weight tiếp theo → dự đoán mọi PG thay đổi → kiểm tra ngân sách
→ áp một nấc → đối chiếu mapping thực tế → chờ hội tụ
→ verify dữ liệu + QoS → quyết định giữ/tăng/dừng.
```

Lịch weight dưới đây chỉ là **ví dụ thiết kế**; `Wε` và bước tăng phải điều chỉnh theo số PG/byte thực tế, không chạy tự động theo đồng hồ:

| Giai đoạn | CRUSH weight | Điều kiện chuyển tiếp |
| --- | --- | --- |
| Sau drain/nâng | `0` | X chạy B ổn, chưa nhận PG |
| Canary | `Wε > 0`, xác định từ map | Chỉ 1–2 PG được phép vào và G4 đạt |
| Mở nhỏ | Khoảng `0.5% → 1% → 2% → 5% × W0` | Từng nấc không vượt budget PG/byte/tài nguyên; có thể cần bước nhỏ hơn |
| Mở vừa | Khoảng `10% → 20% → 35% → 50% × W0` | Ổn định qua tải đại diện, coverage và backlog đạt |
| Hoàn tất | Khoảng `65% → 80% → 100% × W0` | Từng nấc hội tụ, cấu hình/ngoại lệ được đối chiếu |

Nếu `W0=15` thì 1% tương ứng CRUSH weight 0.15; **không có nghĩa đĩa chỉ được ghi tối đa 1% dung lượng hay chỉ nhận 1% số PG chính xác**. Hai PG lớn có thể mang nhiều dữ liệu hơn hàng chục PG nhỏ.

Tại mỗi nấc phải kiểm tra lại mapping canary cũ: nếu cặp `FROM → X` đã không còn cần thiết hoặc không còn hợp lệ, đối chiếu và xử lý nó theo journal. Dọn mapping cũng có thể gây di chuyển; tính cả chi phí này trong lượt thử.

### 7.8. B6 — Khôi phục mức vận hành bình thường

Khôi phục `W0` và các giá trị đã thống nhất của override/affinity; hoàn tất kiểm chứng vai trò primary. Xử lý các entry tạm do phiên sở hữu, kiểm tra mọi PG hội tụ, đánh giá lại khi bật balancer theo trạng thái ban đầu. Bật balancer có thể khởi tạo một đợt cân bằng mới; theo dõi sau bật, không kết thúc báo cáo ngay trước bước này.

**PA2 đạt:** drain không phải dừng X sớm, canary được giới hạn đúng và không bỏ qua mapping ngoài phạm vi, từng nấc weight có bằng chứng dữ liệu/QoS, tổng thời gian và lưu lượng nằm trong ngân sách.

<a id="kiem-chung"></a>
## 8. Kiểm chứng dữ liệu và QoS

### 8.1. Ba lớp kiểm chứng bổ sung cho nhau

| Lớp | Cần kiểm tra | Không được suy rộng |
| --- | --- | --- |
| PG/replication | Active+clean, đủ replica, không inconsistent/unfound, mapping đúng | Active+clean không chứng minh byte đúng với dữ liệu gốc |
| BlueStore/deep-scrub | Lỗi checksum cục bộ, đối chiếu các replica của PG được kiểm tra | Không chứng minh nội dung ứng dụng vốn đúng nếu các bản cùng chứa sai nội dung |
| Client H0 | Hash nguồn/baseline độc lập so với byte đọc lại đúng phiên bản/phạm vi | Một GET thành công không chứng minh đã đọc mọi replica vật lý |

`deep-scrub` là tác vụ kiểm tra dữ liệu; scrub thường chủ yếu kiểm tra metadata/tính nhất quán tương ứng. Phải đưa chi phí scrub vào budget, không phát deep-scrub tất cả PG cùng lúc. [PG states](https://docs.ceph.com/en/pacific/rados/operations/pg-states/).

### 8.2. H0 cho RGW và RBD

**RGW:** dùng nguồn bất biến; tính SHA-256 trước PUT/multipart bằng streaming, lưu manifest độc lập gồm bucket/key/version hoặc immutable identity, size và hash. GET đúng version, nhận đủ byte rồi tính H1. ETag không thay SHA-256 của payload, nhất là multipart. Timeout PUT phải được phân giải để không so nhầm phiên ghi.

**RBD:** dùng image thử, writer kiểm soát và expected bytes theo offset/length. Flush/quiesce phù hợp trước checkpoint; ghim snapshot, đọc đúng range của snapshot đó. Với VM/database, thêm kiểm tra tính nhất quán ứng dụng; hash khớp không tự chứng minh database phục hồi đúng.

**Dữ liệu đã tồn tại:** hash trước nâng là `preupgrade_baseline`, chỉ chứng minh không đổi so với mốc đó. Không gọi nó là bằng chứng dữ liệu từ trước đến nay luôn đúng. Không thay manifest cũ bằng hash vừa tính từ bản đang bị nghi lỗi.

Thực hiện H0 tại các mốc: trước thay placement; sau S/đích drain đã đồng bộ; sau canary vào X; trước mở nấc tiếp theo với tập bắt buộc; sau restore. Báo cả số job chưa verify, backlog, byte coverage và các phần chỉ lấy mẫu. Theo [thiết kế H0 của dự án](https://app.notion.com/p/3ddac177517c81bb89ddef46bbf73ac9), ACK và trạng thái verified là hai việc khác nhau; MVP không sửa ACK.

### 8.3. Kiểm tra deep-scrub theo PG

```bash
ceph pg "${PG_ID:?set PG_ID}" deep-scrub
ceph pg "$PG_ID" query
rados list-inconsistent-pg "${POOL_NAME:?set POOL_NAME}"
```

Lưu timestamp yêu cầu, đợi lần deep-scrub mới hoàn thành, kiểm tra trạng thái/error/log và tập PG liên quan. Đặt timeout theo kích thước PG và tải đã đo. Không tự `repair` khi mismatch chưa biết nguồn đúng; giữ bằng chứng trước hành động sửa dữ liệu.

### 8.4. Chỉ số bắt buộc

| Nhóm | Chỉ số |
| --- | --- |
| Client RGW/RBD | p50/p95/p99 từng loại thao tác và size/concurrency; throughput/IOPS; timeout/lỗi cuối cùng; retries |
| PG | Số PG affected, remapped, degraded, misplaced; thời gian không đủ replica; thời gian peering/inactive |
| Di chuyển | Byte ra/về, tốc độ, số PG đồng thời, thời gian chờ và thời gian backfill |
| OSD/host | CPU/RAM; disk await/IOPS/throughput; DB/WAL; network của X/S/peer |
| Verify | Coverage bắt buộc/mẫu, MATCH/MISMATCH/INCONCLUSIVE, backlog/tuổi job, chi phí đọc/hash |
| Vận hành | Tổng thời gian, số mutation, số lần pause, remap ngoài kế hoạch, thời gian cờ toàn cụm tồn tại |

Không lấy trung bình các giá trị p99 của nhiều client làm p99 chung; tổng hợp histogram tương thích hoặc latency samples. Không có đủ request thì ghi chưa đủ bằng chứng, không auto-PASS.

### 8.5. Ngưỡng lab để khởi động việc đo

Ngưỡng production cần được chốt từ SLO dịch vụ. Có thể bắt đầu lab bằng chính sách minh họa dưới đây rồi hiệu chỉnh trước khi so sánh chính thức:

| Điều kiện | Chính sách thử ban đầu |
| --- | --- |
| Dữ liệu sai hoặc PG inconsistent/unfound mới | Dừng mở rộng ngay, giữ bằng chứng |
| Latency | Pause batch/nấc mới nếu p99 vượt SLO tuyệt đối hoặc tăng quá 20% baseline ở hai cửa sổ 1 phút liên tiếp |
| Throughput | Điều tra/pause nếu dưới 90% baseline với cùng offered load và chưa do thay đổi workload hợp lệ |
| Lỗi trong bài không fault injection | Mục tiêu không có lỗi I/O cuối cùng mới; retry/timeout vẫn phải được đo riêng |
| Resume | Ít nhất 5 cửa sổ 1 phút ổn định, p99 về gần baseline, ví dụ trong +10%, và các gate dữ liệu/PG vẫn đạt |
| Metrics thiếu/cũ | Không mở rộng; điều tra nguồn đo |
| Canary dwell | Giữ ít nhất một khoảng 30–60 phút có workload đủ đại diện, hoàn tất verify; tăng thời gian nếu chưa đủ mẫu |

Không dùng tỷ lệ tương đối nếu baseline quá nhỏ hoặc khác workload; luôn giữ SLO tuyệt đối. Spike peering cũng phải nằm trong báo cáo, không bỏ các phút xấu để làm kết quả đẹp hơn.

### 8.6. Điều tiết tải nền

Lấy scheduler hiệu lực từ từng OSD. Đánh giá các tham số recovery/backfill phù hợp bản Pacific/Quincy/Reef; không copy một bộ tuning qua tất cả các hop. Với mClock, profile và các giới hạn có tương tác riêng. [mClock configuration](https://docs.ceph.com/en/reef/rados/configuration/mclock-config-ref/).

Khi QoS xấu: ngừng phát batch/nấc mới, giảm H0/backup/scrub tùy chọn theo chính sách đã thử, rồi điều chỉnh ngân sách backfill phù hợp. Dừng cấp việc mới không dừng tức thì I/O đang chạy. Nếu đang thiếu replica, phải cân bằng thời gian khôi phục dự phòng với SLO, không đóng băng recovery kéo dài bằng cờ toàn cụm.

<a id="ma-tran"></a>
## 9. Ma trận thử nghiệm và xử lý sự cố

### 9.1. Ma trận chạy so sánh

| Mã | Bài thử | Bằng chứng cần có |
| --- | --- | --- |
| T0 | Baseline, không upgrade/di chuyển bổ sung | Độ biến thiên QoS và headroom |
| T1 | Rolling một OSD không drain theo MOP | Chi phí restart/peering/recovery; đối chứng, không phải phương án thứ ba mặc định triển khai |
| T2 | PA1 ở tải thường | Store giữ đến khi dừng, recovery sang S dưới chế độ cờ đã chọn, thời gian giảm replica, byte ra/về |
| T3 | PA1 ở tải cao, có verify/backup | QoS và khả năng hoàn thành trong budget |
| T4 | PA2 drain và canary ở tải thường | Drain hoàn tất, đúng 1–2 PG đầu, từng nấc weight và cleanup ngoại lệ |
| T5 | PA2 ở tải cao, có verify/backup | QoS, thời gian và giới hạn thay đổi ngoài phạm vi |
| T6 | Store có lịch sử so với store đã drain/sạch | Mở/replay, OMAP/snapshot, lỗi chuyển đổi và chức năng dịch vụ |
| T7 | Canary replica rồi primary, restart | Cả hai vai trò và phạm vi chứng minh lưu bền |
| T8 | Restore tập ưu tiên | Dữ liệu/ứng dụng phục hồi, RPO/RTO thực đo |
| T9 | Đưa cấu hình về vận hành và bật balancer | Remap sau cleanup, trạng thái ổn định cuối cùng |

Lặp lại trên cùng hop, hardware, topology, PG count, dataset, workload, ngân sách và coverage. Muốn chạy A → B nhiều lần, dựng lại baseline A hoặc khôi phục **toàn bộ lab cô lập nhất quán** theo quy trình thử; không downgrade store B để tạo giả một run A mới. Không nối bản lab clone cùng FSID/OSD identity vào cụm gốc đang hoạt động.

### 9.2. Bài lỗi có chủ đích trong lab

| Mã | Tình huống | Hành vi mong đợi |
| --- | --- | --- |
| F1 | Tải tăng vượt SLO | Ngừng cấp batch/nấc; giảm việc tùy chọn; lưu lượng đang chạy vẫn được ghi |
| F2 | Mất metrics/counter reset/mẫu quá ít | BLOCKED hoặc INCONCLUSIVE; không tự coi là tải thấp |
| F3 | Weight nhỏ nhưng có PG thứ ba ngoài canary | Phát hiện trước khi thả backfill nếu có thể; không vượt G4 |
| F4 | Upmap bị cleanup hoặc operator đổi mapping | Phát hiện drift; không ghi đè thay đổi ngoài ownership |
| F5 | Norebalance làm PG khỏe chờ backfill | Nhận diện đúng, không nhầm lệnh upmap thành công với dữ liệu đã chuyển |
| F6 | PG degraded khác xuất hiện khi norebalance đang bật | Không coi cờ là chặn mọi recovery; ưu tiên sự cố và kiểm tra toàn cụm |
| F7 | Spare/peer down khi đang thế chỗ | Dừng nâng mới, khôi phục dự phòng; đo ảnh hưởng availability |
| F8 | X mới crash khi chỉ có canary | Giữ phạm vi nhỏ, bảo toàn log, phục hồi từ replica tốt theo cơ chế Ceph |
| F9 | H0 mismatch hoặc manifest sai version | Giữ bằng chứng, phân loại nguyên nhân, chặn mở rộng |
| F10 | Hết cửa sổ chạy hoặc controller restart | Giữ trạng thái an toàn đã đạt, reconcile từ map hiện tại, không phát mutation trùng |

Thử mất thêm peer khi PA1 đã dừng X có thể làm PG không đủ `min_size`; chỉ thực hiện trên lab/data được phép thử mất khả dụng. Không hạ `min_size` để làm bài test “không gián đoạn”.

### 9.3. Nhánh xử lý khi không đạt

| Sự cố | Hành động đầu tiên | Hướng tiếp theo |
| --- | --- | --- |
| QoS xấu, dữ liệu còn tốt | Dừng mở rộng và giảm việc tùy chọn | Điều chỉnh budget; không cần restore chỉ vì latency cao |
| PG chưa đủ replica | Không dừng/nâng thêm OSD | Khôi phục dự phòng, sửa nguyên nhân backfill/recovery |
| Spare đầy/không hợp lệ | Không ép mapping | Chọn đích hợp lệ hoặc hoãn; đánh giá lại phương án |
| B không mở được store/crash | Giữ cô lập khi còn đủ replica; lưu log/store | Fix-forward hoặc thay OSD theo runbook; không mặc định chạy A trên store đã bị B sửa |
| Hash không khớp | Giữ manifest/version/range và log; hạn chế ghi phạm vi liên quan nếu cần | Kiểm tra nguồn tham chiếu, đối chiếu replica/backup, chọn nguồn đúng trước repair |
| Không còn bản dữ liệu tin cậy | Chặn mở rộng, xác định phạm vi khách hàng | Restore điểm tốt của tập đã backup, đo RPO/RTO |
| Hết giờ nhưng cluster còn khỏe | Giữ mức weight/mapping đã verify nếu chính sách cho phép | Kết thúc ca có journal và người tiếp nhận; không trả tất cả weight/PG vì muốn “về bình thường” ngay |

**Rollback phải phân biệt:** hoàn nguyên một thay đổi cấu hình/mapping sau đối chiếu không phải rollback dữ liệu hay downgrade Ceph. Tạo lại OSD sạch chạy A chỉ được xét nếu feature floor, mixed-version và cơ chế triển khai vẫn hỗ trợ và đã thử; không dùng làm đường cứu mặc định.

<a id="lua-chon"></a>
## 10. So sánh và chọn phương án production

### 10.1. Bảng đánh đổi cần xác nhận bằng lab

| Tiêu chí | PA1 — Upmap/spare, giữ store bằng dừng nguồn | PA2 — Drain weight=0, mở lại từng nấc |
| --- | --- | --- |
| Cách rút dữ liệu | Chỉ định PG sang spare hợp lệ | CRUSH phân bố lại theo weight; có thể bổ sung mapping mục tiêu |
| X trong lúc copy ra | Dừng để giữ store cũ ở biến thể chính | Tiếp tục chạy đến khi drain xong |
| Cửa sổ giảm dự phòng | Phải đo trên toàn bộ PG của X khi dừng sớm | Có thể chờ đủ replica ở đích trước khi dừng X; vẫn phải đo trạng thái chuyển tiếp |
| Dữ liệu cũ tại thời điểm nâng | Có tại thời điểm dừng; khi chạy lại có thể bị cleanup | Các PG cũ có thể đã bị dọn trong drain |
| Dữ liệu copy khi trả về | Có thể dùng lại một phần, không được giả định | Có khả năng cần backfill đáng kể sau drain |
| Kiểm soát PG vào sau nâng | Trả từng entry/batch đã quản lý | Weight nhỏ kết hợp upmap và kiểm tra toàn bộ mapping |
| Giới hạn cứng 1–2 PG | Phải kiểm tra mọi mapping/drift | Không được suy từ weight; phải chứng minh canary thực tế |
| Phạm vi cờ | Thử norebalance trong giai đoạn cô lập, noout cho X | Cho phép backfill khi drain/trả; có thể cần cửa sổ kiểm tra map ngắn |
| Độ phức tạp | Quản lý nhiều ngoại lệ, store cũ, cửa sổ thiếu replica | Quản lý các nấc weight, remap ngoài kế hoạch và hiệu lực upmap |
| Nguy cơ QoS | Primary chuyển tải, recovery khi nguồn dừng, trả PG | Di chuyển ra/về, CRUSH remap, backfill mỗi nấc |

Không mặc định PA1 giảm dữ liệu di chuyển hoặc PA2 luôn ít ảnh hưởng hơn. Cả hai phải báo các PG/host ngoài canary bị ảnh hưởng tài nguyên.

### 10.2. Kiểm tra ngân sách thời gian

Ước lượng thô cho một chiều:

```text
T_copy ≈ bytes_to_move / effective_backfill_bytes_per_second
T_total = T_prepare + T_out + T_upgrade + T_in + T_verify + T_wait
```

Ví dụ toán học: 10 TiB ở tốc độ hiệu dụng 100 MiB/s cần khoảng **29,1 giờ cho một chiều**; hai chiều copy đầy đủ khoảng 58,3 giờ, chưa cộng verify và chờ. Đây không phải benchmark của cụm.

Vì vậy nếu cửa sổ gián đoạn chấp nhận là 3 giờ ban đêm, phải tách rõ phần nào chạy trước/sau dưới SLO, phần nào nằm trong cửa sổ, và trạng thái an toàn khi kết thúc ca. Không hứa drain rồi trả lại OSD 10–12 TB trong 3 giờ nếu chưa đo được tốc độ và thời gian thực tế.

### 10.3. Điều kiện loại trước khi chấm ưu nhược

Loại phương án cho phạm vi production đang xét nếu có một trong các điểm sau:

- Dữ liệu mismatch/inconsistent chưa tìm được nguyên nhân và chưa có cách phục hồi đã thử.
- Không giới hạn được PG canary hoặc không phát hiện được mapping drift.
- Cửa sổ giảm replica, lỗi client hoặc vi phạm SLO vượt ngân sách.
- Không hoàn thành coverage bắt buộc; metrics thiếu nhưng vẫn cần tuyên bố PASS.
- Không có cách xử lý an toàn khi lỗi, hết cửa sổ hoặc controller/operator bị gián đoạn.
- Quản lý cờ/mapping không thể khép lại; phụ thuộc giữ cờ toàn cụm kéo dài ngoài mức vận hành chấp nhận.
- Chưa đạt bài store có lịch sử cần thiết cho hop, dù bài OSD đã drain chạy tốt.

Không dùng một con số điểm tổng cao để vượt qua lỗi an toàn dữ liệu.

### 10.4. Cách chọn một phương án

1. Loại phương án không đạt các gate bắt buộc.
2. Trong các phương án đạt, ưu tiên ít vi phạm SLO và ít thời gian giảm dự phòng hơn.
3. So tổng thời gian hoàn tất, byte ra/về, tài nguyên spare và coverage tương đương.
4. So khả năng thao tác lặp lại, phát hiện drift, điều kiện dừng và công sức vận hành.
5. Chọn **một phương án cho phạm vi đã thử**, ghi giới hạn hardware/pool/version/workload; lập MOP và pilot.

Nếu cả hai đạt và lợi ích đo được tương đương, ưu tiên quy trình dễ lặp lại, ít trạng thái đặc biệt và không phải dừng nguồn sớm để giữ store. PA1 chỉ nên được ưu tiên khi lợi ích kiểm chứng store hoặc chi phí thực tế đủ rõ và cửa sổ giảm dự phòng được chấp nhận. Đây là tiêu chí quyết định đề xuất, chưa phải kết luận chọn PA2 trước lab.

Nếu cả hai không đạt, **hoãn triển khai hai phương án**, dùng kết quả rolling đối chứng để đánh giá lại mục tiêu hoặc thiết kế. Không buộc chọn một phương án không đạt chỉ vì đã lập kế hoạch thử hai phương án.

<a id="production"></a>
## 11. Kế hoạch triển khai production

### 11.1. Giai đoạn P0 — Chuẩn bị từ kết quả lab

- Chốt phương án thắng và phạm vi áp dụng; điền toàn bộ ngưỡng, timeout, weight/batch budget bằng số đo.
- Inventory lại cụm production: raw/usable của khoảng 24 PB, phân bố PG/byte/tải, phiên bản, device class, failure domain và spare thực tế. Không suy rằng 10–20 spare bất kỳ đều dùng được cho mọi OSD.
- Chốt hop/image digest, hỗ trợ phiên bản, thứ tự daemon, client và feature floor.
- Xác định nhóm khách hàng/dữ liệu ưu tiên được backup riêng trên cụm 100 TB; kiểm tra manifest, retention và restore. Không dùng cùng phần dung lượng đó để tính spare PG của production.
- Chuẩn bị MOP có owner, lệnh cụ thể, trạng thái mong đợi, timeout và nhánh xử lý; chạy lại trên map/topology đại diện.

### 11.2. Giai đoạn P1 — Pilot một OSD ít ảnh hưởng

1. Chọn X bằng dữ liệu 24–72 giờ hoặc chu kỳ dài hơn cần thiết; thẩm định lại ngay trước chạy.
2. Chuẩn bị đích/backup/baseline, bắt đầu trong cửa sổ được phép.
3. Thực hiện đúng phương án đã chọn, một OSD, ghi đầy đủ journal.
4. Sau nâng, chỉ mở 1–2 PG canary đã xác minh phạm vi; chạy kiểm chứng và role test.
5. Mở rộng trong phạm vi một OSD theo gate, không dùng thành công ở lab để bỏ bước production canary.
6. Quan sát qua ít nhất một chu kỳ tải quan trọng theo chính sách đã chốt, rồi mới đánh giá pilot đạt.

### 11.3. Giai đoạn P2 — Staggered theo từng OSD

Sau pilot đạt, tiếp tục **một OSD mỗi đợt**. Mỗi đợt chọn lại ứng viên và peer/spare theo trạng thái mới; không dùng một thứ tự cố định cho toàn bộ vài trăm node nếu tải/topology thay đổi.

Chưa chạy đồng thời các OSD cùng PG/failure domain hay dùng chung tài nguyên nghẽn. Nếu muốn mở rộng concurrency, đó là pha further work cần ma trận kiểm thử bổ sung, không tự suy từ thành công một OSD.

### 11.4. Giai đoạn P3 — Khép lại từng hop

- Hoàn tất các daemon còn lại theo thứ tự và MOP của hop, gồm RGW và rbd-mirror nếu có sử dụng.
- Xác nhận version thực chạy, health, coverage, backup/restore và không còn thay đổi tạm bỏ quên.
- Chỉ nâng feature floor hoặc bật tính năng định dạng mới khi đúng điều kiện của release/MOP; không dùng mixed-version như trạng thái ổn định vô thời hạn.
- Tổng kết hop rồi mới bắt đầu hop tiếp theo. Nâng xong một OSD không có nghĩa nâng xong cụm.

### 11.5. Quy tắc dọn cấu hình cuối phiên

Với mỗi weight, affinity, flag, scheduler setting hoặc upmap entry:

1. Đọc trạng thái hiện tại, so với lần cuối phiên đã áp.
2. Nếu người khác đã thay đổi, đánh dấu conflict và đối chiếu, không ghi đè.
3. Khôi phục/xử lý đúng thay đổi của phiên, kiểm tra ảnh hưởng placement trước khi thực hiện.
4. Theo dõi sau khôi phục balancer/affinity và chỉ đóng phiên khi mọi chuyển tiếp cần thiết đã được giải thích.

Snapshot OSDMap/CRUSH trước phiên là bằng chứng so sánh; không phải gói rollback an toàn để nạp đè lên cụm đã phát sinh ghi và epoch mới.

<a id="dau-ra"></a>
## 12. Lộ trình, đầu ra và mẫu biên bản

### 12.1. Lộ trình tham khảo khoảng hai tháng

| Giai đoạn | Việc chính | Đầu ra |
| --- | --- | --- |
| Tuần 1 | Inventory, chuẩn bị topology/spare, dữ liệu có lịch sử, baseline | Bảng chọn OSD, SLO lab, manifest và map ban đầu |
| Tuần 2 | Thử cơ chế PA1: affinity, norebalance, source stop, upmap và cleanup | Bằng chứng cửa sổ giảm replica và store cũ |
| Tuần 3 | Thử PA2: drain, weight nhỏ, canary, tăng từng nấc | Bảng weight–PG thực tế và dữ liệu/QoS |
| Tuần 4–5 | Lặp so sánh, tải cao, lỗi có chủ đích, restore và rolling đối chứng | Báo cáo so sánh và giới hạn từng phương án |
| Tuần 6 | Chọn phương án, chốt MOP và ngưỡng production | Quyết định có bằng chứng, runbook và nhánh sự cố |
| Tuần 7 | Pilot một OSD production nếu đủ gate | Biên bản pilot và quyết định mở rộng |
| Tuần 8 | Hoàn thiện báo cáo, triển khai staggered trong phạm vi cho phép | Bài học, số liệu và kế hoạch các đợt tiếp theo |

Đây là lịch tổ chức công việc đề xuất; không cam kết hoàn thành tất cả hop của cụm 24 PB trong 8 tuần. Tiến độ thực phụ thuộc copy/verify, số OSD, SLO và cửa sổ vận hành.

### 12.2. Mẫu biên bản một run

```yaml
run_id: <id>
method: <PA1_or_PA2>
variant: <retained_store_or_other_explicit_variant>
fsid: <cluster_fsid>
source_osd: <X>
spares: []
hop: <A_to_B>
image_source_digest: <digest>
image_target_digest: <digest>
weight_control: <crush_or_override>
initial_crush_weight: null
initial_override_reweight: null
initial_primary_affinity: null
pgs_affected_initially: []
canary_pgs: []
workload_definition: <path_or_id>
baseline_window: <start_end>
slo_policy: <version>
mapping_journal: <path_or_id>
weight_or_batch_history: <path_or_id>
unexpected_mapping_changes: []
data_moved_out_bytes: null
data_moved_in_bytes: null
degraded_pg_seconds: null
max_simultaneously_degraded_pgs: null
client_unavailable_seconds: null
client_p99_by_phase: <path_or_id>
final_io_error_rate_by_phase: <path_or_id>
verification_manifest: <path_or_id>
verification_coverage: <mandatory_sampled_pending>
old_store_opened_by_target_version: <yes_no_unknown>
old_pg_cleanup_observed: <description>
backup_restore_evidence: <path_or_id>
temporary_config_remaining: []
result: <PASS_FAIL_INCONCLUSIVE>
reason: <evidence_based_reason>
```

`degraded_pg_seconds` là diện tích theo thời gian của số PG degraded, cần kèm số PG tối đa và thời gian kéo dài nhất; không dùng nó thay thông tin PG nào bị ảnh hưởng.

### 12.3. Checklist quyết định sau lab

- [ ] PA1 và PA2 được so ở cùng điều kiện, có baseline và rolling đối chứng.
- [ ] Đã đo tải PG trong cửa sổ đại diện; có lý do chọn X/S/C từ note tiêu chí.
- [ ] Đã phân biệt CRUSH weight, override reweight, primary affinity và cờ rebalance.
- [ ] PA1 có số đo thời gian giảm replica, hành vi giữ/cleanup store và byte copy trở lại.
- [ ] PA2 chứng minh đúng 1–2 PG trong canary; không suy giới hạn từ weight.
- [ ] Đã kiểm tra cả replica và primary trong phạm vi nhỏ, cùng bài mở store có lịch sử.
- [ ] Có coverage H0/deep-scrub và bài restore; không bỏ qua job chưa verify.
- [ ] Có ma trận sự cố và cách kết thúc khi hết giờ; không dựa vào downgrade store.
- [ ] Có kế hoạch dọn cấu hình/mapping theo ownership và quan sát sau bật balancer.
- [ ] Một phương án được chọn bằng kết quả, hoặc ghi rõ chưa phương án nào đủ điều kiện.

<a id="nguon"></a>
## 13. Nguồn và phạm vi xác minh

### 13.1. Nguồn dự án đã đọc

- [PRJ GD2 — Tổng hợp kế hoạch nâng cấp Ceph](https://app.notion.com/p/3dcac177517c814cafc2d4db50e481b0).
- [V2 — Kế hoạch nâng cấp Ceph: spare, QoS và H0](https://app.notion.com/p/3ddac177517c81708502f5c76c17ac5d).
- [Tiêu chí chọn OSD — tải PG trong khoảng thời gian đại diện](https://app.notion.com/p/3d7ac177517c8086a3eed25414b34cb9).
- [01 — Phương án nâng cấp OSD](https://app.notion.com/p/3dcac177517c81799242f24aa4ca3dea).
- [08 — Note: quyết định và nội dung cần kiểm chứng](https://app.notion.com/p/3dcac177517c81949cf7eb78262d210d).
- [07 — Backup 100 TB và phương án phục hồi](https://app.notion.com/p/3dcac177517c818fa4eac8c10e509c79).
- [V2 — Checklist, ma trận lab và tiêu chí nghiệm thu](https://app.notion.com/p/3ddac177517c81fabd21e8739cdef5c2).
- [V2 — Kiểm chứng dữ liệu H0 tại client](https://app.notion.com/p/3ddac177517c81bb89ddef46bbf73ac9).

### 13.2. Tài liệu Ceph và mã nguồn đối chiếu

- [Pacific — Using pg-upmap](https://docs.ceph.com/en/pacific/rados/operations/upmap/): ngoại lệ placement, client compatibility và balancer.
- [Pacific — CRUSH Maps](https://docs.ceph.com/en/pacific/rados/operations/crush-map/): weight, topology, failure domain và primary affinity.
- [Pacific — Control commands](https://docs.ceph.com/en/pacific/rados/operations/control/): override reweight và truy vấn trạng thái.
- [Pacific — Health checks](https://docs.ceph.com/en/pacific/rados/operations/health-checks/): flags, nearfull/backfillfull và phạm vi OSD flags.
- [Pacific — PG states](https://docs.ceph.com/en/pacific/rados/operations/pg-states/): active/clean, peering, degraded, backfill và deep-scrub.
- [Pacific — Adding/removing OSDs](https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/): quan sát di chuyển, CRUSH weight=0 và phân biệt dừng/xóa.
- [Pacific — osdmaptool](https://docs.ceph.com/en/pacific/man/8/osdmaptool/): mô phỏng placement và CRUSH weight.
- [Reef — Cephadm upgrade](https://docs.ceph.com/en/reef/cephadm/upgrade/): thứ tự daemon và staggered upgrade.
- [Reef — mClock](https://docs.ceph.com/en/reef/rados/configuration/mclock-config-ref/): scheduler và điều tiết tác vụ nền.
- [PrimaryLogPG.cc v16.2.5](https://github.com/ceph/ceph/blob/v16.2.5/src/osd/PrimaryLogPG.cc), [v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/PrimaryLogPG.cc), [v17.2.7](https://github.com/ceph/ceph/blob/v17.2.7/src/osd/PrimaryLogPG.cc), [v18.2.7](https://github.com/ceph/ceph/blob/v18.2.7/src/osd/PrimaryLogPG.cc): điều kiện `norebalance` với backfill của PG không degraded.
- [OSDMap.cc v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/OSDMap.cc): áp dụng/kiểm tra/cleanup upmap theo weight và CRUSH.
- [OSDMonitor.cc v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/mon/OSDMonitor.cc): xử lý danh sách `pg-upmap-items`.
- [PeeringState.cc v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/PeeringState.cc): stray, deletion và trạng thái PG.

**Phạm vi xác minh khi soạn:** đã đọc nội dung Notion và đối chiếu tài liệu/mã nguồn upstream cho các cơ chế trọng tâm. Các ngưỡng, lịch thử, thứ tự thao tác chi tiết và tiêu chí lựa chọn là thiết kế đề xuất của kế hoạch. Chưa chạy lệnh Ceph, chưa thử source build tùy biến và chưa có benchmark của lab/production để xác nhận phương án thắng.
