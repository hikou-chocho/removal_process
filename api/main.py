
from __future__ import annotations
import os
from pathlib import Path
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import cadquery as cq
from .models import (
    PipelineRequest,
    PipelineResponse,
    StepResult,
    NLStockRequest,
    NLStockResponse,
    NLFeatureRequest,
    NLFeatureResponse,
    Stock,
    Operation,
    FeaturePipelineRequest,
    FeaturePipelineResponse,
    FeatureStepResult,
)
from .llm_client import call_stock_extractor, call_feature_extractor
from .cad_ops import OpError, build_stock
from .process_context import ProcessContext, FeatureError


# -----------------------------
# Logging setup
# -----------------------------
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

# basicConfig affects root logger; keep it idempotent
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8")
        ],
    )

logger = logging.getLogger("pipeline")

app = FastAPI(title="Removal Process API", version="0.1.0")

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "data" / "output"
OUTDIR.mkdir(parents=True, exist_ok=True)

# 静的ファイル公開: Web UI と出力ディレクトリ
app.mount(
    "/ui",
    StaticFiles(directory=str(ROOT / "web"), html=True),
    name="ui",
)

app.mount(
    "/output",
    StaticFiles(directory=str(ROOT / "data" / "output")),
    name="output",
)

def _export_stl(solid: cq.Workplane, path: Path):
    from cadquery import exporters
    path.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(solid, str(path))


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f">>> {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"<<< {request.method} {request.url.path} {response.status_code}")
        return response
    except Exception as ex:
        logger.exception(f"Unhandled exception during {request.method} {request.url.path}")
        raise


# -----------------------------
# Natural Language → FeatureGraph API
# （Phase1 追加部分）
# -----------------------------


@app.post("/nl/stock", response_model=NLStockResponse)
async def nl_stock(req: NLStockRequest) -> NLStockResponse:
    """
    素材命令（日本語） → Stock JSON

    フロントエンド想定フロー:
      1. ユーザーが素材命令を入力
      2. /nl/stock に POST
      3. 返ってきた `stock` をクライアント側 FeatureGraph に保持
    """
    logger.info(">>> POST /nl/stock")

    # LLM に投げて { "stock": {...} } をもらう
    result = await call_stock_extractor(req.text, language=req.language)

    if "stock" not in result:
        logger.error("Stock extractor result missing 'stock' key: %s", result)
        raise HTTPException(
            status_code=500,
            detail="LLM stock extractor did not return 'stock' key.",
        )

    # Pydantic Stock モデルにバインド
    from .models import Stock  # ローカル import で循環参照を回避

    stock_obj = Stock(**result["stock"])
    logger.info("NL stock extracted: type=%s params=%s", stock_obj.type, stock_obj.params)

    return NLStockResponse(stock=stock_obj)


@app.post("/nl/feature", response_model=NLFeatureResponse)
async def nl_feature(req: NLFeatureRequest) -> NLFeatureResponse:
    """
    フィーチャ命令（日本語） → 単一 Operation JSON

    フロントエンド想定フロー:
      - FeatureGraph.operations に対して 1発話1フィーチャで append。
      - 最終的に /pipeline/run にまとめて投げる。
    """
    logger.info(">>> POST /nl/feature")

    result = await call_feature_extractor(req.text, language=req.language)

    # 最低限のバリデーション
    if "op" not in result or "params" not in result:
        logger.error("Feature extractor result missing required keys: %s", result)
        raise HTTPException(
            status_code=500,
            detail="LLM feature extractor did not return required keys.",
        )

    from .models import Operation  # ローカル import で循環参照を回避

    op_obj = Operation(**result)
    logger.info(
        "NL feature extracted: op=%s selector=%s params=%s",
        op_obj.op,
        getattr(op_obj, "selector", None),
        op_obj.params,
    )

    return NLFeatureResponse(op=op_obj)

