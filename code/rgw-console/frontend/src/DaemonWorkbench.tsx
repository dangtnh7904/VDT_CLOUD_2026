import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownToLine, ChevronLeft, ChevronRight, RefreshCw, Save, X } from "lucide-react";
import { api, downloadAttachment } from "./api";
import { DAEMON_TYPES, PHASE_LABELS, labelQuality, localTime, pageRows, showValue, toggleKeys, type Daemon, type Observation, type Phase } from "./as-is-contracts";
import { OsdMapPreview } from "./OsdMapPreview";
import { retryFreshRead } from "./fresh-read";
import { SourceWarning } from "./SourceWarning";

export function Pagination({ page, total, onPage }: { page: number; total: number; onPage: (value: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / 10));
  return <div className="as-is-pagination"><span>{total} mục · 10 mục/trang · Trang {page}/{pages}</span><div><button className="button ghost" aria-label="Trang trước" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft /></button><button className="button ghost" aria-label="Trang sau" disabled={page >= pages} onClick={() => onPage(page + 1)}><ChevronRight /></button></div></div>;
}
export function DataDetails({ data, title }: { data: unknown; title: string }) { const [open, setOpen] = useState(false); return <details className="as-is-details" onToggle={event => setOpen(event.currentTarget.open)}><summary>{title}</summary>{open && <pre className="preview">{JSON.stringify(data, null, 2)}</pre>}</details>; }
function record(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
export function EnvironmentSummary({ data, diagnostics = false }: { data: unknown; diagnostics?: boolean }) {
  const environment = record(data); if (!Object.keys(environment).length) return null;
  const host = record(environment.host), os = record(host.os), kernel = record(host.kernel), python = record(environment.python), shell = record(environment.shell), clock = record(environment.clock);
  const fields = { "Máy SSH client": host.hostname, "Hệ điều hành": os.pretty_name ?? os.name, "Kernel": kernel.release, "Kiến trúc": kernel.machine, "Python": python.version, "Shell được khai báo": shell.configured_path, "Chương trình cha quan sát được": shell.observed_parent_executable, "NTP được bật": clock.ntp_enabled, "Đồng hồ đã đồng bộ": clock.synchronized, "Múi giờ máy SSH": clock.time_zone };
  return <section className="as-is-observation"><h3>Môi trường máy SSH client · {labelQuality(String(environment.quality || "UNKNOWN"))}<SourceWarning environment={environment} /></h3><div className="as-is-fields">{Object.entries(fields).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{showValue(value)}</dd></div>)}</div><div className="table-wrap"><table><thead><tr><th>Công cụ client</th><th>Phiên bản quan sát</th><th>Chất lượng</th></tr></thead><tbody>{Object.entries(record(environment.tools)).map(([name, value]) => { const tool = record(value); return <tr key={name}><td>{name}</td><td>{showValue(tool.version)}</td><td>{labelQuality(String(tool.quality || "UNKNOWN"))}</td></tr>; })}</tbody></table></div>{diagnostics && <DataDetails title="Bằng chứng môi trường, lệnh đọc và thời điểm nguồn" data={environment} />}</section>;
}
export function ObservationDetails({ observation, daemonType = "", daemonKey = "", diagnostics = false, expanded = false }: { observation: Observation; daemonType?: string; daemonKey?: string; diagnostics?: boolean; expanded?: boolean }) {
  const daemons = observation.daemons.filter(row => (!daemonType || row.type === daemonType) && (!daemonKey || row.key === daemonKey));
  return <div className="as-is-observation"><p><strong>{observation.kind === "AS_IS_COLLECTION" ? "Dữ liệu đã lưu" : "Dữ liệu thu theo yêu cầu"}</strong> · {labelQuality(observation.quality)} · {localTime(observation.started_at)} → {localTime(observation.completed_at)}<SourceWarning observation={{...observation, daemons}} /></p><p className="muted">FSID: {observation.fsid}{observation.phase ? ` · ${PHASE_LABELS[observation.phase]}` : ""}</p>{(daemonType || daemonKey) && <p>{daemons.length}/{observation.daemons.length} daemon trong bộ gốc khớp bộ lọc{daemonType ? ` ${daemonType.toUpperCase()}` : ""}{daemonKey ? ` · ${daemonKey}` : ""}.</p>}{observation.deleted_at && <p className="notice error">Bộ As-is này đã bị xóa mềm.</p>}{diagnostics && <DataDetails title="Thông tin hệ thống và nguồn thu" data={{ system: observation.system, sources: observation.sources, limitations: observation.limitations, missing_daemon_keys: observation.missing_daemon_keys, sha256: observation.sha256 }} />}{daemons.map(row => <details className="as-is-details" key={row.key} open={expanded || undefined}><summary>{row.key} · {labelQuality(row.quality)}</summary><DaemonDetails daemon={row} /></details>)}</div>;
}
function DaemonDetails({ daemon }: { daemon: Daemon }) {
  return <><p>{localTime(daemon.observed_at)} · {labelQuality(daemon.quality)}<SourceWarning daemon={daemon} /></p><div className="as-is-fields">{Object.entries(daemon.fields).filter(([key]) => !["warnings", "raw_evidence", "evidence", "payload", "sources", "limitations"].includes(key)).map(([key, value]) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{value !== null && typeof value === "object" ? <DataDetails title={`Xem ${fieldLabel(key)}`} data={value} /> : showValue(value)}</dd></div>)}</div><MetricTable metrics={daemon.metrics || []} /></>;
}
export function MetricTable({ metrics }: { metrics: Daemon["metrics"] }) {
  return metrics.length ? <div className="table-wrap"><table><thead><tr><th>Chỉ số</th><th>Giá trị</th><th>Đơn vị</th><th>Thời điểm / khoảng đo</th><th>Chất lượng</th></tr></thead><tbody>{metrics.map((metric, index) => <tr key={`${metric.metric_id}:${index}`}><td title={metric.metric_id}>{fieldLabel(metric.metric_id)}</td><td>{typeof metric.value === "number" ? Number(metric.value.toFixed(3)).toLocaleString("vi-VN") : showValue(metric.value)}</td><td>{metric.unit || "—"}</td><td>{localTime(metric.observed_at)}{metric.window_seconds != null && <small className="block">Cửa sổ {metric.window_seconds} giây</small>}</td><td title={metric.reason ? reasonLabel(metric.reason) : undefined}>{labelQuality(metric.quality)}</td></tr>)}</tbody></table></div> : <p className="muted">Chưa có mẫu chỉ số cho daemon này.</p>;
}
export function DaemonWorkbench({ mode = "metrics", canSave = true, onCollected }: { mode?: "overview" | "metrics" | "inventory"; canSave?: boolean; onCollected?: (value: Observation) => void }) {
  const [observation, setObservation] = useState<Observation>();
  const [type, setType] = useState(""); const [search, setSearch] = useState(""); const [host, setHost] = useState(""); const [status, setStatus] = useState("");
  const [page, setPage] = useState(1); const [selected, setSelected] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>("BEFORE"); const [note, setNote] = useState("");
  const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [detail, setDetail] = useState<Daemon>(); const [previewOpen, setPreviewOpen] = useState(false);
  const [selectedObservation, setSelectedObservation] = useState<Observation>();
  const activeRequest = useRef<AbortController | undefined>(undefined); const mounted = useRef(false); const inventory = mode === "inventory";
  const rows = useMemo(() => (observation?.daemons || []).filter(row => (!type || row.type === type) && (!search || `${row.name} ${row.key}`.toLowerCase().includes(search.toLowerCase())) && (!host || showValue(row.fields.host ?? row.fields.hostname).toLowerCase().includes(host.toLowerCase())) && (!status || showValue(row.fields.status ?? row.fields.state ?? row.fields.role).toLowerCase().includes(status.toLowerCase()))).sort((a, b) => `${a.type}:${a.id}`.localeCompare(`${b.type}:${b.id}`, "en", { numeric: true })), [observation, type, search, host, status]);
  const visible = pageRows(rows, page);
  const scope = (explicitKeys?: string[]) => ({ ...(explicitKeys?.length ? { daemon_keys: explicitKeys } : selected.length ? { daemon_keys: selected } : type ? { daemon_types: [type] } : {}), deep: inventory });
  const action = async (name: string, run: (signal: AbortSignal, current: () => boolean) => Promise<void>) => {
    if (activeRequest.current) return;
    const controller = new AbortController(); activeRequest.current = controller;
    const current = () => mounted.current && activeRequest.current === controller && !controller.signal.aborted;
    setBusy(name); setError(""); setNotice("");
    try { await run(controller.signal, current); }
    catch (caught) { if (current()) setError((caught as Error).message); }
    finally { if (activeRequest.current === controller) { activeRequest.current = undefined; if (mounted.current) setBusy(""); } }
  };
  const freshRead = <T,>(read: () => Promise<T>, signal: AbortSignal) => retryFreshRead(read, signal, attempt => {
    if (mounted.current && !signal.aborted) setNotice(`Các lần thu trước đang hoàn tất. Tự thử đọc mới lần ${attempt}/2; mỗi lần đọc vẫn lấy dữ liệu trực tiếp từ Ceph.`);
  });
  const load = (initial = false) => action("view", async (signal, current) => {
    setDetail(undefined);
    // Opening/navigating the inventory only reads the live catalogue. Deep OSD
    // evidence is fetched explicitly for a selected daemon, export or saved As-is.
    const body = JSON.stringify({ ...(initial || !type ? {} : { daemon_types: [type] }), deep: false });
    const result = await freshRead(() => api<Observation>("/v1/as-is/observe", { method: "POST", cache: "no-store", signal, body }), signal);
    if (!current()) return;
    setObservation(result); setPage(1); setNotice(`Đã đọc mới ${result.daemons.length} daemon. Kết thúc: ${localTime(result.completed_at)}.`);
  });
  useEffect(() => {
    mounted.current = true; setObservation(undefined); setSelected([]); setDetail(undefined); setPage(1); setBusy("view"); setError(""); setNotice("");
    // A cancelled first StrictMode effect must not leave a source read running.
    const timer = window.setTimeout(() => void load(true), 0);
    return () => { window.clearTimeout(timer); mounted.current = false; activeRequest.current?.abort(); activeRequest.current = undefined; };
  }, [mode]);
  useEffect(() => { setPage(1); }, [type, search, host, status]);
  useEffect(() => { setSelectedObservation(undefined); }, [selected.join("|"), mode]);
  useEffect(() => { setPage(value => Math.min(value, Math.max(1, Math.ceil(rows.length / 10)))); }, [rows.length]);
  const exportFresh = () => action("export", async (signal, current) => {
    const body = JSON.stringify(scope(selected.length ? selected : rows.map(row => row.key)));
    const filename = await freshRead(() => downloadAttachment("/v1/as-is/export", { method: "POST", signal, body }), signal);
    if (current()) setNotice(`Đã thu mới và tải ${filename}. Trình duyệt chọn thư mục lưu.`);
  });
  const collect = (download: boolean) => action("collect", async (signal, current) => {
    if (!canSave) return;
    const saved = await api<Observation>("/v1/as-is/collections", { method: "POST", signal, headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ daemon_keys: selected, phase, note: note.trim() }) });
    if (!current()) return;
    onCollected?.(saved); setNotice(`Đã lưu bộ As-is ${saved.id}: ${labelQuality(saved.quality)}. ${localTime(saved.completed_at)}.`);
    if (download) { const filename = await downloadAttachment(`/v1/as-is/collections/${saved.id}/export`, { signal }); if (current()) setNotice(`Đã lưu và tải ${filename} từ cùng một lần thu.`); }
  });
  const viewDaemon = (key: string) => action("detail", async (signal, current) => {
    setDetail(undefined);
    const result = await freshRead(() => api<Observation>("/v1/as-is/observe", { method: "POST", cache: "no-store", signal, body: JSON.stringify({ daemon_keys: [key], deep: inventory }) }), signal);
    if (!current()) return;
    const daemon = result.daemons.find(row => row.key === key);
    if (!daemon) throw new Error(`Nguồn không trả về ${key}. Không sử dụng dữ liệu cũ thay thế.`);
    setDetail(daemon); setNotice(`Đã đọc mới ${key}: ${localTime(result.completed_at)}.`);
  });
  const viewSelected = () => action("selection", async (signal, current) => {
    if (!selected.length) return;
    setSelectedObservation(undefined);
    const body = JSON.stringify({ daemon_keys: selected, deep: false });
    const result = await freshRead(() => api<Observation>("/v1/as-is/observe", { method: "POST", cache: "no-store", signal, body }), signal);
    if (current()) { setSelectedObservation(result); setNotice(`Đã đọc chỉ số mới của ${result.daemons.length} daemon đã chọn. ${localTime(result.completed_at)}.`); }
  });
  return <div className="cluster-metrics-workspace as-is-workspace">
    <section className="panel as-is-hero"><div className="as-is-hero-heading"><div><span className="eyebrow">ĐỌC TRỰC TIẾP TỪ CỤM</span><h2>{inventory ? "Thu thập hiện trạng (As-is)" : mode === "overview" ? "Tổng quan hệ thống" : "Chỉ số cụm và daemon"}</h2><p>{inventory ? "Chọn các daemon cần theo dõi và lưu hiện trạng Trước, Trong hoặc Sau nâng cấp. OSD có thêm dữ liệu chuyên sâu." : "Mỗi lần bấm Xem hoặc Xuất dữ liệu mới đều đọc lại nguồn. Chỉ số có thời điểm và khoảng đo riêng."}</p></div><span className="as-is-chip">Chỉ đọc Ceph</span></div>
      <div className="toolbar"><button className="button primary" disabled={Boolean(busy)} onClick={() => void load()}><RefreshCw className={busy === "view" ? "spin" : ""} />{busy === "view" ? "Đang lấy dữ liệu…" : inventory ? "Xem hiện trạng" : "Xem dữ liệu mới"}</button><button className="button ghost" disabled={Boolean(busy) || !observation || (!rows.length && !selected.length)} onClick={() => void exportFresh()}><ArrowDownToLine />{busy === "export" ? "Đang thu mới và xuất…" : "Xuất dữ liệu mới (JSON)"}</button><button className="button ghost" disabled={Boolean(busy)} onClick={() => { setSelected([]); setType(""); setSearch(""); setHost(""); setStatus(""); void load(true); }}>Đọc lại toàn bộ danh mục</button></div>
      {observation && <p className="muted as-is-scope-note">Xem dữ liệu mới: {type ? `danh mục ${type.toUpperCase()}` : "toàn bộ danh mục"}. Xuất dữ liệu mới: {selected.length ? `${selected.length} daemon đã chọn` : "các daemon khớp bộ lọc"}.<SourceWarning observation={observation} /></p>}
    </section>
    {error && <div className="notice error" role="alert"><strong>Không thể hoàn tất lần thu mới.</strong><p>{error}</p>{observation ? <p>Dữ liệu còn hiển thị là lần trước: {localTime(observation.completed_at)}. Bấm Xem dữ liệu mới để thử lại.</p> : <p>Bấm {inventory ? "Xem hiện trạng" : "Xem dữ liệu mới"} để thử lại.</p>}</div>}{notice && <div className="notice" role="status">{notice}</div>}
    {busy && <div className="as-is-read-progress" role="status"><RefreshCw className="spin" aria-hidden="true" /><div><strong>{busy === "collect" ? "Đang thu và lưu hiện trạng" : busy === "export" ? "Đang đọc nguồn và chuẩn bị tệp" : busy === "detail" ? "Đang đọc daemon đã chọn" : "Đang đọc nguồn Ceph"}</strong><p>Đang xác minh cụm và lấy dữ liệu trực tiếp. Các nguồn có thời điểm đo riêng; kết quả sẽ hiển thị khi lần thu hoàn tất.</p></div></div>}
    {observation ? <div className="metrics"><div className="metric"><span>Cụm đã xác minh</span><strong>{observation.cluster_id}</strong><small>FSID: {observation.fsid}</small></div><div className="metric"><span>Chất lượng lần thu</span><strong>{labelQuality(observation.quality)}</strong><small>{localTime(observation.completed_at)}</small></div><div className="metric"><span>Phạm vi đã đọc</span><strong>{observation.daemons.length} daemon</strong><small>Không tính host, pool hoặc hệ thống thành daemon</small></div></div> : !busy && !error && <div className="notice">Chưa thu dữ liệu. Bấm {inventory ? "Xem hiện trạng" : "Xem dữ liệu mới"} để đọc trực tiếp từ Ceph.</div>}
    {observation && <section className="panel"><h3>Hệ thống / cụm</h3><div className="as-is-fields">{Object.entries(observation.system || {}).filter(([, value]) => value === null || typeof value !== "object").map(([key, value]) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{showValue(value)}</dd></div>)}</div><MetricTable metrics={(observation.system.metrics || []) as Daemon["metrics"]} /></section>}
    <section className="panel"><div className="section-head"><div><h3>Danh sách daemon</h3><p>{rows.length} daemon khớp bộ lọc · Đã chọn {selected.length} daemon, giữ lựa chọn qua các trang.</p></div></div>
      <div className="form-grid as-is-filters"><label>Loại daemon<select value={type} disabled={Boolean(busy)} onChange={event => setType(event.target.value)}><option value="">Tất cả loại đã hỗ trợ</option>{DAEMON_TYPES.map(value => <option key={value} value={value} disabled={observation?.capabilities[value] === false}>{value.toUpperCase()}{observation?.capabilities[value] === false ? " — chưa hỗ trợ" : ""}</option>)}</select></label><label>Tìm tên / ID<input value={search} disabled={Boolean(busy)} onChange={event => setSearch(event.target.value)} placeholder="Ví dụ: osd.2" /></label><label>Máy chủ<input value={host} disabled={Boolean(busy)} onChange={event => setHost(event.target.value)} /></label><label>Trạng thái<input value={status} disabled={Boolean(busy)} onChange={event => setStatus(event.target.value)} /></label></div>
      <div className="as-is-selection"><button className="button ghost" disabled={!visible.length || Boolean(busy)} onClick={() => setSelected(current => toggleKeys(current, visible.map(row => row.key), true))}>Chọn {visible.length} hàng trang này</button><button className="button ghost" disabled={!rows.length || Boolean(busy)} onClick={() => setSelected(current => toggleKeys(current, rows.map(row => row.key), true))}>Chọn tất cả {rows.length} kết quả lọc</button><button className="button ghost" disabled={!selected.length || Boolean(busy)} onClick={() => setSelected([])}>Bỏ chọn tất cả</button></div>
      {!inventory && <div className="as-is-selection-actions"><strong>{selected.length ? `${selected.length} daemon đã chọn` : "Chọn daemon để xem hoặc xuất chỉ số riêng"}</strong><p>Chọn một hoặc nhiều daemon, rồi bấm nút bên dưới. Kết quả đọc mới hiện riêng; danh mục phía trên không bị thu hẹp. Không thực hiện nâng cấp.</p><div className="toolbar"><button className="button primary" disabled={!selected.length || Boolean(busy)} onClick={() => void viewSelected()}><RefreshCw />{busy === "selection" ? "Đang đọc chỉ số đã chọn…" : `Xem chỉ số mới (${selected.length} daemon)`}</button><button className="button ghost" disabled={!selected.length || Boolean(busy)} onClick={() => void exportFresh()}><ArrowDownToLine />{busy === "export" ? "Đang thu mới và xuất…" : `Xuất ${selected.length} daemon (JSON)`}</button></div></div>}
      {selectedObservation && <div className="as-is-selection-result" role="region" aria-label="Chỉ số các daemon đã chọn"><div className="section-head"><h3>Chỉ số mới của {selectedObservation.daemons.length} daemon đã chọn</h3><button className="button ghost" onClick={() => setSelectedObservation(undefined)}>Đóng</button></div><ObservationDetails observation={selectedObservation} expanded /></div>}
      {selected.length > 0 && <details className="as-is-details"><summary>Danh sách đích đã chọn ({selected.length})</summary><div className="as-is-chips">{selected.map(key => <button className="as-is-chip" key={key} disabled={Boolean(busy)} onClick={() => setSelected(current => current.filter(value => value !== key))}>{key}<X size={12} /></button>)}</div></details>}
      <div className="table-wrap"><table><thead><tr><th>Chọn</th><th>Daemon</th><th>Loại</th><th>Máy chủ</th><th>Trạng thái</th><th>Phiên bản</th><th>Chất lượng</th><th></th></tr></thead><tbody>{visible.map(row => <tr key={row.key}><td><input type="checkbox" aria-label={`Chọn ${row.key}`} checked={selected.includes(row.key)} disabled={Boolean(busy)} onChange={event => setSelected(current => toggleKeys(current, [row.key], event.target.checked))} /></td><td><strong>{row.name || row.key}</strong><small className="block">{row.key}</small></td><td>{row.type.toUpperCase()}</td><td>{showValue(row.fields.host ?? row.fields.hostname)}</td><td>{showValue(row.fields.status ?? row.fields.state ?? row.fields.role ?? (row.fields.up !== undefined ? { up: row.fields.up, in: row.fields.in } : undefined))}</td><td>{showValue(row.fields.ceph_version_short ?? row.fields.version ?? row.fields.ceph_version)}</td><td>{labelQuality(row.quality)}</td><td><button className="button ghost" disabled={Boolean(busy)} onClick={() => void viewDaemon(row.key)}>Xem mới</button></td></tr>)}</tbody></table></div>
      {!rows.length && <p className="empty-state">{busy ? "Đang đọc danh mục daemon…" : "Không có daemon khớp bộ lọc hoặc nguồn chưa trả dữ liệu."}</p>}<Pagination page={page} total={rows.length} onPage={setPage} />
      {inventory && <><div className="form-grid"><label>Giai đoạn<select value={phase} disabled={Boolean(busy)} onChange={event => setPhase(event.target.value as Phase)}>{Object.entries(PHASE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Ghi chú (tùy chọn)<input maxLength={1000} value={note} disabled={Boolean(busy)} onChange={event => setNote(event.target.value)} /></label></div><div className="toolbar"><button className="button primary" disabled={!canSave || Boolean(busy) || !selected.length} onClick={() => void collect(false)}><Save />{busy === "collect" ? "Đang thu thập…" : "Lấy As-is"}</button><button className="button ghost" disabled={!canSave || Boolean(busy) || !selected.length} onClick={() => void collect(true)}><ArrowDownToLine />Lấy As-is và xuất</button><button className="button ghost" disabled={!canSave || Boolean(busy)} onClick={() => setPreviewOpen(value => !value)}>Xem trước thay đổi OSDMap</button></div><p className="muted">Chọn daemon chỉ xác định phạm vi thu thập. Nhãn giai đoạn không xác nhận thao tác nâng cấp đã thực hiện.</p></>}
    </section>
    {detail && <section className="panel"><div className="section-head"><h3>{detail.key} — lần đọc mới riêng</h3><button className="button ghost" onClick={() => setDetail(undefined)}>Đóng</button></div><DaemonDetails daemon={detail} /></section>}
    {observation?.system.environment != null && <section className="panel"><EnvironmentSummary data={observation.system.environment} /></section>}
    {inventory && previewOpen && <OsdMapPreview daemons={(observation?.daemons || []).filter(row => row.type === "osd")} selectedKeys={selected} />}
  </div>;
}
import { fieldLabel, reasonLabel } from "./labels";
