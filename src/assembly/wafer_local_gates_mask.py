import gdstk
from src.chips.chiplet_local_gates_mask import LocalGatesChipletConfig, build_local_gates_mask
from src.assembly import wafer_mask as wm
from src.config.layers import LAYERS
from src.config.run_registry import next_wafer, new_run
from dataclasses import dataclass, asdict, field
from pathlib import Path
import numpy as np

@dataclass
class LocalGatesWaferConfig(wm.WaferConfig):
    chiplet: LocalGatesChipletConfig = field(default_factory = LocalGatesChipletConfig)

def build_local_gates_wafer_mask(lib: gdstk.Library,
                                  cfg: LocalGatesWaferConfig,
                                  cell_name: str = "WAFER_LOCAL_GATES",
                                  wafer_ID_str: str = "") -> gdstk.Cell:
    return wm.build_wafer_mask(
        lib, cfg,
        cell_name=cell_name,
        chiplet_builder=build_local_gates_mask,
        chiplet_cell_prefix="CHIPLET_LG",
        wafer_ID_str=wafer_ID_str
    )

if __name__ == "__main__":
    EDIT_MODE = True

    from src.config.paths import STANDARD_DIR, EXPERIMENTAL_DIR
    OUTPUT_DIR = STANDARD_DIR  # or EXPERIMENTAL_DIR for one-offs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not EDIT_MODE:
        run_num, wafer_num = next_wafer("STD")
        stem = f"STD-R{run_num:02d}-W{wafer_num:02d}-LG"
    else:
        run_num, wafer_num = 99,99
        stem = f"STD-LG-EDIT-MODE"

    wafer_cfg = LocalGatesWaferConfig(
        run_number   = run_num,
        wafer_number = wafer_num,
        chiplet      = LocalGatesChipletConfig(grid_style="excel"),
    )

    gds_path = OUTPUT_DIR / f"{stem}.gds"
    cfg_path = OUTPUT_DIR / f"{stem}.json"
    

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_local_gates_wafer_mask(lib, wafer_cfg, wafer_ID_str=stem)
    lib.write_gds(gds_path)
    wafer_cfg.save(cfg_path)

    print(f"Written: {gds_path}")
    print(f"Written: {cfg_path}")
    print(f"  Wafer diameter:  {wafer_cfg.wafer_diameter/1000:.0f} mm")
    print(f"  Wafer Run Number:{wafer_cfg.run_number}")
    print(f"  Wafer number:    {wafer_cfg.wafer_number:02d}")
    print(f"  Wafer IDL        {stem}")
    print(f"  Row config:      {wafer_cfg.row_config}  (bottom to top)")
    print(f"  Total chips:     {sum(wafer_cfg.row_config)}")
    print(f"  Chip size:       {wafer_cfg.chiplet.chip_width/1000:.1f} x "
          f"{wafer_cfg.chiplet.chip_height/1000:.1f} mm")
    print(f"  Grid style:      {wafer_cfg.chiplet.grid_style}")