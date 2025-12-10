# api/geometry/volume_3d.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, Tuple
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


def box_volume(
    wp: cq.Workplane,
    size_x: float,
    size_y: float,
    depth: float,
    direction: Tuple[float, float, float],
) -> cq.Workplane:
    """
    Workplane 上に「大きさ size_x × size_y、片側 depth」の
    直方体ボリュームを生成して返す。

    direction の Z 成分の符号で、
    - +Z: Z=0..depth
    - -Z: Z=-depth..0
    になるように配置する。
    """
    if depth <= 0.0:
        raise ValueError("depth must be > 0")

    _, _, nz = direction

    # まず Z=0..depth の箱を作る（centered=(True,True,False)）
    vol = wp.box(
        size_x,
        size_y,
        depth,
        centered=(True, True, False),
    )

    # -Z の場合だけ、全体を -depth シフトして [-depth, 0] に移動する
    if nz < 0.0:
        vol = vol.translate((0.0, 0.0, -depth))

    return vol


def box_volume_apply(
    solid: cq.Workplane,
    wp: cq.Workplane,
    size_x: float,
    size_y: float,
    depth: float,
    direction: Tuple[float, float, float],
    mode: Literal["cut", "add"] = "cut",
) -> GeometryDelta:
    """
    box_volume を使って solid に cut / add を適用し、GeometryDelta を返す。
    planar_face / 単純な矩形段差・ポケットなどから利用する想定。
    """
    vol = box_volume(wp, size_x=size_x, size_y=size_y, depth=depth, direction=direction)

    if mode == "cut":
        new_solid = solid.cut(vol)
        removed = vol
        return GeometryDelta(solid=new_solid, removed=removed)

    elif mode == "add":
        new_solid = solid.union(vol)
        added = vol
        return GeometryDelta(solid=new_solid, added=added)

    else:
        raise ValueError(f"Unsupported mode: {mode}")


def extrude_profile_volume(
    solid: cq.Workplane,
    profile: cq.Workplane,
    depth: float,
    direction: Tuple[float, float, float],
    mode: Literal["cut", "add"] = "cut",
) -> GeometryDelta:
    """
    2D プロファイルを Workplane 法線方向に押し出し、solid に cut/add。
    direction は押し出し符号決定のみに使用。
    """
    if depth <= 0.0:
        raise ValueError("depth must be > 0")

    _, _, nz = direction
    sign = 1.0 if nz >= 0.0 else -1.0

    vol = profile.extrude(sign * depth)

    if mode == "cut":
        new_solid = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=vol)

    elif mode == "add":
        new_solid = solid.union(vol)
        return GeometryDelta(solid=new_solid, added=vol)

    else:
        raise ValueError(f"Unsupported mode: {mode}")


def cylinder_volume_apply(
    solid: cq.Workplane,
    wp: cq.Workplane,
    diameter: float,
    depth: float,
    direction: Tuple[float, float, float],
    mode: Literal["cut", "add"] = "cut",
) -> GeometryDelta:
    """
    Workplane 上の円を押し出して円柱ボリュームを生成し、solid に適用。
    simple_hole / 円形ポケットなどで利用。
    """
    if diameter <= 0.0 or depth <= 0.0:
        raise ValueError("diameter/depth must be > 0")

    radius = float(diameter) * 0.5
    _, _, nz = direction
    sign = 1.0 if nz >= 0.0 else -1.0

    vol = wp.circle(radius).extrude(sign * depth)

    if mode == "cut":
        new_solid = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=vol)

    elif mode == "add":
        new_solid = solid.union(vol)
        return GeometryDelta(solid=new_solid, added=vol)

    else:
        raise ValueError(f"Unsupported mode: {mode}")
