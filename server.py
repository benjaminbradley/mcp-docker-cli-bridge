"""MCP Docker CLI Bridge — exposes allowlisted CLI commands as MCP tools."""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool
from pydantic import BaseModel, ValidationError, field_validator

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CommandEntry(BaseModel):
    """A single command in the allowlist."""

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
    warnings: list[str] | None = None
    cache_id: str | None = None
    cache_age_ms: int | None = None


@dataclass
class StreamMergeOp:
    """Merge stderr into stdout before filtering."""


@dataclass
class GrepOp:
    """Filter lines by pattern."""

    pattern: str
    regex: bool = False
    ignore_case: bool = False
    line_numbers: bool = False
    context_before: int = 0
    context_after: int = 0


@dataclass
class HeadOp:
    """Keep first N lines."""

    n: int


@dataclass
class TailOp:
    """Keep last N lines."""

    n: int


PipeOp = StreamMergeOp | GrepOp | HeadOp | TailOp


# ---------------------------------------------------------------------------
# Pipe parser
# ---------------------------------------------------------------------------


def _tokenize_pipe_segment(seg: str) -> list[str]:
    """Tokenize a single pipe segment, stripping single/double quote delimiters."""
    tokens: list[str] = []
    i = 0
    while i < len(seg):
        if seg[i].isspace():
            i += 1
        elif seg[i] in ("'", '"'):
            quote = seg[i]
            end = seg.find(quote, i + 1)
            if end == -1:
                tokens.append(seg[i + 1 :])
                break
            tokens.append(seg[i + 1 : end])
            i = end + 1
        else:
            j = i
            while j < len(seg) and not seg[j].isspace():
                j += 1
            tokens.append(seg[i:j])
            i = j
    return tokens


def _parse_grep_args(args: list[str]) -> tuple[GrepOp | None, list[str]]:
    pattern: str | None = None
    regex = False
    ignore_case = False
    line_numbers = False
    context_before = 0
    context_after = 0
    w: list[str] = []

    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("-"):
            flag_chars = tok[1:]
            j = 0
            while j < len(flag_chars):
                c = flag_chars[j]
                if c == "E":
                    regex = True
                elif c == "i":
                    ignore_case = True
                elif c == "n":
                    line_numbers = True
                elif c in ("A", "B", "C"):
                    i += 1
                    if i < len(args):
                        try:
                            val = int(args[i])
                            if c == "A":
                                context_after = val
                            elif c == "B":
                                context_before = val
                            else:
                                context_before = val
                                context_after = val
                        except ValueError:
                            w.append(f"grep: -{c} requires an integer argument")
                    break  # value flag must be last in a bundle
                else:
                    w.append(f"grep: flag -{c} not supported, ignored")
                j += 1
        else:
            pattern = tok
        i += 1

    if pattern is None:
        return None, w
    return (
        GrepOp(
            pattern=pattern,
            regex=regex,
            ignore_case=ignore_case,
            line_numbers=line_numbers,
            context_before=context_before,
            context_after=context_after,
        ),
        w,
    )


def _parse_head_args(args: list[str]) -> tuple[HeadOp | None, list[str]]:
    w: list[str] = []
    n: int | None = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "-n":
            i += 1
            if i < len(args):
                try:
                    n = int(args[i])
                except ValueError:
                    pass
        elif tok == "-c":
            i += 1  # consume the byte-count value
            w.append("head: -c (byte truncation) not supported, use `head N` for line truncation")
            return None, w
        elif tok.startswith("-"):
            w.append(f"head: flag {tok} not supported, ignored")
        else:
            try:
                n = int(tok)
            except ValueError:
                pass
        i += 1
    if n is None:
        return None, w
    return HeadOp(n), w


