import asyncio
import base64
import os
import shlex
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import commands
from app.schemas import WorkflowStepCreate


def python_command(script: str) -> str:
    if os.name == "nt":
        encoded = base64.b64encode(script.encode()).decode()
        return f"& '{sys.executable.replace(chr(39), chr(39) * 2)}' -c \"import base64;exec(base64.b64decode('{encoded}'))\""
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def test_legacy_agent_step_and_command_validation():
    agent = WorkflowStepCreate(sub_agent_id="agent-1", payload={"task": "read"})
    assert agent.step_type == "sub_agent"
    command = WorkflowStepCreate(step_type="command", command="python task.py")
    assert command.sub_agent_id is None
    for payload in [
        {},
        {"step_type": "unknown", "command": "echo hi"},
        {"step_type": "command", "command": "  "},
        {"step_type": "command", "command": "echo hi", "sub_agent_id": "random-uuid"},
        {"step_type": "command", "command": "echo hi", "payload": {"invalid": True}},
        {"step_type": "sub_agent", "sub_agent_id": "one", "command": "echo hi"},
        {"step_type": "command", "command": "echo hi", "timeout_seconds": 0},
        {"step_type": "command", "command": "echo hi", "timeout_seconds": 86401},
        {"step_type": "command", "command": "echo\x00hi"},
    ]:
        with pytest.raises(ValidationError):
            WorkflowStepCreate.model_validate(payload)


def test_command_authoring_is_opt_in_and_token_protected(monkeypatch):
    monkeypatch.delenv("EYE_ENABLE_COMMAND_STEPS", raising=False)
    with pytest.raises(HTTPException) as disabled:
        commands.authorize_command_edit("secret")
    assert disabled.value.status_code == 403
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    monkeypatch.delenv("EYE_COMMAND_ADMIN_TOKEN", raising=False)
    with pytest.raises(HTTPException) as unconfigured:
        commands.authorize_command_edit("secret")
    assert unconfigured.value.status_code == 503
    monkeypatch.setenv("EYE_COMMAND_ADMIN_TOKEN", "secret")
    for token in [None, "wrong"]:
        with pytest.raises(HTTPException) as forbidden:
            commands.authorize_command_edit(token)
        assert forbidden.value.status_code == 403
    commands.authorize_command_edit("secret")


def test_command_captures_output_cwd_and_does_not_inherit_admin_token(monkeypatch, tmp_path):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    monkeypatch.setenv("EYE_COMMAND_ADMIN_TOKEN", "secret")
    result = asyncio.run(commands.execute_command(python_command(
        'import os,sys; print(os.getcwd()); print(os.getenv("EYE_COMMAND_ADMIN_TOKEN", "absent")); print("warning", file=sys.stderr)'
    ), str(tmp_path), 10))
    assert result["exit_code"] == 0
    assert "absent" in result["stdout"]
    assert str(tmp_path) in result["stdout"]
    assert "warning" in result["stderr"]
    assert result["timed_out"] is False


def test_command_preserves_unicode_output(monkeypatch):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    result = asyncio.run(commands.execute_command(python_command('print("résumé 世界")'), timeout_seconds=10))
    assert "résumé 世界" in result["stdout"]


def test_command_nonzero_exit_preserves_both_streams(monkeypatch):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    with pytest.raises(commands.CommandExecutionError) as raised:
        asyncio.run(commands.execute_command(python_command(
            'import sys; print("partial output", flush=True); print("problem", file=sys.stderr); sys.exit(7)'
        ), timeout_seconds=10))
    assert raised.value.result["exit_code"] == 7
    assert "partial output" in raised.value.result["stdout"]
    assert "problem" in raised.value.result["stderr"]


def test_output_is_bounded_without_deadlocking(monkeypatch):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    monkeypatch.setattr(commands, "OUTPUT_LIMIT_BYTES", 1024)
    result = asyncio.run(commands.execute_command(python_command(
        'import sys; print("x"*50000); print("y"*50000, file=sys.stderr)'
    ), timeout_seconds=10))
    assert len(result["stdout"].encode()) == 1024
    assert len(result["stderr"].encode()) == 1024
    assert result["stdout_truncated"] and result["stderr_truncated"]


def test_timeout_kills_process_tree_and_preserves_output(monkeypatch, tmp_path):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    marker = tmp_path / "should-not-exist.txt"
    child = f'import time; from pathlib import Path; time.sleep(3); Path({str(marker)!r}).write_text("still alive")'
    script = f'import subprocess,sys,time; subprocess.Popen([sys.executable, "-c", {child!r}]); print("before timeout", flush=True); time.sleep(30)'

    async def scenario():
        with pytest.raises(commands.CommandExecutionError) as raised:
            await commands.execute_command(python_command(script), timeout_seconds=1)
        assert raised.value.result["timed_out"]
        # Shell startup may itself consume the deadline on a busy Windows host.
        assert isinstance(raised.value.result["stdout"], str)
        await asyncio.sleep(3)
        assert not marker.exists()

    asyncio.run(scenario())


def test_cancellation_kills_process(monkeypatch, tmp_path):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    marker = tmp_path / "late.txt"
    script = f'import time; from pathlib import Path; print("start", flush=True); time.sleep(3); Path({str(marker)!r}).write_text("late")'

    async def scenario():
        task = asyncio.create_task(commands.execute_command(python_command(script)))
        await asyncio.sleep(1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(3)
        assert not marker.exists()

    asyncio.run(scenario())


def test_disabled_commands_and_missing_directory_fail_before_start(monkeypatch, tmp_path):
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "false")
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(commands.execute_command("echo unexpected"))
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    with pytest.raises(ValueError, match="does not exist"):
        asyncio.run(commands.execute_command("echo unexpected", str(tmp_path / "missing")))
