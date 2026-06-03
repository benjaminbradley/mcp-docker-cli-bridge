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
            commands={"fast": CommandEntry(command=["echo"], allow_extra_args=False, cwd="/app", timeout=30)},
        )
        assert config.effective_timeout("fast") == 30

    def test_effective_timeout_falls_back_to_default(self):
        from server import CommandEntry, CommandsConfig

        config = CommandsConfig(
            default_timeout=60,
            commands={"slow": CommandEntry(command=["sleep"], allow_extra_args=True, cwd="/app")},
        )
        assert config.effective_timeout("slow") == 60

    def test_default_timeout_defaults_to_60(self):
        from server import CommandEntry, CommandsConfig

        config = CommandsConfig(commands={"cmd": CommandEntry(command=["echo"], allow_extra_args=False, cwd="/app")})
        assert config.default_timeout == 60


class TestCommandResult:
    """Tests for CommandResult pydantic model new fields (Phase 4)."""

    def test_new_fields_default_to_none(self):
        from server import CommandResult

        r = CommandResult(stdout="", stderr="", exit_code=0)
        assert r.warnings is None
        assert r.cache_id is None
        assert r.cache_age_ms is None

    def test_warnings_field_serializes(self):
        from server import CommandResult

        r = CommandResult(stdout="", stderr="", exit_code=0, warnings=["unsupported flag -i ignored"])
        data = json.loads(r.model_dump_json(exclude_none=True))
        assert data["warnings"] == ["unsupported flag -i ignored"]

    def test_cache_fields_serialize(self):
        from server import CommandResult

        r = CommandResult(stdout="", stderr="", exit_code=0, cache_id="abc", cache_age_ms=5000)
        data = json.loads(r.model_dump_json(exclude_none=True))
        assert data["cache_id"] == "abc"
        assert data["cache_age_ms"] == 5000

    def test_exclude_none_omits_missing_fields(self):
        from server import CommandResult

        r = CommandResult(stdout="a", stderr="b", exit_code=0)
        data = json.loads(r.model_dump_json(exclude_none=True))
        assert "warnings" not in data
        assert "cache_id" not in data
        assert "cache_age_ms" not in data


