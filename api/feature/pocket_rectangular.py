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
    pocket_rectangular フィーチャを矩形プロファイル + 押し出しボリューム cut/add として適用。

    axis は CSYS ローカル基準で解釈する:
      - axis = "-Z"（デフォルト）: 面の表側(+Z)から中(-Z)へ掘る
      - axis = "+Z"               : 中から表側へ押し出す（特殊用途）
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

    axis = params.get("axis", "-Z")  # CSYS ローカル
    if axis not in ("+Z", "-Z"):
        raise FeatureError("pocket_rectangular.axis must be '+Z' or '-Z' in CSYS local coords")

    # depth の符号を axis で決定
    signed_depth = depth if axis == "+Z" else -depth

    mode = params.get("mode", "cut")

    # csys の XY 平面上で、origin_x / origin_y をポケット中心に取る
    wp = workplane_from_csys(csys, base_plane="XY").center(origin_x, origin_y)

    # 2D 矩形プロファイル（角R付き）を生成
    prof = make_rect_profile_centered(
        wp=wp,
        width=width,
        length=length,
        corner_radius=corner_radius,
    )

    # ローカル Z 方向に押し出して cut/add
    delta = extrude_profile_volume(
        solid=solid,
        profile=prof,
        depth=signed_depth,
        mode=mode,
    )
    return delta
