#!/usr/bin/env python3
"""Static checks for Eldritch Pacts. This is not a full HoI4 validator; it
catches the mistakes that are easy to make by hand:

  * unbalanced braces / unparseable script
  * missing localisation for decisions, ideas, traits, units, techs, events,
    tooltips and custom cost texts
  * custom battalion sprites without an entity, entities without a mesh
    definition, mesh definitions without a .mesh file
  * icons / pictures without a sprite, sprites without a texture file,
    battalions without a designer icon, traits without an icon, missing
    portrait files
  * scripted effects / triggers / events that are used but never defined
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
    for path, items in load_script("interface/*.gfx", problems).items():
        for key, _, value in walk(items):
            if key == "spriteType" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                name = fields.get("name", "").strip('"')
                tex = fields.get("texturefile", "").strip('"')
                sprites[name] = tex
                if not os.path.exists(os.path.join(ROOT, tex)):
                    problems.append(f"{path}: sprite {name} points to missing texture {tex}")

    def need_sprite(name, where):
        if name not in sprites:
            problems.append(f"missing sprite '{name}' ({where})")

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

    # 3D models: pdxmesh definitions (gfx/entities/*.gfx) and entities (*.asset)
    meshes = {}
    for path, items in load_script("gfx/entities/*.gfx", problems).items():
        for key, _, value in walk(items):
            if key == "pdxmesh" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                name, mfile = fields.get("name", "").strip('"'), fields.get("file", "").strip('"')
                meshes[name] = mfile
                if not os.path.exists(os.path.join(ROOT, mfile)):
                    problems.append(f"{path}: pdxmesh {name} points to missing file {mfile}")
    entities = set()
    for path, items in load_script("gfx/entities/*.asset", problems).items():
        for key, _, value in items:
            if key == "entity" and isinstance(value, list):
                fields = {k: v for k, _, v in value}
                entities.add(fields.get("name", "").strip('"'))
                mesh = fields.get("pdxmesh", "").strip('"')
                if mesh not in meshes:
                    problems.append(f"{path}: entity {fields.get('name')} uses undefined pdxmesh {mesh}")

    subunits = set()
    for path, items in load_script("common/units/*.txt", problems).items():
        for key, _, value in items:
            if key == "sub_units":
                for unit, _, body in value:
                    subunits.add(unit)
                    need_loc(unit, path)
                    need_loc(unit + "_desc", path)
                    need_sprite(f"GFX_unit_{unit}_icon_medium", path)
                    sprite = {k: v for k, _, v in body}.get("sprite", "")
                    if sprite.startswith("eldritch_") and sprite + "_entity" not in entities:
                        problems.append(f"{path}: {unit} uses sprite {sprite} but {sprite}_entity is not defined")

    techs = set()
    for path, items in load_script("common/technologies/*.txt", problems).items():
        for key, _, value in items:
            if key == "technologies":
                for tech, _, body in value:
                    techs.add(tech)
                    need_loc(tech, path)
                    for k, _, v in body:
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
    for path, items in decision_files.items():
        for cat, _, decisions in items:
            if cat not in categories:
                problems.append(f"{path}: unknown decision category {cat}")
            for dec, _, body in decisions:
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
            if key in ("add_timed_idea",) and isinstance(value, list):
                idea = {k: v for k, _, v in value}.get("idea")
                if idea not in ideas:
                    problems.append(f"{path}: unknown timed idea {idea}")
            if key in ("add_country_leader_trait", "add_unit_leader_trait", "has_trait") and isinstance(value, str):
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
          f"{len(traits)} traits, {len(subunits)} battalions, {len(techs)} techs, {len(events)} events.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
