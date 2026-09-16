# Tổng hợp phương án nâng cấp Ceph — ưu tiên tách cụm

**Dự án:** PRJ GD2 upgrade ceph  
**Ngày tổng hợp:** 11/09/2026  
**Phạm vi:** Ceph core, RBD và RGW; lựa chọn kiến trúc, quy trình tổng quan, chi phí, QoS và phương án phục hồi.

Tài liệu tổng hợp từ [trang dự án Notion][n1], [ghi chú phương án][n2], [Upgrade risk][n3], [checklist][n4] và [tiêu chí chọn OSD][n5], có đối chiếu tài liệu Ceph. Phần tách cụm được ưu tiên theo định hướng hiện tại của dự án, thay cho ưu tiên rolling/OSD dự phòng trong một số ghi chú cũ. Các đánh giá và quy trình đề xuất dưới đây chưa phải kết quả kiểm thử production.

## Mục lục

1. [Định hướng lựa chọn](#dinh-huong)
2. [Phân loại các phương án](#phan-loai)
3. [Phương án ưu tiên: tách cụm từ hạ tầng hiện có](#tach-cum)
4. [Ưu, nhược điểm và lưu ý của các phương án còn lại](#phuong-an-khac)
5. [Áp dụng RBD mirroring và RGW multisite vào từng phương án](#mirroring-multisite)
6. [Chi phí và kiểm soát QoS](#chi-phi-qos)
7. [Fix-forward, failback và giới hạn rollback](#phuc-hoi)
8. [Kiểm thử, điều kiện thực hiện và lưu ý chung](#kiem-thu)
9. [Số liệu cần thu thập để chọn cụm](#so-lieu)
10. [Nguồn tham khảo](#nguon)

<a id="dinh-huong"></a>
## 1. Định hướng lựa chọn

**Ưu tiên thẩm định phương án tách một phần hạ tầng hiện có thành cụm B độc lập, dựng B đồng nhất phiên bản đích rồi chuyển workload từ cụm A sang từng đợt.** Cách này có thể giảm rủi ro do nâng trực tiếp phần mềm và định dạng lưu trữ trên cụm đang phục vụ khách hàng. A được giữ nguyên phiên bản trong giai đoạn dựng và kiểm chứng B; chỉ chuyển dịch vụ khi B đạt các điều kiện đã định.

**Trade-off lớn:** để có node dựng B, phải dồn dữ liệu khỏi nhóm node đó. Rebalance/backfill tiêu tốn thời gian, disk I/O và network; các OSD còn lại phải chứa thêm dữ liệu và gánh phần tải của node đã rút. Sau đó, đồng bộ A sang B tạo thêm một lượt đọc/ghi. Tiết kiệm phần cứng mua mới không đồng nghĩa chi phí vận hành hoặc ảnh hưởng QoS thấp.

Tách cụm chỉ được ưu tiên khi đã chứng minh đủ dung lượng, hiệu năng, failure domain và đường phục hồi. Nếu không đáp ứng, **rolling tại chỗ kết hợp canary và chia đợt** vẫn là phương án đối chứng cần đo, vì thường di chuyển ít dữ liệu hơn.

Không gắn nhãn “an toàn 99%” nếu chưa có cơ sở định lượng. Mức bảo vệ phải thể hiện qua phạm vi dữ liệu được bảo vệ, RPO, RTO, lỗi đã diễn tập, kết quả kiểm tra toàn vẹn và điều kiện dừng. RPO là mức mất dữ liệu mới có thể chấp nhận khi phục hồi; RTO là thời gian khôi phục dịch vụ mục tiêu.

<a id="phan-loai"></a>
## 2. Phân loại các phương án

Rolling, canary và staggered mô tả các khía cạnh khác nhau: rolling là nâng luân phiên; canary là thử trên phạm vi nhỏ; staggered là chia thành những đợt có điểm kiểm tra. Có thể kết hợp cả ba. Chuyển primary và tăng replica là biện pháp bổ sung, không tự tạo một kiến trúc nâng cấp độc lập.

| Mã | Phương án | Bản chất và phạm vi |
| --- | --- | --- |
| **PA1** | **Tách cụm từ hạ tầng hiện có — ưu tiên** | Rút sạch nhóm node, dựng B với FSID riêng, chuyển workload A sang B |
| PA2 | Cụm B độc lập trên hạ tầng khác | Dùng phần cứng mới, thuê hoặc dự phòng sẵn; tránh bước rút node khỏi A |
| PA3 | Rolling tại chỗ từng OSD/daemon | Giữ store và placement, cập nhật phần mềm rồi restart lần lượt |
| PA4 | Rolling theo nhóm chọn bằng PG/QoS | Mở rộng PA3 bằng nhóm OSD được kiểm tra an toàn cùng lúc |
| PA5 | Chuyển primary trước khi restart | Bổ sung cho rolling; thay vai trò primary trước khi nâng OSD |
| PA6 | OSD dự phòng thế chỗ | Chuyển PG sang spare, nâng/reprovision OSD cũ, có thể đưa dữ liệu trở lại |
| PA7 | Drain OSD sang dung lượng hiện có | Rút PG khỏi OSD cần nâng, sử dụng các OSD còn lại thay vì thêm spare |
| PA8 | Nhóm OSD/pool mới trong cùng cụm | Chuyển workload sang vùng lưu trữ mới nhưng vẫn dùng chung MON/MGR/FSID |
| PA9 | Tăng replica tạm thời | Bổ sung bảo vệ cho replicated pool trước khi nâng; không áp dụng tương tự cho EC |
| PA10 | Nâng trong cửa sổ dừng dịch vụ | Bổ sung để so sánh: chấp nhận downtime, kiểm soát ghi và phục hồi theo kế hoạch |

PA3–PA9 tổng hợp từ [ghi chú Notion][n2]. PA1 theo định hướng mới của dự án; PA2 và PA10 bổ sung để so sánh chi phí hạ tầng và downtime.

<a id="tach-cum"></a>
## 3. Phương án ưu tiên: tách cụm từ hạ tầng hiện có

### 3.1. Mô hình và lợi ích về phiên bản

**Bản chất của PA1 là rút hạ tầng khỏi A → xóa store cũ trên các thiết bị đã drain an toàn → cài mới B ở phiên bản đích → migrate dữ liệu/workload sang B.** Đây là cách đạt mục tiêu chuyển phiên bản bằng cụm mới. “Tách cụm” trong tài liệu là tách tài nguyên để dựng một cụm độc lập; không phải chia nguyên trạng dữ liệu/OSD của A thành hai cụm.

Cụm A vẫn giữ dữ liệu và phục vụ trong lúc dựng, kiểm thử B. Chỉ tái khởi tạo thiết bị của nhóm node đã rút sạch và đạt kiểm tra an toàn; không xóa dữ liệu đang phục vụ trên A. Nếu B còn chỉ chứa dữ liệu test và gặp lỗi, có thể dựng lại B rồi test lại.

Cụm A giữ phiên bản hiện tại. Một nhóm node được rút dữ liệu và gỡ khỏi A đúng quy trình, sau đó tạo cụm B có **FSID, MON, MGR, OSD và cấu hình riêng**. B có thể được cài mới đồng nhất phiên bản đích. Đĩa/OSD đang chứa PG của A không được coi là dữ liệu của B chỉ bằng cách đổi MON hoặc FSID.

Ceph mô tả việc rút OSD theo hai bước: chuyển hết PG rồi loại bỏ OSD không còn PG. Host được gỡ sau khi các daemon đã được loại bỏ. Dựng B là quá trình bootstrap một cụm mới. [Rút OSD][c4], [rút host][c3], [bootstrap][c5].

MON mới của B không quản lý OSD cũ của A. Đây là sự tách biệt ở cấp cụm, khác với dựng một pool hoặc nhóm OSD mới trong cùng FSID. Tuy vậy, **giao thức đồng bộ A–B và client truy cập B vẫn phải tương thích**; cài mới B không phải cách bỏ qua các điều kiện này.

Nếu chuyển hết workload rồi loại bỏ A, có thể hoàn thành mục tiêu chuyển sang phiên bản mới bằng migration thay vì nâng tại chỗ toàn bộ A. Nếu giữ A làm dự phòng hoặc tiếp tục phục vụ workload chưa chuyển, A vẫn cần kế hoạch nâng riêng.

### 3.2. Chọn cụm nào ít tải hơn để tách trước

Nếu có nhiều cụm production, đánh giá từng cụm trước khi chọn nhóm node bên trong. “Ít tải” phải xét theo tỷ lệ tài nguyên còn dư và ảnh hưởng sau khi rút node, không chỉ IOPS tuyệt đối hoặc CPU thấp ở một thời điểm.

| Nhóm | Tiêu chí chọn cụm nguồn | Bằng chứng cần có |
| --- | --- | --- |
| Điều kiện bắt buộc | PG khỏe, đủ replica/shard; không có lỗi dữ liệu hoặc sự cố nền chưa xử lý | Health, PG state, crash, scrub, tình trạng đĩa và đồng bộ thời gian |
| Điều kiện bắt buộc | A còn đủ dung lượng sau khi rút node | Tính theo từng CRUSH rule/device class và OSD nhận dữ liệu, có phần dư cho tăng trưởng và sự cố |
| Điều kiện bắt buộc | A vẫn duy trì failure domain và MON quorum | Sơ đồ rack/host, rule, vị trí MON/MGR và các daemon dịch vụ |
| Ưu tiên cao | Tải thấp trong khoảng đo đại diện | IOPS, MiB/s, p95/p99, CPU, disk latency và network có cả giờ cao điểm, batch job, backup |
| Ưu tiên cao | Các OSD còn lại còn sức nhận dữ liệu và tải | Mô hình tải sau drain, benchmark có backfill, mức sử dụng tài nguyên cao nhất |
| Ưu tiên | Workload ít ràng buộc, có thể chuyển theo nhóm | Danh sách image/bucket và ứng dụng phụ thuộc; cửa sổ dừng ghi được thống nhất |
| Ưu tiên | Có đường phục hồi đã kiểm chứng | Backup đọc được, restore/failback đã diễn tập và đo thời gian |
| Ưu tiên | Đủ đại diện cho đợt mở rộng | Cùng dạng pool, phiên bản/client, loại đĩa và workload với các cụm tiếp theo |

**Quy tắc lựa chọn đề xuất:** loại cụm không đạt điều kiện bắt buộc; trong số còn lại, ưu tiên cụm có tải đỉnh thấp so với năng lực, nhiều phần dư sau drain và phạm vi workload dễ chuyển. Cụm rất nhỏ hoặc gần như rỗng có thể phù hợp thử thao tác nhưng chưa chứng minh an toàn cho cụm lớn đang bận.

Chưa có số liệu production trong nguồn Notion để chỉ định một cụm cụ thể. Kết quả lựa chọn phải dựa vào bảng đo thực tế, không suy từ cấu hình lab ba node.

### 3.3. Chọn nhóm node/OSD bên trong cụm đã chọn

Tiêu chí trong [ghi chú chọn OSD][n5] được mở rộng cho việc rút node:

- Ưu tiên nhóm có ít dữ liệu phải di chuyển, ít primary PG chịu tải cao và ít PG nhạy latency; số PG chỉ là một chỉ báo phụ.
- Kiểm tra tải trên các OSD sẽ nhận dữ liệu hoặc tiếp tục giữ replica, không chỉ tải trên node bị rút.
- Xét toàn bộ pool liên quan: RBD data/metadata, RGW data/index/metadata và các pool hệ thống. Một node ít tải S3 vẫn có thể phục vụ metadata quan trọng.
- Giữ đủ failure domain ở cả A và B. Với `size=3` và rule theo host, mỗi cụm cần bố trí replica trên ba host khác nhau; còn phải dự trù khả năng phục hồi khi thêm host/đĩa hỏng.
- Lập kế hoạch chuyển MON/MGR/RGW khỏi nhóm node rút, giữ quorum và năng lực phục vụ. Tính cả DB/WAL, NIC, switch hoặc nguồn điện dùng chung.
- Rút theo đợt nhỏ, kiểm tra lại sau mỗi đợt. Kết quả kiểm tra an toàn là theo trạng thái hiện tại và tập OSD thực tế dự kiến dừng.

CRUSH rule quyết định vị trí và failure domain; khác host/rack chưa tự chứng minh cả nhóm OSD có thể dừng cùng lúc. [CRUSH][c6].

### 3.4. Tính dung lượng và phần dư trước khi quyết định

Gọi `C` là tổng dung lượng raw thuộc phạm vi đang xét, `R` là raw đã sử dụng và `f` là tỷ lệ dung lượng raw sẽ rút. Ước lượng trung bình sau khi dữ liệu hội tụ:

```text
Dung lượng raw còn lại của A = C × (1 − f)
Tỷ lệ sử dụng dự kiến của A = R / [C × (1 − f)]
```

Đây là phép tính sơ bộ, giả sử chính sách replica/EC không đổi. Phải tính lại riêng theo pool/device class/rule; trung bình toàn cụm không bảo đảm từng OSD còn chỗ backfill. Kiểm tra các ngưỡng `nearfull/backfillfull/full` thực tế và phần dư khi có thêm lỗi host/đĩa trong lúc drain.

**Ví dụ giả định:** tổng raw 100 TiB, đang dùng 40 TiB; rút 20 TiB để dựng B. A còn 80 TiB và mức dùng trung bình thành 50%. B có 20 TiB raw nên không thể giữ thêm toàn bộ bộ dữ liệu đang chiếm 40 TiB raw trên A với cùng chính sách bảo vệ. B chỉ nhận phạm vi vừa sức chứa và hiệu năng của nó.

Nếu muốn A và B cùng giữ toàn bộ dữ liệu, tổng raw sử dụng cần xấp xỉ gấp đôi mức hiện tại khi giữ cùng cơ chế bảo vệ, cộng metadata, tăng trưởng, snapshot và phần dư. Nếu chuyển dần rồi giải phóng bản trên A, yêu cầu dung lượng thấp hơn nhưng mất dần khả năng quay lại bản nguồn.

**Không giảm `size` hoặc `min_size` chỉ để làm cho phép tính tách cụm vừa dung lượng.** Đây là thay đổi mức bảo vệ riêng, đi ngược mục tiêu giảm rủi ro nếu chưa có đánh giá độc lập. Khi rút OSD, Ceph cũng yêu cầu chú ý các ngưỡng đầy vì dung lượng được dồn lên phần còn lại. [Rút OSD và dung lượng][c7].

### 3.5. Quy trình đề xuất và điểm kiểm tra

| Bước | Thực hiện | Điều kiện hoàn thành / xử lý nếu không đạt |
| --- | --- | --- |
| 1. Chốt phạm vi | Chọn cụm A, nhóm node rút, image/bucket/ứng dụng chuyển đợt đầu; chốt RPO/RTO | Có inventory, số liệu tải, bản phục hồi và tính toán phần dư |
| 2. Chuẩn bị A | Bố trí daemon và quorum; kiểm soát placement, autoscaler/balancer, lịch job nền; đo baseline | A khỏe và có đủ tài nguyên trong kịch bản rút node |
| 3. Drain nhóm node | Di chuyển PG có giới hạn tải, theo dõi cả phía nhận | Hết PG cần phục vụ trên OSD rút, các PG liên quan hội tụ đủ replica/shard; kiểm tra an toàn đạt |
| 4. Tạo B | Gỡ node khỏi A, kiểm soát spec tự triển khai OSD; tái khởi tạo thiết bị đã xác nhận an toàn; bootstrap B | B có danh tính và quản lý riêng, topology đúng, daemon đồng nhất phiên bản dự kiến |
| 5. Kiểm chứng B | Nạp dữ liệu test đại diện, chạy tải và diễn tập chuyển dữ liệu/khôi phục; sau khi đạt mới đồng bộ phạm vi dữ liệu thật đã chọn | Đạt tính toàn vẹn, hiệu năng, metadata và tương thích hai chiều cần thiết |
| 6. Cutover có kế hoạch | Dừng/flush ghi trong phạm vi chuyển, chờ đồng bộ cuối; chặn bên cũ tiếp tục ghi rồi chuyển client | Chỉ một bên có quyền ghi theo kế hoạch; ứng dụng chạy trên B và đối chiếu dữ liệu đạt |
| 7. Quan sát và giữ đường về | Giữ bản nguồn/backup theo chính sách; bảo vệ các ghi mới phát sinh trên B | Failback hoặc restore đã diễn tập với dữ liệu phát sinh sau cutover |
| 8. Mở rộng | Chuyển nhóm workload tiếp theo; chỉ giải phóng nguồn sau khi đủ điều kiện | Tính lại dung lượng, tải và phạm vi có thể quay lại ở từng đợt |

`ok-to-stop` kiểm tra khả năng dừng mà vẫn duy trì khả dụng tức thời; nó không chứng minh OSD đã được rút hết dữ liệu. `safe-to-destroy` kiểm tra điều kiện loại bỏ mà không giảm độ bền dữ liệu, không phải lệnh xóa. Hai kiểm tra không thay thế việc xem trạng thái PG và mapping. [Ceph command API][c8].

Trong PA1, mặc định giữ A nguyên phiên bản khi dựng B. Nếu B là cụm đã có dữ liệu và phải nâng tại chỗ, để A phục vụ trong khi nâng B, kiểm chứng B xong mới cutover; sau đó mới nâng A. Các cụm không cùng được nâng tại một thời điểm.

### 3.6. Vì sao có thể an toàn hơn, và đánh đổi ở đâu

| Lợi ích có điều kiện | Đánh đổi / giới hạn |
| --- | --- |
| B được cài đồng nhất phiên bản; A chưa thay đổi phần mềm | A đã giảm tài nguyên sau khi rút node; backfill có thể kéo dài và làm tăng latency |
| Có thể nạp dữ liệu test và chạy tải trên B trước khi nhận khách hàng | Cần dữ liệu và tải test đại diện cho dung lượng, số object/image, metadata, client và tải đỉnh dự kiến; thêm thời gian kiểm thử trước khi chuyển thật |
| Nếu B lỗi trước cutover, vẫn giữ workload ở A | Tải đồng bộ và hạ tầng dùng chung vẫn có thể ảnh hưởng A |
| Có đường chuyển dịch vụ về A nếu giữ nguồn và đồng bộ đúng | Sau khi B nhận ghi, quay lại phải bảo toàn các ghi mới; không chỉ đổi endpoint |
| Tái sử dụng phần cứng thay vì mua thêm toàn bộ | Tăng công vận hành, thời gian migration và khoảng thời gian hai cụm cần cùng tồn tại |
| Tách vòng đời phần mềm và control plane | Nếu dùng chung rack, điện hoặc mạng, rủi ro hạ tầng tương quan vẫn còn |

**PA1 giảm một nhóm rủi ro nâng cấp tại chỗ, đồng thời tạo rủi ro do di chuyển dữ liệu và giảm năng lực A.** Lựa chọn cuối cùng cần dựa vào đo lường hai nhóm này. Không coi đây là phép tách một replica ra thành một cụm backup hoàn chỉnh.

Kiểm thử B không cần giới hạn ở cụm rỗng: có thể tạo image/bucket test, nạp dữ liệu, dùng fio/Warp mô phỏng tải dự kiến và kiểm tra dữ liệu trước khi nhận workload thật. Diễn tập đường chuyển A–B bằng phạm vi test riêng, gồm cả cutover và bảo vệ ghi mới khi quay lại; sau đó chuyển workload thật theo đợt nhỏ. B cài mới không trải qua việc daemon mới mở trực tiếp store OSD cũ; phần cần kiểm chứng là B dưới tải cùng đường chuyển dữ liệu, metadata và client.

Khi muốn lấy thêm node từ A để mở rộng B, phải chuyển và nghiệm thu workload trước, quản lý vòng đời bản nguồn rồi tính lại từng đợt. Với replication còn hoạt động, thao tác xóa trên nguồn có thể lan sang đích; việc kết thúc đồng bộ và giải phóng dữ liệu phải có quy trình riêng, gồm cả metadata RGW. Không coi dung lượng xóa logic là dung lượng vật lý đã thu hồi ngay.

<a id="phuong-an-khac"></a>
## 4. Ưu, nhược điểm và lưu ý của các phương án còn lại

### PA2 — Cụm B độc lập trên hạ tầng khác

- **Cách làm:** dựng hoặc dùng cụm B riêng trên phần cứng mới, thuê hoặc dự phòng; kiểm chứng rồi chuyển workload. Nếu B cần nâng, nâng B trước khi nhận khách hàng.
- **Ưu điểm:** giữ nguyên năng lực A trong giai đoạn chuẩn bị, không phát sinh drain node khỏi A; tách được thay đổi phần mềm khỏi nơi đang phục vụ.
- **Nhược điểm / QoS:** chi phí hạ tầng và vận hành hai cụm lớn; đồng bộ vẫn tạo tải đọc trên A và ghi trên B, cộng băng thông giữa cụm.
- **Lưu ý:** B phải đủ sức phục vụ phạm vi cam kết; kiểm chứng client, đồng bộ ngược và điều phối quyền ghi. Failback về A là chuyển dịch vụ, không phải downgrade B.

**Phù hợp:** có ngân sách hoặc đã có DR đủ năng lực; cần giảm thêm rủi ro do co nhỏ A của PA1. Cơ chế liên cụm xem [RBD mirroring][c11] và [RGW multisite][c12].

### PA3 — Rolling tại chỗ từng OSD/daemon

- **Cách làm:** giữ đĩa, OSD ID và placement; nâng phần mềm theo phương thức triển khai, restart lần lượt, kiểm tra rồi tiếp tục. Với cephadm, thay container image; với cụm package, theo quy trình package tương ứng.
- **Ưu điểm:** thường ít dữ liệu phải di chuyển nhất, không cần cụm thứ hai; chi phí hạ tầng thấp, quy trình orchestration sẵn có.
- **Nhược điểm / QoS:** PG liên quan có thể peering và giảm số replica online tạm thời; daemon mới có thể phải xử lý store cũ. Có giai đoạn MON/OSD hoặc các OSD khác phiên bản.
- **Lưu ý:** chọn OSD ít ảnh hưởng, kiểm tra an toàn ngay trước restart; chờ phục hồi ổn định giữa các lượt. Nếu dừng ngắn và lịch sử thay đổi còn đủ, thường chỉ đồng bộ phần thiếu; không mặc định luôn tránh được full backfill.

**Phù hợp:** phần cứng khỏe, thời gian restart dự đoán được, đường nâng đã kiểm chứng. Đây là baseline để đo chi phí tăng thêm của PA1/PA6/PA7. [Cephadm upgrade][c1], [peering và recovery][c10].

### PA4 — Rolling theo nhóm được chọn bằng PG/QoS

- **Cách làm:** chọn tập OSD có thể nghỉ cùng lúc dựa trên PG, failure domain, tải và tài nguyên dùng chung; kiểm tra an toàn của cả tập trước khi thực hiện.
- **Ưu điểm:** giảm tổng thời gian nâng cụm lớn so với tuyệt đối một OSD mỗi lượt.
- **Nhược điểm / QoS:** nhiều PG có thể bị ảnh hưởng đồng thời; giảm dung lượng phục vụ và tăng recovery theo đợt; công xây dựng/kiểm chứng bộ điều phối cao hơn.
- **Lưu ý:** từng OSD riêng lẻ vượt `ok-to-stop` không có nghĩa cả tập đều an toàn. Nhóm ở các host khác nhau vẫn có thể cùng thuộc acting set của PG hoặc dùng chung DB/NIC.

**Phù hợp:** sau khi PA3 đã có số liệu ổn định. Staggered/giới hạn phạm vi upgrade không tự thay thế thuật toán chọn nhóm an toàn; không giả định mọi lệnh restart theo service đều có cùng kiểm tra như luồng upgrade. [Ceph command API][c8], [OSD service][c4].

### PA5 — Chuyển primary trước khi restart

- **Cách làm:** điều chỉnh cơ chế chọn primary, chẳng hạn `primary-affinity`, chờ trạng thái ổn định rồi nâng OSD; ghi lại cấu hình ban đầu để khôi phục.
- **Ưu điểm:** có thể tránh mất đột ngột một primary đang chịu tải cao và chuyển phần tải đó có kiểm soát.
- **Nhược điểm / QoS:** việc đổi primary tự tạo thêm chuyển trạng thái PG; tải chuyển sang OSD khác. OSD cũ vẫn có thể giữ replica và xử lý ghi replication.
- **Lưu ý:** không tạo thêm bản sao, không rút dữ liệu khỏi OSD, không cách ly phiên bản. Đây là biện pháp cần benchmark với đúng workload; không mặc định tốt hơn PA3.

**Phù hợp:** đã xác định primary là yếu tố gây ảnh hưởng và các OSD nhận vai còn dư tài nguyên. [Primary affinity][c6].

### PA6 — OSD dự phòng thế chỗ

- **Cách làm:** thêm spare OSD/nhóm OSD; chuyển các PG khỏi OSD A khi A còn chạy; chờ đủ bản sao rồi nâng A. Có thể chuyển dữ liệu về A sau kiểm chứng hoặc dùng OSD mới làm thay thế lâu dài.
- **Ưu điểm:** sau khi chuyển hoàn tất, A có thể dừng lâu mà PG vẫn đủ replica online trên các OSD khác. Phù hợp bảo trì đĩa/host hoặc restart khó dự đoán.
- **Nhược điểm / QoS:** cần spare và backfill. Nếu chuyển đi rồi về, có thể phải chép lại gần toàn bộ phần dữ liệu đã di chuyển; không mặc định lượt về chỉ là delta.
- **Lưu ý:** không có cặp active–standby OSD clone 1–1 tự chuyển tức thì. `out` không chỉ định toàn bộ dữ liệu sang đúng một spare; nếu dùng `pg-upmap`, cần mapping hợp lệ, tương thích client và kiểm soát xung đột balancer.

**Phù hợp:** cần duy trì mức dư thừa trong thời gian OSD nghỉ dài. Khi A bản mới nhận PG trở lại, vẫn phải phối hợp với OSD bản cũ trong cùng cụm; PA6 không giải quyết riêng rủi ro tương thích MON/OSD. [PG-upmap][c9], [di chuyển OSD][c7].

**Hai biến thể cần phân biệt trong lab:** drain khi A còn chạy có thể dẫn tới dọn các bản PG cũ trên A; dừng A trước để giữ store thì có giai đoạn giảm replica online, vì spare trống chưa thể tiếp quản ngay. Chọn biến thể theo mục tiêu test, không coi OSD đã drain là bản backup của store cũ. [Ghi chú dự án][n1].

### PA7 — Drain OSD sang các OSD hiện có rồi nâng

- **Cách làm:** rút dữ liệu khỏi OSD cần nâng sang phần còn lại của cụm, nâng OSD rồi đưa trở lại theo kế hoạch placement.
- **Ưu điểm:** không cần thêm spare riêng; OSD được nâng sau khi đã ngừng chịu trách nhiệm phục vụ PG.
- **Nhược điểm / QoS:** phần còn lại vừa nhận thêm dữ liệu vừa gánh tải client; di chuyển dữ liệu thường xảy ra cả lúc rút và đưa lại. Phụ thuộc mạnh vào phần dư của cụm.
- **Lưu ý:** kiểm tra đầy theo từng OSD/rule, không chỉ tổng raw còn trống. Drain không tự biến store thành một cài đặt mới và không tạo điểm phục hồi độc lập.

**Phù hợp:** bảo trì cần nghỉ dài, cụm dư tài nguyên; phải đo so với PA3 trước khi dùng cho hàng loạt OSD. [Thêm/rút OSD][c7].

### PA8 — Nhóm OSD/pool mới trong cùng cụm

- **Cách làm:** tạo vùng lưu trữ/pool mới, chuyển image/bucket/workload bằng quy trình migration phù hợp.
- **Ưu điểm:** chia phạm vi chuyển dữ liệu dễ hơn; có thể tạo nhóm OSD có đặc tính và phiên bản đồng nhất để kiểm chứng.
- **Nhược điểm / QoS:** vẫn chung MON/MGR/FSID và có thể chung network; migration tạo tải cả phía nguồn lẫn đích. Lỗi hoặc thay đổi ở control plane vẫn có phạm vi toàn cụm.
- **Lưu ý:** tạo pool hoặc đổi cấu hình placement không tự chuyển đầy đủ một ứng dụng sang vùng mới. RBD/RGW có metadata và quan hệ phụ thuộc riêng; RGW index và object vẫn nằm trong RADOS.

**Phù hợp:** đổi lớp lưu trữ, thay phần cứng hoặc migration có phạm vi; không dùng PA8 để chứng minh cách ly phiên bản như hai cụm độc lập. [RGW data layout][c13], [ghi chú phương án][n2].

### PA9 — Tăng replica tạm thời cho pool quan trọng

- **Cách làm:** ví dụ tăng replicated pool từ `size=3` lên 4, chờ đồng bộ đủ rồi nâng luân phiên; giảm về mức cũ sau nghiệm thu bằng một thay đổi riêng.
- **Ưu điểm:** tăng số bản sao còn online khi một OSD dừng, nếu placement và phần cứng thực sự đáp ứng.
- **Nhược điểm / QoS:** riêng dữ liệu replicated tăng lý tưởng khoảng 33% raw khi đi từ ba lên bốn bản, chưa tính overhead; thêm ghi replication và traffic. Cần backfill khi tăng và xử lý dữ liệu dư khi giảm.
- **Lưu ý:** cần đủ failure domain cho bốn bản. Không đổi EC `k/m` theo phép tương tự; không nhầm `size` của pool với giới hạn trong CRUSH rule. Bản sao thêm trong cùng cụm vẫn chịu lỗi logic/phần mềm dùng chung.

**Phù hợp:** biện pháp tăng dư thừa cho phạm vi hẹp khi đủ tài nguyên. Không loại bỏ peering, không thay backup, không bảo đảm QoS tốt hơn. [Replication của pool][c14].

### PA10 — Nâng trong cửa sổ dừng dịch vụ

- **Cách làm:** thống nhất thời gian ngừng workload, chốt bản phục hồi nhất quán, nâng theo trình tự được hỗ trợ và kiểm chứng trước khi mở lại.
- **Ưu điểm:** dễ kiểm soát các ghi phát sinh và giảm cạnh tranh với I/O khách hàng trong thời gian thay đổi.
- **Nhược điểm / QoS:** có downtime chủ động; thời gian khởi động, chuyển đổi store và phục hồi có thể kéo dài. Không đáp ứng yêu cầu live upgrade.
- **Lưu ý:** dừng I/O không ngăn mọi lỗi định dạng hoặc phần mềm. Snapshot trong chính cụm hoặc image container cũ không đủ làm kế hoạch phục hồi toàn hệ thống.

**Phù hợp:** workload chấp nhận downtime hoặc trường hợp hạn chế tài nguyên; là lựa chọn đánh đổi khả dụng, không tự có xác suất an toàn cao hơn. Kế hoạch vẫn cần fix-forward và restore đã kiểm chứng. [Giới hạn downgrade][c2], [tính nhất quán snapshot RBD][c17].

<a id="mirroring-multisite"></a>
## 5. Áp dụng RBD mirroring và RGW multisite vào từng phương án

Hai cơ chế này hỗ trợ sao chép và chuyển dữ liệu/dịch vụ. Chúng không thay thế trực tiếp OSD, không sao chép toàn bộ MON store và không biến hai nhóm OSD chung FSID thành hai cụm độc lập.

| Phương án | RBD mirroring | RGW multisite | Khuyến nghị áp dụng |
| --- | --- | --- | --- |
| **PA1 — Tách cụm** | Phù hợp để đưa image đã chọn sang B | Phù hợp để đưa dữ liệu bucket sang zone trên B | Ưu tiên đánh giá; phải so với export/copy có kiểm soát nếu migration một lần |
| PA2 — Cụm B trên hạ tầng khác | Phù hợp cho DR và chuyển workload | Phù hợp cho DR và chuyển endpoint/zone | Giá trị cao nếu đã có B đủ năng lực |
| PA3 — Rolling từng OSD | Tùy chọn bảo vệ image quan trọng sang cụm khác | Tùy chọn bảo vệ workload S3 sang cụm khác | Không bắt buộc cho cơ chế rolling; chỉ thêm khi lợi ích DR tương xứng chi phí |
| PA4 — Rolling theo nhóm | Tương tự PA3 | Tương tự PA3 | Không dùng DR để bỏ qua kiểm tra an toàn cả nhóm OSD |
| PA5 — Chuyển primary | Chỉ là lớp DR bên ngoài | Chỉ là lớp DR bên ngoài | Không cần để đổi primary PG |
| PA6 — OSD spare | Không dùng để clone/thế chỗ OSD | Không dùng để clone/thế chỗ OSD | Nếu thêm, đó là một lớp bảo vệ liên cụm riêng |
| PA7 — Drain OSD | Không cần cho thao tác drain | Không cần cho thao tác drain | Có thể bảo vệ khách hàng quan trọng ở cụm khác trước đợt bảo trì |
| PA8 — Pool/OSD mới cùng cụm | Không cần dùng liên cụm chỉ để đổi pool | Không cần mặc định dựng multisite cho đổi pool | Dùng quy trình migration thích hợp; chỉ có DR độc lập khi đích thực sự ở cụm khác |
| PA9 — Tăng replica | Không cần để tăng `size` | Không cần để tăng `size` | Mirror/multisite và replica tăng thêm xử lý các lớp rủi ro khác nhau |
| PA10 — Cửa sổ dừng | Có thể giảm lượng dữ liệu phải chuyển ở thời điểm dừng | Có thể chuẩn bị đích trước thời điểm dừng | Vẫn phải giữ bản phục hồi và hoàn tất đồng bộ trước cutover |

### 5.1. RBD: chọn phạm vi và chi phí

RBD mirroring là bất đồng bộ và có thể bật trên các image được chọn. Journal mode thêm bước ghi journal trước khi cập nhật image, làm tăng tải ghi và có thể tăng latency; snapshot mode chuyển delta theo các điểm chụp, tạo tải theo đợt và độ trễ phụ thuộc lịch chụp cùng thời gian đồng bộ. Không đặt một tỷ lệ giảm hiệu năng cố định khi chưa đo. [RBD mirroring][c11].

Lập danh sách đầy đủ image thuộc ứng dụng/tenant, gồm các volume phụ thuộc nhau; không coi nhãn tenant tự động tạo phạm vi bảo vệ. Nếu chọn theo namespace, xác minh hỗ trợ của đúng phiên bản. Chuyển VM/OpenStack cần điều phối phía compute/ứng dụng, thông tin kết nối và quyền truy cập; RBD mirroring không tự chuyển cả dịch vụ.

Với cutover có kế hoạch, dừng và flush ghi, xác nhận image đích đã đạt điểm đồng bộ cuối, demote/promote đúng quy trình và chặn nguồn tiếp tục ghi. Snapshot/mirror crash-consistent chưa tự bảo đảm database hoặc nhiều volume nhất quán với nhau; cần phối hợp ứng dụng. [Snapshot RBD][c17].

### 5.2. RGW: chọn bucket, metadata và chi phí

Sync policy cho phép kiểm soát đồng bộ ở mức bucket giữa các zone; cơ chế này có từ Octopus. Phạm vi dữ liệu bucket và phạm vi metadata của realm/zonegroup phải được đánh giá riêng. Liệt kê bucket, user/tenant, policy, quyền, versioning và các cấu hình ứng dụng cần thiết; không mặc định bật multisite là mọi thứ đã đủ để tiếp quản. [Multisite sync policy][c18].

Chi phí gồm đọc object và log trên A, truyền mạng, ghi object/index/metadata trên B và xử lý đồng bộ tồn đọng. Nhiều object nhỏ hoặc bucket index lớn có thể gây tải metadata đáng kể dù MiB/s không cao. Đây là điểm cần đo trên workload thực tế.

Trước chuyển dịch vụ, kiểm tra cả data sync và metadata sync; điều phối quyền ghi, endpoint/LB và thay đổi metadata master nếu có. Các tính năng mới phụ thuộc mọi zone phải chờ tất cả zone hỗ trợ. [RGW multisite][c12].

### 5.3. Giới hạn chung khi dùng theo từng khách hàng

- Cụm B nhỏ chỉ bảo vệ phạm vi đã sao chép và đủ sức phục vụ; không bảo vệ mặc nhiên các khách hàng còn lại trên A.
- Một tenant có thể dùng nhiều image/bucket và chia sẻ metadata, dịch vụ hoặc PG với tenant khác. Chọn workload không đồng nghĩa đã cô lập node vật lý.
- Bất đồng bộ không tự bảo đảm RPO bằng 0. RPO mục tiêu tại cutover có kế hoạch cần chứng minh qua việc dừng ghi và đồng bộ cuối; các ghi sau đó cần tiếp tục được bảo vệ.
- Sau cutover, phải kiểm chứng chiều đồng bộ ngược cần cho failback, kể cả phiên bản và feature. Nếu không làm được, phương án quay lại phải đổi thành restore/copy được diễn tập với RPO/RTO tương ứng.
- Giữ một điểm phục hồi không bị cập nhật cùng replication. Mirror có thể tiếp nhận cả thay đổi sai hợp lệ ở cấp ứng dụng; nó không thay thế backup giữ lịch sử.
- Nếu không cần replication lâu dài, export/import hoặc copy theo ứng dụng có thể giảm độ phức tạp kiến trúc, nhưng phải kiểm tra đầy đủ dữ liệu, metadata, downtime và lần ghi cuối. SAN/NAS tạm có thể làm đích backup, không tự tạo thành cụm Ceph tiếp quản dịch vụ.

<a id="chi-phi-qos"></a>
## 6. Chi phí và kiểm soát QoS

### 6.1. So sánh chi phí tương đối

Các mức dưới đây là **đánh giá định tính để lập kế hoạch**, chưa phải benchmark hay báo giá. QoS ở đây là chất lượng dịch vụ khách hàng nhận được trong quá trình nâng: latency, throughput, lỗi và thời gian gián đoạn.

| Phương án | Phần cứng / dung lượng bổ sung | Di chuyển dữ liệu | Áp lực QoS chính | Công và thời gian |
| --- | --- | --- | --- | --- |
| **PA1 — Tách cụm** | Có thể không mua mới; cần đủ chỗ cho hai bản trong phạm vi bảo vệ | Cao: drain trong A, sau đó copy A–B; thêm các đợt mở rộng | **A ít OSD hơn, tải dồn lên phần còn lại; backfill và sync kéo dài** | Cao; nhiều bước và hai cụm cùng vận hành |
| PA2 — B trên hạ tầng khác | Cao nếu chưa có cụm dự phòng | Copy A–B, không cần drain để lấy node | Tải đọc A, ghi B, đường truyền | Cao nhưng tránh được bước co nhỏ A |
| PA3 — Rolling từng OSD | Thấp, vẫn cần phần dư vận hành | Thường thấp; có thể tăng khi OSD nghỉ lâu | Peering, replica tạm offline, catch-up | Từng bước ngắn; tổng thời gian tùy số daemon |
| PA4 — Rolling theo nhóm | Tương tự PA3 | Tương tự PA3 nhưng tập trung theo đợt | Nhiều PG/tài nguyên chịu tác động đồng thời | Có thể nhanh hơn, cần chọn và kiểm tra nhóm |
| PA5 — Chuyển primary | Thấp | Thường không cần đổi nơi chứa replica | Dồn xử lý primary sang OSD khác; PG đổi trạng thái | Công mapping, theo dõi và hoàn nguyên cấu hình |
| PA6 — OSD spare | Cần spare và chỗ chứa PG chuyển sang | Cao nếu chuyển toàn bộ, có thể thêm lượt chuyển về | Đọc/ghi backfill ở cả nguồn, spare và replica liên quan | Lâu theo lượng dữ liệu và giới hạn tải |
| PA7 — Drain vào OSD còn lại | Không nhất thiết mua thêm; cần nhiều phần dư | Cao với OSD đầy | Tăng mức đầy và I/O trên OSD đang phục vụ | Lâu; nhạy với thiếu dung lượng |
| PA8 — Pool/OSD mới cùng cụm | Cần chỗ cho dữ liệu chuyển và bản giữ lại | Copy workload giữa vùng lưu trữ | Tranh chấp tài nguyên, vẫn chung control plane | Công migration và quản lý ứng dụng |
| PA9 — Replica 3 lên 4 | Raw cho phần replicated tăng khoảng 33% | Tạo thêm replica rồi thu hồi khi giảm lại | Backfill, tải ghi và chỗ chứa bổ sung | Chờ hội tụ trước và sau thay đổi |
| PA10 — Cửa sổ dừng | Tùy backup/đích phục hồi | Tùy cơ chế nâng và restore | Downtime đã lên lịch; vẫn có tải recovery | Chi phí gián đoạn và thời gian phục hồi |

Chi phí tổng nên tính cả giờ vận hành, dung lượng giữ bản cũ, network, tài nguyên mất khỏi A, kiểm thử và downtime. Với PA1, số node tái sử dụng là khoản tiết kiệm đầu tư; thời gian A chạy với ít tài nguyên hơn là khoản chi phí phải chấp nhận.

### 6.2. Đo và chốt ngân sách ảnh hưởng

| Lớp đo | Chỉ số cần theo dõi | Quyết định phục vụ |
| --- | --- | --- |
| Ứng dụng / client | p95/p99 và latency cao nhất; IOPS/MiB/s; timeout, lỗi, retry; tách read/write và thao tác S3 | Khách hàng còn đạt SLO không |
| Ceph | Slow ops; PG inactive, degraded, misplaced, inconsistent; tốc độ và lượng recovery/backfill còn lại | Đợt hiện tại có hội tụ và giữ mức bảo vệ không |
| Từng host/OSD | Disk latency, queue, CPU/RAM, OSD latency, network và mức đầy cao nhất | Tài nguyên nào đang giới hạn; OSD nhận có bị quá tải không |
| Đồng bộ A–B | Backlog, lỗi sync, độ trễ theo image/bucket và tiến độ dữ liệu/metadata | Có thể đạt điểm đồng bộ cuối và RPO mục tiêu không |

Phải đo baseline trong khoảng đại diện có giờ cao điểm, batch job và backup. Không chỉ dùng trung bình toàn cụm: một nhóm PG hoặc khách hàng có thể bị chậm dù số tổng vẫn đẹp.

Chốt trước ba loại ngưỡng: SLO tuyệt đối của khách hàng, mức suy giảm được phép so với baseline và khoảng thời gian được phép vượt ngưỡng. Ví dụ **đề xuất để thử trong lab**, p99 tăng trên 20% trong 5 phút thì không mở đợt mới; ngưỡng production phải điều chỉnh theo hợp đồng và phép đo. Đây không phải giá trị mặc định hoặc mức an toàn do Ceph bảo đảm.

**RPO/RTO là mục tiêu phục hồi; QoS là chất lượng lúc đang phục vụ.** Không thay mục tiêu “không mất dữ liệu” bằng một biểu đồ latency đẹp, và không suy ra xác suất an toàn 99% từ việc 99% I/O đạt latency mục tiêu.

### 6.3. Điều tiết đúng cơ chế, đúng phiên bản

Với Pacific dùng WPQ, các tham số như `osd_max_backfills`, `osd_recovery_max_active*`, priority và sleep ảnh hưởng lượng công việc hoặc lịch xử lý. Giới hạn số backfill đồng thời không phải trần MiB/s của cả cụm. [Cấu hình OSD Pacific][c15].

Với Reef dùng mClock, cần phân biệt lớp client, recovery và background best-effort; backfill thuộc lớp best-effort. Vì vậy, profile ưu tiên recovery không đồng nghĩa mọi tác vụ rebalance sẽ nhanh hơn. mClock vô hiệu hóa các sleep liên quan; đổi một số giới hạn recovery/backfill cần `osd_mclock_override_recovery_settings`. Phải kiểm tra giá trị đang có hiệu lực trên daemon. [mClock][c16].

Đề xuất vận hành:

- Kiểm tra scheduler thực tế trước khi dùng cấu hình; trong giai đoạn hỗn hợp phiên bản, không giả định mọi OSD đang áp dụng cùng hành vi.
- Bắt đầu với cấu hình mặc định đã kiểm chứng, đợt nhỏ và ít luồng migration. Chỉ điều chỉnh khi phép đo chỉ ra nút thắt.
- Không áp một tỷ lệ “20% network cho rebalance” rồi coi đó là bảo đảm latency. Disk/CPU/metadata cũng có thể nghẽn.
- Điều tiết cả workload copy/mirror ở phía client hoặc daemon đồng bộ. I/O migration đi qua giao diện client có thể cạnh tranh trong cùng lớp với I/O ứng dụng.
- Với PA1, ban đầu tách giai đoạn drain và sync, tránh chồng nhiều đợt mở rộng. Khi đã đo đủ phần dư mới cân nhắc chạy đồng thời.
- Khi vượt ngưỡng QoS, dừng mở đợt mới và giảm công việc di chuyển có kế hoạch. Nếu có OSD hỏng thật, đánh giá lại ưu tiên khôi phục replica; không giữ recovery bị chặn vô thời hạn để làm đẹp latency.

### 6.4. Ước lượng thời gian

Với một giai đoạn truyền dữ liệu, dùng phép tính sơ bộ:

```text
Thời gian truyền tối thiểu ≈ lượng byte thực sự phải truyền / tốc độ hữu hiệu đo được
```

Phải cộng thời gian scan, xử lý object/metadata, catch-up các ghi mới, kiểm tra và cutover. Tốc độ hữu hiệu phải được đo trong giới hạn QoS, không lấy tốc độ danh nghĩa của NIC. Lượng dữ liệu PG di chuyển nội cụm và lượng dữ liệu logic copy sang B không phải cùng một đại lượng.

Ví dụ giả định: 10 TiB truyền liên tục ở 100 MiB/s mất khoảng 29,1 giờ chỉ cho phần truyền. Nhiều object nhỏ, ghi mới liên tục hoặc giờ cao điểm có thể làm lâu hơn. Nếu tốc độ xử lý delta không theo kịp tốc độ phát sinh, backlog sẽ không hội tụ; phải tăng năng lực, giảm phạm vi hoặc bố trí thời gian dừng ghi.

<a id="phuc-hoi"></a>
## 7. Fix-forward, failback và giới hạn rollback

### 7.1. Cách diễn đạt đúng khi trình phương án

**Các phương án nâng tại chỗ như PA3–PA9, và PA10 nếu vẫn nâng trên store hiện có, phải được lập kế hoạch theo hướng fix-forward; không dựa vào giả định đổi lại image/package cũ là rollback được.** Khi daemon mới đã cập nhật định dạng lưu trữ, metadata hoặc yêu cầu feature, khả năng chạy lại bản cũ có thể không còn. Tài liệu nâng Reef nêu rõ không hỗ trợ downgrade về Pacific hoặc Quincy. [Nâng cấp Reef][c2].

“Fix-forward” là xử lý để hệ thống chạy đúng ở phiên bản hiện tại hoặc bản vá phù hợp: khắc phục cấu hình, dùng bản vá đã kiểm chứng, phục hồi daemon/OSD bằng quy trình hợp lệ. Nó **không có nghĩa tiếp tục nâng tất cả daemon khi đang có lỗi chưa hiểu rõ**. Có thể dừng đợt tiếp theo, điều tra và ổn định hệ thống trước.

PA1 và PA2 cũng không làm cho downgrade của cụm B trở nên an toàn. Điểm khác là có thể giữ dịch vụ ở A hoặc chuyển lại A trong những điều kiện đã kiểm chứng, trong khi B được sửa hoặc dựng lại. Nếu nguồn đã bị giải phóng hoặc thiếu các ghi mới, lợi thế này giảm hoặc mất.

| Khái niệm | Việc thực sự làm | Điều kiện / giới hạn |
| --- | --- | --- |
| Pause nâng cấp | Ngừng thay đổi thêm daemon | Không đảo ngược daemon/store đã nâng |
| Fix-forward | Sửa lỗi, triển khai bản phù hợp, khôi phục thành phần | Cần hiểu nguyên nhân và giữ dữ liệu hợp lệ |
| Failback dịch vụ | Chuyển workload từ B về A | A đủ năng lực, có dữ liệu cần thiết và chỉ một phía được ghi |
| Restore | Khôi phục từ điểm backup được giữ | Có thể mất các ghi sau điểm backup và mất thời gian restore |
| Downgrade phần mềm | Chạy phiên bản cũ trên trạng thái sau nâng | Không được coi là đường phục hồi mặc định |

### 7.2. Xử lý lo ngại MON/OSD khác phiên bản

Với rolling theo đường nâng được hỗ trợ, giai đoạn daemon khác phiên bản là trạng thái chuyển tiếp được quy trình nâng tính đến. Ví dụ cephadm nâng MGR, MON trước OSD; sau OSD còn các loại daemon khác, tùy cụm. OSD không phải luôn là loại daemon cuối cùng. [Cephadm upgrade][c1].

Phải chốt cặp phiên bản và thứ tự hợp lệ, kiểm tra client/feature và đặt mốc hoàn tất. Tuy nhiên, cảnh báo daemon cũ kéo dài không phải một cơ chế hết hạn bắt buộc nâng tiếp bất chấp lỗi. Ceph có cảnh báo `DAEMON_OLD_VERSION` sau khoảng trễ cấu hình được; tài liệu cũng đề cập trường hợp quá trình nâng được pause lâu. [Health checks][c22].

RBD mirroring hoặc RGW multisite không xóa trạng thái hỗn hợp phiên bản **bên trong một cụm đang rolling**. Chúng cung cấp dữ liệu ở cụm khác để hỗ trợ chuyển dịch vụ. Với PA1 cài mới B, A và B có control plane riêng; tương thích cần giải quyết ở đường đồng bộ và client thay vì để MON của một cụm quản lý OSD thuộc hai cụm.

### 7.3. Những bản sao không đủ để gọi là rollback

Theo [ghi chú dự án][n2], cần tách rõ:

- Snapshot một MON không đưa cả cụm về quá khứ; MON trong quorum còn phải thống nhất trạng thái đã được chấp nhận.
- Bản sao một OSD không đại diện cho bộ dữ liệu toàn cụm. Với BlueStore, điểm sao lưu phải nhất quán giữa data, DB và WAL; không ép một bản PG cũ trở thành nguồn đúng khi đã có ghi mới.
- Image/config RGW không bao gồm toàn bộ object, index và metadata trong các pool RADOS. [Bố trí dữ liệu RGW][c13].
- Giữ OSD cũ sau khi drain không bảo đảm vẫn còn bộ PG nguyên vẹn để hoàn tác; PG có thể đã được di chuyển và bản cũ bị thu hồi.

Nếu cần restore toàn hệ thống, phải xác định phạm vi backup, điểm nhất quán, khóa/credential phụ thuộc và thứ tự phục hồi ứng dụng. Một bản backup chỉ được tính vào kế hoạch khi đã đọc thử và diễn tập restore.

### 7.4. Ma trận phục hồi cho phương án tách cụm

| Thời điểm / lỗi | Hướng xử lý | Điều kiện quan trọng |
| --- | --- | --- |
| Drain A làm QoS xấu | Không rút thêm node; giảm công việc có kế hoạch, ổn định placement và tải | A còn đủ dung lượng, replica/shard và failure domain |
| B lỗi trước cutover | Giữ khách hàng trên A; sửa hoặc dựng lại B | A vẫn đủ năng lực phục vụ sau khi rút node |
| B lỗi sau khi đã nhận ghi mới | Fencing bên lỗi; chọn failback hoặc restore theo dữ liệu thực tế | Không quay về bản A cũ rồi bỏ qua các ghi đã được xác nhận trên B |
| Mất đường đồng bộ | Dừng mở rộng/cutover chưa thực hiện; xác định dữ liệu đang lệch | Có kế hoạch backlog, RPO và quyền ghi rõ ràng |
| Thay đổi sai đã lan qua replication | Dùng điểm phục hồi giữ lịch sử và kiểm chứng dữ liệu | Bản mirror mới nhất có thể không phải bản đúng cần phục hồi |
| Đã xóa bản nguồn để lấy thêm node | Dùng đường phục hồi còn lại đã được nghiệm thu | Không tiếp tục mô tả là có failback đầy đủ về A |

<a id="kiem-thu"></a>
## 8. Kiểm thử, điều kiện thực hiện và lưu ý chung

### 8.1. Chốt phiên bản và lịch sử store

Trước khi viết runbook lệnh, xác nhận phiên bản thực tế của từng daemon/client, image digest, cách build, kernel/OS và lịch sử nâng của cụm. Với custom image, nhãn phiên bản chưa đủ chứng minh mã nguồn hoặc thư viện trùng bản upstream. [Checklist][n4], [ghi chú dự án][n2].

Hai điểm từ Notion cần đưa vào kiểm tra theo điều kiện:

- Lỗi chuyển đổi OMAP trước Pacific trong các bản đến 16.2.6 có điều kiện kích hoạt liên quan repair/quick-fix và được sửa ở 16.2.7. Phân biệt cụm cài mới Pacific với cụm đã nâng từ đời trước; không suy rằng mọi cụm 16.2.5 đều đã hỏng dữ liệu. [Pacific release notes][c21].
- Release notes Reef hiện cảnh báo không nên nâng trực tiếp Pacific → Reef do vấn đề nhận diện feature bit và cảnh báo hoàn tất OSD sớm. Tài liệu không khẳng định sự cố tương tác gây hỏng dữ liệu đã được biết đến từ riêng vấn đề này. Vì vậy cần thẩm định đường đi qua phiên bản trung gian. [Reef known issues][c2].

Chức năng staggered của cephadm được bổ sung từ 16.2.11 và 17.2.1. Với 16.2.5, không mặc định dùng được các tùy chọn mới ngay từ đầu; cần xử lý bước MGR theo hướng dẫn tương ứng. [Cephadm upgrade][c1].

Các nhánh Pacific/Quincy/Reef trong tài liệu phản ánh phạm vi dự án, **chưa phải phê duyệt phiên bản đích cho production**. Khi triển khai phải rà lại release notes, vòng đời hỗ trợ, bản vá, client và feature của đúng bản chọn; không bật feature chỉ bản mới hiểu trước khi đạt điều kiện tương thích.

### 8.2. Bảo đảm dữ liệu bằng nhiều lớp kiểm tra

BlueStore có checksum cho dữ liệu và metadata. PG `active+clean` cho biết trạng thái hoạt động và số bản sao đã hội tụ; deep-scrub kiểm tra dữ liệu theo checksum. Các tín hiệu này không tự chứng minh database hoặc nhiều volume của ứng dụng nhất quán tại một thời điểm. [BlueStore][c20], [PG states][c19].

| Bài kiểm tra | Nội dung cần chứng minh | Bằng chứng lưu lại |
| --- | --- | --- |
| Baseline và migration có tải | RBD random/sequential, sync write; RGW object nhỏ/lớn, LIST, multipart theo workload thực tế | fio/Warp, p95/p99, lỗi, tải node và tốc độ hội tụ |
| Toàn vẹn đầu cuối | Ghi dữ liệu xác định, đọc và so hash tại cùng điểm nhất quán; kiểm tra object/volume và metadata thuộc phạm vi chuyển | Manifest/hash, kết quả đối chiếu trước–sau; không mặc định ETag S3 luôn là checksum toàn object |
| Nhất quán ứng dụng | Quiesce/flush; khôi phục database/VM, kiểm tra giao dịch qua thời điểm cutover | Kết quả ứng dụng và giao dịch cuối đã được xác nhận |
| Lỗi trong lúc có tải | OSD/host mất, daemon restart, sync gián đoạn; trường hợp hỗn hợp phiên bản nếu dùng rolling | Thời gian gián đoạn, trạng thái PG, dữ liệu sau khôi phục |
| Cutover và quay lại | A → B rồi B → A với ghi mới ở B; hoặc restore thay thế nếu không hỗ trợ chiều ngược | RPO/RTO đo được, dữ liệu mới còn đủ, không có hai phía ghi ngoài kế hoạch |
| Giải phóng nguồn | Kết thúc replication, thu hồi bản nguồn và tái sử dụng node theo phạm vi đã chọn | Không xóa lan sang đích; tài nguyên thực tế được thu hồi; backup còn hiệu lực |

Chạy kiểm thử ghi và fault injection trên lab hoặc phạm vi thử riêng đã cô lập. Với nâng tại chỗ, lab cần lịch sử store đại diện; với PA1 cài mới B, cần tái hiện dữ liệu/tải dự kiến và đường migration từ phiên bản nguồn. Cả hai cần loại pool, client và kiểu tải đại diện; một lượt chạy thành công trên ba node chưa chứng minh các tình huống tải và quy mô production.

### 8.3. Điều kiện mở và dừng từng đợt

- **Mở đợt:** cụm khỏe, đủ phần dư, không có lỗi dữ liệu chưa xử lý; nhóm OSD/host và các phụ thuộc đạt kiểm tra hiện thời; backup và đường phục hồi của phạm vi đó đã được xác nhận.
- **Qua đợt tiếp theo:** PG liên quan hội tụ, QoS về mức được chấp nhận, không có lỗi mới, sync đạt yêu cầu; người vận hành đã kiểm tra kết quả.
- **Dừng mở rộng:** lỗi checksum/inconsistent/unfound, PG mất khả dụng, mất quorum, crash lặp lại, thiếu dung lượng hoặc vượt ngưỡng QoS/sync đã chốt.
- **Nếu nghi dữ liệu sai:** giữ log và điểm phục hồi, cô lập phạm vi ảnh hưởng theo kế hoạch; không tự chạy repair, xóa bản cũ hoặc đồng bộ đè khi chưa xác định bản dữ liệu hợp lệ.
- **Kết thúc:** xác nhận version/feature, health, hiệu năng và dữ liệu; gỡ cấu hình tạm đúng kế hoạch, ghi rõ bản nguồn nào còn được giữ và đến khi nào.

Phân công trước người điều phối, người theo dõi QoS/dữ liệu và đầu mối ứng dụng. Runbook phải gắn mỗi thao tác với nhóm OSD/workload cụ thể và điều kiện dừng; tài liệu tổng quan này không thay thế danh sách lệnh cho topology thực tế.

### 8.4. Đoạn đề xuất có thể dùng khi trình lãnh đạo

> Đề xuất ưu tiên thẩm định việc tách hạ tầng từ cụm có tải thấp và còn đủ tài nguyên thành một cụm Ceph độc lập, cài đồng nhất phiên bản đích rồi chuyển khách hàng theo từng đợt. Trong giai đoạn kiểm chứng, cụm nguồn giữ nguyên phiên bản để giữ dịch vụ và tạo đường phục hồi có điều kiện. Đổi lại, phải chấp nhận thời gian backfill/rebalance, tải tăng trên các OSD còn lại và chi phí duy trì hai bản dữ liệu trong phạm vi cần quay lại. Các phương án nâng tại chỗ vẫn cần kế hoạch fix-forward và không dựa vào downgrade phần mềm. Mức an toàn sẽ được chứng minh bằng kết quả kiểm tra dữ liệu, RPO/RTO đã diễn tập, giới hạn QoS và điều kiện dừng từng đợt; chưa có cơ sở để cam kết xác suất an toàn 99% hoặc 100%.

<a id="so-lieu"></a>
## 9. Số liệu cần thu thập để chọn cụm

### 9.1. Inventory và số liệu lịch sử

| Nhóm | Dữ liệu cần bổ sung |
| --- | --- |
| Phiên bản | Daemon, client RBD/RGW, image/digest, kernel/OS, lịch sử nâng và store |
| Topology | Node/rack, MON/MGR/RGW, OSD, DB/WAL và mạng dùng chung; CRUSH rule, device class |
| Bảo vệ và dung lượng | Từng pool replicated/EC, size/min_size hoặc k+m, raw/usable, phân bố mức đầy, tăng trưởng |
| Hiệu năng | Tải đỉnh và p95/p99 theo workload; tải từng OSD/host và phía nhận sau drain |
| Phạm vi chuyển | Ứng dụng, image/bucket, phụ thuộc metadata/quyền, dữ liệu cần giữ cả hai bên |
| Phục hồi | Backup có thể restore, RPO/RTO, cửa sổ dừng ghi, khả năng đồng bộ ngược |
| Giới hạn kinh doanh | Downtime cho phép, SLO trong khi nâng, thời gian giữ nguồn, ngân sách node và vận hành |

Không chỉ dùng số PG làm đại diện tải. Nếu phiên bản/monitoring hiện tại chưa có số I/O theo từng PG đáng tin cậy, dùng dữ liệu OSD, primary mapping, pool và phép đo workload làm chỉ báo, đồng thời ghi rõ giới hạn của cách chọn.

### 9.2. Lệnh đọc tham khảo

Chạy trong môi trường quản trị phù hợp với cụm; nhóm `ceph orch` chỉ áp dụng khi có orchestrator tương ứng. Kết quả lệnh là ảnh chụp hiện tại, cần kết hợp số liệu lịch sử.

```bash
ceph -s
ceph health detail
ceph versions
ceph df detail
ceph osd df tree
ceph osd pool ls detail
ceph osd crush rule dump
ceph orch ps
```

Khi đã xác định tập OSD và đúng thời điểm thực hiện, dùng `ceph osd ok-to-stop` hoặc `ceph osd safe-to-destroy` với ID cụ thể cho đúng mục đích. Kiểm tra cả tập dự kiến dừng, không cộng các kết quả kiểm tra riêng lẻ rồi coi là cả nhóm an toàn. [Command API][c8].

### 9.3. Quy tắc ra quyết định sau khi có số liệu

1. Loại cụm không đủ health, dung lượng hoặc failure domain sau tách.
2. Trong số còn lại, chọn cụm có nhiều phần dư nhất ở giờ cao điểm và workload có thể chuyển theo phạm vi nhỏ.
3. Đo drain + sync trong giới hạn QoS, xác nhận B đủ dung lượng và khả năng phục vụ.
4. Diễn tập cutover, bảo vệ ghi mới và failback/restore; ghi RPO/RTO thực đo.
5. Chọn PA1 khi lợi ích giảm rủi ro nâng tại chỗ lớn hơn chi phí co nhỏ A và migration. Nếu thiếu phần dư, xét PA2 khi có hạ tầng; nếu không, quay về thẩm định PA3/PA4 với phạm vi nhỏ và kế hoạch phục hồi tương ứng.

<a id="nguon"></a>
## 10. Nguồn tham khảo

**Notion của dự án, đọc ngày 11/09/2026:**

- [PRJ GD2 upgrade ceph][n1]: phạm vi, kiểm thử và định hướng tách cụm.
- [note][n2]: các phương án OSD, phiên bản/store và giới hạn phục hồi.
- [Upgrade risk][n3]: các rủi ro phiên bản cần đối chiếu.
- [checklist][n4]: lịch sử store, engine và điều kiện cụm.
- [Tiêu chí chọn OSD][n5]: health, PG, tải primary và tải các replica liên quan.

**Tài liệu Ceph được dẫn tại các nhận định tương ứng:**

- Nâng cấp/phiên bản: [cephadm Pacific][c1], [Reef release notes][c2], [Pacific release notes][c21], [health checks][c22].
- Rút node/OSD và topology: [host management][c3], [OSD service][c4], [bootstrap][c5], [CRUSH][c6], [thêm/rút OSD][c7], [command API][c8], [upmap][c9].
- Dữ liệu và pool: [theo dõi OSD/PG][c10], [pool][c14], [PG states][c19], [BlueStore][c20].
- Replication: [RBD mirroring][c11], [RBD snapshot][c17], [RGW multisite][c12], [RGW data layout][c13], [multisite sync policy][c18].
- QoS: [OSD configuration Pacific][c15], [mClock Reef][c16].

Các bảng chi phí, tiêu chí lựa chọn và quy trình PA1 là đề xuất tổng hợp từ bối cảnh dự án cùng các cơ chế trên; không phải chứng nhận của Ceph hoặc số đo production. Release notes có thể được cập nhật; cần kiểm tra lại đúng phiên bản trước triển khai.

[n1]: https://app.notion.com/p/3c3ac177517c80219d6edffa27d07e1a
[n2]: https://app.notion.com/p/3d5ac177517c805d807cd295acd8ceb1
[n3]: https://app.notion.com/p/3c3ac177517c8083af7afdc952408484
[n4]: https://app.notion.com/p/3c4ac177517c80b1ac03e226bd8f1968
[n5]: https://app.notion.com/p/3d7ac177517c8086a3eed25414b34cb9
[c1]: https://docs.ceph.com/en/pacific/cephadm/upgrade/
[c2]: https://docs.ceph.com/en/latest/releases/reef/
[c3]: https://docs.ceph.com/en/reef/cephadm/host-management/
[c4]: https://docs.ceph.com/en/reef/cephadm/services/osd/
[c5]: https://docs.ceph.com/en/reef/cephadm/install/
[c6]: https://docs.ceph.com/en/reef/rados/operations/crush-map/
[c7]: https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/
[c8]: https://docs.ceph.com/en/pacific/api/mon_command_api/
[c9]: https://docs.ceph.com/en/reef/rados/operations/upmap/
[c10]: https://docs.ceph.com/en/pacific/rados/operations/monitoring-osd-pg/
[c11]: https://docs.ceph.com/en/reef/rbd/rbd-mirroring/
[c12]: https://docs.ceph.com/en/reef/radosgw/multisite/
[c13]: https://docs.ceph.com/en/reef/radosgw/layout/
[c14]: https://docs.ceph.com/en/reef/rados/operations/pools/
[c15]: https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/
[c16]: https://docs.ceph.com/en/reef/rados/configuration/mclock-config-ref/
[c17]: https://docs.ceph.com/en/reef/rbd/rbd-snapshot/
[c18]: https://docs.ceph.com/en/reef/radosgw/multisite-sync-policy/
[c19]: https://docs.ceph.com/en/reef/rados/operations/pg-states/
[c20]: https://docs.ceph.com/en/reef/rados/configuration/bluestore-config-ref/
[c21]: https://docs.ceph.com/en/latest/releases/pacific/
[c22]: https://docs.ceph.com/en/reef/rados/operations/health-checks/
