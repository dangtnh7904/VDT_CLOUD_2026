import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPACITY_GUIDANCE,
  CRUD_DEFAULT_OPERATION_WEIGHTS,
  CRUD_OPERATIONS,
  canResumeStreamJob,
  capacityScopeLabel,
  capacityStateLabel,
  telemetryStatusLabel,
  comparisonTone,
  isRbdDeleteConfirmed,
  isRbdFileAccessState,
  operationCountLabel,
  inventoryValue,
  parseOsdIdInput,
  qualityTone,
  rbdPreviewKind,
  resolveTelemetryStatus,
  parseRuntimeConfig,
  visibleConsoleViews,
  type TelemetryStatus,
} from "./ui-contracts.ts";

test("capacity banner preserves every backend telemetry state", () => {
  const statuses: TelemetryStatus[] = [
    "NOT_CONFIGURED",
    "NO_SNAPSHOT",
    "FRESH",
    "STALE",
    "EXECUTOR_UNAVAILABLE",
    "COLLECTOR_ERROR",
  ];
  for (const status of statuses) {
    assert.equal(resolveTelemetryStatus(false, status, false), status);
  }
  assert.equal(resolveTelemetryStatus(true, "FRESH", true), "EXECUTOR_UNAVAILABLE");
  assert.equal(resolveTelemetryStatus(false, undefined, true), "FRESH");
  assert.equal(resolveTelemetryStatus(false, undefined, false), "NO_SNAPSHOT");
  assert.equal(CAPACITY_GUIDANCE.FRESH, undefined);
  assert.match(CAPACITY_GUIDANCE.NO_SNAPSHOT || "", /snapshot/i);
  assert.equal(capacityScopeLabel([0, 1, 3], ["rbd-lab"]), "3 OSD · rbd-lab");
  assert.equal(capacityScopeLabel([], []), "Chưa có phạm vi OSD");
  assert.equal(capacityStateLabel("PAUSED_CAPACITY"), "Chạm ngưỡng dung lượng");
  assert.equal(telemetryStatusLabel("FRESH"), "Dữ liệu mới");
});

test("RGW CRUD operation mix covers and reports all backend operations", () => {
  assert.deepEqual(CRUD_OPERATIONS, ["PUT", "GET", "HEAD", "LIST", "UPDATE", "DELETE"]);
  assert.equal(Object.values(CRUD_DEFAULT_OPERATION_WEIGHTS).reduce((sum, value) => sum + value, 0), 100);
  assert.equal(
    operationCountLabel({ PUT: 2, GET: 1, DELETE: 3 }),
    "PUT 2 · GET 1 · HEAD 0 · LIST 0 · UPDATE 0 · DELETE 3",
  );
  assert.equal(canResumeStreamJob("paused", "OPERATOR_PAUSE"), true);
  assert.equal(canResumeStreamJob("paused", null), true);
  assert.equal(canResumeStreamJob("running", "OPERATOR_PAUSE"), false);
  assert.equal(canResumeStreamJob("paused", "LEASE_EXPIRED_RECONCILE_REQUIRED"), false);
  assert.equal(canResumeStreamJob("paused", "RECONCILE_REQUIRED_AFTER_AMBIGUOUS_MUTATION"), false);
});

test("RBD destructive confirmation requires the exact displayed name", () => {
  assert.equal(isRbdDeleteConfirmed("lab-pr7-volume", "lab-pr7-volume"), true);
  assert.equal(isRbdDeleteConfirmed("lab-pr7-volume", "lab-pr7-volum"), false);
  assert.equal(isRbdDeleteConfirmed("lab-pr7-volume", " lab-pr7-volume"), false);
  assert.equal(isRbdDeleteConfirmed("lab-pr7-volume", "LAB-PR7-VOLUME"), false);
});

test("RBD file access and preview contracts stay fail-closed", () => {
  assert.equal(isRbdFileAccessState("READY"), true);
  assert.equal(isRbdFileAccessState("MOUNTED"), true);
  assert.equal(isRbdFileAccessState("UNMOUNTED"), false);
  assert.equal(rbdPreviewKind("text/plain; charset=utf-8"), "text");
  assert.equal(rbdPreviewKind("application/json"), "text");
  assert.equal(rbdPreviewKind("image/png"), "image");
  assert.equal(rbdPreviewKind("application/pdf"), "pdf");
  assert.equal(rbdPreviewKind("application/octet-stream"), null);
});

test("OSD inventory keeps unknown distinct from numeric zero", () => {
  assert.equal(inventoryValue(null), "UNKNOWN");
  assert.equal(inventoryValue(undefined), "UNKNOWN");
  assert.equal(inventoryValue(0), "0");
  assert.equal(inventoryValue(NaN), "UNKNOWN");
  assert.equal(qualityTone("VALID"), "valid");
  assert.equal(qualityTone("PARTIAL"), "partial");
  assert.equal(qualityTone(null), "inconclusive");
  assert.equal(comparisonTone("COMPARABLE"), "valid");
  assert.equal(comparisonTone("INCONCLUSIVE"), "partial");
  assert.equal(comparisonTone("NOT_COMPARABLE"), "inconclusive");
  assert.deepEqual(parseOsdIdInput(""), { ids: null, error: null });
  assert.deepEqual(parseOsdIdInput("0, 4"), { ids: [0, 4], error: null });
  assert.match(parseOsdIdInput("0, x").error || "", /số nguyên/);
  assert.match(parseOsdIdInput("4,4").error || "", /lặp lại/);
});


test("production navigation contains only current observation and comparison flows", () => {
  const config = parseRuntimeConfig({ console_read_only: true, application_version: "3.0.0", features: { upgrade: true, lab: true, legacy_rgw: true, legacy_rbd: true } });
  assert.deepEqual(visibleConsoleViews(config), ["overview", "metrics", "inventory", "comparison"]);
  assert.equal(visibleConsoleViews(config).some(view => ["upload", "random", "stream", "objects", "volumes"].includes(view)), false);
  assert.deepEqual(visibleConsoleViews({ ...config, features: { ...config.features, upgrade: false } }), ["overview", "metrics"]);
  assert.deepEqual(visibleConsoleViews({ ...config, console_read_only: false }), ["overview", "metrics", "inventory", "comparison", "dashboard", "performance", "upload", "random", "stream", "objects", "volumes"]);
});

test("missing or malformed runtime configuration cannot unlock lab navigation", () => {
  for (const input of [null, {}, { console_read_only: "false" }, { console_read_only: true, application_version: "3.0.0", features: { upgrade: true } }]) {
    assert.throws(() => parseRuntimeConfig(input), /cấu hình/i);
  }
});
