# Eldritch Pacts – Call of the Old Ones

A Hearts of Iron IV mod that lets any nation summon one of three Lovecraftian Old Ones (Cthulhu, Hastur or Azathoth), bind it in a pact, and spend its favor on blessings. Blessings buff the nation, give traits to its generals, admirals and leader, raise avatar commanders, and unlock unique eldritch battalions.

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
**Seek the Forbidden Lore** (25 PP, 30 days) reveals the three summoning rituals: Cthulhu, Hastur and Azathoth.

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
Favor is the currency of the pact. You gain it monthly (5 / 8 / 12 by tier), from **Hold a Rite of Worship** (15 PP → 15 Favor, every 30 days), from **Offer a Blood Sacrifice** (20k manpower → 40 Favor, every 60 days), from the god's random whims (events), and, for followers of Hastur, from the Road to Carcosa's buildings (up to +3 for Theatres, +2 for a Hall, +2 for an Observatory, +5 for the Palace; see 13).

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
| **Hastur** – the King in Yellow *(needs 30% war support)* | Army morale, air attack and agility, aces | **Zealots of the Yellow Sign** (unbreakable infantry), **Byakhee Riders** (paradrop-capable shock troops) – *Host of the Yellow Sign*; six more are earned by quests (see 13) | The Yellow Sign Unveiled (morale, org, war support) | **The Stranger in the Pallid Mask** | **Stage 'The King in Yellow'** – curse an enemy: −morale, −org, −stability for 90 days | +10% war support |
| **Azathoth** – the Daemon Sultan *(needs 50% war support, −10% stability)* | Attack, breakthrough, factory output, at a heavy stability cost | **Spawn of the Nuclear Chaos** (shock infantry), **Void Pipers** (sorcerous artillery) – *Chaos Horde* | Mindless Fury (attack, breakthrough, speed) | **The Piper of the Void** | **Bottle the Nuclear Chaos** – a nuclear bomb (Tier II+) | Two nuclear bombs |

### 5. The gods incarnate
From Tier II, **Incarnate [God] in the Flesh** brings the god onto the battlefield as a veteran division at your capital, with the world told what has happened. Only one incarnation can be on the map at a time: the decision stays locked while the god's division exists and reopens once it is destroyed (still at most once a year, for 200 Favor). Each incarnate division is a single colossal **god battalion**: the god fights alone, and is the whole division.

**The King in Yellow is different.** He walks only for Carcosa: Hastur's followers can incarnate him only after proclaiming Carcosa (13). In return he is **twice as mighty as any other god**: 4,000 strength, 600 organization (+200 from the incarnation, +60 at Tier III), 95% hardness, +1,700% soft and hard attack, +2,100% defense and breakthrough, +600% piercing (rising to +1,900% / +2,300% at Tier III), recon 6, +100% initiative, 90% of casualties returned, and +120% attack in hills, mountains and cities.

| God | Division | Terrain where the god is strongest |
|---|---|---|
| Cthulhu | **Great Cthulhu** | sea landings, rivers, marsh |
| Hastur | **The King in Yellow** | hills, mountains, cities |
| Azathoth | **Fragment of Azathoth** | plains, desert, cities |

What every other god battalion has:

* **2,000 strength** (eighty infantry battalions' worth) and **300 organization**, plus 100 more from the incarnation and 30 more at Tier III, recovering at 100%.
* **90% hardness**, so soft attacks (rifles, machine guns, artillery) barely scratch it; only anti-tank weapons hurt it properly.
* **+800% soft and hard attack, +1,000% defense and breakthrough, +250% piercing** and **+75% speed**, rising to +900% / +1,100% at Tier III.
* Its own **recon (3)**, **initiative (+50%)** and field-hospital recovery (three quarters of its casualties return, half the experience loss).
* **Large bonuses in its favoured terrain** from the table above, for example +200% attack in sea landings for Great Cthulhu.
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

A division is drawn with the model of its highest-priority battalion, so the *Host of the Yellow Sign* shows a Byakhee rider and the King's division shows the King himself. Of the battalions earned on the Road to Carcosa, Cassilda's Choir, the Pallid Masks and the King's Tatters use the Zealot model; the Lidless, the Audience and Hali's Drowned use vanilla infantry.

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
| Hastur | **The Pallid Mask**: +15% morale, +5% organization, +15% war support, +10% air attack |
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
2. **Choose an approach.** An event decides which stat the finale will test. One approach is a dialogue check (Lore, or Zeal for Azathoth) worth **+20%** to the finale.
3. **The task, on the map.** Each quest marks a place when it begins, and a timed mission with a countdown in the mission bar highlights it. You act there, by taking the place or with a decision you click on the map at it (shown on the map and in the decisions view), before time runs out.
4. **The finale.** A skill check of **base + 7% per point** of the chosen stat, plus 10% with the perk that boosts that stat's checks (The Pnakotic Fragments, The Prophet's Banner or Iron Composure). Success brings a permanent **relic** spirit, 100 experience and 1 Insight. Failure has a price, gives 25 experience, and the quest can be begun again a year after that attempt began. Running out of time also fails the quest.

