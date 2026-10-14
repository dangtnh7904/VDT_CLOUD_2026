type ErrorDetail = {
  request_id?: string;
  code?: string;
  message?: string;
  retryable?: boolean;
  observed_state?: unknown;
};

export class ApiError extends Error {
  status: number;
  code?: string;
  requestId?: string;
  retryable?: boolean;
  observedState?: unknown;

  constructor(status: number, detail: ErrorDetail | string | undefined) {
    const structured = typeof detail === "object" && detail !== null ? detail : undefined;
    super(structured?.message || (typeof detail === "string" ? detail : `HTTP ${status}`));
    this.name = "ApiError";
    this.status = status;
    this.code = structured?.code;
    this.requestId = structured?.request_id;
    this.retryable = structured?.retryable;
    this.observedState = structured?.observed_state;
  }
}

const isRawBody = (body: BodyInit | null | undefined) =>
  body instanceof FormData || body instanceof Blob || body instanceof ArrayBuffer || ArrayBuffer.isView(body as any);

const errorDetail = (payload: any, fallback: string): ErrorDetail | string => {
  if (payload?.detail) return payload.detail;
  if (payload?.message) return payload;
  return fallback;
};

export const api = async <T = any>(path: string, options?: RequestInit): Promise<T> => {
  const headers = new Headers(options?.headers);
  if (options?.body && !isRawBody(options.body) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes((options?.method || "GET").toUpperCase())) {
    headers.set("X-Console-Request", "1");
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw new ApiError(response.status, errorDetail(body, response.statusText));
  }
  if (response.status === 204) return undefined as T;
  return response.json();
};

export type ExportFormat = "json" | "csv" | "zip" | "md";
export type ExportSource = "osd_collection" | "osd_comparison" | "osd_config_diff" | "performance" | "capacity" | "cluster_collection";
export type ConsoleExportRequest = {
  source: ExportSource;
  source_id?: string;
  comparison_id?: string;
  format: ExportFormat;
  filters?: {
    osd_ids?: number[];
    resource_ids?: string[];
    source?: "application" | "ceph" | "device";
    scope_type?: "cluster" | "osd" | "pool" | "image" | "job" | "operation" | "mon" | "mgr" | "host";
    scope?: string;
    from?: string;
    to?: string;
    step?: number;
    metric_ids?: string[];
  };
};

export function exportFilename(disposition: string | null, fallback: string): string {
  const extended = disposition?.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)?.[1];
  const regular = disposition?.match(/filename\s*=\s*(?:"([^"]*)"|([^;]+))/i);
  let candidate = regular?.[1] || regular?.[2]?.trim() || fallback;
  if (extended) {
    try { candidate = decodeURIComponent(extended.trim().replace(/^"|"$/g, "")); } catch { /* Retain the safe fallback or ordinary filename. */ }
  }
  candidate = candidate.split(/[\\/]/).at(-1)?.replace(/[\u0000-\u001f\u007f<>:"|?*]/g, "_").replace(/[. ]+$/g, "").slice(0, 180) || fallback;
  return /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(candidate) ? `export-${candidate}` : candidate;
}

export async function requestConsoleExport(request: ConsoleExportRequest): Promise<{ blob: Blob; filename: string; sha256: string | null }> {
  return requestAttachment("/v1/exports", {
    method: "POST",
    body: JSON.stringify(request),
  }, `storage-lab-${request.source}.${request.format}`);
}

export async function requestAttachment(path: string, options: RequestInit = {}, fallback = "storage-lab.json"): Promise<{ blob: Blob; filename: string; sha256: string | null }> {
  const checksumAPI = globalThis.crypto?.subtle;
  if (!checksumAPI) throw new Error("Không thể kiểm tra tính toàn vẹn tệp trong trình duyệt này. Hãy dùng HTTPS (hoặc localhost) và trình duyệt hỗ trợ Web Crypto.");
  const headers = new Headers(options.headers);
  headers.set("X-Console-Request", "1");
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...options, headers, cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw new ApiError(response.status, errorDetail(payload, response.statusText));
  }
  const disposition = response.headers.get("Content-Disposition");
  if (!/^attachment(?:;|$)/i.test(disposition || "")) throw new Error("Máy chủ không trả về tệp tải xuống hợp lệ (attachment).");
  const maximumBytes = 16 * 1024 * 1024;
  const length = Number(response.headers.get("Content-Length"));
  if (Number.isFinite(length) && length > maximumBytes) throw new Error("Tệp vượt giới hạn 16 MiB. Hãy thu hẹp phạm vi dữ liệu.");
  const sha256 = response.headers.get("X-Export-Sha256");
  if (!sha256 || !/^[a-f0-9]{64}$/i.test(sha256)) throw new Error("Tệp thiếu mã kiểm tra hợp lệ (checksum). Chưa tải tệp xuống.");
  if (!response.body) throw new Error("Máy chủ không trả nội dung tệp tải xuống.");
  const reader = response.body.getReader();
  const chunks: ArrayBuffer[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximumBytes) {
        await reader.cancel().catch(() => undefined);
        throw new Error("Tệp vượt giới hạn 16 MiB. Hãy thu hẹp phạm vi dữ liệu.");
      }
      // Own each bounded chunk instead of retaining an oversized transport buffer.
      chunks.push(value.slice().buffer);
    }
  } finally { reader.releaseLock(); }
  const blob = new Blob(chunks, { type: response.headers.get("Content-Type") || "application/octet-stream" });
  const bytes = await blob.arrayBuffer();
  const digest = Array.from(new Uint8Array(await checksumAPI.digest("SHA-256", bytes)), byte => byte.toString(16).padStart(2, "0")).join("");
  if (digest !== sha256.toLowerCase()) throw new Error("Kiểm tra tính toàn vẹn thất bại (integrity). Chưa tải tệp xuống.");
  return { blob, filename: exportFilename(disposition, fallback), sha256 };
}

export async function downloadConsoleExport(request: ConsoleExportRequest): Promise<string> {
  const { blob, filename } = await requestConsoleExport(request);
  return saveAttachment(blob, filename);
}

export async function downloadAttachment(path: string, options: RequestInit = {}, fallback?: string): Promise<string> {
  const { blob, filename } = await requestAttachment(path, options, fallback);
  return saveAttachment(blob, filename);
}

function saveAttachment(blob: Blob, filename: string): string {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = filename;
  document.body.appendChild(link);
  try { link.click(); } finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 10000); }
  return filename;
}

export const formatBytes = (value?: number | null) => {
  if (value === null || value === undefined || !Number.isFinite(value) || value < 0) return "—";
  if (value === 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};

export const uploadWithProgress = (
  file: File,
  fields: Record<string, string>,
  onProgress: (progress: number) => void,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<any> => new Promise((resolve, reject) => {
  const body = new FormData();
  body.append("file", file, file.name);
  Object.entries(fields).forEach(([key, value]) => body.append(key, value));
  const request = new XMLHttpRequest();
  request.open("POST", "/api/uploads/browser");
  request.setRequestHeader("X-Console-Request", "1");
  request.setRequestHeader("Idempotency-Key", idempotencyKey);
  request.upload.onprogress = event => event.lengthComputable && onProgress(Math.round(event.loaded / event.total * 100));
  request.onload = () => {
    const payload = JSON.parse(request.responseText || "{}");
    request.status >= 200 && request.status < 300
      ? resolve(payload)
      : reject(new ApiError(request.status, errorDetail(payload, request.statusText)));
  };
  request.onerror = () => reject(new Error("Không kết nối được máy chủ."));
  request.send(body);
});
