# Storage Lab Console — Kế hoạch v5: Chỉ số trực tiếp, As-is và so sánh daemon

**Phiên bản:** 5.1

**Cập nhật:** 13/10/2026

**Trạng thái:** bản chỉ đọc `5.1.0-rc.1` đã phát hành Docker Hub ngày 12/10/2026. Localhost 8080 đang chạy bản sửa app `5.1.1-preview.2` và worker `16.2.15-minimal-preview.2`, chỉ lab/chỉ đọc. Giới hạn ở mục 21, release Hub ở mục 22, lịch sử đổi cấu hình ở mục 26, bản sửa hiện tại ở mục 27. Worker vẫn chưa đạt security/stability gate production.

Đây là plan console hiện hành, thay thế các yêu cầu sản phẩm của v4.2. Không dùng phần kế hoạch cũ trong bản lưu trữ để bổ sung lại chức năng đã bị loại bỏ.

## 1. Quyết định sản phẩm

Console tập trung vào việc đọc trạng thái và chỉ số của cụm Ceph, lấy hiện trạng **As-is** cho các daemon được chọn trước/trong/sau một đợt nâng cấp, xuất dữ liệu về máy và so sánh hai lần thu thập.

Các quyết định bắt buộc:

1. Bỏ toàn bộ chức năng Benchmark fio/Warp khỏi sản phẩm và backlog hiện hành: menu, màn hình, runner, API điều khiển, cấu hình asset/workload và hướng dẫn sử dụng liên quan.
2. Bỏ màn hình và quy trình Dry-run planning. Người dùng không cần tạo plan/run nâng cấp để lấy dữ liệu.
3. **Chỉ số cụm và daemon** đọc dữ liệu mới tại thời điểm bấm **Xem** hoặc **Xuất dữ liệu mới**, cho từng daemon và toàn hệ thống.
4. Danh sách daemon hiển thị **10 dòng mỗi trang**. Không giới hạn cluster, phạm vi thu thập hoặc export còn 10 daemon.
5. **Thu thập hiện trạng (As-is)** thay OSD inventory: hỗ trợ nhiều loại daemon, chọn một hoặc nhiều daemon, thu mới khi bấm; OSD có bộ thông tin chuyên sâu hơn.
6. Có ba nhãn giai đoạn **Trước nâng cấp / Trong nâng cấp / Sau nâng cấp**. Nhãn do người dùng chọn, không phải chứng nhận nâng cấp đã chạy.
7. Bỏ tên **Evidence & Comparison**, thay bằng **So sánh**. Người dùng chọn **Collection A / Collection B**, không bị bắt buộc Before→After.
8. So sánh chỉ giữa daemon **cùng loại, cùng cluster FSID**, ghép theo daemon ID. Có lọc ngày, loại daemon, daemon được chọn và giai đoạn.
9. Bỏ trường **Upgrade session** và bước tạo/chọn session khỏi luồng sử dụng mới.
10. Có thể xóa collection qua thao tác có xác nhận và khả năng khôi phục; không xóa dữ liệu hoặc daemon trên Ceph.
11. Việt hóa toàn bộ giao diện, trạng thái, validation, thông báo lỗi và nội dung hướng dẫn.
12. Giữ đóng gói OCI image portable, SSH key/host-key pinning, FSID verification, quyền đọc, bảo mật export và dữ liệu bền vững ngoài image.
13. Thêm **Xem trước thay đổi OSDMap** bằng `osdmaptool`: lấy map hiện tại, mô phỏng thay đổi trên bản cục bộ và hiển thị chênh lệch placement trước khi người vận hành thay đổi thật. Chỉ dự đoán các thay đổi đã có adapter được kiểm thử; không gửi map/lệnh giả định vào cluster.

**Phạm vi nâng cấp:** chọn nhiều daemon để thu thập/theo dõi các daemon dự định nâng cấp. Không có nút tự nâng cấp, redeploy, stop OSD hoặc thay đổi placement trong phạm vi v5. Việc nâng cấp vẫn do người vận hành thực hiện qua quy trình riêng. Plan chiến lược PA2 ở tài liệu dự án không trở thành lệnh mà console tự thực thi.

### 1.1. Phạm vi triển khai

- Một deployment nối một cluster tại một thời điểm; đổi cluster qua cấu hình runtime.
- Loại daemon đích: MON, MGR, OSD, RGW, MDS, theo capability và dữ liệu thực tế của cluster.
- Host, pool và tổng quan hệ thống là **tài nguyên/ngữ cảnh**, không được tính thành daemon.
- MON/MGR/OSD là lát cắt đầu tiên; RGW/MDS phải hiện rõ chưa hỗ trợ nếu adapter chưa có, không giả là đã triển khai.
- Công cụ RGW/RBD cũ giữ trong nhóm **Công cụ cũ**, không xuất hiện trong luồng As-is chính.
- Chỉ số hiệu năng của application/workload cũ không được trình bày như chỉ số Ceph/system thật.

## 2. Hiện trạng và khoảng trống

### 2.1. Đã kiểm tra trên localhost

Ngày 12/10/2026, localhost đã nối Ceph thật bằng SSH key, kiểm FSID và có dữ liệu:

- Cluster, MON/MGR, 6 OSD, 3 host, 12 pool.
- OSD collector lấy thông tin thiết bị, topology, phiên bản, PG/primary PG và cluster context.
- Baseline OSD đã lưu trong database/evidence; export ZIP thực đã tải xuống máy và đối chiếu checksum.
- Nguồn Prometheus MGR đã có IOPS/throughput cluster và từng OSD.
- Deployment hiện read-only; các thao tác ghi vào Ceph bị khóa.

Chi tiết lần kiểm tra nằm trong [VALIDATION.md](rgw-console/VALIDATION.md) và [hướng dẫn SSH local](rgw-console/docs/LOCAL_SSH_READONLY.md). Các tài liệu này ghi hiện trạng cũ, cần cập nhật cùng lát cắt triển khai v5.

### 2.2. Khoảng trống ghi nhận trước triển khai v5

Danh sách dưới là mốc trước triển khai; kết quả đã làm và phần còn thiếu hiện tại được cập nhật ở mục 21.

- Cluster & Metrics hiện đọc collection lưu gần nhất; nút xem/export hiện chưa luôn thu mới.
- OSD collection còn phụ thuộc session và chỉ hỗ trợ OSD.
- Comparison hiện có ràng buộc cùng session/config snapshot và Before→After; không đáp ứng A/B bất kỳ.
- Chưa có collection As-is đa loại daemon, xóa/khôi phục và phân trang 10 daemon hoàn chỉnh.
- Nguồn CPU/RAM/process/network cho host/daemon chưa có adapter đầy đủ.
- UI còn tiếng Anh và còn các màn hình cần gỡ.
- Chưa có tính năng xem trước OSDMap trong console. Việc có hướng dẫn mô phỏng trong MOP không có nghĩa UI/API đã triển khai.

**Không đánh dấu hoàn tất bằng việc đổi tài liệu.** Cần sửa source, kiểm thử, build image và cập nhật localhost trước khi tuyên bố v5 đã chạy. Image Docker Hub đã phát hành không tự thay đổi theo source local.

## 3. Luồng sử dụng mới và navigation

Navigation chính, theo thứ tự:

1. **Tổng quan**
2. **Chỉ số cụm và daemon**
3. **Thu thập hiện trạng**
4. **So sánh**
5. **Công cụ cũ** — nhóm thu gọn

Không còn mục Benchmark, Dry-run planning hoặc Evidence & Comparison.

### 3.1. Luồng lấy chỉ số trực tiếp

1. Mở **Chỉ số cụm và daemon**.
2. Chọn toàn hệ thống, một loại daemon, một daemon hoặc nhiều daemon.
3. Bấm **Xem** để đọc lại nguồn; hiển thị thời điểm thực thu và chất lượng dữ liệu.
4. Bấm **Xuất dữ liệu mới** để đọc lại nguồn một lần nữa rồi tạo file.
5. Nếu muốn giữ hiện trạng phục vụ so sánh, chuyển lựa chọn sang **Thu thập hiện trạng** và bấm **Lấy As-is**.

### 3.2. Luồng As-is trước/trong/sau

1. Mở **Thu thập hiện trạng**, danh sách daemon được đọc mới.
2. Chọn các daemon sẽ theo dõi/nâng cấp, có thể chọn nhiều daemon qua nhiều trang.
3. Chọn nhãn **Trước / Trong / Sau nâng cấp**, tùy chọn ghi chú.
4. Bấm **Lấy As-is**: hệ thống thu **mới tại lần bấm này**, tạo collection riêng.
5. Xem dữ liệu từng daemon và lỗi nếu có; xuất collection hoặc lấy lần mới.
6. Sang **So sánh**, lọc và chọn hai collection A/B phù hợp.

Không cần Upgrade session, upgrade run, target image, spare OSD, plan revision hoặc xác nhận dry-run để đọc/thu dữ liệu.

### 3.3. Ý nghĩa “Upgrade session” và cách bỏ

Hiện session là nhóm kỹ thuật dùng để gắn FSID, bản cấu hình và lịch sử; nó **không tự thực hiện nâng cấp**. Người dùng bị yêu cầu chọn session do API/foreign key cũ, không phải vì đọc Ceph cần session.

Thiết kế mới:

- Mỗi collection tự giữ cluster ID, FSID, người thu, phạm vi daemon, thời gian, nguồn, schema và bản cấu hình đã redact/hash.
- UI không có selector hoặc nút tạo session.
- Có thể có tên đợt/ghi chú tùy chọn để dễ tìm, nhưng không phải điều kiện bắt buộc.
- Lớp tương thích có thể tạo ngữ cảnh nội bộ cho collector cũ trong giai đoạn chuyển tiếp. Ngữ cảnh này không được tái xuất hiện thành bước người dùng phải thao tác.
- Không xóa bảng/session/config snapshot cũ hoặc sửa migration đã áp dụng để né foreign key.

### 3.4. Xem trước tác động trước khi thay đổi

Trong phần OSD của **Thu thập hiện trạng**, có nút **Xem trước thay đổi OSDMap**:

1. Chọn OSD, pool/phạm vi PG và thông số dự định thay đổi qua form có kiểu dữ liệu.
2. Bấm **Tính tác động**: thu OSDMap mới, tạo kịch bản cục bộ và so sánh map gốc với map giả định.
3. Xem PG/primary thay đổi, phân bố trên OSD và ảnh hưởng ngoài tập OSD được chọn; sửa thông số và tính lại nếu cần.
4. Lưu/xuất báo cáo với nhãn **Dự đoán — chưa áp dụng**. Không có nút Áp dụng lên Ceph.
5. Nếu người vận hành đổi cluster bên ngoài console, có thể lấy As-is mới để đối chiếu thực tế; không coi kịch bản giả định là collection Sau nâng cấp.

Đây là công cụ phân tích placement độc lập, **không khôi phục Dry-run planning/session/upgrade controller đã bỏ**. Chi tiết contract ở mục 20.

## 4. Quy ước “thời gian thực” và dữ liệu mới

