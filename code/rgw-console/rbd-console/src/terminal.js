import { randomBytes } from "crypto";
import { ExecutorError } from "./errors.js";

function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'"'"'`)}'`;
}

export class TerminalTicketStore {
  constructor({ ttlMs = Number(process.env.RBD_TERMINAL_TICKET_TTL_MS || 30000), maxTickets = 1000 } = {}) {
    this.ttlMs = ttlMs;
    this.maxTickets = maxTickets;
    this.tickets = new Map();
  }

  issue(context) {
    const now = Date.now();
    this.prune(now);
    const ticket = randomBytes(32).toString("base64url");
    const expiresAt = now + this.ttlMs;
    while (this.tickets.size >= this.maxTickets) this.tickets.delete(this.tickets.keys().next().value);
    this.tickets.set(ticket, { context: structuredClone(context), expiresAt });
    return { ticket, expires_at: new Date(expiresAt).toISOString() };
  }

  consume(ticket) {
    const now = Date.now();
    this.prune(now);
    const record = this.tickets.get(ticket);
    this.tickets.delete(ticket);
    if (!record || record.expiresAt <= now) throw new ExecutorError("TERMINAL_TICKET_INVALID", "Terminal ticket is invalid or expired", { status: 401 });
    return record.context;
  }

  prune(now = Date.now()) {
    for (const [ticket, record] of this.tickets) if (record.expiresAt <= now) this.tickets.delete(ticket);
  }
}

function sendJson(ws, value) {
  if (ws.readyState === 1) ws.send(JSON.stringify(value));
}

export async function attachTerminal({ ws, context, executor }) {
  const verified = await executor.terminalContext(context);
  let stream;
  try { stream = await executor.transport.openShell({ cols: 100, rows: 30 }); }
  catch (error) { executor.endAccessSession(context.volume_id); throw error; }
  const maxSessionMs = Number(process.env.RBD_TERMINAL_MAX_SESSION_MS || 60 * 60 * 1000);
  const idleMs = Number(process.env.RBD_TERMINAL_IDLE_TIMEOUT_MS || 15 * 60 * 1000);
  let idleTimer;
  let closed = false;

  const close = (code = 1000, reason = "Terminal closed") => {
    if (closed) return;
    closed = true;
    clearTimeout(idleTimer);
    clearTimeout(maxTimer);
    executor.endAccessSession(context.volume_id);
    try { stream.end("exit\n"); } catch { /* best effort */ }
    if (ws.readyState === 1 || ws.readyState === 0) ws.close(code, reason.slice(0, 120));
  };
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => close(1000, "Terminal idle timeout"), idleMs);
  };
  const maxTimer = setTimeout(() => close(1000, "Terminal session limit reached"), maxSessionMs);
  resetIdle();

  sendJson(ws, {
    type: "ready",
    volume_id: context.volume_id,
    mountpoint: verified.mountpoint,
    host: process.env.RBD_HOST || null,
    warning: "Lab shell: commands execute on the configured Linux Ceph client host.",
  });
  stream.write(`cd -- ${shellQuote(verified.mountpoint)}\n`);

  ws.on("message", (payload, isBinary) => {
    resetIdle();
    if (isBinary || payload.length > 64 * 1024) return close(1009, "Unsupported terminal message");
    let message;
    try { message = JSON.parse(payload.toString("utf8")); }
    catch { return close(1003, "Invalid terminal message"); }
    if (message.type === "input" && typeof message.data === "string" && Buffer.byteLength(message.data) <= 64 * 1024) stream.write(message.data);
    else if (message.type === "resize" && Number.isInteger(message.cols) && Number.isInteger(message.rows) && message.cols >= 20 && message.cols <= 400 && message.rows >= 5 && message.rows <= 200) stream.setWindow(message.rows, message.cols, 0, 0);
    else if (message.type !== "ping") close(1003, "Invalid terminal message");
  });
  ws.on("close", () => close());
  ws.on("error", () => close(1011, "Terminal WebSocket error"));
  stream.on("data", chunk => {
    resetIdle();
    if (ws.readyState === 1) ws.send(chunk, { binary: true });
  });
  stream.on("close", () => close(1000, "SSH shell closed"));
  stream.on("error", () => close(1011, "SSH shell error"));
}
