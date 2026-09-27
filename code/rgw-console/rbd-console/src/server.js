/**
 * RBD Test Console — Express server.
 *
 * Connects to a Linux Ceph host via SSH and exposes REST API
 * for RBD image management and cluster health.
 */

import "dotenv/config";
import express from "express";
import { timingSafeEqual } from "crypto";
import { createServer } from "http";
import { WebSocketServer } from "ws";
import { connect, disconnect, status as sshStatus } from "./ssh.js";
import { ExecutorError, publicError } from "./errors.js";
import { SshExecutor, validateRequest } from "./executor.js";
import { attachTerminal } from "./terminal.js";

const app = express();
const PORT = parseInt(process.env.PORT || "3001", 10);
const server = createServer(app);
const terminals = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });

// --- Middleware ---

app.use(express.json({ limit: "1mb" }));
const executor = new SshExecutor();

// Request ID
app.use((req, _res, next) => {
  req.requestId = `rbd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  next();
});

// --- Routes ---

app.get("/healthz", (_req, res) => {
  const ssh = sshStatus();
  res.status(ssh.connected ? 200 : 503).json({ status: ssh.connected ? "ok" : "disconnected" });
});

function authenticate(req, _res, next) {
  const configured = process.env.RBD_EXECUTOR_TOKEN || "";
  const supplied = String(req.get("X-Executor-Token") || "");
  const valid = configured.length >= 32 && supplied.length === configured.length
    && timingSafeEqual(Buffer.from(supplied), Buffer.from(configured));
  if (!valid) return next(new ExecutorError("EXECUTOR_AUTH_FAILED", "Executor authentication failed", { status: 401 }));
  next();
}

function decodeFileContext(req) {
  const encoded = String(req.get("X-RBD-Context") || "");
  if (!encoded || encoded.length > 8192 || !/^[A-Za-z0-9_-]+$/.test(encoded)) {
    throw new ExecutorError("INVALID_REQUEST", "RBD file context header is missing or invalid");
  }
  try {
    const value = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid context");
    return value;
  } catch {
    throw new ExecutorError("INVALID_REQUEST", "RBD file context header is not valid JSON");
  }
}

app.get("/internal/v1/files/content", authenticate, async (req, res, next) => {
  try {
    const context = decodeFileContext(req);
    await executor.downloadFile(context, res, async metadata => {
      res.status(200);
      res.set({
        "Content-Type": "application/octet-stream",
        "Content-Length": String(metadata.size),
        "X-RBD-File-Path": Buffer.from(metadata.path).toString("base64url"),
        "X-RBD-File-Mime": metadata.mime_type || "application/octet-stream",
        "X-Content-Type-Options": "nosniff",
      });
      res.flushHeaders();
    });
  } catch (error) {
    if (res.headersSent) return res.destroy(error);
    next(error);
  }
});

app.put("/internal/v1/files/content", authenticate, async (req, res, next) => {
  try {
    const context = decodeFileContext(req);
    const expectedBytes = Number(req.get("Content-Length"));
    if (!Number.isSafeInteger(expectedBytes) || expectedBytes < 0) throw new ExecutorError("INVALID_LENGTH", "Content-Length is required for file uploads", { status: 411 });
    const result = await executor.uploadFile(context, req, expectedBytes);
    res.json({ version: 1, ok: true, result });
  } catch (error) {
    next(error);
  }
});

app.post("/internal/v1/execute", authenticate, async (req, res, next) => {
  let requestId = null;
  try {
    const request = validateRequest(req.body);
    requestId = request.request_id;
    req.executorRequestId = requestId;
    const result = await executor.dispatch(request.action, request.params);
    res.json({ version: 1, request_id: requestId, ok: true, result });
  } catch (error) {
    if (error instanceof ExecutorError) {
      return res.status(error.status || 400).json({ version: 1, request_id: requestId, ok: false, error: publicError(error) });
    }
    next(error);
  }
});

// --- Error handler ---

app.use((err, req, res, _next) => {
  const status = err.status || 500;
  const visible = publicError(err);
  const message = visible.message;
  console.error(`[${req.requestId}] ${req.method} ${req.path} → ${status}: ${message}`);
  if (req.path === "/internal/v1/execute") {
    return res.status(status).json({
      version: 1,
      request_id: req.executorRequestId || null,
      ok: false,
      error: visible,
    });
  }
  res.status(status).json({
    error: message,
    code: visible.code,
    retryable: visible.retryable,
    request_id: req.requestId,
  });
});

// 404
app.use((_req, res) => {
  res.status(404).json({ error: "Not found", code: "NOT_FOUND" });
});

// --- Startup ---

async function start() {
  console.log("╔══════════════════════════════════════════╗");
  console.log("║       RBD Test Console (SSH mode)        ║");
  console.log("╚══════════════════════════════════════════╝");
  console.log();

  const host = process.env.RBD_HOST;
  if (!host) {
    console.error("[startup] RBD_HOST is required. Set it in .env");
    process.exit(1);
  }

  console.log(`[startup] SSH target: ${process.env.RBD_SSH_USER || "root"}@${host}:${process.env.RBD_SSH_PORT || 22}`);
  console.log(`[startup] Pool: ${process.env.RBD_POOL || "(not set)"}`);
  console.log(`[startup] Mount root: ${process.env.RBD_MOUNT_ROOT || "(not set)"}`);
  console.log(`[startup] Image prefix: ${process.env.RBD_IMAGE_PREFIX || "(none)"}`);
  console.log(`[startup] Expected FSID: ${process.env.CEPH_EXPECTED_FSID || "(not set)"}`);
  console.log();

  // Connect SSH (non-blocking — service starts even if SSH is down)
  try {
    await connect();
    console.log("[startup] SSH connected successfully");
  } catch (err) {
    console.warn(`[startup] SSH connection failed: ${err.message}`);
    console.warn("[startup] Service will start anyway; SSH will auto-reconnect");
  }

  server.listen(PORT, () => {
    console.log();
    console.log(`[startup] Listening on http://localhost:${PORT}`);
    console.log(`[startup] Health: http://localhost:${PORT}/healthz`);
    console.log("[startup] Executor API is internal-only: POST /internal/v1/execute");
    console.log();
  });
}

server.on("upgrade", (request, socket, head) => {
  let url;
  try { url = new URL(request.url || "", "http://executor.internal"); }
  catch { socket.destroy(); return; }
  if (url.pathname !== "/ws/terminal") { socket.destroy(); return; }
  const ticket = url.searchParams.get("ticket") || "";
  let context;
  try {
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(ticket)) throw new Error("invalid ticket");
    context = executor.consumeTerminalTicket(ticket);
  } catch {
    socket.write("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
    socket.destroy();
    return;
  }
  terminals.handleUpgrade(request, socket, head, ws => {
    attachTerminal({ ws, context, executor }).catch(error => {
      console.error(`[terminal] ${error.code || "TERMINAL_OPEN_FAILED"}: ${error.message}`);
      try { ws.close(1011, "Terminal could not be opened"); } catch { /* best effort */ }
    });
  });
});

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n[shutdown] Closing SSH connection...");
  disconnect();
  process.exit(0);
});

process.on("SIGTERM", () => {
  disconnect();
  process.exit(0);
});

start().catch((err) => {
  console.error("[startup] Fatal:", err);
  process.exit(1);
});
