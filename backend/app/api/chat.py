from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..models.schemas import AgentResponse

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    message: str
    session_id: str
    status: str = "success"
    tool_calls: list = []
    task_plan: Optional[dict] = None



@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with agent workflow - Phase 2 implementation.

    Uses the AgentController to understand, plan, and execute tasks.
    """
    from ..main import get_agent

    agent = get_agent()

    try:

        # Process request through agent workflow
        response: AgentResponse = await agent.process_request(
            message=request.message, session_id=request.session_id or "default"
        )

        return ChatResponse(
            message=response.message,
            session_id=request.session_id or "default",
            status=response.status,
            tool_calls=[
                tc.model_dump() for tc in response.tool_calls
            ],
            task_plan=response.task_plan.model_dump()
            if response.task_plan
            else None,
        )

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"LLM service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


class ConfirmRequest(BaseModel):
    """Request model for approving pending tool calls."""

    session_id: str = "default"


@router.post("/chat/confirm", response_model=ChatResponse)
async def confirm_pending(request: ConfirmRequest):
    """Approve and execute tool calls that were paused for confirmation."""
    from ..main import get_agent

    agent = get_agent()
    state = agent.get_or_create_state(request.session_id)
    if not state.pending_tool_calls:
        raise HTTPException(status_code=409, detail="No pending tool calls to confirm")

    original_message = state.current_task or "confirmed task"
    try:
        response: AgentResponse = await agent.process_request(
            message=original_message, session_id=request.session_id, confirmed=True
        )
        return ChatResponse(
            message=response.message,
            session_id=request.session_id,
            status=response.status,
            tool_calls=[tc.model_dump() for tc in response.tool_calls],
            task_plan=response.task_plan.model_dump() if response.task_plan else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/chat/cancel", response_model=ChatResponse)
async def cancel_pending(request: ConfirmRequest):
    """Discard pending tool calls without executing them."""
    from ..main import get_agent

    agent = get_agent()
    state = agent.get_or_create_state(request.session_id)
    count = len(state.pending_tool_calls)
    state.pending_tool_calls = []
    state.task_status = "idle"
    return ChatResponse(
        message=f"Cancelled {count} pending tool call(s). Nothing was executed.",
        session_id=request.session_id,
        status="cancelled",
    )


@router.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Get conversation history for a session."""
    from ..main import get_agent

    agent = get_agent()
    history = agent.get_conversation_history(session_id)

    return {
        "session_id": session_id,
        "messages": [msg.model_dump() for msg in history],
    }


@router.delete("/conversation/{session_id}")
async def clear_conversation(session_id: str):
    """Clear conversation history for a session."""
    from ..main import get_agent

    agent = get_agent()
    success = agent.clear_session(session_id)

    return {"success": success, "session_id": session_id}