“Thời gian thực” trong v5 nghĩa là **đọc mới theo yêu cầu tại lần bấm**, không phải lấy collection cũ và đổi timestamp.

### 4.1. Contract nút Xem

- Mỗi lần bấm phát sinh request mới tới nguồn Ceph/telemetry được phép.
- Trả thông tin daemon cùng chỉ số đo có thời gian nguồn cụ thể.
- Trong khi đọc, hiển thị **Đang lấy dữ liệu…**; ngăn thao tác trùng ngoài ý muốn.
- Không âm thầm dùng lịch sử hoặc cache cũ khi SSH/Prometheus lỗi.
- Nếu giữ dữ liệu đã xem trên màn hình khi request mới lỗi, phải tách rõ **Dữ liệu lần trước**, thời gian cũ và lỗi lần mới; không gắn nhãn “Mới”.
- Đọc mới khi vào màn hình; thao tác Xem lại luôn thu mới. Phân trang không được tự làm mất lựa chọn.
- Đáp ứng đổi filter/daemon bằng request đúng phạm vi; kết quả request cũ không được ghi đè request mới nếu trả về muộn.

### 4.2. Contract nút Xuất dữ liệu mới

- Thu mới đúng phạm vi đã chọn trước khi tạo file, không tái dùng payload lần Xem.
- Mỗi lần export giữ request ID và thời gian thu; retry cùng request để tải lại có thể dùng chính kết quả đó. Một lần bấm mới dùng request ID mới.
- Nguồn thiếu/lỗi phải hiện rõ; chỉ xuất phần có thật kèm trạng thái Một phần, không tạo số 0 hoặc số liệu giả.
- Có hai ý định tách biệt: **Xuất dữ liệu mới** ở màn hình trực tiếp và **Xuất collection đã lưu** trong lịch sử/So sánh.
- Xuất collection đã lưu không được thu lại, vì sẽ làm thay đổi ý nghĩa của A/B; file phải ghi rõ **Dữ liệu đã lưu — thời điểm…**.

### 4.3. Timestamp và tính đồng thời

Mỗi yêu cầu có:

- Thời điểm bắt đầu và kết thúc.
- Thời điểm quan sát của từng daemon/nguồn.
- Khoảng đo, độ trễ/tuổi dữ liệu nguồn và chất lượng.
- Thông tin schema, nguồn CLI/Prometheus/host agent và collector version.

Lưu UTC; hiển thị thời gian **Asia/Saigon**, kèm múi giờ trong export. Thu nhiều daemon không phải ảnh chụp nguyên tử của cluster: phải thể hiện khoảng thu và chênh thời điểm quan sát.

### 4.4. Counter, rate và percentile

- IOPS/throughput cần cửa sổ đo và ít nhất hai counter hợp lệ, hoặc truy vấn rate đã có cửa sổ xác định.
- Lần Xem/Export đọc endpoint mới; không hứa đo tức thời trong một mili giây.
- Nếu cần hai lần scrape trực tiếp, UI báo đang đo và hiển thị khoảng đo thực; không lấy counter thô làm IOPS.
- Counter reset/restart/incarnation đổi phải được nhận diện; không sinh rate/delta âm giả.
- Không dùng số đo quá cũ như số đo mới. Ngưỡng freshness theo nguồn có cấu hình và được hiển thị.
- Không suy luận p50/p95/p99 từ average hoặc trung bình percentile. Chỉ hiển thị percentile khi nguồn có dữ liệu hợp lệ.

## 5. Chỉ số cụm và daemon

### 5.1. Bố cục và 10 daemon mỗi trang

- Khu tổng quan hệ thống nằm riêng: health, dung lượng, population daemon, trạng thái PG/recovery và chỉ số tải khi có nguồn.
- Bảng daemon mặc định 10 dòng/trang, có tổng số, trang trước/sau và filter.
- Filter loại daemon, tên/ID, host, trạng thái; sort ổn định theo loại + daemon ID.
- Chọn hàng ở trang hiện tại, chọn nhiều trang, hoặc chọn toàn bộ kết quả lọc. Phải ghi rõ **Đã chọn N daemon**, không nhầm “Chọn 10 hàng” với “Chọn tất cả”.
- API trả page/cursor, tổng số hoặc next cursor; không tải vô hạn toàn cluster vào DOM.
- Export theo một daemon, các daemon đã chọn hoặc toàn phạm vi lọc được phép. Export không bị cắt còn trang đang thấy.
- Nếu yêu cầu quá lớn, tạo job thu/export có tiến độ hoặc báo giới hạn rõ; không cắt ngầm.

### 5.2. Nguồn và nội dung

| Phạm vi | Dữ liệu phải hỗ trợ theo nguồn thực |
|---|---|
| Hệ thống/cluster | Health/checks, FSID, dung lượng, phiên bản, PG trạng thái, recovery/backfill, cluster flags, IOPS/throughput/latency khi có |
| MON | Danh tính/host/địa chỉ/phiên bản, quorum/rank/election/monmap, latency và process metrics khi có adapter |
| MGR | Active/standby, module, host/địa chỉ/phiên bản/image, process metrics khi có |
| OSD | Up/in, capacity, weight/reweight/primary-affinity, PG/primary PG, phiên bản/image, IOPS/throughput/latency và process metrics khi có |
| RGW | Danh tính/host/phiên bản/image, request/error/latency/throughput theo endpoint telemetry được phép |
| MDS | Danh tính/host/phiên bản/image, filesystem/rank/state, session/cache/load theo nguồn được phép |
| Host | Host inventory; CPU/RAM/disk/network/clock qua nguồn host thật, không lấy metric cluster gán thành metric host |
| Pool | Config/capacity/PG, ngữ cảnh các daemon liên quan; không phải workload generator |

Phân biệt **Thông tin hiện trạng** với **Chỉ số đo**, gauge với counter/rate, cluster aggregate với daemon/process metrics.

Nội dung nguồn chưa có phải hiện **Chưa có nguồn / Chưa hỗ trợ / Không đủ dữ liệu**, kèm lý do. Daemon vắng mặt không tự động có nghĩa “down”; cần bằng chứng từ nguồn chính thức.

### 5.3. Nguồn dữ liệu cần bổ sung

- Ceph CLI qua closed executor cho inventory, health, quorum, maps và cấu hình.
- Ceph MGR Prometheus/Prometheus query cho các chỉ số Ceph được xác minh.
- Host/process telemetry adapter cho CPU/RAM/network/disk/clock; cần xác định mapping daemon→process/container→host.
- Khi nguồn không có FSID label, endpoint phải được ràng buộc với cluster đã kiểm danh tính; không tự kết hợp nhiều cluster.
- Không đổi cài đặt MGR, mở port hoặc cài agent lên cluster một cách ngầm định. Triển khai nguồn mới cần cấu hình/quyền riêng.

## 6. Thu thập hiện trạng (As-is)

### 6.1. Đối tượng và lựa chọn nhiều daemon

- Danh tính chuẩn: **(cluster FSID, loại daemon, daemon ID)**; không dùng chỉ tên vì MON/MGR có thể trùng.
- Chọn daemon cụ thể, host hoặc loại daemon; UI phải cho xem danh sách đích cuối cùng trước khi thu.
- Lưu danh sách yêu cầu và danh sách đã thu thực tế; daemon thiếu/lỗi nằm trong kết quả, không biến mất khỏi báo cáo.
- Có thể thu nhiều loại trong một collection. Khi so sánh phải chọn từng loại, không gộp MON và OSD vào một bảng diff có ý nghĩa sai.
- Chọn nhiều daemon nghĩa là phạm vi theo dõi phục vụ nâng cấp, không cho phép console nâng cấp đồng thời tất cả.
- Không bắt nhập OSD ID thủ công nếu có inventory danh sách; vẫn có tìm tên/ID.

### 6.2. Ba giai đoạn

Ba giá trị UI:

- **Trước nâng cấp**
- **Trong nâng cấp**
- **Sau nâng cấp**

Có thể lấy nhiều collection trong cùng giai đoạn. Không yêu cầu đủ cả ba mới được xem/xuất/so sánh. Không bắt A phải Trước và B phải Sau. Không tự chuyển nhãn dựa trên tuổi dữ liệu hoặc giả định upgrade thành công.

### 6.3. Hành vi mỗi lần bấm

- Nút **Xem hiện trạng** đọc mới, không chọn snapshot cũ làm nguồn.
- Nút **Lấy As-is** đọc mới và lưu collection bất biến của chính lần thu.
- Nút **Lấy As-is và xuất** dùng một lần thu mới duy nhất: lưu và xuất cùng collection ID/hash.
- Collection cũ chỉ nằm trong **Lịch sử thu thập**, được ghi ngày giờ rõ. Không gọi lịch sử đó là “hiện trạng đang sống”.
- Mỗi bấm mới có collection mới. Retry của cùng một job không tạo hai collection khác nhau.
- Thu lâu hoặc nhiều daemon dùng job có tiến độ từng daemon; giới hạn concurrency/timeouts/output được áp dụng.
- Trạng thái tiếng Việt: **Đang thu thập / Hoàn tất / Một phần / Thất bại / Đã xóa**. State kỹ thuật có thể giữ mã ổn định trong API.
- Một daemon lỗi không xóa kết quả hợp lệ của daemon khác; thông tin lỗi được redact.
- Không đánh dấu toàn collection “đủ” khi thiếu command/field bắt buộc.

### 6.4. Thông tin chung và phần OSD chuyên sâu

Thông tin chung mỗi daemon:

- ID, loại, host/địa chỉ, cluster FSID và incarnation khi có.
- Trạng thái, phiên bản Ceph, image/digest, cấu hình hiệu lực liên quan.
- Chỉ số tại cửa sổ thu, đơn vị và thời gian nguồn.
- Capability, dữ liệu thiếu, lỗi từng nguồn và quality.
- Provenance/hash để kiểm tra tính toàn vẹn.

OSD phải giữ thêm:

- OSD UUID, public/cluster network, CRUSH location và device class.
- BlueStore data/DB/WAL path, physical devices, capacity và device IDs.
- Up/in, daemon status, CRUSH weight, reweight, primary-affinity.
- PG count, primary PG count, PG IDs và dữ liệu up/acting/override theo phạm vi được phép.
- Effective config, cluster/pool/CRUSH context cần để đọc đúng tình trạng OSD.
- Thông tin thiết bị không được báo phải giữ **Không có dữ liệu**, không giả DB/WAL riêng.
- Tách thông tin read-only khỏi điều kiện an toàn nâng cấp. Dữ liệu hợp lệ không tự thành PASS/HOLD vận hành.

### 6.5. Coverage A0 cần bảo toàn

Các nhóm dưới đây là yêu cầu thu thập/export, **không phải tuyên bố source đã hỗ trợ đầy đủ**:

