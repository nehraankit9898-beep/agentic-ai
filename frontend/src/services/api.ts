import type { ChatResponseData, HealthInfo, ToolInfo } from "../types";

// In dev, Vite proxies /api -> http://localhost:8000 (see vite.config.ts)
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function sendMessage(
  message: string,
  sessionId: string
): Promise<ChatResponseData> {
  return request<ChatResponseData>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>("/api/health");
}

export function getTools(): Promise<{ tools: ToolInfo[] }> {
  return request<{ tools: ToolInfo[] }>("/api/tools");
}

export function clearConversation(sessionId: string): Promise<unknown> {
  return request(`/api/conversation/${sessionId}`, { method: "DELETE" });
}
