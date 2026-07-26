"""
photonic_wafer_mask.py
======================
Wafer-level assembly for the **photonic** chiplet. Tiles the gdsfactory-based
photonic chiplet across the wafer grid and reuses all of the standard
wafer-level infrastructure from ``wafer_mask`` (dicing lanes, multi-scale
alignment markers, stepped L-pads, wafer/lab labels, boundary circle).

Because the wafer assembly in ``wafer_mask`` is built with ``gdstk`` while the
photonic chiplet is built with ``gdsfactory``, a small adapter bridges the two:
the ``gf.Component`` is written to a temporary GDS, read back with ``gdstk``,
flattened (so per-chiplet sub-cell names never collide across placements), and
handed to the standard wafer builder as an ordinary ``gdstk.Cell``.

Usage:
    from src.assembly.photonic_wafer_mask import (
        PhotonicWaferConfig, build_photonic_wafer_mask,
    )
    import gdstk

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cfg = PhotonicWaferConfig()
    build_photonic_wafer_mask(lib, cfg, wafer_ID_str="PH-R01-W01")
    lib.write_gds("photonic_wafer.gds")
"""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import gdstk

from src.assembly import wafer_mask as wm
from src.chips.photonic_chiplet_mask import (
    PhotonicChipletConfig,
    build_photonic_chiplet_mask,
)
from src.config.run_registry import next_wafer


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class PhotonicWaferConfig(wm.WaferConfig):
    """Wafer config carrying a photonic chiplet instead of the standard one."""
    chiplet: PhotonicChipletConfig = field(default_factory=PhotonicChipletConfig)

    @classmethod
    def load(cls, path: Path) -> "PhotonicWaferConfig":
        import json
        with open(Path(path)) as f:
            d = json.load(f)
        d["chiplet"] = PhotonicChipletConfig(**d["chiplet"])
        return cls(**d)


# =============================================================================
# gdsfactory → gdstk ADAPTER
# =============================================================================

def _photonic_chiplet_builder(lib: gdstk.Library,
                              chip_cfg: PhotonicChipletConfig,
                              cell_name: str) -> gdstk.Cell:
    """
    Builds the gdsfactory photonic chiplet and returns it as a flattened
    ``gdstk.Cell`` added to *lib*, matching the ``chiplet_builder`` signature
    expected by ``wafer_mask.build_wafer_mask``.

    Flattening pulls every polygon into the single top cell, so no sub-cell
    names (rings, gratings, …) leak into *lib* to collide between placements.
    """
    # The photonic chiplet's helpers use fixed cell names (CORNER_MARKER_3x3,
    # BIG_PAD_SQUARE, …). gdsfactory/kfactory keeps a global layout registry, so
    # rebuilding the chiplet for the next placement would collide on those names.
    # Clearing the cache frees them before each build.
    import gdsfactory as gf
    gf.clear_cache()

    component = build_photonic_chiplet_mask(chip_cfg, cell_name=cell_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        gds_path = Path(tmpdir) / f"{cell_name}.gds"
        component.write_gds(gds_path)
        sub_lib = gdstk.read_gds(str(gds_path))

    # Find the chiplet's top cell (fall back to the first top-level cell).
    top = next((c for c in sub_lib.cells if c.name == cell_name), None)
    if top is None:
        top = sub_lib.top_level()[0]

    top.flatten()
    top.name = cell_name
    lib.add(top)
    return top


# =============================================================================
# PUBLIC API
# =============================================================================

def build_photonic_wafer_mask(lib: gdstk.Library,
                              cfg: PhotonicWaferConfig,
                              cell_name: str = "WAFER_PHOTONIC",
                              wafer_ID_str: str = "") -> gdstk.Cell:
    return wm.build_wafer_mask(
        lib, cfg,
        cell_name=cell_name,
        chiplet_builder=_photonic_chiplet_builder,
        chiplet_cell_prefix="CHIPLET_PH",
        wafer_ID_str=wafer_ID_str,
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse
    import gdsfactory as gf

    from src.config.paths import STANDARD_DIR

    parser = argparse.ArgumentParser(description="Build a photonic wafer mask.")
    parser.add_argument("--edit", action="store_true",
                        help="Edit mode — does not consume a run number.")
    args = parser.parse_args()

    gf.gpdk.PDK.activate()

    if args.edit:
        run_num, wafer_num = 99, 99
        stem = "PH-EDIT-MODE"
    else:
        run_num, wafer_num = next_wafer("PHOTONIC")
        stem = f"PH-R{run_num:02d}-W{wafer_num:02d}"

    wafer_cfg = PhotonicWaferConfig(
        run_number   = run_num,
        wafer_number = wafer_num,
        chiplet      = PhotonicChipletConfig(),
    )

    STANDARD_DIR.mkdir(parents=True, exist_ok=True)
    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_photonic_wafer_mask(lib, wafer_cfg, wafer_ID_str=stem)
    lib.write_gds(gds_path)
    wafer_cfg.save(cfg_path)

    print(f"Written: {gds_path}")
    print(f"Written: {cfg_path}")
    print(f"  Wafer diameter:  {wafer_cfg.wafer_diameter/1000:.0f} mm")
    print(f"  Run number:      {wafer_cfg.run_number}")
    print(f"  Wafer number:    {wafer_cfg.wafer_number:02d}")
    print(f"  Wafer ID:        {stem}")
    print(f"  Row config:      {wafer_cfg.row_config}  (bottom to top)")
    print(f"  Total chips:     {sum(wafer_cfg.row_config)}")
    print(f"  Chip size:       {wafer_cfg.chiplet.chip_width/1000:.1f} x "
          f"{wafer_cfg.chiplet.chip_height/1000:.1f} mm")
