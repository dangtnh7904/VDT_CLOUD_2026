from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
import threading
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ...db import connection
from ...platform.config import resolve_settings
from ...platform.evidence import FilesystemArtifactStore
from ...services.executor_client import ExecutorClient, ExecutorClientError

GATE = threading.BoundedSemaphore(1)
SUPPORTED_TOOL_VERSIONS = frozenset({
    "16.2.15",
    "ceph version 16.2.15 (618f440892089921c3e944a991122ddc44e60516) pacific (stable)",
})
# These are the tested AMD64 tools, not arbitrary well-formed hashes reported
# by a replacement worker. Keep aligned with the pinned worker/release manifest.
EXPECTED_TOOL_SHA256 = {
    "osdmaptool_sha256": "c1532cfd43e6a0cfab5c6a3bd3da405ac7224606646f9351fe34bf5fb2ed1fe0",
    "crushtool_sha256": "187ab0d81224f4e692a4376b728a86f380dffa599529bd7b9749389a086952ce",
}


def _valid_tool_identity(payload):
    return (isinstance(payload, dict)
            and isinstance(payload.get("tool_version"), str)
            and payload["tool_version"] in SUPPORTED_TOOL_VERSIONS
            and type(payload.get("parser_version")) is int and payload["parser_version"] == 2
            and payload.get("tool_binary_sha256") == EXPECTED_TOOL_SHA256)


