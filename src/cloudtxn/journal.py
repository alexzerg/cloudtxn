"""Append-only transaction journal."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Journal:
    """Write JSON Lines events using owner-only permissions."""

    def __init__(self, root: Path, transaction_id: str) -> None:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        self.path = root / f"{transaction_id}.jsonl"
        descriptor = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)

    def append(self, event: str, **payload: Any) -> None:
        """Append and fsync one event."""

        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
