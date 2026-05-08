"""
verniers.py
===========
Parametric vernier alignment structures for multi-layer lithography.

A vernier pair consists of:
  - A REFERENCE grating on layer A (pad_markers — always fabricated first)
  - An ALIGNED  grating on layer B (the layer being checked for misalignment)

The two gratings have slightly different pitches. When aligned perfectly,
the centre bars line up. A shift of N bars indicates N × δ misalignment,
where δ = pitch_b - pitch_a (the pitch difference = measurement resolution).

One vernier pair measures misalignment in one axis only:
  - Horizontal vernier (H): bars are vertical lines  → measures X misalignment
  - Vertical   vernier (V): bars are horizontal lines → measures Y misalignment

Both orientations are always placed together as a matched pair.

Usage:
    from src.components.verniers import VernierConfig, add_vernier_set

    vernier_cfg = VernierConfig(
        exposures=[
            ("LG",  LAYERS["local_gates"]),
            ("TG",  LAYERS["top_gates"]),
            ("PM",  LAYERS["pos_markers"]),
        ]
    )
    add_vernier_set(cell, lib, vernier_cfg, origin=(x, y))
"""

import gdstk
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple

from src.config.layers import LAYERS
from src.utils.deplof_font import deplof_text


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class VernierConfig:
    # --- Grating geometry ---
    bar_length:     float = 50.0    # um — long dimension of each bar
    bar_width:      float = 3.0     # um — short dimension of each bar
    pitch_ref:      float = 10.0    # um — pitch of reference grating (pad_markers)
    pitch_delta:    float = 1.0     # um — pitch difference → measurement resolution
    n_bars:         int   = 5       # number of bars per side (total = 2*n_bars + 1)

    # --- Layout ---
    grating_gap:    float = 10.0    # um — gap between reference and aligned gratings
    pair_gap:       float = 20.0    # um — gap between H and V verniers in a pair
    group_gap:      float = 40.0    # um — gap between exposure groups
    label_size:     float = 20.0    # um — DEPLOF font height for exposure number labels
    label_gap:      float = 8.0     # um — gap between vernier pair and its label

    # --- Exposures ---
    # List of (label_str, layer_dict) for each exposure to compare against pad_markers.
    # label_str is rendered as a number label beside the vernier pair.
    # layer_dict is the LAYERS entry for the aligned layer.
    exposures: List[Tuple[str, dict]] = field(default_factory=lambda: [
        ("1", LAYERS["local_gates"]),
        ("2", LAYERS["top_gates"]),
        ("3", LAYERS["pos_markers"]),
    ])


# =============================================================================
# SINGLE VERNIER GRATING
# =============================================================================

def _draw_grating(cell: gdstk.Cell,
                  cx: float, cy: float,
                  n_bars: int,
                  pitch: float,
                  bar_width: float,
                  bar_length: float,
                  orientation: str,
                  layer: dict) -> None:
    """
    Draws a single grating of (2*n_bars + 1) bars centred on (cx, cy).

    Parameters
    ----------
    orientation : "H" — vertical bars (measures X displacement)
                  "V" — horizontal bars (measures Y displacement)
    """
    lp      = {"layer": layer["layer"], "datatype": layer["datatype"]}
    n_total = 2 * n_bars + 1
    hw      = bar_width  / 2
    hl      = bar_length / 2

    for i in range(n_total):
        offset = (i - n_bars) * pitch
        if orientation == "H":
            cell.add(gdstk.rectangle(
                (cx + offset - hw, cy - hl),
                (cx + offset + hw, cy + hl),
                **lp
            ))
        else:
            cell.add(gdstk.rectangle(
                (cx - hl, cy + offset - hw),
                (cx + hl, cy + offset + hw),
                **lp
            ))


