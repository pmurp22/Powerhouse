"""Engine tests with a fake clock and an in-memory review log."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

import pytest  # noqa: E402

from engine import content as C  # noqa: E402
from engine.game import DAY_MS, Game, compute_streak, migrate, new_state  # noqa: E402

BASE_CUTOFF = 1_700_006_400_000  # an arbitrary "next day starts at" in ms
HOUR = 3_600_000


class FakeClock:
    def __init__(self) -> None:
        self.now = BASE_CUTOFF - 10 * HOUR  # 6pm-ish of "today" if rollover is 4am
        self.base_today = 1000

    def now_ms(self) -> int:
        return self.now

    def day_cutoff_ms(self) -> int:
        # cutoff moves forward one day for every day elapsed
        days = (self.now - (BASE_CUTOFF - DAY_MS)) // DAY_MS
        return BASE_CUTOFF + days * DAY_MS

    def today(self) -> int:
        days = (self.now - (BASE_CUTOFF - DAY_MS)) // DAY_MS
        return self.base_today + days

    def local_hour(self, ms: int) -> int:
        # pretend the cutoff is 4am local
        return int(((ms - BASE_CUTOFF) % DAY_MS) // HOUR + 4) % 24

    def weekday(self, ms: int) -> int:
        return int(((ms - BASE_CUTOFF) // DAY_MS) % 7)


class FakeRevlog:
    def __init__(self) -> None:
        self.rows: list[tuple[int, int, int, int]] = []

    def add(self, rid: int, cid: int, ease: int = 3, rtype: int = 1, taken=None) -> None:
        self.rows.append((rid, cid, ease, rtype) if taken is None else (rid, cid, ease, rtype, taken))
        self.rows.sort()

    def remove(self, rid: int) -> None:
        self.rows = [r for r in self.rows if r[0] != rid]

    def new_rows(self, after_id: int, limit: int = 50_000):
        out = [r for r in self.rows if r[0] > after_id and 1 <= r[2] <= 4 and r[3] <= 3]
        return out[:limit]

    def ids_since(self, min_id: int):
        return {r[0] for r in self.rows if r[0] >= min_id and 1 <= r[2] <= 4}

    def daily_counts(self, cutoff_ms: int, days: int):
        out: dict[int, int] = {}
        for r in self.rows:
            if r[0] < cutoff_ms and 1 <= r[2] <= 4:
                ago = (cutoff_ms - 1 - r[0]) // DAY_MS
                if ago < days:
                    out[ago] = out.get(ago, 0) + 1
        return out

    def banked_cards(self) -> int:
        return 500

    def max_id(self) -> int:
        return max((r[0] for r in self.rows), default=0)


def make_game(history: int = 0, settings=None) -> tuple[Game, FakeClock, FakeRevlog]:
    clock = FakeClock()
    log = FakeRevlog()
    # optional pre-install history: `history` answers on each of the last 10 days
    for d in range(1, 11):
        for i in range(history):
            log.add(clock.now - d * DAY_MS - i * 1000, 10_000 + i)
    state = new_state(clock.now, clock.today(), log.max_id(), salt="test")
    game = Game(state, clock, log, settings or {"daily_goal": 20})
    game.load_history()
    return game, clock, log


def answer(game: Game, clock: FakeClock, log: FakeRevlog, n: int, cid0: int = 1, ease: int = 3, gap_ms: int = 8000):
    for i in range(n):
        clock.now += gap_ms
        log.add(clock.now, cid0 + i, ease)
    return game.sync()


def test_every_button_pays_the_same():
    results = []
    for ease in (1, 2, 3, 4):
        game, clock, log = make_game()
        answer(game, clock, log, 10, ease=ease)
        results.append(round(game.s["atp_all"], 6))
    assert len(set(results)) == 1
    assert results[0] > 10  # 10 cards with a little flow bonus


def test_history_is_not_paid_out():
    game, clock, log = make_game(history=50)
    game.sync(full=True)
    assert game.s["answers"] == 0
    assert game.s["atp"] == 0


def test_undo_takes_back_exactly_what_was_earned():
    game, clock, log = make_game()
    answer(game, clock, log, 30)
    before_atp = game.s["atp"]
    before_xp = game.s["xp"]
    last = log.rows[-1][0]
    log.remove(last)
    events = game.check_undo()
    assert any(e["t"] == "undo" for e in events)
    assert game.s["xp"] == before_xp - 1
    assert game.s["atp"] < before_atp
    # answering again re-earns
    clock.now += 5000
    log.add(clock.now, 999, 3)
    game.sync()
    assert game.s["xp"] == before_xp


def test_undo_reanswer_cannot_reroll_a_vesicle():
    game, clock, log = make_game()
    # answer many distinct cards until a vesicle drops
    cid = 1
    dropped = None
    while dropped is None and cid < 400:
        clock.now += 5000
        log.add(clock.now, cid, 3)
        events = game.sync()
        dropped = next((e for e in events if e["t"] == "vesicle"), None)
        cid += 1
    assert dropped is not None
    count = len(game.s["vesicles"])
    last_id, last_cid = log.rows[-1][0], log.rows[-1][1]
    log.remove(last_id)
    game.check_undo()
    assert len(game.s["vesicles"]) == count - 1  # unopened vesicle taken back
    clock.now += 5000
    log.add(clock.now, last_cid, 1)  # same card, same day, different button
    events = game.sync()
    assert any(e["t"] == "vesicle" for e in events)  # same deterministic result
    assert len(game.s["vesicles"]) == count


def test_late_synced_reviews_count_once():
    game, clock, log = make_game()
    answer(game, clock, log, 10)
    # phone reviews from two hours ago arrive after the desktop ones
    for i in range(5):
        log.add(clock.now - 2 * HOUR + i * 1000, 5000 + i)
    game.sync()  # fast path ignores older ids
    assert game.s["answers"] == 10
    game.sync(full=True)
    assert game.s["answers"] == 15
    game.sync(full=True)
    assert game.s["answers"] == 15


def test_streak_with_freezes():
    install = 100
    counts = {d: 50 for d in range(80, 107)}  # 27 days in a row ending day 106
    counts.pop(104)  # a missed day after install
    info = compute_streak(counts, 20, today=107, install_day=install)
    # days 80..103 = 24 days, freeze earned at 7-multiples after install (day 104 streak 25? no)
    # streak hits 21 on day 100 (>= install) -> earns a freeze, used on 104
    assert info["current"] == 26
    assert 104 in info["frozen_days"]
    info2 = compute_streak(counts, 20, today=107, install_day=200)  # no freezes before install
    assert info2["current"] == 2


def test_streak_today_pending_does_not_break():
    counts = {d: 30 for d in range(10, 20)}
    info = compute_streak(counts, 20, today=20, install_day=0)
    assert info["current"] == 10 and info["at_risk"]
    counts[20] = 25
    info = compute_streak(counts, 20, today=20, install_day=0)
    assert info["current"] == 11 and info["today_done"]


def test_buying_and_costs():
    game, clock, log = make_game()
    game.s["atp"] = 1000.0
    assert game.buy_pathway("pdh")["ok"] is False  # glycolysis first
    r = game.buy_pathway("glycolysis", 1)
    assert r["ok"] and game.s["owned"]["glycolysis"] == 1
    assert game.pathway_cost("glycolysis", 1) == pytest.approx(15 * 1.15)
    q = game.pathway_max_affordable("glycolysis")
    cost = game.pathway_cost("glycolysis", q)
    assert cost <= game.s["atp"] < game.pathway_cost("glycolysis", q + 1)
    r = game.buy_pathway("glycolysis", "max")
    assert r["ok"] and r["qty"] == q
    assert game.per_card() > 1.0


def test_upgrades_unlock_and_apply():
    game, clock, log = make_game()
    game.s["atp"] = 1e9
    game.buy_pathway("glycolysis", 10)
    out_before = game.pathway_output("glycolysis")
    assert game.buy_upgrade("glycolysis_10")["ok"]
    assert game.pathway_output("glycolysis") == pytest.approx(out_before * 2)
    assert game.buy_upgrade("coffee")["ok"] is False  # needs 150 answers
    game.s["answers"] = 200
    game._check_achievements([])  # settle trophies that 200 answers unlock (+1% each)
    pc = game.per_card()
    assert game.buy_upgrade("coffee")["ok"]
    assert game.per_card() == pytest.approx(pc * 1.1)


def test_vesicle_opening_is_deterministic_and_fills_codex():
    game, clock, log = make_game()
    ids = game.give_welcome_pack()
    assert len(ids) == 3 and game.give_welcome_pack() == []
    import copy
    snap = copy.deepcopy(game.s)
    loot1 = game.open_vesicle(ids[0])
    game.s = snap
    loot2 = game.open_vesicle(ids[0])
    assert loot1["atp"] == loot2["atp"] and loot1["items"] == loot2["items"]
    assert game.s["stats"]["opened"] == 1
    # at level 1 only the first set turns up
    for _ in range(40):
        game._add_vesicle("legendary", 100.0, "test", game.today())
        game.open_vesicle()
    found = {e for e, n in game.s["codex"].items() if n}
    assert found and all(C.ENZYME_BY_ID[e].set == "sugar" for e in found)
    # at level 25 every set is open (once enough days have passed), and enough legendaries find them all
    game.s["xp"] = sum(C.xp_for_next(lv) for lv in range(1, 25))
    assert game.level_info()[0] == 25 and game.unlocked_sets() == ["sugar"]  # day 0: the day minimums still apply
    game.s["install_day"] -= 90
    assert len(game.unlocked_sets()) == len(C.ENZYME_SETS)
    for _ in range(300):
        game._add_vesicle("legendary", 100.0, "test", game.today())
        game.open_vesicle()
    legendaries = [e.id for e in C.ENZYMES if e.rarity == "legendary"]
    assert all(game.s["codex"].get(e, 0) > 0 for e in legendaries)


def test_quests_complete_and_reward():
    game, clock, log = make_game(history=100)
    game.sync()
    quests = game.s["quests"]["list"]
    assert len(quests) == 3
    easy = quests[0]["target"]
    events = answer(game, clock, log, easy)
    assert any(e["t"] == "quest" for e in events)
    assert quests[0]["done"]


def test_daily_goal_pays_dividend_once():
    game, clock, log = make_game()
    events = answer(game, clock, log, 25)
    goals = [e for e in events if e["t"] == "goal"]
    assert len(goals) == 1 and goals[0]["atp"] > 0
    events = answer(game, clock, log, 5)
    assert not any(e["t"] == "goal" for e in events)


def test_level_up_and_achievements():
    game, clock, log = make_game()
    events = answer(game, clock, log, 120, gap_ms=4000)
    kinds = {e["t"] for e in events}
    assert "level" in kinds
    assert "first_rep" in game.s["achievements"]
    assert "warm_up" in game.s["achievements"]
    assert game.s["flow"]["best"] >= 100


def test_flow_resets_after_long_break():
    game, clock, log = make_game()
    answer(game, clock, log, 20)
    assert game.s["flow"]["n"] == 20
    clock.now += 10 * 60 * 1000
    answer(game, clock, log, 1, cid0=900)
    assert game.s["flow"]["n"] == 1


def test_day_rollover_new_quests():
    game, clock, log = make_game()
    game.sync()
    day1 = game.s["quests"]["day"]
    clock.now += DAY_MS
    game.sync()
    assert game.s["quests"]["day"] == day1 + 1


def test_fission_resets_run_but_keeps_progress():
    game, clock, log = make_game()
    game.s["atp_all"] = C.FISSION_BASE * 8.5  # cube root ~2.04 -> 2 mtDNA
    game.s["atp"] = 5e9
    game.s["owned"] = {"glycolysis": 50}
    game.s["upgrades"] = ["glycolysis_10", "glycolysis_25", "coffee", "sleep", "clathrin", "flow1"]
    game.s["achievements"]["first_rep"] = 1
    r = game.fission()
    assert r["ok"] and r["gain"] == 2
    assert game.s["owned"] == {} and game.s["atp"] == 0
    # Mito's pathway boosts restart; study habits, vesicle machinery and flow upgrades stay
    assert game.s["upgrades"] == ["coffee", "sleep", "clathrin", "flow1"]
    assert game.growth() == 0.0
    assert "first_rep" in game.s["achievements"]
    assert "skin_galaxy" in game.s["cosmetics"]["owned"]
    assert game.fission()["ok"] is False


def test_sweep_detection_idempotent():
    game, clock, log = make_game()
    answer(game, clock, log, 5)
    e1 = game.note_due_counts(10, 0, 0)
    e2 = game.note_due_counts(10, 0, 0)
    assert any(e["t"] == "sweep" for e in e1)
    assert not any(e["t"] == "sweep" for e in e2)


def test_migrate_fills_new_keys():
    game, clock, log = make_game()
    old = dict(game.s)
    del old["stats"]["dividends"]
    del old["pity"]
    fresh = new_state(clock.now, clock.today(), 0, salt="x")
    m = migrate(old, fresh)
    assert m["pity"] == 0 and m["stats"]["dividends"] == 0
    assert m["salt"] == "test"


def test_snapshot_and_payloads_are_json_safe():
    import json
    game, clock, log = make_game(history=30)
    answer(game, clock, log, 40)
    game.give_welcome_pack()
    json.dumps(game.snapshot())
    json.dumps(game.panel_payload())
    json.dumps(game.hud_payload())


def test_history_refresh_keeps_answers_processed_meanwhile():
    game, clock, log = make_game(history=40)
    # answers processed, then a history query that ran *before* them lands
    stale_counts = log.daily_counts(clock.day_cutoff_ms(), 800)
    stale_max = log.max_id()
    answer(game, clock, log, 7)
    game.apply_history(stale_counts, 100, stale_max)
    assert game.hist.get(game.today(), 0) == 7


def test_quests_redrawn_once_history_arrives():
    clock = FakeClock()
    log = FakeRevlog()
    for d in range(1, 15):
        for i in range(600):
            log.add(clock.now - d * DAY_MS - i * 1000, 20_000 + i)
    state = new_state(clock.now, clock.today(), log.max_id(), salt="q")
    game = Game(state, clock, log, {"daily_goal": 50})
    game.sync()  # quests drawn with the 150-card default
    before = game.s["quests"]["list"][1]["target"]
    game.load_history()  # typical day is 600 now
    after = game.s["quests"]["list"][1]["target"]
    assert after > before


def test_opening_vesicle_after_undo_keeps_it():
    game, clock, log = make_game()
    cid = 1
    while not game.s["vesicles"] and cid < 500:
        clock.now += 5000
        log.add(clock.now, cid, 3)
        game.sync()
        cid += 1
    vid = game.s["vesicles"][0]["id"]
    loot = game.open_vesicle(vid)
    assert loot["ok"]
    # undoing the answer that dropped it can't take back an opened vesicle
    log.remove(log.rows[-1][0])
    game.check_undo()
    assert game.s["stats"]["opened"] == 1
    assert game.s["atp"] > 0


def test_poke_does_not_make_atp():
    game, clock, log = make_game()
    before = game.s["atp"]
    for _ in range(60):
        game.poke()
    assert game.s["atp"] == before
    assert "poke_50" in game.s["achievements"]


def test_pacing_month_one_is_not_the_whole_game():
    """The real engine, a 250-card/day student, 30 days: plenty happens, but the codex,
    wardrobe and pathway list are nowhere near done (tools/pacing_report.py has the full picture)."""
    import importlib
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    sim = importlib.import_module("longsim")
    st = sim.Student(250, 1, row_len=5)
    st.run(30)
    m = st.milestones
    end = st.timeline[-1]
    assert m["buy:krebs"] <= 5 and m["buy:synthase"] <= 20  # early pathways come quickly
    assert "buy:creatine" not in m and "first fission" not in m
    assert 12 <= end["enzymes"] <= 32  # a good start on 48
    assert end["sets"] <= 3 and "all drop cosmetics" not in m
    assert end["level"] >= 10


def test_redo_is_credited_on_next_sync():
    game, clock, log = make_game()
    answer(game, clock, log, 5)
    last = log.rows[-1]
    log.remove(last[0])
    game.check_undo()
    assert game.s["answers"] == 4
    log.add(*last)  # redo puts the same row back
    answer(game, clock, log, 1, cid0=777)
    assert game.s["answers"] == 6
    game.sync()
    assert game.s["answers"] == 6  # no double counting


def _study_days(game, clock, log, days, per_day, cid_base=0):
    for day in range(days):
        answer(game, clock, log, per_day, cid0=cid_base + day * 1000)
        game.sync(full=True)
        clock.now += DAY_MS - per_day * 8000


def test_clean_sweep_days_keep_counting_after_the_day_stats_are_trimmed():
    """A below-goal day saved by a clean sweep still counts once its per-day stats are gone (120 days)."""
    game, clock, log = make_game()  # goal 20
    _study_days(game, clock, log, 1, 20)
    answer(game, clock, log, 5, cid0=5000)
    game.sync(full=True)
    assert any(e["t"] == "sweep" for e in game.note_due_counts(0, 0, 0))
    sweep_day = game.today()
    clock.now += DAY_MS - 5 * 8000
    _study_days(game, clock, log, 129, 20, cid_base=10_000)
    game.sync(full=True)
    assert str(sweep_day) not in game.s["days"]  # the detailed stats for that day are long gone
    st = game.streak()
    assert st["current"] == 131 and st["frozen_days"] == []
    # saves from before sweeps were kept separately pick them up from the day stats they still have
    old = dict(game.s)
    old.pop("sweep_list")
    old["days"] = dict(old["days"])
    recent = max(int(k) for k in old["days"])
    old["days"][str(recent)] = dict(old["days"][str(recent)], sweep=True)
    assert migrate(old, new_state(0, game.today(), 0, "x"))["sweep_list"] == [recent]


def test_week_old_phone_reviews_still_count_once():
    game, clock, log = make_game()
    start = clock.now
    _study_days(game, clock, log, 8, 60)
    paid = game.s["answers"]
    assert paid == 480
    assert game.s["ledger"]["old"]  # older answers left the detailed ledger
    # phone reviews from about a week ago finally sync
    for i in range(40):
        log.add(start + DAY_MS + 3 * HOUR + i * 7000 + 1, 90_000 + i)
    game.sync()
    assert game.s["answers"] == paid  # the quick path after an answer only looks back 15 minutes
    game.sync(full=True)
    assert game.s["answers"] == paid + 40
    for _ in range(3):
        game.sync(full=True)
        game.sync()
    assert game.s["answers"] == paid + 40


def test_month_of_play_keeps_save_small_and_never_repays():
    import json as _json

    game, clock, log = make_game()
    _study_days(game, clock, log, 40, 300)
    assert game.s["answers"] == 12_000
    size = len(_json.dumps(game.s, separators=(",", ":")))
    assert size < 600_000, size
    # the computer's clock jumps back ten days (wrong system time): nothing is paid twice
    clock.now -= 10 * DAY_MS
    game.sync(full=True)
    clock.now += 10 * DAY_MS
    game.sync(full=True)
    assert game.s["answers"] == 12_000


def test_save_from_previous_version_does_not_repay_history():
    game, clock, log = make_game()
    _study_days(game, clock, log, 8, 30)
    paid = game.s["answers"]
    s = game.s
    # what the previous version saved: no floor/old, details only for the last four days
    del s["ledger"]["floor"]
    del s["ledger"]["old"]
    horizon = clock.now - 4 * DAY_MS
    s["ledger"]["recent"] = {k: v for k, v in s["ledger"]["recent"].items() if int(k) >= horizon}
    fresh = new_state(clock.now, clock.today(), log.max_id(), salt="x")
    g2 = Game(migrate(s, fresh), clock, log, {"daily_goal": 20})
    g2.load_history()
    g2.sync(full=True)
    assert g2.s["answers"] == paid
    assert g2.s["ledger"]["floor"] >= horizon - DAY_MS


def test_fmt_number_matches_the_web_formatter():
    from engine.game import fmt_number

    cases = {0: "0", 0.5: "0.50", 1: "1", 5.25: "5.3", 9.96: "10", 12: "12", 9999: "9,999", 10_000: "10K",
             12_345: "12.3K", 999_499: "999K", 999_500: "1M", 1_234_567: "1.23M", 2.5e9: "2.5B", -1500: "−1,500",
             10_250: "10.3K", 100_500: "101K", 0.125: "0.13"}  # ties round up, like JavaScript
    for n, want in cases.items():
        assert fmt_number(n) == want, (n, fmt_number(n), want)


def test_freeze_shows_up_the_day_the_streak_hits_seven():
    counts = {d: 30 for d in range(10, 16)}  # six days done
    info = compute_streak(counts, 20, today=16, install_day=10)
    assert info["current"] == 6 and info["freezes"] == 0
    counts[16] = 30  # day seven done today
    info = compute_streak(counts, 20, today=16, install_day=10)
    assert info["current"] == 7 and info["freezes"] == 1
    # next day, not studied yet: still one freeze; the day after a miss, it's been used
    info = compute_streak(counts, 20, today=17, install_day=10)
    assert info["current"] == 7 and info["freezes"] == 1 and info["at_risk"]
    counts[18] = 30
    info = compute_streak(counts, 20, today=18, install_day=10)
    assert info["current"] == 8 and info["freezes"] == 0 and 17 in info["frozen_days"]


# --- found by an independent review -------------------------------------------------------


def test_long_break_then_phone_sync_pays_everything():
    for desktop_answers in (40, 60):  # below and above the size where old details get archived
        game, clock, log = make_game()
        answer(game, clock, log, desktop_answers)
        last_id = game.s["ledger"]["last_id"]
        clock.now += 60 * DAY_MS  # two months of phone-only studying
        game.sync()  # the profile opens before Anki's auto-sync
        for d in range(1, 60):
            for i in range(20):
                log.add(last_id + d * DAY_MS + i * 5000, 50_000 + d * 100 + i)
        before = game.s["answers"]
        game.sync(full=True)  # after the sync
        assert game.s["answers"] - before == 59 * 20


def test_clock_set_a_year_ahead_then_fixed():
    game, clock, log = make_game()
    answer(game, clock, log, 60)
    real = clock.now
    clock.now += 400 * DAY_MS  # wrong system date when Anki opens
    game.sync()
    clock.now = real
    before = game.s["answers"]
    answer(game, clock, log, 30, cid0=7000)
    game.sync(full=True)
    assert game.s["answers"] - before == 30


def test_previous_version_save_after_a_break_pays_phone_reviews():
    game, clock, log = make_game()
    answer(game, clock, log, 30)
    s = game.s
    last_id = s["ledger"]["last_id"]
    del s["ledger"]["floor"]
    del s["ledger"]["old"]
    clock.now += 10 * DAY_MS
    fresh = new_state(clock.now, clock.today(), log.max_id(), salt="x")
    g2 = Game(migrate(s, fresh), clock, log, {"daily_goal": 20})
    g2.load_history()
    g2.sync()
    for d in range(1, 10):
        for i in range(20):
            log.add(last_id + d * DAY_MS + i * 5000, 80_000 + d * 100 + i)
    before = g2.s["answers"]
    g2.sync(full=True)
    assert g2.s["answers"] - before == 9 * 20


def test_row_stamped_in_the_future_does_not_stall_answers():
    game, clock, log = make_game()
    answer(game, clock, log, 5)
    log.add(clock.now + 6 * HOUR, 4242)  # a phone with the wrong time syncs in
    game.sync(full=True)
    before = game.s["answers"]
    for i in range(10):
        clock.now += 8000
        log.add(clock.now, 9000 + i)
        game.sync()  # what runs after each answer
    assert game.s["answers"] == before + 10
    assert game.current_flow() >= 10


def test_heavy_user_full_sync_pages_through_the_window():
    clock = FakeClock()
    log = FakeRevlog()
    game = Game(new_state(clock.now, clock.today(), 0, salt="t"), clock, log, {"daily_goal": 20})
    game.row_page = 500  # small pages keep the test quick
    game.load_history()
    for d in range(29):
        for i in range(200):
            clock.now += 20_000
            log.add(clock.now, d * 10_000 + i)
        game.sync()
        clock.now += DAY_MS - 200 * 20_000
    paid = game.s["answers"]
    assert paid == 29 * 200
    for i in range(50):  # phone reviews from 3 hours ago arrive late
        log.add(clock.now - 3 * HOUR + i * 1000 + 1, 900_000 + i)
    game.sync(full=True)
    assert game.s["answers"] == paid + 50


def test_damaged_review_row_is_paid_once_and_the_game_keeps_going():
    from datetime import datetime

    class StrictClock(FakeClock):  # like the real clock: odd timestamps raise
        def local_hour(self, ms):
            return datetime.fromtimestamp(ms / 1000).hour

        def weekday(self, ms):
            return datetime.fromtimestamp(ms / 1000).weekday()

    clock = StrictClock()
    log = FakeRevlog()
    game = Game(new_state(clock.now, clock.today(), 0, salt="t"), clock, log, {"daily_goal": 20})
    answer(game, clock, log, 3)
    log.add(1_700_000_000_000_000, 77)  # stamped in microseconds by mistake
    for _ in range(5):
        game.sync()
        game.sync(full=True)
    assert game.s["answers"] in (3, 4)
    clock.now += 8000
    log.add(clock.now, 78)
    events = game.sync()
    assert any(e["t"] == "answers" for e in events)


def test_partial_history_refresh_keeps_older_days():
    game, clock, log = make_game(history=30)
    today = game.today()
    assert game.hist[today - 5] == 30 and game.hist[today - 9] == 30
    # late phone reviews land on a day 5 days ago (recent) and 9 days ago (older than the partial window)
    for i in range(4):
        log.add(clock.now - 5 * DAY_MS + 3_600_000 + i * 1000, 70_000 + i)
        log.add(clock.now - 9 * DAY_MS + 3_600_000 + i * 1000, 71_000 + i)
    cutoff = clock.day_cutoff_ms()
    game.apply_history(log.daily_counts(cutoff, 7), 500, log.max_id(), partial_days=7)
    assert game.hist[today - 5] == 34  # recounted
    assert game.hist[today - 9] == 30  # kept from the last full count until the next one
    game.apply_history(log.daily_counts(cutoff, 800), 500, log.max_id())
    assert game.hist[today - 9] == 34


# ------------------------------------------------------------------ fair play


def timed(game, clock, log, times, cid0=1, gap_ms=None, same_card=False):
    """Answer one card per entry in `times` (ms taken); the clock moves on by that much."""
    for i, t in enumerate(times):
        clock.now += gap_ms if gap_ms is not None else max(t, 1) + 400
        log.add(clock.now, cid0 if same_card else cid0 + i, 3, 1, t)
    return game.sync()


def test_one_quick_answer_counts_but_mashing_does_not():
    game, clock, log = make_game()
    timed(game, clock, log, [6000, 700, 6000, 6000, 6000, 6000, 650])  # two quick ones, far apart
    assert game.s["answers"] == 7
    ev = timed(game, clock, log, [400] * 10, cid0=100)  # mashing
    ds = game._day(game.today())
    assert game.s["answers"] == 7  # the first mashed one comes 1 answer after a quick one
    assert ds["x"] == 10 and ds["xq"] == 10
    assert any(e["t"] == "nocount" and e["quick"] == 10 for e in ev)
    # interleaving slow and quick answers doesn't help
    timed(game, clock, log, [5000, 400] * 6, cid0=200)
    assert game.s["answers"] == 7 + 6  # only the slow ones


def test_quick_rule_resets_after_a_break():
    game, clock, log = make_game()
    timed(game, clock, log, [400, 400])
    assert game.s["answers"] == 1
    clock.now += 10 * 60 * 1000
    timed(game, clock, log, [400], cid0=50)
    assert game.s["answers"] == 2


def test_uncounted_answers_pay_nothing_and_do_not_build_the_goal():
    game, clock, log = make_game(settings={"daily_goal": 10})
    timed(game, clock, log, [300] * 30)
    assert game.s["answers"] == 1
    assert game.s["xp"] == 1
    assert game.today_count() == 1
    assert not game.streak()["today_done"]
    assert not game._day(game.today())["goal"]
    snap = game.snapshot()
    assert snap["today"]["x"] == 29 and snap["today"]["count"] == 1


def test_a_card_counts_four_times_a_day():
    game, clock, log = make_game()
    timed(game, clock, log, [5000] * 6, same_card=True)
    ds = game._day(game.today())
    assert game.s["answers"] == 4 and ds["xr"] == 2
    clock.now += DAY_MS
    timed(game, clock, log, [5000] * 2, same_card=True)
    assert game.s["answers"] == 6


def test_auto_advance_rhythm_does_not_count_but_capped_times_do():
    game, clock, log = make_game()
    bot = [3004, 3011, 3007, 3002, 3015, 3009, 3006, 3012, 3003, 3010]
    timed(game, clock, log, bot)
    ds = game._day(game.today())
    assert game.s["answers"] == 5 and ds["xs"] == 5
    # a human breaks the rhythm
    timed(game, clock, log, [7400, 2900, 12000], cid0=100)
    assert game.s["answers"] == 8
    # slow answers all capped at Anki's 60-second limit look identical, and still count
    game2, clock2, log2 = make_game()
    timed(game2, clock2, log2, [60000] * 10)
    assert game2.s["answers"] == 10


def test_bulk_graded_rows_do_not_count():
    """Browse > Grade Now writes many rows with no answer time, milliseconds apart."""
    game, clock, log = make_game()
    timed(game, clock, log, [0] * 200, gap_ms=1)
    assert game.s["answers"] == 1


def test_undo_of_an_uncounted_answer():
    game, clock, log = make_game()
    timed(game, clock, log, [5000, 5000, 400, 400])
    ds = game._day(game.today())
    assert game.s["answers"] == 3 and ds["x"] == 1
    atp = game.s["atp"]
    log.remove(log.rows[-1][0])
    ev = game.check_undo()
    assert ds["x"] == 0 and game.s["answers"] == 3 and game.s["atp"] == atp
    assert any(e["t"] == "undo" and e["atp"] == 0 for e in ev)
    # after undoing it, the pace is rebuilt: the last answer (quick) is now the one before
    timed(game, clock, log, [400], cid0=90)
    assert game.s["answers"] == 3


def test_reviews_that_sync_late_still_follow_the_card_limit():
    game, clock, log = make_game()
    yesterday = clock.now - DAY_MS
    for i in range(7):
        log.add(yesterday + i * 6000, 777, 1, 1, 5000)
    game.sync(full=True)
    assert game.s["answers"] == 4
    assert game.s["days"][str(game.today() - 1)]["xr"] == 3


def test_clean_sweep_keeps_the_streak():
    game, clock, log = make_game(history=30, settings={"daily_goal": 50})
    assert game.streak()["current"] == 0  # 30 a day never met a goal of 50
    answer(game, clock, log, 12)
    game.note_due_counts(5, 0, 0)  # every due review done
    st = game.streak()
    assert st["today_done"] and st["current"] == 1
    clock.now += DAY_MS
    game.sync()
    answer(game, clock, log, 3, cid0=500)
    st = game.streak()
    assert st["current"] == 1 and st["at_risk"]  # yesterday's sweep still counts


def test_pomodoro_lets_flow_wait_out_a_five_minute_break():
    game, clock, log = make_game()
    answer(game, clock, log, 5)
    clock.now += 5 * 60 * 1000
    answer(game, clock, log, 1, cid0=50)
    assert game.s["flow"]["n"] == 1
    game.s["upgrades"].append("pomodoro")
    answer(game, clock, log, 3, cid0=60)
    clock.now += 5 * 60 * 1000
    answer(game, clock, log, 1, cid0=70)
    assert game.s["flow"]["n"] == 5


def test_duplicates_raise_expression_levels():
    assert [C.expression_level(n, "common") for n in (0, 1, 2, 3, 6, 12, 20, 99)] == [0, 1, 1, 2, 3, 4, 5, 5]
    assert [C.expression_level(n, "legendary") for n in (0, 1, 2, 3, 4, 6)] == [0, 1, 2, 3, 4, 5]
    game, clock, log = make_game()
    base = game.global_multiplier()
    game.s["codex"]["pfk1"] = 4  # a legendary at level 4: three levels above 1
    game.s["codex"]["hexokinase"] = 3  # a common at level 2
    assert game.expression_levels_extra() == 4
    assert game.global_multiplier() == pytest.approx(base * (1 + 4 * C.EXPRESSION_BONUS))
    # a duplicate from a vesicle reports its new level
    game.s["codex"] = {e.id: 1 for e in C.ENZYMES if e.set == "sugar"}
    ups = []
    for _ in range(80):
        game._add_vesicle("common", 1.0, "test", game.today())
        loot = game.open_vesicle()
        ups += [it for it in loot["items"] if it["k"] == "enzyme" and it.get("up")]
    assert ups and all(it["dup"] and it["lvl"] >= 2 for it in ups)


def test_legendary_bad_luck_protection():
    """Never more than LEGENDARY_PITY duplicate legendaries in a row while one you're missing can drop."""
    game, clock, log = make_game()
    game.s["xp"] = sum(C.xp_for_next(lv) for lv in range(1, 25))
    game.s["install_day"] -= 90
    legendaries = [e.id for e in C.ENZYMES if e.rarity == "legendary"]
    assert C.LEGENDARY_PITY == 2
    run, worst, drops = 0, 0, 0
    for _ in range(400):
        if all(game.s["codex"].get(e) for e in legendaries):
            break
        missing_before = [e for e in legendaries if not game.s["codex"].get(e)]
        loot = game.open_vesicle(game._add_vesicle("legendary", 1.0, "test", game.today()))
        for it in loot["items"]:
            if it["k"] == "enzyme":
                drops += 1
                run = run + 1 if it["dup"] else 0
                worst = max(worst, run)
                if not it["dup"]:
                    assert it["id"] in missing_before
    assert all(game.s["codex"].get(e) for e in legendaries)
    assert worst <= C.LEGENDARY_PITY and game.s["leg_dupes"] <= C.LEGENDARY_PITY
    # once you have them all, duplicates keep coming (they raise expression) and the count stays at 0
    for _ in range(30):
        game.open_vesicle(game._add_vesicle("legendary", 1.0, "test", game.today()))
    assert game.s["leg_dupes"] == 0 and not game.snapshot()["legendaryNext"]
    # the codex says so when the protection is about to kick in
    fresh, clock2, log2 = make_game()
    fresh.s["codex"]["pfk1"] = 3
    fresh.s["leg_dupes"] = C.LEGENDARY_PITY
    assert not fresh.legendary_guaranteed()  # level 1: the only legendary you can find is one you have
    fresh.s["xp"] = sum(C.xp_for_next(lv) for lv in range(1, 5))
    fresh.s["install_day"] -= 7
    assert fresh.legendary_guaranteed() and fresh.snapshot()["legendaryNext"]
    loot = fresh.open_vesicle(fresh._add_vesicle("legendary", 1.0, "test", fresh.today()))
    got = [it for it in loot["items"] if it["k"] == "enzyme"]
    assert not got or (got[0]["id"] == "glycogen_phosphorylase" and not got[0]["dup"])
    # older saves without the counter still load
    old = dict(game.s)
    old.pop("leg_dupes")
    assert "leg_dupes" in migrate(old, new_state(0, game.today(), 0, "x"))


