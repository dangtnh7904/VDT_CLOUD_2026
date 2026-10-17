# GO/NO-GO register — Pacific 16.2.15 lên Quincy 17.2.7

| ID | Tiêu chí | Điều kiện đóng | Bằng chứng hiện có | Trạng thái | Owner | Bước tiếp theo |
|---|---|---|---|---|---|---|
| GNG-01 | Provenance và net diff | Hai ref, SHA và inventory net diff được validator xác nhận nhất quán. | Validator nguồn xác nhận v16.2.15 đến v17.2.7 và inventory đầy đủ. | COMPLETE | Analysis owner | Giữ pin cố định và chạy validator sau mọi thay đổi. |
| GNG-02 | Phân loại binary impact | Mọi dòng CSV có hai cột binary hợp lệ và loại trừ lẫn nhau. | 4.179 dòng gồm 1.736 ảnh hưởng và 2.443 trivial đã hợp lệ. | COMPLETE | Analysis owner | Chỉ mở lại khi component CSV hoặc schema thay đổi. |
| GNG-03 | Độ phủ thiết kế kiểm chứng | Mọi runtime gate có As-Is, action và test-pack mapping được validator kiểm tra. | Ba register phủ 43 gate; 15 pack và 28 source asset đúng target đã được kiểm. | COMPLETE | Validation owner | Duy trì coverage khi thêm hoặc đổi gate. |
| GNG-04 | Exact-hop artifact pins | Mười hai pin có digest, provenance và không còn PENDING_INPUT. | Pin manifest vẫn là template và chưa có artifact lab thực tế. | OPEN | Release owner | Điền manifest từ registry và repository sẽ dùng trong lab. |
| GNG-05 | As-Is production-like baseline | Hai mươi nhóm evidence được CAPTURED hoặc NOT_APPLICABLE hợp lệ. | Toàn bộ nhóm còn NOT_CAPTURED, chưa có snapshot cluster thực. | OPEN | Cluster owner | Thu bundle theo AS-IS-EVIDENCE.md và review checksum. |
| GNG-06 | Finding quality và applicability | Mọi finding đủ 11 chiều bằng chứng; service, client, backend và integration có quyết định áp dụng. | Quality audit đạt 44/441 finding; owner 03/06/15 đã đủ nhưng 397 finding và inventory RGW, CephFS, client estate còn mở. | OPEN | Architecture owner | Bổ sung evidence theo finding và ký scope record cho ngoại lệ. |
| GNG-07 | Owner, window và threshold | Mọi action có owner, thời gian, stop threshold và decision authority. | Hai mươi action đều UNASSIGNED và PENDING_INPUT. | OPEN | Change manager | Gán RACI, maintenance window và ngưỡng định lượng. |
| GNG-08 | Exact-hop lab P0 | Các LAB gate P0 chạy bằng artifact pin và có verdict PASS. | Runtime manifest có 43 ID nhưng tất cả đang NOT_RUN. | OPEN | Lab owner | Dựng clone production-like và chạy matrix exact hop. |
| GNG-09 | Mixed-version và client | Control-plane, OSD, RBD, CephFS, RGW cùng client thật đạt oracle. | Chưa có timeline mixed-version, checksum hoặc request oracle. | OPEN | Service owners | Chạy mixed-client matrix và fault injection trên lab. |
| GNG-10 | Canary và ổn định | Canary theo failure-domain đạt health, SLO và soak time đã duyệt. | Chưa có canary run, batch size hoặc hai cửa sổ ổn định. | OPEN | Operations owner | Chốt batch, soak, stop rule và thực hiện canary giám sát. |
| GNG-11 | Rollback và restore | Release-floor boundary, rollback và restore đạt RTO RPO, checksum. | Chưa có restore drill hoặc package activation failback evidence. | OPEN | Recovery owner | Diễn tập đường lui trước và sau irreversible boundary. |
| GNG-12 | Bảo mật và tích hợp | CephX, TLS, KMS, registry, tracing, NFS và external API đều đạt. | Chưa có inventory hoặc kết quả test môi trường đích. | OPEN | Security owner | Thu scope, chạy oracle và ký exception nếu không áp dụng. |
| GNG-13 | Evidence closure | Mọi LAB ID có artifact immutable, timestamp, verdict, owner và reviewer. | Runtime evidence template vẫn toàn bộ NOT_RUN, chưa có index ký. | OPEN | Evidence owner | Nạp artifact, chạy strict validator và review độc lập. |
| GNG-14 | Irreversible boundary và floor | Chỉ nâng require-osd-release sau full-fleet closure và approval. | Chưa có full-fleet evidence, client closure hoặc approval nâng floor. | OPEN | Change authority | Giữ floor Pacific đến khi mọi tiêu chí trước được đóng. |

## Tổng hợp trạng thái

| Trạng thái | Số lượng |
|---|---:|
| COMPLETE | 3 |
| OPEN | 11 |
| BLOCKED | 0 |
| FAILED | 0 |
| NOT_APPLICABLE | 0 |

**Kết luận hiện tại ngày 13/10/2026: `NOT_READY_FOR_DECISION`.**

Kết luận này không phải `NO_GO`: phân tích tĩnh và cấu trúc kiểm chứng đã đủ, nhưng artifact exact-hop và bằng chứng lab hoặc cluster vẫn chưa được cung cấp.
