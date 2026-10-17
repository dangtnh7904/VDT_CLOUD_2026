export const FIELD_LABELS: Record<string, string> = {
  filesystem: "Hệ thống tệp", filesystem_id: "ID hệ thống tệp", fsmap_epoch: "Epoch FSMap", identity_source: "Nguồn định danh", state: "Trạng thái CephFS", gid: "GID daemon", laggy_since: "Chậm từ lúc", environment: "Môi trường máy SSH client",
  id: "Định danh", name: "Tên", scope_type: "Phạm vi", health: "Sức khỏe cụm", osdmap_epoch: "Epoch OSDMap", flags: "Cờ cụm", osd_count: "Số OSD",
  hostname: "Máy chủ", host: "Máy chủ", role: "Vai trò", status: "Trạng thái", daemon_status: "Trạng thái daemon", ceph_version: "Phiên bản Ceph", ceph_version_short: "Phiên bản ngắn",
  osd_fsid: "UUID OSD", osd_id: "OSD ID", container_id: "Container ID", container_image: "Image container", container_image_id: "Image ID", container_image_digests: "Digest image",
  started_at: "Daemon khởi động lúc", orchestrator_observed_at: "Orchestrator quan sát lúc", pg_count: "Số PG", primary_count: "Số PG primary", device_class: "Lớp thiết bị",
  crush_weight: "CRUSH weight", reweight: "Reweight OSD", primary_affinity: "Primary affinity", up: "OSD up", in: "OSD in", rank: "Rank MON", in_quorum: "Trong quorum", election_epoch: "Epoch bầu chọn", monmap_epoch: "Epoch MONMap",
  address: "Địa chỉ", total_bytes: "Tổng dung lượng (byte)", used_bytes: "Đã dùng (byte)", available_bytes: "Còn trống (byte)", used_percent: "Đã dùng (%)", payload: "Bằng chứng gốc đã che thông tin bí mật",
  "container.cpu_percentage": "CPU container (%)", "container.memory_usage": "RAM container (byte)",
  "mon.in_quorum": "MON trong quorum", "mon.election_epoch": "Epoch bầu chọn MON", "mgr.available": "MGR sẵn sàng", "osd.utilization_percent": "Dung lượng OSD đã dùng", "osd.used_kb": "OSD đã dùng", "osd.pg_count": "Số PG trên OSD"
};
for (const scope of ["cluster", "osd"]) for (const [name, text] of Object.entries({ read_iops: "IOPS đọc", write_iops: "IOPS ghi", total_iops: "IOPS tổng", read_bytes_per_second: "Thông lượng đọc", write_bytes_per_second: "Thông lượng ghi", total_bytes_per_second: "Thông lượng tổng" })) FIELD_LABELS[`${scope}.${name}`] = `${text} ${scope === "cluster" ? "toàn cụm" : "OSD"}`;
export const REASON_LABELS: Record<string, string> = { QUALITY_INSUFFICIENT: "Chất lượng nguồn chưa đủ", UNIT_CHANGED: "Đơn vị khác nhau", INCARNATION_CHANGED: "Daemon đã được thay hoặc khởi động lại", FIELD_UNAVAILABLE: "Thiếu trường ở một phía", METRIC_UNAVAILABLE: "Thiếu chỉ số ở một phía", COUNTER_RESET: "Counter đã reset", SAMPLE_WINDOW_UNAVAILABLE: "Nguồn không cung cấp cửa sổ mẫu", SOURCE_FIELD_MISSING: "Nguồn không có trường này" };
export function fieldLabel(value: string): string { return FIELD_LABELS[value] || (value.startsWith("metrics.") ? FIELD_LABELS[value.slice(8)] || value : value); }
REASON_LABELS.INVALID_SOURCE_TIMESTAMP = "Thời điểm nguồn nằm trong tương lai hoặc không hợp lệ";
REASON_LABELS.INVALID_DAEMON_SOURCE_SCHEMA = "Nguồn không đúng cấu trúc daemon đã hỗ trợ";
REASON_LABELS.KIND_CHANGED = "Loại chỉ số khác nhau; không tính chênh lệch";
REASON_LABELS.SOURCE_NONFINITE = "Nguồn trả giá trị số không hữu hạn";
export function reasonLabel(value?: string | null): string { return value ? REASON_LABELS[value] || value : "—"; }
Object.assign(REASON_LABELS, { INVALID_SOURCE_SCHEMA: "Nguồn không đúng cấu trúc đã hỗ trợ", SOURCE_PREDATES_REQUEST: "Nguồn có trước yêu cầu đọc này", INVALID_SOURCE_FIELD: "Trường dữ liệu nguồn không hợp lệ", METRIC_KIND_CHANGED: "Loại chỉ số đã thay đổi", METRIC_VALUE_INVALID: "Giá trị chỉ số không hợp lệ", NUMERIC_OUT_OF_RANGE: "Chênh lệch số vượt giới hạn" });