| Nhóm | Dữ liệu cần giữ | Áp dụng |
|---|---|---|
| A0.1 — Môi trường | Host chạy collector, shell/OS, thời gian/múi giờ, công cụ và client version | Provenance của lần thu |
| A0.2 — Cluster | Health/checks, MON quorum, MGR, capacity, flags | Ngữ cảnh chung |
| A0.3 — OSD | Tree, weight/reweight/primary-affinity, capacity, phiên bản/image | Phần OSD chuyên sâu |
| A0.4 — CRUSH | Map/rules, compat weight-set, choose_args | Phần OSD/placement context |
| A0.5 — PG | Up/acting, PG theo các OSD được chọn, override | Phần OSD/PG context |
| A0.6 — Pool/RBD | Pool config, PG/image/mapping liên quan được chọn | Chốt phạm vi hiện trạng, không tạo workload |
| A0.7 — Orchestration | Daemon version/image, service spec, upgrade status | Mỗi loại daemon khi nguồn hỗ trợ |
| A0.8 — An toàn | Clock sync, crash, scrub, recovery, dung lượng và tình trạng nguồn/helper | Bằng chứng; không tự cấp quyền thực thi |

Không hard-code osd.2/osd.5 hoặc PG 13.0 vào logic; đó là giá trị lab có thể chọn qua cấu hình/UI. Collection phải ghi coverage **Đã lấy / Thiếu / Không áp dụng / Chưa hỗ trợ**. Group lỗi/thiếu vẫn xuất được với lý do.

## 7. Lịch sử và xóa collection

### 7.1. Lịch sử

Lọc theo ngày thu, loại daemon, daemon ID/host, nhãn Trước/Trong/Sau, quality và trạng thái xóa. Hiển thị số daemon, coverage, thời gian, ID rút gọn và ghi chú.

Khoảng ngày trong UI dùng Asia/Saigon và quy đổi UTC, biên **từ đầu ngày bắt đầu đến trước đầu ngày kế tiếp của ngày kết thúc**. Không bỏ mất dữ liệu cuối ngày.

### 7.2. Xóa và khôi phục

- Cho xóa một hoặc nhiều collection do người dùng chọn rõ.
- Mặc định **xóa mềm**: ẩn khỏi danh sách và lựa chọn so sánh thông thường, ghi deleted_at/deleted_by/reason và cho **Khôi phục**.
- Hộp xác nhận ghi ID/thời gian/số collection/số daemon và ảnh hưởng tới comparison.
- Không xóa collection đang thu; không dừng job hoặc xóa dữ liệu Ceph qua nút xóa.
- Comparison có nguồn bị xóa phải báo **Nguồn đã xóa**, không trả kết quả mới như nguồn vẫn tồn tại.
- Khôi phục collection trả dữ liệu gốc/hash gốc, không thu lại rồi gán ID cũ.
- Collection có tham chiếu lịch sử cần giữ blob và audit. Không cascade xóa session, upgrade evidence hoặc collection khác.
- Dọn blob/xóa vĩnh viễn là quy trình riêng có quyền, kiểm references và xác nhận; chưa tự động làm trong MVP.
- File export đã tải trên máy không bị xóa theo collection.
- Read-only đối với Ceph vẫn cho phép metadata collection trong ứng dụng thay đổi; phải tách quyền **đọc Ceph**, **thu**, **xuất**, **xóa/khôi phục lịch sử**.

## 8. So sánh hai As-is collection

### 8.1. Cách chọn

- Trang chỉ có chức năng **So sánh**, không còn một workspace Evidence riêng.
- Filter ngày, loại daemon, tên/ID/host, giai đoạn và chất lượng.
- Chọn một loại daemon trước, rồi chọn **Collection A** và **Collection B** khác nhau.
- Collection nhiều loại chỉ dùng phần đúng loại đã chọn.
- Cho chọn nhiều daemon trong hợp hai tập A/B; không ép toàn bộ scope hai bên phải giống nhau. Bảng coverage giữ cả các daemon chỉ có một phía; delta chỉ tính cho daemon cùng ID có dữ liệu tương thích ở cả hai phía.
- Nhãn Trước/Trong/Sau hiển thị để đọc ngữ cảnh, không làm gate hợp lệ.
- Không bắt cùng session hoặc cùng config hash; thay đổi cấu hình/phiên bản là nội dung cần so sánh.
- A/B có thể được chọn theo thứ tự bất kỳ; delta ghi rõ **B − A** và ngày giờ hai bên. Đảo A/B đảo hướng, không đổi dữ liệu nguồn.

### 8.2. Điều kiện và matching

- Cùng FSID và cùng loại daemon là điều kiện bắt buộc; không so MON với OSD, không trộn hai cluster.
- Ghép từng hàng theo daemon ID, không tự lấy ID khác thay thế.
- Daemon chỉ có ở một bên hiển thị **Chỉ có ở A / Chỉ có ở B / Không đủ dữ liệu**.
- Nếu incarnation/OSD UUID/process đổi, hiển thị rõ **Daemon đã được tạo lại/khởi động lại** khi có bằng chứng; không coi raw counter là chuỗi liên tục.
- Schema/collector version khác phải kiểm mapping tương thích; trường không tương thích có lý do, không auto PASS.
- Giữ dữ liệu thiếu null/unknown riêng với zero, false và tập rỗng hợp lệ.

### 8.3. Kết quả

- Bảng A/B: danh tính, thời điểm, giá trị A, giá trị B, thay đổi, đơn vị, quality và lý do không so được.
- Nhóm trường theo thông tin chung, phiên bản/image, cấu hình, metric, và phần chuyên sâu loại daemon.
- OSD thêm topology/device/weight/affinity/capacity/PG/up-acting/override.
- Metric rate chỉ so khi cửa sổ/đơn vị/định nghĩa tương thích; ghi rõ nếu khác cửa sổ. Raw counter reset không suy thành biến động tải.
- Ngữ cảnh cluster có thể trình bày bên cạnh, không tự coi nó là metric của daemon.
- So sánh là dữ liệu mô tả, không phải kết luận nâng cấp thành công hoặc quyền vận hành.
- Cho **Xuất so sánh** JSON/CSV/Markdown/ZIP với hai source collection ID/hash/coverage, không đọc lại Ceph khi xuất diff.

## 9. Việt hóa

Toàn bộ nội dung người dùng nhìn thấy phải bằng tiếng Việt:

- Menu, heading, nút, label, tooltip, empty/loading/error state.
- Tên filter, pagination, confirmation và validation.
- Nhãn quality/freshness và giải thích dữ liệu thiếu.
- Hướng dẫn README và báo cáo đọc được trong export.

Giữ nguyên tên daemon/host/pool, FSID/ID/hash, tên lệnh Ceph, metric key, đơn vị và raw schema khi cần đối chiếu.

Một số mapping:

| Nhãn cũ/kỹ thuật | Nhãn UI mới |
|---|---|
| Cluster & Metrics | Chỉ số cụm và daemon |
| OSD inventory | Thu thập hiện trạng |
| Evidence & Comparison | So sánh |
| Legacy | Công cụ cũ |
| View / Export | Xem / Xuất dữ liệu mới |
| Before / During / After | Trước / Trong / Sau nâng cấp |
| Collection A / Collection B | Bộ As-is A / Bộ As-is B |
| VALID / PARTIAL / UNKNOWN | Dữ liệu hợp lệ / Dữ liệu một phần / Chưa xác định |
| FRESH / STALE | Dữ liệu mới / Dữ liệu cũ |
| Delete / Restore | Xóa collection / Khôi phục |

Không dịch mã API/state lưu trong database theo kiểu làm mất khả năng đọc lịch sử. Dùng bảng nhãn/localization riêng; thông báo backend có mã ổn định và nội dung UI tiếng Việt.

## 10. API và kiến trúc mục tiêu

Các tên API dưới đây là **contract đề xuất**, chưa phải endpoint đã triển khai.

### 10.1. Bounded modules

- **Danh mục tài nguyên/daemon:** discovery, filter, pagination, allowlist và capability.
- **Chỉ số trực tiếp:** fresh read/rate window, source timestamps, đơn vị và scope.
- **Thu thập As-is:** job, partial results, collection registry, provenance và artifact.
- **So sánh:** matching, compatible schema, diff A/B và coverage.
- **Xem trước OSDMap:** đọc map gốc, thay đổi có kiểu trên bản cục bộ, gọi `osdmaptool`, đối chiếu placement và lưu kết quả dự đoán tách biệt với As-is thực.
- **Xuất dữ liệu:** live read + render hoặc saved collection + verified render.
- **Lịch sử:** filter, xóa mềm/khôi phục và audit.
- **Cấu hình/bảo mật:** FSID, SSH, token, authorization, redact và storage containment.
- **Công cụ cũ:** cách ly, không điều khiển As-is state.

Domain không import SSH/FastAPI/database driver; adapter gọi fixed allowlisted actions. Không có arbitrary shell/CLI argv từ browser.

### 10.2. API đề xuất

- GET /api/v1/daemons — danh mục trực tiếp; type/host/search/status/page_size=10/cursor.
- POST /api/v1/live-observations — đọc mới system/daemon metrics, không đọc collection gần nhất.
- POST /api/v1/as-is/collections — phạm vi daemon + giai đoạn + ghi chú; không yêu cầu session_id.
- GET /api/v1/as-is/jobs/{id} — tiến độ, daemon hoàn tất/lỗi và kết quả.
- GET /api/v1/as-is/collections — lịch sử có filter ngày/type/ID/giai đoạn/deleted.
- GET /api/v1/as-is/collections/{id} — đọc dữ liệu đã lưu, ghi rõ historical.
- DELETE /api/v1/as-is/collections/{id} — xóa mềm có authorization/audit.
- POST /api/v1/as-is/collections/{id}/restore — khôi phục dữ liệu gốc.
- POST /api/v1/as-is/comparisons — collection_a/collection_b/daemon_type/daemon_ids.
- POST /api/v1/exports/live — thu mới rồi xuất theo scope.
- POST /api/v1/exports/saved — xuất collection hoặc diff bất biến đã xác minh.
- POST /api/v1/osdmap-previews — tạo job tính tác động; chỉ nhận thay đổi đã có capability và phạm vi được phép.
- GET /api/v1/osdmap-previews/{id} — kết quả, provenance, coverage và trạng thái map gốc đã cũ.
- POST /api/v1/osdmap-previews/{id}/export — xuất báo cáo dự đoán đã lưu, không thực thi lệnh Ceph.

Có batch xóa với danh sách ID đóng/giới hạn; không nhận SQL filter hoặc wildcard path để xóa. Payload các thao tác dùng schema đóng, idempotency và giới hạn số daemon.

### 10.3. Freshness và đồng thời

- Discovery, live read và collection job có request/job IDs riêng.
- Ghi nguồn từng daemon, thời điểm và quality; không biến API poll time thành observed_at.
- Collector worker có concurrency cap, timeout, output cap và một owner lease của job.
- Restart API/worker không làm job đang chạy thành Hoàn tất giả; reconcile hoặc báo trạng thái chưa xác định.
- UI polling có backoff; đổi trang/filter không mất selection hoặc trộn response.
- Cấm cache browser/service worker/proxy làm fresh action thành old observation; API gửi cache policy phù hợp.

