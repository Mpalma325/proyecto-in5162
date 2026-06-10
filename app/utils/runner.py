import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_DIR.parent
TESTS_DIR = PROJECT_ROOT / "tests_semanales"
TAREAS_DIR = PROJECT_ROOT / "tareas"


def run_command(
    cmd: list[str],
    cwd: Path,
    output_callback: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    lines: list[str] = []
    for line in process.stdout:
        lines.append(line)
        if output_callback:
            output_callback("".join(lines))

    process.wait()
    return process.returncode, "".join(lines)


def python() -> str:
    return sys.executable
