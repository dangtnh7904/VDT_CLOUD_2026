import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { api, downloadAttachment } from "./api";
import { DaemonWorkbench, EnvironmentSummary, ObservationDetails } from "./DaemonWorkbench";
import { DAEMON_TYPES, PHASE_LABELS, collectionQuery, daemonScopeError, labelQuality, localTime, savedCollectionQuery, scopedDaemonKeys, type CollectionSummary, type Observation } from "./as-is-contracts";
import { CollectionHistoryPager, useCollectionHistory, useDebouncedValue } from "./useCollectionHistory";
import { createRequestScope } from "./request-scope";

export function AsIs() {
  const [revision, setRevision] = useState(0);
  const [latest, setLatest] = useState<Observation>();
  return <div className="stack"><DaemonWorkbench mode="inventory" onCollected={saved => { setLatest(saved); setRevision(value => value + 1); }} />{latest && <section className="cluster-metrics-workspace"><div className="panel"><h3>Bộ As-is vừa lưu</h3><ObservationDetails observation={latest} diagnostics={false} /><EnvironmentSummary data={latest.system.environment} /></div></section>}<CollectionHistory revision={revision} /></div>;
}

export function CollectionHistory({ revision = 0 }: { revision?: number }) {
  const [type, setType] = useState(""); const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [phase, setPhase] = useState(""); const [deleted, setDeleted] = useState(false);
  const [search, setSearch] = useState(""); const [quality, setQuality] = useState(""); const [daemonKey, setDaemonKey] = useState("");
  const [selected, setSelected] = useState<CollectionSummary[]>([]);
  const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [detail, setDetail] = useState<Observation>(); const [targets, setTargets] = useState<CollectionSummary[]>([]);
  const requests = useRef(createRequestScope());
  const invalidDates = Boolean(from && to && from > to);
  const debouncedSearch = useDebouncedValue(search);
  const debouncedDaemonKey = useDebouncedValue(daemonKey.trim());
  const scopeError = daemonScopeError(daemonKey, type);
  const query = invalidDates || scopeError ? "" : collectionQuery({ type, from, to, phase, deleted, search: debouncedSearch, quality, daemonKey: debouncedDaemonKey });
  const history = useCollectionHistory(query, revision);
  const rows = history.items;
  const isBusy = Boolean(busy) || history.loading || daemonKey.trim() !== debouncedDaemonKey;
  const invalidFilters = invalidDates || Boolean(scopeError);
  const scopeActive = Boolean(type || daemonKey.trim());
  const filteredKeys = (row: CollectionSummary) => scopedDaemonKeys(row, type, daemonKey);
  useEffect(() => { requests.current.invalidate(); setBusy(""); setSelected([]); setDetail(undefined); setTargets([]); return () => requests.current.invalidate(); }, [query, revision]);
  const load = () => history.reload();
  const action = async (name: string, run: (current: () => boolean) => Promise<void>) => {
    const token = requests.current.begin(); if (token === undefined) return;
    const current = () => requests.current.current(token);
    setBusy(name); setError(""); setNotice("");
    try { await run(current); } catch (caught) { if (current()) setError((caught as Error).message); } finally { if (requests.current.finish(token)) setBusy(""); }
  };
  const remove = () => action("delete", async current => {
    const deleting = targets;
    const results = await Promise.allSettled(deleting.map(row => api(`/v1/as-is/collections/${row.id}`, { method: "DELETE" })));
    if (!current()) return;
    const count = results.filter(value => value.status === "fulfilled").length;
    const failed = results.flatMap((value, index) => value.status === "rejected" ? [`${deleting[index].id}: ${value.reason?.message || "Xóa thất bại"}`] : []);
    setTargets([]); setSelected([]); setDetail(undefined); await load(); if (!current()) return;
    setNotice(`Đã xóa mềm ${count} bộ As-is. Có thể khôi phục bằng bộ lọc Bao gồm đã xóa.`);
    if (failed.length) setError(failed.join("; "));
  });
  return <div className="cluster-metrics-workspace as-is-workspace"><section className="panel"><div className="section-head"><div><h2>Lịch sử thu thập</h2><p>Xem hoặc xuất lịch sử dùng dữ liệu đã lưu, không thu lại Ceph. Bộ chứa nhiều loại daemon vẫn xuất hiện khi lọc; chỉ daemon khớp bộ lọc được hiển thị. Bộ gốc và mã kiểm tra không thay đổi.</p></div><button className="button ghost" disabled={isBusy || invalidFilters} onClick={() => { setSelected([]); void load(); }}><RefreshCw />Làm mới lịch sử</button></div>
    {(error || history.error) && <div className="notice error" role="alert">{error || history.error}</div>}{notice && <div className="notice" role="status">{notice}</div>}
    <div className="form-grid as-is-filters"><label>Từ ngày (UTC+7)<input type="date" value={from} onChange={event => setFrom(event.target.value)} /></label><label>Đến hết ngày (UTC+7)<input type="date" value={to} onChange={event => setTo(event.target.value)} /></label><label>Loại daemon<select value={type} onChange={event => { setType(event.target.value); setDaemonKey(""); }}><option value="">Tất cả</option>{DAEMON_TYPES.map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select></label><label>Daemon cụ thể (tùy chọn)<input maxLength={132} placeholder="Ví dụ osd.2" value={daemonKey} onChange={event => setDaemonKey(event.target.value)} /></label><label>Giai đoạn<select value={phase} onChange={event => setPhase(event.target.value)}><option value="">Tất cả</option>{Object.entries(PHASE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Tìm ID / daemon / ghi chú<input maxLength={200} value={search} onChange={event => setSearch(event.target.value)} /></label><label>Chất lượng<select value={quality} onChange={event => setQuality(event.target.value)}><option value="">Tất cả</option>{["VALID", "PARTIAL"].map(value => <option key={value} value={value}>{labelQuality(value)}</option>)}</select></label><label className="as-is-check"><input type="checkbox" checked={deleted} onChange={event => setDeleted(event.target.checked)} />Bao gồm đã xóa</label></div>
    {invalidDates && <p role="alert" className="error-text">Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.</p>}
    {scopeError && <p role="alert" className="error-text">{scopeError}</p>}
    <div className="toolbar"><span>Đã chọn {selected.length} bộ As-is trên các trang</span><button className="button ghost" disabled={!selected.length || isBusy} onClick={() => setTargets(selected.filter(row => !row.deleted_at))}><Trash2 />Xóa các bộ đã chọn</button><button className="button ghost" disabled={!selected.length || isBusy} onClick={() => setSelected([])}>Bỏ chọn</button></div>
    <div className="table-wrap"><table><thead><tr><th>Chọn</th><th>Thời điểm thu</th><th>Giai đoạn</th><th>Daemon / ghi chú</th><th>Chất lượng bộ gốc</th><th>Thao tác</th></tr></thead><tbody>{rows.map(row => {
      const keys = filteredKeys(row);
      return <tr key={row.id}><td><input type="checkbox" aria-label={`Chọn bộ As-is ${row.id}`} checked={selected.some(value => value.id === row.id)} disabled={Boolean(row.deleted_at) || isBusy} onChange={event => setSelected(current => event.target.checked ? [...current.filter(value => value.id !== row.id), row] : current.filter(value => value.id !== row.id))} /></td><td>{localTime(row.started_at)}<small className="block">{row.id.slice(0, 8)}</small></td><td>{PHASE_LABELS[row.phase] || row.phase}</td><td>{keys.length} daemon{scopeActive ? " khớp bộ lọc" : ""}<small className="block">{keys.join(", ")}</small>{row.note && <small className="block">{row.note}</small>}</td><td>{row.deleted_at ? "Đã xóa" : labelQuality(row.quality)}</td><td><div className="as-is-row-actions">
        <button className="button ghost" disabled={isBusy || invalidFilters} onClick={() => void action("detail", async current => { setDetail(undefined); const value = await api<Observation>(`/v1/as-is/collections/${row.id}?${savedCollectionQuery(Boolean(row.deleted_at))}`); if (current()) setDetail(value); })}>{scopeActive ? "Xem daemon đã lọc" : "Xem bản đã lưu"}</button>
        <button className="button ghost" disabled={isBusy || invalidFilters} onClick={() => void action("export", async current => { const filename = await downloadAttachment(`/v1/as-is/collections/${row.id}/export?${savedCollectionQuery(Boolean(row.deleted_at), type, daemonKey)}`); if (current()) setNotice(`Đã tải ${filename}; ${scopeActive ? `chỉ ${keys.length} daemon khớp bộ lọc, bộ gốc được giữ nguyên` : "toàn bộ daemon của bộ gốc"}; giữ thời điểm ${localTime(row.started_at)}${row.deleted_at ? "; nguồn đang xóa mềm" : ""}.`); })}><ArrowDownToLine />{scopeActive ? "Xuất daemon đã lọc" : "Xuất bộ gốc"}</button>
        {scopeActive && <button className="button ghost" disabled={isBusy} onClick={() => void action("export-original", async current => { const filename = await downloadAttachment(`/v1/as-is/collections/${row.id}/export?${savedCollectionQuery(Boolean(row.deleted_at))}`); if (current()) setNotice(`Đã tải ${filename}; toàn bộ ${row.daemon_keys.length} daemon của bộ gốc, không áp dụng bộ lọc.`); })}>Xuất bộ gốc</button>}
        {row.deleted_at ? <button className="button ghost" disabled={isBusy} onClick={() => void action("restore", async current => { await api(`/v1/as-is/collections/${row.id}/restore`, { method: "POST" }); if (!current()) return; setDetail(undefined); await load(); if (current()) setNotice("Đã khôi phục bộ As-is với dữ liệu gốc."); })}><RotateCcw />Khôi phục</button> : <button className="button ghost" disabled={isBusy} onClick={() => setTargets([row])}><Trash2 />Xóa bộ gốc</button>}
      </div></td></tr>;
    })}</tbody></table></div>
    {!rows.length && <p className="empty-state">{history.loading ? "Đang đọc lịch sử…" : "Chưa có bộ As-is phù hợp với bộ lọc."}</p>}<CollectionHistoryPager page={history.page} count={rows.length} hasMore={history.hasMore} busy={isBusy || invalidFilters} previous={() => void history.previous()} next={() => void history.next()} />
  </section>{detail && <section className="panel"><div className="section-head"><h3>Bộ As-is {detail.id}</h3><button className="button ghost" onClick={() => setDetail(undefined)}>Đóng</button></div>{scopeActive && <p className="muted">Đang xem daemon khớp bộ lọc. Bộ As-is gốc và mã kiểm tra được giữ nguyên.</p>}{detail.deleted_at && <p className="notice">Nguồn đang xóa mềm; xem và xuất giữ dữ liệu gốc. Khôi phục trước khi dùng để so sánh.</p>}<ObservationDetails observation={detail} daemonType={type} daemonKey={daemonKey.trim()} diagnostics={false} /><EnvironmentSummary data={detail.system.environment} /></section>}
  {targets.length > 0 && <div className="modal-backdrop"><section className="panel as-is-confirm" role="dialog" aria-modal="true" aria-labelledby="delete-as-is-title"><h2 id="delete-as-is-title">Xóa {targets.length} bộ As-is?</h2><p>Xóa mềm toàn bộ bộ As-is gốc, không chỉ daemon đang lọc; có thể khôi phục. Bộ đã xóa không được dùng để so sánh cho đến khi khôi phục. Không thay đổi daemon hoặc dữ liệu trên Ceph.</p><ul>{targets.map(row => <li key={row.id}><code>{row.id}</code> · {localTime(row.started_at)} · {row.daemon_keys.length} daemon</li>)}</ul><div className="toolbar"><button className="button ghost" disabled={busy === "delete"} onClick={() => setTargets([])}>Hủy</button><button className="button danger" disabled={Boolean(busy)} onClick={() => void remove()}><Trash2 />Xác nhận xóa mềm</button></div></section></div>}
  </div>;
}
