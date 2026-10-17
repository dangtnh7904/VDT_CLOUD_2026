import { useEffect, useRef, useState } from "react";
import { api, downloadAttachment } from "./api";
import { DataDetails, Pagination } from "./DaemonWorkbench";
import { SourceWarning } from "./SourceWarning";
import { localTime, mappingValidationMessage, pageRows, reconcileWeightInputs, validateWeights, type Daemon } from "./as-is-contracts";
import { createRequestScope } from "./request-scope";

type Placement = { raw: number[]; up: number[]; acting: number[]; up_primary: number; acting_primary: number };
type MappingWarning = { pgid: string; set: "raw" | "up" | "acting"; code: string; expected_members: number; assigned_members: number };
type ToolIdentity = { osdmaptool_sha256: string; crushtool_sha256: string };
type Preview = { id: string; fsid: string; base_epoch: number; current_epoch: number | null; stale: boolean | null; tool_version: string; parser_version?: number; tool_binary_sha256?: ToolIdentity; completed_at: string; base_sha256: string; scope: { pool_id: number | null; pg_count: number; pool_types?: string[] }; mapping_validation?: { quality: "VALID" | "PARTIAL"; before_warnings: MappingWarning[]; after_warnings: MappingWarning[]; failure_domain_checked: boolean }; crush_effects?: { weight_sets_changed: boolean; effective_weights: unknown[] }; summary: { changed_pgs: number; primary_changes: number; membership_changes: number; order_changes: number }; pg_changes: { pgid: string; before: Placement; after: Placement; primary_changed: boolean; membership_changed: boolean; order_changed: boolean }[]; osd_distribution: { osd_id: number; before_pg: number; after_pg: number; delta_pg: number; before_primary: number; after_primary: number; delta_primary: number }[]; limitations: string[] };

