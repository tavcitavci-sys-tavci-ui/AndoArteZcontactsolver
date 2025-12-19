# artezbuild_0.0.06

Linux-only experimental build focusing on **in-process** integration of the existing `ppf-contact-solver` GPU backend into Blender (no subprocess).

## Layout
- `blender_addon/` — Blender 4.2+ extension (thin UI + modal runner)
- `ppf_cts_backend/` — PyO3 Python extension module (wheel) that will wrap the PPF backend
 - `ppf-contact-solver/` — vendored upstream solver source (in-process CUDA backend)

## Status
- In-process solver stepping is wired and validated headlessly in Blender.
- The upstream solver source is vendored so the backend can be built from this single repo.

## Dev prerequisites
- Rust toolchain
- Python 3.11
- `maturin` (recommended): `pip install maturin`

## Build the wheel (dev)
From `ppf_cts_backend/`:
- `maturin develop` (installs into your current Python env)

## Blender
- The extension packaging step will come after the wheel is building reliably.
