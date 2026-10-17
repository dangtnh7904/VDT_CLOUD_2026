# Finding-quality baseline — Pacific 16.2.15 lên Quincy 17.2.7

**Baseline cập nhật ngày 13/10/2026:** 441 finding ổn định được phát hiện trong các báo cáo `01`–`15`; 44 finding đủ toàn bộ chiều kiểm tra, 397 finding còn ít nhất một khoảng trống. Owner 03 và 06 đã đạt strict theo report, owner 15 đạt 7/7; CFG-008 đồng thời đóng thêm một section RGW dùng chung. Đây là audit cấu trúc nội dung, không tự chứng minh kết luận code đúng và không phải runtime PASS.

## Khoảng trống theo chiều bằng chứng

| Chiều còn thiếu | Số finding |
|---|---:|
| Rollback boundary | 308 |
| Activation mode | 221 |
| Impact category | 216 |
| Mixed/full-version behavior | 71 |
| Confidence | 51 |
| Unresolved evidence | 41 |
| Endpoint behavior | 1 |
| Substantive length | 1 |

## Baseline theo báo cáo

| Report | Finding | Đủ 11 chiều | Còn thiếu |
|---|---:|---:|---:|
| 01 OSD/PG | 94 | 2 | 92 |
| 02 BlueStore/BlueFS | 25 | 1 | 24 |
| 03 KV/block device | 6 | 6 | 0 |
| 04 MON/OSDMap/CRUSH | 25 | 3 | 22 |
| 05 messaging/auth/common | 74 | 0 | 74 |
| 06 config/defaults | 14 | 14 | 0 |
| 07 MGR/monitoring | 58 | 3 | 55 |
| 08 cephadm/orchestrator | 25 | 0 | 25 |
| 09 ceph-volume | 3 | 0 | 3 |
| 10 RADOS/RBD | 16 | 2 | 14 |
| 11 CephFS/MDS | 17 | 1 | 16 |
| 12 RGW | 60 | 5 | 55 |
| 13 build/package | 18 | 1 | 17 |
| 15 upgrade validation | 7 | 7 | 0 |

Report 14 là cross-reference không có heading finding riêng trong audit này; security IDs được sở hữu và kiểm ở các report chứa heading tương ứng.

## Quy tắc cải thiện

Mỗi finding chỉ được tính đủ khi section của chính ID đó có: evidence anchor; hành vi hai endpoint; applicability; mixed/full-version; rollback boundary; impact; confidence; validation; activation mode; unresolved evidence; và nội dung đủ chi tiết. Không chèn câu boilerplate để qua regex: mọi bổ sung phải dựa trên endpoint code, test hoặc giới hạn vận hành đã được chứng minh.

Baseline được khóa bằng `--expected-count 441 --max-incomplete 397`: số incomplete không được tăng. Mục tiêu strict cuối là `0`; trước khi đạt, README và GO/NO-GO phải tiếp tục nêu rõ finding-quality còn mở.

```powershell
python -B comparison/tools/audit_finding_quality.py `
  --root comparison/pacific-16.2.15-to-quincy-17.2.7 `
  --expected-count 441 --max-incomplete 397 --show 0
```
