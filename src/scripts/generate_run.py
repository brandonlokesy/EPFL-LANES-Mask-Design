"""
generate_run.py
===============
Interactive batch script for generating multiple wafers in one lithography run.

Prompts you for:
  - Mask type (standard | local gates)
  - Whether to start a new run or continue the current one
  - How many wafers to generate

Each wafer gets its own numbered GDS + JSON pair written to masks/standard/.

Usage:
    python src/scripts/generate_run.py
"""

import gdstk
from src.config.paths import STANDARD_DIR
from src.config.run_registry import next_wafer, new_run, _load
from src.chips.chiplet_mask import ChipletConfig
from src.chips.chiplet_local_gates_mask import LocalGatesChipletConfig
from src.assembly.wafer_mask import WaferConfig, build_wafer_mask
from src.assembly.wafer_local_gates_mask import LocalGatesWaferConfig, build_local_gates_wafer_mask


# =============================================================================
# HELPERS
# =============================================================================

def _prompt_choice(prompt: str, options: list[str]) -> str:
    """Prompts until the user enters one of the valid options."""
    opts_str = " / ".join(f"[{o}]" for o in options)
    while True:
        raw = input(f"{prompt} {opts_str}: ").strip().lower()
        if raw in options:
            return raw
        print(f"  Please enter one of: {', '.join(options)}")


def _prompt_int(prompt: str, min_val: int = 1, max_val: int = 99) -> int:
    """Prompts until the user enters an integer in [min_val, max_val]."""
    while True:
        raw = input(f"{prompt} ({min_val}–{max_val}): ").strip()
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"  Please enter a number between {min_val} and {max_val}.")
        except ValueError:
            print("  Please enter a whole number.")


def _current_run(mask_type: str) -> int:
    """Returns the current run number for a mask type (0 if none exists yet)."""
    data = _load()
    return data.get(mask_type, {}).get("run", 1)


# =============================================================================
# WAFER BUILDERS
# =============================================================================

def _build_standard_wafer(run_num: int, wafer_num: int) -> tuple[str, WaferConfig]:
    stem      = f"STD-R{run_num:02d}-W{wafer_num:02d}"
    wafer_cfg = WaferConfig(
        run_number   = run_num,
        wafer_number = wafer_num,
        chiplet      = ChipletConfig(grid_style="excel"),
    )
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_wafer_mask(lib, wafer_cfg, wafer_ID_str=stem)

    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"
    lib.write_gds(gds_path)
    wafer_cfg.save(cfg_path)
    return stem, wafer_cfg


def _build_local_gates_wafer(run_num: int, wafer_num: int) -> tuple[str, LocalGatesWaferConfig]:
    stem      = f"STD-R{run_num:02d}-W{wafer_num:02d}-LG"
    wafer_cfg = LocalGatesWaferConfig(
        run_number   = run_num,
        wafer_number = wafer_num,
        chiplet      = LocalGatesChipletConfig(grid_style="excel"),
    )
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_local_gates_wafer_mask(lib, wafer_cfg, wafer_ID_str=stem)

    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"
    lib.write_gds(gds_path)
    wafer_cfg.save(cfg_path)
    return stem, wafer_cfg


# =============================================================================
# MAIN
# =============================================================================

MASK_TYPES = {
    "std": ("STD", _build_standard_wafer),
    "lg":  ("STD", _build_local_gates_wafer),
}

def main():
    print()
    print("=" * 52)
    print("  Wafer Batch Generator")
    print("=" * 52)

    # ── Step 1: mask type ──────────────────────────────────────────────────────
    print()
    print("Mask type:")
    print("  std — Standard wafer")
    print("  lg  — Local gates wafer")
    mask_choice = _prompt_choice("Select mask type", ["std", "lg"])
    registry_key, builder = MASK_TYPES[mask_choice]

    # ── Step 2: run number ─────────────────────────────────────────────────────
    current = _current_run(registry_key)
    print()
    print(f"Current run for '{registry_key}': R{current:02d}")
    run_choice = _prompt_choice("Start a new run or continue current?", ["new", "continue"])

    if run_choice == "new":
        run_num = new_run(registry_key)
        print(f"  → New run started: R{run_num:02d}")
    else:
        run_num = current
        print(f"  → Continuing run: R{run_num:02d}")

    # ── Step 3: wafer count ────────────────────────────────────────────────────
    print()
    n_wafers = _prompt_int("How many wafers to generate?", min_val=1, max_val=99)

    # ── Step 4: confirm ────────────────────────────────────────────────────────
    suffix = "-LG" if mask_choice == "lg" else ""
    preview_start = _current_run(registry_key)  # wafers not yet incremented
    print()
    print("Summary:")
    print(f"  Mask type : {'Local Gates' if mask_choice == 'lg' else 'Standard'}")
    print(f"  Run       : R{run_num:02d}")
    print(f"  Wafers    : {n_wafers}")
    print(f"  Output    : {STANDARD_DIR}")
    print()
    confirm = _prompt_choice("Generate wafers?", ["yes", "no"])
    if confirm != "yes":
        print("Aborted.")
        return

    # ── Step 5: generate ───────────────────────────────────────────────────────
    STANDARD_DIR.mkdir(parents=True, exist_ok=True)
    print()

    generated = []
    for i in range(n_wafers):
        _, wafer_num = next_wafer(registry_key, run=run_num)
        print(f"  [{i+1}/{n_wafers}] Building wafer {wafer_num:02d}...", end=" ", flush=True)
        stem, cfg = builder(run_num, wafer_num)
        generated.append((stem, cfg))
        print(f"done  →  {stem}.gds")

    # ── Step 6: summary ────────────────────────────────────────────────────────
    print()
    print("=" * 52)
    print(f"  Done — {n_wafers} wafer(s) written to:")
    print(f"  {STANDARD_DIR}")
    print()
    print("  Files generated:")
    for stem, cfg in generated:
        chip_w = cfg.chiplet.chip_width  / 1000
        chip_h = cfg.chiplet.chip_height / 1000
        total  = sum(cfg.row_config)
        print(f"    {stem}.gds   "
              f"({total} chips, {chip_w:.1f}×{chip_h:.1f} mm)")
    print("=" * 52)
    print()


if __name__ == "__main__":
    main()