def _parse_tail_args(args: list[str]) -> tuple[TailOp | None, list[str]]:
    w: list[str] = []
    n: int | None = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "-n":
            i += 1
            if i < len(args):
                try:
                    n = int(args[i])
                except ValueError:
                    pass
        elif tok.startswith("-"):
            w.append(f"tail: flag {tok} not supported, ignored")
        else:
            try:
                n = int(tok)
            except ValueError:
                pass
        i += 1
    if n is None:
        return None, w
    return TailOp(n), w


def parse_pipe(pipe_str: str) -> tuple[list[PipeOp], list[str]]:
    """Parse a pipe string. Returns (ops, warnings). Raises ValueError on unknown command."""
    if not pipe_str.strip():
        return [], []

    segments = [s.strip() for s in re.split(r"\s*\|\s*", pipe_str) if s.strip()]
    ops: list[PipeOp] = []
    warnings: list[str] = []

    for seg in segments:
        if seg == "2>&1":
            ops.append(StreamMergeOp())
            continue

        tokens = _tokenize_pipe_segment(seg)
        if not tokens:
            continue

        cmd, rest = tokens[0], tokens[1:]

        if cmd == "grep":
            grep_op, w = _parse_grep_args(rest)
            if grep_op is not None:
                ops.append(grep_op)
            warnings.extend(w)
        elif cmd == "head":
            head_op, w = _parse_head_args(rest)
            if head_op is not None:
                ops.append(head_op)
            warnings.extend(w)
        elif cmd == "tail":
            tail_op, w = _parse_tail_args(rest)
            if tail_op is not None:
                ops.append(tail_op)
            warnings.extend(w)
        else:
            raise ValueError(f"Unsupported pipe command: {cmd!r}")

    return ops, warnings


# ---------------------------------------------------------------------------
# Pipe executor
# ---------------------------------------------------------------------------


def _grep_sync(
    lines: list[str],
    pattern: str,
    regex: bool,
    ignore_case: bool,
    line_numbers: bool,
    context_before: int,
    context_after: int,
) -> list[str]:
    """Synchronous grep helper. Called via asyncio.to_thread for regex mode."""
    flags = re.IGNORECASE if ignore_case else 0
    matched_indices: list[int] = []
    for idx, line in enumerate(lines):
        if regex:
            if re.search(pattern, line, flags):
                matched_indices.append(idx)
        else:
            compare = line.lower() if ignore_case else line
            pat = pattern.lower() if ignore_case else pattern
            if pat in compare:
                matched_indices.append(idx)

    if not matched_indices:
        return []

    if context_before > 0 or context_after > 0:
        included: set[int] = set()
        for idx in matched_indices:
            for i in range(max(0, idx - context_before), min(len(lines), idx + context_after + 1)):
                included.add(i)
        result_indices = sorted(included)
    else:
        result_indices = matched_indices

    if line_numbers:
        return [f"{idx + 1}:{lines[idx]}" for idx in result_indices]
    return [lines[idx] for idx in result_indices]


async def _apply_grep(op: GrepOp, stdout: str) -> tuple[str, list[str]]:
    """Apply a GrepOp to stdout. Returns (new_stdout, additional_warnings)."""
    lines = stdout.splitlines()
    w: list[str] = []

    if op.regex:
        try:
            result_lines = await asyncio.wait_for(
                asyncio.to_thread(
                    _grep_sync,
                    lines,
                    op.pattern,
                    op.regex,
                    op.ignore_case,
                    op.line_numbers,
                    op.context_before,
                    op.context_after,
                ),
                timeout=1.0,
            )
        except TimeoutError:
            w.append("grep -E: regex timed out, returning unfiltered output")
            result_lines = lines
    else:
        result_lines = _grep_sync(
            lines,
            op.pattern,
            op.regex,
            op.ignore_case,
            op.line_numbers,
            op.context_before,
            op.context_after,
        )

    if not result_lines:
        return "", w
    new_stdout = "\n".join(result_lines)
    if stdout.endswith("\n"):
        new_stdout += "\n"
    return new_stdout, w


