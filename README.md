# Automating the Creation of Graduated Number Cartograms in ArcGIS Pro

This repository contains materials related to a master's thesis focused on automating the creation of graduated number cartograms in ArcGIS Pro.

The repository is organized around three main parts:
- a publishable ArcGIS Pro toolbox in `.atbx` format
- standalone source scripts developed in VS Code
- example outputs, screenshots, and sample data

## Important Note on Architecture

The `.atbx` file is an embedded ArcGIS Pro toolbox, meaning the production logic may be stored internally inside the toolbox. The `Execution.py` and `Validation.py` files in this repository are **not** a direct export of the toolbox internals — they are independently versioned source files developed and documented in Visual Studio Code.

For this reason, the repository distinguishes between:
- `toolbox/` — the publishable `.atbx` toolbox file
- `src/` — standalone source scripts and their development history

## Repository Structure

- `toolbox/` — the `.atbx` file and a short description of its contents
- `src/` — standalone Python scripts `Execution.py` and `Validation.py`
- `docs/` — thesis summary, upload guide, and repository structure explanation
- `examples/` — example maps, screenshots, and other outputs
- `sample-data/` — small demonstration data for trying out the tool

## What to Add Before Publishing

1. Place the final `.atbx` file into `toolbox/`.
2. Copy `Execution.py` and `Validation.py` into `src/`.
3. Add screenshots of finished maps to `examples/screenshots/`.
4. Add PDF or image map exports to `examples/maps/`.
5. Add small, publicly shareable data to `sample-data/`.
6. Fill in the thesis annotation in `docs/thesis-summary.md`.

## How to Use This Repository

1. Open ArcGIS Pro.
2. Load the `.atbx` toolbox from the `toolbox/` folder.
3. If needed, compare or adjust the logic using the separately documented scripts in `src/`.
4. Browse the examples in the `examples/` folder.
5. Use the small dataset in `sample-data/` for testing.

## Repository Status

This folder was prepared as a publication scaffold for GitHub. Some files are intentionally placeholder templates and should be filled in before the first public release.