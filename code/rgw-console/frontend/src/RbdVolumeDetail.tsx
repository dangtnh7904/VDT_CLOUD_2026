import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowDownToLine, Check, ChevronRight, File, FileCheck2, Folder,
  FolderOpen, FolderPlus, Image, LoaderCircle, Monitor, RefreshCw, Trash2, Upload, X,
} from "lucide-react";
import { api, formatBytes } from "./api";
import { RbdTerminal } from "./RbdTerminal";
import { rbdPreviewKind } from "./ui-contracts";

type FileItem = { path: string; name: string; type: "directory" | "file" | "symlink" | "other"; size: number; mtime?: string | null; mime_type?: string | null };

const joinPath = (parent: string, name: string) => `${parent === "/" ? "" : parent}/${name}`.replace(/\/+/g, "/") || "/";
const messageFrom = async (response: Response) => {
  const body = await response.json().catch(() => ({}));
  return body?.detail?.message || body?.error?.message || body?.error || response.statusText;
};

export function RbdVolumeDetail({ volume, onClose, onChanged }: { volume: any; onClose: () => void; onChanged: () => void }) {
  const [path, setPath] = useState("/");
  const [items, setItems] = useState<FileItem[]>([]);
  const [selected, setSelected] = useState<FileItem | null>(null);
  const [metadata, setMetadata] = useState<FileItem | null>(null);
  const [preview, setPreview] = useState<{ kind: "text" | "image" | "pdf"; value: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [mkdirName, setMkdirName] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [runs, setRuns] = useState<any[]>([]);
  const [baselineName, setBaselineName] = useState(`upgrade-${new Date().toISOString().slice(0, 10)}`);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const uploadInput = useRef<HTMLInputElement | null>(null);

  const loadRuns = () => api(`/rbd/volumes/${volume.id}/validation-runs`).then(result => setRuns(result.items || [])).catch(() => {});
  const load = async (nextPath = path) => {
    setLoading(true); setNotice(null);
    try {
      const result = await api(`/rbd/volumes/${volume.id}/files?path=${encodeURIComponent(nextPath)}`);
      setPath(result.path); setItems(result.items || []); setSelected(null); setMetadata(null); setPreview(null);
      setChecked(current => new Set([...current].filter(item => (result.items || []).some((entry: FileItem) => entry.path === item))));
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Could not read the mounted filesystem." }); }
    finally { setLoading(false); }
  };

  useEffect(() => { load("/"); loadRuns(); }, [volume.id]);
  useEffect(() => () => { if (preview && preview.kind !== "text") URL.revokeObjectURL(preview.value); }, [preview]);

  const openItem = async (item: FileItem) => {
    if (item.type === "directory") return load(item.path);
    if (item.type !== "file") return setNotice({ kind: "error", text: "Symlinks and special files are not accessible from the browser." });
    setSelected(item); setMetadata(null); setPreview(null); setBusy(`preview:${item.path}`);
    try {
      const meta = await api<FileItem>(`/rbd/volumes/${volume.id}/files/metadata?path=${encodeURIComponent(item.path)}`);
      setMetadata(meta);
      const mime = meta.mime_type || "application/octet-stream";
      const previewKind = rbdPreviewKind(mime);
      if (!previewKind) return;
      const response = await fetch(`/api/rbd/volumes/${volume.id}/files/content?preview=true&path=${encodeURIComponent(item.path)}`);
      if (!response.ok) throw new Error(await messageFrom(response));
      if (previewKind === "text") setPreview({ kind: "text", value: await response.text() });
      else {
        const url = URL.createObjectURL(await response.blob());
        setPreview({ kind: previewKind, value: url });
      }
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Preview failed." }); }
    finally { setBusy(""); }
  };

  const upload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = [...(event.target.files || [])];
    if (!files.length) return;
    setBusy("upload"); setNotice(null);
    try {
      for (const file of files) {
        const destination = joinPath(path, file.name);
        const response = await fetch(`/api/rbd/volumes/${volume.id}/files/content?path=${encodeURIComponent(destination)}`, { method: "PUT", body: file });
        if (!response.ok) throw new Error(`${file.name}: ${await messageFrom(response)}`);
      }
      setNotice({ kind: "success", text: `Uploaded ${files.length} file(s) through bounded SFTP streaming.` });
      await load(path); onChanged();
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Upload failed." }); }
    finally { setBusy(""); event.target.value = ""; }
  };

  const mkdir = async () => {
    const name = mkdirName.trim(); if (!name || name.includes("/")) return setNotice({ kind: "error", text: "Directory name must be one path segment." });
    setBusy("mkdir");
    try {
      await api(`/rbd/volumes/${volume.id}/directories`, { method: "POST", body: JSON.stringify({ path: joinPath(path, name) }) });
      setMkdirName(""); setNotice({ kind: "success", text: `Created ${name}.` }); await load(path);
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Could not create directory." }); }
    finally { setBusy(""); }
  };

  const remove = async (item: FileItem) => {
    if (!window.confirm(`Delete ${item.path}? Directories must be empty.`)) return;
    setBusy(`delete:${item.path}`);
    try {
      await api(`/rbd/volumes/${volume.id}/files?path=${encodeURIComponent(item.path)}`, { method: "DELETE" });
      setNotice({ kind: "success", text: `Deleted ${item.path}. Physical RBD allocation is not credited until telemetry proves reclamation.` });
      await load(path); onChanged();
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Delete failed." }); }
    finally { setBusy(""); }
  };

  const createBaseline = async () => {
    if (!checked.size) return setNotice({ kind: "error", text: "Select at least one regular file for the checksum baseline." });
    setBusy("baseline");
    try {
      await api(`/rbd/volumes/${volume.id}/validation-runs`, { method: "POST", body: JSON.stringify({ name: baselineName, baseline_label: "pre-upgrade", paths: [...checked] }) });
      setNotice({ kind: "success", text: `Stored SHA-256 baseline for ${checked.size} file(s).` }); await loadRuns();
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Could not create validation baseline." }); }
    finally { setBusy(""); }
  };

  const verify = async (run: any) => {
    setBusy(`verify:${run.id}`);
    try {
      const result = await api(`/rbd/volumes/${volume.id}/validation-runs/${run.id}/verify`, { method: "POST" });
      setNotice({ kind: result.status === "PASS" ? "success" : "error", text: result.status === "PASS" ? "All baseline SHA-256 values still match." : "One or more files changed or are missing." });
      await loadRuns();
    } catch (error: any) { setNotice({ kind: "error", text: error?.message || "Verification failed." }); await loadRuns(); }
    finally { setBusy(""); }
  };

  const crumbs = useMemo(() => path.split("/").filter(Boolean), [path]);
  return <div className="volume-detail-backdrop"><section className="volume-detail panel">
    <header className="volume-detail-head"><div><span className="eyebrow">MOUNTED EXT4 VOLUME</span><h2>{volume.display_name || volume.image_name}</h2><p>{volume.pool}/{volume.image_name} · {volume.mountpoint}</p></div><div><button className="button ghost" onClick={() => setTerminalOpen(true)}><Monitor />Terminal</button><button className="icon-button" onClick={onClose}><X /></button></div></header>
    {notice && <div className={`rbd-notice ${notice.kind}`}>{notice.kind === "success" ? <Check /> : <AlertTriangle />}<span>{notice.text}</span></div>}
    <div className="file-toolbar"><div className="file-breadcrumb"><button onClick={() => load("/")}><FolderOpen />root</button>{crumbs.map((crumb, index) => <span key={`${crumb}-${index}`}><ChevronRight /><button onClick={() => load(`/${crumbs.slice(0, index + 1).join("/")}`)}>{crumb}</button></span>)}</div><div><input ref={uploadInput} hidden type="file" multiple onChange={upload} /><button className="button ghost" disabled={Boolean(busy)} onClick={() => uploadInput.current?.click()}>{busy === "upload" ? <LoaderCircle className="spin" /> : <Upload />}Upload</button><button className="icon-button" onClick={() => load(path)}><RefreshCw className={loading ? "spin" : ""} /></button></div></div>
    <div className="file-layout"><div className="file-pane"><div className="mkdir-row"><input placeholder="new-directory" value={mkdirName} onChange={event => setMkdirName(event.target.value)} onKeyDown={event => event.key === "Enter" && mkdir()} /><button disabled={!mkdirName.trim() || Boolean(busy)} onClick={mkdir}><FolderPlus />Create</button></div><div className="file-list">{path !== "/" && <button className="file-row" onClick={() => load(path.split("/").slice(0, -1).join("/") || "/")}><span className="file-icon"><Folder /></span><span><strong>..</strong><small>Parent directory</small></span></button>}{items.map(item => <div className={`file-row ${selected?.path === item.path ? "selected" : ""}`} key={item.path}><label className="file-check">{item.type === "file" && <input type="checkbox" checked={checked.has(item.path)} onChange={event => setChecked(current => { const next = new Set(current); event.target.checked ? next.add(item.path) : next.delete(item.path); return next; })} />}</label><button className="file-main" onClick={() => openItem(item)}><span className="file-icon">{item.type === "directory" ? <Folder /> : item.name.match(/\.(png|jpe?g|gif|webp|svg)$/i) ? <Image /> : <File />}</span><span><strong>{item.name}</strong><small>{item.type} · {formatBytes(item.size)} · {item.mtime ? new Date(item.mtime).toLocaleString() : "unknown mtime"}</small></span></button><button className="icon-button danger" disabled={Boolean(busy)} onClick={() => remove(item)}>{busy === `delete:${item.path}` ? <LoaderCircle className="spin" /> : <Trash2 />}</button></div>)}{!loading && !items.length && <div className="empty">Directory is empty.</div>}</div></div>
      <aside className="file-preview"><header><div><strong>{metadata?.name || "Select a file"}</strong><small>{metadata ? `${metadata.mime_type || "application/octet-stream"} · ${formatBytes(metadata.size)}` : "Text, image and PDF preview; other types stay download-only."}</small></div>{selected && <a className="button ghost" href={`/api/rbd/volumes/${volume.id}/files/content?path=${encodeURIComponent(selected.path)}`}><ArrowDownToLine />Download</a>}</header><div className="file-preview-body">{busy.startsWith("preview:") ? <LoaderCircle className="spin" /> : preview?.kind === "text" ? <pre>{preview.value}</pre> : preview?.kind === "image" ? <img src={preview.value} alt={metadata?.name || "preview"} /> : preview?.kind === "pdf" ? <iframe sandbox="" src={preview.value} title={metadata?.name || "PDF preview"} /> : <div><File /><span>{metadata ? "Preview unavailable; use Download." : "No file selected."}</span></div>}</div></aside></div>
    <section className="validation-panel"><div className="section-head"><div><span className="eyebrow">UPGRADE DATA CHECK</span><h3>SHA-256 baseline and remount verification</h3><p>Select files above before the upgrade; verify the same immutable image/FS UUID after remount.</p></div><div className="validation-create"><input value={baselineName} onChange={event => setBaselineName(event.target.value)} /><button className="button primary" disabled={!checked.size || busy === "baseline"} onClick={createBaseline}>{busy === "baseline" ? <LoaderCircle className="spin" /> : <FileCheck2 />}Save baseline ({checked.size})</button></div></div><div className="validation-runs">{runs.map(run => <article key={run.id}><div><strong>{run.name}</strong><small>{run.baseline_label} · {run.manifest?.files?.length || 0} files · {new Date(run.baseline_at).toLocaleString()}</small></div><span className={`job-state ${String(run.status).toLowerCase()}`}>{run.status}</span><button className="button ghost" disabled={Boolean(busy)} onClick={() => verify(run)}>{busy === `verify:${run.id}` ? <LoaderCircle className="spin" /> : <Check />}Verify now</button></article>)}{!runs.length && <div className="empty">No stored validation baseline.</div>}</div></section>
    {terminalOpen && <RbdTerminal volume={volume} onClose={() => { setTerminalOpen(false); load(path); }} />}
  </section></div>;
}
