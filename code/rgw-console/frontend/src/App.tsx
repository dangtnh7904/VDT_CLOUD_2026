import { useEffect, useRef, useState } from "react";
import {
  Activity, AlertTriangle, Archive, ArrowDownToLine, Boxes, Check, ChevronLeft, ChevronRight,
  Clock3, Database, File, FileJson, Folder, FolderOpen, Gauge, HardDrive, History, Image,
  Layers3, LoaderCircle, Menu, MoreHorizontal, Pause, Play, RefreshCw, Save, Search, Server,
  ShieldAlert, Shuffle, Square, Trash2, Upload, Video, X, Zap,
} from "lucide-react";
import { api, formatBytes, uploadWithProgress } from "./api";

type View = "dashboard" | "upload" | "random" | "stream" | "objects";
type CorpusItem = { name: string; path: string; kind: "file" | "directory"; size?: number; category?: string; content_type?: string };
type Pick = { corpusId: string; paths: string[] };
type UploadRow = { id: string; name: string; size?: number; progress: number; state: "queued" | "uploading" | "success" | "error"; result?: any; retry?: () => void };
type CapacitySnapshot = {
  state: string;
  fresh: boolean;
  most_full_osd: number | null;
  most_full_ratio: number | null;
  captured_at?: string | null;
  contract?: string;
  observe_only?: boolean;
  reasons?: string[];
  policy?: { hard_ceiling_ratio?: number; admission_stop_ratio?: number; resume_ratio?: number };
};
type ActionNotice = { kind: "success" | "error"; text: string };

const nav: { id: View; label: string; icon: any }[] = [
  { id: "dashboard", label: "Live dashboard", icon: Gauge },
  { id: "upload", label: "Upload objects", icon: Upload },
  { id: "random", label: "Random object", icon: Shuffle },
  { id: "stream", label: "Streaming PUT", icon: Zap },
  { id: "objects", label: "Object explorer", icon: Boxes },
];

const categoryIcons: Record<string, any> = { images: Image, data: FileJson, documents: File, media: Video, archives: Archive, binary: Database, other: File };

function CorpusPicker({ open, multiple = true, folders = false, onClose, onChoose }: { open: boolean; multiple?: boolean; folders?: boolean; onClose: () => void; onChoose: (pick: Pick) => void }) {
  const [corpusId, setCorpusId] = useState("mixed");
  const [path, setPath] = useState("");
  const [items, setItems] = useState<CorpusItem[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (nextPath = path, nextCorpus = corpusId) => {
    setLoading(true);
    try {
      const data = await api(`/corpora/${nextCorpus}/browse?path=${encodeURIComponent(nextPath)}`);
      setPath(data.path); setItems(data.items); setParent(data.parent); setSelected([]);
    } finally { setLoading(false); }
  };
  useEffect(() => { if (open) load("", corpusId); }, [open]);
  if (!open) return null;
  const toggle = (item: CorpusItem) => {
    if (item.kind === "directory" && !folders) return load(item.path);
    if (!multiple) return setSelected([item.path]);
    setSelected(current => current.includes(item.path) ? current.filter(x => x !== item.path) : [...current, item.path]);
  };
  return <div className="modal-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="picker panel">
      <header className="picker-head">
        <div><span className="eyebrow">UBUNTU FILESYSTEM</span><h2>{folders ? "Chọn folder nguồn" : "Chọn file từ corpus"}</h2></div>
        <button className="icon-button" onClick={onClose}><X size={19} /></button>
      </header>
      <div className="corpus-tabs">
        {[{ id: "mixed", label: "Mixed-file corpus" }, { id: "size", label: "Size corpus" }].map(c =>
          <button className={corpusId === c.id ? "active" : ""} onClick={() => { setCorpusId(c.id); load("", c.id); }} key={c.id}><HardDrive size={16} />{c.label}</button>)}
      </div>
      <div className="breadcrumbs">
        <button onClick={() => load("")}><Server size={15} /> data</button>
        <ChevronRight size={14} /><button onClick={() => load("")}>{corpusId === "mixed" ? "mix-file-corpus" : "size-file-corpus"}</button>
        {path.split("/").filter(Boolean).map((part, index, arr) => <span className="crumb" key={index}><ChevronRight size={14} /><button onClick={() => load(arr.slice(0, index + 1).join("/"))}>{part}</button></span>)}
      </div>
      <div className="file-list">
        {parent !== null && <button className="file-row" onDoubleClick={() => load(parent)} onClick={() => load(parent)}><FolderOpen size={19} /><span className="file-name">..</span><span>Parent directory</span></button>}
        {loading ? <div className="empty"><LoaderCircle className="spin" />Reading allowlisted directory…</div> : items.map(item => {
          const Icon = item.kind === "directory" ? Folder : (categoryIcons[item.category || "other"] || File);
          const checked = selected.includes(item.path);
          return <button key={item.path} className={`file-row ${checked ? "selected" : ""}`} onClick={() => toggle(item)} onDoubleClick={() => item.kind === "directory" && load(item.path)}>
            <span className={`check ${checked ? "checked" : ""}`}>{checked && <Check size={13} />}</span><Icon size={19} />
            <span className="file-name">{item.name}</span><span className="muted">{item.kind === "directory" ? "Folder" : item.category}</span><span className="file-size">{formatBytes(item.size)}</span>
          </button>;
        })}
      </div>
      <footer className="picker-foot"><span>{selected.length} mục đã chọn</span><div><button className="button ghost" onClick={onClose}>Hủy</button><button className="button primary" disabled={!selected.length} onClick={() => { onChoose({ corpusId, paths: selected }); onClose(); }}>Chọn nguồn</button></div></footer>
    </section>
  </div>;
}

function Header({ view, endpoint }: { view: View; endpoint: string }) {
  return <header className="topbar"><div><p className="eyebrow">CEPH OBJECT GATEWAY</p><h1>{nav.find(x => x.id === view)?.label}</h1></div><div className="endpoint"><span className="status-dot" /><div><small>RGW endpoint</small><strong>{endpoint || "Connecting…"}</strong></div></div></header>;
}

function CapacityBanner() {
  const [snapshot, setSnapshot] = useState<CapacitySnapshot | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const next = await api<CapacitySnapshot>("/capacity");
        if (active) { setSnapshot(next); setError(""); }
      } catch (reason: any) {
        if (active) setError(reason?.message || "Capacity API unavailable");
      }
    };
    load();
    const timer = window.setInterval(load, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const state = error ? "UNAVAILABLE" : snapshot?.state || "CONNECTING";
  const severity = ["EMERGENCY_CAPACITY", "BLOCKED_TELEMETRY", "READ_CLEANUP_ONLY", "UNAVAILABLE"].includes(state)
    ? "danger"
    : ["THROTTLED", "PAUSED_CAPACITY", "PAUSED_REMAP", "RECONCILING"].includes(state) ? "warning" : "normal";
  const observeOnly = snapshot?.observe_only ?? snapshot?.contract === "OBSERVE_ONLY";
  const ratio = snapshot?.most_full_ratio;
  const reasons = error ? [error] : snapshot?.reasons || [];
  const Icon = severity === "danger" ? ShieldAlert : severity === "warning" ? AlertTriangle : Gauge;

  return <div className="capacity-shell"><section className={`capacity-banner ${severity}`}>
    <div className="capacity-state"><span className="capacity-icon"><Icon /></span><div><small>CAPACITY GUARD</small><strong>{state.replaceAll("_", " ")}</strong></div></div>
    <div className="capacity-reading"><small>Most-full participating OSD</small><strong>{ratio == null ? "—" : `${(ratio * 100).toFixed(1)}%`}</strong><span>{snapshot?.most_full_osd == null ? "No OSD evidence" : `osd.${snapshot.most_full_osd}`}</span></div>
    <div className="capacity-contract">
      <span className={`fresh-pill ${snapshot?.fresh && !error ? "fresh" : "stale"}`}><Clock3 />{snapshot?.fresh && !error ? "FRESH" : "STALE"}</span>
      {observeOnly && <span className="observe-pill">OBSERVE ONLY</span>}
      <p title={reasons.join(" · ")}>{reasons.length ? reasons.join(" · ") : "No active capacity warning."}</p>
    </div>
  </section></div>;
}

