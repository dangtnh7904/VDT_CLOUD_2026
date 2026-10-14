import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import { ALLOWED_ACTIONS, READ_ONLY_ACTIONS, SshExecutor, executorPolicy, validateRequest } from "./executor.js";
import { ExecutorError } from "./errors.js";
import { VolumeStateStore } from "./state.js";
import { redactCmd } from "./ssh.js";
import { validateFilePath, validateMountPath } from "./validators.js";

const FSID = "17c77e12-a16a-11f1-838e-cf68e9c001d8";

test("environment evidence uses the fixed unprivileged helper, bounded output and no caller command", async () => {
  env();
  process.env.CONSOLE_READ_ONLY = "true";
  process.env.OSD_INFO_COLLECTOR_RUN_AS_SSH_USER = "true";
  const commands = [];
  const transport = { async exec(command, options) {
    commands.push(command);
    if (command === "ceph fsid") return { code: 0, stdout: FSID, stderr: "" };
    assert.equal(command, "python3 /opt/storage-lab/collect_osd.py --environment-only --sudo-ceph --timeout 2");
    assert.equal(options.sudo, false);
    assert.equal(options.timeout, 20000);
    assert.equal(options.maxOutputBytes, 1048576);
    return { code: 0, stdout: JSON.stringify({ kind: "CEPH_CLIENT_ENVIRONMENT", scope: "SSH_CLIENT_HOST_ONLY" }), stderr: "" };
  } };
  try {
    const executor = new SshExecutor({ transport });
    await assert.rejects(() => executor.dispatch("ceph.client_environment", { command: "rm" }), e => e.code === "INVALID_REQUEST");
    assert.deepEqual(commands, []);
    const result = await executor.dispatch("ceph.client_environment");
    assert.equal(result.data.scope, "SSH_CLIENT_HOST_ONLY");
    assert.equal(commands.filter(x => x === "ceph fsid").length, 2);
  } finally {
    process.env.CONSOLE_READ_ONLY = "false";
    delete process.env.OSD_INFO_COLLECTOR_RUN_AS_SSH_USER;
  }
});

test("CephFS map is a fixed read-only action and rejects caller arguments", async () => {
  env(); process.env.CONSOLE_READ_ONLY = "true";
  const commands = [];
  const transport = { async exec(command) {
    commands.push(command);
    if (command === "ceph fsid") return { code: 0, stdout: FSID, stderr: "" };
    assert.equal(command, "ceph fs dump --format=json");
    return { code: 0, stdout: '{"epoch":1,"filesystems":[],"standbys":[]}', stderr: "" };
  } };
  try {
    const executor = new SshExecutor({ transport });
    await assert.rejects(() => executor.dispatch("ceph.fs_dump", { epoch: 2 }), e => e.code === "INVALID_REQUEST");
    assert.deepEqual(commands, []);
    const result = await executor.dispatch("ceph.fs_dump");
    assert.deepEqual(result.data.filesystems, []);
  } finally { process.env.CONSOLE_READ_ONLY = "false"; }
});

test("OSDMap export is a fixed binary read, rejects caller paths and verifies FSID twice", async () => {
  env();
  process.env.CONSOLE_READ_ONLY = "true";
  const commands = [];
  const raw = Buffer.from([0, 255, 128, 65]);
  const transport = { async exec(command, options) {
    commands.push(command);
    if (command === "ceph fsid") return { code: 0, stdout: FSID, stderr: "" };
    assert.equal(command, "ceph osd getmap -o /dev/stdout");
    assert.equal(options.binary, true);
    return { code: 0, stdout: raw, stderr: "" };
  } };
  const executor = new SshExecutor({ transport });
  await assert.rejects(() => executor.dispatch("ceph.osd_map_export", { path: "/other" }), e => e.code === "INVALID_REQUEST");
  assert.deepEqual(commands, []);
  const result = await executor.dispatch("ceph.osd_map_export");
  assert.deepEqual(Buffer.from(result.data.map, "base64"), raw);
  assert.equal(commands.filter(x => x === "ceph fsid").length, 2);
  process.env.CONSOLE_READ_ONLY = "false";
});
const VOLUME = "11111111-1111-4111-8111-111111111111";
const CREATE = "22222222-2222-4222-8222-222222222222";
const IDS = [
  CREATE,
  "33333333-3333-4333-8333-333333333333",
  "44444444-4444-4444-8444-444444444444",
  "55555555-5555-4555-8555-555555555555",
  "66666666-6666-4666-8666-666666666666",
  "77777777-7777-4777-8777-777777777777",
  "88888888-8888-4888-8888-888888888888",
];
const IMAGE_ID = "1a2b3c";
const FS_UUID = "99999999-9999-4999-8999-999999999999";

