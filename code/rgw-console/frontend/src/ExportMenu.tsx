import { useState } from "react";
import { AlertTriangle, ArrowDownToLine, Check, LoaderCircle } from "lucide-react";
import { downloadConsoleExport, type ConsoleExportRequest, type ExportFormat, type ExportSource } from "./api";

export type ExportMenuProps = {
  source: ExportSource;
  sourceId?: string;
  comparisonId?: string;
  filters?: ConsoleExportRequest["filters"];
  formats?: ExportFormat[];
  disabled?: boolean;
  label?: string;
};

export function ExportMenu({ source, sourceId, comparisonId, filters, formats = ["json", "csv", "zip", "md"], disabled = false, label = "Export" }: ExportMenuProps) {
  const [format, setFormat] = useState<ExportFormat>(formats[0] || "json");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null);
  const selectedFormat = formats.includes(format) ? format : formats[0] || "json";
  const download = async () => {
    setBusy(true); setNotice(null);
    try {
      const filename = await downloadConsoleExport({ source, ...(sourceId ? { source_id: sourceId } : {}), ...(comparisonId ? { comparison_id: comparisonId } : {}), format: selectedFormat, ...(filters ? { filters } : {}) });
      setNotice({ error: false, text: `Download requested: ${filename}. Your browser chooses the save location.` });
    } catch (error: any) { setNotice({ error: true, text: error?.message || "Export failed; no file was downloaded." }); }
    finally { setBusy(false); }
  };
  return <div className="export-control">
    <div className="export-actions"><select aria-label={`${label} file format`} value={selectedFormat} disabled={disabled || busy} onChange={event => setFormat(event.target.value as ExportFormat)}>{formats.map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select><button type="button" className="button ghost" disabled={disabled || busy || !formats.length} onClick={download}>{busy ? <LoaderCircle className="spin" /> : <ArrowDownToLine />}{busy ? "Exporting…" : label}</button></div>
    {notice && <small role={notice.error ? "alert" : "status"} className={notice.error ? "error-text" : "success-text"}>{notice.error ? <AlertTriangle /> : <Check />}{notice.text}</small>}
  </div>;
}
