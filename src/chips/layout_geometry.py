"""
layout_geometry.py
==================
Pure position-computing functions for chiplet infrastructure elements.

All functions take scalar parameters and return lists of (x, y) tuples.
No gdstk or gdsfactory dependency — safe to import from either chip file.

Coordinate convention: chip centre at (0, 0).
"""


def corner_marker_positions(
    chip_width: float,
    chip_height: float,
    corner_margin: float,
) -> list[tuple[float, float]]:
    """Returns the 4 corner marker centres, one per chip corner."""
    hw, hh = chip_width / 2, chip_height / 2
    i = corner_margin
    return [
        (-hw + i, -hh + i),
        ( hw - i, -hh + i),
        (-hw + i,  hh - i),
        ( hw - i,  hh - i),
    ]


def big_pad_square_positions(
    chip_width: float,
    chip_height: float,
    pad_sq_margin: float,
) -> list[tuple[float, float]]:
    """Returns the 3 square pad centres (TR, TL, BR corners; BL gets the L-pad)."""
    hw, hh = chip_width / 2, chip_height / 2
    i = pad_sq_margin
    return [
        ( hw - i, -hh + i),
        (-hw + i,  hh - i),
        ( hw - i,  hh - i),
    ]


def big_pad_L_origin(
    chip_width: float,
    chip_height: float,
    pad_sq_margin: float,
    pad_sq_size: float,
) -> tuple[float, float]:
    """Returns the origin of the L-pad (inner corner, at the BL chip corner)."""
    hw, hh = chip_width / 2, chip_height / 2
    return (
        -hw + pad_sq_margin - pad_sq_size / 2,
        -hh + pad_sq_margin - pad_sq_size / 2,
    )


def rectangular_pad_positions(
    chip_width: float,
    chip_height: float,
    pad_sq_margin: float,
    pad_sq_size: float,
    rec_pad_length: float,
    rec_pad_width: float,
    rec_pad_margin_from_big_pad: float,
    rec_pad_gap: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Returns (vertical_positions, horizontal_positions).

    vertical   : 14 pad centres along the left edge, top-to-bottom
    horizontal : 9 pad centres along the bottom edge (indices 4-8 skipped)
    """
    pitch  = rec_pad_gap + rec_pad_length
    hw, hh = chip_width / 2, chip_height / 2

    top_left_x = -hw + pad_sq_margin
    top_left_y =  hh - pad_sq_margin
    vertical = [
        (
            top_left_x + pad_sq_size / 2 - rec_pad_width / 2,
            top_left_y - pad_sq_size / 2 - rec_pad_margin_from_big_pad - i * pitch,
        )
        for i in range(14)
    ]

    skip       = set(range(4, 9))
    bot_left_x = -hw + pad_sq_margin
    bot_left_y = -hh + pad_sq_margin
    horizontal = [
        (
            bot_left_x + 3 * pad_sq_size / 2 + rec_pad_margin_from_big_pad + i * pitch,
            bot_left_y + pad_sq_size / 2 - rec_pad_width / 2,
        )
        for i in range(14) if i not in skip
    ]

    return vertical, horizontal
