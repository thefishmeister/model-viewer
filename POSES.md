# Pose profiles: how an item is held and swung in game

The viewer draws vanilla poses. A mod usually changes them in code (a mixin into `HumanoidModel` or `ItemInHandLayer`, an arm
pose, an item extension), so a scythe carried low, a two-handed hammer or a sword raised overhead all look wrong until the
viewer is told. A **pose profile** is that information as data, so the viewer needs no per-item code.

`scripts/scan_poses.py <item>` finds where a project defines the pose. The `view-model` skill reads what it finds, writes the
profile and asks you about anything it is unsure of. To write one by hand, save it as either

* `<model>.pose.json` beside the model (`.../models/item/scythe.pose.json`), or
* `.model-viewer/poses/<model>.pose.json` in the project root,

or pass `--pose FILE` to `build_viewer.py`. Angles are **radians** for body parts (as `ModelPart.xRot` is) and **degrees** for the item.
Write the profile for a **right-handed** main arm: a left-handed view mirrors it, as the game does.

```json
{
  "item": "mymod:scythe",
  "source": "src/client/java/.../ScytheHold.java",
  "carry": {
    "rightArm": { "x": 0.9, "z": 0.1 },
    "leftArm":  { "x": 0.2 },
    "item":     { "x": -35, "pivot": [-1.67, 2.26] }
  },
  "animations": {
    "swing": {
      "ticks": 12, "gap": 8, "ease": "smooth",
      "tracks": {
        "rightArm.x": [[0, 0.9], [0.4, -2.0], [1, 0.9]],
        "body.y":     [[0, 0], [0.5, 0.4], [1, 0]],
        "item.x":     [[0, -35], [0.5, -90], [1, -35]]
      }
    }
  }
}
```

* **`carry`**: applied whenever the item is held, on top of vanilla walking, idle and so on (as a mixin at the tail of `setupAnim`
  does). Parts: `head`, `body`, `rightArm`, `leftArm`, `rightLeg`, `leftLeg`, each with `x`, `y`, `z`. Values replace the vanilla
  ones; add `"mode": "add"` to add to them instead. `item` turns the held item about `pivot` (`[y, z]` in pixels, in the hand's
  frame) by `x`, `y`, `z` degrees, and moves it by `tx`, `ty`, `tz` pixels.
* **`animations`**: each becomes an "Item: name" entry in the Animation menu. `ticks` is its length, `gap` the pause before it
  repeats (or `"loop": true`), `tracks` maps `part.axis` (or `item.x`, `item.tx`, ...) to `[progress 0..1, value]` keyframes.
  `ease` is `linear` (default), `smooth` or `in`.

**Recorded profiles.** `scripts/install_recorder.py` adds a recorder to a Fabric mod's client code (`recorder/`). In a development game
it writes the profile itself while the item is held and swung in third person: every part's rotation and position from the finished
pose, with axes `x y z` (radians) and `px py pz` (pixels), plus `itemMatrix`, the item's exact transform in the character's model
space (16 numbers, column-major; keyframed as `[progress, [16 numbers]]` inside an animation). It lands in
`<run folder>/model-viewer/poses/<item>.pose.json`. A left-handed wielder is recorded mirrored, as a right-handed one.

The viewer never applies a profile until the user presses **Load accurate in-game animations**.

Not expressible as data, so ported by hand: solved poses such as the Giant Hammer's second hand finding the haft. That one is built in.