def test_every_legendary_is_rate_limiting_and_sets_unlock_with_titles():
    legend = {e.set: e.name for e in C.ENZYMES if e.rarity == "legendary"}
    assert legend == {"sugar": "PFK-1", "storage": "Glycogen phosphorylase", "mito": "Isocitrate dehydrogenase",
                      "lipid": "HMG-CoA reductase", "nitrogen": "Carbamoyl phosphate synthetase I",
                      "amines": "ALA synthase"}
    titles = [C.title_for_level(es.unlock_level) for es in C.ENZYME_SETS]
    assert titles == ["Pre-med", "MS1", "MS2", "Step 1 survivor", "MS3", "MS4"]


def test_fission_is_only_suggested_when_worth_it():
    game, clock, log = make_game()
    game.s["atp_all"] = C.FISSION_BASE * 1.5  # one copy possible
    assert game.fission_gain() == 1 and not game.fission_worth_it()
    assert game.panel_payload()["fissionGain"] == 0 and game.snapshot()["fission"]["gain"] == 1
    game.s["atp_all"] = C.FISSION_BASE * 27  # three copies
    assert game.fission_worth_it()


def test_a_sweep_made_of_uncounted_answers_is_not_a_sweep():
    """Mashing through every due card empties the queue, but that's not a clean sweep."""
    game, clock, log = make_game(settings={"daily_goal": 500})
    timed(game, clock, log, [400] * 200)  # 1 counts, 199 don't
    ev = game.note_due_counts(0, 0, 0)
    ds = game._day(game.today())
    assert not ds["sweep"] and not any(e["t"] == "sweep" for e in ev)
    assert not game.streak()["today_done"]
    # honest answers afterwards make it a real one
    timed(game, clock, log, [5000] * 210, cid0=1000)
    game.note_due_counts(0, 0, 0)
    assert game._day(game.today())["sweep"] and game.streak()["today_done"]


