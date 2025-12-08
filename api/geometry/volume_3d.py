# api/geometry/volume_3d.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal
import cadquery as cq


@dataclass
class GeometryDelta:
    """
    1ステップ分の幾何変化。
    - solid  : 変更後のソリッド
    - removed: 除去されたボリューム（cut の場合）
    - added  : 追加されたボリューム（add の場合）
    """
    solid: cq.Workplane
    removed: Optional[cq.Workplane] = None
    added: Optional[cq.Workplane] = None


def revolve_profile_volume(
    solid: cq.Workplane,
    profile: cq.Workplane,
    angle_deg: float = 360.0,
    mode: Literal["cut", "add"] = "cut",
) -> GeometryDelta:
    """
    2D プロファイルを回転してボリューム化し、solid に対して
    cut / add を行う。new_solid と removed/added ボリュームを返す。

    - profile.revolve() の回転軸/平面は profile 側の Workplane に依存。
    """

    if angle_deg == 0.0:
        # 変化なし
        return GeometryDelta(solid=solid)

    # 回転体ボリューム
    vol = profile.revolve(angle_deg)

    if mode == "cut":
        # 実際に除去される部分は solid と vol の交差部分
        removed = solid.intersect(vol)
        new_solid = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=removed)

    elif mode == "add":
        new_solid = solid.union(vol)
        added = vol
        return GeometryDelta(solid=new_solid, added=added)

    else:
        raise ValueError(f"Unsupported mode: {mode}")
