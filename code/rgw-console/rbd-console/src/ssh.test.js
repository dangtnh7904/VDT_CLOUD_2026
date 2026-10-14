import test, { afterEach, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  __resetForTests, __setClientFactoryForTests, connect, disconnect, exec, status,
} from "./ssh.js";

class FakeClient extends EventEmitter {
  constructor(mode = "idle") { super(); this.mode = mode; }
  connect(config) { this.config = config; queueMicrotask(() => this.emit("ready")); }
  end() { this.emit("close"); }
  exec(_command, callback) {
    const stream = new EventEmitter();
    stream.stderr = new EventEmitter();
    stream.destroy = () => {};
    callback(null, stream);
    if (this.mode === "output") queueMicrotask(() => stream.emit("data", Buffer.alloc(32)));
    if (this.mode === "binary") queueMicrotask(() => {
      stream.emit("data", Buffer.from([0, 255, 254]));
      stream.emit("data", Buffer.from([128, 65]));
      stream.emit("close", 0);
    });
  }
}

beforeEach(() => { process.env.RBD_SSH_HOST_KEY_REQUIRED = "false"; });
afterEach(() => {
  delete process.env.RBD_SSH_HOST_KEY_REQUIRED;
  delete process.env.RBD_SSH_HOST_KEY_SHA256;
  delete process.env.RBD_SSH_KNOWN_HOSTS_PATH;
});

test("binary OSDMap output preserves bytes across SSH chunks", async () => {
  __setClientFactoryForTests(() => new FakeClient("binary"));
  try {
    await connect();
    const result = await exec("ceph osd getmap -o /dev/stdout", { binary: true });
    assert.ok(Buffer.isBuffer(result.stdout));
    assert.deepEqual(result.stdout, Buffer.from([0, 255, 254, 128, 65]));
  } finally { disconnect(); __resetForTests(); }
});

test("SSH host key fingerprint is pinned and mismatches are rejected", async () => {
  const expectedKey = Buffer.from("test-host-public-key");
  const fingerprint = createHash("sha256").update(expectedKey).digest("base64").replace(/=+$/, "");
  process.env.RBD_SSH_HOST_KEY_REQUIRED = "true";
  process.env.RBD_SSH_HOST_KEY_SHA256 = `SHA256:${fingerprint}`;
  const client = new FakeClient();
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    assert.equal(client.config.hostVerifier(expectedKey), true);
    assert.equal(client.config.hostVerifier(Buffer.from("different-host-key")), false);
  } finally { disconnect(); __resetForTests(); }
});

test("SSH connection fails closed when host-key pinning is required but absent", async () => {
  process.env.RBD_SSH_HOST_KEY_REQUIRED = "true";
  delete process.env.RBD_SSH_HOST_KEY_SHA256;
  __setClientFactoryForTests(() => new FakeClient());
  try {
    await assert.rejects(() => connect(), error => error.code === "SSH_HOST_KEY_CONFIG_INVALID");
  } finally { disconnect(); __resetForTests(); }
});

test("SSH known-hosts pin accepts only the configured host key", async () => {
  const expectedKey = Buffer.from("known-host-public-key");
  const root = mkdtempSync(join(tmpdir(), "storage-lab-known-hosts-"));
  const knownHosts = join(root, "known_hosts");
  writeFileSync(knownHosts, `ceph-admin ssh-ed25519 ${expectedKey.toString("base64")}\n`, { mode: 0o600 });
  process.env.RBD_HOST = "ceph-admin";
  process.env.RBD_SSH_HOST_KEY_REQUIRED = "true";
  process.env.RBD_SSH_KNOWN_HOSTS_PATH = knownHosts;
  const client = new FakeClient();
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    assert.equal(client.config.hostVerifier(expectedKey), true);
    assert.equal(client.config.hostVerifier(Buffer.from("unexpected-key")), false);
  } finally {
    disconnect();
    __resetForTests();
    delete process.env.RBD_HOST;
    rmSync(root, { recursive: true, force: true });
  }
});

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

test("SSH channel opening itself has a bounded deadline", async () => {
  const client = new FakeClient(); client.exec = () => {};
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    await assert.rejects(exec("ceph fsid", { timeout: 10 }), error => error.code === "EXECUTOR_TIMEOUT");
  } finally { disconnect(); __resetForTests(); }
});

test("synchronous SSH open failure releases admission and clears deadline", async () => {
  const client = new FakeClient(); client.exec = () => { throw new Error("private-host-secret"); };
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    for (let attempt = 0; attempt < 8; attempt++) {
      await assert.rejects(exec("ceph fsid"), error => error.code === "EXECUTOR_UNAVAILABLE" && !error.message.includes("secret"));
    }
  } finally { disconnect(); __resetForTests(); }
});

test("late-opened stream after deadline is destroyed without executing output", async () => {
  let destroyed = 0;
  const client = new FakeClient();
  client.exec = (_command, callback) => setTimeout(() => {
    const stream = new EventEmitter(); stream.stderr = new EventEmitter(); stream.destroy = () => { destroyed += 1; };
    callback(null, stream);
  }, 20);
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    await assert.rejects(exec("ceph fsid", { timeout: 5 }), error => error.code === "EXECUTOR_TIMEOUT");
    await new Promise(resolve => setTimeout(resolve, 30)); assert.equal(destroyed, 1);
  } finally { disconnect(); __resetForTests(); }
});

test("rejected SSH open has a stable code without leaking the description", async () => {
  const client = new FakeClient();
  client.exec = (_command, callback) => callback(Object.assign(new Error("private-host-secret"), { reason: 4 }));
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    await assert.rejects(exec("ceph fsid"), error => error.code === "SSH_CHANNEL_OPEN_FAILED" && !error.message.includes("secret"));
  } finally { disconnect(); __resetForTests(); }
});

test("command stream closed without exit status cannot be marked successful", async () => {
  const client = new FakeClient();
  client.exec = (_command, callback) => {
    const stream = new EventEmitter(); stream.stderr = new EventEmitter(); stream.destroy = () => {};
    callback(null, stream); queueMicrotask(() => stream.emit("close"));
  };
  __setClientFactoryForTests(() => client);
  try {
    await connect();
    await assert.rejects(exec("ceph fsid"), error => error.code === "SSH_EXIT_STATUS_UNAVAILABLE");
  } finally { disconnect(); __resetForTests(); }
});

test("all SSH commands share four slots even across independent callers", async () => {
  let active = 0; let peak = 0;
  const client = new FakeClient();
  client.exec = (_command, callback) => {
    active += 1; peak = Math.max(peak, active);
    const stream = new EventEmitter(); stream.stderr = new EventEmitter(); stream.destroy = () => {};
    callback(null, stream);
    setTimeout(() => { active -= 1; stream.emit("close", 0); }, 5);
  };
  __setClientFactoryForTests(() => client);
  try {
    await connect(); await Promise.all(Array.from({ length: 12 }, () => exec("ceph fsid", { timeout: 1000 })));
    assert.equal(peak, 4); assert.equal(active, 0);
  } finally { disconnect(); __resetForTests(); }
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
