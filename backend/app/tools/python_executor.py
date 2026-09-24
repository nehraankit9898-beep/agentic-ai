import ast
import asyncio
import json
import sys
from .base import BaseTool


# Modules that are safe for basic computation / text processing.
ALLOWED_MODULES = {
    "math", "random", "datetime", "json", "re", "collections", "itertools",
    "functools", "statistics", "string", "textwrap", "hashlib", "base64",
    "decimal", "fractions", "copy", "enum", "dataclasses", "typing", "time",
}

# Builtins that are always blocked (system access).
BLOCKED_BUILTINS = {
    "__import__", "exec", "eval", "compile", "open", "input", "breakpoint",
    "exit", "quit", "globals", "locals", "vars", "dir", "help", "memoryview",
    "getattr", "setattr", "delattr", "super", "object", "type",
    "classmethod", "staticmethod", "property", "wrapped",
}

# AST nodes that indicate dangerous capability usage.
FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
)


class PythonExecutorTool(BaseTool):
    """Execute short Python snippets in a restricted sandbox."""

    name = "python_executor"
    description = (
        "Execute a small Python 3 code snippet in a restricted sandbox and "
        "return its stdout. Only pure computation and text processing are "
        "allowed: no file I/O, imports outside a safe list, or system access."
    )
    requires_confirmation = True  # code execution must be user-approved
    timeout_seconds = 5

    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python 3 source code to execute",
            }
        },
        "required": ["code"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "output": {"type": "string", "description": "Captured stdout/stderr"},
            "error": {"type": "string"},
        },
    }

    def validate_input(self, **kwargs) -> tuple[bool, str | None]:
        code = kwargs.get("code")
        if not isinstance(code, str) or not code.strip():
            return False, "Input 'code' must be a non-empty string"
        return self._static_check(code)

    @staticmethod
    def _static_check(code: str) -> tuple[bool, str | None]:
        """Reject code that clearly escapes the sandbox before running it."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error on line {e.lineno}: {e.msg}"

        for node in ast.walk(tree):
            # Attribute access like os.system(...) is blocked via dunder names.
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                return False, "Access to private/dunder attributes is not allowed"
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, str) and node.slice.value.startswith("__"):
                    return False, "Access to private/dunder attributes is not allowed"
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                return False, "'global'/'nonlocal' statements are not allowed"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in ALLOWED_MODULES:
                        return False, f"Import of module '{alias.name}' is not allowed"
            if isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root not in ALLOWED_MODULES:
                    return False, f"Import from module '{node.module}' is not allowed"
            # Direct calls: eval(...), getattr(...), ...
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_BUILTINS:
                    return False, f"Use of '{node.func.id}()' is not allowed in the sandbox"
            # Indirect references: x = eval; x(...); map(eval, ...) etc.
            # Any *load* of a blocked builtin name outside a direct call is
            # rejected so blocked builtins cannot be aliased or passed around.
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in BLOCKED_BUILTINS:
                    return False, f"Reference to '{node.id}' is not allowed in the sandbox"
        return True, None

    async def execute(self, code: str) -> dict:
        is_valid, error = self._static_check(code)
        if not is_valid:
            return {"success": False, "error": f"Sandbox policy violation: {error}"}

        # Run in a separate OS process so infinite loops can be hard-killed.
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-I", "-c", _SANDBOX_RUNNER,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin"},  # minimal env: no secrets leak
            )
        except Exception as e:
            return {"success": False, "error": f"Could not start sandbox process: {e}"}

        payload = json.dumps({"code": code, "allowed": sorted(ALLOWED_MODULES)})
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(payload.encode()), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return {
                "success": False,
                "error": f"Execution timed out after {self.timeout_seconds}s and was terminated",
            }

        out = stdout.decode(errors="replace")
        # Cap captured output to prevent resource exhaustion via huge prints.
        max_output = 200_000
        if len(out) > max_output:
            out = out[:max_output] + "\n...(output truncated)"
        try:
            result = json.loads(out.strip().splitlines()[-1])
            return result
        except (ValueError, IndexError):
            err = stderr.decode(errors="replace").strip() or f"Runner exited with {proc.returncode}"
            return {"success": False, "output": out, "error": f"Sandbox runner error: {err[:2000]}"}


# Standalone runner executed via `python -I -c`. Reads JSON {code, allowed} on
# stdin, applies the same static policy check, then execs inside restricted
# builtins. Prints a single JSON line {success, output|error} on stdout.
_SANDBOX_RUNNER = r'''
import ast, json, sys, builtins, resource
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

BLOCKED = {"__import__","exec","eval","compile","open","input","breakpoint",
           "exit","quit","globals","locals","vars","dir","help","memoryview",
           "getattr","setattr","delattr","super","object","type",
           "classmethod","staticmethod","property","wrapped"}

def check(code, allowed):
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return "Access to private/dunder attributes is not allowed"
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
           and isinstance(node.slice.value, str) and node.slice.value.startswith("__"):
            return "Access to private/dunder attributes is not allowed"
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return "global/nonlocal statements are not allowed"
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in allowed:
                    return "Import of module '%s' is not allowed" % a.name
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in allowed:
                return "Import from module '%s' is not allowed" % node.module
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
           and node.func.id in BLOCKED:
            return "Use of '%s()' is not allowed in the sandbox" % node.func.id
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) \
           and node.id in BLOCKED:
            return "Reference to '%s' is not allowed in the sandbox" % node.id
    return None

def apply_limits():
    # Cap address space (~1 GB) and CPU time (4s, below the 5s hard kill).
    try:
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024,) * 2)
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
    except Exception:
        pass

def main():
    payload = json.load(sys.stdin)
    code, allowed = payload["code"], set(payload["allowed"])
    reason = None
    try:
        reason = check(code, allowed)
    except SyntaxError as e:
        reason = "Syntax error on line %s: %s" % (e.lineno, e.msg)
    if reason:
        print(json.dumps({"success": False, "error": "Sandbox policy violation: " + reason}))
        return
    apply_limits()
    safe = {n: getattr(builtins, n) for n in dir(builtins)
            if n not in BLOCKED and not n.startswith("__")}
    real_import = builtins.__import__
    def guarded(name, *a, **k):
        if name.split(".")[0] not in allowed:
            raise ImportError("Module '%s' is not allowed in the sandbox" % name)
        return real_import(name, *a, **k)
    safe["__import__"] = guarded
    g = {"__builtins__": safe, "__name__": "__sandbox__"}
    l = {}
    buf, ebuf = StringIO(), StringIO()
    try:
        compiled = compile(code, "<sandbox>", "exec")
        with redirect_stdout(buf), redirect_stderr(ebuf):
            exec(compiled, g, l)
        if ebuf.getvalue():
            print(json.dumps({"success": False, "output": buf.getvalue(),
                              "error": ebuf.getvalue().strip()}))
        else:
            print(json.dumps({"success": True,
                              "output": buf.getvalue().rstrip("\n") or "(no output)"}))
    except BaseException as e:
        print(json.dumps({"success": False, "output": buf.getvalue(),
                          "error": "%s: %s" % (type(e).__name__, e)}))

main()
'''
