# Track description reference

A description is YAML (`.yaml`/`.yml`) or JSON. Only `name` and
`track.control_points` are required. Unlisted fields use the defaults here.

Distances are **feet**, angles are **degrees**. Any `at` field accepts a number
of feet or a percentage string like `"37%"` measured from the start line.

## Top level

| field | default | meaning |
| --- | --- | --- |
| `name` | required | track folder name; sanitised to `[A-Za-z0-9_-]` |
| `title` | name in caps | minimap title and preview heading |
| `desc` | title | long name written to the `desc` file |
| `seed` | `1` | drives terrain noise and prop scattering; change for a different look |
| `obstacles` | `[]` | list of obstacle entries |
| `statues` | `[]` | statue scatter rules |
| `billboards` | `[]` | billboard scatter rules |
| `terrain`, `track`, `theme`, `gates` | see below | sections |

## terrain

| field | default | meaning |
| --- | --- | --- |
| `dimension` | `9` | `9` = 1025 px, `10` = 2049 px, `11` = 4097 px |
| `resolution` | `2.0` | feet per heightfield pixel |
| `base_height` | `55` | average ground height in feet |
| `relief` | `16` | amplitude of rolling terrain |
| `roughness` | `0.35` | 0-1 amount of small-scale noise |
| `margin` | `1.0` | padding added to the low/high range in `terrain.hf` |
| `hills` | `[]` | `{x, z, radius, height}` gaussian hills/bowls |
| `smooth_iterations` | `0` | 3x3 heightfield passes; 2-8 soften station steps |
| `shoulder_smooth` | `0` | feet of box-blur outside the ribbon; 6-12 relaxes hooked shoulder creases without touching the riding surface |

World width is `2^(dimension+1) * resolution` feet:
`9 / 2.0` = 2048 ft, `10 / 1.25` = 2560 ft, `9 / 0.75` = 768 ft,
`8 / 2.0` = 1024 ft.

`resolution` is the single biggest quality/size lever. 2.0 ft is a normal
national; 1.0 ft is detailed but four times the pixels; 0.75-1.0 suits
supercross. 0.625 ft on a 2,560 ft national gives a 4097 px heightfield (29 MB
terrain texture); it is large but supported.

## track

| field | default | meaning |
| --- | --- | --- |
| `control_points` | required | closed loop of `[x, z]` in feet, at least 3 |
| `width` | `26` | running surface width in feet |
| `start_width` | auto | ribbon width at the start; defaults to gate row + 8 ft |
| `start_taper` | `160` | feet to blend `start_width` back to `width` |
| `start_flat` | `90` | feet around the start flattened for the gate |
| `smooth` | `45` | feet of smoothing on the base elevation profile |
| `elevation_smooth` | `80` | feet of smoothing on an explicit `elevation` profile |
| `crown` | `0.0` | feet of crown at the ribbon centre |
| `edge_falloff` | `18` | feet of blend from ribbon to terrain |
| `elevation` | `[]` | absolute height overrides: `{at, height}` |

Control points define a **corner-to-corner closed loop**. The spline passes
through each point; order is direction of travel. The first point is the start
line, so place the last two points on the same line behind it: a straight start
needs the incoming and outgoing tangents aligned. Aim for roughly 300 degrees
of direction change per 1,000 ft on a national (about 380 on SX) and keep the
tightest centreline radius at least 0.6 x `track.width`; the build warns below
that because the ribbon can pinch.

```yaml
track:
  control_points:
    - [330, 1450]   # start/finish
    - [350, 1100]
    - [440, 800]
    # ...
    - [330, 1750]   # approach behind the start
```

`elevation` is useful for a deliberate ridge or valley; it replaces the base
terrain profile with a smoothed line through your points. Put a point at both
0% and 100% with the same height, and allow 40-60 ft of change over several
hundred feet so the grades stay rideable (roughly 3-6%). `elevation_smooth`
softens the joins. A high track needs a broad shoulder: use `edge_falloff` 120-180 ft for 20-35 ft of fill,
not the default 18. Cactus uses 170 ft.

```yaml
  elevation_smooth: 80
  elevation:
    - {at: "0%", height: 42}
    - {at: "20%", height: 62}
    - {at: "45%", height: 38}
    - {at: "70%", height: 58}
    - {at: "100%", height: 42}
```

