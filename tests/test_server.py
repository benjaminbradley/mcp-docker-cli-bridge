"""Tests for server.py — MCP Docker CLI Bridge."""
import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError


class TestCommandsConfig:
    """Tests for CommandEntry and CommandsConfig pydantic models."""

    def test_valid_config_parses_correctly(self):
        from server import CommandEntry, CommandsConfig

        config = CommandsConfig(
            default_timeout=60,
            commands={
                "run_tests": CommandEntry(
                    command=["python", "-m", "pytest"],
                    allow_extra_args=True,
                    cwd="/app",
                    timeout=120,
                )
            },
        )
        assert config.default_timeout == 60
        assert "run_tests" in config.commands
        assert config.commands["run_tests"].command == ["python", "-m", "pytest"]
        assert config.commands["run_tests"].allow_extra_args is True
        assert config.commands["run_tests"].cwd == "/app"
        assert config.commands["run_tests"].timeout == 120

    def test_missing_required_field_raises(self):
        from server import CommandEntry

        with pytest.raises(ValidationError):
            CommandEntry(allow_extra_args=True, cwd="/app")

    def test_wrong_type_for_command_raises(self):
        from server import CommandEntry

        with pytest.raises(ValidationError):
            CommandEntry(command="python", allow_extra_args=True, cwd="/app")

    def test_empty_command_array_raises(self):
        from server import CommandEntry

        with pytest.raises(ValidationError, match="non-empty"):
            CommandEntry(command=[], allow_extra_args=True, cwd="/app")

    def test_effective_timeout_uses_per_command_override(self):
        from server import CommandEntry, CommandsConfig

        config = CommandsConfig(
            default_timeout=60,
            commands={
                "fast": CommandEntry(
                    command=["echo"], allow_extra_args=False, cwd="/app", timeout=30
                )
            },
        )
        assert config.effective_timeout("fast") == 30

    def test_effective_timeout_falls_back_to_default(self):
        from server import CommandEntry, CommandsConfig

        config = CommandsConfig(
            default_timeout=60,
            commands={
                "slow": CommandEntry(
                    command=["sleep"], allow_extra_args=True, cwd="/app"
                )
            },
        )
        assert config.effective_timeout("slow") == 60

    def test_default_timeout_defaults_to_60(self):
        from server import CommandEntry, CommandsConfig

        config = CommandsConfig(
            commands={
                "cmd": CommandEntry(command=["echo"], allow_extra_args=False, cwd="/app")
            }
        )
        assert config.default_timeout == 60