function Dashboard() {
  const [metrics, setMetrics] = useState<any>({ recent: [] });
  useEffect(() => { const source = new EventSource("/api/metrics/stream"); source.onmessage = event => setMetrics(JSON.parse(event.data)); return () => source.close(); }, []);
  const cards = [
    ["Total operations", (metrics.puts || 0) + (metrics.gets || 0), `${metrics.puts || 0} PUT · ${metrics.gets || 0} GET`, Activity],
    ["Success rate", `${metrics.success + metrics.failure ? ((metrics.success / (metrics.success + metrics.failure)) * 100).toFixed(1) : "100.0"}%`, `${metrics.failure || 0} failed`, Check],
    ["Throughput", `${(metrics.mib_per_second || 0).toFixed(2)} MiB/s`, `${(metrics.objects_per_second || 0).toFixed(2)} objects/s`, Zap],
    ["Active jobs", metrics.active_jobs || 0, "worker queue", Layers3],
    ["Bytes transferred", formatBytes((metrics.bytes_sent || 0) + (metrics.bytes_received || 0)), `${formatBytes(metrics.bytes_sent)} up · ${formatBytes(metrics.bytes_received)} down`, HardDrive],
    ["Latest latency", `${Number(metrics.latest_latency || 0).toFixed(1)} ms`, `p99 ${Number(metrics.p99 || 0).toFixed(1)} ms`, Activity],
  ];
  return <div className="stack">
    <section className="hero panel"><div><span className="live"><i /> LIVE TELEMETRY</span><h2>Object traffic, at a glance.</h2><p>Real-time PUT and GET activity from the RGW cluster.</p></div><div className="hero-stat"><small>p95 latency</small><strong>{Number(metrics.p95 || 0).toFixed(0)}<em>ms</em></strong><span>p50 {Number(metrics.p50 || 0).toFixed(0)} · p99 {Number(metrics.p99 || 0).toFixed(0)}</span></div></section>
    <div className="metric-grid">{cards.map(([label, value, sub, Icon]: any) => <article className="metric panel" key={label}><div className="metric-icon"><Icon size={19} /></div><small>{label}</small><strong>{value}</strong><span>{sub}</span></article>)}</div>
    <section className="panel table-panel"><div className="section-head"><div><h2>Recent activity</h2><p>Latest object operations across all clients</p></div><span className="live mini"><i /> streaming</span></div>
      <table><thead><tr><th>Operation</th><th>Object</th><th>Size</th><th>Latency</th><th>Time</th><th>Status</th></tr></thead><tbody>{metrics.recent?.map((row: any) => <tr key={`${row.created_at}-${row.object_key}`}><td><span className={`op ${row.kind.toLowerCase()}`}>{row.kind}</span></td><td className="key-cell">{row.object_key}</td><td>{formatBytes(row.bytes_count)}</td><td>{Number(row.latency_ms).toFixed(1)} ms</td><td>{new Date(row.created_at).toLocaleTimeString()}</td><td><span className={row.success ? "success-text" : "error-text"}>{row.success ? "Success" : "Failed"}</span></td></tr>)}</tbody></table>
      {!metrics.recent?.length && <div className="empty">Chưa có operation. Hãy upload object đầu tiên.</div>}
    </section>
  </div>;
}

