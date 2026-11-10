---
name: mx-track-builder
description: Create, regenerate or fix MX Simulator tracks from a YAML/JSON track description. Use this skill whenever the user mentions an MX Simulator or MXS track, track folder, terrain.png, terrain.hf, map.png, decals, timing gates, statues or billboards for MX Sim, or asks for a motocross/supercross layout to build, change or repair. The bundled deterministic scripts turn one closed-spline description into all game files, so never hand-draw a track map or hand-write coordinates - describe the layout and run the scripts.
---

# MX Track Builder

Builds a complete, game-readable MX Simulator track folder from one description
file. One closed spline drives everything: terrain ribbon, minimap, ground
decal, statues/billboards and timing gates. Move a control point and every
output stays consistent.

## The one rule

Do not draw maps or invent coordinates in chat. Write the description, run the
scripts, look at the generated preview and map, then adjust the description.
The generator is deterministic (same description + seed = byte-identical
files), so each rebuild is a clean, reviewable step.

## Quick start

```bash
# once, from the skill folder
python -m pip install -r requirements.txt        # Windows: py -m pip install -r requirements.txt

# build the example
python scripts/build_track.py assets/examples/cactus-ridge.yaml --out ./tracks

# check the generated folder against the game's formats
python scripts/validate_track.py ./tracks/Cactus_Ridge

# build every bundled example, twice, and validate them
python scripts/selftest.py
```

The build prints the lap length, height range, obstacle summary, prop counts,
estimated jump clearing speeds and warnings. It writes a hillshade preview next
to the track folder (`<Name>_preview.png`).

## Workflow

1. **Start from an example** in `assets/examples/` and copy it next to your
   project. Keep the example's structure; change values.
2. **Lay out the loop** with `track.control_points` in feet. The first point is
   the start/finish; the last point should sit *behind* it on the same line so
   the start straight is actually straight. See `references/description.md`.
3. **Place obstacles by percentage** (`at: "37%"`) so they stay put when the
   layout changes. Tune with `references/tuning.md`.
4. **Choose a theme**: map colours/outline/title and ground colours. Multiple
   `track_colors` become stripes along the ribbon (good for flag themes).
5. **Add props and gates** with `statues`, `billboards` and `gates`.
6. **Build**, then inspect `<Name>_preview.png` and the track folder's
   `map.png`. Check for self-intersections, jumps on corners, props in the
   track, and a sane lap length.
7. **Validate** with `validate_track.py`. Fix warnings in the description and
   rebuild; do not patch generated files.
