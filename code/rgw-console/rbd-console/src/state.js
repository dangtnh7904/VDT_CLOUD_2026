import { mkdir, open, readFile, rename, rm } from "fs/promises";
import { dirname, join } from "path";
import { randomUUID } from "crypto";

export class VolumeStateStore {
  constructor(root = process.env.RBD_EXECUTOR_STATE_ROOT || "/var/lib/rbd-executor") {
    this.root = root;
    this.locks = new Map();
  }

  path(volumeId) {
    return join(this.root, `${volumeId}.json`);
  }

  async load(volumeId) {
    try {
      const parsed = JSON.parse(await readFile(this.path(volumeId), "utf8"));
      if (!parsed || parsed.volume_id !== volumeId) throw new Error("state identity mismatch");
      return parsed;
    } catch (error) {
      if (error?.code === "ENOENT") return null;
      throw error;
    }
  }

  async save(record) {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    const target = this.path(record.volume_id);
    const temp = join(dirname(target), `.${record.volume_id}.${randomUUID()}.tmp`);
    const handle = await open(temp, "wx", 0o600);
    try {
      await handle.writeFile(JSON.stringify(record));
      await handle.sync();
    } finally {
      await handle.close();
    }
    try {
      await rename(temp, target);
    } finally {
      await rm(temp, { force: true });
    }
  }

  async withLock(volumeId, fn) {
    const previous = this.locks.get(volumeId) || Promise.resolve();
    let release;
    const current = new Promise(resolve => { release = resolve; });
    const queued = previous.then(() => current);
    this.locks.set(volumeId, queued);
    await previous;
    try {
      return await fn();
    } finally {
      release();
      if (this.locks.get(volumeId) === queued) this.locks.delete(volumeId);
    }
  }
}
