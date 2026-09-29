# 05 — messenger, CephX, encoding và common runtime: v16.2.15 → v17.2.7

**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./05-messaging-auth-common.csv) có 227 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 0`, `trivial = 0`, **chưa phân loại = 227**; các số 0 không phải kết luận không có tác động.

## Phạm vi và phương pháp

Owner này phụ trách messenger, CephX, encoding và common runtime. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

Chưa có finding được xác minh đủ hunk, symbol hai endpoint, commit, test và điều kiện áp dụng để công bố. Các hàng `upgrade_impact` để trống cho tới khi đọc diff/metadata thực tế; không gán `trivial` theo đường dẫn.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 227` và viết tóm tắt các cụm trivial.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
