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
    - setups / current_setup_id の管理
    - setup:index 等、工程レベルの op の解釈
    - cad_ops.apply_op を呼び出してジオメトリを更新

    Strategy A（ワークを world で回す）:
      - self.work は常に「canonical world 姿勢」で保持する
      - 各 Operation 実行時だけ、一時的に setup.orientation で回転してから apply_op
      - 結果は逆回転して self.work（world 姿勢）に戻す
    """

    def __init__(self, req: PipelineRequest) -> None:
        self.req: PipelineRequest = req

        # --- ワーク形状 ---
        # ここで stock build に失敗した場合は OpError / Exception をそのまま外に投げる。
        self.work: cq.Workplane = build_stock(req.stock)
        self.removed: Optional[cq.Workplane] = None

        # --- Setup 管理 ---
        # req.setups は無い場合もあるので getattr で安全に取得。
        raw_setups = getattr(req, "setups", None)
        self.setup_map: Dict[str, Any] = self._build_setup_map(raw_setups)
        # 現在の setup（setup:index で切り替え）。None の場合は「素の world 姿勢」。
        self.current_setup_id: Optional[str] = None

        # --- 実行状態 ---
        self.step_index: int = 0  # 1 始まりのステップ番号（apply_operation 呼び出しごとに +1）
        # Debug: dump the parsed request to output for inspection
        try:
            import json, os
            outp = os.path.join(os.path.dirname(__file__), '..', 'data', 'output', 'debug_req.json')
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            with open(outp, 'w', encoding='utf-8') as fh:
                # PipelineRequest may be Pydantic; try .dict() then fallback to str(req)
                try:
                    d = req.dict()
                except Exception:
                    try:
                        d = dict(req)
                    except Exception:
                        d = str(req)
                json.dump(d, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # -----------------------------
    # Setup ヘルパ
    # -----------------------------
    def _build_setup_map(self, setups: Optional[Iterable[Any]]) -> Dict[str, Any]:
        """
        req.setups から id -> Setup 定義 の辞書を作る。
        要素は Pydantic モデルでも dict でも良い前提で、id の取り方をゆるくしている。
        """
        setup_map: Dict[str, Any] = {}

        if not setups:
            return setup_map

        for setup in setups:
            setup_id = None
            # Pydantic モデル想定: setup.id
            if hasattr(setup, "id"):
                setup_id = getattr(setup, "id")
            # dict 想定: setup["id"]
            elif isinstance(setup, dict):
                setup_id = setup.get("id")

            if not setup_id:
                logger.warning("Setup entry without id is ignored: %r", setup)
                continue

            setup_map[setup_id] = setup

        return setup_map

    # orientation 抜き出し（rx_deg, ry_deg, rz_deg）を返す
    def _get_orientation_deg(self, setup: Any) -> Tuple[float, float, float]:
        if setup is None:
            return 0.0, 0.0, 0.0

        # setup.orientation を想定（Pydantic or dict）
        ori = None
        if hasattr(setup, "orientation"):
            ori = getattr(setup, "orientation")
        elif isinstance(setup, dict):
            ori = setup.get("orientation")

        if ori is None:
            return 0.0, 0.0, 0.0

        def _get(obj: Any, name: str, default: float = 0.0) -> float:
            if hasattr(obj, name):
                v = getattr(obj, name)
            elif isinstance(obj, dict):
                v = obj.get(name, default)
            else:
                v = default
            try:
                return float(v)
            except Exception:
                return default

        rx = _get(ori, "rx_deg", 0.0)
        ry = _get(ori, "ry_deg", 0.0)
        rz = _get(ori, "rz_deg", 0.0)
        return rx, ry, rz

    # Workplane を orientation で回転／逆回転する
    def _apply_orientation(
        self,
        wp: Optional[cq.Workplane],
        orientation_deg: Tuple[float, float, float],
        forward: bool = True,
    ) -> Optional[cq.Workplane]:
        """
        orientation_deg = (rx, ry, rz) [deg]

        forward=True  のとき: world -> setup 姿勢に回転
        forward=False のとき: setup -> world（逆回転）

        今は world 原点 (0,0,0) 回りに X→Y→Z の順で回転させる簡易版。
        割り出し 5 軸の 90° 単位ではこれで十分と割り切る。
        """
        if wp is None:
            return None

        rx, ry, rz = orientation_deg
        if rx == 0.0 and ry == 0.0 and rz == 0.0:
            return wp

        sign = 1.0 if forward else -1.0
        rx *= sign
        ry *= sign
        rz *= sign

        result = wp
        if rx != 0.0:
            result = result.rotate((0, 0, 0), (1, 0, 0), rx)
        if ry != 0.0:
            result = result.rotate((0, 0, 0), (0, 1, 0), ry)
        if rz != 0.0:
            result = result.rotate((0, 0, 0), (0, 0, 1), rz)

        return result

    # -----------------------------
    # メイン API
    # -----------------------------
    def apply_operation(self, op: Operation) -> Tuple[cq.Workplane, Optional[cq.Workplane]]:
        """
        1 つの Operation を適用し、(work, removed) を返す。

        - setup:index など setup 系 op は _apply_setup_index で処理
        - それ以外は cad_ops.apply_op に委譲
          （その際、必要に応じて setup.orientation で一時的にワークを回転）
        """
        self.step_index += 1

        if op.op == "setup:index":
            self._apply_setup_index(op)
            # setup:index 自体は幾何を変えない（現時点では）
            # removed も None のままにしておく
            return self.work, self.removed

        # -------------------------
        # 通常のジオメトリ op
        # -------------------------
        # 1. この op に対して有効な setup を決める
        setup_id = getattr(op, "setup", None)
        if not setup_id:
            setup_id = self.current_setup_id

        setup_def = self.setup_map.get(setup_id) if setup_id else None
        orientation_deg = self._get_orientation_deg(setup_def)

        # 2. world 姿勢の self.work を、一時的に setup 姿勢に回転
        work_for_op = self._apply_orientation(self.work, orientation_deg, forward=True)

        # 3. setup 姿勢で cad_ops.apply_op を実行
        work_after, removed_local = apply_op(work_for_op, op)

        # 4. 結果を world 姿勢に逆回転して self.work / self.removed に戻す
        self.work = self._apply_orientation(work_after, orientation_deg, forward=False)
        self.removed = (
            self._apply_orientation(removed_local, orientation_deg, forward=False)
            if removed_local is not None
            else None
        )

        return self.work, self.removed

    # -----------------------------
    # setup 関連 op
    # -----------------------------
    def _apply_setup_index(self, op: Operation) -> None:
        """
        割り出し op:
        - 今は「current_setup_id の更新」のみを行う。
        - geometry は変えず、後続の通常 op で orientation を使用する。
        """
        # setup の持ち方はモデル次第なので、属性と params 両方を見ておく
        setup_id = getattr(op, "setup", None)
        if setup_id is None:
            params = op.params or {}
            setup_id = params.get("setup")

        # 明示的な setup が無ければ「素の world 姿勢」に戻す扱い
        if not setup_id:
            logger.info(
                "STEP %02d setup:index -> setup=None (identity world, prev=%s)",
                self.step_index,
                self.current_setup_id,
            )
            self.current_setup_id = None
            return

        if setup_id not in self.setup_map:
            raise OpError(f"Unknown setup id: '{setup_id}'")

        logger.info(
            "STEP %02d setup:index -> setup=%s (prev=%s)",
            self.step_index,
            setup_id,
            self.current_setup_id,
        )
        self.current_setup_id = setup_id

    # -----------------------------
    # 補助的なアクセサ
    # -----------------------------
    def get_current_solids(self) -> Tuple[cq.Workplane, Optional[cq.Workplane]]:
        """
        現在のワーク形状と直近の除去形状を返す。
        """
        return self.work, self.removed
