/**
 * RBD Test Console — Express server.
 *
 * Connects to a Linux Ceph host via SSH and exposes REST API
 * for RBD image management and cluster health.
 */

import "dotenv/config";
import express from "express";
import cors from "cors";
import { connect, disconnect, status as sshStatus } from "./ssh.js";
import healthRouter from "./routes/health.js";
import imagesRouter from "./routes/images.js";
import devicesRouter from "./routes/devices.js";

const app = express();
const PORT = parseInt(process.env.PORT || "3001", 10);

// --- Middleware ---

const origins = (process.env.CORS_ORIGINS || "http://localhost:5173").split(",").map(s => s.trim());
app.use(cors({ origin: origins, credentials: true }));
app.use(express.json({ limit: "1mb" }));

// Request ID
app.use((req, _res, next) => {
  req.requestId = `rbd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  next();
});

// --- Routes ---

app.get("/api/rbd/health", (_req, res) => {
  const ssh = sshStatus();
  res.json({ status: ssh.connected ? "ok" : "disconnected", ssh });
});

app.use("/api/rbd/ssh", healthRouter);
app.use("/api/rbd/images", imagesRouter);
app.use("/api/rbd/devices", devicesRouter);

// --- Error handler ---

app.use((err, req, res, _next) => {
  const status = err.status || 500;
  const message = err.message || "Internal server error";
  console.error(`[${req.requestId}] ${req.method} ${req.path} → ${status}: ${message}`);
  res.status(status).json({
    error: message,
    code: err.code || "INTERNAL_ERROR",
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

  app.listen(PORT, () => {
    console.log();
    console.log(`[startup] Listening on http://localhost:${PORT}`);
    console.log(`[startup] Health: http://localhost:${PORT}/api/rbd/ssh/health`);
    console.log(`[startup] Images: http://localhost:${PORT}/api/rbd/images`);
    console.log(`[startup] Devices: http://localhost:${PORT}/api/rbd/devices`);
    console.log();
  });
}

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
