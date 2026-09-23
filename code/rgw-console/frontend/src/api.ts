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

export const formatBytes = (value?: number | null) => {
  if (value === null || value === undefined) return "—";
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
  request.setRequestHeader("Idempotency-Key", idempotencyKey);
  request.upload.onprogress = event => event.lengthComputable && onProgress(Math.round(event.loaded / event.total * 100));
  request.onload = () => {
    const payload = JSON.parse(request.responseText || "{}");
    request.status >= 200 && request.status < 300
      ? resolve(payload)
      : reject(new ApiError(request.status, errorDetail(payload, request.statusText)));
  };
  request.onerror = () => reject(new Error("Network error"));
  request.send(body);
});
