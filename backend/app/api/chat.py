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
    from ..main import llm_client, tool_manager
    from ..agent.controller import AgentController

    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    if not tool_manager:
        raise HTTPException(status_code=503, detail="Tool manager not initialized")

    try:
        # Create agent controller
        agent = AgentController(llm_client, tool_manager)

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


@router.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Get conversation history for a session."""
    from ..main import llm_client, tool_manager
    from ..agent.controller import AgentController

    if not llm_client or not tool_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")

    agent = AgentController(llm_client, tool_manager)
    history = agent.get_conversation_history(session_id)

    return {
        "session_id": session_id,
        "messages": [msg.model_dump() for msg in history],
    }


@router.delete("/conversation/{session_id}")
async def clear_conversation(session_id: str):
    """Clear conversation history for a session."""
    from ..main import llm_client, tool_manager
    from ..agent.controller import AgentController

    if not llm_client or not tool_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")

    agent = AgentController(llm_client, tool_manager)
    success = agent.clear_session(session_id)

    return {"success": success, "session_id": session_id}
