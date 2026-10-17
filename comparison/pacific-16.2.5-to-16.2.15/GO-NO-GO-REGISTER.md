# GO/NO-GO register — Pacific 16.2.5 lên 16.2.15

| ID | Tiêu chí | Điều kiện đóng | Bằng chứng hiện có | Trạng thái | Owner | Bước tiếp theo |
|---|---|---|---|---|---|---|
| GNG-01 | Provenance và net diff | Hai ref, SHA và inventory net diff được validator xác nhận nhất quán. | Validator nguồn đã xác nhận v16.2.5 đến v16.2.15 và inventory đầy đủ. | COMPLETE | Analysis owner | Giữ nguyên pin và chạy lại validator sau mọi thay đổi. |
| GNG-02 | Phân loại binary impact | Mọi dòng CSV có affects_upgrade và trivial_change hợp lệ, loại trừ lẫn nhau. | 2.665 dòng đã phân loại gồm 517 ảnh hưởng và 2.148 trivial. | COMPLETE | Analysis owner | Chỉ mở lại khi component CSV hoặc schema thay đổi. |
| GNG-03 | Độ phủ thiết kế kiểm chứng | Mọi runtime gate xuất hiện trong As-Is, action và test-pack register có validator tự động. | As-Is, action và 16 test pack đã phủ 85 gate; 26 source asset đúng target đã được kiểm. | COMPLETE | Validation owner | Duy trì coverage khi thêm hoặc đổi runtime gate. |
| GNG-04 | Exact-hop artifact pins | Mười hai pin có digest, provenance và không còn PENDING_INPUT. | Pin manifest hiện vẫn là template và chưa có artifact lab thực tế. | OPEN | Release owner | Điền manifest từ registry và repository được chọn cho lab. |
| GNG-05 | As-Is production-like baseline | Hai mươi nhóm evidence được CAPTURED hoặc có quyết định NOT_APPLICABLE hợp lệ. | Toàn bộ nhóm hiện ở NOT_CAPTURED, chưa có snapshot cluster. | OPEN | Cluster owner | Thu thập bundle theo AS-IS-EVIDENCE.md và review checksum. |
| GNG-06 | Finding quality và applicability | Mọi finding đủ 11 chiều bằng chứng; service, client, integration và test lịch sử có quyết định áp dụng. | Quality audit strict đạt 127/127; inventory môi trường và scope decision theo deployment còn mở. | OPEN | Architecture owner | Ký scope/applicability record cho từng service, client và integration của môi trường đích. |
| GNG-07 | Owner, window và threshold | Mọi action có owner, thời gian, ngưỡng stop và người ra quyết định. | Hai mươi action hiện đều UNASSIGNED và PENDING_INPUT. | OPEN | Change manager | Gán RACI, maintenance window và ngưỡng định lượng. |
| GNG-08 | Exact-hop lab P0 | Các gate P0 chạy trên artifact pin đúng và mọi verdict đều PASS. | Runtime manifest có 85 ID nhưng tất cả đang NOT_RUN. | OPEN | Lab owner | Dựng clone production-like và chạy checklist exact hop. |
| GNG-09 | Mixed-version và client | MON, MGR, OSD, RBD, CephFS, RGW cùng client thật đạt oracle mixed phase. | Chưa có timeline mixed-version, checksum hoặc service oracle. | OPEN | Service owners | Chạy fault injection và mixed-client matrix trên lab. |
| GNG-10 | Canary và ổn định | Canary theo failure-domain đạt health, SLO và thời gian soak đã duyệt. | Chưa có canary run, threshold hay hai cửa sổ quan sát liên tiếp. | OPEN | Operations owner | Chốt batch size, soak time và thực hiện canary có giám sát. |
| GNG-11 | Rollback và restore | Ranh giới rollback được ghi rõ, diễn tập và đạt RTO RPO cùng checksum. | Chưa có restore drill hoặc bằng chứng downgrade package activation. | OPEN | Recovery owner | Diễn tập cả rollback trực tiếp và restore khi đường lùi đóng. |
| GNG-12 | Bảo mật và tích hợp | CephX, TLS, FIPS, Manila, NFS, registry và alert consumer đều đạt. | Chưa có inventory hay kết quả test từ môi trường đích. | OPEN | Security owner | Thu scope, chạy oracle và ký exception nếu không áp dụng. |
| GNG-13 | Evidence closure | Mọi runtime ID có artifact immutable, timestamp, verdict, owner và reviewer. | Runtime evidence template vẫn toàn bộ NOT_RUN, chưa có index được ký. | OPEN | Evidence owner | Nạp artifact, chạy validator strict và review độc lập. |
| GNG-14 | Irreversible boundary và floor | Chỉ nâng release floor sau khi loại bỏ đường lui có chủ đích và được phê duyệt. | Chưa có bằng chứng full fleet, client closure hoặc approval nâng floor. | OPEN | Change authority | Giữ floor cũ đến khi toàn bộ tiêu chí trước được đóng. |

## Tổng hợp trạng thái

| Trạng thái | Số lượng |
|---|---:|
| COMPLETE | 3 |
| OPEN | 11 |
| BLOCKED | 0 |
| FAILED | 0 |
| NOT_APPLICABLE | 0 |

**Kết luận hiện tại ngày 13/10/2026: `NOT_READY_FOR_DECISION`.**

Kết luận này không phải `NO_GO`: bộ hồ sơ tĩnh đã đủ cấu trúc, nhưng chưa có artifact exact-hop và bằng chứng lab hoặc cluster để ra quyết định vận hành.
