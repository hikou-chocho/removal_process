# api/feature/pocket_rectangular.py
from __future__ import annotations
from typing import Any, Dict, Tuple

import cadquery as cq

from ..csys import CsysDef, workplane_from_csys
from ..geometry.profile_2d import make_rect_profile_centered
from ..geometry.volume_3d import extrude_profile_volume, GeometryDelta


class FeatureError(RuntimeError):
    """pocket_rectangular の解釈エラー"""


def apply_pocket_rectangular_geometry(
    solid: cq.Workplane,
    feature: Dict[str, Any],
    csys_index: Dict[str, CsysDef],
) -> GeometryDelta:
    """
    pocket_rectangular を矩形プロファイル押し出しで cut/add。
    """
    params = feature.get("params") or {}

    csys_id = params.get("csys_id")
    if not csys_id:
        raise FeatureError("pocket_rectangular.params.csys_id is required")

    csys = csys_index.get(csys_id)
    if csys is None:
        raise FeatureError(f"Unknown csys_id: {csys_id}")

    width = float(params.get("width", 0.0))
    length = float(params.get("length", 0.0))
    if width <= 0.0 or length <= 0.0:
        raise FeatureError("pocket_rectangular.width/length must be > 0")

    depth = float(params.get("depth", 0.0))
    if depth <= 0.0:
        raise FeatureError("pocket_rectangular.depth must be > 0")

    corner_radius = float(params.get("corner_radius", 0.0))
    origin_x = float(params.get("origin_x", 0.0))
    origin_y = float(params.get("origin_y", 0.0))

    axis = params.get("axis", "-Z")
    a = str(axis).strip().upper()
    if a not in ("+Z", "-Z"):
        raise FeatureError("pocket_rectangular.axis must be '+Z' or '-Z'")
    direction = (0.0, 0.0, 1.0) if a == "+Z" else (0.0, 0.0, -1.0)

    mode = params.get("mode", "cut")

    wp = workplane_from_csys(csys, base_plane="XY").center(origin_x, origin_y)

    prof = make_rect_profile_centered(
        wp=wp,
        width=width,
        length=length,
        corner_radius=corner_radius,
    )

    delta = extrude_profile_volume(
        solid=solid,
        profile=prof,
        depth=depth,
        direction=direction,
        mode=mode,
    )
    return delta
