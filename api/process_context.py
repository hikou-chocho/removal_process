# api/process_context.py
from __future__ import annotations
from typing import Dict, Any, Optional, Iterable, Tuple
import logging

import cadquery as cq

from .models import PipelineRequest, Operation
from .cad_ops import build_stock, apply_op, OpError

logger = logging.getLogger("pipeline.process")


class ProcessContext:
    """
    パイプライン実行中の「加工プロセス状態」を持つコンテキスト。

    - 現在の work（ワーク形状）
    - 直近の removed（除去形状）
    - csys_list / current_csys の管理
    - setup:index 等、工程レベルの op の解釈
    - cad_ops.apply_op を呼び出してジオメトリを更新

    ※CSYS の幾何学的な反映（ワーク回転など）は、Step2 では未実装。
      まずは「current_csys を覚える」「unknown CSYS をエラーにする」まで。
    """

    def __init__(self, req: PipelineRequest) -> None:
        self.req: PipelineRequest = req

        # --- ワーク形状 ---
        # ここで stock build に失敗した場合は OpError / Exception をそのまま外に投げる。
        self.work: cq.Workplane = build_stock(req.stock)
        self.removed: Optional[cq.Workplane] = None

        # --- CSYS 管理 ---
        # csys_list はまだモデルにないかもしれないので getattr で安全に取得。
        raw_csys_list = getattr(req, "csys_list", None)
        self.csys_map: Dict[str, Any] = self._build_csys_map(raw_csys_list)
        self.current_csys: str = "WCS"  # デフォルト CSYS 名

        # --- 実行状態 ---
        self.step_index: int = 0  # 1 始まりのステップ番号（apply_operation 呼び出しごとに +1）

    # -----------------------------
    # CSYS ヘルパ
    # -----------------------------
    def _build_csys_map(self, csys_list: Optional[Iterable[Any]]) -> Dict[str, Any]:
        """
        req.csys_list から name -> CSYS 定義 の辞書を作る。
        要素は Pydantic モデルでも dict でも良い前提で、name の取り方をゆるくしている。
        """
        csys_map: Dict[str, Any] = {}

        if not csys_list:
            # csys_list が無い場合でも "WCS" は一応定義しておく
            csys_map["WCS"] = None
            return csys_map

        for csys in csys_list:
            name = None
            # Pydantic モデル想定: csys.name
            if hasattr(csys, "name"):
                name = getattr(csys, "name")
            # dict 想定: csys["name"]
            elif isinstance(csys, dict):
                name = csys.get("name")

            if not name:
                logger.warning("CSYS entry without name is ignored: %r", csys)
                continue

            csys_map[name] = csys

        # WCS がなければ追加
        if "WCS" not in csys_map:
            csys_map["WCS"] = None

        return csys_map

    # -----------------------------
    # メイン API
    # -----------------------------
    def apply_operation(self, op: Operation) -> Tuple[cq.Workplane, Optional[cq.Workplane]]:
        """
        1 つの Operation を適用し、(work, removed) を返す。

        - setup:index など CSYS 系 op は _apply_setup_index で処理
        - それ以外は cad_ops.apply_op に委譲
        """
        self.step_index += 1

        if op.op == "setup:index":
            self._apply_setup_index(op)
            # setup:index 自体は幾何を変えない（Step2 初期段階）
            # removed も None のままにしておく
            return self.work, self.removed

        # 通常のジオメトリ op
        self.work, self.removed = apply_op(self.work, op)
        return self.work, self.removed

    # -----------------------------
    # CSYS 関連 op
    # -----------------------------
    def _apply_setup_index(self, op: Operation) -> None:
        """
        割り出し op:
        - 今は「current_csys の更新」のみを行う。
        - 将来的にここでワークの回転などを行う余地を残す。
        """
        # csys_ref の持ち方はモデル次第なので、属性と params 両方を見ておく
        csys_ref = getattr(op, "csys_ref", None)
        if csys_ref is None:
            # params 側に埋められている場合も一応見る
            params = op.params or {}
            csys_ref = params.get("csys_ref")

        target = csys_ref or "WCS"

        if target not in self.csys_map:
            raise OpError(f"Unknown CSYS name: '{target}'")

        logger.info(
            "STEP %02d setup:index -> csys_ref=%s (prev=%s)",
            self.step_index,
            target,
            self.current_csys,
        )
        self.current_csys = target
        # 幾何学的な変換はまだ行わない（Step2 の後半で実装予定）

    # -----------------------------
    # 補助的なアクセサ
    # -----------------------------
    def get_current_solids(self) -> Tuple[cq.Workplane, Optional[cq.Workplane]]:
        """
        現在のワーク形状と直近の除去形状を返す。
        """
        return self.work, self.removed
