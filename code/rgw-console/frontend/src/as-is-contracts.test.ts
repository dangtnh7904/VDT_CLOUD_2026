import assert from "node:assert/strict";
import test from "node:test";
import { pageRows, toggleKeys, showValue, validateWeights, collectionPairError, comparisonKeys, collectionQuery, reconcileWeightInputs, mappingValidationMessage, scopedDaemonKeys, scopedDaemons, daemonScopeError, savedCollectionQuery, comparisonWarningDaemons, type Daemon } from "./as-is-contracts.ts";
test("pagination is ten daemon rows and selection persists across pages", () => {
  const rows = Array.from({ length: 25 }, (_, i) => `osd.${i}`);
  assert.equal(pageRows(rows, 1).length, 10);
  assert.equal(pageRows(rows, 3).length, 5);
  assert.equal(toggleKeys(pageRows(rows, 1), pageRows(rows, 2), true).length, 20);
  assert.equal(showValue(0), "0"); assert.notEqual(showValue(null), "0");
});

test("refreshing the OSD catalogue retains explicit weight edits but refreshes untouched defaults and removes hidden OSDs", () => {
  assert.deepEqual(reconcileWeightInputs({ "osd.1": "0", "osd.2": "1", "osd.3": "5" }, { "osd.1": "1", "osd.2": "1", "osd.3": "5" }, { "osd.1": "2", "osd.2": "3", "osd.4": "4" }), { "osd.1": "0", "osd.2": "3", "osd.4": "4" });
});

test("mapping validation never presents undersized or legacy predictions as complete safety evidence", () => {
  assert.match(mappingValidationMessage("PARTIAL"), /không phải kết quả đầy đủ/);
  assert.match(mappingValidationMessage("VALID"), /không đồng nghĩa đã kiểm chứng failure domain/);
  assert.match(mappingValidationMessage(), /chưa có bằng chứng/);
});
test("comparison supports arbitrary phases and union coverage with matching type and FSID", () => {
  const a = { id: "a", fsid: "cluster", phase: "AFTER" as const, started_at: "", completed_at: "", quality: "VALID", daemon_keys: ["osd.0", "mgr.one"], daemon_types: ["osd", "mgr"] as ("osd" | "mgr")[], sha256: "" };
  const b = { ...a, id: "b", daemon_keys: ["osd.1"], phase: "DURING" as const };
  assert.equal(collectionPairError(a, b, "osd"), null);
  assert.deepEqual(comparisonKeys(a, b, "osd"), ["osd.0", "osd.1"]);
  assert.ok(collectionPairError(a, { ...b, fsid: "other" }, "osd"));
  assert.ok(collectionPairError(a, { ...b, deleted_at: "today" }, "osd"));
});
test("weight scenarios reject nonfinite, duplicate and out-of-range values", () => {
  assert.equal(validateWeights([{ osd_id: 0, crush_weight: 0 }]), null);
  assert.ok(validateWeights([{ osd_id: 0, crush_weight: NaN }]));
  assert.ok(validateWeights([{ osd_id: 0, crush_weight: 1 }, { osd_id: 0, crush_weight: 2 }]));
});
test("history query sends all filters and opaque cursor to the server with ten-row default", () => {
  const query = new URLSearchParams(collectionQuery({ type: "osd", from: "2026-10-12", to: "2026-10-13", phase: "DURING", deleted: true, search: " osd.5 % _ ", quality: "PARTIAL", daemonKey: "osd.5", cursor: "opaque-_-cursor" }));
  assert.equal(query.get("limit"), "10");
  assert.equal(query.get("daemon_type"), "osd");
  assert.equal(query.get("q"), "osd.5 % _");
  assert.equal(query.get("quality"), "PARTIAL");
  assert.equal(query.get("daemon_key"), "osd.5");
  assert.equal(query.get("include_deleted"), "true");
  assert.equal(query.get("cursor"), "opaque-_-cursor");
  assert.equal(query.get("from_date"), "2026-10-12");
  assert.equal(query.get("to_date"), "2026-10-13");
  assert.equal(query.get("phase"), "DURING");
});