function UploadView({ defaultBucket }: { defaultBucket: string }) {
  const [source, setSource] = useState<"ubuntu" | "browser">("ubuntu");
  const [mode, setMode] = useState<"single" | "batch" | "folder">("single");
  const [clientId, setClientId] = useState("host-01");
  const [bucket, setBucket] = useState(defaultBucket);
  const [prefix, setPrefix] = useState("");
  const [picker, setPicker] = useState(false);
  const [pick, setPick] = useState<Pick | null>(null);
  const [browserFiles, setBrowserFiles] = useState<File[]>([]);
  const [rows, setRows] = useState<UploadRow[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => setBucket(defaultBucket), [defaultBucket]);
  const uploadCorpusPath = async (path: string, index: number) => {
    if (!pick) return;
    setRows(current => current.map((row, i) => i === index ? { ...row, state: "uploading", progress: 20 } : row));
    try {
      const data = await api("/uploads/corpus", { method: "POST", body: JSON.stringify({ corpus_id: pick.corpusId, paths: [path], client_id: clientId, bucket, prefix, mode }) });
      const first = data.results[0] || {};
      const result = data.results.length === 1 ? first : { ...first, filename: path, size: data.results.reduce((sum: number, x: any) => sum + (x.size || 0), 0), error: data.failed ? `${data.failed}/${data.results.length} files failed` : undefined };
      setRows(current => current.map((row, i) => i === index ? { ...row, name: result.filename || path, size: result.size, progress: 100, state: data.failed ? "error" : "success", result } : row));
    } catch (error: any) { setRows(current => current.map((row, i) => i === index ? { ...row, state: "error", result: { error: error.message } } : row)); }
  };
  const runCorpus = async () => {
    if (!pick) return;
    setRows(pick.paths.map((name, i) => ({ id: `${i}`, name, progress: 0, state: "queued" })));
    await Promise.allSettled(pick.paths.map((path, index) => uploadCorpusPath(path, index)));
  };
  const uploadOne = async (file: File, index: number) => {
    setRows(current => current.map((row, i) => i === index ? { ...row, state: "uploading", progress: 0 } : row));
    try {
      const result = await uploadWithProgress(file, { client_id: clientId, bucket, prefix, mode, relative_path: (file as any).webkitRelativePath || "" }, progress => setRows(current => current.map((row, i) => i === index ? { ...row, progress } : row)));
      setRows(current => current.map((row, i) => i === index ? { ...row, state: "success", progress: 100, result } : row));
    } catch (error: any) { setRows(current => current.map((row, i) => i === index ? { ...row, state: "error", result: { error: error.message } } : row)); }
  };
  const runBrowser = async () => {
    setRows(browserFiles.map((file, i) => ({ id: `${i}-${file.name}`, name: (file as any).webkitRelativePath || file.name, size: file.size, progress: 0, state: "queued" })));
    await Promise.allSettled(browserFiles.map((file, index) => uploadOne(file, index)));
  };
  return <div className="stack"><section className="panel form-panel">
    <div className="section-head"><div><span className="eyebrow">FEATURES 1–3</span><h2>Upload objects</h2><p>Một file, mixed batch, hoặc toàn bộ folder.</p></div></div>
    <div className="segmented">{(["single", "batch", "folder"] as const).map(item => <button className={mode === item ? "active" : ""} onClick={() => { setMode(item); setPick(null); setBrowserFiles([]); }} key={item}>{item === "single" ? "Single object" : item === "batch" ? "Mixed batch" : "Folder"}</button>)}</div>
    <div className="form-grid"><label><span>Client ID</span><input value={clientId} onChange={e => setClientId(e.target.value)} /></label><label><span>Bucket</span><input value={bucket} onChange={e => setBucket(e.target.value)} /></label><label className="wide"><span>Prefix <em>optional</em></span><input placeholder="experiments/run-01" value={prefix} onChange={e => setPrefix(e.target.value)} /></label></div>
    <div className="source-label">Nguồn file</div><div className="source-switch"><button className={source === "ubuntu" ? "active" : ""} onClick={() => setSource("ubuntu")}><Server size={19} /><span><strong>Ubuntu filesystem</strong><small>Chọn từ 2 corpus allowlist trên server</small></span></button><button className={source === "browser" ? "active" : ""} onClick={() => setSource("browser")}><Upload size={19} /><span><strong>Máy đang mở browser</strong><small>Native browser file picker</small></span></button></div>
    {source === "ubuntu" ? <button className="dropzone" onClick={() => setPicker(true)}><div className="drop-icon"><FolderOpen /></div><strong>{pick ? `${pick.paths.length} mục đã chọn` : mode === "folder" ? "Chọn folder trên Ubuntu" : "Chọn file trên Ubuntu"}</strong><span>{pick ? pick.paths.join(", ") : "/home/dangg/code/data · chỉ đọc · allowlisted"}</span></button> : <>
      <input ref={fileInput} hidden type="file" multiple={mode !== "single"} {...(mode === "folder" ? { webkitdirectory: "", directory: "" } as any : {})} onChange={e => setBrowserFiles(Array.from(e.target.files || []))} />
      <button className="dropzone" onClick={() => fileInput.current?.click()}><div className="drop-icon"><Upload /></div><strong>{browserFiles.length ? `${browserFiles.length} file đã chọn` : "Mở file picker của browser"}</strong><span>{browserFiles.length ? formatBytes(browserFiles.reduce((a, f) => a + f.size, 0)) : "Filename, extension và Content-Type được giữ nguyên"}</span></button></>}
    <div className="action-row"><span>Object key sẽ theo chuẩn <code>clients/{clientId || "client"}/{mode}/…</code></span><button className="button primary large" disabled={!clientId || !bucket || (source === "ubuntu" ? !pick : !browserFiles.length)} onClick={source === "ubuntu" ? runCorpus : runBrowser}><Upload size={17} /> Upload</button></div>
  </section>
  {!!rows.length && <section className="panel queue"><div className="section-head"><div><h2>Upload queue</h2><p>Mỗi object có trạng thái độc lập.</p></div></div>{rows.map((row, index) => <div className="queue-row" key={row.id}><span className={`state-icon ${row.state}`}>{row.state === "uploading" ? <LoaderCircle className="spin" /> : row.state === "success" ? <Check /> : row.state === "error" ? <X /> : <File />}</span><div className="queue-info"><div><strong>{row.name}</strong><span>{formatBytes(row.size)} {row.result?.latency_ms ? `· ${row.result.latency_ms} ms` : ""}</span></div><div className="progress"><i style={{ width: `${row.progress}%` }} /></div>{row.result?.error && <small className="error-text">{row.result.error}</small>}</div>{row.state === "error" && <button className="button ghost" onClick={() => source === "browser" ? uploadOne(browserFiles[index], index) : pick && uploadCorpusPath(pick.paths[index], index)}><RefreshCw size={15} /> Retry</button>}</div>)}</section>}
  <CorpusPicker open={picker} folders={mode === "folder"} multiple={mode !== "single"} onClose={() => setPicker(false)} onChoose={setPick} /></div>;
}

