# STOP, fallback, rollback và phục hồi dữ liệu

[Mục lục](00-README.md) · [Gate](06-GATE-VA-NGUONG.md) · [Test phục hồi](08-TEST-CHUC-NANG.md)

## 1. Dừng ở mức nào?

STOP nghĩa dừng mở rộng batch/role và hạn chế đường đang gây hại theo runbook. Không mặc định shutdown cả cluster hoặc giữ recovery bị chặn vô thời hạn.

| Dấu hiệu | Hành động đầu tiên |
| --- | --- |
| Checksum/data mismatch, acknowledged write mất, inconsistent/unfound mới | Dừng mở rộng; giữ payload/log/map/version; xác định phạm vi và nguồn còn tốt trước sửa |
| Quorum mất/election loop, OSD replay fail/crash loop | Dừng upgrade; giữ peer đang khỏe và bảo vệ trạng thái; điều tra đúng role |
| SLO/capacity vượt ngưỡng | Dừng thêm tải/batch; giảm benchmark và rate có thể điều chỉnh; giữ recovery cần cho an toàn |
| Mất telemetry bắt buộc | Dùng nguồn độc lập đã kiểm; nếu không đủ thì HOLD, không tiếp tục nâng mù |
| Image/device/PG scope sai | Ngừng thao tác kế tiếp; đối chiếu manifest và ownership; không sửa nhanh bằng zap/force-remove |
| RGW auth/policy fail | Drain luồng/endpoint bị ảnh hưởng; giữ endpoint đã kiểm còn capacity |
| H0 thiếu reference/capability, mismatch, timeout hoặc policy/epoch thay đổi | Không trả SUCCESS_ACK khi chưa đủ proof; đóng admission mới trong scope cần thiết, giữ native recovery/peering và ghi trạng thái submit/commit/verify của từng request |

## 2. Phân biệt bốn hành động

| Hành động | Nghĩa | Ví dụ |
| --- | --- | --- |
| Pause/stop rollout | Dừng thay daemon tiếp theo; giữ phần đã nâng | `ceph orch upgrade pause/stop` theo CLI thực |
| Fallback dịch vụ | Đưa traffic/công việc sang đường còn khỏe và tương thích | RGW endpoint khác, client cohort đã kiểm |
| Rollback binary/config | Trở về bản cũ khi state còn tương thích và đã rehearsal | Config/consumer hoặc daemon trong phạm vi được chứng minh |
| Forward-fix/rebuild/restore | Giữ/đưa về build target phù hợp, tái dựng từ nguồn tốt hoặc restore checkpoint | OSD không thể mở store bằng base sau khi target ghi format mới |

`upgrade stop` không undo migration, không phục hồi image cũ và không tự trả mọi flag/spec/LB/rank. Kết quả command success chỉ chứng minh command hoàn thành.

## 3. Ranh giới quan trọng của hop này

### OSD/BlueFS

Target có opcode `OP_FILE_UPDATE_INC`; reader base không có case xử lý đó và nhánh opcode không nhận diện trả `-EIO`. Đây là bằng chứng source cho một **rủi ro không tương thích store khi downgrade**. Không suy mọi OSD vừa start đều chắc chắn đã ghi opcode này; cũng không suy chưa thấy lỗi nghĩa downgrade an toàn. [S09](13-NGUON-VA-DOI-CHIEU.md)

Chính sách vận hành: sau target đã mở/ghi store, không dựa vào package/image-only downgrade. Chọn trước một đường đã thử: forward-fix, rebuild từ nguồn tốt, hoặc restore nhất quán toàn bộ block/DB/WAL theo checkpoint. Thử old reader chỉ trên clone độc lập.

Không chụp lại riêng block.db rồi gọi đó là backup toàn OSD. Snapshot các device phải đồng bộ theo procedure đã kiểm. Snapshot cũ cũng không tự mang theo những ghi mới sau checkpoint; xác định RPO và catch-up, không restore đè OSD đang live.

### MGR/cephadm

MGR target có state migrations tới 5 trong source. Promote target có thể đổi state/specs ngoài process; hạ image không chứng minh base có thể reconcile đúng. Giữ checkpoint cần thiết và ưu tiên forward-fix nếu chưa rehearsal chiều về. Không tự sửa `migration_current` để ép chạy lại. [S12](13-NGUON-VA-DOI-CHIEU.md)

### Client/cache và dịch vụ

Nếu có PWL/mirror/NFS/Manila/multisite, rollback phụ thuộc state riêng. Không xóa dirty cache; không failback vào endpoint security đã biết không đạt; không đổi quyền hoặc trim log chỉ để làm test xanh.

## 4. Ma trận lựa chọn theo đối tượng

