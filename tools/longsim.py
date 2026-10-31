"""Long-run pacing simulator that drives the real engine (engine/game.py).

A simulated student answers cards in two sessions a day for months. After every
session they open the game, open every vesicle, buy greedily, and divide
(Fission) when it's worth it. The script prints a timeline: level, ATP per card,
enzymes, sets, cosmetics, trophies, and the day each milestone was first reached.

Usage: python tools/longsim.py [cards_per_day] [days] [seed] [--json out.json] [--mash 0.0]
"""

from __future__ import annotations

import bisect
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

from engine import content as C  # noqa: E402
from engine import game as G  # noqa: E402

DAY = G.DAY_MS
HOUR = 3_600_000
START_CUTOFF = 1_767_247_200_000  # a 4 a.m. day cutoff


class Clock:
    def __init__(self) -> None:
        self.now = START_CUTOFF - DAY + 5 * HOUR  # 9 a.m. on day 0
        self.base_today = 2000

    def _days(self) -> int:
        return (self.now - (START_CUTOFF - DAY)) // DAY

    def now_ms(self) -> int:
        return self.now

    def today(self) -> int:
        return self.base_today + self._days()

    def day_cutoff_ms(self) -> int:
        return START_CUTOFF + self._days() * DAY

    def local_hour(self, ms: int) -> int:
        return int(((ms - START_CUTOFF) % DAY) // HOUR + 4) % 24

    def weekday(self, ms: int) -> int:
        return int(((ms - START_CUTOFF) // DAY) % 7)


class Revlog:
    """Sorted, append-mostly review log with O(log n) queries."""

    def __init__(self) -> None:
        self.ids: list[int] = []
        self.rows: list[tuple] = []
        self.by_day: dict[int, int] = {}  # cutoff-relative day index -> count
        self.banked = 1240

    def add(self, row: tuple) -> None:
        rid = row[0]
        i = bisect.bisect_left(self.ids, rid)
        if i < len(self.ids) and self.ids[i] == rid:
            return
        self.ids.insert(i, rid)
        self.rows.insert(i, row)
        k = (rid - START_CUTOFF) // DAY
        self.by_day[k] = self.by_day.get(k, 0) + 1

    def new_rows(self, after_id: int, limit: int = 50_000):
        i = bisect.bisect_right(self.ids, after_id)
        return self.rows[i:i + limit]

    def ids_since(self, min_id: int):
        i = bisect.bisect_left(self.ids, min_id)
        return set(self.ids[i:])

    def daily_counts(self, cutoff_ms: int, days: int):
        top = (cutoff_ms - START_CUTOFF) // DAY  # index of the day that ends at cutoff_ms
        out = {}
        for k, n in self.by_day.items():
            ago = top - 1 - k
            if 0 <= ago < days:
                out[ago] = n
        return out

    def banked_cards(self) -> int:
        return self.banked

    def max_id(self) -> int:
        return self.ids[-1] if self.ids else 0


class Student:
    def __init__(self, per_day: int, seed: int, mash: float = 0.0, row_len: int = 4) -> None:
        self.rng = random.Random(seed)
        self.per_day = per_day
        self.mash = mash  # share of answers that are mashed (well under a second)
        self.row_len = row_len
        self.clock = Clock()
        self.log = Revlog()
        self.next_card = 1
        self.pool: list[int] = []  # cards the student has seen
        # two weeks of history before installing
        for d in range(14, 0, -1):
            self._history_day(d)
        state = G.new_state(self.clock.now, self.clock.today(), self.log.max_id(), salt=f"sim{seed}")
        self.game = G.Game(state, self.clock, self.log, {"daily_goal": 100})
        self.game.load_history()
        # count where vesicles come from
        self.sources: dict[str, int] = {}
        orig = self.game._add_vesicle

        def counted(rarity, pc, src, day, _orig=orig):
            self.sources[f"{src}:{rarity}"] = self.sources.get(f"{src}:{rarity}", 0) + 1
            return _orig(rarity, pc, src, day)
        self.game._add_vesicle = counted
        self.milestones: dict[str, int] = {}
        self.timeline: list[dict] = []
        self.opened_once = False
        self.last_fission_day = -99

    # ---------------------------------------------------------------- cards
    def _pick_cards(self, n: int) -> list[int]:
        cards = []
        new_n = max(0, int(n * 0.12))
        for _ in range(new_n):
            cards.append(self.next_card)
            self.pool.append(self.next_card)
            self.next_card += 1
        while len(cards) < n:
            if self.pool:
                cards.append(self.rng.choice(self.pool))
            else:
                cards.append(self.next_card)
                self.pool.append(self.next_card)
                self.next_card += 1
        return cards

    def _history_day(self, days_ago: int) -> None:
        base = self.clock.now - days_ago * DAY
        for i, cid in enumerate(self._pick_cards(self.per_day)):
            self.log.add(self._row(base + i * 7000, cid, 7000))

    def _row(self, rid: int, cid: int, taken: int) -> tuple:
        ease = self.rng.choices([1, 2, 3, 4], weights=[12, 5, 78, 5])[0]
        row = (rid, cid, ease, 1, taken)
        return row[: self.row_len]

    # ------------------------------------------------------------- sessions
    def session(self, n: int, start_hour: float) -> None:
        g = self.game
        day_start = self.clock.day_cutoff_ms() - DAY  # 4 a.m.
        self.clock.now = max(self.clock.now, int(day_start + (start_hour - 4) * HOUR))
        g.start_session()
        cards = self._pick_cards(n)
        # some cards come back once or twice (learning steps)
        extra = []
        for cid in cards:
            r = self.rng.random()
            if r < 0.12:
                extra.append(cid)
            if r < 0.04:
                extra.append(cid)
        order = cards + extra
        since = 0
        for cid in order:
            mashed = self.rng.random() < self.mash
            gap = self.rng.randint(350, 800) if mashed else int(min(60_000, max(1500, self.rng.lognormvariate(math.log(6500), 0.55))))
            if not mashed and self.rng.random() < 0.01:
                gap += self.rng.randint(60_000, 240_000)  # short distraction
            self.clock.now += gap
            self.log.add(self._row(self.clock.now, cid, min(gap, 60_000)))
            since += 1
            if since >= 20:
                g.sync()
                since = 0
        g.sync(full=True)
        g.end_session()

    def play(self, day: int) -> None:
        g = self.game
        if not self.opened_once:
            g.mark_game_opened()
            g.give_welcome_pack()
            g.s["seen_intro"] = True
            self.opened_once = True
        g.sync(full=True)
        # open every vesicle
        while g.s["vesicles"]:
            g.open_vesicle(g.s["vesicles"][0]["id"])
        self.shop()
        # divide when it's clearly worth it (at most weekly)
        # divide when the game suggests it (at most weekly)
        if g.fission_worth_it() and day - self.last_fission_day >= 7:
            g.fission()
            self.last_fission_day = day
            self.shop()
        g.sync(full=True)

    def _gain_of(self, kind: str, ident: str) -> tuple[float, float]:
        g = self.game
        gm = g.global_multiplier()
        pc = g.per_card()
        if kind == "p":
            p = C.PATHWAY_BY_ID[ident]
            return p.base_yield * g.pathway_multiplier(ident) * gm, g.pathway_cost(ident, 1)
        u = C.UPGRADE_BY_ID[ident]
        if u.kind == "pathway":
            return g.pathway_output(u.pathway) * gm, u.cost
        if u.kind == "habit":
            return pc * (u.factor - 1), u.cost
        if u.kind == "vesicle":
            return pc * (0.25 if ident != "snare" else 1.2), u.cost
        if u.kind == "flow":
            return pc * 0.08, u.cost
        return 0.0, u.cost

    def shop(self) -> None:
        g = self.game
        for _ in range(3000):
            opts = []
            for p in C.PATHWAYS:
                if g.pathway_unlocked(p.id):
                    gain, cost = self._gain_of("p", p.id)
                    opts.append((gain / cost, cost, "p", p.id))
            for u in C.UPGRADES:
                if g.upgrade_status(u) == "available":
                    gain, cost = self._gain_of("u", u.id)
                    opts.append((gain / cost if cost else 1e9, cost, "u", u.id))
            opts.sort(reverse=True)
            bought = False
            for ratio, cost, kind, ident in opts[:3]:
                if cost <= g.s["atp"]:
                    r = g.buy_pathway(ident, 1) if kind == "p" else g.buy_upgrade(ident)
                    if r.get("ok"):
                        if kind == "p":
                            self.mark(f"buy:{ident}")
                        bought = True
                        break
            if not bought:
                return

    # ------------------------------------------------------------ tracking
    def mark(self, key: str) -> None:
        if key not in self.milestones:
            self.milestones[key] = self.day

    def track(self) -> None:
        g = self.game
        s = g.s
        codex = s["codex"]
        by_r = {r: 0 for r in C.RARITIES}
        for e in C.ENZYMES:
            if codex.get(e.id, 0) > 0:
                by_r[e.rarity] += 1
        uniq = sum(by_r.values())
        sets = g.sets_complete()
        for k in (1, 10, 24, 36, 42, len(C.ENZYMES)):
            if uniq >= k:
                self.mark(f"enzymes>={k}")
        for k in range(1, len(C.ENZYME_SETS) + 1):
            if sets >= k:
                self.mark(f"sets>={k}")
        if by_r["legendary"] >= 1:
            self.mark("first legendary")
        drops = [c for c in C.COSMETICS if c.source == "drop"]
        owned_drops = sum(1 for c in drops if c.id in s["cosmetics"]["owned"])
        if owned_drops == len(drops):
            self.mark("all drop cosmetics")
        level = g.level_info()[0]
        for lv, title in C.TITLES:
            if level >= lv:
                self.mark(f"title:{title}")
        if s["fissions"] >= 1:
            self.mark("first fission")
        habits = [u for u in C.HABIT_UPGRADES]
        if all(u.id in s["upgrades"] for u in habits):
            self.mark("all habits")
        self.timeline.append({
            "day": self.day, "answers": s["answers"], "level": level, "title": C.title_for_level(level),
            "per_card": g.per_card(), "atp_all": s["atp_all"], "enzymes": uniq, "by_rarity": dict(by_r),
            "sets": sets, "cosmetics": len(s["cosmetics"]["owned"]), "trophies": len(s["achievements"]),
            "fissions": s["fissions"], "mtdna": s["mtdna"], "opened": s["stats"]["opened"],
            "top_pathway": max((i for i, p in enumerate(C.PATHWAYS) if s["owned"].get(p.id, 0)), default=-1),
            "streak": g.streak()["current"], "uncounted": s["stats"].get("uncounted", 0),
            "atp_bank": s["atp"], "base_yield": g.base_yield(), "growth": g.growth(),
            "freezes": g.streak()["freezes"], "vesicles_today": g._day(g.today() - 1)["vf"] if False else None,
        })

    def run(self, days: int, sweep_rate: float = 0.5, off_every: int = 14) -> None:
        for day in range(1, days + 1):
            self.day = day
            g = self.game
            # history refresh as on profile open
            g.load_history()
            off = off_every and day % off_every == 0
            if not off:
                n = max(40, int(self.rng.gauss(self.per_day, self.per_day * 0.2)))
                am = int(n * 0.4)
                self.session(am, 8.5 + self.rng.random())
                self.play(day)
                self.session(n - am, 19 + self.rng.random() * 1.5)
                if self.rng.random() < sweep_rate:
                    g.note_due_counts(20, 0, 0)
                else:
                    g.note_due_counts(20, 0, 15)
                self.play(day)
                self.log.banked += self.rng.randint(4, 12)
            self.track()
            # next morning
            self.clock.now = self.clock.day_cutoff_ms() + 5 * HOUR


def main() -> None:
    args = [a for a in sys.argv[1:]]
    out_json = None
    mash = 0.0
    if "--json" in args:
        i = args.index("--json")
        out_json = args[i + 1]
        del args[i:i + 2]
    if "--mash" in args:
        i = args.index("--mash")
        mash = float(args[i + 1])
        del args[i:i + 2]
    per_day = int(args[0]) if args else 250
    days = int(args[1]) if len(args) > 1 else 365
    seed = int(args[2]) if len(args) > 2 else 1
    row_len = 5 if getattr(G, "ROW_HAS_TIME", False) else 4
    st = Student(per_day, seed, mash=mash, row_len=row_len)
    st.run(days)
    show = {1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 300, 365, 450, 540, 630, 730}
    print(f"{per_day} cards/day, {days} days, seed {seed}")
    print(" day  answers lvl title              per_card   enz (c/r/e/l)   sets cos troph fis top  opened   atp_all   base  grow frz")
    for t in st.timeline:
        if t["day"] in show or t["day"] == days:
            br = t["by_rarity"]
            print(f"{t['day']:>4} {t['answers']:>8} {t['level']:>3} {t['title']:<18} {t['per_card']:>9.3g}"
                  f"  {t['enzymes']:>2} ({br['common']}/{br['rare']}/{br['epic']}/{br['legendary']})"
                  f"  {t['sets']:>4} {t['cosmetics']:>3} {t['trophies']:>5} {t['fissions']:>3} {t['top_pathway']:>3}"
                  f"  {t['opened']:>6} {t['atp_all']:>9.3g} {t['base_yield']:>7.3g} {t['growth']:>4.2f} {t['freezes']:>3}")
    print("milestones:")
    for k, v in sorted(st.milestones.items(), key=lambda kv: kv[1]):
        print(f"  day {v:>4}: {k}")
    tot = sum(st.sources.values())
    by_src: dict[str, int] = {}
    for k, v in st.sources.items():
        by_src[k.split(":")[0]] = by_src.get(k.split(":")[0], 0) + v
    print(f"vesicles: {tot} total, {tot / days:.1f}/day;", ", ".join(f"{k} {v}" for k, v in sorted(by_src.items(), key=lambda kv: -kv[1])))
    by_r: dict[str, int] = {}
    for k, v in st.sources.items():
        by_r[k.split(":")[1]] = by_r.get(k.split(":")[1], 0) + v
    print("  by rarity:", ", ".join(f"{r} {by_r.get(r, 0)}" for r in C.RARITIES), f"| uncounted answers {st.game.s['stats'].get('uncounted', 0)}")
    if out_json:
        Path(out_json).write_text(json.dumps({"timeline": st.timeline, "milestones": st.milestones}))


if __name__ == "__main__":
    main()
