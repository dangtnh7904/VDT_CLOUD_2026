# Runbook thu As-Is read-only cho Quincy 17.2.7 → Reef 18.2.7

**Trạng thái ngày 12/10/2026: collector đã được kiểm plan mode và bundle validator; chưa chạy với Ceph cluster.** Tài liệu này biến một phần [register As-Is](./AS-IS-EVIDENCE.md) thành bundle có checksum. Nó không phải approval truy cập production và không tự đổi bất kỳ `AS-*` nào sang `CAPTURED`.

## Phạm vi collector

[`tools/capture_as_is.ps1`](./tools/capture_as_is.ps1) có 23 lệnh mặc định, chỉ đọc qua CLI `ceph`. Chúng chạm các nhóm `AS-002`→`AS-006`, `AS-008`→`AS-012`, `AS-014`, `AS-016`, `AS-020`, `AS-022`, `AS-023`. Hai option bổ sung cho `AS-007`, `AS-008` và `AS-017` bị tắt mặc định vì config/service spec có thể chứa credential hoặc endpoint nhạy cảm.

Collector không tự thu đủ 24 nhóm. Artifact/SBOM (`AS-001`), host-local ceph-volume/client inventory, RBD/RGW feature sampling, external integrations, backup/restore, SLO và sign-off vẫn cần owner và nguồn riêng. Một command thất bại được giữ nguyên stdout/stderr/exit code, không bị bỏ qua.

## Guardrail

- Mặc định script chỉ in plan; không gọi `ceph` và không tạo thư mục.
- Chỉ `-Execute` mới chạy. Operator phải có approval và credential read-only riêng.
- Script từ chối ghi đè bundle đã tồn tại.
- Mỗi command dùng process trực tiếp, không thông qua shell; stdout/stderr/meta tách riêng.
- Output của command đánh dấu nhạy cảm được redact trước khi ghi. Redaction tự động vẫn phải được con người review trước khi chia sẻ archive.
- Không có `set`, `apply`, `restart`, `redeploy`, `pause`, `resume`, `repair`, `migrate`, `trim`, `zap`, feature-floor hoặc mutation command.

## Xem plan an toàn

Lệnh sau chỉ in 23 command mặc định:

```powershell
pwsh -NoProfile -File .\tools\capture_as_is.ps1
```

Xem thêm config/spec commands mà vẫn không thực thi:

```powershell
pwsh -NoProfile -File .\tools\capture_as_is.ps1 `
  -IncludeConfiguration `
  -RepresentativeDaemon osd.0 `
  -IncludeServiceSpecs
```

Review tên daemon đại diện, output root, quyền archive và redaction policy trước khi thêm `-Execute`.

## Capture sau khi được phê duyệt

Ví dụ cú pháp; tài liệu không chạy lệnh này:

```powershell
pwsh -NoProfile -File .\tools\capture_as_is.ps1 `
  -Execute `
  -OutputRoot E:\ceph-upgrade-evidence\h3 `
  -RunId h3-as-is-20261012T220000Z
```

Nếu cần config/spec, thêm các switch ở phần plan. Không dùng thư mục đồng bộ công khai hoặc vị trí mà người ngoài nhóm evidence có thể đọc.

## Bundle và integrity

Một bundle gồm:

```text
<run-id>/
|-- run.json
|-- commands.json
|-- results.json
|-- MANIFEST.sha256
`-- commands/
    |-- <command>.stdout.txt
    |-- <command>.stderr.txt
    `-- <command>.meta.json
```

`run.json` giữ identity comparison và endpoint SHA. `commands.json` giữ plan; `results.json` giữ exit code/timestamp/duration/path; `MANIFEST.sha256` khóa mọi artifact còn lại.

Kiểm integrity và schema:

```powershell
python .\tools\validate_as_is_bundle.py --bundle E:\ceph-upgrade-evidence\h3\<run-id>
```

Yêu cầu mọi command thành công:

```powershell
python .\tools\validate_as_is_bundle.py `
  --bundle E:\ceph-upgrade-evidence\h3\<run-id> `
  --require-success
```

Validator kiểm identity, command/result order, artifact paths và SHA-256. Nó không đánh giá nội dung Ceph có đúng topology mong đợi hay không và không tự cập nhật status.

## Closure sau capture

1. Review redaction và quyền archive trước khi mở output.
2. Triage mọi exit code khác 0; rerun có run ID mới, không ghi đè bundle.
3. Đối chiếu từng artifact với tiêu chí trong `AS-IS-EVIDENCE.md`; bundle hợp lệ nhưng thiếu command/service/host vẫn là `NOT_CAPTURED` hoặc `BLOCKED`.
4. Bổ sung evidence ngoài collector, checksum và owner/sign-off vào `AS-024`.
5. Chỉ sau review mới đổi từng nhóm sang `CAPTURED`, `BLOCKED` hoặc `NOT_APPLICABLE`; không đổi runtime gate thành PASS.
