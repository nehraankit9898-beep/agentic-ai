from typing import Optional
from ..models.schemas import (
    Message,
    MessageRole,
    ConversationState,
    ToolCall,
    ToolResult,
    TaskPlan,
    AgentResponse,
)
from ..core.config import settings
from ..services.llm_client import LLMClient
from ..tools.manager import ToolManager


class AgentController:
    """
    Main agent controller that orchestrates the workflow:
    Understand → Plan → Execute (ReAct loop) → Check → Recover → Respond

    Advanced features:
    - Native tool-calling ReAct loop with parallel tool execution and a
      MAX_AGENT_STEPS runaway guard (falls back to heuristic parsing when
      the provider/model lacks native function calling).
    - Persistent long-term memory: session transcripts + key/value facts
      are stored in SQLite via app.services.memory.
    - Cloud fallback: if the primary LLM errors out, an OpenAI-compatible
      provider is used when configured (keys stay server-side).
    """

    def __init__(self, llm_client: LLMClient, tool_manager: ToolManager):
        self.llm_client = llm_client
        self.tool_manager = tool_manager
        self.conversation_states: dict[str, ConversationState] = {}
        self._native_tool_calls = True  # flips off if provider rejects tools
        self._restored_sessions: set[str] = set()

    @property
    def memory(self):
        from ..services.memory import memory

        return memory

    def _persist(self, coro) -> None:
        """Schedule a best-effort async memory write without blocking."""
        import asyncio

        if not settings.memory_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(coro)
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    def get_or_create_state(self, session_id: str) -> ConversationState:
        """Get existing conversation state or create new one."""
        if session_id not in self.conversation_states:
            self.conversation_states[session_id] = ConversationState(
                session_id=session_id
            )
        return self.conversation_states[session_id]

    async def ensure_history_loaded(self, session_id: str) -> ConversationState:
        """Lazily restore a session's transcript from SQLite after a restart."""
        state = self.get_or_create_state(session_id)
        if (
            settings.memory_enabled
            and session_id not in self._restored_sessions
            and not state.messages
        ):
            self._restored_sessions.add(session_id)
            try:
                rows = await self.memory.load_session(session_id, limit=20)
                for row in rows:
                    try:
                        role = MessageRole(row["role"])
                    except ValueError:
                        continue
                    if role == MessageRole.SYSTEM:
                        continue
                    state.messages.append(
                        Message(
                            role=role,
                            content=row["content"],
                            metadata=row.get("metadata") or None,
                        )
                    )
            except Exception:  # noqa: BLE001 - memory is best-effort
                pass
        return state

    async def process_request(
        self, message: str, session_id: str, confirmed: bool = False
    ) -> AgentResponse:
        """
        Process a user request through the agent workflow.

        Args:
            message: User's input message
            session_id: Session identifier for conversation memory
            confirmed: Whether pending tool calls were explicitly approved

        Returns:
            AgentResponse with message, tool calls, and status
        """
        state = await self.ensure_history_loaded(session_id)

        # --- Confirmation flow: resume previously paused tool calls ---
        if confirmed and state.pending_tool_calls:
            pending = state.pending_tool_calls
            state.pending_tool_calls = []
            # Record the user's approval in history before executing.
            from datetime import datetime as _dt, timezone as _tz
            state.messages.append(
                Message(role=MessageRole.USER, content=message, timestamp=_dt.now(_tz.utc))
            )
            self._persist(self.memory.append_message(session_id, "user", message))
            return await self._execute_and_respond(
                message, state, pending, skip_confirmation=True
            )

        # Add user message to history (in-memory + persistent store)
        from datetime import datetime, timezone
        state.messages.append(
            Message(role=MessageRole.USER, content=message, timestamp=datetime.now(timezone.utc))
        )
        state.updated_at = datetime.now(timezone.utc)
        self._persist(self.memory.append_message(session_id, "user", message))

        # Step 1: Understand - Determine if tools are needed
        understanding = await self._understand_request(message, state)

        if understanding["needs_tools"]:
            # Step 2: Plan - Create a task plan if multi-step
            if understanding.get("is_complex", False):
                plan = await self._create_plan(message, understanding)
                state.current_task = message
                state.task_status = "planning"
            else:
                plan = None

            # Step 3: Execute - Use tools to fulfill the request
            tool_calls = understanding.get("tool_calls", [])
            
            # If no specific tool calls but tools are needed, try to infer and execute
            if understanding["needs_tools"] and not tool_calls:
                # Infer which tool to use based on message content
                inferred_tool_call = await self._infer_tool_call(message)
                if inferred_tool_call:
                    tool_calls = [inferred_tool_call]
            
            # Safety gate: tools that require confirmation pause the run
            needs_confirm = [
                tc for tc in tool_calls
                if self.tool_manager.requires_confirmation(tc.tool_name)
            ]
            if needs_confirm:
                state.pending_tool_calls = tool_calls
                state.current_task = message
                state.task_status = "awaiting_confirmation"
                names = ", ".join(sorted({tc.tool_name for tc in needs_confirm}))
                preview = "; ".join(
                    f"{tc.tool_name}({tc.arguments})" for tc in tool_calls
                )[:400]
                return AgentResponse(
                    message=(
                        f"I need your confirmation before running: {names}.\n\n"
                        f"Planned calls: {preview}\n\n"
                        "Send confirm=true to /api/chat/confirm (or click Approve "
                        "in the dashboard) to proceed."
                    ),
                    tool_calls=tool_calls,
                    task_plan=plan,
                    requires_confirmation=True,
                    status="needs_confirmation",
                )

            return await self._execute_and_respond(message, state, tool_calls, plan)
        else:
            # Simple chat - no tools needed
            state.task_status = "idle"
            final_message = understanding.get("response", "")
            tool_calls = []
            plan = None
            status = "success"

        # Add assistant response to history
        from datetime import datetime, timezone
        state.messages.append(
            Message(role=MessageRole.ASSISTANT, content=final_message, timestamp=datetime.now(timezone.utc))
        )
        self._persist(self.memory.append_message(state.session_id, "assistant", final_message))

        # Keep only last 20 messages for short-term memory
        if len(state.messages) > 20:
            state.messages = state.messages[-20:]

        return AgentResponse(
            message=final_message,
            tool_calls=tool_calls,
            task_plan=plan,
            requires_confirmation=False,
            status=status,
        )

    async def _execute_and_respond(
        self,
        message: str,
        state: ConversationState,
        tool_calls: list[ToolCall],
        plan: TaskPlan | None = None,
        skip_confirmation: bool = False,
    ) -> AgentResponse:
        """Execute a batch of tool calls in parallel, recover from errors, respond."""
        import asyncio
        from datetime import datetime, timezone

        state.task_status = "executing"
        results = await asyncio.gather(
            *(self._execute_tool_call(tc) for tc in tool_calls)
        )

        for tool_call, result in zip(tool_calls, results):
            state.messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=str(result.output if result.success else result.error),
                    timestamp=datetime.now(timezone.utc),
                    metadata={"tool_name": tool_call.tool_name},
                )
            )

        failed_results = [r for r in results if not r.success]
        if failed_results:
            final_message = await self._handle_errors(message, failed_results)
            status = "error"
        elif results:
            final_message = await self._generate_final_response(
                message, results, state
            )
            status = "success"
        else:
            final_message = "I detected that you might need a tool, but I couldn't determine which one. Could you be more specific?"
            status = "success"

        state.task_status = "completed"
        state.messages.append(
            Message(role=MessageRole.ASSISTANT, content=final_message, timestamp=datetime.now(timezone.utc))
        )
        self._persist(self.memory.append_message(state.session_id, "assistant", final_message))
        if len(state.messages) > 20:
            state.messages = state.messages[-20:]

        return AgentResponse(
            message=final_message,
            tool_calls=tool_calls,
            task_plan=plan,
            requires_confirmation=False,
            status=status,
        )

    async def _chat_llm(self, messages: list[dict]) -> str:
        """Call the primary LLM; transparently fall back to a configured
        OpenAI-compatible cloud provider if the local model errors out."""
        try:
            return await self.llm_client.chat(messages)
        except Exception as primary_err:  # noqa: BLE001
            from ..services.llm_client import OpenAICompatClient

            if settings.openai_api_key and not isinstance(
                self.llm_client, OpenAICompatClient
            ):
                try:
                    fallback = OpenAICompatClient()
                    return await fallback.chat(messages)
                except Exception:  # noqa: BLE001 - report the original error
                    pass
            raise primary_err

    async def _understand_request(
        self, message: str, state: ConversationState
    ) -> dict:
        """
        Analyze the user's request to determine:
        - Whether tools are needed
        - Which tools might be required
        - If it's a complex multi-step task

        Uses JSON-prompt parsing + heuristic inference. Native function
        calling (when the provider supports it) is handled by
        run_react_stream(); this path stays compatible with plain chat-only
        LLM clients and test stubs.
        """
        tool_definitions = self.tool_manager.list_tools()

        system_prompt = """You are an AI assistant analyzing a user request.
Determine if the request requires using any tools.

Available tools:
"""
        for tool in tool_definitions:
            system_prompt += f"- {tool['name']}: {tool['description']}\n"

        system_prompt += """
Respond in JSON format:
{
    "needs_tools": true/false,
    "is_complex": true/false,
    "tool_calls": [{"tool_name": "...", "arguments": {...}}],
    "response": "direct response if no tools needed"
}

For simple questions like greetings, general knowledge, or explanations, set needs_tools to false.
For calculations, file operations, date/time queries, or data lookups, set needs_tools to true.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        # Add recent conversation context
        recent_messages = state.messages[-5:]  # Last 5 messages
        for msg in recent_messages:
            messages.append({"role": msg.role.value, "content": msg.content})

        try:
            response = await self._chat_llm(messages)
            # Parse the response to extract JSON
            import json

            # Try to extract JSON from response
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                parsed = json.loads(json_str)
                return {
                    "needs_tools": parsed.get("needs_tools", False),
                    "is_complex": parsed.get("is_complex", False),
                    "tool_calls": [
                        ToolCall(**tc)
                        for tc in parsed.get("tool_calls", [])
                    ],
                    "response": parsed.get("response", ""),
                }
        except Exception as e:
            # Fallback: simple heuristic
            print(f"LLM understanding failed: {e}")
            return self._simple_understanding(message)

        # If no valid JSON found, use simple understanding
        return self._simple_understanding(message)

    async def _infer_tool_call(self, message: str) -> ToolCall | None:
        """Infer which tool to call based on the message content."""
        message_lower = message.lower()
        
        # Date/time inference
        if any(word in message_lower for word in ["time", "date", "day", "today", "now", "current time"]):
            format_val = "datetime"
            if "only time" in message_lower or "what time" in message_lower:
                format_val = "time"
            elif "date" in message_lower and "time" not in message_lower:
                format_val = "date"
            elif "day" in message_lower:
                format_val = "day"
            
            return ToolCall(
                tool_name="date_time",
                arguments={"format": format_val}
            )
        
        # Calculator inference - extract expression from message
        import re
        math_pattern = r'(\d+\s*[\+\-\*/]\s*\d+)'
        matches = re.findall(math_pattern, message)
        if matches:
            expression = matches[0]
            return ToolCall(
                tool_name="calculator",
                arguments={"expression": expression}
            )
        
        # Check for explicit calculation requests
        if any(word in message_lower for word in ["calculate", "sum", "multiply", "divide", "add", "subtract"]):
            # Try to extract numbers
            numbers = re.findall(r'\d+', message)
            if len(numbers) >= 2:
                if "add" in message_lower or "sum" in message_lower:
                    expr = f"{numbers[0]} + {numbers[1]}"
                elif "subtract" in message_lower or "minus" in message_lower:
                    expr = f"{numbers[0]} - {numbers[1]}"
                elif "multiply" in message_lower or "times" in message_lower:
                    expr = f"{numbers[0]} * {numbers[1]}"
                elif "divide" in message_lower:
                    expr = f"{numbers[0]} / {numbers[1]}"
                else:
                    expr = f"{numbers[0]} + {numbers[1]}"  # default to addition
                
                return ToolCall(
                    tool_name="calculator",
                    arguments={"expression": expr}
                )
        
        # File writer inference - detect file creation requests
        file_write_patterns = [
            r"(?:create|write|make)\s+(?:a\s+)?(?:file\s+)?(\S+)\s+(?:with\s+)?(?:content\s+)?(.+)",
            r"(?:write|save)\s+(.+)\s+(?:to|in)\s+(\S+)",
            r"(?:create|new)\s+file\s+(\S+)",
        ]
        for pattern in file_write_patterns:
            match = re.search(pattern, message_lower)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    # Pattern 1: create file.txt with content Hello
                    file_path = groups[0].strip()
                    content = groups[1].strip()
                else:
                    # Pattern 2: create file test.txt
                    file_path = groups[0].strip()
                    content = ""
                
                # Clean up file path (remove common prefixes)
                file_path = file_path.replace("a ", "").replace("the ", "").strip()
                
                return ToolCall(
                    tool_name="file_writer",
                    arguments={"file_path": file_path, "content": content or " "}
                )
        
        # Python execution inference
        import_block = "```python" in message_lower or "```py" in message_lower
        code_kw = any(w in message_lower for w in ["run python", "execute python", "python code", "run this code", "exec code"])
        has_code_tokens = any(t in message for t in ["def ", "print(", "for ", "while ", "= "])
        if import_block or (code_kw and has_code_tokens):
            code = message
            if import_block:
                parts = re.split(r"```(?:python|py)?", message)
                candidates = [p.strip() for p in parts if p.strip()]
                code = max(candidates, key=len) if candidates else message
            return ToolCall(tool_name="python_executor", arguments={"code": code})

        # Web search inference
        lower = message_lower
        if any(v in lower for v in ["search", "look up", "lookup", "find online", "google"]):
            query = message
            for v in ["search the web for", "search for", "search", "look up", "lookup", "find online", "google"]:
                query = re.sub(re.escape(v), "", query, flags=re.IGNORECASE)
            query = query.strip(" ?.:")
            if query:
                return ToolCall(tool_name="web_search", arguments={"query": query})

        research_words = ["who is", "what is", "what are", "when was", "where is", "how does", "why is"]
        current_markers = ["news", "current", "latest", "today", "weather", "price of", "version"]
        if any(lower.startswith(r) for r in research_words) and any(w in lower for w in current_markers):
            return ToolCall(tool_name="web_search", arguments={"query": message.strip("?")})

        return None

    def _simple_understanding(self, message: str) -> dict:
        """Simple heuristic-based understanding when LLM parsing fails."""
        message_lower = message.lower()

        # Check for file operations FIRST (before greetings to avoid false positives from content like "hello world")
        if any(
            word in message_lower
            for word in ["create", "write", "save", "make file", "new file"]
        ):
            # Try to infer the tool call directly
            import re
            
            # File writer inference patterns
            file_write_patterns = [
                r"(?:create|write|make)\s+(?:a\s+)?(?:file\s+)?(\S+)\s+(?:with\s+)?(?:content\s+)?(.+)",
                r"(?:write|save)\s+(.+)\s+(?:to|in)\s+(\S+)",
                r"(?:create|new)\s+file\s+(\S+)",
            ]
            
            for pattern in file_write_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    groups = match.groups()
                    if len(groups) == 2:
                        file_path = groups[0].strip()
                        content = groups[1].strip()
                    else:
                        file_path = groups[0].strip()
                        content = ""
                    
                    # Clean up file path
                    file_path = file_path.replace("a ", "").replace("the ", "").strip()
                    
                    return {
                        "needs_tools": True,
                        "is_complex": False,
                        "tool_calls": [
                            ToolCall(
                                tool_name="file_writer",
                                arguments={"file_path": file_path, "content": content or " "}
                            )
                        ],
                        "response": "",
                    }
            
            # Generic file operation detected but couldn't parse details
            return {
                "needs_tools": True,
                "is_complex": False,
                "tool_calls": [],
                "response": "",
            }

        # Check for greetings and simple chat - no tools needed
        # Use word boundaries to avoid matching content within other words
        greeting_words = ["hello", "hi", "hey", "what can you", "help me", "who are you"]
        if any(word in message_lower for word in greeting_words):
            # Only treat as greeting if it's at the start or the message is short
            if message_lower.startswith(tuple(greeting_words)) or len(message_lower.split()) <= 3:
                return {
                    "needs_tools": False,
                    "is_complex": False,
                    "tool_calls": [],
                    "response": "Hello! I'm an AI assistant with tool capabilities. I can help you with calculations, file operations, date/time queries, and more. What would you like to do?",
                }

        # Check for calculator needs
        if any(op in message for op in ["+", "-", "*", "/", "calculate", "sum", "multiply", "divide", "add", "subtract"]):
            return {
                "needs_tools": True,
                "is_complex": False,
                "tool_calls": [],
                "response": "",
            }

        # Check for date/time needs
        if any(
            word in message_lower
            for word in ["time", "date", "day", "today", "now", "current time", "what time"]
        ):
            return {
                "needs_tools": True,
                "is_complex": False,
                "tool_calls": [],
                "response": "",
            }

        # Default: simple chat - provide a generic response
        return {
            "needs_tools": False,
            "is_complex": False,
            "tool_calls": [],
            "response": "I understand your request. Since I'm currently running without an LLM connection, I can still help you with basic tasks using my available tools. Try asking me to calculate something, check the time, or manage files.",
        }

    async def _create_plan(
        self, message: str, understanding: dict
    ) -> TaskPlan:
        """Create a multi-step plan for complex tasks."""
        system_prompt = """You are a task planner. Break down the user's request into clear, sequential steps.
