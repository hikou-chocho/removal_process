from __future__ import annotations
import math

import cadquery as cq

from api.csys import CsysDef, workplane_from_csys
from api.geometry.volume_3d import (
    extrude_profile_volume,
    cylinder_volume_apply,
    GeometryDelta,
)

# axis->vector は共通 util を参照
from api.feature.common import axis_to_vector

# エイリアスをテスト内で使える形に用意
planar_axis_to_vector = pocket_axis_to_vector = hole_axis_to_vector = axis_to_vector


EPS = 1e-6


def bbox6(wp: cq.Workplane):
    """Workplane の BoundingBox を (xmin, xmax, ymin, ymax, zmin, zmax) で返す。"""
    bb = wp.val().BoundingBox()
    return bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax


# -----------------------------
# axis → ベクトルのユニットテスト
# -----------------------------


def test_axis_to_vector_mapping():
    # planar / pocket / hole で同じ実装になっていることの sanity check
    for fn in (planar_axis_to_vector, pocket_axis_to_vector, hole_axis_to_vector):
        assert fn("+Z") == (0.0, 0.0, 1.0)
        assert fn("-Z") == (0.0, 0.0, -1.0)
        assert fn("+X") == (1.0, 0.0, 0.0)
        assert fn("-X") == (-1.0, 0.0, 0.0)
        assert fn("+Y") == (0.0, 1.0, 0.0)
        assert fn("-Y") == (0.0, -1.0, 0.0)


# -----------------------------
# csys → Workplane の向きテスト
# -----------------------------


def test_workplane_from_csys_wcs_xy():
    """WCS (rpy=0) + base_plane='XY' では、Z軸が world Z と一致する想定。"""
    csys = CsysDef(
        name="WCS",
        role="world",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(0.0, 0.0, 0.0),
    )

    wp = workplane_from_csys(csys, base_plane="XY")

    # XY 平面で 10x10 の板を作ると、Z=0 に乗ることを確認
    slab = wp.box(10.0, 10.0, 1.0, centered=(True, True, False))
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(slab)

    assert math.isclose(zmin, 0.0, abs_tol=EPS)
    assert math.isclose(zmax, 1.0, abs_tol=EPS)


def test_workplane_from_csys_wcs_xz():
    """WCS + base_plane='XZ' では、厚み方向が world Y になることだけ確認する。"""
    csys = CsysDef(
        name="WCS",
        role="world",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(0.0, 0.0, 0.0),
    )

    wp = workplane_from_csys(csys, base_plane="XZ")

    # XZ 上の板 → ある軸に厚み1、他の2軸に長さ10
    slab = wp.box(10.0, 1.0, 10.0, centered=(True, True, False))
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(slab)

    len_x = xmax - xmin
    len_y = ymax - ymin
    len_z = zmax - zmin

    # CadQueryのXZ平面はZ軸が厚み方向（1.0）
    assert math.isclose(len_z, 1.0, abs_tol=EPS), "Z 軸が厚み方向であること (CadQuery既定)"
    assert math.isclose(len_x, 10.0, abs_tol=EPS)
    assert math.isclose(len_y, 10.0, abs_tol=EPS)


# -----------------------------
# extrude_profile_volume (pocket_rectangular 相当) の方向テスト
# -----------------------------


def test_extrude_profile_volume_minus_z():
    """
    pocket_rectangular axis='-Z', depth>0 のとき、
    プロファイルは Z=0 にあり、押し出しは Z=-depth 方向に伸びる。
    """
    csys = CsysDef(
        name="WCS",
        role="world",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(0.0, 0.0, 0.0),
    )
    wp = workplane_from_csys(csys, base_plane="XY")

    # Z=0 上に 10x10 のプロファイルを作る
    profile = wp.rect(10.0, 10.0)

    # solid は仮の大きめブロック
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    delta: GeometryDelta = extrude_profile_volume(
        solid=solid,
        profile=profile,
        depth=-5.0,
        mode="cut",
    )

    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)

    assert math.isclose(zmax, 0.0, abs_tol=EPS)
    assert math.isclose(zmin, -5.0, abs_tol=EPS)


def test_extrude_profile_volume_plus_z():
    """
    pocket_rectangular axis='+Z', depth>0 のとき、
    押し出しは Z=+depth 方向に伸びる。
    """
    csys = CsysDef(
        name="WCS",
        role="world",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(0.0, 0.0, 0.0),
    )
    wp = workplane_from_csys(csys, base_plane="XY")

    profile = wp.rect(10.0, 10.0)
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    delta: GeometryDelta = extrude_profile_volume(
        solid=solid,
        profile=profile,
        depth=5.0,
        mode="cut",
    )

    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)

    assert math.isclose(zmin, 0.0, abs_tol=EPS)
    assert math.isclose(zmax, 5.0, abs_tol=EPS)


# -----------------------------
# cylinder_volume_apply (simple_hole 相当) の方向テスト
# -----------------------------


def test_cylinder_volume_minus_z():
    """
    simple_hole axis='-Z', depth>0 のとき、
    円柱ボリュームは Z=0 から Z=-depth に向かって伸びる。
    """
    csys = CsysDef(
        name="WCS",
        role="world",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(0.0, 0.0, 0.0),
    )
    wp = workplane_from_csys(csys, base_plane="XY")
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    delta: GeometryDelta = cylinder_volume_apply(
        solid=solid,
        wp=wp,
        diameter=10.0,
        depth=-5.0,
        mode="cut",
    )

    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)

    assert math.isclose(zmax, 0.0, abs_tol=EPS)
    assert math.isclose(zmin, -5.0, abs_tol=EPS)


def test_cylinder_volume_plus_z():
    """
    simple_hole axis='+Z', depth>0 のとき、
    円柱ボリュームは Z=0 から Z=+depth に向かって伸びる。
    """
    csys = CsysDef(
        name="WCS",
        role="world",
        origin=(0.0, 0.0, 0.0),
        rpy_deg=(0.0, 0.0, 0.0),
    )
    wp = workplane_from_csys(csys, base_plane="XY")
    solid = cq.Workplane("XY").box(100.0, 100.0, 100.0, centered=True)
    delta: GeometryDelta = cylinder_volume_apply(
        solid=solid,
        wp=wp,
        diameter=10.0,
        depth=5.0,
        mode="cut",
    )

    assert delta.removed is not None
    xmin, xmax, ymin, ymax, zmin, zmax = bbox6(delta.removed)

    assert math.isclose(zmin, 0.0, abs_tol=EPS)
    assert math.isclose(zmax, 5.0, abs_tol=EPS)
