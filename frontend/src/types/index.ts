export type Role = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
}

export interface ToolCallInfo {
  tool_name: string;
  arguments?: Record<string, unknown>;
  success?: boolean;
  output?: string;
  error?: string | null;
}

export interface PlanStep {
  step_number?: number;
  description?: string;
  [key: string]: unknown;
}

export interface TaskPlanInfo {
  steps?: PlanStep[];
  reasoning?: string;
  requires_tools?: boolean;
  [key: string]: unknown;
}

export interface ChatResponseData {
  message: string;
  session_id: string;
  status: string;
  tool_calls: ToolCallInfo[];
  task_plan: TaskPlanInfo | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  dangerous?: boolean;
  requires_confirmation?: boolean;
  [key: string]: unknown;
}

export interface HealthInfo {
  status: string;
  llm_available: boolean;
  tools_available: number;
}

export type AgentStatus =
  | "idle"
  | "thinking"
  | "planning"
  | "using_tool"
  | "completed"
  | "failed";