async def apply_pipe(ops: list[PipeOp], stdout: str, stderr: str) -> tuple[str, str, list[str]]:
    """Apply ops in order. Returns (stdout, stderr, additional_warnings)."""
    w: list[str] = []
    for op in ops:
        if isinstance(op, StreamMergeOp):
            stdout = stdout + stderr
            stderr = ""
        elif isinstance(op, GrepOp):
            stdout, extra_w = await _apply_grep(op, stdout)
            w.extend(extra_w)
        elif isinstance(op, HeadOp):
            lines = stdout.splitlines()
            result_lines = lines[: op.n]
            stdout = ("\n".join(result_lines) + "\n") if result_lines else ""
        elif isinstance(op, TailOp):
            lines = stdout.splitlines()
            result_lines = lines[-op.n :] if op.n > 0 else []
            stdout = ("\n".join(result_lines) + "\n") if result_lines else ""
    return stdout, stderr, w


# ---------------------------------------------------------------------------
# Cache subsystem
# ---------------------------------------------------------------------------

_CACHE_DIR = "/tmp/bridge_cache"
_CACHE_TTL_SECONDS = 86400  # 24 hours
_UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@dataclass
class CacheEntry:
    stdout: str
    stderr: str
    exit_code: int
    created_at: float


def _validate_cache_id(cache_id: str) -> None:
    """Raise ValueError if cache_id is not a valid UUID4 string."""
    if not _UUID4_RE.fullmatch(cache_id):
        raise ValueError(f"Invalid cache_id format: {cache_id!r}")


def save_cache(stdout: str, stderr: str, exit_code: int) -> str:
    """Write entry to cache dir, return UUID string."""
    cache_id = str(uuid.uuid4())
    cache_dir = Path(_CACHE_DIR)
    cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = cache_dir / cache_id
    payload = json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "created_at": time.time()})
    path.write_text(payload)
    os.chmod(path, 0o600)
    return cache_id


def load_cache(cache_id: str) -> CacheEntry:
    """Load cache entry by ID. Raises ValueError, FileNotFoundError, or RuntimeError."""
    _validate_cache_id(cache_id)
    path = Path(_CACHE_DIR) / cache_id
    if not path.exists():
        raise FileNotFoundError(f"Cache entry not found: {cache_id}")
    age = time.time() - path.stat().st_mtime
    if age > _CACHE_TTL_SECONDS:
        raise RuntimeError(f"Cache entry expired (age={age:.0f}s): {cache_id}")
    data = json.loads(path.read_text())
    return CacheEntry(
        stdout=data["stdout"],
        stderr=data["stderr"],
        exit_code=data["exit_code"],
        created_at=data["created_at"],
    )


