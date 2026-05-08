"""
paths.py
========
Single source of truth for all project-level paths.

Import this everywhere instead of repeating Path(__file__).parent chains.
"""

from pathlib import Path

# Project root — the directory that contains src/, masks/, assets/
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Assets
ASSETS_DIR      = PROJECT_ROOT / "assets"
FONTS_DIR       = ASSETS_DIR  / "fonts"
DEPLOF_FONT_GDS = FONTS_DIR   / "DEPLOF.gds"

# Mask outputs
MASKS_DIR        = PROJECT_ROOT / "masks"
STANDARD_DIR     = MASKS_DIR   / "standard"
EXPERIMENTAL_DIR = MASKS_DIR   / "experimental"

# Run registry
REGISTRY_PATH = MASKS_DIR / ".registry.json"