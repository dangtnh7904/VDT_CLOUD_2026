/**
 * RBD device routes.
 *
 * GET /api/rbd/devices — list currently mapped RBD devices
 */

import { Router } from "express";
import { listDevices } from "../rbd.js";
import { status as sshStatus } from "../ssh.js";

const router = Router();

router.get("/", async (_req, res, next) => {
  try {
    const ssh = sshStatus();
    if (!ssh.connected) {
      return res.status(503).json({ error: "SSH not connected", code: "SSH_DISCONNECTED" });
    }

    const devices = await listDevices();

    res.json({
      count: devices.length,
      items: devices,
    });
  } catch (err) {
    next(err);
  }
});

export default router;
