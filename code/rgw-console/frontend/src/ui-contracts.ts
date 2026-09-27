export type TelemetryStatus =
  | "NOT_CONFIGURED"
  | "NO_SNAPSHOT"
  | "FRESH"
  | "STALE"
  | "EXECUTOR_UNAVAILABLE"
  | "COLLECTOR_ERROR";

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
  if (!osds?.length) return "No OSD scope";
  return `${osds.length} OSD · ${pools?.join(", ") || "no pool"}`;
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
