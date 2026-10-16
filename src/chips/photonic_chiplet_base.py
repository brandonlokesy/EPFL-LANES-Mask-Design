"""
photonic_chiplet_base.py

Shared frame for every gdsfactory photonic chiplet: chip boundary, corner
markers, pads, chiplet ID, the inverse-tone pass and the command-line entry
point. A concrete chiplet supplies only its device payload:

    @dataclass
    class MyChipletConfig(PhotonicChipletBaseConfig):
        my_param: float = 1.0          # device fields only

    def build_my_chiplet(cfg, cell_name=None):
        c = build_chip_frame(cfg, cell_name or f"MY_CHIPLET_{cfg.chiplet_number:03d}")
        ...                            # place devices + labels
        return finish_chip(c, cfg)

    if __name__ == "__main__":
        run_cli(MyChipletConfig, build_my_chiplet, stem="my_chiplet")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

import gdstk
import gdsfactory as gf

from src.config.layers import LAYERS
from src.config.paths import EXPERIMENTAL_DIR
from src.chips.layout_geometry import (
    corner_marker_positions,
    big_pad_square_positions,
    big_pad_L_origin,
    rectangular_pad_positions,
)
from src.utils.text import draw_chiplet_number
from src.components.photonics.technology import _l
from src.components.photonics.inverse_tone import (
    add_inverted_layers
)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class PhotonicChipletBaseConfig:
    """
    Infrastructure parameters shared by every photonic chiplet. Subclass it and
    add only device fields.

    Infrastructure fields mirror ``ChipletConfig`` exactly so the shared
    helper functions (add_corner_markers, etc.) work without modification.
    """

    # ── Chip dimensions ────────────────────────────────────────────────────
    chip_width:   float = 12000.0
    chip_height:  float = 12000.0

    # ── Corner markers (mirrors ChipletConfig) ─────────────────────────────
    corner_marker_style:  str   = "3x3"
    marker_x_size:        float = 50.0
    marker_x_width:       float = 10.0
    corner_sq_size:       float = 20.0
    corner_sq_gap:        float = 180.0
    corner_margin:        float = 1000.0

    # ── Big pad markers (mirrors ChipletConfig) ────────────────────────────
    pad_sq_size:          float = 500.0
    pad_sq_margin:        float = 1750.0
    pad_L_margin:         float = 2000.0
    pad_L_length:         float = 1000.0

    # ── Rectangular pad bars (mirrors ChipletConfig) ───────────────────────
    rec_pad_length:       float = 100.0
    rec_pad_width:        float = 40.0
    rec_pad_margin_from_big_pad: float = 450.0
    rec_pad_gap:          float = 400.0

    # ── Chiplet ID number (mirrors ChipletConfig) ──────────────────────────
    chiplet_number:           int   = 0
    chiplet_id_text_size:     float = 1400.0
    chiplet_id_stroke_ratio:  float = 0.12
    chiplet_id_char_w_ratio:  float = 0.6
    chiplet_id_gap_ratio:     float = 0.15
    chiplet_id_chamfer_ratio: float = 0.35
    chiplet_id_centre_y:      float = 1250.0

    # ── Annotation ─────────────────────────────────────────────────────────
    draw_boundary:  bool = True
    draw_active_area: bool = True

    # ── Process / cross-section ────────────────────────────────────────────
    cross_section:  str   = "SIN_VIS"   # key into technology.CROSS_SECTIONS

    # ── Inverse-tone (negative) exposure ──────────────────────────────────
    # Etch everything except the layers in invert_layers, split across output
    # layers so each can get its own beam current at EBPG job setup. See
    # inverse_tone.py.
    invert_tone:            bool  = False
    invert_coarse_extent:   str   = "chip"       # "chip" | "active_area"
    invert_bias:            float = 0.0          # µm — dilate surviving geometry
    # Key: layer whose geometry survives. collar_width: µm the exposed ribbon
    # extends past that layer's edges, must exceed invert_bias. output_layer:
    # LAYERS key the ribbon is written to, one of inv_t1..inv_t8. Dict order is
    # precedence: where collars overlap, the earlier key keeps the overlap.
    invert_layers: dict = field(default_factory=lambda: {
        "ring":    {"collar_width": 1.0, "output_layer": "inv_t1"},
        "wg_core": {"collar_width": 1.0, "output_layer": "inv_t1"},
        "grating": {"collar_width": 1.0, "output_layer": "inv_t1"},
        "notes":   {"collar_width": 2.0, "output_layer": "inv_t2"},
        "sample_id" : {"collar_width" : 100.0, "output_layer" : "inv_t3"}
    })
    # MLA150 features, patterned in a later step: film is left under them.
    invert_exclude_layers:  list  = field(default_factory=lambda: [
        "corner_markers", "pad_markers", "chiplet_id",
    ])
    invert_exclude_margin:  float = 20.0         # µm around excluded footprints
    # GDSII stores at most 1024 points per polygon (one 8 KB record); larger
    # output polygons are split.
    invert_max_vertices:    int   = 1024

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path):
        with open(Path(path)) as f:
            return cls(**json.load(f))


# =============================================================================
# FRAME COMPONENTS  (gdsfactory)
# =============================================================================

def make_corner_marker(sq_size: float, sq_gap: float, array: str = "3x3") -> gf.Component:
    c = gf.Component(f"CORNER_MARKER_{array}")
    half = sq_size / 2 + sq_gap / 2
    positions = {
        "2x2": [(-half, -half), ( half, -half), (-half,  half), ( half,  half)],
        "2x1x2": [(-half, -half), ( half, -half), (0, 0), (-half, half), ( half,  half)],
        "3x3": [
            (-2*half, -2*half), (0, -2*half), (2*half, -2*half),
            (-2*half,       0), (0,       0), (2*half,       0),
            (-2*half,  2*half), (0,  2*half), (2*half,  2*half),
        ],
    }
    if array not in positions:
        raise ValueError(f"Unknown array style '{array}'. Choose from: {list(positions)}")
    sq = sq_size / 2
    layer = _l("corner_markers")
    for ox, oy in positions[array]:
        c.add_polygon([(ox-sq, oy-sq), (ox+sq, oy-sq), (ox+sq, oy+sq), (ox-sq, oy+sq)], layer=layer)
    return c


def add_corner_markers(c: gf.Component, cfg: PhotonicChipletBaseConfig) -> None:
    marker = make_corner_marker(cfg.corner_sq_size, cfg.corner_sq_gap, cfg.corner_marker_style)
    for cx, cy in corner_marker_positions(cfg.chip_width, cfg.chip_height, cfg.corner_margin):
        c.add_ref(marker).move((cx, cy))


def make_big_pad_square(size: float) -> gf.Component:
    c = gf.Component("BIG_PAD_SQUARE")
    h = size / 2
    c.add_polygon([(-h, -h), (h, -h), (h, h), (-h, h)], layer=_l("pad_markers"))
    return c


def make_big_pad_L(pad_size: float, arm_length: float) -> gf.Component:
    """L-shaped pad with inner corner at (0, 0), arms extending in +x and +y."""
    c = gf.Component("BIG_PAD_L")
    T, L = pad_size, arm_length
    c.add_polygon([(0,0),(L,0),(L,T),(T,T),(T,L),(0,L)], layer=_l("pad_markers"))
    return c


def make_rectangular_pad(length: float, width: float, orientation: str) -> gf.Component:
    c = gf.Component(f"RECTANGULAR_PAD_{orientation.upper()}")
    if orientation == "horizontal":
        c.add_polygon([(-length/2,-width/2),(length/2,-width/2),(length/2,width/2),(-length/2,width/2)], layer=_l("pad_markers"))
    else:
        c.add_polygon([(-width/2,-length/2),(width/2,-length/2),(width/2,length/2),(-width/2,length/2)], layer=_l("pad_markers"))
    return c


def add_big_pads(c: gf.Component, cfg: PhotonicChipletBaseConfig) -> None:
    """Places 3 square pads and 1 L-shaped pad at the chip corners."""
    sq    = make_big_pad_square(cfg.pad_sq_size)
    l_pad = make_big_pad_L(cfg.pad_sq_size, cfg.pad_L_length)

    for cx, cy in big_pad_square_positions(cfg.chip_width, cfg.chip_height, cfg.pad_sq_margin):
        c.add_ref(sq).move((cx, cy))

    c.add_ref(l_pad).move(
        big_pad_L_origin(cfg.chip_width, cfg.chip_height, cfg.pad_sq_margin, cfg.pad_sq_size)
    )


def add_rectangular_pad_array(c: gf.Component, cfg: PhotonicChipletBaseConfig) -> None:
    """Vertical pads along the left edge, horizontal pads along the bottom edge."""
    v_pad = make_rectangular_pad(cfg.rec_pad_length, cfg.rec_pad_width, "vertical")
    h_pad = make_rectangular_pad(cfg.rec_pad_length, cfg.rec_pad_width, "horizontal")

    v_positions, h_positions = rectangular_pad_positions(
        cfg.chip_width, cfg.chip_height, cfg.pad_sq_margin, cfg.pad_sq_size,
        cfg.rec_pad_length, cfg.rec_pad_width, cfg.rec_pad_margin_from_big_pad, cfg.rec_pad_gap,
    )
    for pos in v_positions:
        c.add_ref(v_pad).move(pos)
    for pos in h_positions:
        c.add_ref(h_pad).move(pos)


def chiplet_number_component(number: int, cfg) -> gf.Component:
    """Adapter: renders the gdstk chiplet-number label into a gf.Component."""
    tmp_cell = gdstk.Library().new_cell("_tmp")
    draw_chiplet_number(tmp_cell, number, cfg)
    c = gf.Component("CHIPLET_ID")
    for poly in tmp_cell.polygons:
        c.add_polygon(poly.points, layer=_l("chiplet_id"))
    return c


def build_chip_frame(cfg: PhotonicChipletBaseConfig, cell_name: str) -> gf.Component:
    """
    Empty chiplet: boundary, active area, corner markers, pads and chiplet ID.
    Devices are added to the returned component by the concrete chiplet.
    """
    c = gf.Component(cell_name)

    if cfg.draw_boundary:
        c << gf.components.rectangle(size=(cfg.chip_width, cfg.chip_height), layer=_l("chip_boundary"), centered=True)

    if cfg.draw_active_area:
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
        c << gf.components.rectangle(size=(cfg.chip_width - 2*inset, cfg.chip_height - 2*inset), layer=_l("chip_active_area"), centered=True)

    add_corner_markers(c, cfg)
    add_big_pads(c, cfg)
    add_rectangular_pad_array(c, cfg)
    c.add_ref(chiplet_number_component(cfg.chiplet_number, cfg))
    return c


# =============================================================================
# INVERSE TONE
# =============================================================================

def coarse_extent_box(cfg: PhotonicChipletBaseConfig) -> tuple:
    """Outer extent of the inverse-tone exposure, as (x0, y0, x1, y1) centred on (0, 0)."""
    if cfg.invert_coarse_extent == "chip":
        inset = 0.0
    elif cfg.invert_coarse_extent == "active_area":
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
    else:
        raise ValueError(
            "invert_coarse_extent must be 'chip' or 'active_area', "
            f"got {cfg.invert_coarse_extent!r}"
        )
    hw = cfg.chip_width / 2 - inset
    hh = cfg.chip_height / 2 - inset
    return (-hw, -hh, hw, hh)

def add_inverse_tone(
        c: gf.Component,
        cfg: PhotonicChipletBaseConfig,
        ) -> dict:
    """
    Run add_inverted_layers on c with the invert_* fields of cfg. The returned
    summary is also stored as a JSON string in c.info["inv_summary"], because
    run_cli receives only c from the builder.
    """
    summary = add_inverted_layers(
        c=c,
        invert_layers=cfg.invert_layers,
        exclude_layers=cfg.invert_exclude_layers,
        coarse_box=coarse_extent_box(cfg),
        bias=cfg.invert_bias,
        exclude_margin=cfg.invert_exclude_margin,
        max_vertices=cfg.invert_max_vertices,
    )

    c.info["inv_summary"] = json.dumps(summary)
    return summary
    

def finish_chip(c: gf.Component,
                cfg: PhotonicChipletBaseConfig,
                ) -> gf.Component:
    """
    Last step of every chiplet builder. If `invert_tone` is `True`, creates an inverted layer.
    """
    if cfg.invert_tone:
        add_inverse_tone(c, cfg)
    return c

def print_inverted_layers_summary(summary: dict) -> None:
    layers = summary["layers"]
    exposed = sum(e["area_um2"] for e in layers)
    protect = summary["protect_area_um2"]
    exclude = summary["exclude_area_um2"]

    print(f"  Inverse tone:    ON  ({len(layers)} output layers)")
    print(f"    {'layer':<12}{'area':>14}{'polygons':>10}{'max pts':>9}")
    for e in layers:
        print(f"    {e['layer']:<12}{e['area_um2']/1e6:>9.3f} mm^2"
              f"{e['n_polygons']:>10d}{e['max_points']:>9d}")
    print(f"    {'protect':<12}{protect/1e6:>9.3f} mm^2")
    print(f"    {'exclude':<12}{exclude/1e6:>9.3f} mm^2")
    print(f"    {'TOTAL':<12}{(exposed + protect + exclude)/1e6:>9.3f} mm^2")


# =============================================================================
# ENTRY POINT
# =============================================================================

def run_cli(config_cls: type,
            build_fn: Callable[..., gf.Component],
            stem: str,
            description: str = "Build a standalone photonic chiplet mask.") -> None:
    """
    Shared ``__main__`` for photonic chiplets: parse the flags, build, write
    ``<stem>_EDIT`` (with --edit) or ``<stem>_NNN`` GDS + JSON to
    masks/experimental/, and report the inverse-tone tiers.
    """
    import argparse

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--edit", action="store_true",
                        help="Edit mode - writes a fixed filename for iteration.")
    parser.add_argument("--invert", action="store_true",
                        help="Also build the tiered inverse-tone (negative) "
                             "exposure layers: inv_t1..inv_t8 + inv_coarse.")
    parser.add_argument("--invert-extent", choices=("chip", "active_area"),
                        default="chip",
                        help="Outer extent of the coarse tier (default: chip).")
    args = parser.parse_args()

    gf.gpdk.PDK.activate()
    cfg = config_cls(
        invert_tone=args.invert,
        invert_coarse_extent=args.invert_extent,
    )
    c = build_fn(cfg)
    EXPERIMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{stem}_EDIT" if args.edit else f"{stem}_{cfg.chiplet_number:03d}"
    gds_path = EXPERIMENTAL_DIR / f"{name}.gds"
    cfg_path = EXPERIMENTAL_DIR / f"{name}.json"
    c.write_gds(gds_path)
    cfg.save(cfg_path)
    print(f"GDS  -> {gds_path}")
    print(f"JSON -> {cfg_path}")
    if cfg.invert_tone:
        print_inverted_layers_summary(json.loads(c.info["inv_summary"]))
    c.show()
