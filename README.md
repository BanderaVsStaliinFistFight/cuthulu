# Eldritch Pacts – Call of the Old Ones

A Hearts of Iron IV mod that lets any nation summon one of the Lovecraftian Old Ones, bind it in a pact, and spend its favor on blessings. Blessings buff the nation, give traits to its generals, admirals and leader, raise avatar commanders, and unlock unique eldritch battalions.

Everything is in a new decision category, **The Forbidden Rites**, open to every country. The mod overwrites no vanilla files.

---

## Installation

Your HoI4 `mod` folder is here:
* Windows: `Documents\Paradox Interactive\Hearts of Iron IV\mod\`
* Linux: `~/.local/share/Paradox Interactive/Hearts of Iron IV/mod/`
* macOS: `~/Documents/Paradox Interactive/Hearts of Iron IV/mod/`

1. Put the mod files in a folder called **`eldritch_pacts`** inside `mod/`. `descriptor.mod`, `common`, `events` and the other folders must sit **directly** inside `eldritch_pacts`:

   ```
   mod/
   ├── eldritch_pacts.mod          <- step 2
   └── eldritch_pacts/
       ├── descriptor.mod
       ├── common/
       ├── events/
       ├── gfx/
       ├── interface/
       ├── localisation/
       └── ...
   ```

   GitHub's "Download ZIP" puts everything inside an extra folder (e.g. `cuthulu-claude-happy-curie-tj0rkv`). Move the *contents* of that folder into `eldritch_pacts`, or rename that folder itself to `eldritch_pacts`. A clone ends up in a folder called `cuthulu`; rename it to `eldritch_pacts`.
2. Copy `install/eldritch_pacts.mod` into `mod/`, next to the `eldritch_pacts` folder, as shown above.
   On Linux and macOS, edit its `path` line to the absolute path, e.g. `path="/home/you/.local/share/Paradox Interactive/Hearts of Iron IV/mod/eldritch_pacts"`.
3. Open the Paradox launcher, add **Eldritch Pacts - Call of the Old Ones** to your playset, make sure it is ticked, and start a game from that playset.

If the launcher shows a version warning, change `supported_version` in `descriptor.mod` and `eldritch_pacts.mod` to your game version. The mod does not depend on a specific patch.

### Can't see the decisions?

When the mod is loaded, every human player gets an **"Eldritch Pacts Is Active"** pop-up on the first day of a new game. The **Decisions** tab (top-left button) always shows the **The Forbidden Rites** category.

* **No pop-up and no category:** the game is not loading the mod. Check that the folder name matches the `path` in `eldritch_pacts.mod`, that `descriptor.mod` is directly inside that folder (not one level deeper), and that the mod is enabled in the playset you launched.
* **The category is there but empty, or something else looks wrong:** open `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log`, search for `eldritch`, and report the lines you find.

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
| **Incarnate the God in the Flesh** | 200 Favor | The god itself joins your army as one division (see below). Requires Tier II. 30-day ritual, then once a year. |
| *God's avatar* | 120 Favor | A unique, extremely skilled commander with a custom portrait. Requires Tier II. Once per game. |
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

### 5. The gods incarnate
From Tier II, **Incarnate [God] in the Flesh** brings the god onto the battlefield as a veteran division at your capital, with the world told what has happened. Each incarnate division is one colossal **god battalion** plus an escort of the god's servitors:

| God | Division | Escort | Terrain where the god is strongest |
|---|---|---|---|
| Cthulhu | **Great Cthulhu** | 3 Deep One Brood, 2 Star-Spawn | sea landings, rivers, marsh |
| Nyarlathotep | **The Crawling Chaos** | 3 Faceless Cultists, 2 Shantak Riders | cities, desert |
| Hastur | **The King in Yellow** | 3 Zealots, 3 Byakhee Riders | hills, mountains, cities |
| Shub-Niggurath | **The Black Goat of the Woods** | 3 Thousand Young, 2 Dark Young | forest, jungle |
| Yog-Sothoth | **The All-in-One** | 3 Wardens of the Gate, 2 Dunwich Horrors | plains, hills, cities |
| Azathoth | **Fragment of Azathoth** | 4 Spawn of the Nuclear Chaos, 1 Void Pipers | plains, desert, cities |

A god battalion has 400 strength, 150+ organization, 80% morale and +200% attack / +300% defense and breakthrough, rising further at Tier III. It takes 8 combat width. You can't put it in your own templates or train it: it only arrives through the ritual. Losses are reinforced from your normal stockpile.

### 6. 3D models for the King in Yellow's forces
Hastur's units have their own detailed map models instead of reusing vanilla infantry:

| Battalion | Model |
|---|---|
| **Zealots of the Yellow Sign** | a cultist built on real human proportions (1.8 m, 0.23 m head, 0.42 m shoulders): a robe hanging from the shoulders in gravity folds and cinched by a knotted rope belt, a capelet, a hood framing a bandaged face with brow, nose and chin, bell sleeves over real-length arms with bandaged hands, boots under the hem, and a spear with a torn banner bearing a faded Yellow Sign (~10k triangles) |
| **Byakhee Riders** | a mount with flying-creature anatomy: a deep-keeled ribbed torso, two bird-like legs with talons under its centre of mass, bat wings that are its forelimbs (finger bones carrying a membrane with ragged edges and rips), a long neck, a skull with a hooked beak, teeth and burning eyes, and a tail. A saddle cloth bears the Yellow Sign. The rider sits properly astride: thighs over the flanks, booted feet, robe hanging down the sides, a couched lance with a pennant, and reins in the other hand (~19k triangles) |
| **The King in Yellow** (incarnate) | the same anatomy at giant scale (~4.5 m): hood, bandaged face, capelet and long robe with a ragged, holed hem, and eight octopus-like tentacles that taper from a thick muscular base, with two alternating rows of suckers sized to the arm (~48k triangles; only one is ever on the map) |

They share a 1024px texture set: woven cloth with sun-bleaching, grime and stains climbing from the hem, wrapped bandages with old blood, mottled tentacle skin with green slime, wrinkled leather, veined wing membrane, tarnished iron and weathered wood. Each texture has a matching normal map for surface detail.

#### Animations
Each model is rigged to a skeleton and has six animations, played by the unit's map states (`retreat` reuses the walk and `training` the idle):

| State | Zealot (19 bones) | Byakhee Rider (28 bones) | The King in Yellow (38 bones) |
|---|---|---|---|
| `idle` | breathes, looks around, the banner stirs | shifts its weight, turns its head, swishes its tail, wings twitch; the rider looks about | sways, all eight tentacles ripple in slow waves |
| `move` / `retreat` | walks: legs stride under the robe, the free arm swings, the banner sways | takes off and flies: rises off the ground, beats its wings, trails its talons | glides forward on rolling tentacle waves |
| `attack` | winds up and thrusts the spear level with a lunge | rears back with its jaws open, then snaps forward; the rider couches the lance | the front tentacles rear up, then slam down |
| `defend` | crouches with the spear braced like a pike | mantles: wings spread low and wide, neck drawn back, jaws hissing | tentacles rise into a writhing guard |
| `support_attack` | raises the spear and chants | shrieks skyward with wings half raised | tips its head back, tentacles undulating in a rite |
| `death` | sinks to its knees and slumps forward, dropping the spear | its legs fold and it sinks down, wings sprawling to the ground and head dropping; the rider slumps over its neck | slumps forward and sinks into the earth, tentacles going limp |

The animations are 15 fps and loop, except `death`, which plays once.

A division is drawn with the model of its highest-priority battalion, so the *Host of the Yellow Sign* shows a Byakhee rider and the King's division shows the King himself.

### 7. The god's whims
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
common/on_actions/                 welcome pop-up at game start
events/                            summoning, tier, whim, curse, news and monthly-pulse events
interface/eldritch.gfx             sprite definitions
gfx/                               generated art (DDS): spirit, decision, battalion and trait icons,
                                   event pictures, and avatar portraits (gfx/leaders/eldritch/)
localisation/english/              all text (UTF-8 with BOM)
install/eldritch_pacts.mod         launcher file to copy into your mod/ folder
gfx/entities/                      King in Yellow mesh definitions (.gfx) and unit entities with their animation states (.asset)
gfx/models/units/eldritch/         King in Yellow .mesh models, .anim animations, their definitions and the texture atlas
tools/generate_art.py              regenerates every texture and the thumbnail
tools/generate_models.py           regenerates the 3D models and animations (add --preview DIR to render PNG
                                   previews, an animated GIF per animation and a contact sheet per model)
tools/validate_mod.py              static checks: braces, localisation, sprites, entities, animations, references
```

