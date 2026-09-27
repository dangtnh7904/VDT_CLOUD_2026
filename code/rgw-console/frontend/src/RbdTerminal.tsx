import { useEffect, useRef, useState } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { AlertTriangle, LoaderCircle, Monitor, RotateCcw, X } from "lucide-react";
import "@xterm/xterm/css/xterm.css";
import { api } from "./api";

export function RbdTerminal({ volume, onClose }: { volume: any; onClose: () => void }) {
  const host = useRef<HTMLDivElement | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const terminal = useRef<XTerm | null>(null);
  const fit = useRef<FitAddon | null>(null);
  const [state, setState] = useState<"connecting" | "open" | "closed" | "error">("connecting");
  const [message, setMessage] = useState("Requesting a single-use terminal ticket…");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!host.current) return;
    const term = new XTerm({
      convertEol: true,
      cursorBlink: true,
      fontFamily: "'DM Mono', Consolas, monospace",
      fontSize: 13,
      theme: { background: "#070c11", foreground: "#c8d3dc", cursor: "#6fffc8", selectionBackground: "#294859" },
      scrollback: 5000,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(host.current);
    fitAddon.fit();
    terminal.current = term;
    fit.current = fitAddon;
    let disposed = false;

    const open = async () => {
      setState("connecting");
      setMessage("Requesting a single-use terminal ticket…");
      try {
        const ticket = await api(`/rbd/volumes/${volume.id}/terminal-ticket`, { method: "POST" });
        if (disposed) return;
        const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${scheme}//${window.location.host}${ticket.websocket_path}?ticket=${encodeURIComponent(ticket.ticket)}`);
        ws.binaryType = "arraybuffer";
        socket.current = ws;
        ws.onopen = () => {
          if (disposed) return;
          setState("open");
          setMessage(ticket.lab_warning);
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
          term.focus();
        };
        ws.onmessage = event => {
          if (event.data instanceof ArrayBuffer) term.write(new Uint8Array(event.data));
          else if (typeof event.data === "string") {
            try {
              const control = JSON.parse(event.data);
              if (control.type === "ready") {
                setMessage(`${control.warning} cwd=${control.mountpoint}`);
                term.writeln(`\r\n\x1b[38;2;111;255;200m[Storage Lab] ${control.host || "SSH host"}:${control.mountpoint}\x1b[0m`);
              }
            } catch { term.write(event.data); }
          }
        };
        ws.onerror = () => { if (!disposed) { setState("error"); setMessage("Terminal WebSocket failed."); } };
        ws.onclose = event => {
          if (!disposed) {
            setState(event.code === 1000 ? "closed" : "error");
            setMessage(event.reason || "Terminal session closed. The volume remains mounted.");
          }
        };
      } catch (error: any) {
        if (!disposed) { setState("error"); setMessage(error?.message || "Could not open terminal."); }
      }
    };

    const input = term.onData(data => {
      if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: "input", data }));
    });
    const observer = new ResizeObserver(() => {
      try { fitAddon.fit(); } catch { return; }
      if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    });
    observer.observe(host.current);
    open();
    return () => {
      disposed = true;
      observer.disconnect();
      input.dispose();
      socket.current?.close(1000, "UI closed");
      socket.current = null;
      term.dispose();
      terminal.current = null;
    };
  }, [attempt, volume.id]);

  return <div className="terminal-backdrop"><section className="terminal-window">
    <header><div><Monitor /><span><strong>{volume.display_name || volume.image_name}</strong><small>REAL LAB SHELL · closing this window does not unmount</small></span></div><button className="icon-button" onClick={onClose}><X /></button></header>
    <div className={`terminal-status ${state}`}>{state === "connecting" ? <LoaderCircle className="spin" /> : state === "error" ? <AlertTriangle /> : <i />}<span>{message}</span>{state !== "open" && <button onClick={() => setAttempt(value => value + 1)}><RotateCcw />New ticket</button>}</div>
    <div className="terminal-host" ref={host} />
  </section></div>;
}