test("a mixed collection projects only the chosen daemon type without changing its original keys or SHA", () => {
  const collection = { id: "mixed", daemon_keys: ["mon.ceph-master", "osd.2", "osd.5"], sha256: "original-sha" };
  Object.freeze(collection.daemon_keys); Object.freeze(collection);
  assert.deepEqual(scopedDaemonKeys(collection, "osd"), ["osd.2", "osd.5"]);
  assert.deepEqual(scopedDaemonKeys(collection, "mon"), ["mon.ceph-master"]);
  assert.deepEqual(scopedDaemonKeys(collection, "osd", " osd.5 "), ["osd.5"]);
  assert.deepEqual(scopedDaemonKeys(collection, "mgr"), []);
  assert.deepEqual(scopedDaemonKeys(collection), ["mon.ceph-master", "osd.2", "osd.5"]);
  assert.equal(collection.sha256, "original-sha");
  assert.equal(collection.daemon_keys.length, 3);
});

test("saved detail projection uses exact daemon key and preserves saved objects and missing scope", () => {
  const daemon = (key: string, type: Daemon["type"]): Daemon => ({ key, type, id: key.split(".").slice(1).join("."), quality: "VALID", fields: {}, metrics: [], limitations: [] });
  const observation = { daemons: [daemon("mon.one", "mon"), daemon("osd.2", "osd"), daemon("osd.5", "osd")] };
  Object.freeze(observation.daemons); Object.freeze(observation);
  const result = scopedDaemons(observation, "osd", "osd.5");
  assert.deepEqual(result.map(value => value.key), ["osd.5"]);
  assert.equal(result[0], observation.daemons[2]);
  assert.deepEqual(scopedDaemons(observation, "mon", "osd.5"), []);
  assert.deepEqual(scopedDaemons(observation, "mds"), []);
  assert.equal(observation.daemons.length, 3);
});

test("saved export filters are explicit and original export has no projection scope", () => {
  const scoped = new URLSearchParams(savedCollectionQuery(true, "osd", " osd.5 "));
  assert.equal(scoped.get("daemon_type"), "osd");
  assert.equal(scoped.get("daemon_key"), "osd.5");
  assert.equal(scoped.get("include_deleted"), "true");
  const original = new URLSearchParams(savedCollectionQuery(false));
  assert.equal(original.has("daemon_type"), false);
  assert.equal(original.has("daemon_key"), false);
  assert.equal(original.get("include_deleted"), "false");
});

test("daemon filter rejects incomplete or cross-type keys before querying the API", () => {
  assert.equal(daemonScopeError("", "osd"), null);
  assert.equal(daemonScopeError(" osd.2 ", "osd"), null);
  assert.equal(daemonScopeError("rgw.lab.ceph-master.abc123", "rgw"), null);
  assert.ok(daemonScopeError("osd.", "osd"));
  assert.ok(daemonScopeError("osd.2", "mon"));
  assert.ok(daemonScopeError("osd.2?include_deleted=true", "osd"));
});

test("comparison warnings gather missing or stale samples from both saved sides safely", () => {
  const a: Daemon = { key: "osd.2", id: "2", type: "osd", quality: "PARTIAL", fields: {}, limitations: [], metrics: [{ metric_id: "container.memory_usage", value: null, quality: "UNAVAILABLE" }] };
  const b = { ...a, metrics: [{ metric_id: "container.cpu_percentage", value: 1, quality: "STALE" }, null, "invalid"] };
  const rows = [{ a, b }, { a: null, b: {} }, { a: { ...a, metrics: "not an array" }, b: false }];
  const original = JSON.stringify(rows);
  const warnings = comparisonWarningDaemons(rows);
  assert.equal(warnings.length, 2);
  assert.deepEqual(warnings.flatMap(daemon => daemon.metrics.map(metric => metric.quality)), ["UNAVAILABLE", "STALE"]);
  assert.equal(JSON.stringify(rows), original);
  assert.notEqual(warnings[0], a);
});