def test_vesicles_thin_out_over_a_big_day_and_freezes_are_rare():
    assert [Game.drop_weight(n) for n in (1, 150, 151, 500, 501, 1000, 1001, 2500)] == \
        [1.0, 1.0, 0.5, 0.5, 0.25, 0.25, 0.125, 0.125]
    game, clock, log = make_game()
    timed(game, clock, log, [5000] * 2000)
    drops = game._day(game.today())["vf"]
    # about 150/40 + 350/80 + 500/160 + 1000/320 ≈ 14 rather than 2000/40 = 50
    assert 8 <= drops <= 22
    assert C.FREEZE_CHANCE["common"] == C.FREEZE_CHANCE["rare"] == C.FREEZE_CHANCE["epic"] == 0
    assert "day_2000" in C.ACHIEVEMENT_BY_ID


def test_enzyme_sets_wait_for_days_on_heavy_schedules():
    game, clock, log = make_game()
    game.s["xp"] = sum(C.xp_for_next(lv) for lv in range(1, 30))  # a huge first week
    assert game.unlocked_sets() == ["sugar"]
    game.s["install_day"] -= 21
    assert game.unlocked_sets() == ["sugar", "storage", "mito"]
    assert game.snapshot()["setUnlockDays"]["lipid"] == 14


