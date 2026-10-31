"""Powerhouse game engine.

Pure Python: no Anki imports, so it can be tested on its own. The Anki side
supplies two small adapters:

* a Clock (what "today" is in Anki's terms, local hours), and
* a RevlogSource (read-only queries against Anki's review log).

Design rules that matter for studying:

* Every answer earns the same ATP no matter which button you press, so there is
  never a reason to grade a card dishonestly.
* Speed is never rewarded. "Flow" only asks that you don't take long breaks.
* Fair play: mashing through cards, looping one card, or letting auto-advance
  answer for you stops paying almost at once (see _fair_play). Reviewing at a
  normal pace, a couple of seconds a card or more, almost never trips it.
* The review log is the source of truth, so reviews done on your phone count
  once they sync, and an undo takes back exactly what that answer earned.
* The engine never writes to the Anki collection.
"""

from __future__ import annotations

import hashlib
import math
from decimal import ROUND_HALF_UP, Decimal
import random
import time
from typing import Any, Iterable, Optional, Protocol

from . import content as C

DAY_MS = 86_400_000
RECENT_WINDOW_MS = 4 * DAY_MS  # full details kept this long, so an undo can be taken back
LATE_WINDOW_MS = 30 * DAY_MS  # reviews that sync in this late (phone, AnkiWeb) still pay
REDO_WINDOW_MS = 15 * 60 * 1000  # every sync re-checks this much recent history
FUTURE_SLACK_MS = 5 * 60 * 1000  # clocks on two devices can disagree by this much
ROW_PAGE = 50_000  # review-log rows fetched per query
SESSION_GAP_MS = 60 * 60 * 1000  # a gap this long starts a new study session
MAX_FREEZES = 2  # earned freezes you can bank (loot freezes can go one higher)
FREEZE_EVERY = 7  # earn a freeze every 7 streak days
DAY_STATS_KEEP = 120  # days of detailed stats kept in the save file
DIVIDEND_RATE = 0.01  # dividend = banked cards × 1% × ATP per card
DIVIDEND_MAX_CARDS = 1000
DUP_ENZYME_CARDS = {"common": 10, "rare": 25, "epic": 60, "legendary": 150}
STATE_VERSION = 2

# Fair play. An answer that doesn't count earns nothing and doesn't count toward
# the goal, quests or streak; it's just tallied so the game can say why.
QUICK_MS = 1000  # an answer faster than this is "quick"
QUICK_SPACING = 4  # a quick answer counts only if none of the 4 answers before it was quick
CARD_DAILY_CAP = 4  # a card counts at most this many times a day
STEADY_RUN = 6  # this many answers in a row with machine-steady timing (auto-advance)...
STEADY_SPREAD_MS = 60  # ...all within this many ms of each other don't count
STEADY_GAP_MS = 3 * 60 * 1000  # a break this long starts a fresh rhythm
ROW_HAS_TIME = True  # review-log rows carry the answer time (ms) as a fifth field
NOCOUNT_KEYS = {"quick": "xq", "repeat": "xr", "steady": "xs"}
HISTORY_DAYS = 800
RECENT_HISTORY_DAYS = 45  # after a sync, only recount recent days (covers the late-sync window)

RARITY_RANK = {r: i for i, r in enumerate(C.RARITIES)}


class Clock(Protocol):
    def now_ms(self) -> int: ...
    def today(self) -> int: ...
    def day_cutoff_ms(self) -> int: ...
    def local_hour(self, ms: int) -> int: ...
    def weekday(self, ms: int) -> int: ...  # Monday = 0 ... Sunday = 6


class RevlogSource(Protocol):
    def new_rows(self, after_id: int, limit: int) -> list[tuple]:
        """(id, card_id, ease, type, time_ms) for answers with id > after_id, ascending, at most `limit`.
        The time is optional: rows without it are never judged as too quick or too steady."""
        ...

    def ids_since(self, min_id: int) -> set[int]:
        """Ids of answers with id >= min_id."""
        ...

    def daily_counts(self, cutoff_ms: int, days: int) -> dict[int, int]:
        """days_ago -> number of answers, relative to the given day cutoff."""
        ...

    def banked_cards(self) -> int:
        """Mature cards: interval of 21 days or more."""
        ...

    def max_id(self) -> int: ...


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _hash_units(key: str, salt: str) -> tuple[float, float]:
    digest = hashlib.blake2b(f"{salt}|{key}".encode(), digest_size=16).digest()
    a = int.from_bytes(digest[:8], "big") / 2**64
    b = int.from_bytes(digest[8:], "big") / 2**64
    return a, b


def _pack_ids(ids: Iterable[int]) -> list[int]:
    """Sorted ids stored as [first, gap, gap, ...] so the save file stays small."""
    out: list[int] = []
    prev = 0
    for i in sorted(set(int(x) for x in ids)):
        out.append(i - prev)
        prev = i
    return out


def _unpack_ids(packed: Iterable[int]) -> list[int]:
    out: list[int] = []
    acc = 0
    for d in packed:
        acc += int(d)
        out.append(acc)
    return out


# ledger records: [atp, day, cid, vid, key, hour, flag, taken]; older saves have only the first six
FLAG_WHY = {1: "quick", 2: "repeat", 3: "steady"}
WHY_FLAG = {v: k for k, v in FLAG_WHY.items()}


def _rec_flag(rec: list) -> int:
    return int(rec[6]) if len(rec) > 6 and rec[6] else 0


def _rec_time(rec: list) -> Optional[int]:
    return int(rec[7]) if len(rec) > 7 and rec[7] is not None else None


def _to_fixed(x: float, places: int) -> str:
    """JavaScript's Number.toFixed: the exact binary value, ties rounded up."""
    q = Decimal(1).scaleb(-places)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))


def fmt_number(n: float) -> str:
    """Python twin of fmt() in web/mito.js, for tooltips."""
    if n is None or not math.isfinite(n):
        return "0"
    neg = n < 0
    n = abs(n)
    if n < 10:
        out = f"{math.floor(n * 10 + 0.5) / 10:g}" if n >= 1 or n == 0 else _to_fixed(n, 2)
    elif n < 1e4:
        out = f"{math.floor(n):,}"
    else:
        units = ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]
        i = min(int(math.floor(math.log10(n) / 3)), len(units) - 1)
        v = n / 1000 ** i
        if v >= 999.5 and i < len(units) - 1:
            i += 1
            v = n / 1000 ** i
        txt = _to_fixed(v, 0) if v >= 100 else _to_fixed(v, 1) if v >= 10 else _to_fixed(v, 2)
        if "." in txt:
            txt = txt.rstrip("0").rstrip(".")
        out = txt + units[i]
    return ("−" if neg else "") + out


def round_nice(x: float) -> int:
    """Round to a friendly quest target (10s, then 25s, then 50s)."""
    if x < 100:
        return int(max(10, round(x / 10) * 10))
    if x < 400:
        return int(round(x / 25) * 25)
    return int(round(x / 50) * 50)


_GROWTH_POWERS = [1.0]


def growth_pow(n: int) -> float:
    """COST_GROWTH ** n, by repeated multiplication: plain multiplication rounds the same
    way everywhere, so the browser demo's engine gets exactly the same prices."""
    pw = _GROWTH_POWERS
    while len(pw) <= n:
        pw.append(pw[-1] * C.COST_GROWTH)
    return pw[n]


def compute_streak(
    counts: dict[int, int],
    goal: int,
    today: int,
    install_day: int,
    loot_freezes: Iterable[int] = (),
    sweep_days: Iterable[int] = (),
) -> dict[str, Any]:
    """Walk the daily answer counts and work out the current streak.

    A day counts when it has at least `goal` answers, or when every due review
    was finished that day (a clean sweep). From the install day on, every 7
    streak days earns a freeze (bank up to 2), and a missed day uses a freeze
    instead of breaking the streak. Today never breaks a streak; it only
    extends it once the day counts.
    """
    goal = max(1, int(goal))
    sweeps = {int(d) for d in sweep_days}
    loot_by_day: dict[int, int] = {}
    for d in loot_freezes:
        loot_by_day[int(d)] = loot_by_day.get(int(d), 0) + 1

    past_days = [d for d, n in counts.items() if n > 0 and d < today]
    start = min(past_days) if past_days else today
    start = max(start, today - HISTORY_DAYS)

    streak = 0
    best = 0
    freezes = 0
    frozen: list[int] = []
    for d in range(start, today):
        freezes = min(freezes + loot_by_day.get(d, 0), MAX_FREEZES + 1)
        if counts.get(d, 0) >= goal or d in sweeps:
            streak += 1
            if d >= install_day and streak % FREEZE_EVERY == 0 and freezes < MAX_FREEZES:
                freezes += 1
        elif d >= install_day and freezes > 0 and streak > 0:
            freezes -= 1
            frozen.append(d)
        else:
            streak = 0
        best = max(best, streak)
    freezes = min(freezes + loot_by_day.get(today, 0), MAX_FREEZES + 1)
    today_done = counts.get(today, 0) >= goal or today in sweeps
    current = streak + (1 if today_done else 0)
    if today_done and today >= install_day and current % FREEZE_EVERY == 0 and freezes < MAX_FREEZES:
        freezes += 1  # show the freeze the moment day 7 is done, not tomorrow
    best = max(best, current)
    return {
        "current": current,
        "best": best,
        "freezes": freezes,
        "today_done": today_done,
        "today_count": counts.get(today, 0),
        "frozen_days": frozen[-30:],
        "at_risk": (not today_done) and streak > 0,
    }


