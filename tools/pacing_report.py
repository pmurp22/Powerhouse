"""Run tools/longsim.py's student over several seeds and pace levels; print milestone days.

Usage: python tools/pacing_report.py [days] [seeds] [paces...] [--json out.json]
"""

from __future__ import annotations

import json
import statistics
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import longsim  # noqa: E402

KEYS = [
    "enzymes>=10", "sets>=1", "enzymes>=24", "sets>=3", "enzymes>=36", "first legendary", "enzymes>=48",
    "all drop cosmetics", "buy:krebs", "buy:etc", "buy:synthase", "buy:betaox", "buy:ketones", "buy:creatine",
    "buy:brownfat", "buy:biogenesis", "first fission",
]


def one(args):
    pace, seed, days, mash = args
    st = longsim.Student(pace, seed, mash=mash, row_len=5)
    st.run(days)
    last = st.timeline[-1]
    return pace, seed, st.milestones, {
        "level": last["level"], "trophies": last["trophies"], "fissions": last["fissions"],
        "opened_per_day": last["opened"] / days, "uncounted": st.game.s["stats"].get("uncounted", 0),
        "answers": last["answers"], "atp_all": last["atp_all"],
    }


OUT_JSON = None


def main() -> None:
    global OUT_JSON
    args = sys.argv[1:]
    if "--json" in args:  # also save every milestone as JSON
        i = args.index("--json")
        OUT_JSON = args[i + 1]
        del args[i:i + 2]
    days = int(args[0]) if len(args) > 0 else 365
    seeds = int(args[1]) if len(args) > 1 else 3
    paces = [int(x) for x in args[2:]] or [100, 250, 500]
    jobs = [(p, s, days, 0.0) for p in paces for s in range(1, seeds + 1)]
    with Pool(2) as pool:
        results = pool.map(one, jobs)
    out = {}
    for pace, seed, ms, end in results:
        out.setdefault(pace, []).append((seed, ms, end))
    for pace in paces:
        rows = out[pace]
        print(f"\n== {pace} cards/day, {len(rows)} seeds, {days} days ==")
        for k in KEYS:
            vals = [ms.get(k) for _, ms, _ in rows]
            got = sorted(v for v in vals if v is not None)
            miss = len(vals) - len(got)
            if got:
                med = statistics.median(got)
                print(f"  {k:<20} median day {med:>5.0f}   range {got[0]}-{got[-1]}" + (f"   ({miss} never)" if miss else ""))
            else:
                print(f"  {k:<20} never")
        ends = [e for _, _, e in rows]
        print("  at the end: level", [e["level"] for e in ends], "trophies", [e["trophies"] for e in ends],
              "fissions", [e["fissions"] for e in ends], "vesicles/day", [round(e["opened_per_day"], 1) for e in ends])
    if OUT_JSON:
        Path(OUT_JSON).write_text(json.dumps({str(k): [(s, m, e) for s, m, e in v] for k, v in out.items()}))


if __name__ == "__main__":
    main()