def test_mito_grows_with_his_pathways():
    game, clock, log = make_game()
    assert game.growth() == 0.0
    game.s["owned"] = {"glycolysis": 10, "pdh": 10, "krebs": 10, "etc": 10, "synthase": 10}
    g1 = game.growth()
    game.s["owned"]["betaox"] = 50
    assert 0 < g1 < game.growth() <= 1.0
    game.s["owned"]["biogenesis"] = 500
    assert game.growth() == 1.0


# --------------------------------------------------------------------------- release review fixes


def test_new_game_on_an_empty_profile_never_pays_old_history():
    """A brand-new profile is empty until its first full sync. Games start at the current
    time (what the add-on passes to new_state), so the history that sync brings never pays."""
    clock, log = FakeClock(), FakeRevlog()
    game = Game(new_state(clock.now, clock.today(), clock.now, salt="empty"), clock, log, {"daily_goal": 20})
    game.load_history()
    for i in range(3000):  # years of reviews from before Powerhouse, arriving with the sync
        log.add(clock.now - 300 * DAY_MS + i * 50_000, 10_000 + i % 400)
    game.load_history()
    game.sync(full=True)
    assert game.s["answers"] == 0 and game.s["atp"] == 0 and game.s["xp"] == 0
    # the history still shows in the streak and best day, and those trophies come with their vesicles
    assert all(v["src"] == "trophy" for v in game.s["vesicles"])
    answer(game, clock, log, 3, cid0=90_000)
    assert game.s["answers"] == 3
    # the replaced collection counts days from its own start, so "today" jumps
    clock.base_today = 1500
    game.reanchor_install_day()
    assert game.s["install_day"] == game.today()
    clock.now += 3 * DAY_MS
    game.reanchor_install_day()
    assert game.today() - game.s["install_day"] == 3