def new_state(now_ms: int, today: int, max_revlog_id: int, salt: Optional[str] = None) -> dict[str, Any]:
    return {
        "v": STATE_VERSION,
        "salt": salt or hashlib.blake2b(str(now_ms).encode() + str(random.random()).encode(),
                                         digest_size=6).hexdigest(),
        "created_ms": now_ms,
        "install_day": today,
        "install_id": max_revlog_id,
        "atp": 0.0,
        "atp_run": 0.0,
        "atp_all": 0.0,
        "owned": {},
        "upgrades": [],
        "mtdna": 0,
        "fissions": 0,
        "xp": 0,
        "answers": 0,
        # recent: answers paid in the last few days, with enough detail to undo them
        # old: ids of older paid answers (packed), so a late sync can't pay twice
        # floor: never look below this id
        "ledger": {"last_id": max_revlog_id, "recent": {}, "old": [], "floor": max_revlog_id},
        "flow": {"ts": 0, "n": 0, "best": 0},
        # pace: the last answer's id, answers since the last quick one, and recent answer times
        "pace": {"ts": 0, "sq": 99, "t": []},
        "late_counts": {},  # "cid:day" -> counted answers, for reviews that sync after their day
        "days": {},
        "cards_today": {"day": today, "counts": {}},
        "granted": {"day": today, "keys": []},
        "pity": 0,
        "leg_dupes": 0,  # duplicate legendary enzymes in a row (see LEGENDARY_PITY)
        "vesicles": [],
        "vseq": 0,
        "codex": {},
        "cosmetics": {
            "owned": [c.id for c in C.COSMETICS if c.source == "default"],
            "equipped": dict(C.DEFAULT_EQUIPPED),
            "new": [],
        },
        "achievements": {},
        "quests": {"day": None, "list": [], "bonus": False},
        "quests_done": 0,
        "quest_full_days": 0,
        "loot_freezes": [],
        "sweep_list": [],  # days with a clean sweep (kept longer than the per-day stats)
        "stats": {
            "opened": 0,
            "purchases": 0,
            "pokes": 0,
            "sweeps": 0,
            "comebacks": 0,
            "weekend_pairs": 0,
            "early_best": 0,
            "best_day": 0,
            "opened_game": False,
            "legendary_enzymes": 0,
            "dividends": 0,
            "uncounted": 0,
        },
        "session": None,
        "last_session": None,
        "banked": 0,
        "level_seen": 1,
        "seen_intro": False,
        "welcome_given": False,
    }


