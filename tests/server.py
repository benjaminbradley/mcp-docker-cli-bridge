"""MCP Docker CLI Bridge — exposes whitelisted CLI commands as MCP tools."""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CommandEntry(BaseModel):
    """A single command in the whitelist."""

    command: list[str]
    allow_extra_args: bool
    cwd: str
    timeout: int | None = None

    @field_validator("command")
    @classmethod
    def command_must_be_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("command must be a non-empty list")
        return v


class CommandsConfig(BaseModel):
    """The entire commands.json file."""

    default_timeout: int = 60
    commands: dict[str, CommandEntry]

    def effective_timeout(self, name: str) -> int:
        """Return per-command timeout if set, otherwise default_timeout."""
        entry = self.commands[name]
        return entry.timeout if entry.timeout is not None else self.default_timeout


class CommandResult(BaseModel):
    """Subprocess execution result, serialized into MCP tool result text."""

    stdout: str
    stderr: str
    exit_code: int


class LogEntry(BaseModel):
    """Single JSONL log line. Serialized via model_dump_json()."""

    timestamp: datetime
    command: str | None
    args: list[str] | None
    exit_code: int | None
    duration_ms: int
    stdout: str | None
    stderr: str | None
    stdout_bytes: int
    stderr_bytes: int
    rejected: bool
    rejection_reason: str | None = None


class BridgeConfig(BaseModel):
    """Server configuration loaded from environment variables."""

    port: int = 7357
    host: str = "0.0.0.0"
    commands_file: str = "/bridge/commands.json"
    log_dir: str = "/bridge/logs"
    log_file: str = "bridge.jsonl"


# ---------------------------------------------------------------------------
# Concurrency state
# ---------------------------------------------------------------------------

_lock: asyncio.Lock = asyncio.Lock()
_current_command: str | None = None

# ---------------------------------------------------------------------------
# Config and command loaders
# ---------------------------------------------------------------------------


def load_config() -> BridgeConfig:
    """Read BRIDGE_* environment variables and return a validated BridgeConfig."""
    return BridgeConfig(
        host=os.environ.get("BRIDGE_HOST", "0.0.0.0"),
        port=int(os.environ.get("BRIDGE_PORT", "7357")),
        commands_file=os.environ.get("BRIDGE_COMMANDS_FILE", "/bridge/commands.json"),
        log_dir=os.environ.get("BRIDGE_LOG_DIR", "/bridge/logs"),
        log_file=os.environ.get("BRIDGE_LOG_FILE", "bridge.jsonl"),
    )


