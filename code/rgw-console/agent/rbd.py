from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from .config import AgentConfig
from .errors import AgentError


EMPTY_SCHEMA: dict[str, dict[str, str]] = {"required": {}, "optional": {}}
READ_IDENTITY = {"pool": "scope", "namespace": "namespace", "image_name": "scope"}
MUTATION_COMMON = {
    "volume_id": "uuid",
    "action_id": "uuid",
    "fence_token": "positive_int",
}
IMAGE_IDENTITY = {
    "pool": "scope",
    "namespace": "namespace",
    "image_name": "scope",
    "image_id": "image_id",
}
DEVICE_IDENTITY = {
    "device_major": "device_number",
    "device_minor": "device_number",
}

RBD_ACTION_SCHEMAS: dict[str, dict[str, dict[str, str]]] = {
    "rbd.pool.list": EMPTY_SCHEMA,
    "rbd.image.list": {
        "required": {"pool": "scope", "namespace": "namespace"},
        "optional": {},
    },
    "rbd.image.info": {"required": READ_IDENTITY, "optional": {}},
    "rbd.device.list": EMPTY_SCHEMA,
    "rbd.image.create": {
        "required": {
            **MUTATION_COMMON,
            "pool": "scope",
            "namespace": "namespace",
            "image_name": "scope",
            "size_bytes": "positive_int",
        },
        "optional": {},
    },
    "rbd.image.map": {
        "required": {**MUTATION_COMMON, **IMAGE_IDENTITY},
        "optional": {},
    },
    "rbd.device.format_ext4": {
        "required": {
            **MUTATION_COMMON,
            **IMAGE_IDENTITY,
            "creation_action_id": "uuid",
            **DEVICE_IDENTITY,
        },
        "optional": {},
    },
    "rbd.device.mount": {
        "required": {
            **MUTATION_COMMON,
            **IMAGE_IDENTITY,
            **DEVICE_IDENTITY,
            "fs_uuid": "uuid",
        },
        "optional": {},
    },
    "rbd.device.unmount": {
        "required": {
            **MUTATION_COMMON,
            **IMAGE_IDENTITY,
            **DEVICE_IDENTITY,
            "fs_uuid": "uuid",
        },
        "optional": {},
    },
    "rbd.device.unmap": {
        "required": {
            **MUTATION_COMMON,
            **IMAGE_IDENTITY,
            **DEVICE_IDENTITY,
        },
        "optional": {},
    },
    "rbd.image.remove": {
        "required": {**MUTATION_COMMON, **IMAGE_IDENTITY},
        "optional": {},
    },
}
RBD_ACTIONS = frozenset(RBD_ACTION_SCHEMAS)
RBD_MUTATIONS = frozenset(action for action in RBD_ACTIONS if action not in {
    "rbd.pool.list", "rbd.image.list", "rbd.image.info", "rbd.device.list"
})

_MOUNT_ESCAPE = re.compile(r"\\([0-7]{3})")
_NOT_FOUND_MARKERS = (
    "no such file or directory",
    "no such file",
    "error opening image",
    "doesn't exist",
    "does not exist",
)


