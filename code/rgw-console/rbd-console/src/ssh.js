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
let connectPromise = null;
let manualDisconnect = false;
let reconnectDelayMs = 3000;
let clientFactory = () => new Client();

function getConfig() {
  const cfg = {
    host: process.env.RBD_HOST,
    port: parseInt(process.env.RBD_SSH_PORT || "22", 10),
    username: process.env.RBD_SSH_USER || "root",
    readyTimeout: parseInt(process.env.RBD_SSH_CONNECT_TIMEOUT_MS || "10000", 10),
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
  if (connected) return Promise.resolve();
  if (connectPromise) return connectPromise;
  connecting = true;
  manualDisconnect = false;
  clearTimeout(reconnectTimer);

  connectPromise = new Promise((resolve, reject) => {
    const client = clientFactory();
    const cfg = getConfig();
    let settled = false;

    client.on("ready", () => {
      settled = true;
      conn = client;
      connected = true;
      connecting = false;
      connectPromise = null;
      lastError = null;
      console.log(`[ssh] Connected to ${cfg.host}:${cfg.port} as ${cfg.username}`);
      resolve();
    });

    client.on("error", (err) => {
      lastError = err.message;
      console.error(`[ssh] Error: ${err.message}`);
      if (!settled) {
        settled = true;
        connecting = false;
        connectPromise = null;
        scheduleReconnect();
        reject(err);
      }
    });

    client.on("close", () => {
      const wasConnected = connected;
      connected = false;
      connecting = false;
      connectPromise = null;
      conn = null;
      if (!settled) {
        settled = true;
        scheduleReconnect();
        reject(new Error("SSH connection closed before ready"));
      } else if (wasConnected && !manualDisconnect) {
        console.warn("[ssh] Connection closed, scheduling reconnect...");
        scheduleReconnect();
      }
    });

    client.on("end", () => {
      connected = false;
      conn = null;
      if (!manualDisconnect) scheduleReconnect();
    });

    try {
      client.connect(cfg);
    } catch (err) {
      connecting = false;
      connectPromise = null;
      lastError = err.message;
      if (!settled) {
        settled = true;
        scheduleReconnect();
        reject(err);
      }
    }
  });
  return connectPromise;
}


function scheduleReconnect() {
  if (manualDisconnect || reconnectTimer) return;
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    console.log("[ssh] Attempting reconnect...");
    connect().catch((err) => {
      console.error(`[ssh] Reconnect failed: ${err.message}`);
      scheduleReconnect();
    });
  }, reconnectDelayMs);
}

/**
 * Execute a command on the remote host.
 *
 * @param {string} command - The command string to execute.
 * @param {object} [opts]
 * @param {number} [opts.timeout] - Timeout in ms (default from env).
 * @param {boolean} [opts.sudo] - Prepend sudo -n (default false).
 * @returns {Promise<{stdout: string, stderr: string, code: number}>}
 */