class FakeTransport {
  constructor() { this.image = false; this.mapped = false; this.formatted = false; this.mounted = false; this.watcherReadsRemaining = 0; this.persistentWatcher = false; this.statusReads = 0; this.commands = []; }
  async probeFile() { assert.equal(this.mounted, true); }
  async exec(command) {
    this.commands.push(command);
    const ok = stdout => ({ code: 0, stdout, stderr: "" });
    if (command === "ceph fsid") return ok(`${FSID}\n`);
    if (command.startsWith("python3 /opt/storage-lab/collect_osd.py ")) return ok(JSON.stringify({
      schema_version: 1, kind: "CEPH_OSD_BASELINE", collector_version: "1.0.2",
      collection_id: CREATE, collected_at: "2026-10-08T00:00:00Z",
      cluster_fsid: FSID, quality: "VALID", errors: [], osd_count: 2, osds: [],
      cluster_evidence: {},
    }));
    if (command.includes("ceph status --format=json")) return ok('{"health":{"status":"HEALTH_OK"}}');
    if (command.includes("ceph osd df --format=json")) return ok('{"nodes":[]}');
    if (command.includes("ceph osd tree --format=json")) return ok('{"nodes":[]}');
    if (command.includes("ceph osd pool ls detail --format=json")) return ok('[]');
    if (command.includes("ceph osd crush rule dump --format=json")) return ok('[]');
    if (command.includes("ceph osd pool ls --format=json")) return ok('["rbd-lab","other"]');
    if (command.includes("rbd info")) return this.image ? ok(JSON.stringify({ id: IMAGE_ID, size: 1073741824, features: ["layering", "exclusive-lock"] })) : { code: 2, stdout: "", stderr: "No such file or directory" };
    if (command.includes("rbd create")) { this.image = true; return ok(""); }
    if (command.includes("rbd status")) {
      this.statusReads += 1;
      const watched = this.persistentWatcher || this.watcherReadsRemaining > 0;
      if (this.watcherReadsRemaining > 0) this.watcherReadsRemaining -= 1;
      return ok(JSON.stringify({ watchers: watched ? [{ address: "client" }] : [] }));
    }
    if (command.includes("rbd device list")) return ok(this.mapped ? JSON.stringify([{ id: 0, pool: "rbd-lab", namespace: "", name: "lab-test", image_id: IMAGE_ID, device: "/dev/rbd0" }]) : "[]");
    if (command.includes("rbd device map")) { this.mapped = true; return ok("/dev/rbd0\n"); }
    if (command.includes("stat -Lc")) return ok("fb:0\n");
    if (command.endsWith("/pool")) return ok("rbd-lab\n");
    if (command.endsWith("/name")) return ok("lab-test\n");
    if (command.endsWith("/image_id")) return ok(`${IMAGE_ID}\n`);
    if (command.includes("findmnt -J -S")) return this.mounted ? ok('{"filesystems":[{"source":"/dev/rbd0","target":"/mnt/rbd/11111111-1111-4111-8111-111111111111","fstype":"ext4","options":"rw,nosuid,nodev"}]}') : { code: 1, stdout: "", stderr: "" };
    if (command.includes("findmnt -J -T")) return this.mounted ? ok('{"filesystems":[{"source":"/dev/rbd0","target":"/mnt/rbd/11111111-1111-4111-8111-111111111111","fstype":"ext4","options":"rw,nosuid,nodev"}]}') : { code: 1, stdout: "", stderr: "" };
    if (command.includes("blkid -p")) return this.formatted ? ok(`TYPE=ext4\nUUID=${FS_UUID}\n`) : { code: 2, stdout: "", stderr: "" };
    if (command.includes("wipefs -n")) return ok('{"signatures":null}');
    if (command.endsWith("id -u")) return ok("1000\n");
    if (command.endsWith("id -g")) return ok("1000\n");
    if (command.includes("mkfs.ext4")) { this.formatted = true; return ok(""); }
    if (command.startsWith("mkdir -p ")) return ok("");
    if (command.startsWith("mount -t ")) { this.mounted = true; return ok(""); }
    if (command.startsWith("sync -f ")) return ok("");
    if (command.startsWith("umount ")) { this.mounted = false; return ok(""); }
    if (command.includes("rbd device unmap")) { this.mapped = false; return ok(""); }
    if (command.includes("rbd snap ls") || command.includes("rbd children")) return ok("[]");
    if (command.includes("rbd rm")) { this.image = false; return ok(""); }
    if (command.startsWith("rmdir ")) return ok("");
    throw new Error(`Unexpected fake command: ${command}`);
  }
}

