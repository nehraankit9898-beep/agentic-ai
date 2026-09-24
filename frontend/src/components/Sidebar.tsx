import { useEffect, useState } from "react";
import type { ChatMessage, ToolInfo } from "../types";
import { clearConversation, getTools } from "../services/api";

interface HistoryEntry {
  time: number;
  user: string;
  agent: string;
  status: string;
}

export default function Sidebar({
  sessionId,
  messages,
  onClear,
}: {
  sessionId: string;
  messages: ChatMessage[];
  onClear: () => void;
}) {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("task_history") ?? "[]");
    } catch {
      return [];
    }
  });

  useEffect(() => {
    getTools()
      .then((d) => setTools(d.tools))
      .catch(() => setTools([]));
  }, []);

  // Persist conversation-derived task history
  useEffect(() => {
    const entries: HistoryEntry[] = [];
    for (let i = 0; i < messages.length; i++) {
      if (messages[i].role === "user") {
        const reply = messages[i + 1];
        entries.push({
          time: messages[i].timestamp,
          user: messages[i].content,
          agent: reply?.role === "assistant" ? reply.content : "",
          status: reply ? "done" : "pending",
        });
      }
    }
    const merged = [...entries.slice(-20), ...history.filter((h) => !entries.some((e) => e.time === h.time))].slice(0, 30);
    setHistory(merged);
    localStorage.setItem("task_history", JSON.stringify(merged));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  async function handleClear() {
    try {
      await clearConversation(sessionId);
    } catch {
      /* backend may be down; still clear locally */
    }
    setHistory([]);
    localStorage.removeItem("task_history");
    onClear();
  }

  return (
    <aside className="panel sidebar">
      <h2>Task history</h2>
      {history.length === 0 ? (
        <p className="muted">No tasks yet.</p>
      ) : (
        <ul className="history-list">
          {history.map((h, i) => (
            <li key={i} className="history-item">
              <div className="history-q">{h.user}</div>
              <div className="history-a muted">{h.agent.slice(0, 80)}</div>
              <div className="history-time muted">
                {new Date(h.time).toLocaleTimeString()} · {h.status}
              </div>
            </li>
          ))}
        </ul>
      )}
      <button className="secondary" onClick={() => void handleClear()}>
        Clear session &amp; history
      </button>

      <h2>Tools</h2>
      {tools.length === 0 ? (
        <p className="muted">Backend offline or no tools registered.</p>
      ) : (
        <ul className="tool-info-list">
          {tools.map((t) => (
            <li key={t.name}>
              <strong>{t.name}</strong>
              <div className="muted">{t.description}</div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
