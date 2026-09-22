from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Simple chat endpoint - Phase 1 implementation.

    This provides basic LLM-powered conversation without tool calling yet.
    Tool calling and agent workflow will be added in Phase 2-3.
    """
    from ..main import llm_client

    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")

    try:
        # Prepare messages for LLM
        messages = [
            {
                "role": "system",
                "content": "You are a helpful AI assistant. Provide clear, concise answers.",
            },
            {"role": "user", "content": request.message},
        ]

        # Get response from LLM
        response = await llm_client.chat(messages)

        return ChatResponse(
            message=response,
            session_id=request.session_id or "default",
            status="success",
        )

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"LLM service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
