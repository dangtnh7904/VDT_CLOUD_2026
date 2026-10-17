import type { Daemon, Observation } from "./as-is-contracts.ts";
import { fieldLabel } from "./labels.ts";

export function sourceWarningLines({ observation, daemon, daemons, limitations = [], environment }: { observation?: Observation; daemon?: Daemon; daemons?: Daemon[]; limitations?: string[]; environment?: unknown }): string[] {
  const lines: string[] = [];
  const add = (line: string) => { if (line && !lines.includes(line)) lines.push(line); };
  const rows = daemon ? [daemon] : daemons || observation?.daemons || [];
  if (observation?.missing_daemon_keys?.length) add(`Chưa có: ${observation.missing_daemon_keys.join(", ")}.`);
  const sources = observation?.sources || {};
  for (const [name, raw] of Object.entries(sources)) {
    const source = raw as { quality?: string } | null;
    if (["UNAVAILABLE", "UNSUPPORTED", "NOT_CONFIGURED", "PARTIAL"].includes(source?.quality || "")) add(`Chưa đủ dữ liệu nguồn ${name}.`);
    if (source?.quality === "STALE") add(`Nguồn ${name} có dữ liệu cũ.`);
  }
  const missing = new Set<string>(); let staleContainer = false; let missingWindow = false;
  for (const row of rows) for (const metric of row.metrics || []) {
    if (metric.value == null || ["UNAVAILABLE", "UNSUPPORTED", "NOT_CONFIGURED"].includes(metric.quality || "")) missing.add(fieldLabel(metric.metric_id));
    else if (metric.quality === "STALE") {
      if (metric.metric_id.startsWith("container.")) staleContainer = true;
      else add(`Dữ liệu cũ: ${fieldLabel(metric.metric_id)}.`);
    }
    if (metric.reason === "SAMPLE_WINDOW_UNAVAILABLE") missingWindow = true;
  }
  if (missing.size) add(`Chưa có chỉ số hợp lệ: ${[...missing].join(", ")}.`);
  if (staleContainer) add("CPU/RAM container đang dùng mẫu nguồn cũ.");
  if (missingWindow) add("Chưa có cửa sổ đo CPU container.");
  const notes = [...(observation?.limitations || []), ...rows.flatMap(row => row.limitations || []), ...limitations];
  for (const note of notes) {
    if (/host\/process|process\/network|percentile/i.test(note)) add("Chưa có đầy đủ telemetry host/process/network và percentile độ trễ.");
    else if (/TIMESTAMP_UNAVAILABLE/.test(note)) add("Chưa có thời điểm đo container hợp lệ.");
    else if (/UNAVAILABLE|UNSUPPORTED|MISSING/.test(note)) add(`Chưa có: ${note.split(":")[0]}.`);
    else if (/chưa|thiếu|không hỗ trợ|không có|cannot|not supported|unavailable|not checked|not implemented/i.test(note)) add(note.slice(0, 220));
  }
  const env = (environment || observation?.system?.environment) as { tools?: Record<string, { version?: string; quality?: string }> } | undefined;
  const tools = Object.entries(env?.tools && typeof env.tools === "object" && !Array.isArray(env.tools) ? env.tools : {}).filter(([, value]) => !value || typeof value !== "object" || !value.version || value.quality !== "VALID").map(([name]) => name);
  if (tools.length) add(`Chưa có thông tin công cụ: ${tools.join(", ")}.`);
  return lines;
}
