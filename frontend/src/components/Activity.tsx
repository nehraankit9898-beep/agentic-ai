import type { ToolCallInfo, TaskPlanInfo } from "../types";

export default function Activity({
  toolCalls,
  taskPlan,
}: {
  toolCalls: ToolCallInfo[];
  taskPlan: TaskPlanInfo | null;
}) {
  return (
    <aside className="panel activity">
      <h2>Activity</h2>

      <div className="activity-section">
        <h3>Task plan</h3>
        {taskPlan ? (
          <pre className="json">{JSON.stringify(taskPlan, null, 2)}</pre>
        ) : (
          <p className="muted">No plan for the current task.</p>
        )}
      </div>

      <div className="activity-section">
        <h3>Tool calls (last request)</h3>
        {toolCalls.length === 0 ? (
          <p className="muted">No tools used yet.</p>
        ) : (
          <ul className="tool-list">
            {toolCalls.map((tc, i) => (
              <li key={i} className="tool-item">
                <span className="tool-name">🔧 {tc.tool_name}</span>
                {tc.arguments && (
                  <pre className="json small">
                    {JSON.stringify(tc.arguments, null, 2)}
                  </pre>
                )}
                {typeof tc.success === "boolean" && (
                  <span className={`badge ${tc.success ? "badge-online" : "badge-offline"}`}>
                    {tc.success ? "ok" : "error"}
                  </span>
                )}
                {tc.output && <pre className="json small">{String(tc.output)}</pre>}
                {tc.error && <pre className="json small error">{tc.error}</pre>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
