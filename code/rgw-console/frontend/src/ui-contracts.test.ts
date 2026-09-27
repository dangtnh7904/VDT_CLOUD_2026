import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPACITY_GUIDANCE,
  CRUD_DEFAULT_OPERATION_WEIGHTS,
  CRUD_OPERATIONS,
  canResumeStreamJob,
  capacityScopeLabel,
  isRbdDeleteConfirmed,
  isRbdFileAccessState,
  operationCountLabel,
  rbdPreviewKind,
  resolveTelemetryStatus,
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
  assert.equal(capacityScopeLabel([], []), "No OSD scope");
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
