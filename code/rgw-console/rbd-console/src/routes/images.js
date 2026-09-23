/**
 * RBD image routes (read-only for PR6).
 *
 * GET /api/rbd/images          — list all images with state
 * GET /api/rbd/images/:name    — detailed info for one image
 */

import { Router } from "express";
import { listImagesDetailed, imageInfo, listDevices } from "../rbd.js";
import { validateImageName } from "../validators.js";
import { status as sshStatus } from "../ssh.js";

const router = Router();

router.get("/", async (req, res, next) => {
  try {
    const ssh = sshStatus();
    if (!ssh.connected) {
      return res.status(503).json({ error: "SSH not connected", code: "SSH_DISCONNECTED" });
    }

    const pool = process.env.RBD_POOL || "rbd-lab";
    const images = await listImagesDetailed(pool);

    res.json({
      pool,
      count: images.length,
      items: images,
    });
  } catch (err) {
    next(err);
  }
});

router.get("/:name", async (req, res, next) => {
  try {
    const ssh = sshStatus();
    if (!ssh.connected) {
      return res.status(503).json({ error: "SSH not connected", code: "SSH_DISCONNECTED" });
    }

    const { name } = req.params;
    const nameCheck = validateImageName(name);
    if (!nameCheck.ok) {
      return res.status(422).json({ error: nameCheck.error, code: "INVALID_SCOPE" });
    }

    const pool = process.env.RBD_POOL || "rbd-lab";
    const info = await imageInfo(name, pool);

    // Get device/mount state
    const devices = await listDevices();
    const device = devices.find(d => d.name === name && d.pool === pool);

    res.json({
      ...info,
      pool,
      device: device?.device || null,
      mapped: !!device,
      state: device ? "MAPPED" : "UNMAPPED",
    });
  } catch (err) {
    if (err.message.includes("No such file or directory") || err.message.includes("not found")) {
      return res.status(404).json({ error: `Image "${req.params.name}" not found`, code: "NOT_FOUND" });
    }
    next(err);
  }
});

export default router;
