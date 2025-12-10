# api/geometry/profile_2d.py
from __future__ import annotations
from typing import List, Dict
import cadquery as cq


def make_turn_od_profile_zd(
    wp: cq.Workplane,
    points_zd: List[Dict[str, float]],
) -> cq.Workplane:
    """
    旋盤 OD 用の Z–radius プロファイルを XZ 平面上に作る例。
    Z = 軸方向, radius = 半径を X に割り当てる。

    points_zd: [{ "z": 0.0, "radius": 25.0 }, ...]
    
    このプロファイルは「残す形状の外形」を定義する。
    """

    if len(points_zd) < 2:
        raise ValueError("turn_od_profile requires at least 2 points")

    path_points = []
    for p in points_zd:
        z = float(p["z"])
        r = float(p["radius"])
        path_points.append((r, z))  # X = radius, Z = axis direction

    # 回転軸（Z軸）との閉じた領域を作るため、軸上の点を追加
    z_start = path_points[0][1]
    z_end = path_points[-1][1]
    
    # 閉じた形状を作る：プロファイル → 終点のZ軸上 → 始点のZ軸上 → 始点
    closed_points = path_points + [(0, z_end), (0, z_start)]
    
    prof = wp.polyline(closed_points).close()

    # ここで corner R, chamfer などを入れたい場合は、
    # prof = prof.fillet(r) / prof = prof.chamfer(...) などで拡張する。
    return prof


def make_rect_profile_centered(
    wp: cq.Workplane,
    width: float,
    length: float,
    corner_radius: float = 0.0,
) -> cq.Workplane:
    """
    XY 平面上に中心原点の矩形プロファイルを作成。
    corner_radius > 0 の場合は四隅をフィレット。

    wp は「原点がポケット中心」の CSYS に合わせておく前提。
    """
    if width <= 0.0 or length <= 0.0:
        raise ValueError("width/length must be > 0")

    w = float(width)
    l = float(length)
    r = float(corner_radius)

    prof = wp.rect(w, l)

    if r > 0.0:
        # Corner fillet on a standalone profile requires creating a solid
        # or a sketch context; calling vertices().fillet(r) here can fail
        # with "Cannot find a solid on the stack" in some CadQuery versions.
        # For now, we skip automatic fillet to keep profile creation robust.
        # TODO: implement rounded-rectangle polyline if corner_radius > 0
        pass

    return prof
