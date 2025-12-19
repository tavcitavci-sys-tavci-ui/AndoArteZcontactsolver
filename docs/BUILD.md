# Build (Linux-only)

## Backend wheel (PyO3)

This repo vendors the upstream solver source in `ppf-contact-solver/`, so building the backend is self-contained.

Notes:
- Blender 4.x uses Python 3.11, so build with `-i python3.11`.
- `maturin` uses `patchelf` when producing manylinux wheels. If you installed it via pip (`pip install patchelf`), ensure `~/.local/bin` is on your `PATH`.

From `ppf_cts_backend/`:
- `python3.11 -m pip install -U maturin`
- `PATH="$HOME/.local/bin:$PATH" maturin develop -i python3.11`

This installs `ppf_cts_backend` into your current Python environment.

## Blender extension

This project is scaffolded as a Blender 4.2+ extension in `blender_addon/`.
Packaging + wheel bundling will be added after the backend is wired to the real PPF CUDA backend.
