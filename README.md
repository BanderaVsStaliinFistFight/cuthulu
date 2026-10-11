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
From Tier II, **Incarnate [God] in the Flesh** brings the god onto the battlefield as a veteran division at your capital, with the world told what has happened. Only one incarnation can be on the map at a time: the decision stays locked while the god's division exists and reopens once it is destroyed (still at most once a year, for 200 Favor). Each incarnate division is one colossal **god battalion** plus an escort of the god's servitors:

| God | Division | Escort | Terrain where the god is strongest |
|---|---|---|---|
| Cthulhu | **Great Cthulhu** | 3 Deep One Brood, 2 Star-Spawn | sea landings, rivers, marsh |
| Nyarlathotep | **The Crawling Chaos** | 3 Faceless Cultists, 2 Shantak Riders | cities, desert |
| Hastur | **The King in Yellow** | 3 Zealots, 3 Byakhee Riders | hills, mountains, cities |
| Shub-Niggurath | **The Black Goat of the Woods** | 3 Thousand Young, 2 Dark Young | forest, jungle |
| Yog-Sothoth | **The All-in-One** | 3 Wardens of the Gate, 2 Dunwich Horrors | plains, hills, cities |
| Azathoth | **Fragment of Azathoth** | 4 Spawn of the Nuclear Chaos, 1 Void Pipers | plains, desert, cities |

A god battalion is a division in itself:

