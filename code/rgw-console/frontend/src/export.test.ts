import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { exportFilename, requestAttachment, requestConsoleExport } from "./api.ts";

test("export filenames cannot escape the download directory or use Windows device names", () => {
  assert.equal(exportFilename('attachment; filename="../../report.csv"', "safe.csv"), "report.csv");
  assert.equal(exportFilename("attachment; filename*=UTF-8''CON.csv", "safe.csv"), "export-CON.csv");
  assert.equal(exportFilename("attachment; filename*=UTF-8''bad%00name.json", "safe.json"), "bad_name.json");
});

test("download verifies response bytes and checksum before returning a blob", async (t) => {
  const body = '{"value":null,"zero":0}';
  const sha = createHash("sha256").update(body).digest("hex");
  const fetch = t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options?.method, "POST");
    assert.equal(new Headers(options?.headers).get("X-Console-Request"), "1");
    return new Response(body, { headers: { "Content-Disposition": 'attachment; filename="report.json"', "X-Export-Sha256": sha } });
  });
  const request = { source: "performance" as const, format: "json" as const };
  const result = await requestConsoleExport(request);
  assert.equal(result.filename, "report.json");
  assert.equal(await result.blob.text(), body);
  fetch.mock.mockImplementation(async () => new Response(body, { headers: { "Content-Disposition": "attachment", "X-Export-Sha256": "0".repeat(64) } }));
  await assert.rejects(requestConsoleExport(request), /integrity/);
  fetch.mock.mockImplementation(async () => new Response(body, { headers: { "Content-Disposition": "attachment" } }));
  await assert.rejects(requestConsoleExport(request), /checksum/);
});

test("download rejects non-attachments, oversized exports and structured API errors", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response("<html>login</html>"));
  const request = { source: "performance" as const, format: "json" as const };
  await assert.rejects(requestConsoleExport(request), /attachment/);
  fetch.mock.mockImplementation(async () => new Response("", { headers: { "Content-Disposition": "attachment", "Content-Length": String(17 * 1024 * 1024) } }));
  await assert.rejects(requestConsoleExport(request), /16 MiB/);
  fetch.mock.mockImplementation(async () => new Response(JSON.stringify({ detail: { code: "EXPORT_SCOPE_REJECTED", message: "Outside profile" } }), { status: 403 }));
  await assert.rejects(requestConsoleExport(request), /Outside profile/);
});

test("chunked exports without Content-Length are stopped at 16 MiB before retaining the excess chunk", async (t) => {
  let reads = 0; let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) { reads++; controller.enqueue(new Uint8Array(9 * 1024 * 1024)); },
    cancel() { cancelled = true; },
  }, { highWaterMark: 0 });
  t.mock.method(globalThis, "fetch", async () => new Response(stream, { headers: { "Content-Disposition": "attachment", "X-Export-Sha256": "0".repeat(64) } }));
  await assert.rejects(requestAttachment("/v1/as-is/export"), /16 MiB/);
  assert.equal(reads, 2);
  assert.equal(cancelled, true);
});

test("exports fail closed when a remote HTTP context cannot verify the checksum", async (t) => {
  t.mock.getter(globalThis, "crypto", () => undefined as unknown as Crypto);
  const request = t.mock.method(globalThis, "fetch", async () => new Response("not verified"));
  await assert.rejects(requestAttachment("/v1/as-is/export"), /HTTPS/);
  assert.equal(request.mock.callCount(), 0);
});
