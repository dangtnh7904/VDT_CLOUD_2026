# Nâng cấp Ceph — PA2 và Storage Lab Console

**Cập nhật: 12/10/2026.** Dự án chuẩn bị, kiểm chứng và điều phối nâng cấp Ceph phục vụ RGW/RBD. Chiến lược OSD duy nhất trong kế hoạch hiện hành là **PA2 — luân chuyển spare**. Các báo cáo, MOP và kết quả lab là bằng chứng theo phạm vi riêng; chúng không tự xác nhận cụm hiện tại đủ điều kiện rollout.

## Đọc từ đâu

| Tài liệu chính | Nội dung và nơi cập nhật |
|---|---|
| [README dự án](README.md) | Phạm vi, tình trạng và điều hướng toàn dự án |
| [Plan tổng](plan-tổng.md) | Lộ trình từng hop, quy trình PA2, gate và tiêu chí hoàn thành |
| [Tổng quan console](code/README.md) | Sản phẩm console, chức năng đang có và giới hạn |
| [Plan console hiện có](code/plan%285%29.md) | Backlog kỹ thuật, state machine, API/UI, kiểm thử và đóng gói portable |
| [Comparison tổng](comparison/README.md) | Bản mới đổi gì, cần sửa/bỏ gì trước nâng, applicability, test và evidence |
| [Benchmark](benchmark/README.md) | Đo trước/trong/sau nâng cấp và đo các tool dùng trong quá trình nâng |

Các file kỹ thuật dưới từng nhánh tiếp tục giữ chi tiết và bằng chứng. Chỉ cập nhật quyết định/phạm vi tại đầu mối tương ứng, tránh tạo thêm plan tổng song song.

## PA2 đã chọn

```text
S sẵn sàng ở bản đích
  X → S  → nâng X → X thành spare
  Y → X  → nâng Y → Y thành spare
  Z → Y  → nâng Z → Z thành spare
  … → bàn giao placement sau xoay và spare cuối
```

S giữ PG nhận từ X; X sau nâng nhận PG từ Y. Không có bước trả dữ liệu S → X trong quy trình chuẩn. Thiết kế dùng `KEEP_ROTATED_PLACEMENT`; mọi cân bằng thêm phải có kế hoạch và được tính vào thời gian/traffic. OSD giữ ID và incarnation khi chỉ nâng daemon; replacement mới tạo incarnation khác.

Mỗi cặp nguồn/đích phải hợp lệ theo CRUSH, failure domain, capacity và down set. Trước mỗi lượt U→D, deep-scrub mới phải hoàn tất và đạt trên toàn handoff set ở placement hiện tại rồi mới bắt đầu chuyển. Đích nhận PG theo nhóm ở vai trò replica; sau hội tụ phải deep-scrub mới lần nữa trước bàn giao. Nguồn chỉ được nâng sau khi vắng trong cả `up[]` và `acting[]` của toàn bộ scope. Canary PA2 có ít nhất hai lượt để kiểm việc chuyển vai spare và nhận dữ liệu trên OSD vừa nâng.

## Tình trạng dự án

| Nhánh | Đã có trong repository | Phần tiếp theo |
|---|---|---|
| 16.2.5 → 16.2.15 | [Bộ H1](comparison/pacific-16.2.5-to-16.2.15/README.md) hoàn tất binary gate, coverage và finding-quality strict `127/127` | As-Is/pins/actions/test/runtime vẫn mở; quyết định `NOT_READY_FOR_DECISION` |
| 16.2.15 → 17.2.7 | [Bộ H2](comparison/pacific-16.2.15-to-quincy-17.2.7/README.md) hoàn tất binary gate và coverage; quality audit hiện 44/441 finding đủ 11 chiều | Còn 397 quality gap; As-Is/pins/actions/test/runtime mở; quyết định `NOT_READY_FOR_DECISION` |
| Console | RGW/RBD tools, inventory/collector, profile, evidence, dry-run; PA2 ledger/simulator và QoS foundation | PA2 live, bỏ lựa chọn PA1 khỏi tạo mới, runner/validation và image portable |
| Benchmark | Protocol và mẫu run trong `benchmark/` | Baseline mới, PA2 và tool benchmarks; lần hợp nhất này chưa chạy workload |
| Reef 18.2.7 | [Bộ H3 `17.2.7 → 18.2.7`](comparison/quincy-17.2.7-to-reef-18.2.7/README.md) đã hoàn tất source/binary 4.434/4.434 và quality audit 188/188 finding | Thu 24 nhóm As-Is, khóa 12 exact-hop pin, chạy 52 gate/19 test pack và đóng GO/NO-GO; hiện vẫn `NOT_READY_FOR_DECISION` |

Hồ sơ MON ngày 01/10 ghi version target nhưng gate vẫn HOLD; smoke S3 ngày 02/10 có phạm vi ngắn. Xem [closeout MON](test/MON-20261001-QUORUM-VA-GATE-CLOSEOUT.md) và [validation console](code/rgw-console/VALIDATION.md) trước khi sử dụng kết quả cũ. Acceptance tài liệu, test phần mềm, lab và production là các mức bằng chứng khác nhau.

## Cấu trúc repository

```text
README.md                         Điều hướng dự án
plan-tổng.md                      Kế hoạch nâng cấp PA2 tổng
code/
  README.md                       Tổng quan console/tool
  plan(5).md                      Plan console duy nhất
  rgw-console/                    Backend, frontend, executor, migrations, tests
  osd-info-collector/              Thu inventory và cấu hình OSD
comparison/
  README.md                       Comparison và checklist tổng
  pacific-16.2.5-to-16.2.15/        Hop 1 và checklist nguồn
  pacific-16.2.15-to-quincy-17.2.7/ Hop 2 đang làm
benchmark/                        Protocol và mẫu run; bench tool
MOP/                              Quy trình theo thành phần, cần rà revision trước dùng
test/                             Gate, biên bản và evidence đã thu
as-is-base/                       Snapshot lịch sử, phải thu lại trước rollout
checklists/                       Bảng kiểm hỗ trợ
chọn osd/, placement-draining/    Ghi chú chọn OSD và placement
docs/archive/2026-10-09/           Bản tài liệu trước khi hợp nhất
```

Checkout `ceph16.2.5/`, `ceph16.2.15/`, `ceph17.2.7/` là nguồn đối chiếu; các thư mục này và một số dữ liệu lab nằm trong `.gitignore`. `buoi2/` là bài học/lab nền; `projects/`, slide, DOCX, `h0-new.md` và ghi chú cũ là tham khảo, không phải plan PA2 hiện hành.

## Quy tắc duy trì

- PA1 đã bỏ khỏi kế hoạch triển khai mới. Tên PA1 trong code/schema, evidence hoặc archive phản ánh lịch sử; bỏ lựa chọn đó khỏi UI/API tạo run mới là đầu việc console, chưa được thực hiện bằng sửa tài liệu.
- Checklist cũ từng gọi drain weight là PA2. Khi triển khai dùng định nghĩa luân chuyển spare ở [plan tổng](plan-tổng.md). H0 enforcement/repair trong nghiên cứu cũ không phải khả năng Ceph native đã có.
- Comparison lưu thay đổi và nguyên nhân; plan/MOP quyết thứ tự hành động; console thực thi/thu evidence khi tính năng đã được kiểm chứng; benchmark đo tác động.
- Lệnh trong tài liệu là nội dung runbook để review. Lần hợp nhất này chỉ sửa tài liệu, không thay cấu hình hoặc nâng cấp cluster.
