#!/usr/bin/env python3
"""Scans a mod project for how an item is held and animated in game, and reports where to read it. It changes nothing.

    python scan_poses.py scythe                 # a bare item name, an id (mymod:scythe) or a model .json path
    python scan_poses.py scythe --json          # machine-readable, for the view-model skill

Pose code cannot be run here, so this finds it: the model's `display` transforms, the item definition (assets/*/items),
the Java files that mention the item next to arm-pose or item-transform code, and any mixin into the humanoid model or the
hand-item layer (those run for every held item, and usually test for the item themselves). For each file it lists the lines
that set arm rotations, turn or move the item, or define constants. Reading those files and writing a pose profile from
them (POSES.md) is the next step. Standard library only. Run it from the project root.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import build_viewer as bv

SOURCE_DIRS = ["src"]
POSE_LINE = re.compile(
    r"\b(xRot|yRot|zRot|setRotation|ArmPose|HumanoidArm|translate\(|mulPose|Axis\.[XYZ]|rotateX|rotateY|rotateZ|setupAnim|"
    r"setupAttackAnimation|submitArmWithItem|renderArmWithItem|attackTime|swingTime|static final float)")
# A file only counts as pose code if it works with the humanoid model, arm poses or the held-item transform stack.
STRONG = re.compile(r"HumanoidModel|PlayerModel|ItemInHandLayer|ArmPose|setupAnim|submitArmWithItem|renderArmWithItem|"
                    r"ArmedEntityRenderState|attackTime|IClientItemExtensions|applyForgeHandTransform|ItemInHandRenderer")
POSE_MIXIN = re.compile(r"@Mixin\(\s*\{?\s*(HumanoidModel|PlayerModel|ItemInHandLayer|ArmedEntityRenderState|"
                        r"HumanoidMobRenderer|PlayerRenderer|ItemInHandRenderer|ArmorStand\w*)")
MAX_LINES_PER_FILE = 40


def names_for(item: str) -> list[str]:
    """The spellings an item is known by in code: scythe, Scythe, SCYTHE, plus its id."""
    base = item.split(":")[-1].split("/")[-1]
    parts = re.split(r"[_\-\s]+", base)
    return sorted({base, base.upper(), "".join(p.capitalize() for p in parts), "_".join(p.upper() for p in parts)})


def scan(item_arg: str, extra_roots: list[str]) -> dict:
    roots = [Path(r) for r in extra_roots] + bv.DEFAULT_ROOTS
    model_path = None
    try:
        model_path, ns = bv.locate_model(item_arg, roots)
    except SystemExit:
        ns = bv.split_id(item_arg)[0]
    stem = model_path.stem if model_path else bv.split_id(item_arg)[1].split("/")[-1]
    spellings = names_for(stem)
    result: dict = {"item": stem, "model": str(model_path) if model_path else None, "display": {}, "item_definition": None,
                    "profile": None, "java": [], "hints": []}
    if model_path and model_path.suffix == ".json":
        merged = bv.resolve(model_path, ns, roots, [])
        result["display"] = {k: v for k, v in merged["display"].items() if k.startswith(("thirdperson", "firstperson", "head"))}
    for root in roots:
        definition = root / ns / "items" / f"{stem}.json"
        if definition.is_file():
            result["item_definition"] = {"path": str(definition), "text": definition.read_text(encoding="utf-8")[:2000]}
    for candidate in [model_path.with_suffix(".pose.json")] if model_path else []:
        if candidate.is_file():
            result["profile"] = str(candidate)
    project_profile = bv.REPO / ".model-viewer" / "poses" / f"{stem}.pose.json"
    if project_profile.is_file():
        result["profile"] = str(project_profile)

    pattern = re.compile("|".join(re.escape(s) for s in spellings))
    for folder in SOURCE_DIRS:
        for path in sorted((bv.REPO / folder).rglob("*.java")):
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            mentions = [i for i, line in enumerate(lines, 1) if pattern.search(line)]
            mixin = POSE_MIXIN.search(text)
            posey = [i for i, line in enumerate(lines, 1) if POSE_LINE.search(line) and not line.lstrip().startswith("import ")]
            if not posey or not STRONG.search(text) or not (mentions or mixin):
                continue
            # A file about the item with pose code, or a mixin that poses every held item (and so tests for it itself).
            kind = "mentions the item and sets poses" if mentions else f"mixin into {mixin.group(1)}"
            if mixin and mentions:
                kind = f"mixin into {mixin.group(1)}, mentions the item"
            shown = [{"line": i, "code": lines[i - 1].strip()[:160]} for i in posey[:MAX_LINES_PER_FILE]]
            result["java"].append({"file": str(path.relative_to(bv.REPO)).replace("\\", "/"), "kind": kind,
                                   "item_mentions": mentions[:5], "pose_lines": shown, "pose_line_count": len(posey)})
    # Files that mention the item and pose code first, then mixins.
    result["java"].sort(key=lambda f: (not f["item_mentions"], f["file"]))
    if not any(f["item_mentions"] for f in result["java"]):
        result["hints"].append("No Java pose code mentions this item by name" + (" (only mixins that pose every held item, which may test for it some other way)." if result["java"] else ".") + " ")
    if not result["java"]:
        result["hints"].append("No pose code was found at all. If it is held differently in game, the pose is not in this "
                               "project's source yet (unpushed, another repo or branch, or a resource pack). Ask where it is defined.")
    if not result["display"]:
        result["hints"].append("The model has no thirdperson/firstperson/head display transform, so the game uses its defaults.")
    if result["item_definition"]:
        result["hints"].append("An item definition exists: check it for per-context model swaps (display_context, using_item).")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("item", help="item name, id or path to its model .json")
    parser.add_argument("--resources", action="append", default=[], metavar="DIR", help="extra assets folder to search")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args()
    found = scan(args.item, args.resources)
    if args.json:
        print(json.dumps(found, indent=2))
        return
    print(f"{found['item']}: model {found['model'] or 'NOT FOUND'}")
    print(f"  pose profile: {found['profile'] or 'none yet'}")
    for name, d in found["display"].items():
        print(f"  display.{name}: {json.dumps(d)}")
    if found["item_definition"]:
        print(f"  item definition: {found['item_definition']['path']}")
    for f in found["java"]:
        print(f"\n{f['file']}  ({f['kind']}; {f['pose_line_count']} pose line(s), item mentioned on {f['item_mentions'] or 'no'} line(s))")
        for row in f["pose_lines"][:12]:
            print(f"  {row['line']:>4}: {row['code']}")
    for hint in found["hints"]:
        print(f"\nNote: {hint}")


if __name__ == "__main__":
    main()