class RbdActionRunner:
    """Closed manual RBD lifecycle actions with local fencing and identity checks."""

    def __init__(
        self,
        config: AgentConfig,
        invoke: Callable[[tuple[str, ...], str], str],
        ceph_argv: Callable[[str, tuple[str, ...]], tuple[str, ...]],
    ) -> None:
        self.config = config
        self._invoke = invoke
        self._argv = ceph_argv
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def dispatch(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "rbd.pool.list": self._pool_list,
            "rbd.image.list": self._image_list,
            "rbd.image.info": self._image_info_action,
            "rbd.device.list": self._device_list_action,
            "rbd.image.create": self._create,
            "rbd.image.map": self._map,
            "rbd.device.format_ext4": self._format_ext4,
            "rbd.device.mount": self._mount,
            "rbd.device.unmount": self._unmount,
            "rbd.device.unmap": self._unmap,
            "rbd.image.remove": self._remove,
        }
        handler = handlers.get(action)
        if handler is None:
            raise AgentError("ACTION_NOT_ALLOWED", "The requested action is not allowed")
        if action in RBD_MUTATIONS:
            with self._volume_lock(params["volume_id"]):
                return handler(params)
        return handler(params)

    def capability_scope(self) -> dict[str, Any]:
        return {
            "pools": sorted(self.config.rbd_allowed_pools),
            "namespaces": sorted(self.config.rbd_allowed_namespaces),
            "image_prefixes": sorted(self.config.rbd_allowed_image_prefixes),
            "mount_root": str(self.config.rbd_mount_root),
            "filesystem": "ext4",
            "file_browser": False,
            "force_operations": False,
            "lazy_unmount": False,
        }

    # -- filtered inventory -------------------------------------------------

    def _pool_list(self, _params: dict[str, Any]) -> dict[str, Any]:
        raw = self._json_command(
            self._argv("ceph", ("osd", "pool", "ls", "--format=json")),
            "rbd.pool.list",
        )
        names = raw if isinstance(raw, list) else []
        allowed = sorted(
            name for name in names
            if isinstance(name, str) and name in self.config.rbd_allowed_pools
        )
        return {"pools": allowed}

    def _image_list(self, params: dict[str, Any]) -> dict[str, Any]:
        pool, namespace = self._scope(params)
        raw = self._json_command(
            self._argv(
                "rbd",
                (
                    "ls", "--pool", pool, "--namespace", namespace,
                    "--format=json",
                ),
            ),
            "rbd.image.list",
        )
        if not isinstance(raw, list):
            raise self._invalid_output("rbd.image.list")
        names: list[str] = []
        for item in raw:
            name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
            if isinstance(name, str) and self._image_allowed(name):
                names.append(name)
        return {"pool": pool, "namespace": namespace, "images": sorted(set(names))}

    def _image_info_action(self, params: dict[str, Any]) -> dict[str, Any]:
        pool, namespace, image_name = self._identity(params)
        info = self._read_info(pool, namespace, image_name, required=True)
        assert info is not None
        return info

    def _device_list_action(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"devices": self._device_list()}

    # -- mutations ----------------------------------------------------------

    def _create(self, params: dict[str, Any]) -> dict[str, Any]:
        pool, namespace, image_name = self._identity(params)
        size_bytes = params["size_bytes"]
        if not self.config.rbd_min_size_bytes <= size_bytes <= self.config.rbd_max_size_bytes:
            raise AgentError("INVALID_SIZE", "RBD image size is outside the configured range")
        mib = 1024 * 1024
        if size_bytes % mib:
            raise AgentError("INVALID_SIZE", "RBD image size must be MiB-aligned")

        record = self._load_record(params["volume_id"])
        if record is not None:
            replay = self._replay_or_fence(record, "rbd.image.create", params)
            if replay is not None:
                return replay
            raise AgentError(
                "VOLUME_ID_CONFLICT",
                "The volume ID is already bound to an agent record",
            )
        if self._read_info(pool, namespace, image_name, required=False) is not None:
            raise AgentError(
                "IMAGE_ALREADY_EXISTS",
                "Refusing to adopt or overwrite an existing RBD image",
            )

        record = {
            "version": 1,
            "volume_id": params["volume_id"],
            "pool": pool,
            "namespace": namespace,
            "image_name": image_name,
            "size_bytes": size_bytes,
            "creation_action_id": params["action_id"],
            "created_confirmed": False,
            "formatted": False,
            "deleted": False,
            "last_fence_token": 0,
            "actions": {},
        }
        self._begin_action(record, "rbd.image.create", params)
        self._invoke(
            self._argv(
                "rbd",
                (
                    "create", "--pool", pool, "--namespace", namespace,
                    "--image", image_name, "--size", f"{size_bytes // mib}M",
                    "--image-format", "2", "--image-feature", "layering,exclusive-lock",
                ),
            ),
            "rbd.image.create",
        )
        info = self._read_info(pool, namespace, image_name, required=True)
        assert info is not None
        self._assert_created_info(info, size_bytes)
        record.update(
            image_id=info["image_id"],
            created_confirmed=True,
            features=info["features"],
        )
        result = {**info, "volume_id": params["volume_id"], "state": "CREATED"}
        return self._finish_action(record, params["action_id"], result)

    def _map(self, params: dict[str, Any]) -> dict[str, Any]:
        record = self._managed_record(params)
        replay = self._replay_or_fence(record, "rbd.image.map", params)
        if replay is not None:
            return replay
        info = self._assert_live_image(params, record)
        if "exclusive-lock" not in info["features"]:
            raise AgentError("FEATURE_MISMATCH", "RBD image lacks exclusive-lock")
        mappings = self._matching_mappings(params)
        if mappings:
            raise AgentError("IMAGE_ALREADY_MAPPED", "RBD image already has a local mapping")
        status = self._read_status(params)
        if status.get("watchers"):
            raise AgentError("IMAGE_IN_USE", "RBD image has an existing watcher")

        self._begin_action(record, "rbd.image.map", params)
        self._invoke(
            self._argv(
                "rbd",
                (
                    "device", "map", "--pool", params["pool"],
                    "--namespace", params["namespace"], "--image",
                    params["image_name"], "--exclusive",
                ),
            ),
            "rbd.image.map",
        )
        mappings = self._matching_mappings(params)
        if len(mappings) != 1:
            raise AgentError(
                "MAPPING_IDENTITY_UNKNOWN",
                "Could not identify exactly one new RBD mapping",
                retryable=True,
            )
        observed = self._observe_mapping_identity(mappings[0], params)
        record.update(
            mapped=True,
            device=observed["device"],
            device_major=observed["device_major"],
            device_minor=observed["device_minor"],
            mapping_id=observed["mapping_id"],
        )
        result = {**observed, "volume_id": params["volume_id"], "state": "MAPPED"}
        return self._finish_action(record, params["action_id"], result)

    def _format_ext4(self, params: dict[str, Any]) -> dict[str, Any]:
        record = self._managed_record(params)
        replay = self._replay_or_fence(record, "rbd.device.format_ext4", params)
        if replay is not None:
            return replay
        if params["creation_action_id"] != record.get("creation_action_id"):
            raise AgentError(
                "CREATION_IDENTITY_MISMATCH",
                "Format is allowed only for the action that created this volume",
            )
        if not record.get("created_confirmed") or record.get("formatted"):
            raise AgentError(
                "FORMAT_NOT_ALLOWED",
                "Only a newly created, never-formatted managed image may be formatted",
            )
        self._assert_live_image(params, record)
        mapping = self._required_mapping(params)
        observed = self._observe_mapping_identity(mapping, params)
        self._assert_expected_device(params, observed, record)
        self._assert_not_mounted(observed)
        self._assert_no_holders(observed)
        self._assert_blank_device(observed["device"])

        self._begin_action(record, "rbd.device.format_ext4", params)
        self._invoke(
            (str(self.config.mkfs_ext4_binary), "-m", "0", observed["device"]),
            "rbd.device.format_ext4",
        )
        signature = self._blkid(observed["device"], blank_allowed=False)
        if signature.get("TYPE") != "ext4" or "UUID" not in signature:
            raise AgentError(
                "FORMAT_VERIFY_FAILED",
                "The new filesystem could not be verified as ext4",
                retryable=True,
            )
        try:
            fs_uuid = str(UUID(signature["UUID"]))
        except (ValueError, TypeError) as exc:
            raise AgentError("FORMAT_VERIFY_FAILED", "Filesystem UUID is invalid") from exc
        record.update(formatted=True, filesystem="ext4", fs_uuid=fs_uuid)
        result = {
            "volume_id": params["volume_id"],
            "state": "FORMATTED",
            "filesystem": "ext4",
            "fs_uuid": fs_uuid,
            **observed,
        }
        return self._finish_action(record, params["action_id"], result)

    def _mount(self, params: dict[str, Any]) -> dict[str, Any]:
        record = self._managed_record(params)
        replay = self._replay_or_fence(record, "rbd.device.mount", params)
        if replay is not None:
            return replay
        self._assert_live_image(params, record)
        mapping = self._required_mapping(params)
        observed = self._observe_mapping_identity(mapping, params)
        self._assert_expected_device(params, observed, record)
        self._assert_filesystem(params, record, observed["device"])
        mountpoint = self._ensure_mountpoint(params["volume_id"])
        entries = self._mount_entries()
        same_device = [entry for entry in entries if entry["major"] == observed["device_major"] and entry["minor"] == observed["device_minor"]]
        at_target = [entry for entry in entries if entry["target"] == str(mountpoint)]
        if same_device or at_target:
            if len(same_device) == len(at_target) == 1 and same_device[0] is at_target[0]:
                self._assert_mount_entry(same_device[0], observed, mountpoint)
                result = self._mount_result(params, observed, mountpoint, "MOUNTED")
                self._begin_action(record, "rbd.device.mount", params)
                record.update(mounted=True, mountpoint=str(mountpoint))
                return self._finish_action(record, params["action_id"], result)
            raise AgentError("MOUNT_IDENTITY_CONFLICT", "Device or mountpoint is already in use")
        if any(mountpoint.iterdir()):
            raise AgentError("MOUNTPOINT_NOT_EMPTY", "Managed mountpoint is not empty")

        self._begin_action(record, "rbd.device.mount", params)
        self._invoke(
            (
                str(self.config.mount_binary), "-t", "ext4", "-o", "rw,nosuid,nodev",
                observed["device"], str(mountpoint),
            ),
            "rbd.device.mount",
        )
        entry = self._entry_for_target(mountpoint)
        self._assert_mount_entry(entry, observed, mountpoint)
        self._probe_mount(mountpoint, params["action_id"])
        record.update(mounted=True, mountpoint=str(mountpoint))
        return self._finish_action(
            record,
            params["action_id"],
            self._mount_result(params, observed, mountpoint, "MOUNTED"),
        )

    def _unmount(self, params: dict[str, Any]) -> dict[str, Any]:
        record = self._managed_record(params)
        replay = self._replay_or_fence(record, "rbd.device.unmount", params)
        if replay is not None:
            return replay
        self._assert_live_image(params, record)
        mapping = self._required_mapping(params)
        observed = self._observe_mapping_identity(mapping, params)
        self._assert_expected_device(params, observed, record)
        self._assert_filesystem(params, record, observed["device"])
        mountpoint = self._derived_mountpoint(params["volume_id"])
        entry = self._entry_for_target(mountpoint, required=False)

        self._begin_action(record, "rbd.device.unmount", params)
        if entry is not None:
            self._assert_mount_entry(entry, observed, mountpoint)
            self._invoke(
                (str(self.config.sync_binary), "-f", str(mountpoint)),
                "rbd.device.unmount.sync",
            )
            try:
                self._invoke(
                    (str(self.config.umount_binary), str(mountpoint)),
                    "rbd.device.unmount",
                )
            except AgentError as exc:
                stderr = str(exc.details.get("stderr", "")).lower()
                if exc.code == "COMMAND_FAILED" and "busy" in stderr:
                    raise AgentError("VOLUME_BUSY", "The volume is busy; unmount was refused") from exc
                raise
            if self._entry_for_target(mountpoint, required=False) is not None:
                raise AgentError("UNMOUNT_VERIFY_FAILED", "Mount is still present", retryable=True)
        record["mounted"] = False
        result = {
            "volume_id": params["volume_id"],
            "state": "UNMOUNTED",
            "mountpoint": str(mountpoint),
            "device": observed["device"],
            "device_major": observed["device_major"],
            "device_minor": observed["device_minor"],
        }
        return self._finish_action(record, params["action_id"], result)

    def _unmap(self, params: dict[str, Any]) -> dict[str, Any]:
        record = self._managed_record(params)
        replay = self._replay_or_fence(record, "rbd.device.unmap", params)
        if replay is not None:
            return replay
        self._assert_live_image(params, record)
        mappings = self._matching_mappings(params)
        self._begin_action(record, "rbd.device.unmap", params)
        if mappings:
            if len(mappings) != 1:
                raise AgentError("MAPPING_IDENTITY_UNKNOWN", "Multiple matching mappings exist")
            observed = self._observe_mapping_identity(mappings[0], params)
            self._assert_expected_device(params, observed, record)
            self._assert_not_mounted(observed)
            self._invoke(
                self._argv("rbd", ("device", "unmap", observed["device"])),
                "rbd.device.unmap",
            )
            if self._matching_mappings(params):
                raise AgentError("UNMAP_VERIFY_FAILED", "RBD mapping is still present", retryable=True)
        else:
            self._assert_record_device(params, record)
            observed = {
                "device": record.get("device"),
                "device_major": params["device_major"],
                "device_minor": params["device_minor"],
            }
        record["mapped"] = False
        result = {"volume_id": params["volume_id"], "state": "UNMAPPED", **observed}
        return self._finish_action(record, params["action_id"], result)

    def _remove(self, params: dict[str, Any]) -> dict[str, Any]:
        record = self._managed_record(params)
        replay = self._replay_or_fence(record, "rbd.image.remove", params)
        if replay is not None:
            return replay
        self._assert_live_image(params, record)
        if self._matching_mappings(params):
            raise AgentError("IMAGE_STILL_MAPPED", "RBD image is still mapped")
        if self._read_status(params).get("watchers"):
            raise AgentError("IMAGE_IN_USE", "RBD image still has watchers")
        snapshots = self._rbd_json_for_image("snap", "ls", params, "rbd.image.remove.snapshots")
        if snapshots:
            raise AgentError("DELETE_BLOCKED_DEPENDENCY", "RBD image still has snapshots")
        children = self._rbd_json_for_image("children", None, params, "rbd.image.remove.children")
        if children:
            raise AgentError("DELETE_BLOCKED_DEPENDENCY", "RBD image still has clone dependencies")
        mountpoint = self._derived_mountpoint(params["volume_id"])
        if self._entry_for_target(mountpoint, required=False) is not None:
            raise AgentError("VOLUME_BUSY", "Managed mountpoint is still mounted")
        if mountpoint.exists() and any(mountpoint.iterdir()):
            raise AgentError("MOUNTPOINT_NOT_EMPTY", "Managed mountpoint is not empty")

        self._begin_action(record, "rbd.image.remove", params)
        self._invoke(
            self._argv(
                "rbd",
                (
                    "rm", "--pool", params["pool"], "--namespace",
                    params["namespace"], "--image", params["image_name"],
                ),
            ),
            "rbd.image.remove",
        )
        if self._read_info(params["pool"], params["namespace"], params["image_name"], required=False) is not None:
            raise AgentError("DELETE_VERIFY_FAILED", "RBD image still exists", retryable=True)
        if mountpoint.exists():
            self._remove_empty_mountpoint(mountpoint)
        record.update(deleted=True, mapped=False, mounted=False)
        return self._finish_action(
            record,
            params["action_id"],
            {"volume_id": params["volume_id"], "state": "DELETED", "image_id": params["image_id"]},
        )

    # -- Ceph observations --------------------------------------------------

    def _scope(self, params: dict[str, Any]) -> tuple[str, str]:
        pool = params["pool"]
        namespace = params["namespace"]
        if pool not in self.config.rbd_allowed_pools:
            raise AgentError("SCOPE_NOT_ALLOWED", "RBD pool is outside the agent allowlist")
        if namespace not in self.config.rbd_allowed_namespaces:
            raise AgentError("SCOPE_NOT_ALLOWED", "RBD namespace is outside the agent allowlist")
        return pool, namespace

    def _identity(self, params: dict[str, Any]) -> tuple[str, str, str]:
        pool, namespace = self._scope(params)
        image_name = params["image_name"]
        if not self._image_allowed(image_name):
            raise AgentError("SCOPE_NOT_ALLOWED", "RBD image prefix is outside the agent allowlist")
        return pool, namespace, image_name

    def _image_allowed(self, name: str) -> bool:
        return any(name.startswith(prefix) for prefix in self.config.rbd_allowed_image_prefixes)

    def _read_info(
        self, pool: str, namespace: str, image_name: str, *, required: bool
    ) -> dict[str, Any] | None:
        self._identity({"pool": pool, "namespace": namespace, "image_name": image_name})
        try:
            raw = self._json_command(
                self._argv(
                    "rbd",
                    (
                        "info", "--pool", pool, "--namespace", namespace,
                        "--image", image_name, "--format=json",
                    ),
                ),
                "rbd.image.info",
            )
        except AgentError as exc:
            if self._is_not_found(exc):
                if required:
                    raise AgentError("IMAGE_NOT_FOUND", "Managed RBD image does not exist") from exc
                return None
            raise
        if not isinstance(raw, dict):
            raise self._invalid_output("rbd.image.info")
        image_id = raw.get("id")
        size = raw.get("size")
        features_raw = raw.get("features", [])
        if isinstance(features_raw, str):
            features = sorted(part.strip() for part in features_raw.split(",") if part.strip())
        elif isinstance(features_raw, list) and all(isinstance(item, str) for item in features_raw):
            features = sorted(features_raw)
        else:
            raise self._invalid_output("rbd.image.info")
        if not isinstance(image_id, str) or not re.fullmatch(r"[0-9a-f]{1,64}", image_id):
            raise self._invalid_output("rbd.image.info")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise self._invalid_output("rbd.image.info")
        return {
            "pool": pool,
            "namespace": namespace,
            "image_name": image_name,
            "image_id": image_id,
            "size_bytes": size,
            "features": features,
        }

    def _read_status(self, params: dict[str, Any]) -> dict[str, Any]:
        raw = self._rbd_json_for_image("status", None, params, "rbd.image.status")
        if not isinstance(raw, dict):
            raise self._invalid_output("rbd.image.status")
        watchers = raw.get("watchers", [])
        if not isinstance(watchers, list):
            raise self._invalid_output("rbd.image.status")
        return {"watchers": watchers}

    def _rbd_json_for_image(
        self,
        command: str,
        subcommand: str | None,
        params: dict[str, Any],
        action: str,
    ) -> Any:
        prefix = (command,) if subcommand is None else (command, subcommand)
        return self._json_command(
            self._argv(
                "rbd",
                (
                    *prefix, "--pool", params["pool"], "--namespace",
                    params["namespace"], "--image", params["image_name"],
                    "--format=json",
                ),
            ),
            action,
        )

    def _device_list(self) -> list[dict[str, Any]]:
        raw = self._json_command(
            self._argv("rbd", ("device", "list", "--format=json")),
            "rbd.device.list",
        )
        if not isinstance(raw, list):
            raise self._invalid_output("rbd.device.list")
        result: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise self._invalid_output("rbd.device.list")
            pool = item.get("pool")
            namespace = item.get("namespace") or ""
            image_name = item.get("name", item.get("image"))
            device = item.get("device")
            if (
                pool not in self.config.rbd_allowed_pools
                or namespace not in self.config.rbd_allowed_namespaces
                or not isinstance(image_name, str)
                or not self._image_allowed(image_name)
            ):
                continue
            if not isinstance(device, str) or not device.startswith("/dev/rbd"):
                raise self._invalid_output("rbd.device.list")
            result.append(
                {
                    "mapping_id": str(item.get("id", "")),
                    "pool": pool,
                    "namespace": namespace,
                    "image_name": image_name,
                    "device": device,
                    **({"image_id": item["image_id"]} if isinstance(item.get("image_id"), str) else {}),
                }
            )
        return result

    def _matching_mappings(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._identity(params)
        return [
            item for item in self._device_list()
            if item["pool"] == params["pool"]
            and item["namespace"] == params["namespace"]
            and item["image_name"] == params["image_name"]
        ]

    def _required_mapping(self, params: dict[str, Any]) -> dict[str, Any]:
        mappings = self._matching_mappings(params)
        if len(mappings) != 1:
            raise AgentError("MAPPING_IDENTITY_UNKNOWN", "Expected exactly one managed RBD mapping")
        return mappings[0]

    # -- device and mount identity -----------------------------------------

    def _observe_mapping_identity(
        self, mapping: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        device = Path(mapping["device"])
        try:
            device_stat = device.stat()
        except OSError as exc:
            raise AgentError("DEVICE_NOT_FOUND", "Mapped RBD device is unavailable") from exc
        if not stat.S_ISBLK(device_stat.st_mode):
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "Mapped path is not a block device")
        major = os.major(device_stat.st_rdev)
        minor = os.minor(device_stat.st_rdev)
        mapping_id = mapping.get("mapping_id")
        if not mapping_id or not str(mapping_id).isdigit():
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "RBD mapping ID is missing")
        sysfs = self.config.sysfs_root / "bus" / "rbd" / "devices" / str(mapping_id)
        expected_files = {
            "pool": params["pool"],
            "name": params["image_name"],
            "image_id": params["image_id"],
            "major": str(major),
        }
        if params["namespace"]:
            expected_files["pool_ns"] = params["namespace"]
        for filename, expected in expected_files.items():
            try:
                observed = (sysfs / filename).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise AgentError(
                    "DEVICE_IDENTITY_MISMATCH",
                    "Required RBD sysfs identity is unavailable",
                    details={"field": filename},
                ) from exc
            if observed != expected:
                raise AgentError(
                    "DEVICE_IDENTITY_MISMATCH",
                    "RBD sysfs identity does not match the requested image",
                    details={"field": filename},
                )
        if mapping.get("image_id") not in {None, params["image_id"]}:
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "Mapping image ID does not match")
        return {
            "mapping_id": str(mapping_id),
            "device": str(device),
            "device_major": major,
            "device_minor": minor,
        }

    def _assert_expected_device(
        self,
        params: dict[str, Any],
        observed: dict[str, Any],
        record: dict[str, Any],
    ) -> None:
        if (
            observed["device_major"] != params["device_major"]
            or observed["device_minor"] != params["device_minor"]
        ):
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "Device major:minor changed")
        self._assert_record_device(params, record)
        if record.get("device") != observed["device"]:
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "Mapped device path changed")

    @staticmethod
    def _assert_record_device(params: dict[str, Any], record: dict[str, Any]) -> None:
        if (
            record.get("device_major") != params["device_major"]
            or record.get("device_minor") != params["device_minor"]
        ):
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "Device does not match agent record")

    def _assert_not_mounted(self, observed: dict[str, Any]) -> None:
        if any(
            entry["major"] == observed["device_major"]
            and entry["minor"] == observed["device_minor"]
            for entry in self._mount_entries()
        ):
            raise AgentError("VOLUME_BUSY", "RBD device is mounted")

    def _assert_no_holders(self, observed: dict[str, Any]) -> None:
        holders = (
            self.config.sysfs_root / "dev" / "block"
            / f"{observed['device_major']}:{observed['device_minor']}" / "holders"
        )
        try:
            entries = list(holders.iterdir())
        except OSError as exc:
            raise AgentError("DEVICE_IDENTITY_MISMATCH", "Could not inspect block holders") from exc
        if entries:
            raise AgentError("VOLUME_BUSY", "RBD device has block holders")

    def _assert_blank_device(self, device: str) -> None:
        raw = self._json_command(
            (str(self.config.wipefs_binary), "-n", "--json", device),
            "rbd.device.format_ext4.wipefs",
        )
        if not isinstance(raw, dict) or "signatures" not in raw:
            raise self._invalid_output("rbd.device.format_ext4.wipefs")
        signatures = raw["signatures"]
        if signatures not in (None, []):
            raise AgentError("FILESYSTEM_SIGNATURE_PRESENT", "Device already contains a signature")
        if self._blkid(device, blank_allowed=True):
            raise AgentError("FILESYSTEM_SIGNATURE_PRESENT", "Device already contains a signature")

    def _blkid(self, device: str, *, blank_allowed: bool) -> dict[str, str]:
        try:
            stdout = self._invoke(
                (str(self.config.blkid_binary), "-p", "-o", "export", device),
                "rbd.device.blkid",
            )
        except AgentError as exc:
            if blank_allowed and exc.code == "COMMAND_FAILED" and exc.details.get("exit_code") == 2:
                return {}
            raise
        fields: dict[str, str] = {}
        for line in stdout.splitlines():
            if not line:
                continue
            key, separator, value = line.partition("=")
            if not separator or not key:
                raise self._invalid_output("rbd.device.blkid")
            fields[key] = value
        return fields

    def _mount_entries(self) -> list[dict[str, Any]]:
        try:
            lines = self.config.proc_mountinfo_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AgentError("MOUNT_STATE_UNAVAILABLE", "Could not read mountinfo") from exc
        entries: list[dict[str, Any]] = []
        for line in lines:
            fields = line.split()
            try:
                separator = fields.index("-")
                major_text, minor_text = fields[2].split(":", 1)
                entry = {
                    "major": int(major_text),
                    "minor": int(minor_text),
                    "target": self._unescape_mount(fields[4]),
                    "options": fields[5].split(","),
                    "fstype": fields[separator + 1],
                    "source": self._unescape_mount(fields[separator + 2]),
                }
            except (ValueError, IndexError):
                raise self._invalid_output("mountinfo")
            entries.append(entry)
        return entries

    @staticmethod
    def _unescape_mount(value: str) -> str:
        return _MOUNT_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)

    def _entry_for_target(
        self, mountpoint: Path, *, required: bool = True
    ) -> dict[str, Any] | None:
        entries = [entry for entry in self._mount_entries() if entry["target"] == str(mountpoint)]
        if len(entries) > 1:
            raise AgentError("MOUNT_IDENTITY_CONFLICT", "Mountpoint is over-mounted")
        if not entries:
            if required:
                raise AgentError("MOUNT_VERIFY_FAILED", "Managed mountpoint is not mounted")
            return None
        return entries[0]

    @staticmethod
    def _assert_mount_entry(
        entry: dict[str, Any] | None,
        observed: dict[str, Any],
        mountpoint: Path,
    ) -> None:
        if entry is None or (
            entry["major"] != observed["device_major"]
            or entry["minor"] != observed["device_minor"]
            or entry["target"] != str(mountpoint)
            or entry["fstype"] != "ext4"
            or "rw" not in entry["options"]
        ):
            raise AgentError("MOUNT_IDENTITY_MISMATCH", "Mounted filesystem identity does not match")

    def _derived_mountpoint(self, volume_id: str) -> Path:
        canonical = str(UUID(volume_id))
        return self.config.rbd_mount_root / canonical

    def _ensure_mountpoint(self, volume_id: str) -> Path:
        root = self.config.rbd_mount_root
        try:
            root_stat = root.lstat()
        except FileNotFoundError as exc:
            raise AgentError("MOUNT_ROOT_UNAVAILABLE", "Configured mount root does not exist") from exc
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise AgentError("MOUNT_ROOT_UNSAFE", "Configured mount root is not a real directory")
        if root_stat.st_mode & stat.S_IWOTH:
            raise AgentError("MOUNT_ROOT_UNSAFE", "Configured mount root is world-writable")
        name = str(UUID(volume_id))
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(root, flags)
        try:
            try:
                os.mkdir(name, mode=0o770, dir_fd=root_fd)
            except FileExistsError:
                pass
            child = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISDIR(child.st_mode):
                raise AgentError("MOUNTPOINT_UNSAFE", "Managed mountpoint is not a real directory")
        finally:
            os.close(root_fd)
        return root / name

    def _remove_empty_mountpoint(self, mountpoint: Path) -> None:
        root_fd = os.open(
            self.config.rbd_mount_root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.rmdir(mountpoint.name, dir_fd=root_fd)
        except OSError as exc:
            raise AgentError("MOUNTPOINT_NOT_EMPTY", "Managed mountpoint could not be removed") from exc
        finally:
            os.close(root_fd)

    def _probe_mount(self, mountpoint: Path, action_id: str) -> None:
        directory_fd = os.open(
            mountpoint,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        name = f".rgw-console-probe-{action_id}"
        payload = action_id.encode("ascii")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        file_fd: int | None = None
        try:
            file_fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
            os.write(file_fd, payload)
            os.fsync(file_fd)
            os.lseek(file_fd, 0, os.SEEK_SET)
            if os.read(file_fd, len(payload) + 1) != payload:
                raise AgentError("MOUNT_PROBE_FAILED", "Mounted filesystem probe mismatch")
        finally:
            if file_fd is not None:
                os.close(file_fd)
            try:
                os.unlink(name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)

    # -- registry, fencing, idempotency ------------------------------------

    def _volume_lock(self, volume_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(volume_id, threading.Lock())

    def _record_path(self, volume_id: str) -> Path:
        return self.config.rbd_state_root / f"{str(UUID(volume_id))}.json"

    def _ensure_state_root(self) -> None:
        root = self.config.rbd_state_root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_stat = root.lstat()
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise AgentError("AGENT_STATE_UNSAFE", "Agent state root is not a real directory")
        if root_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise AgentError("AGENT_STATE_UNSAFE", "Agent state root is writable by other users")

    def _load_record(self, volume_id: str) -> dict[str, Any] | None:
        self._ensure_state_root()
        path = self._record_path(volume_id)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        try:
            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > 1024 * 1024:
                raise AgentError("AGENT_STATE_UNSAFE", "Agent volume record is unsafe")
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                fd = -1
                record = json.load(stream)
        except (OSError, ValueError, TypeError) as exc:
            raise AgentError("AGENT_STATE_INVALID", "Agent volume record is invalid") from exc
        finally:
            if fd >= 0:
                os.close(fd)
        if not isinstance(record, dict) or record.get("volume_id") != volume_id:
            raise AgentError("AGENT_STATE_INVALID", "Agent volume record identity is invalid")
        return record

    def _save_record(self, record: dict[str, Any]) -> None:
        self._ensure_state_root()
        path = self._record_path(record["volume_id"])
        temporary = path.parent / f".{path.name}.{uuid4()}.tmp"
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, path)
            directory_fd = os.open(
                path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _fingerprint(params: dict[str, Any]) -> str:
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()

    def _replay_or_fence(
        self, record: dict[str, Any], action: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        action_id = params["action_id"]
        previous = record.get("actions", {}).get(action_id)
        fingerprint = self._fingerprint(params)
        if previous is not None:
            if previous.get("action") != action or previous.get("fingerprint") != fingerprint:
                raise AgentError("IDEMPOTENCY_CONFLICT", "action_id was reused with different input")
            if previous.get("state") == "SUCCEEDED" and isinstance(previous.get("result"), dict):
                return {**previous["result"], "replayed": True}
            raise AgentError(
                "ACTION_RECONCILIATION_REQUIRED",
                "Previous action outcome is uncertain; observe state before retry",
            )
        if params["fence_token"] <= int(record.get("last_fence_token", 0)):
            raise AgentError("FENCE_REJECTED", "Action fence token is stale")
        return None

    def _begin_action(
        self, record: dict[str, Any], action: str, params: dict[str, Any]
    ) -> None:
        replay = self._replay_or_fence(record, action, params)
        if replay is not None:
            raise RuntimeError("replay must be handled before begin")
        actions = record.setdefault("actions", {})
        actions[params["action_id"]] = {
            "action": action,
            "fingerprint": self._fingerprint(params),
            "state": "IN_PROGRESS",
        }
        record["last_fence_token"] = params["fence_token"]
        if len(actions) > 64:
            for stale_id in list(actions)[:-64]:
                del actions[stale_id]
        self._save_record(record)

    def _finish_action(
        self, record: dict[str, Any], action_id: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        action = record["actions"][action_id]
        action.update(state="SUCCEEDED", result=result)
        self._save_record(record)
        return result

    def _managed_record(self, params: dict[str, Any]) -> dict[str, Any]:
        self._identity(params)
        record = self._load_record(params["volume_id"])
        if record is None:
            raise AgentError("UNMANAGED_VOLUME", "No agent record exists for this volume")
        for field in ("pool", "namespace", "image_name", "image_id"):
            if record.get(field) != params[field]:
                raise AgentError("IMAGE_IDENTITY_MISMATCH", "Image identity does not match agent record")
        if not record.get("created_confirmed") or record.get("deleted"):
            raise AgentError("IMAGE_STATE_CONFLICT", "Managed image is not in a mutable live state")
        return record

    def _assert_live_image(
        self, params: dict[str, Any], record: dict[str, Any]
    ) -> dict[str, Any]:
        info = self._read_info(params["pool"], params["namespace"], params["image_name"], required=True)
        assert info is not None
        if info["image_id"] != params["image_id"] or info["image_id"] != record.get("image_id"):
            raise AgentError("IMAGE_IDENTITY_MISMATCH", "Immutable RBD image ID changed")
        return info

    @staticmethod
    def _assert_created_info(info: dict[str, Any], size_bytes: int) -> None:
        if info["size_bytes"] != size_bytes:
            raise AgentError("CREATE_VERIFY_FAILED", "Created RBD image size is unexpected")
        if "exclusive-lock" not in info["features"]:
            raise AgentError("CREATE_VERIFY_FAILED", "Created RBD image lacks exclusive-lock")

    def _assert_filesystem(
        self, params: dict[str, Any], record: dict[str, Any], device: str
    ) -> None:
        if not record.get("formatted") or record.get("fs_uuid") != params["fs_uuid"]:
            raise AgentError("FILESYSTEM_IDENTITY_MISMATCH", "Filesystem does not match agent record")
        signature = self._blkid(device, blank_allowed=False)
        if signature.get("TYPE") != "ext4" or signature.get("UUID") != params["fs_uuid"]:
            raise AgentError("FILESYSTEM_IDENTITY_MISMATCH", "Observed filesystem identity changed")

    @staticmethod
    def _mount_result(
        params: dict[str, Any], observed: dict[str, Any], mountpoint: Path, state: str
    ) -> dict[str, Any]:
        return {
            "volume_id": params["volume_id"],
            "state": state,
            "mountpoint": str(mountpoint),
            "filesystem": "ext4",
            "fs_uuid": params["fs_uuid"],
            **observed,
        }

    # -- command helpers ----------------------------------------------------

    def _json_command(self, argv: tuple[str, ...], action: str) -> Any:
        stdout = self._invoke(argv, action)
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise self._invalid_output(action) from exc

    @staticmethod
    def _invalid_output(action: str) -> AgentError:
        return AgentError(
            "INVALID_CEPH_OUTPUT",
            "Command returned an unexpected response",
            details={"action": action},
        )

    @staticmethod
    def _is_not_found(error: AgentError) -> bool:
        if error.code != "COMMAND_FAILED":
            return False
        stderr = str(error.details.get("stderr", "")).lower()
        return any(marker in stderr for marker in _NOT_FOUND_MARKERS)

