#!/usr/bin/env python3
"""Static checks for Eldritch Pacts. This is not a full HoI4 validator; it
catches the mistakes that are easy to make by hand:

  * unbalanced braces / unparseable script
  * missing localisation for decisions, ideas, traits, units, techs, events,
    tooltips and custom cost texts
  * custom battalion sprites without an entity, entities without a mesh
    definition, mesh definitions without a .mesh file, animation states
    without an animation on the mesh, animations whose .anim file is not
    next to the .asset that defines them (the game resolves it from there)
  * icons / pictures without a sprite, sprites without a texture file,
    battalions without a designer or map icon (or with one in the wrong
    size or frame count), traits without an icon, missing
    portrait files, dynamic modifiers without text or icon
  * scripted effects / triggers / events that are used but never defined
  * formables (set_cosmetic_tag): names for every ideology, flags in all
    three sizes as uncompressed TGA, and a map colour in
    common/countries/cosmetic.txt (the only file the game reads them from)
  * buildings: names, descriptions, special icons (two 36x36 frames, on a
    provincial building), hidden until a technology unlocks them, and only
    unlocked by technologies that exist
  * text icons (£name£) in localisation point to sprites that exist
  * doctrines: folders, tracks, grand doctrines and sub-doctrines refer to
    each other correctly, have names, icons and reward names, one milestone
    per track, and only touch battalions that exist
  * localisation file encoding (UTF-8 with BOM) and header

Usage:  python3 tools/validate_mod.py      (exit code 1 on problems)
"""

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|[{}]|[<>]=?|!=|==|=|[^\s{}=<>"#]+|#[^\n]*')


def tokenize(text):
    for m in TOKEN_RE.finditer(text):
        tok = m.group(0)
        if tok.startswith("#"):
            continue
        yield tok


def parse(text, path):
    """Parse Clausewitz script into nested lists of (key, op, value)."""
    tokens = list(tokenize(text))
    pos = 0

    def block():
        nonlocal pos
        items = []
        while pos < len(tokens):
            tok = tokens[pos]
            if tok == "}":
                pos += 1
                return items
            if tok == "{":
                pos += 1
                items.append((None, None, block()))
                continue
            if pos + 1 < len(tokens) and tokens[pos + 1] in ("=", "<", ">", "<=", ">=", "!=", "=="):
                key, op = tok, tokens[pos + 1]
                pos += 2
                if pos >= len(tokens):
                    raise SyntaxError(f"{path}: dangling '{key} {op}'")
                if tokens[pos] == "{":
                    pos += 1
                    items.append((key, op, block()))
                else:
                    items.append((key, op, tokens[pos]))
                    pos += 1
            else:
                items.append((tok, None, None))
                pos += 1
        return items

    items = block()
    if pos < len(tokens):
        raise SyntaxError(f"{path}: unexpected '}}' at top level (token {pos})")
    return items


def check_braces(text, path, problems):
    depth = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line).split("#", 1)[0]
        for ch in stripped:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    problems.append(f"{path}:{lineno}: closing brace without opening brace")
                    depth = 0
    if depth != 0:
        problems.append(f"{path}: {depth} unclosed brace(s)")


def walk(items):
    for key, op, value in items:
        yield key, op, value
        if isinstance(value, list):
            yield from walk(value)


def rel(path):
    return os.path.relpath(path, ROOT)


def load_script(pattern, problems):
    data = {}
    for path in sorted(glob.glob(os.path.join(ROOT, pattern), recursive=True)):
        text = open(path, encoding="utf-8-sig").read()
        check_braces(text, rel(path), problems)
        try:
            data[rel(path)] = parse(text, rel(path))
        except SyntaxError as e:
            problems.append(str(e))
    return data