| Quest | Who | Begin | Task | Finale base | Relic (on success) | Failure |
|---|---|---|---|---|---|---|
| **Recover the Necronomicon** | any pact | 50 PP + 25 Favor, 30 days | The book is kept in the capitals of Britain, France, Argentina and the United States (marked). Hold one of those states, or **steal it** from one on the map (25 Favor, 45 days), within 120 days | 40% | **The Necronomicon**: +5% research, +0.1 PP a day | −3% stability, +20 Favor |
| **At the Mountains of Madness** | any pact, Tier II | 75 PP, 45 days | The expedition sails from a southern port: the coastal capital of Australia, New Zealand, Argentina, Chile or South Africa (marked). **Send it** from one we hold or whose owner isn't at war with us (50 PP, a 60-day voyage), within 150 days | 35% | **The Elder Things' Archive**: +5% research, +5% factory output | −10k manpower, −3% stability |
| **Raise R'lyeh** | Cthulhu, Tier II | 100 Favor, 60 days | R'lyeh rises off a coast of Oceania we and our allies don't hold, picked when the quest begins (marked). Hold that state, or **call the Deep Ones** to it on the map with Great Cthulhu walking or 12+ Deep One Brood battalions (30 Favor, 30 days), within 180 days | 30% | **R'lyeh Risen**: naval damage, dockyards, invasions; plus two servitor divisions | −5% stability, −40 Favor |
| **Stage the Full Play** | Hastur, at war | 100 Favor, 30 days | **Stage the premiere** at an enemy capital (marked) while our troops hold a state next to it (25 PP, 14 days; its nation loses 3% war support), and have war support above 50%, within 150 days | 30% | **The Full Play Performed**: morale, organization, war support; plus the Yellow Madness on every enemy, and the **Audience** battalion | the Yellow Madness on yourself for 60 days |
| **The Daemon Sultan's Engine** | Azathoth, Tier II | 150 Favor, 60 days | **Raise the Engine** in one of our states with 3+ civilian factories (marked; 50 PP, 60 days, consumes 2 of them) and keep that state, and Bottle the Nuclear Chaos, within 180 days | 30% | **The Daemon Engine**: +15% factory output, +5% efficiency, −5% stability; plus two nuclear bombs | −8% stability, −5% war support |

The category description and the character sheet count your completed quests.

### 13. The Road to Carcosa: Hastur's questline and formable
Hastur's cults get their own category, **The Road to Carcosa**: six chapters. Chapter I opens when the pact is sealed, and each chapter opens the next. A chapter is a single decision whose requirements are its **goals**: lands to **conquer**, the cult's own **buildings** to raise, and other aims. The decision's tooltip ticks off each goal as you meet it. Each chapter highlights its places on the map when you hover over it, and some goals are decisions you click at a state on the map (they show on the map and in the decisions view). When all are met, complete the chapter (it costs Favor) to collect its rewards: experience and Insight for the Prophet, and the next stage of the national spirit **The Road to Carcosa** (I to V). There is no time limit and no dice roll; the goals are the challenge.