Run `python3 tools/validate_mod.py` after editing to catch missing localisation, sprites, effects, traits or events. Run `python3 tools/generate_art.py` (needs Pillow and numpy) to rebuild the art.

---

## Testing status

The script is written against the standard HoI4 modding syntax. It passes the bundled static validator but **has not been run in-game yet**. If something misbehaves, check `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log`. These parts are the most likely to need a tweak on a new game version:

* `create_unit` (servitor and god spawning) and the locked `division_template`.
* **The 3D models.** They're written in Paradox's binary `.mesh` and `.anim` formats by `tools/generate_models.py`, read back and checked, and compared byte for byte against animated units that work in game (Millennium Dawn's infantry). They follow the same conventions: the `PdxMeshAdvanced` shader that HoI4's own skinned units use, up to four bone weights per vertex, at most 44 bones, a `Collision` box shape, animation definitions that name each `.anim` file relative to their own folder, and the size set by `scale` on the entity rather than on the mesh. The textures use normal map X in green, Y in alpha and an emissive mask in blue; specular R mask, G specular, B metalness, A roughness. If surfaces look oddly lit, inverted or glowing, the in-game layout differs from that. If units look too big or too small, change `scale` in `gfx/entities/eldritch_hastur_units.asset` (default 3.0; vanilla-sized infantry stands about 6 units tall). If a unit stands in its rest pose without moving, the game didn't accept the animation files or the state names; `error.log` will name the file. If they cause any problem, set `sprite = infantry` again on `eldritch_yellow_zealots`, `eldritch_byakhee_riders` and `eldritch_hastur_incarnate` in `common/units/eldritch_units.txt` to go back to vanilla models.
* The god battalions are deliberately never unlocked for the designer. If the game refuses to spawn a template that contains them, the god division will not appear. `error.log` will say so.
* The hidden rite technologies, which have no tech-tree folder and are granted with `set_technology`.
* Icon sizes. The textures are 64×67 (spirits), 46×46 (decisions), 60×40 (battalions), 40×40 (traits), 156×210 (portraits) and 210×176 / 397×153 (events). If the UI expects different sizes, change the constants at the top of `tools/generate_art.py` and regenerate.
