# api/cad_ops.py (hardened)
from __future__ import annotations
from typing import Tuple, Dict, Any, List, Iterable, Optional
import math
import cadquery as cq
from .models import Operation, Stock

# =========================
# Errors & param utilities
# =========================

class OpError(RuntimeError):
    """User-facing operation error (invalid selector/params, etc.)"""


class CadOpError(Exception):
    """CAD operation error (alias for backward compatibility)"""

def _require_params(p: Dict[str, Any], keys: Iterable[str]) -> None:
    for k in keys:
        if k not in p:
            raise OpError(f"Missing param: '{k}'")
        v = p[k]
        # allow numeric strings; non-finite numeric rejected below on coercion

def _f(v: Any, name: str) -> float:
    try:
        fv = float(v)
    except Exception as ex:
        raise OpError(f"Param '{name}' must be numeric, got {type(v).__name__}") from ex
    if not math.isfinite(fv):
        raise OpError(f"Param '{name}' must be finite")
    return fv

# =========================
# Workplane helpers
# =========================

def _select_faces(work: cq.Workplane, selector: str | None):
    # CadQuery selector string passthrough (e.g., ">Z", "<X", "|Y")
    return work.faces(selector or ">Z")

def _wp_from(work: cq.Workplane, plane: str | None):
    if plane == "YZ":
        return work.workplane(offset=0).transformed(rotate=(0, 90, 0))
    if plane == "ZX":
        return work.workplane(offset=0).transformed(rotate=(90, 0, 0))
    # default XY
    return work.workplane()

def _must_single_planar_face(work: cq.Workplane, selector: str | None) -> cq.Workplane:
    """Reduce selector to a single planar face and return a WP on that face."""
    sel = selector or ">Z"
    try:
        faces = work.faces(sel)
        face_val = faces.val()  # raises if none/ambiguous
    except Exception as ex:
        raise OpError(f"Selector '{sel}' did not resolve to a single planar face") from ex

    # light planarity check
    try:
        gt = face_val.geomType()
        if str(gt).upper() != "PLANE":
            raise OpError(f"Selected face is not planar (geomType={gt})")
    except AttributeError:
        pass

    # Workplane anchored on that face
    try:
        return cq.Workplane(face_val).workplane()
    except Exception as ex:
        raise OpError(f"Failed to create workplane on selected face: {ex}") from ex

# =========================
# stock builders
# =========================

def build_stock(stock: Stock) -> cq.Workplane:
    p = stock.params or {}
    if stock.type == "block":
        _require_params(p, ["w", "d", "h"])
        w = _f(p.get("w", 50), "w")
        d = _f(p.get("d", p.get("l", 50)), "d")  # depth/length
        h = _f(p.get("h", 20), "h")
        # centered in X/Y; extrude in +Z direction
        return cq.Workplane("XY").box(w, d, h, centered=(True, True, False))

    if stock.type == "cylinder":
        _require_params(p, ["dia", "h"])
        dia = _f(p.get("dia", p.get("d", 50)), "dia")
        h   = _f(p.get("h", 50), "h")
        return cq.Workplane("XY").circle(dia / 2.0).extrude(h)

    if stock.type == "mesh":
        # STEP1: import is optional; keep placeholder as block for now
        w = _f(p.get("w", 50), "w")
        d = _f(p.get("d", 50), "d")
        h = _f(p.get("h", 20), "h")
        return cq.Workplane("XY").box(w, d, h, centered=True)

    raise ValueError(f"unsupported stock.type={stock.type}")


# -----------------------------
#  Lathe helpers & ops
# -----------------------------

def _lathe_axis_info(before: cq.Workplane) -> Tuple[float, float, float]:
    """
    旋盤系 op 用の補助情報:
      - zmin, zmax : Z方向の範囲
      - radius     : おおよその外径半径（BoundingBox から推定）
    """
    bb = before.val().BoundingBox()
    zmin, zmax = bb.zmin, bb.zmax
    radius = max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax))
    return zmin, zmax, radius


