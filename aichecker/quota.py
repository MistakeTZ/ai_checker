"""Per-user daily check quota, persisted so a bot restart doesn't reset it."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


class DailyQuota:
    """Counts checks per user per calendar day (server local time). ``limit`` 0 = unlimited."""

    def __init__(self, path: Path, limit: int) -> None:
        self.path = path
        self.limit = limit
        self._day = date.today().isoformat()
        self._counts: dict[str, int] = {}
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("day") == self._day:
                self._counts = {str(k): int(v) for k, v in saved.get("counts", {}).items()}
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            log.warning("ignoring unreadable quota file %s", path)

    def _roll(self) -> None:
        today = date.today().isoformat()
        if today != self._day:
            self._day, self._counts = today, {}

    def used(self, user_id: int) -> int:
        self._roll()
        return self._counts.get(str(user_id), 0)

    def remaining(self, user_id: int) -> int | None:
        return None if not self.limit else max(0, self.limit - self.used(user_id))

    def take(self, user_id: int) -> bool:
        """Use one check; False when today's quota is exhausted."""
        if self.limit and self.used(user_id) >= self.limit:
            return False
        self._counts[str(user_id)] = self.used(user_id) + 1
        self._save()
        return True

    def refund(self, user_id: int) -> None:
        if self.used(user_id) > 0:
            self._counts[str(user_id)] -= 1
            self._save()

    @staticmethod
    def resets_in_hours() -> int:
        midnight = datetime.combine(date.today() + timedelta(days=1), time.min)
        return max(1, round((midnight - datetime.now()).total_seconds() / 3600))

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"day": self._day, "counts": self._counts}), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save quota file %s", self.path, exc_info=True)