class TestBuildTools:
    """Tests for build_tools() MCP tool definition generation."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(
            commands={
                name: CommandEntry(**kwargs) for name, kwargs in commands.items()
            }
        )

    def test_builds_one_tool_per_command(self):
        from server import build_tools

        config = self._make_config(
            cmd_a=dict(command=["echo"], allow_extra_args=True, cwd="/app"),
            cmd_b=dict(command=["ls"], allow_extra_args=False, cwd="/app"),
        )
        assert len(build_tools(config)) == 2

    def test_tool_name_matches_command_name(self):
        from server import build_tools

        config = self._make_config(
            run_tests=dict(command=["pytest"], allow_extra_args=True, cwd="/app"),
        )
        assert build_tools(config)[0].name == "run_tests"

    def test_allow_extra_args_true_includes_args_in_schema(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["echo"], allow_extra_args=True, cwd="/app"),
        )
        props = build_tools(config)[0].inputSchema["properties"]
        assert "args" in props
        assert props["args"]["type"] == "array"
        assert props["args"]["items"] == {"type": "string"}

    def test_allow_extra_args_false_has_empty_schema(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["ls"], allow_extra_args=False, cwd="/app"),
        )
        assert build_tools(config)[0].inputSchema["properties"] == {}

    def test_description_format(self):
        from server import build_tools

        config = self._make_config(
            run_tests=dict(
                command=["python", "-m", "pytest", "src/"],
                allow_extra_args=True,
                cwd="/app",
            ),
        )
        assert build_tools(config)[0].description == "Execute: python -m pytest src/"


class TestValidateArgs:
    """Tests for validate_args() — metacharacter blocklist and type check."""

    def test_valid_args_returns_none(self):
        from server import validate_args

        assert validate_args(["--tb=short"]) is None

    def test_empty_args_returns_none(self):
        from server import validate_args

        assert validate_args([]) is None

    def test_semicolon_rejected(self):
        from server import validate_args

        assert validate_args(["--flag; rm -rf /"]) is not None

    def test_pipe_rejected(self):
        from server import validate_args

        assert validate_args(["foo | bar"]) is not None

    def test_double_ampersand_rejected(self):
        from server import validate_args

        assert validate_args(["foo && bar"]) is not None

    def test_double_pipe_rejected(self):
        from server import validate_args

        assert validate_args(["foo || bar"]) is not None

    def test_backtick_rejected(self):
        from server import validate_args

        assert validate_args(["`cmd`"]) is not None

    def test_subshell_rejected(self):
        from server import validate_args

        assert validate_args(["$(cmd)"]) is not None

    def test_redirect_gt_rejected(self):
        from server import validate_args

        assert validate_args(["> /etc/passwd"]) is not None

    def test_redirect_lt_rejected(self):
        from server import validate_args

        assert validate_args(["< /etc/shadow"]) is not None

    def test_non_string_arg_rejected(self):
        from server import validate_args

        assert validate_args([123]) is not None


class TestExecuteCommand:
    """Tests for execute_command() — subprocess execution and result capture."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(
            commands={
                name: CommandEntry(**kwargs) for name, kwargs in commands.items()
            }
        )

    def test_captures_stdout_and_exit_code(self):
        from server import execute_command

        config = self._make_config(
            echo=dict(command=["echo", "hello"], allow_extra_args=True, cwd="/tmp")
        )
        result = execute_command("echo", ["world"], config)
        assert "hello" in result.stdout
        assert "world" in result.stdout
        assert result.exit_code == 0

    def test_captures_stderr(self):
        from server import execute_command

        config = self._make_config(
            stderr_cmd=dict(
                command=["python", "-c", "import sys; sys.stderr.write('err\\n')"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        result = execute_command("stderr_cmd", [], config)
        assert "err" in result.stderr

    def test_nonzero_exit_code_returned(self):
        from server import execute_command

        config = self._make_config(
            fail=dict(
                command=["python", "-c", "import sys; sys.exit(1)"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        result = execute_command("fail", [], config)
        assert result.exit_code == 1

    def test_timeout_raises(self):
        from server import execute_command

        config = self._make_config(
            slow=dict(command=["sleep", "5"], allow_extra_args=False, cwd="/tmp", timeout=1)
        )
        with pytest.raises(subprocess.TimeoutExpired):
            execute_command("slow", [], config)

    def test_missing_executable_raises(self):
        from server import execute_command

        config = self._make_config(
            bad=dict(command=["nonexistent_binary_xyz"], allow_extra_args=False, cwd="/tmp")
        )
        with pytest.raises(FileNotFoundError):
            execute_command("bad", [], config)


class TestToolHandlers:
    """Integration tests for tool handler functions — call handlers directly."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(
            commands={
                name: CommandEntry(**kwargs) for name, kwargs in commands.items()
            }
        )

    def _reset_lock(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = None

    @pytest.mark.asyncio
    async def test_success_path_returns_command_result_json(self):
        import server

        self._reset_lock()
        config = self._make_config(
            echo=dict(command=["echo", "hello"], allow_extra_args=True, cwd="/tmp")
        )
        handler = server._create_tool_handler("echo", config)
        result_str = await handler(args=["world"])
        data = json.loads(result_str)
        assert "stdout" in data
        assert "stderr" in data
        assert "exit_code" in data
        assert data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_nonzero_exit_code_is_not_error(self):
        import server

        self._reset_lock()
        config = self._make_config(
            fail=dict(
                command=["python", "-c", "import sys; sys.exit(1)"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        handler = server._create_tool_handler("fail", config)
        result_str = await handler()
        data = json.loads(result_str)
        assert data["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_metacharacter_args_return_is_error(self):
        import server

        self._reset_lock()
        config = self._make_config(
            echo=dict(command=["echo"], allow_extra_args=True, cwd="/tmp")
        )
        handler = server._create_tool_handler("echo", config)
        with pytest.raises(Exception, match=";"):
            await handler(args=["--flag; rm -rf /"])

    @pytest.mark.asyncio
    async def test_timeout_returns_is_error(self):
        import server

        self._reset_lock()
        config = self._make_config(
            slow=dict(command=["sleep", "5"], allow_extra_args=False, cwd="/tmp", timeout=1)
        )
        handler = server._create_tool_handler("slow", config)
        with pytest.raises(Exception, match="timed out after 1s"):
            await handler()

    @pytest.mark.asyncio
    async def test_exec_failure_returns_is_error(self):
        import server

        self._reset_lock()
        config = self._make_config(
            bad=dict(command=["nonexistent_xyz"], allow_extra_args=False, cwd="/tmp")
        )
        handler = server._create_tool_handler("bad", config)
        with pytest.raises(Exception, match="not found"):
            await handler()

    @pytest.mark.asyncio
    async def test_busy_rejection_returns_is_error(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = "other_cmd"
        await server._lock.acquire()
        try:
            config = self._make_config(
                echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp")
            )
            handler = server._create_tool_handler("echo", config)
            with pytest.raises(Exception, match="busy"):
                await handler()
        finally:
            server._lock.release()
            server._current_command = None


class TestLogRequest:
    """Tests for log_request() — JSONL file creation, appending, and field presence."""

    def _make_entry(self, **overrides):
        from server import LogEntry

        defaults = dict(
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            command="run_tests",
            args=["--tb=short"],
            exit_code=0,
            duration_ms=1234,
            stdout="ok\n",
            stderr="",
            stdout_bytes=3,
            stderr_bytes=0,
            rejected=False,
            rejection_reason=None,
        )
        return LogEntry(**{**defaults, **overrides})

    def test_creates_log_file_if_not_exists(self, tmp_path):
        from server import log_request

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        entry = self._make_entry()
        log_request(entry, str(log_dir), "bridge.jsonl")
        log_file = log_dir / "bridge.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().splitlines()
        assert len(lines) == 1

    def test_creates_log_directory_if_not_exists(self, tmp_path):
        from server import log_request

        log_dir = tmp_path / "nested" / "logs"
        entry = self._make_entry()
        log_request(entry, str(log_dir), "bridge.jsonl")
        assert (log_dir / "bridge.jsonl").exists()

    def test_appends_valid_jsonl_lines(self, tmp_path):
        from server import log_request

        log_dir = tmp_path / "logs"
        entry = self._make_entry()
        log_request(entry, str(log_dir), "bridge.jsonl")
        log_request(entry, str(log_dir), "bridge.jsonl")
        lines = (log_dir / "bridge.jsonl").read_text().splitlines()
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # each line must be valid JSON

    def test_log_entry_fields_present(self, tmp_path):
        from server import log_request

        log_dir = tmp_path / "logs"
        entry = self._make_entry()
        log_request(entry, str(log_dir), "bridge.jsonl")
        line = (log_dir / "bridge.jsonl").read_text().splitlines()[0]
        data = json.loads(line)
        expected_keys = {
            "timestamp", "command", "args", "exit_code", "duration_ms",
            "stdout", "stderr", "stdout_bytes", "stderr_bytes",
            "rejected", "rejection_reason",
        }
        assert expected_keys <= set(data.keys())
