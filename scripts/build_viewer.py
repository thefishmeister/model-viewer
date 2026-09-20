#!/usr/bin/env python3
"""Builds a self-contained 3D viewer page for a Minecraft item/block model, so it can be inspected before it is pushed.

    python build_viewer.py giant_hammer                 # by name: orvcraft:item/giant_hammer
    python build_viewer.py orvcraft:item/void_bow
    python build_viewer.py path/to/model.json -o out.html
    python build_viewer.py royal_crown --open           # also opens it in your browser
    python build_viewer.py art/royal_knight/royal_knight.bbmodel   # a Blockbench project: entity models, animations
    python build_viewer.py giant_hammer --skin-name SomePlayer   # dress the character in a player's skin
    python build_viewer.py giant_hammer --artifact      # a fragment for the Artifact tool (see below)

The page loads three.js from the jsDelivr CDN, so it needs a network connection to display. The model, its parents and
its textures are embedded, so the file can be moved, mailed, or published as an Artifact on its own.

Handles Blockbench projects (.bbmodel): bone tree, box or per-face UVs, embedded textures, keyframe animations, and an
optional glow texture and aura for a glowing entity. Also handles: cuboid elements (from/to, per-face uv and rotation, element rotation about any origin, shade), parent chains
inside the mod's own assets, `#texture` references, the `generated`/`handheld` item parents (a flat one-pixel-thick
sprite), and `display` transforms. Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import sys
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path.cwd()                        # the project being viewed: run this from its root
TEMPLATE = HERE / "viewer_template.html"
DEFAULT_ROOTS = [REPO / "src/main/resources/assets", REPO / "src/client/resources/assets"]
SKINS = HERE / "skins"                   # <name>.png (64x64 or 64x32) with an optional <name>.json {"model": "slim"|"classic"}
DEFAULT_NAMESPACE = "orvcraft"
GENERATED_PARENTS = {"minecraft:item/generated", "item/generated", "minecraft:builtin/generated", "builtin/generated",
                     "minecraft:item/handheld", "item/handheld", "minecraft:item/handheld_rod", "item/handheld_rod"}


def split_id(value: str, default_ns: str = DEFAULT_NAMESPACE) -> tuple[str, str]:
    if ":" in value:
        ns, path = value.split(":", 1)
        return ns, path
    return default_ns, value


def find_file(roots: list[Path], ns: str, kind: str, path: str, suffix: str) -> Path | None:
    for root in roots:
        candidate = root / ns / kind / (path + suffix)
        if candidate.is_file():
            return candidate
    return None


def locate_model(arg: str, roots: list[Path]) -> tuple[Path, str]:
    """Accepts a file path, `ns:models-path`, or a bare name (looked for under models/item then models/block)."""
    as_path = Path(arg)
    if as_path.suffix in (".json", ".bbmodel") and as_path.is_file():
        return as_path, DEFAULT_NAMESPACE
    ns, path = split_id(arg)
    for prefix in ([""] if "/" in path else ["item/", "block/"]):
        found = find_file(roots, ns, "models", prefix + path, ".json")
        if found:
            return found, ns
    sys.exit(f"Could not find a model for '{arg}'. Looked in: " + ", ".join(str(r) for r in roots))


def load_model(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(model_path: Path, ns: str, roots: list[Path], warnings: list[str]) -> dict:
    """Merges a model with its parents: children override textures and elements, and inherit display transforms."""
    model = load_model(model_path)
    chain = [model]
    seen = {str(model_path)}
    generated = False
    parent = model.get("parent")
    while parent:
        pns, ppath = split_id(parent, ns)
        if parent in GENERATED_PARENTS or f"{pns}:{ppath}" in GENERATED_PARENTS:
            generated = True
            break
        found = find_file(roots, pns, "models", ppath, ".json")
        if not found:
            warnings.append(f"Parent model '{parent}' is not in the mod's assets, so its elements and display "
                            f"transforms are missing here (vanilla parents are not bundled).")
            break
        if str(found) in seen:
            warnings.append(f"Parent loop at '{parent}'.")
            break
        seen.add(str(found))
        parent_model = load_model(found)
        chain.append(parent_model)
        parent = parent_model.get("parent")
    merged: dict = {"textures": {}, "display": {}, "elements": None}
    for m in reversed(chain):                      # root-most parent first, so the child wins
        merged["textures"].update(m.get("textures", {}))
        for name, transform in (m.get("display") or {}).items():
            merged["display"][name] = transform
        if m.get("elements") is not None:
            merged["elements"] = m["elements"]
    if merged["elements"] is None:
        if generated or any(k.startswith("layer") for k in merged["textures"]):
            merged["elements"] = generated_elements(merged["textures"])
        else:
            merged["elements"] = []
            warnings.append("This model has no elements of its own.")
    return merged


def generated_elements(textures: dict) -> list:
    """`item/generated`: each layerN is a flat sprite, one pixel thick, facing north and south."""
    elements = []
    layer = 0
    while f"layer{layer}" in textures:
        # As in the game, the back face is flipped so the sprite reads the same way round from both sides.
        front = {"uv": [0, 0, 16, 16], "texture": f"#layer{layer}"}
        back = {"uv": [16, 0, 0, 16], "texture": f"#layer{layer}"}
        elements.append({"from": [0, 0, 7.5], "to": [16, 16, 8.5], "faces": {"north": back, "south": front}})
        layer += 1
    return elements


def embed_textures(textures: dict, roots: list[Path], ns: str, warnings: list[str]) -> dict:
    images: dict[str, str] = {}
    for name, ref in textures.items():
        if not isinstance(ref, str) or ref.startswith("#") or ref in images:
            continue
        tns, tpath = split_id(ref, ns)
        found = find_file(roots, tns, "textures", tpath, ".png")
        if not found:
            warnings.append(f"Texture '{ref}' was not found under any assets/{tns}/textures.")
            continue
        images[ref] = "data:image/png;base64," + base64.b64encode(found.read_bytes()).decode("ascii")
    return images


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def load_bbmodel(path: Path, warnings: list[str], glow: Path | None = None) -> dict:
    """A Blockbench project (.bbmodel): bone tree, cubes with box or per-face UVs, embedded textures and animations.

    Works for entity models ("modded entity", "free", "bedrock") and for Java block/item projects alike. The result is the
    viewer's own compact form: a tree of nodes {id, name, origin, rotation, children, cubes}, the textures as data URIs,
    and the animations. Blockbench's y is up, its unit is the pixel (16 to a block) and its front is north (-z).
    """
    project = json.loads(path.read_text(encoding="utf-8"))
    res = project.get("resolution") or {}
    resolution = [res.get("width", 16), res.get("height", 16)]
    textures = []
    for index, tex in enumerate(project.get("textures", [])):
        source = tex.get("source", "")
        uri = source if source.startswith("data:") else None
        if uri is None:
            beside = path.parent / (tex.get("name") or f"texture{index}.png")
            if beside.is_file():
                uri = data_uri(beside)
            else:
                warnings.append(f"Texture {index} ('{tex.get('name')}') is not embedded and was not found next to the project.")
        textures.append({"uri": uri, "uv": [tex.get("uv_width") or resolution[0], tex.get("uv_height") or resolution[1]]})
    skipped = 0
    cubes: dict[str, dict] = {}
    for element in project.get("elements", []):
        if element.get("type", "cube") != "cube":
            skipped += 1
            continue
        faces = {}
        for name, face in (element.get("faces") or {}).items():
            if face.get("texture") is None:
                continue
            faces[name] = {"uv": face.get("uv"), "texture": face["texture"]}
        cubes[element["uuid"]] = {
            "from": element["from"], "to": element["to"], "origin": element.get("origin", [0, 0, 0]),
            "rotation": element.get("rotation", [0, 0, 0]), "inflate": element.get("inflate", 0),
            "shade": element.get("shade", True), "boxUv": bool(element.get("box_uv")), "uvOffset": element.get("uv_offset"),
            "mirrorUv": bool(element.get("mirror_uv")), "faces": faces, "hidden": element.get("visibility") is False}
    if skipped:
        warnings.append(f"{skipped} non-cube element(s) (meshes, locators) were skipped: only cubes are shown.")
    groups = {g["uuid"]: g for g in project.get("groups", []) if isinstance(g, dict)}
    count = [0]

    def build_node(item) -> dict | None:
        if isinstance(item, str):
            return None
        props = {**groups.get(item.get("uuid"), {}), **{k: v for k, v in item.items() if k != "children"}}
        if props.get("visibility") is False:
            return None
        node = {"id": props.get("uuid", props.get("name", "node")), "name": props.get("name", "group"),
                "origin": props.get("origin", [0, 0, 0]), "rotation": props.get("rotation", [0, 0, 0]),
                "children": [], "cubes": []}
        for child in item.get("children", []):
            if isinstance(child, str):
                cube = cubes.get(child)
                if cube and not cube["hidden"]:
                    node["cubes"].append(cube)
                    count[0] += 1
            else:
                sub = build_node(child)
                if sub:
                    node["children"].append(sub)
        return node

    root = {"id": "root", "name": "root", "origin": [0, 0, 0], "rotation": [0, 0, 0], "children": [], "cubes": []}
    for item in project.get("outliner", []):
        if isinstance(item, str):
            cube = cubes.get(item)
            if cube and not cube["hidden"]:
                root["cubes"].append(cube)
                count[0] += 1
        else:
            node = build_node(item)
            if node:
                root["children"].append(node)
    animations = []
    for animation in project.get("animations") or []:
        animators = {}
        for uuid, animator in (animation.get("animators") or {}).items():
            keyframes = [{"channel": k["channel"], "time": k["time"], "interpolation": k.get("interpolation", "linear"),
                          "value": k["data_points"][0] if k.get("data_points") else {}}
                         for k in animator.get("keyframes", []) if k.get("channel") in ("rotation", "position", "scale")]
            if keyframes:
                animators[uuid] = keyframes
        animations.append({"name": animation.get("name", "animation"), "loop": animation.get("loop", "once"),
                           "length": animation.get("length", 1), "animators": animators})
    extra = project.get("orvcraft") or {}
    glow_uri = data_uri(glow) if glow else extra.get("glow_texture")
    return {"resolution": resolution, "textures": textures, "root": root, "animations": animations, "cubeCount": count[0],
            "item": (project.get("meta") or {}).get("model_format") == "java_block", "glow": glow_uri,
            "aura": extra.get("aura"), "name": project.get("name") or path.stem,
            "display": project.get("display") or {}}


def http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "orvcraft-model-viewer"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def fetch_skin(name: str) -> Path:
    """Downloads a Java Edition player's skin from Mojang's public profile servers into the plugin's skins folder."""
    profile_id = json.loads(http_get(f"https://api.minecraftservices.com/minecraft/profile/lookup/name/{name}"))["id"]
    profile = json.loads(http_get(f"https://sessionserver.mojang.com/session/minecraft/profile/{profile_id}"))
    encoded = next(p["value"] for p in profile["properties"] if p["name"] == "textures")
    skin = json.loads(base64.b64decode(encoded))["textures"]["SKIN"]
    SKINS.mkdir(exist_ok=True)
    target = SKINS / f"{name}.png"
    target.write_bytes(http_get(skin["url"]))
    meta = {"name": name, "model": skin.get("metadata", {}).get("model", "classic"), "source": skin["url"]}
    target.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Downloaded {name}'s skin ({target.stat().st_size} bytes) from {skin['url']}")
    return target


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit("The skin is not a PNG file.")
    return struct.unpack(">II", data[16:24])


