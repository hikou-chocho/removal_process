# api/geometry/volume_3d.py
from __future__ import annotations
from dataclasses import dataclass

from typing import Optional, Literal, Tuple
import math
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

    vol = profile.revolve(angle_deg)

    if mode == "cut":
        new_solid = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=vol)

    elif mode == "add":
        new_solid = solid.union(vol)
        return GeometryDelta(solid=new_solid, added=vol)

    else:
        raise ValueError(f"Unsupported mode: {mode}")


def extrude_profile_volume(
    solid: cq.Workplane,
    profile: cq.Workplane,
    depth: float,
    mode: Literal["cut", "add"] = "cut",
) -> GeometryDelta:
    """
    2D プロファイルを Workplane のローカル Z 方向に押し出し、
    solid に対して cut / add を行う。

    - depth > 0: ローカル +Z 方向に押し出す
    - depth < 0: ローカル -Z 方向に押し出す
    - depth = 0: 何もしない

    CSYS の回転は Workplane 側にすべて押し込む前提。
    """
    if math.isclose(depth, 0.0, abs_tol=1e-9):
        return GeometryDelta(solid=solid)

    vol = profile.extrude(depth)

    if mode == "cut":
        new_solid = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=vol)

    if mode == "add":
        new_solid = solid.union(vol)
        return GeometryDelta(solid=new_solid, added=vol)

    raise ValueError(f"Unsupported mode: {mode}")


def cylinder_volume_apply(
    solid: cq.Workplane,
    wp: cq.Workplane,
    diameter: float,
    depth: float,
    mode: Literal["cut", "add"] = "cut",
) -> GeometryDelta:
    """
    Workplane 上の円をローカル Z 方向に押し出して円柱ボリュームを作り、
    solid に cut/add する。

    - depth > 0: ローカル +Z 方向に押し出し
    - depth < 0: ローカル -Z 方向に押し出し
    - depth = 0: 変化なし

    CSYS の回転は Workplane 側（wp）にすべて押し込む前提。
    """
    if diameter <= 0.0:
        raise ValueError("diameter must be > 0")
    if math.isclose(depth, 0.0, abs_tol=1e-9):
        return GeometryDelta(solid=solid)

    radius = float(diameter) * 0.5

    vol = wp.circle(radius).extrude(depth)

    if mode == "cut":
        new_solid = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=vol)

    if mode == "add":
        new_solid = solid.union(vol)
        return GeometryDelta(solid=new_solid, added=vol)

    raise ValueError(f"Unsupported mode: {mode}")
