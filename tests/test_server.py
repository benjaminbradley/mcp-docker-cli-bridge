"""Tests for server.py — MCP Docker CLI Bridge."""
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
