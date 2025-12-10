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
    planar_face フィーチャを「矩形領域の平面加工」として適用。
    実装は rect プロファイル＋押し出しボリュームの cut/add。

    axis は CSYS ローカル基準で解釈する:
      - axis = "-Z"（デフォルト）: 面の表側(+Z)から中(-Z)へ削る
      - axis = "+Z"               : 中から表側へ削る（特殊用途）

    既存データで normal_axis がある場合:
      - geometry 的には使わず、あくまでメタ情報として扱う
      - axis 未指定なら "-Z" とみなす（後方互換）
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

    # axis: CSYS ローカル。省略時は "-Z"（表側から中へ）
    axis = params.get("axis", "-Z")
    if axis not in ("+Z", "-Z"):
        raise FeatureError("planar_face.axis must be '+Z' or '-Z' in CSYS local coords")

    # depth の符号を axis で決定
    signed_depth = depth if axis == "+Z" else -depth

    mode = params.get("mode", "cut")

    # csys の XY を面の平面として扱う（原点を矩形中心とみなす）
    wp = workplane_from_csys(csys, base_plane="XY")

    # 2D プロファイル（矩形）を生成。planar_face は角Rなし。
    prof = make_rect_profile_centered(
        wp=wp,
        width=size_x,
        length=size_y,
        corner_radius=0.0,
    )

    # ローカル Z 方向に押し出して cut/add
    delta = extrude_profile_volume(
        solid=solid,
        profile=prof,
        depth=signed_depth,
        mode=mode,
    )
    return delta
