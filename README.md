# Agentic AI Personal Assistant

A modular AI assistant with tool calling capabilities, powered by local LLMs (Ollama).

## Features

- Natural language conversation
- Tool calling (calculator, file operations, date/time)
- Modular architecture for easy extension
- Local LLM support via Ollama
- Configurable security and permissions

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── agent/               # Agent logic (Phase 2+)
│   ├── tools/               # Tool implementations
│   │   ├── base.py          # Base tool class
│   │   ├── manager.py       # Tool manager
│   │   ├── calculator.py    # Calculator tool
│   │   ├── file_reader.py   # File reading tool
│   │   ├── file_writer.py   # File writing tool
│   │   ├── directory_lister.py  # Directory listing tool
│   │   └── date_time.py     # Date/time tool
│   ├── memory/              # Memory systems (Phase 5+)
│   ├── models/              # Pydantic models
│   ├── services/            # External services (LLM client)
│   ├── api/                 # API routes
│   └── core/                # Configuration
├── tests/                   # Test suite
├── requirements.txt         # Python dependencies
└── .env.example            # Environment variables template
```

## Phase 1: Backend Setup & Basic Chat

### Prerequisites

1. Install Python 3.10+
2. Install Ollama from https://ollama.ai
3. Pull a model: `ollama pull llama3.2`

### Installation

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### Running the Server

```bash
# Make sure Ollama is running
ollama serve

# Start the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Health check
curl http://localhost:8000/health

# List tools
curl http://localhost:8000/tools

# Chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

## Upcoming Phases

- **Phase 2**: Agent controller and task planning
- **Phase 3**: Tool calling integration
- **Phase 4**: Python execution tool
- **Phase 5**: Memory and task history
- **Phase 6**: React frontend
- **Phase 7**: Web search and additional tools
- **Phase 8**: Testing and hardening

## Security Notes

- File operations are restricted to the current working directory
- Python execution uses a sandboxed environment
- Dangerous operations require explicit confirmation
- API keys and secrets should be stored in `.env`

## License

MIT