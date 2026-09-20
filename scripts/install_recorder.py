#!/usr/bin/env python3
"""Installs (or removes) the model viewer's in-game pose recorder in a Fabric mod project.

    python install_recorder.py            # install into the project in the current folder
    python install_recorder.py --remove   # take it out again

The recorder is three small client classes (a HumanoidModel mixin, a hand-item-layer mixin and PoseRecorder). While a held item
is drawn in a development game it records how the game poses the body and the item, and writes a pose profile to
<game dir>/model-viewer/poses/<item>.pose.json, which build_viewer.py picks up. It only records in a development environment
(or with -Dmodelviewer.record=true) and never changes what is drawn. Nothing is committed or built for you.
Standard library only. Run it from the project root.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "recorder"
FILES = {"PoseRecorder.java": False, "PoseRecorderHumanoidMixin.java": True, "PoseRecorderItemMixin.java": True}   # name: is a mixin
MIXIN_CLASSES = ["PoseRecorderHumanoidMixin", "PoseRecorderItemMixin"]
CRLF, LF = b"\r\n".decode(), b"\n".decode()


def find_client_mixins(root: Path) -> Path:
    found = sorted(p for p in (root / "src").rglob("*.mixins.json") if "client" in p.name.lower())
    if not found:
        sys.exit("No client mixin config (*client*.mixins.json) found under src/. The recorder needs one: add a client mixin config first.")
    return found[0]


def java_root(root: Path) -> Path:
    for candidate in ("src/client/java", "src/main/java"):
        if (root / candidate).is_dir():
            return root / candidate
    sys.exit("No src/client/java or src/main/java folder found.")


def edit_config(config: Path, install: bool) -> str:
    text = config.read_bytes().decode("utf-8")   # bytes, not read_text: keep the file's own line endings
    package = re.search(r'"package"\s*:\s*"([^"]+)"', text)
    if not package:
        sys.exit(f"{config} has no \"package\".")
    match = re.search(r'("client"\s*:\s*\[)(.*?)(\])', text, re.S)
    if not match:
        sys.exit(f"{config} has no \"client\" mixin list.")
    body = match.group(2)
    eol = CRLF if CRLF in text else LF
    if install:
        missing = [c for c in MIXIN_CLASSES if f'"{c}"' not in body]
        if missing:
            multiline = LF in body
            pad = (re.search(r'\n([ \t]*)"', body) or re.search(r'()', body)).group(1) if multiline else ""
            sep = (eol + pad) if multiline else " "
            new_body = body.rstrip() + ("," if body.strip() else "") + ",".join(sep + f'"{c}"' for c in missing)
            new_body += (eol + pad[:-2]) if multiline and len(pad) >= 2 else ""
            text = text[:match.start(2)] + new_body + text[match.end(2):]
    else:
        for c in MIXIN_CLASSES:
            body = re.sub(r'\s*,?\s*"%s"' % c, "", body)
        text = text[:match.start(2)] + body + text[match.end(2):]
    config.write_bytes(text.encode("utf-8"))
    return package.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="remove the recorder instead")
    args = parser.parse_args()
    root = Path.cwd()
    config = find_client_mixins(root)
    package = edit_config(config, not args.remove)
    parent = package.rsplit(".", 1)[0] if "." in package else package
    base = java_root(root)
    eol = CRLF if CRLF in config.read_bytes().decode("utf-8") else LF
    for name, is_mixin in FILES.items():
        target = base / (package if is_mixin else parent).replace(".", "/") / name
        if args.remove:
            if target.is_file():
                target.unlink()
                print(f"removed {target.relative_to(root)}")
            continue
        source = (TEMPLATES / name).read_text(encoding="utf-8").replace("@MIXIN_PACKAGE@", package).replace("@PACKAGE@", parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.replace(CRLF, LF).replace(LF, eol).encode("utf-8"))
        print(f"wrote {target.relative_to(root)}")
    print(f"{'Removed from' if args.remove else 'Registered in'} {config.relative_to(root)}")
    if not args.remove:
        print("Run the game in a development environment (gradlew runClient), hold the item, switch to third person (F5) and swing it.\n"
              "The pose is written to <run folder>/model-viewer/poses/. Build the viewer again to load it.")


if __name__ == "__main__":
    main()