function RandomView({ defaultBucket }: { defaultBucket: string }) {
  const [form, setForm] = useState<any>({ client_id: "host-01", bucket: defaultBucket, prefix: "", corpus_ids: ["mixed", "size"], category: "", extension: "", min_mib: "", max_mib: "" });
  const [result, setResult] = useState<any>(null); const [loading, setLoading] = useState(false);
  useEffect(() => setForm((x: any) => ({ ...x, bucket: defaultBucket })), [defaultBucket]);
  const run = async () => { setLoading(true); setResult(null); try { const body = { ...form, category: form.category || null, extension: form.extension || null, min_bytes: form.min_mib ? Number(form.min_mib) * 1048576 : null, max_bytes: form.max_mib ? Number(form.max_mib) * 1048576 : null }; delete body.min_mib; delete body.max_mib; setResult(await api("/uploads/random", { method: "POST", body: JSON.stringify(body) })); } catch (e: any) { setResult({ success: false, error: e.message }); } finally { setLoading(false); } };
  return <section className="panel form-panel"><div className="section-head"><div><span className="eyebrow">FEATURE 4</span><h2>Random object</h2><p>Chọn ngẫu nhiên từ corpus theo loại, extension hoặc kích thước.</p></div><div className="shuffle-art"><Shuffle /></div></div>
    <div className="form-grid"><label><span>Client ID</span><input value={form.client_id} onChange={e => setForm({ ...form, client_id: e.target.value })} /></label><label><span>Bucket</span><input value={form.bucket} onChange={e => setForm({ ...form, bucket: e.target.value })} /></label><label><span>Category</span><select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}><option value="">Tất cả loại</option>{["images","data","documents","media","archives","binary","other"].map(x => <option key={x}>{x}</option>)}</select></label><label><span>Extension</span><input placeholder="pdf, jpg, bin…" value={form.extension} onChange={e => setForm({ ...form, extension: e.target.value })} /></label><label><span>Min size (MiB)</span><input type="number" min="0" value={form.min_mib} onChange={e => setForm({ ...form, min_mib: e.target.value })} /></label><label><span>Max size (MiB)</span><input type="number" min="0" value={form.max_mib} onChange={e => setForm({ ...form, max_mib: e.target.value })} /></label><label className="wide"><span>Prefix <em>optional</em></span><input value={form.prefix} onChange={e => setForm({ ...form, prefix: e.target.value })} /></label></div>
    <div className="action-row"><span>Nguồn: Mixed-file corpus + Size corpus</span><button className="button primary large" onClick={run} disabled={loading}>{loading ? <LoaderCircle className="spin" /> : <Shuffle size={17} />} Pick & upload</button></div>
    {result && <div className={`result-card ${result.success ? "ok" : "bad"}`}><span className="state-icon">{result.success ? <Check /> : <X />}</span><div><strong>{result.success ? result.filename : "Upload failed"}</strong><p>{result.success ? `${result.corpus_id}/${result.corpus_path} → ${result.key}` : result.error}</p></div>{result.success && <span>{formatBytes(result.size)} · {result.latency_ms} ms</span>}</div>}
  </section>;
}

