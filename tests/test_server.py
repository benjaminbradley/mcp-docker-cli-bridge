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
