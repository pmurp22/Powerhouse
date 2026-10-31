"""Finding a save that lost its profile name. No Anki imports, so it can be tested alone.

Saves are named after the Anki profile. Renaming the profile (Profiles → Rename) changes
that name, which used to leave the progress behind in a file nobody opened.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Iterable, Optional


def _recent_review_ids(data: dict[str, Any]) -> list[int]:
    """A few review ids this save has paid out, newest first."""
    led = data.get("ledger") if isinstance(data.get("ledger"), dict) else {}
    ids: list[int] = []
    try:
        ids = sorted((int(k) for k in (led.get("recent") or {})), reverse=True)[:10]
        last = int(led.get("last_id") or 0)
        if last and last not in ids:
            ids.insert(0, last)
    except (TypeError, ValueError):
        pass
    return ids


def find_orphan_save(save_dir: str, taken: Iterable[str], col_mark: Optional[int],
                     in_this_collection: Callable[[list[int]], bool]) -> Optional[str]:
    """The newest save in `save_dir` that no current profile uses (`taken` holds every
    current profile's save paths) and that belongs to this collection: the same
    collection creation time (`col_mark`), or, for saves older than that check,
    reviews this collection's log still has. None if there's no such save."""
    taken_set = {os.path.normcase(os.path.abspath(p)) for p in taken}
    best: Optional[tuple[float, str]] = None
    try:
        names = os.listdir(save_dir)
    except OSError:
        return None
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(save_dir, name)
        if os.path.normcase(os.path.abspath(path)) in taken_set:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("ledger"), dict) or "salt" not in data:
            continue
        mark = data.get("col_crt")
        if mark is not None:
            try:
                same = col_mark is not None and int(mark) == int(col_mark)
            except (TypeError, ValueError):
                same = False
        else:
            ids = _recent_review_ids(data)
            same = bool(ids) and bool(in_this_collection(ids))
        if not same:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, path)
    return best[1] if best else None