function StreamView({ defaultBucket }: { defaultBucket: string }) {
  const defaults = { client_id: "loadgen-01", bucket: defaultBucket, prefix: "", requests_per_second: 2, concurrency: 2, duration_seconds: 60, object_limit: 100, weights: { images: 35, data: 25, documents: 20, media: 10, archives: 10 }, corpus_ids: ["mixed"], naming_strategy: "generated" };
  const [form, setForm] = useState<any>(defaults); const [jobs, setJobs] = useState<any[]>([]);
  const load = () => api("/jobs").then(setJobs).catch(() => {});
  useEffect(() => { setForm((x: any) => ({ ...x, bucket: defaultBucket })); load(); const timer = setInterval(load, 1500); return () => clearInterval(timer); }, [defaultBucket]);
  const create = async () => { await api("/jobs", { method: "POST", body: JSON.stringify(form) }); load(); };
  const control = async (id: string, action: string) => { await api(`/jobs/${id}/${action}`, { method: "POST" }); load(); };
  return <div className="stack"><section className="panel form-panel"><div className="section-head"><div><span className="eyebrow">FEATURE 5</span><h2>Mixed-object streaming PUT</h2><p>Tạo workload dài hạn từ corpus, worker chạy độc lập với API.</p></div><span className="worker-badge"><i /> WORKER QUEUE</span></div>
    <div className="form-grid three"><label><span>Client ID</span><input value={form.client_id} onChange={e => setForm({ ...form, client_id: e.target.value })} /></label><label><span>Bucket</span><input value={form.bucket} onChange={e => setForm({ ...form, bucket: e.target.value })} /></label><label><span>Prefix</span><input value={form.prefix} onChange={e => setForm({ ...form, prefix: e.target.value })} /></label><label><span>Requests / second</span><input type="number" value={form.requests_per_second} onChange={e => setForm({ ...form, requests_per_second: Number(e.target.value) })} /></label><label><span>Concurrency</span><input type="number" value={form.concurrency} onChange={e => setForm({ ...form, concurrency: Number(e.target.value) })} /></label><label><span>Duration (seconds)</span><input type="number" value={form.duration_seconds} onChange={e => setForm({ ...form, duration_seconds: Number(e.target.value) })} /></label><label><span>Object limit</span><input type="number" value={form.object_limit} onChange={e => setForm({ ...form, object_limit: Number(e.target.value) })} /></label><label><span>Naming strategy</span><select value={form.naming_strategy} onChange={e => setForm({ ...form, naming_strategy: e.target.value })}><option value="generated">Timestamp + UUID</option><option value="preserve">UUID + original filename</option></select></label></div>
    <div className="weights"><span className="source-label">Tỷ lệ category</span>{Object.entries(form.weights).map(([name, value]: any) => <label key={name}><span>{name}<em>{value}%</em></span><input type="range" min="0" max="100" value={value} onChange={e => setForm({ ...form, weights: { ...form.weights, [name]: Number(e.target.value) } })} /></label>)}</div>
    <div className="action-row"><span>Tổng weight: {Object.values(form.weights).reduce((a: any, b: any) => a + b, 0) as number}%</span><button className="button primary large" onClick={create}><Play size={17} /> Start new job</button></div></section>
    <section className="panel table-panel"><div className="section-head"><div><h2>Streaming jobs</h2><p>Pause, resume hoặc stop từng workload.</p></div></div><table><thead><tr><th>Client</th><th>State</th><th>Objects</th><th>Bytes</th><th>Created</th><th></th></tr></thead><tbody>{jobs.map(job => <tr key={job.id}><td><strong>{job.config.client_id}</strong><small className="block">{job.id.slice(0, 8)}</small></td><td><span className={`job-state ${job.state}`}>{job.state}</span></td><td>{job.sent_count} <span className="error-text">/ {job.failed_count} failed</span></td><td>{formatBytes(job.bytes_sent)}</td><td>{new Date(job.created_at).toLocaleString()}</td><td><div className="row-actions">{job.state === "paused" ? <button onClick={() => control(job.id, "resume")}><Play /></button> : <button disabled={!['running','pending'].includes(job.state)} onClick={() => control(job.id, "pause")}><Pause /></button>}<button disabled={['completed','stopped','failed'].includes(job.state)} onClick={() => control(job.id, "stop")}><Square /></button></div></td></tr>)}</tbody></table>{!jobs.length && <div className="empty">Chưa có streaming job.</div>}</section>
  </div>;
}

