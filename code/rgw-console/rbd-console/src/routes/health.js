/**
 * Health and capability check routes.
 *
 * GET /api/rbd/ssh/health       — cluster health, FSID, connection status
 * GET /api/rbd/ssh/capabilities — check required tools on remote host
 */

import { Router } from "express";
import { exec, execJson, status as sshStatus } from "../ssh.js";

const router = Router();

router.get("/health", async (_req, res, next) => {
  try {
    const ssh = sshStatus();
    if (!ssh.connected) {
      return res.status(503).json({
        status: "disconnected",
        ssh,
        cluster: null,
        fsid_match: false,
        error: ssh.lastError || "SSH not connected",
      });
    }

    // Get cluster status
    let cluster = null;
    let fsid = null;
    let rbdVersion = null;
    let error = null;

    try {
      cluster = await execJson("ceph -s --format=json", { sudo: true });
    } catch (err) {
      error = `ceph -s failed: ${err.message}`;
    }

    try {
      const fsidResult = await exec("ceph fsid", { sudo: true });
      fsid = fsidResult.stdout.trim();
    } catch (err) {
      error = error || `ceph fsid failed: ${err.message}`;
    }

    try {
      const versionResult = await exec("rbd --version", { sudo: true });
      rbdVersion = versionResult.stdout.trim();
    } catch (err) {
      error = error || `rbd --version failed: ${err.message}`;
    }

    const expectedFsid = process.env.CEPH_EXPECTED_FSID;
    const fsidMatch = expectedFsid ? fsid === expectedFsid : null;

    // Extract health summary
    const health = cluster?.health?.status || null;
    const osdMap = cluster?.osdmap?.osdmap || cluster?.osdmap || null;

    res.json({
      status: health === "HEALTH_OK" && fsidMatch !== false ? "ok" : "degraded",
      ssh: { connected: ssh.connected, host: ssh.host, user: ssh.user },
      cluster: {
        health,
        fsid,
        fsid_match: fsidMatch,
        num_osds: osdMap?.num_osds ?? null,
        num_up_osds: osdMap?.num_up_osds ?? null,
        num_in_osds: osdMap?.num_in_osds ?? null,
      },
      rbd_version: rbdVersion,
      pool: process.env.RBD_POOL || null,
      mount_root: process.env.RBD_MOUNT_ROOT || null,
      error,
    });
  } catch (err) {
    next(err);
  }
});

router.get("/capabilities", async (_req, res, next) => {
  try {
    const ssh = sshStatus();
    if (!ssh.connected) {
      return res.status(503).json({ connected: false, tools: {} });
    }

    const tools = ["rbd", "ceph", "mkfs.ext4", "mount", "umount", "blkid", "wipefs", "findmnt", "sync"];
    const checks = {};

    for (const tool of tools) {
      try {
        const result = await exec(`which ${tool} 2>/dev/null`);
        checks[tool] = {
          available: result.code === 0,
          path: result.stdout.trim() || null,
        };
      } catch {
        checks[tool] = { available: false, path: null };
      }
    }

    // Check SFTP availability
    let sftp = false;
    try {
      // If SSH works, SFTP subsystem should also work
      sftp = ssh.connected;
    } catch {
      sftp = false;
    }

    // Check mount root exists
    let mountRootExists = false;
    const mountRoot = process.env.RBD_MOUNT_ROOT || "/mnt/rbd";
    try {
      const result = await exec(`test -d ${mountRoot} && echo yes || echo no`);
      mountRootExists = result.stdout.trim() === "yes";
    } catch {
      mountRootExists = false;
    }

    res.json({
      connected: true,
      tools: checks,
      sftp,
      mount_root: mountRoot,
      mount_root_exists: mountRootExists,
      all_required: Object.values(checks).every(c => c.available) && mountRootExists,
    });
  } catch (err) {
    next(err);
  }
});

export default router;
