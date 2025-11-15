# api/cad_ops.py (hardened)
from __future__ import annotations
from typing import Tuple, Dict, Any, Iterable, Optional
import math
import cadquery as cq
from .models import Operation, Stock

# =========================
# Errors & param utilities
# =========================

class OpError(RuntimeError):
    """User-facing operation error (invalid selector/params, etc.)"""

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
        # centered in X/Y; rise in +Z by half-height to keep top at +h/2
        return cq.Workplane("XY").box(w, d, h, centered=True)

    if stock.type == "cylinder":
        _require_params(p, ["dia", "h"])
        dia = _f(p.get("dia", p.get("d", 50)), "dia")
        h   = _f(p.get("h", 50), "h")
        return cq.Workplane("XY").circle(dia / 2.0).extrude(h, both=True)

    if stock.type == "mesh":
        # STEP1: import is optional; keep placeholder as block for now
        w = _f(p.get("w", 50), "w")
        d = _f(p.get("d", 50), "d")
        h = _f(p.get("h", 20), "h")
        return cq.Workplane("XY").box(w, d, h, centered=True)

    raise ValueError(f"unsupported stock.type={stock.type}")

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
            depth = _f(params.get("depth", 1.0), "depth")
            wp = _must_single_planar_face(before, ">Z")
            after = wp.cutBlind(-depth)

        elif name == "lathe:turn_od":
            dia = _f(params.get("dia", 40), "dia")
            bb = before.val().BoundingBox()
            length = bb.zlen
            shell = (
                cq.Workplane("ZX")
                .circle(dia / 2.0)
                .extrude(length, both=True)
                .translate((0, 0, bb.zmin + length / 2.0))
            )
            after = before.intersect(shell)

        elif name == "lathe:bore_id":
            dia = _f(params.get("dia", 20), "dia")
            bb = before.val().BoundingBox()
            length = bb.zlen
            core = (
                cq.Workplane("ZX")
                .circle(dia / 2.0)
                .extrude(length, both=True)
                .translate((0, 0, bb.zmin + length / 2.0))
            )
            after = before.cut(core)

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
