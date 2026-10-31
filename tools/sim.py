"""Economy simulator for tuning Powerhouse's numbers.

Models a student answering N cards a day and buying greedily (best ATP-per-card
gain per ATP spent). Prints when each pathway first gets bought, per-card yield
over time, level, and when Fission becomes available.

Usage: python tools/sim.py [cards_per_day] [days]
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

from engine import content as C  # noqa: E402

PER_DAY = 500
DAYS = 120
CHUNK = 50  # buy decisions every 50 cards
rng = random.Random(7)


class Sim:
    def __init__(self) -> None:
        self.atp = 0.0
        self.all_time = 0.0
        self.owned = {p.id: 0 for p in C.PATHWAYS}
        self.ups: set[str] = set()
        self.answers = 0
        self.xp = 0
        self.achievements = 0
        self.mtdna = 0
        self.sets = 0
        self.first_buy: dict[str, int] = {}
        self.habit_day: dict[str, int] = {}

    def level(self) -> int:
        return C.level_from_xp(self.xp)[0]

    def pathway_mult(self, pid: str) -> float:
        n = sum(1 for u in C.UPGRADES if u.kind == "pathway" and u.pathway == pid and u.id in self.ups)
        return 2.0 ** n

    def base(self) -> float:
        return 1 + sum(self.owned[p.id] * p.base_yield * self.pathway_mult(p.id) for p in C.PATHWAYS)

    def global_mult(self) -> float:
        m = 1.0
        for u in C.HABIT_UPGRADES:
            if u.id in self.ups:
                m *= u.factor
        m *= 1 + C.LEVEL_ATP_BONUS * (self.level() - 1)
        m *= 1 + C.ACHIEVEMENT_ATP_BONUS * self.achievements
        m *= 1 + C.MTDNA_BONUS * self.mtdna
        m *= 1 + C.SET_BONUS * self.sets
        return m

    def per_card(self) -> float:
        return self.base() * self.global_mult()

    def cost(self, pid: str) -> float:
        p = C.PATHWAY_BY_ID[pid]
        return p.base_cost * C.COST_GROWTH ** self.owned[pid]

    def options(self):
        pc = self.per_card()
        gm = self.global_mult()
        out = []
        for p in C.PATHWAYS:
            idx = C.PATHWAYS.index(p)
            if idx > 0 and self.owned[C.PATHWAYS[idx - 1].id] == 0:
                continue
            gain = p.base_yield * self.pathway_mult(p.id) * gm
            out.append((gain / self.cost(p.id), self.cost(p.id), ("p", p.id)))
        for u in C.UPGRADES:
            if u.id in self.ups:
                continue
            if u.kind == "pathway":
                if self.owned[u.pathway] < u.owned_needed:
                    continue
                p = C.PATHWAY_BY_ID[u.pathway]
                gain = self.owned[p.id] * p.base_yield * self.pathway_mult(p.id) * gm
            elif u.kind == "habit":
                if self.answers < u.answers_needed:
                    continue
                gain = pc * (u.factor - 1)
            else:
                continue
            out.append((gain / u.cost, u.cost, ("u", u.id)))
        out.sort(reverse=True)
        return out

    def shop(self, day: int) -> None:
        for _ in range(500):
            opts = self.options()
            bought = False
            for ratio, cost, (kind, ident) in opts[:3]:
                if cost <= self.atp:
                    self.atp -= cost
                    if kind == "p":
                        self.owned[ident] += 1
                        self.first_buy.setdefault(ident, day)
                    else:
                        self.ups.add(ident)
                        if C.UPGRADE_BY_ID[ident].kind == "habit":
                            self.habit_day.setdefault(ident, day)
                    bought = True
                    break
            if not bought:
                return

    def earn(self, cards: int) -> None:
        pc = self.per_card()
        flow = 1.25  # average flow bonus
        atp = cards * pc * flow
        # vesicles ~1/32 cards, average bundle ~45 cards' worth
        atp += cards / 32 * 45 * pc
        self.atp += atp
        self.all_time += atp
        self.answers += cards
        self.xp += cards


def main() -> None:
    global PER_DAY, DAYS
    if len(sys.argv) > 1:
        PER_DAY = int(sys.argv[1])
    if len(sys.argv) > 2:
        DAYS = int(sys.argv[2])
    s = Sim()
    fission_day = None
    print(f"Simulating {PER_DAY} cards/day for {DAYS} days")
    for day in range(1, DAYS + 1):
        n = max(50, int(rng.gauss(PER_DAY, PER_DAY * 0.25)))
        done = 0
        while done < n:
            chunk = min(CHUNK, n - done)
            s.earn(chunk)
            done += chunk
            s.shop(day)
        # quests + dividend
        pc = s.per_card()
        s.atp += 150 * pc
        banked = min(s.answers * 0.35, 30000)
        s.atp += banked * 0.01 * pc
        s.all_time += 150 * pc + banked * 0.01 * pc
        # achievements trickle in roughly logarithmically
        s.achievements = min(40, int(3 + 4 * math.log1p(s.answers / 300)))
        s.sets = min(6, s.answers // 15000)
        if fission_day is None and C.mtdna_possible(s.all_time) >= 1:
            fission_day = day
        if day in (1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 120, 180, 240, 365) or day == DAYS:
            lvl = s.level()
            owned = ", ".join(f"{k}:{v}" for k, v in s.owned.items() if v)
            print(f"day {day:>3} | answers {s.answers:>7} | lvl {lvl:>3} {C.title_for_level(lvl):<16}"
                  f"| per card {pc:>12.4g} | bank {s.atp:>10.3g} | all {s.all_time:>10.3g} | {owned}")
    print("first buys:", s.first_buy)
    print("habits:", s.habit_day)
    print("fission available on day:", fission_day, "mtDNA possible at end:", C.mtdna_possible(s.all_time))


if __name__ == "__main__":
    main()