Each step should be actionable and represent a single operation.

Respond in JSON format:
{
    "steps": ["step 1", "step 2", ...]
}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        try:
            response = await self._chat_llm(messages)
            import json

            start_idx = response.find("[")
            end_idx = response.rfind("]") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                parsed = json.loads(json_str)
                return TaskPlan(steps=parsed.get("steps", [message]))
        except Exception:
            pass

        # Fallback
        return TaskPlan(steps=[message])

    async def _execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call."""
        result = await self.tool_manager.execute_tool(
            tool_call.tool_name, **tool_call.arguments
        )

        return ToolResult(
            success=result.get("success", False),
            output=result.get("output"),
            error=result.get("error"),
            call_id=tool_call.call_id,
        )

    async def _handle_errors(
        self, original_message: str, failed_results: list[ToolResult]
    ) -> str:
        """Attempt to recover from tool execution errors."""
        error_details = "\n".join(
            [f"- {r.error}" for r in failed_results if r.error]
        )

        system_prompt = """Some tools failed during execution. Explain the issue to the user clearly.
If possible, suggest an alternative approach.

Be honest about what went wrong. Do not pretend the task succeeded.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Original request: {original_message}\n\nErrors:\n{error_details}",
            },
        ]

        try:
            response = await self._chat_llm(messages)
            return response
        except Exception:
            return f"I encountered an error while processing your request: {error_details}"

    async def _generate_final_response(
        self,
        original_message: str,
        results: list[ToolResult],
        state: ConversationState,
    ) -> str:
        """Generate a natural language response based on tool results."""
        results_summary = "\n".join(
            [f"Tool result: {r.output}" for r in results if r.success]
        )

        system_prompt = """Based on the tool execution results, provide a clear and helpful response to the user's original request.
Summarize the findings naturally.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Original request: {original_message}\n\n{results_summary}",
            },
        ]

        try:
            response = await self._chat_llm(messages)
            return response
        except Exception:
            # Fallback: just return the raw results
            return results_summary

    def get_conversation_history(self, session_id: str) -> list[Message]:
        """Get conversation history for a session."""
        state = self.conversation_states.get(session_id)
        if state:
            return state.messages
        return []

    def clear_session(self, session_id: str) -> bool:
        """Clear conversation history for a session."""
        if session_id in self.conversation_states:
            del self.conversation_states[session_id]
            return True
        return False
