"""Powerhouse controller: wires the game engine into Anki.

Compatibility rules this file follows on purpose:
* Only hooks are used (never monkey-patching), so other add-ons keep working.
* Nothing is ever written to your collection: progress lives in user_files/.
* Every hook is wrapped so an error here can never interrupt a review.
* Messages from web pages are only claimed when they start with "powerhouse:".
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
import time
import traceback
from datetime import date
from typing import Any, Callable, Optional

from aqt import gui_hooks, mw
from aqt.qt import QAction, QTimer, qconnect
from aqt.utils import tooltip

from .anki_bridge import AnkiClock, AnkiRevlog
from .engine import content as C
from .engine.game import HISTORY_DAYS, RECENT_HISTORY_DAYS, Game, fmt_number, migrate, new_state
from .saves import find_orphan_save

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.join(ADDON_DIR, "user_files")
SAVE_DIR = os.path.join(USER_DIR, "saves")
LOG_PATH = os.path.join(USER_DIR, "powerhouse.log")

DEFAULT_SETTINGS: dict[str, Any] = {
    "daily_goal": 100,
    "hud": True,
    "hud_position": "bar",
    "hud_toasts": True,
    "deck_panel": True,
    "deck_panel_compact": False,
    "toolbar_button": True,
    "sounds": True,
    "reduce_motion": False,
}
HUD_POSITIONS = ("bar", "top-right", "top-left", "bottom-left")
PAUSED_NOTE = ("Powerhouse couldn't open its save file (another program seems to be using it), "
               "so it's paused until you restart Anki. Your progress is safe.")


# ---------------------------------------------------------------------------
# logging & safety
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    try:
        os.makedirs(USER_DIR, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 256_000:
            shutil.move(LOG_PATH, LOG_PATH + ".old")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def safe(default: Any = None) -> Callable:
    """Never let an exception escape into Anki. Log it instead."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:
                log(f"error in {fn.__name__}:\n{traceback.format_exc()}")
                if callable(default):
                    return default(*args, **kwargs)
                return default

        return wrapper

    return deco


def _passthrough_first(*args: Any, **kwargs: Any) -> Any:
    return args[1] if len(args) > 1 else (args[0] if args else None)


# ---------------------------------------------------------------------------
# the controller
# ---------------------------------------------------------------------------


