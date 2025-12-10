# api/feature/planar_face.py
from __future__ import annotations
from typing import Any, Dict, Tuple

import cadquery as cq

from ..csys import CsysDef, workplane_from_csys
from ..geometry.profile_2d import make_rect_profile_centered
from ..geometry.volume_3d import extrude_profile_volume, GeometryDelta


class FeatureError(RuntimeError):
    """planar_face の解釈エラー"""


def apply_planar_face_geometry(
    solid: cq.Workplane,
    feature: Dict[str, Any],
    csys_index: Dict[str, CsysDef],
) -> GeometryDelta:
    """
    planar_face フィーチャを「矩形プロファイル押し出し」で cut/add。
    profile_2d.make_rect_profile_centered + volume_3d.extrude_profile_volume ベース。
    """
    params = feature.get("params") or {}

    csys_id = params.get("csys_id")
    if not csys_id:
        raise FeatureError("planar_face.params.csys_id is required")

    csys = csys_index.get(csys_id)
    if csys is None:
        raise FeatureError(f"Unknown csys_id: {csys_id}")

    depth = float(params.get("depth", 0.0))
    if depth <= 0.0:
        raise FeatureError("planar_face.depth must be > 0")

    size_x = float(params.get("size_x", 0.0))
    size_y = float(params.get("size_y", 0.0))
    if size_x <= 0.0 or size_y <= 0.0:
        raise FeatureError("planar_face.size_x/size_y must be > 0")

    normal_axis = params.get("normal_axis", "+Z")
    a = str(normal_axis).strip().upper()
    if a not in ("+Z", "-Z"):
        raise FeatureError("planar_face.normal_axis must be '+Z' or '-Z'")
    direction = (0.0, 0.0, 1.0) if a == "+Z" else (0.0, 0.0, -1.0)

    mode = params.get("mode", "cut")

    # csys の XY を面の平面として扱う
    wp = workplane_from_csys(csys, base_plane="XY")

    # profile_2d.make_rect_profile_centered で矩形プロファイルを作成
    prof = make_rect_profile_centered(
        wp=wp,
        width=size_x,
        length=size_y,
        corner_radius=0.0,
    )

    # volume_3d.extrude_profile_volume で押し出し
    delta = extrude_profile_volume(
        solid=solid,
        profile=prof,
        depth=depth,
        direction=direction,
        mode=mode,
    )
    return delta
