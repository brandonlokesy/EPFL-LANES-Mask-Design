"""
Utilities for rendering DEPLOF stroke font in gdstk layouts.

Uses the DEPLOF glyph data embedded directly in gdsfactory (gdsfactory.constants),
so no external .gds font file is required.

Each glyph is stored as a list of polygons in a 0–1000 unit coordinate box.
We scale by (size / 1000) to map that box to the desired character height in um.
Character advance width is taken from gdsfactory's _width and _indent tables,
matching gdsfactory's own text_freetype behaviour exactly.

Usage:
    from deplof_font import deplof_text

    deplof_text(
        cell,
        text      = "W07",
        size      = 500.0,          # character height in um
        origin    = (x, y),         # bottom-left of first character
        layer     = LAYERS["wafer_id"],
        spacing   = 1.0,            # multiplier on per-character advance (default 1.0)
    )
"""

import numpy as np
import gdstk
from typing import Tuple

# ---------------------------------------------------------------------------
# Load DEPLOF glyph tables from gdsfactory.
# _glyph  : dict[int, list[list[list[int]]]]  keyed by ASCII value
#           each value is a list of polygons; each polygon is a list of [x, y]
#           in a 0–1000 unit box (height = 1000 units).
# _width  : dict[int, int]  nominal advance width per character (units)
# _indent : dict[int, int]  additional indent / kerning offset (units)
# ---------------------------------------------------------------------------
try:
    from gdsfactory.constants import _glyph, _indent, _width
except ImportError as e:
    raise ImportError(
        "gdsfactory is required for DEPLOF font rendering. "
        "Install it with: pip install gdsfactory"
    ) from e

# Unit box height used by gdsfactory's DEPLOF data
_FONT_UNITS: float = 1000.0


def deplof_text(
    cell: gdstk.Cell,
    text: str,
    size: float,
    origin: Tuple[float, float],
    layer: dict,
    spacing: float = 1.0,
    x_reflection: bool = False,
    rotation: float = 0.0,
) -> float:
    """
    Place DEPLOF font text into *cell* as gdstk polygons.

    Parameters
    ----------
    cell        : target gdstk.Cell
    text        : string to render (printable ASCII)
    size        : character height in um  (maps the 1000-unit font box → size um)
    origin      : (x, y) bottom-left of the first character
    layer       : LAYERS dict entry, e.g. LAYERS["wafer_id"]
    spacing     : multiplier on each character's natural advance width (default 1.0)
    x_reflection: mirror text horizontally around the origin x
    rotation    : rotation in radians (applied around origin)

    Returns
    -------
    float — x coordinate after the last character (for chaining calls)
    """
    scale = size / _FONT_UNITS
    lp = {"layer": layer["layer"], "datatype": layer["datatype"]}
    ox, oy = origin

    x_cursor = 0.0  # work in font units, translate to um at polygon creation

    for char in text:
        ascii_val = ord(char)

        if char == " ":
            x_cursor += 500 * spacing
            continue

        if ascii_val not in _glyph:
            # Skip unsupported characters silently
            if ascii_val in _width:
                x_cursor += (_width[ascii_val] + _indent.get(ascii_val, 0)) * spacing
            else:
                x_cursor += 500 * spacing
            continue

        for poly in _glyph[ascii_val]:
            pts = np.array(poly, dtype=float)   # shape (N, 2), units 0–1000

            if x_reflection:
                pts[:, 0] = -pts[:, 0]

            # Scale to um and translate to cursor position + origin
            xpts = pts[:, 0] * scale + x_cursor * scale + ox
            ypts = pts[:, 1] * scale + oy

            if rotation != 0.0:
                cos_r, sin_r = np.cos(rotation), np.sin(rotation)
                # Rotate around origin
                dx = xpts - ox
                dy = ypts - oy
                xpts = ox + dx * cos_r - dy * sin_r
                ypts = oy + dx * sin_r + dy * cos_r

            points = list(zip(xpts.tolist(), ypts.tolist()))
            cell.add(gdstk.Polygon(points, **lp))

        x_cursor += (_width[ascii_val] + _indent.get(ascii_val, 0)) * spacing

    return ox + x_cursor * scale