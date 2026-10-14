export const DAEMON_TYPES = ["mon", "mgr", "osd", "rgw", "mds"] as const;
export type DaemonType = typeof DAEMON_TYPES[number];
export type Phase = "BEFORE" | "DURING" | "AFTER";
export const PHASE_LABELS: Record<Phase, string> = { BEFORE: "Trước nâng cấp", DURING: "Trong nâng cấp", AFTER: "Sau nâng cấp" };
export const QUALITY_LABELS: Record<string, string> = { VALID: "Dữ liệu hợp lệ", PARTIAL: "Dữ liệu một phần", UNKNOWN: "Chưa xác định", INCONCLUSIVE: "Chưa đủ dữ liệu", FAILED: "Thất bại", COMPLETE: "Hoàn tất", COMPLETED: "Hoàn tất", FRESH: "Dữ liệu mới", STALE: "Dữ liệu cũ", UNAVAILABLE: "Chưa có nguồn", UNSUPPORTED: "Chưa hỗ trợ", NOT_CONFIGURED: "Chưa cấu hình", DELETED: "Đã xóa" };
export type DaemonMetric = { metric_id: string; value: unknown; unit?: string; observed_at?: string; quality?: string; reason?: string; window_seconds?: number; [key: string]: unknown };
export type Daemon = { key: string; type: DaemonType; id: string; name?: string; observed_at?: string; quality: string; fields: Record<string, unknown>; metrics: DaemonMetric[]; limitations: string[] };
export type Observation = { id: string; kind: string; cluster_id: string; fsid: string; started_at: string; completed_at: string; observed_at: string; quality: string; daemons: Daemon[]; system: Record<string, unknown>; sources: Record<string, unknown>; missing_daemon_keys: string[]; capabilities: Partial<Record<DaemonType, boolean>>; limitations: string[]; phase?: Phase; note?: string; sha256?: string; deleted_at?: string | null; [key: string]: unknown };
export type CollectionSummary = { id: string; fsid: string; phase: Phase; note?: string; started_at: string; completed_at: string; quality: string; daemon_keys: string[]; daemon_types: DaemonType[]; deleted_at?: string | null; sha256: string };
export type CollectionPage = { items: CollectionSummary[]; next_cursor: string | null; has_more: boolean; limit: number; timezone: string };
export function labelQuality(value?: string): string { return QUALITY_LABELS[value || "UNKNOWN"] || value || "Chưa xác định"; }
export function showValue(value: unknown): string { return value === null || value === undefined || value === "" || (typeof value === "number" && !Number.isFinite(value)) ? "Chưa có dữ liệu" : typeof value === "boolean" ? value ? "Có" : "Không" : typeof value === "object" ? JSON.stringify(value) : String(value); }
export function localTime(value?: string | null): string { if (!value) return "Chưa có thời điểm"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "Thời điểm không hợp lệ" : new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "medium", timeZone: "Asia/Saigon" }).format(date) + " (UTC+7)"; }
export function pageRows<T>(rows: T[], page: number): T[] { return rows.slice((Math.max(1, page) - 1) * 10, Math.max(1, page) * 10); }
export function toggleKeys(selected: string[], keys: string[], checked: boolean): string[] { return checked ? [...new Set([...selected, ...keys])] : selected.filter(key => !keys.includes(key)); }
export function collectionPairError(a?: CollectionSummary, b?: CollectionSummary, type?: string): string | null {
  if (!a || !b) return "Chọn hai bộ As-is để so sánh.";
  if (a.id === b.id) return "Chọn hai bộ As-is khác nhau.";
  if (a.deleted_at || b.deleted_at) return "Nguồn đã xóa. Hãy khôi phục trước khi so sánh.";
  if (a.fsid !== b.fsid) return "Hai bộ As-is phải thuộc cùng một cụm (FSID).";
  if (!type || !a.daemon_types.includes(type as DaemonType) || !b.daemon_types.includes(type as DaemonType)) return "Hai bộ As-is phải cùng có loại daemon đã chọn.";
  return null;
}
export function comparisonKeys(a?: CollectionSummary, b?: CollectionSummary, type?: string): string[] { return [...new Set([...(a?.daemon_keys || []), ...(b?.daemon_keys || [])])].filter(key => key.startsWith(`${type}.`)).sort(); }
/** A filtered view never modifies the saved collection or its integrity hash. */
export function scopedDaemonKeys(collection?: Pick<CollectionSummary, "daemon_keys">, daemonType?: string, daemonKey?: string): string[] {
  const key = daemonKey?.trim();
  return (collection?.daemon_keys || []).filter(value => (!daemonType || value.startsWith(`${daemonType}.`)) && (!key || value === key));
}
export function scopedDaemons(observation: Pick<Observation, "daemons">, daemonType?: string, daemonKey?: string): Daemon[] {
  const key = daemonKey?.trim();
  return observation.daemons.filter(value => (!daemonType || value.type === daemonType) && (!key || value.key === key));
}
/** Gather quality warnings from both saved sides without modifying the result. */
export function comparisonWarningDaemons(rows: { a: unknown; b: unknown }[]): Daemon[] {
  return rows.flatMap(row => [row.a, row.b]).flatMap(raw => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    const daemon = raw as Partial<Daemon>;
    if (typeof daemon.key !== "string" || typeof daemon.id !== "string" || !DAEMON_TYPES.includes(daemon.type as DaemonType) || !Array.isArray(daemon.metrics)) return [];
    return [{ ...daemon, fields: daemon.fields && typeof daemon.fields === "object" && !Array.isArray(daemon.fields) ? daemon.fields : {},
      quality: typeof daemon.quality === "string" ? daemon.quality : "UNKNOWN",
      limitations: Array.isArray(daemon.limitations) ? daemon.limitations.filter(value => typeof value === "string") : [],
      metrics: daemon.metrics.filter(metric => metric && typeof metric === "object" && !Array.isArray(metric) && typeof metric.metric_id === "string") } as Daemon];
  });
}
export function daemonScopeError(daemonKey: string, daemonType?: string): string | null {
  const key = daemonKey.trim();
  if (!key) return null;
  if (!/^(mon|mgr|osd|rgw|mds)\.[A-Za-z0-9_.-]{1,128}$/.test(key)) return "Nhập tên daemon đầy đủ, ví dụ osd.2 hoặc mon.ceph-master.";
  if (daemonType && !key.startsWith(`${daemonType}.`)) return "Daemon cụ thể phải cùng loại daemon đã chọn.";
  return null;
}
export function savedCollectionQuery(includeDeleted = false, daemonType?: string, daemonKey?: string): string {
  const query = new URLSearchParams({ include_deleted: String(includeDeleted) });
  if (daemonType) query.set("daemon_type", daemonType);
  if (daemonKey?.trim()) query.set("daemon_key", daemonKey.trim());
  return query.toString();
}
export function collectionQuery(filters: { type?: string; from?: string; to?: string; phase?: string; deleted?: boolean; search?: string; quality?: string; daemonKey?: string; cursor?: string; limit?: number }): string {
  const query = new URLSearchParams();
  if (filters.type) query.set("daemon_type", filters.type);
  if (filters.from) query.set("from_date", filters.from);
  if (filters.to) query.set("to_date", filters.to);
  if (filters.phase) query.set("phase", filters.phase);
  if (filters.search?.trim()) query.set("q", filters.search.trim());
  if (filters.quality) query.set("quality", filters.quality);
  if (filters.daemonKey?.trim()) query.set("daemon_key", filters.daemonKey.trim());
  if (filters.cursor) query.set("cursor", filters.cursor);
  query.set("limit", String(filters.limit || 10));
  query.set("include_deleted", String(Boolean(filters.deleted)));
  return query.toString();
}
export function validateWeights(changes: { osd_id: number; crush_weight: number }[]): string | null {
  if (!changes.length) return "Chọn ít nhất một OSD.";
  if (changes.length > 128) return "Mỗi kịch bản nhận tối đa 128 OSD.";
  if (new Set(changes.map(row => row.osd_id)).size !== changes.length) return "OSD không được lặp lại.";
  if (changes.some(row => !Number.isSafeInteger(row.osd_id) || row.osd_id < 0 || !Number.isFinite(row.crush_weight) || row.crush_weight < 0 || row.crush_weight > 32767)) return "OSD phải là số nguyên không âm; CRUSH weight từ 0 đến 32767.";
  return null;
}
/** Refresh untouched defaults, retain explicit edits, and remove unavailable OSDs. */
export function reconcileWeightInputs(inputs: Record<string, string>, previousDefaults: Record<string, string>, defaults: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, inputs[key] !== undefined && inputs[key] !== previousDefaults[key] ? inputs[key] : value]));
}
export function mappingValidationMessage(quality?: string): string {
  if (quality === "PARTIAL") return "Placement thiếu thành viên so với số bản sao pool. Dù không có PG thay đổi, đây không phải kết quả đầy đủ hoặc chứng minh thay đổi an toàn.";
  if (quality === "VALID") return "Số thành viên placement đủ theo cấu hình pool; không đồng nghĩa đã kiểm chứng failure domain hoặc thay đổi an toàn.";
  return "Bản dự đoán này chưa có bằng chứng kiểm tra đủ thành viên placement. Hãy tính lại bằng worker đã hỗ trợ kiểm tra.";
}
