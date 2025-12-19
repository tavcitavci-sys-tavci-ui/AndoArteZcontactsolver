#!/usr/bin/env bash
set -euo pipefail

# Clean uninstall old ArteZ/PPF-related Blender extensions and install the current repo's extension.
#
# This script is intentionally conservative: it only removes known extension IDs
# (andosim_artez, artezbuild_ppf) plus the backend extraction cache used by this addon.
# It does NOT delete unrelated Blender addons.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_EXT_DIR="$REPO_ROOT/blender_addon"
MANIFEST="$SRC_EXT_DIR/blender_manifest.toml"

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: Missing $MANIFEST" >&2
  exit 1
fi

# Extract id from blender_manifest.toml (expects: id = "..." on its own line)
EXT_ID="$(grep -E '^id\s*=\s*"' "$MANIFEST" | head -n 1 | sed -E 's/^id\s*=\s*"([^"]+)".*/\1/')"
if [[ -z "$EXT_ID" ]]; then
  echo "ERROR: Could not parse extension id from $MANIFEST" >&2
  exit 1
fi

# Choose Blender config version dir.
# Prefer BLENDER_VERSION if set; otherwise pick the newest version-like folder.
if [[ -n "${BLENDER_VERSION:-}" ]]; then
  CFG_DIR="$HOME/.config/blender/$BLENDER_VERSION"
else
  CFG_DIR="$(ls -1d "$HOME/.config/blender/"* 2>/dev/null | sort -V | tail -n 1 || true)"
fi

if [[ -z "$CFG_DIR" || ! -d "$CFG_DIR" ]]; then
  echo "ERROR: Blender config dir not found under $HOME/.config/blender" >&2
  echo "Set BLENDER_VERSION (e.g. BLENDER_VERSION=4.5) and re-run." >&2
  exit 1
fi

USER_DEFAULT_EXT="$CFG_DIR/extensions/user_default"
mkdir -p "$USER_DEFAULT_EXT"

OLD_IDS=("andosim_artez" "$EXT_ID")

echo "Using Blender config: $CFG_DIR"
echo "Installing extension id: $EXT_ID"

echo "\n== Uninstall old extensions =="
for id in "${OLD_IDS[@]}"; do
  if [[ -d "$USER_DEFAULT_EXT/$id" ]]; then
    echo "Removing $USER_DEFAULT_EXT/$id"
    rm -rf "$USER_DEFAULT_EXT/$id"
  else
    echo "Not present: $USER_DEFAULT_EXT/$id"
  fi
done

echo "\n== Clear addon backend cache =="
# Wheel extraction cache used by blender_addon/backend_loader.py
if [[ -d "$HOME/.cache/artezbuild_ppf" ]]; then
  echo "Removing $HOME/.cache/artezbuild_ppf"
  rm -rf "$HOME/.cache/artezbuild_ppf"
else
  echo "Not present: $HOME/.cache/artezbuild_ppf"
fi

# Optional: Blender extension cache (safe; Blender rebuilds)
if [[ -d "$CFG_DIR/extensions/.cache" ]]; then
  echo "(Optional) Removing $CFG_DIR/extensions/.cache"
  rm -rf "$CFG_DIR/extensions/.cache"
fi

echo "\n== Install current extension =="
DEST="$USER_DEFAULT_EXT/$EXT_ID"
mkdir -p "$DEST"

# Copy extension files (avoid copying __pycache__)
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$SRC_EXT_DIR/" \
  "$DEST/"

echo "Installed to: $DEST"

echo "\n== Next steps =="
echo "1) Start Blender."
echo "2) Preferences -> Add-ons: enable 'Artezbuild PPF (In-Process)'."
echo "3) In the 3D Viewport sidebar, open the 'Artezbuild' tab and click 'Run PPF (In-Process)'."

echo "\nTip: If you want to enable it automatically from CLI:"
echo "  blender -b --python-expr \"import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.${EXT_ID}'); bpy.ops.wm.save_userpref(); print('enabled bl_ext.user_default.${EXT_ID}')\""
