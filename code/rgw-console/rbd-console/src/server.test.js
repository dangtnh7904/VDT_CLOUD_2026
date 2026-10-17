import test from "node:test";
import assert from "node:assert/strict";
import { connect as connectTcp } from "net";
import { SshExecutor } from "./executor.js";
import { createExecutorServer } from "./server.js";

const TOKEN = "executor-test-token-32-characters-long";
const REQUEST_ID = "22222222-2222-4222-8222-222222222222";

test("authenticated HTTP and WebSocket entrypoints cannot bypass the read-only profile", async () => {
  process.env.APP_ENV = "production";
  process.env.CONSOLE_READ_ONLY = "true";
  process.env.UPGRADE_MUTATIONS_ENABLED = "false";
  process.env.RBD_TERMINAL_ENABLED = "false";
  process.env.CEPH_EXECUTOR_TOKEN = TOKEN;
  delete process.env.RBD_EXECUTOR_TOKEN;
  let accesses = 0;
  const forbidden = () => { accesses += 1; throw new Error("Forbidden side effect"); };
  const executor = new SshExecutor({
    transport: { exec: forbidden, openSftp: forbidden, openShell: forbidden },
    store: { load: forbidden, save: forbidden, withLock: forbidden },
    tickets: { issue: forbidden, consume: forbidden },
  });
  const { server } = createExecutorServer({ executor, getSshStatus: () => ({ connected: true }), terminalHandler: forbidden });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  const origin = `http://127.0.0.1:${port}`;
  const headers = { "X-Executor-Token": TOKEN };
  try {
    for (const method of ["GET", "PUT"]) {
      // A valid token and malformed context must still reach the policy guard
      // before any file parsing, volume lock, SSH or streaming begins.
      const response = await fetch(`${origin}/internal/v1/files/content`, { method, headers });
      assert.equal(response.status, 403);
      assert.equal((await response.json()).code, "CONSOLE_READ_ONLY");
    }
    const mutation = await fetch(`${origin}/internal/v1/execute`, {
      method: "POST", headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ version: 1, request_id: REQUEST_ID, action: "rbd.image.create", params: {} }),
    });
    assert.equal(mutation.status, 403);
    const envelope = await mutation.json();
    assert.equal(envelope.request_id, REQUEST_ID);
    assert.equal(envelope.error.code, "CONSOLE_READ_ONLY");
    const unauthenticated = await fetch(`${origin}/internal/v1/files/content`);
    assert.equal(unauthenticated.status, 401);
    assert.equal((await unauthenticated.json()).code, "EXECUTOR_AUTH_FAILED");
    const websocketResponse = await new Promise((resolve, reject) => {
      const socket = connectTcp(port, "127.0.0.1");
      let data = "";
      socket.setTimeout(2000, () => socket.destroy(new Error("WebSocket rejection timed out")));
      socket.on("error", reject);
      socket.on("data", chunk => { data += chunk; });
      socket.on("close", () => resolve(data));
      socket.on("connect", () => socket.write([
        `GET /ws/terminal?ticket=${"A".repeat(43)} HTTP/1.1`,
        `Host: 127.0.0.1:${port}`, "Connection: Upgrade", "Upgrade: websocket",
        "Sec-WebSocket-Version: 13", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
        `X-Executor-Token: ${TOKEN}`, "", "",
      ].join("\r\n")));
    });
    assert.match(websocketResponse, /^HTTP\/1\.1 403 Forbidden/);
    assert.equal(accesses, 0);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