8. **Install**: copy the folder directly into `%LOCALAPPDATA%\MX Simulator\`
   (not into a subfolder), then launch `mx.exe --track <Name>`.

The agent can inspect the PNGs with its image-reading tools and iterate without
ever opening the game. Report the lap length, obstacle summary and any warnings
when handing the track back.

## Layout guidance

- World size is `2^(dimension+1) * resolution` feet. The default (dimension 9,
  resolution 2.0) is 2048 x 2048 ft. The bundled Cactus national uses 2,560 ft
  (dimension 11, 0.625 ft/px) so its 1.74-mile folded lap has room to breathe and
  its jumps stay smooth at 4,097 px.
- World size and lap length are separate: the former is the terrain extent, the
  latter is the control-point path. To make a track longer, spread the points
  and/or add hooks; enlarge the terrain if the new layout needs room. Scaling a
  built track does not lengthen its centreline.
- Keep control points at least 100-150 ft from the terrain edge. The ribbon plus
  its edge falloff is clipped at the edge.
- Real MX layouts average about 300 degrees of direction change per 1,000 ft
  and 2.4 corners of 45 degrees or more; SX is tighter, around 380 degrees and
  3.3 corners. A simple national usually needs 16-24 points and an SX 14-20; a
  technical national with a folded lane layout needs more corner points (the
  folded Cactus example uses 467). Use 80-250 ft spacing through corners
  and 250-450 ft on straights.
- Keep the tightest centreline radius at least 0.6 x track width. The build
  warns if a hairpin is tight enough to fold the ribbon.
- A control point is a **corner**, not a waypoint: the spline passes through it.
  Put two points in a row to make a straight.
- For line choices, include **six to eight return hooks** on a national: short
  U-shaped detours whose outbound and return lanes are roughly 100-180 ft
  apart. Keep both hook turns at or above the minimum radius so the ribbon does
  not fold.
- Order defines travel direction (positive curvature turns left).
- The start straight must be at least ~250 ft for a national and ~140 ft for an
  SX. `track.start_width` widens the ribbon for the gate row; `start_taper`
  blends it back to `track.width`. Put the last two control points on the start
  line and begin the turn onto it earlier; a single last point turns too
  sharply.
- Put big jumps on straights, not at maximum curvature. The preview shows both.
- For elevation, add `track.elevation` points with the same height at 0% and
  100%; 40-60 ft of range over a national gives real climbs and descents.
  Aim for roughly 3-6% grades; `elevation_smooth` softens the transitions, and
  jumps add on top. With a high track, widen `edge_falloff` to 120-180 ft for 20-35 ft of fill so the
  shoulder does not become a cliff. `terrain.smooth_iterations: 8` lightly
  rounds the 0.625 ft grid on sharp jump faces and berm shoulders. For return
  hooks whose wide falloffs overlap, add `terrain.shoulder_smooth: 6-12`; it
  blurs only outside the ribbon and preserves the riding surface.
- Percentages are measured from the start line, so `at: "95%"` is just before
  the line and `at: "0%"` is on it.

## Obstacle presets

All distances are feet, angles are degrees, `at` accepts feet or a percentage.

| type | key fields | sensible range |
| --- | --- | --- |
| `jump` | `height`, `takeoff_angle`, `gap`, `landing_length`, `landing_ratio`, `backside_angle`, `landing_face_angle`, `reverse` | height 4-9, angle 18-28, gap 25-70, landing 35-65 |
| `tabletop` | `height`, `takeoff_angle`, `table`, `landing_length` | height 4-8, table 12-30 |
| `whoops` | `count`, `spacing`, `height`, `height_start_ratio` | 4-8 bumps, 18-32 ft spacing, 1.5-3.5 ft high |
| `rollers` | `count`, `spacing`, `height` | 2-4 rollers, 35-60 ft spacing |
| `berm` | `length`, `height`, `side` | length 50-120, bank 2-5 ft |

A jump is built as an engineered takeoff ramp (ending at the requested angle)
→ smoothed backside → flat gap floor → short landing face → descending landing.
`gap` is horizontal lip-to-landing-crest distance; the landing face is inside
it. `backside_angle` and `landing_face_angle` are true maximum slopes, not just
labels. The build prints a projectile clearing speed that accounts for the
landing height; above ~70 mph means shorten the gap.

A tabletop uses the same ramp shape but a flat top and no gap. A jump cannot
combine `table` and `gap`.

`berm` is one-sided: the inside half stays flat and the outside rises on a
smootherstep, so it does not cut a V through the infield. `side: auto` averages
curvature across the berm; the build warns on straights and curvature
reversals. Use `left`/`right` to force it.

## Theme and map

```yaml
theme:
  map:
    size: 1024                 # power of two; RGBA minimap
    background: null           # null = transparent
    track_colors: ["#0b66d6", "#46b7ff"]  # blue stripes
    outline: "#0b0b0b"
    outline_width: 12
    track_width: 26            # pixels at map size 1024
    stripe_length: 230         # feet per colour band
    title: CACTUS RIDGE
    title_color: "#ffffff"
    title_outline: "#0b0b0b"
  ground:
    base_color: "#b3a06a"
    dirt_color: "#96603c"
    edge_falloff: 13           # feet of blend outside the ribbon
    noise: 0.5
    friction: [1.0, 6.0]       # tileinfo: coefficient, slip speed (ft/s)
    roll_resist: [5.0, 15.0, 10.0]  # tileinfo: low, high, value
```

The map rasterises the outline and ribbon as continuous shapes, so the outline
never shows through the fill, and stripes follow distance along the spline. A
single `track_colors` entry gives a plain track.

## Statues and billboards

```yaml
statues:
  - name: cactus
    model: "@Cactus_Ridge/statues/cactus.jm"
    texture: "@Cactus_Ridge/statues/cactus.png"
    shape: null
    count: 45
    min_distance: 16           # feet outside the ribbon edge
    max_distance: 260
    min_spacing: 16
    side: both
    rotation_degrees: random
billboards:
  - texture: "@Cactus_Ridge/billboards/joshua_tree.png"
    count: 55
    min_distance: 40
    max_distance: 280
    height: 44                   # sprite height in feet
    aspect: 1.0
