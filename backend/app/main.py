from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import settings
from .core.logging import configure_logging
from .services.llm_client import LLMClient
from .tools.manager import ToolManager
from .api.chat import router as chat_router
from .api.errors import register_error_handlers


# Global instances
llm_client: LLMClient | None = None
tool_manager: ToolManager | None = None
agent_controller: "AgentController | None" = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global llm_client, tool_manager, agent_controller

    # Startup
    configure_logging(settings.log_level)
    app.state.debug = settings.debug
    llm_client = LLMClient()
    tool_manager = ToolManager()

    from .agent.controller import AgentController
    agent_controller = AgentController(llm_client, tool_manager)

    yield

    # Shutdown
    if llm_client:
        await llm_client.aclose()


def get_agent():
    """Return the shared AgentController (singleton keeps session state)."""
    if agent_controller is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent_controller


app = FastAPI(
    title="Agentic AI Assistant",
    description="AI assistant with tool calling capabilities",
    version="0.1.0",
    lifespan=lifespan,
)

# Standard error envelope + request-id middleware (must be registered before routers)
register_error_handlers(app)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Agentic AI Assistant",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    llm_healthy = False
    if llm_client:
        llm_healthy = await llm_client.check_health()

    return {
        "status": "healthy" if llm_healthy else "degraded",
        "llm_available": llm_healthy,
        "tools_available": len(tool_manager.list_tools()) if tool_manager else 0,
    }


@app.get("/tools")
async def list_tools():
    """List available tools."""
    if not tool_manager:
        raise HTTPException(status_code=503, detail="Tool manager not initialized")

    return {"tools": tool_manager.list_tools()}


# Alias endpoints under /api so the frontend can use a single proxied prefix
@app.get("/api/tools")
async def list_tools_api():
    """List available tools (API-prefixed alias)."""
    return await list_tools()


@app.get("/api/health")
async def health_check_api():
    """Health check (API-prefixed alias)."""
    return await health_check()