function env() {
  process.env.APP_ENV = "lab";
  process.env.CONSOLE_READ_ONLY = "false";
  process.env.CEPH_EXPECTED_FSID = FSID;
  process.env.RBD_ALLOWED_POOLS = "rbd-lab";
  process.env.RBD_ALLOWED_NAMESPACES = "default";
  process.env.RBD_IMAGE_PREFIX = "lab-";
  process.env.RBD_MOUNT_ROOT = "/mnt/rbd";
  process.env.UPGRADE_ALLOWED_OSDS = "0,4";
  process.env.OSD_INFO_COLLECTOR_PATH = "/opt/storage-lab/collect_osd.py";
}

function params(actionId, fence, extra = {}) {
  return { volume_id: VOLUME, action_id: actionId, fence_token: fence, pool: "rbd-lab", namespace: "", image_name: "lab-test", ...extra };
}

test("closed protocol rejects unknown fields and actions", () => {
  assert.throws(() => validateRequest({ version: 1, request_id: CREATE, action: "shell", params: {} }), ExecutorError);
  assert.throws(() => validateRequest({ version: 1, request_id: CREATE, action: "health", params: {}, extra: true }), ExecutorError);
});

test("retired benchmark actions cannot reach SSH even in writable lab mode", async () => {
  env();
  let accesses = 0;
  const forbidden = () => { accesses += 1; throw new Error("No access allowed"); };
  const executor = new SshExecutor({
    transport: { exec: forbidden }, store: { withLock: forbidden },
  });
  for (const action of ["benchmark.preflight", "benchmark.start", "benchmark.status", "benchmark.stop"]) {
    await assert.rejects(() => executor.dispatch(action, {}), error => error.code === "ACTION_NOT_ALLOWED");
  }
  assert.equal(accesses, 0);
});

test("production policy requires the read-only profile and rejects conflicting mutation flags", () => {
  for (const config of [
    { APP_ENV: "production" },
    { APP_ENV: "production", CONSOLE_READ_ONLY: "false" },
    { APP_ENV: "production", CONSOLE_READ_ONLY: "true", UPGRADE_MUTATIONS_ENABLED: "true" },
    { APP_ENV: "production", CONSOLE_READ_ONLY: "true", RBD_TERMINAL_ENABLED: "true" },
    { CONSOLE_READ_ONLY: "maybe" },
  ]) assert.throws(() => executorPolicy(config), error => error.code === "EXECUTOR_NOT_CONFIGURED");
  assert.deepEqual(executorPolicy({ APP_ENV: "production", CONSOLE_READ_ONLY: "true" }), { readOnly: true });
  assert.deepEqual(executorPolicy({ APP_ENV: "lab" }), { readOnly: false });
});

