# Điều tra lỗi integration đầu tiên — 13/10/2026

Report của các lượt chạy mới đã được nâng lên schema 2 để lưu đầy đủ HTTP/worker/failure context và source snapshot: [hướng dẫn mới](INTEGRATION_REPORTING.md). Kết quả điều tra và các checksum bên dưới là bằng chứng lịch sử của phiên bản runner tại thời điểm chạy.

## Kết luận có thể chứng minh

Chưa xác định được lỗi nền đã xảy ra ở lần đầu. Đã xác nhận một thiếu sót của script kiểm thử: assertion `tampered_real_worker_result_identity_rejected` chỉ lưu tên bước thất bại, bỏ mất HTTP status/code và dấu vết xử lý. Vì nhiều lỗi khác nhau tạo cùng assertion này, không thể suy ngược một nguyên nhân duy nhất từ report cũ.

Đã khôi phục script gốc đúng SHA, chạy lại 20 lượt với cặp image và giới hạn tài nguyên cũ, đều đạt 38/38. Trong đó có 7 lượt khởi động lại worker, 15 lượt có trace và 5 lượt không bọc API bằng tracer. Không diễn giải các lượt PASS thành bằng chứng lần lỗi cũ chưa từng xảy ra. Stability review vẫn OPEN.

## Bằng chứng lịch sử

- [Report lỗi đầu](../deploy/dist/api-worker-smoke-20261013/report/integration-preview2.json) có SHA `fc5594a095ea68578eb5442edfa5bf212fa4026aa5ebf81a617d52dcacc568fc`: 32 kiểm tra đạt, rồi assertion thất bại; không có response hoặc envelope.
- Thời điểm report: `02:36:05.626243Z`–`02:36:07.860725Z`, khoảng 2,234 giây. Lịch sử lệnh `exec-9424de06-5f6d-40fb-b229-44d319d43a4b` của chat ghi tổng thời gian lệnh 8,005 giây, gồm stop/create volumes/start worker và client. Script đặt timeout 90 giây. Vì vậy timeout 90 giây không phù hợp với lần lỗi này; không chỉ dựa vào đồng hồ bên trong container.
- Lệnh gốc dừng `slc-api-worker-synthetic-20261013`, tạo spool/evidence riêng cho worker thứ hai rồi khởi động `slc-api-worker-synthetic2-20261013` (ID `a4ea4b66…`). Worker cũ dùng spool thứ nhất. Không có bằng chứng hai worker này cùng ghi spool trong lượt lỗi.
- Hai kịch bản hợp lệ được lưu trước lỗi. Truy vấn DB lúc đó đã ghi nhận đúng hai row; chưa có bằng chứng kết quả sai hash thứ ba được lưu.
- Diff sau lỗi chỉ thêm guard DB và thông tin response của script; không thay logic API/worker/tamper. Bản gốc phục hồi [historical_script.py](../deploy/dist/integration-rootcause-20261013/historical_script.py) có SHA `ea523c81ae3da14450c14471a5a1dcac80c1c2fd8d354969840cb3e06bd7cefb`, khớp checksum nguồn đã lưu trước lỗi. File này là evidence; chạy qua runner có guard hiện hành, không chạy trực tiếp bản guard lịch sử.

## Chạy lại có kiểm soát

App `5.1.1-preview.1` pinned index `sha256:8fee0b7383ceb64a4b464ff0dadaad7f8fc6b52a9f132d42eb83123b60eea3cc`, worker `16.2.15-minimal-preview.2` pinned index `sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893`. Worker CPU 1/RAM 1536 MiB/PIDs 32, client CPU 1/RAM 1536 MiB/PIDs 128; UID 10001/rootfs chỉ đọc/cap-drop ALL/no-new-privileges. Fixture requests và metadata giữ đúng hash lịch sử.

DB riêng `osdmap_synthetic_rootcause_20261013`, network internal `slc-v51-release-tests`, spool/evidence volumes riêng `slc-integration-rootcause-*`. Nguồn Ceph là adapter trong bộ nhớ với đúng ba hành động đọc trên map tạo offline. Không dùng SSH/executor hoặc dữ liệu Ceph lab.

[Runner điều tra](../packaging/osdmap/diagnose_historical_integration.py) kiểm marker, URI DB và cấu hình DB đã resolve bằng guard hiện hành trước nhập `app.db`; bắt buộc SHA script gốc khớp. Trace ghi capability, envelope, bước decode/validate, loại exception/errno, mã HTTP và thời lượng; không ghi exception text, connection string hoặc SQL. [Danh sách 20 report và hash](../deploy/dist/integration-rootcause-20261013/replay-manifest.json) có SHA `2023b4c06b42db8932a8a1a6358d1fb5ca9839de83c9a318cf65db8761b992f2`.

15 trace đều chứng minh request tamper nhận envelope thành công, decode chạy, hash đã sửa tới validator và nhận 503 `OSDMAP_RESULT_IDENTITY_MISMATCH`. Giá trị heartbeat trong trace là đọc lại sau kiểm tra, có thể khác file mà capability vừa đọc. Tracer cũng ảnh hưởng timing; năm lượt không bọc API vẫn đạt nhưng không chứng minh mọi race đã bị loại trừ.

## Ba lỗi đối chứng tạo cùng triệu chứng

Đây là fault injection chủ động trong runner synthetic, **không phải tái hiện nguyên nhân thực của lần lịch sử**. Mỗi lỗi đều làm bản script gốc đạt 32 bước rồi thất bại ở cùng assertion.

| Lỗi được tiêm | HTTP thực nhận | Trước bước sửa hash |
|---|---|---|
| Capability không còn mới | 503 / `OSDMAP_CAPABILITIES_STALE` | Chưa nhận envelope |
| Worker trả tool failure | 409 / `OSDMAP_TOOL_FAILED` | Envelope lỗi, chưa decode thành công |
| OSError trong đường xử lý kết quả | 503 / `OSDMAP_UNAVAILABLE` | Chưa tới validator |

Report `fault-control-*-http.json` trong [thư mục điều tra](../deploy/dist/integration-rootcause-20261013) ghi response thực. Ba control đầu chưa ghi HTTP được giữ riêng; ba lượt sau thêm HTTP trace, không ghi đè kết quả trước.

## Bổ sung để tránh mất nguyên nhân lần sau

[Script integration hiện hành](../packaging/osdmap/test_api_worker_integration.py) giờ ghi `tamper_diagnostic`: capability ngay tại create, envelope, decode thành công hay chưa, source-call sequence, thời lượng và DB/artifact có đổi không. Assertion bắt buộc `tamper_injection_executed=true` cùng mã HTTP đúng. Guard 9/9 và integration mới 38/38 đạt trên app hiện hành; [report](../deploy/dist/integration-rootcause-20261013/current-diagnostic-complete.json) SHA `d3fe47682280eabe845f02d391a833d82a4c49b4cbc081176f94dd3487cdb35f` có marker true, đúng 503 và không lưu kết quả sai.

Đã giữ archive riêng của DB synthetic (54 row hợp lệ từ 20 replay, 6 control và 1 lượt diagnostic); đọc TOC custom archive đạt, chưa chạy restore rehearsal. Worker/DB kiểm thử được dừng, volumes/report/archive giữ lại. Localhost vẫn `5.1.1-preview.2`, sẵn sàng/chỉ đọc. Không thay image hoặc cấu hình chạy vì chưa có lỗi production được tái hiện. [Manifest điều tra](../deploy/releases/integration-rootcause-20261013.yaml) ghi hash và giới hạn.
