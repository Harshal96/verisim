from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from verisim.cli import app


def test_fixtures_cli_emits_json_manifest_on_config_error(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        app, ["fixtures", "--config", str(tmp_path / "missing.yaml")]
    )
    assert result.exit_code == 2
    manifest = json.loads(result.stdout)
    assert manifest["status"] == "error"
    assert manifest["fixture_path"] is None


def test_fixtures_command_is_available_to_another_process():
    process = subprocess.run(
        [sys.executable, "-m", "verisim.cli", "fixtures", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    assert process.returncode == 0
    assert "--config" in process.stdout
    assert "--format" in process.stdout
