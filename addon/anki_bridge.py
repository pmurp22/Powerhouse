"""Read-only adapters between the game engine and Anki's collection.

Nothing in here writes to the collection: Powerhouse only ever reads the
review log, so it can't disturb scheduling, syncing or other add-ons.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Optional

ANSWER_FILTER = "ease between 1 and 4 and type between 0 and 3"


class AnkiClock:
    """Anki's idea of 'today', which respects the 'next day starts at' setting."""

    def __init__(self, get_col: Callable[[], Any]) -> None:
        self._get_col = get_col
        self._cache: tuple[float, int, int] = (0.0, 0, 0)

    def _timing(self) -> tuple[int, int]:
        now = time.time()
        stamp, today, cutoff = self._cache
        if now - stamp < 2.0 and cutoff and now * 1000 < cutoff:
            return today, cutoff
        sched = self._get_col().sched
        today = int(sched.today)
        cutoff = int(sched.day_cutoff) * 1000
        self._cache = (now, today, cutoff)
        return today, cutoff

    def reset(self) -> None:
        """Forget the cached day, say after the collection was swapped out by a full sync."""
        self._cache = (0.0, 0, 0)

    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def today(self) -> int:
        return self._timing()[0]

    def day_cutoff_ms(self) -> int:
        return self._timing()[1]

    def local_hour(self, ms: int) -> int:
        try:
            return datetime.fromtimestamp(ms / 1000).hour
        except (OverflowError, OSError, ValueError):
            return 12  # a timestamp the OS can't place (a damaged review row)

    def weekday(self, ms: int) -> int:
        try:
            return datetime.fromtimestamp(ms / 1000).weekday()
        except (OverflowError, OSError, ValueError):
            return -1


class AnkiRevlog:
    """Queries against the revlog table. `get_col` returns the open collection."""

    def __init__(self, get_col: Callable[[], Any]) -> None:
        self._get_col = get_col

    @property
    def db(self) -> Any:
        return self._get_col().db

    def new_rows(self, after_id: int, limit: int = 50_000) -> list[tuple[int, int, int, int, int]]:
        # `time` is how long the answer took in ms (Anki caps it at the deck's maximum answer time)
        rows = self.db.all(
            f"select id, cid, ease, type, time from revlog where id > ? and {ANSWER_FILTER} order by id limit ?",
            int(after_id), int(limit),
        )
        return [(int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4] or 0)) for r in rows]

    def ids_since(self, min_id: int) -> set[int]:
        return set(self.db.list(f"select id from revlog where id >= ? and {ANSWER_FILTER}", int(min_id)))

    def daily_counts(self, cutoff_ms: int, days: int) -> dict[int, int]:
        low = int(cutoff_ms) - int(days) * 86_400_000
        rows = self.db.all(
            f"select (? - 1 - id) / 86400000 as ago, count() from revlog "
            f"where id < ? and id >= ? and {ANSWER_FILTER} group by ago",
            int(cutoff_ms), int(cutoff_ms), low,
        )
        return {int(ago): int(n) for ago, n in rows}

    def banked_cards(self) -> int:
        # mature cards (21+ day interval). Counted from the cards table, which stays fast on
        # collections with hundreds of thousands of reviews (the review log took ~1 s there).
        return int(self.db.scalar("select count() from cards where ivl >= 21") or 0)

    def max_id(self, before: Optional[int] = None) -> int:
        """The newest review's id, optionally only among reviews before `before` (ms). A
        device with a wrong clock can leave a review stamped in the future; it mustn't
        become the bookmark that later answers are measured against."""
        if before is None:
            return int(self.db.scalar("select max(id) from revlog") or 0)
        return int(self.db.scalar("select max(id) from revlog where id < ?", int(before)) or 0)

    def has_any(self, ids: list[int]) -> bool:
        """Whether any of these review ids are in this collection's review log."""
        ids = [int(i) for i in ids][:20]
        if not ids:
            return False
        marks = ",".join("?" * len(ids))
        return bool(self.db.scalar(f"select 1 from revlog where id in ({marks}) limit 1", *ids))