| Chapter | Cost | Goals | Rewards |
|---|---|---|---|
| **I. Have You Seen the Yellow Sign?** | 50 Favor | A **Theatre of the Yellow Sign** in your capital; at least 40% war support; the **Yellow Sign** shown in a foreign capital on your continent (a decision on the map: 25 Favor, 30 days; its nation loses 2% stability) | Road I (+5% war support, +3% morale), +3% war support, the **Lidless** |
| **II. Cassilda's Song** | 75 Favor | **Theatres of the Yellow Sign** in at least 3 of your states; **Cassilda's Song** sung across your border from one of them (a decision on the map: 25 PP, 21 days; the state's nation loses 2% war support); at least 9 Zealot battalions in the field | Road II (adds +3% research), +30 Favor, **Cassilda's Choir** |
| **III. The Stranger in the Pallid Mask** | 100 Favor | Tier II pact; **hold the state where the Stranger was last seen**, marked when the chapter opens (on your border, an enemy's if you're at war; **Follow the Stranger**, 50 PP every 90 days, marks another); build the **Hall of the Pallid Masque** | Road III (adds +3% organization), +50 command power, the **Pallid Masks** |
| **IV. Black Stars Rise** | 100 Favor | Tier III pact; **Black Star Observatories** in at least 2 of your states | Road IV (adds political power), +5% war support |
| **V. The King Walks** | 150 Favor | **Conquer 10 more states** than you controlled when the chapter opened; **the King walks** through a city that was another nation's capital when the game began, once you hold it (a decision on the map, 7 days) | Road V (adds +5% stability), +50 army experience, the **King's Tatters** |
| **VI. The Throne of Carcosa** | 200 Favor | The **Palace of the Yellow King** in your capital; the Prophet is Hastur's Vessel or Chosen | unlocks **Proclaim Carcosa**, **Hali's Drowned** |

#### The cult's buildings
The chapters unlock four buildings. Every country sees them in the construction menu, but they stay locked, with a tooltip naming the chapter that unlocks them, until a follower of Hastur opens that chapter (each is unlocked by a hidden technology). Each is built in a province, like a dam or a facility, can be built once per state, and doesn't take a building slot. Each has its own icon: a playhouse with its curtains open on the Yellow Sign, the pallid mask before a lit ballroom window, a domed observatory under black stars, and the gold palace under twin suns with a crown on its spire. The icon shows in the view of the province where one stands, in its description, and next to each goal that asks for it.

**In the construction menu** each building has its own picture too. The game draws every building's picture there from one image strip (`GFX_buildings_strip`, one 46×46 frame per building, picked by `icon_frame`), so the mod ships the game's strip with four frames added after its 31: a playhouse front open on the Yellow Sign, the pallid mask in a ballroom window, a domed observatory under black stars, and the crowned palace before the twin suns, drawn in the game's own style (orange glyph on a dark tile).

| Building | Unlocked by | Cost | Effects |
|---|---|---|---|
| **Theatre of the Yellow Sign** | Chapter I | 3,000 | +20% manpower and +10% non-core manpower in its state; per Theatre, +1% war support and +2% compliance growth; +1 Favor a month (+2 with three, +3 with five) |
| **Hall of the Pallid Masque** | Chapter III | 6,000 | +15% command power gain, +15 maximum command power, new generals start a level higher, +15% encryption; +2 Favor a month |
| **Black Star Observatory** | Chapter IV | 8,000 | +3% research speed, +10% decryption, −15% air night penalty, −10% air weather penalty; +2 Favor a month |
| **Palace of the Yellow King** | Chapter VI | 15,000 | +15% political power, +5% stability, +5% war support, +5% army morale, +50% resistance to ideology drift; in its state +15% construction speed and +20% building slots; +5 Favor a month |

The AI doesn't build special buildings by itself, so an AI follower of Hastur gets each chapter's buildings placed for free when the chapter opens. It still has to do the conquering, though in Chapter III it may conquer any 5 states instead of the Stranger's, and it is spared Cassilda's Song.

**Older saves:** a follower of Hastur whose pact was sealed before the chapters had goals gets the first chapter it hasn't finished (and the buildings of every chapter before it) when the game is loaded, or at the next monthly pulse.

#### Battalions earned on the road
Hastur's quests also unlock six new battalions, one per quest, for the division designer. Each arrives with an editable template and a first veteran division of it at the capital. Like Hastur's other battalions, they grow stronger with the Rites of Carcosa II and III and the Fervent Host perk. Their in-game descriptions say what they are; none of it is pleasant.

| Battalion | Earned by | Role | First division |
|---|---|---|---|
| **The Lidless** | Chapter I | Defensive line infantry: 75 organization, +20% defense, and bonuses defending cities, forests and hills | *The Lidless Watch*: 6 Lidless, 3 Zealots |
| **The Audience** | Stage the Full Play | Cheap mass infantry: 40 strength, 0.8 morale, 30 days to train and 1,400 manpower, but only 40 infantry equipment, so they hit softly | *The Second Act*: 9 Audience |
| **Cassilda's Choir** | Chapter II | Line artillery (width 3): 14 artillery equipment, +20% soft attack | *Cassilda's Choir*: 6 Zealots, 2 Choirs |
| **The Pallid Masks** | Chapter III | Assault infantry: 80 organization, +30% breakthrough, +15% soft attack, and bonuses attacking in cities and forests | *The Masque*: 6 Masks, 3 Byakhee Riders |
| **The King's Tatters** | Chapter V | Heavy shock troops (width 3): 50 strength, 35% hardness, +30% breakthrough, +20% soft attack, +15% defense | *The Tatters of the King*: 4 Tatters, 3 Zealots |
| **Hali's Drowned** | Chapter VI | Amphibious infantry: +40% attack in landings, +30% attack and +50% movement across rivers, and marsh bonuses | *Hali's Drowned*: 6 Drowned, 2 Choirs |

**Proclaim Carcosa** (100 PP, needs 25% stability) is the formable. It works for any country, as a cosmetic tag:

* **Name:** the nation is called **Carcosa**, whatever its ideology. Its adjective becomes *Carcosan*.
* **Flag:** the King in Yellow, crowned and antlered with the Yellow Sign on its robe, between two sigils, in gold on a black field between two gold bands.
* **Map colour:** deep yellow.
* **The King walks:** only now can a follower of Hastur incarnate the King in Yellow (see 5).
* **Spirit:** The Road to Carcosa becomes **The Yellow Throne**: +15% war support and morale, +8% organization and research speed, +5% attack, +10% stability, +0.3 PP a day.
* **News:** the rest of the world hears of it.
* **The King's Play begins:** Carcosa becomes a crisis for the whole world (below).

#### The King's Play: Carcosa as a world crisis
Like a crisis in Stellaris, Carcosa grows more terrible the longer it lasts, and the world answers it. A new decision category, **The King's Play**, shows Carcosa's **Dread**, the Act the play has reached and the next one.

**Dread** grows every month at war (+2), for every Theatre of the Yellow Sign (+1), for every enemy under the Yellow Madness (+2) and while the King in Yellow walks the earth (+3); with every state taken from an enemy (+3), every staging of the King in Yellow (+10), every Black Stars Rise (+5), every Unmasking (+40) and every enemy that capitulates to Carcosa (+25). It falls with every state lost (−3), every month without the Palace of the Yellow King (−10), when the King's division is destroyed (−50), with every Theatre the Elder Sign Accord exorcises (−15), and by half if Carcosa capitulates. An Act, once begun, never ends.

| Act | Dread | Carcosa gains | The world answers |
|---|---|---|---|
| **I. The Sign Spreads** | at the proclamation | Every state Carcosa controls with a **Theatre** becomes its **core**, now and later. The **Yellow Fever** spreads into the foreign states on its borders (−15% manpower, construction speed and supply, 60 days at a time). | World tension rises. |
| **II. The Tattered Host** | 100 | **The Tattered Host** (+5% organization, attack, reinforcement), +10% soft attack and +10 organization for every Hastur battalion, and every general gets the **King's mark** (Hastur's general trait). | News: something is wrong in Carcosa. World tension rises. |
| **III. Black Stars** | 250 | **Black Stars Rise over [state]** (50 Favor, once every 60 days, a decision on the map): an enemy state on the front and its enemy-held neighbours get −40% supply, −30% manpower and construction speed, +20% factory sabotage for 30 days. | **The Stars Are Wrong** (−5% stability) for every nation that doesn't follow Hastur. The great powers are asked to join the **Elder Sign Accord** (AI: 80% yes), which gives them a war goal against Carcosa. |
| **IV. The Unmasking** | 450 | **Unmask [nation]** (100 Favor, 30 days): a nation at peace with Carcosa with stability below 50% becomes its **puppet** if its stability is under 25% when the masks come off, or the cult rises against its government in a **civil war**. | The Accord and every great power at peace with Carcosa get **The Investigators** (+5% attack, defence and stability) and a war goal against it. |

