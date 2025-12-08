# api/process_context.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any
import cadquery as cq

from .csys import CsysDef, build_csys_index
from .geometry.volume_3d import GeometryDelta
from .feature.turn_od_profile import apply_turn_od_profile_geometry, FeatureError

# 必要に応じて他の feature も import:
# from .feature.planar_face import apply_planar_face_geometry
# from .feature.pocket_rectangular import apply_pocket_rectangular_geometry
# ...


@dataclass
class StepRecord:
    """
    1 フィーチャ適用ステップの記録。
    - name      : ログ/ファイル名用のラベル
    - feature   : 元の feature dict（id, params 等）
    - delta     : 幾何差分（GeometryDelta）
    """
    name: str
    feature: Dict[str, Any]
    delta: GeometryDelta


@dataclass
class ProcessContext:
    """
    フィーチャ適用の実行コンテキスト。
    - solid      : 現在のソリッド
    - csys_index : name → CsysDef
    - steps      : 各ステップの GeometryDelta の履歴
    """
    solid: cq.Workplane
    csys_index: Dict[str, CsysDef]
    steps: List[StepRecord] = field(default_factory=list)

    @classmethod
    def from_request(cls, req: Dict[str, Any]) -> "ProcessContext":
        """
        CaseN 風 JSON から初期コンテキストを生成。
        stock / csys_list を解釈して最初の solid / csys_index を作る。
        """
        stock_dict = req.get("stock") or {}
        csys_list = req.get("csys_list") or []

        # Stock を Pydantic モデルに変換してから build_stock を呼ぶ
        from .models import Stock
        from .cad_ops import build_stock
        
        stock_obj = Stock(**stock_dict)
        solid = build_stock(stock_obj)

        csys_index = build_csys_index(csys_list)
        return cls(solid=solid, csys_index=csys_index)

    def apply_feature(self, feature: Dict[str, Any]) -> None:
        """
        単一の feature を解釈して幾何を適用し、steps に GeometryDelta を蓄積。
        """
        ft = feature.get("feature_type")
        fid = feature.get("id", "UNKNOWN")
        name = feature.get("name", fid)

        if ft == "turn_od_profile":
            delta = apply_turn_od_profile_geometry(self.solid, feature, self.csys_index)

        # elif ft == "planar_face":
        #     delta = apply_planar_face_geometry(self.solid, feature, self.csys_index)
        # elif ft == "pocket_rectangular":
        #     delta = apply_pocket_rectangular_geometry(self.solid, feature, self.csys_index)
        else:
            raise FeatureError(f"Unsupported feature_type: {ft}")

        # 次ステップ用 solid を更新
        self.solid = delta.solid

        # 履歴に追加
        self.steps.append(StepRecord(name=name, feature=feature, delta=delta))

    def apply_all_features(self, features: List[Dict[str, Any]]) -> None:
        """
        features 配列を順に適用。
        """
        for feat in features:
            self.apply_feature(feat)