test("read-only dispatch rejects every excluded action before SSH, state or ticket access", async () => {
  env(); process.env.CONSOLE_READ_ONLY = "true";
  let accesses = 0;
  const forbidden = () => { accesses += 1; throw new Error("No state/SSH access is allowed"); };
  try {
    const executor = new SshExecutor({
      transport: { exec: forbidden, openSftp: forbidden, openShell: forbidden },
      store: { load: forbidden, save: forbidden, withLock: forbidden },
      tickets: { issue: forbidden, consume: forbidden },
    });
    for (const action of ALLOWED_ACTIONS) {
      if (!READ_ONLY_ACTIONS.has(action)) await assert.rejects(
        () => executor.dispatch(action, {}),
        error => error.code === "CONSOLE_READ_ONLY" && error.status === 403,
        action,
      );
    }
    for (const operation of [
      () => executor.downloadFile({}), () => executor.uploadFile({}),
      () => executor.issueTerminalTicket({}), () => executor.terminalContext({}),
      () => executor.manifestFiles({}), () => executor.mutate("rbd.image.create", {}),
      () => executor.createImage({}),
    ]) await assert.rejects(operation, error => error.code === "CONSOLE_READ_ONLY");
    assert.throws(() => executor.consumeTerminalTicket("existing-valid-ticket"), error => error.code === "CONSOLE_READ_ONLY");
    assert.equal(accesses, 0);
  } finally { env(); }
});

test("read-only capabilities expose only inventory and collection; allowed aggregates remain FSID-bound", async () => {
  env(); process.env.CONSOLE_READ_ONLY = "true";
  const transport = new FakeTransport();
  const forbidden = () => { throw new Error("Read-only inventory cannot access volume state"); };
  try {
    const executor = new SshExecutor({ transport, store: { withLock: forbidden, save: forbidden, load: forbidden } });
    const capabilities = await executor.dispatch("capabilities");
    assert.equal(capabilities.read_only, true);
    assert.deepEqual(capabilities.actions, [...READ_ONLY_ACTIONS].sort());
    assert.equal(capabilities.rbd_scope.file_browser, false);
    assert.equal(capabilities.rbd_scope.terminal, false);
    assert.equal((await executor.dispatch("ceph.capacity_inventory")).fsid, FSID);
    assert.equal((await executor.dispatch("ceph.osd_info_collect", { osd_ids: [0, 4] })).data.kind, "CEPH_OSD_BASELINE");
    assert.ok(transport.commands.every(command => command.startsWith("ceph ") || command.startsWith("python3 /opt/storage-lab/collect_osd.py ")));
  } finally { env(); }
});

test("path validators reject traversal and prefix confusion", () => {
  env();
  assert.equal(validateMountPath("../escape").ok, false);
  assert.equal(validateFilePath("lab-test", "../../escape").ok, false);
});

test("daemon inventory uses fixed FSID-bound read commands and rejects extra params before SSH", async () => {
  env(); process.env.CONSOLE_READ_ONLY = "true";
  const commands = [];
  const ok = stdout => ({ code: 0, stdout, stderr: "" });
  const transport = { exec: async command => {
    commands.push(command);
    if (command === "ceph fsid") return ok(FSID);
    if (command === "ceph mon dump --format=json") return ok('{"epoch":4,"mons":[{"name":"a","rank":0}]}');
    if (command === "ceph mgr dump --format=json") return ok('{"active_name":"mgr-a","available":true}');
    if (command === "ceph mgr services --format=json") return ok('{"prometheus":"http://mgr-a:9283/"}');
    throw new Error("Unexpected command");
  } };
  try {
    const executor = new SshExecutor({ transport });
    const mon = await executor.dispatch("ceph.mon_dump");
    assert.equal(mon.fsid, FSID);
    assert.equal(mon.data.mons[0].name, "a");
    assert.equal((await executor.dispatch("ceph.mgr_dump")).data.active_name, "mgr-a");
    const services = await executor.dispatch("ceph.mgr_services");
    assert.equal(services.fsid, FSID);
    assert.equal(services.data.prometheus, "http://mgr-a:9283/");
    const before = commands.length;
    await assert.rejects(() => executor.dispatch("ceph.mon_dump", { command: "ceph auth export" }), error => error.code === "INVALID_REQUEST");
    await assert.rejects(() => executor.dispatch("ceph.mgr_services", { command: "ceph mgr fail mgr-a" }), error => error.code === "INVALID_REQUEST");
    assert.equal(commands.length, before);
  } finally { env(); }
});

