# Report integration có mã HTTP và lỗi worker

Runner `packaging/osdmap/test_api_worker_integration.py` hiện tạo report `diagnostic_schema_version: 2`. Cách chạy giữ nguyên các tham số `--fixtures`, `--spool`, `--evidence`, `--report`; mount cả thư mục test `/tests` để có module `integration_diagnostics.py`. Chọn tên report mới cho mỗi lần chạy vì runner không ghi đè report cũ.

## Đọc report thất bại

Xem `failure_context` trước. Nó ghi tên bước, assertion lỗi, request HTTP và service của **đúng request đó**, cùng loại exception. HTTP có method/endpoint/status/code/thời lượng; worker có capability, envelope, bước decode/validate, exception code/status/errno, source-call sequence và trạng thái DB/artifact trước/sau.

Ví dụ từ [report thử map hỏng](../deploy/dist/integration-reporting-20261013/failure-corrupt-map-with-sources.json):

```json
{
  "status": "FAILED",
  "failed_check": "no-op_created_201",
  "failure_context": {
    "stage": "no-op.create",
    "http": {"status_code": 409, "code": "OSDMAP_TOOL_FAILED"},
    "service": {
      "last_worker_stage": "WORKER_RESULT_DECODE",
      "worker_envelope": {"ok": false, "code": "OSDMAP_TOOL_FAILED"},
      "storage_changed": false
    }
  }
}
```

Đây là lỗi được chủ động tạo trên map synthetic để kiểm tra report; không phải lỗi Ceph lab. Nó xảy ra trước bước tamper nhưng vẫn ghi được nguyên nhân worker trả về.

`http_requests` và `service_requests` giữ diễn biến các request trước đó. `http_sequence` nối service với HTTP. Nếu request bị chặn trước khi vào service, `failure_context.service=null`, không gắn trace của request trước. Capability trả HTTP 200 nhưng `available=false` vẫn giữ mã lý do. Lỗi kết nối chưa nhận được response thì `status_code=null` và có exception type; không giả thành HTTP 503 hoặc 0. Lỗi JSON vẫn giữ status đã nhận và `json_decode_exception`.

`storage_changed=null` nghĩa là chưa xác định được vì diagnostic không đọc được trạng thái; `false` nghĩa là đã so và không đổi. Lỗi lấy diagnostic phụ được ghi trong `diagnostic_errors` và không che lỗi gốc.

## Giới hạn nội dung và tái kiểm chứng

Report không sao chép request/response body, header xác thực, worker message, exception text, SQL hoặc connection string. Chỉ giữ code có định dạng/độ dài cho phép và metadata cần chẩn đoán. Tối đa 512 HTTP trace/128 service trace; nếu vượt giới hạn, giữ trace mới nhất và đánh dấu đã cắt.

Mỗi report mới giữ hash và bản sao bất biến của hai file nguồn runner/diagnostic dưới `sources/<sha256>.py`. Nhờ đó đổi code sau này vẫn đọc được đúng nguồn của lượt đã chạy. Không sao chép env, SSH key hoặc profile. Report được ghi qua file tạm; nếu không ghi được file, stdout vẫn có metadata lỗi ghi report và ngữ cảnh HTTP/service đã thu.

## Kiểm thử đã thực hiện — 13/10/2026

26 unit tests đạt: 9 guard và 17 diagnostic. Các test kiểm HTTP lỗi trước tamper, JSON sai/response quá lớn, lỗi kết nối, envelope sai, snapshot phụ lỗi, redaction, liên kết request và source snapshot không ghi đè.

| Tình huống chủ động tạo | Report thực nhận |
|---|---|
| Capability stale ở create đầu | 503 / `OSDMAP_CAPABILITIES_STALE`, chưa nhận envelope |
| Map hỏng tới worker thật | 409 / `OSDMAP_TOOL_FAILED`, envelope `ok=false`, storage không đổi |
| Mất kết nối trước response | HTTP null, `ConnectionError`, service null |
| Response không phải JSON | HTTP 502, `JSONDecodeError`, service null |

[Report bình thường](../deploy/dist/integration-reporting-20261013/success-with-source-snapshots.json) đạt 38/38. Source snapshots của report thành công/thất bại đều khớp hash. [Manifest nghiệm thu](../deploy/releases/integration-reporting-20261013.yaml) giữ bằng chứng. Các report lỗi lịch sử giữ nguyên; thông tin không được ghi ở lần cũ không thể bổ sung bằng suy đoán. Bộ test này không đóng stability review của lỗi lịch sử hoặc nghiệm thu production.