class Powerhouse:
    def __init__(self) -> None:
        self.game: Optional[Game] = None
        self.window: Any = None
        self.profile: Optional[str] = None
        self.last_tab = "pathways"
        self.pkg = mw.addonManager.addonFromModule(__name__)
        self.web_base = f"/_addons/{self.pkg}/web"
        self._sync_timer = QTimer(mw)
        self._sync_timer.setSingleShot(True)
        qconnect(self._sync_timer.timeout, self._sync_after_answer)
        self._save_timer = QTimer(mw)
        self._save_timer.setInterval(15_000)
        qconnect(self._save_timer.timeout, self._autosave)
        self._window_push_timer = QTimer(mw)
        self._window_push_timer.setSingleShot(True)
        qconnect(self._window_push_timer.timeout, self._push_window)
        self._pending_window_events: list[dict[str, Any]] = []
        self._history_running = False
        self._history_again: Optional[dict[str, bool]] = None
        self._history_day: Optional[int] = None
        self._sync_seen = False
        self._main_ok = True
        self._paused = False  # the save file couldn't be opened this session
        self._static: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------ settings

    def settings(self) -> dict[str, Any]:
        try:
            cfg = mw.addonManager.getConfig(__name__) or {}
        except Exception:
            cfg = {}
        out = dict(DEFAULT_SETTINGS)
        for k, v in cfg.items():
            if k in DEFAULT_SETTINGS:
                out[k] = v
        try:
            out["daily_goal"] = max(1, min(5000, int(out["daily_goal"])))
        except (TypeError, ValueError):
            out["daily_goal"] = DEFAULT_SETTINGS["daily_goal"]
        if out["hud_position"] not in HUD_POSITIONS:
            out["hud_position"] = "bar"
        for k in ("hud", "hud_toasts", "deck_panel", "deck_panel_compact", "toolbar_button", "sounds",
                  "reduce_motion"):
            out[k] = bool(out[k])
        return out

    def write_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        cur = self.settings()
        for k, v in patch.items():
            if k in DEFAULT_SETTINGS:
                cur[k] = v
        try:
            cfg = mw.addonManager.getConfig(__name__) or {}
        except Exception:
            cfg = {}
        cfg.update(cur)
        mw.addonManager.writeConfig(__name__, cfg)
        new = self.settings()
        if self.game:
            self.game.settings.update(new)
            self.game._streak_cache = None
        return new

    def client_settings(self) -> dict[str, Any]:
        s = self.settings()
        s["last_tab"] = self.last_tab
        return s

    # ---------------------------------------------------------- lifecycle

    def setup(self) -> None:
        os.makedirs(SAVE_DIR, exist_ok=True)
        readme = os.path.join(USER_DIR, "README.txt")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Powerhouse keeps your game saves here. Anki leaves this folder alone when the add-on updates.\n")
        mw.addonManager.setWebExports(__name__, r"web/.*\.(js|css|woff2|svg|png)$")
        mw.addonManager.setConfigAction(__name__, self.open_settings)

        for name, fn in (
            ("profile_did_open", self.on_profile_open),
            ("profile_will_close", self.on_profile_close),
            ("reviewer_did_answer_card", self.on_answer),
            ("state_did_undo", self.on_undo),
            ("state_did_change", self.on_state_change),
            ("sync_will_start", self.on_sync_start),
            ("sync_did_finish", self.on_sync_finished),
            ("collection_did_temporarily_close", self.on_collection_reloaded),  # after a full sync download
            ("collection_did_load", self.on_collection_reloaded),  # after a .colpkg import
            ("day_did_change", self.on_day_change),  # Anki 25.09+; a timer covers older versions
            ("deck_browser_will_render_content", self.on_deck_browser),
            ("webview_will_set_content", self.on_webview_content),
            ("webview_did_receive_js_message", self.on_js_message),
            ("top_toolbar_did_init_links", self.on_toolbar_links),
        ):
            hook = getattr(gui_hooks, name, None)
            if hook is not None:
                hook.append(fn)
            else:
                log(f"hook {name} not available in this Anki version")
        self._last_day: Optional[int] = None
        self._day_timer: Any = None  # started on the first profile open (see _start_day_timer)

        action = QAction("Powerhouse", mw)
        qconnect(action.triggered, self.open_window)
        mw.form.menuTools.addAction(action)

    @staticmethod
    def _legacy_save_name(profile: str) -> str:
        return (re.sub(r"[^A-Za-z0-9_.-]+", "_", profile) or "profile") + ".json"

    def _save_path(self, profile: str) -> str:
        """One save file per profile. A name that had to be changed to be a safe file name
        gets a short fingerprint, so two profiles can never share a file (before, "Иван" and
        "Мария" would both have become "_.json")."""
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", profile) or "profile"
        if safe_name != profile:
            safe_name += "-" + hashlib.sha1(profile.encode("utf-8")).hexdigest()[:8]
        return os.path.join(SAVE_DIR, f"{safe_name}.json")

    @safe()
    def on_profile_open(self) -> None:
        self.profile = mw.pm.name
        self._sync_seen = False
        clock = AnkiClock(lambda: mw.col)
        source = AnkiRevlog(lambda: mw.col)
        path = self._save_path(self.profile)
        bak = path + ".bak"
        legacy = os.path.join(SAVE_DIR, self._legacy_save_name(self.profile))
        if legacy != path and not os.path.exists(path) and not os.path.exists(bak) and os.path.exists(legacy):
            # a save from before per-profile fingerprints. Copy rather than move: another
            # profile may have been sharing that old file name.
            for src, dst in ((legacy, path), (legacy + ".bak", bak)):
                try:
                    if os.path.exists(src):
                        shutil.copyfile(src, dst)
                except Exception:
                    log(f"could not copy {src}:\n{traceback.format_exc()}")
        adopted = None
        if not os.path.exists(path) and not os.path.exists(bak):
            adopted = self._adopt_save_from_other_copy(path, self._legacy_save_name(self.profile))
        renamed = None
        if not adopted and not os.path.exists(path) and not os.path.exists(bak):
            renamed = self._adopt_renamed_profile_save(path, source)
        # A new game starts now: only reviews from here on pay. (Not "the newest review":
        # on a brand-new, still empty profile that's 0, and the first full sync would then
        # pay out the whole history at once.)
        start = clock.now_ms()
        fresh = new_state(start, clock.today(), start)
        state = None
        loaded_from = None
        damaged: list[str] = []
        locked = None
        for candidate in (path, bak):
            if not os.path.exists(candidate):
                continue
            try:
                data = self._read_save(candidate)
            except OSError:
                # another program (antivirus, a cloud-sync client) has the file open: that's
                # not damage, and starting over now could overwrite good progress later
                log(f"could not open {candidate}:\n{traceback.format_exc()}")
                locked = candidate
                break
            try:
                if not isinstance(data, dict) or not isinstance(data.get("ledger"), dict):
                    raise ValueError("not a Powerhouse save")
                state = migrate(data, new_state(start, clock.today(), start))
                Game(state, clock, source, self.settings()).snapshot()  # make sure it's usable
                loaded_from = candidate
                break
            except Exception:
                state = None
                log(f"could not use {candidate}:\n{traceback.format_exc()}")
                damaged.append(self._set_aside(candidate))
        if locked:
            self.game = None
            self._paused = True
            QTimer.singleShot(2500, lambda: tooltip(PAUSED_NOTE, period=9000))
            return
        self._paused = False
        if state is None:
            state = fresh
        # only a main file that loaded fine (or none at all) may become tomorrow's backup
        self._main_ok = loaded_from == path or not os.path.exists(path)
        self.game = Game(state, clock, source, self.settings())
        self._check_collection(self.game)
        self._start_day_timer()
        self.game.sync()
        self._save_timer.start()
        self.refresh_history()
        notes = []
        if damaged and state is not fresh:
            notes.append("Powerhouse: your save file was damaged, so it loaded the backup. Reviews since then still count.")
        elif damaged:
            notes.append("Powerhouse couldn't read your save, so it started a new game. "
                         "The damaged file is kept in the add-on's user_files/saves folder.")
        if adopted:
            notes.append("Powerhouse: brought your progress over from your other copy of the add-on.")
        if renamed and loaded_from:
            notes.append("Powerhouse: found your progress from before this profile was renamed.")
        dupes = getattr(mw, "_powerhouse_duplicates", [])
        if dupes:
            notes.append(f"Powerhouse is installed twice. The copy in add-on folder {dupes[0]!r} is switched off; "
                         "you can delete it in Tools → Add-ons.")
        if notes:
            QTimer.singleShot(2500, lambda: tooltip("<br>".join(notes), period=7000))

    @staticmethod
    def _read_save(path: str) -> Any:
        """Read a save file, waiting a moment if another program briefly has it open.
        OSError means it couldn't be opened; ValueError means it isn't valid JSON."""
        for attempt in range(4):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(0.25)
        return None

    def _adopt_renamed_profile_save(self, path: str, source: AnkiRevlog) -> Optional[str]:
        """No save for this profile name: if the profile was renamed, its save is still
        under the old name. Take it over when it belongs to this same collection."""
        try:
            taken: list[str] = []
            for p in mw.pm.profiles():
                taken.append(self._save_path(p))
                taken.append(os.path.join(SAVE_DIR, self._legacy_save_name(p)))
            found = find_orphan_save(SAVE_DIR, taken, self._collection_mark(), source.has_any)
            if not found:
                return None
            for src, dst in ((found, path), (found + ".bak", path + ".bak")):
                if os.path.exists(src):
                    os.replace(src, dst)
            log(f"took over {found} (the profile was renamed)")
            return found
        except Exception:
            log(f"could not look for a renamed profile's save:\n{traceback.format_exc()}")
            return None

    @staticmethod
    def _collection_mark() -> Optional[int]:
        """The collection's creation time: it changes when the collection is replaced."""
        try:
            return int(mw.col.crt)
        except Exception:
            return None

    def _check_collection(self, game: Game) -> None:
        """A full sync download or a .colpkg import replaces the collection, and Anki's
        day numbers are counted from its creation, so they jump. Keep the install day
        the same number of days back when that happens."""
        mark = self._collection_mark()
        if mark is None:
            return
        old = game.s.get("col_crt")
        game.s["col_crt"] = mark
        if old is None:
            game.dirty = True
        elif int(old) != mark:
            game.reanchor_install_day()
            log(f"the collection was replaced; install day is now {game.s['install_day']}")

    @staticmethod
    def _set_aside(path: str) -> str:
        """Move a save we couldn't read out of the way (never delete it), so the next
        save can't copy it over the good backup."""
        target = f"{path}.damaged-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            os.replace(path, target)
        except Exception:
            log(f"could not move {path} aside:\n{traceback.format_exc()}")
        return target

    def _other_copies(self) -> list[str]:
        """Folders of other Powerhouse installs (one from a file, one from AnkiWeb, say)."""
        out: list[str] = []
        try:
            mgr = mw.addonManager
            for d in mgr.allAddons():
                if d == self.pkg:
                    continue
                folder = mgr.addonsFolder(d)
                if (os.path.exists(os.path.join(folder, "engine", "game.py"))
                        and os.path.exists(os.path.join(folder, "web", "mito.js"))):
                    out.append(folder)
        except Exception:
            log(f"could not look for other copies:\n{traceback.format_exc()}")
        return out

    def _adopt_save_from_other_copy(self, path: str, legacy_name: str) -> Optional[str]:
        """First run of this copy: pick up the progress saved by another copy, if any."""
        names = {os.path.basename(path), legacy_name}
        best: Optional[tuple[float, str]] = None
        for src in (os.path.join(folder, "user_files", "saves", n) for folder in self._other_copies() for n in names):
            try:
                if not os.path.exists(src):
                    continue
                with open(src, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "ledger" in data and "salt" in data:
                    mtime = os.path.getmtime(src)
                    if best is None or mtime > best[0]:
                        best = (mtime, src)
            except Exception:
                log(f"could not read {src}:\n{traceback.format_exc()}")
        if best is None:
            return None
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            shutil.copyfile(best[1], path)
            log(f"copied progress from {best[1]}")
            return best[1]
        except Exception:
            log(f"could not copy progress from {best[1]}:\n{traceback.format_exc()}")
            return None

    @safe()
    def on_profile_close(self) -> None:
        if self.window:
            try:
                self.window.close()
            except Exception:
                pass
        if self.game:
            self.game.end_session()
            self.save()
        self._save_timer.stop()
        self._history_again = None
        self._history_day = None
        self.game = None

    # ------------------------------------------------------------- saving

    def save(self) -> None:
        if not self.game or not self.profile:
            return
        path = self._save_path(self.profile)
        os.makedirs(SAVE_DIR, exist_ok=True)
        try:
            if os.path.exists(path) and self._main_ok:
                # keep the previous day's save as a backup, refreshed once a day. copyfile
                # gives the copy today's date, so this runs once, not on every save.
                bak = path + ".bak"
                if not os.path.exists(bak) or date.fromtimestamp(os.path.getmtime(bak)) != date.today():
                    tmp_bak = bak + ".tmp"
                    shutil.copyfile(path, tmp_bak)
                    os.replace(tmp_bak, bak)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.game.s, f, separators=(",", ":"))
            os.replace(tmp, path)
            self._main_ok = True
            self.game.dirty = False
        except Exception:
            log(f"save failed:\n{traceback.format_exc()}")

    @safe()
    def _autosave(self) -> None:
        if self.game and self.game.dirty:
            self.save()

    # ------------------------------------------------------------ history

    def refresh_history(self, then_full_sync: bool = True, after_sync: bool = False) -> None:
        if not self.game or not mw.col:
            return
        if self._history_running:
            # one is already running (say, a sync finished during startup): run again after it
            again = self._history_again or {"then_full_sync": False, "after_sync": False}
            again["then_full_sync"] = again["then_full_sync"] or then_full_sync
            again["after_sync"] = again["after_sync"] or after_sync
            self._history_again = again
            return
        from aqt.operations import QueryOp

        game = self.game
        cutoff = game.clock.day_cutoff_ms()
        today = game.today()
        # count the whole history once a day; after that only recent days, which keeps
        # syncs snappy on collections with years of reviews
        partial = game.hist_loaded and self._history_day == today
        days = RECENT_HISTORY_DAYS if partial else HISTORY_DAYS
        self._history_running = True

        def op(col: Any) -> tuple[dict[int, int], Optional[int], int]:
            src = AnkiRevlog(lambda: col)
            try:
                banked: Optional[int] = src.banked_cards()
            except Exception:
                banked = None  # keep the last known count; the streak matters more
            # a review stamped in the future (a device with a wrong clock) mustn't become
            # the bookmark later answers are measured against
            return src.daily_counts(cutoff, days), banked, src.max_id(before=cutoff)

        def done(result: tuple[dict[int, int], Optional[int], int]) -> None:
            self._history_running = False
            try:
                if self.game is game:
                    counts, banked, max_id = result
                    game.apply_history(counts, banked, max_id, partial_days=days if partial else None,
                                       counted_on=today)
                    if not partial:
                        self._history_day = today
                    events = game.sync(full=True) if then_full_sync else []
                    self.after_change(events, hud=False)
                    # the startup refresh often finishes after the first sync has already
                    # brought reviews in, so it announces them too
                    if after_sync or self._sync_seen:
                        got = next((e for e in events if e.get("t") == "answers"), None)
                        if got and got.get("n"):
                            n = int(got["n"])
                            tooltip(f"Powerhouse: {n:,} synced review{'s' if n != 1 else ''} counted, "
                                    f"+{fmt_number(got.get('atp', 0))} ATP", period=4000)
                    if after_sync:
                        self._sync_seen = False
            except Exception:
                log(f"history apply failed:\n{traceback.format_exc()}")
            self._run_queued_history()

        def failed(err: Exception) -> None:
            self._history_running = False
            log(f"history query failed: {err!r}")
            self._run_queued_history()

        QueryOp(parent=mw, op=op, success=done).failure(failed).run_in_background()

    def _run_queued_history(self) -> None:
        again, self._history_again = self._history_again, None
        if again and self.game:
            self.refresh_history(**again)

    # -------------------------------------------------------------- hooks

    @safe()
    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        # Let Anki show the next card first; tally the reward a moment later.
        if self.game:
            self._sync_timer.start(60)

    @safe()
    def _sync_after_answer(self) -> None:
        if not self.game or not mw.col:
            return
        events = self.game.sync()
        self.after_change(events, hud=True)

    @safe()
    def on_undo(self, changes: Any) -> None:
        if not self.game or not mw.col:
            return
        events = self.game.check_undo()
        if events:
            self.after_change(events, hud=True)

    @safe()
    def on_state_change(self, new_state_name: str, old_state_name: str) -> None:
        if not self.game:
            return
        if new_state_name == "review" and old_state_name != "review":
            self.game.start_session()
        elif old_state_name == "review" and new_state_name != "review":
            if self._sync_timer.isActive():
                self._sync_timer.stop()
                self._sync_after_answer()
            self.game.end_session()
            self._schedule_window_push()

    @safe()
    def on_sync_start(self) -> None:
        self._sync_seen = True

    @safe()
    def on_sync_finished(self) -> None:
        self.refresh_history(then_full_sync=True, after_sync=True)

    def _start_day_timer(self) -> None:
        """Check every 5 minutes whether the day rolled over (older Anki has no hook for it).
        Anki's own timer skips a tick while a progress window (a sync, an import, Check
        Database) is open, so asking the collection for today's date never has to wait.
        It's made here, not at startup: add-ons load before Anki's progress manager exists."""
        if self._day_timer is not None:
            return
        try:
            self._day_timer = mw.progress.timer(5 * 60 * 1000, self._check_day, True, True, parent=mw)
        except Exception:
            log(f"could not start the day timer:\n{traceback.format_exc()}")

    @safe()
    def on_collection_reloaded(self, col: Any = None) -> None:
        """The open profile's collection was replaced or reopened (a full sync download,
        a .colpkg import). On a normal profile open this runs before there's a game."""
        if not self.game or not mw.col:
            return
        reset = getattr(self.game.clock, "reset", None)
        if callable(reset):
            reset()
        self._check_collection(self.game)
        self.refresh_history(then_full_sync=True)

    @safe()
    def _check_day(self) -> None:
        if not self.game or not mw.col:
            return
        today = self.game.today()
        if self._last_day is not None and today != self._last_day:
            self.on_day_change()
        self._last_day = today

    @safe()
    def on_day_change(self) -> None:
        if self.game:
            self.game.sync()
            self.refresh_history(then_full_sync=True)

    @safe()
    def on_deck_browser(self, deck_browser: Any, content: Any) -> None:
        if not self.game:
            return
        settings = self.settings()
        tree = getattr(getattr(deck_browser, "_render_data", None), "tree", None)
        events: list[dict[str, Any]] = []
        if tree is not None:
            try:
                events = self.game.note_due_counts(int(tree.new_count), int(tree.learn_count),
                                                   int(tree.review_count))
            except Exception:
                log(f"due counts unavailable:\n{traceback.format_exc()}")
        if events:
            self._announce(events)
        if not settings["deck_panel"]:
            return
        opts = {"fontUrl": f"{self.web_base}/fonts/fredoka.woff2", "compact": settings["deck_panel_compact"],
                "reduceMotion": settings["reduce_motion"]}
        payload = self.game.panel_payload()
        content.stats += '<div id="powerhouse-panel"></div>' + self._boot_script(
            ["mito.js", "panel.js"],
            f'PowerhousePanel.mount(document.getElementById("powerhouse-panel"),{json.dumps(opts)},'
            f'{json.dumps(payload)});',
        )

    @safe()
    def on_webview_content(self, web_content: Any, context: Any) -> None:
        if not self.game:
            return
        from aqt.reviewer import Reviewer, ReviewerBottomBar

        settings = self.settings()
        hud_context = ReviewerBottomBar if settings["hud_position"] == "bar" else Reviewer
        if isinstance(context, hud_context) and settings["hud"]:
            opts = {
                "position": settings["hud_position"],
                "toasts": settings["hud_toasts"],
                "reduceMotion": settings["reduce_motion"],
                "fontUrl": f"{self.web_base}/fonts/fredoka.woff2",
            }
            payload = self.game.hud_payload()
            web_content.body += self._boot_script(
                ["mito.js", "hud.js"], f"PowerhouseHUD.mount({json.dumps(opts)},{json.dumps(payload)});"
            )

    def _boot_script(self, files: list[str], call: str) -> str:
        """A tiny inline loader. Our scripts are fetched *after* the page is parsed,
        so they never delay Anki's 'page ready' handshake for the screen they're on."""
        srcs = json.dumps([f"{self.web_base}/{name}" for name in files])
        return (
            "<script>(function(){"
            f"var srcs={srcs};"
            "function go(i){"
            "if(i>=srcs.length){try{" + call + "}catch(e){console.log('powerhouse:',e)}return;}"
            "var s=document.createElement('script');s.src=srcs[i];"
            "s.onload=function(){go(i+1)};"
            "s.onerror=function(){console.log('powerhouse: could not load '+srcs[i])};"
            "(document.head||document.documentElement).appendChild(s);}"
            "go(0);})();</script>"
        )

    def on_js_message(self, handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
        if not isinstance(message, str) or not message.startswith("powerhouse:"):
            return handled
        try:
            return True, self.handle_command(message[len("powerhouse:"):], context)
        except Exception:
            log(f"command failed {message!r}:\n{traceback.format_exc()}")
            return True, {"ok": False, "error": "Something went wrong. Details are in powerhouse.log."}

    @safe()
    def on_toolbar_links(self, links: list[str], toolbar: Any) -> None:
        if not self.settings()["toolbar_button"]:
            return
        links.append(toolbar.create_link("powerhouse", "Powerhouse", self.open_window,
                                         tip="Open Powerhouse, your ATP game", id="powerhouse"))

    # ----------------------------------------------------------- updates

    def after_change(self, events: list[dict[str, Any]], hud: bool) -> None:
        if not self.game:
            return
        if hud and mw.state == "review" and self.settings()["hud"]:
            payload = self.game.hud_payload(events)
            try:
                web = mw.reviewer.bottom.web if self.settings()["hud_position"] == "bar" else mw.reviewer.web
                web.eval(self._update_js("PowerhouseHUD", "__phHudPending", payload))
            except Exception:
                log(f"hud update failed:\n{traceback.format_exc()}")
        else:
            self._update_panel()
        if self.window:
            self._pending_window_events.extend(e for e in events if e.get("t") != "answers")
            self._schedule_window_push()

    @staticmethod
    def _update_js(obj: str, pending: str, payload: dict[str, Any]) -> str:
        return (f"(function(p){{if(window.{obj}){{{obj}.update(p)}}else{{window.{pending}=p}}}})"
                f"({json.dumps(payload)});")

    def _update_panel(self) -> None:
        if self.game and mw.state == "deckBrowser" and self.settings()["deck_panel"]:
            try:
                mw.deckBrowser.web.eval(self._update_js("PowerhousePanel", "__phPanelPending",
                                                        self.game.panel_payload()))
            except Exception:
                pass

    def _schedule_window_push(self) -> None:
        if self.window and not self._window_push_timer.isActive():
            self._window_push_timer.start(400)

    @safe()
    def _push_window(self) -> None:
        if self.window and self.game:
            events, self._pending_window_events = self._pending_window_events, []
            self.window.push(self.game.snapshot(), events)

    def _announce(self, events: list[dict[str, Any]]) -> None:
        """Small tooltips for things that happen outside the review screen."""
        for e in events:
            if e.get("t") == "sweep":
                tooltip("Powerhouse: clean sweep! Every due review is done. A rare vesicle is waiting.", period=4000)
            elif e.get("t") == "achievement":
                tooltip(f"Powerhouse trophy: {e.get('name')}", period=3000)

    # ------------------------------------------------------------- window

    @safe()
    def open_window(self, *args: Any) -> None:
        if not self.game:
            tooltip(PAUSED_NOTE if self._paused else "Open a profile first.", period=6000)
            return
        if self.window:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
            return
        from .window import GameWindow

        events = self.game.sync()
        events += self.game.mark_game_opened()
        self.window = GameWindow(self)
        self.window.show()
        if events:
            self.window.push(self.game.snapshot(), [e for e in events if e.get("t") != "answers"])

    def open_settings(self) -> None:
        self.last_tab = "stats"
        if self.window is not None:
            try:  # already open: show the Stats tab, where the settings are
                self.window.web.eval("window.PH && PH.tab && PH.tab('stats');")
            except Exception:
                pass
        self.open_window()

    def window_closed(self, win: Any) -> None:
        if self.window is win:
            self.window = None
        self.save()
        self._update_panel()

    # ------------------------------------------------------------ payloads

    def snapshot(self) -> dict[str, Any]:
        return self.game.snapshot() if self.game else {}

    def static_payload(self) -> dict[str, Any]:
        if self._static is None:
            self._static = {
                "pathways": {p.id: {"name": p.name, "blurb": p.blurb, "baseYield": p.base_yield} for p in C.PATHWAYS},
                "pathwayOrder": [p.id for p in C.PATHWAYS],
                "upgrades": {u.id: {"id": u.id, "name": u.name, "blurb": u.blurb, "cost": u.cost, "kind": u.kind,
                                    "pathway": u.pathway, "ownedNeeded": u.owned_needed,
                                    "answersNeeded": u.answers_needed, "factor": u.factor} for u in C.UPGRADES},
                "enzymes": {e.id: {"name": e.name, "set": e.set, "rarity": e.rarity, "fact": e.fact}
                            for e in C.ENZYMES},
                "enzymeOrder": [e.id for e in C.ENZYMES],
                "sets": {s.id: {"name": s.name, "unlockLevel": s.unlock_level,
                                "unlockTitle": C.title_for_level(s.unlock_level)} for s in C.ENZYME_SETS},
                "expressionCopies": {r: list(v) for r, v in C.EXPRESSION_COPIES.items()},
                "expressionBonus": C.EXPRESSION_BONUS,
                "legendaryPity": C.LEGENDARY_PITY,
                "setOrder": [s.id for s in C.ENZYME_SETS],
                "cosmetics": {c.id: {"id": c.id, "name": c.name, "slot": c.slot, "rarity": c.rarity,
                                     "source": c.source} for c in C.COSMETICS},
                "cosmeticOrder": [c.id for c in C.COSMETICS],
                "achievements": {a.id: {"name": a.name, "desc": a.desc, "tier": a.tier, "hidden": a.hidden}
                                 for a in C.ACHIEVEMENTS},
                "achievementOrder": [a.id for a in C.ACHIEVEMENTS],
                "costGrowth": C.COST_GROWTH,
            }
        return self._static

    # ------------------------------------------------------------ commands

    def handle_command(self, cmd: str, context: Any) -> Any:
        game = self.game
        if cmd == "open":
            self.open_window()
            return None
        if cmd.startswith("panel:"):
            self.write_settings({"deck_panel_compact": cmd == "panel:compact"})
            return None
        if game is None:
            return {"ok": False, "error": "Open a profile first."}

        name, _, arg = cmd.partition(":")
        result: dict[str, Any]
        if name == "tab":
            self.last_tab = arg or "pathways"
            return None
        if name == "buy":
            kind, _, rest = arg.partition(":")
            if kind == "pathway":
                pid, _, qty = rest.partition(":")
                qty_val: Any = "max" if qty == "max" else int(qty or 1)
                result = game.buy_pathway(pid, qty_val)
            else:
                result = game.buy_upgrade(rest)
        elif name == "open":
            loot = game.open_vesicle(arg or None)
            result = {"ok": loot.get("ok", False), "loot": loot, "events": loot.pop("events", []),
                      "error": loot.get("error")}
        elif name == "openall":
            loots, events = [], []
            for _ in range(500):
                if not game.s["vesicles"]:
                    break
                loot = game.open_vesicle()
                events.extend(loot.pop("events", []))
                loots.append(loot)
            result = {"ok": True, "loots": loots, "events": events}
        elif name == "equip":
            result = game.equip(arg)
        elif name == "clearnew":
            game.clear_new_cosmetics()
            result = {"ok": True}
        elif name == "poke":
            result = game.poke()
        elif name == "fission":
            result = game.fission()
        elif name == "intro":
            game.s["seen_intro"] = True
            game.give_welcome_pack()
            events = game.mark_game_opened()
            result = {"ok": True, "events": events}
        elif name == "settings":
            try:
                patch = json.loads(arg) if arg else {}
            except ValueError:
                patch = {}
            result = {"ok": True, "settings": dict(self.write_settings(patch), last_tab=self.last_tab)}
        else:
            return {"ok": False, "error": f"Unknown command: {name}"}

        game.dirty = True
        result.setdefault("events", [])
        result["state"] = game.snapshot()
        self._update_panel()
        return result


_controller: Optional[Powerhouse] = None


def setup() -> None:
    global _controller
    if _controller is not None:
        return
    pkg = mw.addonManager.addonFromModule(__name__)
    owner = getattr(mw, "_powerhouse_pkg", None)
    if owner and owner != pkg:
        # Installed twice (say, once from a file and once from AnkiWeb). One copy is enough;
        # the running copy will offer to bring this copy's progress over.
        dupes = list(getattr(mw, "_powerhouse_duplicates", []))
        dupes.append(pkg)
        mw._powerhouse_duplicates = dupes
        log(f"Powerhouse is already running from add-on folder {owner!r}; this copy ({pkg!r}) stays off")
        return
    mw._powerhouse_pkg = pkg
    try:
        _controller = Powerhouse()
        _controller.setup()
    except Exception:
        # let another copy (if any) take over instead
        mw._powerhouse_pkg = None
        _controller = None
        raise
