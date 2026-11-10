# Tuning the ride

These are starting points, not physics. MX Sim bikes are unforgiving, and a
track that looks right in the preview still needs a lap in game.

## Scale

| track | terrain | width | lap length |
| --- | --- | --- | --- |
| national | 2048-2560 ft, 0.625-2.0 ft/px | 24-30 ft | 1.0-1.8 miles |
| supercross | 700-900 ft pad, 0.75-1.0 ft/px | 22-26 ft | 1,400-2,000 ft |
| mini / pit bike | 1024 ft, 2.0 ft/px | 20-24 ft | 1,200-2,500 ft |

Bigger `resolution` values mean coarser terrain: at 2.0 ft/px a 2 ft whoop is
one pixel wide and will look like a step. Use 1.0 ft/px or finer for small SX
obstacles.

## Jumps

- Takeoff angle: 18-24 degrees is a normal MX lip; 25-30 is steep and poppy.
- Lip height: 4-6 ft is small, 6-8 ft is a national double, above 10 ft is huge.
- Gap is lip-to-landing-crest. 25-45 ft for a 250F-friendly double, 45-70 ft
  for a pro jump. The landing face is inside that distance, so the actual gap
  floor is shorter than the number suggests.
- The build prints an estimated clearing speed using the gap and the height
  difference to the landing. 25-45 mph is comfortable; above 60 mph is a
  big-bike pro jump. A step-up landing needs more speed than a downhill one.
- Landing length: 35-65 ft of descending surface after the crest. A short
  landing feels like casing even when the gap is right; a longer landing
  spreads the same drop over a gentler, less jagged slope.
- `landing_ratio` below 0.7 drops the landing well below the lip; above 1.0
  makes a step-up feel.
- The takeoff ramp ends at `takeoff_angle`, with a rounded base. The backside
  defaults to a 45 degree maximum and the landing face to 42 degrees; these are
  actual maxima, not average slopes. Use a 32-38 degree landing face for a
  softer transition into long landings. A tabletop uses a smooth ramp onto a
  flat top (15-25 ft is a safe rhythm piece).
- A tabletop with `gap` is rejected: use `gap: 0` for a tabletop and `table: 0`
  for a double.

Sequence rhythm sections with 25-60 ft between landings, not 15: the bike needs
room to settle.

## Whoops and rollers

- Whoops: 18-28 ft spacing, 1.5-3 ft tall, 4-8 bumps. Tighter spacing and
  taller bumps get sketchy fast.
- Rollers: 35-55 ft spacing, 2.5-4.5 ft tall, 2-4 bumps. These are jumpable or
  rollable and read as terrain, not braking bumps.
- `height_start_ratio` below 0.6 makes the first bump a ramp into the section.

## Berms

- Length should roughly match the corner arc. If the corner is 80 ft long, a
  70-90 ft berm is right; a 40 ft berm in a 100 ft corner only banks the middle.
  A long, gentle sweeper can take a 150-200 ft berm.
- Bank height 2-4 ft is normal; 4-5 ft is a pronounced national berm; 6+ ft
  is a wall.
- The bank is one-sided: flat across the inside 45%, then a concave rise that
  is steepest at the outer lip. It no longer digs a V through the infield, tilts
  the whole racing surface, or forms a rounded hump with a flat top.
- `side: auto` samples curvature across the whole berm. Check the build
  warnings; a berm that crosses a curvature reversal needs to be split, moved,
  or shortened.

## Ruts

- A rut is the alternative to a berm on a flat corner: 2.5-4 ft wide and
  0.2-0.4 ft deep is enough to read as a line without forming a bank.
- `offset` is measured from the centreline. Leave at least 1.5 ft between the
  rut edge and the track edge; the generator clamps and warns if it does not
  fit.
- Put the rut through the exit of the corner rather than the whole turn. On
  Cactus the five 90-110 ft ruts start late in their 180s and run to the exit.
- Cactus uses a 0.48 ft raw depth with 3.6 ft width; the eight smooth passes
  leave roughly 0.2 ft of finished depth. A 0.32 ft raw depth was too faint.
- A rut does not change the minimap or the gate layout; it only cuts the
  heightfield.

## Start

- Gate row width is `start_count * spacing` (20 x 4 = 80 ft). The start straight
  widens to `start_width`, defaulting to that plus 8 ft.
- `start_taper` of 150-250 ft blends into the track. Too short feels like a
  funnel; too long wastes the first corner.
- `start_flat` flattens the gate area. 60-120 ft is normal.

## Elevation and terrain

- For a deliberate profile, use `track.elevation` with `{at, height}` points.
  Put the same height at 0% and 100%, keep the range around 40-60 ft on a
  national, and aim for grades of roughly 3-6%.
- `elevation_smooth` of 60-100 ft keeps the crests and valley floors from
  becoming sharp ramps. It does not change the requested peak heights.
- `relief` above ~30 ft over a 2048 ft map starts to feel like hills, not a
  motocross track. 8-20 is normal.
- `hills` are useful for scenery and for supporting a high track section; keep
  the radius large (400+ ft) so the track cuts across a slope rather than a
  spike.
- `edge_falloff` of 20-35 ft suits a low track; use 120-180 ft when the
  elevation profile is 30 ft or more (Cactus uses 170). Below 8 ft the ribbon edge looks like a
  cliff.
- `terrain.smooth_iterations: 8` applies eight light 3x3 passes to the
  heightfield. It is useful at 0.625-1.25 ft/px when jump backs or berm
  shoulders still look stepped; nine or more passes start to round off the
  lip.
- `terrain.shoulder_smooth: 8` adds a wider, shoulder-only box blur measured
  in feet. It leaves the running surface and jump faces untouched, and is the
  right tool when return hooks put two wide falloffs close enough to form a
  stepped crease. Use 6-12 ft at 0.625 ft/px; do not raise
  `smooth_iterations` to compensate, because that also softens the track.
- Jumps are additive on top of the elevation profile; put them on relatively
  straight, gentle-grade sections so the takeoff and landing still read.

## Reading the build output

- `est_clear` is a projectile estimate to the landing crest, including the
  height difference between lip and landing. It ignores suspension, so treat
  ±15% as noise.
- "overlaps" warnings mean two obstacle height deltas stack; move one.
- "placed N of M" means prop rejection sampling ran out of room: lower `count`,
  raise `max_distance`, or lower `min_spacing`.
- A lap shorter than 400 ft is rejected as too small; 1,400-2,000 ft is SX,
  4,000-7,500 ft is a national. The bundled folded Cactus example is
  9,211 ft.