@app.post("/pipeline/run", response_model=FeaturePipelineResponse)
async def run_pipeline(req: FeaturePipelineRequest) -> FeaturePipelineResponse:
    """
    Feature-based pipeline (AP238 L0 features with GeometryDelta)
    Unified endpoint for both legacy Operation-based and new Feature-based requests.
    """
    logger.info(">>> POST /pipeline/run")
    logger.info(
        "PIPELINE start: units=%s origin=%s features=%d out=%s",
        req.units,
        req.origin,
        len(req.features),
        req.output_mode,
    )

    # CSYS リストのログ
    if req.csys_list:
        logger.info("CSYS count: %d", len(req.csys_list))
        for cs in req.csys_list:
            logger.info("  - csys name=%s role=%s", cs.name, cs.role)

    try:
        # Stock をビルド
        solid = build_stock(req.stock)
        logger.info("STOCK built: type=%s params=%s", req.stock.type, req.stock.params)

        # リクエストを dict に変換して ProcessContext に渡す
        req_dict = req.dict()
        
        # ProcessContext を初期化（stock は既にビルド済みなので上書き）
        ctx = ProcessContext.from_request(req_dict)
        ctx.solid = solid  # build_stock で作成した solid で上書き
        
    except OpError as e:
        logger.exception("PIPELINE stock build failed (OpError): %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("PIPELINE stock build failed (Unexpected): %s", e)
        raise HTTPException(status_code=500, detail="Internal error during stock build")

    step_results: list[FeatureStepResult] = []

    try:
        # 全フィーチャを適用
        ctx.apply_all_features(req.features)
    except FeatureError as e:
        logger.exception("PIPELINE failed (FeatureError): %s", e)
        return FeaturePipelineResponse(
            status="error",
            message=f"Feature processing failed: {e}",
            steps=step_results,
        )
    except Exception as e:
        logger.exception("PIPELINE failed (Unexpected): %s", e)
        return FeaturePipelineResponse(
            status="error",
            message="Internal error during feature processing",
            steps=step_results,
        )

    # ステップ結果をエクスポート
    for idx, step_record in enumerate(ctx.steps, start=1):
        name_safe = step_record.name or f"step{idx:02d}"
        feature_type = step_record.feature.get("feature_type", "unknown")
        
        logger.info(
            "STEP %02d: name=%s feature_type=%s",
            idx,
            name_safe,
            feature_type,
        )

        solid_path: str | None = None
        removed_path: str | None = None

        # 出力モードが step または stl の場合のみファイルを書き出す
        if req.output_mode in ["step", "stl"] and not req.dry_run:
            solid_path = str(
                (ROOT / "data" / "output" / req.file_template_solid.format(
                    step=idx,
                    name=name_safe,
                )).resolve()
            )
            removed_path = str(
                (ROOT / "data" / "output" / req.file_template_removed.format(
                    step=idx,
                    name=name_safe,
                )).resolve()
            )

            os.makedirs(os.path.dirname(solid_path), exist_ok=True)

            # Solid をエクスポート
            if step_record.delta.solid is not None:
                if req.output_mode == "step":
                    step_record.delta.solid.val().exportStep(solid_path)
                else:
                    cq.exporters.export(step_record.delta.solid, solid_path)

            # Removed をエクスポート
            if step_record.delta.removed is not None:
                if req.output_mode == "step":
                    step_record.delta.removed.val().exportStep(removed_path)
                else:
                    cq.exporters.export(step_record.delta.removed, removed_path)

            logger.info(
                "STEP %02d EXPORTED: solid=%s removed=%s",
                idx,
                solid_path,
                removed_path,
            )

        step_results.append(
            FeatureStepResult(
                step=idx,
                name=name_safe,
                feature_type=feature_type,
                solid=solid_path,
                removed=removed_path,
            )
        )

    logger.info("PIPELINE done: steps=%d", len(step_results))
    return FeaturePipelineResponse(status="ok", message=None, steps=step_results)


if __name__ == "__main__":
    # Allow running directly for local testing / simple container entrypoint.
    # Azure App Service will typically start the app with an ASGI server
    # such as `uvicorn api.main:app --host 0.0.0.0 --port $PORT`.
    try:
        import uvicorn
    except Exception:
        logger.error("uvicorn is not installed; please run via an ASGI server.")
        raise

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Starting uvicorn on {host}:{port}")
    uvicorn.run("api.main:app", host=host, port=port, log_level="info")