export function OsdMapPreview({ daemons, selectedKeys }: { daemons: Daemon[]; selectedKeys: string[] }) {
  const [capability, setCapability] = useState<{ available: boolean; tool_version?: string; reason?: string; pool_types?: string[]; parser_version?: number; tool_binary_sha256?: ToolIdentity }>();
  const [keys, setKeys] = useState(selectedKeys.filter(key => key.startsWith("osd.")));
  const [weights, setWeights] = useState<Record<string, string>>(Object.fromEntries(daemons.map(row => [row.key, String(row.fields.crush_weight ?? "")])));
  const [pool, setPool] = useState(""); const [result, setResult] = useState<Preview>();
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [page, setPage] = useState(1);
  const requests = useRef(createRequestScope());
  const previousDefaults = useRef<Record<string, string>>({});
  const catalogue = JSON.stringify(daemons.map(row => [row.key, row.fields.crush_weight, row.observed_at]));
  useEffect(() => { let active = true; api<typeof capability>("/v1/osdmap-previews/capabilities").then(value => { if (active) setCapability(value); }).catch(reason => { if (active) setError(reason.message); }); return () => { active = false; }; }, []);
  const invalidate = () => { setResult(undefined); setNotice(""); setPage(1); };
  useEffect(() => {
    requests.current.invalidate(); setBusy(false); invalidate();
    const defaults = Object.fromEntries(daemons.map(row => [row.key, String(row.fields.crush_weight ?? "")]));
    const previous = previousDefaults.current;
    setKeys(current => current.filter(key => Object.hasOwn(defaults, key)));
    setWeights(current => reconcileWeightInputs(current, previous, defaults));
    previousDefaults.current = defaults;
    return () => requests.current.invalidate();
  }, [catalogue]);
  const action = async (run: (current: () => boolean) => Promise<void>) => {
    const token = requests.current.begin(); if (token === undefined) return;
    const current = () => requests.current.current(token);
    setBusy(true); setError("");
    try { await run(current); } catch (reason) { if (current()) setError((reason as Error).message); }
    finally { if (requests.current.finish(token)) setBusy(false); }
  };
  const calculate = async () => {
    const changes = keys.map(key => ({ osd_id: Number(key.slice(4)), crush_weight: Number(weights[key]) }));
    const invalid = keys.some(key => !weights[key]?.trim()) ? "Nhập CRUSH weight cho từng OSD được chọn." : validateWeights(changes);
    if (invalid || (pool && (!Number.isSafeInteger(Number(pool)) || Number(pool) < 0))) { setError(invalid || "Pool ID phải là số nguyên không âm."); return; }
    await action(async current => { invalidate(); const value = await api<Preview>("/v1/osdmap-previews", { method: "POST", body: JSON.stringify({ changes, pool_id: pool ? Number(pool) : null }) }); if (current()) setResult(value); });
  };
  const exportResult = async () => { if (!result) return; await action(async current => { const filename = await downloadAttachment(`/v1/osdmap-previews/${result.id}/export`, { method: "POST" }); if (current()) setNotice(`Đã tải ${filename}.`); }); };
  const checkEpoch = async () => { if (!result) return; await action(async current => { const value = await api<Preview>(`/v1/osdmap-previews/${result.id}`, { cache: "no-store" }); if (current()) setResult(value); }); };
  return <section className="panel osdmap-preview"><span className="eyebrow">MÔ PHỎNG PLACEMENT CỤC BỘ</span><h2>Xem trước thay đổi OSDMap</h2><p>Đọc map mới và tính tác động của CRUSH weight dự định thay đổi. Công cụ giữ override PG; weight-set liên quan được đồng bộ theo CRUSH reweight native Pacific.</p>
    <p className="notice">Dự đoán — chưa áp dụng. Chỉ hỗ trợ pool replicated; pool EC bị từ chối, kể cả khi chọn tất cả pool có chứa EC. Kết quả PG/primary không dự đoán hiệu năng hoặc thời gian recovery.</p>
    {error && <p className="notice error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <p>{capability?.available ? `Công cụ: ${capability.tool_version}` : capability?.reason || "Đang kiểm tra công cụ…"}</p>
    {capability?.available && <DataDetails title="Phiên bản parser, loại pool đã hỗ trợ và SHA-256 công cụ" data={{ pool_types: capability.pool_types, parser_version: capability.parser_version, tool_binary_sha256: capability.tool_binary_sha256 }} />}
    <div className="table-wrap"><table><thead><tr><th>Chọn</th><th>OSD</th><th>Weight hiện tại</th><th>CRUSH weight giả định</th></tr></thead><tbody>{daemons.map(row => <tr key={row.key}><td><input type="checkbox" aria-label={`Mô phỏng ${row.key}`} disabled={busy} checked={keys.includes(row.key)} onChange={event => { setKeys(current => event.target.checked ? [...current, row.key] : current.filter(key => key !== row.key)); invalidate(); }} /></td><td>{row.key}</td><td>{String(row.fields.crush_weight ?? "Chưa có dữ liệu")}</td><td><input aria-label={`CRUSH weight giả định ${row.key}`} type="number" min="0" max="32767" step="any" disabled={busy || !keys.includes(row.key)} value={weights[row.key] || ""} onChange={event => { setWeights(current => ({ ...current, [row.key]: event.target.value })); invalidate(); }} /></td></tr>)}</tbody></table></div>
    <label>Pool ID (để trống = tất cả pool)<input type="number" min="0" step="1" value={pool} disabled={busy} onChange={event => { setPool(event.target.value); invalidate(); }} /></label>
    <div className="toolbar"><button className="button primary" disabled={busy || !capability?.available || !keys.length} onClick={() => void calculate()}>{busy ? "Đang tính tác động…" : "Tính tác động"}</button>{result && <><button className="button ghost" disabled={busy} onClick={() => void exportResult()}>Xuất dự đoán đã lưu</button><button className="button ghost" disabled={busy} onClick={() => void checkEpoch()}>Kiểm tra epoch hiện tại</button></>}</div>
    {result && <><p><strong>Dự đoán — chưa áp dụng</strong> · {localTime(result.completed_at)}</p><p>Map nguồn epoch {result.base_epoch} · Epoch hiện tại {result.current_epoch ?? "Chưa xác minh"} · {result.stale === true ? "Map nguồn đã cũ; hãy tính lại." : result.stale === null ? "Chưa xác minh độ mới của map." : "Epoch khớp tại lúc kiểm tra."}</p><p>Đã tính {result.scope.pg_count} PG {result.scope.pool_id === null ? "trên toàn bộ pool" : `trong pool ${result.scope.pool_id}`} · {result.summary.changed_pgs} PG thay đổi · {result.summary.primary_changes} đổi primary (raw/up/acting) · {result.summary.membership_changes} đổi thành viên · {result.summary.order_changes} đổi thứ tự.</p>
      <div className={`notice${result.mapping_validation?.quality === "PARTIAL" ? " error" : ""}`} role={result.mapping_validation?.quality === "PARTIAL" ? "alert" : "status"}><p>{mappingValidationMessage(result.mapping_validation?.quality)}</p>{result.mapping_validation && <p>Cảnh báo map gốc: {result.mapping_validation.before_warnings.length} · Map giả định: {result.mapping_validation.after_warnings.length}. Không có kiểm chứng failure domain độc lập trong bản này.</p>}</div>
      <DataDetails title="Cảnh báo PG thiếu thành viên và bằng chứng kiểm mapping" data={{ mapping_validation: result.mapping_validation, pool_types: result.scope.pool_types, parser_version: result.parser_version, tool_binary_sha256: result.tool_binary_sha256 }} />
      <p>Weight-set có thay đổi: {result.crush_effects?.weight_sets_changed === undefined ? "Chưa ghi nhận trong bản cũ" : result.crush_effects.weight_sets_changed ? "Có" : "Không"}.</p><DataDetails title="CRUSH weight thực dùng sau lượng tử hóa" data={result.crush_effects?.effective_weights} /><h3>Phân bố acting trên OSD</h3><div className="table-wrap"><table><thead><tr><th>OSD</th><th>PG gốc</th><th>PG giả định</th><th>Chênh PG</th><th>Primary gốc</th><th>Primary giả định</th><th>Chênh primary</th></tr></thead><tbody>{result.osd_distribution.map(row => <tr key={row.osd_id}><td>osd.{row.osd_id}</td><td>{row.before_pg}</td><td>{row.after_pg}</td><td>{row.delta_pg}</td><td>{row.before_primary}</td><td>{row.after_primary}</td><td>{row.delta_primary}</td></tr>)}</tbody></table></div>
      <h3>PG thay đổi</h3><div className="table-wrap"><table><thead><tr><th>PG</th><th>Map gốc</th><th>Kịch bản giả định</th><th>Loại thay đổi</th></tr></thead><tbody>{pageRows(result.pg_changes, page).map(row => <tr key={row.pgid}><td>{row.pgid}</td><td><DataDetails title="Raw / up / acting gốc" data={row.before} /></td><td><DataDetails title="Raw / up / acting giả định" data={row.after} /></td><td>{[row.membership_changed && "Thành viên", row.order_changed && "Thứ tự", row.primary_changed && "Primary"].filter(Boolean).join(", ")}</td></tr>)}</tbody></table></div>{!result.pg_changes.length && <p>Không có PG thay đổi trong phạm vi đã tính.</p>}<Pagination page={page} total={result.pg_changes.length} onPage={setPage} />
      <SourceWarning limitations={result.limitations} /></>}
  </section>;
}
