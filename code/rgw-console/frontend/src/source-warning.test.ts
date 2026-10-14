import assert from "node:assert/strict";
import test from "node:test";
import { sourceWarningLines } from "./source-warning.ts";
test("source warnings are concise, deduplicated and keep missing separate from zero", () => {
  const result = sourceWarningLines({ daemon: { key: "osd.1", type: "osd", id: "1", quality: "PARTIAL", fields: {}, limitations: [], metrics: [
    { metric_id: "osd.pg_count", value: 0, quality: "VALID" },
    { metric_id: "container.memory_usage", value: null, quality: "UNAVAILABLE" },
    { metric_id: "container.cpu_percentage", value: 1, quality: "STALE", reason: "SAMPLE_WINDOW_UNAVAILABLE" },
  ] }, limitations: ["chưa có host/process telemetry đầy đủ hoặc percentile độ trễ", "chưa có host/process telemetry đầy đủ hoặc percentile độ trễ"] });
  assert.ok(result.some(line => line.includes("RAM container")));
  assert.ok(result.some(line => line.includes("mẫu nguồn cũ")));
  assert.equal(result.filter(line => line.includes("telemetry host")).length, 1);
  assert.ok(!result.some(line => line.includes("Số PG")));
});
test("tool availability warning does not invent absent daemon types", () => {
  assert.deepEqual(sourceWarningLines({ environment: { tools: { osdmaptool: { version: null, quality: "PARTIAL" }, ceph: { version: "17", quality: "VALID" } } } }), ["Chưa có thông tin công cụ: osdmaptool."]);
  assert.deepEqual(sourceWarningLines({}), []);
  assert.deepEqual(sourceWarningLines({ environment: { tools: { ceph: null } } }), ["Chưa có thông tin công cụ: ceph."]);
});