## obstacles

Each entry needs `type` and `at`. Unknown types are rejected. Overlapping
obstacles add their heights and produce a warning.

### jump

| field | default | meaning |
| --- | --- | --- |
| `height` | `7` | takeoff lip height, ft |
| `takeoff_angle` | `22` | ramp angle, degrees |
| `gap` | `45` | horizontal lip-to-landing-crest distance, ft |
| `table` | `0` | flat table length on top, ft |
| `landing_length` | `35` | landing downslope length after the crest, ft |
| `landing_ratio` | `0.85` | landing peak height / takeoff height |
| `backside_angle` | `45` | maximum takeoff-backside slope, degrees |
| `landing_face_angle` | `42` | maximum landing near-face slope, degrees |
| `reverse` | `false` | mirror the jump in place for a track ridden the other way |

A double is an engineered takeoff ramp, a steep backside, a flat gap floor, a
short landing face and then a descending landing. `gap` is measured from the
lip to the landing crest, not to the start of the landing face. The takeoff
ramp ends at the requested angle; it does not flatten at the lip.

Use `reverse: true` when the route is ridden in the opposite direction from
the control-point order. It mirrors the finished jump inside the same
footprint, so the takeoff and landing swap ends without moving the obstacle.
Apply it to every jump and tabletop on that route, not just one.

Setting `table: 20` and `gap: 0` gives a tabletop: a smooth ramp onto a flat
top, then a rollable descent. `gap: 0` and `table: 0` gives a kicker. A jump
cannot combine a table and a gap.

### tabletop

Same fields as `jump`, defaults: height 6, angle 20, table 18, landing 30,
`landing_ratio: 1.0`. For a tabletop, `takeoff_angle` is the steepest part of
the ramp; the top joins the table flat so it can be rolled.

### whoops / rollers

| field | default (whoops / rollers) | meaning |
| --- | --- | --- |
| `count` | 6 / 3 | number of bumps |
| `spacing` | 26 / 52 | feet between bump starts |
| `height` | 2.6 / 3.5 | bump height, ft |
| `height_start_ratio` | 0.6 / 0.7 | first bump height relative to full |

Bumps are `sin^2` humps, so they have no sharp edges; the first bump is smaller
to ease entry.

### berm

| field | default | meaning |
| --- | --- | --- |
| `length` | `70` | length along the track, ft |
| `height` | `3.0` | bank height at the outside edge, ft |
| `side` | `auto` | `auto`, `left` or `right` |

`auto` averages curvature over the berm length and raises the outside of the
turn. The inside half stays flat: the bank is one-sided, not a V-shaped cut.
The bank rises on a smootherstep, and the terrain ribbon interpolates between
stations so the face is not built from 1 ft terraces. The build warns when a
berm is on a straight, crosses a curvature reversal, or is forced to the inside
of its corner.

### rut

| field | default | meaning |
| --- | --- | --- |
| `length` | `80` | length along the track, ft |
| `width` | `3.4` | full rut width, ft |
| `depth` | `0.32` | depth at the rut centre, ft |
| `offset` | `6.0` | distance from the centreline, ft |
| `side` | `auto` | `auto`, `left` or `right` |

A rut cuts a shallow groove without adding a raised edge. `auto` puts it on
the inside of the turn and samples curvature across the whole rut, so it can
be used through flat corners to define an exit line. The groove returns
smoothly to the flat track at both lateral edges and tapers to zero at both
ends. Use 2.5-4 ft width and 0.2-0.4 ft depth for a normal MX rut; the build
warns above 0.6 ft.

## theme.map

| field | default | meaning |
| --- | --- | --- |
| `size` | `1024` | map image size; keep a power of two |
| `background` | `null` | `null` = transparent, else `#rrggbb` |
| `track_colors` | `["#8a5a35"]` | one colour, or a list for stripes |
| `outline` | `"#111111"` | continuous outline colour |
| `outline_width` | `10` | outline pixels at size 1024 |
| `track_width` | `22` | ribbon pixels at size 1024 |
| `stripe_length` | `260` | feet per colour band |
| `title` | track title | text, or `null` to omit |
| `title_color` | `"#ffffff"` | fill |
| `title_outline` | `"#111111"` | stroke |
| `title_size` | `76` | pixels at size 1024 |
| `title_position` | `bottom` | `bottom` or `top` |
| `show_start` | `true` | white start bar across the ribbon |
| `show_gates` | `true` | checkpoint dots |