class LateClock(FakeClock):
    """Anki's "next day starts at" set to 10 a.m."""

    def local_hour(self, ms: int) -> int:
        return int(((ms - BASE_CUTOFF) % DAY_MS) // HOUR + 10) % 24


def test_a_late_day_start_still_allows_every_quest_and_early_bird():
    clock, log = LateClock(), FakeRevlog()
    game = Game(new_state(clock.now, clock.today(), 0, salt="late"), clock, log, {"daily_goal": 20})
    game.load_history()
    assert game._rollover_hour() == 10
    kinds = {q["kind"] for d in range(300) for q in game._make_quests(1000 + d)}
    assert "noon" not in kinds and {"flow", "sessions", "vesicles", "sweep"} <= kinds  # no morning to answer in
    clock.now += 5 * HOUR  # 5 a.m., before the 10 a.m. day start
    assert clock.local_hour(clock.now) == 5
    answer(game, clock, log, 3)
    assert game._day(game.today())["early"] == 3
    # with the usual 4 a.m. start, the window is still 4 to 8 a.m.
    assert Game._early(5, 4) and not Game._early(9, 4) and not Game._early(2, 4) and Game._early(2, 0)


def test_history_counts_use_the_day_they_were_counted_on():
    """A count that started just before rollover and finished after it must not shift a day."""
    game, clock, log = make_game()
    today = game.today()
    game.apply_history({0: 30, 1: 25}, 500, 0, counted_on=today - 1)
    assert game.hist.get(today - 1) == 30 and game.hist.get(today - 2) == 25 and today not in game.hist


def test_a_renamed_profile_finds_its_save(tmp_path):
    from saves import find_orphan_save

    def write(name, **extra):
        data = {"salt": "s", "ledger": {"last_id": 0, "recent": {}}}
        data.update(extra)
        (tmp_path / name).write_text(__import__("json").dumps(data))
        return str(tmp_path / name)

    old = write("User_1.json", col_crt=111)
    other = write("Other.json", col_crt=222)
    current = write("Pat.json", col_crt=111)
    write("User_1.json.bak", col_crt=111)
    never = lambda ids: False  # noqa: E731
    # "User 1" was renamed to "Pat": its save is nobody's now and belongs to this collection
    assert find_orphan_save(str(tmp_path), [current, other], 111, never) == old
    assert find_orphan_save(str(tmp_path), [current, other, old], 111, never) is None
    assert find_orphan_save(str(tmp_path), [current], 333, never) is None
    # a save from before the collection mark: matched by reviews this collection still has
    legacy = write("Old_name.json", ledger={"last_id": 77, "recent": {"75": [], "76": []}})
    assert find_orphan_save(str(tmp_path), [current, other, old], 999, lambda ids: 76 in ids) == legacy
    assert find_orphan_save(str(tmp_path), [current, other, old], 999, never) is None


def test_the_newest_review_bookmark_ignores_reviews_stamped_in_the_future():
    import sqlite3

    from anki_bridge import AnkiRevlog

    class DB:
        def __init__(self):
            self.c = sqlite3.connect(":memory:")
            self.c.execute("create table revlog (id integer primary key, cid, ease, type, time)")

        def scalar(self, sql, *args):
            row = self.c.execute(sql, args).fetchone()
            return row[0] if row else None

    class Col:
        db = DB()

    now = 1_700_000_000_000
    for rid in (now - 5000, now - 1000, now + 400 * DAY_MS):  # the last from a phone set to next year
        Col.db.c.execute("insert into revlog values (?, 1, 3, 1, 4000)", (rid,))
    src = AnkiRevlog(lambda: Col)
    assert src.max_id() == now + 400 * DAY_MS
    assert src.max_id(before=now) == now - 1000
    assert src.has_any([1, now - 5000]) and not src.has_any([1, 2]) and not src.has_any([])


def test_a_review_stamped_in_the_future_doesnt_freeze_todays_count():
    """The history bookmark comes from reviews before today's cutoff (what the add-on asks
    for), so a phone with its clock set to next year can't stall today's answers."""
    game, clock, log = make_game()
    answer(game, clock, log, 3)
    log.add(clock.now + 400 * DAY_MS, 4242)  # a review from a device whose clock is wrong
    capped = max(r[0] for r in log.rows if r[0] < clock.day_cutoff_ms())
    game.apply_history(log.daily_counts(clock.day_cutoff_ms(), 45), 500, capped)
    before = game.today_count()
    answer(game, clock, log, 5, cid0=500)
    assert game.today_count() == before + 5
