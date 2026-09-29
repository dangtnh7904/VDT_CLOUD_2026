# 14 — security advisory trực tiếp và cross-reference đã xác minh: v16.2.15 → v17.2.7

**Trạng thái: binary gate của owner 14 đã hoàn tất; cross-reference runtime toàn suite còn đang phân tích.** [CSV đầy đủ của owner](./14-security-cross-reference.csv) có 3 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Đã đối soát `affect = 0`, `trivial = 3`, **chưa phân loại = 0** cho ba hàng owner này. Đây không phải kết luận rằng hai endpoint không có khác biệt bảo mật ở runtime; các owner code vẫn đang phân tích.

## Phạm vi và phương pháp

Owner này phụ trách security advisory trực tiếp và cross-reference đã xác minh. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

Không có finding `affect` từ ba hunk tài liệu của owner 14. Tài liệu CVE-2022-0670 ghi cả Pacific 16.2.15 lẫn Quincy 17.2.7 thuộc phiên bản đã sửa; diff chỉ bổ sung bản sửa Octopus 15.2.17. Điều này không xác minh mã của hai endpoint hoặc CephX caps thực tế. Nếu deployment dùng Manila native CephFS và đã nâng từ Nautilus hoặc cũ hơn, vẫn cần audit path caps theo advisory; đối chiếu code thuộc owner 11.

## Trivial changes

Cả **3/3** hàng đã được screen theo hunk và commit: chính sách báo lỗ hổng ở `SECURITY.md` không thay đổi binary/recipe; advisory chỉ cập nhật thông tin Octopus; index chỉ đổi Sphinx orphan marker. Chi tiết từng hàng và commit nằm trong [CSV owner](./14-security-cross-reference.csv).

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn cross-reference tới finding owner 11 nếu code-level audit của cặp endpoint phát hiện khác biệt áp dụng cho CVE-2022-0670; không suy từ hunk advisory.
- Kiểm chứng deployment có dùng Manila native CephFS và lịch sử nâng từ Nautilus hoặc cũ hơn trước khi đưa kết luận áp dụng.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
