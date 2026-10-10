# Eldritch Pacts – Call of the Old Ones

A Hearts of Iron IV mod that lets any nation summon one of the Lovecraftian Old Ones, bind it in a pact, and spend its favor on blessings. Blessings buff the nation, give traits to its generals, admirals and leader, raise avatar commanders, and unlock unique eldritch battalions.

Everything is in a new decision category, **The Forbidden Rites**, open to every country. The mod overwrites no vanilla files.

---

## Installation

1. Copy this folder to your HoI4 mod directory:
   * Windows: `Documents\Paradox Interactive\Hearts of Iron IV\mod\eldritch_pacts`
   * Linux: `~/.local/share/Paradox Interactive/Hearts of Iron IV/mod/eldritch_pacts`
   * macOS: `~/Documents/Paradox Interactive/Hearts of Iron IV/mod/eldritch_pacts`
2. Next to that folder (in `mod/`), create a file named `eldritch_pacts.mod` with this content:

   ```
   version="1.0.0"
   tags={ "Alternative History" "Gameplay" "Military" }
   name="Eldritch Pacts - Call of the Old Ones"
   picture="thumbnail.png"
   supported_version="1.16.*"
   path="mod/eldritch_pacts"
   ```

   On Linux and macOS, `path` must be absolute, e.g. `path="/home/you/.local/share/Paradox Interactive/Hearts of Iron IV/mod/eldritch_pacts"`.
3. Enable **Eldritch Pacts** in a playset in the Paradox launcher and start the game.

If the launcher shows a version warning, change `supported_version` in both `descriptor.mod` and `eldritch_pacts.mod` to your game version. The mod does not depend on a specific patch.

---

## How it works

### 1. Find the lore
**Seek the Forbidden Lore** (25 PP, 30 days) reveals the six summoning rituals.

### 2. Summon one god
Each summoning takes 60 days and costs political power plus a manpower sacrifice. **You can only ever bind one god.** Once a pact is sealed, the other rituals disappear for good, and while one ritual is running the others are locked.

Sealing a pact:
* adds the god's **national spirit** (Tier I),
* gives your country leader the god's **Herald** trait,
* unlocks the god's **two unique battalions** for the division designer,
* creates a locked **division template** and spawns **two veteran divisions** at your capital,
* starts your **Eldritch Favor** at 50, plus 5 per month,
* sends world news to every other nation.

### 3. Spend Eldritch Favor on blessings
Favor is the currency of the pact. You gain it monthly (5 / 8 / 12 by tier), from **Hold a Rite of Worship** (15 PP → 15 Favor, every 30 days), from **Offer a Blood Sacrifice** (20k manpower → 40 Favor, every 60 days), and from the god's random whims (events).

| Blessing | Cost | Effect |
|---|---|---|
| **Anoint a Champion** | 50 Favor | An un-anointed general gets the god's general trait. Field marshals are chosen first. Every 60 days. |
| **Anoint an Admiral** | 50 Favor | An un-anointed admiral gets the god's admiral trait. Every 60 days. |
| **Exalt the Prophet** | 75 Favor | Your country leader gets the god's **Herald** and **Chosen** traits. Once a year, so a new leader can be exalted too. |
| **Call Forth the Servitors** | 60 Favor | Two veteran divisions of the god's template spawn at your capital. Every 90 days. |
| **Deepen the Pact (Tier II)** | 150 Favor | Stronger national spirit, stronger eldritch battalions, more monthly Favor, unlocks the Avatar. 45-day ritual. |
| **Deepen the Pact (Tier III)** | 300 Favor | The ultimate spirit and battalion bonuses, more Favor, a unique gift, and world news. 90-day ritual. |
| *God's timed blessing* | 40 Favor | A 180-day national spirit (see below). |
| *God's avatar* | 120 Favor | A unique, extremely skilled commander. Requires Tier II. Once per game. |
| *God's unique rite* | varies | See below. |

### 4. The gods

