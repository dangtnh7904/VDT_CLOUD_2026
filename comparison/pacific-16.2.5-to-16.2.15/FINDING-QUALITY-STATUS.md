# Finding-quality status — Pacific 16.2.5 lên 16.2.15

**Trạng thái cập nhật ngày 13/10/2026:** 127/127 finding ổn định trong các báo cáo `01`–`15` đủ toàn bộ 11 chiều kiểm tra; không còn finding incomplete. Đây là audit cấu trúc nội dung và evidence boundary, không tự chứng minh kết luận code đúng, không thay thế peer review, và không phải runtime PASS.

## Khoảng trống theo chiều bằng chứng

| Chiều còn thiếu | Số finding |
|---|---:|
| Evidence anchor | 0 |
| Endpoint behavior | 0 |
| Applicability | 0 |
| Mixed/full-version behavior | 0 |
| Rollback boundary | 0 |
| Impact category | 0 |
| Confidence | 0 |
| Validation path | 0 |
| Activation mode | 0 |
| Unresolved evidence | 0 |
| Substantive length | 0 |

## Baseline theo báo cáo

| Report | Finding | Đủ 11 chiều | Còn thiếu |
|---|---:|---:|---:|
| 01 OSD/PG | 13 | 13 | 0 |
| 02 BlueStore/BlueFS | 10 | 10 | 0 |
| 03 KV/block device | 6 | 6 | 0 |
| 04 MON/OSDMap/CRUSH | 11 | 11 | 0 |
| 05 messaging/auth/common | 9 | 9 | 0 |
| 06 config/defaults | 7 | 7 | 0 |
| 07 MGR/monitoring | 10 | 10 | 0 |
| 08 cephadm/orchestrator | 9 | 9 | 0 |
| 09 ceph-volume | 6 | 6 | 0 |
| 10 RADOS/RBD | 7 | 7 | 0 |
| 11 CephFS/MDS | 8 | 8 | 0 |
| 12 RGW | 8 | 8 | 0 |
| 13 build/package | 10 | 10 | 0 |
| 14 security cross-reference | 8 | 8 | 0 |
| 15 upgrade validation | 8 | 8 | 0 |

## Quy tắc cải thiện

Mỗi finding chỉ được tính đủ khi section của chính ID đó có: evidence anchor; hành vi hai endpoint; applicability; mixed/full-version; rollback boundary; impact; confidence; validation; activation mode; unresolved evidence; và nội dung đủ chi tiết. Không chèn câu boilerplate để qua regex: mọi bổ sung phải dựa trên endpoint code, test hoặc giới hạn vận hành đã được chứng minh.

Gate đã được nâng lên strict-zero bằng `--expected-count 127 --strict`: thêm finding mới phải cập nhật expectation có chủ đích và mọi finding đều phải đủ 11 chiều ngay trong cùng thay đổi. Runtime/As-Is/pin/action vẫn là các gate độc lập và còn mở.

```powershell
python -B comparison/tools/audit_finding_quality.py `
  --root comparison/pacific-16.2.5-to-16.2.15 `
  --expected-count 127 --strict --show 0
```
