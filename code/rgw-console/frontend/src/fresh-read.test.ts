import assert from "node:assert/strict";
import test from "node:test";
import { retryFreshRead } from "./fresh-read.ts";

test("busy requests retry a new source read and return only its fresh result", async () => {
  let reads = 0; const waiting: number[] = [];
  const result = await retryFreshRead(async () => {
    if (++reads < 3) throw Object.assign(new Error("Busy"), { code: "COLLECTION_BUSY" });
    return { fsid: "verified", observed_at: "new" };
  }, new AbortController().signal, attempt => waiting.push(attempt), [0, 0]);
  assert.equal(reads, 3);
  assert.deepEqual(waiting, [1, 2]);
  assert.equal(result.observed_at, "new");
});

test("busy retries are bounded and other collector errors are never retried", async () => {
  let reads = 0;
  const busy = Object.assign(new Error("Busy"), { code: "COLLECTION_BUSY" });
  await assert.rejects(retryFreshRead(async () => { reads++; throw busy; }, new AbortController().signal, () => {}, [0, 0]), error => error === busy);
  assert.equal(reads, 3);
  reads = 0;
  const failed = Object.assign(new Error("FSID mismatch"), { code: "FSID_MISMATCH" });
  await assert.rejects(retryFreshRead(async () => { reads++; throw failed; }, new AbortController().signal, () => {}, [0, 0]), error => error === failed);
  assert.equal(reads, 1);
});

test("leaving a view while waiting cancels retries and does not start another read", async () => {
  let reads = 0; const controller = new AbortController();
  const request = retryFreshRead(async () => { reads++; throw Object.assign(new Error("Busy"), { code: "COLLECTION_BUSY" }); }, controller.signal, () => setTimeout(() => controller.abort(), 0), [1000]);
  await assert.rejects(request, { name: "AbortError" });
  assert.equal(reads, 1);
});

test("a cancelled view never starts its initial read", async () => {
  let reads = 0; const controller = new AbortController(); controller.abort();
  await assert.rejects(retryFreshRead(async () => ++reads, controller.signal, () => {}), { name: "AbortError" });
  assert.equal(reads, 0);
});