def _parse_profile_points(op: Operation) -> List[Tuple[float, float]]:
    """
    params.profile から (z_profile, r) のリストを取り出す。
    - z_profile: 心押し側端面からの距離
    - r: 半径 (d/2)

    - z は昇順限定ではない（戻りプロファイルもOK）
    - (z,d) が完全に同じ点が連続するのだけ禁止
    """
    prof = op.params.get("profile")
    if not isinstance(prof, list) or len(prof) < 2:
        raise OpError(f"{op.op}: params.profile は 2 点以上の配列で指定してください。")

    result: List[Tuple[float, float]] = []
    prev_z = None
    prev_d = None

    for i, p in enumerate(prof):
        if not isinstance(p, dict):
            raise OpError(f"{op.op}: profile[{i}] は {{'z':..,'d':..}} 形式で指定してください。")

        try:
            z = float(p["z"])
            d = float(p["d"])
        except KeyError as ex:
            raise OpError(f"{op.op}: profile[{i}] に必須キー {ex} がありません。")
        except Exception as ex:
            raise OpError(f"{op.op}: profile[{i}] の z/d を float に変換できません: {ex}")

        if d <= 0:
            raise OpError(f"{op.op}: profile[{i}].d は正の直径を指定してください。")

        # 同一点連続だけ禁止（同じ z で d が変わる＝垂直壁は OK）
        if prev_z is not None and prev_d is not None:
            if z == prev_z and d == prev_d:
                raise OpError(
                    f"{op.op}: profile[{i-1}] と profile[{i}] が同一座標です (z={z}, d={d})。"
                )

        prev_z, prev_d = z, d
        r = d / 2.0
        result.append((z, r))

    return result


def _profile_to_world(
    before: cq.Workplane, profile_zr: List[Tuple[float, float]]
) -> Tuple[List[Tuple[float, float]], float, float, float]:
    """
    (z_profile, r) → (z_world, r) に変換。
    心押し側端面 = zmin とみなして:
      z_world = zmin + z_profile
    """
    zmin, zmax, stock_r = _lathe_axis_info(before)

    mapped: List[Tuple[float, float]] = []
    for (z_profile, r) in profile_zr:
        z_world = zmin + z_profile
        mapped.append((z_world, r))

    return mapped, zmin, zmax, stock_r


def _dedupe_points(points: List[cq.Vector]) -> List[cq.Vector]:
    """
    連続する同一座標の点を削除（0長さエッジを避ける）
    """
    if not points:
        return points

    deduped = [points[0]]
    for p in points[1:]:
        last = deduped[-1]
        if (abs(p.x - last.x) > 1e-9) or (abs(p.y - last.y) > 1e-9) or (abs(p.z - last.z) > 1e-9):
            deduped.append(p)
    return deduped


def _make_profile_solid(
    before: cq.Workplane,
    op: Operation,
) -> cq.Solid:
    """
    params.profile から、Z軸まわりの回転体ソリッドを生成する。
    - XZ 平面上で、
        (r, z_world) の polyline + 軸(r=0) で 2D ループを作り、
      それを Z 軸まわりに 360° 回転。
    """
    profile_zr = _parse_profile_points(op)
    mapped, zmin, zmax, stock_r = _profile_to_world(before, profile_zr)

    z_vals = [zw for (zw, _) in mapped]

    # XZ 平面上に 2D ループを作る
    #   - outer: プロファイル r(z)
    #   - inner: 軸 r=0 側で閉じる
    outer_pts = [cq.Vector(r, z, 0.0) for (z, r) in mapped]
    inner_pts = [cq.Vector(0.0, z, 0.0) for z in reversed(z_vals)]

    outer_pts = _dedupe_points(outer_pts)
    inner_pts = _dedupe_points(inner_pts)

    if len(outer_pts) < 2 or len(inner_pts) < 2:
        raise OpError(f"{op.op}: 有効なプロファイル点が不足しています。")

    wp = cq.Workplane("XZ")
    wire = (
        wp.polyline(outer_pts)
          .polyline(inner_pts)
          .close()
    )

    # ★ここを修正：XZ ワークプレーン上で Z 軸まわりに回転させる
    #   axisStart/axisEnd は Workplane ローカル座標で指定するので
    #   「(0,0,0) → (0,1,0)」が world Z 軸に対応する
    profile_wp = wire.revolve(360.0, (0, 0, 0), (0, 1, 0))
    profile_solid = profile_wp.val()

    return profile_solid


def _op_lathe_face_cut(before: cq.Workplane, op: Operation) -> cq.Workplane:
    depth = _f(op.params.get("depth", 0), "depth")
    if depth <= 0:
        raise OpError("lathe:face_cut depth must be positive")

    wp = _must_single_planar_face(before, ">Z")

    _, _, radius = _lathe_axis_info(before)
    cut_solid = wp.circle(radius * 1.2).extrude(-abs(depth))
    after = before.cut(cut_solid)
    return after


