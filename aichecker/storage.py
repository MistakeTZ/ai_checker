"""Append-only JSONL logs: every result and every user rating (the calibration dataset, FORMULA.md §18)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

RESULTS = "results.jsonl"
RATINGS = "ratings.jsonl"


class Storage:
    def __init__(self, data_dir: Path) -> None:
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def append(self, name: str, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._write, self.dir / name, line)

    @staticmethod
    def _write(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
