"""
markers.py
==========
Reusable primitive marker components for chiplet and wafer masks.

All functions return a named gdstk.Cell centred on (0, 0) and are
safe to call multiple times — if the cell already exists in the library
it is returned immediately without re-building.

Usage:
    from src.components.markers import (
        make_corner_marker, make_cross_marker, make_square_marker,
        make_x_marker, make_big_pad_square, make_big_pad_L,
        make_small_pad, make_rectangular_pad,
    )
"""

import gdstk
import numpy as np

from src.config.layers import LAYERS


# =============================================================================
# HELPERS
# =============================================================================

def _get_or_create(lib: gdstk.Library, name: str) -> tuple[gdstk.Cell | None, bool]:
    """
    Returns (existing_cell, True) if *name* already exists in *lib*,
    otherwise returns (new_cell, False).
    """
    existing = next((c for c in lib.cells if c.name == name), None)
    if existing:
        return existing, True
    return lib.new_cell(name), False


def _make_cross(lib: gdstk.Library,
                cell_name: str,
                length: float,
                width: float,
                layer_key: str) -> gdstk.Cell:
    """
    Generic boolean-union cross (+) centred on (0, 0).
    Shared implementation for all cross sizes.
    """
    cell, already_exists = _get_or_create(lib, cell_name)
    if already_exists:
        return cell

    L  = length / 2
    W  = width  / 2
    lp = LAYERS[layer_key]

    h_bar = gdstk.rectangle((-L, -W), ( L,  W))
    v_bar = gdstk.rectangle((-W, -L), ( W,  L))
    for poly in gdstk.boolean([h_bar], [v_bar], "or",
                               layer=lp["layer"], datatype=lp["datatype"]):
        cell.add(poly)
    return cell


def _make_square(lib: gdstk.Library,
                 cell_name: str,
                 size: float,
                 layer_key: str) -> gdstk.Cell:
    """Generic square centred on (0, 0). Shared for all square marker sizes."""
    cell, already_exists = _get_or_create(lib, cell_name)
    if already_exists:
        return cell

    h = size / 2
    cell.add(gdstk.rectangle((-h, -h), (h, h), **LAYERS[layer_key]))
    return cell


# =============================================================================
# CHIP-LEVEL MARKERS
# =============================================================================

def make_corner_marker(lib: gdstk.Library,
                       sq_size: float,
                       sq_gap: float,
                       array: str = "3x3") -> gdstk.Cell:
    """
    Corner marker: a regular grid of small squares centred on (0, 0).

    Parameters
    ----------
    sq_size : side length of each square (um)
    sq_gap  : centre-to-centre pitch between squares (um)
    array   : "2x2" | "2x1x2" | "3x3"
    """
    cell_name = f"CORNER_MARKER_{array}"
    cell, already_exists = _get_or_create(lib, cell_name)
    if already_exists:
        return cell

    half = sq_size / 2 + sq_gap / 2

    positions = {
        "2x2": [
            (-half, -half), ( half, -half),
            (-half,  half), ( half,  half),
        ],
        "2x1x2": [
            (-half, -half), ( half, -half),
            (    0,     0),
            (-half,  half), ( half,  half),
        ],
        "3x3": [
            (-2*half, -2*half), (0, -2*half), (2*half, -2*half),
            (-2*half,       0), (0,       0), (2*half,       0),
            (-2*half,  2*half), (0,  2*half), (2*half,  2*half),
        ],
    }

    if array not in positions:
        raise ValueError(f"Unknown corner marker array style '{array}'. "
                         f"Choose from: {list(positions)}")

    sq = sq_size / 2
    for ox, oy in positions[array]:
        cell.add(gdstk.rectangle(
            (ox - sq, oy - sq),
            (ox + sq, oy + sq),
            **LAYERS["corner_markers"]
        ))
    return cell


def make_x_marker(lib: gdstk.Library,
                  size: float,
                  width: float) -> gdstk.Cell:
    """
    X-shaped marker centred on (0, 0), built from two ±45° rotated bars
    merged with a boolean union to avoid double-exposure.

    Parameters
    ----------
    size  : tip-to-tip diagonal length (um)
    width : arm thickness (um)
    """
    cell, already_exists = _get_or_create(lib, "X_MARKER")
    if already_exists:
        return cell

    L  = size  / 2
    W  = width / 2
    lp = LAYERS["corner_markers"]

    def rotated_bar(theta: float) -> gdstk.Polygon:
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        pts = [(-L, -W), (L, -W), (L, W), (-L, W)]
        return gdstk.Polygon([
            (x * cos_t - y * sin_t, x * sin_t + y * cos_t)
            for x, y in pts
        ])

    angle = np.deg2rad(45)
    for poly in gdstk.boolean([rotated_bar(angle)], [rotated_bar(-angle)], "or",
                               layer=lp["layer"], datatype=lp["datatype"]):
        cell.add(poly)
    return cell