def migrate(state: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Fill in any keys a newer version added. Never removes data."""

    def fill(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if k not in dst:
                dst[k] = v
            elif isinstance(v, dict) and isinstance(dst[k], dict) and k not in ("owned", "codex", "achievements",
                                                                                 "days", "recent", "counts"):
                fill(dst[k], v)

    led = state.get("ledger")
    if isinstance(led, dict) and "floor" not in led:
        # saves from before late syncs were tracked for 30 days: only the last
        # few days have complete records, so don't look further back than that
        last_id = int(led.get("last_id", 0) or 0)
        led["floor"] = max(int(state.get("install_id", 0) or 0),
                           min(last_id, int(fresh["created_ms"]) - RECENT_WINDOW_MS))
        led.setdefault("old", [])
    if "sweep_list" not in state:
        # older saves kept sweeps only in the per-day stats, which are trimmed after 120 days
        days = state.get("days") if isinstance(state.get("days"), dict) else {}
        state["sweep_list"] = sorted(int(k) for k, ds in days.items() if isinstance(ds, dict) and ds.get("sweep"))
    fill(state, fresh)
    state["v"] = STATE_VERSION
    return state


# ---------------------------------------------------------------------------
# the game
# ---------------------------------------------------------------------------


class Game:
    def __init__(self, state: dict[str, Any], clock: Clock, source: RevlogSource,
                 settings: Optional[dict[str, Any]] = None) -> None:
        self.s = state
        self.clock = clock
        self.source = source
        self.settings = {"daily_goal": 100}
        if settings:
            self.settings.update(settings)
        self.hist: dict[int, int] = {}
        self.hist_max_id = 0
        self.hist_loaded = False
        self.dirty = False
        self._streak_cache: Optional[tuple[Any, dict[str, Any]]] = None
        self._today_cache: Optional[int] = None
        self._old_cache: Optional[tuple[list[int], int, set[int]]] = None
        self.row_page = ROW_PAGE

    # ------------------------------------------------------------------ time

    def today(self) -> int:
        return self.clock.today()

    def day_of(self, rid: int, cutoff: int, today: int) -> int:
        return today - ((cutoff - 1 - rid) // DAY_MS)

    def _rollover_hour(self) -> int:
        try:
            return self.clock.local_hour(self.clock.day_cutoff_ms())
        except Exception:
            return 4

    def _day(self, day: int) -> dict[str, Any]:
        key = str(day)
        ds = self.s["days"].get(key)
        if ds is None:
            # n: answers that counted; x: answers that didn't (xq quick, xr repeats, xs steady)
            ds = {"n": 0, "atp": 0.0, "noon": 0, "early": 0, "flow": 0, "vf": 0, "sessions": 0,
                  "lt": 0, "goal": False, "sweep": False, "wk": False, "cb": False,
                  "x": 0, "xq": 0, "xr": 0, "xs": 0}
            self.s["days"][key] = ds
        elif "x" not in ds:
            ds.update({"x": 0, "xq": 0, "xr": 0, "xs": 0})  # a day saved before fair play
        return ds

    # -------------------------------------------------------------- numbers

    def goal(self) -> int:
        try:
            return max(1, int(self.settings.get("daily_goal", 100)))
        except (TypeError, ValueError):
            return 100

    def level_info(self) -> tuple[int, int, int]:
        return C.level_from_xp(self.s["xp"])

    def pathway_multiplier(self, pid: str) -> float:
        n = 0
        for uid in self.s["upgrades"]:
            u = C.UPGRADE_BY_ID.get(uid)
            if u and u.kind == "pathway" and u.pathway == pid:
                n += 1
        return 2.0 ** n

    def pathway_output(self, pid: str) -> float:
        p = C.PATHWAY_BY_ID[pid]
        return self.s["owned"].get(pid, 0) * p.base_yield * self.pathway_multiplier(pid)

    def base_yield(self) -> float:
        return 1.0 + sum(self.pathway_output(p.id) for p in C.PATHWAYS)

    def sets_complete(self) -> int:
        n = 0
        for es in C.ENZYME_SETS:
            if all(self.s["codex"].get(e.id, 0) > 0 for e in C.ENZYMES if e.set == es.id):
                n += 1
        return n

    def multiplier_parts(self) -> list[tuple[str, float]]:
        parts: list[tuple[str, float]] = []
        habits = 1.0
        for uid in self.s["upgrades"]:
            u = C.UPGRADE_BY_ID.get(uid)
            if u and u.kind == "habit":
                habits *= u.factor
        if habits != 1.0:
            parts.append(("Study habits", habits))
        level = self.level_info()[0]
        if level > 1:
            parts.append((f"Level {level}", 1 + C.LEVEL_ATP_BONUS * (level - 1)))
        n_ach = len(self.s["achievements"])
        if n_ach:
            parts.append((f"{n_ach} trophies", 1 + C.ACHIEVEMENT_ATP_BONUS * n_ach))
        sets = self.sets_complete()
        if sets:
            bonus = C.SET_BONUS * sets + (C.CODEX_COMPLETE_BONUS if sets == len(C.ENZYME_SETS) else 0)
            parts.append((f"{sets} enzyme sets", 1 + bonus))
        extra = self.expression_levels_extra()
        if extra:
            parts.append(("Enzyme expression", 1 + C.EXPRESSION_BONUS * extra))
        if self.s["mtdna"]:
            parts.append((f"{self.s['mtdna']} mtDNA", 1 + C.MTDNA_BONUS * self.s["mtdna"]))
        return parts

    def expression_levels_extra(self) -> int:
        """Expression levels above 1, summed over every enzyme found."""
        n = 0
        for e in C.ENZYMES:
            lv = C.expression_level(self.s["codex"].get(e.id, 0), e.rarity)
            if lv > 1:
                n += lv - 1
        return n

    def legendary_guaranteed(self) -> bool:
        """True when bad-luck protection makes the next legendary enzyme one you're missing."""
        if self.s.get("leg_dupes", 0) < C.LEGENDARY_PITY:
            return False
        unlocked = set(self.unlocked_sets())
        return any(e.rarity == "legendary" and e.set in unlocked and not self.s["codex"].get(e.id) for e in C.ENZYMES)

    def unlocked_sets(self) -> list[str]:
        level = self.level_info()[0]
        days_in = self.today() - int(self.s["install_day"])
        return [es.id for es in C.ENZYME_SETS if es.unlock_level <= level and es.unlock_day <= days_in]

    def growth(self) -> float:
        """How big Mito has grown this run (0 to 1), from what his own pathways make."""
        return max(0.0, min(1.0, math.log10(max(1.0, self.base_yield())) / C.MITO_FULL_LOG10))

    @staticmethod
    def drop_weight(n_today: int) -> float:
        """Vesicle drop-rate factor for the n-th answer that counted today (see VESICLE_TAPER)."""
        for limit, w in C.VESICLE_TAPER:
            if limit is None or n_today <= limit:
                return w
        return C.VESICLE_TAPER[-1][1]

    def global_multiplier(self) -> float:
        m = 1.0
        for _, f in self.multiplier_parts():
            m *= f
        return m

    def per_card(self) -> float:
        return self.base_yield() * self.global_multiplier()

    def flow_cap(self) -> int:
        n = sum(1 for uid in ("flow1", "flow2") if uid in self.s["upgrades"])
        return C.FLOW_CAPS[n]

    def flow_multiplier(self, n: int) -> float:
        return 1.0 + C.FLOW_STEP * min(max(n, 0), self.flow_cap())

    def flow_gap(self) -> int:
        """Longest break that keeps flow going (the Pomodoro timer stretches it)."""
        return C.FLOW_GAP_POMODORO_MS if "pomodoro" in self.s["upgrades"] else C.FLOW_GAP_MS

    def current_flow(self) -> int:
        f = self.s["flow"]
        if not f["ts"]:
            return 0
        now = self.clock.now_ms()
        if now - f["ts"] > self.flow_gap() or f["ts"] > now + FUTURE_SLACK_MS:
            return 0
        return f["n"]

    def find_multiplier(self) -> float:
        m = 1.0
        for uid in ("clathrin", "dynamin"):
            if uid in self.s["upgrades"]:
                m *= C.UPGRADE_BY_ID[uid].factor
        return m

    def rarity_weights(self) -> dict[str, float]:
        if "rab" in self.s["upgrades"]:
            return dict(C.RARITY_WEIGHTS_RAB)
        return dict(C.RARITY_WEIGHTS)

    def _roll_rarity(self, u: float) -> str:
        weights = self.rarity_weights()
        total = sum(weights.values())
        x = u * total
        for r in C.RARITIES:
            x -= weights[r]
            if x < 0:
                return r
        return "common"

    # -------------------------------------------------------------- history

    def apply_history(self, days_ago_counts: dict[int, int], banked: Optional[int], max_id: int,
                      partial_days: Optional[int] = None, counted_on: Optional[int] = None) -> None:
        """Load per-day answer counts computed from the review log.

        With `partial_days`, the counts only cover the most recent days; older days keep
        what the last full count found (big review logs make the full count slow).
        `counted_on` is the day the counts were taken on, when that may not be today
        (a count that started just before the day rolled over)."""
        today = self.today()
        base = today if counted_on is None else int(counted_on)
        fresh = {base - int(k): int(v) for k, v in days_ago_counts.items()}
        if partial_days and self.hist_loaded:
            start = base - int(partial_days) + 1
            self.hist = {d: n for d, n in self.hist.items() if d < start}
            self.hist.update(fresh)
        else:
            self.hist = fresh
        self.hist_max_id = int(max_id)
        # answers we processed after that query ran aren't in its counts yet
        for k, rec in self.s["ledger"]["recent"].items():
            if int(k) > self.hist_max_id:
                self.hist[rec[1]] = self.hist.get(rec[1], 0) + 1
        self.hist_loaded = True
        if banked is not None:
            self.s["banked"] = int(banked)
        self._streak_cache = None
        counts = self.effective_counts()
        best = max(counts.values()) if counts else 0
        if best > self.s["stats"]["best_day"]:
            self.s["stats"]["best_day"] = best
        q = self.s["quests"]
        if q.get("day") == today and not q.get("hist") and not any(x["done"] for x in q.get("list", [])):
            # today's quests were drawn before we knew how much you usually study
            self.s["quests"] = {"day": today, "list": self._make_quests(today), "bonus": False, "hist": True}
        self.dirty = True

    def load_history(self) -> None:
        cutoff = self.clock.day_cutoff_ms()
        counts = self.source.daily_counts(cutoff, HISTORY_DAYS)
        self.apply_history(counts, self.source.banked_cards(), self.source.max_id())

    def effective_counts(self) -> dict[int, int]:
        """Answers per day for the streak: the review log's counts, minus the answers
        that didn't count (fair play) on days the game kept stats for."""
        counts = dict(self.hist)
        for k, ds in self.s["days"].items():
            x = ds.get("x", 0)
            if x:
                d = int(k)
                if d in counts:
                    counts[d] = max(0, counts[d] - x)
        return counts

    def today_count(self) -> int:
        """Today's answers that count toward the goal, including any from before Powerhouse was
        installed today (the review log has them) but not the ones fair play turned away."""
        today = self.today()
        ds = self.s["days"].get(str(today)) or {}
        if not self.hist_loaded:
            return int(ds.get("n", 0))
        return max(0, self.hist.get(today, 0) - ds.get("x", 0))

    def reanchor_install_day(self) -> None:
        """The collection was replaced (a full sync download, a .colpkg import), and Anki
        counts days from the collection's creation, so today's number jumped. Keep the
        install day the same number of days back, for the enzyme sets' waits and freezes."""
        days_in = max(0, (self.clock.now_ms() - int(self.s["created_ms"])) // DAY_MS)
        self.s["install_day"] = self.today() - int(days_in)
        self._today_cache = None
        self._streak_cache = None
        self.dirty = True

    def sweep_days(self) -> list[int]:
        return list(self.s["sweep_list"])

    def typical_day(self) -> int:
        today = self.today()
        vals = sorted(n for d, n in self.effective_counts().items() if today - 21 <= d < today and n > 0)
        if not vals:
            return 150
        return int(vals[len(vals) // 2])

    def streak(self) -> dict[str, Any]:
        today = self.today()
        ds = self.s["days"].get(str(today)) or {}
        key = (today, self.goal(), self.hist.get(today, 0), ds.get("x", 0), bool(ds.get("sweep")),
               len(self.s["loot_freezes"]), len(self.hist))
        if self._streak_cache and self._streak_cache[0] == key:
            return self._streak_cache[1]
        info = compute_streak(self.effective_counts(), self.goal(), today, self.s["install_day"],
                              self.s["loot_freezes"], self.sweep_days())
        self._streak_cache = (key, info)
        return info

    # ----------------------------------------------------------------- sync

    def sync(self, full: bool = False) -> list[dict[str, Any]]:
        """Pull new answers from the review log and settle rewards.

        `full=True` also looks back a few days for reviews that arrived late
        (phone sync) and takes back rewards for answers that were undone.
        """
        events: list[dict[str, Any]] = []
        now = self.clock.now_ms()
        today = self.today()
        cutoff = self.clock.day_cutoff_ms()
        self._roll_day(today, events)

        ledger = self.s["ledger"]
        recent: dict[str, list] = ledger["recent"]
        floor = max(int(self.s["install_id"]), int(ledger.get("floor", 0)))
        if full:
            self._check_reversals(events)
            floor_id = max(floor, min(ledger["last_id"], now - LATE_WINDOW_MS))
        else:
            # Look back a little so a redone answer (or a just-synced one) is caught;
            # anything already paid is skipped via the ledger. A row stamped in the
            # future (a phone with the wrong time) must not hide today's answers.
            floor_id = max(floor, min(ledger["last_id"], now) - REDO_WINDOW_MS)
        horizon = now - RECENT_WINDOW_MS
        gained = 0.0
        answered = 0
        counted = 0
        nocount: dict[str, int] = {}
        pc = self.per_card()
        rollover = self._rollover_hour()
        after = floor_id
        while True:
            rows = self.source.new_rows(after, self.row_page)
            for row in rows:
                if str(row[0]) in recent or row[0] in self._old_paid():
                    continue
                try:
                    got = self._apply(row, pc, cutoff, today, rollover, now, events, nocount)
                except Exception:
                    # an odd row must never stop the game: remember it as seen and move on
                    self._archive_paid([int(row[0])], now)
                    continue
                answered += 1
                if got is not None:
                    gained += got
                    counted += 1
            if rows:
                ledger["last_id"] = max(ledger["last_id"], max(r[0] for r in rows))
            if len(rows) < self.row_page:
                break
            after = rows[-1][0]
        # move old entries out of the detailed ledger
        if recent and len(recent) > 50:
            stale = [k for k in recent if int(k) < horizon]
            if stale:
                self._archive_paid([int(k) for k in stale], now)
                for k in stale:
                    del recent[k]
        if answered:
            events.insert(0, {"t": "answers", "n": counted, "atp": gained})
            self.dirty = True
        if nocount:
            events.append({"t": "nocount", "quick": nocount.get("quick", 0), "repeat": nocount.get("repeat", 0),
                           "steady": nocount.get("steady", 0)})
        self._after_changes(today, events)
        return events

    def _weekday(self, ms: int) -> int:
        try:
            return int(self.clock.weekday(ms))
        except Exception:
            return -1

    @staticmethod
    def _early(hour: int, rollover: int) -> bool:
        """Before 8 a.m. (for the Early bird trophy). When Anki's day starts at 8 or later,
        4 to 8 a.m. still counts, toward the day those answers belong to."""
        return (rollover if rollover < 8 else 4) <= hour < 8

    def _hour(self, ms: int) -> int:
        try:
            return int(self.clock.local_hour(ms))
        except Exception:
            return 12  # a timestamp the OS can't place: counts as neither early nor before noon

    def _card_count(self, cid: int, day: int) -> int:
        """How many answers of this card have counted on that day."""
        ct = self.s["cards_today"]
        if day == ct["day"]:
            return int(ct["counts"].get(str(cid), 0))
        return int(self.s["late_counts"].get(f"{cid}:{day}", 0))

    def _fair_play(self, rid: int, cid: int, day: int, taken: Optional[int]) -> Optional[str]:
        """None when an answer counts. Otherwise why it doesn't:

        * "quick": under a second, with another answer under a second among the 4
          before it (an occasional fast answer is fine; mashing through cards isn't),
        * "steady": the sixth answer in a row with machine-steady timing, which is
          what Anki's auto-advance produces and people never do,
        * "repeat": the card already counted CARD_DAILY_CAP times today.
        """
        pace = self.s["pace"]
        prev = int(pace.get("ts") or 0)
        gap: Optional[int] = rid - prev if prev else None
        if gap is not None and gap < 0:
            gap = None  # an older review that synced late: judge it on its own
        quick = taken is not None and taken < QUICK_MS
        since_quick = int(pace.get("sq", 99))
        times = [int(t) for t in (pace.get("t") or [])]
        if gap is None or gap > STEADY_GAP_MS:
            since_quick, times = 99, []  # a fresh start after a break
        why: Optional[str] = None
        if quick and since_quick < QUICK_SPACING:
            why = "quick"
        if taken is not None and not quick and taken % 1000 != 0:
            times.append(int(taken))  # a whole number of seconds is usually Anki's time cap, not a rhythm
        else:
            times = []
        if why is None and len(times) >= STEADY_RUN and max(times[-STEADY_RUN:]) - min(times[-STEADY_RUN:]) <= STEADY_SPREAD_MS:
            why = "steady"
        if why is None and self._card_count(cid, day) >= CARD_DAILY_CAP:
            why = "repeat"
        pace["ts"] = rid
        pace["sq"] = 0 if quick else min(99, since_quick + 1)
        pace["t"] = times[-(STEADY_RUN - 1):]
        return why

    def _apply(self, row: tuple, pc: float, cutoff: int, today: int, rollover: int, now: int,
               events: list[dict[str, Any]], nocount: dict[str, int]) -> Optional[float]:
        """Settle one answer. Returns the ATP it earned, or None if it didn't count."""
        rid, cid = int(row[0]), int(row[1])
        taken = int(row[4]) if len(row) > 4 and row[4] is not None else None
        hour = self._hour(rid)
        day = self.day_of(rid, cutoff, today)
        ds = self._day(day)
        if day != today:
            self._streak_cache = None  # a review that synced late can change a past day

        why = self._fair_play(rid, cid, day, taken)
        if why:
            ds["x"] += 1
            ds[NOCOUNT_KEYS[why]] += 1
            self.s["stats"]["uncounted"] = self.s["stats"].get("uncounted", 0) + 1
            if rid > self.hist_max_id:
                self.hist[day] = self.hist.get(day, 0) + 1
            nocount[why] = nocount.get(why, 0) + 1
            self.s["ledger"]["recent"][str(rid)] = [0.0, day, cid, None, None, hour, WHY_FLAG[why], taken]
            return None

        # study sessions
        if rid > ds["lt"]:
            if ds["lt"] == 0 or rid - ds["lt"] > SESSION_GAP_MS:
                ds["sessions"] += 1
            ds["lt"] = rid

        # flow: consecutive answers without a long break
        flow = self.s["flow"]
        if flow["ts"] > now + FUTURE_SLACK_MS:
            flow["ts"], flow["n"] = 0, 0  # left behind by a row stamped in the future
        if flow["ts"] <= rid <= now + FUTURE_SLACK_MS:
            if flow["ts"] and rid - flow["ts"] <= self.flow_gap():
                flow["n"] += 1
            else:
                flow["n"] = 1
            flow["ts"] = rid
            flow_n = flow["n"]
        else:
            flow_n = 1  # a late-synced older review
        flow["best"] = max(flow["best"], flow_n)
        ds["flow"] = max(ds["flow"], flow_n)

        # ATP (identical for every button)
        atp = pc * self.flow_multiplier(flow_n)
        self.s["atp"] += atp
        self.s["atp_run"] += atp
        self.s["atp_all"] += atp
        ds["atp"] += atp
        self.s["xp"] += 1
        self.s["answers"] += 1
        ds["n"] += 1
        if rid > self.hist_max_id:
            self.hist[day] = self.hist.get(day, 0) + 1

        if rollover <= hour < 12:
            ds["noon"] += 1
        if self._early(hour, rollover):
            ds["early"] += 1

        sess = self.s.get("session")
        if sess and rid >= sess["start"]:
            sess["n"] += 1
            sess["atp"] += atp
            sess["flow"] = max(sess["flow"], flow_n)

        # vesicle drop, deterministic per (card, day, nth counted answer of that card)
        ct = self.s["cards_today"]
        if day == ct["day"]:
            k = ct["counts"].get(str(cid), 0) + 1
            ct["counts"][str(cid)] = k
        else:
            lk = f"{cid}:{day}"
            self.s["late_counts"][lk] = self.s["late_counts"].get(lk, 0) + 1
            k = rid
        key = f"{cid}:{day}:{k}"
        granted = self.s["granted"]
        vid = None
        if not (granted["day"] == day and key in granted["keys"]):
            weight = self.drop_weight(ds["n"])  # drops thin out over a big day; pity fills at the same pace
            self.s["pity"] += weight
            u1, u2 = _hash_units(key, self.s["salt"])
            chance = C.VESICLE_BASE_CHANCE * self.find_multiplier() * weight
            if u1 < chance or self.s["pity"] >= C.VESICLE_PITY:
                rarity = self._roll_rarity(u2)
                vid = self._add_vesicle(rarity, pc, "drop", day)
                self.s["pity"] = 0
                if granted["day"] == day:
                    granted["keys"].append(key)
                ds["vf"] += 1
                if sess and rid >= sess["start"]:
                    sess["vf"] += 1
                events.append({"t": "vesicle", "r": rarity, "id": vid})

        self.s["ledger"]["recent"][str(rid)] = [round(atp, 6), day, cid, vid, key if vid else None, hour, 0, taken]
        return atp

    def _old_paid(self) -> set[int]:
        packed = self.s["ledger"].get("old") or []
        cache = self._old_cache
        if cache is None or cache[0] is not packed or cache[1] != len(packed):
            cache = (packed, len(packed), set(_unpack_ids(packed)))
            self._old_cache = cache
        return cache[2]

    def _archive_paid(self, ids: list[int], now: int) -> None:
        """Keep just the ids of answers that leave the detailed ledger, for 30 days."""
        ledger = self.s["ledger"]
        keep_from = now - LATE_WINDOW_MS
        merged: list[int] = []
        forgotten = 0
        for i in list(_unpack_ids(ledger.get("old", []))) + list(ids):
            if i >= keep_from:
                merged.append(i)
            else:
                forgotten = max(forgotten, i)
        ledger["old"] = _pack_ids(merged)
        if forgotten:
            # we no longer remember what was paid up to here, so never look back past it
            # (everything forgotten was paid, so it's no newer than last_id)
            ledger["floor"] = max(int(ledger.get("floor", 0)), forgotten)

    def _check_reversals(self, events: list[dict[str, Any]], last_n: Optional[int] = None) -> int:
        recent: dict[str, list] = self.s["ledger"]["recent"]
        if not recent:
            return 0
        keys = sorted(recent, key=int)
        if last_n:
            keys = keys[-last_n:]
        min_id = int(keys[0])
        present = self.source.ids_since(min_id)
        rollover = self._rollover_hour()
        reversed_n = 0
        lost = 0.0
        for k in keys:
            rid = int(k)
            if rid in present:
                continue
            rec = recent.pop(k)
            atp, day, cid, vid, key, hour = rec[:6]
            flag = _rec_flag(rec)
            ds = self.s["days"].get(str(day))
            if day in self.hist:
                self.hist[day] = max(0, self.hist[day] - 1)
            reversed_n += 1
            if flag:
                # it never counted, so there's nothing to take back but the tally
                if ds:
                    rk = NOCOUNT_KEYS[FLAG_WHY[flag]]
                    ds["x"] = max(0, ds.get("x", 0) - 1)
                    ds[rk] = max(0, ds.get(rk, 0) - 1)
                st = self.s["stats"]
                st["uncounted"] = max(0, st.get("uncounted", 0) - 1)
                continue
            self.s["atp"] -= atp
            self.s["atp_run"] = max(0.0, self.s["atp_run"] - atp)
            self.s["atp_all"] = max(0.0, self.s["atp_all"] - atp)
            self.s["xp"] = max(0, self.s["xp"] - 1)
            self.s["answers"] = max(0, self.s["answers"] - 1)
            if ds:
                ds["n"] = max(0, ds["n"] - 1)
                ds["atp"] = max(0.0, ds["atp"] - atp)
                if rollover <= hour < 12:
                    ds["noon"] = max(0, ds["noon"] - 1)
                if self._early(hour, rollover):
                    ds["early"] = max(0, ds["early"] - 1)
            ct = self.s["cards_today"]
            if ct["day"] == day and str(cid) in ct["counts"]:
                ct["counts"][str(cid)] = max(0, ct["counts"][str(cid)] - 1)
            else:
                lk = f"{cid}:{day}"
                if lk in self.s["late_counts"]:
                    self.s["late_counts"][lk] = max(0, self.s["late_counts"][lk] - 1)
            sess = self.s.get("session")
            if sess and rid >= sess["start"]:
                sess["n"] = max(0, sess["n"] - 1)
                sess["atp"] = max(0.0, sess["atp"] - atp)
            if vid:
                before = len(self.s["vesicles"])
                self.s["vesicles"] = [v for v in self.s["vesicles"] if v["id"] != vid]
                if len(self.s["vesicles"]) < before:
                    granted = self.s["granted"]
                    if key in granted["keys"]:
                        granted["keys"].remove(key)
                    if ds:
                        ds["vf"] = max(0, ds["vf"] - 1)
                    if sess and rid >= sess["start"]:
                        sess["vf"] = max(0, sess["vf"] - 1)
            lost += atp
        if reversed_n:
            self._recompute_flow()
            self._recompute_pace()
            self._streak_cache = None
            self.dirty = True
            events.append({"t": "undo", "n": reversed_n, "atp": lost})
        return reversed_n

    def check_undo(self) -> list[dict[str, Any]]:
        """Fast check after Anki's undo: only the latest answers can vanish."""
        events: list[dict[str, Any]] = []
        self._check_reversals(events, last_n=40)
        self._after_changes(self.today(), events)
        return events

    def _recompute_flow(self) -> None:
        recent = self.s["ledger"]["recent"]
        # only answers that counted build flow
        ids = sorted((int(k) for k, rec in recent.items() if not _rec_flag(rec)), reverse=True)
        gap = self.flow_gap()
        flow = self.s["flow"]
        if not ids:
            flow["ts"], flow["n"] = 0, 0
            return
        n = 1
        for a, b in zip(ids, ids[1:]):
            if a - b <= gap:
                n += 1
            else:
                break
        flow["ts"], flow["n"] = ids[0], n

    def _recompute_pace(self) -> None:
        """Rebuild the fair-play pace from the detailed ledger (after an undo)."""
        recent = self.s["ledger"]["recent"]
        pace = self.s["pace"]
        ids = sorted(int(k) for k in recent)
        if not ids:
            pace["ts"], pace["sq"], pace["t"] = 0, 99, []
            return
        pace["ts"] = ids[-1]
        since_quick = 99
        later: Optional[int] = None
        for n, rid in enumerate(reversed(ids)):
            if later is not None and later - rid > STEADY_GAP_MS:
                break
            t = _rec_time(recent[str(rid)])
            if t is not None and t < QUICK_MS:
                since_quick = n
                break
            later = rid
            if n >= 99:
                break
        pace["sq"] = since_quick
        times: list[int] = []
        later = None
        for rid in reversed(ids):
            t = _rec_time(recent[str(rid)])
            if later is not None and later - rid > STEADY_GAP_MS:
                break
            if t is None or t < QUICK_MS or t % 1000 == 0:
                break
            times.append(t)
            later = rid
            if len(times) >= STEADY_RUN - 1:
                break
        pace["t"] = list(reversed(times))

    # ----------------------------------------------------------- daily stuff

    def _roll_day(self, today: int, events: list[dict[str, Any]]) -> None:
        ct = self.s["cards_today"]
        if ct["day"] != today:
            ct["day"] = today
            ct["counts"] = {}
        g = self.s["granted"]
        if g["day"] != today:
            g["day"] = today
            g["keys"] = []
        if self.s["quests"]["day"] != today:
            self.s["quests"] = {"day": today, "list": self._make_quests(today), "bonus": False,
                                "hist": self.hist_loaded}
            self.dirty = True
        if self._today_cache != today:
            self._today_cache = today
            self._streak_cache = None
            cutoff_day = today - DAY_STATS_KEEP
            for k in [k for k in self.s["days"] if int(k) < cutoff_day]:
                del self.s["days"][k]
            sweeps = self.s["sweep_list"]
            if sweeps and sweeps[0] < today - HISTORY_DAYS:
                self.s["sweep_list"] = [d for d in sweeps if d >= today - HISTORY_DAYS]
            late = self.s["late_counts"]
            oldest = today - LATE_WINDOW_MS // DAY_MS - 1
            for k in [k for k in late if int(k.rsplit(":", 1)[1]) < oldest]:
                del late[k]

    def _make_quests(self, day: int) -> list[dict[str, Any]]:
        typical = self.typical_day()
        rng = random.Random(f"{self.s['salt']}:quests:{day}")
        easy = round_nice(max(30, 0.4 * typical))
        medium = round_nice(max(80, 0.9 * typical))
        if medium <= easy:
            medium = round_nice(easy * 2)
        noon_ok = self._rollover_hour() < 10  # a day that starts at 10 or later leaves no morning
        spice_kind = rng.choices(
            ["flow", "noon", "sessions", "vesicles", "sweep"], weights=[3, 2 if noon_ok else 0, 2, 3, 2])[0]
        if spice_kind == "flow":
            target = 30 if typical < 150 else 50 if typical < 400 else 80
        elif spice_kind == "noon":
            target = round_nice(max(20, 0.3 * typical))
        elif spice_kind in ("sessions", "vesicles"):
            target = 2
        else:
            target = 1
        return [
            {"id": f"{day}-easy", "tier": "easy", "kind": "cards", "target": easy, "done": False},
            {"id": f"{day}-medium", "tier": "medium", "kind": "cards", "target": medium, "done": False},
            {"id": f"{day}-spice", "tier": "spice", "kind": spice_kind, "target": target, "done": False},
        ]

    def quest_progress(self, q: dict[str, Any], ds: dict[str, Any]) -> int:
        kind = q["kind"]
        if kind == "cards":
            return ds["n"]
        if kind == "flow":
            return ds["flow"]
        if kind == "noon":
            return ds["noon"]
        if kind == "sessions":
            return ds["sessions"]
        if kind == "vesicles":
            return ds["vf"]
        if kind == "sweep":
            return 1 if ds["sweep"] else 0
        return 0

    @staticmethod
    def quest_label(q: dict[str, Any]) -> str:
        kind, t = q["kind"], q["target"]
        if kind == "cards":
            return f"Answer {t:,} cards"
        if kind == "flow":
            return f"Reach a flow of {t}"
        if kind == "noon":
            return f"Answer {t:,} cards before noon"
        if kind == "sessions":
            return "Study in two separate sessions"
        if kind == "vesicles":
            return f"Find {t} vesicles while reviewing"
        if kind == "sweep":
            return "Finish every due review today"
        return "Mystery quest"

    def _after_changes(self, today: int, events: list[dict[str, Any]]) -> None:
        ds = self._day(today)
        st = self.s["stats"]
        if ds["n"] > st["best_day"]:
            st["best_day"] = ds["n"]
        if ds["early"] > st["early_best"]:
            st["early_best"] = ds["early"]
        goal = self.goal()

        # daily goal reached: pay the knowledge dividend once
        if self.today_count() >= goal and not ds["goal"]:
            ds["goal"] = True
            cards = min(DIVIDEND_MAX_CARDS, self.s["banked"] * DIVIDEND_RATE)
            amount = cards * self.per_card()
            if amount > 0:
                self._gain(amount)
                st["dividends"] += 1
            events.append({"t": "goal", "atp": amount, "banked": self.s["banked"]})
            self.dirty = True

        # weekend warrior: goal on a Sunday after a goal Saturday
        if ds["goal"] and not ds["wk"] and ds["lt"]:
            if self._weekday(ds["lt"]) == 6:
                sat = self.s["days"].get(str(today - 1))
                if (sat and sat.get("goal")) or self.hist.get(today - 1, 0) >= goal:
                    ds["wk"] = True
                    st["weekend_pairs"] += 1

        # comeback: studying again after 3+ empty days
        if ds["n"] > 0 and not ds["cb"]:
            previous = [d for d, n in self.hist.items() if d < today and n > 0]
            if previous and today - max(previous) >= 4:
                ds["cb"] = True
                st["comebacks"] += 1
                events.append({"t": "comeback", "days": today - max(previous) - 1})

        self._check_quests(ds, events)
        self._check_level(events)
        self._check_achievements(events)

    def _check_quests(self, ds: dict[str, Any], events: list[dict[str, Any]]) -> None:
        q = self.s["quests"]
        for quest in q["list"]:
            if quest["done"]:
                continue
            if self.quest_progress(quest, ds) >= quest["target"]:
                quest["done"] = True
                self.s["quests_done"] += 1
                rarity = C.QUEST_REWARD_RARITY[quest["tier"]]
                vid = self._add_vesicle(rarity, self.per_card(), "quest", q["day"])
                bonus = C.QUEST_REWARD_CARDS[quest["tier"]] * self.per_card()
                self._gain(bonus)
                events.append({"t": "quest", "label": self.quest_label(quest), "r": rarity, "id": vid,
                               "atp": bonus})
                self.dirty = True
        if q["list"] and all(x["done"] for x in q["list"]) and not q["bonus"]:
            q["bonus"] = True
            self.s["quest_full_days"] += 1
            vid = self._add_vesicle(C.QUEST_ALL_BONUS_RARITY, self.per_card(), "quests", q["day"])
            events.append({"t": "quests_all", "r": C.QUEST_ALL_BONUS_RARITY, "id": vid})

    def _check_level(self, events: list[dict[str, Any]]) -> None:
        level = self.level_info()[0]
        seen = self.s["level_seen"]
        if level > seen:
            for lv in range(seen + 1, level + 1):
                ev: dict[str, Any] = {"t": "level", "level": lv, "title": C.title_for_level(lv)}
                if lv % 5 == 0:
                    ev["vesicle"] = self._add_vesicle("rare", self.per_card(), "level", self.today())
                unlocked = self._unlock_cosmetics(f"level:{lv}")
                if unlocked:
                    ev["cosmetics"] = unlocked
                events.append(ev)
            self.s["level_seen"] = level
            self.dirty = True

    def derived(self) -> dict[str, Any]:
        st = self.s["stats"]
        streak = self.streak()
        return {
            "opened_game": bool(st["opened_game"]),
            "answers_total": self.s["answers"],
            "best_day": st["best_day"],
            "best_streak": streak["best"],
            "flow_best": self.s["flow"]["best"],
            "purchases": st["purchases"],
            "owned": self.s["owned"],
            "per_card": self.per_card(),
            "atp_all_time": self.s["atp_all"],
            "codex_unique": sum(1 for v in self.s["codex"].values() if v > 0),
            "legendary_enzymes": st["legendary_enzymes"],
            "sets_complete": self.sets_complete(),
            "vesicles_opened": st["opened"],
            "quests_completed": self.s["quests_done"],
            "quest_full_days": self.s["quest_full_days"],
            "early_best": st["early_best"],
            "weekend_pairs": st["weekend_pairs"],
            "comebacks": st["comebacks"],
            "sweeps": st["sweeps"],
            "fissions": self.s["fissions"],
            "pokes": st["pokes"],
        }

    def _check_achievements(self, events: list[dict[str, Any]]) -> None:
        d = self.derived()
        now = self.clock.now_ms()
        for a in C.ACHIEVEMENTS:
            if a.id in self.s["achievements"]:
                continue
            try:
                ok = a.check(d)
            except Exception:
                ok = False
            if ok:
                self.s["achievements"][a.id] = now
                vid = self._add_vesicle(a.tier, self.per_card(), "trophy", self.today())
                ev: dict[str, Any] = {"t": "achievement", "id": a.id, "name": a.name, "r": a.tier, "vid": vid}
                unlocked = self._unlock_cosmetics(f"achievement:{a.id}")
                if unlocked:
                    ev["cosmetics"] = unlocked
                events.append(ev)
                self.dirty = True

    # --------------------------------------------------------------- economy

    def _gain(self, amount: float) -> None:
        self.s["atp"] += amount
        self.s["atp_run"] += amount
        self.s["atp_all"] += amount

    def _add_vesicle(self, rarity: str, per_card: float, src: str, day: int) -> str:
        self.s["vseq"] += 1
        vid = f"v{self.s['vseq']}"
        self.s["vesicles"].append({"id": vid, "r": rarity, "pc": per_card, "src": src, "day": day})
        self.dirty = True
        return vid

    def pathway_unlocked(self, pid: str) -> bool:
        idx = next(i for i, p in enumerate(C.PATHWAYS) if p.id == pid)
        if idx == 0:
            return True
        return self.s["owned"].get(C.PATHWAYS[idx - 1].id, 0) > 0

    def pathway_cost(self, pid: str, qty: int = 1) -> float:
        p = C.PATHWAY_BY_ID[pid]
        n = self.s["owned"].get(pid, 0)
        g = C.COST_GROWTH
        return p.base_cost * growth_pow(n) * (growth_pow(qty) - 1) / (g - 1)

    def pathway_max_affordable(self, pid: str) -> int:
        p = C.PATHWAY_BY_ID[pid]
        n = self.s["owned"].get(pid, 0)
        g = C.COST_GROWTH
        atp = max(0.0, self.s["atp"])
        first = p.base_cost * growth_pow(n)
        if atp < first:
            return 0
        q = int(math.floor(math.log(atp * (g - 1) / first + 1) / math.log(g)))
        while q > 0 and self.pathway_cost(pid, q) > atp + 1e-9:
            q -= 1
        while self.pathway_cost(pid, q + 1) <= atp + 1e-9:  # the estimate can come out one short
            q += 1
        return max(0, q)

    def buy_pathway(self, pid: str, qty: Any = 1) -> dict[str, Any]:
        if pid not in C.PATHWAY_BY_ID:
            return {"ok": False, "error": "Unknown pathway."}
        if not self.pathway_unlocked(pid):
            return {"ok": False, "error": "Buy the pathway before it first."}
        if qty == "max":
            qty = self.pathway_max_affordable(pid)
        qty = int(qty)
        if qty <= 0:
            return {"ok": False, "error": "Not enough ATP yet."}
        cost = self.pathway_cost(pid, qty)
        if cost > self.s["atp"] + 1e-9:
            return {"ok": False, "error": "Not enough ATP yet."}
        self.s["atp"] -= cost
        first = self.s["owned"].get(pid, 0) == 0
        self.s["owned"][pid] = self.s["owned"].get(pid, 0) + qty
        self.s["stats"]["purchases"] += qty
        events: list[dict[str, Any]] = []
        if first:
            unlocked = self._unlock_cosmetics(f"pathway:{pid}")
            if unlocked:
                events.append({"t": "cosmetics", "ids": unlocked})
        self._check_achievements(events)
        self.dirty = True
        return {"ok": True, "qty": qty, "cost": cost, "events": events}

    def upgrade_status(self, u: C.Upgrade) -> str:
        """'owned', 'available', 'locked' (requirement not met)."""
        if u.id in self.s["upgrades"]:
            return "owned"
        if u.kind == "pathway":
            return "available" if self.s["owned"].get(u.pathway or "", 0) >= u.owned_needed else "locked"
        return "available" if self.s["answers"] >= u.answers_needed else "locked"

    def buy_upgrade(self, uid: str) -> dict[str, Any]:
        u = C.UPGRADE_BY_ID.get(uid)
        if not u:
            return {"ok": False, "error": "Unknown upgrade."}
        status = self.upgrade_status(u)
        if status == "owned":
            return {"ok": False, "error": "Already owned."}
        if status == "locked":
            return {"ok": False, "error": "Not unlocked yet."}
        if u.cost > self.s["atp"] + 1e-9:
            return {"ok": False, "error": "Not enough ATP yet."}
        self.s["atp"] -= u.cost
        self.s["upgrades"].append(uid)
        events: list[dict[str, Any]] = []
        self._check_achievements(events)
        self.dirty = True
        return {"ok": True, "cost": u.cost, "events": events}

    # -------------------------------------------------------------- vesicles

    def open_vesicle(self, vid: Optional[str] = None) -> dict[str, Any]:
        vs = self.s["vesicles"]
        if not vs:
            return {"ok": False, "error": "No vesicles to open."}
        v = next((x for x in vs if x["id"] == vid), None) if vid else vs[0]
        if v is None:
            return {"ok": False, "error": "That vesicle is gone."}
        vs.remove(v)
        rng = random.Random(f"{self.s['salt']}:open:{v['id']}")
        r = v["r"]
        pc = max(float(v.get("pc") or 1.0), 1.0)
        lo, hi = C.VESICLE_ATP_CARDS[r]
        mult = 2.0 if "snare" in self.s["upgrades"] else 1.0
        atp = pc * rng.uniform(lo, hi) * mult
        self._gain(atp)
        loot: dict[str, Any] = {"ok": True, "id": v["id"], "r": r, "atp": atp, "items": []}

        if rng.random() < C.ENZYME_CHANCE[r]:
            # any enzyme of this rarity from the sets your level has reached, all equally likely
            unlocked = set(self.unlocked_sets())
            pool = [e for e in C.ENZYMES if e.rarity == r and e.set in unlocked]
            if pool:
                missing = [e for e in pool if not self.s["codex"].get(e.id)] if r == "legendary" else []
                if missing and self.s.get("leg_dupes", 0) >= C.LEGENDARY_PITY:
                    pool = missing  # bad-luck protection
                pick = rng.choice(pool)
                had = self.s["codex"].get(pick.id, 0)
                if r == "legendary":
                    self.s["leg_dupes"] = (self.s.get("leg_dupes", 0) + 1) if (had and missing) else 0
                sets_before = self.sets_complete()
                self.s["codex"][pick.id] = had + 1
                if had:
                    # a duplicate raises the enzyme's expression level and is recycled for ATP
                    bonus = pc * DUP_ENZYME_CARDS[r] * mult
                    self._gain(bonus)
                    level = C.expression_level(had + 1, r)
                    item = {"k": "enzyme", "id": pick.id, "dup": True, "atp": bonus, "lvl": level}
                    if level > C.expression_level(had, r):
                        item["up"] = True
                    loot["items"].append(item)
                else:
                    if r == "legendary":
                        self.s["stats"]["legendary_enzymes"] += 1
                    item = {"k": "enzyme", "id": pick.id, "dup": False}
                    if self.sets_complete() > sets_before:
                        item["set_complete"] = pick.set
                    loot["items"].append(item)

        if rng.random() < C.COSMETIC_CHANCE[r]:
            owned = set(self.s["cosmetics"]["owned"])
            pool = [c for c in C.COSMETICS
                    if c.source == "drop" and c.id not in owned and RARITY_RANK[c.rarity] <= RARITY_RANK[r]]
            if pool:
                same = [c for c in pool if c.rarity == r]
                pick_c = rng.choice(same if same and rng.random() < 0.75 else pool)
                self.s["cosmetics"]["owned"].append(pick_c.id)
                self.s["cosmetics"]["new"].append(pick_c.id)
                loot["items"].append({"k": "cosmetic", "id": pick_c.id})

        if rng.random() < C.FREEZE_CHANCE[r]:
            self.s["loot_freezes"].append(self.today())
            self._streak_cache = None
            loot["items"].append({"k": "freeze"})

        self.s["stats"]["opened"] += 1
        events: list[dict[str, Any]] = []
        self._check_achievements(events)
        loot["events"] = events
        self.dirty = True
        return loot

    # ------------------------------------------------------------- cosmetics

    def _unlock_cosmetics(self, source: str) -> list[str]:
        owned = self.s["cosmetics"]["owned"]
        new = []
        for c in C.COSMETICS:
            if c.source == source and c.id not in owned:
                owned.append(c.id)
                self.s["cosmetics"]["new"].append(c.id)
                new.append(c.id)
        return new

    def equip(self, cosmetic_id: str) -> dict[str, Any]:
        c = C.COSMETIC_BY_ID.get(cosmetic_id)
        if not c or cosmetic_id not in self.s["cosmetics"]["owned"]:
            return {"ok": False, "error": "You don't own that yet."}
        eq = self.s["cosmetics"]["equipped"]
        if eq.get(c.slot) == cosmetic_id and c.slot not in ("skin", "stage"):
            eq.pop(c.slot, None)  # tapping an equipped accessory takes it off
        else:
            eq[c.slot] = cosmetic_id
        if cosmetic_id in self.s["cosmetics"]["new"]:
            self.s["cosmetics"]["new"].remove(cosmetic_id)
        self.dirty = True
        return {"ok": True}

    def clear_new_cosmetics(self) -> None:
        if self.s["cosmetics"]["new"]:
            self.s["cosmetics"]["new"] = []
            self.dirty = True

    # --------------------------------------------------------------- fission

    def fission_gain(self) -> int:
        return max(0, C.mtdna_possible(self.s["atp_all"]) - self.s["mtdna"])

    def fission_worth_it(self) -> bool:
        """Whether to point the player at Fission. A tiny gain isn't worth restarting for."""
        gain = self.fission_gain()
        return gain >= max(C.FISSION_SUGGEST_MIN, math.ceil(C.FISSION_SUGGEST_SHARE * self.s["mtdna"]))

    def fission(self) -> dict[str, Any]:
        gain = self.fission_gain()
        if gain < 1:
            return {"ok": False, "error": "Not enough lifetime ATP to divide yet."}
        self.s["mtdna"] += gain
        self.s["fissions"] += 1
        self.s["atp"] = 0.0
        self.s["atp_run"] = 0.0
        self.s["owned"] = {}
        # Mito's own machinery restarts; your study habits and the cell's upgrades stay
        self.s["upgrades"] = [u for u in self.s["upgrades"]
                              if u in C.UPGRADE_BY_ID and C.UPGRADE_BY_ID[u].kind in C.FISSION_KEEPS]
        events: list[dict[str, Any]] = []
        for n in range(1, self.s["fissions"] + 1):
            unlocked = self._unlock_cosmetics(f"fission:{n}")
            if unlocked:
                events.append({"t": "cosmetics", "ids": unlocked})
        self._check_achievements(events)
        self.dirty = True
        return {"ok": True, "gain": gain, "mtdna": self.s["mtdna"], "events": events}

    # ------------------------------------------------------------------ misc

    def poke(self) -> dict[str, Any]:
        st = self.s["stats"]
        st["pokes"] += 1
        line = C.POKE_LINES[(st["pokes"] * 7 + len(self.s["salt"])) % len(C.POKE_LINES)]
        events: list[dict[str, Any]] = []
        self._check_achievements(events)
        self.dirty = True
        return {"ok": True, "line": line, "events": events}

    def mark_game_opened(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.s["stats"]["opened_game"]:
            self.s["stats"]["opened_game"] = True
            self.dirty = True
        self._check_achievements(events)
        return events

    def give_welcome_pack(self) -> list[str]:
        if self.s["welcome_given"]:
            return []
        self.s["welcome_given"] = True
        pc = self.per_card()
        ids = [self._add_vesicle(r, pc, "welcome", self.today()) for r in ("common", "common", "rare")]
        self.dirty = True
        return ids

    def note_due_counts(self, new: int, learn: int, review: int) -> list[dict[str, Any]]:
        """Called with the whole collection's due counts (from the deck list)."""
        events: list[dict[str, Any]] = []
        today = self.today()
        ds = self._day(today)
        self.s["due_now"] = {"day": today, "learn": int(learn), "review": int(review), "new": int(new)}
        # a clean sweep made mostly of answers that didn't count (mashing, auto-advance) isn't one
        if ds["n"] > 0 and ds["n"] >= ds.get("x", 0) and learn == 0 and review == 0 and not ds["sweep"]:
            ds["sweep"] = True
            self.s["sweep_list"].append(today)
            self.s["stats"]["sweeps"] += 1
            vid = self._add_vesicle("rare", self.per_card(), "sweep", today)
            events.append({"t": "sweep", "id": vid})
            self.dirty = True
        self._after_changes(today, events)
        return events

    # -------------------------------------------------------------- sessions

    def start_session(self) -> None:
        self.s["session"] = {"start": self.clock.now_ms(), "n": 0, "atp": 0.0, "vf": 0, "flow": 0}
        self.dirty = True

    def end_session(self) -> Optional[dict[str, Any]]:
        sess = self.s.get("session")
        self.s["session"] = None
        if sess and sess["n"] > 0:
            sess["end"] = self.clock.now_ms()
            self.s["last_session"] = sess
            self.dirty = True
            return sess
        return None

    # ------------------------------------------------------------- payloads

    def rounds(self) -> dict[str, Any]:
        today = self.today()
        ds = self._day(today)
        due = self.s.get("due_now") or {}
        if due.get("day") != today:
            return {"known": False, "done": ds["n"]}
        remaining = due.get("review", 0) + due.get("learn", 0)
        done = ds["n"] + ds.get("x", 0)  # every real answer, counted or not, is progress through the queue
        total = done + remaining
        return {
            "known": True,
            "done": done,
            "remaining": remaining,
            "new": due.get("new", 0),
            "pct": (done / total) if total else (1.0 if done else 0.0),
            "sweep": ds["sweep"],
        }

    def hud_payload(self, events: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        flow_n = self.current_flow()
        sess = self.s.get("session") or {}
        return {
            "atp": max(0.0, self.s["atp"]),
            "perCard": self.per_card(),
            "flow": flow_n,
            "flowMult": self.flow_multiplier(flow_n),
            "flowCap": self.flow_cap(),
            "vesicles": len(self.s["vesicles"]),
            "sessionN": sess.get("n", 0),
            "sessionAtp": sess.get("atp", 0.0),
            "level": self.level_info()[0],
            "events": events or [],
        }

    def panel_payload(self) -> dict[str, Any]:
        level, into, need = self.level_info()
        today = self.today()
        ds = self._day(today)
        quests = self.s["quests"]["list"]
        return {
            "atp": max(0.0, self.s["atp"]),
            "perCard": self.per_card(),
            "level": level,
            "title": C.title_for_level(level),
            "xpInto": into,
            "xpNeed": need,
            "streak": self.streak(),
            "goal": self.goal(),
            "today": self.today_count(),
            "todayAtp": ds["atp"],
            "vesicles": len(self.s["vesicles"]),
            "quests": [{"label": self.quest_label(q), "done": q["done"],
                        "progress": min(self.quest_progress(q, ds), q["target"]), "target": q["target"]}
                       for q in quests],
            "rounds": self.rounds(),
            "lastSession": self.s.get("last_session"),
            "equipped": self.s["cosmetics"]["equipped"],
            "newCosmetics": len(self.s["cosmetics"]["new"]),
            "fissionGain": self.fission_gain() if self.fission_worth_it() else 0,
        }

    def snapshot(self) -> dict[str, Any]:
        """Everything the game window shows."""
        level, into, need = self.level_info()
        today = self.today()
        ds = self._day(today)
        flow_n = self.current_flow()
        pathways = []
        reveal_next = True
        for p in C.PATHWAYS:
            owned = self.s["owned"].get(p.id, 0)
            unlocked = self.pathway_unlocked(p.id)
            if not unlocked and not reveal_next:
                break
            if not unlocked:
                reveal_next = False
            mult = self.pathway_multiplier(p.id)
            pathways.append({
                "id": p.id,
                "owned": owned,
                "unlocked": unlocked,
                "cost": self.pathway_cost(p.id, 1),
                "cost10": self.pathway_cost(p.id, 10),
                "maxQty": self.pathway_max_affordable(p.id) if unlocked else 0,
                "each": p.base_yield * mult * self.global_multiplier(),
                "total": self.pathway_output(p.id) * self.global_multiplier(),
                "mult": mult,
            })
        upgrades = []
        upcoming = []
        for u in C.UPGRADES:
            status = self.upgrade_status(u)
            if status == "owned":
                upgrades.append({"id": u.id, "status": "owned"})
                continue
            if u.kind == "pathway":
                owned = self.s["owned"].get(u.pathway or "", 0)
                if owned == 0:
                    continue
                if status == "locked" and owned < u.owned_needed // 2:
                    continue
            elif status == "locked":
                upcoming.append(u)
                continue
            upgrades.append({"id": u.id, "status": status})
        upcoming.sort(key=lambda u: u.answers_needed)
        upgrades.extend({"id": u.id, "status": "locked"} for u in upcoming[:4])
        level_progress = into / need if need else 0
        streak = self.streak()
        return {
            "atp": max(0.0, self.s["atp"]),
            "atpRun": self.s["atp_run"],
            "atpAll": self.s["atp_all"],
            "perCard": self.per_card(),
            "baseYield": self.base_yield(),
            "multiplier": self.global_multiplier(),
            "multiplierParts": self.multiplier_parts(),
            "flow": {"n": flow_n, "mult": self.flow_multiplier(flow_n), "cap": self.flow_cap(),
                     "best": self.s["flow"]["best"]},
            "level": {"n": level, "title": C.title_for_level(level), "into": into, "need": need,
                      "pct": level_progress, "nextTitle": next((t for lv, t in C.TITLES if lv > level), None),
                      "nextTitleAt": next((lv for lv, t in C.TITLES if lv > level), None)},
            "answers": self.s["answers"],
            "today": {"n": ds["n"], "count": self.today_count(), "atp": ds["atp"], "goal": self.goal(), "vf": ds["vf"],
                      "flow": ds["flow"], "goalHit": ds["goal"],
                      "x": ds.get("x", 0), "xq": ds.get("xq", 0), "xr": ds.get("xr", 0), "xs": ds.get("xs", 0)},
            "streak": streak,
            "rounds": self.rounds(),
            "dividend": {"banked": self.s["banked"],
                         "cards": min(DIVIDEND_MAX_CARDS, self.s["banked"] * DIVIDEND_RATE),
                         "paid": ds["goal"]},
            "pathways": pathways,
            "upgrades": upgrades,
            "vesicles": [{"id": v["id"], "r": v["r"], "src": v.get("src", "drop")} for v in self.s["vesicles"]],
            "codex": {k: v for k, v in self.s["codex"].items() if v},
            "setsComplete": self.sets_complete(),
            "unlockedSets": self.unlocked_sets(),
            "setUnlockDays": {es.id: int(self.s["install_day"]) + es.unlock_day - today for es in C.ENZYME_SETS},
            "expressionExtra": self.expression_levels_extra(),
            "legendaryNext": self.legendary_guaranteed(),
            "growth": self.growth(),
            "cosmetics": {"owned": list(self.s["cosmetics"]["owned"]),
                          "equipped": dict(self.s["cosmetics"]["equipped"]),
                          "new": list(self.s["cosmetics"]["new"])},
            "achievements": dict(self.s["achievements"]),
            "quests": [{"id": q["id"], "label": self.quest_label(q), "tier": q["tier"], "done": q["done"],
                        "progress": min(self.quest_progress(q, ds), q["target"]), "target": q["target"],
                        "reward": C.QUEST_REWARD_RARITY[q["tier"]]} for q in self.s["quests"]["list"]],
            "questsBonus": self.s["quests"]["bonus"],
            "fission": {"gain": self.fission_gain(), "mtdna": self.s["mtdna"], "fissions": self.s["fissions"],
                        "bonusEach": C.MTDNA_BONUS, "suggest": self.fission_worth_it(),
                        "nextAt": ((C.mtdna_possible(self.s["atp_all"]) + 1) ** 3) * C.FISSION_BASE},
            "stats": dict(self.s["stats"]),
            "lastSession": self.s.get("last_session"),
            "seenIntro": self.s["seen_intro"],
            "installDay": self.s["install_day"],
            "todayIndex": today,
        }


def now_ms() -> int:
    return int(time.time() * 1000)