def load_commands(path: str) -> CommandsConfig:
    """Read and validate commands.json. Exits non-zero on any error."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: commands file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        return CommandsConfig(**data)
    except Exception as e:
        print(f"Error: invalid commands config in {path}:\n{e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument validator
# ---------------------------------------------------------------------------

BLOCKED_SEQUENCES = [";", "&&", "||", "|", "`", "$(", ">", "<"]


def validate_args(args: list) -> str | None:
    """Return None if args are valid, or an error message string if invalid."""
    for arg in args:
        if not isinstance(arg, str):
            return f"Argument must be a string, got {type(arg).__name__}: {arg!r}"
        for seq in BLOCKED_SEQUENCES:
            if seq in arg:
                return f"Argument contains disallowed characters: {arg!r}"
    return None


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


async def execute_command(
    name: str, args: list[str], config: CommandsConfig
) -> CommandResult:
    """Run the whitelisted command in a thread pool and return its result. Raises on timeout or missing executable."""
    entry = config.commands[name]
    argv = entry.command + args
    timeout = config.effective_timeout(name)
    result = await asyncio.to_thread(
        subprocess.run,
        argv,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=entry.cwd,
    )
    return CommandResult(
        stdout=result.stdout, stderr=result.stderr, exit_code=result.returncode
    )


# ---------------------------------------------------------------------------
# Request logger
# ---------------------------------------------------------------------------


def log_request(entry: LogEntry, log_dir: str, log_file: str) -> None:
    """Append a JSONL log line to the log file. Creates directory and file if needed."""
    path = Path(log_dir) / log_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(entry.model_dump_json() + "\n")


# ---------------------------------------------------------------------------
# Tool builder
# ---------------------------------------------------------------------------


def build_tools(config: CommandsConfig) -> list[Tool]:
    """Generate MCP Tool definitions from CommandsConfig."""
    tools = []
    for name, entry in config.commands.items():
        description = "Execute: " + " ".join(entry.command)
        if entry.allow_extra_args:
            input_schema = {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional arguments appended to the command",
                    }
                },
            }
        else:
            input_schema = {
                "type": "object",
                "properties": {},
            }
        tools.append(Tool(name=name, description=description, inputSchema=input_schema))
    return tools


# ---------------------------------------------------------------------------
# MCP server registration
# ---------------------------------------------------------------------------


def _create_tool_handler(
    name: str, commands: CommandsConfig, log_dir: str, log_file: str
):
    """Return an async handler function for the named command."""
    entry = commands.commands[name]

    async def _run(args: list[str]) -> str:
        global _current_command
        if _lock.locked():
            busy = _current_command
            rejection = f"Bridge is busy executing '{busy}'. Retry after it completes."
            log_request(
                LogEntry(
                    timestamp=datetime.now(timezone.utc),
                    command=name,
                    args=args,
                    exit_code=None,
                    duration_ms=0,
                    stdout=None,
                    stderr=None,
                    stdout_bytes=0,
                    stderr_bytes=0,
                    rejected=True,
                    rejection_reason=rejection,
                ),
                log_dir,
                log_file,
            )
            raise Exception(rejection)
        await _lock.acquire()
        _current_command = name
        try:
            if err := validate_args(args):
                log_request(
                    LogEntry(
                        timestamp=datetime.now(timezone.utc),
                        command=name,
                        args=args,
                        exit_code=None,
                        duration_ms=0,
                        stdout=None,
                        stderr=None,
                        stdout_bytes=0,
                        stderr_bytes=0,
                        rejected=True,
                        rejection_reason=err,
                    ),
                    log_dir,
                    log_file,
                )
                raise Exception(err)
            t0 = time.monotonic()
            try:
                result = await execute_command(name, args, commands)
                duration_ms = int((time.monotonic() - t0) * 1000)
                log_request(
                    LogEntry(
                        timestamp=datetime.now(timezone.utc),
                        command=name,
                        args=args,
                        exit_code=result.exit_code,
                        duration_ms=duration_ms,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        stdout_bytes=len(result.stdout.encode()),
                        stderr_bytes=len(result.stderr.encode()),
                        rejected=False,
                    ),
                    log_dir,
                    log_file,
                )
                return result.model_dump_json()
            except subprocess.TimeoutExpired:
                raise Exception(
                    f"Command '{name}' timed out after {commands.effective_timeout(name)}s"
                )
            except FileNotFoundError:
                raise Exception(
                    f"Command '{name}' executable not found: {entry.command[0]!r}"
                )
        finally:
            _current_command = None
            _lock.release()

    if entry.allow_extra_args:

        async def handler_with_args(args: list[str] | None = None) -> str:
            return await _run(args or [])

        handler_with_args.__name__ = name
        return handler_with_args
    else:

        async def handler_no_args() -> str:
            return await _run([])

        handler_no_args.__name__ = name
        return handler_no_args


def _register_tools(
    mcp: FastMCP, commands: CommandsConfig, log_dir: str, log_file: str
) -> None:
    """Register one MCP tool per whitelist entry."""
    for name, entry in commands.commands.items():
        description = "Execute: " + " ".join(entry.command)
        handler = _create_tool_handler(name, commands, log_dir, log_file)
        mcp.add_tool(handler, name=name, description=description)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    config = load_config()
    commands = load_commands(config.commands_file)

    cmd_summary = ", ".join(
        f"{name} (timeout: {commands.effective_timeout(name)}s)"
        for name in commands.commands
    )
    print(f"Bridge listening on {config.host}:{config.port}")
    print(f"Loaded {len(commands.commands)} commands: {cmd_summary}")

    mcp = FastMCP("bridge", host=config.host, port=config.port)
    _register_tools(mcp, commands, config.log_dir, config.log_file)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
