# 14 — security advisory trực tiếp và cross-reference: v17.2.7 → v18.2.7

**Trạng thái: binary gate owner 14 đã hoàn tất; cross-reference code còn mở ở các owner chức năng.** [CSV đầy đủ của owner](./14-security-cross-reference.csv) có 2 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 0`, `trivial = 2`, chưa phân loại = 0.

## Phạm vi và phương pháp

Owner này bao phủ hai security document đổi giữa endpoint. Đã đọc full hunk và nội dung hai phiên bản; không có source, config, package hay validation executable trong hai hàng. Runtime fix, auth behavior hoặc advisory mapping vẫn thuộc owner chức năng và chỉ được cross-reference ở đây khi có bằng chứng độc lập.

## Cross-reference cần kiểm ở owner chức năng

`doc/security/cves.rst` thêm mục `CVE-2023-46159` (RGW DoS) và `CVE-2022-3650` (`ceph-crash` privilege behavior) cùng link NVD. Việc tên CVE xuất hiện ở target chỉ chứng minh danh mục tài liệu được cập nhật; nó không chứng minh affected-version range, fix commit, code presence hoặc applicability cho hai endpoint. Khi owner RGW, common/crash hoặc packaging gặp hunk liên quan, cần đối chiếu advisory chính thức và endpoint code trước khi đưa ra security finding.

`doc/security/index.rst` bỏ khóa GPG và link MIT key server dùng khi báo cáo vulnerability. Đây là thay đổi kênh liên hệ của dự án, không đổi security behavior của cluster hay quy trình nâng binary.

## Trivial changes

**2 hàng.** `SEC-DOC-001` bao phủ việc thêm hai CVE vào danh mục/link; `SEC-DOC-002` bao phủ việc bỏ hướng dẫn GPG cũ. Sau khi đọc endpoint hunk, cả hai chỉ thay nội dung tài liệu và không có causal path độc lập tới preparation, rollout, mixed-version, rollback hay validation của hop này.

## Validation và giới hạn

Không cần runtime test cho hai document verdict. Chưa kết luận CVE applicability hay trạng thái fix của Quincy/Reef; các kết luận đó đòi hỏi advisory/commit/code evidence ở owner chức năng. Báo cáo này không cấp quyền thao tác cluster production.

