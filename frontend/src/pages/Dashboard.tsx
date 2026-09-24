import { useCallback, useEffect, useState } from "react";
import StatusBar from "../components/StatusBar";
import Chat from "../components/Chat";
import Activity from "../components/Activity";
import Sidebar from "../components/Sidebar";
import { getHealth } from "../services/api";
import type {
  AgentStatus,
  ChatMessage,
  ChatResponseData,
  ToolCallInfo,
  TaskPlanInfo,
} from "../types";

const SESSION_KEY = "agent_session_id";

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export default function Dashboard() {
  const sessionId = getSessionId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<AgentStatus>("idle");
  const [toolCalls, setToolCalls] = useState<ToolCallInfo[]>([]);
  const [taskPlan, setTaskPlan] = useState<TaskPlanInfo | null>(null);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const [toolsCount, setToolsCount] = useState<number | null>(null);

  const refreshHealth = useCallback(() => {
    getHealth()
      .then((h) => {
        setLlmAvailable(h.llm_available);
        setToolsCount(h.tools_available);
      })
      .catch(() => {
        setLlmAvailable(null);
        setToolsCount(null);
      });
  }, []);

  useEffect(() => {
    refreshHealth();
    const t = setInterval(refreshHealth, 15000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  function handleResponse(data: ChatResponseData) {
    setTaskPlan(data.task_plan);
  }

  return (
    <div className="app">
      <StatusBar
        status={status}
        llmAvailable={llmAvailable}
        toolsCount={toolsCount}
      />
      <main className="layout">
        <Chat
          sessionId={sessionId}
          messages={messages}
          onMessagesChange={setMessages}
          onStatusChange={setStatus}
          onToolCalls={setToolCalls}
          onResponse={handleResponse}
        />
        <Activity toolCalls={toolCalls} taskPlan={taskPlan} />
        <Sidebar
          sessionId={sessionId}
          messages={messages}
          onClear={() => {
            setMessages([]);
            setToolCalls([]);
            setTaskPlan(null);
            setStatus("idle");
          }}
        />
      </main>
    </div>
  );
}
