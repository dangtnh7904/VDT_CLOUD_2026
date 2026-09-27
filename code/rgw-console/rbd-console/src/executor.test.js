import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import { SshExecutor, validateRequest } from "./executor.js";
import { ExecutorError } from "./errors.js";
import { VolumeStateStore } from "./state.js";
import { redactCmd } from "./ssh.js";
import { validateFilePath, validateMountPath } from "./validators.js";

const FSID = "17c77e12-a16a-11f1-838e-cf68e9c001d8";
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
  constructor() { this.image = false; this.mapped = false; this.formatted = false; this.mounted = false; }
  async probeFile() { assert.equal(this.mounted, true); }
  async exec(command) {
    const ok = stdout => ({ code: 0, stdout, stderr: "" });
    if (command === "ceph fsid") return ok(`${FSID}\n`);
    if (command.includes("ceph status --format=json")) return ok('{"health":{"status":"HEALTH_OK"}}');
    if (command.includes("ceph osd df --format=json")) return ok('{"nodes":[]}');
    if (command.includes("ceph osd tree --format=json")) return ok('{"nodes":[]}');
    if (command.includes("ceph osd pool ls detail --format=json")) return ok('[]');
    if (command.includes("ceph osd crush rule dump --format=json")) return ok('[]');
    if (command.includes("ceph osd pool ls --format=json")) return ok('["rbd-lab","other"]');
    if (command.includes("rbd info")) return this.image ? ok(JSON.stringify({ id: IMAGE_ID, size: 1073741824, features: ["layering", "exclusive-lock"] })) : { code: 2, stdout: "", stderr: "No such file or directory" };
    if (command.includes("rbd create")) { this.image = true; return ok(""); }
    if (command.includes("rbd status")) return ok('{"watchers":[]}');
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
  process.env.CEPH_EXPECTED_FSID = FSID;
  process.env.RBD_ALLOWED_POOLS = "rbd-lab";
  process.env.RBD_ALLOWED_NAMESPACES = "default";
  process.env.RBD_IMAGE_PREFIX = "lab-";
  process.env.RBD_MOUNT_ROOT = "/mnt/rbd";
}

function params(actionId, fence, extra = {}) {
  return { volume_id: VOLUME, action_id: actionId, fence_token: fence, pool: "rbd-lab", namespace: "", image_name: "lab-test", ...extra };
}

test("closed protocol rejects unknown fields and actions", () => {
  assert.throws(() => validateRequest({ version: 1, request_id: CREATE, action: "shell", params: {} }), ExecutorError);
  assert.throws(() => validateRequest({ version: 1, request_id: CREATE, action: "health", params: {}, extra: true }), ExecutorError);
});

test("path validators reject traversal and prefix confusion", () => {
  env();
  assert.equal(validateMountPath("../escape").ok, false);
  assert.equal(validateFilePath("lab-test", "../../escape").ok, false);
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
