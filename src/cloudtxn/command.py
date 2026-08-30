"""Safe subprocess execution without a shell."""

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Optional

from cloudtxn.errors import AdapterError


@dataclass(frozen=True)
class CommandResult:
    """Captured command output."""

    stdout: str
    stderr: str
    returncode: int


def run_command(
    args: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    check: bool = True,
) -> CommandResult:
    """Execute an argument array and capture text output."""

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        env=merged_env,
    )
    result = CommandResult(completed.stdout.strip(), completed.stderr.strip(), completed.returncode)
    if check and completed.returncode != 0:
        detail = result.stderr or result.stdout or "command returned no output"
        raise AdapterError(f"command failed ({completed.returncode}): {' '.join(args)}: {detail}")
    return result
