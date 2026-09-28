import { createHash, randomUUID } from "crypto";
import * as ssh from "./ssh.js";
import { ExecutorError } from "./errors.js";
import { normalizeVolumePath, SftpFileService } from "./files.js";
import { VolumeStateStore } from "./state.js";
import { TerminalTicketStore } from "./terminal.js";
import {
  csvSet, safeCommand, validateImageName, validateNamespace, validatePool, validateUuid,
} from "./validators.js";

export const PROTOCOL_VERSION = 1;
export const INVENTORY_ACTIONS = new Set([
  "ceph.status", "ceph.fsid", "ceph.versions", "ceph.osd_df", "ceph.osd_tree",
  "ceph.pool_ls_detail", "ceph.crush_rule_dump",
]);
export const RBD_READ_ACTIONS = new Set([
  "rbd.pool.list", "rbd.image.list", "rbd.image.info", "rbd.device.list",
]);
export const RBD_MUTATION_ACTIONS = new Set([
  "rbd.image.create", "rbd.image.map", "rbd.device.format_ext4", "rbd.device.mount",
  "rbd.device.unmount", "rbd.device.unmap", "rbd.image.remove",
]);
export const RBD_FILE_ACTIONS = new Set([
  "rbd.files.list", "rbd.files.stat", "rbd.files.mkdir", "rbd.files.delete", "rbd.files.manifest",
]);
export const TERMINAL_ACTIONS = new Set(["rbd.terminal.ticket.create"]);
export const ALLOWED_ACTIONS = new Set([
  "health", "capabilities", "ceph.capacity_inventory", ...INVENTORY_ACTIONS, ...RBD_READ_ACTIONS,
  ...RBD_MUTATION_ACTIONS, ...RBD_FILE_ACTIONS, ...TERMINAL_ACTIONS,
]);

const INVENTORY_COMMANDS = {
  "ceph.status": ["ceph", "status", "--format=json"],
  "ceph.versions": ["ceph", "versions", "--format=json"],
  "ceph.osd_df": ["ceph", "osd", "df", "--format=json"],
  "ceph.osd_tree": ["ceph", "osd", "tree", "--format=json"],
  "ceph.pool_ls_detail": ["ceph", "osd", "pool", "ls", "detail", "--format=json"],
  "ceph.crush_rule_dump": ["ceph", "osd", "crush", "rule", "dump", "--format=json"],
};

const IDENTITY_FIELDS = ["pool", "namespace", "image_name"];
const MUTATION_COMMON = ["volume_id", "action_id", "fence_token"];
const FILE_IDENTITY = ["volume_id", ...IDENTITY_FIELDS, "image_id", "device_major", "device_minor", "fs_uuid"];
const ACTION_FIELDS = {
  "rbd.image.list": ["pool", "namespace"],
  "rbd.image.info": IDENTITY_FIELDS,
  "rbd.image.create": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "size_bytes"],
  "rbd.image.map": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "image_id"],
  "rbd.device.format_ext4": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "image_id", "creation_action_id", "device_major", "device_minor"],
  "rbd.device.mount": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "image_id", "device_major", "device_minor", "fs_uuid"],
  "rbd.device.unmount": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "image_id", "device_major", "device_minor", "fs_uuid"],
  "rbd.device.unmap": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "image_id", "device_major", "device_minor"],
  "rbd.image.remove": [...MUTATION_COMMON, ...IDENTITY_FIELDS, "image_id"],
  "rbd.files.list": [...FILE_IDENTITY, "path"],
  "rbd.files.stat": [...FILE_IDENTITY, "path"],
  "rbd.files.mkdir": [...FILE_IDENTITY, "path"],
  "rbd.files.delete": [...FILE_IDENTITY, "path"],
  "rbd.files.manifest": [...FILE_IDENTITY, "paths"],
  "rbd.files.download": [...FILE_IDENTITY, "path"],
  "rbd.files.upload": [...FILE_IDENTITY, "path"],
  "rbd.terminal.ticket.create": FILE_IDENTITY,
};

function excerpt(value, max = 2000) {
  return ssh.redactCmd(String(value || "")).slice(0, max);
}

function fingerprint(value) {
  const canonical = JSON.stringify(Object.keys(value).sort().reduce((out, key) => {
    out[key] = value[key]; return out;
  }, {}));
  return createHash("sha256").update(canonical).digest("hex");
}

function ensure(condition, code, message, options) {
  if (!condition) throw new ExecutorError(code, message, options);
}