class PreviewError(ValueError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class PreviewRepository:
    def save(self, payload, artifact, actor):
        with connection() as conn, conn.transaction():
            conn.execute("""INSERT INTO evidence_artifacts
              (id,cluster_id,fsid,evidence_type,uri,sha256,size_bytes,mime_type,producer,observed_at,metadata)
              VALUES (%s,%s,%s,'osdmap_preview',%s,%s,%s,%s,'osdmap_preview',%s,%s)""",
              (payload["id"], payload["cluster_id"], payload["fsid"], artifact.uri, artifact.sha256,
               artifact.size_bytes, artifact.mime_type, payload["started_at"],
               Jsonb({"kind": "OSDMAP_PREVIEW", "base_epoch": payload["base_epoch"], "actor": actor})))

    def get(self, preview_id, cluster_id, fsid):
        with connection() as conn:
            return conn.execute("""SELECT * FROM evidence_artifacts WHERE id=%s AND cluster_id=%s
                 AND fsid=%s AND evidence_type='osdmap_preview' AND access_policy='operator'""",
                 (preview_id, cluster_id, fsid)).fetchone()


class PreviewService:
    def __init__(self, settings, client=None, repository=None):
        self.settings = resolve_settings(settings)
        self.client = client
        self.repository = repository or PreviewRepository()

    def _client(self):
        if self.client is None:
            self.client = ExecutorClient.from_settings()
        return self.client

    def _store(self):
        return FilesystemArtifactStore(self.settings.evidence_root,
                                       max_artifact_bytes=min(self.settings.evidence_max_artifact_bytes, 64 * 1024 * 1024))

    def capabilities(self):
        spool = self.settings.osdmap_preview_spool
        if spool is not None:
            try:
                file = spool / "capabilities.json"
                if file.is_symlink() or file.stat().st_size > 4096:
                    raise ValueError()
                result = json.loads(file.read_text())
                if (not _valid_tool_identity(result) or result.get("available") is not True
                        or result.get("operations") != ["crush_weight"]
                        or result.get("pool_types") != ["replicated"]
                        or type(result.get("heartbeat")) not in (int, float)
                        or not math.isfinite(result["heartbeat"])):
                    raise ValueError()
                if 0 <= time.time() - result["heartbeat"] < 120:
                    return {k: result[k] for k in ("available", "tool_version", "operations", "pool_types",
                                                  "parser_version", "tool_binary_sha256")}
                return {"available": False, "operations": [], "code": "OSDMAP_CAPABILITIES_STALE",
                        "reason": "Heartbeat worker đã cũ hoặc nằm trong tương lai; chưa cho phép tính dự đoán."}
            except FileNotFoundError:
                pass
            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                return {"available": False, "operations": [], "code": "OSDMAP_CAPABILITIES_INVALID",
                        "reason": "Worker thiếu handshake bắt buộc hoặc khác tool/version/parser/phạm vi đã pin."}
        return {"available": False, "operations": [], "code": "OSDMAP_WORKER_UNAVAILABLE",
                "reason": "Chưa có worker osdmaptool tương thích đang hoạt động."}

    @staticmethod
    def _worker_result(output):
        if not isinstance(output, dict) or type(output.get("ok")) is not bool:
            raise PreviewError("OSDMAP_WORKER_RESULT_INVALID", "Worker trả sai cấu trúc kết quả; không lưu dự đoán.", 503)
        if not output["ok"]:
            code = output.get("code")
            if (not isinstance(code, str) or not code.startswith("OSDMAP_") or len(code) > 128
                    or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in code)):
                raise PreviewError("OSDMAP_WORKER_RESULT_INVALID", "Worker trả mã lỗi không hợp lệ; không lưu dự đoán.", 503)
            message = ("Adapter hiện chỉ nghiệm thu pool replicated; EC hoặc loại pool khác chưa được hỗ trợ. Chọn một pool replicated cụ thể."
                       if code == "OSDMAP_POOL_TYPE_UNSUPPORTED" else "Không thể kiểm chứng kịch bản; không tạo dự đoán.")
            raise PreviewError(code, message)
        return output.get("result")

    @staticmethod
    def _validate_result_identity(result, capabilities, pool_id):
        if (not _valid_tool_identity(result)
                or any(result.get(key) != capabilities[key]
                       for key in ("tool_version", "parser_version", "tool_binary_sha256"))):
            raise PreviewError("OSDMAP_RESULT_IDENTITY_MISMATCH",
                               "Kết quả khác tool/version/parser đã pin trong handshake; không lưu dự đoán.", 503)
        scope = result.get("scope")
        if (not isinstance(scope, dict) or scope.get("pool_types") != capabilities["pool_types"]
                or "pool_id" not in scope or scope["pool_id"] != pool_id
                or (pool_id is not None and type(scope["pool_id"]) is not int)):
            raise PreviewError("OSDMAP_RESULT_SCOPE_MISMATCH",
                               "Kết quả khác pool replicated/phạm vi yêu cầu; không lưu dự đoán.", 503)

    def _epoch(self):
        response = self._client().request("ceph.osd_dump")
        if response.get("fsid") != self.settings.ceph_expected_fsid:
            raise PreviewError("FSID_MISMATCH", "FSID nguồn khác cấu hình.")
        return response["data"]

    def _freshness(self, result):
        try:
            epoch = self._epoch()["epoch"]
            return {**result, "current_epoch": epoch, "stale": epoch != result["base_epoch"]}
        except (ExecutorClientError, ValueError, KeyError):
            return {**result, "current_epoch": None, "stale": None,
                    "freshness_reason": "Chưa xác minh epoch hiện tại; đây là dự đoán trên map đã lưu."}

    def create(self, changes, pool_id=None, actor="operator"):
        capabilities = self.capabilities()
        if not capabilities["available"]:
            raise PreviewError(capabilities["code"], capabilities["reason"], 503)
        allowed = {int(x.removeprefix("osd.")) for x in self.settings.upgrade_allowed_osd_set}
        if any(x["osd_id"] not in allowed for x in changes):
            raise PreviewError("OSDMAP_SCOPE_REJECTED", "OSD nằm ngoài phạm vi được cấu hình.", 403)
        if not GATE.acquire(blocking=False):
            raise PreviewError("OSDMAP_BUSY", "Một kịch bản đang được tính; thử lại sau.", 429)
        job = None
        try:
            started = datetime.now(timezone.utc).isoformat()
            context_response = self._client().request('ceph.osdmap_preview_context', timeout_seconds=35)
            if context_response.get('fsid') != self.settings.ceph_expected_fsid:
                raise PreviewError('FSID_MISMATCH', 'FSID nguồn khác cấu hình.')
            preview_context = context_response['data']
            if not preview_context.get('mons') or any(mon.get('osd_crush_update_weight_set') is not True for mon in preview_context['mons']):
                raise PreviewError('OSDMAP_WEIGHT_SET_MODE_UNSUPPORTED', 'MON chưa được xác minh đồng bộ weight-set. Adapter hiện chỉ hỗ trợ osd_crush_update_weight_set=true.')
            if not preview_context.get('mon_versions') or any(not version.startswith('ceph version 16.2.15 ') for version in preview_context['mon_versions']):
                raise PreviewError('OSDMAP_TOOL_VERSION_UNSUPPORTED', 'Adapter này chỉ đã kiểm cho MON Pacific 16.2.15; chưa dự đoán release khác.')
            identity = self._epoch()
            if pool_id is not None and not any(p.get("pool") == pool_id and p.get("pool_name") in self.settings.upgrade_allowed_pool_set for p in identity.get("pools", [])):
                raise PreviewError("OSDMAP_POOL_REJECTED", "Pool không tồn tại hoặc ngoài phạm vi được phép.", 403)
            if pool_id is None and (not identity.get("pools") or any(
                    p.get("pool_name") not in self.settings.upgrade_allowed_pool_set for p in identity["pools"])):
                raise PreviewError("OSDMAP_POOL_REJECTED", "Phạm vi tất cả pool gồm pool ngoài danh sách được phép; hãy chọn một pool cụ thể.", 403)
            response = self._client().request("ceph.osd_map_export", timeout_seconds=35,
                                              max_response_bytes=24 * 1024 * 1024)
            if response.get("fsid") != self.settings.ceph_expected_fsid:
                raise PreviewError("FSID_MISMATCH", "FSID nguồn khác cấu hình.")
            source = response["data"]
            raw = base64.b64decode(source["map"], validate=True)
            if not 0 < len(raw) <= min(self.settings.osdmap_preview_max_map_bytes, 16 * 1024 * 1024) or hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise PreviewError("OSDMAP_INVALID", "Map rỗng, quá lớn hoặc sai checksum.")
            preview_id = uuid4()
            spool = self.settings.osdmap_preview_spool.resolve()
            job = spool / str(preview_id)
            job.mkdir(mode=0o700)
            queued = {"changes": changes, "pool_id": pool_id, "map": source["map"],
                      "base_sha256": source["sha256"], "fsid": self.settings.ceph_expected_fsid,
                      "allowed_pool_ids": [p["pool"] for p in identity.get("pools", [])
                                           if p.get("pool_name") in self.settings.upgrade_allowed_pool_set],
                      "queued_at": time.time()}
            temporary = job / "request.tmp"
            temporary.write_text(json.dumps(queued), encoding="utf-8")
            temporary.replace(job / "request.json")
            deadline = time.monotonic() + self.settings.osdmap_preview_timeout_seconds
            while not (job / "result.json").exists():
                if time.monotonic() >= deadline:
                    raise PreviewError("OSDMAP_TIMEOUT", "Mô phỏng vượt thời gian cho phép.", 503)
                time.sleep(0.2)
            target = job / "result.json"
            if target.is_symlink() or target.stat().st_size > 32 * 1024 * 1024:
                raise PreviewError("OSDMAP_OUTPUT_LIMIT", "Kết quả quá lớn; chọn một pool.", 413)
            output = json.loads(target.read_text(encoding="utf-8"))
            worker_result = self._worker_result(output)
            self._validate_result_identity(worker_result, capabilities, pool_id)
            result = {**worker_result, "id": str(preview_id), "kind": "OSDMAP_PREVIEW", "schema_version": 1,
                      "label": "Dự đoán — chưa áp dụng", "cluster_id": self.settings.cluster_id,
                      "fsid": self.settings.ceph_expected_fsid, "started_at": started,
                      "completed_at": datetime.now(timezone.utc).isoformat(), "changes": changes,
                      "base_sha256": source["sha256"], "base_map_base64": source["map"],
                      "worker_capabilities": capabilities,
                      "cluster_preview_context": preview_context,
                      "limitations": ["Chỉ mô phỏng CRUSH weight; không thay reweight hoặc primary-affinity.",
                          "Giữ pg_temp, primary_temp và upmap; CRUSH weight-set được đồng bộ theo thao tác native của osdmaptool Pacific.",
                          "Đây là CRUSH reweight native (có đồng bộ weight-set), không phải thay canonical weight trong khi cố giữ compat weight-set độc lập.",
                          "PG/shard thay đổi không tương đương số byte, thời gian recovery hoặc hiệu năng.",
                          "Chỉ pool replicated đã được hỗ trợ; pool EC chưa được nghiệm thu và sẽ bị từ chối.",
                          "Cảnh báo mapping thiếu thành viên không phải HEALTH của cluster; chưa kiểm topology/failure-domain độc lập.",
                          "Phân bố OSD thống kê acting của phạm vi đã chọn, bao gồm cả OSD ngoài tập thay đổi.",
                          "Kịch bản chỉ nằm trong bộ nhớ osdmaptool; không có map ứng viên được áp dụng."]}
            result = self._freshness(result)
            artifact = self._store().put_json(result, cluster_id=self.settings.cluster_id,
                                              session_id=preview_id, run_id=preview_id)
            self.repository.save(result, artifact, actor)
            return {k: v for k, v in result.items() if k != "base_map_base64"}
        except ExecutorClientError as exc:
            raise PreviewError(exc.code, "Không đọc được OSDMap mới từ Ceph.", 503) from None
        finally:
            # Only this generated UUID child; durable evidence remains in the artifact store.
            if job is not None and job.parent == self.settings.osdmap_preview_spool.resolve() and job.exists():
                shutil.rmtree(job)
            GATE.release()

    def get(self, preview_id, *, refresh=True):
        row = self.repository.get(preview_id, self.settings.cluster_id, self.settings.ceph_expected_fsid)
        if not row:
            raise PreviewError("OSDMAP_NOT_FOUND", "Không tìm thấy kịch bản trong cluster này.", 404)
        result = self._store().read_json(row["uri"], expected_sha256=row["sha256"], expected_size_bytes=row["size_bytes"])
        if result.get("id") != str(preview_id) or result.get("fsid") != self.settings.ceph_expected_fsid:
            raise PreviewError("OSDMAP_ARTIFACT_INVALID", "Kịch bản không khớp danh tính đã lưu.")
        result.pop("base_map_base64", None)
        result["artifact_sha256"] = row["sha256"]
        return self._freshness(result) if refresh else result