test("redaction removes key material from command errors", () => {
  assert.equal(redactCmd("ceph --key secret --keyring /secret/path"), "ceph --key [REDACTED] --keyring [REDACTED]");
});

test("read-only inventory is allowlist-filtered and FSID-bound", async () => {
  env(); const root = await mkdtemp(join(tmpdir(), "rbd-executor-"));
  try {
    const executor = new SshExecutor({ transport: new FakeTransport(), store: new VolumeStateStore(root) });
    const result = await executor.dispatch("rbd.pool.list", {});
    assert.deepEqual(result.data.pools, ["rbd-lab"]);
    process.env.CEPH_EXPECTED_FSID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const mismatched = new SshExecutor({ transport: new FakeTransport(), store: new VolumeStateStore(root) });
    await assert.rejects(() => mismatched.dispatch("health", {}), error => error.code === "FSID_MISMATCH");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("capacity inventory is captured in one FSID-bound executor request", async () => {
  env(); const root = await mkdtemp(join(tmpdir(), "rbd-executor-"));
  try {
    const executor = new SshExecutor({ transport: new FakeTransport(), store: new VolumeStateStore(root) });
    const result = await executor.dispatch("ceph.capacity_inventory", {});
    assert.equal(result.action, "ceph.capacity_inventory");
    assert.deepEqual(Object.keys(result.data).sort(), ["crush_rules", "osd_df", "osd_tree", "pool_details", "status_after", "status_before"]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("OSD info collector uses fixed argv and enforces the executor allowlist", async () => {
  env(); const root = await mkdtemp(join(tmpdir(), "rbd-executor-"));
  try {
    const transport = new FakeTransport();
    const executor = new SshExecutor({ transport, store: new VolumeStateStore(root) });
    const result = await executor.dispatch("ceph.osd_info_collect", { osd_ids: [0, 4] });
    assert.equal(result.data.kind, "CEPH_OSD_BASELINE");
    assert.ok(transport.commands.includes(
      "python3 /opt/storage-lab/collect_osd.py --osd 0 --osd 4 --timeout 45",
    ));
    await assert.rejects(
      () => executor.dispatch("ceph.osd_info_collect", { osd_ids: [9] }),
      error => error.code === "SCOPE_NOT_ALLOWED",
    );
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("restricted SSH user runs collector without sudo Python and retains fixed sudo Ceph argv", async () => {
  env(); process.env.UPGRADE_ALLOWED_OSDS = "2,5";
  process.env.OSD_INFO_COLLECTOR_RUN_AS_SSH_USER = "true";
  const calls = [];
  const transport = { exec: async (command, options) => {
    calls.push({ command, options });
    return { code: 0, stderr: "", stdout: command.includes("python3") ? JSON.stringify({ cluster_fsid: FSID, osds: [] }) : FSID };
  }};
  try {
    await new SshExecutor({ transport }).dispatch("ceph.osd_info_collect", { osd_ids: [2,5] });
    const collector = calls.find(call => call.command.includes("python3"));
    assert.equal(collector.options.sudo, false);
    assert.match(collector.command, /--sudo-ceph/);
  } finally { delete process.env.OSD_INFO_COLLECTOR_RUN_AS_SSH_USER; }
});

test("complete PR7 lifecycle is fenced, verified, replayable, and cleaned", async () => {
  env(); const root = await mkdtemp(join(tmpdir(), "rbd-executor-")); const transport = new FakeTransport();
  try {
    const executor = new SshExecutor({ transport, store: new VolumeStateStore(root) });
    const createParams = params(IDS[0], 1, { size_bytes: 1073741824 });
    const created = await executor.dispatch("rbd.image.create", createParams); assert.equal(created.data.state, "CREATED");
    const replay = await executor.dispatch("rbd.image.create", createParams); assert.equal(replay.data.replayed, true);
    const mapped = await executor.dispatch("rbd.image.map", params(IDS[1], 2, { image_id: IMAGE_ID })); assert.equal(mapped.data.device_major, 251);
    const formatted = await executor.dispatch("rbd.device.format_ext4", params(IDS[2], 3, { image_id: IMAGE_ID, creation_action_id: CREATE, device_major: 251, device_minor: 0 })); assert.equal(formatted.data.fs_uuid, FS_UUID);
    const mounted = await executor.dispatch("rbd.device.mount", params(IDS[3], 4, { image_id: IMAGE_ID, device_major: 251, device_minor: 0, fs_uuid: FS_UUID })); assert.equal(mounted.data.state, "MOUNTED");
    executor.beginAccessSession(VOLUME);
    await assert.rejects(
      () => executor.dispatch("rbd.device.unmount", params(IDS[4], 5, { image_id: IMAGE_ID, device_major: 251, device_minor: 0, fs_uuid: FS_UUID })),
      error => error.code === "VOLUME_BUSY",
    );
    executor.endAccessSession(VOLUME);
    const unmounted = await executor.dispatch("rbd.device.unmount", params(IDS[4], 5, { image_id: IMAGE_ID, device_major: 251, device_minor: 0, fs_uuid: FS_UUID })); assert.equal(unmounted.data.state, "UNMOUNTED");
    const unmapped = await executor.dispatch("rbd.device.unmap", params(IDS[5], 6, { image_id: IMAGE_ID, device_major: 251, device_minor: 0 })); assert.equal(unmapped.data.state, "UNMAPPED");
    const deleted = await executor.dispatch("rbd.image.remove", params(IDS[6], 7, { image_id: IMAGE_ID })); assert.equal(deleted.data.state, "DELETED");
    assert.equal(transport.image, false); assert.equal(transport.mapped, false); assert.equal(transport.mounted, false);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("map waits for a watcher left briefly after unmap", async () => {
  env(); const root = await mkdtemp(join(tmpdir(), "rbd-executor-")); const transport = new FakeTransport();
  try {
    const executor = new SshExecutor({ transport, store: new VolumeStateStore(root), wait: async () => {} });
    await executor.dispatch("rbd.image.create", params(IDS[0], 1, { size_bytes: 1073741824 }));
    transport.watcherReadsRemaining = 2;
    const mapped = await executor.dispatch("rbd.image.map", params(IDS[1], 2, { image_id: IMAGE_ID }));
    assert.equal(mapped.data.state, "MAPPED");
    assert.equal(transport.statusReads, 3);
    assert.equal(transport.mapped, true);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("map refuses a persistent watcher without mapping the image", async () => {
  env(); const root = await mkdtemp(join(tmpdir(), "rbd-executor-")); const transport = new FakeTransport();
  try {
    const executor = new SshExecutor({ transport, store: new VolumeStateStore(root), wait: async () => {} });
    await executor.dispatch("rbd.image.create", params(IDS[0], 1, { size_bytes: 1073741824 }));
    transport.persistentWatcher = true;
    await assert.rejects(
      () => executor.dispatch("rbd.image.map", params(IDS[1], 2, { image_id: IMAGE_ID })),
      error => error.code === "IMAGE_IN_USE",
    );
    assert.equal(transport.statusReads, 6);
    assert.equal(transport.mapped, false);
  } finally { await rm(root, { recursive: true, force: true }); }
});