## 11. Data model và chuyển đổi lịch sử

Collection mới cần tối thiểu:

- ID, cluster_id, fsid, actor, phase, ghi chú/tên đợt tùy chọn.
- Requested/resolved daemon identities và lỗi các đích không thu được.
- Started_at/completed_at, source observed times và metric windows.
- Collector/schema version, capability/coverage và config provenance đã redact/hash.
- Quality/state, immutable artifact ID/hash/size.
- Metadata xóa mềm/khôi phục và audit.

Daemon record có type/ID/host/incarnation, payload chung + extension theo loại, source status và metric units.

### 11.1. Migration an toàn

- Dùng migration mới bổ sung schema; không sửa checksum migration đã phát hành.
- Giữ các bảng/FK cũ để đọc evidence lịch sử; không reset DB để bỏ UI cũ.
- Adapter read lịch sử phân biệt legacy OSD collection với As-is mới và ghi rõ phase mapping.
- Không sửa timestamp/hash/quality hoặc artifact cũ để giả đó là collection v5.
- Thay đổi config không được làm mất lịch sử. Khi đọc/export phải kiểm FSID và quyền hiện tại; khi so sánh cho phép config thay đổi nhưng nêu rõ.
- Soft-delete không sửa immutable payload; trạng thái hiển thị lưu ở registry/tombstone riêng.
- Kịch bản OSDMap lưu trong registry riêng với `kind=OSDMAP_PREVIEW`; không ghi kết quả giả định vào daemon As-is records. Tham chiếu map/collection nguồn được bảo vệ khi xóa mềm hoặc dọn blob.
- Backup DB/evidence trước migration; kiểm restore có thể thực hiện, giữ rollback ứng dụng tương thích schema.

## 12. Export và tính toàn vẹn

- JSON cho cấu trúc, CSV cho bảng, Markdown cho báo cáo, ZIP cho bundle.
- Manifest gồm ID, cluster/daemon scope, source times, generation time, quality/coverage, units và config/collector schema.
- ZIP có SHA256SUMS và source hash riêng với download hash.
- Redact password/token/keyring/private key/auth headers và URL chứa credentials; không đưa server filesystem path tùy ý ra client.
- CSV chống formula injection; Markdown/HTML không thực thi dữ liệu nguồn.
- Đọc artifact theo registry, kiểm containment/hash/size; không nhận path từ browser.
- Giới hạn rows/columns/nodes/depth/output và job quá lớn; không silent truncation.
- Live export ghi đúng dữ liệu mới vừa thu; saved export giữ nguyên provenance lịch sử.
- Người dùng không cần SSH/copy file thủ công để tải thông tin đang xem.
- Không xuất tập dữ liệu ngoài allowlist hoặc nối sang cluster khác chỉ vì collection cũ có nó.

## 13. Bảo mật, cấu hình và quyền đọc

- Private key/token/DB credentials ngoài image và ngoài Git.
- Host key bắt buộc pin/trust; FSID kiểm trước và sau thu khi cần.
- Executor private network; chỉ ingress API được expose đúng phạm vi.
- Fixed read commands, scope allowlist, no arbitrary shell/terminal.
- Không thay sudoers hoặc tắt TLS/host validation để làm collector chạy.
- Permission matrix tách đọc hệ thống, thu As-is, export, xóa/khôi phục collection.
- Xóa collection là ghi metadata ứng dụng, không mở các Ceph mutation.
- Production cần TLS/auth/least privilege và nghiệm thu nguồn metrics; lab read-only chạy được chưa đủ chứng nhận production.
- Không hard-code địa chỉ/FSID/OSD/pool lab vào logic; local profile có giá trị runtime riêng.
- Các capability không được hỗ trợ phải fail closed và được giải thích bằng tiếng Việt.
- Worker mô phỏng OSDMap không có Ceph key/token, không nối mạng cluster và không có action ghi map. Chỉ bước thu map dùng executor đọc; parser/process bị giới hạn tài nguyên theo mục 20.

## 14. Gỡ chức năng cũ khỏi sản phẩm

Lát cắt gỡ Benchmark và Dry-run phải bao gồm:

- Navigation, deep link, component/form/control và CSS riêng.
- API tạo/preflight/start/stop/status và discovery target của workload.
- Executor actions, helper runner, version metadata và COPY trong Dockerfile.
- Env/profile/config registry mẫu, deployment flags và phụ thuộc chỉ dùng cho các phần bị bỏ.
- Export source và tests riêng của chức năng bị loại; thêm regression bảo đảm đường cũ không còn gọi được.
- README/hướng dẫn hiện hành, release/version metadata và localhost image.

Không xóa:

- Migration/schema đã áp dụng hoặc evidence cũ mà chưa có quy trình kiểm tham chiếu.
- Thông tin/collector/capacity/metrics được Inventory hoặc Chỉ số cụm sử dụng.
- Pool/image/bucket/PG/daemon trên cluster.
- Tài liệu nâng cấp/benchmark độc lập bên ngoài console khi chưa có yêu cầu riêng.

Route đã bỏ phải trả lỗi rõ hoặc 404; bookmark cũ được đưa về trang hợp lệ với thông báo tiếng Việt, không đưa tới action khác âm thầm. File lịch sử/backups không được quảng cáo như hướng dẫn sản phẩm hiện hành.

## 15. Đóng gói image và vận hành portable

- Một OCI application image có version/digest và các role cần thiết: API/UI, executor, collector/worker.
- PostgreSQL, cấu hình, secret, evidence và job state bên ngoài image.
- Build không chứa key/token hoặc dữ liệu cluster.
- Không cài package tùy ý khi container khởi động.
- Root filesystem read-only, user non-root, cap-drop/no-new-privileges và writable mounts tối thiểu.
- Image mới không chứa helper workload đã bị bỏ.
- Thành phần phân tích OSDMap dùng `osdmaptool`/`crushtool` được pin phiên bản/digest và kiểm tương thích map; có thể là role/worker image riêng nếu dependency Ceph lớn. Không cài công cụ bằng network lúc container khởi động và không mount cluster credentials vào worker offline.
- Health/readiness tách DB, cấu hình, executor, SSH/FSID và nguồn metric theo capability.
- Không gắn app ready với mọi metric adapter đều có số liệu; những nguồn thiếu phải hiển thị rõ và không chặn inventory nguồn khác một cách sai.
- Docker Hub/registry publication là bước release riêng, không tự push khi chỉ sửa plan.
- Hỗ trợ online/offline với version/digest, schema compatibility, backup/restore và rollback đã kiểm.
- Cùng source/image mang sang cluster khác bằng profile, nhưng release/topology mới cần acceptance; không hứa mọi Ceph version tự động tương thích.

## 16. Thứ tự triển khai

Mỗi lát cắt phải kèm test, docs và checkpoint; không gộp trạng thái planned với delivered.

### L0 — Thu hẹp sản phẩm và Việt hóa khung

- Gỡ Benchmark/Dry-run UI/API/executor/config/package theo mục 14.
- Navigation tiếng Việt, xử lý bookmark cũ.
- Giữ SSH/inventory/metrics/evidence cũ không mất dữ liệu.
- Build image mới, kiểm localhost không còn hai mục bị loại.

### L1 — Danh mục daemon và chỉ số đọc mới

- Canonical identity đa daemon, bảng 10 dòng/trang và multi-selection.
- Xem/Export fresh source, system + daemon metrics, timestamp/window/error rõ.
- MON/MGR/OSD đầu tiên; bảng capability RGW/MDS/host process.
- Không dùng collection gần nhất như nguồn trực tiếp.

### L2 — As-is đa daemon, không session UI

- Form chọn daemon, giai đoạn, ghi chú; job thu mới và partial results.
- Schema collection mới, legacy reader và OSD deep extension.
- Lấy As-is/Lấy As-is và xuất cùng provenance, không trùng retry.
- Lịch sử có filter, không buộc upgrade plan/run.

### L3 — So sánh A/B và quản lý collection

- Same-type/same-FSID matcher, multi-daemon diff và date/type filters.
- Bỏ gate Before→After/session/config hash.
- Soft-delete/restore, reference checks/audit và source-deleted warning.
- Export saved/diff không recollect.

### L3a — Xem trước thay đổi OSDMap

- Thu map binary read-only, kiểm FSID/epoch/hash, fixed job directory và closed simulator protocol.
- MVP: CRUSH weight của một/nhiều OSD; trả diff PG/raw/up/acting/primary và phân bố theo OSD từ cùng map nguồn.
- Mọi biến thể state/reweight/affinity/CRUSH nâng cao cần capability test theo tool build, không mở option chỉ vì có trong tài liệu.
- Lưu/export giả định riêng, báo epoch drift và giới hạn dự đoán; kiểm không có đường Apply/ceph write.

### L4 — Bổ sung coverage và nghiệm thu

- Hoàn thiện nhóm A0/adapter còn thiếu và telemetry host/process.
- Việt hóa toàn bộ trường/trạng thái/lỗi.
- Test failure/restart/concurrency/limits/access và cluster acceptance.
- Update README/VALIDATION/release artifact, kiểm clean host deployment.

## 17. Test matrix bắt buộc

### 17.1. Fresh View/Export

- Hai lần bấm tạo hai lần đọc nguồn; timestamp/data phản ánh từng lần.
- Export sau Xem không dùng payload Xem cũ.
- Nguồn lỗi không fallback stale âm thầm; partial/null có lý do.
- Rate có đúng window/counter reset semantics; proxy/browser không cache fresh action.
- Response chậm của daemon A không ghi đè daemon B vừa được chọn.

### 17.2. Phân trang và selection

- Cluster >10 daemon: 10 dòng/trang, total/next đúng, sort ổn định.
- Chọn daemon qua nhiều trang/filter, UI đếm đúng.
- Export toàn lựa chọn không cắt về 10 hàng.
- Không tính host/pool/system summary thành daemon.
- Daemon ID trùng giữa các loại không gây collision.

### 17.3. As-is

- Bấm thu đọc mới, không cần session/upgrade plan.
- Cả ba giai đoạn; nhiều collection cùng giai đoạn.
- Một/nhiều daemon, một/nhiều loại; OSD sâu hơn loại khác.
- Required/optional command failure, missing source, giới hạn/timeouts/restart đều giữ kết quả/lỗi thật.
- Retry idempotent không tạo duplicate; bấm mới tạo collection khác.
- Evidence immutable/hash/redaction/coverage đúng.

### 17.4. Comparison

- Cho Trước↔Trong, Trong↔Trong, Sau↔Trước và A/B bất kỳ cùng loại/FSID.
- Khác loại/FSID bị chặn ở UI và API.
- Khác config/session không tự chặn; config khác hiện trong diff.
- Same-ID matching, only-A/only-B, incarnation drift, missing metric và counter reset.
- Selected intersection/subset không đòi toàn scope hai bên giống hệt.
- Lọc ngày đúng timezone/biên cuối ngày.
- Export diff giữ hai source ID/hash/thời gian, không gọi Ceph lại.

