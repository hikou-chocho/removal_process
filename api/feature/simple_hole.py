# api/feature/simple_hole.py
from __future__ import annotations
from typing import Any, Dict, Tuple

import cadquery as cq

from ..csys import CsysDef, workplane_from_csys
from ..geometry.volume_3d import cylinder_volume_apply, GeometryDelta


class FeatureError(RuntimeError):
    """simple_hole の解釈エラー"""


def apply_simple_hole_geometry(
    solid: cq.Workplane,
    feature: Dict[str, Any],
    csys_index: Dict[str, CsysDef],
) -> GeometryDelta:
    """
    simple_hole を円柱押し出しで cut/add。
    """
    params = feature.get("params") or {}

    csys_id = params.get("csys_id")  # CSYS ローカル
    if not csys_id:
        raise FeatureError("simple_hole.params.csys_id is required")

    csys = csys_index.get(csys_id)
    if csys is None:
        raise FeatureError(f"Unknown csys_id: {csys_id}")

    diameter = float(params.get("diameter", 0.0))
    if diameter <= 0.0:
        raise FeatureError("simple_hole.diameter must be > 0")

    depth = float(params.get("depth", 0.0))
    if depth <= 0.0:
        raise FeatureError("simple_hole.depth must be > 0")

    origin_x = float(params.get("origin_x", 0.0))
    origin_y = float(params.get("origin_y", 0.0))

    axis = params.get("axis", "-Z")  # CSYS ローカル
    if axis not in ("+Z", "-Z"):
        raise FeatureError("simple_hole.axis must be '+Z' or '-Z' in CSYS local coords")

    # depth の符号を axis で決定
    signed_depth = depth if axis == "+Z" else -depth

    mode = params.get("mode", "cut")

    wp = workplane_from_csys(csys, base_plane="XY").center(origin_x, origin_y)

    delta = cylinder_volume_apply(
        solid=solid,
        wp=wp,
        diameter=diameter,
        depth=signed_depth,
        mode=mode,
    )
    return delta