class TestParsePipe:
    """Tests for parse_pipe() — pipe string tokenisation and PipeOp construction."""

    def test_empty_string_returns_no_ops(self):
        from server import parse_pipe

        ops, warnings = parse_pipe("")
        assert ops == []
        assert warnings == []

    def test_stream_merge(self):
        from server import StreamMergeOp, parse_pipe

        ops, warnings = parse_pipe("2>&1")
        assert ops == [StreamMergeOp()]
        assert warnings == []

    def test_grep_literal(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe('grep "FAIL"')
        assert ops == [GrepOp("FAIL", regex=False)]
        assert warnings == []

    def test_grep_regex(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -E 'ERR.*'")
        assert ops == [GrepOp("ERR.*", regex=True)]
        assert warnings == []

    def test_grep_single_quotes(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep 'foo'")
        assert ops == [GrepOp("foo", regex=False)]
        assert warnings == []

    def test_head_bare(self):
        from server import HeadOp, parse_pipe

        ops, warnings = parse_pipe("head 20")
        assert ops == [HeadOp(20)]
        assert warnings == []

    def test_head_n_flag(self):
        from server import HeadOp, parse_pipe

        ops, warnings = parse_pipe("head -n 20")
        assert ops == [HeadOp(20)]
        assert warnings == []

    def test_tail_bare(self):
        from server import TailOp, parse_pipe

        ops, warnings = parse_pipe("tail 5")
        assert ops == [TailOp(5)]
        assert warnings == []

    def test_tail_n_flag(self):
        from server import TailOp, parse_pipe

        ops, warnings = parse_pipe("tail -n 5")
        assert ops == [TailOp(5)]
        assert warnings == []

    def test_chained_pipe(self):
        from server import GrepOp, HeadOp, StreamMergeOp, parse_pipe

        ops, warnings = parse_pipe("2>&1 | grep 'ERR' | head 10")
        assert ops == [StreamMergeOp(), GrepOp("ERR", False), HeadOp(10)]
        assert warnings == []

    def test_unknown_command_raises(self):
        from server import parse_pipe

        with pytest.raises(ValueError):
            parse_pipe("awk '{print}'")

    def test_grep_case_insensitive(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -i 'pat'")
        assert ops == [GrepOp("pat", ignore_case=True)]
        assert warnings == []

    def test_grep_line_numbers(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -n 'pat'")
        assert ops == [GrepOp("pat", line_numbers=True)]
        assert warnings == []

    def test_grep_context_after(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -A 3 'pat'")
        assert ops == [GrepOp("pat", context_after=3)]
        assert warnings == []

    def test_grep_context_before(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -B 2 'pat'")
        assert ops == [GrepOp("pat", context_before=2)]
        assert warnings == []

    def test_grep_context_symmetric(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -C 5 'pat'")
        assert ops == [GrepOp("pat", context_before=5, context_after=5)]
        assert warnings == []

    def test_grep_flag_bundling_iE(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -iE 'pat'")
        assert len(ops) == 1
        assert isinstance(ops[0], GrepOp)
        assert ops[0].pattern == "pat"
        assert ops[0].regex is True
        assert ops[0].ignore_case is True
        assert warnings == []

    def test_grep_flag_bundling_in(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -in 'pat'")
        assert len(ops) == 1
        assert isinstance(ops[0], GrepOp)
        assert ops[0].pattern == "pat"
        assert ops[0].ignore_case is True
        assert ops[0].line_numbers is True
        assert warnings == []

    def test_grep_flag_bundling_with_context(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -iA 3 'pat'")
        assert len(ops) == 1
        assert isinstance(ops[0], GrepOp)
        assert ops[0].pattern == "pat"
        assert ops[0].ignore_case is True
        assert ops[0].context_after == 3
        assert warnings == []

    def test_grep_unknown_flag_warns(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -v 'pat'")
        assert len(ops) == 1
        assert isinstance(ops[0], GrepOp)
        assert ops[0].pattern == "pat"
        assert len(warnings) == 1
        assert "-v" in warnings[0]

    def test_head_c_flag_warns_and_skips(self):
        from server import parse_pipe

        ops, warnings = parse_pipe("head -c 100")
        assert ops == []
        assert len(warnings) == 1
        assert "-c" in warnings[0]

    def test_grep_fully_unknown_flag_warns(self):
        from server import GrepOp, parse_pipe

        ops, warnings = parse_pipe("grep -Ei -v 'pat'")
        assert len(ops) == 1
        assert isinstance(ops[0], GrepOp)
        assert ops[0].regex is True
        assert len(warnings) >= 1
        assert any("-v" in w for w in warnings)


class TestApplyPipe:
    """Tests for apply_pipe() — per-operation filtering logic."""

    @pytest.mark.asyncio
    async def test_no_ops_returns_unchanged(self):
        from server import apply_pipe

        stdout, stderr, w = await apply_pipe([], "hello\nworld\n", "err\n")
        assert stdout == "hello\nworld\n"
        assert stderr == "err\n"
        assert w == []

    @pytest.mark.asyncio
    async def test_stream_merge(self):
        from server import StreamMergeOp, apply_pipe

        stdout, stderr, w = await apply_pipe([StreamMergeOp()], "out\n", "err\n")
        assert stdout == "out\nerr\n"
        assert stderr == ""
        assert w == []

    @pytest.mark.asyncio
    async def test_stream_merge_ordering(self):
        from server import GrepOp, StreamMergeOp, apply_pipe

        stdout, stderr, w = await apply_pipe([StreamMergeOp(), GrepOp("err")], "out\n", "err\n")
        assert "err" in stdout
        assert stderr == ""

    @pytest.mark.asyncio
    async def test_grep_literal_filters_lines(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe([GrepOp("PASS")], "PASS: test1\nFAIL: test2\nPASS: test3\n", "")
        assert "PASS: test1" in stdout
        assert "FAIL: test2" not in stdout
        assert "PASS: test3" in stdout
        assert w == []

    @pytest.mark.asyncio
    async def test_grep_literal_empty_match(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe([GrepOp("NOMATCH")], "line1\nline2\n", "")
        assert stdout == ""
        assert w == []

    @pytest.mark.asyncio
    async def test_grep_regex_filters_lines(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe([GrepOp("ERR.*", regex=True)], "ERROR: bad\ninfo: ok\nERROR: worse\n", "")
        assert "ERROR: bad" in stdout
        assert "info: ok" not in stdout
        assert w == []

    @pytest.mark.asyncio
    async def test_grep_regex_timeout_returns_unfiltered_with_warning(self):
        import asyncio
        from unittest.mock import patch

        from server import GrepOp, apply_pipe

        async def _force_timeout(coro, *args, **kwargs):
            coro.close()  # prevent unawaited coroutine warning
            raise asyncio.TimeoutError()

        with patch("asyncio.wait_for", _force_timeout):
            lines = "line1\nline2\nline3\n"
            stdout, stderr, w = await apply_pipe([GrepOp("pat", regex=True)], lines, "")
            assert stdout == lines  # returned unfiltered
            assert any("timed out" in warning for warning in w)

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe([GrepOp("error", ignore_case=True)], "Error here\nok\nERROR bad\n", "")
        assert "Error here" in stdout
        assert "ERROR bad" in stdout
        assert "ok" not in stdout

    @pytest.mark.asyncio
    async def test_grep_case_insensitive_regex(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe(
            [GrepOp("err.*", regex=True, ignore_case=True)],
            "Error here\nok\nERROR bad\n",
            "",
        )
        assert "Error here" in stdout
        assert "ERROR bad" in stdout
        assert "ok" not in stdout

    @pytest.mark.asyncio
    async def test_grep_line_numbers(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe([GrepOp("FAIL", line_numbers=True)], "ok\nFAIL test\nok\n", "")
        assert "2:FAIL test" in stdout

    @pytest.mark.asyncio
    async def test_grep_context_after(self):
        from server import GrepOp, apply_pipe

        lines = "line1\nFAIL\nline3\nline4\n"
        stdout, stderr, w = await apply_pipe([GrepOp("FAIL", context_after=2)], lines, "")
        assert "FAIL" in stdout
        assert "line3" in stdout
        assert "line4" in stdout
        assert "line1" not in stdout

    @pytest.mark.asyncio
    async def test_grep_context_before(self):
        from server import GrepOp, apply_pipe

        lines = "line1\nline2\nFAIL\nline4\n"
        stdout, stderr, w = await apply_pipe([GrepOp("FAIL", context_before=2)], lines, "")
        assert "FAIL" in stdout
        assert "line1" in stdout
        assert "line2" in stdout
        assert "line4" not in stdout

    @pytest.mark.asyncio
    async def test_grep_context_symmetric(self):
        from server import GrepOp, apply_pipe

        lines = "before\nFAIL\nafter\n"
        stdout, stderr, w = await apply_pipe([GrepOp("FAIL", context_before=1, context_after=1)], lines, "")
        assert "before" in stdout
        assert "FAIL" in stdout
        assert "after" in stdout

    @pytest.mark.asyncio
    async def test_grep_context_overlapping_matches(self):
        from server import GrepOp, apply_pipe

        lines = "FAIL1\nshared\nFAIL2\n"
        stdout, stderr, w = await apply_pipe([GrepOp("FAIL", context_after=1)], lines, "")
        result_lines = [l for l in stdout.splitlines() if l]
        # "shared" should appear only once even though it's after both matches
        assert result_lines.count("shared") == 1

    @pytest.mark.asyncio
    async def test_grep_context_at_boundaries(self):
        from server import GrepOp, apply_pipe

        lines = "FAIL\nline2\n"
        # Match on first line with context_before=2 must not error
        stdout, stderr, w = await apply_pipe([GrepOp("FAIL", context_before=2)], lines, "")
        assert "FAIL" in stdout

        lines2 = "line1\nFAIL\n"
        # Match on last line with context_after=2 must not error
        stdout2, _, _ = await apply_pipe([GrepOp("FAIL", context_after=2)], lines2, "")
        assert "FAIL" in stdout2

    @pytest.mark.asyncio
    async def test_head_n_lines(self):
        from server import HeadOp, apply_pipe

        lines = "\n".join(str(i) for i in range(10)) + "\n"
        stdout, stderr, w = await apply_pipe([HeadOp(3)], lines, "")
        result = stdout.splitlines()
        assert result == ["0", "1", "2"]

    @pytest.mark.asyncio
    async def test_tail_n_lines(self):
        from server import TailOp, apply_pipe

        lines = "\n".join(str(i) for i in range(10)) + "\n"
        stdout, stderr, w = await apply_pipe([TailOp(3)], lines, "")
        result = stdout.splitlines()
        assert result == ["7", "8", "9"]

    @pytest.mark.asyncio
    async def test_head_larger_than_input(self):
        from server import HeadOp, apply_pipe

        lines = "a\nb\nc\nd\ne\n"
        stdout, stderr, w = await apply_pipe([HeadOp(100)], lines, "")
        assert stdout.splitlines() == ["a", "b", "c", "d", "e"]

    @pytest.mark.asyncio
    async def test_grep_applies_to_stdout_only_when_not_merged(self):
        from server import GrepOp, apply_pipe

        stdout, stderr, w = await apply_pipe([GrepOp("PASS")], "PASS: ok\n", "FAIL: stderr\n")
        assert "PASS: ok" in stdout
        assert stderr == "FAIL: stderr\n"

    @pytest.mark.asyncio
    async def test_chained_merge_grep_head(self):
        from server import GrepOp, HeadOp, StreamMergeOp, apply_pipe

        stdout, stderr, w = await apply_pipe(
            [StreamMergeOp(), GrepOp("E"), HeadOp(2)],
            "Error1\nInfo\nError2\nError3\n",
            "Err4\n",
        )
        result_lines = stdout.splitlines()
        assert len(result_lines) == 2
        assert all("E" in l for l in result_lines)
        assert stderr == ""


class TestCacheSubsystem:
    """Tests for save_cache(), load_cache(), cleanup_stale_cache()."""

    def test_save_returns_uuid_string(self, tmp_path, monkeypatch):
        import re

        from server import save_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        result = save_cache("out", "err", 0)
        assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", result)

    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        from server import load_cache, save_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = save_cache("my stdout", "my stderr", 42)
        entry = load_cache(cache_id)
        assert entry.stdout == "my stdout"
        assert entry.stderr == "my stderr"
        assert entry.exit_code == 42

    def test_load_invalid_uuid_raises_value_error(self, tmp_path, monkeypatch):
        from server import load_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        with pytest.raises(ValueError):
            load_cache("../../etc/passwd")

    def test_load_invalid_uuid_no_traversal(self, tmp_path, monkeypatch):
        from server import load_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        with pytest.raises(ValueError):
            load_cache("../secret")

    def test_load_missing_raises_file_not_found(self, tmp_path, monkeypatch):
        from server import load_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        with pytest.raises(FileNotFoundError):
            load_cache("00000000-0000-4000-8000-000000000000")

    def test_load_expired_raises_runtime_error(self, tmp_path, monkeypatch):
        import os
        import time

        from server import load_cache, save_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = save_cache("data", "", 0)
        # Backdate mtime by 25 hours
        cache_path = tmp_path / "cache" / cache_id
        old_time = time.time() - (25 * 3600)
        os.utime(str(cache_path), (old_time, old_time))
        with pytest.raises(RuntimeError, match="expired"):
            load_cache(cache_id)

    def test_cleanup_removes_old_files(self, tmp_path, monkeypatch):
        import os
        import time

        from server import cleanup_stale_cache, save_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        old_id = save_cache("old", "", 0)
        fresh_id = save_cache("fresh", "", 0)
        # Backdate old file by 25 hours
        old_path = tmp_path / "cache" / old_id
        old_time = time.time() - (25 * 3600)
        os.utime(str(old_path), (old_time, old_time))
        count = cleanup_stale_cache()
        assert count == 1
        assert not old_path.exists()
        assert (tmp_path / "cache" / fresh_id).exists()

    def test_cleanup_returns_zero_when_nothing_stale(self, tmp_path, monkeypatch):
        from server import cleanup_stale_cache, save_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        save_cache("data", "", 0)
        assert cleanup_stale_cache() == 0

    def test_cache_file_permissions(self, tmp_path, monkeypatch):
        import os
        import stat

        from server import save_cache

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = save_cache("data", "", 0)
        path = tmp_path / "cache" / cache_id
        mode = stat.S_IMODE(os.stat(str(path)).st_mode)
        assert mode == 0o600


class TestBuildToolsPhase4:
    """Tests for build_tools() schema additions — pipe, cache, cache_id params."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

    def test_pipe_param_in_schema(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"),
        )
        for tool in build_tools(config):
            assert "pipe" in tool.inputSchema["properties"]
            assert tool.inputSchema["properties"]["pipe"]["type"] == "string"

    def test_cache_param_in_schema(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"),
        )
        for tool in build_tools(config):
            assert "cache" in tool.inputSchema["properties"]
            assert tool.inputSchema["properties"]["cache"]["type"] == "boolean"

    def test_cache_id_param_in_schema(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"),
        )
        for tool in build_tools(config):
            assert "cache_id" in tool.inputSchema["properties"]
            assert tool.inputSchema["properties"]["cache_id"]["type"] == "string"

    def test_existing_schema_structure_unchanged_extra_args(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"),
        )
        props = build_tools(config)[0].inputSchema["properties"]
        assert "args" in props

    def test_existing_schema_structure_unchanged_no_extra_args(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["ls"], allow_extra_args=False, cwd="/tmp"),
        )
        props = build_tools(config)[0].inputSchema["properties"]
        assert "args" not in props

    def test_new_schema_params_present_for_no_extra_args_tool(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["ls"], allow_extra_args=False, cwd="/tmp"),
        )
        props = build_tools(config)[0].inputSchema["properties"]
        assert "pipe" in props
        assert "cache" in props
        assert "cache_id" in props


class TestToolHandlersPhase4:
    """Tests that handler functions accept new pipe/cache/cache_id params."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

    def _reset_lock(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = None

    @pytest.mark.asyncio
    async def test_handler_accepts_pipe_param(self):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo", "hello"], allow_extra_args=True, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, "/tmp", "test.jsonl")
        result = await handler(args=[], pipe="head 1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_handler_accepts_cache_param(self, tmp_path, monkeypatch):
        import server

        self._reset_lock()
        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        config = self._make_config(echo=dict(command=["echo", "hello"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, "/tmp", "test.jsonl")
        result = await handler(cache=True)
        data = json.loads(result)
        assert "cache_id" in data

    @pytest.mark.asyncio
    async def test_handler_accepts_cache_id_param(self, tmp_path, monkeypatch):
        import server

        self._reset_lock()
        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = server.save_cache("cached stdout\n", "", 0)
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, "/tmp", "test.jsonl")
        result = await handler(cache_id=cache_id)
        data = json.loads(result)
        assert data["stdout"] == "cached stdout\n"


class TestPipeIntegration:
    """End-to-end integration tests: pipe filtering, cache roundtrip, warnings."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

    def _reset_lock(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = None

    @pytest.mark.asyncio
    async def test_pipe_head_truncates_output(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(
            py=dict(
                command=["python", "-c", "print('\\n'.join(str(i) for i in range(10)))"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        handler = server._create_tool_handler("py", config, str(tmp_path), "t.jsonl")
        result = await handler(pipe="head 2")
        data = json.loads(result)
        assert data["stdout"].splitlines() == ["0", "1"]

    @pytest.mark.asyncio
    async def test_pipe_grep_filters_lines(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(
            py=dict(
                command=["python", "-c", "print('PASS\\nFAIL\\nPASS')"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        handler = server._create_tool_handler("py", config, str(tmp_path), "t.jsonl")
        result = await handler(pipe="grep 'PASS'")
        data = json.loads(result)
        assert "FAIL" not in data["stdout"]
        assert data["stdout"].count("PASS") == 2

    @pytest.mark.asyncio
    async def test_pipe_stream_merge(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(
            py=dict(
                command=[
                    "python",
                    "-c",
                    "import sys; print('out'); sys.stderr.write('err\\n')",
                ],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        handler = server._create_tool_handler("py", config, str(tmp_path), "t.jsonl")
        result = await handler(pipe="2>&1")
        data = json.loads(result)
        assert "out" in data["stdout"]
        assert "err" in data["stdout"]
        assert data["stderr"] == ""

    @pytest.mark.asyncio
    async def test_pipe_warnings_in_result(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(
            py=dict(
                command=["python", "-c", "print('hello')"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        handler = server._create_tool_handler("py", config, str(tmp_path), "t.jsonl")
        # -v is unsupported → warning
        result = await handler(pipe="grep -v 'x'")
        data = json.loads(result)
        assert "warnings" in data
        assert any("-v" in w for w in data["warnings"])

    @pytest.mark.asyncio
    async def test_pipe_invalid_command_raises(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(py=dict(command=["python", "-c", "pass"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("py", config, str(tmp_path), "t.jsonl")
        with pytest.raises(Exception, match="Unsupported"):
            await handler(pipe="awk '{print}'")

    @pytest.mark.asyncio
    async def test_cache_true_returns_cache_id(self, tmp_path, monkeypatch):
        import re

        import server

        self._reset_lock()
        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        config = self._make_config(py=dict(command=["python", "-c", "print('hi')"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("py", config, str(tmp_path), "t.jsonl")
        result = await handler(cache=True)
        data = json.loads(result)
        assert "cache_id" in data
        assert re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            data["cache_id"],
        )

    @pytest.mark.asyncio
    async def test_cache_id_skips_execution(self, tmp_path, monkeypatch):
        import server

        self._reset_lock()
        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = server.save_cache("line1\nline2\nline3\n", "", 0)
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "t.jsonl")
        result = await handler(cache_id=cache_id, pipe="head 1")
        data = json.loads(result)
        assert data["stdout"].strip() == "line1"
        assert "cache_age_ms" in data
        assert not server._lock.locked()

    @pytest.mark.asyncio
    async def test_cache_id_no_pipe_returns_raw(self, tmp_path, monkeypatch):
        import server

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = server.save_cache("full content\n", "", 0)
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "t.jsonl")
        result = await handler(cache_id=cache_id)
        data = json.loads(result)
        assert data["stdout"] == "full content\n"

    @pytest.mark.asyncio
    async def test_cache_id_expired_returns_error(self, tmp_path, monkeypatch):
        import os
        import time

        import server

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        cache_id = server.save_cache("data", "", 0)
        old_time = time.time() - (25 * 3600)
        os.utime(str(tmp_path / "cache" / cache_id), (old_time, old_time))
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "t.jsonl")
        with pytest.raises(Exception, match="expired"):
            await handler(cache_id=cache_id)

    @pytest.mark.asyncio
    async def test_cache_id_invalid_format_returns_error(self, tmp_path, monkeypatch):
        import server

        monkeypatch.setattr("server._CACHE_DIR", str(tmp_path / "cache"))
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "t.jsonl")
        with pytest.raises(Exception, match="Invalid cache_id"):
            await handler(cache_id="../../etc")

    @pytest.mark.asyncio
    async def test_normal_path_unaffected(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo", "hello"], allow_extra_args=True, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "t.jsonl")
        result = await handler(args=[])
        data = json.loads(result)
        assert "stdout" in data
        assert "stderr" in data
        assert "exit_code" in data
        assert "warnings" not in data
        assert "cache_id" not in data


class TestCacheCleanupLoop:
    """Tests for _cache_cleanup_loop() and its wiring into main()."""

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_cleanup(self):
        from unittest.mock import patch

        from server import _cache_cleanup_loop

        call_count = 0

        def fake_cleanup() -> int:
            nonlocal call_count
            call_count += 1
            return 0

        with patch("server.cleanup_stale_cache", fake_cleanup):
            task = asyncio.create_task(_cache_cleanup_loop(interval_seconds=0.01))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_cleanup_loop_swallows_exceptions(self):
        from unittest.mock import patch

        from server import _cache_cleanup_loop

        call_count = 0

        def raising_cleanup() -> int:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("oops")

        with patch("server.cleanup_stale_cache", raising_cleanup):
            task = asyncio.create_task(_cache_cleanup_loop(interval_seconds=0.01))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert call_count >= 2  # kept running despite exceptions

    def test_main_passes_lifespan_to_fastmcp(self):
        """main() must pass a lifespan to FastMCP (not call create_task directly)."""
        from unittest.mock import MagicMock, patch

        import server

        captured: dict = {}

        def capture_fastmcp(*args, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        with (
            patch("server.load_config") as mock_cfg,
            patch("server.load_commands") as mock_cmds,
            patch("server.FastMCP", side_effect=capture_fastmcp),
            patch("server._register_tools"),
        ):
            mock_cfg.return_value = server.BridgeConfig()
            mock_cmds.return_value = server.CommandsConfig(commands={})
            server.main()

        assert "lifespan" in captured, "main() must pass lifespan= to FastMCP"

    @pytest.mark.asyncio
    async def test_lifespan_starts_cleanup_task(self):
        """_cache_cleanup_lifespan must schedule the cleanup loop on entry."""
        from unittest.mock import patch

        import server

        created_tasks = []
        orig = asyncio.create_task

        def track(coro, *a, **kw):
            t = orig(coro, *a, **kw)
            created_tasks.append(t)
            return t

        with patch("asyncio.create_task", side_effect=track):
            async with server._cache_cleanup_lifespan(None):
                pass  # startup is all we need to trigger

        for t in created_tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        assert any(created_tasks), "lifespan must schedule at least one task on startup"


class TestBuildTools:
    """Tests for build_tools() MCP tool definition generation."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

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

    def test_allow_extra_args_false_has_no_args_in_schema(self):
        from server import build_tools

        config = self._make_config(
            cmd=dict(command=["ls"], allow_extra_args=False, cwd="/app"),
        )
        assert "args" not in build_tools(config)[0].inputSchema["properties"]

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

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

    @pytest.mark.asyncio
    async def test_captures_stdout_and_exit_code(self):
        from server import execute_command

        config = self._make_config(echo=dict(command=["echo", "hello"], allow_extra_args=True, cwd="/tmp"))
        result = await execute_command("echo", ["world"], config)
        assert "hello" in result.stdout
        assert "world" in result.stdout
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_captures_stderr(self):
        from server import execute_command

        config = self._make_config(
            stderr_cmd=dict(
                command=["python", "-c", "import sys; sys.stderr.write('err\\n')"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        result = await execute_command("stderr_cmd", [], config)
        assert "err" in result.stderr

    @pytest.mark.asyncio
    async def test_nonzero_exit_code_returned(self):
        from server import execute_command

        config = self._make_config(
            fail=dict(
                command=["python", "-c", "import sys; sys.exit(1)"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        result = await execute_command("fail", [], config)
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        from server import execute_command

        config = self._make_config(slow=dict(command=["sleep", "5"], allow_extra_args=False, cwd="/tmp", timeout=1))
        with pytest.raises(subprocess.TimeoutExpired):
            await execute_command("slow", [], config)

    @pytest.mark.asyncio
    async def test_missing_executable_raises(self):
        from server import execute_command

        config = self._make_config(bad=dict(command=["nonexistent_binary_xyz"], allow_extra_args=False, cwd="/tmp"))
        with pytest.raises(FileNotFoundError):
            await execute_command("bad", [], config)


class TestToolHandlers:
    """Integration tests for tool handler functions — call handlers directly."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

    def _reset_lock(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = None

    @pytest.mark.asyncio
    async def test_success_path_returns_command_result_json(self):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo", "hello"], allow_extra_args=True, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, "/tmp", "bridge-test.jsonl")
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
        handler = server._create_tool_handler("fail", config, "/tmp", "bridge-test.jsonl")
        result_str = await handler()
        data = json.loads(result_str)
        assert data["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_metacharacter_args_return_is_error(self):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, "/tmp", "bridge-test.jsonl")
        with pytest.raises(Exception, match=";"):
            await handler(args=["--flag; rm -rf /"])

    @pytest.mark.asyncio
    async def test_timeout_returns_is_error(self):
        import server

        self._reset_lock()
        config = self._make_config(slow=dict(command=["sleep", "5"], allow_extra_args=False, cwd="/tmp", timeout=1))
        handler = server._create_tool_handler("slow", config, "/tmp", "bridge-test.jsonl")
        with pytest.raises(Exception, match="timed out after 1s"):
            await handler()

    @pytest.mark.asyncio
    async def test_exec_failure_returns_is_error(self):
        import server

        self._reset_lock()
        config = self._make_config(bad=dict(command=["nonexistent_xyz"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("bad", config, "/tmp", "bridge-test.jsonl")
        with pytest.raises(Exception, match="not found"):
            await handler()

    @pytest.mark.asyncio
    async def test_busy_rejection_returns_is_error(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = "other_cmd"
        await server._lock.acquire()
        try:
            config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
            handler = server._create_tool_handler("echo", config, "/tmp", "bridge-test.jsonl")
            with pytest.raises(Exception, match="busy"):
                await handler()
        finally:
            server._lock.release()
            server._current_command = None

    @pytest.mark.asyncio
    async def test_concurrent_busy_rejection(self):
        """Second handler launched while first is running must be rejected immediately."""
        import server

        server._lock = asyncio.Lock()
        server._current_command = None
        config = self._make_config(
            slow=dict(
                command=["python", "-c", "import time; time.sleep(0.5)"],
                allow_extra_args=False,
                cwd="/tmp",
            )
        )
        handler = server._create_tool_handler("slow", config, "/tmp", "bridge-test.jsonl")
        task1 = asyncio.create_task(handler())
        await asyncio.sleep(0.1)  # let task1 acquire lock and enter subprocess
        with pytest.raises(Exception, match="busy"):
            await handler()
        await task1


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
            "timestamp",
            "command",
            "args",
            "exit_code",
            "duration_ms",
            "stdout",
            "stderr",
            "stdout_bytes",
            "stderr_bytes",
            "rejected",
            "rejection_reason",
        }
        assert expected_keys <= set(data.keys())


class TestLogIntegration:
    """Tests for log_request wired into tool handlers."""

    def _make_config(self, **commands):
        from server import CommandEntry, CommandsConfig

        return CommandsConfig(commands={name: CommandEntry(**kwargs) for name, kwargs in commands.items()})

    def _reset_lock(self):
        import server

        server._lock = asyncio.Lock()
        server._current_command = None

    def _read_log(self, log_dir, filename="bridge.jsonl"):
        import json
        from pathlib import Path

        lines = (Path(log_dir) / filename).read_text().splitlines()
        return [json.loads(line) for line in lines]

    @pytest.mark.asyncio
    async def test_successful_call_logged(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo", "hi"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "bridge.jsonl")
        await handler()
        entries = self._read_log(tmp_path)
        assert len(entries) == 1
        assert entries[0]["rejected"] is False
        assert entries[0]["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_rejected_call_logged_with_reason(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "bridge.jsonl")
        with pytest.raises(Exception):
            await handler(args=["bad; arg"])
        entries = self._read_log(tmp_path)
        assert len(entries) == 1
        assert entries[0]["rejected"] is True
        assert entries[0]["rejection_reason"] is not None
        assert entries[0]["stdout"] is None
        assert entries[0]["stderr"] is None

    @pytest.mark.asyncio
    async def test_busy_rejection_logged(self, tmp_path):
        import server

        server._lock = asyncio.Lock()
        server._current_command = "other_cmd"
        await server._lock.acquire()
        try:
            config = self._make_config(echo=dict(command=["echo"], allow_extra_args=False, cwd="/tmp"))
            handler = server._create_tool_handler("echo", config, str(tmp_path), "bridge.jsonl")
            with pytest.raises(Exception, match="busy"):
                await handler()
        finally:
            server._lock.release()
            server._current_command = None

        entries = self._read_log(tmp_path)
        assert len(entries) == 1
        assert entries[0]["rejected"] is True
        assert "other_cmd" in entries[0]["rejection_reason"]

    @pytest.mark.asyncio
    async def test_duration_ms_nonzero_for_executed_commands(self, tmp_path):
        import server

        self._reset_lock()
        # Use python -c "pass" — interpreter startup guarantees duration > 1ms
        config = self._make_config(py=dict(command=["python", "-c", "pass"], allow_extra_args=False, cwd="/tmp"))
        handler = server._create_tool_handler("py", config, str(tmp_path), "bridge.jsonl")
        await handler()
        entries = self._read_log(tmp_path)
        assert entries[0]["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_duration_ms_zero_for_rejected_requests(self, tmp_path):
        import server

        self._reset_lock()
        config = self._make_config(echo=dict(command=["echo"], allow_extra_args=True, cwd="/tmp"))
        handler = server._create_tool_handler("echo", config, str(tmp_path), "bridge.jsonl")
        with pytest.raises(Exception):
            await handler(args=["bad; arg"])
        entries = self._read_log(tmp_path)
        assert entries[0]["duration_ms"] == 0
