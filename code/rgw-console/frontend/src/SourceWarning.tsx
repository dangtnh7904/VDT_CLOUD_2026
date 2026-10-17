import { AlertTriangle } from "lucide-react";
import { sourceWarningLines } from "./source-warning";

export function SourceWarning(props: Parameters<typeof sourceWarningLines>[0]) {
  const lines = sourceWarningLines(props);
  if (!lines.length) return null;
  return <details className="source-warning"><summary aria-label="Xem dữ liệu còn thiếu hoặc cũ" title={lines.join("\n")}><AlertTriangle size={15} aria-hidden="true" /></summary><div role="note"><strong>Dữ liệu còn thiếu hoặc cũ</strong><ul>{lines.map(line => <li key={line}>{line}</li>)}</ul></div></details>;
}
