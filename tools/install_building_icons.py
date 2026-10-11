#!/usr/bin/env python3
"""Give the Road to Carcosa's buildings their own pictures in the construction menu.

The construction menu draws every building's picture from one image strip that
belongs to the game (the sprite GFX_buildings_strip), picked by the building's
icon_frame. A mod can't add frames to it without the game's own image, so this
script, run on your computer, does it from your copy of the game:

  1. reads the game's strip (the texture of GFX_buildings_strip),
  2. appends the four building pictures (gfx/interface/buildings/
     eldritch_building_strip_frames.dds, drawn by tools/generate_art.py),
  3. writes the result into the mod, with a sprite that replaces
     GFX_buildings_strip (every vanilla picture is kept, in its place),
  4. points the buildings' icon_frame at the new frames.

    python3 tools/install_building_icons.py "C:/Program Files (x86)/Steam/steamapps/common/Hearts of Iron IV"
    python3 tools/install_building_icons.py              # looks in the usual Steam folders
    python3 tools/install_building_icons.py --remove     # undo

Needs Python 3 and Pillow (pip install pillow). Run it again after a game update
(the strip may change) or after downloading a fresh copy of the mod. A mod that
also replaces GFX_buildings_strip will clash with this: whichever loads last wins.
"""

import glob
import os
import re
import struct
import sys

from PIL import Image

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(MOD, "gfx", "interface", "buildings", "eldritch_building_strip_frames.dds")
OUT_TEXTURE = "gfx/interface/buildings/eldritch_building_icon_strip.dds"
# named to load after the game's own interface files, so its GFX_buildings_strip wins
OUT_GFX = os.path.join(MOD, "interface", "zz_eldritch_buildings_strip.gfx")
BUILDINGS_FILE = os.path.join(MOD, "common", "buildings", "eldritch_buildings.txt")

# the buildings, in the order of their frames in FRAMES, with the vanilla frame each
# uses when this script hasn't been run (restored by --remove)
BUILDINGS = [
    ("eldritch_yellow_theatre", 23),
    ("eldritch_masque_hall", 23),
    ("eldritch_black_star_observatory", 14),
    ("eldritch_yellow_palace", 23),
]

STEAM_FOLDERS = [
    "C:/Program Files (x86)/Steam/steamapps/common/Hearts of Iron IV",
    "C:/Program Files/Steam/steamapps/common/Hearts of Iron IV",
    "D:/SteamLibrary/steamapps/common/Hearts of Iron IV",
    "~/.local/share/Steam/steamapps/common/Hearts of Iron IV",
    "~/.steam/steam/steamapps/common/Hearts of Iron IV",
    "~/Library/Application Support/Steam/steamapps/common/Hearts of Iron IV",
]


def fail(msg):
    print("Error: " + msg)
    sys.exit(1)


def find_game(arg):
    candidates = [arg] if arg else STEAM_FOLDERS
    for folder in candidates:
        folder = os.path.expanduser(folder)
        if os.path.isdir(os.path.join(folder, "interface")) and os.path.isdir(os.path.join(folder, "gfx")):
            return folder
    if arg:
        fail(f"{arg} doesn't look like the Hearts of Iron IV folder (no interface/ and gfx/ in it).")
    fail("couldn't find Hearts of Iron IV. Pass its folder, e.g.\n"
         '  python3 tools/install_building_icons.py "C:/Program Files (x86)/Steam/steamapps/common/Hearts of Iron IV"')


def find_strip_sprite(game):
    """(texture path relative to the game folder, number of frames) of the game's GFX_buildings_strip."""
    for path in sorted(glob.glob(os.path.join(game, "interface", "*.gfx"))):
        text = open(path, encoding="utf-8", errors="replace").read()
        text = re.sub(r"#[^\n]*", "", text)
        m = re.search(r'name\s*=\s*"?GFX_buildings_strip"?', text)
        if not m:
            continue
        start = text.rfind("{", 0, m.start())
        end = text.find("}", m.end())
        block = text[start:end]
        tex = re.search(r'texture[Ff]ile\s*=\s*"([^"]+)"', block)
        frames = re.search(r"noOfFrames\s*=\s*(\d+)", block)
        if tex and frames:
            return tex.group(1), int(frames.group(1)), path
    fail("couldn't find the sprite GFX_buildings_strip in the game's interface/*.gfx files.")


