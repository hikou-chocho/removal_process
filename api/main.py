
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
)
from .llm_client import call_stock_extractor, call_feature_extractor
from .cad_ops import OpError
from .process_context import ProcessContext


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

@app.post("/pipeline/run", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest) -> PipelineResponse:
    logger.info(">>> POST /pipeline/run")
    logger.info(
        "PIPELINE start: units=%s origin=%s ops=%d out=%s",
        req.units,
        req.origin,
        len(req.operations),
        req.output_mode,
    )

    # Setup の概要をログに出す（Strategy A）
    setups = getattr(req, "setups", None) or []
    if setups:
        logger.info("PIPELINE setups: count=%d", len(setups))
        for s in setups:
            # Pydantic / dict 両対応
            sid = getattr(s, "id", None) if hasattr(s, "id") else s.get("id", None)
            label = getattr(s, "label", None) if hasattr(s, "label") else s.get("label", None)
            logger.info("  - setup id=%s label=%s", sid, label)

    # 例外系: stock build 等の OpError は 400, それ以外は 500
    try:
        ctx = ProcessContext(req)
        logger.info("STOCK built: type=%s params=%s", req.stock.type, req.stock.params)
    except OpError as e:
        logger.exception("PIPELINE stock build failed (OpError): %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("PIPELINE stock build failed (Unexpected): %s", e)
        raise HTTPException(status_code=500, detail="Internal error during stock build")

    step_results: list[StepResult] = []

    for idx, op in enumerate(req.operations, start=1):
        # この op に対して有効な setup id を決めて、ログに出す
        op_setup = getattr(op, "setup", None)
        # ProcessContext 内部の current_setup_id に依存したくないので、
        # ログ上は「op.setup が優先、無ければ 'current' に任せる」ということだけ書く。
        logger.info(
            "STEP %02d START op=%s name=%s selector=%s setup=%s params=%s",
            idx,
            op.op,
            op.name,
            op.selector,
            op_setup,
            op.params,
        )

        try:
            work, removed = ctx.apply_operation(op)
        except OpError as e:
            logger.exception("STEP %02d FAILED (OpError) op=%s: %s", idx, op.op, e)
            return PipelineResponse(
                status="error",
                message=f"STEP {idx:02d} failed: {e}",
                steps=step_results,
            )
        except Exception as e:
            logger.exception("STEP %02d FAILED (Unexpected) op=%s: %s", idx, op.op, e)
            return PipelineResponse(
                status="error",
                message=f"STEP {idx:02d} failed: internal error",
                steps=step_results,
            )

        solid_path: str | None = None
        removed_path: str | None = None

        # 出力モードが stl の場合のみファイルを書き出す
        if req.output_mode == "stl" and not req.dry_run:
            name_safe = op.name or f"step{idx:02d}"

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

            if work is not None:
                cq.exporters.export(work, solid_path)
            if removed is not None:
                cq.exporters.export(removed, removed_path)

            logger.info(
                "STEP %02d EXPORTED: solid=%s removed=%s",
                idx,
                solid_path,
                removed_path,
            )

        step_results.append(
            StepResult(
                step=idx,
                name=op.name or f"step{idx:02d}",
                solid=solid_path,
                removed=removed_path,
            )
        )

    logger.info("PIPELINE done: steps=%d", len(step_results))
    return PipelineResponse(status="ok", message=None, steps=step_results)


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