* **1,000 strength** (forty infantry battalions' worth) and **220 organization**, plus 50 more from the incarnation and 30 more at Tier III, recovering at 100%.
* **+500% soft and hard attack, +600% defense and breakthrough, +100% piercing** and **+50% speed**, rising to +600% / +700% at Tier III.
* Its own **recon (2)**, **initiative (+25%)** and field-hospital recovery (half its casualties return, half the experience loss).
* **Large bonuses in its favoured terrain** from the table above, for example +200% attack in sea landings for Great Cthulhu and +120% attack in forest and jungle for the Black Goat.
* It takes 8 combat width. You can't put it in your own templates or train it: it only arrives through the ritual. Losses are reinforced from your normal stockpile.

The god never comes alone. Every incarnation also brings **two veteran servitor divisions** of the god's template. While the god's division is on the map:

* your country has **A God Walks Among Us**: +10% attack, defense, morale and war support;
* every nation at war with you suffers **Dread of the Incarnate**: −15% morale, −10% organization, −10% war support.

Both are renewed every month and fade within a month of the god's division being destroyed.

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

### 8. The Prophet: your leader's own rites
Your country leader can take part in the pact in person. These rites need the leader to bear the god's **Herald** trait. The leader gets it when the pact is sealed, and a later leader gets it from **Exalt the Prophet**. The Forbidden Rites header shows where the leader stands: *Herald*, *Chosen*, *Vessel*, or *bears no mark*.

| Decision | Cost | Needs | Effect | Repeat |
|---|---|---|---|---|
| **Commune with [God]** | 25 PP | Herald | A 10-day trance, then the leader asks for **strength** (army and navy experience, +10 Favor), **knowledge** (50% research bonus for one industry and one land doctrine tech, +10 Favor) or just **listens** (+40 Favor). One time in four the leader **comes back changed**: you either show them to the people (+40 Favor and *The Prophet's Fever* for 60 days: −5% stability, +5% war support, +0.1 PP a day) or hide them until it passes (+20 Favor, −30 PP). | every 90 days |
| **Preach to the Faithful** | 30 Favor | Herald | +4% stability and +2% war support, plus another +3% stability if the leader is **Chosen**. It offsets the pact's stability penalties. | every 60 days |
| **Demand a Tithe from the Cult** | 50 Favor | Herald | +60 political power. | every 90 days |
| **Convene the Dark Council** | 40 Favor | Herald, an anointed general or admiral, or an avatar | *The Dark Council* for 120 days (+15% planning speed, +10% max planning, +5% organization) and +25 command power, or +50 if an avatar sits on the council. | every 180 days |
| **Review the Servitor Legions** | 20 PP | Herald, eldritch battalions in the field | +15 army experience, +3% war support, +10 Favor. | every 120 days |
| **March Beside [God]** | 50 Favor | Herald, the incarnate god on the map (Tier II) | *The Prophet Marches with the God* for 90 days: +10% attack, +10% morale, +5% war support. | every 120 days |
| **Speak the Name of [Enemy]** | 30 Favor | Herald; Cthulhu or Hastur; an enemy at war with you that carries your curse | The curse lasts 60 days longer and the enemy loses 3% war support. | every 60 days |
| **Raise the Great Temple** | 100 PP + 75 Favor | Herald | Built over 90 days. Adds *The Great Temple* for good (+5% stability, +0.15 PP a day) and **+3 Favor every month**. | once |
| **Become the Vessel** | 250 Favor | Tier III, the leader is **Chosen** | A 60-day ritual. The leader becomes a living vessel of the god and gains a powerful **Vessel** trait. You lose 10% stability, gain 10% war support, and the world hears of it. The trait goes with the leader if they are replaced. | once |

| God | Vessel trait |
|---|---|
| Cthulhu | **Flesh of the Sleeper**: +10% naval damage, +20% invasion speed, +10% war support, +0.15 PP a day, −5% stability |
| Nyarlathotep | **Mask of the Crawling Chaos**: +0.35 PP a day, +5% stability, −25% war goal justification time, +25% ideology drift defence |
| Hastur | **The Pallid Mask**: +15% morale, +5% organization, +15% war support, +10% air attack |
| Shub-Niggurath | **Womb of the Thousand Young**: +25% monthly population, +2% recruitable population, +3% reinforce rate, +0.1 PP a day |
| Yog-Sothoth | **The Key Made Flesh**: +10% research speed, +15% planning speed, +5% max factory efficiency |
| Azathoth | **Seat of the Daemon Sultan**: +10% attack and breakthrough, +10% factory output, −10% stability |

### 9. The Prophet's Mantle: a character sheet
The Prophet levels up like a role-playing character. **The Prophet's Record** (free, any time) opens the character sheet: level, experience, unspent Insight and three stats. The Forbidden Rites header shows a one-line summary.

| Stat | Each point gives | What it stands for |
|---|---|---|
| **Lore** | +2% research speed | knowledge of the rites and the old tongues |
| **Zeal** | +2% army attack | the fire that sends soldiers into battle |
| **Will** | +2% stability | what is left of the Prophet's own mind |

* **Experience** comes from every rite of the pact, scaled to its weight. Most rites give 10. Exalt the Prophet, the avatars, Commune, the Dark Council and March Beside the God give 25. Tier II, incarnations and the Great Temple give 50. Tier III and Become the Vessel give 100.
* **Levels** need 100 experience, then 50 more for each level after that. Each level brings a point of **Insight**. Spend it on a stat straight away when the level-up event appears, keep it and spend it later on the sheet, or save it for a perk (see **The Prophet's Path** below).
* **Stats** start at 1 and go up to 10. There aren't enough levels in a game to max all three, so your choices shape the Prophet.
* **The mantle belongs to the cult, not to one leader.** If the leader changes, the stats and levels stay, but the mantle's bonuses lapse until the new leader is marked by **Exalt the Prophet**.
* **Older saves:** a pact sealed before this update gets a level 1 mantle at its next monthly pulse, or as soon as you open the record.

### 10. Skill checks
The Prophet's stats decide how some rites turn out. A **rolled check** rolls d100 against odds that grow with one stat. The odds appear in the decision's tooltip and on the character sheet, and the roll and outcome are shown afterwards.

| Check | Stat | Odds at 1 / 5 / 10 | Success | Failure |
|---|---|---|---|---|
| **Commune** | Will | 64% / 80% / 95% | the Prophet asks the god for something | the Prophet comes back changed |
| **Curses** (Send Nightmares, Stage the Play, Whisper Madness) | Lore | 51% / 75% / 95% | the curse lands in full (90 days; Whispers: −8% stability and an ideology push) | it lands weakly (45 days; Whispers: −4% stability only) |
| **Preach to the Faithful** | Zeal | 46% / 70% / 95% | +3% more war support | the normal effect |
| **Incarnate the god** | Zeal | 36% / 60% / 90% | the god is pleased: 50 Favor back, +25 army experience | the normal effect |
| **Become the Vessel** | Will | 36% / 60% / 90% | the nation loses only 5% stability instead of 10% | the normal effect |

Odds never go below 5% or above 95%. Checks use the stats even while the mantle is unclaimed: the cult keeps what it has learned, even when the god's gifts lapse.

**Dialogue checks** are event options that only appear when the Prophet's stat is high enough. They are always a better deal than the ordinary options:

| Event | Needs | Option |
|---|---|---|
| The god demands tribute | Will 4 | Refuse, and make the god accept it: +2% stability, no Favor lost |
| A prophet in the streets | Zeal 4 | Make the street prophet one of ours: +20 Favor, +3% war support |
| The stars are right | Lore 4 | Read what the stars are really saying: +30 Favor and a 50% electronics research bonus |
| Dreams of the faithful | Zeal 3 | Turn the dream into a war cry: +10 Favor, +25 army experience |
| The Prophet communes | Lore 5 | Ask to be taught, not given: 100% research bonuses for an industry and a land doctrine tech, +10 Favor |
| The Prophet returns changed | Will 5 | The Prophet masters the fever: +40 Favor, +2% stability, no fever |

### 11. The Prophet's Path: a perk tree
A second decision category, **The Prophet's Path**, holds three paths of three perks, one path per stat. A perk costs **1 Insight**, the same points that raise stats, so every point is a choice between a stat and a perk. Each perk needs its stat at **2 / 4 / 6** and the perk before it. Perks belong to the mantle, so they survive a change of leader.

| | Tier 1 (stat 2) | Tier 2 (stat 4) | Tier 3 (stat 6) |
|---|---|---|---|
| **Lore**, the Scholar | **The Pnakotic Fragments**: +10% to every Lore check | **Curses That Linger**: curses last 30 days longer; Whisper Madness costs its target 3% more stability | **Forbidden Science**: +1 research slot |
| **Zeal**, the Zealot | **The Fervent Host**: servitor battalions get +15% soft attack, defense and breakthrough and +10 organization | **The Prophet's Banner**: +10% to every Zeal check; March Beside the God lasts 180 days | **Voice of the God**: the incarnate god gets +50% soft and hard attack, defense and breakthrough |
| **Will**, the Mystic | **Iron Composure**: +10% to every Will check, +3% stability | **The Elder Sign**: enemy cultists can no longer curse you, and any curse on you is lifted | **Apostolic Succession**: every new leader is marked by the god at once, so the mantle never lapses |

The category description and the character sheet show your Insight and how far along each path you are. AI Prophets sometimes bank Insight and walk the paths too.

### 12. The Prophet's Quests
A third category, **The Prophet's Quests**, holds multi-stage quests. Every cult can undertake three: two that any pact may attempt, and its patron's own great work.

1. **Begin.** The quest decision has a cost and a ritual of 30 to 60 days.
2. **Choose an approach.** An event decides which stat the finale will test. One approach is a dialogue check (Lore, or Zeal for Yog-Sothoth and Azathoth) worth **+20%** to the finale.
3. **The task.** A timed mission with a countdown in the mission bar asks you to use the pact's rites before time runs out. Rites performed since the quest began count, and only toward quests that are underway.
4. **The finale.** A skill check of **base + 7% per point** of the chosen stat, plus 10% with the perk that boosts that stat's checks (The Pnakotic Fragments, The Prophet's Banner or Iron Composure). Success brings a permanent **relic** spirit, 100 experience and 1 Insight. Failure has a price, gives 25 experience, and the quest can be begun again a year after that attempt began. Running out of time also fails the quest.

| Quest | Who | Begin | Task | Finale base | Relic (on success) | Failure |
|---|---|---|---|---|---|---|
| **Recover the Necronomicon** | any pact | 50 PP + 25 Favor, 30 days | Rite of Worship and Commune, within 120 days | 40% | **The Necronomicon**: +5% research, +0.1 PP a day | −3% stability, +20 Favor |
| **At the Mountains of Madness** | any pact, Tier II | 75 PP, 45 days | Dark Council and Preach, within 150 days | 35% | **The Elder Things' Archive**: +5% research, +5% factory output | −10k manpower, −3% stability |
| **Raise R'lyeh** | Cthulhu, Tier II | 100 Favor, 60 days | Call Forth the Servitors, then have Great Cthulhu walking or 12+ Deep One Brood battalions, within 180 days | 30% | **R'lyeh Risen**: naval damage, dockyards, invasions; plus two servitor divisions | −5% stability, −40 Favor |
| **The Thousand Masks** | Nyarlathotep | 100 Favor, 45 days | Whisper Madness twice, within 180 days | 35% | **The Thousand Masks**: +0.25 PP a day, ideology defence, faster war goals; plus 100 PP | −100 PP, −3% stability |
| **Stage the Full Play** | Hastur, at war | 100 Favor, 30 days | Stage the play in an enemy nation with war support above 50%, within 150 days | 30% | **The Full Play Performed**: morale, organization, war support; plus the Yellow Madness on every enemy | the Yellow Madness on yourself for 60 days |
| **The Hunt of the Thousand Young** | Shub-Niggurath | 25k manpower, 30 days | Rite of the Thousand Young with 50k manpower in reserve, within 120 days | 35% | **The Black Goat's Brood**: population, recruitment, reinforcement; plus two servitor divisions | −30k manpower, −3% stability |
| **Find the Silver Key** | Yog-Sothoth | 100 PP, 45 days | Open the Gate and Commune, within 180 days | 30% | **The Silver Key**: +10% research and planning; plus two 100% research bonuses | −5% stability, −40 Favor |
| **The Daemon Sultan's Engine** | Azathoth, Tier II | 150 Favor, 60 days | Bottle the Nuclear Chaos, within 180 days | 30% | **The Daemon Engine**: +15% factory output, +5% efficiency, −5% stability; plus two nuclear bombs | −8% stability, −5% war support |

The category description and the character sheet count your completed quests.

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
common/dynamic_modifiers/          the Prophet's mantle (character sheet stats as modifiers)
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
tools/generate_art.py              regenerates every texture and the thumbnail (`units` for the battalion icons only)
tools/art_portraits.py             the King in Yellow's painted portrait: forms sculpted and lit by
                                   art_render.py, then repainted stroke by stroke by art_paint.py
tools/art_units.py                 the battalion icons: each unit as a small scene (figures, mud or sea, smoky
                                   sky) rendered by art_render.py and graded like a worn war photograph, with
                                   the figures' silhouette as the white variant
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
* The god battalions carry `recon`, `initiative`, `casualty_trickleback` and `experience_loss_factor`, which vanilla normally gives only to support companies. If a future version stops reading them on a line battalion, the god loses just those extras.
* The hidden rite technologies, which have no tech-tree folder and are granted with `set_technology`.
* Icon sizes. The textures are 64×67 (spirits), 46×46 (decisions), 60×40 (battalions), 40×40 (traits), 156×210 (portraits) and 210×176 / 397×153 (events). If the UI expects different sizes, change the constants at the top of `tools/generate_art.py` (battalions: `ICON_SIZE` in `tools/art_units.py`) and regenerate.