### 17.5. Xóa/khôi phục và an toàn

- Một/nhiều collection, xác nhận chính xác và scope authorization.
- Không xóa đang thu, không cascade refs/evidence cũ, không gọi Ceph write.
- Deleted source comparison có cảnh báo; restore giữ original bytes/hash.
- Audit actor/time/reason; purge riêng không tự mở trong MVP.
- Migration không sửa file cũ; backup/restore và DB permission tests.
- Key/token không xuất hiện trong image/log/export.
- API/executor workload và dry-run đã bỏ không còn callable.
- Inventory/metrics/export và công cụ cũ cần giữ không bị regression.

### 17.6. OSDMap preview

- Kịch bản không đổi tham số có diff rỗng; map nguồn/hash không đổi sau chạy.
- Fixture có PG remap/primary đổi và weight-set/override: raw/up/acting được phân biệt, không tự clear-temp hoặc mark-up-in để làm đẹp kết quả.
- Thay nhiều CRUSH weight áp dụng đủ mục; option state lặp không được âm thầm chỉ đổi OSD cuối.
- Kiểm `mark-out`, `mark-in` và persistence thực tế theo tool build; adapter không đúng ý định phải báo chưa hỗ trợ.
- FSID sai, epoch drift, map hỏng, schema/tool không tương thích, thiếu pool/OSD và output truncated đều có lỗi/coverage rõ.
- Kiểm blast radius toàn phạm vi cho phép; không chỉ thống kê PG của OSD nguồn mà bỏ PG ngoài mục tiêu.
- Counter/performance/recovery không có dữ liệu dự báo; không tạo IOPS/latency/ETA giả hoặc nhãn an toàn vận hành.
- Không có network/credential trong worker; API không nhận argv/path/command tùy ý, không chạy output upmap như shell.
- Export lưu đúng source hash, thông số, tool build, kết quả và nhãn Dự đoán; không lẫn vào collection thực hoặc comparison As-is.

## 18. Definition of Done

Chỉ công bố v5 hoàn tất khi:

- Navigation hiện đúng Tổng quan, Chỉ số cụm và daemon, Thu thập hiện trạng, So sánh, Công cụ cũ.
- Không còn chức năng chạy workload hoặc Dry-run trong sản phẩm hiện hành.
- Bảng 10 daemon/trang; chọn/export nhiều daemon đúng scope.
- Xem/Export trực tiếp thu mới, có source times/window/quality, không dùng snapshot cũ thay nguồn.
- As-is hỗ trợ các loại đã công bố, OSD deep data, Trước/Trong/Sau và không có Upgrade session UI.
- So sánh hai collection tùy ý cùng loại/FSID, ngày/type filters và multi-daemon matcher đúng.
- Xóa mềm/khôi phục hoạt động, không mất dữ liệu được tham chiếu hoặc tài nguyên Ceph.
- Toàn UI/hướng dẫn tiếng Việt; metric key/raw identity giữ nguyên.
- Tests, browser verification, real read-only cluster acceptance và download/hash checks có bằng chứng.
- Image/version đang chạy khớp source đã kiểm; docs nêu rõ adapter nào còn thiếu.
- Không dùng chất lượng dữ liệu/so sánh thay kết luận an toàn nâng cấp.
- Có xem trước OSDMap cho các loại thay đổi đã công bố, báo chênh placement và epoch drift; không thay đổi cluster và không trình bày dự đoán như kết quả thực.

## 19. Tài liệu liên quan

