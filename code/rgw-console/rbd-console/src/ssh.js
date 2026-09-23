/**
 * SSH connection manager for rbd-console.
 *
 * Provides a persistent SSH connection to the Linux Ceph host with
 * auto-reconnect, command execution with timeout, and FSID validation.
 */

import { Client } from "ssh2";
import { readFileSync } from "fs";
import { resolve } from "path";

/** @type {Client | null} */
let conn = null;
let connected = false;
let connecting = false;
let lastError = null;
let reconnectTimer = null;

const RECONNECT_DELAY_MS = 3000;

function getConfig() {
  const cfg = {
    host: process.env.RBD_HOST,
    port: parseInt(process.env.RBD_SSH_PORT || "22", 10),
    username: process.env.RBD_SSH_USER || "root",
    readyTimeout: 10000,
    keepaliveInterval: 10000,
    keepaliveCountMax: 3,
  };
  const keyPath = process.env.RBD_SSH_KEY_PATH;
  if (keyPath) {
    const resolved = resolve(keyPath.replace(/^~/, process.env.HOME || process.env.USERPROFILE || ""));
    try {
      cfg.privateKey = readFileSync(resolved);
    } catch (err) {
      console.error(`[ssh] Cannot read key ${resolved}: ${err.message}`);
    }
  }
  const password = process.env.RBD_SSH_PASSWORD;
  if (password) {
    cfg.password = password;
  }
  if (!cfg.privateKey && !cfg.password) {
    console.warn("[ssh] No SSH key or password configured; connection will likely fail");
  }
  return cfg;
}

/**
 * Connect (or reconnect) to the SSH host.
 * @returns {Promise<void>}
 */
export function connect() {
  if (connected || connecting) return Promise.resolve();
  connecting = true;
  clearTimeout(reconnectTimer);

  return new Promise((resolve, reject) => {
    const client = new Client();
    const cfg = getConfig();

    client.on("ready", () => {
      conn = client;
      connected = true;
      connecting = false;
      lastError = null;
      console.log(`[ssh] Connected to ${cfg.host}:${cfg.port} as ${cfg.username}`);
      resolve();
    });

    client.on("error", (err) => {
      lastError = err.message;
      console.error(`[ssh] Error: ${err.message}`);
    });

    client.on("close", () => {
      const wasConnected = connected;
      connected = false;
      connecting = false;
      conn = null;
      if (wasConnected) {
        console.warn("[ssh] Connection closed, scheduling reconnect...");
        scheduleReconnect();
      }
    });

    client.on("end", () => {
      connected = false;
      conn = null;
    });

    try {
      client.connect(cfg);
    } catch (err) {
      connecting = false;
      lastError = err.message;
      reject(err);
    }
  });
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    console.log("[ssh] Attempting reconnect...");
    connect().catch((err) => {
      console.error(`[ssh] Reconnect failed: ${err.message}`);
      scheduleReconnect();
    });
  }, RECONNECT_DELAY_MS);
}

/**
 * Execute a command on the remote host.
 *
 * @param {string} command - The command string to execute.
 * @param {object} [opts]
 * @param {number} [opts.timeout] - Timeout in ms (default from env).
 * @returns {Promise<{stdout: string, stderr: string, code: number}>}
 */
export function exec(command, opts = {}) {
  const timeout = opts.timeout ?? parseInt(process.env.RBD_COMMAND_TIMEOUT_MS || "15000", 10);

  return new Promise((resolve, reject) => {
    if (!conn || !connected) {
      return reject(new Error("SSH not connected"));
    }

    let stdout = "";
    let stderr = "";
    let finished = false;
    let timer = null;

    conn.exec(command, (err, stream) => {
      if (err) return reject(err);

      timer = setTimeout(() => {
        if (!finished) {
          finished = true;
          stream.destroy();
          reject(new Error(`Command timed out after ${timeout}ms: ${redactCmd(command)}`));
        }
      }, timeout);

      stream.on("data", (chunk) => { stdout += chunk; });
      stream.stderr.on("data", (chunk) => { stderr += chunk; });

      stream.on("close", (code) => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        resolve({ stdout, stderr, code: code ?? 0 });
      });
    });
  });
}

/**
 * Execute a command, expecting JSON output.
 * @param {string} command
 * @param {object} [opts]
 * @returns {Promise<any>}
 */
export async function execJson(command, opts = {}) {
  const result = await exec(command, opts);
  if (result.code !== 0) {
    throw new Error(`Command failed (exit ${result.code}): ${redactCmd(command)}\n${result.stderr.slice(0, 500)}`);
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new Error(`Invalid JSON from: ${redactCmd(command)}\n${result.stdout.slice(0, 200)}`);
  }
}

/** Redact potential secrets from command strings for logging. */
function redactCmd(cmd) {
  return cmd.replace(/--key\s+\S+/g, "--key [REDACTED]")
            .replace(/--keyring\s+\S+/g, "--keyring [REDACTED]");
}

/** Check connection status. */
export function status() {
  return {
    connected,
    host: process.env.RBD_HOST || null,
    port: parseInt(process.env.RBD_SSH_PORT || "22", 10),
    user: process.env.RBD_SSH_USER || "root",
    lastError,
  };
}

/** Gracefully close the SSH connection. */
export function disconnect() {
  clearTimeout(reconnectTimer);
  if (conn) {
    conn.end();
    conn = null;
  }
  connected = false;
  connecting = false;
}

/** Get the raw ssh2 Client (for shell/sftp). */
export function getConnection() {
  return conn;
}