| **V. Lost Carcosa** | 700 | **Raise Lost Carcosa** (below). | Every great power and Accord member not yet at war with Carcosa gets the Investigators and **declares war on it**. |

**Raise Lost Carcosa** is the endgame, like the Aetherophasic Engine: five stages, each a decision that needs the Palace of the Yellow King held for as long as it takes (it is cancelled if the Palace falls). Each casts the **Shadow of Carcosa** deeper over every nation that doesn't follow Hastur.

| Stage | Needs | Cost, time | The world |
|---|---|---|---|
| **I. The Hyades Rise** | the Palace | 100 Favor, 60 days | Shadow I: −10% stability |
| **II. The Twin Suns** | 3 cities that were other nations' capitals at game start (counted monthly) | 150 Favor, 60 days | Shadow II: also −10% factory output |
| **III. Cassilda's Song** | the King walking; 8+ Theatres | 150 Favor, 60 days | Shadow III: also −5% war support; the Yellow Madness on every nation at war with Carcosa for 180 days |
| **IV. The Black Stars** | 900 Dread | 200 Favor, 90 days | Shadow IV: −15% stability, −10% factory output, −5% war support, −10% army organization and morale |
| **V. Carcosa Returns** | 1000 Dread | 250 Favor, 90 days | **The end of the play** |

