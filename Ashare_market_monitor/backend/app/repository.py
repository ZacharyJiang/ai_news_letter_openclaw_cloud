import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonRepository:
    def __init__(self, data_dir: str) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._meta_file = self._data_dir / "etf_meta.json"
        self._extreme_file = self._data_dir / "etf_extreme.json"
        self._state_file = self._data_dir / "sync_state.json"

        self._lock = threading.Lock()

    def _read_file(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    def _write_file(self, path: Path, data: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def load_meta(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return self._read_file(self._meta_file, {})

    def save_meta(self, payload: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._write_file(self._meta_file, payload)

    def load_extreme(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return self._read_file(self._extreme_file, {})

    def save_extreme(self, payload: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._write_file(self._extreme_file, payload)

    def load_sync_state(self) -> dict[str, Any]:
        with self._lock:
            return self._read_file(
                self._state_file,
                {
                    "running": False,
                    "last_start": None,
                    "last_finish": None,
                    "processed": 0,
                    "total": 0,
                    "last_error": None,
                },
            )

    def save_sync_state(self, payload: dict[str, Any]) -> None:
        with self._lock:
            payload = dict(payload)
            payload["updated_at"] = datetime.now().isoformat()
            self._write_file(self._state_file, payload)
