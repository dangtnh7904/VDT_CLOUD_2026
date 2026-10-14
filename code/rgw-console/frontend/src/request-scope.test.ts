import assert from "node:assert/strict";
import test from "node:test";
import { createRequestScope } from "./request-scope.ts";

test("filter invalidation releases the UI lock without allowing an old request to finish a newer one", () => {
  const scope = createRequestScope();
  const old = scope.begin()!;
  assert.equal(scope.begin(), undefined, "double clicks must not start a second action");
  scope.invalidate();
  const fresh = scope.begin()!;
  assert.equal(scope.current(old), false);
  assert.equal(scope.finish(old), false);
  assert.equal(scope.current(fresh), true);
  assert.equal(scope.finish(fresh), true);
});

test("superseded history loads and responses after unmount cannot commit", () => {
  const scope = createRequestScope();
  const pageA = scope.begin(true)!;
  const pageB = scope.begin(true)!;
  assert.equal(scope.current(pageA), false);
  assert.equal(scope.finish(pageA), false);
  assert.equal(scope.current(pageB), true);
  scope.invalidate();
  assert.equal(scope.current(pageB), false);
  assert.equal(scope.finish(pageB), false);
});