def load_skin(skin: str | None, skin_name: str | None) -> dict | None:
    """The skin the viewer's character wears: --skin FILE, --skin-name NAME, else skins/DEFAULT, else a plain built-in one."""
    path: Path | None = None
    if skin_name:
        path = fetch_skin(skin_name)
    elif skin:
        path = Path(skin)
    elif (SKINS / "DEFAULT").is_file():
        path = SKINS / (SKINS / "DEFAULT").read_text(encoding="utf-8").strip()
    if path is None or not path.is_file():
        return None
    data = path.read_bytes()
    width, height = png_size(data)
    if width != 64 or height not in (32, 64):
        sys.exit(f"{path.name} is {width}x{height}; a skin must be 64x64 (or the old 64x32).")
    meta_file = path.with_suffix(".json")
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    return {"uri": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
            "slim": meta.get("model") == "slim", "legacy": height == 32, "name": meta.get("name", path.stem)}


def load_wings(name: str) -> dict:
    """A worn wing set for the viewer: its geometry and animation constants (from its texture generator, which the game's
    model mirrors) and the texture sheet."""
    import importlib.util
    folder = {"vampire": ("tools/vampire_wings/generate_wings.py", REPO / "tools" / "vampire_wings")}.get(name)
    if folder is None:
        sys.exit(f"Unknown wings '{name}'. Available: vampire")
    spec = importlib.util.spec_from_file_location("wing_generator", REPO / folder[0])
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return {"image": "data:image/png;base64," + base64.b64encode(gen.OUT.read_bytes()).decode("ascii"),
            "sheet": [128, 64], "panel": [gen.PANEL_W, gen.PANEL_H, gen.PANEL_Y0],
            "arm": [list(gen.ROOT), list(gen.ELBOW), list(gen.WRIST)], "claw": [list(p) for p in gen.CLAW], "clawThick": gen.CLAW_THICK, "clawDepth": gen.CLAW_DEPTH, "clawTipFrom": gen.CLAW_TIP_FROM,
            "tipColor": "#%02x%02x%02x" % gen.CLAW_TIP[:3],
            "fingers": [[list(p) for p in f] for f in gen.FINGERS],
            "boneColor": "#%02x%02x%02x" % gen.BONE[:3], "armColor": "#%02x%02x%02x" % gen.ARM[:3],
            "offset": [1, 1.5, 3.0], "scale": 0.9,
            # Mirrors the constants in VampireWingsModel.java; blend is WingFlight's ease per tick.
            "anim": {"beatSpeed": 0.18, "beatLift": 0.55, "beatSweep": 0.15, "groundSpeed": 0.2, "groundSwing": 0.35,
                     "restSweep": 0.5, "flightSweep": 0.3, "restSpread": 0.4, "flightSpread": 0.05, "fold": 0.3, "blend": 0.12}}