def main():
    problems = []

    # ------------------------------------------------------------- localisation
    loc = {}
    for path in glob.glob(os.path.join(ROOT, "localisation", "**", "*.yml"), recursive=True):
        raw = open(path, "rb").read()
        if not raw.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{rel(path)}: missing UTF-8 BOM")
        lines = raw.decode("utf-8-sig").splitlines()
        if not lines or not re.match(r"^l_\w+:\s*$", lines[0]):
            problems.append(f"{rel(path)}: first line must be the language header (e.g. l_english:)")
        for lineno, line in enumerate(lines[1:], 2):
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = re.match(r'^ ([\w.\-]+):\d* "(.*)"\s*$', line)
            if not m:
                problems.append(f"{rel(path)}:{lineno}: malformed localisation line")
                continue
            key = m.group(1)
            if key in loc:
                problems.append(f"{rel(path)}:{lineno}: duplicate key {key}")
            loc[key] = m.group(2)

    def need_loc(key, where):
        if key not in loc:
            problems.append(f"missing localisation '{key}' ({where})")

    # ------------------------------------------------------------- sprites
    sprites = {}
    frames = {}
    for path, items in load_script("interface/*.gfx", problems).items():
        for key, _, value in walk(items):
            if key == "spriteType" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                name = fields.get("name", "").strip('"')
                tex = fields.get("texturefile", "").strip('"')
                sprites[name] = tex
                frames[name] = int(fields.get("noOfFrames", 1))
                if not os.path.exists(os.path.join(ROOT, tex)):
                    problems.append(f"{path}: sprite {name} points to missing texture {tex}")

    def need_sprite(name, where):
        if name not in sprites:
            problems.append(f"missing sprite '{name}' ({where})")

    # text icons in localisation: £name£ shows the sprite GFX_name
    for key, text in loc.items():
        for icon in re.findall(r"£([\w.]+)", text):
            if icon.startswith("eldritch_"):
                need_sprite(f"GFX_{icon}", f"text icon in {key}")

    # ------------------------------------------------------------- cosmetic tag colours
    # The game reads them from common/countries/cosmetic.txt and nowhere else.
    cosmetic_colours = set()
    for path, items in load_script("common/countries/cosmetic.txt", problems).items():
        for tag, _, body in items:
            if isinstance(body, list) and any(k == "color" for k, _, _ in body):
                cosmetic_colours.add(tag)

    # ------------------------------------------------------------- definitions
    scripted_effects = set()
    for path, items in load_script("common/scripted_effects/*.txt", problems).items():
        scripted_effects.update(k for k, _, v in items if isinstance(v, list))
    scripted_triggers = set()
    for path, items in load_script("common/scripted_triggers/*.txt", problems).items():
        scripted_triggers.update(k for k, _, v in items if isinstance(v, list))

    ideas = set()
    for path, items in load_script("common/ideas/*.txt", problems).items():
        for key, _, value in walk(items):
            if key == "country" and isinstance(value, list):
                for idea, _, body in value:
                    ideas.add(idea)
                    need_loc(idea, path)
                    need_loc(idea + "_desc", path)
                    pic = {k: v for k, _, v in body}.get("picture")
                    if pic:
                        need_sprite("GFX_idea_" + pic, f"{path} {idea}")

    dynamic_modifiers = set()
    for path, items in load_script("common/dynamic_modifiers/*.txt", problems).items():
        for name, _, body in items:
            dynamic_modifiers.add(name)
            need_loc(name, path)
            fields = {k: v for k, _, v in body}
            if "icon" in fields:
                need_sprite(fields["icon"], f"{path} {name}")
            if "custom_modifier_tooltip" in fields:
                need_loc(fields["custom_modifier_tooltip"], f"{path} {name}")

    traits = set()
    for pattern in ("common/country_leader/*.txt", "common/unit_leader/*.txt"):
        for path, items in load_script(pattern, problems).items():
            for key, _, value in items:
                if key == "leader_traits":
                    for trait, _, _ in value:
                        traits.add(trait)
                        need_loc(trait, path)
                        if "unit_leader" in path:
                            need_sprite("GFX_trait_" + trait, path)

    # 3D models: animation clips (gfx/models/**/*.asset), pdxmesh definitions
    # (gfx/entities/*.gfx) and entities (gfx/entities/*.asset)
    anims = set()
    for path, items in load_script("gfx/models/**/*.asset", problems).items():
        for key, _, value in items:
            if key == "animation" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                name, afile = fields.get("name", "").strip('"'), fields.get("file", "").strip('"')
                anims.add(name)
                # the game looks for the file next to the .asset that defines it
                if not os.path.exists(os.path.join(ROOT, os.path.dirname(path), afile)):
                    problems.append(f"{path}: animation {name} file {afile} is not in {os.path.dirname(path)}/")
    meshes = {}
    for path, items in load_script("gfx/entities/*.gfx", problems).items():
        for key, _, value in walk(items):
            if key == "pdxmesh" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                name, mfile = fields.get("name", "").strip('"'), fields.get("file", "").strip('"')
                meshes[name] = set()
                if not os.path.exists(os.path.join(ROOT, mfile)):
                    problems.append(f"{path}: pdxmesh {name} points to missing file {mfile}")
                for k, _, v in value:
                    if k == "animation" and isinstance(v, list):
                        anim = {ak: av.strip('"') for ak, _, av in v}
                        meshes[name].add(anim.get("id"))
                        if anim.get("type") not in anims:
                            problems.append(f"{path}: pdxmesh {name} uses undefined animation {anim.get('type')}")
    entities = set()
    for path, items in load_script("gfx/entities/*.asset", problems).items():
        for key, _, value in items:
            if key == "entity" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                entities.add(fields.get("name", "").strip('"'))
                mesh = fields.get("pdxmesh", "").strip('"')
                if mesh not in meshes:
                    problems.append(f"{path}: entity {fields.get('name')} uses undefined pdxmesh {mesh}")
                    continue
                states = {}
                for k, _, v in value:
                    if k == "state" and isinstance(v, list):
                        state = {sk: sv.strip('"') for sk, _, sv in v}
                        states[state.get("name")] = state.get("animation")
                for state, anim in states.items():
                    if anim not in meshes[mesh]:
                        problems.append(f"{path}: state {state} of {fields.get('name')} plays animation "
                                        f"{anim}, which {mesh} does not define")
                default = fields.get("default_state", "").strip('"')
                if default and default not in states:
                    problems.append(f"{path}: {fields.get('name')} has default_state {default} but no such state")

    subunits = set()
    for path, items in load_script("common/units/*.txt", problems).items():
        for key, _, value in items:
            if key == "sub_units":
                for unit, _, body in value:
                    subunits.add(unit)
                    need_loc(unit, path)
                    need_loc(unit + "_desc", path)
                    need_sprite(f"GFX_unit_{unit}_icon_medium", path)
                    need_sprite(f"GFX_unit_{unit}_icon_medium_white", path)
                    # The game reads battalion icons as two frames side by side (picture, NATO
                    # symbol): 152x42 in the designer, 60x12 inside the counter on the map.
                    for sprite, size in ((f"GFX_unit_{unit}_icon_medium", (152, 42)),
                                         (f"GFX_unit_{unit}_icon_medium_white", (60, 12))):
                        tex = sprites.get(sprite)
                        if not tex or not os.path.exists(os.path.join(ROOT, tex)):
                            continue
                        if frames.get(sprite) != 2:
                            problems.append(f"interface: {sprite} needs noOfFrames = 2")
                        with open(os.path.join(ROOT, tex), "rb") as f:
                            head = f.read(20)
                        h, w = int.from_bytes(head[12:16], "little"), int.from_bytes(head[16:20], "little")
                        if (w, h) != size:
                            problems.append(f"{tex}: {sprite} must be {size[0]}x{size[1]} (two frames), is {w}x{h}")
                    sprite = {k: v for k, _, v in body}.get("sprite", "")
                    if sprite.startswith("eldritch_") and sprite + "_entity" not in entities:
                        problems.append(f"{path}: {unit} uses sprite {sprite} but {sprite}_entity is not defined")

    # ------------------------------------------------------------- buildings
    buildings = set()
    for path, items in load_script("common/buildings/*.txt", problems).items():
        for key, _, value in items:
            if key == "buildings":
                for building, _, body in value:
                    buildings.add(building)
                    need_loc(building, path)
                    need_loc(building + "_desc", path)
                    fields = {k: v for k, _, v in body}
                    if "special_icon" in fields:
                        icon = fields["special_icon"]
                        need_sprite(icon, f"{path} {building}")
                        # The game shows a building's special icon in the province row of the
                        # state view, as it does for its own special buildings (dams, canals,
                        # landmarks, facilities), all of them provincial.
                        cap = fields.get("level_cap")
                        if not isinstance(cap, list) or not any(k == "province_max" for k, _, _ in cap):
                            problems.append(f"{path}: {building} has a special_icon, so it must be provincial "
                                            "(level_cap province_max)")
                        tex = sprites.get(icon)
                        if tex and os.path.exists(os.path.join(ROOT, tex)):
                            if frames.get(icon) != 2:
                                problems.append(f"interface: {icon} needs noOfFrames = 2")
                            with open(os.path.join(ROOT, tex), "rb") as f:
                                head = f.read(20)
                            h, w = int.from_bytes(head[12:16], "little"), int.from_bytes(head[16:20], "little")
                            if (w, h) != (72, 36):
                                problems.append(f"{tex}: {icon} must be 72x36 (two 36x36 frames), is {w}x{h}")
                    if fields.get("hide_if_missing_tech") != "yes":
                        problems.append(f"{path}: {building} must be hidden until its technology unlocks it")

    techs = set()
    for path, items in load_script("common/technologies/*.txt", problems).items():
        for key, _, value in items:
            if key == "technologies":
                for tech, _, body in value:
                    techs.add(tech)
                    need_loc(tech, path)
                    for k, _, v in body:
                        if k == "enable_building":
                            b = {kk: vv for kk, _, vv in v}.get("building")
                            if b and b.startswith("eldritch_") and b not in buildings:
                                problems.append(f"{path}: {tech} unlocks unknown building {b}")
                        if k == "enable_subunits":
                            for unit, _, _ in v:
                                if unit not in subunits:
                                    problems.append(f"{path}: {tech} enables unknown sub-unit {unit}")
                        elif isinstance(v, list) and k.startswith("eldritch_") and k not in subunits:
                            problems.append(f"{path}: {tech} modifies unknown sub-unit {k}")

    events = set()
    event_files = load_script("events/*.txt", problems)
    for path, items in event_files.items():
        for key, _, value in items:
            if key in ("country_event", "news_event") and isinstance(value, list):
                fields = {}
                for k, _, v in value:
                    fields.setdefault(k, []).append(v)
                eid = fields["id"][0]
                events.add(eid)
                if fields.get("hidden") == ["yes"]:
                    continue
                for k in ("title", "desc"):
                    for v in fields.get(k, []):
                        if isinstance(v, list):
                            text = {kk: vv for kk, _, vv in v}.get("text")
                            need_loc(text, f"{path} {eid}")
                        else:
                            need_loc(v, f"{path} {eid}")
                for pic in fields.get("picture", []):
                    need_sprite(pic, f"{path} {eid}")
                for opt in fields.get("option", []):
                    name = {kk: vv for kk, _, vv in opt}.get("name")
                    need_loc(name, f"{path} {eid}")

    # ------------------------------------------------------------- decisions
    decision_files = load_script("common/decisions/*.txt", problems)
    category_files = load_script("common/decisions/categories/*.txt", problems)
    categories = set()
    for path, items in category_files.items():
        for cat, _, body in items:
            categories.add(cat)
            need_loc(cat, path)
            need_loc(cat + "_desc", path)
            icon = {k: v for k, _, v in body}.get("icon")
            if icon:
                need_sprite("GFX_decision_category_" + icon, f"{path} {cat}")
    decision_names = set()
    for path, items in decision_files.items():
        for cat, _, decisions in items:
            if cat not in categories:
                problems.append(f"{path}: unknown decision category {cat}")
            for dec, _, body in decisions:
                decision_names.add(dec)
                need_loc(dec, path)
                need_loc(dec + "_desc", path)
                fields = {k: v for k, _, v in body}
                if "icon" in fields:
                    need_sprite("GFX_decision_" + fields["icon"], f"{path} {dec}")
                if "custom_cost_text" in fields:
                    need_loc(fields["custom_cost_text"], f"{path} {dec}")
                    need_loc(fields["custom_cost_text"] + "_blocked", f"{path} {dec}")
                    if "custom_cost_trigger" not in fields:
                        problems.append(f"{path}: {dec} has custom_cost_text without custom_cost_trigger")

    # ------------------------------------------------------------- references
    all_files = {}
    for pattern in ("common/**/*.txt", "events/*.txt"):
        all_files.update(load_script(pattern, problems))

    for path, items in all_files.items():
        for key, op, value in walk(items):
            if value == "yes" and key and key.startswith("eldritch_"):
                if key not in scripted_effects and key not in scripted_triggers:
                    problems.append(f"{path}: '{key} = yes' is not a scripted effect or trigger")
            if key in ("custom_effect_tooltip", "tooltip") and isinstance(value, str):
                need_loc(value, path)
            if key in ("add_ideas", "has_idea", "remove_idea", "add_idea") and isinstance(value, str):
                if value.startswith("eldritch_") and value not in ideas:
                    problems.append(f"{path}: unknown idea {value}")
            if key == "set_cosmetic_tag" and isinstance(value, str):
                # a formable: its name in every form and ideology, a map colour, and a flag in all three sizes
                if value not in cosmetic_colours:
                    problems.append(f"{path}: cosmetic tag {value} has no map colour in common/countries/cosmetic.txt")
                for ideology in ("", "_fascism", "_communism", "_democratic", "_neutrality"):
                    for form in ("", "_DEF", "_ADJ"):
                        need_loc(value + ideology + form, path)
                for folder, size in (("", (82, 52)), ("medium/", (41, 26)), ("small/", (10, 7))):
                    flag = os.path.join(ROOT, "gfx", "flags", folder + value + ".tga")
                    if not os.path.exists(flag):
                        problems.append(f"{path}: cosmetic tag {value} has no flag gfx/flags/{folder}{value}.tga")
                        continue
                    with open(flag, "rb") as f:
                        head = f.read(18)
                    w, h = int.from_bytes(head[12:14], "little"), int.from_bytes(head[14:16], "little")
                    if head[2] != 2 or (w, h) != size:
                        problems.append(f"{path}: flag gfx/flags/{folder}{value}.tga must be an uncompressed "
                                        f"{size[0]}x{size[1]} TGA (is type {head[2]}, {w}x{h})")
            if key == "activate_mission" and isinstance(value, str) and value not in decision_names:
                problems.append(f"{path}: activate_mission names unknown mission {value}")
            if key in ("add_dynamic_modifier", "remove_dynamic_modifier") and isinstance(value, list):
                mod = {k: v for k, _, v in value}.get("modifier")
                if mod not in dynamic_modifiers:
                    problems.append(f"{path}: unknown dynamic modifier {mod}")
            if key in ("add_timed_idea", "modify_timed_idea") and isinstance(value, list):
                idea = {k: v for k, _, v in value}.get("idea")
                if idea not in ideas:
                    problems.append(f"{path}: unknown timed idea {idea}")
            if key in ("add_country_leader_trait", "add_unit_leader_trait", "has_trait",
                       "has_country_leader_with_trait") and isinstance(value, str):
                if value not in traits:
                    problems.append(f"{path}: unknown trait {value}")
            if key == "traits" and isinstance(value, list):
                for trait, _, _ in value:
                    if trait not in traits:
                        problems.append(f"{path}: unknown trait {trait}")
            if key == "set_technology" and isinstance(value, list):
                for tech, _, _ in value:
                    if tech != "popup" and tech not in techs:
                        problems.append(f"{path}: unknown technology {tech}")
            if key == "regiments" and isinstance(value, list):
                for unit, _, _ in value:
                    if unit not in subunits:
                        problems.append(f"{path}: template uses unknown sub-unit {unit}")
            if key in ("country_event", "news_event") and isinstance(value, list) and not path.startswith("events"):
                eid = {k: v for k, _, v in value}.get("id")
                if eid not in events:
                    problems.append(f"{path}: fires unknown event {eid}")
            if key in ("country_event", "news_event") and isinstance(value, list) and path.startswith("events"):
                fields = {k: v for k, _, v in value}
                if "id" in fields and "is_triggered_only" not in fields:  # an effect, not a definition
                    eid = fields.get("id")
                    if eid not in events:
                        problems.append(f"{path}: fires unknown event {eid}")
            if key == "portrait_path" and isinstance(value, str):
                if not os.path.exists(os.path.join(ROOT, value.strip('"'))):
                    problems.append(f"{path}: portrait_path points to missing file {value}")
            if key == "add_tech_bonus" and isinstance(value, list):
                need_loc({k: v for k, _, v in value}.get("name"), path)
            if key == "localization_key":
                need_loc(value, path)
            if key in ("name", "text", "desc") and isinstance(value, str) and value.startswith('"RULE_'):
                need_loc(value.strip('"'), path)

    # Templates referenced by create_unit must be created somewhere.
    created_templates = set()
    for path, items in all_files.items():
        for key, _, value in walk(items):
            if key == "division_template" and isinstance(value, list):
                created_templates.add({k: v for k, _, v in value}.get("name", "").strip('"'))

    # ------------------------------------------------------------- doctrines (the 1.16 doctrine system)
    # Vanilla sprites our tracks reuse: the milestone icons and their frame.
    vanilla_doctrine_sprites = {"GFX_doctrine_milestone_infantry_land", "GFX_doctrine_milestone_armored_land",
                                "GFX_doctrine_milestone_operations_land", "GFX_doctrine_decor_land"}

    def doctrine_units(effects, where):
        for k, _, v in walk(effects):
            if isinstance(v, list) and k and k.startswith("eldritch_") and k not in subunits:
                problems.append(f"{where}: unknown sub-unit {k}")

    def mastery_units(body, where):
        for k, _, v in body:
            if k == "mastery":
                for kk, _, vv in v:
                    if kk == "sub_units":
                        for unit, _, _ in vv:
                            if unit.startswith("eldritch_") and unit not in subunits:
                                problems.append(f"{where}: mastery from unknown sub-unit {unit}")

    folders = {"land", "naval", "air"}
    for path, items in load_script("common/doctrines/folders/*.txt", problems).items():
        for folder, _, body in items:
            folders.add(folder)
            fields = {k: v for k, _, v in body}
            need_loc(fields.get("name", "").strip('"'), path)
            for k in ("tab_gfx", "ledger_gfx"):
                need_sprite(fields.get(k, "").strip('"'), f"{path} {folder}")
    tracks = set()
    for path, items in load_script("common/doctrines/tracks/*.txt", problems).items():
        for track, _, body in items:
            tracks.add(track)
            fields = {k: v for k, _, v in body}
            need_loc(fields.get("name", "").strip('"'), path)
            for k in ("background", "icon", "icon_frame"):
                name = fields.get(k, "").strip('"')
                if name not in vanilla_doctrine_sprites:
                    need_sprite(name, f"{path} {track}")
            mastery_units(body, f"{path} {track}")
    for path, items in load_script("common/doctrines/grand_doctrines/*.txt", problems).items():
        for gd, _, body in items:
            fields = {k: v for k, _, v in body}
            if fields.get("folder") not in folders:
                problems.append(f"{path}: {gd} is in unknown doctrine folder {fields.get('folder')}")
            need_loc(fields.get("name", ""), path)
            need_loc(fields.get("description", ""), path)
            need_sprite(fields.get("icon", ""), f"{path} {gd}")
            gd_tracks = [t for t, _, _ in fields.get("tracks", [])]
            for t in gd_tracks:
                if t not in tracks:
                    problems.append(f"{path}: {gd} uses unknown track {t}")
            milestones = [v for k, _, v in fields.get("milestones", []) if k is None]
            if len(milestones) != len(gd_tracks):
                problems.append(f"{path}: {gd} has {len(milestones)} milestones for {len(gd_tracks)} tracks")
            doctrine_units(body, f"{path} {gd}")
    for path, items in load_script("common/doctrines/subdoctrines/**/*.txt", problems).items():
        for sd, _, body in items:
            fields = {k: v for k, _, v in body}
            if fields.get("track") not in tracks:
                problems.append(f"{path}: {sd} is for unknown track {fields.get('track')}")
            need_loc(fields.get("name", ""), path)
            need_loc(fields.get("description", ""), path)
            need_sprite(fields.get("icon", ""), f"{path} {sd}")
            for reward, _, _ in fields.get("rewards", []):
                # reward names are localised as <sub-doctrine>_<reward>
                need_loc(f"{sd}_{reward}", path)
                need_loc(f"{sd}_{reward}_desc", path)
            doctrine_units(body, f"{path} {sd}")
            mastery_units(body, f"{path} {sd}")

    for path, items in all_files.items():
        for key, _, value in walk(items):
            if key == "create_unit" and isinstance(value, list):
                division = {k: v for k, _, v in value}.get("division", "")
                m = re.search(r'division_template = \\"([^\\]+)\\"', division)
                if not m or m.group(1) not in created_templates:
                    problems.append(f"{path}: create_unit uses a template that is never created: {division}")

    problems = list(dict.fromkeys(problems))
    if problems:
        print(f"{len(problems)} problem(s) found:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK: {len(loc)} localisation keys, {len(sprites)} sprites, {len(ideas)} ideas, "
          f"{len(traits)} traits, {len(subunits)} battalions, {len(techs)} techs, {len(events)} events, "
          f"{len(tracks)} doctrine tracks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
