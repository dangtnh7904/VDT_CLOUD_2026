import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import {
  __resetForTests, __setClientFactoryForTests, connect, disconnect, exec, status,
} from "./ssh.js";

class FakeClient extends EventEmitter {
  constructor(mode = "idle") { super(); this.mode = mode; }
  connect() { queueMicrotask(() => this.emit("ready")); }
  end() { this.emit("close"); }
  exec(_command, callback) {
    const stream = new EventEmitter();
    stream.stderr = new EventEmitter();
    stream.destroy = () => {};
    callback(null, stream);
    if (this.mode === "output") queueMicrotask(() => stream.emit("data", Buffer.alloc(32)));
  }
}

test("SSH command output cap is enforced", async () => {
  process.env.RBD_MAX_OUTPUT_BYTES = "8";
  __setClientFactoryForTests(() => new FakeClient("output"));
  try {
    await connect();
    await assert.rejects(() => exec("ceph fsid"), error => error.code === "COMMAND_OUTPUT_LIMIT");
  } finally { disconnect(); __resetForTests(); delete process.env.RBD_MAX_OUTPUT_BYTES; }
});

test("SSH command timeout has a stable error code", async () => {
  process.env.RBD_COMMAND_TIMEOUT_MS = "5";
  __setClientFactoryForTests(() => new FakeClient("idle"));
  try {
    await connect();
    await assert.rejects(() => exec("ceph fsid"), error => error.code === "EXECUTOR_TIMEOUT");
  } finally { disconnect(); __resetForTests(); delete process.env.RBD_COMMAND_TIMEOUT_MS; }
});

test("initial SSH failure schedules and completes reconnect", async () => {
  let attempts = 0;
  __setClientFactoryForTests(() => {
    const client = new FakeClient();
    client.connect = () => queueMicrotask(() => {
      attempts += 1;
      if (attempts === 1) client.emit("error", new Error("first connection failed"));
      else client.emit("ready");
    });
    return client;
  }, 5);
  try {
    await assert.rejects(() => connect(), /first connection failed/);
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(attempts, 2);
    assert.equal(status().connected, true);
  } finally { disconnect(); __resetForTests(); }
});