The world sees each stage in the news and can fight back: if Carcosa loses its Palace, the project falls back a stage (at most once every 60 days), and if Carcosa capitulates, it starts over. The nations of the **Elder Sign Accord** get their own decision category with **Exorcise [state]** (25 PP, 30 days, a decision on the map): in a state they hold where a Theatre stands, every Carcosa loses 15 Dread and that Theatre doesn't count for it for a year.

**Carcosa Returns** ends the play in the King's victory: every nation at war with Carcosa becomes its puppet, every other nation that doesn't follow Hastur falls under the Yellow Madness for good, and Carcosa gains **The King Reigns** (+20% stability, war support and political power, +10% factory output). The game goes on in the world the King has won.

**The Yellow Empire** is the second formable, unlocked by Carcosa Returns: **Proclaim the Yellow Empire** (100 PP, in the King's Play) renames the nation the **Yellow Empire** (whatever its ideology; adjective *Carcosan*), gives it its own flag (Carcosa's turned around: the King in black on a gold field between crimson bands) and an amber map colour, and makes **every state it controls its core**. The world hears of it.

### 14. The gods' doctrines
Sealing a pact opens a fourth doctrine tab, **Eldritch**, next to land, naval and air. It holds one grand doctrine for each god, and a country only ever sees its own patron's: the doctrine, its sub-doctrines and their rewards are visible and available only to the god's followers. It works alongside your land doctrine rather than replacing it.

The grand doctrine costs 100 army experience, and each sub-doctrine 50. Each grand doctrine has three tracks. Mastery comes from the units in that track, and each track ends in a milestone:

* **The Servitors**: mastery from your god's own battalions (six times as fast as from ordinary troops, because there are few of them).
* **The Faithful**: mastery from your infantry.
* **Rites of War**: mastery from your whole army.

