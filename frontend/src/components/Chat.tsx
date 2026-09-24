import { useEffect, useRef, useState } from "react";
import type {
  AgentStatus,
  ChatMessage,
  ChatResponseData,
  ToolCallInfo,
} from "../types";
import { sendMessage } from "../services/api";

interface Props {
  sessionId: string;
  messages: ChatMessage[];
  onMessagesChange: (msgs: ChatMessage[]) => void;
  onStatusChange: (status: AgentStatus) => void;
  onToolCalls: (calls: ToolCallInfo[]) => void;
  onResponse: (data: ChatResponseData) => void;
}

export default function Chat({
  sessionId,
  messages,
  onMessagesChange,
  onStatusChange,
  onToolCalls,
  onResponse,
}: Props) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, busy]);

  async function handleSend() {
    const text = input.trim();
    if (!text || busy) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: Date.now(),
    };
    onMessagesChange([...messages, userMsg]);
    setInput("");
    setBusy(true);
    onStatusChange("thinking");

    try {
      const data = await sendMessage(text, sessionId);
      onToolCalls(data.tool_calls ?? []);
      onResponse(data);
      onMessagesChange([
        ...messages,
        userMsg,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.message,
          timestamp: Date.now(),
        },
      ]);
      onStatusChange(data.status === "error" || data.status === "failed" ? "failed" : "completed");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      onMessagesChange([
        ...messages,
        userMsg,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `⚠️ Request failed: ${msg}`,
          timestamp: Date.now(),
        },
      ]);
      onStatusChange("failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="chat">
      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 && (
          <p className="empty-hint">
            Send a message to start. Try: “What time is it?” or
            “Calculate 12 * (3 + 4)” or “Create a file notes.txt”.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg msg-${m.role}`}>
            <div className="msg-role">
              {m.role === "user" ? "You" : m.role === "assistant" ? "Agent" : "System"}
            </div>
            <div className="msg-content">{m.content}</div>
          </div>
        ))}
        {busy && (
          <div className="msg msg-system">
            <div className="msg-content typing">Agent is working…</div>
          </div>
        )}
      </div>
      <div className="chat-input">
        <textarea
          value={input}
          placeholder="Type your instruction…"
          rows={2}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          disabled={busy}
        />
        <button onClick={() => void handleSend()} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </section>
  );
}
