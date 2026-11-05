import asyncio
import hmac
import os
import signal
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import HTTPException

OUTPUT_LIMIT_BYTES = 256 * 1024


def commands_enabled() -> bool:
    return os.getenv("EYE_ENABLE_COMMAND_STEPS", "false").lower() == "true"


def authorize_command_edit(token: str | None) -> None:
    if not commands_enabled():
        raise HTTPException(status_code=403, detail="Command steps are disabled on this Eye server")
    expected = os.getenv("EYE_COMMAND_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="EYE_COMMAND_ADMIN_TOKEN must be configured")
    if token is None or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="A valid command admin token is required")


class CommandExecutionError(RuntimeError):
    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


async def _capture(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
    data = bytearray()
    truncated = False
    while chunk := await stream.read(64 * 1024):
        remaining = max(0, limit - len(data))
        data.extend(chunk[:remaining])
        truncated = truncated or len(chunk) > remaining
    return data.decode("utf-8", errors="replace"), truncated


async def _terminate_tree(process: asyncio.subprocess.Process) -> None:
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill.exe", "/PID", str(process.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.kill()
    await process.wait()


async def execute_command(
    command: str,
    working_directory: str | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if not commands_enabled():
        raise RuntimeError("Command steps are disabled on this Eye server")
    cwd = Path(working_directory).expanduser() if working_directory else Path(__file__).resolve().parents[1]
    if not cwd.is_dir():
        raise ValueError(f"Command working directory does not exist: {cwd}")
    arguments = (
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$ErrorActionPreference = 'Stop'; "
            "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
            f"& {{\n{command}\n}} | Out-String -Stream | ForEach-Object {{ "
            "[Console]::Out.WriteLine($_); [Console]::Out.Flush() }; "
            "if ($LASTEXITCODE) { exit $LASTEXITCODE }",
        ]
        if os.name == "nt"
        else ["/bin/sh", "-c", command]
    )
    environment = os.environ.copy()
    environment.pop("EYE_COMMAND_ADMIN_TOKEN", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=str(cwd),
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **({"start_new_session": True} if os.name != "nt" else {}),
    )
    stdout_task = asyncio.create_task(_capture(process.stdout, OUTPUT_LIMIT_BYTES))
    stderr_task = asyncio.create_task(_capture(process.stderr, OUTPUT_LIMIT_BYTES))
    collection = asyncio.gather(process.wait(), stdout_task, stderr_task)
    timed_out = False
    try:
        await asyncio.wait_for(asyncio.shield(collection), timeout_seconds)
    except TimeoutError:
        timed_out = True
        await _terminate_tree(process)
        await collection
    except BaseException:
        await _terminate_tree(process)
        await collection
        raise
    stdout, stdout_truncated = stdout_task.result()
    stderr, stderr_truncated = stderr_task.result()
    result = {
        "step_type": "command",
        "command": command,
        "working_directory": str(cwd.resolve()),
        "exit_code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }
    if timed_out:
        raise CommandExecutionError(f"Command timed out after {timeout_seconds}s", result)
    if process.returncode != 0:
        raise CommandExecutionError(f"Command exited with code {process.returncode}", result)
    return result