function ObjectExplorer({ defaultBucket }: { defaultBucket: string }) {
  const [bucket, setBucket] = useState(defaultBucket); const [prefix, setPrefix] = useState(""); const [query, setQuery] = useState(""); const [category, setCategory] = useState(""); const [clientId, setClientId] = useState(""); const [minMiB, setMinMiB] = useState(""); const [maxMiB, setMaxMiB] = useState(""); const [startTime, setStartTime] = useState(""); const [endTime, setEndTime] = useState("");
  const [data, setData] = useState<any>({ objects: [] }); const [tokens, setTokens] = useState<(string | null)[]>([null]); const [page, setPage] = useState(0); const [selected, setSelected] = useState<any>(null); const [meta, setMeta] = useState<any>(null); const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<any[]>([]); const [versionsTruncated, setVersionsTruncated] = useState(false); const [drawerLoading, setDrawerLoading] = useState(false);
  const [metadataDraft, setMetadataDraft] = useState("{}"); const [overwriteFile, setOverwriteFile] = useState<File | null>(null); const [actionBusy, setActionBusy] = useState(""); const [actionNotice, setActionNotice] = useState<ActionNotice | null>(null);
  const overwriteInput = useRef<HTMLInputElement>(null);
  useEffect(() => setBucket(defaultBucket), [defaultBucket]);
  const load = async (targetPage = 0, token: string | null = null) => { setLoading(true); try { const params = new URLSearchParams({ bucket, prefix, name: query, category, client_id: clientId, max_keys: "100" }); if (minMiB) params.set("min_bytes", String(Number(minMiB) * 1048576)); if (maxMiB) params.set("max_bytes", String(Number(maxMiB) * 1048576)); if (startTime) params.set("start_time", new Date(startTime).toISOString()); if (endTime) params.set("end_time", new Date(endTime).toISOString()); if (token) params.set("continuation_token", token); const result = await api(`/objects?${params}`); setData(result); setPage(targetPage); if (result.next_token) setTokens(current => { const copy = [...current]; copy[targetPage + 1] = result.next_token; return copy; }); } finally { setLoading(false); } };
  const refreshHead = async (row: any) => {
    const next = await api(`/objects/head?bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(row.key)}`);
    setMeta(next); setMetadataDraft(JSON.stringify(next.metadata || {}, null, 2));
    return next;
  };
  const refreshVersions = async (row: any) => {
    const params = new URLSearchParams({ bucket, key: row.key, max_keys: "1000" });
    const result = await api(`/objects/versions?${params}`);
    setVersions((result.versions || []).filter((version: any) => version.key === row.key));
    setVersionsTruncated(Boolean(result.is_truncated));
    return result;
  };
  const inspect = async (row: any) => {
    setSelected(row); setMeta(null); setVersions([]); setActionNotice(null); setOverwriteFile(null); setDrawerLoading(true);
    try { await Promise.all([refreshHead(row), refreshVersions(row)]); }
    catch (error: any) { setActionNotice({ kind: "error", text: error?.message || "Không thể đọc chi tiết object." }); }
    finally { setDrawerLoading(false); }
  };
  const runAction = async (name: string, action: () => Promise<string>) => {
    setActionBusy(name); setActionNotice(null);
    try { setActionNotice({ kind: "success", text: await action() }); }
    catch (error: any) { setActionNotice({ kind: "error", text: error?.message || "Operation failed" }); }
    finally { setActionBusy(""); }
  };
  const overwrite = () => {
    if (!selected || !overwriteFile) return;
    runAction("overwrite", async () => {
      const params = new URLSearchParams({ bucket, key: selected.key });
      await api(`/objects/content?${params}`, {
        method: "PUT",
        body: overwriteFile,
        headers: {
          "Idempotency-Key": crypto.randomUUID(),
          "Content-Type": overwriteFile.type || "application/octet-stream",
          "Content-Length": String(overwriteFile.size),
        },
      });
      await Promise.all([refreshHead(selected), refreshVersions(selected), load(page, tokens[page] || null)]);
      setOverwriteFile(null); if (overwriteInput.current) overwriteInput.current.value = "";
      return "Đã overwrite đúng object key; nội dung mới đã được đọc lại từ RGW.";
    });
  };
  const updateMetadata = () => {
    if (!selected) return;
    runAction("metadata", async () => {
      const metadata = JSON.parse(metadataDraft);
      if (!metadata || Array.isArray(metadata) || typeof metadata !== "object" || Object.values(metadata).some(value => typeof value !== "string")) {
        throw new Error("Metadata phải là JSON object với toàn bộ value là string.");
      }
      await api("/objects/metadata", {
        method: "PATCH",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ bucket, key: selected.key, metadata, content_type: meta?.content_type || null }),
      });
      await Promise.all([refreshHead(selected), refreshVersions(selected)]);
      return "Metadata đã được thay thế bằng self-copy; capacity accounting vẫn áp dụng.";
    });
  };
  const deleteCurrent = () => {
    if (!selected || !window.confirm(`Delete current head của “${selected.key}”?\n\nNếu bucket bật versioning, thao tác này có thể tạo delete marker thay vì giải phóng dung lượng ngay.`)) return;
    runAction("delete-current", async () => {
      const params = new URLSearchParams({ bucket, key: selected.key });
      await api(`/objects?${params}`, { method: "DELETE", headers: { "Idempotency-Key": crypto.randomUUID() } });
      await refreshVersions(selected);
      try { await refreshHead(selected); } catch { setMeta(null); }
      await load(page, tokens[page] || null);
      return "Delete current head đã gửi. Dung lượng chỉ được credit sau khi telemetry xác nhận.";
    });
  };
  const hardDeleteVersion = (version: any) => {
    if (!selected || !version.version_id || !window.confirm(`Xóa vĩnh viễn ${version.is_delete_marker ? "delete marker" : "version"} “${version.version_id}”?\n\nThao tác hard-delete này không thể hoàn tác.`)) return;
    runAction(`version-${version.version_id}`, async () => {
      const params = new URLSearchParams({ bucket, key: selected.key, version_id: version.version_id });
      await api(`/objects?${params}`, { method: "DELETE", headers: { "Idempotency-Key": crypto.randomUUID() } });
      await refreshVersions(selected);
      try { await refreshHead(selected); } catch { setMeta(null); }
      await load(page, tokens[page] || null);
      return `Đã hard-delete ${version.is_delete_marker ? "delete marker" : "version"} đã chọn.`;
    });
  };
  const previewable = meta?.content_type?.startsWith("image/") || meta?.content_type?.startsWith("text/") || ["application/json", "text/csv", "video/mp4", "video/webm", "audio/mpeg", "audio/ogg"].includes(meta?.content_type);
  const previewUrl = selected && meta ? `/api/objects/content?bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(selected.key)}&preview=${encodeURIComponent(meta.etag || "latest")}` : "";
  return <div className="stack"><section className="panel explorer"><div className="section-head"><div><span className="eyebrow">FEATURES 6–7</span><h2>System objects</h2><p>ListObjectsV2 pagination · metadata · safe preview · Range GET.</p></div><button className="button ghost" onClick={() => load(0, null)}><RefreshCw size={16} /> Refresh</button></div>
    <div className="filters"><label><span>Bucket</span><input value={bucket} onChange={e => setBucket(e.target.value)} /></label><label><span>Client ID</span><input placeholder="host-01" value={clientId} onChange={e => setClientId(e.target.value)} /></label><label><span>Prefix</span><input placeholder="clients/host-01/" value={prefix} onChange={e => setPrefix(e.target.value)} /></label><label className="search-box"><span>Name</span><i><Search size={16} /></i><input placeholder="Search object key" value={query} onChange={e => setQuery(e.target.value)} /></label><label><span>Category</span><select value={category} onChange={e => setCategory(e.target.value)}><option value="">All</option>{["images","data","documents","media","archives","binary","other"].map(x => <option key={x}>{x}</option>)}</select></label><label><span>Min size (MiB)</span><input type="number" min="0" value={minMiB} onChange={e => setMinMiB(e.target.value)} /></label><label><span>Max size (MiB)</span><input type="number" min="0" value={maxMiB} onChange={e => setMaxMiB(e.target.value)} /></label><label><span>From</span><input type="datetime-local" value={startTime} onChange={e => setStartTime(e.target.value)} /></label><label><span>To</span><input type="datetime-local" value={endTime} onChange={e => setEndTime(e.target.value)} /></label><button className="button primary" onClick={() => { setTokens([null]); load(0, null); }}>Apply</button></div>
    <div className="object-table"><table><thead><tr><th>Object key</th><th>Client / category</th><th>Size</th><th>Modified</th><th>Source</th><th></th></tr></thead><tbody>{data.objects.map((row: any) => { const Icon = categoryIcons[row.category] || File; return <tr key={row.key}><td><div className="object-name"><span><Icon /></span><div><strong>{row.key.split("/").pop()}</strong><small>{row.key}</small></div></div></td><td>{row.client_id || "—"}<small className="block">{row.category || row.content_type}</small></td><td>{formatBytes(row.size)}</td><td>{new Date(row.last_modified).toLocaleString()}</td><td><span className="source-pill">{row.source}</span></td><td><button className="icon-button" onClick={() => inspect(row)}><MoreHorizontal /></button></td></tr>})}</tbody></table>{loading && <div className="empty"><LoaderCircle className="spin" /> Loading RGW objects…</div>}{!loading && !data.objects.length && <div className="empty">Không tìm thấy object.</div>}</div>
    <div className="pagination"><span>Page {page + 1} · {data.objects.length} objects</span><div><button disabled={page === 0} onClick={() => load(page - 1, tokens[page - 1])}><ChevronLeft /></button><button disabled={!data.next_token} onClick={() => load(page + 1, data.next_token)}><ChevronRight /></button></div></div>
  </section>{selected && <div className="drawer-backdrop" onMouseDown={e => e.target === e.currentTarget && setSelected(null)}><aside className="drawer"><header><div><span className="eyebrow">OBJECT DETAIL</span><h2>{selected.key.split("/").pop()}</h2></div><button className="icon-button" onClick={() => setSelected(null)}><X /></button></header>
    {drawerLoading && <div className="drawer-loading"><LoaderCircle className="spin" /> Reading head and versions…</div>}
    {actionNotice && <div className={`action-notice ${actionNotice.kind}`}>{actionNotice.kind === "success" ? <Check /> : <AlertTriangle />}<span>{actionNotice.text}</span></div>}
    {meta && <><div className="preview">{previewable ? meta.content_type.startsWith("image/") ? <img key={meta.etag} src={previewUrl} /> : meta.content_type.startsWith("video/") ? <video key={meta.etag} controls src={previewUrl} /> : meta.content_type.startsWith("audio/") ? <audio key={meta.etag} controls src={previewUrl} /> : <iframe key={meta.etag} sandbox="" src={previewUrl} /> : <div><File size={38} /><strong>Preview disabled</strong><span>Binary không tin cậy sẽ không được render.</span></div>}</div><dl><div><dt>Object key</dt><dd>{selected.key}</dd></div><div><dt>Content-Type</dt><dd>{meta.content_type}</dd></div><div><dt>Size</dt><dd>{formatBytes(meta.size)}</dd></div><div><dt>ETag</dt><dd>{meta.etag}</dd></div>{meta.version_id && <div><dt>Current version</dt><dd>{meta.version_id}</dd></div>}{Object.entries(meta.metadata || {}).map(([key, value]: any) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><a className="button primary download" href={`/api/objects/content?download=true&bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(selected.key)}`}><ArrowDownToLine /> Download object</a></>}
    <section className="drawer-section"><div className="drawer-section-title"><div><Upload /><span><strong>Overwrite exact key</strong><small>PUT nội dung mới vào cùng object key.</small></span></div></div><input ref={overwriteInput} className="file-control" type="file" onChange={event => setOverwriteFile(event.target.files?.[0] || null)} /><div className="drawer-action-row"><span>{overwriteFile ? `${overwriteFile.name} · ${formatBytes(overwriteFile.size)}` : "Chưa chọn file local"}</span><button className="button primary" disabled={!overwriteFile || Boolean(actionBusy)} onClick={overwrite}>{actionBusy === "overwrite" ? <LoaderCircle className="spin" /> : <Upload />}Overwrite</button></div></section>
    <section className="drawer-section"><div className="drawer-section-title"><div><Save /><span><strong>Replace metadata</strong><small>JSON string map; self-copy có thể phát sinh I/O.</small></span></div></div><textarea className="metadata-editor" rows={7} value={metadataDraft} onChange={event => setMetadataDraft(event.target.value)} spellCheck={false} /><div className="drawer-action-row"><span>Content-Type hiện tại sẽ được giữ nguyên.</span><button className="button ghost" disabled={!meta || Boolean(actionBusy)} onClick={updateMetadata}>{actionBusy === "metadata" ? <LoaderCircle className="spin" /> : <Save />}Save metadata</button></div></section>
    <section className="drawer-section"><div className="drawer-section-title"><div><History /><span><strong>Object versions</strong><small>Hard-delete chỉ xóa version hoặc marker được chọn.</small></span></div><button className="icon-button" disabled={Boolean(actionBusy)} onClick={() => refreshVersions(selected)}><RefreshCw /></button></div><div className="version-list">{versions.map(version => <article className={`version-row ${version.is_delete_marker ? "marker" : ""}`} key={`${version.version_id}-${version.last_modified}`}><div><strong>{version.is_delete_marker ? "Delete marker" : version.is_latest ? "Current version" : "Object version"}</strong><code>{version.version_id || "null"}</code><small>{version.last_modified ? new Date(version.last_modified).toLocaleString() : "Unknown time"} · {formatBytes(version.size)}</small></div><div>{version.is_latest && <span className="version-pill">LATEST</span>}<button className="icon-button danger" title="Hard-delete selected version" disabled={!version.version_id || Boolean(actionBusy)} onClick={() => hardDeleteVersion(version)}>{actionBusy === `version-${version.version_id}` ? <LoaderCircle className="spin" /> : <Trash2 />}</button></div></article>)}{!drawerLoading && !versions.length && <div className="version-empty">Không có version/delete marker được trả về.</div>}{versionsTruncated && <div className="version-warning">Danh sách bị giới hạn; dùng continuation API trước khi cleanup toàn bộ.</div>}</div></section>
    <section className="danger-zone"><div><ShieldAlert /><span><strong>Delete current head</strong><small>Versioned bucket có thể chỉ tạo delete marker.</small></span></div><button className="button danger" disabled={Boolean(actionBusy)} onClick={deleteCurrent}>{actionBusy === "delete-current" ? <LoaderCircle className="spin" /> : <Trash2 />}Delete current</button></section>
  </aside></div>}</div>;
}

export default function App() {
  const [view, setView] = useState<View>("dashboard"); const [menu, setMenu] = useState(false); const [health, setHealth] = useState<any>({}); const [defaultBucket, setDefaultBucket] = useState("test-data");
  useEffect(() => { api("/health").then(setHealth).catch(e => setHealth({ status: "degraded", error: e.message })); api("/buckets").then(rows => rows[0]?.name && setDefaultBucket(rows[0].name)).catch(() => {}); }, []);
  return <div className="shell"><aside className={`sidebar ${menu ? "open" : ""}`}><div className="brand"><div><Database /></div><span><strong>RGW</strong><small>OBJECT LAB</small></span></div><nav>{nav.map(item => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => { setView(item.id); setMenu(false); }}><item.icon /><span>{item.label}</span>{view === item.id && <i />}</button>)}</nav><div className="sidebar-foot"><div className="cluster"><span className={health.status === "ok" ? "online" : "offline"}><i /></span><div><strong>{health.status === "ok" ? "Cluster connected" : "RGW unavailable"}</strong><small>{health.buckets ?? 0} buckets discovered</small></div></div><p>Credentials stay server-side</p></div></aside>
    <main><button className="mobile-menu" onClick={() => setMenu(!menu)}><Menu /></button><Header view={view} endpoint={health.endpoint} /><CapacityBanner /><div className="content">{view === "dashboard" && <Dashboard />}{view === "upload" && <UploadView defaultBucket={defaultBucket} />}{view === "random" && <RandomView defaultBucket={defaultBucket} />}{view === "stream" && <StreamView defaultBucket={defaultBucket} />}{view === "objects" && <ObjectExplorer defaultBucket={defaultBucket} />}</div></main></div>;
}
