# api/feature/turn_od_profile.py
from __future__ import annotations
from typing import Any, Dict, List

import cadquery as cq

from ..csys import CsysDef, workplane_from_csys
from ..geometry.profile_2d import make_turn_od_profile_zd
from ..geometry.volume_3d import revolve_profile_volume, GeometryDelta


class FeatureError(RuntimeError):
    """Feature 解釈時のユーザー向けエラー"""


def apply_turn_od_profile_geometry(
    solid: cq.Workplane,
    feature: Dict[str, Any],
    csys_index: Dict[str, CsysDef],
) -> GeometryDelta:
    """
    turn_od_profile フィーチャを幾何として適用し、
    GeometryDelta（solid + removed/added）を返す。

    想定する feature 例:

    {
      "feature_type": "turn_od_profile",
      "id": "F_OD",
      "params": {
        "csys_id": "WCS",
        "profile": [
          { "z": 0.0,  "radius": 25.0 },
          { "z": 20.0, "radius": 25.0 },
          { "z": 20.0, "radius": 20.0 },
          { "z": 40.0, "radius": 20.0 },
          { "z": 40.0, "radius": 15.0 },
          { "z": 80.0, "radius": 15.0 }
        ],
        "angle_deg": 360.0,
        "mode": "cut"  # or "add"
      }
    }
    """

    params = feature.get("params") or {}

    csys_id = params.get("csys_id")
    if not csys_id:
        raise FeatureError("turn_od_profile.params.csys_id is required")

    csys = csys_index.get(csys_id)
    if csys is None:
        raise FeatureError(f"Unknown csys_id: {csys_id}")

    profile_pts: List[Dict[str, float]] = params.get("profile") or []
    if not profile_pts:
        raise FeatureError("turn_od_profile.params.profile is required")

    angle_deg = float(params.get("angle_deg", 360.0))
    mode = params.get("mode", "cut")

    # 1) CSYS から軸方向 Workplane を取得
    # ここでは「XZ 平面に Z 軸方向のプロファイル」を描く想定
    wp_axis = workplane_from_csys(csys, base_plane="XZ")

    # 2) Z–D プロファイルを作成
    prof = make_turn_od_profile_zd(wp_axis, profile_pts)

    # 3) プロファイルを回転して solid に適用（GeometryDelta を受け取る）
    delta = revolve_profile_volume(
        solid=solid,
        profile=prof,
        angle_deg=angle_deg,
        mode=mode,
    )
    return delta