| God | Pact spirit focus | Battalions (template) | Timed blessing | Avatar | Unique rite | Tier III gift |
|---|---|---|---|---|---|---|
| **Cthulhu** – the Dreamer in R'lyeh *(needs a coastline)* | Navy damage and speed, dockyards, amphibious invasions | **Deep One Brood** (amphibious infantry), **Star-Spawn of Cthulhu** (heavy monsters) – *Deep One Swarm* | Tide of R'lyeh (naval and invasion bonuses) | Admiral **Father Dagon** and field marshal **Mother Hydra** | **Send Nightmares** – curse an enemy at war with you: −stability, −PP, −war support for 90 days | Two more Deep One Swarms |
| **Nyarlathotep** – the Crawling Chaos *(needs 40% stability)* | Political power, faster war goals, stability | **Faceless Cultists** (urban infantry), **Shantak Riders** (fast mobile) – *Faceless Legion* | Masks of Nyarlathotep (PP, stability) | **The Black Pharaoh** | **Whisper Madness** – target a neighbour, enemy or major: −8% stability and a push toward your ideology | +200 PP |
| **Hastur** – the King in Yellow *(needs 30% war support)* | Army morale, air attack and agility, aces | **Zealots of the Yellow Sign** (unbreakable infantry), **Byakhee Riders** (paradrop-capable shock troops) – *Host of the Yellow Sign* | The Yellow Sign Unveiled (morale, org, war support) | **The Stranger in the Pallid Mask** | **Stage 'The King in Yellow'** – curse an enemy: −morale, −org, −stability for 90 days | +10% war support |
| **Shub-Niggurath** – the Black Goat *(25k manpower sacrifice)* | Population growth, recruitable pop, organization | **Dark Young** (forest/jungle monsters), **Thousand Young** (cheap swarm infantry) – *Brood of the Black Goat* | Fecundity of the Black Goat (growth, reinforcement, attrition) | **The Shepherd of the Black Goat** | **Rite of the Thousand Young** – +25k manpower | +100k manpower |
| **Yog-Sothoth** – the Gate and the Key | Research speed, planning, factory efficiency | **Wardens of the Gate** (defensive infantry), **Dunwich Horror** (invisible monster) – *Wardens of the Gate* | All Is One (research, planning) | **Wilbur Whateley** | **Open the Gate** – +100% research bonus for one industry and one electronics tech | +1 research slot |
| **Azathoth** – the Daemon Sultan *(needs 50% war support, −10% stability)* | Attack, breakthrough, factory output, at a heavy stability cost | **Spawn of the Nuclear Chaos** (shock infantry), **Void Pipers** (sorcerous artillery) – *Chaos Horde* | Mindless Fury (attack, breakthrough, speed) | **The Piper of the Void** | **Bottle the Nuclear Chaos** – a nuclear bomb (Tier II+) | Two nuclear bombs |

### 5. The god's whims
About once every eight months on average, your patron makes itself known: it demands tribute, a prophet preaches in the streets, the stars align, or your soldiers share a dream. Each event trades Favor against manpower, political power, stability or war support.

---

## Game rule

**AI Eldritch Pacts** (game rules screen, *Eldritch Pacts* group):
* **Disabled** (default): only human players summon gods.
* **Allowed**: AI nations may seek the lore, bind a god and use its blessings.

---

## Compatibility

* No vanilla files are overwritten. Every key, flag, variable and file uses the `eldritch_` prefix, so the mod should work alongside most other mods, including total conversions that keep the standard decision system.
* No DLC is required.
* Achievements are disabled, as with any mod.

---

## Files

```
common/decisions/                  decision category and all decisions
common/ideas/                      pact spirits, timed blessings, curses
common/country_leader/             Herald / Chosen leader traits
common/unit_leader/                general, admiral and avatar traits
common/units/                      the 12 eldritch battalions
common/technologies/               hidden "rite" techs that unlock and buff the battalions
common/scripted_effects|triggers/  shared logic (summoning, blessings, tiers, favor)
common/scripted_localisation/      [ROOT.GetEldritchGodName] etc.
common/game_rules/                 the AI rule
events/                            summoning, tier, whim, curse, news and monthly-pulse events
interface/eldritch.gfx             sprite definitions
gfx/                               generated icons and event pictures (DDS)
localisation/english/              all text (UTF-8 with BOM)
tools/generate_art.py              regenerates every texture and the thumbnail
tools/validate_mod.py              static checks: braces, localisation, sprites, references
```

Run `python3 tools/validate_mod.py` after editing to catch missing localisation, sprites, effects, traits or events. Run `python3 tools/generate_art.py` (needs Pillow and numpy) to rebuild the art.

---

## Testing status

The script is written against the standard HoI4 modding syntax. It passes the bundled static validator but **has not been run in-game yet**. If something misbehaves, check `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log`. These parts are the most likely to need a tweak on a new game version:

* `create_unit` (servitor spawning) and the locked `division_template`.
* The hidden rite technologies, which have no tech-tree folder and are granted with `set_technology`.
* Icon sizes. The textures are 64×67 (spirits), 46×46 (decisions) and 210×176 / 397×153 (events). If the UI expects different sizes, change the constants at the top of `tools/generate_art.py` and regenerate.