POSE_PARTS = {"head", "body", "rightArm", "leftArm", "rightLeg", "leftLeg"}


def load_pose(model_path: Path, pose_arg: str | None, warnings: list[str]) -> dict | None:
    """The item's in-game pose profile (see POSES.md): --pose FILE, else <model>.pose.json beside the model, else
    .model-viewer/poses/<model>.pose.json in the project."""
    candidates = [Path(pose_arg)] if pose_arg else [model_path.with_suffix(".pose.json"),
                                                    REPO / ".model-viewer" / "poses" / f"{model_path.stem}.pose.json"]
    path = next((c for c in candidates if c.is_file()), None)
    if path is None:
        if pose_arg:
            sys.exit(f"Pose profile not found: {pose_arg}")
        return None
    profile = json.loads(path.read_text(encoding="utf-8"))
    named = {k.split(".")[0] for a in profile.get("animations", {}).values() for k in a.get("tracks", {})} | set(profile.get("carry", {}))
    unknown = sorted(named - POSE_PARTS - {"item", "mode"})
    if unknown:
        warnings.append(f"Pose profile {path.name} names unknown parts: {', '.join(unknown)} (known: {', '.join(sorted(POSE_PARTS))}, item).")
    print(f"Using pose profile {path}")
    return profile


def as_artifact(html: str, title: str) -> str:
    """The Artifact tool wraps a page in its own <html>, <head> and <body>, so hand it only the title, style and body."""
    head_title = f"<title>{title} Viewer</title>"
    style = re.search(r"<style>.*?</style>", html, re.S).group(0)
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    return head_title + "\n" + style + "\n" + body.strip() + "\n"


