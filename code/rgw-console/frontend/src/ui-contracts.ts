export type TelemetryStatus =
  | "NOT_CONFIGURED"
  | "NO_SNAPSHOT"
  | "FRESH"
  | "STALE"
  | "EXECUTOR_UNAVAILABLE"
  | "COLLECTOR_ERROR";

export type ConsoleView = "overview" | "metrics" | "inventory" | "comparison" | "dashboard" | "performance" | "upload" | "random" | "stream" | "objects" | "volumes";
export type RuntimeConfig = {
  console_read_only: boolean;
  application_version: string;
  features: { upgrade: boolean; lab: boolean; legacy_rgw: boolean; legacy_rbd: boolean };
};

export function parseRuntimeConfig(value: unknown): RuntimeConfig {
  const config = value as Partial<RuntimeConfig> | null;
  const names = ["upgrade", "lab", "legacy_rgw", "legacy_rbd"] as const;
  if (!config || typeof config.console_read_only !== "boolean" || typeof config.application_version !== "string"
      || !config.application_version || !config.features || names.some(name => typeof config.features?.[name] !== "boolean")) {
    throw new Error("Cấu hình giao diện không hợp lệ hoặc chưa sẵn sàng.");
  }
  return config as RuntimeConfig;
}

export const CORE_CONSOLE_VIEWS: ConsoleView[] = ["overview", "metrics", "inventory", "comparison"];
export const LEGACY_CONSOLE_VIEWS: ConsoleView[] = ["dashboard", "performance", "upload", "random", "stream", "objects", "volumes"];

export function consoleViewDisabledReason(view: ConsoleView, config: RuntimeConfig): string | null {
  if (["inventory", "comparison"].includes(view) && !config.features.upgrade) return "Chưa cấu hình tính năng thu thập hiện trạng.";
  if (LEGACY_CONSOLE_VIEWS.includes(view)) {
    if (config.console_read_only) return "Đã khóa theo chế độ chỉ đọc. Công cụ cũ chỉ dùng trong môi trường lab cho phép ghi.";
    if (view === "volumes" && !config.features.legacy_rbd) return "Chưa cấu hình công cụ RBD cũ.";
    if (view !== "volumes" && !config.features.legacy_rgw) return "Chưa cấu hình công cụ RGW cũ.";
  }
  return null;
}

export function visibleConsoleViews(config: RuntimeConfig): ConsoleView[] {
  return [...CORE_CONSOLE_VIEWS, ...LEGACY_CONSOLE_VIEWS].filter(view => !consoleViewDisabledReason(view, config));
}

