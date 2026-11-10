# MX Track Builder

Build complete, game-readable MX Simulator tracks from one YAML or JSON layout.
A single closed spline drives the terrain, minimap, ground decal, statues,
billboards, timing gates and preview.

This repository is both a Claude Code plugin marketplace and a standalone Agent
Skill.

## Install in Claude Code

Add this repository as a marketplace once:

```text
/plugin marketplace add slayyyyer/track-creator
```

Then install the plugin:

```text
/plugin install mx-track-builder@track-creator
```

The equivalent shell commands are:

```bash
claude plugin marketplace add slayyyyer/track-creator
claude plugin install mx-track-builder@track-creator
```

Install the Python dependencies once:

```bash
python -m pip install numpy pillow PyYAML
```

On Windows, `py -m pip install numpy pillow PyYAML` works too. The plugin does
not install Python packages automatically.

Start a new Claude Code session, or run `/reload-plugins`, and ask it to build
or modify an MX Simulator track. Claude loads the plugin when the request
matches its skill.

## Install in other agents

The same folder is an Agent Skill. Install it with the Skills CLI:

```bash
npx skills add slayyyyer/track-creator/mx-track-builder
```

Choose your agent when prompted, then install the Python dependencies above.

## Install manually

```bash
git clone https://github.com/slayyyyer/track-creator.git
cd track-creator/mx-track-builder
python -m pip install -r requirements.txt
python scripts/selftest.py
```

The self-test builds every bundled example twice and validates the results.

The optional `scripts/reshape_shoulders.py` utility also needs SciPy:

```bash
python -m pip install scipy
```

## Build a track

```bash
python scripts/build_track.py assets/examples/cactus-ridge.yaml --out ./tracks
python scripts/validate_track.py ./tracks/Cactus_Ridge
```

The build writes the track folder plus a hillshade preview beside it. To use the
track, copy the generated folder directly into `%LOCALAPPDATA%\MX Simulator\`
(not into a subfolder) and launch:

```bash
mx.exe --track Cactus_Ridge
```

Tracks, decals and generated previews are intentionally not committed. The
description file is the source of truth; edit it and rebuild rather than
hand-editing generated terrain or maps.

## What is included

- `mx-track-builder/SKILL.md` - the agent instructions and workflow
- `mx-track-builder/assets/examples/` - complete example descriptions
- `mx-track-builder/scripts/` - deterministic build, validation and shoulder tools
- `mx-track-builder/references/` - format, field and tuning references
- `mx-track-builder/evals/` - skill evaluation cases

## Updating

Claude Code users can refresh the marketplace and reinstall:

```bash
claude plugin marketplace update track-creator
claude plugin install mx-track-builder@track-creator
```

## Requirements

- Python 3 with `pip`
- NumPy, Pillow and PyYAML
- MX Simulator only for riding the generated track

No in-game verification is claimed by the scripts. They validate file formats
and geometry, not bike physics or visual quality.