def build(model_arg: str, out: Path | None, extra_roots: list[str], skin: str | None = None,
          skin_name: str | None = None, artifact: bool = False, wings: str | None = None, pose: str | None = None) -> Path:
    roots = [Path(r) for r in extra_roots] + DEFAULT_ROOTS
    warnings: list[str] = []
    bb = None
    wing_data = None
    if wings:
        wing_data = load_wings(wings)
        model_path, ns = Path(f"{wings}_wings.json"), "orvcraft"
        merged = {"elements": [], "textures": {}, "display": {}}
        images = {}
    else:
        model_path, ns = locate_model(model_arg, roots)
    if wings:
        pass
    elif model_path.suffix == ".bbmodel":
        bb = load_bbmodel(model_path, warnings)
        merged = {"elements": [], "textures": {}, "display": bb["display"]}
        images: dict = {}
    else:
        merged = resolve(model_path, ns, roots, warnings)
        images = embed_textures(merged["textures"], roots, ns, warnings)
    title = model_path.stem.replace("_", " ").title()
    data = {"title": title, "elements": merged["elements"], "textures": merged["textures"], "images": images,
            "display": merged["display"], "warnings": warnings, "skin": load_skin(skin, skin_name), "bb": bb, "wings": wing_data,
            "pose": None if wings else load_pose(model_path, pose, warnings)}
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("/*__DATA__*/null", payload, 1)
    if artifact:
        html = as_artifact(html, title)
    if out is None:
        out = Path.cwd() / f"{model_path.stem}_viewer.html"
    out.write_text(html, encoding="utf-8")
    count = bb["cubeCount"] if bb else len(merged["elements"])
    print(f"{title}: {count} {'cubes' if bb else 'elements'}, {len(bb['textures']) if bb else len(images)} texture(s) -> {out}")
    for w in warnings:
        print("  warning:", w)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", nargs="?", default="", help="model name (giant_hammer), id (orvcraft:item/void_bow) or path to a model .json")
    parser.add_argument("-o", "--out", type=Path, help="output HTML file (default: <name>_viewer.html in the current folder)")
    parser.add_argument("--resources", action="append", default=[], metavar="DIR",
                        help="extra assets folder to search (holding <namespace>/models and <namespace>/textures); repeatable")
    parser.add_argument("--skin", metavar="FILE", help="a 64x64 skin PNG for the viewer's character (default: skins/DEFAULT)")
    parser.add_argument("--skin-name", metavar="PLAYER", help="download this Java Edition player's skin and use it")
    parser.add_argument("--artifact", action="store_true",
                        help="write a fragment (title, style, body) for the Artifact tool, which supplies the page around it")
    parser.add_argument("--wings", metavar="SET", help="show a worn wing set on the character instead of an item model (vampire); the model argument is ignored")
    parser.add_argument("--pose", metavar="FILE", help="the item's in-game pose profile (default: <model>.pose.json beside the model, or .model-viewer/poses/)")
    parser.add_argument("--open", action="store_true", help="open the result in the default browser")
    args = parser.parse_args()
    out = build(args.model, args.out, args.resources, args.skin, args.skin_name, args.artifact, args.wings, args.pose)
    if args.open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