```

- Statue `model`/`texture`/`shape` are game paths, normally `@Track/...`. The
  assets are **not** generated; point them at files that exist or the game skips
  them silently. The build warns about this.
- Statues are placed on the ground. The file stores `y` as height above the
  local ground, not absolute elevation; `y_offset` lifts or sinks the model
  (0 = on the terrain), and rotation is radians (the description uses degrees).
- Scatter is seeded and rejection-sampled: `min_distance` from the track,
  `max_distance` for scenery bands, `min_spacing` between props, clipped to the
  terrain.
- Billboards in MX Sim are camera-facing sprites. There is no rotation field;
  "facing the track" is achieved by placing them beside it, which this does.
- Billboard `height` is the sprite height in feet; `aspect` is width / height.

## Gates

```yaml
gates:
  start_at: 0
  start_count: 20       # gate boxes across the start
  spacing: 4            # feet between them
  checkpoint_count: 7
  checkpoint_offset: 0
  width_margin: 8       # checkpoint width beyond track width
```

Starting gates are written as `[x y z] rotation`; checkpoints as
`width [x y z] [travel_x 0 travel_z]`, so they are perpendicular to travel by
construction. Start-gate rotation uses the **reversed angle of the line across
the track plus half a turn**: `pi - atan2(nz, nx)`, normalized. MX Sim's yaw is
clockwise in x/z, and the gate models are directional. The negation keeps a
diagonal row straight; the half turn stops the gate fronts facing backwards. It
is not the travel tangent. `firstlap`/
`normallap` list every checkpoint index. The start row is 20 gates x 4 ft =
80 ft wide, so the start straight is widened to match. `checkpoint_count` must
be at least 3 so the first lap has enough gates.

## Generated files

| file | contents |
| --- | --- |
| `terrain.hf` | text: `dimension resolution low high` |
| `terrain.png` | 16-bit greyscale heightfield, `2^(dim+1)+1` square |
| `map.png` | RGBA minimap with outline, stripes, start bar and checkpoints |
| `desc` | long track name |
| `decals` | one full-terrain ground decal entry |
| `ground/ground.png` | dirt ribbon, edge falloff, noise, grass base |
| `statues` | `[x y z] rotation model texture shape` |
| `billboards` | `[x y z] height aspect texture` |
| `timing_gates` | start gates, checkpoints and lap lists |
| `ground/tile.png` | flat ground-tile texture under the decal |
| `tileinfo` | one ground tile: friction, roll_resist, texture, addtile |
| `tilemap` | raw `2^dimension` square bytes, all zero (tile 0) |
| `lighting` | sun vector/colour and ambient light |

`preview.png` lives next to the folder, not inside it. The whole track uses one
generated dirt tile; change `theme.ground.friction`/`roll_resist` for different
traction. `shading.ppm`, `shadingx2.ppm`, `shadows.pgm` and the legacy
`texturelist` are not generated; add them by hand only if a track needs custom
baked shading, shadows or hand-painted surface zones.

## Iterating

- **Move a corner**: edit the control point, rebuild, compare preview.
- **Add a jump**: add an obstacle entry at a percentage, rebuild, read the
  printed clearing speed, adjust `gap`/`angle`.
- **Change scale**: change `terrain.resolution` (all coordinates are feet, so
  the layout keeps its size) or `dimension` for more terrain around it.
- **Map colours**: change `track_colors`, `outline`, `title`.
- **Ground too wide/narrow**: `track.width` and `edge_falloff`.
- **Props too close**: raise `min_distance`; if placement warnings say it ran
  out of room, lower `count` or widen `max_distance`.

When a request cannot be expressed by the description, extend the generator and
document the new field in `references/description.md`; do not special-case
individual tracks in the build script.

## References

- `references/description.md` - every field, default and format.
- `references/formats.md` - exact MX Simulator file formats and gotchas.
- `references/tuning.md` - jump/whoop/berm numbers and speed sanity checks.
- `references/troubleshooting.md` - missing ground, floating statues, wrong
  scale, game not loading the track.

## Guardrails

- Do not claim a track is verified in-game unless it was actually loaded. The
  scripts validate file structure; they cannot test bike physics or visuals.
- Do not edit `terrain.png` or `map.png` by hand; change the description and
  rebuild.
- Do not move the track folder into a subfolder of the MX Simulator folder; the
  game will see it but media paths break.