def cleanup_stale_cache() -> int:
    """Delete cache files older than TTL. Returns count of deleted files."""
    cache_dir = Path(_CACHE_DIR)
    if not cache_dir.exists():
        return 0
    count = 0
    now = time.time()
    for p in cache_dir.glob("*"):
        if now - p.stat().st_mtime > _CACHE_TTL_SECONDS:
            p.unlink()
            count += 1
    return count


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
        print(
            f"Error: commands file not found: {path}\n  Set BRIDGE_COMMANDS_FILE to override the default path",
            file=sys.stderr,
        )
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: {path}:{e.lineno}:{e.colno}: {e.msg}", file=sys.stderr)
        sys.exit(1)

    try:
        return CommandsConfig(**data)
    except ValidationError as e:
        lines = [f"Error: invalid commands config in {path}:"]
        for err in e.errors():
            loc = ".".join(str(part) for part in err["loc"])
            lines.append(f"  {loc}: {err['msg']}")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: invalid commands config in {path}:\n{e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument validator
# ---------------------------------------------------------------------------

BLOCKED_SEQUENCES = [";", "&&", "||", "|", "`", "$(", ">", "<"]


def validate_args(args: list[str]) -> str | None:
    """Return None if args are valid, or an error message string if invalid."""
    for arg in args:
        if not isinstance(arg, str):
            return f"Argument must be a string, got {type(arg).__name__}: {arg!r}"
        for seq in BLOCKED_SEQUENCES:
            if seq in arg:
                return f"Argument contains disallowed sequence {seq!r} in: {arg!r}"
    return None


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


async def execute_command(name: str, args: list[str], config: CommandsConfig) -> CommandResult:
    """Run the allowlisted command in a thread pool and return its result. Raises on timeout or missing executable."""
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
    return CommandResult(stdout=result.stdout, stderr=result.stderr, exit_code=result.returncode)


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


def _filter_schema_properties() -> dict[str, dict[str, object]]:
    return {
        "pipe": {
            "type": "string",
            "description": (
                "Filter output: 2>&1 | grep [-EinABC] 'pat' | head/tail N. "
                "Example: \"2>&1 | grep -iA 5 'FAILED' | tail 100\""
            ),
        },
        "cache": {
            "type": "boolean",
            "description": "Cache full output; returns cache_id for reuse",
        },
        "cache_id": {
            "type": "string",
            "description": "UUID from prior result — skips re-execution, applies pipe to cached output",
        },
    }


def build_tools(config: CommandsConfig) -> list[Tool]:
    """Generate MCP Tool definitions from CommandsConfig."""
    tools = []
    filter_props = _filter_schema_properties()
    for name, entry in config.commands.items():
        description = "Execute: " + " ".join(entry.command)
        if entry.allow_extra_args:
            properties = {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional arguments appended to the command",
                },
                **filter_props,
            }
        else:
            properties = {**filter_props}
        tools.append(
            Tool(
                name=name,
                description=description,
                inputSchema={"type": "object", "properties": properties},
            )
        )
    return tools


# ---------------------------------------------------------------------------
# MCP server registration
# ---------------------------------------------------------------------------


