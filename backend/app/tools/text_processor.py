"""Advanced: text processing tool (case transforms, word/char stats, base64).

Pure computation only — no file or network access — so it never requires
confirmation and is safe to expose to the LLM for quick text tasks.
"""

import base64
import re

from .base import BaseTool


class TextProcessorTool(BaseTool):
    """Common text transformations and statistics."""

    name = "text_processor"
    description = (
        "Process text: operations = 'stats' (word/char/line counts), "
        "'upper', 'lower', 'title', 'reverse', 'sort_lines', "
        "'dedupe_lines', 'base64_encode', 'base64_decode', "
        "'slugify', 'word_frequency' (top words as JSON)."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Input text"},
            "operation": {
                "type": "string",
                "enum": [
                    "stats", "upper", "lower", "title", "reverse",
                    "sort_lines", "dedupe_lines", "base64_encode",
                    "base64_decode", "slugify", "word_frequency",
                ],
                "description": "Operation to perform",
            },
        },
        "required": ["text", "operation"],
    }

    MAX_INPUT_LENGTH = 200_000

    def validate_input(self, **kwargs) -> tuple[bool, str | None]:
        text = kwargs.get("text")
        if not isinstance(text, str):
            return False, "Input 'text' must be a string"
        if len(text) > self.MAX_INPUT_LENGTH:
            return False, f"Text too long (max {self.MAX_INPUT_LENGTH} characters)"
        op = kwargs.get("operation")
        allowed = set(self.input_schema["properties"]["operation"]["enum"])
        if op not in allowed:
            return False, f"Unknown operation '{op}'. Allowed: {sorted(allowed)}"
        return True, None

    async def execute(self, text: str, operation: str) -> dict:
        try:
            if operation == "stats":
                words = re.findall(r"\S+", text)
                output = {
                    "characters": len(text),
                    "characters_no_spaces": len(re.sub(r"\s", "", text)),
                    "words": len(words),
                    "lines": len(text.splitlines()),
                }
            elif operation == "upper":
                output = text.upper()
            elif operation == "lower":
                output = text.lower()
            elif operation == "title":
                output = text.title()
            elif operation == "reverse":
                output = text[::-1]
            elif operation == "sort_lines":
                output = "\n".join(sorted(text.splitlines()))
            elif operation == "dedupe_lines":
                seen: list[str] = []
                for line in text.splitlines():
                    if line not in seen:
                        seen.append(line)
                output = "\n".join(seen)
            elif operation == "base64_encode":
                output = base64.b64encode(text.encode()).decode()
            elif operation == "base64_decode":
                output = base64.b64decode(text.encode(), validate=True).decode(
                    "utf-8", errors="replace"
                )
            elif operation == "slugify":
                slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
                output = slug
            elif operation == "word_frequency":
                import json

                words = re.findall(r"[a-zA-Z0-9']+", text.lower())
                freq: dict[str, int] = {}
                for w in words:
                    freq[w] = freq.get(w, 0) + 1
                top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
                output = json.dumps(dict(top), indent=2)
            else:  # pragma: no cover - guarded by validate_input
                return {"success": False, "error": f"Unknown operation: {operation}"}

            return {"success": True, "output": output, "operation": operation}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"Text processing failed: {e}"}
