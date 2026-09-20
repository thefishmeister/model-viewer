# Model viewer (Claude Code plugin)

Install: `/plugin marketplace add <github-user>/model-viewer` (or a local path) then `/plugin install model-viewer@model-viewer`. Run the scripts from your project root; assets are read from its `src/main/resources/assets` and `src/client/resources/assets`.

Look at any Minecraft item or block model in 3D, held by a character, before it is pushed to `dev`.

```
python scripts/build_viewer.py giant_hammer          # writes giant_hammer_viewer.html
python scripts/build_viewer.py royal_crown --open    # ...and opens it in your browser
```

The result is one self-contained HTML file: the model, its parent models and its textures are embedded. It loads
three.js from the jsDelivr CDN, so it needs an internet connection to display. It needs Python 3.9+ and nothing else.

## In Claude Code (the chat)

Ask for it: *"show me the giant hammer in 3D"*, *"let me look at my new sword"*. The plugin's `view-model` skill
(`skills/view-model`) builds the page with `--artifact` (a fragment: the Artifact tool supplies the page around it) and publishes it, so the model can be rotated right in the
conversation, and the link can be shared with the team for review.

## What the page can do

| Control | What it does |
| --- | --- |
| **In game** | Model only, held in the right or left hand, worn on the head, in an inventory slot, dropped, in an item frame, first person, or floating above the head as an item display (with a scale control). Uses the game's own mounting transforms and the model's `display` block. |
| **Animation** | Idle, walk, sprint, attack swing, overhead slam, driven by the same limb maths the game uses. Speed slider, pause. |
| **View** | North / South / East / West / Top / Iso, plus free orbit, zoom and pan. |
| **Show** | Auto-rotate, wireframe, full-bright, the 1-block cube, the character, the floor grid, light or dark stage. |
| **Model** | Element count, texture count, size in model units, and warnings (missing textures, missing parent models). |

The character wears a real 64x64 skin (both layers, classic or slim arms). The default is `skins/DEFAULT`; change it by
dropping a skin PNG into `tools/model_viewer/skins/` and editing that file, or per run:

```
python scripts/build_viewer.py giant_hammer --skin path/to/skin.png
python scripts/build_viewer.py giant_hammer --skin-name SomePlayer   # downloads the skin from Mojang
```

`--skin-name` fetches the skin from Mojang's public profile servers (`api.minecraftservices.com`,
`sessionserver.mojang.com`, `textures.minecraft.net`) and saves it under `skins/`. For a slim (Alex) skin, put
`{"model": "slim"}` in a `<name>.json` beside the PNG; `--skin-name` does this for you.

## Worn wings

`build_viewer.py --wings vampire` shows the Lord of the Night wings on the character instead of an item model, with a
Wings menu (resting, flight, crouching) that eases between poses as the game does, alongside the usual Idle, Walk and
Sprint. Its geometry comes from `tools/vampire_wings/generate_wings.py` and must match `VampireWingsModel.java`.

## Naming a model

```
build_viewer.py giant_hammer                 a bare name: looks in models/item, then models/block
build_viewer.py orvcraft:item/void_bow       a full id
build_viewer.py path/to/model.json           any file
build_viewer.py my_model --resources DIR     extra assets folder (holding <namespace>/models and <namespace>/textures)
```

It reads `src/main/resources/assets` and `src/client/resources/assets` by default. Parent models inside the mod's assets
are followed. Vanilla parents such as `minecraft:block/cube_all` are not bundled, so a model that inherits its shape from
one shows a warning; `item/generated` and `item/handheld` (flat sprites) are built in.

## z-fighting

Two faces in the same plane, facing the same way, flicker or show the wrong texture. Cross-shaped cuboids (a plus made of
two boxes) share their top and bottom faces, so they do it a lot.

```
python scripts/fix_zfighting.py path/to/model.json          # report
python scripts/fix_zfighting.py path/to/model.json --fix    # nudge the smaller face out by 0.01 unit
```

Run it before pushing a model. It leaves the file's formatting alone.

## Limits

* Cuboid models only: no entity models, no Blockbench `.bbmodel` animations, and no `builtin/entity` renderers.
* The character animations are the vanilla limb poses, not custom ones your item might play in game.
* Display transforms are close to the game's but not pixel-exact (rotation order and the left-hand mirroring follow the game).
* Elements rotate about one axis with any origin, as the format allows; `rescale` is ignored.

## Files

* `build_viewer.py` builds the page. `viewer_template.html` is the page (three.js, the character, the controls).
* `fix_zfighting.py` finds and fixes overlapping coplanar faces.
* `skins/` holds the character's skin(s); `skins/DEFAULT` names the one used.
* `.claude-plugin/plugin.json` is the plugin manifest; `skills/view-model/SKILL.md` is the skill.