def _grating_span(n_bars: int, pitch: float, bar_width: float) -> float:
    """
    Total span (tip to tip) of a grating along its measurement axis.
    The outermost bar centres are at ±n_bars*pitch, each half a bar_width wide.
    """
    return 2 * n_bars * pitch + bar_width


# =============================================================================
# SINGLE VERNIER  (one orientation, reference + aligned interleaved)
# =============================================================================
#
# Layout of one vernier (H orientation shown, looking from above):
#
#   ┌──────────────────────────────────┐  ▲
#   │  ref bar  ref bar  ref bar  ...  │  │  bar_length      ← reference grating
#   └──────────────────────────────────┘  ▼
#        gap = grating_gap
#   ┌──────────────────────────────────┐  ▲
#   │  aln bar  aln bar  aln bar  ...  │  │  bar_length      ← aligned grating
#   └──────────────────────────────────┘  ▼
#
# The two gratings are spatially separated by grating_gap so they are visually
# readable. The reference grating pitch is pitch_ref; the aligned grating pitch
# is pitch_ref + pitch_delta. When perfectly aligned the centre bars coincide
# in x (for H). A shift of N bars = N × pitch_delta misalignment.
#
# A wider centre tick on the reference grating marks the zero position.

def _single_vernier_height(cfg: VernierConfig) -> float:
    """
    Total height of one single-orientation vernier (ref + gap + aligned).
    Used for both H (where 'height' is the stacking direction, i.e. y)
    and V (where it is the x extent, but the same formula applies by symmetry).
    """
    return 2 * cfg.bar_length + cfg.grating_gap


def _draw_single_vernier(cell: gdstk.Cell,
                         cx: float, cy: float,
                         aligned_layer: dict,
                         orientation: str,
                         cfg: VernierConfig) -> None:
    """
    Draws one vernier (reference grating + aligned grating) centred on (cx, cy).

    For orientation "H":
      - reference grating is on top   (cy + bar_length/2 + grating_gap/2)
      - aligned  grating is on bottom (cy - bar_length/2 - grating_gap/2)

    For orientation "V" the same geometry is rotated 90°:
      - reference grating is on the right
      - aligned  grating is on the left
    """
    ref_layer     = LAYERS["pad_markers"]
    pitch_aligned = cfg.pitch_ref + cfg.pitch_delta

    half_stack = cfg.bar_length / 2 + cfg.grating_gap / 2

    if orientation == "H":
        ref_cy = cy + half_stack
        aln_cy = cy - half_stack
        # Reference grating — full bar_length tall
        _draw_grating(cell, cx, ref_cy,
                      cfg.n_bars, cfg.pitch_ref, cfg.bar_width, cfg.bar_length,
                      "H", ref_layer)
        # Centre tick on reference — slightly taller and wider to stand out
        _draw_grating(cell, cx, ref_cy,
                      0, cfg.pitch_ref, cfg.bar_width * 2, cfg.bar_length * 1.2,
                      "H", ref_layer)
        # Aligned grating — same bar_length, different pitch
        _draw_grating(cell, cx, aln_cy,
                      cfg.n_bars, pitch_aligned, cfg.bar_width, cfg.bar_length,
                      "H", aligned_layer)

    else:  # "V"
        ref_cx = cx + half_stack
        aln_cx = cx - half_stack
        # Reference grating
        _draw_grating(cell, ref_cx, cy,
                      cfg.n_bars, cfg.pitch_ref, cfg.bar_width, cfg.bar_length,
                      "V", ref_layer)
        # Centre tick
        _draw_grating(cell, ref_cx, cy,
                      0, cfg.pitch_ref, cfg.bar_width * 2, cfg.bar_length * 1.2,
                      "V", ref_layer)
        # Aligned grating
        _draw_grating(cell, aln_cx, cy,
                      cfg.n_bars, pitch_aligned, cfg.bar_width, cfg.bar_length,
                      "V", aligned_layer)


# =============================================================================
# SINGLE VERNIER PAIR  (H on top, V on bottom, for one exposure)
# =============================================================================