High-contrast blue stripes: `track_colors: ["#0b66d6", "#46b7ff"]` with a
dark `outline` gives a bright blue ribbon that reads over tan terrain.

## theme.ground

| field | default | meaning |
| --- | --- | --- |
| `size` | `2048` | decal texture size (power of two recommended) |
| `base_color` | `"#8d9a6a"` | grass/base everywhere the ribbon is not |
| `dirt_color` | `"#8a5a35"` | ribbon colour |
| `edge_falloff` | `12` | feet of dirt-to-base blend |
| `noise` | `0.45` | 0-1 mottling |
| `noise_scale` | `120` | feet per noise feature |
| `friction` | `[1.0, 6.0]` | tileinfo friction coefficient and slip speed (ft/s) |
| `roll_resist` | `[5.0, 15.0, 10.0]` | tileinfo low/high/value rolling resistance |

These set the single generated `tileinfo` tile; the all-zero `tilemap` paints
it across the whole track. `base_color: null` makes the decal transparent
outside the ribbon instead of painting a base.

## statues

| field | default | meaning |
| --- | --- | --- |
| `model` | required | `.jm` path, normally `@Track/statues/x.jm` |
| `texture` | required | `.png`/`.ppm` path |
| `shape` | `null` | `.shp` path or `null` |
| `count` | `0` | attempts to place |
| `min_distance` | `20` | feet outside the ribbon edge |
| `max_distance` | `200` | outer band from the ribbon |
| `min_spacing` | `12` | feet between props |
| `side` | `both` | `both`, `left`, `right` |
| `rotation_degrees` | `random` | number, `random`, or `[min, max]` |
| `y_offset` | `0` | feet above ground (0 = on the terrain) |
| `enabled` | `true` | set false to keep a rule but skip it |

The file stores height above ground, not absolute elevation; `y_offset` can
sink a statue slightly (e.g. `-2`).

## billboards

| field | default | meaning |
| --- | --- | --- |
| `texture` | required | sprite path |
| `count` | `0` | attempts to place |
| `min_distance` | `20` | feet outside the ribbon edge |
| `max_distance` | `200` | outer band |
| `min_spacing` | `15` | feet between sprites |
| `side` | `both` | `both`, `left`, `right` |
| `height` | `40` | sprite height in feet |
| `aspect` | `1.0` | width / height |
| `width` | - | deprecated alias for `height` |
| `y_offset` | `0` | feet above terrain |
| `enabled` | `true` | skip a rule |

Billboards are camera-facing sprites; there is no rotation field in the game
format.

## gates

| field | default | meaning |
| --- | --- | --- |
| `start_at` | `0` | distance of the start line (feet or `%`) |
| `start_count` | `20` | gate boxes |
| `spacing` | `4` | feet between gate boxes |
| `checkpoint_count` | `7` | lap checkpoints, at least 3 |
| `checkpoint_offset` | `0` | feet after the start for the first checkpoint |
| `width_margin` | `8` | checkpoint width beyond `track.width` |
| `checkpoint_width` | auto | override checkpoint width |
| `y_offset` | `0` | feet above ground for gates (0 = on the terrain) |

Checkpoints are spaced evenly around the lap and oriented perpendicular to
travel using the spline tangent as their normal. The first lap needs at least 3
checkpoints, so lower values are rejected.

## Minimal example

```yaml
name: Test_MX
track:
  control_points:
    - [300, 900]
    - [320, 500]
    - [700, 350]
    - [1000, 650]
    - [850, 1000]
    - [500, 1050]
    - [300, 1150]
  width: 26
obstacles:
  - {type: jump, at: "20%", height: 6, takeoff_angle: 22, gap: 35, landing_length: 28}
  - {type: berm, at: "55%", length: 70, height: 3}
theme:
  map:
    track_colors: ["#0b66d6", "#46b7ff"]
```