def make_big_pad_square(lib: gdstk.Library, size: float) -> gdstk.Cell:
    """Square alignment pad centred on (0, 0)."""
    return _make_square(lib, "BIG_PAD_SQUARE", size, "pad_markers")


def make_big_pad_L(lib: gdstk.Library,
                   pad_size: float,
                   arm_length: float) -> gdstk.Cell:
    """
    L-shaped alignment marker. Inner corner at (0, 0), arms extend in +x and +y.

    Parameters
    ----------
    pad_size   : thickness of each arm (um) — matches the square pad size
    arm_length : outer length of each arm (um)
    """
    cell, already_exists = _get_or_create(lib, "BIG_PAD_L")
    if already_exists:
        return cell

    T = pad_size
    L = arm_length
    pts = [
        (0, 0),  # inner corner
        (L, 0),  # end of horizontal arm
        (L, T),  # outer bottom-right
        (T, T),  # elbow
        (T, L),  # outer top of vertical arm
        (0, L),  # end of vertical arm
    ]
    cell.add(gdstk.Polygon(pts, **LAYERS["pad_markers"]))
    return cell


def make_small_pad(lib: gdstk.Library, size: float) -> gdstk.Cell:
    """Small square pad centred on (0, 0). Used for top pad arrays."""
    return _make_square(lib, "SMALL_PAD", size, "pad_markers")


def make_rectangular_pad(lib: gdstk.Library,
                         length: float,
                         width: float,
                         orientation: str = "horizontal") -> gdstk.Cell:
    """
    Rectangular pad centred on (0, 0).

    Parameters
    ----------
    length      : long dimension (um)
    width       : short dimension (um)
    orientation : "horizontal" (length along x) | "vertical" (length along y)
    """
    if orientation not in ("horizontal", "vertical"):
        raise ValueError(f"orientation must be 'horizontal' or 'vertical', got '{orientation}'")

    cell_name = f"RECTANGULAR_PAD_{orientation.upper()}"
    cell, already_exists = _get_or_create(lib, cell_name)
    if already_exists:
        return cell

    if orientation == "horizontal":
        cell.add(gdstk.rectangle((-length/2, -width/2), (length/2, width/2), **LAYERS["pad_markers"]))
    else:
        cell.add(gdstk.rectangle((-width/2, -length/2), (width/2, length/2), **LAYERS["pad_markers"]))
    return cell


# =============================================================================
# WAFER-LEVEL MARKERS
# =============================================================================

def make_cross_marker(lib: gdstk.Library,
                      cell_name: str,
                      length: float,
                      width: float) -> gdstk.Cell:
    """
    Cross (+) alignment marker centred on (0, 0) on the wafer_markers layer.

    Parameters
    ----------
    cell_name : GDS cell name (allows multiple sizes to coexist)
    length    : tip-to-tip arm length (um)
    width     : arm thickness (um)
    """
    return _make_cross(lib, cell_name, length, width, "wafer_markers")


def make_dicing_lane_cross(lib: gdstk.Library,
                           length: float,
                           width: float) -> gdstk.Cell:
    """Cross (+) marker on the crosses layer."""
    return _make_cross(lib, "DICING_LANE_CROSS", length, width, "dicing_crosses")


def make_square_marker(lib: gdstk.Library,
                       cell_name: str,
                       size: float) -> gdstk.Cell:
    """
    Square marker centred on (0, 0) on the wafer_markers layer.

    Parameters
    ----------
    cell_name : GDS cell name (allows multiple sizes to coexist)
    size      : side length (um)
    """
    return _make_square(lib, cell_name, size, "wafer_markers")


def make_L_shaped_wafer_pad(lib: gdstk.Library,
                             heights: tuple[float, float, float],
                             lengths: tuple[float, float, float]) -> gdstk.Cell:
    """
    Stepped L-shaped pad for wafer-level alignment, anchored at (0, 0).

    Parameters
    ----------
    heights : (h1, h2, h3) — step heights in um
    lengths : (l1, l2, l3) — step lengths in um
    """
    cell, already_exists = _get_or_create(lib, "L_SHAPED_WAFER_PAD")
    if already_exists:
        return cell

    h1, h2, h3 = heights
    l1, l2, l3 = lengths

    pts = [
        (0,  0),
        (0,  h1),
        (l1, h1),
        (l1, h2),
        (l2, h2),
        (l2, h3),
        (l3, h3),
        (l3,  0),
    ]
    cell.add(gdstk.Polygon(pts, **LAYERS["wafer_markers"]))
    return cell