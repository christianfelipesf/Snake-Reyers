from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    temp_path = Path(temp_name)
    try:
        for attempt in range(7):
            try:
                os.replace(temp_path, path)
                return
            except PermissionError:
                if attempt == 6:
                    raise
                # Antivirus and indexers can briefly hold JSON files on Windows.
                time.sleep(0.025 * (2**attempt))
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