- [Code console](rgw-console/)
- [README console](rgw-console/README.md)
- [Tổng quan trong thư mục code](README.md)
- [OSD collector](osd-info-collector/README.md)
- [Validation](rgw-console/VALIDATION.md)
- [Cấu hình SSH local](rgw-console/docs/LOCAL_SSH_READONLY.md)
- [Plan chiến lược dự án](../plan-tổng.md)
- [Tài liệu osdmaptool — Pacific](https://docs.ceph.com/en/pacific/man/8/osdmaptool/)
- [Mã nguồn osdmaptool — Ceph v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/tools/osdmaptool.cc)
- [Đọc OSDMap từ cluster — Pacific](https://docs.ceph.com/en/pacific/rados/operations/control/)
- [CRUSH map tool — Pacific](https://docs.ceph.com/en/pacific/man/8/crushtool/)

Tài liệu phụ có menu/contract cũ sẽ được cập nhật trong L0–L4. File tham khảo OSD validation do người dùng từng gửi không còn ở đường dẫn cũ lúc rà soát; bảng A0 trên được giữ từ yêu cầu đã cung cấp, không coi file thiếu là bằng chứng đã nghiệm thu.

## 20. Xem trước thay đổi bằng osdmaptool

**Mục tiêu:** trước một thay đổi ảnh hưởng placement, xem map hiện tại và map giả định khác nhau ở đâu, trên PG/OSD nào, mà không tác động cluster. Localhost đã có adapter CRUSH weight cho pool replicated trên Pacific 16.2.15; các thao tác khác trong bảng dưới vẫn là kế hoạch. Phạm vi đã kiểm và gate còn thiếu nằm ở mục 21–23.

### 20.1. Phạm vi hỗ trợ và capability

Không diễn giải “thay đổi bất cứ gì” thành một bộ giả lập toàn Ceph. `osdmaptool` xử lý OSDMap/placement; công cụ có test mapping, thay CRUSH weight và nhúng CRUSH map trên file. Các option phải được kiểm trên đúng bản đóng gói, không chỉ đọc help. [Tài liệu Pacific](https://docs.ceph.com/en/pacific/man/8/osdmaptool/).

| Thay đổi dự định | Chính sách triển khai |
|---|---|
| CRUSH weight một/nhiều OSD | MVP theo CRUSH reweight native Pacific: `--adjust-crush-weight` đồng bộ weight-set của item/parent; trả effective weight và dấu hiệu choose_args thay đổi. Dải đã kiểm 0–32767, có lượng tử hóa 1/65536 |
| In/out/up/down, override reweight, primary-affinity | Chỉ mở khi adapter offline tái hiện đúng ý định và có fixture theo tool build; chưa hỗ trợ thì khóa form, nêu lý do |
| CRUSH rule/topology/class, compat weight-set, choose_args | Lát cắt sau: xử lý bản CRUSH cục bộ bằng adapter kiểm soát, nhúng vào bản map riêng, kiểm rule/device IDs và semantics |
| Upmap/primary override, pool size/PG config | Lát cắt sau theo capability/version; không tự sinh rồi chạy các lệnh lên cluster |
| Đổi phiên bản/image OSD hoặc cấu hình MON/MGR/RGW/MDS không ảnh hưởng OSDMap | Không dự báo bằng osdmaptool; hiển thị thay đổi thông số dự định và giới hạn, dùng As-is thực để kiểm tra sau |
| IOPS/latency, peering, thời gian recovery hoặc an toàn stop daemon | Ngoài khả năng dự báo của map tool; không đưa ra số đo giả hoặc PASS/HOLD vận hành |

CRUSH weight khác override reweight và primary-affinity; không dùng thao tác này thay cho thao tác kia. Có thể hỗ trợ nhiều tham số trong một kịch bản nếu adapter chứng minh đầy đủ; tuyệt đối không bỏ qua trường chưa hỗ trợ.

Điểm cần kiểm ở Pacific: mã nguồn tag v16.2.15 giữ một biến cho OSD mark-out, thao tác này còn đặt UP; nhánh mark-in dùng biến mark-up. Vì vậy không ghép tùy chọn lặp để giả mô phỏng nhiều OSD hoặc coi chúng là semantics chuẩn của lệnh online. State thay đổi trong bộ nhớ cũng không mặc nhiên có trong file xuất. Những trường hợp này phải kiểm bằng dump/mapping thực và khóa capability nếu sai. [Mã nguồn theo tag](https://github.com/ceph/ceph/blob/v16.2.15/src/tools/osdmaptool.cc).

### 20.2. Thu map mới và giữ nguyên baseline

- Mỗi bấm **Tính tác động** lấy map binary mới từ cluster bằng fixed read action, tương đương `ceph osd getmap`; không dựng map giả bằng createsimple rồi gọi đó là cluster thật. [Ceph control commands](https://docs.ceph.com/en/pacific/rados/operations/control/).
- Kiểm FSID, epoch, thời gian nguồn, SHA-256 và tool compatibility; lưu map gốc bất biến trong artifact store được kiểm containment.
- So sánh baseline/candidate đều bắt đầu từ **cùng một map gốc**, cùng pool/PG scope và cùng tool build; chỉ candidate áp dụng bộ thông số dự định.
- Không ghi đè map gốc. Worker dùng thư mục job riêng, tạo bản làm việc riêng; không nhận đường dẫn từ browser.
- Giữ nguyên upmap/pg_temp/primary_temp và flags; không tự clear-temp/mark-up-in/balancer. Với MVP CRUSH reweight native, weight-set/choose_args liên quan được tool đồng bộ và phải báo rõ/hash trước–sau. Không mô tả thao tác này là canonical weight độc lập giữ nguyên compat weight-set. [Default update_weight_sets=true](https://github.com/ceph/ceph/blob/v16.2.15/src/crush/CrushWrapper.h#L935-L944).
- Đọc epoch/identity lúc thu và lúc hoàn tất. Nếu cluster đổi map, kết quả vẫn là dự đoán của epoch đã lưu nhưng phải ghi **Map gốc đã cũ — tính lại trước khi thay đổi**. Không cập nhật kết quả cũ bằng cách đổi epoch/hash.
- Khi mở lại scenario đã lưu, API đọc epoch hiện tại riêng để kiểm drift; nếu không đọc được phải báo **Chưa xác minh với cluster hiện tại**, không coi lịch sử là dự đoán mới.
- Không gọi epoch giả định của file candidate là epoch đã được cluster chấp nhận.

### 20.3. Kết quả phải xem được

- Bảng **Hiện tại theo map gốc / Dự kiến theo kịch bản / Chênh lệch** cho từng PG.
- Dùng output có raw/up/acting và primary khi bản tool hỗ trợ; parser giữ đúng nghĩa từng tập, không gọi acting từ map là peering/replica availability đã kiểm ngoài cluster. Source v16.2.15 có output chi tiết này qua test-map-pgs-dump-all. [Mã nguồn output](https://github.com/ceph/ceph/blob/v16.2.15/src/tools/osdmaptool.cc#L609-L659).
- Tổng PG đã kiểm, PG đổi membership, đổi thứ tự/primary, số PG dự kiến vào/ra từng OSD, OSD/pool/failure domain bị tác động.
- Replicated pool và EC pool phải có capability/fixture riêng; với EC giữ thứ tự shard và profile/rule, không diễn giải shard placement thành số bản sao replicated. Phạm vi chưa nghiệm thu phải báo chưa hỗ trợ.
- Thống kê theo raw/up/acting riêng; tính từ PG records đầy đủ, không chỉ summary của tool vì có thể không liệt kê OSD weight=0/out.
- Hiện PG chưa map đủ thành viên, OSD không hợp lệ/trùng và vi phạm rule/failure domain mà adapter kiểm được, kèm phạm vi/cách kiểm. Không gọi đây là trạng thái HEALTH của cluster thật.
- Filter OSD/pool/PG và phân trang; tổng kết phải tính trên toàn phạm vi đã kiểm, không cắt theo trang.
- Khi người dùng chọn OSD nguồn/đích, vẫn phải tính và báo **ảnh hưởng ngoài các OSD mục tiêu**. Nếu chỉ kiểm một pool, ghi rõ không bao phủ pool khác; không được tuyên bố không ảnh hưởng toàn cluster.
- PG di chuyển không đồng nghĩa byte di chuyển. Nếu sau này ước lượng bytes từ PG stats, phải ghi thời điểm/độ tin cậy và điều kiện ước lượng; MVP không đoán dung lượng hoặc ETA từ số PG.
- Weight nhỏ không là quota PG. Chênh lệch bằng 0 có thể đúng do weight-set/override; phải giải thích coverage và dữ liệu kiểm, không tự xóa override để tạo kết quả mong muốn.

### 20.4. Form, lưu lịch sử và export

- Form chỉ có thao tác đã kiểm: loại thay đổi, OSD IDs, giá trị cũ/mới và pool/PG scope. Validator kiểm OSD tồn tại, finite/range, precision/rounding và duplicate/conflict.
- Chỉ hiển thị **Tính tác động / Lưu kịch bản / Xuất dự đoán / Tính lại với map mới**. Không có Apply, chạy lệnh sinh ra hoặc submit map lên Ceph.
- Thay form làm kết quả cũ thành **Chưa tính cho cấu hình này**; không tái sử dụng báo cáo cũ cho thông số mới.
- Mỗi kết quả có scenario ID, base FSID/epoch/hash, input parameters/hash, tool version/binary digest, source times, scope/coverage, effective candidate dump/mapping hashes và lỗi.
- Nếu thay đổi chỉ tồn tại trong bộ nhớ, manifest ghi rõ và lưu thông số + effective output để tái tạo. Chỉ lưu candidate binary khi đã kiểm nó thực sự chứa thay đổi; không xuất bản sao gốc rồi gắn nhãn map đã đổi.
- Lưu/xuất JSON/CSV/Markdown/ZIP có nhãn **Dự đoán — chưa áp dụng**. Saved export dùng bản đã lưu; nút tính lại thu map mới và tạo scenario mới.
- Không nhập scenario vào lịch sử As-is thực. Comparison A/B trong mục 8 tiếp tục chỉ so hai lần thu thực cùng loại daemon; một panel dự đoán riêng có thể liên kết collection nguồn.
- Scenario có xóa mềm/khôi phục và reference checks tương tự lịch sử collection; không xóa nguồn dùng chung hoặc map của job khác.

### 20.5. An toàn, đóng gói và nghiệm thu

- Chỉ executor đọc map được giữ quyền Ceph; mô phỏng chạy offline, không keyring/token, network hoặc shell input tùy ý.
- Tool version/binary digest được pin, hỗ trợ decoding của map đích và có ma trận fixture theo release; không dùng bản latest mặc định cho mọi cluster.
- CRUSH thay đổi nâng cao có thể cần `crushtool` để xử lý/kiểm bản cục bộ; công cụ này không thay thế full OSDMap PG/pool semantics. [Tài liệu crushtool](https://docs.ceph.com/en/pacific/man/8/crushtool/).
- Closed argv, tối thiểu quyền filesystem, giới hạn CPU/RAM/thời gian/map bytes/PG output, exit code và parser version. Map hỏng/lớn hoặc tool lỗi phải báo chưa tính được, không trả preview rỗng như không thay đổi.
- Không mặc nhiên tin uploaded map/CRUSH file; MVP dùng map đọc từ cluster và typed changes. Import file chỉ mở sau validation/sandbox được nghiệm thu.
- Không dùng `ceph osd setmap/setcrushmap`, ceph osd out/reweight hoặc các lệnh upmap trong quá trình xem trước; không thực thi command output của tool.
- Nghiệm thu gồm fixture không đổi/đổi weight/nhiều OSD/overrides/failure-domain, version gotchas, source drift, export integrity và proof không có lệnh ghi Ceph. Chỉ công bố capability đã đạt.
## 21. Trạng thái triển khai và giới hạn bản preview

Ngày 12/10/2026, localhost đã chạy `dang7904/storage-lab-console:5.1.0-rc.1`, schema 0021 và worker riêng `dang7904/storage-lab-osdmap:16.2.15-rc.1`. Đây là release candidate chỉ đọc, không đánh dấu toàn bộ Definition of Done hay nghiệm thu production đã hoàn thành.

Đã triển khai/kiểm tra:

- Gỡ màn hình/API/executor/runner/config Benchmark khỏi console; gỡ router Dry-run hoạt động. Migrations/session/evidence lịch sử giữ nguyên. Các tài liệu benchmark/MOP ở ngoài `code` không bị xóa.
- Navigation chính tiếng Việt: Tổng quan, Chỉ số cụm và daemon, Thu thập hiện trạng, So sánh; nhóm Công cụ cũ thu gọn.
- Xem/Xuất trực tiếp thu mới qua CLI; hai scrape Prometheus trong cùng yêu cầu cho cửa sổ IOPS/throughput. MON/MGR/OSD/RGW/MDS có adapter metadata/version/image/host theo khả năng nguồn. MDS ghép FSMap active/standby với orchestrator; RGW giữ thời điểm cache orchestrator thật. CPU/RAM container lấy từ orchestrator với thời điểm/chất lượng nguồn. Mẫu quá cũ hoặc timestamp tương lai bất hợp lệ không được xem là mới; schema nguồn sai không giả làm danh sách daemon rỗng hợp lệ.
- 10 daemon mỗi trang, chọn nhiều trang, chọn tập lọc và export đủ lựa chọn; đã kiểm danh sách 14 daemon thật trên hai trang.
- As-is tự chứa FSID/cấu hình/provenance, ba giai đoạn, không cần Upgrade session UI; một lần Lấy As-is và xuất lưu/tải cùng collection.
- Môi trường A0.1 qua helper 1.0.5: host/OS/kernel, Python, shell có provenance, Ceph/RBD/Rados/SSH/tool versions, thời điểm và NTP properties. Phạm vi chỉ SSH client host, không đọc key/env dump/process command line và không suy ra clock offset/PASS toàn cụm. Probe thiếu/thất bại được ghi PARTIAL.
- Lịch sử máy chủ dùng cursor keyset `(started_at,id)`, mặc định 10 collection/trang, không cắt tổng số ở 200. Tìm ID/daemon/ghi chú/chất lượng/daemon key được lọc trên server. Giữ lựa chọn qua trang; chọn A/B ở hai trang khác nhau. Collection xóa mềm vẫn xem/xuất được khi chủ ý bao gồm đã xóa; cần khôi phục trước khi so sánh.
- So sánh A/B bất kỳ cùng loại/FSID, lọc ngày UTC+7/loại/giai đoạn/daemon, union coverage, metric delta có kiểm unit/quality/incarnation/reset. Xóa mềm/khôi phục giữ nguyên payload/checksum và ghi audit event.
- OSD deep giữ raw collector, cluster context, CRUSH JSON/choose_args, PG dump brief/up/acting và override theo khả năng nguồn. Độ phủ A0.1–A0.8 và thiếu dữ liệu được ghi trong `system.coverage`.
- Mô phỏng CRUSH reweight native Pacific một/nhiều OSD trên map mới; trả diff raw/up/acting/primary, phân bố OSD cả weight-zero, effective weight và hash choose_args trước/sau. Worker không có network hoặc credential Ceph. Không có Apply.
- Kiểm real-data pool 13: PG 13.0 gốc acting `[0,2,1]`, giả định `[0,5,1]`; acting primary vẫn 0, raw primary đổi 2→5. Map thật không được sửa bởi kịch bản. Export có nhãn Dự đoán, timestamp, scope và checksum.
- Backend 292 test qua toàn bộ, không bỏ qua sau khi dùng PostgreSQL test cô lập; frontend 20 test và TypeScript qua; executor/SSH 25 test qua; helper 26 test qua; worker 11 test gồm tool thật và upmap đã qua. Có kiểm live database cho tạo/đọc/so sánh/xóa/khôi phục, truy vấn lịch sử keyset và tải file qua browser. Adapter kiểm config hiệu lực của từng MON và chỉ cho dự đoán khi MON 16.2.15 đồng bộ weight-set=true. Release khóa EC/unknown pool, kiểm allowlist và báo mapping thiếu thành viên, không tự kết luận failure-domain.

Còn lại trước nghiệm thu đủ v5/production:

- Request/session metrics và host/process/network telemetry đầy đủ cho RGW/MDS; percentile latency không được dựng từ average. MDS active/standby đã kiểm fixture; lab hiện không có MDS để nghiệm thu daemon chạy thật.
- Môi trường/tool versions từng daemon host/container ngoài SSH client, RBD read-only context, service specs/upgrade status, clock offset toàn cụm/crash/helper an toàn đầy đủ. CRUSH binary riêng chưa được export trong As-is.
- Collection hiện thu đồng bộ có giới hạn 128 daemon/16 MiB; cần job tiến độ và phân trang danh mục daemon server cho cluster lớn. Cursor lịch sử collection đã triển khai, không còn giới hạn tổng lịch sử 200.
- Hướng dẫn/nhãn công cụ legacy ngoài luồng chính còn cần hoàn tất Việt hóa. Lịch sử OSD/session cũ còn API tương thích; chưa có projection import vào danh sách As-is mới.
- Mô phỏng down/out/in, override reweight, affinity, topology/rules/pool config, release khác, purge/xóa/khôi phục kịch bản và ma trận fixture EC/override/weight-set rộng hơn là các lát cắt sau. No-op của thao tác native không đồng nghĩa chỉ nhập lại canonical weight khi compat weight-set khác; phải xem hiệu ứng weight-set.
- Chỉ linux/amd64 đã build/kiểm/publish. Scan ứng dụng không phát hiện CVE tại lần kiểm; worker Ceph cũ còn 9 Critical/333 High nên **không bật production**. Production destination/cluster thứ hai, multi-architecture/signature/full offline acceptance vẫn chưa nghiệm thu. Compose overlay offline worker chỉ dành lab; phát hành registry không tự cập nhật deployment đích.

Đối chiếu [VALIDATION.md](rgw-console/VALIDATION.md), [README](README.md) và [hướng dẫn OSDMap](rgw-console/docs/OSDMAP_PREVIEW.md) trước khi dùng image trên hệ thống khác.

## 22. Release candidate 5.1.0-rc.1 — 12/10/2026

- Docker Hub ứng dụng: `dang7904/storage-lab-console:5.1.0-rc.1`; digest `sha256:36b6b7b1664958b792dda841cf7140ab9e0006d3aff436d8b8823056451c86f4`.
- Worker lab/offline: `dang7904/storage-lab-osdmap:16.2.15-rc.1`; digest `sha256:65025d1fb24e90b87ec623b805946bcc6252bce43f8bfd198e70d6ef2a63cdad`.
- Cả hai tag đã xác minh trạng thái active qua Docker Hub API, manifest registry và pull theo digest; không ghi đè bản v3 hay tag latest.
- Sửa race/debounce/double-click và phản hồi async cũ; export stream giới hạn 16 MiB và bắt buộc SHA-256/WebCrypto, HTTP ngoài localhost phải dùng HTTPS.
- Sửa dữ liệu nguồn sai/NaN/Infinity/timestamp cũ hoặc tương lai; metric có timestamp đúng nguồn; không tính delta khi loại metric đổi hoặc số vượt giới hạn. Lịch sử ngoài scope hiện tại trả 403 cho xem/xuất/so sánh, không sửa payload; vẫn xóa/khôi phục metadata được.
- Image/env mẫu mặc định chỉ đọc, tắt mutation/legacy writes. HTTPS/auth/CSRF/least-privilege DB đã kiểm trên deployment riêng, không dùng secret/DB/Ceph của lab để test production bootstrap.
- Script backup/restore dùng schema theo image, giữ lịch sử migration; đã khôi phục offline schema 21, 21 checksum migration, 2 As-is synthetic gồm 1 bản xóa mềm, 1 evidence/hash liên kết. Unicode/float/null và SHA giữ nguyên. Đây không phải nghiệm thu RPO/RTO của site đích.
- [Release manifest](rgw-console/deploy/releases/5.1.0-rc.1.yaml) ghi digest, SBOM/scan hash và các gate PASS/PARTIAL/NOT_RUN. Worker có CVE công khai; giảm quyền/network-none không thay thế bản vá. Không gọi toàn bộ bộ công cụ là production-ready.

## 23. Nhánh kiểm thử local sau RC1 — 13/10/2026

Tại thời điểm kiểm thử nhánh này, Docker Hub và localhost chưa thay; RC1 trong mục 22 còn đang chạy. Trạng thái local sau yêu cầu đổi cấu hình được ghi riêng ở mục 26. Không thay giao diện So sánh, DB schema, SSH profile hoặc dữ liệu Ceph.

- Backend yêu cầu handshake đầy đủ: version/commit đã kiểm, parser 2, pool replicated, đúng thao tác CRUSH weight và đúng SHA hai tool. Từ chối heartbeat không hữu hạn/cũ/tương lai, field thiếu, binary khác, cờ thành công không phải boolean và mã lỗi không hợp lệ. Kết quả phải khớp handshake và pool yêu cầu trước khi lưu evidence; hồ sơ dự đoán cũ vẫn được đọc/xuất như trước. Đây là kiểm hợp đồng dữ liệu, không phải attestation mật mã của worker.
- Đã build ứng dụng local `storage-lab-console:5.1.1-preview.1`, index `sha256:8fee0b7383ceb64a4b464ff0dadaad7f8fc6b52a9f132d42eb83123b60eea3cc`; source service trùng checksum trong image. Backend 296/296 test qua trên PostgreSQL test cô lập, không bỏ qua. Fixture lab có policy rõ ràng, không kế thừa `CONSOLE_READ_ONLY=true` của runtime để làm sai mục tiêu test; bảo vệ production không bị tắt. Scout kiểm 167 package của ứng dụng, không phát hiện CVE trong lần kiểm này.
- Worker thử nghiệm `storage-lab-osdmap:16.2.15-minimal-preview.1`, index `sha256:452ba2b9b3e4c1660b5e1e89a45b0d2a8aba6190d4d0bfa84d058403b147cff5`. [Dockerfile.minimal](rgw-console/packaging/osdmap/Dockerfile.minimal) lấy đúng hai tool và `libceph-common.so.2` từ donor Ceph đã pin, chạy trên UBI8-minimal được pin và cập nhật bằng repo chính thức. Không copy system library cũ hay giả RPM database. Giữ license/source URLs, manifest dependency closure 22 mục, 114 RPM thật và SBOM riêng cho hai package Ceph được trích file.
- Cả ba ELF Ceph giữ đúng checksum; 17/17 worker test qua ở cả RC1 và runtime mới. Ba kịch bản trên cùng map tạo offline (no-op, nhiều weight, pg_upmap_items) cho cùng raw/up/acting/primary, CRUSH bytes, effective weight, choose_args và parser diagnostics. Chỉ chuẩn hóa một dòng stdout chứa đường dẫn thư mục tạm xuất CRUSH; raw stdout và kết quả/hash gốc được giữ riêng. SHA bản so sánh canonical: `b5dad984d27f13ff56b1c093222dc6ceb106f830af29217828b35332457742d5`.
- Scan toàn worker mới: 144 package được index, raw findings 1 Critical / 28 High / 40 Medium / 6 Low / 0 unspecified (RC1: 9 / 333 / 1333 / 481 / 18). Scout ghi SQLite `CVE-2026-51302` Critical/Not Fixed, nhưng [CNA đã rút bản ghi ngày 31/07/2026](https://cveawg.mitre.org/api/cve/CVE-2026-51302) vì không phải vấn đề bảo mật; phải phân biệt scanner finding với vulnerability đã xác nhận. Giữ raw report/checksum, không gọi “đã vá” hoặc tự suppress để vượt gate. Scan SBOM Ceph trích file không phát hiện CVE nhưng không chứng minh mã Pacific đã hết rủi ro hoặc mọi backend được nạp động đã được thử. **Worker mới vẫn chưa đạt gate production; không tự promote, publish hoặc cập nhật deployment.**

Biên bản: [VALIDATION](rgw-console/VALIDATION.md), [manifest local preview](rgw-console/deploy/releases/5.1.1-preview.1.yaml), [hướng dẫn runtime tối giản](rgw-console/docs/OSDMAP_PREVIEW.md#runtime-tối-giản-thử-nghiệm-chưa-phát-hành). Sau khi chọn hướng tiếp theo cần xử lý CVE residual và nghiệm thu integration/môi trường đích; không dùng việc giảm package hoặc test fixture để tuyên bố toàn bộ plan hoàn tất.

## 24. Integration và triage sau preview — 13/10/2026

- API/middleware/service/repository của app preview, worker tối giản thật và PostgreSQL 16/schema 21 đã qua **38/38 kiểm tra synthetic**. Hai scenario được lưu DB/artifact; checksum, export bất biến/không thu lại, epoch drift, CSRF/no-Apply, capability lỗi và kết quả sai identity trước save đều được kiểm. Dataset tạo offline có metadata từ cùng map; không nối Ceph thật hoặc dùng credential lab. Script được khóa bằng marker opt-in + tên DB synthetic/host internal; spool/evidence/DB tách biệt, dữ liệu chứng minh giữ riêng.
- [Báo cáo security triage](rgw-console/docs/OSDMAP_SECURITY_TRIAGE.md) đối chiếu 29 raw Critical/High: 15 vendor-fixed đúng RPM EVR/product/component, 5 vendor-not-affected, 4 CNA-rejected, 5 vendor-affected. Giữ nguyên raw Scout/count/hash; không VEX/suppress/waiver. Không gọi CVE SQLite đã bị rút là “còn Critical chưa vá đã xác nhận”.
- Năm finding vendor-affected cần tiếp tục xử lý: GnuTLS hai CVE, OpenSSL, PCRE2 và Expat. GnuTLS có thể được bỏ nếu solver uninstall được package-manager extras mà giữ closure/RPM metadata/chown/runtime; ba core component khác cần bản vá vendor hoặc runtime/adapter mới có fixture và pin mới. Không ép `--nodeps`, giả ABI OpenSSL3 thành 1.1 hoặc xóa file để che scanner.
- Gate synthetic integration đổi thành PASS trong manifest local; **live-cluster/site acceptance và production vẫn chưa đạt**. Tại thời điểm kiểm thử này chưa publish/promote/thay localhost; việc đổi local theo yêu cầu riêng ở mục 26 không phải promote production. Giao diện So sánh và image RC1 đã phát hành vẫn giữ nguyên.

## 25. Worker preview.2 sau gỡ package quản lý — 13/10/2026

- Build local `storage-lab-osdmap:16.2.15-minimal-preview.2`, index `sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893`, flag `STRIP_PACKAGE_MANAGER_EXTRAS=true`. Gỡ thật 13 package qua solver; không fake RPM metadata, dùng `--nodeps` hoặc che scanner. Tool/library pins, 22 dependencies, RPM query/chown/Python và UID 10001 giữ nguyên; build cập nhật glibc/libxml2, có 103 RPM headers.
- 17 worker tests và 3 differential scenarios đạt. API–worker–Postgres synthetic có 4 lượt liên tiếp 38/38 PASS sau thêm diagnostics. Lượt đầu lỗi ở kiểm tampered identity sau 32 bước, chưa tái hiện/xác nhận nguyên nhân; giữ report lỗi và stability review OPEN. DB chỉ có hai artifact hợp lệ của lượt đó, không lưu kết quả sai thứ ba. Không dùng retries để xóa lỗi khỏi acceptance.
- Guard script synthetic reject libpq query/fragment và environment override đích DB trước mở pool; 9 guard tests đạt. Đây là fixture safety, không tắt policy production.
- Raw Scout còn 1 Critical/21 High/35 Medium/2 Low; triage 22 C/H là 12 vendor-fixed, 3 not affected, 4 CNA-rejected, 3 vendor-affected (OpenSSL/PCRE2/Expat). Không sửa raw finding hoặc tạo waiver. Compressed size 80 MB so với preview.1 66 MB; bớt package không mặc nhiên làm ít layer bytes hơn.
- [Manifest preview.2](rgw-console/deploy/releases/osdmap-16.2.15-minimal-preview.2.yaml) và VALIDATION ghi rõ tag/digest/checksum/report lỗi/PASS. **Tại thời điểm kiểm thử này chưa publish/promote/thay localhost; production gate chưa đạt.** Cấu hình local hiện tại ở mục 26; residual affected, lỗi đầu chưa xác nhận và site acceptance vẫn phải xử lý.

## 26. Đổi cấu hình localhost lab — 13/10/2026

- Theo yêu cầu đổi cấu hình, localhost `http://127.0.0.1:8080` dùng app `5.1.1-preview.1`, digest `sha256:8fee0b7383ceb64a4b464ff0dadaad7f8fc6b52a9f132d42eb83123b60eea3cc`, và worker `16.2.15-minimal-preview.2`, digest `sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893`. [Cấu hình opt-in](rgw-console/deploy/local-images.preview.json) pin image local; default RC1/production env không đổi.
- Đã backup DB vào thư mục runtime riêng với ACL hạn chế trước migration/recreate; schema vẫn 21, không có migration chờ. Giữ nguyên DB/container/volume, bốn collection và SHA/deletion state/tám events, tám file evidence cũ cùng checksum, mọi SSH/config/token mounts. Container RC1 cũ giữ ở trạng thái dừng để rollback, không xóa volume.
- Bốn app role và worker mới chạy UID 10001/rootfs chỉ đọc/cap-drop ALL/no-new-privileges. API chỉ publish loopback 8080; worker network-none, CPU 1/RAM 1536 MiB/PIDs 32, chỉ mount spool. `CONSOLE_READ_ONLY=true`, mutation/lab/legacy writes tắt. Readiness/schema, capability/parser/tool hashes, so sánh và export lịch sử đạt.
- Smoke thực tế chỉ đọc: observe MON/OSD mới theo request trả đúng FSID; quality PARTIAL do nguồn CPU/RAM orchestrator cũ, không giả thành VALID. Mô phỏng offline no-op `osd.2`/pool 13 có epoch 3888, 0 PG thay đổi, không lưu map ứng viên; export kiểm SHA. Không tạo collection As-is mới hoặc thay cấu hình Ceph.
- Đây chỉ là **local lab smoke**, không đóng lỗi integration đầu hoặc production gate. Ba vendor-affected và stability review OPEN được giữ. Không push/tag lại Docker Hub, không thay production-test 8443, không chạy nâng cấp/Apply/Ceph write. [Biên bản chuyển cấu hình](rgw-console/deploy/releases/localhost-20261013-preview.yaml).

## 27. Sửa lỗi So sánh và thông báo dung lượng — 13/10/2026

- Đã tái hiện việc đổi bộ lọc giai đoạn làm xóa cả A/B trên preview.1. Preview.2 chỉ reset lựa chọn/kết quả khi đổi loại daemon; giữ A/B qua ngày, giai đoạn, từ khóa và trang lịch sử. Chọn A ở Trước rồi B ở Sau, đổi ngày/tìm kiếm và so sánh ba RGW cũ đã kiểm trực tiếp trên browser; đổi sang OSD xóa đúng A/B và kết quả.
- Snapshot dung lượng trước đây có state cảnh báo nhưng `reasons=[]`, làm UI ghi “Chưa có cảnh báo”. Backend mới thêm OSD, phần trăm dùng và ngưỡng policy đã chạm; giữ ghi chú vận hành/cảnh báo nguồn cũ hoặc scope thiếu. UI chỉ dùng thông báo không cảnh báo khi NORMAL; trạng thái scope thiếu có nhãn tiếng Việt. Ô chọn daemon dùng 16×16 px, không kế thừa kích thước ô nhập văn bản.
- App local `storage-lab-console:5.1.1-preview.2`, index `sha256:44c809d6ebc46c66e43152b746ba167e83fbbcebfa6f905bcd79c21f0c395c84`, đã build và cập nhật localhost. 20 frontend tests, TypeScript/build và 61 backend tests liên quan đạt. Không đổi schema hoặc dữ liệu lịch sử; backup riêng trước swap, bốn collection/tám events/chín file evidence cùng SHA giữ nguyên.
- API/worker/DB synthetic sau khởi động worker từ trạng thái dừng đạt 38/38, marker xác nhận tamper injection đã chạy và trả 503 trước lưu kết quả sai. Lỗi đầu lịch sử vẫn chưa tái hiện hoặc xác định nguyên nhân; stability OPEN/production NOT_PASSED giữ nguyên. Browser kiểm tải JSON ở lượt này bị từ chối quyền tải xuống, không dùng cách khác để vượt chặn; test export/checksum synthetic đạt.
- [Manifest bản sửa](rgw-console/deploy/releases/5.1.1-preview.2.yaml) và [VALIDATION](rgw-console/VALIDATION.md) ghi kết quả/giới hạn. Worker vẫn preview.2, chưa publish Hub hoặc triển khai production.

## 28. Bổ sung chẩn đoán report integration — 13/10/2026

- Runner test tạo report schema 2 cho mọi request, giữ HTTP status/code, tên bước, worker envelope và exception, thời lượng, source calls và thay đổi DB/artifact. Lỗi không có response ghi HTTP null; service được nối đúng request, không dùng trace của request trước. Lỗi logging phụ không che lỗi gốc. Report mới lưu nguồn runner/diagnostic bất biến theo SHA, không lưu body/credential/env/SQL.
- 26 unit tests và bốn tình huống lỗi chủ động tạo đã kiểm contract; lượt integration bình thường đạt 38/38. Worker thật trên map hỏng trả 409/OSDMAP_TOOL_FAILED và có envelope trong report ngay từ create đầu. [Hướng dẫn](rgw-console/docs/INTEGRATION_REPORTING.md) · [Manifest](rgw-console/deploy/releases/integration-reporting-20261013.yaml). Thông tin chưa ghi trong report lịch sử không được tự suy đoán bổ sung; stability lịch sử vẫn OPEN. Lát cắt này sửa runner, không yêu cầu rebuild image ứng dụng.

## 29. Hoàn thiện và phát hành demo/lab — 13/10/2026

- Bản app mới `5.1.1-rc.1` sửa lỗi nguồn bận do thao tác chồng nhau: hai slot đang chạy + hai slot chờ tối đa 30 giây; mỗi yêu cầu được nhận thu nguồn mới độc lập. UI single-flight, hủy yêu cầu client khi rời trang, tự thử lại tối đa hai lần chỉ cho `COLLECTION_BUSY`; không dùng cache để giả dữ liệu real-time. Thu sâu OSD có thể lâu hơn; giao diện hiển thị đang đọc rõ ràng.
- `last_refresh` null/rỗng/sai kiểu của orchestrator trả dữ liệu một phần thay vì lỗi server. Metric có timestamp, cửa sổ đo, chất lượng thật. Giữ phân trang 10 daemon, chọn nhiều daemon qua trang, As-is theo giai đoạn, so sánh A/B cùng loại/FSID, xóa mềm/khôi phục; benchmark và dry-run vẫn bị loại khỏi sản phẩm.
- Backend 304 test không skip PostgreSQL, frontend 24 + TypeScript/build, executor 31, helper 26, real worker 17, diagnostics/guard 26 đạt. API–worker–PostgreSQL synthetic đạt 38/38 với HTTP/worker report schema 2 và tamper rejection 503 có bằng chứng. Lỗi integration đầu lịch sử chưa xác nhận nguyên nhân, không tự ghi là đã giải quyết.
- Đã kiểm browser: đọc mới đủ 14 daemon/FSID, 10 + 4 hàng; xuất mới hai daemon chọn qua trang tải thật về máy; so sánh hai bộ OSD và xuất JSON, lọc giai đoạn không mất A/B; thu một bộ demo mới hai OSD ghi rõ không nâng cấp/ghi Ceph. [Kịch bản demo](rgw-console/docs/DEMO.md) và README được cập nhật.
- App và worker đã push Docker Hub, kiểm API tag/index và pull theo digest: app `sha256:49f5284d27fd4defe2e2804e3b4eb06eaa3ac19352026622de3eae6c417fbe1f`; worker `sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893`. Không ghi đè tag RC1 cũ hoặc `latest`. [Manifest mới](rgw-console/deploy/releases/5.1.1-rc.1.yaml).
- App raw scan 0 findings; worker raw scan vẫn 1C/21H/35M/2L, chỉ lab/offline, không promote production. Chưa hoàn tất telemetry host/process/network và RGW/MDS request/latency, cluster thứ hai, ARM64/signing hoặc nghiệm thu production toàn bộ. “Hoàn thiện demo” không biến các gate đó thành PASS.
- Localhost đã đổi cấu hình theo digest mới; backup trước swap, dữ liệu As-is/evidence/SSH/DB/mount cũ giữ nguyên, container cũ giữ để phục hồi. Production-test 8443 không thay; không Apply, nâng cấp hoặc Ceph write. Đã thêm một collection demo có chủ đích sau khi xác nhận bốn collection cũ và evidence không đổi.

## 30. Sửa lựa chọn metric, bộ lọc collection và nguồn bận — 14/10/2026

- Giữ Lịch sử thu thập; thay khối nguồn/phạm vi/giới hạn dài bằng biểu tượng warning nhỏ, bấm xem chỉ liệt kê dữ liệu thiếu/cũ. Giữ null/quality/timestamp thật; không xóa thông tin nguồn khỏi tệp gốc để làm đẹp giao diện.
- Chọn daemon trong Chỉ số cụm để bấm **Xem chỉ số mới (N daemon)** hoặc **Xuất N daemon (JSON)** ngay cạnh lựa chọn. Đọc mới trả một khu vực kết quả riêng, không thu hẹp danh mục và không nâng cấp. Xem danh mục toàn bộ là thao tác riêng.
- Collection nhiều loại vẫn khớp bộ lọc khi chứa loại được chọn; danh sách/count/chi tiết chỉ hiện daemon đúng loại hoặc exact ID. So sánh chỉ xét cùng loại/FSID. **Xuất daemon đã lọc** trả `FILTERED_AS_IS_EXPORT` với nguồn gốc/SHA gốc rõ ràng; checksum bytes xuất là checksum riêng. **Xuất bộ gốc** giữ đầy đủ payload. Xóa mềm có xác nhận là xóa toàn bộ bộ gốc, không chỉ daemon đang lọc.
- Sửa nguyên nhân thu bận do server tiếp tục lịch lệnh sau browser abort: request observe/export theo dõi ASGI disconnect, hủy lượt chờ và lệnh chưa chạy; slot còn giữ đến khi HTTP nguồn đã chạy kết thúc. Không tăng đồng thời hoặc dùng cache để né lỗi. SSH đã chạy không bị dừng tức thì, vẫn có timeout; tải quá mức thật vẫn được từ chối có giới hạn.
- Inventory mở trang đọc danh mục nhẹ, không tự thu sâu sáu OSD. Đọc sâu theo thao tác explicit có deadline 60 giây cộng budget collector được cấu hình; metric thường 60 giây. Đã sửa mismatch 60 giây/collector 300 giây được tìm trong review.
- Local `5.1.2-preview.1`, digest `sha256:98ed06baecb12868acbed65fa67c338da6f2c4d7b584d509b4326cd7cf238297`, đã build/cập nhật; 319 backend không skip PostgreSQL, 31 frontend + TypeScript/build đạt. Kiểm HTTP nguồn thật hủy hai request rồi đọc mới đạt 200; bộ MON+OSD lọc/export đúng và SHA gốc không đổi. Năm collection/19 events trước kiểm giữ nguyên, không tạo/xóa/khôi phục collection trong lượt kiểm này. Backup trước swap, schema vẫn 21, chỉ đọc Ceph.
- [Manifest kiểm](rgw-console/deploy/releases/5.1.2-preview.1.yaml) giữ báo cáo/checksum. Preview **chưa đăng Hub**; tag Hub RC1 không thay. Tab lỗi ban đầu đã được người dùng thay bằng tab localhost truy cập được; không vượt chặn. Kiểm Browser trực tiếp đạt cho xem/xuất mới hai daemon, bộ hỗn hợp lọc OSD, exact osd.2, cảnh báo nhỏ và so sánh đúng một OSD. Hai JSON tải thật về Downloads; SHA bộ gốc và 5 collection/19 events giữ nguyên. Đây là kiểm theo phạm vi bản sửa, không phải mọi thao tác UI, tải dài hạn hoặc chấp thuận production.
