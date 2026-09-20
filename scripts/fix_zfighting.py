#!/usr/bin/env python3
"""Finds and fixes z-fighting in a Minecraft item/block model.

Z-fighting is two faces lying in the same plane, facing the same way, and overlapping: the graphics card cannot tell which
is in front, so the texture flickers or shows the wrong one. It is common with cross-shaped cuboids (a "plus" made of two
boxes shares its top and bottom faces) and with details laid flat on a surface.

    python fix_zfighting.py path/to/model.json            # report only
    python fix_zfighting.py path/to/model.json --fix      # rewrite the file

The fix pushes the face of the smaller element out by 0.01 model units (about a sixteenth of a pixel) for each element that
shares its plane, so the detail wins and nothing is visibly different. Elements with an element rotation are skipped, as
their faces are not on a shared axis-aligned plane. Standard library only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# face name -> (axis index, which end of the element the face is on)
FACES = {"north": (2, "from"), "south": (2, "to"), "west": (0, "from"), "east": (0, "to"), "down": (1, "from"), "up": (1, "to")}
EPSILON = 0.01


def face_rect(element: dict, axis: int) -> list[tuple[float, float]]:
    return [(element["from"][a], element["to"][a]) for a in (0, 1, 2) if a != axis]


def overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    area = 1.0
    for (a0, a1), (b0, b1) in zip(a, b):
        span = min(a1, b1) - max(a0, b0)
        if span <= 1e-6:
            return 0.0
        area *= span
    return area


def area_of(rect: list[tuple[float, float]]) -> float:
    return (rect[0][1] - rect[0][0]) * (rect[1][1] - rect[1][0])


def find_groups(elements: list[dict]) -> list[tuple[str, float, list[int]]]:
    """Groups of elements whose same-facing faces share a plane and overlap: (face, plane, [element indices])."""
    by_plane: dict[tuple[str, float], list[tuple[int, list]]] = {}
    for i, element in enumerate(elements):
        rotation = element.get("rotation")
        if rotation and rotation.get("angle"):
            continue
        for name in element.get("faces", {}):
            axis, end = FACES[name]
            plane = round(element[end][axis], 4)
            by_plane.setdefault((name, plane), []).append((i, face_rect(element, axis)))
    groups = []
    for (name, plane), faces in by_plane.items():
        parent = list(range(len(faces)))

        def root(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        for a in range(len(faces)):
            for b in range(a + 1, len(faces)):
                if overlap(faces[a][1], faces[b][1]) > 0:
                    parent[root(a)] = root(b)
        components: dict[int, list[int]] = {}
        for k in range(len(faces)):
            components.setdefault(root(k), []).append(k)
        for members in components.values():
            if len(members) > 1:
                groups.append((name, plane, [faces[k][0] for k in members]))
    return groups


def fix_once(elements: list[dict]) -> int:
    """One pass of nudging. Returns how many faces were moved."""
    moved = 0
    for name, plane, indices in find_groups(elements):
        axis, end = FACES[name]
        outward = 1 if end == "to" else -1
        # Largest face stays put; each smaller one sits a step further out, so the finest detail is on top.
        ordered = sorted(indices, key=lambda i: (-area_of(face_rect(elements[i], axis)), i))
        for rank, i in enumerate(ordered):
            if rank:
                elements[i][end][axis] = round(elements[i][end][axis] + outward * EPSILON * rank, 4)
                moved += 1
    return moved


def fix(elements: list[dict]) -> int:
    """Repeats until nothing overlaps (a nudged face can land on a third element's plane). Returns faces moved."""
    total = 0
    for _ in range(8):
        moved = fix_once(elements)
        if not moved:
            break
        total += moved
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", type=Path)
    parser.add_argument("--fix", action="store_true", help="rewrite the model with the faces nudged apart")
    args = parser.parse_args()
    raw = args.model.read_text(encoding="utf-8", newline="")
    model = json.loads(raw)
    elements = model.get("elements", [])
    groups = find_groups(elements)
    involved = {i for _, _, indices in groups for i in indices}
    print(f"{args.model.name}: {len(groups)} overlapping coplanar face group(s), {len(involved)} of {len(elements)} elements involved")
    for name, plane, indices in groups[:20]:
        names = ", ".join(str(elements[i].get("name", i)) for i in indices)
        print(f"  {name:5} face at {plane}: {names}")
    if not args.fix:
        return
    moved = fix(elements)
    remaining = len(find_groups(elements))
    trailing = raw[len(raw.rstrip("\r\n")):]
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = json.dumps(model, indent=2, ensure_ascii=False)
    args.model.write_text(text.replace("\n", newline) + trailing, encoding="utf-8", newline="")
    print(f"Moved {moved} face(s) by {EPSILON} unit steps; {remaining} group(s) remain.")


if __name__ == "__main__":
    main()