| Đối tượng | Đường ưu tiên khi lỗi | Chỉ rollback khi |
| --- | --- | --- |
| Config/parser/alert | Khôi phục artifact consumer tương thích và test lại | Có snapshot, biết scope, không phá daemon target khác |
| MGR | Giữ active còn khỏe, sửa module/config hoặc forward-fix | State migration và base reconciliation đã rehearsal |
| MON | Giữ quorum, xử lý một MON theo runbook đã thử | State decode/compatibility và quorum-safe sequence có bằng chứng |
| OSD đã target write | Giữ nguồn còn tốt; sửa activation/config hoặc forward-fix/rebuild | Có chứng cứ store tương thích hoặc procedure restore đầy đủ được kiểm |
| RGW | Drain endpoint lỗi, phục vụ bằng endpoints đã đạt policy | Shared state và security vẫn đáp ứng; không chỉ image start được |
| RBD client/PWL | Quiesce đúng ứng dụng, flush/recovery theo integration | Cache layout/lock/state hợp lệ với client cũ |
| PA1 map | Giữ tập đang phục vụ đã xác minh, xem dữ liệu/current acting set trước sửa map | Nguồn đích còn đúng/current, không mất replica hoặc ghi đè upmap có trước; S không mặc nhiên còn dữ liệu mới nhất sau return |
| H0 mismatch | Giữ evidence, đối chiếu đúng request/version/range; H0 tự chặn kết luận thành công, không tự sửa dữ liệu | H0 không là binary rollback; chẩn đoán/chọn nguồn/repair là procedure riêng đã chứng minh |

### Khi write đã commit nhưng chưa qua H0

Ở L2 một số nhánh có thể đã tiến tới commit; ở L3 kiểm D diễn ra sau durable completion. `COMMITTED_UNVERIFIED` hoặc không có SUCCESS_ACK **không có nghĩa dữ liệu chưa ghi, đã rollback hoặc không thể đọc thấy**. Visibility gate không thuộc bảo đảm hiện tại.

- Lưu request/op/generation, object/version/range, run/policy revision, primary/acting epoch, kết quả từng peer và trạng thái `not_submitted/submitted/committed/uncertain`.
- Retry không được trả thành công chỉ vì native PG log nói operation đã committed. Phải khôi phục bằng chứng hoặc xác minh lại đúng contract; reply bị mất cũng phải giữ idempotence.
- Failover/đổi acting set không dùng proof cũ ngoài scope. Peer mới thiếu capability thì dừng protected path theo contract; không tự chuyển L3 xuống L2/L1.
- Muốn kết thúc hoặc đổi policy: đóng admission, đối soát request đang chạy, tạo run/policy mới. Mất Web/controller không được làm request đã nhận bỏ qua ACK gate.

Các tên trạng thái H0 là contract thiết kế, chưa phải mã lỗi API Ceph upstream. Chi tiết test crash/retry ở W07…10 trong [15](15-TEST-H0-LEVEL-1-2-3.md).

## 5. Backup cần đến mức nào?

Với 24 PB dữ liệu, cụm dự phòng khoảng 100 TB không thể được gọi là bản sao đầy đủ toàn cụm nếu không có phân tích logical/raw, selection, retention và capacity. Chọn phạm vi: dữ liệu quan trọng/canary, cấu hình/control state, nguồn tái dựng, checkpoint và RPO/RTO.

Replica và recovery giúp phục hồi hỏng một OSD khi còn nguồn hợp lệ; không tương đương backup độc lập cho xóa nhầm hoặc lỗi logic đồng loạt. H0 hiện tại xác minh và giữ gate, **không tự chọn nguồn tốt, sửa dữ liệu hay tạo backup**. Phục hồi vẫn cần payload đúng còn tồn tại và procedure riêng; hash không sinh lại dữ liệu.

Không buộc dựng thêm cụm 100 TB để thử lab. Production phải có quyết định phục hồi phù hợp yêu cầu nghiệp vụ; nếu chấp nhận chỉ forward-fix/rebuild từ replica thì ghi rõ giới hạn sự cố được bảo vệ.

## 6. Trình tự xử lý và resume

1. Ghi incident, stop reason, scope và timestamp; pause engine hoặc ngừng hàng đợi manual đang dùng.
2. Giữ logs, maps, actual versions, client failures và state journal; kiểm nguồn dữ liệu còn tốt.
3. Chọn đúng một đường phục hồi theo bảng; không chạy chuỗi repair/trim/downgrade thử trên live store.
4. Thực hiện runbook đã thử; đọc lại dữ liệu và kiểm health/SLO/telemetry sau hành động.
5. Chạy lại gate đã fail; resume sau cửa sổ ổn định đã chốt. Ghi quyết định mới, không ghi đè evidence lỗi.
