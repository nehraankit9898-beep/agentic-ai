"""Advanced: memory_store tool — lets the agent persist durable facts.

Actions: set / get / delete / search / list. Backed by the shared SQLite
MemoryStore singleton (app.services.memory). No confirmation needed: writes
are confined to the agent's own facts table, never the filesystem.
"""

from .base import BaseTool


class MemoryStoreTool(BaseTool):
    """Long-term key/value facts for the assistant."""

    name = "memory_store"
    description = (
        "Persist and recall long-term facts across sessions. Actions: "
        "'set' (key+value), 'get' (key), 'delete' (key), 'search' (query), "
        "'list'. Use when the user shares preferences or info worth "
        "remembering, or asks what you remember."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["set", "get", "delete", "search", "list"],
                "description": "Memory operation to perform",
            },
            "key": {"type": "string", "description": "Fact key (for set/get/delete)"},
            "value": {"type": "string", "description": "Fact value (for set)"},
            "query": {"type": "string", "description": "Search text (for search)"},
        },
        "required": ["action"],
    }

    def validate_input(self, **kwargs) -> tuple[bool, str | None]:
        action = kwargs.get("action")
        if action not in {"set", "get", "delete", "search", "list"}:
            return False, "Input 'action' must be one of set/get/delete/search/list"
        if action in {"set", "get", "delete"}:
            key = kwargs.get("key")
            if not isinstance(key, str) or not key.strip():
                return False, f"'key' is required for action '{action}'"
            if len(key) > 200:
                return False, "'key' too long (max 200 chars)"
        if action == "set":
            value = kwargs.get("value")
            if not isinstance(value, str) or not value.strip():
                return False, "'value' is required for action 'set'"
        if action == "search":
            query = kwargs.get("query")
            if not isinstance(query, str) or not query.strip():
                return False, "'query' is required for action 'search'"
        return True, None

    async def execute(
        self,
        action: str,
        key: str = "",
        value: str = "",
        query: str = "",
    ) -> dict:
        from ..services.memory import memory

        try:
            if action == "set":
                await memory.set_fact(key.strip(), value.strip())
                return {"success": True, "output": f"Remembered: {key} = {value}"}
            if action == "get":
                v = await memory.get_fact(key.strip())
                if v is None:
                    return {"success": False, "error": f"No fact stored under key '{key}'"}
                return {"success": True, "output": f"{key} = {v}"}
            if action == "delete":
                removed = await memory.delete_fact(key.strip())
                return {
                    "success": True,
                    "output": f"Deleted '{key}'" if removed else f"No fact named '{key}'",
                }
            if action == "search":
                rows = await memory.search_facts(query.strip())
                if not rows:
                    return {"success": True, "output": "No matching facts."}
                text = "\n".join(f"- {r['key']}: {r['value']}" for r in rows)
                return {"success": True, "output": text}
            # list
            rows = await memory.all_facts()
            if not rows:
                return {"success": True, "output": "I have no stored facts yet."}
            text = "\n".join(f"- {r['key']}: {r['value']}" for r in rows)
            return {"success": True, "output": text}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"Memory operation failed: {e}"}
