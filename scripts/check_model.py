#!/usr/bin/env python3
"""Checks an item/block model for things that are usually mistakes, and lists each one as a question for the author:
"is this intended?". It changes nothing.

    python check_model.py giant_hammer                 # same model names as build_viewer.py
    python check_model.py path/to/model.json --json    # machine-readable, for the view-model skill

Checks: overlapping coplanar faces (z-fighting), missing parent models or textures, faces that use a texture the model
never defines, elements outside the -16..32 range the game renders, face UVs outside 0..16, element rotations the game
does not support, zero-thickness elements, and missing display transforms for the hand, head and inventory views.
Standard library only. Run it from the project root, like build_viewer.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import build_viewer as bv
import fix_zfighting as zf

DISPLAY_VIEWS = ["thirdperson_righthand", "gui", "head", "ground", "fixed"]


def check(model_arg: str, extra_roots: list[str]) -> tuple[str, list[dict]]:
    roots = [Path(r) for r in extra_roots] + bv.DEFAULT_ROOTS
    path, ns = bv.locate_model(model_arg, roots)
    if path.suffix != ".json":
        sys.exit("check_model.py reads block/item model .json files, not Blockbench projects.")
    warnings: list[str] = []
    merged = bv.resolve(path, ns, roots, warnings)
    bv.embed_textures(merged["textures"], roots, ns, warnings)
    elements, textures = merged["elements"], merged["textures"]
    issues: list[dict] = []

    def add(kind: str, detail: str, question: str) -> None:
        issues.append({"kind": kind, "detail": detail, "question": question})

    for w in warnings:      # missing parents, missing textures, no elements: the build's own warnings
        add("build-warning", w, "Is this intended?")

    for face_dir, coord, members in zf.find_groups(elements):
        names = ", ".join(f"#{i}" for i in members)
        add("z-fighting", f"Elements {names} have faces in the same plane ({face_dir} faces at {coord:g}), facing the same way, "
            "so they flicker or show the wrong texture.",
            "Is the overlap intended? (fix_zfighting.py --fix nudges the smaller face out by 0.01.)")

    for i, e in enumerate(elements):
        lo, hi = e.get("from", [0, 0, 0]), e.get("to", [0, 0, 0])
        if any(v < -16 or v > 32 for v in (*lo, *hi)):
            add("out-of-range", f"Element #{i} reaches outside -16..32 ({lo} to {hi}); the game clips or drops it.",
                "Is it meant to reach that far out?")
        flat = [a for a in "xyz" if lo["xyz".index(a)] == hi["xyz".index(a)]]
        if len(flat) > 1:
            add("degenerate", f"Element #{i} has no thickness on {len(flat)} axes ({', '.join(flat)}).", "Is that element needed?")
        rot = e.get("rotation")
        if rot and rot.get("angle") not in (0, None, -45, -22.5, 22.5, 45):
            add("bad-rotation", f"Element #{i} is rotated {rot.get('angle')} degrees; the game only allows -45, -22.5, 0, 22.5 and 45.",
                "Is that angle intended? (It is ignored or snapped by the game.)")
        for face_name, face in (e.get("faces") or {}).items():
            uv = face.get("uv")
            if uv and any(v < 0 or v > 16 for v in uv):
                add("uv-range", f"Element #{i}, face {face_name}: uv {uv} is outside 0..16.", "Is the texture meant to wrap or stretch there?")
            ref = face.get("texture", "")
            seen = set()
            while ref.startswith("#") and ref[1:] in textures and ref not in seen:
                seen.add(ref)
                ref = textures[ref[1:]]
            if ref.startswith("#"):
                add("undefined-texture", f"Element #{i}, face {face_name} uses '{face.get('texture')}', which the model never defines.",
                    "Is that texture supplied somewhere else (a child model)?")

    if elements and not any(k.startswith("layer") for k in textures):
        for view in DISPLAY_VIEWS:
            if view not in merged["display"]:
                add("no-display", f"No '{view}' display transform: the game uses its default position, rotation and scale.",
                    f"Is the default '{view}' placement intended?")
    # A group of identical findings would flood the author: keep the first five of a kind, count the rest.
    trimmed, per_kind = [], {}
    for issue in issues:
        per_kind[issue["kind"]] = per_kind.get(issue["kind"], 0) + 1
        if per_kind[issue["kind"]] <= 5:
            trimmed.append(issue)
    for kind, n in per_kind.items():
        if n > 5:
            trimmed.append({"kind": kind, "detail": f"...and {n - 5} more '{kind}' finding(s) like the ones above.", "question": "Same answer for all of them?"})
    return path.stem, trimmed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", help="model name, id or path to a model .json")
    parser.add_argument("--resources", action="append", default=[], metavar="DIR", help="extra assets folder to search")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args()
    name, issues = check(args.model, args.resources)
    if args.json:
        print(json.dumps({"model": name, "issues": issues}, indent=2))
        return
    if not issues:
        print(f"{name}: nothing to ask about.")
        return
    print(f"{name}: {len(issues)} thing(s) to confirm")
    for n, issue in enumerate(issues, 1):
        print(f"{n}. [{issue['kind']}] {issue['detail']}\n   {issue['question']}")


if __name__ == "__main__":
    main()