| God | Grand doctrine | The Servitors | The Faithful | Rites of War |
|---|---|---|---|---|
| Cthulhu | **The Rising Tide**: +25% invasion speed, +10 invasion capacity; milestones add invasion prep, reinforcement and smaller invasion penalties | **The Brood of Dagon**: Deep Ones fight in rivers and marshes, Star-Spawn hit harder, more organization, morale and recovered casualties | **The Esoteric Order of Dagon**: infantry organization, defense and morale, marsh and river attacks, faster invasion prep | **Dreams of the Sleeper**: morale, planning, organization, invasion capacity, breakthrough |
| Hastur | **The Yellow Sign**: +10% army morale; milestones add Infantry Charge, Relentless Assault, paradrop organization and weather-proof aircraft | **The Host of Carcosa**: all eight of Hastur's battalions, including those from the Road to Carcosa | **The Second Act**: infantry morale and organization, war support, less organization loss when broken | **The Winds of Hali**: aircraft fly in any weather, by night and faster; enemy air superiority counts for less |
| Azathoth | **The Nuclear Chaos**: +5% army attack but −5% organization; milestones add Blitz, Relentless Assault and Barrage | **The Court of the Daemon Sultan**: Chaos Spawn tear through armour, Void Pipers hit harder | **The Mindless Dancers**: infantry soft attack and morale, breakthrough | **The Blind Idiot God**: artillery attack, army attack, morale |

---

## Game rule

**AI Eldritch Pacts** (game rules screen, *Eldritch Pacts* group):
* **Disabled** (default): only human players summon gods.
* **Allowed**: AI nations may seek the lore, bind a god and use its blessings.

---

## Compatibility

* One vanilla file is replaced: `common/countries/cosmetic.txt`, the only file the game reads cosmetic tags' map colours from, so Carcosa can be yellow and the Yellow Empire amber. The mod's copy holds only the mod's formables (Carcosa and the Yellow Empire), so while the mod is on, the game's other cosmetic tags (focus-tree renames) show their nation's normal colour, and a mod that also replaces that file will clash (whichever loads last wins; Carcosa's entry can be copied into the other mod's file). 
* One vanilla sprite is replaced: `GFX_buildings_strip`, the construction menu's building pictures, so the Carcosa buildings can have their own. The mod's strip keeps all 31 of the game's pictures in place and adds four after them. A mod that also replaces that strip will clash (whichever loads last wins), and if a game update adds pictures to it, the mod's copy needs updating (see the testing notes). Nothing else of the game's is overwritten.
* Every other key, flag, variable and file uses the `eldritch_` prefix, so the mod should work alongside most other mods, including total conversions that keep the standard decision system.
* No DLC is required.
* Achievements are disabled, as with any mod.

---

## Files

