"""Powerhouse: an ATP clicker game that runs on your Anki reviews.

Every card you answer makes ATP for Mito the mitochondrion. Spend it on
pathways and upgrades, open vesicles for collectible enzymes and outfits,
and keep a daily streak. The add-on only reads your review history; it never
changes your cards or scheduling.
"""

from __future__ import annotations

try:
    from aqt import mw
except Exception:  # running outside Anki (tests)
    mw = None

if mw is not None:
    try:
        from .main import setup

        setup()
    except Exception:
        import os
        import traceback

        try:
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "powerhouse.log"), "a", encoding="utf-8") as f:
                f.write("startup failed:\n" + traceback.format_exc() + "\n")
        except Exception:
            pass