def _pair_height(cfg: VernierConfig) -> float:
    """
    Total height of one H+V pair.

    H vernier occupies: 2*bar_length + grating_gap  (stacked in y)
    V vernier occupies: 2*bar_length + grating_gap  (stacked in x, but takes
                        bar_length height in y)
    Plus pair_gap between H and V.

    H vernier height = 2*bar_length + grating_gap
    V vernier height = bar_length   (its bar_length is the y extent)
    """
    h_height = 2 * cfg.bar_length + cfg.grating_gap
    v_height = cfg.bar_length
    return h_height + cfg.pair_gap + v_height


def _pair_width(cfg: VernierConfig) -> float:
    """
    Total width of one H+V pair.

    H vernier width = span of the wider grating (aligned, pitch_ref+delta, n_bars)
                    + bar_width (for outermost half-bars)
    V vernier width = 2*bar_length + grating_gap (stacked in x)
    We take the max of the two.
    """
    h_width = _grating_span(cfg.n_bars, cfg.pitch_ref + cfg.pitch_delta, cfg.bar_width)
    v_width = 2 * cfg.bar_length + cfg.grating_gap
    return max(h_width, v_width)


def _draw_vernier_pair(cell: gdstk.Cell,
                       cx: float, cy: float,
                       aligned_layer: dict,
                       cfg: VernierConfig) -> None:
    """
    Draws one H vernier (top) and one V vernier (bottom) centred on (cx, cy).
    The two are separated by pair_gap so they don't overlap.
    """
    h_height = 2 * cfg.bar_length + cfg.grating_gap
    v_height = cfg.bar_length

    # H vernier centre — top half
    h_cy = cy + cfg.pair_gap / 2 + h_height / 2
    _draw_single_vernier(cell, cx, h_cy, aligned_layer, "H", cfg)

    # V vernier centre — bottom half
    v_cy = cy - cfg.pair_gap / 2 - v_height / 2
    _draw_single_vernier(cell, cx, v_cy, aligned_layer, "V", cfg)


# =============================================================================
# FULL VERNIER SET  (all exposure pairs side by side)
# =============================================================================

def vernier_set_width(cfg: VernierConfig) -> float:
    """
    Total width of the full vernier set.
    Uses the true bounding box of each pair including bar overhang.
    """
    pw = _pair_width(cfg)
    return len(cfg.exposures) * pw + (len(cfg.exposures) - 1) * cfg.group_gap


def vernier_set_height(cfg: VernierConfig) -> float:
    """Total height of the full vernier set including label."""
    return _pair_height(cfg) + cfg.label_size + cfg.label_gap


def add_vernier_set(cell: gdstk.Cell,
                    cfg: VernierConfig,
                    origin: Tuple[float, float]) -> None:
    """
    Places the full set of vernier pairs into *cell*.

    The set is anchored at *origin* = bottom-left corner of the bounding box.
    Each exposure gets one H+V pair, with a number label below it.
    Pairs are arranged left to right.

    Parameters
    ----------
    cell   : target gdstk.Cell
    cfg    : VernierConfig
    origin : (x, y) bottom-left corner of the vernier block
    """
    ox, oy      = origin
    pw          = _pair_width(cfg)
    ph          = _pair_height(cfg)
    label_layer = LAYERS["chiplet_id"]

    for i, (label_str, aligned_layer) in enumerate(cfg.exposures):
        cx = ox + i * (pw + cfg.group_gap) + pw / 2
        cy = oy + cfg.label_size + cfg.label_gap + ph / 2

        _draw_vernier_pair(cell, cx, cy, aligned_layer, cfg)

        # Number label centred below the pair
        label_w = len(label_str) * cfg.label_size * 0.6
        deplof_text(
            cell,
            text   = label_str,
            size   = cfg.label_size,
            origin = (cx - label_w / 2, oy),
            layer  = label_layer,
        )