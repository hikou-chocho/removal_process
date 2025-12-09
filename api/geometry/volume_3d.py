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
    
    旋盤加工の場合:
    - プロファイルは「残す形状の外形」を定義
    - mode="cut" の場合、プロファイル形状との交差が new_solid、差分が removed
    """

    if angle_deg == 0.0:
        # 変化なし
        return GeometryDelta(solid=solid)

    # 回転体ボリューム
    vol = profile.revolve(angle_deg)

    if mode == "cut":
        # プロファイルは「残す形状」を定義
        # new_solid = プロファイル形状との交差（残る部分）
        # removed = 元の solid から new_solid を引いた部分（削られる部分）
        new_solid = solid.intersect(vol)
        removed = solid.cut(vol)
        return GeometryDelta(solid=new_solid, removed=removed)

    elif mode == "add":
        new_solid = solid.union(vol)
        added = vol
        return GeometryDelta(solid=new_solid, added=added)

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

    direction は「depth をどちら側に伸ばすか」を決めるために使い、
    ここでは単純に Z 成分の符号で前後を決める。
    """
    if depth <= 0.0:
        raise ValueError("depth must be > 0")

    _, _, nz = direction
    sign = 1.0 if nz >= 0.0 else -1.0

    vol = (
        wp.box(
            size_x,
            size_y,
            depth,
            centered=(True, True, False),  # XY 中心、Z 片側
        )
        .translate((0.0, 0.0, sign * depth / 2.0))
    )
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
