import { DaemonWorkbench } from "./DaemonWorkbench";
export function ClusterMetrics({ section = "metrics" }: { section?: "overview" | "metrics" }) { return <DaemonWorkbench mode={section} />; }
