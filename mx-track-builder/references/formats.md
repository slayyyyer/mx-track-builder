# MX Simulator track formats

Verified against the official `blank_track.zip` (mxsimulator.com/editing.html),
the manual, and the 2026 community track editing guide. All text files use
**unix line endings**; the generator normalises every file it writes.

## Folder

```
%LOCALAPPDATA%\MX Simulator\<TrackName>\
    terrain.hf
    terrain.png
    map.png
    desc
    decals
    ground\ground.png
    ground\tile.png
    statues
    billboards
    timing_gates
    tileinfo
    tilemap
    lighting
    (optional) shading.ppm, shadingx2.ppm, shadows.pgm, flaggers, texturelist
```

The track folder must sit **directly** in the MX Simulator folder. Nested
folders are visible to the game but break media paths (white or black ground).

## terrain.hf

Plain text, one line:

```
9 2.000000 36.0 57.0
```

`[dimension] [resolution] [lowest point] [highest point]`

- `dimension 9` = 1025 x 1025 heightfield (`2^(9+1)+1`); `10` = 2049;
  `11` = 4097.
- `resolution` = feet between heightfield points.
- The world is `2^(dimension+1) * resolution` feet across.
- Heights in feet; `low`/`high` span the 16-bit texture.

## terrain.png

- Square, `2^(dimension+1)+1` pixels, **16-bit greyscale**, no alpha.
- Pixel value 0 = `low` in terrain.hf, 65535 = `high`.
- The generator writes this with a built-in encoder, not Pillow, so the bit
  depth is always correct.
- Image row 0 is world z = 0; column 0 is world x = 0. `map.png` uses the same
  convention, so the minimap matches the terrain.

## map.png

- RGBA PNG, power-of-two size (non-power-of-two works but logs a warning).
- This is the minimap in the top right. Transparent background is allowed.
- Same orientation as terrain.png.

## desc

One line with the track's long name.

## decals

One line per decal:

```
[512.000000 512.000000] 0.000000 1024.000000 1.000000 @Cactus_Ridge/ground/ground.png
```

`[x z] rotation size aspect @texture`

- Rotation is radians.
- `size` is the decal's long-axis length in feet, `aspect` the other axis ratio.
- Paths starting with `@` resolve from the MX Simulator folder.
- The decal *list* is a file named `decals`. On Windows the texture folder
  therefore **cannot** also be called `decals`; this generator uses `ground/`.
- A single decal covering the whole world is legal; use a large power-of-two
  texture for detail.

## statues

```
[330.000000 51.200000 1200.000000] 0.523599 @Cactus_Ridge/statues/cactus.jm @Cactus_Ridge/statues/cactus.png null
```

`[x y z] rotation @model.jm @texture.png @shape.shp|null`

- `y` is height **above the local ground**, not absolute elevation (blank track
  props sit at y = 0 on flat ground at 0). Negative values sink a prop.
- The field after the position is **rotation in radians**, not scale. A scale of
  0.0 would make every prop invisible, and community tools scale the `.jm`
  geometry because the text format has no scale field.
- `null` is accepted for the shape (blank track uses it).
- The generator places props outside the ribbon and writes `y_offset` directly
  (default 0 = on the terrain).

## billboards

```
[400.000000 -5.000000 10.000000] 80.000000 1.000000 @forestedge1.png
```

`[x y z] height aspect @texture.png`

- Camera-facing sprites used for trees, spectators and banners. There is no
  rotation field; orientation follows the camera.
- `height` is the sprite height in feet; `aspect` = width / height (x:y).
- `y` is height above the local ground; negative values sink the sprite.

## timing_gates

```
startinggate:
[1500.000000 0.000000 920.000000] 1.570000
...

checkpoints:
50.000000 [50.000000 0.000000 2000.000000] [1.000000 0.000000 0.000000]
...

firstlap:
0 1 2 3 4
normallap:
0 1 2 3 4
```

- Start gates: `[x y z] rotation`, rotation in radians. A row of gate boxes
  spaced ~4 ft across the start line, wide enough for the start straight.
  Rotation is `pi - atan2(nz, nx)`, normalized: the **reversed angle of the
  line across the track plus half a turn**, not the direction of travel. MX
  Sim's yaw is clockwise in x/z, and the gate models have a front and back.
  The negation keeps a diagonal row straight; omitting the half turn leaves the
  row straight but every gate facing backwards. Real tracks use this facing.
- Checkpoints: `width [x y z] [normal_x 0 normal_z]`. The normal is the direction
  of travel, which makes the plane perpendicular to the track.
- `firstlap` / `normallap` list the checkpoint indices used on those laps. The
  generator lists every checkpoint index in order.
- A track needs at least three checkpoints: the first lap must pass at least
  three gates before it can time a lap.

## tileinfo and tilemap

`tileinfo` defines ground types; `tilemap` selects one per terrain cell.

```
friction 1.0 6.0
friction 0.8 8.0
roll_resist 5.0 15.0 10.0
texture @Cactus_Ridge/ground/tile.png
addtile
```

- `friction <coefficient> <slipSpeedFt/s>`; stack lines to build a friction
  curve. `roll_resist <low> <high> <value>` is also stackable.
- `texture` points at the tile image; `addtile` closes each tile block.
- `tilemap` is raw bytes, `2^dimension` square (512 x 512 at dimension 9), one
  byte per terrain cell. The value indexes the `addtile` blocks in order.
- The generator writes one dirt tile and an all-zero map, so tile 0 covers the
  whole track. A missing tile texture renders the track black.
- `texturelist` is the legacy alternative (`1 5 15 dirt.ppm`); `tileinfo` is
  the current format.

## lighting

```
sun_vector [ 1.00 1.00 1.00 ]
sun_color [ 1.00 1.00 0.50 ]
ambient [ 0.25 0.25 0.50 ]
```

- `sun_vector` is the direction the light travels **from**, not a position.
- `ambient` affects terrain and decals; objects use `global_ambient` when it is
  present.
- Optional keys include `sky_*`, `flare_*`, `fog`, `near_plane`, `far_plane`
  and `dynamic_lighting 1`.
- A malformed `dynamic_lighting` line (for example `dynamic lighting 1`) is a
  load error.

## Optional files

- `shading.ppm`, `shadingx2.ppm`, `shadows.pgm`: baked shading and shadow
  layers; the game regenerates `shading.ppm` when shaders are on.
- `flaggers`: flagger positions plus animation state.

The generator writes `tileinfo`, `tilemap`, `lighting` and the tile texture;
the files above are optional. Decals supply the visible ground, and the
generated one-tile tileinfo supplies basic traction.

## Coordinates and units

- One world unit is one foot on the horizontal plane. Heights are feet.
- `x` is image column, `z` is image row for generated images.
- Rotation in text files is radians; the description schema uses degrees and
  converts.
- The spline's left normal is `(-tz, tx)`; positive curvature is a left turn.

## Common format mistakes

- Writing `terrain.hf` as binary. It is text.
- Using `2^dimension` instead of `2^(dimension+1)+1` for the PNG size.
- Saving `terrain.png` as 8-bit. Heights become blocky and jumps lose shape.
- CRLF line endings. The game is tolerant in places, but the manual specifies
  unix endings and the generator enforces them.
- A file named `decals` next to a folder named `decals`.
- Pointing at `@Track/...` assets with the wrong track folder name.