export function exec(command, opts = {}) {
  const timeout = opts.timeout ?? parseInt(process.env.RBD_COMMAND_TIMEOUT_MS || "15000", 10);
  const maxOutputBytes = opts.maxOutputBytes ?? parseInt(process.env.RBD_MAX_OUTPUT_BYTES || String(5 * 1024 * 1024), 10);
  const actualCmd = opts.sudo ? `sudo -n ${command}` : command;

  return new Promise((resolve, reject) => {
    if (!conn || !connected) {
      return reject(new Error("SSH not connected"));
    }

    let stdout = "";
    let stderr = "";
    let finished = false;
    let timer = null;
    let outputBytes = 0;

    conn.exec(actualCmd, (err, stream) => {
      if (err) return reject(err);

      timer = setTimeout(() => {
        if (!finished) {
          finished = true;
          stream.destroy();
          reject(Object.assign(new Error(`Command timed out after ${timeout}ms: ${redactCmd(actualCmd)}`), { code: "EXECUTOR_TIMEOUT" }));
        }
      }, timeout);

      const collect = (target, chunk) => {
        if (finished) return;
        outputBytes += chunk.length;
        if (outputBytes > maxOutputBytes) {
          finished = true;
          clearTimeout(timer);
          stream.destroy();
          reject(Object.assign(new Error(`Command output exceeded ${maxOutputBytes} bytes: ${redactCmd(actualCmd)}`), { code: "COMMAND_OUTPUT_LIMIT" }));
          return;
        }
        if (target === "stdout") stdout += chunk;
        else stderr += chunk;
      };
      stream.on("data", (chunk) => collect("stdout", chunk));
      stream.stderr.on("data", (chunk) => collect("stderr", chunk));

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
    const actualCmd = opts.sudo ? `sudo -n ${command}` : command;
    throw new Error(`Command failed (exit ${result.code}): ${redactCmd(actualCmd)}\n${result.stderr.slice(0, 500)}`);
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new Error(`Invalid JSON from: ${redactCmd(command)}\n${result.stdout.slice(0, 200)}`);
  }
}

/** Write, read back, and remove one bounded probe file through SFTP. */
export function probeFile(remotePath, payload) {
  if (!conn || !connected) return Promise.reject(new Error("SSH not connected"));
  const data = Buffer.isBuffer(payload) ? payload : Buffer.from(String(payload));
  if (data.length > 64 * 1024) return Promise.reject(new Error("Probe payload is too large"));
  return new Promise((resolve, reject) => {
    conn.sftp((sftpError, sftp) => {
      if (sftpError) return reject(sftpError);
      const finish = (error) => {
        try { sftp.end(); } catch { /* best effort */ }
        if (error) reject(error); else resolve();
      };
      sftp.writeFile(remotePath, data, { mode: 0o600, flag: "wx" }, (writeError) => {
        if (writeError) return finish(writeError);
        sftp.readFile(remotePath, (readError, observed) => {
          if (readError) return sftp.unlink(remotePath, () => finish(readError));
          const mismatch = !Buffer.from(observed).equals(data) ? new Error("Mounted filesystem probe mismatch") : null;
          sftp.unlink(remotePath, (unlinkError) => finish(mismatch || unlinkError || null));
        });
      });
    });
  });
}

/** Open an SFTP session on the authenticated SSH connection. */
export function openSftp() {
  if (!conn || !connected) return Promise.reject(new Error("SSH not connected"));
  return new Promise((resolve, reject) => {
    conn.sftp((error, sftp) => error ? reject(error) : resolve(sftp));
  });
}

/** Open one interactive PTY-backed shell. */
export function openShell(options = {}) {
  if (!conn || !connected) return Promise.reject(new Error("SSH not connected"));
  const cols = Number.isInteger(options.cols) ? options.cols : 100;
  const rows = Number.isInteger(options.rows) ? options.rows : 30;
  return new Promise((resolve, reject) => {
    conn.shell({ term: "xterm-256color", cols, rows }, (error, stream) => {
      if (error) reject(error);
      else resolve(stream);
    });
  });
}

/** Redact potential secrets from command strings for logging. */
export function redactCmd(cmd) {
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
  manualDisconnect = true;
  clearTimeout(reconnectTimer);
  reconnectTimer = null;
  if (conn) {
    conn.end();
    conn = null;
  }
  connected = false;
  connecting = false;
  connectPromise = null;
}

/** Get the raw ssh2 Client (for shell/sftp). */
export function getConnection() {
  return conn;
}

/** Test-only dependency seam for deterministic reconnect/stream behavior. */
export function __setClientFactoryForTests(factory, delayMs = 0) {
  disconnect();
  clientFactory = factory;
  reconnectDelayMs = delayMs;
}

export function __resetForTests() {
  disconnect();
  clientFactory = () => new Client();
  reconnectDelayMs = 3000;
}