def _create_tool_handler(
    name: str, commands: CommandsConfig, log_dir: str, log_file: str
) -> Callable[..., Awaitable[str]]:
    """Return an async handler function for the named command."""
    entry = commands.commands[name]

    async def _run_from_cache(cache_id: str, pipe: str | None) -> str:
        """Load cached result and optionally apply pipe filter."""
        try:
            cached = load_cache(cache_id)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            raise Exception(str(e)) from e
        cache_age_ms = int((time.time() - cached.created_at) * 1000)
        all_warnings: list[str] = []
        if pipe:
            try:
                ops, pipe_warnings = parse_pipe(pipe)
            except ValueError as e:
                raise Exception(str(e)) from e
            filtered_stdout, filtered_stderr, apply_warnings = await apply_pipe(ops, cached.stdout, cached.stderr)
            all_warnings = pipe_warnings + apply_warnings
        else:
            filtered_stdout, filtered_stderr = cached.stdout, cached.stderr
        result = CommandResult(
            stdout=filtered_stdout,
            stderr=filtered_stderr,
            exit_code=cached.exit_code,
            warnings=all_warnings or None,
            cache_id=cache_id,
            cache_age_ms=cache_age_ms,
        )
        return result.model_dump_json(exclude_none=True)

    async def _run_execute(args: list[str], pipe: str | None, cache: bool) -> str:
        """Execute command, optionally pipe-filter output, optionally cache result."""
        global _current_command
        if _lock.locked():
            busy = _current_command
            rejection = f"Bridge is busy executing '{busy}'. Retry after it completes."
            log_request(
                LogEntry(
                    timestamp=datetime.now(UTC),
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
                        timestamp=datetime.now(UTC),
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
                raw = await execute_command(name, args, commands)
                duration_ms = int((time.monotonic() - t0) * 1000)
            except subprocess.TimeoutExpired as e:
                raise Exception(f"Command '{name}' timed out after {commands.effective_timeout(name)}s") from e
            except FileNotFoundError as e:
                raise Exception(
                    f"Command '{name}' executable not found: {entry.command[0]!r} "
                    f"(cwd={entry.cwd!r}) — check the 'command' field in commands.json"
                ) from e

            # Pipe filter (applied to raw output; log records pre-filter bytes)
            all_warnings: list[str] = []
            if pipe:
                try:
                    ops, pipe_warnings = parse_pipe(pipe)
                except ValueError as e:
                    raise Exception(str(e)) from e
                filtered_stdout, filtered_stderr, apply_warnings = await apply_pipe(ops, raw.stdout, raw.stderr)
                all_warnings = pipe_warnings + apply_warnings
            else:
                filtered_stdout, filtered_stderr = raw.stdout, raw.stderr

            # Cache full pre-filter output
            saved_cache_id: str | None = None
            if cache:
                saved_cache_id = save_cache(raw.stdout, raw.stderr, raw.exit_code)

            log_request(
                LogEntry(
                    timestamp=datetime.now(UTC),
                    command=name,
                    args=args,
                    exit_code=raw.exit_code,
                    duration_ms=duration_ms,
                    stdout=raw.stdout,
                    stderr=raw.stderr,
                    stdout_bytes=len(raw.stdout.encode()),
                    stderr_bytes=len(raw.stderr.encode()),
                    rejected=False,
                ),
                log_dir,
                log_file,
            )
            result = CommandResult(
                stdout=filtered_stdout,
                stderr=filtered_stderr,
                exit_code=raw.exit_code,
                warnings=all_warnings or None,
                cache_id=saved_cache_id,
            )
            return result.model_dump_json(exclude_none=True)
        finally:
            _current_command = None
            _lock.release()

    if entry.allow_extra_args:

        async def handler_with_args(
            args: list[str] | None = None,
            pipe: str | None = None,
            cache: bool = False,
            cache_id: str | None = None,
        ) -> str:
            if cache_id is not None:
                return await _run_from_cache(cache_id, pipe)
            return await _run_execute(args or [], pipe, cache)

        handler_with_args.__name__ = name
        return handler_with_args
    else:

        async def handler_no_args(
            pipe: str | None = None,
            cache: bool = False,
            cache_id: str | None = None,
        ) -> str:
            if cache_id is not None:
                return await _run_from_cache(cache_id, pipe)
            return await _run_execute([], pipe, cache)

        handler_no_args.__name__ = name
        return handler_no_args


def _register_tools(mcp: FastMCP, commands: CommandsConfig, log_dir: str, log_file: str) -> None:
    """Register one MCP tool per allowlist entry."""
    for name, entry in commands.commands.items():
        description = "Execute: " + " ".join(entry.command)
        handler = _create_tool_handler(name, commands, log_dir, log_file)
        mcp.add_tool(handler, name=name, description=description)


# ---------------------------------------------------------------------------
# Background cache cleanup
# ---------------------------------------------------------------------------


async def _cache_cleanup_loop(interval_seconds: int = 3600) -> None:
    """Run cleanup_stale_cache() every interval_seconds. Never raises."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            cleanup_stale_cache()
        except Exception:
            pass


@asynccontextmanager
async def _cache_cleanup_lifespan(server: object) -> AsyncIterator[None]:
    """FastMCP lifespan: start cache cleanup loop when the server starts."""
    task = asyncio.create_task(_cache_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    config = load_config()
    commands = load_commands(config.commands_file)

    cmd_summary = ", ".join(f"{name} (timeout: {commands.effective_timeout(name)}s)" for name in commands.commands)
    print(f"Bridge listening on {config.host}:{config.port}")
    print(f"Loaded {len(commands.commands)} commands: {cmd_summary}")

    mcp = FastMCP("bridge", host=config.host, port=config.port, lifespan=_cache_cleanup_lifespan)
    _register_tools(mcp, commands, config.log_dir, config.log_file)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
