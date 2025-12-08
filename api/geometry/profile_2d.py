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
    """

    if len(points_zd) < 2:
        raise ValueError("turn_od_profile requires at least 2 points")

    path_points = []
    for p in points_zd:
        z = float(p["z"])
        r = float(p["radius"])
        path_points.append((r, z))  # X = radius, Z = axis direction

    # XZ 平面に 2D polyline プロファイルを作成
    # 回転軸（Z軸）との閉じた領域を作るため、軸上の点を追加
    z_start = path_points[0][1]
    z_end = path_points[-1][1]
    
    # 閉じた形状を作る：プロファイル → 終点のZ軸上 → 始点のZ軸上 → 始点
    closed_points = path_points + [(0, z_end), (0, z_start)]
    
    prof = wp.polyline(closed_points).close()

    # ここで corner R, chamfer などを入れたい場合は、
    # prof = prof.fillet(r) / prof = prof.chamfer(...) などで拡張する。
    return prof