export function consoleViewFromHash(hash: string): ConsoleView | null {
  const raw = new URLSearchParams(hash.replace(/^#/, "")).get("view");
  const value = raw === "evidence" ? "comparison" : raw;
  return [...CORE_CONSOLE_VIEWS, ...LEGACY_CONSOLE_VIEWS].includes(value as ConsoleView) ? value as ConsoleView : null;
}

export const CAPACITY_GUIDANCE: Partial<Record<TelemetryStatus, string>> = {
  NOT_CONFIGURED: "Cấu hình FSID, executor token, SSH target và allowlist rồi bật profile ceph-ssh.",
  NO_SNAPSHOT: "Collector chưa lưu snapshot; bật profile ceph-ssh và chờ chu kỳ thu thập.",
  STALE: "Snapshot cuối đã quá hạn; kiểm tra collector và kết nối SSH.",
  EXECUTOR_UNAVAILABLE: "Node SSH executor không truy cập được; kiểm tra container, token và SSH.",
  COLLECTOR_ERROR: "Collector nhận dữ liệu không hợp lệ hoặc scope chưa đầy đủ; xem error code.",
};

export function resolveTelemetryStatus(
  apiError: boolean,
  reportedStatus: TelemetryStatus | undefined,
  legacyFresh: boolean | undefined,
): TelemetryStatus {
  if (apiError) return "EXECUTOR_UNAVAILABLE";
  if (reportedStatus) return reportedStatus;
  return legacyFresh ? "FRESH" : "NO_SNAPSHOT";
}

export function capacityScopeLabel(osds: number[] | undefined, pools: string[] | undefined): string {
  if (!osds?.length) return "Chưa có phạm vi OSD";
  return `${osds.length} OSD · ${pools?.join(", ") || "chưa chọn pool"}`;
}

export function capacityStateLabel(state: string): string {
  const labels: Record<string, string> = { NORMAL: "Bình thường", CONNECTING: "Đang kết nối", UNAVAILABLE: "Không có dữ liệu", THROTTLED: "Cảnh báo sớm", PAUSED_CAPACITY: "Chạm ngưỡng dung lượng", PAUSED_REMAP: "Placement đang thay đổi", RECONCILING: "Đang đối soát", EMERGENCY_CAPACITY: "Dung lượng nguy cấp", BLOCKED_TELEMETRY: "Thiếu dữ liệu để đánh giá", BLOCKED_UNKNOWN_CAPACITY: "Chưa xác định phạm vi dung lượng", READ_CLEANUP_ONLY: "Chỉ quan sát và dọn dẹp" };
  return labels[state] || state;
}
export function telemetryStatusLabel(status: TelemetryStatus): string {
  return ({ FRESH: "Dữ liệu mới", STALE: "Dữ liệu cũ", NO_SNAPSHOT: "Chưa có mẫu", NOT_CONFIGURED: "Chưa cấu hình", EXECUTOR_UNAVAILABLE: "Không đọc được nguồn", COLLECTOR_ERROR: "Lỗi thu thập" })[status];
}

export const CRUD_OPERATIONS = ["PUT", "GET", "HEAD", "LIST", "UPDATE", "DELETE"] as const;
export type CrudOperation = (typeof CRUD_OPERATIONS)[number];

export const CRUD_DEFAULT_OPERATION_WEIGHTS: Record<CrudOperation, number> = {
  PUT: 28,
  GET: 28,
  HEAD: 3,
  LIST: 2,
  UPDATE: 20,
  DELETE: 19,
};

export function operationCountLabel(counts: Partial<Record<CrudOperation, number>> | undefined): string {
  return CRUD_OPERATIONS.map(name => `${name} ${counts?.[name] || 0}`).join(" · ");
}

const NON_RESUMABLE_PAUSE_REASONS = new Set([
  "RECONCILE_REQUIRED_AFTER_AMBIGUOUS_MUTATION",
  "LEASE_EXPIRED_RECONCILE_REQUIRED",
]);

export function canResumeStreamJob(state: string, pausedReason?: string | null): boolean {
  return state === "paused" && !NON_RESUMABLE_PAUSE_REASONS.has(pausedReason || "");
}

export function isRbdDeleteConfirmed(expectedName: string, typedName: string): boolean {
  return typedName === expectedName;
}

export function isRbdFileAccessState(state: string): boolean {
  return state === "MOUNTED" || state === "READY";
}

export function rbdPreviewKind(mimeType: string | null | undefined): "text" | "image" | "pdf" | null {
  const mime = (mimeType || "").toLowerCase().split(";", 1)[0];
  if (mime.startsWith("text/") || mime === "application/json") return "text";
  if (mime.startsWith("image/")) return "image";
  if (mime === "application/pdf") return "pdf";
  return null;
}

export function inventoryValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" || (typeof value === "number" && !Number.isFinite(value)) ? "UNKNOWN" : String(value);
}

export function qualityTone(quality: string | null | undefined): "valid" | "partial" | "inconclusive" {
  if (quality === "VALID") return "valid";
  if (quality === "PARTIAL") return "partial";
  return "inconclusive";
}

export function comparisonTone(status: string | null | undefined): "valid" | "partial" | "inconclusive" {
  if (status === "COMPARABLE") return "valid";
  if (status === "INCONCLUSIVE") return "partial";
  return "inconclusive";
}

export function parseOsdIdInput(value: string): { ids: number[] | null; error: string | null } {
  if (!value.trim()) return { ids: null, error: null };
  const tokens = value.split(",").map(item => item.trim()).filter(Boolean);
  if (!tokens.length || tokens.some(token => !/^\d+$/.test(token))) {
    return { ids: null, error: "OSD IDs phải là số nguyên không âm, phân tách bằng dấu phẩy." };
  }
  const ids = tokens.map(Number);
  if (ids.some(id => !Number.isSafeInteger(id))) {
    return { ids: null, error: "OSD ID nằm ngoài giới hạn số nguyên an toàn." };
  }
  if (new Set(ids).size !== ids.length) {
    return { ids: null, error: "OSD IDs không được lặp lại." };
  }
  if (ids.length > 128) {
    return { ids: null, error: "Mỗi collection chỉ nhận tối đa 128 OSD." };
  }
  return { ids, error: null };
}