```
common/decisions/                  decision categories and decisions (the King's Play's own in eldritch_crisis_decisions.txt)
common/ideas/                      pact spirits, timed blessings, curses
common/country_leader/             Herald / Chosen leader traits
common/unit_leader/                general, admiral and avatar traits
common/units/                      the 12 servitor battalions and the 3 gods incarnate
common/technologies/               hidden "rite" techs that unlock and buff the battalions
common/scripted_effects|triggers/  shared logic (summoning, blessings, tiers, favor); eldritch_crisis_effects.txt is the King's Play
common/scripted_localisation/      [ROOT.GetEldritchGodName] etc.
common/dynamic_modifiers/          the Prophet's mantle (character sheet stats as modifiers); the Yellow Fever and Black Stars (states)
common/doctrines/                  the Eldritch doctrine folder: its tracks, the gods' grand doctrines and sub-doctrines
common/countries/cosmetic.txt      the formables' map colours, Carcosa and the Yellow Empire (replaces the game's file of cosmetic tag colours)
common/buildings/                  the four buildings of the Road to Carcosa, locked until a chapter unlocks them
common/game_rules/                 the AI rule
common/on_actions/                 welcome pop-up at game start; records each nation's starting capital (Road to Carcosa, Chapter V);
                                   the King's Play's Dread from states taken and lost and from capitulations
events/                            summoning, tier, whim, curse, news and monthly-pulse events; eldritch_crisis_events.txt is the King's Play
interface/eldritch.gfx             sprite definitions
gfx/                               generated art (DDS): spirit, decision, battalion and trait icons, Carcosa's flags (gfx/flags),
                                   event pictures, and avatar portraits (gfx/leaders/eldritch/)
localisation/english/              all text (UTF-8 with BOM)
install/eldritch_pacts.mod         launcher file to copy into your mod/ folder
gfx/entities/                      King in Yellow mesh definitions (.gfx) and unit entities with their animation states (.asset)
gfx/models/units/eldritch/         King in Yellow .mesh models, .anim animations, their definitions and the texture atlas
tools/generate_art.py              regenerates every texture and the thumbnail (`units` for the battalion icons only,
                                   `doctrines` for the doctrine tab, icons and track backgrounds only)
tools/art_sources/                 source art the generator reads (carcosa_flag.png: Carcosa's flag, and the Yellow Empire's from it;
                                   building_icon_strip.dds: the game's own building strip, which the mod's extends)
tools/art_portraits.py             the King in Yellow's painted portrait: forms sculpted and lit by
                                   art_render.py, then repainted stroke by stroke by art_paint.py
tools/art_units.py                 the battalion icons: each unit as a small scene (figures, mud or sea, smoky
                                   sky) rendered by art_render.py and graded like a worn war photograph, laid
                                   out in the game's two-frame textures: the scene and a NATO symbol for the
                                   designer (counters/divisions_large, 152×42), and the figures' silhouette and
                                   the same symbol for the division counter on the map (counters/divisions_small, 60×12)
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
* **The Road to Carcosa's buildings.** They are written like the game's own special buildings (facilities, dams, canals, landmarks): provincial (`province_max = 1`, with `state_max = 1` for one per state), locked until their technology unlocks them (`missing_tech_loc` says how; they are not hidden, so you can always find them in the construction menu), and each with its own `special_icon` (two 36×36 frames, sized for the province building slot, shown only where one stands with `only_display_if_exists`; the validator enforces the size). The same pictures, 20×20, are text icons (`£eldritch_building_<name>_text£`) in their descriptions and the chapter goals. The construction menu shows `icon_frame`, a frame of `GFX_buildings_strip` counted from 1 (checked against the game's own buildings: the naval supply hub is 28, the naval headquarters 29). The mod's strip is the game's 1.16 strip (31 frames) with the four buildings as frames 32 to 35; if a game update adds frames to its strip, put the new `gfx/interface/buildings/building_icon_strip.dds` in `tools/art_sources/`, run `python3 tools/generate_art.py buildings` and move the buildings' `icon_frame` up to match. The AI's free buildings go in the state's first province (`province = { all_provinces = yes first = yes }`). Conquest goals compare `num_controlled_states` with a target recorded when the chapter opens.
* **The King's Play.** Dread from conquest and capitulation uses the game's `on_state_control_changed` (read as: ROOT the new controller, FROM the old) and `on_capitulation` (ROOT the nation that capitulated, FROM the winner) hooks; if Dread moves the wrong way when states change hands, those scopes are the other way round. The Yellow Fever and Black Stars are dynamic modifiers on states; The Stars Are Wrong, The Investigators and the Shadow of Carcosa remove themselves (`cancel`) when no Carcosa has reached their Act or stage. The ending's puppets use `puppet`, which ends the puppet's wars. Unmasking uses `puppet` and `start_civil_war` (the cult's side is fascist).
* **The quests' map objectives.** Each quest marks its place with state flags (the libraries, the ports) or a state kept in a variable (R'lyeh's shore, the Engine's site, read as `var:`), its mission highlights it with `highlight_states`, and the action there is a state-targeted decision (`state_target = yes`, shown on the map and in the decisions view). The libraries and ports are found from the capitals of fixed nations (no state IDs), so they follow a government that moves its capital. If a quest's decision doesn't appear on the map, check `error.log` for the decision's name.
* **The Eldritch doctrines.** They follow the format of the game's own doctrine files and use only modifiers, battalion stats and tactics that exist. The tab is a custom folder like the game's own special forces folder. Untested parts: the icon size (54×58, matched to the doctrine list's layout), the tab texture (512×61 in two frames, like the land tab), and the track backgrounds (400×700; the UI clips the edges). The tracks reuse the game's own milestone icons. Reward names are localised as `<sub-doctrine>_<reward>`; if a reward shows its raw key in game, the game expects a different pattern.
* Icon sizes. The textures are 64×67 (spirits), 46×46 (decisions), 152×42 and 60×12 (battalions: two frames each, picture then NATO symbol; the validator enforces these), 40×40 (traits), 156×210 (portraits) and 210×176 / 397×153 (events). If the UI expects different sizes, change the constants at the top of `tools/generate_art.py` (battalions: `ICON_SIZE`, `DESIGNER_FRAME` and `MAP_FRAME` in `tools/art_units.py`) and regenerate.
