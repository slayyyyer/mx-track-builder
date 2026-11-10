# Troubleshooting

## The game does not list the track

- The folder must be directly inside `%LOCALAPPDATA%\MX Simulator\`, not in a
  `tracks` subfolder.
- Folder name and `name:` in the description should match; the generator writes
  the folder itself, so use the built path.
- Launch with `mx.exe --track <FolderName>` to skip the menu and see errors in
  `lastlog.txt`.

## Ground is white or black

- Almost always the nested-folder problem above: the game finds the track but
  cannot resolve `@Track/...` media.
- If only the dirt looks wrong, check that `decals` references
  `@<Folder>/ground/ground.png` and that the file exists. A missing decal
  texture renders black.
- The generator writes a one-tile `tileinfo`, a zeroed `tilemap` and
  `ground/tile.png`. If the track is black after editing, check that this
  texture still exists and that every `addtile` block has a `texture` line.
- A file named `decals` cannot coexist with a folder named `decals` on Windows.
  This generator uses `ground/`.

## Statues or billboards are missing

- The `.jm`, texture and `.shp` paths must resolve. Missing models are skipped
  silently by the game.
- Paths normally start with `@<TrackFolder>/...`; a bare filename only works for
  assets in the game install.
- Check `lastlog.txt` for "Loading statues" and any missing-file lines.

## Statues float or sink

- `y` in the statues file is height above ground, not absolute elevation. The
  generator writes `y_offset` directly (0 = on the terrain), so a float usually
  means the heightfield changed after the props were written or a hand-edit
  broke the file.
- Rebuild after changing terrain; do not hand-edit statue lines.
- `y_offset: -2` sinks a prop slightly, useful for rocks.

## Hairpins pinch or overlap

- The centreline radius is too small for the track width. Keep it at least
  0.6 x `track.width`; the build warns when it drops below that.
- A common cause is a single last control point turning onto the start straight.
  Put two points on the start line and begin the turn earlier.
- Widen the corner by moving the apex outward or adding a short straight before
  it; do not patch the generated terrain.

## Track looks cut off at the edge

- Control points are too close to the terrain boundary. The ribbon plus
  `edge_falloff` is clipped at the edge.
- Keep points 100-150 ft inside; enlarge `terrain.dimension` or `resolution` for
  more room.

## Track edges are jagged or torn

- Rebuild with the current generator. An older ribbon picker let a station with
  zero coverage overwrite the height of the station the pixel was actually on,
  leaving adjacent-pixel cliffs along the shoulders. It now prefers coverage
  before along-track distance.
- `terrain.smooth_iterations` softens one-pixel grid steps; do not raise it to
  hide a multi-foot tear. `terrain.shoulder_smooth` relaxes broad overlapping
  falloffs, but an over-wide mask can leave its own crease at the edge.

## Jumps look like walls or steps

- Terrain resolution is too coarse for the feature. A 2 ft whoop at 2 ft/px is
  one pixel wide. Use `resolution: 1.0` or finer.
- A very high `takeoff_angle` with a short `height` still produces a steep
  face. Use 18-28 degrees for normal MX.
- `backside_angle` and `landing_face_angle` are maximum slopes now. If the back
  still reads as a wall, lower them (32-40 degrees is a smoother face) or use a
  finer `terrain.resolution`.
- A harsh landing can also be spread out: use a 35-65 ft `landing_length` and a
  32-38 degree `landing_face_angle`.
- At 1.25 ft/px or coarser, try `terrain.smooth_iterations: 2-8`; it removes
  the one-pixel stair steps without moving the whole jump.
- `gap` is lip-to-landing-crest. If it is too short for the backside and
  landing face, the build rejects it instead of making a pit; widen the gap or
  lower `landing_ratio`.
- The landing should be a downslope after a crest. If it reads as a wall, check
  that you did not put the jump on top of a steep `track.elevation` grade.

## Jumps look backwards

- The control-point order and the direction riders actually approach can be
  opposite. Add `reverse: true` to every `jump` and `tabletop` entry on that
  route. The obstacle stays at the same place, but its takeoff and landing swap
  ends.
- Rebuild after changing it; do not hand-edit the heightfield. Reversing only
  some jumps leaves the route inconsistent.
- If the gate row and checkpoints already work, fix the obstacles only; do not
  reverse the control points, because that also moves the obstacles and map.

## Berms look like rounded humps

- The bank profile is flat across the inside 45%, then concave to the outer
  lip. If an older build shows a smooth mound that flattens at the top, rebuild
  it; do not raise `terrain.smooth_iterations` to reshape it.
- A berm that looks too tall and narrow is carrying too much `height` for the
  track width. Lower the bank before changing the track width.

## Berm is on the wrong side

- `side: auto` samples curvature across the whole berm, not one point. On an
  S-turn, a long berm can cross a reversal; the build warns and you should
  shorten, move, or split it.
- A berm on a straight gets a warning too; move it into a corner or remove it.
- Check the preview: the dotted track line shows direction, and the hillshade
  shows the bank.

## Flat corners have no line

- A flat corner with no feature has no obvious exit. Add a `rut` through the
  exit instead of restoring a berm: 3-4 ft wide, 0.2-0.4 ft deep, and 5-7 ft
  from the centreline on the inside.
- If the rut disappears, the terrain resolution or smoothing is too coarse for
  its width. Keep `resolution` at 1.0 ft/px or finer, or widen the rut before
  increasing its depth.
- If the rut is on the wrong side, check `side`; `auto` follows the corner's
  curvature. A reversal warning means the rut is too long for that corner.

## Map looks mirrored or rotated

- `map.png` and `terrain.png` share the same orientation (image row = world z),
  so the minimap always matches the terrain. If a real-world blueprint feels
  mirrored, flip the control points' z values in the description and rebuild;
  never flip only one generated image.

## Start gates look sideways or backwards

- Start-gate yaw is the row angle negated, plus half a turn: `pi - atan2(nz,
  nx)`, normalized. The negation keeps a diagonal row straight; the half turn
  points the front of the directional gate models the right way. Using
  `-atan2` alone leaves them straight but backwards. A positive row angle
  leaves them sideways.
- The gate positions still run across the track; only their stored rotation is
  wrong. Rebuild rather than hand-editing `timing_gates`.

## Timing does not work

- `timing_gates` needs `startinggate:` lines, at least three `checkpoints:`,
  and `firstlap`/`normallap` index lists. `validate_track.py` checks all of
  these.
- Gate positions must be on the track. If you change `start_at`, rebuild.
- Checkpoint normals are the travel direction; a reversed spline flips them and
  timing can behave oddly. Rebuild rather than editing the file.

## Python problems

- Windows often has no `python` on PATH; use `py` instead.
- `ModuleNotFoundError: numpy/PIL/yaml` means dependencies are missing:
  `py -m pip install -r requirements.txt`.
- `PermissionError` when writing the track usually means the game has the folder
  open or the output path is inside a protected directory. Build to a normal
  project folder, then copy it.
- `terrain.png` must stay 16-bit. The generator uses its own encoder; do not
  re-save it with an image editor that drops to 8-bit.

## Rebuilding while the game is open

Close the track or restart the game after a rebuild. The game reads many of
these files once at load time; a running track will not pick up new terrain or
props. The editor's `s` key saves the editor state, it does not reload files
from disk.