export class SshExecutor {
  constructor({ transport = ssh, store = new VolumeStateStore(), tickets = new TerminalTicketStore(), wait = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
    this.transport = transport;
    this.store = store;
    this.files = new SftpFileService(transport);
    this.tickets = tickets;
    this.wait = wait;
    this.activeAccessSessions = new Map();
    this.expectedFsid = String(process.env.CEPH_EXPECTED_FSID || "").toLowerCase();
    this.mountRoot = String(process.env.RBD_MOUNT_ROOT || "/mnt/rbd").replace(/\/+$/, "");
    this.allowedPools = csvSet(process.env.RBD_ALLOWED_POOLS || process.env.RBD_POOL);
    this.allowedNamespaces = new Set([...csvSet(process.env.RBD_ALLOWED_NAMESPACES || "default")].map(item => item === "default" ? "" : item));
    this.imagePrefix = process.env.RBD_IMAGE_PREFIX || "lab-";
  }

  async dispatch(action, params = {}) {
    ensure(ALLOWED_ACTIONS.has(action), "ACTION_NOT_ALLOWED", "The requested executor action is not allowlisted", { status: 404 });
    this.validateParams(action, params);
    const fsid = await this.assertFsid();
    const collectedAt = new Date().toISOString();

    if (action === "health") {
      return { status: "ok", executor_version: "1.0.0", protocol_version: PROTOCOL_VERSION, fsid, collected_at: collectedAt };
    }
    if (action === "capabilities") {
      return {
        executor_version: "1.0.0", protocol_version: PROTOCOL_VERSION, fsid,
        actions: [...ALLOWED_ACTIONS].sort(), collected_at: collectedAt,
        rbd_scope: {
          pools: [...this.allowedPools].sort(), namespaces: [...this.allowedNamespaces].sort(),
          image_prefixes: [this.imagePrefix], mount_root: this.mountRoot, filesystem: "ext4",
          file_browser: true, terminal: true,
          preview_max_bytes: Number(process.env.RBD_FILE_PREVIEW_MAX_BYTES || 5 * 1024 * 1024),
          preview_mime: [...csvSet(process.env.RBD_ALLOWED_PREVIEW_MIME || "text/plain,text/markdown,text/yaml,text/csv,application/json,application/pdf,image/jpeg,image/png,image/gif,image/webp,image/svg+xml")].sort(),
          force_operations: false, lazy_unmount: false,
        },
      };
    }

    let data;
    if (action === "ceph.fsid") data = { fsid };
    else if (action === "ceph.capacity_inventory") data = await this.capacityInventory();
    else if (INVENTORY_ACTIONS.has(action)) data = await this.runJson(INVENTORY_COMMANDS[action], action);
    else if (action === "rbd.pool.list") data = await this.poolList();
    else if (action === "rbd.image.list") data = await this.imageList(params);
    else if (action === "rbd.image.info") data = await this.imageInfo(params, true);
    else if (action === "rbd.device.list") data = await this.deviceListDetailed();
    else if (action === "rbd.files.manifest") data = await this.manifestFiles(params);
    else if (RBD_FILE_ACTIONS.has(action)) data = await this.store.withLock(params.volume_id, () => this.fileAction(action, params));
    else if (action === "rbd.terminal.ticket.create") data = await this.issueTerminalTicket(params);
    else data = await this.store.withLock(params.volume_id, () => this.mutate(action, params));
    return { fsid, action, data, collected_at: collectedAt };
  }

  validateParams(action, params) {
    ensure(params && typeof params === "object" && !Array.isArray(params), "INVALID_REQUEST", "params must be a JSON object");
    const required = ACTION_FIELDS[action] || [];
    const keys = Object.keys(params);
    ensure(keys.every(key => required.includes(key)), "INVALID_REQUEST", "params contains an unknown field");
    ensure(required.every(key => Object.hasOwn(params, key)), "INVALID_REQUEST", "params is missing a required field");
    if (required.includes("pool")) {
      const checked = validatePool(params.pool); ensure(checked.ok, "SCOPE_NOT_ALLOWED", checked.error);
    }
    if (required.includes("namespace")) {
      const checked = validateNamespace(params.namespace); ensure(checked.ok && checked.value === params.namespace, "SCOPE_NOT_ALLOWED", checked.error || "Namespace must be normalized");
    }
    if (required.includes("image_name")) {
      const checked = validateImageName(params.image_name); ensure(checked.ok, "SCOPE_NOT_ALLOWED", checked.error);
    }
    for (const field of ["volume_id", "action_id", "creation_action_id", "fs_uuid"]) {
      if (required.includes(field)) {
        const checked = validateUuid(params[field], field); ensure(checked.ok, "INVALID_REQUEST", checked.error);
      }
    }
    if (required.includes("image_id")) ensure(typeof params.image_id === "string" && /^[0-9a-f]{1,64}$/i.test(params.image_id), "INVALID_REQUEST", "image_id is invalid");
    if (required.includes("fence_token")) ensure(Number.isInteger(params.fence_token) && params.fence_token > 0, "INVALID_REQUEST", "fence_token must be positive");
    for (const field of ["size_bytes", "device_major", "device_minor"]) {
      if (required.includes(field)) ensure(Number.isInteger(params[field]) && params[field] >= (field === "size_bytes" ? 1 : 0), "INVALID_REQUEST", `${field} is invalid`);
    }
    if (required.includes("path")) normalizeVolumePath(params.path);
    if (required.includes("paths")) {
      ensure(Array.isArray(params.paths) && params.paths.length >= 1 && params.paths.length <= 100, "INVALID_REQUEST", "paths must contain 1 to 100 entries");
      params.paths.forEach(path => normalizeVolumePath(path));
    }
  }

  async assertFsid() {
    ensure(validateUuid(this.expectedFsid, "CEPH_EXPECTED_FSID").ok, "EXECUTOR_NOT_CONFIGURED", "CEPH_EXPECTED_FSID is required", { status: 503 });
    const observed = (await this.runText(["ceph", "fsid"], "ceph.fsid")).trim().toLowerCase();
    ensure(validateUuid(observed, "observed fsid").ok, "INVALID_CEPH_OUTPUT", "ceph fsid returned an invalid UUID");
    ensure(observed === this.expectedFsid, "FSID_MISMATCH", "Connected Ceph cluster does not match CEPH_EXPECTED_FSID", { details: { expected_fsid: this.expectedFsid, observed_fsid: observed } });
    return observed;
  }

  async run(parts, action, { sudo = true, allowCodes = [0], timeout } = {}) {
    let result;
    try {
      result = await this.transport.exec(safeCommand(parts), { sudo, timeout });
    } catch (error) {
      throw new ExecutorError(error?.code || "EXECUTOR_UNAVAILABLE", error?.message || "SSH executor is unavailable", { retryable: true, status: 503 });
    }
    if (!allowCodes.includes(result.code)) {
      throw new ExecutorError("COMMAND_FAILED", "SSH command failed", {
        retryable: true,
        details: { action, exit_code: result.code, stderr: excerpt(result.stderr) },
      });
    }
    return result;
  }

  async runText(parts, action, options) {
    return (await this.run(parts, action, options)).stdout;
  }

  async runJson(parts, action, options) {
    const output = await this.runText(parts, action, options);
    try { return JSON.parse(output); }
    catch { throw new ExecutorError("INVALID_CEPH_OUTPUT", "Command did not return valid JSON", { details: { action } }); }
  }

  imageArgs(params) {
    return ["--pool", params.pool, ...(params.namespace ? ["--namespace", params.namespace] : []), "--image", params.image_name];
  }

  async poolList() {
    const pools = await this.runJson(["ceph", "osd", "pool", "ls", "--format=json"], "rbd.pool.list");
    return { pools: Array.isArray(pools) ? pools.filter(pool => this.allowedPools.has(pool)).sort() : [] };
  }

  async capacityInventory() {
    const statusBefore = await this.runJson(INVENTORY_COMMANDS["ceph.status"], "ceph.status");
    const [osdDf, osdTree, poolDetails, crushRules] = await Promise.all([
      this.runJson(INVENTORY_COMMANDS["ceph.osd_df"], "ceph.osd_df"),
      this.runJson(INVENTORY_COMMANDS["ceph.osd_tree"], "ceph.osd_tree"),
      this.runJson(INVENTORY_COMMANDS["ceph.pool_ls_detail"], "ceph.pool_ls_detail"),
      this.runJson(INVENTORY_COMMANDS["ceph.crush_rule_dump"], "ceph.crush_rule_dump"),
    ]);
    const statusAfter = await this.runJson(INVENTORY_COMMANDS["ceph.status"], "ceph.status");
    return {
      status_before: statusBefore,
      status_after: statusAfter,
      osd_df: osdDf,
      osd_tree: osdTree,
      pool_details: poolDetails,
      crush_rules: crushRules,
    };
  }

  async imageList(params) {
    const images = await this.runJson(["rbd", "ls", "--pool", params.pool, ...(params.namespace ? ["--namespace", params.namespace] : []), "--format=json"], "rbd.image.list");
    return { pool: params.pool, namespace: params.namespace, images: (Array.isArray(images) ? images : []).map(item => typeof item === "string" ? item : item?.name).filter(name => typeof name === "string" && name.startsWith(this.imagePrefix)).sort() };
  }

  async imageInfo(params, required = true) {
    let raw;
    try {
      raw = await this.runJson(["rbd", "info", ...this.imageArgs(params), "--format=json"], "rbd.image.info");
    } catch (error) {
      const text = `${error.message} ${error.details?.stderr || ""}`.toLowerCase();
      if (!required && ["no such file", "does not exist", "error opening image"].some(marker => text.includes(marker))) return null;
      throw error;
    }
    const features = Array.isArray(raw.features) ? raw.features : String(raw.features || "").split(",").map(item => item.trim()).filter(Boolean);
    ensure(typeof raw.id === "string" && /^[0-9a-f]{1,64}$/i.test(raw.id) && Number.isInteger(raw.size) && raw.size > 0, "INVALID_CEPH_OUTPUT", "rbd info returned an invalid identity");
    return { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: raw.id, size_bytes: raw.size, features: [...features].sort() };
  }

  async deviceList() {
    const rows = await this.runJson(["rbd", "device", "list", "--format=json"], "rbd.device.list");
    ensure(Array.isArray(rows), "INVALID_CEPH_OUTPUT", "rbd device list returned an invalid response");
    return rows.map(item => ({
      mapping_id: String(item.id ?? ""), pool: item.pool, namespace: item.namespace || "",
      image_name: item.name ?? item.image, image_id: item.image_id, device: item.device,
    })).filter(item => this.allowedPools.has(item.pool) && this.allowedNamespaces.has(item.namespace) && typeof item.image_name === "string" && item.image_name.startsWith(this.imagePrefix));
  }

  async observeMapping(mapping, params) {
    ensure(mapping && typeof mapping.device === "string" && mapping.device.startsWith("/dev/rbd") && /^\d+$/.test(mapping.mapping_id), "DEVICE_IDENTITY_MISMATCH", "RBD mapping identity is invalid");
    const stat = (await this.runText(["stat", "-Lc", "%t:%T", mapping.device], "rbd.device.stat", { sudo: false })).trim();
    const [majorHex, minorHex] = stat.split(":");
    const major = Number.parseInt(majorHex, 16); const minor = Number.parseInt(minorHex, 16);
    ensure(Number.isInteger(major) && Number.isInteger(minor), "DEVICE_IDENTITY_MISMATCH", "Mapped device major:minor is invalid");
    const root = `/sys/bus/rbd/devices/${mapping.mapping_id}`;
    for (const [field, expected] of [["pool", params.pool], ["name", params.image_name], ["image_id", params.image_id]]) {
      const observed = (await this.runText(["cat", `${root}/${field}`], "rbd.device.sysfs", { sudo: false })).trim();
      ensure(observed === expected, "DEVICE_IDENTITY_MISMATCH", `RBD sysfs ${field} does not match`);
    }
    if (params.namespace) {
      const observed = (await this.runText(["cat", `${root}/pool_ns`], "rbd.device.sysfs", { sudo: false })).trim();
      ensure(observed === params.namespace, "DEVICE_IDENTITY_MISMATCH", "RBD sysfs namespace does not match");
    }
    return { mapping_id: mapping.mapping_id, device: mapping.device, device_major: major, device_minor: minor };
  }

  async matchingMappings(params) {
    return (await this.deviceList()).filter(item => item.pool === params.pool && item.namespace === params.namespace && item.image_name === params.image_name);
  }

  async deviceListDetailed() {
    const devices = [];
    for (const mapping of await this.deviceList()) {
      const info = await this.imageInfo(mapping, true);
      const observed = await this.observeMapping(mapping, info);
      const signature = await this.blkid(observed.device, true);
      const mount = await this.findMountBySource(observed.device);
      devices.push({ ...info, ...observed, mounted: Boolean(mount), ...(mount ? { mountpoint: mount.target } : {}), ...(signature.TYPE === "ext4" ? { filesystem: "ext4", fs_uuid: signature.UUID } : {}) });
    }
    return { devices };
  }

  async mutate(action, params) {
    if (["rbd.device.unmount", "rbd.device.unmap", "rbd.image.remove"].includes(action)) {
      ensure(!this.activeAccessSessions.get(params.volume_id), "VOLUME_BUSY", "The volume has an active file transfer or terminal session", { status: 409 });
    }
    if (action === "rbd.image.create") return this.createImage(params);
    const record = await this.requireRecord(params);
    if (action === "rbd.image.map") return this.mapImage(params, record);
    if (action === "rbd.device.format_ext4") return this.formatExt4(params, record);
    if (action === "rbd.device.mount") return this.mount(params, record);
    if (action === "rbd.device.unmount") return this.unmount(params, record);
    if (action === "rbd.device.unmap") return this.unmap(params, record);
    if (action === "rbd.image.remove") return this.removeImage(params, record);
    throw new ExecutorError("ACTION_NOT_ALLOWED", "Mutation action is not supported");
  }

  actionState(record, action, params) {
    const previous = record.actions?.[params.action_id];
    const digest = fingerprint(params);
    if (previous) {
      ensure(previous.action === action && previous.fingerprint === digest, "IDEMPOTENCY_CONFLICT", "action_id was reused with different input");
      if (previous.state === "SUCCEEDED") return { replay: { ...previous.result, replayed: true } };
      ensure(previous.state === "IN_PROGRESS", "ACTION_STATE_INVALID", "Stored executor action state is invalid");
      return { inProgress: true };
    }
    ensure(params.fence_token > Number(record.last_fence_token || 0), "FENCE_REJECTED", "Action fence token is stale");
    return {};
  }

  async begin(record, action, params) {
    const state = this.actionState(record, action, params);
    if (state.replay) return state;
    record.actions ||= {};
    record.actions[params.action_id] = { action, fingerprint: fingerprint(params), state: "IN_PROGRESS" };
    record.last_fence_token = Math.max(Number(record.last_fence_token || 0), params.fence_token);
    const ids = Object.keys(record.actions); for (const id of ids.slice(0, Math.max(0, ids.length - 64))) delete record.actions[id];
    await this.store.save(record);
    return state;
  }

  async finish(record, params, result) {
    record.actions[params.action_id] = { ...record.actions[params.action_id], state: "SUCCEEDED", result };
    await this.store.save(record);
    return result;
  }

  async requireRecord(params) {
    const record = await this.store.load(params.volume_id);
    ensure(record, "UNMANAGED_VOLUME", "No executor record exists for this volume");
    for (const field of ["pool", "namespace", "image_name", "image_id"]) ensure(record[field] === params[field], "IMAGE_IDENTITY_MISMATCH", "Image identity does not match executor record");
    ensure(record.created_confirmed && !record.deleted, "IMAGE_STATE_CONFLICT", "Managed image is not in a mutable live state");
    return record;
  }

  async assertLive(params, record) {
    const info = await this.imageInfo(params, true);
    ensure(info.image_id === params.image_id && info.image_id === record.image_id, "IMAGE_IDENTITY_MISMATCH", "Immutable RBD image ID changed");
    return info;
  }

  async mountedContext(params) {
    const record = await this.requireRecord(params);
    ensure(record.mounted && record.mountpoint === this.mountpoint(params.volume_id), "VOLUME_NOT_MOUNTED", "The managed volume is not mounted", { status: 409 });
    const observed = await this.expectedMapping(params, record);
    await this.assertFilesystem(params, record, observed.device);
    const mountpoint = this.mountpoint(params.volume_id);
    const mounted = await this.findMountByTarget(mountpoint);
    ensure(mounted && mounted.source === observed.device && mounted.target === mountpoint && mounted.fstype === "ext4" && String(mounted.options || "").split(",").includes("rw"), "MOUNT_IDENTITY_MISMATCH", "The mounted filesystem identity does not match");
    return { record, mountpoint, ...observed };
  }

  async fileAction(action, params) {
    const context = await this.mountedContext(params);
    if (action === "rbd.files.list") return this.files.list(context.mountpoint, params.path);
    if (action === "rbd.files.stat") return this.files.stat(context.mountpoint, params.path);
    if (action === "rbd.files.mkdir") return this.files.mkdir(context.mountpoint, params.path);
    if (action === "rbd.files.delete") return this.files.remove(context.mountpoint, params.path);
    if (action === "rbd.files.manifest") return this.files.manifest(context.mountpoint, params.paths);
    throw new ExecutorError("ACTION_NOT_ALLOWED", "File action is not supported");
  }

  async manifestFiles(params) {
    const context = await this.store.withLock(params.volume_id, async () => {
      const mounted = await this.mountedContext(params);
      this.beginAccessSession(params.volume_id);
      return mounted;
    });
    try { return await this.files.manifest(context.mountpoint, params.paths); }
    finally { this.endAccessSession(params.volume_id); }
  }

  async issueTerminalTicket(params) {
    await this.store.withLock(params.volume_id, () => this.mountedContext(params));
    return { ...this.tickets.issue(params), websocket_path: "/ws/terminal" };
  }

  consumeTerminalTicket(ticket) {
    return this.tickets.consume(ticket);
  }

  async terminalContext(params) {
    this.validateParams("rbd.terminal.ticket.create", params);
    await this.assertFsid();
    return this.store.withLock(params.volume_id, async () => {
      const context = await this.mountedContext(params);
      this.beginAccessSession(params.volume_id);
      return { mountpoint: context.mountpoint };
    });
  }

  beginAccessSession(volumeId) {
    this.activeAccessSessions.set(volumeId, Number(this.activeAccessSessions.get(volumeId) || 0) + 1);
  }

  endAccessSession(volumeId) {
    const remaining = Number(this.activeAccessSessions.get(volumeId) || 0) - 1;
    if (remaining > 0) this.activeAccessSessions.set(volumeId, remaining);
    else this.activeAccessSessions.delete(volumeId);
  }

  async downloadFile(params, writable, onReady) {
    this.validateParams("rbd.files.download", params);
    await this.assertFsid();
    const context = await this.store.withLock(params.volume_id, async () => {
      const context = await this.mountedContext(params);
      this.beginAccessSession(params.volume_id);
      return context;
    });
    try { return await this.files.download(context.mountpoint, params.path, writable, onReady); }
    finally { this.endAccessSession(params.volume_id); }
  }

  async uploadFile(params, readable, expectedBytes) {
    this.validateParams("rbd.files.upload", params);
    await this.assertFsid();
    const maxBytes = Number(process.env.RBD_FILE_UPLOAD_MAX_BYTES || 16 * 1024 * 1024 * 1024);
    const context = await this.store.withLock(params.volume_id, async () => {
      const context = await this.mountedContext(params);
      this.beginAccessSession(params.volume_id);
      return context;
    });
    try { return await this.files.upload(context.mountpoint, params.path, readable, { expectedBytes, maxBytes }); }
    finally { this.endAccessSession(params.volume_id); }
  }

  async createImage(params) {
    ensure(params.size_bytes % (1024 * 1024) === 0, "INVALID_SIZE", "RBD image size must be MiB-aligned");
    ensure(params.size_bytes <= Number(process.env.RBD_MAX_SIZE_BYTES || 1024 ** 4), "INVALID_SIZE", "RBD image size exceeds the configured maximum");
    let record = await this.store.load(params.volume_id);
    if (!record) {
      ensure(!(await this.imageInfo(params, false)), "IMAGE_ALREADY_EXISTS", "Refusing to adopt or overwrite an existing RBD image");
      record = { version: 1, volume_id: params.volume_id, pool: params.pool, namespace: params.namespace, image_name: params.image_name, size_bytes: params.size_bytes, creation_action_id: params.action_id, created_confirmed: false, formatted: false, deleted: false, last_fence_token: 0, actions: {} };
    } else {
      for (const [field, value] of Object.entries({ pool: params.pool, namespace: params.namespace, image_name: params.image_name, size_bytes: params.size_bytes, creation_action_id: params.action_id })) ensure(record[field] === value, "VOLUME_ID_CONFLICT", "Volume ID is bound to a different executor record");
    }
    const state = await this.begin(record, "rbd.image.create", params); if (state.replay) return state.replay;
    let info = await this.imageInfo(params, false);
    if (!info) {
      await this.run(["rbd", "create", ...this.imageArgs(params), "--size", `${params.size_bytes / (1024 * 1024)}M`, "--image-format", "2", "--image-feature", "layering,exclusive-lock"], "rbd.image.create", { timeout: 60000 });
      info = await this.imageInfo(params, true);
    }
    ensure(info.size_bytes === params.size_bytes && info.features.includes("exclusive-lock"), "CREATE_VERIFY_FAILED", "Created image identity or features are unexpected");
    Object.assign(record, { image_id: info.image_id, features: info.features, created_confirmed: true });
    return this.finish(record, params, { ...info, volume_id: params.volume_id, state: "CREATED" });
  }

  async imageStatus(params) {
    const raw = await this.runJson(["rbd", "status", ...this.imageArgs(params), "--format=json"], "rbd.image.status");
    ensure(raw && Array.isArray(raw.watchers), "INVALID_CEPH_OUTPUT", "rbd status returned invalid watchers");
    return raw;
  }

  async waitForNoWatchers(params) {
    // An unmap may disappear from the local device list before Ceph drops its
    // watcher. Keep the refusal for persistent or external users of the image.
    for (let attempt = 0; attempt < 6; attempt += 1) {
      if (!(await this.imageStatus(params)).watchers.length) return;
      if (attempt < 5) await this.wait(1000);
    }
    throw new ExecutorError("IMAGE_IN_USE", "RBD image has an existing watcher");
  }

  async mapImage(params, record) {
    const state = await this.begin(record, "rbd.image.map", params); if (state.replay) return state.replay;
    const info = await this.assertLive(params, record); ensure(info.features.includes("exclusive-lock"), "FEATURE_MISMATCH", "RBD image lacks exclusive-lock");
    let mappings = await this.matchingMappings(params);
    if (!mappings.length) {
      await this.waitForNoWatchers(params);
      mappings = await this.matchingMappings(params);
      if (!mappings.length) {
        await this.run(["rbd", "device", "map", ...this.imageArgs(params), "--exclusive"], "rbd.image.map", { timeout: 60000 });
        mappings = await this.matchingMappings(params);
      }
    }
    ensure(mappings.length === 1, "MAPPING_IDENTITY_UNKNOWN", "Expected exactly one managed RBD mapping", { retryable: true });
    const observed = await this.observeMapping(mappings[0], params);
    Object.assign(record, { mapped: true, ...observed });
    return this.finish(record, params, { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: params.image_id, volume_id: params.volume_id, state: "MAPPED", ...observed });
  }

  async blkid(device, blankAllowed) {
    const result = await this.run(["blkid", "-p", "-o", "export", device], "rbd.device.blkid", { allowCodes: blankAllowed ? [0, 2] : [0] });
    if (result.code === 2) return {};
    return result.stdout.split(/\r?\n/).filter(Boolean).reduce((out, line) => { const at = line.indexOf("="); ensure(at > 0, "INVALID_CEPH_OUTPUT", "blkid output is invalid"); out[line.slice(0, at)] = line.slice(at + 1); return out; }, {});
  }

  async expectedMapping(params, record) {
    const mappings = await this.matchingMappings(params); ensure(mappings.length === 1, "MAPPING_IDENTITY_UNKNOWN", "Expected exactly one managed RBD mapping");
    const observed = await this.observeMapping(mappings[0], params);
    ensure(observed.device_major === params.device_major && observed.device_minor === params.device_minor, "DEVICE_IDENTITY_MISMATCH", "Device major:minor changed");
    if (record.device) ensure(record.device === observed.device, "DEVICE_IDENTITY_MISMATCH", "Mapped device path changed");
    return observed;
  }

  async findMountBySource(device) {
    const result = await this.run(["findmnt", "-J", "-S", device], "rbd.device.findmnt", { allowCodes: [0, 1] });
    if (result.code === 1 || !result.stdout.trim()) return null;
    const parsed = JSON.parse(result.stdout); const rows = parsed.filesystems || [];
    ensure(rows.length <= 1, "MOUNT_IDENTITY_CONFLICT", "Device has multiple mount entries");
    return rows[0] || null;
  }

  async findMountByTarget(target) {
    const result = await this.run(["findmnt", "-J", "-T", target], "rbd.device.findmnt", { allowCodes: [0, 1] });
    if (result.code === 1 || !result.stdout.trim()) return null;
    const parsed = JSON.parse(result.stdout); const row = (parsed.filesystems || [])[0] || null;
    return row?.target === target ? row : null;
  }

  mountpoint(volumeId) { return `${this.mountRoot}/${volumeId}`; }

  async formatExt4(params, record) {
    ensure(params.creation_action_id === record.creation_action_id, "CREATION_IDENTITY_MISMATCH", "Format is allowed only for the action that created this volume");
    const state = await this.begin(record, "rbd.device.format_ext4", params); if (state.replay) return state.replay;
    await this.assertLive(params, record); const observed = await this.expectedMapping(params, record);
    ensure(!(await this.findMountBySource(observed.device)), "VOLUME_BUSY", "RBD device is mounted");
    const existing = await this.blkid(observed.device, true);
    if (state.inProgress && existing.TYPE === "ext4" && existing.UUID) {
      record.formatted = true; record.filesystem = "ext4"; record.fs_uuid = existing.UUID;
    } else {
      ensure(!record.formatted && !Object.keys(existing).length, "FILESYSTEM_SIGNATURE_PRESENT", "Device already contains a filesystem signature");
      const wipe = await this.runJson(["wipefs", "-n", "--json", observed.device], "rbd.device.wipefs");
      ensure(wipe.signatures == null || (Array.isArray(wipe.signatures) && !wipe.signatures.length), "FILESYSTEM_SIGNATURE_PRESENT", "Device already contains a signature");
      const uid = (await this.runText(["id", "-u"], "executor.uid", { sudo: false })).trim();
      const gid = (await this.runText(["id", "-g"], "executor.gid", { sudo: false })).trim();
      ensure(/^\d+$/.test(uid) && /^\d+$/.test(gid), "EXECUTOR_IDENTITY_ERROR", "Could not determine SSH user identity");
      await this.run(["mkfs.ext4", "-m", "0", "-E", `root_owner=${uid}:${gid}`, observed.device], "rbd.device.format_ext4", { timeout: 120000 });
      const signature = await this.blkid(observed.device, false);
      ensure(signature.TYPE === "ext4" && validateUuid(signature.UUID, "filesystem UUID").ok, "FORMAT_VERIFY_FAILED", "New filesystem could not be verified as ext4");
      record.formatted = true; record.filesystem = "ext4"; record.fs_uuid = signature.UUID;
    }
    return this.finish(record, params, { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: params.image_id, volume_id: params.volume_id, state: "FORMATTED", filesystem: "ext4", fs_uuid: record.fs_uuid, ...observed });
  }

  async assertFilesystem(params, record, device) {
    ensure(record.formatted && record.fs_uuid === params.fs_uuid, "FILESYSTEM_IDENTITY_MISMATCH", "Filesystem does not match executor record");
    const signature = await this.blkid(device, false); ensure(signature.TYPE === "ext4" && signature.UUID === params.fs_uuid, "FILESYSTEM_IDENTITY_MISMATCH", "Observed filesystem identity changed");
  }

  async mount(params, record) {
    const state = await this.begin(record, "rbd.device.mount", params); if (state.replay) return state.replay;
    await this.assertLive(params, record); const observed = await this.expectedMapping(params, record); await this.assertFilesystem(params, record, observed.device);
    const target = this.mountpoint(params.volume_id); await this.run(["mkdir", "-p", target], "rbd.device.mkdir");
    const bySource = await this.findMountBySource(observed.device); const byTarget = await this.findMountByTarget(target);
    if (!bySource && (!byTarget || byTarget.target !== target)) await this.run(["mount", "-t", "ext4", "-o", "rw,nosuid,nodev", observed.device, target], "rbd.device.mount", { timeout: 60000 });
    const mounted = await this.findMountByTarget(target);
    ensure(mounted && mounted.target === target && mounted.source === observed.device && mounted.fstype === "ext4" && String(mounted.options || "").split(",").includes("rw"), "MOUNT_IDENTITY_MISMATCH", "Mounted filesystem identity does not match");
    await this.transport.probeFile(`${target}/.rgw-console-probe-${params.action_id}`, Buffer.from(params.action_id));
    record.mounted = true; record.mountpoint = target;
    return this.finish(record, params, { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: params.image_id, volume_id: params.volume_id, state: "MOUNTED", mountpoint: target, filesystem: "ext4", fs_uuid: params.fs_uuid, ...observed });
  }

  async unmount(params, record) {
    const state = await this.begin(record, "rbd.device.unmount", params); if (state.replay) return state.replay;
    await this.assertLive(params, record); const observed = await this.expectedMapping(params, record); await this.assertFilesystem(params, record, observed.device);
    const target = this.mountpoint(params.volume_id); const mounted = await this.findMountByTarget(target);
    if (mounted) {
      ensure(mounted.source === observed.device, "MOUNT_IDENTITY_CONFLICT", "Mountpoint belongs to another device");
      await this.run(["sync", "-f", target], "rbd.device.unmount.sync");
      try { await this.run(["umount", target], "rbd.device.unmount", { timeout: 60000 }); }
      catch (error) { if (String(error.details?.stderr || "").toLowerCase().includes("busy")) throw new ExecutorError("VOLUME_BUSY", "The volume is busy; unmount was refused"); throw error; }
    }
    ensure(!(await this.findMountByTarget(target)), "UNMOUNT_VERIFY_FAILED", "Mount is still present", { retryable: true });
    record.mounted = false;
    return this.finish(record, params, { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: params.image_id, volume_id: params.volume_id, state: "UNMOUNTED", mountpoint: target, ...observed });
  }

  async unmap(params, record) {
    const state = await this.begin(record, "rbd.device.unmap", params); if (state.replay) return state.replay;
    await this.assertLive(params, record); const mappings = await this.matchingMappings(params);
    let observed = { device: record.device, device_major: params.device_major, device_minor: params.device_minor };
    if (mappings.length) {
      ensure(mappings.length === 1, "MAPPING_IDENTITY_UNKNOWN", "Multiple matching mappings exist"); observed = await this.expectedMapping(params, record);
      ensure(!(await this.findMountBySource(observed.device)), "VOLUME_BUSY", "RBD device is mounted");
      await this.run(["rbd", "device", "unmap", observed.device], "rbd.device.unmap", { timeout: 60000 });
    }
    ensure(!(await this.matchingMappings(params)).length, "UNMAP_VERIFY_FAILED", "RBD mapping is still present", { retryable: true });
    record.mapped = false;
    return this.finish(record, params, { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: params.image_id, volume_id: params.volume_id, state: "UNMAPPED", ...observed });
  }

  async removeImage(params, record) {
    const state = await this.begin(record, "rbd.image.remove", params); if (state.replay) return state.replay;
    const info = await this.imageInfo(params, false);
    if (info) {
      ensure(info.image_id === params.image_id, "IMAGE_IDENTITY_MISMATCH", "Immutable RBD image ID changed");
      ensure(!(await this.matchingMappings(params)).length, "IMAGE_STILL_MAPPED", "RBD image is still mapped");
      ensure(!(await this.imageStatus(params)).watchers.length, "IMAGE_IN_USE", "RBD image still has watchers");
      const snapshots = await this.runJson(["rbd", "snap", "ls", ...this.imageArgs(params), "--format=json"], "rbd.image.remove.snapshots");
      const children = await this.runJson(["rbd", "children", ...this.imageArgs(params), "--format=json"], "rbd.image.remove.children");
      ensure(!snapshots.length && !children.length, "DEPENDENCY_EXISTS", "RBD image still has snapshots or clone dependencies");
      ensure(!(await this.findMountByTarget(this.mountpoint(params.volume_id))), "VOLUME_BUSY", "Managed mountpoint is still mounted");
      await this.run(["rbd", "rm", ...this.imageArgs(params)], "rbd.image.remove", { timeout: 120000 });
    }
    ensure(!(await this.imageInfo(params, false)), "DELETE_VERIFY_FAILED", "RBD image still exists", { retryable: true });
    const target = this.mountpoint(params.volume_id);
    try { await this.run(["rmdir", target], "rbd.mountpoint.cleanup", { sudo: false, allowCodes: [0, 1] }); } catch { /* image deletion is authoritative */ }
    record.deleted = true; record.mapped = false; record.mounted = false;
    return this.finish(record, params, { pool: params.pool, namespace: params.namespace, image_name: params.image_name, image_id: params.image_id, volume_id: params.volume_id, state: "DELETED" });
  }
}

export function validateRequest(body) {
  ensure(body && typeof body === "object" && !Array.isArray(body), "INVALID_REQUEST", "Request must be a JSON object");
  ensure(body.version === PROTOCOL_VERSION, "EXECUTOR_PROTOCOL_ERROR", "Unsupported executor protocol version");
  ensure(validateUuid(body.request_id, "request_id").ok, "INVALID_REQUEST", "request_id must be a UUID");
  ensure(typeof body.action === "string" && ALLOWED_ACTIONS.has(body.action), "ACTION_NOT_ALLOWED", "Action is not allowlisted");
  ensure(body.params && typeof body.params === "object" && !Array.isArray(body.params), "INVALID_REQUEST", "params must be a JSON object");
  ensure(Object.keys(body).every(key => ["version", "request_id", "action", "params"].includes(key)), "INVALID_REQUEST", "Request contains an unknown field");
  return body;
}

export function requestId() { return randomUUID(); }
