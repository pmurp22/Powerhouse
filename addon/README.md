# Powerhouse

An ATP clicker that runs on your Anki reviews. Every card you answer makes ATP for
Mito the mitochondrion. Spend it on metabolic pathways that make every future card
worth more, open vesicles for collectible enzymes and outfits, and keep a daily streak.

## How to play

- **Review like normal.** Each answer adds ATP. The pill next to "More" in the review
  screen's bottom bar shows your ATP, what a card is worth, your flow and how many
  vesicles are waiting to be opened.
- **Any button, same ATP.** Again pays exactly what Easy pays: the button you press
  never changes what an answer earns, so grade honestly. Going faster never pays more, either.
- **Fair play.** Answers only count when you actually do them. An answer under a
  second counts now and then, but not when another under-a-second answer came within
  the 4 answers before it. A card counts up to 4 times a day, and auto-advance's
  machine-steady rhythm doesn't count. Answers that don't count earn nothing and don't
  count toward your goal. At a normal pace, a couple of seconds a card or more, it
  almost never triggers.
- **Flow** builds while you keep reviewing with no more than 3 minutes between answers
  (the Pomodoro timer upgrade lets it wait out a 5-minute break), up to ×1.5 ATP (×2 with
  upgrades). It's about not wandering off, not about rushing.
- **Vesicles** drop about once every 40 cards early in the day (more often with the
  vesicle upgrades), and less often on a big day (half as often after 150 cards that day,
  a quarter after 500, an eighth after 1,000), so a 2,000-card day doesn't bury you in
  them. Quests, trophies, clean sweeps and every fifth level give more. Open them in the
  Powerhouse window after your session for ATP, enzymes, looks for Mito and, rarely, a
  streak freeze.
- **Enzymes** come in six sets, and a new set starts turning up with each title:
  Pre-med, MS1, MS2, Step 1 survivor, MS3 and MS4. Each later set also has a minimum
  wait after install (1, 3, 5, 8 and 12 weeks), so on a busy schedule a set can arrive a
  little after its title. Every legendary is the rate-limiting
  enzyme of its pathway, and bad luck has a limit: you never get more than 2 duplicate
  legendaries in a row while you're missing one. Duplicates raise an enzyme's expression
  level (more enzyme, higher Vmax), and each level adds a little ATP.
- **Daily goal** (100 cards by default) keeps your streak alive and pays a
  *knowledge dividend* based on how many mature cards you have. Finishing every due
  review also counts for the streak, even below the goal, as long as at least half of
  the day's answers counted. Powerhouse checks when this computer's deck list shows
  nothing due. Every 7 streak days earns a freeze that covers a missed day.
- **Daily quests**, **trophies** (+1% ATP each) and **levels** (+1% ATP each) stack on top.
- **Mito grows, then divides (Fission).** Mito grows as his pathways make more ATP.
  Once you've made 10 billion ATP in total he can divide: your ATP, his pathways and
  their ×2 boosts restart, but you keep your study habits, vesicle and flow upgrades,
  enzymes, trophies, looks, level and streak, and each mtDNA copy adds +25% ATP forever. The game suggests it once
  a division would gain at least 3 copies and at least double what you have. It's
  optional, like Cookie Clicker's Ascension.
- **How to play**: the **?** button in the game window opens an illustrated guide.

At about 250 cards a day, a typical student finds the whole codex in about 6 months
(5 to 7 in simulations) and buys every pathway in about 6, with Fission first worth it
around month 3½ and then about every 6 weeks (7 divisions in the first year). The
rarest outfits can take a year or more. At 1,500 cards a day the codex takes about
3 months and every pathway under 2, with Fission first worth it after a month and then
every 2 to 3 weeks. `tools/pacing_report.py` in the source repository runs the real
game rules over a simulated year to check this (`python tools/pacing_report.py 365 3 250 1500`
compares two paces).

Open the game from the **Powerhouse** button in the top bar, the card under your deck
list, or **Tools → Powerhouse**.

## Good to know

- Powerhouse only **reads** your review history. It never changes cards, scheduling,
  decks or sync, so it can't affect AnkiHub, AnKing decks or other add-ons.
- Reviews from your phone (AnkiMobile, AnkiDroid or AnkiWeb) count once they sync
  to this computer, even if that's a few weeks later (up to 30 days). The game itself
  lives on this computer, so a second computer would keep its own separate game.
- Undoing an answer takes back what it earned: its ATP and XP, and its vesicle if you
  haven't opened it yet.
- Your progress is saved in `user_files/saves/` inside this add-on's folder, with a
  daily backup. Anki keeps that folder when the add-on updates, and your progress follows
  the profile if you rename it.
- Settings live in the **Stats** tab of the Powerhouse window (or Tools → Add-ons →
  Powerhouse → Config).
- If something goes wrong, details are in `user_files/powerhouse.log`.

## How it's built (for the curious)

Coming from R? Here's the map.

| File | What it does | R analogy |
| --- | --- | --- |
| `__init__.py` | Anki runs this at startup. It calls `setup()` and swallows any error so Anki keeps working. | `source("main.R")` in `.Rprofile` |
| `main.py` | Registers *hooks*: functions Anki calls when something happens (a card was answered, the deck list is drawn, a sync finished). | Shiny's `observeEvent(input$x, {...})` |
| `anki_bridge.py` | Read-only SQL against Anki's `revlog` table (one row per review) and its `cards` table (to count mature cards). | `DBI::dbGetQuery(con, "select ...")` |
| `engine/game.py` | The game rules: turning new review rows into ATP, vesicles, quests, streaks. No Anki code, so it can be tested alone. | a package of pure functions you `testthat` |
| `engine/content.py` | Every pathway, upgrade, enzyme, outfit and trophy as plain data. Change numbers here. | a data frame of game constants |
| `window.py` + `web/game.*` | The game window: an HTML page (like a Shiny UI) that talks to Python with `pycmd("powerhouse:...")`. | `ui.R` + `server.R` |
| `web/hud.js`, `web/panel.js` | The review pill and the deck-list card. They live in a *shadow DOM* so other add-ons' styles can't touch them. | an `htmlwidget` in its own iframe |
| `web/mito.js` | Mito and every icon, drawn as SVG strings. | `ggplot` geoms, but by hand |

The key idea: Anki already logs every answer in `revlog`. After each answer, Powerhouse
asks "which rows are new since last time?", pays out for them, and remembers the ids.
If a row disappears (you hit undo), it takes that payment back.

Try a tiny change: open `engine/content.py`, edit a line in `POKE_LINES`, restart Anki,
and poke Mito in the game window.

## License

Powerhouse is free software under the GNU Affero General Public License v3 or later
(see `LICENSE`), the license AnkiWeb expects add-ons to use. The Fredoka font is
under the SIL Open Font License (`web/fonts/OFL-Fredoka.txt`).
