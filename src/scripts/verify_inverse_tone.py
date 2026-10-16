"""
verify_inverse_tone.py
======================
Reads a GDS built with ``--invert`` back with klayout and checks the inverse-tone
layers, independently of the code that wrote them::

    python -m src.scripts.verify_inverse_tone masks/experimental/photonic_chiplet_EDIT.gds

Terms:
  tier      the exposure on one output layer: inv_t1..inv_t8 or inv_coarse.
  protect   union of wg_core, ring, grating, notes: film that must survive.
  exclude   corner_markers, pad_markers, chiplet_id, grown by 20 um: film
            left for the MLA150 step.
  extent    bounding box of all tiers together.

Checks, per cell that holds tiers (one for a chiplet, one per die on a wafer):
  1. No two tiers overlap, for every pair. Overlap is double exposure.
  2. extent - tiers - protect - exclude is empty. A remainder is film that
     should have been etched.
  3. No tier overlaps protect. Overlap etches a waveguide.
  4. No polygon has more than 1024 points, the GDSII limit (one 8 KB record).

Residuals that are not zero: the output polygons are split to stay under 1024
points, and the split snaps vertices to the 1 nm grid, while the rings are drawn
with 15 nm segments (pulley_n_segments = 2048). A residual passes as grid noise
when eroding it by noise_floor_nm / 2 (default 2.5 nm) leaves nothing, i.e. it
has no part wider than noise_floor_nm. Anything wider fails.
"""

from __future__ import annotations

import argparse
import itertools
import sys

import klayout.db as kdb

from src.config.layers import LAYERS

# GDSII allows 8 KB per XY record, 8 bytes per point.
GDSII_MAX_POINTS = 1024

# A residual is grid-snap noise only if nothing in it survives erosion by half.
NOISE_FLOOR_NM = 5.0

# Every layer a tier can land on, coarse last.
TIER_KEYS = [f"inv_t{n}" for n in range(1, 9)] + ["inv_coarse"]


def _shapes(layout: kdb.Layout, cell: kdb.Cell, key: str) -> kdb.Region:
    """Raw shapes on a layer, hierarchy resolved, NOT merged."""
    spec = LAYERS[key]
    index = layout.find_layer(spec["layer"], spec["datatype"])
    if index is None:
        return kdb.Region()
    return kdb.Region(cell.begin_shapes_rec(index))


def _region(layout: kdb.Layout, cell: kdb.Cell, key: str) -> kdb.Region:
    region = _shapes(layout, cell, key)
    region.merge()
    return region


def _max_thickness_nm(region: kdb.Region, dbu: float) -> float:
    """
    Thickness of the fattest polygon in *region*, in nm.

    Uses 2 x area / perimeter, which is the width of a long thin sliver. The
    bbox is the wrong measure here: a 500 nm long, 1 nm thick seam artifact has
    a 500 nm bbox but is 1 nm of geometry.
    """
    worst = 0.0
    for poly in region.each():
        perimeter = poly.perimeter()
        if perimeter:
            worst = max(worst, 2.0 * poly.area() / perimeter)
    return worst * dbu * 1000.0


def _is_grid_noise(region: kdb.Region, dbu: float, floor_nm: float) -> bool:
    """
    True if nothing in *region* survives eroding by half the noise floor.

    Erosion is the decisive test rather than any single measured dimension: it
    asks directly whether the residual contains a feature of real width.
    """
    probe = region.dup()
    probe.size(-max(1, int(round(floor_nm / 2.0 / 1000.0 / dbu))))
    probe.merge()
    return probe.is_empty()


