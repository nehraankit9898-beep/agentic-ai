import type { AgentStatus } from "../types";

const LABELS: Record<AgentStatus, string> = {
  idle: "Idle",
  thinking: "Thinking…",
  planning: "Planning…",
  using_tool: "Using tool…",
  completed: "Completed",
  failed: "Failed",
};

export default function StatusBar({
  status,
  llmAvailable,
  toolsCount,
}: {
  status: AgentStatus;
  llmAvailable: boolean | null;
  toolsCount: number | null;
}) {
  return (
    <header className="statusbar">
      <div className="statusbar-title">
        <span className="logo">🤖</span>
        <h1>Agentic AI Assistant</h1>
      </div>
      <div className="statusbar-items">
        <span className={`badge badge-${status}`}>{LABELS[status]}</span>
        <span
          className={`badge ${llmAvailable ? "badge-online" : "badge-offline"}`}
          title="LLM (Ollama) connection"
        >
          LLM: {llmAvailable === null ? "?" : llmAvailable ? "online" : "offline"}
        </span>
        <span className="badge badge-muted" title="Registered tools">
          Tools: {toolsCount ?? "?"}
        </span>
      </div>
    </header>
  );
}
