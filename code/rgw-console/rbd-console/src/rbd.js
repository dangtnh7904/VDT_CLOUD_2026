/**
 * RBD image and device helpers.
 *
 * Wraps SSH commands for rbd ls, info, device list and parses output
 * into structured objects for the API layer.
 */

import { exec, execJson } from "./ssh.js";
import { validatePool, validateImageName, safeCommand } from "./validators.js";

/**
 * List all images in a pool.
 * @param {string} [pool] - Pool name; defaults to RBD_POOL env.
 * @returns {Promise<string[]>} Array of image names.
 */
export async function listImages(pool) {
  pool = pool || process.env.RBD_POOL || "rbd-lab";
  const check = validatePool(pool);
  if (!check.ok) throw new Error(check.error);

  const cmd = safeCommand(["rbd", "ls", pool, "--format=json"]);
  try {
    return await execJson(cmd, { sudo: true });
  } catch (err) {
    // rbd ls returns empty string for empty pool
    if (err.message.includes("Invalid JSON")) return [];
    throw err;
  }
}

/**
 * Get detailed info for a single image.
 * @param {string} name - Image name.
 * @param {string} [pool] - Pool name.
 * @returns {Promise<object>}
 */
export async function imageInfo(name, pool) {
  pool = pool || process.env.RBD_POOL || "rbd-lab";
  const poolCheck = validatePool(pool);
  if (!poolCheck.ok) throw new Error(poolCheck.error);
  const nameCheck = validateImageName(name);
  if (!nameCheck.ok) throw new Error(nameCheck.error);

  const spec = `${pool}/${name}`;
  const cmd = safeCommand(["rbd", "info", spec, "--format=json"]);
  return execJson(cmd, { sudo: true });
}

/**
 * List all images with detailed info.
 * @param {string} [pool]
 * @returns {Promise<object[]>}
 */
export async function listImagesDetailed(pool) {
  const names = await listImages(pool);
  const mountRoot = process.env.RBD_MOUNT_ROOT || "/mnt/rbd";

  // Get mapped devices and mount state in parallel
  const [devices, mounts] = await Promise.all([
    listDevices(),
    getMounts(mountRoot),
  ]);

  const images = await Promise.all(
    names.map(async (name) => {
      try {
        const info = await imageInfo(name, pool);
        const device = devices.find(d => d.name === name && d.pool === (pool || process.env.RBD_POOL));
        const mountpoint = device ? mounts[device.device] || null : null;

        return {
          name,
          pool: pool || process.env.RBD_POOL,
          size: info.size,
          objects: info.objects,
          order: info.order,
          object_size: info.object_size,
          block_name_prefix: info.block_name_prefix,
          format: info.format,
          features: info.features,
          id: info.id,
          device: device?.device || null,
          mapped: !!device,
          mountpoint,
          mounted: !!mountpoint,
          state: mountpoint ? "MOUNTED" : device ? "MAPPED" : "UNMAPPED",
        };
      } catch (err) {
        return {
          name,
          pool: pool || process.env.RBD_POOL,
          state: "ERROR",
          error: err.message,
        };
      }
    })
  );

  return images;
}

/**
 * List currently mapped RBD devices.
 * @returns {Promise<object[]>}
 */
export async function listDevices() {
  const cmd = "rbd device list --format=json";
  try {
    const raw = await execJson(cmd, { sudo: true });
    // rbd device list returns array of {id, pool, namespace, name, snap, device}
    return Array.isArray(raw) ? raw : [];
  } catch (err) {
    if (err.message.includes("Invalid JSON")) return [];
    throw err;
  }
}

/**
 * Get mount state for devices under a root path.
 * Returns a map of device -> mountpoint.
 * @param {string} mountRoot
 * @returns {Promise<Record<string, string>>}
 */
async function getMounts(mountRoot) {
  try {
    const result = await exec(`findmnt -J -T ${mountRoot} --submounts 2>/dev/null || findmnt -J -l -t ext4 2>/dev/null || echo "{}"`);
    const mounts = {};
    if (result.stdout.trim()) {
      try {
        const data = JSON.parse(result.stdout);
        const list = data.filesystems || [];
        for (const fs of list) {
          if (fs.source?.startsWith("/dev/rbd") || fs.target?.startsWith(mountRoot)) {
            mounts[fs.source] = fs.target;
          }
          // Also check children
          for (const child of fs.children || []) {
            if (child.source?.startsWith("/dev/rbd") || child.target?.startsWith(mountRoot)) {
              mounts[child.source] = child.target;
            }
          }
        }
      } catch {
        // findmnt JSON parse failure — return empty
      }
    }
    return mounts;
  } catch {
    return {};
  }
}