def verify_cell(layout: kdb.Layout,
                cell: kdb.Cell,
                verbose: bool = True,
           protect_keys=("wg_core", "ring", "grating", "notes"),
           exclude_keys=("corner_markers", "pad_markers", "chiplet_id"),
           exclude_margin: float = 20.0,
           noise_floor_nm: float = NOISE_FLOOR_NM) -> bool:
    dbu = layout.dbu

    def mm2(region: kdb.Region) -> float:
        return region.area() * dbu * dbu / 1e6

    raw = {key: _shapes(layout, cell, key) for key in TIER_KEYS}
    raw = {key: region for key, region in raw.items() if not region.is_empty()}
    if not raw:
        return False

    tiers = {}
    for key, region in raw.items():
        merged = region.dup()
        merged.merge()
        tiers[key] = merged

    protect = kdb.Region()
    for key in protect_keys:
        protect += _region(layout, cell, key)
    protect.merge()

    exclude = kdb.Region()
    for key in exclude_keys:
        exclude += _region(layout, cell, key)
    if not exclude.is_empty():
        exclude.size(int(round(exclude_margin / dbu)))
        exclude.merge()

    everything = kdb.Region()
    for region in tiers.values():
        everything += region
    everything.merge()
    extent = kdb.Region(everything.bbox())

    checks = []

    # 1. pairwise, so a 3-tier mistake cannot hide behind a 2-tier check
    for a, b in itertools.combinations(sorted(tiers), 2):
        checks.append((f"{a} and {b} never overlap", tiers[a] & tiers[b]))

    # 2. the tiers plus what survives must tile the extent
    gap = extent.dup()
    for region in tiers.values():
        gap -= region
    checks.append(("no unexposed gap in the extent", gap - protect - exclude))

    # 3. no tier may touch the protected pattern
    for key in sorted(tiers):
        checks.append((f"{key} never touches the protected pattern",
                       tiers[key] & protect))

    out = []
    ok = True
    for name, residual in checks:
        if residual.is_empty():
            verdict, thick = "PASS", 0.0
        else:
            thick = _max_thickness_nm(residual, dbu)
            if _is_grid_noise(residual, dbu, noise_floor_nm):
                verdict = "pass (grid)"
            else:
                verdict, ok = "FAIL", False
        out.append(f"  {name:<46}{mm2(residual):9.6f} mm2 {thick:6.2f} nm  {verdict}")

    # Vertex counts must be read from the raw shapes: merging the fractured
    # pieces back together would report the pre-fracture count and hide the
    # very thing being checked.
    worst = max((p.num_points() for region in raw.values() for p in region.each()),
                default=0)
    passed = worst <= GDSII_MAX_POINTS
    ok &= passed
    out.append(f"  {'polygon vertices within GDSII record limit':<46}"
               f"{worst:9d} pts{'':10s}{'PASS' if passed else 'FAIL'}")

    out.append("  " + "-" * 80)
    total = 0.0
    for key in TIER_KEYS:
        if key not in tiers:
            continue
        total += mm2(tiers[key])
        out.append(f"  {key:<12}({LAYERS[key]['layer']:3d}) {mm2(tiers[key]):9.3f} mm2 "
                   f"in {raw[key].count():6d} polygons")
    out.append(f"  surviving          {mm2(protect):9.3f} mm2 protected, "
               f"{mm2(exclude):9.3f} mm2 excluded")
    out.append(f"  total              "
               f"{total + mm2(protect) + mm2(exclude):9.3f} mm2 "
               f"(extent {mm2(extent):.3f} mm2)")

    if verbose or not ok:
        print(f"  cell {cell.name} - {len(tiers)} tiers")
        print(f"  {'check':<46}{'residual':>12} {'thickest':>9}  result")
        print("  " + "-" * 80)
        print("\n".join(out))
        print()
    return ok


def verify(gds_path: str, noise_floor_nm: float = NOISE_FLOOR_NM) -> bool:
    """
    Verify every cell in *gds_path* that owns inverse-tone geometry.

    A standalone chiplet has one such cell; a wafer has one per die. Checking
    them individually is what makes the tiling check meaningful -- across a whole
    wafer the gaps between dies would read as unexposed area.
    """
    layout = kdb.Layout()
    layout.read(gds_path)

    indexes = [layout.find_layer(LAYERS[k]["layer"], LAYERS[k]["datatype"])
               for k in TIER_KEYS]
    indexes = [i for i in indexes if i is not None]
    cells = [c for c in layout.each_cell()
             if any(not c.shapes(i).is_empty() for i in indexes)]

    print(f"{gds_path}")
    if not cells:
        print("  no inverse-tone geometry found - built without --invert?\n")
        return False

    verbose = len(cells) == 1
    results = {c.name: verify_cell(layout, c, verbose=verbose,
                                   noise_floor_nm=noise_floor_nm)
               for c in cells}
    failed = [name for name, ok in results.items() if not ok]

    if not verbose:
        print(f"  {len(cells)} cells with inverse-tone geometry, "
              f"{len(cells) - len(failed)} pass, {len(failed)} fail")
        if failed:
            print(f"  failing: {', '.join(failed[:8])}"
                  f"{' ...' if len(failed) > 8 else ''}")
    print("  ALL CHECKS PASS" if not failed else "  SOME CHECKS FAILED")
    print()
    return not failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify inverse-tone tier geometry in a written GDS.")
    parser.add_argument("gds", nargs="+", help="GDS file(s) built with --invert")
    parser.add_argument("--noise-floor-nm", type=float, default=NOISE_FLOOR_NM,
                        help="Residuals with no feature wider than this count as "
                             f"grid-snap noise (default {NOISE_FLOOR_NM:g} nm).")
    args = parser.parse_args()
    results = [verify(path, noise_floor_nm=args.noise_floor_nm) for path in args.gds]
    sys.exit(0 if all(results) else 1)
