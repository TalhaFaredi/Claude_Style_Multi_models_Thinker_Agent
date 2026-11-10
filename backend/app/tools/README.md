# Tools

Code the model can ask to run (spec Part 1, Mode A). One file per tool; `__init__.py` is the registry.

| File | Tool | Setup switch | Safety |
|---|---|---|---|
| `web_search.py` | `web_search` | Web search | read-only; results wrapped as DATA; numbered `[n]` across the run |
| `read_webpage.py` | `read_webpage` | Web search | only links `web_search` returned in this run; public IP addresses only, redirects included |
| `calculator.py` | `calculator` | Code | parses a math syntax tree; never runs code; size limits |
| `file_search.py` | `search_files` | Files | this chat's files only |
| `code_runner.py` | `run_code` | Code | asks permission; Linux Docker container with no network/host mounts, read-only filesystem and resource limits |

## How a tool is built

```python
# app/tools/my_tool.py
from app.tools.base import Tool, ToolResult, ToolRun

async def _run(args: dict, state: ToolRun) -> ToolResult:
    ...                                   # do the work; never raise for bad input, return ok=False
    return ToolResult("text the model reads", done_label="Shown in the UI chip", citations=["[1] example.org"])

TOOL = Tool(name="my_tool", setting="web", description="When to use it.",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            run=_run, running_label=lambda a: "Working...")
```

Then add `my_tool.TOOL` to `TOOLS` in `__init__.py` and a test in `tests/test_hubs.py`.

## Rules (enforced in `__init__.py` and `app/modes/common/tool_loop.py`)

- The model gets only tools that are switched on and available (`specs_for`), and none if it has no tool support (C9). Every returned call is checked against that answer's allow-list again before execution.
- At most 10 tool calls per answer or Planner step; the same counter survives Checker retries. Step children share citations and found URLs, while keeping separate counters (C10).
- Risky tools require an explicit permission response for that action (C11); missing or denied permission means the action is refused.
- A crashing tool returns an error text to the model; it never breaks the answer.
- Outside content goes back wrapped as DATA. A tool must never send the user's private data anywhere the user did not ask for.
- Every invocation, refusal and failure is durably logged without storing arguments or result contents.

## Code sandbox setup

Install Docker with a running **Linux** container engine, then install the sandbox image once:

```powershell
docker pull python:3.12-alpine
```

The API checks Docker and the local image before offering `run_code`; an unavailable engine/image is shown with its actual reason. It does not pull images or run inference during its health check. Set `CODE_SANDBOX_IMAGE` to a preinstalled compatible Python image to use another image or a pinned digest.

Code runs with a 10-second timeout, 128 MiB memory, one CPU, 32 processes, an unprivileged UID, dropped capabilities, no network, no host mounts, a read-only root and a 16 MiB temporary filesystem. Output is capped at 16,000 bytes. Stop/timeout removes the named container. Model code is passed on stdin and is never executed by the host Python interpreter.

Direct trusted callers must supply `tools.execute(..., allowed={...})` or `ToolRun.allowed_tools`; leaving both empty deliberately refuses every action. They must provide an asynchronous `ToolRun.permission(name, args)` callback for risky actions.
