"""MCP Docker CLI Bridge — exposes whitelisted CLI commands as MCP tools."""
import json
import os
import sys
from datetime import datetime

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


def _register_tools(mcp: FastMCP, commands: CommandsConfig) -> None:
    """Register one MCP tool per whitelist entry. Handler bodies filled in task 1.4."""
    for name, entry in commands.commands.items():
        description = "Execute: " + " ".join(entry.command)

        if entry.allow_extra_args:
            def _make_handler_with_args(cmd_name: str):
                async def handler(args: list[str] | None = None) -> str:
                    # Full implementation in task 1.4
                    return f"Not yet implemented: {cmd_name}"
                handler.__name__ = cmd_name
                return handler
            mcp.add_tool(_make_handler_with_args(name), name=name, description=description)
        else:
            def _make_handler_no_args(cmd_name: str):
                async def handler() -> str:
                    # Full implementation in task 1.4
                    return f"Not yet implemented: {cmd_name}"
                handler.__name__ = cmd_name
                return handler
            mcp.add_tool(_make_handler_no_args(name), name=name, description=description)


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

    mcp = FastMCP("bridge")
    _register_tools(mcp, commands)
    mcp.run(transport="streamable-http", host=config.host, port=config.port)


if __name__ == "__main__":
    main()
