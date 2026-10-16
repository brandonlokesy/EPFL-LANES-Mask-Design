"""
inverse_tone.py

Inverse-tone exposure: expose the whole chip except the photonic pattern, so
the SiN is etched everywhere else. The exposure is split across output layers
so each can be written with its own beam current, set at EBPG job setup. Only
the area near waveguide sidewalls needs a low current: 144 mm^2 at
300 uC/cm^2 takes ~24 h at 5 nA and ~14 min at 500 nA.

Terms:
  protect   union of the layers named as keys of invert_layers (default
            wg_core, ring, grating, notes), grown by bias: film that survives.
  exclude   union of exclude_layers (default corner_markers, pad_markers,
            chiplet_id), grown by exclude_margin: film left for the MLA150
            step. Never exposed.
  collar    one layer's geometry grown by its collar_width (default 10 um),
            clipped to coarse_box. Contains the geometry itself.
  coarse    coarse_box - all collars - exclude, written to inv_coarse.

Each collar becomes `collar - protect - exclude` on its output_layer
(inv_t1..inv_t8). Collars are taken in dict order and each loses the area
earlier collars already took, so no point is exposed twice. The coarse layer
subtracts the collars themselves, not the exposed ribbons, so fine and coarse
layers share edges with no gap.

The edge between a fine and the coarse layer lies collar_width from the
sidewall. Backscattered electrons travel ~30 um, so with a 10 um collar the
sidewall dose also depends on the coarse layer's dose; proximity correction
accounts for that.

Measured on the 3x3 pulley chiplet with the defaults: inv_t1 0.106 mm^2,
inv_t2 0.017 mm^2, inv_coarse 140.209 mm^2, exclude 3.659 mm^2.

Geometry is klayout `kdb.Region` on the 1 nm database grid, so shared edges
coincide exactly.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import gdsfactory as gf
import klayout.db as kdb

from src.config.layers import LAYERS
from src.components.photonics.technology import _l

# (x0, y0, x1, y1) in um
Box = tuple[float, float, float, float]

# =============================================================================
# BOX HELPERS
# =============================================================================

def pad_bbox(bbox, margin: float = 0.0) -> Box:
    """A klayout DBox (from ``ref.dbbox()``) as a padded ``(x0, y0, x1, y1)``."""
    return (bbox.left - margin, bbox.bottom - margin,
            bbox.right + margin, bbox.top + margin)


def union_boxes(boxes: Sequence[Box]) -> Box:
    """Smallest box containing all of *boxes*."""
    x0, y0, x1, y1 = zip(*boxes)
    return (min(x0), min(y0), max(x1), max(y1))


def site_box(refs: Sequence, margin: float = 0.0) -> Box:
    """One padded box covering every reference in *refs* -- e.g. device + label."""
    return union_boxes([pad_bbox(r.dbbox(), margin) for r in refs])


# =============================================================================
# THE PRIMITIVE
# =============================================================================

def to_kdb_box(box: Box, dbu: float) -> kdb.Box:
    """A ``(x0, y0, x1, y1)`` in um as an integer-grid ``kdb.Box``."""
    x0, y0, x1, y1 = box
    u = lambda v: int(round(v / dbu))    # noqa: E731
    return kdb.Box(u(x0), u(y0), u(x1), u(y1))


def inverse_of(pattern: kdb.Region, box: Box, dbu: float) -> kdb.Region:
    """The negative of *pattern* within *box*: ``box - pattern``."""
    return kdb.Region(to_kdb_box(box, dbu)) - pattern

def add_inverted_layers(
        c: gf.Component,
        *,
        invert_layers: dict,
        exclude_layers: list,
        coarse_box: Box,
        bias: float = 0.0,
        exclude_margin: float = 0.0,
        max_vertices: int = 1024) -> dict:
    """
    Add inverse-tone exposure layers to c. Existing geometry is not changed.

    Parameters
    ----------
    c : gf.Component
        The chiplet. Its layers are read, and the output layers are added to it.
    invert_layers : dict
        {layer to keep: {"collar_width": um, "output_layer": LAYERS key}}, e.g.
        {"ring": {"collar_width": 10.0, "output_layer": "inv_t1"}}.
        collar_width must be larger than bias. output_layer must be one of
        inv_t1..inv_t8; several keys may share one. Where collars overlap, the
        key listed first keeps the overlap.
    exclude_layers : list of str
        LAYERS keys whose area is never exposed, e.g. ["pad_markers"].
    coarse_box : tuple of float
        (x0, y0, x1, y1) in um: the chip or the active area. Nothing outside it
        is exposed.
    bias : float, default 0.0
        um protect is grown by, to compensate a known process bias. Positive
        widens the surviving lines.
    exclude_margin : float, default 0.0
        um the excluded areas are grown by.
    max_vertices : int, default 1024
        Output polygons are split to at most this many points (GDSII limit).

    Raises
    ------
    ValueError
        If a layer name is not in LAYERS, an output_layer is not inv_t1..inv_t8,
        or a collar_width is not larger than bias.

    Returns
    -------
    summary : dict
        "protect_area_um2" : float, um^2 of protect after bias (film that survives).
        "exclude_area_um2" : float, um^2 of exclude after exclude_margin.
        "layers" : list of dict, one per output layer, in the order written:
            "layer"      : str, LAYERS key, e.g. "inv_t1".
            "area_um2"   : float, exposed area, measured before break_polygons.
            "n_polygons" : int, polygon count after break_polygons.
            "max_points" : int, most points in one polygon; <= max_vertices.

    """

    validate_layers(invert_layers) # Check that every name in invert_layers is a valid layer in LAYERS
    validate_layers([settings["output_layer"] for settings in invert_layers.values()]) # Check that every output layer in invert_layers is a valid layer in LAYERS
    validate_layers(exclude_layers) # Check that every name in exclude_layers is a valid layer in LAYERS

    # Conversion factor from um to database units
    dbu = c.kcl.dbu
    u = lambda v: int(round(v / dbu))
    um2 = dbu * dbu

    summary = {"layers" : []}
    # -- geometry that must survive ------------------------------------------
    protect = kdb.Region()
    for layer in invert_layers.keys():
        protect += c.get_region(_l(layer))
    protect.merge()
    if bias:
        protect.size(u(bias)) # modifies protect
        protect.merge()

    summary["protect_area_um2"] = protect.area() * um2
    # -- layers that are to be neglected ------------------------------------------
    exclude = kdb.Region()
    for layer in exclude_layers:
        exclude += c.get_region(_l(layer))
    if not exclude.is_empty():
        if exclude_margin:
            exclude.size(u(exclude_margin)) 
        exclude.merge()
    summary["exclude_area_um2"] = exclude.area() * um2

    # -- Create the inverse tone regions for each layer in invert_layers ------------------------------------------
    outer = kdb.Region(to_kdb_box(coarse_box, dbu))
    outputs = defaultdict(kdb.Region)
    all_frames = kdb.Region()
    for (layer_name, settings) in invert_layers.items():
        out_name = settings["output_layer"]
        if not out_name.startswith("inv_t"):
            raise ValueError(
                f"{layer_name!r}: output_layer {out_name!r} must be one of "
                f"inv_t1..inv_t8. inv_coarse is written by this function."
            )
        if settings["collar_width"] <= max(bias, 0.0):
            raise ValueError(
                f"{layer_name!r}: collar_width {settings['collar_width']} um must "
                f"be larger than bias {bias} um, or protect extends past its "
                f"collar and the coarse tier exposes the waveguide edge."
            )
        pattern = c.get_region(_l(layer_name))
        frame = pattern.sized(u(settings["collar_width"])) # does not modify pattern -> assigns to frame
        frame = frame & outer # keep only the part inside coarse_box
        frame = frame - all_frames # excludes any region already being used
        all_frames += frame
        expose = frame - protect - exclude # the collar minus the (pattern + bias) minus the exclude regions (if any)
        outputs[out_name] += expose

    outputs["inv_coarse"] = outer - all_frames - exclude

    for out_name, out in outputs.items():
        out.merge() # merge any overlapping polygons
        area_um2 = out.area() * um2
        out.break_polygons(max_vertices,0) # GDSII can store at most 1024 points per polygon. This cuts polygons over 1024 points into smaller ones
        summary["layers"].append({
            "layer": out_name,
            "area_um2": area_um2,
            "n_polygons": out.count(),
            "max_points": max((p.num_points() for p in out.each()), default=0),
        })
        c.shapes(gf.get_layer(_l(out_name))).insert(out)
    return summary

def validate_layers(layers: dict | list):
    """
    Check that every name in layers (a list, or a dict's keys) is a LAYERS key.

    Raises
    ------
    ValueError
        If a layer name or output layer is not in src/config/layers.py
    """
    for layer_name in layers:
        if layer_name not in LAYERS:
            raise ValueError(
                f"layer {layer_name!r} is not in src/config/layers.py. Only the following are valid: {sorted(LAYERS.keys())}"
            )