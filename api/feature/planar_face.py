# api/feature/planar_face.py
from __future__ import annotations
from typing import Any, Dict, Tuple

import cadquery as cq

from ..csys import CsysDef, workplane_from_csys
from ..geometry.volume_3d import box_volume_apply, GeometryDelta


class FeatureError(RuntimeError):
    """planar_face の解釈エラー"""


def _axis_to_vector(axis: str) -> Tuple[float, float, float]:
    """
    "+Z", "-Z", "+X", ... を単位ベクトルにマッピング。
    planar_face では主に depth 方向判定のために使う。
    """
    a = axis.strip().upper()
    if a == "+Z":
        return (0.0, 0.0, 1.0)
    if a == "-Z":
        return (0.0, 0.0, -1.0)
    if a == "+X":
        return (1.0, 0.0, 0.0)
    if a == "-X":
        return (-1.0, 0.0, 0.0)
    if a == "+Y":
        return (0.0, 1.0, 0.0)
    if a == "-Y":
        return (0.0, -1.0, 0.0)
    raise FeatureError(f"Unsupported normal_axis: {axis}")


def apply_planar_face_geometry(
    solid: cq.Workplane,
    feature: Dict[str, Any],
    csys_index: Dict[str, CsysDef],
) -> GeometryDelta:
    """
    planar_face フィーチャを「矩形領域の直方体ボリューム cut/add」として適用し、
    GeometryDelta（solid + removed/added）を返す。

    想定 feature 例:

    {
      "feature_type": "planar_face",
      "id": "F1_PLANAR_TOP",
      "params": {
        "csys_id": "WCS",
        "normal_axis": "+Z",
        "depth": 2.0,
        "size_x": 50.0,
        "size_y": 30.0,
        "mode": "cut"   // 任意。省略時 cut
      }
    }

    ※ csys の XY 平面を面の基準とし、原点を矩形の中心とみなす。
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
    direction = _axis_to_vector(normal_axis)

    mode = params.get("mode", "cut")  # 将来 add も許容可能

    # csys の XY を面の平面として扱う
    wp = workplane_from_csys(csys, base_plane="XY")

    # ここで box_volume_apply を使って GeometryDelta を取得
    delta = box_volume_apply(
        solid=solid,
        wp=wp,
        size_x=size_x,
        size_y=size_y,
        depth=depth,
        direction=direction,
        mode=mode,
    )
    return delta