def _op_lathe_turn_od(before: cq.Workplane, op: Operation) -> cq.Workplane:
    target_dia = _f(op.params.get("target_dia", 0), "target_dia")
    length = _f(op.params.get("length", 0), "length")

    if target_dia <= 0:
        raise OpError("lathe:turn_od target_dia must be positive")
    if length <= 0:
        raise OpError("lathe:turn_od length must be positive")

    zmin, zmax, radius = _lathe_axis_info(before)
    total_len = zmax - zmin
    if length > total_len:
        raise OpError(f"lathe:turn_od length={length} exceeds total length {total_len}")

    stock_r = radius
    target_r = target_dia / 2.0
    if target_r >= stock_r:
        raise OpError("lathe:turn_od target_dia must be smaller than current stock diameter")

    z_start = zmax - length

    outer = (
        cq.Workplane("XY")
        .workplane(offset=z_start)
        .circle(stock_r * 1.05)
        .extrude(length)
    )
    inner = (
        cq.Workplane("XY")
        .workplane(offset=z_start)
        .circle(target_r)
        .extrude(length)
    )
    cut_shell = outer.cut(inner)
    after = before.cut(cut_shell)
    return after


def _op_lathe_bore_id(before: cq.Workplane, op: Operation) -> cq.Workplane:
    target_dia = _f(op.params.get("target_dia", 0), "target_dia")
    length = _f(op.params.get("length", 0), "length")

    if target_dia <= 0:
        raise OpError("lathe:bore_id target_dia must be positive")
    if length <= 0:
        raise OpError("lathe:bore_id length must be positive")

    zmin, zmax, radius = _lathe_axis_info(before)
    total_len = zmax - zmin
    if length > total_len:
        raise OpError(f"lathe:bore_id length={length} exceeds total length {total_len}")

    target_r = target_dia / 2.0
    if target_r >= radius:
        raise OpError("lathe:bore_id target_dia must be smaller than stock outer diameter")

    z_start = zmax - length
    cut_solid = (
        cq.Workplane("XY")
        .workplane(offset=z_start)
        .circle(target_r)
        .extrude(length)
    )
    after = before.cut(cut_solid)
    return after


def _op_lathe_turn_od_profile(before: cq.Workplane, op: Operation) -> cq.Workplane:
    """
    外径プロファイル加工 (Phase1: polyline ベース)

    params.profile: [
      { "z": <float>, "d": <float> },
      ...
    ]
    - z: 心押し側端面からの距離
    - d: 仕上がり直径
    """
    profile_zr = _parse_profile_points(op)
    mapped, zmin, zmax, stock_r = _profile_to_world(before, profile_zr)

    # ストック外に出ていないかチェック
    for i, (z_world, r) in enumerate(mapped):
        if r > stock_r + 1e-6:
            raise OpError(
                f"{op.op}: profile[{i}] の半径 r={r} が現在の外径 {stock_r} を超えています。"
            )

    profile_solid = _make_profile_solid(before, op)

    # 仕上がり形状 = 現在のワーク ∩ プロファイル回転体
    after = before.intersect(profile_solid)
    return after


def _op_lathe_bore_id_profile(before: cq.Workplane, op: Operation) -> cq.Workplane:
    """
    内径プロファイル加工 (Phase1: polyline ベース)

    params.profile: [
      { "z": <float>, "d": <float> },
      ...
    ]
    - z: 心押し側端面からの距離
    - d: 仕上がり直径
    """
    profile_zr = _parse_profile_points(op)
    mapped, zmin, zmax, stock_r = _profile_to_world(before, profile_zr)

    # 外径を超えていないかチェック
    for i, (z_world, r) in enumerate(mapped):
        if r >= stock_r - 1e-6:
            raise OpError(
                f"{op.op}: profile[{i}] の半径 r={r} が外径 {stock_r} 以上です。"
            )

    profile_solid = _make_profile_solid(before, op)

    # 内径 = 現在のワークから穴ソリッドをくり抜く
    after = before.cut(profile_solid)
    return after

# =========================
# operation appliers
# =========================