def save_dds(img, path):
    """An uncompressed A8R8G8B8 DDS, like the rest of the mod's textures."""
    img = img.convert("RGBA")
    w, h = img.size
    header = struct.pack("<4sIIIIIII11I", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x8 | 0x1000, h, w, w * 4, 0, 0,
                         *([0] * 11))
    pixel_format = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32,
                               0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    r, g, b, a = img.split()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(header + pixel_format + caps + Image.merge("RGBA", (b, g, r, a)).tobytes())


def set_icon_frames(frames):
    """Set each building's icon_frame (a dict name -> frame) in the mod's buildings file."""
    text = open(BUILDINGS_FILE, encoding="utf-8").read()
    for name, frame in frames.items():
        m = re.search(rf"^\t{re.escape(name)} = \{{", text, re.M)
        if not m:
            fail(f"{name} not found in {BUILDINGS_FILE}")
        f = re.compile(r"icon_frame = \d+").search(text, m.end())
        text = text[:f.start()] + f"icon_frame = {frame}" + text[f.end():]
    open(BUILDINGS_FILE, "w", encoding="utf-8").write(text)


def remove():
    for path in (OUT_GFX, os.path.join(MOD, OUT_TEXTURE)):
        if os.path.exists(path):
            os.remove(path)
            print("removed " + os.path.relpath(path, MOD))
    set_icon_frames(dict(BUILDINGS))
    print("The buildings use the game's own pictures again.")


def install(game_arg):
    game = find_game(game_arg)
    tex_rel, count, gfx_path = find_strip_sprite(game)
    tex_path = os.path.join(game, tex_rel)
    if not os.path.exists(tex_path):
        fail(f"{gfx_path} names {tex_rel}, which isn't there.")
    try:
        strip = Image.open(tex_path).convert("RGBA")
    except Exception as e:  # an image format this Pillow can't read
        fail(f"couldn't read {tex_path} ({e}). Updating Pillow may help: pip install --upgrade pillow")
    ours = Image.open(FRAMES).convert("RGBA")

    w, h = strip.size
    fw = round(w / count)
    if fw * count != w:
        # keep every frame boundary where the game expects it
        strip = strip.resize((fw * count, h), Image.LANCZOS)
    n = len(BUILDINGS)
    ours = ours.resize((fw * n, h), Image.LANCZOS) if ours.size != (fw * n, h) else ours

    out = Image.new("RGBA", (fw * (count + n), h), (0, 0, 0, 0))
    out.paste(strip, (0, 0))
    out.paste(ours, (fw * count, 0))
    save_dds(out, os.path.join(MOD, OUT_TEXTURE))

    with open(OUT_GFX, "w", encoding="utf-8") as f:
        f.write("# Written by tools/install_building_icons.py from the game's building strip\n"
                f"# ({tex_rel}, {count} frames) with the Road to Carcosa's four buildings\n"
                "# appended. Delete it (or run the script with --remove) to undo.\n"
                "spriteTypes = {\n"
                "\tspriteType = {\n"
                '\t\tname = "GFX_buildings_strip"\n'
                f'\t\ttexturefile = "{OUT_TEXTURE}"\n'
                f"\t\tnoOfFrames = {count + n}\n"
                "\t}\n"
                "}\n")

    # icon_frame counts from 1
    set_icon_frames({name: count + 1 + i for i, (name, _) in enumerate(BUILDINGS)})
    print(f"Read {tex_rel} ({count} frames) from the game.")
    print(f"Wrote {OUT_TEXTURE} ({count + n} frames) and interface/{os.path.basename(OUT_GFX)}.")
    print(f"The buildings now use frames {count + 1} to {count + n}. Restart the game to see them.")


def main():
    args = sys.argv[1:]
    if args == ["--remove"]:
        remove()
    elif len(args) <= 1 and not (args and args[0].startswith("-")):
        install(args[0] if args else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
