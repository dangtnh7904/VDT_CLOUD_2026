import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowLeftRight } from "lucide-react";
import { api, downloadAttachment } from "./api";
import { Pagination } from "./DaemonWorkbench";
import { SourceWarning } from "./SourceWarning";
import { DAEMON_TYPES, PHASE_LABELS, collectionPairError, collectionQuery, comparisonKeys, comparisonWarningDaemons, daemonScopeError, labelQuality, localTime, pageRows, scopedDaemonKeys, showValue, toggleKeys, type CollectionSummary } from "./as-is-contracts";
import { CollectionHistoryPager, useCollectionHistory, useDebouncedValue } from "./useCollectionHistory";
import { createRequestScope } from "./request-scope";
type ComparisonResult = { collection_a: CollectionSummary; collection_b: CollectionSummary; daemon_type: string; fsid: string; rows: { key: string; coverage: string; changes: { field: string; a: unknown; b: unknown; delta?: number | null; reason?: string }[]; a: unknown; b: unknown }[]; summary: { both: number; only_a: number; only_b: number; changed: number }; limitations: string[] };
export function Comparison() {
  const [type, setType] = useState("osd"); const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [phase, setPhase] = useState("");
  const [a, setA] = useState<CollectionSummary>(); const [b, setB] = useState<CollectionSummary>(); const [selected, setSelected] = useState<string[]>([]); const [search, setSearch] = useState("");
  const [collectionSearch, setCollectionSearch] = useState(""); const [daemonKey, setDaemonKey] = useState("");
  const [result, setResult] = useState<ComparisonResult>(); const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [page, setPage] = useState(1);
  const requests = useRef(createRequestScope()); const requestBody = useRef<object | undefined>(undefined);
  const aId = a?.id || ""; const bId = b?.id || "";
  const keys = comparisonKeys(a, b, type).filter(key => !daemonKey.trim() || key === daemonKey.trim());
  const pairError = collectionPairError(a, b, type) || (a && b && !keys.length ? "Không có daemon khớp bộ lọc trong hai nguồn đã chọn." : null);
  const visibleKeys = keys.filter(key => key.toLowerCase().includes(search.toLowerCase()));
  const invalidDates = Boolean(from && to && from > to);
  const debouncedSearch = useDebouncedValue(collectionSearch);
  const debouncedDaemonKey = useDebouncedValue(daemonKey.trim());
  const scopeError = daemonScopeError(daemonKey, type);
  const invalidFilters = invalidDates || Boolean(scopeError);
  const query = invalidFilters ? "" : collectionQuery({ type, from, to, phase, search: debouncedSearch, daemonKey: debouncedDaemonKey });
  const history = useCollectionHistory(query);
  const isBusy = Boolean(busy) || history.loading || daemonKey.trim() !== debouncedDaemonKey;
  const invalidate = () => { setResult(undefined); requestBody.current = undefined; setNotice(""); setPage(1); };
  useEffect(() => {
    requests.current.invalidate(); setBusy(""); invalidate(); setSelected([]); setA(undefined); setB(undefined); setError("");
    return () => { requests.current.invalidate(); };
  }, [type]);
  useEffect(() => {
    requests.current.invalidate(); setBusy(""); invalidate(); setSelected([]); setError("");
  }, [daemonKey]);
  const compare = async () => {
    if (pairError || invalidFilters) return;
    const sequence = requests.current.begin(); if (sequence === undefined) return;
    setBusy("compare"); setError(""); invalidate();
    const body = { collection_a_id: aId, collection_b_id: bId, daemon_type: type, ...(selected.length || daemonKey.trim() ? { daemon_keys: selected.length ? selected : [daemonKey.trim()] } : {}) };
    try { const value = await api<ComparisonResult>("/v1/as-is/compare", { method: "POST", body: JSON.stringify(body) }); if (requests.current.current(sequence)) { setResult(value); requestBody.current = body; } } catch (caught) { if (requests.current.current(sequence)) setError((caught as Error).message); } finally { if (requests.current.finish(sequence)) setBusy(""); }
  };
  const exportResult = async () => {
    const body = requestBody.current; if (!body) return;
    const sequence = requests.current.begin(); if (sequence === undefined) return;
    setBusy("export"); setError("");
    try { const filename = await downloadAttachment("/v1/as-is/compare/export", { method: "POST", body: JSON.stringify(body) }); if (requests.current.current(sequence)) setNotice(`Đã tải ${filename}. Hai nguồn giữ nguyên thời điểm thu.`); }
    catch (caught) { if (requests.current.current(sequence)) setError((caught as Error).message); }
    finally { if (requests.current.finish(sequence)) setBusy(""); }
  };
  const filteredKeys = (row: CollectionSummary) => scopedDaemonKeys(row, type, daemonKey);
  const option = (row: CollectionSummary) => `${localTime(row.started_at)} · ${PHASE_LABELS[row.phase]} · ${row.id.slice(0, 8)} · ${filteredKeys(row).length} ${type.toUpperCase()} khớp bộ lọc`;
  return <div className="cluster-metrics-workspace as-is-workspace"><section className="panel"><span className="eyebrow">HAI LẦN THU THỰC TẾ</span><h2>So sánh</h2><p>Chọn hai bộ As-is cùng cụm để so sánh daemon cùng loại. Bộ chứa nhiều loại vẫn được tìm thấy nhưng chỉ hiện loại đã chọn. Thứ tự A/B và giai đoạn được chọn tự do; chênh lệch số là B − A. Lựa chọn A/B được giữ khi đổi trang, ngày, giai đoạn hoặc từ khóa tìm kiếm; đổi loại daemon sẽ xóa lựa chọn.</p>{(error || history.error) && <div className="notice error" role="alert">{error || history.error}</div>}{notice && <div className="notice" role="status">{notice}</div>}
    <div className="form-grid as-is-filters"><label>Loại daemon<select value={type} disabled={Boolean(busy)} onChange={event => { setType(event.target.value); setDaemonKey(""); }}>{DAEMON_TYPES.map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select></label><label>Daemon cụ thể (tùy chọn)<input maxLength={132} placeholder="Ví dụ osd.2" value={daemonKey} disabled={Boolean(busy)} onChange={event => setDaemonKey(event.target.value)} /></label><label>Từ ngày (UTC+7)<input type="date" disabled={Boolean(busy)} value={from} onChange={event => setFrom(event.target.value)} /></label><label>Đến hết ngày (UTC+7)<input type="date" disabled={Boolean(busy)} value={to} onChange={event => setTo(event.target.value)} /></label><label>Giai đoạn<select value={phase} disabled={Boolean(busy)} onChange={event => setPhase(event.target.value)}><option value="">Tất cả giai đoạn</option>{Object.entries(PHASE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Tìm bộ As-is theo ID / daemon / ghi chú<input maxLength={200} value={collectionSearch} disabled={Boolean(busy)} onChange={event => setCollectionSearch(event.target.value)} /></label></div>
    {invalidDates && <p role="alert" className="error-text">Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.</p>}
    {scopeError && <p role="alert" className="error-text">{scopeError}</p>}
    <div className="table-wrap"><table><thead><tr><th>Thời điểm / giai đoạn</th><th>Daemon khớp bộ lọc / ghi chú</th><th>Chất lượng bộ gốc</th><th>Chọn nguồn</th></tr></thead><tbody>{history.items.map(row => <tr key={row.id}><td>{localTime(row.started_at)}<small className="block">{PHASE_LABELS[row.phase]} · {row.id.slice(0, 8)}</small></td><td>{filteredKeys(row).length} {type.toUpperCase()}<small className="block">{filteredKeys(row).join(", ")}</small><small className="block">{row.note || "Không có ghi chú"}</small></td><td>{labelQuality(row.quality)}</td><td><div className="as-is-row-actions"><button className="button ghost" disabled={isBusy || invalidFilters || row.id === bId} onClick={() => { setA(row); setSelected([]); invalidate(); }}>{row.id === aId ? "Đang là A" : "Chọn làm A"}</button><button className="button ghost" disabled={isBusy || invalidFilters || row.id === aId || Boolean(a && a.fsid !== row.fsid)} onClick={() => { setB(row); setSelected([]); invalidate(); }}>{row.id === bId ? "Đang là B" : "Chọn làm B"}</button></div></td></tr>)}</tbody></table></div>
    {!history.items.length && <p className="empty-state">{history.loading ? "Đang đọc lịch sử…" : "Chưa có bộ As-is phù hợp với bộ lọc."}</p>}
    <CollectionHistoryPager page={history.page} count={history.items.length} hasMore={history.hasMore} busy={isBusy || invalidFilters} previous={() => void history.previous()} next={() => void history.next()} retry={history.error ? () => void history.reload() : undefined} />
    <div className="form-grid"><div><strong>Bộ As-is A</strong><p>{a ? option(a) : "Chưa chọn bộ A"}</p>{a && <button className="button ghost" disabled={isBusy} onClick={() => { setA(undefined); setSelected([]); invalidate(); }}>Bỏ chọn A</button>}</div><div><strong>Bộ As-is B</strong><p>{b ? option(b) : "Chưa chọn bộ B"}</p>{b && <button className="button ghost" disabled={isBusy} onClick={() => { setB(undefined); setSelected([]); invalidate(); }}>Bỏ chọn B</button>}</div></div>
    {a && b && <p className="muted">A: {labelQuality(a.quality)} · B: {labelQuality(b.quality)} · FSID {a.fsid}</p>}
    {keys.length > 0 && <div className="as-is-details"><label>Lọc daemon trong hợp A/B<input value={search} onChange={event => setSearch(event.target.value)} /></label><div className="as-is-chips">{visibleKeys.map(key => <label className="as-is-chip" key={key}><input type="checkbox" checked={selected.includes(key)} disabled={Boolean(busy)} onChange={event => { setSelected(current => toggleKeys(current, [key], event.target.checked)); invalidate(); }} />{key}</label>)}</div><p className="muted">{selected.length ? `So sánh ${selected.length} daemon đã chọn.` : `Chưa chọn riêng: so sánh cả ${keys.length} daemon trong hợp A/B, gồm daemon chỉ có ở một bên.`}</p></div>}
    {pairError && <p className="muted">{pairError}</p>}<div className="toolbar"><button className="button primary" disabled={isBusy || Boolean(pairError) || invalidFilters} onClick={() => void compare()}>{busy === "compare" ? "Đang so sánh…" : "So sánh A với B"}</button><button className="button ghost" disabled={isBusy || !a || !b} onClick={() => { setA(b); setB(a); invalidate(); }}><ArrowLeftRight />Đảo A/B</button>{result && <button className="button ghost" disabled={isBusy} onClick={() => void exportResult()}><ArrowDownToLine />Xuất so sánh (JSON)</button>}</div>
  </section>{result && <section className="panel"><div className="section-head"><h3>Kết quả so sánh — B − A</h3><SourceWarning limitations={result.limitations} daemons={comparisonWarningDaemons(result.rows)} /></div><p>Có ở cả hai: {result.summary.both} · Chỉ ở A: {result.summary.only_a} · Chỉ ở B: {result.summary.only_b} · Có thay đổi: {result.summary.changed}</p><p>Dữ liệu mô tả giữa hai lần thu, không phải kết luận nâng cấp thành công.</p>{pageRows(result.rows, page).map(row => <details className="as-is-details" key={row.key} open><summary>{row.key} · {row.coverage === "BOTH" ? "Có ở cả hai" : row.coverage === "ONLY_A" ? "Chỉ có ở A" : "Chỉ có ở B"}</summary>{row.changes.length ? <div className="table-wrap"><table><thead><tr><th>Trường</th><th>A</th><th>B</th><th>B − A</th><th>Ghi chú</th></tr></thead><tbody>{row.changes.map(change => <tr key={change.field}><td title={change.field}>{fieldLabel(change.field)}</td><td>{showValue(change.a)}</td><td>{showValue(change.b)}</td><td>{change.delta == null ? "—" : showValue(change.delta)}</td><td>{reasonLabel(change.reason)}</td></tr>)}</tbody></table></div> : <p>{row.coverage === "BOTH" ? "Không có thay đổi trong các trường so sánh được." : "Không đủ hai phía để tính chênh lệch."}</p>}</details>)}<Pagination page={page} total={result.rows.length} onPage={setPage} /></section>}</div>;
}
import { fieldLabel, reasonLabel } from "./labels";
