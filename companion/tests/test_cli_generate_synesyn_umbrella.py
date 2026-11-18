"""Umbrella ``lumur generate-synesyn`` stays bridge-optional."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], *, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Ensure Hub env cannot accidentally satisfy the command.
    for key in list(env):
        if key.startswith("LUMUR_SYNESYN_"):
            env.pop(key)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_umbrella_lists_generate_synesyn_in_help():
    proc = _run([sys.executable, "-m", "lumur.cli_main", "--help"])
    assert proc.returncode == 0
    assert "generate-synesyn" in proc.stdout


def test_umbrella_generate_synesyn_without_hub_is_clear():
    room = REPO_ROOT / "demo" / "fixtures" / "sample_room"
    proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli_main",
            "generate-synesyn",
            str(room),
            "--surface",
            "floor",
        ]
    )
    assert proc.returncode != 0
    err = (proc.stderr + proc.stdout).lower()
    assert "hub" in err
    assert "traceback" not in err
