---
name: view-model
description: Preview a Minecraft item or block model in 3D, held by a character or in an inventory slot, and check it for z-fighting. Use when someone asks to see, view, preview, inspect, rotate or review a model, sword, weapon, hat or any item model, or before pushing a new model.
---

# View a model in 3D

Build a self-contained 3D viewer for the model, then publish it as an Artifact so it can be rotated in this conversation
and shared with the team. The scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts`. Run them from the **project root**: models
and textures are found under `src/main/resources/assets` and `src/client/resources/assets` of the current directory.

## 1. Build the page

Work out which model. It may be a name (`giant_hammer`), an id (`orvcraft:item/void_bow`), a path to a `.json` file or to
a Blockbench `.bbmodel`. If the user has not said, list `src/main/resources/assets/*/models/item/` and ask, or pick the one
they just changed (`git status`).

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/build_viewer.py" <model> --artifact -o <scratchpad>/<model>_viewer.html
```

`--artifact` writes just a title, a style block and the body, because the Artifact tool wraps the page in its own
`<html>`/`<head>`/`<body>`. Leave it off (and add `--open`) only to view the file locally in a browser.

Put the output in the session scratchpad, not the repository. Read the printed warnings (missing textures, vanilla parent
models that are not bundled) and tell the user about any.

Options: `--skin FILE` or `--skin-name PLAYER` (the character's skin; default is the bundled one),
`--resources DIR` (extra assets folder for models kept outside the project), `--wings vampire` (ORVCraft only).

## 2. Check for problems, and ask

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/check_model.py" <model> --json
```

It lists things that are usually mistakes (z-fighting, missing parents or textures, elements outside the game's -16..32 range,
UVs outside 0..16, unsupported rotations, missing display transforms) and changes nothing. **Never assume a finding is a bug
or that it is fine: ask the user whether each one is intended**, with the AskUserQuestion tool (up to four at a time, grouping
findings of the same kind into one question). Options: "Intended, leave it", "Not intended, fix it", "Show me first".

* Intended: leave it, and do not raise that finding again in this conversation.
* Not intended: fix it. For z-fighting run `fix_zfighting.py <model.json> --fix` (it nudges the smaller face out by 0.01 unit and
  keeps the file's formatting); for anything else make the smallest edit that resolves it and say what changed.
* Show me first: describe the exact edit, or for a layout problem publish the viewer first, then ask again.

Rebuild the page after any fix, so what is published matches the file.

## 3. Publish it

Load the `artifact-design` skill, then publish the HTML with the Artifact tool. Title it `<Model Name> Viewer` (two to four
words), use a short generic icon such as `cube`, and describe it in one sentence. The page handles dark and light themes and
loads three.js only from jsDelivr, which Artifacts allow. Give the user the link, and say what to try:

* **In game** dropdown: held in either hand, worn, in an inventory slot, or floating above the head (item display, with a scale slider).
* **Animation** dropdown: idle, walk, sprint, attack swing, overhead slam.
* Drag to orbit, scroll to zoom, right-drag to pan.

If the model changes, rebuild and republish to the same Artifact URL.

## Notes

* Cuboid models and Blockbench projects only; no other entity renderers. `check_model.py` reads `.json` models only.
* Character animations follow the game's `HumanoidModel` maths (walk, sprint, attack swing, held-item arm pose). The Giant Hammer's
  own swing is ported from its mod code, and is offered only for a model titled "Giant Hammer".
* The viewer needs internet access (three.js comes from a CDN); the model and textures are embedded.
* `${CLAUDE_PLUGIN_ROOT}/README.md` documents everything.
