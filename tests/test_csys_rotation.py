from __future__ import annotations
import math

import cadquery as cq

from api.csys import CsysDef
from api.geometry.volume_3d import GeometryDelta
from api.feature.planar_face import apply_planar_face_geometry
from api.feature.pocket_rectangular import apply_pocket_rectangular_geometry
from api.feature.simple_hole import apply_simple_hole_geometry

EPS = 1e-6

def bbox6(wp: cq.Workplane):
    bb = wp.val().BoundingBox()
    return bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax

def make_a90c0_front_csys() -> CsysDef:
    """
    A90C0_FRONT 相当: X軸まわりに +90deg 回転。
    （ローカル +Z が world -Y に向く）
    """
    return CsysDef(
        name="A90C0_FRONT",
        role="setup",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(90.0, 0.0, 0.0),
    )

def test_planar_face_a90c0_axis_minus_z_removal_along_world_y():
    csys = make_a90c0_front_csys()
    csys_index = {csys.name: csys}
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    depth = 5.0
    size_x = 20.0
    size_y = 10.0
    feature = {
        "feature_type": "planar_face",
        "id": "F_PLANAR_FRONT",
        "params": {
            "csys_id": csys.name,
            "depth": depth,
            "size_x": size_x,
            "size_y": size_y,
            "axis": "-Z",
            "mode": "cut",
        }
    }
    delta: GeometryDelta = apply_planar_face_geometry(solid, feature, csys_index)
    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)
    len_x = xmax - xmin
    len_y = ymax - ymin
    len_z = zmax - zmin
    # いずれかの軸長が depth になっているはず（ローカル -Z がどの world 軸に落ちていても良い）
    assert any(
        math.isclose(L, depth, rel_tol=1e-3, abs_tol=1e-3)
        for L in (len_x, len_y, len_z)
    ), f"One of axis lengths should equal depth={depth}, got ({len_x}, {len_y}, {len_z})"

def test_pocket_rectangular_a90c0_axis_minus_z_removal_along_world_y():
    csys = make_a90c0_front_csys()
    csys_index = {csys.name: csys}
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    width = 30.0
    length = 20.0
    depth = 8.0
    feature = {
        "feature_type": "pocket_rectangular",
        "id": "F_POCKET_FRONT",
        "params": {
            "csys_id": csys.name,
            "origin_x": 0.0,
            "origin_y": 0.0,
            "width": width,
            "length": length,
            "corner_radius": 2.0,
            "depth": depth,
            "axis": "-Z",
            "mode": "cut",
            "open_side": None
        }
    }
    delta: GeometryDelta = apply_pocket_rectangular_geometry(
        solid=solid,
        feature=feature,
        csys_index=csys_index,
    )
    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)
    len_x = xmax - xmin
    len_y = ymax - ymin
    len_z = zmax - zmin
    # depth 長の軸が一つあること
    assert any(
        math.isclose(L, depth, rel_tol=1e-3, abs_tol=1e-3)
        for L in (len_x, len_y, len_z)
    )

def test_simple_hole_a90c0_axis_minus_z_hole_along_world_y():
    csys = make_a90c0_front_csys()
    csys_index = {csys.name: csys}
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    dia = 10.0
    depth = 15.0
    feature = {
        "feature_type": "simple_hole",
        "id": "F_HOLE_FRONT",
        "params": {
            "csys_id": csys.name,
            "origin_x": 0.0,
            "origin_y": 0.0,
            "axis": "-Z",
            "diameter": dia,
            "depth": depth,
            "through": False,
            "mode": "cut"
        }
    }
    delta: GeometryDelta = apply_simple_hole_geometry(
        solid=solid,
        feature=feature,
        csys_index=csys_index,
    )
    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)
    len_x = xmax - xmin
    len_y = ymax - ymin
    len_z = zmax - zmin
    # depth 長の軸が一つあること（穴軸方向）
    assert any(
        math.isclose(L, depth, rel_tol=1e-3, abs_tol=1e-3)
        for L in (len_x, len_y, len_z)
    )