def apply_op(before: cq.Workplane, op: Operation) -> Tuple[cq.Workplane, cq.Workplane]:
    """
    Returns (after, removed)
      solid  = after
      removed= before - after
    """
    if before is None:
        raise OpError("No stock solid. First operation must build stock")

    name = op.op
    params = op.params or {}
    selector = op.selector or ">Z"

    after = before

    try:
        if name == "mill:face":
            # Face mill: cut a large rectangle covering the selected face by depth
            _require_params(params, ["depth"])
            depth = _f(params.get("depth", 1.0), "depth")
            # locate a single planar face and workplane on it
            wp = _must_single_planar_face(before, selector)

            # bounding box from before (support different bbox attribute names)
            bb = before.val().BoundingBox()
            try:
                width = bb.xlen * 1.1
                height = bb.ylen * 1.1
            except Exception:
                width = (bb.xmax - bb.xmin) * 1.1
                height = (bb.ymax - bb.ymin) * 1.1

            try:
                cut_solid = wp.rect(width, height).extrude(-abs(depth))
                after = before.cut(cut_solid)
            except ValueError as vex:
                raise OpError(f"mill:face failed during cut: {vex}")
            except Exception as ex:
                raise OpError(f"mill:face failed: {ex}")

        elif name == "mill:profile":
            # rectangular pocket cut on selected face
            _require_params(params, ["rect_w", "rect_h", "depth"])
            rect_w = _f(params.get("rect_w", 10), "rect_w")
            rect_h = _f(params.get("rect_h", 10), "rect_h")
            depth  = _f(params.get("depth", 1.0), "depth")

            if rect_w <= 0 or rect_h <= 0:
                raise OpError("rect_w, rect_h must be positive")
            if depth == 0:
                raise OpError("depth must be non-zero")

            wp = _must_single_planar_face(before, selector)
            try:
                cut_solid = wp.rect(rect_w, rect_h).extrude(-abs(depth))
                after = before.cut(cut_solid)
            except ValueError as vex:
                raise OpError(f"mill:profile failed during cut: {vex}")
            except Exception as ex:
                raise OpError(f"mill:profile failed: {ex}")

        elif name == "drill:hole":
            # simple through/partial hole implemented as a negative cylinder
            _require_params(params, ["dia", "depth"])
            dia   = _f(params.get("dia", 5), "dia")
            depth = _f(params.get("depth", 5), "depth")
            x     = _f(params.get("x", 0), "x")
            y     = _f(params.get("y", 0), "y")

            if dia <= 0:
                raise OpError("dia must be positive")
            if depth == 0:
                raise OpError("depth must be non-zero")

            wp = _must_single_planar_face(before, selector)
            try:
                cut_solid = wp.center(x, y).circle(dia / 2.0).extrude(-abs(depth))
                after = before.cut(cut_solid)
            except ValueError as vex:
                raise OpError(f"drill:hole failed during cut: {vex}")
            except Exception as ex:
                raise OpError(f"drill:hole failed: {ex}")

        elif name == "lathe:face_cut":
            after = _op_lathe_face_cut(before, op)

        elif name == "lathe:turn_od":
            after = _op_lathe_turn_od(before, op)

        elif name == "lathe:bore_id":
            after = _op_lathe_bore_id(before, op)

        elif name == "lathe:turn_od_profile":
            after = _op_lathe_turn_od_profile(before, op)

        elif name == "lathe:bore_id_profile":
            after = _op_lathe_bore_id_profile(before, op)

        elif name == "xform:transform":
            dx = _f(params.get("dx", 0), "dx")
            dy = _f(params.get("dy", 0), "dy")
            dz = _f(params.get("dz", 0), "dz")
            after = before.translate((dx, dy, dz))

        else:
            raise ValueError(f"unsupported op: {name}")

        # removed = before - after
        try:
            removed = before.cut(after)
        except Exception:
            # In rare degenerate cases cut may fail; degrade gracefully with empty removal
            removed = before

        return after, removed

    except OpError:
        raise
    except ValueError:
        # bubble up unsupported errors
        raise
    except Exception as ex:
        # normalize unexpected exceptions into OpError for clarity
        raise OpError(f"{name} failed: {ex}") from ex

# 旧版: faces(selector)→val()→workplane() を安全化
def _wp_on_single_face(work: cq.Workplane, selector: str | None):
    # Backward-compatible alias kept for callers; delegates to safer impl
    return _must_single_planar_face(work, selector)
