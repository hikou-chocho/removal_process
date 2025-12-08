# api/csys.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Tuple
import cadquery as cq


@dataclass(frozen=True)
class CsysDef:
    name: str
    role: str  # "world" / "setup" / etc.
    origin: Tuple[float, float, float]      # (x, y, z)
    rpy_deg: Tuple[float, float, float]     # (r, p, y) in degrees


def build_csys_index(csys_list: list[dict[str, Any]]) -> Dict[str, CsysDef]:
    """
    CaseN.json の csys_list から CsysDef の辞書を作る。
    """
    index: Dict[str, CsysDef] = {}
    for cs in csys_list:
        name = cs["name"]
        origin = cs.get("origin", {})
        rpy = cs.get("rpy_deg", {})

        index[name] = CsysDef(
            name=name,
            role=cs.get("role", "local"),
            origin=(
                float(origin.get("x", 0.0)),
                float(origin.get("y", 0.0)),
                float(origin.get("z", 0.0)),
            ),
            rpy_deg=(
                float(rpy.get("r", 0.0)),
                float(rpy.get("p", 0.0)),
                float(rpy.get("y", 0.0)),
            ),
        )
    return index


def workplane_from_csys(csys: CsysDef, base_plane: str = "XY") -> cq.Workplane:
    """
    CsysDef から CadQuery Workplane を生成。
    base_plane は "XY" / "XZ" / "YZ" など。

    rpy_deg は「world に対するローカル座標系」の回転として扱う。
    """
    ox, oy, oz = csys.origin
    r, p, y = csys.rpy_deg

    wp = (
        cq.Workplane(base_plane)
        .transformed(
            rotate=(r, p, y),
            offset=(ox, oy, oz),
        )
    )
    return wp
